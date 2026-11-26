# Ẩn dữ liệu nhạy cảm trong log, tham số truy vấn và công cụ giám sát

## 1. Tại sao hệ thống hoạt động đúng vẫn có thể làm lộ dữ liệu?

Neo4j lưu thông tin dưới dạng **property graph**: node, relationship và property. Một truy vấn Cypher có thể đi qua nhiều liên kết rồi trả về thông tin khách hàng, nhân viên, tài khoản, hồ sơ y tế, giao dịch hoặc cấu trúc nội bộ của doanh nghiệp.

Ví dụ, ứng dụng Java tìm khách hàng bằng email:

~~~cypher
MATCH (c:Customer {email: $email})
RETURN c.customerId AS customerId,
       c.status AS status;
~~~

Về mặt nghiệp vụ, câu truy vấn có thể hoàn toàn đúng. Nhưng nếu ứng dụng ghi một bản log như sau, nó đã sao chép email của khách hàng vào **hệ thống log**, nơi có thể có nhóm người dùng, thời gian lưu và quy trình xuất dữ liệu khác database:

~~~text
WARN  Neo4j query failed
query=MATCH (c:Customer {email: $email}) RETURN c
parameters={email: "customer.real@example.invalid"}
error=...
~~~

Ngay cả khi log được lưu trong nội bộ, hậu quả có thể gồm:

- Người không có quyền xem node `Customer` vẫn đọc được email qua dashboard log.
- Log được chuyển tới bên thứ ba hoặc môi trường phân tích rộng hơn.
- Bản sao log được lưu lâu hơn thời gian lưu dữ liệu nguồn.
- Bản tin cảnh báo có đoạn log nhạy cảm được gửi tới email, chat hoặc ticket.
- Truy vấn hỗ trợ sự cố được sao chép vào ảnh chụp màn hình/tài liệu.
- Một thao tác ẩn/xóa dữ liệu trong Neo4j không tự xóa các bản sao đã có trong log.

**Mục tiêu của bài học** là bảo vệ dữ liệu nhạy cảm trên toàn bộ đường đi quan sát hệ thống: **Cypher → Neo4j server → Java Driver/Spring Data Neo4j → log/trace/metric/APM → dashboard, cảnh báo và kho lưu trữ**.

> **Nguyên tắc cốt lõi:** Tham số hóa truy vấn giúp tách dữ liệu ra khỏi văn bản Cypher, nhưng **không đồng nghĩa** giá trị tham số sẽ được che trong mọi loại log, trace hay công cụ giám sát. Cần áp dụng chính sách giảm thiểu, lọc và kiểm soát truy cập ở từng lớp.

## 2. Xác định dữ liệu nào cần được bảo vệ

Không phải mọi property của graph đều có cùng mức nhạy cảm. Trước khi cấu hình logging, cần phân loại trường dữ liệu theo rủi ro.

| Loại dữ liệu | Ví dụ trong graph | Rủi ro nếu xuất hiện trong log |
|---|---|---|
| **Thông tin định danh cá nhân (PII)** | `Person.email`, `phone`, `address`, tên kết hợp thông tin khác | Nhận dạng cá nhân, spam, lừa đảo |
| **Thông tin xác thực/bí mật** | API key, OAuth token, mật khẩu, secret kết nối | Chiếm quyền truy cập; cần xử lý khẩn cấp |
| **Dữ liệu tài chính** | Mã tài khoản, thông tin thanh toán, giao dịch chi tiết | Rò rỉ giao dịch, gian lận |
| **Thông tin sức khỏe/pháp lý** | Chẩn đoán, hồ sơ nhạy cảm, quan hệ tới vụ việc | Ảnh hưởng lớn tới quyền riêng tư |
| **Dữ liệu nội bộ** | Cơ cấu tổ chức, topology, kế hoạch, ID hệ thống | Lộ thông tin doanh nghiệp |
| **Định danh có thể liên kết lại** | `customerId`, `userId`, `orderId` | Có thể trở thành dữ liệu cá nhân khi ghép với nguồn khác |
| **Thông tin vận hành ít nhạy cảm** | Tên operation được duyệt, trạng thái, latency, số hàng tổng hợp | Thường phù hợp hơn cho log/metric |

Một `customerId` trông như mã kỹ thuật vẫn có thể là dữ liệu định danh nếu nội bộ có bảng đối chiếu tới người thật. Không tự động coi mọi giá trị không phải email là “vô hại”.

### 2.1. Câu hỏi phân loại cần trả lời

- Dữ liệu có thể **nhận dạng trực tiếp hoặc gián tiếp** một người không?
- Dữ liệu có dùng để **đăng nhập, ký yêu cầu hoặc mở quyền truy cập** không?
- Nếu người đọc log không có quyền đọc node tương ứng, họ có được phép xem giá trị này không?
- Dữ liệu có cần xuất hiện trong log để chẩn đoán lỗi không, hay chỉ cần mã operation và thời gian?
- Có yêu cầu lưu giữ hoặc xóa dữ liệu riêng cho từng loại không?

Kết quả phân loại phải dẫn tới một **chính sách cụ thể**: trường nào tuyệt đối không ghi, trường nào được pseudonymize, trường nào được phép đưa vào log sau khi kiểm tra.

### 2.2. Graph có rủi ro lộ thông tin qua mối liên kết

Không chỉ property đơn lẻ mới nhạy cảm. Một đường đi:

~~~text
(:Employee)-[:WORKS_ON]->(:ConfidentialProject)
(:Customer)-[:HAS_CASE]->(:SensitiveCase)
(:Person)-[:MEMBER_OF]->(:PrivateGroup)
~~~

có thể làm lộ thông tin chỉ bằng cách ghi **những node và relationship nào xuất hiện cùng nhau**.

Vì vậy, log dạng “debug toàn bộ graph result” hoặc ghi danh sách đường đi `Path` có thể nhạy cảm ngay cả khi đã bỏ email và số điện thoại. Cần hạn chế cả **cấu trúc kết nối và danh tính đầu mút** được xuất ra hệ thống giám sát.

## 3. Bản đồ các đường rò rỉ dữ liệu

Một request đi qua nhiều lớp, mỗi lớp có cơ chế ghi lại khác nhau:

~~~mermaid
flowchart TD
  A["HTTP/API request<br/>PII, token, request body"] --> B["Java Service"]
  B --> C["Cypher query + parameters"]
  C --> D["Neo4j Server"]
  D --> E["Result/Record/Graph values"]
  E --> B
  B --> F["Application log"]
  B --> G["APM / distributed tracing"]
  B --> H["Metrics"]
  D --> I["Neo4j query log / diagnostics"]
  D --> J["Administration / query inspection"]
  F --> K["Log platform / alerts"]
  G --> K
  H --> K
  I --> K
~~~

