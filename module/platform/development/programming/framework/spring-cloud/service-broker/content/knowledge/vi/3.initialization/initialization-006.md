# Cấu hình application.yml và tách cấu hình theo môi trường

Một service broker xây dựng bằng Spring Cloud cần nhiều nhóm cấu hình để khởi động và vận hành: tên ứng dụng, cổng HTTP, kết nối cơ sở dữ liệu lưu trạng thái, địa chỉ provisioner, thời gian chờ, chính sách retry, logging, health check và thông tin xác thực. Spring Boot cho phép tập trung các giá trị này trong `application.yml`, đồng thời thay thế chúng theo từng môi trường triển khai.

Với module `SPRING_CLOUD_SERVICE_BROKER`, cấu hình cần phục vụ một broker triển khai Open Service Broker API (OSB API): platform gọi các endpoint của broker để đọc catalog, provision, update, bind, unbind và deprovision tài nguyên. Vì những thao tác này có thể chạy bất đồng bộ và phải an toàn khi retry, broker cần lưu trạng thái bền vững, gọi được hệ thống cung cấp tài nguyên và bảo vệ credential. Cấu hình vì thế phải thể hiện rõ đâu là thiết lập chung, đâu là khác biệt theo môi trường và đâu là bí mật cần được cấp từ hệ thống triển khai.

## 1. Vai trò của application.yml

Spring Boot tự động nạp cấu hình từ các nguồn như file `application.properties`, `application.yml`, biến môi trường, tham số JVM và tham số dòng lệnh. YAML phù hợp khi cấu hình có cấu trúc lồng nhau, ví dụ nhóm `spring.datasource`, `management` và nhóm cấu hình nghiệp vụ riêng của broker.

Một cấu trúc dự án thường có dạng:

```text
src/main/resources/
  application.yml
  application-local.yml
  application-dev.yml
  application-staging.yml
  application-prod.yml
```

`application.yml` chứa những thiết lập dùng chung và các giá trị bắt buộc phải được cung cấp từ môi trường. Các file có hậu tố profile như `application-local.yml` hoặc `application-prod.yml` chỉ chứa phần khác biệt của profile tương ứng. Spring Boot hợp nhất các nguồn cấu hình; giá trị từ nguồn có độ ưu tiên cao hơn sẽ ghi đè giá trị thấp hơn.

Ví dụ, `server.port` có thể được đặt trong `application.yml` với giá trị mặc định, sau đó môi trường triển khai ghi đè bằng biến `SERVER_PORT`. Tương tự, `broker.provisioner.base-url` có thể được cấu hình khác nhau cho máy phát triển, môi trường kiểm thử và production.

## 2. Phân loại cấu hình của service broker

Trước khi viết YAML, nên phân loại các giá trị theo mục đích và mức độ nhạy cảm.

| Nhóm | Ví dụ | Cách quản lý |
|---|---|---|
| Nhận dạng ứng dụng | `spring.application.name` | Thường dùng chung giữa các môi trường. |
| HTTP server | `server.port`, graceful shutdown | Có thể dùng mặc định và ghi đè khi triển khai. |
| Kết nối lưu trạng thái | JDBC URL, pool size, timeout | URL và giới hạn pool theo môi trường; tài khoản lấy từ secret. |
| Provisioner | Base URL, connect timeout, read timeout | Endpoint thay đổi theo môi trường; timeout được kiểm soát rõ ràng. |
| Vòng đời operation | Retry, thời gian chờ, lịch polling | Đặt giá trị có giới hạn để thao tác async không chạy vô hạn. |
| Quan sát hệ thống | Log level, health endpoint, metrics | Production chỉ mở các endpoint cần thiết và bảo vệ truy cập. |
| Bảo mật | Mật khẩu DB, credential gọi provider, khóa ký | Cấp từ secret manager, biến môi trường hoặc mounted secret. |

Không phải mọi giá trị đều nên nằm trong YAML. Tên service và plan của catalog là dữ liệu nghiệp vụ của broker. Tùy phiên bản và cách tích hợp Spring Cloud Open Service Broker, catalog có thể được tạo bằng API hoặc bean Java. Không nên tự đặt một khóa YAML tùy ý rồi giả định thư viện sẽ tự động hiểu nó; chỉ dùng các thuộc tính mà phiên bản thư viện đang sử dụng thực sự hỗ trợ. Các thông số vận hành riêng của ứng dụng có thể được đặt dưới prefix do nhóm phát triển định nghĩa, chẳng hạn `broker.*`, rồi bind vào một lớp `@ConfigurationProperties`.

