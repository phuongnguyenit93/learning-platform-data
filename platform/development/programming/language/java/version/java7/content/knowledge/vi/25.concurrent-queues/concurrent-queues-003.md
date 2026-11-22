# Hàng đợi đồng thời trong Java: Phân biệt đưa vào hàng đợi với transfer tới bên nhận

## 1. Tại sao “đã đưa vào queue” không đồng nghĩa “đã có bên nhận”?

Trong một hệ thống producer–consumer, phía producer thường cần biết mình vừa **gửi yêu cầu thành công ở cấp độ nào**. Hai câu sau không giống nhau:

- **Đã đưa vào hàng đợi:** dữ liệu đã được chấp nhận để bên nhận có thể lấy trong tương lai.
- **Đã chuyển tới bên nhận (transfer):** một consumer đã nhận chính phần tử ấy qua thao tác lấy khỏi hàng đợi.

Thậm chí còn một mức thứ ba độc lập:

- **Đã xử lý nghiệp vụ:** consumer không chỉ nhận dữ liệu mà còn chạy logic, lưu database, hoàn thành giao dịch hoặc tạo kết quả.

Bài **“Phân biệt đưa vào hàng đợi với transfer tới bên nhận”** thuộc chủ đề **“Hàng đợi đồng thời”** tập trung vào `java.util.concurrent.TransferQueue<E>` và `LinkedTransferQueue<E>`. Các API được đưa vào từ **Java 7** và **vẫn còn áp dụng trong Java 17+**. Chúng cho phép cùng một cấu trúc dữ liệu hỗ trợ cả hai chế độ: enqueue thông thường và handoff chờ consumer.

Quy tắc trọng tâm:

```text
put(e) / offer(e)
  Producer: queue chấp nhận e
  Producer: trả về
  Consumer: có thể còn CHƯA nhận

transfer(e)
  Producer: gửi e vào cơ chế handoff / hàng đợi nếu cần
  Producer: CHỜ cho tới khi consumer nhận chính e
  Consumer: take()/poll(...) lấy e
  Producer: transfer(e) trả về
  Consumer: có thể còn CHƯA xử lý xong nghiệp vụ

tryTransfer(e)
  Có waiting consumer phù hợp: chuyển ngay, trả true
  Không có waiting consumer: trả false, KHÔNG enqueue e

tryTransfer(e, timeout, unit)
  Đợi consumer nhận trong thời hạn
  Thành công: trả true
  Hết hạn trước khi nhận: trả false; KHÔNG để e nằm lại queue
```

**Không có API nào kể trên tự chứng minh consumer đã hoàn thành nghiệp vụ.** Nếu cần mức xác nhận cuối, phải thiết kế acknowledgment riêng.

## 2. Phân biệt `Queue`, `BlockingQueue` và `TransferQueue`

### 2.1. `Queue<E>`

`Queue` định nghĩa những thao tác cơ bản:

- `offer(e)`: thử thêm phần tử vào queue.
- `poll()`: lấy và loại bỏ phần tử đầu, trả `null` nếu trống.
- `peek()`: nhìn phần tử đầu mà không loại bỏ.

`offer(e)` trả `true` thường chỉ chứng minh queue chấp nhận phần tử. Nó **không phải acknowledgment của consumer**. Ở các queue có giới hạn dung lượng, `offer` có thể trả `false` do đầy.

### 2.2. `BlockingQueue<E>`

`BlockingQueue` bổ sung `put(e)` và `take()`, cùng các phiên bản có thời hạn của `offer`/`poll`.

- `put(e)` có thể chờ khi queue bounded và đang đầy.
- `take()` chờ cho tới khi có phần tử để lấy.
- `poll(timeout, unit)` có thể chờ giới hạn, sau đó trả `null` nếu không có phần tử.
- Việc producer chờ **dung lượng trống** là vấn đề khác với chờ **consumer nhận phần tử**.

Ví dụ: với một `ArrayBlockingQueue` đầy, `put(e)` chờ vì **không còn capacity**. Nhưng khi `put(e)` cuối cùng trả về, không nhất thiết e đã được consumer lấy.

### 2.3. `TransferQueue<E>`

`TransferQueue` **extends `BlockingQueue`**, bổ sung:

- `transfer(e)`: chờ consumer nhận phần tử nếu cần.
- `tryTransfer(e)`: chỉ chuyển ngay nếu có consumer đang đợi; không có thì trả false, không enqueue.
- `tryTransfer(e, timeout, unit)`: đợi consumer nhận trong thời hạn.
- `hasWaitingConsumer()`: quan sát xem hiện có waiting consumer hay không.
- `getWaitingConsumerCount()`: **ước lượng** số consumer đang đợi.

Theo tài liệu Java SE 17, một `TransferQueue` có thể bounded hoặc unbounded tùy implementation. Đừng đồng nhất interface `TransferQueue` với một class cụ thể.

### 2.4. `LinkedTransferQueue<E>`

`LinkedTransferQueue` là implementation concurrent **không giới hạn dung lượng logic** (unbounded), có cấu trúc linked và hỗ trợ transfer trực tiếp. Trong Java 17:

- `offer(e)`, `add(e)`, `put(e)` thêm ở cuối queue.
- `put(e)` **không phải chờ consumer** vì không bị ràng buộc capacity.
- `remainingCapacity()` trả `Integer.MAX_VALUE`, **không hứa JVM có bộ nhớ vô hạn**.
- `transfer(e)` chờ đến khi consumer nhận e.
- `tryTransfer(e)` chỉ thành công khi consumer đang chờ nhận ngay.
- `tryTransfer(e,timeout,unit)` thất bại theo thời hạn mà không để e lại queue.
- `null` không được chấp nhận làm phần tử.

Java có thể thực hiện matching producer/consumer với cơ chế lock-free/nonblocking tùy implementation, nhưng không xây dựng logic nghiệp vụ bằng giả định về cách các node nội bộ được nối hoặc trạng thái private bên trong queue.

## 3. Bảng đối chiếu các thao tác của LinkedTransferQueue

| Producer API | Có thể chờ? | Nếu không có consumer | Điều kiện trả về thành công | Có để lại e trong queue khi không có receiver? |
| --- | --- | --- | --- | --- |
| `add(e)` | Không chờ receiver | Thêm e | e được queue chấp nhận | **Có** |
| `offer(e)` | Không chờ receiver | Thêm e | Trả `true` | **Có** |
| `put(e)` | Không chờ receiver trong `LinkedTransferQueue` | Thêm e | Method trả về | **Có** |
| `offer(e,timeout,unit)` | Không chờ capacity trong class này | Thêm e | Trả `true` | **Có** |
| `transfer(e)` | **Có**; interruptible | E có thể nằm trong queue trong lúc producer chờ | Consumer đã **nhận e** | Đang chờ thì có thể có; sau khi trả thành công thì đã được nhận |
| `tryTransfer(e)` | Không chờ | Trả `false` | Consumer đang đợi đã nhận ngay | **Không** |
| `tryTransfer(e,timeout,unit)` | **Có thời hạn**; interruptible | Tạm đưa e vào cơ chế chờ | Consumer đã nhận trong deadline thì `true`; quá hạn thì `false` | **Không** sau timeout |

