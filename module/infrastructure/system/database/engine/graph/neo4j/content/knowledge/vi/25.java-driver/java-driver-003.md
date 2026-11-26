# Vòng đời Driver, session và lựa chọn cơ sở dữ liệu

## 1. Tại sao vòng đời kết nối lại quan trọng trong Neo4j?

Ứng dụng Java truy vấn Neo4j theo mô hình property graph: node, relationship, label, type và property. Dù truy vấn là `MATCH`, `MERGE`, tìm đường đi bằng Cypher hay nhập hàng nghìn bản ghi, **vòng đời của Java Driver, Session và Transaction** quyết định hiệu năng, khả năng phục hồi và độ tin cậy.

Ba sai lầm phổ biến:

- Mỗi HTTP request tạo một `Driver` mới, lãng phí pool và các chi phí thiết lập kết nối.
- Một `Session` được chia sẻ giữa nhiều thread, gây nguy cơ xung đột trạng thái giao dịch hoặc cursor.
- Ứng dụng bỏ qua tên database, khiến truy vấn đi tới home database không đúng với môi trường hoặc tenant.

Trong mô-đun `DATABASE_ENGINE_GRAPH_NEO4J`, bài thuộc chương **Java Driver**, giải thích **vòng đời Driver, session và lựa chọn cơ sở dữ liệu**, đồng thời liên hệ tới index, constraint, Spring Data Neo4j và việc chạy truy vấn trên cluster.

Sau bài học, bạn có thể xác định **ai tạo/đóng Driver**, khi nào mở/đóng **Session**, cách dùng `executeRead`/`executeWrite`, cách truyền tên database bằng `SessionConfig`, lý do sử dụng URI routing và khi nào bookmark cần thiết.

> **Phạm vi code:** Java 17+ và API đồng bộ của **Neo4j Java Driver 5.x** (`org.neo4j.driver`). Các thế hệ mới giữ khái niệm tương tự nhưng cần đối chiếu API với phiên bản Driver và Neo4j server thật. Các ví dụ `readTransaction`/`writeTransaction` cũ đã được thay thế bằng `executeRead`/`executeWrite`.

## 2. Bốn tầng tài nguyên

~~~mermaid
flowchart TD
  A["Application / Spring Boot"] --> B["Driver dùng chung"]
  B --> C["Connection pool + routing"]
  B --> D["Session cho request A"]
  B --> E["Session cho request B"]
  D --> F["Transaction: executeRead / executeWrite"]
  E --> G["Transaction khác"]
  F --> H["Result → Record / Summary"]
  H --> I["Đọc dữ liệu và ánh xạ thành DTO"]
  I --> J["Đóng session"]
  A --> K["Shutdown: đóng Driver"]
~~~

| Thành phần | Trách nhiệm | Tính an toàn luồng | Thời gian sống |
|---|---|---|---|
| **Driver** | Tạo kết nối, quản lý pool, TLS, auth, routing metadata | **Thread-safe** | Dùng chung lâu dài theo cấu hình kết nối/credentials |
| **Session** | Chọn database, access mode, bookmark và khởi tạo transaction | **Không thread-safe** | Một request, job hoặc đơn vị công việc ngắn |
| **Transaction** | Gom các thao tác để commit/rollback nhất quán | Không chia sẻ đồng thời giữa thread | Vừa đủ cho một thao tác nghiệp vụ |
| **Result** | Cursor/luồng các `Record` từ query | Phụ thuộc transaction/session | Đọc và chuyển dữ liệu trước khi đóng tài nguyên |

**Driver không phải một connection TCP đơn lẻ.** Nó quản lý connection pool và có thể phục vụ nhiều Session; tạo một Session mới không nhất thiết mở ngay một connection mới. Đóng Session không có nghĩa đóng Driver.

**Session không phải transaction kéo dài cả ngày.** Mỗi Session có thể chạy nhiều transaction lần lượt, nhưng các transaction đó độc lập về commit/rollback. Nếu nghiệp vụ phải tạo node và relationship cùng thành công hoặc cùng thất bại, hãy đặt trong **một transaction**.

