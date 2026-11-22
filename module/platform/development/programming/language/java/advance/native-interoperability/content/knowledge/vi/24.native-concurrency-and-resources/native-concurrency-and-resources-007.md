# Hủy tác vụ kéo dài, timeout và giới hạn khả năng can thiệp của luồng Java

## 1. Bài toán trong Java và native interoperability

Một tác vụ Java có thể gọi JNI, JNA hoặc Foreign Function & Memory API (FFM) để thực thi mã C/C++, gọi hệ điều hành, truy cập thiết bị, chờ I/O hoặc chạy thuật toán native kéo dài. Khi yêu cầu của người dùng đã hết hạn, ứng dụng phải ngừng chờ và cố gắng dừng công việc. Hai việc này có ý nghĩa khác nhau.

**Ba khái niệm cần tách biệt:**

- **Timeout (hết thời gian chờ):** bên gọi không tiếp tục đợi kết quả sau một khoảng thời gian hoặc một deadline. Timeout tự nó không chứng minh rằng tác vụ đã dừng.
- **Cancellation (yêu cầu hủy):** một tín hiệu yêu cầu tác vụ kết thúc sớm. Tác vụ chỉ dừng có kiểm soát nếu mã đang chạy nhận tín hiệu và có cơ chế thoát.
- **Termination (thực sự kết thúc):** mã Java/native không còn thực thi tác vụ, tài nguyên đang dùng đã được đóng theo giao ước an toàn, và trạng thái hoàn thành đã được xác nhận.

Ví dụ: luồng Java gọi một hàm native đọc dữ liệu từ driver trong 90 giây. Một request HTTP chỉ còn ngân sách 500 ms. Request có thể timeout sau 500 ms, nhưng driver vẫn bị chặn trong lời gọi native. Gọi interrupt hoặc hủy Future không tự động làm driver trả về. Khi nhiều request tương tự xảy ra, pool có thể cạn luồng, handle native bị giữ lâu và những yêu cầu mới tiếp tục timeout.

**Nguyên tắc cốt lõi:** thiết kế thời hạn ở tầng gọi, kênh hủy có hợp đồng ở tầng thực thi, và một cơ chế xác nhận kết thúc trước khi thu hồi tài nguyên mà tác vụ còn sử dụng.

## 2. Luồng Java thực sự có thể can thiệp đến đâu?

### 2.1. Interrupt là tín hiệu hợp tác, không phải lệnh giết luồng

**Thread.interrupt()** đặt cờ ngắt của luồng. Một số lời gọi chờ trong Java như **Thread.sleep**, **Object.wait**, **Thread.join**, **BlockingQueue.take/poll** hoặc **Lock.lockInterruptibly** phản ứng bằng **InterruptedException**. Khi ngoại lệ này được ném ra, cờ ngắt thường đã bị xóa; nếu mã không ném tiếp ngoại lệ mà chọn kết thúc ở tầng hiện tại, nên khôi phục bằng **Thread.currentThread().interrupt()** để tầng trên nhận biết.

Trong vòng lặp tính toán thuần Java, mã thường phải chủ động kiểm tra **Thread.currentThread().isInterrupted()**. Khác với **Thread.interrupted()** (phương thức static), **isInterrupted()** không xóa cờ. Chờ để đi vào khối **synchronized** bằng monitor thông thường không có API ngắt như **lockInterruptibly()**. Không nên mặc định mọi hoạt động đọc/ghi I/O đều có hành vi interrupt giống nhau; phải tra hợp đồng của API cụ thể.

Một luồng khác không có API Java an toàn để tùy tiện dừng ngay bất kỳ lệnh nào đang chạy. **Thread.stop()** đã lỗi thời vì có thể phá vỡ bất biến của đối tượng và nhả monitor khi trạng thái đang cập nhật dở. Luồng daemon chỉ ảnh hưởng đến việc JVM có chờ nó khi thoát hay không, không phải cơ chế hủy an toàn.

### 2.2. Qua biên JNI/JNA/FFM, tín hiệu Java không tự biến thành hủy native