## 3. File application.yml dùng chung

Ví dụ sau minh họa một broker dùng PostgreSQL để lưu trạng thái instance, binding và operation, đồng thời gọi một provisioner nội bộ. Tên `broker.*` là prefix cấu hình do ứng dụng tự định nghĩa; các khóa `spring.*`, `server.*` và `management.*` là nhóm cấu hình Spring Boot.

```yaml
spring:
  application:
    name: spring-cloud-service-broker

  datasource:
    url: ${BROKER_DB_URL}
    username: ${BROKER_DB_USERNAME}
    password: ${BROKER_DB_PASSWORD}
    hikari:
      maximum-pool-size: ${BROKER_DB_POOL_SIZE:10}
      connection-timeout: 30000

server:
  port: ${SERVER_PORT:8080}
  shutdown: graceful

spring.lifecycle:
  timeout-per-shutdown-phase: 30s

broker:
  provisioner:
    base-url: ${PROVISIONER_BASE_URL}
    connect-timeout: 2s
    read-timeout: 30s
  operations:
    max-attempts: 3
    retry-delay: 5s
    timeout: 15m

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true

logging:
  level:
    root: INFO
    org.springframework: INFO
```

Một số điểm cần chú ý:

- `spring.application.name` định danh ứng dụng trong log, tracing và các tích hợp của hệ sinh thái Spring.
- `spring.datasource.*` chỉ cần thiết nếu broker dùng JDBC để lưu trạng thái hoặc dữ liệu nghiệp vụ. Nếu dùng một kho dữ liệu khác, hãy cấu hình đúng client tương ứng thay vì giữ cấu hình datasource không sử dụng.
- `server.port` cho phép nền tảng triển khai quyết định cổng HTTP qua biến môi trường. Broker cần được đặt sau ingress hoặc load balancer có TLS khi triển khai thực tế.
- `spring.lifecycle.timeout-per-shutdown-phase` cho phép các thành phần có thời gian đóng kết nối và hoàn tất giai đoạn shutdown. Giá trị này cần phù hợp với thời gian dừng của container và quy trình triển khai.
- `broker.provisioner.*` và `broker.operations.*` là cấu hình riêng của ứng dụng. Các giá trị timeout và retry phải hữu hạn để worker không giữ tài nguyên vô thời hạn.
- `management.endpoints.web.exposure.include` chỉ công bố `health` và `info` qua web. Không mở rộng các endpoint nhạy cảm như `env`, `configprops` hoặc `beans` ra mạng công khai.

Các placeholder `${TEN_BIEN}` yêu cầu biến môi trường tương ứng phải tồn tại. Placeholder `${TEN_BIEN:gia-tri}` cung cấp giá trị mặc định khi biến chưa được thiết lập. Chỉ dùng mặc định cho giá trị không nhạy cảm hoặc cấu hình phát triển có chủ đích; không đặt mật khẩu production hay khóa truy cập mặc định trong file dùng chung.

## 4. Tách cấu hình theo Spring Profile

Spring Profile cho phép chọn tập cấu hình theo môi trường mà không cần thay đổi mã nguồn. Ví dụ:

- `local`: chạy trên máy phát triển, kết nối database cục bộ và provisioner giả lập.
- `dev`: tích hợp với dịch vụ phát triển dùng chung.
- `staging`: gần với production để kiểm tra trước khi phát hành.
- `prod`: sử dụng endpoint, tài nguyên và secret của môi trường thật.

File `application-local.yml` có thể cung cấp giá trị tiện dụng cho môi trường phát triển:

```yaml
spring:
  datasource:
    url: ${BROKER_DB_URL:jdbc:postgresql://localhost:5432/service_broker}
    username: ${BROKER_DB_USERNAME:broker_local}
    password: ${BROKER_DB_PASSWORD:local-only-password}

broker:
  provisioner:
    base-url: ${PROVISIONER_BASE_URL:http://localhost:8081}
  operations:
    max-attempts: 2
    retry-delay: 2s
```

