# Thời hạn chờ, hủy thao tác và tránh khóa chết trong callback

Trong CRaC, các callback `beforeCheckpoint` và `afterRestore` chạy ở những thời điểm nhạy cảm của vòng đời tiến trình. Callback `beforeCheckpoint` phải đưa ứng dụng và tài nguyên về trạng thái an toàn để JVM có thể tạo checkpoint. Callback `afterRestore` phải khôi phục hoặc xác nhận các tài nguyên cần thiết trước khi ứng dụng tiếp tục phục vụ công việc.

Nếu callback chờ vô thời hạn một thread, một lock, một truy vấn database hoặc một dịch vụ bên ngoài, toàn bộ thao tác checkpoint/restore có thể bị treo. Nếu callback giữ lock trong khi chờ một tác vụ cũng cần lock đó, ứng dụng có thể rơi vào deadlock. Vì vậy, callback cần có **thời hạn chờ hữu hạn, cơ chế hủy có kiểm soát và quy tắc sử dụng lock rõ ràng**.

## 1. Vì sao callback có thể làm checkpoint hoặc restore bị treo?

Callback CRaC thường phải phối hợp nhiều thành phần đang hoạt động đồng thời: request thread, worker thread, scheduler, connection pool, cache, file và dịch vụ bên ngoài. Các thành phần này có thể đang giữ lock hoặc chờ nhau.

Một số tình huống phổ biến:

- `beforeCheckpoint` chờ một request đang chạy kết thúc, nhưng request đó bị treo trong một lời gọi HTTP không có read timeout.
- Callback gọi `Future.get()` hoặc `Thread.join()` không giới hạn thời gian, khiến callback chờ mãi khi tác vụ nền không hoàn tất.
- Callback lấy một lock đang được worker giữ, trong khi worker lại chờ một tín hiệu chỉ callback mới có thể phát ra.
- Callback giữ `synchronized` hoặc `ReentrantLock` rồi chờ một task khác; task đó cần chính lock đang bị giữ để kết thúc.
- Hai Resource gọi callback theo cách phụ thuộc lẫn nhau và lấy nhiều lock theo thứ tự khác nhau, tạo thành chu trình chờ.
- `afterRestore` kết nối lại database hoặc message broker nhưng client không có connect/read timeout, khiến tiến trình không thể đạt readiness.

Callback không nên giả định mọi thread và dependency đều sẽ hoàn tất nhanh. Một thao tác có thể bình thường trong lúc ứng dụng chạy liên tục nhưng lại trở thành điểm chặn nghiêm trọng trong giai đoạn checkpoint hoặc restore.

## 2. Phân biệt timeout, cancellation và interruption

Ba khái niệm này liên quan nhưng không giống nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Timeout | Giới hạn thời gian chờ một điều kiện hoặc thao tác. Khi hết hạn, code nhận biết thao tác chưa hoàn tất. | Chờ request đang chạy tối đa 20 giây. |
| Cancellation | Yêu cầu tác vụ dừng hoặc không tiếp tục kết quả nữa. Tác vụ phải hỗ trợ cơ chế hủy để kết thúc an toàn. | Gọi `future.cancel(true)` sau khi hết thời gian chờ. |
| Interruption | Tín hiệu hợp tác qua interrupt flag của thread để báo thread nên dừng chờ hoặc hủy công việc. | `CountDownLatch.await()` ném `InterruptedException` khi thread bị interrupt. |

Timeout không tự động dừng tác vụ. Ví dụ `future.get(5, TimeUnit.SECONDS)` ném `TimeoutException` sau năm giây, nhưng task được submit vẫn có thể tiếp tục chạy. Muốn yêu cầu task dừng, ứng dụng phải chủ động hủy và task phải phản ứng với cancellation/interruption.

Tương tự, `future.cancel(true)` không cưỡng bức kết thúc một thread đang chạy. Tham số `true` yêu cầu interrupt thread thực thi nếu task đã bắt đầu; code bên trong task phải kiểm tra interrupt hoặc gọi các API có khả năng phản hồi interruption. Không nên xem interrupt là cơ chế kill thread an toàn.

## 3. Đặt deadline cho toàn bộ callback

