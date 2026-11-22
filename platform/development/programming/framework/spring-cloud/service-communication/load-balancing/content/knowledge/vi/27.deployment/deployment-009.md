# Quản lý cấu hình theo môi trường và bí mật kết nối

Một ứng dụng Spring Boot dùng **Spring Cloud LoadBalancer** thường phải hoạt động trong nhiều môi trường: **development**, **testing**, **staging** và **production**. Code nghiệp vụ của Order Service có thể luôn gọi **http://inventory-service/api/stock/{sku}**, nhưng cách tìm bản sao, giới hạn timeout, chính sách retry, vùng triển khai, TLS/mTLS và thông tin xác thực tới Inventory Service lại phụ thuộc môi trường.

Nếu đưa trực tiếp **địa chỉ host production, mật khẩu, API key, client secret hoặc private key** vào source code hay application.yml được commit lên Git, mỗi lần triển khai sẽ rủi ro hơn. Nếu chỉnh cấu hình thủ công trên từng pod, các bản sao của cùng một dịch vụ có thể dùng chính sách khác nhau và phát sinh lỗi 401/403, TLS handshake, 503 hoặc sai service ID. Giải pháp là thiết kế **hợp đồng cấu hình**, xác định **nguồn và thứ tự ưu tiên**, tách **bí mật khỏi giá trị công khai**, và kiểm chứng trạng thái cuối cùng ngay trong pipeline triển khai.

Trong bài thuộc chương **Triển khai** của module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**, chúng ta sẽ quản lý cấu hình theo môi trường cho **RestClient, WebClient, OpenFeign và Spring Cloud LoadBalancer**, bao gồm discovery, health check, cache, retry/timeout, SSL bundles, OAuth2/API key, Kubernetes ConfigMap/Secret, Spring Cloud Config, kiểm thử, đổi phiên bản cấu hình và rollback.

**Giới hạn:** Các đoạn YAML, Java và Kubernetes manifests là ví dụ để học; hostname, đường dẫn và số timeout đều là dữ liệu minh họa. Không có thông tin xác thực thực nào trong bài. Các phiên bản Spring Boot, Spring Cloud và HTTP engines cần được chọn theo BOM tương thích của dự án; một cấu hình trên Spring Cloud LoadBalancer không mặc nhiên kích hoạt cùng hành vi ở mọi HTTP client.

## 1. Phân biệt cấu hình vận hành và bí mật kết nối

**Cấu hình vận hành** là những giá trị quyết định ứng dụng chạy thế nào: service ID, timeout, cache TTL, lựa chọn thuật toán, URL hệ thống phụ trợ, tên zone hoặc profile.

**Bí mật kết nối** là dữ liệu cấp quyền truy cập hoặc chứng minh danh tính: OAuth2 client secret, API key, mật khẩu, private key mTLS, refresh token và credentials để đọc secret/config store.

| Giá trị | Nhóm | Ví dụ | Có nên commit vào Git? |
| --- | --- | --- | --- |
| Spring application name | Cấu hình | order-service | Có |
| Logical service ID | Cấu hình | inventory-service | Có |
| Connect/read timeout | Cấu hình | 500 ms / 2 s | Có |
| LoadBalancer cache TTL | Cấu hình | 35s hoặc giá trị đã đo | Có |
| Discovery provider URL không có credentials | Cấu hình | https://registry.internal | Tùy chính sách hạ tầng |
| Zone của caller | Cấu hình | zone-a | Có nếu không nhạy cảm |
| OAuth2 issuer URL | Cấu hình | https://identity.example.internal | Tùy mô hình bảo mật |
| OAuth2 client ID | Định danh ứng dụng | order-inventory | Thường có thể, theo policy |
| OAuth2 client secret | **Bí mật** | (không ghi giá trị thật) | **Không** |
| Inventory API key | **Bí mật** | (không ghi giá trị thật) | **Không** |
| mTLS client private key | **Bí mật** | File PEM/keystore được bảo vệ | **Không** |
| Server CA public certificate | Vật liệu tin cậy | inventory-ca.pem | Có thể, nhưng cần quản lý vòng đời |
| Truststore password | **Bí mật nếu có** | Secret store | **Không** |

**Một URL chứa username/password hoặc token trong query string vẫn là bí mật.** Đừng cho rằng URL luôn là cấu hình công khai. Mật khẩu cũng không an toàn chỉ vì được mã hóa Base64 trong Kubernetes Secret: Base64 là mã hóa biểu diễn, không phải encryption.

### 1.1. Bốn nguyên tắc

1. **Build once, deploy many:** cùng một artifact/image được đẩy qua các môi trường; cấu hình đến từ runtime/deployment.
2. **Least privilege:** từng ứng dụng chỉ đọc secret và service endpoints thật sự cần.
3. **Fail closed đối với bí mật bắt buộc:** thiếu secret quan trọng phải được phát hiện sớm, không âm thầm gọi HTTP không xác thực.
4. **Có nguồn gốc và phiên bản:** biết một pod đang chạy **image revision + config revision + secret generation** nào.

Thay đổi secret không nhất thiết là thay đổi code; thay đổi chính sách cache/timeout không nhất thiết là thay đổi image. Nhưng cả hai đều cần quy trình kiểm tra và rollback phù hợp.

## 2. Cấu hình nằm ở đâu trên đường gọi service-to-service?

~~~mermaid
flowchart TD
    A["Application image: Spring Boot + Spring Cloud"] --> B["Spring Environment / Config Data"]
    C["Profile dev/staging/prod"] --> B
    D["ConfigMap / Config Server"] --> B
    E["Secret volume / Secret Manager"] --> F["Credential provider / SSL context"]
    B --> G["HTTP client settings: timeout, retry, SSL bundle refs"]
    B --> H["Discovery + ServiceInstanceListSupplier"]
    B --> I["LB cache/health/zone/algorithm"]
    H --> J["Spring Cloud LoadBalancer chọn instance"]
    I --> J
    J --> G
    F --> G
    G --> K["RestClient / WebClient / OpenFeign HTTP request"]
    K --> L["Inventory instance"]
~~~

Điểm quan trọng: **Spring Cloud LoadBalancer chỉ chọn ServiceInstance theo service ID**. Nó không tự quản lý private key, OAuth2 token, mật khẩu hoặc bảo mật đường truyền. Một lời gọi như **http://inventory-service/...** có thể được tái dựng thành **http://10.2.0.18:8080/...**; nếu dùng HTTPS/mTLS, HTTP transport phải có trust/key material phù hợp với hostname và TLS peer identity thực.

### 2.1. Chia trách nhiệm theo lớp

| Lớp | Thứ cần cấu hình | Ai thực thi? |
| --- | --- | --- |
| Spring Boot Config Data | Profiles, files, env vars, configtree import | Environment / Binder |
| Discovery | Registry endpoint, credentials, namespace, danh sách instance | DiscoveryClient / ReactiveDiscoveryClient |
| LoadBalancer | Supplier chain, Round Robin/Random, health, zone, cache TTL | Spring Cloud LoadBalancer |
| HTTP transport | Connect/response/read timeout, connection pool, TLS | Apache HC5, Reactor Netty, JDK client... |
| HTTP auth | API key, OAuth2 bearer, mTLS identity | Interceptor/filter/authorized client manager |
| Deployment | ConfigMap, Secret mount, RBAC, rollout/restart | Kubernetes/CI-CD/secret provider |
| Observability | Request errors, latency, selected instance, config generation | Actuator, Micrometer, tracing, logs |

**Không trộn trách nhiệm:** đặt **spring.cloud.loadbalancer.retry.enabled** không tự đặt mọi HTTP transport timeout; thêm **@LoadBalanced** không tự bảo đảm đã có TLS/mTLS; cập nhật Kubernetes Secret cũng không mặc định làm RestClient/WebClient/Feign đang chạy đọc lại credential.

## 3. Thiết kế một hợp đồng cấu hình trước khi triển khai

Một bảng hợp đồng giúp các nhóm dev/ops/security hiểu mỗi giá trị đến từ đâu:

| Key/cấu hình | Mục đích | Nguồn được phép | Có nhạy cảm? | Áp dụng thay đổi |
| --- | --- | --- | --- | --- |
| spring.application.name | Định danh ứng dụng | application.yml | Không | Khởi động lại |
| spring.profiles.active | Chọn môi trường | Deployment/CLI | Không | Khởi động lại |
| app.inventory.service-id | Dịch vụ đích logic | Profile/ConfigMap | Không | Khởi động lại theo thiết kế |
| spring.cloud.loadbalancer.zone | Zone preference của caller | Deployment metadata | Không/nhạy cảm tùy tổ chức | Tùy lifecycle |
| spring.cloud.loadbalancer.cache.ttl | Cache danh sách instance | Profile/ConfigMap | Không | Thường restart nếu không có refresh đã test |
| spring.cloud.loadbalancer.retry.* | Retry policy | Profile/ConfigMap | Không | Tùy HTTP client/bean lifecycle |
| app.inventory.response-timeout | Timeout ứng dụng đặt cho transport | Profile/ConfigMap | Không | Tạo lại HTTP client khi config đổi |
| app.inventory.api-key | API key Inventory | Secret volume/Secret Manager | **Có** | Provider refresh hoặc restart |
| spring.security.oauth2.client.registration...client-secret | OAuth2 client secret | Secret Manager/configtree | **Có** | Thường cần thay credentials/restart |
| spring.ssl.bundle.pem...private-key | mTLS private key | Protected secret file | **Có** | Consumer-dependent; test hoặc restart |
| SPRING_CONFIG_IMPORT | Nguồn cấu hình bắt buộc | Deployment | Không nếu không chứa credentials | Startup |

Tại thời điểm rollout, nên có **config contract version** và **schema kiểm tra**: nếu một deployment thiếu credential bắt buộc, dùng sai service ID hoặc đặt retry count ngoài giới hạn, phải báo lỗi trong pipeline hoặc tại startup thay vì đợi production traffic thất bại.

### 3.1. Không dùng một biến môi trường “chứa tất cả”

Ví dụ phản mẫu:

~~~text
APP_CONFIG=inventory_url=http://...;password=...;retry=10;tls=false
~~~

Chuỗi cấu hình tự định nghĩa kiểu này khó validate, khó kiểm soát quyền xem, dễ ghi lộ vào log và dễ phát sinh precedence bất nhất. Hãy dùng **@ConfigurationProperties** cho giá trị thường và **secret provider** cho credential. Nếu dùng SPRING_APPLICATION_JSON, hiểu rõ đó vẫn là môi trường chứa dữ liệu có thể bị lộ qua công cụ vận hành.

## 4. Spring Boot ưu tiên các nguồn cấu hình theo quy tắc nào?

Spring Boot đọc nhiều **PropertySource**. Không tồn tại một quy tắc đơn giản “YAML luôn thắng env var” hoặc “profile luôn thắng command line”.

Một số quy tắc trọng tâm:

| Nguồn | Ví dụ | So sánh thường gặp |
| --- | --- | --- |
| Default properties | SpringApplication defaults | Ưu tiên thấp |
| Config Data đóng gói trong JAR | application.yml | Mức nền |
| Profile-specific Config Data | application-prod.yml | Thường ghi đè bản không theo profile cùng vị trí |
| Config Data ngoài JAR | /config/application.yml | Có thể ghi đè config đóng gói, theo location group |
| Operating system environment variables | SPRING_PROFILES_ACTIVE | Thường ghi đè Config Data |
| Java system properties | -D... | Ưu tiên cao hơn env vars trong thứ tự chuẩn |
| Command-line arguments | --server.port=... | Ưu tiên cao hơn file-based config theo mặc định |
| SPRING_APPLICATION_JSON | JSON trong environment/system property | Có thứ tự riêng trong chuỗi property sources |

