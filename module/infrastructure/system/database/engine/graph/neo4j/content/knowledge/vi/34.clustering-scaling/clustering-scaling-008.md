# Độ trễ mạng, phân vùng mạng và ảnh hưởng đến khả năng phục vụ trong cụm Neo4j

## 1. Từ một sự cố thực tế đến câu hỏi về tính sẵn sàng

Một nền tảng B2B quản lý graph cung ứng với các node `Company`, `Product`, `Customer`, `Order` và các relationship `SUPPLIES`, `PLACED`. Neo4j được triển khai theo cụm để Java Driver và Spring Data Neo4j có thể đọc/ghi khi một máy chủ gặp sự cố.

Một ngày, API tạo đơn hàng bị timeout. Hai trong ba máy Neo4j vẫn bật, dashboard đọc sản phẩm có lúc chạy được, nhưng một vài người dùng nhận kết quả cũ. Có thể đã xảy ra:

- Một **network partition** chia các primary thành hai nhóm không liên lạc với nhau.
- Cụm vẫn có **quorum ghi**, nhưng Java service không kết nối được với phía đa số.
- Các primary đủ quorum nhưng độ trễ giữa những máy phải xác nhận commit quá cao.
- Secondary gần người dùng tiếp tục đọc nhưng chưa bắt kịp transaction mới vì nhân bản bất đồng bộ.
- Driver giữ routing table hoặc một bootstrap address không còn sử dụng được.
- Neo4j đã commit transaction nhưng gói phản hồi bị mất, khiến client không chắc ghi đã thành công.

Bài học thuộc chương **Cụm và mở rộng** giải thích cơ chế, dấu hiệu giám sát, quyết định kiến trúc và cách diễn tập có kiểm soát. Mục tiêu không chỉ là “cụm có bao nhiêu server”, mà là **truy vấn nào được phục vụ, dữ liệu mới tới đâu và người dùng chịu độ trễ bao nhiêu**.

> Phạm vi: Neo4j Enterprise cluster với các bản sao **primary/secondary** và Java Driver 6.x. Neo4j Community/standalone không có khả năng Raft/quorum của Enterprise cluster. Trên AuraDB, cấu trúc cluster và những thao tác quản trị được dịch vụ kiểm soát theo tier.

## 2. Phân biệt sẵn sàng đọc, ghi, tính mới và độ bền

| Khái niệm | Câu hỏi | Điều kiện cần phân tích |
| --- | --- | --- |
| **Write availability** | Có thể commit `CREATE`, `MERGE`, `SET`, `DELETE` không? | Writer và **đa số primary** trong nhóm của database hoạt động, đường mạng/routing tới writer |
| **Read availability** | Có bản sao phục vụ được `MATCH` không? | Bản sao primary/secondary còn truy cập được và đủ quyền đọc |
| **Freshness** | Read có thấy write mới commit không? | Replication lag, bookmarks, mức nhất quán của use case |
| **Durability** | Sau khi commit, lỗi máy có làm mất transaction không? | Bảo đảm commit/quorum, trạng thái disk và backup |
| **Application availability** | Endpoint của Java/Spring còn trả kết quả đúng SLO không? | Cả mạng client, routing, pool, auth, query, failover, dependency khác |

Một database có thể **mất quyền ghi nhưng vẫn đọc được** từ bản sao còn khỏe; read có thể không đủ mới. Ngược lại, database có thể khỏe nhưng Java service không truy cập được vì lỗi DNS, firewall hoặc TLS.

**Khả năng phục vụ không chỉ là trạng thái TCP port.** Health check trả HTTP 200 không chứng minh một transaction ghi sẽ được majority chấp nhận, cũng không chứng minh mọi replica đã áp log mới nhất.

## 3. Kiến trúc cụm: primary, secondary, writer và Raft

### 3.1. Primary/secondary là vai trò theo database

Neo4j Enterprise có thể có nhiều database trên một cụm. Mỗi database có topology riêng; server A có thể là primary cho database `orders` và secondary cho `catalog`.

```text
                    Neo4j Enterprise cluster
                   Server A  Server B  Server C
database orders     Primary   Primary   Primary
                    Writer    Follower  Follower

database catalog    Secondary Primary   Primary
                       -      Writer    Follower
```

**Leader/writer thuộc nhóm Raft của từng database**, không phải một nhãn cố định cho toàn server. Vai trò writer có thể thay đổi sau election hoặc thay đổi topology.

### 3.2. Primary xác nhận write theo quorum

Ở database có ba primary:

```text
 Java Driver --WRITE--> P1 (writer)
                            | \
                      Raft  |  \ Raft
                            v   v
                           P2   P3
                          (ack) (chậm)
                            |
                  P1 + P2 = quorum
                            |
                     commit hợp lệ
```

Quy trình khái niệm:

1. Client gửi transaction tới writer primary của database.
2. Writer sắp xếp thay đổi theo Raft log.
3. Writer chuyển log cho follower primaries.
4. Transaction cần được **đa số primary** xác nhận để được công nhận là commit.
5. Sau commit, client nhận xác nhận nếu đường mạng client vẫn tốt.

Trong nhóm ba primary, quorum bằng **hai**. Writer không cần đợi mọi follower; nếu follower gần nhất không sẵn sàng, writer có thể cần xác nhận từ follower khác ở xa, khiến write latency tăng.

### 3.3. Secondary nhân bản bất đồng bộ để mở rộng đọc

Secondary lấy transaction logs từ upstream theo cơ chế catch-up:

- Có thể phục vụ truy vấn **read-only**.
- Không tham gia bỏ phiếu Raft, không trở thành writer chỉ nhờ được thêm vào cụm.
- Có thể **lag** so với primary.
- Giúp phân phối read workloads, tăng throughput đọc trong điều kiện tài nguyên phù hợp.
- Không thay thế một primary đã mất khi tính quorum ghi.