**Result không phải dữ liệu độc lập.** Trả một `Result` chưa được tiêu thụ ra khỏi `try-with-resources` chứa Session là lỗi vòng đời. Chuyển thành `List<DTO>`, `Optional<DTO>` hoặc giá trị nguyên thủy trong phạm vi session.

## 3. Khởi tạo Driver đúng cách

### 3.1. Dependency

Ví dụ khai báo Maven cho ứng dụng không được Spring Boot quản lý dependency:

~~~xml
<dependency>
  <groupId>org.neo4j.driver</groupId>
  <artifactId>neo4j-java-driver</artifactId>
  <version>5.x.y</version>
</dependency>
~~~

`5.x.y` là **ký hiệu** để chọn bản phát hành phù hợp, không phải phiên bản Maven hợp lệ để sao chép nguyên xi. Trong Spring Boot, ưu tiên BOM và cơ chế quản lý dependency của framework để tránh xung đột Java Driver/SDN.

### 3.2. Chương trình console: một Driver cho toàn thời gian chạy

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;

public final class Bootstrap {
    public static void main(String[] args) {
        String uri = requireEnv("NEO4J_URI");
        String username = requireEnv("NEO4J_USERNAME");
        String password = requireEnv("NEO4J_PASSWORD");

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(username, password))) {
            driver.verifyConnectivity();
            System.out.println("Neo4j reachable");
            // Tạo nhiều Session khác nhau trên cùng Driver.
        }
    }

    static String requireEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing env: " + key);
        }
        return value;
    }
}
~~~

`verifyConnectivity()` giúp phát hiện sớm sự cố địa chỉ, xác thực hoặc kết nối. Nhưng **không đảm bảo** việc truy cập database cụ thể có quyền đầy đủ, và cũng không đảm bảo mạng sẽ luôn ổn định trong các request sau.

Trong web server, Driver nên được tạo **khi ứng dụng khởi động** và được đóng **khi ứng dụng dừng**. Không tạo/đóng Driver trong mỗi controller method hoặc mỗi truy vấn repository.

### 3.3. URI, TLS và routing

| URI | Ý nghĩa | Trường hợp |
|---|---|---|
| `neo4j://host:7687` | Driver sử dụng cơ chế routing | Topology có router/cluster; deployment hỗ trợ routing |
| `bolt://host:7687` | Kết nối trực tiếp vào endpoint được chỉ định | Direct server theo chủ đích |
| `neo4j+s://...` | Routing với TLS xác thực chứng chỉ tin cậy | Phù hợp production với chứng chỉ hợp lệ |
| `bolt+s://...` | Direct với TLS xác thực chứng chỉ | Direct endpoint bảo mật |
| `neo4j+ssc://...` | TLS chấp nhận chứng chỉ tự ký | Chỉ dùng khi đã đánh giá vấn đề trust, chủ yếu môi trường test |

Chọn URI dựa trên topology và chính sách TLS. Trong routing mode, Driver có thể sử dụng server đọc/ghi khác nhau dựa trên transaction type và access mode. `bolt://` kết nối endpoint cụ thể, không tự biến thành cơ chế routing cluster chỉ vì tồn tại nhiều server.

**Driver trỏ tới DBMS/cluster; Session mới chọn database.** Đây là hai lớp cấu hình khác nhau.

## 4. Connection pool và khi nào nên điều chỉnh

Driver chia sẻ pool để nhiều Session có thể thực hiện query đồng thời. Ứng dụng thường có **một Driver cho cùng endpoint và bộ credentials**, không có nghĩa chỉ có một transaction chạy tại một thời điểm.

Ví dụ cấu hình pool:

~~~java
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.Config;

Config config = Config.builder()
    .withMaxConnectionPoolSize(50)
    .withConnectionAcquisitionTimeout(30, TimeUnit.SECONDS)
    .build();
~~~

Sau đó truyền `config` cho `GraphDatabase.driver(uri, token, config)`. Các số 50 và 30 chỉ dùng để minh họa; phải đo tải, thời gian truy vấn, khả năng server và số request đồng thời trước khi thay đổi.

