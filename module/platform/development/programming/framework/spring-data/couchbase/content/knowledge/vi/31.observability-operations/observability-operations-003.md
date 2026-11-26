# Log SDK, thông tin chẩn đoán và endpoint kết nối

## 1. Tại sao một lỗi kết nối khó chẩn đoán hơn dòng “database down”?

Ứng dụng **Spring Data Couchbase** đã startup và trả HTTP, nhưng thỉnh thoảng `findById` timeout, trong khi `findByCustomerId` lại báo lỗi Query Service. Một pod khác vẫn đọc Order bình thường. Nếu chỉ lưu dòng log `Couchbase unavailable`, đội vận hành khó biết đang hỏng:

- DNS/địa chỉ seed/bootstrap.
- Kết nối TCP, TLS hoặc certificate trust.
- Xác thực hay phân quyền trên bucket/scope/collection.
- Endpoint của **Data/KV**, **Query** hoặc một dịch vụ khác.
- Index chưa online hoặc query plan sai, dù Query Service vẫn chạy.
- Timeout do nghẽn tài nguyên, retry/cancellation hoặc tải tăng.
- Cache/mapping làm sai kết quả dù kết nối Couchbase bình thường.

Bài học thuộc chương **Quan sát và vận hành** của module **SPRING_DATA_COUCHBASE**: xây dựng tầng truy cập Couchbase bằng document mapping, `CouchbaseRepository`, `CouchbaseTemplate` và SQL++; đồng thời quan tâm bucket/scope/collection, index, TTL, CAS, giao dịch, reactive API và hiệu năng.

**Mục tiêu:** Bạn biết thu thập log có cấu trúc, bật logging SDK có giới hạn, sử dụng `ping()` và `diagnostics()` đúng ngữ nghĩa, hiểu cách SDK kết nối tới các service endpoints, tương quan với Actuator/metrics/traces, phân loại lỗi timeout–TLS–RBAC–index, xây runbook và kiểm thử chẩn đoán an toàn.

**Nguyên tắc:** Không viết “Couchbase DOWN” nếu bằng chứng mới chỉ chứng minh **một operation trên một endpoint thất bại tại một thời điểm**.

## 2. Tình huống xuyên suốt: Orders API trên một cluster nhiều dịch vụ

Giả sử ứng dụng quản lý đơn hàng có:

~~~text
Bucket       : shop
Scope        : sales
Collection   : orders
Document ID  : order::o-1001
~~~

Một document minh họa:

~~~json
{
  "customerId": "c-1001",
  "status": "CREATED",
  "createdAt": "2026-11-25T08:00:00Z",
  "totalVnd": 540000
}
~~~

Các đường truy cập quan trọng:

| Chức năng | API Spring | Đường Couchbase |
| --- | --- | --- |
| Chi tiết Order | `repository.findById(id)` | KV theo key |
| Tạo Order | `repository.save(order)` | KV mutation, có thể dùng CAS/durability |
| Lịch sử Order | `findByCustomerId(id)` | SQL++ qua Query và thường GSI |
| Query động | `CouchbaseTemplate.findByQuery(...)` | SQL++, mapper/converter |
| Tìm kiếm toàn văn | Search SDK/API nếu triển khai | Search Service, Search index riêng |
| Báo cáo phân tích | Analytics nếu sử dụng | Analytics Service/dataset |

Ở mỗi đường, log cần đủ để trả lời **operation nào**, **keyspace nào**, **dịch vụ nào**, **kết quả/lỗi nào**, **độ trễ bao nhiêu**, nhưng không để lộ full document hoặc thông tin người dùng.

## 3. Bản đồ chẩn đoán: từ HTTP request tới service endpoint

~~~mermaid
flowchart LR
    CLIENT["HTTP client"] --> API["Controller / Service"]
    API --> REPO["Repository / CouchbaseTemplate"]
    REPO --> SDK["Java SDK ClusterEnvironment"]
    SDK --> BOOT["Bootstrap / config"]
    BOOT --> KV[("Data/KV endpoints")]
    BOOT --> Q[("Query endpoints")]
    Q --> IDX[("Index Service / GSI")]
    SDK --> SEARCH[("Search endpoints, nếu dùng")]
    SDK --> ANA[("Analytics endpoints, nếu dùng")]
    API --> LOG["App logs / trace spans"]
    SDK --> D["SDK events, diagnostics, metrics"]
~~~

Không phải API nào cũng gọi mọi service. Một KV `get` **không cần SQL++**; một câu `SELECT RAW 1` có thể chạy mà **không dùng GSI trên collection**. Khi thấy lỗi, hãy bắt đầu từ **đường thực sự được thực thi**, không gán ngay cho toàn cluster.

Một ứng dụng có thể vừa trả chi tiết Order thành công vừa lỗi lịch sử vì Query/Index. Một ping thành công tới KV endpoint cũng không chứng minh Query Service hoặc Search index khả dụng.

## 4. Năm loại bằng chứng bổ trợ nhau

| Nguồn | Câu hỏi chính | Giới hạn |
| --- | --- | --- |
| **Application structured logs** | Request nào, nghiệp vụ nào, operation gì, elapsed và kết quả? | Không tự biết trạng thái mọi SDK endpoint |
| **SDK/core event logs** | Bootstrap, connection, retry, timeout hoặc transport đang diễn biến ra sao? | Không tự chứng minh business correctness |
| **SDK ping result** | Endpoint/service được thử có phản hồi lúc kiểm tra không? | Không thay query trên đúng index/keyspace |
| **SDK diagnostics snapshot** | Client đang biết những endpoints và trạng thái kết nối nào? | Snapshot không nhất thiết là live request thành công |
| **Metrics/tracing/server dashboards** | Lỗi có lan rộng, p95/p99 tăng, Index Service backlog hay không? | Cần correlation theo thời điểm/topology |

Không có một nguồn “chính xác tuyệt đối” cho mọi sự cố. Một log timeout chỉ là điểm xuất phát; cần kết hợp **request timing, error type, endpoint, server metrics và kết quả phép thử khác**.

### 4.1. “Kết nối thành công” phải gắn phạm vi

`Cluster.connect(...)` tạo client/khởi động bootstrap theo semantics SDK; việc có đối tượng `Cluster` trong Spring Context không tự xác nhận mọi network request, mọi collection hay mọi index đã sẵn sàng. Ngay cả startup health UP cũng không bảo đảm request một giây sau sẽ không gặp outage.

### 4.2. Tín hiệu âm cũng cần ngữ cảnh

Không có log Query Service trong một request `findById` **không phải** Query Service khỏe hay lỗi; request KV vốn không cần Query. Cũng vậy, query trả 0 rows có thể là response thành công chứ không phải lỗi kết nối.

## 5. Hiểu các thành phần Java SDK trong Spring

Ví dụ kết nối được Spring Boot quản lý bằng `spring-boot-starter-data-couchbase`. SDK Java 3.x có các khái niệm:

- **ClusterEnvironment:** giữ cấu hình môi trường client như timeouts, I/O, tracing/metrics/logging options tùy phiên bản.
- **Cluster:** entry point cho truy cập cluster và các cluster-level operations như SQL++ query.
- **Bucket, Scope, Collection:** định vị data namespace cho KV và các thao tác tương ứng.
- **Service endpoints:** các địa chỉ mà SDK biết tới sau bootstrap/discovery, có thể khác seed node ban đầu.
- **Error context / diagnostics:** thông tin về operation/endpoint/lỗi mà SDK ghi nhận theo API và phiên bản.

