# Database health

Một ứng dụng Spring Boot có thể còn chạy bình thường dù database mất kết nối, hết connection hoặc từ chối xác thực. Nếu load balancer vẫn gửi traffic vào instance không thể phục vụ request cần database, người dùng sẽ nhận lỗi dù process Java vẫn sống. Database health indicator giúp Actuator kiểm tra khả năng truy cập database và đưa trạng thái đó vào health response; readiness probe có thể dùng thông tin này để quyết định instance có nên nhận traffic hay không.

Bài **Database health** thuộc chương **Health và readiness** của module **SPRING_BOOT_OBSERVABILITY**. Module học cách thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; hiểu context propagation, tag/cardinality, exporter, sampling và liên kết các tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trong môi trường thực.

> **Điểm cốt lõi:** Database health phản ánh khả năng kiểm tra database tại thời điểm probe. Nó không thay thế metrics/traces để đo latency hoặc điều tra query. Phân biệt liveness (process có cần restart không) với readiness (instance có nên nhận traffic không). Database dependency thường ảnh hưởng readiness của service phụ thuộc nó; đưa database vào liveness thiếu cân nhắc có thể khiến outage gây restart loop trên toàn fleet.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích vai trò của database health indicator trong Spring Boot Actuator.
2. Hiểu DataSourceHealthIndicator và cách health contributor kiểm tra database.
3. Đọc trạng thái UP, DOWN, OUT_OF_SERVICE và UNKNOWN.
4. Phân biệt liveness, readiness và overall application health.
5. Quyết định khi nào database nên ảnh hưởng readiness.
6. Cấu hình health groups và probe endpoints.
7. Hiểu tác động của timeout, connection pool và database outage lên health checks.
8. Bảo vệ health details để không lộ JDBC URL, database version hoặc exception nhạy cảm.
9. Kiểm thử database health khi DB sẵn sàng, unreachable hoặc query chậm.
10. Kết hợp health với metrics, logs và traces trong điều tra sự cố.

## 2. Database health indicator là gì?

Spring Boot Actuator cung cấp health endpoint tổng hợp các HealthContributor. Với JDBC DataSource, auto-configuration có thể đăng ký database health indicator khi có DataSource và health auto-configuration phù hợp.

Database health indicator kiểm tra khả năng truy cập database thông qua DataSource/connection. Nó thường lấy connection và thực hiện validation/query phù hợp với implementation. Nếu check thành công, component báo UP; nếu thất bại, component có thể báo DOWN cùng thông tin lỗi tùy cấu hình và quyền hiển thị details.

~~~http
GET /actuator/health
~~~

Response minh họa khi database hoạt động:

~~~json
{
  "status": "UP",
  "components": {
    "db": {"status": "UP"},
    "diskSpace": {"status": "UP"}
  }
}
~~~

Response khi database check thất bại có thể là:

~~~json
{
  "status": "DOWN",
  "components": {
    "db": {"status": "DOWN"}
  }
}
~~~

Đây là ví dụ rút gọn; response thực tế phụ thuộc health details visibility, health groups và Spring Boot version.

## 3. DataSourceHealthIndicator kiểm tra điều gì?

DataSourceHealthIndicator là health contributor cho JDBC DataSource. Nó xác minh có thể tương tác với database qua connection mà ứng dụng sử dụng.

Tùy database/driver và Spring Boot version, indicator có thể:
- Lấy connection từ DataSource.
- Sử dụng validation query hoặc JDBC Connection validation.
- Đưa database product/version vào details khi được cấu hình và được phép hiển thị.
- Trả DOWN khi không lấy/validate được connection hoặc query kiểm tra thất bại.

Không xem health check thành phép đo toàn diện database. Một query đơn giản thành công không chứng minh mọi query nghiệp vụ đều nhanh, index tốt, transaction khỏe hay replica đã đồng bộ.

### 3.1 Validation query

Thông thường auto-configuration tự chọn cách validation phù hợp với driver. Nếu database/driver cần query riêng, có thể cấu hình bean/custom HealthIndicator hoặc datasource validation mechanism phù hợp. Không đặt query nặng hoặc truy vấn bảng nghiệp vụ lớn làm health probe.

~~~yaml
management:
  health:
    db:
      enabled: true
~~~

