# 15.8. Phân tích khóa, trạng thái thread, thao tác file/socket và ngoại lệ bằng JFR

## Mục tiêu bài học

Sau bài này, bạn có thể:

1. Đọc một file **Java Flight Recorder (JFR)** để tìm dấu hiệu **tranh chấp khóa**, chờ monitor, park/sleep, I/O file/socket và exception.
2. Phân biệt đúng `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`, `jdk.ThreadPark`, `jdk.ThreadSleep` và các trạng thái trong `java.lang.Thread.State`.
3. Xác định sự kiện I/O đáng chú ý theo **thời điểm, duration, endpoint/path, số byte, event thread và stack trace**; không nhầm độ trễ chờ với mức CPU sử dụng.
4. Hiểu `jdk.JavaExceptionThrow`, `jdk.JavaErrorThrow` và thống kê exception; biết vì sao exception được **throw** không đồng nghĩa với request thất bại hoặc tiến trình crash.
5. Kết hợp nhiều nhóm event trên cùng **timeline**, kiểm tra event settings/threshold, rồi đưa ra giả thuyết có thể xác minh bằng log, metric, thread dump và thử nghiệm.
6. Tự chạy chương trình Java 17+ để tạo một recording có các thao tác chờ có kiểm soát, rồi đọc sự kiện bằng `jfr` và `jdk.jfr.consumer`.

> **Giới hạn quan trọng:** JFR ghi **những event mà recording được cấu hình để thu**. Không có event trong file **không** chứng minh thao tác không xảy ra; event có duration dài **không** tự chứng minh deadlock, CPU nóng hay sự cố của server bên ngoài.

## 1. Cách tiếp cận: đi từ triệu chứng đến event và stack

JFR ghi lại sự kiện có **event type**, **start time**, **duration** (với event có khoảng thời gian), **event thread**, **payload**, và có thể có **stack trace**. Một event thường chỉ trả lời một câu hỏi hẹp:

- Một thread mất 240 ms để **vào monitor** (`jdk.JavaMonitorEnter`).
- Một thread **chờ điều kiện** qua `Object.wait()` trong 500 ms (`jdk.JavaMonitorWait`).
- Một thread **park** khi chờ task/lock/permit (`jdk.ThreadPark`).
- Một lần **socket read** mất 800 ms và trả về một số byte nhất định (`jdk.SocketRead`).
- Một exception đã được **throw** tại một stack (`jdk.JavaExceptionThrow`).

Cần đặt các event trên trục thời gian và đối chiếu với dấu hiệu thật: request latency tăng, queue backlog, throughput giảm, CPU cao, timeout hoặc error rate.

```text
Triệu chứng: request p99 tăng
        |
        v
Ghi đúng khoảng thời gian trong .jfr
        |
        +--> Lock/park/wait? ------> Ai phải chờ? Chờ bao lâu? Ở stack nào?
        |
        +--> File/socket I/O? -----> Endpoint/path nào? Duration, bytes, timeout?
        |
        +--> Exception? -----------> Loại nào? Lặp bao nhiêu? Có được xử lý?
        |
        +--> Thread/CPU samples? --> Thread nào? Đang chờ hay đang được lấy mẫu chạy?
        |
        v
Đối chiếu log/request ID, metrics, cấu hình, thread dump
        |
        v
Giả thuyết -> thử nghiệm -> xác nhận hoặc bác bỏ
```

**Điểm rất dễ sai:** các event duration có thể *chồng thời gian giữa nhiều thread*. Cộng 100 lần `SocketRead` mỗi lần 1 giây ra **100 giây tổng thời lượng event**, không có nghĩa **100 giây wall-clock** đã trôi qua hay một request dài 100 giây.

## 2. Bảng event cần biết trước khi phân tích

Tên dưới đây thuộc các JFR event type phổ biến của HotSpot/JDK 17–21+. Phiên bản, JVM implementation, `.jfc`, event threshold, stack setting và workload quyết định type nào có trong recording. Trước khi phân tích, **kiểm tra `jfr summary` và `jfr metadata` trên file thật**.

| Hiện tượng | JFR event | Ý nghĩa chính |
| --- | --- | --- |
| Tranh chấp `synchronized` | `jdk.JavaMonitorEnter` | Thời gian một thread bị chặn khi **chờ vào intrinsic monitor** rồi mới vào được. |
| Gọi `Object.wait()` | `jdk.JavaMonitorWait` | Thời gian thread **đợi trên monitor sau `wait()`**, có thể do notify, timeout hoặc interrupt. |
| Chờ qua `LockSupport` và nhiều abstraction concurrent | `jdk.ThreadPark` | Khoảng thời gian park, ví dụ một số thao tác đợi của `Lock`, `Future`, queue, executor. |
| `Thread.sleep()` | `jdk.ThreadSleep` | Khoảng thời gian ngủ, không chứng tỏ lock contention. |
| Vòng đời thread | `jdk.ThreadStart`, `jdk.ThreadEnd` | Mốc tạo/hoàn tất, không phải mọi lần thay đổi `Thread.State`. |
| Đọc/ghi file | `jdk.FileRead`, `jdk.FileWrite` | Thời gian thao tác I/O được đo và dữ liệu path/bytes khi có. |
| Đọc/ghi TCP socket | `jdk.SocketRead`, `jdk.SocketWrite` | Thời gian thao tác socket và endpoint/bytes khi có. |
| Exception được ném | `jdk.JavaExceptionThrow` | Loại exception, message/stack nếu event được bật và dữ liệu có sẵn. |
| Error được ném | `jdk.JavaErrorThrow` | Sự kiện liên quan `Error`; không đồng nghĩa JVM đã crash. |
| Thống kê exception định kỳ | `jdk.ExceptionStatistics` | Một góc nhìn số lượng ngoại lệ, không phải log chi tiết mọi lần ném. |
| Mẫu thực thi/CPU | `jdk.ExecutionSample`, `jdk.CPULoad`, `jdk.ThreadCPULoad` | Bổ trợ khi cần phân biệt đang tính toán với đang chờ. |

**Hai event rất hay bị nhầm:** `jdk.JavaMonitorEnter` liên quan **tranh chấp khi đi vào `synchronized`**; `jdk.JavaMonitorWait` liên quan **`Object.wait()` sau khi thread đã sở hữu monitor và tạm nhả nó**. Không gộp hai loại thành “blocked on lock”.

