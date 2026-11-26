# Phân loại lỗi trình điều khiển, lỗi máy chủ và lỗi tạm thời

Ứng dụng Java kết nối Neo4j có thể thất bại ở nhiều điểm: không mở được kết nối Bolt, thông tin xác thực sai, cú pháp Cypher không hợp lệ, vi phạm constraint, deadlock khi nhiều transaction tranh chấp khóa hoặc máy chủ tạm thời không sẵn sàng. Các lỗi đó cần **cách xử lý khác nhau**. Thử chạy lại một truy vấn sai cú pháp sẽ không giải quyết vấn đề, trong khi từ bỏ ngay sau một lần đổi leader ngắn của cluster có thể khiến ứng dụng kém ổn định.

Bài thuộc chương **Java Driver** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Module sử dụng Neo4j để lưu property graph gồm node, relationship và thuộc tính, truy vấn bằng Cypher, thiết kế index/constraint, nhập dữ liệu và vận hành qua Java Driver hoặc Spring Data Neo4j. Bài tập trung vào **phân loại lỗi, đánh giá có nên retry hay không, quản lý ranh giới giao dịch và quan sát lỗi** trong ứng dụng Java. Ví dụ sử dụng API đồng bộ của Neo4j Java Driver 5.26+/6.x; với phiên bản khác cần đối chiếu tài liệu API tương ứng, đặc biệt các phương thức liên quan đến GQLSTATUS.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **nguồn phát sinh** lỗi (driver/kết nối hay máy chủ) với **khả năng phục hồi** (có thể retry hay cần sửa yêu cầu).
2. Nhận diện các exception phổ biến: `Neo4jException`, `ClientException`, `DatabaseException`, `TransientException`, `ServiceUnavailableException`, `SessionExpiredException`, `AuthenticationException`.
3. Đọc `Neo4jException.code()`, GQLSTATUS và nguyên nhân gốc thay vì phân loại bằng chuỗi `getMessage()`.
4. Biết khi nào dùng `executeRead`/`executeWrite` hoặc `Driver.executableQuery()` để tận dụng retry tự động.
5. Thiết kế thao tác ghi có thể chạy lại an toàn, đặc biệt trong tình huống **không rõ transaction trước đó đã commit hay chưa**.
6. Ghi log, đo số lần lỗi và xử lý sự cố theo nguyên nhân thay vì retry vô hạn.

## 2. Hai trục phân loại: nguồn lỗi và khả năng retry

Trong ngôn ngữ hằng ngày, người ta hay chia lỗi thành “lỗi driver”, “lỗi server” và “lỗi tạm thời”. Cách chia này có một điểm cần làm rõ: **“tạm thời” là đặc tính khả năng phục hồi, không phải một nguồn lỗi thứ ba loại trừ hai nguồn còn lại**.

~~~mermaid
flowchart LR
    A["Ứng dụng Java"] --> B["Neo4j Java Driver"]
    B --> C["Mạng / TLS / Bolt / routing"]
    C --> D["Neo4j Database / cluster"]
    D --> E["Cypher, quyền, constraint,<br/>transaction, tài nguyên"]
    B -.-> F["Lỗi sử dụng API<br/>hoặc trạng thái session/result"]
    C -.-> G["Lỗi kết nối, timeout,<br/>địa chỉ không phù hợp"]
    E -.-> H["Lỗi server trả về<br/>ClientError / TransientError / DatabaseError"]
~~~

| Trục | Nhóm | Ví dụ | Câu hỏi cần trả lời |
|---|---|---|---|
| **Nguồn** | Phía driver/ứng dụng/kết nối | Session đã đóng, lỗi kết nối, certificate không hợp lệ | Có cần sửa cách dùng API, cấu hình hay mạng? |
| **Nguồn** | Phía Neo4j server | Cypher sai, không đủ quyền, deadlock, lỗi trạng thái database | Server báo mã lỗi nào? |
| **Khả năng phục hồi** | **Có thể retry** | Deadlock, leader switch, kết nối gián đoạn có thể hồi phục | Retry ở mức nào, có an toàn cho thao tác này không? |
| **Khả năng phục hồi** | **Không nên retry y nguyên** | Cú pháp sai, credential sai, vi phạm ràng buộc dữ liệu | Phải sửa yêu cầu, dữ liệu hoặc cấu hình nào? |
| **Khả năng phục hồi** | **Cần điều tra** | Lỗi nội bộ database kéo dài, hết dung lượng, cấu hình cluster sai | Có cần can thiệp vận hành trước khi thử lại? |

**Ví dụ chồng lấn:** `TransientException` thường biểu diễn lỗi tạm thời từ server, còn `ServiceUnavailableException` thường xuất hiện khi driver không thể giao tiếp với hệ thống. Cả hai có thể là **retryable** theo API driver dù chúng đến từ những tầng khác nhau.

## 3. Hệ thống exception trong Neo4j Java Driver

Các lớp đáng biết thuộc package `org.neo4j.driver.exceptions`. Phần lớn lỗi Neo4j do driver báo ra đều là các lớp con của `Neo4jException`, một `RuntimeException`.