Property trên cho phép bật/tắt database health contributor trong các cấu hình Spring Boot hỗ trợ. Kiểm tra property reference đúng version khi thay đổi behavior.

### 3.2 Connection pool ảnh hưởng kết quả

Health check dùng DataSource của ứng dụng; nếu pool hết connection, probe có thể thất bại dù database server vẫn sống. Điều đó vẫn là tín hiệu quan trọng: instance hiện không lấy được connection để phục vụ traffic.

Khi điều tra, phân biệt database unreachable, credentials/permission invalid, pool exhausted, connection validation timeout và database quá tải.

## 4. Trạng thái health

Spring Boot Health status thường dùng các giá trị:

| Status | Ý nghĩa |
|---|---|
| UP | Component được kiểm tra hoạt động |
| DOWN | Component gặp lỗi hoặc không đáp ứng check |
| OUT_OF_SERVICE | Component đang được cố ý đưa khỏi phục vụ |
| UNKNOWN | Không thể xác định trạng thái |

HealthAggregator/StatusAggregator tổng hợp component statuses thành trạng thái cấp cao. Mặc định, DOWN và OUT_OF_SERVICE thường có mức ưu tiên khiến overall status không UP; có thể tùy chỉnh status order.

Database contributor DOWN có thể làm overall /actuator/health thành DOWN. Tuy nhiên readiness group có thể được cấu hình riêng; không phải mọi contributor tự động có mặt trong mọi group.

## 5. Liveness và readiness khác nhau

| Probe | Câu hỏi | Khi fail, platform thường làm gì? |
|---|---|---|
| Liveness | Process có còn tiến triển và không bị kẹt đến mức cần restart? | Restart container/process |
| Readiness | Instance có sẵn sàng nhận traffic mới? | Tạm ngừng route traffic tới instance |
| Overall health | Các health contributors của ứng dụng đang ở trạng thái nào? | Dùng cho chẩn đoán/monitoring |

Database outage thường không có nghĩa JVM cần restart. Nếu database nằm trong liveness, tất cả pods có thể fail liveness đồng thời và restart liên tục, tạo thêm áp lực lên DB khi nó phục hồi.

Với readiness, câu trả lời phụ thuộc kiến trúc:
- Nếu mọi request quan trọng đều cần DB, database DOWN có thể làm instance not ready.
- Nếu service có thể phục vụ một phần chức năng bằng cache/fallback, có thể giữ readiness UP và trả lỗi có kiểm soát cho chức năng phụ thuộc DB.
- Nếu chỉ một route/feature phụ thuộc database phụ, không nhất thiết rút toàn bộ service khỏi load balancer.

Đặt policy theo khả năng phục vụ thực tế, không chỉ theo trạng thái dependency.

## 6. Spring Boot probe health groups

Spring Boot có thể expose liveness và readiness health groups. Trong Kubernetes, probe paths thường là:
- /actuator/health/liveness
- /actuator/health/readiness

Bật probes:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Spring Boot tạo health groups tương ứng trong môi trường hỗ trợ. Có thể thêm database vào readiness group một cách tường minh:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db
~~~

Ví dụ này đưa application readiness state và database health contributor vào readiness group. Kiểm tra group members hiện hữu và tên contributor thực tế; nếu dùng nhiều DataSources, có thể có contributor names khác nhau.

Không thêm db vào liveness group theo thói quen. Liveness nên tập trung vào trạng thái nội tại của process/application, không phụ thuộc service bên ngoài có thể outage độc lập.

## 7. Khi nào database nên ảnh hưởng readiness?

Dùng các câu hỏi theo business capability:

1. Instance có thể nhận request và trả kết quả đúng nếu DB unavailable không?
2. Có cache/fallback/read-only mode cho một phần request không?
3. Có endpoint nào không cần DB nhưng vẫn nên phục vụ?
4. DB là dependency bắt buộc cho toàn bộ traffic hay chỉ một feature?
5. Khi DB outage, rút instance khỏi load balancer có giúp giảm lỗi hay khiến toàn fleet không còn instance?
6. Khi DB phục hồi, readiness có hồi phục tự động không?

Ví dụ:
- Order Service cần DB để tạo order: có thể đưa DB vào readiness.
- Catalog Service có cache đầy đủ và chấp nhận stale data: có thể giữ readiness theo policy riêng.
- Notification Service nhận message và lưu vào durable queue khác: database reporting phụ không nhất thiết quyết định readiness.