| Bề mặt quan sát | Dữ liệu có thể xuất hiện | Cách kiểm soát ưu tiên |
|---|---|---|
| **Query text** | Cypher chứa literal, property name, label, path | Parameter hóa, tránh bí mật trong literal, giới hạn chia sẻ |
| **Query parameters** | Email, ID, token, JSON/list/map lồng nhau | Tắt ghi tham số không cần thiết, allowlist |
| **Neo4j query log** | Text truy vấn, timing và đôi khi parameter tùy config | Giảm chi tiết, cấu hình redaction/obfuscation theo phiên bản |
| **Server debug/diagnostic** | Trạng thái hệ thống, ngoại lệ, thông tin kết nối | Quyền truy cập, TTL, không bật tùy tiện |
| **Java Driver/framework log** | Exception, query, map tham số, response | Không log object thô, giới hạn log level, sanitization |
| **APM/span** | `db.statement` hoặc thuộc tính truy vấn, lỗi, baggage | Allowlist span attributes, không capture parameter |
| **Metrics** | Label/URL/query text/ID nếu instrument sai | Label hữu hạn, thống kê tổng hợp |
| **Monitoring UI/admin query list** | Query đang chạy, text, thống kê session | Vai trò tối thiểu và audit thao tác xem |
| **Alert/ticket/export** | Đoạn log đã được chèn vào thông báo | Cảnh báo bằng mã an toàn, phân quyền hệ thống đích |
| **Backup/heap dump/support bundle** | Nội dung log, memory, cấu hình và đôi khi dữ liệu thô | Kênh lưu trữ giới hạn, mã hóa, retention, quy trình chia sẻ |

Bảo vệ một điểm chưa chắc đã bảo vệ toàn bộ. Ví dụ tắt parameter logging ở Neo4j **không ngăn** Spring controller ghi request body hoặc APM agent chụp attribute chứa email.

## 4. Cypher parameterization: đúng nhưng chưa đủ

### 4.1. Tránh ghép dữ liệu người dùng vào câu Cypher

**Không nên:**

~~~java
String cypher =
    "MATCH (c:Customer {email: '" + email + "'}) RETURN c";
~~~

Việc ghép chuỗi có thể tạo rủi ro **Cypher injection** và khiến email xuất hiện trực tiếp trong văn bản truy vấn, vốn có thể được log, hiển thị trong công cụ chẩn đoán hoặc gửi kèm exception.

**Nên:**

~~~cypher
MATCH (c:Customer {email: $email})
RETURN c.customerId AS customerId,
       c.status AS status;
~~~

và truyền tham số từ Java:

~~~java
Map<String, Object> parameters = Map.of("email", email);
tx.run(cypher, parameters);
~~~

Parameterization có lợi vì:

- Tách cú pháp Cypher khỏi dữ liệu không tin cậy.
- Giảm nguy cơ injection đối với những vị trí hỗ trợ parameter.
- Giúp tránh nhân bản văn bản truy vấn theo từng giá trị literal.
- Cho phép áp dụng chính sách logging query text và parameter **riêng biệt**.

Nhưng map `parameters` **vẫn chứa email thật**. Nếu logger in cả map, dữ liệu bị lộ:

~~~java
// Sai: phát tán giá trị email qua log.
logger.info("Cypher params = " + parameters);
~~~

**Không nhầm “dùng parameter” với “parameter được mã hóa hoặc ẩn khỏi mọi nơi”**. Driver cần truyền giá trị thực cho Neo4j để query thực thi; chính sách bảo vệ là không đưa nó sang kênh quan sát không cần thiết.

### 4.2. Không đưa secret vào query dù dùng parameter

Một số ứng dụng sai thiết kế có thể truyền API key, token hoặc mật khẩu vào một truy vấn chỉ để so sánh/chẩn đoán. Dù dùng parameter, secret vẫn đi qua database và có nguy cơ xuất hiện trong tooling nếu cấu hình không chặt.

Chỉ truyền những dữ liệu **thực sự cần để thực hiện nghiệp vụ**. Với xác thực người dùng, ưu tiên cơ chế xác thực của hệ thống có trách nhiệm thay vì lưu hoặc so sánh password thô bằng Cypher.

### 4.3. Không dựa vào tên parameter để quyết định an toàn

~~~cypher
MATCH (u:User)
WHERE u.email = $value
RETURN u.userId;
~~~

Tên parameter `$value` không làm giá trị bớt nhạy cảm. Ngược lại, tên `$email` cho biết ý nghĩa dữ liệu, nhưng cũng không thể dùng một quy tắc tên đơn giản để che đủ mọi trường lồng nhau.

Ví dụ payload phức tạp:

~~~json
{
  "profile": {
    "email": "sample.user@example.invalid",
    "phone": "+84-000-000-000"
  },
  "metadata": {
    "source": "mobile"
  }
}
~~~

Nếu logger ghi toàn bộ `profile` hoặc `metadata` mà không phân loại, một trường mới được thêm trong tương lai có thể bị lộ. Chính sách nên theo hướng **cho phép rõ những trường an toàn**, thay vì mặc định mọi trường không nằm trong danh sách cấm đều được ghi.

### 4.4. Cypher động vẫn cần kiểm soát phần cấu trúc

Nếu ứng dụng phải chọn label, relationship type, property name hay thứ tự sắp xếp động, chỉ parameter hóa **giá trị** không tự bảo vệ mọi vị trí cấu trúc của Cypher trên mọi phiên bản.

Ưu tiên **allowlist các lựa chọn cấu trúc đã được duyệt**; không chèn thẳng tên label/type hoặc ORDER BY từ request. Ngoài injection, một query text động có thể chứa dữ liệu bí mật bị đưa nhầm vào tên schema.

## 5. Neo4j query log: phân biệt query text và giá trị parameter

Neo4j có các cơ chế ghi log truy vấn, nhưng **tên setting, chế độ, giá trị mặc định và mức obfuscation** thay đổi theo phiên bản và cấu hình triển khai. Ví dụ trong phần này là định hướng cho dòng **Neo4j 5.x**, cần đối chiếu với cấu hình thực tế trước khi áp dụng.

### 5.1. Điều cần đánh giá trước khi bật query logging

Query log thường hữu ích cho:

- Truy vết truy vấn chậm và timeout.
- Phân tích thời lượng, số liệu thực thi và nhóm truy vấn.
- Chẩn đoán bottleneck trong Cypher, index và traversal.
- Phát hiện những query bất thường ở cấp vận hành.

Nhưng nó cũng là đường sao chép:

- Văn bản truy vấn có **literal nhạy cảm**.
- Map parameter nếu logging parameter đang bật.
- Thông tin transaction/session có thể liên hệ tới người dùng hoặc tenant.
- Mẫu truy vấn và label/relationship nội bộ.

Không bật chế độ chi tiết nhất trên production chỉ vì “để đủ thông tin debug”. Hãy xác định **mục đích, quyền truy cập, thời gian lưu và giá trị cần thiết** trước.

### 5.2. Ví dụ cấu hình theo chính sách giảm thiểu

Trong môi trường Neo4j 5.x hỗ trợ các setting tương ứng, một điểm khởi đầu có thể là:

~~~properties
# neo4j.conf — ví dụ cần xác minh với phiên bản đang chạy.
db.logs.query.enabled=INFO
db.logs.query.parameter_logging_enabled=false
~~~

Ý nghĩa mong muốn:

- Bật ghi thông tin truy vấn theo mức `INFO` được phiên bản hỗ trợ.
- **Không ghi giá trị tham số** vào query log qua setting tương ứng.

