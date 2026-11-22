# Connection pool, server selection và các loại timeout

Một ứng dụng Java dùng MongoDB đôi khi gặp thông báo:

~~~text
com.mongodb.MongoTimeoutException:
Timed out after 30000 ms while waiting for a server
that matches ReadPreferenceServerSelector{readPreference=primary}
~~~

Phản ứng vội vàng thường là tăng `maxPoolSize` vì nghĩ “driver hết connection”. Nhưng lỗi trên nói rằng **driver không chọn được server phù hợp** (ví dụ chưa tìm thấy primary), không nhất thiết do pool đầy. Ngược lại, một request có thể chọn được primary nhưng **không lấy được connection từ pool**; hoặc lấy được connection rồi **query chạy lâu**; hoặc socket **không mở được** do mạng. Các tình huống cần chẩn đoán và cấu hình khác nhau.

Bài **“Connection pool, server selection và các loại timeout”** thuộc chương **Java Driver**, module *Database Engine Document MongoDB*, giải thích một cách có hệ thống cách **MongoDB Java Sync Driver** quản lý kết nối, khám phá topology, chọn server và áp dụng các timeout. Trọng tâm là **hiểu cơ chế, API Java, lỗi thực tế, phép đo và quy trình tối ưu** thay vì thử tăng các con số một cách ngẫu nhiên.

## Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích vòng đời của một `MongoClient` và lý do tái sử dụng client.
2. Phân biệt **per-server connection pool**, server monitoring sockets và số TCP connections thực tế.
3. Phân biệt SDAM/topology discovery với pool checkout và server command execution.
4. Giải thích cách driver chọn **primary, secondary, nearest**, read preference, latency window và server selection timeout.
5. Thiết lập các options `maxPoolSize`, `minPoolSize`, `maxConnecting`, `maxIdleTimeMS`, `maxLifeTimeMS`, `waitQueueTimeoutMS`.
6. Phân biệt `serverSelectionTimeoutMS`, `connectTimeoutMS`, `socketTimeoutMS`, `maxTimeMS`, `waitQueueTimeoutMS`, `timeoutMS` (CSOT).
7. Sử dụng Java Sync Driver configuration qua URI và `MongoClientSettings`, hiểu precedence của options.
8. Đặt deadline cho service, xử lý timeout/failover/retries mà không nhân đôi dữ liệu.
9. Dùng CMAP, SDAM, command monitoring và JMX để chẩn đoán nơi request chờ.
10. Thực hiện bài tập về sizing, timeout budget, server selection và kiểm chứng sự cố.

> **Phiên bản:** Ví dụ chủ yếu nhắm **MongoDB Java Sync Driver 5.x**. Một số API (đặc biệt `timeout()`/CSOT, timeout mode cho cursor, transaction timeout) là mới hoặc có semantics khác ở 4.x. Tài liệu MongoDB Java Driver hiện hành vẫn đánh dấu **CSOT là experimental**. Đối chiếu tài liệu của phiên bản driver thực đang chạy, không gộp mặc định của Java 5.x với driver khác. Các số latency/pool size trong ví dụ chỉ để minh họa.

## 1. Bản đồ đường đi của một MongoDB operation

~~~text
Ứng dụng Java gọi collection.find(...).first()
                   |
                   v
          Xây command + deadline
                   |
                   v
       Chọn server theo topology/read preference
       [SDAM + server selection]
                   |
                   v
      Checkout connection từ pool của server đó
      [CMAP: idle / create / wait / timeout]
                   |
                   v
        Gửi command qua network socket
                   |
                   v
           mongod / mongos thực thi
        [query plan, locks, CPU, I/O]
                   |
                   v
         Nhận response / cursor batch
                   |
                   v
     Trả connection cho pool theo lifecycle
                   |
                   v
       Trả Java result / phát sinh exception
~~~

Đừng hiểu sơ đồ này là *luôn* có đúng một lần checkout cho toàn bộ API: một cursor có nhiều `getMore`; một operation có thể retry; transaction có đặc điểm **connection pinning**; load-balanced topology có xử lý riêng. Đây là khung để phân biệt **nơi chờ và loại lỗi**.

### 1.1. Năm thời điểm khác nhau

| Giai đoạn | Công việc | Nếu chậm hoặc lỗi |
|---|---|---|
| **Server discovery** | Monitor xác định server nào là primary/secondary/mongos, tình trạng và latency. | SDAM/topology issue. |
| **Server selection** | Chọn server phù hợp với read preference, tags, freshness, latency. | `serverSelectionTimeoutMS` hoặc CSOT. |
| **Connection checkout** | Mượn pooled connection hoặc chờ một socket mới/được trả về. | `waitQueueTimeoutMS` legacy hoặc CSOT. |
| **Socket/command** | TCP/TLS/auth, gửi và nhận BSON command, server thực thi. | `connectTimeoutMS`, `socketTimeoutMS`, `maxTimeMS`, CSOT, network/server error. |
| **Result lifecycle** | Consume cursor, `getMore`, release resource, transaction commit/abort. | Cursor/transaction timeout, cancellation/cleanup. |

Thời gian người dùng trải nghiệm là **tổng các chặng và chi phí ứng dụng**:

\[
T_{\mathrm{HTTP}}
=T_{\mathrm{queue/app}}
+T_{\mathrm{selection}}
+T_{\mathrm{checkout}}
+T_{\mathrm{network/server}}
+T_{\mathrm{processing}}
\]

Giới hạn một thành phần không tự giới hạn tổng. Ví dụ `maxTimeMS=200` không ngăn request chờ 2 giây để checkout connection trước khi server bắt đầu chạy.

### 1.2. Ba khái niệm dễ bị trộn

- **Server:** một `mongod`/`mongos` thực tế mà driver có thể gửi operation đến.
- **Connection:** một kênh TCP/TLS đã được mở, xác thực và có thể tái sử dụng.
- **Operation:** một hành động như `find`, `aggregate`, `insertOne`, `getMore`, `commitTransaction`; một request HTTP có thể thực hiện nhiều operations.

Tăng số connections **không** tạo thêm primary, không làm index hiệu quả hơn và không tăng CPU/IOPS của MongoDB. Nó chỉ thay đổi khả năng **truyền nhiều operations đồng thời** qua những connections đó, tới ngưỡng server có thể xử lý.

## 2. `MongoClient`: một đối tượng, nhiều pools, nhiều monitors

### 2.1. MongoClient là đối tượng đắt, thread-safe

`MongoClient` quản lý topology discovery, pool, socket/TLS setup, credentials, session/retry behavior và monitoring. Java Sync Driver thiết kế client dùng được từ **nhiều threads**, vì vậy nên tạo **một MongoClient sống suốt vòng đời ứng dụng** cho một kết nối/workload phù hợp.

**Không nên:**

~~~java
// ANTI-PATTERN: tạo/đóng MongoClient cho từng request.
Document getUserBad(String id, String uri) {
    try (MongoClient mongoClient = MongoClients.create(uri)) {
        return mongoClient
            .getDatabase("sample")
            .getCollection("users")
            .find(Filters.eq("_id", id))
            .first();
    }
}
~~~

Mỗi request lại kích hoạt topology discovery và tạo/đóng pools, tăng TLS/auth handshakes, CPU, số sockets và connection churn.

**Nên:**

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public final class UserRepository implements AutoCloseable {
    private final MongoClient client;
    private final MongoCollection<Document> users;

    public UserRepository(String uri) {
        this.client = MongoClients.create(uri);
        this.users = client.getDatabase("sample")
            .getCollection("users");
    }

    public Document getById(String id) {
        return users.find(Filters.eq("_id", id)).first();
    }

    @Override
    public void close() {
        client.close();
    }
}
~~~

Application tạo `UserRepository` một lần hoặc dùng DI để quản lý MongoClient bean. Nếu Spring Boot đã tạo một MongoClient tự động, không vô tình tạo thêm client trong mỗi repository.

### 2.2. MongoClient có **pool riêng cho mỗi server**

~~~text
              1 MongoClient
                    |
       +------------+------------+
       |            |            |
       v            v            v
   Primary P    Secondary A  Secondary B
    Pool P        Pool A       Pool B
   max=100        max=100      max=100
~~~

`maxPoolSize=100` nghĩa tối đa **100 pooled application connections cho mỗi server**, không phải một ngân sách chung 100 cho cả replica set. Driver cũng duy trì **monitoring sockets** cho server state (Java Driver docs mô tả thêm **hai sockets/server**), ngoài trần pooled connections.

Default read preference là `primary` nên trong nhiều service các pools thứ cấp không mở nhiều application sockets; **trần cấu hình không bằng số connections thực đang mở**.

### 2.3. Hai `mongos` cũng có hai pools

Nếu driver kết nối tới 2 routers `mongos-1` và `mongos-2`, mỗi router có pool riêng theo MongoClient. Với `maxPoolSize=50`, một client có thể mở tối đa 50 pooled connections tới **mỗi router**, không phải 50 cộng lại.

MongoDB driver chọn router theo topology/latency. Router còn routing tới shards; app pool lớn không giải quyết shard key hotspot hoặc aggregation chậm.

### 2.4. Công thức budget khi scale ứng dụng

Giả sử có 15 pods, mỗi pod 1 MongoClient, `maxPoolSize=80`, mọi traffic write đến cùng primary:

\[
\text{Potential pooled connections tới primary}
=15\times1\times80=1200
\]

Đây là trần **potential**, không phải current. Nếu mỗi pod vô tình có 3 MongoClients, trần thành `15×3×80=3.600`. Cộng monitoring sockets và client từ các dịch vụ khác trước khi kết luận DB đủ connection capacity.

### 2.5. Connection state và pool lifecycle

Một socket có thể:

1. **Connecting:** đang mở TCP/TLS/handshake và authenticate.
2. **Ready & idle:** sẵn sàng checkout.
3. **Checked out:** được operation sử dụng.
4. **Checked in:** được trả về để tái sử dụng.
5. **Closed:** do idle/lifetime, network error hoặc pool clear.

**Checked-out count** khác **pool size** và khác `serverStatus.connections.current`. Server có thể thấy 1.000 incoming connections nhưng chỉ một phần nhỏ đang chạy operations.

### 2.6. Kết nối tới một host bằng `directConnection=true`

`directConnection=true` yêu cầu driver dùng chế độ single-server connection thay vì khám phá replica set topology qua host đó. Hữu ích cho trường hợp quản trị/lab có host cụ thể, nhưng **không** phải cách dùng mặc định để “bỏ qua election” cho ứng dụng HA: client sẽ không tự chuyển sang primary mới theo cách replica-set connection bình thường.

Trong ứng dụng production cần HA, cấu hình seed list/replica set hoặc Atlas SRV URI phù hợp thay vì ép kết nối trực tiếp một member.

## 3. Connection pool: cấu hình và mặc định theo Java Sync Driver

Tài liệu **Java Sync Driver hiện hành** nêu các default dưới đây (phiên bản cụ thể cần xác minh):

| URI option | Java builder tương ứng | Default Java Driver 5.x | Vai trò |
|---|---|---|---|
| `maxPoolSize` | `maxSize(int)` | 100 | Trần số application pooled connections **mỗi server**. |
| `minPoolSize` | `minSize(int)` | 0 | Mức tối thiểu driver cố duy trì trong pool theo lifecycle. |
| `maxConnecting` | `maxConnecting(int)` | 2 | Tối đa sockets đang **establish đồng thời** trên pool. |
| `maxIdleTimeMS` | `maxConnectionIdleTime(long, TimeUnit)` | 0 | Thời gian idle tối đa; 0 = không giới hạn bởi option này. |
| `maxLifeTimeMS` | `maxConnectionLifeTime(long, TimeUnit)` | 0 | Lifetime connection tối đa; 0 = không giới hạn bởi option này. |
| `waitQueueTimeoutMS` | `maxWaitTime(long, TimeUnit)` | 120.000 ms | Chờ lấy connection; deprecated khi dùng CSOT. |

**Mọi thông số phải được hiểu trong phạm vi pool theo server**. Tăng một giá trị lên 10 lần có thể làm số connections tiềm năng tăng 10 lần trên **mỗi primary/secondary/mongos** mà client sử dụng.

### 3.1. `maxPoolSize` không đồng nghĩa “số operations chạy thực”

Nếu pool 100 connections nhưng 95 idle, không có 100 commands chạy đồng thời. Nếu pool 100 checked-out, vẫn chưa chắc tất cả đang tiêu thụ CPU liên tục; một số chờ network, storage hoặc transaction. Điều đáng đo là:

- `checkedOutCount` và checkout wait p95/p99.
- Command execution p95/p99 theo loại query.
- Server CPU/IOPS/cache/locks và active operations.
- HTTP in-flight/queue depth và error rate.

### 3.2. `minPoolSize` và cold start

`minPoolSize=20` có thể giữ một số sockets warm, giảm latency sau idle; nhưng nhiều pods cùng startup có thể tạo **connection storm**. Nó cũng **không đảm bảo pool tức khắc có 20 sockets ngay sau constructor**; cần chờ connection establishment và driver maintenance. Không dùng minPoolSize lớn như một công cụ thay application readiness/warmup.

### 3.3. `maxConnecting`: điểm nghẽn trước khi đạt max size

Pool `maxPoolSize=100`, `maxConnecting=2` và đang có 0 connection ready:

~~~text
100 requests cùng tới
         |
         v
Pool có thể tạo rất ít connections cùng lúc
     [maxConnecting = 2]
         |
         +---- các requests khác chờ checkout
         |
         v
Connections ready dần rồi checkout
~~~

Thấy checkout wait sau deploy không nhất thiết do đã **chạm maxPoolSize**; có thể do **pool chưa warm** và bị giới hạn tốc độ establishment. Tăng `maxConnecting` có thể giảm ramp-up nhưng tăng TLS/auth/CPU load; đo cẩn thận.

### 3.4. `maxIdleTimeMS` và `maxLifeTimeMS`

`maxIdleTimeMS` loại sockets idle quá lâu, hữu ích khi firewall/NAT đóng idle connections trước driver. `maxLifeTimeMS` recycle sockets sau tuổi thọ tối đa. Đặt quá thấp có thể tạo churn/handshake; đặt quá cao có thể giữ socket stale qua network devices.

Đừng giải thích `maxLifeTimeMS` là timeout “một query không được chạy quá N ms”: đây là **connection lifecycle setting**, không phải operation deadline.

### 3.5. `waitQueueTimeoutMS` không đặt queue size cap

Nếu pool có 10 connections và 1000 Java threads cùng checkout, `waitQueueTimeoutMS=5.000` chỉ giới hạn **thời gian chờ** theo legacy semantics, không phải “chỉ cho 5.000 requests vào queue” và không bảo đảm không hết RAM.

Để giới hạn pending requests cần **bounded executor/admission gate/rate limits** tại ứng dụng. Java 5.x mới khuyến khích `timeoutMS`/CSOT để giới hạn operation end-to-end; xem phần sau để tránh trộn timeout cũ với mới.

## 4. Cấu hình pool qua `MongoClientSettings` và URI

### 4.1. Khởi tạo một MongoClient có pool riêng

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import java.util.concurrent.TimeUnit;

public final class MongoClientConfig {
    private MongoClientConfig() { }

    public static MongoClient create(String uri) {
        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .applicationName("catalog-api")
            .applyToConnectionPoolSettings(pool -> pool
                .maxSize(64)
                .minSize(4)
                .maxConnecting(4)
                .maxConnectionIdleTime(45, TimeUnit.SECONDS)
                .maxConnectionLifeTime(30, TimeUnit.MINUTES))
            .build();

        return MongoClients.create(settings);
    }
}
~~~

Các số trên là **cấu hình thí nghiệm**; không có bằng chứng rằng `64/4/4/45s/30m` phù hợp mọi hệ thống. Hãy lấy `maxSize` theo in-flight load và server headroom, `minSize` theo warmup cần thiết, `maxConnecting` theo reconnect/cold-start tests.

### 4.2. URI tương đương

~~~text
mongodb://db1.example.internal:27017,db2.example.internal:27017,db3.example.internal:27017/?replicaSet=rs0&appName=catalog-api&maxPoolSize=64&minPoolSize=4&maxConnecting=4&maxIdleTimeMS=45000&maxLifeTimeMS=1800000
~~~