| Exception / interface | Nguồn hoặc đặc điểm | Hướng xử lý thông thường |
|---|---|---|
| `Neo4jException` | Lớp cha cung cấp thông tin lỗi, gồm mã `code()` khi có | Bắt ở ranh giới truy cập DB, phân loại và ghi log |
| `ClientException` | Yêu cầu/hoạt động không hợp lệ; có thể là phản hồi lỗi từ server hoặc cách sử dụng API sai | Sửa Cypher, quyền, dữ liệu hay vòng đời tài nguyên |
| `DatabaseException` | Server báo vấn đề bên trong database | Quan sát sức khỏe DB, log, tài nguyên, tình trạng cluster |
| `TransientException` | Lỗi tạm thời thường do server phát hiện | Có thể retry có giới hạn khi thao tác an toàn |
| `ServiceUnavailableException` | Driver không giao tiếp được với cluster/server | Kiểm tra kết nối; managed transaction có thể tự retry |
| `SessionExpiredException` | Session không còn đáp ứng điều kiện ban đầu, ví dụ đổi leader | Thực hiện lại tác vụ trên session hợp lệ; tận dụng managed transaction |
| `AuthenticationException` | Đăng nhập thất bại do thông tin xác thực không hợp lệ | Kiểm tra credential và cơ chế xác thực; không retry vô hạn |
| `ResultConsumedException` | Cố sử dụng `Result` không còn hợp lệ hoặc đã tiêu thụ | Sửa vòng đời session/result và vị trí lấy dữ liệu |
| `TransactionNestingException` | Sử dụng transaction lồng nhau không hợp lệ | Sửa cấu trúc gọi transaction |
| `RetryableException` | **Interface marker** cho exception có khả năng giải quyết khi thử lại | Kết hợp với ngữ nghĩa thao tác và cơ chế retry đã cấu hình |

`RetryableException` **không phải lớp lỗi cha** và không có nghĩa là “hãy chạy lại vô điều kiện”. Đó là tín hiệu ở **mức exception**; mã Cypher và quy tắc nghiệp vụ còn quyết định việc retry có an toàn hay không.

Sơ đồ đơn giản hóa các quan hệ quan trọng:

~~~text
RuntimeException
└── Neo4jException
    ├── ClientException
    │   ├── ResultConsumedException
    │   └── TransactionNestingException
    ├── DatabaseException
    ├── TransientException --------- implements RetryableException
    ├── ServiceUnavailableException implements RetryableException
    └── SessionExpiredException ---- implements RetryableException

RetryableException là interface marker, không phải subclass.
~~~

Sơ đồ không cố liệt kê mọi exception trong driver. Tên lớp, constructor và các interface bổ sung có thể thay đổi giữa các phiên bản. Đừng coi toàn bộ `ClientException` là “lỗi xảy ra trong Java client”: **server cũng có thể trả một client error** khi câu Cypher sai.

## 4. Mã lỗi do máy chủ trả về: ba nhóm chính

Neo4j server có **Neo4j status code** (chuỗi thường bắt đầu bằng `Neo.`). Một số ví dụ:

| Nhóm mã server | Ví dụ | Ý nghĩa | Retry nguyên yêu cầu? |
|---|---|---|---|
| `Neo.ClientError.*` | `Neo.ClientError.Statement.SyntaxError` | Cypher có lỗi cú pháp | **Không**; sửa query |
| `Neo.ClientError.*` | Lỗi quyền hoặc constraint | Người dùng thiếu quyền hoặc dữ liệu vi phạm quy tắc | **Không** nếu chưa sửa nguyên nhân |
| `Neo.TransientError.*` | `Neo.TransientError.Transaction.DeadlockDetected` | Transaction bị hủy do deadlock | **Có thể**, sau khi transaction trước rollback |
| `Neo.TransientError.*` | `Neo.TransientError.Transaction.LeaderSwitch` | Chuyển leader trong cluster | **Có thể**, sau khi routing/leader ổn định |
| `Neo.DatabaseError.*` | Lỗi xử lý nội bộ database | Server không hoàn thành thao tác | Điều tra trước; không tự coi là retryable |

**Lưu ý:** một lỗi database có thể do tình trạng tạm thời hoặc kéo dài; quyết định retry không nên suy từ việc tên lỗi chứa chữ “database”. Nếu cluster hết dung lượng hoặc database không thể khởi động, lặp request không có giới hạn chỉ làm tăng tải.

Với **Neo4j 5.26+**, server bổ sung đối tượng lỗi theo chuẩn **GQLSTATUS**; ở các tổ hợp driver/server mới, exception có `gqlStatus()`, `statusDescription()`, `classification()` hoặc `rawClassification()`, `diagnosticRecord()` và `gqlCause()`. GQL error classification có thể là:

- `CLIENT_ERROR`: lỗi do yêu cầu/quyền/dữ liệu ở phía client.
- `TRANSIENT_ERROR`: lỗi có khả năng tạm thời.
- `DATABASE_ERROR`: lỗi xuất phát từ trạng thái hoặc xử lý của database.

**Neo4j status code** và **GQLSTATUS** là hai hệ mã khác nhau. GQLSTATUS thường có năm ký tự như `42001` hoặc `50N05`, có thể mô tả nguyên nhân chi tiết hơn. Không gộp chúng thành một trường dữ liệu tùy ý và không tự suy rằng GQLSTATUS nào cũng có sẵn trên server cũ.