**Đây không phải bảo đảm rằng log hoàn toàn vô hại.** Nếu chính văn bản Cypher có literal nhạy cảm, hoặc một kênh log/diagnostics khác ghi dữ liệu, setting trên không tự xử lý chúng.

Trong hệ thống có yêu cầu bảo mật cao, cân nhắc chỉ log truy vấn chậm hoặc mức tối thiểu mà phiên bản Neo4j hỗ trợ; lựa chọn thực tế phụ thuộc nhu cầu vận hành và yêu cầu audit. Một số phiên bản có tùy chọn **obfuscation literal** và giới hạn chi tiết parameter — kiểm tra các tùy chọn cụ thể thay vì mặc định chúng tồn tại ở mọi bản cài.

### 5.3. Xem setting hiệu lực thay vì đoán theo file

Khi có quyền và phiên bản Neo4j phù hợp:

~~~cypher
SHOW SETTINGS
YIELD name, value
WHERE name STARTS WITH 'db.logs.query.'
RETURN name, value
ORDER BY name;
~~~

Truy vấn giúp đối chiếu các setting query logging thực sự tồn tại và giá trị hiệu lực. Nếu không có quyền `SHOW SETTINGS`, nhờ quản trị viên kiểm tra theo quy trình.

Các điểm cần xác minh:

1. `db.logs.query.enabled` đang ở chế độ phù hợp.
2. Tùy chọn ghi parameter đã được **tắt hoặc giới hạn** theo chính sách.
3. Cơ chế che literal/obfuscation (nếu hỗ trợ) có được bật và kiểm thử không.
4. Các loại log khác có đang chụp query/parameter theo một đường khác không.
5. File log và nền tảng thu thập log có giới hạn quyền, retention và export hay không.

### 5.4. Obfuscation không thay thế phân loại dữ liệu

Ngay cả khi Neo4j có cơ chế che một số bí mật trong cú pháp đặc biệt, không được suy diễn nó luôn che:

- Email hoặc số điện thoại được ghép trực tiếp vào literal bất kỳ.
- Object/list lồng nhau trong parameter.
- Dữ liệu nằm trong biểu thức hoặc procedure tự viết.
- Các trường được một APM agent ghi độc lập ngoài query log.
- Dữ liệu được ứng dụng ghi trước khi gọi Neo4j.

**Cách kiểm chứng thực tế:** gửi giá trị thử không có thật, có dấu nhận diện duy nhất, rồi tìm trong các đầu ra log và trace được phép. Nếu marker xuất hiện, cần sửa điểm ghi dữ liệu trước khi đưa vào production.

## 6. Log truy vấn và dữ liệu do quản trị viên nhìn thấy

Ngoài file query log, công cụ quản trị có thể hiển thị thông tin truy vấn đang chạy, transaction, session hoặc cài đặt theo quyền được cấp.

Ví dụ lệnh quản trị:

~~~cypher
SHOW TRANSACTIONS;
~~~

Lệnh này phục vụ vận hành; tùy phiên bản và quyền, kết quả/công cụ có thể chứa thông tin transaction hoặc truy vấn hữu ích cho chẩn đoán. **Không chia sẻ kết quả thô của một phiên quản trị** lên ticket hoặc chat nếu chưa rà soát dữ liệu nhạy cảm.

### 6.1. Nguyên tắc quyền tối thiểu

- Người chỉ cần xem **CPU, memory, latency, tổng transaction** không mặc định cần quyền đọc từng query/parameter.
- Người điều tra sự cố có thể được cấp quyền tạm thời, có kiểm soát và audit.
- Quyền quản trị Neo4j không mặc nhiên cần cấp cho agent thu thập metric.
- Phân quyền trong Neo4j và phân quyền ở hệ thống **thu thập/hiển thị log** phải được xem xét riêng.

Một operator không được đọc property nhạy cảm trong graph cũng không nên có một đường vòng để đọc cùng dữ liệu đó qua logging backend.

### 6.2. EXPLAIN và PROFILE cần xử lý có kiểm soát

~~~cypher
EXPLAIN
MATCH (c:Customer {email: $email})
RETURN c.customerId;
~~~

`EXPLAIN` hiển thị kế hoạch truy vấn mà không chạy phần Cypher đang được giải thích. Dù vậy, **nội dung query text và các thông tin kế hoạch** trước khi chia sẻ vẫn cần được rà soát.

`PROFILE` thực thi câu truy vấn rồi thu thập số liệu. Với câu ghi `CREATE`, `SET` hoặc `DELETE`, PROFILE cũng **thực hiện tác động ghi thật**. Không chạy PROFILE trên production với truy vấn ghi chỉ để thu thập dữ liệu trình bày cho tài liệu hỗ trợ.

Khi debug, ưu tiên **parameter tổng hợp và bản sao dữ liệu an toàn**, không chụp màn hình truy vấn chứa email thật.

## 7. Java Driver: đặt điểm ghi log ở ranh giới đã kiểm soát

Java Driver làm việc với `Driver`, `Session`, transaction và `Result`/`Record`. Nếu logger vô tình gọi `toString()` trên map parameter, record hoặc exception, giá trị nghiệp vụ có thể bị đưa vào log.

### 7.1. Mẫu log không nên dùng

~~~java
// Không dùng trên request chứa dữ liệu nhạy cảm.
logger.info("Running query: " + cypher + " params: " + parameters);

// Có thể in property của node/relationship trong kết quả.
logger.info("Result: " + record);

// Thông điệp lỗi có thể chứa chi tiết không phù hợp để công bố.
logger.warning("Neo4j failed: " + exception.getMessage());
~~~

Vấn đề không nằm ở mức `INFO` hay `WARN` đơn lẻ; nó nằm ở **giá trị được đưa ra ngoài phạm vi database**. Thay mức INFO bằng DEBUG cũng không tạo ra chính sách an toàn nếu DEBUG có thể được bật khi cần chẩn đoán.

### 7.2. Mẫu log an toàn hơn: operation, kết quả và thời lượng

Một service chỉ cần ghi sự kiện `customer.lookup` đã thành công/không tìm thấy/thất bại và thời gian xử lý, **không ghi email, customerId hoặc map parameter**.

~~~java
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.TimeUnit;
import java.util.logging.Level;
import java.util.logging.Logger;

import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.exceptions.Neo4jException;

public final class CustomerLookupService {
    private static final Logger LOG =
        Logger.getLogger(CustomerLookupService.class.getName());

    public record CustomerSummary(
        String customerId,
        String status
    ) {}

    private final Driver driver;

    public CustomerLookupService(Driver driver) {
        this.driver = driver;
    }

    public Optional<CustomerSummary> findByEmail(String email) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("email is required");
        }

        String cypher = """
            MATCH (c:Customer {email: $email})
            RETURN c.customerId AS customerId,
                   c.status AS status
            LIMIT 1
            """;

        long started = System.nanoTime();

        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {

            Optional<CustomerSummary> found = session.executeRead(tx -> {
                var result = tx.run(cypher, Map.of("email", email));
                if (!result.hasNext()) {
                    return Optional.<CustomerSummary>empty();
                }

                var row = result.next();
                return Optional.of(new CustomerSummary(
                    row.get("customerId").asString(),
                    row.get("status").asString()
                ));
            });

            long ms = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started
            );
            LOG.log(Level.INFO,
                "operation=customer.lookup outcome={0} durationMs={1}",
                new Object[] {
                    found.isPresent() ? "found" : "not_found",
                    ms
                }
            );
            return found;

        } catch (Neo4jException ex) {
            long ms = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started
            );
            LOG.log(Level.WARNING,
                "operation=customer.lookup outcome=failed durationMs={0}",
                ms
            );
            throw ex;
        }
    }
}
~~~