**Không tạo một Cluster hoặc ClusterEnvironment mới cho mỗi HTTP request**. Spring quản lý lifecycle cho connection pool, bootstrap và tài nguyên I/O; tạo nhiều client gây chi phí và có thể làm sự cố trở nên tệ hơn.

### 5.1. Bootstrap seed không nhất thiết là tất cả endpoints

Connection string có thể nêu một hoặc vài seed addresses. Sau khi lấy cluster configuration, SDK kết nối tới các node/service endpoints thích hợp. Do đó, chỉ thử TCP tới **một seed node** rồi kết luận toàn bộ hoạt động là không đủ.

### 5.2. Khi nào `waitUntilReady` hữu ích?

SDK có những API chờ tài nguyên sẵn sàng trong timeout, ví dụ `bucket.waitUntilReady(Duration)`. Chúng hữu ích khi startup hoặc integration-test fixture cần chờ một điều kiện cụ thể, **không** thay quyền/query/index checks, và không nên gọi liên tục trong business request hay readiness probe.

## 6. Thiết lập log của Spring Boot và Java SDK có kiểm soát

Với các phiên bản dùng SLF4J/logging facade thích hợp, Spring Boot quản lý mức logger qua cấu hình:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.data.couchbase: INFO
    com.couchbase.client: WARN
~~~

Khi điều tra trong thời gian giới hạn, có thể tăng mức cho phạm vi cần thiết, ví dụ:

~~~yaml
logging:
  level:
    org.springframework.data.couchbase: DEBUG
    com.couchbase.client.core: DEBUG
~~~

Đây là **mẫu cấu hình logger category** thường dùng, cần xác minh logger name/output thực tế với phiên bản Spring Data/SDK đang chạy. Không mặc định SDK mọi thế hệ đều dùng cùng category hay mọi class đều phát log như nhau.

### 6.1. DEBUG/TRACE là công cụ tạm thời, không phải trạng thái thường trực

- Log volume có thể tăng rất nhanh dưới tải.
- I/O, serialization và backend log ingestion có thể ảnh hưởng latency.
- Một số logs có thể chứa endpoint, query parameters, metadata hoặc thông tin nhạy cảm tùy API.
- TRACE có thể tạo chi phí lớn hơn DEBUG.
- Không cần bật cả root logger ở DEBUG chỉ để điều tra một Query timeout.

**Thực hành:** Giới hạn thời gian, số pod và phạm vi logger; xác định người chịu trách nhiệm tắt lại, không commit cấu hình debug dài hạn vào environment chung.

### 6.2. Dùng đúng một logging backend

Spring Boot thường tích hợp Logback trong cấu hình mặc định. Nếu ứng dụng dùng Log4j2 hoặc một backend khác, hãy bảo đảm binding và format tương thích; tránh nhiều logging bindings cùng lúc gây output bất ngờ. Không cần chỉnh nội bộ SDK bằng patch chỉ để bật logger.

## 7. Application logs: phải có correlation ID và operation boundary

SDK logs mô tả transport và operation theo góc nhìn client. Application logs thêm ngữ cảnh mà SDK không thể tự biết: request ID, endpoint, service method và user-visible outcome.

Một record có cấu trúc **giả định**:

~~~text
ts=2026-11-25T08:00:00Z
requestId=req-a83
route=GET /orders/{id}
dependency=couchbase
service=kv
operation=get
keyspace=shop.sales.orders
elapsedMs=47
outcome=success
~~~

Đối với một Query timeout:

~~~text
requestId=req-b24
route=GET /customers/{id}/orders
dependency=couchbase
service=query
operation=sqlpp
keyspace=shop.sales.orders
elapsedMs=1510
outcome=timeout
errorClass=UnambiguousTimeoutException
~~~

Hai record là **format minh họa do ứng dụng tự chọn**, không phải log tự động của Couchbase. Không sử dụng một tên exception giả làm bằng chứng SDK đang ném đúng loại đó; khi log ở runtime hãy lấy từ exception thực.

### 7.1. Những field hữu ích và an toàn

| Field | Giá trị sử dụng |
| --- | --- |
| `requestId/traceId` | Nối HTTP request với DB operation/span |
| `route` | Template route, **không** nguyên URL chứa PII |
| `operation` | `kv_get`, `kv_upsert`, `query`, `search` |
| `service` | KV/Query/Search/... để phân loại dependency |
| `keyspace` | Tên namespace đã duyệt theo policy |
| `durationMs` | Đo bằng monotonic clock |
| `outcome/errorCategory` | success, timeout, auth, missing index... |
| `retryAttempt` | Khi ứng dụng chủ động retry theo policy |
| `queryShape` | Tên query template cố định, không raw SQL++ có dữ liệu |

**Tránh** log document body, mật khẩu, access token, username đăng nhập, raw document ID gắn với người dùng hoặc full query parameters khi không có nhu cầu và quyền hợp lệ.

## 8. Ví dụ Spring service ghi log thời gian KV an toàn

Một service wrapper tối giản, dùng SLF4J và đo duration với `System.nanoTime()`:

~~~java
import java.util.NoSuchElementException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OrderDetailService {
    private static final Logger log =
            LoggerFactory.getLogger(OrderDetailService.class);

    private final OrderRepository repository;

    public OrderDetailService(OrderRepository repository) {
        this.repository = repository;
    }

    public OrderDocument getById(String documentId) {
        long startedNs = System.nanoTime();
        try {
            return repository.findById(documentId)
                    .orElseThrow(NoSuchElementException::new);
        } catch (RuntimeException failure) {
            long durationMs =
                    (System.nanoTime() - startedNs) / 1_000_000;

            log.warn(
                    "dependency=couchbase service=kv operation=get"
                    + " keyspace=shop.sales.orders durationMs={}"
                    + " errorClass={}",
                    durationMs,
                    failure.getClass().getSimpleName());

            throw failure;
        }
    }
}
~~~

Mã trên giả định `OrderRepository` đã được tạo và Order entity mapping hợp lệ. Nó **không log ID hoặc body**; trong dự án thực dùng trace/MDC để liên kết request.

### 8.1. Lỗi không tìm thấy document khác lỗi kết nối

`NoSuchElementException` ở ví dụ có thể phát sinh khi KV đọc thành công nhưng document không tồn tại. Nếu log mọi `RuntimeException` thành `couchbase down` thì đó là **phân loại sai**. Trong production hãy tách:

- `document_not_found`: điều kiện dữ liệu/API, có thể trả 404.
- `timeout`: operation quá deadline.
- `permission/authentication`: credential/RBAC.
- `transport/service_unavailable`: network/endpoint.
- `business_validation` hoặc optimistic-lock conflict: xử lý domain.

Ví dụ cố ý đơn giản để minh họa scope logging; handler và loại exception phải được chuẩn hóa theo dự án.

### 8.2. Không nuốt exception thành danh sách rỗng

Nếu SQL++ timeout, trả `Collections.emptyList()` có thể khiến người dùng tin “không có đơn hàng”. Giữ error semantics rõ để logs, metrics, API status và SLO có thể phát hiện outage.