Điều này giải thích vì sao “thêm năm secondary” không giải quyết sự cố mất majority primary.

## 4. Quorum và giới hạn chịu lỗi

Với `N` bản sao primary của **một database**:

```text
quorum = floor(N / 2) + 1

Số primary có thể mất mà vẫn giữ quyền ghi
  = N - quorum
```

| Số primary | Quorum | Số primary có thể mất | Ý nghĩa |
| ---: | ---: | ---: | --- |
| 1 | 1 | 0 | Tối giản, không có chịu lỗi primary |
| 2 | 2 | 0 | Mất một primary là mất write availability |
| 3 | 2 | 1 | Mẫu HA phổ biến |
| 5 | 3 | 2 | Có thể chịu hai lỗi primary nếu nhóm còn lại liên lạc được |

Công thức `N = 2F + 1` thường được dùng để chọn số primary nhằm chịu `F` lỗi. Tuy nhiên, **chịu F lỗi primary không tự có nghĩa chịu được mất F datacenter**: còn phụ thuộc phân bố bản sao theo các vùng.

Quorum này là **theo database**. `system` database có topology riêng; nếu chỉ `orders` còn quorum nhưng `system` không, các thao tác quản trị metadata có thể bị ảnh hưởng khác những truy vấn dữ liệu thông thường.

## 5. Độ trễ mạng ảnh hưởng đến query và commit qua những đường nào?

| Loại đường đi | Mô tả | Hệ quả |
| --- | --- | --- |
| Client ↔ Bolt | Java Driver gửi Cypher, nhận records, mở connection | Cộng thêm thời gian trên request đọc/ghi |
| Writer ↔ primary followers | Raft replication, heartbeat và ACK | Ảnh hưởng **commit latency** và election |
| Primary/upstream ↔ secondary | Transaction log shipping | Ảnh hưởng **read freshness** và catch-up time |
| Driver ↔ routing endpoint | Routing table, DNS, bootstrap | Ảnh hưởng failover/routing refresh |
| Server ↔ disk/CPU/GC | Không phải network nhưng làm xử lý Raft chậm | Có thể bị chẩn đoán nhầm thành lỗi mạng |

### 5.1. Mô hình thời gian ghi

Một mô hình lập luận, **không phải công thức đo chính xác của Neo4j**:

```text
T_write_end_to_end
 ≈ T_client_to_writer
 + T_execute_and_validate
 + T_replicate_to_majority
 + T_commit_and_response
 + T_queueing
```

Phần `T_replicate_to_majority` phụ thuộc thời gian nhận ACK từ **đủ follower để đạt quorum**, không đơn thuần là tổng RTT mọi primary.

Ví dụ các số dưới đây **giả định**, không phải benchmark:

| Đường mạng | RTT ví dụ |
| --- | ---: |
| API ↔ primary cùng vùng | 2 ms |
| Primary ↔ primary cùng datacenter | 1 ms |
| Primary ↔ primary khác khu vực | 80 ms |
| API ↔ secondary địa phương | 2 ms |

Khi một follower địa phương mất kết nối và phải nhận ACK từ vùng xa, write p95 có thể tăng đáng kể dù CPU và Cypher không đổi. Nhưng **không thể kết luận “tăng RTT 80 ms thì mọi write chậm thêm đúng 80 ms”**: xử lý disk, batching, leader location, queue và jitter đều có tác động.

### 5.2. Độ trễ đọc và tính địa phương

Một truy vấn traversal nhiều relationship có thể trả hàng nghìn record. Nếu ứng dụng ở vùng A nhưng read endpoint ở vùng B, thời gian truyền response có thể đáng kể. Secondary gần ứng dụng giúp giảm quãng đường, nhưng nếu dữ liệu chưa bắt kịp:
- Truy vấn không có bookmark có thể thấy snapshot cũ.
- Truy vấn có bookmark có thể **đợi catch-up** và mất lợi thế latency.
- Đọc cục bộ nhanh chưa chắc là lựa chọn đúng cho một API vừa thanh toán xong cần thấy trạng thái mới.

**Phải phân biệt RTT, p95/p99 truy vấn và replication lag**; chúng không phải một metric.

## 6. Network partition: server sống nhưng không liên lạc được

**Network partition** là tình trạng các nhóm máy vẫn có thể chạy, nhưng không trao đổi thông tin tin cậy với nhau. Nguyên nhân có thể gồm firewall/security group, switch/router, đứt WAN, mất packet, routing hoặc cổng cluster bị chặn.

```text
Ban đầu:                     Khi partition:
 P1 ----- P2                   P1 ----- P2
  \       /                       (2 máy)
   \     /                           |
      P3                         X   X
                                     P3
                                  (1 máy)
```

Raft bảo vệ lịch sử commit: **nhóm đủ quorum mới có thể xác nhận write mới**. Nhóm thiểu số không được tự nhận mình là một cluster ghi độc lập.

Điều đó **không bảo đảm mọi client luôn phục vụ được**:
- Client chỉ truy cập được nhóm thiểu số có thể lỗi dù phần đa số đang khỏe.
- Có thể cần thời gian cho election, routing refresh và retry.
- Một secondary tách khỏi upstream có thể tiếp tục trả dữ liệu cũ nếu truy cập được.
- Sau khi mạng được khôi phục, member bị trễ cần **catch up** log.

### Ba kiểu mất kết nối khác nhau

| Mất kết nối | Hệ quả chính |
| --- | --- |
| Java service ↔ Bolt members | App có thể unavailable dù cluster nội bộ đủ quorum |
| Primary ↔ primary Raft | Mất quorum/bầu lại leader/không commit ở nhóm thiểu số |
| Secondary ↔ upstream | Read scaling/freshness giảm; primary quorum có thể vẫn bình thường |