### Đọc field theo ngữ nghĩa, không chỉ tên

| Field thường gặp | Cách dùng | Cẩn thận |
| --- | --- | --- |
| `startTime`, `duration` | Xếp các event theo thời gian và so độ trễ. | Duration thường là elapsed time, có thể bao gồm chờ/scheduling; không tự bằng CPU time. |
| `eventThread` / `getThread()` | Xác định thread phát sinh event. | Thread name có thể trùng và được tái sử dụng; virtual thread và carrier không có quan hệ cố định. |
| `stackTrace` | Xem call path tại điểm sự kiện được ghi/lấy mẫu. | Có thể thiếu hoặc bị giới hạn độ sâu; stack không phải lịch sử toàn duration. |
| `monitorClass`, `previousOwner`, `address` | Điều tra monitor và người sở hữu trước đó khi JFR có ghi. | `address` là nhận dạng thấp cấp trong runtime, không dùng làm ID lâu dài giữa JVM/recording. |
| `path`, `bytesRead`, `bytesWritten` | Tìm file/operation lớn hoặc chậm. | Không suy ra toàn bộ disk latency hoặc lượng disk I/O vật lý từ một sự kiện. |
| `host`, `address`, `port` | Gom socket theo endpoint được ghi. | Một endpoint có thể phục vụ nhiều request; không thay thế request ID. |
| `thrownClass`, `message` | Phân loại exception, phát hiện lặp lại. | Không nên dùng message chứa dữ liệu nhạy cảm làm key chính; throw chưa chắc uncaught. |

Tên field **có thể khác theo event type và JDK**, nên xem metadata thực, ví dụ `jfr metadata --events jdk.JavaMonitorEnter recording.jfr`.

## 3. Kiểm tra một file recording trước khi đưa ra kết luận

Giả sử đã có file `incident.jfr` từ một JVM có vấn đề. Dùng JDK 17+:

```bash
jfr summary incident.jfr
jfr metadata --events jdk.JavaMonitorEnter,jdk.SocketRead incident.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark --stack-depth 20 incident.jfr
jfr print --events jdk.FileRead,jdk.FileWrite,jdk.SocketRead,jdk.SocketWrite --stack-depth 20 incident.jfr
jfr print --events jdk.JavaExceptionThrow,jdk.JavaErrorThrow,jdk.ExceptionStatistics --stack-depth 20 incident.jfr
```

Các lệnh này **đọc file hiện có**, không chỉnh file `.jfr` hoặc chạy code bên trong ứng dụng.

- **`jfr summary`** cho biết thời gian recording, số lượng và kích thước event theo type: đây là bước đầu tiên để tránh phân tích một type không được ghi.
- **`jfr metadata`** cho biết schema/field của type được ghi (hoặc metadata có trong file); giúp xác định các field để lọc đúng khi dùng JSON/API.
- **`jfr print --events ...`** chỉ in các event khớp tên type; có thể xuất hàng nghìn dòng nếu nhiều event.
- **`--stack-depth 20`** tăng **số frame được hiển thị**, không khôi phục stack đã không được ghi do `stackTrace=false` hoặc giới hạn độ sâu lúc thu.

Có thể xuất JSON để công cụ khác phân tích:

```bash
jfr print --json --events jdk.SocketRead,jdk.SocketWrite incident.jfr
```

Không giả định mọi bản JDK đều có **một schema JSON y hệt**; đối chiếu `jfr metadata`, kiểm tra field có tồn tại trước khi truy vấn. Đừng gửi nguyên file chứa exception message, path hoặc endpoint nội bộ ra ngoài môi trường tin cậy.

Nếu đang xem trong **Java Mission Control (JMC)**, mở recording, tìm các vùng xem về **Threads/Lock Instances**, **I/O**, **Exceptions**, lọc time range/thread, xem bảng event và stack. Bố cục/tên tab có thể khác theo phiên bản JMC. Mục tiêu là **đọc từng event cùng ngữ cảnh trên timeline**, không phụ thuộc một vị trí menu cố định.

## 4. Phân tích khóa: tranh chấp monitor khác với chờ điều kiện

### 4.1. `jdk.JavaMonitorEnter`: khi thread bị chặn để vào `synchronized`

Giả sử:

```java
private static final Object LOCK = new Object();

// Thread A đang ở trong synchronized rất lâu:
synchronized (LOCK) {
    processSlowly();
}

// Thread B đến sau và phải đợi A nhả LOCK:
synchronized (LOCK) {
    updateSharedState();
}
```

Đây là **mã minh họa**, không phải chương trình hoàn chỉnh. Nếu thread B bị chặn khi vào monitor đủ lâu để vượt threshold JFR, ta có thể thấy `jdk.JavaMonitorEnter` của **thread B**. `duration` phản ánh khoảng chờ trước khi lấy được monitor; **không** phải thời lượng `updateSharedState()` chạy bên trong critical section.

Khi xem event:

1. **Thread nào phải chờ?** Đọc event thread/ID; chú ý thread pool có thể đổi tên giữa các task.
2. **Chờ ở đâu?** Stack trace gợi ý frame gọi `synchronized`, ví dụ handler, cache, formatter hay logger.
3. **Monitor của kiểu nào?** `monitorClass`; nhiều instance cùng lớp có thể là các lock khác nhau.
4. **Ai giữ trước đó?** `previousOwner` nếu field có dữ liệu; cần kiểm tra timeline/thread dump để tìm tác vụ của owner.
5. **Chờ nhiều hay chờ lâu?** Đếm event và xem p95/p99/max, số thread cùng tranh chấp một monitor. So với thời gian ghi và workload.

Một event 200 ms có thể chỉ là contention thoáng qua. Nếu nhiều request bị chặn nối tiếp ở cùng một lock và throughput giảm, **đây mới là dấu hiệu serialization/bottleneck đáng điều tra**.

### 4.2. `jdk.JavaMonitorWait`: `Object.wait()` không phải đợi vào monitor

```java
synchronized (LOCK) {
    while (!ready) {
        LOCK.wait();
    }
}
```