## 9. Log một truy vấn SQL++ mà không tiết lộ parameter

Query theo customerId nên dùng parameter binding và đặt query template cố định:

~~~sql
SELECT META(o).id AS documentId, o.status, o.createdAt
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Ở service layer:

~~~text
operation=query
queryShape=orders_by_customer_recent
consistency=NOT_BOUNDED
parameterCount=1
returnedRows=20
durationMs=85
outcome=success
~~~

**Không log `customerId` nguyên văn**, đặc biệt khi đây là PII hoặc correlation key nhạy cảm. Hạn chế lưu raw SQL++ nếu nó có literal dữ liệu; ưu tiên tên template/plan ID ổn định.

### 9.1. Spring Data generated SQL++ khác câu query tự viết

Derived query hoặc `CouchbaseTemplate` có thể thêm type discriminator, alias hoặc mapping/projection. Khi kết quả khác SDK raw SQL++, hãy so generated query và mapping trước khi kết luận lỗi network/index. Bật log SQL++ chi tiết tạm thời trong môi trường được kiểm soát, sau đó tắt.

## 10. Phân loại timeout: biết thao tác nào chưa hoàn thành

Các tình huống cần phân biệt:

| Kịch bản | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **KV get timeout** | Không nhận phản hồi cho key đã biết | Kiểm tra Data endpoints, network, load, deadline |
| **Query timeout** | SQL++ không hoàn tất | Query/Index plan, scan consistency, capacity |
| **Write timeout ambiguous** | Không rõ server đã áp dụng mutation chưa | Xác minh qua key/idempotency; tránh retry tạo ID mới |
| **Bootstrap/discovery timeout** | Không lấy được cluster config | DNS, TCP/TLS, seed, firewall, alternate address |
| **Application HTTP timeout** | Client bỏ request trước khi SDK xong | Kiểm tra timeout budgets/cancellation |
| **SDK retry kéo dài** | Nhiều lần thử vì transient failure | Kiểm tra retry reason và tổng request latency |

Couchbase SDK phân biệt một số dạng timeout và failure context theo phiên bản. **Đừng giả định mọi timeout đều có nghĩa thao tác không thực thi**. Đặc biệt với write, client có thể không nhận được ACK dù server đã xử lý. Đặt idempotency key và chính sách xác minh kết quả theo nguồn có thẩm quyền.

### 10.1. Retry có thể khuếch đại sự cố

Một Query Service đang quá tải có thể bị nhiều client retry cùng lúc, làm p99 và backlog tăng thêm. Không retry vô hạn, không dùng UUID mới cho retry tạo Order, và không “tăng timeout lên vô hạn” như cách chữa lỗi thiếu index/RBAC.

## 11. Error context: hữu ích nhưng phải xem và che thông tin

Một exception SDK có thể cung cấp error context, retry reasons, service/endpoint/request ID hoặc timing details tùy loại operation/version.

**Khi đọc exception:**

1. Xác nhận exception class/category và operation được gọi.
2. Xem thời gian chờ, request lifecycle và có retry không.
3. Phân biệt lỗi trước/sau khi mutation có thể đã gửi.
4. Xác định endpoint và service có liên quan, nhưng **không tự suy một node lỗi thì cluster down**.
5. Đối chiếu server logs và metrics tương ứng thời điểm.
6. Chỉ đưa **trường đã qua redaction** vào logs công khai.

Không log `failure.toString()` hay toàn bộ exception context ở nơi người dùng bên ngoài truy cập. Stack trace và context có thể hữu ích trong hệ thống bảo mật nhưng phải có retention, quyền truy cập và quy tắc loại bỏ sensitive fields.

### 11.1. Exception type không thay root-cause analysis

`TimeoutException` chỉ là triệu chứng. Một query có thể timeout vì Index backlog, thiếu Query capacity, large sort, network latency hoặc client timeout budget quá thấp. Cần so với Query Service/Index Service metrics và query plan.

## 12. Ping và diagnostics: hai câu hỏi khác nhau

SDK Java 3.x có các entry points thuận tiện từ `Cluster`:

~~~java
import com.couchbase.client.java.Cluster;

public final class CouchbaseDiagnosticSampler {
    private final Cluster cluster;

    public CouchbaseDiagnosticSampler(Cluster cluster) {
        this.cluster = cluster;
    }

    public void sample() {
        var ping = cluster.ping();
        var snapshot = cluster.diagnostics();

        // Phân tích report theo service/endpoint bằng API đúng version.
        // Chỉ phát hành metric/status đã loại thông tin nhạy cảm.
        // Không đưa raw report vào HTTP response công khai.
    }
}
~~~

**Ping:** thực hiện phép thử reachability/response tới những loại dịch vụ và endpoints được SDK hỗ trợ trong phạm vi call/options.

**Diagnostics:** chụp trạng thái các endpoints/connection mà SDK đang biết; hữu ích để kiểm tra client view nhưng không nhất thiết tạo một query KV/SQL++ mới tới toàn bộ services.

### 12.1. Kết quả cần xem theo từng service/endpoint

Đừng chỉ đọc một boolean `allHealthy`, nếu API không thật sự hứa điều đó. Một report có thể biểu hiện:

~~~text
KV endpoint A        responsive
KV endpoint B        timeout
QUERY endpoint C     responsive
QUERY endpoint D     unavailable
SEARCH endpoint E    not observed / not configured
~~~

Đây là **sơ đồ minh họa**, không phải JSON output/enum cố định của SDK. `not observed` khác `DOWN`: dịch vụ có thể không được client dùng hoặc không nằm trong scope của phép thử.

### 12.2. Ping response không chứng minh Index readiness

Một Query endpoint có thể ping tốt nhưng named GSI `ix_orders_customer_created` chưa online. Kiểm tra Index qua metadata/management/query plan và query thật. `SELECT RAW 1` cũng không đi qua GSI của Orders.

### 12.3. Diagnostics là ảnh chụp, không phải dự báo

Endpoint healthy lúc chụp không loại trừ lỗi mới ngay sau đó. Một endpoint chưa có request trước đó có thể có trạng thái chưa đủ thông tin; không diễn giải thiếu quan sát thành outage chắc chắn.

## 13. Endpoint kết nối: seed, bootstrap, discovery và đường mạng

Một connection string minh họa:

~~~yaml
spring:
  couchbase:
    connection-string: couchbases://couchbase.example.internal
    username: YOUR_COUCHBASE_USERNAME
    password: YOUR_COUCHBASE_PASSWORD
  data:
    couchbase:
      bucket-name: shop
~~~

`couchbase://` thường diễn tả kết nối không TLS theo cấu hình, còn `couchbases://` định hướng kết nối TLS; cần thiết lập trust/certificates đúng môi trường. Dùng secret manager/environment injection cho credentials, không commit vào repository.

**Luồng khái niệm:**

~~~mermaid
flowchart TD
    A["Connection string seeds / DNS"] --> B["TCP và TLS handshake nếu bật"]
    B --> C["Cluster bootstrap/config discovery"]
    C --> D["SDK biết topology và service endpoints"]
    D --> E["KV request tới Data node"]
    D --> F["SQL++ request tới Query node"]
    D --> G["Search/Analytics request khi được dùng"]
