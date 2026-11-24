# Phân biệt Azure App Configuration và Azure Key Vault

Trong một ứng dụng Spring Boot chạy trên Azure, cấu hình thường gồm hai nhóm thông tin: **tham số điều khiển hành vi ứng dụng** và **dữ liệu cần giữ bí mật**. Azure cung cấp hai dịch vụ bổ trợ cho nhau: **Azure App Configuration** quản lý cấu hình ứng dụng, còn **Azure Key Vault** bảo vệ secret, khóa mật mã và chứng chỉ.

Bài học thuộc chương **Cấu hình Azure** của mô-đun `SPRING_CLOUD_PROVIDER_INTEGRATION`. Mục tiêu là biết chọn dịch vụ đúng, tích hợp với Spring Cloud Azure bằng danh tính và quyền phù hợp, hiểu luồng Key Vault reference, kiểm thử và vận hành cấu hình an toàn.

## 1. Phân biệt bằng câu hỏi về dữ liệu

Hãy bắt đầu với hai câu hỏi:

1. **Giá trị có phải bí mật không?** Nếu việc lộ giá trị có thể cho phép truy cập trái phép (mật khẩu, API token, private credential), hãy lưu trong **Key Vault**.
2. **Giá trị có dùng để điều chỉnh hành vi ứng dụng không?** Nếu là timeout, ngưỡng retry, địa chỉ endpoint công khai, lựa chọn tính năng hoặc giá trị khác nhau theo môi trường, hãy lưu trong **App Configuration**.

Ví dụ về hệ thống đặt hàng:

| Dữ liệu | Nơi lưu phù hợp | Vì sao |
| --- | --- | --- |
| `orders.timeout=PT3S` | App Configuration | Tham số vận hành, có thể điều chỉnh theo môi trường |
| `orders.max-retries=4` | App Configuration | Cấu hình logic retry, không phải bí mật |
| Bật/tắt tính năng thanh toán mới | App Configuration | Có cơ chế feature flags và quản lý phát hành |
| `payments.api-key` | Key Vault | Khóa truy cập đối tác cần giới hạn người đọc |
| Mật khẩu truy cập cơ sở dữ liệu | Key Vault | Bí mật xác thực, cần quy trình cấp quyền và luân chuyển |
| Khóa dùng để ký/mã hóa, chứng chỉ TLS | Key Vault | Là đối tượng mật mã có API và vòng đời quản lý riêng |
| URI tham chiếu đến `payments.api-key` | App Configuration | Có thể giữ **tham chiếu** để ứng dụng truy xuất secret từ Key Vault |

**Quy tắc chính:** App Configuration có mã hóa dữ liệu khi lưu và truyền, nhưng điều đó không biến nó thành kho quản lý bí mật chuyên dụng. Khi kết hợp hai dịch vụ, App Configuration giữ **con trỏ tới secret**, còn giá trị secret vẫn thuộc Key Vault.

## 2. Bảng so sánh theo trách nhiệm

| Tiêu chí | Azure App Configuration | Azure Key Vault |
| --- | --- | --- |
| Mục đích | Tập trung quản lý cấu hình ứng dụng, feature flags | Quản lý secret, cryptographic key, certificate |
| Đơn vị dữ liệu chính | Key-value, label, metadata, feature flag | Secret có phiên bản, key có phiên bản, certificate |
| Ví dụ | Timeout, URL dịch vụ, rollout flag | Password, API token, khóa ký, certificate |
| Phân chia môi trường | Labels, tiền tố key, cấu hình riêng cho app/profile | Có thể tách vault theo môi trường/ứng dụng và cấp quyền |
| Đọc hàng loạt | Chọn/filter nhiều key-value theo key và label | Secret thường được truy xuất riêng theo tên/phiên bản |
| Thay đổi cấu hình khi chạy | Thư viện Spring có cơ chế kiểm tra và refresh theo cấu hình | Thay đổi secret không tự cập nhật mọi đối tượng đang giữ giá trị cũ |
| Kiểm soát quyền đọc điển hình | `App Configuration Data Reader` | `Key Vault Secrets User` cho secret (Azure RBAC) |
| Vòng đời bí mật | Không thay thế quản lý secret, key hay certificate | Phiên bản, hết hạn, rotation, thao tác mật mã tùy loại đối tượng |
| Tích hợp Spring | App Configuration config provider, feature management | Key Vault Secrets property source, Azure SDK cho key/certificate |
| Quan hệ với dịch vụ kia | Lưu **Key Vault reference** | Cung cấp giá trị secret khi ứng dụng được cấp quyền |