Các giá trị mặc định trong file này chỉ dành cho môi trường local dùng dữ liệu thử nghiệm. Không tái sử dụng mật khẩu mẫu hoặc endpoint giả lập trong môi trường có dữ liệu thật.

File `application-prod.yml` chỉ ghi đè những giá trị cần điều chỉnh cho production:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 30

server:
  shutdown: graceful

broker:
  operations:
    max-attempts: 5
    retry-delay: 10s
    timeout: 30m

logging:
  level:
    root: INFO
```

Endpoint provisioner và thông tin database của production tiếp tục được cung cấp qua biến môi trường hoặc secret store. Khi file profile không khai báo một thuộc tính, Spring Boot dùng giá trị đã được nạp từ cấu hình chung hoặc nguồn cấu hình khác.

Chọn profile khi khởi động:

```bash
# Linux/macOS
SPRING_PROFILES_ACTIVE=local ./mvnw spring-boot:run

# Windows PowerShell
$env:SPRING_PROFILES_ACTIVE = "local"
./mvnw spring-boot:run
```

Trong container, có thể đặt `SPRING_PROFILES_ACTIVE=prod` qua cấu hình triển khai. Không nên cố định `spring.profiles.active: prod` trong `application.yml` vì như vậy artifact khó được tái sử dụng giữa các môi trường và có thể vô tình khởi động sai profile.

## 5. Bind cấu hình riêng của broker bằng @ConfigurationProperties

Các thuộc tính tùy chỉnh nên được gom vào một lớp có kiểu dữ liệu thay vì đọc rải rác bằng `@Value`. `@ConfigurationProperties` hỗ trợ relaxed binding, cấu trúc lồng nhau, chuyển đổi kiểu `Duration` và kiểm tra hợp lệ.

Ví dụ với Spring Boot 3 và Jakarta Validation:

```java
package com.example.broker.config;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import java.net.URI;
import java.time.Duration;

@Validated
@ConfigurationProperties(prefix = "broker")
public record BrokerProperties(
        @Valid @NotNull Provisioner provisioner,
        @Valid @NotNull Operations operations
) {
    public record Provisioner(
            @NotNull URI baseUrl,
            @NotNull Duration connectTimeout,
            @NotNull Duration readTimeout
    ) {}

    public record Operations(
            @Min(1) int maxAttempts,
            @NotNull Duration retryDelay,
            @NotNull Duration timeout
    ) {}
}
```

Đăng ký lớp cấu hình bằng `@ConfigurationPropertiesScan` trên lớp ứng dụng hoặc `@EnableConfigurationProperties(BrokerProperties.class)` trong một lớp cấu hình:

```java
package com.example.broker;

import com.example.broker.config.BrokerProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ServiceBrokerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServiceBrokerApplication.class, args);
    }
}
```

Với YAML ở phần trước, Spring Boot bind `broker.provisioner.base-url` vào `Provisioner.baseUrl`, `broker.operations.max-attempts` vào `Operations.maxAttempts` và các chuỗi `2s`, `30s`, `15m` thành `Duration`. Nếu URL sai định dạng, thuộc tính bắt buộc bị thiếu hoặc số lần thử nhỏ hơn 1, ứng dụng có thể thất bại ngay khi khởi động. Fail-fast giúp phát hiện cấu hình sai trước khi broker nhận request từ platform.

Nếu dự án dùng Spring Boot 2, cần đối chiếu phiên bản thư viện và dùng namespace validation tương ứng (`javax.validation` thay cho `jakarta.validation` ở các phiên bản phù hợp). Không sao chép nguyên import của Boot 3 vào dự án Boot 2.

## 6. Biến môi trường và quy tắc ánh xạ tên

Spring Boot hỗ trợ relaxed binding giữa tên thuộc tính dạng kebab-case và tên biến môi trường viết hoa. Quy tắc thực hành phổ biến là đổi dấu chấm thành dấu gạch dưới, bỏ dấu gạch ngang và viết hoa toàn bộ:

| Thuộc tính | Biến môi trường |
|---|---|
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `server.port` | `SERVER_PORT` |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` |
| `broker.provisioner.base-url` | `BROKER_PROVISIONER_BASEURL` |
| `broker.operations.max-attempts` | `BROKER_OPERATIONS_MAXATTEMPTS` |