Đừng chỉ ping IP để kết luận các cổng và giao thức client/cluster đều khỏe.

## 7. Kịch bản ba primary, phân vùng 2–1

Giả sử `orders` có P1, P2, P3; lúc đầu P1 là writer.

### 7.1. P3 bị cô lập

```text
          P1 writer ------ P2 follower
                \          /
                     2/3 quorum

             X-----------X
                     P3
                   isolated
```

Kết quả mong đợi:

- P1+P2 tạo được quorum, **có thể tiếp tục commit** nếu phần còn lại của hệ thống khỏe.
- P3 không thể tự commit mới.
- Dữ liệu tại P3 có thể thiếu các transaction commit sau lúc phân vùng.
- Client ở phía P3 mà không thể tới P1/P2 có thể mất khả năng ghi và gặp lỗi routing.
- Khi kết nối được nối lại, P3 bắt kịp các thay đổi.

### 7.2. P1 (writer cũ) bị cô lập

```text
           P1 (old writer)
                  X
            -------------
              P2 ---- P3
                quorum=2
```

P2/P3 đủ đa số để tiến hành bầu writer mới. Trong quá trình bầu cử, ứng dụng có thể gặp **TransientException, timeout hoặc retry**. P1 không thể commit write mới nếu mất quorum, dù một Java client vẫn giữ TCP connection tới P1.

Chú ý: một báo cáo leader cục bộ tại một thời điểm không chứng minh writer đã ổn định. So trạng thái từ nhiều primary và khả năng commit thật.

### 7.3. Ba primary chia thành 1–1–1

Không nhóm nào có **2 phiếu**. Các primary có thể còn bản sao để phục vụ đọc phù hợp, nhưng **không thể commit giao dịch ghi mới** cho database ấy cho tới khi quorum được khôi phục hoặc áp dụng quy trình disaster recovery được hỗ trợ.

### 7.4. Nhìn từ client

| Hiện tượng | Ý nghĩa có thể | Cách xử lý |
| --- | --- | --- |
| Ghi timeout khi election | Leader/routing chưa ổn định | Retry có giới hạn và idempotency |
| `MATCH` từ secondary vẫn chạy | Có dữ liệu cũ | Kiểm tra yêu cầu freshness |
| App chỉ biết địa chỉ P3 | Bootstrap/routing mất lối vào majority | Sửa discovery/advertised address |
| Ghi đã commit nhưng app lỗi | ACK từ server bị mất | Kiểm tra trạng thái bằng khóa nghiệp vụ |
| Đọc sau ghi không thấy node | Replica lag/bookmark thiếu | Bookmarks hoặc đọc theo phiên nhân quả |

## 8. Phân vùng năm primary, 3–2 và tác động của multi-region

Với `N=5`, quorum là `3`:

```text
             Partition A                  Partition B
          P1 --- P2 --- P3                 P4 --- P5
               3/5                          2/5

           Có thể WRITE                 Không WRITE
```

Nhóm ba primary có thể bầu writer và commit; nhóm hai không thể commit. Tuy nhiên khả năng ứng dụng phục vụ vẫn phụ thuộc client có tới được phía đa số không.

### 8.1. Phân bố 2+2+1 trên ba datacenter

Tài liệu Neo4j khuyến nghị cân nhắc **5 primary phân bố 2P+2P+1P** trong ba datacenter khi muốn chịu mất **bất kỳ một** datacenter:

- Mất datacenter có 2 primary: còn 3 primary, đủ quorum.
- Mất datacenter có 1 primary: còn 4, đủ quorum.
- Có nhiều đường WAN cho Raft, do đó latency/cost tăng so với một datacenter.

Ngược lại, ba primary phân bố **2P+1P** trong hai datacenter không chịu được mất vùng có hai primary. Phân bố **3P+1P+1P** trên ba datacenter với năm primary cũng không chịu được mất vùng có ba primary.

### 8.2. Không tối ưu số primary bằng một chỉ số duy nhất

Chọn topology theo:
- Write latency p95/p99 và throughput thực tế.
- Khả năng chịu mất primary/datacenter.
- RTT/jitter/packet loss giữa các primary.
- RPO, RTO và tốc độ bắt kịp sau failover.
- Băng thông, chi phí WAN và yêu cầu bảo mật.
- Chiến lược đọc gần người dùng.

Nhiều primary hơn **không có nghĩa mỗi truy vấn Cypher tự chạy nhanh hơn**. Trong cụm có tải ghi cao, số primary lớn còn tăng công việc replication và vận hành.

## 9. Read-after-write: secondary có thể chậm, bookmark có thể chờ

Giả sử Java service tạo một đơn:

```cypher
MERGE (o:NetDemoOrder {orderId: 'o501'})
SET o.status = 'NEW';
```

Ngay sau khi write commit trên quorum, secondary có thể chưa áp bản cập nhật, nên request đọc độc lập `MATCH (o:NetDemoOrder {orderId:'o501'})` chưa thấy node.

**Bookmark** là mốc trạng thái database. Khi request đọc mang bookmark của transaction đã commit, Neo4j chỉ thực thi read trên bản sao đã tới ít nhất trạng thái đó, hoặc chờ tới khi đạt được.

```text
Session ghi --commit--> bookmark B
                          |
Request đọc + B ----------+
                          |
            Replica đã áp B?
              /          \
           Có             Chưa
           |               |
         Read           Chờ bắt kịp
                           |
                      Read / timeout
```

Đánh đổi:
- Read-your-writes được bảo đảm khi thành công.
- Có thể tăng độ trễ khi replica chậm.
- Khi partition kéo dài, thao tác đòi hỏi bookmark có thể bị timeout thay vì trả dữ liệu cũ.