**Thứ tự đầy đủ** bao gồm test properties, devtools và các nguồn khác; không nên dựa hoàn toàn vào bảng rút gọn khi nhiều nhóm config cùng khai báo một key. Spring Boot Reference có danh sách PropertySource order chính thức.

### 4.1. Profile-specific file

Giả sử:

~~~yaml
# application.yml — cấu hình chung, không có secret
spring:
  application:
    name: order-service
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s

app:
  inventory:
    service-id: inventory-service
    response-timeout: 2s
~~~

Và:

~~~yaml
# application-prod.yml — chỉ các giá trị khác với mặc định
app:
  inventory:
    response-timeout: 1s

spring:
  cloud:
    loadbalancer:
      cache:
        ttl: 20s
~~~

Khi profile **prod** active, **app.inventory.response-timeout=1s** và **cache.ttl=20s** trong cấu hình này, trừ khi một PropertySource có mức ưu tiên cao hơn ghi đè.

**Không dùng profile để giấu secret**: application-prod.yml nằm trong source/JAR vẫn có thể bị người đọc artifact truy cập. Profile chỉ quyết định **nhóm cấu hình**, không cấp khả năng encryption hoặc least privilege.

### 4.2. Environment variables và relaxed binding

Spring Boot có relaxed binding. Ví dụ:

~~~text
SPRING_PROFILES_ACTIVE=prod
SPRING_CLOUD_LOADBALANCER_CACHE_TTL=20s
APP_INVENTORY_RESPONSE_TIMEOUT=1s
~~~

Các biến được ánh xạ đến properties tương ứng trong nhiều trường hợp chuẩn. Với tên có dấu gạch ngang, index của list, map keys hoặc các key viết hoa, cần xem quy tắc **Binding From Environment Variables** trong Spring Boot Reference; đừng tự phát minh quy tắc thay thế mọi ký tự bằng dấu gạch dưới.

### 4.3. Vì sao phải biết nguồn cuối cùng?

Khi **application-prod.yml** ghi timeout 1s nhưng deployment inject **APP_INVENTORY_RESPONSE_TIMEOUT=5s**, kết quả có thể là **5s**. Debug chỉ bằng cách nhìn file Git sẽ sai. Cần quan sát nguồn cấu hình của runtime thông qua công cụ chẩn đoán **được bảo vệ và sanitization**, không dump toàn bộ Environment/Secret lên stdout.

## 5. Thiết kế profile dev, staging và prod

Một hệ thống nên có **base configuration ổn định**, sau đó thay phần thật sự phụ thuộc môi trường:

~~~text
Same JAR / same image digest
  |
  +-- dev:  SimpleDiscoveryClient + backend localhost, fake credentials
  |
  +-- test: MockWebServer/WireMock, deterministic timeouts, no production secrets
  |
  +-- staging: discovery thật, TLS và auth gần giống production
  |
  +-- prod: discovery thật, bí mật từ Secret Manager, readiness và alerting
~~~

### 5.1. Cấu hình dev với SimpleDiscoveryClient

~~~yaml
# application-dev.yml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://127.0.0.1:8091
              - uri: http://127.0.0.1:8092
    loadbalancer:
      retry:
        enabled: false
      cache:
        ttl: 10s

app:
  inventory:
    response-timeout: 3s
~~~

Ở dev, một danh sách tĩnh giúp học **Round Robin/Random**, kiểm tra RestClient, WebClient và OpenFeign mà không cần vận hành Eureka/Consul/Kubernetes discovery thật.

**Cảnh báo:** Một địa chỉ 127.0.0.1 nhìn từ bên trong container/pod là **chính container/pod đó**, không phải laptop host hay một pod khác. Không copy nguyên cấu hình localhost vào môi trường container production.

### 5.2. Cấu hình staging

~~~yaml
# application-staging.yml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 20s
      retry:
        enabled: false

app:
  inventory:
    response-timeout: 2s
~~~

Staging nên chạy với **cùng discovery provider/TLS/auth pattern** như production nếu mục tiêu là kiểm thử triển khai. Chỉ khác **credentials, namespace, service endpoints, capacity và cấu hình đã được phê duyệt**.

**Không mặc định lấy Secret production để đưa sang staging** cho tiện test. Dùng credentials riêng, scope riêng, rotation độc lập và dữ liệu thử nghiệm.

### 5.3. Cấu hình prod

~~~yaml
# application-prod.yml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
      retry:
        enabled: false

app:
  inventory:
    response-timeout: 1500ms
~~~

Các số **35s/1500ms** chỉ là ví dụ. TTL 35 giây là mặc định phổ biến trong tài liệu Spring Cloud LoadBalancer, nhưng không phải giá trị tối ưu cho mọi hệ thống. Ở production phải đo **staleness, registry refresh latency, connection timeout, retry amplification và P99** trước khi quyết định.

### 5.4. Profile không quyết định discovery implementation

Chỉ đặt **spring.profiles.active=prod** không tự làm Spring Cloud LoadBalancer biết cách tìm Pods. Discovery source phải thật sự tồn tại:

- **SimpleDiscoveryClient:** chỉ đọc instances từ config.
- **Eureka/Consul:** cần client starter, network/auth và registration/registry semantics.
- **Spring Cloud Kubernetes DiscoveryClient:** cần đúng Spring Cloud Kubernetes starter/configuration và quyền API phù hợp nếu đọc Pods/Services.
- **Kubernetes Service DNS:** có thể gọi trực tiếp một Kubernetes Service bằng HTTP client thông thường; lúc đó load balancing có thể diễn ra ở tầng Kubernetes Service/kube-proxy hoặc mesh, **không đồng nghĩa Spring Cloud LoadBalancer đang chọn từng Pod**.

**Không chồng hai tầng cân bằng tải mà không biết tác dụng:** nếu client đã chọn một Pod qua Spring Cloud LoadBalancer rồi lại đi qua một Service/gateway chọn backend khác, thông tin selected ServiceInstance có thể không trùng Pod xử lý request. Chọn mô hình triển khai có chủ đích và kiểm chứng bằng trace.

## 6. Đặt service ID và cấu hình transport vào một loại có kiểm tra

Thay vì rải nhiều **@Value** trên các lớp, dùng **@ConfigurationProperties** để gom các tham số không bí mật:

~~~java
package example.order.config;

import java.time.Duration;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.inventory")
public record InventoryClientSettings(
        @NotBlank String serviceId,
        @NotNull Duration responseTimeout) {
}
~~~

Kích hoạt binding:

~~~java
@SpringBootApplication
@EnableConfigurationProperties(InventoryClientSettings.class)
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

**Dependencies:** Spring Boot configuration processor là tùy chọn để tạo metadata IDE; để các annotation **jakarta.validation** thực sự được xử lý ở startup, bổ sung Jakarta Bean Validation implementation, thường qua **spring-boot-starter-validation** phù hợp BOM.

Khi cấu hình thiếu **app.inventory.service-id** hoặc Duration không chuyển được từ chuỗi hợp lệ, ứng dụng phải phát hiện sớm thay vì đến production mới nhận lỗi UnknownHostException hoặc request bị treo.

### 6.1. Không đưa secret vào record in log mặc định

Java **record** có **toString()** tự động. Nếu một record chứa apiKey/clientSecret, việc log object sẽ làm lộ giá trị. Để các thông số **không bí mật** trong một record và secret trong **secret provider** riêng, hoặc triển khai **toString()/logging** cẩn trọng.

Ví dụ thiết kế:

~~~text
InventoryClientSettings
  serviceId: inventory-service
  responseTimeout: PT1.5S

InventoryCredentialProvider
  getBearerToken(): hiện tại, có expiry/refresh
  getApiKey(): bí mật, KHÔNG log

InventoryTransportFactory
  create RestClient/WebClient/Feign transport từ settings + TLS material
~~~

### 6.2. Xác thực chéo thông số

Validation riêng từng field chưa đủ. Với retry/timeout:

~~~text
connectTimeout     = 500ms
responseTimeout    = 1500ms
retryAttempts      = 3
overallDeadline    = 2s
~~~

Nếu hai retries mỗi attempt đều có responseTimeout 1500ms cộng backoff, **overallDeadline=2s** có thể làm request bị hủy trước khi chạy đủ attempts. Nên có test kiểm tra **tổng ngân sách** thay vì chỉ xác nhận properties bind thành công.

## 7. Config Data import: file ngoài JAR và configuration tree

Spring Boot hỗ trợ **spring.config.import** để nhập cấu hình ngoài JAR, bao gồm **file:** và **configtree:**.

### 7.1. Một file cấu hình được mount ngoài JAR

~~~yaml
# application.yml
spring:
  config:
    import: "optional:file:/etc/order/config/overrides.yml"
~~~

Nếu overrides.yml tồn tại, các giá trị trong nó có thể ghi đè document khai báo import theo thứ tự Config Data. **optional:** có nghĩa file có thể không tồn tại mà startup vẫn tiếp tục.

**Không dùng optional cho mọi thứ**: nếu thiếu bí mật bắt buộc mà ứng dụng vẫn khởi động với cấu hình trống/default, đó có thể là lỗi an toàn. Đối với production secrets quan trọng, chủ động chọn **non-optional import** và validation.

### 7.2. Configuration tree từ các file Secret

Giả sử Kubernetes mount một volume:

~~~text
/etc/order/secrets/
  app.inventory-auth.api-key
  app.inventory-auth.client-secret
~~~

Mỗi **tên file** trở thành property key, nội dung file trở thành value. Khai báo:

~~~yaml
spring:
  config:
    import: "configtree:/etc/order/secrets/"
~~~

Sau khi import:

~~~text
app.inventory-auth.api-key     <- nội dung file app.inventory-auth.api-key
app.inventory-auth.client-secret <- nội dung file còn lại
~~~

**Không ghi thật nội dung các file lên console**. Nếu dùng file có tên khác hoặc nested directories, tên property tạo ra sẽ khác; cần kiểm tra contract với cấu hình binding.

### 7.3. Khởi tạo credential provider fail closed

Ví dụ startup provider đọc một API key **bắt buộc** từ Config Data:

~~~java
package example.order.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class InventoryCredentialConfiguration {

    @Bean
    InventoryApiKeyProvider inventoryApiKeyProvider(
            Environment environment) {
        String key = environment.getProperty(
                "app.inventory-auth.api-key");
        if (key == null || key.isBlank()) {
            throw new IllegalStateException(
                    "Inventory API key is missing");
        }
        return new InventoryApiKeyProvider(key);
    }
}
~~~

Ở đây **InventoryApiKeyProvider** là class của ứng dụng, chịu trách nhiệm giữ credential và không để lộ qua toString/log. Đoạn code thể hiện **validation ở startup**; nó **không tự hot-reload** khi nội dung file trong volume thay đổi.

Nếu cùng artifact còn chạy profile dev không có API key, nên tạo bean này dưới **@Profile("staging | prod")** hoặc cấu hình security mode rõ ràng với validation theo profile; không dùng fallback placeholder như "none" trong production.

## 8. Không nhầm configtree import với Spring Cloud Config Server

Hai cách đọc cấu hình bổ sung nhau nhưng khác nguồn:

| Cơ chế | Nguồn | Khi nào phù hợp? |
| --- | --- | --- |
| Spring Boot Config Data file | application.yml, file ngoài JAR | Config cơ bản, không phụ thuộc hệ thống từ xa |
| configtree: | Volume chứa một key mỗi file | Kubernetes Secret/CSI, password/API key hoặc PEM paths |
| Spring Cloud Config Client | Config Server qua HTTP | Quản trị tập trung, version/label/profile |
| Spring Cloud Kubernetes PropertySource | Kubernetes ConfigMaps/Secrets qua API | Khi đã chọn tích hợp Spring Cloud Kubernetes |
| Vault/Secret Manager SDK hoặc CSI | Secret system | Credentials có policy/rotation/audit chuyên dụng |