Không nên cấp một timeout mới, đầy đủ cho từng bước mà quên tổng thời gian callback. Nếu callback có năm thao tác, mỗi thao tác chờ tối đa 30 giây, tổng thời gian có thể vượt quá hai phút.

Nên xác định một deadline tổng bằng `System.nanoTime()` rồi truyền thời gian còn lại cho từng thao tác:

```java
long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(30);

long remainingNanos = deadline - System.nanoTime();
if (remainingNanos <= 0) {
    throw new TimeoutException("Checkpoint preparation deadline exceeded");
}

// Dùng remainingNanos cho lần chờ tiếp theo.
```

`System.nanoTime()` phù hợp để đo thời gian trôi qua vì không phụ thuộc vào việc đồng hồ hệ thống được điều chỉnh. Không dùng `System.currentTimeMillis()` để tính deadline cho khoảng chờ ngắn cần chính xác.

Ví dụ ngân sách 30 giây:

| Công việc | Ngân sách minh họa |
| --- | ---: |
| Chặn nhận công việc mới và chờ request đang chạy hoàn tất | 18 giây |
| Flush dữ liệu hoặc hoàn tất giao dịch | 5 giây |
| Đóng hoặc giải phóng tài nguyên bên ngoài | 4 giây |
| Dự phòng xử lý và ghi log | 3 giây |

Đây chỉ là ví dụ. Timeout thực tế cần dựa trên SLA, thời gian checkpoint cho phép, đặc tính của dependency và số lượng công việc đang chạy. Các thao tác con phải dùng thời gian còn lại của deadline tổng, tránh cộng dồn nhiều timeout độc lập.

Nên đặt ngân sách riêng cho `beforeCheckpoint` và `afterRestore`. Restore có thể cần thời gian kết nối lại dịch vụ hoặc dựng lại pool; thời gian đó phải nằm trong giới hạn startup/readiness mà hệ thống triển khai cho phép.

## 4. Dừng nhận việc mới và drain công việc đang chạy

Trước khi đóng tài nguyên, ứng dụng cần ngăn request mới đi vào đường xử lý cần tài nguyên đó. Sau đó callback mới chờ số công việc đang chạy giảm về 0.

Một trình tự thường dùng:

1. Chuyển component sang trạng thái `PREPARING` hoặc `QUIESCING`.
2. Từ chối, tạm dừng hoặc chuyển hướng công việc mới theo chính sách của ứng dụng.
3. Chờ các request/task đang chạy hoàn tất trong một khoảng thời gian hữu hạn.
4. Nếu hết hạn, yêu cầu hủy các tác vụ còn lại theo chính sách đã định.
5. Chỉ khi trạng thái đã an toàn mới flush dữ liệu và đóng/tạm dừng tài nguyên.
6. Nếu không thể đạt trạng thái an toàn, báo lỗi để checkpoint bị từ chối thay vì tiếp tục với tài nguyên đang ở trạng thái không xác định.

Ví dụ callback dưới đây minh họa cấu trúc xử lý. Các hàm `stopAcceptingNewWork`, `awaitInFlight`, `flushAndCloseResources` và `rollbackPreparation` là logic riêng của ứng dụng; chúng phải thực hiện deadline và cancellation phù hợp với từng loại tài nguyên.

```java
import org.crac.Context;
import org.crac.Resource;

import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class ManagedResource implements Resource {

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(25);

        try {
            stopAcceptingNewWork();

            if (!awaitInFlight(remaining(deadline))) {
                throw new TimeoutException("In-flight work did not drain in time");
            }

            flushAndCloseResources(remaining(deadline));
        } catch (InterruptedException e) {
            // Giữ lại trạng thái interrupt để tầng gọi phía trên nhận biết.
            Thread.currentThread().interrupt();
            rollbackPreparation();
            throw e;
        } catch (Exception e) {
            rollbackPreparation();
            throw e;
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context) throws Exception {
        reconnectResources(Duration.ofSeconds(15));
        resumeAcceptingNewWork();
    }

    private void stopAcceptingNewWork() { /* application-specific */ }
    private boolean awaitInFlight(Duration timeout) throws InterruptedException {
        return true; // Replace with a bounded drain implementation.
    }
    private void flushAndCloseResources(Duration timeout) throws Exception { /* application-specific */ }
    private void rollbackPreparation() { /* application-specific and safe to repeat */ }
    private void reconnectResources(Duration timeout) throws Exception { /* application-specific */ }
    private void resumeAcceptingNewWork() { /* application-specific */ }

    private Duration remaining(long deadline) throws TimeoutException {
        long nanos = deadline - System.nanoTime();
        if (nanos <= 0) {
            throw new TimeoutException("Checkpoint preparation deadline exceeded");
        }
        return Duration.ofNanos(nanos);
    }
}
```

