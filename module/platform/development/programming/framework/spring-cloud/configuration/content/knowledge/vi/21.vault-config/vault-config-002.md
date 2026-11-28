# Nạp bí mật bằng spring.config.import=vault://

Spring Cloud Vault cho phép ứng dụng Spring Boot nạp bí mật từ HashiCorp Vault như một nguồn cấu hình trong Spring Environment. Với Config Data API, ứng dụng khai báo `spring.config.import: "vault://"`; Spring Cloud Vault kết nối Vault, đọc các context được cấu hình theo application và profile, rồi đưa các key/value vào quá trình binding của Spring Boot.

Điểm quan trọng của cách tích hợp này là Config Client kết nối trực tiếp tới Vault để lấy secret. Đây là đường nạp cấu hình riêng của Spring Cloud Vault, khác với việc cấu hình Spring Cloud Config Server dùng Vault làm backend. Có thể dùng Vault cùng Config Server, nhưng cần phân định rõ dữ liệu nào lấy từ Config Server và dữ liệu bí mật nào lấy trực tiếp từ Vault, đồng thời kiểm tra thứ tự ưu tiên khi hai nguồn cùng khai báo một key.

## 1. Luồng nạp secret bằng Config Data API

Khi ứng dụng khởi động, Spring Boot đọc các Config Data locations. Location `vault://` yêu cầu Spring Cloud Vault tạo property source từ Vault:

~~~mermaid
flowchart LR
    A[Spring Boot startup] --> B[spring.config.import=vault://]
    B --> C[Spring Cloud Vault]
    C --> D[Authenticate to Vault]
    D --> E[Read KV contexts]
    E --> F[Spring Environment]
    F --> G[ConfigurationProperties / Value]
~~~

Luồng cơ bản:

1. Ứng dụng xác định Vault URI, phương thức xác thực, backend và context cần đọc.
2. Spring Cloud Vault xác thực với Vault bằng token hoặc danh tính workload.
3. Vault kiểm tra policy của danh tính và chỉ trả về các secret được phép đọc.
4. Spring Cloud Vault đọc các context phù hợp với application và profile.
5. Các property source được đưa vào Spring Environment.
6. Spring Boot bind property vào bean hoặc cho phép ứng dụng đọc qua Environment.

Giá trị không được mã hóa lại bởi Config Server trong luồng này. Vault là nơi lưu trữ và kiểm soát truy cập secret; Spring Cloud Vault là thành phần lấy secret vào process của ứng dụng.

## 2. Thêm dependency Spring Cloud Vault

Với Maven, thêm starter:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-vault-config</artifactId>
</dependency>
~~~

Project cần quản lý phiên bản Spring Boot và Spring Cloud bằng các BOM tương thích. Starter này cung cấp tích hợp Vault Config Data và các thành phần cần thiết để đọc secret. Nếu ứng dụng còn dùng Config Server, giữ thêm dependency Config Client tương ứng.

Ví dụ một ứng dụng vừa lấy cấu hình thông thường từ Config Server vừa lấy secret trực tiếp từ Vault có thể khai báo:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-config</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-vault-config</artifactId>
    </dependency>
</dependencies>
~~~

Không tự ghép các phiên bản starter độc lập. Hãy dùng Spring Cloud release train tương thích với phiên bản Spring Boot của ứng dụng.

## 3. Khai báo vault:// trong application.yml

Ví dụ ứng dụng tên orders-service đọc secret từ Vault KV version 2:

~~~yaml
spring:
  application:
    name: orders-service

  profiles:
    active: prod

  config:
    import: "vault://"

  cloud:
    vault:
      uri: https://vault.internal:8200
      authentication: TOKEN
      token: ${VAULT_TOKEN}
      kv:
        enabled: true
        backend: secret
        backend-version: 2
        default-context: application
        application-name: orders-service
        profile-separator: "_"
~~~

Ý nghĩa các thuộc tính:

| Thuộc tính | Ý nghĩa |
|---|---|
| spring.config.import | Đăng ký Vault như một Config Data location |
| spring.cloud.vault.uri | Địa chỉ Vault server, nên dùng HTTPS ngoài môi trường local |
| spring.cloud.vault.authentication | Phương thức xác thực |
| spring.cloud.vault.token | Token được cấp cho ứng dụng; ví dụ lấy từ biến môi trường |
| spring.cloud.vault.kv.enabled | Bật tích hợp KV secrets engine |
| spring.cloud.vault.kv.backend | Tên mount của KV engine, ví dụ secret |
| spring.cloud.vault.kv.backend-version | Phiên bản KV engine, ví dụ 2 |
| spring.cloud.vault.kv.default-context | Context dùng chung, thường là application |
| spring.cloud.vault.kv.application-name | Context riêng cho ứng dụng |
| spring.cloud.vault.kv.profile-separator | Ký tự nối tên context và profile; ví dụ dùng dấu gạch dưới |

`application-name` được đặt tường minh để đường dẫn Vault không phụ thuộc vào việc tên ứng dụng runtime có bị thay đổi ở môi trường khác hay không. Trong hệ thống đơn giản, có thể đồng bộ giá trị này với `spring.application.name`.

Không ghi token thật vào application.yml, Config Repository hoặc image container. Placeholder `${VAULT_TOKEN}` chỉ đọc giá trị được cấp ở runtime; bản thân biến môi trường cũng cần được bảo vệ bằng secret management của nền tảng.

## 4. Tổ chức KV theo application và profile

Spring Cloud Vault có thể đọc các context chung và context riêng theo application/profile. Với cấu hình ví dụ:

- Backend: secret
- Default context: application
- Application name: orders-service
- Active profile: prod
- Profile separator: dấu gạch dưới

Các logical context thường dùng có dạng:

| Phạm vi | Logical path trong KV mount |
|---|---|
| Cấu hình dùng chung | application |
| Cấu hình dùng chung cho prod | application_prod |
| Cấu hình riêng của orders-service | orders-service |
| Cấu hình riêng của orders-service cho prod | orders-service_prod |

Với KV v2 được mount tại secret, Vault API lưu dữ liệu dưới endpoint có thành phần data, ví dụ `secret/data/orders-service`. Tuy nhiên, khi dùng Vault CLI, đường dẫn logical thường không cần tự thêm `data` vì CLI và Spring Cloud Vault xử lý chi tiết API KV v2.

Ví dụ ghi dữ liệu bằng Vault CLI:

~~~bash
vault kv put -mount=secret application \
  platform.banner="Internal services"

vault kv put -mount=secret orders-service \
  secrets.database.username="orders_app"

vault kv put -mount=secret orders-service_prod \
  secrets.database.password="replace-with-secret-value"
~~~

Đây là ví dụ dữ liệu minh họa; không dùng password mẫu trong môi trường thật. Tên key có thể dùng dấu chấm để biểu diễn property phân cấp của Spring. Cần thống nhất cách đặt key giữa người quản lý secret và mã nguồn ứng dụng.

Spring Cloud Vault xây dựng các property source theo context chung, application và profile. Thứ tự ưu tiên giữa các context cần được xác minh bằng Environment thực tế của phiên bản đang dùng; không nên suy ra chỉ từ thứ tự ghi secret vào Vault.

## 5. Đọc secret trong ứng dụng

Sau khi Vault property source được nạp, ứng dụng có thể bind secret bằng `@ConfigurationProperties`. Ví dụ:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "secrets.database")
public record DatabaseSecretProperties(
        String username,
        String password) {
}
~~~

Đăng ký properties bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Sau đó inject vào cấu hình DataSource hoặc thành phần cần dùng:

~~~java
import javax.sql.DataSource;

import org.springframework.boot.jdbc.DataSourceBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DatabaseConfiguration {

    @Bean
    DataSource dataSource(DatabaseSecretProperties secrets) {
        return DataSourceBuilder.create()
                .username(secrets.username())
                .password(secrets.password())
                .build();
    }
}
~~~