## 5. Đọc mã lỗi đúng cách

Ví dụ cố ý gửi query thiếu biểu thức sau `RETURN`:

~~~cypher
MATCH (p:Person) RETURN
~~~

Khi gọi qua Java Driver, đây là **lỗi câu lệnh**. Với server phát hành hỗ trợ mã Neo4j như minh họa, driver có thể trả:

~~~text
Exception: org.neo4j.driver.exceptions.ClientException
Neo4j code: Neo.ClientError.Statement.SyntaxError
~~~

Mã lỗi là cơ sở phân loại ổn định hơn **chuỗi thông báo**, vì mô tả lỗi có thể đổi theo phiên bản, vị trí câu lệnh hoặc ngôn ngữ. Ở Java Driver 6.x:

~~~java
import org.neo4j.driver.exceptions.Neo4jException;

try {
    // Gọi truy vấn qua driver/session.
} catch (Neo4jException e) {
    System.err.println("Neo4j code = " + e.code());
    System.err.println("GQLSTATUS = " + e.gqlStatus());
    System.err.println("Classification = " + e.rawClassification().orElse("UNKNOWN"));
    System.err.println("Description = " + e.statusDescription());
}
~~~

Đoạn mã minh họa việc đọc exception, không phải chương trình độc lập chạy được nếu không thay phần gọi truy vấn. `rawClassification()` trả giá trị dạng `Optional`, vì phân loại GQL không phải lúc nào cũng có.

### Khi nguyên nhân nằm sâu trong chuỗi GQL

Một mã GQLSTATUS có thể đại diện cho nhóm lỗi chung; nguyên nhân chi tiết nằm ở đối tượng `gqlCause()`. Nếu cần xử lý một mã cụ thể, Java Driver mới hỗ trợ:

~~~java
catch (Neo4jException e) {
    if (e.containsGqlStatus("42001")) {
        // Ví dụ: lỗi cú pháp, cần sửa câu truy vấn.
        System.err.println("Invalid Cypher syntax");
    } else {
        System.err.println("Neo4j code: " + e.code());
    }
}
~~~

Không phân loại lỗi bằng việc tìm một từ trong `getMessage()`, ví dụ `contains("deadlock")`. Đồng thời, mã GQLSTATUS `50N42` là **mã mặc định** khi server chưa cung cấp object lỗi GQL cụ thể; không xây nghiệp vụ phụ thuộc mã mặc định này. API GQL và tập mã có thể thay đổi theo bộ phiên bản Neo4j/driver; khi ứng dụng cần hỗ trợ nhiều phiên bản, hãy có nhánh fallback qua `code()` và loại exception.

## 6. Quy trình phân loại lỗi trong ứng dụng Java

~~~mermaid
flowchart TD
    A["Một truy vấn Neo4j thất bại"] --> B{"Bị lỗi ở tầng nào?"}
    B -->|"Driver / mạng"| C["Kiểm tra URI, TLS, auth, routing,<br/>trạng thái session/result"]
    B -->|"Server trả lỗi"| D["Đọc code + GQLSTATUS<br/>và cause khi có"]
    C --> E{"RetryableException?"}
    D --> E
    E -->|"Không"| F["Sửa query/dữ liệu/quyền/cấu hình;<br/>không retry nguyên request"]
    E -->|"Có"| G{"Thao tác có thể chạy lại an toàn?"}
    G -->|"Không rõ"| H["Kiểm tra trạng thái commit;<br/>xử lý bằng khóa idempotency"]
    G -->|"Có"| I["Dùng managed transaction<br/>hoặc retry có giới hạn"]
    I --> J{"Hết lỗi?"}
    J -->|"Có"| K["Trả kết quả"]
    J -->|"Không"| L["Ghi log, cảnh báo,<br/>đưa lỗi lên tầng gọi"]
~~~

Trước khi quyết định retry, trả lời ba câu:

1. **Lỗi có khả năng tự hết không?** Deadlock sau rollback thường đáng thử lại; query sai cú pháp thì không.
2. **Driver đã tự retry chưa?** Gọi `executeWrite` có cơ chế retry riêng; bọc bên ngoài một vòng `while(true)` rất dễ tạo số lần thử quá lớn.
3. **Chạy lại yêu cầu có an toàn không?** Một lần lỗi kết nối ngay lúc commit có thể khiến ứng dụng **không biết** thay đổi đã được ghi hay chưa.

## 7. Managed transaction: cách retry được khuyến nghị

Java Driver cung cấp `Session.executeRead(...)` và `Session.executeWrite(...)` để chạy **managed transaction**. Khi lỗi được driver coi là tạm thời và còn trong thời gian retry cho phép, driver có thể chạy lại **toàn bộ callback** trên transaction mới. `Driver.executableQuery()` cũng cung cấp cơ chế retry cho truy vấn được quản lý.

Ví dụ ghi khách hàng theo **khóa nghiệp vụ cố định**:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

~~~java
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Config;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.exceptions.Neo4jException;

public class CustomerRepository implements AutoCloseable {
    private final Driver driver;
    private final String database;

    public CustomerRepository(
            String uri, String user, String password, String database) {
        Config config = Config.builder()
                .withMaxTransactionRetryTime(30, TimeUnit.SECONDS)
                .build();
        this.driver = GraphDatabase.driver(
                uri, AuthTokens.basic(user, password), config);
        this.database = database;
        driver.verifyConnectivity();
    }

