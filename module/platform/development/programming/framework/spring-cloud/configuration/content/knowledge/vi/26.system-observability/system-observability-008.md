# Cảnh báo lỗi nạp cấu hình, sai phiên bản và cập nhật không hội tụ

Trong hệ thống Spring Cloud Config, một lần phát hành cấu hình chỉ hoàn tất khi các Config Server trả đúng revision, các Config Client nạp được cấu hình và những thành phần đang chạy thực sự sử dụng giá trị mới. Một request refresh trả HTTP 200 hoặc webhook được nhận thành công chưa đủ chứng minh toàn bộ hệ thống đã hội tụ.

Quan sát hệ thống cần phát hiện được ba nhóm vấn đề: **lỗi nạp cấu hình**, **sai phiên bản cấu hình** và **cập nhật không hội tụ giữa các instance**. Muốn xử lý nhanh, nhóm vận hành phải kết hợp log có ngữ cảnh, health/readiness, metric, kiểm tra revision và xác minh hành vi của client. Bài viết trình bày cách xây dựng các tín hiệu đó, đặt cảnh báo có thể hành động và xử lý sự cố từ Config Server đến từng Config Client.

## 1. Ba nhóm sự cố cần quan sát

| Nhóm sự cố | Biểu hiện | Tác động |
| --- | --- | --- |
| Lỗi nạp cấu hình | Config Server không đọc được backend hoặc Config Client không tải được Environment | Ứng dụng khởi động thất bại, thiếu cấu hình hoặc tiếp tục dùng giá trị cũ |
| Sai phiên bản | Node trả revision/label khác với release được mong đợi | Các instance có thể chạy hành vi khác nhau |
| Cập nhật không hội tụ | Một số client đã refresh, một số chưa nhận event hoặc bean vẫn giữ giá trị cũ | Cụm ứng dụng ở trạng thái hỗn hợp trong thời gian dài |

Các lỗi có thể liên quan nhau nhưng cần tín hiệu khác nhau. Ví dụ, Git fetch thất bại là lỗi backend; Config Server trả commit cũ là vấn đề freshness/revision; Config Server đã trả commit mới nhưng một client vẫn dùng bean cũ là vấn đề refresh hoặc runtime convergence.

Không nên gộp tất cả vào một cảnh báo chung như “Config Server unhealthy”. Cảnh báo tốt phải cho biết thành phần nào lỗi, application/profile/label nào bị ảnh hưởng, revision mong đợi là gì và bước kiểm tra tiếp theo là gì.

## 2. Sơ đồ quan sát từ nguồn đến runtime

Một luồng cấu hình thường đi qua nhiều thành phần:

~~~mermaid
flowchart LR
    G[Git / Vault / Native backend] --> S[Config Server replicas]
    S -->|Environment JSON| C[Config Client instances]
    W[Webhook / operator / Bus event] --> S
    W --> B[Message broker]
    B --> C
    C --> E[Spring Environment]
    E --> R[Beans / pools / clients]
    S --> O[Logs, metrics, health]
    C --> O
    R --> O
    O --> A[Dashboards and alerts]
~~~

Cần quan sát từng chặng:

1. Backend có thể truy cập và trả đúng version không?
2. Mỗi Config Server replica có trả cùng application/profile/label và revision không?
3. Webhook hoặc thao tác refresh có được tiếp nhận và phát sự kiện không?
4. Mỗi Config Client có nhận event và lấy lại Environment không?
5. Bean hoặc tài nguyên runtime có áp dụng giá trị mới không?
6. Tất cả instance có đạt revision đích trong thời gian hội tụ cho phép không?

Mỗi chặng nên có log, metric hoặc health signal riêng. Nhờ đó, một cảnh báo có thể dẫn tới đúng lớp cần xử lý thay vì phải restart toàn bộ hệ thống.

## 3. Ghi nhận định danh cấu hình trong mỗi lần phát hành

Để phát hiện sai phiên bản, mỗi lần phát hành nên có một định danh cấu hình không nhạy cảm, ví dụ:

~~~yaml
config:
  release-id: orders-prod-2026.11.27

orders:
  http:
    read-timeout: 8s
  retry:
    max-attempts: 3
~~~

