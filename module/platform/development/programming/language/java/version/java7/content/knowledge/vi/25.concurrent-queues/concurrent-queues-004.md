# Hàng đợi đồng thời trong Java: tryTransfer và biến thể có thời hạn chờ

## 1. Tại sao cần tryTransfer?

Giả sử một producer nhận các thông báo trạng thái tạm thời. Khi đã có consumer **đang chờ** lấy một thông báo, producer muốn đưa ngay thông báo đó cho consumer. Nhưng nếu **chưa có consumer nào chờ**, producer muốn biết điều đó để quyết định bỏ qua, retry hoặc chuyển sang hàng đợi lưu trữ — chứ không muốn âm thầm xếp một lượng thông báo không giới hạn.

Trong Java, giao diện **`java.util.concurrent.TransferQueue<E>`** (có từ Java 7, vẫn hiện hành) cung cấp chính xác lựa chọn:

- **`boolean tryTransfer(E e)`**: thử **bàn giao ngay** cho một consumer đã **đang đợi** bằng `take()` hoặc `poll(timeout, unit)`. Nếu không có consumer chờ, trả **`false`** và **không enqueuing phần tử**.
- **`boolean tryTransfer(E e, long timeout, TimeUnit unit)`**: thử bàn giao; nếu chưa có consumer đang chờ, có thể **đợi tối đa khoảng thời gian chỉ định** cho consumer nhận phần tử. Trả **`true`** khi consumer đã nhận, trả **`false`** nếu hết hạn mà không bàn giao được; **phần tử không được để lại trong queue** ở nhánh false.
- **`void transfer(E e)`**: producer sẵn sàng **đợi không giới hạn do API tự áp** cho tới khi một consumer nhận phần tử, trừ khi bị ngắt hoặc có sự cố khác. Nếu chưa có consumer, phần tử có thể hiện diện như một transfer đang chờ.

Cùng một `TransferQueue` còn triển khai `BlockingQueue` nên có `offer`, `put`, `take` và `poll`. Hai nhóm thao tác có **hợp đồng khác nhau**: **đưa vào queue** khác với **bàn giao cho một consumer**.

**Thông điệp quan trọng nhất:** `tryTransfer(e)==false` **không phải** “đã xếp hàng nhưng consumer chưa xử lý”. Nó có nghĩa **bàn giao không thành công và phần tử không được giữ lại bởi thao tác đó**. Nếu ứng dụng bỏ qua giá trị false, dữ liệu có thể bị mất ngay tại producer.

Bài học thuộc mục **Hàng đợi đồng thời** của Java 7. Chỉ sử dụng API vẫn áp dụng trong Java hiện đại; ví dụ hoàn chỉnh biên dịch và chạy trên **JDK 17**.

### Sau bài này, bạn có thể

1. Phân biệt `tryTransfer(e)` với `tryTransfer(e, timeout, unit)`.
2. Hiểu consumer thế nào được coi là **đang đợi**.
3. So sánh `tryTransfer`, `transfer`, `offer` và `put` bằng đúng điều kiện hoàn tất.
4. Xây chính sách **drop/retry/fallback/timeout** khi không bàn giao được.
5. Xử lý `InterruptedException`, `NullPointerException` và kết thúc ứng dụng.
6. Tránh dùng `hasWaitingConsumer()`/`getWaitingConsumerCount()` như quyết định giao thức bảo đảm tính đúng đắn.
7. Hiểu vì sao `LinkedTransferQueue` là **unbounded** và phải có backpressure bên ngoài nếu cần.
8. Viết test đồng thời có xác nhận trạng thái thay vì chỉ dùng `Thread.sleep` đoán thứ tự.
9. Không nhầm consumer **đã nhận** với nghiệp vụ **đã xử lý thành công**.

## 2. Các lớp và interface liên quan

`TransferQueue<E>` mở rộng `BlockingQueue<E>`:

```text
java.util.Queue<E>
       |
       v
java.util.concurrent.BlockingQueue<E>
       |
       v
java.util.concurrent.TransferQueue<E>
       |
       v
java.util.concurrent.LinkedTransferQueue<E>
```

Đây là sơ đồ quan hệ API để học, không phải source code.

Trong Java chuẩn, **`LinkedTransferQueue<E>`** là implementation phổ biến của `TransferQueue<E>`. Nó sử dụng cấu trúc liên kết thread-safe, không giới hạn dung lượng bằng một con số capacity được truyền vào constructor, và có hỗ trợ thao tác bàn giao trực tiếp cho consumer. Nó không phải một queue persistent trên ổ đĩa.

```java
import java.util.concurrent.LinkedTransferQueue;
import java.util.concurrent.TransferQueue;

TransferQueue<String> messages = new LinkedTransferQueue<>();
```

Đoạn trên có thể đặt trong một phương thức hoặc class. Khai báo theo interface giúp code phụ thuộc hợp đồng `TransferQueue`, còn implementation quyết định các thuộc tính như dung lượng và tổ chức node.

### 2.1. TransferQueue khác BlockingQueue thông thường

`BlockingQueue` quan tâm tới việc một phần tử có được **thêm vào queue** hoặc **lấy ra**. `TransferQueue` bổ sung cơ chế cho producer biết rằng phần tử đã được **nhận bởi một consumer**.

- Với `queue.offer(e)`, thành công có nghĩa thao tác **chèn/trao phần tử theo queue contract** đã hoàn tất; consumer **không bắt buộc** đã nhận.
- Với `queue.tryTransfer(e)`, trả `true` nghĩa có consumer đang đợi và **đã nhận** phần tử theo giao thức transfer.
- Với `queue.transfer(e)`, producer có thể **phải đợi** consumer nhận mới trả về.

**“Đã nhận” chỉ là handoff tại queue**, không phải database transaction committed, file đã được ghi bền vững, HTTP request đã thành công hay business logic đã xử lý xong. Muốn xác nhận xử lý, ứng dụng cần một bước **acknowledgement** riêng.

### 2.2. LinkedTransferQueue không có giới hạn capacity hữu hạn

`LinkedTransferQueue` không bị chặn bởi capacity nội bộ. Phương thức `remainingCapacity()` trả `Integer.MAX_VALUE` theo API, nhưng đó **không phải** báo cáo RAM thực tế còn bao nhiêu và không có nghĩa có thể lưu vô hạn thông điệp.

Với implementation này:

- `offer(e)` chèn phần tử mà **không phải đợi có consumer nhận**.
- `put(e)` cũng đưa phần tử vào queue; không tự biến thành `transfer(e)`.
- `offer(e, timeout, unit)` về mặt chèn phần tử cũng không cần đợi chỗ trống của một queue bị giới hạn, nên timeout **không đóng vai trò deadline để một consumer nhận**.
- `tryTransfer` vẫn có thể trả false ngay cả khi queue hoàn toàn còn chỗ — vì điều kiện của nó là **consumer đang đợi**, không phải **capacity còn trống**.

Đối với các implementation `TransferQueue` khác có capacity hữu hạn, giao thức chờ có thể còn chịu ràng buộc dung lượng. Không áp đặt đặc tính unbounded của `LinkedTransferQueue` cho mọi loại `TransferQueue` do bên thứ ba viết.

## 3. tryTransfer(E e): bàn giao ngay hoặc trả false

Chữ ký:

```java
boolean tryTransfer(E e);
```