    public void upsertCustomer(String customerId, String name) {
        try (Session session = driver.session(
                SessionConfig.builder().withDatabase(database).build())) {
            session.executeWrite(tx -> {
                tx.run("""
                    MERGE (c:Customer {customerId: $customerId})
                    SET c.name = $name
                    """,
                    Map.of("customerId", customerId, "name", name)
                ).consume();
                return null;
            });
        } catch (Neo4jException e) {
            // Lỗi vẫn còn sau cơ chế retry hoặc thuộc nhóm không retry.
            System.err.println("Customer upsert failed; code=" + e.code());
            throw e;
        }
    }

    @Override
    public void close() {
        driver.close();
    }
}
~~~

Điểm quan trọng của ví dụ:

- `Driver` được tạo và dùng lại trong vòng đời thành phần; một `Session` ngắn được tạo cho mỗi thao tác. `Driver` dùng được giữa nhiều thread, còn `Session` **không** thread-safe.
- `MERGE` theo `customerId` giúp thao tác **có khả năng chạy lại mà không tạo node mới liên tục**. Uniqueness constraint bảo đảm không có hai node cùng khóa.
- `.consume()` giúp tiêu thụ kết quả của lệnh ghi **trong callback** để phát hiện lỗi của truy vấn trước khi thoát callback.
- `.withMaxTransactionRetryTime(30, TimeUnit.SECONDS)` giới hạn khoảng thời gian driver được phép retry managed transaction. Đây không phải timeout cho **mỗi** Cypher query và không phải đảm bảo request sẽ thành công.
- Nếu callback ném lỗi không retryable hoặc hết thời gian retry, exception được trả lên cho tầng gọi; code bên ngoài cần log và xử lý theo chính sách nghiệp vụ.
- Ví dụ giả định `customerId` và `name` khác `null`; `Map.of` không cho phép giá trị null. Ứng dụng phải kiểm tra input trước khi gọi repository.

**Không thực hiện tác động bên ngoài trong callback retry** như gọi API thanh toán, gửi email, ghi một file một lần, cập nhật số đếm trong biến toàn cục. Callback có thể chạy **nhiều lần** dù ứng dụng chỉ gọi `executeWrite` một lần. Nếu cần một tác động bên ngoài, hãy thiết kế **outbox/idempotency** hoặc thực hiện sau commit theo quy trình riêng.

### Sự khác nhau giữa các API transaction

| Cách chạy | Retry mặc định | Điểm cần nhớ |
|---|---|---|
| `session.executeRead(...)` | Driver retry với lỗi được coi là transient theo chính sách | Dùng cho transaction đọc |
| `session.executeWrite(...)` | Driver retry có giới hạn với lỗi phù hợp | Callback phải an toàn khi thực thi lại |
| `driver.executableQuery(...)` | Driver xử lý managed transaction/retry | Phù hợp truy vấn đơn giản; chỉ rõ database |
| `session.beginTransaction()`, rồi `commit()` | **Không tự điều phối retry toàn tác vụ** như managed transaction | Người viết tự quản lý vòng đời, rollback, retry |
| `session.run(...)` (implicit/auto-commit) | **Không có cùng bảo đảm retry** như managed transaction | Đặc biệt cẩn trọng với lệnh ghi nhiều transaction |

Từ Java Driver **6.1**, implicit transaction có **một lần retry hạn chế** đối với một tập lỗi mà server đánh dấu là idempotent; trong các phiên bản cũ hoặc hoàn cảnh khác không nên trông đợi cơ chế đó. Cần đặc biệt thận trọng với `CALL { ... } IN TRANSACTIONS` vì một số batch có thể đã commit trước khi toàn bộ truy vấn kết thúc. Không gộp thao tác import nhiều transaction vào một vòng retry mù.

## 8. Retryable không đồng nghĩa với an toàn để retry

Giả sử ứng dụng cần “đặt đơn một lần”:

~~~cypher
CREATE (o:Order {amount: 250000, createdAt: datetime()})
RETURN elementId(o) AS orderId;
~~~

Nếu server đã commit nhưng kết nối đứt **trước khi client nhận phản hồi**, client có thể không biết đơn đã được tạo. Chạy lại câu lệnh `CREATE` sẽ có nguy cơ tạo **hai đơn hàng**.

Hãy xác định **requestId** ở tầng ứng dụng và bảo vệ tính duy nhất:

~~~cypher
CREATE CONSTRAINT order_request_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.requestId IS UNIQUE;
~~~

~~~cypher
MERGE (o:Order {requestId: $requestId})
ON CREATE SET o.amount = $amount,
              o.createdAt = datetime(),
              o.status = 'NEW'
RETURN o.requestId AS requestId,
       o.amount AS amount,
       o.status AS status;
~~~

Sau một lỗi kết nối, ứng dụng có thể **đọc lại theo `requestId`** để phân biệt request đã tạo đơn trước đó hay chưa; nếu chưa có, có thể thử lại trong chính sách có giới hạn. Cách này cũng yêu cầu xử lý trường hợp **cùng `requestId` nhưng nội dung request khác nhau**: không được âm thầm trả dữ liệu của một đơn khác như thành công.