**Phân biệt ba loại đối tượng trong Key Vault:** secret là giá trị nhạy cảm có thể đọc dưới dạng dữ liệu; key là đối tượng khóa mật mã phục vụ các thao tác như ký hay giải mã tùy quyền và loại khóa; certificate phục vụ quản lý chứng chỉ. Starter `spring-cloud-azure-starter-keyvault-secrets` xử lý **secret** dưới dạng Spring property source; nó không mặc nhiên thay thế API Key Vault Keys hay Certificates.

## 3. Các khái niệm đặc trưng

### 3.1. App Configuration: key, label và feature flag

App Configuration lưu các cặp key-value. Một key có thể có nhiều giá trị phân biệt bởi **label**:

| Key | Label | Value |
| --- | --- | --- |
| `/application/orders.timeout` | `dev` | `PT10S` |
| `/application/orders.timeout` | `prod` | `PT3S` |
| `/application/orders.max-retries` | `prod` | `4` |

Spring provider có quy ước đọc key dưới tiền tố `/application/` và ánh xạ vào thuộc tính Spring như `orders.timeout`. Theo mặc định, nếu không cấu hình label filter riêng, provider dùng Spring profile đang hoạt động làm label; không có active profile thì dùng giá trị không có label. Cần kiểm tra quy tắc chọn key/label theo phiên bản thư viện đang sử dụng.

**Feature flag** là một kiểu dữ liệu chuyên biệt để điều khiển khả năng xuất hiện của tính năng, khác với việc tự tạo một thuộc tính boolean thông thường. Cơ chế feature management có thể xét điều kiện, bộ lọc và chiến lược phát hành; chỉ lưu một key `checkout.enabled=true` thì chưa có đầy đủ hành vi feature management.

### 3.2. Key Vault: bí mật, danh tính, phiên bản

Ví dụ Key Vault có secret tên `payments-api-key`. Key Vault cung cấp URI như:

~~~text
https://demo-payments-kv.vault.azure.net/secrets/payments-api-key
~~~

URI này **không phải** secret. Giá trị secret chỉ được trả về cho danh tính có quyền đọc, qua kết nối và chính sách mạng hợp lệ. Khi có phiên bản mới, URI có version cụ thể trỏ đến một phiên bản xác định; URI không chứa version cho phép truy xuất phiên bản hiện hành theo hành vi dịch vụ và thư viện, nhưng ứng dụng vẫn cần nạp lại/cập nhật cache đúng cách.

## 4. Kết hợp hai dịch vụ bằng Key Vault reference

Một cấu hình thực tế:

- Trong **Key Vault**, quản lý secret `payments-api-key` với giá trị thật.
- Trong **App Configuration**, tạo key `/application/payments.api-key` kiểu **Key Vault reference**, trỏ tới URI của secret.
- Spring Boot nạp cấu hình qua App Configuration provider. Khi gặp reference, **thư viện phía ứng dụng** truy vấn Key Vault và đưa giá trị đã phân giải vào Spring `Environment`.

~~~mermaid
sequenceDiagram
    participant Spring as Spring Boot + Spring Cloud Azure
    participant Config as Azure App Configuration
    participant Vault as Azure Key Vault
    Spring->>Config: Đọc /application/payments.api-key
    Config-->>Spring: Key Vault reference (URI, không phải secret)
    Spring->>Vault: Đọc secret theo URI và danh tính ứng dụng
    Vault-->>Spring: Giá trị secret (nếu được cấp quyền)
    Note over Spring: Đưa giá trị vào Spring Environment