Ví dụ trên có vài quyết định quan trọng:

- Dùng `parameter` để truyền email vào Cypher.
- **Không** ghi giá trị email, map parameter, record hay `exception.getMessage()`.
- Dữ liệu về thời gian và kết quả được **tính từ luồng ứng dụng**, không từ object chứa dữ liệu cá nhân.
- `executeRead` là managed read transaction; callback có thể được driver retry. Log “một request hoàn thành” được phát **sau callback**, tránh tính mỗi lần thử thành một lần thành công.
- DTO chứa `customerId` được trả về trong bộ nhớ theo nghiệp vụ, nhưng **không bị logger in trực tiếp**.
- `Driver` được tái sử dụng; `Session` có vòng đời ngắn.

**Phạm vi ví dụ:** trong thực tế, cần xử lý null property, database name, cấu hình authentication và các nhóm exception khác theo hợp đồng ứng dụng. Ngoài ra, ngoại lệ được ném lại có thể bị tầng HTTP/telemetry bắt và log nội dung; tầng đó cũng cần chính sách sanitization.

### 7.3. Không đưa Throwable thô vào logger khi chưa kiểm soát

Đoạn sau có thể làm hệ thống log tự in message/stack trace:

~~~java
// Cần đánh giá chính sách trước khi dùng.
logger.log(Level.SEVERE, "Neo4j request failed", exception);
~~~

Stack trace có thể hữu ích cho phát triển, nhưng error message, suppressed exception, cause chain hoặc dữ liệu đầu vào được chèn vào exception tùy thư viện và tình huống. Trên luồng có PII, cần logger/error handler phân loại mức độ an toàn của dữ liệu được đính kèm.

Một chiến lược là log **mã lỗi được allowlist và tên operation**, đồng thời lưu chẩn đoán chi tiết hơn trong hệ thống hạn chế quyền nếu thực sự cần. Không nên lấy exception message làm nhãn metric hoặc response API công khai.

### 7.4. Kiểm soát logging của driver

Khi bật DEBUG/TRACE ở namespace của Java Driver, có thể xuất hiện thêm thông tin giao thức, kết nối và truy vấn tùy phiên bản/config. Không giả định mọi phiên bản sẽ log hoặc không log cùng một loại dữ liệu.

Quy tắc an toàn:

1. Giữ mức log bình thường ở giá trị đã kiểm thử.
2. Chỉ bật DEBUG/TRACE theo thời hạn và phạm vi được phê duyệt.
3. Kiểm tra **giá trị thực sự xuất hiện** bằng dữ liệu thử trước khi dùng production.
4. Không bật “wire dump” hoặc logging raw traffic có thể chứa payload khi không có nhu cầu và bảo vệ đặc biệt.
5. Sau điều tra, tắt chế độ chi tiết và xử lý log được tạo theo retention/incident policy.

Nếu có framework log intercept mọi lệnh `tx.run(...)`, cấu hình an toàn của Neo4j server **không chặn** logger này vì nó chạy phía ứng dụng.

## 8. Spring Data Neo4j: query logging có thể xuất hiện ở nhiều tầng

Với Spring Boot/Spring Data Neo4j, luồng truy vấn có thể đi qua:

~~~text
HTTP controller
    |
Application service
    |
Repository / Neo4jClient
    |
Neo4j Java Driver
    |
Neo4j server
~~~

Mỗi tầng có thể có:

- Logging request/response do filter/interceptor.
- Logging tham số của controller hoặc service qua annotation/AOP.
- Logging query từ repository hoặc `Neo4jClient`.
- Logging driver và exception.
- APM/tracing được tự động instrument.
- Công cụ đẩy log sang backend tập trung.

### 8.1. Không dùng log tất cả method arguments

Một interceptor dạng “log mọi argument của mọi service method” rất dễ in email, token, mã tài khoản, map JSON hoặc thông tin đồ thị. Phương thức `findByEmail(email)` có thể bị ghi tham số dù bản thân service không gọi logger.

**Cần thiết kế allowlist** cho tên operation, kết quả chung, thời lượng và correlation ID do hệ thống tạo. Nếu cần debug riêng một field, phải có quy trình phê duyệt và biến đổi an toàn theo loại dữ liệu.

### 8.2. Cấu hình logging framework cần được kiểm thử

Có thể cấu hình mức log cho các package liên quan driver và Spring Data bằng cơ chế của Spring Boot. Tuy nhiên, **tên logger và chi tiết dữ liệu phát ra phụ thuộc phiên bản/framework**. Không coi một thuộc tính `logging.level...=INFO` bất kỳ là bằng chứng đã che parameter.

Thực hiện thử nghiệm với marker giả để xem nội dung từ:

- Log ứng dụng.
- Log query/repository.
- Log driver.
- Log của HTTP filter.
- Exception handler.
- APM auto-instrumentation.

Đừng dừng ở việc xác nhận riêng log của Neo4j server đã tắt tham số.

### 8.3. Entity và DTO cũng có thể làm lộ dữ liệu

Nếu một entity Java có `toString()` tự động bao gồm `email`, `phone` hoặc danh sách relationship, việc log entity có thể phơi bày cả đồ thị liên kết.

Trong ứng dụng dùng Lombok hoặc Java record, cần chú ý các phương thức tự sinh và những chỗ gọi trực tiếp/gián tiếp `toString()`. Thiết kế DTO dành cho phản hồi API không đồng nghĩa DTO đó cũng an toàn để log.

## 9. Tracing/APM: không đưa tham số vào span attributes

Distributed tracing rất hữu ích để tìm request chậm, ví dụ:

~~~text
HTTP POST /orders
    |
    +-- validate request
    |
    +-- Neo4j transaction
            |
            +-- MATCH Customer
            +-- CREATE Order
~~~

Span có thể chứa tên operation, thời gian, trạng thái và lỗi. Nhưng nếu span cũng chứa **toàn bộ Cypher statement, parameter map, URL query string hoặc body**, nó trở thành nguồn rò rỉ.

### 9.1. Thuộc tính span nên cho phép rõ

Ví dụ một tập thuộc tính an toàn hơn (tên minh họa, không yêu cầu schema một APM cụ thể):

~~~json
{
  "operation": "order.create",
  "component": "neo4j",
  "db.operation": "WRITE",
  "db.name": "commerce",
  "result": "success",
  "duration_ms": 24
}
~~~

Không đưa các trường sau làm attribute mặc định:

~~~json
{
  "customer.email": "person@example.invalid",
  "cypher.parameters": {
    "email": "person@example.invalid",
    "phone": "+84-000-000-000"
  },
  "auth.token": "SECRET-CANARY-DO-NOT-LOG"
}
~~~

Khối JSON thứ hai là **phản ví dụ**, không phải cấu hình nên triển khai. Dùng các giá trị giả có thể nhận diện rõ khi kiểm thử hệ thống log/tracing.

