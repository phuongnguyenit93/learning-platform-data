# Theo dõi health của Config Server và các repository

Config Server chỉ hữu ích khi có thể cung cấp đúng Environment cho ứng dụng yêu cầu. Một tiến trình Java đang chạy và trả HTTP 200 ở endpoint health chưa chắc đã đọc được Git repository, truy vấn được database hoặc lấy được secret từ Vault. Vì vậy, cần theo dõi cả sức khỏe của Config Server lẫn khả năng đọc các repository theo những application, profile và label thực tế.

Spring Boot Actuator cung cấp health endpoint; Spring Cloud Config Server bổ sung health indicator để kiểm tra khả năng truy xuất cấu hình từ EnvironmentRepository. Có thể cấu hình các context đại diện để health check kiểm tra đúng repository và phiên bản cấu hình cần phục vụ. Khi đưa vào load balancer hoặc Kubernetes, hãy phân biệt liveness với readiness: backend lỗi thường khiến node không sẵn sàng phục vụ, nhưng không nhất thiết có nghĩa process cần bị khởi động lại.

## 1. Các lớp cần quan sát

Health của hệ thống cấu hình gồm nhiều lớp:

~~~mermaid
flowchart TD
    A[Config Client] --> B[Load balancer / Config Server URL]
    B --> C[Config Server process]
    C --> D[EnvironmentRepository]
    D --> E[Git / JDBC / Vault / Native / Composite]
    C --> F[Actuator health]
    F --> G[Config Server health indicator]
    G --> D
    H[Metrics, logs, traces and alerts] --> F
    H --> C
    H --> D
~~~

| Lớp | Câu hỏi cần trả lời | Tín hiệu quan sát |
|---|---|---|
| Process | JVM và ứng dụng còn hoạt động không? | Liveness, process/JVM metrics |
| HTTP server | Config Server có nhận request không? | Readiness, request rate, latency, HTTP status |
| Repository abstraction | Server có tạo được Environment không? | Config Server health indicator |
| Backend cụ thể | Git, JDBC, Vault hoặc filesystem có truy cập được không? | Health check, backend logs, connection/query metrics |
| Cấu hình thực tế | Application/profile/label quan trọng có trả đủ property không? | Environment endpoint, metadata, smoke test |
| Client impact | Các dịch vụ có lấy được cấu hình và khởi động không? | Client logs, startup failures, refresh results |

Không nên gom tất cả thành một tín hiệu duy nhất. Một Config Server có thể UP nhưng một repository hoặc một label riêng đang lỗi; ngược lại, một backend phụ có thể lỗi nhưng các ứng dụng không sử dụng backend đó vẫn hoạt động bình thường.

## 2. Thêm Spring Boot Actuator vào Config Server

Config Server cần Actuator để expose health endpoint. Với Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-config-server</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Ứng dụng Config Server cũng cần bật server mode:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.config.server.EnableConfigServer;

@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
~~~

Expose health và info qua HTTP:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: when-authorized
~~~

Actuator chỉ expose một tập endpoint giới hạn theo mặc định. Chỉ thêm endpoint thực sự cần cho monitoring. Không expose `env`, `configprops`, `beans` hoặc endpoint quản trị rộng ra mạng công cộng chỉ để công cụ giám sát đọc được health.

Nếu dùng management port hoặc base path riêng, URL health thay đổi theo cấu hình:

~~~yaml
management:
  server:
    port: 9001
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info
~~~

Khi đó endpoint health nằm tại `/manage/health` trên port 9001. Hãy cấu hình load balancer và monitoring dùng đúng port/path; không mặc định mọi deployment đều sử dụng `/actuator/health` trên cổng ứng dụng.

## 3. Đọc health tổng thể

Gọi endpoint:

~~~bash
curl --fail https://config-server.internal/actuator/health
~~~

Một response thành công có dạng khái niệm:

~~~json
{
  "status": "UP",
  "components": {
    "diskSpace": {
      "status": "UP"
    },
    "ping": {
      "status": "UP"
    },
    "configServer": {
      "status": "UP"
    }
  }
}
~~~

Danh sách component chính xác phụ thuộc dependency, phiên bản Spring Boot/Spring Cloud và health contributor được đăng ký. Config Server health indicator thường xuất hiện dưới component `configServer`. Nếu health detail bị ẩn, người gọi không được cấp quyền có thể chỉ thấy trạng thái tổng thể.

`UP` có nghĩa các health contributor được cấu hình đã báo trạng thái tốt tại thời điểm kiểm tra. Nó không chứng minh tất cả application/profile/label trong repository đều hợp lệ, cũng không chứng minh mọi client đã nhận cấu hình mới.

Có thể truy vấn riêng component nếu endpoint và quyền truy cập cho phép:

~~~bash
curl --fail https://config-server.internal/actuator/health/configServer
~~~

Nếu component ID khác trong phiên bản đang dùng, xem danh sách component trong response health tổng thể và dùng đúng ID được công bố. Không dựa vào một đường dẫn hard-code nếu đã tùy chỉnh health contributor.

## 4. Config Server health indicator kiểm tra điều gì?

Spring Cloud Config Server có health indicator cho EnvironmentRepository. Theo mặc định, health indicator thực hiện một lần tra cứu Environment mẫu bằng repository đã cấu hình. Mục đích là xác nhận server có thể tạo Environment từ backend.

Với Git backend, thao tác này có thể xác nhận repository có thể phục vụ context mẫu từ clone/cache hiện có. Không nên hiểu nó luôn buộc server fetch remote Git mới ở mỗi lần health check. Nếu cần xác nhận commit mới đã đến, hãy kiểm tra metadata `version` hoặc thực hiện smoke test theo label cụ thể.

Với JDBC, health check xác nhận truy vấn cấu hình mẫu có thể thực hiện qua repository. Với Vault hoặc composite backend, kết quả phụ thuộc cách EnvironmentRepository tương ứng đọc dữ liệu và xử lý lỗi. Một health check thành công ở context mặc định không đảm bảo mọi path, policy hoặc repository thành phần đều có thể phục vụ tất cả ứng dụng.

Health indicator hữu ích cho việc phát hiện lỗi backend phổ biến, nhưng cần bổ sung các kiểm tra đại diện cho những cấu hình quan trọng của hệ thống.

## 5. Cấu hình health check theo application, profile và label

Có thể khai báo các repository context cần được health indicator kiểm tra. Ví dụ:

~~~yaml
spring:
  cloud:
    config:
      server:
        health:
          enabled: true
          repositories:
            orders-production:
              name: orders-service
              profiles: prod
              label: release-2026.11
            payments-production:
              name: payment-service
              profiles: prod
              label: release-2026.11
            catalog-staging:
              name: catalog-service
              profiles: staging
              label: main
~~~

Mỗi entry đại diện một bộ ba application, profile và label mà Config Server cần thử đọc. Tên entry như `orders-production` là tên định danh của phép kiểm tra trong health report; `name` là application được yêu cầu.

Chọn các context có ý nghĩa vận hành:

- Ứng dụng quan trọng nhất trong production.
- Profile đang được triển khai thực tế.
- Label phát hành cần phục vụ.
- Repository thành phần trong composite nếu chúng có đường truy cập riêng.

Không cần liệt kê mọi tổ hợp profile và label nếu chúng không mang thêm giá trị chẩn đoán. Quá nhiều health check có thể tăng request backend, làm health endpoint chậm và khiến trạng thái tổng thể nhạy với những context ít quan trọng.

Tên thuộc tính và khả năng cấu hình chi tiết có thể thay đổi theo release train. Hãy đối chiếu metadata cấu hình của đúng phiên bản Spring Cloud Config trong dự án khi dùng cấu hình health nâng cao.

