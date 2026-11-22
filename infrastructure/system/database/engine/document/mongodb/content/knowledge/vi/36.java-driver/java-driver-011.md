# Theo dõi topology, pool, lệnh và phân loại exception trong MongoDB Java Driver

## 1. Bối cảnh: một lỗi timeout có thể có nhiều nguyên nhân

Một ứng dụng Java Spring Boot sử dụng MongoDB replica set ba node. Bình thường API ghi đơn hàng trong 30 ms. Khi bảo trì, primary chuyển từ node A sang node B và ứng dụng bắt đầu báo:

```text
com.mongodb.MongoTimeoutException:
Timed out while waiting for a server that matches
ReadPreferenceServerSelector{readPreference=primary}
```

Một giờ sau, vẫn là “timeout”, nhưng lần này nguyên nhân hoàn toàn khác: primary khỏe, query bình thường, chỉ có **connection pool hết connection khả dụng** do lượng request tăng vọt.

Một lần khác, server nhận lệnh và trả `DuplicateKey` vì đơn hàng đã tồn tại. Nếu ứng dụng coi mọi exception là “network tạm thời” rồi retry vô hạn, hệ thống có thể phát sinh thêm lỗi nghiệp vụ.

Để phân biệt đúng ba tình huống, cần nhìn **bốn lớp quan sát** của Java MongoDB Driver:

1. **Topology / SDAM:** driver biết những server nào, node nào có thể nhận writes, vì sao không chọn được server?
2. **Connection pool / CMAP:** có bao nhiêu connection, checkout mất bao lâu, có đang chờ pool hay pool bị clear?
3. **Command monitoring:** lệnh `find`, `insert`, `aggregate`... mất bao lâu, thành công hay thất bại, được gửi đến database nào?
4. **Exception & error labels:** lỗi do mạng, không có server thích hợp, xác thực, conflict dữ liệu, thời gian thực thi hay transaction chưa rõ kết quả?

**Điểm cốt lõi:** một exception type không phải toàn bộ chẩn đoán. Cần ghép **thời gian**, **topology events**, **pool events**, **command duration**, **application request/trace** và trạng thái MongoDB server.

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **Server Discovery and Monitoring (SDAM)**, **Connection Monitoring and Pooling (CMAP)** và **Command Monitoring**.
- Đăng ký `ClusterListener`, `ServerListener`, `ServerMonitorListener`, `ConnectionPoolListener`, `CommandListener` trên `MongoClientSettings`.
- Đọc ý nghĩa sự kiện thay primary, heartbeat, pool checkout failed, pool cleared và command failed.
- Phân biệt **server selection timeout**, **connection checkout timeout**, **socket timeout** và **server execution timeout**.
- Sử dụng nhóm exception và `MongoException.hasErrorLabel()` để quyết định **retry**, **reconcile** hay **fail fast**.
- Thiết kế metrics, tracing, logs an toàn, dashboards và alerts không gây bùng nổ cardinality.
- Viết Java Sync Driver code ứng dụng quan sát thực tế và xây runbook cho failover, pool exhaustion, lỗi xác thực/TLS, command errors.
- Hiểu vì sao driver retry không thay thế **business idempotency** hay transaction correctness.

### 1.2. Phiên bản và phạm vi

Ví dụ tập trung vào **MongoDB Java Sync Driver 5.x**, dùng Java 11+ khi có `String.isBlank()`. Tên method/event phù hợp các APIs Java driver 5.x; hãy đối chiếu tài liệu đúng phiên bản trong dự án trước khi biên dịch.

`MongoClient`, `MongoDatabase`, `MongoCollection` trong các ví dụ thuộc **Sync Driver**. Reactive Streams Driver có cách lập trình bất đồng bộ khác, dù SDAM/CMAP/command concepts tương tự.

Các đoạn code minh họa phục vụ **môi trường lab/ứng dụng được phép quản trị**. Không cố tình làm mất primary hoặc gây cạn connection trên production để “kiểm chứng” các khái niệm.

## 2. Sơ đồ một request đi qua driver

```text
HTTP request / background job
          |
          v
    Business service
          |
          v
    MongoClient (long-lived)
          |
          +--------> SDAM monitor
          |           - topology descriptions
          |           - server descriptions
          |           - hello / heartbeat
          |
          v
     Server selection
          |
          v
    Select a suitable node
          |
          v
     Connection checkout <-------- Connection Pool (per server)
          |
          v
     Send MongoDB command
          |
          v
        mongod / mongos
          |
          v
     Receive reply or failure
          |
          v
     Decode BSON / result
          |
          v
     Return connection to pool
          |
          v
     Business response / error
```

### 2.1. Một request có nhiều thời gian chờ

Phân rã logic:

\[
T_{\text{request}} \approx
T_{\text{app}} +
T_{\text{server selection}} +
T_{\text{pool checkout}} +
T_{\text{command}} +
T_{\text{decode}} +
T_{\text{other}}
\]

Đây là **mô hình tư duy**, không phải công thức cộng mọi timer độc lập luôn bằng chính xác một request duration. Có concurrency, retries, network handshakes, timeouts và các bước có thể chồng nhau.

### 2.2. Bốn tầng quan sát trả lời bốn câu hỏi

| Tầng | Câu hỏi | Tín hiệu Java Driver |
|---|---|---|
| SDAM | Có primary/readable server thích hợp? | Cluster/server description, heartbeat |
| CMAP | Có connection sẵn để dùng? | Checkout, wait duration, pool cleared/closed |
| Command | Lệnh đã thực thi nhanh/chậm/thất bại? | Started/succeeded/failed, duration |
| Exception | Ứng dụng nên xử lý lỗi ra sao? | Type, error code, error labels, cause |

### 2.3. Không đồng nhất các tầng

```text
Server selection 10 giây
Pool checkout     1 ms
Command execution 8 ms

=> Command duration thấp,
   nhưng request vẫn rất chậm vì chờ chọn server.
```

Vì vậy một dashboard chỉ đo `CommandSucceededEvent.getElapsedTime()` sẽ **bỏ sót** nhiều phần chờ.

## 3. Ba hệ thống event của Java Driver

MongoDB Java Driver có ba nhóm monitoring events chính:

| Nhóm | Listener | Event thường dùng |
|---|---|---|
| **SDAM — Topology** | `ClusterListener` | `ClusterOpeningEvent`, `ClusterDescriptionChangedEvent`, `ClusterClosedEvent` |
| **SDAM — Server** | `ServerListener` | `ServerOpeningEvent`, `ServerDescriptionChangedEvent`, `ServerClosedEvent` |
| **SDAM — Heartbeat** | `ServerMonitorListener` | `ServerHeartbeatStartedEvent`, `ServerHeartbeatSucceededEvent`, `ServerHeartbeatFailedEvent` |
| **CMAP — Pool** | `ConnectionPoolListener` | Pool open/clear/close, connection create/ready/close, checkout/checkin |
| **Commands** | `CommandListener` | `CommandStartedEvent`, `CommandSucceededEvent`, `CommandFailedEvent` |

### 3.1. Events phát ở driver, không phải collection audit

`CommandListener` không đồng nghĩa với MongoDB Enterprise/Atlas database auditing:

- Driver listener chỉ thấy những thao tác của **MongoClient đó**.
- Database audit có phạm vi server-side và chính sách khác.
- Listener application có thể bị tắt hoặc process crash.
- Driver không phát command events cho mọi command nội bộ, đặc biệt những command dùng để handshake/monitor topology.

### 3.2. Listener chạy trong luồng hoạt động nhạy cảm

Đừng viết listener mà:

- Ghi log đồng bộ rất chậm với mỗi command.
- Gửi HTTP request ra hệ thống monitoring.
- Tạo MongoClient mới rồi query MongoDB trong mỗi event.
- Block trên lock toàn cục.
- Ném exception ra khỏi callback.

Thay vào đó dùng bộ đếm/gauge nhẹ, metric recorder hiệu quả hoặc non-blocking/bounded export. **Observer không được trở thành nguyên nhân outage.**

## 4. Dependencies và lifecycle của MongoClient

### 4.1. Dependency Gradle minh họa

```groovy
dependencies {
    implementation 'org.mongodb:mongodb-driver-sync:<compatible-5.x-version>'
}
```

Chuỗi phiên bản chỉ là placeholder. Dự án thật nên chốt dependency và xác minh tương thích với BOM/framework/version server. Không trộn tùy ý Java Driver 3.x legacy API với lớp `com.mongodb.client.MongoClient` của 5.x.

### 4.2. Một MongoClient sống lâu

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public final class MongoLifecycle394 {
    private final MongoClient mongoClient;

    public MongoLifecycle394(String uri) {
        this.mongoClient = MongoClients.create(uri);
    }

    public MongoClient client() {
        return mongoClient;
    }

    public void shutdown() {
        mongoClient.close();
    }
}
```

Trong ứng dụng thực tế, quản lý `MongoClient` bằng singleton/DI container/managed bean và gọi `close()` khi service shutdown.

### 4.3. Vì sao không tạo client mới cho từng request?

Mỗi `MongoClient` có topology monitoring và pools riêng. Nếu mỗi HTTP request tạo client:

- Nhiều pool mở/đóng liên tục.
- Nhiều TCP/TLS handshakes.
- Tăng server connections.
- Tăng CPU/memory và độ trễ.
- Metrics bị phân mảnh theo vô số client IDs.

### 4.4. Không dùng URI khóa primary

Ví dụ URI replica set:

```text
mongodb://db-a.internal.example:27017,db-b.internal.example:27017,db-c.internal.example:27017/?replicaSet=rsShop&tls=true&retryWrites=true
```

URI trên cho phép driver khám phá topology và chọn primary mới. `directConnection=true` thích hợp cho một số thao tác chẩn đoán node, không phải cấu hình mặc định cho Java service cần failover.

### 4.5. Tài khoản monitoring

Driver listeners không yêu cầu tự cấp `root` để thu event phía client. Nếu muốn đọc thêm `replSetGetStatus`/`serverStatus` từ database, hãy dùng identity được phân quyền tương ứng, ví dụ `clusterMonitor` khi phù hợp.

## 5. SDAM: driver biết topology bằng cách nào?

**SDAM = Server Discovery and Monitoring.** Driver dùng kết quả handshake/`hello` và monitoring để duy trì thông tin:

- Deployment là standalone, replica set, sharded cluster qua `mongos` hay load-balanced.
- Server nào có vai trò primary/secondary/router.
- Server nào đang known/unknown.
- Round-trip-time estimate và khả năng kết nối.
- Tên replica set, danh sách members, địa chỉ đã công bố.
- Khả năng chọn server theo read preference.

### 5.1. Hai cấp mô tả

**ClusterDescription:** cái nhìn tổng thể của một `MongoClient` về topology.

**ServerDescription:** cái nhìn về một host cụ thể.

```text
ClusterDescription:
  type = REPLICA_SET
  servers:
    db-a -> REPLICA_SET_PRIMARY
    db-b -> REPLICA_SET_SECONDARY
    db-c -> REPLICA_SET_SECONDARY
```

### 5.2. Mô tả là view, không phải consensus protocol

Driver có một **view được cập nhật bất đồng bộ** của deployment. Một `ClusterDescriptionChangedEvent` cho biết view của client đổi, không phải bằng chứng chính thức rằng mọi client đồng thời thấy cùng trạng thái.

### 5.3. Failover

```text
T0: driver chọn db-a primary
T1: db-a steps down
T2: driver phát hiện not-primary/network failure
T3: SDAM đánh dấu/chỉnh server descriptions
T4: driver nhận primary mới db-b
T5: các thao tác đủ điều kiện tiếp tục/retry
```

Thời gian từng bước phụ thuộc election, mạng, timeout, heartbeat và khả năng chọn lại server.

## 6. `ClusterListener`: quan sát có server nhận ghi hay không

Java example dùng `ClusterDescriptionChangedEvent.getNewDescription().hasWritableServer()`:

```java
import com.mongodb.event.ClusterDescriptionChangedEvent;
import com.mongodb.event.ClusterListener;
import java.util.concurrent.atomic.AtomicBoolean;

public final class WritableTopology394 implements ClusterListener {
    private final AtomicBoolean writable = new AtomicBoolean(false);

    @Override
    public void clusterDescriptionChanged(
            ClusterDescriptionChangedEvent event) {
        boolean nowWritable =
            event.getNewDescription().hasWritableServer();

        boolean wasWritable = writable.getAndSet(nowWritable);
        if (wasWritable != nowWritable) {
            // Ví dụ: update metric gauge, không log cả ClusterDescription.
            System.out.println(
                "MongoDB writable server observed=" + nowWritable);
        }
    }