Không cần bật mọi giải pháp cùng lúc. Việc đồng thời tải Config Server, Kubernetes API, Secret Manager và nhiều local imports cho cùng một key dễ tạo precedence khó hiểu, nhiều chỗ phải có credential và các phụ thuộc startup dạng vòng tròn.

## 9. Spring Cloud Config Server: tập trung cấu hình nhưng không nhúng bí mật vào URL

Khi nhiều microservices chia sẻ cấu hình vận hành, Spring Cloud Config Server có thể cung cấp **Config Data theo application, profile và label**. Trên client thêm starter phù hợp và cấu hình import:

~~~yaml
# application-prod.yml — sử dụng khi đã có Spring Cloud Config Client starter
spring:
  config:
    import: "configserver:https://config.internal.example"
  cloud:
    config:
      label: release-2026-11
~~~

**Không có optional:** client sẽ thất bại khi không truy cập được Config Server tại bước tải Config Data (theo cơ chế import). Nếu cấu hình đó chỉ là tối ưu không bắt buộc, có thể chọn **optional:configserver:** và validation phù hợp, nhưng **không fallback âm thầm sang một cấu hình production không an toàn**.

### 9.1. Tách endpoint, credential và trust

~~~text
Config Server URL:     https://config.internal.example
Client authorization:  workload identity / mTLS / credential riêng
TLS trust:             CA/truststore theo hạ tầng
Application config:    service ID, timeout, cache/health/zone policies
Inventory credential:  vẫn ở Secret Manager / Secret volume
~~~

Nếu có thể, dùng **workload identity**, mTLS hoặc mechanism cấp quyền đã được tổ chức hỗ trợ để truy cập Config Server. **Không nhúng username/password vào URI** (ví dụ user:password@host) vì URI dễ xuất hiện trong log, monitoring, error messages hoặc deployment diffs.

Config Server giúp quản lý **cấu hình phiên bản hóa** nhưng không tự giải quyết vấn đề **phân phối và xoay private keys, client secret, API key**. Nếu Config Server còn đọc Vault, các quyền và credential để truy cập Vault phải được bảo vệ theo trust boundary riêng.

### 9.2. Label và khả năng tái hiện deployment

Giả sử deploy:

~~~text
image digest = sha256:...
Spring profile = prod
Config Server label = release-2026-11
Secret generation = inventory-key-v7
~~~

Một rollback chỉ đổi image nhưng không đổi **label/config generation** có thể tạo tổ hợp code–config không tương thích. Ghi metadata của từng rollout, xác định ai được thay label và có quy trình **revert cấu hình** riêng nếu một timeout, zone hoặc auth setting gây lỗi.

### 9.3. Refresh không phải tự động áp dụng cho mọi bean

Spring Cloud có **EnvironmentChangeEvent**, **@RefreshScope** và /actuator/refresh trong những môi trường được hỗ trợ. Nhưng:

- Một **RestClient/WebClient/Feign instance** đã được dựng bằng request factory, SSLContext và pool cũ không nhất thiết tự xây lại sau refresh.
- ConfigurationProperties constructor-bound/record có giới hạn refresh tùy cách quản lý bean.
- Những bean đã copy giá trị vào field không thay đổi khi một property source mới được phát hành.
- Spring Cloud Context refresh có các giới hạn ở chế độ **AOT/native image**.

Nếu chưa có test đúng đường **rebind → thay HTTP client/credential → drain connection cũ**, hãy dùng **rolling restart**. Không mở /actuator/refresh rộng cho traffic công cộng.

## 10. Kubernetes ConfigMap: cấu hình không nhạy cảm

Trong Kubernetes, ConfigMap có thể cấp **environment variables** hoặc file mount cho các tham số không chứa bí mật.

Ví dụ:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-service-settings
  namespace: orders
data:
  SPRING_PROFILES_ACTIVE: "prod"
  APP_INVENTORY_RESPONSE_TIMEOUT: "1500ms"
  SPRING_CLOUD_LOADBALANCER_CACHE_TTL: "35s"
  SPRING_CONFIG_IMPORT: "configtree:/etc/order/secrets/"
~~~

Chú thích:

- **SPRING_PROFILES_ACTIVE=prod** kích hoạt cấu hình profile.
- **APP_INVENTORY_RESPONSE_TIMEOUT** có thể ghi đè profile file nếu property source precedence cho phép.
- **SPRING_CLOUD_LOADBALANCER_CACHE_TTL** điều chỉnh TTL của LB cache, không phải HTTP connection pool.
- **SPRING_CONFIG_IMPORT** ở đây bắt buộc tồn tại directory Secret. Nếu mount sai, ứng dụng fail startup thay vì chạy thiếu credential.

**Chỉ nên đưa giá trị không nhạy cảm vào ConfigMap.** Không đặt API key, private key, OAuth2 client secret hoặc password trong ConfigMap chỉ vì nó có thể mount như file.

### 10.1. ConfigMap dạng env không tự cập nhật JVM đang chạy

Khi ConfigMap được truyền qua **envFrom**, các giá trị environment được tạo tại lúc container start. Cập nhật ConfigMap **không thay thế environment variables bên trong process đang chạy**.

Do đó, sau khi đổi **APP_INVENTORY_RESPONSE_TIMEOUT**, việc Kubernetes cập nhật đối tượng ConfigMap **chưa đủ** để chắc chắn RestClient sử dụng timeout mới. Cần:

1. Rolling restart để tạo Pods mới với env vars mới; **hoặc**
2. Thiết kế ConfigMap volume/file watcher và refresh bean/HTTP client **đã được kiểm thử**.

Với cấu hình thay đổi ít, **rolling restart có readiness gate** thường dễ kiểm soát hơn hot reload toàn bộ object graph.

## 11. Kubernetes Secret: tạo từ hệ thống bảo mật, mount thành file

Ví dụ Secret chứa API key Inventory được cấp thông qua **Secret Manager/CI-CD an toàn**. Khi thử local, có thể tạo Secret từ một file có sẵn trên máy người học:

~~~bash
kubectl -n orders create secret generic inventory-auth \
  --from-file=app.inventory-auth.api-key=./secrets/inventory-api-key
~~~

**Không commit file thật trong secrets/ vào Git** và không đưa giá trị vào command line argument trực tiếp. Lệnh trên là ví dụ thao tác vận hành; ở production nên tích hợp external-secrets/CSI hoặc công cụ quản lý credential có audit, rotation và quyền hạn phù hợp.

Nếu tổ chức quản lý Secret bằng manifest GitOps, phải dùng **encryption/sealed/external secret references** theo chính sách; không commit Kubernetes Secret có **data** Base64 rồi coi đó là encryption.

### 11.1. Deployment mẫu cho Order Service

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
  namespace: orders
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      securityContext:
        runAsNonRoot: true
        fsGroup: 2000
      containers:
        - name: order
          image: registry.example.internal/order-service@sha256:REPLACE_DIGEST
          ports:
            - containerPort: 8080
          envFrom:
            - configMapRef:
                name: order-service-settings
          volumeMounts:
            - name: inventory-credentials
              mountPath: /etc/order/secrets
              readOnly: true
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
      volumes:
        - name: inventory-credentials
          secret:
            secretName: inventory-auth
            defaultMode: 0440
~~~

**Những điểm cần chỉnh trước production:**

- **image digest** trên chỉ là placeholder, phải thay bằng digest thật.
- **namespace orders**, securityContext, fsGroup, file permission và ServiceAccount phải phù hợp cluster. Một file 0440 với group permission chỉ đọc được nếu volume ownership/group/Pod securityContext tương thích.
- Probe endpoint **/actuator/health/readiness** và **/actuator/health/liveness** cần được Spring Boot/Actuator hỗ trợ và cấu hình trong môi trường. Nếu chưa được expose/enable theo phiên bản, Pod sẽ không ready.
- Cấu hình workload identity/service account riêng nếu cần truy cập Kubernetes API hoặc Secret Manager; không cấp cluster-admin.
- Deployment trên **không** tạo service-discovery client cho từng Pod. Nếu dùng Spring Cloud Kubernetes DiscoveryClient, phải thêm starter và quyền phù hợp; nếu chỉ đi qua Kubernetes Service DNS, thiết kế client khác.

### 11.2. Secret mount thay đổi như thế nào?

Kubernetes có thể cập nhật Secret volume theo cơ chế **eventual consistency**. Theo tài liệu Kubernetes, độ trễ gồm kubelet sync period và thời gian truyền thay đổi qua watch/cache.

Quan trọng:

- **Secret mount qua subPath không tự nhận cập nhật** khi Secret được sửa.
- **Secret được đưa qua env var** giữ giá trị cũ cho đến khi container được khởi động lại.
- **File volume cập nhật** không khiến một String API key/SSLContext/Feign RequestInterceptor đã cache giá trị cũ tự cập nhật.

Không mở file watcher cho private key rồi coi rotation đã thành công chỉ vì filesystem báo file mới. Bước xác minh phải là **credential generation thật được dùng trong request mới và downstream chấp nhận**.

### 11.3. Quyền truy cập Secret và RBAC

Các quyền tối thiểu cần được phân biệt:

~~~text
Kubernetes RBAC GET/LIST/WATCH Secrets:
  chỉ cấp khi ứng dụng thật sự đọc Secret qua API

Pod Secret volume:
  kubelet mount vào container được khai báo
  không cần tự động cấp API quyền LIST toàn namespace cho app

Secret Manager:
  workload identity chỉ đọc path/version được phép

CI/CD:
  có quyền tạo/cập nhật tham chiếu hoặc secret theo pipeline
  không được in plaintext vào logs/artifacts
~~~

Kubernetes Secret không được mã hóa ở rest trong mọi cluster theo mặc định nếu quản trị viên chưa cấu hình; cần kiểm tra **encryption at rest**, admission controls, audit logging và RBAC. Bảo vệ private key không thể chỉ dựa vào việc file nằm trong namespace.

## 12. Spring Cloud Kubernetes và Kubernetes Service DNS không phải một thứ

Đây là quyết định triển khai ảnh hưởng trực tiếp đến Spring Cloud LoadBalancer:

| Mô hình | Caller dùng địa chỉ nào? | Ai chọn backend? | Điều cần kiểm chứng |
| --- | --- | --- | --- |
| **Kubernetes Service DNS** | http://inventory-service.namespace.svc.cluster.local | Kubernetes Service/network dataplane hoặc service mesh | Routing và TLS tại Service/mesh |
| **Spring Cloud Kubernetes DiscoveryClient** | http://inventory-service với @LoadBalanced client | Spring Cloud LoadBalancer chọn từ các ServiceInstance do discovery cung cấp | Starter, RBAC, instance metadata, HTTP scheme |
| **Eureka/Consul** | http://inventory-service với @LoadBalanced client | Spring Cloud LoadBalancer từ registry entries | Registry credentials, metadata, health/TTL |
| **Static SimpleDiscoveryClient** | http://inventory-service với @LoadBalanced client | Spring Cloud LoadBalancer từ URI tĩnh | Chỉ phù hợp môi trường cố định/test |

Nếu chỉ muốn gọi **Kubernetes Service** được cân bằng tải bởi cluster, **không nhất thiết cần** Spring Cloud LoadBalancer chọn từng Pod. Nhưng nếu bài toán yêu cầu zone preference, hint routing hoặc policy riêng ở client, cần chọn discovery integration cung cấp những instance và metadata đúng.

### 12.1. Dùng Kubernetes API làm property source

Spring Cloud Kubernetes có phương thức:

~~~yaml
spring:
  config:
    import: "kubernetes:"
~~~

Khi đã có **Spring Cloud Kubernetes Config starter** tương thích, cơ chế này có thể nạp ConfigMap/Secret theo quy ước **spring.application.name** và namespace. Tính năng không hoạt động chỉ bởi vì ứng dụng chạy trong Pod; phải có starter, configuration và quyền API cần thiết.