| Quan sát | Khả năng | Hành động trước khi tăng pool |
|---|---|---|
| Chờ acquire connection lâu | Pool đầy, giữ Session lâu, query chậm | Kiểm tra close/consume và thời gian transaction |
| Nhiều connection nhưng CPU server bão hòa | Query/locking là giới hạn | `EXPLAIN`/`PROFILE`, tối ưu Cypher và concurrency |
| Tạo Driver ở mỗi request | Pool không được tái sử dụng | Chuyển sang singleton/application-scoped Driver |
| Session không được đóng khi exception | Leak tài nguyên hoặc cursor | Sử dụng `try-with-resources` |

Pool lớn hơn có thể làm tăng tranh chấp khóa, CPU hoặc memory trên server; **không** tự giúp một `MATCH` thiếu index chạy nhanh.

## 5. Chọn database bằng SessionConfig

Thay vì dùng ngầm home database:

~~~java
try (var session = driver.session()) {
    // Database được xác định theo home/default database của user.
}
~~~

hãy chỉ rõ database:

~~~java
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

String database = System.getenv().getOrDefault(
    "NEO4J_DATABASE", "neo4j"
);

try (Session session = driver.session(
        SessionConfig.forDatabase(database))) {
    session.run("RETURN 1 AS ok").consume();
}
~~~

**Vì sao chọn tường minh?**

- Một DBMS có thể chứa nhiều database; home database của user không nhất thiết là database ứng dụng cần.
- Khi không nêu database, Driver có thể phải phân giải home database, làm tăng round trip tùy topology.
- Khi deploy sang môi trường khác, app có thể đọc dữ liệu sai nếu home/default database thay đổi.
- Truy vấn chạy tới database không tồn tại hoặc user không được quyền vẫn sẽ thất bại; `SessionConfig` **không cấp quyền**.

`"neo4j"` thường là tên database mặc định trong deployment cơ bản nhưng không phải quy tắc cố định. Với môi trường multi-tenant, ánh xạ **tenant đã xác thực → database được cho phép** từ cấu hình đáng tin cậy; không chuyển thẳng tham số HTTP tự do thành tên database.

### Kiểm tra database khả dụng

~~~cypher
SHOW DATABASES
YIELD name, currentStatus
RETURN name, currentStatus
ORDER BY name;
~~~

Việc liệt kê phụ thuộc quyền và edition. Dùng Session đã chọn đúng database để chạy `RETURN 1` hoặc một truy vấn đọc có kiểm soát. `verifyConnectivity()` chỉ là kiểm tra kết nối DBMS, không phải kiểm thử truy vấn nghiệp vụ trên database đích.

## 6. Access mode không phải quyền bảo mật

Trên Driver 5.x, có thể đặt mục đích truy vấn đọc khi tạo Session:

~~~java
import org.neo4j.driver.AccessMode;
import org.neo4j.driver.SessionConfig;

SessionConfig readConfig = SessionConfig.builder()
    .withDatabase("neo4j")
    .withDefaultAccessMode(AccessMode.READ)
    .build();

try (var session = driver.session(readConfig)) {
    long n = session.run("""
        MATCH (c:QA003Customer)
        RETURN count(c) AS n
        """).single().get("n").asLong();
    System.out.println(n);
}
~~~

`AccessMode.READ` là **routing hint**; nó không phải tường lửa bảo mật và không thay thế quyền Neo4j. Cấu hình role ở server vẫn quyết định có thể đọc/ghi nhãn, relationship, property hay database nào.

Trong nghiệp vụ thông thường, hai phương thức **managed transaction** thường diễn đạt ý định rõ hơn:

- `session.executeRead(...)` — query đọc; Driver có thể chọn tuyến đọc trong routing mode.
- `session.executeWrite(...)` — query ghi; Driver có thể chọn tuyến ghi trong routing mode.

Không dùng `AccessMode.READ` để giả định một tài khoản có quyền ghi chắc chắn bị ngăn ghi; hãy cấp role đúng ở Neo4j.

## 7. Managed transaction và tự động retry

