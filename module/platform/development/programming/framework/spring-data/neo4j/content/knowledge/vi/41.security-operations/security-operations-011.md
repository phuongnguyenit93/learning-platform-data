# Quan sát log, metric và trace mà không ghi lộ dữ liệu nhạy cảm

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt vai trò của log, metric và trace khi vận hành ứng dụng Spring Data Neo4j (SDN).
- Thiết kế log có cấu trúc để chẩn đoán lỗi repository, Cypher, transaction và kết nối.
- Bật logger của SDN và Neo4j Java Driver đúng mục đích, có kiểm soát.
- Cấu hình query log của Neo4j để quan sát truy vấn chậm mà không ghi lộ parameter hoặc literal nhạy cảm.
- Thu thập metric ứng dụng, repository, Driver và Neo4j server.
- Kết nối trace ID/span ID với log để theo dõi một request qua nhiều tầng.
- Dùng Micrometer Observation để bổ sung quan sát cho nghiệp vụ graph.
- Giới hạn cardinality, sampling, retention và quyền truy cập vào hệ thống quan sát.

## 1. Vì sao ứng dụng SDN cần observability?

Một request trong ứng dụng Spring Boot có thể đi qua controller, service, repository, SDN mapping layer, Neo4j Java Driver và Neo4j DBMS. Khi request chậm hoặc thất bại, chỉ nhìn HTTP status thường không đủ để xác định nguyên nhân.

Ví dụ, API tìm người dùng trả về 500 hoặc mất 4 giây. Nguyên nhân có thể là:

- Repository sinh Cypher không phù hợp.
- Query phải mở rộng quá nhiều relationship.
- Neo4j chờ lock hoặc chờ connection từ pool.
- Kết nối Bolt gặp timeout hoặc lỗi TLS.
- Mapping một graph lớn thành object mất nhiều thời gian.
- Một dependency khác trong cùng request bị chậm.
- Một transaction giữ tài nguyên quá lâu.

Observability (khả năng quan sát) thường được xây dựng từ ba tín hiệu:

| Tín hiệu | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Log | Điều gì đã xảy ra và tại sao? | Query bị từ chối, connection timeout, transaction rollback |
| Metric | Hệ thống đang hoạt động ở mức nào? | Request rate, error rate, latency p95, connection pool usage |
| Trace | Một request đã đi qua những bước nào và mất thời gian ở đâu? | HTTP request → service → repository → Neo4j operation |

Ba tín hiệu bổ sung cho nhau. Metric giúp phát hiện xu hướng hoặc bất thường; trace định vị đoạn xử lý chậm trong một request; log cung cấp chi tiết sự kiện và nguyên nhân.

Observability không đồng nghĩa với ghi mọi dữ liệu. Một hệ thống có thể rất nhiều log nhưng vẫn khó chẩn đoán, đồng thời tạo ra rủi ro lộ thông tin. Mục tiêu là thu thập đủ dữ liệu kỹ thuật để giải thích hành vi của hệ thống, theo nguyên tắc tối thiểu hóa dữ liệu.

## 2. Xác định dữ liệu nhạy cảm trước khi bật log

Trong ứng dụng graph, thông tin nhạy cảm có thể xuất hiện ở nhiều vị trí:

- Property của node như email, số điện thoại, địa chỉ, tên thật, ngày sinh.
- Property của relationship như vai trò, quan hệ giữa người dùng hoặc trạng thái phê duyệt.
- Parameter của Cypher.
- Literal được viết trực tiếp trong query.
- Token, password, connection URI hoặc thông tin xác thực.
- Exception message có chứa query, parameter hoặc dữ liệu đầu vào.
- Trace baggage, span attribute hoặc custom tag.
- File dump, support bundle, ảnh chụp màn hình và dữ liệu gửi cho nhà cung cấp.

Hãy phân loại trước khi triển khai:

| Nhóm dữ liệu | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Dữ liệu kỹ thuật nội bộ | Tên service, version, môi trường | Có thể ghi theo chính sách vận hành |
| Metadata ít nhạy cảm | Tên repository, tên method, database alias | Ghi khi cần, giới hạn tập giá trị |
| Định danh có thể liên kết người dùng | Email, account ID, tenant ID, node ID | Không đưa vào metric tag; chỉ ghi nếu có lý do và chính sách cho phép |
| Dữ liệu nghiệp vụ | Tên, địa chỉ, nội dung node, property relationship | Không ghi toàn bộ object hoặc parameter map |
| Bí mật xác thực | Password, bearer token, private key | Tuyệt đối không ghi |
| Nội dung query | Cypher literal, parameter, exception details | Parameterize, obfuscate và kiểm soát query logging |

