# Classic shared-file-system và JDBC master/slave với cơ chế khóa

> **Chương:** Sẵn sàng cao  
> **Module:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — tìm hiểu ActiveMQ Classic/Artemis trong giao tiếp Java/JMS bất đồng bộ.  
> **Phạm vi trực tiếp:** Hai mô hình HA **master/slave dùng chung persistence store của ActiveMQ Classic**: **KahaDB trên shared file system** và **pure JDBC persistence trên database chung**, với các cơ chế **shared file lock, database lock, database lease**. Mọi cấu hình trong bài thuộc **Classic `activemq.xml`**, **không phải Artemis `broker.xml`**.

## 1. Bài toán: ActiveMQ Classic A chết, B phải tiếp quản cùng backlog

Dịch vụ đơn hàng gửi command `ShipOrder(orderId=ORD-100)` tới queue `ha.demo.orders`. Broker A đang active, broker B đã khởi động standby. Sau khi producer gửi message persistent và commit thành công, nhưng trước khi consumer ACK, host A chết.

Hệ thống cần:

1. **Tối đa một broker active** có quyền ghi cùng message store trong mọi thời điểm.
2. Broker B tiếp quản và đọc **chính dữ liệu queue đã được A commit** mà không cần producer phát lại toàn bộ backlog.
3. Client Java thử kết nối các endpoint A/B, không chỉ một IP cố định.
4. Sau failover, broker A quay lại sẽ **chờ khóa** thay vì tự động giành vai active từ B.
5. Nếu có network partition/storage issue, cơ chế khóa và **fencing** không cho hai broker cùng sửa dữ liệu.

Hai mô hình giải quyết thông qua **một nguồn dữ liệu được chia sẻ**:

~~~mermaid
flowchart TD
    P["OpenWire Java clients: failover:(A,B)"] --> A["Classic broker A"]
    P --> B["Classic broker B"]
    A --> L{"Lock owner?"}
    B --> L
    L -->|Shared KahaDB| FS[("Shared filesystem + file lock")]
    L -->|Pure JDBC| DB[("Shared database + lock/lease")]
    L --> AC["Một ACTIVE: nhận connections, send, ACK"]
    L --> ST["Các STANDBY: chờ quyền sử dụng store"]
~~~

**Không phải active/active:** Nhiều broker có thể chạy process nhưng **chỉ một broker** nắm quyền làm master và phục vụ client; thêm standby **không tăng throughput** của một queue hay một message store.

**Không phải tự động sao chép dữ liệu giữa hai đĩa:** KahaDB shared FS và pure JDBC đều phụ thuộc vào **một backing store chung**. Nếu SAN/database đó mất hoàn toàn, cả A và B có thể không hoạt động. Độ sẵn sàng của broker không thay thế HA/backup của tầng lưu trữ.

### Mục tiêu

Người học có thể cấu hình hai broker, hiểu *acquire lock → active → keepalive → mất lock → takeover*, dùng Failover Transport trong Classic OpenWire client, kiểm chứng message tồn tại qua failover và đánh giá các lỗi split-brain, stale lock, lease, DB downtime.

## 2. Cơ chế chung: ai giữ storage lock thì được active

### 2.1. Vòng đời của master/slave

~~~mermaid
stateDiagram-v2
    [*] --> STARTING
    STARTING --> ACTIVE: Acquire lock thành công
    STARTING --> WAITING: Lock bị giữ
    WAITING --> ACTIVE: Acquire lock sau khi owner cũ rời đi
    ACTIVE --> STOPPING: Shutdown hoặc phát hiện mất lock
    WAITING --> STOPPING: Operator dừng standby
    STOPPING --> [*]
~~~

Một broker chỉ trở thành **active** khi cơ chế lưu trữ cho phép nó nắm quyền. Các broker khác chờ trong vòng thử lấy khóa; khi active dừng sạch và nhả khóa, một standby lấy khóa rồi khôi phục store và mở transport connector. Khi active chết bất thường, thời gian khóa được giải phóng/hết lease còn phụ thuộc OS, FS/DB, network và thời gian phát hiện lỗi.

| Trạng thái | Quyền đối với shared store | OpenWire client thấy gì? |
|---|---|---|
| **ACTIVE/master** | Quyền đọc/ghi và commit hợp lệ | Listener/transport connector hoạt động |
| **STANDBY/slave** | Chưa được phép làm writer | Không phục vụ kết nối JMS như một active |
| **FAILOVER** | Owner cũ mất quyền, standby tranh khóa | Client bị gián đoạn rồi thử endpoint khác |
| **STORAGE OUTAGE** | Không bảo đảm broker nào đọc/ghi an toàn | Có thể **không có active nào**, dù các process còn chạy |

Từ **ActiveMQ Classic 5.7**, persistence adapter có cơ chế **pluggable storage lockers**. Thông thường **KahaDB** dùng `shared-file-locker` và **pure JDBC** dùng `database-locker`; có thể chọn `lease-database-locker` khi yêu cầu phù hợp. *Locker* là phần quyết định quyền writer; *persistence adapter* là phần lưu message. Thay locker **không tự chuyển message sang backend khác**.

### 2.2. Không nhầm storage lock với JMS consumer lock

- **File lock/DB lease** bảo vệ **quyền của cả broker đối với message store**.
- **Exclusive consumer** bảo vệ **quyền phân phối từ queue tới consumer**.
- **JMS commit/ACK** đánh dấu trạng thái một message được gửi/nhận.
- **DB transaction/idempotency của ứng dụng** bảo vệ tác động nghiệp vụ.

