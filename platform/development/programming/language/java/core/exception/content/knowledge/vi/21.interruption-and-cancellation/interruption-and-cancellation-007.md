# Vì sao không nên nuốt InterruptedException rồi tiếp tục như bình thường

## 1. Vấn đề: một tín hiệu dừng có thể biến mất

Trong Java, một luồng có thể bị yêu cầu **ngắt** (*interrupt*) khi một thành phần khác muốn nó ngừng chờ, hủy công việc, giải phóng tài nguyên hoặc kết thúc có kiểm soát. Việc gọi `thread.interrupt()` gửi tín hiệu tới **luồng đích**, thường qua trạng thái interrupt của luồng; nó không cưỡng chế giết luồng hay tự động hoàn tác công việc đã làm.

Nếu luồng đang ở thao tác chờ có hỗ trợ interruption như `Thread.sleep()`, `Thread.join()` hoặc `BlockingQueue.take()`, nó có thể nhận `InterruptedException`. Nhiều phương thức chờ theo cơ chế này **xóa trạng thái interrupt khi ném ngoại lệ**. Do đó, một đoạn mã như sau có thể vô tình làm mất yêu cầu hủy:

```java
try {
    Thread.sleep(10_000);
} catch (InterruptedException ex) {
    // Bỏ qua rồi tiếp tục công việc.
}
doMoreWork();
```

Đây là **mảnh mã trong một phương thức** có `doMoreWork()` đã được định nghĩa, không phải chương trình độc lập. Nếu có luồng khác yêu cầu ngắt trong lúc `sleep`, phương thức thoát `sleep` qua exception, nhưng handler không chuyển tiếp tín hiệu, không khôi phục cờ, cũng không thay đổi đường điều khiển. `doMoreWork()` vẫn được gọi. Với một vòng lặp worker dài hạn, tác vụ có thể tiếp tục hoạt động dù hệ thống đã yêu cầu dừng.

**“Nuốt `InterruptedException`”** nghĩa là bắt tín hiệu ngắt rồi không chuyển tiếp cho tầng có trách nhiệm, không giữ trạng thái, và vẫn vận hành như chưa xảy ra yêu cầu hủy. Đây là vấn đề về **giao thức phối hợp giữa các luồng**, không chỉ là mất một thông báo lỗi.

## 2. Interrupt là yêu cầu hợp tác, không phải lệnh dừng cưỡng bức

Khi A gọi `worker.interrupt()`, các hành vi chính cần phân biệt:

1. JVM đặt trạng thái interrupted cho **worker**, trừ những trường hợp API chờ phản ứng bằng cách ném `InterruptedException` và xóa trạng thái đó.
2. Nếu worker đang chạy tính toán không kiểm tra interrupt, lời gọi `interrupt()` **không tự dừng** các lệnh tính toán.
3. Nếu worker đang chờ ở một phương thức có hợp đồng interruptible, thao tác chờ có thể ném `InterruptedException` để worker quyết định thoát, trả lỗi hoặc dọn dẹp.
4. Worker có thể chủ động kiểm tra `Thread.currentThread().isInterrupted()` trong vòng lặp không có điểm chờ.
5. Interruption không có chức năng tự rollback thay đổi đối tượng, database, file hoặc request mạng.

Không nên đồng nhất `InterruptedException` với lỗi I/O bình thường hoặc lỗi đầu vào người dùng. Trong nhiều thư viện concurrency, nó thể hiện **một yêu cầu hủy hoặc một thay đổi về chính sách điều khiển luồng**. Nuốt tín hiệu này có thể phá hợp đồng dừng của thành phần cấp trên.

Tuy nhiên, `interrupt()` không luôn có nghĩa “hủy toàn bộ” trong mọi ứng dụng. Ý nghĩa cụ thể do giao thức giữa các thành phần quyết định; nếu một tầng có trách nhiệm xử lý interruption hoàn toàn, nó có thể tiêu thụ tín hiệu một cách có chủ đích. Vấn đề là **bỏ qua mà không đưa ra quyết định điều khiển phù hợp**.

## 3. Cơ chế cờ interrupt và hành vi của các phương thức chờ

Mỗi `Thread` có trạng thái interrupted. Những API quan trọng:

| API | Tác động |
| --- | --- |
| `someThread.interrupt()` | Gửi tín hiệu ngắt tới luồng `someThread`; không chờ nó kết thúc |
| `Thread.currentThread().isInterrupted()` | Kiểm tra cờ của luồng hiện tại; **không xóa cờ** |
| `someThread.isInterrupted()` | Kiểm tra cờ của một luồng được tham chiếu; **không xóa cờ** |
| `Thread.interrupted()` | Phương thức `static` kiểm tra **luồng hiện tại** và **xóa cờ** |
| `Thread.currentThread().interrupt()` | Đặt/khôi phục cờ interrupted cho luồng hiện tại |
| `Thread.sleep(...)` | Nếu bị interrupt khi chờ (hoặc có cờ ngắt khi vào), ném `InterruptedException` và xóa cờ theo hợp đồng |
| `Thread.join(...)`, `Object.wait(...)` | Có thể ném `InterruptedException` khi luồng chờ bị ngắt và xóa cờ |