Trong mã thực tế, các thao tác con phải chia sẻ deadline tổng thay vì mỗi helper tự tiêu hết timeout riêng. Ví dụ trên cũng giả định `rollbackPreparation()` có thể đưa component về trạng thái hoạt động an toàn sau khi chuẩn bị thất bại. Nếu tài nguyên đã đóng một phần, rollback phải mở lại hoặc đánh dấu component không sẵn sàng; không được bật nhận request chỉ vì callback đã thoát.

## 5. Hủy tác vụ đang chạy đúng cách

### Với Future

Nếu callback chờ một task qua `Future`, hãy dùng phiên bản `get` có timeout và yêu cầu hủy khi hết hạn:

```java
try {
    future.get(5, TimeUnit.SECONDS);
} catch (TimeoutException e) {
    future.cancel(true);
    throw e;
}
```

Task cần hỗ trợ interruption:

```java
void processWork() throws InterruptedException {
    while (!Thread.currentThread().isInterrupted()) {
        processNextItem();
    }
}
```

Nếu task đang thực hiện một thao tác I/O không phản hồi interrupt, cần cấu hình timeout ở chính client hoặc đóng tài nguyên theo API để giải phóng thao tác đang chờ. Cancellation chỉ là yêu cầu; hãy theo dõi task thực sự kết thúc hay chưa.

### Với ExecutorService

`shutdown()` ngăn nhận task mới nhưng cho phép task đã submit tiếp tục chạy. `awaitTermination(timeout, unit)` chờ trong thời hạn. Nếu quá hạn, `shutdownNow()` yêu cầu interrupt các task đang chạy và trả về các task chưa bắt đầu; nó không bảo đảm mọi task đang chạy đã dừng.

```java
executor.shutdown();

if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
    List<Runnable> neverStarted = executor.shutdownNow();
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        throw new TimeoutException("Executor did not stop");
    }
}
```

Đoạn code trên chỉ minh họa cơ chế chờ/hủy. Trong ứng dụng CRaC, cần xác định executor có thể được tạo lại sau restore hay không. `ExecutorService` đã shutdown không thể chuyển lại trạng thái hoạt động; nếu cần tiếp tục dùng, hãy thiết kế việc tạo executor mới trong lifecycle phù hợp.

### Với I/O và database

Không nên dựa riêng vào interrupt để dừng mọi thao tác I/O. Hãy cấu hình timeout ở đúng tầng:

- HTTP client: connect timeout, response/read timeout và timeout tổng của request.
- JDBC: query timeout, network/socket timeout và cơ chế cancel statement phù hợp với driver.
- Message broker: timeout khi publish/ack, thời hạn xử lý message và cơ chế xác nhận lại khi retry.
- Socket tự quản lý: timeout đọc/ghi và đóng socket khi chính sách hủy yêu cầu.
- File hoặc native call: dùng API có giới hạn thời gian nếu có; nếu API không thể hủy an toàn, tránh gọi nó trong callback hoặc chuyển sang thiết kế có thể kiểm soát.

Timeout của một client chỉ giới hạn một loại chờ. Ví dụ connect timeout không nhất thiết giới hạn thời gian đọc response. Cần xác định chính xác API nào có thể block và cấu hình đúng timeout tương ứng.

## 6. Tránh deadlock khi dùng lock trong callback

Deadlock xuất hiện khi các thread giữ tài nguyên mà thread khác cần, tạo thành một chu trình chờ không thể tự giải quyết.

### Tình huống 1: Callback giữ lock rồi chờ worker

```text
Callback thread                    Worker thread
---------------                    -------------
lock.acquire()
wait for worker  ----------------> needs same lock
                                   cannot continue
callback waits forever
```

Callback giữ lock trong khi chờ worker. Worker cần lock để hoàn tất, vì vậy cả hai không thể tiến lên.

