# Không để URL, tài khoản hoặc khóa bí mật cố định trong mã nguồn

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_BOOT_INTEGRATION**, một ứng dụng Spring Boot thường kết nối đồng thời tới HTTP API, cơ sở dữ liệu, cache, message broker và các adapter Spring Integration. Để vận hành an toàn, từng kết nối cần có endpoint, tài khoản, credential, chứng chỉ và các tham số như timeout, pool size, retry. Trọng tâm của module còn bao gồm hợp đồng dữ liệu, giao dịch, xử lý lỗi, chống trùng, kiểm thử và quan sát các luồng tích hợp thực tế.

Vấn đề xảy ra khi giá trị dùng để kết nối được viết cố định trong class Java, YAML đem commit cùng mã nguồn, Docker image hoặc script triển khai. Ví dụ thay đổi máy chủ database đòi hỏi sửa code và build lại, trong khi lộ token trên Git có thể trao quyền truy cập thật cho người không được phép.

**Nguyên tắc:** mã nguồn mô tả **cách kết nối**, còn môi trường triển khai cung cấp **kết nối tới đâu** và **đăng nhập bằng quyền nào**. Với giá trị nhạy cảm, cần dùng một cơ chế quản lý bí mật được bảo vệ, có quyền truy cập, audit và khả năng xoay vòng.

Sau bài học, bạn có thể:

1. Phân biệt endpoint, username, password, API token, khóa riêng, chứng chỉ và các thông số không nhạy cảm.
2. Dùng **Spring Boot Externalized Configuration** thay cho literal trong Java và cấu hình được commit.
3. Ánh xạ cấu hình bằng **@ConfigurationProperties**, placeholder và xác minh fail-fast.
4. Chọn biến môi trường, **config tree**, Kubernetes Secret hoặc secret manager theo môi trường.
5. Truyền cấu hình an toàn cho WebClient, DataSource, Redis và message broker.
6. Kiểm soát quyền truy cập, log, Actuator, CI/CD, rotation và cách khôi phục khi credential bị lộ.
7. Kiểm thử ứng dụng mà không sử dụng credential thật hoặc phụ thuộc endpoint production.

## 2. Phân loại dữ liệu kết nối trước khi cấu hình

Không phải mọi URL đều là secret; nhưng một URL cố định trong code vẫn gây coupling với môi trường, khó chuyển đổi local, test, staging và production. Ngược lại, **URL có nhúng username/password hoặc token trong query string** phải được xử lý như bí mật.

| Giá trị | Ví dụ về vai trò | Mức độ nhạy cảm | Cách quản lý |
| --- | --- | --- | --- |
| **Base URL, hostname, port** | Địa chỉ partner API, DB host, broker bootstrap servers | Thường là cấu hình; đôi khi tiết lộ topology nội bộ | Externalized config, có phân quyền truy cập môi trường |
| **Username / client ID** | Định danh tài khoản kỹ thuật | Không phải lúc nào là secret nhưng thường cần bảo vệ | Cấu hình theo môi trường, không nhúng code |
| **Password, API key, bearer token** | Chứng thực client/consumer | **Secret** | Vault/Kubernetes Secret/secret manager, quyền tối thiểu |
| **OAuth client secret / refresh token** | Lấy hoặc gia hạn access token | **Secret** | Secret manager và chính sách rotation |
| **Private key, keystore password** | TLS client authentication, chữ ký | **Secret rất nhạy cảm** | File/secret manager, hạn chế quyền đọc và audit |
| **Public certificate / CA trust bundle** | Xác minh server TLS | Thường không phải secret, nhưng phải giữ tính toàn vẹn | Artifact/config có kiểm soát version và provenance |
| **Database name, schema, virtual host, topic** | Định tuyến kết nối và phân vùng dữ liệu | Cấu hình, có thể chứa thông tin nội bộ | Externalized config |
| **Timeout, pool size, retry budget** | Giới hạn tài nguyên, hành vi lỗi | Không phải secret | Cấu hình theo môi trường, kiểm thử và theo dõi |

Điểm cốt lõi là **tách yêu cầu bí mật khỏi yêu cầu thay đổi cấu hình**. Đưa URL ra biến môi trường giải quyết khả năng triển khai; đưa token ra một biến môi trường chỉ giải quyết việc không ghi literal trong code, **chưa tự tạo mã hóa, audit, TTL hoặc rotation**.

### Ví dụ cần tránh

~~~java
// ANTI-PATTERN: không viết tài khoản/secret trong class.
public final class PartnerClient {
    private static final String BASE_URL =
            "https://partner-production.example.internal";
    private static final String USERNAME = "service-prod";
    private static final String PASSWORD = "production-password";
    private static final String API_TOKEN = "replace-with-real-token";
}
~~~

Các chuỗi trên chỉ là ví dụ minh họa **những thứ không được làm**, không phải credential hợp lệ. Dù file bị xóa ở commit mới, secret thật vẫn có thể tồn tại trong Git history, image layers, build logs, bản sao CI và hệ thống tìm kiếm mã nguồn.

**Không chỉ cấm hard-code literal trong Java.** Cần kiểm soát mọi nơi credential có thể bị nhúng:

- **application.yml/application.properties** được commit cùng dự án;
- tệp **.env** vô tình được đưa lên Git;
- Dockerfile **ENV/ARG** hoặc lệnh build có secret;
- Kubernetes manifest/Helm values chứa token thật;
- shell script, Gradle/Maven settings, tài liệu ví dụ, log test;
- URL có query chứa key, connection string có embedded password;
- screenshot, issue tracker, chat, bản sao cấu hình khi debug.

## 3. Kiến trúc cấu hình được tách khỏi mã nguồn

~~~mermaid
flowchart TD
    A["Application code + artifact bất biến"] --> B["Spring Boot Environment / Binder"]
    C["Config chung: versioned YAML"] --> B
    D["Deployment variables / ConfigMap"] --> B
    E["Secret manager / configtree / workload identity"] --> B
    B --> F["Validated @ConfigurationProperties"]
    B --> G["Credential provider"]
    F --> H["WebClient / DataSource / Redis / Broker clients"]
    G --> H
    H --> I["Downstream services"]
    J["Observability + audit có kiểm soát"] -.-> H
~~~

Nguyên tắc vận hành:

1. **Một artifact** có thể dùng cho nhiều môi trường mà không sửa source code.
2. Endpoint được gán theo environment hoặc tenant đã được kiểm soát; không đọc trực tiếp từ input chưa xác thực.
3. Credential do runtime cung cấp bằng kênh an toàn; quyền cấp đủ cho chính service đang chạy.
4. Cấu hình bắt buộc được **validate lúc startup** hoặc trước khi mở consumer traffic.
5. Khi secret thay đổi, ứng dụng có quy trình **refresh/reconnect** chứ không giả định mọi bean tự dùng giá trị mới.
6. Log/trace/metric chỉ thể hiện trạng thái cấu hình an toàn, **không xuất credential**.

## 4. Spring Boot Externalized Configuration

Spring Boot đọc thuộc tính từ nhiều nguồn: cấu hình đóng gói trong ứng dụng, cấu hình ngoài artifact, biến môi trường, Java system properties, command-line arguments, **config tree** và các nguồn được tích hợp thêm như Vault/Config Server. Tùy phiên bản, thứ tự precedence cụ thể có khác biệt; khi cùng tên property xuất hiện ở nhiều nguồn, **nguồn có precedence cao hơn** quyết định giá trị cuối.

Đừng đoán “giá trị cuối chắc nằm trong application.yml”. Kiểm tra theo cơ chế Environment/ConfigData của đúng phiên bản Boot và thiết kế tránh khai báo nhiều chỗ cho cùng một secret.

### 4.1. application.yml chỉ chứa tên property và placeholder

Ví dụ cho một dịch vụ tích hợp nhiều loại kết nối:

~~~yaml
app:
  integration:
    partner:
      base-url: ${PARTNER_API_BASE_URL}
      request-timeout: ${PARTNER_API_TIMEOUT:3s}
      token: ${PARTNER_API_TOKEN}

spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_APP_USERNAME}
    password: ${DB_APP_PASSWORD}
    hikari:
      maximum-pool-size: ${DB_POOL_MAX_SIZE:12}
      connection-timeout: 2s

  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6379}
      password: ${REDIS_PASSWORD}

  rabbitmq:
    host: ${RABBITMQ_HOST}
    port: ${RABBITMQ_PORT:5672}
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    virtual-host: ${RABBITMQ_VHOST}
~~~

**Điều kiện của ví dụ:** ứng dụng thực sự sử dụng những starter tương ứng (JDBC, Redis, AMQP, WebClient). Không sao chép tất cả khóa cấu hình vào dịch vụ chỉ cần HTTP; chỉ khai báo kết nối đang được sử dụng. Những placeholder không có giá trị mặc định như **PARTNER_API_TOKEN** phải được cung cấp từ môi trường hoặc nguồn secret hợp lệ.

- **PARTNER_API_BASE_URL** chứa endpoint, không phải credential.
- **PARTNER_API_TOKEN** là bí mật; không ghi giá trị thật vào YAML.
- Các default như **3s**, **12** hoặc **6379** minh họa thông số không nhạy cảm. Chúng cần được điều chỉnh theo tải, SLO, TLS và kiến trúc thực tế.
- **DB_JDBC_URL** không được chứa username/password trong URL hay query parameter nếu driver có thể nhận chúng qua thuộc tính riêng. Một JDBC URL chứa credential phải được coi là secret.
- **spring.data.redis.password** và **spring.rabbitmq.password** chỉ là ví dụ cho nguồn có password. Với IAM, mTLS, OAuth hoặc SASL hiện đại, cần chọn cơ chế chứng thực phù hợp thay vì mặc định username/password.

### 4.2. Placeholder, default và fail-fast

Spring hỗ trợ cú pháp:

~~~yaml
# Không có default: deployment phải cung cấp.
app.integration.partner.base-url: ${PARTNER_API_BASE_URL}

# Có default cho giá trị không nhạy cảm:
app.integration.partner.request-timeout: ${PARTNER_API_TIMEOUT:3s}
~~~

**Không đặt default giả cho secret production**, chẳng hạn một password dễ đoán hoặc một token cố định. Điều đó khiến ứng dụng âm thầm chạy với quyền sai và che khuất lỗi cấu hình.