Hai phương thức dễ nhầm nhất là:

```java
boolean flagStillThere = Thread.currentThread().isInterrupted();
boolean flagAndClearIt = Thread.interrupted();
```

Đây là hai câu lệnh Java hợp lệ bên trong một phương thức. `isInterrupted()` chỉ đọc cờ, còn `Thread.interrupted()` có hiệu ứng **clear-on-read**. Trong loop điều khiển hủy, vô tình dùng `Thread.interrupted()` rồi bỏ qua giá trị trả về có thể xóa mất yêu cầu dừng ngay cả khi không hề catch một `InterruptedException`.

Các API trong `java.util.concurrent` như `BlockingQueue.take()`, `CountDownLatch.await()`, `Future.get()`, `Semaphore.acquire()`, `Lock.lockInterruptibly()` và `Condition.await()` cũng hỗ trợ interruption theo hợp đồng riêng. Nhiều API blocking xóa trạng thái khi ném `InterruptedException`; cần đọc đúng API cụ thể thay vì giả định mọi lời gọi Java đều có cùng hành vi.

Một số API như `LockSupport.park()` có semantics khác: có thể **trở về** khi bị interrupt mà không ném `InterruptedException` và không xóa cờ. Lệnh I/O hoặc thao tác native cũng không nhất thiết phản ứng nhanh với interruption. Vì vậy việc một luồng còn đang chạy sau `interrupt()` không tự chứng minh chương trình sai; cần xem **điểm hợp tác hủy** và trách nhiệm của tác vụ.

## 4. Tại sao `catch (InterruptedException) {}` nguy hiểm?

Nuốt interruption có thể gây nhiều hệ quả:

- **Hủy không hiệu lực:** `Future.cancel(true)` hoặc `ExecutorService.shutdownNow()` đã cố interrupt worker, nhưng task tiếp tục như bình thường.
- **Dừng ứng dụng chậm hoặc không dừng:** các shutdown hook hoặc controller đang đợi worker thoát trong khi worker cứ gọi lại thao tác chờ.
- **Xóa dấu vết hủy:** vì một số phương thức chờ xóa cờ khi ném, tầng trên gọi `isInterrupted()` có thể thấy `false` và hiểu nhầm không có yêu cầu dừng.
- **Chờ thêm lần nữa:** handler bỏ qua exception rồi quay lại `sleep()`, `take()` hoặc `await()`; vì cờ đã bị xóa, lần chờ kế tiếp có thể lại block đến khi có một tín hiệu mới.
- **Tác dụng phụ sau hủy:** worker tiếp tục ghi database, gửi thông báo, xử lý job hoặc thực hiện giao dịch mà caller tưởng đã yêu cầu hủy.
- **Sai contract giữa các tầng:** thư viện đã được yêu cầu kết thúc nhưng che tín hiệu, khiến lớp service hoặc scheduler không biết chính sách dừng đã bị xâm phạm.
- **Khó chẩn đoán:** log có thể chỉ ghi “sleep interrupted” như một cảnh báo không quan trọng, trong khi vấn đề thực là vòng đời không đi theo lệnh hủy.

Một câu lệnh `catch` trống đặc biệt khó review vì người đọc không biết đó là quyết định có chủ đích hay sai sót. Nếu thật sự muốn tiêu thụ interruption, cần mô tả rõ **ai sở hữu yêu cầu hủy** và vì sao trạng thái đã được xử lý đầy đủ.

## 5. Ví dụ Java 17+ chạy được: nuốt tín hiệu và khôi phục tín hiệu

Chương trình sau tạo hai worker tuần tự. Mỗi worker báo đã bắt đầu qua `CountDownLatch` rồi chờ bằng `Thread.sleep(...)`. Luồng main yêu cầu ngắt worker.

- `SWALLOW`: bắt `InterruptedException` rồi vẫn chạy bước tiếp theo; do `sleep` xóa cờ, `isInterrupted()` trong handler là `false`.
- `RESTORE`: bắt lỗi, gọi `Thread.currentThread().interrupt()` và `return` để ngừng task; cờ có giá trị `true` ở điểm kiểm tra sau khôi phục.

Lưu thành **`InterruptedExceptionHandlingDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class InterruptedExceptionHandlingDemo {
    private static void runCase(String name, boolean restore)
            throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        Thread worker = new Thread(() -> {
            try {
                started.countDown();
                Thread.sleep(60_000);
            } catch (InterruptedException ex) {
                System.out.println(name + " caught; flag="
                        + Thread.currentThread().isInterrupted());
                if (restore) {
                    Thread.currentThread().interrupt();
                    System.out.println(name + " stopped; flag="
                            + Thread.currentThread().isInterrupted());
                    return;
                }
                System.out.println(name + " continued despite cancellation");
            }
        }, name);
        worker.start();
        started.await();
        worker.interrupt();
        worker.join();
    }

    public static void main(String[] args) throws InterruptedException {
        runCase("SWALLOW", false);
        runCase("RESTORE", true);
        System.out.println("DONE");
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac -encoding UTF-8 InterruptedExceptionHandlingDemo.java
java InterruptedExceptionHandlingDemo
```