**Cách xử lý:** không giữ application lock trong lúc chờ Future, latch, thread hoặc I/O. Chỉ lấy lock trong đoạn cập nhật trạng thái ngắn, nhả lock rồi mới chờ tác vụ khác.

### Tình huống 2: Hai callback lấy lock ngược thứ tự

```text
Callback A                         Callback B
----------                         ----------
holds lock A                       holds lock B
waits for lock B                   waits for lock A
```

Nếu hai callback hoặc hai component lấy nhiều lock theo thứ tự khác nhau, chúng có thể tạo deadlock. Nếu bắt buộc dùng nhiều lock, xác định một thứ tự toàn cục và tuân thủ ở mọi đường code. Tốt hơn là gom thay đổi trạng thái vào một coordinator để giảm số lock cần phối hợp.

### Tình huống 3: Chờ task trên chính executor đang chạy callback

Nếu callback chạy trên một executor có số worker hữu hạn rồi submit task mới vào cùng executor và chờ task đó, pool có thể không còn worker rảnh. Task mới không được chạy, còn callback chờ kết quả của task đó.

**Cách xử lý:** không chờ đồng bộ task được submit vào executor có thể đã bão hòa hoặc đang chạy callback. Thực hiện công việc cần thiết trực tiếp trong callback, dùng executor riêng có capacity được kiểm soát, hoặc thiết kế bước drain từ trước khi yêu cầu checkpoint.

## 7. Quy tắc sử dụng lock an toàn

- Không dùng `synchronized` hoặc `lock()` vô thời hạn cho tài nguyên có thể đang bị thread khác giữ lâu.
- Với `ReentrantLock`, ưu tiên `tryLock(timeout, unit)` khi cần chờ lock; nếu không lấy được lock trong thời hạn, báo lỗi và xử lý rollback.
- Không giữ lock trong khi gọi network, database, `Future.get`, `Thread.join`, `CountDownLatch.await` hoặc `ExecutorService.awaitTermination`.
- Không gọi một method nghiệp vụ từ callback nếu method đó có thể lấy lock theo thứ tự khác với các thread bình thường.
- Dùng một thứ tự lock thống nhất nếu phải lấy nhiều lock.
- Giữ critical section ngắn, chỉ bảo vệ việc chuyển trạng thái hoặc cập nhật cấu trúc dữ liệu.
- Không chờ một thread mà thread đó lại cần callback hoàn tất mới có thể tiếp tục.
- Ghi nhận thời gian chờ lock và thread đang giữ lock khi điều tra sự cố.

Ví dụ lấy lock có timeout:

```java
if (!lock.tryLock(2, TimeUnit.SECONDS)) {
    throw new TimeoutException("Could not acquire lifecycle lock");
}

try {
    updateLifecycleState();
} finally {
    lock.unlock();
}
```

Đoạn code chỉ giữ lock trong thời gian cập nhật state. Nếu cần chờ worker drain, thực hiện việc đó sau khi đã nhả lock.

## 8. Không dựa vào thứ tự callback để giải quyết phụ thuộc

Một ứng dụng có thể đăng ký nhiều `Resource`: database pool, message consumer, scheduler, cache và HTTP client. Không nên tạo phụ thuộc ngầm kiểu Resource A giả định Resource B đã hoàn tất callback chỉ vì B được đăng ký trước hoặc sau.

Nếu các tài nguyên cần một thứ tự chuẩn bị cụ thể, hãy thể hiện thứ tự đó trong một lifecycle coordinator duy nhất hoặc một cơ chế orchestration do ứng dụng sở hữu. Coordinator có thể dừng nhận việc, drain worker, flush dữ liệu rồi đóng các resource theo thứ tự đã xác định.

Tránh để callback của A gọi trực tiếp callback của B. Điều này có thể dẫn đến callback chạy hai lần, phụ thuộc thứ tự khó kiểm soát hoặc deadlock do cùng một resource bị điều khiển từ nhiều nơi. Mỗi resource nên có một chủ sở hữu lifecycle rõ ràng.

## 9. Xử lý lỗi và rollback khi callback không hoàn tất