## 6. Tắt hoặc điều chỉnh health check

Trong một số môi trường, có thể tắt Config Server health indicator:

~~~yaml
spring:
  cloud:
    config:
      server:
        health:
          enabled: false
~~~

Chỉ tắt khi có lý do rõ ràng, ví dụ backend health được giám sát bằng một cơ chế chuyên biệt khác và health contributor hiện tại gây kiểm tra quá tốn kém. Khi tắt, `/actuator/health` có thể vẫn báo UP dù Config Server không đọc được repository. Phải thay thế bằng tín hiệu readiness phù hợp nếu load balancer hoặc orchestrator dựa vào health để quyết định gửi traffic.

Nếu health check chậm, trước hết xem số context được kiểm tra, thời gian truy cập backend, timeout và cache behavior. Không tăng timeout vô hạn hoặc tắt health chỉ để che giấu lỗi kết nối.

## 7. Phân biệt liveness và readiness

Hai probe có mục đích khác nhau:

- **Liveness:** process còn hoạt động và có thể tiếp tục chạy không? Nếu liveness fail, orchestrator có thể restart container.
- **Readiness:** instance có thể phục vụ request cấu hình ngay lúc này không? Nếu readiness fail, load balancer/orchestrator nên ngừng gửi request mới tới node đó.

Bật health probes:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
~~~

Các URL thường dùng:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

Với Config Server, không nên đưa tất cả phụ thuộc từ xa vào liveness. Nếu Git remote tạm thời mất kết nối, restart liên tục mọi Config Server có thể làm tăng tải và gây mất khả năng phục vụ từ các clone/cache đang dùng được. Có thể đưa kiểm tra repository vào readiness theo yêu cầu hệ thống để node không nhận request mới khi không thể đọc cấu hình cần thiết.

Ví dụ thêm Config Server health contributor vào readiness group:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,configServer
~~~

Tên contributor `configServer` cần được xác nhận từ health response thực tế. Nếu ứng dụng có custom health indicator hoặc phiên bản đặt ID khác, dùng đúng ID. Việc đưa backend vào readiness đồng nghĩa backend gián đoạn có thể làm node bị loại khỏi load balancer; hãy chọn chính sách này dựa trên khả năng phục vụ bằng cache và yêu cầu nhất quán.

## 8. Theo dõi Git repository

Với Git backend, cần theo dõi cả khả năng đọc clone cục bộ và trạng thái đồng bộ với remote:

- Clone-on-start có thành công không?
- Repository có branch/tag/commit label cần phục vụ không?
- Credential đọc repository còn hợp lệ không?
- Remote Git có timeout, rate limit hoặc lỗi TLS không?
- Mỗi Config Server replica đang phục vụ commit nào?
- Clone/cache có bị hỏng hoặc thiếu dung lượng không?

Ví dụ cấu hình Git:

~~~yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          default-label: main
          clone-on-start: true
          refresh-rate: 30
~~~

`refresh-rate` điều khiển khoảng thời gian tối thiểu giữa các lần refresh repository theo cơ chế Git backend của phiên bản đang dùng; giá trị `0` thường yêu cầu fetch mỗi lần truy cập. Cân nhắc tải lên Git remote và độ trễ cập nhật trước khi chọn. Đừng giả định health check luôn ép refresh remote.

Environment response có thể chứa metadata như `version` khi backend cung cấp. Gọi endpoint đại diện:

~~~bash
curl --fail \
  https://config-server.internal/orders-service/prod/release-2026.11
~~~

So sánh `version`, `label`, `profiles` và các property source giữa các replica. Nếu dùng tag hoặc commit SHA bất biến, việc xác minh nhất quán dễ dự đoán hơn so với branch luôn thay đổi.

## 9. Theo dõi JDBC, Vault, native và composite repositories

Health check cần phản ánh cách backend thực sự được sử dụng:

| Backend | Kiểm tra nên có | Rủi ro cần theo dõi |
|---|---|---|
| JDBC | Truy vấn context đại diện, connection pool, schema | DB failover, timeout, replica lag, thiếu row |
| Vault | Xác thực bằng identity của Config Server, đọc path được phép | Token/lease hết hạn, policy đổi, TLS hoặc Vault cluster lỗi |
| Native filesystem | Đọc file đại diện, kiểm tra mount và quyền | Volume mất kết nối, file thiếu, rollout không atomic |
| Composite | Kiểm tra từng nguồn thành phần và kết quả hợp nhất | Một backend lỗi, thứ tự ưu tiên thay đổi, dữ liệu không đồng bộ |

Với composite repository, một context tổng hợp có thể vẫn trả được Environment dù một backend không cung cấp dữ liệu cho key đó. Nếu backend thành phần là bắt buộc, hãy tạo health check riêng cho path hoặc context cần nó và theo dõi trạng thái từng nguồn.

Không chỉ kiểm tra TCP port. Kết nối thành công chưa chứng minh identity có quyền đọc đúng path, database query chạy được hoặc Git label tồn tại.

## 10. Kiểm tra cấu hình thực tế bằng Environment endpoint

Health indicator là kiểm tra tổng quát; để xác minh một cấu hình cụ thể, gọi endpoint Environment:

~~~bash
curl --fail \
  https://config-server.internal/orders-service/prod/release-2026.11
~~~

Kiểm tra:

1. `name` đúng application.
2. `profiles` đúng profile.
3. `label` đúng ref yêu cầu.
4. `version` khớp commit hoặc version backend mong đợi nếu được cung cấp.
5. `propertySources` có đủ nguồn cấu hình.
6. Các key bắt buộc tồn tại và có kiểu/giá trị hợp lệ.

Không dump toàn bộ response vào log monitoring nếu có thể chứa dữ liệu nhạy cảm. Dùng script smoke test chỉ trích xuất metadata và key không nhạy cảm. Với secret đã được giải mã, chỉ kiểm tra sự hiện diện hoặc khả năng bind; không in plaintext.

Ví dụ PowerShell chỉ hiển thị metadata:

~~~powershell
$environment = Invoke-RestMethod -Uri "https://config-server.internal/orders-service/prod/release-2026.11"

[PSCustomObject]@{
    Name = $environment.name
    Profiles = ($environment.profiles -join ",")
    Label = $environment.label
    Version = $environment.version
    PropertySourceCount = $environment.propertySources.Count
}
~~~

## 11. Dùng readiness qua load balancer

Nếu có nhiều Config Server replica, load balancer nên chỉ gửi request tới node ready. Một cấu hình health check của load balancer có thể dùng:

~~~text
GET /actuator/health/readiness
Expected status: 200
Interval: theo SLO và thời gian phục hồi
Timeout: ngắn hơn timeout request Config Client
Unhealthy threshold: đủ để tránh loại node do một lỗi mạng thoáng qua
~~~

Đây là thông số khái niệm; giá trị cụ thể phụ thuộc hạ tầng. Tránh đặt interval quá ngắn khiến một đợt Git fetch chậm làm tất cả node bị đánh dấu unhealthy cùng lúc.

Nếu readiness có phụ thuộc repository, kiểm tra backend có khả năng phục vụ từ cache hay không. Một node không thể fetch remote nhưng vẫn có thể phục vụ cấu hình đã cache có thể được xem là ready trong một chính sách chấp nhận stale config; khi đó cần hiển thị trạng thái degraded riêng và đặt giới hạn độ cũ. Nếu cấu hình phải luôn mới nhất, readiness cần fail khi không xác nhận được nguồn.

## 12. Metrics và cảnh báo

Actuator health cho biết trạng thái tại thời điểm gọi; metrics cho biết xu hướng và mức độ ảnh hưởng:

- Request rate và latency của endpoint Config Server.
- Tỷ lệ HTTP 4xx/5xx và timeout.
- Số request theo application/profile nếu có instrumentation an toàn.
- JVM heap, garbage collection, CPU và thread usage.
- Git fetch/clone duration và lỗi truy cập remote.
- JDBC connection pool usage, query latency và failure rate.
- Vault authentication/read failures.
- Số replica ready và thời gian node bị loại khỏi pool.
- Client startup failure, refresh failure và retry count.

Nếu dùng Prometheus, thêm registry và expose endpoint:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
~~~

Scrape `/actuator/prometheus` từ mạng monitoring được bảo vệ. Không tạo metric label có cardinality cao như commit SHA, request ID hoặc tên property tùy ý. Những metadata đó phù hợp hơn với log hoặc event.

Cảnh báo nên dựa trên triệu chứng ảnh hưởng:

- Không còn Config Server replica ready.
- Tỷ lệ request Environment lỗi vượt ngưỡng.
- Latency p95/p99 tăng kéo dài.
- Repository health fail liên tục.
- Config Server trả version cũ hơn release đã phê duyệt.
- Vault/JDBC/Git auth lỗi.
- Client không lấy được cấu hình trong thời gian startup hoặc refresh.

Không cảnh báo chỉ vì một lần health check chậm. Dùng cửa sổ đánh giá, số lần liên tiếp và mức độ ảnh hưởng tới dịch vụ.

## 13. Logs và trace để tìm nguyên nhân

Log cần giúp xác định request nào thất bại và ở backend nào:

- Correlation ID hoặc trace ID.
- Config Server instance xử lý request.
- Application, profile và label được yêu cầu.
- Backend repository được chọn.
- Thời gian xử lý và loại lỗi.
- Commit/version được trả về nếu có.

Không log password, token, private key, plaintext secret hoặc toàn bộ property source. Với lỗi xác thực, ghi loại lỗi và principal đã được làm mờ theo chính sách, không ghi credential.

Distributed tracing có thể nối request từ Config Client qua load balancer tới Config Server và backend nếu các thành phần đã được instrument. Trace nên giúp phân biệt thời gian chờ ở gateway, Config Server và backend. Không đưa giá trị cấu hình nhạy cảm vào span attribute.

## 14. Bảo vệ health và monitoring endpoints

Health detail có thể tiết lộ hostname, repository name, backend path, lỗi xác thực hoặc topology nội bộ. Cần:

- Chỉ expose endpoint cần thiết.
- Giới hạn management port bằng private network hoặc network policy.
- Bảo vệ health detail và metrics bằng authentication/authorization nếu phù hợp.
- Dùng HTTPS khi endpoint đi qua mạng không tin cậy.
- Chỉ cấp quyền read cho hệ thống monitoring.
- Không expose Environment endpoint cho probe định kỳ.
- Không hiển thị giá trị secret trong Actuator.
- Tách endpoint phục vụ load balancer khỏi endpoint chi tiết cho operator nếu cần.

Readiness endpoint có thể được load balancer truy cập không xác thực trong mạng riêng, nhưng health details nên chỉ dành cho operator. Thiết kế cụ thể phải cân bằng giữa yêu cầu probe và chính sách bảo mật của nền tảng.

## 15. Quy trình điều tra khi health báo DOWN

Khi Config Server health chuyển DOWN hoặc readiness fail:

1. Xác định component nào báo DOWN trong health response.
2. Kiểm tra Config Server process, HTTP server và resource usage.
3. Xác định application/profile/label health check đang thất bại.
4. Kiểm tra backend tương ứng: Git, JDBC, Vault, filesystem hoặc composite component.
5. Xác minh network, DNS, TLS, credential và permission từ chính Config Server instance.
6. Gọi Environment endpoint đại diện để lấy lỗi cụ thể; tránh in secret.
7. So sánh các Config Server replica nếu triển khai nhiều node.
8. Xác định lỗi là tạm thời, lỗi cấu hình hay thay đổi backend.
9. Khôi phục backend hoặc rollback cấu hình; theo dõi readiness trước khi đưa node trở lại pool.
10. Kiểm tra Config Client đã lấy lại được cấu hình và dịch vụ phụ thuộc đã phục hồi.