Đây là **mã minh họa**. `wait()` **nhả monitor** trong lúc thread chờ notify/notifyAll, timeout hoặc interrupt; trước khi `wait()` trả về bình thường, thread phải lấy lại monitor. Event `jdk.JavaMonitorWait` phản ánh hoạt động **đợi điều kiện** qua monitor. Nó có thể cho biết monitor class, notifier, timeout hoặc `timedOut` khi được ghi, tùy phiên bản/schema.

Nếu stack dừng ở `Object.wait`, hãy hỏi:

- Điều kiện `ready` do ai thay đổi? Có `notify`/`notifyAll` đúng chỗ và dưới cùng monitor không?
- Đó là **idle worker** đang chờ công việc (bình thường) hay một request phải chờ dữ liệu lẽ ra đã có?
- Có **lost notification**, timeout, guard condition bị sai hoặc backlog upstream không?
- Một thread báo wait dài có thực sự thuộc critical path của request cần điều tra không?

Đừng kết luận `JavaMonitorWait` kéo dài là **monitor lock contention**; hai tình huống có cơ chế khác nhau.

### 4.3. `jdk.ThreadPark`: `LockSupport`, `Lock`, queue và future

Nhiều abstraction trong `java.util.concurrent` dùng park/unpark. Ví dụ `ReentrantLock`, `CompletableFuture` hoặc `BlockingQueue` trong một số code path có thể gây `jdk.ThreadPark`, thay vì `jdk.JavaMonitorEnter`.

```java
LockSupport.parkNanos(100_000_000L); // minh họa park tối đa khoảng 100 ms
```

Trong `jdk.ThreadPark`, kiểm tra event thread, `duration`, stack, `parkedClass` và timeout/đối tượng nếu schema có. Stack đến `CompletableFuture.get()` hoặc `LinkedBlockingQueue.take()` có thể biểu thị **chờ đúng thiết kế**, còn stack đến một lock có contention có thể biểu thị nghẽn. Phải truy tìm **điều kiện đánh thức**: ai hoàn tất future, ai đưa dữ liệu vào queue, ai nhả lock.

Không đồng nhất mọi `ThreadPark` với deadlock. Thread park dài ở một executor đang rỗi rất thường gặp và có thể bình thường.

### 4.4. `jdk.ThreadSleep`: cố ý ngủ hoặc backoff

`Thread.sleep()` là chờ theo thời gian, thường dùng trong retry/backoff, scheduler hoặc demo. Nếu một request thật gọi sleep 500 ms trong critical path, latency sẽ tăng; nhưng đó **không** phải contention trừ khi còn bằng chứng lock khác. Nếu sleep ở maintenance thread không nằm trên đường request, không nên ưu tiên nó chỉ vì duration lớn.

### 4.5. Checklist cho vấn đề khóa

| Dấu hiệu | Câu hỏi cần kiểm tra | Bằng chứng bổ sung |
| --- | --- | --- |
| `JavaMonitorEnter` nhiều và dài | Có critical section chứa I/O, logging, gọi service, work nặng không? | Stack owner/contender, thread dump, profile, mã đồng bộ. |
| `JavaMonitorWait` dài | Đang đợi điều kiện nào? Ai có trách nhiệm notify? | Code guarded block, log trạng thái queue/condition. |
| `ThreadPark` nhiều ở request thread | Chờ future/lock/queue nào? Có timeout không? | Stack, queue depth, executor saturation, task completion. |
| `ThreadSleep` dài ở request thread | Có retry/backoff vô tình chặn request? | Retry policy, log timeout và các lần thử. |
| Không thấy monitor event | Event bị tắt/ngưỡng cao, loại lock khác, contention ngắn hoặc không xảy ra. | Kiểm tra settings, `ThreadPark`, thread dump. |

> **Phân biệt deadlock:** vài event chờ lock dài **không** chứng minh deadlock. Cần bằng chứng về vòng chờ/owner/GC roots tương ứng, thread dump và quan sát tiến trình. Một hệ thống chậm vì lock contention vẫn có thể tiến triển.

## 5. Trạng thái thread: không đồng nhất `Thread.State` với màu của timeline JFR

`java.lang.Thread.State` có các trạng thái **NEW, RUNNABLE, BLOCKED, WAITING, TIMED_WAITING, TERMINATED**. JFR thường cho ta **mảnh quan sát** từ event lifecycle, chờ, I/O và sample; nó **không tự phát ra bản ghi đầy đủ cho mọi lần một thread chuyển giữa sáu trạng thái**.

| Java state | Ý nghĩa ở mức API | Tín hiệu JFR có thể hỗ trợ | Điều không được suy ra |
| --- | --- | --- | --- |
| `NEW` | Thread chưa `start()`. | Có thể chưa thấy `ThreadStart`. | Không thể chứng minh chưa tồn tại chỉ từ thiếu event. |
| `RUNNABLE` | Có thể đang chạy hoặc sẵn sàng chạy, đôi khi ở native I/O tùy VM. | `ExecutionSample`, thread CPU load. | `RUNNABLE` **không đồng nghĩa đang tiêu thụ CPU 100%**. |
| `BLOCKED` | Chờ vào intrinsic monitor (`synchronized`). | `JavaMonitorEnter` khi contention được ghi. | Không bao gồm mọi loại chờ `Lock`/Future. |
| `WAITING` | Chờ không thời hạn, như `Object.wait()` hay `park()`. | `JavaMonitorWait`, `ThreadPark` tùy hoạt động. | Chờ có chủ đích không phải tự động là bug. |
| `TIMED_WAITING` | Chờ có timeout như `sleep`, `wait(timeout)`, `parkNanos`. | `ThreadSleep`, `JavaMonitorWait`, `ThreadPark`. | Event duration không phải timeout được cấu hình. |
| `TERMINATED` | Thread đã kết thúc. | `ThreadEnd` nếu được thu. | Một event end không chỉ ra đầy đủ lý do kết thúc. |

**Vì sao không suy ra trạng thái từ mọi khoảng trống?** JFR có **threshold**, sampling và event filtering. Không có event trong một đoạn timeline có thể do thread đang chạy CPU, không có hoạt động được instrument, event dưới threshold, event bị tắt hoặc dữ liệu bị mất. Cần kiểm tra `jdk.DataLoss`/metadata và so cùng CPU samples, thread dump/log nếu cần.