Một trace ID ngẫu nhiên hoặc correlation ID kỹ thuật thường đủ để nối các sự kiện. Không cần đưa email, số điện thoại hoặc node ID của người dùng vào log chỉ để tìm lại một request.

## 3. Thiết kế log có cấu trúc cho service SDN

Log ứng dụng nên mô tả sự kiện theo dạng có thể tìm kiếm và tổng hợp. Một log tốt thường chứa:

- Timestamp và log level.
- Service name, environment và application version.
- Trace ID/span ID hoặc correlation ID.
- Tên operation nghiệp vụ, ví dụ person.search hoặc order.create.
- Kết quả như success, not-found, validation-error hoặc database-error.
- Thời gian xử lý nếu cần chẩn đoán.
- Error type hoặc status code, không kèm secret và payload nhạy cảm.

Ví dụ log an toàn:

~~~text
2026-11-26T09:15:30.124Z INFO
service=people-api
operation=person.search
repository=PersonRepository
outcome=SUCCESS
duration_ms=42
traceId=8f3a...c912
spanId=2b71...aa09
~~~

Ví dụ này cho biết operation nào được thực hiện, repository nào liên quan và thời gian xử lý. Nó không ghi email, tên người dùng hoặc giá trị parameter.

Không nên ghi:

~~~text
Searching person email=alice@example.com
Cypher params={email: "alice@example.com", token: "..."}
Entity saved: Person{id=..., name=..., phone=...}
~~~

Những log này có thể đưa dữ liệu cá nhân hoặc credential vào hệ thống tập trung, nơi có nhiều người và công cụ truy cập hơn database gốc.

### 3.1. Log exception mà không làm lộ nội dung

Khi bắt lỗi ở service, ghi loại lỗi và operation. Chỉ đính kèm stack trace khi cần chẩn đoán và đã đánh giá nội dung exception có thể chứa gì.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class PersonService {

    private static final Logger log =
        LoggerFactory.getLogger(PersonService.class);

    private final PersonRepository repository;

    public PersonService(PersonRepository repository) {
        this.repository = repository;
    }

    public Person findById(String id) {
        try {
            return repository.findById(id)
                .orElseThrow(() -> new PersonNotFoundException());
        } catch (PersonNotFoundException ex) {
            log.info("operation=person.find outcome=NOT_FOUND");
            throw ex;
        } catch (RuntimeException ex) {
            log.error(
                "operation=person.find outcome=ERROR errorType={}",
                ex.getClass().getSimpleName()
            );
            throw ex;
        }
    }
}
~~~

Ví dụ cố ý không ghi giá trị id và không truyền toàn bộ exception message vào log. Trong hệ thống thực tế, có thể ghi stack trace ở một logger có quyền truy cập hạn chế, sau khi kiểm tra rằng message và cause chain không chứa dữ liệu nhạy cảm.

Không dùng log.error với toàn bộ ex.getMessage() một cách mặc định. Error message từ database, driver hoặc tầng mapping đôi khi chứa query, parameter hoặc dữ liệu đầu vào.

## 4. Log Cypher notification của Spring Data Neo4j

Từ Spring Data Neo4j 7.1.5, SDN cung cấp nhóm logger cho Cypher notification. Logger gốc:

**org.springframework.data.neo4j.cypher**

bao gồm các statement được SDN gọi và notification trả về từ Neo4j server. Một số logger con cho phép tách loại notification:

| Logger | Nội dung |
| --- | --- |
| org.springframework.data.neo4j.cypher.performance | Cảnh báo hoặc notification liên quan hiệu năng |
| org.springframework.data.neo4j.cypher.hint | Notification về query hint |
| org.springframework.data.neo4j.cypher.unrecognized | Notification chưa được nhận diện |
| org.springframework.data.neo4j.cypher.unsupported | Notification không được hỗ trợ |
| org.springframework.data.neo4j.cypher.deprecation | Cảnh báo API hoặc cú pháp đã deprecated |
| org.springframework.data.neo4j.cypher.generic | Notification tổng quát |
| org.springframework.data.neo4j.cypher.security | Notification liên quan bảo mật |
| org.springframework.data.neo4j.cypher.topology | Notification liên quan topology |

Có thể cấu hình logger trong application.yml:

~~~yaml
logging:
  level:
    org.springframework.data.neo4j.cypher: INFO
    org.springframework.data.neo4j.cypher.performance: WARN
    org.springframework.data.neo4j.cypher.deprecation: WARN
~~~