Đối với chuyển tiền hoặc thao tác liên quan nhiều hệ thống, chỉ có `MERGE` trong Neo4j **không đủ** để đạt exactly-once trên toàn bộ hệ thống. Cần giao thức nghiệp vụ phù hợp như idempotency key, outbox, kiểm tra trạng thái từ hệ thống ngoài và đối soát.

### Khi nào retry có thể tạo thêm tải?

| Tình huống | Rủi ro của retry vô hạn | Giải pháp |
|---|---|---|
| Deadlock ngắn | Các luồng liên tục tranh chấp | Retry có backoff/jitter và giảm cạnh tranh khóa nếu cần |
| Database không sẵn sàng kéo dài | Dồn thêm kết nối và yêu cầu | Giới hạn thời gian/số lần, cảnh báo, kiểm tra hạ tầng |
| Cypher sai cú pháp | Cùng một lỗi lặp lại | Sửa câu lệnh, không retry |
| Credential sai | Khóa tài khoản hoặc tạo nhiều lỗi xác thực | Kiểm tra cấu hình/secret |
| Vi phạm uniqueness constraint | Ghi trùng cùng khóa không thể được chấp nhận | Sửa logic tạo và chính sách cập nhật |
| Không rõ commit đã thành công | Tạo trùng dữ liệu hoặc tác động bên ngoài | Đọc trạng thái theo idempotency key trước khi thử lại |

Managed transaction đã có retry và backoff nội bộ. Nếu thêm retry ở API HTTP hoặc job queue, phải **phối hợp ngân sách retry của nhiều tầng**, tránh tổng số lần thử tăng ngoài dự kiến.

## 9. Phân loại và xử lý exception trong mã Java

Nếu chỉ cần một điểm bắt lỗi chung, hãy bắt `Neo4jException` ở **ranh giới repository/service** rồi phân loại bằng exception type và mã lỗi. Mẫu dưới đây dành cho **Java Driver 5.26+/6.x** và giúp biểu diễn chính sách, không tự triển khai vòng retry chồng lên managed transaction:

~~~java
import org.neo4j.driver.exceptions.ClientException;
import org.neo4j.driver.exceptions.DatabaseException;
import org.neo4j.driver.exceptions.Neo4jException;
import org.neo4j.driver.exceptions.RetryableException;
import org.neo4j.driver.exceptions.ServiceUnavailableException;
import org.neo4j.driver.exceptions.SessionExpiredException;

public final class Neo4jErrorPolicy {
    public enum Action {
        FIX_REQUEST, INSPECT_OPERATIONS, RETRY_IF_SAFE
    }

    public static Action classify(Neo4jException error) {
        // Phân biệt dấu hiệu retry ở mức driver với ngữ nghĩa nghiệp vụ.
        if (error instanceof RetryableException) {
            return Action.RETRY_IF_SAFE;
        }
        if (error instanceof ClientException) {
            return Action.FIX_REQUEST;
        }
        if (error instanceof DatabaseException) {
            return Action.INSPECT_OPERATIONS;
        }
        return Action.INSPECT_OPERATIONS;
    }

    public static void report(Neo4jException error) {
        Action action = classify(error);
        System.err.println("exception=" + error.getClass().getSimpleName());
        System.err.println("neo4jCode=" + error.code());
        System.err.println("gqlStatus=" + error.gqlStatus());
        System.err.println("action=" + action);

        // Cần xử lý/raise cho tầng gọi; không được coi log là đã khôi phục.
    }
}
~~~

Đây là một **bộ phân loại tối thiểu**, chưa phải retry engine. Các exception có thể có chính sách đặc biệt theo mã lỗi cụ thể và bối cảnh, ví dụ xác thực token hết hạn có thể cần cập nhật token, trong khi cấu hình mật khẩu sai cần người quản trị sửa.

**Chú ý:** `ServiceUnavailableException` và `SessionExpiredException` là ví dụ của các exception triển khai `RetryableException`. Việc import lớp trong ví dụ nhằm nêu rõ chúng tồn tại; logic chung ưu tiên kiểm tra marker thay vì chỉ kiểm tra hai lớp cụ thể. Với ứng dụng dùng driver cũ hơn 5.0, marker này có thể không có: hãy dùng bảng tương thích API của phiên bản đang chạy.

## 10. Nhận diện bốn kịch bản lỗi phổ biến

### 10.1. Lỗi cú pháp Cypher — sửa câu lệnh

~~~cypher
MATCH (c:Customer)
RETURN
~~~

Đây là ví dụ minh họa mã `Neo.ClientError.Statement.SyntaxError`; cùng query retry 10 lần vẫn sai. Hướng xử lý là kiểm thử/query validation ở môi trường phát triển, bảo vệ tham số khỏi Cypher injection và triển khai bản sửa.

### 10.2. Lỗi constraint — sửa yêu cầu hoặc dữ liệu

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

~~~cypher
CREATE (:Customer {customerId: 'C001', name: 'An'});
CREATE (:Customer {customerId: 'C001', name: 'Binh'});
~~~