Standard output:

```text
SWALLOW caught; flag=false
SWALLOW continued despite cancellation
RESTORE caught; flag=false
RESTORE stopped; flag=true
DONE
```

**Vì sao output này đáng chú ý?**

1. `started.await()` chỉ xác nhận worker đã chạy đến điểm báo hiệu; main có thể interrupt ngay trước hoặc trong `Thread.sleep`. Cả hai đều khiến thao tác `sleep` phản ứng bằng `InterruptedException`.
2. `Thread.sleep` xóa cờ khi ném, vì vậy cả hai handler in `flag=false` ngay lúc vào `catch`.
3. Trong trường hợp `SWALLOW`, chương trình cố tình thực hiện bước “continued despite cancellation”. Trong worker thực tế có loop, một lần bỏ qua như vậy có thể gây xử lý tiếp nhiều lượt.
4. Trong trường hợp `RESTORE`, handler khôi phục cờ `true` rồi **kết thúc Runnable**. Việc restore đơn thuần mà không thoát đường điều khiển có thể vẫn dẫn đến loop tiếp tục chạy và các lời gọi blocking sau lại lập tức bị interrupt.
5. `worker.join()` chỉ chờ worker kết thúc; nó không chuyển `InterruptedException` xảy ra **ở worker** về main. `runCase` khai báo `throws InterruptedException` vì chính luồng main khi chờ `await` hoặc `join` cũng có thể bị interrupt.

Ví dụ cố tình nhỏ và không có tác dụng phụ thật, không cho thấy mọi dạng I/O đều interruptible. `Thread.sleep(60_000)` là thời gian chờ dự kiến, nhưng trong demo main yêu cầu ngắt ngay nên không đợi đến một phút. Nếu môi trường chạy rất đặc biệt làm main bị interrupt ngoài chương trình, nó có thể ném `InterruptedException` ở `await` hoặc `join`; output liệt kê giả định chương trình chạy bình thường và chỉ có các lệnh interrupt được chỉ ra trong mã.

## 6. Mẫu tốt nhất khi hợp đồng cho phép: truyền tiếp `InterruptedException`

Nếu phương thức đang viết **có thể khai báo `throws InterruptedException`**, cách dễ bảo toàn tín hiệu nhất thường là không bắt nó hoặc bắt chỉ để dọn dẹp rồi ném tiếp:

```java
void waitForItem(BlockingQueue<String> queue)
        throws InterruptedException {
    String item = queue.take();
    process(item);
}
```

Đây là mảnh phương thức trong một lớp có `process(String)` đã được định nghĩa; cần import `java.util.concurrent.BlockingQueue`. `queue.take()` có thể chờ và ném `InterruptedException`. Khi exception thoát từ `waitForItem`, tầng gọi biết thao tác đã dừng vì bị yêu cầu ngắt và có thể quyết định hủy cả quy trình.

Nếu phải dọn dẹp:

```java
void runOneStep() throws InterruptedException {
    Resource resource = acquireResource();
    try {
        blockingOperation();
    } finally {
        resource.close();
    }
}
```

Đây là mẫu cấu trúc, với `Resource`, `acquireResource()` và `blockingOperation()` do ứng dụng định nghĩa. `finally` chạy trên đường rời phương thức khi `InterruptedException` được truyền tiếp. Cần thiết kế `close()` sao cho xử lý được lỗi cleanup, không vô tình che exception ngắt ban đầu.

**Không nhất thiết khôi phục cờ trong mọi đoạn bắt rồi `throw ex`**: với phương thức khai báo `throws InterruptedException`, caller đã nhận được tín hiệu rõ ràng qua exception. Nhiều hợp đồng chờ chủ động xóa interrupt flag khi ném; việc truyền tiếp exception giữ đúng cơ chế đó. Nếu caller cần khôi phục cờ để truyền tín hiệu tới mã cao hơn không thể khai báo ngoại lệ, hãy thực hiện tại ranh giới thích hợp.

## 7. Khi không thể ném checked exception: khôi phục rồi kết thúc

`Runnable.run()` không khai báo `throws InterruptedException`. Với một worker muốn kết thúc khi bị interrupt, mẫu phổ biến:

```java
@Override
public void run() {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            WorkItem item = queue.take();
            process(item);
        }
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return;
    } finally {
        releaseResources();
    }
}
```

Đây là đoạn trong một lớp đã định nghĩa `queue` kiểu `BlockingQueue<WorkItem>` cùng `process`, `releaseResources`; không phải chương trình độc lập. Nó có ba điểm:

- Điều kiện vòng lặp chủ động kiểm tra cờ interrupted.
- `queue.take()` bị interrupt thì ném exception; handler **khôi phục cờ** để đường xử lý phía trên còn thấy tín hiệu.
- `return` kết thúc `run()`, còn `finally` vẫn thực hiện cleanup.