| Use case | Độ mới cần thiết | Hướng lựa chọn |
| --- | --- | --- |
| Xem đơn hàng vừa tạo | Read-your-writes | Cùng session hoặc bookmarks qua session |
| Dashboard KPI cập nhật định kỳ | Chấp nhận trễ | Secondary kèm thời điểm dữ liệu |
| Thanh toán/chống trùng đơn | Không được đếm sai | Unique constraint + transaction ghi, không dựa vào negative read ở replica |
| Báo cáo lịch sử | Snapshot có mốc rõ | Read model/secondary, ghi as-of time |
| Kiểm tra quyền | Không để quyền cũ gây lộ dữ liệu | Chọn cơ chế nhất quán và fail-closed phù hợp |

**Bookmark không tăng tốc replication**; nó chỉ điều phối thao tác cần tính nhân quả.

## 10. Java Driver: routing URI khác direct URI

Đối với Java Driver:

- `neo4j://` và `neo4j+s://`: Driver dùng **routing**, lấy bảng endpoint theo vai trò và cập nhật khi cần.
- `bolt://` và `bolt+s://`: kết nối **direct** tới một member cụ thể, không tự định tuyến qua writer/reader topology.
- Scheme bảo mật phải khớp TLS và certificate của triển khai.

Nếu mã ứng dụng trỏ cứng tới `bolt://primary1:7687`, việc primary1 chết có thể làm ứng dụng lỗi mặc dù primary2/primary3 còn đủ quorum. Vì vậy phần lớn ứng dụng production trong cụm nên dùng URI routing do operator cung cấp.

### 10.1. Bootstrap/discovery quan trọng như quorum

Driver có thể lấy routing table từ entrypoint, nhưng:
- Nếu entrypoint duy nhất bị partition, Driver có thể không lấy được bảng mới.
- DNS nhiều bản ghi A/AAAA hoặc **custom address resolver** có thể tăng khả năng bootstrap.
- Địa chỉ **advertised** trả từ server phải truy cập được từ mọi client được phép.
- Firewall, security group, hostname/TLS và cổng Bolt phải cho phép truy cập những endpoint thực sự được route tới.
- Một load balancer/TCP proxy cấu hình sai có thể vô tình biến cả cụm thành một **single point of failure** phía client.

Routing tốt không chữa được mất quorum; quorum có sẵn nhưng client không kết nối được cũng chưa tạo ra availability cho người dùng.

## 11. Java Driver 6.x: ghi idempotent và đọc đúng phiên

Giả sử đã tạo database `supply`, schema và credential phù hợp; ví dụ dùng khóa nghiệp vụ có constraint:

```cypher
CREATE CONSTRAINT net_demo_order_id IF NOT EXISTS
FOR (o:NetDemoOrder) REQUIRE o.orderId IS UNIQUE;
```

Ví dụ Java Driver dùng routing URI:

```java
import java.time.Duration;
import java.util.Map;

import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Config;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

String uri = System.getenv("NEO4J_URI");  // neo4j+s://...
String username = System.getenv("NEO4J_USER");
String password = System.getenv("NEO4J_PASSWORD");

Config config = Config.builder()
    .withMaxTransactionRetryTime(Duration.ofSeconds(15))
    .build();

try (Driver driver = GraphDatabase.driver(
        uri, AuthTokens.basic(username, password), config)) {

    driver.verifyConnectivity();

    try (Session session = driver.session(
            SessionConfig.forDatabase("supply"))) {

        session.executeWriteWithoutResult(tx ->
            tx.run("""
                MERGE (o:NetDemoOrder {orderId: $id})
                ON CREATE SET o.status = 'NEW'
                """, Map.of("id", "o501")).consume()
        );

        String status = session.executeRead(tx ->
            tx.run("""
                MATCH (o:NetDemoOrder {orderId: $id})
                RETURN o.status AS status
                """, Map.of("id", "o501"))
              .single().get("status").asString()
        );

        System.out.println(status);
    }
}
```

Ở đây:
1. Một `Driver` quản lý routing và pool; trong Spring Boot nên dùng một Driver được quản lý xuyên vòng đời ứng dụng.
2. `SessionConfig.forDatabase("supply")` chỉ rõ database, vì quorum/writer là theo từng database.
3. `executeWriteWithoutResult` dùng managed transaction; lỗi transient có thể được retry.
4. `executeRead` ngay sau đó trong **cùng session** có causal chain.
5. `MERGE` theo khóa và uniqueness constraint giúp tránh tạo trùng khi callback chạy lại.
6. Retry tối đa 15 giây **chỉ là ví dụ**, cần cân chỉnh với API SLO, gateway timeout và circuit breaker.

### 11.1. Bookmarks giữa hai session độc lập

Nếu write và read ở hai request/session khác nhau:

```java
import java.util.Collection;
import java.util.Map;
import org.neo4j.driver.Bookmark;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

Collection<Bookmark> bookmarks;

// Biến driver đã được khởi tạo, database supply đã tồn tại.
try (Session writer = driver.session(
        SessionConfig.forDatabase("supply"))) {

    writer.executeWriteWithoutResult(tx ->
        tx.run("""
            MERGE (:NetDemoOrder {orderId: $id})
            """, Map.of("id", "o502")).consume()
    );

    bookmarks = writer.lastBookmarks();
}

try (Session reader = driver.session(
        SessionConfig.builder()
            .withDatabase("supply")
            .withBookmarks(bookmarks)
            .build())) {

    boolean found = reader.executeRead(tx ->
        tx.run("""
            MATCH (o:NetDemoOrder {orderId: $id})
            RETURN count(o) > 0 AS found
            """, Map.of("id", "o502"))
          .single().get("found").asBoolean()
    );

    System.out.println(found);
}
```