    public boolean writableInLastObservedView() {
        return writable.get();
    }
}
```

### 6.1. Đăng ký listener

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

String uri = System.getenv("MONGODB_URI");
WritableTopology394 topology = new WritableTopology394();

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToClusterSettings(b ->
        b.addClusterListener(topology))
    .build();

try (MongoClient client = MongoClients.create(settings)) {
    client.getDatabase("admin").runCommand(
        new org.bson.Document("ping", 1));
}
```

### 6.2. Hạn chế của boolean `hasWritableServer`

Nó trả lời khả năng ghi **theo topology view của driver tại lần quan sát**. Nó không bảo đảm:

- Mọi request mới thành công.
- Authentication đã đúng.
- Network không thay đổi ngay sau callback.
- Majority write concern có thể hoàn tất.
- Một transaction/command cụ thể được hỗ trợ.

Đừng dùng gauge này thay thế business write probe hoặc server-side majority monitoring.

### 6.3. Cẩn thận boot time

Ở startup, listener chưa nhận description hoàn chỉnh; initial value có thể là false. Đừng coi một mẫu false lúc khởi tạo là incident outage nếu client vẫn đang discovery.

## 7. `ServerListener`: phát hiện trạng thái từng server

Một server có thể chuyển từ primary sang secondary, từ known sang unknown hoặc ngược lại.

```java
import com.mongodb.event.ServerDescriptionChangedEvent;
import com.mongodb.event.ServerListener;

public final class ServerChange394 implements ServerListener {
    @Override
    public void serverDescriptionChanged(
            ServerDescriptionChangedEvent event) {
        String before = String.valueOf(
            event.getPreviousDescription().getType());
        String after = String.valueOf(
            event.getNewDescription().getType());

        if (!before.equals(after)) {
            System.out.println(
                "Server role/type changed: " + before + " -> " + after);
        }
    }
}
```

**Production:** dùng metric/log event có labels đã kiểm soát (deployment, role trước/sau) thay vì in nguyên object có địa chỉ nội bộ. Có thể bổ sung server identity với mức bảo mật phù hợp.

### 7.1. `UNKNOWN` không đồng nghĩa process mongod đã chết

Server description có thể thành UNKNOWN do:

- DNS/network/TLS/auth handshake failure.
- Timeout hoặc connection lỗi.
- Server chuyển trạng thái trong election.
- Firewall hoặc private endpoint không reachable từ **client này**.

Phải đối chiếu view từ ứng dụng khác, Atlas/server metrics và logs để xác định root cause.

### 7.2. Đừng đồng nhất topology change với every request

ServerDescriptionChanged thường chỉ được phát khi mô tả đổi, không phải báo cáo từng lệnh `find`. Command metrics và application metrics vẫn cần riêng.

## 8. `ServerMonitorListener`: heartbeat và khả năng liên lạc

Server monitor events gồm:

- `serverHeartbeatStarted`.
- `serverHeartbeatSucceeded`.
- `serverHeartbeatFailed`.

Java example:

```java
import com.mongodb.event.ServerMonitorListener;
import com.mongodb.event.ServerHeartbeatSucceededEvent;
import com.mongodb.event.ServerHeartbeatFailedEvent;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

public final class HeartbeatCounters394
        implements ServerMonitorListener {
    private final LongAdder succeeded = new LongAdder();
    private final LongAdder failed = new LongAdder();

    @Override
    public void serverHeartbeatSucceeded(
            ServerHeartbeatSucceededEvent event) {
        succeeded.increment();
        // Có thể ghi histogram; chú ý awaited heartbeat.
    }

    @Override
    public void serverHeartbeatFailed(
            ServerHeartbeatFailedEvent event) {
        failed.increment();
        // Không log raw exception chứa secrets/host details.
    }

    public long successCount() {
        return succeeded.sum();
    }

    public long failureCount() {
        return failed.sum();
    }
}
```

### 8.1. Đăng ký

```java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToServerSettings(b ->
        b.addServerMonitorListener(new HeartbeatCounters394()))
    .build();
```

### 8.2. Awaited heartbeat có một bẫy về duration

MongoDB hỗ trợ các cơ chế **streaming/exhaust hello** cho monitoring trong các điều kiện tương thích. Với `ServerHeartbeatSucceededEvent.isAwaited() == true`, thời gian `getElapsedTime()` có thể bao gồm **thời gian server chủ động chờ trước khi phản hồi**.

Vì vậy:

```text
heartbeat elapsed = 10 giây
awaited = true
```

**không đồng nghĩa RTT của mạng là 10 giây**. Cần phân biệt awaited monitoring với phép đo round-trip-time estimate.

### 8.3. Load-balanced mode

Trong MongoDB load-balanced mode, Java driver **không phát heartbeat-related SDAM events** theo cơ chế thông thường. Không biến “không có heartbeat events” thành outage khi deployment sử dụng load-balanced topology.

### 8.4. Tần suất heartbeat

Driver có `heartbeatFrequencyMS`, `minHeartbeatFrequency` và `serverMonitoringMode` với defaults theo phiên bản/môi trường. Giảm heartbeat interval quá thấp có thể tạo tải; tăng quá cao có thể trì hoãn discovery.

Không thay mặc định chỉ để dashboard “mượt hơn” nếu chưa đo tác động.

## 9. Tách SDAM state khỏi health check

### 9.1. Một primary bị mất tạm thời

```text
MongoDB replica set:
  db-a PRIMARY -> steps down
  db-b SECONDARY -> election -> PRIMARY

Client A:
  chưa khám phá primary mới

Client B:
  đã chọn db-b
```

Client A và B có thể ghi nhận hai trạng thái khác nhau trong khoảng ngắn, dù server cùng tồn tại.

### 9.2. Health probe của ứng dụng

Nên phân biệt:

- **Liveness:** process Java còn chạy và không bị deadlock.
- **Readiness:** instance có thể phục vụ workload cần thiết.
- **Database readiness:** driver có thể chọn server theo read/write concern yêu cầu trong thời hạn chấp nhận.

Không restart toàn bộ 100 pods khi một election ngắn khiến readiness tạm fail; điều này có thể tạo connection storm và kéo dài outage.

### 9.3. Quan sát từ cả client và server

Một cụm có primary nhưng ứng dụng vẫn không kết nối được vì TLS SAN/firewall/DNS. `rs.status()` chỉ từ server **không chứng minh** client path hoạt động.

Một dashboard thực tế ghép:

```text
SDAM events + pool checkouts + command failures
              +
MongoDB replSetGetStatus / Atlas metrics
              +
API error rate / latency
```

## 10. CMAP: connection pool hoạt động như thế nào?

**CMAP = Connection Monitoring and Pooling.** Driver duy trì connection pool riêng cho từng server endpoint dưới mỗi `MongoClient`.

```text
MongoClient in Java Service
        |
        +-- Pool db-a
        |     conns idle / checked out
        |
        +-- Pool db-b
        |     conns idle / checked out
        |
        +-- Pool db-c
              conns idle / checked out
```

Ngoài application pooled connections, driver còn có connections dùng cho server monitoring; không tính tổng connections phía server bằng đúng `maxPoolSize` nhân số nodes.

### 10.1. Một connection không phải một request

Connections có thể được sử dụng lại qua nhiều operations. Một request có thể cần nhiều MongoDB commands/transactions; ngược lại pool không mở một connection mới cho mỗi HTTP request.

### 10.2. Connection “checked out”

Khi operation lấy connection từ pool, connection đó đang **in use** cho operation. Khi kết thúc/được giải phóng, driver check in để các operations khác tái sử dụng.

### 10.3. Checkout trước command

Nếu pool đang bận, một operation có thể **chờ lấy connection** trước khi `CommandStartedEvent` được phát. Command metrics không phản ánh toàn bộ thời gian chờ pool.

## 11. Vòng đời connection và các CMAP events

```text
Pool opened
   |
   v
Connection created
   |
   v
Connection ready (handshake/auth complete)
   |
   v
Checkout started
   |
   +------> Checked out -> command -> Checked in
   |
   +------> Checkout failed (timeout/error/pool closed)
   |
   v
Connection closed / pool cleared / pool closed
```

Vòng đời thực tế không phải mọi event luôn diễn ra đúng thứ tự cố định trên một connection: pool có thể có nhiều connections, readiness có thể phát trong một checkout, clear có thể invalidate generation, và một connection có thể dùng lại nhiều lần.

### 11.1. Những events hữu ích

| Event | Ý nghĩa quan sát |
|---|---|
| `ConnectionPoolOpenedEvent` | Pool cho server được tạo |
| `ConnectionCreatedEvent` | Driver bắt đầu tạo connection |
| `ConnectionReadyEvent` | Connection sẵn sàng |
| `ConnectionCheckOutStartedEvent` | Operation đang yêu cầu connection |
| `ConnectionCheckedOutEvent` | Operation lấy được connection |
| `ConnectionCheckOutFailedEvent` | Không lấy được connection |
| `ConnectionCheckedInEvent` | Connection được trả |
| `ConnectionClosedEvent` | Connection bị đóng với reason |
| `ConnectionPoolClearedEvent` | Connections thuộc generation có thể bị invalidated |
| `ConnectionPoolClosedEvent` | Pool kết thúc vòng đời |

### 11.2. Pool clear không luôn là “pool hết connection”

Pool có thể được clear sau network error, lỗi kết nối hoặc thay topology; khi đó các connections cũ bị invalidated, driver sẽ tạo lại theo điều kiện.

**Một đợt pool cleared sau failover không tự chứng minh app bị leak connections.** Xem thời điểm SDAM event và checkout failure.

## 12. `ConnectionPoolListener`: đếm checkout và thất bại

Ví dụ đơn giản, **thread-safe**, chỉ đếm sự kiện:

```java
import com.mongodb.event.ConnectionPoolListener;
import com.mongodb.event.ConnectionCheckedOutEvent;
import com.mongodb.event.ConnectionCheckedInEvent;
import com.mongodb.event.ConnectionCheckOutFailedEvent;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

public final class PoolCounters394 implements ConnectionPoolListener {
    private final LongAdder checkedOut = new LongAdder();
    private final LongAdder checkedIn = new LongAdder();
    private final LongAdder checkoutFailed = new LongAdder();

    @Override
    public void connectionCheckedOut(ConnectionCheckedOutEvent event) {
        checkedOut.increment();
        long waitMicros = event.getElapsedTime(TimeUnit.MICROSECONDS);
        // Gửi waitMicros tới histogram với server label an toàn.
    }

    @Override
    public void connectionCheckedIn(ConnectionCheckedInEvent event) {
        checkedIn.increment();
    }

    @Override
    public void connectionCheckOutFailed(
            ConnectionCheckOutFailedEvent event) {
        checkoutFailed.increment();
        String reason = event.getReason().name();
        // Counter cho từng reason: TIMEOUT/CONNECTION_ERROR/POOL_CLOSED...
    }

    public long failedCount() {
        return checkoutFailed.sum();
    }
}
```

### 12.1. Đăng ký CMAP listener

```java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToConnectionPoolSettings(b ->
        b.addConnectionPoolListener(new PoolCounters394()))
    .build();
```

### 12.2. LongAdder không tự tạo gauge chính xác

`checkedOut.sum() - checkedIn.sum()` chỉ là một ước lượng lượng in-use trên đời listener; pool clear/close, concurrent event delivery và restart có thể khiến phép trừ không còn ý nghĩa như **pool size hiện tại**.

Nếu cần gauges active/idle/pending chính xác theo từng server, dùng **pool lifecycle state được cập nhật đầy đủ** hoặc MXBean/instrumentation library có hỗ trợ; kiểm tra semantics khi clear và connection close.

### 12.3. Checkout duration

Trong Java Driver 5.x, `ConnectionCheckedOutEvent.getElapsedTime(TimeUnit)` đo từ checkout start đến checkout success. Đây là metric sát với **thời gian chờ connection**, có thể gồm thời gian thiết lập connection mới nếu cần.

Nên quan sát histogram p50/p95/p99 thay vì chỉ tổng số checkout.

## 13. Phân biệt ba nguyên nhân checkout failed

`ConnectionCheckOutFailedEvent.getReason()` mô tả những nhóm như:

- **TIMEOUT:** chờ connection vượt giới hạn.
- **CONNECTION_ERROR:** lỗi khi tạo/thiết lập connection.
- **POOL_CLOSED:** pool đã đóng.

### 13.1. TIMEOUT

Điều tra:

- `maxPoolSize` có bị chạm không?
- Checkout wait p95/p99 có tăng không?
- Operations có giữ connections quá lâu?
- HTTP concurrency có tăng đột ngột?
- `maxConnecting` có đang hạn chế tốc độ tạo connections mới?

### 13.2. CONNECTION_ERROR

Điều tra:

- DNS/TCP/TLS/CA/certificate.
- MongoDB host có reachable?
- Authentication failures.
- Network partition hoặc server overload.

**Tăng `maxPoolSize` không sửa lỗi certificate.**

### 13.3. POOL_CLOSED

Điều tra:

- `MongoClient.close()` đã bị gọi?
- Service đang shutdown?
- Có tạo client theo request rồi đóng sớm?

### 13.4. Không gộp tất cả checkout failures thành “MongoDB down”

Nếu host healthy nhưng checkout timeout vì application concurrency cao, đội database có thể không thấy lỗi server-side. Cần đo từ client.

## 14. Các cấu hình pool quan trọng

| Tùy chọn | Ý nghĩa | Trade-off |
|---|---|---|
| `maxPoolSize` | Số connection tối đa **mỗi pool** | Quá thấp: queue; quá cao: tải connections |
| `minPoolSize` | Mức duy trì connections tối thiểu | Quá cao: giữ tài nguyên không dùng |
| `maxConnecting` | Tốc độ thiết lập connections mới đồng thời **mỗi pool** | Quá thấp: cold-start tail latency |
| `maxIdleTimeMS` | Đóng connection idle quá lâu | Quá ngắn: handshake nhiều |
| `maxLifeTimeMS` | Tuổi thọ connection tối đa | Rotation churn nếu quá thấp |
| `maxWaitTime` / `waitQueueTimeoutMS` | Thời gian chờ checkout | Cần phối hợp deadline |
| `timeoutMS` (Client-Side Operation Timeout, khi hỗ trợ) | Budget tổng thời gian operation | Có thể thay thế/ưu tiên hơn legacy wait time setting |

### 14.1. Mặc định phổ biến trong tài liệu 5.x

```text
maxPoolSize   = 100 / server pool
minPoolSize   = 0
maxConnecting = 2
```

Đây là defaults của bộ tài liệu driver hiện hành, không phải cấu hình đề xuất cho mọi cluster. Có những default/timeouts khác tùy bản driver, API và URI.

### 14.2. Legacy `waitQueueTimeoutMS`

Tài liệu MongoDB Java Sync Driver hiện hành đánh dấu `waitQueueTimeoutMS` là **deprecated** và khuyến nghị client-level timeout cho một số kịch bản.

Nếu dự án cũ vẫn dùng `waitQueueTimeoutMS` hoặc builder `maxWaitTime`, cần hiểu tương tác với `timeoutMS` của version hiện hành. Đừng cộng nhiều timeout và kỳ vọng mỗi timeout tác động độc lập.

### 14.3. Giới hạn theo từng server

Với ba `mongos` và một MongoClient:

```text
maxPoolSize=100

Pool mongos-a: tối đa 100 pooled conns
Pool mongos-b: tối đa 100 pooled conns
Pool mongos-c: tối đa 100 pooled conns
```

Không hiểu `maxPoolSize=100` là “toàn bộ MongoClient chỉ có tối đa 100 sockets cho mọi server”.

## 15. Ví dụ cấu hình pool trong Java

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import java.util.concurrent.TimeUnit;

public final class ClientWithPool394 {
    public static MongoClient create(String uri) {
        return MongoClients.create(
            MongoClientSettings.builder()
                .applyConnectionString(new ConnectionString(uri))
                .applyToConnectionPoolSettings(b -> b
                    .maxSize(80)
                    .minSize(5)
                    .maxConnecting(4)
                    .maxConnectionIdleTime(60, TimeUnit.SECONDS)
                    .addConnectionPoolListener(new PoolCounters394()))
                .applyToClusterSettings(b -> b
                    .serverSelectionTimeout(15, TimeUnit.SECONDS))
                .retryWrites(true)
                .retryReads(true)
                .build());
    }
}
```

`80`, `5`, `4` và `15 seconds` là **giá trị minh họa**. Không áp vào production nếu chưa biết concurrency, số MongoClient instances, số servers và giới hạn server connections.

### 15.1. Pool size cần tính theo toàn bộ fleet

Ví dụ:

```text
Application replicas = 50
MongoClient per replica = 1
maxPoolSize per server = 80

Theoretical pooled capacity per targeted server
  = 50 * 80 = 4.000
```

Đó là **trần lý thuyết** khi mọi pool chạm max, chưa tính monitoring sockets, controllers/other apps, load distribution và topology. Server connections có thể quá cao dù một instance app chỉ có pool 80.

### 15.2. Little's Law như công cụ ước lượng

Tại trạng thái ổn định:

\[
L \approx \lambda W
\]

Nếu 500 requests/giây đồng thời dùng connection trung bình 20 ms:

\[
L \approx 500 \times 0.02 = 10
\]

Đây chỉ là **số in-flight DB operations trung bình** trong một giả thiết đơn giản, chưa tính burst, fan-out, transactions, pool per server và tail latency. Phải benchmark ở tải thực.

### 15.3. Không chữa mọi chậm trễ bằng pool lớn hơn

Nếu mỗi query mất 3 giây vì collection scan, mở thêm connections có thể tăng concurrency và làm server disk/CPU càng nghẽn. Tối ưu query/index trước hoặc cùng lúc với pool tuning.

## 16. Pool cleared sau failover

Một timeline phổ biến:

```text
T0   Primary A healthy
T1   Primary A steps down
T2   Driver detects network/not-primary error
T3   Pool to A cleared
T4   Server description for A changes
T5   Server B recognized as primary
T6   Pool to B creates/uses connections
T7   Commands succeed on B
```

### 16.1. Pool clear là một sự kiện hữu ích

Đếm `connectionPoolCleared` theo server có thể phát hiện:

- Failover/stepdown.
- Network instability.
- Server errors dẫn tới invalidation.
- Credential/certificate rollout bất ổn.

### 16.2. Không alert chỉ từ một clear

Pool clear có thể là hành vi phù hợp khi topology đổi. Nên alert khi:

- Clears lặp lại quá thường xuyên.
- Checkout failure rate tăng.
- Application errors kéo dài.
- SDAM không có writable server.

### 16.3. Connection pool churn

Tín hiệu:

```text
connectionsCreated/sec tăng
connectionsClosed/sec tăng
checkout duration p99 tăng
poolCleared/sec tăng
```

Có thể do network, aggressive idle/lifetime setting, quá nhiều `MongoClient`, app deploy restart hoặc election storm.

## 17. Detect connection leaks và long-held connections

Một connection checkout lâu không nhất thiết là leak. Nó có thể phục vụ:

- Query/aggregation chạy lâu.
- Transaction dài.
- Cursor đang được duyệt.
- Change stream/tailable behavior.
- Session hoặc workload bất thường.

### 17.1. Phân biệt leak với slow operation

```text
Scenario A:
  Pool in-use tăng
  Command duration tăng
  Server CPU/disk cao

=> Có thể query chậm, không hẳn leak.

Scenario B:
  Pool in-use tăng mãi
  Command rate không tương ứng
  Cursors/transactions mở lâu

=> Cần xem resource lifecycle/leak.
```

### 17.2. Cursor lifecycle trong Java

```java
import com.mongodb.client.MongoCursor;
import org.bson.Document;

try (MongoCursor<Document> cursor =
         collection.find().limit(1000).iterator()) {
    while (cursor.hasNext()) {
        Document doc = cursor.next();
        // Process minimally; avoid expensive blocking I/O in this loop.
    }
}
```

Sử dụng try-with-resources khi chủ động giữ cursor; không để cursor sống quá lâu hoặc quên close. Cơ chế giữ connection/cursor thực tế phụ thuộc driver/server operation.

### 17.3. Transactions

Transaction dài có thể ghim resources và gây contention. Không tạo transaction rồi chờ user confirmation trong vài phút.

### 17.4. Metrics bổ sung

Theo dõi open cursors, active transactions, command durations, pool in-use và application concurrency để phân biệt nguyên nhân.

## 18. JMX: lựa chọn theo dõi connection pools

Java Driver có `JMXConnectionPoolListener`, tạo MXBeans cho các pools để JConsole/JMX monitoring có thể thu thông tin.

Ví dụ:

```java
import com.mongodb.management.JMXConnectionPoolListener;

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToConnectionPoolSettings(b ->
        b.addConnectionPoolListener(
            new JMXConnectionPoolListener()))
    .build();
```

### 18.1. Khi nào dùng JMX?

- Ứng dụng Java đã dùng JMX exporter/APM.
- Muốn xem pool size/in-use/idle theo server.
- Muốn quan sát pool mà không phải tự viết state machine CMAP.

### 18.2. JMX không tự bảo mật

Nếu expose remote JMX, cần authentication/TLS/network isolation. Một JMX endpoint mở công khai có thể tiết lộ runtime/internal data.

### 18.3. Quan hệ với Micrometer/Prometheus

Có thể chuyển JMX metrics thành Prometheus hoặc đăng ký CMAP listeners với Micrometer. **Tránh chạy hai bộ instrumentation trùng thông tin** mà không có quy ước đơn vị và naming.

## 19. Command monitoring: nhìn lệnh thực thi

`CommandListener` lắng nghe các MongoDB command events phía client:

```text
CommandStartedEvent
       |
       +-- CommandSucceededEvent
       |
       +-- CommandFailedEvent
```

### 19.1. Field thường hữu ích

| Trường | Công dụng |
|---|---|
| `commandName` | Nhóm lệnh `find`, `insert`, `aggregate`, `update`... |
| `databaseName` | Phân vùng metrics theo database khi cho phép |
| `requestId` | Ghép start/result của một request command cụ thể |
| `operationId` | Tương quan các command attempts thuộc operation theo semantics driver |
| Connection/server metadata | Biết endpoint được gửi command |
| `elapsedTime` | Histogram thời gian command hoàn tất |
| Success/failure | Error rate theo command name và nhóm lỗi |

### 19.2. Những command nào không xuất hiện?

Driver không phát command monitoring events cho **một số internal commands**, gồm initial handshake/`hello` dùng cho monitoring topology.

Nếu muốn đo heartbeat, dùng `ServerMonitorListener`; không đếm `CommandStartedEvent("hello")` rồi khẳng định đã theo dõi SDAM đầy đủ.

### 19.3. Một query có nhiều commands

Cursor:

```text
find -> getMore -> getMore -> killCursors
```

Một API request có thể phát nhiều MongoDB commands, mỗi cái có duration riêng. Command count không đồng nghĩa HTTP request count.

## 20. Java `CommandListener` chỉ log metadata an toàn

```java
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import com.mongodb.event.CommandFailedEvent;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

public final class SafeCommandMetrics394 implements CommandListener {
    private final LongAdder succeeded = new LongAdder();
    private final LongAdder failed = new LongAdder();

    @Override
    public void commandStarted(CommandStartedEvent event) {
        // Chỉ lấy command name; KHÔNG log event.getCommand().
        String cmd = event.getCommandName();
        // Optional: count starts by allowlisted command names.
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        succeeded.increment();
        long millis = event.getElapsedTime(TimeUnit.MILLISECONDS);
        String cmd = event.getCommandName();
        // recordHistogram("mongodb.command.duration", millis, cmd);
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        failed.increment();
        long millis = event.getElapsedTime(TimeUnit.MILLISECONDS);
        String cmd = event.getCommandName();
        String failureType =
            event.getThrowable().getClass().getSimpleName();
        // Record only allowlisted cmd and failureType, not raw payload.
    }

    public long failedCommands() {
        return failed.sum();
    }
}
```

### 20.1. Đăng ký

```java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .addCommandListener(new SafeCommandMetrics394())
    .build();