Nếu URI có `?` và nhiều options, nối bằng `&`. Tên `maxPoolSize` khác method `maxSize()` nhưng chỉ cùng một cấu hình. Trong production **không hardcode username/password** trong ví dụ hoặc logs; dùng secret manager, TLS và connection string chính thức của deployment.

### 4.3. Precedence khi vừa có URI vừa có builder

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToConnectionPoolSettings(pool -> pool.maxSize(64))
    .build();
~~~

Với đoạn builder được gọi **sau** `applyConnectionString()`, giá trị `maxSize(64)` sẽ ghi đè cấu hình tương ứng của builder nhận từ URI trong cách xây settings trên. Nhưng **đừng suy mọi option ở mọi framework có cùng precedence**: Spring Boot có auto-config/customizers và driver versions khác. Log **effective settings đã ẩn credentials** lúc start, hoặc inspect pool metrics, để xác minh.

### 4.4. Thêm `maxWaitTime()` kiểu legacy

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToConnectionPoolSettings(pool -> pool
        .maxSize(64)
        .maxWaitTime(200, TimeUnit.MILLISECONDS))
    .build();
~~~

`maxWaitTime()` tương ứng `waitQueueTimeoutMS`, hữu ích khi **không** sử dụng CSOT trên driver hỗ trợ. Khi cấu hình `timeoutMS`, docs Java hiện hành ghi **các timeout legacy bị bỏ qua theo quy tắc CSOT**, do đó đừng đặt `maxWaitTime(200ms)` rồi thêm `timeout(30s)` và tuyên bố thời gian chờ pool chắc chắn vẫn tối đa 200ms.

### 4.5. Socket/cluster settings phối hợp

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToClusterSettings(cluster -> cluster
        .serverSelectionTimeout(5, TimeUnit.SECONDS)
        .localThreshold(15, TimeUnit.MILLISECONDS))
    .applyToSocketSettings(socket -> socket
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS))
    .applyToConnectionPoolSettings(pool -> pool
        .maxSize(64)
        .maxConnecting(4))
    .build();
~~~

Lưu ý: `readTimeout()` là socket/read timeout trong Java builder tương ứng `socketTimeoutMS`, **không** thay server-side `maxTimeMS`. Một operation có thể trải qua server selection, pool checkout và socket read ở các giai đoạn riêng. Với CSOT, nên **chọn một mô hình deadline rõ ràng** thay vì cấu hình tất cả legacy timeouts chồng lấn.

### 4.6. Khi dùng Spring Boot/Spring Data

~~~yaml
spring:
  data:
    mongodb:
      uri: "mongodb://db1.example.internal:27017/?replicaSet=rs0&maxPoolSize=64&maxConnecting=4"
~~~

Đây là **mẫu cấu hình khái niệm** cho deployment có cách resolve host phù hợp; nếu chỉ khai một host seed, driver phải có thể khám phá các host replica set được công bố. Với Atlas dùng `mongodb+srv://...`/TLS theo thông tin Atlas cấp, không thay URL tùy tiện.

Trong Spring Boot:

- Để framework quản lý **MongoClient singleton bean**.
- Tránh gọi `MongoClients.create` bên trong mỗi request/repository.
- Kiểm tra auto-configuration có tạo thêm client nếu bạn tự định nghĩa bean.
- Với `MongoClientSettingsBuilderCustomizer`, xác nhận thứ tự customizer và effective settings.
- Đóng client khi application shutdown/drain; không đóng giữa requests.

## 5. SDAM: driver biết topology bằng cách nào?

**SDAM (Server Discovery and Monitoring)** là cơ chế driver tìm những servers trong topology, theo dõi tình trạng và phản ứng khi primary thay đổi. Nó **khác** CMAP (Connection Monitoring and Pooling), dù cả hai cùng quản lý sockets và có events.

### 5.1. Discovery với replica set

~~~text
MongoClient connects to seed list
           |
           v
       Hello/handshake
           |
           v
 Driver learns replica set name,
 members, roles and topology info
           |
           v
 Monitor detects:
   - Primary P
   - Secondary S1
   - Secondary S2
           |
           v
 Server selection chooses an eligible node
           |
           v
 Checkout from that node's pool
~~~

Khi một server stepdown hoặc bị mất mạng, driver cập nhật cluster description và chọn server khác phù hợp khi có thể. **Không phải mỗi query quét tất cả nodes**: SDAM duy trì thông tin topology riêng và driver dựa vào thông tin đó để chọn server.

### 5.2. Heartbeats và topology updates

Java Sync Driver docs hiện hành liệt kê:

| Option | Default | Ý nghĩa |
|---|---:|---|
| `heartbeatFrequencyMS` | 10.000 ms | Khoảng thời gian giữa các lần monitor thử xác định trạng thái server. |
| `minHeartbeatFrequency` trong Builder | 500 ms | Ngưỡng thời gian tối thiểu cho monitoring check theo docs. |
| `serverMonitoringMode` | `auto` | Có thể chọn polling hoặc streaming tùy môi trường, ví dụ FaaS. |

Monitor có thể xử lý immediate topology change signals, nên không nên suy cứng rằng “chỉ phát hiện primary mới sau đúng 10 giây”. Giảm heartbeat xuống cực thấp có thể làm tăng network/server overhead, không thay cơ chế timeout thích hợp cho application.

### 5.3. Mô hình topology sau election

~~~text
t0:  P là primary, S1/S2 secondaries
t1:  P down / stepdown
t2:  driver discovers no eligible primary
t3:  write operation waits at server selection
t4:  S1 becomes primary; SDAM refreshes
t5:  driver selects S1
t6:  checkout S1 connection, execute command
~~~

Nếu operation timeout ở `t3–t4`, lỗi liên quan **server selection**, không phải pool `maxPoolSize`. Nếu driver đã thấy S1 primary nhưng S1 pool vừa bị clear và chưa có connection ready, latency có thể chuyển sang **pool checkout/connection establishment**.

### 5.4. Mô tả cluster trong exception rất có giá trị

~~~text
Client view of cluster state is:
{
  type=REPLICA_SET,
  servers=[
    {address=db1:27017, type=UNKNOWN,
     exception=MongoSocketOpenException: connection refused},
    {address=db2:27017, type=REPLICA_SET_SECONDARY,
     state=CONNECTED},
    {address=db3:27017, type=UNKNOWN}
  ]
}
~~~

Nếu chỉ có secondary reachable mà request cần `primary`, server selection timeout là kết quả hợp lý. **Không nên tự chuyển writes sang secondary** để “vượt lỗi”: replica set writes thông thường phải tới primary.

### 5.5. Seed list khác tập member cuối cùng

Một URI chỉ cần cung cấp seed hosts phù hợp, driver có thể khám phá các members qua handshake. Tuy nhiên, những **hostnames được server công bố phải resolve/reachable từ ứng dụng**; đây là lỗi phổ biến khi chạy MongoDB trong Docker/Kubernetes nhưng clients ở mạng khác.

Ví dụ app kết nối seed `localhost:27017`, driver nhận members `mongo1:27017`, `mongo2:27017` nhưng tên đó chỉ resolve trong container network; server selection có thể thất bại. Cần cấu hình replica set members **bằng địa chỉ hợp lệ trong mạng client**, không chỉ tăng timeout.

### 5.6. `replicaSet` và cấu hình sai tên

URI:

~~~text
mongodb://db1:27017,db2:27017/?replicaSet=rs0
~~~

Nếu cluster thực là `rsOther`, driver có thể không coi các server đó là members phù hợp. Kiểm tra tên replica set thực, certificates/DNS/port và cluster description; đừng đổi tên replica set trên production chỉ vì ứng dụng đang dùng URI sai.

### 5.7. Môi trường TLS/DNS lỗi không phải pool exhaustion

`SSLHandshakeException`, certificate chain error, hostname mismatch, DNS SRV lookup fail, socket refused hoặc network timeout xảy ra **trước hoặc trong kết nối**. Pool cap không thể tự sửa certificate/truststore sai. Tách logs:

- DNS lookup / seed list.
- TCP connect.
- TLS certificate/hostname verification.
- MongoDB authentication handshake.
- SDAM topology.
- Pool checkout và command execution.

## 6. Server selection: quy tắc chọn primary, secondary và nearest

Khi operation bắt đầu, driver xác định **những servers đủ điều kiện** rồi chọn trong tập đó. Với replica set, điều kiện bao gồm:

1. **Operation type:** Writes thông thường yêu cầu primary; reads theo read preference.
2. **Member state:** Primary/secondary, healthy/reachable.
3. **Read preference:** `primary`, `primaryPreferred`, `secondary`, `secondaryPreferred`, `nearest`.
4. **Tags, staleness:** Nếu cấu hình, secondaries phải đáp ứng tag sets/maxStalenessSeconds.
5. **Latency window:** Trên các servers phù hợp, driver chọn node có RTT nằm trong khoảng giới hạn.

### 6.1. Read preference modes

| Mode | Server được chọn cho read | Cần cân nhắc |
|---|---|---|
| `primary` (mặc định) | Primary hiện tại. | Dễ đọc newest-primary state theo semantics; fail nếu không có primary. |
| `primaryPreferred` | Ưu tiên primary, fallback secondaries khi primary không available. | Có thể đọc dữ liệu stale khi fallback. |
| `secondary` | Eligible secondary. | Không fallback primary; có thể stale hoặc không có eligible secondary. |
| `secondaryPreferred` | Ưu tiên secondaries; nếu không có thì fallback primary. | Có thể tạo hành vi không ổn định giữa secondary và primary sau failover. |
| `nearest` | Member có RTT trong latency window, kể cả primary/secondary. | Không bảo đảm dữ liệu mới nhất; tối ưu đường mạng không phải độ mới. |

**Writes không chuyển sang secondary khi chọn `readPreference=secondary`.** Driver vẫn yêu cầu server writable cho writes thông thường. Transactions có constraints riêng: theo MongoDB docs, các transaction có reads phải sử dụng **primary read preference**; không dùng `secondary` cho multi-document transaction rồi trông chờ routing qua secondary.

### 6.2. Ví dụ Java với `ReadPreference`

~~~java
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

MongoCollection<Document> inventory = mongoClient
    .getDatabase("shop")
    .getCollection("inventory")
    .withReadPreference(ReadPreference.secondaryPreferred());

Document item = inventory
    .find(new Document("_id", "SKU-100"))
    .first();
~~~

`withReadPreference` trả về **collection handle** cấu hình cho những operations qua handle đó; không cần tạo MongoClient mới chỉ để đổi read preference một collection. Việc chọn secondary có **replication lag**; không dùng cho yêu cầu read-after-write mạnh nếu business cần đọc ngay giá trị vừa commit.

### 6.3. `localThresholdMS` và latency window

Java Sync Driver docs nêu mặc định `localThresholdMS=15`. Nếu các eligible servers có round-trip time (RTT):

~~~text
S1: 10 ms  <-- fastest
S2: 21 ms
S3: 31 ms

Latency window threshold = 15 ms
Eligible by latency: RTT <= 10 + 15 = 25 ms
=> S1 và S2, không S3.
~~~

**Cẩn trọng:** Latency window áp dụng **sau khi** lọc role/read preference/tags/staleness. Nếu readPreference chỉ có một eligible primary, `localThresholdMS` không tạo ra secondary để chọn. Server selection thường **phân bổ ngẫu nhiên** trong latency window theo semantics driver; không mặc định chọn server có RTT nhỏ nhất mọi lần.

### 6.4. `nearest` không đồng nghĩa “secondary gần địa lý nhất”

`nearest` xét RTT và eligible servers, **không** tự hiểu region/data residency hoặc business consistency. Một secondary gần client có thể chậm apply replication; dữ liệu stale dù RTT thấp. Nếu cần region routing, có thể dùng tag sets, read preference và topology policy phù hợp; đồng thời xét freshness và quyền dữ liệu.

### 6.5. `maxStalenessSeconds` và tag sets

Read preference có thể kèm:

- `maxStalenessSeconds` để loại những secondaries quá stale (theo estimated lag).
- Tag sets để ưu tiên hoặc giới hạn nodes có tags phù hợp, ví dụ `region:ap-southeast`.

Không suy rằng max staleness là **cam kết tuyệt đối** “dữ liệu không bao giờ chậm hơn N giây”: driver ước lượng dựa trên replication metadata và monitoring, còn business need có thể yêu cầu transactional/read concern semantics khác. MongoDB docs đặt ràng buộc giá trị tối thiểu maxStaleness (thường >=90 giây); xác minh version/monitoring frequency trước khi cấu hình.

### 6.6. Server selection với `mongos`

Trên sharded cluster, MongoClient thường chọn một **router `mongos`** trong danh sách endpoints/eligible latency window, còn `mongos` quyết định route tới shard(s). Không thể ép mọi query shard-local chỉ bằng `localThresholdMS`; query targeting phụ thuộc shard key/filter và cluster metadata.

### 6.7. Không có server phù hợp: điều gì xảy ra?

Driver đợi topology update và cố chọn server cho tới khi:

- Tìm được server eligible, rồi chuyển sang checkout pool; hoặc
- Hết `serverSelectionTimeoutMS` (legacy) hoặc remaining CSOT deadline; phát sinh exception.

**Đợi chọn server khác với đợi một connection**. Đây là lý do một exception có chuỗi `ReadPreferenceServerSelector{readPreference=primary}` không chứng minh pool size thiếu.

## 7. Các loại timeout: bảng phân biệt đầy đủ

MongoDB Java Driver có nhiều giới hạn thời gian vì **các hoạt động khác nhau có thể bị treo ở những bước khác nhau**. Một số giới hạn là client-side, một số là server-side và một số được kế thừa theo database/collection/operation. Không tồn tại một thuộc tính `timeout` duy nhất hoạt động giống nhau ở mọi bản driver.

| Option | Default Java Driver hiện hành | Áp cho bước nào? | Không giải quyết được |
|---|---|---|---|
| `serverSelectionTimeoutMS` | 30.000 ms | Chờ chọn server phù hợp theo topology/read preference. | Pool checkout/server execution sau khi chọn được server. |
| `connectTimeoutMS` | 10.000 ms | Mở socket/thiết lập kết nối network. | Hàng đợi mượn socket có sẵn trong pool. |
| `socketTimeoutMS` | 0 (không đặt giới hạn read/write socket legacy). | Chờ gửi/nhận dữ liệu trên socket. | Bao trùm toàn bộ request/application queue. |
| `waitQueueTimeoutMS` | 120.000 ms trong Java docs hiện hành, **deprecated**. | Chờ pooled connection available. | Giới hạn số waiters hoặc server execution. |
| `maxTimeMS` | Không mặc định áp giới hạn operation nếu chưa set (theo operation). | Thời gian thực thi server của command hỗ trợ. | Server selection/pool wait/network end-to-end. |
| `maxCommitTimeMS` | Theo transaction options, nếu chưa đặt thì không có mốc này. | Giới hạn thời gian commit transaction phía server theo semantics. | Đảm bảo commit chắc chắn rollback khi response timeout. |
| `wTimeoutMS` | Phụ thuộc write concern, chỉ khi có `wtimeout`. | Giới hạn chờ write concern acknowledgement. | Hủy write đã được áp dụng. |
| `timeoutMS` (CSOT) | Không set trừ khi cấu hình. | Deadline client operation từ selection → checkout → execution. | Phần xử lý HTTP trước/sau MongoDB, và rollback business tự động. |

**Các default nói trên thuộc phạm vi Java Sync Driver docs hiện tại**; timeout behavior của driver 4.x, legacy mongosh và server options có thể khác. Khi `timeoutMS` được cấu hình, các legacy options liên quan có thể bị driver **ignore theo tài liệu CSOT**, nên không được giả sử bảng default nào cũng đồng thời có hiệu lực.

### 7.1. Ví dụ timeline để nhận ra điểm hết hạn

