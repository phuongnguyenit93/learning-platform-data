# Quyền ưu tiên cấu hình và các bean do từng thành phần quản lý

## 1. Bài toán tích hợp Spring Vault trong ứng dụng Spring Boot

Một ứng dụng Java có thể nhận cấu hình từ `application.yml`, biến môi trường, tham số dòng lệnh, Spring Cloud Vault và các `@Bean` tự định nghĩa. Khi hai nguồn cùng đặt một thuộc tính hoặc hai thành phần cùng tạo một bean, kết quả có thể khác điều nhóm phát triển dự kiến:

- `spring.datasource.password` tồn tại cả trong secret KV và biến môi trường triển khai. Ứng dụng thực sự dùng giá trị nào?
- `VaultTemplate` được Spring Cloud Vault auto-configuration tạo sẵn, nhưng lập trình viên cũng khai báo `@Bean VaultTemplate`. Bean nào được inject?
- Một service dùng `@Value` để lấy cấu hình khi khởi tạo, sau đó secret trong Vault được đổi. Service có tự nhận giá trị mới?
- `ClientAuthentication` đăng nhập Vault bằng Kubernetes workload identity; một cấu hình tự viết lại dùng token cố định. Đâu là danh tính thực sự được sử dụng?
- `SecretLeaseContainer` đã nhận credential database mới, nhưng HikariCP vẫn dùng kết nối cũ. Thành phần nào có trách nhiệm chuyển đổi pool?

Chủ đề **“Quyền ưu tiên cấu hình và các bean do từng thành phần quản lý”** giúp trả lời các câu hỏi đó một cách có hệ thống. Trong module **SPRING_VAULT**, các nguyên tắc này áp dụng không chỉ cho KV secrets mà còn cho token/lease, Transit encryption, PKI, dynamic database credentials, xử lý lỗi và kiểm thử tích hợp.

Phải phân biệt ba cơ chế:

1. **Property source precedence:** Spring `Environment` quyết định giá trị nào thắng khi nhiều nguồn cùng cung cấp một key.
2. **Bean registration và dependency injection:** Spring `ApplicationContext` quyết định bean nào được tạo, bean nào thỏa mãn một dependency và bean nào bị loại theo điều kiện auto-configuration.
3. **Secret/token lifecycle:** Vault và các thành phần Spring Vault quyết định khi nào secret được đọc, token được renew/re-auth, lease được gia hạn hoặc credential được thay thế.

Một property có mức ưu tiên cao **không** đồng nghĩa với một bean có mức ưu tiên cao. Một secret được rotate trong Vault **không** đồng nghĩa với một `DataSource` đang chạy sẽ tự đổi username/password.

## 2. Các thành phần chịu trách nhiệm ở từng tầng

| Thành phần | Trách nhiệm chính | Không nên gán nhầm trách nhiệm |
|---|---|---|
| Spring Boot `Environment` / `ConfigData` | Nạp và sắp xếp property sources; giải quyết key theo thứ tự ưu tiên | Không tự tạo token Vault hay tự luân chuyển JDBC pool |
| Spring Cloud Vault Config Data | Kết nối Vault để đưa secrets được cấu hình vào `Environment` | Không có nghĩa mọi lời gọi `VaultTemplate.read` đều trở thành property |
| Spring Cloud Vault auto-configuration | Cấu hình infrastructure Vault và các bean có điều kiện theo starter/phiên bản | Không bảo đảm vẫn giữ đúng lựa chọn mặc định sau khi ứng dụng tự định nghĩa bean cùng loại |
| Spring Vault Core | Cung cấp `VaultTemplate`, `VaultOperations`, `ClientAuthentication`, `SessionManager` và thao tác với secrets engines | Không áp đặt thứ tự ưu tiên của `application.yml` và CLI |
| `VaultTemplate` / `VaultOperations` | Thực hiện request đến Vault ở thời điểm code gọi | Không tự copy kết quả đọc KV vào toàn bộ property sources |
| `ClientAuthentication` | Lấy Vault token từ phương thức auth đã chọn | Không quản lý mật khẩu DB hoặc PKI certificate của ứng dụng |
| `SessionManager` | Cung cấp và có thể quản lý vòng đời token cho client | Không thay thế lease manager của database dynamic secrets |
| `SecretLeaseContainer` / lease integration | Theo dõi secret lease, renew/rotate khi được thiết lập phù hợp | Không tự bảo đảm mọi bean nghiệp vụ hoặc connection pool đã được tạo lại |
| `@ConfigurationProperties` / `@Value` | Đọc/bind một giá trị từ `Environment` vào bean | Không mặc định cập nhật live bean mỗi lần secret ở Vault đổi |
| `DataSource` / HikariCP | Quản lý kết nối vật lý đến database | Không tự hiểu vòng đời Vault lease nếu ứng dụng không tích hợp |

Sơ đồ mô tả hai đường đi khác nhau từ Vault vào ứng dụng:

~~~mermaid
flowchart TD
    A["Vault KV / Dynamic secrets / Transit / PKI"] --> B["Spring Cloud Vault Config Data"]
    A --> C["Spring Vault: VaultTemplate / VaultOperations"]
    B --> D["Environment / PropertySources"]
    D --> E["@Value / @ConfigurationProperties"]
    E --> F["Bean ứng dụng: DataSource, service, client"]
    C --> G["Request Vault khi runtime"]
    G --> H["Dữ liệu phản hồi / Lease"]
    H --> I["Code nghiệp vụ / lease listener"]
    I --> F
    J["ClientAuthentication + SessionManager"] --> C
    J --> B
~~~