Với các thuộc tính có dấu gạch ngang, relaxed binding của Spring Boot loại bỏ dấu gạch ngang khi tạo tên biến môi trường. Vì vậy `base-url` ánh xạ thành `BASEURL`, không phải `BASE_URL`. Đối với biến do tổ chức tự đặt tên như `PROVISIONER_BASE_URL`, có thể tham chiếu trực tiếp bằng placeholder `${PROVISIONER_BASE_URL}` trong YAML rồi bind vào thuộc tính `broker.provisioner.base-url`.

Ví dụ cấu hình khi chạy container:

```bash
SPRING_PROFILES_ACTIVE=prod
SERVER_PORT=8080
BROKER_DB_URL=jdbc:postgresql://postgres.internal:5432/service_broker
BROKER_DB_USERNAME=service_broker
PROVISIONER_BASE_URL=https://provisioner.internal
```

Không đưa giá trị mật khẩu vào lệnh shell được lưu trong lịch sử terminal hoặc pipeline log. Hãy cấp `BROKER_DB_PASSWORD` từ secret store của nền tảng triển khai.

## 7. Quản lý secret và cấu hình nhạy cảm

Broker có thể cần mật khẩu database, credential gọi API của nhà cung cấp tài nguyên, token hoặc khóa mã hóa. Các giá trị này không nên được commit vào Git, ghi trực tiếp trong `application.yml`, đóng gói vào image hay ghi vào log.

Có một số cách phổ biến để cấp secret:

1. **Secret manager của nền tảng:** pipeline hoặc workload lấy secret từ hệ thống quản lý bí mật và cấp cho process/container theo quyền tối thiểu.
2. **Biến môi trường:** phù hợp với nhiều nền tảng triển khai; cần kiểm soát quyền đọc cấu hình process và tránh in toàn bộ environment ra log.
3. **Mounted secret/config tree:** nền tảng mount mỗi giá trị thành một file, ứng dụng import thư mục đó bằng `spring.config.import`.

Ví dụ import một thư mục secret dạng config tree:

```yaml
spring:
  config:
    import: optional:configtree:/run/secrets/
```

Nếu trong `/run/secrets/` có file tên `spring.datasource.password`, nội dung file được nạp như giá trị của thuộc tính tương ứng. Từ khóa `optional:` cho phép ứng dụng khởi động khi thư mục không tồn tại; chỉ dùng nó khi môi trường đó thực sự không yêu cầu secret này. Production cần kiểm tra secret bắt buộc có mặt và hợp lệ trước khi nhận traffic.

Khi dùng Kubernetes, ConfigMap phù hợp với cấu hình không nhạy cảm như endpoint hoặc giới hạn timeout; Secret phù hợp với credential. Cần giới hạn RBAC, quyền mount, quyền đọc và bật cơ chế bảo vệ dữ liệu secret theo chính sách của cluster. Với Cloud Foundry hoặc nền tảng tương tự, cấp biến cấu hình và secret qua cơ chế environment/service binding được nền tảng hỗ trợ. Cách phân phối khác nhau nhưng ứng dụng vẫn nên đọc cấu hình qua Spring Environment hoặc `@ConfigurationProperties`.

Một file `.env` không được Spring Boot tự động nạp chỉ vì nó nằm cạnh `pom.xml` hoặc `application.yml`. Nếu dùng `.env`, cần có công cụ chạy local hoặc thư viện tích hợp chủ động nạp file đó. Không nhầm hành vi của Docker Compose, shell hoặc IDE với hành vi mặc định của Spring Boot.

## 8. Thứ tự ưu tiên và cách tránh cấu hình bị ghi đè

Spring Boot hợp nhất cấu hình từ nhiều property source. Trong vận hành, các nguồn như file YAML, file profile, biến môi trường, system property và tham số dòng lệnh có thể cùng khai báo một khóa. Nguồn có độ ưu tiên cao hơn sẽ quyết định giá trị cuối cùng.

Ví dụ `application.yml` khai báo:

```yaml
server:
  port: 8080
```

nhưng container được chạy với `SERVER_PORT=9090`, server sẽ dùng cổng 9090. Đây là cơ chế hữu ích để dùng cùng một artifact cho nhiều môi trường, nhưng cũng dễ gây nhầm nếu pipeline vô tình giữ biến môi trường cũ.

