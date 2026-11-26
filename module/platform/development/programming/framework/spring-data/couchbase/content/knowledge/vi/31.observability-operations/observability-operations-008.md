# Quản lý thời gian khởi động và phục hồi kết nối

Trong hệ thống dùng **Spring Data Couchbase**, một ứng dụng có thể khởi động được JVM và Spring ApplicationContext nhưng **chưa thực sự đọc được document từ Couchbase**. Sau khi chạy ổn định, mạng có thể chập chờn, node Couchbase được thay thế, cluster rebalance, chứng chỉ hết hạn hoặc dịch vụ Query gián đoạn. Vận hành tốt không chỉ là “thử `Cluster.connect(...)` một lần rồi tin rằng đã kết nối mãi mãi”.

Couchbase Java SDK 3.x khởi tạo các kết nối và tải cấu hình topology **bất đồng bộ/lazy**. `Cluster.connect(...)` có thể trả về khi quá trình bootstrap còn đang chạy; `cluster.bucket(name)` cũng không đồng nghĩa mọi socket KV đã sẵn sàng. Vì vậy, **thời gian khởi động của ứng dụng**, **thời gian sẵn sàng nhận lưu lượng**, **thời gian chờ của mỗi KV/SQL++ operation**, và **thời gian phục hồi sau sự cố** là những ngân sách khác nhau.

Bài thuộc chương **Quan sát và vận hành** của module **SPRING_DATA_COUCHBASE**: xây dựng tầng truy cập Couchbase bằng document mapping, Repository, `CouchbaseTemplate` và SQL++; hiểu bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và reactive API để tối ưu tính sẵn sàng, nhất quán và khả năng vận hành.

> **Nguyên tắc:** Tái sử dụng `Cluster` do Spring quản lý; khởi động theo một **readiness policy** phù hợp nghiệp vụ; để SDK điều phối kết nối lại/topology khi lỗi tạm thời; phân loại timeout và ghi nhận trạng thái **chưa rõ** của mutation; dùng probes và telemetry để phân biệt ứng dụng bị lỗi với Couchbase đang suy giảm. **Không tạo một Cluster mới cho mỗi request hoặc mỗi lần mất kết nối.**

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả các giai đoạn từ JVM/Spring startup đến Couchbase bootstrap, bucket readiness và phục vụ request đầu tiên.
2. Phân biệt `Cluster.connect()`, `Cluster.waitUntilReady(...)`, `Bucket.waitUntilReady(...)`, `ping()` và `diagnostics()`.
3. Cấu hình Spring Boot Couchbase connection string, credentials, bucket và timeout theo phiên bản đang dùng.
4. Thiết kế chiến lược **fail-fast startup**, **degraded startup** hoặc **readiness-gated startup** theo tính quan trọng của Couchbase.
5. Sử dụng `ApplicationRunner` để chờ bucket readiness với **ngân sách thời gian hữu hạn** khi cần.
6. Phân biệt Kubernetes `startupProbe`, `livenessProbe` và `readinessProbe`.
7. Tránh đưa lỗi Couchbase dùng chung toàn cluster vào liveness, dẫn đến restart storm.
8. Phân tích DNS/SRV, TLS/truststore, seed nodes, alternate addresses, firewall và RBAC khi bootstrap lỗi.
9. Phân biệt `connectTimeout`, `kvTimeout`, `kvDurableTimeout`, `queryTimeout` và deadline nghiệp vụ.
10. Hiểu hành vi SDK retry và giới hạn của recovery; không xây vòng `disconnect/reconnect` thủ công quanh mọi exception.
11. Phân loại `AmbiguousTimeoutException`, `UnambiguousTimeoutException`, `RequestCanceledException` và CAS/conflict đúng bản chất.
12. Dùng circuit breaker, bulkhead, backoff và admission control khi Couchbase bị lỗi kéo dài.
13. Xây observability cho startup duration, readiness flapping, timeout reason, endpoint health và recovery time.
14. Thiết kế graceful shutdown, rolling deployment và fault-injection tests.

## 2. Một timeline khởi động có nhiều “đã sẵn sàng”

~~~text
T0  JVM started
T1  Spring ApplicationContext tạo bean
T2  Couchbase Cluster handle tồn tại
T3  SDK nhận cluster configuration/topology
T4  Bucket được mở và KV sockets đủ dùng
T5  Data Service đọc/ghi được theo policy ứng dụng
T6  Query/Index/Search có thể sẵn sàng theo nhu cầu riêng
T7  Readiness = ACCEPTING_TRAFFIC
T8  HTTP request đầu tiên đi qua Repository/Template/SDK
~~~

T2 **không bằng** T4; T4 **không bằng** T6; T7 là **quyết định của ứng dụng**, không phải trạng thái Couchbase đơn giản.

Một cách đo cần tách:

| Thước đo | Bắt đầu | Kết thúc | Người sở hữu |
| --- | --- | --- | --- |
| `process_startup_seconds` | JVM start | Spring context started | JVM/Spring |
| `couchbase_bootstrap_seconds` | Bắt đầu tạo client | Client có đủ topology/endpoint theo policy | SDK adapter |
| `couchbase_bucket_ready_seconds` | Mở Bucket handle | `bucket.waitUntilReady` hoàn tất | SDK/ứng dụng |
| `app_time_to_ready_seconds` | Container start | Readiness chuyển UP | Platform/application |
| `first_kv_request_latency` | Gửi KV get đầu tiên | Response/error | SDK + Data Service |
| `recovery_time_seconds` | Mất khả năng phục vụ | Khôi phục tới SLO | Toàn hệ thống |

Không cộng các con số thành một “thời gian connect” duy nhất rồi tăng mọi timeout.

## 3. Java SDK bootstrap theo cơ chế bất đồng bộ

Theo tài liệu Java SDK, việc gọi:

~~~java
Cluster cluster = Cluster.connect(
        connectionString, username, password);

Bucket bucket = cluster.bucket("shop");
Collection customers = bucket.scope("crm")
        .collection("customers");
~~~

không nhất thiết chờ toàn bộ sockets hoặc topology sẵn sàng trước khi trả về. Việc mở các resources có thể hoàn tất **trong background**. Lần operation đầu tiên đôi khi chịu thêm thời gian bootstrap.

Điều này giải thích một triệu chứng thường gặp:

~~~text
Start app: báo Spring Boot started
First user request: KV get timeout
Later requests: bình thường
~~~

Tình huống trên **có thể** do bootstrap chưa kịp, nhưng cũng có thể do DNS, TLS, RBAC, network, server overload. Không kết luận chỉ bằng thời gian; đối chiếu SDK diagnostics/error context và logs.

**Lưu ý:** SDK thread-safe, dùng được từ nhiều threads; không tạo client mới trong Repository service mỗi lần gọi.

## 4. Tái sử dụng Spring-managed Cluster là tiền đề của recovery

Với Spring Boot có `spring-boot-starter-data-couchbase` hoặc reactive starter, Framework có thể auto-configure một `com.couchbase.client.java.Cluster` dùng chung cho Spring Data Repository và `CouchbaseTemplate`.

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import org.springframework.stereotype.Component;

@Component
public final class CustomerSdkGateway {
    private final Collection customers;

    public CustomerSdkGateway(Cluster cluster) {
        this.customers = cluster.bucket("shop")
                .scope("crm")
                .collection("customers");
    }

    public Collection sdkCollection() {
        return customers;
    }
}
~~~

Production nên lấy `shop`/`crm`/`customers` từ **trusted configuration**, không hardcode nếu deployment khác nhau.

Không làm:

~~~java
public Customer findById(String id) {
    Cluster cluster = Cluster.connect(url, user, password);
    try {
        return readWith(cluster, id);
    } finally {
        cluster.disconnect();
    }
}
~~~

Vì mỗi request sẽ khởi tạo bootstrap mới, tăng tài nguyên, tạo nhiều TCP/TLS handshakes và biến lỗi mạng tạm thời thành **connection storm**.

**Một Cluster dùng chung không có nghĩa chỉ có một TCP connection**: SDK quản lý sockets tới nhiều nodes/services nội bộ.

## 5. Cấu hình Spring Boot cơ bản

Ví dụ cấu hình (dùng secret/environment do platform cấp):

~~~yaml
spring:
  couchbase:
    connection-string: "${COUCHBASE_CONNECTION_STRING}"
    username: "${COUCHBASE_USERNAME}"
    password: "${COUCHBASE_PASSWORD}"
  data:
    couchbase:
      bucket-name: "${COUCHBASE_BUCKET}"