### 9.2. Tên span có độ biến thiên cao gây hai vấn đề

Không đặt tên span:

~~~text
lookup-customer-person@example.invalid
~~~

Vì nó vừa lộ email, vừa làm số lượng tên span tăng vô hạn theo dữ liệu người dùng. Nên dùng:

~~~text
customer.lookup
~~~

Giữ các trường phân loại trạng thái hữu hạn như `read`, `write`, `success`, `error` và các tên operation được duyệt.

### 9.3. Baggage và error event

Baggage trong distributed tracing có thể được **chuyển qua nhiều service**. Không đưa email, session token hoặc dữ liệu bí mật vào baggage trừ khi có thiết kế được xét duyệt với mục đích cụ thể; dù endpoint cuối không log, service trung gian vẫn có thể ghi nó.

Một số APM SDK tự ghi exception message/stack trace vào span event. Cần kiểm tra cấu hình capture exception, scrub attributes và các hệ thống đích. Một rule redaction ở dashboard **không đủ** nếu raw span đã được gửi và lưu.

## 10. Metrics: an toàn hơn khi tổng hợp, nhưng label có thể lộ PII

Metric về Neo4j nên tập trung vào:

- Số query/transaction.
- Thời gian thực thi và thời gian chờ pool.
- Lỗi, timeout, retry.
- CPU, heap, page cache, I/O.
- Số kết nối, tải đọc/ghi.
- Kích thước response hoặc lượng hàng tổng hợp.

Các label nên là **tập giá trị nhỏ, ổn định**, ví dụ:

~~~text
neo4j_requests_total{operation="customer.lookup",outcome="success"}
neo4j_request_duration_seconds{operation="order.create"}
~~~

**Không nên:**

~~~text
neo4j_requests_total{email="person@example.invalid"}
neo4j_query_duration_seconds{customerId="C-123456"}
neo4j_requests_total{cypher="MATCH ... email literal ..."}
~~~

Ngoài nguy cơ lộ dữ liệu, label `email` hoặc `customerId` có **cardinality rất cao**, làm tăng số time series, chi phí lưu trữ và rủi ro quá tải hệ thống giám sát.

### 10.1. Giữ metric không có ID người dùng

Một bảng metric có thể chứa:

| Metric | Label nên dùng | Label nên tránh |
|---|---|---|
| Query latency | operation, outcome | email, token, query text thô |
| Transaction retry | operation, error category | request body, raw exception |
| Pool wait | service, pool name đã duyệt | userId, sessionId |
| Neo4j error count | nhóm lỗi được allowlist | exception message chưa scrub |
| Graph import throughput | job type, outcome | bản ghi CSV, khóa nhạy cảm |
| Cache hit/miss | cache type, service | customer/tenant ID nếu không cần và chưa duyệt |

Nếu cần phân tích theo tenant, phải cân nhắc số tenant, tính nhạy cảm của mã tenant, yêu cầu phân tách dữ liệu và giới hạn cardinality. Không mặc định tenant ID luôn được phép xuất trong metrics.

## 11. Dùng correlation ID mà không in danh tính khách hàng

Khi điều tra một request xuyên Java service và Neo4j, kỹ sư thường cần biết các log thuộc **cùng một thao tác**. Thay vì ghi email của khách hàng, ứng dụng có thể tạo **correlation ID ngẫu nhiên** cho request và dùng ID đó để liên kết log/trace.

~~~text
requestId=8d62f6f7-...  operation=customer.lookup  outcome=success
requestId=8d62f6f7-...  component=neo4j        durationMs=24
~~~

Lưu ý:

- Correlation ID nên được tạo hoặc kiểm tra bởi hệ thống tin cậy; không tin trực tiếp mọi chuỗi `X-Request-ID` dài/tùy ý từ client.
- Không nhét email hoặc số điện thoại vào ID dưới dạng `customer-email-2026...`.
- Không dùng correlation ID như bằng chứng duy nhất về người yêu cầu.
- Nếu cần tra ngược request tới chủ thể nghiệp vụ, lưu ánh xạ trong hệ thống có quyền truy cập phù hợp, với retention rõ ràng.

Một request ID tuy không phải PII trực tiếp vẫn có thể liên kết hoạt động của người dùng nếu được ghép với các hệ thống khác; vì thế cũng cần chính sách lưu giữ hợp lý.

## 12. Masking, redaction và pseudonymization

Ba kỹ thuật thường được gọi chung là “ẩn dữ liệu”, nhưng tính chất khác nhau.

| Kỹ thuật | Ví dụ | Có thể đảo ngược/nhận diện không? | Khi nào dùng |
|---|---|---|---|
| **Masking** | `a***@example.invalid` | Có thể lộ một phần danh tính | UI hỗ trợ, khi thật sự cần nhìn một phần |
| **Redaction** | `[REDACTED]` | Không thể khôi phục từ chính log đã loại bỏ giá trị | Log và alert không cần giá trị gốc |
| **Pseudonymization** | HMAC cho ra ID giả ổn định | Có thể liên kết/đối chiếu bằng khóa hoặc dữ liệu phụ | Theo dõi cùng thực thể không lưu ID thô |
| **Aggregation** | `count=125` | Thường giảm khả năng nhận diện | Metrics và thống kê vận hành |

**Pseudonymization không đồng nghĩa anonymization tuyệt đối.** Một ID giả ổn định vẫn có thể liên kết nhiều hành động và trở thành dữ liệu cá nhân tùy ngữ cảnh.

### 12.1. Vì sao không chỉ dùng SHA-256 trực tiếp trên email?

Email có không gian giá trị đủ dễ đoán cho các phép thử từ điển. Nếu log lưu `SHA256(email)`, người có danh sách email ứng viên có thể hash từng địa chỉ để đối chiếu.

Khi thật sự cần mã ổn định để nhóm log theo chủ thể, cân nhắc **HMAC-SHA-256 với secret key được quản lý an toàn**. Khi đó, không có khóa, việc thử đoán hàng loạt khó hơn đáng kể. Nhưng HMAC token vẫn là một **pseudonym** và cần:

- Key management/rotation và quyền đọc khóa tối thiểu.
- Cách chuẩn hóa input thống nhất trước HMAC.
- Chính sách khi đổi khóa làm thay đổi mã giả.
- Không log khóa HMAC.
- Đánh giá yêu cầu pháp lý/quyền riêng tư tại tổ chức.

Nếu không cần nhóm theo người dùng, **bỏ hẳn ID** là giải pháp đơn giản và an toàn hơn.

### 12.2. Mẫu log dựa trên allowlist thay vì regex bắt mọi PII

**Cách yếu:** ghi toàn bộ map request rồi thay chuỗi khớp email bằng `***`. Cách này có thể bỏ sót:

- Số điện thoại, địa chỉ, tên riêng, token.
- Email theo định dạng không ngờ tới.
- JSON nhiều lớp, encoded value, URL query parameter.
- Relationship và đường đi nhạy cảm.
- Trường mới do phiên bản API bổ sung.

**Cách mạnh hơn:** logger chỉ được xây từ các trường **đã được duyệt**:

~~~json
{
  "operation": "customer.lookup",
  "outcome": "not_found",
  "durationMs": 18,
  "retryCount": 0
}
~~~

Sau đó có thể thêm **sanitizer/redaction tại collector** như một lớp phòng thủ thứ hai, nhưng không dùng nó để biện minh cho việc ghi dữ liệu thô ở nguồn.

## 13. Cấu hình audit và log truy cập khác log query chi tiết

Một số hệ thống cần audit “ai đã thực hiện thao tác gì” để điều tra an ninh hoặc tuân thủ. Audit **khác** với query logging phục vụ tối ưu hiệu năng.

Ví dụ audit event có thể cần:

- Actor hoặc service identity theo chính sách được phê duyệt.
- Mã hành động nghiệp vụ như `order.cancel`.
- Thời điểm, outcome, correlation ID.
- Đối tượng bị ảnh hưởng dưới dạng mã được bảo vệ nếu thực sự cần.
- Dấu vết thay đổi/quyền quản trị trong phạm vi quy định.

Điều này **không đòi hỏi** ghi toàn bộ parameter map, query text chứa literal hoặc dữ liệu graph.

### 13.1. Phân quyền xem audit và query log

- Người làm hiệu năng có thể cần **latency, operator và error category**, nhưng không cần dữ liệu cá nhân.
- Người điều tra an ninh có thể cần audit về actor/action, với quyền hạn riêng.
- Đội hỗ trợ khách hàng có thể cần xem một phần thông tin được masking qua UI, không cần quyền xem log thô.
- Tài khoản agent thu thập log cần quyền ghi/xuất đúng phạm vi, không cần quyền quản trị Neo4j rộng hơn mức cần thiết.

Nếu quy trình điều tra yêu cầu xem dữ liệu chi tiết, nên có cơ chế **truy cập có kiểm soát và ghi audit** thay vì bật log tham số cho tất cả request.

### 13.2. Phân biệt danh tính vận hành với danh tính người dùng

Một tài khoản kết nối Neo4j là `app_service` có thể thay mặt hàng nghìn người dùng. Log server chỉ biết service account **không tự chứng minh** người dùng cuối nào đã gọi API.

Nếu cần audit người dùng cuối, application service phải tạo sự kiện audit theo hợp đồng riêng, có bảo vệ quyền riêng tư và xác thực actor. Không dùng việc chèn email người dùng vào query comment hoặc tên transaction như một lối tắt thiếu an toàn.

## 14. Retention và nơi dữ liệu bị sao chép

Không nên chỉ hỏi “log có lộ không?”, mà còn hỏi **log đi đâu, được lưu bao lâu và ai có thể xuất nó ra**.

~~~text
Java/Neo4j logs
      |
      v
Collector/Agent
      |
      +--> Central log storage
      +--> Alert notification
      +--> Ticket/incident attachment
      +--> Backup/archive
      +--> External observability vendor
~~~

Một giá trị nhạy cảm có thể tồn tại trong nhiều bản sao khác nhau. Khi xóa dữ liệu tại Neo4j, bản sao trong hệ thống giám sát **không tự bị xóa theo**.

### 14.1. Quy tắc quản trị dữ liệu log

1. Chỉ thu những trường cần thiết cho mục tiêu vận hành.
2. Mã hóa kết nối log collector và kho lưu trữ khi phù hợp.
3. Phân quyền đọc/tra cứu/export theo vai trò, bảo vệ tài khoản máy.
4. Thiết lập retention, chính sách archive và xóa theo yêu cầu tổ chức/pháp luật.
5. Xác định rõ nơi có thể gửi alert hoặc đính kèm log.
6. Không để debug bundle/log thô trong bucket công khai.
7. Giới hạn quyền tải hàng loạt và kiểm tra lịch sử truy cập log.
8. Đưa dữ liệu log và bản sao vào kế hoạch xử lý sự cố rò rỉ.

### 14.2. Xử lý khi phát hiện PII/secret trong log

Nếu lỡ ghi token hoặc mật khẩu thật, **chỉ chỉnh code để ngừng log từ thời điểm đó là chưa đủ**. Cần kích hoạt quy trình incident:

- Ngăn phát sinh thêm dữ liệu nhạy cảm.
- Xác định phạm vi/khoảng thời gian và những hệ thống nhận bản sao.
- Xoay vòng/thu hồi secret có nguy cơ bị lộ.
- Thu hồi quyền truy cập không phù hợp và xử lý bản sao theo chính sách.
- Kiểm tra alert/ticket/export và backup liên quan.
- Ghi nhận biện pháp ngăn tái diễn và kiểm thử regression.

Với PII, đánh giá nghĩa vụ thông báo và xử lý theo chính sách dữ liệu/luật áp dụng; không tùy tiện chia sẻ log nhạy cảm thêm trong quá trình điều tra.

## 15. Quy trình debug Neo4j không cần giá trị thật

Kỹ sư có thể kiểm tra truy vấn chậm mà không cần in email hoặc payload sản phẩm thật vào log.

### 15.1. Dùng tên operation cố định

Đặt tên operation ở tầng ứng dụng:

~~~text
operation=customer.lookup
operation=order.create
operation=graph.followers.list
operation=product.recommend
~~~

Dựa trên tên này, có thể thống kê latency, lỗi, retry và throughput. Nếu phải định danh phiên bản câu query, dùng **mã template/version được quản lý**, chẳng hạn `customer.lookup.v2`, chứ không hash thô một query có literal nhạy cảm rồi công khai mọi thứ.

### 15.2. EXPLAIN bằng dữ liệu giả

~~~cypher
EXPLAIN
MATCH (c:Customer {email: $email})
RETURN c.customerId AS customerId
LIMIT 1;
~~~

Kết quả kế hoạch giúp xem index, Filter, Estimated Rows và các operator. Để chia sẻ với nhóm hỗ trợ, thay dữ liệu thật bằng **tham số giả có cấu trúc tương đương**.

Nếu muốn đánh giá hiệu năng thật, một tập dữ liệu synthetic/ẩn danh vẫn cần bảo tồn độ chọn lọc, phân bố property, cardinality relationship và kích thước graph phù hợp; không thể thay bằng ba node rồi kết luận query production nhanh/chậm như thế.

### 15.3. Chỉ nâng mức log có thời hạn

Khi bắt buộc tăng chi tiết quan sát:

1. Ghi nhận lý do, người phê duyệt và khoảng thời gian bật.
2. Thử trước trên môi trường test với marker giả.
3. Giới hạn service/instance/operation nếu công cụ hỗ trợ.
4. Chỉ thu trường đã được duyệt; tránh parameter và raw result.
5. Giới hạn người xem và nơi xuất dữ liệu.
6. Tắt cấu hình chi tiết sau điều tra.
7. Kiểm tra/xử lý log đã sinh theo retention và quy trình an ninh.

Đừng sửa logging level hàng loạt rồi quên khôi phục; tải log cao còn có thể làm giảm hiệu năng của Neo4j và ứng dụng.

## 16. Bộ kiểm thử phát hiện dữ liệu nhạy cảm bị ghi ra log

Đây là phần quan trọng để biến một chính sách “không log PII” thành **bằng chứng kỹ thuật**.

### 16.1. Dùng marker giả, duy nhất

Ví dụ request test:

~~~json
{
  "email": "canary-neo4j-2026@example.invalid",
  "phone": "+84-000-111-222",
  "apiToken": "TEST-ONLY-CANARY-SECRET-2026",
  "nested": {
    "note": "NEO4J-PII-CANARY-2026"
  }
}
~~~

Các giá trị trên là **dữ liệu thử**, không có tác dụng xác thực. Chúng phải đủ đặc biệt để tìm kiếm mà không nhầm với dữ liệu bình thường.

Cho request đi qua **đúng đường production tương đương**: HTTP/filter → Java/Spring → Driver → Neo4j → logger/collector/APM → backend/alert.

### 16.2. Các kịch bản bắt buộc kiểm tra

| Kịch bản | Nguy cơ | Kỳ vọng |
|---|---|---|
| Query thành công | Logger debug request và parameter | Marker không có trong log/trace/metric |
| Query trả 0 hàng | In đầy đủ parameter để giải thích not found | Chỉ outcome=not_found |
| Query syntax error | Exception có query text/literal | Không phát tán parameter/literal |
| Vi phạm uniqueness | Framework in object gây lỗi | Chỉ mã lỗi an toàn và correlation ID |
| Transaction timeout | Debug tự động bật thêm | Không in request body/parameter |
| Retry managed transaction | Callback log nhiều lần | Không ghi PII ở bất kỳ lần thử nào |
| JSON/list parameter lồng nhau | Sanitizer chỉ lọc trường top-level | Marker lồng nhau không xuất hiện |
| Trả Result có node/path | Log response object | Không in property/relationship nhạy cảm |
| APM auto-instrumentation | Span capture DB statement/param | Chỉ thuộc tính được phép |
| Metric labels | ID người dùng bị dùng làm label | Không có ID/PII và không bùng cardinality |
| Alert khi query chậm | Chèn full query vào chat/ticket | Alert chỉ có mã operation và số liệu |
| Support bundle | Sao chép log raw | Chỉ xuất qua luồng phê duyệt và scrub |

### 16.3. Kiểm thử kiểm tra dữ liệu không được xuất hiện

Một quy trình kiểm thử có thể:

1. Dọn hoặc tạo namespace log/trace của môi trường test để dễ đối chiếu.
2. Gửi request chứa marker giả vào các endpoint đại diện.
3. Tạo thành công, lỗi và timeout có kiểm soát.
4. Chờ pipeline observability nhận đủ dữ liệu.
5. Tìm chính xác marker trong log, trace, metric, alert và những bản export được phép.
6. Nếu thấy marker, xác định **nguồn tạo** (application, driver, server, collector, APM) thay vì chỉ xóa ở dashboard.
7. Lặp sau khi thay cấu hình hoặc nâng phiên bản driver/Neo4j/collector.

Chỉ kiểm tra log local chưa đủ nếu hệ thống còn một **APM backend riêng** hoặc alert service sao chép dữ liệu qua kênh khác.

### 16.4. Bộ test phải bao gồm “mất dữ liệu” và “lộ dữ liệu”

Một thay đổi sanitization không nên làm log và metric mất hết khả năng vận hành. Sau chỉnh sửa, phải còn:

- Tên operation.
- Outcome, error category an toàn.
- Request/correlation ID đã được duyệt.
- Thời lượng, retry và timeout.
- Thông tin để tìm query template/index liên quan.

Mục tiêu là **diagnostics hữu ích mà không cần dữ liệu riêng tư**, không phải tắt tất cả giám sát.

## 17. Các sai lầm phổ biến

| Sai lầm | Vì sao nguy hiểm? | Cách sửa |
|---|---|---|
| “Cypher dùng parameter nên log an toàn” | Logger vẫn có thể in map parameter | Tắt/kiểm soát parameter logging ở mọi tầng |
| Ghép email vào query literal | Email xuất hiện trong query text và tăng nguy cơ injection | Dùng parameter |
| Ghi cả `parameters` để debug | Map có thể chứa email, token, object lồng nhau | Chỉ log operation, outcome, latency |
| Log cả node/relationship/path | Kết quả graph có PII và quan hệ nhạy cảm | Trả DTO, không log raw Result/Record |
| Chỉ filter email bằng regex | Bỏ sót token, số điện thoại, encoded/nested data | Allowlist tại nguồn, sanitizer là lớp bổ sung |
| Dùng SHA-256 trực tiếp cho email | Dễ đối chiếu từ điển với email đoán được | Không lưu ID hoặc dùng HMAC được quản lý |
| Đưa userId vào label metric | Lộ danh tính, cardinality cao | Label hữu hạn theo operation/status |
| Đưa request body vào span | APM giữ bản sao dữ liệu | Attribute allowlist |
| Gửi exception thô vào alert | Message/stack trace có thể chứa dữ liệu | Alert bằng error category an toàn |
| Bật TRACE của driver trên production vô thời hạn | Nguy cơ capture thêm dữ liệu, chi phí log cao | Bật có phê duyệt và TTL |
| Tin obfuscation mặc định luôn đủ | Phiên bản và kênh log khác nhau | Kiểm tra setting và canary test |
| Chỉ kiểm tra file log của Neo4j | PII có thể ở Java, Spring, APM | Test toàn tuyến |
| Xóa PII từ Neo4j nhưng quên log | Bản sao còn trong collector/archive | Quản trị retention và xử lý bản sao |
| Dùng cùng quyền xem log cho mọi nhân viên | Mở đường vòng truy cập PII | RBAC, least privilege, audit |
| Chia sẻ `SHOW TRANSACTIONS` thô trên ticket | Có thể lộ nội dung truy vấn/ngữ cảnh | Rà soát/scrub trước khi chia sẻ |
| Dùng dữ liệu khách hàng thật để test redaction | Tự tạo rò rỉ trong môi trường test | Marker giả, dữ liệu synthetic |
| Tin rằng tắt log server đã đủ | Interceptor phía ứng dụng vẫn log | Kiểm soát mỗi tầng độc lập |

## 18. Checklist triển khai an toàn

### 18.1. Cypher và mô hình dữ liệu

- [ ] Các giá trị do người dùng cung cấp được truyền qua parameter ở những vị trí Cypher hỗ trợ.
- [ ] Không ghép email, token, mật khẩu hay dữ liệu nhạy cảm vào query literal.
- [ ] Tên label/type/property động được chọn từ allowlist.
- [ ] Đã phân loại node property và relationship nhạy cảm.
- [ ] Query chỉ trả trường thật sự cần cho API, không trả toàn bộ graph khi không cần.
- [ ] Không gửi secret đến Neo4j chỉ vì mục đích debug.

### 18.2. Neo4j server và quyền quản trị

- [ ] Đã kiểm tra đúng phiên bản Neo4j và setting query logging hiệu lực.
- [ ] Parameter logging được tắt/giới hạn theo chính sách.
- [ ] Literal obfuscation (nếu có) đã được kiểm thử, không chỉ tin mặc định.
- [ ] Quyền xem query/transaction/log được cấp tối thiểu.
- [ ] File log, collector và nơi xuất log có RBAC, retention và transport protection.
- [ ] Không dùng production query/raw result để chia sẻ tài liệu sự cố.

### 18.3. Java Driver và Spring Data Neo4j