Bảng mô tả **`LinkedTransferQueue`**, không phải mọi implementation `TransferQueue`. Đặc biệt, `put` trên queue bounded có thể block vì **capacity**, còn `transfer` chờ vì **reception**.

Các phương thức consumer:

| Consumer API | Khi queue trống | Sau khi thành công |
| --- | --- | --- |
| `take()` | Chờ | Trả về và loại bỏ một phần tử |
| `poll()` | Trả `null` ngay | Trả và loại bỏ một phần tử |
| `poll(timeout,unit)` | Chờ tới deadline | Trả phần tử hoặc `null` |
| `peek()` | Trả `null` ngay | **Không** loại bỏ, **không** xác nhận transfer |
| `iterator()` | Quan sát weakly consistent | Không phải cơ chế xác nhận delivery |

Khi cần semantics chờ bên nhận, phải dùng **transfer/tryTransfer**, không suy từ `offer`, `put`, `peek` hoặc `size`.

## 4. Enqueue: `put` và `offer` trả về trước khi consumer nhận

Xét ví dụ:

```java
LinkedTransferQueue<String> queue = new LinkedTransferQueue<>();

queue.put("PENDING");

System.out.println(queue.isEmpty()); // false
System.out.println(queue.take());    // PENDING
```

Không cần consumer thread nào đang đợi khi `put("PENDING")` trả về. Phần tử đã sẵn sàng cho một consumer lấy sau đó. Với `LinkedTransferQueue` unbounded, `put` không cần chờ capacity.

Giả sử request phải được xử lý trong 5 phút. Chỉ vì `put` không ném lỗi không có nghĩa:
- Có consumer thread đã chạy.
- Có consumer vẫn còn sống.
- Consumer đã `take`.
- Consumer đã commit dữ liệu.
- Dữ liệu đã được lưu bền vững.
- Ứng dụng sẽ hoàn thành trước deadline.

**Queue in-memory không phải durable message broker.** Nếu tiến trình JVM bị tắt trước khi consumer lấy phần tử, các phần tử trong bộ nhớ có thể mất. Muốn durability cần thiết kế khác như database/outbox/message broker phù hợp.

### 4.1. Vì sao `put` có tên “blocking” nhưng không block trong class này?

Vì `put` là phương thức của `BlockingQueue`; ở implementation khác, nó có thể đợi dung lượng trống. `LinkedTransferQueue` không capacity-bounded, vì vậy thêm phần tử không phải chờ chỗ trống.

Không được áp dụng kết luận “`put` luôn nonblocking” cho mọi `BlockingQueue`. Sự khác nhau nằm ở implementation và thời điểm queue cần được kiểm soát.

### 4.2. Queue có consumer đang đợi thì sao?

Khi consumer đã bị block tại `take()`, `put(e)` có thể đáp ứng ngay yêu cầu của consumer. Tuy nhiên **API `put` không buộc producer chờ consumer đã nhận**; producer không nhận một tín hiệu receipt riêng. Nếu requirement là “producer chỉ tiếp tục sau khi một consumer nhận e”, dùng `transfer(e)` hoặc giao thức ack khác.

### 4.3. Khi nào chỉ enqueue là đúng?

`put/offer` phù hợp nếu:
- Producer không muốn chờ consumer availability.
- Nhiệm vụ có thể xử lý sau.
- Các queue/retry/backpressure được quản lý ở tầng hệ thống.
- Business logic không cần producer xác nhận chính xác thời điểm receive.
- Có cơ chế giám sát lag và shutdown để tránh mất dữ liệu in-memory.

Nếu producer phải chờ **quá trình xử lý xong**, cả enqueue lẫn transfer đều chưa đủ; cần acknowledgment nghiệp vụ riêng.

## 5. `transfer(e)`: đợi một consumer nhận chính phần tử e

### 5.1. Hợp đồng của API

`TransferQueue.transfer(E e)` có ý nghĩa:

> Chuyển phần tử cho consumer, chờ nếu cần.

Với `LinkedTransferQueue`, nếu một consumer đã chờ trong `take()` hoặc timed `poll(...)` thì có thể chuyển ngay. Nếu không, phần tử được đặt ở cuối queue trong khi producer **chờ cho tới khi nó được consumer nhận**.

```java
LinkedTransferQueue<String> queue = new LinkedTransferQueue<>();

// Thread producer:
queue.transfer("WORK"); // Có thể đợi cho tới khi receiver lấy WORK.

// Thread consumer:
String work = queue.take(); // Nhận và loại bỏ WORK.
```

Đây là **snippet minh họa đa luồng**, không phải hai dòng chạy tuần tự trên cùng thread; nếu cùng thread gọi `transfer` trước `take`, chương trình có thể chờ mãi.

### 5.2. Không nhầm “đang nằm trong queue” với “producer đã hết chờ”

Khi chưa có consumer, `transfer(e)` có thể đưa phần tử vào queue rồi **producer vẫn bị block**. Tại thời điểm đó:

```text
Producer: transfer("WORK") đang chờ
Queue:    [WORK]
Consumer: chưa gọi take()
```

Nhìn thấy `queue.peek()=="WORK"` **không chứng minh** producer đã nhận acknowledgment. Sau khi consumer lấy WORK:

```text
Producer: transfer("WORK") trả về
Queue:    không còn WORK từ operation đó
Consumer: đã nhận WORK, có thể sắp xử lý
```

Đây là sự khác biệt lớn giữa “inserted/visible” và “received by consumer”.

### 5.3. `transfer` không chờ consumer xử lý nghiệp vụ

Consumer có thể gọi `take()`, nhận WORK, rồi mất nhiều giây để ghi database. `transfer("WORK")` có thể đã trả về trước khi database được ghi.

Nếu yêu cầu là **“người xử lý đã hoàn tất”**, hãy bổ sung một future/ack token hoặc một cơ chế persistent acknowledgment, không lạm dụng `transfer` như cam kết xử lý thành công.

### 5.4. Interrupt khi producer đang chờ

`transfer` có thể ném `InterruptedException` nếu thread producer bị interrupt trong lúc chờ. Hợp đồng của API nêu **trong nhánh bị ngắt, phần tử không bị để lại trong queue**. Tương tự, phần tử `null` bị từ chối.

Bắt interrupt đúng:

```java
try {
    queue.transfer(payload);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // Trả trạng thái bị hủy/propagate, không retry vô hạn.
}
```

Trong thực tế, nếu tín hiệu ngắt đua với lúc consumer nhận, caller cần dựa vào kết quả hoàn tất thực tế và giao thức idempotency/ack, không xây tính đúng nghiệp vụ từ một giả định scheduling không được bảo đảm.

## 6. `tryTransfer(e)`: handoff tức thời hoặc từ chối, không enqueue

Theo tài liệu Java SE 17:

- Nếu **đã có waiting consumer**, `tryTransfer(e)` chuyển phần tử ngay và trả `true`.
- Nếu **không có waiting consumer**, nó trả `false` và **không đưa e vào hàng đợi**.