management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Đây là configuration cho Spring Boot phiên bản hỗ trợ các properties tương ứng; kiểm tra **Common Application Properties** của bản đã khóa.

- `spring.couchbase.connection-string`: địa chỉ bootstrap; có thể dùng `couchbase://` hoặc `couchbases://`.
- Credentials của Couchbase cấp qua secret, không commit password.
- `spring.data.couchbase.bucket-name` để Spring Data cấu hình bucket mặc định.
- `management.endpoint.health.probes.enabled` bật nhóm probe nếu không tự kích hoạt theo môi trường.
- `add-additional-paths` cho phép `/livez` và `/readyz` trên main server port ở các Boot versions hỗ trợ.

Không trộn connection-string cho cluster A với bucket name của cluster B. `Bucket` handle tồn tại không chứng minh bucket thực sự có trên Server; cần readiness/operation check.

## 6. `waitUntilReady`: chờ có ngân sách, không chờ vô hạn

~~~java
import java.time.Duration;
import com.couchbase.client.java.Bucket;
import com.couchbase.client.java.Cluster;

Cluster cluster = /* bean do Spring quản lý */;

cluster.waitUntilReady(Duration.ofSeconds(15));

Bucket bucket = cluster.bucket("shop");
bucket.waitUntilReady(Duration.ofSeconds(20));
~~~

Khác biệt:

- `Cluster.waitUntilReady` đợi trạng thái cluster mong muốn (mặc định online) theo SDK.
- `Bucket.waitUntilReady` ngoài trạng thái cluster còn đợi **KV/Data Service của bucket**, hữu ích cho Repository/Template theo key.
- Các overload có `WaitUntilReadyOptions` để chọn trạng thái/service theo API hỗ trợ.
- `waitUntilReady` là **một phép chờ bounded**, không phải vô hạn, không tự “sửa” sai DNS/credentials.
- Nếu timeout, ứng dụng phải chọn fail startup, giữ unready hay vận hành degraded.
- Một lần trả thành công **không bảo đảm** không mất kết nối trong tương lai.

Các số 15/20 giây chỉ để minh họa. Chọn dựa trên SLO, mạng, deployment và khởi động hàng loạt.

## 7. Khác biệt giữa KV readiness và Query readiness

Một ứng dụng chỉ dùng Repository `findById` theo key cần đường KV. Một ứng dụng chạy SQL++ ngay sau startup còn cần Query Service và index phù hợp.

| Workload | Phép kiểm tra cần cân nhắc | Không suy ra |
| --- | --- | --- |
| KV GET/UPSERT | `bucket.waitUntilReady` và KV request nhỏ nếu cần | Index/GSI đã build |
| SQL++ read | Query Service reachable, query/plan/index hợp lệ | CAS/version không đổi |
| Search | Search Service + FTS index readiness | Không bị index lag |
| Analytics | Analytics Service/dataset readiness | Dữ liệu đã ingest tới current |
| Transaction | KV, metadata collection/transaction requirements | Broker bên ngoài đã sẵn |
| Replica read | Replica endpoints/topology | Strong consistency như active |

Một `Cluster.waitUntilReady` trả về thành công không tự chứng minh schema/index/collection name, RBAC hay mọi business query đều hoạt động. “Ứng dụng sẵn sàng” là chính sách phụ thuộc tính năng **bắt buộc phải phục vụ**.

## 8. Ba chính sách startup đáng cân nhắc

| Chính sách | Hành vi | Phù hợp | Rủi ro |
| --- | --- | --- | --- |
| **Fail-fast** | Startup gặp lỗi dependency quan trọng thì fail | Mọi request cần DB, không thể degraded | Deploy có thể fail khi DB đang tạm trục trặc |
| **Start but unready** | HTTP/main process sống, readiness false tới khi kiểm tra đạt | Muốn giữ pod và tự phục hồi | Cần readiness state/report và background checks đúng |
| **Start degraded** | Phục vụ chức năng không cần DB, Couchbase path trả controlled error/fallback | Có cache/read-only/offline behavior rõ | Dễ che sự cố hoặc phục vụ dữ liệu stale |

Một batch worker khác HTTP server: có thể chạy scheduler, chưa nhận job mới khi DB unready, nhưng vẫn sống để phục hồi. Không chọn fail-fast chỉ vì dễ code nếu cluster downtime khiến cả fleet khởi động liên tục.

## 9. Startup gate bằng Spring `ApplicationRunner`

Nếu sản phẩm **không được nhận traffic trước khi bucket KV sẵn sàng**, một gate đơn giản:

~~~java
import com.couchbase.client.java.Bucket;
import com.couchbase.client.java.Cluster;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public final class CouchbaseStartupGate
        implements ApplicationRunner {

    private final Cluster cluster;
    private final String bucketName;

    public CouchbaseStartupGate(
            Cluster cluster,
            @Value("${spring.data.couchbase.bucket-name}")
            String bucketName) {
        this.cluster = cluster;
        this.bucketName = bucketName;
    }

    @Override
    public void run(ApplicationArguments args) {
        Bucket bucket = cluster.bucket(bucketName);
        bucket.waitUntilReady(Duration.ofSeconds(20));
    }
}
~~~

`ApplicationRunner.run` chạy trước khi ứng dụng được công bố **ready** theo lifecycle chuẩn của Spring Boot. Nếu readiness check ném exception, startup thường thất bại; **đó là lựa chọn fail-fast**, không phải degraded startup.

Phải bảo đảm:

- Tối đa một startup gate có trách nhiệm rõ (tránh một loạt beans cùng chờ).
- Không block vô hạn; thời gian chờ nhỏ hơn phù hợp budget của orchestrator.
- Không gọi `disconnect` nếu gate fail mà Cluster do Spring quản lý.
- Nếu chỉ cần một bucket, tránh chờ mọi service không sử dụng.
- Không chạy migration/index build nặng trong gate nếu muốn startup ổn định.
- Không log password/connection string chứa secrets.

## 10. Khi không muốn fail startup: tách readiness khỏi lifecycle

Một service có thể cần **sống nhưng không nhận traffic** khi Couchbase chưa sẵn sàng. Khi đó tránh một `ApplicationRunner` ném lỗi làm application context chết.

Thiết kế:

~~~text
Spring context starts
        |
        v
ReadinessState = REFUSING_TRAFFIC
        |
background bounded probe / state evaluator
        |
    +---+----+
    |        |
  Healthy  Unavailable
    |        |
  ACCEPT   REFUSE
    |
  Routes handle requests
~~~

Triển khai thực tế có thể dùng Spring `ApplicationAvailability`, `AvailabilityChangeEvent` hoặc một `HealthIndicator`/readiness health group có policy. **Không tạo vòng busy-loop** hoặc scheduler vô hạn bên trong health endpoint; dùng background scheduled check có backoff và hysteresis.

Điểm cần cân nhắc: default Spring Boot readiness state được chuyển thành `ACCEPTING_TRAFFIC` sau startup. Nếu tự quản lý readiness động, phải phối hợp đúng với lifecycle events để không có race giữa component tự đặt state và Boot auto-publish state.

## 11. Ngân sách timeout gồm nhiều lớp

~~~text
HTTP client deadline          2 s
  Application service budget  1.5 s
    SDK KV timeout            1.0 s
      Internal retries        dùng phần budget còn lại

Or on startup:
  Kubernetes startup budget  90 s
    Spring init              20 s
    Couchbase bucket ready   20 s
    Other startup checks     15 s
    Safety margin            35 s
~~~

Đây là **số ví dụ**, không phải default.

Bảng timeout:

| Timeout | Phạm vi | Dùng để điều chỉnh |
| --- | --- | --- |
| `connectTimeout` | Bucket open/connect theo SDK | Kết nối/tài nguyên khởi tạo |
| `kvTimeout` | KV operations thông thường | GET/INSERT/REPLACE không durable |
| `kvDurableTimeout` | KV mutation có durability nâng cao | Sync-write latency |
| `queryTimeout` | SQL++ Query Service request | Query plan/index/data volume |
| `disconnectTimeout` | Chờ SDK shutdown | Drain/cleanup |
| `waitUntilReady(Duration)` | Chờ bootstrap/endpoint readiness | Startup gate |
| HTTP/request timeout | Tổng nghiệp vụ | SLA từ caller |
| Kubernetes probes | Khoảng kiểm tra/threshold | Pod lifecycle |

Một `kvTimeout` dài hơn HTTP caller deadline có thể làm server xử lý request mà client đã bỏ cuộc; với mutation, outcome có thể ambiguous. Phải thiết kế **deadline và idempotency cùng nhau**.

