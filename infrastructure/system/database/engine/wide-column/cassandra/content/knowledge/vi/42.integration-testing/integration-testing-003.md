# Phân biệt nút đã khởi động với dữ liệu đã phục vụ được ở CL yêu cầu trong Apache Cassandra

> **Chương:** Kiểm thử tích hợp  
> **Mục tiêu bài:** Thiết kế kiểm thử chứng minh **dữ liệu của một truy vấn/thao tác cụ thể thực sự được phục vụ ở consistency level (CL) đã cam kết**, thay vì chỉ kiểm Docker/container đã chạy, cổng 9042 đã mở hoặc driver tạo được `CqlSession`. Ví dụ dùng Apache Cassandra, CQL, Java 17, Java Driver 4.x, JUnit 5 và Testcontainers 2.x. Mọi thao tác thay topology/khởi động lại node chỉ dành cho cluster lab được phép.

## 1. Kết quả học tập

Sau bài này, người học có thể:

1. Phân biệt sáu tầng **process started → native transport reachable → CQL responsive → schema agreed → replica quorum reachable → business data visible**.
2. Giải thích vì sao `nodetool status` trả `UN` hoặc `SELECT release_version FROM system.local` thành công **không chứng minh** `LOCAL_QUORUM`/`QUORUM` cho mọi partition.
3. Tính số replicas cần phản hồi theo RF/CL, đặc biệt `ONE`, `LOCAL_ONE`, `QUORUM`, `LOCAL_QUORUM`, `EACH_QUORUM` và `ALL`.
4. Biết coordinator, natural replicas, token/partition key, local DC và node-state/gossip ảnh hưởng đến điều kiện kiểm thử.
5. Phân biệt **availability đạt CL** với **data đã stream/repair đúng** và **read-after-write thấy giá trị mong đợi**.
6. Chọn đúng *test oracle*: ghi một record bằng CL yêu cầu, đọc bằng CL yêu cầu và so giá trị/phiên bản nghiệp vụ, thay vì “không ném exception” là đủ.
7. Viết integration test Testcontainers Cassandra **một node** để xác minh CL ONE; thêm test âm với RF=2/CL TWO trên một node mà **không cần tắt máy**.
8. Biết khi nào một test đa node/đa DC là bắt buộc và vì sao single-node container không chứng minh điều kiện `LOCAL_QUORUM` RF3.
9. Thực hiện polling có deadline/backoff, phân biệt lỗi tạm thời khi startup với lỗi cấu hình/schema vĩnh viễn.
10. Xây dựng readiness gate cho bootstrap, replace, RF change, migration, restore/repair và rolling restart với metrics/rollback rõ ràng.

**Phạm vi `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`:** Cassandra là wide-column database phân tán, thiết kế bảng theo access pattern. Partition key xác định token/natural replicas; consistency level là hợp đồng read/write giữa coordinator và replicas. Java test chỉ đáng tin khi nó kiểm đúng **keyspace, table, token/partition, DC, CL và dữ liệu** của workload sẽ chạy trong production. `SPECIAL_NOTE` không có ràng buộc bổ sung.

## 2. Sáu tầng readiness: từ “lên process” tới “dữ liệu dùng được”

~~~text
L0  OS/Docker process RUNNING
       |
       v
L1  Native TCP port 9042 có listener / kết nối
       |
       v
L2  CQL coordinator đáp ứng system.local
       |
       v
L3  Schema đã được thống nhất, migration/table tồn tại
       |
       v
L4  Natural replicas của partition đủ số lượng/CL yêu cầu
       |
       v
L5  Write/read nghiệp vụ tại đúng CL thành công,
    giá trị/version/TTL/visibility đúng như oracle
       |
       v
PRODUCTION-READY theo một tập access patterns đã định
~~~

**Không được suy rằng tầng cao hơn tự động đúng khi tầng thấp hơn đã PASS.** Cổng 9042 có thể lắng nghe trước khi schema/data sẵn sàng. Một node `UN` có thể là coordinator dùng được, nhưng các replicas cần cho partition lại thiếu quorum. Cả ba node `UN` cũng **không chứng minh** vừa hoàn tất restore/repair hoặc dữ liệu hợp lệ sau migration.

### 2.1. Bảng tín hiệu và điều nó không chứng minh

| Tín hiệu quan sát | Kết luận hợp lệ | Kết luận **không** hợp lệ |
|---|---|---|
| Docker `running` | Container process còn sống | Cassandra đã sẵn sàng nhận CQL |
| TCP connect `:9042` thành công | Endpoint đang nhận kết nối | Auth/CQL/schema/replica read-write hoạt động |
| `cqlsh` mở session | Có ít nhất đường CQL hoạt động | Các token ranges đủ CL |
| `SELECT release_version FROM system.local` | Coordinator phục vụ local system table | User keyspace/table/ring đã phục vụ được |
| `nodetool status` báo `UN` | Node được nhìn thấy Up/Normal từ góc nhìn tool | Toàn bộ cluster đủ replicas cho mọi CL |
| Driver `CqlSession` được tạo | Có kết nối/metadata đủ để tạo client | Mọi query nghiệp vụ đều thành công |
| Schema agreement PASS | Các node **đang UP** thống nhất schema version | Node DOWN đã sẵn sàng, data đã được stream |
| `INSERT` ở `ONE` thành công | Có số ACK đáp ứng ONE | `QUORUM` read/write chắc chắn thành công |
| `SELECT` ở `LOCAL_QUORUM` không exception | Đủ responses để hoàn tất read này | Giá trị chắc đúng theo business expectation |
| Read sau write cùng PK tại CL yêu cầu và value đúng | Một test case thực đạt CL và oracle | Mọi partition/time/rack/traffic đều sẵn sàng |

### 2.2. Điểm kiểm thử phải có **ngữ cảnh**

Một mệnh đề readiness đầy đủ có dạng:

~~~text
Trong cluster C, local DC D, keyspace K (RF map R),
table T, query family Q trên partition key P,
với CLread=RCL và CLwrite=WCL,
trong timeout/deadline B,
write/read hoàn tất và dữ liệu khớp oracle O.
~~~

Thiếu **CL** thì chưa biết yêu cầu bao nhiêu replica. Thiếu **partition key** thì chưa biết natural replicas. Thiếu **DC/RF** thì không thể tính quorum tại vị trí kiểm thử. Thiếu **oracle** thì read trả 0 rows vẫn có thể là “success” về protocol nhưng sai nghiệp vụ.

## 3. Tầng process/port/CQL: những phép kiểm cơ bản

### 3.1. Container đã lên chỉ là điều kiện cần

~~~bash
docker ps
docker inspect cassandra-lab --format '{{.State.Running}}'
~~~

Hai lệnh chỉ đo Docker lifecycle. Cassandra còn phải khởi tạo JVM, system keyspaces, commitlog, memtables, gossip, token metadata, native transport, authentication, schema và các hoạt động streaming nếu vừa bootstrap/replace.

**Không** lấy container healthcheck đơn giản làm tín hiệu “data-ready ở CL QUORUM” khi healthcheck chỉ thử TCP/`cqlsh` vào `system.local`.

### 3.2. Kiểm native transport có chủ đích

~~~bash
# Trên môi trường Linux có cqlsh:
cqlsh 127.0.0.1 9042
~~~

~~~sql
SELECT cluster_name, data_center, release_version
FROM system.local;
~~~

Phép thử này hữu ích để phát hiện wrong port, TLS/auth, Cassandra chưa mở CQL hoặc driver không tương thích protocol. Nó đọc **system.local của coordinator**, không đọc dữ liệu nghiệp vụ ở replicas phân tán.

### 3.3. `nodetool status` và hai ký tự trạng thái

~~~bash
nodetool status
nodetool status my_keyspace
~~~

Trong cột đầu:

- `U` / `D`: node **Up/Down** theo góc nhìn trạng thái.
- `N` / `J` / `L` / `M`: node **Normal/Joining/Leaving/Moving**.
- `UN` = Up + Normal; `UJ` = Up + Joining; `DN` = Down + Normal.

Ví dụ minh họa:

~~~text
Datacenter: dc1
Status=Up/Down
|/ State=Normal/Leaving/Joining/Moving
--  Address       Load       Tokens  Owns ... Rack
UN  10.0.1.11     1.2 GiB    16      ...     rack1
UN  10.0.1.12     1.1 GiB    16      ...     rack2
DN  10.0.1.13     ?         16      ...     rack3
~~~

