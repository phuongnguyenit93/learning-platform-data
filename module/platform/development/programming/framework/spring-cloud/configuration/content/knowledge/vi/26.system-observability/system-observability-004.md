# Quan sát thời gian fetch Git, truy cập backend và retry

Spring Cloud Config nằm trên đường khởi động và vận hành của nhiều ứng dụng. Khi một Config Client yêu cầu cấu hình, request đi qua HTTP tới Config Server, sau đó Config Server gọi `EnvironmentRepository` để lấy dữ liệu từ Git hoặc backend đã cấu hình. Nếu backend chậm, lỗi xác thực, không truy cập được hoặc phải fetch lại repository, thời gian phản hồi của Config Server và thời gian khởi động của client đều có thể tăng.

Để điều tra đúng nguyên nhân, cần đo từng chặng: request HTTP, xử lý `EnvironmentRepository`, truy cập backend, Git clone/fetch/checkout và các lần retry. Một HTTP 200 chưa chắc có nghĩa cấu hình vừa được lấy từ commit mới nhất; Config Server có thể đang phục vụ bản working copy cục bộ đã cache khi Git remote tạm thời không khả dụng.

Bài học này hướng dẫn cách dùng Micrometer Observation, metrics, traces, health indicator và log để quan sát luồng đó; cách hiểu `refreshRate`, `clone-on-start`, timeout và retry; đồng thời xây dashboard và cảnh báo giúp phát hiện backend chậm hoặc cấu hình bị cũ.

Sau bài học, bạn có thể:

- Mô tả đường đi của request từ Config Client qua Config Server đến Git/backend.
- Đo thời gian xử lý `EnvironmentRepository` bằng metric và span có sẵn.
- Phân biệt thời gian HTTP, thời gian đọc backend và thời gian fetch Git.
- Hiểu tác động của lazy clone, local working copy và `refresh-rate`.
- Theo dõi health của repository và revision thực tế đang được phục vụ.
- Cấu hình timeout và retry phù hợp cho Config Client.
- Phân biệt retry của client với việc fetch lại Git ở server.
- Xây dashboard, cảnh báo và quy trình chẩn đoán có thể lặp lại.

## 1. Đường đi của một lần lấy cấu hình

Với Git backend, Config Server không đọc trực tiếp remote Git cho mọi thao tác file. Server quản lý một local working copy làm cache. Khi có request, server xác định application, profile và label, kiểm tra repository local, có thể fetch remote theo chính sách refresh, sau đó đọc các file cấu hình và trả `Environment` cho client.

~~~mermaid
sequenceDiagram
    participant Client as Config Client
    participant HTTP as Config Server HTTP
    participant Repo as EnvironmentRepository
    participant Git as Git remote
    participant Local as Local working copy

    Client->>HTTP: GET /{application}/{profile}/{label}
    HTTP->>Repo: findOne(application, profile, label)
    Repo->>Local: Kiểm tra clone và label
    alt Cần fetch theo refreshRate
        Repo->>Git: fetch refs/objects
        Git-->>Repo: Kết quả fetch
        Repo->>Local: Cập nhật working copy
    else Chưa đến thời điểm fetch
        Note over Repo,Local: Dùng local working copy hiện tại
    end
    Repo->>Local: Đọc property sources
    Local-->>Repo: Các file cấu hình
    Repo-->>HTTP: Environment + version
    HTTP-->>Client: HTTP response
~~~

Các chặng có thể được đo riêng:

| Chặng | Thời gian cần quan sát | Dấu hiệu khi chậm |
|---|---|---|
| Client → Config Server | DNS, connect, TLS, HTTP response | Client startup chậm dù server xử lý nhanh |
| Config Server HTTP | Queue/thread, controller, serialization | Nhiều request cùng chậm |
| `EnvironmentRepository.find` | Tổng thời gian lấy Environment | Chỉ request đọc cấu hình chậm |
| Git remote access | Kết nối, xác thực, fetch objects | Tăng latency hoặc lỗi backend |
| Local repository | Checkout label, đọc file, search paths | Git remote nhanh nhưng server vẫn chậm |
| Client retry | Số lần gọi và thời gian backoff | Startup kéo dài theo từng lần thử |