Nếu chỉ một repository context lỗi, xác định ứng dụng nào phụ thuộc vào context đó. Không nhất thiết phải loại mọi Config Server khỏi pool nếu các context khác vẫn được phục vụ và chính sách availability cho phép; tuy nhiên không được báo toàn hệ thống healthy khi một cấu hình bắt buộc đang không đọc được.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách kiểm tra |
|---|---|---|
| `/actuator/health` UP nhưng client không lấy được config | Health chỉ kiểm tra context mẫu hoặc không kiểm tra label cần thiết | Thêm repository health check đại diện và smoke test Environment |
| `configServer` DOWN | Repository không thể tạo Environment | Xem health detail, log backend và application/profile/label |
| Git health UP nhưng cấu hình vẫn cũ | Local clone/cache chưa fetch commit mới | So sánh `version`, kiểm tra refresh-rate và remote fetch |
| Chỉ một application bị lỗi | Context riêng hoặc profile-specific path thiếu/sai | Gọi đúng endpoint Environment cho application đó |
| Vault health/read thất bại | Token, policy, lease hoặc TLS lỗi | Xác minh identity và path từ Config Server |
| JDBC health fail | Database down, schema sai hoặc query timeout | Kiểm tra connection pool, schema và DB metrics |
| Readiness liên tục flap | Probe quá nhạy hoặc backend timeout không ổn định | Điều chỉnh threshold, timeout và readiness dependency |
| Tất cả node bị loại khỏi load balancer | Readiness phụ thuộc một backend đang lỗi toàn cục | Kiểm tra backend chung và chính sách degraded/cache |
| Health detail không xuất hiện | `show-details` hoặc quyền truy cập không cho phép | Kiểm tra authorization và cấu hình Actuator |
| Metrics endpoint 404 | Chưa thêm registry hoặc chưa expose endpoint | Kiểm tra dependency và management exposure |

## 17. Checklist quan sát production

- [ ] Config Server có Actuator và chỉ expose endpoint cần thiết.
- [ ] Health response có component Config Server khi phù hợp.
- [ ] Đã cấu hình context health check đại diện cho application/profile/label quan trọng.
- [ ] Đã xác định health check có kiểm tra local cache hay remote backend.
- [ ] Liveness và readiness có mục đích riêng.
- [ ] Readiness phản ánh khả năng phục vụ cấu hình theo SLO.
- [ ] Git/JDBC/Vault/native/composite backend có tín hiệu giám sát phù hợp.
- [ ] Có smoke test Environment cho các release/label quan trọng.
- [ ] Đã so sánh version giữa các Config Server replica.
- [ ] Có metrics về HTTP, JVM, backend latency và error rate.
- [ ] Có cảnh báo theo triệu chứng và thời gian kéo dài.
- [ ] Logs/traces không chứa secret hoặc toàn bộ cấu hình.
- [ ] Health details và management endpoints được bảo vệ.
- [ ] Có runbook điều tra DOWN, degraded và backend failover.

Theo dõi health hiệu quả cần trả lời được hai câu hỏi: Config Server còn hoạt động không, và nó có thể cung cấp đúng bộ cấu hình mà ứng dụng cần không. Actuator cùng Config Server health indicator tạo nền tảng kiểm tra; các context đại diện, Environment smoke tests, metrics backend và readiness policy giúp phát hiện lỗi có ý nghĩa vận hành. Khi phân biệt rõ liveness, readiness và độ mới của dữ liệu, đội vận hành có thể xử lý sự cố repository mà không tạo thêm gián đoạn do restart hoặc loại node sai cách.
