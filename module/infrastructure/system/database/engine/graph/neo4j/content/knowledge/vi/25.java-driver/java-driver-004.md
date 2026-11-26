# Giao dịch được trình điều khiển quản lý cho thao tác đọc và ghi trong Neo4j Java Driver

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **managed transaction** là gì và phân biệt với **implicit transaction** hoặc **explicit transaction** trong Neo4j Java Driver.
- Sử dụng `Session.executeRead(...)` và `Session.executeWrite(...)` để thực hiện một hoặc nhiều câu Cypher trong đúng ranh giới giao dịch.
- Quản lý vòng đời của `Driver`, `Session`, callback và kết quả truy vấn; chọn chế độ READ/WRITE để định tuyến thích hợp.
- Hiểu điều kiện commit, rollback, lỗi tạm thời và cơ chế **tự động retry** của managed transaction.
- Thiết kế callback không phát sinh tác dụng phụ ngoài Neo4j, xử lý yêu cầu lặp và bảo vệ dữ liệu bằng khóa ổn định/constraint.
- Viết kiểm thử xác nhận tính nguyên tử, xử lý lỗi, độ an toàn khi dùng nhiều luồng và tính đúng đắn của thao tác đọc/ghi.

Đây là bài trong chương **Java Driver** của module **DATABASE_ENGINE_GRAPH_NEO4J**. Ứng dụng Java dùng Neo4j để mô hình hóa **property graph**, truy vấn các node, relationship và đường đi bằng **Cypher**. Khi một nghiệp vụ phải sửa nhiều phần tử của đồ thị, **transaction** giúp những thay đổi được commit hoặc rollback cùng nhau. Managed transaction là cách Java Driver điều phối ranh giới đó và hỗ trợ xử lý lại một số lỗi tạm thời.

> Ví dụ trong bài dùng API `executeRead` / `executeWrite` của Neo4j Java Driver 5.x và các phiên bản mới hơn có API tương ứng. Tài liệu hay mã nguồn cũ có thể dùng `readTransaction` / `writeTransaction`; không tự trộn API giữa các phiên bản. Hãy kiểm tra phiên bản driver, Neo4j DBMS và hướng dẫn chính thức đang áp dụng trước khi đưa ví dụ vào dự án.

## 1. Vì sao cần một giao dịch được quản lý?

Giả sử một hệ thống bán hàng có đồ thị:

~~~mermaid
flowchart LR
    C["Customer<br/>customerId"] -->|PLACED| O["Order<br/>orderId, totalCents"]
    O -->|CONTAINS| P["Product<br/>sku"]
~~~

Một yêu cầu tạo đơn có thể gồm:

1. Kiểm tra khách hàng `Customer` đã tồn tại.
2. Tạo hoặc nhận diện `Order` có khóa `orderId`.
3. Gắn relationship `PLACED` từ khách hàng đến đơn hàng.
4. Trả về ID đơn sau khi **toàn bộ thao tác ghi** đã hoàn tất.

Nếu câu lệnh tạo đơn đã commit riêng nhưng câu lệnh tạo relationship thất bại, đồ thị có thể chứa một đơn chưa gắn khách hàng. Managed transaction cho phép **nhiều câu Cypher nằm trong một đơn vị commit/rollback**; khi callback thất bại, các thay đổi chưa commit của transaction đó bị hủy.

Trong Java Driver có ba hình thức thường gặp:

| Cách gọi | Ai quyết định commit/rollback? | Đặc điểm |
| --- | --- | --- |
| `session.run(cypher, params)` | Driver chạy **implicit transaction** cho câu lệnh | Gọn cho lệnh đơn; nhiều lần gọi `session.run` không tự thành một transaction chung |
| `session.executeRead(tx -> ...)` / `executeWrite(tx -> ...)` | **Driver quản lý** transaction quanh callback | Chọn hướng đọc/ghi, commit khi thành công, rollback khi lỗi, có thể retry lỗi phù hợp |
| `session.beginTransaction()` | **Ứng dụng quản lý tường minh** `commit()` / `rollback()` | Linh hoạt, nhưng tự xử lý vòng đời và chính sách retry |

**Managed** không có nghĩa là Neo4j tự sửa mọi lỗi nghiệp vụ. Driver quản lý giao dịch và một số lỗi kỹ thuật; ứng dụng vẫn phải tự quyết định **khóa định danh, tính đúng đắn, cách xử lý trùng yêu cầu và thứ tự cập nhật**.

## 2. Vòng đời của managed transaction

Các phương thức có dạng tổng quát:

~~~java
T result = session.executeRead(tx -> {
    // Một hoặc nhiều câu Cypher chỉ đọc.
    return ...;
});

T result = session.executeWrite(tx -> {
    // Một hoặc nhiều câu Cypher có ghi.
    return ...;
});
~~~

Biến `tx` là **ngữ cảnh transaction do driver cung cấp**. Ứng dụng chạy `tx.run(...)` bên trong callback, lấy kết quả cần dùng rồi trả về một giá trị Java. Không gọi `commit()` hay `rollback()` trực tiếp trên ngữ cảnh này.