Nếu chỉ muốn nhập mounted Secret files, **configtree:** của Spring Boot đã đủ và **không bắt buộc** cấp cho ứng dụng quyền GET/LIST Kubernetes Secrets qua API.

**Không trộn legacy bootstrap với spring.config.import cho cùng nguồn** nếu implementation không hỗ trợ cả hai đồng thời. Spring Cloud Kubernetes có tài liệu riêng về PropertySource precedence khi kết hợp Config Server/Kubernetes; phải xác định thứ tự trước khi dùng cùng key ở hai nguồn.

## 13. Cấu hình Spring Cloud LoadBalancer theo từng môi trường

Với một caller sử dụng service ID **inventory-service**, các giá trị thường cần đánh giá theo môi trường gồm:

~~~yaml
spring:
  cloud:
    loadbalancer:
      enabled: true
      cache:
        enabled: true
        ttl: 35s
      retry:
        enabled: false
      eager-load:
        clients:
          - inventory-service
      zone: zone-a
~~~

Đây chỉ là bộ property minh họa; **zone-a** phải được cung cấp từ metadata/placement thực của caller, không hardcode một zone cho tất cả Pods ở nhiều Availability Zones.

### 13.1. Cache TTL và nguồn discovery

Spring Cloud LoadBalancer có **CachingServiceInstanceListSupplier** tùy đường cấu hình và cache mặc định thường được bật; tài liệu mô tả TTL 35 giây, capacity 256.

Nhưng một DiscoveryClient như Eureka có thể **đã cache danh sách instances**. Khi có hai tầng cache:

~~~text
Registry snapshot/cache
       |
       v
Spring Cloud LB cache
       |
       v
ServiceInstanceListSupplier -> LoadBalancer choose()
~~~

việc scale-in một instance có thể chưa được mọi caller nhìn thấy ngay. TTL thấp không đồng nghĩa “không có stale request”, vì còn registry propagation và connection pool. Không chỉ giảm TTL vô hạn để sửa một incident; nó có thể tăng truy vấn registry và tải CPU.

**Khi quyết định TTL**, đo các tình huống: Pod restart, scale-out, scale-in, unhealthy instance, registry/network partition và rate of new connections.

### 13.2. Health check cần supplier, không chỉ một property

Ví dụ:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        path:
          default: /actuator/health
        interval: 25s
~~~

Các properties định nghĩa **đường dẫn/lịch** của health check, nhưng **không mặc nhiên tạo HealthCheckServiceInstanceListSupplier trong mọi ứng dụng**. Cần đăng ký supplier chain phù hợp theo blocking/reactive discovery và cấu hình như Spring Cloud reference.

Ngoài ra, health check phải gọi đúng endpoint/bảo mật:

- Nếu endpoint yêu cầu token hoặc mTLS, health-check client phải được cấu hình đúng.
- Probe HTTP 200 không bảo đảm mọi nghiệp vụ của backend đều khỏe.
- Không dùng một protected business endpoint đắt làm heartbeat liên tục.
- Nếu registry đã cung cấp trạng thái healthy đáng tin cậy, đánh giá xem health-check supplier thêm có cần thiết không.

### 13.3. Zone preference và metadata

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: zone-a
~~~

Giá trị trên là **zone của caller**, trong khi zone của backend phải hiện diện theo **metadata hoặc cơ chế zone mapping** mà supplier sử dụng. Chỉ đặt zone ở caller không tạo metadata zone cho providers.

ZonePreferenceServiceInstanceListSupplier thường **ưu tiên bản sao same-zone** nhưng có fallback khi không có ứng viên cùng zone; không phải ranh giới bảo mật/tuân thủ địa lý tuyệt đối. Nếu dữ liệu không được rời một region, cần thêm **network policy, deployment policy, admission guard và backend authorization**.

### 13.4. Retry khác giữa các HTTP clients

Cấu hình minh họa:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
~~~

**Không bật retry mù trong production**:

- RestTemplate blocking có điều kiện classpath/integration như Spring Retry.
- WebClient có cơ chế reactive retry/filter riêng.
- RestClient có hành vi theo Spring Cloud release train/request factory.
- Spring Cloud OpenFeign có Retryer riêng; mặc định **Retryer.NEVER_RETRY** trong nhiều phiên bản tích hợp.
- Gateway, mesh hoặc proxy cũng có thể retry ngoài JVM.

Một logical request có thể tạo nhiều HTTP attempts khi các tầng được bật đồng thời. Với POST tạo đơn/reserve stock, phải có **idempotency key** trước khi retry transport errors hoặc timeout chưa rõ trạng thái.

### 13.5. Eager-load không phải preconnect

**spring.cloud.loadbalancer.eager-load.clients** giúp tạo sớm child ApplicationContext của các service IDs đã chỉ định. Nó **không tự mở sẵn TCP/TLS tới mọi ServiceInstance**; connection warm-up phụ thuộc HTTP engine và request thực.

Chỉ đưa service IDs quan trọng vào danh sách để tránh tăng startup time/memory vô ích. Nếu application đóng vai trò aggregator gọi 30 downstream, eager-load cả 30 context khi startup cần được đo về readiness latency.

## 14. Phân biệt cấu hình LoadBalancer với HTTP client transport

Một cấu hình gọn:

~~~text
LoadBalancer policy:
  Chọn A hoặc B từ danh sách eligible

HTTP transport:
  DNS / TCP connect / TLS / connection pool
  response timeout / pool acquire timeout

HTTP application:
  Bearer token / API key / headers / request body

Resilience:
  retry / circuit breaker / fallback / overall deadline
~~~

Nếu bạn đặt **spring.cloud.loadbalancer.cache.ttl=10s**, điều đó **không đổi thời gian HTTP connect timeout**; tương tự, tăng Feign readTimeout không làm refresh discovery nhanh hơn.

### 14.1. Bảng cấu hình theo client

| Client | Nơi cấu hình service ID | Nơi cấu hình transport timeout | Nơi đặt credential |
| --- | --- | --- | --- |
| RestClient | @LoadBalanced RestClient.Builder + URI logic | ClientHttpRequestFactory/HTTP engine | ClientHttpRequestInterceptor hoặc OAuth2 client integration |
| RestTemplate | @LoadBalanced RestTemplate | ClientHttpRequestFactory/HTTP engine | Interceptor hoặc OAuth2 integration |
| WebClient | @LoadBalanced WebClient.Builder + URI logic | Reactor Netty HttpClient/ClientHttpConnector | ExchangeFilterFunction/OAuth2 filter |
| OpenFeign | @FeignClient(name=...) | Named-client connectTimeout/readTimeout và underlying engine | Per-client RequestInterceptor/OAuth2 integration |

**Không có một property duy nhất của Spring Cloud LoadBalancer** tự đặt connect/read/response/pool timeout cho toàn bộ bốn clients.

## 15. RestClient: cấu hình theo service ID nhưng không hardcode credential

Ví dụ tạo RestClient bằng builder được đánh dấu LoadBalancer:

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryRestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient inventoryRestClient(
            @LoadBalanced RestClient.Builder builder,
            InventoryClientSettings settings,
            InventoryTokenProvider tokens) {

        return builder
                .baseUrl("https://" + settings.serviceId())
                .requestInterceptor((request, body, execution) -> {
                    request.getHeaders().setBearerAuth(
                            tokens.currentValidToken());
                    return execution.execute(request, body);
                })
                .build();
    }
}
~~~

Trong ví dụ **InventoryTokenProvider** là abstraction ứng dụng tự cung cấp; nó phải lấy access token có hiệu lực, tránh refresh storm và không ghi token vào log. Với OAuth2 chuẩn, ưu tiên **OAuth2AuthorizedClientManager/RestClient OAuth2 interceptor** của Spring Security thay vì tự quản lý token.

**Ràng buộc:**

- HTTPS với service ID đòi hỏi certificate/SNI/hostname verification tương thích với **URI vật lý sau LoadBalancer rewrite**.
- Một interceptor gắn Authorization chỉ nên dùng trên **dedicated Inventory client**, không dùng chung để gọi Payment/Catalog.
- RestClient.Builder có thể cần Spring Boot customizer để giữ observation, codec, TLS và request factory; đừng bỏ cấu hình Boot đã có khi tự tạo bean.
- **responseTimeout** trong InventoryClientSettings chưa được dùng ở snippet; production phải áp dụng nó vào **ClientHttpRequestFactory/underlying transport** phù hợp. Không gọi snippet là đã cấu hình timeout hoàn chỉnh.

### 15.1. Nếu dùng RestClientSsl

Spring Boot có **RestClientSsl** cho các phiên bản hỗ trợ SSL bundles, có thể áp dụng khi **xây client**:

~~~java
RestClient client = builder
        .apply(ssl.fromBundle("inventory-client"))
        .baseUrl("https://inventory-service")
        .build();
~~~

Ở đây **ssl** là RestClientSsl được inject từ Spring Boot, **builder** là @LoadBalanced nếu dùng service ID, và **inventory-client** là bundle cấu hình riêng. Đoạn này áp dụng TLS config khi tạo client, **không tự bảo đảm hot-reload SSLContext ở outbound connection pool**.

## 16. WebClient: response timeout, connection pool và credential

Reactor Netty cho phép cấu hình HTTP transport:

~~~java
@Bean
HttpClient inventoryHttpClient() {
    return HttpClient.create()
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 500)
            .responseTimeout(Duration.ofSeconds(2));
}

@Bean
@LoadBalanced
WebClient.Builder loadBalancedWebClientBuilder(
        HttpClient inventoryHttpClient) {
    return WebClient.builder().clientConnector(
            new ReactorClientHttpConnector(inventoryHttpClient));
}
~~~

**Đây là mẫu kỹ thuật**, import các class từ Reactor Netty, Netty, Spring WebFlux/Spring Cloud. Dự án thật nên giữ Spring Boot WebClientCustomizer, codecs, observations và security filters. Để điều chỉnh pool acquisition/concurrency, phải xem **ConnectionProvider** và cấu hình HTTP client riêng; responseTimeout không thay thế một overall deadline.

Khi gắn token OAuth2 lên WebClient, dùng **ReactiveOAuth2AuthorizedClientManager** cùng filter của Spring Security phù hợp. Không thực hiện blocking read Secret Manager hoặc token exchange trên Netty event loop.

**Không áp dụng Spring Cloud LoadBalancer hai lần**: một WebClient.Builder đã @LoadBalanced không nên lại được thêm ReactorLoadBalancerExchangeFilterFunction thủ công lần thứ hai, trừ khi pipeline được chủ động thiết kế và kiểm thử.

### 16.1. WebClient có thể được subscribe nhiều lần

~~~text
Mono được tạo lúc T0
HTTP request thật bắt đầu khi subscribe T1
retryWhen có thể subscribe lần 2 tại T2
~~~

Nếu secret/token được chụp quá sớm vào header ở T0, lần gửi tại T1/T2 có thể dùng credential hết hạn. Token provider/filter nên chọn credential theo thời điểm request thực thi và chính sách cache, đồng thời xác định số attempts được phép.

## 17. OpenFeign: named-client configuration và secrets

Ví dụ khai báo Feign theo service ID:

~~~java
@FeignClient(name = "inventory-service")
interface InventoryFeignClient {

    @GetMapping("/api/stock/{sku}")
    StockResponse getStock(@PathVariable("sku") String sku);
}
~~~

Named-client timeout:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          inventory-service:
            connectTimeout: 500
            readTimeout: 1500
            loggerLevel: basic
~~~

Các timeout Feign trong ví dụ tính theo **mili giây** theo API/config của Feign hiện hành. Chúng không phải TTL của Spring Cloud LoadBalancer, và cũng không luôn là tổng end-to-end deadline nếu còn DNS, proxy, retries và pool acquisition.