Mẫu này chỉ phù hợp khi interruption được định nghĩa là **yêu cầu kết thúc worker**. Nếu logic nghiệp vụ có transaction phải rollback hoặc checkpoint trước khi dừng, cần tổ chức cleanup có kiểm soát, không chỉ thêm `return`.

Cần tránh mẫu nửa vời:

```java
while (true) {
    try {
        Thread.sleep(1000);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
    }
}
```

Đây là **ví dụ sai có chủ đích**. Sau khi handler khôi phục cờ, vòng lặp lại gọi `sleep`. Vì cờ đã đặt, `sleep` có thể lập tức ném `InterruptedException` và xóa cờ; handler lại đặt cờ. Kết quả có thể là **vòng lặp nóng**, tiêu tốn CPU, không làm việc hữu ích và không kết thúc. Vì vậy **khôi phục cờ phải đi cùng đường điều khiển đúng**, thường là `break`, `return` hoặc truyền một kết quả hủy rõ ràng.

## 8. Vì sao phải cân nhắc cả `catch (Exception)` và các wrapper?

Một phương thức có thể vô tình nuốt interruption dù không viết `catch (InterruptedException)` riêng:

```java
try {
    queue.take();
} catch (Exception ex) {
    logger.warn("Cannot receive next item", ex);
    // Tiếp tục vòng lặp — đã nuốt InterruptedException.
}
```

Đây là **mảnh minh họa lỗi**, với `queue`, `logger` do ứng dụng định nghĩa. `InterruptedException` kế thừa `Exception`, nên khối `catch (Exception)` bắt được nó. Nếu mã cứ tiếp tục, yêu cầu shutdown có thể mất.

Cũng cần kiểm tra code bắt các ngoại lệ cha khác và các adapter đổi checked exception sang unchecked:

- `catch (Throwable)` còn bao gồm `Error`, có thể che tình trạng JVM không an toàn; không phải giải pháp để worker “không bao giờ chết”.
- `throw new RuntimeException(ex)` giữ `cause` nhưng **chưa chắc bảo toàn interrupt status**. Nếu tầng ngoài chỉ kiểm tra cờ, thông tin có thể bị mất.
- Ghi log `ex.getMessage()` rồi bỏ qua không báo đủ ý nghĩa điều khiển của interruption.
- Gói tất cả lỗi thành “request timeout” hoặc “unknown failure” khiến hệ thống không phân biệt bị hủy với phụ thuộc thất bại.

Nếu đang ở một ranh giới API bắt buộc phải chuyển `InterruptedException` sang unchecked và không còn chữ ký truyền tiếp, một mẫu thường dùng là:

```java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Operation interrupted", ex);
}
```

Đây là **mảnh triển khai**, với `blockingOperation()` là hàm interruptible. Nó vừa giữ `cause` vừa khôi phục trạng thái. Tuy nhiên, loại wrapper và quyết định ném phải theo hợp đồng API. Đừng đổi interruption thành lỗi trạng thái khi caller cần phân biệt hủy riêng biệt; một ngoại lệ chuyên biệt có thể phù hợp hơn. Nếu task đã đáp ứng yêu cầu hủy bằng cách kết thúc bình thường và chỉ cần báo “cancelled”, việc ném wrapper cũng không phải lựa chọn bắt buộc.

## 9. Khi nào được phép “tiêu thụ” interruption?

Có những thành phần **sở hữu toàn bộ giao thức hủy** và có trách nhiệm xử lý việc ngắt ngay tại chỗ. Khi đó, không truyền tiếp hoặc không khôi phục cờ có thể là quyết định có chủ đích. Ví dụ một controller đang quản lý dừng hệ thống có thể bắt tín hiệu, chuyển state sang STOPPING, thực hiện cleanup đến trạng thái đã xác nhận, rồi trả kết quả theo hợp đồng riêng.

Để một trường hợp được xem là xử lý đúng, cần chứng minh:

1. Thành phần bắt exception chính là bên chịu trách nhiệm **hoàn tất xử lý tín hiệu hủy**.
2. Tác vụ không tiếp tục thực hiện side effect sai hợp đồng sau khi yêu cầu hủy đã được chấp nhận.
3. Caller hoặc thành phần quản lý vòng đời có cách nhận biết tác vụ đã dừng/hủy đúng, ví dụ Future, trạng thái hoặc callback.
4. Cleanup không che lỗi quan trọng và không đợi vô hạn vì cờ đã bị mất.
5. Quyết định được mô tả và kiểm thử rõ, không phải `catch` trống do quên xử lý.

Một số thư viện có API chỉ chấp nhận trả về bình thường hoặc thông báo cancellation qua kết quả riêng. Trong trường hợp ấy có thể tiêu thụ exception nếu quy trình hủy được hoàn tất và trạng thái phía ngoài vẫn chính xác.

Câu “phải luôn gọi `Thread.currentThread().interrupt()` ngay khi bắt `InterruptedException`” là **quá tuyệt đối**. Với phương thức khai báo checked exception, truyền tiếp `InterruptedException` đã là cách bảo toàn tín hiệu. Với nơi thật sự xử lý xong interruption, giữ cờ có thể làm các thao tác sau bị ngắt ngoài ý muốn. Điều cần tránh là **nuốt vô thức rồi tiếp tục như bình thường**.