Storage lock đúng **không** có nghĩa consumer không bao giờ nhận một message hai lần. Khi A ngừng giữa DB commit và JMS ACK, B có thể redeliver một message mà ứng dụng đã thực hiện side effect. Broker HA không tạo exactly-once ở tầng DB/API.

## 3. Classic shared-file-system master/slave với KahaDB

### 3.1. Shared directory phải thực sự là một backing store

Hai broker phải truy cập **cùng KahaDB directory** trên SAN hoặc distributed/shared filesystem:

~~~text
broker-a:/srv/activemq-ha/kahadb ──┐
                                   ├── CÙNG filesystem vật lý
broker-b:/srv/activemq-ha/kahadb ──┘
~~~

Hai ổ local trên hai host có cùng chuỗi đường dẫn **không phải shared storage**. Trong trường hợp đó, mỗi broker có thể chiếm khóa riêng của chính nó và trở thành hai active với dữ liệu lệch nhau.

Yêu cầu quan trọng:

1. Distributed file locking hỗ trợ đúng cơ chế lock Java/Classic sử dụng giữa **hai host khác nhau**.
2. Hệ thống tệp thực hiện nhất quán metadata/data, không cache làm hai host nhận định lock sai.
3. Lock của active được nhả hoặc có cơ chế timeout phù hợp khi process/host chết.
4. Storage và orchestrator có thể **fence active cũ** khi nó mất lock hoặc truy cập storage không an toàn.
5. Snapshot/backup nhất quán và HA của chính shared filesystem được kiểm thử.

Tài liệu Apache cảnh báo: một số triển khai **OCFS2** không hỗ trợ flock/POSIX lock mà Java mong đợi; với **NFSv3**, lock có thể treo sau client crash làm standby không lên. **NFSv4** có lease mechanism, nhưng không tự động bảo đảm an toàn với mọi server/mount/version. Hãy kiểm thử thực tế trên đúng OS, JVM, FS driver và storage.

### 3.2. Cấu hình KahaDB + shared-file-locker

Trong ActiveMQ Classic `conf/activemq.xml`, phần cấu hình persistence **bên trong `<broker xmlns="http://activemq.apache.org/schema/core">`**:

~~~xml
<persistenceAdapter>
    <kahaDB directory="/srv/activemq-ha/kahadb"
            lockKeepAlivePeriod="10000">
        <locker>
            <shared-file-locker lockAcquireSleepInterval="5000"/>
        </locker>
    </kahaDB>
</persistenceAdapter>

<transportConnectors>
    <transportConnector name="openwire"
        uri="tcp://0.0.0.0:61616"/>
</transportConnectors>
~~~

Trên **broker A**, phần thẻ bao quanh có các thuộc tính:

~~~xml
<broker xmlns="http://activemq.apache.org/schema/core"
        brokerName="classic-fs-a"
        persistent="true"
        schedulerSupport="false"
        deleteAllMessagesOnStartup="false">
    <!-- Đặt persistenceAdapter/transportConnectors tại đây -->
</broker>
~~~

Đây là **các mảnh XML để chèn vào XBean/Spring cấu hình đã có**, không phải hai thẻ broker để copy nguyên văn vào cùng file. Root `<beans>`, security, namespace, management và các thành phần khác phải giữ nguyên. Classic có yêu cầu thứ tự một số child elements theo XSD; đối chiếu file mẫu đúng phiên bản.

Ý nghĩa:

- `directory` là **đường dẫn cùng backing shared FS** mà cả hai node dùng.
- `lockAcquireSleepInterval="5000"`: standby chờ khoảng 5 giây giữa các lần thử lấy lock. Không phải cam kết RTO = 5 giây.
- `lockKeepAlivePeriod="10000"`: active kiểm tra tính hợp lệ của shared-file lock. **Không nên đặt bằng 0**; tài liệu Classic cảnh báo sửa/xóa lock file khi keepalive tắt có thể dẫn đến **hai master, KahaDB corruption**.
- `persistent="true"` và gửi message `DeliveryMode.PERSISTENT` giúp message bền vững khi store đáng tin.
- `deleteAllMessagesOnStartup="false"` quan trọng: cấu hình true có thể xóa dữ liệu mà standby cần khôi phục khi takeover.

### 3.3. Broker B và giới hạn của bài thử một máy

B có **cùng** KahaDB directory và locker, nhưng tên node riêng:

~~~xml
<broker xmlns="http://activemq.apache.org/schema/core"
        brokerName="classic-fs-b"
        persistent="true"
        schedulerSupport="false"
        deleteAllMessagesOnStartup="false">
    <!-- Cùng KahaDB /srv/activemq-ha/kahadb -->
    <!-- OpenWire trên host broker-b -->
</broker>
~~~

Nếu A/B trên **hai host**, cả hai có thể dùng port 61616. Nếu thử hai instance trên **một host**, phải tách các cổng (ví dụ 61616 và 61617), JMX/management port, process data phụ trợ, nhưng vẫn trỏ **một store dùng chung**. Hai process cùng host chỉ giúp quan sát locking; **không** kiểm chứng host-level HA.

**Scheduler:** Với ActiveMQ Classic, scheduled-job state không nhất thiết nằm trong chính persistence adapter. Nếu dùng `schedulerSupport="true"`, cần cấu hình đường `dataDirectory`/scheduler store phù hợp trên shared storage, kiểm chứng scheduled messages tồn qua takeover. Ví dụ lab **tắt scheduler** để không khiến node A/B dùng hai scheduler data directory độc lập.

### 3.4. Ma trận sự cố file lock