### 17.1. Feign URL cố định có thể bỏ qua LoadBalancer

Nếu cấu hình **@FeignClient(name="inventory-service", url="https://some-host")** hoặc named-client URL property, Feign có thể gọi trực tiếp địa chỉ đó thay vì chọn ServiceInstance. Nếu bài toán cần client-side selection, nên dùng **name/service ID** và không override URL vô tình trong từng environment.

### 17.2. Không dùng global RequestInterceptor làm lộ credential

Một RequestInterceptor cho Inventory nên có scope **riêng Feign named client**, không được component-scan thành bean toàn cục vô ý. Nếu global interceptor gắn Inventory API key lên tất cả Feign clients, token có thể bị gửi tới Payment hoặc Catalog.

Trong môi trường có mTLS, **Apache HC5/OkHttp hoặc underlying Feign client** quyết định SSLContext và connection pool, không phải bản thân @FeignClient. Khi bí mật kết nối thay đổi, cần xác minh underlying transport đã sử dụng vật liệu mới.

## 18. TLS/mTLS: cấu hình truststore, client certificate và hostname

TLS bảo vệ kênh truyền và xác minh server. Với **mTLS**, client còn xuất trình **client certificate** để server xác minh danh tính workload.

Ví dụ Spring Boot **SSL bundle PEM** để cấu hình vật liệu:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        inventory-client:
          truststore:
            certificate: "file:/etc/order/tls/inventory-ca.pem"
          keystore:
            certificate: "file:/etc/order/tls/order-client.crt"
            private-key: "file:/etc/order/tls/order-client.key"
~~~

Các file này do **Secret volume/CSI/PKI** phân phối, không nằm trong JAR. Chỉ cấu hình truststore nếu dùng **server TLS** mà không cần client certificate; keystore/client key được thêm khi downstream yêu cầu mTLS.

**Cần xác minh tương thích phiên bản:** SSL bundle là cơ chế cấu hình vật liệu cho các thành phần được Spring Boot hỗ trợ; HTTP connector của **RestClient/WebClient/Feign** phải thực sự sử dụng bundle. Không được suy ra Feign tự lấy client certificate chỉ vì tên bundle xuất hiện trong YAML.

### 18.1. TLS identity sau khi LoadBalancer chọn instance

Giả sử:

~~~text
Logical URI: https://inventory-service/stock
Selected ServiceInstance: inventory-b.internal:8443
Physical URI: https://inventory-b.internal:8443/stock
~~~

Certificate của server phải hợp lệ theo **hostname mà HTTP client xác minh**, bao gồm SAN phù hợp. Việc đặt certificate chỉ có DNS SAN inventory-service **có thể không đủ** nếu HTTP connector xác minh inventory-b.internal hoặc IP trực tiếp.

Không sửa bằng:

- tắt hostname verification;
- trust-all TrustManager;
- vô hiệu certificate chain validation;
- đặt HTTP Host header tùy tiện để giả vờ TLS identity đã thay đổi.

Hãy thống nhất **discovery address, DNS, certificate SAN, SNI, proxy/mesh topology**. Nếu mesh sidecar kết thúc TLS, cần xác định **mesh hay Java** sở hữu certificate và chính sách xác minh.

### 18.2. Khi nào SSL bundle hot reload?

Spring Boot hỗ trợ **reload-on-update** cho một số SSL bundle consumers. Theo tài liệu hiện hành, các consumer được nêu rõ hỗ trợ là **Tomcat web server** và **Netty web server**:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        webserver:
          reload-on-update: true
          keystore:
            certificate: "file:/etc/tls/server.crt"
            private-key: "file:/etc/tls/server.key"
server:
  ssl:
    bundle: webserver
~~~

Đây là ví dụ cho **TLS inbound web server**, **không phải** cam kết **outbound RestClient, WebClient và Feign** tự reload SSLContext/connection pool khi file thay đổi.

### 18.3. Mối quan hệ giữa TLS rotation và connection pool

~~~text
N:   TLS context/connection pool cũ
       |
       +-- connections đang mở có TLS session cũ

N+1: Secret volume có cert/key mới
       |
       +-- HTTP engine cần dùng TLS material mới cho handshake mới
       +-- Pool cũ có thể vẫn giữ socket/SSLContext cũ
~~~

Nếu transport không hỗ trợ đổi vật liệu động một cách đã được kiểm thử, chọn **rolling restart** hoặc **tạo HTTP client/pool generation mới rồi drain generation cũ**. Không đóng pool cũ tức thì khi còn HTTP requests đang xử lý; không tiếp tục tin key cũ khi đã bị compromise chỉ để giữ availability.

## 19. OAuth2 client_credentials: không nhầm secret với access token

Một Order Service dùng OAuth2 client credentials để gọi Inventory có thể cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory:
            provider: internal-idp
            client-id: order-inventory
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
        provider:
          internal-idp:
            token-uri: https://identity.internal.example/oauth2/token
~~~

**Không có client-secret trong đoạn YAML này.** Property bí mật tương ứng là:

~~~text
spring.security.oauth2.client.registration.inventory.client-secret
~~~

Nó phải được cung cấp bằng **secret provider hoặc configtree file** nếu phương thức client authentication sử dụng client secret. Khi tổ chức hỗ trợ private_key_jwt hoặc mTLS client authentication, cách cấu hình token client khác và cần xác minh với Identity Provider.

### 19.1. Hai vòng đời riêng

| Thành phần | Vòng đời | Cách đổi |
| --- | --- | --- |
| **Access token** | Thường ngắn hạn | OAuth2AuthorizedClientManager lấy token mới khi cần |
| **OAuth2 client secret** | Được cấp/thu hồi theo chính sách Identity Provider | Cập nhật ClientRegistration/credential provider hoặc restart |
| **OAuth2 signing key/JWKS** | Luân chuyển của issuer | Issuer publish public key trước khi ký token mới; resource servers cập nhật verifier |
| **TLS client certificate** | Hạn sử dụng của cert/key | Thay SSLContext/HTTP transport hoặc restart |

Spring Security có abstractions như **OAuth2AuthorizedClientManager** cho RestClient và **ReactiveOAuth2AuthorizedClientManager** cho WebClient. Đừng tự cache access token vĩnh viễn trong một field hoặc gọi Token Endpoint ở mọi request.

### 19.2. Token đúng audience và scope

Ngay cả khi TLS handshake thành công, Inventory vẫn có thể trả:

~~~text
401 Unauthorized: token thiếu/hết hạn/sai issuer/audience
403 Forbidden: token hợp lệ nhưng không đủ scope/permission
~~~

**Không retry 401/403 mù bằng LoadBalancer**. Nếu token hết hạn, token manager có thể cấp lại với ngân sách hữu hạn theo contract; nếu scope sai, cần sửa authorization. Không gửi Bearer token Inventory sang một host/Feign client khác do interceptor toàn cục hoặc redirect không kiểm soát.

## 20. Xoay bí mật kết nối khi ứng dụng đang chạy

Quy trình rotation chuẩn cần **hai phía**:

~~~mermaid
flowchart TD
    A["Secret Manager/PKI phát hành generation N+1"] --> B["Bên nhận chấp nhận key/cert mới"]
    B --> C["Phân phối secret generation N+1"]
    C --> D["Caller đọc và xác minh vật liệu mới"]
    D --> E{"HTTP client dùng được N+1?"}
    E -->|Không| F["Rolling restart hoặc tạo client/pool mới"]
    E -->|Có| G["Publish generation mới cho request mới"]
    F --> G
    G --> H["Canary HTTPS + auth qua service ID"]
    H --> I{"Canary OK?"}
    I -->|Không| J["Dừng rollout, rollback nếu credential cũ an toàn"]
    I -->|Có| K["Drain generation N và thu hồi cũ đúng lịch"]
~~~

### 20.1. Đừng coi file thay đổi là rotation hoàn tất

Các trạng thái khác nhau:

~~~text
Secret Manager:          generation 12
Kubernetes Secret:       generation 12
Mounted volume:          generation 12
Spring Environment:      có thể vẫn generation 11
HTTP client interceptor: có thể vẫn generation 11
TLS connection pool:     có thể đang giữ TLS session generation 11
Backend accepts:         generations 11 và 12
~~~

Một lần cập nhật filesystem chỉ chứng minh tới **mounted volume**. Phải xác minh **request mới được gửi bằng credential generation 12** và downstream chấp nhận nó.

### 20.2. API key có thể cập nhật qua provider từng request

Nếu interceptor/filter đọc **CurrentCredentialProvider** ở thời điểm request thực, API key có thể chuyển mà không thay TCP pool, miễn backend đã chấp nhận key mới.

Ngược lại, nếu RestClient/Feign giữ **API key từ constructor** hoặc defaultHeader cố định, sửa Secret file không tự đổi header. Cần reload bean/credential provider an toàn hoặc restart. Tuyệt đối không log key trước/sau để “chứng minh đã thay”.

### 20.3. Đổi CA cho mTLS theo hai pha

Thông thường:

1. **Expand trust:** cả client/server tin CA-old và CA-new khi chính sách cho phép.
2. **Migrate:** triển khai certificates mới dần, kiểm tra từng instance và pool.
3. **Contract:** loại CA-old khi mọi callers/backends đã chuyển và đủ điều kiện thu hồi.

Khi private key bị lộ, phải theo **incident response** và có thể thu hồi khẩn cấp, không kéo dài overlap vì lý do tiện triển khai.

### 20.4. Rolling restart với Secret env vars

Khi credential được nạp qua environment variables hoặc transport không hỗ trợ cập nhật TLS động:

~~~bash
kubectl -n orders rollout restart deployment/order-service
kubectl -n orders rollout status deployment/order-service
~~~

Lệnh trên chỉ là hướng dẫn vận hành, **không thực hiện trong bài viết này**. Cần đủ replicas, rolling strategy phù hợp và readiness probes; với chỉ một replica, restart có thể gây gián đoạn.

Nếu dùng Helm/GitOps, nên thay **Pod template annotation với config/secret generation hoặc checksum đã được kiểm soát**, khiến Deployment tạo Pods mới một cách có phiên bản. Không đưa secret plaintext vào annotation hoặc labels.

## 21. Cấu hình timeout/retry để không biến lỗi credential thành retry storm

Một chính sách bảo vệ có thể mô tả:

~~~text
Connect timeout:       500 ms
Response timeout:      1500 ms
Maximum HTTP attempts: 2 (chỉ idempotent GET và lỗi cho phép)
Overall deadline:      2500 ms
Circuit breaker:       theo operation
Fallback:              degraded/unknown, không giả mạo thành công
~~~

Các số này **minh họa**, cần test với latency thực tế và thời gian discovery/TLS/circuit breaker. Timeout HTTP engine có thể tính từ một giai đoạn khác với **overall deadline**.

### 21.1. Ma trận có nên retry?

| Lỗi | Retry? | Nguyên nhân |
| --- | --- | --- |
| Connect refused sau instance đã bị terminate | Có thể, attempt hữu hạn | Retry với instance khác có thể phục hồi |
| HTTP 503 backend | Có thể, có backoff | Tránh làm backend quá tải |
| Timeout đọc response cho GET | Có thể, tùy idempotency | Đảm bảo HTTP request an toàn để lặp |
| HTTP 401 access token expired | Có thể qua OAuth2 token refresh chuyên trách | Không retry mù với token cũ |
| HTTP 403 scope không đủ | Thường không | Retry không cấp thêm quyền |
| SSLHandshakeException do trust/SAN sai | Không retry mù | Phải sửa TLS policy/certificate |
| No ServiceInstance | Theo discovery/retry budget cụ thể | Không giả định registry sẽ có instance ngay |
| HTTP 400/422 input không hợp lệ | Không | Thường là lỗi contract |
| POST đặt hàng timeout sau gửi | Chỉ khi có idempotency/deduplication | Backend có thể đã commit |