Với `VaultTemplate.read("secret/...")`, code nhận `VaultResponse`; nếu không có phần ghi/binding bổ sung, `Environment` không tự xuất hiện key mới. Với `spring.config.import=vault://`, Spring Cloud Vault nạp các secret backend được chọn thành property sources ở giai đoạn xây dựng cấu hình.

## 3. Chọn cách tích hợp trước khi viết cấu hình

Hai hướng phổ biến có thể cùng sử dụng thư viện Spring Vault nhưng có **người sở hữu infrastructure khác nhau**.

| Hướng | Dependency/khởi tạo | Ai sở hữu bean Vault cốt lõi? | Điểm cần chú ý |
|---|---|---|---|
| Spring Vault Core trực tiếp | Thư viện `spring-vault-core`; cấu hình `VaultTemplate`, auth/session bằng Java | Ứng dụng tự chịu trách nhiệm | Phải quản lý endpoint, TLS, workload auth và vòng đời token |
| Spring Cloud Vault với Spring Boot | Starter `spring-cloud-starter-vault-config`, `spring.config.import=vault://` hoặc cơ chế bootstrap phù hợp phiên bản | Auto-configuration của Spring Cloud Vault quản lý phần lớn infrastructure | Tránh khai báo lại bean lõi nếu không có yêu cầu rõ và test quyết định của auto-config |

**Quyết định quan trọng:** ứng dụng dùng starter Spring Cloud Vault để tự cấu hình bean và property source, hay tự dựng Spring Vault Core. Nếu dùng cả hai cần có bản thiết kế rõ bean nào thuộc nhóm tự quản lý và bean nào bị auto-configuration loại trừ.

Spring Boot xử lý `@Bean`, `@Configuration`, `@ConditionalOnMissingBean` và `@Primary` bằng luật bean registration/autowiring riêng. Chúng **không** đọc tên key `spring.cloud.vault.*` rồi tự xác định một bean tùy ý “ưu tiên hơn” theo cùng cơ chế property source.

## 4. Property source precedence trong Spring Boot

Spring Boot tổng hợp nhiều `PropertySource` thành `Environment`. Khi tra cứu cùng một key, giá trị thuộc **nguồn có độ ưu tiên cao nhất trong Environment hiện tại** được chọn.

Trong ứng dụng Spring Boot phổ biến dùng Config Data, thứ tự thường thấy từ **cao xuống thấp** khi các nguồn cùng đặt một thuộc tính là:

1. Tham số dòng lệnh `--app.feature.mode=...` (nếu command-line property source đang bật).
2. Java system properties và biến môi trường hệ điều hành theo thứ tự ưu tiên Spring Boot quy định.
3. Config Data từ `application.yml`, profile files và các nguồn import như `vault://`, xét theo quy tắc import/profile.
4. Nguồn mặc định của ứng dụng.

Bảng này chỉ mô tả các nguồn tiêu biểu. `@TestPropertySource`, test annotations, `SPRING_APPLICATION_JSON`, servlet/JNDI, custom `EnvironmentPostProcessor` và legacy bootstrap có vị trí riêng. **Không suy luận mọi ứng dụng đều có cùng thứ tự** nếu có thêm cơ chế tùy chỉnh; cần quan sát `Environment.getPropertySources()` trong chính ứng dụng.

### Ví dụ xung đột cấu hình

Giả sử các nguồn cung cấp:

| Nguồn | Key | Giá trị minh họa |
|---|---|---|
| `application.yml` | `orders.retry.max-attempts` | `2` |
| Secret KV được import | `orders.retry.max-attempts` | `4` |
| Biến môi trường `ORDERS_RETRY_MAXATTEMPTS` (tên phù hợp relaxed binding) | `orders.retry.max-attempts` | `6` |
| Tham số khởi chạy | `--orders.retry.max-attempts=8` | `8` |

Trong cách khởi tạo Config Data Spring Boot thông thường, tham số dòng lệnh thắng và ứng dụng nhận `8`. Nếu bỏ tham số dòng lệnh, biến môi trường có thể thắng `6`. Nếu bỏ tiếp biến môi trường, giá trị từ Vault hoặc file local được chọn theo thứ tự **Config Data imports và profile documents**.

Để tránh mơ hồ về ánh xạ tên biến môi trường, hãy cấu hình/kiểm tra theo hướng dẫn relaxed binding của chính phiên bản Spring Boot đang dùng; với key phân cấp sử dụng dấu chấm, ký hiệu phân tách và dấu gạch nối có quy tắc chuẩn hóa riêng.

### Quy tắc với Config Data import

Khi một file `application.yml` khai báo `spring.config.import=vault://`, các tài liệu Config Data được import được đưa vào thứ tự xử lý do Spring Boot quy định. Theo cơ chế Config Data, **giá trị từ nguồn được import có thể được ưu tiên hơn các giá trị khai báo trong file đã kích hoạt import**. Nếu có nhiều imports hoặc profile files, thứ tự giải quyết phụ thuộc vị trí import và tài liệu/profile được kích hoạt.

Không đưa ra lời khẳng định chung rằng “Vault luôn thắng `application.yml`” hoặc “Vault luôn thắng mọi biến môi trường”. Legacy bootstrap có thể có thứ tự khác với Config Data; custom property source cũng có thể thay đổi kết quả.

### Điều cần kiểm tra khi property là secret

Nếu `spring.datasource.password` có trong Vault KV nhưng biến môi trường triển khai cũng đặt key đó, ứng dụng **có thể dùng mật khẩu từ biến môi trường** theo thứ tự thực tế. Vì vậy, việc Vault chứa secret đúng chưa đủ để xác nhận DataSource đã sử dụng nó. Để chẩn đoán, hãy xác minh **nguồn được chọn** thay vì in giá trị mật khẩu ra log.

## 5. Cấu hình Spring Cloud Vault Config Data

