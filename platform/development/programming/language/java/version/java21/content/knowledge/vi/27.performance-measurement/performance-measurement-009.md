# Phân tích pinning, lock contention và connection pool saturation

Pinning, lock contention và connection pool saturation đều có thể làm request chậm, nhưng chúng mô tả ba điểm nghẽn khác nhau. **Pinning** giữ carrier thread khi virtual thread không thể unmount trong lúc blocking. **Lock contention** xảy ra khi nhiều thread phải chờ cùng một khóa hoặc vùng dữ liệu được bảo vệ. **Connection pool saturation** xảy ra khi không còn connection rảnh và request phải chờ một connection được trả về hoặc được tạo mới.

Ba hiện tượng có thể xuất hiện cùng lúc. Ví dụ, một request giữ database connection trong khi chờ một monitor; các request khác vừa chờ monitor vừa chờ connection pool. Muốn xử lý đúng, cần ghép dữ liệu từ JFR, thread dump, metric connection pool và thời gian truy vấn thay vì chỉ tăng số thread hoặc kích thước pool.

## 1. Phân biệt ba loại nghẽn

| Hiện tượng | Tài nguyên bị tranh chấp hoặc giữ lại | Dấu hiệu chính | Công cụ nên xem |
|---|---|---|---|
| Virtual thread pinning | Carrier platform thread | Event `jdk.VirtualThreadPinned`, carrier bị giữ trong lúc virtual thread blocking | JFR, thread dump, stack trace |
| Lock contention | Monitor hoặc explicit lock | Nhiều thread chờ cùng lock; thời gian chờ lock tăng | JFR `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`, `jdk.ThreadPark` |
| Connection pool saturation | Connection trong pool | Active đạt max, idle bằng 0, pending/waiters và acquisition time tăng | Pool metrics/JMX, JDBC metrics, JFR, database monitoring |

Một virtual thread chờ lấy connection từ pool thường có thể park và unmount khỏi carrier. Vì vậy, pool bị bão hòa không tự động có nghĩa virtual thread bị pin. Ngược lại, nếu mã giữ monitor hoặc đang ở native call trong lúc chờ, carrier có thể bị giữ theo cơ chế pinning trên JDK 21.

## 2. Virtual thread pinning là gì?

Virtual thread chạy trên một platform thread được gọi là carrier. Khi virtual thread đi vào thao tác blocking mà runtime hỗ trợ unmount, nó tạm dừng và trả carrier về scheduler. Carrier sau đó có thể thực thi virtual thread khác.

Virtual thread bị **pin** khi runtime không thể unmount nó khỏi carrier trong một số vùng thực thi. Khi một thao tác blocking xảy ra trong vùng bị pin, carrier cũng bị giữ cho đến khi thao tác đó kết thúc. Nếu nhiều virtual thread bị pin lâu và thường xuyên, số carrier khả dụng giảm, throughput có thể giảm dù ứng dụng tạo được rất nhiều virtual thread.

### Pinning trên Java 21

Trong JDK 21, các trường hợp quan trọng gây pinning gồm:

- Virtual thread thực hiện thao tác blocking khi đang ở trong `synchronized` block hoặc `synchronized` method.
- Virtual thread đang thực thi native method hoặc foreign function.

Ví dụ:

```java
final class LegacyGateway {
    private final Object lock = new Object();

    Response callRemote(Request request) throws IOException {
        synchronized (lock) {
            // Nếu lời gọi này blocking trên JDK 21,
            // virtual thread có thể bị pin vào carrier.
            return blockingHttpCall(request);
        }
    }
}
```

Vùng `synchronized` giữ monitor trong suốt thời gian chờ mạng. Trên Java 21, carrier của virtual thread có thể bị giữ cùng lúc. Nếu nhiều request đi qua vùng này, pinning có thể làm cạn carrier khả dụng.

Không phải mọi lần dùng `synchronized` đều gây vấn đề. Critical section ngắn, chỉ thao tác bộ nhớ và ít tranh chấp thường không gây ảnh hưởng đáng kể. Cần tìm những vùng vừa có blocking vừa được thực thi thường xuyên hoặc giữ khóa lâu.

### Lưu ý khi ứng dụng chạy JDK mới hơn