~~~

Một seed host có thể chỉ là **điểm bắt đầu**; SDK cần reach tới những node/service endpoints quảng bá trong cluster config. Đường mạng tới seed thành công không tự chứng minh ứng dụng có thể kết nối tới mọi endpoint sau discovery.

## 14. DNS, TLS, NAT và alternate addresses

Khi app chạy trên Kubernetes, VM, VPN hoặc cloud private network, các vấn đề phổ biến:

- DNS tên seed không phân giải hoặc trả địa chỉ không thể route.
- DNS/SRV record và service discovery không phù hợp topology.
- Firewall/NetworkPolicy chỉ mở một cổng bootstrap nhưng chặn KV/Query endpoints.
- Cluster quảng bá **địa chỉ nội bộ** mà ứng dụng ngoài mạng không route tới.
- NAT/load balancer cần cơ chế **alternate addresses/external network configuration** phù hợp.
- TLS server certificate chưa được trust hoặc hostname không khớp SAN.
- Credential hợp lệ nhưng user thiếu quyền trên đúng collection.

### 14.1. Cẩn thận với ví dụ port

Các service Couchbase có cổng mặc định khác nhau cho TLS/non-TLS và có thể thay đổi theo deployment. Không dùng một danh sách port copy từ môi trường khác làm sự thật tuyệt đối. Hãy lấy **đúng endpoint/port quảng bá, phiên bản Server và network policy** trong cluster mục tiêu.

### 14.2. Network path khác nhau giữa các pod

Một pod ở node A có thể route được KV endpoints, pod ở node B không; hoặc proxy/service mesh chỉ áp với một namespace. So sánh cùng request/connection diagnostics giữa pods, tránh kết luận cluster lỗi toàn cục từ một pod.

### 14.3. TLS error khác authentication error

TLS handshake/trust failure xảy ra trước hoặc trong thiết lập kênh bảo mật. Authentication failure liên quan thông tin đăng nhập/cơ chế xác thực. Authorization failure xảy ra khi identity đã được nhận nhưng **không đủ quyền** cho operation. Ba loại lỗi dẫn tới ba hướng xử lý khác nhau.

## 15. Những phép kiểm tra kết nối tối thiểu, có giới hạn

| Phép thử | Kiểm tra được | Giới hạn |
| --- | --- | --- |
| DNS lookup seed | Phân giải tên | Không xác nhận TCP/TLS hoặc SDK config |
| TCP connect tới endpoint | Network reachability ở lớp kết nối | Không chứng minh authentication/operation |
| TLS handshake phù hợp | Trust/hostname/certificate path | Không chứng minh RBAC/query |
| SDK ping KV | Một số Data endpoints phản hồi | Không chứng minh đúng collection |
| SDK `Collection.exists` | Một KV operation trên collection | Không chứng minh Query/index hoặc quyền write |
| SQL++ `SELECT RAW 1` | Query Engine đáp ứng | Không xác minh named GSI |
| SQL++ read-only theo field | Đường Query/Index cụ thể có thể chạy | Không chứng minh mutation mới đã được index |
| Search read-only query | Search path/index liên quan | Không thay GSI/Analytics checks |

Dùng phép thử ít tốn tài nguyên nhất mà vẫn trả lời câu hỏi đang điều tra. Trên production, ưu tiên **read-only, bounded timeout, không tự tạo dữ liệu**, và không dùng health check để thực hiện DDL.

## 16. Ví dụ KV diagnostic bằng Java SDK

Một phép thử `exists` với sentinel key không cần tồn tại:

~~~java
import java.time.Duration;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.ExistsOptions;

public class OrdersKvProbe {
    private final Collection orders;

    public OrdersKvProbe(Cluster cluster) {
        this.orders = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");
    }

    public void checkConnectivity() {
        // Một response exists=false vẫn chứng minh KV operation chạy.
        orders.exists(
                "__readiness_orders_probe__",
                ExistsOptions.existsOptions()
                        .timeout(Duration.ofSeconds(1)));
    }
}
~~~

**Ưu điểm:** Đi đúng collection; không write/delete fixture, không cần index; có timeout.

**Giới hạn:** Không chứng minh `insert/replace` quyền ghi, CAS, durability, transaction hoặc SQL++ query availability. Một KV operation thành công ở thời điểm T không bảo đảm T+1 không có outage.

### 16.1. Đừng lấy `exists() == false` làm DOWN

Khi sentinel không có trong database, một response false là **thành công về connectivity**. Nếu muốn khẳng định dữ liệu sentinel luôn tồn tại, đó là functional check riêng phải có fixture quản lý.

## 17. Ví dụ Query Engine và Index path: hai phép thử tách biệt

**Query Engine check**, không cần GSI:

~~~java
import java.time.Duration;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.query.QueryOptions;

public class QueryEngineProbe {
    private final Cluster cluster;

    public QueryEngineProbe(Cluster cluster) {
        this.cluster = cluster;
    }

    public void checkConnectivity() {
        cluster.query(
                "SELECT RAW 1",
                QueryOptions.queryOptions()
                        .timeout(Duration.ofSeconds(1)));
    }
}
~~~

**Query/Index path check**, dùng keyspace và GSI phù hợp:

~~~sql
SELECT RAW META(o).id
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
LIMIT 1;
~~~

Có thể chạy với `QueryOptions.scanConsistency(QueryScanConsistency.NOT_BOUNDED)` để kiểm tra khả năng **thực thi query theo field** mà không yêu cầu index đợi mốc request. Phải xác minh `EXPLAIN` để biết index nào thực sự được chọn.

Nếu Query Engine check thành công nhưng query theo `customerId` thất bại, hướng điều tra là index online/plan, Query RBAC trên keyspace, Data fetch path hoặc logic query, không mặc định do DNS/bootstrap.

### 17.1. Đừng dùng REQUEST_PLUS cho mọi health query

`REQUEST_PLUS` có thể chờ Index Service bắt kịp mutation. Nó hữu ích cho yêu cầu freshness/read-after-write, nhưng một health probe chạy nhiều lần có thể tăng latency và readiness flapping khi GSI backlog. Đưa freshness validation sang integration/synthetic tests có kiểm soát khi phù hợp.

## 18. Spring Boot Actuator: health check không phải toàn bộ diagnostics

Spring Boot Actuator thường cung cấp:

~~~text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Ví dụ bật probe và giới hạn chi tiết:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,info
~~~

**Phân biệt:**

- **Liveness:** JVM/process còn hoạt động; không nên kéo DOWN khi Couchbase outage tạm thời.
- **Readiness:** instance có nên nhận traffic mới theo business contract.
- **Couchbase auto health contributor:** phụ thuộc Spring Boot version/classpath, phải xác minh phạm vi của contributor `couchbase` nếu có.
- **Custom indicator:** dùng khi cần kiểm tra chính xác Orders KV collection hoặc capability đặc biệt.
- **Admin diagnostics:** có thể cần ping/diagnostics, nhưng không được tự động phơi toàn bộ SDK report cho người dùng công khai.

Nếu Couchbase lỗi chung khiến mọi pod cùng NotReady, Kubernetes Service có thể mất hết endpoints. Đây là quyết định routing phải được cân nhắc, không phải thuốc chữa Database.