Ví dụ ứng dụng `orders-api` chạy trong Kubernetes, Vault có mount KV v2 logic `secret/`. YAML minh họa:

~~~yaml
spring:
  application:
    name: orders-api
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "${VAULT_URI}"
      authentication: KUBERNETES
      kubernetes:
        role: orders-api
      kv:
        enabled: true
        backend: secret
~~~

Spring Boot giải quyết placeholder **`${VAULT_URI}`** từ môi trường khởi động; nếu không cung cấp biến `VAULT_URI`, ứng dụng nên fail fast theo cách cấu hình đã chọn.

Kubernetes authentication thường sử dụng service account JWT của pod và role đã cấu hình trên Vault. Ví dụ này giả định auth mount Kubernetes và endpoint/TLS Vault đã được cấu hình đúng; các tên path, namespace và thông số TLS cần phù hợp hạ tầng thực.

Ví dụ dữ liệu KV v2 ở đường dẫn logic `secret/orders-api`:

~~~text
orders.retry.max-attempts = 4
orders.api.base-url = https://orders-internal.example.test
~~~

Spring Cloud Vault có thể đưa những key ấy vào `Environment` khi ứng dụng khởi động theo cấu hình context/kv backend. Với KV v2, API thực tế có đoạn `data`, nhưng trong cấu hình Spring Cloud Vault ta thường chỉ định tên backend logic `secret` và context tương ứng; không tự chèn `data` vào tên context.

Các thông số cần phân biệt:

| Property | Vai trò |
|---|---|
| `spring.config.import` | Quyết định nạp nguồn Config Data, ví dụ `vault://` |
| `spring.cloud.vault.uri` | Địa chỉ Vault để client kết nối |
| `spring.cloud.vault.authentication` | Phương thức xác thực workload, ví dụ `KUBERNETES` |
| `spring.cloud.vault.kubernetes.role` | Role trong Kubernetes auth của Vault |
| `spring.cloud.vault.kv.backend` | Secret engine mount logic cung cấp property sources |
| `spring.application.name` | Tên ứng dụng; có thể ảnh hưởng tới context mặc định của KV property source |

**Cảnh báo phụ thuộc khởi động:** Vault client cần biết URI, phương thức auth và thông tin đăng nhập **trước khi** có thể nạp các secret từ Vault. Không thiết kế cấu hình vòng lặp, chẳng hạn cố lấy chính `spring.cloud.vault.uri` hoặc dữ liệu Kubernetes auth đầu tiên từ property source Vault mà client phải kết nối tới mới đọc được.

### Dùng `optional:vault://` khi nào?

Spring Boot hỗ trợ cú pháp optional cho các Config Data imports, nhưng cần hiểu phạm vi hành vi của phiên bản Spring Cloud Vault đang dùng. `optional:vault://` có thể làm ứng dụng tiếp tục khi một nguồn import tùy chọn không có mặt; **không nên coi đó là cách bỏ qua mọi lỗi 403, TLS, thiếu policy hoặc lỗi authentication**. Với secrets bắt buộc (database password, API credential quan trọng), hãy ưu tiên fail fast và test đường khởi động thất bại rõ ràng.

### Không trộn legacy bootstrap và Config Data thiếu chủ đích

Các phiên bản Spring Cloud cũ dùng bootstrap context và `bootstrap.yml`; ứng dụng hiện đại thường dùng `spring.config.import=vault://`. Khi hệ thống bật cả hai mà không có kế hoạch migration, có thể xuất hiện:

- Cùng backend KV được đăng ký nhiều lần dưới property source khác nhau.
- Thứ tự ưu tiên khó dự đoán, đặc biệt khi profile/context trùng key.
- Nhiều cấu hình lifecycle và lỗi authentication khó xác định nguồn.

Hãy chọn cơ chế phù hợp với phiên bản Boot/Cloud đang chạy, kiểm tra report nguồn cấu hình và migration guide trước khi bỏ hoặc bật bootstrap.

## 6. Đọc cấu hình qua Environment và đọc Vault qua VaultTemplate

Hai đoạn mã dưới đây đều có thể lấy giá trị từng được lưu trong Vault, nhưng hoạt động rất khác nhau.

### 6.1. Dữ liệu đã nhập vào Environment

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "orders.retry")
public record RetryProperties(int maxAttempts) {
}
~~~

Nếu `orders.retry.max-attempts` đã được nạp từ Config Data, Spring Boot sẽ bind vào `RetryProperties` khi tạo bean (sau khi có cấu hình `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` phù hợp). Một service inject `RetryProperties` sẽ đọc giá trị cấu hình **đã được Environment giải quyết tại thời điểm binding**.

Cơ chế này thuận tiện cho **startup configuration**. Đổi secret trong Vault sau khi ứng dụng chạy **không đảm bảo** record/bean đã bind sẽ tự mang giá trị mới; để refresh cần cơ chế hỗ trợ và quyết định an toàn riêng.

### 6.2. Yêu cầu Vault trực tiếp ở runtime

~~~java
import java.util.Objects;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class OrderSecretReader {

    private final VaultOperations vault;

    public OrderSecretReader(VaultOperations vault) {
        this.vault = Objects.requireNonNull(vault);
    }

    public String readFeatureFlag() {
        VaultResponse response =
            vault.opsForKeyValue(
                    "secret",
                    org.springframework.vault.core
                        .VaultKeyValueOperationsSupport.KeyValueBackend.KV_2)
                 .get("orders-api/features");

        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Feature secret missing");
        }
        Object raw = response.getData().get("enabled");
        if (!(raw instanceof String value)) {
            throw new IllegalStateException("Unexpected feature flag type");
        }
        return value;
    }
}
~~~

