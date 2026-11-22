# 9.1 Phân biệt deadlock, livelock, starvation và thao tác chờ quá lâu

## Mục tiêu học tập

Một dịch vụ Java có thể vẫn chạy, không báo exception nhưng **không hoàn tất công việc**. Người vận hành thường gọi chung đó là “treo”; tuy nhiên bốn cơ chế khác nhau có thể tạo ra triệu chứng tương tự:

- **Deadlock:** nhiều luồng tạo thành chu trình phụ thuộc tài nguyên, không luồng nào trong chu trình tiếp tục được.
- **Livelock:** các luồng vẫn hoạt động, liên tục phản ứng/thử lại nhưng sự tương tác khiến tiến độ hữu ích bằng không.
- **Starvation:** một luồng hoặc một tác vụ liên tục bị thiếu cơ hội sở hữu tài nguyên/được lập lịch, dù những công việc khác vẫn tiến triển.
- **Thao tác chờ quá lâu (long wait):** một lời gọi đang đợi I/O, lock, tín hiệu hoặc kết quả quá lâu so với ngân sách thời gian; có thể do dependency chậm/không phản hồi, **không nhất thiết** có deadlock hay starvation.

Phân loại đúng giúp quyết định phải tìm **chu trình lock**, **retry loop**, **tính công bằng của tài nguyên/queue**, hay **deadline/đường phụ thuộc bên ngoài**, thay vì cứ tăng số thread, ép GC hoặc restart không có chứng cứ.

Sau bài, bạn có thể:

1. Định nghĩa và phân biệt bốn hiện tượng theo **progress**, trạng thái luồng, lock ownership, CPU, queue và timeout.
2. Đọc thread dumps nhiều thời điểm, phân biệt `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`; hiểu vì sao các state này **không phải chẩn đoán hoàn chỉnh**.
3. Dùng `ThreadMXBean`, `ThreadInfo`, `findMonitorDeadlockedThreads()` và `findDeadlockedThreads()` đúng phạm vi; nhận ra giới hạn đối với các phụ thuộc ngoài JVM.
4. Thu thập các số đo như completed jobs, retries, per-thread CPU delta, lock owner, queue waiting age, downstream latency để kiểm chứng giả thuyết.
5. Thực hành các tình huống Java 17+ được **giới hạn thời gian** trong một chương trình lab; giữ riêng ví dụ deadlock có chủ đích khỏi ứng dụng thật.
6. Thiết kế biện pháp phòng ngừa: lock ordering, giảm vùng giữ khóa, backoff có jitter, bounded queues, fairness khi cần, timeout/deadline, cancellation và giám sát progress.
7. Viết kết luận chẩn đoán với phạm vi bằng chứng và giới hạn, tránh đồng nhất “không phát hiện deadlock” với “không có vấn đề”.

## 1. Trước hết hãy định nghĩa “tiến độ”

Không nên dùng “CPU cao”, “CPU thấp”, “thread đang WAITING” hoặc “ứng dụng chưa chết” như thước đo duy nhất. Một hệ thống có thể xử lý nhiều vòng lặp nhưng không hoàn tất transaction nào; một worker có thể đứng yên trong khi các worker khác hoàn thành việc; một lời gọi chờ 30 giây có thể hợp lệ với báo cáo batch nhưng là lỗi với API có SLO 300 ms.

**Tiến độ hữu ích** phải đo theo nghiệp vụ, ví dụ:

- Số request được **hoàn tất** và trả response, không chỉ số request được nhận.
- Số job **acknowledged/committed**, không chỉ số lần được dequeue.
- Số bản ghi thực sự xử lý thành công, không chỉ số retry attempts.
- Queue oldest-item age có giảm không, không chỉ queue length biến động.
- Một task cụ thể đã chuyển sang trạng thái hoàn tất/thất bại/canceled chưa.
- Độ trễ end-to-end so với deadline, không chỉ một method nội bộ chạy nhanh.

Ví dụ:

```text
14:00:00  requestsReceived=1000  requestsCompleted=980
14:00:10  requestsReceived=1100  requestsCompleted=980
14:00:20  requestsReceived=1200  requestsCompleted=980
```

Trong 20 giây, 200 requests mới vào nhưng **không thêm request nào hoàn tất**. Đây là một tín hiệu “progress bị mất”, chưa xác định được deadlock, livelock, starvation hay downstream wait. Cần thêm thread dumps, queue/lock metrics và dependency traces.

### 1.1 “Ứng dụng treo” có nhiều phạm vi

- Một **thread** bị chặn, nhưng những thread khác vẫn phục vụ bình thường.
- Một **thread pool** hết khả năng xử lý do workers bị chiếm bởi tác vụ chờ.
- Một **component** (payment/cache/message consumer) dừng progress nhưng health endpoint vẫn trả OK.
- **Toàn process** không phản hồi, có thể do CPU saturation, safepoints, lock, GC, native I/O hoặc lỗi khác.
- **Cả hệ thống phân tán** bị nghẽn vì dependency, rate limit hoặc chu trình RPC giữa các dịch vụ.

Điều tra phải chỉ rõ phạm vi trước khi suy ra nguyên nhân.

## 2. So sánh nhanh bốn hiện tượng

| Tiêu chí | Deadlock | Livelock | Starvation | Chờ quá lâu |
| --- | --- | --- | --- | --- |
| Cơ chế chính | Chu trình chờ tài nguyên/khóa | Liên tục phản ứng, nhường/đổi trạng thái nhưng không xong việc | Một bên không được cấp cơ hội tài nguyên | Đợi điều kiện/sự kiện/dependency vượt ngân sách |
| Có hoạt động? | Các bên trong chu trình thường bị block/park | **Có**; retry/yield/backoff lặp | Bên bị thiếu cơ hội có thể đứng chờ, bên khác vẫn chạy | Thường ít hoạt động ở bên đang chờ, nhưng không bắt buộc |
| Tiến độ hữu ích | Bằng 0 cho các bên trong cycle | Bằng 0 hoặc gần 0 dù attempts tăng | Bên bị thiệt hại tiến độ bằng 0; bên khác có thể hoàn tất | Không có tiến độ cho operation đang chờ; các operation khác có thể hoàn tất |
| Có chu trình lock ownership? | Thường có nếu là lock deadlock; có thể là chu trình phụ thuộc logic ngoài lock | Không bắt buộc | Không bắt buộc | Không bắt buộc |
| CPU | Thường thấp ở threads bị block; không quy luật toàn process | Có thể cao nếu retry dày; có thể thấp khi backoff | Không có mẫu CPU cố định | Thường thấp khi blocked I/O/park, nhưng JVM state tùy API |
| Thread dump | `BLOCKED`, `WAITING` hoặc `TIMED_WAITING` tùy lock/synchronizer | Stack thay đổi hoặc cùng đoạn retry; có thể `RUNNABLE`/`TIMED_WAITING` | Victim chờ lock hoặc **chưa được executor chạy**, nên không hiện như một executing thread | I/O, `Future.get`, `CountDownLatch.await`, `wait`, `park`, lock… |
| Hướng giải quyết | Phá circular wait, lock ordering, giảm lock nesting | Randomized/exponential backoff, ưu tiên rõ, tránh đối xứng gây va chạm | Fairness phù hợp, scheduling/queue isolation, giảm độc chiếm | Deadline/timeout, propagate cancel, xử lý dependency và resource leak |

**Cảnh báo:** bảng trình bày dấu hiệu thường gặp, không phải phép phân loại bằng một chỉ số đơn lẻ. Deadlock logic giữa hai `Future` có thể làm worker `WAITING` nhưng không được `ThreadMXBean.findDeadlockedThreads()` nhận diện. Livelock có thể có `Thread.sleep()` và CPU thấp. Starvation của task đang ở queue thậm chí **không có stack trace riêng của task**, vì nó chưa được worker chạy.

## 3. Deadlock: chu trình chờ khóa hoặc tài nguyên