~~~

Điểm dễ nhầm: **App Configuration không chuyển sẵn giá trị secret cho ứng dụng**. Chính client provider của ứng dụng nhận reference rồi kết nối tới Key Vault. Danh tính chạy ứng dụng phải được phép đọc **cả App Configuration lẫn Key Vault**; chỉ cấp `App Configuration Data Reader` thì không đủ.

Một Key Vault reference cũng không giống cú pháp `@Microsoft.KeyVault(...)` dùng cho *App Service application settings*. Đó là cơ chế resolve riêng của Azure App Service; trong bài này ta dùng **App Configuration Key Vault reference** được Spring provider hỗ trợ.

## 5. Tích hợp trong Spring Boot với Spring Cloud Azure

### 5.1. Điều kiện và dependency

Giả sử dự án có Spring Boot, Java 17+ và cấu hình Maven. Chọn **BOM Spring Cloud Azure tương thích với phiên bản Spring Boot**. Ví dụ theo ma trận hỗ trợ: Spring Boot 3.5.x ghép với Spring Cloud Azure 6.x (hoặc một bản 5.x được hỗ trợ), còn Spring Boot 4.0.x ghép với Spring Cloud Azure 7.x. Không tự ghép các dòng major bất tương thích.

Trong `pom.xml`, khai báo BOM và dependency tương ứng:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.azure.spring</groupId>
      <artifactId>spring-cloud-azure-dependencies</artifactId>
      <version>${spring-cloud-azure.version}</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <!-- Provider App Configuration, bản web hỗ trợ tự kiểm tra refresh -->
  <dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-appconfiguration-config-web</artifactId>
  </dependency>

  <!-- Chỉ cần khi muốn đọc Key Vault secrets thành Spring properties -->
  <dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-keyvault-secrets</artifactId>
  </dependency>
</dependencies>
~~~

Đặt property `spring-cloud-azure.version` trong POM bằng một phiên bản **đã kiểm tra tương thích**; ví dụ `6.2.0` với Spring Boot 3.5.x hoặc `7.2.0` với Spring Boot 4.0.x. Phần dependency App Configuration **không cần starter Key Vault Secrets để resolve Key Vault reference**; provider App Configuration có cơ chế riêng. Ta thêm starter Key Vault để minh họa trường hợp ứng dụng **đọc một secret trực tiếp** từ Key Vault.

Nếu không có Spring Web hoặc không cần kiểm tra refresh tự động theo sự kiện web, có thể chọn thư viện `spring-cloud-azure-appconfiguration-config` thay bản `-web`.

### 5.2. Tạo dữ liệu cho hai kiểu truy cập

Trên Azure portal:

1. Tạo App Configuration store và Key Vault, ví dụ `demo-orders-config` và `demo-payments-kv`.
2. Trong App Configuration, tạo `/application/orders.timeout` = `PT3S`, `/application/orders.max-retries` = `4` với label `prod`.
3. Trong Key Vault, tạo secret `payments-api-key` và `jdbc-password` bằng quy trình quản lý secret của môi trường; không chép giá trị thật vào mã nguồn, tài liệu, shell history hay log.
4. Trong App Configuration, tạo **Key Vault reference**: key `/application/payments.api-key`, label `prod`, secret URI `https://demo-payments-kv.vault.azure.net/secrets/payments-api-key`.
5. Dùng secret `jdbc-password` để minh họa đường đọc **trực tiếp** qua Key Vault Secrets property source.

Tương đương, lệnh Azure CLI tạo reference có dạng:

~~~bash
az appconfig kv set-keyvault \
  --name demo-orders-config \
  --key /application/payments.api-key \
  --label prod \
  --secret-identifier "https://demo-payments-kv.vault.azure.net/secrets/payments-api-key"