Ví dụ trên chủ động thực hiện một request khi `readFeatureFlag()` được gọi. Nó không thay đổi `RetryProperties` và không tạo property key mới trong `Environment`. Với production, nên khai báo `VaultKeyValueOperations` một lần để tái sử dụng, quyết định cache khi cần và kiểm tra schema giá trị secret (KV có thể chứa Boolean thay vì String). Đừng gọi Vault cho mỗi request HTTP nếu không có chiến lược latency, timeout và dự phòng.

**Hai cách phục vụ nhu cầu khác nhau:** Config Data phù hợp khởi tạo cấu hình ứng dụng; `VaultOperations` phù hợp thao tác động như đọc/ghi KV, Transit encryption, PKI và dynamic credentials. Không trông chờ chúng tự đồng bộ hai chiều.

## 7. Bean nào do auto-configuration quản lý?

Khi dùng Spring Cloud Vault starter, các bean và thành phần có thể được tạo tự động **theo điều kiện**, phụ thuộc phiên bản Spring Boot/Spring Cloud/Spring Vault và những bean người dùng đã khai báo.

| Bean/abstraction | Chủ sở hữu mặc định trong cấu hình starter | Khi nào nên định nghĩa riêng? |
|---|---|---|
| `VaultEndpoint` và URI/SSL client configuration | Spring Cloud Vault auto-configuration | Khi ứng dụng thực sự cần endpoint hoặc transport đặc biệt |
| `ClientAuthentication` | Auto-config dựa trên `spring.cloud.vault.authentication` | Khi tích hợp auth method tùy biến; phải biết cách token được lấy |
| `SessionManager` | Infrastructure Vault (có thể quản lý token lifecycle) | Khi cần chiến lược session riêng đã kiểm thử |
| `VaultTemplate` / `VaultOperations` | Auto-configuration nếu điều kiện phù hợp | Khi chỉ dùng Core hoặc muốn client độc lập có chủ đích |
| `VaultPropertySource` / Config Data loader | Spring Cloud Vault config integration | Khi thay cách chọn và ưu tiên secret backend |
| `SecretLeaseContainer` | Có thể được đăng ký bởi cơ chế lifecycle tùy starter/cấu hình | Khi phải quản lý dynamic secret lease rõ ràng |
| `VaultKeyValueOperations`, `VaultTransitOperations`, `VaultPkiOperations` | Thường lấy từ `VaultTemplate.opsForKeyValue/opsForTransit/opsForPki` | Khi cần wrapper nghiệp vụ với namespace/key/policy cố định |
| `DataSource`, `@ConfigurationProperties`, service beans | Spring Boot hoặc cấu hình ứng dụng tương ứng | Khi cần xử lý thay đổi credentials và vòng đời bean nghiệp vụ |

Đừng coi bảng là danh mục bean bất biến cho mọi phiên bản. Một số component được tạo trong giai đoạn **Config Data loading** trước khi application context hoàn tất; không phải mọi đối tượng xuất hiện dưới dạng một `@Bean` công khai. Chỉ xác định chủ sở hữu chính xác bằng dependency graph, auto-configuration report và danh sách bean trong **ứng dụng đang chạy**.

### Sơ đồ phụ thuộc

~~~mermaid
flowchart TD
    CA["ClientAuthentication"] --> SM["SessionManager"]
    END["VaultEndpoint + TLS/HTTP options"] --> VT["VaultTemplate"]
    SM --> VT
    VT --> OPS["KV / Transit / PKI operations"]
    OPS --> APP["Service ứng dụng"]
    CS["Spring Cloud Vault Config Data"] --> ENV["Environment"]
    ENV --> PROP["ConfigurationProperties beans"]
    PROP --> APP
    VT --> LEASE["SecretLeaseContainer nếu được cấu hình"]
    LEASE --> LIFE["Listener / quản lý credential"]
    LIFE --> DS["DataSource / Pool"]
~~~

Ở đây, các mũi tên biểu thị **quan hệ khái niệm**. Constructor thật và cách Spring tự cấu hình mỗi thành phần có thể khác theo phiên bản, đặc biệt trong giai đoạn bootstrapping.

## 8. Tránh tạo trùng VaultTemplate khi đã dùng starter

Ví dụ ứng dụng đã dùng Spring Cloud Vault auto-configuration và inject qua interface:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;

@Service
public final class PaymentEncryptionGateway {

    private final VaultOperations vault;

    public PaymentEncryptionGateway(VaultOperations vault) {
        this.vault = vault;
    }

    public void submitEncryptedPayload(byte[] rawPayload) {
        // Dùng vault.opsForTransit() hoặc VaultTemplate theo nghiệp vụ.
        // Phần mã hóa cụ thể thuộc service nghiệp vụ, không khởi tạo client khác.
    }
}
~~~

Service này nhận bean `VaultOperations` do context quản lý. Nếu starter đã cung cấp đúng một bean tương thích, constructor injection hoạt động và tái sử dụng endpoint, auth/session đã được cấu hình.

Một cấu hình có thể gây xung đột:

~~~java
@Configuration
class UnexpectedVaultConfig {

    @Bean
    VaultTemplate vaultTemplate(
            VaultEndpoint endpoint,
            ClientAuthentication authentication) {
        return new VaultTemplate(endpoint, authentication);
    }
}
~~~

Nếu đồng thời auto-configuration cũng tạo bean tên `vaultTemplate` hoặc bean loại `VaultOperations`, hệ quả phụ thuộc điều kiện tạo bean và tên:

- Bean tự định nghĩa có thể khiến auto-configuration **back off** do `@ConditionalOnMissingBean`.
- Có thể có nhiều bean `VaultOperations`, gây `NoUniqueBeanDefinitionException` khi inject bằng type.
- Có thể phát sinh lỗi trùng bean name nếu cả hai đăng ký cùng tên và Bean Definition Override bị vô hiệu hóa.
- Nếu bean mới dùng `ClientAuthentication` hoặc `SessionManager` khác bean mặc định, hai client có thể sử dụng danh tính/token khác nhau.