### 3.1 Cơ chế

Giả sử hai luồng đi qua cùng hai monitors theo thứ tự trái ngược:

```text
Thread A giữ Lock X, muốn lấy Lock Y
Thread B giữ Lock Y, muốn lấy Lock X

A --đợi Y đang do B giữ--> B
^                          |
|----đợi X do A giữ--------|
```

Nếu cả hai chỉ buông khóa khi đã lấy được khóa còn lại, không ai tiến lên. Đây là **deadlock kiểu monitor**.

Một mô hình phổ biến để hiểu điều kiện cần của deadlock tài nguyên là bốn điều kiện Coffman:

1. **Mutual exclusion:** tài nguyên chỉ một bên sử dụng tại một thời điểm.
2. **Hold and wait:** giữ tài nguyên này trong khi chờ tài nguyên khác.
3. **No preemption:** tài nguyên không bị thu hồi cưỡng bức theo cách an toàn.
4. **Circular wait:** tồn tại chu trình chờ sở hữu.

Phá một điều kiện phù hợp có thể ngăn thiết kế rơi vào deadlock, ví dụ quy định thứ tự lấy khóa nhất quán. Đây là mô hình giải thích, không phải checklist chứng minh mọi tình huống “treo” đều do locks.

### 3.2 Deadlock Java không chỉ là `synchronized`

Có ít nhất ba lớp cần phân biệt:

**Intrinsic monitor deadlock:** xảy ra với `synchronized` và object monitors; `ThreadMXBean.findMonitorDeadlockedThreads()` được thiết kế để nhận diện chu trình monitor này.

**Ownable synchronizer deadlock:** ví dụ các `ReentrantLock` do những thread sở hữu và chờ lẫn nhau. `ThreadMXBean.findDeadlockedThreads()` có thể tìm chu trình với object monitors **và ownable synchronizers** khi VM hỗ trợ giám sát loại này. Kiểm tra `isSynchronizerUsageSupported()` và handling `UnsupportedOperationException`.

**Logical/distributed deadlock:** worker trong single-thread executor chờ `Future.get()` của một job khác nằm **sau** nó trong cùng queue; hoặc dịch vụ A gọi B đồng bộ và B lại chờ A. Đây có thể là một chu trình phụ thuộc không được thể hiện như monitor/ownable synchronizer cycle trong JVM. Hai API deadlock ở trên **không bảo đảm phát hiện**.

Ví dụ dependency deadlock trong executor:

```java
// Đoạn minh họa phản-pattern, KHÔNG chạy nguyên trạng.
// Executor chỉ có một worker; task ngoài đang đợi task trong,
// nhưng task trong chỉ có thể chạy khi worker hiện tại nhả ra.
Future<?> outer = singleThreadExecutor.submit(() -> {
    Future<?> inner =
            singleThreadExecutor.submit(() -> doWork());
    inner.get(); // cần xử lý checked exceptions; có thể chờ mãi
});
```

Đây **không phải chương trình Java độc lập**, vì `doWork()` và biến executor là placeholder mô tả ý tưởng. Về thiết kế, không làm block một worker lên công việc cần chính worker đó thực thi. Trong sản phẩm thực, sử dụng dependency graph không có cycle, async composition phù hợp, hoặc tách pool/tiền xử lý và deadlines.

### 3.3 Triệu chứng và cách thu chứng cứ

Một monitor deadlock thường có:

- Hai hay nhiều thread `BLOCKED` khi chờ monitors.
- Mỗi thread giữ monitor mà thread khác đang đợi.
- Thread dumps lấy cách nhau vẫn cho thấy cùng chu trình.
- Completed request/job có thể dừng cho những đường nghiệp vụ liên quan.
- `findMonitorDeadlockedThreads()` có thể trả array thread IDs của cycle.

Tuy nhiên, **không có deadlock result** không chứng minh tất cả hệ thống không bị treo: có thể JVM khác, dependency ngoài JVM, loại tài nguyên không được giám sát, hoặc sự cố không tồn tại đúng thời điểm lấy mẫu.

### 3.4 Phòng ngừa

- **Global lock ordering:** mọi đường code lấy X rồi Y, không có nơi lấy Y rồi X.
- Giảm số locks giữ cùng lúc và thời gian giữ khóa.
- Không giữ monitor trong lúc gọi network/DB hoặc chờ `Future.get()` không deadline.
- Với `Lock`, cân nhắc `tryLock(timeout, TimeUnit)` khi semantic cho phép; nếu không lấy được phải **thả mọi khóa đã lấy** trong `finally`, không retry nóng.
- Dùng immutable data, concurrent collections, single-writer design hoặc message passing khi phù hợp.
- Kiểm thử concurrency dưới tải và dùng lock graph / thread dumps/JFR/metrics làm bằng chứng.

Đối với `synchronized`, một thread đang `BLOCKED` chờ lấy monitor **không tự thoát khi `interrupt()`** như lời gọi `lockInterruptibly()`; không coi interrupt là “thuốc giải” deadlock monitor. `Thread.stop()` không an toàn và không phải cách giải quyết được chấp nhận.

## 4. Livelock: các luồng vẫn hoạt động nhưng không làm xong việc

### 4.1 Cơ chế

Hai “người lịch sự” cùng nhường đường:

```text
Vòng 1: A thấy B muốn đi → A nhường
        B thấy A muốn đi → B nhường
Vòng 2: cả hai thử lại cùng lúc → cả hai lại nhường
Vòng 3: lặp lại cùng cách → không ai qua được
```

Tương tự trong Java: hai workers phát hiện xung đột, cùng rollback, cùng retry ngay, rồi đụng nhau lần nữa vì **chiến lược đối xứng**. Các threads có thể tiêu thụ CPU, phát log, tăng retry counter, đổi trạng thái qua lại nhưng **completed work = 0**.

Livelock khác deadlock ở chỗ hệ thống **không chỉ đứng chờ một lock bất động**; các bên tích cực làm việc hoặc phản ứng và chính cơ chế tương tác ngăn tiến độ hữu ích.

### 4.2 Dấu hiệu

- Retry/attempt counter tăng rất nhanh, completion/commit rate không tăng tương ứng.
- CPU có thể cao do busy retry; hoặc thấp nếu mỗi lần retry đều sleep/backoff.
- Stacks chụp ở nhiều thời điểm có thể dao động qua retry, conflict check, release/reacquire.
- Log có nhiều thông điệp “conflict, retry”, “CAS failed”, “optimistic lock failure” hay “temporary unavailable”.
- Không nhất thiết có chu trình monitor để `ThreadMXBean` báo deadlock.

**Lưu ý:** một retry loop với nhiều lần thất bại **không tự động là livelock**. Có thể upstream thật sự trả lỗi liên tục; khi đó căn nguyên là dependency thất bại, còn retry không kiểm soát là yếu tố làm nghiêm trọng thêm. Cần phân tích quan hệ giữa các actors và nguyên nhân attempts không tạo progress.

### 4.3 Chống livelock

- **Exponential backoff với jitter**: hai actors không thử lại theo nhịp đồng bộ mãi mãi.
- Giới hạn retry attempts / retry budget / deadline và đưa thất bại ra đường báo lỗi có thể xử lý.
- Dùng một quy tắc ưu tiên hoặc conflict resolution xác định, tránh cả hai nhường nhau vô hạn.
- Với tài nguyên có lock, cân nhắc lock ordering hoặc handoff protocol.
- Khi có optimistic concurrency, chỉ retry nếu khả năng thành công thay đổi; không busy spin vô hạn trên cùng phiên bản dữ liệu.
- Đo **successful commits per second** bên cạnh attempts per second; đừng lấy “nhiều activity” làm dấu hiệu khỏe.

Jitter chỉ **giảm xác suất** va chạm đồng pha trong nhiều mô hình; nó không phải một chứng minh toán học rằng mọi livelock đã được loại bỏ.