```

### 20.2. Duration có đơn vị rõ

`getElapsedTime(TimeUnit.MILLISECONDS)` có thể làm tròn về 0 cho command rất nhanh. Với histogram microseconds:

```java
long micros = event.getElapsedTime(TimeUnit.MICROSECONDS);
```

Không trộn samples microseconds vào dashboard đặt đơn vị milliseconds.

### 20.3. Duration chỉ cho một command attempt

Command duration không bao gồm toàn bộ server selection/pool checkout và các lần retry nếu đo riêng từng attempt. Kết hợp với end-to-end tracing/request histogram.

## 21. Command metrics không phải profiling phía server

### 21.1. Client-side duration

`CommandSucceededEvent.getElapsedTime()` đo thời gian của command attempt qua driver, gồm các yếu tố truyền dữ liệu/trả reply theo định nghĩa.

### 21.2. Server-side query execution

MongoDB `explain("executionStats")`, profiler, slow query logging và `serverStatus` giúp xem:

- Index scan và `COLLSCAN`.
- `totalKeysExamined`, `totalDocsExamined`.
- Server execution time.
- Query shape, locks/CPU/disk theo khả năng.

### 21.3. Hai nguồn có thể khác nhau

Ví dụ:

```text
Client command elapsed: 250 ms
Server query processing: 30 ms
```

Có thể còn network, server queueing, reply transfer, client effects hoặc sự khác nhau của phép đo. Đừng tuyên bố chắc chắn “220 ms là network” chỉ vì hai số chênh nhau.

### 21.4. Một query không phải một operation

`find` + `getMore`, `aggregate` với cursor, bulk write, transaction commit đều có thể sinh nhiều command events. Hãy gắn instrumentation với business trace nếu cần phân tích tổng.

## 22. Bảo mật: command payload có thể là PII hoặc secret

**Không** ghi nguyên command:

```java
// Chống chỉ định trên production:
System.out.println(event.getCommand().toJson());
```

Trong filter/update có thể có:

- Email, số điện thoại, địa chỉ, personal IDs.
- Password reset tokens hoặc refresh tokens.
- Nội dung order/payment.
- Tenant identifiers và business logic.
- Tên collection/namespace nhạy cảm.

### 22.1. Driver redaction có giới hạn

Driver có cơ chế tự redaction cho **một số command events nhạy cảm** theo specification, nhưng không có nghĩa **mọi `find`/`update` payload đều được che**.

Application logger trực tiếp serialize `event.getCommand()` có thể làm lộ dữ liệu.

### 22.2. Structured metadata được phép

```text
service=order-api
command=update
result=failed
exceptionFamily=connectivity
durationMs=12
topologyType=replicaSet
```

### 22.3. Không log raw connection string

```java
// Sai: có thể chứa username/password và query parameters nhạy cảm.
log.info("Connecting with URI: {}", mongoUri);

// Tốt hơn:
log.info("Initializing MongoDB client for service=order-api");
```

### 22.4. Trường hợp cần debug sâu

Sử dụng staging dữ liệu giả, sampling có thời hạn, masking, access approval và retention rõ. Không bật raw command logging trên toàn bộ production chỉ để tìm một lỗi.

## 23. Request IDs, operation IDs và trace IDs

### 23.1. Request ID của driver

`CommandStartedEvent.getRequestId()` liên quan đến request command; hữu ích ghép events trong cùng client/connection context.

### 23.2. Operation ID

`getOperationId()` có thể giúp tương quan commands của một logical driver operation theo semantics driver version, nhưng **không là business request ID** toàn hệ thống.

### 23.3. HTTP trace

```text
HTTP requestId = R1001
     |
     v
OrderService span = S23
     |
     v
MongoDB command operation (find/update)
     |
     v
driver requestId / operationId
```

Muốn gắn đúng các lớp cần framework instrumentation/OpenTelemetry context propagation phù hợp. Không đoán rằng driver requestId tự động chứa ID của HTTP request.

### 23.4. Cardinality cảnh báo

Không dùng `requestId`, `operationId`, `orderId` hay raw userId làm **Prometheus metric labels**; cardinality có thể tăng không giới hạn. Dùng chúng trong traces/logs được bảo vệ khi cần.

## 24. Đặt tên metrics và labels có chủ đích

### 24.1. Gợi ý metrics

| Metric | Type | Labels giới hạn |
|---|---|---|
| `mongo_driver_topology_writable` | Gauge 0/1/unknown | service, deployment |
| `mongo_driver_sdam_changes_total` | Counter | type, deployment |
| `mongo_driver_heartbeat_failures_total` | Counter | server group, reason class |
| `mongo_driver_pool_checkout_seconds` | Histogram | service, server role |
| `mongo_driver_pool_checkout_failures_total` | Counter | reason, server group |
| `mongo_driver_pool_clears_total` | Counter | server group |
| `mongo_driver_command_seconds` | Histogram | command, outcome |
| `mongo_driver_command_failures_total` | Counter | command, error family |
| `mongo_driver_application_errors_total` | Counter | business operation, retry decision |

**Đây là một naming scheme gợi ý**, không phải metrics tự động do MongoDB Java Driver phát ở những tên này.

### 24.2. Các nhãn thường nguy hiểm

- Raw MongoDB URI, hostnames cá nhân nhạy cảm.
- Collection name do user tự tạo không giới hạn.
- User/email/token/orderId/requestId.
- Exception message chứa literal query.
- `getThrowable().toString()` làm label.

### 24.3. Dùng histogram thay vì chỉ average

```text
avg command latency = 10 ms
p99 command latency = 1500 ms
```

Average nhìn có vẻ tốt nhưng 1% requests rất chậm. Pool checkout p99 và server selection timeout cũng cần quan sát.

## 25. Observability: metrics, logs và traces khác nhau

**Metrics:** tổng hợp, phù hợp alerts và SLO; ít labels.

**Logs:** kể lại events có ngữ cảnh, phải redact/scope/retention.

**Traces:** nối những spans qua API → service → MongoDB để thấy độ trễ end-to-end.

### 25.1. Ví dụ cấu trúc trace

```text
POST /checkout [480 ms]
  validation [2 ms]
  MongoDB find inventory [10 ms]
  MongoDB update inventory [40 ms]
  MongoDB insert order [35 ms]
  payment RPC [360 ms]
```

Nếu chỉ nhìn MongoDB commands, hệ thống có thể bỏ qua 360 ms ở payment RPC.

### 25.2. Một trace chưa phải mẫu thống kê

Trace một request nhanh không chứng minh p95 tốt. Metrics cung cấp phân bố, traces giúp giải thích các mẫu bất thường.

### 25.3. Driver listener không làm sampling tự động

Nếu cần sampling traces/command events, thiết kế ở instrumentation layer và giữ counters bao quát. Không sample mất hết những sự kiện lỗi hiếm nhưng quan trọng.

## 26. Exception taxonomy: bắt đầu từ `MongoException`

Đa số các lỗi MongoDB Java Driver liên quan hoạt động MongoDB thuộc họ `com.mongodb.MongoException`, nhưng vẫn có thể gặp:

- `IllegalArgumentException` do input invalid.
- `CodecConfigurationException` hoặc BSON/serialization errors.
- `NullPointerException`/application bugs.
- Exception do network/TLS/JVM dưới dạng cause.

**Không catch `Exception` rồi coi mọi lỗi là MongoDB tạm thời.**

### 26.1. Một bảng phân loại thực dụng

| Nhóm | Exception thường thấy | Gợi ý hướng xử lý |
|---|---|---|
| **Server selection / topology** | `MongoTimeoutException` | SDAM, no primary, host selection, timeout |
| **Socket/network** | `MongoSocketException` và subclasses | DNS/TCP/TLS/proxy/network, unknown outcome |
| **Authentication** | `MongoSecurityException`; server command error 18 | Credentials/authSource/cert/RBAC |
| **Authorization** | `MongoCommandException` với code 13 | Quyền user/role, fail fast |
| **Write duplicate/conflict** | `MongoWriteException`, `MongoBulkWriteException` | Error code/indices/idempotency |
| **Write concern** | `MongoWriteConcernException` | Acknowledgement chưa đạt, reconcile |
| **Server command** | `MongoCommandException` | Code, error labels, command context |
| **Execution timeout** | `MongoExecutionTimeoutException` hoặc timeout code | Query plan/maxTimeMS/resource |
| **Transactions** | `MongoException` có transaction error labels | Retry body/commit theo semantics |
| **Serialization/config** | BSON/codec/config exceptions | Sửa code/schema/config, không retry vô hạn |

### 26.2. Exception type không đủ để quyết định retry

`MongoCommandException` có thể là lỗi validation, authentication, not-primary hoặc command bị từ chối. Cần xem error code, label, command name và context.

### 26.3. Chú ý subclass và thứ tự catch

Nếu catch `MongoException` trước `MongoWriteException`, block specialized ở dưới sẽ không bao giờ chạy. Khi cần phân biệt, catch subclass trước, generic sau.

## 27. Phân biệt bốn kiểu timeout

| Loại timeout | Xảy ra ở bước | Triệu chứng/nguồn |
|---|---|---|
| **Server selection timeout** | Tìm server phù hợp | `MongoTimeoutException`, cluster description |
| **Pool checkout timeout** | Chờ connection từ pool | CMAP checkout failed: TIMEOUT |
| **Socket/connect timeout** | Thiết lập hoặc I/O kết nối | Socket/network exception và cause |
| **Server execution timeout** | Server giới hạn thời gian chạy | `maxTimeMS`, lỗi server code/exception |

### 27.1. Server selection

```text
No server matches ReadPreference.primary
Cause: election, only secondaries visible, bad TLS/DNS, network partition
```

Giải pháp: xem SDAM topology, host states, server-side election/quorum, TLS/firewall. **Tăng pool size không tạo primary.**

### 27.2. Pool checkout

```text
Primary discovered and healthy
Command hasn't started
Checkout fails with TIMEOUT
```

Giải pháp: pool size, checkout duration, in-use connections, slow operations, app concurrency, maxConnecting.

### 27.3. Socket/connect

```text
Socket connection refused / read timed out / TLS handshake failed
```

Giải pháp: network/TLS/cert/DNS, server capacity, proxy/load balancer, client socket timeout. Có thể có **unknown write outcome** nếu request đã tới server trước lỗi.

### 27.4. Server execution

```javascript
db.orders.find({ status: "CREATED" })
  .maxTimeMS(2000);
```

Server có thể ngắt operation khi vượt giới hạn theo semantics, trả lỗi thích hợp. Không chữa `COLLSCAN` rất nặng bằng cách chỉ tăng mọi timeout.

### 27.5. Client-Side Operation Timeout

Java driver 5.x có cơ chế `timeoutMS` tùy version/API để giới hạn **toàn bộ operation budget**. Nó không đồng nghĩa với `maxTimeMS` ở server và có thể thay đổi hành vi các timeout cũ.

Khi điều chỉnh, phải hiểu **timeout nào thật sự kích hoạt** từ exception + CMAP/SDAM/command events.

## 28. Nhóm lỗi server thường gặp

| Tình huống | Dấu hiệu | Cần làm |
|---|---|---|
| Duplicate key | Error code `11000`; `MongoWriteException` hoặc bulk write error | Kiểm tra unique key, idempotency |
| Unauthorized | Error code `13` | RBAC/role/namespace, không retry |
| Authentication failed | Error code `18` | user/authSource/secret/mechanism |
| Not primary / topology change | Server code/error label phù hợp | SDAM + driver retry + failover |
| Write concern failed/timeout | Write concern exception/detail | Đối chiếu outcome và majority |
| Execution time exceeded | `maxTimeMS` liên quan | Query plan, index, resource |
| Transient transaction failure | `TransientTransactionError` label | Retry toàn transaction hợp lệ |
| Unknown transaction commit | `UnknownTransactionCommitResult` label | Retry commit theo protocol |

### 28.1. Không hardcode mọi số lỗi vào một enum ứng dụng

MongoDB server versions có thể bổ sung/sửa error codes và labels. Ưu tiên **API error labels** cho semantics retry khi được hỗ trợ, kết hợp known codes cho chính sách nghiệp vụ cụ thể như duplicate key.

### 28.2. Duplicate key không nhất thiết là “tất cả lỗi DB”

Unique index vi phạm có thể là:

- Business conflict hợp lệ.
- Client retry cùng requestId.
- Bug tạo ID.
- Data migration duplicate.

Ứng dụng cần phân biệt các trường hợp đó, không nhất thiết trả HTTP 500.

### 28.3. Authorization 13 không giống authentication 18

- **Authentication:** danh tính/credential không được chấp nhận.
- **Authorization:** đã có danh tính nhưng quyền không cho phép hành động.

Chúng có nguyên nhân và runbook khác nhau.

## 29. `MongoException.hasErrorLabel()`

Java driver hỗ trợ:

```java
boolean transientTxn =
    e.hasErrorLabel("TransientTransactionError");