Ví dụ trên minh họa cách bind, không phải cấu hình DataSource production đầy đủ. Trong ứng dụng thực tế, nên dùng Spring Boot DataSource auto-configuration hoặc cấu hình connection pool phù hợp thay vì tự tạo DataSource đơn giản như ví dụ.

Cũng có thể dùng `@Value`:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class PartnerService {

    private final String apiToken;

    public PartnerService(
            @Value("${partner.api-token}") String apiToken) {
        this.apiToken = apiToken;
    }
}
~~~

Chỉ đọc secret ở thành phần cần dùng. Tránh tạo một object tổng hợp chứa tất cả secret của ứng dụng rồi truyền rộng khắp hệ thống.

## 6. Xác thực với Vault

Ứng dụng phải xác thực trước khi đọc secret. Chọn phương thức xác thực dựa trên môi trường chạy:

| Môi trường | Phương thức phù hợp | Lưu ý |
|---|---|---|
| Local development | Token có TTL ngắn, cấp riêng cho developer | Không dùng root token hoặc token production |
| Kubernetes | Kubernetes auth | Vault xác minh service account token và role của workload |
| VM hoặc workload có danh tính cloud | AWS IAM, Azure hoặc GCP auth theo nền tảng | Dùng identity của workload thay cho secret tĩnh nếu có thể |
| CI/CD hoặc hệ thống triển khai | AppRole hoặc cơ chế workload identity được phê duyệt | Role và secret ID phải được giới hạn, luân chuyển và bảo vệ |

### 6.1. Token cho môi trường phát triển

Ví dụ cấu hình token:

~~~yaml
spring:
  cloud:
    vault:
      uri: https://vault.dev.internal:8200
      authentication: TOKEN
      token: ${VAULT_TOKEN}
~~~

Token phải có policy chỉ đọc đúng các path cần thiết. Không dùng token có quyền quản trị toàn Vault. Không truyền token qua command line nếu có nguy cơ bị lưu trong process list hoặc shell history.

### 6.2. Kubernetes authentication

Trong Kubernetes, ứng dụng thường dùng service account identity để xác thực với Vault. Cấu hình khái niệm:

~~~yaml
spring:
  cloud:
    vault:
      uri: https://vault.vault.svc:8200
      authentication: KUBERNETES
      kubernetes:
        role: orders-service
~~~

Vault cần được cấu hình Kubernetes auth method, reviewer role và policy gắn với service account/namespace tương ứng. Ứng dụng không nên đóng gói token dài hạn vào image. Spring Cloud Vault dùng service account token theo cấu hình và đường dẫn mặc định hoặc đường dẫn được chỉ định cho phiên bản đang dùng.

## 7. Policy giới hạn quyền đọc

Vault policy quyết định một workload được đọc path nào. Với KV v2 mount tên secret, API data path chứa segment data. Ví dụ policy HCL giới hạn quyền đọc các context cần thiết:

~~~hcl
path "secret/data/application" {
  capabilities = ["read"]
}

path "secret/data/application_prod" {
  capabilities = ["read"]
}

path "secret/data/orders-service" {
  capabilities = ["read"]
}

path "secret/data/orders-service_prod" {
  capabilities = ["read"]
}
~~~

Gắn policy này vào role hoặc token của orders-service theo cơ chế xác thực đang dùng. Nếu ứng dụng không cần đọc cấu hình dùng chung, bỏ các path application tương ứng. Nếu dùng KV v1, đường dẫn policy khác vì không có segment data của KV v2; không sao chép policy KV v2 sang mount KV v1 mà không điều chỉnh.

Không cấp quyền list hoặc read toàn bộ mount chỉ để làm cho ứng dụng chạy được. Cấp đúng path cần thiết và kiểm tra policy bằng một danh tính thử nghiệm có cùng role với workload.

## 8. KV v1 và KV v2