## 12. Timeout config trong Spring Boot

Spring Boot hiện có các properties môi trường SDK:

~~~yaml
spring:
  couchbase:
    env:
      timeouts:
        connect: 10s
        key-value: 2500ms
        key-value-durable: 10s
        query: 75s
        disconnect: 10s
~~~

Đây là các **giá trị minh họa tương ứng với defaults thường thấy** trong tài liệu Spring Boot/Couchbase SDK 3.x, không phải một khuyến nghị tăng timeout. Các properties/giá trị chính xác phải xác nhận theo Spring Boot đang dùng.

Một số thao tác có per-operation timeout trong SDK options. Nếu chỉ một truy vấn báo cáo chậm, đổi timeout riêng cho query đó thường hợp lý hơn thay global KV budget của toàn application.

**Cảnh báo:** Timeout là triệu chứng, không phải chẩn đoán. Tăng `key-value` từ 2.5s lên 30s có thể khiến queue và HTTP thread/pending requests phình to, không sửa DNS/TLS, index scan, overload hay hot key.

## 13. Seed nodes và topology discovery

Trong Couchbase Server tự quản lý, production nên có **nhiều seed nodes có thể kết nối** trong connection string khi không sử dụng một DNS-SRV endpoint chuyên biệt:

~~~text
couchbase://node-a.example.com,node-b.example.com,node-c.example.com
~~~

SDK liên lạc một seed node để lấy **cluster configuration và danh sách endpoints thực tế**. Các seeds là điểm khởi tạo, không phải danh sách “chỉ được dùng những nodes này” cho toàn bộ vòng đời.

Do đó:

- Một seed chết không nhất thiết làm bootstrap thất bại nếu seed khác truy cập được.
- Không cần liệt kê mọi node nhưng nên có đủ địa chỉ bootstrap đáng tin.
- Không dùng IP tĩnh một node duy nhất rồi coi là highly available.
- Topology thay đổi (rebalance/failover) cần SDK nhận config cập nhật.
- Seed hostname phải có DNS và network đúng từ **vị trí chạy pod**, không chỉ từ laptop.
- Không để load balancer/proxy che/mutate giao thức theo cách SDK không hỗ trợ.

Với Couchbase Capella, **connection string `couchbases://...` dùng DNS-SRV và TLS** theo tài liệu Capella; không tự thay nó bằng một tập IP tĩnh khi chưa hiểu cơ chế giải quyết DNS-SRV.

## 14. DNS-SRV và Couchbase Capella

Capella thường cung cấp hostname cho DNS SRV lookup. Một lỗi `UnknownHost` hoặc timeout ở bootstrap có thể liên quan:

1. DNS resolver của pod không trả được `SRV` record dài.
2. CoreDNS/forwarder/network policy đang lỗi hoặc cache record cũ.
3. DNS host từ endpoint/region sai.
4. Network path, IP allowlist hoặc security group không cho client vào cluster.
5. Client dùng `couchbase://` thay vì `couchbases://` với Capella.
6. SDK/Java runtime quá cũ so với deployment/TLS features.
7. DNS trả hosts nhưng firewall không cho kết nối các service ports cần thiết.

Không gán mọi DNS-SRV error thành “sai password”. Chẩn đoán lần lượt **DNS → TCP/TLS → authentication → bucket/collection RBAC → service operation**.

SDK Doctor và lệnh DNS lookup ở **môi trường vận hành được cấp phép** có thể giúp xác định nguyên nhân; không in passwords/credentials trong logs hoặc command history.

## 15. TLS, truststore và certificate rotation

Một connection `couchbases://...` cần trust chain và certificate hostname hợp lệ. Nếu TLS handshake thất bại:

- Kiểm tra hostname trong certificate/SAN và connection string.
- Kiểm tra CA/truststore của JVM/container.
- Kiểm tra ngày hết hạn/rotation của certificate.
- Nếu self-managed cluster dùng custom CA, cấu hình trust root theo SDK phiên bản.
- Kiểm tra proxy TLS interception của mạng doanh nghiệp có được cho phép không.
- Kiểm tra system clock/NTP vì certificate validation phụ thuộc thời gian.
- Không log private keys, password, tokens hoặc PEM contents vào logs.
- Không tắt certificate verification như “giải pháp nhanh” trên production.

Một thay đổi certificate có thể khiến **connections cũ tiếp tục nhưng connections mới fail**. Nếu timeout chỉ xảy ra khi SDK cố reconnect/new sockets, hãy điều tra TLS/CA rotation thay vì liên tục tạo Cluster mới.


## 16. NAT, Kubernetes và `alternate addresses`

Với Couchbase Server chạy sau NAT, port mapping hay trong Kubernetes, client có thể khởi đầu kết nối tới seed thành công nhưng nhận topology gồm những **địa chỉ nội bộ không thể truy cập**:

~~~text
Pod ứng dụng -> seed.example.com:11207 [OK]
SDK nhận cluster config:
  node1.internal.local:11207
  node2.internal.local:11207
Pod không resolve/route được các địa chỉ mới
=> Bootstrap một phần, KV requests timeout
~~~

Cần kiểm tra advertised/alternate addresses phía Server, DNS, firewall, ports, TLS certificate hostname và cấu hình `io.networkResolution` (default/external) nếu network topology yêu cầu. SDK thường tự chọn địa chỉ phù hợp, nhưng NAT phức tạp cần kiểm chứng.

**Không hardcode một seed IP** để bỏ qua topology: sau rebalance/failover ứng dụng sẽ tiếp tục lỗi. Chẩn đoán ở **mạng của pod**, không chỉ laptop của lập trình viên.

## 17. `ping()` và `diagnostics()` là hai loại bằng chứng

| API | Network I/O? | Dùng khi nào | Giới hạn |
| --- | --- | --- | --- |
| `cluster.ping()` | Có | Kiểm tra trực tiếp các services/endpoints | Có chi phí, có thể mở socket |
| `bucket.ping()` | Có | Kiểm tra KV của bucket | Không xác nhận mọi business query |
| `cluster.diagnostics()` | Không | Xem socket/endpoint state SDK đang biết | Có thể stale |
| `waitUntilReady(...)` | Chờ readiness đến deadline | Startup gate, khôi phục có kiểm soát | Không tự chữa lỗi cấu hình |

~~~java
var ping = bucket.ping();
System.out.println(ping.exportToJson());

var diagnostics = cluster.diagnostics();
System.out.println(diagnostics.state());
~~~

`diagnostics().state()` có thể là `ONLINE`, `DEGRADED` hoặc `OFFLINE` theo SDK socket states. Đây là **client-side view**, không có nghĩa mọi query/operation chắc chắn thành công.

Không gọi active ping ở **mọi HTTP request**, vì sẽ thêm I/O và tăng tải khi cluster đang suy giảm. Dùng cadence/budget cụ thể và caching/aggregation khi cần.

## 18. Ping đúng service mà workload phụ thuộc

Theo tài liệu SDK, ping ở cấp Cluster có thể không bao gồm KV service tùy Server version; để xác minh **KV bucket**, dùng `bucket.ping()`.

Ví dụ giới hạn service với Query:

~~~java
import com.couchbase.client.core.service.ServiceType;
import java.util.EnumSet;
import static com.couchbase.client.java.diagnostics.PingOptions.pingOptions;

var queryPing = cluster.ping(
        pingOptions().serviceTypes(
                EnumSet.of(ServiceType.QUERY)));
~~~

Chữ ký/import cần được biên dịch với SDK version của dự án trước khi dùng. Một response ping không chứng minh Query index/schema/permissions đều đúng. Một cluster có thể vừa phục vụ KV tốt, vừa gặp lỗi Query Service hoặc Search Service.

Readiness nên gắn với những **thành phần thực sự cần** cho chức năng đang cung cấp.

## 19. Spring Boot Actuator health và khả năng sẵn sàng

Khi có dependencies phù hợp, Spring Boot Actuator có thể tự tạo `CouchbaseHealthIndicator` hoặc `CouchbaseReactiveHealthIndicator` và hai indicators trạng thái ứng dụng `livenessState`, `readinessState`.

Những URLs phổ biến:

~~~text
/actuator/health
/actuator/health/liveness
/actuator/health/readiness
/livez      (khi add-additional-paths=true)
/readyz
~~~

Không nhầm `/actuator/health` với `/actuator/health/readiness`. Spring Boot **không mặc định thêm mọi external HealthIndicator vào readiness group**.

Có thể cấu hình:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: "readinessState,couchbase"
~~~