- [ ] Service không log map parameter hoặc entity/Record/Result thô.
- [ ] Logger chỉ nhận operation, outcome, duration và mã lỗi đã được duyệt.
- [ ] Exception handler và AOP/interceptor không chụp request body nhạy cảm.
- [ ] Đã kiểm tra DEBUG/TRACE của driver/framework trong phiên bản dùng thực tế.
- [ ] Correlation ID không chứa email hoặc bí mật.
- [ ] Managed transaction retry không gây log nhạy cảm ở nhiều lần thử.

### 18.4. Observability và vận hành

- [ ] APM/span dùng attribute allowlist; không ghi parameter, token, raw query.
- [ ] Metric labels có cardinality thấp và không nhận dạng người dùng.
- [ ] Alert/ticket/chat không chứa query/exception thô.
- [ ] Có quyền truy cập, retention, xuất bản sao và quy trình xóa log.
- [ ] Dùng dữ liệu canary giả để test thành công, lỗi, retry, timeout.
- [ ] Đã tìm marker trên **mọi** backend log/trace/metric/alert.
- [ ] Có quy trình ứng phó khi phát hiện secret/PII đã vào log.
- [ ] Logging policy được kiểm tra lại sau nâng phiên bản Neo4j, Driver, Spring hoặc APM agent.

## 19. Bài tập và tình huống tự kiểm tra

### Bài 1 — Parameter có thật sự bí mật?

Ứng dụng chạy:

~~~cypher
MATCH (u:User {email: $email})
RETURN u.userId;
~~~

nhưng logger ghi `parameters={email: ...}`.

**Câu hỏi:** Tham số hóa đã giải quyết toàn bộ rủi ro chưa?

**Đáp án:** Chưa. Tham số hóa giúp tách giá trị khỏi cú pháp Cypher, nhưng logger vẫn làm lộ map parameter. Cần loại giá trị khỏi log tại nguồn và kiểm tra query logging phía server.

### Bài 2 — Truy vấn động

Một endpoint ghép `$email` vào string Cypher, rồi bật slow query log để điều tra hiệu năng.

**Câu hỏi:** Có hai rủi ro nào?

**Đáp án:** Có nguy cơ Cypher injection nếu xây chuỗi thiếu kiểm soát, đồng thời email có thể nằm trong query text được ghi lại. Dùng parameter và cấu hình logging không ghi parameter.

### Bài 3 — Dữ liệu lồng nhau

Logger có rule che key `email` cấp đầu nhưng API gửi:

~~~json
{
  "payload": {
    "profile": {
      "email": "canary@example.invalid"
    }
  }
}
~~~

**Câu hỏi:** Rule có chắc chắn che hết dữ liệu không?

**Đáp án:** Không. Trường nhạy cảm có thể nằm sâu trong object; cấu trúc JSON còn có thể thay đổi. Không log map thô; dùng allowlist trường an toàn và canary test.

### Bài 4 — Metric theo người dùng

Một lập trình viên thêm `userId` làm label cho metric đo latency của query gợi ý bạn bè.

**Câu hỏi:** Vì sao không nên?

**Đáp án:** ID có thể giúp nhận diện người dùng và làm số lượng time series tăng theo từng tài khoản. Đo latency theo operation/cohort được phê duyệt thay vì ID cá nhân.

### Bài 5 — Exception message

Handler ghi:

~~~java
logger.warning(exception.getMessage());
~~~

**Câu hỏi:** Có an toàn trong mọi trường hợp không?

**Đáp án:** Không thể bảo đảm. Message có thể chứa query, input hoặc dữ liệu được thư viện nhúng vào. Dùng error category/mã an toàn và quy trình giữ chẩn đoán chi tiết có kiểm soát khi cần.

### Bài 6 — Hash email

Nhóm vận hành muốn thay email trong log bằng `SHA256(email)` để theo dõi cùng khách hàng.

**Câu hỏi:** Có rủi ro không?

**Đáp án:** Có. Email có thể bị đoán từ một danh sách ứng viên rồi hash để đối chiếu. Nếu thật sự cần pseudonym, cân nhắc HMAC có secret được quản lý và retention; nếu không cần, bỏ ID.

### Bài 7 — SHOW TRANSACTIONS

Một kỹ sư chụp màn hình công cụ hiển thị query đang chạy và đăng vào ticket công khai của dự án.

**Câu hỏi:** Có thể rò rỉ dữ liệu gì?

**Đáp án:** Tùy phiên bản và quyền, có thể lộ query text, cấu trúc nội bộ, session hoặc thông tin ngữ cảnh. Cần rà soát/scrub trước khi chia sẻ; ticket cũng là một bản sao phải quản trị.

### Bài 8 — APM vẫn thấy email

Neo4j query log đã được cấu hình không ghi parameter, nhưng dashboard APM vẫn tìm thấy email trong span.

**Câu hỏi:** Nguyên nhân có thể là gì?

**Đáp án:** APM hoặc interceptor phía Java đang chụp parameter, request body hoặc error details **độc lập** với Neo4j server. Cần sửa instrumentation/scrubber tại nguồn và test lại toàn tuyến.

### Bài 9 — Truy vấn chậm trong production

Một query hai bước trên graph rất lớn đang chậm. Đội phát triển muốn bật TRACE cho toàn bộ Driver và in parameter map trong hai ngày.

**Câu hỏi:** Cách tiếp cận nào an toàn hơn?

**Đáp án:** Bắt đầu bằng metric theo operation, plan EXPLAIN và dữ liệu synthetic. Nếu cần log chi tiết, giới hạn phạm vi/thời gian, kiểm tra canary, cấp quyền và không thu parameter thô.

### Bài 10 — Token đã xuất hiện trong log

Một người phát hiện API token thật trong alert đã gửi tới nhóm chat và kho log.

**Câu hỏi:** Có đủ khi tắt logger để ngừng xuất hiện token mới không?

**Đáp án:** Chưa đủ. Cần kích hoạt quy trình incident, thu hồi/xoay vòng token, xác định bản sao trong chat/log/backup, xử lý lưu trữ và truy cập theo chính sách, sau đó thêm regression test chống lộ token.

## 20. Ghi nhớ

Trong hệ thống Neo4j, **giám sát hiệu quả không yêu cầu ghi dữ liệu nhạy cảm**. Cypher parameterization là bước nền tảng để tách dữ liệu khỏi câu lệnh, nhưng giá trị parameter, node/relationship result, exception, transaction inspection, Java Driver log và APM span vẫn có thể trở thành kênh rò rỉ.

Hãy áp dụng **data minimization và allowlist tại nơi tạo log**: ghi tên operation, kết quả, thời lượng, lỗi được phân loại và correlation ID an toàn; không ghi raw query parameter, email, token hay toàn bộ graph. Kiểm soát query logging theo **phiên bản Neo4j**, quyền xem log, retention, dashboard, cảnh báo và bản sao xuất ra. Cuối cùng, dùng **dữ liệu canary giả để kiểm thử toàn tuyến**, kể cả lỗi, retry và tracing. Một hệ thống giám sát đúng phải đủ khả năng chẩn đoán hiệu năng và sự cố **mà không biến log thành bản sao dữ liệu khách hàng**.