**Không tự thêm `@Primary` để “chữa” lỗi trùng bean mà chưa kiểm tra danh tính Vault.** `@Primary` chỉ ảnh hưởng quyết định autowiring khi nhiều bean cùng loại; nó không đổi quyền ưu tiên property sources và không hợp nhất các session managers.

Thay vì tạo lại bean core, nên tách wrapper mang nghiệp vụ:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.vault.core.VaultOperations;

@Component
public final class OrdersVaultClient {

    private final VaultOperations operations;

    public OrdersVaultClient(VaultOperations operations) {
        this.operations = operations;
    }

    public VaultOperations operations() {
        return operations;
    }
}
~~~

Cách này giữ nguyên chủ sở hữu Vault infrastructure là auto-configuration, còn ứng dụng chỉ sở hữu wrapper và luật sử dụng đúng key/mount. Khi cần nhiều Vault clients, hãy đặt tên bean và inject `@Qualifier` minh bạch.

## 9. Khi ứng dụng tự quản lý Spring Vault Core

Nếu dự án **không dùng** Spring Cloud Vault starter và tự tích hợp `spring-vault-core`, có thể khai báo `VaultEndpoint` cùng `VaultTemplate`. Ví dụ dưới đây cố ý để `ClientAuthentication` ở dạng dependency do cấu hình workload-auth riêng cung cấp.

~~~java
import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTemplate;

@Configuration(proxyBeanMethods = false)
public class ManualVaultCoreConfiguration {

    @Bean
    VaultEndpoint vaultEndpoint(
            @Value("${app.vault.uri}") URI vaultUri) {
        return VaultEndpoint.from(vaultUri);
    }

    @Bean
    VaultOperations vaultOperations(
            VaultEndpoint endpoint,
            ClientAuthentication workloadAuthentication) {
        return new VaultTemplate(endpoint, workloadAuthentication);
    }
}
~~~

Các điều kiện để dùng mẫu này:

1. Cấu hình khác phải cung cấp một `ClientAuthentication` đúng phương thức xác thực của workload (ví dụ Kubernetes auth/AppRole). Không dùng token root hoặc hardcode token trong source code.
2. Transport/TLS cần được cấu hình phù hợp môi trường. Constructor đơn giản ở trên minh họa việc lắp ghép, chưa mô tả toàn bộ SSL/mTLS, proxy, timeout hay session renewal.
3. Bean do ứng dụng tự tạo phải được quản lý lifecycle theo nhu cầu. Nếu chạy dài hạn, cần thiết kế token renewal/re-auth và tác động tới những request đang chạy.
4. Không bật auto-configuration khác đồng thời tạo cùng bean một cách vô thức. Nếu đang dùng Cloud Vault starter, nên cấu hình thông qua cơ chế hỗ trợ sẵn hoặc tùy biến có chủ đích, cùng kiểm thử điều kiện bean.

Trong Spring Vault Core có thể dùng `AbstractVaultConfiguration` để cung cấp các bean tiêu chuẩn thay vì tự khai báo tất cả; **chỉ chọn một cách quản lý infrastructure** cho từng context.

## 10. Trường hợp nhiều VaultTemplate hoặc VaultOperations có chủ đích

Một ứng dụng có thể cần client dành cho workload và một client quản trị riêng trong **môi trường vận hành hoặc công cụ triển khai**, nhưng điều đó làm tăng rủi ro lưu nhiều danh tính quyền cao trong cùng process.

Ví dụ khi một ứng dụng thực sự có hai bean `VaultOperations`:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;

@Service
public final class AuditVaultReader {

    private final VaultOperations auditorVault;

    public AuditVaultReader(
            @Qualifier("auditorVaultOperations")
            VaultOperations auditorVault) {
        this.auditorVault = auditorVault;
    }

    public void check() {
        // Chỉ truy cập những path mà auditor token có quyền.
    }
}
~~~

`@Qualifier` chọn bean theo tên/qualifier rõ ràng. Nếu ứng dụng có nhiều bean loại `VaultOperations`, mỗi nơi inject phải xác định lựa chọn hoặc một default được thiết kế minh bạch; **không** dựa vào thứ tự khai báo trong source file.

Với các thao tác nhạy cảm như `sys/policies/acl/*`, quản trị PKI issuer hoặc cấu hình database connection, nên dùng thành phần vận hành riêng nếu kiến trúc cho phép, vì một process nghiệp vụ nhận quyền quản trị thường làm tăng phạm vi tác động khi có sự cố bảo mật.

## 11. Thứ tự cấu hình ảnh hưởng đến workload identity

`spring.cloud.vault.uri`, `spring.cloud.vault.authentication` và `spring.cloud.vault.kubernetes.role` là cấu hình **cấp cho client Vault**. `ClientAuthentication` dựa vào chúng để lấy token. Những secret nghiệp vụ như `spring.datasource.password` lại là **dữ liệu được trả về sau khi xác thực**.

Có thể hình dung vòng phụ thuộc đúng:

~~~mermaid
sequenceDiagram
    participant B as Spring Boot Config Data
    participant C as Spring Cloud Vault
    participant A as Vault Auth
    participant V as Vault KV
    participant X as ApplicationContext

    B->>C: URI + auth method + role từ nguồn cấu hình sớm
    C->>A: Đăng nhập bằng workload identity
    A-->>C: Token theo policy, TTL
    C->>V: Đọc context KV được phép
    V-->>C: Các key cấu hình
    C-->>B: PropertySources
    B->>X: Environment đã được giải quyết
    X->>X: Tạo VaultOperations, services, DataSource
