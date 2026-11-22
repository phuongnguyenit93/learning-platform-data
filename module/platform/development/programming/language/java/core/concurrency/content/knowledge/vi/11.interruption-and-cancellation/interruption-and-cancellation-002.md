# interrupt(), isInterrupted() và Thread.interrupted() trong Java

## 1. Interrupt là tín hiệu phối hợp, không phải lệnh buộc thread dừng

Trong Java concurrency, một thread đôi khi cần yêu cầu thread khác **ngừng công việc đang làm**: người dùng hủy tác vụ, ứng dụng đóng, request vượt deadline, hoặc một nhóm worker không còn cần kết quả. Cơ chế căn bản của Java là **interrupt**.

Điểm dễ hiểu sai nhất: **`thread.interrupt()` không tương đương `Thread.stop()`**. Nó không ép mã Java đang chạy dừng tại một vị trí tùy ý, không rollback cập nhật dữ liệu, và không tự đóng mọi I/O. Interrupt là một **tín hiệu hợp tác**. Thread nhận tín hiệu phải đến điểm nhận biết phù hợp, sau đó thực hiện chính sách hủy, dọn dẹp tài nguyên và kết thúc hoặc tiếp tục theo hợp đồng.

Ba phương thức trọng tâm:

- `thread.interrupt()`: yêu cầu ngắt **thread đối tượng đích**. Thông thường đặt *interrupt status* của thread đích; nếu thread đang chờ trong một phương thức interruptible, có thể khiến phương thức đó kết thúc bằng `InterruptedException` hoặc cơ chế đặc thù được API định nghĩa.
- `thread.isInterrupted()`: **đọc trạng thái ngắt của thread đích** mà **không xóa cờ**.
- `Thread.interrupted()`: phương thức **static** kiểm tra trạng thái ngắt của **thread đang thực thi lời gọi** và **xóa trạng thái đó** khi đọc (test-and-clear). Nó không nhận đối tượng đích.

Bài này thuộc phạm vi **Java concurrency nói chung**, tập trung vào Thread API và phối hợp hủy trong JDK; không sử dụng cơ chế riêng của framework.

### Mục tiêu học tập

Sau bài, bạn cần có khả năng:

1. So sánh ý nghĩa, đối tượng tác động và tác dụng phụ của ba API.
2. Giải thích vì sao `InterruptedException` thường xóa cờ interrupt và khi nào nên khôi phục bằng `Thread.currentThread().interrupt()`.
3. Viết worker kiểm tra interrupt khi tính toán, xử lý hủy khi `sleep`/`wait`/`join`/`Condition.await` bị ngắt.
4. Phân biệt yêu cầu hủy với xác nhận hủy đã hoàn tất; dùng `join`, `Future` hoặc cơ chế phối hợp để chờ an toàn.
5. Nhận diện lỗi nuốt interrupt, vô tình xóa cờ, gọi sai phương thức static, và giả định API blocking nào cũng interruptible.
6. Hiểu những giới hạn của interrupt đối với intrinsic monitor, I/O, executor, cancellation và Java Memory Model.

## 2. Bảng so sánh chính xác ba API

| API | Ai thường gọi? | Trạng thái được xét là của ai? | Có xóa cờ interrupt khi kiểm tra không? | Mục đích |
| --- | --- | --- | --- | --- |
| `target.interrupt()` | Thread yêu cầu hủy hoặc chính thread đó | `target` | Không phải thao tác đọc/xóa cờ; gửi yêu cầu ngắt | Yêu cầu thread đích chú ý tín hiệu |
| `target.isInterrupted()` | Bất kỳ thread có reference đến `target` | `target` | **Không** | Quan sát cờ hiện có |
| `Thread.interrupted()` | Thread **đang chạy** | Thread **hiện tại** | **Có** | Kiểm tra và tiêu thụ cờ |
| `Thread.currentThread().isInterrupted()` | Thread đang chạy | Thread hiện tại | **Không** | Tự kiểm tra mà giữ nguyên cờ |

### 2.1. Cú pháp gây nhầm lẫn

~~~java
// Minh họa, không phải chương trình độc lập.
Thread worker = ...;

worker.interrupt();     // Gửi ngắt tới worker.
worker.isInterrupted(); // Đọc cờ của worker, không xóa.

Thread.interrupted();   // Đọc VÀ XÓA cờ của thread đang gọi dòng này.
~~~

**Không được suy luận từ đối tượng reference mà phương thức static kiểm tra đối tượng đó.** Dù Java cho phép gọi static method qua expression thuộc kiểu `Thread`, viết `worker.interrupted()` là cú pháp gây hiểu nhầm và vẫn gọi phương thức static cho **current thread**, không phải kiểm tra worker. Luôn viết `Thread.interrupted()` khi bạn chủ động muốn test-and-clear **chính mình**.