| Sự cố | Hành vi đúng | Nguy cơ / điều cần xác minh |
|---|---|---|
| Master dừng sạch | Nhả lock, standby lấy khóa và phục hồi KahaDB | Store còn nguyên, một OpenWire connector active |
| Master process bị kill | OS/FS phải giải phóng lock hợp lệ | Stale lock kéo dài RTO |
| Thay/xóa file lock bằng tay | **Không được phép** trong quy trình thường | Hai broker có thể cùng active và ghi hỏng store |
| NFS lock không được hỗ trợ đúng | Failover không an toàn | Split-brain, corruption hoặc standby chờ mãi |
| Shared filesystem chết | Không broker nào truy xuất dữ liệu an toàn | Shared storage là failure domain chung |
| Master mất kết nối storage nhưng còn kết nối client | Master phải dừng/fence đúng cách | Side effect cũ tiếp tục trong khi standby mới hoạt động |

**Không dùng thao tác xóa KahaDB lock file để “ép failover”.** Nếu standby chờ quá lâu, điều tra owner lock, mount status, broker logs và tình trạng master cũ đã thực sự bị fence hay chưa.

## 4. Classic JDBC master/slave: pure JDBC persistence và database lock

### 4.1. JDBC store là nơi chứa message, không chỉ giữ khóa

Trong mô hình **pure JDBC master/slave**, cả A/B dùng **cùng JDBC persistence adapter** trỏ tới **cùng DB schema/tables** chứa message/queue state. Broker nắm được database lock/lease mới được active. So với KahaDB shared FS, JDBC phải đi qua driver/SQL transactions, database server, WAL/redo logs và đôi khi network round trips.

**Đừng nhầm với KahaDB + database lease locker:** có thể dùng DB *chỉ để bầu master* nhưng vẫn lưu message bằng KahaDB; đó là mô hình kết hợp khác. Phần này dùng **jdbcPersistenceAdapter** để lưu thực sự trong RDBMS.

### 4.2. Chuẩn bị database riêng cho một HA group

Ví dụ PostgreSQL lab:

~~~sql
-- Chạy ở kết nối quản trị; không tạo DB bên trong SQL transaction.
CREATE ROLE amq_ha LOGIN PASSWORD 'lab-only-password';
CREATE DATABASE amq_ha OWNER amq_ha;
~~~

Chỉ sử dụng literal password trong lab; production cần TLS, secret injection, quyền tối thiểu, database backups và HA. Hai Classic brokers trong **cùng HA group** trỏ đúng **database/table set** đó; không đưa broker active độc lập của hệ thống khác vào cùng tables.

Trên **cả A/B** cần:

- JDBC driver `org.postgresql.Driver` nằm trong **broker classpath**, không chỉ trong Maven classpath Java client.
- Nếu dùng pool ví dụ `org.apache.commons.dbcp2.BasicDataSource`, phải có thư viện DBCP2 tương thích trong broker classpath.
- Database user có quyền tạo/đọc/ghi các bảng ActiveMQ theo chính sách DDL/preprovision của tổ chức.
- Cùng JDBC persistence schema, DB endpoint logic, version broker tương thích; có connection/transaction timeout và DB monitoring phù hợp.

### 4.3. XBean: bean DataSource đặt ngoài broker, adapter đặt trong broker

Trong Spring `<beans>` root của `conf/activemq.xml`, định nghĩa DataSource:

~~~xml
<!-- Spring namespace, ngoài phần tử <broker>. -->
<bean id="ha-ds"
      class="org.apache.commons.dbcp2.BasicDataSource"
      destroy-method="close">
    <property name="driverClassName"
              value="org.postgresql.Driver"/>
    <property name="url"
              value="jdbc:postgresql://db-ha.internal:5432/amq_ha?sslmode=require"/>
    <property name="username" value="${ha.db.user}"/>
    <property name="password" value="${ha.db.password}"/>
    <property name="maxTotal" value="20"/>
</bean>
~~~

Cấu hình trên cần Spring `PropertyPlaceholderConfigurer` hoặc cơ chế cấu hình tương đương đọc `ha.db.user`/`ha.db.password` từ secrets/credentials file của broker. Không sao chép XML mảnh thành file standalone không có root Spring namespaces và placeholder resolver.

Trong thẻ `<broker>` ở mỗi node:

~~~xml
<persistenceAdapter>
    <jdbcPersistenceAdapter dataSource="#ha-ds"
            lockKeepAlivePeriod="5000">
        <locker>
            <lease-database-locker
                lockAcquireSleepInterval="10000"/>
        </locker>
    </jdbcPersistenceAdapter>
</persistenceAdapter>

<transportConnectors>
    <transportConnector name="openwire"
        uri="tcp://0.0.0.0:61616"/>
</transportConnectors>
~~~

Node A nên có thuộc tính:

~~~xml
<broker xmlns="http://activemq.apache.org/schema/core"
        brokerName="classic-jdbc-a"
        persistent="true"
        schedulerSupport="false"
        deleteAllMessagesOnStartup="false">
    <!-- JDBC persistenceAdapter + transportConnectors -->
</broker>
~~~

Node B dùng `brokerName="classic-jdbc-b"`, cùng DB/tables/locker, endpoint riêng. **Lease database locker yêu cầu định danh broker khác nhau** (hoặc cấu hình `leaseHolderId` riêng) để phân biệt owner. Không thể khởi động hai broker active độc lập cùng ghi một bộ tables rồi gọi đó là “cluster”.

### 4.4. Database locker mặc định và lease database locker