~~~

Trình tự là **mô tả logic cho Config Data integration**; các phiên bản khác có thể tạo và chia sẻ instance/client theo đường triển khai riêng.

Nếu người vận hành đổi auth role, token hiện có có thể tiếp tục mang policy cũ cho tới khi được phát hành/đổi theo cơ chế auth và session. Nếu Vault policy được cập nhật, hiệu lực ACL có thể thay đổi ngay đối với request tiếp theo của token gắn policy đó. Đây là vòng đời **quyền truy cập Vault**, tách với vòng đời các bean `@ConfigurationProperties`.

### Ba câu hỏi khi debug quyền

1. Client nào đã gửi request: Bean `VaultOperations` mặc định hay một client `@Qualifier` khác?
2. Token từ đâu: Kubernetes auth, AppRole, token cố định phục vụ test hay credential bị dùng nhầm do cấu hình?
3. Request tới path nào: `kv/data/...`, `transit/encrypt/...`, `pki/issue/...` hay `database/creds/...`?

Không mở rộng Vault ACL chỉ vì một bean đang dùng nhầm token hoặc endpoint.

## 12. Cập nhật secret không tự cập nhật bean đang chạy

Ví dụ: ứng dụng load `spring.datasource.password` từ Vault Config Data khi khởi động và tạo `HikariDataSource`. Sau một giờ, operator thay mật khẩu tương ứng trong Vault:

- Nội dung KV ở Vault đã thay đổi.
- `Environment` đang chạy **không chắc** đã được làm mới; cần cơ chế refresh riêng nếu muốn đọc lại source.
- Một bean `@ConfigurationProperties` khởi tạo từ giá trị cũ **không tự động bind lại** nếu không được cấu hình cho refresh.
- HikariCP còn giữ kết nối vật lý đang dùng credential cũ. Việc cập nhật property hoặc thay password trên bean không bảo đảm mọi connection dùng thông tin mới.
- Nếu password được cấp qua Database secrets engine, còn có lease TTL, renew/revoke và vai trò của `SecretLeaseContainer`.

Cần thiết kế một luồng rotation rõ ràng:

~~~mermaid
flowchart TD
    A["Vault có credential/secret mới"] --> B["Listener hoặc refresh mechanism nhận thay đổi"]
    B --> C["Kiểm tra giá trị mới, cấp đủ quyền"]
    C --> D["Tạo/chuẩn bị DataSource hoặc client mới"]
    D --> E{"Kết nối thử thành công?"}
    E -->|Không| F["Ghi cảnh báo an toàn, không in secret"]
    E -->|Có| G["Chuyển traffic sang client mới"]
    G --> H["Drain kết nối và giao dịch cũ"]
    H --> I["Đóng pool cũ, revoke lease theo quy trình"]
~~~

Một số kiểu secret có thể được gia hạn mà không đổi credential, trong khi loại khác cần xoay vòng bằng credential mới. `SecretLeaseContainer` cung cấp khả năng theo dõi sự kiện lease, nhưng **service sử dụng secret phải xử lý event và chuyển trạng thái an toàn**.

Với token Vault, `SessionManager` có trách nhiệm riêng. Không dùng renewal của Vault service token như bằng chứng rằng username/password JDBC cũng đã được gia hạn.

## 13. Kiểm tra nguồn được chọn mà không lộ secret

Khi cấu hình có nhiều nguồn, nên xác định **tên property source thắng** thay vì log giá trị. Ví dụ với `ConfigurableEnvironment`:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public final class PropertyOriginInspector {

    public static String firstSourceContaining(
            ConfigurableEnvironment environment,
            String key) {
        for (PropertySource<?> source : environment.getPropertySources()) {
            if (source.containsProperty(key)) {
                return source.getName();
            }
        }
        return "<not found>";
    }
}
~~~

`Environment.getPropertySources()` duyệt nguồn theo thứ tự ưu tiên thực tế. Hàm trên trả tên nguồn đầu tiên chứa key, **không log giá trị**. Một số property source có logic ánh xạ key phức tạp hoặc wrapped composite source; với `@ConfigurationProperties`, relaxed binding và origin tracking có thể cần kiểm chứng bổ sung theo key canonical.

Ví dụ áp dụng:

~~~java
String owner = PropertyOriginInspector.firstSourceContaining(
        environment, "spring.datasource.username");

// Chỉ in tên source nếu tên không chứa thông tin nhạy cảm.
logger.info("Datasource username selected from source: {}", owner);
~~~

Đối với mật khẩu/token, tốt nhất không in tên hoặc đường dẫn nội bộ nếu nó tiết lộ secret location/tenant. Trong chẩn đoán, có thể đối chiếu source name ở môi trường test hoặc qua công cụ quan sát đã giới hạn quyền.

Spring Boot Actuator cung cấp những endpoint như `/actuator/env`, `/actuator/configprops` và `/actuator/conditions` tùy phiên bản/cấu hình. Chúng có thể tiết lộ cấu trúc hệ thống và nguồn config; **hạn chế exposure, bảo vệ truy cập và cấu hình cơ chế che giá trị**. Không đưa các endpoint chẩn đoán ra Internet công cộng chỉ để debug ưu tiên cấu hình.

### Kiểm tra bean được tạo từ đâu

Dùng `ApplicationContext.getBeanNamesForType(VaultOperations.class)` để xem những bean tương thích đã được đăng ký. Nếu thấy nhiều bean, đối chiếu tên, `@Primary`, `@Qualifier` và bean definition source. Khi auto-config không hoạt động như mong muốn, kiểm tra **condition evaluation report** (chẳng hạn log `--debug` hoặc Actuator conditions nếu được bảo vệ).