~~~mermaid
flowchart TD
    A["session.executeRead / executeWrite"] --> B["Driver mở transaction phù hợp"]
    B --> C["Gọi callback với tx"]
    C --> D{"Callback hoàn tất?"}
    D -->|Trả kết quả| E["Driver COMMIT"]
    D -->|Ném lỗi| F["Driver ROLLBACK"]
    E --> G{"Commit thành công?"}
    G -->|Có| H["Trả kết quả cho ứng dụng"]
    G -->|Lỗi có thể retry| R["Rollback/đánh giá retry"]
    F --> R
    R --> S{"Driver được phép retry?"}
    S -->|Có| B
    S -->|Không| X["Ném exception cho ứng dụng"]
    G -->|Lỗi không retry| X
~~~

Đây là sơ đồ khái niệm. **Không phải mọi lỗi đều được retry**; lỗi xác thực, vi phạm constraint, lỗi Cypher hay lỗi do nghiệp vụ chủ động phát sinh thường đòi hỏi ứng dụng xử lý. Driver chỉ retry những lỗi mà chính sách của nó phân loại là có thể thử lại trong thời hạn cấu hình.

### Điều gì xảy ra với kết quả callback?

- Callback chạy thành công và commit hoàn tất: `executeRead` / `executeWrite` trả giá trị callback về cho caller.
- Callback ném exception hoặc transaction không thể commit: caller nhận lỗi; transaction chưa commit được rollback theo cơ chế driver/server.
- Với lỗi retryable, **toàn bộ callback có thể chạy nhiều lần**, mỗi lần trong một transaction mới.
- Một câu Cypher chạy thành công **trong callback** chưa có nghĩa transaction đã commit. Chỉ nên thông báo nghiệp vụ thành công sau khi lời gọi managed transaction kết thúc thành công.

## 3. Chuẩn bị Driver và Session đúng vòng đời

### 3.1. Thêm thư viện Java Driver

Với Maven, khai báo dependency (thay `<compatible-version>` bằng phiên bản đã chọn, hoặc quản lý version qua BOM/phần cấu hình build):

~~~xml
<dependency>
    <groupId>org.neo4j.driver</groupId>
    <artifactId>neo4j-java-driver</artifactId>
    <version>COMPATIBLE_DRIVER_VERSION</version>
</dependency>
~~~

`COMPATIBLE_DRIVER_VERSION` là **placeholder**, không phải số phiên bản thật để Maven tải được. Với dự án Spring Data Neo4j hoặc Spring Boot, cần lưu ý dependency management của framework thay vì tự ép một driver version không tương thích.

### 3.2. Tạo Driver một lần, Session cho mỗi đơn vị công việc

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class DriverLifecycle {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String user = System.getenv("NEO4J_USERNAME");
        String password = System.getenv("NEO4J_PASSWORD");

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(user, password))) {
            driver.verifyConnectivity();

            try (Session session =
                    driver.session(SessionConfig.forDatabase("neo4j"))) {
                String greeting = session.executeRead(tx ->
                        tx.run("RETURN 'Neo4j ready' AS message")
                          .single()
                          .get("message")
                          .asString());
                System.out.println(greeting);
            }
        }
    }
}
~~~

Ứng dụng cần cấu hình ba biến môi trường trên trước khi chạy. Trong môi trường thật, dùng URI, xác thực và bảo mật kết nối phù hợp; không hard-code mật khẩu vào repository.

**Vòng đời nên nhớ:**

- **`Driver`:** tạo một lần và **dùng chung** trong ứng dụng; Driver có khả năng quản lý pool và an toàn khi nhiều luồng cùng dùng. Đóng khi ứng dụng kết thúc.
- **`Session`:** nhẹ và nên tạo theo request/đơn vị công việc; **không dùng chung một Session giữa các luồng đồng thời**. Đóng bằng `try-with-resources`.
- **`TransactionContext` (`tx`):** chỉ sử dụng bên trong callback; không giữ lại hoặc chuyển cho luồng khác.
- **`Result`:** là luồng kết quả gắn với transaction đang mở; đọc/`consume()` kết quả cần thiết **trước khi callback kết thúc**.

Khi ứng dụng dùng nhiều database, chỉ định rõ tên bằng `SessionConfig.forDatabase(...)` để tránh lượt yêu cầu xác định database mặc định và nhầm đích. Trong cluster, URI dạng `neo4j://` hỗ trợ định tuyến thông qua routing driver; `bolt://` thường nhắm trực tiếp vào một địa chỉ server. Chọn URI theo topology và yêu cầu vận hành thực tế.

## 4. Đọc dữ liệu với executeRead

### 4.1. Ví dụ đọc danh sách đơn hàng

Đọc các đơn từ `Customer` đã biết, không ghi thuộc tính:

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId,
       o.totalCents AS totalCents,
       o.status AS status
ORDER BY o.orderId
LIMIT 20;
~~~

Java Driver:

~~~java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class OrderQueries {
    public record OrderSummary(
            String orderId, long totalCents, String status) {}

    public static List<OrderSummary> recentOrders(
            Driver driver, String customerId) {
        try (Session session =
                driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(tx ->
                    tx.run("""
                        MATCH (c:Customer {customerId: $customerId})
                              -[:PLACED]->(o:Order)
                        RETURN o.orderId AS orderId,
                               o.totalCents AS totalCents,
                               o.status AS status
                        ORDER BY o.orderId
                        LIMIT 20
                        """, Map.of("customerId", customerId))
                      .list(row -> new OrderSummary(
                              row.get("orderId").asString(),
                              row.get("totalCents").asLong(),
                              row.get("status").asString())));
        }
    }
}
~~~

