# Bookmarks, nhất quán nhân quả và định tuyến khi kết nối cụm

## 1. Vì sao ứng dụng Java cần bookmark trong cụm Neo4j?

Trong Neo4j, các node, relationship và property tạo thành **property graph**. Một ứng dụng Java có thể ghi một node đơn hàng bằng Cypher, rồi ngay lập tức đọc lại để hiển thị trạng thái, truy vấn đường đi hoặc tải các quan hệ của đơn hàng đó. Nếu kết nối một **Neo4j cluster**, giao dịch ghi thường được gửi tới **writer** của database, còn giao dịch đọc có thể chạy trên một **reader** khác đang áp dụng những thay đổi được sao chép đến.

Ví dụ, dịch vụ Java thực hiện theo thứ tự:

1. **T1:** tạo **(:DemoBookmarkOrder {id: 'O-101'})** và commit thành công.
2. **T2:** từ một session hoặc service khác, đọc đơn **O-101** ngay sau T1.
3. Ở thời điểm T2 bắt đầu, reader được chọn có thể chưa áp dụng trạng thái mà T1 vừa commit.

Nếu T2 bắt buộc phải nhìn thấy T1, ứng dụng cần thể hiện quan hệ phụ thuộc **T1 xảy ra trước T2**. **Bookmark** là token giúp Neo4j Java Driver chuyển quan hệ phụ thuộc này cho lần truy vấn tiếp theo. Server sẽ chỉ thực thi giao dịch phụ thuộc khi thành viên được chọn đạt ít nhất trạng thái cơ sở dữ liệu mà bookmark biểu diễn.

Bài thuộc chương **Java Driver** của module **DATABASE_ENGINE_GRAPH_NEO4J**, tập trung vào:

- Khác biệt giữa **commit thành công**, **reader bắt kịp dữ liệu** và **nhất quán nhân quả** (*causal consistency*).
- Cơ chế **bookmark**, phạm vi tự động quản lý và cách chuyển bookmark giữa các **session**, luồng hoặc service.
- **Routing URI**, routing table và vai trò **reader/writer** trong cụm.
- Thực hành với Java Driver đời mới, xử lý failover, retry và tối ưu độ trễ.

Đây là bài về tính nhất quán và định tuyến trong truy cập đồ thị bằng Java. Nó **không** thay thế phần thiết kế transaction, index, constraint hoặc cách tối ưu Cypher; các yếu tố đó vẫn quyết định tính đúng và hiệu năng của ứng dụng.

## 2. Mô hình nhất quán: phải bảo đảm điều gì?

### 2.1. Commit không có nghĩa mọi reader lập tức hiển thị thay đổi

Trong cụm Neo4j, một database có thể có nhiều server. Các giao dịch ghi được phối hợp bởi **leader/writer** của database, còn các thành viên khác có thể nhận và áp dụng thay đổi vào thời điểm sau đó. Driver có thể định tuyến giao dịch đọc sang một reader nhằm phân phối tải.

Hình dung:

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant W as Writer
    participant R as Reader
    App->>W: T1: CREATE Order O-101
    W-->>App: Commit + bookmark B1
    Note over W,R: Reader có thể đang bắt kịp T1
    App->>R: T2: MATCH Order O-101 + B1
    R-->>R: Đợi trạng thái B1 nếu cần
    R-->>App: Trả Order O-101
~~~

**Bookmark không ép mọi thành viên của cụm đồng bộ tức thời.** Nó đặt một **điều kiện trước khi chạy truy vấn có phụ thuộc**: server phải đủ cập nhật để đáp ứng bookmark. Truy vấn có thể phải chờ, định tuyến lại hoặc thất bại khi không thể đáp ứng điều kiện trong giới hạn thời gian.

### 2.2. Phân biệt các loại bảo đảm

| Khái niệm | Điều được bảo đảm hoặc mô tả | Điều **không** được tự suy ra |
|---|---|---|
| **Transaction ACID** | Một transaction commit hoặc rollback như một đơn vị | Mọi reader khác đều thấy commit ngay cùng một thời điểm |
| **Eventual consistency khi sao chép** | Khi hệ thống ổn định, các replica cuối cùng bắt kịp | Một reader bất kỳ đọc ngay sau commit luôn thấy bản mới |
| **Causal consistency qua bookmark** | Giao dịch phụ thuộc không chạy trước khi trạng thái được đánh dấu đã có trên server phục vụ nó | Tất cả giao dịch của mọi user có một thứ tự thời gian toàn cục do ứng dụng kiểm soát |
| **Read-your-writes** | Đọc sau đó trong cùng chuỗi nhân quả thấy những gì mình đã ghi | Truy vấn của tiến trình khác tự biết bookmark mà không được truyền |
| **Linearizability / đọc trạng thái mới nhất toàn hệ thống** | Một bảo đảm mạnh hơn về thứ tự quan sát theo thời gian thực | Bookmark đơn lẻ không biến mọi luồng đọc/ghi độc lập thành linearizable |

Bookmark tạo ra một quan hệ **happens-before** cho các công việc có phụ thuộc rõ ràng. Nó không phải timestamp đáng tin cậy để so sánh thời gian, không phải ID của node và không thể thay thế kiểm soát tranh chấp khi nhiều giao dịch cùng sửa một thực thể.

### 2.3. Khi nào cần liên kết nhân quả?

- **Đọc ngay sau ghi:** API tạo hồ sơ rồi yêu cầu API khác lấy hồ sơ mới.
- **Chuỗi công việc:** tạo Customer trước, tạo Order gắn với Customer sau, rồi đọc graph chứa cả hai.
- **Fan-in:** hai tác vụ độc lập tạo A và B; tác vụ thứ ba cần thấy **cả A và B**.
- **Giao việc qua hàng đợi:** worker B chỉ được xử lý sau khi dữ liệu do worker A tạo đã khả dụng.