Một request Config Data có thể tạo nhiều lần gọi Config Server. Spring Boot trước tiên tải cấu hình với profile `default` để xác định profile được kích hoạt, rồi gọi thêm lần nữa cho các profile đang hoạt động. Vì vậy, hai hoặc nhiều request lúc startup không tự động là lỗi hoặc retry. Hãy đối chiếu application, profile, label và trace ID trước khi kết luận. Xem [Spring Cloud Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html).

## 2. Metric có sẵn của Spring Cloud Config

Spring Cloud Config hiện hành tạo Micrometer Observation quanh `EnvironmentRepository`. Observation này cung cấp timer, long-task timer và span:

| Tên metric/span | Loại | Ý nghĩa |
|---|---|---|
| `spring.cloud.config.environment.find` | Timer | Thời gian hoàn tất một lần lấy Environment |
| `spring.cloud.config.environment.find.active` | Long task timer | Những lần lấy Environment vẫn đang chạy |

Observation gắn các tag có cardinality thấp:

- `spring.cloud.config.environment.application`: application được yêu cầu.
- `spring.cloud.config.environment.class`: lớp triển khai `EnvironmentRepository`.
- `spring.cloud.config.environment.label`: Git label hoặc label của backend.
- `spring.cloud.config.environment.profile`: profile được yêu cầu.

Tên tag được Spring Cloud Config công bố trong convention là nhóm low-cardinality. Tuy nhiên, giá trị thực tế vẫn cần được kiểm soát: nếu `label` là một commit SHA mới sau mỗi lần phát hành, số giá trị label có thể tăng liên tục. Với metric tự tạo, ưu tiên branch/profile ổn định; ghi commit SHA vào log hoặc trace để điều tra một lần phát hành cụ thể.

Metric giúp trả lời các câu hỏi:

- Request đọc cấu hình đang mất bao lâu?
- Có bao nhiêu lần tìm Environment đã hoàn tất?
- Có bao nhiêu thao tác đang chạy lâu bất thường?
- Backend nào đang được sử dụng qua tag `class`?
- Application/profile/label nào thường tạo request chậm?

Timer có thể được phân tích bằng count, total time, max và percentile/histogram nếu registry được cấu hình. Long-task timer giúp thấy thao tác còn đang chạy, hữu ích khi backend treo hoặc fetch kéo dài.

**Giới hạn cần hiểu:** metric `spring.cloud.config.environment.find` đo toàn bộ thao tác tìm Environment. Nó không phải một metric Git-fetch chuyên biệt. Nếu repository không fetch vì local working copy còn trong thời gian `refreshRate`, timer chủ yếu phản ánh việc đọc local repository và tạo response. Nếu cần tách chính xác thời gian DNS, TLS, JGit fetch, checkout và đọc file, cần bổ sung instrumentation ở các điểm đó.