KV v1 và KV v2 có API path và khả năng versioning khác nhau:

| Đặc điểm | KV v1 | KV v2 |
|---|---|---|
| Dữ liệu | Giá trị key/value tại path | Dữ liệu có version và metadata |
| API data path | Mount/path | Mount/data/path |
| API metadata path | Không có metadata version như KV v2 | Mount/metadata/path |
| Khôi phục version | Thường cần backup riêng | Có thể đọc version trước theo chính sách engine |
| Khai báo Spring Cloud Vault | backend-version: 1 | backend-version: 2 |

KV v2 hữu ích khi cần version history và khả năng khôi phục dữ liệu. Tuy nhiên, versioning không thay thế backup, audit hoặc quy trình phê duyệt. Quyền truy cập API data và metadata cần được cân nhắc riêng theo nhu cầu của ứng dụng.

Nếu backend đã được mount dưới dạng KV v2 nhưng ứng dụng khai báo backend-version là 1, request có thể sai endpoint và bị lỗi. Hãy xác nhận mount thực tế bằng công cụ quản trị Vault và cấu hình Spring Cloud Vault khớp với phiên bản engine.

## 9. Kết hợp Vault với Config Server

Một ứng dụng có thể lấy cấu hình không nhạy cảm từ Spring Cloud Config Server và secret từ Vault. Ví dụ:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import:
      - "configserver:https://config-server.internal"
      - "vault://"
  cloud:
    vault:
      uri: https://vault.internal:8200
      authentication: KUBERNETES
      kubernetes:
        role: orders-service
      kv:
        enabled: true
        backend: secret
        backend-version: 2
        default-context: application
        application-name: orders-service
~~~

Trong mô hình này:

- Config Server cung cấp cấu hình dịch vụ được quản trị tập trung như timeout, feature policy và endpoint không bí mật.
- Vault cung cấp database password, API token, private integration secret và credential cần kiểm soát truy cập.
- Client có hai kết nối độc lập: tới Config Server và tới Vault.

Thứ tự property source khi có nhiều Config Data imports cần được kiểm tra trong ứng dụng. Tránh khai báo cùng một key ở cả Config Server và Vault nếu không có chủ đích. Nếu buộc phải trùng, ghi rõ nguồn nào là nguồn có thẩm quyền và xác minh giá trị hiệu lực bằng Spring Environment.

Đây là mô hình client đọc trực tiếp từ Vault. Nếu muốn Config Server đứng giữa và cung cấp Vault như backend cho nhiều client, đó là cách triển khai khác với cấu hình backend Vault của Config Server; không đồng nhất hai cơ chế chỉ vì đều sử dụng Vault.

## 10. Vault không truy cập được: fail-fast hay optional?

Khi khai báo:

~~~yaml
spring:
  config:
    import: "vault://"
~~~

Vault là nguồn cấu hình bắt buộc. Nếu không thể kết nối hoặc xác thực/đọc path cần thiết, quá trình khởi động có thể thất bại. Đây thường là lựa chọn phù hợp nếu secret là điều kiện để ứng dụng hoạt động an toàn.

Nếu môi trường phát triển có fallback an toàn và chấp nhận chạy khi Vault tạm thời không khả dụng, có thể dùng:

~~~yaml
spring:
  config:
    import: "optional:vault://"
~~~

Không dùng optional chỉ để che giấu lỗi xác thực hoặc policy. Nếu password database bắt buộc nhưng không nạp được, ứng dụng nên dừng khởi động thay vì chạy với chuỗi rỗng, credential mẫu hoặc cấu hình yếu.

Có thể phân biệt các tình huống:

- Vault không thể kết nối: kiểm tra DNS, network, TLS và health của Vault.
- Authentication thất bại: kiểm tra auth method, role, token và TTL.
- Permission denied: kiểm tra policy và path KV v1/v2.
- Không tìm thấy secret: kiểm tra backend mount, context, application name và profile.
- Giá trị bind sai kiểu: kiểm tra tên key, format và validation phía ứng dụng.