## 5. Starvation: một tác vụ không được cấp cơ hội

### 5.1 Cơ chế

Một worker/task có thể phải đợi rất lâu vì bên khác liên tục được chọn để chạy hoặc sử dụng tài nguyên:

- Khóa **unfair** có thể bị các contenders khác giành liên tiếp, một waiter không được chọn.
- Thread pool nhỏ bị các long-running tasks chiếm hết; các tasks phía sau bị chờ trong queue.
- Hệ thống ưu tiên cao liên tục có việc, tác vụ ưu tiên thấp không bao giờ có “slot”.
- Semaphore/connection pool bị độc chiếm hoặc return chậm làm một nhóm requests luôn thiếu tài nguyên.
- Scheduling policy/cgroup CPU throttling và cạnh tranh OS làm một số threads không có đủ thời gian chạy, nhưng không thể kết luận starvation chỉ từ CPU thấp.

**Đặc trưng phân biệt:** những tác vụ **khác vẫn có thể hoàn tất**, trong khi một nạn nhân đợi không có giới hạn hoặc không nhận phần tài nguyên cần thiết.

### 5.2 Starvation khác queue wait bình thường

Một queue có 100 jobs, mỗi worker mất 1 giây/job, sẽ có thời gian chờ hợp lệ nếu workload tới nhanh và vẫn đạt fairness. Không phải bất cứ queued job nào cũng “bị starvation”.

Để chứng minh starvation có ích, cần quan sát:

- **Oldest queued item age** tăng liên tục mặc dù hệ thống vẫn hoàn thành các job khác.
- Per-task wait time/tail latency lớn hơn deadline/SLO nhiều lần.
- Một số nhóm task bị trì hoãn có hệ thống, trong khi nhóm ưu tiên khác liên tục chiếm slot.
- Lock/semaphore acquisition distribution lệch hoặc một bên liên tục thất bại.
- Queue có chính sách ưu tiên/barging và thiếu aging/fairness.
- Có thể dùng thread dumps để nhận diện workers đang bận; nhưng một task **chưa được chạy** không nhất thiết có `Thread` riêng để xuất stack.

### 5.3 Tránh starvation

- Chọn **fair scheduling** ở đúng nơi cần thiết; một `ReentrantLock(true)` có chính sách ưu tiên lock lâu chờ khi tranh chấp, nhưng **không cam kết fairness tuyệt đối của OS scheduling**, và có thể giảm throughput.
- Tách pool cho việc dài/blocking khỏi pool xử lý request ngắn.
- Đặt queue capacity có giới hạn, backpressure và admission control thay vì tăng queue vô hạn.
- Dùng aging trong priority queue nếu domain cho phép; tránh để công việc ưu tiên thấp bị loại vĩnh viễn.
- Thiết lập deadline cho thời gian ở queue, không chỉ timeout khi task đã bắt đầu.
- Theo dõi queue age theo class/priority, số tác vụ chưa có cơ hội chạy và tỷ lệ hoàn tất.
- Không biến việc nạn nhân được chạy **một lần** sau vài phút thành bằng chứng scheduling đã công bằng.

Một pool single-thread có task A đang chờ vô hạn và task B xếp phía sau là minh họa **task starvation/queue starvation risk**; đó có thể là kết quả của một long wait ban đầu. Một incident thực có thể đồng thời có **nhiều cơ chế** và chúng cần được phân tích theo quan hệ nhân quả.

## 6. Thao tác chờ quá lâu: không tự đồng nghĩa deadlock

### 6.1 Những kiểu chờ

- `Future.get()` không timeout chờ task/dependency.
- `CountDownLatch.await()` chờ một signal mà đường tạo signal đã lỗi.
- `BlockingQueue.take()` chờ message trong khi producer đã dừng.
- `Object.wait()` hoặc `Condition.await()` chờ notification.
- Socket/JDBC/RPC read chờ server/downstream, có thể thiếu read/query timeout hoặc deadline.
- `Thread.join()` chờ thread khác kết thúc.
- `LockSupport.park()` chờ unpark/interrupt/event; **`WAITING` không nói lý do nghiệp vụ**.
- `ReentrantLock.lock()` chờ lock do thread khác giữ quá lâu.
- DNS/connect/SSL handshake, filesystem/network I/O có cơ chế timeout riêng.

Một operation chờ 20 giây có thể **hoàn toàn đúng** với một job chờ batch window, nhưng không đúng với request có deadline 2 giây. Không có cách phân loại “long wait” chỉ bằng threshold tuyệt đối chung cho mọi loại công việc.

### 6.2 Chờ hữu hạn và vô hạn

```java
// Đoạn minh họa tích hợp:
String value = future.get(250, TimeUnit.MILLISECONDS);
```

`Future.get(timeout, unit)` báo `TimeoutException` khi hết ngân sách chờ mà kết quả chưa có. **Nó không tự đảm bảo task nền đã dừng.** Phải thiết kế cancellation, signal/interrupt, thời gian I/O ở tầng dưới và đường cleanup, đồng thời xử lý `InterruptedException` có chủ đích.

Các API với timeout khác nhau không nhất thiết cùng điều kiện: `socket.setSoTimeout(...)` ảnh hưởng socket read phù hợp, JDBC driver/query timeout có semantics riêng, gRPC/HTTP client có deadline/connect/read/overall timeouts tùy thư viện. Khi end-to-end request có 500 ms, không nên lần lượt cho 5 dependencies mỗi bên 500 ms mà không truyền **remaining deadline**.

### 6.3 Chờ lâu nhưng không có deadlock

Ví dụ service A chờ một HTTP response từ server đang bảo trì. Thread A có thể bị chặn trong socket read; nó không giữ một monitor mà service B đang chờ để tạo chu trình. `findDeadlockedThreads()` hợp lệ trả `null`. Đây là một **unbounded or overdue wait**, không phải chứng cứ deadlock.

Ngược lại, một worker trong single-thread executor chờ future của task bị queued phía sau tạo **dependency cycle**, có thể gọi là logical deadlock, dù monitor deadlock detector không thấy. Vậy “chờ quá lâu” là **triệu chứng ở cấp operation**, có thể là cơ chế độc lập hoặc hậu quả của deadlock/starvation.

### 6.4 Phòng ngừa

- Quy định deadline end-to-end và timeout từng công đoạn.
- Propagate remaining time budget qua các lớp và dependencies.
- Hạn chế số blocking calls trong pools nhỏ; ưu tiên async composition khi phù hợp.
- Dùng interruptible waits/locks khi API và semantics cho phép, cùng cleanup trong `finally`.
- Không retry vô hạn sau timeout; kết hợp backoff, circuit breaker, retry budget và idempotency.
- Phân biệt timeout của **caller** với dừng thực sự của **remote work**; cần cancellation protocol nếu có.
- Theo dõi latency của từng dependency và oldest in-flight age.

## 7. Đọc thread state đúng cách