Đây là **lựa chọn chính sách**, không phải default nên bật ở mọi nơi. Kiểm tra Couchbase indicator có thật, tên health component và Boot version.

Nếu Couchbase là dependency **dùng chung cho tất cả pods**, thêm nó vào readiness có thể khiến toàn bộ pods `UNREADY` cùng lúc. Tùy ingress/load balancer, người dùng có thể nhận connection refused hoặc HTTP 503; phải cân nhắc failover/routing/fallback.

## 20. `startupProbe`, `livenessProbe` và `readinessProbe`

| Probe | Câu hỏi | Khi lỗi kéo dài | Có nên truy vấn Couchbase? |
| --- | --- | --- | --- |
| Startup | Pod hoàn thành startup chưa? | Restart sau startup budget | Chỉ kiểm tra cần thiết |
| Liveness | Process có bị kẹt/hỏng nội tại? | Restart pod | **Không** gắn external dependency |
| Readiness | Pod có nên nhận traffic lúc này? | Gỡ khỏi Service endpoints | Tùy critical path/fallback |

Ví dụ Kubernetes với Spring Boot có `add-additional-paths=true`:

~~~yaml
startupProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 5
  failureThreshold: 30

livenessProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Khi main web server khởi động chậm, `startupProbe` giúp tránh liveness kill pod sớm; readiness vẫn chặn traffic. Nếu Actuator dùng management port riêng, probe trên cổng quản trị UP chưa chắc web server chính nhận request được. Chọn path/port đúng deployment.

Các ngưỡng 5/10/30 chỉ là ví dụ, phải đo startup distribution và SLO.

## 21. Vì sao không đặt Couchbase vào liveness?

Sự cố cluster dùng chung:

~~~text
Couchbase unavailable 90 giây
  |
  +-- Pod A liveness DOWN -> restart
  +-- Pod B liveness DOWN -> restart
  +-- Pod C liveness DOWN -> restart
  +-- Tất cả pod cùng bootstrap lại khi cluster đang lỗi
  +-- Connection storm làm kéo dài recovery
~~~

Restart pod **không sửa** database/network bên ngoài, còn làm mất in-flight work. Liveness nên dựa trên sự sống của JVM/event-loop và các tình huống mà restart có thể khắc phục.

Readiness có thể quyết định ngừng traffic theo workload và fallback. Alert phải dựa trên operation latency/timeout/error mix và backlog, không chỉ một boolean `ClusterState`.

## 22. “Đủ sẵn sàng” khác nhau theo endpoint

Ví dụ:

~~~text
GET /products/preview
    Có cache stale cho phép ≤ 2 phút nếu Couchbase lỗi.

POST /orders/confirm-payment
    Cần KV/transaction đúng, không thể degraded tùy tiện.

GET /health/readiness
    Chính sách dựa trên những critical routes cần phục vụ.
~~~

Nếu Couchbase không sẵn nhưng chỉ một số routes cần DB, pod có thể vẫn ready và các routes critical trả controlled `503`/`Retry-After` hoặc accepted async job theo contract. Nếu toàn bộ hệ thống phụ thuộc DB, readiness false có thể hợp lý hơn.

Không fallback write critical thành “lưu trong memory rồi trả success” nếu không có durable queue và reconciliation.

## 23. Sau mất kết nối: SDK quản lý sockets và topology

SDK giữ một hạ tầng quản lý connections tới Data/Query/Services. Khi một node offline, failover hoặc network glitch, SDK có thể **phân loại lỗi, retry request đủ điều kiện, nhận topology mới và tái tạo sockets**.

~~~text
T0  Cluster online
T1  KV node/network segment mất kết nối
T2  Một số requests timeout/retry/cancel
T3  SDK nhận topology/vBucket mapping cập nhật
T4  Sockets được tái lập/traffic dùng endpoints mới
T5  New requests có thể thành công trở lại
~~~

Không có cam kết mọi in-flight request sẽ thành công hoặc “reconnect trong N giây” dưới mọi điều kiện.

**Không `disconnect()` rồi `Cluster.connect()` cho từng exception.** Nó phá lifecycle Spring, có thể làm mất in-flight work, nhân clients/TLS handshakes và tạo connection storm. Để SDK quản lý recovery; chỉ xây lại client khi có quyết định vận hành cụ thể (ví dụ thay credential/cluster target theo quy trình an toàn).


## 24. `BestEffortRetryStrategy` không có nghĩa mọi request sẽ retry

Java SDK 3.x có `BestEffortRetryStrategy` mặc định: request có thể được retry theo `RetryReason` nếu semantics cho phép, trong **timeout budget** của operation.

Các điểm quan trọng:

- Retry nội bộ không phải vòng vô hạn; request vẫn có thể timeout.
- `DocumentNotFoundException`, `CasMismatchException` hoặc sai quyền RBAC **không** biến thành “thử cho tới khi thành công”.
- SDK phân loại an toàn với non-idempotent operations; tùy loại request, một số retry reasons không cho retry.
- Một socket reset trước/khi dispatch có thể dẫn tới hành vi khác với response application-level error.
- `ErrorContext` có thể cho biết retry reasons và elapsed time.
- Nếu thêm Spring Retry/Reactor retry bên ngoài, tổng attempts/latency có thể cao hơn dự định.
- Không override retry strategy chỉ để “bắt mọi lỗi”; callback ở SDK hot path không được block.

**Đừng thay `BestEffortRetryStrategy` bằng logic tùy biến không hiểu idempotency.** Thời gian chờ/failed result có thể là vấn đề network, tải server hoặc configuration, không nhất thiết retry càng nhiều càng tốt.

## 25. Phân loại lỗi trước khi quyết định reconnect

| Loại | Ví dụ | Xử lý |
| --- | --- | --- |
| Bootstrap/configuration | DNS/SRV không hoạt động, TLS CA sai, credentials sai | Sửa cấu hình/mạng, không retry vô hạn |
| Transient transport | Socket reset, node failover, network flap | SDK tự quản lý sockets; retry bounded |
| Data semantics | `DocumentNotFoundException`, `DocumentExistsException` | Business outcome, không reconnect |
| Optimistic locking | `CasMismatchException` | Đọc lại/merge đúng invariant |
| Authorization | RBAC bị từ chối ở scope/collection | Fail closed, sửa quyền |
| Query/index | Chỉ mục chưa có hoặc SQL++ sai | Sửa index/query, không tạo Cluster mới |
| Capacity | p99 cao, request queue tăng, timeout nhiều | Backpressure/rate cap/capacity plan |
| Canceled | `RequestCanceledException` | Xem retry/timeout/cancellation source |
| Ambiguous write | `AmbiguousTimeoutException` | Reconcile, không retry mù |

Một lỗi trong **một KV request** không chứng minh Cluster object không thể phục hồi. Ngược lại, `diagnostics().state() == ONLINE` không chứng minh mọi operation đúng/đủ quyền.

## 26. Mutation có thể thành công trước khi client timeout

Timeline:

~~~text
T0  Client gửi upsert(order::1001)
T1  Server ghi thành công, CAS thay đổi
T2  Response bị mất do network
T3  Client nhận AmbiguousTimeoutException
~~~

Nếu application retry một stale body bằng `upsert` không CAS, nó có thể ghi đè dữ liệu của writer khác.

Chính sách an toàn:

1. Phân biệt `AmbiguousTimeoutException` và `UnambiguousTimeoutException`.
2. Có `commandId`/`idempotencyKey` ổn định cho write nghiệp vụ.
3. Với write ambiguous, đọc lại trạng thái thực và đối chiếu business event/payload/version.
4. Với CAS conflict, đọc–merge–replace theo invariant, giới hạn số attempts.
5. Không trả `failed, chắc chắn chưa ghi` nếu outcome không xác định.
6. Với nhiều document phải cùng commit, dùng transaction context phù hợp.
7. Không coi việc SDK đã reconnect là bằng chứng retry write không có side effect.

Trong Spring Data Couchbase, entity có `@Version` sử dụng CAS để optimistic locking khi Repository/Template cập nhật theo đường hỗ trợ. Nếu một job trong giai đoạn phục hồi chuyển sang raw SDK `upsert` không CAS, nó không tự tôn trọng `@Version`: bản dữ liệu cũ có thể ghi đè document vừa được writer khác sửa. Với SDK direct, dùng conditional `replace` với CAS hoặc transaction/business-idempotency policy phù hợp, không bypass version chỉ để retry cho thành công.

Read-only GET thường có thể retry đơn giản hơn, nhưng phải tuân thủ deadline, authorization và capacity policy.