~~~

Giá trị của key trong App Configuration lúc này là **reference**, không phải bản sao API key.

### 5.3. Định danh và phân quyền

Ở máy phát triển có thể đăng nhập Azure CLI bằng `az login` (và chọn subscription phù hợp). Khi triển khai, nên bật **Managed Identity** cho môi trường chạy Spring Boot, ví dụ App Service hoặc workload có hỗ trợ identity. Thư viện Spring Cloud Azure hỗ trợ các cách cấp credential của Azure, gồm các cấu hình dựa trên danh tính và credential chain; kiểm tra cách chọn credential của đúng phiên bản được dùng.

Với một danh tính chạy ứng dụng chỉ cần đọc:

| Tài nguyên | Quyền tối thiểu khi dùng Azure RBAC | Công dụng |
| --- | --- | --- |
| App Configuration store | `App Configuration Data Reader` | Đọc key-value, label, reference |
| Key Vault | `Key Vault Secrets User` | Đọc giá trị secret được tham chiếu và secret đọc trực tiếp |

Nếu vault đang dùng **Vault access policy** thay cho Azure RBAC, phải cấp quyền `Get` cho secret; nếu property source được cấu hình để liệt kê mọi secret, cần kiểm tra thêm quyền `List`. Tránh gán `Owner` hoặc `Contributor` chỉ để chữa lỗi 403. Đăng nhập thành công vào Azure không đồng nghĩa có quyền đọc dữ liệu của hai dịch vụ.

Lưu ý danh tính chạy trong cloud và danh tính của người phát triển tại máy local có thể **khác nhau**. Kiểm tra RBAC trên đúng principal, đúng subscription/resource và chờ quyền được đồng bộ nếu vừa gán.

### 5.4. Kết nối hai nguồn cấu hình