Trình tự tư duy:

```text
Producer gọi tryTransfer(e)
             |
             v
Có consumer đã đang chờ take()/poll(timeout)?
             |
       +-----+------+
       |            |
      Có          Không
       |            |
       v            v
Bàn giao e       Không enqueuing e
       |            |
       v            v
return true      return false
```

Consumer “đang chờ” là người đã bắt đầu **một lời gọi nhận có thể block** do chưa có phần tử tương ứng. Ví dụ:

- `consumer.take()` đang đợi vì queue không có dữ liệu phù hợp.
- `consumer.poll(5, TimeUnit.SECONDS)` đang đợi và chưa timeout.

Một consumer **đang bận xử lý** một thông điệp cũ không được xem là “đang đợi nhận phần tử mới”. Chỉ có thread dự kiến sẽ gọi `take()` sau vài millisecond cũng **không** đủ.

### 3.1. Không có consumer chờ: false không xếp hàng

```java
TransferQueue<String> queue = new LinkedTransferQueue<>();

boolean handedOff = queue.tryTransfer("event-1");
System.out.println(handedOff);
System.out.println(queue.isEmpty());
```

Trong đoạn tuần tự này, không có thread consumer nào được tạo. Output:

```text
false
true
```

Cả hai dòng này **phụ thuộc tiền đề không có consumer hoặc thao tác nào khác can thiệp**. Trong thực tế có concurrency, trạng thái queue có thể đổi ngay khi gọi `isEmpty()`; không sử dụng một snapshot đơn lẻ làm khóa logic.

**Lỗi nghiêm trọng:**

```java
queue.tryTransfer(message);
markAsDelivered(message);  // Sai nếu tryTransfer trả false.
```

Nếu `tryTransfer` trả false, message **không được bàn giao và không nằm lại trong queue**. Đánh dấu “đã gửi thành công” sẽ làm mất trạng thái nghiệp vụ.

Cách đúng phải **kiểm tra boolean** và chọn policy:

```java
if (queue.tryTransfer(message)) {
    markAsHandedOff(message);
} else {
    handleNoWaitingConsumer(message);
}
```

Đây là mã minh họa với `message`, `markAsHandedOff`, `handleNoWaitingConsumer` do ứng dụng định nghĩa. Không tự nhận kết quả false là một ngoại lệ Java; đó là một kết quả **bình thường có ý nghĩa**.

### 3.2. Có consumer chờ: true là bàn giao trực tiếp

Hai thread có thể phối hợp như sau:

```text
Consumer thread                 Producer thread
---------------                 ---------------
queue.take() -> đang đợi
                                queue.tryTransfer("A")
nhận "A"                        nhận true
tiếp tục xử lý                  tiếp tục chạy
```

Lệnh producer **không phải đợi lâu cho consumer xuất hiện**; nó chỉ thành công nếu consumer đã ở vị trí chờ phù hợp ngay thời điểm lời gọi khớp được.

**Kết quả true không bảo đảm consumer đã xử lý xong "A".** Consumer có thể lấy xong rồi mới bắt đầu xử lý, hoặc lỗi khi xử lý sau đó. Producer nên ghi trạng thái **HANDED_OFF** chứ không phải **PROCESSED** nếu không có ack cấp ứng dụng.

### 3.3. Không chuyển thành công bằng cách kiểm tra trước

Một anti-pattern:

```java
if (queue.hasWaitingConsumer()) {
    queue.tryTransfer(message);
}
```

Có hai vấn đề:

1. Giá trị `hasWaitingConsumer()` là **trạng thái tức thời**, consumer có thể timeout/được thread khác phục vụ trước khi bạn gọi `tryTransfer`.
2. Lời gọi `tryTransfer` vẫn trả boolean nhưng code lại **bỏ qua**, gây mất dữ liệu khi thất bại.

**Cách đúng: gọi `tryTransfer` trực tiếp và xử lý kết quả.** Không dùng `hasWaitingConsumer` như precondition bảo đảm.

### 3.4. Khi nào sử dụng immediate tryTransfer?

Phù hợp khi nghiệp vụ cho phép quyết định nhanh:

- Gửi “cập nhật thoáng qua” tới worker **nếu hiện có worker đang chờ**.
- Phát tín hiệu tối ưu hóa mà có thể bỏ qua khi receiver chưa sẵn.
- Áp dụng policy **fail-fast** cho một đường giao nhận trực tiếp.
- Thử handoff trước khi chọn fallback rõ ràng vào queue, pool khác hoặc log.

Không phù hợp nếu ứng dụng **bắt buộc nhận mọi message và không có fallback**; nếu vậy gọi `tryTransfer` rồi bỏ false là sai thiết kế.

## 4. tryTransfer(E e, long timeout, TimeUnit unit): chờ có giới hạn

Chữ ký:

```java
boolean tryTransfer(E e, long timeout, TimeUnit unit)
        throws InterruptedException;
```

Đây là biến thể có thời hạn chờ. Nếu ngay lúc gọi đã có consumer đang đợi, nó có thể bàn giao ngay. Nếu chưa, producer có thể **chờ tới deadline** để một consumer nhận.

| Tình huống | Kết quả theo hợp đồng |
| --- | --- |
| Consumer chờ sẵn và nhận được e | `true` |
| Consumer tới trước khi hết hạn và nhận e | `true` |
| Không ai nhận trước khi thời gian hết | `false`, e **không nằm lại trong queue** |
| Thread producer bị interrupt trong lúc chờ | `InterruptedException`, e **không nằm lại trong queue** |
| `e == null` | `NullPointerException` |
| `unit == null` | `NullPointerException` đối với đối số TimeUnit cần để xác định deadline |
| Phần tử vi phạm hợp đồng implementation | Có thể có `ClassCastException` hoặc `IllegalArgumentException` theo interface |

### 4.1. Ví dụ producer chờ tối đa 200 ms

```java
boolean delivered = queue.tryTransfer(
        message, 200, TimeUnit.MILLISECONDS);

if (!delivered) {
    // Không có consumer nhận trước deadline.
    // Tùy chính sách: bỏ qua, retry hoặc chuyển sang persistence.
}
```

Đây là đoạn minh họa trong phương thức xử lý `InterruptedException`, với `queue`, `message` đã định nghĩa. Đây không phải deadline của **toàn bộ xử lý business logic**; chỉ là thời hạn để giao message cho một consumer của queue.

### 4.2. Hết thời hạn không để lại một phần tử “chờ muộn”

Giả sử không có consumer trong 100 ms:

```java
TransferQueue<String> queue = new LinkedTransferQueue<>();

boolean done = queue.tryTransfer(
        "report", 100, TimeUnit.MILLISECONDS);

System.out.println(done);
System.out.println(queue.isEmpty());
```

Nếu không có actor khác, output:

```text
false
true
```

Điểm mấu chốt: **timeout không tự chuyển thao tác thành `offer`**. Nếu consumer bắt đầu `take` sau deadline, nó không tự nhận được phần tử "report" từ lời gọi đã hết hạn.

### 4.3. Vì sao thời hạn chờ không đồng nghĩa thời gian chạy chính xác?

`timeout=100 ms` là khoảng chờ tối đa dự kiến theo contract của việc chuyển phần tử, **không** phải cam kết wall-clock chính xác một phần nghìn giây. Scheduler, preemption, JVM/OS và overhead có thể ảnh hưởng thời điểm thread thực sự quay về.