`interrupt()` trả về `void`, nên không có boolean “hủy thành công” được trả từ lời gọi. `isInterrupted()` và `interrupted()` trả boolean về **trạng thái cờ tại thời điểm quan sát**, không phải kết luận nghiệp vụ đã dừng đúng cách.

## 3. Cờ interrupt và quá trình được nhận biết

Một thread có trạng thái interrupt. Một câu chuyện thông thường:

~~~text
Thread A:                         Thread B:
  target.interrupt()  --------->     cờ interrupt được đặt
                                     |
                                     +--> polling isInterrupted()
                                     |      thấy true, tự dọn dẹp, thoát
                                     |
                                     +--> sleep/wait/join/await()
                                            bị ngắt bằng
                                            InterruptedException
                                            (trạng thái thường đã clear)
~~~

Điều gì xảy ra chính xác phụ thuộc vào **thời điểm thread ở đâu** và **API nó đang thực thi**:

- Nếu đang chạy vòng tính toán bình thường, thread không tự bị Java ném exception vào một lệnh tính toán tùy ý. Nó có thể tiếp tục chạy đến lúc tự kiểm tra cờ.
- Nếu đang chờ bằng `Thread.sleep`, `Object.wait`, `Thread.join` hoặc `Condition.await` bản interruptible, lời chờ thường phản hồi bằng `InterruptedException` và cờ interrupt bị **xóa theo hợp đồng**.
- Nếu dùng `ReentrantLock.lockInterruptibly()` hoặc `BlockingQueue.take()`, yêu cầu ngắt có thể làm kết thúc việc chờ bằng `InterruptedException`.
- Nếu đang chờ **lấy intrinsic monitor** để vào `synchronized`, interrupt không tự làm thread thoát khỏi trạng thái chờ monitor. Cờ có thể được đặt, nhưng thread chỉ phản ứng khi đến một điểm có thể xử lý nó.
- Nếu đang trong thao tác I/O, phản ứng có thể phụ thuộc API: một số blocking channel của NIO có quy tắc ngắt/đóng channel riêng; không được áp dụng một kết luận đồng loạt cho mọi nguồn I/O.

Vì thế **gửi interrupt** và **thread hoàn tất** là hai sự kiện khác nhau.

### 3.1. Interrupt đến trước lời gọi sleep

Nếu current thread đã có cờ interrupt khi gọi `Thread.sleep(...)`, lời gọi có thể ném `InterruptedException` ngay thay vì ngủ đủ thời lượng. Điều này giúp worker nhận biết yêu cầu hủy dù tín hiệu tới trước điểm chờ.

Không dùng `Thread.sleep(100)` để “đảm bảo” thread khác đã xử lý interrupt. Sleep chỉ ảnh hưởng lịch chạy của **thread đang gọi**, không xác nhận trạng thái của worker.

### 3.2. Interrupt là yêu cầu không phải phép ép hủy

Ví dụ một thread không bao giờ kiểm tra flag và chỉ chạy phép tính vô hạn:

~~~java
// Sai về khả năng hủy, không phải chương trình độc lập.
for (;;) {
    computeNextStep();
}
~~~

Nếu `computeNextStep` không dùng primitive interruptible hoặc tự kiểm tra cờ, việc gọi `interrupt()` từ ngoài có thể **không làm vòng lặp dừng**. Một giao thức hủy tốt phải thiết kế **cooperative cancellation points** ở những chỗ có thể dọn dẹp và thoát an toàn.

## 4. Ví dụ 1 — test-and-clear bằng Thread.interrupted() (Java 17+)

Để hiểu khác biệt mà không phụ thuộc scheduler, ta dùng **chính thread main** làm đối tượng thí nghiệm. Chương trình chủ động xóa cờ ban đầu, đặt lại nó, quan sát và kiểm tra việc xóa cờ.

Tạo tệp `InterruptFlagDemo.java`:

~~~java
public class InterruptFlagDemo {
    public static void main(String[] args) {
        Thread current = Thread.currentThread();

        Thread.interrupted(); // Đảm bảo trạng thái đầu thí nghiệm là clear.
        current.interrupt();

        System.out.println("isInterrupted #1 = "
            + current.isInterrupted());

        System.out.println("interrupted #1 = "
            + Thread.interrupted());

        System.out.println("isInterrupted #2 = "
            + current.isInterrupted());

        System.out.println("interrupted #2 = "
            + Thread.interrupted());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac InterruptFlagDemo.java
java InterruptFlagDemo
~~~

Stdout khi không có thread bên ngoài can thiệp vào trạng thái của main:

~~~text
isInterrupted #1 = true
interrupted #1 = true
isInterrupted #2 = false
interrupted #2 = false
~~~

Giải thích theo thứ tự:

1. `current.interrupt()` đặt cờ interrupt của current thread.
2. `current.isInterrupted()` chỉ **đọc** trạng thái, nên kết quả lần đầu là true và cờ vẫn còn.
3. `Thread.interrupted()` trả về true **đồng thời xóa cờ**.
4. Lần `isInterrupted()` sau đó trả về false.
5. Lần `Thread.interrupted()` tiếp theo trả về false vì cờ đã bị tiêu thụ ở bước 3.

**Điểm thực hành:** Đừng chèn `Thread.interrupted()` vào logging hoặc một câu điều kiện chỉ cần quan sát. Vì nó xóa cờ, code ở tầng gọi sau đó có thể mất tín hiệu hủy.

## 5. Ví dụ 2 — gọi interrupt vào thread đang sleep (Java 17+)

Đây là ví dụ nhận tín hiệu qua `InterruptedException`. Dùng `CountDownLatch` để bảo đảm main chỉ gửi interrupt sau khi worker đã bắt đầu đoạn code liên quan; không dùng `Thread.sleep` để đoán thời điểm.

Tạo tệp `InterruptSleepDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptSleepDemo {
    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch entered = new CountDownLatch(1);
        AtomicBoolean caught = new AtomicBoolean();
        AtomicBoolean restored = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            entered.countDown();

            try {
                for (;;) {
                    Thread.sleep(1_000);
                }
            } catch (InterruptedException ex) {
                caught.set(true);

                // Vì sleep thường đã xóa cờ, ta khôi phục
                // để code tầng gọi/cleanup có thể quan sát.
                Thread.currentThread().interrupt();
                restored.set(
                    Thread.currentThread().isInterrupted()
                );
            }
        }, "interruptible-worker");

        worker.start();
        entered.await();

        worker.interrupt();
        worker.join();

        System.out.println("caught = " + caught.get());
        System.out.println("restored = " + restored.get());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac InterruptSleepDemo.java
java InterruptSleepDemo
~~~

Đầu ra khi worker không bị lỗi ngoài dự kiến:

~~~text
caught = true
restored = true
~~~

**Vì sao không có race làm thay đổi output?**

- Worker đếm latch trước khi đi vào vòng sleep; main đợi latch rồi mới gửi interrupt. Nếu interrupt đến **trước** lần sleep đầu tiên, `sleep` vẫn nhận cờ và ném `InterruptedException` khi bắt đầu; nếu đến trong lúc sleep, lời chờ được ngắt.
- Vòng sleep chạy mãi nếu không nhận interrupt, nên worker không tự hoàn thành trước yêu cầu hủy.
- Worker bắt exception, lưu `caught=true`, đặt lại interrupt flag và lưu `restored=true`.
- Main gọi `join()` để chờ worker kết thúc rồi mới đọc các kết quả `AtomicBoolean`. Output không phụ thuộc thứ tự log của các thread vì chỉ main in.

**Không nên lấy `worker.isInterrupted()` sau khi thread đã `TERMINATED` làm bằng chứng duy nhất rằng nó từng bị interrupt**. Khi thread đã kết thúc, quan sát cờ của đối tượng không thay thế được việc worker ghi nhận trạng thái xử lý hoặc báo kết quả qua kênh phối hợp.

### 5.1. Tại sao catch rồi gọi interrupt lại?

Một số API chờ như `Thread.sleep` ném `InterruptedException` và **clear interrupt status**. Nếu method hiện tại thuộc `Runnable.run()` không thể khai báo `throws InterruptedException`, một mẫu thực tế là:

~~~java
// Mẫu Runnable, không phải chương trình độc lập.
try {
    performInterruptibleWork();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt(); // Restore flag.
    return; // Dừng tác vụ hoặc bắt đầu cleanup theo hợp đồng.
}
~~~

Khôi phục cờ để tầng cao hơn hoặc code dọn dẹp phù hợp có thể quan sát yêu cầu hủy; **không** vì thế mà tiếp tục làm side effect như tác vụ chưa hề bị hủy. Nếu phương thức có thể khai báo `throws InterruptedException`, việc truyền exception lên thường rõ ràng hơn.

Một trường hợp khác là tầng hiện tại **xử lý hoàn toàn** interrupt theo giao thức của nó và cố ý tiếp tục; khi đó việc giữ hay xóa flag phải được **tài liệu hóa có chủ đích**, không để mất tín hiệu vì một catch rỗng.

## 6. Ví dụ 3 — vòng tính toán tự kiểm tra isInterrupted() (Java 17+)

Với công việc CPU-bound không gọi `sleep`, `wait` hoặc `take`, thread phải tự kiểm tra interrupt để thoát. Cách đơn giản là dùng `!Thread.currentThread().isInterrupted()`.

Tạo tệp `InterruptPollingDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptPollingDemo {
    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        AtomicBoolean noticed = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            started.countDown();

            while (!Thread.currentThread().isInterrupted()) {
                Thread.onSpinWait();
            }

            noticed.set(true);
        }, "polling-worker");