Ví dụ `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: orders-api
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: ${AZURE_APPCONFIG_ENDPOINT}
      keyvault:
        secret:
          property-source-enabled: true
          property-sources:
            - endpoint: ${AZURE_KEYVAULT_ENDPOINT}
              secret-keys:
                - jdbc-password
~~~

Biến môi trường chứa **endpoint**, không chứa secret:

~~~text
AZURE_APPCONFIG_ENDPOINT=https://demo-orders-config.azconfig.io
AZURE_KEYVAULT_ENDPOINT=https://demo-payments-kv.vault.azure.net/
SPRING_PROFILES_ACTIVE=prod
~~~

- `spring.config.import=azureAppConfiguration` là cú pháp import của thư viện App Configuration thế hệ mới; không thay bằng `azure-appconfiguration:` nếu tài liệu của phiên bản đang dùng yêu cầu đúng chuỗi `azureAppConfiguration`.
- Provider nạp các key/label áp dụng cho cấu hình; active profile `prod` tương ứng label `prod` ở ví dụ.
- `keyvault.secret.property-sources` cung cấp **đường truy cập trực tiếp** đến `jdbc-password`. Danh sách `secret-keys` giới hạn tên secret cần nạp, thay vì đọc toàn bộ vault. Starter này không bắt buộc cho key `payments.api-key` nếu đã nạp qua App Configuration reference.
- Không đưa `connection-string` chứa credential, mật khẩu, client secret hay khóa truy cập vào file commit lên Git.

Nếu muốn ép label thay vì dựa vào active profile, có thể cấu hình chọn label rõ ràng:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].selects[0].key-filter=/application/*
spring.cloud.azure.appconfiguration.stores[0].selects[0].label-filter=prod
~~~

Với cấu hình sản xuất đa môi trường, cân nhắc giữ các giá trị chung không có label rồi chồng giá trị môi trường bằng label phù hợp, tránh nhầm lẫn thứ tự ưu tiên giữa nhiều nguồn Spring `PropertySource`.

### 5.5. Đọc giá trị trong mã Spring

Hai loại cấu hình khi đã nạp thành công đều truy cập thông qua Spring `Environment`, `@Value` hoặc `@ConfigurationProperties`. Không nên để phần nghiệp vụ biết URI Key Vault hay API gọi SDK.

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "orders")
public record OrderSettings(Duration timeout, int maxRetries) {}
~~~

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class PaymentGatewaySettings {
    private final String apiKey;
    private final String jdbcPassword;
    private final OrderSettings orders;

    public PaymentGatewaySettings(
            @Value("${payments.api-key}") String apiKey,
            @Value("${jdbc-password}") String jdbcPassword,
            OrderSettings orders) {
        this.apiKey = apiKey;             // App Configuration -> Key Vault reference
        this.jdbcPassword = jdbcPassword; // Key Vault property source trực tiếp
        this.orders = orders;             // App Configuration key-value
    }

    public boolean isConfigured() {
        return apiKey != null && !apiKey.isBlank()
                && jdbcPassword != null && !jdbcPassword.isBlank()
                && orders.timeout().isPositive();
    }
}
~~~

Trong ứng dụng thật, các giá trị nhạy cảm chỉ nên được truyền tới client hoặc kết nối cần sử dụng; **không** trả secret qua REST API, log hoặc message lỗi. Ví dụ trên cố ý chỉ kiểm tra có cấu hình hợp lệ, không in giá trị.

## 6. Cập nhật runtime, rotation và bộ nhớ đệm

**App Configuration** có hỗ trợ refresh, nhưng không phải mọi thay đổi được đẩy ngay vào mọi bean:

- Thư viện `spring-cloud-azure-appconfiguration-config-web` có thể kiểm tra refresh thông qua hoạt động Spring Web; nó không tạo cơ chế push tức thời cho một ứng dụng không có request. Thư viện cũng hỗ trợ kiểm tra theo cách chủ động.
- Bật monitoring/refresh khi cần và cấu hình điều kiện trigger cho hệ thống. Khi giá trị đã được nạp, `@RefreshScope` có thể giúp bean được tạo lại sau lần refresh thực sự; các object tự cache giá trị vẫn cần chiến lược cập nhật.
- Khoảng cách tối thiểu giữa các lần kiểm tra theo mặc định được tài liệu App Configuration nêu là 30 giây. Kết quả quan sát còn phụ thuộc request, trigger và cache.

Ví dụ cấu hình bật kiểm tra thay đổi (một phần của `application.properties`):

~~~properties
spring.cloud.azure.appconfiguration.stores[0].monitoring.enabled=true
~~~

**Key Vault secret rotation** là một luồng riêng: tạo phiên bản secret mới, bảo đảm ứng dụng đọc được phiên bản phù hợp, cập nhật/cắt cache và xác minh các client đang sử dụng giá trị mới. Nếu App Configuration reference chỉ định **một version cụ thể**, thay đổi giá trị sang phiên bản mới không tự dịch chuyển reference đó. Nếu dùng URI không có version, việc ứng dụng thấy giá trị mới vẫn phụ thuộc lần phân giải lại reference và cache/refresh.

Không thể coi việc thay secret trong Key Vault là bảo đảm Spring bean đang chạy tự động đổi ngay. Đối với bí mật quan trọng, thiết kế rotation theo pha: phát hành credential mới → cho phép cả cũ và mới trong thời gian chuyển tiếp nếu hệ thống hỗ trợ → kích hoạt nạp lại/khởi động lại thành phần cần thiết → thu hồi credential cũ.

## 7. Bảo mật và độ tin cậy trong thực tế

| Tình huống | Cách xử lý |
| --- | --- |
| Ứng dụng truy cập được App Configuration nhưng resolve reference trả 403 | Kiểm tra quyền secret trên Key Vault cho **cùng danh tính** mà client thực tế sử dụng; xác minh mô hình RBAC hoặc access policy |
| App Configuration trả 403 ngay lúc khởi động | Kiểm tra `App Configuration Data Reader`, danh tính/token, scope gán role và đồng bộ quyền |
| Không thấy `orders.timeout` hoặc thấy sai môi trường | Kiểm tra tiền tố `/application/`, key filter, active Spring profile, label và thứ tự nguồn cấu hình |
| Secret không tồn tại / URI tham chiếu sai | Kiểm tra tên vault, secret, version, trạng thái enabled và quyền truy xuất |
| Thay secret nhưng ứng dụng vẫn dùng giá trị cũ | Xem lại version-pinned reference, cache, chu kỳ refresh, bean và pool kết nối |
| Lỗi DNS, timeout hoặc 429 | Kiểm tra mạng/private endpoint, firewall, retry có backoff; tránh truy vấn secret lặp lại quá nhiều |
| Ứng dụng chạy tốt local nhưng lỗi khi deploy | Kiểm tra Managed Identity đã bật và role được cấp cho **principal của workload**, không phải tài khoản local |
| Test khởi động vô tình gọi tài nguyên Azure thật | Tắt tích hợp nguồn ngoài trong test và cấp property giả tại môi trường test |

Một số nguyên tắc nên áp dụng đồng thời:

1. **Quyền tối thiểu:** tách quyền đọc App Configuration và Key Vault; phân vai theo ứng dụng/môi trường.
2. **Không lộ secret:** tránh log `Environment`, Actuator `/env`, dump exception chứa credential hoặc truyền bí mật vào URL/tracing.
3. **Phân tách môi trường:** dùng App Configuration labels và cân nhắc vault riêng cho môi trường quan trọng; không lấy chung secret production cho local development.
4. **Kiểm soát mạng:** cấu hình private endpoint, firewall và đường truy cập tới từng dịch vụ theo chính sách hệ thống.
5. **Giám sát:** theo dõi xác thực thất bại, lỗi tải cấu hình, thao tác đọc secret và độ trễ; không đưa nội dung secret vào telemetry.
6. **Chi phí và tải:** App Configuration có giới hạn/chi phí theo gói, Key Vault cũng có quota và hoạt động đọc riêng; mỗi reference có thể tạo truy vấn Key Vault, nên cân nhắc số lượng reference và cache.

## 8. Kiểm thử mà không phụ thuộc Azure thật

Trong kiểm thử logic nghiệp vụ, cung cấp các giá trị giả (không phải credential thật) và vô hiệu hóa việc đọc nguồn cấu hình bên ngoài. Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "spring.cloud.azure.appconfiguration.enabled=false",
    "spring.cloud.azure.keyvault.secret.property-source-enabled=false",
    "orders.timeout=PT3S",
    "orders.max-retries=4",
    "payments.api-key=test-placeholder",
    "jdbc-password=test-placeholder"
})
class OrdersApplicationTests {
    @Test
    void contextLoads() {}
}
~~~

Bài test kiểu này chỉ xác minh **Spring wiring và binding**. Nó **không** chứng minh quyền Azure, Key Vault reference hay refresh hoạt động. Để xác minh tích hợp, có thể dùng môi trường dev riêng với danh tính giới hạn quyền, secret thử nghiệm và các bước kiểm tra:

1. Nạp key/label `prod` hoặc `dev` đúng với profile, xác nhận `orders.timeout`.
2. Kiểm tra reference `payments.api-key` phân giải thành công (chỉ xác nhận ứng dụng dùng được, không in secret).
3. Thu hồi quyền đọc Key Vault trên một danh tính thử nghiệm, xác nhận lỗi truy cập được ghi nhận và phân biệt rõ với lỗi App Configuration.
4. Thay đổi giá trị cấu hình không nhạy cảm và quan sát refresh theo đúng chu kỳ/trigger.
5. Tạo version secret thử nghiệm mới, kiểm tra hành vi khi dùng URI cố định version và URI không cố định version.

**Điểm cần nhớ:** kiểm thử mock giúp nhanh và ổn định, còn kiểm thử tích hợp cần xác thực cả hai dịch vụ, phân quyền, network và vòng đời thay đổi dữ liệu.

## 9. Bài tập chọn phương án

Xét một hệ thống `checkout-service` triển khai ở `dev`, `staging` và `prod`:

| Yêu cầu | Quyết định đề xuất |
| --- | --- |
| Đổi thời gian chờ API đối tác giữa ba môi trường | Một key App Configuration, ba labels theo môi trường |
| Dùng API token khác nhau giữa ba môi trường | Secret trong Key Vault theo môi trường; tham chiếu từ App Configuration nếu cần đồng nhất điểm quản lý |
| Bật checkout mới cho nhóm người dùng thử | Feature flag trong App Configuration và thư viện feature management thích hợp |
| Ứng dụng được cấp quyền xem timeout nhưng không được xem token đối tác | Cấp role App Configuration cho identity đọc config; tách quyền đọc Key Vault theo nhu cầu thực tế |
| Luân chuyển token mà không commit code | Tạo secret version mới; thiết kế nạp lại và cập nhật Key Vault reference/cấu hình theo vòng đời rotation |

**Câu hỏi tự kiểm tra:**

1. Vì sao mã hóa dữ liệu của App Configuration vẫn không đủ để coi đó là kho secret?
2. Khi App Configuration chứa Key Vault reference, thành phần nào thật sự truy xuất secret?
3. Một identity có `App Configuration Data Reader` nhưng không có quyền đọc Key Vault sẽ gặp vấn đề gì?
4. Vì sao thay secret version chưa bảo đảm một bean Spring đang chạy nhìn thấy giá trị mới?
5. Khi nào dùng Key Vault Secrets property source trực tiếp thay cho App Configuration Key Vault reference?

**Đáp án gợi ý:** (1) Key Vault cung cấp quản trị vòng đời và quyền trên bí mật/khóa/chứng chỉ chuyên dụng; (2) provider phía ứng dụng; (3) đọc được reference nhưng không resolve được secret; (4) còn version URI, cache, refresh và vòng đời bean; (5) khi ứng dụng chỉ cần đọc secret theo tên và không cần quản lý con trỏ qua App Configuration.

## 10. Tài liệu tham khảo chính thức

- [Microsoft Learn – Azure App Configuration FAQ](https://learn.microsoft.com/en-us/azure/azure-app-configuration/faq): so sánh với Key Vault và khuyến nghị lưu secret.
- [Microsoft Learn – Azure App Configuration quickstart cho Spring](https://learn.microsoft.com/en-us/azure/azure-app-configuration/quickstart-java-spring-app): dependency, `spring.config.import` và quy ước `/application/`.
- [Microsoft Learn – Key Vault references trong Spring](https://learn.microsoft.com/en-us/azure/azure-app-configuration/use-key-vault-references-spring-boot): liên kết hai dịch vụ.
- [Microsoft Learn – Dynamic configuration trong Spring](https://learn.microsoft.com/en-us/azure/azure-app-configuration/enable-dynamic-configuration-java-spring-app): cơ chế refresh.
- [Microsoft Learn – Spring Cloud Azure configuration](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configuration): thuộc tính cấu hình các Azure SDK clients và Key Vault property source.
- [Azure SDK – Spring versions mapping](https://github.com/Azure/azure-sdk-for-java/wiki/Spring-Versions-Mapping): chọn BOM tương thích Spring Boot.
- [Microsoft Learn – App Configuration với Microsoft Entra ID](https://learn.microsoft.com/en-us/azure/azure-app-configuration/concept-enable-rbac): phân quyền truy xuất dữ liệu.

Trong hệ thống thực tế, hãy chọn mô hình theo **đặc tính dữ liệu và vòng đời cập nhật**: App Configuration cho điều khiển hành vi và feature flags; Key Vault cho secret/key/certificate. Khi kết hợp, ứng dụng Spring Cloud Azure được quyền đọc cấu hình, nhận reference và tự truy xuất secret từ Key Vault theo danh tính được cấp quyền riêng.