Từ JDK 24, JEP 491 thay đổi cơ chế monitor để virtual thread có thể unmount khi bị block trong `synchronized` block hoặc method. Vì vậy, việc chờ monitor trong mã Java thông thường không còn tự nó gây monitor pinning như trên Java 21. Tuy nhiên, nếu virtual thread vẫn có native method hoặc foreign function frame trên stack, nó vẫn có thể bị pin; cần xem stack trace và JDK thực tế thay vì kết luận chỉ từ từ khóa `synchronized`.

Điều này không loại bỏ lock contention. Một virtual thread trên JDK mới hơn vẫn có thể phải chờ monitor lâu; khác biệt là việc chờ monitor không nhất thiết giữ carrier, trừ các trường hợp còn native/foreign frame hoặc giới hạn runtime cụ thể. Khi phân tích production, luôn ghi nhận phiên bản runtime thực tế. Nếu chạy Java 21, phải xét monitor pinning; nếu chạy JDK 24+, vẫn phải xét contention nhưng không quy mọi monitor wait thành carrier pinning.

## 3. Lock contention là gì?

Lock contention xuất hiện khi nhiều thread cùng cần vào một vùng được bảo vệ bởi khóa, nhưng chỉ một thread có thể tiến hành tại một thời điểm. Các thread còn lại phải chờ.

Hai nhóm khóa thường gặp:

- **Intrinsic monitor:** được sử dụng bởi `synchronized` block và method.
- **Explicit lock:** ví dụ `ReentrantLock`, `ReentrantReadWriteLock` hoặc các cấu trúc đồng bộ dựa trên `LockSupport.park`.

Lock contention có thể làm giảm throughput ngay cả khi không có pinning. Nếu critical section bảo vệ một thao tác chậm hoặc được gọi rất thường xuyên, các thread xếp hàng phía sau khóa và thời gian chờ tăng.

Ví dụ một bộ đếm dùng chung có critical section quá rộng:

```java
final class ReportCache {
    private final Object lock = new Object();
    private Report cached;

    Report getReport() {
        synchronized (lock) {
            if (cached == null) {
                cached = loadReportFromDatabase();
            }
            return cached;
        }
    }
}
```

`loadReportFromDatabase()` có thể chờ I/O trong lúc monitor đang được giữ. Các request khác không thể lấy report cho đến khi truy vấn hoàn tất. Trên Java 21, virtual thread chờ trong vùng này còn có nguy cơ pin carrier.

Có thể giảm thời gian giữ monitor bằng cách chỉ bảo vệ việc kiểm tra/cập nhật trạng thái và thực hiện I/O bên ngoài khóa. Cần xử lý race condition phù hợp, không đơn giản chuyển câu lệnh ra ngoài nếu điều đó làm sai tính nhất quán.

## 4. Connection pool saturation là gì?

Connection pool giới hạn số kết nối vật lý đến database. Khi một request gọi `DataSource.getConnection()`, pool cấp connection rảnh hoặc đưa request vào hàng chờ nếu mọi connection đang được sử dụng.

Pool có dấu hiệu bão hòa khi:

- Số connection active liên tục chạm giới hạn tối đa.
- Số connection idle thường xuyên bằng 0.
- Số thread đang chờ connection tăng.
- Thời gian lấy connection tăng và bắt đầu xuất hiện acquisition timeout.
- Request latency tăng trước cả khi câu SQL bắt đầu chạy, vì request phải chờ connection.

Pool bão hòa có thể do nhiều nguyên nhân khác nhau:

1. Truy vấn chậm hoặc database quá tải, khiến connection bị giữ lâu.
2. Transaction kéo dài hoặc giữ connection qua nhiều bước không cần thiết.
3. Connection không được đóng/return về pool do thiếu `try-with-resources` hoặc lỗi quản lý vòng đời.
4. Ứng dụng giữ connection trong lúc gọi HTTP service, xử lý file hoặc chờ người dùng.
5. Pool quá nhỏ so với tải hợp lý hoặc cấu hình không phù hợp.
6. Tổng số connection từ nhiều instance ứng dụng vượt năng lực database.