boolean unknownCommit =
    e.hasErrorLabel("UnknownTransactionCommitResult");
```

Những labels quan trọng:

- `RetryableWriteError`: gợi ý lỗi có semantics retry theo driver/protocol.
- `TransientTransactionError`: có thể retry **toàn transaction** theo transaction API.
- `UnknownTransactionCommitResult`: kết quả commit chưa xác định; xử lý **retry commit** theo quy trình.
- `NoWritesPerformed`: trong những server versions hỗ trợ, dùng để diễn đạt không có write nào được thực hiện trong các attempts của retryable write.
- `ResumableChangeStreamError`: một số change stream errors có thể resume theo protocol.

### 29.1. Error labels không phải nhãn lỗi nghiệp vụ

`DuplicateKey` có thể được ứng dụng xem là “đã có order”, nhưng đó là domain decision dựa trên unique key và trạng thái thực tế, không phải một nhãn retry để gọi lại insert vô hạn.

### 29.2. Đừng tự tạo nhãn tùy ý rồi gắn vào exception

Driver/server quyết định labels theo protocol. Policy của ứng dụng có thể ánh xạ chúng thành `retryable`, `reconcile`, `permanent`, nhưng phải ghi rõ đó là **app classification**, không phải label MongoDB tự phát.

### 29.3. Phân biệt mong muốn và kết quả

`UnknownTransactionCommitResult` không có nghĩa transaction chưa commit. Nó nói **không biết kết quả commit tại thời điểm lỗi**. Retry toàn bộ business action có thể tạo side effect lặp.

## 30. Quyết định xử lý exception: fail fast, retry hay reconcile?

Một hệ thống vận hành cần **phân loại hành động**, không chỉ liệt kê class exceptions.

| Quyết định | Nghĩa | Ví dụ |
|---|---|---|
| **FAIL_FAST** | Trả lỗi rõ; cần sửa input/role/config | Authentication, unauthorized, validation |
| **RETRY_BOUNDED** | Retry trong ngân sách cho thao tác đủ điều kiện | Read idempotent và lỗi tạm thời |
| **RETRY_TRANSACTION** | Retry toàn transaction theo protocol | `TransientTransactionError` |
| **RETRY_COMMIT** | Retry commit, không tự chạy lại body | `UnknownTransactionCommitResult` |
| **RECONCILE_OUTCOME** | Đọc trạng thái theo operation ID trước khi quyết định | Network timeout sau write |
| **ALERT_AND_ESCALATE** | Có thể cần điều tra hạ tầng/rủi ro dữ liệu | Không có majority, outage dài, write concern |

### 30.1. Có ba câu hỏi trước khi retry

1. **Lỗi có thể tạm thời không?** Network failover khác duplicate key.
2. **Operation có thể retry an toàn không?** Một `find` khác với việc trừ tiền hoặc `$inc` cho business event mới.
3. **Có deadline và budget không?** Retry vô hạn có thể tạo retry storm, vượt SLO và tăng tải MongoDB.

### 30.2. Unknown result là trạng thái nghiệp vụ riêng

```text
Client sends write
    |
    +-- Server applied write
    |
    +-- Connection lost before response
    |
    v
Client sees MongoSocketException
```

Ứng dụng không biết server đã áp dụng hay chưa, trừ khi xác minh bằng trạng thái có identity ổn định hoặc protocol retry phù hợp.

### 30.3. Đừng retry theo tên exception thôi

Hai `MongoSocketException` có thể khác nhau:

- `find` không có side effect: retry hữu hạn thường có thể xem xét.
- `$inc` được gửi và response mất: retry như một lệnh business mới có thể đếm hai lần.

Phân loại phải kết hợp **loại thao tác + trạng thái session/transaction + labels + domain idempotency**.

## 31. Ví dụ Java: classifier cho xử lý lỗi nghiệp vụ

Ví dụ này minh họa cách **đề xuất hành động**; nó không tự thực hiện retry.

```java
import com.mongodb.MongoException;
import com.mongodb.MongoSocketException;
import com.mongodb.MongoTimeoutException;
import com.mongodb.MongoSecurityException;
import com.mongodb.MongoWriteException;
import com.mongodb.MongoWriteConcernException;
import com.mongodb.MongoCommandException;

public final class MongoErrorDecision394 {
    public enum Decision {
        FAIL_FAST,
        RETRY_OPERATION_IF_SAFE,
        RETRY_TRANSACTION,
        RETRY_COMMIT_ONLY,
        RECONCILE_WRITE_OUTCOME,
        ALERT_AND_INVESTIGATE
    }

    public static Decision classify(
            MongoException e,
            boolean writeOperation,
            boolean transactionOperation) {

        // Xem error labels trước những nhóm type chung.
        if (transactionOperation
                && e.hasErrorLabel("UnknownTransactionCommitResult")) {
            return Decision.RETRY_COMMIT_ONLY;
        }

        if (transactionOperation
                && e.hasErrorLabel("TransientTransactionError")) {
            return Decision.RETRY_TRANSACTION;
        }

        if (e instanceof MongoSecurityException) {
            return Decision.FAIL_FAST;
        }

        if (e instanceof MongoWriteException) {
            MongoWriteException write = (MongoWriteException) e;
            if (write.getError().getCode() == 11000) {
                return Decision.FAIL_FAST;
            }
        }

        if (e instanceof MongoCommandException) {
            int code = ((MongoCommandException) e).getErrorCode();
            if (code == 13 || code == 18) {
                return Decision.FAIL_FAST;
            }
        }

        if (e instanceof MongoWriteConcernException) {
            // Write có thể đã được áp dụng nhưng chưa đạt write concern.
            return Decision.RECONCILE_WRITE_OUTCOME;
        }

        if (e instanceof MongoSocketException) {
            return writeOperation
                    ? Decision.RECONCILE_WRITE_OUTCOME
                    : Decision.RETRY_OPERATION_IF_SAFE;
        }

        if (e instanceof MongoTimeoutException) {
            return writeOperation
                    ? Decision.RECONCILE_WRITE_OUTCOME
                    : Decision.RETRY_OPERATION_IF_SAFE;
        }

        return Decision.ALERT_AND_INVESTIGATE;
    }
}
```

### 31.1. Tại sao classifier không gọi retry tự động?

Vì nó **chưa biết**:

- Write có idempotency key hay không.
- Client đã sử dụng retryable-write protocol chưa.
- Operation có chạy trong transaction không.
- Deadline còn bao nhiêu.
- Loại lệnh có được retry theo tài liệu driver không.
- Dữ liệu nghiệp vụ có cho phép apply lại không.

Những thông tin này thuộc orchestration/application service.

### 31.2. Classifier cần phát triển theo ứng dụng

Classifier ở trên **không bao quát** `MongoBulkWriteException`, mọi error code, nested causes hoặc các timeout mới. Nó chỉ minh họa phân loại rủi ro, không phải thư viện production.

Không sửa `MongoCommandException` code 13 bằng cách thêm `root` cho application mà chưa review quyền và resource.

### 31.3. Error classification phải được test

Một test table:

```text
Duplicate key            -> FAIL_FAST / domain-conflict
Auth failure             -> FAIL_FAST / configuration/security
Unknown commit label     -> RETRY_COMMIT_ONLY
Transient transaction    -> RETRY_TRANSACTION
Network after write      -> RECONCILE_WRITE_OUTCOME
Read selection timeout   -> RETRY_OPERATION_IF_SAFE (bounded)
```

Các test còn phải kiểm tra không log raw PII/secret trong exception messages.

## 32. Catch exception trong Java Sync Driver

Ví dụ write một order có ID cố định:

```java
import com.mongodb.MongoException;
import com.mongodb.MongoWriteException;
import com.mongodb.MongoTimeoutException;
import com.mongodb.MongoSocketException;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public final class OrderInsert394 {
    public static void insert(
            MongoCollection<Document> orders,
            String orderId,
            String tenantId) {

        try {
            orders.insertOne(new Document("_id", orderId)
                .append("tenantId", tenantId)
                .append("status", "CREATED"));

            System.out.println("ORDER_CONFIRMED");

        } catch (MongoWriteException e) {
            if (e.getError().getCode() == 11000) {
                // Không mặc định coi duplicate là lỗi hạ tầng.
                // Kiểm tra order hiện có có cùng requestId và payload không.
                System.out.println("ORDER_ALREADY_EXISTS_CHECK");
            } else {
                throw e;
            }

        } catch (MongoSocketException e) {
            // Outcome có thể chưa biết nếu request đã đến server.
            System.err.println("ORDER_OUTCOME_UNCERTAIN");
            throw e;

        } catch (MongoTimeoutException e) {
            System.err.println("ORDER_TIMEOUT_INVESTIGATE");
            throw e;

        } catch (MongoException e) {
            System.err.println(
                "ORDER_DATABASE_FAILURE type=" +
                e.getClass().getSimpleName());
            throw e;
        }
    }
}
```

### 32.1. Mục đích catch

Ví dụ chỉ giúp phân tách **observability và xử lý phù hợp**, chưa phải API idempotency hoàn chỉnh. Production cần trả kết quả theo business requestId, kiểm tra trạng thái khi duplicate/timeout và không xác nhận thành công chỉ vì đã bắt được exception.

### 32.2. Không log toàn `e.getMessage()` vô điều kiện

Một số exception messages có topology addresses, command details hoặc metadata nhạy cảm. Log class name, safe error code/category, correlation ID và bổ sung chi tiết dưới quyền truy cập hạn chế khi cần.

## 33. Bulk write exception: lỗi có thể xảy ra một phần

Khi dùng `bulkWrite()`, một phần operations có thể thành công và phần khác thất bại tùy ordered/unordered mode.

```java
import com.mongodb.MongoBulkWriteException;
import com.mongodb.bulk.BulkWriteError;

try {
    collection.bulkWrite(writeModels);
} catch (MongoBulkWriteException e) {
    for (BulkWriteError error : e.getWriteErrors()) {
        int index = error.getIndex();
        int code = error.getCode();

        // Index liên hệ tới vị trí operation trong batch.
        // Không log raw document ở đây.
        System.err.println(
            "Bulk write error index=" + index +
            " code=" + code);
    }

    // Kiểm tra write result và write concern exception nếu có.
    throw e;
}
```

### 33.1. Ordered vs unordered

- `ordered=true`: driver/server dừng xử lý theo semantics của batch khi có lỗi.
- `ordered=false`: nhiều operations có thể được thử độc lập; thứ tự/chi tiết không được hiểu như transaction.

### 33.2. Không replay cả batch mù quáng

Nếu 700/1.000 writes đã thành công, gửi lại 1.000 writes như lệnh mới có thể tạo duplicates hoặc double increments.

Cần identity/idempotency từng item và reconciliation của những item chưa chắc chắn.

### 33.3. Write concern khác write error

Một command có thể ghi dữ liệu nhưng không đạt write concern. Phân biệt lỗi write validation/duplicate với **acknowledgment/durability uncertainty**.

## 34. Transaction labels và retry đúng tầng

### 34.1. TransientTransactionError

Nếu operation trong transaction thất bại với `TransientTransactionError`:

```text
startTransaction
    |
    v
body operations
    |
    v
TransientTransactionError
    |
    v
abort/cleanup
    |
    v
retry entire transaction (bounded)
```

### 34.2. UnknownTransactionCommitResult

Nếu commit trả `UnknownTransactionCommitResult`:

```text
transaction body successful
          |
          v
commitTransaction()
          |
          v
unknown commit result
          |
          v
retry commit as prescribed
          |
          v
confirmed outcome or explicit unresolved handling
```

**Không tự khởi chạy lại transaction body ngay chỉ vì commit response bị mất**, vì transaction có thể đã commit.

### 34.3. Callback API

Driver cung cấp transaction callback/convenient API trên những phiên bản tương ứng để tự xử lý nhiều trường hợp retry theo labels. Khi dùng helper, phải hiểu callback có thể chạy nhiều lần.

### 34.4. Side effects ngoài DB

Không đưa code gửi SMS/email/thu tiền ngoài MongoDB trực tiếp vào một callback có thể retry nếu chưa có idempotency/transactional outbox.

```text
MongoDB transaction:
  update order
  insert outbox event
commit
     |
     v
Outbox worker (idempotent)
     |
     v