## 10. Các API thường phát tín hiệu ngắt như thế nào?

| API | Thao tác | Khi bị interrupt |
| --- | --- | --- |
| `Thread.sleep` | Tạm dừng luồng | Ném `InterruptedException` và xóa trạng thái interrupt |
| `Object.wait` | Chờ monitor theo giao thức wait/notify | Ném `InterruptedException`, xóa trạng thái; phải sở hữu monitor hợp lệ |
| `Thread.join` | Chờ một thread kết thúc | Luồng **đang đợi** nhận `InterruptedException`, không phải lỗi của thread được join |
| `BlockingQueue.take` | Chờ phần tử có sẵn | Có thể ném `InterruptedException`; tác vụ nên dừng/chuyển tiếp đúng hợp đồng |
| `CountDownLatch.await` | Chờ counter về 0 | Có thể ném `InterruptedException` |
| `Future.get` | Chờ kết quả tác vụ | Có thể ném `InterruptedException` ở **thread đang chờ**, khác với `ExecutionException` của task |
| `Semaphore.acquire` | Chờ permit | Có thể ném `InterruptedException` |
| `Lock.lockInterruptibly` | Đợi lock theo cách hỗ trợ ngắt | Có thể ném `InterruptedException` |
| `ExecutorService.awaitTermination` | Chờ executor kết thúc | Có thể ném `InterruptedException` ở thread đang chờ |
| `LockSupport.park` | Dừng chờ theo permit/interrupt | Có thể trở về khi bị ngắt, không phải đường `InterruptedException` thông thường |

Không phải mọi thao tác chờ đều hỗ trợ interrupt. Ví dụ `ReentrantLock.lock()` bình thường không có hợp đồng ném `InterruptedException` trong lúc chờ lock; hãy dùng `lockInterruptibly()` khi muốn hủy theo interrupt. Một số thao tác I/O có cách phản ứng khác nhau tùy kênh, provider và OS. Nếu cần bảo đảm dừng đúng hạn, phải có timeout hoặc cơ chế đóng/hủy tài nguyên thích hợp, không chỉ dựa vào `interrupt()`.

## 11. `Future.cancel(true)` và `shutdownNow()` không thể đảm bảo task dừng

Khi tác vụ chạy trong `ExecutorService`, code quản lý thường dùng:

```java
Future<?> future = executor.submit(task);
future.cancel(true);
```

Đây là mảnh code có `executor` và `task` đã định nghĩa. `cancel(true)` **yêu cầu** hủy công việc và có thể interrupt luồng thực thi nếu tác vụ đang chạy. Điều này không đồng nghĩa JVM đã cưỡng chế hủy mọi tính toán hoặc đảo ngược side effect.

Nếu task:

- đang gọi API interruptible và **tuân thủ tín hiệu**, nó có thể thoát sớm;
- bắt `InterruptedException` rồi bỏ qua, nó **có thể tiếp tục công việc** dù future đã báo cancelled;
- đang tính CPU dài nhưng không kiểm tra cờ, nó có thể tiếp tục cho tới khi kết thúc;
- đang ở thao tác I/O không đáp ứng interruption, nó có thể chưa dừng ngay;
- đã commit DB hoặc gửi request mạng, những hiệu ứng đó không tự bị rollback.

`ExecutorService.shutdownNow()` cố gắng dừng tác vụ đang thực thi bằng interruption, ngừng nhận công việc mới và trả về danh sách tác vụ chưa bắt đầu. Nó là *best effort*; nếu task bỏ qua interrupt, executor có thể không kết thúc trong thời gian mong đợi. `shutdown()` là yêu cầu ngừng nhận task mới nhưng cho công việc đã nộp tiếp tục theo chính sách của executor.

Với `CompletableFuture`, nên nhớ `cancel(boolean mayInterruptIfRunning)` không dùng tham số này để điều khiển interruption theo cách tương đương `FutureTask`; trong triển khai `CompletableFuture`, tham số đó không có hiệu lực vì interrupt không được dùng để kiểm soát xử lý. Đừng xây giao thức dừng task trên giả định mọi API future đều có cùng cơ chế interrupt.

## 12. Hủy khi đang chờ và lỗi của công việc là hai loại thông tin khác nhau

Trong code concurrency, một luồng A có thể chờ kết quả do B thực hiện:

```java
try {
    String value = future.get();
    use(value);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
} catch (ExecutionException ex) {
    handleTaskFailure(ex.getCause());
}
```

Đây là **mảnh code trong phương thức trả về `void`**, với `future`, `use`, `handleTaskFailure` do ứng dụng cung cấp và import `ExecutionException`.

Phân biệt:

- `InterruptedException`: **A đang chờ** bị yêu cầu ngắt. Việc chờ bị gián đoạn; B có thể **vẫn đang chạy**. Muốn hủy cả B cần chính sách riêng, ví dụ `future.cancel(true)` nếu thích hợp.
- `ExecutionException`: task B hoàn tất do lỗi; `getCause()` giữ nguyên nhân thất bại của B. Đây là thông tin **kết quả tác vụ**, không phải tín hiệu interrupt của A.
- `CancellationException`: Future ở trạng thái hủy; điều đó không nhất thiết chứng minh mọi side effect của task đã dừng.
- `TimeoutException` của `future.get(timeout, unit)`: A đợi quá hạn; B có thể tiếp tục chạy trừ khi được hủy theo chính sách.

Nuốt `InterruptedException` trong A rồi gọi `get()` lại có thể khiến A tiếp tục chờ không giới hạn, phá deadline hoặc yêu cầu shutdown. Đó là ví dụ thường gặp của việc “đã yêu cầu ngừng chờ nhưng lại chờ tiếp”.

## 13. Xử lý interruption trong vòng lặp worker

Một worker dài hạn thường có ba loại bước: nhận yêu cầu, xử lý dữ liệu, ghi nhận kết quả. Nếu dùng `BlockingQueue.take()`, thiết kế hợp tác hủy có thể là:

```java
void workerLoop(BlockingQueue<Job> queue)
        throws InterruptedException {
    while (!Thread.currentThread().isInterrupted()) {
        Job job = queue.take();
        execute(job);
    }
}
```

Đây là **mảnh phương thức**, với `Job` và `execute(Job)` do ứng dụng định nghĩa. `take()` nhận tín hiệu interrupt đúng quy tắc, nhưng `execute(job)` cũng cần có hợp đồng xử lý hủy và trạng thái. Nếu `execute` chặn trong I/O hoặc làm việc CPU nặng không có điểm kiểm tra, worker sẽ chưa dừng ngay.

Nếu thay bằng một loop luôn bắt rồi bỏ qua:

```java
while (true) {
    try {
        Job job = queue.take();
        execute(job);
    } catch (InterruptedException ex) {
        // Không làm gì, lặp lại take().
    }
}
```

Đây là **ví dụ sai có chủ đích**. Sau interrupt, `take()` ném, cờ bị xóa, vòng lặp tiếp tục chờ job mới. Điều đó có thể khiến shutdown không thể hoàn tất, dù các thành phần quản lý đã gửi yêu cầu hủy.

Trong thiết kế production còn phải quyết định:

- Nếu worker bị hủy giữa khi xử lý job, job được đánh dấu **cancelled**, **retryable** hay **unknown**?
- Nếu job đã ghi một phần, có transaction/rollback, checkpoint hoặc bù trừ nào được phép?
- Nếu nhiều worker cùng dùng queue, interruption có thể xảy ra sau khi đã lấy một job; job đó cần được hoàn trả/ghi tiến độ theo hợp đồng nào?
- Nếu cleanup xảy ra khi cờ interrupt đang đặt, các thao tác blocking tiếp theo có thể lại ném exception ngay; cần lập kế hoạch cleanup có giới hạn và xử lý lỗi riêng.

Không nên suy ra “đã nhận `InterruptedException`” đồng nghĩa “mọi trạng thái đã được rollback”. Đó là hai mối quan tâm riêng.

## 14. Cleanup, trạng thái và tính nhất quán khi ngắt

Khi nhận yêu cầu hủy, ứng dụng có thể đang giữ lock, file handle, transaction hoặc trạng thái đang thay đổi. Hai nguyên tắc phối hợp:

**Đầu tiên, không che yêu cầu hủy.** Thông thường truyền tiếp `InterruptedException` hoặc khôi phục interrupt flag trước khi kết thúc task, để cấp trên nhận diện được trạng thái.

**Tiếp theo, đảm bảo cleanup theo phạm vi thực tế.** Dùng `finally`, `try-with-resources`, rollback transaction, release lock hoặc checkpoint đúng hợp đồng. Các tác vụ cleanup có thể ném exception hoặc block; không thể giả định quá trình khôi phục luôn thành công.

Ví dụ về cấu trúc có ý nghĩa (mảnh code, các phương thức liên quan phải được định nghĩa):

```java
try {
    startTransaction();
    doInterruptibleWork();
    commitTransaction();
} catch (InterruptedException ex) {
    try {
        rollbackTransaction();
    } catch (RuntimeException rollbackFailure) {
        ex.addSuppressed(rollbackFailure);
    }
    throw ex;
} finally {
    releaseResources();
}
```

Đoạn này giả định phương thức ngoài **khai báo `throws InterruptedException`** và các thao tác DB/rollback là những hàm ứng dụng với kiểu exception tương thích đã định nghĩa. `addSuppressed` giữ thông tin rollback lỗi nhưng **không làm rollback thành công**. Đây chỉ là cấu trúc phân tích; ứng dụng thật phải xử lý mọi ngoại lệ DB, tính không chắc chắn của commit, việc rollback cũng có thể bị interrupt và thông tin liên quan đến giao dịch.

Nếu `commitTransaction()` đã thành công rồi mới có một yêu cầu hủy, dữ liệu commit vẫn có thể tồn tại. Không có bảo đảm “interrupt tức rollback”. Đừng tự động retry một job có side effect sau khi hủy mà không dùng idempotency hoặc đối chiếu.