Để đo SLA, ghi `System.nanoTime()` và đo **end-to-end** thực tế, không tính bằng cách suy ra “đã đợi đúng timeout” từ tham số.

### 4.4. Khi deadline bằng 0 hoặc âm

Đừng dựa vào giá trị âm để mô tả một chờ có ý nghĩa nghiệp vụ. Một cấu hình deadline nên validate rõ `timeout >= 0`, dùng `TimeUnit` tương ứng và coi `0` là yêu cầu **không chờ** theo mục tiêu API nếu phù hợp.

Với đường nóng (hot path) chỉ muốn thử ngay, `tryTransfer(e)` thể hiện mục tiêu rõ ràng hơn một overload truyền timeout bằng 0.

### 4.5. Không tự retry vô hạn

Ví dụ nguy hiểm:

```java
while (!queue.tryTransfer(message, 1, TimeUnit.SECONDS)) {
    // Không có deadline tổng, không có chính sách shutdown.
}
```

Đây là **đoạn minh họa anti-pattern**, không nên dùng nguyên trạng. Nó có thể chờ vô hạn qua nhiều lần timeout, giữ message và chiếm một thread producer mãi.

Thay vào đó:

- Định nghĩa **deadline tổng** cho request.
- Kiểm tra trạng thái shutdown/cancel.
- Giới hạn số retry nếu nghiệp vụ chấp nhận.
- Giữ rõ ownership của message qua các lần thử.
- Có cơ chế fallback hoặc trả lỗi cho upstream.

### 4.6. Nếu producer bị interrupt trong lúc chờ

`tryTransfer(e,timeout,unit)` có thể ném `InterruptedException`. Theo contract, trường hợp đó **phần tử không được để lại trong queue**.

Một mẫu xử lý trong phương thức có thể propagate:

```java
try {
    boolean handedOff = queue.tryTransfer(
            event, 500, TimeUnit.MILLISECONDS);
    if (!handedOff) {
        recordDeliveryTimeout(event);
    }
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    recordCancelled(event);
    return;
}
```

Đây là đoạn minh họa với `event` và các hàm ghi nhận trạng thái do ứng dụng định nghĩa. Nếu phương thức được thiết kế `throws InterruptedException`, có thể **propagate** thay vì catch. Nếu catch mà tiếp tục ở cùng tầng, khôi phục interrupt flag thường phù hợp; không nuốt rồi retry vô hạn.

**Đừng đồng nhất timeout với interruption:** timeout trả boolean false, interruption ném checked exception. Chúng cần telemetry và chính sách khôi phục khác nhau.

## 5. Phân biệt bốn cách producer gửi phần tử

| Producer API | Có đợi consumer nhận? | Khi không có consumer đang chờ | Điều kiện trả thành công |
| --- | --- | --- | --- |
| `tryTransfer(e)` | **Không** | `false`, **không enqueue** | Consumer đang đợi đã nhận |
| `tryTransfer(e,t,u)` | **Có**, tối đa khoảng `t` | Đợi; hết hạn trả `false`, **không để lại e** | Consumer đã nhận trước deadline |
| `transfer(e)` | **Có**, đến khi được nhận hoặc interrupted | Có thể giữ transfer pending và chặn caller | Consumer đã nhận |
| `offer(e)` trên `LinkedTransferQueue` | **Không đợi nhận** | Đưa e vào queue để consumer lấy sau | Chèn phần tử theo queue contract |
| `put(e)` trên `LinkedTransferQueue` | **Không đợi nhận** | Đưa e vào queue để consumer lấy sau | Chèn thành công (khác TransferQueue tổng quát có capacity) |

Một ý quan trọng: `LinkedTransferQueue.offer` khi có consumer đang đợi có thể **bàn giao ngay**; điều đó không làm `offer` trở thành API bảo đảm **đợi cho consumer nhận**. Hợp đồng `offer` cho phép producer hoàn tất mà chưa có ai nhận.

### 5.1. Khi không được phép mất thông điệp

Nếu nghiệp vụ yêu cầu phải xử lý mọi message, lựa chọn:

- `offer(e)` và xây pipeline consumer, nếu có cơ chế giới hạn tải.
- `tryTransfer(e,t,u)` với **retry/fallback có hạn** và durability hợp lý.
- `transfer(e)` nếu chấp nhận producer chờ đến khi có consumer và có cách dừng an toàn.
- Persistence/queue broker nếu cần phục hồi qua crash hoặc machine restart.

**Không có cách nào ở trên tự bảo đảm exactly-once processing hoặc durability qua process crash**. `TransferQueue` là cấu trúc dữ liệu trong bộ nhớ của JVM.

### 5.2. Khi chủ động chấp nhận bỏ qua sự kiện

Nếu event là cập nhật trạng thái nhất thời, producer có thể:

```java
if (!queue.tryTransfer(event)) {
    droppedEvents.increment();
}
```

Đây là đoạn minh họa; `droppedEvents` có thể là `LongAdder` và `event` có kiểu tương ứng. Hãy đặt tên metric là **handoff skipped/dropped**, không gọi việc false là lỗi JVM hay “message đã nằm trong queue”.

### 5.3. Khi muốn hàng đợi thông thường, đừng dùng timed tryTransfer

Một anti-pattern:

```java
queue.tryTransfer(item, 1, TimeUnit.SECONDS);
// Không có consumer -> false -> item biến mất khỏi đường giao nhận.
```

Nếu mục tiêu là “enqueue dù consumer chưa có”, dùng `offer`/`put` theo contract của implementation, không phải timed tryTransfer.

### 5.4. So với SynchronousQueue

`SynchronousQueue<E>` là một hàng đợi **capacity bằng 0**, nơi một phép `put` có thể phải gặp một phép `take`; interface `TransferQueue` giải thích rằng với capacity 0, `put` và `transfer` có ngữ nghĩa tương tự về bàn giao.

Nhưng **`SynchronousQueue` không được dùng như một implementation của `TransferQueue`** trong Java chuẩn; không ép kiểu `(TransferQueue) new SynchronousQueue<>()`. Nếu chỉ cần rendezvous và không bao giờ lưu phần tử, `SynchronousQueue` có thể là lựa chọn đơn giản hơn, tùy yêu cầu.

## 6. Consumer nào thực sự được tính là “đang đợi”?

Hai phương thức consumer:

```java
E value = queue.take();
```

```java
E value = queue.poll(5, TimeUnit.SECONDS);
```

đều có thể **đợi** phần tử. Trong trạng thái chờ, chúng có thể được khớp với `tryTransfer`.

Ngược lại, `poll()` **không có timeout** là phép kiểm tra không chờ, trả `null` ngay khi không có phần tử sẵn. Việc một thread gọi `poll()` mỗi 100 ms không đồng nghĩa tại mọi thời điểm luôn có consumer đang đợi.

### 6.1. Race rất phổ biến giữa producer và consumer

```text
t0: Consumer chưa gọi take()
t1: Producer tryTransfer("A") -> false, không enqueue
t2: Consumer bắt đầu take() -> chờ

Không có "A" nào ở trong queue.
```

**Đây là hành vi đúng của API.** Nếu ứng dụng cần truyền "A" ngay cả khi consumer đến muộn, phải dùng một thao tác lưu queue hoặc thiết kế khác.