## 27. Application retry chỉ dùng khi có ngân sách và đúng semantics

Ví dụ một **read-only GET** được phép thử lại:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Mono<GetResult> read =
        Mono.defer(() -> collection.reactive().get(documentId))
            .retryWhen(
                Retry.backoff(2, Duration.ofMillis(150))
                    .filter(ex -> ex instanceof
                            UnambiguousTimeoutException))
            .timeout(Duration.ofSeconds(2));
~~~

`UnambiguousTimeoutException` là một lựa chọn filter minh họa, không phải danh sách đầy đủ lỗi transient. SDK vốn đã có internal retry; lớp retry ứng dụng **không mặc định cần thiết**. `timeout` Reactor hủy subscription, nhưng không bảo đảm một request đã gửi ra mạng không còn được thực hiện.

Đừng sao chép đoạn này cho `increment`, `upsert` hoặc gọi payment HTTP nếu chưa thiết kế idempotency. Không đặt `retry(3)` bên ngoài **cả một batch writes** vì có thể thực hiện lại những items đã thành công.

## 28. Circuit breaker và bulkhead giữ tài nguyên ổn định

Khi database down kéo dài, hàng nghìn requests cùng chờ timeout có thể làm process quá tải ngay cả khi SDK xử lý mạng nonblocking.

~~~text
HTTP ingress
    |
    +-- Admission/rate limiter
    +-- Circuit breaker theo operation/service
    +-- Bulkhead/concurrency cap
    +-- Repository / Template / SDK
    +-- Error mapping / fallback / result
~~~

Thiết kế:

- Circuit `OPEN` không gửi mọi request xuống cluster đang bất khả dụng.
- `HALF_OPEN` chỉ cho số probes/requests hạn chế để kiểm tra phục hồi.
- KV/Query/Search có thể cần policies khác.
- 404/CAS conflict không nên làm circuit coi như transport outage.
- Khi phục hồi, tăng lưu lượng dần để tránh thundering herd.
- Rate limit theo tenant/pod/global budget; không để một tenant chiếm mọi sockets.
- Business-critical writes không được “fallback ghi RAM rồi báo thành công” nếu thiếu durable queue/reconciliation.
- Circuit breaker không thay SDK topology/retry, mà bảo vệ **application capacity**.

## 29. Backpressure: giới hạn in-flight khác giới hạn tổng hàng chờ

Ví dụ:

~~~text
Ingress:   2.000 ops/s
DB xử lý:    500 ops/s
Backlog:  +1.500 ops/s (khi chưa reject)
~~~

Dù một `Flux.flatMap(...,16)` giới hạn 16 inner operations, 100 HTTP requests song song có thể đạt tổng 1.600 in-flight tại các operators đó.

Cần:

1. Input batch/body size cap.
2. Rate limiter và concurrency cap theo service/pod/tenant.
3. Bounded queue với deadline và reject policy.
4. Không `collectList()` một stream vô hạn.
5. Retry ngân sách nhỏ và tránh retry nguyên batch mutation.
6. Đo queue length/oldest item age, timeout và OOM/GC.
7. Tạm giảm background jobs khi OLTP bị nghẽn.
8. Slow-start khi circuit đóng lại hoặc cluster phục hồi.
9. Nếu traffic vượt capacity lâu dài, tăng tài nguyên/giảm workload, không chỉ tăng timeout.

## 30. Scheduled jobs và consumers cần recovery riêng

Một worker nền có thể cần:

- Tạm dừng **nhận công việc mới** khi Couchbase unavailable, thay vì terminate process liên tục.
- Có checkpoint/job state bền vững để resume sau crash.
- Không ack message broker trước khi business update commit nếu contract yêu cầu.
- Sau timeout ambiguous, reconciliation trước replay.
- Dùng bounded concurrency cho backfill khi cluster hồi phục.
- Định nghĩa retention của queue/outbox đủ dài cho outage.
- Có DEAD/UNKNOWN status và human triage khi quá retry budget.
- Không tạo/đóng `Cluster` theo từng job.
- Đo backlog drain time và latency p99 của traffic người dùng trong lúc backfill.

Khi failover kéo dài quá job SLA, chuyển sang trạng thái deferred hoặc controlled failure theo business contract. Không tăng `kvTimeout` lên hàng phút để mọi job chiếm pending resources vô hạn.

## 31. Observability cho bootstrap và recovery

Bảng metric đề xuất (tên thuộc ứng dụng, không phải SDK tự phát toàn bộ):

| Metric | Ý nghĩa |
| --- | --- |
| `app_start_to_ready_seconds` | Từ process start đến chấp nhận traffic |
| `couchbase_startup_wait_seconds` | Thời gian `waitUntilReady` của startup gate |
| `couchbase_startup_timeout_total` | Số lần chờ bootstrap thất bại |
| `couchbase_connection_state` | Client-side state online/degraded/offline theo cách gán nhãn |
| `couchbase_kv_request_p99` | Latency đuôi của KV |
| `couchbase_query_request_p99` | Latency đuôi của SQL++ |
| `couchbase_timeout_total` | Timeouts theo service/operation/category |
| `couchbase_retry_reason_total` | Retry reasons đã tổng hợp |
| `readiness_transition_total` | Số lần readiness UP↔DOWN |
| `couchbase_recovery_duration_seconds` | Từ outage đến phục hồi SLO |
| `sdk_connection_endpoint_count` | Số endpoints open/degraded theo client diagnostics |
| `client_pending_queue_items` | Backpressure khi unavailable |

SDK Java có **LoggingMeter**/integration **Micrometer/OpenTelemetry** cho operation latency percentiles. SDK còn có threshold/orphaned request logging và Event Bus. Kết hợp SDK metrics với Spring Boot Actuator, system/network metrics và Server dashboards.

Một `ClusterState.ONLINE` không thay end-to-end SLO. Chỉ số trọng tâm là **business request success/latency, pending workload, reconnect recovery**.

## 32. Logging và ErrorContext hỗ trợ điều tra

Khi một KV get timeout, tránh chỉ log:

~~~text
java.lang.RuntimeException: Couchbase error
~~~

Nên ghi ở logs nội bộ có kiểm soát:

~~~text
operation=get
service=KV
bucket=shop
scope=crm
collection=customers
errorCategory=UNAMBIGUOUS_TIMEOUT
elapsedMs=2500
sdkRetryReason=...
traceId=...
pod=checkout-api-7d4
~~~

Đây là **log schema ví dụ**; tên trường có thể khác SDK `ErrorContext` thực tế. Các nguồn hữu ích:

- Exception hierarchy và `ErrorContext` để xem retry reasons/timing.
- SDK `ping()/diagnostics()` cho service/endpoint state.
- Threshold Logging Tracer cho slow operations.
- Orphaned response logs khi response đến muộn so với client deadline.
- Spring/Micrometer timer cho request/business operation.
- Couchbase server node CPU/memory/disk, failover/rebalance logs.
- DNS/network/TLS handshake telemetry từ infrastructure.
- `requestId` và `clientContextId` của SQL++ nếu đã có.

**Không** log password, auth token, toàn bộ connection string có secret, raw JSON PII, document key nhạy cảm, hay full ErrorContext công khai. Không dùng document ID/pod unique ID cho high-cardinality metric labels; logs/traces có redaction/retention riêng.

## 33. Graceful shutdown: không đóng Cluster quá sớm

Khi Kubernetes gửi SIGTERM/rolling deployment:

~~~text
T0  Readiness = REFUSING_TRAFFIC
T1  Ngừng nhận requests/jobs mới
T2  Cho in-flight requests hoàn tất trong ngân sách
T3  Flush/commit checkpoints, broker offsets theo contract
T4  Spring ApplicationContext đóng
T5  SDK Cluster disconnect/drain connections
T6  Process exit trước terminationGracePeriod
~~~

Nguyên tắc:

- Với `Cluster` do Spring auto-configure, **để Spring quản lý shutdown**.
- Không gọi `disconnect()` trong business request/`ApplicationRunner` hoặc health endpoint.
- Nếu application **tự tạo** Cluster riêng, phải quản lý `disconnect` ở đúng owner/lifecycle.
- SDK `disconnectTimeout` giới hạn chờ drain; không bảo đảm mọi pending writes đều đã commit.
- Một request bị kill khi đang mutation có thể có outcome chưa rõ, cần idempotency/reconciliation.
- Liveness không nên chuyển DOWN chỉ vì app bắt đầu graceful shutdown; readiness mới phù hợp.
- Thiết lập `terminationGracePeriodSeconds`, HTTP graceful shutdown và job cancel budget có thứ tự.
- Chạy test rolling restart khi vẫn có traffic, không chỉ test `System.exit(0)` lúc idle.