Với giá trị bắt buộc, khi placeholder chưa được giải quyết hoặc kiểu giá trị sai, ứng dụng nên thất bại sớm ở bước bind/validate thay vì gửi request tới một endpoint không xác định. Lưu ý **một property không được dùng/bind** có thể không gây fail-fast; muốn kiểm soát toàn bộ tập config quan trọng, phải đăng ký và validate properties một cách chủ đích.

### 4.3. Profile: chọn chính sách, không chứa secret thật

~~~yaml
# application-dev.yml, không phải nơi chứa credential thật.
app:
  integration:
    partner:
      request-timeout: 5s
~~~

~~~yaml
# application-prod.yml, vẫn chỉ là cấu hình phi bí mật.
app:
  integration:
    partner:
      request-timeout: 2s
~~~

Profile có thể được chọn bằng **SPRING_PROFILES_ACTIVE** ở môi trường chạy. Không dùng profile làm “kho secret” bằng cách commit **application-prod.yml** có password. Các tệp profile vẫn có thể bị đóng gói trong JAR hoặc image.

## 5. @ConfigurationProperties và kiểm tra trước khi mở kết nối

**@ConfigurationProperties** giúp biểu diễn hợp đồng cấu hình thành kiểu Java, hỗ trợ chuyển đổi URI, Duration và kiểm tra giá trị. Nó phù hợp hơn việc rải hàng chục **@Value** trong nhiều class.

### 5.1. Typed properties chỉ chứa thông tin không nhạy cảm

~~~java
import java.net.URI;
import java.time.Duration;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.integration.partner")
public record PartnerClientProperties(
        @NotNull URI baseUrl,
        @NotNull Duration requestTimeout) {
}
~~~

Đăng ký properties trong ứng dụng:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class IntegrationApplication {
    public static void main(String[] args) {
        SpringApplication.run(IntegrationApplication.class, args);
    }
}
~~~

Để annotation **@NotNull** và validation trên configuration properties hoạt động, dự án phải có Bean Validation provider phù hợp, thường được bổ sung qua **spring-boot-starter-validation**. Kiểm tra module và import theo phiên bản Spring Boot (ví dụ Boot 3.x sử dụng **jakarta.validation**).

**Tách token khỏi record** ở ví dụ này vì mặc định **record.toString()** có thể in toàn bộ trường chứa secret. Nếu một class cấu hình bắt buộc giữ secret, không tự log object đó và nên cân nhắc **toString() có che giá trị** hoặc một abstraction chỉ cung cấp credential tại thời điểm sử dụng.

### 5.2. Validate endpoint và cấu hình không hợp lệ

Chỉ dùng **@NotNull** chưa đủ nếu URI chỉ ra host sai, scheme không phù hợp hoặc có embedded credentials.

~~~java
import java.net.URI;

public final class PartnerEndpointPolicy {
    private PartnerEndpointPolicy() {}

    public static void verify(PartnerClientProperties properties) {
        URI uri = properties.baseUrl();
        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null
                || uri.getUserInfo() != null) {
            throw new IllegalStateException(
                    "Partner base URL must be HTTPS without user-info");
        }
        if (properties.requestTimeout().isZero()
                || properties.requestTimeout().isNegative()) {
            throw new IllegalStateException(
                    "Partner timeout must be positive");
        }
    }
}
~~~

Hàm **verify** kiểm tra dữ liệu đã bind và sẽ được gọi khi tạo WebClient ở phần tiếp theo; không tạo thêm bean **PartnerClientProperties** cạnh bean do **@ConfigurationPropertiesScan** đăng ký. Trong ứng dụng thật, có thể chuyển kiểm tra này thành **Bean Validation custom constraint** hoặc constructor invariant. Điều kiện **HTTPS** cho production phải được kiểm tra ở đúng environment; endpoint **localhost HTTP** cho test cần chính sách ngoại lệ rõ, không cho phép thay bằng bất kỳ HTTP URL nào ở production.

### 5.3. Một cấu hình WebClient sử dụng giá trị được inject

~~~java
@Configuration(proxyBeanMethods = false)
public class PartnerWebClientConfiguration {

    @Bean
    WebClient partnerWebClient(
            WebClient.Builder builder,
            PartnerClientProperties properties,
            @Value("${app.integration.partner.token}") String token) {

        PartnerEndpointPolicy.verify(properties);
        return builder
                .baseUrl(properties.baseUrl().toString())
                .defaultHeaders(headers -> headers.setBearerAuth(token))
                .build();
    }
}
~~~

**@Value** ở đây minh họa cách dùng placeholder có sẵn để nhận secret; production có thể thay bằng **TokenProvider/SecretProvider** để hỗ trợ rotation. Không in **token**, không in **Authorization header**, không log **WebClient.Builder** hay các object cấu hình khi chúng có thể giữ credential. **defaultHeaders(setBearerAuth)** giữ token đã được lấy lúc tạo bean: nếu secret thay đổi sau đó, bean này **không tự cập nhật**.

Nếu partner dùng OAuth client credentials, tốt hơn là dùng một thành phần **OAuth2AuthorizedClientManager** hoặc auth provider phù hợp để tự lấy access token ngắn hạn, cache có giới hạn và refresh theo giao thức, thay vì sao chép client secret vào nhiều WebClient bean.