Khi điều tra cấu hình sai, hãy kiểm tra theo trình tự:

1. Xác nhận profile thực sự đang active.
2. Kiểm tra file cấu hình chung và file profile được nạp.
3. Kiểm tra biến môi trường và system properties của process.
4. Kiểm tra tham số command line hoặc cấu hình do nền tảng inject.
5. Xác minh kiểu dữ liệu, placeholder, secret mount và quyền đọc file.

Không bật endpoint Actuator `env` hoặc `configprops` công khai chỉ để debug. Nếu cần xem cấu hình đã bind, hãy dùng môi trường kiểm thử, quyền truy cập hạn chế và che giá trị nhạy cảm. Với lỗi khởi động, ưu tiên thông báo validation có tên thuộc tính và nguồn cấu hình mà không in giá trị secret.

## 9. Cấu hình phù hợp với vòng đời OSB API

Cấu hình broker ảnh hưởng trực tiếp tới độ tin cậy của các thao tác OSB API:

- **Provision:** timeout kết nối và timeout xử lý provider phải phù hợp với khả năng tạo tài nguyên. Nếu công việc kéo dài, broker ghi operation bền vững và trả phản hồi async theo hợp đồng; không tăng HTTP timeout vô hạn.
- **Update:** giới hạn retry và timeout cần cho phép worker phục hồi khi provider tạm lỗi, đồng thời tránh áp dụng lặp cấu hình không idempotent.
- **Bind/unbind:** cấu hình credential provider và chính sách bảo mật phải đủ để tạo hoặc thu hồi quyền truy cập cho từng binding. Không dùng một secret chung làm credential cho tất cả ứng dụng.
- **Deprovision:** worker phải có đủ quyền thu hồi tài nguyên; timeout và retry phải xử lý được trường hợp provider đã xóa tài nguyên nhưng phản hồi bị mất.
- **Last operation:** kho trạng thái phải bền vững để endpoint polling đọc được trạng thái sau khi process restart hoặc request được chuyển sang instance broker khác.

Các giá trị `max-attempts`, `retry-delay` và `timeout` trong ví dụ là tham số minh họa. Hãy chọn chúng dựa trên SLA của provider, giới hạn rate, thời gian provisioning thực tế và cách triển khai worker. Retry quá nhanh có thể gây quá tải provider; timeout quá ngắn có thể đánh dấu sai một operation vẫn đang chạy.

Không lưu trạng thái operation chỉ trong biến static hoặc bộ nhớ của một instance ứng dụng nếu broker chạy nhiều replica. Khi platform gửi request tới replica khác để polling, replica đó vẫn phải đọc được cùng trạng thái từ kho lưu trữ dùng chung.

## 10. Kiểm tra cấu hình trước khi nhận traffic

Một broker nên xác minh cấu hình ngay trong giai đoạn khởi động:

- Các thuộc tính bắt buộc như URL database và provisioner có tồn tại và đúng định dạng.
- Timeout dương và có giới hạn; số lần retry không nhỏ hơn 1.
- Profile production được chọn đúng; không vô tình bật profile local.
- Secret bắt buộc được cấp và process có quyền đọc.
- Kết nối database và các dependency quan trọng có thể được kiểm tra bằng startup validation hoặc readiness probe.
- Health endpoint chỉ tiết lộ trạng thái cần thiết và không trả thông tin credential hoặc topology nhạy cảm.
- Log level production không bật DEBUG/TRACE cho request chứa token hoặc thông tin kết nối.

Ví dụ, nếu `BROKER_DB_URL` không được cấp, placeholder `${BROKER_DB_URL}` sẽ khiến cấu hình không thể resolve và ứng dụng thất bại khi khởi động. Đây là kết quả phù hợp cho một dependency bắt buộc: broker không nên nhận lệnh provision khi không thể lưu trạng thái vòng đời một cách bền vững.

Trong pipeline, nên kiểm tra tối thiểu việc ứng dụng khởi động được với cấu hình kiểm thử, các thuộc tính bắt buộc được bind đúng và profile mong muốn được chọn. Không cần đưa secret production vào bước build image; secret chỉ nên xuất hiện ở runtime với quyền tối thiểu.

## 11. Ví dụ triển khai trên Kubernetes và Cloud Foundry