~~~text
HTTP handler bắt đầu    0 ms
Auth/validation xong    40 ms
Server selection xong   90 ms   (+50)
Pool checkout xong     240 ms   (+150)
Server command xong    430 ms   (+190)
Transform/HTTP xong    455 ms   (+25)
~~~

Trong kịch bản này:

- `serverSelectionTimeoutMS=200`: không vi phạm vì selection chỉ tốn 50 ms.
- `waitQueueTimeoutMS=100` (legacy): có thể timeout trong checkout vì chờ 150 ms.
- `maxTimeMS=300`: không vi phạm vì server execution giả định 190 ms.
- `timeoutMS=400` (CSOT): MongoDB operation có thể timeout trước khi hoàn tất nếu tính từ khi bắt đầu operation đến mốc 430 ms.
- HTTP deadline 500 ms: tổng xử lý 455 ms nằm trong SLA về mặt ví dụ (không nói tới p95/p99).

Vấn đề không phải chọn “timeout nào lớn nhất”, mà là **giới hạn nào phù hợp với stage đang bị chậm và deadline còn lại**.

## 8. `serverSelectionTimeoutMS`: chọn được primary/secondary trước đã

### 8.1. Ý nghĩa

Driver chờ tới khi topology có **ít nhất một server eligible** với operation/read preference, hoặc hết thời gian selection. Java docs mặc định **30 giây**. Exception thường ở dạng:

~~~text
com.mongodb.MongoTimeoutException:
Timed out after 30000 ms while waiting for a server
that matches ReadPreferenceServerSelector{readPreference=primary}.
Client view of cluster state is ...
~~~

Đọc phần `Client view of cluster state` để biết:

- Cluster type và replica set members driver nhìn thấy.
- Primary được phát hiện hay không.
- Server nào UNKNOWN/CONNECTING.
- Có socket/DNS/TLS errors không.
- Node healthy nhưng chỉ là SECONDARY?
- Hostnames trong replica set config có reachable từ app không?

### 8.2. Java Builder

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToClusterSettings(cluster -> cluster
        .serverSelectionTimeout(3, TimeUnit.SECONDS))
    .build();
~~~

URI tương đương:

~~~text
mongodb://db1:27017,db2:27017/?replicaSet=rs0&serverSelectionTimeoutMS=3000
~~~

**Đây là cấu hình ví dụ**, không phải khuyến cáo “mọi app nên timeout sau 3 giây”. Với failover bình thường mất vài giây, timeout cực ngắn có thể gây nhiều lỗi tạm; với HTTP API chỉ có deadline 500 ms, timeout 30 giây có thể giữ request quá lâu. Cần thống nhất policy từ application đến driver.

### 8.3. Những nguyên nhân thường gặp

| Nguyên nhân | Dấu hiệu | Cách kiểm |
|---|---|---|
| Primary stepdown/election | Không có eligible primary tạm thời; secondaries còn reachable. | Replica set status, SDAM transitions. |
| Network partition/DNS lỗi | Nhiều nodes UNKNOWN/CONNECTING, socket refused/timeout. | DNS, port, firewall, TLS, SRV resolution. |
| Replica set seed list sai | Driver khám phá hostnames không reachable. | `rs.conf()` trên lab/cluster có quyền, network path thực. |
| Replica set name sai | Members bị loại do không đúng replica set expected. | URI `replicaSet` và cluster config. |
| Read preference quá hạn chế | Secondary tagged không có hoặc quá stale. | Tags/maxStalenessSeconds/eligible nodes. |
| Server role không phù hợp | Read cần secondary nhưng không có secondary eligible. | Read preference và topology. |
| Load balancer/mongos không khả dụng | Không chọn được router. | Health của mongos/LB/network. |

### 8.4. Đừng đổi read preference để chữa network bằng mọi giá

Chuyển `primary` sang `secondaryPreferred` có thể giúp một số read operations chịu dữ liệu stale, **nhưng**:

- Writes vẫn cần writable primary.
- Read-after-write có thể trả giá trị cũ.
- Transaction read constraints vẫn áp dụng.
- Nếu network không reachable toàn bộ replica set, read preference cũng không tạo server mới.

Chỉ đổi khi **business cho phép consistency trade-off** và đã kiểm chứng tác động.

### 8.5. Deadline CSOT có thể cắt selection sớm hơn

Nếu cấu hình `timeoutMS=500`, operation có thể hết client deadline trong selection dù `serverSelectionTimeoutMS=30.000`. Vì vậy khi quan sát thực tế, cần xem **CSOT đã bật chưa và timeout nào có hiệu lực**; không giải thích mọi selection error bằng mỗi `serverSelectionTimeoutMS`.

## 9. `connectTimeoutMS`: khi socket mới không mở được

### 9.1. Ý nghĩa

`connectTimeoutMS` giới hạn thời gian driver chờ **mở một connection mới** trước khi báo lỗi. Java docs hiện hành nêu default **10 giây**; cấu hình `0` ở option legacy tương ứng không đặt giới hạn mở socket.

~~~text
Driver needs a new socket
        |
        v
DNS/address resolution
        |
        v
TCP connect -> TLS handshake -> MongoDB handshake/auth
        |
        v
Connection ready for pool
~~~

Một số chi phí như DNS/TLS/handshake có phạm vi timeout/giới hạn riêng theo driver/JVM. Không suy rằng chỉ một option bảo đảm toàn bộ các bước startup luôn kết thúc đúng N ms.

### 9.2. URI/Java

~~~text
mongodb://db1:27017/?connectTimeoutMS=3000
~~~

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToSocketSettings(socket -> socket
        .connectTimeout(3, TimeUnit.SECONDS))
    .build();
~~~

### 9.3. Khi connect timeout không phải hết pool

Pool đang rỗng sau cold start và driver thử tạo socket tới host unreachable. Request có thể fail với `MongoSocketOpenException` hoặc nested `ConnectException`. Tăng `maxPoolSize` không giúp host trở nên reachable. Kiểm:

1. DNS/SRV records đúng chưa.
2. Port/firewall/security group/private endpoint.
3. TLS truststore/certificate SAN/hostname.
4. Server còn accept connections hay đã đạt OS/file descriptor limits.
5. `maxConnecting` và số pending socket establishments.

### 9.4. Network timeout và slow server

Nếu TCP connect thành công nhưng query mất 10 giây vì COLLSCAN, **`connectTimeoutMS` không giới hạn query execution**. Cần xem command monitoring, `maxTimeMS`/CSOT và query plan.

## 10. `socketTimeoutMS`: chờ gửi/nhận bytes qua socket

### 10.1. Ý nghĩa

`socketTimeoutMS` là timeout đọc/ghi socket theo Java Driver semantics; mặc định hiện hành **0** (không đặt timeout legacy). Đây không phải một đồng hồ duy nhất tính toàn bộ thời gian MongoDB server thực thi mọi bước.

~~~text
Checkout succeeded
       |
       v
Write MongoDB command bytes
       |
       v
Wait for response bytes over network
       |
       v
Decode BSON result
~~~

Nếu trong thời gian read/write không nhận được dữ liệu theo semantics, client có thể gặp `MongoSocketReadTimeoutException` hoặc socket/network errors. **Không kết luận chắc chắn command chưa thực hiện** chỉ vì client không nhận được response.

### 10.2. Cấu hình

~~~text
mongodb://db1:27017/?socketTimeoutMS=15000
~~~

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToSocketSettings(socket -> socket
        .readTimeout(15, TimeUnit.SECONDS))
    .build();
~~~

### 10.3. Vì sao timeout quá thấp nguy hiểm

Nếu một aggregation legitimately tốn 2 giây nhưng `socketTimeoutMS=500`, ứng dụng có thể ngắt socket liên tục, pool clear/reconnect và retry những operations đắt. Đây là **amplification**, không phải tối ưu performance.

Giải pháp đúng thường là:

- Tối ưu query/index/aggregation.
- Đặt `maxTimeMS` khi cần giới hạn server execution.
- Dùng CSOT với deadline rõ ràng trên driver hỗ trợ.
- Đưa exports lớn thành async job.
- Chọn socket timeout tương thích network/SLO, tránh quá ngắn và đo error reasons.

### 10.4. Timeout socket không đồng nghĩa rollback

Với writes, server có thể đã commit dù client socket timeout trước khi nhận acknowledgement. Trước retry, phải hiểu **retryable writes**/idempotency và trạng thái commit; không tự tạo requestId mới sau mỗi timeout.

## 11. `waitQueueTimeoutMS`: chờ checkout pool

### 11.1. Pool wait phát sinh khi nào?

Pool có maxSize 20. Có 20 operations đang checked-out, thêm operation thứ 21 đến:

~~~text
Pool server P:
  20 / 20 checked out
      |
      +-- new request wants connection
               |
               v
         wait for available connection
               |
         +-----+--------+
         |              |
      returned         timeout
         |              |
      checkout       exception
~~~

Thời gian này là **connection checkout wait**; không phải server selection, và không được tính vào `maxTimeMS` server execution. Driver có thể chờ dù server vẫn xử lý nhanh từng command, nếu too many concurrent operations cùng dùng pool.

### 11.2. Java 5.x mặc định và deprecation

MongoDB Java Driver pool docs hiện hành ghi `waitQueueTimeoutMS` mặc định **120.000 ms (2 phút)** và được đánh dấu **deprecated**, khuyến khích client-level `timeoutMS`. Nếu `timeoutMS` đã set, legacy wait timeout có thể **bị ignore** theo CSOT rules.

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToConnectionPoolSettings(pool -> pool
        .maxSize(40)
        .maxWaitTime(200, TimeUnit.MILLISECONDS))
    .build();
~~~

Ví dụ giới hạn checkout wait 200 ms **khi không dùng CSOT** và driver version hỗ trợ `maxWaitTime()`.

### 11.3. Timeout checkout không phải deadlock detection

Nếu chờ connection quá lâu, có thể do:

- Pool cap quá nhỏ so với **legitimate concurrency**.
- Query chậm làm giữ connection lâu.
- Long-running cursor/transaction.
- Code quên close cursor/session.
- Connection creation chậm do `maxConnecting`/TLS/handshake.
- Nhiều HTTP requests tạo fan-out queries.
- Pool clear liên tục khi network/failover.

**Không** nên chỉ tăng maxPoolSize: nếu server đã CPU/IOPS bão hòa, thêm parallel commands có thể làm checkout wait chuyển thành command wait và tăng p99.

### 11.4. Driver pool không phải bounded request queue

Giới hạn `maxPoolSize=40` có thể giới hạn checked-out sockets trên một server/pool, nhưng nếu hàng chục nghìn Java threads vẫn chờ checkout với timeout 120 giây, application có thể cạn memory/thread resources. Cần **semaphore/ThreadPoolExecutor bounded queue/admission control** phía trước MongoDB call.

### 11.5. `maxConnecting` có thể tạo checkout wait dù pool chưa full

Ngay sau restart, current pool size 0/100, 100 callers đến. `maxConnecting=2` hạn chế connection establishments; những callers khác có thể chờ. CMAP events giúp phân biệt:

- **Pool full:** `checkedOutCount` sát `maxSize`.
- **Cold start:** `size` thấp nhưng `ConnectionCreated/Ready` đang tăng chậm.
- **Network:** nhiều `ConnectionClosed/PoolCleared` và failures.

Đây là ba chẩn đoán khác nhau; không có một nút “increase pool” cho cả ba.

## 12. `maxTimeMS`: thời gian thực thi phía MongoDB server

`maxTimeMS` là giới hạn **server-side execution** cho các operations hỗ trợ. Nếu một query chạy quá giới hạn, server có thể chấm dứt execution ở những điểm ngắt phù hợp và trả lỗi. Nó **không tính** khoảng thời gian request chờ admission, server selection hoặc pool checkout **trước khi command đến server**.

### 12.1. Ví dụ `find().maxTime()` trong Java

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import java.util.concurrent.TimeUnit;

MongoCollection<Document> orders =
    mongoClient.getDatabase("shop").getCollection("orders");

Document one = orders
    .find(Filters.eq("status", "OPEN"))
    .maxTime(750, TimeUnit.MILLISECONDS)
    .first();
~~~

Trong `mongosh`:

~~~javascript
db.orders.find({ status: "OPEN" }).maxTimeMS(750)
~~~

Giới hạn này không “đẩy query nhanh hơn”. Nếu query luôn quét cả collection và mất 3 giây, `maxTimeMS=750` có thể biến yêu cầu chậm thành timeout sớm; **điểm nghẽn là query plan/indexes**. Sử dụng `explain("executionStats")` để phân tích và tăng khả năng phục vụ.

### 12.2. `aggregate` và execution limits

~~~java
List<Document> pipeline = List.of(
    new Document("$match", new Document("tenantId", "tenant-a")),
    new Document("$group",
        new Document("_id", "$status")
            .append("count", new Document("$sum", 1)))
);

List<Document> result = collection.aggregate(pipeline)
    .maxTime(2, TimeUnit.SECONDS)
    .into(new ArrayList<>());
~~~

Các aggregation stages có thể dùng disk/memory/cursors và phát sinh `getMore`; semantics tổng thời gian giữa command ban đầu và cursor operations khác nhau theo server/driver/CSOT. Không coi một `maxTime` đặt ở initial aggregation là HTTP **absolute deadline** cho toàn bộ streaming cursor.

### 12.3. `maxTimeMS` không thay CSOT

Giả sử:

~~~text
Server selection:    200 ms
Pool checkout:       800 ms
Server execution:    150 ms

maxTimeMS:            500 ms
Total MongoDB call:  1150 ms
~~~

Query không vi phạm server limit 500 ms nhưng call đã mất 1,15 giây. Với client có operation deadline 900 ms, cần CSOT/timeout policy để cắt ở chặng checkout/execution thay vì tin `maxTimeMS`.

### 12.4. Nếu query bị ngắt, hãy xem nguyên nhân

Lỗi server execution exceeded thường thể hiện `MaxTimeMSExpired`/error code thích hợp, khác message `ReadPreferenceServerSelector` hoặc `Connection checkout timed out`. Điều tra:

- Index có selectivity/compound prefix đúng không?
- Query có `COLLSCAN`, `SORT` trong memory, huge `$group` không?
- Nhiều clients/transactions đang giữ resources không?
- Có lock/CPU/IOPS/WiredTiger cache pressure không?
- Deadline có quá ngắn so với expected business operation không?

Không tăng pool chỉ vì thấy lỗi `maxTimeMS`.

## 13. Write concern timeout: `wTimeoutMS` không có nghĩa ghi chưa thành công

MongoDB write concern quyết định mức **acknowledgement/durability** được yêu cầu sau một write. `wTimeoutMS`/`wtimeout` giới hạn **thời gian chờ đủ write concern**, không hủy write đã được primary áp dụng.

### 13.1. Ví dụ Java

~~~java
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

MongoCollection<Document> criticalOrders =
    mongoClient.getDatabase("shop")
        .getCollection("orders")
        .withWriteConcern(
            WriteConcern.MAJORITY.withWTimeout(
                1500, TimeUnit.MILLISECONDS));

criticalOrders.insertOne(new Document("_id", "ORD-1001")
    .append("state", "NEW"));
~~~

Đoạn này là ví dụ **legacy write concern timeout** khi không bị CSOT override; Java Driver 5.x CSOT docs ghi `wTimeoutMS` nằm trong nhóm timeout options **bị ignore khi `timeoutMS` được set**.

### 13.2. Vì sao không retry tạo bản mới?

~~~text
Client -> Primary insert ORD-1001
Primary accepts and writes data
Replication acknowledgement is delayed
Client's wtimeout expires
~~~

Operation có thể đã áp dụng trên primary, nhưng chưa đáp ứng `w:"majority"` trước timeout. Client nhận error/uncertain outcome **không chứng minh insert chưa xảy ra**. Nếu retry với `_id:ORD-1002` chỉ vì timeout, có thể tạo duplicate order.

Giải pháp business:

- Stable idempotency key/unique index cho request.
- Retryable writes theo semantics driver + server.
- Đọc/đối chiếu trạng thái khi kết quả không rõ.
- Tránh loop retry vô hạn khi replica set lag.

### 13.3. Write concern và consistency

