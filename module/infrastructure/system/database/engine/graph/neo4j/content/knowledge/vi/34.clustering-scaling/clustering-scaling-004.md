# Định tuyến truy vấn đọc hoặc ghi và cân bằng tải phía trình điều khiển

Khi Neo4j chỉ chạy trên một máy, ứng dụng Java có thể kết nối tới một địa chỉ Bolt rồi thực hiện toàn bộ truy vấn. Khi dữ liệu được phục vụ bởi **Neo4j cluster**, cách làm này chưa tận dụng đúng các thành viên trong cụm: giao dịch ghi cần đến nơi có khả năng tiếp nhận ghi, truy vấn đọc có thể được phục vụ ở nhiều máy và sau một lần thay đổi leader, địa chỉ phù hợp để ghi có thể khác trước. **Neo4j Java Driver hỗ trợ định tuyến (routing) theo loại giao dịch và quản lý kết nối**, giúp ứng dụng không phải tự viết danh sách máy chủ rồi chọn ngẫu nhiên một máy cho từng truy vấn.

Bài thuộc chương **Cụm và mở rộng** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Module sử dụng Neo4j để lưu property graph gồm node, relationship, index và constraint, thực thi Cypher, nhập dữ liệu và tích hợp bằng Java Driver hoặc Spring Data Neo4j (SDN). Nội dung tập trung vào **routing read/write, connection pool, phân phối tải đọc, nhất quán nhân quả bằng bookmark và xử lý lỗi khi cấu trúc cluster thay đổi**.

> **Phạm vi triển khai:** Những khái niệm cluster primary/secondary, discovery và routing bên dưới dựa trên Neo4j Enterprise 5.x và họ phiên bản tương thích. Neo4j Community không cung cấp cùng khả năng clustering Enterprise. Neo4j AuraDB che giấu nhiều chi tiết topology và cung cấp endpoint theo gói dịch vụ. Tên cài đặt, cách chọn thành viên, chính sách read routing và khả năng server-side routing có thể khác theo phiên bản/edition. Đọc tài liệu đúng phiên bản trước khi đặt giả định về địa chỉ, độ trễ sao chép hoặc tính sẵn sàng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích khác biệt giữa **kết nối trực tiếp** và **kết nối có routing**.
2. Phân biệt vai trò của thành viên **primary**, **secondary** và **leader** trong đường đọc/ghi của một cluster.
3. Sử dụng `neo4j://`, `neo4j+s://` và `Session.executeRead`/`executeWrite` đúng mục đích.
4. Giải thích driver sử dụng routing table và connection pool như thế nào; phân biệt **cân bằng tải** với **tăng thông lượng bảo đảm**.
5. Áp dụng **bookmark** khi đọc sau ghi để hạn chế trường hợp một replica chưa bắt kịp dữ liệu.
6. Kiểm thử failover, truy cập mạng, lỗi tạm thời, ghi idempotent và phân phối tải từ ứng dụng thực.
7. Chọn chỉ số quan sát, kịch bản benchmark và cấu hình tối thiểu cho ứng dụng Java/Spring Data Neo4j.

## 2. Vì sao ứng dụng cần biết đang chạy trong cluster?

Giả sử đồ thị nghiệp vụ có:

~~~text
(:Customer {customerId: 'C01'})
    -[:PLACED]->
(:Order {orderId: 'O01', totalAmount: 120000})
~~~

Ứng dụng có hai loại việc:

- **Đọc:** hiển thị lịch sử đơn hàng và các quan hệ của khách hàng.
- **Ghi:** tạo đơn, cập nhật trạng thái, thêm relationship hoặc sửa thuộc tính.

Một cluster có thể cung cấp nhiều nơi phục vụ đọc, nhưng không có nghĩa **mọi máy đều độc lập chấp nhận cùng một thao tác ghi**. Dữ liệu phải được ghi theo quy tắc nhất quán của cluster, sau đó lan truyền đến các thành viên khác. Nếu ứng dụng chỉ kết nối cứng tới một địa chỉ thành viên, việc mất thành viên đó hoặc thay leader có thể khiến nhiều request lỗi dù cluster vẫn còn khả năng phục vụ.

~~~mermaid
flowchart LR
    APP["Ứng dụng Java / SDN"] --> DRIVER["Neo4j Java Driver<br/>routing + connection pool"]
    DRIVER -->|"WRITE"| P1["Primary P1<br/>leader ghi hiện tại"]
    DRIVER -->|"READ"| P2["Primary P2<br/>có thể đọc"]
    DRIVER -->|"READ"| S1["Secondary S1<br/>phục vụ đọc nếu cấu hình cho phép"]
    P1 <-.->|"Consensus / replication"| P2
    P1 -.->|"Đồng bộ dữ liệu"| S1
~~~

Sơ đồ là **mô hình khái niệm**, không phải topology hay danh sách router/reader/writer được bảo đảm cho mọi cluster. Một hệ thống thật có thể có nhiều primary, nhiều secondary, nhiều database và chính sách chọn nơi đọc khác nhau.

## 3. Primary, secondary và leader: không nhầm vai trò

| Thành phần | Vai trò khái niệm | Điều cần nhớ |
|---|---|---|
| **Primary** | Thành viên tham gia duy trì dữ liệu và cơ chế đồng thuận của database trong cluster | Không đồng nghĩa **mọi primary đều là leader** cùng lúc |
| **Leader của database** | Thành viên giữ vai trò xử lý ghi theo cơ chế cluster tại thời điểm đó | Leader có thể thay đổi sau failover |
| **Primary không phải leader** | Có thể phục vụ truy vấn đọc theo routing/topology | Không giả định việc ghi trực tiếp sẽ được tiếp nhận như leader |
| **Secondary** | Thường dùng tăng khả năng phục vụ đọc và bản sao dữ liệu mà không tham gia quorum ghi như primary | Khả năng đọc, độ trễ sao chép và chính sách routing phụ thuộc phiên bản/cấu hình |
| **Router** | Địa chỉ để driver lấy thông tin nơi nên gửi đọc/ghi | Một máy có thể tham gia vai trò router và các vai trò khác; không phải “một database router” riêng |

Trong Neo4j, **mỗi database trong cluster có thể có topology và leader riêng**. Vì thế một câu như “máy P1 luôn là máy ghi của toàn bộ DBMS” không phải giả định an toàn. Driver cần biết **database đích** và sử dụng thông tin routing tương ứng.