Nếu một bean không xuất hiện, cần kiểm tra dependency, profile, `@ConditionalOnProperty`, `@ConditionalOnMissingBean` và thứ tự cấu hình. Không khắc phục bằng cách tạo bean cùng loại một cách ngẫu nhiên.

## 14. Kiểm thử tích hợp cho precedence và bean ownership

Mục tiêu kiểm thử không chỉ là “ứng dụng chạy được”, mà phải chứng minh **config đúng nguồn, bean đúng danh tính, và secret lifecycle không gây lỗi**.

| Mã | Tình huống | Kết quả cần chứng minh |
|---|---|---|
| C01 | Cùng key có trong `application.yml` và Vault Config Data | Nguồn được chọn đúng contract import/profile |
| C02 | Thêm biến môi trường hoặc CLI override key không nhạy cảm | Giá trị thực tế phù hợp thứ tự precedence của môi trường test |
| C03 | Config bắt buộc trong Vault bị thiếu | Khởi động thất bại rõ hoặc fallback đúng chủ đích |
| B01 | Chỉ dùng starter auto-config | Có bean `VaultOperations` đúng config, không có bean trùng vô tình |
| B02 | Tự thêm bean cùng type trong context thử nghiệm | Test phát hiện bean ambiguity hoặc auto-config back off |
| B03 | Hai Vault clients dùng `@Qualifier` | Service inject đúng bean và đúng Vault identity |
| A01 | Workload token không có quyền trên mount khác | Request bị Vault từ chối dù bean vẫn tạo thành công |
| L01 | KV secret thay đổi trong Vault | Xác định bean nào cần refresh, bean nào vẫn giữ snapshot |
| L02 | Credential database lease xoay vòng | DataSource mới kết nối được và pool cũ được xử lý an toàn |
| F01 | Vault tạm thời không kết nối được | Có lỗi rõ, timeout/retry hữu hạn và không lộ secrets |

### Ví dụ JUnit 5 kiểm tra wiring của một ứng dụng chỉ có một Vault client

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.vault.core.VaultOperations;

@SpringBootTest
class VaultIntegrationWiringIT {

    @Autowired
    private ApplicationContext context;

    @Autowired
    private ConfigurableEnvironment environment;

    @Test
    void hasExactlyOneVaultOperationsBean() {
        Map<String, VaultOperations> beans =
                context.getBeansOfType(VaultOperations.class);

        assertEquals(1, beans.size(),
                "Ứng dụng này quy định đúng một VaultOperations");
    }

    @Test
    void showsOriginOfNonSecretConfiguration() {
        String source = PropertyOriginInspector.firstSourceContaining(
                environment, "orders.retry.max-attempts");

        assertNotEquals("<not found>", source);
        // Bổ sung assertion về source name phù hợp
        // test fixture cụ thể, không log secret value.
    }
}
~~~

Đây là **mẫu kiểm thử dành cho cấu hình một Vault client**, không phải bất biến với ứng dụng cố ý dùng nhiều clients. Khi mô hình có hai bean, thay assertion bằng kiểm tra bean names và `@Qualifier` của từng consumer.

Nếu `spring.config.import=vault://` đòi Vault lúc khởi động, integration test phải có Vault dev/test fixture và workload auth/policy tương ứng. Không dựa vào mock bean để chứng minh API Vault thật, lease renewal hay precedence giữa Vault Config Data và môi trường.

### Test property precedence có kiểm soát

Trong test profile, tạo một key không nhạy cảm như `orders.retry.max-attempts` ở cả file local và Vault KV. Khi cần so sánh override từ CLI hoặc biến môi trường, chạy cùng ứng dụng trong hai environment khác nhau và so sánh **giá trị cuối cùng** cùng **nguồn gốc**. Tránh dùng mật khẩu thật làm giá trị test; một bài test chỉ kiểm tra precedence nên dùng các chuỗi marker dễ nhận biết.

### Test negative cho auth/bean

- Workload được gán policy chỉ cho `secret/data/orders-api/*`; cố đọc `secret/data/payments/*` phải bị từ chối.
- Nếu có hai `VaultOperations`, service dùng `@Qualifier("auditorVaultOperations")` phải thực sự gọi Vault với quyền auditor, không lén dùng bean workload.
- Token hết hạn hoặc auth thất bại phải được báo rõ; không tự fallback sang token root hoặc môi trường khác.
- Khi sửa `spring.cloud.vault.kubernetes.role`, test phải xác nhận role mới có quyền phù hợp, thay vì chỉ nhìn thấy app khởi động thành công.

## 15. Các lỗi phổ biến và hướng chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `spring.datasource.password` không khớp Vault KV | Bị biến môi trường/CLI/config profile override; import sai context | Kiểm tra nguồn thực tế, tên key và thứ tự Config Data |
| Không thấy property từ Vault | Thiếu `spring.config.import`, KV backend/context sai, không có quyền hoặc cấu hình bootstrap chưa tương thích | Kiểm tra config mode, auth, path và property sources |
| `NoSuchBeanDefinitionException: VaultOperations` | Không có starter hoặc cấu hình Core; auto-config không được kích hoạt | Kiểm tra dependency, conditional report và cách khởi tạo bean |
| `NoUniqueBeanDefinitionException` | Nhiều bean `VaultOperations`/`VaultTemplate` | Kiểm tra định nghĩa trùng, sử dụng `@Qualifier` có chủ đích |
| `BeanDefinitionOverrideException` | Cùng bean name được khai báo nhiều lần | Chọn một owner, đổi tên bean có chủ đích, không bật override toàn cục để che lỗi |
| App dùng token/namespace khác dự kiến | Custom `ClientAuthentication`, `SessionManager` hoặc client thứ hai được inject nhầm | Kiểm tra bean graph và cấu hình auth từng client |
| `403 permission denied` dù URI đúng | Policy workload không có quyền path hoặc token hết hạn/sai namespace | Kiểm tra auth role, token capabilities và path API thực |
| Vault Config Data đọc được nhưng `VaultTemplate` fail | Hai client có cấu hình endpoint/auth/TLS khác nhau | So sánh client infrastructure của Config Data và runtime |
| Rotate credential nhưng JDBC login mới fail | Bean DataSource giữ credentials cũ, thiếu lease listener/pool replacement | Kiểm tra rotation event, nguồn username/password và connection pool |
| Đổi secret mà `@ConfigurationProperties` không đổi | Bean bind snapshot lúc khởi động, không có refresh | Xác định cơ chế refresh/rebinding và giới hạn cập nhật |
| Test pass trên local nhưng fail Kubernetes | Config source order, service account, DNS/TLS hoặc profile khác | Chạy integration test với cấu hình workload giống môi trường triển khai |