Ở phía JNI, JNA hay một lời gọi **Linker.downcallHandle** của FFM, mã native có thể chặn trong thư viện bên ngoài hoặc syscall. **Thread.interrupt()** không có quy tắc chung buộc hàm native đang chạy phải trả về, và không tự ánh xạ thành một lệnh hủy của mọi thư viện C/C++ hay thiết bị. Một syscall có thể có cơ chế ngắt riêng của hệ điều hành; không được suy ra rằng interrupt của Java tương đương với việc gửi tín hiệu OS như **EINTR**.

Hủy được hay không phụ thuộc vào hợp đồng native:

| Hoạt động | Động tác có tác dụng | Điều không được suy diễn |
| --- | --- | --- |
| Java đang sleep, await, poll có hỗ trợ interrupt | Interrupt làm chờ kết thúc qua InterruptedException | Tất cả đoạn mã trước đó tự rollback |
| Vòng lặp tính toán Java | Kiểm tra cờ ngắt hoặc token, tự thoát | Một luồng khác có thể giết an toàn bằng Thread.stop |
| Lời gọi JNI/JNA/FFM đồng bộ bị chặn | Timeout/cancel API riêng của native, hủy I/O theo API của thiết bị hoặc hợp đồng thư viện | Future.cancel(true) chắc chắn ngắt được hàm C |
| Native worker do thư viện tự tạo | Token/handle hủy và cơ chế join/await của thư viện | Ngắt luồng Java gọi API sẽ ngắt mọi native worker |
| Tác vụ chạy trong tiến trình con | Gửi lệnh dừng, đóng kênh, cuối cùng dừng tiến trình nếu cần | Dừng tiến trình bảo đảm cleanup nghiệp vụ hoặc rollback |

Với FFM, việc có một **Arena** hay **MemorySegment** không đồng nghĩa với có API hủy lời gọi. Đóng hoặc giải phóng bộ nhớ đang được native dùng không phải biện pháp hủy: trước hết cần hoàn tất hoặc cách ly lời gọi theo hợp đồng vòng đời, tránh truy cập bộ nhớ sau khi giải phóng.

## 3. Timeout trên Future: bên chờ được giải phóng, tác vụ có thể còn chạy

Với **ExecutorService**, **Future.get(timeout, unit)** giới hạn thời gian mà thread gọi **get** phải chờ. Khi hết hạn, phương thức ném **TimeoutException**; nó **không tự gọi cancel**. Nếu muốn yêu cầu hủy, bên gọi chủ động gọi **future.cancel(true)**.

- **cancel(false):** yêu cầu hủy Future; không cố gắng ngắt luồng đang chạy.
- **cancel(true):** cố gắng interrupt luồng thực thi nếu tác vụ đang chạy. Giá trị **true** trả về chỉ có nghĩa yêu cầu hủy trạng thái Future được chấp nhận; nó không chứng minh mã native đã dừng.
- Sau khi Future bị hủy, **get()** ném **CancellationException**. Quan sát **isDone() = true** hoặc **isCancelled() = true** cho biết trạng thái của Future, không chứng nhận tài nguyên native đã được giải phóng.
- **ExecutorService.shutdownNow()** cố gắng interrupt các tác vụ đang chạy và trả về các tác vụ chưa bắt đầu; nó không có bảo đảm mọi tác vụ đều ngừng. **awaitTermination** chỉ chờ một thời gian, không giết luồng.

**CompletableFuture** có sắc thái khác: **orTimeout** hoàn tất future bằng **TimeoutException**, còn **completeOnTimeout** cung cấp giá trị thay thế khi hết hạn. Công việc đã bắt đầu ở phía sau có thể vẫn chạy. Theo hợp đồng **CompletableFuture.cancel(mayInterruptIfRunning)**, tham số **mayInterruptIfRunning** không điều khiển interrupt của tác vụ nền. Vì vậy, không dùng CompletableFuture timeout như bằng chứng rằng một lời gọi JNI đã bị chặn nay đã kết thúc.

### 3.1. Ví dụ Java 17+: timeout, gửi yêu cầu hủy và xác nhận worker đã thoát