`config.release-id` là metadata do pipeline hoặc quy trình release tạo ra. Giá trị này phải gắn với bộ cấu hình đã được review và không chứa secret. Với Git backend, manifest phát hành nên ghi thêm full commit SHA, application, profile và label.

Ví dụ manifest:

~~~yaml
release:
  id: orders-prod-2026.11.27
  application: orders-service
  profile: prod
  label: orders-prod-2026.11.27
  git-commit: 4b7f2b6d7b0e9c1a2f3d4e5f60718293a4b5c6d7
~~~

Client có thể báo release ID hiện đang dùng qua một health contributor, metric hoặc endpoint nội bộ được bảo vệ. Nguồn expected release phải đến từ deployment manifest hoặc hệ thống rollout độc lập; nếu expected ID cũng được đọc từ chính Config Server đang kiểm tra thì phép so sánh không phát hiện được server phục vụ sai revision.

Với composite repository, release manifest cần ghi version của từng nguồn: Git commit, Vault KV version, image digest hoặc snapshot ID của native filesystem. Git commit đơn lẻ không đại diện cho toàn bộ Environment nếu còn backend khác.

## 4. Quan sát lỗi nạp cấu hình ở Config Server

Config Server có thể gặp lỗi khi:

- Git remote không truy cập được, credential hết hạn hoặc TLS/host verification thất bại.
- Repository chưa clone được hoặc local clone bị lỗi.
- Vault/native backend không sẵn sàng hoặc thiếu quyền.
- Label, branch, tag hoặc search path không tồn tại.
- Một repository thành phần trong composite repository thất bại.
- Keystore hoặc thông tin xác thực backend không đọc được.

Nên ghi log tại thời điểm backend được truy cập và khi Environment được tạo. Log cần có các trường không nhạy cảm như:

- Tên Config Server instance.
- Application, profile và label được yêu cầu.
- Backend/repository type.
- Git revision hoặc backend version nếu có.
- Thời gian xử lý và kết quả.
- Correlation ID hoặc request ID.

Ví dụ log có cấu trúc:

~~~json
{
  "event": "config_environment_fetch",
  "service": "config-server",
  "instance": "config-server-2",
  "application": "orders-service",
  "profiles": ["prod"],
  "label": "orders-prod-2026.11.27",
  "backend": "git",
  "version": "4b7f2b6d7b0e9c1a2f3d4e5f60718293a4b5c6d7",
  "duration_ms": 142,
  "result": "success",
  "correlation_id": "req-7f31a"
}
~~~

Đây là schema log minh họa. Không ghi password, access token, Authorization header, plaintext secret hoặc toàn bộ Environment JSON. Nếu log lỗi có exception message chứa URL credential, cần sanitize trước khi gửi tới hệ thống log tập trung.

## 5. Health và readiness của Config Server

Spring Boot Actuator cung cấp endpoint health để theo dõi trạng thái ứng dụng và các health contributor đã được cấu hình:

~~~bash
curl https://config.internal.example/actuator/health
~~~

Health cho biết trạng thái của process và các thành phần được health indicator kiểm tra. Tuy nhiên, `UP` không tự chứng minh Config Server đang phục vụ đúng revision. Một server có thể kết nối được Git nhưng vẫn trả label hoặc commit không đúng với release mong muốn.

Nên phân biệt ba tín hiệu:

| Tín hiệu | Câu hỏi | Cách kiểm tra |
| --- | --- | --- |
| Liveness | Process còn hoạt động không? | JVM và liveness health group |
| Readiness | Node có đủ điều kiện nhận request không? | Readiness group, dependency thiết yếu và kiểm tra cấu hình đại diện |
| Revision parity | Node có phục vụ đúng revision không? | Environment endpoint và release manifest |

Nếu release train cung cấp health indicator cho Config Server hoặc repository, có thể dùng nó như một tín hiệu bổ sung. Tên component, phạm vi kiểm tra và cách bật phụ thuộc phiên bản; hãy xác minh endpoint health thực tế thay vì giả định mọi backend đều có indicator giống nhau.

Không nên thực hiện Git fetch nặng ở mỗi lần readiness probe. Có thể kiểm tra revision trong bước deployment hoặc theo chu kỳ, lưu kết quả gần nhất và để readiness đọc trạng thái đã xác nhận. Node không đạt parity có thể được đánh dấu unready hoặc rút khỏi load balancer.