~~~java
session.executeRead(tx -> {
    // Đọc trong một transaction do Driver quản lý.
    return tx.run("RETURN 41 + 1 AS answer")
             .single().get("answer").asLong();
});

session.executeWrite(tx -> {
    // Ghi trong một transaction do Driver quản lý.
    tx.run("""
        MERGE (:QA003Tag {code: 'java'})
        """).consume();
    return null;
});
~~~

Driver mở transaction, commit/rollback theo kết quả và có thể **retry transaction function** khi gặp lỗi transient phù hợp. Điều này giúp xử lý một số tình huống failover hoặc tranh chấp tạm thời.

**Không gửi email, gọi payment API hay publish event không idempotent bên trong transaction callback.** Function có thể được thực hiện nhiều lần, trong khi side effect bên ngoài Neo4j không được rollback theo transaction graph.

Dùng tham số thay vì nối input vào Cypher:

~~~java
import org.neo4j.driver.Values;

try (var session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    session.executeWrite(tx -> {
        tx.run("""
            MERGE (c:QA003Customer {customerId: $id})
            SET c.name = $name
            """, Values.parameters(
                "id", "C001", "name", "An"
            )).consume();
        return null;
    });
}
~~~

`MERGE` cùng uniqueness constraint trên `customerId` giúp tạo hành vi idempotent hơn `CREATE` khi client/transaction retry, nhưng vẫn phải thiết kế quy tắc nghiệp vụ rõ ràng, đặc biệt khi cập nhật nhiều node và relationship.

## 8. Auto-commit và explicit transaction

### Auto-commit: session.run

~~~java
try (var session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    var result = session.run(
        "RETURN $v + 1 AS next",
        Values.parameters("v", 41)
    );
    long next = result.single().get("next").asLong();
    // next = 42
}
~~~

`session.run` tạo **implicit transaction**. Đọc hết record hoặc gọi `consume()` khi không cần kết quả để đảm bảo câu lệnh hoàn tất. Đừng chỉ gọi `session.run(...)` rồi bỏ cursor mà không tiêu thụ.

Implicit transaction không có cơ chế managed retry tương tự `executeRead/executeWrite`. Một số câu Cypher như `CALL { ... } IN TRANSACTIONS` phải chạy dưới implicit transaction, không nằm bên trong managed/explicit transaction.

### Explicit transaction: tự commit

~~~java
try (var session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    try (var tx = session.beginTransaction()) {
        tx.run("""
            MERGE (:QA003Customer {customerId: $id})
            """, Values.parameters("id", "C900")
        ).consume();
        tx.commit();
    }
}
~~~

Transaction chứa các query của một nghiệp vụ. Nếu đóng transaction mà chưa commit, nó sẽ được rollback theo cơ chế của Driver. Với explicit transaction, ứng dụng phải tự xử lý các tình huống retry cần thiết. Không giữ transaction mở trong khi chờ người dùng, gọi HTTP bên ngoài hay thực hiện I/O không liên quan.

### Hai transaction trong một session không phải một transaction

~~~java
try (var session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    long before = session.executeRead(tx ->
        tx.run("MATCH (c:QA003Customer) RETURN count(c) AS n")
          .single().get("n").asLong()
    );

    session.executeWrite(tx -> {
        tx.run("""
            MERGE (:QA003Customer {customerId: 'C002'})
            """).consume();
        return null;
    });

    long after = session.executeRead(tx ->
        tx.run("MATCH (c:QA003Customer) RETURN count(c) AS n")
          .single().get("n").asLong()
    );
}
~~~

Các giá trị `before`, `after` thuộc các transaction khác nhau, có thể chịu ảnh hưởng từ ghi đồng thời của client khác. Nếu phải kiểm tra và ghi nguyên tử, gộp vào một transaction phù hợp.

## 9. Result và summary: xử lý khi session còn mở

**Anti-pattern:** trả `Result` ra khỏi session đã đóng:

~~~java
// SAI: không áp dụng trong code thật.
static org.neo4j.driver.Result badQuery(Driver driver) {
    try (var session = driver.session(
            SessionConfig.forDatabase("neo4j"))) {
        return session.run("MATCH (n) RETURN n LIMIT 10");
    }
}
~~~