Ở ví dụ này:

1. Mỗi lần gọi mở một `Session` riêng cho database `neo4j`.
2. `executeRead` tạo một **managed read transaction** và cung cấp `tx`.
3. `tx.run(query, parameters)` truyền tham số an toàn, tránh nối chuỗi đầu vào người dùng vào mã Cypher.
4. `.list(mapper)` đọc hết kết quả và ánh xạ thành Java record **khi transaction còn sống**.
5. Khi callback và commit kết thúc thành công, danh sách Java không còn phụ thuộc `Result` hay Session.

**Tại sao dùng `list(...)`?** Một `Result` trả về trực tiếp từ callback có thể không còn truy cập được sau khi transaction đóng. Với kết quả rất lớn, không nên nạp mọi hàng vào `List` vì sẽ tốn heap của Java; hãy thiết kế phân trang hoặc xử lý có giới hạn phù hợp với API.

### 4.2. Hai câu đọc trong cùng transaction

Nếu cần xác nhận khách hàng tồn tại rồi đọc đơn:

~~~java
return session.executeRead(tx -> {
    var customer = tx.run("""
            MATCH (c:Customer {customerId: $customerId})
            RETURN c.customerId AS id
            """, Map.of("customerId", customerId)).single();

    var orders = tx.run("""
            MATCH (:Customer {customerId: $customerId})
                  -[:PLACED]->(o:Order)
            RETURN o.orderId AS id
            ORDER BY id
            """, Map.of("customerId", customerId))
            .list(row -> row.get("id").asString());

    return Map.of(
            "customerId", customer.get("id").asString(),
            "orderIds", orders);
});
~~~

Hai câu thuộc **cùng transaction**, nhưng **read committed** (mức cô lập mặc định của Neo4j) **không bảo đảm snapshot cố định** giữa các lần đọc. Một transaction khác có thể commit dữ liệu mới ở giữa hai truy vấn. Nếu nghiệp vụ cần tính nhất quán nghiêm ngặt hơn cho nhiều đối tượng, cần phân tích quy tắc đồng thời và chiến lược khóa/phiên bản phù hợp.

## 5. Ghi dữ liệu với executeWrite

### 5.1. Tạo constraint cho khóa nghiệp vụ

Để tránh hai node có cùng định danh được commit, đặt **uniqueness constraint** trước khi nhiều luồng cùng ghi:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;
~~~

Ràng buộc trên `Order.orderId` giúp nhận diện cùng một đơn khi retry. Dù vậy, nó **không tự kiểm tra toàn bộ bất biến nghiệp vụ** như chủ sở hữu đơn hoặc tổng tiền.

### 5.2. Ví dụ nhiều câu ghi trong một callback

Mục tiêu: tạo `Order` với ID ổn định, xác minh thông tin khi ID đã tồn tại và gắn node với `Customer`. Nếu không có customer, toàn bộ transaction phải rollback.

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class OrderCommands {
    public static String placeOrder(
            Driver driver, String customerId,
            String orderId, long totalCents) {
        if (customerId == null || customerId.isBlank()
                || orderId == null || orderId.isBlank()
                || totalCents < 0) {
            throw new IllegalArgumentException("Invalid order input");
        }

        Map<String, Object> params = Map.of(
                "customerId", customerId,
                "orderId", orderId,
                "totalCents", totalCents);

        try (Session session =
                driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeWrite(tx -> {
                // Lệnh 1: nhận diện hoặc tạo một Order duy nhất.
                var order = tx.run("""
                    MERGE (o:Order {orderId: $orderId})
                    ON CREATE SET
                        o.customerId = $customerId,
                        o.totalCents = $totalCents,
                        o.status = 'CREATED',
                        o.createdAt = datetime()
                    RETURN o.customerId AS ownerId,
                           o.totalCents AS storedTotal
                    """, params).single();

                // Cùng ID nhưng dữ liệu khác phải là lỗi nghiệp vụ.
                if (!customerId.equals(
                        order.get("ownerId").asString())
                        || totalCents !=
                        order.get("storedTotal").asLong()) {
                    throw new IllegalStateException(
                            "Order ID reused with different data");
                }

                // Lệnh 2: yêu cầu Customer tồn tại, tạo liên kết.
                return tx.run("""
                    MATCH (c:Customer {customerId: $customerId})
                    MATCH (o:Order {orderId: $orderId})
                    MERGE (c)-[:PLACED]->(o)
                    RETURN o.orderId AS id
                    """, params).single().get("id").asString();
            });
        }
    }
}
~~~

Giải thích kết quả:

- Nếu `Customer` tồn tại và `Order` chưa có: tạo node + relationship trong **cùng transaction**, rồi commit.
- Nếu cùng yêu cầu được gọi lại sau lần đã commit: `MERGE` tìm đơn hiện có, kiểm tra chủ sở hữu/tổng tiền và tìm lại liên kết. Đây là cách hướng đến **lũy đẳng theo business ID**.
- Nếu `Customer` không tồn tại: câu thứ hai trả 0 hàng, `single()` phát sinh lỗi; driver rollback cả node `Order` vừa tạo trong transaction đó.
- Nếu `orderId` đã tồn tại với dữ liệu khác: callback ném exception; không commit thay đổi mới.
- Nếu database báo xung đột constraint hoặc lỗi kỹ thuật: managed transaction xử lý rollback/retry theo loại lỗi; ứng dụng vẫn cần phân loại lỗi khi nhận kết quả.

**Giới hạn ghi đồng thời:** `MERGE` của relationship giữa hai node không tự là **uniqueness constraint** cho cặp đầu mút ở mức database. Nếu nhiều transaction chạy đua và nghiệp vụ bắt buộc chỉ có một relationship, cần thêm cơ chế bảo vệ theo định danh relationship ổn định/constraint phù hợp, khóa hoặc tuần tự hóa theo khóa nghiệp vụ. Đặc biệt, **đừng giả định `MERGE` luôn loại bỏ mọi cạnh trùng trong mọi cuộc đua**.

### 5.3. Vì sao ví dụ dùng hai câu?

Ta cố ý tách upsert node và tạo relationship thành **hai lần `tx.run`** để thấy tính nguyên tử của callback. Nếu gọi hai lần `session.run` độc lập, lệnh tạo node có thể commit trước khi lệnh tạo relationship thất bại. Khi dùng `executeWrite`, driver chỉ commit toàn bộ khi callback kết thúc thành công.

Một transaction **không thay thế validation**: hãy kiểm tra định danh, dữ liệu đơn, quyền người dùng, hạn mức và các bất biến nghiệp vụ trước hoặc trong transaction theo mức độ cần thiết.

## 6. Commit, rollback và exception: hiểu chính xác

| Tình huống | Neo4j/Driver xử lý | Ứng dụng cần làm |
| --- | --- | --- |
| Callback trả kết quả bình thường và commit thành công | Transaction được commit; giá trị trả về caller | Có thể trả response thành công |
| Callback ném lỗi nghiệp vụ | Transaction chưa commit bị rollback | Ánh xạ lỗi thành response thích hợp |
| Cypher lỗi cú pháp hoặc dữ liệu không hợp lệ | Transaction thất bại; thông thường không tự retry | Sửa truy vấn hoặc từ chối input |
| Vi phạm uniqueness constraint | Ghi bị từ chối; transaction không commit | Kiểm tra ID trùng, xung đột nghiệp vụ |
| Deadlock hoặc lỗi transient được driver nhận diện | Driver có thể retry **toàn callback** | Callback phải có khả năng chạy lại an toàn |
| Kết nối bị ngắt gần lúc commit | Client có thể không xác định được trạng thái commit | Đọc lại theo business ID, tránh tạo lặp |

**Không được giả định:** “Callback đã chạy qua lệnh cuối = commit chắc chắn thành công”. Transaction có thể thất bại khi commit, vì thế chỉ hành động theo thành công sau khi phương thức `executeWrite` hoàn tất.

Khi exception đi ra ngoài callback, **không nên bắt lỗi rồi trả một giá trị bình thường chỉ để driver commit**, trừ khi ứng dụng có chủ đích chấp nhận các thao tác đã thành công trước đó. Nếu nghiệp vụ phải rollback toàn bộ, hãy **ném lỗi ra ngoài callback**.

### Ví dụ điều kiện khiến transaction rollback

~~~java
session.executeWrite(tx -> {
    tx.run("""
        CREATE (a:AuditMarker {markerId: $id})
        """, Map.of("id", "MARK-001")).consume();

    // Khi phát hiện một điều kiện nghiệp vụ không hợp lệ:
    throw new IllegalStateException("Business validation failed");
});
~~~

Sau exception, `AuditMarker` được tạo bởi transaction này **không được commit**. Nếu một node cùng ID đã tồn tại từ transaction khác, rollback của transaction mới **không** xóa dữ liệu cũ đó.

## 7. Automatic retry: lợi ích và bẫy lớn nhất

Trong hệ thống thực, có thể gặp transaction bị deadlock, server tạm ngắt hoặc lỗi nhất thời. Managed transaction cho phép driver **thử chạy lại callback** đối với các lỗi mà driver nhận định là có thể retry, trong giới hạn chính sách/thời gian đã cấu hình.

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant Driver as Neo4j Java Driver
    participant DB as Neo4j
    App->>Driver: executeWrite(callback)
    Driver->>DB: Bắt đầu transaction #1
    DB-->>Driver: Lỗi tạm thời có thể retry
    Driver->>DB: Bắt đầu transaction #2
    Driver->>DB: Gọi lại toàn callback
    DB-->>Driver: COMMIT thành công
    Driver-->>App: Trả kết quả
~~~

### 7.1. Callback có thể được gọi lại

Sai lầm phổ biến:

~~~java
session.executeWrite(tx -> {
    String orderId = java.util.UUID.randomUUID().toString();
    tx.run(
        "CREATE (o:Order {orderId: $id})",
        Map.of("id", orderId)
    ).consume();
    paymentGateway.charge(orderId); // Tác dụng phụ ngoài Neo4j!
    return orderId;
});
~~~