### 5.4. Tránh tạo DataSource thủ công khi Boot đã hỗ trợ

Với kết nối JDBC thông thường, nên để **Spring Boot auto-configure DataSource** từ **spring.datasource.\***:

~~~java
@Repository
public class OrderJdbcRepository {
    private final JdbcTemplate jdbc;

    public OrderJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int markReady(String orderId) {
        return jdbc.update(
                "UPDATE orders SET ready = true WHERE id = ?",
                orderId);
    }
}
~~~

Repository không biết tên host, database username hoặc password. Pool lấy thông tin đăng nhập từ cấu hình môi trường; transaction manager dùng chung DataSource theo cấu hình Spring.

Khi nhiều datasource hoặc driver đặc thù đòi cấu hình bằng code, vẫn đưa credential vào property/provider được inject, không đưa literal vào **DataSourceBuilder**, **DriverManager.getConnection(...)** hay lệnh SQL.

## 6. Biến môi trường: hữu ích nhưng chưa phải secret manager

Biến môi trường là một kênh phân phối cấu hình phổ biến, nhưng có giới hạn:

- Có thể được đọc bởi process, debugger hoặc người có quyền thao tác vào runtime.
- Có thể lộ qua tool hỗ trợ, crash dump, thread dump có kèm environment, shell history hoặc các command hiển thị cấu hình.
- Không mặc nhiên có versioning, rotation, expiration và audit.
- Thường chỉ được đọc khi process khởi động; thay đổi môi trường trên hệ điều hành không tự thay đổi giá trị đã bind trong bean.

**Không đưa credential lên command line** kiểu **--password=...** hoặc Java **-D...password=...** nếu có lựa chọn an toàn hơn. Command line có thể bị giữ trong process listing, log hoặc lịch sử triển khai.

### Local development

Một ví dụ script thiết lập môi trường nên dùng secret lấy từ công cụ quản lý của nhóm, không chép password thật vào file:

~~~text
Môi trường local
  → Công cụ cấp quyền/secret manager dành cho developer
  → Export biến môi trường tạm cho process Java
  → Spring Boot resolve placeholder
  → Kết nối endpoint test/dev
~~~

Tệp **.env** trong nhiều môi trường dev chỉ là quy ước của Docker Compose hoặc công cụ shell. **Spring Boot không mặc nhiên tự đọc mọi tệp .env** chỉ vì file đó nằm trong thư mục dự án; cần cấu hình công cụ triển khai để truyền biến vào process hoặc import nguồn config phù hợp.

Nếu dùng file local không theo dõi bởi Git để phát triển, phải cấu hình ignore, permission và không dùng credential production. **.gitignore không phải biện pháp khắc phục khi secret đã từng bị commit**.

## 7. Config tree và secret được mount dưới dạng file

Spring Boot hỗ trợ **config tree**: tên file trở thành tên property, nội dung file trở thành giá trị. Cách này phù hợp khi orchestrator mount secret thành file mà không cần đưa giá trị vào source hoặc biến môi trường.

Ví dụ môi trường runtime có:

~~~text
/run/secrets/
    partner.token
    database.password
~~~

Đường dẫn đó là **file trong container runtime**, không phải file lưu trong Git. Trong **application.yml**:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  datasource:
    password: ${database.password}

app:
  integration:
    partner:
      token: ${partner.token}
~~~

Ví dụ cấu hình này có thể được dùng thay cho các placeholder môi trường tương ứng ở phần 4; **không khai báo cả hai cùng lúc mà không có chủ đích**, vì thứ tự các property sources có thể che mất nguồn mong muốn. **configtree:** và **optional:configtree:** có semantics khác nhau: với production, không nên thêm **optional:** chỉ để ứng dụng âm thầm khởi động khi mount secret bị thiếu.

Trong Kubernetes, có thể mount Secret thành volume:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: integration-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: integration-service
  template:
    metadata:
      labels:
        app: integration-service
    spec:
      containers:
        - name: app
          image: registry.example.invalid/integration-service:stable
          volumeMounts:
            - name: credentials
              mountPath: /run/secrets
              readOnly: true
      volumes:
        - name: credentials
          secret:
            secretName: integration-credentials
~~~

Manifest này chỉ **tham chiếu tên Secret**; không chứa nội dung Secret và không tự tạo Secret. Người vận hành cần cấp RBAC, bảo vệ Kubernetes API/etcd, hạn chế quyền đọc volume và chọn cơ chế phân phối secret phù hợp. Kubernetes Secret thường biểu diễn dữ liệu ở dạng **Base64 trong manifest/API**, **không đồng nghĩa đã được mã hóa đầu cuối**. Phải cấu hình encryption-at-rest, RBAC và audit cho cluster.

**Lưu ý rotation:** khi secret mounted volume được cập nhật, file trên filesystem có thể đổi theo cơ chế orchestrator, nhưng giá trị đã bind thành String hoặc đã được WebClient/connection pool giữ trong bộ nhớ **không tự refresh**. Cần thiết kế reload/reconnect hoặc rolling restart một cách an toàn.

## 8. Secret manager và workload identity

Với production, sử dụng một hệ quản lý secret có thể là:

- **HashiCorp Vault**;
- một **cloud secret manager** của nền tảng đang dùng;
- **Kubernetes Secrets** kết hợp cơ chế quản lý và đồng bộ được bảo vệ;
- **Spring Cloud Vault** hoặc cơ chế **spring.config.import**/**ConfigData** tương ứng để tải property từ nguồn bên ngoài;
- workload identity/IAM hoặc **mTLS** thay password tĩnh khi giao thức downstream hỗ trợ.

### Lợi ích và giới hạn

| Khả năng | Tác dụng |
| --- | --- |
| **RBAC, namespace, policy** | Một service chỉ đọc được những secret cần thiết |
| **Audit** | Truy vết ai/identity nào đã yêu cầu secret, lúc nào |
| **Versioning, rotation** | Đổi credential không cần thay source code |
| **Lease, TTL** | Giảm thời gian credential bị lộ còn hữu dụng |
| **Workload identity** | Tránh phải đặt một “mật khẩu để lấy mật khẩu” trong image |
| **Encryption at rest/in transit** | Bảo vệ dữ liệu trong kho và trên đường phân phối |
| **High availability** | Giảm nguy cơ secret manager thành điểm lỗi đơn |

Secret manager vẫn có thể bị cấu hình sai quyền. **Không cấp quyền list/read mọi secret**, không cho một consumer đọc credential của nhiều hệ thống không liên quan, và không dùng chung tài khoản production cho local developer hoặc CI test.

### Trường hợp cần token ngắn hạn

Thay vì giữ một token tĩnh mãi trong **@ConfigurationProperties**, có thể inject một **CredentialProvider**:

~~~java
public interface PartnerTokenProvider {
    String currentAccessToken();
}

@Bean
WebClient partnerWebClient(
        WebClient.Builder builder,
        PartnerClientProperties properties,
        PartnerTokenProvider tokenProvider) {

    ExchangeFilterFunction bearerAuthentication =
            (request, next) -> {
                ClientRequest authenticated = ClientRequest
                        .from(request)
                        .headers(headers -> headers.setBearerAuth(
                                tokenProvider.currentAccessToken()))
                        .build();
                return next.exchange(authenticated);
            };

    return builder
            .baseUrl(properties.baseUrl().toString())
            .filter(bearerAuthentication)
            .build();
}
~~~

**PartnerTokenProvider là interface do ứng dụng định nghĩa**, không phải một implementation có sẵn của Spring Boot. Implementation cần xử lý cache theo expiry, refresh, phân quyền, chặn thundering herd và lỗi secret manager. Một provider gọi network **blocking** ngay trong WebClient filter có thể chặn event-loop: hãy dùng một cơ chế async/reactive phù hợp, hoặc cache token được refresh an toàn ở luồng riêng. Ví dụ minh họa nơi gắn token, **không** giải quyết toàn bộ bài toán OAuth/refresh.

## 9. TLS và chứng chỉ cũng là cấu hình kết nối

Không hard-code URL và password mà lại **tắt xác minh TLS** là một lỗi nghiêm trọng. Trong ứng dụng tích hợp, địa chỉ và bí mật phải đi cùng chính sách xác thực máy chủ.

### 9.1. Những điều cần làm

1. Sử dụng HTTPS/TLS khi giao tiếp qua mạng hoặc theo yêu cầu môi trường.
2. Kiểm tra hostname và chuỗi tin cậy của certificate; không tắt certificate validation trong production.
3. Nếu dùng **mTLS**, bảo vệ private key và keystore password bằng secret storage.
4. Có quy trình rotate cert trước hạn hết hiệu lực và giám sát lỗi handshake.
5. Dùng CA/truststore có nguồn gốc rõ; không tự động tin cậy mọi chứng chỉ để “sửa lỗi” cấu hình.
6. Khi dùng Spring Boot SSL bundles, cấu hình đường dẫn, nội dung và password từ nguồn bên ngoài. Khả năng reload bundle phụ thuộc connector và phiên bản, nên phải kiểm thử.

### 9.2. URI không được chứa mật khẩu

Không tạo request như:

~~~text
https://user:password@partner.example.invalid/api
https://partner.example.invalid/api?access_token=SECRET
jdbc:postgresql://host/shop?user=admin&password=SECRET
~~~

Các giá trị đó chỉ minh họa cấu trúc có rủi ro, không phải credential thật. URL dễ bị đưa vào access log, proxy log, tracing tags, monitoring, exception messages hoặc browser history. Ưu tiên cơ chế header/credential provider của giao thức và cấu hình riêng theo môi trường.

**Cảnh báo SSRF:** chỉ vì endpoint đến từ cấu hình không có nghĩa luôn an toàn nếu ứng dụng cho người dùng bên ngoài quyết định giá trị đó. Với API nhận URL động, phải dùng allowlist destination, hạn chế scheme/host, bảo vệ mạng egress, xác minh DNS/redirect theo threat model. Không biến **base-url** đã được cấu hình thành giá trị tùy ý của request chưa xác thực.

## 10. Rotation: thay secret mà không mất dịch vụ

Tách secret khỏi source chỉ là bước đầu. Khi password bị lộ, hết hạn hoặc cần đổi định kỳ, dịch vụ phải có cách tiếp nhận secret mới mà không tạo ra nhiều lỗi kết nối.

~~~mermaid
flowchart TD
    A["Secret cũ đang được ứng dụng dùng"] --> B["Tạo credential mới ở backend/secret manager"]
    B --> C["Cho credential cũ và mới cùng hợp lệ trong giai đoạn chuyển tiếp nếu hỗ trợ"]
    C --> D["Cập nhật runtime config / token provider"]
    D --> E["Refresh hoặc rolling restart client/connection pool"]
    E --> F["Xác minh health, auth failures, metrics"]
    F --> G["Thu hồi credential cũ"]
    G --> H["Audit kết quả rotation"]
~~~

### 10.1. HTTP API token

- Với token ngắn hạn, dùng token provider có cơ chế tự refresh trước expiry.
- Phân biệt **401** do token hết hạn với **403** do không đủ quyền; retry mọi 401 không giới hạn có thể tạo vòng lặp và rate-limit.
- Nếu WebClient dùng static **defaultHeaders(setBearerAuth(token))** từ token được bind lúc startup, giá trị không đổi cho tới khi client được rebuild hoặc process restart.

### 10.2. Database account

- **HikariCP** giữ các kết nối JDBC đã xác thực, không tự thay credential của tất cả connection đang mở khi secret store đổi.
- Nếu đổi password ở server, connection cũ có thể còn hoạt động một thời gian, nhưng connection mới có thể thất bại nếu pool chưa nhận password mới.
- Cần chiến lược cập nhật **DataSource/connection pool**, dùng credential chồng lấn trong giai đoạn chuyển đổi khi DB hỗ trợ, và giám sát connection acquisition/authentication failures.
- Không đưa password vào exception log khi chẩn đoán lỗi pool.

### 10.3. Broker và cache

- RabbitMQ/JMS/Redis/Kafka clients có kết nối dài hạn và reconnect policy khác nhau.
- Đổi secret có thể chỉ phát hiện khi client reconnect; một container đang chạy “healthy” không chứng minh credential mới đã hoạt động.
- Nếu broker dùng SASL/OAuth hoặc TLS client certificate, rotation phải đi cùng config của consumer/producer, bootstrap/reconnect và quyền topic/queue.
- Thực hiện canary hoặc rolling deployment để tránh mọi consumer mất kết nối đồng thời.

### 10.4. Sự cố lộ credential

Khi phát hiện secret thật từng bị commit:

1. **Thu hồi/rotate ngay credential** ở hệ thống cấp quyền; chỉ xóa dòng code là chưa đủ.
2. Giảm hoặc vô hiệu hóa quyền truy cập không cần thiết.
3. Điều tra log truy cập và audit trong thời gian credential có hiệu lực.
4. Xác định nơi đã sao chép (Git history, CI artifact, image, logs, developer machine).
5. Làm sạch lịch sử/bản sao theo quy trình tổ chức sau khi secret đã bị thu hồi; tránh làm gián đoạn công việc nhóm do rewrite Git history không phối hợp.
6. Bổ sung scan/pre-commit/pipeline để tránh tái diễn.

Không dán lại giá trị secret bị lộ trong ticket, chat hay thông báo sự cố.

## 11. CI/CD, image và quyền truy cập deployment

### 11.1. Pipeline không được trở thành nơi phát tán bí mật

Các kiểm soát thiết thực:

- Secret chỉ được cấp cho **job, environment và service account** cần nó.
- Pipeline dùng **short-lived identity/credential** nếu nền tảng hỗ trợ.
- Không echo biến môi trường chứa secret, không chạy shell debug với chế độ in mọi lệnh/giá trị.
- Không đưa credential vào Maven/Gradle command-line, artifact metadata, report test hoặc cache build.
- Chạy **secret scanning** trên commit/pull request và kiểm tra secret có trong Docker build context.
- CI test dùng database/broker/container test và credential dùng riêng, không dùng production secrets.
- Tách quyền **deploy**, **read secret**, **rotate secret** và **audit** theo nguyên tắc least privilege.

### 11.2. Docker build và runtime khác nhau

~~~text
Build:
  source + dependencies
  → JAR/container image
  → KHÔNG chứa secret production

Deploy:
  image bất biến
  + cấu hình môi trường
  + secret runtime được cấp quyền
  → process Spring Boot
~~~

**Dockerfile ARG/ENV không phải vault.** Giá trị có thể nằm trong image layers, build history, cache hoặc metadata. Nếu build cần credential để tải dependency từ registry riêng, dùng **build secret mount/identity được hỗ trợ bởi builder**, không copy token vào layer rồi xóa sau.

### 11.3. GitOps và manifest

GitOps vẫn có thể giữ tên Secret, tham chiếu ConfigMap, policy và cấu hình phi bí mật trong Git. Không commit **Secret data** ở dạng cleartext hoặc chỉ Base64. Nếu dùng Sealed Secrets/SOPS/encrypted manifests, phải kiểm soát **key management**, quyền giải mã, rotation và đường đi của plaintext.

## 12. Tránh lộ secret qua Actuator, log và exception

### 12.1. Spring Boot Actuator

Actuator có thể cung cấp **env**, **configprops**, **beans**, **loggers**, **heapdump** và nhiều endpoint phục vụ vận hành. Một số giá trị có cơ chế sanitization, nhưng **sanitization không phải hàng rào bảo mật duy nhất**: cấu hình hiện tại, custom endpoint, log hoặc dump có thể chứa thông tin nhạy cảm theo cách khác.

Ví dụ chỉ expose endpoint cần thiết:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
~~~

Ngoài danh sách exposure, cần kiểm soát **network, authentication, authorization** và chính sách thu thập metrics/log/traces. Không mở **/actuator/env**, **/actuator/configprops** hoặc **/actuator/heapdump** ra mạng công cộng để “xem thử cấu hình”.