## 15. Gắn interruption với chính sách timeout và deadline

Yêu cầu ngắt và timeout liên quan nhưng không đồng nhất:

- **Deadline/timeout:** giới hạn thời gian hoàn tất hoặc chờ; `get(timeout)` có thể ném `TimeoutException` cho luồng gọi.
- **Interrupt:** yêu cầu luồng cụ thể ngừng chờ hoặc hợp tác dừng; nhiều API trả `InterruptedException`.
- **Cancellation:** trạng thái vòng đời của task/request, có thể kích hoạt interrupt nhưng còn có semantics về kết quả và side effect.

Một controller có thể hủy future do hết thời gian, nhưng nếu worker nuốt interruption rồi tiếp tục, thời gian thực thi có thể vượt deadline và còn gửi tác dụng phụ sau khi caller đã bỏ cuộc.

Một chiến lược có thể kết hợp timeout, `cancel(true)` khi API hỗ trợ, check cờ interrupt tại các điểm hợp lý, và deadline truyền xuống dependency. Đừng coi `interrupt()` là cơ chế timeout tổng quát cho mọi socket, file, JDBC driver hay dịch vụ bên ngoài.

## 16. Đừng dùng interruption như lỗi nghiệp vụ để retry vô hạn

Ví dụ worker gửi request tới backend. Nếu lỗi mạng tạm thời, có thể retry với số lần giới hạn, backoff và jitter. Nhưng nếu thread bị interrupt, thường đó là tín hiệu từ hệ thống quản lý rằng **không nên tiếp tục retry**.

Sai lầm thường thấy:

```java
while (true) {
    try {
        requestRemote();
        break;
    } catch (Exception ex) {
        Thread.sleep(1000);
    }
}
```

Đây là **mảnh code sai có chủ đích**, với `requestRemote()` đã định nghĩa; để biên dịch phải xử lý hoặc khai báo checked `InterruptedException` từ `sleep`. Nếu vòng retry bắt `Exception` mà không phân biệt lỗi hủy, hoặc catch interrupt ở tầng trên rồi tiếp tục, nó có thể chống lại shutdown.

Mẫu chính sách tốt hơn:

1. Nếu lỗi là **InterruptedException**, truyền tiếp hoặc khôi phục cờ rồi rời task.
2. Nếu là lỗi phụ thuộc có thể retry, kiểm tra deadline và trạng thái interrupt trước vòng kế.
3. Backoff bằng thao tác chờ interruptible để có thể dừng nhanh khi bị hủy.
4. Nếu retry có side effect, dùng idempotency key và kiểm tra kết quả chưa rõ.
5. Khi vượt ngân sách retry, báo lỗi có ngữ cảnh và kết thúc theo hợp đồng.

Không tự động convert interruption thành `IllegalStateException` rồi đưa nó vào nhánh “retry lỗi tạm thời”. Chính sách retry phải nhận biết cancellation là trường hợp riêng.

## 17. Virtual threads cũng cần tôn trọng interruption

Virtual thread (ổn định từ Java 21) vẫn là một `Thread` với trạng thái interrupt và các quy tắc `InterruptedException` ở những API hỗ trợ. Nó giúp chạy nhiều tác vụ blocking nhẹ hơn, **không** làm cancellation tự động hay rollback.

Một virtual thread ngủ trong `Thread.sleep(...)` cũng có thể bị interrupt, ném `InterruptedException` và yêu cầu code quyết định thoát/khôi phục tín hiệu. Nếu handler bỏ qua rồi tiếp tục, virtual thread vẫn có thể thực hiện công việc sai hợp đồng.

Nếu dùng các phiên bản Java mới có **structured concurrency** hoặc framework quản lý nhóm task, hủy các sibling task thường dựa vào interrupt hoặc cơ chế tương tự. Một tác vụ con nuốt tín hiệu có thể làm nhóm khó hoàn tất đúng thời hạn. API structured concurrency và trạng thái ổn định thay đổi theo phiên bản JDK; cần xem hợp đồng JDK thực tế, không áp đặt một đoạn demo của Java 17 cho API không có ở Java 17.

## 18. Cách kiểm thử việc không nuốt interruption

Kiểm thử phải xác nhận **tín hiệu và hành vi sau tín hiệu**, không chỉ assert rằng log có chữ “InterruptedException”.

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Thread đang `sleep` bị interrupt | `InterruptedException` xuất hiện trong chính thread bị ngắt |
| Handler nuốt rồi tiếp tục | Có thể nhìn thấy bước xử lý sau yêu cầu hủy (để phát hiện lỗi) |
| Handler restore và return | Cờ được khôi phục tại điểm cần thiết; task không làm bước nghiệp vụ tiếp theo |
| Phương thức `throws InterruptedException` | Exception được truyền lên caller thay vì bị che |
| Worker dùng `BlockingQueue.take()` | Hủy làm worker rời vòng lặp, không quay lại chờ job vô hạn |
| `Future.cancel(true)` | Task có phản ứng phù hợp; không suy ra mọi side effect đã bị rollback |
| Bị interrupt lúc đang cleanup | Tài nguyên được xử lý theo chính sách; không làm mất thông tin lỗi chính |
| Timeout chờ `Future.get(timeout)` | Caller phân biệt timeout với interrupt và lỗi thật của task |
| Luồng khác đang làm việc | Interrupt một worker không tự “lan exception” sang call stack của worker khác |
| Một loop dùng `Thread.interrupted()` | Xác nhận hành vi clear-on-read không làm tín hiệu hủy bị mất |