Send notification / payment integration
```

### 34.5. Retry budget

Transaction retry phải có deadline/backoff. Không retry vô hạn khi thiếu majority, backend down hoặc lỗi không transient.

## 35. Retryable writes: driver retry khác business retry

### 35.1. Driver retry

Trong deployment được hỗ trợ, Java Driver có `retryWrites(true)`. Driver tự retry những write attempts đủ điều kiện theo retryable-write protocol khi gặp lỗi phù hợp.

### 35.2. Business retry

Một client HTTP gửi `POST /orders` lần hai là **business request khác** nếu backend tạo mới mỗi lần, dù driver đã dùng `retryWrites`.

```text
HTTP POST request R1
  -> insert order O1
  -> server executes
  -> response lost

HTTP POST request R2
  -> backend generates order O2
  -> insert succeeds

=> Double order despite driver retryWrites.
```

### 35.3. Idempotency key

Ví dụ document:

```javascript
{
  _id: "O394-1",
  tenantId: "T01",
  requestId: "CHECKOUT-REQ-394",
  status: "CREATED"
}
```

Unique index:

```javascript
db.orders394.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true }
);
```

Khi trùng requestId, backend đọc order hiện có và xác minh payload/state trước khi trả lại kết quả. Với sharded collections, unique index phải tuân thủ quy tắc shard key.

### 35.4. `$inc` dễ gây lặp

```javascript
db.stats394.updateOne(
  { _id: "orders" },
  { $inc: { count: 1 } }
);
```

Chạy lại như một operation nghiệp vụ mới có thể tăng hai lần. Cần operation ID và deduplication/outbox/transaction semantics thích hợp.

### 35.5. `NoWritesPerformed` không mặc định luôn có

Label `NoWritesPerformed` chỉ có trong những điều kiện/version cụ thể và không xuất hiện trong mọi failure. **Thiếu label này không chứng minh write đã xảy ra.**

## 36. Code Java tổng hợp đăng ký cả bốn nhóm listener

Ví dụ tích hợp trong một lớp factory:

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

import java.util.concurrent.TimeUnit;

public final class InstrumentedMongoClient394 {
    private InstrumentedMongoClient394() {}

    public static MongoClient create() {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI missing");
        }

        return MongoClients.create(
            MongoClientSettings.builder()
                .applyConnectionString(new ConnectionString(uri))
                .applyToClusterSettings(b -> b
                    .addClusterListener(new WritableTopology394())
                    .serverSelectionTimeout(15, TimeUnit.SECONDS))
                .applyToServerSettings(b -> {
                    b.addServerListener(new ServerChange394());
                    b.addServerMonitorListener(
                        new HeartbeatCounters394());
                })
                .applyToConnectionPoolSettings(b -> b
                    .maxSize(80)
                    .minSize(5)
                    .maxConnecting(4)
                    .addConnectionPoolListener(
                        new PoolCounters394()))
                .addCommandListener(new SafeCommandMetrics394())
                .retryReads(true)
                .retryWrites(true)
                .build());
    }
}
```

### 36.1. Các lớp tham chiếu

`WritableTopology394`, `ServerChange394`, `HeartbeatCounters394`, `PoolCounters394`, `SafeCommandMetrics394` đã được giới thiệu ở các mục trước.

Đặt chúng thành các classes nguồn tương ứng hoặc inner classes phù hợp trong dự án. Snippet factory giả định đã có các lớp đó, không phải một file Java duy nhất tự chứa mọi class.

### 36.2. Production instrumentation

Thay `System.out.println` bằng metrics/traces/logging đã kiểm soát. Không dùng listener giữ tài nguyên vô hạn hoặc call MongoDB trong callback.

### 36.3. Không lẫn profile settings với diagnostics

Pool `maxSize(80)` trong ví dụ chỉ để minh họa API. Nếu một service có 100 replicas, tổng pool capacity có thể rất lớn; cần capacity planning và connection limits của cluster.

## 37. Một lab không phá dữ liệu để phát sinh command events

### 37.1. Tạo client và query `ping`

```java
import com.mongodb.client.MongoClient;
import org.bson.Document;

try (MongoClient client = InstrumentedMongoClient394.create()) {
    Document result = client.getDatabase("admin")
        .runCommand(new Document("ping", 1));

    System.out.println(
        "Ping result ok=" + result.get("ok"));
}
```

`ping` tạo một command application-level, có thể phát command monitoring event trong khi server handshake `hello` nội bộ không phát như vậy.

### 37.2. Truy vấn read-only

```java
long count = client
    .getDatabase("driver_lab_394")
    .getCollection("sample394")
    .countDocuments();

System.out.println("count=" + count);
```

Nếu collection không tồn tại, count có thể là 0 tùy semantics, không cần drop/recreate dữ liệu thật chỉ để test listener.

### 37.3. Quan sát các events

Khi một read chạy, có thể có:

- SDAM cluster/server events trong lúc discovery.
- CMAP pool opened, connection created/ready.
- Checkout/checkin.
- Command started/succeeded.

Đừng kỳ vọng chính xác **một event của mỗi loại cho mọi request**; caching/pooling/background monitoring khiến số lượng khác nhau.

### 37.4. Chỉ tạo lỗi trên môi trường lab

Để kiểm tra `DuplicateKey`, dùng collection thử riêng và unique ID cố định trong lab; không thử cố tình sai password/mạng/stepdown trên production.

## 38. Dashboard tối thiểu cho Java + MongoDB

```text
┌────────────────────────────────────────────────────┐
│ MongoDB Java Driver Health — order-api              │
├────────────────────────────────────────────────────┤
│ Topology                                             │
│ writable server known: yes                           │
│ server description changes (5m): 2                   │
│ heartbeat failure rate: 0.1%                         │
├────────────────────────────────────────────────────┤
│ Pools                                                │
│ total in-use / available: 45 / 55                    │
│ checkout p95: 3 ms; p99: 35 ms                       │
│ checkout failures: 0.02% (TIMEOUT)                   │
│ pool clears (5m): 1                                 │
├────────────────────────────────────────────────────┤
│ Commands                                             │
│ find p95: 18 ms; update p95: 35 ms                   │
│ command failure rate: 0.2%                           │
│ top failure family: not-primary during election      │
├────────────────────────────────────────────────────┤
│ Application                                          │
│ HTTP 5xx: 0.3%; checkout SLO: degraded              │
│ retry attempts/request: increasing                   │
└────────────────────────────────────────────────────┘
```

Các số trên chỉ là **dữ liệu giả lập**. Một deployment thật cần phân biệt MongoClient, server, cluster, application version và metric sampling windows.

### 38.1. Thêm server-side metrics

Đi cùng dashboard driver:

- Replica set election/primary availability.
- Replication lag và oplog window.
- MongoDB CPU/memory/disk IOPS.
- `connections.current` và giới hạn connections.
- Slow query/profiler và index usage.
- Network throughput/latency.

### 38.2. Mọi biểu đồ phải ghi đơn vị

- Seconds cho pool checkout.
- Milliseconds hoặc microseconds cho command latency.
- Counters tăng theo thời gian.
- Gauges hiện trạng không cộng dồn như counters.

### 38.3. Không lấy average làm bằng chứng p99

Latency có tail dài; p95/p99 phù hợp để phát hiện người dùng bị ảnh hưởng dù average vẫn tốt.

## 39. Alerts và ngưỡng theo triệu chứng

| Alert | Điều kiện gợi ý | Điều tra ưu tiên |
|---|---|---|
| Không có writable server | Kéo dài quá grace window | SDAM, election, quorum, network |
| Heartbeat failures tăng | Tăng liên tục ở một server | Network/TLS/host |
| Pool checkout p99 cao | Vượt SLO trong vài phút | Pool in-use, slow queries, app concurrency |
| Pool checkout TIMEOUT | Failed rate tăng | Exhaustion/leak/maxConnecting |
| Pool clear storm | Nhiều clears/phút | Stepdown, connection resets, proxy |
| Command duration p99 cao | Chỉ một command type tăng | Explain/index/server resources |
| Command failure tăng | Theo command và exception family | App release, server changes |
| Authentication failures | Xuất hiện sau deploy/rotation | Secret/authSource/CA |
| Unknown write outcome | Bất thường ở critical flow | Reconciliation/idempotency |
| Transaction retry spike | Tăng cùng failover/contension | Election, write conflicts |
| Instrumentation silent | Events/metrics biến mất | Listener wiring/exporter |

### 39.1. Threshold phải theo workload

Không đặt quy tắc “checkout > 10 ms là critical” cho mọi ứng dụng. Những request dài, region xa, cold starts hoặc load spikes có phân bố khác nhau.

### 39.2. Dùng SLO + duration

Một spike 1 giây có thể không cần paging, nhưng 5 phút không có primary trong service ghi đơn hàng là nghiêm trọng. Cảnh báo phải gắn với tác động nghiệp vụ.

### 39.3. Đừng biến metrics missing thành 0

Nếu listener bị tháo hoặc process crash, `command_failed_total` không tăng không đồng nghĩa mọi command thành công. Cần alert về **thiếu telemetry**.

## 40. Runbook 1 — Server selection timeout khi chuyển primary

### Dấu hiệu

```text
MongoTimeoutException:
Timed out while waiting for a server
that matches ReadPreferenceServerSelector{readPreference=primary}
```

### Điều tra

1. Xem `ClusterDescriptionChangedEvent` trước/sau lỗi.
2. Xem `ServerDescriptionChangedEvent` và heartbeat failures.
3. Xác nhận primary từ MongoDB/Atlas/`rs.status()` nếu có quyền.
4. Kiểm tra voter majority và election history.
5. Kiểm tra DNS/SRV/TLS/firewall từ application environment.
6. Kiểm tra application URI có `replicaSet` đúng, không `directConnection=true` nhầm.
7. Đối chiếu API failures/retry latency và affected instances.

### Phản ứng

- Với election đang tiến triển: dùng driver retry, bounded request deadlines và backpressure.
- Với mismatch TLS/DNS: sửa certificate/network, không bỏ validate.
- Với thiếu quorum: khôi phục member/connectivity theo runbook, không tùy ý force reconfig.

### Điều **không** nên làm

Không tăng `maxPoolSize` khi cluster không có primary. Không restart tất cả services đồng loạt khiến connection storm.

## 41. Runbook 2 — Pool checkout timeout nhưng primary vẫn khỏe

### Dấu hiệu

```text
Topology writable = true
Heartbeat success = normal
Command duration p95 = 15 ms
Pool checkout p99 = 3 seconds
CheckoutFailed reason = TIMEOUT
```

### Điều tra

1. Xem active/idle/waiting pool metrics theo server.
2. Xác minh `maxPoolSize`/`maxConnecting`/client timeout.
3. Xem app concurrency và số MongoClients.
4. Tìm cursor/transaction giữ connection lâu.
5. Kiểm tra command latency của những queries chạy lâu.
6. Xem server connection limits và CPU/disk.

### Biện pháp

- Giảm burst bằng backpressure/queue bounds.
- Sửa code mở cursor/transaction không close.
- Tối ưu query/index nếu command chậm.
- Điều chỉnh pool size/cold-start ramp nếu capacity cho phép.
- Không tăng tất cả pool sizes lên vô hạn.

### Tiêu chí giải quyết

Checkout p95/p99 trở lại baseline, failure rate giảm, không có tăng quá mức server connections, API p95 ổn định.

## 42. Runbook 3 — Pool clear liên tục sau deploy

### Dấu hiệu

```text
poolCleared rate tăng
ConnectionCreated/sec tăng
TLS handshakes/sec tăng
CommandFailed tăng
```

### Điều tra

- Deploy có đổi CA/certificate/hostname không?
- Primary có election liên tục không?
- Client có gửi qua load balancer/proxy chưa tương thích không?
- `maxIdleTimeMS` quá thấp?
- MongoClient được tạo mới cho mỗi request?
- Network idle timeout hay firewall reset?

### Biện pháp

Phân tích theo timeline, sửa network/TLS/lifecycle, dùng rolling rollout. Một pool clear đơn lẻ khi election **không** đồng nghĩa sự cố.

## 43. Runbook 4 — Command latency tăng nhưng pool checkout vẫn nhanh

### Dấu hiệu

```text
checkout p99 = 3 ms
find command p99 = 2.5 s
serverSelection stable
```

### Điều tra