### Nhiều máy không tự động nhân đôi mọi khả năng

- Bổ sung nơi phục vụ **đọc** có thể giúp mở rộng tổng số truy vấn đọc khi workload và mạng phù hợp.
- Tải **ghi** vẫn chịu ràng buộc leader/consensus, khóa, tài nguyên và độ phức tạp cập nhật.
- Một truy vấn duyệt đồ thị quá rộng có thể chiếm nhiều CPU trên **mỗi** replica; tăng replica không sửa câu Cypher đó.
- Một cluster đủ số máy nhưng thiếu quorum, mất mạng liên vùng hoặc có replica chưa bắt kịp vẫn có thể gặp gián đoạn hay lỗi độ trễ.

Phải phân biệt **high availability (HA)** với **horizontal read scaling**: một giải pháp có nhiều bản sao chưa chắc đã đáp ứng cả mục tiêu uptime lẫn throughput dự kiến.

## 4. Routing URI khác direct URI như thế nào?

Neo4j Java Driver suy ra kiểu kết nối từ **scheme** của URI. Đây là quyết định đầu tiên cần kiểm tra trong cấu hình.

| URI scheme | Định hướng | Trường hợp điển hình |
|---|---|---|
| `neo4j://host:7687` | **Routing-aware** | Kết nối cluster, để driver sử dụng routing table |
| `neo4j+s://host:7687` | Routing-aware + **TLS với chứng chỉ được tin cậy** | Phổ biến với endpoint quản lý như AuraDB và môi trường TLS |
| `neo4j+ssc://host:7687` | Routing-aware + TLS với cơ chế chấp nhận chứng chỉ tự ký theo cách driver hỗ trợ | Chỉ cân nhắc trong môi trường kiểm thử đã kiểm soát; không dùng thay bảo mật production |
| `bolt://host:7687` | **Kết nối trực tiếp** tới địa chỉ chỉ định | Standalone, debug một thành viên hoặc trường hợp đã thiết kế direct connection |
| `bolt+s://host:7687` | Direct + TLS tin cậy | Kết nối trực tiếp có TLS |

**Sai lầm phổ biến:** đổi `neo4j+s://cluster.example.com` thành `bolt://node-a:7687` vì máy node-a trả kết quả nhanh ở lúc thử. Khi node-a mất kết nối, driver không thể tận dụng cơ chế routing tương tự; nếu node-a không còn là nơi ghi, giao dịch ghi cũng có thể thất bại hoặc bị chuyển xử lý theo cơ chế server/version.

**Một điểm cần phân biệt:** driver có hỗ trợ routing không có nghĩa nó luôn mở kết nối tới toàn bộ thành viên trong cluster. Nó tìm thông tin routing khi cần, duy trì connection pool và tạo kết nối theo nhu cầu của workload.

### Endpoint ban đầu không phải toàn bộ danh sách endpoint

Với `neo4j://cluster.example.com`, hostname ban đầu thường dùng để **bootstrap** discovery. Driver có thể nhận các địa chỉ **routers, readers và writers** theo routing table. Vì vậy, ngay cả khi bootstrap endpoint truy cập được, các truy vấn sau đó vẫn có thể lỗi nếu những địa chỉ được công bố **không thể truy cập từ mạng của ứng dụng**.

Đặc biệt khi triển khai Docker, Kubernetes, NAT hoặc cluster liên vùng:

1. Kiểm tra hostname và port **advertised** có thể resolve và kết nối từ **máy chạy ứng dụng**.
2. Không chỉ kiểm tra `localhost:7687` trên host Neo4j.
3. Xác minh chứng chỉ TLS có tên miền phù hợp với hostname được dùng.
4. Kiểm tra firewall, DNS, private routing và khả năng tiếp cận từng thành viên được trả về.
5. Đừng hard-code địa chỉ nội bộ container/pod không truy cập được từ ngoài cụm.

Sự khác nhau giữa **listen address** và **advertised address** rất quan trọng: server lắng nghe trên một interface nhưng cần công bố địa chỉ mà client thật có thể dùng.

## 5. Routing table hoạt động ra sao?

Ở kết nối routing-aware, driver có cơ chế lấy và làm mới **routing table** cho database. Về mặt khái niệm, bảng đó chứa:

~~~text
Database: neo4j
Routers: [R1, R2, ...]
Readers: [P2, S1, ...]
Writers: [P1, ...]
TTL: thời hạn thông tin routing
~~~

Đây là ví dụ **minh họa**, không phải kết quả query thực, không cố định số reader/writer và không bảo đảm danh sách đầy đủ ở mọi thời điểm.

~~~mermaid
sequenceDiagram
    participant A as Ứng dụng
    participant D as Java Driver
    participant R as Router / cluster
    participant P as Writer hiện tại
    participant S as Reader được chọn
    A->>D: Tạo Driver với neo4j+s://
    D->>R: Khám phá routing cho database
    R-->>D: Routing table + TTL
    A->>D: executeRead(...)
    D->>S: Gửi read transaction
    S-->>D: Kết quả
    A->>D: executeWrite(...)
    D->>P: Gửi write transaction
    P-->>D: Commit + bookmark
    Note over D,R: Routing được làm mới khi cần<br/>hoặc khi topology/TTL thay đổi
~~~

### Ba sự kiện làm routing thay đổi

- **Leader switch:** địa chỉ writer của database có thể đổi.
- **Thành viên vào/ra cluster:** tập reader/router có thể thay đổi.
- **Routing TTL hết hoặc kết nối xảy ra lỗi:** driver cần làm mới thông tin theo thuật toán của bản driver.

**Routing table không phải danh sách tĩnh trong source code.** Không nên xây “bản sao routing table” riêng bằng mảng IP do ứng dụng tự duy trì, trừ khi có yêu cầu tích hợp cụ thể và cơ chế quản lý nhất quán.

### Driver có luôn chia đều 50/50 giữa hai reader không?

**Không có bảo đảm mặc định như vậy.** Việc chọn địa chỉ có thể phụ thuộc:

- Tập reader thực tế trong routing table cho database đó.
- Chính sách/khả năng routing do server cung cấp.
- Connection pool, thời gian sống connection và concurrency.
- Cách driver chọn server trong **phiên bản thư viện cụ thể**.
- Số transaction, thời lượng query và sự phân bố request từ ứng dụng.