Nếu một callback hết thời gian chờ hoặc bị interruption, không nên bỏ qua lỗi rồi để checkpoint tiếp tục trong khi resource chỉ mới được chuẩn bị một phần. Hãy báo lỗi để thao tác checkpoint bị từ chối theo semantics của runtime.

Có một điểm quan trọng: `afterRestore` là callback cho giai đoạn restore thành công. Không nên dựa vào `afterRestore` để hoàn tác những gì `beforeCheckpoint` đã làm nếu checkpoint bị abort. Nếu callback đóng một kết nối rồi timeout ở bước tiếp theo, chính logic chuẩn bị hoặc một coordinator cần có cách đưa ứng dụng về trạng thái an toàn.

Khi có nhiều Resource, cũng không nên giả định runtime sẽ tự gọi một callback rollback chung cho mọi Resource đã chuẩn bị trước đó nếu một Resource khác thất bại. Hãy thiết kế quy trình chuẩn bị có thể rollback rõ ràng, hoặc gom các thao tác liên quan vào một coordinator có thể theo dõi chính xác phần nào đã hoàn tất.

Một mô hình trạng thái hữu ích:

```text
RUNNING
   |
   v
PREPARING
   |
   +---- lỗi/timeout/interruption ----> ROLLING_BACK
   |                                      |
   |                                      v
   |                                  RUNNING hoặc FAILED
   |
   v
QUIESCED
   |
   v
CHECKPOINTING
   |
   v
RESTORING
   |
   v
RECONNECTING
   |
   v
READY
```

Nếu rollback không thể khôi phục tài nguyên, chuyển component sang `FAILED` hoặc `NOT_READY`, giữ traffic ở ngoài và phát tín hiệu vận hành. Không đặt lại `RUNNING` chỉ để tránh callback báo lỗi.

## 10. Xử lý interruption đúng cách

Các API chờ như `Future.get`, `CountDownLatch.await`, `Thread.join` và `ReentrantLock.lockInterruptibly` có thể ném `InterruptedException`. Khi bắt exception này, callback nên:

1. Dừng thao tác đang chờ theo cách an toàn.
2. Thực hiện rollback cần thiết cho phần chuẩn bị đã hoàn tất.
3. Khôi phục interrupt flag bằng `Thread.currentThread().interrupt()` nếu đã bắt `InterruptedException` và không chuyển interruption thành một giao thức khác.
4. Ném exception lên tầng CRaC để checkpoint/restore biết callback không hoàn tất.

Không nên viết:

```java
try {
    latch.await();
} catch (InterruptedException ignored) {
    // Tiếp tục như thể đã hoàn tất.
}
```

Đoạn code này nuốt tín hiệu hủy và có thể khiến callback tiếp tục trong trạng thái chưa an toàn.

Một cách xử lý đúng hơn:

```java
try {
    if (!latch.await(10, TimeUnit.SECONDS)) {
        throw new TimeoutException("Workers did not stop");
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw e;
}
```

Nếu callback cần rollback trước khi ném exception, thực hiện rollback trong `catch` rồi mới khôi phục interrupt flag và ném lại. Bản thân rollback cũng phải có giới hạn thời gian hoặc cơ chế thoát khi dependency không phản hồi.

## 11. Timeout ở tầng orchestration không thay thế timeout trong callback

Script hoặc công cụ triển khai có thể đặt timeout khi chờ lệnh checkpoint, nhưng timeout của tiến trình gọi bên ngoài không bảo đảm thao tác bên trong JVM đã bị hủy an toàn. Ví dụ, dừng tiến trình `jcmd` đang chờ không đồng nghĩa JVM chắc chắn đã hủy checkpoint.

Vì vậy, cần phân biệt:

- **Callback deadline:** giới hạn thời gian mà code callback cho phép một bước chuẩn bị hoặc phục hồi chạy.
- **JVM/CRaC operation timeout:** giới hạn thời gian của thao tác checkpoint/restore theo runtime và cách triển khai.
- **Orchestration timeout:** giới hạn thời gian script, job hoặc deployment controller chờ kết quả.

Orchestration timeout hữu ích để phát hiện thao tác vượt quá cửa sổ vận hành, nhưng sau khi hết hạn cần kiểm tra trạng thái JVM, log CRaC/CRIU và thư mục checkpoint trước khi retry. Không gửi một lệnh checkpoint thứ hai hoặc xóa ảnh đang được ghi khi chưa biết thao tác đầu tiên đã kết thúc hay chưa.