## 6. Phát hiện Config Server trả sai revision

Với Git backend, Environment JSON thường chứa các trường `name`, `profiles`, `label`, `version` và `propertySources`.

Gọi trực tiếp từng Config Server replica:

~~~bash
curl --fail --silent --show-error \
  https://config-server-a.internal/orders-service/prod/orders-prod-2026.11.27 \
  | jq '{name, profiles, label, version, sources: [.propertySources[].name]}'
~~~

Lặp lại với từng node. So sánh:

- Application và profile có đúng không.
- Label có đúng label đã phát hành không.
- `version` có khớp full commit SHA trong manifest không.
- Danh sách property source có giống nhau không.
- Các key không nhạy cảm quan trọng có cùng giá trị không.

Không lưu toàn bộ response nếu Config Server trả secret đã giải mã. Chỉ trích xuất metadata an toàn hoặc dùng script kiểm tra key allowlist không nhạy cảm.

Nếu dùng Vault hoặc native backend, trường Git `version` không đủ. Cần có version ID riêng cho secret hoặc snapshot cấu hình và ghi nhận trong release manifest.

## 7. Quan sát lỗi nạp cấu hình ở Config Client

Config Client có thể không lấy được cấu hình khi khởi động hoặc khi refresh vì:

- Config Server không truy cập được hoặc DNS/TLS lỗi.
- Client gửi sai application name, profile hoặc label.
- Credential client hết hạn hoặc không được cấp quyền đọc application.
- Config Server trả HTTP lỗi hoặc backend không tạo được Environment.
- Cấu hình không hợp lệ hoặc thiếu key bắt buộc.
- Client dùng `optional:configserver:` và tiếp tục khởi động với fallback dù cấu hình từ xa đang lỗi.

Cần ghi nhận request/fetch result tại client với application, profile, label, Config Server endpoint, thời gian và kết quả. Nếu client khởi động với Config Server là nguồn bắt buộc, import không có `optional:` sẽ làm lỗi được phát hiện sớm hơn. Chỉ dùng optional khi có fallback an toàn và đã kiểm thử.

Ví dụ cấu hình import bắt buộc:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    active: prod
  config:
    import: "configserver:https://config.internal.example"
~~~

Nếu Config Server tạm thời chưa sẵn sàng, có thể cấu hình retry theo thuộc tính được hỗ trợ trong phiên bản Spring Cloud Config đang dùng. Retry xử lý lỗi tạm thời; nó không sửa sai label, credential hoặc cấu hình không hợp lệ.

## 8. Phân biệt fetch failure với refresh failure

Một lần refresh có nhiều bước: nhận sự kiện, lấy Environment, cập nhật property source, rebind hoặc invalidate bean, sau đó thành phần runtime áp dụng giá trị.

| Bước | Dấu hiệu lỗi | Tín hiệu nên ghi |
| --- | --- | --- |
| Nhận refresh event | Client không nhận Bus event hoặc request refresh | Event ID, destination, thời điểm phát/nhận |
| Fetch Environment | HTTP lỗi, timeout, sai profile/label | Fetch result, status code, duration, revision |
| Cập nhật Environment | Property source không đổi hoặc parse/binding lỗi | Số key thay đổi, lỗi binding đã sanitize |
| Refresh bean | Target không được tạo lại hoặc rebind không thành công | Bean/component type, refresh outcome |
| Áp dụng runtime | Pool/client vẫn dùng credential hoặc policy cũ | Runtime generation, connection/behavior check |

Không nên ghi giá trị của các key đã thay đổi. Có thể ghi số lượng key thay đổi, tên nhóm cấu hình không nhạy cảm và release ID.

Nếu webhook `/monitor` trả thành công, điều đó chỉ chứng minh Config Server đã xử lý request theo khả năng endpoint báo cáo. Cần kiểm tra Bus broker, client event receipt và fetch result riêng. Nếu `/actuator/refresh` trả HTTP 200, vẫn cần xác minh bean và hành vi runtime.

## 9. Metric cần theo dõi