Ngay cả khi hai máy nhận số **transaction** gần nhau, tải CPU có thể rất khác nếu một transaction mở rộng 100 relationship còn transaction khác duyệt hàng triệu cạnh. “Load balancing” nên đánh giá bằng **latency, throughput và tài nguyên thực**, không chỉ đếm số query.

## 6. Phân biệt `executeRead` và `executeWrite`

Java Driver cung cấp **managed transaction functions**:

~~~java
session.executeRead(tx -> {
    // Đọc bằng Cypher và trả kết quả.
    return ...;
});
~~~

~~~java
session.executeWrite(tx -> {
    // Ghi bằng Cypher rồi commit khi callback thành công.
    return ...;
});
~~~

**Ý nghĩa quan trọng:**

1. `executeRead` cho driver biết giao dịch dùng **read access mode**, để chọn nơi phục vụ đọc được cluster công bố.
2. `executeWrite` yêu cầu **write access mode**, để chọn nơi phù hợp cho ghi.
3. Driver quản lý vòng đời transaction và **có thể retry** một số lỗi tạm thời, với giới hạn theo cấu hình.
4. Callback có thể chạy **nhiều lần**; không thực hiện tác dụng bên ngoài không idempotent trong callback.
5. Đường routing và việc được quyền **thực hiện thao tác** là hai chuyện khác nhau. Access mode **không thay thế Neo4j RBAC**.

Nếu một transaction cần **đọc và ghi atomically**, hãy chạy các bước đó **trong cùng `executeWrite`**. Không tách làm `executeRead` rồi `executeWrite` chỉ để cố “phân tải” khi logic cần snapshot/transaction chung.

### `executeRead` không làm query nhanh hơn bằng phép màu

Một query `MATCH` không có index vẫn có thể scan trên reader. Một câu Cypher chứa `ORDER BY` lớn vẫn có thể chiếm nhiều RAM ở reader. **Routing là lựa chọn nơi chạy**, còn **tối ưu Cypher** vẫn phụ thuộc index, schema, cardinality, planner và dữ liệu.

## 7. Ví dụ Java Driver hoàn chỉnh: đọc và ghi trên cluster

Giả sử cluster có database `neo4j` và dữ liệu:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_request_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.requestId IS UNIQUE;
~~~

**Tạo constraint là bước triển khai schema riêng**, cần tài khoản có quyền tương ứng. Không cho runtime repository quyền quản trị schema chỉ để thực thi `executeRead`/`executeWrite`.

Lớp Java 17+ dưới đây minh họa dùng **một Driver dài hạn**, các `Session` ngắn và truy vấn có tham số. Trong môi trường Spring Boot, thường cấu hình Driver làm bean/singleton thay vì tạo lại cho mỗi request.

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Config;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class ClusterOrderRepository implements AutoCloseable {
    private final Driver driver;
    private final String database;

    public record OrderView(String orderId, long totalAmount) {}

    public ClusterOrderRepository(
            String uri,
            String username,
            String password,
            String database) {
        Config config = Config.builder()
                .withMaxTransactionRetryTime(30, TimeUnit.SECONDS)
                .build();
        this.driver = GraphDatabase.driver(
                uri, AuthTokens.basic(username, password), config);
        this.database = database;
        driver.verifyConnectivity();
    }

    public List<OrderView> findOrders(String customerId) {
        try (Session session =
                driver.session(SessionConfig.forDatabase(database))) {

            return session.executeRead(tx -> tx.run("""
                    MATCH (c:Customer {customerId: $customerId})
                          -[:PLACED]->(o:Order)
                    RETURN o.orderId AS orderId,
                           o.totalAmount AS amount
                    ORDER BY orderId
                    LIMIT 100
                    """, Map.of("customerId", customerId))
                    .list(record -> new OrderView(
                            record.get("orderId").asString(),
                            record.get("amount").asLong())));
        }
    }

    public String createOrder(
            String customerId,
            String requestId,
            long totalAmount) {

        try (Session session =
                driver.session(SessionConfig.forDatabase(database))) {

            return session.executeWrite(tx -> tx.run("""
                    MATCH (c:Customer {customerId: $customerId})
                    MERGE (o:Order {requestId: $requestId})
                    ON CREATE SET
                        o.orderId = $requestId,
                        o.totalAmount = $amount,
                        o.status = 'NEW'
                    MERGE (c)-[:PLACED]->(o)
                    RETURN o.requestId AS requestId
                    """, Map.of(
                        "customerId", customerId,
                        "requestId", requestId,
                        "amount", totalAmount))
                    .single()
                    .get("requestId")
                    .asString());
        }
    }

    @Override
    public void close() {
        driver.close();
    }
}
~~~

Ví dụ cách khởi tạo ở entry point:

~~~java
String uri = System.getenv("NEO4J_URI");
String user = System.getenv("NEO4J_USERNAME");
String password = System.getenv("NEO4J_PASSWORD");

try (var repository = new ClusterOrderRepository(
        uri, user, password, "neo4j")) {
    var orders = repository.findOrders("C01");
    System.out.println("Orders: " + orders.size());
}
~~~

Thiết lập `NEO4J_URI` theo địa chỉ cluster hoặc Aura do quản trị cung cấp, chẳng hạn `neo4j+s://graph.example.org` khi TLS và routing được hỗ trợ. Không ghi mật khẩu vào source.

**Cần hiểu đúng ví dụ:**

- `findOrders` được định tuyến theo **READ** khi driver đang kết nối cluster routing-aware. Nó không cam kết dùng riêng secondary; read servers do topology/routing cung cấp.
- `createOrder` được định tuyến theo **WRITE**. Trong cùng transaction, query tìm Customer, upsert Order và tạo quan hệ `PLACED`.
- `MERGE` dựa trên `requestId` và uniqueness constraint giúp giảm nguy cơ tạo trùng khi **request được thử lại**. Nhưng nếu hai request dùng cùng `requestId` mà payload khác, code hiện tại **không tự phát hiện khác biệt**: cần validate hoặc so đối chiếu trước khi trả thành công.
- `.single()` yêu cầu query trả đúng một hàng. Nếu `Customer` không tồn tại, `MATCH` loại hàng và phương thức thất bại; ứng dụng nên ánh xạ tình huống đó thành lỗi nghiệp vụ rõ ràng.
- Callback managed transaction phải an toàn khi driver retry. **Không gửi email, gọi thanh toán hoặc tăng bộ đếm ngoài DB** bên trong callback.
- `driver.verifyConnectivity()` chỉ kiểm tra khả năng kết nối cơ bản tại thời điểm gọi; nó **không** chứng minh mọi member đều reachable, mọi privilege đúng hoặc failover sẽ thành công.