## 19. Custom HealthIndicator kiểm tra đúng Orders KV collection

Khi KV là dependency bắt buộc của hầu hết Orders API, có thể viết `HealthIndicator` ngắn, read-only, có timeout.

~~~java
import java.time.Duration;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.ExistsOptions;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("ordersKv")
public class OrdersKvHealthIndicator implements HealthIndicator {
    private final Collection orders;

    public OrdersKvHealthIndicator(Cluster cluster) {
        this.orders = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");
    }

    @Override
    public Health health() {
        try {
            orders.exists(
                    "__orders_health_probe__",
                    ExistsOptions.existsOptions()
                            .timeout(Duration.ofSeconds(1)));

            return Health.up()
                    .withDetail("check", "orders-kv")
                    .build();
        } catch (RuntimeException failure) {
            // Loại lỗi và timing chỉ ghi trong logs bảo mật.
            return Health.down()
                    .withDetail("check", "orders-kv")
                    .build();
        }
    }
}
~~~

`exists(false)` vẫn là **KV operation thành công**: key sentinel không cần tồn tại. Đây không phải test quyền write, query SQL++, transaction, CAS hoặc durability.

Đưa custom indicator vào readiness **nếu** policy yêu cầu KV:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,ordersKv
~~~

Contributor ID phải được đăng ký đúng. Không đưa query nặng, create/delete document hoặc `REQUEST_PLUS` vào liveness. Nếu cả một Query Service chỉ phục vụ chức năng phụ gặp lỗi, có thể xuất health group/cảnh báo riêng thay vì hạ toàn bộ Orders pod.

## 20. Cách đọc một incident bằng app log và SDK diagnostics

Giả sử 10:05 sáng người dùng báo lịch sử đơn timeout, còn chi tiết đơn vẫn hoạt động.

### 20.1. Application log, định dạng minh họa

~~~text
10:05:01 requestId=req-581 route=/customers/{id}/orders
        service=query operation=sqlpp
        elapsedMs=1550 outcome=timeout

10:05:02 requestId=req-582 route=/orders/{id}
        service=kv operation=get
        elapsedMs=18 outcome=success
~~~

Các trường là logging convention tự thiết kế, **không phải log tự động SDK**.

### 20.2. SDK diagnostics snapshot minh họa

~~~text
sampleAt=10:05:03
KV endpoint A      responsive
KV endpoint B      responsive
QUERY endpoint C   degraded / unavailable
QUERY endpoint D   responsive
~~~

Đây là sơ đồ trạng thái, không phải enum hoặc JSON SDK cố định. Một endpoint Query lỗi không chứng minh tất cả Query nodes đều lỗi.

### 20.3. Đối chiếu metrics và query plan

Kiểm tra SQL++ p95/p99, timeout rate, Query Service load, Index Service mutation backlog, named index state và `EXPLAIN`. Nếu KV vẫn ổn mà Query path xấu, ưu tiên điều tra Query/Index, không chạy restart toàn bộ pod trước khi biết nguyên nhân.

### 20.4. Khi không có SDK log mới

Cache hit có thể trả dữ liệu cũ mà không chạm Couchbase. Nếu HTTP response sai nhưng không thấy KV/SQL++ span, kiểm tra Spring Cache/Redis/HTTP cache/frontend state và **instrumentation có được bật hay không** trước khi suy rằng Query Service không chạy.

## 21. Distributed tracing: nối request tới đúng SDK operation

Một request xuyên qua nhiều lớp:

~~~mermaid
sequenceDiagram
    participant H as Controller
    participant S as OrderService
    participant R as Repository
    participant C as Couchbase Java SDK
    participant Q as Query Service

    H->>S: GET history [traceId]
    S->>R: findByCustomerId
    R->>C: SQL++ query
    C->>Q: request
    Q-->>C: rows hoặc timeout
    C-->>R: result/error
    R-->>S: entities/error
    S-->>H: HTTP response
~~~

Các thuộc tính hữu ích cho tracing:

- `traceId`, `spanId`, route template và service/operation name.
- `db.system`/dependency type theo conventions mà dự án sử dụng.
- `keyspace` đã chuẩn hóa, không chứa dữ liệu cá nhân.
- `duration` và error category.
- Query template name/shape, không log raw parameters.
- SDK retry/timeout information nếu instrumentation thực sự cung cấp.

**Không mặc định** Spring Data, SDK và OpenTelemetry/Micrometer tự truyền toàn bộ context trong mọi phiên bản. Phải kiểm thử một request end-to-end. Thiếu span không chứng minh operation không xảy ra; có thể do tracing config.

### 21.1. Tránh label có cardinality quá lớn

Không gắn full document ID, customerId, UUID, raw SQL++ hoặc URL chứa ID vào metrics labels. Cardinality lớn tăng chi phí lưu trữ và rủi ro lộ thông tin. Dùng `service=kv`, `operation=get`, `outcome=timeout`, `route=/orders/{id}`.

## 22. Metrics bổ sung log và ping/diagnostics

| Nhóm | Cần quan sát | Ý nghĩa |
| --- | --- | --- |
| HTTP | 5xx rate, p50/p95/p99 theo route | Người dùng bị ảnh hưởng đến đâu |
| KV | request latency, timeout, mutation rate | Data path khỏe/chậm |
| Query | query count, latency, errors, scan/fetch/sort | Query Service và plan |
| Index | index online state, mutation backlog, update pressure | GSI readiness/freshness |
| SDK client | retry, endpoint reachability, timeout | Khả năng kết nối từ client |
| Network | DNS/TLS errors, round-trip latency | Lỗi trước business operation |
| JVM/pod | CPU/GC, threads, readiness flaps, restarts | App và probe overhead |
| Search/Analytics | endpoint errors, index/dataset lag nếu dùng | Từng capability riêng |

Tên metric, đơn vị và API SDK instrument có thể thay đổi theo Server/SDK/observability stack version. Lấy từ môi trường thực tế, **không tự giả định tên metric là chuẩn**.

### 22.1. Tail latency quan trọng hơn trung bình khi có backlog

Một query `REQUEST_PLUS` có thể chờ index khi mutation backlog tăng. Average vẫn thấp nếu đa số request nhanh, nhưng p99 và timeout xấu. Báo cáo số request thành công, timeout và p95/p99 cùng lúc; đừng loại timeout khỏi biểu đồ rồi tuyên bố SLO đạt.

### 22.2. Availability khác freshness

Một named index online chưa chắc đã bắt kịp mutation. SDK `ping` responsive không nói GSI/Search/Analytics đã cập nhật dữ liệu. Độ mới có SLO và phép thử riêng, không được suy từ health `UP`.

## 23. Timeout budget và retry khi kết nối không ổn định

Một ngân sách minh họa:

~~~text
HTTP deadline                2.0s
  Controller/validation      một phần
  SQL++ SDK timeout          1.2s
  Serialization/network      phần còn lại
~~~

Các con số chỉ để minh họa; phải chọn từ SLO thực.

Điều cần kiểm tra trong logs:

1. HTTP timeout xảy ra trước hay sau SDK timeout?
2. SDK đã retry bao nhiêu lần, vì lỗi nào?
3. Có nhiều query/publisher tồn tại dù client đã hủy request?
4. Query có chờ Index Service do `REQUEST_PLUS` hay chậm ở scan/fetch/sort?
5. Network lỗi từ một pod hay toàn bộ cluster?
6. Timeout đã bị application catch rồi trả success/empty list sai nghĩa chưa?