`w:1`, `majority` và `journal` liên quan **durability/replication guarantees**; chúng không tạo ra thêm pool connections và không đổi cách chọn primary cho writes. Tăng write concern có thể **kéo dài operation latency**, khiến connections được giữ lâu hơn và pool checked-out cao hơn. Khi tune pool, cần đo workload với write concern giống production.

## 14. CSOT: `timeoutMS` giới hạn **toàn bộ MongoDB operation**

**Client-Side Operation Timeout (CSOT)** là cơ chế Java Driver hiện hành nhằm đặt một deadline cho tất cả bước cần hoàn thành MongoDB operation, gồm **server selection, connection checkout và execution**. Trang MongoDB chính thức hiện đánh dấu tính năng **experimental**; API và tương tác timeout phải kiểm theo **driver version**.

### 14.1. Vì sao CSOT giải quyết bài toán timeout rời rạc?

Trước đây ứng dụng có thể đặt:

~~~text
serverSelectionTimeoutMS = 30000
waitQueueTimeoutMS       = 120000
socketTimeoutMS          = 30000
maxTimeMS                = 30000
~~~

Nếu request trải qua nhiều giai đoạn nối tiếp, application có thể mất thời gian rất dài dù từng bước không vượt limit của nó. CSOT cho phép định nghĩa **một budget chung cho operation**, thay vì mỗi bước có một deadline độc lập.

~~~text
Operation CSOT timeoutMS = 800 ms

  100 ms: select server
  200 ms: checkout pool
  300 ms: execute command
  200 ms: remain for response/other work

All inside one 800 ms budget.
~~~

### 14.2. Cấu hình `timeoutMS`

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import java.util.concurrent.TimeUnit;

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .timeout(800L, TimeUnit.MILLISECONDS)
    .build();

MongoClient client = MongoClients.create(settings);
~~~

Hoặc URI:

~~~text
mongodb://db1:27017/?timeoutMS=800
~~~

**Những ví dụ này yêu cầu Java Driver có hỗ trợ CSOT.** Không copy sang project driver cũ nếu API không tồn tại.

### 14.3. Các giá trị CSOT đặc biệt

| `timeoutMS` | Ý nghĩa trong Java docs hiện hành |
|---|---|
| Số dương, ví dụ 800 | Giới hạn operation completion trong 800 ms. |
| `0` | Không timeout dựa trên CSOT (không giới hạn theo option đó). |
| Không set/`null` | Dùng semantics timeout legacy theo các options liên quan. |

**`0` không phải “timeout ngay lập tức”** trong CSOT; theo docs, nó nghĩa là không đặt giới hạn CSOT. Không chọn 0 trong production API có SLA chỉ vì không muốn exception.

### 14.4. Legacy timeout options bị ảnh hưởng

MongoDB Java Driver CSOT docs ghi những options sau **deprecated và ignored khi `timeoutMS` được set**:

- `waitQueueTimeoutMS`.
- `socketTimeoutMS`.
- `wTimeoutMS`.
- `maxTimeMS`.
- `maxCommitTimeMS`.

Do đó, cấu hình:

~~~text
...?timeoutMS=800&waitQueueTimeoutMS=5000&socketTimeoutMS=20000
~~~

**Không** có nghĩa “operation tối đa 800 ms, nhưng checkout được chờ 5 giây và socket đọc 20 giây”. **Operation timeout 800 ms** là cơ chế chính theo CSOT, với những giới hạn riêng khác như `connectTimeoutMS`/server selection constraints có tương tác theo implementation. Tránh trộn settings vì khó debug và dễ suy sai.

### 14.5. Thứ tự kế thừa timeout

CSOT có thể được định nghĩa trên các cấp:

| Cấp | Ý nghĩa |
|---|---|
| Client | Mặc định cho operations nếu không override. |
| Database | Áp cho operations từ database handle đó. |
| Collection | Áp cho operations từ collection handle đó. |
| Session | Default timeout cho lifecycle operations của session theo config. |
| Transaction | Timeout trong phạm vi transaction nếu set. |
| Operation | Mức cụ thể nhất và có precedence cao theo docs. |

Lưu ý đây là **scope/config inheritance**, không phải “thời gian cộng dồn”. Một collection đặt 500 ms không phải tự động cộng với client 800 ms để được 1.300 ms. Với transactions, kiểm tra rõ cách `ClientSessionOptions.defaultTimeout` và `TransactionOptions.timeout` tương tác.

### 14.6. Ví dụ override trên collection

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .timeout(800L, TimeUnit.MILLISECONDS)
    .build();

try (MongoClient client = MongoClients.create(settings)) {
    MongoCollection<Document> reports =
        client.getDatabase("shop")
            .getCollection("reports")
            .withTimeout(2L, TimeUnit.SECONDS);

    reports.find(new Document("state", "READY")).first();
}
~~~

Ở đây collection handle `reports` cho phép deadline 2 giây thay cho client-level 800 ms. **Đừng** mở rộng timeout cho mọi API chỉ vì một báo cáo chậm; nên tách long-running workload/queues và budget phù hợp.

### 14.7. Deadline HTTP khác CSOT deadline

Nếu request đã chờ 300 ms ở HTTP queue rồi mới gọi MongoDB với CSOT 800 ms, HTTP có thể mất **1.100 ms** hoặc hơn cùng với transform/network. CSOT chỉ bắt đầu theo MongoDB operation, **không tính thời gian request nằm trước driver call**.

Thiết kế tốt:

1. Nhận **absolute request deadline** ở ingress.
2. Trước MongoDB call, tính **remaining budget**.
3. Nếu còn quá ít thời gian, reject/degrade thay vì gọi DB.
4. Chọn CSOT cho operation theo remaining budget và giới hạn business.
5. Hạn chế retries trong tổng budget; không reset deadline vô hạn.

### 14.8. Timeout trong cursor: lifetime hay iteration?

MongoDB Java Driver CSOT docs có **cursor timeout modes**:

- `CURSOR_LIFETIME`: timeout áp lên **toàn bộ thời gian sống** của cursor, từ initialization qua việc đọc các batches.
- `ITERATION`: timeout áp cho **mỗi lần iteration/call như `hasNext`, `next`, `tryNext`**, được refresh theo semantics; mode mặc định cho tailable/change-stream cursors theo docs.

Ví dụ khi driver version hỗ trợ:

~~~java
import com.mongodb.client.MongoCursor;
import com.mongodb.TimeoutMode;

try (MongoCursor<Document> cursor = collection
        .find(new Document("status", "READY"))
        .timeoutMode(TimeoutMode.CURSOR_LIFETIME)
        .cursor()) {
    while (cursor.hasNext()) {
        Document doc = cursor.next();
        consume(doc);
    }
}
~~~

`consume(doc)` chỉ là hàm application minh họa; ví dụ cần `collection` và method `consume` có sẵn. **Timeout mode có tiền điều kiện CSOT timeout được kế thừa/đặt trên client/database/collection** theo docs. Với change streams dài hạn, không đặt cursor lifetime quá ngắn khiến stream phải restart liên tục.

### 14.9. CSOT không bảo đảm server operation bị rollback

Client có thể hết deadline sau khi server đã thực thi write nhưng response chưa nhận. Timeout là **quyết định client ngừng chờ**, không phải proof về business side effect. Retry writes/transactions phải theo semantics được hỗ trợ và idempotency.

### 14.10. CSOT còn ảnh hưởng transactions và encryption

CSOT docs có hỗ trợ timeout cho:

- Session lifecycle/`ClientSessionOptions.defaultTimeout`.
- `TransactionOptions.timeout`.
- `ClientEncryptionSettings.timeout` trong Client-Side Field Level Encryption.
- GridFS bucket operations và cursor iteration modes.

Không suy rằng timeout trên client/collection tự làm mọi transaction rollback kịp HTTP SLA: transaction lifecycle, commit ambiguity và session cleanup là vấn đề riêng.

## 15. Timeout trong transaction và session

### 15.1. Không dùng session đồng thời tùy ý

Một `ClientSession` phải có lifecycle rõ ràng. Java Driver không thiết kế để nhiều threads thực hiện operations đồng thời trên **cùng session** một cách tùy ý. Mỗi transaction phải giữ đúng session, chọn primary theo constraints, và xử lý retry/abort/commit theo spec.

### 15.2. Đặt transaction timeout

~~~java
import com.mongodb.TransactionOptions;
import com.mongodb.client.ClientSession;
import java.util.concurrent.TimeUnit;

TransactionOptions options = TransactionOptions.builder()
    .timeout(2, TimeUnit.SECONDS)
    .build();

try (ClientSession session = client.startSession()) {
    session.startTransaction(options);

    // Sử dụng cùng session cho các operations trong transaction.
    // collection.updateOne(session, filter, update);
    // collection.insertOne(session, document);

    session.commitTransaction();
}
~~~

**Cần MongoDB Java Driver hỗ trợ transaction-level CSOT**; method `timeout()` có thể không có trong bản cũ. Ví dụ minh họa API/lifecycle, chưa có operations thực nên không có business change.

### 15.3. Transaction timeout và server transaction lifetime

MongoDB server còn có các giới hạn transaction lifetime/locks/resources độc lập với client operation timeout. Một transaction không nên giữ hàng chục locks/cursors lâu chỉ vì `timeoutMS` lớn. Quan sát `serverStatus`/`currentOp`/transactions metrics và thiết kế **ngắn, bounded và retryable**.

### 15.4. Commit result có thể ambiguous

Giả sử:

~~~text
Client calls commitTransaction()
        |
        v
Server commits transaction
        |
        v
Network response lost / CSOT expires
~~~

Application không được kết luận “transaction chưa commit” rồi phát lại toàn bộ business workflow với ID mới. Dùng driver transaction retry helpers/`withTransaction` khi phù hợp, xử lý error labels như `UnknownTransactionCommitResult` và stable business IDs, theo docs Transactions.

### 15.5. `withTransaction` không biến operations thành free retries

Driver có thể retry transient errors theo transaction callback semantics, vì vậy callback nên **không chứa side effects ngoài MongoDB không-idempotent** (gửi email/charge payment) mà không có outbox/idempotency protection. Timeout/retries và connection pool là kỹ thuật transport; business correctness vẫn do ứng dụng thiết kế.

## 16. Phân loại exceptions theo nơi xảy ra

Không nên xử lý mọi `MongoException` bằng một nhánh “retry after 1 second”. Cùng là timeout nhưng nguyên nhân và khả năng retry khác nhau.

| Loại thông báo/exception | Giai đoạn có khả năng liên quan | Cách phân biệt |
|---|---|---|
| `MongoTimeoutException` chứa `ReadPreferenceServerSelector` | Server selection. | Client cluster description; có primary/secondary eligible không? |
| `MongoTimeoutException` chứa `Timed out waiting for a connection` / pool checkout | Connection pool. | Checked-out count, queue wait, connection churn. |
| `MongoSocketOpenException` / `ConnectException` | TCP connect/network. | Host/port/DNS/firewall/TLS/connect timeout. |
| `MongoSocketReadTimeoutException` | Socket read/wait response. | Server command duration, network, socket timeout config. |
| `MongoSecurityException` / authentication error | Credentials/auth handshake. | User/authSource/permissions/SCRAM/TLS identity. |
| Error code `MaxTimeMSExpired` hoặc max time exceeded | Server execution. | Query plan/aggregation/locks/CPU/IOPS. |
| `MongoWriteConcernException`, wtimeout-related | Write concern acknowledgement. | Replication lag/majority availability; write may have applied. |
| Error label `TransientTransactionError` | Transaction transient failure. | Retry whole transaction theo helper/spec, budget. |
| Error label `UnknownTransactionCommitResult` | Commit outcome không rõ. | Retry commit/verify theo spec, không nhân đôi business action. |
| `MongoInterruptedException`/cancellation-related | Caller thread interrupted hoặc operation cancel. | Deadline/cancel behavior, cursor/session cleanup. |

**Class và thông điệp cụ thể thay đổi theo driver version**; bảng là hướng chẩn đoán, không phải mapping tuyệt đối. Một socket error có thể bọc trong server selection timeout khi driver không tìm được bất cứ server nào đủ điều kiện.

### 16.1. Phân loại theo context, không parse string cứng

Đừng viết:

~~~java
if (e.getMessage().contains("30000")) {
    // assume pool exhausted
}
~~~

Vì số 30.000 có thể thuộc **server selection** và lỗi message không là API ổn định. Hãy dùng class/causes, error labels/codes khi có, CMAP/SDAM events, trace spans và cluster description đã redacted để biết nguồn.

### 16.2. Một catcher ở API layer

~~~java
try {
    return orders.find(Filters.eq("_id", id)).first();
} catch (MongoTimeoutException e) {
    // Log correlationId, operation class, elapsed time,
    // server/pool/SDAM metrics from separate instrumentation.
    throw new ServiceUnavailableException(
        "Database deadline or server selection unavailable", e);
} catch (MongoException e) {
    // Other MongoDB command/network/auth/write errors need
    // classification by codes/labels and operation semantics.
    throw new DataAccessFailureException("Database operation failed", e);
}
~~~

Ví dụ trên dùng các application exception giả định `ServiceUnavailableException` và `DataAccessFailureException`; cần khai báo trong dự án thực và không hiển thị exception internals/credentials ra client. Với API có idempotent read, retry policy khác writes.

### 16.3. Retry read và retry write

Java Driver hỗ trợ các cơ chế retryable reads/writes theo điều kiện. Tuy nhiên:

- Không phải mọi operation đều retry được.
- Không phải mọi network timeout đều thuộc error labels có thể retry.
- Application-side manual retry có thể nhân attempts do driver đã retry nội bộ.
- Deadline phải tính cho tổng attempts.
- Đối với writes, phải giữ cùng business idempotency semantics.

Không tự bật retry vô hạn bằng vòng `while(true)` quanh MongoDB call.

## 17. CMAP: quan sát connection pool thay vì đoán

**CMAP (Connection Monitoring and Pooling)** cung cấp những sự kiện driver về pool và connection lifecycle. Trong Java Driver có `ConnectionPoolListener`, giúp biết operation chờ **checkout** bao lâu, pool có tạo connection mới hay vừa clear.

### 17.1. Các events cần biết

| Sự kiện | Điều phản ánh |
|---|---|
| `connectionPoolCreated` / `connectionPoolReady` | Pool được tạo và sẵn sàng theo lifecycle. |
| `connectionPoolCleared` | Connections trong pool bị invalidate/clear, thường liên quan topology/network. |
| `connectionCreated` | Driver khởi tạo một connection mới. |
| `connectionReady` | Connection đã handshake/ready để dùng. |
| `connectionClosed` | Connection đóng, có reason tùy event. |
| `connectionCheckOutStarted` | Operation bắt đầu tìm connection. |
| `connectionCheckedOut` | Operation lấy được pooled connection. |
| `connectionCheckOutFailed` | Checkout thất bại do timeout/pool closed/lỗi. |
| `connectionCheckedIn` | Operation trả connection cho pool. |

Không suy “checkout started không thấy checked out” = leak chắc chắn: có thể có **checkout failed**. Muốn current checked-out phải giữ gauge tăng khi checked out và giảm khi checked in **đúng event matching**, hoặc dùng JMX listener.

### 17.2. Đăng ký `ConnectionPoolListener` trong Java

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.event.ConnectionPoolListener;
import com.mongodb.event.ConnectionCheckedOutEvent;
import com.mongodb.event.ConnectionCheckedInEvent;
import com.mongodb.event.ConnectionCheckOutFailedEvent;
import java.util.concurrent.atomic.LongAdder;

public final class PoolEventsDemo {
    static final class Counters implements ConnectionPoolListener {
        final LongAdder checkoutSuccess = new LongAdder();
        final LongAdder checkoutFailed = new LongAdder();
        final LongAdder checkedIn = new LongAdder();

        @Override
        public void connectionCheckedOut(ConnectionCheckedOutEvent e) {
            checkoutSuccess.increment();
        }

        @Override
        public void connectionCheckOutFailed(ConnectionCheckOutFailedEvent e) {
            checkoutFailed.increment();
        }

        @Override
        public void connectionCheckedIn(ConnectionCheckedInEvent e) {
            checkedIn.increment();
        }
    }