### 12.2. Log an toàn

Tránh:

~~~java
// Không làm: có thể đưa URL nội bộ hoặc secret ra log.
log.info("Partner config: {}", properties);
log.debug("Authorization: {}", request.headers().get("Authorization"));
log.error("Environment: {}", System.getenv());
~~~

Nên log **trạng thái** thay vì giá trị:

~~~java
log.info(
        "Partner client configured: operation={}, authConfigured={}, " +
        "requestTimeoutMs={}",
        "customer-lookup",
        tokenProvider != null,
        properties.requestTimeout().toMillis());
~~~

Ngay cả trường **authConfigured=true** chỉ cho biết đã cấu hình một provider, không chứng minh token hợp lệ. Không dùng health check để trả lại secret hoặc log header Authorization; health nên dựa trên phép kiểm tra có quyền tối thiểu, tránh gây side effect và quá tải downstream.

### 12.3. Metrics và distributed tracing

Với Micrometer/OpenTelemetry:

- Không dùng token, username, tenant ID nhạy cảm hoặc URL chứa credential làm metric label.
- HTTP client metrics nên có **operation/route template**, không gắn raw URL có query động.
- Span attributes có thể chứa server address và path; lọc query parameters, Authorization/Cookie và body.
- Phân biệt lỗi DNS, TLS, authentication, rate limiting và application-level rejection khi phân loại.