### Một Driver, nhiều Session

~~~text
Driver (long-lived, thread-safe)
    |
    +-- Session request A --> executeRead --> reader do routing chọn
    |
    +-- Session request B --> executeRead --> reader do routing chọn
    |
    +-- Session request C --> executeWrite --> writer do routing chọn
    |
    +-- Connection pools được quản lý bên trong Driver
~~~

Một `Driver` dùng chung được cho nhiều thread; `Session` **không thread-safe** và nên được tạo cho một đơn vị công việc. Không giữ một Session toàn cục dùng giữa các request HTTP đồng thời. Cũng không khởi tạo `Driver` mới cho từng truy vấn vì như vậy làm mất lợi ích pooling và tăng chi phí discovery/kết nối.

## 8. `SessionConfig.defaultAccessMode` với implicit transaction

Không phải ứng dụng nào cũng dùng managed transaction. Khi gọi `session.run(...)` ngoài explicit/managed transaction, Java Driver thực hiện **implicit transaction** và dùng `defaultAccessMode` của session để chọn access mode.

Ví dụ chỉ đọc:

~~~java
import org.neo4j.driver.AccessMode;
import org.neo4j.driver.SessionConfig;

SessionConfig readSessionConfig = SessionConfig.builder()
        .withDatabase("neo4j")
        .withDefaultAccessMode(AccessMode.READ)
        .build();

try (var session = driver.session(readSessionConfig)) {
    var ids = session.run("""
            MATCH (o:Order)
            RETURN o.orderId AS id
            LIMIT 20
            """)
            .list(r -> r.get("id").asString());
}
~~~

Nếu không chỉ định mode và không dùng `executeRead`, các implicit transaction có thể dùng **WRITE mode mặc định** theo hành vi driver. Khi đó truy vấn `MATCH` đơn giản có thể được gửi đến nơi phục vụ ghi dù về mặt logic nó chỉ đọc; đây là một lỗi thiết kế phổ biến khi kỳ vọng mở rộng tải đọc.

**Phân biệt:** `SessionConfig.withDefaultAccessMode(...)` ảnh hưởng tới các đường chạy dùng mode mặc định, còn `executeRead`/`executeWrite` **chủ động chỉ định** access mode theo loại transaction. Đừng cố sửa đường routing của managed transaction bằng cách đổi duy nhất default mode của session.

### Implicit transaction và retry

Managed transaction cung cấp cơ chế retry phù hợp cho lỗi tạm thời. Implicit transaction **không có cùng bảo đảm** retry toàn callback ở các phiên bản driver; một số bản mới có hỗ trợ retry hạn chế cho trường hợp cụ thể. Với import `CALL { ... } IN TRANSACTIONS`, nhiều lô có thể commit trước khi query ngoài thất bại. **Không retry toàn câu lệnh một cách mù quáng** nếu thao tác không idempotent.

## 9. Tính nhất quán: đọc sau ghi khi read được route sang replica

Giả sử một request thực hiện:

~~~text
T0: executeWrite tạo O02 trên writer -> COMMIT
T1: executeRead lấy danh sách đơn từ reader khác
~~~

Nếu reader nhận dữ liệu qua cơ chế sao chép và chưa bắt kịp commit tại T0, câu hỏi là: **làm sao bảo đảm truy vấn đọc phản ánh ít nhất bản ghi vừa ghi?**

Neo4j Java Driver hỗ trợ **bookmark** để duy trì **causal consistency**: một read transaction phụ thuộc bookmark cần được phục vụ sau khi dữ liệu tương ứng đã đạt trạng thái được yêu cầu. Driver có thể chờ một server đọc bắt kịp hoặc báo lỗi nếu không thể đáp ứng trong giới hạn.

### 9.1. Đọc sau ghi trong cùng Session

Một `Session` có thể tự quản lý bookmark từ các transaction của chính session đó. Ví dụ:

~~~java
try (Session session =
        driver.session(SessionConfig.forDatabase("neo4j"))) {

    session.executeWrite(tx -> {
        tx.run("""
                MERGE (o:Order {requestId: $requestId})
                ON CREATE SET o.orderId = $requestId,
                              o.totalAmount = 120000
                """, Map.of("requestId", "READ-AFTER-WRITE-01"))
                .consume();
        return null;
    });

    var record = session.executeRead(tx -> tx.run("""
            MATCH (o:Order {requestId: $requestId})
            RETURN o.orderId AS orderId
            """, Map.of("requestId", "READ-AFTER-WRITE-01"))
            .single());

    System.out.println(record.get("orderId").asString());
}
~~~

Với cùng session, driver duy trì quan hệ nhân quả cần thiết giữa transaction ghi đã commit và transaction đọc tiếp theo. Dù query đọc được route sang server khác, cơ chế bookmark giúp bảo đảm **read-your-writes** trong phạm vi và điều kiện hỗ trợ.

**Bookmark không có nghĩa** mọi read trong toàn bộ cluster đều tức thời nhìn thấy ghi vừa xảy ra. Nó cũng không thay thế phân tích isolation của một transaction hay kiểm tra trạng thái commit khi kết nối rớt.

### 9.2. Khi hai Session thuộc hai request khác nhau

Một ứng dụng có request A ghi và request B đọc trên session riêng. Muốn duy trì causal consistency **xuyên Session**, phải **truyền bookmark** thích hợp hoặc dùng **BookmarkManager** của API/driver phù hợp phiên bản. Không nên suy rằng chỉ vì hai session dùng cùng một `Driver` thì mọi request đọc tự động “thấy dữ liệu mới nhất” trong mọi điều kiện.

Ví dụ luồng khái niệm:

~~~text
Request A / Session A:
  WRITE -> COMMIT -> bookmark B

Request B / Session B:
  khởi tạo với B hoặc dùng shared bookmark manager phù hợp
  READ -> yêu cầu kết quả ít nhất phù hợp với B
~~~

Trong ứng dụng multi-thread, việc dùng bookmark manager chung cần lựa chọn theo **ranh giới nghiệp vụ**. Chia sẻ bookmark không cần thiết có thể tăng yêu cầu chờ nhất quán và tạo liên hệ ngoài dự định giữa các luồng. Đối với luồng đơn thuần đọc dữ liệu cũ chấp nhận được, có thể không cần truyền bookmark từ một giao dịch khác.