    public static MongoClient create(String uri, Counters c) {
        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .applyToConnectionPoolSettings(pool -> pool
                .maxSize(64)
                .addConnectionPoolListener(c))
            .build();
        return MongoClients.create(settings);
    }
}
~~~

**Đây là counters tích lũy**, không phải gauge số kết nối current. Lấy `checkoutSuccess - checkedIn` chỉ là ước lượng nếu events không bị mất, lifecycle và event order được quản lý tốt; để lấy current pool size/checkedOutCount ổn định, dùng JMX/MXBeans hoặc metrics library với synchronous gauges hợp lệ.

### 17.3. Vì sao cần timestamp events?

Muốn đo checkout wait latency:

~~~text
t=10:00:00.000  CheckOutStarted
t=10:00:00.083  CheckedOut

checkout wait = 83 ms
~~~

Instrumentation phải **correlate events đúng operation/connection checkout attempt**; không lấy timestamp event của request A trừ event của request B rồi gọi là latency. Dùng OpenTelemetry/Micrometer/driver instrumentation có hỗ trợ, không tự ghép events chỉ bằng server address khi có hàng nghìn requests đồng thời.

### 17.4. Những metrics tối thiểu cần biểu đồ

- `pool.size` (open pooled connections).
- `pool.checkedOut` (in use).
- `pool.checkoutWait.p50/p95/p99`.
- `pool.checkoutFailed` theo reason.
- `connection.created/ready/closed` rates.
- `pool.cleared` và topology events.
- `serverSelectionDuration` nếu instrumentation có.
- `commandDuration` / errors theo command name.

Nếu chỉ theo dõi MongoDB `connections.current` mà không theo **per-client checkout wait**, bạn có thể bỏ sót bottleneck ở app.

## 18. JMX và command/SDAM monitoring

### 18.1. `JMXConnectionPoolListener`

Java Driver docs hướng dẫn đăng ký:

~~~java
import com.mongodb.management.JMXConnectionPoolListener;

JMXConnectionPoolListener jmxListener =
    new JMXConnectionPoolListener();

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToConnectionPoolSettings(pool ->
        pool.addConnectionPoolListener(jmxListener))
    .build();

MongoClient client = MongoClients.create(settings);
~~~

MXBeans nằm dưới domain `org.mongodb.driver`, có những properties như `clusterId`, `host`, `port`, `minSize`, `maxSize`, `size` và `checkedOutCount`. Dùng JConsole/JMX exporter/Micrometer phù hợp. **Không mở remote JMX thiếu authentication** vì có thể làm lộ operational details.

### 18.2. CommandListener

`CommandListener` nhận `CommandStartedEvent`, `CommandSucceededEvent`, `CommandFailedEvent`. Dùng để đo:

- Query/aggregate/insert/update/getMore duration.
- Commands lỗi theo error type/code (không log dữ liệu nhạy cảm).
- Số lần retry attempts so với request.
- Phân biệt command execution latency khỏi checkout/server selection.

Ví dụ:

~~~java
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import com.mongodb.event.CommandFailedEvent;

final class MongoCommandEvents implements CommandListener {
    @Override
    public void commandStarted(CommandStartedEvent event) {
        recordStarted(event.getCommandName());
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        recordSuccess(event.getCommandName());
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        recordFailure(event.getCommandName());
    }

    private void recordStarted(String name) { /* metrics counter */ }
    private void recordSuccess(String name) { /* metrics counter */ }
    private void recordFailure(String name) { /* metrics counter */ }
}

// Register in builder:
// .addCommandListener(new MongoCommandEvents())
~~~

Listener chỉ minh họa counters. Để đo thời gian chính xác, `CommandSucceededEvent` có elapsed-time APIs theo driver version và correlation identifiers; dùng supported getters hoặc tracer. Không dựa vào một global stopwatch khi nhiều commands chạy đồng thời.

### 18.3. SDAM events

SDAM listeners như `ClusterListener`/`ServerListener`/`ServerMonitorListener` phản ánh:

- Cluster description changed.
- Member role đổi từ PRIMARY sang UNKNOWN/SECONDARY.
- Monitor heartbeat success/fail.
- Topology/server availability.

Khi `serverSelectionTimeoutMS` xuất hiện, **SDAM timeline** giải thích liệu driver mất primary, gặp hostname không reachable hay đang khám phá cluster.

### 18.4. Phân biệt ba biểu đồ

~~~text
HTTP p99 latency
   |
   +--> Driver server selection wait
   |
   +--> Driver connection checkout wait
   |
   +--> MongoDB command duration
~~~

Một request có thể chậm ở nhiều đoạn; tổng p99 không được suy từ cộng p99 từng đoạn một cách máy móc vì những percentiles đến từ các requests khác nhau. Dùng **per-request traces** và breakdown.

### 18.5. Bảo mật metrics/logs

- Không log full connection URI có password.
- Không log BSON command chứa PII/tokens nếu không có policy.
- Không gắn `userId`/`requestId`/query text vào Prometheus labels gây high cardinality.
- Ẩn hostname/IP nội bộ khi xuất metrics ra hệ thống không đáng tin.
- Đặt retention, RBAC và auditing cho traces.

## 19. Server-side metrics để đối chiếu driver

Trên `mongosh` với quyền quan sát:

~~~javascript
const status = db.getSiblingDB("admin")
  .runCommand({ serverStatus: 1 })

printjson(status.connections)
printjson(status.opcounters)
printjson(status.globalLock?.currentQueue)
~~~

### 19.1. `serverStatus.connections`

Các trường có thể gồm:

- `current`: tổng incoming client connections, gồm cả idle/monitor.
- `active`: số incoming connections có operation đang diễn ra theo semantics/version.
- `available`: connections server còn có thể chấp nhận.
- `totalCreated`: counter tích lũy từ khi server start.
- `rejected`: thống kê rejected connections nếu version hỗ trợ.

Không thay `pool.checkedOutCount` bằng `connections.current`: server nhìn nhiều clients; Java client nhìn một pool cụ thể.

### 19.2. Lock/queue và storage engine

`globalLock.currentQueue`/server admission queues (nếu version có) phản ánh **server-side waiting**, không phải `ConnectionPoolListener` checkout wait. MongoDB `serverStatus` 8.x/9.x có các metrics `queues` mới/khác tên theo patch versions; dashboards phải version-aware.

WiredTiger cache pressure, eviction, disk IOPS, CPU saturation và query plan có thể làm **command latency** tăng; tăng pool lúc này thường đẩy thêm commands vào bottleneck.

### 19.3. Query plan

~~~javascript
db.orders.explain("executionStats").find({
  tenantId: "tenant-a",
  status: "OPEN"
}).sort({ createdAt: -1 }).limit(25)
~~~

Đọc `totalKeysExamined`, `totalDocsExamined`, stages `IXSCAN/COLLSCAN/SORT` và actual execution stats. Nếu query quét hàng triệu documents để trả 25, tối ưu index/query có thể giảm **thời gian giữ connection** nhiều hơn việc tăng pool.

### 19.4. Operation đang chạy

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true, idleConnections: false } },
  { $match: { active: true } },
  { $project: {
      ns: 1,
      op: 1,
      secs_running: 1,
      waitingForLock: 1,
      appName: 1
  }}
])
~~~

`$currentOp` có thể yêu cầu quyền elevated; không chạy/đưa raw commands nhạy cảm ra logs công khai. Những commands chạy lâu có thể liên quan cursor/transactions/aggregation và kéo pool checkout wait lên.

## 20. Failover, pool clear và connection storms

### 20.1. Khi primary stepdown

~~~text
t0  App requests normally reach Primary P
t1  P steps down / connection breaks
t2  SDAM reports no eligible primary
t3  Writes wait for server selection
t4  New primary S1 elected
t5  Driver updates cluster description
t6  Pools may clear/reconnect; connections ramp up
t7  Backlogged writes + retries hit S1
~~~

Tại `t2–t3`, tăng pool trên P không có nghĩa gì vì **không có eligible primary**. Tại `t6`, `maxConnecting` có thể giới hạn số connections mới được tạo đồng thời; quá nhiều application pods cùng reconnect có thể tạo TLS/auth storm. Tại `t7`, retries không có backoff có thể áp tải lớn lên primary mới.

### 20.2. Phân biệt error spikes trong failover

| Thời điểm | Triệu chứng | Cách hành động |
|---|---|---|
| Mất primary | Server selection timeout/read preference primary. | Kiểm SDAM/election; chờ có hạn theo business deadline. |
| Mở socket tới primary mới | Connect/open exceptions, high created rate. | Network/TLS/DNS, `maxConnecting`, rollout warmup. |
| Client đã chọn server nhưng pool còn cold | Checkout wait tăng, `size` thấp hơn `maxSize`. | Quan sát pool ramp, avoid connection storm. |
| Server mới bị dồn retries | Command latency cao, server CPU/IOPS tăng. | Admission/backoff/jitter, giảm fan-out. |
| API timeout nhưng write có thể commit | Unknown outcome. | Idempotency/verify operation state. |

### 20.3. Đừng restart toàn bộ pods vì một failover

Nếu health probe kill/restart tất cả pods khi MongoDB primary đang election, mỗi pod mới lại tạo client/pool/monitor sockets. Điều đó có thể **kéo dài thời gian phục hồi**. Nên phân biệt:

- **Liveness:** process/JVM còn hoạt động không?
- **Readiness:** có đủ điều kiện phục vụ traffic yêu cầu DB không?
- **Dependency availability:** primary/secondary đang reachable ở trạng thái nào?

Một service có thể **chưa ready** cho writes trong một đợt election ngắn nhưng vẫn là process khỏe mạnh; không nhất thiết cần restart.

### 20.4. Idle connections và firewall

Sau vài phút không traffic, firewall/NAT/load balancer có thể đóng TCP sockets. App vẫn nghĩ pool có idle sockets; operation đầu gặp read/write error, driver clear hoặc refresh connection. So sánh **network idle timeout** với `maxIdleTimeMS` và quan sát `connectionClosed` reasons; không tăng pool để giữ thêm sockets stale.

### 20.5. TLS/authentication cũng có thể là bottleneck

TLS handshakes và authentication tiêu tốn CPU/network. `maxConnecting=100` có thể làm pool warm nhanh hơn trên một client nhưng nhiều clients/pods cùng làm vậy gây handshake storm. Tuning cần quan sát:

- `ConnectionCreated` và `ConnectionReady` gap.
- CPU server/application/sidecar.
- TLS/auth failures.
- `connectTimeoutMS` và network RTT.
- Retry/connect rate sau failover.

### 20.6. Tách retryable reads/writes và manual retry

MongoDB Java Driver có `retryReads`/`retryWrites` theo hỗ trợ. Nếu application còn retry thêm 3 lần mà không phân biệt driver đã retry, một request user có thể tạo nhiều DB attempts. Khi overload:

\[
\mathrm{effectiveAttempts}
=\mathrm{originalRequests}\times
\mathrm{averageAttemptsPerRequest}
\]

Ví dụ 500 RPS, trung bình 1,4 attempts/request → 700 DB attempts/s (giả định một operation/request). Đây là **retry amplification**; cap attempts, deadline và exponential backoff with jitter giúp phục hồi.

### 20.7. Phân loại mã lỗi overload trong version mới

MongoDB 9.0+ có cơ chế **Intelligent Workload Management/load shedding** trên deployment được hỗ trợ; MongoDB Java Driver 5.8+ bổ sung cách xử lý retry/retargeting cho một số error labels như `SystemOverloadedError`/`RetryableError` theo docs. Đây là **version-dependent**, không tự suy code Java 5.2 đã nhận diện hết overload labels. Hãy xem tài liệu driver/server thực và hạn chế retry storm thay vì dùng retries vô hạn.

## 21. Thiết kế deadline theo SLO

### 21.1. Bắt đầu từ SLA người dùng

Giả sử API tìm order có SLO p95 400 ms:

~~~text
End-to-end HTTP budget     400 ms
  Auth/validation           40 ms
  App queue admission       40 ms
  MongoDB operation        240 ms
  Response transformation   30 ms
  Network/reserve           50 ms
~~~

Đây là **budget giả định**, không phải phép cộng p95 hợp lệ cho thống kê thực. Nó giúp thiết kế deadlines và phân phối thời gian. Nếu đã chờ 250 ms ở ingress, không nên cho MongoDB operation thêm 240 ms mà vẫn hứa trả trong 400 ms.

### 21.2. Dùng remaining deadline

~~~java
// Pseudocode: mỗi HTTP request có deadlineNanos đáng tin.
long nanosLeft = deadlineNanos - System.nanoTime();
if (nanosLeft <= 0) {
    throw new RequestDeadlineExceededException();
}

long millisLeft = Math.max(1,
    TimeUnit.NANOSECONDS.toMillis(nanosLeft));

// Chỉ tạo handle override khi driver hỗ trợ CSOT.
MongoCollection<Document> scoped =
    orders.withTimeout(millisLeft, TimeUnit.MILLISECONDS);

Document result = scoped.find(Filters.eq("_id", id)).first();
~~~

`deadlineNanos` phải được tạo dựa trên monotonic clock cùng process; không chuyển trực tiếp giữa hosts bằng `System.nanoTime()` vì origin khác nhau. `RequestDeadlineExceededException` là application class cần tự khai báo. Với external HTTP deadline timestamp, convert đáng tin sang remaining budget theo server clock policy.

### 21.3. Không chỉ dùng một timeout khổng lồ

Nếu để `serverSelectionTimeoutMS=30s`, `waitQueueTimeoutMS=120s`, `socketTimeoutMS=0` mà không có CSOT/HTTP deadline, một request đơn giản có thể treo lâu hơn user chịu được. Ngược lại, timeout 50 ms trên mạng có p99 80 ms sẽ tạo lỗi giả thường xuyên.

Chọn timeout từ:

1. **Business SLO** và mức độ quan trọng của operation.
2. Độ trễ bình thường p95/p99 theo region/query class.
3. Failover duration thường gặp.
4. Queue/pool saturation behavior.
5. Khả năng retry/idempotency.
6. Fallback policy và error budget.

### 21.4. Chọn HTTP status và retry hints

- `429 Too Many Requests` khi client/tenant vượt quota.
- `503 Service Unavailable` khi dependency tạm quá tải/không khả dụng.
- Deadline riêng có thể dẫn tới `504 Gateway Timeout` ở proxy/API gateway.

Đây là **mapping API policy**, không phải mapping 1–1 mọi MongoDB exception sang HTTP status. Tránh trả raw MongoDB exception có hostnames/credentials cho client. Nếu có `Retry-After`, clients phải có jitter và cap attempts.

### 21.5. Read-only vs writes

Read idempotent có thể được retry khi timeout/ngắt network theo driver semantics và deadline; writes có thể đã commit nên cần stable request IDs, retryable write support và verify outcome. Không retry:

~~~text
POST /orders with new _id each attempt
~~~

chỉ vì response timeout. Nếu dùng `_id`/unique business key ổn định, retry có thể xác định duplicate là cùng request và xử lý an toàn theo thiết kế.

## 22. Bounded concurrency quanh MongoDB Java Sync Driver

### 22.1. Pool cap không đủ để chống overload

~~~text
5000 HTTP requests arriving
        |
        v
5000 Java tasks waiting to checkout
        |
        v
MongoClient pool maxSize = 64
        |
        v
MongoDB server
~~~

Pool chỉ cho một số connections được checkout đồng thời; **5000 tasks vẫn đang giữ thread/future/request contexts**. Nếu server xử lý chậm, queue dài, timeout rồi retry có thể tạo vòng lặp overload.

### 22.2. Java semaphore có timeout

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class MongoReadGate {
    private final Semaphore permits = new Semaphore(24, true);
    private final MongoCollection<Document> orders;

    public MongoReadGate(MongoCollection<Document> orders) {
        this.orders = orders;
    }

    public Document findById(String id) throws InterruptedException {
        if (!permits.tryAcquire(30, TimeUnit.MILLISECONDS)) {
            throw new RejectedExecutionException(
                "MongoDB read admission full");
        }

        try {
            return orders.find(Filters.eq("_id", id)).first();
        } finally {
            permits.release();
        }
    }
}
~~~