Không phải tất cả truy vấn đều cần chờ bookmark mới nhất. Báo cáo thống kê độc lập hoặc danh sách công khai có thể chấp nhận độ trễ sao chép để giảm thời gian chờ và tăng thông lượng.

## 3. Bookmark là gì trong Java Driver?

Một bookmark là **token opaque** đại diện cho một trạng thái đã đạt của **một database**. Java Driver biểu diễn nó bằng interface **org.neo4j.driver.Bookmark**. Ứng dụng nên **lưu, chuyển và khôi phục**, không phân tích chuỗi bên trong hoặc tự tạo giá trị theo quy luật đoán được.

Vòng đời:

~~~mermaid
flowchart LR
    A["Transaction T1 commit"] --> B["Driver nhận bookmark B1"]
    B --> C["Session tiếp theo nhận B1"]
    C --> D["Server đợi trạng thái >= B1"]
    D --> E["T2 có thể đọc dữ liệu của T1"]
    E --> F["T2 kết thúc và có bookmark mới"]
~~~

**Điểm cần nhớ về phạm vi:**

1. Trong **một Session**, driver tự liên kết các transaction **chạy tuần tự** theo bookmark mới nhất của session.
2. Với **Driver.executableQuery()**, driver dùng bookmark manager mặc định để liên kết các lời gọi tiếp theo qua **cùng driver**.
3. Hai **Session độc lập** không tự chia sẻ mọi bookmark chỉ vì chúng được tạo từ cùng một Driver. Cần **Session.lastBookmarks()**, **SessionConfig.withBookmarks(...)** hoặc một **BookmarkManager** dùng chung.
4. Hai **tiến trình Java/service độc lập** không tự chia sẻ manager trong bộ nhớ. Nếu yêu cầu nhân quả bắc qua ranh giới service, phải chuyển dữ liệu bookmark hoặc thiết kế một cơ chế truyền trạng thái khác.
5. Bookmark gắn với **database** cụ thể. Không trộn bookmark tùy tiện giữa các database khác nhau trong cùng DBMS, hoặc giữa các cụm độc lập.

**Đừng nhầm thứ tự thời gian với quan hệ phụ thuộc.** Hai giao dịch độc lập có thể chạy song song; chỉ những giao dịch thực sự phải quan sát kết quả của nhau mới cần chuỗi bookmark chung.

### 3.1. Các API quan trọng

| API Java Driver | Vai trò |
|---|---|
| **Session.lastBookmarks()** | Lấy tập bookmark cuối của session sau khi công việc đã hoàn tất |
| **SessionConfig.Builder.withBookmarks(...)** | Gắn tập bookmark ban đầu cho session mới |
| **SessionConfig.Builder.withBookmarkManager(...)** | Dùng một manager để quản lý bookmark qua nhiều session |
| **BookmarkManagers.defaultManager(config)** | Tạo manager dùng chung có cơ chế quản lý bookmark của driver |
| **Driver.executableQueryBookmarkManager()** | Lấy manager mặc định của các lời gọi **executableQuery()** |
| **Bookmark.value()** | Lấy chuỗi opaque để chuyển qua ranh giới tiến trình |
| **Bookmark.from(value)** | Khôi phục Bookmark từ chuỗi đã được tạo bởi driver |

Tài liệu và ví dụ dưới đây dùng cách gọi API của **Neo4j Java Driver 5/6 hiện đại**, đặc biệt kiểm tra theo API **6.x**. Từ Java Driver 6, **Session.lastBookmark()** dạng đơn không còn dùng; sử dụng **Session.lastBookmarks()**. Kiểm tra version driver trong ứng dụng trước khi sao chép mã.

## 4. Routing URI và vai trò reader/writer trong cluster

### 4.1. Chọn URI quyết định driver có định tuyến hay không

Java Driver sử dụng giao thức **Bolt**. Tiền tố URI điều khiển cách kết nối:

| URI | Kiểu kết nối | Mã hóa/kết nối tin cậy | Khi nào dùng |
|---|---|---|---|
| **neo4j://host:7687** | Có cơ chế **routing** | Thông thường không bật TLS theo scheme | Môi trường cục bộ hoặc cluster đã cấu hình bảo mật phù hợp |
| **neo4j+s://host:7687** | Routing | TLS, chứng chỉ do CA tin cậy ký | Cluster production, **Neo4j Aura** theo URI cấp sẵn |
| **neo4j+ssc://host:7687** | Routing | TLS chấp nhận chứng chỉ tự ký | Môi trường kiểm thử có chính sách chứng chỉ rõ ràng |
| **bolt://host:7687** | **Direct** tới server chỉ định | Thông thường không bật TLS theo scheme | Kết nối trực tiếp một instance, chẩn đoán có chủ đích |
| **bolt+s://host:7687** | Direct | TLS, chứng chỉ CA tin cậy | Server cụ thể có TLS |
| **bolt+ssc://host:7687** | Direct | TLS chấp nhận chứng chỉ tự ký | Kiểm thử direct với certificate tự ký |

**Không tự đổi neo4j+s:// thành bolt+s:// chỉ vì cả hai mã hóa.** Nhóm **neo4j** có routing; nhóm **bolt** nói chuyện trực tiếp với một máy. Với cụm cần failover và phân tải đọc, dùng **URI routing do nhà quản trị hoặc Aura cung cấp**.

Không bật **+ssc** để bỏ qua lỗi xác minh chứng chỉ trong production khi hệ thống yêu cầu CA tin cậy. Scheme, DNS, chứng chỉ và endpoint phải khớp cấu hình của môi trường thật.