Đây là chương trình **độc lập**, minh họa một tác vụ Java **có hợp tác với interrupt**. Nó không giả lập khả năng hủy lời gọi native bất kỳ.

~~~java
// CancelTimeoutDemo.java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class CancelTimeoutDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);

        Future<?> future = executor.submit(() -> {
            entered.countDown();
            try {
                while (!Thread.currentThread().isInterrupted()) {
                    Thread.sleep(200);
                    // Thực tế: làm một phần công việc nhỏ ở đây.
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                exited.countDown();
            }
        });

        try {
            entered.await(); // Bảo đảm worker đã bắt đầu.
            try {
                future.get(50, TimeUnit.MILLISECONDS);
                throw new IllegalStateException("Unexpected completion");
            } catch (TimeoutException expected) {
                System.out.println("Caller timed out");
            }

            if (!future.cancel(true)) {
                throw new IllegalStateException("Cancellation not accepted");
            }
            System.out.println("Cancellation requested");

            if (!exited.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker still running");
            }
            System.out.println("Worker stopped");
        } finally {
            executor.shutdownNow();
            if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                System.err.println("Executor still has a running worker");
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CancelTimeoutDemo.java
java CancelTimeoutDemo
~~~

Khi worker được hệ điều hành cấp CPU bình thường, stdout:

~~~text
Caller timed out
Cancellation requested
Worker stopped
~~~

Dòng **Worker stopped** có cơ sở nhờ latch **exited** được báo trong **finally** của worker; bản thân kết quả **cancel(true)** chưa đủ. Nếu máy quá tải đến mức worker không đáp ứng trong hai giây, chương trình chủ động báo lỗi thay vì khẳng định đã dừng. Một lời gọi native không hỗ trợ hủy có thể khiến latch không bao giờ đếm về 0; khi đó không được đóng tài nguyên native đang còn được sử dụng chỉ vì Future đã chuyển sang trạng thái cancelled.

### 3.2. Kiểm soát các mức thời gian khác nhau

Đo riêng **queue wait** (chờ đến lượt chạy), **execution time** (thời gian thực thi), **caller wait** (thời gian bên gọi chờ), **cancellation latency** (từ lúc yêu cầu hủy đến lúc worker dừng), và **cleanup time**. Một timeout bao trùm toàn request không nhất thiết ngăn tác vụ vẫn nằm trong hàng đợi; phải áp dụng deadline ngay cả trước khi bắt đầu native call.

## 4. Dùng một deadline xuyên suốt, tránh nhân đôi thời gian chờ

Nếu quy trình gồm kết nối, chuẩn bị dữ liệu, gọi native và ghi kết quả, việc cấp mới **timeout = 5 giây** cho mỗi bước có thể khiến tổng thời gian lớn hơn năm giây rất nhiều. Thay vào đó, đặt **một ngân sách tổng**, tính **thời gian còn lại** trước mỗi bước và chuyển phần còn lại cho mọi API hỗ trợ timeout.

Đối với đo thời lượng bên trong một tiến trình Java, ưu tiên **System.nanoTime()** vì là nguồn thời gian đơn điệu phù hợp đo elapsed time. **System.currentTimeMillis()** phản ánh đồng hồ tường và có thể bị chỉnh. Ví dụ dưới đây là **các phương thức để tích hợp vào lớp hiện có**, không phải một chương trình Java hoàn chỉnh:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

static String receiveTwo(
        BlockingQueue<String> queue, long timeoutMillis)
        throws InterruptedException, TimeoutException {
    if (timeoutMillis <= 0) {
        throw new IllegalArgumentException("timeout must be positive");
    }
    long budget = TimeUnit.MILLISECONDS.toNanos(timeoutMillis);
    long started = System.nanoTime();

    String first = nextBeforeDeadline(queue, started, budget);
    String second = nextBeforeDeadline(queue, started, budget);
    return first + ":" + second;
}

static String nextBeforeDeadline(
        BlockingQueue<String> queue, long started, long budget)
        throws InterruptedException, TimeoutException {
    long remaining = budget - (System.nanoTime() - started);
    if (remaining <= 0) {
        throw new TimeoutException("Deadline elapsed");
    }
    String value = queue.poll(remaining, TimeUnit.NANOSECONDS);
    if (value == null || System.nanoTime() - started >= budget) {
        throw new TimeoutException("Deadline elapsed");
    }
    return value;
}
~~~

Hai lần poll **chia sẻ cùng ngân sách**, không được nhận riêng hai timeout mới. Kiểu tính bằng hiệu **nanoTime() - started** phù hợp các khoảng thời gian thực tế, không quá xa giới hạn số nguyên 64-bit. Đối với API native nhận deadline dạng thời gian tuyệt đối của hệ điều hành, phải chuyển đổi theo **clock** mà API ấy yêu cầu; không tự truyền trực tiếp giá trị **System.nanoTime()** qua JNI.

Deadline được truyền theo request giúp thư viện quyết định không bắt đầu một bước mới khi thời gian đã hết. Dù có timeout, mã vẫn phải định nghĩa cách xử lý khi kết quả đến muộn: bỏ kết quả, kiểm tra idempotency trước khi commit, hoặc báo trạng thái không chắc chắn nếu side effect đã xảy ra.

## 5. Thiết kế hợp đồng hủy ở biên native

Khi tự quản lý mã C/C++ hoặc thiết kế wrapper, hãy công khai một **cơ chế hủy** thay vì trông chờ Java interrupt làm mọi việc. Một thiết kế thường có **native task handle**, tín hiệu cancel và cơ chế chờ task kết thúc:

~~~text
Java request
   | submit / startNativeTask(config, deadline) -> handle
   |                         |
   |                         v
   |                   native worker
   |                   poll cancel flag
   |                   call bounded I/O
   |                   release owned resources
   |
   | requestCancel(handle) --(atomic flag / wakeup)--> worker
   | awaitFinished(handle, grace period)
   | closeHandle(handle) ONLY when lifetime contract permits
   v
return success / timeout / cancelled / error
~~~

Đây là **phác thảo giao thức**, không phải chữ ký chuẩn có sẵn của JNI, JNA hoặc FFM. Các hàm cần được hiện thực trong thư viện native tương ứng.

Hợp đồng tốt phải trả lời rõ:

1. **Ai sở hữu handle?** Tránh đóng handle từ Java trong khi native worker còn đọc/ghi vào nó. Dùng reference counting, ownership chuyển giao hoặc một API **close** chỉ an toàn sau khi task kết thúc.
2. **Cancel có làm gì?** Đặt cờ nguyên tử, đánh thức condition variable, gửi lệnh hủy I/O hoặc yêu cầu thư viện bên dưới dừng. Nếu thư viện không hỗ trợ, cancel chỉ là lời yêu cầu và trạng thái có thể tiếp tục **RUNNING**.
3. **Worker kiểm tra khi nào?** Trong vòng lặp tính toán, giữa các chunk dữ liệu, trước khi gọi API dài, sau mỗi lần I/O có giới hạn. Không nên chờ đến cuối một lệnh block vô hạn mới kiểm tra.
4. **Đảm bảo bộ nhớ xuyên biên ngôn ngữ ra sao?** Cờ chia sẻ giữa các native thread cần cơ chế đồng bộ phù hợp (ví dụ atomic của C11/C++), không dùng biến thường rồi giả định Java interrupt tạo ra quan hệ happens-before cho mọi truy cập native.
5. **Nếu cancel đua với complete?** Chốt trạng thái cuối cùng một lần, quy định khi nào **CANCELLED**, **SUCCEEDED** hoặc **FAILED** được công bố; tránh trả thành công sau khi tài nguyên đã bị thu hồi.
6. **Ai chịu trách nhiệm cleanup?** Worker giải phóng tài nguyên mà nó sở hữu khi thoát; bên Java chỉ đóng wrapper/handle khi API xác nhận an toàn. Chạy cleanup trong **finally**, nhưng không suy ra rằng finally của Java đã chạy khi Java đang bị chặn chưa trở về từ native.

### 5.1. Mẫu wrapper Java: trạng thái và ownership

Một đối tượng quản lý native task có thể phơi bày giao diện sau. Đây là **mẫu thiết kế, không có phần cài đặt native và không thể biên dịch/chạy độc lập**:

~~~java
interface NativeTask extends AutoCloseable {
    enum State { RUNNING, SUCCEEDED, CANCELLED, FAILED }

    // Không đồng nghĩa chắc chắn đã dừng ngay lập tức.
    void requestCancel();

    // Trả về false nếu vẫn còn chạy sau timeout.
    boolean awaitFinished(long timeout, TimeUnit unit)
            throws InterruptedException;

    State state();

    // Chỉ hợp lệ theo hợp đồng ownership/lifetime đã quy định.
    @Override void close();
}
~~~

Bên dùng nên gửi cancel, **đợi có giới hạn**, rồi chỉ giải phóng handle khi biết chắc worker đã kết thúc hoặc API native có cơ chế giữ sống tài nguyên an toàn. Nếu không chờ được, chuyển handle sang bộ quản lý theo dõi cleanup sau đó hoặc cách ly task trong tiến trình khác; không xóa pointer đang được native sử dụng. Với C/C++ API có **cancel(handle)**, **join(handle)** và **destroy(handle)**, ba thao tác này thường có thứ tự và ý nghĩa khác nhau.

### 5.2. Synchronous native call chỉ có một thread Java

Nếu Java gọi **longRunningNativeCall()** và bị chặn ngay trong hàm, đoạn Java sau lời gọi không thể chạy để xử lý cancellation cho chính lời gọi đó. Có thể dùng một luồng điều phối thứ hai gửi yêu cầu hủy qua handle an toàn, **nếu** API native cho phép hủy đồng thời; hoặc thay đổi thiết kế thành async native task có handle/callback. Đừng dùng ngắt cưỡng bức một OS thread đang giữ mutex, JNI critical region hay con trỏ bộ nhớ chung: có thể gây deadlock, hỏng dữ liệu hoặc crash cả JVM.

Một số thư viện hỗ trợ timeout riêng (**connect timeout**, **read timeout**, **native operation timeout**, **context deadline**). Phải đặt timeout **trong thư viện ở lớp thật sự đang block**. Timeout của Future bên ngoài chỉ là lớp bảo vệ latency của caller.

### 5.3. Blocking I/O, callback và virtual threads

- Với **Socket** Java, các cơ chế như socket read timeout, NIO selector/channel hoặc đóng kênh có hợp đồng riêng; kiểm tra API cụ thể xem việc close/cancel từ thread khác có đánh thức thao tác đang chờ không. Không áp dụng kết quả ấy cho mọi thư viện native.
- Với callback từ native vào Java, định nghĩa trạng thái hủy và ownership của dữ liệu callback. Sau timeout, callback đến muộn phải kiểm tra lifecycle của request trước khi ghi kết quả; không giữ tham chiếu đến vùng nhớ đã đóng.
- **Virtual thread** giúp quản lý nhiều tác vụ Java kiểu chờ theo những API tương thích, nhưng không biến hàm native bị block thành lời gọi tự hủy. Tùy bản JDK và loại lời gọi native, việc block có thể chiếm carrier/platform thread hoặc tài nguyên OS; vẫn phải đặt giới hạn concurrency và timeout tại nơi gọi native.

## 6. Khi không có API hủy: cô lập để kiểm soát hậu quả

Nếu thư viện native có thể block vô hạn, bỏ qua cancel, deadlock hoặc gây crash, cách ly trong **tiến trình con** thường cho ranh giới kiểm soát mạnh hơn. JVM chính gửi request qua IPC, đặt deadline, đợi kết quả và theo dõi sức khỏe tiến trình con. Khi hết hạn:

1. Đánh dấu request timeout; không tiếp nhận kết quả đến muộn như một thành công thông thường.
2. Gửi lệnh hủy/đóng kết nối theo giao thức để tiến trình con có cơ hội cleanup.
3. Chờ một **grace period** hữu hạn; nếu không phản hồi, có thể dừng tiến trình bằng **Process.destroy()**, và khi chính sách cho phép dùng **destroyForcibly()**.
4. Xác minh tiến trình đã thoát bằng **waitFor(timeout, unit)** hoặc cơ chế tương đương, xử lý dữ liệu dang dở và khởi tạo worker mới.

**destroyForcibly()** không có nghĩa toàn bộ transaction đã rollback, thiết bị đã về trạng thái an toàn, hay mọi tiến trình con cháu đều chắc chắn bị dừng trên mọi hệ điều hành. Đó là lý do thiết kế thao tác native nên hỗ trợ idempotency, cleanup sau crash và khôi phục trạng thái. Khi native library có lỗi memory corruption, cách ly tiến trình còn giúp giới hạn tác động lên JVM chính.

Trong cùng một JVM, không tạo thread vô hạn để thay cho timeout. Mỗi native call bị kẹt có thể vẫn giữ thread, file descriptor, khóa và bộ nhớ. Dùng **bounded executor / semaphore** giới hạn số native call đồng thời, hàng đợi có giới hạn và chính sách từ chối có kiểm soát. Nếu một worker cố định bị kẹt không thể phục hồi, hệ thống cần chiến lược chuyển sang tiến trình cô lập hoặc vận hành lại, thay vì ngầm mở rộng pool mãi.

## 7. Thiết kế vòng đời request hoàn chỉnh

Một luồng xử lý production có thể đi theo các bước sau:

| Giai đoạn | Hành động | Bằng chứng cần có |
| --- | --- | --- |
| Admission | Kiểm tra deadline và quota native concurrency | Request chưa hết hạn, còn slot |
| Start | Ghi request ID, thời điểm bắt đầu, tạo native handle theo ownership | Task thực sự đã được nhận |
| Execute | Truyền thời gian còn lại cho mọi native/API I/O hỗ trợ timeout | Worker cập nhật tiến độ/trạng thái |
| Timeout | Trả lỗi timeout cho caller, yêu cầu hủy task | Ghi nhận thời điểm requestCancel |
| Grace period | Đợi **acknowledged stop**, không khóa caller vô hạn | Worker đã thoát hoặc vẫn RUNNING |
| Escalation | Dùng native cancel mạnh hơn hoặc cô lập/dừng tiến trình nếu có | Trạng thái tiến trình/handle rõ ràng |
| Cleanup | Đóng tài nguyên khi không còn người sử dụng | Native task terminated và ownership được giải quyết |
| Observe | Đo timeout, cancellation latency, leaked/stuck operations | Không để tăng vô hạn số task bỏ lại |

**Chính sách trạng thái:** timeout của HTTP request và trạng thái native task nên là hai trường riêng. Chẳng hạn **REQUEST_TIMED_OUT / NATIVE_CANCEL_PENDING** là trạng thái có thể tồn tại hợp lệ; gán ngay **NATIVE_CANCELLED** chỉ vì Future đã cancel sẽ che giấu lỗi tài nguyên. Nếu tác vụ tạo side effect (ghi file, gửi gói tin, cập nhật thiết bị), không tự động retry sau timeout trừ khi thao tác idempotent hoặc có idempotency key/transaction kiểm soát việc thực thi trùng.

**Khôi phục interrupt đúng cách:** khi API Java hỗ trợ ném **InterruptedException**, thông thường cho phép ngoại lệ lan lên nơi quyết định hủy. Nếu bắt ngoại lệ để cleanup và không ném tiếp, khôi phục cờ ngắt. Không dùng vòng **catch (InterruptedException ignored) { }** rồi tiếp tục chạy như chưa có yêu cầu hủy.

## 8. Lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Sau **get(timeout)** coi native call đã dừng | Worker vẫn chiếm tài nguyên | Gửi cancel, theo dõi termination riêng |
| Dựa vào **Future.cancel(true)** để giết JNI/C | Timeout ảo, native tiếp tục chạy | Cung cấp API cancel, bounded native I/O hoặc process isolation |
| Dùng **CompletableFuture.orTimeout** như hủy supplier | Công việc nền âm thầm tồn tại | Điều khiển lifecycle/handle độc lập với trạng thái future |
| Timeout năm giây cho **từng** bước | Tổng latency vượt deadline request | Truyền thời gian còn lại của một deadline |
| Bỏ qua **InterruptedException** hoặc xóa interrupt flag | Task không hợp tác với cancel | Propagate/restore và thoát có kiểm soát |
| Đóng **Arena**, con trỏ hoặc handle trước khi native ngừng | Use-after-free, crash, lỗi dữ liệu | Ràng buộc ownership với acknowledged termination |
| Tăng pool khi native liên tục bị kẹt | Cạn thread, RAM, FD | Bounded concurrency, backpressure, isolation |
| Dùng **Thread.stop()** hoặc ép OS thread chết khi đang giữ lock | Hỏng bất biến, deadlock | Cooperative cancellation, native-specific cancel, tiến trình con |
| Trả **CANCELLED** ngay khi timeout | Che lấp trạng thái vẫn RUNNING | Tách request timeout, cancel requested, terminated |
| Retry tác vụ có side effect sau timeout | Chạy trùng hoặc ghi đè dữ liệu | Idempotency/transaction và truy vết operation ID |

## 9. Kiểm thử và quan sát trong hệ thống thực

Một bộ kiểm thử có giá trị nên bao gồm:

- **Hoàn thành sớm:** trả kết quả đúng, không phát sinh cancel, không rò handle.
- **Timeout trước khi chạy:** task còn xếp hàng được đánh dấu hết hạn và không khởi động native call muộn.
- **Hủy hợp tác:** Java worker bị interrupt, native worker nhận token và xác nhận dừng, tài nguyên giải phóng đúng thứ tự.
- **Native cố ý không phản hồi:** caller timeout đúng hạn nhưng hệ thống không báo nhầm đã dừng; giới hạn in-flight không bị vượt.
- **Race completion/cancel:** thành công và hủy gần như đồng thời vẫn chỉ có một trạng thái cuối; không double-close hoặc callback vào vùng nhớ đã giải phóng.
- **Grace period hết:** xác minh escalation/isolated process dừng đúng chính sách, xử lý cleanup dang dở.
- **Tải lớn:** số lượng thread, native handles, file descriptors và hàng đợi có giới hạn; không tích lũy task zombie sau hàng nghìn lần timeout.
- **Side effect đến muộn:** hệ thống bỏ/đối soát kết quả trễ và ngăn retry gây thực thi lặp.

Ghi log hoặc metric tách bạch **requested timeout**, **actual execution duration**, **cancel requested**, **cancel acknowledged**, **termination observed**, **cleanup completed**. Đính kèm operation ID, thư viện và phương thức native, thời hạn, elapsed time và trạng thái cuối. Đo số native call đang chạy, thời gian nằm trong queue, p95/p99 cancellation latency và số tác vụ bị kẹt vượt grace period. Chỉ dựa trên số **TimeoutException** sẽ bỏ sót nhiều native worker vẫn còn hoạt động.

## 10. Checklist áp dụng

Trước khi đưa một lời gọi JNI/JNA/FFM kéo dài vào production, cần trả lời được: **(1)** timeout nằm ở tầng nào; **(2)** có deadline tổng cho request không; **(3)** native API hỗ trợ timeout/cancel cụ thể nào; **(4)** interrupt của Java có thật sự được native xử lý không; **(5)** làm sao xác nhận worker đã dừng; **(6)** ai sở hữu/đóng bộ nhớ và handle; **(7)** bao nhiêu lời gọi block đồng thời được phép; **(8)** khi hủy thất bại có cơ chế cô lập và khôi phục không; **(9)** kết quả/side effect đến muộn được xử lý thế nào; **(10)** telemetry có phân biệt timeout với termination không.

Kết luận kỹ thuật: **timeout giới hạn thời gian chờ của bên gọi; cancellation là giao thức hợp tác; termination cần được quan sát.** Java có thể truyền yêu cầu ngắt và quản lý thời hạn, nhưng không thể tự bảo đảm dừng an toàn mọi lời gọi native. Tính đúng đắn phụ thuộc vào API của thư viện native, ownership tài nguyên, giới hạn concurrency và phương án cách ly khi không thể hủy trong cùng JVM.