Đoạn này giả định biến `driver` đã tồn tại và hai lời gọi thành công. Bookmark truyền qua request cần được quản lý an toàn và gắn đúng nghiệp vụ; nó **không** là credential hay token phân quyền.

Driver cũng có bookmark manager mặc định cho chuỗi `driver.executableQuery(...)`. Với các session độc lập hoặc transaction song song, không mặc định có causal chain nếu chưa phối hợp bookmarks.

## 12. Lỗi mạng sau write: commit chưa chắc thất bại

Xét hai tình huống:

1. Raft chưa đạt quorum → transaction chưa được công nhận, client timeout.
2. Raft **đã commit**, nhưng phản hồi từ server đến client bị mất → client cũng timeout.

Do đó, **client-side timeout không xác nhận transaction đã rollback**.

Thiết kế đúng cho đơn hàng và thanh toán:
- Gửi **idempotency key/orderId** duy nhất.
- Dùng constraint và transaction logic để ngăn duplicate.
- Khi phản hồi ghi không rõ, truy vấn lại bằng business ID/nguồn trạng thái đáng tin cậy.
- Không gắn gửi email, gọi thanh toán hoặc publish Kafka trực tiếp vào callback có thể retry.
- Dùng outbox/idempotent consumer/reconciliation cho side effect bên ngoài Neo4j.
- Thiết lập giới hạn retry, backoff và concurrency để tránh **retry storm**.

Managed transaction của Java Driver tự retry một số transient errors đến thời hạn cấu hình, nhưng **không phải mọi lỗi đều retry được**. Syntax error, permission error hoặc constraint violation cần xử lý riêng.

## 13. Spring Data Neo4j và ứng dụng reactive

Spring Data Neo4j dùng Java Driver bên dưới, nên lựa chọn routing/transaction/credential vẫn quan trọng:
- Cấu hình `neo4j+s://` hoặc URI phù hợp trong deployment, không ghim vào một primary.
- Dùng connection pool/Driver chung; không tạo Driver mỗi HTTP request.
- Giữ transaction ngắn và tách external API call khỏi transaction khi có thể.
- Khi write cần exactly-once effect theo nghiệp vụ, áp dụng unique key và idempotent workflow.
- Với read-after-write giữa requests, bảo đảm truyền bookmark/correlation khi cần; không mặc định mọi secondary đã bắt kịp.
- Với Spring WebFlux/Reactor, không block event loop trong callback retry hoặc trong pipeline đọc.
- Đo lỗi routing, p95/p99 và số lần retry **ở tầng ứng dụng**, không chỉ theo dõi server.

`@Transactional(readOnly = true)` là tín hiệu transaction/read semantics ở tầng Spring, **không phải cam kết một secondary bất kỳ có dữ liệu mới nhất**. Khả năng định tuyến phải được kiểm tra theo transaction manager, driver access mode và phiên bản đang sử dụng.

## 14. Mức suy giảm dịch vụ theo từng use case graph

| Chức năng | Khi mất quorum ghi | Khi secondary lag |
| --- | --- | --- |
| Xem danh mục sản phẩm | Có thể tiếp tục nếu read copy reachable | Có thể dùng dữ liệu cũ trong SLA |
| Tạo order/relationship `PLACED` | Không giả thành công; từ chối hoặc hàng đợi bền vững theo kiến trúc | Primary quorum quyết định, không dựa secondary |
| Xem order vừa đặt | Nếu write chưa xác nhận, hiển thị trạng thái pending phù hợp | Dùng bookmark hoặc chờ đủ mới |
| Thanh toán/đánh dấu `PAID` | Fail-closed hoặc bền vững đưa hàng đợi; đối soát payment | Không quyết định “chưa thanh toán” chỉ từ replica cũ |
| Dashboard doanh thu | Có thể tiếp tục nếu đọc được và có timestamp | Hiển thị mức trễ/as-of time |
| Kiểm tra phân quyền người dùng | Không được bỏ qua bảo mật | Không dựa vào snapshot quyền quá cũ để cho phép truy cập |
| Batch GDS/import | Hoãn write-mode hoặc job cần consistency | Kiểm tra graph projection và catch-up |

Chế độ suy giảm (*graceful degradation*) phải do **ca sử dụng** xác định, không bật một cờ “read-only cho tất cả” mà bỏ qua khác biệt consistency.

## 15. Quan sát trạng thái cluster bằng Cypher

Với quyền quản trị phù hợp trong Neo4j Enterprise:

```cypher
SHOW SERVERS;
```

```cypher
SHOW DATABASES;
```

```cypher
SHOW DATABASE supply;
```

Lệnh giúp đánh giá server, topology và trạng thái database. Khi cụm có nhiều database phải quan sát **đúng database đang báo lỗi**. Một database có leader khỏe không chứng minh database khác cũng có quorum.

Đọc thêm `neo4j.log`/`debug.log`, trạng thái ứng dụng và kết nối mạng. Khi database không vào được, dùng quan sát tại host/container và các endpoint status được phép truy cập.

### 15.1. Cluster status endpoints

Neo4j Enterprise công bố các endpoint theo database:

```text
/db/supply/cluster/writable
/db/supply/cluster/read-only
/db/supply/cluster/available
/db/supply/cluster/status
/dbms/cluster/status
```

- `writable`: hỗ trợ định tuyến tới member phục vụ write.
- `read-only`: định tuyến read tới member không ghi.
- `available`: trạng thái phục vụ read nói chung.
- `status`: quan điểm trạng thái của member.
- `/dbms/cluster/status`: trạng thái DBMS cho nhiều database.

Phải xem từ **nhiều primary** khi nghi có partition: status một member có thể không phản ánh toàn bộ topology đang phân vùng.