### 4.2. Routing table hoạt động thế nào?

Khi dùng scheme **neo4j**, driver liên hệ một địa chỉ đầu vào (*seed/router*), lấy **routing table** cho database, sau đó quyết định gửi giao dịch tới server phù hợp. Routing table có thể chứa:

- **Routers:** thành viên cung cấp thông tin định tuyến mới.
- **Writers:** server có khả năng xử lý ghi của database, thường là **leader** hiện tại.
- **Readers:** thành viên phục vụ truy vấn đọc theo chính sách cụm.

~~~mermaid
flowchart TD
    A["Java Driver neo4j+s://cluster"] --> B["Nhận routing table cho database"]
    B --> C{"Loại giao dịch?"}
    C -->|"WRITE"| D["Writer / leader"]
    C -->|"READ"| E["Reader thích hợp"]
    D --> F["Commit + bookmark"]
    F --> E
    E --> G["Đợi bookmark nếu cần, rồi trả kết quả"]
~~~

**Vai trò được xác định theo database.** Trong hệ thống nhiều database, một server có thể là writer cho database này và reader cho database khác. Routing table có thời hạn sử dụng (*TTL*); driver làm mới định kỳ hoặc khi phát hiện thành viên/leader thay đổi.

Một entrypoint đơn lẻ vẫn có thể là điểm yếu khi chưa lấy được routing table: nếu địa chỉ đầu tiên chết, driver có thể không khám phá được cụm. Với triển khai production, cân nhắc tên DNS có nhiều bản ghi A/AAAA, custom resolver theo hướng dẫn hoặc điểm truy cập có tính sẵn sàng cao.

### 4.3. Lỗi DNS hoặc advertised address khi đã kết nối được seed

Trường hợp hay gặp trong Docker, Kubernetes hoặc mạng nội bộ: Java kết nối được **cluster.example.com:7687**, nhưng bảng định tuyến trả về địa chỉ thành viên như **neo4j-1.internal:7687** không thể truy cập từ ứng dụng. Driver có thể báo lỗi lấy connection hoặc lỗi routing dù endpoint đầu tiên hoạt động.

Để khắc phục, kiểm tra **advertised Bolt addresses**, DNS, firewall, cổng, chứng chỉ và tên host được công bố cho client. Đừng dùng **bolt://** để bỏ qua lỗi đó rồi kết luận cluster đã được cấu hình đúng; direct connection có thể chỉ hoạt động trước khi leader chuyển sang máy khác.

## 5. Thực hành: chuẩn bị dữ liệu và kết nối Java

Chạy constraint trên **database thử nghiệm**, chỉ một lần:

~~~cypher
CREATE CONSTRAINT demo_bookmark_order_id IF NOT EXISTS
FOR (o:DemoBookmarkOrder)
REQUIRE o.id IS UNIQUE;
~~~

Ví dụ dùng **(:DemoBookmarkOrder {id, status})**. Tên nhãn này giúp tách bài thực hành khỏi node **Order** thật. Lệnh **MERGE** tạo hoặc cập nhật một đơn cụ thể, nên nếu chạy nhiều lần với cùng id thì sẽ cập nhật trạng thái thay vì tạo bản sao.

### 5.1. Khởi tạo Driver đúng vòng đời

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;

String uri = System.getenv("NEO4J_URI");
String username = System.getenv("NEO4J_USERNAME");
String password = System.getenv("NEO4J_PASSWORD");

try (Driver driver = GraphDatabase.driver(
        uri, AuthTokens.basic(username, password))) {
    driver.verifyConnectivity();
    // Các ví dụ tiếp theo sử dụng driver này.
}
~~~