Tăng `maximumPoolSize` không phải cách sửa mặc định. Nếu database đã bão hòa CPU, I/O hoặc giới hạn session, thêm connection có thể làm tình trạng nặng hơn.

## 5. Nhận biết pool saturation bằng metric

Các metric quan trọng có thể khác tên giữa các thư viện pool, nhưng thường có ý nghĩa tương tự:

| Metric | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| Active connections | Connection đang được ứng dụng mượn | Tăng cao và nằm sát max trong thời gian dài |
| Idle connections | Connection sẵn sàng được cấp | Bằng 0 khi tải cao |
| Total connections | Tổng connection hiện có trong pool | Bằng maximum pool size trong khi vẫn có waiter |
| Pending / waiting threads | Số caller đang đợi connection | Tăng kéo dài hoặc tăng cùng latency |
| Connection acquisition time | Thời gian từ lúc yêu cầu đến lúc nhận connection | P95/P99 tăng; timeout xuất hiện |
| Connection usage time | Thời gian ứng dụng giữ connection | Cao bất thường hoặc lệch lớn giữa các request |
| Connection timeout count | Số lần không lấy được connection trong timeout | Tăng theo thời gian |

Ví dụ, HikariCP cung cấp các giá trị qua `HikariPoolMXBean` như `getActiveConnections()`, `getIdleConnections()`, `getTotalConnections()` và `getThreadsAwaitingConnection()`. Tên metric khi tích hợp Micrometer/Prometheus có thể khác theo phiên bản và registry.

Ví dụ lấy snapshot bằng API quản lý của HikariCP:

```java
import com.zaxxer.hikari.HikariDataSource;
import com.zaxxer.hikari.HikariPoolMXBean;

static void logPoolState(HikariDataSource dataSource) {
    HikariPoolMXBean pool = dataSource.getHikariPoolMXBean();
    if (pool == null) {
        return; // Pool chưa khởi tạo hoặc đã đóng.
    }

    System.out.printf(
            "active=%d idle=%d total=%d waiting=%d%n",
            pool.getActiveConnections(),
            pool.getIdleConnections(),
            pool.getTotalConnections(),
            pool.getThreadsAwaitingConnection());
}
```

Đây là API riêng của HikariCP, không thuộc JDBC. Snapshot có thể thay đổi ngay sau khi đọc; hãy xuất metric theo thời gian thay vì dùng một lần đọc để quyết định tự động tăng pool.

Một snapshot đơn lẻ chưa đủ để kết luận. Hãy quan sát chuỗi metric trong cùng khoảng thời gian với request latency, database CPU, query duration và số request đến hệ thống.

## 6. Dùng JFR để phân biệt pinning và lock contention

Java Flight Recorder (JFR) ghi nhận các sự kiện theo thời gian, giúp tìm stack trace và duration của thao tác chờ. Các event hữu ích trong Java 21 gồm:

| JFR event | Dữ liệu giúp điều tra |
|---|---|
| `jdk.VirtualThreadPinned` | Virtual thread bị pin đủ lâu; có stack trace và thời gian pin |
| `jdk.JavaMonitorEnter` | Thời gian chờ để vào intrinsic monitor đang bị thread khác giữ |
| `jdk.JavaMonitorWait` | Thời gian chờ từ `Object.wait()` |
| `jdk.ThreadPark` | Thời gian thread park; thường hữu ích với `ReentrantLock`, semaphore, queue và pool wait |
| `jdk.SocketRead`, `jdk.SocketWrite` | Thời gian chờ đọc/ghi mạng |
| `jdk.ExecutionSample` | Mẫu stack khi thread đang chạy; hữu ích để tìm CPU hot path |

Trong JDK 21, `jdk.VirtualThreadPinned` được bật trong cấu hình JFR mặc định với threshold 20 ms. Một event ngắn hơn ngưỡng có thể không được ghi. Các event khác có thể phụ thuộc recording configuration và threshold; kiểm tra cấu hình thực tế trước khi kết luận không có contention.

### Bắt đầu recording

Có thể bắt đầu JFR khi khởi chạy ứng dụng:

```bash
java -XX:StartFlightRecording=filename=diagnostics.jfr,settings=profile,dumponexit=true -jar application.jar
```