Các endpoint này có cơ chế authentication/authorization. **Không tắt auth hoặc expose công khai** chỉ để hệ thống monitor đơn giản hơn; cần giới hạn mạng quản trị và quyền truy cập tương ứng.

## 16. Những metric giúp chứng minh mạng hay cluster đang nghẽn

| Nhóm | Metric hoặc tín hiệu | Ý nghĩa |
| --- | --- | --- |
| Raft leader | `cluster.raft.is_leader` | Member hiện tin mình là leader của database |
| Raft log | `append_index`, `commit_index`, `applied_index` | Mốc ghi log, commit và áp dụng |
| Raft replication | `replication_attempt`, `replication_success`, `replication_fail` | Số thử/thành công/lỗi replication |
| Heartbeat | `last_leader_message` | Thời gian kể từ message gần nhất của leader |
| Processing | `message_processing_delay` và timers | Chậm giữa nhận và xử lý message |
| Transaction lag | `transaction.last_committed_tx_id` theo member | Bản sao nào tụt sau |
| Bolt/Driver | Error/timeout, routing refresh, retry, connection wait | Ảnh hưởng thực ở ứng dụng |
| Network/OS | RTT, packet loss, TCP retransmit, CPU, GC, I/O | Phân biệt mất mạng với máy chủ quá tải |

Quan hệ thông thường của các chỉ số Raft:

```text
append_index >= commit_index >= applied_index
```

Nếu `commit_index - applied_index` tăng kéo dài, member có thể áp transaction chậm; nếu `last_leader_message` liên tục tăng, cần kiểm tra heartbeat/kết nối hoặc leader; nếu `replication_fail` đồng thời tăng cùng write p99, việc điều tra mạng/peer trở nên có cơ sở.

**Không kết luận split brain từ một snapshot metric leader.** Trong election, các member có thể tạm thời báo cáo leader khác nhau theo góc nhìn riêng; kết hợp time series, status nhiều member và khả năng **commit thực sự**.

Ngưỡng cảnh báo cần dựa trên baseline. Ví dụ, lag 1.000 transaction có ý nghĩa khác nhau giữa hệ thống 10 và 100.000 transaction mỗi giây. Đặt ngưỡng theo **thời gian lag tương ứng và SLO nghiệp vụ** nếu có thể.

## 17. Ma trận chẩn đoán triệu chứng

| Triệu chứng | Nguyên nhân có thể | Bằng chứng nên lấy | Tránh làm ngay |
| --- | --- | --- | --- |
| Không ghi, vẫn đọc được | Mất majority primary | Quorum, status, leader | Thêm secondary để “thêm phiếu” |
| Write p95 tăng khi một follower mất | Phải nhận ACK từ primary xa | RTT giữa primaries, raft delay | Chỉ tăng heap |
| App vùng A lỗi, vùng B vẫn chạy | Client routing/firewall/DNS | DNS, advertised endpoints, TLS/Bolt | Restore database |
| Read secondary trả dữ liệu cũ | Async catch-up lag | Applied/commit indices, bookmark | Xóa/rebuild graph |
| Write timeout nhưng node đã xuất hiện | Commit xong, ACK thất lạc | Business key/transaction state | Retry `CREATE` vô điều kiện |
| Leader thay đổi liên tục | Packet loss/jitter, GC, I/O, CPU | Election logs, heartbeat, host metrics | Giảm election timeout tùy ý |
| Server healthy, app không truy cập | Endpoint/routing sai | Client-side Bolt/TLS/DNS | Ép failover thủ công |
| Secondary lỗi, writes còn khỏe | Giảm năng lực đọc | Read pool, CPU, p95 | Dừng toàn cụm |
| Query chậm, mạng bình thường | Fan-out, sort, index hoặc GC | `EXPLAIN`/`PROFILE`, Rows, DB Hits | Tăng số primary |
| Chia 1–1–1 | Không bên nào đạt quorum | Raft connectivity | Ép write trên mỗi đảo |

## 18. Diễn tập network delay và partition an toàn trong lab

**Không chạy fault injection trên production khi chưa có quy trình và phê duyệt.** Bài thực hành giả định cluster 3 primary riêng, dữ liệu giả, có quyền reset, đường quản trị ngoài băng và bản sao dự phòng.

### 18.1. Tiền kiểm

1. Dựng database `supply` trên 3 primary; tùy chọn thêm secondary.
2. Xác nhận các cổng Bolt, cluster communication và advertised addresses **đúng phiên bản Neo4j thực tế**.
3. Tạo constraint `NetDemoOrder(orderId)`, chạy workload read/write có ID duy nhất.
4. Thu 5–15 phút baseline: write p95/p99, read freshness, election, replication metrics, driver retry.
5. Đảm bảo có thể **tự động gỡ mọi hạn chế mạng** dù phiên shell/test bị mất.
6. Ghi kế hoạch rollback và người thực hiện.

### 18.2. Thử A: tăng latency giữa primary

Mô phỏng tăng RTT giữa các primary trong network test (ví dụ 40 ms), giữ các biến khác ổn định.

Kiểm tra: write p95/p99 thay đổi bao nhiêu, sự kiện leader đổi hay không, replication success/fail, read locality, CPU/I/O. **Không giả định mọi write sẽ tăng đúng 40 ms.**

### 18.3. Thử B: cách ly follower P3

Ngắt luồng cluster giữa P3 và P1/P2 theo cơ chế lab, **không khóa đường quản trị**. Mong đợi P1/P2 còn quorum và tiếp tục write; P3 không được tự commit. Khi gỡ sự cố, đo **catch-up time** của P3.

### 18.4. Thử C: cách ly writer P1

Giữ P2↔P3 liên thông, cô lập P1. Quan sát bầu writer mới, khoảng ngắt ghi, driver routing refresh và những write có kết quả không xác định.