**Bật nhiều tầng retry** (LoadBalancer, Reactor, Feign, gateway, service mesh) có thể làm số HTTP attempts nhân lên. Quản lý cấu hình theo môi trường cũng phải xác định rõ **tầng nào sở hữu retry**, không chỉ định một con số maxRetries ở mỗi chỗ.

## 22. Readiness/liveness không đồng nghĩa kiểm tra tất cả downstream

Một Pod có thể **process running** nhưng chưa nên nhận traffic vì thiếu cấu hình, secret chưa mount, HTTP client chưa khởi tạo được hoặc service discovery chưa có nguồn hợp lệ. Đây là vấn đề **readiness**, không nhất thiết là liveness.

Ví dụ bật health probes trong Spring Boot khi cần:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: "health,info"
~~~

**Liveness** nên phản ánh tiến trình có khả năng tiếp tục hoạt động; không nên tự động DOWN chỉ vì Inventory tạm thời trả 503. Nếu biến một lỗi downstream thành liveness failure, Kubernetes có thể restart hàng loạt Order pods, gây cascade.

**Readiness** có thể từ chối traffic khi ứng dụng chưa tải được **credential/config bắt buộc**. Nhưng không mặc định đưa mọi downstream phụ trợ vào readiness: nếu Inventory tạm thời lỗi mà Order vẫn có thể phục vụ những API khác, nên đánh dấu chức năng phụ bị degraded hoặc xử lý fallback đúng contract thay vì đưa toàn bộ pod ra khỏi hệ thống.

### 22.1. Startup gate cho secrets

Luồng hợp lý:

~~~text
Pod start
  |
  v
Mount Secret volume / inject env vars
  |
  v
Spring Boot Config Data import + binding + validation
  |
  v
Xây HTTP client, TLS/auth providers
  |
  v
Readiness = accepting traffic
  |
  v
Caller gửi request theo service ID
~~~

Nếu **configtree:** bắt buộc bị thiếu, startup fail sớm là tín hiệu đúng. Nếu Secret Manager tạm thời unavailable, quyết định **fail-fast, retry hữu hạn ở startup, hoặc degraded mode** phải nằm trong deployment policy và phù hợp với chức năng của dịch vụ.

### 22.2. Chống circular dependency ở rollout

Không xây readiness của Order yêu cầu Inventory ready, đồng thời readiness của Inventory lại yêu cầu Order ready. Vòng phụ thuộc có thể khiến cả hai không bao giờ được đưa vào endpoints. Đánh giá riêng khả năng xử lý request của từng service và dùng timeout/fallback cho quan hệ downstream.

## 23. Quan sát cấu hình runtime mà không lộ bí mật

Spring Boot Actuator có các endpoint **env**, **configprops**, **health**, **info**, **metrics**. Theo tài liệu Spring Boot, các giá trị trên env/configprops được sanitization theo mặc định, nhưng **không nên coi sanitization thay thế network access control**.

### 23.1. Những thông tin vận hành nên công bố có kiểm soát

~~~text
application:          order-service
image digest:         sha256:...
active profile:       prod
config revision:      release-2026-11
credential generation: inventory-key-v7  (ID không bí mật)
service ID:           inventory-service
discovery provider:   kubernetes/eureka/consul
loadbalancer policy:  round-robin
retry policy:         enabled=false
health policy:        named supplier chain
~~~

Không expose:

~~~text
Bearer token
OAuth2 client secret
API key
Private key PEM
Truststore password
Full Config Server auth URL có credentials
Database password
Kubernetes Secret data
~~~

### 23.2. Metrics gợi ý

| Metric | Công dụng |
| --- | --- |
| config_revision / deployment_info | Biết pod đang chạy cấu hình nào |
| credential_generation_age | Biết secret đã stale bao lâu |
| credential_expiry_seconds | Alert trước khi token/certificate hết hạn |
| lb_no_instance_requests | Phát hiện discovery/supplier không trả bản sao |
| lb_requests_success/failed | Tình trạng lời gọi qua LoadBalancer |
| outbound_http_duration | P50/P95/P99 từng service/operation |
| outbound_connect_timeout | Phân biệt lỗi mạng với auth |
| outbound_tls_handshake_failures | Bắt lỗi CA/SAN/mTLS |
| outbound_http_401_403 | Phát hiện client secret/scope/policy mismatch |
| outbound_retry_attempts | Kiểm soát retry amplification |
| refresh_or_rotation_failures | Báo lỗi khi cập nhật config/credential |

Đây là **tên nhóm metric gợi ý**, không mặc định tên meter Spring Cloud/Micrometer. Với Spring Cloud LoadBalancer, các meters thống kê chỉ có khi integration và lifecycle metrics được cấu hình. Không chép tên minh họa thành SLO query trước khi kiểm tra registry thực tế.

### 23.3. Tracing với selected instance

Một trace an toàn có thể ghi:

~~~text
logical service id: inventory-service
selected instance: inventory-b  (nếu cardinality/phân quyền cho phép)
selected zone: zone-a
http method: GET
uri template: /api/stock/{sku}
outcome: HTTP 200
client credential generation: 7
~~~

Không đưa SKU, order ID, token, raw URL chứa query bí mật hoặc session ID thành metric tag có cardinality không giới hạn. Nếu cần instance ID, ưu tiên sampled trace/log đã kiểm soát truy cập.

## 24. Pipeline triển khai: kiểm chứng trước khi đưa traffic

Một quy trình CI/CD hoặc GitOps có thể gồm:

~~~mermaid
flowchart TD
    A["Code + configuration review"] --> B["Secret scanning + policy validation"]
    B --> C["Build image + SBOM + image digest"]
    C --> D["Static YAML/Helm/Kustomize validation"]
    D --> E["Deploy test profile với fake credentials"]
    E --> F["Integration tests: service discovery + auth + TLS"]
    F --> G["Staging canary"]
    G --> H{"SLO + security checks đạt?"}
    H -->|Không| I["Rollback config/image/credential refs"]
    H -->|Có| J["Prod rolling rollout/canary"]
    J --> K["Post-deploy smoke + observability"]
~~~

### 24.1. Kiểm tra trước build

- Không có secret plaintext trong source, YAML, CI variables được in ra logs, Dockerfile hoặc build cache.
- application.yml không hardcode production instance IP/credentials.
- Properties đúng tên, không có typo như **spring.cloud.loadbalancer.cache.tll**.
- Các giá trị timeout/TTL parse được, không âm hoặc vô lý.
- Profile prod không vô hiệu TLS validation, auth hoặc health check ngoài chủ đích.
- Dependency BOM Spring Boot/Spring Cloud/Spring Security tương thích.

### 24.2. Kiểm tra trước deploy

- ConfigMap và Secret reference đúng namespace/name/key.
- ServiceAccount có đúng quyền; không cấp list Secrets toàn cluster khi không cần.
- Secret volume mount có file permissions phù hợp process UID/GID.
- **SPRING_CONFIG_IMPORT** trỏ đúng đường dẫn trong Pod.
- TLS certificate SAN khớp hostname vật lý/client route.
- Registry/DiscoveryClient và service ID đúng, không lấy localhost từ profile dev.
- Resource limits/pool settings khớp concurrency và latency SLO.

### 24.3. Kiểm tra sau deploy

- Pod readiness ổn định, không có vòng CrashLoopBackOff do thiếu secret.
- Gọi thành công một endpoint safe qua service ID; biết instance thực nhận request.
- Kiểm tra negative path: 401/403 không bị che thành HTTP 200 giả.
- Đếm HTTP attempts khi lỗi để không có retry storm.
- Xác minh config revision và credential generation **không nhạy cảm**.
- Theo dõi P95/P99, 503/no-instance, TLS, token renewal và connection pool.

### 24.4. Cùng image nhưng khác cấu hình phải được kiểm thử

Nếu image version không đổi mà chỉ sửa ConfigMap từ timeout 1s sang 5s, đó vẫn là **một release hành vi mới**. Cần có changelog, owner, phạm vi môi trường và rollback. Không mặc định “chỉ sửa YAML, không cần test”.

## 25. Kiểm thử cấu hình bằng Spring Boot Test

Một bài test đơn giản có thể xác minh **profile dev** bind đúng giá trị:

~~~java
@SpringBootTest
@ActiveProfiles("dev")
class InventorySettingsDevTest {

    @Autowired
    InventoryClientSettings settings;

    @Test
    void resolvesDevSettings() {
        assertEquals("inventory-service", settings.serviceId());
        assertEquals(Duration.ofSeconds(3),
                settings.responseTimeout());
    }
}
~~~

Đoạn này chỉ chạy nếu project test thực có **application-dev.yml** như mục 5 và bean **InventoryClientSettings** được đăng ký. Imports từ Spring Boot Test, Spring Test, JUnit 5 và java.time.Duration.

### 25.1. Test fail startup khi thiếu bí mật

Trong integration test có thể dựng một ApplicationContext/test profile chỉ áp dụng credential config và **không đưa key bắt buộc vào Environment**, rồi xác nhận:

~~~text
No app.inventory-auth.api-key
       |
       v
Credential bean initialization fails
       |
       v
Application not ready
~~~

Không viết unit test in nội dung secret thực trong assertion failure. Dùng fake keys và môi trường test cô lập; không chạy test với production Secret Manager.

### 25.2. Test precedence

Tạo một test với:

~~~text
application.yml:      response-timeout=2s
application-dev.yml:  response-timeout=3s
test env/override:    response-timeout=500ms
~~~

Test xác minh **giá trị cuối** phù hợp Spring Boot PropertySource ordering. Nếu dùng **@TestPropertySource**, **DynamicPropertySource** hoặc command-line override, nhớ rằng chính các công cụ test này cũng tạo PropertySources với mức ưu tiên khác môi trường runtime.

### 25.3. Test discovery và route thực

Giả lập hai Inventory backends bằng **MockWebServer/WireMock**, cung cấp danh sách qua SimpleDiscoveryClient, rồi dùng **RestClient/WebClient/Feign đã load balance** để gọi theo service ID. Assert:

~~~text
logical URI = http://inventory-service/whoami
selected instance belongs to [A, B]
backend receives exactly expected attempts
Authorization header only sent to allowed downstream
no secret appears in HTTP client logs
~~~

Không chỉ mock **DiscoveryClient** rồi kết luận HTTP transport đã bảo vệ TLS và token đúng; cần integration test riêng cho truststore, mTLS, OAuth2 token endpoint, certificate rotation và server response.

### 25.4. Test runtime secret rotation

Tạo hai thế hệ fake credentials:

~~~text
generation N   -> backend chấp nhận key-old
generation N+1 -> backend chấp nhận key-new
~~~

Quy trình:

1. Caller gọi bằng key-old, nhận 200.
2. Backend mở giai đoạn chấp nhận cả key-old và key-new.
3. Secret provider chuyển sang key-new hoặc rolling restart pod.
4. Request mới dùng key-new và nhận 200.
5. Backend thu hồi key-old.
6. Request mới vẫn thành công, không còn requests dùng key-old.

Với mTLS, kiểm tra bằng **một TLS handshake mới** tới từng instance, không chỉ HTTP request trên connection keep-alive cũ.

## 26. Chẩn đoán lỗi: cấu hình nào đang sai?

Những sự cố thường gặp sau deployment nhìn từ caller có thể giống nhau nhưng nguyên nhân hoàn toàn khác.