Quy trình chẩn đoán gọn:

1. Xác định **giá trị key nào** có vấn đề, nhưng không in secret.
2. Xác định **property source đang thắng** và giai đoạn nó được nạp.
3. Xác định **bean nào sở hữu** client hoặc dependency đang gây lỗi.
4. Kiểm tra **workload identity**, Vault namespace, mount và request path thật.
5. Phân biệt lỗi **startup configuration**, **runtime Vault request**, **token lease** hoặc **credential rotation**.
6. Sau khi sửa, chạy lại các ca positive/negative liên quan.

## 16. Nguyên tắc thiết kế để tránh xung đột

**Một nguồn sở hữu rõ ràng cho mỗi loại thành phần.** Nếu chọn Spring Cloud Vault starter, cấu hình thông qua các thuộc tính/starter trước khi tự viết bean infrastructure. Nếu tự dùng Spring Vault Core, chịu trách nhiệm tạo client, auth/session và timeout/TLS.

**Một nguồn chính được phê duyệt cho từng secret.** Dù Spring Boot có cơ chế override, không nên để credential quan trọng vô tình trùng giữa Vault và biến môi trường nhiều môi trường. Xác định chủ sở hữu và có test bảo vệ nguồn ưu tiên.

**Tách lifecycle khỏi giá trị ban đầu.** Việc tải secret thành công khi khởi động không đủ cho dynamic database credentials, token renewal hoặc PKI certificate rotation. Mỗi loại secret cần cơ chế thay đổi và kiểm chứng của riêng nó.

**Tách operator khỏi workload.** Bean Vault cho hoạt động nghiệp vụ nên mang policy ít quyền nhất. Các thao tác hệ thống như sửa ACL policies, quản lý PKI issuer hoặc database role nên được thực hiện bởi quy trình vận hành có danh tính riêng.

**Quan sát được mà không lộ secrets.** Kiểm tra bean graph, tên property sources, condition report, Vault request IDs và metrics renewal/rotation; không log raw response, token, private key, SecretID hoặc mật khẩu DB.

## 17. Câu hỏi tự kiểm tra

1. Nếu cùng key xuất hiện trong `application.yml`, Config Data Vault và tham số dòng lệnh, cơ chế nào quyết định giá trị cuối cùng? Liệu `@Primary` trên một bean có thay đổi điều đó không?
2. Nếu dự án đã dùng `spring-cloud-starter-vault-config`, việc thêm `@Bean VaultTemplate` có thể làm thay đổi những gì?
3. Sự khác biệt giữa `VaultTemplate.read(...)` tại runtime và property được nhập vào `Environment` qua `vault://` là gì?
4. Vì sao không nên cố lấy chính Vault URI hoặc thông tin đăng nhập đầu tiên từ Vault Config Data?
5. Vì sao cập nhật `spring.datasource.password` chưa đủ để bảo đảm mọi connection HikariCP dùng mật khẩu mới?
6. Khi có hai bean `VaultOperations`, cách nào chọn chính xác bean dành cho workload thay vì phụ thuộc thứ tự khởi tạo?
7. Những bằng chứng nào giúp xác nhận lỗi 403 xuất phát từ ACL thay vì bean chọn nhầm token/namespace?
8. Có thể dùng `/actuator/env` để chẩn đoán không? Cần bảo vệ những gì?

## 18. Tổng kết

Trong Spring Boot và Spring Vault, **quyền ưu tiên cấu hình**, **chủ sở hữu bean**, và **vòng đời secret/token** là ba cơ chế khác nhau. `Environment` quyết định key nào thắng; Spring `ApplicationContext` và auto-configuration quyết định bean nào được tạo/inject; Spring Vault cùng Vault server xử lý authentication, token, secrets và leases. Các cơ chế này phải được phối hợp chủ động.

Với ứng dụng tích hợp **SPRING_VAULT**, cách làm ổn định là chọn một mô hình khởi tạo Vault rõ ràng, hiểu vị trí của `vault://` trong Config Data, tránh tạo trùng `VaultTemplate`, dùng `@Qualifier` khi thực sự có nhiều clients, và thiết kế refresh/rotation riêng cho các bean có trạng thái như `DataSource`. Kiểm thử tích hợp cần xác nhận đúng property source, đúng bean, đúng workload identity và cả trường hợp request Vault bị từ chối theo policy.

### Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Config Data](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing)
- [Spring Cloud Vault — Reference Documentation](https://docs.spring.io/spring-cloud-vault/reference/)
- [Spring Vault — Reference Documentation](https://docs.spring.io/spring-vault/reference/)
- [Spring Vault — VaultOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultOperations.html)
- [Spring Vault — VaultTemplate API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTemplate.html)
- [Spring Vault — SecretLeaseContainer API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretLeaseContainer.html)