Java 17 có `Thread.State` với các trạng thái `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, `TERMINATED`. Đây là các trạng thái JVM, **không phải ánh xạ một-một sang OS process/thread states**.

| State | Ý nghĩa chuẩn | Điều không được kết luận vội |
| --- | --- | --- |
| `RUNNABLE` | Thread đang thực thi trong JVM hoặc ở trạng thái runnable; có thể đợi tài nguyên OS như CPU | “Chắc chắn đang dùng 100% CPU” |
| `BLOCKED` | Chờ lấy intrinsic monitor để vào/reenter `synchronized` | “Chắc chắn deadlock” |
| `WAITING` | Chờ không thời hạn cho một hành động/tín hiệu khác; có thể `Object.wait`, `join`, `park` | “Chắc chắn bị lỗi” |
| `TIMED_WAITING` | Chờ có giới hạn theo API, sleep/timed wait/park | “Chắc chắn sẽ có progress trước deadline nghiệp vụ” |
| `TERMINATED` | Thread đã kết thúc | “Có thể lấy stack của thread đó từ getAllThreadIds” |

**Đặc biệt:** nhiều thread trong một pool có `WAITING` khi queue **trống** là bình thường. Thread `RUNNABLE` trong native socket read/OS wait không tự chứng minh CPU busy. Một thread ở `BLOCKED` vài mili giây là contention có thể bình thường.

Với `ReentrantLock` hoặc `Condition`, phần chờ thường đi qua cơ chế park/AQS và có thể hiện dưới `WAITING`/`TIMED_WAITING`, không nhất thiết `BLOCKED`. Cần xem **stack, lock owner và tài nguyên đang chờ**, không chỉ state.

## 8. Thread dump: chụp gì và đọc như thế nào?

### 8.1 Thu dữ liệu từ đúng JVM

Ví dụ với HotSpot JDK 17+ và JVM bạn có quyền quản lý:

```bash
jcmd -l
jcmd <PID> Thread.print -l
```

`<PID>` là **ký hiệu cần thay bằng PID số thật**, không phải text gõ nguyên văn. `jcmd -l` có thể không thấy JVM ở container/PID namespace khác. Với môi trường container, xác nhận đúng pod/container, PID namespace, effective user, image có JDK tools hay không, và start time của JVM.

`Thread.print -l` cung cấp stack traces và thông tin locks theo JVM/phiên bản; nó có chi phí, có thể làm tăng latency trên hệ thống nhiều threads. Nếu không chắc option, gọi `jcmd <PID> help Thread.print`.

**Không dùng một mẫu duy nhất:** chọn 3–5 mốc có timestamp (ví dụ cách nhau 2–5 giây) khi trạng thái hệ thống cho phép. Thời lượng và số lượng phải phù hợp workload, tránh script dump dày liên tục làm sự cố nặng thêm.

Một ví dụ lịch lấy mẫu:

```text
T0: ghi p99, completed rate, queue depth/age, CPU/GC
T1: thread dump #1
T2: thread dump #2
T3: thread dump #3
T4: so stack/owner/retry/queue age và ghi tác động của việc thu thập
```

Đây là **cấu trúc minh họa**, không phải kết quả đã đo của JVM.

### 8.2 Những phần cần đọc trong dump

1. Thread name và ID (gắn với đúng JVM/instance).
2. Thread state.
3. Stack frame trên cùng và call path, đặc biệt `synchronized`, `LockSupport.park`, `FutureTask.get`, `ThreadPoolExecutor.getTask`, socket reads, database client.
4. Lock **đang chờ** (`waiting to lock`, `parking to wait for`) và lock **đang giữ**.
5. Owner của lock; theo dõi chu trình `A → B → A` nếu có.
6. Thread hiện giữ lock có đang làm I/O dưới lock không?
7. Các thay đổi qua nhiều mẫu: stack có lặp một vòng retry không? owner có đổi không? request completions có tăng không?
8. Liên hệ với request/trace ID nếu có; tên thread pool không luôn bằng ID nghiệp vụ.

**Một thread dump phản ánh thời điểm chụp**, không phải thời gian nó đã chờ trong trạng thái đó. Để biết “wait kéo dài bao lâu”, cần timestamp, logging instrumentation, duration metrics, multiple samples, hoặc contention monitoring phù hợp.

## 9. ThreadMXBean: deadlock detector có phạm vi giới hạn

Trong Java 17:

```java
ThreadMXBean mx = ManagementFactory.getThreadMXBean();
long[] monitors = mx.findMonitorDeadlockedThreads();
```

**`findMonitorDeadlockedThreads()`** tìm cycle của threads chờ giành **object monitors** (thường liên quan `synchronized`). Kết quả là `long[]` thread IDs hoặc `null` nếu không tìm thấy.

```java
if (mx.isSynchronizerUsageSupported()) {
    long[] broader = mx.findDeadlockedThreads();
}
```

**`findDeadlockedThreads()`** bao gồm chu trình chờ **object monitors và ownable synchronizers** khi được JVM hỗ trợ; có thể ném `UnsupportedOperationException` nếu VM không hỗ trợ giám sát ownable synchronizer.

Đây là **hai đoạn mã tích hợp**, cần `import java.lang.management.*` và phần xử lý lỗi phù hợp.

| API | Dữ liệu dùng được | Giới hạn |
| --- | --- | --- |
| `findMonitorDeadlockedThreads()` | Các thread thuộc monitor deadlock cycle | Không phát hiện mọi lock/dependency khác |
| `findDeadlockedThreads()` | Object monitors + ownable synchronizers | Phụ thuộc support; không bao quát mọi kiểu chờ |
| `getThreadInfo(ids, maxDepth)` | Stack, state, lock owner tại thời điểm lấy mẫu | Có thể trả `null` cho thread đã chết; snapshot |
| `getThreadCpuTime(id)` | CPU time tích lũy nếu supported/enabled | `-1` khi không có số liệu; dùng delta, không dùng giá trị lifetime |
| Contention monitoring | Blocked/waited counts/time | Time chỉ có khi feature hỗ trợ và đã bật; có overhead |

### 9.1 `null` không đồng nghĩa “hệ thống không có deadlock”

`findDeadlockedThreads()==null` có nghĩa **không phát hiện cycle thuộc phạm vi API tại thời điểm gọi**. Nó không loại trừ:

- Logical deadlock trên `Future`, queue, latch, callback.
- Network/DB/resource deadlock ở process khác.
- Livelock và starvation.
- Chờ quá lâu mà không có cycle.
- Deadlock thoáng qua đã thay đổi trạng thái trước lần chụp.
- Phạm vi ngoài loại synchronizer mà API giám sát.

Trong các JDK mới có virtual threads, cần đối chiếu khả năng giám sát/công cụ đúng JDK: `ThreadMXBean` không phải profiler toàn diện mọi virtual thread. Bài thực hành nhắm **Java 17 platform threads**.

### 9.2 ThreadInfo lock owner và stack

Với IDs đã được phát hiện:

```java
ThreadInfo[] infos = mx.getThreadInfo(ids, 32);
for (ThreadInfo info : infos) {
    if (info != null) {
        System.out.println(info.getThreadName()
                + " state=" + info.getThreadState()
                + " waitingFor=" + info.getLockName()
                + " owner=" + info.getLockOwnerName());
    }
}
```

Đây là **mã minh họa tích hợp**; cần `ids` lấy từ API detector và import `ThreadInfo`. Khi cần locks đang được giữ, xem overload `getThreadInfo(ids, lockedMonitors, lockedSynchronizers)` nhưng kiểm tra `isObjectMonitorUsageSupported()`/`isSynchronizerUsageSupported()` tương ứng và cân nhắc chi phí.

Không dùng các method chẩn đoán này để **điều khiển thứ tự khóa** trong ứng dụng. Chúng dành cho troubleshooting/management, kết quả có thể biến động ngay sau snapshot.

## 10. CPU, retry và metrics: tín hiệu xác định loại hiện tượng

Một sự cố chỉ có `requestCompleted=0` và CPU thấp là chưa đủ. Đặt các tín hiệu cạnh nhau:

| Tín hiệu trong cửa sổ | Deadlock | Livelock | Starvation | Long wait |
| --- | --- | --- | --- | --- |
| Completed work của nhóm bị ảnh hưởng | Dừng | Dừng/gần 0 | Victim dừng, nhóm khác có thể tiếp tục | Operation chờ dừng |
| Retry/attempt counters | Không nhất thiết tăng | **Thường tăng** | Có thể tăng nếu bị từ chối tài nguyên | Có thể giữ nguyên hoặc retry tùy tầng gọi |
| Thread CPU delta | Threads blocked có thể thấp | Có thể cao (busy retry) hoặc thấp (backoff) | Victim thấp; contender có thể cao | Thường thấp ở operation đang đợi |
| Lock cycle evidence | Có với lock deadlock | Không bắt buộc | Không bắt buộc | Không bắt buộc |
| Queue oldest-item age | Có thể tăng do workers dừng | Có thể tăng | **Rất hữu ích** để nhận victim bị bỏ đói | Có thể tăng nếu workers đang chờ |
| Dependency latency | Phụ thuộc tình huống | Có thể liên quan conflict | Có thể liên quan pool contention | **Trọng tâm** khi chờ I/O |
| Thread stacks qua nhiều mẫu | Owner cycle ổn định | Retry path/active transition | Victim wait/queue, others progress | Một wait call, latency/timer/dependency |

### 10.1 Tính CPU theo hai thời điểm

`ThreadMXBean.getThreadCpuTime(id)` trả CPU time tích lũy **nanoseconds** khi được hỗ trợ và bật. Một ví dụ:

```text
T1: threadCpuNs=8_000_000_000
T2: threadCpuNs=8_150_000_000
elapsedWallNs=500_000_000
deltaCpuNs=150_000_000
CPU share tương đương một logical CPU = 150/500 * 100 = 30%
```

Tỷ lệ này **không** phải 30% toàn node nhiều cores; cần khai báo mẫu số nếu muốn so với CPU container/quota. Kiểm tra `isThreadCpuTimeSupported()`, `isThreadCpuTimeEnabled()`; `-1` nghĩa là không có giá trị hợp lệ, không phải 0. Khi thread đã chết hoặc ID đổi, không trộn counters từ hai thread khác nhau.

### 10.2 Contention time không đo mọi loại chờ

`ThreadInfo.getBlockedTime()` phản ánh thời gian blocked do monitor contention khi monitoring được bật; `getWaitedTime()` phản ánh thời gian chờ theo ngữ nghĩa API, không phải “mọi thời gian socket read”. Nếu feature bị tắt, time có thể là `-1`. Bật monitoring trên production là **thay đổi trạng thái chẩn đoán**, có overhead, cần ghi thời điểm.

Một worker chờ `Future.get()` hoặc network có thể không có blocked time cao. Không dùng `getBlockedTime()==0` để phủ định latency hoặc starvation.

## 11. Thực hành Java 17: một chương trình an toàn theo từng mode

Chương trình **`HangPatternsLab.java`** có các mode:

- `fixture`: chỉ in một bảng tóm tắt cố định, stdout **chính xác**.
- `deadlock`: cố tình tạo **monitor deadlock** giữa **hai daemon threads trong JVM lab riêng**, rồi dùng `ThreadMXBean` tìm chúng; không đợi join các threads đã deadlock.
- `livelock`: mô phỏng **hai actors liên tục cùng thấy xung đột rồi cùng nhường** trong số vòng hữu hạn. Chúng hoạt động/retry nhưng không có tiến độ nghiệp vụ; đây là mô phỏng chiến lược livelock, không phải thuật toán lock sản xuất.
- `starvation`: một single-thread executor bị task đầu giữ chỗ, task sau ở queue không được chạy trước khi release; đây là mô phỏng **queue starvation risk**, không chứng minh hệ thống luôn starvation vô hạn.
- `longwait`: một `CompletableFuture` chưa bao giờ được complete, `get` có timeout; mô phỏng một operation chờ event không đến trong deadline.

**Chỉ chạy các mode trên tiến trình lab mà bạn sở hữu.** Chế độ `deadlock` cố ý tạo cycle và không dành cho một server ứng dụng. Các mode khác không gửi request ra mạng hoặc thao tác vào JVM khác.

Tạo file `HangPatternsLab.java`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.atomic.AtomicInteger;

public class HangPatternsLab {
    static void fixture() {
        System.out.println("deadlock: circular lock wait, no progress");
        System.out.println("livelock: active retries, no progress");
        System.out.println("starvation: victim denied execution opportunities");
        System.out.println("longwait: external event absent before deadline");
    }

    static void acquireInOppositeOrder(Object own, Object other,
            CountDownLatch ready, CountDownLatch proceed) {
        synchronized (own) {
            ready.countDown();
            try {
                proceed.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            synchronized (other) {
                // Intentionally unreachable once both threads have first locks.
            }
        }
    }

    static void deadlockLab() throws InterruptedException {
        Object left = new Object();
        Object right = new Object();
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch proceed = new CountDownLatch(1);

        Thread a = new Thread(
                () -> acquireInOppositeOrder(
                        left, right, ready, proceed), "lab-deadlock-A");
        Thread b = new Thread(
                () -> acquireInOppositeOrder(
                        right, left, ready, proceed), "lab-deadlock-B");
        a.setDaemon(true);
        b.setDaemon(true);
        a.start();
        b.start();

        if (!ready.await(3, TimeUnit.SECONDS)) {
            proceed.countDown();
            System.out.println("deadlock=lab-not-ready");
            return;
        }
        proceed.countDown();

        ThreadMXBean mx = ManagementFactory.getThreadMXBean();
        boolean detected = false;
        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(3);

        while (System.nanoTime() < deadline) {
            long[] ids = mx.findMonitorDeadlockedThreads();
            if (ids != null) {
                boolean hasA = Arrays.stream(ids)
                        .anyMatch(id -> id == a.getId());
                boolean hasB = Arrays.stream(ids)
                        .anyMatch(id -> id == b.getId());
                if (hasA && hasB) {
                    detected = true;
                    break;
                }
            }
            Thread.sleep(20);
        }
        System.out.println("monitorDeadlockDetected=" + detected);
    }

    static void livelockLikeLab() throws InterruptedException {
        CyclicBarrier bothAttempt = new CyclicBarrier(2);
        AtomicInteger retries = new AtomicInteger();

        Runnable polite = () -> {
            try {
                for (int i = 0; i < 5; i++) {
                    bothAttempt.await(3, TimeUnit.SECONDS);
                    // Both notice a conflict and both give way.
                    retries.incrementAndGet();
                    bothAttempt.await(3, TimeUnit.SECONDS);
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } catch (BrokenBarrierException | TimeoutException ex) {
                System.err.println("lab barrier failed: " + ex);
            }
        };

        Thread a = new Thread(polite, "polite-A");
        Thread b = new Thread(polite, "polite-B");
        a.start();
        b.start();
        a.join(7_000);
        b.join(7_000);
        if (a.isAlive()) a.interrupt();
        if (b.isAlive()) b.interrupt();
        System.out.println("retries=" + retries.get()
                + " usefulCompletions=0");
    }

    static void starvationLikeLab() throws Exception {
        ExecutorService single = Executors.newSingleThreadExecutor();
        CountDownLatch releaseFirst = new CountDownLatch(1);
        try {
            Future<?> first = single.submit(() -> {
                releaseFirst.await();
                return null;
            });
            Future<String> victim = single.submit(() -> "DONE");
            boolean missedWindow = false;
            try {
                victim.get(80, TimeUnit.MILLISECONDS);
            } catch (TimeoutException ex) {
                missedWindow = true;
            } finally {
                releaseFirst.countDown();
            }

            first.get(3, TimeUnit.SECONDS);
            String result = victim.get(3, TimeUnit.SECONDS);
            System.out.println("victimMissedWindow=" + missedWindow
                    + " recovered=" + "DONE".equals(result));
        } finally {
            releaseFirst.countDown();
            single.shutdownNow();
        }
    }

    static void longWaitLab() throws Exception {
        CompletableFuture<String> response = new CompletableFuture<>();
        boolean timedOut = false;
        try {
            response.get(80, TimeUnit.MILLISECONDS);
        } catch (TimeoutException ex) {
            timedOut = true;
        } finally {
            response.cancel(true);
        }
        System.out.println("waitTimedOut=" + timedOut
                + " futureCancelled=" + response.isCancelled());
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println(
                    "Usage: java HangPatternsLab "
                    + "fixture|deadlock|livelock|starvation|longwait");
            return;
        }
        switch (args[0]) {
            case "fixture" -> fixture();
            case "deadlock" -> deadlockLab();
            case "livelock" -> livelockLikeLab();
            case "starvation" -> starvationLikeLab();
            case "longwait" -> longWaitLab();
            default -> System.out.println("Unknown mode");
        }
    }
}
```