### 18.5. Thử D: mất quorum toàn bộ

Tách 3 primary để không nhóm nào có 2 phiếu. Xác minh không có write commit mới khi thiếu quorum. Các API được phép đọc stale có thể hoạt động theo bản sao khả dụng; API ghi phải trả trạng thái phù hợp, không giả thành công.

**Không đưa lệnh `iptables` hay `tc netem` áp thẳng lên NIC production**. Cần thiết kế fault injection trong lab để không vô tình cô lập máy khỏi đường quản trị hoặc ảnh hưởng dịch vụ khác.

## 19. Mẫu bảng đo sau diễn tập

| Chỉ số | Baseline | Delay test | Partition 2–1 | Sau phục hồi |
| --- | --- | --- | --- | --- |
| Primary liên lạc được | 3/3 | 3/3 | 2/3 phía đa số | 3/3 |
| Write quorum | Có | Có | Có ở nhóm 2 | Có |
| Write p95/p99 | Đo | Đo | Đo cùng thời gian chuyển leader | Đo |
| Write error rate | Đo | Đo | Đo | Đo |
| Read p95 địa phương | Đo | Đo | Đo theo bản sao reachable | Đo |
| Replication/applied lag | Đo | Đo | Theo member bị cách ly | Đo catch-up |
| Driver retry/errors | Đo | Đo | Đo | Đo |
| Số commit ambiguous | Đếm business ID | Đếm | Đếm | Đối soát |
| Số đơn hàng duplicate | 0 | 0 | 0 | 0 |
| Outage duration | 0 hoặc baseline | Đo | Đo | Đóng sự cố |

Đây là **mẫu báo cáo**, không phải số liệu đã đo. Cần giữ workload, dataset, tỷ lệ read/write, loại query và cách kết nối tương đương, đồng thời đánh dấu thời điểm election hay sửa mạng.

Một cluster phía đa số có thể ghi trong khi client phía thiểu số lỗi: **đó không tự mâu thuẫn với bảo đảm Raft**. Báo cáo phải nêu rõ vùng và đường đi của từng client.

## 20. Lựa chọn topology và chiến lược nhiều vùng

| Mô hình | Điểm mạnh | Điểm yếu |
| --- | --- | --- |
| 1 primary | Tối thiểu chi phí replication và write latency | Không chịu lỗi primary |
| 3 primary cùng datacenter | Có HA một primary, RTT LAN thấp | Mất cả datacenter gây dừng ghi |
| 3 primary chia 2+1 datacenter | Có thể write nhanh ở vùng đa số | Mất vùng có 2 primary → mất quorum |
| 5 primary chia 2+2+1 | Chịu mất bất kỳ một trong ba datacenter | WAN/replication và vận hành phức tạp |
| 3 primary + local secondary | Đọc gần client, giảm tải primary | Secondary không thêm quorum và có thể stale |
| Nhiều cluster độc lập có database replication | Tách failure domain giữa các vùng | DR/promotion và consistency khác với một Raft group |

Tài liệu Neo4j từ **2026.08** mô tả cách triển khai **nhiều cluster độc lập có database replication**. Đây **không phải** 5 primary cùng một nhóm Raft trải vùng. Replica database ở cluster đích có trạng thái read-only trước khi được promote theo quy trình; `system` và role/user metadata không tự được nhân bản như user database. Không suy ra có thể ghi đồng thời an toàn ở hai cluster độc lập khi bị partition.

Nếu doanh nghiệp đòi hỏi “mọi vùng vẫn tự ghi đơn ngay cả khi ngắt hẳn WAN”, một cluster Raft ưu tiên an toàn của commit và **không cho phía thiếu quorum ghi**. Muốn đạt yêu cầu đó phải thay đổi kiến trúc nghiệp vụ (ví dụ hàng đợi nhận đơn bền vững theo vùng rồi đồng bộ có idempotency/conflict resolution), không được làm yếu quorum bằng thao tác thủ công.

## 21. Hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Ba server bật là write được.” | Cần quorum primary theo database và route tới writer |
| “Secondary có thể bỏ phiếu khi thiếu primary.” | Không, secondary dùng cho read scaling |
| “Leader cũ luôn được ghi tiếp khi bị cô lập.” | Mất quorum thì không commit mới |
| “Read thành công nghĩa dữ liệu mới nhất.” | Secondary có thể lag, bookmark có thể cần |
| “Bookmark làm replica cập nhật nhanh hơn.” | Bookmark đợi trạng thái causal, không tăng replication speed |
| “Cluster là backup.” | Xóa nhầm có thể replicate; vẫn cần backup độc lập |
| “Tăng primary làm query nhanh hơn.” | Có lợi chịu lỗi, không tự tối ưu Cypher/DB Hits |
| “Ping được host là đủ.” | Raft/Bolt/routing/TLS có các đường truy cập khác nhau |
| “Write timeout nghĩa chắc chắn chưa commit.” | ACK có thể mất sau commit |
| “Tăng retry là chữa partition.” | Không tự tạo quorum, dễ gây retry storm |
| “`bolt://` tới một primary là HA.” | Direct không tự routing writer/reader |
| “Status endpoint read trả 200 thì write khỏe.” | Writable và read availability khác nhau |
| “Raft leadership thuộc cả server.” | Mỗi database có Raft group/leader riêng |
| “Mở lại mạng là replica đã bắt kịp ngay.” | Cần đo transaction catch-up |
| “Một số server lỗi nhưng quorum còn nên mọi client khỏe.” | Client routing có thể bị tách khỏi nhóm majority |
| “Mất quorum có thể ép secondary làm writer.” | Không bảo đảm an toàn, cần DR workflow được hỗ trợ |

## 22. Checklist triển khai và bài tập