Khi callback chạy lại, `orderId` có thể **đổi**, còn lệnh thu tiền phía cổng thanh toán **không thể rollback cùng Neo4j**. Việc gọi cổng thanh toán bên trong transaction làm tăng rủi ro thu tiền nhiều lần hoặc trạng thái hai hệ thống không khớp.

Một thiết kế an toàn hơn:

1. Nhận hoặc tạo **requestId/orderId ổn định trước khi vào callback**, dùng lại khi retry.
2. Trong callback, chỉ truy cập Neo4j và validate dữ liệu cần ghi; có constraint và upsert thích hợp.
3. Ghi một **event/outbox record** có ID duy nhất **trong cùng transaction** nếu cần xử lý sau commit.
4. Worker độc lập đọc outbox, gọi dịch vụ ngoài bằng khóa idempotency, xác nhận trạng thái và xử lý retry của riêng nó.

Với nhu cầu gửi email, Kafka hoặc gọi hệ thống khác sau commit, cần cơ chế đáng tin cậy như **transactional outbox** hoặc thiết kế bù trừ theo nghiệp vụ; chỉ đặt mã ngoài callback **sau** `executeWrite` cũng chưa tự đảm bảo giao hàng nếu tiến trình crash giữa commit và gửi.

### 7.2. Retry của Driver khác retry của request

Hai tầng retry có thể cùng xuất hiện:

- **Driver retry:** một lời gọi `executeWrite` thử callback lại do lỗi tạm thời được nhận diện.
- **Application/HTTP retry:** client gửi lại **cả yêu cầu** sau timeout, có thể sau khi giao dịch trước **đã commit**.

Vì vậy, ngay cả một callback không làm side effect bên ngoài vẫn cần **tính lũy đẳng của nghiệp vụ** nếu khách hàng có thể gửi lại request. Constraint và `MERGE` theo business ID hữu ích nhưng phải kiểm tra nội dung khi ID trùng; không được coi mọi request trùng ID đều hợp lệ.

### 7.3. Thời gian retry

Driver có giới hạn thời gian retry được cấu hình (ví dụ qua cấu hình transaction retry của driver). Giới hạn này cần phù hợp **HTTP timeout**, số lần gọi ngoại vi và yêu cầu SLO. Tăng retry vô hạn không giải quyết được schema lỗi, query sai hoặc sự cố kéo dài.

Ghi log mã lỗi và số lần retry bằng thông tin có sẵn từ driver/hệ thống quan sát, tránh đưa ID khách hàng hay tham số nhạy cảm trực tiếp vào nhãn metric. Khi một lỗi không được driver retry, để lỗi đi ra application và thực hiện backoff/đọc lại có chủ đích.

## 8. executeRead và executeWrite: chọn theo ý định

| Nhu cầu | API đề nghị | Ghi chú |
| --- | --- | --- |
| Đọc node theo `customerId` | `executeRead` | Có thể được định tuyến tới thành viên đọc |
| Duyệt quan hệ hoặc tìm đường đi chỉ đọc | `executeRead` | Dùng index/giới hạn độ sâu để kiểm soát chi phí |
| `CREATE`, `MERGE`, `SET`, `DELETE` | `executeWrite` | Dùng transaction ghi |
| Chạy nhiều câu ghi phụ thuộc nhau | `executeWrite` | Bao toàn bộ bất biến cần commit chung |
| Đọc, xác minh rồi ghi | `executeWrite` | Đọc và ghi trong cùng transaction ghi; cân nhắc cạnh tranh dữ liệu |
| Xuất dữ liệu lớn theo các batch riêng | Thiết kế nhiều transaction có kiểm soát | Không giả định tất cả batch là một transaction nguyên tử |

**`executeRead` không phải nơi để ghi.** Nó chỉ định ngữ cảnh READ và giúp driver chọn đường định tuyến phù hợp; khi gọi lệnh ghi trong read transaction, server có thể từ chối. **`executeWrite`** có thể vừa đọc vừa ghi.

### Routing trong cluster

Khi kết nối bằng URI định tuyến `neo4j://`, driver có thể dùng routing table để gửi transaction READ/WRITE đến thành viên thích hợp. Tuy nhiên:

- `executeRead` **không tự có nghĩa** phải chạy trên một follower cụ thể.
- Session/transaction **không được tùy tiện chia sẻ giữa các luồng** khi chạy đồng thời.
- Sau một write, read khác ở session mới cần bảo đảm **causal consistency** nếu nghiệp vụ yêu cầu thấy chính dữ liệu vừa commit. Neo4j Java Driver hỗ trợ **bookmark** và `BookmarkManager` để liên kết các transaction phụ thuộc nhau.
- **Bookmark** quản lý thứ tự nhân quả, không tự nâng read committed thành snapshot isolation/serializable.

Trong ứng dụng đơn giản dùng session phù hợp, driver hỗ trợ theo dõi bookmark trong session; khi chuyển giữa session/instance, cần thiết kế cách chia sẻ bookmark hoặc BookmarkManager theo API và version đang dùng.

## 9. Xử lý kết quả, thời gian chờ và tài nguyên

### 9.1. Consume kết quả bên trong callback

Sai về vòng đời:

~~~java
var result = session.executeRead(tx ->
        tx.run("MATCH (c:Customer) RETURN c"));