Micrometer và hệ thống metrics như Prometheus có thể thu thập metric từ Spring Boot Actuator và các thành phần tích hợp. Các metric cụ thể có sẵn tùy dependency/version; với các sự kiện nghiệp vụ riêng của quy trình cấu hình, có thể bổ sung custom metric.

Những tín hiệu hữu ích:

| Metric/tín hiệu | Ý nghĩa | Dùng để cảnh báo |
| --- | --- | --- |
| Số lần Config Server fetch thất bại | Backend hoặc request lỗi | Tăng đột biến hoặc lỗi kéo dài |
| Thời gian fetch Environment | Độ trễ lấy cấu hình | Vượt ngưỡng SLO |
| Số lần client refresh thất bại | Client không áp dụng được cấu hình mới | Có lỗi sau một release |
| Tuổi của lần refresh thành công gần nhất | Client đã lâu chưa hội tụ | Vượt thời gian hội tụ cho phép |
| Revision mismatch | Actual release khác expected release | Bất kỳ mismatch kéo dài nào ở production |
| Bus event delivery delay | Độ trễ từ lúc phát đến lúc client nhận | Vượt thời gian phân phối dự kiến |
| Số instance theo release ID | Phân bố phiên bản cấu hình | Còn instance ở revision cũ sau rollout |
| Runtime validation failure | Bean/pool/client không dùng được policy mới | Cấu hình mới không an toàn hoặc không hợp lệ |

Không nên đưa commit SHA, user ID hoặc label thay đổi liên tục thành metric label nếu tạo cardinality lớn. Dùng metric boolean/counter theo service và environment; revision chi tiết có thể để trong log, release metadata hoặc health detail đã được bảo vệ.

Ví dụ tên custom metric:

~~~text
config_fetch_failures_total
config_refresh_failures_total
config_revision_mismatch
config_refresh_duration_seconds
config_last_success_timestamp_seconds
config_bus_delivery_delay_seconds
~~~

Đây là tên minh họa do ứng dụng định nghĩa, không phải cam kết rằng Spring Boot tự xuất sẵn tất cả các metric đó.

## 10. Ví dụ instrument custom metric

Một thành phần có thể ghi nhận lỗi refresh và trạng thái revision parity. Ví dụ sau minh họa cách dùng Micrometer; cần gọi các method tại điểm fetch/refresh/convergence thực tế của ứng dụng:

~~~java
@Component
public class ConfigurationObservability {

    private final Counter refreshFailures;
    private final AtomicLong revisionMismatch = new AtomicLong(0);
    private final AtomicLong lastSuccessEpochSeconds = new AtomicLong(0);

    public ConfigurationObservability(MeterRegistry registry) {
        this.refreshFailures = Counter.builder("config.refresh.failures")
                .description("Number of failed configuration refresh operations")
                .register(registry);

        Gauge.builder(
                "config.revision.mismatch",
                revisionMismatch,
                AtomicLong::get)
            .description("1 when the active configuration differs from expected")
            .register(registry);

        Gauge.builder(
                "config.last.success.timestamp.seconds",
                lastSuccessEpochSeconds,
                AtomicLong::get)
            .description("Unix timestamp of the last successful config application")
            .register(registry);
    }

    public void recordRefreshFailure() {
        refreshFailures.increment();
    }

    public void recordRevisionCheck(boolean matches) {
        revisionMismatch.set(matches ? 0 : 1);
    }

    public void recordSuccessfulApplication() {
        lastSuccessEpochSeconds.set(Instant.now().getEpochSecond());
        revisionMismatch.set(0);
    }
}
~~~

Các import cần có gồm `io.micrometer.core.instrument.Counter`, `Gauge`, `MeterRegistry`, `java.time.Instant` và `java.util.concurrent.atomic.AtomicLong`.

Trong triển khai thật, chỉ gọi `recordSuccessfulApplication()` sau khi Environment đã được nạp, validate và thành phần cần thiết đã áp dụng cấu hình theo chính sách của ứng dụng. Không gọi ngay khi nhận webhook hoặc Bus event. Nếu chỉ fetch thành công nhưng bean refresh thất bại, phải ghi nhận fetch success và runtime application failure riêng.

Để metric có ý nghĩa theo service, có thể thêm tag cố định như `service` và `environment` khi đăng ký. Tránh tag có giá trị tùy ý từ request hoặc tag chứa secret.