Đúng hơn là chuyển record thành một cấu trúc độc lập trong session:

~~~java
static java.util.List<String> listCustomerIds(
        Driver driver, String database) {
    try (var session = driver.session(
            SessionConfig.forDatabase(database))) {
        return session.executeRead(tx ->
            tx.run("""
                MATCH (c:QA003Customer)
                RETURN c.customerId AS id
                ORDER BY id
                """)
              .list(record -> record.get("id").asString())
        );
    }
}
~~~

Với query ghi, dùng `consume()` để nhận `ResultSummary` và counter:

~~~java
try (var session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    session.executeWrite(tx -> {
        var summary = tx.run("""
            MERGE (:QA003Tag {code: 'java'})
            """).consume();
        System.out.println(
            "Created: " + summary.counters().nodesCreated()
        );
        return null;
    });
}
~~~

`nodesCreated()` là số node tạo **trong lần thực thi câu lệnh**, không phải tổng node hiện có. Nếu callback bị retry, logging bên trong callback có thể xuất hiện nhiều lần, dù chỉ một transaction cuối cùng commit.

## 10. Thực hành: một dataset có đáp án

### Bước 1 — Chuẩn bị database test

Các lệnh dưới đây **chỉ dùng trong database thực hành** và chỉ khi không có dữ liệu thật cùng label `QA003Customer`. Nếu đã chạy bài trước đó, dọn fixture rồi tạo unique constraint:

~~~cypher
DROP CONSTRAINT qa003_customer_id IF EXISTS;
~~~

~~~cypher
MATCH (c:QA003Customer)
DETACH DELETE c;
~~~

~~~cypher
CREATE CONSTRAINT qa003_customer_id IF NOT EXISTS
FOR (c:QA003Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

~~~cypher
UNWIND [
  {id:'C001', name:'An'},
  {id:'C002', name:'Binh'},
  {id:'C003', name:'Chi'}
] AS row
MERGE (c:QA003Customer {customerId: row.id})
SET c.name = row.name;
~~~

Kiểm tra:

~~~cypher
MATCH (c:QA003Customer)
RETURN count(c) AS total,
       count(DISTINCT c.customerId) AS distinctIds;
~~~

**Đáp án:** `total = 3`, `distinctIds = 3`.

### Bước 2 — Chương trình Java end-to-end

Thiết lập environment `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` và `NEO4J_DATABASE` (nếu database không tên `neo4j`).

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;

public class CustomerDemo {
    public static void main(String[] args) {
        String uri = env("NEO4J_URI");
        String user = env("NEO4J_USERNAME");
        String password = env("NEO4J_PASSWORD");
        String db = System.getenv().getOrDefault(
            "NEO4J_DATABASE", "neo4j"
        );

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(user, password))) {
            driver.verifyConnectivity();

            upsert(driver, db, "C001", "An cap nhat");
            String name = readName(driver, db, "C001");
            System.out.println("Customer C001 = " + name);
        }
    }

    static void upsert(Driver driver, String db,
                       String id, String name) {
        try (Session session = driver.session(
                SessionConfig.forDatabase(db))) {
            session.executeWrite(tx -> {
                tx.run("""
                    MERGE (c:QA003Customer {customerId: $id})
                    SET c.name = $name
                    """, Values.parameters(
                        "id", id, "name", name
                    )).consume();
                return null;
            });
        }
    }

    static String readName(Driver driver, String db, String id) {
        try (Session session = driver.session(
                SessionConfig.forDatabase(db))) {
            return session.executeRead(tx ->
                tx.run("""
                    MATCH (c:QA003Customer {customerId: $id})
                    RETURN c.name AS name
                    """, Values.parameters("id", id))
                  .single().get("name").asString()
            );
        }
    }

    static String env(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing env: " + name);
        }
        return value;
    }
}
~~~

**Đầu ra dự kiến:**

~~~text
Customer C001 = An cap nhat
~~~

Sau đó chạy Cypher kiểm chứng:

~~~cypher
MATCH (c:QA003Customer)
RETURN c.customerId AS id, c.name AS name
ORDER BY id;
~~~