### 11.1 Biên dịch và chạy mode xác định

Yêu cầu JDK 17 hoặc mới hơn:

```bash
javac HangPatternsLab.java
java HangPatternsLab fixture
```

Stdout **chính xác** của `fixture`:

```text
deadlock: circular lock wait, no progress
livelock: active retries, no progress
starvation: victim denied execution opportunities
longwait: external event absent before deadline
```

Mode `fixture` **chỉ in bốn định nghĩa**, không tạo locks, threads, waits, executor hoặc network. Vì vậy stdout ổn định và không phụ thuộc tốc độ máy.

### 11.2 Mode deadlock — kết quả phụ thuộc timing/VM

Chạy **trong JVM lab mới**, không đưa vào production:

```bash
java HangPatternsLab deadlock
```

`CountDownLatch ready` bảo đảm cả A và B đã giữ monitor đầu tiên trước khi `proceed` cho phép họ yêu cầu monitor thứ hai. Đây là monitor cycle có chủ đích. Trên HotSpot hỗ trợ detector và khi scheduling bình thường, dòng thường quan sát được:

```text
monitorDeadlockDetected=true
```

Nếu hết thời gian chờ khởi tạo hoặc phát hiện không kịp, chương trình có thể in `deadlock=lab-not-ready` hoặc `monitorDeadlockDetected=false`. Vì vậy **không cam kết stdout cố định** cho mode này. Các thread trong deadlock là **daemon**, nên chúng không giữ JVM lab tồn tại mãi khi main kết thúc. Không chuyển nguyên đoạn deadlock này vào một test dùng chung JVM dài hạn.