## 12. Quan sát và kiểm thử callback có giới hạn thời gian

Mỗi Resource nên ghi nhận các thông tin sau:

- Tên/định danh Resource và checkpoint attempt id.
- Thời điểm callback bắt đầu và kết thúc, tổng duration.
- Số request hoặc task đang chạy khi bắt đầu drain.
- Thời gian chờ lock và loại lock liên quan nếu có.
- Dependency đang được gọi và timeout được cấu hình.
- Số task bị cancel, số task vẫn chạy sau cancellation và nguyên nhân timeout.
- Kết quả rollback hoặc reconnect.

Không ghi credential, token hoặc dữ liệu nhạy cảm vào log callback. Log cần đủ để xác định bước bị treo mà không làm lộ dữ liệu trong tài nguyên.

Các kịch bản kiểm thử nên bao gồm:

1. Worker hoàn tất bình thường trước deadline.
2. Worker chạy quá deadline và callback yêu cầu cancellation.
3. Worker bỏ qua interruption để xác nhận hệ thống phát hiện task vẫn chưa dừng.
4. Lock bị thread khác giữ lâu hơn timeout.
5. Hai component có nguy cơ lấy lock ngược thứ tự.
6. Dependency HTTP/database không phản hồi.
7. Callback bị interrupt trong lúc chờ.
8. Một bước chuẩn bị thành công nhưng bước tiếp theo thất bại, cần rollback.
9. Restore thành công nhưng reconnect dependency vượt quá deadline.
10. Ứng dụng không nhận traffic cho đến khi mọi tài nguyên quan trọng sẵn sàng.

Thử nghiệm cần chạy với JDK/CRaC và môi trường triển khai thực tế. Unit test cho helper timeout và state machine hữu ích, nhưng không thay thế kiểm thử checkpoint/restore tích hợp.

## 13. Checklist thiết kế callback

- [ ] Mỗi callback có deadline tổng rõ ràng.
- [ ] Mọi thao tác blocking đều có timeout hoặc cơ chế thoát được xác định.
- [ ] Các timeout con dùng thời gian còn lại của deadline tổng.
- [ ] Ứng dụng dừng nhận việc mới trước khi drain công việc đang chạy.
- [ ] Tác vụ có cơ chế cancellation/interruption hợp tác.
- [ ] I/O, database và HTTP client có timeout đúng tầng.
- [ ] Không giữ lock trong khi chờ worker, Future hoặc network.
- [ ] Không chờ task trên executor có thể đã bão hòa hoặc đang chạy callback.
- [ ] Thứ tự lock thống nhất và không có chu trình chờ giữa Resource.
- [ ] Timeout hoặc interruption làm checkpoint bị từ chối nếu resource chưa an toàn.
- [ ] Có rollback rõ ràng; không dựa vào `afterRestore` để hoàn tác checkpoint bị abort.
- [ ] Sau restore, chỉ mở nhận traffic khi resource đã reconnect và readiness đạt.
- [ ] Log duration, timeout, cancellation và lỗi theo từng Resource.
- [ ] Đã thử các trường hợp timeout, deadlock tiềm ẩn, interruption và dependency chậm.

## 14. Kết luận

Callback CRaC phải kết thúc trong một khoảng thời gian có kiểm soát và để lại trạng thái tài nguyên xác định. Dừng nhận việc mới, drain công việc đang chạy, dùng deadline tổng, đặt timeout ở tầng I/O phù hợp và hủy task theo cơ chế hợp tác giúp tránh callback chờ vô hạn. Không giữ lock trong lúc chờ tác vụ khác, thống nhất thứ tự lock và quản lý rollback khi checkpoint bị abort để tránh deadlock hoặc để ứng dụng ở trạng thái dở dang.

Sau restore, kết nối lại dependency trong thời hạn cho phép và chỉ đưa ứng dụng vào trạng thái sẵn sàng khi các tài nguyên quan trọng đã hoạt động. Khi timeout, cancellation và state transition được thiết kế rõ ràng, callback trở thành một phần có thể quan sát và kiểm soát của chu kỳ checkpoint–restore.