| Triệu chứng | Tầng cần kiểm tra | Cách phân biệt |
| --- | --- | --- |
| UnknownHostException: inventory-service | HTTP client không có LoadBalancer hoặc URI bị gọi như DNS | Kiểm tra @LoadBalanced builder, filter/interceptor và Feign URL override |
| Spring Cloud LoadBalancer no instance / 503 | Discovery/supplier/health | Registry danh sách rỗng? sai service ID? zone/health filter loại hết? |
| Connection refused | IP/port/Pod listener | Đã chọn instance nhưng transport không connect được |
| Read timeout | Backend chậm hoặc transport/deadline | Request đến backend chưa? có body xử lý? |
| TLS handshake failure | Trust, SAN, SNI, mTLS | Peer cert chain, private key, URI vật lý, clock |
| HTTP 401 | OAuth2 access token, API key, issuer/audience | Token/key có hết hạn, sai nguồn hay còn thế hệ cũ? |
| HTTP 403 | Authorization policy/scope | Xác thực thành công nhưng không đủ quyền |
| Một Pod Order lỗi, Pod khác OK | Config/secret generation giữa pods khác | So config revision, mount version, rollout trạng thái |
| Chỉ profile prod lỗi | application-prod.yml, env/Secret/prod registry | Đối chiếu precedence và nguồn config |
| Sau sửa ConfigMap vẫn dùng giá trị cũ | Env vars đã chụp lúc start | Rolling restart hay refresh pipeline đã chạy? |
| Sau sửa Secret volume vẫn gửi API key cũ | Interceptor/provider giữ snapshot cũ | Kiểm tra provider generation và bean lifecycle |
| Một số Inventory instances bị TLS lỗi | Rolling cert chưa đồng bộ | Canary theo instance, CA overlap, SAN |
| Error rate tăng sau giảm cache TTL | Registry/network load hoặc discovery jitter | Kiểm tra cache miss/registry latency |
| Retry nhiều hơn config mong đợi | Nhiều tầng retry bật đồng thời | Đếm HTTP attempts theo từng layer |
| Actuator lộ values | Endpoint exposed/show-values/filters sai | Khóa truy cập, audit ngay |
| Pod CrashLoopBackOff do Config Data import | Secret path chưa mount hoặc import bắt buộc thiếu | Kiểm tra volume, permissions, startup exception |

### 26.1. Phân biệt no-instance với backend HTTP 503

~~~text
Kịch bản A:
  ServiceInstanceListSupplier = []
  LoadBalancer không chọn được đích
  Backend nhận 0 request
  Caller nhận lỗi/no-instance (có thể được map thành 503)

Kịch bản B:
  Supplier = [inventory-a]
  LoadBalancer chọn A
  HTTP request đã tới A
  Inventory A trả 503
~~~

Cả hai có thể xuất hiện dưới dạng **503** ở phía caller, nhưng runbook và quyết định retry khác nhau. Cần xem **backend request count, selected instance, trace và nơi sinh response**.

### 26.2. Sai profile và sai service ID

Ví dụ:

~~~text
Correct prod service ID: inventory-service
Wrong profile value:    inventory-prod-service

Spring Cloud LB lookup: inventory-prod-service
Registry has only:     inventory-service
Result: no instance
~~~

Không giải quyết bằng cách tăng readTimeout hoặc thêm retry. Cần sửa **source of truth** của property và có test contract service IDs.

## 27. Runbook rollout và rollback cấu hình/secret

Một workflow triển khai an toàn:

### 27.1. Trước rollout

1. Xác định **image digest**, **config revision**, **secret generation** và chủ sở hữu thay đổi.
2. Kiểm tra manifest namespace, ConfigMap/Secret references, RBAC, file permission.
3. Kiểm tra YAML/ConfigurationProperties binding và fail-fast secret validation ở staging.
4. Bảo đảm Inventory/Identity Provider đã chấp nhận **credential mới** nếu rotate.
5. Đặt rollout strategy, readiness và mức traffic canary.
6. Xác định ngưỡng rollback: 401/403, TLS handshake failures, no-instance, timeout, P95/P99.

### 27.2. Trong rollout

~~~text
Canary 1 pod/nhóm nhỏ
  -> đọc config/secret generation mới
  -> ready
  -> test route Inventory A/B theo policy
  -> kiểm chứng Bearer/mTLS
  -> theo dõi errors và retry attempts
  -> mở rộng rollout dần
~~~

Không rollout tất cả pods cùng lúc khi thay **client secret, CA hoặc discovery policy**, vì một lỗi nhỏ có thể làm toàn bộ callers mất quyền truy cập.

### 27.3. Khi phát hiện lỗi

1. **Dừng rollout** để giới hạn blast radius.
2. Phân loại **config precedence, discovery, HTTP transport, TLS, auth hay backend 5xx**.
3. Thu metadata không nhạy cảm: version, selected instance, zone, error class, HTTP status.
4. Nếu credential cũ vẫn an toàn, rollback config/secret reference và khôi phục Pods theo quy trình.
5. Nếu khóa cũ bị compromise, **không rollback sang khóa bị lộ**; thực hiện cấp lại/thu hồi khẩn cấp và chấp nhận downtime có kiểm soát nếu cần.
6. Xác nhận recovery bằng request thật và SLO, không chỉ Kubernetes Deployment Available.
7. Ghi incident timeline và cập nhật test/alert.

### 27.4. Rollback không chỉ là image rollback

~~~text
Image v15 + Config rev-A + Secret gen-7 => OK
Image v15 + Config rev-B + Secret gen-8 => FAIL

Rollback image v15 alone: không giải quyết vấn đề.
~~~

Nếu thay đổi là **ConfigMap value** hoặc **Secret generation**, quy trình rollback phải thay **đúng nguồn** và kích hoạt restart/refresh cần thiết. Đảm bảo schema/config giữa các phiên bản code tương thích; config mới có thể chứa key mà code cũ không hiểu hoặc thiếu key mà code mới yêu cầu.

## 28. Bài tập thực hành theo môi trường

### 28.1. Bài tập A: dev hoạt động, prod báo no-instance

**Bối cảnh:** Dev dùng SimpleDiscoveryClient với inventory-service và chạy OK. Prod đã deploy Order pods, nhưng tất cả request đến Inventory trả lỗi no-instance.

**Câu hỏi:** Kiểm tra gì trước?

**Đáp án:** Xác minh **spring.profiles.active**, service ID thực trong runtime, discovery provider/starter, namespace, registry/list ServiceInstances và supplier filters. Không suy từ việc Pod healthy rằng LoadBalancer đã tìm được backend. Không tăng retry hoặc hardcode localhost vào prod.

### 28.2. Bài tập B: đổi ConfigMap nhưng timeout không đổi

**Bối cảnh:** Ops đổi APP_INVENTORY_RESPONSE_TIMEOUT từ 2s thành 500ms trong ConfigMap. Các Pod cũ vẫn dùng giá trị trước đó.

**Đáp án:** Nếu ConfigMap được inject qua **envFrom**, process không nhận cập nhật environment mới. Cần rolling restart hoặc thiết kế volume/refresh đã được test. Ngoài ra, phải xác minh bean/HTTP request factory thực sự **dùng** property này, chứ không chỉ bind vào một record.

### 28.3. Bài tập C: Secret đã đổi nhưng Feign vẫn 401

**Bối cảnh:** Secret key đã đổi, Kubernetes volume thấy file mới, nhưng Feign RequestInterceptor vẫn gửi API key cũ.

**Đáp án:** RequestInterceptor/credential provider có thể đã chụp giá trị lúc startup. File update không tự làm mới Java field. Cần provider đọc generation mới ở thời điểm request hoặc tạo lại client/bean có kiểm soát, hoặc rolling restart. Kiểm tra Feign configuration có scope riêng, không gửi key sang service khác.

### 28.4. Bài tập D: TLS handshake chỉ lỗi một instance

**Bối cảnh:** Inventory A/B dùng certificate mới, C còn certificate cũ; Order đã bỏ CA-old khỏi truststore.

**Đáp án:** Đây là **trust rollover không đồng bộ**. Cần chiến lược dual trust cho luân chuyển bình thường, canary từng instance, xác minh selected physical host/SAN, rồi mới thu hồi CA-old. Nếu cũ đã compromise, áp security runbook và không tự bật trust-all.

### 28.5. Bài tập E: retry tạo quá nhiều request

**Bối cảnh:** Spring Cloud LoadBalancer retry 2 attempts, WebClient Reactor retry 3 attempts và mesh retry thêm 2 lần.

**Câu hỏi:** Vì sao backend có thể nhận nhiều lần gọi?

**Đáp án:** Các tầng retry **có thể nhân số attempts** khi cùng áp dụng cho một lỗi. Không giả định tổng chỉ bằng max(2,3,2). Cần xác định chính xác semantics/độ lồng của từng tầng và đếm attempts thực ở backend. Chọn một tầng retry chủ đạo, đặt deadline và idempotency.

### 28.6. Bài tập F: Config Server unavailable

**Bối cảnh:** Prod dùng spring.config.import=configserver:... không optional, Config Server tạm thời lỗi.

**Đáp án:** Startup có thể fail vì Config Data bắt buộc không tải được. Đây là hành vi có chủ đích khi cấu hình thiết yếu. Cần xử lý availability của Config Server, TLS/auth và retry bounded; không tự đổi sang **optional:** nếu điều đó dẫn tới khởi động với endpoint/auth thiếu an toàn.

### 28.7. Bài tập G: chuyển từ Kubernetes Service DNS sang Spring Cloud LoadBalancer

**Bối cảnh:** Ban đầu client gọi trực tiếp inventory-service.orders.svc.cluster.local. Sau đó muốn zone preference theo Pod metadata.

**Đáp án:** Cần xác định **Spring Cloud Kubernetes DiscoveryClient** có cung cấp các Pods và metadata zone đúng không, cấp RBAC cần thiết, đăng ký @LoadBalanced client, giữ HTTPS/SAN hợp lệ và kiểm chứng Selected ServiceInstance. Không chỉ thay Host header hoặc bật **spring.cloud.loadbalancer.zone** rồi chờ tự có Pod discovery.

## 29. Những anti-pattern dễ gây sự cố

| Anti-pattern | Hậu quả | Thay thế |
| --- | --- | --- |
| Hardcode password/API key trong application-prod.yml | Lộ credential qua Git/JAR | Secret Manager/configtree |
| Commit Secret manifest với base64 plaintext | Base64 không mã hóa bảo mật | External secret/encryption policy |
| Dùng ConfigMap để chứa private key | Quyền truy cập không phù hợp | Secret/PKI workload identity |
| Một artifact khác nhau cho mỗi môi trường chỉ để đổi config | Khó tái hiện và audit | Build once, deploy many |
| Dùng profiles làm “mã hóa” secret | Profile file vẫn đọc được | Tách secret khỏi artifact |
| Bật cả Config Server/K8s API/local imports không xác định precedence | Cấu hình khó dự đoán | Chỉ định nguồn chuẩn/priority |
| Config import optional cho secret bắt buộc | App khởi động thiếu credential | Non-optional + validation |
| Copy localhost từ dev sang Pod prod | Gọi chính Pod thay vì Inventory | Discovery/Kubernetes Service đúng |
| Coi Kubernetes Service DNS là LB client-side chọn Pod | Sai observability/routing assumption | Chọn kiến trúc rõ ràng |
| Chỉ đổi spring.cloud.loadbalancer.cache.ttl để sửa TLS | Sai lớp xử lý | Sửa certificate/HTTP connector |
| Bật retry mọi exception và HTTP method | Retry storm/duplicate side effects | Classify errors, budget/idempotency |
| Tắt hostname verification để TLS qua | Mất xác minh danh tính, nguy cơ MITM | Sửa URI/SAN/CA |
| Chỉnh Secret env và kỳ vọng JVM tự cập nhật | Giá trị cũ tồn tại | Rolling restart |
| Mount Secret qua subPath rồi chờ rotation | File không nhận update tự động | Mount directory hoặc restart |
| Chỉ reload Spring Boot server SSL bundle rồi tin outbound tự đổi | HTTP client pool vẫn cũ | Test consumer, rebuild/drain |
| Dùng Feign RequestInterceptor global cho token Inventory | Rò token sang service khác | Per-client auth provider |
| Log Environment/configprops unsanitized | Lộ secrets và URLs | Sanitization + RBAC |
| Gắn tất cả downstream vào liveness | Restart cascade khi phụ thuộc lỗi | Liveness cho chính process, readiness có chọn lọc |
| Rollback image nhưng không rollback config/secret reference | Incident không hết | Truy vết đủ ba revision |