// Result có thể đã mất transaction nguồn tại đây.
~~~

Đúng khi kết quả nhỏ:

~~~java
var customerIds = session.executeRead(tx ->
        tx.run("""
            MATCH (c:Customer)
            WHERE c.customerId IS NOT NULL
            RETURN c.customerId AS id
            LIMIT 100
            """).list(row -> row.get("id").asString()));
~~~

Với lệnh ghi không cần trả danh sách, hãy dùng `consume()` bên trong callback để hoàn tất việc xử lý result:

~~~java
session.executeWrite(tx -> {
    tx.run("""
        MATCH (c:Customer {customerId: $id})
        SET c.lastSeenByJob = $jobName
        """, Map.of("id", "C-101", "jobName", "sync-01"))
      .consume();
    return null;
});
~~~

**Lưu ý:** `consume()` hoàn tất kết quả của câu truy vấn, **không đồng nghĩa commit transaction**. Driver vẫn chỉ commit sau khi callback hoàn tất thành công.

### 9.2. Kết quả lớn và bộ nhớ

`.list(...)` tiện lợi nhưng đưa toàn bộ result vào heap Java. Đối với kết quả lớn:

- Chọn lọc bằng `WHERE` và dùng `LIMIT`/phân trang với khóa ổn định.
- Trả đúng thuộc tính cần thiết, không trả toàn bộ node/relationship khi chỉ cần ID.
- Xử lý row trong khi transaction còn mở, nhưng **không giữ transaction lâu** để chờ network, message broker hoặc công việc bên ngoài.
- Với batch ghi, dùng `UNWIND $rows AS row ...` và chia thành các transaction có kích thước được kiểm soát; mỗi batch có chiến lược retry/deduplication riêng.

Một transaction quá lâu có thể giữ tài nguyên/khóa và tăng tranh chấp với workload khác. Thiết kế số hàng, thời gian và timeout theo dữ liệu/tải thực tế, không chỉ theo một ví dụ ít bản ghi.

### 9.3. Timeout và metadata transaction

Neo4j Java Driver có thể cấu hình **transaction timeout** và metadata để hỗ trợ quan sát, tùy API phiên bản:

~~~java
import java.time.Duration;
import java.util.Map;
import org.neo4j.driver.TransactionConfig;

var config = TransactionConfig.builder()
        .withTimeout(Duration.ofSeconds(5))
        .withMetadata(Map.of("operation", "read-customer-orders"))
        .build();

var orders = session.executeRead(tx ->
        tx.run("""
            MATCH (c:Customer {customerId: $customerId})
                  -[:PLACED]->(o:Order)
            RETURN o.orderId AS id
            LIMIT 20
            """, Map.of("customerId", customerId))
          .list(row -> row.get("id").asString()), config);
~~~

Đoạn mã giả sử `session` và `customerId` đã được khai báo. **Transaction timeout**, timeout lấy connection, network timeout và giới hạn thời gian của HTTP endpoint là những lớp khác nhau; cần cấu hình đồng bộ để tránh HTTP đã timeout nhưng server còn tiếp tục công việc lâu. Metadata nên chứa nhãn nghiệp vụ ổn định, không chứa bí mật hoặc dữ liệu cá nhân không cần thiết.

## 10. Managed, explicit và implicit transaction trong một tình huống

Giả sử nghiệp vụ cập nhật hạng khách hàng và tạo lịch sử thay đổi:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
SET c.tier = $tier
CREATE (a:TierAudit {auditId: $auditId, tier: $tier})
CREATE (c)-[:HAS_TIER_AUDIT]->(a)
RETURN c.customerId AS id;
~~~

Một câu lệnh như trên đã có tính nguyên tử trong transaction của **chính câu lệnh**. Nhưng khi nghiệp vụ phức tạp hơn, cần nhiều lần `tx.run` và quyết định trong Java, lựa chọn sẽ khác.

| Kiểu giao dịch | Ưu điểm | Hạn chế/cẩn trọng |
| --- | --- | --- |
| **Implicit `session.run`** | Gọn cho một câu Cypher độc lập | Các lần `session.run` không mặc định chung commit; hoàn tất phụ thuộc việc consume result |
| **Managed `executeWrite`** | Có ranh giới rõ ràng, điều phối commit/rollback và retry | Callback có thể chạy lại; phải cẩn trọng với side effect và result lifecycle |
| **Explicit `beginTransaction`** | Chủ động gọi `commit`, `rollback` | Tự quản lý lỗi, resource và retry; dễ quên rollback/đóng transaction |

Ví dụ explicit để đối chiếu:

~~~java
try (Session session = driver.session();
     var tx = session.beginTransaction()) {
    tx.run("""
        MATCH (c:Customer {customerId: $id})
        SET c.tier = $tier
        """, Map.of("id", "C-101", "tier", "GOLD"))
      .consume();

    // Ứng dụng kiểm tra các điều kiện khác.
    tx.commit();
}
~~~

Khi transaction tường minh bị đóng mà chưa commit, các ghi chưa commit được rollback. Explicit transaction không tự cung cấp cơ chế retry callback tương tự `executeWrite`. Nếu nghiệp vụ không có nhu cầu điều phối riêng, managed transaction thường là lựa chọn thuận tiện.