Đặt **NEO4J_URI** theo endpoint của môi trường (ví dụ **neo4j+s://...** do Aura cấp). Không hardcode mật khẩu hoặc in credential ra log. Driver nên được tạo **một lần cho mỗi cấu hình kết nối ứng dụng** và dùng lại giữa các luồng, vì nó quản lý connection pool và routing table. **Session** là đối tượng nhẹ và **không thread-safe**; tạo riêng, đóng bằng **try-with-resources** sau mỗi đơn vị công việc.

Các đoạn Java ở những mục tiếp theo là những ví dụ **bên trong phương thức đang có biến Driver driver** và tên database **dbName**; nhập **dbName** đúng với database thử nghiệm đang dùng. Ví dụ dùng Java phiên bản hỗ trợ **text block**.

## 6. Trong một session: bookmark được duy trì tự động

Khi các giao dịch kế tiếp chạy trong cùng session, driver sẽ truyền trạng thái nhân quả giữa chúng:

~~~java
import java.util.Map;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

String dbName = "neo4j";
String orderId = "O-101";

try (Session session = driver.session(
        SessionConfig.forDatabase(dbName))) {

    session.executeWriteWithoutResult(tx -> {
        tx.run("""
            MERGE (o:DemoBookmarkOrder {id: $id})
            SET o.status = $status
            """, Map.of("id", orderId, "status", "CREATED"))
            .consume();
    });

    String status = session.executeRead(tx ->
        tx.run("""
            MATCH (o:DemoBookmarkOrder {id: $id})
            RETURN o.status AS status
            """, Map.of("id", orderId))
          .single().get("status").asString()
    );

    System.out.println(status); // CREATED
}
~~~

Giao dịch **executeWriteWithoutResult(...)** kết thúc thành công trước khi gọi **executeRead(...)**. Driver tự giữ bookmark tương ứng trong session, vì vậy đọc sau được gắn với trạng thái commit của ghi trước. **executeRead(...)** còn thể hiện truy vấn chỉ đọc để driver định tuyến sang reader thích hợp trong cụm.

Nếu muốn hai câu Cypher phải **nguyên tử** với nhau, đặt trong **một transaction** bằng một callback phù hợp. Bookmark liên kết **các transaction đã commit theo thứ tự**, nhưng không biến hai transaction thành một đơn vị ACID.

## 7. Giữa hai session: chuyển lastBookmarks sang withBookmarks

Một API HTTP có thể ghi trong session ngắn, đóng session, rồi code khác mở session đọc. Hai session độc lập cần chuyển bookmark khi yêu cầu **read-your-writes**.

~~~java
import java.util.Map;
import java.util.Set;
import org.neo4j.driver.AccessMode;
import org.neo4j.driver.Bookmark;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

String dbName = "neo4j";
String orderId = "O-102";
Set<Bookmark> afterWrite;

// T1: ghi, commit, rồi giữ lại bookmark của session.
try (Session writer = driver.session(SessionConfig.forDatabase(dbName))) {
    writer.executeWriteWithoutResult(tx -> {
        tx.run("""
            MERGE (o:DemoBookmarkOrder {id: $id})
            SET o.status = 'CREATED'
            """, Map.of("id", orderId))
            .consume();
    });
    afterWrite = Set.copyOf(writer.lastBookmarks());
}

// T2: session khác, đọc trên reader nhưng phải thấy T1.
try (Session reader = driver.session(SessionConfig.builder()
        .withDatabase(dbName)
        .withBookmarks(afterWrite)
        .withDefaultAccessMode(AccessMode.READ)
        .build())) {

    String status = reader.executeRead(tx ->
        tx.run("""
            MATCH (o:DemoBookmarkOrder {id: $id})
            RETURN o.status AS status
            """, Map.of("id", orderId))
            .single().get("status").asString()
    );

    System.out.println(status); // CREATED
}
~~~

**Vì sao lấy bookmark sau callback?** Chỉ sau khi transaction đã **commit thành công**, bookmark mới đại diện cho trạng thái mà giao dịch sau phải nhìn thấy. Không lấy bookmark ở giữa callback trước commit; không giả định transaction bị rollback vẫn tạo ra bookmark cho dữ liệu chưa được ghi.

Ở đây **Set.copyOf(...)** giữ một bản sao không bị thay đổi trong ứng dụng. **withBookmarks(...)** nhận tập bookmark ban đầu, và driver tiếp tục tự cập nhật bookmark trong session đọc. Bookmark có thể trống trong một số tình huống; code thật phải xử lý theo API và kết quả transaction, không tự suy ra một bookmark từ thời gian hệ thống.

### 7.1. Fan-in: cần thấy kết quả của hai nguồn ghi song song

Giả sử session A tạo Customer và session B tạo Product; session C cần tạo relationship giữa hai node. Hai tác vụ A và B có thể chạy song song, nhưng **C chỉ bắt đầu sau khi cả hai commit**. Sau khi hai tác vụ ghi trả về:

~~~java
import java.util.HashSet;
import java.util.Set;
import org.neo4j.driver.Bookmark;
import org.neo4j.driver.SessionConfig;

Set<Bookmark> dependencies = new HashSet<>();
dependencies.addAll(sessionABookmarks);
dependencies.addAll(sessionBBookmarks);

try (var sessionC = driver.session(SessionConfig.builder()
        .withDatabase(dbName)
        .withBookmarks(dependencies)
        .build())) {
    sessionC.executeWriteWithoutResult(tx -> {
        tx.run("""
            MATCH (c:DemoBookmarkCustomer {id: $customerId})
            MATCH (p:DemoBookmarkProduct {sku: $sku})
            MERGE (c)-[:DEMO_BOOKMARK_BUYS]->(p)
            """, Map.of("customerId", "C-101", "sku", "P-201"))
            .consume();
    });
}
~~~

**sessionABookmarks** và **sessionBBookmarks** ở đây là các tập **Set<Bookmark>** thu được bằng **lastBookmarks()** sau commit của hai tác vụ riêng; Customer và Product phải được tạo trước trên database thử nghiệm nếu muốn chạy mẫu này. Java Driver sẽ yêu cầu trạng thái đáp ứng **cả hai phụ thuộc** trước khi thực thi T3.

Không có ý nghĩa ghép bookmark của các database khác nhau vào cùng một session. Đồng thời, **kết hợp bookmark không khóa dữ liệu**; nếu tác vụ khác sửa Customer sau khi A commit, các quy tắc đồng thời vẫn phải được giải quyết bằng transaction và constraint.

## 8. BookmarkManager: dùng chung trạng thái qua nhiều session

Chuyển thủ công **lastBookmarks()/withBookmarks()** hữu ích khi chỉ có một vài phụ thuộc rõ ràng. Nếu một luồng nghiệp vụ tạo nhiều session trong **cùng JVM**, có thể dùng chung **BookmarkManager** để driver tự thu thập và phân phối bookmark.

### 8.1. Tạo manager dành riêng cho một luồng phụ thuộc

~~~java
import java.util.Map;
import org.neo4j.driver.BookmarkManager;
import org.neo4j.driver.BookmarkManagerConfig;
import org.neo4j.driver.BookmarkManagers;
import org.neo4j.driver.SessionConfig;

BookmarkManager manager = BookmarkManagers.defaultManager(
    BookmarkManagerConfig.builder().build());

SessionConfig writeConfig = SessionConfig.builder()
    .withDatabase(dbName)
    .withBookmarkManager(manager)
    .build();

try (var writer = driver.session(writeConfig)) {
    writer.executeWriteWithoutResult(tx ->
        tx.run("""
            MERGE (o:DemoBookmarkOrder {id: $id})
            SET o.status = $status
            """, Map.of("id", "O-103", "status", "PAID")).consume()
    );
}

SessionConfig readConfig = SessionConfig.builder()
    .withDatabase(dbName)
    .withBookmarkManager(manager)
    .build();

try (var reader = driver.session(readConfig)) {
    String status = reader.executeRead(tx ->
        tx.run("""
            MATCH (o:DemoBookmarkOrder {id: $id})
            RETURN o.status AS status
            """, Map.of("id", "O-103"))
            .single().get("status").asString()
    );
    System.out.println(status); // PAID
}
~~~

**Manager phải được chia sẻ thật sự**: mỗi lần gọi **BookmarkManagers.defaultManager(...)** tạo một manager riêng, nên không tạo manager mới cho từng session rồi mong có quan hệ nhân quả. Chỉ chia sẻ manager cho các công việc **cùng database và thật sự liên quan**; dùng một manager toàn cục cho hàng nghìn yêu cầu độc lập có thể khiến nhiều truy vấn phải chờ những ghi không liên quan.

Mặc định, **Session** không tự dùng chung một BookmarkManager với mọi session khác. Quản lý bookmark **nội bộ session** vẫn có hiệu lực mà không cần cấu hình manager chung.

### 8.2. Driver.executableQuery(): tự quản lý bookmark

**executableQuery()** thuận tiện khi một truy vấn độc lập trong mỗi transaction:

~~~java
import java.util.Map;
import org.neo4j.driver.QueryConfig;
import org.neo4j.driver.RoutingControl;

driver.executableQuery("""
    MERGE (o:DemoBookmarkOrder {id: $id})
    SET o.status = 'SHIPPED'
    """)
    .withParameters(Map.of("id", "O-104"))
    .withConfig(QueryConfig.builder()
        .withDatabase(dbName)
        .build())
    .execute();

var result = driver.executableQuery("""
    MATCH (o:DemoBookmarkOrder {id: $id})
    RETURN o.status AS status
    """)
    .withParameters(Map.of("id", "O-104"))
    .withConfig(QueryConfig.builder()
        .withDatabase(dbName)
        .withRouting(RoutingControl.READ)
        .build())
    .execute();

System.out.println(result.records().get(0).get("status").asString());
~~~

Những lời gọi **executableQuery()** dùng manager mặc định của **cùng Driver** được nối nhân quả; lời gọi đọc sau có thể đặt **RoutingControl.READ** để khai báo mục tiêu đọc. Nếu ứng dụng chủ động cấu hình **withBookmarkManager(null)**, nó tắt việc dùng manager cho lời gọi đó; đừng làm vậy nếu code đang phụ thuộc vào bảo đảm đọc sau ghi.

Khi trộn **executableQuery()** với session trong cùng chuỗi phụ thuộc, đưa manager mặc định vào session:

~~~java
SessionConfig sharedConfig = SessionConfig.builder()
    .withDatabase(dbName)
    .withBookmarkManager(driver.executableQueryBookmarkManager())
    .build();

try (var session = driver.session(sharedConfig)) {
    session.executeRead(tx ->
        tx.run("RETURN 1 AS ok").single().get("ok").asInt()
    );
}
~~~

**Không mặc định mọi Session tạo từ Driver đều chia sẻ manager này**: phải gắn **withBookmarkManager(...)** nếu cần liên kết với executableQuery.

## 9. Giao bookmark qua ranh giới service

Nếu service A commit một transaction, gửi sự kiện sang service B qua HTTP/message broker, **BookmarkManager trong JVM A không tự chuyển sang JVM B**. Khi quy trình yêu cầu B chắc chắn nhìn thấy dữ liệu vừa được A ghi:

1. A **commit thành công**.
2. A lấy **Set<Bookmark>** từ session.
3. A chuyển những giá trị opaque sang B bằng kênh truyền đáng tin cậy, cùng **tên database / thông tin luồng phụ thuộc**.
4. B khôi phục bookmark rồi tạo session mới với **withBookmarks(...)**.
5. B chạy transaction trên **cùng database logic**, để server đợi trạng thái phụ thuộc nếu cần.

Chuyển đổi dữ liệu ở Java:

~~~java
import java.util.List;
import org.neo4j.driver.Bookmark;

// Service A: sau khi commit, chuẩn bị payload để gửi sang service B.
List<String> tokens = writerBookmarks.stream()
    .map(Bookmark::value)
    .toList();

// Service B: nhận payload đã được kiểm tra và gắn vào session mới.
List<Bookmark> restored = tokens.stream()
    .map(Bookmark::from)
    .toList();

try (var session = driver.session(SessionConfig.builder()
        .withDatabase(dbName)
        .withBookmarks(restored)
        .build())) {
    session.executeRead(tx ->
        tx.run("RETURN 1 AS reachable")
          .single().get("reachable").asInt()
    );
}
~~~

Trong đoạn trên, **writerBookmarks** là tập bookmark từ giao dịch đã hoàn tất ở A; **tokens** được chuyển qua kênh liên service; service B thay giá trị biến bằng dữ liệu nhận thật. Câu **RETURN 1** chỉ minh họa cấu hình session; trong nghiệp vụ, thay bằng truy vấn đọc node/relationship phụ thuộc.

**Không tự thay bookmark bằng timestamp hoặc ID giao dịch tự tăng**. Bookmark là token do database/driver quy định. Hãy coi nó là metadata của luồng xử lý: giới hạn kích thước, xác thực nguồn gửi, tránh ghi token không cần thiết vào log hoặc lộ ở URL công khai. Đừng giữ bookmark mãi mãi như một trạng thái ứng dụng vĩnh viễn; thời gian sống và cách xử lý token lỗi cần theo chính sách hệ thống.

Nếu service A ghi database **orders** còn service B đọc database **analytics** khác, chỉ chuyển bookmark của orders **không tự bảo đảm** dữ liệu đã có trong analytics. Đồng bộ xuyên database yêu cầu cơ chế riêng (CDC, ETL, event, workflow hoặc xác nhận tiến độ).

## 10. Định tuyến truy vấn đọc và ghi đúng cách

### 10.1. Managed transactions: executeRead / executeWrite

Khi sử dụng **neo4j://** hoặc **neo4j+s://**, chỉ định rõ ý định để driver phân phối tải:

~~~java
try (var session = driver.session(
        SessionConfig.forDatabase(dbName))) {

    long total = session.executeRead(tx ->
        tx.run("MATCH (o:DemoBookmarkOrder) RETURN count(o) AS total")
          .single().get("total").asLong()
    );

    session.executeWriteWithoutResult(tx ->
        tx.run("""
            MERGE (o:DemoBookmarkOrder {id: $id})
            SET o.status = $status
            """, Map.of("id", "O-105", "status", "CREATED"))
          .consume()
    );
}
~~~

**executeRead** hướng transaction đọc tới nhóm reader theo routing table; **executeWrite** hướng transaction ghi đến writer của database. Driver có thể retry callback của **managed transaction** khi gặp lỗi tạm thời được nhận diện.

**Không dùng access mode làm cơ chế phân quyền.** Quyền READ/WRITE thật sự vẫn phải được cấp hoặc từ chối bằng role/database privileges. **executeRead** là *gợi ý định tuyến/intent*; không phải hàng rào bảo mật thay cho quyền của người dùng.

### 10.2. Explicit transaction và session.run()

Với explicit transaction:

~~~java
import org.neo4j.driver.AccessMode;

SessionConfig readOnlyRouting = SessionConfig.builder()
    .withDatabase(dbName)
    .withDefaultAccessMode(AccessMode.READ)
    .build();

try (var session = driver.session(readOnlyRouting);
     var tx = session.beginTransaction()) {
    long count = tx.run("MATCH (o:DemoBookmarkOrder) RETURN count(o) AS n")
        .single().get("n").asLong();
    System.out.println(count);
    tx.commit();
}
~~~

**withDefaultAccessMode(AccessMode.READ)** đặc biệt quan trọng cho **explicit transaction** và **session.run(...)** nếu cần đọc từ reader. Managed **executeRead** và **executeWrite** có thể tự chọn access mode theo loại callback. Không nên định tuyến mặc định mọi query đọc tới writer, vì dễ tạo tải không cần thiết trên thành viên xử lý ghi.

Với **session.run(...)** (*auto-commit*), cần tiêu thụ kết quả hoặc bảo đảm transaction đã hoàn tất trước khi dựa vào bookmark/kết quả commit. So với managed transaction, auto-commit có cơ chế retry và thời điểm commit khác; không dùng nó để thay thế những giao dịch nhiều bước cần điều phối và retry có kiểm soát.

### 10.3. Chọn database rõ ràng

~~~java
SessionConfig config = SessionConfig.builder()
    .withDatabase("neo4j")
    .build();
~~~

Tất cả ví dụ nên **chỉ định database**, kể cả môi trường chỉ có một database. Nếu bỏ qua, driver có thể phải hỏi server về home database, làm phát sinh round trip và có rủi ro nhầm database khi account hoặc deployment thay đổi. Với cluster có nhiều database, bảng định tuyến và writer được xác định **theo từng database**.

Sử dụng **SessionConfig.withDatabase(...)** thay vì phụ thuộc vào **USE** trong mọi Cypher; **USE** có thể đòi hỏi server-side routing và làm kế hoạch định tuyến phức tạp hơn.

## 11. Sự cố, failover và giới hạn của bookmark

### 11.1. Reader không bắt kịp bookmark

Tình huống: T1 commit, T2 có bookmark nhưng được gửi tới reader chưa áp dụng T1. Driver/server có thể phải **đợi** để reader bắt kịp. Nếu thời gian chờ vượt giới hạn hoặc thành viên không khả dụng, ứng dụng có thể nhận **timeout/transient error**.

Không kết luận rằng bookmark “không hoạt động” chỉ vì thời gian T2 tăng. Phần tăng có thể là **chi phí đợi dữ liệu** để đáp ứng yêu cầu nhân quả. Quan sát thời gian request, transaction retry, lỗi routing, trạng thái cụm và độ trễ sao chép trước khi đổi cấu hình.

### 11.2. Leader chuyển và routing table cũ

Trong cụm có bầu lại leader, một writer được ghi trong bảng định tuyến cũ có thể không còn được phép ghi. Driver có thể cập nhật routing table và **thử lại** managed transaction khi gặp lỗi tạm thời.

Tuy nhiên, callback **executeWrite** có thể **được chạy lại**. Vì vậy:

- Chỉ đặt thao tác database và tính toán an toàn khi retry trong callback.
- **Không** gửi email, thu tiền hoặc gọi API ngoài trong callback nếu các tác động đó không idempotent.
- Dùng **requestId/idempotency key** và constraint khi yêu cầu nghiệp vụ chỉ được áp dụng một lần.
- Không retry vô hạn; để driver quản lý lỗi transient và có giới hạn thời gian, hoặc triển khai chính sách retry riêng được đo đạc.
- Phân biệt lỗi **không thể định tuyến**, **hết thời gian chờ bookmark**, **lỗi authentication/permission** và **constraint violation**; không retry mù tất cả.

### 11.3. Những điều bookmark không giải quyết

| Vấn đề | Bookmark có giải quyết không? | Cách tiếp cận |
|---|---|---|
| Reader cần nhìn thấy transaction ghi trước | **Có**, khi bookmark được truyền/managed đúng | Liên kết bằng bookmark |
| Hai transaction cùng tăng một bộ đếm và gây lost update | **Không** | Thiết kế Cypher cập nhật nguyên tử, khóa/constraint phù hợp |
| Hai service tạo trùng Customer vì thiếu khóa duy nhất | **Không** | Uniqueness constraint và MERGE theo khóa ổn định |
| Đọc dữ liệu từ cache ứng dụng không được làm mới | **Không** | Invalidate/update cache theo quy trình riêng |
| Giữ dữ liệu nhất quán giữa hai database độc lập | **Không tự động** | CDC/outbox/ETL và xác nhận tiến độ |
| Giảm latency mọi truy vấn | **Không**; chờ bookmark có thể làm tăng latency | Chỉ liên kết các truy vấn có quan hệ phụ thuộc |
| Thay quyền WRITE/READ của user | **Không** | RBAC, quyền graph/database và cấu hình an toàn |

### 11.4. Không dùng một manager toàn cục theo thói quen

Giả sử app có hàng nghìn người dùng tạo và đọc đơn hàng độc lập. Một **BookmarkManager dùng chung toàn app** có thể đẩy các truy vấn độc lập vào chuỗi phụ thuộc không cần thiết, làm mỗi request phải chờ trạng thái do request khác tạo ra. Nếu cần bảo đảm nhân quả **theo từng request hoặc người dùng**, dùng manager hoặc bookmark đúng **phạm vi luồng nghiệp vụ**.

Chiến lược thường gặp:

| Mức phụ thuộc | Thiết kế thích hợp |
|---|---|
| Nhiều thao tác trong cùng transaction | Một transaction |
| Nhiều transaction tuần tự trong một Session | Một Session |
| Nhiều Session trong một workflow Java | Chuyển bookmark hoặc dùng chung manager |
| Kết hợp executableQuery với Session | **driver.executableQueryBookmarkManager()** |
| Nhiều service/JVM | Chuyển token bookmark qua ranh giới service, hoặc cơ chế đồng bộ khác |
| Tác vụ độc lập, cho phép độ trễ sao chép | Không ghép bookmark không cần thiết |

## 12. Kiểm thử hành vi trên cụm

Bài thực hành cần tối thiểu **một database thử nghiệm**, tài khoản Java có quyền đọc/ghi và một endpoint routing. Để quan sát thực sự việc reader bắt kịp writer, nên thử trên cluster có nhiều thành viên; một Neo4j instance đơn lẻ vẫn giúp kiểm tra API, nhưng không thể chứng minh tác dụng của routing/replication.

### 12.1. Test read-your-writes

1. Dùng **executeWrite** ghi một **DemoBookmarkOrder** mới.
2. Đọc ở **Session khác** với bookmark được lấy từ writer và **executeRead**.
3. Xác nhận **status** đúng với dữ liệu vừa commit.
4. Lặp lại với nhiều id, nhiều lần để kiểm tra tính ổn định.

Kết quả mong đợi là reader có điều kiện bookmark **không đọc trạng thái cũ hơn giao dịch phụ thuộc**. Kiểm thử không cần cố tạo độ trễ sao chép bằng **Thread.sleep**; độ trễ thực của cluster không thể được dự báo chính xác.

### 12.2. Test fan-in

1. Dùng hai session/luồng ghi độc lập để tạo Customer và Product.
2. Chờ **cả hai transaction commit**, lấy hai tập bookmark.
3. Session thứ ba nhận **hợp** hai tập bookmark và tạo relationship.
4. Kiểm tra cả hai endpoint tồn tại và relationship được tạo đúng.

Nếu một nhánh ghi thất bại, **không** coi bookmark của nhánh còn lại là bằng chứng cho sự tồn tại của cả hai node. Giao dịch kết hợp chỉ nên chạy khi các điều kiện nghiệp vụ đã được đáp ứng.

### 12.3. Test routing và failover

1. Kết nối bằng **neo4j+s://...** theo cấu hình của cụm; chạy **executeRead** và **executeWrite**.
2. Quan sát log/metrics của driver hoặc cụm để xác nhận request đi đến vai trò phù hợp và routing table được làm mới.
3. Trong môi trường thử nghiệm được quản trị viên cho phép, thay đổi leader hoặc tạm dừng thành viên để kiểm tra lỗi transient, cơ chế retry và khả năng tiếp tục hoạt động.
4. Kiểm tra có phải mọi **advertised address** đều phân giải được từ host/container của ứng dụng, kể cả sau failover.

**Không kiểm thử failover trực tiếp trên production khi chưa có phương án vận hành.** Không dùng URI **bolt://** để đánh giá khả năng routing vì driver sẽ nối trực tiếp một thành viên.

### 12.4. Chỉ số cần đo

- p50/p95 latency của **read sau write**, so với đọc độc lập không có bookmark.
- Tỷ lệ retry của **executeRead/executeWrite**, lỗi timeout và lỗi routing.
- Thời gian phát hiện thành viên không dùng được và làm mới routing table.
- Tải và độ trễ trên writer so với reader, tình trạng sao chép trong cụm.
- Dấu hiệu nghẽn connection pool, số session chưa được đóng, số transaction chạy quá lâu.

Chỉ tắt bookmark khi workload thật **cho phép** đọc dữ liệu chưa bắt kịp. Quyết định này là thay đổi về **yêu cầu nhất quán**, không chỉ là mẹo tối ưu hiệu năng.

## 13. Những lỗi thiết kế thường gặp

1. **Dùng bolt:// để kết nối cụm cần tự failover.** Driver không có routing tới các writer/reader khác; có thể gãy khi server đích ngừng hoạt động.
2. **Cho rằng commit khiến mọi reader nhìn thấy dữ liệu ngay.** Replica cần áp dụng dữ liệu; bookmark giúp những truy vấn phụ thuộc đợi đúng trạng thái.
3. **Nghĩ cùng Driver tức là mọi Session tự chia sẻ bookmark.** Chỉ tự quản lý trong session hoặc qua manager/đường truyền đã cấu hình.
4. **Lấy bookmark trước commit.** Token phải đại diện cho trạng thái commit đã hoàn tất, không phải thay đổi đang xử lý.
5. **Gộp bookmark từ hai database độc lập.** Bookmark có phạm vi database; không phải công cụ đồng bộ dữ liệu liên database.
6. **Mặc định mọi truy vấn chạy executeWrite.** Truy vấn chỉ đọc bị định tuyến theo ý định ghi và có thể tăng tải writer.
7. **Dùng read mode để bảo mật.** Routing intent không thay thế quyền READ/WRITE của user.
8. **Dùng bookmark chung toàn hệ thống cho mọi request độc lập.** Có thể thêm quan hệ chờ không cần thiết và làm tăng p95.
9. **Gọi dịch vụ ngoài trong callback có retry.** Retry callback có thể lặp side effect; cần outbox/idempotency.
10. **Không chỉ định database.** Có thể phát sinh round trip để khám phá home database hoặc làm phức tạp routing.
11. **Không đóng Session/Driver.** Session/connection giữ tài nguyên và có thể làm cạn pool.
12. **Tự phân tích giá trị bookmark như số thứ tự.** Bookmark là token opaque; chỉ dùng API Bookmark.value()/Bookmark.from().

## 14. Bài tập và câu hỏi tình huống

### Bài 1 — Đọc sau ghi

Service A tạo một node Order O-200, rồi service B lập tức đọc nó trên reader. Hãy giải thích vì sao chỉ biết **thời điểm A trả HTTP 200** chưa đủ để B chọn reader an toàn, và vẽ lại luồng truyền **Bookmark** từ A sang B.

### Bài 2 — Hai session độc lập

Viết phương thức Java có hai session. Session thứ nhất **MERGE** một Customer và lấy **lastBookmarks()** sau commit. Session thứ hai dùng **withBookmarks(...)**, **executeRead(...)** để kiểm tra Customer vừa được tạo. Giải thích khi nào nên dùng **BookmarkManager** thay cho chuyển thủ công.

### Bài 3 — Fan-in sau hai nhánh song song

Hai worker tạo Product và Category trong hai transaction độc lập. Transaction thứ ba tạo **(:Product)-[:IN_CATEGORY]->(:Category)**. Liệt kê những điều kiện phải chờ và cho biết vì sao chỉ truyền một bookmark có thể thiếu.

### Bài 4 — Chọn URI

Cho ba URI **neo4j+s://cluster.example**, **bolt+s://server-1.example** và **neo4j+ssc://test.example**. Xác định URI có routing, URI direct và yêu cầu liên quan tới xác thực chứng chỉ. Vì sao không nên chuyển từ **neo4j+s** sang **bolt+s** để “khắc phục” lỗi routing mà chưa sửa nguyên nhân?

### Bài 5 — Phân tích sự cố

Sau một đợt chuyển leader, ứng dụng Java báo lỗi truy cập **server-2.internal** dù seed hostname còn hoạt động. Hãy đề xuất kiểm tra DNS, advertised address, routing table và firewall từ bên trong container ứng dụng.

### Bài 6 — Đánh đổi hiệu năng

Ứng dụng có 90% truy vấn đọc báo cáo và 10% giao dịch tạo đơn cần đọc ngay dữ liệu vừa ghi. Bạn sẽ dùng bookmark chung cho mọi request hay chỉ các chuỗi phụ thuộc? Nêu cách đo p95 và yêu cầu nhất quán giúp quyết định.

## 15. Tổng kết

Trong Neo4j Java Driver, **bookmark** giúp một transaction tiếp theo quan sát được trạng thái mà transaction trước đã commit, ngay cả khi giao dịch đọc được định tuyến sang server khác trong cụm. Driver tự quản lý chuỗi bookmark trong **một Session** và qua **executableQuery()** có manager mặc định; giữa các session hoặc service độc lập, ứng dụng phải **chuyển bookmark** hoặc **dùng chung BookmarkManager** khi có phụ thuộc thật.

Kết nối cụm cần **URI routing** thuộc nhóm **neo4j://** (thường **neo4j+s://** trong môi trường TLS chuẩn), xác định **database**, dùng **executeRead** cho đọc và **executeWrite** cho ghi, giữ Driver lâu dài nhưng đóng Session đúng lúc. Bookmark bảo đảm **thứ tự nhân quả** cho công việc được liên kết, không thay thế ACID, constraint, chống lost update, cache invalidation hoặc đồng bộ dữ liệu giữa các database độc lập.

### Tài liệu chính thức

- [Neo4j Java Driver Manual – Coordinate parallel transactions (bookmarks)](https://neo4j.com/docs/java-manual/current/bookmarks/)
- [Neo4j Java Driver Manual – Connect to the database and cluster](https://neo4j.com/docs/java-manual/current/connect/)
- [Neo4j Java Driver Manual – Advanced connection information](https://neo4j.com/docs/java-manual/current/connect-advanced/)
- [Neo4j Java Driver Manual – Run your own transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual – Performance recommendations](https://neo4j.com/docs/java-manual/current/performance/)
- [Neo4j Java Driver Manual – Upgrade from older versions](https://neo4j.com/docs/java-manual/current/upgrade/)
- [Neo4j Java Driver API – SessionConfig.Builder](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/SessionConfig.Builder.html)
- [Neo4j Java Driver API – BookmarkManagers](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/BookmarkManagers.html)
- [Neo4j Operations Manual – Leadership and routing](https://neo4j.com/docs/operations-manual/current/clustering/setup/routing/)