## 34. Rolling deployment và startup budgets

Một rollout tạo nhiều pods cùng bootstrap tới Couchbase có thể tạo connection pressure. Nếu pod cũ bị terminate **trước khi pod mới ready**, ứng dụng mất capacity dù database bình thường.

Cần phối hợp:

- `maxSurge`/`maxUnavailable` và desired replicas theo SLO.
- `startupProbe` đủ budget cho cold-start, `readinessProbe` đo đúng policy.
- `terminationGracePeriodSeconds` đủ drain requests/jobs.
- CPU/memory đủ cho TLS handshake, DNS và initial SDK configuration.
- Không build GSI/migrate data tại **mọi replica** trong startup gate.
- Stagger rollout nếu cluster đang rebalance/overloaded.
- Có rollback image/config nếu pod mới fail TLS/RBAC/bucket readiness.
- Theo dõi `time_to_ready` p50/p95/p99 theo release và cluster topology.

Ví dụ:

~~~text
6 pods serving
  -> Khởi động tối đa 2 pods mới
  -> Chờ bucket readiness/HTTP readiness
  -> Chuyển traffic có kiểm soát
  -> Drain/terminate pod cũ
  -> Lặp lại
~~~

## 35. Secret, certificate và DNS rotation lúc runtime

| Thay đổi | Triệu chứng | Chính sách |
| --- | --- | --- |
| DB password/account | Connections mới auth failed | Rotation có kế hoạch/chồng lấn |
| TLS root CA | Handshake lỗi sau reconnect | Rollout truststore/bundle trước |
| Server certificate | Hostname/expiry mismatch | Kiểm tra SAN/chain/clock |
| DNS-SRV | Pods mới fail, pods cũ còn chạy | Kiểm tra resolver/TTL |
| Firewall/security group | Một số service ports không tới được | Sửa routing/policy |
| RBAC scope/collection | GET/Query bị permission denied | Sửa quyền, không tăng timeout |
| Cluster advertised addresses | Bootstrap được seed nhưng KV timeout | Sửa alternate addresses |

Không mặc định SDK sẽ tự đọc lại credentials mới từ environment variables hay JVM truststore khi secret đổi. Tùy cách cấu hình, có thể cần **controlled client replacement/rolling restart** với drain, không reconnect toàn fleet cùng lúc.

## 36. Runbook: không bootstrap được

Một quy trình tìm nguyên nhân:

1. **Scope:** mọi pods fail hay chỉ một zone/namespace?
2. **Stage:** Spring bean creation, `waitUntilReady`, hay KV request đầu tiên?
3. **Config:** scheme `couchbase://`/`couchbases://`, bucket, credentials, active profile.
4. **DNS:** A/AAAA/SRV resolve được từ **cùng pod network** không?
5. **TCP:** seed và topology endpoints có reachable qua các ports đúng không?
6. **TLS:** certificate chain, hostname, truststore, expired CA, system clock.
7. **RBAC:** user có quyền tại bucket/scope/collection cần truy cập không?
8. **SDK:** xem diagnostics, bootstrap logs và exception ErrorContext đã redaction.
9. **Server:** node/service status, rebalance, failover, bucket tồn tại, overload?
10. **Decision:** sửa lỗi nền, giảm simultaneous bootstrap hoặc rollback; không tăng timeout vô tội vạ.

### Một số dấu hiệu dễ phân biệt

~~~text
UnknownHost / DNS SRV lookup failed
  -> DNS/resolver/endpoint

TLS handshake/certificate exception
  -> CA/truststore/hostname/rotation

Authentication/Authorization
  -> Secrets, RBAC, scope

WaitUntilReady timeout
  -> Endpoints/network/Server capacity; chưa thể kết luận phải tăng timeout

KV timeout chỉ trên request đầu
  -> Kiểm tra lazy bootstrap, nhưng vẫn điều tra DNS/TLS/network

KV GET OK, SQL++ fail
  -> Query Service, GSI/index, query syntax/RBAC
~~~

## 37. Runbook: mất kết nối khi đang phục vụ

1. **Không** đồng loạt `disconnect/connect` hay restart pods khi chỉ có vài KV timeouts.
2. Phân tách lỗi theo KV/Query/Search, endpoint, tenant và availability zone.
3. Dùng `diagnostics()` (passive) và `ping()` có cadence hợp lý; không tạo ping flood.
4. Kiểm tra node failover/rebalance, DNS/TLS/secret rotations và network events.
5. Giảm traffic với circuit breaker, bulkhead; tạm dừng jobs không ưu tiên.
6. Những mutation timeout ambiguous cần ghi `UNKNOWN` và reconciliation, không retry mù.
7. Giữ checkpoints/queue state cho workers, không ack broker trước durable business commit.
8. Khi endpoints hoạt động, half-open circuit và tăng tải từng bước.
9. Chỉ coi là recovery khi p95/p99, success rate và backlog về ngưỡng SLO.
10. Ghi incident timeline, root cause, change plan và runbook follow-up.

Một `ping` thành công không chứng minh hệ thống có thể chịu peak load như trước outage.

## 38. Ma trận triệu chứng và xử lý

| Triệu chứng | Giả thuyết đầu | Cần thu thập |
| --- | --- | --- |
| First request rất chậm | Lazy bootstrap | KV first-request timing, startup milestones |
| Pods mới fail, pods cũ OK | DNS/secret/cert rotation | Config/version, TLS and DNS |
| Cluster DEGRADED, GET vẫn OK | Endpoint phụ không reachable | Diagnostics per-service |
| Cluster ONLINE nhưng p99 cao | Overload/hot key/network | Server CPU, SDK operation percentiles |
| Query lỗi, KV khỏe | Index/Query Service/RBAC | Query error context, `EXPLAIN` |
| CAS mismatch tăng | Writer conflict | BusinessVersion/CAS logs |
| Unambiguous timeout tăng | Latency/budget/network | Retry reason, endpoint/queue |
| Ambiguous timeout mutation | Ack bị mất sau write | CommandId/current state |
| Readiness liên tục đổi UP/DOWN | Probe nhạy/hysteresis thiếu | Probe history, app load |
| Liveness fail khi DB outage | Probe dependency sai | Health group/probe config |
| Shutdown mất pending writes | Grace period ngắn | SIGTERM timeline/in-flight requests |

## 39. Integration tests cho startup/readiness

Chạy trên môi trường có Couchbase Server và Spring Boot tương thích, không chỉ mock Cluster.

**A — Healthy start**

~~~text
Given bucket có thể kết nối
When Spring Boot app khởi động
Then chỉ một Cluster bean dùng chung
And startup gate waitUntilReady hoàn thành
And readiness lên UP sau startup tasks
~~~

**B — DB unavailable, fail-fast policy**

~~~text
Given seed endpoints không reachable
When app starts
Then startup fail trong bounded budget
And không loop vô hạn hay leak clients
~~~

**C — Degraded startup**

~~~text
Given app chủ ý hỗ trợ degraded
When Couchbase unavailable
Then process vẫn sống
And readiness phản ánh critical routes
And independent routes vẫn chạy nếu policy cho phép
~~~

**D — Health groups**

~~~text
Liveness không phụ thuộc Couchbase outage
Readiness phản ánh policy
Kiểm tra /livez nếu cấu hình thêm path trên main server port
/readyz hoạt động trên cổng chính khi được bật
~~~

Các đoạn Given/When/Then là mô hình test; cần hiện thực với Testcontainers hoặc Couchbase test environment theo nhu cầu và quyền truy cập hợp lệ.

## 40. Fault injection nên bao phủ cả bootstrap và recovery

| Fault | Kỳ vọng |
| --- | --- |
| Tất cả seeds offline trước boot | Startup chờ hữu hạn, không hung |
| Một seed mất, seed khác còn | Bootstrap vẫn có thể thành công |
| DNS-SRV lỗi | Chẩn đoán DNS, không lộ credential |
| TLS CA không tin cậy | Fail an toàn, không tắt verification |
| Wrong password/RBAC | Không retry vô hạn |
| Bucket không tồn tại | Readiness/gate báo đúng |
| Query Service down, KV OK | Degraded policy đúng |
| Node failover/rebalance | SDK recovery và timeout metrics rõ |
| Network partition 30 giây | Circuit/queue giới hạn tài nguyên |
| RTT tăng ×10 | Tail latency/timeout tăng được quan sát |
| Ambiguous write timeout | Không double-apply khi retry |
| SIGTERM giữa mutation | Drain và reconciliation |
| 50 pods khởi động cùng lúc | Không có connection storm ngoài budget |
| Certificate rotation | Pods cũ/mới có kế hoạch rollout |