### 23.1. Write timeout có thể ambiguous

Lệnh `insert`/`replace`/`upsert` timeout không chứng minh server chưa xử lý mutation. Nếu retry với UUID mới có thể tạo đơn trùng. Dùng ID/idempotency key ổn định, xác minh kết quả ở nguồn khi phù hợp và có chính sách xử lý trạng thái chưa xác định.

### 23.2. Retry storm

Một Query Service đang nghẽn có thể bị retry liên tục từ nhiều pods khiến tình hình xấu hơn. Giới hạn retry/concurrency, backoff và budget tổng; không tăng mọi timeout hoặc bật retry vô hạn để che lỗi cấu hình/permission.

## 24. Diagnostics endpoint cho operator: không mở công khai

Có thể phân tầng kiểm tra như sau:

- **Actuator health:** lightweight trạng thái phục vụ routing.
- **SDK ping/diagnostics:** thu thập trạng thái endpoints có kiểm soát khi điều tra.
- **Synthetic monitor:** thử Query/Index/Search path định kỳ với tần suất giới hạn.
- **Business API:** không cho người dùng ngoài kích hoạt debug SDK hoặc raw diagnostics tùy ý.

Một schema output **tự thiết kế** đã lược bỏ host/secret:

~~~json
{
  "sampledAt": "2026-11-25T08:00:00Z",
  "checks": [
    {"service": "kv", "state": "UP"},
    {"service": "query", "state": "DEGRADED"}
  ]
}
~~~

`DEGRADED` ở đây cần do hệ thống vận hành định nghĩa theo số endpoint, thời gian phản hồi và khả năng phục vụ; **không phải field mặc định trong `cluster.diagnostics()`**.

Nếu triển khai admin endpoint, cần RBAC/network isolation, audit, rate limiting, retention và allowlist fields. Không trả raw `pingReport.toString()`, exception context hoặc connection string có credential tới browser không được cấp quyền.

### 24.1. Không tạo mutation trong health handler

Một probe `insert → query → delete` có thể tạo GSI updates, Eventing side effects, dữ liệu rác khi timeout và áp lực hệ thống. Chuyển nó sang smoke/integration test cô lập nếu cần kiểm tra write path.

## 25. Chẩn đoán trên Windows, Linux và Kubernetes

Các lệnh sau giúp xác minh **một tầng** của kết nối. Chúng chỉ là ví dụ chạy từ đúng máy/pod/network namespace; không phải chứng minh Couchbase sẵn sàng hoàn toàn.

### 25.1. DNS seed

~~~powershell
Resolve-DnsName couchbase.example.internal
~~~

~~~bash
getent hosts couchbase.example.internal
nslookup couchbase.example.internal
~~~

DNS resolve được chưa chứng minh TCP/TLS và SDK discovery đến mọi node thành công.

### 25.2. TCP endpoint

~~~powershell
Test-NetConnection -ComputerName couchbase.example.internal -Port 11207
~~~

~~~bash
nc -vz couchbase.example.internal 11207
~~~

`11207` chỉ minh họa một cổng KV TLS thường gặp; **phải xác minh ports/endpoints thực tế của cluster và TLS mode đang dùng**. Một seed TCP reachable chưa chứng minh discovered Data/Query endpoints đều reachable.

### 25.3. Pod logs

~~~bash
kubectl logs deployment/orders-api --since=15m
~~~

Trong cluster thật cần chọn đúng namespace/container và RBAC. Distroless images có thể không có shell hoặc `nc`; dùng debug container/pod được ủy quyền. Không export logs chứa secret sang kênh chia sẻ công khai.

### 25.4. So sánh pod A và B

Nếu chỉ một pod lỗi, đối chiếu image version, secret, DNS resolution, trust store, network policy, service mesh, SDK endpoint snapshots và resource pressure. Không tự kết luận cluster chết vì một pod gặp timeout.

## 26. Reactive WebFlux: log phải bám theo tín hiệu I/O thực

Trong WebFlux, một request có thể chạy qua nhiều thread/scheduler. Một `ThreadLocal MDC` đặt ở controller không mặc định tự đi cùng mọi signal của Reactor pipeline nếu context propagation chưa được thiết lập.

**Nguyên tắc:**

1. Dùng trace/`Reactor Context` và cơ chế context propagation tương thích Spring Boot–Reactor–Micrometer version.
2. Kiểm chứng request ID ở Controller, Repository/Template và operation SDK thực tế.
3. Đo duration tới khi Publisher kết thúc bằng success/error, không tính ngay lúc tạo `Mono`.
4. Không `subscribe()` rồi log “save thành công” trước khi có ACK.
5. Không dùng blocking SDK operation trên event loop chỉ để gọi `ping` hoặc `get`.
6. Giữ timeout, cancellation và retry có giới hạn trong reactive chain.

Phản ví dụ:

~~~java
// Sai: blocking call chạy ngay trước khi Mono được tạo.
Mono.just(blockingRepository.findById(id));

// Sai: chặn event loop.
reactiveRepository.findById(id).block();

// Sai: tự subscribe không quản lý completion/error.
reactiveRepository.save(order).subscribe();
log.info("Saved order");
~~~

Một thiếu sót trong tracing có thể khiến SDK log và HTTP request log mất correlation, nhưng **không có span không chứng minh request DB không xảy ra**. Phải kiểm tra instrumentation.

### 26.1. Reactive không xóa độ trễ phía Couchbase

Một query `REQUEST_PLUS` vẫn có thể chờ GSI bắt kịp. Reactive tránh chặn thread khi chờ I/O theo thiết kế, nhưng latency cuối-đầu và tải Query/Index Service vẫn tồn tại.

## 27. Kiểm thử chẩn đoán: phân biệt policy và kết nối thực

Một bộ test nên có **unit/contract tests** và **integration tests**.

### 27.1. Unit test cho phân loại lỗi

Fake gateway có thể mô phỏng:

~~~text
A: KV success, Query timeout
  -> log service=query, errorCategory=timeout
  -> không báo Data Service DOWN

B: KV exists returns false
  -> operation success, không báo DOWN

C: Query engine success, named index missing
  -> query-engine UP, orders-index-path FAILED

D: Write outcome ambiguous
  -> không retry tạo Order với UUID mới

E: Cache hit
  -> không có new SDK call; kiểm tra cache riêng
~~~

Mock chỉ chứng minh **logic phân loại, logging và health policy** của application, không chứng minh server Couchbase thật đang khỏe.

### 27.2. Spring Boot integration test KV path

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.ExistsOptions;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrdersConnectivityIT {
    @Autowired
    private Cluster cluster;

    @Test
    void kvOperationCompletesAgainstTestCollection() {
        Collection orders = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");

        var result = orders.exists(
                "__it_connectivity_probe__",
                ExistsOptions.existsOptions());

        assertNotNull(result);

        // Không assert result.exists() == true:
        // sentinel key không nhất thiết tồn tại.
    }
}
~~~