Hoặc yêu cầu JVM đang chạy ghi trong một khoảng thời gian:

```bash
jcmd <pid> JFR.start name=contention settings=profile duration=60s filename=contention.jfr
```

Đọc các event quan tâm:

```bash
jfr print --events jdk.VirtualThreadPinned,jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark,jdk.SocketRead,jdk.SocketWrite contention.jfr
```

Đối chiếu event với stack trace để tìm lớp ứng dụng, thư viện hoặc phương thức đang giữ lock, gọi I/O hay chờ pool. Khi cần xem tổng quan và lọc theo thread/stack/duration, mở recording bằng JDK Mission Control.

## 7. Đọc JFR event đúng cách

### VirtualThreadPinned

Tìm các event có duration dài và lặp lại nhiều lần. Đọc stack trace để xác định virtual thread bị pin do `synchronized`, native method hoặc foreign function trong phiên bản JDK đang chạy.

Một event pinning kéo dài nhưng rất hiếm có thể không phải nút thắt chính. Ngược lại, nhiều event ngắn lặp lại với tần suất cao cũng có thể ảnh hưởng throughput. Xem tổng thời gian, số lần, tỷ lệ request bị ảnh hưởng và số carrier bị chiếm trong cùng khoảng thời gian.

### JavaMonitorEnter và JavaMonitorWait

`jdk.JavaMonitorEnter` giúp xác định thread phải chờ để vào monitor. Stack trace thường chỉ ra điểm tranh chấp, nhưng cần xác định thêm đoạn code giữ monitor và thời gian giữ khóa. `jdk.JavaMonitorWait` phản ánh thao tác `Object.wait()`; đây là chờ điều kiện, không đồng nghĩa với chờ lấy monitor.

JFR event chỉ ghi các sự kiện thỏa threshold. Nếu không thấy event, có thể thời gian chờ thấp hơn threshold, event chưa được bật hoặc recording không bao phủ thời điểm sự cố.

### ThreadPark

`jdk.ThreadPark` hữu ích khi ứng dụng dùng explicit locks hoặc các cấu trúc concurrency. Tuy nhiên, không phải mọi park đều là lỗi. Thread có thể park bình thường khi đợi queue, semaphore hoặc connection pool. Phải đọc stack trace và kết hợp metric pool để xác định nguyên nhân.

## 8. Dùng thread dump để tìm nhóm thread đang chờ

Thread dump bổ sung góc nhìn tại một thời điểm. Trên JDK 21, dùng lệnh sau để xuất dump gồm cả platform thread và virtual thread:

```bash
jcmd <pid> Thread.dump_to_file -format=text /var/tmp/threads.txt
```

Tìm các nhóm stack lặp lại:

- Nhiều virtual thread cùng dừng tại một synchronized method hoặc điểm truy cập shared state.
- Nhiều thread dừng ở `LockSupport.park`, `AbstractQueuedSynchronizer` hoặc `ReentrantLock`.
- Nhiều request dừng ở `DataSource.getConnection()`, `HikariPool.getConnection()` hoặc đoạn code lấy connection.
- Một số ít thread giữ connection và đang thực thi query hoặc chờ socket từ database.

Thread dump JDK 21 có ích để thấy virtual thread và stack trace, nhưng không thay thế JFR để đo duration. Dump dạng `Thread.dump_to_file` cũng không cung cấp đầy đủ lock ownership như dump truyền thống. Hãy lấy nhiều dump cách nhau một khoảng thời gian và ghép với JFR/pool metrics.

## 9. Phân tích connection pool saturation theo từng lớp

Khi pool bão hòa, tách thời gian xử lý request thành các đoạn:

```text
Request đến
    |
    v
Chờ lấy connection từ pool
    |
    v
Thực thi SQL / chờ database
    |
    v
Commit hoặc rollback
    |
    v
Đóng connection, trả về pool
    |
    v
Response hoàn tất
```

Nếu thời gian chờ lấy connection tăng nhưng query execution time không tăng, có thể pool đang thiếu connection khả dụng hoặc connection bị giữ ở một nơi khác. Nếu query time tăng cùng active connections, cần điều tra database, index, lock ở database hoặc tải truy vấn.