Readiness là quyết định routing; nó không sửa lỗi dependency. Nếu mọi replica cùng phụ thuộc một DB đang DOWN, tất cả có thể trở thành not-ready. Điều đó có thể đúng về correctness nhưng cần tính vào incident strategy.

## 8. Health details và bảo mật

Health details có thể tiết lộ database product/version, JDBC URL hoặc host/port nếu custom indicator thêm, exception class/message, component names và dependency topology, pool state hoặc internal infrastructure information.

Cấu hình hiển thị details cho người dùng được xác thực:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      roles: ACTUATOR
~~~

Không bật show-details=always trên endpoint công khai. Bảo vệ management endpoints bằng Spring Security, network policies và management port phù hợp. Không đưa credentials hoặc raw exception message vào custom Health details.

### 8.1 Custom health details an toàn

Nếu cần details, chỉ trả dữ liệu hữu ích và đã chuẩn hóa, ví dụ dependency alias primary-db, check connection-validation, error.type connection_timeout và timestamp phù hợp.

Tránh raw JDBC URL, username, password, SQL, query parameters và stack trace. Logs/traces có kiểm soát quyền truy cập là nơi phù hợp hơn cho chẩn đoán chi tiết.

## 9. Timeout và tần suất health check

Health check cũng tạo tải lên database. Nếu orchestrator gọi readiness mỗi vài giây trên hàng trăm instances, mỗi probe có thể lấy connection và chạy validation. Khi DB quá tải, health probes dồn dập có thể làm tình hình nặng hơn.

Cân nhắc:
- Connection acquisition/validation timeout ngắn và có giới hạn.
- Probe interval phù hợp, tránh quá dày.
- Failure threshold và success threshold để tránh flapping.
- Không chạy query nghiệp vụ nặng.
- Không để probe chờ vô hạn.
- Đảm bảo probe không giữ connection lâu.
- Theo dõi health check latency và failure rate.

Nếu health check timeout do pool exhausted, đó là tín hiệu instance không lấy được connection. Không tăng timeout vô hạn để làm probe xanh trong lúc ứng dụng thực tế vẫn không phục vụ được.

## 10. Multiple DataSources và database health

Ứng dụng có thể có nhiều DataSources: primary, reporting, audit hoặc tenant-specific. Health contributor mặc định có thể được tạo cho từng datasource theo naming/auto-configuration. Kiểm tra component names trong /actuator/health thay vì giả định chỉ có một db.

Chính sách readiness cần trả lời:
- Primary DB là bắt buộc, reporting DB là optional?
- Audit DB unavailable có chặn mọi request không?
- Có thể degrade một feature mà vẫn phục vụ phần còn lại không?
- Tenant database health có thể được kiểm tra tổng hợp mà không tạo quá nhiều probes không?

Không tạo health check cho mọi tenant/database mỗi lần probe nếu số lượng lớn. Việc này có thể tạo connection storm và làm endpoint chậm. Dùng aggregate strategy, sampling hoặc dependency status từ hệ thống quản lý phù hợp.

## 11. Custom HealthIndicator

Khi cần logic khác với default DataSource check, có thể viết HealthIndicator riêng. Ví dụ minh họa dùng dependency client đã được cấu hình timeout:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("primaryDatabase")
class PrimaryDatabaseHealthIndicator implements HealthIndicator {

    private final DatabaseProbe probe;

    PrimaryDatabaseHealthIndicator(DatabaseProbe probe) {
        this.probe = probe;
    }

    @Override
    public Health health() {
        try {
            probe.checkConnection();
            return Health.up()
                    .withDetail("dependency", "primary-db")
                    .build();
        } catch (RuntimeException ex) {
            return Health.down()
                    .withDetail("dependency", "primary-db")
                    .withDetail("error.type", "connection_failure")
                    .build();
        }
    }
}
~~~

DatabaseProbe là abstraction minh họa. Trong code thực tế, dùng API kiểm tra connection/validation có timeout, không swallow error để trả UP. Custom contributor có thể thay đổi tên component; tránh vô tình tạo hai check cùng kết nối DB nếu default indicator vẫn bật.

