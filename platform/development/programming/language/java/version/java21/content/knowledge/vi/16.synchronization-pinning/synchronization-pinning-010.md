# Kiểm tra deadlock, starvation và tranh chấp tài nguyên ngoài thread

## 1. Phân biệt ba vấn đề

Khi ứng dụng chậm, treo hoặc không xử lý được request mới, nguyên nhân không nhất thiết nằm ở `synchronized`, `Lock` hay scheduler của JVM. Một request có thể đang chờ connection database, slot trong HTTP connection pool, distributed lock, hàng đợi hoặc giới hạn của dịch vụ bên ngoài. Cần phân biệt ba dạng vấn đề trước khi điều tra.

| Hiện tượng | Bản chất | Dấu hiệu thường gặp |
|---|---|---|
| **Deadlock** | Hai hay nhiều tác nhân chờ tài nguyên do tác nhân khác giữ, tạo thành chu trình không thể tự tiến triển | Một nhóm thread/task chờ nhau; không có tác nhân nào trong chu trình có thể giải phóng tài nguyên |
| **Starvation** | Một tác nhân liên tục không nhận được tài nguyên hoặc thời gian thực thi cần thiết, trong khi tác nhân khác vẫn tiến triển | Một số request chờ rất lâu, bị đói permit/lock/CPU; hệ thống vẫn có hoạt động |
| **Resource contention** | Nhiều tác nhân cạnh tranh cùng tài nguyên có năng lực hữu hạn | Queue tăng, thời gian chờ và latency tăng, throughput chạm trần; hệ thống vẫn có thể hoàn tất công việc |

Ba hiện tượng có thể xuất hiện đồng thời. Ví dụ, connection pool bị bão hòa gây contention; nếu các tác vụ giữ application lock trong lúc chờ connection và tác vụ khác giữ connection trong lúc chờ application lock, contention có thể phát triển thành deadlock.

Không nên kết luận deadlock chỉ từ việc một thread ở trạng thái `WAITING` hoặc `BLOCKED`. Chờ là hành vi bình thường trong hệ thống đồng thời. Cần xác định thread đang chờ điều gì, ai giữ tài nguyên và liệu có chu trình phụ thuộc hay không.

## 2. Deadlock trong JVM: chu trình giữa các lock

Deadlock cổ điển thường xảy ra khi các thread lấy nhiều lock theo thứ tự khác nhau. Mỗi thread giữ một lock và chờ lock còn lại.

```java
private static final Object accountLock = new Object();
private static final Object ledgerLock = new Object();

// Thread A gọi method này.
static void updateAccount() {
    synchronized (accountLock) {
        synchronized (ledgerLock) {
            updateAccountAndLedger();
        }
    }
}

// Thread B gọi method này.
static void reconcileLedger() {
    synchronized (ledgerLock) {
        synchronized (accountLock) {
            reconcileLedgerAndAccount();
        }
    }
}
```

Nếu Thread A lấy `accountLock` trước và Thread B lấy `ledgerLock` trước, A sẽ chờ `ledgerLock` trong khi B chờ `accountLock`. Cả hai đều không thể đi tới đoạn code giải phóng lock.

Deadlock cũng có thể liên quan đến `ReentrantLock`, `ReentrantReadWriteLock` hoặc các synchronizer triển khai `java.util.concurrent.locks.OwnableSynchronizer`. Khi điều tra, không chỉ tìm từ khóa `synchronized`; cần xem cả stack trace, lock đang chờ và lock đang được giữ.

### 2.1. Cách ngăn deadlock do thứ tự lock

Một quy tắc hiệu quả là áp dụng **thứ tự lấy lock toàn cục**. Nếu mọi đoạn code đều lấy `accountLock` trước `ledgerLock`, sẽ không có đường đi ngược tạo chu trình giữa hai lock này.

Các biện pháp khác:

- Tránh lấy nhiều lock cùng lúc nếu có thể thiết kế lại để chỉ cần một lock.
- Nếu dùng `ReentrantLock`, cân nhắc `tryLock` có timeout để không chờ vô hạn; khi thất bại, giải phóng lock đã lấy và xử lý retry hoặc báo lỗi theo chính sách.
- Không gọi dịch vụ mạng, database hoặc callback không kiểm soát trong khi đang giữ application lock.
- Giữ vùng critical section ngắn và tránh gọi code bên ngoài khi đang giữ lock.
- Với nhiều tài nguyên, ghi rõ thứ tự acquire/release trong thiết kế và code review.