1. Phân nhóm theo command name/query shape qua logs an toàn.
2. Xem `explain("executionStats")` trên query đại diện.
3. Kiểm tra `totalDocsExamined`, `totalKeysExamined`, `COLLSCAN`.
4. Đo server disk/CPU/cache/network/locks.
5. Tìm recent index changes, large documents, N+1 calls.
6. Kiểm tra command duration có tăng ở tất cả services hay chỉ một endpoint.

### Biện pháp

Tối ưu filter/index/projection/pagination, giảm query fan-out hoặc tăng capacity theo bằng chứng. **Tăng pool size không sửa query plan xấu.**

## 44. Runbook 5 — Duplicate key tăng sau failover

### Dấu hiệu

```text
Election occurred
Driver command retries increased
API POST /orders duplicated
MongoWriteException code=11000
```

### Điều tra

- Duplicates có cùng business requestId?
- Backend có tạo ID mới khi HTTP request retry?
- Có unique index bảo vệ scope?
- Có duplicate webhook/payment side effect?
- Có thể truy vấn trạng thái request cũ không?

### Phản ứng

1. Đóng lỗ hổng retry thiếu idempotency.
2. Reconcile orders/payments/inventory affected.
3. Phân biệt duplicate hợp lệ với dữ liệu sai.
4. Không xóa dữ liệu trùng tự động trước khi đánh giá business impact.
5. Bổ sung tests cho response lost after server commit.

## 45. Runbook 6 — Auth hoặc TLS failure

### Dấu hiệu

```text
MongoSecurityException
MongoCommandException code 18
MongoCommandException code 13
TLS handshake failure / certificate verify failed
```

### Điều tra

- Secret rotation có hoàn tất ở mọi service instances?
- `authSource`, username và mechanism có khớp?
- User có đúng role trên database/collection?
- Certificate CA trust và SAN/hostname có đúng?
- Clock lệch khiến cert không hợp lệ?
- Network policies/private endpoints có đổi?

### Hành động

Sửa credentials/permissions/certs theo chính sách bảo mật, rotate secret lộ nếu cần. Không tăng role thành `root` hoặc tắt TLS verification để “tạm chạy”.

## 46. Runbook 7 — Unknown transaction commit result

### Dấu hiệu

`MongoException.hasErrorLabel("UnknownTransactionCommitResult") == true` khi commit.

### Điều tra

- Driver/core transaction API hay callback API?
- Transaction đã gửi commit chưa?
- Có thể query trạng thái theo business operation ID?
- Error có trùng election/network outage?
- Có external side effects trong callback?

### Phản ứng

Theo protocol driver: retry **commit** khi thích hợp; nếu hết deadline vẫn unknown, ghi nhận trạng thái chờ reconciliation thay vì trả success giả hoặc tự chạy lại toàn nghiệp vụ.

### Điều không nên làm

Không gửi lại payment/notification mà không có idempotency; không drop collections/khởi động transaction mới chỉ vì commit reply mất.

## 47. Runbook 8 — Người dùng báo API chậm nhưng MongoDB commands nhanh

### Dấu hiệu

```text
HTTP p95 = 2s
Command p95 = 15ms
Pool checkout p95 = 1ms
SDAM stable
```

### Điều tra

- Application serialization/deserialization.
- HTTP connection/thread pool.
- GC pauses, CPU starvation.
- Downstream HTTP service.
- Lock trong business code.
- N+1: nhiều commands nhanh cộng thành request chậm.
- Transaction/cursor iteration nhiều `getMore`.
- Server selection chờ trước command chưa được instrument.

Đừng quy mọi API latency cho MongoDB chỉ vì MongoDB là database chính.

## 48. Sử dụng OpenTelemetry/Micrometer có kiểm soát

### 48.1. Khi dùng Spring Boot

Một ứng dụng có thể tích hợp:

- Spring Boot Actuator/Micrometer cho request latency và counters.
- OpenTelemetry cho traces.
- JMX pool monitoring hoặc CMAP metrics adapter.
- Command listeners hoặc official instrumentation cho MongoDB spans.

Không tự động bật nhiều instrumentation overlapping mà không kiểm tra **duplicate spans/metrics** và sample overhead.

### 48.2. Ví dụ Micrometer histogram

Đoạn code minh họa nếu dự án có `micrometer-core`:

```java
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandSucceededEvent;
import com.mongodb.event.CommandFailedEvent;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.Set;
import java.util.concurrent.TimeUnit;

public final class CommandTimer394 implements CommandListener {
    private static final Set<String> ALLOWED =
        Set.of("find", "insert", "update",
               "delete", "aggregate", "getMore");

    private final MeterRegistry registry;

    public CommandTimer394(MeterRegistry registry) {
        this.registry = registry;
    }

    private String commandLabel(String name) {
        return ALLOWED.contains(name) ? name : "other";
    }

    private void record(String command, String outcome, long nanos) {
        Timer.builder("mongodb.client.command.duration")
            .tags("command", commandLabel(command),
                  "outcome", outcome)
            .register(registry)
            .record(nanos, TimeUnit.NANOSECONDS);
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        record(event.getCommandName(), "success",
               event.getElapsedTime(TimeUnit.NANOSECONDS));
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        record(event.getCommandName(), "failure",
               event.getElapsedTime(TimeUnit.NANOSECONDS));
    }
}
```

### 48.3. Tại sao có allowlist?

Tên command đa số có danh sách hữu hạn, nhưng policy allowlist vẫn giúp tránh tích hợp nhãn không kiểm soát khi thêm commands custom. Không dùng raw query hoặc collection do user tạo làm tag.

### 48.4. Cần tránh synchronous exporter

Recording metrics vào registry thường rẻ hơn gọi HTTP đồng bộ trong callback. Export metrics định kỳ bằng exporter/agent thay vì gửi tới Prometheus trong mỗi command.

## 49. Test plan observability trên môi trường lab

### 49.1. Mục tiêu đo

- Listener đã được đăng ký đúng.
- SDAM thay đổi được ghi nhận.
- Pool checkout duration/failures phản ánh hiện trạng.
- Command events và durations có đơn vị chuẩn.
- Exception classification đưa ra quyết định an toàn.
- Không rò PII/secret trong logs/metrics.

### 49.2. Kiểm thử cơ bản không phá dữ liệu

1. Khởi động service với connection string lab đúng.
2. Gọi `ping`, `find` trên collection test.
3. Xác minh `CommandSucceededEvent`, checkout/checkin và writable view.
4. Xác minh histogram có samples và không ném lỗi callback.
5. Đóng MongoClient, kiểm tra pool lifecycle events phù hợp.

### 49.3. Kiểm thử lỗi trên lab được phép

- URI sai hostname: quan sát server selection/connection failure.
- Wrong credentials lab: xác thực bị từ chối.
- Missing role lab: lỗi authorization.
- Duplicate unique key: lỗi 11000.
- Slow query trên dataset giả: quan sát duration/`maxTimeMS`.
- Staged failover lab: SDAM change/pool clear/retry.
- Load test bounded: pool checkout queue và latency.

**Không dùng lỗi cố tình trên production** để chứng minh hệ thống có monitoring.

### 49.4. Kỳ vọng là tương quan, không phải exact event count

Không viết test mong chờ mỗi `find` phát chính xác một heartbeat hoặc một connectionCreated. Driver sử dụng pool và background monitoring, nên số events có thể thay đổi tùy connection reuse và timing.

### 49.5. Data protection test

Gửi tài liệu giả chứa chuỗi `fake-secret-394` trong lab, xác nhận:

- Không xuất hiện trong metrics labels.
- Không xuất hiện ở application logs thường dùng.
- CommandListener không log raw BSON.
- Exporter và tracing không giữ payload.

## 50. Sharded cluster và load-balanced deployment

### 50.1. Sharded cluster

Thông thường Java driver kết nối tới `mongos` routers, không chọn trực tiếp primary từng shard như replica set URI riêng.

```text
Java MongoClient
   |
   +-- Pool mongos-a
   +-- Pool mongos-b
   |
   +-- Routes to shards via mongos
```

Theo dõi:

- Server selection của `mongos`.
- Pool checkout/connection errors theo router.
- Command duration của query xuyên shards.
- Metrics/alerts của shard replica sets ở cấp cluster/server nếu cần.

### 50.2. Load-balanced mode

Khi dùng deployment/load balancing được hỗ trợ, SDAM heartbeat event semantics khác replica set thông thường, và có thể **không có heartbeat events**.

Không dựa vào “heartbeat count = 0” để kết luận database unreachable; monitor pool/commands/application probes và load balancer metrics.

### 50.3. Atlas

Atlas cung cấp cluster metrics và events; driver vẫn cần client-side SDAM/CMAP/command monitoring vì Atlas không thấy **thời gian request chờ checkout trong Java process**.

### 50.4. Self-managed

Ngoài driver events, vận hành cần `serverStatus`, replica set monitoring, network/disk logs, slow queries và host metrics. Một tầng không thay tầng khác.

## 51. Security và các giới hạn observability

### 51.1. Những field nên tránh

- Connection string chứa username/password.
- Raw commands/filter/update documents.
- Full `Throwable.toString()` khi có request literal.
- Raw userId/email/phone.
- Session credentials, private keys, JWTs.
- Unbounded request IDs làm metric labels.

### 51.2. Mức truy cập

| Người xem | Dữ liệu phù hợp |
|---|---|
 Developer | Aggregated latency/errors và sanitized logs |
 On-call SRE | Topology/pool/command metrics, safe host labels |
 DBA | Server-side status, query plans, cluster alerts |
 Security | Audit/access anomalies, redaction checks |
 Break-glass | Chi tiết sâu hơn theo phê duyệt/thời hạn |

### 51.3. Driver event là data plane metadata

Hostnames, database names, query shapes và exception reasons có thể tiết lộ hạ tầng; cần TLS, RBAC, retention và centralized logging như mọi operational data.

### 51.4. Instrumentation overhead

Lượng command events có thể rất cao:

```text
10.000 commands/sec
-> nếu log 1 KB/command
-> khoảng 10 MB/sec logs (ước lượng thô)
```

Không bật verbose per-command logs vô hạn. Dùng counters/histograms/sampling và điều tra theo time window.

## 52. Những anti-pattern thường gặp

| Anti-pattern | Vấn đề | Cách thay |
|---|---|---|
| Tạo `MongoClient` mỗi HTTP request | Nhiều pools/handshakes | Managed singleton |
| Coi `MongoTimeoutException` luôn do pool | Có thể server selection | Xem SDAM vs CMAP |
| Coi `CommandSucceededEvent` là request duration | Bỏ selection/checkout/app time | End-to-end tracing |
| Dùng `ping` để nói mọi writes sẽ thành công | Không kiểm tra business/majority | Proper readiness/write probe |
| Log `event.getCommand()` | Có PII/secret | Metadata allowlist |
| Cho listener gọi HTTP đồng bộ | Block driver threads | Async/bounded exporter |
| Gửi full exception message làm metric label | Cardinality/rò info | Error family/code/label |
| Lấy awaited heartbeat elapsed làm RTT | Kết luận mạng chậm sai | Xem `isAwaited()` |
| Coi không có heartbeat là outage ở LB mode | False alarm | Mode-aware monitoring |
| Đếm mọi command như một HTTP request | Cursor/getMore/transaction có nhiều command | Trace/correlation |
| Coi `maxPoolSize` là toàn cluster | Mỗi server có pool | Capacity toàn fleet |
| Tăng maxPool khi query chậm | Server càng tải | Explain/index và sizing |
| Tăng `maxConnecting` vô hạn | Handshake storm | Benchmark |
| Coi pool cleared là connection leak | Có thể do failover | Correlate SDAM/network |
| Coi checkout failure reason TIMEOUT là server down | Có thể pool bận | Pool in-use/wait |
| Chỉnh timeout mà không có request deadline | Queue/backlog | CSOT + budgets |
| Retry mọi `MongoException` | Infinite retries/sai nghiệp vụ | Labels + operation semantics |
| Coi `UnknownTransactionCommitResult` là chưa commit | Double side effects | Retry commit/reconcile |
| Dùng `RetryableWriteError` cho HTTP POST bất kỳ | Duplicate orders | Idempotency key |
| Coi write concern timeout là write chưa chạy | Có thể đã apply | Reconcile |
| Bắt `MongoException` trước subclasses | Mất phân loại | Catch specialized first |
| Tắt TLS validation sau failover | Security risk | Fix CA/SAN/DNS |
| Không test missing telemetry | Silent blind spots | Alert no data |
| Chỉ xem driver, không xem server | Thiếu root cause | Merge Atlas/server metrics |
| Chỉ xem server, không xem driver | Không biết pool/selection wait | Client instrumentation |
| Force primary change để tạo test production | Ảnh hưởng availability | Controlled staging drill |