## 11. Xác minh secret đã được nạp

Không cần in giá trị bí mật ra console để xác nhận tích hợp. Có thể kiểm tra theo nhiều tầng:

1. Kiểm tra log startup để xác nhận Vault Config Data location được xử lý.
2. Xác nhận Vault audit log có request từ workload identity đúng.
3. Dùng một property không nhạy cảm trong context kiểm thử để xác minh path và profile.
4. Kiểm tra bean configuration đã bind và validation thành công.
5. Kiểm tra ứng dụng kết nối được tới database hoặc dịch vụ cần secret.
6. Kiểm tra policy bằng cách thử đọc một path ngoài phạm vi và xác nhận bị từ chối.

Ví dụ kiểm tra bean mà không in password:

~~~java
import org.springframework.stereotype.Component;

@Component
public class SecretReadiness {

    private final DatabaseSecretProperties properties;

    public SecretReadiness(DatabaseSecretProperties properties) {
        this.properties = properties;
    }

    public boolean hasRequiredCredentials() {
        return properties.username() != null
                && !properties.username().isBlank()
                && properties.password() != null
                && !properties.password().isBlank();
    }
}
~~~

Chỉ expose trạng thái readiness phù hợp; không trả secret hoặc độ dài secret ra endpoint công khai. Tốt hơn nữa, kiểm tra kết nối thực tế tới hệ thống đích bằng health indicator được thiết kế an toàn.

Actuator endpoint env có thể hiển thị tên property source và giá trị tùy cấu hình. Nếu dùng để chẩn đoán, giới hạn quyền, đặt chế độ che giá trị và không bật hiển thị plaintext trong production. Secret sau khi được nạp vào Environment vẫn là dữ liệu nhạy cảm trong memory của process.

## 12. Lease và dynamic secrets

KV thường lưu secret tĩnh theo context. Vault còn có các secrets engine tạo credential động, ví dụ database secrets engine. Credential động thường có lease duration và có thể được gia hạn hoặc thu hồi theo vòng đời lease.

Không nên coi mọi giá trị đọc qua Vault KV là dynamic secret. KV versioning và lease renewal là hai cơ chế khác nhau:

- KV v2 lưu nhiều version của secret nhưng giá trị thường tồn tại cho đến khi bị cập nhật/xóa theo chính sách.
- Dynamic secrets được tạo theo request, có TTL/lease và có thể hết hạn hoặc bị revoke.

Nếu ứng dụng dùng dynamic database credentials, phải kiểm tra Spring Cloud Vault có module và cấu hình tương ứng cho secrets engine đó, đồng thời xác định connection pool xử lý khi credential được gia hạn hoặc thay mới như thế nào. Việc lấy được credential lúc startup chưa đủ chứng minh pool sẽ tự đổi password khi lease hết hạn.

## 13. Bảo vệ secret sau khi nạp

Vault kiểm soát việc đọc secret ở phía server, nhưng sau khi client nhận secret, ứng dụng phải bảo vệ dữ liệu trong process và trên đường truyền:

- Dùng HTTPS và xác minh certificate của Vault.
- Cấp danh tính riêng cho từng workload; không chia sẻ token quản trị.
- Giới hạn policy theo application, profile và path thực sự cần.
- Không log secret, không đưa vào exception message, tracing tag hoặc metric label.
- Bảo vệ Actuator env/configprops và các endpoint chẩn đoán tương tự.
- Không truyền secret qua command line nếu có thể bị ghi trong process list hoặc shell history.
- Hạn chế quyền đọc environment variables và filesystem của container.
- Không ghi secret vào heap dump hoặc diagnostic bundle có quyền truy cập rộng.
- Có quy trình rotation credential và xử lý khi token/secret bị lộ.