Vì sao không `join()` A/B? Một `join` vô hạn trên threads deadlocked sẽ làm main tiếp tục treo, phá tính hữu hạn của lab.

### 11.3 Mode livelock — tiến trình hoạt động mà completion vẫn bằng 0

```bash
java HangPatternsLab livelock
```

Hai threads dùng `CyclicBarrier` để cùng đi qua 5 vòng *cùng thử, cùng nhường*. Trong điều kiện bình thường, kết quả minh họa:

```text
retries=10 usefulCompletions=0
```

Mỗi thread ghi một retry trong 5 vòng; cả hai không hoàn tất một tác vụ nghiệp vụ nào. Đây là **mô phỏng cố ý của đối xứng retry/nhường đường**, không phải một implementation dùng CAS hay lock production. Nếu barrier timeout/interrupt thì số retry có thể nhỏ hơn và có log stderr; bản chất bài học là **attempts tăng không đồng nghĩa completed work tăng**.

Livelock thật có thể kéo dài mãi nếu không có tie-breaker/backoff hoặc deadline. Lab **giới hạn số vòng** để không gây một vòng vô hạn trên máy người học.

### 11.4 Mode starvation — task bị kẹt sau một task chiếm worker

```bash
java HangPatternsLab starvation
```

Trong single-thread executor, task đầu chiếm worker để đợi `releaseFirst`, task thứ hai nằm sau nó trong hàng đợi. Mode thử đợi task thứ hai **80 ms**, sau đó release task đầu và kiểm tra task thứ hai cuối cùng được thực hiện.

Kết quả bình thường:

```text
victimMissedWindow=true recovered=true
```

Đây là **mô phỏng queue starvation risk / scheduling delay có kiểm soát**, **không** tự chứng minh một chương trình bị starvation vĩnh viễn. Do worker đầu đang chờ latch chứ không có monitor cycle, deadlock detector có thể không thấy. Khi worker đầu được release, task sau chạy được.

Điều quan trọng là phải theo dõi **thời gian chờ trong queue** và tuổi công việc cũ nhất; riêng số workers bằng 1 không tự chứng minh lỗi, vì thiết kế tuần tự có thể hoàn toàn hợp lệ khi task ngắn và backlog có giới hạn.

### 11.5 Mode longwait — deadline thay vì chờ vô hạn

```bash
java HangPatternsLab longwait
```

Một `CompletableFuture` chưa có producer hoàn tất; `get(80, MILLISECONDS)` báo timeout. Trong điều kiện bình thường:

```text
waitTimedOut=true futureCancelled=true
```

`cancel(true)` đánh dấu **Future** bị hủy; ở đây không có công việc nền nào thực sự chạy. Trong production, `Future.cancel(true)` **không bảo đảm** network call, thread hoặc transaction phía remote dừng ngay. Deadline/cancellation phải được truyền tới tầng thực thi phù hợp.

### 11.6 Không trộn mode để “so sánh số CPU”

Mỗi lệnh `java HangPatternsLab ...` khởi động một JVM mới với PID/thread lifecycle khác nhau. Không so CPU/heap/thread count giữa các modes như một phép benchmark định lượng chính xác; chúng là **tình huống giảng dạy**. Khi nghiên cứu sự cố thật, phải đo trên cùng service/build/config/workload và theo cùng cửa sổ.

## 12. Quy trình phân loại một incident “không tiến độ”

### Bước 1 — Xác nhận mục tiêu và triệu chứng

- JVM/process nào, pod/container nào, build nào, vừa deploy gì?
- Một request, một queue, một worker pool hay cả service không progress?
- SLO/deadline của operation là bao nhiêu?
- Điều gì **đã ngừng hoàn tất**? Thu completed/failed/accepted per second và oldest in-flight/queue age.
- Có GC pause, CPU quota throttling, OOM, DNS/network error, downstream outage hay resource saturation không?

Không gọi ngay là deadlock chỉ vì user nói “treo”. Ghi **timestamp và workload** trước khi can thiệp.

### Bước 2 — Thu bằng chứng ít xâm lấn

- Request/trace IDs, logs và metrics đang có.
- JVM CPU, GC, heap, native memory, pool size/active/queue, request concurrency.
- Dependency latency và timeout count.
- Thread dump tại vài thời điểm. Ghi thời gian và chi phí thao tác thu dump, vì snapshot có thể làm latency tăng thêm.

### Bước 3 — Xem có chu trình sở hữu khóa không

- Từ stack/ThreadInfo, tìm `thread A waiting to lock X`, owner B; từ owner B đi tiếp.
- Với object monitors, dùng `findMonitorDeadlockedThreads()`.
- Nếu JVM hỗ trợ ownable synchronizer usage, dùng `findDeadlockedThreads()`.
- Nếu không có lock cycle, kiểm tra dependency graph/logical cycles (executor A chờ B trong cùng pool, RPC A → B → A).

**Kết luận:** “Không thấy cycle thuộc phạm vi detector tại T1/T2” là hợp lệ; “không có bất kỳ deadlock nào” là quá mạnh.

### Bước 4 — Nếu có activity nhưng không có progress, tìm livelock

- So retry attempts, CAS conflicts, rollback count, task completions và CPU/thread stack changes theo cùng cửa sổ.
- Có hai tác nhân cùng retry xung đột và cùng nhường theo nhịp không?
- Có backoff/jitter hay chỉ loop retry ngay không?
- Retry có tôn trọng deadline và ngân sách, hay biến lỗi downstream thành retry storm?

Nếu retry cao nhưng requests vẫn hoàn tất theo tỷ lệ chấp nhận được, chưa thể gọi livelock. Cần định nghĩa “progress hữu ích” theo nghiệp vụ.

### Bước 5 — Nếu một nhóm vẫn xử lý còn nạn nhân bị trì hoãn, tìm starvation

- Kiểm tra queue oldest age, priority classes, workers busy time, lock/semaphore acquisition distribution.
- Victim có chưa được scheduled, hay đã vào worker nhưng đang block downstream?
- Có unfair lock barging, priority queue thiếu aging, pool nhỏ bị nhiệm vụ dài chiếm giữ hoặc resource leak không?
- Task có deadline riêng cho thời gian **nằm trong queue** không?