## 11. Cảnh báo revision mismatch và không hội tụ

Một số rule Prometheus minh họa:

~~~yaml
groups:
  - name: spring-cloud-config
    rules:
      - alert: ConfigRefreshFailures
        expr: increase(config_refresh_failures_total[5m]) > 0
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Config refresh đang thất bại"
          description: "Kiểm tra fetch Environment, Bus delivery và bean refresh."

      - alert: ConfigRevisionMismatch
        expr: config_revision_mismatch == 1
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Client đang dùng sai revision cấu hình"
          description: "So sánh expected release với revision thực tế của instance."

      - alert: ConfigRefreshTooOld
        expr: config_last_success_timestamp_seconds > 0 and time() - config_last_success_timestamp_seconds > 900
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Client chưa xác nhận cập nhật cấu hình gần đây"
          description: "Kiểm tra client offline, Bus event hoặc refresh pipeline."

      - alert: ConfigNeverApplied
        expr: config_last_success_timestamp_seconds == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Client chưa từng xác nhận áp dụng cấu hình"
          description: "Kiểm tra startup fetch, validation và runtime application."
~~~

Tên metric trong rule phải khớp với metric thật sau khi instrumentation được triển khai. Ngưỡng 900 giây và thời gian `for` chỉ là ví dụ; đặt theo chu kỳ phát hành, SLO hội tụ và mức độ quan trọng của service.

Không cảnh báo chỉ vì một client không refresh trong 15 phút nếu không có thay đổi cấu hình nào trong khoảng đó. Metric `last_success_timestamp` cần được hiểu cùng với thời điểm release/event gần nhất. Một cách tốt hơn là theo dõi thời gian từ lúc phát hành một revision đến khi mỗi instance xác nhận revision đích.

## 12. Đo thời gian hội tụ sau một lần phát hành

Định nghĩa một lần phát hành cấu hình có:

- `release_id` hoặc Git commit SHA đích.
- Thời điểm phát hành được chấp nhận.
- Danh sách Config Server replica và Config Client instance cần cập nhật.
- Thời hạn hội tụ mục tiêu, ví dụ 2 phút hoặc theo SLO riêng.
- Điều kiện hoàn tất: tất cả instance đủ điều kiện đã xác nhận revision và runtime validation thành công.

Có thể tính:

```text
convergence_duration =
    timestamp(last_instance_confirmed_target_revision)
    - timestamp(release_started)
```

Nếu một instance offline, cần quy định rõ nó có thuộc mẫu số hay được đánh dấu unavailable. Không loại instance offline khỏi báo cáo một cách âm thầm; nếu nó quay lại với cấu hình cũ, nó có thể tạo ra mismatch sau đó.

Một dashboard phát hành nên thể hiện:

| Tín hiệu | Mục tiêu hiển thị |
| --- | --- |
| Expected release ID | Revision đích của đợt phát hành |
| Config Server parity | Số node đúng/tổng node |
| Client convergence | Số instance đúng/tổng instance |
| Refresh failures | Số lỗi theo service và thời gian |
| Bus delivery delay | p50/p95 hoặc thời gian lớn nhất |
| Runtime validation | Thành công/thất bại theo instance |
| Offline instances | Instance chưa xác nhận hoặc không liên lạc được |

Không coi rollout hoàn tất khi chỉ có đa số instance đã cập nhật nếu service yêu cầu tất cả instance hoạt động cùng revision. Nếu cho phép rolling convergence, phải ghi rõ mức chấp nhận được và cách xử lý instance cũ.

## 13. Xác minh revision và property source ở client

Actuator `env` và `configprops` có thể giúp kiểm tra cấu hình phía client, tùy phiên bản và chính sách expose:

~~~bash
curl https://orders-1.internal/actuator/env/config.release-id
curl https://orders-1.internal/actuator/configprops
~~~

Dùng `env` để xem property source và nguồn cung cấp release ID; dùng `configprops` để kiểm tra bean đã binding. Chỉ expose endpoint trong mạng quản trị, bật authentication/authorization và giữ sanitization. Không tắt sanitization để xem password hoặc token.

Một health contributor riêng có thể so sánh expected release ID do deployment cung cấp với actual release ID trong Environment. Ví dụ:

~~~java
@Component
public class ConfigConvergenceHealthIndicator implements HealthIndicator {

    private final Environment environment;
    private final String expectedReleaseId;

    public ConfigConvergenceHealthIndicator(
            Environment environment,
            @Value("${CONFIG_EXPECTED_RELEASE_ID:}") String expectedReleaseId) {
        this.environment = environment;
        this.expectedReleaseId = expectedReleaseId;
    }

    @Override
    public Health health() {
        String actual = environment.getProperty(
                "config.release-id", "unknown");

        if (expectedReleaseId.isBlank()) {
            return Health.unknown()
                    .withDetail("reason", "expected release is not configured")
                    .build();
        }

        if (!expectedReleaseId.equals(actual)) {
            return Health.down()
                    .withDetail("expectedRelease", expectedReleaseId)
                    .withDetail("actualRelease", actual)
                    .build();
        }

        return Health.up()
                .withDetail("releaseId", actual)
                .build();
    }
}
~~~

Các import chính gồm `Health`, `HealthIndicator`, `Environment`, `Value` và `Component`. Ví dụ này giả định expected release ID được inject từ deployment environment độc lập với Config Server. Nếu giá trị expected lấy từ cùng remote property source đang kiểm tra, phép so sánh mất ý nghĩa.

Có thể thêm health contributor vào readiness group nếu chính sách yêu cầu node chỉ nhận traffic khi đúng revision. Không nhất thiết đưa mismatch cấu hình vào liveness: restart process liên tục không sửa được Git label, quyền truy cập hay sự cố Bus. Hãy chọn readiness hoặc cảnh báo tùy mức độ ảnh hưởng và cơ chế phục hồi.

## 14. Quan sát Spring Cloud Bus và webhook

Với refresh được kích hoạt qua webhook hoặc Spring Cloud Bus, cần theo dõi cả đường đi của event:

1. Git provider gửi webhook và nhận response.
2. Config Server nhận payload, xác định application bị ảnh hưởng.
3. Config Server publish event lên broker.
4. Broker chuyển event đến các client.
5. Client nhận event và fetch Environment.
6. Client áp dụng cấu hình và xác nhận release ID.

Các trường nên ghi nhận gồm delivery ID, commit SHA, event type, destination, thời điểm phát, thời điểm nhận và kết quả xử lý. Không log webhook secret hoặc toàn bộ payload nếu payload có thể chứa dữ liệu nhạy cảm.

Metric broker như queue depth, consumer connection, publish/ack rate và consumer lag giúp phát hiện event bị chậm hoặc không được xử lý. Tên metric phụ thuộc RabbitMQ/Kafka và exporter được triển khai. Một broker health check `UP` vẫn chưa chứng minh mọi client đã nhận cùng một refresh event.

Nếu dùng webhook `/monitor`, một response thành công chỉ xác nhận endpoint xử lý request ở phía server. Cần đối chiếu event publish và client receipt. Nếu webhook bị retry hoặc gửi trùng, có thể có nhiều refresh; hãy correlation theo delivery ID/commit SHA để tránh hiểu nhầm số lần event thành số lần release.

## 15. Bảng chẩn đoán theo tín hiệu

| Quan sát | Lớp có khả năng lỗi | Hành động đầu tiên |
| --- | --- | --- |
| Config Server health DOWN | Process hoặc dependency được health indicator kiểm tra | Xem health component và log backend |
| Health UP nhưng Environment endpoint trả lỗi | Repository, label, auth hoặc application/profile | Gọi endpoint trực tiếp và kiểm tra backend |
| Các server replica trả `version` khác nhau | Local clone, fetch timing hoặc label khác | So sánh từng node và đưa node lệch ra khỏi load balancer |
| Webhook thành công nhưng không có refresh event | Monitor mapping hoặc Bus publish | Kiểm tra payload, application mapping và broker log |
| Event publish nhưng client không nhận | Broker, subscription hoặc network | Kiểm tra consumer connection, queue/group và event destination |
| Client nhận event nhưng fetch thất bại | Client-to-server auth/network hoặc Config Server backend | Kiểm tra HTTP status, profile, label và retry |
| Environment mới nhưng bean cũ | Rebind/RefreshScope hoặc singleton giữ state | Kiểm tra bean lifecycle và runtime generation |
| Bean mới nhưng hành vi vẫn cũ | Pool/cache/client hoặc state ngoài bean | Kiểm tra tài nguyên runtime và connection replacement |
| Một số instance chưa hội tụ | Instance offline, Bus event miss hoặc rollout chưa xong | Kiểm tra từng instance và thực hiện targeted refresh/restart |
| Revision đúng nhưng giá trị khác | Local override hoặc backend composite khác version | Kiểm tra property source precedence và version từng backend |