Fault injection chỉ làm ở staging/test cluster cô lập; không ngắt mạng production khi chưa có kế hoạch rủi ro và phê duyệt.

## 41. Performance và đo thời gian recovery

Benchmark ít nhất:

~~~text
Cold start, warm start
Network RTT bình thường vs cao
Một seed mất, node failover/rebalance
Query Service down, KV healthy
TLS/DNS rotation
Peak traffic và đồng thời có backfill
~~~

Theo dõi:

- `time_to_ready` p50/p95/p99.
- First KV latency so với steady-state KV latency.
- Query p95/p99, Index freshness nếu nghiệp vụ cần.
- Recovery duration từ outage tới khi đạt lại SLO.
- Readiness flapping, restart count và pending work.
- SDK timeouts, ambiguous/unambiguous, retry reasons.
- JVM heap/GC/CPU, connections và broker/job backlog.
- Số lượng pods cùng bootstrap và thời gian rolling deployment.

Không tối ưu startup bằng cách xóa readiness checks rồi chuyển lỗi sang request đầu tiên. Ngược lại, không chạy quá nhiều active probes khiến ứng dụng tự tạo tải và khởi động chậm hơn.


## 42. Reactive startup và phục hồi không được block event loop

Reactive SDK có phương thức:

~~~java
import reactor.core.publisher.Mono;
import java.time.Duration;

Mono<Void> ready =
        cluster.reactive()
                .waitUntilReady(Duration.ofSeconds(20));
~~~

`Mono<Void>` là một **Publisher**; ứng dụng phải gắn subscription/lifecycle của nó với readiness state hoặc startup orchestration.

Các sai lầm:

~~~java
Mono<Void> stillBlocking = Mono.fromRunnable(
        () -> cluster.waitUntilReady(Duration.ofSeconds(20)));
~~~

Ví dụ `Mono.fromRunnable` ở trên **vẫn chạy thao tác chờ blocking trên thread subscribe**; chỉ bọc vào một publisher không tự biến I/O thành nonblocking. Tương tự, `Mono.just` không giúp tránh blocking của biểu thức Java được thực thi trước khi tạo Mono.

Không làm:

~~~java
public Mono<Customer> getCustomer(String id) {
    cluster.waitUntilReady(Duration.ofSeconds(30));
    return repository.findById(id);
}
~~~

vì đoạn đầu có thể block thread gọi method, đặc biệt khi handler WebFlux chạy trên event loop.

Chọn một trong hai cách:

1. Startup gate đồng bộ ở `ApplicationRunner`, **trước** khi web app nhận traffic, với budget rõ.
2. Nonblocking readiness workflow dùng `ReactiveCluster.waitUntilReady`, cập nhật app readiness state đúng lifecycle, tránh fire-and-forget subscription không được giám sát.

Không gọi `block()` ở event loop; nếu legacy blocking API không tránh được, dùng scheduler phù hợp có giới hạn và không coi đó là reactive IO thật. Một `Mono` đã hoàn thành ready **không bảo đảm uptime mãi mãi** — vẫn phải monitor runtime health và operation errors.

## 43. Quy tắc chọn timeout và probes theo workload

| Workload | Startup gate | Runtime timeout | Failure policy |
| --- | --- | --- | --- |
| API chỉ KV theo key | `bucket.waitUntilReady` hoặc readiness gate KV | KV budget theo HTTP SLA | 503/defer khi unavailable |
| API SQL++ tìm kiếm/sắp xếp | KV + Query/index readiness nếu bắt buộc | Query timeout riêng | Circuit Query, không làm chết KV nếu tách routes |
| Batch import 100k docs | Worker startup linh hoạt, checkpoint | KV timeout + job deadline | Retry từng item/idempotency |
| Transaction nhiều docs | Transaction configuration đúng | Transaction timeout + commit semantics | Reconcile ambiguous |
| Search/Analytics report | Service-specific readiness nếu critical | Search/Analytics budget riêng | Có thể serve cached/as-of report |
| Event consumer | Có queue retention và nack/defer policy | DB write deadline + broker ack budget | Không ack trước durable commit |
| Cache-first read-only API | Degraded có chủ đích | Cache TTL + Couchbase fallback policy | Stale label và SLO riêng |

**Không có một timeout toàn cục tối ưu cho mọi service.** Phân biệt cold-start allowance với steady-state latency, transaction deadline với KV timeout, và network bootstrap với database business readiness.

## 44. Các anti-pattern dễ gây sự cố dây chuyền

| Anti-pattern | Tác hại | Giải pháp |
| --- | --- | --- |
| `Cluster.connect` trong mỗi request | TCP/TLS/bootstrap storm | Dùng Spring-managed Cluster |
| `disconnect/reconnect` cho mọi KV timeout | Phá in-flight, tăng lỗi | Để SDK recovery, phân loại lỗi |
| Tin `cluster.bucket` là KV đã ready | First-request timeout | `bucket.waitUntilReady` khi cần |
| Chờ vô hạn trong `@PostConstruct` | Startup treo, probe kill | Bounded gate/lifecycle rõ |
| Dùng Couchbase indicator trong liveness | DB outage → restart cả fleet | Liveness nội tại, readiness theo policy |
| Tăng mọi timeout khi p99 tăng | Queue bành trướng, che root cause | Phân tích logs/metrics/network |
| Query Service lỗi rồi restart Cluster | Không sửa index/schema | Kiểm tra Query/index/RBAC |
| Bỏ qua DNS-SRV/alternate addresses | Bootstrap nửa vời | Kiểm tra topology thực từ pod |
| Tắt TLS verification cho nhanh | Mất bảo mật | Sửa certificate/CA/hostname |
| `diagnostics ONLINE` = mọi thao tác OK | False-positive readiness | Health theo service/critical operation |
| Ping toàn cluster mỗi 100 ms | Tải thêm, socket churn | Sampling/cadence/cache |
| Retry toàn batch writes | Duplicate, lost update | Per-key idempotency/reconcile |
| Retry CAS mismatch bằng unconditional upsert | Lost update | Read–merge–replace CAS |
| Fail-open write “success” khi DB down | Mất dữ liệu | Durable queue/defer/controlled 503 |
| `collectList` vô hạn khi outage | OOM/GC | Stream/queue bounds |
| Shutdown Cluster trước drain | In-flight writes bị cancel | Spring graceful shutdown |
| Không test rotation/failover | Chỉ chạy được happy path | Fault injection + runbook |

## 45. Checklist trước triển khai production

### Khởi động và cấu hình

- [ ] Một owner quản lý `Cluster`, `Bucket` và lifecycle; không connect per request.
- [ ] Connection string và seed/SRV đúng environment.
- [ ] `couchbases://`, TLS/CA, authentication và RBAC đúng deployment.
- [ ] NAT/alternate addresses, DNS và network ports đã kiểm tra **từ pod**.
- [ ] Có chính sách fail-fast/degraded/unready rõ.
- [ ] `waitUntilReady` ở Cluster/Bucket level theo workload, timeout hữu hạn.
- [ ] Startup budget tương thích Kubernetes startupProbe/rolling release.
- [ ] Spring Boot properties/timeouts đã đối chiếu phiên bản thực.

### Runtime và phục hồi

- [ ] Liveness không gắn trực tiếp sự cố Couchbase bên ngoài.
- [ ] Readiness dựa trên mức phụ thuộc critical và fallback.
- [ ] SDK retry và app retry có tổng attempt/time budget.
- [ ] Lỗi transient khác business conflict/authorization/schema error.
- [ ] Mutation ambiguous có idempotency/reconciliation.
- [ ] Có circuit breaker, bulkhead, bounded queue và rate limit phù hợp.
- [ ] Worker/job có checkpoint và recovery sau outage.
- [ ] Timeout KV/Query/Analytics/Search/transaction không bị trộn tùy tiện.
- [ ] Traffic được khôi phục từ từ sau failover, không retry storm.

### Quan sát và kiểm thử

- [ ] Có `time_to_ready`, p99 KV/Query, timeouts, retry, recovery SLO.
- [ ] SDK ping/diagnostics được dùng đúng chi phí và service.
- [ ] ErrorContext/threshold/orphan logs có redaction.
- [ ] Secrets và document keys không bị đưa vào metric labels.
- [ ] Có integration tests cho bootstrap, fail-fast/degraded và readiness.
- [ ] Có fault injection DNS/TLS/RBAC/network/rebalance.
- [ ] Có test rolling deployment, graceful shutdown, cert rotation.
- [ ] Runbook có người sở hữu, rollback criteria và incident follow-up.