### Phân tích thread pool và virtual thread

- Với **thread pool**, một platform thread phục vụ **nhiều task/request nối tiếp**. Không gán mọi event của cùng tên thread cho cùng request nếu không có request/correlation ID.
- Với **virtual thread (Java 21+)**, một virtual thread có thể mount/unmount lên các **carrier platform thread khác nhau**. Không suy giả định cứng “virtual thread A luôn chạy trên carrier B”.
- Khả năng ghi lifecycle và các event chuyên biệt cho virtual thread thay đổi theo bản JDK/JVM/recording. Nếu đang điều tra virtual thread, kiểm tra event như `jdk.VirtualThreadPinned` (khi được hỗ trợ và được bật), stack và các công cụ dump phù hợp, thay vì tưởng chỉ một thread ID platform đủ đại diện.
- **Stack sampling** đo các stack được lấy mẫu theo tần suất/cấu hình, không đếm chính xác số lần gọi method.

Đối với lỗi “request treo”, ưu tiên lập chuỗi: **request đang đợi điều gì → thread/event nào cho biết điều đó → tác nhân nào giải phóng điều kiện → có xảy ra không?** Chỉ liệt kê trạng thái thread không đủ tìm nguyên nhân.

## 6. Phân tích file I/O (`jdk.FileRead`, `jdk.FileWrite`)

Các event I/O có thể chứa `path`, `bytesRead`/`bytesWritten`, `startTime`, `duration`, event thread và stack (nếu bật). Chúng giúp phân biệt loại công việc file nào khiến ứng dụng chậm.

Ví dụ *minh họa* về một tập event:

| Path | Số event | Tổng duration event | Tổng byte | Gợi ý cần kiểm tra |
| --- | ---: | ---: | ---: | --- |
| `/var/log/app.log` | 900 | 3.400 ms | 5 MiB | Ghi log đồng bộ trên critical path? |
| `/data/cache.bin` | 22 | 1.800 ms | 300 MiB | Đọc/ghi file lớn, nhiều lần chờ I/O? |
| `/tmp/export.csv` | 2 | 5.500 ms | 85 MiB | Một tác vụ export có thể tốn thời gian; có cần streaming? |

Đây **không phải output cố định** của JFR. Muốn ưu tiên điều tra:

1. Xem **duration cao nhất** và p95/p99 cho từng path hoặc call site; nhiều I/O nhỏ có thể ít tác động hơn một thao tác chậm ở critical path.
2. Xem **số byte**, nhưng không dùng `bytes/duration` để suy ra tốc độ disk vật lý nếu có cache, buffer, nhiều thread hoặc native layer.
3. Phân biệt **ứng dụng thật sự chờ** với I/O nền (log batching, file rotate, backup) bằng thread và stack.
4. Xem file/network filesystem, contention OS, queue disk, latency storage và log hạ tầng; JFR event không tự biết “ổ đĩa hỏng”.

Một thao tác `FileWrite` 200 ms không chắc là 200 ms đĩa đang ghi vật lý, vì I/O Java có thể đi qua OS page cache, buffering, lớp mã hóa hoặc async mechanism. JFR cũng không nhất thiết ghi đầy đủ mọi loại file operation của thư viện native.

## 7. Phân tích socket I/O (`jdk.SocketRead`, `jdk.SocketWrite`)

Socket event cho biết thời điểm và elapsed duration của thao tác read/write mà JVM instrument, cùng thông tin endpoint khi có. Các field thường gặp gồm `host`, `address`, `port`, `bytesRead`, `bytesWritten`, `timeout`, `endOfStream` (tùy event và JDK).

### Socket read chậm có thể có nhiều nguyên nhân

Một `jdk.SocketRead` kéo dài **800 ms** có thể do:

- Peer/server gửi dữ liệu muộn, xử lý request chậm.
- Network latency, packet loss hoặc kết nối suy giảm.
- Ứng dụng đọc khi chưa có dữ liệu vì giao thức/request sequencing.
- Thread scheduling hoặc tranh chấp tài nguyên xung quanh operation.
- Pool/retry/timeout/circuit breaker được cấu hình chưa phù hợp.

**Không nên kết luận:** “Socket read 800 ms = mạng bị lỗi”. JFR chỉ đo phía JVM đang quan sát; phải đối chiếu metrics ở peer/server, network, TCP retransmissions (nếu có), trace và log.

### Socket write chậm cũng chưa đủ chứng minh mạng chậm

`SocketWrite` duration dài có thể liên quan backpressure, send buffer đầy, peer đọc chậm, blocking I/O hoặc workload JVM. Phân tích **bytes, endpoint, stack, event thread, duration** và thời điểm request. Một thao tác ghi nhiều byte nhưng duration dài có thể bình thường nếu giới hạn băng thông đã biết.

### Một quy trình lọc khả thi

```bash
jfr print --events jdk.SocketRead,jdk.SocketWrite --stack-depth 20 incident.jfr
jfr print --events jdk.FileRead,jdk.FileWrite --stack-depth 20 incident.jfr
```

Lọc theo **endpoint/path** và gom theo time window trong JMC hoặc script. Khi xuất JSON, xem schema thực trước khi lọc. Đừng dùng riêng hostname hoặc IP làm chứng cứ một request cụ thể, vì kết nối có thể reuse và nhiều request chồng nhau.

**Tính toán cần thận trọng:**

```text
count             = số event được ghi
totalEventTime    = tổng duration các event
maxEventTime      = duration lớn nhất
totalBytes        = tổng số byte được event cung cấp
```

`totalEventTime` của các thread có thể **chồng nhau**; nó không bằng latency của cả hệ thống. Khi event dưới threshold bị loại, `count`, `totalEventTime` và phân bố mẫu **bị thiên lệch**. Không so hai recording có ngưỡng I/O khác nhau như cùng một thước đo.

## 8. Phân tích exception: “được throw” khác với “thất bại”

### 8.1. `jdk.JavaExceptionThrow` và `jdk.JavaErrorThrow`

Một exception có thể bị ném và **được catch/handle bình thường**, ví dụ:

```java
try {
    Integer.parseInt("not-a-number");
} catch (NumberFormatException expected) {
    // Ứng dụng có thể xử lý input không hợp lệ theo thiết kế.
}
```