### 11.1 Không trả DOWN vì mọi lỗi nghiệp vụ

HealthIndicator kiểm tra khả năng phục vụ dependency, không phải chạy thử một business transaction. Unique constraint violation hoặc request validation không phải bằng chứng database unhealthy. Chỉ đưa vào health result các lỗi phản ánh availability/capability của dependency.

## 12. Kết hợp database health với metrics, logs và traces

Health cho biết trạng thái tại thời điểm probe. Metrics cho biết xu hướng và mức độ. Traces/logs cho biết nguyên nhân từng lần gọi.

| Signal | Câu hỏi |
|---|---|
| Health | DB check hiện tại UP hay DOWN? |
| Metrics | Connection errors, pool pending, query latency có tăng không? |
| Logs | Exception class/SQLState và thời điểm lỗi là gì? |
| Traces | Request nào chờ DB, query span kéo dài bao lâu? |

Khi readiness DOWN:
1. Kiểm tra HikariCP active/idle/pending.
2. Xem database connection error/timeout counters.
3. Mở logs theo timestamp để xem SQLState class/exception type.
4. Tìm traces có DB spans chậm hoặc lỗi.
5. Xác định DB outage, pool exhaustion hay permission/credential issue.

Không dùng health endpoint làm latency dashboard; probe thường chỉ phản ánh check nhỏ, không phải workload query thật.

## 13. Kiểm thử database health

| Scenario | Kết quả mong đợi |
|---|---|
| Database reachable, validation thành công | db UP |
| Database server dừng hoặc network bị chặn | db DOWN |
| Credentials sai | db DOWN và lỗi được phân loại an toàn |
| Connection pool exhausted | Check có thể DOWN/timeout theo pool behavior |
| Validation query chậm | Check timeout/fail theo policy |
| Primary DB UP, reporting DB DOWN | Component statuses riêng và overall/group theo policy |
| DB DOWN nhưng service có fallback | Readiness theo business capability đã định nghĩa |
| Liveness probe khi DB DOWN | Vẫn UP nếu process còn khỏe và policy không phụ thuộc DB |

### 13.1 Integration test

Có thể dùng Testcontainers để chạy database thật cho integration tests. Test nên:
- Khởi tạo application context với DataSource.
- Gọi HealthContributor/Actuator health endpoint.
- Xác nhận db component UP.
- Dừng hoặc chặn database và xác nhận DOWN.
- Kiểm tra health group readiness/liveness theo cấu hình.
- Xác nhận details không chứa JDBC credentials hoặc raw exception message.

Nếu test dừng container, dùng lifecycle rõ ràng và tránh test phụ thuộc timing quá sát.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| /actuator/health trả DOWN | Database check thất bại hoặc component khác DOWN | Đọc component status và details được phép |
| db DOWN nhưng DB server vẫn UP | Pool exhausted, credentials, validation hoặc network path | Kiểm tra pool metrics và connection test từ app |
| Readiness DOWN làm toàn bộ pods ngừng nhận traffic | DB được include trong readiness của mọi replica | Xác minh policy và khả năng degrade |
| Liveness DOWN khi DB outage | Dependency ngoài process bị gắn vào liveness | Tách DB khỏi liveness group |
| Health endpoint chậm | Probe query/connection acquisition chờ lâu | Đặt timeout và dùng validation nhẹ |
| Health flapping | Probe interval/threshold quá nhạy hoặc DB chập chờn | Điều chỉnh thresholds và xem latency/error rate |
| Details không hiện | show-details policy hoặc authorization | Dùng role được phép, không bật public details |
| Nhiều db components | Nhiều DataSources | Xác định contributor nào critical |
| Probe tạo connection storm | Nhiều instances/tenant checks quá dày | Giảm tần suất, aggregate và giới hạn concurrency |
| Health UP nhưng query nghiệp vụ lỗi | Probe chỉ kiểm tra connection đơn giản | Kết hợp query metrics, traces và application-level SLO |

## 15. Playbook: Database DOWN trong readiness

**Tình huống:** Kubernetes readiness probe bắt đầu fail trên nhiều Order Service pods.