### 6.2. Nhiều consumer và nhiều producer

Nếu có một consumer đang chờ và hai producer đồng thời gọi `tryTransfer`:

- Một producer có thể bàn giao thành công.
- Producer kia có thể trả `false` nếu không còn consumer chờ.
- Không thể suy từ việc `hasWaitingConsumer` từng trả true rằng cả hai producer sẽ thành công.
- Thứ tự winner phụ thuộc scheduling và trạng thái cấu trúc dữ liệu.

Ứng dụng cần kiểm tra **kết quả của từng lần gọi**, không gộp thành một quyết định trước rồi bỏ qua boolean.

### 6.3. FIFO không có nghĩa tổng thứ tự tuyệt đối cho mọi producer

`LinkedTransferQueue` bảo toàn thứ tự FIFO **đối với các phần tử từ một producer nhất định**, nhưng trong concurrency đa producer, thời điểm operation chồng lấp khiến thứ tự quan sát giữa các producer không nhất thiết trùng với log timestamp hay thứ tự gọi dự tính.

Nếu nghiệp vụ cần tổng thứ tự toàn cục, phải thiết kế sequence numbers/serialization phù hợp. Không dựa vào FIFO của queue để cung cấp một global ordered log bền vững.

## 7. hasWaitingConsumer() và getWaitingConsumerCount() dùng để làm gì?

`TransferQueue` có:

```java
boolean hasWaitingConsumer();
int getWaitingConsumerCount();
```

- `hasWaitingConsumer()` cho biết tại một thời điểm quan sát có consumer đợi `take` hoặc timed `poll` hay không.
- `getWaitingConsumerCount()` cho **ước tính** số consumer đang đợi. API cảnh báo kết quả có thể không chính xác ngay khi các consumer đã nhận được item hoặc hết hạn; implementation có thể phải đi qua nhiều node, nên chậm hơn `hasWaitingConsumer`.

### 7.1. Cách dùng hợp lý

- Dashboard giám sát backlog, số consumer idle.
- Heuristic để điều chỉnh số producer/consumer theo tải.
- Hỗ trợ diagnostic trong integration test có giới hạn thời gian.
- Quan sát tạm thời, **không làm precondition duy nhất của hành động nghiệp vụ**.

### 7.2. Cách dùng nguy hiểm

```java
if (queue.hasWaitingConsumer()) {
    // Không có lock nào bảo đảm consumer vẫn còn đợi ngay sau check.
    queue.tryTransfer(data); // Vẫn phải kiểm tra boolean.
}
```

Một consumer có thể timeout hoặc được producer khác phục vụ ngay giữa hai lệnh. Đây là lỗi **check-then-act**. Câu trả lời thực sự của handoff nằm ở `tryTransfer`.

### 7.3. Vì sao size() không phải metric nhẹ?

`LinkedTransferQueue.size()` **không O(1)**: có thể cần duyệt các node. Trong khi queue bị sửa đồng thời, giá trị có thể là ước tính cũ. Không poll `size()` với tần suất rất cao trong hot path hoặc dùng làm phương pháp giới hạn capacity chính.

Để kiểm soát overload, nên dùng cấu trúc **bounded queue** khi cần, hoặc một cơ chế `Semaphore`/quota cấp ứng dụng, không trông cậy vào phép đọc `size() < LIMIT` rồi `offer` vì hai thao tác không atomic.

## 8. Java 17+ chạy thực tế: kiểm thử cả ba đường thành công/thất bại

Tạo file **`TransferQueueDemo.java`**. Chương trình dùng `LinkedTransferQueue<Integer>` và `ExecutorService` tối đa hai worker để kiểm tra tuần tự các tình huống:

1. `tryTransfer(10)` khi không có consumer → false và queue rỗng.
2. `offer(11)` → consumer lấy được 11, chứng minh `offer` không đòi consumer chờ trước.
3. Consumer thực sự bắt đầu `take`; sau khi `hasWaitingConsumer()==true`, `tryTransfer(20)` trả true, consumer lấy 20.
4. `tryTransfer(30,100,MILLISECONDS)` khi không có consumer → false, queue rỗng.
5. Một producer gọi timed `tryTransfer(40,5,SECONDS)` và một consumer gọi `take` → producer trả true, consumer nhận 40.
6. Một producer gọi `transfer(50)` trong lúc chưa có consumer; test thấy transfer pending và producer chưa hoàn tất; khi consumer `take`, producer mới hoàn tất.
7. Một thread đang đợi timed `tryTransfer(60,30,SECONDS)` bị interrupt; nhận `InterruptedException` và không để 60 trong queue.
8. `tryTransfer(null)` ném `NullPointerException`.
9. Shutdown và chờ executor do chương trình tạo.

Các helper `waitForWaitingConsumer`/`waitForPendingElement` là **cơ chế quan sát có deadline để điều phối TEST trong môi trường kiểm soát**, không phải khuyến nghị dùng `hasWaitingConsumer/contains` cho code giao hàng production. Phần kiểm thử không khẳng định thứ tự scheduling chính xác; nó chờ **điều kiện quan sát được** rồi mới thực hiện bước tiếp theo.

### 8.1. Chương trình hoàn chỉnh: TransferQueueDemo.java

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedTransferQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TransferQueue;
import java.util.concurrent.atomic.AtomicBoolean;

public final class TransferQueueDemo {
    private static void check(boolean ok, String description) {
        if (!ok) throw new AssertionError(description);
    }