Nếu Config Server và Vault cùng được dùng, không đưa secret vào Git chỉ để Config Server phân phối lại. Hãy giữ secret ở Vault và để client có danh tính riêng đọc đúng path. Nếu cần proxy secret qua một service trung gian, phải thiết kế authorization và audit theo từng client.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách kiểm tra |
|---|---|---|
| Không nhận diện vault:// | Thiếu spring-cloud-starter-vault-config hoặc BOM không tương thích | Kiểm tra dependency và phiên bản Spring Cloud |
| Không kết nối được Vault | Sai URI, DNS, port, TLS hoặc network policy | Kiểm tra từ đúng container/host chạy ứng dụng |
| 401 từ Vault | Token hết hạn hoặc auth method sai | Kiểm tra authentication, role và TTL |
| 403 permission denied | Policy không cho đọc path | So sánh KV logical path với API path trong policy |
| Không tìm thấy property | Sai backend, default context, application name hoặc profile separator | Kiểm tra cấu hình KV và path trong Vault |
| KV v2 trả lỗi path | Khai báo backend-version sai hoặc policy thiếu segment data | Xác nhận mount version và policy path |
| Client đọc nhầm secret context | Tên application/profile không như dự kiến | Kiểm tra spring.application.name, active profiles và property sources |
| Secret bị giá trị local ghi đè | Trùng key giữa Vault và Config Data source khác | Kiểm tra Environment và thứ tự imports |
| Ứng dụng khởi động dù thiếu secret | Dùng optional:vault:// hoặc có default không an toàn | Xác định secret bắt buộc và validation startup |
| Credential động hết hạn | Chưa xử lý lease renewal hoặc pool không đổi credential | Kiểm tra lease lifecycle và tích hợp secrets engine |

## 15. Quy trình đưa Vault Config vào môi trường thật

1. Chọn KV v1 hoặc KV v2 và xác nhận mount path.
2. Quy định default context, application name, profile separator và naming convention.
3. Tạo policy chỉ đọc các path mà ứng dụng cần.
4. Cấu hình auth method theo workload identity; tránh token tĩnh dài hạn.
5. Cấu hình Vault URI bằng HTTPS và triển khai trust chain.
6. Thêm spring-cloud-starter-vault-config và import vault://.
7. Ghi secret vào context dùng chung hoặc context riêng theo ứng dụng/profile.
8. Bind secret bằng ConfigurationProperties và validation.
9. Kiểm tra startup, audit log, kết nối hệ thống đích và quyền bị từ chối ngoài phạm vi.
10. Bảo vệ endpoint Actuator và log; thiết lập quy trình rotation và thu hồi.

## 16. Checklist vận hành

- [ ] Dependency Spring Cloud Vault tương thích với Spring Boot/Spring Cloud.
- [ ] spring.config.import có vault:// hoặc optional:vault:// theo chính sách rõ ràng.
- [ ] Vault URI dùng HTTPS và certificate được xác minh.
- [ ] Authentication dùng danh tính workload phù hợp.
- [ ] Không có root token hoặc credential production trong source code.
- [ ] KV backend và backend-version khớp mount thực tế.
- [ ] Application name, default context và profile separator đã thống nhất.
- [ ] Policy chỉ cho phép đọc các path cần thiết.
- [ ] Secret bắt buộc được validate khi khởi động.
- [ ] Không log hoặc expose secret qua Actuator.
- [ ] Đã kiểm tra property source và giá trị bind mà không in plaintext.
- [ ] Có kế hoạch rotation, revoke và xử lý lease nếu dùng dynamic secrets.

`spring.config.import=vault://` đưa Vault vào quy trình nạp cấu hình của Spring Boot. Khi backend, context application/profile, authentication và policy được cấu hình đúng, ứng dụng có thể lấy secret trực tiếp từ Vault và bind vào các thành phần cần dùng. Để vận hành an toàn, hãy giữ secret ngoài Git, cấp quyền theo workload, kiểm tra giá trị mà không hiển thị plaintext và quản lý riêng vòng đời của KV secret với dynamic credentials có lease.