Timeout có thể giúp một tác vụ thoát khỏi việc chờ vô hạn, nhưng không tự sửa được thiết kế gây deadlock. Nếu retry ngay và liên tục, ứng dụng có thể tạo thêm contention. Cần có backoff, giới hạn retry và cách phục hồi trạng thái nhất quán.

## 3. Phát hiện deadlock bằng `ThreadMXBean`

`java.lang.management.ThreadMXBean` cung cấp API để tìm deadlock giữa các **platform thread** trong JVM. `findDeadlockedThreads()` phát hiện chu trình liên quan đến object monitor và ownable synchronizer. Nếu không tìm thấy, method trả về `null`.

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;

static void reportPlatformThreadDeadlocks() {
    ThreadMXBean bean = ManagementFactory.getThreadMXBean();
    long[] threadIds = bean.findDeadlockedThreads();

    if (threadIds == null) {
        System.out.println("No platform-thread deadlock detected");
        return;
    }

    ThreadInfo[] infos = bean.getThreadInfo(threadIds, true, true);
    for (ThreadInfo info : infos) {
        if (info != null) {
            System.err.println(info);
        }
    }
}
```

`getThreadInfo(ids, true, true)` yêu cầu thông tin về monitor và synchronizer đang được giữ. Cách này hữu ích khi cần phát hiện hoặc ghi log deadlock định kỳ trong một dịch vụ chạy lâu.

**Giới hạn quan trọng:** `ThreadMXBean` là API quản lý platform thread và không cung cấp đầy đủ quan sát cho virtual thread trong Java 21. Ngoài ra, nó chỉ tìm chu trình lock mà JVM quản lý; nó không tự phát hiện deadlock ở database, connection pool, dịch vụ từ xa, distributed lock hay hàng đợi ứng dụng. Kết quả `null` không chứng minh toàn hệ thống không deadlock.

## 4. Thread dump và công cụ chẩn đoán trong Java 21

Thread dump cho biết thread đang chạy ở đâu, đang chờ ở stack frame nào và trong một số định dạng có thể cho thấy lock liên quan. Với ứng dụng Java 21 sử dụng nhiều virtual thread, cần chọn công cụ phù hợp.

### 4.1. Platform thread và monitor/synchronizer

Có thể lấy thread dump truyền thống bằng `jcmd`:

```bash
jcmd <pid> Thread.print
```

Dump này hữu ích để tìm các platform thread ở trạng thái `BLOCKED`, `WAITING` hoặc `TIMED_WAITING`, xem stack trace và quan hệ monitor/synchronizer. Lấy nhiều dump cách nhau vài giây giúp phân biệt một lần chờ ngắn bình thường với trạng thái bị kẹt kéo dài.

### 4.2. Virtual thread

Trong JDK 21, lệnh `Thread.dump_to_file` được cung cấp để tạo thread dump có thể bao gồm virtual thread:

```bash
jcmd <pid> Thread.dump_to_file -format=json threads.json
```

Có thể dùng định dạng text nếu phù hợp với công cụ xử lý. Dump này giúp tìm số lượng virtual thread, stack trace và các điểm chờ như semaphore, socket hoặc lock. Đừng giả định dump virtual thread có đầy đủ thông tin monitor ownership giống mọi định dạng dump truyền thống; kết hợp thêm JFR và metrics của tài nguyên đang chờ.

Thread dump có thể rất lớn khi ứng dụng tạo hàng chục nghìn virtual thread. Hãy lưu cùng timestamp, PID, phiên bản JDK và tình trạng tải để đối chiếu. Không chia sẻ dump chứa tên thread, đường dẫn hoặc thông tin nội bộ ra ngoài phạm vi cần thiết.

### 4.3. Java Flight Recorder (JFR)

JFR giúp quan sát sự kiện runtime trong một khoảng thời gian, phù hợp để xác định thread thường xuyên chờ monitor, park, socket hoặc file I/O. Có thể ghi một bản profile có thời hạn:

```bash
jcmd <pid> JFR.start name=concurrency settings=profile duration=2m filename=concurrency.jfr
jfr summary concurrency.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.ThreadPark,jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite,jdk.VirtualThreadPinned concurrency.jfr
```

Các event cần quan tâm gồm:

- `jdk.JavaMonitorEnter`: thời gian và tình huống chờ vào intrinsic monitor.
- `jdk.ThreadPark`: thread bị park, thường liên quan đến lock hoặc synchronizer.
- `jdk.SocketRead` và `jdk.SocketWrite`: thời gian thực hiện socket I/O ở các API được instrument.
- `jdk.FileRead` và `jdk.FileWrite`: hoạt động file I/O được ghi nhận.
- `jdk.VirtualThreadPinned`: sự kiện virtual thread bị pin trong carrier thread trên runtime Java 21.

JFR cho thấy thời điểm và stack liên quan đến các event được ghi nhận; nó không tự biết ý nghĩa nghiệp vụ của mọi lần chờ. Ví dụ, event socket không cho biết trực tiếp request đang chờ quota của dịch vụ nào, còn thời gian chờ connection trong một JDBC pool có thể chỉ xuất hiện như stack ở thư viện pool. Cần kết hợp tracing và metrics của ứng dụng.

## 5. Deadlock có thể nằm ngoài JVM

Không phải mọi chu trình chờ đều được tạo bởi Java lock. Ứng dụng có thể deadlock qua nhiều loại tài nguyên:

- **Database transaction**: transaction A giữ row lock X và chờ row lock Y; transaction B giữ Y và chờ X.
- **Connection pool**: task giữ application lock rồi chờ connection; task khác giữ connection nhưng cần application lock trước khi hoàn tất và trả connection.
- **Distributed lock**: service A giữ lock ở hệ thống ngoài rồi chờ service B; service B lại chờ tài nguyên hoặc lock mà A đang giữ.
- **Hàng đợi và worker**: mọi worker đang chờ kết quả của task mới được xếp vào chính hàng đợi mà chúng đang xử lý.
- **File hoặc thiết bị**: một tiến trình giữ file lock hoặc tài nguyên thiết bị trong khi chờ một tiến trình khác đang chờ tài nguyên ngược lại.

Ví dụ chu trình giữa application lock và connection pool:

1. Task A lấy `orderLock`, sau đó chờ một connection từ pool.
2. Task B đã lấy connection, sau đó cần `orderLock` để cập nhật trạng thái.
3. A không thể lấy connection vì B đang giữ; B không thể tiếp tục và trả connection vì chờ lock do A giữ.

Thread dump có thể cho thấy A ở stack lấy connection và B ở stack chờ monitor. Nhưng để xác nhận chu trình, phải kiểm tra thêm pool đang có bao nhiêu connection active/idle, ai đang giữ connection và transaction/query tương ứng.

Với database deadlock, hãy xem deadlock report hoặc lock wait graph từ chính database. Database thường có cơ chế phát hiện chu trình transaction và chọn một transaction làm victim; JVM không thể thay thế việc quan sát này.

Với distributed lock, cần kiểm tra owner, lease/expiry, fencing token và log của các service liên quan. Một timeout của client không chứng minh lock đã được giải phóng ở hệ thống từ xa.

## 6. Starvation: một tác vụ không được phục vụ

Starvation xảy ra khi một thread hoặc task liên tục không lấy được tài nguyên cần thiết hoặc không có cơ hội chạy đủ để hoàn tất, trong khi những task khác vẫn tiến triển.

Nguyên nhân thường gặp:

- Lock hoặc semaphore không công bằng khiến một số tác vụ liên tục bị vượt mặt.
- Một thread giữ lock quá lâu hoặc liên tục chiếm critical section.
- Thread pool có số worker cố định và tất cả worker đang block chờ task khác được xếp vào cùng pool.
- Task ưu tiên thấp bị task ưu tiên cao chiếm CPU liên tục.
- Một nhóm request liên tục lấy hết connection hoặc permit, khiến nhóm khác phải chờ.
- Retry không có backoff làm một số tác vụ liên tục cạnh tranh và bị đẩy lùi.

Starvation khác deadlock ở chỗ hệ thống vẫn có thể tiến triển. Có thể thấy request A chờ rất lâu trong khi request B, C và D liên tục hoàn tất. Nếu toàn bộ tác nhân trong một chu trình không thể tiến triển, cần nghi ngờ deadlock.

### 6.1. Starvation trong thread pool

Một lỗi phổ biến với executor có số worker cố định là worker đang chạy task cha lại block chờ task con được submit vào cùng executor. Nếu tất cả worker đều làm như vậy, không còn worker rảnh để chạy task con.

```java
// Mô tả tình huống nguy hiểm trong fixed-size executor.
Future<Integer> parent = executor.submit(() -> {
    Future<Integer> child = executor.submit(this::calculate);
    return child.get(); // Worker cha giữ chỗ trong khi chờ worker chạy child
});
```

Nếu pool có một worker và worker đó đang chờ `child.get()`, task con không bao giờ được chạy. Đây là thread-starvation deadlock do cách tổ chức task và executor.

Hướng xử lý:

- Tránh block worker để chờ task con được submit vào cùng pool.
- Dùng composition bất đồng bộ như `CompletableFuture.thenCompose` thay vì `get()` lồng nhau.
- Tách executor theo loại công việc nếu có lý do rõ ràng và quản lý vòng đời phù hợp.
- Không tăng pool size một cách mù quáng; việc đó có thể chỉ đẩy điểm nghẽn sang database hoặc dịch vụ bên ngoài.

Với virtual thread, không có một nhóm nhỏ worker virtual thread cố định cần tái sử dụng. Tuy vậy, task vẫn có thể starvation do semaphore, connection pool, lock, quota hoặc dịch vụ downstream. Virtual thread không loại bỏ các giới hạn đó.

### 6.2. Fairness không giải quyết mọi starvation

`ReentrantLock(true)` và `Semaphore(permits, true)` có thể áp dụng chính sách fairness cho thread đang chờ tại synchronizer tương ứng. Fairness giúp giảm việc thread mới liên tục vượt mặt thread cũ, nhưng có thể giảm throughput và không bảo đảm thứ tự hoàn tất.

Fairness của Java lock cũng không điều khiển thứ tự cấp connection của JDBC pool, thứ tự xử lý của database, quota của remote API hay lịch chạy của hệ điều hành. Mỗi tầng có chính sách riêng; phải kiểm tra đúng tài nguyên gây chờ.

## 7. Tranh chấp tài nguyên ngoài thread

Một ứng dụng có thể có nhiều virtual thread đang chạy nhưng throughput vẫn thấp vì tất cả cùng chờ một tài nguyên bên ngoài. Các nhóm tài nguyên phổ biến gồm:

| Tài nguyên | Chỉ số cần quan sát | Dấu hiệu contention |
|---|---|---|
| Database connection pool | Active, idle, pending borrowers, acquisition latency, timeout | Pool luôn hết connection, thời gian chờ lấy connection tăng |
| Database engine | Query latency, lock wait, deadlock, active transaction, slow query | Connection đã lấy được nhưng query chậm hoặc chờ row/table lock |
| HTTP client connection pool | Leased/available/pending connections, connect/read latency | Task chờ connection hoặc response từ upstream |
| Remote service/API quota | Request rate, 429/503, latency, retry count, timeout | Bị throttling, retry tăng, thời gian response tăng |
| File system/storage | I/O latency, queue depth, throughput, lock wait | Nhiều tác vụ chờ đọc/ghi hoặc file lock |
| CPU và GC | CPU utilization, run queue, allocation rate, pause time | Task sẵn sàng chạy nhưng thiếu CPU hoặc bị ảnh hưởng bởi GC |
| Application queue | Queue depth, oldest task age, enqueue/dequeue rate | Công việc chờ tăng nhanh hơn tốc độ xử lý |

Thread dump có thể chỉ ra vị trí thread đang chờ, nhưng không cho biết đầy đủ capacity, queue depth hoặc nguyên nhân bên trong hệ thống bên ngoài. Hãy ghép stack trace với metrics ở đúng tầng tài nguyên.

### 7.1. Database connection pool bị bão hòa

Khi số connection active chạm giới hạn và số borrower đang chờ tăng, các request mới có thể mất phần lớn thời gian ở bước lấy connection. Nếu connection bị giữ lâu do transaction kéo dài, query chậm hoặc code thực hiện network call khi đang giữ connection, pool sẽ nhanh chóng bão hòa.

Kiểm tra:

- Thời gian chờ lấy connection riêng biệt với thời gian chạy query.
- Số connection active/idle/pending và số lần acquisition timeout.
- Transaction mở lâu, query chậm, row lock và deadlock trong database.
- Đường code có giữ connection trong lúc gọi API khác hoặc chờ user input hay không.

Giải pháp thường là rút ngắn transaction, đóng connection/result set đúng cách, tối ưu query/index, không giữ connection khi thực hiện công việc không liên quan đến database và điều chỉnh pool theo capacity thực tế của database.

### 7.2. Remote API hoặc HTTP connection pool bị nghẽn

Một service bên ngoài có thể chậm, giới hạn số kết nối hoặc trả `429 Too Many Requests`. Nếu ứng dụng retry ngay, số request mới tăng lên và làm contention nghiêm trọng hơn.

Hãy tách thời gian chờ connection, DNS/connect, TLS handshake, thời gian response và thời gian xử lý nội bộ. Áp dụng timeout phù hợp, retry có exponential backoff và jitter, giới hạn concurrency bằng semaphore/bulkhead, đồng thời tôn trọng `Retry-After` nếu upstream cung cấp.

### 7.3. Distributed lock và tài nguyên chia sẻ

Với distributed lock, cần theo dõi thời gian giữ lock, thời gian chờ, owner, lease expiry và các lần acquire thất bại. Lease hết hạn không tự động bảo đảm một client cũ đã ngừng ghi dữ liệu. Hệ thống có thể cần fencing token hoặc version để từ chối thao tác đến muộn từ owner cũ.

Với file lock, object storage hoặc tài nguyên thiết bị, hãy quan sát cả hệ điều hành và dịch vụ cung cấp tài nguyên. JVM thread dump thường chỉ cho biết thread đang nằm trong lời gọi thư viện; nó không thay thế công cụ chẩn đoán ở hệ thống ngoài.

## 8. Vai trò của virtual thread và pinning trong điều tra

Virtual thread giúp xử lý nhiều tác vụ chờ I/O với ít platform thread hơn. Tuy nhiên, nó không làm tăng số connection database, số kết nối HTTP, quota API hoặc throughput của storage.

Trong Java 21, virtual thread có thể bị **pin** vào carrier thread khi thực hiện blocking operation trong một số vùng như `synchronized` hoặc native/foreign method. Nếu nhiều virtual thread bị pin trong lúc chờ, carrier thread bị giữ và khả năng tiến triển của scheduler có thể bị ảnh hưởng.

Khi nghi ngờ pinning:

- Xem event `jdk.VirtualThreadPinned` trong JFR.
- Kiểm tra stack trace để xác định blocking call đang nằm trong synchronized region hay native/foreign call.
- Tránh giữ intrinsic monitor trong lúc gọi I/O blocking; rút ngắn vùng synchronized và tách phần I/O ra ngoài lock khi an toàn về mặt dữ liệu.
- Đánh giá thư viện native/driver đang dùng và cập nhật phiên bản phù hợp nếu có cách khắc phục.

Không nhầm pinning với resource contention bên ngoài. Pinning mô tả việc virtual thread giữ carrier thread; contention mô tả nhiều tác vụ tranh cùng tài nguyên. Một request có thể đồng thời bị pin và chờ database, nhưng hai vấn đề cần bằng chứng và cách xử lý khác nhau.

## 9. Quy trình điều tra có hệ thống

Khi latency tăng hoặc request bị treo, có thể đi theo quy trình sau:

1. **Xác định phạm vi và thời điểm**: lỗi ảnh hưởng toàn hệ thống hay một endpoint, một tenant, một node hoặc một nhóm request? Ghi timestamp, phiên bản JDK, tải và thay đổi triển khai gần nhất.
2. **Đo mức độ tiến triển**: throughput, request đang chạy, queue depth, oldest task age, p50/p95/p99 latency, timeout và error rate.
3. **Thu thập nhiều thread dump**: lấy vài snapshot cách nhau một khoảng ngắn; so sánh stack của cùng thread và số thread ở cùng điểm chờ. Với Java 21, dùng dump phù hợp cho platform và virtual thread.
4. **Tìm chu trình lock trong JVM**: dùng `ThreadMXBean` cho platform thread; đọc monitor/synchronizer ownership trong dump và xác minh thứ tự lấy lock.
5. **Đối chiếu tài nguyên bên ngoài**: kiểm tra database lock graph, pool metrics, HTTP pending connections, rate-limit response, distributed lock và queue metrics.
6. **Vẽ chuỗi phụ thuộc**: xác định task nào giữ tài nguyên nào, đang chờ tài nguyên nào và ai có thể giải phóng nó. Nếu tạo thành chu trình, xử lý như deadlock; nếu không có chu trình nhưng một số task chờ quá lâu, điều tra starvation hoặc contention.
7. **Đo thời gian theo từng chặng**: queue wait, acquire wait, thời gian sử dụng tài nguyên và thời gian xử lý sau khi trả tài nguyên. Distributed tracing nên có span hoặc metric cho từng chặng quan trọng.
8. **Thử một thay đổi có mục tiêu**: giảm thời gian giữ lock/connection, sửa thứ tự acquire, thêm timeout, backpressure hoặc điều chỉnh concurrency limit theo capacity đã đo.
9. **Kiểm tra lại dưới tải**: xác nhận throughput, latency và queue giảm; bảo đảm không chỉ chuyển điểm nghẽn sang một tài nguyên khác.

Không nên chỉ nhìn CPU thấp rồi kết luận JVM bị treo. CPU thấp cùng queue tăng thường gợi ý tác vụ đang chờ I/O, lock hoặc permit. Ngược lại, CPU cao có thể là tính toán nặng, retry loop hoặc contention spin; cần kết hợp profiler/JFR và metrics.

## 10. Những cách khắc phục thường có hiệu quả

| Nguyên nhân | Hướng xử lý |
|---|---|
| Lock order không nhất quán | Chuẩn hóa thứ tự acquire; giảm số lock lồng nhau |
| Giữ lock trong lúc I/O | Tách I/O ra ngoài critical section; giữ lock trong thời gian ngắn |
| Transaction/connection bị giữ lâu | Thu hẹp transaction; đóng tài nguyên đúng lúc; tối ưu query |
| Connection pool quá nhỏ hoặc database quá tải | Đo capacity database trước khi tăng pool; giới hạn tải và tối ưu truy vấn |
| Remote service throttling | Giảm concurrency, tôn trọng quota, timeout và retry có backoff/jitter |
| Worker pool starvation | Tránh block chờ task con trong cùng pool; dùng composition hoặc tách executor hợp lý |
| Starvation do fairness | Đánh giá fair lock/semaphore và thời gian giữ permit; không giả định fairness giải quyết mọi tầng |
| Hàng đợi tăng vô hạn | Bounded queue, backpressure, admission control và chính sách từ chối |
| Virtual thread pinning trong Java 21 | Tìm `jdk.VirtualThreadPinned`; tránh blocking I/O trong synchronized/native region khi có thể |

Tăng thread count hoặc tăng pool size không phải biện pháp mặc định. Nếu database hoặc upstream đã ở giới hạn, tăng số thread chỉ làm tăng số tác vụ chờ, bộ nhớ sử dụng và áp lực retry.

## 11. Checklist chẩn đoán

Trước khi kết luận nguyên nhân, hãy kiểm tra:

1. Có chu trình lock rõ ràng hay chỉ là một nhóm thread đang chờ bình thường?
2. Thread đang chờ monitor, ownable synchronizer, semaphore, connection pool, queue hay remote response?
3. Có thread/task nào giữ tài nguyên lâu bất thường không?
4. Một số tác vụ có bị starvation trong khi tác vụ khác vẫn hoàn tất không?
5. Queue depth và thời gian chờ tăng ở tầng nào?
6. Database có lock wait, deadlock, transaction dài hoặc connection pool exhaustion không?
7. HTTP client/upstream có pending connection, timeout, 429/503 hoặc retry storm không?
8. Có chu trình phụ thuộc xuyên qua application lock, connection, queue hoặc distributed lock không?
9. Virtual thread có bị pin trong Java 21 hay không?
10. Thay đổi dự kiến có xử lý đúng bottleneck và được xác minh dưới tải không?

## 12. Tài liệu tham khảo chính thức

- [Java SE 21 API — `ThreadMXBean`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): tìm deadlock giữa platform thread và lấy thông tin monitor/synchronizer.
- [Java SE 21 API — `ThreadInfo`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadInfo.html): thông tin trạng thái thread, lock đang chờ và lock đang giữ.
- [Java SE 21 API — `ReentrantLock`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): lock fairness, `tryLock` và thao tác interruptible.
- [Java SE 21 API — `Semaphore`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html): permit, fairness và các cách chờ tài nguyên.
- [Java SE 21 `jcmd` documentation](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): lệnh thread dump và JFR cho tiến trình đang chạy.
- [Java Flight Recorder runtime guide](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-runtime-guide.html): ghi và phân tích sự kiện runtime.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): mô hình virtual thread và các lưu ý về pinning trong Java 21.

Deadlock, starvation và resource contention đều có thể làm hệ thống chậm hoặc ngừng xử lý, nhưng cần cách chẩn đoán khác nhau. Hãy tìm chu trình giữ/chờ để xác nhận deadlock, theo dõi tiến triển của từng tác vụ để phát hiện starvation, và đo queue/acquire/service time ở từng tài nguyên để tìm contention. Với Java 21, kết hợp thread dump phù hợp cho virtual thread, `ThreadMXBean`, JFR và metrics của database, connection pool, HTTP client cùng dịch vụ bên ngoài để tìm đúng điểm nghẽn.