    private static void waitForWaitingConsumer(TransferQueue<?> queue)
            throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (!queue.hasWaitingConsumer()) {
            if (System.nanoTime() >= deadline) {
                throw new AssertionError("Consumer did not begin waiting");
            }
            Thread.sleep(1);
        }
    }

    private static void waitForPendingElement(
            LinkedTransferQueue<Integer> queue, int value)
            throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (!queue.contains(value)) {
            if (System.nanoTime() >= deadline) {
                throw new AssertionError("Pending transfer not observed");
            }
            Thread.sleep(1);
        }
    }

    public static void main(String[] args) throws Exception {
        LinkedTransferQueue<Integer> queue = new LinkedTransferQueue<>();
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            boolean immediateWithoutConsumer = queue.tryTransfer(10);
            check(!immediateWithoutConsumer && queue.isEmpty(),
                    "immediate failure must not enqueue");
            System.out.println(
                    "tryTransfer without consumer = false; empty = true");

            queue.offer(11);
            check(queue.take() == 11 && queue.isEmpty(),
                    "offer must enqueue");
            System.out.println("offer then take = 11");

            Future<Integer> waitingConsumer = pool.submit(queue::take);
            waitForWaitingConsumer(queue);
            boolean immediateWithConsumer = queue.tryTransfer(20);
            check(immediateWithConsumer
                            && waitingConsumer.get(5, TimeUnit.SECONDS) == 20
                            && queue.isEmpty(),
                    "immediate handoff failed");
            System.out.println(
                    "tryTransfer with waiting consumer = true; received = 20");

            boolean timedOut = queue.tryTransfer(
                    30, 100, TimeUnit.MILLISECONDS);
            check(!timedOut && queue.isEmpty(),
                    "timed failure must not enqueue");
            System.out.println(
                    "timed tryTransfer without consumer = false; empty = true");

            Future<Boolean> timedProducer =
                    pool.submit(() -> queue.tryTransfer(
                            40, 5, TimeUnit.SECONDS));
            Future<Integer> timedConsumer = pool.submit(queue::take);
            check(timedProducer.get(6, TimeUnit.SECONDS)
                            && timedConsumer.get(6, TimeUnit.SECONDS) == 40
                            && queue.isEmpty(),
                    "timed transfer matching failed");
            System.out.println(
                    "timed tryTransfer with consumer = true; received = 40");

            CountDownLatch transferStarted = new CountDownLatch(1);
            Future<?> producer = pool.submit(() -> {
                transferStarted.countDown();
                queue.transfer(50);
                return null;
            });
            check(transferStarted.await(5, TimeUnit.SECONDS),
                    "transfer producer did not start");
            waitForPendingElement(queue, 50);
            check(!producer.isDone(),
                    "producer should await reception");
            Future<Integer> receiver = pool.submit(queue::take);
            check(receiver.get(5, TimeUnit.SECONDS) == 50,
                    "transfer receiver");
            producer.get(5, TimeUnit.SECONDS);
            check(queue.isEmpty(),
                    "transfer should not leave item queued");
            System.out.println(
                    "transfer waited and completed after take = true");

            CountDownLatch interruptStarted = new CountDownLatch(1);
            AtomicBoolean interrupted = new AtomicBoolean();
            Thread waitingProducer = new Thread(() -> {
                try {
                    interruptStarted.countDown();
                    queue.tryTransfer(60, 30, TimeUnit.SECONDS);
                } catch (InterruptedException expected) {
                    interrupted.set(true);
                    Thread.currentThread().interrupt();
                }
            }, "transfer-timeout-interrupt");
            waitingProducer.start();
            check(interruptStarted.await(5, TimeUnit.SECONDS),
                    "interrupt producer did not start");
            waitForPendingElement(queue, 60);
            waitingProducer.interrupt();
            waitingProducer.join(5_000L);
            check(!waitingProducer.isAlive() && interrupted.get()
                            && queue.isEmpty(),
                    "interrupted transfer should not leave element");
            System.out.println(
                    "interrupted timed transfer = true; empty = true");

            boolean nullRejected = false;
            try {
                queue.tryTransfer(null);
            } catch (NullPointerException expected) {
                nullRejected = true;
            }
            check(nullRejected, "null should be rejected");
            System.out.println("null element rejected = true");

            System.out.println("checks = PASS");
        } finally {
            pool.shutdownNow();
            check(pool.awaitTermination(5, TimeUnit.SECONDS),
                    "executor did not terminate");
        }
        System.out.println("executor terminated = true");
    }
}
```

### 8.2. Biên dịch và chạy

Dùng JDK 17 trở lên, không cần thư viện ngoài:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 TransferQueueDemo.java
java TransferQueueDemo
```

Một lượt chạy thực tế đã hoàn thành với **stdout đúng mười dòng**:

```text
tryTransfer without consumer = false; empty = true
offer then take = 11
tryTransfer with waiting consumer = true; received = 20
timed tryTransfer without consumer = false; empty = true
timed tryTransfer with consumer = true; received = 40
transfer waited and completed after take = true
interrupted timed transfer = true; empty = true
null element rejected = true
checks = PASS
executor terminated = true
```

Các dòng kết quả thể hiện **assertions thành công** chứ không đo tốc độ. Test dùng timeout để không chờ vô hạn; trên máy bị giới hạn tạo thread hoặc CI quá tải có thể gặp lỗi do môi trường — không được biến timeout thành PASS giả.

### 8.3. Vì sao dùng Thread.sleep(1) trong helper test?

Hai helper muốn quan sát một trạng thái tạm thời: consumer đang chờ hoặc producer đang có transfer pending. Chúng lặp có **deadline 5 giây** và nghỉ ngắn giữa các phép quan sát để giảm busy-spin. Đây **không** là cơ chế đồng bộ ổn định cho nghiệp vụ sản xuất.

Trong production, đừng đoán “chắc chắn consumer đang chờ” qua sleep hay count snapshot; dùng `tryTransfer` rồi tin **boolean return** làm kết quả quyết định.

### 8.4. Vì sao kiểm tra queue.contains(50)?

`transfer(50)` có thể giữ một item đang chờ consumer và block producer. Test kiểm tra có dấu hiệu pending item rồi mới assert `!producer.isDone()`, sau đó cho consumer lấy. `contains` là thao tác collection quan sát được nhưng không bảo đảm atomic với những hành động khác trong tình huống concurrent producer/consumer.

Trong bài test này không có consumer nào được khởi động cho 50 trước khi assertion nên điều kiện khá dễ kiểm chứng; trong production không dùng `contains` như cách quyết định đã nhận hay chưa.

### 8.5. Vì sao kiểm tra queue.isEmpty() sau timeout/interrupt?

Theo hợp đồng `TransferQueue`, khi timed handoff hết hạn hoặc thread bị interrupt lúc chờ, **phần tử không được để lại enqueued**. Trong test chỉ có một luồng logic điều khiển và không có consumer đang xử lý phần tử đó ở nhánh thất bại, nên kiểm tra rỗng giúp nhận diện lỗi logic.

Trong hệ thống có nhiều producer/consumer, `queue.isEmpty()` có thể thay đổi theo race, và không phải bằng chứng riêng một message đã/không được bàn giao; phải dựa vào return/exception và message identity/ack protocol.

### 8.6. Vì sao kết quả true không có nghĩa xử lý xong?

Consumer `take()` trả về integer và Future của consumer hoàn thành. Producer `tryTransfer` trả true khi item **được consumer nhận**, không chờ consumer thực hiện nghiệp vụ sau lệnh `take`. Chương trình demo không có business processing khác; để kiểm thử xử lý thật cần thêm callback/ack kết quả.

## 9. Xử lý lỗi và trạng thái một cách chính xác

| Tình huống | Đầu ra từ API | Ý nghĩa | Hành động gợi ý |
| --- | --- | --- | --- |
| Immediate: consumer chờ | `true` | Đã bàn giao cho consumer | Ghi HANDED_OFF |
| Immediate: consumer chưa chờ | `false` | **Không enqueue** | Drop/fallback/retry có chủ đích |
| Timed: match trước deadline | `true` | Đã bàn giao trước deadline | Ghi HANDED_OFF |
| Timed: hết deadline | `false` | **Không enqueue** | Ghi TIMEOUT; quyết định fallback |
| Timed bị interrupt | `InterruptedException` | Đã dừng chờ; **không để lại e enqueued** | Theo cancellation policy, restore flag nếu catch |
| Phần tử null | `NullPointerException` | Dữ liệu không hợp lệ | Sửa upstream, không retry null |
| Consumer đã take, xử lý sau đó lỗi | Producer có thể đã nhận `true` | Handoff thành công nhưng business failed | Cần ack/retry/durable workflow ngoài TransferQueue |
| Producer chuyển sang `offer` fallback | `offer` true trên LinkedTransferQueue bình thường | Message được đưa vào queue, không nhất thiết đã nhận | Theo dõi ENQUEUED riêng |

### 9.1. Hệ thống cần lưu trạng thái phân biệt

Một mô hình delivery status:

```text
NEW
  |
  +-- tryTransfer true  --------> HANDED_OFF
  |
  +-- tryTransfer false --------> NOT_HANDED_OFF
  |                                |
  |                                +-- drop/drop metric
  |                                +-- retry bounded
  |                                +-- enqueue fallback
  |                                +-- persist to durable broker
  |
  +-- timed interrupted --------> CANCELLED/INTERRUPTED

HANDED_OFF --(business ack)----> PROCESSED
           --(business fail)---> PROCESSING_FAILED
```

Đây là state diagram khái niệm. Nếu yêu cầu xử lý chính xác một lần, cần thêm message ID, idempotency, durable state, retry/ack và failure recovery. Queue in-memory không tự cung cấp toàn bộ điều này.

### 9.2. Không nhầm InterruptedException với boolean false

`tryTransfer(e)` không khai báo checked `InterruptedException` vì không đợi consumer. Bản **có timeout** và `transfer(e)` có thể ném `InterruptedException`. Không nên catch cả hai như cùng một boolean false để retry vô điều kiện.

### 9.3. Memory visibility của dữ liệu qua queue

`LinkedTransferQueue` là concurrent collection có **memory consistency effects**: những hành động của một thread **trước khi đặt** object vào queue *happen-before* những hành động **sau khi thread khác truy cập hoặc lấy** object tương ứng.

Điều đó hỗ trợ việc producer chuẩn bị payload rồi consumer đọc sau nhận. Nhưng **không làm object trở thành immutable**. Nếu producer tiếp tục sửa cùng instance sau khi đã bàn giao, bạn vẫn có thể tạo data race hoặc dữ liệu không nhất quán.

Một thực hành tốt là **immutable message record** hoặc quy ước chuyển ownership rõ sau handoff.

### 9.4. Dữ liệu null không được phép

`LinkedTransferQueue` không chấp nhận `null`. Dùng `Optional` hoặc một loại sentinel/message riêng nếu protocol cần biểu thị “không có dữ liệu” hay “shutdown”, thay vì gọi `tryTransfer(null)`.

## 10. Thiết kế fallback: đảm bảo không vô tình mất dữ liệu

Với một event có thể bỏ qua:

```java
boolean handedOff = queue.tryTransfer(event);
if (!handedOff) {
    metrics.skippedDelivery().increment();
}
```

Đoạn này chỉ hợp lệ khi **bỏ qua event được nghiệp vụ cho phép**. `metrics` là đối tượng do ứng dụng cung cấp, không phải API của Java.

Với một event bắt buộc phải lưu:

```java
if (!queue.tryTransfer(event)) {
    queue.offer(event);
}
```

Đoạn này có thể tạo **fallback enqueue** trên `LinkedTransferQueue`, nhưng phải hiểu:

- `tryTransfer` false không enqueue nên `offer` ở nhánh false không tạo duplicate từ **chính lần thử đó**.
- `offer` không đợi consumer xử lý xong.
- `LinkedTransferQueue` unbounded; khi consumer chậm hơn producer, phần tử có thể tăng không giới hạn về mặt API cho tới khi RAM cạn.
- Nếu upstream có retry do mất ack, không được suy rằng mỗi message identity sẽ chỉ xuất hiện một lần; cần idempotency.

### 10.1. Bounded fallback bằng semaphore

Một ý tưởng để không enqueue vô hạn:

```java
if (queue.tryTransfer(event)) {
    handedOffCounter.increment();
} else if (capacityPermits.tryAcquire()) {
    boolean enqueued = queue.offer(event);
    if (!enqueued) {
        capacityPermits.release();
        throw new IllegalStateException("Fallback enqueue failed");
    }
} else {
    rejectedCounter.increment();
}
```

Đây là **phác thảo**, không phải chương trình độc lập; `capacityPermits` là `Semaphore` do ứng dụng quản lý, `handedOffCounter` và `rejectedCounter` là metrics. Thiết kế thực tế **phải release permit sau khi consumer lấy message từ nhánh fallback**, kể cả khi có exception; nếu không sẽ cạn permit. Cũng phải quản lý shutdown/clear/cancel để không rò permit.

Đoạn minh họa làm rõ ý tưởng quota nhưng chưa xử lý cạnh tranh với producer khác, phân biệt source handoff/fallback của mỗi message hay hard durability; code production cần state/ownership đầy đủ.

### 10.2. Không dùng size() < max rồi offer

```java
if (queue.size() < 1000) {
    queue.offer(event);
}
```

Đây là anti-pattern. `size()` của `LinkedTransferQueue` có thể O(n), momentary, và giữa check và offer các producer khác cũng có thể enqueue. Không có bảo đảm upper bound 1000. Dùng bounded queue implementation hoặc permit atomic.

### 10.3. Vì sao không chỉ tăng timeout?

Tăng từ 100 ms lên 30 s có thể cải thiện tỷ lệ direct handoff nếu consumer thường đến muộn, nhưng đồng thời giữ **producer thread** lâu hơn, ảnh hưởng throughput, thread pool và SLA của upstream. Không có một timeout tối ưu chung.

Hãy đo tần suất `HANDOFF/NO_CONSUMER/TIMEOUT/INTERRUPT`, p50/p95/p99 của thời gian chờ và số thread blocked, rồi quyết định theo workload.

## 11. Backpressure và ứng dụng nhiều producer

### 11.1. Timed handoff là một dạng áp lực ngược có điều kiện

Khi producer gọi `tryTransfer(e,timeout,unit)`, nó chấp nhận đợi consumer **nhận** trước một thời hạn. Vì vậy producer có thể tự chậm lại theo khả năng consumer, thay vì bơm mọi thứ vào hàng đợi.

Tuy nhiên:

- Nếu mỗi request tạo một producer thread mới, lượng thread blocked có thể rất lớn.
- Timeout chỉ giới hạn thời gian **mỗi lần thử**, không giới hạn số producer đang cùng đợi.
- Không tự giới hạn tải của database/network downstream.
- Không tự tạo ack nghiệp vụ.

Backpressure thực tế nên bao gồm concurrency budget, bounded queue/permit, timeout và chính sách từ chối rõ.

### 11.2. Đừng mặc định worker pool sẽ luôn đủ consumer

Một hệ thống chỉ có hai consumer workers, nhưng cả hai bận xử lý tác vụ dài, thì `tryTransfer` từ producer có thể trả false liên tục dù “consumer thread vẫn còn tồn tại”. Điều kiện là **consumer đang ở take/timed poll chờ**, không phải chỉ kiểm tra số worker đã khởi tạo.

### 11.3. Độ dài xử lý nghiệp vụ khác độ dài nhận

Consumer có thể nhận message cực nhanh rồi xử lý chậm. Direct handoff có thể thành công thường xuyên nhưng backlog nghiệp vụ vẫn nằm ở downstream processing queue khác. Nếu muốn biết ứng dụng end-to-end ổn không, phải đo cả ack cuối, timeouts và resource use.

### 11.4. Shutdown phải giải phóng producer đang đợi

Nếu producer đang `transfer(e)` vô hạn, và hệ thống đã shutdown consumer, producer có thể chờ mãi. Cần policy điều phối:

1. Đánh dấu ngừng chấp nhận work mới.
2. Thông báo producer ngừng submit hoặc dùng deadline.
3. Có interrupt/cancel mechanism phù hợp.
4. Cho consumer drain nếu muốn graceful shutdown, hoặc báo lỗi rõ nếu hủy.
5. Chờ tất cả threads/executor dừng trong deadline.
6. Phân biệt message đã bàn giao và message chưa bàn giao.