| Cơ chế | `database-locker` | `lease-database-locker` |
|---|---|---|
| Cách bảo vệ store | Giữ một transaction JDBC/DB table lock dài hạn | Ghi lease có hạn dùng và gia hạn định kỳ |
| Master crash | DB cần phát hiện TCP/session chết để release lock | Standby đợi lease hết hạn rồi chiếm |
| DB failover | Transaction cũ có thể rollback/mất | Lease có thể tồn qua DB failover nếu backend bảo toàn state |
| Tài nguyên | Transaction/connection giữ lock lâu | Renew/poll/clock consistency |
| Rủi ro chính | Half-open socket giữ lock, takeover lâu | Clock skew, GC pause, lease hết hạn giả |
| Mặc định của pure JDBC adapter | **Database locker** theo docs Classic | Chọn explicit nếu muốn lease |

Ví dụ dùng **database-locker truyền thống** thay toàn bộ `<locker>`/adapter ở trên:

~~~xml
<persistenceAdapter>
    <jdbcPersistenceAdapter dataSource="#ha-ds"
            lockKeepAlivePeriod="10000">
        <locker>
            <database-locker
                lockAcquireSleepInterval="5000"/>
        </locker>
    </jdbcPersistenceAdapter>
</persistenceAdapter>
~~~

Đây là **hai cấu hình loại trừ nhau**, không khai báo cả database-locker và lease-database-locker trong cùng một persistence adapter.

Với `database-locker`, một transaction lock được giữ lâu trên bảng lock. Nếu broker crash, DB có thể chưa thấy connection chết cho tới khi TCP timeout; standby vì vậy chờ lâu.

Với `lease-database-locker`:

- Broker active gia hạn lease trước khi hết hạn, standby kiểm tra để chiếm khi lease cũ hết hiệu lực.
- Theo tài liệu Classic, cần **`lockAcquireSleepInterval > lockKeepAlivePeriod`**. Ví dụ `10000 ms > 5000 ms` như cấu hình trên.
- Broker name/lease holder phải riêng. Đồng hồ của broker và database cần được đồng bộ hoặc điều chỉnh chênh lệch bằng chức năng như `maxAllowableDiffFromDBTime` khi hỗ trợ.
- Không đặt lease quá ngắn chỉ để giảm RTO: GC pause, DB/network stall hoặc clock skew có thể khiến owner cũ hết lease nhưng chưa dừng việc đang làm.

**Không dùng SQL UPDATE/DELETE trên bảng lock để ép bầu master** nếu chưa chứng minh owner cũ đã dừng/fence. DB lock tables là cơ chế đồng bộ nội bộ broker, không phải API thao tác queue.

## 5. Tham số khóa, fencing và split-brain

### 5.1. Các setting phải hiểu trước khi sửa

| Tham số | Vị trí | Ý nghĩa |
|---|---|---|
| `useLock` | Persistence adapter | Bật/tắt locking; **không đặt false** trong shared-store HA |
| `failIfLocked` | Locker | True làm standby fail startup khi không có lock ngay; thông thường standby cần chờ |
| `lockAcquireSleepInterval` | Locker | Khoảng thử acquiring lock; không phải tổng RTO |
| `lockKeepAlivePeriod` | Persistence adapter | Nhịp active kiểm tra/gia hạn quyền |
| `leaseHolderId` | Lease locker (tùy bản) | Định danh owner, thay cho brokerName khi cấu hình đúng |
| `maxAllowableDiffFromDBTime` | Lease locker | Điều chỉnh chênh clock với database khi cần |

Riêng `shared-file-locker`, tài liệu Classic cảnh báo giữ `lockKeepAlivePeriod=0` có thể không phát hiện lock file đã bị xóa/sửa; standby lấy được lock và cùng active → **KahaDB corruption**.

### 5.2. Failure mode split-brain

~~~text
t0  A là active và giữ lock/lease; B standby.
t1  A mất kết nối tới storage nhưng vẫn giữ TCP client connections.
t2  Phía storage coi lock/lease A đã hết; B chiếm quyền active.
t3  A chưa được fence, có thể tiếp tục phục vụ hoặc gây side effect.
~~~

Điều kiện an toàn là **master cũ phải mất quyền ghi/được fence** khi master mới được phép tiếp quản. Cơ chế hỗ trợ có thể là host power fencing, storage fencing, volume exclusive attach, lock/lease correctness hoặc orchestration nghiêm ngặt. **Failover Transport không tự giải quyết split-brain**; nó chỉ chuyển kết nối client tới endpoint khả dụng.

Không mô phỏng split-brain bằng cách xóa lock file hoặc phá đồng bộ DB trên production. Thử sự cố storage/network nên chỉ làm ở lab disposable, có snapshot/backup.

### 5.3. KahaDB + lease database locker là một biến thể khác

Classic 5.9+ có thể dùng `lease-database-locker` **với KahaDB**, nghĩa là:

~~~text
Message persistence: KahaDB files
Quyền master: database lease
~~~

Trường hợp này **không phải pure JDBC master/slave**, vì message vẫn ở KahaDB. Hai node vẫn phải dùng cùng KahaDB store hoặc cơ chế replication riêng được hỗ trợ. Tài liệu Classic yêu cầu một số cấu hình `dataSource`/`statements` trên locker và exception handler tương thích khi phối hợp; không nên chỉ đổi tên thẻ trong XML rồi coi message đã nằm trong DB.

## 6. Failover Transport của Classic client: kết nối lại không đồng nghĩa chắc chắn commit

Trong hai mô hình master/slave, chỉ master đang giữ lock mới được phép mở transport connector cho client. Một OpenWire client Java nên biết **hai endpoint ứng viên**, ví dụ:

~~~text
failover:(tcp://broker-a:61616,tcp://broker-b:61616)?randomize=false&maxReconnectDelay=2000&timeout=10000
~~~

Các option:

- `failover:(A,B)`: ActiveMQ Classic **OpenWire client** thử kết nối các broker. Khi A mất kết nối, client thử lại B hoặc A theo chính sách.
- `randomize=false`: thử danh sách theo thứ tự; **không buộc A phải là master**. Nếu B đang giữ lock thì A standby và client chỉ có thể kết nối B.
- `maxReconnectDelay=2000`: giới hạn một khoảng delay giữa các lần reconnect; không bảo đảm thời gian takeover tổng cộng 2 giây.
- `timeout=10000`: giới hạn thời gian **send operation** bị block trong lúc failover. **Không** phải timeout cứng cho toàn transaction JMS hoặc toàn application request.
- Không có endpoint nào active vì storage không sẵn sàng: client có thể tiếp tục reconnect; chính sách retry/deadline do ứng dụng quản lý.

**URI này không portable sang Artemis Core client.** Artemis có connector/HA topology riêng; native AMQP/STOMP clients cũng không tự hiểu đầy đủ option của Classic `failover:`. Mỗi giao thức có cách reconnect khác nhau.

### 6.1. Những cửa sổ lỗi khó quan sát

| Thời điểm mất A | Điều client có thể biết | Hành động |
|---|---|---|
| Trước `send()` | Chưa gửi message | Gửi sau khi connection sẵn sàng |
| Đã `send()` nhưng chưa JMS `commit()` | Transaction chưa được xác nhận | Thử rollback/retry có kiểm soát |
| Broker đã commit, response về client bị mất | **Không chắc commit đã thành công hay chưa** | Giữ nguyên `eventId` khi retry, consumer idempotent |
| Consumer đã ghi DB, chưa ACK/commit JMS | Broker có thể redeliver | Dùng unique business key/dedup |
| Consumer transacted session bị failover | Có thể được client replay in-flight transaction hoặc ném rollback exception | Xử lý `TransactionRolledBackException`/reconnect và kiểm chứng trạng thái |

Theo tài liệu Classic, Failover Transport có thể replay transaction và theo dõi redelivery; tuy nhiên khi không thể tái lập điều kiện an toàn, nó có thể ném `javax.jms.TransactionRolledBackException`. Đừng hiểu “client reconnect thành công” là “mọi transaction cũ tự động committed đúng một lần”.

**Ranh giới tin cậy:** queue message persistent + store durable + JMS commit được xác nhận giúp giảm mất dữ liệu khi broker restart, nhưng không đồng nghĩa message chỉ được xử lý một lần bởi business system. Producer resend do response bị mất hoặc consumer redelivery đều có thể tạo duplicate tác động nghiệp vụ.

## 7. Java/JMS lab với ActiveMQ Classic

### 7.1. Chọn client cùng JMS namespace

Ví dụ dùng **ActiveMQ Classic 5.19.x** (nhánh dùng `javax.jms.*`) và Java 17. POM tối thiểu cho một project Maven độc lập:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <activemq.version>5.19.12</activemq.version>
</properties>
<dependencies>
    <dependency>
        <groupId>org.apache.activemq</groupId>
        <artifactId>activemq-client</artifactId>
        <version>${activemq.version}</version>
    </dependency>
</dependencies>
~~~

`5.19.12` là ví dụ pin client trong nhánh Classic 5.19, phù hợp tài liệu trạng thái phát hành tháng 11/2026; kiểm tra broker/JDK và dependency thực tế trước khi chạy. **Classic 5.x dùng `javax.jms.*`**; với Classic 6.x, chuyển sang Jakarta Messaging với client phù hợp. **Không** trộn package `jakarta.jms.*` của Artemis client và `javax.jms.*` của Classic 5.x trong cùng mã Java.

Dùng biến môi trường `AMQ_USER`/`AMQ_PASSWORD` và quyền `send`/`consume` queue `ha.demo.orders`. Cả hai broker phải có cùng security policy; nếu không, failover có thể chuyển sang broker mới nhưng bị `JMSSecurityException`.

### 7.2. Chương trình Java 17 đầy đủ

Mode:

- `send E100`: publish một persistent `TextMessage` rồi commit JMS.
- `receive`: nhận một message, in `JMSMessageID`, `JMSRedelivered` rồi commit (ACK).
- `hold`: nhận message, **giữ chưa commit trong 90 giây**. Dùng để quan sát nếu client/broker mất kết nối; sau timeout, rollback.

~~~java
import javax.jms.Connection;
import javax.jms.DeliveryMode;
import javax.jms.JMSException;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.MessageProducer;
import javax.jms.Queue;
import javax.jms.Session;
import javax.jms.TextMessage;

import org.apache.activemq.ActiveMQConnectionFactory;

public final class ClassicHaLab {
    private static final String URL =
        "failover:(tcp://broker-a:61616,tcp://broker-b:61616)"
        + "?randomize=false&maxReconnectDelay=2000&timeout=10000";

    private static final String QUEUE = "ha.demo.orders";

    public static void main(String[] args) throws Exception {
        if (!validArgs(args)) {
            System.out.println("ClassicHaLab send <eventId>");
            System.out.println("ClassicHaLab receive");
            System.out.println("ClassicHaLab hold");
            return;
        }

        String user = requiredEnv("AMQ_USER");
        String password = requiredEnv("AMQ_PASSWORD");

        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory(URL);
        Connection connection = factory.createConnection(user, password);

        try {
            Session session = connection.createSession(
                true, Session.SESSION_TRANSACTED);
            try {
                Queue queue = session.createQueue(QUEUE);

                switch (args[0]) {
                    case "send" -> send(session, queue, args[1]);
                    case "receive" -> consume(
                        connection, session, queue, false);
                    case "hold" -> consume(
                        connection, session, queue, true);
                    default -> throw new AssertionError();
                }
            } finally {
                session.close();
            }
        } finally {
            connection.close();
        }
    }

    private static void send(
            Session session, Queue queue, String eventId)
            throws Exception {

        MessageProducer producer = session.createProducer(queue);
        try {
            producer.setDeliveryMode(DeliveryMode.PERSISTENT);
            TextMessage message = session.createTextMessage(
                "{\"eventId\":\"" + eventId
                + "\",\"operation\":\"ShipOrder\"}");
            message.setStringProperty("eventId", eventId);

            try {
                producer.send(message);
                session.commit();

                System.out.printf(
                    "SEND_COMMITTED eventId=%s JMSMessageID=%s%n",
                    eventId, message.getJMSMessageID());
            } catch (Exception failure) {
                attemptRollback(session, failure);
                throw failure;
            }
        } finally {
            producer.close();
        }
    }

    private static void consume(
            Connection connection, Session session, Queue queue,
            boolean hold) throws Exception {

        MessageConsumer consumer = session.createConsumer(queue);
        try {
            connection.start(); // Cần cho synchronous receive.
            Message message = consumer.receive(15000);

            if (message == null) {
                System.out.println("RECEIVE_TIMEOUT");
                return;
            }

            try {
                if (!(message instanceof TextMessage text)) {
                    throw new IllegalArgumentException(
                        "Expected TextMessage");
                }

                System.out.printf(
                    "RECEIVED eventId=%s JMSMessageID=%s "
                    + "redelivered=%s%n",
                    text.getStringProperty("eventId"),
                    text.getJMSMessageID(),
                    text.getJMSRedelivered());

                if (hold) {
                    System.out.println(
                        "HOLD_UNCOMMITTED; có thể thử failover lab");
                    Thread.sleep(90_000);
                    session.rollback();
                    return;
                }

                // Production: xử lý side effect idempotent theo eventId
                // trước khi commit JMS delivery.
                session.commit();
                System.out.println("RECEIVE_COMMITTED");
            } catch (Exception failure) {
                attemptRollback(session, failure);
                throw failure;
            }
        } finally {
            consumer.close();
        }
    }

    private static void attemptRollback(
            Session session, Exception original) {
        try {
            session.rollback();
        } catch (JMSException rollbackFailure) {
            original.addSuppressed(rollbackFailure);
        }
    }

    private static boolean validArgs(String[] args) {
        if (args.length == 2 && "send".equals(args[0])) {
            return args[1].matches("[A-Za-z0-9_-]{1,60}");
        }
        return args.length == 1 &&
            ("receive".equals(args[0]) || "hold".equals(args[0]));
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                "Thiếu environment variable " + name);
        }
        return value;
    }
}
~~~