Đây là đoạn minh họa. Khi `jdk.JavaExceptionThrow` được bật, JFR có thể ghi type, thời điểm, `thrownClass`, `message` và stack. **Việc xuất hiện event không đồng nghĩa với HTTP 500, crash hoặc lỗi không được xử lý.**

`jdk.JavaErrorThrow` phản ánh những lần ném `Error` mà JFR ghi được; **không được dùng như bằng chứng JVM chắc chắn sẽ chết**. Một số `Error` vẫn có thể bị bắt trong hệ thống, dù nhiều loại nghiêm trọng đòi hỏi xem xét ngay.

**`jdk.ExceptionStatistics`** có thể giúp nhìn xu hướng tổng quan ở những cấu hình có bật, nhưng không thay thế phân loại per-exception và correlation đến request. Số exception “thrown” có thể rất khác số exception “uncaught” hoặc số response lỗi.

### 8.2. Ưu tiên theo tác động và sự thay đổi

| Quan sát | Kiểm tra tiếp |
| --- | --- |
| Exception mới xuất hiện sau deploy | So type/stack/phiên bản, log thay đổi, request path. |
| Một loại exception tăng đột ngột | Có retry loop, input lỗi, parse, timeout hay fallback thay đổi không? |
| Exception xuất hiện nhưng error rate vẫn ổn | Có thể là exception xử lý được; đo overhead và độ ồn trước khi gọi là incident. |
| `IOException` cùng lúc socket timeout | Ghép với `SocketRead`/`SocketWrite`, endpoint và trace, tránh kết luận chỉ từ trùng timestamp. |
| `Error` nghiêm trọng/OOME | Phối hợp heap/GC/native memory, stderr, health checks và OOME logs; JFR có thể chưa kịp flush đầy đủ. |

**Rủi ro khi bật throw event:** ứng dụng có thể tạo exception với tần suất rất cao (đặc biệt exception dùng cho control flow). Bật chi tiết stack/message có thể tăng overhead, dung lượng file và làm lộ dữ liệu nhạy cảm. Một số JDK áp dụng cơ chế throttle cho exception events; luôn kiểm tra settings và phiên bản đang chạy. Chọn recording ngắn có mục tiêu khi cần điều tra sâu.

### 8.3. Stack trace của exception

Stack gợi ý vị trí **throw**, nhưng không nói đầy đủ **catch ở đâu**, vì stack trace JFR ghi không tự bao gồm tất cả các bước xử lý tiếp theo. Để biết request có thất bại:

- Đối chiếu log với request ID, response status, retry/fallback.
- Tìm cùng loại exception lặp nhiều trong một request hay nhiều request.
- Kiểm tra lần throw này có thật sự làm thay đổi kết quả, throughput hoặc latency không.

`message` có thể chứa path, host, parameter hoặc dữ liệu nhạy cảm; dùng class/type/stack + ngữ cảnh chuẩn hóa khi group thay vì log nguyên message công khai.

## 9. Thu recording mới khi file hiện có thiếu event

**Lưu ý:** phần này dùng khi bạn có thẩm quyền ghi JFR cho JVM đích. `jcmd` cần thấy đúng PID và có quyền attach (thường cùng effective user trên cùng máy/namespace). Trong container, PID và đường dẫn có thể khác host.

Ví dụ trên JVM có PID thực là `12345`:

```bash
jcmd -l
jcmd 12345 help JFR.start
jcmd 12345 JFR.start name=diagnostics settings=profile
jcmd 12345 JFR.check
```

Khi tái hiện triệu chứng, lấy file:

```bash
jcmd 12345 JFR.dump name=diagnostics filename=/tmp/incident.jfr
jcmd 12345 JFR.stop name=diagnostics
```

`JFR.dump` ghi bản dump **trong khi recording có thể tiếp tục**; `JFR.stop` mới dừng. File `/tmp/incident.jfr` được **JVM đích** ghi trong filesystem mà JVM thấy, không nhất thiết là filesystem shell gọi `jcmd`.

Nếu muốn một recording tự dừng:

```bash
jcmd 12345 JFR.start name=short-incident settings=profile duration=60s filename=/tmp/incident-60s.jfr
```

File sẽ hoàn tất theo duration và trạng thái thực tế của recording; lệnh start trả về trước khi thu đủ 60 giây. Để chọn event và threshold cụ thể, dùng **JMC Flight Recorder configuration** hoặc tạo `.jfc` riêng trên cơ sở template `default`/`profile`; xác minh event setting thực bằng JFR metadata và cấu hình recording. Không chỉnh trực tiếp template chuẩn do JDK cung cấp.

### `default` và `profile` không đảm bảo mọi event đều được thu

- `settings=default`: tối ưu overhead thấp, thường phù hợp ghi liên tục.
- `settings=profile`: thường thu nhiều dữ liệu hơn, phù hợp điều tra ngắn với chi phí cao hơn.
- Một số event có **threshold khoảng vài đến vài chục mili giây** (các ví dụ Oracle thường dùng 20 ms cho event I/O/monitor thông dụng), nhưng giá trị đúng phải **đọc từ `.jfc`/recording phiên bản đang chạy**.
- Event dưới threshold bị bỏ qua; các event bị tắt, sample chưa được lấy, event bị throttle, thời điểm chưa được ghi, hoặc dữ liệu bị mất đều có thể tạo “khoảng trống”.

**Chiến lược điều tra có kiểm soát:** trước tiên thu ngắn bằng `profile`; nếu loại event cần thiết bị thiếu, chỉ bật đúng nhóm liên quan và giảm threshold có giới hạn thời gian, đo thêm CPU/overhead/dung lượng recording. Tránh `threshold=0` cho mọi event trong sản xuất liên tục.

## 10. Bài thực hành Java 17+: tạo những tín hiệu JFR có kiểm soát

Ví dụ này chủ động tạo **tranh chấp monitor**, `Object.wait()`, park, sleep, file I/O, socket I/O qua **loopback của chính máy**, và một exception được bắt. Nó ghi file để bạn tự phân tích; các event cụ thể và duration phụ thuộc scheduling, JDK, công cụ và hệ điều hành.