## 11. Quan hệ với Spring Data Neo4j

Trong ứng dụng Spring Data Neo4j, tầng service thường dùng **`@Transactional`** cùng một `Neo4jTransactionManager` được cấu hình đúng để bao các thao tác repository:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public CustomerView findCustomer(String id) {
        var customer = repository.findById(id).orElseThrow();
        return new CustomerView(customer.getCustomerId(),
                                customer.getDisplayName());
    }
}
~~~

Đoạn trên là **khung minh họa**: `CustomerRepository`, `CustomerView` và entity phải được định nghĩa trong dự án. Chỉ dùng `@Transactional` khi lời gọi đi qua cơ chế transaction proxy thích hợp của Spring; tự gọi phương thức khác trong cùng bean có thể không kích hoạt proxy như mong đợi.

**Không đồng nhất**:

- `@Transactional` là cơ chế **quản lý giao dịch của Spring** tại tầng ứng dụng.
- `executeRead` / `executeWrite` là cơ chế **managed transaction của Java Driver**.

Trong cùng một ứng dụng, tránh tự tạo thêm Session/managed transaction độc lập giữa một chuỗi thao tác repository mà bạn kỳ vọng nằm trong **transaction Spring duy nhất**. Hãy nhất quán về transaction manager và điểm truy cập dữ liệu. Nếu cần gọi trực tiếp các procedure GDS, CDC hoặc Cypher đặc thù, kiểm tra cách `Neo4jClient`/Driver tham gia vào ranh giới giao dịch đang dùng.

## 12. Kiểm thử hành vi thay vì chỉ kiểm tra cú pháp

Chuẩn bị database thử nghiệm có `Customer` và các constraint từ phần 5. Những phép thử dưới đây có thể chạy bằng integration test với Neo4j thật hoặc môi trường Neo4j Testcontainers tương thích.

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| `executeRead` đọc khách hàng tồn tại | Trả đúng dữ liệu; không tạo/sửa node |
| Callback `executeRead` có 2 truy vấn | Cả hai chạy trong một transaction đọc, kết quả đã materialize trước khi callback trả |
| `executeWrite` tạo Order + relationship | Cả hai xuất hiện sau commit |
| Lỗi sau khi tạo Order, trước khi tạo relationship | Không còn phần Order mới chưa commit do transaction lỗi |
| Customer không tồn tại, `single()` thất bại | Transaction rollback; không để lại Order mồ côi |
| Cùng `orderId` gửi lại với dữ liệu giống nhau | Không sinh thêm Order theo khóa; kiểm tra relationship không nhân đôi |
| Cùng `orderId` nhưng tổng tiền khác | Ứng dụng phát hiện xung đột và từ chối |
| Vi phạm constraint dưới ghi đồng thời | Database không commit node trùng, ứng dụng xử lý lỗi phù hợp |
| Driver callback bị thử lại do lỗi transient có thể retry | Mọi ID dùng lại ổn định; không phát side effect ngoài database |
| HTTP timeout sau lần commit khả dĩ | Kiểm tra lại bằng business ID trước khi tạo yêu cầu khác |
| Session bị dùng từ nhiều luồng | Thay bằng **mỗi luồng/request một Session** |
| Kết quả rất lớn | Đo bộ nhớ, phân trang/giới hạn thay vì `list` vô hạn |

### Một kiểm thử nguyên tử tối thiểu

Trong môi trường bài tập, tạo customer rồi chạy lệnh cố ý gây exception:

~~~java
try (Session session =
        driver.session(SessionConfig.forDatabase("neo4j"))) {
    try {
        session.executeWrite(tx -> {
            tx.run("""
                CREATE (:Order {orderId: 'ROLLBACK-TEST-01'})
                """).consume();
            throw new IllegalStateException("Force rollback");
        });
    } catch (IllegalStateException expected) {
        // Dự kiến có lỗi nghiệp vụ để kiểm thử rollback.
    }

    long count = session.executeRead(tx ->
            tx.run("""
                MATCH (o:Order {orderId: 'ROLLBACK-TEST-01'})
                RETURN count(o) AS n
                """).single().get("n").asLong());

    if (count != 0) {
        throw new AssertionError("Rollback did not work");
    }
}
~~~

Chỉ chạy kiểm thử trên database riêng. Dữ liệu cùng `orderId` từ **transaction đã commit trước đó** sẽ không bị rollback bởi lần thử hiện tại, vì vậy cần chọn ID thử nghiệm mới hoặc bảo đảm môi trường cô lập.

### Quan sát thời gian và lỗi

Khi đưa vào vận hành, theo dõi:

- Độ trễ p50/p95/p99 của **toàn bộ lời gọi** `executeRead` / `executeWrite`.
- Tỷ lệ lỗi và timeout; thời gian lấy connection, độ trễ network và thao tác đọc hết result.
- Số transaction lỗi/transient/deadlock, số lần retry nếu telemetry hiện có hỗ trợ.
- Số transaction đang chạy, thời gian giữ khóa, số hàng xử lý và tài nguyên Neo4j.