**Quan sát đúng:**

- Khi **send**, không cần `connection.start()`; `Session.commit()` mới xác nhận transaction JMS.
- Khi **receive**, phải start connection trước khi nhận synchronous; `commit()` trên transacted session dùng để ACK.
- `hold` chỉ dùng trong **lab cô lập** để tạo message in-flight. Nếu broker failover giữa lần nhận và rollback, hành vi sẽ phụ thuộc việc client reconnect/session recovery và policy, không phải phép thử deterministic.
- Không dùng `JMSMessageID` làm khóa dedup nếu producer phát lại một bản message mới. Dùng `eventId` do nghiệp vụ cấp, giữ nguyên xuyên retries.
- JMS `Session` không được sử dụng tùy tiện từ nhiều thread; hai process thử nghiệm dùng context/session riêng.

### 7.3. Chạy Java

Thay `broker-a` và `broker-b` bằng tên/IP host thật trong `URL`. Nếu hai instance chạy chung máy với ports 61616/61617, sửa URL tương ứng. Run từ IDE hoặc build project Maven của **ứng dụng lab** theo setup riêng; không cần sửa source broker.

Ví dụ thao tác:

~~~text
1. ClassicHaLab send E100
2. Dừng active broker A, đợi broker B takeover
3. ClassicHaLab receive
4. ClassicHaLab send E101
5. ClassicHaLab receive
~~~

Kỳ vọng E100 và E101 được nhận/commit theo hai lần thử độc lập. Nếu queue có message cũ, kết quả có thể lệch; dọn **chỉ dữ liệu lab**, không purge queue production.

## 8. Thực hành A — Shared KahaDB: takeover từ file lock

### 8.1. Preflight bắt buộc

1. Chuẩn bị hai broker instances Classic **cùng phiên bản tương thích**, file `activemq.xml` riêng, host/port riêng.
2. Cả hai trỏ cùng KahaDB directory qua **shared filesystem đã kiểm chứng file locking**.
3. Bật locking, `lockKeepAlivePeriod>0`, `deleteAllMessagesOnStartup=false`; cả hai có cấu hình persistence/security tương thích.
4. Start A rồi B. Quan sát log: A giành file lock, mở OpenWire connector; B **chờ lock**.
5. Kiểm tra **chỉ một endpoint phục vụ OpenWire**. Process B đang chạy không chứng minh B đã active.

### 8.2. Bài kiểm chứng failover sạch

1. Xác nhận `ha.demo.orders` rỗng, chưa có consumer ngoài bài lab.
2. Chạy `ClassicHaLab send E100`, chờ `SEND_COMMITTED E100`.
3. Đo queue depth và ghi log ID.
4. **Dừng sạch broker A** bằng service/script quản trị của đúng instance; không xóa/sửa file KahaDB.
5. B lấy file lock, recovery journal và mở transport connector.
6. Chạy `ClassicHaLab receive`, đọc E100 và `RECEIVE_COMMITTED`; queue về 0.
7. Start A trở lại. A phải chờ làm standby nếu B vẫn active.

### 8.3. Crash test có kiểm soát