Không lẫn queue wait đúng thiết kế với starvation liên tục. Chỉ kết luận khi có bằng chứng một nhóm không được phục vụ đáng kể trong khi nhóm khác vẫn tiến triển.

### Bước 6 — Nếu một operation chờ lâu, đi theo đường phụ thuộc

- Stack đang ở `Future.get`, socket read, latch, join, DB driver, `Condition.await`, `BlockingQueue.take`?
- Ai có trách nhiệm gửi event/complete future/release resource?
- Dependency có đang sống, có timeout/circuit breaker, có request ID/trace nối qua service?
- Deadline của caller đã hết chưa; cancel có được propagate, side effect có thể còn xảy ra không?
- Có giữ lock trong lúc chờ I/O, khiến nhiều threads khác cũng bị ảnh hưởng không?

Một **long wait** có thể là gốc gây ra **queue starvation**, và từ đó dẫn đến service outage. Phân biệt **gốc và hậu quả** trong timeline.

### Bước 7 — Đối chứng và ghi giới hạn kết luận

Trước khi tuyên bố đã sửa:

- Đo lại under comparable load: completed rate, tail latency, retry rate, wait age, thread states và dependency latency.
- Đối chiếu lock graph hoặc absence of cycle theo nhiều mẫu.
- Chạy test tái hiện có kiểm soát, gồm concurrency stress và failure injection có deadline.
- Ghi dữ liệu trước/sau, thay đổi code/config, môi trường và hạn chế của mẫu.
- Không kết luận chỉ vì service hết treo **sau khi restart**; restart xóa trạng thái và nhiều dấu vết, chưa chứng minh căn nguyên.

## 13. Bốn tình huống đời thực

### Tình huống A — Hai locks giữ chéo trong order processing

**Quan sát:** hai threads liên tục hiện `BLOCKED`; thread A giữ monitor order-cache, chờ inventory-lock, B giữ inventory-lock, chờ order-cache. ThreadMXBean trả cả hai IDs.

**Phân loại:** phù hợp **monitor deadlock**, vì có chu trình sở hữu và chờ.

**Khắc phục:** đặt thứ tự lock toàn cục, không giữ locks khi gọi downstream, test cả đường thành công/lỗi. Không chỉ tăng số thread vì sẽ có thêm threads xếp sau chu trình.

### Tình huống B — Optimistic update retry vô hạn

**Quan sát:** `retries_total` tăng hàng nghìn/giây, `commits_total` không tăng; stack thường nằm trong CAS/rollback/retry; hai workers cùng thay đổi quyết định khi thấy conflict.

**Phân loại:** **livelock** là một giả thuyết mạnh nếu các bên liên tục tác động lẫn nhau khiến không có progress; vẫn cần kiểm tra downstream thật sự có lỗi liên tục hay không.

**Khắc phục:** jitter/backoff, retry budget/deadline, quy tắc tie-break/priority và metric `commits/attempts`.

### Tình huống C — Công việc batch bị bỏ đói

**Quan sát:** high-priority tasks liên tục được xử lý; low-priority job đã ở queue 40 phút, oldest age tăng; workers còn active, không có monitor cycle.

**Phân loại:** phù hợp **starvation do policy ưu tiên/thiếu fairness**, không phải deadlock.

**Khắc phục:** aging, capacity dành riêng hoặc weighted fairness, deadline trong queue, metrics theo class để không chỉ xem tổng throughput.

### Tình huống D — Một client call chưa có read timeout

**Quan sát:** worker chờ socket read 120 giây, downstream mất phản hồi; thread dump giữ cùng call path, lock detector không tìm thấy chu trình, các request khác vẫn hoàn tất.

**Phân loại:** **chờ vượt ngân sách** do dependency/timeout; chưa đủ chứng cứ deadlock hay starvation.

**Khắc phục:** connection/read/overall deadlines nhất quán, propagate cancellation, circuit breaker có semantics phù hợp, theo dõi downstream latency và retries. Nếu blocking workers hết slot, điều này có thể kéo theo queue starvation; phải ghi rõ quan hệ nguyên nhân–hậu quả.

Các tình huống ở trên là **mẫu phân tích**, không phải logs của một hệ thống cụ thể.

## 14. Những thay đổi giảm nguy cơ nhưng có trade-off

| Biện pháp | Mục tiêu | Trade-off/giới hạn |
| --- | --- | --- |
| Lock ordering | Loại trừ circular wait do thứ tự lấy lock trái nhau | Đòi hỏi chuẩn hóa trên mọi code path |
| Giảm critical section | Giảm contention và hold-and-wait | Cần giữ invariant của dữ liệu |
| `tryLock(timeout)` | Giới hạn thời gian chờ lock khi semantics cho phép | Có thể fail và cần xử lý/rollback; không tự giải mọi deadlock |
| Backoff + jitter | Tránh actors retry đồng pha dẫn đến livelock/retry storm | Tăng latency mỗi retry; phải có budget |
| Fairness/aging | Hạn chế starvation | Có thể giảm throughput và tăng context switching |
| Pool isolation/bulkheads | Ngăn long blockers chiếm toàn bộ workers | Tăng complexity/chi phí tài nguyên |
| Bounded queue & backpressure | Ngăn backlog/vượt RAM, hiển thị áp lực | Phải có rejection policy và trải nghiệm caller phù hợp |
| Deadline/timeout | Ngăn một operation chờ vô hạn | Timeout caller không đảm bảo remote task đã dừng |
| Cancellation/interruption | Tạo đường thoát cho các waits hỗ trợ | Không mọi thao tác đều interruptible; cần cleanup/idempotency |
| Progress metrics + multiple dumps | Phân biệt cơ chế bằng bằng chứng | Polling/dumps có overhead và sampling bias |

Không có một setting như “tăng pool từ 20 lên 200 threads” tự giải quyết bốn nhóm. Nếu các threads mới tiếp tục chờ cùng dependency, tăng pool chỉ có thể tăng memory, context switches và áp lực lên downstream.

## 15. Lưu ý an toàn khi chẩn đoán production

- **Không chạy lab cố tình deadlock trên server thật.** Dùng JVM riêng trong local/staging cô lập.
- Không gọi `Thread.stop()` để cắt vòng chờ; nó là API nguy hiểm, có thể phá invariant và để dữ liệu ở trạng thái không nhất quán.
- Không coi `Thread.interrupt()` là lệnh “kill thread” phổ quát; nó chỉ là **tín hiệu** mà API/code phải hợp tác xử lý. Một thread `BLOCKED` đợi monitor trong `synchronized` không đơn giản tự thoát khi interrupt.
- Không tự động gọi `GC.run()`, heap dump hoặc restart khi chưa có evidence; có thể xóa dấu vết và làm incident trầm trọng.
- Không thu full thread dumps/JFR ở tần suất cao mà không tính CPU, pause, output size và dữ liệu nhạy cảm.
- Không chia sẻ thô stack trace/arguments/hostnames/token nếu log/traces chứa thông tin riêng; cần quyền và che/redact phù hợp.
- Với container, xác minh PID/cgroup/quota/thread caps; một JVM có thể có quá ít CPU quota khiến progress chậm mà không có lock cycle.
- Nếu không đo được thread CPU, blocked time hoặc lock owner, ghi “**unknown/unsupported**”, không biến `-1`/`null` thành 0 rồi kết luận.
- Khi đưa ra giải pháp, ưu tiên giảm tác động, giữ dữ liệu chẩn đoán trước can thiệp, đo guardrails và có phương án rollback.

## 16. Những lỗi diễn giải phổ biến