Trong database mới, câu thứ hai vi phạm uniqueness constraint. Ứng dụng phải quyết định **từ chối trùng**, **cập nhật theo khóa** hoặc **trả bản ghi đã có**. Không có quy tắc “lỗi trùng → cứ retry” cho mọi nghiệp vụ. Có thể sử dụng `MERGE` theo khóa phù hợp, kèm constraint, nếu chính sách thực sự cho phép upsert.

### 10.3. Deadlock — lỗi server có thể retry

Khi hai transaction ghi vào cùng nhóm node nhưng lấy khóa theo thứ tự ngược nhau, một transaction có thể bị Neo4j hủy để phá deadlock. Một mã lỗi điển hình:

~~~text
Neo.TransientError.Transaction.DeadlockDetected
~~~

Trong managed transaction, driver có thể thực thi lại callback sau rollback. Nếu deadlock tái diễn thường xuyên, cần **giảm mức cạnh tranh, ổn định thứ tự truy cập tài nguyên** và xem xét kích thước transaction. Retry giúp vượt qua lỗi ngắn, không thay việc sửa cấu trúc workload.

### 10.4. Kết nối mất trong lúc ghi — có thể không rõ kết quả commit

Giả sử request gửi đến DB, server commit thành công, nhưng client không nhận được phản hồi do mạng lỗi. Driver có thể báo `ServiceUnavailableException` hoặc exception khác liên quan kết nối. **Không được tự suy** rằng “có exception tức là chưa có dữ liệu”. Trước khi retry từ tầng nghiệp vụ, hãy kiểm tra khóa idempotency/đối soát nếu thao tác có thể đã commit.

Đây là nguyên nhân sâu xa khiến `CREATE` không có khóa nghiệp vụ, gửi email trong transaction callback hoặc ghi số dư sang hệ thống ngoài trở nên nguy hiểm khi có retry.

## 11. Phân biệt timeout và session hết hiệu lực

Các lỗi “timeout” không giống nhau:

| Hiện tượng | Tầng xảy ra | Điều cần kiểm tra |
|---|---|---|
| Kết nối TCP không mở được | Driver/mạng | URI, port Bolt, firewall, TLS và DNS |
| Chờ lấy kết nối từ pool quá lâu | Driver | Pool size, session có được đóng, tải và acquisition timeout |
| Đọc từ connection quá lâu | Driver/mạng | `ConnectionReadTimeoutException`, query kéo dài, đường truyền |
| Transaction bị timeout ở server | Server | Timeout của transaction, khóa chờ, `PROFILE` và workload |
| `SessionExpiredException` | Driver/routing/cluster | Session không còn thỏa điều kiện ban đầu; thay leader hoặc routing thay đổi |

**Không giải quyết mọi timeout bằng cách tăng timeout**. Trước tiên cần biết đang chờ kết nối, chờ khóa, thực thi Cypher hay truyền kết quả. Ví dụ transaction scan toàn bộ graph lớn có thể cần index hoặc viết lại query; tăng timeout chỉ che dấu nút thắt.

Ví dụ thiết lập **timeout giao dịch** tách khỏi **retry budget**:

~~~java
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.Config;
import org.neo4j.driver.TransactionConfig;

Config driverConfig = Config.builder()
        .withMaxTransactionRetryTime(30, TimeUnit.SECONDS)
        .build();

TransactionConfig txConfig = TransactionConfig.builder()
        .withTimeout(Duration.ofSeconds(5))
        .withMetadata(Map.of("operation", "customer-read"))
        .build();

// driverConfig được truyền khi tạo Driver.
// txConfig được truyền vào session.executeRead(callback, txConfig).
~~~

`withMaxTransactionRetryTime` giới hạn tổng thời gian retry của managed transaction; `TransactionConfig.withTimeout` giới hạn thời gian thực thi một transaction theo cơ chế server. Một transaction timeout **không mặc nhiên retryable ở mọi hoàn cảnh**; đọc exception và mã status cụ thể.

## 12. Ghi log và giám sát lỗi có ích

Một log tốt cần trả lời **yêu cầu nào thất bại**, **tại tầng nào**, **mã lỗi nào** và **ứng dụng đã xử lý ra sao**. Tối thiểu nên ghi:

| Thông tin | Mục đích |
|---|---|
| Tên thao tác (`findCustomer`, `createOrder`) | Xác định luồng nghiệp vụ |
| Database, vùng triển khai hoặc service | Xác định nơi lỗi xảy ra |
| Exception class và `code()` | Phân loại ổn định theo driver/server |
| `gqlStatus()`, classification, cause khi có | Chẩn đoán sâu cho driver/server mới |
| Request ID / correlation ID | Ghép log ứng dụng với server log |
| Thời điểm, latency, số lần thử | Phát hiện sự cố kéo dài hoặc retry storm |
| Kết quả kiểm tra idempotency/commit | Tránh ghi trùng khi xử lý lỗi mạng |

**Không log mật khẩu, auth token, thông tin cá nhân, giá trị nhạy cảm trong tham số Cypher hoặc toàn bộ request body.** Chỉ log những khóa/định danh kỹ thuật đã được cho phép. Stacktrace có thể cần trong log nội bộ bảo vệ phù hợp, nhưng không gửi nguyên văn lỗi database về HTTP response cho người dùng cuối.

Với hệ thống Neo4j có cấu hình ghi log query, có thể gắn metadata transaction để liên kết với ứng dụng:

~~~java
TransactionConfig txConfig = TransactionConfig.builder()
        .withMetadata(Map.of(
                "app", "customer-service",
                "operation", "upsert-customer",
                "requestId", requestId))
        .build();
~~~

`requestId` nên là định danh kỹ thuật không chứa bí mật. Metadata có thể xuất hiện trong query log hoặc `SHOW TRANSACTIONS`, nên cũng phải tuân thủ chính sách dữ liệu của hệ thống.

### Chỉ số vận hành nên theo dõi

- Số lỗi theo **loại exception**, **Neo4j code** và **GQL classification**.
- Số yêu cầu cuối cùng thất bại **sau khi driver đã retry**; nếu có thể, đo thêm số lần thử ở tầng quản lý transaction.
- Độ trễ `p95`/`p99` ở repository/endpoint và thời gian chờ pool.
- Tần suất `ServiceUnavailableException`/`SessionExpiredException` trùng với thay đổi trạng thái cluster.
- Deadlock, lock timeout, tỷ lệ rollback và tải hệ thống Neo4j.

Số lỗi ở một tầng không luôn tương đương số request thất bại: một managed transaction có thể gặp lỗi tạm thời rồi thành công sau retry.

## 13. Thực hành kiểm tra phương án xử lý lỗi

Không cần gây lỗi thật trên production. Trong database **thực hành riêng**:

1. **Cú pháp sai:** gọi `MATCH (n) RETURN` và kiểm tra `ClientException`/`code()`, xác nhận ứng dụng không retry nguyên văn.
2. **Constraint:** tạo uniqueness constraint cho `Customer.customerId` rồi thử ghi hai node trùng khóa; thiết kế phản hồi nghiệp vụ rõ ràng.
3. **Managed transaction:** chạy `MERGE` khách hàng qua `executeWrite`, chạy lại cùng tham số; kiểm tra số node không tăng.
4. **Mô phỏng lỗi kết nối:** dùng môi trường thử nghiệm/chaos test được phép để làm gián đoạn kết nối và quan sát exception class, cơ chế retry và độ trễ.
5. **Kiểm tra log:** xác nhận có operation, request ID và status code nhưng không lộ credential hay dữ liệu nhạy cảm.

**Với bài thử kết nối gián đoạn,** nếu không có hạ tầng mô phỏng riêng, chỉ mô tả kịch bản và viết unit test cho bộ phân loại; không cố làm gián đoạn Neo4j đang phục vụ người dùng để “lấy lỗi thực”.

## 14. Các lỗi thiết kế thường gặp

| Sai lầm | Vì sao nguy hiểm? | Cách sửa |
|---|---|---|
| `catch (Exception e) { return null; }` | Nuốt lỗi, biến sự cố DB thành dữ liệu thiếu hợp lệ | Log đúng, chuyển thành lỗi nghiệp vụ phù hợp hoặc ném tiếp |
| Retry mọi `Neo4jException` | Lặp mãi với syntax, quyền, constraint | Phân loại bằng type/status và khả năng retry |
| Retry vô hạn dù driver đã tự retry | Gây bùng nổ tải và độ trễ | Quản lý retry budget giữa các tầng |
| `CREATE` không có khóa định danh rồi retry | Có thể ghi trùng khi commit không rõ | Dùng request ID, constraint, upsert phù hợp |
| Gọi HTTP/email trong `executeWrite` callback | Callback có thể chạy nhiều lần | Tách side effect, dùng outbox/idempotency |
| Dùng `getMessage()` để phân loại | Thông điệp không ổn định | Dùng `code()`, type và GQLSTATUS |
| Dùng lại `Session` sau khi đã đóng hoặc hết hiệu lực | Lỗi trạng thái tài nguyên | Mở session mới cho thao tác thích hợp |
| Chia sẻ `Session` giữa thread | Session không thread-safe | Chia sẻ `Driver`, tạo session riêng |
| Không tiêu thụ `Result` khi cần xác nhận ghi | Lỗi có thể xuất hiện trễ, commit implicit khó quan sát | `consume()`/xử lý hết record trong phạm vi transaction |
| Tăng tất cả timeout khi query chậm | Che dấu vấn đề index/lock/pool/network | Xác định đúng loại timeout, đo nguyên nhân |
| Trả nguyên stacktrace ra REST API | Lộ cấu trúc query và thông tin nội bộ | Mapping sang lỗi API có kiểm soát |

## 15. Bài tập tự luyện

### Bài 1 — Phân loại bốn tình huống

Cho bốn lỗi:

1. `Neo.ClientError.Statement.SyntaxError`.
2. `Neo.TransientError.Transaction.DeadlockDetected`.
3. `ServiceUnavailableException` khi không kết nối được server.
4. `AuthenticationException` khi mật khẩu sai.

Hãy xác định lỗi thuộc tầng nào, có thể thử lại ngay hay phải sửa cấu hình và có cần quan tâm idempotency không.

<details>
<summary>Đáp án tham khảo</summary>

1. Lỗi server phân loại `ClientError`; sửa Cypher, không retry.
2. Lỗi server `TransientError`; có thể retry transaction sau rollback, cần callback an toàn khi chạy lại.
3. Lỗi giao tiếp driver/mạng; có thể hồi phục sau khi server/kết nối sẵn sàng, nhưng phải xét trạng thái commit nếu đang ghi.
4. Lỗi xác thực; phải sửa credential/quyền hoặc cơ chế cấp token; lặp lại cùng thông tin sai không có ích.