Tạo file **`JfrSignalsDemo.java`**:

```java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.LockSupport;
import jdk.jfr.Recording;

public class JfrSignalsDemo {
    private static final Object MONITOR = new Object();

    public static void main(String[] args) throws Exception {
        Path file = Path.of("jfr-signals-demo.jfr").toAbsolutePath();

        try (Recording recording = new Recording()) {
            for (String name : List.of(
                    "jdk.JavaMonitorEnter", "jdk.JavaMonitorWait",
                    "jdk.ThreadPark", "jdk.ThreadSleep",
                    "jdk.FileRead", "jdk.FileWrite",
                    "jdk.SocketRead", "jdk.SocketWrite")) {
                recording.enable(name)
                        .withThreshold(Duration.ZERO)
                        .withStackTrace();
            }
            recording.enable("jdk.ThreadStart");
            recording.enable("jdk.ThreadEnd");
            recording.enable("jdk.JavaExceptionThrow")
                    .withStackTrace();

            recording.start();
            createMonitorContention();
            synchronized (MONITOR) {
                MONITOR.wait(70);
            }
            LockSupport.parkNanos(TimeUnit.MILLISECONDS.toNanos(70));
            touchFile();
            touchLoopbackSocket();

            try {
                throw new IllegalArgumentException("demo-handled");
            } catch (IllegalArgumentException expected) {
                // Đã xử lý lỗi: vẫn có thể được ghi dưới dạng throw event.
            }

            recording.stop();
            recording.dump(file);
        }

        System.out.println("recording=jfr-signals-demo.jfr");
    }

    private static void createMonitorContention()
            throws InterruptedException {
        CountDownLatch locked = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread owner = new Thread(() -> {
            synchronized (MONITOR) {
                locked.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "demo-monitor-owner");

        Thread contender = new Thread(() -> {
            synchronized (MONITOR) {
                // Chỉ vào monitor sau khi owner nhả khóa.
            }
        }, "demo-monitor-contender");

        owner.start();
        locked.await();
        contender.start();
        Thread.sleep(160);
        release.countDown();
        owner.join();
        contender.join();
    }

    private static void touchFile() throws Exception {
        Path path = Files.createTempFile("jfr-demo-", ".bin");
        try {
            Files.write(path, new byte[8192]);
            try (InputStream input = Files.newInputStream(path)) {
                input.readAllBytes();
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }

    private static void touchLoopbackSocket() throws Exception {
        try (ServerSocket server = new ServerSocket(
                0, 1, InetAddress.getLoopbackAddress())) {
            Thread peer = new Thread(() -> {
                try (Socket accepted = server.accept()) {
                    Thread.sleep(120);
                    accepted.getOutputStream().write(42);
                } catch (Exception e) {
                    throw new RuntimeException(e);
                }
            }, "demo-loopback-peer");

            peer.start();
            try (Socket client = new Socket(
                    InetAddress.getLoopbackAddress(),
                    server.getLocalPort())) {
                int received = client.getInputStream().read();
                if (received != 42) {
                    throw new IllegalStateException(
                            "Unexpected byte: " + received);
                }
            }
            peer.join();
        }
    }
}
```

Biên dịch và chạy (JDK 17+; cần được phép mở **localhost/loopback socket**):

```bash
javac --release 17 JfrSignalsDemo.java
java JfrSignalsDemo
```

Nếu chương trình chạy thành công, dòng output cuối **chính xác** là:

```text
recording=jfr-signals-demo.jfr
```

Kết quả có thể khác về **số event, thứ tự, duration và field** do nội dung JDK, thời điểm được lấy mẫu và buffering. `Thread.sleep(160)` nhằm làm tranh chấp dễ quan sát hơn, nhưng scheduler vẫn có thể khiến contender không kịp chờ đủ lâu. File read/write thường rất nhanh; dù đặt threshold 0, việc một event có được sinh ra hay không vẫn phụ thuộc code path/JVM instrumentation.

**Giải thích những gì chương trình làm:**

1. Bật các **duration event** với threshold 0 và stack trace để demo có cơ hội ghi thao tác ngắn. Đây là setting dành cho bài lab, không khuyến khích giữ trong production.
2. Thread `demo-monitor-owner` giữ `MONITOR` rồi chờ latch. Thread `demo-monitor-contender` cố vào `synchronized`, tạo khả năng xuất hiện `jdk.JavaMonitorEnter`.
3. `MONITOR.wait(70)` là chờ điều kiện trên monitor; `LockSupport.parkNanos` là park; `Thread.sleep` tạo sleep. Ba cách chờ **có ngữ nghĩa khác nhau**.
4. `Files.write`/`Files.newInputStream` minh họa file I/O; `ServerSocket`/`Socket` giao tiếp **trong máy** và cố ý để peer gửi muộn để có socket read duration.
5. Exception được ném rồi catch; nó thể hiện chính xác vì sao **throw event không đồng nghĩa unhandled error**.
6. `recording.stop()` và `recording.dump(file)` lưu recording để đọc bằng tool.

Kiểm tra loại event thực sự có mặt:

```bash
jfr summary jfr-signals-demo.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark --stack-depth 20 jfr-signals-demo.jfr
jfr print --events jdk.FileRead,jdk.FileWrite,jdk.SocketRead,jdk.SocketWrite --stack-depth 20 jfr-signals-demo.jfr
jfr print --events jdk.JavaExceptionThrow --stack-depth 20 jfr-signals-demo.jfr
```

**Bài tập:** tăng `Thread.sleep(160)` thành `400` ms và so hai lần recording. Bạn kỳ vọng độ chờ monitor lớn hơn nếu contender đã bắt đầu tranh chấp đúng lúc; nhưng nếu có event khác ảnh hưởng scheduling, cần đọc thời điểm trên JFR để xác minh, không chỉ nhìn con số tổng.

## 11. Đọc và nhóm event bằng API `jdk.jfr.consumer` (Java 17+)

Khi file có nhiều event, bạn có thể phân tích **loại, count, duration**, rồi xem vài mẫu có thread/stack. Đây là một chương trình độc lập, không cần dependency ngoài JDK.

Tạo file **`JfrSignalSummary.java`**:

```java
import java.nio.file.Path;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordedFrame;
import jdk.jfr.consumer.RecordedStackTrace;
import jdk.jfr.consumer.RecordedThread;
import jdk.jfr.consumer.RecordingFile;

public class JfrSignalSummary {
    private static final Set<String> INTERESTING = Set.of(
            "jdk.JavaMonitorEnter", "jdk.JavaMonitorWait",
            "jdk.ThreadPark", "jdk.ThreadSleep",
            "jdk.FileRead", "jdk.FileWrite",
            "jdk.SocketRead", "jdk.SocketWrite",
            "jdk.JavaExceptionThrow", "jdk.JavaErrorThrow");

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println(
                    "Usage: java JfrSignalSummary <recording.jfr>");
            return;
        }

        Map<String, Long> counts = new TreeMap<>();
        Map<String, Long> totalNanos = new TreeMap<>();
        int examples = 0;

        try (RecordingFile file = new RecordingFile(Path.of(args[0]))) {
            while (file.hasMoreEvents()) {
                RecordedEvent e = file.readEvent();
                String type = e.getEventType().getName();

                if (!INTERESTING.contains(type)) {
                    continue;
                }

                counts.merge(type, 1L, Long::sum);
                totalNanos.merge(
                        type, e.getDuration().toNanos(), Long::sum);

                if (examples < 8) {
                    examples++;
                    RecordedThread thread = e.getThread();
                    String threadName = thread == null
                            ? "(unknown)"
                            : thread.getJavaName();

                    System.out.println(
                            type + " start=" + e.getStartTime()
                            + " duration=" + e.getDuration()
                            + " thread=" + threadName);

                    for (String field : new String[]{
                            "monitorClass", "previousOwner",
                            "path", "bytesRead", "bytesWritten",
                            "host", "address", "port",
                            "thrownClass", "message"}) {
                        if (e.hasField(field)) {
                            System.out.println(
                                    "  " + field + "="
                                    + String.valueOf(e.getValue(field)));
                        }
                    }

                    RecordedStackTrace trace = e.getStackTrace();
                    if (trace != null && !trace.getFrames().isEmpty()) {
                        RecordedFrame frame = trace.getFrames().get(0);
                        if (frame.getMethod() != null) {
                            System.out.println(
                                    "  topFrame="
                                    + frame.getMethod().getType().getName()
                                    + "." + frame.getMethod().getName());
                        }
                    }
                }
            }
        }

        System.out.println("=== Recorded-event totals ===");
        for (Map.Entry<String, Long> entry : counts.entrySet()) {
            String type = entry.getKey();
            double millis = totalNanos.get(type) / 1_000_000.0;
            System.out.printf(
                    "%s count=%d summedDurationMs=%.3f%n",
                    type, entry.getValue(), millis);
        }
    }
}
```

Biên dịch và chạy sau khi đã tạo `jfr-signals-demo.jfr`:

```bash
javac --release 17 JfrSignalSummary.java
java JfrSignalSummary jfr-signals-demo.jfr
```

Chương trình sẽ in một số event đầu tiên tìm được, rồi **đếm theo type** và tính **tổng duration các event thuộc type đó**. Không thể đưa số liệu stdout cố định vì JVM/scheduling/recording khác nhau. Hai tình huống đều hợp lệ:

- Một event type không xuất hiện: chương trình **không có dòng tổng** của type đó.
- Exception throw: thường có `duration=PT0S` hoặc duration bằng 0; không dùng tổng duration của exception để đo “thời gian xử lý lỗi”.

**Các giới hạn quan trọng của mẫu parser:**

- `totalNanos` là **tổng duration của các event được ghi**, không phải elapsed time của hệ thống; có thể chồng lặp nhiều thread.
- Chương trình **không** tính p95/p99, phân tách theo path/endpoint/monitor hay correlation ID; production analytics cần thêm grouping và chú ý sampling/threshold.
- Dùng `e.hasField(...)` trước `getValue(...)` vì mỗi event type có schema khác nhau.
- `getThread()` và `getStackTrace()` có thể là `null`. Top stack frame không nhất thiết là root cause.
- `RecordingFile` duyệt theo stream và không giữ tất cả event trong RAM; phù hợp hơn `readAllEvents()` cho file lớn.

## 12. Phân tích ca thực tế: p99 tăng sau một thay đổi

Giả sử trong 10 phút, request p99 tăng từ 150 ms lên 1.100 ms. JFR cho thấy kết quả **minh họa**:

| Nhóm quan sát | Trước deploy | Sau deploy | Điều cần xác minh |
| --- | --- | --- | --- |
| `JavaMonitorEnter` tại `CacheStore.update()` | Hiếm, dưới 10 ms | Nhiều, 200–450 ms | Có giữ monitor trong lúc gọi I/O/serialize không? |
| `SocketRead` đến backend API | 70–110 ms | 80–120 ms | Độ trễ mạng không tăng tương xứng; có thể không phải nghi phạm chính. |
| `ThreadPark` ở worker | Chủ yếu lúc idle | Tăng cùng queue backlog | Queue nghẽn hậu quả của bottleneck hay nguyên nhân? |
| `JavaExceptionThrow` `TimeoutException` | Thấp | Tăng | Timeout có thể là **hệ quả** của request chậm, chưa chắc nguyên nhân. |

Không được kết luận mọi thứ từ bảng này. Quy trình kiểm chứng:

1. **Đồng bộ thời gian** JFR, log, metrics (múi giờ, deploy timestamp, recording window).
2. **Xác nhận event enabled/threshold** giống nhau giữa hai recording. Nếu không, số count không so trực tiếp được.
3. Từ `JavaMonitorEnter`, xem stack và owner, đối chiếu mã sau deploy. Nếu có I/O chạy **bên trong `synchronized`**, đó là một giả thuyết mạnh.
4. Xem thread dump / JFR thread/CPU khác để kiểm tra owner có thực sự giữ monitor lâu và các request bị xếp hàng.
5. Thử bản sửa phù hợp (ví dụ đưa I/O ra ngoài critical section khi thread safety cho phép), đo lại p99 và lock wait.
6. Nếu lock wait giảm mà p99 vẫn cao, tiếp tục điều tra socket, queue, GC và retry. **Không áp đặt nguyên nhân** trước khi số liệu trước/sau hỗ trợ.