### Kubernetes

Một triển khai Kubernetes thường tách cấu hình không nhạy cảm và bí mật:

- ConfigMap chứa `SPRING_PROFILES_ACTIVE=prod`, `PROVISIONER_BASE_URL`, pool size và timeout.
- Secret hoặc secret manager cung cấp `BROKER_DB_USERNAME`, `BROKER_DB_PASSWORD` và credential provider.
- Deployment inject giá trị vào container qua `env`, `envFrom` hoặc mount file secret.
- Readiness/liveness probe gọi endpoint health phù hợp; service chỉ chuyển traffic tới pod đã sẵn sàng.

Minh họa phần cấu hình container (các tên ConfigMap/Secret là ví dụ):

```yaml
env:
  - name: SPRING_PROFILES_ACTIVE
    value: prod
  - name: PROVISIONER_BASE_URL
    valueFrom:
      configMapKeyRef:
        name: service-broker-config
        key: provisioner-base-url
  - name: BROKER_DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: service-broker-secrets
        key: database-password
```

### Cloud Foundry

Với Cloud Foundry, ứng dụng broker có thể nhận profile và các biến cấu hình từ manifest hoặc cơ chế environment của platform. Credential nên được cấp qua cơ chế quản lý service credential hoặc secret mà tổ chức sử dụng. Cần phân biệt hai luồng: cấu hình của chính ứng dụng broker khi nó chạy trên Cloud Foundry, và các request OSB API mà broker nhận từ platform để provision dịch vụ cho ứng dụng khác.

Trong cả hai trường hợp, artifact của broker có thể giữ nguyên giữa các môi trường. Mỗi môi trường cung cấp profile, endpoint và secret riêng lúc triển khai; nhờ vậy việc chuyển từ dev sang staging rồi production không đòi hỏi sửa source code hoặc đóng gói lại ứng dụng chỉ để đổi URL.

## 12. Lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ứng dụng không khởi động vì placeholder | Thiếu biến môi trường hoặc secret mount | Kiểm tra tên biến, profile và quyền đọc secret. |
| Broker gọi nhầm provisioner | Profile không đúng hoặc biến môi trường ghi đè URL | Xác nhận profile active và nguồn cấu hình cuối cùng. |
| Kết nối DB thất bại | JDBC URL, DNS, credential hoặc network policy sai | Kiểm tra URL, secret, DNS và quyền truy cập mạng. |
| Worker retry liên tục | Retry delay quá ngắn hoặc provider lỗi kéo dài | Đặt giới hạn retry, backoff và timeout; bổ sung quan sát operation. |
| Polling trả trạng thái không nhất quán | Trạng thái chỉ lưu trong memory của một replica | Dùng kho trạng thái bền vững và dùng chung. |
| Secret xuất hiện trong log | Log toàn bộ Environment, request hoặc exception | Che dữ liệu nhạy cảm và giảm phạm vi log. |
| Profile local chạy trên production | Profile bị đặt cứng hoặc pipeline inject nhầm | Đặt profile tại runtime và kiểm tra trong bước triển khai. |

## 13. Checklist cấu hình cho một môi trường mới

1. Chọn profile và xác nhận profile đó không chứa cấu hình của môi trường khác.
2. Cấp endpoint database và provisioner qua cấu hình runtime.
3. Cấp username, password, token và khóa qua secret store.
4. Đặt pool size, timeout, retry và giới hạn worker theo tải dự kiến.
5. Bật health/readiness endpoint cần thiết và giới hạn quyền truy cập.
6. Khởi động thử, kiểm tra validation và kết nối dependency.
7. Xác nhận broker có thể lưu operation bền vững và polling hoạt động qua nhiều replica.
8. Kiểm tra log không chứa secret và profile production được chọn đúng.

Khi cấu hình được phân lớp như vậy, `application.yml` mô tả nền tảng chung của ứng dụng, Spring Profile mô tả khác biệt giữa các môi trường, còn secret store cung cấp thông tin nhạy cảm tại thời điểm chạy. Service broker có thể được triển khai nhất quán trên máy phát triển, Cloud Foundry hoặc Kubernetes trong khi vẫn kết nối đúng database và provisioner, quản lý operation bền vững và bảo vệ credential trong toàn bộ vòng đời OSB API.