**Yêu cầu fixture:** Test cluster riêng với bucket/scope/collection và user quyền KV phù hợp; không dùng production. Nếu cần bảo đảm key không có, dùng UUID ngẫu nhiên. Không bắt buộc sửa document mỗi lần test.

### 27.3. Integration test Query Engine và GSI path

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryScanConsistency;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class QueryConnectivityIT {
    @Autowired
    private Cluster cluster;

    @Test
    void queryEngineAndOrdersIndexAreReachable() {
        assertNotNull(cluster.query("SELECT RAW 1"));

        String sql = """
            SELECT RAW META(o).id
            FROM `shop`.`sales`.`orders` AS o
            WHERE o.customerId = $customerId
            LIMIT 1
            """;

        assertNotNull(cluster.query(
                sql,
                queryOptions()
                        .parameters(JsonObject.create()
                                .put("customerId", "it-missing-customer"))
                        .scanConsistency(
                                QueryScanConsistency.NOT_BOUNDED)));
    }
}
~~~

Query đầu kiểm tra engine; query sau kiểm tra collection/index path. Nếu query thứ hai trả zero rows vẫn có thể thành công. **Phải chuẩn bị GSI online** và quyền SELECT; nếu SDK raw query khác generated Spring Data query về type discriminator thì không tự kết luận đây là lỗi endpoint.

### 27.4. Tránh test flaky về độ mới

Không assert một query `NOT_BOUNDED` sau insert **phải** stale. Index có thể bắt kịp trước lúc query. Nếu kiểm chứng read-after-write qua GSI, dùng `REQUEST_PLUS` hoặc `MutationState/consistentWith` với fixture/conditions phù hợp; đó là bài kiểm tra freshness, **khác** connectivity.

## 28. Ma trận triệu chứng và nguyên nhân có thể

| Quan sát | Những giả thuyết cần kiểm tra |
| --- | --- |
| App startup tốt, request đầu timeout | Lazy I/O/bootstrap, DNS, SDK topology, network |
| DNS seed fail | Resolver/config/NetworkPolicy |
| TCP seed OK, KV operation fail | Discovered endpoints, TLS, auth, Data service, keyspace |
| TLS handshake fail | CA trust, hostname/SAN, certificate rotation |
| Authentication fail | Secret/credential/identity |
| Authorization fail | RBAC bucket/scope/collection, Query role |
| KV `findById` OK, SQL++ fail | Query/Index path, missing index, query timeout |
| `SELECT RAW 1` OK, list query fail | GSI, WHERE/type mapping, index plan, Query RBAC |
| Query latency tăng sau giờ cao điểm | Index lag, sort/fetch, CPU, network, concurrency |
| Một pod lỗi, pod khác OK | Node routing, trust store, DNS, secret, config |
| SDK ping OK, browser vẫn thấy dữ liệu cũ | Cache stale, index freshness, frontend state |
| Write timeout, client retry tạo trùng | Ambiguous mutation và thiếu idempotency |
| Liveness DOWN khi Couchbase lỗi | Health policy gắn dependency vào process liveness |
| Actuator health UP nhưng SQL++ lỗi | Health check không kiểm tra đúng Query/Index capability |

**Không dùng bảng này thay root-cause analysis.** Mỗi dòng là giả thuyết; xác minh bằng operation read-only đúng phạm vi, logs, query plan và metrics liên quan.

## 29. Runbook điều tra “Couchbase connection failed”

~~~mermaid
flowchart TD
    A["HTTP API lỗi khi dùng Couchbase"] --> B{"Operation: KV hay SQL++?"}
    B --> K["KV: đúng collection và Data endpoints"]
    B --> Q["Query: engine + named GSI"]
    K --> C["DNS / TCP / TLS / auth / RBAC"]
    Q --> D["SELECT RAW 1, query thực, EXPLAIN"]
    C --> E["SDK ping/diagnostics theo endpoint"]
    D --> E
    E --> F["Client & server metrics, latency, backlog"]
    F --> G["Sửa đúng nguyên nhân, đo recovery"]
~~~

**Các bước on-call:**

1. Xác định ảnh hưởng: route, tỉ lệ lỗi, thời gian bắt đầu, số pod, region/tenant nào liên quan.
2. Lấy correlation IDs và operation type từ application logs.
3. Phân loại timeout, authentication, authorization, missing index, network hoặc application bug.
4. Xem SDK logs và ping/diagnostics **theo từng service/endpoint**, không coi một health boolean là đủ.
5. Nếu bootstrap lỗi, kiểm tra seed, DNS/SRV, TLS trust, advertised/alternate addresses và các ports thực.
6. Nếu KV lỗi, thử read-only KV trên đúng bucket/scope/collection.
7. Nếu SQL++ lỗi, tách `SELECT RAW 1` với query cần GSI; kiểm tra `EXPLAIN`/index online.
8. Nếu latency cao, xem Query Service p95/p99, Index backlog, retry concurrency và SDK/HTTP timeout budgets.
9. Nếu browser hiện dữ liệu cũ, kiểm tra cache, mapping và scan consistency; không quy hết cho network.
10. Nếu chỉ một pod lỗi, so image, credentials, endpoint reports và network từ đúng pod đó.
11. Với write timeout, không retry mù nếu có nguy cơ ambiguous; dùng idempotency key.
12. Đưa ra hành động khôi phục đúng nguyên nhân: sửa config/RBAC/network, tối ưu index hoặc capacity, rollback thay đổi nếu cần.
13. Sau phục hồi, đo lại error rate/p95/p99, readiness transitions và user impact.
14. Tắt DEBUG/TRACE, lưu kết quả điều tra an toàn, cập nhật alerts và runbook.

Tránh restart đồng loạt khi shared dependency đang lỗi, vì bootstrap/connection storm có thể làm tình hình tệ hơn.

## 30. Bảo mật SDK logs và diagnostics

Những thông tin cần xem là nhạy cảm hoặc có thể hỗ trợ tấn công:

- Password, bearer token, connection string chứa secret.
- Username/identity, client certificates, trust material.
- Customer ID, email, địa chỉ, thông tin thanh toán, document body.
- Query text có literal dữ liệu hoặc parameters chứa PII.
- Private IP, hostname, topology, service/port mapping.
- Raw exception/stacktrace xuất trong public API response.

**Chính sách tối thiểu:**

1. Dùng query template names, service names, timing, error category.
2. Không log raw document body hoặc SQL++ parameter values.
3. Redact raw SDK context trước khi chia sẻ.
4. Chỉ operator được bật DEBUG/TRACE và xem diagnostics sâu.
5. Có retention và access controls cho logging backend.
6. Dùng sampling khi traffic lớn, không in mỗi ping report.
7. Tách log nội bộ với thông điệp HTTP cho người dùng; response chỉ cần mã lỗi an toàn và correlation ID.
8. Không lưu secret trong file cấu hình hoặc bài kiểm thử.

### 30.1. Dùng logs để kết luận vừa đủ

Một error log từ Query endpoint không chứng minh Data Service down; một successful KV ping không chứng minh Search/Analytics/Eventing khỏe. Trạng thái phải được diễn đạt theo **đúng capability mà phép thử đã thực hiện**.

## 31. Các sai lầm vận hành cần tránh