```java
LinkedTransferQueue<String> queue = new LinkedTransferQueue<>();

boolean sent = queue.tryTransfer("NOW");

System.out.println(sent);            // false: chưa có waiting consumer.
System.out.println(queue.isEmpty()); // true: NOW không được enqueue.
```

Đây là snippet khi không có consumer thread nào được tạo. Chú ý: không thể viết “nếu `tryTransfer` false thì chắc chắn có thể lấy e ra sau bằng `poll`” — vì e **không ở trong queue**.

### 6.1. Kiểm tra waiting consumer đúng cách

`hasWaitingConsumer()` chỉ phản ánh **trạng thái tức thời**; một consumer có thể rời trạng thái chờ ngay sau khi bạn kiểm tra. Không dùng:

```java
if (queue.hasWaitingConsumer()) {
    queue.tryTransfer(work);
    // Sai nếu bỏ qua boolean: giữa check và transfer có race!
}
```

Thay vì check-then-act, gọi trực tiếp `tryTransfer` và **kiểm tra boolean kết quả**:

```java
if (!queue.tryTransfer(work)) {
    // Không có handoff tức thời: fallback / reject / enqueue theo policy.
    queue.offer(work); // Chỉ nếu nghiệp vụ cho phép queue backlog.
}
```

Đây là snippet với biến `work` đã được định nghĩa. Nếu fallback enqueue là tùy chọn, phải nhận thức nó **đổi semantics** từ direct handoff thành deferred delivery. Đừng âm thầm fallback khi client yêu cầu phải có receiver ngay.

### 6.2. Ví dụ nhu cầu thích hợp

Giả sử hệ thống đo trạng thái “đang có consumer rảnh chờ công việc”:

- Với chế độ best-effort direct assignment, gọi `tryTransfer`.
- Nếu trả `true`, consumer đã nhận trực tiếp.
- Nếu trả `false`, có thể từ chối công việc hoặc đẩy sang một backlog riêng theo policy.

**Không dùng `hasWaitingConsumer()` như một khóa để đảm bảo direct assignment**, vì đó là snapshot.

## 7. `tryTransfer(e, timeout, unit)`: handoff có deadline

### 7.1. Kết quả

```java
boolean received = queue.tryTransfer(
        "REQUEST", 500, TimeUnit.MILLISECONDS);
```

Ý nghĩa:
- `true`: một consumer nhận REQUEST trước thời hạn.
- `false`: hết thời gian chờ mà REQUEST chưa được nhận; theo contract, **nó không bị để lại trong queue**.
- `InterruptedException`: thread chờ bị ngắt; theo contract, phần tử không bị để lại trong queue trong nhánh này.

Đây là **thời hạn chờ nhận** (*receipt timeout*), không phải thời hạn hoàn thành xử lý nghiệp vụ.

### 7.2. Trong lúc chờ, phần tử vẫn có thể hiện diện

Với `LinkedTransferQueue`, khi chưa có consumer, producer có thể đưa e vào queue và đợi. Vì vậy trước khi timeout, `peek()` có thể thấy e. Nhưng nếu deadline trôi qua và method trả `false` thì e **không còn được queue giữ lại từ lần thử ấy**.

Không chỉ nhìn `isEmpty()` một thời điểm rồi kết luận timed handoff đã thành công hay thất bại; kết quả boolean/exception của operation mới là tín hiệu quan trọng.

### 7.3. Timeout 0 không tương đương enqueue

`tryTransfer(e, 0, NANOSECONDS)` không có thời gian chờ đáng kể: nó chỉ có thể handoff nếu có consumer nhận ngay; nếu không thì trả `false`, **không enqueue**.

Điều này khác hẳn `offer(e)` trên `LinkedTransferQueue`: `offer` có thể nhận e dù chưa có consumer.

### 7.4. Chọn timeout phù hợp

Deadline không được dùng làm bằng chứng hệ thống sẽ hoàn tất processing trước deadline. Nếu muốn:
1. Chờ bên nhận tối đa 200ms;
2. Sau đó chờ processing tối đa 2s;

thì đó là **hai giai đoạn độc lập**. Giai đoạn sau cần một acknowledgment riêng và phải xử lý kết quả đến muộn sau timeout.

### 7.5. Cảnh báo khi retry

Nếu handoff timeout và ứng dụng retry cùng request vào lần sau, nên có **request id** để consumer không xử lý trùng nếu hệ thống có thêm nhánh submit khác, retries từ tầng ngoài, hoặc lỗi mạng. Hợp đồng `LinkedTransferQueue` không biến toàn bộ nghiệp vụ end-to-end thành exactly-once.

## 8. Handoff khác acknowledgment xử lý nghiệp vụ như thế nào?

### 8.1. Một pipeline ba cấp độ

```text
Producer                    LinkedTransferQueue            Consumer
  |                                |                          |
  | ------ put(request) ---------> |                          |
  | <----- put returned --------- |                          |
  |       ENQUEUED                 |                          |
  |                                | ---- take() ------------>|
  |                                |      RECEIVED            |
  |                                |                          | process
  |                                |                          | database.commit()
  |                                |                          | DONE
  |
  | ------ transfer(request) ----> |                          |
  |         waits...               | ---- take() ------------>|
  | <----- transfer returns ------ |      RECEIVED            |
  |                                |                          | process
  |                                |                          | DONE
```

`transfer` chỉ thay đổi điểm mà producer **có thể tiếp tục sau khi bên nhận đã nhận phần tử**. Nó không chờ phương thức xử lý nghiệp vụ của consumer trả về.

### 8.2. Khi cần ack processing

Một hướng minh họa dùng future trong payload:

```java
record Job(String requestId, String content,
           CompletableFuture<Boolean> processed) {}

LinkedTransferQueue<Job> queue = new LinkedTransferQueue<>();

// Phía producer:
Job job = new Job("job-123", "payload", new CompletableFuture<>());
queue.transfer(job); // Chờ consumer nhận job.
boolean success = job.processed().get(2, TimeUnit.SECONDS);

// Phía consumer, chạy ở thread khác:
Job incoming = queue.take();
try {
    // Xử lý nghiệp vụ, ví dụ ghi DB đúng giao thức.
    incoming.processed().complete(true);
} catch (RuntimeException failed) {
    incoming.processed().completeExceptionally(failed);
}
```

Đây là **mã minh họa ghép từ hai threads**, không phải class chạy độc lập. Nó cần import `java.util.concurrent.*` và quản lý cancellation, shutdown, timeout, retry rõ ràng. `CompletableFuture.get` còn ném `InterruptedException`, `ExecutionException`, `TimeoutException` nên production phải xử lý chúng.

**Giới hạn:** future ack chỉ tồn tại trong cùng JVM và không tạo durability. Nếu consumer chết sau `take` trước khi complete future, producer có thể timeout. Nếu consumer xử lý DB xong nhưng chết trước khi ack, một retry có thể gây duplicate effects. Muốn đảm bảo mạnh hơn, cần transaction/idempotent consumer hoặc lưu trạng thái xử lý bền vững.

### 8.3. Vì sao không gọi `transfer` là “đã xử lý”?