Chẩn đoán theo thứ tự nguồn → server → event → client Environment → bean → runtime. Tránh restart tất cả instance trước khi biết lỗi nằm ở đâu; restart có thể làm mất bằng chứng và không sửa được cấu hình sai.

## 16. Playbook khi phát hiện lỗi nạp cấu hình

Khi Config Server hoặc client không nạp được cấu hình:

1. Ghi nhận thời điểm, service, instance, application/profile/label và correlation ID.
2. Xác định lỗi xảy ra ở startup hay refresh runtime.
3. Gọi health endpoint và Environment endpoint của Config Server.
4. Kiểm tra backend: Git URI/credential/TLS, Vault policy/availability hoặc native path/permission.
5. Kiểm tra client-to-server network, DNS, TLS và authentication.
6. Xem retry có đang chạy hay đã hết số lần thử.
7. Nếu cấu hình là bắt buộc, giữ fail-fast hoặc rút instance thiếu cấu hình khỏi traffic.
8. Sau khi backend phục hồi, xác nhận Config Server trả đúng revision rồi mới refresh client.
9. Kiểm tra bean binding và hành vi thực tế.
10. Ghi lại thời gian phục hồi và nguyên nhân gốc.

Nếu client dùng `optional:configserver:`, cần kiểm tra fallback có thực sự an toàn. Một instance khởi động thành công với cấu hình mặc định cũ có thể nguy hiểm hơn một instance fail-fast và không nhận traffic.

## 17. Playbook khi revision sai hoặc cập nhật không hội tụ

Khi expected release đã thay đổi nhưng hệ thống còn nhiều revision:

1. Dừng phát hành cấu hình tiếp theo trong phạm vi ảnh hưởng.
2. Xác nhận expected release ID, label và full commit SHA.
3. Gọi trực tiếp từng Config Server replica; so sánh `version` và property source.
4. Rút node Config Server lệch revision khỏi load balancer.
5. Kiểm tra webhook/Bus event và thời điểm client nhận event.
6. Kiểm tra từng Config Client: actual release ID, Environment, property source và refresh outcome.
7. Xác định instance chưa nhận event, fetch lỗi hay bean/runtime không áp dụng.
8. Gửi targeted refresh hoặc rolling restart cho nhóm instance cần xử lý.
9. Xác minh runtime behavior và số instance còn lệch.
10. Chỉ đóng incident khi đạt tiêu chí hội tụ đã định nghĩa.

Nếu revision mới gây lỗi, dùng quy trình rollback đã được phê duyệt. Khôi phục Git không tự khôi phục Vault KV version hoặc native filesystem snapshot; mọi backend tham gia Environment phải được kiểm tra riêng.

## 18. Thiết kế dashboard và alert có thể hành động

Một dashboard cho nhóm vận hành nên chia thành bốn vùng:

- **Backend/Config Server**: health, fetch latency, fetch failures, revision theo replica.
- **Distribution**: webhook delivery, Bus publish/consume, queue depth và event delay.
- **Config Client**: refresh attempts/success/failure, last successful fetch, actual release ID theo instance.
- **Runtime**: bean generation, pool/client health, validation errors và hành vi nghiệp vụ liên quan.

Mỗi alert cần có:

- Tên service và environment.
- Instance hoặc replica bị ảnh hưởng.
- Expected và actual release ID nếu liên quan version.
- Thời điểm bắt đầu và thời gian kéo dài.
- Dashboard/log query hoặc trace liên quan.
- Bước kiểm tra đầu tiên và điều kiện escalation.