1. Thấy Spring Boot started rồi kết luận mọi Couchbase services connected.
2. Coi một seed TCP reachable nghĩa mọi discovered endpoints reachable.
3. Gộp lẫn TLS handshake, authentication và authorization failures.
4. Coi SDK ping là business query test.
5. Coi diagnostics snapshot là bảo đảm request tiếp theo thành công.
6. Coi `SELECT RAW 1` là GSI/index readiness test.
7. Dùng query timeout đồng nghĩa zero rows.
8. Coi timeout ghi chắc chắn chưa ghi và retry với ID mới.
9. Bật DEBUG/TRACE toàn cluster vô thời hạn.
10. In password/query parameters/document body vào logs.
11. Dùng documentId/customerId làm high-cardinality metrics labels.
12. Tạo Cluster mới mỗi health probe.
13. Gắn Query Service vào liveness khiến restart storm.
14. Chạy query REQUEST_PLUS nặng trong readiness quá thường xuyên.
15. Cứ vài giây insert/delete sentinel để “test tất cả”.
16. Không xem Query/Index metrics khi SQL++ p99 tăng.
17. Không tách cache stale khỏi index lag.
18. Coi non-blocking Publisher được tạo là I/O đã hoàn thành.
19. Phớt lờ correlation ID giữa HTTP và SDK logs.
20. Coi lỗi một pod là outage toàn cluster.
21. Tin mock test là chứng cứ connection thật hoạt động.
22. Không dọn debug level sau khi incident kết thúc.

## 32. Bài tập tình huống và câu hỏi tự kiểm tra

### A. KV hoạt động, SQL++ timeout

`findById` thành công, `findByCustomerId` timeout.

**Gợi ý:** Xem Query endpoint, `SELECT RAW 1`, named index, `EXPLAIN`, Query latency, Index backlog và consistency mode. Chưa có chứng cứ Data/KV chết.

### B. TLS ở một pod thất bại

Pod A chạy, pod B log TLS handshake failure.

**Gợi ý:** So trust store, certificate SAN/rotation, image, network proxy và DNS của B. Không thay CAS/index trước khi xử lý tầng kết nối.

### C. SDK ping trả endpoints nhưng application vẫn lỗi

**Gợi ý:** Ping chỉ kiểm tra phạm vi endpoints được chọn. Thử operation thật trên đúng collection/query path, RBAC, timeout và service-specific metrics.

### D. Một query trả empty list

**Gợi ý:** Có thể là query thành công. Kiểm tra `WHERE`/`LIMIT`/type discriminator; không coi empty result là Query Service down.

### E. Log file quá lớn

Bật SDK DEBUG cho hàng trăm pods làm log volume tăng vọt.

**Gợi ý:** Giới hạn category/pod/time, sampling và redaction; tắt sau incident, đo log ingestion overhead.

### F. Write timeout tạo đơn trùng

**Gợi ý:** Operation có thể ambiguous; dùng Order ID/idempotency key ổn định và verify outcome, không retry với UUID mới.

### G. Tất cả pods NotReady khi Index backlog tăng

**Gợi ý:** Readiness đang query `REQUEST_PLUS` quá đắt. Tách readiness lightweight khỏi freshness synthetic check; kiểm soát concurrency và theo dõi Index backlog.

### H. SDK logs không có trace ID

**Gợi ý:** Kiểm tra Micrometer/OpenTelemetry propagation và Reactor context trên đúng version; đừng chỉ đặt ThreadLocal MDC rồi mặc định nó xuyên qua mọi thread.

### I. Response HTTP chứa raw SDK exception

**Gợi ý:** Trả mã lỗi + request ID an toàn; redacted context nằm trong hệ thống internal logs phân quyền.

### J. Data mới nhưng giao diện còn cũ

**Gợi ý:** Phân biệt KV source, SQL++ GSI lag, Spring Cache/Redis, HTTP cache và frontend state. SDK ping không thể chẩn đoán toàn bộ.

## 33. Checklist production: log SDK và endpoint diagnostics

- [ ] Mỗi operation KV/Query/Search có tên, outcome, duration và correlation ID?
- [ ] Application logs phân biệt not found, timeout, RBAC và business error?
- [ ] Timeout không bị chuyển thành empty result hoặc HTTP success giả?
- [ ] Write ambiguous có idempotency và quy trình xác minh?
- [ ] Spring Data/SDK logger levels được kiểm soát theo version?
- [ ] DEBUG/TRACE chỉ bật có thời hạn, phạm vi nhỏ và có quy trình tắt?
- [ ] Không log credential, PII, payment data hoặc raw query parameters?
- [ ] Metrics labels tránh document ID/customer ID high cardinality?
- [ ] Cluster/ClusterEnvironment được tái sử dụng theo application lifecycle?
- [ ] `ping()` và `diagnostics()` được hiểu đúng phạm vi?
- [ ] Không dùng ping để kết luận mọi Index/Search/Analytics đều sẵn sàng?
- [ ] Có bằng chứng từ đúng pod/network namespace khi lỗi cục bộ?
- [ ] Seed DNS, TCP/TLS, cluster topology, discovered endpoints được phân biệt?
- [ ] RBAC kiểm tra đúng bucket/scope/collection và operation?
- [ ] KV exists false không bị coi là DOWN?
- [ ] `SELECT RAW 1` không bị hiểu nhầm là business GSI test?
- [ ] Query index path có kiểm tra `EXPLAIN`/index state?
- [ ] SDK/HTTP probe timeouts có ngân sách thống nhất và giới hạn retry?
- [ ] Liveness không phụ thuộc Couchbase shared outage?
- [ ] Readiness dependency phù hợp traffic contract, không query nặng mỗi probe?
- [ ] Diagnostics endpoint có RBAC, audit, rate limit và redaction?
- [ ] Tracing/MDC có kiểm thử propagation nếu dùng WebFlux?
- [ ] Dashboard có p95/p99, errors, retry, Index backlog và HTTP impact?
- [ ] Test suite có connectivity KV và Query riêng trên cluster test?
- [ ] Có runbook theo operation/service/endpoint thay vì restart tất cả?
- [ ] CAS, durability, TTL, transaction, data freshness và cache coherence được kiểm tra riêng?

## 34. Kết luận

**Log SDK, thông tin chẩn đoán và endpoint kết nối là ba nguồn chứng cứ bổ trợ nhưng không thay thế nhau.** Application logs giải thích request/nghiệp vụ; SDK logs hỗ trợ điều tra bootstrap, transport, retry và timeout; `ping()`/`diagnostics()` cho thấy khả năng liên lạc và trạng thái endpoint theo phạm vi được kiểm tra; metrics/tracing và server dashboards xác định mức ảnh hưởng và điểm nghẽn.

Trong **Spring Data Couchbase**, hãy chẩn đoán theo thứ tự **request → operation KV/SQL++ → seed/discovered endpoints → DNS/TLS/auth/RBAC → query/index plan → timeout/latency và data freshness**, đồng thời tách riêng cache và lỗi nghiệp vụ. Giữ logs có cấu trúc, correlation ID, redaction, timeout có ngân sách và retry an toàn; không biến health probe thành nguồn mutation hoặc restart storm.

Hệ thống dễ vận hành không phải hệ thống ghi nhiều log nhất, mà là hệ thống mà **mỗi log, diagnostic và probe trả lời đúng một câu hỏi, an toàn và có thể kiểm chứng**.