Một call `take()` return chỉ mới **bàn giao object**. Code consumer có thể:
- Được lên lịch nhưng chưa bắt đầu xử lý.
- Ném exception trong lúc xử lý.
- Bị interrupt hoặc shutdown.
- Đã tạo partial side effects rồi thất bại.
- Xử lý xong nhưng chưa ghi ack.

Không trộn receipt với completion hay durability trong API contract.

## 9. Đợi consumer qua `take` và `poll(timeout)`

### 9.1. `take()`

`take()` là blocking consumer operation: khi queue trống, thread đợi. Với `TransferQueue`, một producer gọi `tryTransfer(e)` có thể match trực tiếp với consumer đang đợi trong `take()`.

### 9.2. `poll()` không đợi

`poll()` trả ngay `null` khi trống. Nếu consumer chỉ thỉnh thoảng gọi `poll()`, `tryTransfer(e)` gọi đúng lúc **không có waiting consumer** sẽ trả `false`. Không phải queue bị hỏng; đúng theo contract.

### 9.3. `poll(timeout, unit)`

Timed `poll` cho consumer chờ phần tử trong giới hạn. Trong thời gian chờ, nó có thể đóng vai trò **waiting consumer** để nhận `tryTransfer`/`transfer`. Nếu hết deadline consumer trả `null`, producer có thể mất khả năng handoff tức thời.

### 9.4. Không dùng `peek` để xác nhận transfer

`peek` xem phần tử nhưng **không loại bỏ**. Producer đang đợi `transfer` không được giải phóng chỉ vì observer vừa `peek` thấy phần tử. Điều kiện đúng là consumer nhận/lấy phần tử theo semantics của queue.

### 9.5. Nhiều consumer

Khi có nhiều consumer, một phần tử chỉ được nhận bởi một consumer trong thao tác dequeue/handoff tương ứng. Nhưng:
- Không giả định một consumer cụ thể được chọn.
- Không suy rằng work sẽ được xử lý theo thứ tự hoàn tất của producers khi nhiều threads concurrent.
- Không suy từ `getWaitingConsumerCount()` rằng một số lượng consumer “đã hứa” nhận công việc.
- Nếu cần routing tới một consumer xác định, dùng cấu trúc queue/channel partition phù hợp.

## 10. Kiểm tra trạng thái waiting consumer không thay thế transfer

`TransferQueue` cung cấp:

```java
boolean hasWaiter = queue.hasWaitingConsumer();
int estimatedWaiters = queue.getWaitingConsumerCount();
```

Hai thông tin này hữu ích cho monitoring/heuristic scheduling nhưng không thể thay cho kết quả `tryTransfer`:

- `hasWaitingConsumer()` biểu diễn trạng thái **tại thời điểm gọi**, có thể thay đổi ngay sau đó.
- `getWaitingConsumerCount()` là **ước lượng**, không thích hợp làm cơ sở kiểm tra chính xác số threads.
- Consumer có thể mới vào `take()` sau khi kiểm tra.
- Một producer khác có thể match consumer ngay giữa lúc check và lúc transfer.

### 10.1. Tránh check-then-act

Sai:

```java
if (queue.hasWaitingConsumer()) {
    queue.transfer(work); // Có thể vẫn block nếu consumer đã đổi.
}
```

Đúng hơn nếu yêu cầu **không được block**:

```java
boolean handedOff = queue.tryTransfer(work);
if (!handedOff) {
    // Trả lỗi / xếp backlog / retry tùy policy.
}
```

Nếu cần **block có giới hạn**:

```java
boolean handedOff = queue.tryTransfer(
        work, 500, TimeUnit.MILLISECONDS);
```

Với các snippets trên, biến `queue`/`work` phải được định nghĩa trong method; xử lý checked `InterruptedException` ở phiên bản có timeout.

### 10.2. Không dùng `size`/`isEmpty` làm ranh giới correctness

`LinkedTransferQueue.size()` cần duyệt các nodes và có thể **không chính xác nếu cấu trúc đang bị thay đổi đồng thời**. `isEmpty()` cũng chỉ phản ánh snapshot. `remainingCapacity()` luôn `Integer.MAX_VALUE` bất kể JVM còn bao nhiêu bộ nhớ thật.

- Metrics: có thể đọc `size` gần đúng để giám sát, chú ý chi phí.
- Correctness: dựa vào kết quả operation, protocol ack và state do ứng dụng quản lý.
- Backpressure: dùng quota/semaphore hoặc queue bounded phù hợp, không dựa vào `size` polling liên tục.

## 11. Backpressure, capacity và khả năng bị kẹt

### 11.1. `LinkedTransferQueue` là unbounded

Nếu producer dùng `put` nhanh hơn consumer, backlog có thể tăng đến lúc JVM cạn bộ nhớ. `remainingCapacity()==Integer.MAX_VALUE` không phải hạn mức bộ nhớ hợp lý.

Muốn giới hạn số công việc pending:
- Dùng queue bounded như `ArrayBlockingQueue`/`LinkedBlockingQueue(capacity)` nếu chỉ cần enqueue.
- Với handoff, dùng quota/semaphore ở tầng app và quản lý cả tasks đang chờ `transfer`.
- Cấu hình producer concurrency, rate limits, deadlines và monitoring.
- Không khóa tất cả worker producer của cùng một executor khi đang chờ consumer mà không còn thread chạy consumer.

### 11.2. `transfer` có thể block vô hạn

`transfer(e)` không có timeout tích hợp. Nếu consumer không bao giờ gọi `take/poll`, producer có thể đợi mãi, trừ khi bị interrupt hoặc một policy bên ngoài xử lý.

Nếu hệ thống cần deadline, ưu tiên `tryTransfer(e, timeout, unit)`. Nếu consumer có thể chết, đừng gọi `transfer` từ một event-loop hoặc thread không thể block.

### 11.3. Handoff không tương đương queue có capacity bằng 0

`SynchronousQueue<E>` là `BlockingQueue` có **zero capacity**, dùng cho handoff trực tiếp giữa producer/consumer. Nó không phải `TransferQueue` interface nhưng `put` trên `SynchronousQueue` chờ bên nhận theo semantics của nó.

`LinkedTransferQueue` khác vì nó **có thể giữ backlog** khi dùng `put/offer`. Có thể kết hợp enqueue và handoff trong cùng implementation.

### 11.4. Tránh deadlock do chạy cùng thread

Không làm:

```java
LinkedTransferQueue<String> queue = new LinkedTransferQueue<>();
queue.transfer("X"); // Chờ bên nhận...
String value = queue.take(); // Không thể tới đây trên cùng thread.
```

Nếu không có consumer khác, thread sẽ không đi qua dòng `transfer`. Trong test, tạo thread consumer riêng và dùng latches/deadlines để xác minh, không dùng `Thread.sleep` để “hy vọng” consumer đã chạy.

## 12. Ví dụ Java 17+ đã biên dịch và chạy thành công

Chương trình `QueueTransferSemanticsDemo.java` minh họa năm nhóm kịch bản:

1. **Enqueue `put/offer`:** chưa có consumer nhưng producer trả về; `take/poll` về sau nhận đúng phần tử.
2. **`tryTransfer` tức thời:** không có consumer thì trả false và không enqueue; khi có consumer đang đợi `take`, trả true và chuyển đúng phần tử.
3. **`transfer` chờ receipt:** producer bắt đầu transfer khi chưa có consumer; phần tử hiện diện trong queue nhưng producer vẫn đợi. Consumer lấy WORK; producer trả về **trước khi consumer được cho phép xử lý nghiệp vụ**, chứng minh receive khác process.
4. **Timed `tryTransfer`:** không có consumer thì timeout/không giữ phần tử; có consumer nhận trong thời hạn thì true.
5. **Interrupt pending `transfer`:** producer đang chờ bị interrupt; nhận `InterruptedException` và phần tử không còn nằm lại queue.

Chương trình dùng `CountDownLatch` để xác nhận thread đã đi tới điểm kiểm thử, `AtomicReference` để truyền lỗi qua threads, `Thread.join` có deadline và một helper `until(...)` với `Thread.onSpinWait()` **chỉ dành cho test** để quan sát trạng thái controlled. Không sao chép vòng spin liên tục vào production. Không cần networking, file I/O hay backend để chạy.

**Lưu toàn bộ đoạn dưới vào file `QueueTransferSemanticsDemo.java`**:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.function.BooleanSupplier;