**Cần imports** `MongoCollection`, `Document`, `Filters`, `RejectedExecutionException` và các classes application. Ví dụ minh họa admission trước DB call. `Semaphore(24,true)` không tự giới hạn số **callers đang chờ permit**; cần bounded HTTP/executor queue ở ngoài.

### 22.3. Bounded executor

~~~java
ThreadPoolExecutor dbExecutor = new ThreadPoolExecutor(
    12, 12,
    0L, TimeUnit.MILLISECONDS,
    new ArrayBlockingQueue<>(48),
    new ThreadPoolExecutor.AbortPolicy()
);
~~~

Khi 12 tasks chạy + 48 đang đợi, task mới bị reject thay vì nằm vô hạn. Tránh `Executors.newFixedThreadPool` cho workload mất kiểm soát nếu nó dùng unbounded queue. Nếu dùng virtual threads/reactive, **số in-flight DB operations vẫn phải được giới hạn**.

### 22.4. Local limit khác global limit

Nếu mỗi pod có 24 permits và HPA lên 30 pods, trần local tổng tới **720 concurrent calls** trên toàn deployment, không phải 24. Với multi-tenant fairness/global DB budget, cần điều phối ở gateway/distributed rate limiter hoặc phân bổ cap theo replica count.

### 22.5. Chia workloads

Một batch export giữ connections rất lâu có thể khiến point lookup API timeout:

~~~text
Interactive API:
  MongoClient A
  gate=32
  pool max=48
  short deadline

Background reports:
  MongoClient B
  gate=4
  pool max=8
  longer deadline
~~~

Hai clients tạo **hai pools trên mỗi server**, phải tính tổng connections. Pool isolation giúp hạn chế checkout starvation, nhưng **không tách CPU/IOPS phía DB**; cần tối ưu query, scheduling, materialized summaries hoặc cluster separation khi cần.

## 23. Quy trình tuning pool và server selection theo số đo

### 23.1. Thu metrics trước

Lập dashboard gồm:

| Phạm vi | Metric |
|---|---|
| HTTP/app | Arrival RPS, completed RPS, p95/p99, timeout/rejection, queue depth. |
| Driver pool | `maxSize`, `size`, `checkedOutCount`, checkout wait p95/p99, checkout failures, created/closed/cleared rates. |
| Driver SDAM | Server selection failures, topology changes, heartbeat failures, eligible servers. |
| Driver command | Command p50/p95/p99, retries, errors theo command type. |
| MongoDB server | CPU, memory, WiredTiger cache, disk IOPS, `connections.current/active`, lock/queues. |
| Deployment | Number of pods/clients, TLS handshake rate, network latency, HPA events. |

### 23.2. Tăng tải từng bước

~~~text
Request rate: 100 -> 200 -> 400 -> 600 -> 800 req/s
For each stage observe:
  completed throughput
  checkout wait
  server selection time
  command time
  HTTP p99 and error rate
~~~

Các số chỉ là **kịch bản lab**, không nên chạy trên production không có kế hoạch. Test cả **open-loop fixed arrivals** để nhìn queue growth khi load vượt capacity và **closed-loop user sessions** để đánh giá experience.

### 23.3. Tìm knee point

| Incoming RPS | Completed RPS | HTTP p95 | Checkout p95 | Server CPU |
|---:|---:|---:|---:|---:|
| 100 | 100 | 70 ms | 2 ms | 22% |
| 300 | 300 | 95 ms | 5 ms | 45% |
| 500 | 500 | 145 ms | 18 ms | 76% |
| 700 | 610 | 700 ms | 200 ms | 96% |
| 900 | 615 | 2.200 ms | 500 ms | 99% |

**Giả định:** Completed throughput bão hòa khoảng 610–615 RPS, latency tăng mạnh. Nếu chỉ tăng pool, DB đang CPU gần 100% có thể chậm hơn. Nên:

1. Giảm concurrency/queue khi overload.
2. Sửa expensive query/indexes.
3. Tăng DB capacity nếu nhu cầu bền vững thật sự vượt ngưỡng.
4. Chọn pool size với headroom, không nhìn một con số từ demo.

### 23.4. Khi nào tăng `maxPoolSize` hợp lý?

Khi:

- `checkedOutCount` sát `maxSize` liên tục.
- Checkout wait p95/p99 đáng kể.
- Query/command execution nhanh, server CPU/IOPS **còn headroom**.
- Không có connection creation/network issue.
- Admission/request budget phù hợp để không làm server quá tải.

Khi đó thử tăng **từng bước** và đo throughput/latency/error, luôn tính tổng trần connections khi autoscaling.

### 23.5. Khi nào giảm pool/concurrency?

Khi:

- Command time p99 tăng khi concurrency tăng.
- Server CPU/IOPS/cache eviction near saturation.
- Retry amplification làm attempts vượt demand.
- Long aggregations/cursors chiếm tài nguyên.
- Pod count tăng đột ngột nhưng DB capacity không đổi.

Giảm admission giúp bảo vệ tail latency của requests được nhận, nhưng có thể tăng **rejected rate**; phải chọn theo product SLO, không coi mọi rejection là sai.

### 23.6. `maxConnecting` cần test riêng

Sau cold start/failover, đo:

- Thời gian pool đạt occupancy cần thiết.
- `ConnectionCreated` → `ConnectionReady` duration.
- TLS/auth CPU.
- Checkout latency.
- Server rejected connection count.

Tăng `maxConnecting` từ 2 lên 8 có thể cải thiện ramp-up trong một deployment nhưng tạo handshake spikes ở deployment khác. Không tự đặt 100 cho 50 pods cùng start.

### 23.7. Replica set tags và latency tuning

Nếu readPreference là `secondary` nhưng server selection time cao:

1. Kiểm eligible secondary còn alive không.
2. Kiểm tag sets có match member nào không.
3. Kiểm maxStalenessSeconds có loại hết secondaries không.
4. Kiểm `localThresholdMS`: có members nằm trong latency window không.
5. Kiểm network RTT, TLS, DNS, serverMonitoringMode/heartbeat events.

**Không** chỉ nới serverSelectionTimeout lên 120 giây rồi coi vấn đề đã được giải quyết; SLO có thể không chấp nhận chờ lâu vậy.

### 23.8. Runbook lỗi theo stage

~~~text
Request slow / timeout
       |
       +-- No server suitable?
       |      -> SDAM, election, replicaSet, DNS, TLS,
       |         read preference, tags, staleness
       |
       +-- Server selected, checkout slow?
       |      -> CMAP checkedOut/maxSize, maxConnecting,
       |         pool clear, idle sockets, MongoClient count
       |
       +-- Checkout fast, command slow?
       |      -> MongoDB profiler/explain, CPU/IOPS,
       |         locks, cache, shard routing
       |
       +-- Command fast, HTTP slow?
       |      -> app queue, GC, transformation,
       |         downstream calls, network
       |
       +-- Write result uncertain?
              -> retryable write semantics, stable IDs,
                 verify outcome, don't blindly duplicate
~~~

## 24. Mô hình thực hành: ba kiểu lỗi có cùng “timeout”

### 24.1. Lỗi A — Không có primary

~~~text
Cluster:
  db1 UNKNOWN (network down)
  db2 SECONDARY
  db3 SECONDARY
Read preference: primary
~~~

Mặc dù secondary pools có idle connections, một read theo `primary` có thể không có eligible server. Driver đợi selection rồi `MongoTimeoutException`; **tăng maxPoolSize từ 100 lên 500 không giúp**.

**Cách xử lý:** kiểm election/network, lựa chọn read preference theo business consistency (chỉ với reads) hoặc áp deadline/fallback.

### 24.2. Lỗi B — Có primary nhưng pool đầy

~~~text
Primary healthy; RTT 5 ms
Pool maxSize 20
Checked-out count 20
20 long aggregations đang chạy
New find request wants connection
~~~

Server selection nhanh nhưng checkout chờ. Tăng pool có thể giúp nếu server còn headroom, nhưng long aggregation có thể làm CPU/IOPS saturated. Cần **CMAP + server metrics**; thường giới hạn reports và tối ưu query trước.

### 24.3. Lỗi C — Pool rảnh nhưng query chậm

~~~text
Primary healthy
Pool size 40, checked-out 5
New find gets connection in 1 ms
Execution 10 seconds (COLLSCAN + SORT)
~~~

Driver pool không bottleneck. Kiểm `explain`, index, filter selectivity, sort, server resources; dùng `maxTimeMS`/CSOT phù hợp để giới hạn thời gian khi cần.

### 24.4. Lỗi D — Cold pool / connection creation bottleneck

~~~text
Pod just started
Pool maxSize=100, size=0
maxConnecting=2
100 operations arrive
TLS/auth handshake takes 100 ms each
~~~

Checkout wait có thể cao dù pool chưa đạt max. Cần warmup/rollout staggered, đo establishment, cân nhắc `maxConnecting` có kiểm soát; **không** tự đặt `maxPoolSize=1000`.

### 24.5. Lỗi E — Timeout write sau server commit

~~~text
Client sends insert _id=ORD-101
Server writes document
Response lost due to network
Client sees timeout
~~~

**Không retry bằng `_id=ORD-102`** nếu đây là cùng business request. Dùng idempotent key, retryable write semantics, kiểm trạng thái/transaction outcome.

## 25. Lab an toàn: quan sát pool/selection/timeout trên replica set test

Lab yêu cầu một MongoDB replica set **riêng được phép**, Java 17+ (hoặc JDK phù hợp driver version), MongoDB Java Sync Driver 5.x và endpoint trong mạng lab. Không gây failover, chặn mạng hay tạo tải cao trên production chỉ để nhìn exception.

### 25.1. Mục tiêu lab

1. Tạo một `MongoClient` với pool size có giới hạn.
2. Đăng ký JMX/CMAP để xem `size` và `checkedOutCount`.
3. Chạy `find()` bình thường; quan sát initial connection creation.
4. Gửi nhiều tasks đồng thời **có giới hạn** để thấy checkout wait.
5. Thử URI sai/`primary` không reachable trên cluster **lab**.
6. Chọn CSOT khác nhau và xem ảnh hưởng tới selected stage.
7. Không suy performance production từ fixture nhỏ.

### 25.2. Khởi tạo dữ liệu thử

Trong `mongosh` kết nối replica set **lab**:

~~~javascript
const lab = db.getSiblingDB("java_pool_lab")
lab.orders.insertMany([
  { _id: "O-1", tenantId: "A", status: "OPEN", amount: 100 },
  { _id: "O-2", tenantId: "A", status: "PAID", amount: 200 },
  { _id: "O-3", tenantId: "B", status: "OPEN", amount: 150 }
])
lab.orders.createIndex({ tenantId: 1, status: 1 })
~~~

Chạy một lần; lần sau sẽ gặp duplicate `_id`. Dữ liệu không đủ lớn để gây checkout contention rõ nét nếu query chỉ mất vài ms; muốn thấy wait cần **test harness có concurrency controlled** hoặc server-side delay trên lab với đánh giá resource.

### 25.3. Lệnh build dependency

Ví dụ Gradle project **tham khảo**, version cần chọn theo ứng dụng của bạn:

~~~groovy
dependencies {
    implementation 'org.mongodb:mongodb-driver-sync:5.8.0'
}
~~~

Version nêu ở đây minh họa dòng 5.x khi bài được viết; không áp dụng mù nếu project có BOM/Java compatibility constraints. Worker STEP 4 **không chạy Gradle**; đây là nội dung hướng dẫn người học tạo lab sau này.

### 25.4. Java demo với JMX listener

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.management.JMXConnectionPoolListener;
import org.bson.Document;
import java.util.concurrent.TimeUnit;

public final class PoolLab {
    public static void main(String[] args) {
        String uri = System.getenv("MONGO_LAB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException("MONGO_LAB_URI required");
        }

        JMXConnectionPoolListener jmx = new JMXConnectionPoolListener();

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .applicationName("pool-timeout-lab")
            .applyToConnectionPoolSettings(pool -> pool
                .maxSize(4)
                .minSize(0)
                .maxConnecting(2)
                .addConnectionPoolListener(jmx))
            .applyToClusterSettings(cluster -> cluster
                .serverSelectionTimeout(3, TimeUnit.SECONDS))
            .build();

        try (MongoClient client = MongoClients.create(settings)) {
            MongoCollection<Document> orders = client
                .getDatabase("java_pool_lab")
                .getCollection("orders");

            System.out.println(
                orders.find(Filters.eq("_id", "O-1")).first());

            // Inspect via JConsole while process still lives:
            // use a debugger or a controlled temporary pause in lab.
        }
    }
}
~~~

Đoạn này sẽ **đóng client ngay sau query**, nên để xem JMX trong JConsole người học cần giữ process sống bằng breakpoint/controlled pause trong **lab**, không thêm vòng busy-wait vô hạn. Không để một MongoClient test sống mãi sau khi bài lab kết thúc.

### 25.5. Đừng dùng production secrets trong log

Sử dụng biến môi trường `MONGO_LAB_URI` hoặc secret manager; nếu cần TLS CA/truststore, cấu hình theo deployment. Không print nguyên URI vì có thể chứa credentials. Khi gửi lỗi cho reviewer, redact user/password/hostnames nhạy cảm.

### 25.6. Đo tác động của pool size

Trên lab:

1. Chạy test có **ít task và deadline**.
2. Bắt đầu với `maxPoolSize=4`.
3. Ghi checkout wait/checked-out count.
4. Thử `maxPoolSize=8`, giữ nguyên workload/query/index.
5. So command time/CPU/throughput trước–sau.
6. Nếu server command time tăng, không kết luận pool 8 tốt hơn chỉ vì ít checkout wait.

### 25.7. Kiểm tra timeout có kiểm soát

- Dùng `serverSelectionTimeoutMS` ngắn hơn **trên lab** với host unreachable để quan sát cluster selection error.
- Dùng low pool cap + bounded concurrent operations để quan sát checkout wait/failures.
- Dùng query không có index trên **dataset nhỏ/lab** và `maxTime` để thấy server time limit theo phép thử phù hợp; không chạy aggregation cực nặng để ép server production.
- Dùng CSOT trên driver được hỗ trợ và so sự khác biệt khi selection/checkout/command chậm.

Lab về timeout cần **đọc loại exception** và events; không phải mục đích tạo workload phá hoại.

### 25.8. Kết quả mong đợi về mặt cơ chế

| Thử nghiệm | Dấu hiệu chính |
|---|---|
| Không có primary eligible | SDAM/`ReadPreferenceServerSelector` exception. |
| Pool cap nhỏ và nhiều concurrent calls | CMAP checkout wait/failed events. |
| Query chậm nhưng pool còn idle | Command latency cao, checkout wait thấp. |
| Cold start với `maxConnecting` thấp | Connection created/ready theo tốc độ có giới hạn. |
| CSOT nhỏ hơn tổng MongoDB call time | Client operation timeout trước khi toàn bộ công việc hoàn tất. |

Không có con số latency “chuẩn” cho mọi máy; tiêu chí lab là **phân biệt đúng stage**.

## 26. Những nhầm lẫn dễ gây lỗi production