1. **Thấy `BLOCKED` là tuyên bố deadlock.** Có thể là contention ngắn hợp lệ; cần cycle, owner và chuỗi mẫu.
2. **Thấy `WAITING` là lỗi.** Idle workers thường chờ queue bình thường.
3. **Thấy CPU cao là kết luận livelock.** Có thể CPU-bound work hữu ích hoặc GC/JIT.
4. **Thấy CPU thấp là loại trừ livelock.** Backoff/sleep có thể khiến retry không tốn CPU nhiều.
5. **Thấy retry tăng là kết luận livelock.** Có thể dependency lỗi hoặc retry vẫn hoàn tất.
6. **Dùng thread count thay progress.** 100 threads sống không chứng minh 100 jobs đang chạy hữu ích.
7. **Dùng một dump duy nhất.** Snapshot không chỉ ra thời gian chờ hay lịch sử.
8. **Tin `findDeadlockedThreads()==null` là không có deadlock ở mọi tầng.** API có phạm vi object monitors/ownable synchronizers.
9. **Không kiểm tra ownable synchronizer support.** Có thể không gọi được detector rộng hơn.
10. **Đồng nhất queue delay với starvation.** Cần so fairness, tuổi lâu nhất và tiến độ của nạn nhân.
11. **Không thấy stack task trong queue rồi kết luận task biến mất.** Task chưa bắt đầu không có call stack worker của riêng nó.
12. **Bỏ qua longwait ở downstream.** Một call quá lâu có thể chiếm pool và gây queue starvation thứ cấp.
13. **Thiếu timeout trên `Future.get()`/I/O.** Operation có thể chờ vô hạn dù process vẫn healthy.
14. **Tưởng `Future.get(timeout)` tự cancel task.** Timeout của caller không dừng task.
15. **Dùng `Thread.stop()` để cứu production.** Có thể phá state/locks và gây lỗi dữ liệu nghiêm trọng.
16. **Tăng thread pool mà không xác minh root cause.** Có thể mở rộng cạnh tranh tài nguyên.
17. **Không biết lock owner.** Đếm `BLOCKED` chưa biết nguyên nhân; cần lock graph/stack của owner.
18. **Chỉ nhìn average latency.** Tail latency và oldest queue age có thể xấu dù mean ổn.
19. **Không phân biệt “bị chậm” với “không tiến triển”.** Cần nhiều mốc, delta progress và deadline.
20. **Gộp mọi sự cố vào một nhãn duy nhất.** Long wait có thể gây starvation; deadlock có thể khiến queue tăng.
21. **Chỉ test khi không có concurrent load.** Một bug lock order có thể không tái hiện trong test đơn luồng.
22. **Không ghi timestamp/config/workload khi so trước sau.** Không có cơ sở kết luận thay đổi đã khắc phục.
23. **Hiểu `RUNNABLE` là “đang chiếm CPU”.** Thread có thể chờ OS resource.
24. **Bỏ qua process/JVM identity trong container.** Có thể đang chẩn đoán sai instance.
25. **Quên timeout/cancellation cũng có side effect.** Remote action có thể vẫn hoàn tất sau khi caller đã bỏ cuộc.

## 17. Câu hỏi tự kiểm tra

1. Hãy dùng một câu nêu khác biệt bản chất giữa deadlock, livelock, starvation và long wait.
2. A giữ lock X muốn Y, B giữ Y muốn X. Vì sao đây là deadlock thay vì starvation?
3. Vì sao hai workers “liên tục nhường nhau” có thể là livelock dù CPU cao và threads không `BLOCKED`?
4. Một job low-priority chờ 30 phút, trong khi high-priority jobs vẫn hoàn tất. Bạn cần chứng cứ gì để gọi là starvation?
5. `Future.get()` chờ 1 phút không timeout. Bạn có thể kết luận deadlock chưa? Vì sao?
6. Thread pool có 30 `WAITING` workers nhưng không có tasks trong queue. Đây có phải incident không?
7. `findMonitorDeadlockedThreads()` và `findDeadlockedThreads()` khác nhau theo loại khóa nào?
8. Vì sao một logical dependency cycle của hai `Future` trong single-thread executor có thể không được `ThreadMXBean` nhận diện?
9. Một retry counter tăng 1.000/giây nhưng completed jobs bằng 0: còn phải loại trừ những giải thích nào trước khi kết luận livelock?
10. `Future.get(timeout)` báo `TimeoutException`. Điều đó có chứng minh remote task đã bị hủy không?
11. Dấu hiệu nào phân biệt một queue delay hợp lệ với starvation kéo dài?
12. Tại sao một thread `RUNNABLE` có thể không dùng CPU 100%?
13. Khi làm lab deadlock, vì sao dùng daemon threads và không gọi `join()` vô hạn?
14. Hãy mô tả 5 số đo nên thu khi service không hoàn tất request dù health endpoint vẫn OK.
15. Nếu có longwait bên ngoài rồi dẫn đến queue starvation, báo cáo root cause và hậu quả nên tách thế nào?
16. Vì sao `tryLock(timeout)` và lock ordering là hai biện pháp khác nhau và không nên đánh đồng?
17. Trong chẩn đoán, tại sao việc tăng pool size có thể che triệu chứng tạm thời nhưng làm nguyên nhân gốc tệ hơn?
18. Nếu `findDeadlockedThreads()` trả `null`, cách diễn đạt giới hạn kết luận chính xác nhất là gì?

## 18. Mẫu báo cáo chẩn đoán

```text
IDENTITY
- Service/build/JDK vendor/version:
- PID/container/pod/node, start time:
- Timestamp/timezone and request workload:

SYMPTOM / PROGRESS
- Which operations stopped completing?
- receivedRate/completedRate/failedRate:
- Retry/attempt rate and useful commit rate:
- Queue depth and oldest queued age:
- InFlight oldest age, latency p95/p99/deadline violations:

THREAD / LOCK EVIDENCE
- Thread dump timestamps and collection overhead:
- Thread names, IDs, state and stack at each sample:
- Waiting lock, current owner and ownership cycles:
- ThreadMXBean monitor/ownable-synchronizer results:
- CPU deltas, contention times and support/enabled flags:

DEPENDENCIES
- DB/HTTP/RPC/file/socket calls and their configured timeout:
- Downstream latency/errors/availability:
- Caller deadline and cancellation propagation:

DIFFERENTIAL DIAGNOSIS
- Deadlock evidence / gaps:
- Livelock evidence / gaps:
- Starvation evidence / gaps:
- Long wait evidence / gaps:
- Primary cause vs secondary symptoms:

CHANGE / VERIFICATION
- Action owner, timestamp, exact code/config change:
- Before/after at comparable load:
- Confirmation test and remaining uncertainty:
- Regression test, rollback criterion and follow-up:
```

Một báo cáo có chất lượng nêu “**đã quan sát**” khác với “**giả thuyết**”. Ví dụ “workers chưa hoàn tất request trong 20 giây; ba dumps cho thấy A/B chờ monitors lẫn nhau; ThreadMXBean trả đúng IDs” là bằng chứng mạnh cho monitor deadlock. “p99 cao, CPU thấp, chắc chắn deadlock” là kết luận thiếu căn cứ.

## 19. Tài liệu tham khảo chính thức

- Oracle Java SE 17 — `Thread.State`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html
- Oracle Java SE 17 — `ThreadMXBean`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Oracle Java SE 17 — `ThreadInfo`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html
- Oracle Java SE 17 — `Future`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- Oracle Java SE 17 — `ReentrantLock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html
- Oracle Java SE 17 — `Lock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Lock.html
- Oracle Java SE 17 — `jcmd`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html

**Ghi nhớ:** trước khi chẩn đoán một hệ thống Java “treo”, hãy hỏi **“công việc nào ngừng tiến triển?”**. Sau đó xác minh có **chu trình chờ**, **retry hoạt động nhưng không hoàn tất**, **nạn nhân thiếu tài nguyên giữa lúc công việc khác vẫn tiến triển**, hay **lời gọi đang đợi vượt deadline**. Cần nhiều mốc dữ liệu, ownership/stack/queue/dependency evidence và kết luận có giới hạn; không dùng một thread state hoặc một mẫu CPU để gán nhãn cả sự cố.