Nếu cần debug giá trị cấu hình, có thể log **tên property, nguồn cấu hình đã xác thực hoặc hash không thể đảo ngược** của một định danh không nhạy cảm; tránh hash mật khẩu yếu/đoán được vì hash thô cũng có thể tạo dữ liệu nhạy cảm.

## 13. Kiểm thử không phụ thuộc production secret

Đối với integration test, nên sử dụng **MockWebServer/WireMock**, **Testcontainers** hoặc database/broker dành riêng cho test, với các giá trị endpoint được cấp động.

### 13.1. Cấp endpoint động qua @DynamicPropertySource

Ví dụ minh họa cho HTTP client test dùng **MockWebServer** đã được khởi động trước khi Spring test context tạo:

~~~java
@SpringBootTest
class PartnerClientIntegrationTest {

    static final MockWebServer server = startTestServer();

    @DynamicPropertySource
    static void partnerProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "app.integration.partner.base-url",
                () -> server.url("/").toString());
        registry.add(
                "app.integration.partner.request-timeout",
                () -> "1s");
        registry.add(
                "app.integration.partner.token",
                () -> UUID.randomUUID().toString());
    }

    // Enqueue response giả rồi assert request dùng đúng endpoint,
    // có Authorization header và không phát tán token ra logs.
}
~~~

**startTestServer()** là helper ứng dụng test phải tự hiện thực, bảo đảm server đã start trước khi context resolve URL và đóng server sau test. Token ngẫu nhiên trong ví dụ là **giá trị giả chỉ dùng trong test**, không phải secret production. Nếu cấu hình production bắt buộc HTTPS, hãy dùng test TLS hoặc chính sách allow HTTP chỉ trong test, không vô hiệu hóa TLS verification ở runtime production.

### 13.2. Test thiếu cấu hình bắt buộc

Kiểm tra ứng dụng **từ chối khởi động** nếu:

- **PARTNER_API_BASE_URL** chưa được cung cấp;
- URI không hợp lệ hoặc scheme không được phép;
- **PARTNER_API_TOKEN** thiếu/blank;
- DB password không có ở source bắt buộc;
- cấu hình mTLS thiếu private key hoặc trust material;
- timeout âm, pool size = 0 hoặc biến giá trị sai kiểu.

Với **ApplicationContextRunner** (trong Spring Boot test), có thể kiểm chứng một context tối thiểu fail binding/validation mà không khởi động broker/DB. Dùng test với config giả, không chạy thật tới service bên ngoài.

### 13.3. Test nhiều môi trường bằng một artifact

Một test triển khai quan trọng:

~~~text
Cùng một JAR / container image
   + môi trường A → endpoint mock/database A
   + môi trường B → endpoint mock/database B

Không build lại source code.
Không dùng credential hoặc địa chỉ production trong test.
Không đổi tên property khi chuyển môi trường.
~~~

Ngoài test property binding, cần kiểm tra **thời điểm fail-fast**, metrics lỗi kết nối, health startup/readiness và khả năng ứng dụng phục hồi khi secret manager tạm thời không sẵn sàng.

## 14. Troubleshooting theo nguyên nhân, không in cấu hình