## 30. Kịch bản tổng hợp: một image Order Service cho dev và production

Hãy hình dung cùng một image **order-service@sha256:...** được đưa qua hai môi trường.

### 30.1. Môi trường phát triển

~~~text
Profile: dev
Service ID: inventory-service
Discovery source: SimpleDiscoveryClient
Instances: 127.0.0.1:8091 và 127.0.0.1:8092
HTTP scheme: HTTP local, không gửi credential production
Retry: disabled
Response timeout: 3s
Observability: debug cục bộ, fake trace
~~~

Người học có thể kiểm tra Round Robin bằng cách gọi hai processes Inventory và ghi **instanceId trả từ backend**. Không cần Secret Manager hoặc Config Server production.

### 30.2. Môi trường production

~~~text
Profile: prod
Service ID: inventory-service
Discovery: Spring Cloud Kubernetes DiscoveryClient (nếu đã chọn mô hình)
Metadata: zone và health theo policy đã cấu hình
HTTP scheme: HTTPS/mTLS nếu bắt buộc
Retry: bounded, chỉ với lỗi/method phù hợp
Response timeout: 1500ms theo SLO
Config source: ConfigMap + Config Data
Secret source: mounted Secret/Secret Manager
Credential source: OAuth2 authorized client hoặc API key provider
Rollout: 3 replicas, readiness, canary, drain
~~~

Code nghiệp vụ vẫn chỉ cần gọi:

~~~java
StockResponse stock = inventoryRestClient.get()
        .uri("/api/stock/{sku}", sku)
        .retrieve()
        .body(StockResponse.class);
~~~

**Không cần phân nhánh trong service method** theo env:

~~~java
// Tránh thiết kế này:
if ("prod".equals(profile)) {
    return client.get("https://hardcoded-production-host");
}
return client.get("http://localhost:8091");
~~~

Thay vào đó, **RestClient bean** và **config/secret providers** là nơi quyết định service ID, transport, trust material và authorization. Business layer chỉ sử dụng một abstraction ổn định.

### 30.3. Một cấu hình không nên biến mất trong một request

Nếu cần request tracing:

~~~text
Request:
  logical service: inventory-service
  selected instance: inventory-b
  environment: prod
  config revision: release-2026-11
  credential generation: v7

Response:
  HTTP 200 / 401 / 503
  elapsed
  retry attempts
~~~

Những trường trên chỉ nên được ghi qua telemetry đã được kiểm soát. **Không** log header Authorization, private keys, access token hoặc username/password. Nếu phát hiện selected instance không đúng policy (ví dụ zone mismatch), kiểm tra **discovery metadata và supplier chain**, không sửa bằng cách thay Host header sau lựa chọn.

### 30.4. Tiêu chí nghiệm thu kịch bản

| Tiêu chí | Cách kiểm tra |
| --- | --- |
| Cùng image digest | Digest của dev/staging/prod không đổi khi chỉ thay config |
| Cấu hình đúng profile | Runtime active profiles được xác minh an toàn |
| Bí mật không nằm trong artifact | Secret scanning và kiểm tra release package |
| Service ID đúng | Test discovery và HTTP request tới instance thực |
| TLS/auth đúng | HTTPS handshake + HTTP 200/401/403 theo chính sách |
| Timeout áp dụng thật | Stub backend chậm và quan sát exception/deadline |
| Retry không nhân quá mức | Đếm attempts ở backend và caller |
| Readiness đúng | Pod không nhận traffic trước khi config/secret bắt buộc sẵn sàng |
| Rotation/rollback đúng | Test credential generation trước/sau, không dùng secret bị lộ |
| Có thể chẩn đoán | Metrics + trace không rò credential |

## 31. Checklist triển khai

### 31.1. Cấu hình và profile

- [ ] Code nghiệp vụ sử dụng **service ID/adapter**, không hardcode host IP theo môi trường.
- [ ] Có quy ước **application.yml**, **application-{profile}.yml** và nguồn external config.
- [ ] Đã xác định PropertySource precedence cho các giá trị trùng nhau.
- [ ] Profile dev dùng mock/local discovery, prod dùng nguồn discovery được phê duyệt.
- [ ] Không dùng profile như một giải pháp encryption hoặc secret storage.
- [ ] Các tham số quan trọng được bind bằng **@ConfigurationProperties** và validate.
- [ ] Giá trị timeout, retry, TTL và endpoints có owner, default và giới hạn.
- [ ] Cấu hình bắt buộc thất bại sớm nếu thiếu hoặc sai.
- [ ] Mỗi rollout có **image digest + config revision + secret generation**.

### 31.2. Secrets và authentication

- [ ] Không có API key, password, client secret, private key thật trong Git, JAR, image, CI logs.
- [ ] Kubernetes ConfigMap chỉ chứa thông số không nhạy cảm.
- [ ] Secret đến từ hệ thống quản lý credential có audit và RBAC tối thiểu.
- [ ] Đã kiểm tra Secret volume path, key name, file permissions, UID/GID.
- [ ] Không dùng subPath nếu kỳ vọng auto-update Secret volume.
- [ ] Biết env vars từ Secret/ConfigMap **không tự cập nhật trong JVM**.
- [ ] OAuth2 access token được lấy/cấp lại bằng manager/provider phù hợp.
- [ ] Client secret và mTLS private key có quy trình rotation riêng.
- [ ] Không dùng trust-all hoặc disable hostname verification.
- [ ] Không gửi Authorization header sang service/audience không được phép.
- [ ] Bảo vệ Actuator env/configprops/refresh, không expose unsanitized values.
- [ ] Có quy trình thu hồi credential khi compromise, không rollback về khóa bị lộ.

### 31.3. LoadBalancer và HTTP clients

- [ ] Tách rõ **Kubernetes Service DNS** với **Spring Cloud client-side selection**.
- [ ] DiscoveryClient đúng starter, namespace, credentials và service ID.
- [ ] ServiceInstanceListSupplier chain có cache/health/zone/hint đúng thứ tự.
- [ ] Cache TTL và registry refresh đã được đo, tránh stale instance kéo dài.
- [ ] Zone preference không được dùng làm ranh giới security/compliance.
- [ ] RestClient/RestTemplate/WebClient/Feign được cấu hình đúng kiểu @LoadBalanced.
- [ ] HTTP client giữ observability, codec, TLS và customizers của Spring Boot.
- [ ] Connection pool và connect/read/response/pool timeouts đã được thiết lập.
- [ ] Retry chỉ cho errors và HTTP methods an toàn, với attempts/backoff/deadline rõ.
- [ ] Không xếp chồng retries từ client, LoadBalancer, gateway và mesh ngoài ý muốn.
- [ ] Circuit breaker/fallback phân biệt unavailable với business result hợp lệ.
- [ ] Feign URL override không vô tình bypass LoadBalancer.

### 31.4. Kiểm thử và vận hành

- [ ] Unit test cấu hình, precedence và @ConfigurationProperties validation.
- [ ] Integration test request qua service ID và nhiều backend.
- [ ] Test no-instance, 503, connect timeout, read timeout và auth failure.
- [ ] TLS test có SAN hợp lệ và certificate/key generation mới.
- [ ] Test secret rotation/rolling restart với requests đang chạy.
- [ ] Deployment có readiness/liveness phù hợp, không tạo restart cascade.
- [ ] Có canary/rolling strategy, ngưỡng rollback và thời gian giám sát.
- [ ] Logs/metrics không lộ token, password, API key, private key hoặc tenant data.
- [ ] Có dashboard cho 401/403, TLS handshake, retries, no-instance, P95/P99.
- [ ] Có runbook rollback đủ **config, image và credential references**.
- [ ] Có owner và lịch review cho secret expiry, CA rotation, config drift.

## 32. Kết luận

Quản lý cấu hình theo môi trường và bí mật kết nối trong một hệ thống Spring Cloud LoadBalancer không đơn giản là tạo nhiều file YAML. Nó là việc xác định **nguồn sự thật**, **thứ tự ưu tiên**, **hợp đồng kiểu dữ liệu**, **vòng đời HTTP client/credential**, **chính sách rollout/rollback** và **khả năng quan sát**.

Những nguyên tắc quan trọng nhất:

1. **Một artifact, nhiều môi trường:** thay thông số triển khai bằng profiles, environment, Config Data và config stores, không nhúng host/secret vào code.
2. **Cấu hình khác bí mật:** TTL/timeout/service ID không cùng vòng đời và quyền truy cập với API key, OAuth2 client secret hay mTLS private key.
3. **LoadBalancer chỉ chọn đích:** discovery/health/zone cấu hình danh sách ứng viên; HTTP client xử lý TLS, Authorization, connection pool và timeout.
4. **Config update chưa chắc có hiệu lực ngay:** ConfigMap/Secret được cập nhật không mặc định tái tạo RestClient/WebClient/Feign hoặc SSLContext đã tồn tại.
5. **Phát hiện sai sớm, triển khai có kiểm soát:** validation, fail-fast cho secret bắt buộc, canary, readiness, tests và rollback làm giảm rủi ro.
6. **Bảo mật không được bị nới lỏng để che lỗi triển khai:** không trust-all, không hardcode credential, không retry vô hạn 401/403/TLS failures.

Khi thiết kế đúng, cùng một Order Service có thể chạy trên laptop, staging và Kubernetes production bằng cấu hình được kiểm soát, trong khi hành vi gọi **inventory-service** vẫn ổn định, có thể kiểm chứng và an toàn.

## 33. Tài liệu tham khảo

- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): PropertySource precedence, profile-specific files, spring.config.import, environment variables và configtree.
- [Spring Boot – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): kích hoạt profile, cấu hình riêng theo môi trường và profile groups.
- [Spring Boot – Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): @ConfigurationProperties, binding và validation.
- [Spring Boot – SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html): PEM/JKS bundles, key/trust material và các giới hạn SSL reload consumers.
- [Spring Boot – Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): RestClient, WebClient, request factories, customizers và SSL helpers.
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): security, exposure và sanitization của env/configprops.
- [Spring Boot – Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): liveness/readiness trong Kubernetes.
- [Spring Cloud LoadBalancer – Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): ServiceInstanceListSupplier, discovery, cache, health, zone, retry và metrics.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): các property của Spring Cloud LoadBalancer.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): @LoadBalanced RestClient, RestTemplate và WebClient.
- [Spring Cloud Config – Client](https://docs.spring.io/spring-cloud-config/reference/client.html): configserver: import, optional/fail-fast, profiles/labels và retry.
- [Spring Cloud Kubernetes – PropertySource Implementations](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config.html): Kubernetes ConfigMap/Secret sources, config import và precedence.
- [Spring Cloud OpenFeign – Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): named-client timeout, URL override, Feign retry và LoadBalancer integration.
- [Spring Security – OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): OAuth2AuthorizedClientManager, client credentials và token lifecycle.
- [Spring Security – Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): reactive token acquisition và WebClient filters.
- [Kubernetes – ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/): cách phân phối cấu hình tới Pods, môi trường và file volumes.
- [Kubernetes – Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): Secret volume/env behavior, subPath, propagation và bảo mật.
- [Kubernetes – Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/): cách quyết định khi nào Pod được nhận traffic.
- [Kubernetes – Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): RollingUpdate, rollout và rollback.
- [Micrometer – Reference](https://docs.micrometer.io/micrometer/reference/concepts.html): counters, timers, histograms và giới hạn cardinality.