Tránh alert chỉ vì một lần retry thất bại nếu lần retry sau thành công trong SLO. Cảnh báo theo tỷ lệ lỗi, thời gian kéo dài hoặc trạng thái chưa hội tụ thường hữu ích hơn cảnh báo từng request đơn lẻ. Tuy nhiên, với mismatch revision production đã kéo dài quá thời gian hội tụ cho phép, cần cảnh báo rõ ràng vì các instance có thể đang xử lý request theo chính sách khác nhau.

## 19. Kiểm thử khả năng quan sát

Trước khi đưa dashboard và alert vào production, kiểm tra chúng bằng tình huống có kiểm soát:

| Tình huống thử | Kết quả quan sát mong đợi |
| --- | --- |
| Tạm thời làm Git backend không truy cập được | Fetch failure được ghi nhận, alert theo ngưỡng, log không lộ token |
| Yêu cầu label không tồn tại | Environment fetch thất bại rõ ràng, application/profile/label được ghi |
| Một Config Server replica dùng revision cũ | Revision mismatch xuất hiện và node không được readiness |
| Ngắt kết nối broker của một client | Event delivery/convergence delay tăng, client được đánh dấu chưa hội tụ |
| Bean không hỗ trợ refresh | Environment đổi nhưng runtime check phát hiện generation cũ |
| Cấu hình mới không hợp lệ | Validation failure được ghi nhận, snapshot/policy cũ được giữ nếu thiết kế yêu cầu |
| Instance offline trong lúc phát hành | Dashboard hiển thị instance chưa xác nhận thay vì tính là thành công |
| Secret có trong response/log test | Kiểm tra sanitization và quy trình ngăn lưu plaintext |

Dùng môi trường staging hoặc fault injection có kiểm soát. Không cố ý làm hỏng backend hoặc thu hồi credential trên production chỉ để thử alert. Sau mỗi bài thử, xác nhận cảnh báo tự đóng khi trạng thái đã phục hồi và có audit trail.

## 20. Bảo mật dữ liệu quan sát

Quan sát tốt không có nghĩa là ghi toàn bộ cấu hình. Environment JSON, Actuator `env`, `configprops`, webhook payload và HTTP debug log có thể chứa hoặc làm lộ thông tin nhạy cảm.

- Không log plaintext secret, password, token, lease ID hoặc private key.
- Không lưu response Environment đầy đủ trong log tập trung.
- Sanitize Actuator và chỉ expose endpoint cần thiết trong mạng quản trị.
- Dùng authentication/authorization cho health detail, refresh và endpoint chẩn đoán.
- Không dùng secret hoặc user-specific data làm metric label.
- Giới hạn retention và quyền truy cập log/trace.
- Dùng release ID, commit SHA và generation không nhạy cảm để đối chiếu.
- Ghi audit thao tác refresh, rollback và thay đổi expected revision.

Nếu cần kiểm tra secret đã được áp dụng, xác minh bằng một thao tác kết nối hoặc health check có kiểm soát; không trả secret ra endpoint chẩn đoán.

## 21. Nguyên tắc vận hành

- Gắn release ID và revision có thể truy vết vào mỗi lần phát hành cấu hình.
- Theo dõi lỗi fetch ở Config Server và Config Client riêng biệt.
- Phân biệt liveness, readiness và revision parity.
- Kiểm tra `version`, label và property source trên từng Config Server replica.
- Theo dõi webhook, Bus event, client receipt và runtime application theo từng chặng.
- Đo thời gian hội tụ từ lúc phát hành đến khi từng instance xác nhận revision đích.
- Dùng custom metrics cho các sự kiện cấu hình mà framework không tự cung cấp.
- Không coi HTTP 200 từ refresh là bằng chứng runtime đã cập nhật.
- Định nghĩa alert theo SLO và cung cấp runbook cụ thể.
- Bảo vệ log, metric, Actuator và dữ liệu secret trong mọi bước chẩn đoán.

Cảnh báo cấu hình chỉ hữu ích khi nối được lỗi với revision và instance cụ thể. Theo dõi backend, Config Server, Bus, Environment, bean và hành vi runtime giúp nhóm xác định cập nhật đang dừng ở đâu. Khi expected release độc lập, revision được kiểm tra trên từng node và mọi client phải xác nhận trạng thái áp dụng, nhóm vận hành có thể phát hiện sớm cấu hình sai hoặc chưa hội tụ và khôi phục có kiểm soát.