## 53. Bài tập thực hành

### Bài 1 — Bốn lớp chẩn đoán

Một HTTP request mất 3 giây, command duration chỉ 5 ms. Những bước nào ngoài command có thể chiếm thời gian? Nêu metrics cho từng bước.

### Bài 2 — Topology listener

Viết `ClusterListener` đặt gauge 1 nếu có writable server, 0 nếu không. Vì sao gauge này không chứng minh majority write chắc chắn thành công?

### Bài 3 — Server listener

Viết `ServerListener` ghi sự thay đổi từ `REPLICA_SET_PRIMARY` sang `REPLICA_SET_SECONDARY` bằng metadata an toàn.

### Bài 4 — Heartbeat

`ServerHeartbeatSucceededEvent.getElapsedTime()` trả 10 giây và `isAwaited()` là true. Có nên báo network RTT 10 giây không? Giải thích.

### Bài 5 — Load-balanced mode

Một service dùng load-balanced mode không có heartbeat events nhưng commands vẫn thành công. Đây có phải lỗi instrumentation không?

### Bài 6 — Pool lifecycle

Vẽ vòng đời `ConnectionPoolOpened` → `ConnectionCreated` → `ConnectionReady` → `ConnectionCheckedOut` → `ConnectionCheckedIn` → `ConnectionClosed`. Vì sao không luôn có created event cho mỗi checkout?

### Bài 7 — CMAP failures

Thiết kế metrics `connectionCheckOutFailed` theo reason và histogram checkout duration. Khi nào gọi incident pool exhaustion?

### Bài 8 — Pool sizing

Có 40 application instances, mỗi instance một MongoClient, maxPoolSize=100 trên một primary. Tính trần lý thuyết pooled connections tới primary và nêu các yếu tố làm thực tế khác.

### Bài 9 — maxConnecting

Sau rollout, `connectionCreated` tăng chậm, request queue dài, pool chưa đạt max size. Vai trò của `maxConnecting` là gì và cần benchmark gì?

### Bài 10 — Connection leak

Pool active tăng, command latency không tăng, có nhiều transaction mở lâu. Nêu các giả thuyết và cách điều tra mà không tăng max pool ngay.

### Bài 11 — CommandListener

Viết listener đếm `find`/`aggregate`/`update` thành công và thất bại theo command name, không ghi raw BSON payload.

### Bài 12 — Cursor

Một API đọc 20.000 documents theo cursor với nhiều `getMore`. Vì sao có nhiều command events nhưng chỉ một HTTP request?

### Bài 13 — Metrics labels

Cho labels gồm commandName, databaseName, requestId, tenantId, exceptionMessage. Field nào nguy hiểm cho Prometheus cardinality? Thiết kế bộ labels thay thế.

### Bài 14 — Server selection timeout

Replica set đã có primary mới, nhưng Java báo không chọn được server. Hãy kiểm tra `ClusterDescription`, DNS, replicaSet name, TLS và URI.

### Bài 15 — Checkout timeout

Topology stable, command p95 20 ms, checkout p99 2 giây. Nêu ba nguyên nhân và cách phân biệt.

### Bài 16 — Socket exception

Client gửi update rồi nhận connection reset. Có được khẳng định update chưa xảy ra không? Thiết kế reconciliation theo operation ID.

### Bài 17 — Error code 11000

Một retry HTTP POST tạo duplicate order, driver trả 11000. Vì sao không tự map thành HTTP 500? Cần so sánh những thông tin nghiệp vụ nào?

### Bài 18 — AuthN vs AuthZ

Phân biệt mã 18 và 13. Nếu Java service thiếu quyền trên collection mới, nên sửa gì và không nên sửa gì?

### Bài 19 — Error labels

So sánh `TransientTransactionError` và `UnknownTransactionCommitResult` về hành động retry transaction body/commit.

### Bài 20 — Retry budget

Một service retry mọi command 20 lần ngay lập tức khi primary mất. Rủi ro gì xảy ra với primary mới? Thiết kế bounded retries/backoff/jitter.

### Bài 21 — Bulk write

Một batch 1.000 inserts có 20 duplicate keys. So sánh ordered/unordered; vì sao không phát lại cả batch mà không kiểm tra kết quả?

### Bài 22 — Micrometer

Tạo histogram command duration theo commandName allowlist và outcome. Vì sao `orderId` không được làm tag?

### Bài 23 — Tracing

HTTP request 500 ms, MongoDB command total 60 ms. Hãy lập một trace giả có các spans khác và đưa ra cách kiểm chứng latency còn lại.

### Bài 24 — Pool clear

Sau election, `poolCleared` tăng một lần rồi trở về bình thường. Trường hợp nào là recovery bình thường? Khi nào cần alert?

### Bài 25 — Spring Boot readiness

Tất cả pods restart vì MongoDB primary mất trong vài giây. Thiết kế lại liveness/readiness để tránh restart storm và vẫn không trả success giả khi writes chưa được xác nhận.

### Bài 26 — Driver observability security

Một `CommandListener` đang log `event.getCommand().toJson()`, chứa email/password reset token. Đề xuất sửa code, xử lý dữ liệu log đã tồn tại và kiểm thử regression.

### Bài 27 — Staging failover drill

Thiết kế bài test dùng replica set lab, thu baseline, thực hiện planned stepdown có phép, quan sát SDAM/pool/command events và xác minh API tự phục hồi.

### Bài 28 — Scenario tổng hợp

Cho timeline:

```text
10:00:00 primary A steps down
10:00:01 SDAM no writable server
10:00:01 pool A cleared
10:00:04 new primary B discovered
10:00:05 pool checkout p99 500ms
10:00:06 command p99 25ms
10:00:07 API errors back to baseline
```

Hãy phân biệt election time, driver recovery time, pool warm-up time và user-visible impact.

### Bài 29 — Error classifier

Thiết kế bảng decision cho `MongoTimeoutException`, `MongoSocketException`, `MongoWriteException`, `MongoWriteConcernException`, `MongoCommandException` và các transaction labels. Gắn hành động fail-fast/retry/reconcile.

### Bài 30 — Observability design hoàn chỉnh

Viết thiết kế cho Java service có 100 pods và MongoDB Atlas replica set:

1. Một MongoClient/pod.
2. Listener SDAM/CMAP/commands và metrics.
3. Timeout/retry budgets.
4. App idempotency cho checkout.
5. Log redaction/PII controls.
6. Prometheus histograms/alerts.
7. Runbooks cho failover, pool exhaustion, auth/TLS, duplicate key.
8. Staging test plan và bằng chứng pass/fail.

## 54. Checklist triển khai trước production

### 54.1. MongoClient và SDAM

1. Driver Java version tương thích với MongoDB deployment.
2. Một `MongoClient` sống lâu theo process/DI container.
3. Replica set/SRV URI phù hợp, không khóa một primary.
4. DNS/TLS/SAN/authSource được kiểm tra từ app environment.
5. Cluster/server/heartbeat monitoring có visibility.
6. Không alert sai vì load-balanced mode không phát heartbeat.
7. Server selection timeout được phối hợp với request deadline.

### 54.2. Pool

1. Pool size và maxConnecting được benchmark với toàn fleet.
2. Có checkout duration histogram và failure counter theo reason.
3. Có visibility của connection created/closed/cleared.
4. Có theo dõi active/idle/waiting connections qua JMX hoặc instrumentation.
5. Cursor/transaction lifecycle đóng đúng.
6. Không có MongoClient per request.
7. Có backpressure và tránh retry/connection storm.

### 54.3. Commands và exceptions

1. Command latency đo theo operation type/outcome.
2. Không log raw BSON commands hoặc credentials.
3. Các exception được phân loại theo type/code/label.
4. Retryable reads/writes sử dụng theo semantics của driver.
5. Có business idempotency và reconciliation cho unknown outcomes.
6. Transaction labels được xử lý đúng body vs commit.
7. Bulk write errors có logic partial success.

### 54.4. Metrics và vận hành

1. Có SLO p95/p99 cho API và database steps.
2. Có alert no writable server, pool timeout, command failures.
3. Có dashboards gộp SDAM + CMAP + command + server metrics.
4. Không dùng unbounded/PII labels.
5. Monitoring pipeline failures có alert.
6. Có staging failover test và incident runbooks.
7. Có người chịu trách nhiệm điều tra, rollback và tối ưu.

## 55. Tổng kết

**Java MongoDB Driver có nhiều tầng hoạt động mà một exception message không thể mô tả đầy đủ.** SDAM quyết định server nào có thể nhận lệnh; CMAP quản lý connection pool; command monitoring quan sát lệnh đã được gửi; exception type, error code và error labels giúp xác định việc tiếp tục, retry hay cần đối chiếu trạng thái.

**Phân biệt đúng nơi chờ là bước tối ưu đầu tiên.** Không chọn được primary không phải pool exhaustion; pool checkout chậm không phải server query chậm; `CommandSucceededEvent` không phản ánh toàn bộ độ trễ HTTP request; awaited heartbeat elapsed không đồng nghĩa network RTT.

**Listener phải nhẹ và an toàn.** Đăng ký `ClusterListener`, `ServerListener`, `ServerMonitorListener`, `ConnectionPoolListener` và `CommandListener` trong `MongoClientSettings`; dùng counters/histograms với labels giới hạn, không log raw commands hoặc secrets, không làm I/O đồng bộ nặng trong callbacks.

**Phân loại lỗi là quyết định nghiệp vụ có ràng buộc.** `MongoTimeoutException`, `MongoSocketException`, `MongoWriteException`, `MongoWriteConcernException` và `MongoCommandException` cung cấp những tín hiệu khác nhau. Labels `TransientTransactionError` và `UnknownTransactionCommitResult` quy định cách retry transaction body hoặc commit; chúng không thay được idempotency của HTTP checkout/payment workflows.

**Khả năng phục hồi phải đo từ người dùng tới database.** Dashboard tốt kết hợp topology availability, pool wait/checkout failures, command duration/error rate, HTTP request SLO và server metrics. Khi có failover, đích không chỉ là “đã có primary mới” mà là **ứng dụng chọn được server, pool ổn định, nghiệp vụ không nhân đôi và người dùng nhận kết quả đúng**.

## 56. Tài liệu tham khảo

- [MongoDB Java Sync Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/): SDAM, command và connection pool listeners.
- [MongoDB Java Sync Driver — Logging](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/logging/): logging và bảo vệ dữ liệu.
- [MongoDB Java Sync Driver — Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/): maxPoolSize, maxConnecting, timeout và JMX.
- [MongoDB Java Sync Driver — Cluster Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/cluster-settings/): server selection và ClusterListener.
- [MongoDB Java Sync Driver — Server Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/server-settings/): ServerListener, heartbeat và monitoring mode.
- [MongoDB Java Sync Driver — Connection Troubleshooting](https://www.mongodb.com/docs/drivers/java/sync/current/connection/connection-troubleshooting/): network, authentication, timeout và topology.
- [MongoDB Java Sync Driver — Limit Execution Time](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/limit-execution-time/): Client-Side Operation Timeout và timeout settings.
- [MongoDB Java Driver API — com.mongodb.event](https://mongodb.github.io/mongo-java-driver/5.6/apidocs/driver-core/com/mongodb/event/package-summary.html): listener và event APIs.
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): retryable-write protocol và giới hạn.
- [MongoDB Manual — Retryable Reads](https://www.mongodb.com/docs/manual/core/retryable-reads/): read operation retry.
- [MongoDB Manual — Transactions in Applications](https://www.mongodb.com/docs/manual/core/transactions-in-applications/): `TransientTransactionError` và `UnknownTransactionCommitResult`.
- [MongoDB Manual — Server Discovery and Monitoring](https://github.com/mongodb/specifications/blob/master/source/server-discovery-and-monitoring/server-discovery-and-monitoring.md): SDAM behavior và driver semantics.
- [MongoDB Driver Specifications — Connection Monitoring and Pooling](https://github.com/mongodb/specifications/blob/master/source/connection-monitoring-and-pooling/connection-monitoring-and-pooling.md): CMAP events, checkout và pool lifecycle.
- [MongoDB Driver Specifications — Command Logging and Monitoring](https://github.com/mongodb/specifications/blob/master/source/command-logging-and-monitoring/command-logging-and-monitoring.md): command event fields và redaction.