| id | name |
|---|---|
| C001 | An cap nhat |
| C002 | Binh |
| C003 | Chi |

**Vì sao đúng 3 node?** `MERGE` theo `customerId` khớp C001 và chỉ cập nhật `name`, không tạo node mới. Chạy ứng dụng thêm lần nữa vẫn ra ba node. Nếu thêm C004 mới, tổng tăng thành 4.

### Bước 3 — Chọn database khác

Trong triển khai có nhiều database, dùng:

~~~java
try (var session = driver.session(
        SessionConfig.forDatabase("some_database"))) {
    long count = session.executeRead(tx ->
        tx.run("""
            MATCH (c:QA003Customer)
            RETURN count(c) AS n
            """).single().get("n").asLong()
    );
    System.out.println(count);
}
~~~

`some_database` chỉ là placeholder; phải thay bằng database thực tồn tại và được phép. Không giả định database khác có ba khách hàng giống fixture. Nếu không có quyền hoặc sai tên, xử lý lỗi rõ ràng thay vì tự động chuyển sang database mặc định.

## 11. Bookmark và tính nhất quán nhân quả trên cluster

Trong cluster, một transaction ghi có thể commit tại server ghi trong khi replica đọc cần thời gian áp dụng dữ liệu. Nếu một request khác đọc ngay sau ghi, ứng dụng đôi lúc cần đảm bảo **read-your-writes** xuyên session.

**Bookmark** mang thông tin tiến độ giao dịch, giúp transaction đọc sau đợi tới mốc dữ liệu cần thiết khi được truyền bookmark phù hợp. Java Driver hỗ trợ bookmark management, ví dụ:

~~~java
import org.neo4j.driver.BookmarkManager;
import org.neo4j.driver.BookmarkManagers;
import org.neo4j.driver.SessionConfig;

BookmarkManager manager = BookmarkManagers.defaultBookmarkManager();

SessionConfig config = SessionConfig.builder()
    .withDatabase("neo4j")
    .withBookmarkManager(manager)
    .build();
~~~

Các session dùng chung manager theo một workflow có thể nhận quan hệ nhân quả phù hợp. **Không vô điều kiện chia sẻ một manager cho mọi tenant/request** vì chúng không nhất thiết cùng chuỗi phụ thuộc, và có thể tạo độ trễ chờ không cần thiết.

Bookmark không phải credential, không cấp quyền truy cập database, không đảm bảo mọi truy vấn giữa các database khác nhau có cùng trạng thái và không thay thế transaction/constraint.

## 12. Spring Boot và Spring Data Neo4j

Với Spring Data Neo4j, Spring Boot có thể tự tạo và quản lý `Driver` bean; cấu hình kết nối thường có dạng:

~~~properties
spring.neo4j.uri=neo4j+s://db.example.com:7687
spring.neo4j.authentication.username=provided-by-deployment
spring.neo4j.authentication.password=provided-by-secret-store
spring.data.neo4j.database=neo4j
~~~

**Hai dòng credential trên là placeholder minh họa**, không phải khuyến nghị hardcode tài khoản/mật khẩu. Trong production, cấu hình secret qua environment hoặc secret manager của deployment. Kiểm tra tên property theo đúng Spring Boot/SDN version; `spring.data.neo4j.database` là lựa chọn phổ biến để chỉ định database cho SDN.

Quy tắc tích hợp:

- Nếu Spring đã cấu hình `Driver`, dùng lại bean đó; không tự tạo Driver trong mỗi controller hoặc repository.
- Repository và `Neo4jClient` thích hợp cho thao tác dữ liệu qua Spring Data Neo4j.
- `@Transactional` của Spring quản lý transaction theo cơ chế Spring/SDN. Một lời gọi `driver.session().executeWrite(...)` tự mở transaction khác, **không tự gộp** vào transaction của repository.
- Một `@Service` singleton có thể giữ tham chiếu tới `Driver`, nhưng **không giữ Session chia sẻ**.
- Nếu tự tạo Driver bean, để Spring context đóng đúng một lần khi shutdown; không gọi `driver.close()` trong từng request.