        worker.start();
        started.await();

        worker.interrupt();
        worker.join();

        System.out.println("noticed = " + noticed.get());
        System.out.println("finished = " + !worker.isAlive());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac InterruptPollingDemo.java
java InterruptPollingDemo
~~~

Đầu ra:

~~~text
noticed = true
finished = true
~~~

Worker không dựa vào API chờ ném exception mà chỉ kiểm tra cờ. Main gửi tín hiệu rồi `join()` để xác nhận vòng đã thoát.

**Không dùng đoạn spin vô hạn này như worker production điển hình.** `Thread.onSpinWait()` chỉ là gợi ý tối ưu cho vòng spin, không tạo trạng thái chờ tiết kiệm CPU, không thay thế blocking queue và không tự tạo bảo đảm đồng bộ. Trong ứng dụng có task thật, nên kiểm tra cờ giữa các đơn vị công việc, hoặc dùng primitive blocking phù hợp để tránh đốt CPU.

### 6.1. Nếu gọi Thread.interrupted() trong điều kiện vòng lặp?

Cũng có thể viết:

~~~java
// Mẫu minh họa, không phải chương trình độc lập.
while (!Thread.interrupted()) {
    doSmallUnit();
}
~~~

Khi phát hiện cờ true, `Thread.interrupted()` **đồng thời xóa cờ**. Vòng sẽ thoát, nhưng nếu code sau đó cần thấy cờ, nó có thể không thấy nữa. Thường thích hợp hơn để **tự kiểm tra không tiêu thụ cờ** bằng `isInterrupted()`. Chỉ dùng `Thread.interrupted()` khi có lý do rõ ràng muốn xử lý và xóa một tín hiệu đã nhận.

## 7. Một ví dụ về phương thức static dễ gọi sai

Một đoạn tưởng như hỏi “worker đã bị interrupt chưa”:

~~~java
// Minh họa sai ngữ nghĩa; không phải chương trình độc lập.
Thread worker = new Thread(() -> doWork());

boolean result = worker.interrupted(); // KHÔNG kiểm tra worker!
~~~

`interrupted()` là static method: nó kiểm tra/xóa cờ của **thread chạy đoạn mã trên**, không phải worker. Kết quả tùy trạng thái của caller.

Viết đúng:

~~~java
// Minh họa đúng; không phải chương trình độc lập.
boolean workerFlag = worker.isInterrupted();
boolean myFlagWithoutClear =
    Thread.currentThread().isInterrupted();
boolean myFlagWithClear = Thread.interrupted();
~~~

Khi debug, ghi chú cờ thuộc về **thread nào** và ở **thời điểm nào**. Một flag có thể bị xóa bởi chính thread nhận khi API interruptible ném `InterruptedException` hoặc khi gọi `Thread.interrupted()`. Một lần đọc `isInterrupted() == false` không chứng minh worker chưa từng bị gửi ngắt.

## 8. InterruptedException và hợp đồng xử lý đúng

### 8.1. Truyền lên hoặc khôi phục cờ

Hai mẫu nên nhớ:

**Mẫu A — truyền yêu cầu hủy lên caller có hợp đồng throws:**

~~~java
// Mẫu phương thức, không phải chương trình độc lập.
void doStep() throws InterruptedException {
    Thread.sleep(100);
    // Chỉ thực hiện phần tiếp nếu chưa bị ngắt tại sleep.
}
~~~

**Mẫu B — không thể khai báo throws trong Runnable:**

~~~java
// Mẫu Runnable, không phải chương trình độc lập.
Runnable task = () -> {
    try {
        doStep();
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        // Có thể cleanup, rồi return.
        return;
    }
};
~~~

Nếu method chứa code đã thực hiện một số side effect trước khi interrupt, caller cần biết trạng thái “hoàn thành một phần” theo hợp đồng. Interrupt không tự rollback file write, thay đổi bộ nhớ hoặc truy vấn remote.

### 8.2. Vì sao catch rỗng gây nguy hiểm?

~~~java
// Sai trong nhiều giao thức hủy; không phải chương trình độc lập.
try {
    blockingCall();
} catch (InterruptedException ignored) {
    // Bỏ qua; tiếp tục như chưa nhận yêu cầu hủy.
}
~~~

Lời chờ thường đã xóa cờ trước khi ném exception. Nếu catch rỗng, code bên ngoài không còn cờ để nhận biết, tạo **lost cancellation**. Ứng dụng có thể không dừng lúc shutdown hoặc task kéo dài vượt deadline.

Không phải lúc nào cũng buộc restore: một tầng quản lý chuyên biệt có thể chủ động xử lý ngắt và tiếp tục theo hợp đồng. Nhưng **nuốt không suy nghĩ** là lỗi phổ biến.

### 8.3. Không nhầm exception với một lỗi nghiệp vụ thông thường

`InterruptedException` nói rằng **một thao tác chờ bị ngắt**, không chứng minh kết quả trước đó của toàn task đã bị rollback và không phải lúc nào cũng biểu thị một bug. Thường nó là một phần của cancellation/control flow.

Khi worker bị `InterruptedException`, chọn chính sách rõ:

1. Đóng hoặc release tài nguyên theo ownership phù hợp.
2. Bảo toàn invariant trạng thái (không giữ khóa vô hạn, không để dữ liệu nửa chừng).
3. Trả kết quả hủy/thất bại qua API task nếu cần.
4. Kết thúc, truyền exception hoặc khôi phục cờ theo lớp abstraction đang xử lý.

Trong code chứa `Lock`, luôn dùng `finally` để unlock nếu acquire thành công, bất kể task bình thường hay bị interrupt.

## 9. API blocking nào phản ứng với interrupt?

| Tình huống | Cơ chế thường thấy trên Java 17+ | Lưu ý |
| --- | --- | --- |
| `Thread.sleep(...)` | Ném `InterruptedException` và clear flag | Không tự release monitor mà thread đang giữ |
| `Object.wait(...)` | Ném `InterruptedException`; phải reacquire monitor trước khi hoàn thành lời gọi | Cần giữ monitor đúng object; chờ trong vòng while |
| `Thread.join()` | Thread **gọi join** bị ngắt thì join ném `InterruptedException` | Ngắt waiter, không có nghĩa đã ngắt thread được join |
| `Condition.await()` | Có thể ném `InterruptedException` và trở lại với lock được reacquire | Predicate phải kiểm tra lại trong while |
| `BlockingQueue.take()` | Thường ném `InterruptedException` khi bị ngắt trong chờ | Queue vẫn cần giao thức producer/consumer hợp lệ |
| `CountDownLatch.await()` | Ném `InterruptedException` khi chờ bị ngắt | Không tự biến count về 0 |
| `Semaphore.acquire()` | Có thể ném `InterruptedException` | Không tự hủy những permit đã lấy ở các bước khác |
| `ReentrantLock.lockInterruptibly()` | Chờ lấy lock có thể bị interrupt | Phải unlock nếu acquire thành công |
| `ReentrantLock.lock()` | Không chấm dứt chờ chỉ vì interrupt | Cờ có thể được giữ để xử lý sau |
| Chờ **vào `synchronized`** | Interrupt không tự kết thúc việc chờ monitor | Khác với `Object.wait()` trong monitor |
| `CompletableFuture.cancel(true)` | Không dùng `mayInterruptIfRunning` để điều khiển execution theo hợp đồng API | Không suy ra task underlying đã bị interrupt |
| `Future.cancel(true)` | Yêu cầu hủy và có thể gửi interrupt cho task đang chạy | Chỉ best effort, không bảo đảm side effect dừng tức thì |

**Không suy rộng quá mức về I/O:** Ví dụ một số NIO interruptible channel ném `ClosedByInterruptException` và đóng channel khi thread chờ bị ngắt, trong khi các loại blocking I/O khác có hợp đồng riêng. Kiểm tra chính xác Javadoc của tài nguyên đang dùng.

Một phương thức có tên “blocking” không đồng nghĩa nó sẽ luôn ném `InterruptedException`; cả bộ phận API và thời điểm xử lý ngắt đều quan trọng.

### 9.1. Thread.join() khác interrupt(thread)

Nếu main đang `worker.join()` và một thread khác gọi `main.interrupt()`, **main** có thể nhận `InterruptedException` từ `join()`. Worker không bị main tự động interrupt, nên có thể tiếp tục chạy.

Ngược lại, nếu main gọi `worker.interrupt()` trong khi worker đang chờ, worker có thể nhận interrupt; main vẫn phải `join()` hoặc cơ chế khác nếu cần xác nhận hoàn thành.

Không dùng tên phương thức `join` như bằng chứng công việc thành công; nó chỉ chờ thread kết thúc. Lỗi của task cần được đưa ra kênh riêng nếu caller cần xử lý.

## 10. Ví dụ 4 — Future.cancel(true) yêu cầu hủy task (Java 17+)

Executor quản lý worker thread nên caller thông thường **không giữ reference để tự gọi worker.interrupt()**. Khi submit task, `Future.cancel(true)` là cơ chế yêu cầu hủy. Task vẫn phải hợp tác, ví dụ nhận `InterruptedException` khi sleep.

Tạo tệp `FutureCancellationDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class FutureCancellationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean noticedInterrupt = new AtomicBoolean();

        try {
            Future<?> future = pool.submit(() -> {
                entered.countDown();
                try {
                    for (;;) {
                        Thread.sleep(1_000);
                    }
                } catch (InterruptedException ex) {
                    noticedInterrupt.set(true);
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });

            entered.await();
            boolean requestAccepted = future.cancel(true);
            finished.await();

            System.out.println("cancel accepted = " + requestAccepted);
            System.out.println("future cancelled = " + future.isCancelled());
            System.out.println("worker noticed = " + noticedInterrupt.get());
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                System.out.println("pool still shutting down");
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FutureCancellationDemo.java
java FutureCancellationDemo
~~~

Đầu ra thông thường khi task không bị lỗi khác và executor dừng trong 5 giây:

~~~text
cancel accepted = true
future cancelled = true
worker noticed = true
~~~

Phân tích:

- `entered` bảo đảm task đã thực sự chạy và bước vào vùng code trước khi caller hủy.
- `cancel(true)` yêu cầu hủy và cho phép interrupt worker đang chạy. Đây không phải lời hứa chung rằng mọi task có thể bị ép dừng trong một thời gian giới hạn.
- Trong ví dụ, vòng `sleep` phản ứng với interrupt; catch đánh dấu trạng thái, restore flag và thoát.
- `finished.await()` là xác nhận **code cleanup của task đã tới cuối**, khác với riêng `future.isCancelled()`. Caller đọc `noticedInterrupt` sau latch để có kết quả quan sát ổn định.
- `shutdownNow()` là yêu cầu ngắt các worker đang hoạt động và trả danh sách task chưa bắt đầu, không đồng nghĩa đảm bảo mọi task kết thúc ngay; `awaitTermination` chờ thêm theo giới hạn.
- Nếu task bên trong không kiểm tra interrupt hoặc bị kẹt ở API không hủy được, `cancel(true)` có thể đánh dấu future đã hủy trong khi code thực sự vẫn còn chạy.

Đừng dùng `future.isCancelled()` làm bằng chứng một transaction đã rollback, file đã đóng hoặc thao tác mạng đã dừng. Phân biệt **trạng thái Future** và **trạng thái tài nguyên bên ngoài**.

## 11. Memory Model: interrupt và happens-before

Java Memory Model có quy tắc quan trọng: **một hành động interrupt thread đồng bộ theo quan hệ happens-before với điểm thread đích phát hiện ra interrupt** (ví dụ kiểm tra thông qua `isInterrupted()`/`Thread.interrupted()` hoặc nhận `InterruptedException` theo API thích hợp).

Điều này giúp mô hình công bố các cập nhật được thực hiện trước hành động interrupt tới điểm nhận biết trong thread đích. Tuy nhiên, không nên dùng interrupt như **giao thức giao dữ liệu tùy tiện** hoặc thay thế một primitive thông báo trạng thái nghiệp vụ.

Ví dụ cần phân biệt:

~~~java
// Minh họa, không phải chương trình độc lập.
payload = prepareData();
worker.interrupt(); // Tín hiệu hủy và có ràng buộc HB khi worker nhận biết.
~~~

Nếu worker thực sự nhận biết interrupt theo hợp đồng, những hành động trước interrupt của sender có quan hệ HB phù hợp. Nhưng:

- Nếu worker không bao giờ kiểm tra và không vào API interruptible, bạn không có điểm nhận biết để dựa vào.
- Nếu nhiều thread còn cập nhật `payload` đồng thời, cần bảo vệ bằng giao thức đồng bộ riêng.
- Nếu cần truyền công việc/kết quả theo nhiều phiên hoặc nhiều producer, nên dùng `BlockingQueue`, `Future` hoặc cấu trúc dữ liệu có memory-consistency contract rõ ràng.
- Nếu cần đợi worker hoàn tất, `join()`/latch/future vẫn là cơ chế chờ; `interrupt()` chỉ là yêu cầu.

`volatile boolean cancelled` hoặc `AtomicBoolean` cũng có thể là một giao thức cờ hủy khi worker chỉ làm CPU work. Tuy vậy, chỉ cập nhật cờ riêng có thể **không đánh thức** thread đang block trên queue/sleep/wait. Interrupt kết hợp điểm chờ interruptible thường phù hợp hơn trong trường hợp đó.

## 12. Thiết kế interruptible worker đúng cách

### 12.1. Chia task thành đơn vị nhỏ

Để hủy phản hồi nhanh mà không kiểm tra flag từng phép toán, chia công việc thành các bước hữu hạn:

~~~java
// Mẫu xử lý CPU work, không phải chương trình độc lập.
void runTask() {
    while (!Thread.currentThread().isInterrupted()) {
        if (!hasMoreWork()) {
            return;
        }
        processOneBoundedUnit();
    }
}
~~~

Điều kiện để mô hình này phản hồi tốt:

- `processOneBoundedUnit()` cần có thời lượng hữu hạn hoặc điểm kiểm tra bổ sung.
- Nếu method block trên I/O không interruptible, flag có thể được đặt mà thread vẫn kẹt.
- Những side effect đã xảy ra phải có quy tắc idempotency/compensation nếu cần retry.
- Khi thoát cần cleanup tài nguyên, có thể đặt trong `finally` hoặc try-with-resources.
- Nếu API cần báo lý do hủy, cung cấp kết quả phù hợp; không chỉ in log rồi biến mất.

### 12.2. Không tự dừng thread khác bằng Thread.stop()

`Thread.stop()` không an toàn vì có thể dừng một thread ở chỗ đang giữ lock hoặc đang phá vỡ bất biến, và API này đã deprecated. Lựa chọn đúng thường là **cooperative cancellation** bằng interrupt/flag, kết hợp điều kiện hoàn thành, deadline và giải phóng tài nguyên do worker sở hữu.

### 12.3. Dọn dẹp và interrupt flag

Nếu dọn dẹp có các phép chờ interruptible, việc **khôi phục cờ ngay** rồi gọi các phép chờ có thể khiến chúng ném `InterruptedException` ngay. Cách sắp xếp restore, cleanup và propagate cần theo hợp đồng và tính an toàn của tài nguyên.

Một mẫu đơn giản khi catch ở rìa Runnable:

~~~java
// Mẫu logic, không phải chương trình độc lập.
boolean interrupted = false;
try {
    doInterruptibleWork();
} catch (InterruptedException ex) {
    interrupted = true;
} finally {
    releaseResourcesWithoutUnboundedWait();
    if (interrupted) {
        Thread.currentThread().interrupt();
    }
}
~~~

Đây chỉ là mẫu nếu cleanup không phụ thuộc một phép chờ dài có thể bị ngắt và không có exception khác cần xử lý. Trong ứng dụng thật, phải cân nhắc thứ tự cleanup, exception bổ sung và truyền lại tín hiệu cho tầng sở hữu tác vụ. Điều cốt lõi là **không vô tình làm mất yêu cầu hủy**.

## 13. Các lỗi thường gặp

| Lỗi | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Xem `interrupt()` là force-stop | Worker có thể không hợp tác | Thiết kế điểm kiểm tra và chờ interruptible |
| Dùng `target.interrupted()` để hỏi cờ target | Đây là static method của **current thread** | Dùng `target.isInterrupted()` |
| Gọi `Thread.interrupted()` để “log trạng thái” | Xóa cờ một cách vô ý | Dùng `Thread.currentThread().isInterrupted()` |
| Catch `InterruptedException` rỗng | API chờ thường đã clear flag; mất thông báo hủy | Propagate hoặc restore rồi thoát theo hợp đồng |
| Gọi `interrupt()` rồi giả định task đã dừng | Chỉ mới yêu cầu, task có thể còn chạy | Chờ `join`, latch hoặc lifecycle outcome |
| Cứ thấy cờ true là ném `InterruptedException` thủ công mọi nơi | Có thể làm lệch hợp đồng exception của API | Xử lý theo thiết kế và điểm cancellation phù hợp |
| Gọi `Thread.sleep` để “đợi worker hủy xong” | Sleep không xác nhận hoàn tất | Dùng `join`/Future/CountDownLatch |
| Tưởng interrupt mở được `synchronized` đang bị chặn | Entry vào intrinsic monitor không interruptible | Thiết kế lock ordering hoặc chọn `lockInterruptibly` nếu cần |
| Tưởng interrupt hủy mọi I/O | API I/O có hợp đồng khác nhau | Kiểm tra API, timeout, close tài nguyên |
| Dùng `Future.cancel(false)` rồi mong worker đang chạy nhận interrupt | `mayInterruptIfRunning=false` không yêu cầu interrupt worker đang chạy | Chọn true khi hợp lý; task vẫn phải hợp tác |
| Cho rằng `future.isCancelled()` = cleanup xong | Future state không đồng nhất lifecycle của side effect | Phối hợp xác nhận hoàn tất riêng |
| Sau khi worker đã kết thúc mới đọc flag để suy ra lịch sử | Cờ tại thời điểm sau không phải nhật ký mọi interrupt | Ghi nhận trạng thái trong task, dùng kênh kết quả |
| Tự retry task sau interrupt mà không xét idempotency | Có thể lặp side effect | Thiết kế retry và compensation theo nghiệp vụ |

## 14. Kiểm tra trong thực tế

### 14.1. Kiểm thử hủy có kiểm soát

Không nên viết test dựa trên `Thread.sleep(50)` của main rồi đoán worker chắc đã vào trạng thái chờ. Thay vào đó:

1. Dùng `CountDownLatch` hoặc primitive tương tự để nhận biết worker đã vào đoạn code cần kiểm tra.
2. Gửi `interrupt()` hoặc `Future.cancel(true)`.
3. Chờ xác nhận kết thúc bằng `join`, latch hay Future theo đúng hợp đồng.
4. Kiểm tra task có giữ invariant, release lock, đóng tài nguyên và không bỏ qua yêu cầu hủy.
5. Đặt timeout để test không treo vô hạn nếu code cố tình không hợp tác.
6. Phân biệt “future đã cancel” và “worker thật sự chạm đến cleanup”.
7. Test cả trường hợp interrupt đến trước khi worker vào `sleep` và đến trong lúc worker đang chờ.
8. Với CPU-bound worker, test việc tự kiểm tra flag; với blocking worker, test API thật mà worker dùng.

### 14.2. Quan sát và debug

- Thread dump giúp nhìn trạng thái `RUNNABLE`, `WAITING`, `TIMED_WAITING`, `BLOCKED`; nó không phải lịch sử đầy đủ các lần interrupt.
- Log nên ghi **event nhận interrupt**, lý do cancel và kết quả cleanup, tránh chỉ log boolean cờ có thể bị xóa.
- Với `ExecutorService`, theo dõi thời gian shutdown, task không phản hồi cancellation và tài nguyên còn mở.
- Nếu task không dừng, xác định nó có kiểm tra flag, đang chờ primitive nào, có giữ khóa ở chỗ chặn không và liệu API đó có phản ứng với interrupt hay không.
- Giữ thời gian hủy có thể dự đoán: task chạy I/O dài nên có timeout hoặc cơ chế đóng tài nguyên riêng phù hợp.

### 14.3. Giới hạn của test

Một stress test thành công không chứng minh mọi interleaving có thể xảy ra đều an toàn. Cần lập luận theo Java Memory Model và hợp đồng API. Các ví dụ trong bài cố tình dùng latch và output sau join để **không khẳng định thứ tự scheduler ngẫu nhiên là cố định**.

## 15. Câu hỏi tự kiểm tra

**1.** `worker.interrupt()` có đảm bảo worker kết thúc trước khi method trả về không?

Không. Nó gửi yêu cầu ngắt và có thể làm các lời chờ interruptible phản hồi; worker cần hợp tác và có thể cần dọn dẹp trước khi kết thúc. Dùng `join` hoặc cơ chế khác để chờ.

**2.** `worker.isInterrupted()` khác `Thread.interrupted()` ở đâu?

`worker.isInterrupted()` đọc cờ của worker mà không clear; `Thread.interrupted()` đọc **current thread** và clear cờ đó. Một hàm có receiver, một hàm static.

**3.** Sau khi `Thread.sleep(...)` ném `InterruptedException`, vì sao catch có thể cần `Thread.currentThread().interrupt()`?

Vì sleep thường đã xóa cờ khi ném exception; restore giúp tầng cao hơn nhận biết yêu cầu hủy nếu method không truyền exception lên.

**4.** Nếu worker không gọi bất kỳ API blocking nào và không kiểm tra cờ, interrupt có buộc nó dừng không?

Không. Interrupt là hợp tác; vòng tính toán phải tự kiểm tra cờ hoặc một cơ chế hủy hợp lệ khác.

**5.** Tại sao `Thread.interrupted()` gọi từ thread main không giúp kiểm tra cờ của worker?

Vì đó là static method, luôn tác động tới thread **đang chạy** lời gọi — ở đây là main — bất kể có biến worker nào trong scope.

**6.** Main đang chờ `worker.join()` và chính main bị interrupt. Điều gì xảy ra?

`join()` có thể ném `InterruptedException` cho **main**, không phải tự động gửi interrupt cho worker. Code caller cần xử lý tín hiệu hủy và quyết định có yêu cầu worker dừng riêng hay không.

**7.** `Future.cancel(true)` trả true có chứng minh mọi side effect của task đã dừng hoàn toàn không?

Không. Future có thể được đánh dấu hủy trong khi task chưa phản ứng hoặc cleanup chưa xong. Cần protocol xác nhận nếu business yêu cầu.

**8.** Khi nào nên chọn `Thread.interrupted()` thay vì `isInterrupted()`?

Khi **chủ ý** kiểm tra và tiêu thụ interrupt status của **chính thread hiện tại**, với giao thức cụ thể xử lý tín hiệu đó. Nếu chỉ polling hoặc quan sát không phá trạng thái, ưu tiên `isInterrupted()`.

**Ghi nhớ:** `interrupt()` là **yêu cầu** ngắt thread đích; `isInterrupted()` là **quan sát không xóa**; `Thread.interrupted()` là **kiểm tra và xóa cờ của current thread**. Xây dựng cancellation đúng cần xác định điểm nhận interrupt, xử lý `InterruptedException`, giữ nguyên tín hiệu khi phù hợp, bảo vệ bất biến và chờ task thật sự kết thúc nếu nghiệp vụ yêu cầu.