Không chỉ lấy thời gian chạy `tx.run`: lời gọi này có thể chưa tiêu thụ toàn bộ kết quả, còn managed transaction chỉ kết thúc sau khi commit. `EXPLAIN` và `PROFILE` giúp phân tích kế hoạch Cypher, nhưng không thay thế đo end-to-end ở ứng dụng.

## 13. Bài tập tự luyện

**Bài 1 — Đọc an toàn:** Viết `executeRead` trả danh sách tối đa 50 khách hàng có `tier = 'GOLD'`. Kiểm tra cách đặt tham số, dùng `list(mapper)` và đóng session.

**Bài 2 — Ghi nguyên tử:** Viết `executeWrite` thực hiện hai câu: (1) upsert node `Order`, (2) tạo `PLACED` tới đúng `Customer`. Cố ý ném exception sau câu thứ nhất và chứng minh Order mới không được commit.

**Bài 3 — Retry:** Giả sử callback đôi khi chạy hai lần. Chỉ ra vì sao `UUID.randomUUID()` và gọi cổng thanh toán bên trong callback là nguy hiểm. Sửa thiết kế dùng `requestId` ổn định và sự kiện outbox có ID duy nhất.

**Bài 4 — Đọc sau ghi:** Một luồng ghi thành công, sau đó luồng khác đọc từ cluster nhưng chưa thấy cập nhật. Hãy tìm hiểu cơ chế bookmark/causal consistency thay vì thêm `Thread.sleep(...)` tùy ý.

**Bài 5 — Dữ liệu lớn:** Một query trả hàng triệu node. Đánh giá vì sao `.list()` có thể gây áp lực heap Java và đề xuất phương án giới hạn, phân trang hoặc xử lý kết quả theo batch.

### Câu hỏi nhanh

**1. Có được gọi `tx.commit()` bên trong `executeWrite` không?** Không. Driver quản lý commit/rollback; callback chỉ chạy công việc trên `tx` và trả về kết quả.

**2. `executeRead` có mặc định bảo đảm snapshot cố định của mọi lần đọc không?** Không. Mức cô lập read committed của Neo4j không phải snapshot isolation/serializable tổng quát.

**3. Một callback thành công nhưng commit thất bại thì ứng dụng có được trả HTTP 200 không?** Không; phải xử lý kết quả/lỗi của `executeWrite`, không lấy việc đi hết callback làm bằng chứng commit.

**4. Driver có retry mọi exception không?** Không. Chỉ những lỗi được nhận diện là retryable theo chính sách và thời hạn cấu hình.

**5. Có nên dùng chung Session trong nhiều request đồng thời?** Không. Dùng chung Driver, tạo Session riêng theo đơn vị công việc.

**6. `MERGE` và uniqueness constraint đã loại bỏ nhu cầu xử lý request gửi lại chưa?** Chưa. Cần thêm khóa yêu cầu ổn định và kiểm tra xung đột dữ liệu nghiệp vụ; với relationship và hệ thống ngoài Neo4j có các điều kiện riêng.

## 14. Checklist áp dụng

- [ ] Chọn `executeRead` cho chỉ đọc, `executeWrite` cho thao tác có ghi hoặc đọc-để-ghi.
- [ ] Dùng **Driver chung**, **Session riêng** theo request và chỉ định đúng database.
- [ ] Đặt tất cả câu Cypher cùng nghiệp vụ vào **một callback** nếu cần commit/rollback nguyên tử.
- [ ] Đọc/`consume()` result bên trong callback, không trả Result còn gắn transaction.
- [ ] Dùng **tham số Cypher**, business ID ổn định, uniqueness constraint và kiểm tra đầu vào.
- [ ] Nhớ callback có thể chạy lại: không gửi email, gọi thanh toán hoặc sinh ID thay đổi ở bên trong.
- [ ] Phân biệt retry kỹ thuật của Driver với **retry toàn HTTP/request** và xử lý tính lũy đẳng.
- [ ] Không bắt lỗi rồi trả “thành công” nếu nghiệp vụ yêu cầu rollback.
- [ ] Cấu hình pool/timeout, routing và bookmark theo topology và mức nhất quán cần thiết.
- [ ] Với Spring Data Neo4j, để transaction manager của Spring điều phối các repository call liên quan.
- [ ] Kiểm thử rollback, constraint, cạnh tranh ghi, timeout và kết quả đọc lớn trên database riêng.

## Tài liệu tham khảo

- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual — Query the database](https://neo4j.com/docs/java-manual/current/query-simple/)
- [Neo4j Java Driver Manual](https://neo4j.com/docs/java-manual/current/)
- [Neo4j Cypher Manual — Transactions](https://neo4j.com/docs/cypher-manual/current/transactions/)
- [Neo4j Java Driver API](https://neo4j.com/docs/api/java-driver/current/)

**Kết luận:** `executeRead` và `executeWrite` là lựa chọn trung tâm khi Java cần Neo4j quản lý giao dịch đọc/ghi. Chúng giúp một callback Cypher có **ranh giới commit/rollback rõ ràng, định tuyến phù hợp và khả năng retry lỗi nhất thời**. Để nghiệp vụ thực sự đúng, ứng dụng vẫn cần quản lý vòng đời Driver/Session, consume kết quả đúng lúc, dùng định danh ổn định, kiểm soát concurrency và tránh tác dụng phụ ngoài database trong callback có thể chạy lại.