`nodetool status my_keyspace` giúp nhìn ownership theo replication của **keyspace cụ thể** thay vì một tỷ lệ chung không có nghĩa với các RF khác nhau. Tuy vậy, đây vẫn không phải phép thử write/read ở một CL, và trạng thái nhìn từ một node không bảo đảm mọi client/replica có cùng network reachability. Xem [nodetool status — DataStax OSS](https://docs.datastax.com/en/cassandra-oss/2.1/cassandra/tools/toolsStatus.html).

### 3.4. Driver nhận biết node khác với Cassandra gossip

Trong Java Driver 4.x:

~~~java
session.getMetadata().getNodes().values().forEach(node ->
    System.out.printf("node=%s state=%s distance=%s openConnections=%d%n",
        node.getEndPoint(),
        node.getState(),
        node.getDistance(),
        node.getOpenConnections()));
~~~

`getNodes()` chứa cả nodes đang down/ignored, **không** chỉ những nodes có connection. `Node.getState()` là đánh giá từ góc nhìn driver và có thể khác gossip nhất thời; `Node.getDistance()` còn liên quan load-balancing policy. Những dữ liệu này phù hợp chẩn đoán topology, **không thay** probe nghiệp vụ ở CL. [Driver Node metadata](https://apache.github.io/cassandra-java-driver/4.18.0/core/metadata/node/).

## 4. CL, RF và phép tính số ACK cần có

Gọi `N` là số **full replicas** của partition trong phạm vi CL đang xét. Với một DC có RF=3 full replicas:

\[
quorum(N) = \lfloor N/2 \rfloor + 1 = 2.
\]

### 4.1. Các CL thường gặp

| CL | Phạm vi | Điều kiện thông thường | Ghi chú |
|---|---|---|---|
| `ONE` | Natural replicas | ≥1 replica phản hồi | Có thể trả dữ liệu cũ ở đọc |
| `TWO` | Natural replicas | ≥2 replicas | RF1 không đạt nếu chỉ có 1 replica |
| `THREE` | Natural replicas | ≥3 replicas | Chỉ hợp lệ khi đủ replicas |
| `QUORUM` | Full replicas của partition trên toàn cluster | Đa số, `floor(total RF/2)+1` | Khác local quorum nếu nhiều DC |
| `LOCAL_ONE` | DC của coordinator | ≥1 local replica | Không chứng minh remote DC |
| `LOCAL_QUORUM` | DC của coordinator | Đa số full replicas tại DC đó | Ví dụ RF3 → 2 local |
| `EACH_QUORUM` | **Write** ở nhiều DC | Đa số full replicas tại **mỗi** DC | Không phải CL đọc thông thường |
| `ALL` | Toàn bộ natural replicas | Tất cả full replicas | Chịu lỗi node kém |
| `ANY` | **Write** | Replica ACK hoặc coordinator lưu hint | Read `ANY` không hợp lệ; hint không bằng dữ liệu đã tới replica |
| `SERIAL`/`LOCAL_SERIAL` | Paxos/LWT | Serial phase riêng | Không thay normal CL của toàn thao tác |

Khi có **transient replication**, cách đếm full/transient replicas và các CL hỗ trợ có ngoại lệ theo phiên bản/cấu hình; các ví dụ trong bài **giả định RF full replicas**, không lấy bảng trên làm bộ đếm cho transient setup. Xem [Apache Cassandra Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo).

### 4.2. Một DC RF3

~~~text
Keyspace NTS: dc1=3 full replicas
  r1 = UP    r2 = UP    r3 = DOWN

CL ONE          cần 1 -> có thể PASS
CL LOCAL_ONE    cần 1 -> có thể PASS
CL LOCAL_QUORUM cần 2 -> có thể PASS
CL QUORUM       cần 2 -> có thể PASS
CL ALL          cần 3 -> không PASS

Nếu thêm r2 DOWN:
CL ONE          vẫn có thể PASS
CL LOCAL_QUORUM không đủ -> UNAVAILABLE
~~~

**Không đồng nhất “UP” với “đã trả ACK”.** Các dòng trên chỉ đếm *known live replicas*. Khi network/storage bị chậm, coordinator có thể ban đầu thấy đủ nhưng sau đó nhận `ReadTimeoutException`/`WriteTimeoutException` vì không đủ responses đúng hạn.

### 4.3. Hai DC có RF khác nhau

Giả sử:

~~~text
dc1 RF3; dc2 RF2; tổng full RF=5

dc1: r1 UP, r2 UP, r3 DOWN
dc2: r4 UP, r5 DOWN
~~~

| CL | Cần bao nhiêu? | Kết quả khả dụng trong ví dụ |
|---|---|---|
| `LOCAL_QUORUM` từ dc1 | 2 ở dc1 | Có thể đạt |
| `LOCAL_QUORUM` từ dc2 | 2 ở dc2 | Không đạt |
| `QUORUM` | 3 trên tổng 5 | Có thể đạt với 2 dc1 + 1 dc2 |
| `EACH_QUORUM` cho write | 2 dc1 **và** 2 dc2 | Không đạt vì dc2 thiếu 1 |
| `ALL` | 5 | Không đạt |

Đây là lý do không thể dùng một test với `LOCAL_QUORUM` ở dc1 để công bố **dc2 cũng ready**. Coordinator DC, Java Driver `basic.load-balancing-policy.local-datacenter`, RF map và natural replica placement phải khớp.

### 4.4. `ANY` không phải cách kiểm data-readiness

Ở write `ANY`, Cassandra có thể xác nhận thành công khi **chỉ lưu hint** để chuyển mutation sau. Điều đó không chứng minh dữ liệu đã được phục vụ bởi replicas và đọc ngay lập tức sẽ thấy. Không dùng `ANY` làm readiness gate cho ứng dụng cần read-after-write, và đừng chuyển CL xuống ANY chỉ để test xanh.

## 5. Natural replicas theo token: cluster-wide UP không đủ

### 5.1. Mỗi partition có một replica set

~~~text
partition key: (tenant_id='t1', day=2026-11-21)
                      |
                partitioner hash
                      |
                    TOKEN
                      |
         keyspace replication strategy
                      |
          natural replicas for this token
            /           |           \
        node A        node C       node F
                      |
              CL determines ACK count
~~~

Node B có thể đang `UN` và trả `system.local` nhưng **không** phải natural replica cho token của t1/day. Nó chỉ có thể làm coordinator. Một node UP trong cluster không thay thế arbitrary replica cần cho `LOCAL_QUORUM`.

### 5.2. Test một partition chỉ chứng minh một lát cắt

Một probe trên partition `tenant=smoke` trả đúng data ở CL=QUORUM chứng minh **đường xử lý của token đó** tại thời điểm đó. Token khác có thể được đặt trên bộ replicas khác, node khác đang down hoặc bị streaming chậm. Readiness production nên có:

- Ít nhất các query families quan trọng của ứng dụng.
- Những **partition key xác định**, dữ liệu có oracle và TTL được kiểm.
- Có thể thêm **nhiều token ranges** đại diện nếu cluster lớn/đang thay topology.
- Phạm vi DC/rack và RF theo keyspace; không gọi “global ready” khi chỉ test một local DC.

### 5.3. Coordinator không nhất thiết là natural replica

Token-aware driver thường ưu tiên một node trong replica set, nhưng query plan/load balancing và network có thể chọn coordinator không sở hữu partition. Coordinator này sẽ chuyển read/write tới natural replicas. Vì vậy:

~~~text
Connected to node B?  -> Có.
Node B UN?             -> Có.
Node B là replica P?   -> Có thể KHÔNG.
CL của P đạt?          -> Phải kiểm actual replica responses.
~~~

Không gắn readiness với hostname/port duy nhất khi yêu cầu phục vụ dữ liệu là tính chất phân tán của **tập replica**.

## 6. “Có đủ live replicas” vẫn khác “đọc/ghi đã hoàn tất”

### 6.1. Hai phép kiểm khác nhau

**Topology-based expectation:**

~~~text
Theo metadata/gossip:
  natural replicas(P) = {A, B, C}
  local full replicas UP = {A, B}
  CL LOCAL_QUORUM RF3 requires 2
  ==> Có cơ hội đáp ứng CL (sufficient known-live).
~~~

**Request-based proof:**

~~~text
Java gọi INSERT / SELECT đúng partition P
  với LOCAL_QUORUM
  trong request timeout đã định
  và nhận ACK/rows với dữ liệu đúng
  ==> Request này đã đạt yêu cầu của test.
~~~

Điểm khác biệt:

- **`UNAVAILABLE`:** coordinator cho rằng không đủ live replicas để đạt CL **trước** hoặc khi xét phục vụ request.
- **`READ_TIMEOUT`/`WRITE_TIMEOUT`:** coordinator có đường xử lý nhưng không nhận đủ responses đúng thời hạn.
- **`READ_FAILURE`/`WRITE_FAILURE`:** replica/coordinator báo lỗi xử lý, không chỉ chậm.
- **`DriverTimeoutException`:** deadline **phía Java driver** hết trước khi có kết quả; có thể do queue, connection, network, retries hoặc server work.
- **`AllNodesFailedException`:** driver đã thử nhiều coordinators và ghi tập errors theo node; không đồng nghĩa mọi replica đều down.
- **`NoNodeAvailableException`:** không có coordinator khả dụng được thử; có thể do local DC/contact points/driver topology chứ chưa chứng minh data replicas không tồn tại.

### 6.2. Hai request giống CL có thể có kết quả khác

~~~text
Req 1: SELECT partition P1, CL LOCAL_QUORUM
       natural replicas A B C -> A+B healthy -> PASS

Req 2: SELECT partition P2, CL LOCAL_QUORUM
       natural replicas C D E -> only C healthy -> UNAVAILABLE

Req 3: SELECT partition P1, CL LOCAL_QUORUM
       A+B alive nhưng disk overloaded -> READ_TIMEOUT
~~~

Do đó liveness probe chỉ trả boolean `clusterAvailable=true` thường không đủ cho hệ thống nhiều token/rack. Tạo **matrix** theo keyspace/query family/CL và representative partitions.

### 6.3. Request-level success không tự bảo đảm SLA

Một request được ACK ở `LOCAL_QUORUM` sau 8 giây có thể thành công về CL nhưng **không đạt** API SLO 500 ms. Readiness gate nên kiểm đồng thời:

1. **Correctness:** đúng row/value/version của test oracle.
2. **Consistency:** read/write dùng đúng CL và local DC.
3. **Availability:** đủ replicas, không có unavailable/failure.
4. **Latency:** hoàn tất trong request deadline/SLO đã định.
5. **Sustainability:** retry/GC/disk/backlog không quá ngưỡng (với production canary).

Một phép kiểm `SELECT 1` thành công nhưng latency của query nghiệp vụ vượt deadline thì **không đủ để giao traffic thật**.

## 7. Khả dụng CL khác tính mới của dữ liệu và tính đúng nghiệp vụ

### 7.1. Read success có thể trả giá trị cũ

Giả sử RF3 tại một DC, write ở `ONE` và read ở `ONE`:

~~~text
Write value=PAID
  replica A ACK
  replicas B,C chưa có update

Read ONE từ B -> có thể thấy NEW

Cả write ONE và read ONE đều "thành công ở CL"
nhưng read-after-write không thấy PAID.
~~~

Vì vậy khi test **visibility**, không chỉ assert `row != null`: phải assert giá trị, version, event ID, timestamp hoặc điều kiện nghiệp vụ.

### 7.2. Quorum intersection — điều kiện cơ bản

Trong cùng tập N full replicas, nếu write cần W ACK và read cần R responses, điều kiện cổ điển:

\[
W+R>N
\]

giúp hai tập replica **giao nhau**, ví dụ RF3, W=2, R=2. Với Cassandra, đây là cơ sở của `QUORUM`/`LOCAL_QUORUM` read-after-write **trong phạm vi và giả định phù hợp**. Nó không tự cho tính tuyến tính hóa tuyệt đối khi có concurrent writes, đồng hồ không đồng bộ, mutations với timestamp, LWT hoặc các đường nhiều DC phức tạp. Xem [Apache Cassandra Dynamo](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo).

| RF | Write CL | Read CL | W+R > RF? | Diễn giải |
|---:|---|---|---|---|
| 3 | ONE (1) | ONE (1) | 2 > 3: không | Có thể đọc cũ |
| 3 | ONE (1) | QUORUM (2) | 3 > 3: không | Chưa có guarantee giao |
| 3 | QUORUM (2) | QUORUM (2) | 4 > 3: có | Giao nhau trong cùng replica set |
| 3 | ALL (3) | ONE (1) | 4 > 3: có | Write cực kém chịu lỗi node |
| dc1 RF3 | LOCAL_QUORUM (2) | LOCAL_QUORUM (2) | 4 > 3: có | Bảo đảm giao trong **dc1**, không mặc định dc2 |

### 7.3. Readiness check “read một row có sẵn” và “ghi rồi đọc” chứng minh điều gì?

**Kiểm read seeded data:**

- Xác nhận dữ liệu được nhập trước (snapshot/restore/migration) có thể đọc tại CL và value mong đợi.
- Phát hiện một số lỗi thiếu dữ liệu, sai partition/codec, tombstones, schema mismatch.
- Không chứng minh write path mới đang healthy.

**Kiểm write → read probe:**

- Xác nhận coordinator có thể ghi và đọc **record vừa ghi** trong keyspace/query path tại CL yêu cầu.
- Không chứng minh dữ liệu lịch sử đã migrate/repair xong.
- Không chứng minh tất cả token ranges đủ replica hoặc mọi dạng query/TTL/LWT chạy đúng.

Một readiness suite tốt dùng **cả hai** khi ứng dụng cần đọc dữ liệu lịch sử và ghi mới.

### 7.4. LWT và tính đúng điều kiện

Với nghiệp vụ cần atomic compare-and-set/uniqueness, một lần `INSERT ... IF NOT EXISTS` ở normal CL không tự kiểm được toàn bộ Paxos semantics. Phép thử cần chỉ rõ:

- **Normal CL** cho read/write phase, ví dụ `LOCAL_QUORUM`.
- **Serial CL** cho conditional transaction, ví dụ `LOCAL_SERIAL`.
- Kết quả `[applied]` và expected record/version; retry LWT cần cẩn trọng vì `[applied]=false` sau retry có thể nghĩa lần đầu đã commit.

Không dùng LWT trong readiness probe thường xuyên trên production nếu một INSERT/SELECT đơn giản đủ; tránh tạo thêm load và contention không cần thiết.

## 8. Schema agreement: cần nhưng chưa đủ

### 8.1. Vì sao DDL và dữ liệu có hai vòng đời

~~~text
CREATE TABLE t
     |
     v
Node A biết schema t
     |
Gossip/schema agreement
     |
Node B, C biết schema t
     |
------------------- Schema agreement PASS
     |
     v
Data ingest / bootstrap / restore / streaming / repair
     |
     v
Các partitions mong đợi đã được phục vụ
     |
------------------- DATA READINESS cần kiểm riêng
~~~

Driver 4.x thường **chờ schema agreement** sau DDL: khi tạo table thành công, coordinator có thể đã áp schema nhưng node khác chưa đồng bộ. Driver kiểm schema versions của các nodes **đang UP** và chờ trong giới hạn; nếu hết hạn, query DDL có thể complete với `isSchemaInAgreement=false`. Tuy nhiên, agreement PASS không có nghĩa **node đang DOWN** đã cập nhật hoặc dữ liệu đã được stream. [Driver schema agreement](https://apache.github.io/cassandra-java-driver/4.18.0/core/metadata/schema/).

### 8.2. Java kiểm schema agreement

~~~java
boolean agreed = session.checkSchemaAgreement();
if (!agreed) {
    throw new IllegalStateException(
        "Schema not agreed among currently UP nodes");
}
~~~

Sau DDL:

~~~java
ResultSet ddlResult = session.execute(
    "CREATE TABLE IF NOT EXISTS ready_lab.probe_by_bucket " +
    "(bucket text, id uuid, value text, " +
    "PRIMARY KEY ((bucket), id))");

if (!ddlResult.getExecutionInfo().isSchemaInAgreement()) {
    // Không ghi "data ready"; có thể poll agreement trong deadline.
    throw new IllegalStateException("DDL schema agreement not reached");
}
~~~

**Điểm tinh tế:** `ExecutionInfo.isSchemaInAgreement()` được kiểm **có ý nghĩa khi vừa thực thi DDL**. Theo Javadoc, với các query không thay schema, cờ này luôn trả true nên **không** được dùng `SELECT...getExecutionInfo().isSchemaInAgreement()` để chứng minh agreement thật. [Javadoc ExecutionInfo](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/cql/ExecutionInfo.html).

### 8.3. Snapshot metadata không tự cập nhật

~~~java
var oldSnapshot = session.getMetadata();

session.execute("CREATE TABLE IF NOT EXISTS ready_lab.probe_by_bucket "
    + "(bucket text, id uuid, value text, "
    + "PRIMARY KEY ((bucket), id))");

// WRONG: oldSnapshot có thể không phản ánh DDL vừa thực thi.
// var oldTable = oldSnapshot.getKeyspace("ready_lab")...

var freshSnapshot = session.getMetadata();
var keyspace = freshSnapshot.getKeyspace("ready_lab");
if (keyspace.isEmpty()) {
    throw new IllegalStateException("Keyspace not visible in driver metadata");
}
~~~

`Metadata` chủ yếu là immutable snapshot; phải gọi `session.getMetadata()` **mới** để thấy thay đổi. Dù metadata thể hiện table tồn tại, vẫn phải **execute query** trong integration test. [Driver metadata](https://apache.github.io/cassandra-java-driver/4.18.0/core/metadata/).

### 8.4. Schema agreement có thể gây “false green”

| Tình huống | Agreement | Data readiness? |
|---|---|---|
| 3 nodes UP, cùng schema, table mới trống | PASS | Không chứng minh historical data |
| 2 nodes UP, 1 node DOWN, hai node UP cùng schema | PASS có thể | Node DOWN chưa sẵn sàng |
| Sau restore SSTables, table metadata giống nhau | PASS | Dữ liệu restore có thể thiếu |
| Sau RF change, schema mới đã lan | PASS | Replicas mới chưa chắc đã chứa historical data |
| App query chỉ `system.local` | Không kiểm user table | Không chứng minh data path |

Không dùng schema agreement như một **“data synchronization complete”** signal.

## 9. Readiness contract cho integration test

### 9.1. Ví dụ contract cụ thể

~~~yaml
readiness_check:
  environment: staging
  cluster: orders-cassandra
  local_dc: dc1
  keyspace: orders_ks
  replication: {dc1: 3, dc2: 3}
  table: orders_by_id
  partition_pattern: tenant_id
  query_family: orders.getById
  expected_read_cl: LOCAL_QUORUM
  expected_write_cl: LOCAL_QUORUM
  required_value: status_and_revision_match
  require_schema_agreement: true
  max_total_wait: 60s
  per_attempt_timeout: 3s
  attempt_interval: 1s
  token_sampling: representative_partitions
  scope: dc1_only
~~~

Đây là ví dụ dữ liệu contract trong tài liệu, **không** phải file cần thêm vào repository. Thông số 60s/3s/1s chỉ để minh họa; test local và production readiness có budgets khác. Trong CI nên đủ để xử lý startup nhưng thất bại có giới hạn thay vì treo vô hạn.

### 9.2. Phân tách các gate

| Gate | Câu hỏi | Cách kiểm |
|---|---|---|
| G0 Process | Process/container tồn tại? | Docker/K8s process health |
| G1 Transport | CQL port mở, auth/TLS đúng? | Driver handshake/CQL |
| G2 Node | Node/ring có trạng thái mong đợi? | `nodetool status`/driver metadata |
| G3 Schema | Table/columns/UDT và schema agreement? | DDL result, `checkSchemaAgreement`, metadata |
| G4 CL availability | Query trên keyspace/partition tại CL yêu cầu có response? | Java `execute`/`setConsistencyLevel` |
| G5 Data oracle | Dữ liệu seeded/write/read khớp giá trị/version? | Assert content/PK/TTL/rows |
| G6 Stability | Qua một cửa sổ quan sát, success/error/p99 có bền? | Repeated bounded probes + metrics |

Với container một node phục vụ bài học CL ONE, G0–G5 có thể PASS. **Không được suy G4/G5 ở RF3 LOCAL_QUORUM** từ test đó.

### 9.3. Quy tắc pass/fail

~~~text
PASS:
  - đúng keyspace/schema
  - CQL read/write theo CL đã khai báo trả success
  - expected key/value/version khớp
  - elapsed <= deadline của test
  - không đổi CL để che lỗi

FAIL:
  - unavailable/timeout/invalid query/permission error
  - read success nhưng trả row cũ/NULL/sai revision
  - agreement không đạt trong budget yêu cầu
  - test bị skip vì điều kiện môi trường không khớp

INCONCLUSIVE:
  - write timeout/outcome unknown, chưa reconcile
  - driver mất kết nối trước khi biết server result
  - chaos test không có oracle/metrics đủ để xác nhận
~~~

Đừng biến `INCONCLUSIVE` thành PASS bằng `catch(Exception ignored)` hoặc retry vô hạn. Nếu write outcome chưa rõ, dùng **ID cố định của probe** và đối chiếu state thay vì tạo probe mới mỗi lần.

## 10. Lab CQL một node: chứng minh CL ONE nhưng không chứng minh CL TWO

**Mục tiêu:** Cùng một Cassandra node có thể trả `UN`/`system.local` OK, phục vụ `ONE` nhưng **không thể phục vụ TWO** trên keyspace RF2 nếu chỉ có một natural replica khả dụng. Không cần tắt node hoặc làm network lỗi.

### 10.1. Môi trường và giới hạn

- Cassandra 4.1 hoặc 5.0 **một node lab**, `cqlsh` hoạt động.
- Quyền tạo keyspace/table test; tuyệt đối không thực hiện trên production keyspace.
- `SimpleStrategy` chỉ dành lab; multi-DC production dùng `NetworkTopologyStrategy`.
- Tên DC thật lấy từ `system.local`/`nodetool status`; ví dụ JUnit sau dùng giá trị container trả về.

### 10.2. Keyspace RF1 — ghi/đọc ONE

~~~sql
CREATE KEYSPACE IF NOT EXISTS ready_one_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS ready_one_lab.probes_by_tenant_day (
  tenant_id text,
  day date,
  probe_id uuid,
  expected_value text,
  revision int,
  PRIMARY KEY ((tenant_id, day), probe_id)
);

CONSISTENCY ONE;

INSERT INTO ready_one_lab.probes_by_tenant_day
  (tenant_id, day, probe_id, expected_value, revision)
VALUES (
  'tenant-lab', '2026-11-21',
  11111111-1111-1111-1111-111111111111,
  'READY_ONE', 7
);

SELECT expected_value, revision
FROM ready_one_lab.probes_by_tenant_day
WHERE tenant_id = 'tenant-lab'
  AND day = '2026-11-21'
  AND probe_id = 11111111-1111-1111-1111-111111111111;
~~~

Kỳ vọng `READY_ONE`, revision `7`. Kiểm thử đã chứng minh một request write/read ở `ONE` với keyspace RF1 và record này. Nó **không** chứng minh khả năng chịu lỗi node hay CL của RF3.

### 10.3. Keyspace RF2 nhưng chỉ một node — test âm

~~~sql
CREATE KEYSPACE IF NOT EXISTS ready_two_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 2
};

CREATE TABLE IF NOT EXISTS ready_two_lab.probes (
  probe_id uuid PRIMARY KEY,
  expected_value text
);

CONSISTENCY ONE;

INSERT INTO ready_two_lab.probes
  (probe_id, expected_value)
VALUES (
  22222222-2222-2222-2222-222222222222,
  'WRITTEN_AT_ONE'
);

CONSISTENCY TWO;

SELECT expected_value
FROM ready_two_lab.probes
WHERE probe_id = 22222222-2222-2222-2222-222222222222;
~~~

Trên cluster **thực sự chỉ có một node**, SELECT ở `TWO` thường trả:

~~~text
Unavailable: Required 2 live replicas, but only 1 available
~~~

Phát biểu chính xác:

1. Cassandra node vẫn **running** và có thể `UN`.
2. CQL query ở `ONE` đã chạy thành công.
3. Một keyspace với RF2 có thể được khai báo nhưng **không có 2 replicas vật lý** trên cluster một node.
4. Vì thế request `TWO` **không đủ replicas** và thất bại đúng như dự đoán.
5. **Đây là test âm chủ đích**, không phải lỗi Docker/Testcontainers hoặc bug driver.

`CREATE KEYSPACE RF2` có thể cảnh báo rằng RF lớn hơn số nodes; không biến ví dụ đó thành cấu hình vận hành thật. Khi xong, dùng môi trường disposable/test namespace; không chạy `DROP KEYSPACE` tự động khi keyspace chứa dữ liệu không do test sở hữu.

### 10.4. Vì sao test này có giá trị học thuật?

Nó loại bỏ các biến khó kiểm soát như tắt mạng, disk overload, JVM GC pause. Dữ liệu vật lý chỉ có một node, nên **không có cách đạt hai replica ACK**. Ta chứng minh được:

\[
\text{node up} \not\Rightarrow
\text{data available at requested CL}.
\]

Trong production RF3/DC nhiều nodes, lỗi `UNAVAILABLE` còn có thể phụ thuộc *natural replica set*, coordinator view và DC/rack placement, nên một bài test RF2/lab chỉ là **minh họa nguyên lý**, không phải bài test chaos đầy đủ.

## 11. Java Driver 4.x: readiness probe phải đặt CL tường minh

### 11.1. Sai lầm thường gặp

~~~java
try (CqlSession session = CqlSession.builder().build()) {
    session.execute("SELECT release_version FROM system.local");
    System.out.println("Cassandra READY");
}
~~~

Code này chỉ chứng minh một coordinator có thể trả `system.local`. Driver default consistency có thể không trùng CL nghiệp vụ, và `CqlSession.builder().build()` còn phụ thuộc contact points/local DC/config loader. Đừng đưa thông báo “READY” vào load balancer chỉ từ phép kiểm trên.

### 11.2. Đặt CL ở statement

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Duration;
import java.time.LocalDate;
import java.util.UUID;

PreparedStatement read = session.prepare(
    "SELECT expected_value, revision " +
    "FROM ready_one_lab.probes_by_tenant_day " +
    "WHERE tenant_id = ? AND day = ? AND probe_id = ?");

BoundStatement request = read.bind(
        "tenant-lab",
        LocalDate.parse("2026-11-21"),
        UUID.fromString(
            "11111111-1111-1111-1111-111111111111"))
    .setConsistencyLevel(DefaultConsistencyLevel.ONE)
    .setTimeout(Duration.ofSeconds(2))
    .setIdempotent(true);

Row row = session.execute(request).one();
if (row == null
        || !"READY_ONE".equals(row.getString("expected_value"))
        || row.getInt("revision") != 7) {
    throw new IllegalStateException("Data oracle mismatch");
}
~~~

**Các điểm cần chú ý:**

- `setConsistencyLevel` được đặt **tường minh**; với lab RF1 dùng ONE.
- Prepared statement/BoundStatement dùng đúng partition key và CQL types (`String`/`LocalDate`/`UUID`).
- `setTimeout` đo deadline **client** cho request này; không biến server nào đó thành replica mới.
- `setIdempotent(true)` hợp lý cho SELECT read-only; không tự bật true cho mọi write.
- Assert cả **row content** chứ không chỉ `execute` không lỗi.
- Đừng coi một row read-back ở CL ONE là bằng chứng production LOCAL_QUORUM.

### 11.3. Nguyên lý với CL QUORUM

Khi có cluster đủ RF3 và local DC đã xác nhận, chính statement ấy có thể được kiểm với `DefaultConsistencyLevel.LOCAL_QUORUM`. Nhưng phải dùng **keyspace NTS RF3** và đủ full replicas trong local DC; **không đổi CL của lab RF1** rồi gọi failure là bug.

~~~java
BoundStatement productionRead = prepared.bind(
        tenantId, day, probeId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setTimeout(Duration.ofSeconds(3))
    .setIdempotent(true);
~~~

Snippet trên giả định `prepared` thuộc keyspace/table production phù hợp, chứ không phải `ready_one_lab` RF1. Khi chạy ngoài lab phải kiểm tenant authorization và bảo vệ probe IDs/values khỏi PII.

### 11.4. Không chỉ đặt CL ở read mà quên write

~~~java
BoundStatement write = insertPrepared.bind(
        tenantId, day, probeId, expectedValue, revision)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setTimeout(Duration.ofSeconds(3));

BoundStatement readBack = selectPrepared.bind(
        tenantId, day, probeId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setTimeout(Duration.ofSeconds(3));
~~~

Khi test read-after-write, phải ghi rõ **WCL và RCL**. Nếu ghi ở `ONE` rồi đọc `LOCAL_QUORUM` thì `W+R` có thể chưa vượt RF3; một lần read cũ không nhất thiết là Cassandra sai. Một ứng dụng sản xuất có thể chủ động dùng CL thấp, nhưng test oracle phải thiết kế theo **contract thật**, không lấy guarantee mạnh hơn bằng cách giả định.

## 12. Testcontainers 2.x + JUnit 5: kiểm thử end-to-end một node

### 12.1. Chọn phiên bản được kiểm soát

Testcontainers Java **2.x** chuyển module Cassandra sang `org.testcontainers.cassandra.CassandraContainer` và artifact `org.testcontainers:testcontainers-cassandra`. Các ví dụ Testcontainers 1.x cũ hay dùng `org.testcontainers.containers.CassandraContainer` và artifact `org.testcontainers:cassandra`; không copy hai thế hệ vào cùng một POM mà không kiểm.

Gradle Kotlin DSL minh họa:

~~~kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.12.2")
    testImplementation("org.testcontainers:testcontainers-junit-jupiter:2.0.5")
    testImplementation("org.testcontainers:testcontainers-cassandra:2.0.5")
    testImplementation("org.apache.cassandra:java-driver-core:4.18.1")
}

tasks.test {
    useJUnitPlatform()
}
~~~

JDK 17 và Docker daemon là tiền đề. Version ở ví dụ là bộ đã phát hành, không tự động có nghĩa **latest**. Trong dự án thật nên pin image Cassandra theo phiên bản/digest và quản lý dependency versions qua BOM để CI tái lập. Xem [Testcontainers Cassandra module](https://java.testcontainers.org/modules/databases/cassandra/) và [Testcontainers 2.0 release](https://github.com/testcontainers/testcontainers-java/releases).

### 12.2. Test JUnit 5 hoàn chỉnh — positive ONE + negative TWO

~~~java
package example;

import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.DriverException;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.servererrors.UnavailableException;
import java.time.Duration;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.cassandra.CassandraContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
final class CassandraReadinessIT {
    @Container
    static final CassandraContainer CASSANDRA =
        new CassandraContainer(
            DockerImageName.parse("cassandra:4.1"));

    private static CqlSession session;

    @BeforeAll
    static void initSchema() {
        session = CqlSession.builder()
            .addContactPoint(CASSANDRA.getContactPoint())
            .withLocalDatacenter(CASSANDRA.getLocalDatacenter())
            .build();

        session.execute(
            "CREATE KEYSPACE IF NOT EXISTS ready_one_lab " +
            "WITH replication = {'class':'SimpleStrategy', " +
            "'replication_factor':1}");
        session.execute(
            "CREATE TABLE IF NOT EXISTS ready_one_lab.probes " +
            "(probe_id uuid PRIMARY KEY, expected_value text)");

        session.execute(
            "CREATE KEYSPACE IF NOT EXISTS ready_two_lab " +
            "WITH replication = {'class':'SimpleStrategy', " +
            "'replication_factor':2}");
        session.execute(
            "CREATE TABLE IF NOT EXISTS ready_two_lab.probes " +
            "(probe_id uuid PRIMARY KEY, expected_value text)");

        assertTrue(session.checkSchemaAgreement(),
            "Schema must be agreed before probes");
    }

    @AfterAll
    static void shutdown() {
        if (session != null) {
            session.close();
        }
    }

    @Test
    void nodeCanServeDataAtOne() {
        UUID id = UUID.fromString(
            "11111111-1111-1111-1111-111111111111");

        PreparedStatement insert = session.prepare(
            "INSERT INTO ready_one_lab.probes " +
            "(probe_id, expected_value) VALUES (?, ?)");
        BoundStatement write = insert.bind(id, "READY")
            .setConsistencyLevel(DefaultConsistencyLevel.ONE)
            .setTimeout(Duration.ofSeconds(3));
        session.execute(write);

        PreparedStatement select = session.prepare(
            "SELECT expected_value FROM ready_one_lab.probes " +
            "WHERE probe_id = ?");
        BoundStatement read = select.bind(id)
            .setConsistencyLevel(DefaultConsistencyLevel.ONE)
            .setTimeout(Duration.ofSeconds(3))
            .setIdempotent(true);

        Row row = session.execute(read).one();
        assertNotNull(row, "Probe row must be visible");
        assertEquals("READY", row.getString("expected_value"));
    }

    @Test
    void oneNodeCannotSatisfyTwoForRfTwo() {
        PreparedStatement select = session.prepare(
            "SELECT expected_value FROM ready_two_lab.probes " +
            "WHERE probe_id = ?");
        BoundStatement request = select.bind(
                UUID.fromString(
                    "22222222-2222-2222-2222-222222222222"))
            .setConsistencyLevel(DefaultConsistencyLevel.TWO)
            .setTimeout(Duration.ofSeconds(3))
            .setIdempotent(true);

        DriverException error = assertThrows(
            DriverException.class,
            () -> session.execute(request));

        assertTrue(containsUnavailable(error),
            "Expected UNAVAILABLE because RF2 has only one live node, " +
            "got " + error.getClass().getName());
    }

    private static boolean containsUnavailable(Throwable error) {
        if (error instanceof UnavailableException) {
            return true;
        }
        if (error instanceof AllNodesFailedException all) {
            return all.getAllErrors().values().stream()
                .flatMap(java.util.List::stream)
                .anyMatch(CassandraReadinessIT::containsUnavailable);
        }
        return error.getCause() != null
            && error.getCause() != error
            && containsUnavailable(error.getCause());
    }
}
~~~

**Vì sao test âm phải kiểm lỗi cụ thể?** `assertThrows(RuntimeException.class)` mà không xem cause có thể PASS vì classpath/CQL syntax/auth lỗi, không hề chứng minh thiếu replicas. Hàm `containsUnavailable` kiểm `UnavailableException` trực tiếp **hoặc trong `AllNodesFailedException.getAllErrors()`**, tránh “false green”.

### 12.3. Kết quả kỳ vọng và giới hạn

| Test | Kỳ vọng | Chứng minh |
|---|---|---|
| `nodeCanServeDataAtOne` | PASS | CL ONE write/read đối với probe ở RF1 |
| `oneNodeCannotSatisfyTwoForRfTwo` | PASS khi nhìn thấy `UNAVAILABLE` | Dù node chạy và CQL reachable, RF2 một node không đạt CL TWO |
| `session.checkSchemaAgreement` | true | Schema UP nodes đã thống nhất |
| Một test `LOCAL_QUORUM` RF3 | **Không có trong suite** | Cần multi-node fixture thật |

**Không tạo cluster ba node bằng cách tạo ba `CassandraContainer` rời** rồi gọi đó là ring chung. Cần đồng bộ seed list, broadcast addresses, DC/rack, ports, token/streaming và network; multi-node test đáng tin nên dùng fixture/operator/Compose đã được kiểm. Không chạy Gradle/Testcontainers trong bước viết tài liệu này; các lệnh là hướng dẫn người học chạy ở môi trường phù hợp.

### 12.4. Testcontainers container-ready không phải business-ready

Testcontainers CassandraModule có wait strategy để đợi container sẵn sàng theo điều kiện module; `CASSANDRA.isRunning()` và việc `new CqlSession` thành công có giá trị bootstrap. Tuy nhiên **chỉ** test `nodeCanServeDataAtOne` mới thêm lớp “CQL data oracle tại CL”; test thứ hai chứng minh điều kiện CL mạnh hơn có thể thất bại mặc dù container đã qua wait strategy.

## 13. Multi-node integration test: thật sự kiểm LOCAL_QUORUM RF3

### 13.1. Fixture phải là một cluster đúng nghĩa

Một fixture ba nodes cho `LOCAL_QUORUM` cần đồng thời:

1. Ba Cassandra processes thuộc **cùng cluster name/ring**, không phải ba standalone clusters.
2. Seed list, internode/broadcast addresses, snitch/DC/rack và port mappings tương thích network.
3. Keyspace `NetworkTopologyStrategy` với `dc1:3`, đủ **3 full replicas** trong dc1.
4. Các nodes ở trạng thái ổn định (thường `UN`), **không có JOINING/LEAVING/MOVING bất ngờ**.
5. Schema agreement theo các nodes UP, DDL/migration hoàn tất.
6. CQL access từ JVM tới **địa chỉ được quảng bá** phù hợp, không chỉ tới host 127.0.0.1 của một container.
7. Read/write statement ở `LOCAL_QUORUM` **và assert data oracle**.

**Testcontainers multi-node không tự nhiên có** khi gọi `new CassandraContainer(...)` ba lần. Nếu không có fixture đã được kiểm, dùng cluster staging chuyên cho integration tests hoặc Docker Compose/Kubernetes operator test cluster có network/DC wiring đúng.

### 13.2. CQL khởi tạo fixture RF3 (chỉ trên cluster lab 3 nodes)

~~~sql
CREATE KEYSPACE IF NOT EXISTS ready_quorum_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS ready_quorum_lab.orders_by_tenant (
  tenant_id text,
  order_id uuid,
  status text,
  revision int,
  PRIMARY KEY ((tenant_id), order_id)
);
~~~

Trước khi dùng dữ liệu test, kiểm:

~~~bash
nodetool status ready_quorum_lab
nodetool describecluster
nodetool netstats
~~~

Nếu có node `UJ` hoặc `DN`, quyết định có nên cho phép test `LOCAL_QUORUM` chạy phải dựa trên **kịch bản cụ thể**: một node DOWN ở RF3 vẫn có thể đạt LOCAL_QUORUM (2 ACK), nhưng test **“all nodes ready before rollout”** cần stricter gate. Đừng ngầm đồng nhất “all UN” với điều kiện tối thiểu đạt quorum.

### 13.3. Java probe RF3 LOCAL_QUORUM

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Duration;
import java.util.UUID;

// Giả sử session đã kết nối cluster 3-node trong dc1
// và ready_quorum_lab thật sự có RF3 với NTS.
UUID orderId = UUID.fromString(
    "33333333-3333-3333-3333-333333333333");

PreparedStatement upsert = session.prepare(
    "INSERT INTO ready_quorum_lab.orders_by_tenant " +
    "(tenant_id, order_id, status, revision) " +
    "VALUES (?, ?, ?, ?)");

BoundStatement write = upsert.bind(
        "tenant-smoke", orderId, "PAID", 42)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setTimeout(Duration.ofSeconds(3));

session.execute(write);

PreparedStatement getOne = session.prepare(
    "SELECT status, revision FROM ready_quorum_lab.orders_by_tenant " +
    "WHERE tenant_id = ? AND order_id = ?");

BoundStatement read = getOne.bind("tenant-smoke", orderId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setTimeout(Duration.ofSeconds(3))
    .setIdempotent(true);

Row row = session.execute(read).one();
if (row == null
        || !"PAID".equals(row.getString("status"))
        || row.getInt("revision") != 42) {
    throw new AssertionError("LOCAL_QUORUM data oracle failed");
}
~~~

Một PASS cho biết **truy vấn probe này** hoạt động ở LOCAL_QUORUM RF3 trong dc1, bao gồm đường ghi và đọc. Nhưng một smoke probe đơn không thay thế toàn bộ token-range coverage, consistency test cho writes cạnh tranh hay quy trình khôi phục dữ liệu trước đó.

### 13.4. Test availability khi một node DOWN — chỉ trong fixture có quyền

Với RF3 và local quorum=2:

| Trạng thái replicas của partition P | Kỳ vọng ở LOCAL_QUORUM |
|---|---|
| A/B/C UP và phản hồi đúng hạn | PASS |
| A/B UP, C DOWN | Có thể PASS nếu A/B healthy |
| Chỉ A UP | UNAVAILABLE |
| A/B UP nhưng B không trả trong timeout | Có thể READ_TIMEOUT/WRITE_TIMEOUT |

**Không** thực hiện `nodetool stop`/`docker kill` trên production chỉ để kiểm test. Khi test được chạy trong fault-injection staging, cần ghi **replica đã dừng**, token owner chính xác, baseline read/write, expected error và recovery; nếu không, việc tắt node **không thuộc replica set** của probe có thể chẳng thay đổi kết quả.

### 13.5. Kiểm nhiều partition representative

~~~text
Probe P1 -> natural replicas A,B,C
Probe P2 -> natural replicas B,C,D
Probe P3 -> natural replicas C,D,E
...

Mỗi probe:
  write(WCL) -> read(RCL) -> assert value/revision
  capture coordinator, latency, retry/error types
~~~

Nên dùng một danh sách partition IDs cố định/kiểm soát, bao phủ các rack/token ranges quan trọng, để test có khả năng tái hiện. Không tạo hàng triệu partitions rồi gọi readiness mỗi giây; đó là workload test/soak test riêng.

## 14. Startup race và polling có deadline

### 14.1. Tại sao `Thread.sleep(10000)` là cách yếu?

~~~java
container.start();
Thread.sleep(10_000);
session.execute("SELECT release_version FROM system.local");
~~~

Ở máy dev, 10 giây có thể dư; ở CI cold Docker, chậm disk hoặc JVM startup có thể chưa đủ. Ngược lại, nếu đã sẵn sàng sau 1 giây thì chờ thêm 9 giây vô ích. **Không** dùng sleep cố định để chứng minh data readiness.

### 14.2. Bounded polling đúng nghĩa

~~~java
import java.time.Duration;
import java.util.concurrent.Callable;
import java.util.concurrent.locks.LockSupport;

public final class ReadinessAwait {
    private ReadinessAwait() {}

    public static void until(
            String description,
            Duration totalBudget,
            Duration interval,
            Callable<Boolean> probe) throws Exception {

        long deadline = System.nanoTime() + totalBudget.toNanos();
        Throwable lastTransient = null;
        int attempts = 0;

        while (System.nanoTime() < deadline) {
            attempts++;
            try {
                if (Boolean.TRUE.equals(probe.call())) {
                    return;
                }
            } catch (com.datastax.oss.driver.api.core.servererrors
                    .UnavailableException transientUnavailable) {
                lastTransient = transientUnavailable;
            } catch (com.datastax.oss.driver.api.core
                    .DriverTimeoutException transientTimeout) {
                lastTransient = transientTimeout;
            }

            long nanosRemaining = deadline - System.nanoTime();
            if (nanosRemaining <= 0) {
                break;
            }
            LockSupport.parkNanos(
                Math.min(interval.toNanos(), nanosRemaining));
            if (Thread.interrupted()) {
                throw new InterruptedException(
                    "Readiness wait interrupted");
            }
        }

        AssertionError failure = new AssertionError(
            description + " not ready after " + attempts +
            " attempts within " + totalBudget);
        if (lastTransient != null) {
            failure.initCause(lastTransient);
        }
        throw failure;
    }
}
~~~

**Phân biệt lỗi tạm/vĩnh viễn:** Ví dụ chỉ bắt `UnavailableException` và `DriverTimeoutException`, không bao mọi exception vào vòng retry. Nếu CQL sai cú pháp, permission thiếu, table không tồn tại hoặc Java codec mismatch, test cần **fail-fast**. Một số driver errors có thể bị bọc trong `AllNodesFailedException`; production helper nên phân loại errors lồng nhau tường minh, tránh `catch(Exception ignored)`.

### 14.3. Đặt per-attempt timeout nhỏ hơn totalBudget

~~~java
BoundStatement probe = statement
    .setTimeout(Duration.ofSeconds(2));

ReadinessAwait.until(
    "orders_by_id LOCAL_QUORUM",
    Duration.ofSeconds(45),
    Duration.ofMillis(750),
    () -> {
        Row row = session.execute(probe).one();
        return row != null
            && "PAID".equals(row.getString("status"));
    });
~~~

Nếu app muốn hard deadline toàn suite, nên kiểm thời gian còn lại trước mỗi attempt và set request timeout không vượt remaining budget. Mẫu ở trên có thể vượt deadline một lần tối đa bằng **một attempt đang chạy**; nó là polling mẫu cho bài học, không phải scheduler có hard cancellation.

**Không làm polling trên driver Netty I/O thread.** Trong JUnit, callback đợi là blocking theo thiết kế test thread; với reactive/async production, dùng nonblocking scheduler và jitter thích hợp.

### 14.4. Poll read chứ không replay write bừa bãi

Nếu lần ghi probe đã timeout, outcome có thể unknown. Đừng đặt `session.execute(INSERT)` bên trong polling với một UUID **mới mỗi lần** để “đợi tới khi write thành công”. Nên:

1. Tạo **probe ID cố định** cho một run/attempt logic.
2. Ghi bằng WCL đã định; nhận success thì chuyển sang read polling.
3. Nếu write timeout/mất response, đánh dấu `UNKNOWN_OUTCOME`.
4. Kiểm lại theo PK bằng RCL/nguồn dữ liệu thích hợp trước khi quyết định replay.
5. Chỉ replay nếu upsert/idempotency contract đã được review.

### 14.5. Mẫu retry budget cho startup

| Lỗi | Có thể retry ngắn trong startup? | Ghi chú |
|---|---|---|
| TCP connection refused trong cửa sổ khởi động | Có giới hạn | Container/native port chưa mở |
| `UNAVAILABLE` khi đợi replicas UP | Có giới hạn | Nếu topology đang hội tụ |
| `READ_TIMEOUT` tạm thời | Có giới hạn, kiểm server metrics | Không retry vô hạn khi disk chậm |
| InvalidQuery / unconfigured table ngay sau DDL | Chỉ sau khi kiểm schema agreement | Có thể là schema chưa lan, nhưng query lỗi thật cần fail |
| Unauthorized / invalid credentials | **Không** | Sửa auth/RBAC |
| Sai local DC | **Không** | Sửa driver config |
| Wrong value/revision, đã hết stabilization window | **Không PASS** | Cần điều tra data/restore/repair |

## 15. Khi node đang JOINING, MOVING, LEAVING hoặc REPLACE

### 15.1. Các trạng thái topology là một tiến trình, không phải bằng chứng data-ready

~~~text
Node process starts
    |
Gossip joins ring (UJ có thể xuất hiện)
    |
Token ownership / streaming / bootstrap
    |
Node normal (UN)
    |
Data/replica CL service cần được kiểm thực tế
    |
Node traffic được promote theo readiness contract
~~~

Không dùng `UJ` làm “đã hoàn tất streaming”. Ngược lại, nếu node đã `UN`, vẫn cần kiểm Cassandra **đúng keyspace/token/CL**, đặc biệt khi replace, restore hoặc ingest đang chạy.

### 15.2. Node readiness và readiness của dịch vụ có thể khác nhau

Ví dụ RF3, một node C đang bootstrap:

- Dịch vụ có thể vẫn phục vụ `LOCAL_QUORUM` nhờ A+B mà **không cần** C.
- Không vì vậy mà C đã sẵn sàng nhận toàn bộ traffic/tokens mới.
- Không vì C chưa ready mà bắt buộc toàn bộ dịch vụ phải FAIL nếu hợp đồng cho phép degraded mode với đủ replicas.

Đặt riêng:

~~~text
node_ready_for_new_traffic
query_family_ready_at_CL
cluster_ready_for_next_topology_step
data_migration_complete
~~~

Bốn trạng thái có thể khác nhau cùng lúc. Một controller/operator tốt dùng nhiều gates, không chỉ một boolean `ready`.

### 15.3. Khi thêm node hoặc thay RF

Đối với keyspace có RF tăng từ 2 lên 3:

~~~text
ALTER KEYSPACE ... replication RF=3
             |
       Schema agreement
             |
    Natural replica mapping thay đổi
             |
 Existing SSTables phải được đưa tới replicas mới
             |
  Full repair/streaming theo runbook/phiên bản
             |
  Readiness probe seeded historical partitions
             |
       Hoàn thành migration gate
~~~

**Không giả định `ALTER KEYSPACE` tự sao chép đầy đủ historical data**. Sau RF change, phải thực hiện workflow đồng bộ dữ liệu/repair theo hướng dẫn phiên bản và kiểm dữ liệu thực tế. [Apache Cassandra Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) giải thích full repair thường cần để phân phối dữ liệu sau tăng RF. Một probe ghi **sau** RF change và đọc thành công không chứng minh tất cả record **trước** RF change đã có đủ bản sao.

### 15.4. Khi restore snapshot

Sau khi khôi phục SSTable/snapshot:

1. Xác minh keyspace/table/schema tương thích.
2. Xác minh các SSTables cần thiết đã được load/refresh đúng.
3. Nếu topology/RF thay đổi, có kế hoạch streaming/repair và verification riêng.
4. Đọc **sample seeded records từ thời điểm trước backup**, không chỉ tạo record mới.
5. Đối chiếu count/checksum/version theo partition/business oracle; CL đạt chưa đủ để kết luận data đầy đủ.

Một Cassandra node có thể `UN` và trả `SELECT release_version` trong khi nhiều partitions lịch sử còn chưa được restore. Đó là ví dụ rõ nhất của sự khác biệt **process readiness** và **data readiness**.

## 16. Test matrix cho các tình huống startup và dữ liệu

| Tình huống | Container/process | CQL local | Schema agreement | CL yêu cầu | Data oracle |
|---|---|---|---|---|---|
| Node đang bootstrap và chưa mở native port | RUNNING | FAIL | Chưa biết | FAIL | Chưa kiểm |
| Node UN đơn, RF1, ONE | RUNNING | PASS | PASS | PASS | Có thể PASS |
| Node UN đơn, RF2, TWO | RUNNING | PASS | PASS | **FAIL** | Không thể xác nhận ở TWO |
| RF3, 2 replicas healthy, LOCAL_QUORUM | RUNNING | PASS | Có thể PASS | Có thể PASS | Cần đọc/so |
| RF3, 1 replica healthy, LOCAL_QUORUM | RUNNING | PASS | Có thể PASS trên các UP | **FAIL** | Không chứng minh |
| Cluster 3 UN, bảng chưa tạo | RUNNING | PASS | Có thể PASS cho schema hiện tại | Query lỗi | FAIL |
| Cluster 3 UN, historical data chưa restore | RUNNING | PASS | PASS | Có thể PASS với row trống | **FAIL** nếu expected row missing |
| Cluster 3 UN, write ONE/read ONE | RUNNING | PASS | PASS | Hai calls có thể PASS | Có thể đọc cũ |
| NTS dc1 RF3 dc2 RF2, một dc2 node DOWN | RUNNING | PASS | Có thể PASS | dc1 LQ PASS, dc2 LQ FAIL | Khác theo DC |
| Full repair đang tải disk, replicas vẫn UP | RUNNING | PASS | PASS | Có thể timeout | Có thể sai SLO |
| App driver local DC cấu hình sai | RUNNING | Có thể truy cập seed | Không chắc | Routing/connection FAIL | Không đủ chứng minh |
| Auth role thiếu SELECT trên user table | RUNNING | `system.local` có thể PASS | PASS | Không thi hành được | FAIL |

**Lưu ý:** “Có thể PASS” là nhận định về **khả năng**. Muốn kết luận test đạt, phải chạy lệnh trên fixture thật và kiểm response/value, không chỉ suy từ bảng.

### 16.1. Test đối chứng cùng cluster

Một bộ thử tốt có **cặp đối chứng**:

~~~text
T1 - RF1 / CL ONE / 1 node:
  EXPECT_SUCCESS

T2 - RF2 / CL TWO / 1 node:
  EXPECT_UNAVAILABLE

T3 - RF3 / CL LOCAL_QUORUM / 3 nodes UP:
  EXPECT_SUCCESS

T4 - RF3 / CL LOCAL_QUORUM / 1 natural replica UP:
  EXPECT_UNAVAILABLE

T5 - RF3 / CL LOCAL_QUORUM / 2 natural replicas UP:
  EXPECT_SUCCESS_IF_RESPONSES_IN_DEADLINE

T6 - Restore test: schema agreed, seeded row absent:
  EXPECT_DATA_ORACLE_FAILURE
~~~

T3–T5 cần **multi-node fixture**. T4–T5 chỉ nên fault-inject trong staging riêng được phê duyệt, biết rõ replica assignment. T6 cần seed manifest, checksum hoặc source-of-truth; không phải chỉ `SELECT` một row tự tạo sau restore.

### 16.2. Điều kiện kiểm thử nào nên tách khỏi integration suite?

| Loại test | Mục tiêu | Chạy khi nào |
|---|---|---|
| Unit test Java | Mapper/codec/CL selection, không cần Cassandra | Mỗi commit |
| Single-node Testcontainers | CQL hợp lệ, migrations, RF1/ONE, oracle | CI thường xuyên |
| Multi-node integration | RF3 LOCAL_QUORUM, availability theo token | CI có hạ tầng phù hợp hoặc scheduled |
| Fault injection | Node/network/slow replica, retry/timeout | Staging có kiểm soát |
| Restore/repair rehearsal | Historical data integrity, RPO/RTO | Trước release/định kỳ |
| Production canary | Dữ liệu/độ trễ thật theo SLO | Deploy/traffic change, load rất nhỏ |

Đừng bắt mỗi pull request khởi động cluster 6 nodes nhiều DC nếu tổ chức không đủ tài nguyên CI; nhưng **cũng không được bỏ hẳn multi-node test** rồi tuyên bố RF/CL đã được chứng minh bởi single-node.

## 17. Kubernetes liveness, readiness và startup probes

### 17.1. Ba loại probe không cùng nghĩa

| Probe | Mục đích | Kiểm tra phù hợp |
|---|---|---|
| `startupProbe` | Cho phép Cassandra khởi động chậm trước khi áp liveness | Process/JVM/native transport cơ bản |
| `livenessProbe` | Xác định process bị kẹt và cần restart | Sức khỏe tiến trình, không phụ thuộc cluster-wide quorum quá nghiêm |
| `readinessProbe` | Quyết định có cho node/pod nhận traffic không | Phù hợp với vai trò node, nhưng không nhất thiết là business CL toàn cluster |

**Không đặt một bài đọc LOCAL_QUORUM trên dữ liệu user làm `livenessProbe` của mọi Cassandra pod.** Khi hai replicas tạm lỗi, nó có thể fail đồng loạt và Kubernetes restart các pods khỏe còn lại, làm outage trầm trọng hơn. Liveness kiểm **node process**, còn quorum readiness nên do service/operator/gateway tính từ **nhiều tín hiệu**.

### 17.2. Readiness với CQL coordinator khác service data readiness

Một node có thể mở CQL và trả system tables; nó không có đủ natural replicas cho mọi keyspace. Application load balancer nên:

- Kiểm session/connection và nodes usable.
- Có canary hoặc startup integration gate cho **keyspace/CL ứng dụng**.
- Theo dõi production error rate, p95/p99 và replica availability.
- Tách “node này nhận kết nối” khỏi “feature này được mở traffic với CL yêu cầu”.

Nếu operator quản lý Cassandra cung cấp các conditions riêng về bootstrap/repair/safe-to-drain, nên dùng chúng như nguồn dữ liệu bổ sung, nhưng vẫn kiểm **data oracle** cho migration/restore.

### 17.3. False restart loop do quorum readiness được dùng sai chỗ

~~~text
Node B DOWN
    |
Liveness A/C đọc LOCAL_QUORUM trên partition phụ thuộc B
    |
Một số probes timeout
    |
Kubernetes restart A/C dù A/C vẫn khỏe
    |
Replicas available giảm hơn
    |
Cluster outage lan rộng
~~~

Một availability test có thể dùng để **chặn rollout/promote traffic**, nhưng không nhất thiết nên dùng làm tiêu chí **kill pod**. Tách rõ hành động khi gate thất bại.

## 18. Readiness và admission control của ứng dụng Java

### 18.1. Ứng dụng có thể chạy HTTP trước khi Cassandra đủ CL

Một service Spring Boot có thể hoàn tất JVM startup, lắng nghe port 8080, trả `/health` 200 nhưng Cassandra keyspace chưa migrated hoặc thiếu local quorum. Để tránh false green:

~~~text
App boot
   |
JVM/HTTP basic startup
   |
Connect Cassandra
   |
Schema/CL/data readiness probe
   |
Enable business endpoints / traffic
   |
Observe ongoing errors and p99
~~~

Ứng dụng có thể mở `/live` sớm (cho orchestrator biết tiến trình còn hoạt động) nhưng `/ready` chỉ PASS khi **các phụ thuộc cần thiết** sẵn sàng ở mức phù hợp. Nếu một feature không phụ thuộc Cassandra, không nhất thiết đánh FAIL toàn service; dùng **dependency-aware degradation** và route gating theo thiết kế.

### 18.2. Không tạo session trong mỗi readiness request

~~~java
// SAI cho HTTP readiness được gọi mỗi giây:
public boolean isReady() {
    try (CqlSession s = CqlSession.builder().build()) {
        return s.execute("SELECT release_version FROM system.local")
            .one() != null;
    }
}
~~~

Mở/đóng session liên tục gây kết nối lại, metadata refresh, auth/TLS handshake, có thể làm Cassandra nghẽn ngay khi đang hồi phục. Sử dụng **một shared CqlSession** và đánh giá trạng thái/CL với tần suất có kiểm soát. Với liveness chỉ dùng trạng thái process, không gọi user data CQL.

### 18.3. Phân biệt fail-closed và degrade

| Use case | Khi Cassandra thiếu CL | Lựa chọn |
|---|---|---|
| Ghi giao dịch/tài chính | Không bảo đảm consistency contract | Fail closed, trả lỗi có mã, tránh ghi bừa |
| Read-only lịch sử không trọng yếu | CL mạnh tạm không đạt, cache còn hợp lệ | Có thể phục vụ stale cache nếu hợp đồng cho phép |
| API quản trị | Có quyền kiểm status nhưng không ghi | Cho phép read-only status route |
| Metrics/telemetry | Cần tránh làm xấu outage | Rate-limit health probe, dùng cached indicators |
| Batch worker | Chưa đủ quorum/repair | Pause job, checkpoint, resume khi gate PASS |

**Không tự giảm CL từ LOCAL_QUORUM xuống ONE** chỉ để readiness biến xanh, trừ khi nghiệp vụ đã quy định một chế độ degrade riêng và test rõ dữ liệu có thể stale/unknown.

## 19. Dữ liệu kiểm thử và test oracle: đừng đo “rỗng cũng OK”

### 19.1. Hai kiểu probe nên tách

| Kiểu probe | Dữ liệu ở đâu? | Chứng minh gì? | Hạn chế |
|---|---|---|---|
| **Synthetic write/read** | Test tạo row riêng, rồi đọc lại | Write/read path tại WCL/RCL đang xử lý được | Không chứng minh historical data đã tồn tại |
| **Seeded known-data read** | Manifest/snapshot/migration đã nhập từ trước | Dữ liệu trước đó nhìn thấy đúng value/version | Không chứng minh write path mới khỏe |
| **Real workload canary** | Key nghiệp vụ được cho phép kiểm | API query shape/latency gần production | Cần bảo vệ PII/side effects |
| **Token-range sample** | Tập probe IDs trải đều token/rack | Nhiều natural replica sets có thể phục vụ | Không chứng minh toàn bộ dữ liệu |
| **Checksum/count verification** | Dataset migration/backup | Phát hiện dữ liệu thiếu/biến đổi | COUNT(*) Cassandra có thể rất tốn, tránh full table scan |

Khi restore/migration, cần **seeded data** có oracle đến từ bên ngoài cluster đích (backup manifest, event source, audit log). Nếu test chỉ INSERT một row mới lên cluster sau restore, nó chỉ chứng minh data path mới — hoàn toàn có thể PASS khi 90% historical SSTables đang thiếu.

### 19.2. Tránh `COUNT(*)` toàn bảng để đo readiness

~~~sql
-- Không nên dùng làm liveness/readiness định kỳ:
SELECT COUNT(*) FROM huge_orders_table;
~~~

Cassandra không tối ưu global count trên hàng tỷ rows; query có thể quét nhiều partitions, tăng disk/CPU, kích hoạt page/timeout và gây vấn đề nặng hơn khi cluster đang phục hồi. Thay bằng:

- Kiểm **known partition keys** từ manifest và expected revision/hash.
- Kiểm **sample đủ đại diện** theo token/tenant/time buckets.
- Dùng **offline checksum/SSTable verification** và đối chiếu nguồn/đích cho migration quy mô lớn.
- Có tolerance/coverage và báo rõ phạm vi, không hứa “100% toàn bảng” khi chỉ sampling.

### 19.3. Seeded data có TTL hoặc tombstone

~~~text
Manifest expects:
  tenant = t1, order = o1, status = PAID
  created_at = T0
  TTL = 24h

Probe at T0+25h:
  row missing

Không kết luận ngay "node phục vụ không được CL":
  Có thể là TTL đã hết hạn đúng thiết kế.
~~~

Phép thử nên biết TTL, tombstone/delete và expected visibility tại thời điểm probe. Nếu muốn một sentry row lâu dài, dùng dataset được quản lý riêng, không auto-expire khi có nhu cầu kiểm historical restore. Ngược lại, synthetic writes dùng TTL giới hạn để tránh tích tụ vô hạn, nhưng TTL phải đủ dài để probe không hết hạn trong cửa sổ test.

### 19.4. Synthetic probe có thể gây tombstones

Một cách thường thấy:

~~~text
Readiness mỗi giây:
  INSERT probe -> SELECT probe -> DELETE probe
~~~

Lặp lại liên tục sẽ tạo mutation/tombstone churn, không phù hợp cho mọi API/tenant và có thể làm giảm hiệu năng cluster đang yếu. Lựa chọn khác:

- Kiểm chủ yếu bằng cached readiness + error metrics, probe nhẹ theo cadence.
- Dùng một bảng/partition thưa với IDs hữu hạn, TTL phù hợp.
- Không DELETE liên tục nếu có thể dùng TTL/cơ chế cleanup có kiểm soát.
- Giới hạn concurrency, không dùng probe hàng triệu lần.
- Không dùng production business row để test cập nhật/xóa.

### 19.5. Probe ID ổn định và rủi ro idempotency

Nếu write probe timeout và Java không biết coordinator đã ghi hay chưa, tạo ID mới rồi retry có thể tạo nhiều rows. Một integration test tốt:

~~~text
run_id = deterministic within one test run
probe_id = stable for this logical probe
written_revision = monotonic or fixed within run
write_outcome = ACK / UNKNOWN
readback = expected value / version / missing
cleanup = isolated by environment or bounded TTL
~~~

Khi có concurrent writes hay LWW timestamp conflicts, probe phải dùng khóa/value riêng, tránh đè lẫn bởi suite khác hoặc test chạy song song.

## 20. Java error taxonomy: “quorum không đạt” và “test setup sai”

### 20.1. Các exception không cùng bản chất

| Java Driver 4.x error | Lớp vấn đề | Chẩn đoán trước |
|---|---|---|
| `UnavailableException` | Không đủ live replicas so với CL tại coordinator | RF/DC/replica set/gossip liveness |
| `ReadTimeoutException` | Replica responses cho read không kịp | Read path, disk/GC/network, tombstones |
| `WriteTimeoutException` | ACKs cho write không kịp, outcome có thể unknown | Commitlog/memtable, disk/GC, CL/replicas |
| `ReadFailureException` | Replica read failure | Node logs/IO/repair |
| `WriteFailureException` | Replica write failure | Node logs/IO/commitlog |
| `DriverTimeoutException` | Deadline phía client/driver hết | Pool, queue, retry, network, server latency |
| `AllNodesFailedException` | Tập lỗi per-coordinator | `getAllErrors()`; có thể mixed causes |
| `NoNodeAvailableException` | Không có node usable trong query plan | Local DC/contact points/connection policy |
| `InvalidQueryException` | Query/schema không hợp lệ | Migrations/DDL/columns/type |
| `UnauthorizedException` | Role/grant không phù hợp | Test credentials/RBAC |
| Codec/marker mismatch | Java binding sai | DTO/CQL type/prepared metadata |

### 20.2. Xử lý lỗi tổng hợp theo node

~~~java
import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.metadata.Node;
import java.util.List;
import java.util.Map;

void reportSanitizedErrors(AllNodesFailedException error) {
    for (Map.Entry<Node, List<Throwable>> entry :
            error.getAllErrors().entrySet()) {
        Node node = entry.getKey();
        for (Throwable cause : entry.getValue()) {
            System.err.printf(
                "coordinator=%s type=%s%n",
                node.getHostId(),
                cause.getClass().getSimpleName());
        }
    }
}
~~~

`AllNodesFailedException` không chứng minh “tất cả Cassandra nodes chết”; nó có thể chứa node A `UNAVAILABLE`, node B connection error, node C read timeout. Một readiness suite phải giữ **nguyên nhân** thay vì ném `AssertionError("cluster not ready")` không kèm thông tin.

### 20.3. Failure reason mapping

~~~text
readiness test FAIL
        |
        +-- Không kết nối/session?
        |      -> Docker/startup/auth/TLS/contact point/local DC
        |
        +-- Invalid CQL/schema?
        |      -> Migration/DDL/schema agreement
        |
        +-- UNAVAILABLE?
        |      -> RF/CL/replica liveness/placement
        |
        +-- READ/WRITE TIMEOUT?
        |      -> Replica response deadline/disk/GC/queue
        |
        +-- Có row nhưng sai value?
        |      -> Wrong key/TTL/tombstone/repair/LWW/version
        |
        +-- Đúng value nhưng quá chậm?
               -> SLO/partition size/compaction/capacity
~~~

Không báo “Docker failed” khi container running nhưng request không đạt CL. Không báo “Cassandra unavailable” chung chung khi lỗi là Java driver **sai DC** hoặc schema thiếu table.

### 20.4. Retry startup khác retry nghiệp vụ

Một test có thể poll `UNAVAILABLE` chờ nodes hoàn tất bootstrap, nhưng **không** nên retry:

- Mọi exception vô hạn.
- `InvalidQuery` khi migration thực sự thiếu.
- `Unauthorized` do wrong credentials.
- `WriteTimeout` của thao tác không idempotent khi outcome chưa xác định.
- Query có data oracle mismatch mãi mãi như một lỗi “tạm” để chờ đến hết timeout rồi báo generic.

Retry được phép phải có **bounded attempts/deadline**, giữ last cause, telemetry về retries, và không làm tăng tải quá mức trên cluster đang khởi động.

## 21. Observability: đo cả liveness, CL và data path

### 21.1. Lớp tín hiệu

~~~text
CONTAINER
  process status / restart count / CPU/memory

NODE / GOSSIP
  nodetool status, ring, joining/leaving, repair/streaming

DRIVER
  nodes UP, connections, request/client timeouts
  retry/speculation, coordinator, pool in-flight

CASSANDRA SERVER
  ClientRequest.Read/Write Latency, Unavailables
  pending compaction, SSTables-per-read, tombstones, GC

BUSINESS PROBE
  WCL / RCL / partition sample, expected value/version
  pass/fail/unknown, elapsed latency
~~~

Mỗi lớp có câu hỏi riêng. Không dùng một số “ready=1” từ Docker thay cho dữ liệu từ Cassandra server, và không dùng metrics node báo UP để kết luận mọi keyspace/CL đều khả dụng.

### 21.2. Commands quan sát an toàn

~~~bash
nodetool status
nodetool status ready_quorum_lab
nodetool describecluster
nodetool netstats
nodetool tpstats
nodetool compactionstats
nodetool tablestats ready_quorum_lab.orders_by_tenant
~~~

Các lệnh trên đọc trạng thái, không tự repair/move/remove nodes. Chúng không cho câu trả lời trực tiếp “record X đã ghi ở CL=LOCAL_QUORUM hay chưa”; cần record-specific read/write oracle.

### 21.3. Driver metrics hữu ích

~~~hocon
datastax-java-driver {
  advanced.metrics {
    session.enabled = [
      connected-nodes,
      cql-requests,
      cql-client-timeouts
    ]
    node.enabled = [
      cql-messages,
      errors.request.unavailables,
      errors.request.read-timeouts,
      errors.request.write-timeouts,
      retries.total,
      pool.in-flight,
      pool.open-connections
    ]
  }
}
~~~

Các mục trên là **driver metric option names** theo nhóm 4.x; tên exported sang Prometheus/Dropwizard/Micrometer tùy backend. Việc bật config không bảo đảm metrics tự xuất nếu thiếu registry/reporter. Trước khi dùng dashboard làm release gate, phải xác minh series thực sự được scrape.

### 21.4. Bảng KPI của một readiness suite

| Chỉ số | Ý nghĩa | Chú ý |
|---|---|---|
| `process_up_ratio` | Số tiến trình còn chạy | Không đo CL |
| `node_state_UN_ratio` | Số node bình thường theo gossip | Không bảo đảm data đúng |
| `schema_agreement_success` | Schema của UP nodes thống nhất | Không đo historical data |
| `probe_success_by_cl` | Tỷ lệ probes thành công ở CL | Label CL/keyspace/query family, không raw key |
| `probe_value_mismatch` | Data oracle sai | Có thể là vấn đề nghiêm trọng dù CQL 200 |
| `probe_unavailable_count` | Thiếu replicas khi kiểm | Phân theo DC/CL |
| `probe_read_write_timeout_count` | Truy vấn không kịp deadline | Điều tra server và client |
| `probe_p95/p99_latency` | SLO probe | Không suy server latency bằng phép trừ p99 |
| `streaming/repair_backlog` | Data movement đang diễn ra | Không tự chứng minh bất kỳ row nào chính xác |
| `cql_messages/request` | Amplification do retry/speculation | Cần cùng scope/window |

**Tránh metric labels** gồm tenant ID, UUID của từng probe, raw token hoặc PII vì high cardinality và rò rỉ dữ liệu. Dùng query family, environment, keyspace, DC, CL và outcome type với tập giá trị hữu hạn.

## 22. Những biến dễ tạo “false green” trong integration test

### 22.1. CL âm thầm trở về default

~~~java
PreparedStatement p = session.prepare(
    "SELECT status FROM ready_quorum_lab.orders_by_tenant " +
    "WHERE tenant_id=? AND order_id=?");

// SAI: không đặt CL, phụ thuộc default execution profile.
Row row = session.execute(p.bind(tenantId, orderId)).one();
assertNotNull(row);
~~~

Nếu default profile là `LOCAL_ONE`, test trên **không kiểm LOCAL_QUORUM** dù PR đặt tên `readAtQuorum`. Cách sửa:

~~~java
BoundStatement checked = p.bind(tenantId, orderId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setIdempotent(true);
Row row = session.execute(checked).one();
~~~

Khi dùng named execution profiles, kiểm cả effective `REQUEST_CONSISTENCY` và mọi explicit statement override. Không chỉ xem text của `application.conf` vì system properties/programmatic loader có thể có precedence cao hơn.

### 22.2. Thay RF nhưng quên sửa phép tính

~~~text
Trước:
  dc1 RF=2 -> LOCAL_QUORUM requires 2

Sau:
  dc1 RF=3 -> LOCAL_QUORUM requires 2

Sau nữa:
  dc1 RF=4 -> LOCAL_QUORUM requires 3
~~~

Nếu test hardcode `required=2` cho mọi local quorum, RF4 với chỉ hai replicas UP sẽ bị đánh dấu PASS sai. Đọc metadata/schema replication và policy thực; với transient replication, cần thuật toán phù hợp chứ không dùng công thức full-RF đơn giản.

### 22.3. Đổi local DC nhưng test vẫn ở DC cũ

~~~text
Service mới deploy ở dc2
Driver config vẫn local-datacenter=dc1
Probe LOCAL_QUORUM thành công vì route tới dc1
=> Không chứng minh dịch vụ có thể phục vụ local quorum dc2.
~~~

Kiểm local DC thực của `CqlSession`, contact points, coordinator trong `ExecutionInfo` và Cassandra `system.local.data_center`; test theo từng vị trí deploy. `LOCAL_QUORUM` theo **coordinator local DC**, không tự đổi phạm vi theo mong muốn của người viết test.

### 22.4. Dữ liệu test cũ làm kết quả giả thành công

Nếu test dùng cùng `probe_id` trong một bảng persistent qua nhiều lần CI, row từ hôm trước có thể tồn tại:

~~~text
Run hôm nay:
  WRITE chưa thực sự thành công (outcome unknown)
  READ thấy row cũ == "READY"
  Test báo PASS sai.
~~~

Khắc phục bằng **run ID/revision unique** và kiểm expected version/timestamp. Với concurrent tests, dùng namespace/keyspace cô lập hoặc partition/ID riêng; khi retry cùng run thì giữ operation ID ổn định để tránh duplicate.

### 22.5. TTL khiến probe thiếu ngẫu nhiên

Read-after-write với TTL 1 giây và CI cold start 5 giây có thể fail dù replicas healthy. Một test readiness nên dùng TTL đủ lớn hoặc record không TTL có cleanup rõ; không dùng TTL quá nhỏ để ép test fail một cách không phản ánh production.

### 22.6. Driver retry che nút lỗi trong khi data vẫn đạt CL

Một request `LOCAL_QUORUM` có thể PASS sau khi retry coordinator B, trong khi coordinator A bị network-isolated:

~~~text
Result correctness PASS
Retry count > 0
Coordinator A errors > baseline
~~~

PASS theo **functional CL/data readiness** không nhất thiết là PASS theo **cluster health/SLO readiness**. Khi rollout, theo dõi retries, per-node failures, p99 và token/rack coverage. Không đánh dấu cả cluster hoàn toàn khỏe chỉ từ một success sau retry.

### 22.7. Read-your-writes bị hiểu vượt phạm vi

Nếu test W=`ONE`, R=`ONE` và thỉnh thoảng đọc được mới nhất, không được viết tài liệu “Cassandra luôn read-your-writes ở ONE”. Đó có thể do cùng coordinator/replica hoặc scheduling may mắn. Một test phải dựa vào **RF/CL contract**, không lấy một lần thành công làm định lý consistency.

### 22.8. Test trên `system.local` thay vì user keyspace

`system.local` là thông tin local node, không chịu cùng RF/quorum và dữ liệu như application keyspace. Nó rất tốt cho **liveness**, không đủ cho **business readiness**.

### 22.9. Dùng `nodetool status` từ đúng một node

Gossip liveness và network partitions có thể khiến các nodes nhìn khác nhau. Một output `UN` từ coordinator A không có nghĩa coordinator B/DC khác nhìn như vậy. Trong incident multi-DC, thu signals từ nhiều vantage points, đối chiếu driver node metadata, errors và actual CL queries.

### 22.10. Có đủ replica nhưng sai quyền CQL

Test chạy `cqlsh` bằng superuser có thể PASS, nhưng service role chỉ có SELECT trên system tables, không có quyền bảng nghiệp vụ. Readiness test nên chạy với **role/TLS/auth và execution profile giống ứng dụng**, không dùng credentials quản trị để hợp thức hóa môi trường.

## 23. Runbook readiness GO / HOLD / STOP

### 23.1. Preflight trước khi mở traffic hoặc nâng RF

1. **Xác định mục đích:** Cassandra node restart, thay RF, schema migration, restore, thêm DC hay deploy Java service.
2. **Chốt phạm vi:** Cluster, keyspace, DC/rack, query family, partition/token samples, CL read/write, RF map.
3. **Xác nhận topology:** `nodetool status <keyspace>`, nodes UP/DOWN/JOINING và streaming/repair plan.
4. **Xác nhận schema:** DDL result/schema agreement và driver metadata mới.
5. **Xác nhận data oracle:** Seeded historical samples nếu cần; synthetic WCL/RCL probe nếu cần write path.
6. **Đặt ngân sách:** Total deadline, per-attempt timeout, retry interval và max load.
7. **Bật metrics:** Client errors/retries/p95/p99 và server read/write latencies, GC/disk/compaction.
8. **Bảo vệ dữ liệu:** Read-only probes nơi có thể; synthetic write trong namespace/partition riêng, ID cố định và cleanup có kiểm soát.
9. **Bảo đảm rollback:** Có chủ thể chịu trách nhiệm và khả năng chặn rollout/gỡ routing trong khi điều tra.

### 23.2. Trình tự gate

~~~text
T0  Process/container started
        |
T1  Native CQL reachable + correct credentials/DC
        |
T2  Check nodetool/driver metadata node states
        |
T3  Check schema agreement + migrations
        |
T4  Check CL availability for representative keys
        |
T5  Verify seeded/historical oracle
        |
T6  Verify synthetic write/read at declared WCL/RCL
        |
T7  Observe stability for configured interval
        |
         +-------------------------------+
         |                               |
      ALL PASS                       FAIL/UNKNOWN
         |                               |
      GO canary                    HOLD/STOP rollout
         |                        classify cause
      Expand traffic                     |
         |                         Investigate/
      Recheck metrics                 reconcile
         |                               |
      Record evidence            Retest same contract
~~~

Mỗi gate phải biết **ai sở hữu** và lỗi nào được phép retry khi startup. Không để một check “đã mở TCP” bypass dữ liệu seed missing hoặc quota/CL chưa đạt.

### 23.3. Bảng quyết định

| Tín hiệu | Quyết định | Hướng giải quyết |
|---|---|---|
| Docker RUNNING, 9042 chưa mở | **HOLD** | Chờ bounded startup, xem logs |
| CQL `system.local` PASS, user table thiếu | **STOP** | Migration/schema agreement |
| RF3 LQ, chỉ 1 natural replica UP | **STOP** | Khôi phục replica, không giảm CL |
| RF3 LQ, 2 replicas UP, probe PASS, p99 ổn | **GO có kiểm soát** | Chấp nhận degraded mode theo SLO |
| LQ probe PASS nhưng historical row missing | **STOP** data restore gate | Restore/repair/manifest reconciliation |
| Query PASS ở CL ONE, production đòi LQ | **HOLD** | Chưa có bằng chứng đúng CL |
| `UNAVAILABLE` tạm trong bootstrap, budget còn | **HOLD và retry có giới hạn** | Theo dõi topology |
| `DriverTimeoutException` và disk/GC tăng | **HOLD** | Capacity/queue/I/O, không tăng retries vô hạn |
| Auth/role sai | **STOP** | Sửa RBAC, không retry |
| Probes PASS nhưng retries/connection churn tăng | **HOLD** | Điều tra sự cố ngầm trước mở rộng |
| Các token/DC samples đạt, p99 và oracle ổn định | **GO** | Mở rộng từng batch |

### 23.4. Rollback có nghĩa gì?

Rollback một **deployment config** không tự rollback các writes:

- Nếu Cassandra đã ghi một mutation trong khi test timeout, outcome có thể unknown; giữ operation ID và reconcile.
- Nếu RF/schema migration đã commit, “rollback Java service” không tự phục hồi data topology.
- Nếu node đã bắt đầu streaming/repair, không kill/stop tùy tiện; làm theo operator runbook.
- Nếu chỉ đổi health gate, đưa gate về phiên bản trước không giải quyết mất dữ liệu, nên lỗi data oracle vẫn cần điều tra.

Sau rollback, chạy **cùng contract** ở T4–T6, kiểm không còn missing data, và đợi SLO/resource trở lại vùng an toàn. Đừng chỉ đọc file config đã sửa rồi đánh dấu `ROLLBACK_COMPLETE`.

### 23.5. Phiếu kiểm chứng sau deploy

~~~text
CHANGE_ID:
SERVICE / LOCAL_DC:
CASSANDRA VERSION / JAVA DRIVER VERSION:
KEYSPACE / RF PER DC:
QUERY FAMILY / TABLE:
SAMPLED TOKEN RANGES / PARTITION COUNT:
WCL / RCL:
SCHEMA AGREEMENT (UP nodes):
NODE STATUS / STREAMING / REPAIR:
SEEDED DATA ORACLE:
SYNTHETIC WRITE-READ ORACLE:
TIMEOUT / ERRORS / RETRIES:
P95/P99 / SERVER RESOURCE:
GO / HOLD / STOP:
UNRESOLVED UNKNOWN OUTCOMES:
OWNER / UTC TIME / NEXT ACTION:
~~~

Mẫu này là checklist trong tài liệu, không phải file cần tạo. Kết luận chính xác nên là **“ready cho query family X ở CL Y trên samples Z, trong thời điểm T và SLO B”** thay vì “Cassandra ready 100%” vô điều kiện.

## 24. Các ca kiểm thử và sự cố thực tế

### Ca A — Docker health check xanh, Java kết nối 9042 lỗi

**Dấu hiệu:** Container chạy, log Cassandra có “startup complete”, nhưng driver báo connection refused hoặc TLS handshake exception.

**Phân tích:** Healthcheck có thể chỉ kiểm process hoặc JMX; native transport có thể chưa mở, IP/port mapping sai, SSL yêu cầu client certificate hoặc firewall vẫn chặn.

**Test:** Dùng đúng `getContactPoint()` của Testcontainers hoặc endpoint từ service discovery, local DC thật, credentials/TLS giống ứng dụng. Không chuyển sang kiểm CL trước khi CQL connectivity được xác nhận.

### Ca B — `system.local` trả 1 row, bảng ứng dụng chưa tồn tại

**Dấu hiệu:** `SELECT release_version FROM system.local` PASS, `SELECT ... FROM orders_by_id` trả `unconfigured table`.

**Nguyên nhân:** Migration chưa chạy/schema chưa lan hoặc sai keyspace. Đây là vấn đề G3, chưa tới G4/G5.

**Quyết định:** STOP route liên quan user table; chờ bounded schema agreement/kiểm DDL, không retry vô hạn cùng query sai.

### Ca C — Một node Cassandra RF1/ONE chạy tốt, team tuyên bố “quorum tested”

**Sai:** RF1/ONE chỉ cần một replica; không thử network gossip giữa các replicas.

**Đúng:** CI single-node chỉ kiểm CQL/mapper/migration; đánh dấu riêng multi-node RF3 LOCAL_QUORUM chưa chạy. Một phép thử âm RF2/TWO trên một node có thể **minh họa nguyên lý** nhưng không thay test đa node.

### Ca D — Single-node RF2, CQL port mở và CL TWO trả UNAVAILABLE

**Kết luận:** Đây là **hành vi mong đợi** vì keyspace định nghĩa 2 full replicas nhưng chỉ có một physical node. Không tăng request timeout 2s lên 30s với hy vọng có replica thứ hai.

**Test:** Assert loại lỗi `UnavailableException` cụ thể, kể cả khi bọc trong `AllNodesFailedException`.

### Ca E — RF3, hai replicas UP, một DOWN, LOCAL_QUORUM vẫn PASS

**Kết luận:** Service vẫn có thể phục vụ CL=2 tại token đó. Tuy nhiên node DOWN vẫn cần recovery, và nếu thêm một node mất thì quorum sẽ không đạt.

**Quyết định:** GO degraded/canary nếu nghiệp vụ/SLO cho phép; HOLD bước topology tiếp theo. Không đánh dấu “all nodes ready”.

### Ca F — RF3, cả ba nodes UN nhưng READ_TIMEOUT

**Phân tích:** Gossip/driver nhìn thấy nodes UP; I/O/GC/compaction/queue khiến không đủ ACK đúng hạn. `UN` không bảo đảm phản hồi trong deadline.

**Test:** Đo server read latency, SSTables-per-read, tombstones, disk await và request timeout; tránh chờ vô hạn hoặc giảm CL khi dữ liệu cần LQ.

### Ca G — RF3, write ONE thành công, read ONE trả NEW thay vì PAID

**Phân tích:** W=1, R=1 không có quorum intersection guarantee; một replica khác có thể trả phiên bản cũ.

**Test:** Không dùng kỳ vọng mạnh hơn contract. Nếu hệ thống cần read-your-writes trong local DC, xem WCL/RCL LOCAL_QUORUM và business concurrency/version policy.

### Ca H — Ghi và đọc LOCAL_QUORUM đều không lỗi, nhưng status sai

**Nguyên nhân:** Có thể ghi vào sai partition, codec/binding đảo hai String, LWW timestamp từ một writer khác thắng, hoặc test đọc row cũ.

**Quyết định:** FAIL G5 data oracle, dù G4 CL availability PASS. Đối chiếu primary key, revision/timestamp, source events, schema và access pattern.

### Ca I — Nâng RF2 lên RF3, schema agreement PASS, historical record vẫn thiếu

**Nguyên nhân:** Schema replication đã đổi, nhưng historical SSTable replicas mới có thể chưa được phân phối/repair đầy đủ.

**Test:** Dùng **seeded historical keys** của nhiều token ranges; kiểm streaming/repair theo runbook và giá trị/versions. Không chỉ tạo row mới rồi đọc ngay.

### Ca J — Restore snapshot, tất cả nodes UN, probe mới PASS nhưng dữ liệu cũ missing

**Phân tích:** New write/read path hoạt động, nhưng snapshot/import có thể thiếu SSTables, sai keyspace/schema hoặc restore chưa đầy đủ.

**Quyết định:** STOP “restore complete”, so manifest/checksums/time coverage và sample by token range; đừng dùng `CREATE TABLE`/`system.local` làm chứng cứ khôi phục.

### Ca K — dc1 RF3 và dc2 RF2, dc2 mất một node

**Tín hiệu:** `LOCAL_QUORUM` từ dc1 có thể PASS, từ dc2 FAIL. `QUORUM` toàn cluster có thể PASS nếu còn ≥3/5 replicas; `EACH_QUORUM` cho write cần ≥2/3 dc1 **và** ≥2/2 dc2, nên FAIL.

**Bài học:** Readiness phụ thuộc **CL + DC + RF map**, không phải số nodes UP tổng chung.

### Ca L — Driver Java local DC nhầm sau chuyển vùng

**Dấu hiệu:** Cassandra dc2 nodes UN nhưng driver không tạo usable connections hoặc route vào dc1. Một cqlsh kiểm tại dc2 có thể PASS trong khi Java FAIL.

**Test:** Dùng đúng driver config trong service, đọc `getMetadata().getNodes()` và coordinator/host errors, xác minh `basic.load-balancing-policy.local-datacenter`. Không đổ lỗi data replicas trước khi sửa routing.

### Ca M — Test dùng superuser, production role thiếu SELECT

**Dấu hiệu:** CI health probe PASS nhưng service trả `UnauthorizedException`.

**Nguyên nhân:** Test không dùng credentials/RBAC của ứng dụng.

**Quyết định:** Thêm integration probe với test role tối thiểu tương đương, không cấp superuser cho app để làm xanh readiness.

### Ca N — JUnit test flake vì `Thread.sleep(10000)`

**Dấu hiệu:** Pass laptop, fail CI cold Docker, retry CI lại pass.

**Nguyên nhân:** Startup timing khác nhau; sleep cố định không dựa vào điều kiện.

**Test:** Thay bằng bounded polling đúng keyspace/CL/data oracle, per-attempt timeout + last error. Với Testcontainers, tận dụng module wait strategy nhưng vẫn thêm business assertion.

### Ca O — Test lặp làm sai vì probe từ run trước

**Dấu hiệu:** Write hôm nay timeout nhưng read thấy `READY` và suite PASS.

**Nguyên nhân:** Probe ID/value cố định tồn tại từ run trước, không kiểm revision/run ID.

**Test:** Dùng revision/run ID riêng cho run hiện tại, giữ ID cố định **trong lần retry đó**, tránh chồng giữa concurrent suites.

### Ca P — LWT uniqueness test dùng SELECT thay cho CAS result

**Dấu hiệu:** SELECT thấy row, team kết luận `INSERT IF NOT EXISTS` đã apply trong request hiện tại.

**Nguyên nhân:** Row có thể đến từ request trước/concurrent actor. LWT cần xem `[applied]` và normal/serial CL, đặc biệt khi retry sau timeout.

**Test:** Kiểm CAS result, row version, business operation ID và re-read nếu outcome ambiguous; không suy transaction success chỉ từ row tồn tại.

### Ca Q — Đọc health bằng `COUNT(*)` khiến node vừa phục hồi lại timeout

**Nguyên nhân:** Query quét nhiều partitions/tombstones, tăng disk/CPU và p99 trong giai đoạn recovery.

**Thay:** Known-key probes và checksum từ manifest/offline validation; giảm cadence, tránh quét toàn bảng theo health request.

### Ca R — Kubernetes liveness gắn LOCAL_QUORUM làm các pod restart dây chuyền

**Dấu hiệu:** Một replica DOWN → quorum health fail → orchestrator restart những nodes vẫn khỏe.

**Sửa:** Liveness chỉ kiểm process; readiness/traffic gate theo dependency và CL, không dùng availability cluster-wide làm lý do kill từng node.

### Ca S — Retry policy giúp test PASS nhưng p99 vượt SLO

**Nguyên nhân:** Driver đổi coordinator/retry sau timeout, request cuối thành công nhưng mất quá nhiều thời gian. Node lỗi vẫn tồn tại.

**Test:** Assert elapsed time/SLO, đo retries, cql-messages và server resource. Có thể HOLD dù functional oracle PASS.

### Ca T — Node ở `UJ`, một số token ranges vẫn đang stream

**Dấu hiệu:** CQL đã nhận query nhưng probe ở token A PASS, token B có latency/error.

**Phân tích:** Bootstrap/streaming chưa xong hoặc replica placement đang hội tụ.

**Quyết định:** Không promote node mới chỉ từ TCP/`UN` snapshot; theo dõi streaming/topology và chạy multi-token data probes. Không dừng bootstrap/repair tùy tiện để “giảm tải”.

## 25. Checklist nghiệm thu tích hợp

### 25.1. Environment và topology

- [ ] Cassandra/version/driver/Testcontainers versions được pin và ghi lại.
- [ ] Docker container là một cluster thật hay chỉ single-node fixture — đã công bố rõ.
- [ ] Contact points, advertised addresses và port mapping hợp lệ.
- [ ] Driver local DC đúng DC của service; auth/TLS/role giống production semantics.
- [ ] `nodetool status`/driver metadata không bị hiểu nhầm với data readiness.
- [ ] Keyspace replication strategy và RF map theo DC đã được đọc lại.
- [ ] Full/transient replicas được phân biệt khi có transient replication.
- [ ] Không có topology change/streaming chưa được tính vào scope.
- [ ] Có bản đồ representative partitions/token ranges và expected replica sets.

### 25.2. Schema và dữ liệu

- [ ] DDL/migrations đã chạy theo thứ tự; schema agreement được kiểm ở **UP nodes**.
- [ ] Không dùng `ExecutionInfo.isSchemaInAgreement` của SELECT làm bằng chứng DDL agreement.
- [ ] Metadata driver được refresh/fetch lại sau schema change.
- [ ] Table/columns/UDT/index phù hợp đúng CQL/Java codec.
- [ ] Có seeded historical data oracle nếu đang restore/migrate/repair.
- [ ] Có synthetic probe riêng nếu cần chứng minh write path.
- [ ] Record ID/revision/run ID được phân biệt để không PASS bằng dữ liệu cũ.
- [ ] TTL/tombstones/cleanup policy phù hợp, không tạo churn vô hạn.
- [ ] Không dùng global `COUNT(*)` định kỳ trên bảng lớn làm readiness.
- [ ] Không log PII/bind values hoặc tạo high-cardinality labels.

### 25.3. Consistency contract

- [ ] CL read **và** CL write được đặt tường minh trên statements.
- [ ] Với RF3: biết local quorum cần 2 full replica ACK đúng hạn.
- [ ] Với multi-DC: phân biệt `QUORUM`/`LOCAL_QUORUM`/`EACH_QUORUM`.
- [ ] Không dùng `ANY` write để khẳng định read-after-write visibility.
- [ ] Biết `SERIAL`/`LOCAL_SERIAL` là serial phase của LWT, khác normal CL.
- [ ] Test so expected key/value/revision/size, không chỉ `row != null`.
- [ ] Multi-node CL test chạy trên **cluster đa node thật**, không dùng single node làm proxy.
- [ ] Test âm kiểm đúng `UnavailableException`, không chỉ “bất kỳ exception”.
- [ ] Driver retries/speculation được ghi nhận và giới hạn theo deadline/SLO.
- [ ] Unknown write outcome được reconcile, không retry tạo ID mới mù.

### 25.4. Độ ổn định và vận hành

- [ ] Có total budget, per-attempt timeout, bounded polling/backoff.
- [ ] Phân biệt lỗi transient vs permanent; không nuốt `InvalidQuery`/`Unauthorized`.
- [ ] Có metrics read/write timeout, unavailable, failed, retry, p95/p99.
- [ ] Server disk/GC/compaction/streaming/repair health được quan sát.
- [ ] Readiness gate không bị gắn nhầm vào Kubernetes liveness dẫn tới restart loop.
- [ ] Canary GO/HOLD/STOP có guardrails và owner, không chỉ một boolean.
- [ ] Khi rollback, có bước kiểm data oracle và unknown outcomes.
- [ ] Không dùng thao tác phá node/network/iptables trên production để chạy test.
- [ ] Step 4 ghi tài liệu; build/test/academic QA được chạy ở vòng chuyên môn riêng.

## 26. Câu hỏi tự đánh giá và gợi ý đáp án

**Câu 1.** Docker báo container RUNNING có chứng minh Cassandra đã mở 9042 chưa?  
**Đáp án:** Chưa; JVM/native transport có thể đang khởi tạo.

**Câu 2.** TCP port 9042 đã kết nối được có chứng minh user table phục vụ được không?  
**Đáp án:** Không; auth/schema/replica quorum/dữ liệu chưa được kiểm.

**Câu 3.** `SELECT release_version FROM system.local` thành công chứng minh gì?  
**Đáp án:** Ít nhất một CQL coordinator có thể phục vụ system table; không chứng minh user keyspace.

**Câu 4.** Hai ký tự `UN` trong `nodetool status` là gì?  
**Đáp án:** U=Up, N=Normal theo góc nhìn status, không phải “all data synced”.

**Câu 5.** `UJ` có nghĩa node đã hoàn tất bootstrap/streaming chưa?  
**Đáp án:** Không; U=Up, J=Joining.

**Câu 6.** Khi node `UN`, có thể khẳng định mọi query `LOCAL_QUORUM` thành công không?  
**Đáp án:** Không; cần đủ natural replicas/ACK đúng hạn cho partition/CL đó.

**Câu 7.** Với RF3 một DC, quorum là bao nhiêu?  
**Đáp án:** 2 full replica responses (giả định replication thường).

**Câu 8.** RF4 một DC thì LOCAL_QUORUM cần bao nhiêu?  
**Đáp án:** 3.

**Câu 9.** RF3 có 2 replicas UP, 1 DOWN, LOCAL_QUORUM chắc chắn PASS không?  
**Đáp án:** Có **thể** đạt về số live replicas, nhưng vẫn có thể timeout/fail nếu hai nodes không ACK đúng hạn.

**Câu 10.** RF3 chỉ 1 replica UP, LOCAL_QUORUM có đạt không?  
**Đáp án:** Không, thông thường coordinator trả `UNAVAILABLE`.

**Câu 11.** `UNAVAILABLE` khác `READ_TIMEOUT` thế nào?  
**Đáp án:** Không đủ known-live replicas vs đã cố xử lý nhưng không đủ responses kịp thời.

**Câu 12.** `DriverTimeoutException` có đồng nghĩa Cassandra server `ReadTimeoutException` không?  
**Đáp án:** Không; driver deadline có thể hết trước khi server trả bất kỳ result/error nào.

**Câu 13.** Trong NTS dc1 RF3, dc2 RF2, LOCAL_QUORUM từ dc2 cần bao nhiêu ACK?  
**Đáp án:** 2 trong dc2.

**Câu 14.** Với cùng RF5 toàn cluster, QUORUM cần bao nhiêu ACK?  
**Đáp án:** 3 full replicas tổng cộng.

**Câu 15.** EACH_QUORUM write khi dc1 RF3 và dc2 RF2 cần gì?  
**Đáp án:** Ít nhất 2 ở dc1 **và** 2 ở dc2; không lấy 3 tổng rồi coi đủ.

**Câu 16.** Có thể đọc ở `ANY` không?  
**Đáp án:** Không; ANY chỉ dùng cho write, có thể thành công nhờ hinted handoff.

**Câu 17.** Ghi ở ONE rồi đọc QUORUM với RF3, có chắc giao nhau không?  
**Đáp án:** Không; W+R = 1+2 = 3, không lớn hơn RF3.

**Câu 18.** Ghi/read QUORUM với RF3 tạo quorum intersection chứ?  
**Đáp án:** Có, trong cùng full replica set (2+2>3), với giả định không có concurrent/timestamp conflicts ngoài mô hình.

**Câu 19.** Có quorum intersection là đủ bảo đảm linearizability cho mọi query không?  
**Đáp án:** Không; concurrent writes, timestamps/LWW, LWT và DC semantics còn quan trọng.

**Câu 20.** Một SELECT ở CL LOCAL_QUORUM trả 0 rows có được PASS G5 không?  
**Đáp án:** Chỉ khi oracle kỳ vọng row không tồn tại; với seeded row mong đợi thì FAIL data oracle.

**Câu 21.** Schema agreement true có chứng minh cả nodes DOWN cũng đồng bộ schema không?  
**Đáp án:** Không; driver kiểm các nodes **đang UP**.

**Câu 22.** Sau DDL, `isSchemaInAgreement()` false có nghĩa DDL chắc chắn rollback?  
**Đáp án:** Không; có thể schema đã thay ở một số nodes nhưng chưa hội tụ trong timeout.

**Câu 23.** Trên một SELECT, `ExecutionInfo.isSchemaInAgreement()` true có phải bằng chứng tốt không?  
**Đáp án:** Không; với non-DDL query cờ đó luôn true theo Javadoc.

**Câu 24.** Vì sao phải gọi lại `session.getMetadata()` sau DDL?  
**Đáp án:** Metadata là immutable snapshot (trừ một số node state fields); snapshot cũ có thể stale.

**Câu 25.** Cassandra Testcontainers 2.x dùng package CassandraContainer nào?  
**Đáp án:** `org.testcontainers.cassandra.CassandraContainer`; không trộn với package cũ trong 1.x.

**Câu 26.** Một Testcontainers Cassandra đơn node có chứng minh RF3 LOCAL_QUORUM không?  
**Đáp án:** Không; cần cluster thực sự có nhiều full replicas cùng DC.

**Câu 27.** Tại sao RF2 trên một node ở CL TWO là test âm hợp lệ?  
**Đáp án:** Không có hai physical replicas; test nên thấy `UNAVAILABLE` dù CQL port/ring local vẫn hoạt động.

**Câu 28.** Vì sao negative test không chỉ dùng `assertThrows(Exception.class)`?  
**Đáp án:** Sai CQL/permission/port đều có thể ném exception; phải kiểm đúng `UnavailableException` hoặc nested cause.

**Câu 29.** Natural replicas được xác định bằng gì?  
**Đáp án:** Partition key → token, keyspace replication strategy/RF và ring/DC/rack topology.

**Câu 30.** Node coordinator có nhất thiết là natural replica của partition không?  
**Đáp án:** Không; coordinator có thể chuyển read/write tới natural replicas.

**Câu 31.** Một key probe PASS ở CL yêu cầu có chứng minh tất cả tokens trong cluster không?  
**Đáp án:** Không; đó là một token/replica set tại thời điểm đo. Cần coverage đại diện.

**Câu 32.** Vì sao test restore cần seeded historical keys?  
**Đáp án:** Probe mới chỉ chứng minh write/read path, không chứng minh dữ liệu trước backup đã được khôi phục.

**Câu 33.** Vì sao schema agreement sau tăng RF chưa đủ để nhận data-ready?  
**Đáp án:** Historical replicas mới có thể chưa có dữ liệu; cần repair/streaming và read oracle.

**Câu 34.** Vì sao `COUNT(*)` toàn bảng thường không thích hợp làm health probe?  
**Đáp án:** Cassandra có thể phải quét lượng lớn partitions/SSTables, tốn CPU/I/O, tăng tải lúc recovery.

**Câu 35.** Test probe có TTL một giây và fail sau năm giây có nhất thiết là replica lỗi không?  
**Đáp án:** Không; data có thể đã expire đúng TTL.

**Câu 36.** Vì sao data probe cần revision/run ID?  
**Đáp án:** Tránh PASS bằng row từ lần test trước hoặc race giữa tests.

**Câu 37.** Kiểm SELECT ở cqlsh bằng superuser có đủ chứng minh Java service role sẵn sàng không?  
**Đáp án:** Không; cần dùng auth/role/driver/DC như ứng dụng thật.

**Câu 38.** Nếu `LOCAL_QUORUM` đã đạt nhưng p99 lớn hơn SLO, readiness có thể FAIL không?  
**Đáp án:** Có; tính khả dụng và độ trễ là hai tiêu chí khác nhau.

**Câu 39.** Vì sao không đặt LOCAL_QUORUM query làm livenessProbe của từng Cassandra pod?  
**Đáp án:** Nó có thể fail do replicas khác và tạo cascading restart, trong khi pod hiện tại vẫn khỏe.

**Câu 40.** App HTTP đã mở 8080, liệu nó có thể chưa ready phục vụ Cassandra data không?  
**Đáp án:** Có; cần dependency readiness gate theo schema/CL/data.

**Câu 41.** Vì sao không dùng `Thread.sleep(10000)` thay cho wait-ready?  
**Đáp án:** Startup timing thay đổi; dùng bounded polling theo điều kiện với timeout/cause rõ ràng.

**Câu 42.** Khi write probe timeout nhưng không có ACK, nên ghi gì?  
**Đáp án:** `UNKNOWN_OUTCOME`, giữ ID cố định và reconcile trước khi retry.

**Câu 43.** Nếu `AllNodesFailedException` tới Java, phải đọc gì?  
**Đáp án:** `getAllErrors()` theo coordinator/node và cause để phân biệt unavailable/network/timeout.

**Câu 44.** Vì sao `UN` của tất cả nodes vẫn có thể đi kèm historical data mismatch?  
**Đáp án:** Node/ring healthy không xác nhận restore/repair hoặc source-of-truth consistency.

**Câu 45.** Một canary LOCAL_QUORUM PASS sau nhiều retries có nghĩa cluster hoàn toàn khỏe không?  
**Đáp án:** Không; cần xem retries, p99, server resource và token coverage.

**Câu 46.** Khi dc1 PASS LOCAL_QUORUM, có thể công bố dc2 PASS không?  
**Đáp án:** Không; mỗi DC có RF/replica availability riêng.

**Câu 47.** Với LWT, read row tồn tại có chứng minh INSERT IF NOT EXISTS của request hiện tại đã applied không?  
**Đáp án:** Không; phải xem `[applied]`/version/operation ID và serial CL.

**Câu 48.** Test readiness cần rollback điều gì nếu thấy wrong value sau deploy?  
**Đáp án:** Chặn rollout, điều tra data/migration và reconcile; rollback code/config không tự rollback Cassandra writes/schema.

## 27. Tổng kết: bài test phải chứng minh **đúng CL và đúng data**

~~~text
PROCESS RUNNING?
       |
       v
TCP/CQL REACHABLE?
       |
       v
SCHEMA EXISTS + AGREED (among UP nodes)?
       |
       v
RF/DC/KEYSPACE/PARTITION MAPPING KNOWN?
       |
       v
EXPECTED CL AVAILABLE FOR NATURAL REPLICAS?
       |
       v
WRITE AT WCL + READ AT RCL (when required)?
       |
       v
EXPECTED BUSINESS VALUE/REVISION VISIBLE?
       |
       v
TIMEOUT/RETRY/LATENCY WITHIN SLO?
       |
       v
READY for explicit scope + time window
~~~

### 27.1. Năm điều kiện bắt buộc của kết luận “ready”

1. **Phạm vi rõ:** cluster, DC, keyspace, table, query family, partition/token samples.
2. **Đúng consistency contract:** RF và CL read/write thật sự được thực thi.
3. **Đủ response trong thời hạn:** Không còn `UNAVAILABLE`/timeout theo gate.
4. **Dữ liệu đúng:** seeded/migration và synthetic probes có oracle phù hợp, không chấp nhận “trả hàng rỗng” nếu phải có dữ liệu.
5. **Ổn định, có giới hạn:** Deadline/p95/p99/error/retry, owner và cách rollback.

**Điểm cần nhớ:** `nodetool status UN` nói node **Up/Normal**. Nó **không nói** 2/3 natural replicas của mỗi partition đã trả ACK trong hạn, cũng không nói dữ liệu lịch sử được repair/restore đúng. Integration test đáng tin **phải thực thi CQL ở CL mà nghiệp vụ yêu cầu và kiểm giá trị thực**, chứ không dừng ở container health, cổng 9042 hay schema agreement.

### 27.2. Phân định việc học và QA chuyên sâu

Bài này cung cấp lab có thể tái tạo trên Cassandra đơn node và hướng dẫn mở rộng multi-node. Trong quy trình tạo lesson, **STEP 4 viết nội dung**, không tự chạy Gradle, không fault-inject cluster và không coi các ví dụ chưa chạy là integration tests đã được xác nhận bằng thực nghiệm. STEP 6/new hoặc nhóm chuyên môn sẽ đánh giá độ đúng và khả năng thực thi trên phiên bản/môi trường đích.

## Tài liệu tham khảo

- [Apache Cassandra — Dynamo architecture và consistency](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo) — natural replicas, RF, coordinator, các CL, quorum và read/write semantics.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — full repair/streaming, đặc biệt sau RF increase.
- [Apache Cassandra — Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — request latency, errors, compaction, thread pools.
- [Apache Cassandra — Data modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html) — query-first design, partition key và token placement.
- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html) — `CONSISTENCY`, CQL và diagnostics.
- [Apache Java Driver 4.18 — Node metadata](https://apache.github.io/cassandra-java-driver/4.18.0/core/metadata/node/) — known nodes, states, distance, open connections.
- [Apache Java Driver 4.18 — Schema metadata/agreement](https://apache.github.io/cassandra-java-driver/4.18.0/core/metadata/schema/) — schema propagation among UP nodes, DDL waiting, metadata refresh.
- [Apache Java Driver 4.18 — Metadata overview](https://apache.github.io/cassandra-java-driver/4.18.0/core/metadata/) — immutable snapshots, token/schema/node consistency.
- [Apache Java Driver 4.18 — Session API](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/session/Session.html) — `checkSchemaAgreement`, metadata.
- [Apache Java Driver 4.18 — ExecutionInfo API](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/cql/ExecutionInfo.html) — `isSchemaInAgreement` chỉ có ý nghĩa sau DDL.
- [Apache Java Driver 4.18 — Retry policies](https://apache.github.io/cassandra-java-driver/4.18.1/core/retries/) — `UNAVAILABLE`, timeouts và retry decisions.
- [Apache Java Driver 4.18 — Configuration](https://apache.github.io/cassandra-java-driver/4.18.1/core/configuration/) — execution profiles, CL và timeouts.
- [Testcontainers for Java — Cassandra module](https://java.testcontainers.org/modules/databases/cassandra/) — `CassandraContainer`, `getContactPoint`, `getLocalDatacenter`.
- [Testcontainers Java 2.0 release notes](https://github.com/testcontainers/testcontainers-java/releases) — artifact/module package relocation.
- [JUnit 5 User Guide](https://docs.junit.org/current/user-guide/) — lifecycle annotations, test assertions và extension model.
- [DataStax nodetool status](https://docs.datastax.com/en/cassandra-oss/2.1/cassandra/tools/toolsStatus.html) — trạng thái `UN`/`UJ`/`DN`, keyspace ownership và giới hạn thông tin.