public final class QueueTransferSemanticsDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static void await(CountDownLatch latch, String label)
            throws InterruptedException {
        check(latch.await(3, TimeUnit.SECONDS), label);
    }

    static void join(Thread thread) throws InterruptedException {
        thread.join(3000);
        if (thread.isAlive()) {
            thread.interrupt();
            throw new AssertionError("Thread did not finish: "
                    + thread.getName());
        }
    }

    static void until(BooleanSupplier predicate, String label) {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
        while (!predicate.getAsBoolean()) {
            if (System.nanoTime() >= deadline) {
                throw new AssertionError(label);
            }
            Thread.onSpinWait(); // For this small deterministic test only.
        }
    }

    static void queuedOfferAndPut() throws Exception {
        LinkedTransferQueue<String> queue = new LinkedTransferQueue<>();
        queue.put("PENDING");
        check(queue.size() == 1, "put should enqueue");
        check(queue.remainingCapacity() == Integer.MAX_VALUE,
                "LinkedTransferQueue is unbounded");
        System.out.println("enqueue.putReturnedWithoutConsumer=true");
        System.out.println("enqueue.elementStillQueued=" + !queue.isEmpty());
        System.out.println("enqueue.take=" + queue.take());

        boolean offered = queue.offer("OFFERED");
        check(offered, "offer should succeed");
        System.out.println("enqueue.offerAccepted=" + offered);
        System.out.println("enqueue.poll=" + queue.poll());
        check(queue.isEmpty(), "enqueue cleanup");
    }

    static void nonblockingTransfer() throws Exception {
        LinkedTransferQueue<String> queue = new LinkedTransferQueue<>();
        boolean missed = queue.tryTransfer("NO_CONSUMER");
        check(!missed && queue.isEmpty(), "no waiting consumer");
        System.out.println("tryTransfer.noConsumer=" + missed);
        System.out.println("tryTransfer.noConsumerRetained=" + !queue.isEmpty());

        CountDownLatch ready = new CountDownLatch(1);
        AtomicReference<String> received = new AtomicReference<>();
        AtomicReference<Throwable> error = new AtomicReference<>();
        Thread consumer = new Thread(() -> {
            ready.countDown();
            try {
                received.set(queue.take());
            } catch (Throwable problem) {
                error.set(problem);
            }
        }, "direct-consumer");
        consumer.start();
        try {
            await(ready, "consumer not ready");
            until(queue::hasWaitingConsumer, "consumer not waiting");
            boolean sent = queue.tryTransfer("DIRECT");
            check(sent, "immediate transfer should match");
            join(consumer);
            check(error.get() == null, "consumer exception");
            check("DIRECT".equals(received.get()), "wrong receipt");
            check(queue.isEmpty(), "direct transfer cleanup");
            System.out.println("tryTransfer.waitingConsumer=" + sent);
            System.out.println("tryTransfer.received=" + received.get());
        } finally {
            consumer.interrupt();
            join(consumer);
        }
    }

    static void blockingHandoff() throws Exception {
        LinkedTransferQueue<String> queue = new LinkedTransferQueue<>();
        CountDownLatch producerStarted = new CountDownLatch(1);
        CountDownLatch producerReturned = new CountDownLatch(1);
        AtomicReference<Throwable> error = new AtomicReference<>();
        Thread producer = new Thread(() -> {
            producerStarted.countDown();
            try {
                queue.transfer("WORK");
            } catch (Throwable problem) {
                error.compareAndSet(null, problem);
            } finally {
                producerReturned.countDown();
            }
        }, "transfer-producer");

        producer.start();
        try {
            await(producerStarted, "producer did not start");
            until(() -> "WORK".equals(queue.peek()),
                    "transfer was not queued");
            check(producerReturned.getCount() == 1L,
                    "transfer returned before receipt");
            System.out.println("transfer.queuedWhileWaiting=true");
            System.out.println("transfer.blockedBeforeTake=true");

            CountDownLatch consumerReceived = new CountDownLatch(1);
            CountDownLatch allowProcessing = new CountDownLatch(1);
            CountDownLatch processed = new CountDownLatch(1);
            AtomicReference<String> value = new AtomicReference<>();
            Thread consumer = new Thread(() -> {
                try {
                    value.set(queue.take());
                    consumerReceived.countDown();
                    if (!allowProcessing.await(3, TimeUnit.SECONDS)) {
                        throw new AssertionError("processing gate timeout");
                    }
                    processed.countDown();
                } catch (Throwable problem) {
                    error.compareAndSet(null, problem);
                    consumerReceived.countDown();
                }
            }, "transfer-consumer");
            consumer.start();
            try {
                await(consumerReceived, "not received");
                await(producerReturned, "producer still blocked");
                check(error.get() == null, "handoff failed: " + error.get());
                check("WORK".equals(value.get()), "wrong work");
                check(processed.getCount() == 1L,
                        "business work was not gated");
                System.out.println("transfer.received=" + value.get());
                System.out.println("transfer.returnedBeforeProcessing=true");
            } finally {
                allowProcessing.countDown();
                join(consumer);
            }
            await(processed, "work not processed");
            check(queue.isEmpty(), "transfer cleanup");
            System.out.println("transfer.processingConfirmed=true");
        } finally {
            producer.interrupt();
            join(producer);
        }
    }

    static void timedTransfer() throws Exception {
        LinkedTransferQueue<String> queue = new LinkedTransferQueue<>();
        boolean noConsumer = queue.tryTransfer(
                "EXPIRE", 100, TimeUnit.MILLISECONDS);
        check(!noConsumer && queue.isEmpty(), "timed timeout");
        System.out.println("timed.noConsumer=" + noConsumer);
        System.out.println("timed.expiredElementRetained=" + !queue.isEmpty());

        CountDownLatch producerStarted = new CountDownLatch(1);
        AtomicBoolean successful = new AtomicBoolean();
        AtomicReference<Throwable> error = new AtomicReference<>();
        Thread producer = new Thread(() -> {
            producerStarted.countDown();
            try {
                successful.set(queue.tryTransfer(
                        "WITH_CONSUMER", 3, TimeUnit.SECONDS));
            } catch (Throwable problem) {
                error.set(problem);
            }
        }, "timed-producer");
        producer.start();
        try {
            await(producerStarted, "timed producer not ready");
            until(() -> "WITH_CONSUMER".equals(queue.peek()),
                    "timed element not visible");
            String received = queue.take();
            join(producer);
            check(error.get() == null, "timed transfer failed");
            check(successful.get() && "WITH_CONSUMER".equals(received),
                    "timed transfer not received");
            System.out.println("timed.withConsumer=" + successful.get());
            System.out.println("timed.received=" + received);
        } finally {
            producer.interrupt();
            join(producer);
        }
    }

    static void interruptedTransfer() throws Exception {
        LinkedTransferQueue<String> queue = new LinkedTransferQueue<>();
        CountDownLatch entered = new CountDownLatch(1);
        AtomicBoolean caught = new AtomicBoolean();
        AtomicReference<Throwable> error = new AtomicReference<>();
        Thread producer = new Thread(() -> {
            entered.countDown();
            try {
                queue.transfer("ABORT");
            } catch (InterruptedException expected) {
                caught.set(true);
                Thread.currentThread().interrupt();
            } catch (Throwable problem) {
                error.set(problem);
            }
        }, "cancelled-producer");
        producer.start();
        try {
            await(entered, "producer not entered");
            until(() -> "ABORT".equals(queue.peek()),
                    "pending transfer not observed");
            producer.interrupt();
            join(producer);
            check(error.get() == null, "unexpected transfer error");
            check(caught.get() && queue.isEmpty(), "interrupt cleanup");
            System.out.println("interrupt.caught=" + caught.get());
            System.out.println("interrupt.elementRetained=" + !queue.isEmpty());
        } finally {
            producer.interrupt();
            join(producer);
        }
    }

    public static void main(String[] args) throws Exception {
        queuedOfferAndPut();
        nonblockingTransfer();
        blockingHandoff();
        timedTransfer();
        interruptedTransfer();
        System.out.println("checks=PASS");
    }
}
```

Biên dịch/chạy trên JDK 17+:

```bash
javac -encoding UTF-8 QueueTransferSemanticsDemo.java
java QueueTransferSemanticsDemo
```

**Stdout chính xác đã được kiểm chứng bằng `javac` và `java`:**

```text
enqueue.putReturnedWithoutConsumer=true
enqueue.elementStillQueued=true
enqueue.take=PENDING
enqueue.offerAccepted=true
enqueue.poll=OFFERED
tryTransfer.noConsumer=false
tryTransfer.noConsumerRetained=false
tryTransfer.waitingConsumer=true
tryTransfer.received=DIRECT
transfer.queuedWhileWaiting=true
transfer.blockedBeforeTake=true
transfer.received=WORK
transfer.returnedBeforeProcessing=true
transfer.processingConfirmed=true
timed.noConsumer=false
timed.expiredElementRetained=false
timed.withConsumer=true
timed.received=WITH_CONSUMER
interrupt.caught=true
interrupt.elementRetained=false
checks=PASS
```

### 12.1. Giải thích `enqueue.*`

`queue.put("PENDING")` trả về khi chưa có consumer, nhưng phần tử vẫn ở trong queue; `queue.take()` sau đó mới nhận nó. `offer("OFFERED")` trả `true`, và `poll()` nhận được OFFERED. Các kết quả này chỉ kiểm tra **chấp nhận đưa vào queue**, không chứng minh có worker xử lý sau đó.

### 12.2. Giải thích `tryTransfer.*`

Khi không có consumer, `tryTransfer("NO_CONSUMER")` trả false và queue vẫn trống. Khi consumer đã chờ trong `take()`, phép transfer tức thời trả true và consumer nhận DIRECT.

Trong **test đã kiểm soát**, chương trình chờ `hasWaitingConsumer` để dựng bối cảnh có waiting consumer. Đó chỉ là cách đồng bộ một bài test có đúng một producer/consumer, **không khuyến nghị code production dùng `hasWaitingConsumer` làm điều kiện correctness** vì có race.

### 12.3. Giải thích `transfer.*`

Producer bắt đầu `transfer("WORK")` trước khi tạo consumer. `peek()` thấy WORK đã được queue lưu tạm nhưng producer vẫn chờ. Khi consumer gọi `take()`, producer được giải phóng, còn consumer **bị giữ ở processing gate**. Chương trình thấy `transfer.returnedBeforeProcessing=true`: đây là bằng chứng thực nghiệm cho sự khác nhau giữa *received* và *processed*. Sau khi mở gate, consumer hoàn tất và test in `processingConfirmed=true`.

### 12.4. Giải thích `timed.*`

Với timed transfer không có receiver, method trả false sau deadline và phần tử EXPIRE không còn trong queue. Trong lần thử khác, producer dùng `tryTransfer("WITH_CONSUMER",3,SECONDS)`; main nhận phần tử trước deadline, producer trả true.

### 12.5. Giải thích `interrupt.*`

Producer gọi `transfer("ABORT")` khi không có receiver, nên chờ. Main gửi interrupt cho producer; code bắt `InterruptedException` và giữ interrupt flag trong thread. Theo contract, phần tử ABORT không bị để lại queue trong nhánh này. Test xác minh `interrupt.elementRetained=false`.

### 12.6. Tại sao bài test dùng `Thread.onSpinWait()`?

Helper `until(...)` liên tục quan sát một điều kiện có **deadline 3 giây**, chỉ để dàn dựng bài test đồng thời có kiểm soát. Đây **không** phải cách thiết kế consumer/producer production; ngoài đời sử dụng blocking queues, condition/event notifications, deadlines và monitoring phù hợp. Không copy vòng spin để polling hàng đợi ở tốc độ cao.

## 13. Các lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Hiểu `put` là consumer đã nhận | Báo delivered quá sớm | Phân biệt enqueue và receive |
| Hiểu `offer=true` là xử lý xong | Mất trạng thái nghiệp vụ | Có processing ack riêng |
| Nghĩ `transfer` đợi business processing | Báo committed dù mới take | Ack qua future/result store/transaction |
| `tryTransfer=false` rồi chờ `poll` lấy e | E chưa từng được enqueue | Fallback rõ ràng nếu cần backlog |
| Nghĩ timed `tryTransfer` hết hạn vẫn giữ e trong queue | Retry/delivery sai | API đảm bảo không để e lại queue khi false |
| Nghĩ `transfer` không bao giờ lưu e trong queue | Nhầm khi `peek` thấy element | E có thể enqueued trong lúc producer đợi |
| Dùng `peek` xác nhận producer đã giao | `peek` không remove/receive | Xem kết quả transfer/take |
| Check `hasWaitingConsumer` rồi gọi transfer | Check-then-act race | Dùng kết quả `tryTransfer` |
| Dùng `getWaitingConsumerCount` làm synchronization | Giá trị ước lượng | Dùng proper handoff protocol |
| Dùng `size` như gauge chính xác | O(n), có thể sai dưới concurrency | Metrics gần đúng; logic từ API results |
| Nghĩ unbounded nghĩa bộ nhớ vô hạn | OutOfMemoryError | Bounded backlog/backpressure |
| Dùng `transfer` trên UI/event-loop | Thread bị block lâu/vô hạn | Timed transfer/async design |
| Producer và consumer cùng thread | Deadlock nếu transfer trước take | Consumer thread riêng |
| Không xử lý `InterruptedException` | Không shutdown sạch | Restore flag và cleanup |
| Timed receive `false` rồi retry tùy tiện | Duplicate nghiệp vụ do nhiều nguồn | Request ID/idempotent consumer |
| Sử dụng `null` làm poison pill | NullPointerException | Sentinel không null với policy rõ |
| Có nhiều consumers nhưng gửi một shutdown token | Một consumer dừng, các consumer khác vẫn chờ | Shutdown protocol cho tất cả workers |
| Đóng producer service khi còn transfer pending | Lỗi, thread leak | Signal/cancel/await đúng owner |
| Coi in-memory queue là durable | Mất task khi JVM crash | Outbox/store/broker nếu cần |
| Catch `Throwable` rồi báo success | Nuốt lỗi nghiêm trọng | Propagate error đúng chính sách |

## 14. Chọn cấu trúc nào trong thực tế?

| Cấu trúc | Đặc trưng | Khi dùng |
| --- | --- | --- |
| `ConcurrentLinkedQueue` | Queue concurrent không blocking consumer `take`, không transfer | Producer/consumer tự điều phối polling hoặc có tín hiệu riêng |
| `ArrayBlockingQueue` | Bounded FIFO queue, `put` có thể block do capacity | Cần backlog cố định, backpressure dung lượng |
| `LinkedBlockingQueue(capacity)` | Bounded nếu truyền capacity, `take/put` | Hàng đợi có giới hạn và blocking retrieval |
| `SynchronousQueue` | Zero-capacity handoff qua `put/take` | Không muốn giữ backlog |
| `LinkedTransferQueue` | Unbounded, vừa enqueue vừa handoff theo `transfer` | Muốn hai semantics trong cùng queue, có giới hạn in-flight ở tầng app |

**Câu hỏi để chọn:**
1. Có cần queue giữ phần tử khi consumer chưa sẵn sàng không?
2. Producer phải chờ **capacity**, chờ **receiver**, hay chờ **processing**?
3. Cần hạn mức memory/backpressure cụ thể không?
4. Yêu cầu durability/retry/exactly-once ở cấp nghiệp vụ thế nào?
5. Có nhiều consumers và cần routing/fairness/ordering đặc biệt không?

Không chọn `LinkedTransferQueue` chỉ vì có tên “Transfer” rồi coi nó tự đáp ứng mọi yêu cầu về reliability.

## 15. Visibility, ordering và tính đúng trong hệ đa luồng

### 15.1. Memory consistency

Java SE 17 mô tả hiệu ứng *happens-before* của concurrent collections: các hành động trong thread producer **trước khi đặt một object vào `LinkedTransferQueue`** happen-before các hành động trong thread consumer **sau khi truy cập hoặc lấy object đó**.

Điều này hỗ trợ publication an toàn của nội dung đã xây dựng trước lúc enqueue/transfer. Tuy nhiên:
- Không biến một object mutable được sửa tiếp đồng thời thành thread-safe.
- Không bảo đảm xử lý nghiệp vụ thành công.
- Không thay thế lock/atomic variables khi có updates đồng thời sau publication.

Ưu tiên truyền những message objects **immutable** (ví dụ Java `record` với các fields phù hợp) để giảm race.

### 15.2. FIFO và concurrency

`LinkedTransferQueue` có semantics thứ tự queue cho các phần tử được enqueue, nhưng trong môi trường nhiều producers/consumers, **thời điểm các lệnh được thực thi đồng thời** có thể interleave. Không đồng nhất thứ tự một producer log “submitted” với thứ tự tất cả consumers hoàn tất business processing.

Nếu bắt buộc duy trì thứ tự theo một aggregate/customer, partition messages theo key hoặc dùng một consumer/serializer cho mỗi partition, thay vì dựa vào một hàng đợi có nhiều workers đồng thời.

### 15.3. Không lặp `size` để đợi empty

`queue.isEmpty()==true` không chứng minh consumer đã hoàn tất processing; phần tử có thể vừa được `take` và worker vẫn đang xử lý. `size()==0` cũng không chứng minh không có producer đang chuẩn bị gửi thêm.

Trong graceful shutdown, cần:
- Ngừng nhận submissions mới.
- Chờ hoặc signal producers đang có `transfer` pending.
- Chờ consumer workers thật sự dừng hoặc nhận ack.
- Xác minh completed/failed tasks qua cơ chế nghiệp vụ.
- Đóng executor do service sở hữu.

## 16. Kiểm thử và QA cho từng mức bảo đảm

### 16.1. Unit/concurrency tests

| Kịch bản | Kết quả nên xác minh |
| --- | --- |
| `put` với không consumer | Trả về; e còn chờ trong queue |
| `offer` với không consumer | Trả true; e có thể `poll` ra sau |
| `tryTransfer` với không consumer | False và không enqueue |
| `tryTransfer` với consumer đang `take` | True; consumer nhận đúng e |
| `transfer` với consumer chưa xuất hiện | Producer chờ receipt |
| Consumer `peek` nhưng chưa take | Producer vẫn chờ |
| Consumer lấy e | `transfer` trả về |
| Consumer lấy nhưng chưa process | `transfer` có thể trả về trước processing |
| Timed transfer không consumer | False, e không còn enqueued |
| Timed transfer có consumer | True và chính e được nhận |
| Interrupted `transfer` khi đang chờ | InterruptedException, e không nằm lại queue |
| Null element | NullPointerException |
| `remainingCapacity` ở LinkedTransferQueue | Integer.MAX_VALUE, không phải memory budget |
| Consumer lỗi sau `take` | `transfer` không báo lỗi business processing |
| Nhiều producers/consumers | Không mất phần tử theo protocol, không giả định processing completion order |
| Shutdown khi producer còn block | Không để thread/element pending bị bỏ quên |

### 16.2. Không dùng `Thread.sleep` để xác nhận đã handoff

Concurrency tests nên dùng `CountDownLatch`, `Future.get(timeout)`, `Thread.join(timeout)` và xác nhận trạng thái có điều kiện. `Thread.sleep(100)` không chứng minh consumer đã vào `take` hoặc producer còn đang chờ. Với bài demo, chỉ dùng `Thread.onSpinWait` có deadline ở những chỗ cần kiểm chứng một trạng thái controlled.

### 16.3. Kiểm thử tải

Ngoài correctness, production cần đo:
- Throughput của enqueue/transfer và `take`.
- Thời gian producer chờ transfer.
- Số producers blocked, số consumers waiting (ước lượng).
- Queue lag, backlog memory, tỷ lệ timeout.
- Tỷ lệ ack processing thành công/thất bại.
- Hành vi khi consumer chết hoặc executor shutdown.
- Khả năng phục hồi nếu service restart/crash.

Không tự diễn giải một benchmark máy đơn làm cam kết hiệu năng chung cho mọi phiên bản JDK hoặc mọi CPU.

## 17. FAQ

**1. `put(e)` trên `LinkedTransferQueue` có đợi bên nhận không?**  
Không. Queue unbounded, `put` thêm phần tử rồi trả về; consumer có thể lấy sau.

**2. `transfer(e)` chờ gì?**  
Chờ một consumer nhận chính e qua thao tác retrieval phù hợp. Không chờ xử lý business logic.

**3. Vì sao tôi thấy e trong queue khi `transfer` chưa trả?**  
Với `LinkedTransferQueue`, nếu chưa có waiting consumer, e có thể được enqueued trong lúc producer chờ.

**4. `tryTransfer(e)` trả false có làm mất một job đã hứa enqueue không?**  
`tryTransfer` vốn không hứa enqueue. False nghĩa không có immediate handoff; e không bị thêm vào queue.

**5. `tryTransfer(e,timeout,unit)` trả false thì e vẫn có thể bị lấy sau không?**  
Theo contract, e **không còn được giữ lại trong queue từ operation ấy** khi timed out. Nếu có nguồn khác gửi cùng nội dung, đó là operation khác.

**6. `transfer` có guarantee xử lý thành công không?**  
Không. Consumer có thể nhận rồi thất bại.

**7. Muốn chờ processing thành công, làm sao?**  
Dùng ack/result future hoặc một store durable, kết hợp timeout, idempotency và failure handling.

**8. `hasWaitingConsumer` có đảm bảo lời gọi `transfer` kế tiếp không block?**  
Không. Đó là snapshot; dùng `tryTransfer` khi cần kết quả không chờ.

**9. `getWaitingConsumerCount` có phải giá trị chính xác tuyệt đối không?**  
Không. Nó là ước lượng trong hệ concurrency.

**10. `remainingCapacity()==Integer.MAX_VALUE` có nghĩa JVM không thể hết memory?**  
Không. `LinkedTransferQueue` unbounded theo logic, vẫn cần backpressure.

**11. Tại sao `SynchronousQueue.put` khác `LinkedTransferQueue.put`?**  
`SynchronousQueue` zero-capacity, yêu cầu bên nhận match; `LinkedTransferQueue` giữ backlog.

**12. Consumer có thể dùng `poll()` thay `take()` không?**  
Có, nhưng `poll()` không block. Nếu không có waiting consumer tại lúc `tryTransfer`, immediate handoff có thể thất bại.

**13. `peek` có đánh thức producer đang `transfer` không?**  
Không; peek không loại bỏ/nhận phần tử.

**14. Interrupted `transfer` có để lại e trong queue không?**  
Theo contract, nếu ném `InterruptedException` trong lúc chờ thì element không bị để lại enqueued.

**15. Có nên retry vô hạn mỗi khi `tryTransfer` false không?**  
Không. Dùng backpressure, deadline, reject hoặc fallback rõ ràng; tránh busy-spin vô tận.

**16. `TransferQueue` có bắt buộc unbounded không?**  
Không. Interface có thể có implementation bounded; `LinkedTransferQueue` cụ thể là unbounded.

**17. `transfer` có durable guarantee qua JVM crash không?**  
Không. Dữ liệu là in-memory object.

**18. Một consumer đã `take` nhưng chưa gọi `processed.complete` thì transfer đã có thể trả chưa?**  
Có. Receive và processed-ack là hai trạng thái độc lập.

## 18. Checklist code review

- [ ] Xác định rõ ứng dụng cần **enqueue**, **receipt** hay **processing ack**.
- [ ] Không dùng `put/offer` để chứng minh consumer đã nhận.
- [ ] Không dùng `transfer` như bằng chứng business processing thành công.
- [ ] `tryTransfer=false` được xử lý, không giả định e đã enqueue.
- [ ] Timed transfer trả false hoặc bị interrupt không để e bị giữ lại queue.
- [ ] Không dùng `hasWaitingConsumer` làm check-then-act bảo đảm handoff.
- [ ] Không dùng `getWaitingConsumerCount` như lock hoặc barrier.
- [ ] Không dùng `size`/`isEmpty` làm bằng chứng toàn bộ job hoàn tất.
- [ ] Không gọi `transfer` trên thread không được phép block.
- [ ] Với queue unbounded, có thiết kế memory quota/backpressure.
- [ ] Consumer dùng `take`/timed `poll` đúng policy.
- [ ] Không truyền `null`.
- [ ] Mỗi request có id nếu có retry/duplicate risks.
- [ ] Nếu cần ack, consumer hoàn tất future sau khi xử lý thật.
- [ ] Xử lý interrupted/timeout/exception của cả producer và consumer.
- [ ] Không giải phóng shared resources chỉ vì queue trống.
- [ ] Shutdown phải xét pending producer transfers và consumer workers.
- [ ] Tests phân biệt đã nhận với đã xử lý.
- [ ] Dùng immutable messages khi có thể.
- [ ] Với durability/exactly-once, xem xét giải pháp lưu bền vững.
- [ ] README và examples dùng API còn hiệu lực trong Java 17+.

## 19. Kết luận và tài liệu chính thức

**Đưa vào hàng đợi** và **transfer tới bên nhận** là hai mốc tiến độ khác nhau của một producer–consumer system:

1. `put(e)`, `offer(e)` trên `LinkedTransferQueue`: **queue đã nhận e**; producer không cần đợi consumer.
2. `transfer(e)`: **producer đợi consumer nhận e**; vẫn chưa bảo đảm consumer xử lý xong.
3. `tryTransfer(e)`: **chuyển ngay nếu đang có waiting consumer**, nếu không trả false mà không enqueue.
4. `tryTransfer(e,timeout,unit)`: **đợi receipt có deadline**; timeout false/interrupt không để e lại queue.
5. `take()` / `poll()`: bên nhận lấy dữ liệu; muốn xác nhận xử lý nghiệp vụ phải dùng **ack riêng**.
6. `LinkedTransferQueue` unbounded: xây dựng **backpressure và lifecycle** thay vì chỉ dựa vào queue capacity.

Nắm rõ ba mốc **ENQUEUED → RECEIVED → PROCESSED** giúp tránh báo thành công quá sớm, tránh producer bị block vô hạn và thiết kế retry đúng khi consumer chưa sẵn sàng. Những API này có từ Java 7 và vẫn còn hiệu lực trong Java 17+.

### Tài liệu chính thức Java SE 17

- [Oracle `TransferQueue<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TransferQueue.html): `transfer`, hai overload `tryTransfer`, waiting consumer hints và contract producer handoff.
- [Oracle `LinkedTransferQueue<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedTransferQueue.html): semantics enqueue/transfer, interrupt, timeout, unbounded capacity, memory consistency.
- [Oracle `BlockingQueue<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): `put`, `take`, `offer`, `poll` và khác biệt capacity.
- [Oracle `SynchronousQueue<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SynchronousQueue.html): zero-capacity handoff.
- [Oracle `ArrayBlockingQueue<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded queue và backpressure theo capacity.
- [Oracle `CompletableFuture<T>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): thiết kế processing acknowledgment trong cùng JVM.
- [Oracle `CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): điều phối bài test concurrency.