Khi cần điều tra một query trong môi trường dev/test, có thể tạm nâng logger SDN lên DEBUG theo tài liệu của phiên bản đang dùng. Không bật mức log chi tiết trên production trong thời gian dài nếu chưa kiểm tra nội dung statement, retention và quyền truy cập log.

Logger này giúp phát hiện query hoặc notification phát sinh từ repository. Nó không thay thế query log phía Neo4j server và không cung cấp đầy đủ số liệu runtime như PROFILE.

### 4.1. Parameterize query ngay từ đầu

Dùng parameter thay vì nối chuỗi hoặc nhúng dữ liệu người dùng vào Cypher literal:

~~~java
import java.util.Optional;

import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
    MATCH (p:Person)
    WHERE p.email = $email
    RETURN p
    """)
Optional<Person> findByEmail(@Param("email") String email);
~~~

Parameterization giúp giữ query shape ổn định, giảm rủi ro injection và hỗ trợ masking literal ở phía server. Tuy nhiên, parameterization không tự bảo đảm parameter value sẽ không xuất hiện trong query log. Cần cấu hình query logging phù hợp ở Neo4j.

## 5. Cấu hình query log an toàn trên Neo4j

Neo4j có query log để ghi nhận các query được thực thi. Query log rất hữu ích khi tìm truy vấn chậm, nhưng có thể chứa query text, parameter và error details.

Ở các phiên bản Neo4j hiện hành, db.logs.query.enabled có thể dùng:

- OFF: tắt query log.
- INFO: chỉ ghi query vượt ngưỡng db.logs.query.threshold.
- VERBOSE: ghi điểm bắt đầu và kết thúc của mọi query.

Giá trị mặc định hiện hành là VERBOSE, vì vậy cần xem lại cấu hình thực tế của môi trường production thay vì giả định query log chỉ ghi truy vấn chậm.

Một cấu hình khởi đầu thận trọng cho production:

~~~properties
db.logs.query.enabled=INFO
db.logs.query.threshold=500ms
db.logs.query.parameter_logging_enabled=false
db.logs.query.obfuscate_literals=true
db.logs.query.obfuscate_errors=true
~~~

Ý nghĩa:

- INFO kết hợp ngưỡng 500 ms chỉ ghi các query mất thời gian vượt ngưỡng.
- parameter_logging_enabled=false ngăn parameter values xuất hiện trong query log.
- obfuscate_literals=true che literal trong query text.
- obfuscate_errors=true che thông tin nhạy cảm có thể nằm trong error details; setting này được giới thiệu từ Neo4j 2026.01.

Điều cần nhớ: obfuscate_literals không che parameter values. Vì vậy, nếu không cần parameter để điều tra, hãy tắt parameter logging. Nếu cần xem parameter trong một sự cố cụ thể, hãy bật tạm thời theo quy trình có phê duyệt, giới hạn thời gian, quyền đọc log và dữ liệu test phù hợp.

obfuscate_errors và obfuscate_literals cũng không thay thế việc kiểm soát quyền truy cập, retention và chia sẻ log. Kiểm tra các setting được hỗ trợ trong đúng phiên bản Neo4j trước khi áp dụng.

### 5.1. Không bật raw query logging trên production

Neo4j có setting db.logs.query.early_raw_logging_enabled. Setting này cho phép ghi query text và parameters sớm, trước khi quá trình parse có thể obfuscate password.

Không bật setting này trên production trừ khi có tình huống điều tra đặc biệt, kiểm soát quyền truy cập và quy trình xử lý dữ liệu rõ ràng.

Khi thay đổi chính sách obfuscation, lưu ý query cache có thể khiến thay đổi không tác động ngay tới query đã cache. Tài liệu Neo4j hướng dẫn clear query cache nếu cần áp dụng obfuscation mới ngay lập tức. Chỉ thực hiện thao tác này khi đã đánh giá ảnh hưởng vận hành.

### 5.2. Query log có thể chứa thông tin ngoài query text

Ngoài query text, log có thể chứa:

- Database name và username.
- Client address và connection details.
- Query parameters nếu được bật.
- Transaction metadata.
- Error details.
- Query plan nếu bật db.logs.query.plan_description_enabled.

Chỉ bật plan description khi cần phân tích hiệu năng có kiểm soát. Setting này có chi phí bổ sung và không nên bật mặc định cho mọi query production.

## 6. Log của Neo4j Java Driver

Neo4j Java Driver có log riêng để chẩn đoán hoạt động kết nối và giao tiếp Bolt. Các nhóm logger thường gặp:

- org.neo4j.driver: hoạt động của Driver.
- org.neo4j.bolt.connection: giao tiếp Bolt và connection.

Driver hiện hành dùng Java System.Logger mặc định. Có thể điều chỉnh mức log qua cấu hình logging của JVM hoặc tích hợp với logging backend của ứng dụng theo phiên bản Driver.

Không bật mức chi tiết cao trên production. Tài liệu Driver cảnh báo log ở mức FINER có thể chứa dữ liệu nhạy cảm, ví dụ database credential. Log trace giao thức có thể tạo rất nhiều dữ liệu và làm tăng chi phí vận hành.

Khi cần điều tra kết nối:

1. Bắt đầu từ log mức INFO/WARN/ERROR.
2. Ghi nhận endpoint đã loại bỏ thông tin xác thực.
3. Tạm bật mức chi tiết hơn cho một instance hoặc một khoảng thời gian ngắn.
4. Lọc log theo thời gian và correlation ID.
5. Tắt mức log chi tiết sau khi thu thập đủ dữ liệu.
6. Kiểm tra và redaction trước khi gửi log ra ngoài tổ chức.

Không gửi log Driver chưa kiểm tra cho ticket hỗ trợ hoặc kênh chat bên ngoài. Coi log mức chi tiết là dữ liệu vận hành nhạy cảm.

## 7. Phân biệt các file log phía Neo4j server

Tùy edition và cấu hình, Neo4j có các file log phục vụ những mục đích khác nhau:

| Log | Mục đích |
| --- | --- |
| neo4j.log | Thông tin vận hành chung |
| debug.log | Chi tiết phục vụ chẩn đoán sự cố và hỗ trợ |
| query.log | Query được thực thi, thời gian và thông tin liên quan |
| security.log | Sự kiện bảo mật như authentication, tùy edition/cấu hình |
| gc.log | Hoạt động garbage collection của JVM |

Neo4j dùng Log4j 2 để quản lý log server. Cần cấu hình rotation, retention, quyền truy cập file và chuyển log sang hệ thống tập trung theo chính sách vận hành.

Không sửa định dạng mặc định của debug.log nếu không có lý do rõ ràng. Neo4j khuyến nghị giữ định dạng này để hỗ trợ điều tra sự cố. Nếu cần định dạng khác, tạo appender bổ sung thay vì thay thế log gốc.

Query log và security log có khả năng chứa thông tin nhạy cảm. Quyền truy cập file, quyền tải log, backup và retention phải được bảo vệ như dữ liệu vận hành có kiểm soát.

## 8. Metrics cho ứng dụng Spring Boot và SDN

Metric là số liệu tổng hợp theo thời gian. Nó giúp phát hiện xu hướng mà không cần lưu từng bản ghi request.

Với Spring Boot, Actuator cung cấp hạ tầng Micrometer. Có thể dùng registry để xuất metric sang Prometheus, OTLP hoặc hệ thống giám sát khác.

Dependency cơ bản:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Phiên bản dependency nên được quản lý bởi Spring Boot BOM/plugin của dự án.

Các nhóm metric hữu ích:

| Nhóm | Metric hoặc chỉ số nên theo dõi |
| --- | --- |
| HTTP | Request count, error rate, latency p50/p95/p99 |
| Repository | Số invocation, success/error/cancel, duration |
| Neo4j connection | Connection acquisition timeout, pool saturation, reconnect |
| Transaction | Transaction duration, rollback, retry, lock wait |
| JVM | Heap, garbage collection, thread count |
| Neo4j server | CPU, page cache, transaction, Bolt connection, checkpoint |
| Business operation | Tỷ lệ thành công của graph search, relationship traversal, batch update |

Metric nên có tập tag hữu hạn. Ví dụ repository=PersonRepository, method=findByEmail, outcome=SUCCESS là những giá trị có số lượng giới hạn.

Không dùng email, account ID, node ID, tenant ID, query text hoặc parameter làm metric tag. Mỗi giá trị mới có thể tạo một time series mới, khiến cardinality tăng không kiểm soát và gây quá tải monitoring backend.

## 9. Spring Data repository metrics

Spring Boot có thể tự động instrument các lời gọi Spring Data Repository. Metric mặc định:

**spring.data.repository.invocations**

Các tag mặc định gồm:

- repository: tên class repository.
- method: tên method được gọi.
- state: SUCCESS, ERROR, CANCELED hoặc RUNNING.
- exception: tên class exception nếu có.

Đây là nguồn dữ liệu hữu ích để so sánh repository nào được gọi nhiều, method nào hay lỗi và thời gian xử lý biến động ra sao.

Nếu không muốn instrument tất cả repository invocation, có thể tắt tự động instrumentation bằng:

~~~yaml
management:
  metrics:
    data:
      repository:
        autotime:
          enabled: false
~~~

Sau đó chỉ instrument các method cần thiết bằng @Timed hoặc Observation API. Tránh gắn nhiều lớp instrumentation lên cùng một method vì có thể tạo metric hoặc span trùng lặp.

## 10. Quan sát hoạt động của Neo4j Driver

Ở Spring Boot 4.2, auto-configuration đăng ký MicrometerObservationProvider cho Neo4j Driver được auto-configure. Điều này cho phép hoạt động Driver tham gia hệ thống Micrometer Observation khi cấu hình observability phù hợp.

Khả năng tích hợp có thể khác giữa các dòng Spring Boot và Neo4j Java Driver. Khi nâng cấp hoặc dùng custom Driver bean, cần kiểm tra tài liệu đúng phiên bản và bảo đảm observation provider được cấu hình cho Driver thực tế.

Không nên giả định rằng chỉ thêm Actuator là mọi query SDN đều có trace chi tiết như một span riêng. Cần xác minh bằng trace thực tế:

- HTTP request có span hay không.
- Service operation có được biểu diễn không.
- Repository invocation có metric tương ứng không.
- Driver/Neo4j operation có span con không.
- Trace ID có được nối qua reactive pipeline không.

Nếu chưa có span ở tầng database, có thể bổ sung Observation ở service layer để đo thời gian nghiệp vụ gọi repository. Tránh tạo thêm span trùng cho mọi repository method nếu Spring Boot đã instrument sẵn.

## 11. Tạo Observation cho thao tác graph

Micrometer Observation cung cấp API chung cho metric và trace. Có thể dùng ObservationRegistry để đo một operation có ý nghĩa nghiệp vụ.

Ví dụ:

~~~java
import java.util.List;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class PersonSearchService {

    private final PersonRepository repository;
    private final ObservationRegistry observationRegistry;

    public PersonSearchService(
            PersonRepository repository,
            ObservationRegistry observationRegistry) {
        this.repository = repository;
        this.observationRegistry = observationRegistry;
    }

    public List<Person> searchByStatus(String status) {
        return Observation.createNotStarted(
                "neo4j.person.search",
                observationRegistry
            )
            .lowCardinalityKeyValue("db.system", "neo4j")
            .lowCardinalityKeyValue("operation", "person-search")
            .lowCardinalityKeyValue("result.type", "list")
            .observe(() -> repository.findAllByStatus(status));
    }
}
~~~

Ví dụ chỉ gắn các tag có số lượng giá trị hữu hạn. Không gắn status nếu đó là giá trị tự do do người dùng nhập, và không gắn email, personId hoặc toàn bộ parameter map.

Các tag có cardinality thấp có thể được dùng cho metric và trace. Giá trị cardinality cao chỉ nên xuất hiện trong trace khi có lý do rõ ràng, và vẫn phải tuân thủ chính sách dữ liệu nhạy cảm.

Nếu method đã được repository auto-instrument, Observation ở service layer nên mô tả operation nghiệp vụ lớn hơn thay vì lặp lại cùng tên và cùng phạm vi đo.

## 12. Metrics phía Neo4j server

Metric ở ứng dụng cho biết request nhìn từ client. Metric phía server cho biết DBMS đang sử dụng tài nguyên như thế nào.

Với Neo4j Enterprise Edition, có thể thu thập metric qua CSV, JMX, Neo4j Ops Manager hoặc hệ thống monitoring bên ngoài như Prometheus.

Một số nhóm metric quan trọng:

- Bolt connection và network.
- Transaction count, active transaction và transaction duration.
- Page cache hit/miss và eviction.
- Checkpoint và transaction log.
- JVM heap, garbage collection, thread và CPU.
- Store size và database operation.

Một số metric có thể được bật hoặc lọc qua cấu hình server.metrics.enabled và server.metrics.filter. Chỉ bật những nhóm cần theo dõi để kiểm soát chi phí và lượng dữ liệu.

Metric phía server và metric phía ứng dụng phải được đọc cùng nhau. Ví dụ:

- API latency tăng, nhưng Neo4j CPU thấp: kiểm tra connection pool, network hoặc thời gian mapping.
- API latency tăng, Neo4j CPU cao: kiểm tra query plan và workload database.
- Page cache miss tăng mạnh: xem working set và cấu hình memory.
- Connection acquisition timeout tăng: kiểm tra pool size, session lifecycle và query duration.
- Transaction duration tăng nhưng query duration thấp: kiểm tra khoảng thời gian giữ transaction sau khi query hoàn tất.

Neo4j server metrics có giới hạn theo edition. Nếu dùng Community hoặc Aura, hãy kiểm tra các công cụ monitoring được cung cấp cho deployment đó thay vì giả định toàn bộ cấu hình CSV/JMX/Prometheus của Enterprise đều khả dụng.

## 13. Tracing với Spring Boot và Micrometer

Trace mô tả hành trình của một request qua nhiều component. Một trace có thể gồm các span:

~~~text
HTTP GET /api/people
└── PersonSearchService.search
    └── PersonRepository.findAllByStatus
        └── Neo4j Driver operation
            └── Bolt request
~~~

Spring Boot hỗ trợ Micrometer Tracing với các bridge như OpenTelemetry hoặc Brave. Ví dụ dùng OpenTelemetry và OTLP:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("io.micrometer:micrometer-tracing-bridge-otel")
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")
}
~~~

Cấu hình sampling:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

Spring Boot mặc định sample khoảng 10% request trong cấu hình tracing tiêu chuẩn để hạn chế lượng trace gửi đi. Giá trị 1.0 gửi mọi request và thường chỉ phù hợp với môi trường kiểm thử hoặc điều tra trong thời gian ngắn.

Cấu hình exporter theo collector/endpoint của tổ chức bằng nhóm property management.otlp.tracing.*. Cần có OpenTelemetry Collector hoặc trace backend tương ứng để nhận và lưu trace.

Khi Micrometer Tracing được bật, Spring Boot có thể đưa traceId và spanId vào MDC để correlation ID xuất hiện trong log mặc định. Nhờ đó, có thể tìm log thuộc cùng request trong khi xem trace ở backend.

## 14. Truyền context qua reactive pipeline

Với reactive SDN, execution có thể chuyển thread và scheduler. Log correlation và tracing phụ thuộc vào việc truyền observation context đúng qua Reactor pipeline.

Spring Boot dùng Context Propagation để chuyển observation context qua thread và reactive pipeline. Nếu trace ID biến mất sau publishOn, subscribeOn hoặc một đoạn xử lý async, hãy kiểm tra context propagation của phiên bản đang dùng.

Có thể bật automatic Reactor context propagation bằng:

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

Với @Async và executor tùy chỉnh, cần kiểm tra cấu hình propagation riêng. Không tự sao chép trace ID vào parameter Cypher hoặc property graph để thay thế context propagation.

Khi kiểm thử, tạo một request reactive có nhiều bước, xác nhận trace ID xuất hiện ở log đầu request và các log sau khi chuyển scheduler. Kiểm tra trace backend có một trace liên tục thay vì nhiều trace không liên kết.

## 15. Bảo vệ Actuator và endpoint monitoring

Actuator cung cấp endpoint để kiểm tra health và metric. Endpoint metrics không được expose qua HTTP mặc định; cần cấu hình rõ. Ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    health:
      show-details: when-authorized
~~~

Để dùng prometheus, cần có Micrometer Prometheus registry tương ứng.

Không expose toàn bộ Actuator endpoint ra internet. Đặc biệt, các endpoint như env, configprops, heapdump, loggers hoặc threaddump có thể tiết lộ cấu hình, thông tin runtime hoặc dữ liệu nhạy cảm.

Nguyên tắc triển khai:

- Chỉ expose endpoint cần thiết.
- Bảo vệ bằng authentication/authorization và network policy.
- Chỉ cho phép monitoring system truy cập endpoint metric.
- Giới hạn quyền người vận hành theo vai trò.
- Không trả chi tiết database hoặc stack trace cho người dùng API thông thường.
- Tách management port/network nếu kiến trúc yêu cầu.
- Kiểm tra lại cấu hình endpoint sau mỗi lần nâng cấp Spring Boot.

## 16. Correlation ID và transaction metadata

Correlation ID giúp nối log ứng dụng với trace. Trace ID/span ID thường được quản lý tự động bởi Micrometer Tracing và MDC.

Nếu cần thêm metadata vào transaction để tìm query trong Neo4j query log, Neo4j Driver hỗ trợ transaction metadata. Ví dụ, một thao tác có thể gắn:

~~~json
{
  "app": "people-api",
  "operation": "person-search",
  "traceId": "8f3a...c912"
}
~~~

Chỉ gắn metadata kỹ thuật cần thiết. Không đưa email, access token, raw request payload hoặc node property vào transaction metadata vì metadata có thể xuất hiện trong query log và công cụ quản trị transaction.

Nếu thao tác đi qua SDN transaction manager, hãy kiểm tra extension point hoặc cấu hình transaction phù hợp của phiên bản SDN trước khi giả định có thể gắn metadata trực tiếp như Driver API. Không mở một transaction thủ công chỉ để gắn trace metadata nếu điều đó làm thay đổi ranh giới transaction của repository.

## 17. Quy trình điều tra một request chậm

Khi một API dùng SDN chậm, có thể làm theo trình tự:

1. Tìm request trong log bằng trace ID hoặc correlation ID.
2. Xem trace để xác định span nào chiếm nhiều thời gian.
3. Nếu thời gian nằm ở service trước repository, kiểm tra logic nghiệp vụ hoặc dependency khác.
4. Nếu thời gian nằm ở repository/Driver, lấy tên method và operation tương ứng.
5. Kiểm tra Neo4j query log để xem thời gian query và database liên quan.
6. Kiểm tra metric server như CPU, transaction, page cache và Bolt connection.
7. Nếu query chậm, chạy EXPLAIN hoặc PROFILE trong môi trường phù hợp để phân tích execution plan.
8. Nếu query nhanh nhưng request chậm, kiểm tra mapping graph, số lượng record, network và serialization.
9. Thực hiện một thay đổi có kiểm soát.
10. So sánh metric và trace trước/sau trong điều kiện tương đương.

Không dùng một metric riêng lẻ để kết luận nguyên nhân. Ví dụ, CPU Neo4j thấp không chứng minh database không liên quan; ứng dụng có thể đang chờ connection, lock hoặc network.

## 18. Retention, sampling và quyền truy cập log

Log, metric và trace có vòng đời khác nhau. Không cần giữ mọi dữ liệu chi tiết trong cùng một thời gian.

| Dữ liệu | Chính sách cần xác định |
| --- | --- |
| Application log | Retention, rotation, redaction và quyền đọc |
| Query log | Ngưỡng ghi, obfuscation, retention và quyền DBA |
| Security log | Retention theo chính sách bảo mật và điều tra |
| Metrics | Độ phân giải, thời gian lưu và cardinality |
| Trace | Sampling, retention, access control và redaction |
| Support bundle | Kiểm tra và làm sạch trước khi chia sẻ |

Sampling trace giúp kiểm soát dung lượng. Tuy nhiên, các request lỗi nghiêm trọng có thể cần cơ chế tail-based sampling ở collector để giữ lại trace có lỗi hoặc latency cao.

Không gửi dữ liệu nhạy cảm vào baggage vì baggage có thể được truyền qua nhiều service và exporter. Chỉ đưa metadata cần thiết, ít nhạy cảm và có phạm vi sử dụng rõ ràng.

## 19. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Ghi toàn bộ entity vào log | Lộ property cá nhân và dữ liệu nghiệp vụ | Chỉ ghi operation, outcome và thời gian |
| Ghi query parameter | Lộ email, token hoặc dữ liệu tìm kiếm | Tắt parameter logging hoặc masking theo chính sách |
| Nghĩ obfuscate_literals che cả parameter | Parameter vẫn có thể xuất hiện trong log | Đặt parameter_logging_enabled=false |
| Bật VERBOSE query log lâu dài | Ghi mọi query, tăng log volume và exposure | Dùng INFO với threshold phù hợp |
| Bật Driver FINER/TRACE trên production | Có thể lộ credential và dữ liệu giao thức | Chỉ bật tạm thời, giới hạn quyền và redaction |
| Đưa user ID vào metric tag | Cardinality tăng không kiểm soát | Dùng tag hữu hạn như repository/operation/outcome |
| Đưa raw Cypher vào metric tag | Mỗi query shape tạo time series riêng | Dùng operation name cố định |
| Bật sampling 100% trên production | Tăng chi phí lưu trữ và exporter | Chọn sampling phù hợp, dùng tail sampling nếu cần |
| Không có trace ID trong log | Khó nối log giữa các tầng | Bật Micrometer Tracing và kiểm tra MDC |
| Reactive trace bị đứt | Context không được truyền qua scheduler | Kiểm tra Reactor context propagation |
| Bật Actuator toàn bộ | Lộ cấu hình và dữ liệu runtime | Chỉ expose endpoint cần thiết và bảo vệ |
| Nhầm metric ứng dụng với metric server | Không xác định được bottleneck | Kết hợp cả hai nguồn |
| Thêm @Observed lên repository đã auto-instrument | Metric/span trùng lặp | Kiểm tra instrumentation hiện có |
| Chia sẻ support bundle nguyên trạng | Query hoặc parameter có thể lộ dữ liệu | Obfuscate, rà soát và phê duyệt trước khi gửi |
| Dùng log thay audit trail | Không bảo đảm tính đầy đủ và bất biến | Thiết kế audit/event history riêng khi nghiệp vụ yêu cầu |

## 20. Checklist observability an toàn cho SDN

Trước khi đưa ứng dụng lên production, kiểm tra:

- [ ] Log có cấu trúc, có timestamp, service, environment và operation.
- [ ] Log có trace ID/correlation ID để nối các tầng.
- [ ] Không ghi password, token, private key hoặc full connection string.
- [ ] Không ghi toàn bộ entity, node properties hoặc relationship properties.
- [ ] Query sử dụng parameter thay vì nối chuỗi.
- [ ] Query log có threshold và chính sách parameter logging rõ ràng.
- [ ] Literal và error details được obfuscate theo phiên bản Neo4j hỗ trợ.
- [ ] Driver log mức chi tiết cao chỉ bật khi cần và có thời hạn.
- [ ] Repository metrics được theo dõi với tag cardinality thấp.
- [ ] Có metric request rate, error rate và latency percentile.
- [ ] Có metric hoặc dashboard cho connection, transaction và Neo4j server.
- [ ] Tracing có sampling phù hợp với production workload.
- [ ] Reactive context propagation được kiểm tra.
- [ ] Actuator endpoint được giới hạn và bảo vệ.
- [ ] Log/metric/trace có retention, rotation và quyền truy cập rõ ràng.
- [ ] Support bundle được kiểm tra trước khi chia sẻ.
- [ ] Log không được dùng thay cho audit trail nghiệp vụ.

## 21. Câu hỏi tự kiểm tra

1. Log, metric và trace khác nhau ở câu hỏi mà chúng trả lời như thế nào?
2. Vì sao observability không có nghĩa là ghi toàn bộ dữ liệu request?
3. Những property nào của node và relationship có thể là dữ liệu nhạy cảm?
4. Logger org.springframework.data.neo4j.cypher cung cấp thông tin gì?
5. Tại sao nên parameterize Cypher thay vì nối chuỗi?
6. Query log VERBOSE khác INFO như thế nào?
7. db.logs.query.obfuscate_literals có che parameter values không?
8. Vì sao cần tắt db.logs.query.parameter_logging_enabled khi không cần parameter?
9. Driver log FINER có rủi ro gì?
10. Metric spring.data.repository.invocations giúp theo dõi điều gì?
11. Vì sao không nên đưa email, user ID hoặc node ID vào metric tag?
12. Micrometer Observation có thể giúp bổ sung metric và trace như thế nào?
13. Spring Boot liên kết trace ID/span ID vào log bằng cơ chế nào?
14. Vì sao reactive pipeline cần context propagation?
15. Neo4j server metrics khác application metrics ở điểm nào?
16. Vì sao không expose toàn bộ Actuator endpoint?
17. Cần kiểm tra gì trước khi chia sẻ support bundle?
18. Khi request chậm nhưng query nhanh, cần kiểm tra thêm những tầng nào?

## Tài liệu tham khảo

- [Spring Data Neo4j – Logging](https://docs.spring.io/spring-data/neo4j/reference/appendix/logging.html)
- [Spring Boot – Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot – Metrics và Spring Data Repository Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot – Tracing và Correlation IDs](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot – Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Neo4j Operations Manual – Logging](https://neo4j.com/docs/operations-manual/current/monitoring/logging/)
- [Neo4j Operations Manual – Metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/)
- [Neo4j Java Driver – Advanced connection information and logging](https://neo4j.com/docs/java-manual/current/connect-advanced/)
- [Neo4j Java Driver API – ObservationProvider](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/observation/ObservationProvider.html)

## Kết luận

Observability cho ứng dụng Spring Data Neo4j cần kết hợp log, metric và trace. Log giải thích sự kiện; metric cho biết xu hướng và mức độ tải; trace giúp theo dõi một request qua service, repository, Driver và database. Khi đọc cả ba tín hiệu, đội vận hành có thể xác định query chậm, connection pool bị nghẽn, transaction kéo dài hoặc lỗi mapping mà không cần ghi toàn bộ dữ liệu nghiệp vụ.

An toàn dữ liệu phải được thiết kế ngay từ cấu hình. Hãy parameterize Cypher, kiểm soát SDN và Driver logger, tắt parameter logging khi không cần, bật obfuscation phù hợp, giới hạn metric tag và bảo vệ Actuator. Với tracing, dùng trace ID/span ID để nối log, chọn sampling phù hợp và bảo đảm context được truyền qua reactive pipeline. Thu thập đúng dữ liệu kỹ thuật, giới hạn retention và quyền truy cập sẽ giúp hệ thống graph dễ vận hành mà không biến log, metric hay trace thành một nguồn rò rỉ dữ liệu mới.