Ví dụ một nghiệp vụ tạo `Order` và relationship `PLACED` cần transaction nguyên tử. Nếu vừa dùng repository trong `@Transactional`, vừa tạo transaction riêng bằng Driver, bạn phải xem lại ranh giới commit vì hai phần có thể không rollback cùng nhau khi một phần lỗi.

## 13. Xử lý lỗi theo đúng lớp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| `verifyConnectivity` thất bại | URI/DNS/TLS/credential/DBMS | Kiểm tra cấu hình mạng, chứng chỉ, auth |
| Driver kết nối được nhưng query database `analytics` lỗi | Sai database, offline hoặc không đủ quyền | Kiểm tra `SessionConfig`, `SHOW DATABASES`, RBAC |
| Timeout acquire connection | Pool quá tải hoặc session/result bị giữ lâu | Dùng try-with-resources, consume đúng, xem latency query |
| `Result` lỗi khi caller đọc | Session đã đóng | Chuyển Record thành DTO/List trước khi return |
| Transaction callback có log/email hai lần | Managed retry sau lỗi transient | Callback chỉ chứa thao tác an toàn khi retry |
| Query chỉ đọc chậm | Index/plan/DB Hits/page cache/server | `EXPLAIN`/`PROFILE`; đừng chỉ tăng pool |
| Không thấy ghi vừa commit khi đọc từ replica | Bookmark/routing chưa đúng | Xem causal consistency, database và trạng thái commit |
| `single()` báo lỗi | Query trả 0 hoặc nhiều hơn 1 record | Kiểm tra dữ liệu, uniqueness và cách xử lý not-found |
| Permission denied | User/role thiếu quyền, không liên quan Driver lifecycle | Cấp quyền tối thiểu cần thiết ở Neo4j |

**Đừng nuốt mọi exception rồi trả HTTP 200.** Với managed transaction, exception làm transaction không commit theo đường xử lý bình thường; với explicit transaction, chỉ gọi `commit()` khi tất cả thao tác đã thành công. Thiết kế retry ở tầng API cần tính tới cả retry của Driver, tránh tác dụng phụ trùng.

## 14. Vòng đời đúng và sai: so sánh nhanh

| Cách làm không nên | Hậu quả | Cách làm đúng |
|---|---|---|
| Tạo `GraphDatabase.driver(...)` trong mỗi query | Mất lợi thế connection pool | Driver dài hạn do application/context quản lý |
| Biến `static Session` dùng chung cho thread | Xung đột session/transaction | Session ngắn hạn cho mỗi đơn vị công việc |
| `driver.session()` mà không biết database | Dùng home database không mong muốn | `SessionConfig.forDatabase(configuredDb)` |
| Trả `Result` ra khỏi `try(Session ...)` | Cursor bị đóng | Ánh xạ thành giá trị/DTO/List khi còn mở |
| Gọi `session.run` rồi bỏ qua Result | Query có thể chưa hoàn tất; giữ tài nguyên | Tiêu thụ hết result hoặc `consume()` |
| Gọi network API ngoài trong `executeWrite` callback | Retry có thể tạo tác dụng phụ trùng | Idempotency hoặc outbox pattern |
| Dùng `AccessMode.READ` như biện pháp security | Không thay thế quyền Neo4j | RBAC và role tối thiểu |
| Tăng connection pool khi query scan nặng | Server càng tranh chấp tài nguyên | Tối ưu index/Cypher, đo CPU/I/O |
| Gọi `driver.close()` sau mỗi request | Các request khác mất connection | Chỉ đóng khi ứng dụng dừng |

## 15. Bài tập có đáp án

**Bài 1 — Ai sống lâu hơn?** Một server nhận 100 HTTP request/s. Có nên tạo 100 Driver mỗi giây?

**Đáp án:** không. Với cùng endpoint/credentials, thường tạo **một Driver dùng chung**. Mỗi request có thể mở Session riêng; không chia sẻ Session đồng thời giữa thread.

**Bài 2 — Chọn cơ sở dữ liệu.** Ứng dụng phải đọc database `sales` nhưng đang gọi `driver.session()`. Sửa ở đâu?