Để test ổn định, dùng `CountDownLatch`, `Future`, `AtomicBoolean` hoặc các synchronization primitive để kiểm soát thứ tự, kèm timeout đủ rộng. Tránh test chỉ dựa trên `Thread.sleep(100)` và suy luận scheduler chắc chắn đã chạy. Luôn bảo đảm thread/executor được yêu cầu kết thúc trong `finally`, kể cả khi assertion lỗi.

Nếu một tác vụ không hợp tác và tiếp tục mãi, test cần có giới hạn thời gian và cơ chế cách ly thích hợp; không để cả bộ test treo vô hạn.

## 19. Các lỗi phổ biến và cách sửa

| Cách viết có vấn đề | Hậu quả | Hướng sửa |
| --- | --- | --- |
| `catch (InterruptedException ignored) {}` | Xóa dấu vết hủy, task tiếp tục | Truyền tiếp, hoặc restore cờ và thoát task |
| Bắt `Exception` rồi log và loop tiếp | Nuốt cả interruption của các API blocking | Catch riêng `InterruptedException` trước và tuân thủ hợp đồng |
| `Thread.currentThread().interrupt()` rồi tiếp tục `while(true)` | Lặp nóng khi API chờ ném ngay lần kế | `break`/`return` hoặc phối hợp trạng thái hủy |
| Dùng `Thread.interrupted()` chỉ để kiểm tra mà bỏ kết quả | Vô tình xóa cờ | Dùng `isInterrupted()` nếu cần kiểm tra không phá cờ |
| Coi `cancel(true)` là dừng cưỡng chế | Task có thể còn chạy và tạo side effect | Thiết kế cancellation hợp tác và idempotency |
| Nuốt interrupt để “bảo đảm hoàn tất job” | Có thể phá deadline/shutdown của caller | Tách yêu cầu bắt buộc hoàn tất với giao thức hủy, tài liệu hóa rõ |
| Đổi `InterruptedException` thành lỗi retry thông thường | Worker tiếp tục thử khi đã bị hủy | Phân loại cancellation riêng, giữ cause/flag khi cần |
| Cho rằng interruption rollback DB/file | Dữ liệu có thể đã commit/ghi | Transaction, cleanup, checkpoint và đối soát độc lập |
| Đoán mọi API I/O phản ứng interrupt ngay | Task không dừng đúng hạn | Kiểm tra contract, timeout, đóng tài nguyên khi phù hợp |
| Chỉ ghi log một lần rồi không ai quan sát kết quả | Caller vẫn tưởng task còn chạy | Trả future/trạng thái/callback lỗi rõ ràng |

## 20. Checklist thiết kế API và review code

1. Xác định **ai có quyền interrupt**, interrupt mang nghĩa **cancel**, shutdown, hủy một lần chờ hay tín hiệu khác.
2. Liệt kê các điểm chờ interruptible: `sleep`, `wait`, `join`, `take`, `get`, lock, latch và các API tích hợp khác.
3. Nếu phương thức có thể khai báo `throws InterruptedException`, ưu tiên **truyền tiếp** tín hiệu cho tầng sở hữu chính sách.
4. Nếu không thể ném checked exception, chọn chính sách xử lý rõ; trường hợp dừng task thường **restore flag + return/break**, và dọn dẹp trong `finally`.
5. Tránh `catch (Exception)` hoặc `catch (Throwable)` khiến yêu cầu hủy bị lẫn với lỗi nghiệp vụ.
6. Đừng restore flag rồi quay lại một blocking call trong loop không kiểm tra điều kiện thoát.
7. Khi task được hủy, xác định trạng thái công việc đã làm, transaction, checkpoint và những side effect cần đối chiếu.
8. Với `Future.cancel(true)`, `shutdownNow()` hay executor, không giả định tác vụ chắc chắn dừng nếu code không hợp tác.
9. Phân biệt **interrupted**, **cancelled**, **timed out** và **failed** trong kết quả, logging và monitoring.
10. Kiểm thử đường hủy ngay cả khi task đang chờ, đang xử lý, đang cleanup và khi dependency không phản ứng interrupt.

**Quy tắc ghi nhớ:** `InterruptedException` thường là tín hiệu điều phối có chủ đích. Bắt rồi bỏ qua có thể xóa tín hiệu và khiến tác vụ tiếp tục trái yêu cầu. Hãy **truyền tiếp**, hoặc **khôi phục cờ và kết thúc đúng đường**, trừ khi tầng hiện tại thực sự sở hữu và đã xử lý xong toàn bộ giao thức hủy.