1. Kiểm tra /actuator/health/readiness và component db status.
2. Xác nhận database có outage thật hay ứng dụng không lấy được connection từ pool.
3. Xem pool active/idle/pending, connection timeout và query latency metrics.
4. Kiểm tra logs theo SQLState/exception type đã chuẩn hóa.
5. Mở traces gần thời điểm bắt đầu fail để xác định connection, validation hoặc query path.
6. Kiểm tra DB contributor có được include trong readiness group có chủ đích không.
7. Đánh giá service có thể phục vụ request không cần DB hay phải ngừng nhận toàn bộ traffic.
8. Tránh restart toàn bộ pods nếu liveness process vẫn khỏe và DB là dependency bên ngoài.
9. Khôi phục database/pool/network/credentials theo nguyên nhân.
10. Xác nhận readiness trở lại UP, probe không flapping và request error rate giảm.

Khi DB phục hồi, không scale toàn bộ consumers/pods đồng thời nếu điều đó tạo connection storm. Dùng recovery có kiểm soát và theo dõi pool saturation.

## 16. Bài tập tự kiểm tra

**Bài 1 — HealthIndicator.** DataSourceHealthIndicator kiểm tra điều gì? Vì sao UP không chứng minh query nghiệp vụ nhanh?

**Bài 2 — Liveness vs readiness.** Database outage có nên làm liveness fail không? Giải thích hậu quả nếu mọi pod restart cùng lúc.

**Bài 3 — Readiness policy.** Một service có cache đầy đủ cho GET nhưng cần DB cho POST. Bạn sẽ quyết định readiness ra sao?

**Bài 4 — Pool exhaustion.** Database server vẫn UP nhưng health db DOWN. Vì sao pool có thể là nguyên nhân?

**Bài 5 — Security.** Vì sao không nên đặt show-details=always trên management endpoint công khai? Nêu details có thể nhạy cảm.

**Bài 6 — Multiple DataSources.** Primary DB UP nhưng reporting DB DOWN. Làm thế nào quyết định component nào ảnh hưởng readiness?

**Bài 7 — Probe load.** Vì sao health checks quá dày có thể làm database outage nặng hơn?

**Bài 8 — Observability signals.** Khi readiness DOWN, hãy nêu metrics, logs và traces cần xem để phân biệt DB outage với pool exhaustion.

### Gợi ý trả lời

1. Kiểm tra khả năng lấy/validate connection. Nó không đo toàn bộ query plans, locks hoặc workload latency.
2. Thường không; liveness fail có thể tạo restart loop và tăng tải lúc DB phục hồi.
3. Định nghĩa capability: nếu instance vẫn phục vụ đúng GET bằng cache thì có thể giữ readiness theo policy; POST trả lỗi có kiểm soát hoặc route riêng.
4. Pool không còn connection rảnh, connection bị giữ lâu/leak hoặc max pool quá nhỏ; app không lấy được connection dù server DB sống.
5. Có thể lộ host/JDBC URL, version, exception message và topology. Dùng auth/network restrictions và show-details=when-authorized.
6. Chỉ DB cần cho traffic chính nên ảnh hưởng readiness; reporting DB có thể optional nếu feature có thể degrade.
7. Mỗi probe có thể mở connection/query; nhiều replicas probe đồng thời tạo thêm load lên DB.
8. Pool active/idle/pending, connection errors/timeouts, SQLState logs và DB client spans/latency.

## 17. Tài liệu tham khảo chính thức

- [Spring Boot — Actuator Health](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health): health endpoint, contributors và status aggregation.
- [Spring Boot — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): liveness/readiness groups và probe behavior.
- [Spring Boot — Health Groups](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health.groups): cấu hình group members và status.
- [Spring Boot — Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html): LivenessState, ReadinessState và availability lifecycle.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): datasource/pool metrics và Micrometer integration.
- [Spring Security — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/web/spring-security.html): authentication/authorization cho management endpoints.
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/): probe semantics và restart/routing behavior.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP): pool sizing, connection acquisition và timeout configuration.

**Ghi nhớ:** Database health indicator kiểm tra khả năng truy cập database qua DataSource tại thời điểm probe. Readiness có thể phụ thuộc DB nếu instance không thể phục vụ đúng khi DB unavailable; liveness thường nên phản ánh sức khỏe nội tại của process để tránh restart loop. Bảo vệ health details, đặt timeout/tần suất probe hợp lý và kết hợp health với pool metrics, logs và DB traces để tìm đúng nguyên nhân.