Các tên metric, span và tag trên được tài liệu Spring Cloud Config mô tả tại [Observability](https://docs.spring.io/spring-cloud-config/reference/observability.html). Kiểm tra tài liệu đúng release train vì tên hoặc mức hỗ trợ có thể thay đổi giữa phiên bản.

## 3. Bật metrics và xuất dữ liệu

Spring Boot Actuator dùng Micrometer để thu thập metrics. Nếu muốn Prometheus scrape Config Server, thêm registry tương ứng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Expose những endpoint cần thiết:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
~~~

Prometheus scrape `/actuator/prometheus`. Endpoint `/actuator/metrics` hữu ích để kiểm tra tên meter và tag trong môi trường chẩn đoán, nhưng không nên dùng làm metrics backend để scrape production. Dùng registry/Prometheus hoặc hệ thống giám sát tương ứng để thu thập liên tục.

Một số metric nền tảng cũng hữu ích khi điều tra Config Server:

| Metric family | Dùng để chẩn đoán |
|---|---|
| `http.server.requests` | Request count, status, latency của Config Server |
| `jvm.memory.*` | Áp lực heap và non-heap khi xử lý nhiều file |
| `jvm.gc.*` | Pause do garbage collection |
| `jvm.threads.*` | Thread usage và tình trạng nghẽn |
| `process.*`, `system.*` | CPU, file descriptor và tài nguyên process |
| `disk.*` | Dung lượng và tình trạng filesystem chứa local clone |

Các meter mặc định phụ thuộc server runtime và thư viện có trên classpath. Hãy kiểm tra meter thực tế tại `/actuator/metrics` trước khi viết query dashboard.

Không expose `metrics`, `prometheus` hoặc health detail công khai nếu endpoint có thể tiết lộ thông tin nội bộ. Bảo vệ bằng network policy, authentication và phân quyền phù hợp.

## 4. Quan sát thời gian fetch Git

Git backend mặc định clone remote repository khi có request đầu tiên. Đây là lazy clone. Vì vậy, Config Server có thể khởi động thành công dù URI Git sai hoặc Git server đang không truy cập được; lỗi chỉ xuất hiện khi request cấu hình đầu tiên tới repository đó.

Có thể yêu cầu clone lúc startup:

~~~yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.internal/platform/config-repo.git
          clone-on-start: true
          timeout: 5
          refresh-rate: 30
~~~

Ý nghĩa:

- `clone-on-start: true`: kiểm tra và clone repository trong lúc Config Server khởi động, giúp phát hiện lỗi nguồn cấu hình sớm.
- `timeout`: giới hạn thời gian chờ lấy kết nối HTTP/SSH tới Git; mặc định hiện hành là 5 giây.
- `refresh-rate`: khoảng thời gian tính bằng giây kiểm soát việc fetch cập nhật từ Git.

`timeout` là timeout kết nối Git, không phải tổng thời gian hoàn thành clone/fetch, đọc file và trả HTTP response. Một fetch lớn hoặc repository có nhiều object vẫn có thể mất nhiều thời gian hơn.

### Hiểu đúng refresh-rate

| Giá trị | Hành vi |
|---|---|
| `0` (mặc định) | Fetch cập nhật Git mỗi khi có request phù hợp |
| Số dương, ví dụ `30` | Chỉ kiểm tra/fetch cập nhật theo khoảng thời gian cấu hình |
| Số âm | Không refresh repository từ remote |

`refresh-rate: 0` giúp server phát hiện commit mới thường xuyên, nhưng mỗi lần request có thể tạo thêm tải lên Git remote. Khi nhiều client khởi động cùng lúc, Git provider có thể nhận một đợt fetch lớn.

Đặt `refresh-rate` dương giúp giảm tần suất fetch và tải lên backend, đổi lại cấu hình mới có thể mất thêm thời gian mới xuất hiện ở local working copy. Chọn khoảng thời gian dựa trên yêu cầu freshness, số lượng Config Client và giới hạn Git provider.

### Theo dõi fetch thành công và freshness

Không chỉ đo latency. Cần ghi nhận:

- Thời điểm fetch thành công gần nhất.
- Thời điểm fetch gần nhất thất bại.
- Revision/commit SHA của local working copy.
- Revision mong muốn từ pipeline phát hành.
- Thời gian kể từ lần fetch thành công.
- Repository/remote tương ứng với request.

Config Server có thể tiếp tục trả cấu hình từ local working copy nếu Git remote ngừng hoạt động sau lần clone thành công. Với `refresh-rate` dương, lần fetch thất bại có thể không làm request hiện tại lỗi; local copy vẫn giữ revision cũ. Khi Git phục hồi, lần fetch kế tiếp mới cập nhật local copy.

Nếu local working copy đã bị chỉnh sửa hoặc lệch khỏi remote, fetch có thể không ghi đè được các thay đổi xung đột. Thuộc tính `force-pull` có thể buộc server reset working copy về trạng thái remote, nhưng thao tác này loại bỏ thay đổi cục bộ. Chỉ bật khi local clone được xem là cache có thể tái tạo và không có thay đổi thủ công cần giữ.

Do đó, HTTP 200 và health UP không chứng minh server đang phục vụ commit mới nhất. Cần so sánh revision được trả về với revision mong muốn. Nếu có nhiều Config Server replica, mỗi instance có local working copy riêng và có thể lệch freshness; dashboard phải phân biệt theo instance.

## 5. Theo dõi truy cập backend và EnvironmentRepository

Spring Cloud Config không chỉ có Git backend. Một server có thể dùng native filesystem, Vault, JDBC, SVN hoặc composite repository tùy module và cấu hình. Tag `spring.cloud.config.environment.class` cho biết implementation `EnvironmentRepository` đang xử lý request.

Khi một backend chậm, hãy kiểm tra cả thời gian tổng `environment.find` và metric riêng của backend nếu thư viện đó cung cấp.

Ví dụ các dấu hiệu:

| Backend | Thành phần cần quan sát |
|---|---|
| Git | DNS/TLS, xác thực, remote fetch, số object tải, checkout và filesystem cache |
| Native filesystem | Disk latency, quyền truy cập, số file và search path |
| JDBC | Connection pool, query latency, lock và database availability |
| Vault | Token/auth, API latency, lease/secret backend và rate limit |
| Composite | Latency và lỗi của từng repository thành phần; thứ tự/chiến lược tổng hợp |

Không giả định metric Git có thể áp dụng cho JDBC hoặc Vault. Với composite repository, một thành phần chậm có thể kéo dài toàn bộ request hoặc khiến kết quả phụ thuộc chiến lược xử lý lỗi.

Nếu backend không có instrumentation chi tiết, tạo custom Observation ở adapter hoặc wrapper quanh thao tác backend. Ví dụ dưới đây minh họa cách đo một pha fetch riêng. `fetchFromRemote()` đại diện cho thao tác thực tế của adapter; đây không phải API có sẵn của `EnvironmentRepository`:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.stereotype.Component;

@Component
public class GitFetchObservation {

    private final ObservationRegistry observationRegistry;

    public GitFetchObservation(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public <T> T observeFetch(java.util.function.Supplier<T> fetchFromRemote) {
        return Observation.createNotStarted(
                "config.git.fetch",
                observationRegistry
            )
            .lowCardinalityKeyValue("backend", "git")
            .observe(fetchFromRemote);
    }
}
~~~

Observation có thể tạo timer và span khi handler tương ứng được đăng ký. Thêm tag ổn định như backend hoặc repository class. Không đưa commit SHA, token, URL chứa credentials, user ID hoặc tên branch tự do có số lượng lớn vào metric tag. Những thông tin có cardinality cao nên đặt trong trace/log đã kiểm soát hoặc lưu dưới dạng revision field.

## 6. Health indicator của Config Server

Config Server có Health Indicator kiểm tra `EnvironmentRepository` có hoạt động hay không. Mặc định, indicator yêu cầu repository trả cấu hình cho application `app`, profile `default` và label mặc định.

Nếu môi trường production dùng application/profile/label khác, hãy cấu hình probe sát với workload:

~~~yaml
spring:
  cloud:
    config:
      server:
        health:
          repositories:
            orders-prod:
              name: order-service
              profiles: prod
              label: main
            payments-prod:
              name: payment-service
              profiles: prod
              label: release
~~~

Health indicator có thể bị tắt bằng `spring.cloud.config.server.health.enabled=false`. Có thể cấu hình trạng thái DOWN riêng theo yêu cầu vận hành.

Health indicator hữu ích để phát hiện repository không trả dữ liệu. Tuy nhiên, nó không thay thế revision freshness check. Nếu Config Server đang dùng local working copy cũ, health probe có thể thành công dù Git remote không cập nhật được. Để phát hiện trường hợp đó, cần theo dõi fetch failure và revision của local copy.

Ở phía Config Client cũng có health indicator kiểm tra Config Server. Kết quả được cache để giảm request; TTL mặc định hiện hành là 5 phút và có thể điều chỉnh bằng `health.config.time-to-live` (milliseconds). Khi đọc dashboard, hãy tính đến cache này để không diễn giải một trạng thái UP cũ như kiểm tra vừa thực hiện.

## 7. Quan sát HTTP request và distributed trace

Metrics tổng hợp cho biết request chậm, còn trace giúp tìm chặng gây chậm. Một trace lý tưởng cho lần lấy cấu hình có thể gồm:

1. Config Client tạo request lấy cấu hình.
2. Config Server nhận HTTP request.
3. `EnvironmentRepository.find` bắt đầu.
4. Git/backend access bắt đầu và kết thúc.
5. Server đọc property source và trả response.
6. Config Client hoàn tất nạp cấu hình.

Spring Cloud Config khai báo span `spring.cloud.config.environment.find` quanh `EnvironmentRepository`. Spring Boot dùng Micrometer Observation và Micrometer Tracing để liên kết metrics với traces. Log có thể tự động chứa `traceId` và `spanId` khi Micrometer Tracing được cấu hình.

Ví dụ log nên chứa metadata có ích:

~~~text
timestamp=2026-11-27T10:15:00Z
service=config-server
instance=config-server-2
application=order-service
profile=prod
label=main
revision=8f31c42
event=config-fetch-completed
duration_ms=842
result=success
traceId=...
~~~

Không ghi property values, password, token hoặc toàn bộ response cấu hình vào log. Nếu cần correlation giữa client và server, truyền trace context qua HTTP client được instrument đúng cách. Với custom client không tự động truyền trace context, cần cấu hình propagation tương ứng.

Để xem riêng thời gian JGit fetch, hãy tạo custom span/observation quanh thao tác fetch. Span `environment.find` chỉ bao phủ tổng hoạt động repository; không nên suy ra phần trăm thời gian Git fetch chỉ từ metric tổng.

## 8. Phân biệt retry của Client và fetch lại Git ở Server

Hai cơ chế thường bị nhầm:

- **Config Client retry:** gọi lại HTTP request tới Config Server khi client không lấy được cấu hình, thường quan trọng trong lúc startup.
- **Git refresh/fetch:** Config Server kiểm tra remote Git và cập nhật local working copy theo `refresh-rate`.

Client retry không tự cấu hình retry cho JGit. Nếu Git remote lỗi nhưng Config Server vẫn trả local working copy, client có thể nhận HTTP 200 với revision cũ; retry client không phát hiện được dữ liệu cũ nếu response vẫn thành công.

Các thuộc tính `spring.cloud.config.retry.*` thuộc Config Client. Không có một nhóm thuộc tính retry Git server tương đương được mô tả trong cấu hình Git backend tiêu chuẩn; muốn retry riêng cho fetch hoặc thao tác backend tùy biến, cần triển khai ở tầng repository/adapter hoặc dùng cơ chế phục hồi của Git provider và hạ tầng.

Nếu Config Server không có local clone và Git không truy cập được, request có thể lỗi. Khi đó client retry có thể gọi lại Config Server, nhưng nếu backend chưa phục hồi, các lần thử tiếp theo chỉ tạo thêm tải. Cần theo dõi nguyên nhân gốc ở server và backend.

### Cấu hình retry khi startup

Với Spring Cloud Config 5.1, có thể bật retry như sau:

~~~yaml
spring:
  config:
    import: "configserver:https://config.internal.example"
  cloud:
    config:
      fail-fast: true
      retry:
        enabled: true
        max-attempts: 6
        initial-interval: 1s
        max-interval: 2s
        multiplier: 1.1
      request-connect-timeout: 2000
      request-read-timeout: 5000
~~~

Trong cấu hình này:

- `fail-fast: true` khiến ứng dụng không tiếp tục startup nếu không thể lấy cấu hình bắt buộc.
- `retry.enabled: true` bật retry cho request lấy cấu hình.
- `max-attempts` đếm cả lần gọi đầu tiên. Giá trị 6 nghĩa là một lần gọi ban đầu và tối đa năm lần retry.
- `initial-interval` là thời gian chờ ban đầu.
- `multiplier` tăng thời gian chờ theo cấp số nhân.
- `max-interval` giới hạn thời gian chờ giữa các lần thử.
- `request-connect-timeout` và `request-read-timeout` giới hạn thời gian kết nối và đọc response từ Config Server.

Trong ví dụ, `max-interval: 2s` là lựa chọn minh họa do ứng dụng đặt; hãy chọn dựa trên startup budget và timeout thực tế. Không để tổng thời gian retry dài hơn thời gian orchestration cho phép ứng dụng khởi động.

Với Spring Cloud Config trước 5.1, retry dựa trên Spring Retry và cần dependency tương ứng trên classpath. Từ 5.1, retry dùng cơ chế retry của Spring Framework; cần đặt `spring.cloud.config.retry.enabled=true`. Kiểm tra tài liệu đúng phiên bản trước khi nâng cấp vì dependency và cách bật retry đã thay đổi.

Nếu `spring.config.import` nằm trong file profile như `application-prod.yml`, cấu hình retry có thể cần đặt dưới dạng query parameter trên chính URL `configserver:` theo hướng dẫn Config Client. Không giả định các property trong profile luôn có sẵn đủ sớm để điều khiển lần import profile đó.

## 9. Retry, nhiều Config Server URL và giới hạn lỗi

Có thể cấu hình nhiều Config Server URL để client thử các server theo thứ tự. Với danh sách URL trong `spring.cloud.config.uri`, chiến lược mặc định là `always`, nhưng không có nghĩa mọi HTTP error đều kích hoạt fallback: response 500 hoặc 401 không khiến client thử URL tiếp theo. Nếu chọn `connection-timeout-only`, client chỉ chuyển URL khi Config Server không chạy hoặc xảy ra connection timeout. Không phải mọi lỗi đều nên được xem là lỗi availability:

- Lỗi kết nối hoặc timeout có thể cho thấy một server tạm thời không sẵn sàng.
- HTTP 401 thường là lỗi credential hoặc authorization.
- HTTP 400 thường là request không hợp lệ.
- HTTP 404 có thể là application/profile/label không tồn tại, nhưng khi server dùng Git backend, lỗi gọi Git remote cũng có thể xuất hiện dưới dạng 404 tùy tình huống.

`spring.cloud.config.multiple-uri-strategy` điều khiển cách thử nhiều URL khi dùng `spring.cloud.config.uri`. Với nhiều `spring.config.import` locations, nếu `fail-fast` bật thì client dừng khi lần gọi đầu tiên thất bại; nếu tắt thì client thử các location theo thứ tự cho tới khi một lần gọi thành công. Cơ chế `multiple-uri-strategy` không áp dụng cho các import locations. Hãy kiểm tra đúng kiểu cấu hình endpoint đang dùng trước khi kỳ vọng failover.

Không retry vô hạn các lỗi cấu hình cố định như credential sai, application name sai hoặc label không tồn tại. Retry nên có giới hạn, backoff và jitter để nhiều client không cùng gọi lại đúng một thời điểm. Khi backend lỗi kéo dài, hãy giảm tải, cảnh báo và phục hồi backend thay vì tăng `max-attempts` tùy tiện.

## 10. Đo retry và lỗi backend

Config Client retry cần được quan sát bằng các trường:

- Số lần request Config Server trên mỗi lần startup.
- Số lần retry và tổng thời gian backoff.
- Lỗi cuối cùng sau khi hết attempts.
- URL/instance Config Server được gọi.
- HTTP status và exception class.
- Application/profile/label được yêu cầu.

Config Server cần theo dõi:

- Số lần `EnvironmentRepository.find`.
- Timer và long-task timer.
- Fetch thành công/thất bại theo repository.
- Thời gian từ lần fetch thành công gần nhất.
- Revision local đang phục vụ.
- Git connection timeout, authentication failure, DNS/TLS failure.
- Local clone disk usage và lỗi đọc filesystem.

Nếu metric mặc định không cung cấp counter retry chi tiết, thêm custom counter/observation tại client retry interceptor hoặc thành phần điều khiển retry. Đặt tên metric rõ nghĩa, ví dụ `config.client.retry.attempts` và `config.git.fetch.failures`; đây là tên metric do ứng dụng tự tạo, không phải metric mặc định của Spring Cloud Config.

Một retry thành công sau lần đầu vẫn là dấu hiệu cần theo dõi. Nếu chỉ nhìn tỷ lệ request cuối cùng thành công, bạn có thể bỏ qua tình trạng backend đang chập chờn và thời gian startup đang tăng.

## 11. Thiết kế dashboard vận hành

Một dashboard nên tách Config Client, Config Server và backend thành các hàng quan sát:

| Khu vực | Panel nên có |
|---|---|
| Client | Startup config fetch duration, retry attempts, lỗi lấy cấu hình, số lần request theo profile |
| Server HTTP | Request rate, p50/p95/p99 latency, status code, thread usage |
| EnvironmentRepository | `environment.find` count, duration, active long tasks, backend class |
| Git | Fetch duration, fetch failures, last successful fetch age, local revision |
| Backend khác | Latency, timeout, error rate và pool/connection status |
| Freshness | Desired revision so với revision server đang phục vụ |
| Runtime | CPU, heap, GC, thread và disk usage |

Đối với nhiều Config Server replica, thêm instance ID vào dashboard để nhận ra một replica có local working copy cũ hoặc Git connection lỗi riêng. Một request load-balanced thành công từ replica A không chứng minh replica B đang đồng bộ.

### Gợi ý cảnh báo

- p95 của `environment.find` vượt SLO trong nhiều cửa sổ liên tiếp.
- Long-task timer tăng hoặc có thao tác repository kéo dài bất thường.
- Git fetch thất bại liên tục hoặc thời gian từ lần fetch thành công cuối cùng vượt giới hạn freshness.
- Desired revision khác revision local đang phục vụ quá lâu.
- Client retry tăng đột biến hoặc nhiều instance không thể startup.
- Config Server health DOWN cho repository production.
- HTTP 5xx/404 tăng cùng thời điểm backend Git có lỗi.
- Disk chứa local clone gần đầy hoặc Config Server restart làm mất local cache khi remote đang lỗi.

Đặt ngưỡng theo baseline và SLO của hệ thống. Một repository lớn có latency khác repository nhỏ; không dùng một ngưỡng cố định cho mọi môi trường.

## 12. Quy trình điều tra khi Config Client lấy cấu hình chậm

Khi nhận cảnh báo, làm theo thứ tự:

1. Xác định client nào chậm, profile/label nào được yêu cầu và thời điểm startup.
2. Kiểm tra thời gian HTTP ở client và server.
3. Tìm trace tương ứng và xem span `environment.find`.
4. Nếu `environment.find` chậm, kiểm tra Git/backend access và local filesystem.
5. Đối chiếu `refresh-rate` để xác định request đó có cần fetch remote hay đang đọc local copy.
6. Kiểm tra DNS, TLS, credentials, Git provider rate limit và `git.timeout`.
7. Kiểm tra server health và revision local đang phục vụ.
8. Kiểm tra client retry attempts, connect/read timeout và nhiều Config Server URL.
9. Sau khi backend phục hồi, xác minh revision mới đã được fetch và client đã nạp revision mong muốn.

Một số mẫu chẩn đoán:

| Quan sát | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| HTTP server chậm, `environment.find` cũng chậm | Backend hoặc repository xử lý chậm | Xem trace, Git fetch và disk |
| HTTP server nhanh nhưng client startup chậm | DNS/connect/TLS, response read hoặc retry ở client | Xem client trace, timeout và số attempts |
| `environment.find` nhanh nhưng config cũ | Server trả local working copy chưa được cập nhật | So revision, last fetch và refresh-rate |
| Một Config Server replica chậm | Clone/cache, network hoặc disk riêng của replica | So sánh metrics theo instance |
| Startup chỉ chậm ở lần đầu | Lazy clone hoặc tải nhiều Git objects | Bật clone-on-start nếu muốn phát hiện sớm và đo startup |
| Client retry tăng nhưng Git fetch không tăng | Client không kết nối được Config Server hoặc server lỗi trước khi vào backend | Kiểm tra HTTP, network và server health |
| HTTP 200 nhưng backend remote đang down | Server vẫn phục vụ local working copy | Kiểm tra freshness, không chỉ status code |

## 13. Kiểm thử tình huống backend và retry

Một bài kiểm thử staging nên mô phỏng:

- **Cold start:** xóa local clone trong môi trường test, khởi động Config Server và đo thời gian clone lần đầu.
- **Warm request:** gọi cùng application/profile/label lần nữa để đo hiệu quả local working copy.
- **Refresh rate:** thay đổi Git commit, gọi liên tục và quan sát thời điểm local revision thay đổi với `refresh-rate: 0` và giá trị dương.
- **Git latency:** thêm độ trễ mạng có kiểm soát để quan sát timer và long-task timer.
- **Git unavailable:** ngắt kết nối remote sau khi clone thành công, xác minh server có thể trả local copy và revision không đổi.
- **No local clone:** restart Config Server khi Git đang down, kiểm tra request lỗi khi lazy clone không có cache.
- **Client retry:** làm Config Server unavailable trong lúc startup rồi khôi phục trước khi hết attempts.
- **Authentication failure:** dùng credential sai để xác minh hệ thống báo lỗi rõ và không retry vô hạn.
- **Multiple replicas:** tạo tình huống một replica fetch được, replica khác không fetch được; so sánh revision và health.
- **Recovery:** khôi phục Git, xác minh lần fetch kế tiếp cập nhật revision và client nhận được cấu hình mới.

Ghi lại thời điểm bắt đầu/kết thúc, application/profile/label, Config Server instance, revision, HTTP status, số lần retry và kết quả backend. Không dùng repository production hoặc ngắt backend đang phục vụ traffic thật để thử nghiệm.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Config Server startup thành công nhưng request đầu tiên lỗi | Lazy clone chưa chạy trong startup | Bật `clone-on-start` để kiểm tra repository sớm |
| Mỗi request đều chậm và Git provider bị tải cao | `refresh-rate: 0` khiến fetch mỗi request | Chọn refresh rate dương theo freshness SLO |
| Config Server trả 200 nhưng client dùng config cũ | Local working copy vẫn được phục vụ khi Git remote down | Theo dõi revision và last successful fetch |
| Client startup mất nhiều thời gian sau sự cố | Retry/backoff cộng dồn hoặc timeout quá lớn | Đặt retry budget và timeout theo startup budget |
| Retry không chạy ở Config Client 5.1 | Chưa bật `spring.cloud.config.retry.enabled` | Bật retry rõ ràng và `fail-fast` theo yêu cầu |
| Retry không hoạt động ở phiên bản cũ | Thiếu Spring Retry dependency hoặc interceptor | Kiểm tra release train và dependency |
| Health UP nhưng Git chưa có commit mới | Health kiểm tra repository có thể trả dữ liệu từ local clone | Thêm freshness check theo revision |
| Chỉ một replica trả config cũ | Local working copy của replica đó không đồng bộ | So sánh fetch timestamp và revision theo instance |
| Git timeout không dừng thao tác tổng thể đúng kỳ vọng | `git.timeout` chỉ giới hạn kết nối | Đặt thêm timeout HTTP client và theo dõi toàn request |
| Dashboard có quá nhiều time series | Gắn commit SHA hoặc label tùy ý vào metric tags | Dùng tag cardinality thấp; đưa revision vào log/trace |

## 15. Checklist production

- Bật Actuator metrics và registry phù hợp; bảo vệ endpoint quản trị.
- Theo dõi `spring.cloud.config.environment.find` và `.active`.
- Theo dõi span `spring.cloud.config.environment.find`.
- Phân biệt HTTP request latency với backend fetch latency.
- Quyết định rõ `clone-on-start` theo yêu cầu fail-fast.
- Chọn `refresh-rate` theo freshness SLO và tải Git provider.
- Theo dõi revision local và thời điểm fetch thành công cuối cùng.
- Cấu hình Git connection timeout và Config Client connect/read timeout.
- Bật retry có giới hạn cho Config Client startup khi cần.
- Phân biệt retry của client với fetch Git ở Config Server.
- Có health probe cho application/profile/label production thực tế.
- Theo dõi từng Config Server replica và local working copy.
- Không log secret hoặc config values.
- Không gắn commit SHA, token hoặc branch tự do làm metric tag.
- Kiểm thử Git outage, cold clone, retry exhaustion và recovery.
- Chỉ đánh dấu rollout thành công sau khi xác nhận revision thực tế được phục vụ.

## 16. Tự kiểm tra

1. `spring.cloud.config.environment.find` đo phần nào của request?
2. Vì sao metric `environment.find` không đủ để xác định chính xác thời gian JGit fetch?
3. `refresh-rate: 0`, giá trị dương và giá trị âm khác nhau thế nào?
4. Vì sao Config Server có thể trả HTTP 200 trong khi Git remote đang không truy cập được?
5. `clone-on-start` thay đổi thời điểm phát hiện lỗi Git như thế nào?
6. Config Server Health Indicator kiểm tra repository với application/profile/label nào theo mặc định?
7. Client retry và Git refresh/fetch khác nhau ở thành phần nào và thời điểm nào?
8. Trong Spring Cloud Config 5.1, `max-attempts: 6` có nghĩa là sáu lần retry hay sáu lần gọi tổng cộng?
9. Vì sao không nên retry vô hạn khi credential Git sai hoặc label không tồn tại?
10. Cần theo dõi dữ liệu nào để phát hiện một Config Server replica đang phục vụ revision cũ?

Hãy triển khai Config Server và một Config Client trong staging, dùng Git repository có ít nhất hai commit. Bật `clone-on-start`, Prometheus metrics và tracing. Đo lần clone đầu, request warm và request sau khi commit mới được push. Thử đặt `refresh-rate` thành 0 rồi một giá trị dương, so sánh số lần fetch và độ trễ cập nhật. Tiếp theo ngắt Git remote sau khi local clone đã tồn tại để quan sát server phục vụ revision cũ; restart server khi remote vẫn down để kiểm tra cold-start failure. Cuối cùng tạo lỗi kết nối Config Server để kiểm thử client retry, rồi đối chiếu số lần retry với trace và thời gian startup. Ghi nhận desired revision và applied revision ở từng bước.

## Tài liệu tham khảo

- [Spring Cloud Config — Observability](https://docs.spring.io/spring-cloud-config/reference/observability.html)
- [Spring Cloud Config — Git Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html)
- [Spring Cloud Config — Health Indicator](https://docs.spring.io/spring-cloud-config/reference/server/health-indicator.html)
- [Spring Cloud Config — Config Client, Retry, Multiple URLs and Timeouts](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)