**Đáp án:** `driver.session(SessionConfig.forDatabase("sales"))`, rồi xác minh user có quyền và database đang hoạt động.

**Bài 3 — Result đã đóng.** Một hàm return `Result` từ trong `try (Session session=...)`. Vì sao caller gặp lỗi?

**Đáp án:** Session bị đóng trước khi caller đọc hết cursor. Đọc các record thành `List`/DTO/giá trị nguyên thủy khi session còn mở.

**Bài 4 — Retry transaction.** Có an toàn khi gửi email trong `executeWrite` callback không?

**Đáp án:** không nếu email không idempotent. Transaction function có thể chạy lại; side effect ngoài DB không rollback theo graph. Dùng outbox/idempotency.

**Bài 5 — Đáp án fixture.** Chạy `upsert` cho C001 với tên “An cap nhat”, số node thay đổi thế nào?

**Đáp án:** vẫn **3 node**, tên C001 được cập nhật; C002 và C003 không đổi, với điều kiện đọc/ghi đúng database test.

**Bài 6 — Routing.** Tài khoản đọc được graph, nhưng ứng dụng `neo4j://` dùng `executeRead` và `executeWrite` trên các server khác. Có phải lỗi?

**Đáp án:** không nhất thiết. Cluster routing có thể phân công server đọc/ghi khác nhau. Nếu cần read-after-write xuyên session, xem bookmark.

**Bài 7 — Kết nối thành công nhưng không có quyền.** `verifyConnectivity()` thành công, còn `MATCH` trên `analytics` bị từ chối. Có mâu thuẫn?

**Đáp án:** không. Verify connectivity kiểm tra khả năng kết nối chung; database đích và quyền truy cập vẫn cần xác minh riêng.

## 16. Dọn dữ liệu thực hành

Chỉ chạy trong **database test** đã dùng ở mục 10:

~~~cypher
DROP CONSTRAINT qa003_customer_id IF EXISTS;
~~~

~~~cypher
MATCH (c:QA003Customer)
DETACH DELETE c;
~~~

~~~cypher
MATCH (t:QA003Tag)
DETACH DELETE t;
~~~

Kiểm tra:

~~~cypher
MATCH (n)
WHERE n:QA003Customer OR n:QA003Tag
RETURN count(n) AS remaining;
~~~

**Đáp án:** `remaining = 0`. Những node C900 hoặc `QA003Tag` từ ví dụ transaction khác cũng thuộc fixture và sẽ được dọn. Không chạy nếu các label demo bị chia sẻ với dữ liệu thực tế.

## 17. Tài liệu chính thức và ghi nhớ

- [Neo4j Java Driver Manual — Connect](https://neo4j.com/docs/java-manual/current/connect/): tạo Driver, URI, auth, `verifyConnectivity`.
- [Neo4j Java Driver Manual — Query the database](https://neo4j.com/docs/java-manual/current/query-simple/): Session, query, tham số và xử lý result.
- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/): managed/explicit transaction, retry và commit/rollback.
- [Neo4j Java Driver Manual — Performance recommendations](https://neo4j.com/docs/java-manual/current/performance/): reuse Driver, chỉ định database và tránh lỗi hiệu năng.
- [Neo4j Java Driver Manual — Bookmarks](https://neo4j.com/docs/java-manual/current/bookmarks/): causal consistency giữa các Session.
- [Neo4j Java Driver Manual — Advanced connection information](https://neo4j.com/docs/java-manual/current/connect-advanced/): routing, pool, TLS và timeout.
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/): repository, Neo4jClient và transaction management.

**Tóm lại:** `Driver` dài hạn và thread-safe; `Session` ngắn hạn, không thread-safe; `Transaction` quyết định commit/rollback; `Result` cần được xử lý trước khi đóng kết nối. Luôn **chọn database một cách tường minh** khi nghiệp vụ yêu cầu dữ liệu ở đích xác định. Vòng đời tài nguyên đúng giúp các truy vấn Cypher, index/constraint và hệ thống Java/Spring hoạt động ổn định khi số request tăng.