### 9.3. Không cố định mọi đọc vào leader chỉ vì lo dữ liệu cũ

Nếu nghiệp vụ yêu cầu read-after-write, trước tiên thiết kế **causal consistency bằng bookmark**. Chỉ cố đưa mọi đọc vào writer thường làm giảm cơ hội cân bằng tải và có thể làm leader quá tải; trong các tình huống cần tính nhất quán chặt hơn, hãy nêu rõ yêu cầu và kiểm chứng trên phiên bản/topology thực tế.

## 10. Cân bằng tải thực tế: pool, session và locality

### 10.1. Connection pool

Java Driver quản lý **connection pool** để tái sử dụng các kết nối Bolt đến server được chọn. Một số cấu hình cần hiểu:

~~~java
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.Config;

Config config = Config.builder()
        .withMaxConnectionPoolSize(100)
        .withConnectionAcquisitionTimeout(20, TimeUnit.SECONDS)
        .withMaxTransactionRetryTime(30, TimeUnit.SECONDS)
        .build();
~~~

Những giá trị **100**, **20 giây**, **30 giây** chỉ là ví dụ để giải thích, **không phải cấu hình tối ưu** cho mọi hệ thống. Cần xem CPU, bộ nhớ, số request đồng thời, số instance ứng dụng, thời gian thực thi query và giới hạn kết nối của Neo4j.

| Cấu hình/khái niệm | Ý nghĩa | Sai lầm dễ gặp |
|---|---|---|
| Pool size | Giới hạn kết nối do driver quản lý theo phạm vi cấu hình | Đặt rất lớn để “tăng throughput” khi server đã bão hòa |
| Acquisition timeout | Giới hạn thời gian chờ lấy connection | Coi timeout lấy connection là query Cypher chạy chậm |
| Max transaction retry time | Ngân sách thử lại managed transaction | Lặp retry thêm nhiều tầng, tạo request storm |
| Session lifecycle | Đơn vị công việc logic của client | Chia sẻ một Session giữa thread, giữ Session mở quá lâu |
| Routing table refresh | Làm mới nơi phục vụ read/write | Tự pin toàn bộ kết nối vào một IP |

**Cân bằng tải không nhất thiết chuyển từng câu Cypher qua một máy khác.** Một transaction phải có tính nhất quán và thường gắn với server được chọn trong thời gian tồn tại. Driver cũng có thể tái sử dụng connection đến server đã chọn cho các transaction khác.

### 10.2. Độ gần mạng và cách phân phối đọc

Khi cluster trải qua nhiều vùng/region:

- Một reader xa có thể tăng **network latency** dù CPU server rảnh.
- Cross-region traffic có thể gây chi phí và tăng p95/p99.
- Chính sách routing/locality phụ thuộc server và sản phẩm triển khai; không giả định driver tự biết “chọn máy gần nhất” dựa trên địa lý.
- Các query trả hàng triệu record có thể bị chi phối bởi tốc độ mạng và thời gian mapping Java, không chỉ DB Hits.

Khi cần ưu tiên reader theo vùng, phải đọc tính năng **routing policy/region affinity** cụ thể của bản Neo4j và xác minh routing table có danh sách đúng như thiết kế.

### 10.3. Tải đọc phân bố nhưng dữ liệu vẫn phải đúng

Một thử nghiệm chỉ đo tỷ lệ CPU trên hai reader mà không đối chiếu kết quả có thể bỏ qua lỗi bookmark, missing relationship hoặc không đồng nhất snapshot. Khi benchmark, hãy kiểm tra cả **tính đúng đắn của query** và **cửa sổ dữ liệu**.

## 11. Spring Data Neo4j: routing xảy ra ở đâu?

Spring Data Neo4j sử dụng Neo4j Java Driver làm lớp kết nối, nên **URI routing và cấu hình Driver** vẫn quan trọng. Repository và template không tự tạo “load balancer” riêng cho cluster.

Ví dụ Spring Boot:

~~~yaml
spring:
  neo4j:
    uri: "neo4j+s://graph.example.org"
    authentication:
      username: "order_app"
      password: "${NEO4J_PASSWORD}"
  data:
    neo4j:
      database: "neo4j"
~~~

Ở ứng dụng thật, nên lấy cả URI, user, password và database từ biến môi trường/secret manager. YAML chỉ minh họa cách tổ chức; không lưu credential production trong source control.

### Quy tắc transaction ở tầng service

Trong Spring Data Neo4j, nên đánh dấu transaction đọc bằng ngữ nghĩa **read-only** khi phù hợp:

~~~java
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<Order> findByCustomer(String customerId) {
        return repository.findByCustomerId(customerId);
    }

    @Transactional
    public void updateStatus(String orderId, String status) {
        repository.updateStatus(orderId, status);
    }
}
~~~

Đây là **mã minh họa lớp service**; `OrderRepository` và entity `Order` phải được định nghĩa tương ứng trong ứng dụng. Cơ chế chính xác mà SDN/Spring transaction manager chuyển `readOnly` thành access mode và routing phải được **kiểm thử với phiên bản framework** đang chạy; không dùng annotation như bằng chứng duy nhất rằng query đã đến reader mong muốn.

**Đặc biệt:** nếu phương thức có transaction bên ngoài đã được tạo ở WRITE mode, việc gọi một repository read-only bên trong không nhất thiết đổi transaction hiện tại sang một reader. Ranh giới transaction của service quyết định nhiều hơn tên repository method.

### Dùng read-only không phải cấp quyền đọc

`@Transactional(readOnly = true)` là **tín hiệu quản lý transaction và tối ưu**, không thay RBAC ở Neo4j. Nếu application user có quyền WRITE, chỉ annotation không tự biến nó thành tài khoản read-only. Hãy dùng quyền Neo4j, credential và test ghi bị từ chối nếu cần tách role.

## 12. Khi failover xảy ra

### 12.1. Đổi leader và cập nhật routing

Khi leader ghi gặp sự cố, cluster cần xác định nơi tiếp nhận ghi mới theo cơ chế đồng thuận và trạng thái thành viên. Trong một khoảng thời gian, giao dịch có thể:

- Thất bại do kết nối cũ không còn hoạt động.
- Bị báo lỗi tạm thời về định tuyến, không có writer hoặc chuyển leader.
- Phải chờ routing table cập nhật và kết nối mới được tạo.
- Được managed transaction **retry** nếu loại lỗi và ngân sách thời gian cho phép.

**Không hứa rằng mọi request đều thành công không gián đoạn.** HA giảm rủi ro mất dịch vụ nhưng failover có thể tạo **độ trễ tăng** và một số request thất bại.

### 12.2. Phân biệt ba nhóm lỗi

| Nhóm | Ví dụ/biểu hiện | Hành động |
|---|---|---|
| Không kết nối/routing | `ServiceUnavailableException`, không có địa chỉ reader/writer phù hợp | Kiểm tra DNS, TLS, advertised address, routing table, trạng thái cluster |
| Session/transaction tạm thời | `SessionExpiredException`, deadlock hoặc leader switch | Managed transaction có thể retry; callback cần an toàn |
| Lỗi request không sửa bằng routing | Cypher syntax error, thiếu quyền, vi phạm constraint | Sửa câu lệnh, role hoặc dữ liệu; không retry vô hạn |

Với Neo4j Java Driver, có thể cấu hình:

~~~java
Config config = Config.builder()
        .withMaxTransactionRetryTime(30, TimeUnit.SECONDS)
        .build();
~~~

**Timeout retry không bảo đảm thành công** nếu cluster không có quorum, database chưa online hoặc đường mạng bị chặn lâu dài.

### 12.3. Kết quả commit không rõ và idempotency

Tình huống nguy hiểm:

~~~text
Ứng dụng gửi CREATE Order
         |
Server commit thành công
         |
Kết nối bị mất trước khi client nhận phản hồi
         |
Ứng dụng nghĩ thất bại và gửi lại CREATE Order
         |
Có thể tạo hai Order nếu thiếu khóa định danh
~~~

**Lỗi kết nối không chứng minh giao dịch chưa commit.** Khi thiết kế ghi trong cluster:

1. Tạo `requestId` hoặc khóa nghiệp vụ duy nhất từ **trước** lần thử đầu tiên.
2. Tạo uniqueness constraint cho khóa đó.
3. Ưu tiên `MERGE` theo khóa ổn định, tránh `CREATE` vô điều kiện khi cần chống ghi trùng.
4. Nếu cùng `requestId` được dùng lại với payload khác, phải **phát hiện xung đột** thay vì âm thầm coi là thành công.
5. Không thực hiện side effect ngoài DB trong callback retry; dùng outbox hoặc cơ chế nghiệp vụ có idempotency.

Khi giao dịch ghi có nhiều bước liên quan đến tiền hoặc hệ thống ngoài, **không coi một Neo4j transaction là exactly-once trên toàn hệ thống phân tán**.

## 13. Cấu hình cluster mà driver cần nhìn thấy

Để routing hoạt động, không chỉ ứng dụng có kết nối đến seed/router. Các member mà cluster công bố phải có thể được liên hệ theo mô hình mạng của client.

| Hạng mục | Kiểm tra gì? |
|---|---|
| URI ban đầu | Đúng `neo4j://` hoặc `neo4j+s://` cho routing, hostname chính xác |
| DNS | Tên bootstrap và địa chỉ server công bố giải được từ môi trường ứng dụng |
| TLS | Scheme đúng, CA/certificate hợp lệ, hostname phù hợp |
| Port Bolt | Có thể đi qua firewall, network policy, private endpoint/proxy |
| Advertised addresses | Không trả IP nội bộ pod/container không thể truy cập từ app |
| Database selection | Driver biết đúng database đích; không phụ thuộc mặc định ngầm |
| Quyền truy cập | Tài khoản có `ACCESS`, `MATCH`/`READ` hoặc `WRITE` theo nghiệp vụ |
| Routing/cluster health | Member, leader, quorum và database availability bình thường |
| Timeout/pool | Đủ cho workload, nhưng không che giấu lỗi hạ tầng |

### Trường hợp kết nối được seed nhưng query lỗi

Ví dụ ứng dụng đặt ngoài Kubernetes kết nối `neo4j+s://cluster.company.example` thành công, nhưng routing table chứa địa chỉ tên nội bộ `neo4j-0.neo4j.svc.cluster.local` mà máy ngoài cụm không resolve được. Truy vấn sau discovery có thể thất bại mặc dù kết nối đầu tiên thành công.

**Hướng điều tra:** kiểm tra topology của Neo4j, listen/advertised address, service routing của Kubernetes, DNS và TLS từ **vị trí thật của ứng dụng**. Không sửa bằng cách thêm retry vô hạn vào repository.

## 14. Quan sát phân phối tải: nên đo những gì?

Một dashboard tốt nhìn cả **ứng dụng** và **từng thành viên Neo4j**, với database/role rõ ràng.

| Chỉ số | Nguồn | Ý nghĩa |
|---|---|---|
| API latency p50/p95/p99 | Micrometer/OpenTelemetry | Sự chậm trễ người dùng nhận thấy |
| Read/write requests/s | Service instrumentation | Nhu cầu truy vấn theo loại |
| Query latency, query errors | Neo4j metrics/query log | Truy vấn thực thi ở server chậm/lỗi |
| Read transactions per server | Metrics/log theo member khi có | Trải tải thực tế |
| Write transactions / commit errors | Member/DB metrics | Leader hoặc đường ghi có quá tải không |
| Driver connection pool acquisition time | Instrumentation ứng dụng nếu có | Phát hiện nghẽn pool |
| Routing/connectivity errors | Exception class và code | Phát hiện địa chỉ công bố hoặc failover |
| Transaction retries/timeouts | Driver/app logs, tracing | Đánh giá tác động failover đến request |
| CPU, heap, page cache, GC | Mỗi member, theo khả năng triển khai | Đo tải thực của reader và writer |
| Replication/lag, cluster health | Công cụ quản trị/metrics hỗ trợ | Xác định khả năng đọc dữ liệu mới và HA |

**Không bịa các metric mà môi trường không xuất.** Một số gói Aura không cung cấp cùng mức quan sát host như self-managed Enterprise. Nếu metric chỉ có ở cluster edition khác, ghi rõ khoảng trống giám sát.

### Đo read balance đúng cách

Không so sánh mỗi `count(read queries)`. Hãy lấy **cùng khung thời gian**, cùng bộ query, so latency p95/p99 và mức dùng tài nguyên từng máy. Một reader có ít query nhưng query nặng hơn có thể đang chịu tải CPU cao hơn.