Không gọi `shutdownNow()` ở một executor rồi tin mọi `transfer` đang chờ của **mọi** thread trong hệ thống đều đã được giải phóng; phải xác định ownership và interrupt semantics cụ thể.

## 12. Các lỗi thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Bỏ qua boolean từ `tryTransfer` | False không enqueue, message có thể mất | Xử lý success/failure |
| Nghĩ false nghĩa “đang xếp hàng” | API quy định **không lưu** trên thất bại | Fallback `offer` nếu cần |
| Dùng `tryTransfer` để thay `offer` mọi nơi | Hợp đồng khác | Chọn theo intent delivery |
| Dùng `tryTransfer(e,t,u)` như enqueue có timeout | Nó chờ **consumer nhận**, không chỉ có capacity | Đọc contract đúng |
| Cho rằng true là xử lý xong nghiệp vụ | Handoff khác business ack | Ack riêng |
| Cho rằng consumer thread tồn tại tức consumer đang đợi | Consumer có thể bận xử lý | Đo trạng thái wait theo API; quyết định bằng tryTransfer result |
| Check `hasWaitingConsumer` trước rồi bỏ boolean | Race check-then-act | Dùng return của tryTransfer |
| Xem `getWaitingConsumerCount` là exact | Chỉ là ước tính momentary | Dùng telemetry, không điều kiện đúng đắn |
| Poll `size` mỗi message | O(n), momentary | Metrics sampled hoặc bounded design |
| Dựa vào `size < N` rồi offer để cap | Check/act không atomic | Semaphore/bounded queue |
| Quên `LinkedTransferQueue` unbounded | Có thể tăng memory rất lớn | Backpressure, limits |
| Gọi `transfer` từ request thread mà không deadline | Có thể chờ vô hạn | Timed tryTransfer hoặc cơ chế hủy |
| Timed tryTransfer false nhưng vẫn đánh dấu SENT | False không bàn giao | Ghi timeout và fallback |
| Ngắt producer nhưng không quản lý state | Retry sai/cancel không rõ | Propagate hoặc restore interrupt flag |
| Thử `tryTransfer(null)` | Null bị từ chối | Validate message |
| Coi timed `offer` là timed `tryTransfer` | Hai hợp đồng khác | Chọn đúng API |
| Dùng `poll()` trong consumer loop và nghĩ nó chờ | `poll()` không chờ | `take()` hoặc timed `poll` |
| Nghĩ queue là durable broker | RAM mất khi process crash | Persistence/ack/idempotency riêng |
| Sửa mutable message sau handoff | Data race và message bị thay đổi | Immutable payload/ownership |
| Tin thứ tự toàn cục giữa nhiều producer | Concurrent interleavings | Sequence/serialization nếu cần |
| Dùng sleep để chứng minh timing | Scheduling nondeterministic | Latch/condition + bounded timeout trong tests |
| Không chờ producer/consumer kết thúc khi shutdown | Resource leak/pending work | Shutdown protocol |
| Retry liên tục mà không total deadline | Có thể chờ vô hạn | Deadline/cancellation budget |
| Ghi metric only success, không đếm false | Mất dữ liệu bị che giấu | Metrics theo từng outcome |
| Nhầm unbounded với không tốn bộ nhớ | Capacity API không bằng RAM | Monitor/limit memory |
| Đếm `hasWaitingConsumer()==true` như cam kết handoff | Consumer có thể biến mất | Dùng kết quả atomic handoff |
| Benchmark một lần rồi tuyên bố API luôn nhanh hơn | Workload/scheduler ảnh hưởng | Benchmark fairness, p99, CPU |

## 13. Bài tập có đáp án

### Bài 1 — Queue rỗng không có consumer

`new LinkedTransferQueue<String>().tryTransfer("A")` trả gì?

**Đáp án:** `false`, không để "A" trong queue. Không có consumer đang chờ để nhận ngay.

### Bài 2 — False có enqueue?

Một producer gọi `tryTransfer("X")` và nhận false. Consumer gọi `take()` một giây sau sẽ nhận "X" từ lần thử đó không?

**Đáp án:** Không. False nghĩa không bàn giao và không enqueue. Consumer sẽ tiếp tục chờ cho tới khi có một operation gửi phần tử mới.

### Bài 3 — Consumer đang đợi

Consumer đã blocked trong `take`, producer gọi `tryTransfer("B")`. Kết quả mong đợi khi bàn giao thành công?

**Đáp án:** Boolean `true`, consumer nhận "B". Việc xử lý business logic sau đó không được bảo đảm bởi return true.

### Bài 4 — Producer xử lý false

Nghiệp vụ bắt buộc không làm mất event. Có nên viết `queue.tryTransfer(event);` mà không kiểm tra kết quả không?

**Đáp án:** Không. Phải xử lý false bằng retry/fallback/durable flow theo hợp đồng.

### Bài 5 — Timed handoff

Producer dùng `tryTransfer("C", 100, MILLISECONDS)`, không consumer nào nhận. Giá trị trả về và trạng thái message?

**Đáp án:** `false`, "C" **không** bị để lại trong queue do lần gọi đó.

### Bài 6 — Consumer đến trong deadline

Consumer bắt đầu chờ sau 40 ms, producer đã gọi timed tryTransfer với deadline 200 ms. Khi match thành công, nhận gì?

**Đáp án:** `true` và consumer nhận phần tử. Không có bảo đảm chính xác scheduler, nhưng đây là trường hợp hoạt động mong muốn.

### Bài 7 — InterruptedException

Producer đang chờ timed tryTransfer và bị interrupt. API trả false hay ném exception?

**Đáp án:** Ném `InterruptedException`; theo contract item không được để lại enqueued. Caller cần policy cancel và bảo toàn interrupt semantics.

### Bài 8 — offer

`queue.offer("D")` trên `LinkedTransferQueue` khi chưa có consumer chờ làm gì?

**Đáp án:** Chèn "D" vào queue, để consumer lấy sau; không chờ người nhận.

### Bài 9 — put

`queue.put("E")` trên `LinkedTransferQueue` có chờ consumer nhận như `transfer("E")` không?

**Đáp án:** Không. Đây là unbounded implementation, `put` chèn vào queue mà không đợi consumer nhận.

### Bài 10 — transfer

`queue.transfer("F")` khi không consumer nào nhận có thể làm gì?

**Đáp án:** Producer chờ tới khi một consumer nhận (hoặc bị interrupt), không phải return ngay như `offer`. Cần lifecycle/timeout strategy tránh kẹt.

### Bài 11 — SynchronousQueue

`SynchronousQueue` có thể cast thành `TransferQueue` trong Java chuẩn không?

**Đáp án:** Không. Nó triển khai `BlockingQueue` với zero capacity, nhưng không là implementation của `TransferQueue`.

### Bài 12 — hasWaitingConsumer

`hasWaitingConsumer()` vừa trả true. Có bảo đảm lần `tryTransfer` kế tiếp phải trả true không?

**Đáp án:** Không. Consumer có thể hết hạn hoặc bị producer khác phục vụ. Đây là momentary observation.

### Bài 13 — getWaitingConsumerCount