Lặp lại với `send E102` nhưng thay stop sạch bằng dừng cưỡng bức **process broker A** trên môi trường thử có snapshot/backup. Chỉ dùng đúng PID của process lab, **không** kill shared filesystem hoặc storage service. Đợi B takeover rồi nhận E102.

Quan sát:

- Chỉ một broker giữ file lock/active connector tại một thời điểm.
- Persistent message đã **commit trước crash** còn đọc được từ B nếu storage giữ đúng durability.
- Message **đang in-flight, chưa ACK** có thể được giao lại. Nếu đã có side effect DB trước khi JMS ACK, cần idempotency.
- Thời gian takeover thực tế gồm phát hiện crash, release lock, storage recovery và client reconnect; không được đồng nhất với `lockAcquireSleepInterval`.

**Không thử gây split-brain thật** bằng cách xóa file lock, phá mount hay tắt fencing trên production.

## 9. Thực hành B — Pure JDBC master/slave và database lease

### 9.1. Preflight

1. Hai broker cùng dùng **một database và bảng message** của HA group, cùng versions/DDL tương thích.
2. JDBC driver/pool và security properties được load đúng trên cả hai.
3. Chọn **một** locker: `database-locker` hoặc `lease-database-locker`, không cả hai.
4. Với lease: brokerName/leaseHolderId khác nhau; `lockAcquireSleepInterval > lockKeepAlivePeriod`; clock đồng bộ và DB endpoint có timeout/HA phù hợp.
5. Start A rồi B; xác minh A giành DB lock/lease, B chờ, chỉ A phục vụ OpenWire.

### 9.2. Kiểm chứng

1. Gửi `E200` bằng ClassicHaLab, chờ JMS commit thành công.
2. Dừng A sạch; quan sát B giành lock/lease, nạp cùng database store, mở listener.
3. Nhận E200 ở B và commit; xác nhận message không còn trong queue.
4. Khởi động lại A: node A phải chờ, không tự xóa data hoặc chiếm lock của B.
5. Trong lab khác, crash active A và đo thời gian DB locker giải phóng transaction hoặc lease hết hạn. Đừng suy tổng RTO chỉ từ chu kỳ poll.

### 9.3. Database outage khác với broker outage

Nếu PostgreSQL/database unavailable:

- A có thể mất lock và phải dừng để bảo vệ store.
- B cũng không thể chiếm lock **và** đọc message nếu DB chưa phục hồi.
- Client Failover Transport tiếp tục thử endpoints nhưng có thể không có broker active hợp lệ.
- Database replication/failover có thể giúp, nhưng phải kiểm chứng **WAL durability, nhất quán lock state, transaction replay, endpoint switching**.

**HA broker không che được single point of failure ở shared database.** Nếu DB replica không đồng bộ đủ trước khi primary chết, cũng không được tuyên bố RPO=0 chỉ vì B lên active.

## 10. Failure matrix: tình huống nào được HA xử lý?

| Tình huống | Shared KahaDB FS | Pure JDBC | Kiểm chứng |
|---|---|---|---|
| Master stop sạch | Nhả file lock | Release DB lock/lease | Một active mới, queue liên tục |
| Master process crash | FS phải nhả lock hoặc thu hồi an toàn | DB session/lease phải giải phóng/hết hạn | Thời gian thật, recovery log |
| Mạng client → A mất, A vẫn giữ lock | B **vẫn standby** | B **vẫn standby** | Không có takeover chỉ vì client timeout |
| Shared storage chết | Cả hai không có store an toàn | DB down, cả hai không có store | HA/backup của storage |
| Lock sai hoặc old master chưa fence | KahaDB corruption/split-brain | Lease owner cũ vẫn có side effect | Fencing, chỉ một writer |
| NFS lock stale | Standby có thể không takeover | Không liên quan file locker | FS mount/lock semantics |
| DB half-open connection | Không áp dụng | Transaction locker có thể chờ lâu | DB TCP timeout/lease |
| Long GC pause / clock drift | Keepalive chậm | Lease có nguy cơ hết hạn sai | Headroom, clock sync |
| Producer commit response bị mất | Outcome bất định | Outcome bất định | eventId ổn định/outbox |
| Restore snapshot cũ | Message đã ACK có thể xuất hiện lại | DB PITR có thể đưa lại message | RPO + dedup |

### 10.1. Metrics và runbook

**Broker:**

- Broker name active, trạng thái locker, thời gian acquire/release, số standby.
- Chỉ một OpenWire listener active ở HA group; reconnect client failures.
- Queue ready/delivering, consumer count, enqueue/dequeue, redelivery/DLQ.
- Startup/recovery duration, latency send/commit, outcome không chắc chắn.

**KahaDB/shared FS:**

- File lock errors, mount availability, disk latency/fsync, KahaDB journal growth.
- Số lần NFS/SAN timeout và thời gian lock release khi crash.
- Snapshot age, restore drill, dấu hiệu split-brain/fencing failures.

**JDBC:**

- DB connections/lock wait, lease renew failures, pool exhaustion.
- DB availability, transaction latency, WAL flush/replication lag, backup/PITR status.
- Long-lived locking transaction nếu dùng database-locker truyền thống.

**Ứng dụng:** `eventId`, `JMSMessageID`, `JMSRedelivered`, transaction outcome, duplicate-detected count, idempotent business commit result. Không log payload/credentials nhạy cảm.

### 10.2. “Hai process chạy” chưa phải HA khỏe

Một standby process đang alive nhưng chờ lock là **trạng thái đúng**. Ngược lại, hai OpenWire ports đều nhận JMS traffic và hai broker cùng sửa một shared store là dấu hiệu **nguy hiểm cần dừng và điều tra**, không phải active/active.