Để theo dõi định tuyến, có thể dùng **logging có kiểm soát của Java Driver** trong môi trường test, server query log và thông tin cluster (nếu phiên bản/edition cho phép) để đối chiếu đích kết nối. Không bật DEBUG toàn bộ driver hoặc log tham số nhạy cảm lâu dài trên production.

## 15. Kiểm thử tích hợp và failover có kiểm soát

Không cần tắt một máy Neo4j production để chứng minh driver có routing. Nên dùng **test cluster cô lập** hoặc môi trường staging được phép, gần topology production.

### 15.1. Ma trận kiểm thử

| Ca kiểm thử | Cách thực hiện | Kết quả mong đợi |
|---|---|---|
| Đọc với routing URI | Gọi `executeRead` nhiều request độc lập | Trả kết quả đúng; có cơ hội phân tải theo routing |
| Ghi với routing URI | Gọi `executeWrite` theo requestId duy nhất | Ghi đúng một bản ghi/quan hệ theo nghiệp vụ |
| Đọc sau ghi cùng Session | Ghi rồi đọc có bookmark ngầm của Session | Nhìn thấy dữ liệu vừa commit |
| Đọc sau ghi khác Session | Truyền bookmark/manager theo thiết kế | Bảo đảm thứ tự nhân quả trong điều kiện hỗ trợ |
| Một reader không sẵn sàng | Làm reader test ngừng hoạt động có kiểm soát | Driver có thể chuyển sang reader còn dùng được hoặc báo lỗi có giới hạn |
| Leader thay đổi | Kích hoạt failover theo runbook staging | Việc ghi phục hồi qua routing; đo error/latency trong giai đoạn chuyển |
| DNS/advertised address sai | Dùng cấu hình test cố ý sai | Phát hiện lỗi discovery/kết nối, không lầm thành lỗi query |
| Tải đọc tăng | Tăng số read request với dataset cố định | Đo throughput/latency từng member, không yêu cầu chia đều tuyệt đối |
| Connection pool cạn | Giới hạn pool trong staging và tăng concurrency | Thấy acquisition latency/timeout; kiểm tra giải pháp hợp lý |
| Ghi thử lại sau lỗi mạng | Mô phỏng kết nối mất ở ranh giới commit | Không tạo đơn trùng do `requestId`/constraint |

### 15.2. Kịch bản failover từng bước

1. Ghi nhận **topology/leader, phiên bản Neo4j và driver, database** trước khi thử.
2. Khởi động workload đọc/ghi **đại diện**, có request ID và trace/metric.
3. Chỉ trên staging, mô phỏng mất một reader rồi quan sát đường read và chất lượng kết quả.
4. Theo quy trình staging được phê duyệt, thử đổi leader hoặc sự cố node ghi có kiểm soát.
5. Quan sát lỗi tạm thời, retry budget, p95/p99, số request ghi thành công, dữ liệu trùng và khả năng read-after-write.
6. Khôi phục topology, kiểm tra database healthy, replication/lag, constraint và mọi transaction đã hoàn tất.
7. Ghi nhận **khoảng thời gian gián đoạn**, RTO quan sát được và các khác biệt so với SLO; không kết luận “zero downtime” chỉ vì workload cuối cùng chạy lại thành công.

**Khi kiểm thử transaction mất kết nối đúng thời điểm commit**, không được chỉ assert “exception được ném”. Cần đọc lại theo `requestId` và đối chiếu **trạng thái dữ liệu cuối cùng**.

### 15.3. Test đúng ngữ nghĩa trước khi đo hiệu năng

Với dữ liệu đồ thị, các đường `MATCH (c)-[:PLACED]->(o)` và phép tổng hợp quan hệ phải trả đúng kết quả. Nếu một query được viết lại để “phù hợp reader” nhưng làm mất relationship hoặc nhân số hàng, benchmark nhanh hơn **không có giá trị**.

## 16. Những nhầm lẫn thường gặp

| Nhầm lẫn | Điều đúng hơn | Cách sửa |
|---|---|---|
| `bolt://` tự load-balance cluster giống `neo4j://` | `bolt://` là direct; routing-aware scheme mới kích hoạt discovery phù hợp | Dùng URI do triển khai cluster/Aura cung cấp |
| `neo4j://` luôn kết nối đồng thời tất cả members | Driver tạo/lấy kết nối theo nhu cầu | Đọc metrics và pool behavior thật |
| `executeRead` luôn chạy trên secondary | Read được route theo tập reader được công bố, có thể gồm primary | Kiểm tra topology và chính sách routing |
| `executeWrite` gửi ghi đến mọi primary | Đường ghi phải theo thành viên phù hợp/leader hiện tại | Dựa vào routing và transaction semantics |
| Hai reader sẽ nhận đúng số query bằng nhau | Không có cam kết chia đều tuyệt đối | Đo theo query cost, latency và tài nguyên |
| Read sau write luôn thấy bản mới ở mọi Session | Replica có thể cần thời gian đồng bộ; bookmark là cơ chế causal consistency | Truyền bookmark khi cần |
| `SessionConfig.defaultAccessMode(READ)` làm mọi managed tx read-only | `executeRead`/`executeWrite` có access mode riêng | Chọn API theo nghiệp vụ |
| `@Transactional(readOnly=true)` là ranh giới bảo mật | Read-only là tín hiệu transaction, không thay RBAC | Thiết kế quyền Neo4j thực |
| Retry giải quyết mọi lỗi routing | DNS/TLS/quorum sai kéo dài không tự hết | Giám sát và sửa topology/network |
| Callback retry chỉ chạy một lần | Managed transaction có thể chạy lại callback | Không đưa side effect ngoài DB vào callback |
| Cluster có ba máy thì ghi nhanh gấp ba | Tải ghi chịu giới hạn consensus/leader/locks | Benchmark read/write riêng |
| Có HA nghĩa là không cần backup | HA không khôi phục xóa dữ liệu logic | Backup/restore và DR theo RPO/RTO |
| Tạo Driver mỗi request giúp cân bằng tải | Làm tăng overhead connect/discovery và mất pool | Tái sử dụng Driver, Session ngắn |

## 17. Bài tập thực hành

### Bài 1 — Chọn đúng URI