## 46. Bài tập thực hành

**Phần A — Startup**

1. Dùng Spring Boot + Spring Data Couchbase kết nối tới test cluster.
2. Cấu hình env `COUCHBASE_CONNECTION_STRING`, username/password, bucket.
3. Inject `Cluster` vào một adapter; xác minh không tạo Cluster mới per request.
4. Đo thời gian Spring startup, `bucket.waitUntilReady` và first KV get.
5. Thêm `CouchbaseStartupGate` với budget 20 giây (chỉ ví dụ).
6. Stop cluster trước khi app start, xác minh fail-fast bounded.
7. Chuyển sang policy unready/degraded có chủ đích và so sánh.

**Phần B — Probes**

1. Bật Actuator liveness/readiness.
2. Expose `/livez` và `/readyz` trên main port nếu Boot version hỗ trợ.
3. Tạo một test deployment có startupProbe/livenessProbe/readinessProbe.
4. Gây DB outage trong staging và xác minh **liveness không restart pods** chỉ do DB.
5. Thử readiness có/không gồm Couchbase indicator; giải thích trade-off all-pods-unready.
6. Đo readiness transition/hysteresis và traffic router behavior.
7. Xác minh endpoint `/actuator/health` khác `/actuator/health/readiness`.

**Phần C — Reconnect và retries**

1. Kiểm tra `cluster.diagnostics()` và `bucket.ping()` khi bình thường.
2. Network-partition một node trong môi trường test.
3. Quan sát KV p99, timeout, retry reason và server topology.
4. Cho node phục hồi, đo recovery time đến SLO, không tạo Cluster mới.
5. Gây CAS mismatch và chứng minh reconnect không giải quyết business conflict.
6. Giả lập ambiguous mutation timeout, thiết kế reconciliation.
7. Test background worker/backlog khi cluster down, tránh retry storm.

**Phần D — TLS/rotation và shutdown**

1. Kiểm tra DNS SRV, network endpoints từ pod.
2. Thử wrong truststore trong staging, quan sát TLS failure.
3. Viết kế hoạch CA/credential rotation theo rolling deployment.
4. SIGTERM khi có 100 in-flight operations, kiểm tra shutdown budget.
5. Xác minh jobs/consumers không ack sớm trước khi DB commit.
6. Viết incident runbook dựa trên bảng triệu chứng ở mục 38.

## 47. Câu hỏi tự kiểm tra

1. Vì sao `Cluster.connect()` trả về chưa chứng minh bucket KV sẵn sàng?
2. `Bucket.waitUntilReady` khác `Cluster.waitUntilReady` điểm nào?
3. Một lần `waitUntilReady` thành công có bảo đảm không timeout về sau không?
4. Vì sao Spring-managed Cluster nên được tái sử dụng?
5. Lỗi first-request timeout có thể do những nguyên nhân nào?
6. Khi nào chọn fail-fast, start-but-unready hoặc degraded start?
7. `ApplicationRunner` gate có thể khiến startup fail theo cách nào?
8. `livenessProbe` khác `readinessProbe` và `startupProbe` thế nào?
9. Vì sao không thêm external Couchbase health vào liveness?
10. Nếu mọi pods cùng unready khi DB outage, load balancer có thể phản ứng ra sao?
11. `cluster.ping()` khác `cluster.diagnostics()` về network I/O?
12. Vì sao muốn kiểm tra KV cần cân nhắc `bucket.ping()`?
13. `ClusterState.ONLINE` có đồng nghĩa mọi Query/index đều đúng không?
14. `connectTimeout` và `kvTimeout` giải quyết những giai đoạn khác nhau thế nào?
15. Vì sao tăng timeout không phải biện pháp khắc phục chung?
16. DNS SRV/alternate addresses ảnh hưởng bootstrap ra sao?
17. Khi chứng chỉ được rotate, tại sao pods cũ có thể OK nhưng pods mới lỗi?
18. SDK có tự retry mọi lỗi vô hạn không?
19. Khi nào `DocumentNotFoundException` không phải lý do reconnect?
20. `AmbiguousTimeoutException` có nghĩa mutation chắc chắn thất bại không?
21. Application retry và SDK retry có thể tạo retry storm thế nào?
22. Circuit breaker giúp gì khi cluster outage kéo dài?
23. Vì sao `flatMap(...,16)` không bảo đảm tổng hệ thống chỉ có 16 operations?
24. Những metric nào xác định **recovery thực** thay vì chỉ ping UP?
25. Vì sao phải drain traffic trước khi Spring shutdown Cluster?
26. Test fault nào chứng minh startup/rolling deployment ổn định?

## 48. Tài liệu chính thức và đối chiếu phiên bản

- [Couchbase Java SDK — Managing Connections](https://docs.couchbase.com/java-sdk/current/howtos/managing-connections.html): Cluster lifecycle, seed nodes, TLS, alternate addresses, `waitUntilReady` và resource sharing.
- [Couchbase Java SDK — Hello World](https://docs.couchbase.com/java-sdk/current/hello-world/start-using-sdk.html): lazy bucket open, `bucket.waitUntilReady`.
- [Couchbase Java SDK — Client Settings](https://docs.couchbase.com/java-sdk/current/ref/client-settings.html): `kvTimeout`, `kvDurableTimeout`, `connectTimeout`, `queryTimeout` và `disconnectTimeout`.
- [Couchbase Java SDK — Health Check](https://docs.couchbase.com/java-sdk/current/howtos/health-check.html): `ping()`, `diagnostics()`, service types và trạng thái endpoint.
- [Couchbase Java SDK API — Cluster](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/Cluster.html): `waitUntilReady`, `ping`, `diagnostics`, `disconnect`.
- [Couchbase Java SDK API — Bucket](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/Bucket.html): `Bucket.waitUntilReady` và KV endpoints.
- [Couchbase Java SDK — Handling Errors](https://docs.couchbase.com/java-sdk/current/howtos/error-handling.html): `BestEffortRetryStrategy`, `RetryReasons`, timeout ambiguity và idempotency.
- [Couchbase Java SDK — Troubleshooting Cloud Connections](https://docs.couchbase.com/java-sdk/current/howtos/troubleshooting-cloud-connections.html): Capella DNS-SRV, SDK Doctor, allowlist, TLS.
- [Couchbase Java SDK — Metrics Reporting](https://docs.couchbase.com/java-sdk/current/howtos/observability-metrics.html): SDK LoggingMeter, Micrometer/OpenTelemetry.
- [Couchbase Java SDK — Slow Operations Logging](https://docs.couchbase.com/java-sdk/current/howtos/slow-operations-logging.html): threshold/orphaned tracing, operation latencies.
- [Couchbase Java SDK — Logging](https://docs.couchbase.com/java-sdk/current/howtos/collecting-information-and-logging.html): Event Bus, SLF4J và log redaction.
- [Spring Boot — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/reference/data/nosql.html): Couchbase auto-configuration, connection, `spring.couchbase.env.timeouts`, bucket.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): tên properties Couchbase hiện hành.
- [Spring Boot — Actuator Endpoints and Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): Couchbase HealthIndicator, liveness/readiness, startupProbe, add-additional-paths và external-dependency policy.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): mapping, Repository và dữ liệu KV/SQL++.
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `retryWhen` và cancellation.

**Ràng buộc phiên bản:** Các ví dụ minh họa Couchbase Java SDK **3.x** với Spring Data Couchbase và Spring Boot tương thích. Tên bean, properties, signatures của `PingOptions`, timeout mặc định, Event Bus và Kubernetes probes phải được đối chiếu dependency đã khóa. Trước triển khai thực cần biên dịch và kiểm thử trên topology/network/Server thực tế. Bài viết STEP 4 **không thay thế Content QA chuyên môn của STEP 6**.

> **Ghi nhớ:** **Bootstrap hoàn tất, sẵn sàng phục vụ và phục hồi sau lỗi là ba trạng thái khác nhau**. Chờ đúng `Bucket`/service với ngân sách hữu hạn, giữ `Cluster` do Spring quản lý, tách liveness khỏi external outages, để SDK quản lý reconnect, giới hạn retry/queue, bảo toàn idempotency của writes và đo recovery bằng SLO của người dùng — không chỉ bằng một dấu `ONLINE` trong diagnostics.