## 11. Chọn shared filesystem hay pure JDBC?

| Tiêu chí | KahaDB shared-file-system | Pure JDBC master/slave |
|---|---|---|
| Dữ liệu message ở đâu? | KahaDB journal trên shared volume | RDBMS message tables / WAL |
| Khóa thường gặp | Shared file lock | Transaction database locker hoặc lease locker |
| Phụ thuộc hạ tầng | SAN/FS phân tán có locking tin cậy | DB shared, driver/pool, DB HA |
| Hiệu năng | KahaDB phù hợp workload broker append-heavy | SQL/DB/network overhead, cần benchmark |
| Failure domain chung | Shared filesystem | Shared database |
| Takeover có thể chậm vì | Stale file lock, mount recovery, journal recovery | DB transaction/lease release, DB failover |
| Backup | Snapshot nhất quán KahaDB và dữ liệu liên quan | DB backup/PITR nhất quán |
| Chống split-brain | FS lock + fencing | DB lock/lease correctness + clock/fencing |
| Phù hợp khi | Có SAN/FS hỗ trợ lock và nhu cầu KahaDB performance | Đội DBA mạnh, yêu cầu quản trị DB, tải đáp ứng SLO |

Nếu mục tiêu là **tăng throughput**, thêm standby vào shared store không giúp. Cần thiết kế cluster/partition với **mỗi active broker có store riêng** và routing phù hợp; đó không phải mô hình HA single-writer đang học.

**Khác ActiveMQ Artemis:** Artemis có `broker.xml`, journal/JDBC store, node manager, replication/shared-store HA khác Classic. Không được chép `<kahaDB>`, `<jdbcPersistenceAdapter>` hoặc `failover:(...)` từ Classic sang Artemis và trông chờ cùng hành vi.

## 12. Bài tập và câu hỏi tự kiểm tra

1. A/B có cùng đường dẫn string `/var/lib/activemq/data` nhưng là **hai đĩa local**. B có thể đọc message A đã commit không? **Không**, đây không phải shared store.
2. B chờ mãi sau A crash trên NFSv3. Có nên xóa file lock? **Không**, điều tra stale locking, xác minh A đã fence và sửa backend FS.
3. Lease locker có `lockKeepAlivePeriod=10000` và `lockAcquireSleepInterval=5000`. Vì sao sai? Theo Classic, lease requires **acquire sleep interval lớn hơn keepalive period**.
4. Database primary chết, không có replica. B có tự đọc message từ local disk không? **Không**, pure JDBC cần DB shared hoạt động.
5. A còn kết nối client nhưng mất storage lease, B lên active. Vì sao đây là rủi ro? **Old master chưa được fence**, có nguy cơ split-brain hoặc side effect ngoài broker.
6. Consumer đã gửi email thành công, chết trước JMS ACK. Sau B takeover, có thể email bị gửi hai lần? **Có**, cần idempotency key/outbox.
7. Thêm ba standby vào HA group có tăng throughput active lên bốn lần? **Không**, vẫn một owner lock.
8. Vì sao `randomize=false` không ép A làm master khi B còn giữ lock? Vì nó chỉ định thứ tự **client thử endpoint**, không điều khiển lock.
9. Scheduler support có cần kiểm tra lưu trạng thái ngoài KahaDB không? **Có**, vì scheduler store có thể độc lập với persistence adapter.
10. Vì sao `JMSMessageID` không phù hợp làm business idempotency key khi producer resend sau failover? Mỗi publish mới có thể nhận một JMSMessageID khác; phải dùng `eventId` ổn định.

## 13. Tài liệu chính thức

- [ActiveMQ Classic — MasterSlave](https://activemq.apache.org/components/classic/documentation/masterslave): các kiểu shared store HA.
- [ActiveMQ Classic — Shared File System Master Slave](https://activemq.apache.org/components/classic/documentation/shared-file-system-master-slave): shared KahaDB, file lock, NFS/OCFS2 và scheduler.
- [ActiveMQ Classic — JDBC Master Slave](https://activemq.apache.org/components/classic/documentation/jdbc-master-slave): lock lúc startup, takeover và JDBC persistence.
- [ActiveMQ Classic — Pluggable Storage Lockers](https://activemq.apache.org/components/classic/documentation/pluggable-storage-lockers): `shared-file-locker`, `database-locker`, `lease-database-locker`, keepalive và clock skew.
- [ActiveMQ Classic — Failover Transport Reference](https://activemq.apache.org/components/classic/documentation/failover-transport-reference): reconnect, timeout và in-flight JMS transactions.
- [ActiveMQ Classic — JDBC Support](https://activemq.apache.org/components/classic/documentation/jdbc-support): adapter và cấu hình RDBMS.
- [ActiveMQ Classic — XML Configuration](https://activemq.apache.org/components/classic/documentation/xml-configuration): XBean/Spring namespace và `activemq.xml`.
- [ActiveMQ Classic — Release Status](https://activemq.apache.org/components/classic/download/): nhánh Classic, JMS API và yêu cầu JDK.

**Kết luận:** Shared-file-system master/slave dùng **file lock** trên **một KahaDB store**; JDBC master/slave dùng **DB lock hoặc DB lease** trên **một relational message store**. Cả hai yêu cầu **single writer**, client reconnect qua **Classic OpenWire Failover Transport**, backend storage tin cậy và fencing chống split-brain. Bài thử tốt phải chứng minh **chỉ một active → message đã commit còn đọc được sau takeover → message chưa ACK có thể redeliver → eventId/idempotency bảo vệ side effect**; không đồng nhất broker failover với exactly-once nghiệp vụ.