Nếu connection usage time cao nhưng database query time thấp, ứng dụng có thể đang giữ connection quá lâu ngoài phần SQL, ví dụ gọi HTTP, serialize dữ liệu lớn hoặc thực hiện tính toán trong transaction. Đo riêng acquisition time, SQL duration và thời gian giữ connection sẽ giúp phân biệt.

## 10. Ví dụ: giữ connection trong lúc gọi dịch vụ bên ngoài

Đoạn code sau giữ connection trong lúc chờ HTTP service:

```java
try (Connection connection = dataSource.getConnection()) {
    Customer customer = httpClient.fetchCustomer(customerId);
    updateCustomer(connection, customer);
}
```

Nếu HTTP service chậm, connection vẫn bị mượn dù database không được sử dụng. Nhiều request đồng thời có thể chiếm hết pool.

Nếu nghiệp vụ cho phép, thực hiện lời gọi bên ngoài trước khi mượn connection:

```java
Customer customer = httpClient.fetchCustomer(customerId);

try (Connection connection = dataSource.getConnection()) {
    updateCustomer(connection, customer);
}
```

Ví dụ này rút ngắn thời gian giữ connection. Nếu nghiệp vụ yêu cầu transaction nhất quán xuyên qua nhiều hệ thống, cần thiết kế workflow, outbox/saga hoặc cơ chế tương đương; không nên kéo dài transaction database chỉ để chờ một HTTP call.

Luôn đóng `Connection`, `Statement` và `ResultSet` bằng try-with-resources. Với pooled `DataSource`, `Connection.close()` thường trả logical connection về pool thay vì đóng socket database vật lý.

## 11. Khắc phục pinning trên Java 21

Khi JFR cho thấy pinning đáng kể và stack trace dẫn đến blocking trong `synchronized`, hãy xem xét:

1. Thu hẹp critical section để không giữ monitor trong lúc I/O hoặc chờ lâu.
2. Tách thao tác mạng, file hoặc database ra ngoài vùng giữ monitor nếu vẫn bảo toàn tính nhất quán.
3. Dùng `ReentrantLock` tại đúng vị trí cần chờ lâu trong khi giữ quyền khóa, vì cơ chế park của explicit lock cho phép virtual thread unmount trong trường hợp phù hợp.
4. Kiểm tra native method và foreign function; nếu chúng block, cân nhắc API bất đồng bộ, native library hoặc boundary thực thi phù hợp.
5. Đo lại pinning duration, throughput và latency sau khi thay đổi.

Không thay toàn bộ `synchronized` bằng `ReentrantLock`. Khóa explicit cũng có thể bị contention; việc đổi loại khóa không loại bỏ thời gian chờ nếu critical section vẫn dài hoặc quá nhiều task tranh cùng tài nguyên.

Ví dụ chuyển một vùng cần giữ khóa qua thao tác chờ sang `ReentrantLock` trên Java 21:

```java
import java.util.concurrent.locks.ReentrantLock;

private final ReentrantLock lock = new ReentrantLock();

Response callRemote(Request request) throws IOException {
    lock.lock();
    try {
        return blockingHttpCall(request);
    } finally {
        lock.unlock();
    }
}
```

Virtual thread có thể unmount khi `blockingHttpCall` chờ trong lúc giữ `ReentrantLock`, vì cơ chế chờ của explicit lock sử dụng park. Nhưng các request vẫn phải lần lượt lấy cùng khóa; ví dụ này chỉ tránh monitor pinning trên Java 21, không giải quyết lock contention hoặc việc tuần tự hóa lời gọi mạng. Nếu không cần giữ khóa xuyên suốt I/O, giải pháp tốt hơn thường là thu hẹp critical section và gọi mạng bên ngoài vùng khóa.

Trên JDK 24 trở lên, JEP 491 loại bỏ monitor pinning do chờ `synchronized` trong mã Java thông thường. Khi chạy các phiên bản này, ưu tiên sửa lock contention nếu có; vẫn điều tra pinning còn lại như native/foreign calls hoặc trường hợp runtime cụ thể.

## 12. Khắc phục lock contention

Khi nhiều thread chờ cùng lock, tìm nguyên nhân ở cả tần suất truy cập và thời gian giữ khóa:

- Giữ critical section ngắn; không thực hiện I/O, gọi service bên ngoài hoặc chờ future bên trong lock.
- Giảm trạng thái mutable dùng chung; cân nhắc immutable data hoặc copy-on-write khi phù hợp với workload đọc nhiều.
- Chia nhỏ vùng khóa theo key/partition nếu dữ liệu độc lập và cần concurrency cao.
- Dùng cấu trúc concurrency phù hợp như `ConcurrentHashMap`, atomic variables hoặc queue thay vì một monitor toàn cục.
- Với read-heavy workload, cân nhắc read/write lock sau khi đo và hiểu chi phí writer starvation/fairness.
- Kiểm tra lock ordering để tránh deadlock khi có nhiều khóa.
- Tránh tạo nhiều lock hoặc dùng `tryLock` chỉ để che latency mà không xác định chính sách retry/failure.

Một khóa toàn cục có thể khiến throughput bị giới hạn bởi một critical section duy nhất. Tăng số virtual thread trong tình huống này thường chỉ làm hàng đợi chờ lock dài hơn.

## 13. Khắc phục connection pool saturation

Đi theo thứ tự sau để không làm quá tải database:

1. **Kiểm tra connection leak:** bảo đảm mọi connection được đóng trong `finally` hoặc try-with-resources; bật leak detection nếu pool hỗ trợ.
2. **Đo thời gian giữ connection:** xác định request nào mượn connection lâu và vì sao.
3. **Tối ưu query:** kiểm tra execution plan, index, lock ở database, round trip và số câu SQL.
4. **Thu hẹp transaction:** không giữ connection trong lúc gọi dịch vụ bên ngoài hoặc thực hiện công việc không cần database.
5. **Giới hạn concurrency:** dùng semaphore hoặc bulkhead nếu số request đồng thời vượt năng lực database.
6. **Đặt timeout:** cấu hình connection acquisition timeout, query timeout và request deadline phù hợp.
7. **Đánh giá kích thước pool:** tính tổng connection từ mọi instance và so sánh với giới hạn database; chỉ tăng pool nếu database còn năng lực xử lý.
8. **Theo dõi timeout và pending:** xác nhận thay đổi có giảm acquisition latency và timeout trong tải đại diện.

Virtual thread cho phép tạo nhiều request đang chờ, nhưng không làm database xử lý được nhiều query hơn. Không đặt maximum pool size bằng số virtual thread hoặc số request tối đa chỉ vì các thread nhẹ hơn platform thread.

## 14. Bảng chẩn đoán nhanh

| Dấu hiệu | Nguyên nhân có thể | Bằng chứng cần tìm | Hướng xử lý |
|---|---|---|---|
| `jdk.VirtualThreadPinned` nhiều và duration cao | Blocking khi pin trên JDK 21 | Stack trace có `synchronized`, native hoặc foreign call | Rút ngắn vùng giữ monitor; xử lý native blocking; đo lại |
| `jdk.JavaMonitorEnter` tăng | Nhiều thread tranh intrinsic monitor | Cùng stack/monitor, thời gian chờ dài | Giảm critical section, chia nhỏ khóa hoặc đổi cấu trúc dữ liệu |
| `jdk.ThreadPark` tăng cùng pool waiters | Chờ explicit lock, queue, semaphore hoặc connection pool | Stack trace park và metric thành phần tương ứng | Xác định queue/lock/pool đang giới hạn throughput |
| Active connections = max, idle = 0, pending tăng | Pool saturation | Acquisition time và timeout tăng | Tối ưu thời gian giữ connection/query, giới hạn concurrency |
| Active connections cao nhưng pending thấp | Pool đang được sử dụng nhiều nhưng chưa chắc bão hòa | Acquisition latency vẫn thấp, DB utilization trong ngưỡng | Theo dõi trend; không tăng pool chỉ dựa trên active count |
| Query duration cao, active gần max | Database hoặc query là bottleneck | DB wait, execution plan, lock, CPU/I/O | Tối ưu SQL/database hoặc giảm tải |
| Latency cao nhưng không có pinning/lock/pool wait đáng kể | Bottleneck khác | Socket, CPU, GC, downstream latency | Mở rộng điều tra theo JFR và tracing |