| Nhầm lẫn | Vấn đề | Hiểu đúng |
|---|---|---|
| “`maxPoolSize=100` là toàn cluster.” | Driver có pool cho mỗi server. | Tính per server × client × pods. |
| “Có 100 sockets là có 100 active queries.” | Sockets có thể idle. | Xem checked-out/`connections.active`. |
| “Client tạo nhẹ, tạo mỗi request được.” | Topology/pool/TLS/auth tốn tài nguyên. | Reuse MongoClient. |
| “Server selection và checkout là một.” | Chọn eligible server xảy ra trước mượn socket. | Đo SDAM và CMAP riêng. |
| “Selection timeout chứng minh pool full.” | Có thể không có primary/secondary phù hợp. | Đọc cluster description/read preference. |
| “Connect timeout là thời gian chờ pool.” | Connect là mở socket mới. | Xem `connectTimeoutMS` vs checkout wait. |
| “Socket timeout là DB max execution time.” | Socket đọc/ghi khác command runtime. | `maxTimeMS`/CSOT và command timing. |
| “`maxTimeMS` bao toàn HTTP request.” | Không tính app queue/selection/checkout. | End-to-end deadline. |
| “`waitQueueTimeoutMS=5s` giới hạn 5.000 waiters.” | Đơn vị là thời gian, không phải số lượng. | Bounded queue ở application. |
| “Legacy timeout và CSOT luôn cộng dồn.” | Java docs ghi nhiều legacy options ignored với CSOT. | Chọn một mô hình có ý thức. |
| “`timeoutMS=0` nghĩa là timeout ngay.” | Trong CSOT, 0 nghĩa là không timeout. | Dùng positive timeout theo SLO. |
| “Read preference secondary chuyển writes sang secondary.” | Writes cần writable primary. | Read preference chủ yếu cho reads. |
| “`nearest` bảo đảm dữ liệu mới nhất.” | Dựa RTT, không phải freshness. | Read concern/business consistency riêng. |
| “`localThresholdMS=15` bắt buộc chọn RTT thấp nhất.” | Có latency window gồm nhiều eligible servers. | Hiểu selection sau role/tags/staleness. |
| “`directConnection=true` vẫn có HA như replica set URI.” | Single-server mode không tự khám phá/route tương đương. | Dùng replicaSet/SRV URI cho HA. |
| “Chỉ cần seed host reachable.” | Members advertised có thể không reachable. | DNS/network từ client tới mọi endpoints cần thiết. |
| “`maxConnecting=2` nghĩa pool chỉ có 2 connections.” | Giới hạn establishment **đồng thời**, không phải max pool. | Phân biệt maxConnecting và maxPoolSize. |
| “Tăng minPool chắc chắn giảm mọi timeout.” | Có thể tạo connection storm hoặc không liên quan selection. | Warmup có đo. |
| “Idle timeout là operation timeout.” | Quản lý vòng đời socket. | `maxIdleTimeMS` khác CSOT. |
| “Timeout write = write chắc chắn thất bại.” | Server có thể commit trước khi response mất. | Idempotency/verify outcome. |
| “Retry toàn bộ transaction callback luôn an toàn.” | External side effects có thể lặp. | Outbox/idempotent external operations. |
| “Pool full cứ tăng 10 lần là tốt.” | DB CPU/IOPS có thể đã saturated. | Đo server headroom và query plan. |
| “Có CSOT thì không cần HTTP deadline.” | CSOT không tính toàn app queue/processing. | Absolute request deadline. |
| “Reactive/virtual threads làm DB concurrency vô hạn.” | Server và pool vẫn giới hạn. | Admission control/queue bounds. |
| “JMX checkoutSuccess là current checked out.” | Event count tích lũy khác gauge. | JMX `checkedOutCount` hoặc matched events. |
| “`serverStatus.connections.current` là pool một client.” | Server gồm mọi clients và monitors. | Driver per-pool metrics. |
| “Một exception string là stable API.” | Error messages/version thay đổi. | Class/code/labels + instrumentation. |
| “`maxTimeMS` error => network problem.” | Thường server-side execution exceeded. | Query plan/server metrics. |
| “No primary => restart mọi pods.” | Tạo reconnect storm sau election. | Readiness/backoff/SDAM. |
| “Retry nhiều sẽ khỏi timeout.” | Retry amplification làm overload nặng hơn. | Attempts cap/jitter/deadline. |
| “Thêm pool size nâng CPU database.” | Connections không tạo server capacity. | Tối ưu query/scale DB. |

### 26.1. Checklist chẩn đoán 60 giây đầu

1. Exception class và đoạn message nào: selection/checkout/socket/server?
2. Cluster description có eligible server không?
3. Driver đang dùng read preference nào và có tags/staleness filters không?
4. `MongoClient` có đúng singleton và cấu hình pool thực tế là gì?
5. Checked-out/maxSize và checkout wait như thế nào?
6. Có connection created/closed/cleared tăng đột biến không?
7. Command p99/server CPU/IOPS có chậm không?
8. CSOT hay legacy timeout đang có hiệu lực?
9. Requests có retry/duplicate risk không?
10. HTTP deadline/availability SLO có còn đạt không?

## 27. Bài tập thực hành có đáp án

Các bài tập có số liệu **giả định**, không phải kết quả benchmark hay sự cố thật. Khi bài nhắc failover/network fault/load test, chỉ thao tác trên cluster **lab hoặc staging được cấp phép**. Mục tiêu là chọn đúng cơ chế Java Driver, không phải cố gây timeout để “chứng minh” performance.

### Bài 1 — MongoClient per request

**Đề:** Một controller gọi `MongoClients.create(uri)` cho từng HTTP request rồi `close()` ngay. Có vấn đề gì?

**Đáp án:** Mỗi request lặp topology discovery, pool lifecycle, socket/TLS/auth handshakes, tốn CPU/network, tăng latency và connection churn. Tạo MongoClient singleton dài hạn theo app/service lifecycle; repositories dùng chung client thread-safe.

### Bài 2 — Max pool theo server

**Đề:** Một MongoClient kết nối replica set 3 nodes với `maxPoolSize=100`. Có đúng tổng các pooled connections luôn tối đa 100 không?

**Đáp án:** Không. Có **pool riêng cho mỗi member**, mỗi pool tối đa 100; số thực mở tùy read preference/traffic. Monitoring sockets nằm ngoài maxPoolSize. Đây là trần tiềm năng, không phải số sockets đang mở.

### Bài 3 — Tính budget tới primary

**Đề:** 20 pods, mỗi pod 1 MongoClient, `maxPoolSize=80`, mọi writes tới cùng primary. Trần app pooled connections tới primary?

**Đáp án:** \(20\times80=1.600\) connections; cộng monitoring/clients khác khi capacity planning. Không kết luận luôn có 1.600 active commands.

### Bài 4 — Hai clients mỗi pod

**Đề:** 12 pods, mỗi pod 2 MongoClients, maxSize=64/client/server. Cả hai clients đều dùng primary. Trần pooled connections tới primary?

**Đáp án:** \(12\times2\times64=1.536\). Cân nhắc tách clients theo workload có chủ đích nhưng phải tính tổng budget.

### Bài 5 — MaxConnecting

**Đề:** Pool `maxPoolSize=100`, `maxConnecting=2`. Có phải pool chỉ chứa tối đa hai connections?

**Đáp án:** Không. `maxConnecting` giới hạn số connections **đang được thiết lập đồng thời**, còn pool có thể mở tới 100. Cold start có thể bị giới hạn bởi establish rate.

### Bài 6 — MinPoolSize

**Đề:** HPA đồng thời start 100 pods với `minPoolSize=50`. Có rủi ro gì?

**Đáp án:** Các pods có thể đồng loạt warm pools, tạo thousands TCP/TLS/auth handshakes, gây connection storm. Giảm min nếu không cần, stagger rollout, kiểm maxConnecting/readiness, đo created/ready rates.

### Bài 7 — Idle time

**Đề:** Firewall đóng socket idle sau 5 phút, driver giữ idle connections vô hạn. Có thể gặp gì sau giờ thấp tải?

**Đáp án:** Driver checkout stale sockets rồi gặp socket errors, pool clear/reconnect. Đặt `maxIdleTimeMS` có kiểm soát thấp hơn network idle timeout theo docs và kiểm reconnect/CPU trade-off.

### Bài 8 — Connection lifetime

**Đề:** Một developer đặt `maxLifeTimeMS=500` để query chậm bị ngắt sau 500 ms. Có đúng không?

**Đáp án:** Không. `maxLifeTimeMS` là giới hạn lifecycle **connection**, không phải timeout operation. Dùng server-side `maxTimeMS` hoặc CSOT/HTTP deadline tùy mục tiêu.

### Bài 9 — Connection checkout queue

**Đề:** Pool max=10, 10 operations đã checked out, operation thứ 11 tới. Chuyện gì?

**Đáp án:** Operation mới chờ checkout connection available (hoặc deadline/timeout), không tự tạo connection thứ 11 vượt max cho server đó. Theo dõi CMAP wait/failed events.

### Bài 10 — `waitQueueTimeoutMS`

**Đề:** Đặt `waitQueueTimeoutMS=5.000` có giới hạn queue tối đa 5.000 tasks không?

**Đáp án:** Không. Đây là **milliseconds** chờ connection (legacy), không phải số tasks. Dùng bounded admission/queue để giới hạn pending requests.

### Bài 11 — Cấu hình CSOT + waitQueueTimeout

**Đề:** Java Driver 5.x có `timeoutMS=800` và `waitQueueTimeoutMS=10.000`. Có được chờ pool 10 giây?

**Đáp án:** Không nên suy vậy. Theo CSOT docs, `timeoutMS` là operation deadline, legacy `waitQueueTimeoutMS` bị ignore khi CSOT được set. Kiểm version/override precedence.

### Bài 12 — `timeoutMS=0`

**Đề:** Trong CSOT, `timeoutMS=0` có khiến MongoDB operation fail ngay khi bắt đầu không?

**Đáp án:** Không. Trong Java Driver CSOT docs, `0` nghĩa **không timeout** theo option đó. Dùng positive timeout để áp deadline.

### Bài 13 — Server selection

**Đề:** Driver thấy một secondary healthy nhưng không có primary; request read dùng `ReadPreference.primary()` và timeout. Tăng pool có giải quyết không?

**Đáp án:** Không. Thiếu **eligible server**. Kiểm election/network/SDAM. Nếu business cho phép stale reads, có thể cân nhắc read preference khác cho **read operation**, không biến write thành secondary write.

### Bài 14 — `serverSelectionTimeoutMS`

**Đề:** `serverSelectionTimeoutMS=30.000`. Một request có SLO 200 ms, primary mất 3 giây khi failover. Có hợp lý cho HTTP thread chờ hết 30 giây?

**Đáp án:** Thường không. Cần deadline end-to-end/CSOT nhỏ hơn theo SLO, fallback/reject có kiểm soát; tránh để request client timeout từ lâu nhưng worker vẫn chờ.

### Bài 15 — Connect timeout

**Đề:** TCP connect tới db1 bị firewall chặn. `maxPoolSize` đang 200 nhưng ứng dụng báo `MongoSocketOpenException`. Nên tăng maxPoolSize?

**Đáp án:** Không. Kiểm DNS/port/firewall/security group/TLS/certificate, `connectTimeoutMS` và socket establishment; pool capacity không tạo network connectivity.

### Bài 16 — Socket timeout

**Đề:** Query aggregation cần 5 giây nhưng `socketTimeoutMS=1.000`. Sau 1 giây client lỗi. Có chắc aggregation chưa chạy?

**Đáp án:** Không. Server có thể đang thực thi; socket read timeout là việc client không nhận response kịp. Tối ưu aggregation, dùng `maxTimeMS`/CSOT phù hợp, không retry đắt tiền vô hạn.

### Bài 17 — Server-side maxTime

**Đề:** `find().maxTime(500ms)` nhưng request chờ pool 2 giây, server chạy 100 ms. Có thể HTTP vẫn mất trên 2 giây không?

**Đáp án:** Có. `maxTimeMS` chỉ giới hạn server execution, không tính pool checkout. Dùng end-to-end deadline/CSOT và admission policy.

### Bài 18 — Majority write timeout

**Đề:** `insertOne` được primary ghi nhưng majority acknowledgement không kịp `wtimeout`. Có thể retry ngay bằng `_id` khác không?

**Đáp án:** Không. `wtimeout` không chứng minh write chưa áp dụng. Cần stable idempotency key, retryable writes/verify outcome.

### Bài 19 — Read preference secondary

**Đề:** App cần đọc ngay order vừa ghi vào primary. Có nên chuyển sang `secondaryPreferred` chỉ vì primary đang bận?

**Đáp án:** Chỉ nếu chấp nhận replication lag/stale read theo business. Nếu cần read-after-write consistency mạnh, secondary có thể không phù hợp. Tối ưu primary/query/capacity trước.

### Bài 20 — Nearest

**Đề:** `ReadPreference.nearest()` có đảm bảo luôn đọc primary gần nhất và dữ liệu mới nhất không?

**Đáp án:** Không. `nearest` cho phép eligible primary/secondary trong RTT latency window; không có bảo đảm freshness. Cần read concern/read preference/consistency policy riêng.

### Bài 21 — Latency window

**Đề:** Ba eligible secondaries có RTT lần lượt 8, 17 và 27 ms. `localThresholdMS=15`. Những nodes nào ở trong latency window?

**Đáp án:** RTT phải ≤8+15=23 ms, nên **node 8 ms và 17 ms** eligible; 27 ms ngoài cửa sổ. Driver không nhất thiết luôn chọn 8 ms.

### Bài 22 — Latency window sau tags

**Đề:** Node nhanh nhất RTT 5 ms có tag `region:us`, còn request chỉ cho `region:ap`. Node AP RTT 40 ms. Có nên chọn node US?

**Đáp án:** Không nếu tag filter là yêu cầu bắt buộc. **Lọc eligible theo tags/read preference trước**, rồi mới xét latency window trên tập còn lại. Hãy xác minh danh sách eligible members và tag sets.

### Bài 23 — Max staleness

**Đề:** Một secondary lag nhiều phút. Đặt maxStalenessSeconds có bảo đảm dữ liệu chính xác “không quá 60 giây” cho mọi operation không?

**Đáp án:** Không. Driver dùng ước lượng replication staleness và MongoDB có giới hạn giá trị tối thiểu theo monitoring/version; 60 giây có thể không hợp lệ. Với yêu cầu nhất quán mạnh, cần thiết kế read/write concern và business workflow.

### Bài 24 — Direct connection

**Đề:** Để “tăng HA”, developer đặt `directConnection=true` tới duy nhất primary cũ. Khi primary stepdown thì driver có tự chuyển như replica-set URI đầy đủ không?

**Đáp án:** Không nên kỳ vọng. Direct mode ép single-server interaction; production replica-set HA cần discovery qua seed list/replicaSet hoặc Atlas SRV URI phù hợp.

### Bài 25 — Advertised hostnames

**Đề:** App kết nối `localhost:27017` trong Docker, nhưng replica set config báo members `mongo1:27017`/`mongo2:27017` mà host OS không resolve được. Lỗi?

**Đáp án:** Driver khám phá các member addresses không reachable, có thể server selection fail. Cần sửa network addressing/replica set config theo deployment đã phê duyệt hoặc dùng connection setup phù hợp; không chỉ tăng `serverSelectionTimeoutMS`.

### Bài 26 — CSOT inheritance

**Đề:** Client timeout 800 ms, collection handle gọi `withTimeout(2s)`. Query qua collection đó có nhất thiết bị giới hạn 800 ms không?

**Đáp án:** Theo CSOT override semantics, collection timeout **2 giây** ghi đè client-level 800 ms cho operations trên handle đó, trừ khi có timeout cụ thể hơn. Nhưng HTTP deadline vẫn độc lập.

### Bài 27 — HTTP request đã chờ 700 ms

**Đề:** HTTP deadline 1 giây, request đã chờ 700 ms ở upstream. Service bắt đầu MongoDB call với CSOT 800 ms. Có thể vi phạm deadline không?

**Đáp án:** Có. Chỉ còn ~300 ms trước HTTP deadline, chưa tính response processing. Nên truyền **remaining deadline** vào DB call hoặc reject sớm; CSOT không tính thời gian trước driver.

### Bài 28 — Cursor timeout mode

**Đề:** Cursor đọc 100 batches, mỗi batch nhanh 50 ms nhưng tổng 5 giây. `CURSOR_LIFETIME` 1 giây và `ITERATION` 1 giây có cùng tác dụng không?

**Đáp án:** Không. CURSOR_LIFETIME giới hạn tổng lifetime, có thể hết hạn sau ~1 giây; ITERATION áp budget từng call/iteration theo docs, có thể cho cursor tiếp tục nếu từng call đủ nhanh. Kiểm model driver/version và dọn cursor.

### Bài 29 — Tailable cursor và change stream

**Đề:** Change stream cần chạy lâu dài. Có nên dùng cursor lifetime CSOT 2 giây rồi cho nó chạy 24 giờ?