Khi xảy ra lỗi:

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra an toàn |
| --- | --- | --- |
| Could not resolve placeholder | Chưa cấp biến môi trường/secret file | Kiểm tra property name và nguồn cấp; chỉ log trạng thái có/không |
| BindException / validation fail | URI, Duration, port hoặc pool size sai | Kiểm tra schema và kiểu; không dump toàn Environment |
| Connection refused / DNS failure | Endpoint/port, service discovery hoặc mạng | Kiểm tra egress, DNS, host/port đã được phê duyệt |
| TLS handshake error | CA, hostname, cert hết hạn hoặc keystore | Kiểm tra certificate chain và time, không tắt verify |
| HTTP 401/403 | Token hết hạn hoặc thiếu quyền | Kiểm tra auth provider, scope và audit; không log token |
| DB authentication error | Username/password/role sai hoặc secret đổi | Xác minh secret version, pool lifecycle, grants |
| Pool acquisition timeout | Downstream chậm hoặc pool cạn | Quan sát active/idle/pending và transaction duration |
| Broker reconnect loop | SASL/TLS/ACL, host hoặc credential mới chưa được reload | So sánh version secret, broker audit và client metrics |
| Chỉ production lỗi | Profile khác, path mount, precedence, IAM hoặc egress policy | Kiểm tra config provenance ở mức metadata |
| Sau rotate vẫn lỗi | Bean, socket hoặc pool còn credential cũ | Xác minh reload/rolling restart và connection mới |

**Không sửa lỗi bằng cách nhúng tạm username/password vào code rồi “sẽ xóa sau”.** Thay vào đó, thiết lập luồng cấp credential test, kiểm tra IAM/RBAC và chuẩn hóa startup validation.

### Một runbook ngắn cho lỗi mất kết nối

~~~mermaid
flowchart TD
    A["Ứng dụng không kết nối được"] --> B{"Có config bắt buộc?"}
    B -->|"Không"| C["Sửa source cấp config, fail-fast"]
    B -->|"Có"| D{"Endpoint/DNS/TLS hợp lệ?"}
    D -->|"Không"| E["Sửa endpoint, CA, network/egress"]
    D -->|"Có"| F{"Credential còn hiệu lực và đúng quyền?"}
    F -->|"Không"| G["Rotate/cấp lại quyền, kiểm tra audit"]
    F -->|"Có"| H["Kiểm tra pool, timeout, retry và downstream health"]
    H --> I["Khắc phục và xác minh qua metric, không in secrets"]
~~~

## 15. Checklist trước khi phát hành

1. **Không có URL môi trường cụ thể, username thật, password, API key, private key** được hard-code trong Java, YAML commit, Dockerfile hoặc pipeline.
2. Cấu hình được chia thành endpoint, thông số vận hành và credential; những giá trị nhạy cảm được cấp bởi nguồn bảo mật phù hợp.
3. Property name được chuẩn hóa; **@ConfigurationProperties** hoặc bean config validate được các trường bắt buộc.
4. Production không có default password/token yếu; thiếu secret làm fail-fast có kiểm soát.
5. Các account được cấp theo **least privilege**, riêng cho từng môi trường, service và loại tài nguyên.
6. TLS và hostname verification hoạt động; keystore/private key không nằm trong image, log hoặc repo.
7. Endpoint của HTTP/JDBC/Redis/Kafka/JMS có timeout, pool/concurrency, retry và budget phù hợp.
8. Secret manager có audit, chính sách rotation, TTL và readiness/failure mode đã được kiểm thử.
9. Khi secret rotate, đã xác minh client, pool và broker reconnect/rebuild đúng thay vì dùng credential cũ vô hạn.
10. Actuator/env/configprops/heapdump được bảo vệ; logs/traces/metrics không chứa Authorization header, raw token hoặc connection string nhạy cảm.
11. CI/CD có secret scanning, không in env và không đóng gói secret vào Docker layers; workload identity và RBAC được kiểm tra.
12. Test chỉ dùng mock/ephemeral infrastructure, không dùng endpoint hoặc tài khoản production.
13. Có runbook thu hồi credential bị lộ và cơ chế đối soát hậu sự cố.
14. Có cảnh báo sớm về authentication failure, TLS expiry, connect timeout và sự cố secret manager mà không tiết lộ giá trị bí mật.

**Kết luận:** không hard-code thông tin kết nối giúp cùng một ứng dụng Spring Boot chạy được trên nhiều môi trường và giảm nguy cơ lộ quyền truy cập. Nhưng để bảo vệ một luồng tích hợp thực tế, cần đi xa hơn việc chuyển password sang biến môi trường: **quản lý bí mật tập trung, validate cấu hình, giới hạn quyền, TLS, rotation, kiểm thử, quan sát và quy trình xử lý sự cố** phải được thiết kế thành một hệ thống thống nhất.

## Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): nguồn cấu hình, placeholder, precedence, config tree và property binding.
- [Spring Boot Reference — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): phân tách cấu hình theo môi trường.
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): @ConfigurationProperties và constructor binding.
- [Spring Boot Reference — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html): Bean Validation và kiểm tra cấu hình.
- [Spring Boot Reference — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure, bảo mật và dữ liệu quản trị.
- [Spring Cloud Vault Reference](https://docs.spring.io/spring-cloud-vault/reference/): quản lý secret với Vault qua Spring.
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): Secret objects, volumes, RBAC và lưu ý bảo mật.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): vòng đời credential, least privilege, rotation và audit.
- [The Twelve-Factor App — Config](https://12factor.net/config): tách cấu hình deployment khỏi mã nguồn.