Một cluster Neo4j Enterprise có ba primary và hai secondary. Ứng dụng Java dùng `bolt://node-1:7687`; sau khi node-1 dừng, tất cả request thất bại dù cluster còn hoạt động. Lỗi thiết kế nằm ở đâu?

**Đáp án:** Ứng dụng dùng **direct URI** tới một node cụ thể. Cần endpoint routing-aware như `neo4j://`/`neo4j+s://` và đảm bảo routing addresses mà cluster công bố reachable từ ứng dụng. Không có URI nào thay thế được việc kiểm tra quorum, DNS/TLS và quyền truy cập.

### Bài 2 — Truy vấn đọc nhưng vẫn quá tải writer

Một repository dùng `session.run("MATCH ... RETURN ...")` với SessionConfig mặc định. Các truy vấn đều đọc, nhưng writer bị tải cao. Nêu cách sửa phía Java Driver.

**Đáp án:** Ưu tiên `session.executeRead(...)` để khai báo read transaction. Nếu cần implicit transaction, đặt `SessionConfig.withDefaultAccessMode(AccessMode.READ)`. Kiểm tra URI `neo4j://`, routing topology và query thực; không khẳng định nguyên nhân chỉ từ CPU writer.

### Bài 3 — Read-your-writes

Request A ghi một node Order trên writer và commit. Request B dùng Session khác, đọc trên reader, thỉnh thoảng không thấy Order mới. Nêu chiến lược khắc phục và giới hạn.

**Đáp án:** Truyền bookmark nhân quả từ A sang B hoặc dùng BookmarkManager phù hợp phạm vi nghiệp vụ. Driver sẽ dùng thông tin đó để yêu cầu read phản ánh ít nhất commit cần thiết. Điều này có thể tăng thời gian chờ; không có nghĩa mọi read trong cluster lập tức tuyến tính hóa toàn bộ dữ liệu.

### Bài 4 — Retry khi đổi leader

Trong lúc failover, `executeWrite` được thử lại. Developer đặt lệnh gọi thanh toán HTTP và `CREATE (:Order)` bên trong callback. Có thể xảy ra chuyện gì?

**Đáp án:** Callback có thể chạy lại, gây gọi thanh toán nhiều lần; nếu commit trước không rõ, có nguy cơ tạo nhiều Order. Cần tách side effect, dùng request ID duy nhất, uniqueness constraint, `MERGE` và outbox/idempotency phù hợp.

### Bài 5 — Cân bằng tải sai kỳ vọng

Hai reader nhận lần lượt 600 và 400 query trong một phút. Reader thứ hai có CPU 90%, reader đầu có CPU 40%. Có thể kết luận driver đã chọn reader “sai” không?

**Đáp án:** Không đủ căn cứ. Hai tập query có thể rất khác chi phí, dữ liệu/cache và mức concurrency; driver không cam kết chia đều số lượng query. Cần so workload, histogram latency, CPU, Rows/DB Hits và cấu hình routing.

### Bài 6 — Kết nối seed thành công nhưng query lỗi

Ứng dụng ở ngoài Kubernetes mở được kết nối tới router, nhưng sau discovery nhận endpoint dạng `neo4j-0.svc.cluster.local` và không thể truy cập. Cần kiểm tra gì trước khi tăng timeout?

**Đáp án:** Kiểm tra advertised address, DNS, TLS và cấu hình service/network policy giữa ứng dụng với từng member được routing table trả về. Đổi timeout không giải quyết địa chỉ không thể route.

### Bài 7 — Quyết định transaction boundary

Một service cần lấy số dư rồi trừ tiền, bảo đảm thao tác là nguyên tử. Có nên tách `executeRead` để lấy số dư trên reader rồi `executeWrite` để trừ tiền cho “cân bằng tải” không?

**Đáp án:** Không. Nếu nghiệp vụ cần atomic read-modify-write, đặt thao tác vào **một `executeWrite` transaction**, dùng điều kiện và đồng bộ thích hợp, chống retry trùng và kiểm tra constraint. Tách thành hai transaction sẽ mở cửa cho race condition.

## 18. Tài liệu chính thức

- [Neo4j Java Driver Manual — Connect to the database](https://neo4j.com/docs/java-manual/current/connect/)
- [Neo4j Java Driver Manual — Advanced connection information](https://neo4j.com/docs/java-manual/current/connect-advanced/)
- [Neo4j Java Driver Manual — Transaction management](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual — Bookmarks và causal consistency](https://neo4j.com/docs/java-manual/current/bookmarks/)
- [Neo4j Operations Manual — Clustering](https://neo4j.com/docs/operations-manual/current/clustering/)
- [Neo4j Operations Manual — Routing in a cluster](https://neo4j.com/docs/operations-manual/current/clustering/)
- [Neo4j Operations Manual — Monitoring](https://neo4j.com/docs/operations-manual/current/monitoring/)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)

Các trang `current` sẽ thay đổi theo release. Khi làm việc với Neo4j 5.x, Aura hoặc phiên bản mới hơn, luôn kiểm chứng **scheme URI, API driver, access mode, routing table, bookmark, quyền và topology** trên cấu hình chạy thật thay vì mặc định mọi hệ thống phân phối read/write giống nhau.

## 19. Ghi nhớ

- **Routing URI `neo4j://`/`neo4j+s://` giúp driver khám phá nơi đọc/ghi**; `bolt://` chủ yếu là direct connection, không tự cung cấp cùng cơ chế routing cluster.
- **`executeRead` và `executeWrite` mô tả mục đích giao dịch**, để driver chọn đường phù hợp; không thay thế RBAC hoặc việc tối ưu Cypher.
- **Load balancing không cam kết chia đều request** và cũng không làm một truy vấn tốn nhiều DB Hits trở nên rẻ hơn.
- **Bookmark hỗ trợ causal consistency**, đặc biệt khi read được gửi tới replica sau một commit; cross-session cần truyền bookmark/manager theo phạm vi nghiệp vụ.
- **Một Driver dùng lâu dài, nhiều Session ngắn và connection pool được cấu hình theo đo đạc** là mô hình Java phổ biến.
- **Failover vẫn có lỗi ngắn và độ trễ**, nên cần managed transaction retry có giới hạn, ghi idempotent và bài kiểm thử read-after-write/failover.
- **Quan sát routing bằng metrics và log thực tế**, kiểm tra đường mạng của mọi địa chỉ công bố, đồng thời đo SLO cả ứng dụng lẫn database.