Ví dụ minh họa giúp thấy sự khác nhau giữa **nguyên nhân** (lock kéo dài), **triệu chứng** (p99 tăng/queue) và **hậu quả** (`TimeoutException`), nhưng trên một hệ thống thật cả ba vị trí có thể khác.

## 13. Những lỗi diễn giải phổ biến

| Kết luận vội | Cách hiểu có cơ sở |
| --- | --- |
| “Thấy `JavaMonitorWait` dài nên bị tranh chấp `synchronized`.” | `JavaMonitorWait` gắn với `Object.wait`; điều tra điều kiện notify/timeout. Để tìm chờ **vào monitor**, xem `JavaMonitorEnter`. |
| “Có `ThreadPark` nghĩa là deadlock.” | Park có thể là idle worker/chờ task/lock/future bình thường; cần biết ai có trách nhiệm unpark và workload. |
| “RUNNABLE chắc chắn đang ăn CPU.” | RUNNABLE có thể chỉ sẵn sàng chạy; xem CPU samples/load và scheduling. |
| “Không có event lock nên chắc chắn không có contention.” | Event có thể disabled, bị threshold lọc, hoặc lock dùng abstraction khác như `ReentrantLock`. |
| “JFR timeline xanh/đoạn trống nghĩa thread đang chạy CPU.” | Khoảng trống có thể do thiếu event hoặc sampling; kết hợp CPU/event settings. |
| “SocketRead lâu là network chậm.” | Có thể peer chưa gửi dữ liệu, app đọc sớm, scheduling, timeout; cần server log/trace/network metrics. |
| “FileWrite 2 s nghĩa đĩa đang ghi 2 s.” | Có buffer, cache, filesystem, native I/O; event đo đoạn code được instrument, không phải phép đo disk vật lý. |
| “`JavaExceptionThrow` là request fail.” | Nhiều throw được catch/handle; cần response/error rate và correlation. |
| “Tổng duration event là thời gian JVM bị chặn.” | Duration nhiều thread chồng nhau; cộng thời gian event không bằng wall time. |
| “`--stack-depth 100` sẽ hiện cả stack đã không ghi.” | Tham số chỉ điều khiển số frame **in ra**; không phục hồi dữ liệu chưa thu. |
| “Không thấy event trong recording thì thao tác không có.” | Kiểm tra time window, enabled, threshold, throttle, sampling, JVM/JDK support, data loss. |
| “Thread name đủ để nối tất cả event thành một request.” | Thread pool tái sử dụng thread, virtual thread có vòng đời riêng; cần request ID/tracing. |

## 14. Checklist điều tra nhanh

- [ ] Xác định **PID/JVM**, JDK, recording window và thời điểm người dùng thấy lỗi.
- [ ] Chạy **`jfr summary`**, xác minh event types, số lượng và settings.
- [ ] Lọc **lock/park/wait/sleep** theo duration, thread, stack, owner và thời gian.
- [ ] Lọc **file/socket** theo path/endpoint, bytes, duration, thread và stack; đối chiếu hạ tầng.
- [ ] Lọc **exception/error** theo class, call site, xu hướng và xử lý thực tế của request.
- [ ] Phân biệt **elapsed duration**, **CPU sample**, **thread state** và **wall-clock**.
- [ ] Không suy leak/deadlock/network failure từ một event duy nhất.
- [ ] Nếu thiếu dữ liệu, điều chỉnh **đúng event/threshold** trong recording ngắn và đo overhead.
- [ ] Kiểm tra với log, metrics, request correlation, thread dump, tracing hoặc thử nghiệm trước/sau.
- [ ] Lưu file `.jfr` theo quyền bảo mật vì stack/path/exception message có thể nhạy cảm.

## 15. Câu hỏi tự kiểm tra

1. **Khác nhau chính giữa `jdk.JavaMonitorEnter` và `jdk.JavaMonitorWait` là gì?** `JavaMonitorEnter` đo chờ để **vào intrinsic monitor** khi có contention; `JavaMonitorWait` liên quan `Object.wait()` trên monitor và chờ điều kiện.
2. **Tại sao `ReentrantLock` có thể liên quan `ThreadPark` mà không có `JavaMonitorEnter`?** Nó dùng cơ chế đồng bộ/park của `java.util.concurrent`, không nhất thiết chờ vào Java intrinsic monitor.
3. **Một `SocketRead` duration 900 ms có chứng minh mạng lỗi không?** Không; có thể là peer gửi chậm, ứng dụng đọc sớm, scheduling hoặc network. Cần đối chiếu endpoint/trace/metrics.
4. **Một exception event có đồng nghĩa response lỗi không?** Không; exception có thể đã được catch và xử lý hợp lệ.
5. **Vì sao không thấy `FileRead` không đủ kết luận không có file I/O?** Event có thể bị tắt, threshold, code path không được instrument, sampling hoặc recording không bao trùm lúc thao tác diễn ra.
6. **Có thể cộng duration của mọi thread để suy elapsed time không?** Không. Nhiều event có thể chồng thời gian.
7. **Điểm đầu tiên cần làm với file JFR lạ là gì?** `jfr summary` để biết recording thực sự có gì; tiếp theo `jfr metadata`/filter phù hợp.
8. **Một thread ở `WAITING` có luôn là bug?** Không; idle worker, wait/park bình thường vẫn có thể là `WAITING`. Phải xem vai trò thread và điều kiện đánh thức.

## Tài liệu tham khảo

- [Oracle Java 21 — The `jfr` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): `summary`, `print`, `metadata`, lọc event, stack depth và JSON.
- [Oracle Java 21 — The `jcmd` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`.
- [Oracle — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshoot-performance-issues-using-jfr.html): lock, I/O, exception và cách đọc event chờ.
- [Oracle Java 21 — JFR Event Settings](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html): `enabled`, `threshold`, `stackTrace`, `period`.
- [Oracle Java 21 — `RecordedEvent`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): `getStartTime`, `getDuration`, `getThread`, `getStackTrace`.
- [Oracle Java 21 — `RecordingFile` và đọc file JFR](https://docs.oracle.com/en/java/javase/21/jfapi/parsing-recording-file.html).
- [Oracle Java 21 — `Recording` / `EventSettings`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html).