### 22.1. Checklist

1. Xác định topology primary/secondary và writer cho **từng database**, kể cả `system`.
2. Định nghĩa write/read SLO, freshness, RPO, RTO và mức lỗi chấp nhận.
3. Tính quorum và rủi ro mất primary/datacenter theo bố trí thực.
4. Đo RTT/jitter, packet loss, bandwidth giữa primary; quan sát p95/p99 commit.
5. Xác nhận URI routing, DNS/multiple entrypoints, advertised addresses và TLS.
6. Phân loại API được phép đọc stale và API phải có bookmarks/read-your-writes.
7. Thiết kế business keys, constraint và retry idempotent cho write ambiguous.
8. Đặt timeout/backoff/retry budget, circuit breaker và giới hạn concurrency.
9. Giám sát Raft indices, leader, heartbeat, routing errors và client p99.
10. Diễn tập follower loss, writer loss, network partition, client bootstrap lỗi, secondary lag.
11. Có backup và DR plan; không sửa Raft store/ép quorum tùy tiện.
12. Ghi RTO thực tế, duplicate-prevention kết quả và bài học sau diễn tập.

### 22.2. Bài tập tự luyện

1. Một database có 5 primary. Tính quorum và phân tích partition `3+2`. Bên nào có thể commit?
2. Ba primary phân bố `2P+1P` trên hai vùng. Nếu vùng có 2 primary bị mất, viết cách xử lý API đọc/ghi.
3. Giải thích vì sao thêm 80 ms RTT giữa hai datacenter có thể làm write p95 tăng nhưng không phải mọi read tại secondary địa phương đều tăng cùng lượng.
4. Một secondary bị lag 10 giây. Thiết kế luồng “tạo đơn rồi xem đơn” đúng read-your-writes bằng Java Driver.
5. Client nhận timeout ngay sau `MERGE`: nêu hai khả năng commit và cách xác minh an toàn.
6. Vì sao `bolt://p1:7687` lỗi khi P1 chết dù P2/P3 đủ quorum? Cách sửa discovery?
7. `SHOW SERVERS` báo server healthy nhưng endpoint `writable` báo không sẵn sàng; lập quy trình điều tra.
8. Chọn sáu metric cho failure injection và mô tả diễn biến khi mất follower, mất writer và phục hồi.
9. Vì sao `@Transactional(readOnly=true)` không bảo đảm replica luôn có dữ liệu mới nhất?
10. Muốn chịu mất bất kỳ một datacenter với ba vùng và năm primary, nên chọn bố trí nào? Có đánh đổi latency gì?
11. Một cụm `1+1+1` còn ba bản sao đọc được một ít dữ liệu. Vì sao không được ép ba phía cùng commit?
12. Lập bảng go/no-go diễn tập gồm write availability, p95/p99, replication lag, idempotency và rollback.

## 23. Ghi nhớ

- **Quorum primary theo database** quyết định write availability: `floor(N/2)+1`.
- Primary xác nhận write bằng Raft; **secondary nhân bản bất đồng bộ** để mở rộng đọc và không có quyền bỏ phiếu.
- Network delay ảnh hưởng commit, client response, routing và secondary catch-up; đo **p95/p99 và thời gian lag thực**.
- Partition khiến nhóm có đa số có thể tiếp tục commit, nhóm thiểu số không; đọc còn có thể stale.
- Ba primary chịu một lỗi; năm primary chịu hai lỗi, nhưng chịu mất datacenter còn tùy **phân bố topology**.
- `neo4j://`/`neo4j+s://` hỗ trợ routing, còn `bolt://`/`bolt+s://` kết nối trực tiếp một member.
- Bookmarks giúp bảo đảm read-your-writes khi cần, nhưng có thể chờ catch-up và tăng latency.
- **Write timeout ở client không chứng minh transaction chưa commit**; dùng idempotency key/unique constraint và đối soát.
- Theo dõi status endpoint, `SHOW DATABASES`/`SHOW SERVERS`, Raft metrics và application routing từ nhiều member.
- Diễn tập delay/partition trong lab với rollback, không thay firewall/election timeout production tùy ý.

### Tài liệu tham khảo chính thức

- [Neo4j Operations Manual — Clustering architecture](https://neo4j.com/docs/operations-manual/current/clustering/introduction/)
- [Neo4j Operations Manual — Leadership, routing and load balancing](https://neo4j.com/docs/operations-manual/current/clustering/setup/routing/)
- [Neo4j Operations Manual — Designing resilient multi-region clusters](https://neo4j.com/docs/operations-manual/current/clustering/multi-region-deployment/geo-redundant-deployment/)
- [Neo4j Operations Manual — Multi-data center routing](https://neo4j.com/docs/operations-manual/current/clustering/multi-region-deployment/multi-data-center-routing/)
- [Neo4j Operations Manual — Cluster status endpoints](https://neo4j.com/docs/operations-manual/current/clustering/monitoring/endpoints/)
- [Neo4j Operations Manual — Essential metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/essential/)
- [Neo4j Operations Manual — Metrics reference](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/reference/)
- [Neo4j Operations Manual — Clustering glossary](https://neo4j.com/docs/operations-manual/current/clustering/glossary/)
- [Neo4j Java Driver Manual — Connection and routing](https://neo4j.com/docs/java-manual/current/connect/)
- [Neo4j Java Driver Manual — Advanced connection information](https://neo4j.com/docs/java-manual/current/connect-advanced/)
- [Neo4j Java Driver Manual — Coordinate transactions with bookmarks](https://neo4j.com/docs/java-manual/current/bookmarks/)
- [Neo4j Java Driver Manual — Managed transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Operations Manual — Backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/)
- [Spring Data Neo4j — Reference](https://docs.spring.io/spring-data/neo4j/reference/)