</details>

### Bài 2 — Sửa callback thiếu an toàn

~~~java
session.executeWrite(tx -> {
    emailService.sendWelcomeEmail(email);
    tx.run("CREATE (:Customer {email: $email})", Map.of("email", email));
    return null;
});
~~~

Đoạn mã này có rủi ro gì nếu driver tự retry transaction?

<details>
<summary>Gợi ý đáp án</summary>

Callback có thể chạy nhiều lần và gửi nhiều email; `CREATE` cũng có nguy cơ tạo nhiều node nếu gọi lại ở tầng ứng dụng sau khi commit không rõ. Chuyển sang thiết kế có khóa định danh và constraint, ghi dữ liệu/outbox trong transaction, xử lý gửi email qua một worker có khóa idempotency sau commit.

</details>

### Bài 3 — Cùng một exception, quyết định khác nhau

Hai yêu cầu đều gặp `ServiceUnavailableException`:

- Yêu cầu A: đọc danh sách sản phẩm bằng `MATCH`.
- Yêu cầu B: tạo đơn bằng `CREATE` không có `requestId`.

Vì sao không nên retry cả hai bằng cùng một vòng lặp không giới hạn?

<details>
<summary>Gợi ý đáp án</summary>

Đọc thuần không tạo dữ liệu nên thường an toàn hơn để thử lại có giới hạn. Ghi đơn có thể đã commit trước khi kết nối lỗi; retry có thể tạo trùng. Cần định danh yêu cầu, kiểm tra trạng thái commit và thiết kế idempotency cho B. Cả hai đều cần giới hạn retry để không gây quá tải khi hệ thống chưa phục hồi.

</details>

### Bài 4 — Phân biệt API transaction

Bạn đang dùng `session.beginTransaction()` và tự `commit()`; khi deadlock, hệ thống có tự chạy lại toàn bộ chức năng nghiệp vụ như `session.executeWrite()` không?

<details>
<summary>Đáp án</summary>

Không. Explicit transaction cho phép kiểm soát thủ công nhưng không cung cấp cùng cơ chế retry toàn callback như managed transaction. Có thể cần quản lý vòng đời transaction mới và retry ở tầng ứng dụng, với ngân sách và kiểm tra idempotency phù hợp.

</details>

### Bài 5 — Khai thác GQLSTATUS

Ứng dụng hỗ trợ cả Neo4j 5.20 và Neo4j 5.26+, driver mới trả `gqlStatus()`. Có nên chỉ dựa vào một mã GQLSTATUS cụ thể để quyết định lỗi hay không?

<details>
<summary>Đáp án</summary>

Không. Server cũ có thể không cung cấp GQL error object chi tiết. Cần xử lý trường hợp thiếu thông tin, dùng `code()` và exception type làm fallback, đồng thời kiểm tra tương thích driver/server. Không phân nhánh bằng chuỗi thông báo lỗi.

</details>

## 16. Tài liệu chính thức để tra cứu theo phiên bản

- [Neo4j Java Driver Manual — Query error handling và GQLSTATUS](https://neo4j.com/docs/java-manual/current/query-simple/#_error_handling)
- [Neo4j Java Driver Manual — Managed và explicit transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual — Implicit transaction](https://neo4j.com/docs/java-manual/current/query-advanced/)
- [Neo4j Java Driver API — Package exceptions](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/exceptions/package-summary.html)
- [Neo4j Java Driver API — RetryableException](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/exceptions/RetryableException.html)
- [Neo4j — Server errors và classification](https://neo4j.com/docs/status-codes/current/errors/)
- [Neo4j — Danh mục status code](https://neo4j.com/docs/status-codes/current/errors/all-errors/)

Liên kết `current` sẽ thay đổi theo phiên bản mới nhất. Khi nâng cấp, hãy đối chiếu **driver version**, **server version**, những exception thực tế và API tương ứng. Đặc biệt, không sao chép chính sách retry của driver 6.1+ cho các bản driver cũ nếu chưa xác minh.

## 17. Ghi nhớ

- **Nguồn lỗi và khả năng retry là hai trục khác nhau**: lỗi tạm thời có thể phát sinh từ server hoặc tầng kết nối/driver.
- **`Neo4jException.code()`, exception type và GQLSTATUS** đáng tin cậy hơn việc phân tích chuỗi `getMessage()`.
- **`ClientException` thường cần sửa yêu cầu**; `TransientException`, `ServiceUnavailableException` và `SessionExpiredException` có thể retry trong điều kiện thích hợp.
- **`executeRead`, `executeWrite` và `executableQuery` có quản lý retry**; callback cần an toàn khi được chạy lại, còn explicit transaction đòi hỏi kiểm soát thủ công.
- **Lỗi mạng quanh thời điểm commit có thể khiến trạng thái giao dịch chưa rõ**; thiết kế khóa idempotency và đối soát trước khi retry thao tác ghi.
- **Giới hạn retry và quan sát lỗi thực tế** giúp hệ thống phục hồi khi lỗi ngắn mà không làm sự cố kéo dài trở nên nghiêm trọng hơn.