**Đáp án:** Không. Với long-lived/tailable cursor, dùng iteration timeout/resume policy phù hợp, checkpoint resume token, handle disconnect; tránh lifetime deadline ngắn làm stream chết liên tục. Không quên quyền và resource cleanup.

### Bài 30 — JMX `checkedOutCount`

**Đề:** Pool `size=60`, `checkedOutCount=55`, `maxSize=64`, checkout wait p99=250 ms. Bạn cần kiểm gì?

**Đáp án:** Pool gần cap; xem command duration, long transactions/cursors, server CPU/IOPS, created/closed/cleared rate. Có thể thử tăng cap nhỏ **nếu server còn headroom**, hoặc giảm concurrency/optimize queries nếu server saturated.

### Bài 31 — JMX vs serverStatus

**Đề:** `serverStatus.connections.current=3.000`, nhưng Java pool `checkedOutCount=12`. Có phải Java listener sai?

**Đáp án:** Không nhất thiết. `current` đo toàn server từ nhiều clients/sockets idle/monitors, JMX đo một pool của một MongoClient. So phạm vi metrics trước.

### Bài 32 — Commands nhanh nhưng API chậm

**Đề:** CommandListener đo `find` p99=15 ms, HTTP p99=400 ms. Nên tăng DB CPU?

**Đáp án:** Chưa có bằng chứng. Tách HTTP queue/admission, server selection, CMAP checkout, JVM GC, response serialization và network. MongoDB command execution chỉ là một phần latency.

### Bài 33 — SDAM event

**Đề:** Lúc 10:00 cluster description đổi PRIMARY → UNKNOWN, 10:01 SECONDARY → PRIMARY, trong khoảng này writes timeout ở selection. Điều đó có hợp lý?

**Đáp án:** Có thể là election/topology transition. Kiểm server logs/SDAM, failover duration, deadline/retry policy; không kết luận pool thiếu.

### Bài 34 — Pool clear

**Đề:** Sau network glitch, `connectionPoolCleared` tăng và checkout wait tăng dù `maxPoolSize=100`, `size` thấp. Vì sao?

**Đáp án:** Pool bị clear/invalidate và phải tạo lại connections; `maxConnecting`/TLS/network chi phối ramp-up. Tối ưu reconnect/warmup, không chỉ nâng maxSize.

### Bài 35 — Command execution tăng theo pool

**Đề:** Pool tăng 50→200, checkout wait giảm nhưng command p99 tăng từ 100 ms lên 900 ms, DB CPU 98%. Có nên giữ 200?

**Đáp án:** Chưa chắc; nhiều operations song song đang bão hòa server. Đánh giá throughput + HTTP p99 + rejection + DB resource, cân nhắc hạ pool/admission, tối ưu query/scale DB.

### Bài 36 — Server selection 30 giây

**Đề:** Một application test kết nối URI `replicaSet=rsWrong` nên timeout selection sau ~30 giây. Có nên đổi thành 120 giây để nó thành công?

**Đáp án:** Không. Sửa replica set name/URI/network. Timeout dài hơn chỉ kéo dài thời gian báo lỗi cấu hình.

### Bài 37 — Retry write và duplicate order

**Đề:** API tạo order với random `_id` mới sau mỗi `MongoSocketReadTimeoutException`. Có thể xảy ra gì?

**Đáp án:** Server có thể đã ghi order ở attempt trước, làm duplicate khi retry. Dùng stable idempotencyKey, unique business key, retryable writes và verify outcome.

### Bài 38 — N+1 queries

**Đề:** Một HTTP request gọi 200 `findOne` nối tiếp. Pool gần như không chờ nhưng response chậm. Tăng pool giúp không?

**Đáp án:** Không nhiều nếu queries nối tiếp và network roundtrip chi phối. Cân nhắc bounded `$in` batch/projection hoặc query design khác, đo; pooling không làm 200 sequential roundtrips biến mất.

### Bài 39 — Bounded queue

**Đề:** Service dùng `Executors.newFixedThreadPool(16)` và nhận 100.000 tasks. Nó chỉ giữ tối đa 16 tasks trong JVM không?

**Đáp án:** Không. Fixed thread pool có **unbounded task queue** mặc định. Cần `ThreadPoolExecutor` với `ArrayBlockingQueue`, reject/degrade có kiểm soát, timeout end-to-end.

### Bài 40 — Thiết kế chẩn đoán một incident production

**Đề:** Một ứng dụng 25 pods dùng Java Driver 5.x, mỗi pod MongoClient pool max100, HTTP p99 tăng sau failover. Logs có `MongoTimeoutException` nhưng chưa rõ stage; request writes có retries. Hãy nêu kế hoạch chẩn đoán và khắc phục.

**Đáp án gợi ý:**

1. Tính trần pooled connections tới primary: `25×100=2.500`, cộng monitors/other clients.
2. Thu exception class, error code/labels và **cluster description đã redact** để phân biệt server selection, checkout, socket, server execution.
3. Xem SDAM timeline: primary election, host reachability, TLS/DNS, read preferences.
4. Xem CMAP: pool clear, connection created/ready, checkout wait, checkedOut/maxSize, maxConnecting.
5. Xem command p95/p99 và serverStatus CPU/IOPS/connections/queues; đừng kết luận từ HTTP p99 đơn lẻ.
6. Kiểm application restarts/HPA và số MongoClient instances thực; tránh reconnect storm.
7. Kiểm retryReads/retryWrites và manual retries, total attempt rate, jitter/attempt caps.
8. Đặt deadline từ ingress tới MongoDB: CSOT hoặc legacy timeout model theo driver version, không cộng vô thức.
9. Bảo đảm stable idempotency keys/transaction outcome handling cho writes có kết quả không rõ.
10. Dùng canary/controlled load test để tune `maxPoolSize`, `maxConnecting`, admission cap và rollback; đo completed throughput/p95/p99, timeout/rejection, recovery.

Một câu trả lời đúng không thể chỉ là “tăng `maxPoolSize` lên 500”. Cần **bằng chứng stage bị chậm, target SLO và biện pháp phù hợp với bottleneck**.

## 28. Bảng tra cứu nhanh cho Java developer

### 28.1. Chọn option theo câu hỏi

| Bạn muốn kiểm soát | Cấu hình/API cần đọc | Điều không nên nhầm |
|---|---|---|
| Số pooled connections tối đa trên **một server** | `maxPoolSize` / `maxSize()` | Không phải tổng mọi server/pod. |
| Mức sockets warm tối thiểu | `minPoolSize` / `minSize()` | Không phải immediate readiness guarantee. |
| Số connections mở **đồng thời** | `maxConnecting` | Không phải max pool size. |
| Đóng socket idle | `maxIdleTimeMS` | Không phải query timeout. |
| Đóng/recycle socket theo lifetime | `maxLifeTimeMS` | Không phải operation deadline. |
| Thời gian chờ eligible server | `serverSelectionTimeoutMS` | Không phải pool checkout. |
| Chọn region/member gần RTT | `readPreference`, tags, `localThresholdMS` | Không bảo đảm fresh data. |
| Thời gian mở TCP socket mới | `connectTimeoutMS` | Không phải thời gian chờ pooled connection. |
| Chờ socket read/write | `socketTimeoutMS` legacy | Không phải toàn bộ HTTP deadline. |
| Chờ lấy pooled connection | `waitQueueTimeoutMS` / `maxWaitTime()` legacy | Không giới hạn số waiters. |
| Thời gian server chạy command | `maxTimeMS` / `FindIterable.maxTime()` | Không tính checkout/selection. |
| Chờ write concern acknowledgement | `wTimeoutMS` | Không rollback write đã áp dụng. |
| Deadline MongoDB operation tổng | `timeoutMS` / `MongoClientSettings.Builder.timeout()` | CSOT experimental; không tính app queue trước call. |
| Timeout một collection | `collection.withTimeout(...)` | Chỉ trên driver hỗ trợ CSOT. |
| Timeout transaction | `TransactionOptions.timeout(...)` | Không thay xử lý unknown commit. |
| Timeout cursor lifetime/iteration | `timeoutMode(...)` | Khác tailable/change-stream lifecycle. |

### 28.2. Chọn công cụ quan sát

| Câu hỏi | Công cụ |
|---|---|
| Driver có primary hay không? | SDAM cluster description, Cluster/Server listeners. |
| Pool có full? | JMX `size`, `checkedOutCount`, `maxSize`. |
| Checkout phải chờ bao lâu? | CMAP `CheckOutStarted/CheckedOut/Failed` + tracing. |
| Có quá nhiều socket creation? | CMAP created/ready/closed, maxConnecting, network/TLS metrics. |
| Server chạy lệnh chậm? | CommandListener, server profiler, `explain`. |
| DB CPU/IOPS/lock pressure? | Atlas metrics/`serverStatus`, `$currentOp`. |
| HTTP request chậm từ đâu? | End-to-end distributed traces và queue metrics. |
| Vì sao write timeout không biết đã commit chưa? | Error labels, stable business ID, retryable writes/transactions docs. |

### 28.3. Mẫu budget để cấu hình trong review

~~~text
Service:                  checkout-api
Java Driver:              5.x.y
MongoDB topology:         replica set rs0
Max application pods:     20
MongoClients per pod:     1
maxPoolSize per server:   64
maxConnecting per pool:   4
minPoolSize per server:   4
readPreference:           primary
serverSelectionTimeoutMS: based on SLO
CSOT timeoutMS:           based on remaining request deadline
admission concurrency:    bounded per instance
HTTP queue:               bounded
retry attempts:           capped and idempotent
monitoring:               CMAP + SDAM + command + serverStatus
~~~

Đây là **mẫu ghi cấu hình**, không phải những giá trị khuyến nghị mặc định. Thông số cần chọn sau khi đo workload/server capacity và kiểm behavior ở peak traffic/failover.

## 29. Tài liệu chính thức

Các trang MongoDB dưới đây là nguồn kiểm chứng cú pháp, defaults và semantics. Một số link dùng đường dẫn `current` nên **luôn đối chiếu Java Driver version cụ thể**, server version, Atlas tier/topology và notes về CSOT/overload handling trước khi áp dụng.

### 29.1. Java Driver pool, cluster và network

1. [MongoDB Java Sync Driver — Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/) — per-server pool, default `maxPoolSize=100`, `maxConnecting=2`, min/idle/lifetime/wait settings.
2. [MongoDB Java Sync Driver — Cluster Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/cluster-settings/) — `serverSelectionTimeoutMS` mặc định 30s, `localThresholdMS` mặc định 15ms, replica set name/direct connection.
3. [MongoDB Java Sync Driver — Server Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/server-settings/) — `heartbeatFrequencyMS`, monitoring modes và server listeners.
4. [MongoDB Java Sync Driver — Socket Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/socket-settings/) — `connectTimeoutMS` 10s, `socketTimeoutMS` 0 trong docs hiện hành.
5. [MongoDB Java Sync Driver — Connection Troubleshooting](https://www.mongodb.com/docs/drivers/java/sync/current/connection/connection-troubleshooting/) — diagnostic messages khi server selection không tìm được primary/host.
6. [MongoDB Manual — Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/) — các tham số URI và khác biệt giữa drivers.

### 29.2. CSOT và read preference

7. [MongoDB Java Sync Driver — Client-Side Operation Timeout](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/csot/) — `timeoutMS`, experimental status, timeout inheritance, legacy options ignored, transaction/cursor modes.
8. [MongoDB Java Sync Driver — Read/Write Settings](https://www.mongodb.com/docs/drivers/java/sync/current/crud/read-write-config/) — `ReadPreference`, `ReadConcern`, `WriteConcern` và collection-level overrides.
9. [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/) — primary/secondaryPreferred/nearest, maxStaleness và tags.
10. [MongoDB Manual — Read Preference Tags](https://www.mongodb.com/docs/manual/core/read-preference-tags/) — cách lọc eligible members theo tags.
11. [MongoDB Manual — maxStalenessSeconds](https://www.mongodb.com/docs/manual/core/read-preference-staleness/) — ước lượng secondary staleness và giới hạn cấu hình.
12. [MongoDB Manual — maxTimeMS](https://www.mongodb.com/docs/manual/reference/method/cursor.maxTimeMS/) — server-side execution limit khác client/network timeout.
13. [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — majority, journal và `wtimeout`.

### 29.3. Observability và resource behavior

14. [MongoDB Java Sync Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/) — CMAP, JMX `JMXConnectionPoolListener`, SDAM/Command events.
15. [MongoDB Driver Specifications — CMAP](https://github.com/mongodb/specifications/blob/master/source/connection-monitoring-and-pooling/connection-monitoring-and-pooling.md) — connection pool events/specification.
16. [MongoDB Driver Specifications — Server Selection](https://github.com/mongodb/specifications/blob/master/source/server-selection/server-selection.md) — selection algorithm, read preference và latency window.
17. [MongoDB Manual — serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — server connections/locks/resource statistics.
18. [MongoDB Manual — $currentOp](https://www.mongodb.com/docs/manual/reference/operator/aggregation/currentOp/) — active operations/latency/locks.
19. [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — query plan/executionStats, xử lý queries chậm.
20. [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — transaction lifetime, retry/commit ambiguity.
21. [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — retry semantics và bảo vệ idempotency.

### 29.4. Những điều phải xác minh trước khi copy code

1. Driver 4.x hay 5.x? Có method `timeout()`/`withTimeout()`/`timeoutMode()` chưa?
2. Có cấu hình CSOT ở client/database/collection/session/transaction không?
3. `maxWaitTime()`/`socketTimeoutMS`/`maxTimeMS` có còn hiệu lực dưới CSOT không?
4. Read preference có phù hợp business consistency và transaction constraints không?
5. Server selection có chọn được eligible server trên topology thật không?
6. Các members được cluster công bố có resolve/reachable từ deployment không?
7. Pool đang **full**, đang **warm**, hay đang **clear/reconnect**?
8. MongoDB server có headroom hay đang saturated CPU/IOPS/locks?
9. Retry writes/transactions có idempotency và deadline policy không?
10. Load test đã đo cả steady-state và failover/recovery chưa?

## 30. Kết luận

Trong **MongoDB Java Driver**, một request phải **chọn được server phù hợp**, **lấy được connection từ đúng pool**, rồi **thực hiện command trong deadline**. Ba giai đoạn này tương tác nhưng không thể thay thế nhau; cùng một biểu hiện timeout có thể đến từ mạng, election, pool exhaustion hoặc query chậm.

Ghi nhớ bốn điểm:

1. **`MongoClient` dùng chung và pool theo từng server.** `maxPoolSize` không phải tổng connections của toàn application; còn phải tính số clients, số pods, topology và monitoring sockets. `maxConnecting` giới hạn tốc độ mở connections, không phải pool capacity.
2. **SDAM và server selection quyết định “gửi tới đâu”, CMAP quyết định “mượn connection nào”.** `serverSelectionTimeoutMS` cần giải quyết bằng topology/read preference/network; `waitQueueTimeoutMS`/checkout wait phải xem pool lifecycle và concurrency; `connectTimeoutMS` và `socketTimeoutMS` liên quan network/socket. Đừng tăng pool khi không có eligible primary.
3. **Timeout phải bám deadline và semantics.** `maxTimeMS` là server execution limit; `timeoutMS` trong Java CSOT giới hạn end-to-end MongoDB operation và ảnh hưởng nhiều legacy options, hiện còn experimental. Client timeout **không có nghĩa write/transaction đã rollback**, nên retries phải idempotent.
4. **Đo đúng bottleneck trước khi tuning.** Quan sát CMAP/JMX/SDAM/command traces, MongoDB `serverStatus`/`explain` và HTTP SLO. Khi DB quá tải, dùng bounded admission, query optimization và capacity planning; khi pool thực sự là bottleneck và server còn headroom, mới điều chỉnh pool từng bước có canary/rollback.

**Tối ưu connection pool không phải đẩy nhiều yêu cầu nhất vào MongoDB, mà là bảo đảm mỗi yêu cầu được định tuyến đúng, không chờ vô hạn, hoàn thành trong thời gian hữu ích và không phá vỡ tính đúng đắn của dữ liệu khi gặp lỗi.**