## 15. Quy trình điều tra từ triệu chứng đến nguyên nhân

Một quy trình có thể lặp lại trong staging hoặc production:

1. Ghi nhận JDK version, traffic, throughput, p50/p95/p99 latency và error rate.
2. Thu thập JFR recording bao phủ đúng thời gian xảy ra sự cố.
3. Kiểm tra `jdk.VirtualThreadPinned`, `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`, `jdk.ThreadPark` và các event I/O.
4. Lấy thread dump có virtual thread bằng `jcmd <pid> Thread.dump_to_file -format=text <file>`.
5. Thu thập pool metrics: active, idle, total, pending, acquisition time, usage time và timeout count.
6. Đối chiếu với database metrics: query latency, active sessions, lock waits, CPU, I/O và connection limit.
7. Xác định bottleneck chiếm phần lớn thời gian request; không suy luận từ một metric đơn lẻ.
8. Thay đổi một nguyên nhân có bằng chứng, chạy lại cùng workload và so sánh trước/sau.

Nếu có thể, dùng cùng một kịch bản tải, cùng dữ liệu và cùng thời lượng recording trước/sau thay đổi. So sánh throughput, latency percentiles, số pinning event, monitor wait, connection acquisition time và database utilization.

## 16. Những kết luận sai thường gặp

- **Thấy nhiều virtual thread là nghĩ pinning:** virtual thread có thể đang chờ và đã unmount bình thường.
- **Thấy `ThreadPark` là kết luận bị treo:** park có thể là hành vi bình thường của lock, queue, semaphore hoặc pool.
- **Thấy active connection bằng maximum là kết luận leak:** có thể đó là tải hợp lệ; cần pending, acquisition time và usage time để xác nhận saturation.
- **Không có `VirtualThreadPinned` là chắc chắn không pin:** event có threshold, có thể bị tắt hoặc pinning ngắn hơn ngưỡng.
- **Tăng pool size luôn tăng throughput:** database có thể đã đạt giới hạn và bị quá tải hơn.
- **Đổi mọi `synchronized` thành `ReentrantLock`:** JDK 24+ đã thay đổi monitor pinning; lock contention vẫn cần xử lý theo bằng chứng.
- **Tăng số carrier để chữa mọi vấn đề:** không giải quyết monitor contention hoặc database pool saturation.

## 17. Tổng kết

Pinning, lock contention và connection pool saturation cần được chẩn đoán riêng. Pinning làm carrier bị giữ trong lúc virtual thread blocking; trên Java 21, blocking trong `synchronized` và native/foreign call là những trường hợp cần chú ý. JDK 24 trở lên đã thay đổi monitor pinning qua JEP 491, nhưng lock contention vẫn có thể làm request chờ lâu.

Lock contention là tranh chấp monitor hoặc explicit lock; connection pool saturation là thiếu connection rảnh và request phải chờ cấp connection. Dùng JFR để đo pinning, monitor wait và park; dùng thread dump để xem stack; dùng pool metrics và database monitoring để đo acquisition/usage time. Chỉ thay đổi critical section, pool size hoặc concurrency limit sau khi đã xác định được tài nguyên thực sự là nút thắt.

## Tài liệu tham khảo

- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html) — pinning, `jdk.VirtualThreadPinned`, JFR và thread dump cho virtual thread trên JDK 21.
- [Oracle Java 21 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshoot-performance-issues-using-jfr.html) — các event `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`, `jdk.ThreadPark`, I/O và cách tìm bottleneck.
- [JEP 491: Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491) — thay đổi monitor pinning từ JDK 24.
- [Oracle JDK 24 — Significant Changes](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html) — tác động của JEP 491 đối với `synchronized` và virtual threads.
- [HikariCP — HikariConfigMXBean](https://github.com/brettwooldridge/HikariCP/blob/dev/src/main/java/com/zaxxer/hikari/HikariConfigMXBean.java) — pool size, connection timeout và leak detection configuration.
- [HikariCP — Metrics](https://github.com/brettwooldridge/HikariCP) — các chỉ số connection active, idle, pending, acquisition/usage và timeout qua metrics integration.