Giá trị `getWaitingConsumerCount()==3` có nghĩa chính xác ba consumers chắc chắn vẫn đang chờ đến hết thao tác tiếp theo không?

**Đáp án:** Không. Đây là **ước tính**, phù hợp monitoring, không bảo đảm giao thức.

### Bài 14 — Consumer bận

Ba consumer threads tồn tại nhưng đều đang xử lý tác vụ cũ. `tryTransfer` có chắc thành công không?

**Đáp án:** Không. Consumer phải đang **đợi một operation nhận** mới khớp được immediate transfer.

### Bài 15 — LinkedTransferQueue.size

Vì sao không poll `queue.size()` liên tục để đảm bảo queue dưới 1000 message?

**Đáp án:** `size()` không O(1) và không atomic với các producers; có thể trả ước tính momentary. Dùng capacity limit thực hoặc quota semaphore.

### Bài 16 — Tính nhất quán bộ nhớ

Producer khởi tạo immutable message rồi đưa vào `LinkedTransferQueue`; consumer đọc sau `take`. Cơ chế Java nào hỗ trợ visibility?

**Đáp án:** Memory consistency/happens-before của concurrent collection cho hành động trước khi đặt và sau khi thread khác truy cập/lấy. Không được tự ý sửa mutable payload sau handoff.

### Bài 17 — Thời hạn tổng

Producer retry `tryTransfer(event,1,SECONDS)` 10 lần liên tiếp. Có cam kết tổng thời gian đợi không vượt 1 giây không?

**Đáp án:** Không. Mỗi lần thử có timeout riêng; cần định nghĩa **deadline tổng** để quản lý request SLA.

### Bài 18 — Exactly-once

`tryTransfer` trả true. Có thể xóa message trong durable store vì downstream chắc chắn đã xử lý thành công không?

**Đáp án:** Không. Nó chỉ chứng minh **consumer nhận**. Cần business acknowledgement, idempotency và giao thức phục hồi.

### Bài 19 — Null

`queue.tryTransfer(null)` có hợp lệ không?

**Đáp án:** Không, `LinkedTransferQueue` từ chối `null` bằng `NullPointerException`.

### Bài 20 — Handoff vs enqueue

Ứng dụng muốn producer không chờ và message được lưu cho consumer đến sau. Chọn `tryTransfer` hay `offer`?

**Đáp án:** Chọn `offer` trên queue phù hợp, và có chính sách capacity/backpressure nếu cần. `tryTransfer` là direct handoff chứ không phải enqueue khi thiếu consumer.

### Bài 21 — Hủy khi shutdown

Producer đang chờ `transfer` vô hạn, consumer đã shutdown. Chỉ ngừng gửi thêm request có đủ giải phóng producer không?

**Đáp án:** Không. Producer có thể vẫn bị blocked. Cần cancellation/interrupt hoặc thiết kế timed handoff cùng shutdown policy để tiến triển.

### Bài 22 — Kết quả benchmark

Một benchmark ghi `tryTransfer` “nhanh hơn offer” vì phần lớn trả false. Có hợp lệ nếu không tính số message bị bỏ?

**Đáp án:** Không. Hai operation làm việc khác nhau; phải so cùng amount of successful delivery và đếm failure/drop rate. Không coi bỏ công việc là tối ưu throughput.

## 14. Checklist triển khai trong dự án

- [ ] Đã xác định rõ mục tiêu: **direct handoff**, **wait bounded**, hay **enqueue**.
- [ ] Không bỏ qua boolean `tryTransfer(e)`.
- [ ] False immediate đồng nghĩa **không enqueued**.
- [ ] False timed đồng nghĩa **hết deadline mà không bàn giao và không enqueued**.
- [ ] `InterruptedException` timed/transfer được xử lý theo policy riêng.
- [ ] Không đánh dấu processed chỉ vì `tryTransfer` trả true.
- [ ] Có ack xử lý nghiệp vụ riêng khi cần.
- [ ] Consumer sử dụng `take()` hoặc timed `poll()` nếu muốn thực sự đợi nhận.
- [ ] Không dùng `hasWaitingConsumer` làm điều kiện đảm bảo handoff.
- [ ] Không dùng `getWaitingConsumerCount` làm counter chính xác.
- [ ] Không dùng `size()` trong hot path để enforce capacity.
- [ ] Hiểu `LinkedTransferQueue` unbounded và `remainingCapacity==Integer.MAX_VALUE` không phản ánh RAM.
- [ ] Nếu cần buffer giới hạn, đã thêm quota hoặc chọn implementation bounded.
- [ ] Có chính sách deadline tổng, retry, fallback và overload.
- [ ] Không tạo vô hạn producer threads bị chờ trên timed transfer.
- [ ] Thông điệp không null và immutable hoặc chuyển ownership rõ.
- [ ] Kiểm thử cả immediate true/false, timed true/false, interrupt và transfer.
- [ ] Không dùng `Thread.sleep` đơn lẻ làm bằng chứng thứ tự thực thi.
- [ ] Có graceful shutdown, release producers và await termination.
- [ ] Có metrics true/false/timeout/interrupted/processed.
- [ ] Nếu muốn persistence/recovery, dùng durable storage riêng.
- [ ] Không dựa vào FIFO toàn cục giữa mọi producer trong concurrency cao.
- [ ] Dùng Java 17+ cho ví dụ hoàn chỉnh, hiểu `TransferQueue` từ Java 7 vẫn hiện hành.

## 15. Tài liệu chính thức

- [Java SE 17 — TransferQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TransferQueue.html): quy tắc của `tryTransfer` immediate/timed, `transfer`, interruption, no-enqueue on timeout/failure và waiting consumer.
- [Java SE 17 — LinkedTransferQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedTransferQueue.html): implementation unbounded, FIFO per producer, `size()` O(n), memory consistency và các phương thức queue.
- [Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): `offer`, `put`, `take`, `poll` và các loại waiting/blocking.
- [Java SE 17 — TimeUnit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html): deadline tương đối và đơn vị thời gian.
- [Java SE 17 — SynchronousQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SynchronousQueue.html): zero-capacity rendezvous queue để phân biệt với `LinkedTransferQueue`.

## 16. Kết luận

`tryTransfer(e)` là **phép bàn giao ngay**, chỉ thành công nếu có consumer đã đợi nhận. Nếu không, nó trả false **mà không enqueue** phần tử. `tryTransfer(e, timeout, unit)` có thể đợi consumer xuất hiện tới deadline; trả true nếu đã bàn giao, false nếu hết hạn, và **không để lại phần tử** ở nhánh timeout. Khi bị interrupt trong lúc chờ, API ném `InterruptedException` và cũng không để item enqueued theo contract.

`transfer(e)` khác ở chỗ có thể đợi cho đến khi nhận được mà không có timeout sẵn; `offer(e)`/`put(e)` trên `LinkedTransferQueue` là thao tác đưa vào queue, **không đợi consumer nhận**. Mọi quyết định đều phải xét tới nhu cầu không mất message, deadlines, thread blocking, backpressure và chính sách fallback.

Cuối cùng, **consumer nhận không phải consumer xử lý thành công**. Cấu trúc đồng thời trong bộ nhớ giúp phối hợp các thread trong một JVM; nếu hệ thống cần durability, exactly-once, audit hoặc khôi phục sau lỗi, cần thêm giao thức acknowledgement, identity và persistence phù hợp.