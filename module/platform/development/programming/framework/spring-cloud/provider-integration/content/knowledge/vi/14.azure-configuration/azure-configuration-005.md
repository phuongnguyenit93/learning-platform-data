# Tích hợp Key Vault Secrets và ánh xạ bí mật vào thuộc tính

Một ứng dụng Spring Boot có thể phải kết nối cổng thanh toán, cơ sở dữ liệu và API đối tác bằng mật khẩu hoặc API token. Việc đặt những giá trị này trực tiếp trong `application.yml` khiến bí mật dễ đi vào Git, build artifact, log hoặc bản sao cấu hình. **Azure Key Vault Secrets** lưu giá trị nhạy cảm trong dịch vụ managed, hỗ trợ cấp quyền đọc theo danh tính và quản lý các phiên bản secret.

**Spring Cloud Azure Key Vault Secrets** có thể chuyển secret thành một nguồn `PropertySource` trong Spring `Environment`. Nhờ đó, `@Value`, `@ConfigurationProperties` và các auto-configuration như `spring.datasource.password` có thể nhận dữ liệu khi ứng dụng khởi động, trong khi mã nguồn không chứa giá trị bí mật.

Bài thuộc chương **Cấu hình Azure** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed từ AWS, Azure và Google Cloud, bao gồm danh tính và quyền, storage, messaging, dữ liệu, secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Trọng tâm ở đây là **tích hợp Key Vault Secrets, ánh xạ tên secret thành thuộc tính Spring và bảo vệ vòng đời sử dụng bí mật**.

## 1. Học xong cần làm được gì?

Bạn sẽ biết cách:

1. Chọn **Key Vault Secrets PropertySource** cho cấu hình cần có ngay từ khi khởi động; phân biệt với Azure SDK `SecretClient` và Key Vault reference trong App Configuration.
2. Thiết lập vault endpoint, danh sách `secret-keys` và danh tính với quyền đọc tối thiểu.
3. Hiểu vì sao tên secret có dấu `-` nhưng Spring property có dấu `.`, và cách dùng placeholder alias.
4. Bind secret vào bean hoặc các thuộc tính có sẵn của Spring Boot mà không in giá trị nhạy cảm.
5. Xử lý nhiều vault, thứ tự ưu tiên, refresh, rotation, kiểm thử và lỗi xác thực.

Tình huống xuyên suốt: `checkout-service` cần `payments-api-token` để gọi nhà cung cấp thanh toán và `database-password` để kết nối cơ sở dữ liệu dev. Không secret nào được commit vào repository.

## 2. Bí mật thuộc Key Vault, tham số thường thuộc App Configuration

| Dữ liệu | Nơi quản lý thích hợp | Khi đọc trong Spring |
| --- | --- | --- |
| Token thanh toán, mật khẩu DB, webhook signing secret | **Key Vault Secrets** | Key Vault PropertySource hoặc `SecretClient` |
| Khóa mật mã dùng ký/giải mã trong HSM | **Key Vault Keys** | API Keys/Cryptography, không phải starter Secrets |
| Chứng chỉ được quản lý trong vault | **Key Vault Certificates** | API Certificates và cơ chế chứng chỉ phù hợp |
| Timeout, retry, endpoint không nhạy cảm | **Azure App Configuration** | App Configuration config provider |
| Feature flags | **Azure App Configuration Feature Manager** | Feature management library |
| URI chỉ đến một secret | **App Configuration Key Vault reference** | Provider nhận reference rồi tự truy vấn Key Vault |

Một secret là **giá trị dữ liệu nhạy cảm**, không đồng nghĩa với đối tượng **key** hay **certificate**. Starter `spring-cloud-azure-starter-keyvault-secrets` phục vụ thao tác với Secret và `PropertySource`; nó không tự động cung cấp toàn bộ quy trình ký bằng khóa Key Vault hay cấu hình TLS certificate.

### 2.1. Ba con đường truy xuất secret

| Cơ chế | Đọc khi nào | Phù hợp khi |
| --- | --- | --- |
| **KeyVaultPropertySource** | Khởi động và mỗi lần refresh được cấu hình | Secret phải được bind như một Spring property để tạo bean |
| **SecretClient** | Khi chương trình gọi API | Cần đọc chủ động theo tên/phiên bản hoặc xử lý từng lỗi |
| **App Configuration Key Vault reference** | Khi provider App Configuration nạp và giải tham chiếu | Muốn quản lý các khóa ứng dụng trong App Configuration nhưng giữ giá trị nhạy cảm ở vault |

Bài dùng **KeyVaultPropertySource trực tiếp**. Nếu chỉ dùng starter Secrets, bạn **không cần** `spring.config.import=azureAppConfiguration`: import này dành cho tích hợp Azure App Configuration.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant Source as KeyVaultPropertySource
    participant Entra as Microsoft Entra ID
    participant Vault as Azure Key Vault
    participant Bean as Spring Binder/Bean
    App->>Source: Đọc cấu hình endpoint và secret-keys
    Source->>Entra: Lấy token của danh tính ứng dụng
    Entra-->>Source: Token truy cập
    Source->>Vault: Get secret
    Vault-->>Source: Giá trị secret nếu được cấp quyền
    Source-->>App: Bổ sung PropertySource vào Environment
    App->>Bean: Resolve placeholder và bind property
    Note over Bean: Không log secret
~~~

## 3. Tạo vault và định danh secret

Giả sử Azure Key Vault của môi trường phát triển có tên `demo-checkout-kv` với endpoint:

~~~text
https://demo-checkout-kv.vault.azure.net/
~~~

Tạo hai **secret dùng giá trị giả** trong Azure portal → Key Vault → Secrets:

| Secret name | Mục đích | Gợi ý cho thực hành |
| --- | --- | --- |
| `payments-api-token` | Token xác thực payment gateway | Dùng chuỗi thử nghiệm không có quyền trên hệ thống thật |
| `database-password` | Password của DB dev | Dùng password chỉ dành cho database thử nghiệm |

Đừng đưa giá trị production vào tài liệu, lệnh shell có lưu history, issue hoặc log để minh họa.

**Phân biệt ba thứ:**

~~~text
Tên secret:        payments-api-token
URI secret:        https://demo-checkout-kv.vault.azure.net/secrets/payments-api-token
URI có phiên bản:  https://demo-checkout-kv.vault.azure.net/secrets/payments-api-token/<version>
Secret value:      Giá trị chỉ được trả về cho identity có quyền đọc
~~~

Bản ghi secret có thể có **nhiều phiên bản**. Tên secret ổn định nhưng giá trị hiện hành có thể thay đổi khi phát hành version mới. Khi cấu hình `KeyVaultPropertySource`, bạn cung cấp **vault endpoint** và tên secret; không cần đưa cả từng URI vào `application.yml`.

### 3.1. Quy tắc tên secret

Tên secret của Azure Key Vault chấp nhận **chữ Latin, chữ số và dấu gạch nối `-`**. Dấu chấm `.`, gạch dưới `_`, dấu cách hay dấu `/` không phải ký tự hợp lệ trong tên secret. Ví dụ:

~~~text
Hợp lệ:    payments-api-token
Hợp lệ:    spring-datasource-password
Không dùng: spring.datasource.password
Không dùng: payments_api_token
~~~

Trong Spring lại thường có tên property phân cấp như `spring.datasource.password` hoặc `checkout.gateway.api-token`. Sự khác biệt này dẫn tới nhu cầu ánh xạ hoặc dùng placeholder, được trình bày ở mục 6.

## 4. Danh tính, quyền và bảo vệ vault

Trước khi kết nối, xác định vault dùng **Azure RBAC** hay **Vault access policy** (mô hình cũ). Khi dùng Microsoft Entra ID, danh tính đọc secret và danh tính tạo/cập nhật secret nên được phân quyền khác nhau.

| Mô hình | Quyền cho ứng dụng chỉ đọc |
| --- | --- |
| **Azure RBAC** | Gán role **Key Vault Secrets User** tại scope vault phù hợp |
| **Vault access policy** | Cho phép `Get`; xét thêm `List` khi ứng dụng cần liệt kê nhiều secret |
| **Role quản lý Azure resource** | `Key Vault Contributor` không mặc nhiên cho quyền đọc **secret value** |

Role `Key Vault Secrets Officer` và `Key Vault Administrator` rộng hơn yêu cầu của một workload chỉ cần đọc; tránh gán các role này để chữa lỗi 403. Theo khuyến nghị Key Vault RBAC, cân nhắc **vault riêng theo ứng dụng và môi trường** khi cần tách biệt trách nhiệm.

### 4.1. Chạy ở local so với cloud

| Nơi chạy | Danh tính phù hợp |
| --- | --- |
| Máy lập trình | Azure CLI/IDE/Developer CLI credential phù hợp và principal được cấp quyền |
| Azure App Service hoặc VM | **Managed Identity** được bật trên đúng workload |
| Container dùng workload identity federation | Principal được liên kết với workload qua cơ chế federation |
| Pipeline CI | Principal thử nghiệm riêng, scope giới hạn, không dùng quyền production |

`az login` chỉ đăng nhập Azure CLI; mã Spring vẫn phải chọn được credential phù hợp. Tài khoản hiển thị trên portal, tài khoản trong CLI và principal Managed Identity chạy production có thể **khác nhau**. Nếu thấy 403, kiểm tra danh tính thực sự được Azure SDK sử dụng cùng scope role và mô hình phân quyền của vault.

Managed Identity loại bỏ nhu cầu lưu **client secret để đăng nhập Azure**. Nó không thay thế mọi secret của bên thứ ba: token cổng thanh toán vẫn có thể cần được lưu trong Key Vault nếu đối tác không hỗ trợ xác thực trực tiếp bằng identity.

## 5. Thêm dependency Spring Cloud Azure

Ví dụ dùng **Spring Boot 3.5.x** và **Spring Cloud Azure 6.5.0**. Theo tài liệu Microsoft, Spring Boot 4.0.x sử dụng Spring Cloud Azure 7.x (ví dụ 7.4.0). Hãy kiểm tra bảng tương thích khi dùng các phiên bản khác.

Trong `pom.xml` của dự án Maven đã có Spring Boot parent hoặc dependency management, thêm:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-cloud-azure.version>6.5.0</spring-cloud-azure.version>
</properties>

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
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-keyvault-secrets</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

BOM (`spring-cloud-azure-dependencies`) giữ các thư viện cùng dòng tương thích. Không cần đặt version riêng cho starter khi đã nhập BOM.

## 6. Cấu hình Key Vault PropertySource và ánh xạ tên

### 6.1. Chỉ tải hai secret cần thiết

Tạo `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: checkout-service
  cloud:
    azure:
      keyvault:
        secret:
          property-source-enabled: true
          property-sources:
            - name: checkout-vault
              endpoint: "${AZURE_KEYVAULT_ENDPOINT}"
              secret-keys:
                - payments-api-token
                - database-password
~~~

Đặt biến môi trường chỉ chứa endpoint:

~~~text
AZURE_KEYVAULT_ENDPOINT=https://demo-checkout-kv.vault.azure.net/
~~~

Trong PowerShell:

~~~powershell
$Env:AZURE_KEYVAULT_ENDPOINT = "https://demo-checkout-kv.vault.azure.net/"
~~~

Hoặc Linux/macOS shell:

~~~bash
export AZURE_KEYVAULT_ENDPOINT="https://demo-checkout-kv.vault.azure.net/"
~~~

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `property-source-enabled` | Bật Key Vault PropertySource, mặc định `true` |
| `property-sources[].name` | Tên nguồn để phân biệt khi xem `Environment` |
| `property-sources[].endpoint` | Endpoint của **vault**, không phải URI của một secret |
| `property-sources[].secret-keys` | Chỉ định tên các secret cần lấy từ vault |
| `property-sources[].case-sensitive` | Cho phép phân biệt chữ hoa/thường khi tra property; mặc định `false` |
| `property-sources[].refresh-interval` | Chu kỳ làm mới; mặc định `30m` |

Nếu bỏ `secret-keys`, provider có thể tải **toàn bộ secret**. Khi vault chứa hàng trăm secret, hãy liệt kê rõ tên cần thiết để giảm chi phí truy cập, nhu cầu `List` và phạm vi dữ liệu đưa vào `Environment`.

### 6.2. Cơ chế tên secret và tên property

Ví dụ tên secret `spring-datasource-password`. Theo tài liệu Spring Cloud Azure, provider hỗ trợ truy cập bằng:

- `spring-datasource-password` — tên secret trực tiếp;
- `spring.datasource.password` — dạng phân cấp được chuyển đổi.

Nhưng **không** giả định `spring.datasource-password` cũng tương đương. Không phải mọi cách thay dấu `-` và `.` đều được Spring Cloud Azure coi như nhau.

| Tên trong vault | Tên Spring muốn dùng | Cách thực hiện |
| --- | --- | --- |
| `spring-datasource-password` | `spring.datasource.password` | Ánh xạ được provider hỗ trợ |
| `payments-api-token` | `payments-api-token` | Đọc bằng tên secret trực tiếp |
| `payments-api-token` | `checkout.gateway.api-token` | Tạo **placeholder alias** tường minh |
| `database-password` | `spring.datasource.password` | Tạo **placeholder alias** tường minh |

Với property có cấu trúc phức tạp, alias rõ ràng dễ kiểm thử và ít phụ thuộc vào suy đoán về quy tắc chuyển đổi.

### 6.3. Alias bằng placeholder

Bổ sung ngoài root `spring` trong `application.yml`:

~~~yaml
checkout:
  gateway:
    api-token: "${payments-api-token}"
~~~

Lúc này:

~~~text
Azure Key Vault secret       KeyVaultPropertySource       Spring property
payments-api-token       -> payments-api-token       -> checkout.gateway.api-token
                                      được resolve qua placeholder
~~~

Đây **không phải bản sao secret** được lưu trên Azure; nó là một công thức Spring để tìm giá trị đã nạp. Nên bỏ fallback đối với secret bắt buộc. Ví dụ `${payments-api-token:demo}` có thể khiến ứng dụng production chạy bằng credential giả và che mất lỗi xác thực.

### 6.4. Ví dụ application.yml hoàn chỉnh

~~~yaml
spring:
  application:
    name: checkout-service
  cloud:
    azure:
      keyvault:
        secret:
          property-source-enabled: true
          property-sources:
            - name: checkout-vault
              endpoint: "${AZURE_KEYVAULT_ENDPOINT}"
              secret-keys:
                - payments-api-token

checkout:
  gateway:
    api-token: "${payments-api-token}"
~~~

Khi thêm DataSource, chỉ cần thêm `database-password` vào `secret-keys` và đặt `spring.datasource.password: "${database-password}"` dưới **root `spring` đã có**. Tránh viết hai root `spring:` trùng nhau trong cùng YAML document.

### 6.5. Dùng secret để cấu hình DataSource

Một ví dụ riêng, dành cho ứng dụng đã thêm JDBC/JPA starter và cấu hình database:

~~~yaml
spring:
  datasource:
    url: "${DB_JDBC_URL}"
    username: "${DB_USERNAME}"
    password: "${database-password}"
~~~

Đây là **đoạn cần ghép vào root `spring`** của file cấu hình đầy đủ ở mục 6.4. Khi khởi động, KeyVaultPropertySource đã đưa `database-password` vào `Environment`; Spring Boot có thể resolve placeholder để tạo DataSource.

Nếu database hỗ trợ **xác thực passwordless bằng Microsoft Entra ID/Managed Identity**, hãy cân nhắc cách đó để loại bỏ nhu cầu lưu password. Khi vẫn cần password, rotation phải phối hợp việc đổi phía database và làm mới connection pool.

### 6.6. Trường hợp user-assigned Managed Identity

Nếu môi trường Azure có nhiều identity và cần chọn cụ thể một user-assigned identity:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - name: checkout-vault
              endpoint: "${AZURE_KEYVAULT_ENDPOINT}"
              secret-keys:
                - payments-api-token
              credential:
                managed-identity-enabled: true
                client-id: "${AZURE_CLIENT_ID}"
~~~

`AZURE_CLIENT_ID` là ID của Managed Identity, **không phải client secret**. Cấu hình trên là lựa chọn **thay thế** phần cấu hình endpoint/credential của ví dụ trước khi triển khai user-assigned identity; phải bật/gắn identity vào workload và cấp role Key Vault Secrets User cho đúng principal.

## 7. Bind secret vào Spring Boot

### 7.1. Sử dụng `@ConfigurationProperties`

Tạo `CheckoutApplication.java`:

~~~java
package com.example.checkout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CheckoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(CheckoutApplication.class, args);
    }
}
~~~

Tạo `GatewayCredentials.java`:

~~~java
package com.example.checkout;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout.gateway")
public record GatewayCredentials(String apiToken) {
    public GatewayCredentials {
        if (apiToken == null || apiToken.isBlank()) {
            throw new IllegalArgumentException(
                    "Required checkout.gateway.api-token is missing");
        }
    }

    @Override
    public String toString() {
        // Record mặc định có toString() chứa field, không để lộ token.
        return "GatewayCredentials[REDACTED]";
    }
}
~~~

Tạo `GatewayReadinessCheck.java`:

~~~java
package com.example.checkout;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class GatewayReadinessCheck {
    @Bean
    ApplicationRunner verifyGatewayCredential(GatewayCredentials credentials) {
        return args -> {
            if (credentials.apiToken().isBlank()) {
                throw new IllegalStateException("Gateway credential unavailable");
            }
            // Không log giá trị credentials.apiToken().
        };
    }
}
~~~

Kết quả: secret `payments-api-token` được resolve thành `checkout.gateway.api-token` rồi bind vào `GatewayCredentials.apiToken()`. Logic nghiệp vụ sử dụng token thông qua đối tượng cấu hình, không cần biết URI Key Vault.

**Lưu ý với Java record:** phương thức `toString()` mặc định thường in toàn bộ trường. Với secret, nên override như trên hoặc dùng class thông thường không tự sinh `toString()` tiết lộ dữ liệu. Việc lưu token trong `String` vẫn khiến nó hiện diện trong bộ nhớ ứng dụng; cần hạn chế phạm vi đối tượng có quyền truy cập.

### 7.2. Dùng `@Value`

Một bean có thể lấy property đơn lẻ:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GatewayTokenProvider {
    private final String token;

    public GatewayTokenProvider(
            @Value("${checkout.gateway.api-token}") String token) {
        this.token = token;
    }

    public boolean isConfigured() {
        return token != null && !token.isBlank();
    }
}
~~~

`@Value` gọn cho một property nhưng khiến chuỗi tên key dễ lặp lại ở nhiều lớp. `@ConfigurationProperties` phù hợp hơn khi nhiều tham số được dùng cùng nhau. Đừng tạo REST endpoint trả token chỉ để xác minh thử nghiệm.

### 7.3. Chọn nơi xác minh bí mật

Một cách xác minh an toàn là **khởi động thành công và thực hiện giao dịch thử** bằng tài khoản đối tác sandbox. Có thể log việc credential đã được cấu hình bằng một giá trị boolean, nhưng không log chính token, password hoặc object chứa secret. Nếu test rơi vào nhánh thất bại, exception cũng chỉ nên nêu **tên property bị thiếu**, không nối thêm giá trị.

## 8. Nhiều vault và thứ tự ưu tiên

Giả sử ứng dụng cần một vault riêng cho thanh toán và một vault dùng chung:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - name: payments-vault
              endpoint: "${PAYMENTS_KEYVAULT_ENDPOINT}"
              secret-keys:
                - payments-api-token
            - name: shared-vault
              endpoint: "${SHARED_KEYVAULT_ENDPOINT}"
              secret-keys:
                - shared-webhook-key
~~~

Theo tài liệu Microsoft về Spring Cloud Azure secret management:

- Nếu **cùng một secret** được nạp vào nhiều Key Vault PropertySource, nguồn khai báo **đứng trước** có độ ưu tiên cao hơn nguồn đứng sau.
- `SystemEnvironmentPropertySource` (biến môi trường) có độ ưu tiên cao hơn Key Vault PropertySource; vì vậy một biến môi trường có thể ghi đè giá trị từ vault.
- Các nguồn khác trong Spring `Environment` có quy tắc ưu tiên riêng, nên vẫn cần kiểm tra thứ tự thực tế khi property trùng tên.

Thứ tự này **khác** với một số quy tắc gộp App Configuration stores. Không chuyển nguyên giả định về ưu tiên App Configuration sang Key Vault.

**Khuyến nghị:** tránh đặt secret cùng tên ở nhiều vault nếu không có chủ đích. Khi phải chia sẻ, hãy thiết kế namespace và kiểm tra rõ nguồn nào thắng, đặc biệt giữa `dev`/`prod`.

## 9. Khi nào dùng `SecretClient` thay cho PropertySource?

PropertySource phù hợp với thuộc tính cần ở startup. Nếu cần đọc một secret **theo yêu cầu** hoặc một **version cụ thể**, Azure SDK `SecretClient` là lựa chọn trực tiếp.

Ví dụ minh họa một service kiểm tra sự tồn tại, không in giá trị:

~~~java
package com.example.checkout;

import com.azure.security.keyvault.secrets.SecretClient;
import org.springframework.stereotype.Service;

@Service
public class VaultSecretProbe {
    private final SecretClient secretClient;

    public VaultSecretProbe(SecretClient secretClient) {
        this.secretClient = secretClient;
    }

    public boolean hasGatewayToken() {
        String token = secretClient.getSecret("payments-api-token").getValue();
        return token != null && !token.isBlank();
    }
}
~~~

Để inject `SecretClient` được Spring Cloud Azure auto-configure, cần cấu hình endpoint của SDK client, ví dụ:

~~~properties
spring.cloud.azure.keyvault.secret.endpoint=${AZURE_KEYVAULT_ENDPOINT}
~~~

Điều này khác với endpoint của `property-sources[0]`. Khi có **nhiều vault**, đừng mặc định một bean `SecretClient` sẽ tự chọn đúng vault theo tên secret; cấu hình client riêng hoặc xây dựng các client có endpoint/credential rõ ràng.

Bảng so sánh thời điểm đọc:

| Cơ chế | Giá trị xuất hiện | Điều cần lưu ý |
| --- | --- | --- |
| `KeyVaultPropertySource` | Trong Spring `Environment` | Có chu kỳ refresh nhưng bean có thể giữ giá trị cũ |
| `SecretClient.getSecret` | Kết quả trả về khi gọi API | Phải chủ động xử lý latency, retry, lỗi và cache |
| App Configuration Key Vault reference | Property đã giải tham chiếu | Cần thêm quyền đọc App Configuration và Key Vault |

## 10. Refresh, rotation và phiên bản secret

### 10.1. Refresh mặc định 30 phút

Theo tài liệu Spring Cloud Azure, `KeyVaultPropertySource` mặc định refresh **mỗi 30 phút**. Có thể cấu hình:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - name: checkout-vault
              endpoint: "${AZURE_KEYVAULT_ENDPOINT}"
              secret-keys:
                - payments-api-token
              refresh-interval: 60m
~~~

`refresh-interval: 60m` thay chu kỳ thành 60 phút; đặt `0` để **tắt refresh tự động**. Chu kỳ này không đồng nghĩa mọi bean nhận secret mới ngay khi Key Vault có version mới.

Ví dụ, một HTTP client được tạo ở startup với `String token` rồi giữ trong field có thể tiếp tục dùng token cũ dù PropertySource đã làm mới. Tương tự, DataSource hoặc connection pool không được tự động tái tạo chỉ vì property `spring.datasource.password` đã thay đổi.

### 10.2. Rotation cần điều phối cả phía sử dụng

Một quy trình đổi `payments-api-token` an toàn:

1. Tạo credential mới ở nhà cung cấp thanh toán và xác nhận có thể chấp nhận token cũ/mới trong giai đoạn chuyển tiếp.
2. Tạo **version secret mới** trong Key Vault bằng quy trình bảo vệ giá trị.
3. Cho các instance đọc giá trị mới theo kế hoạch refresh/restart; tái tạo các HTTP client đang cache credential nếu cần.
4. Quan sát lỗi 401/403 và giao dịch sandbox; xác nhận mọi instance đều dùng credential hợp lệ.
5. Thu hồi token cũ sau khi đã chuyển đổi, kiểm tra không còn request dùng credential cũ.

Với `SecretClient` đọc version cố định hoặc Key Vault reference có URI ghim version, bạn phải **đổi version được tham chiếu** nếu muốn nhận giá trị mới. Đừng xem “đã tạo secret version mới” là bằng chứng rotation hoàn tất.

### 10.3. Giới hạn và retry

Một ứng dụng có nhiều instance khởi động cùng lúc có thể tạo nhiều yêu cầu tới Key Vault. Nếu không giới hạn `secret-keys` hoặc refresh quá ngắn, có thể gặp lỗi 429/throttling. Dùng retry có backoff và giám sát, nhưng **không** biến retry thành vòng lặp vô hạn ở mỗi HTTP request nghiệp vụ.

## 11. Bảo mật khi secret đã vào Environment

Key Vault bảo vệ dữ liệu khi lưu và kiểm soát quyền đọc ở dịch vụ. Nhưng sau khi Spring giải secret thành `String`, giá trị đã hiện diện trong bộ nhớ ứng dụng.

| Rủi ro | Biện pháp |
| --- | --- |
| In cả `Environment`, config object, record hoặc exception | Chỉ log tên key và trạng thái; redacted `toString()` cho object chứa secret |
| Lộ giá trị từ Spring Actuator | Hạn chế hoặc tắt `/env`, `/configprops`; bảo vệ quyền truy cập và kiểm tra masking |
| Lưu secret trong Git hoặc image/container layer | Chỉ commit endpoint, tên secret, placeholder; không commit giá trị |
| Chọn nhầm danh tính khi deploy | Kiểm tra principal Managed Identity, tenant và RBAC |
| Vault dev/prod dùng chung quyền | Tách vault hoặc role theo workload và môi trường |
| Gọi Key Vault liên tục | Dùng refresh/cache hợp lý, đo quota và độ trễ |
| Lỗi mạng tới vault | Kiểm tra firewall, private endpoint, DNS, proxy và routing |
| Lộ token qua HTTP query string | Truyền credential qua cơ chế xác thực được SDK đối tác hỗ trợ |

Với tính năng thanh toán, hãy chỉ truyền token vào **client phải sử dụng token**. Tránh đưa secret vào DTO API, log, metric label, trace tag hoặc thông báo lỗi gửi cho người dùng.

## 12. Kiểm thử không phụ thuộc Azure thật

### 12.1. Spring test chỉ kiểm tra binding

Khi kiểm tra `GatewayCredentials`, không cần kết nối vault. Có thể vô hiệu hóa Key Vault PropertySource rồi cung cấp giá trị giả qua test property:

~~~java
package com.example.checkout;

import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "spring.cloud.azure.keyvault.secret.property-source-enabled=false",
    "checkout.gateway.api-token=test-placeholder"
})
class GatewayCredentialsTest {
    @Autowired
    GatewayCredentials credentials;

    @Test
    void bindsSecretAliasWithoutAzure() {
        assertThat(credentials.apiToken()).isEqualTo("test-placeholder");
        assertThat(credentials.toString()).doesNotContain("test-placeholder");
    }
}
~~~

Test này chứng minh việc **bind property vào Java** và redaction của object. Nó không chứng minh token từ Azure hay quyền Key Vault hoạt động. Nếu `application.yml` còn cấu hình App Configuration độc lập, cần tắt provider đó riêng trong test.

### 12.2. Integration test trên vault dev

Dùng một vault thử nghiệm tách khỏi production và một identity chỉ có quyền đọc:

1. Tạo secret giả `payments-api-token` trong vault dev.
2. Chạy app với endpoint dev; xác nhận bean có credential và client sandbox xác thực thành công.
3. Cấu hình `secret-keys` chỉ chứa secret cần thiết và kiểm tra property khác không được nạp.
4. Thử principal không có quyền đọc, xác nhận lỗi được log dưới dạng mã/loại lỗi và **không chứa secret**.
5. Tạo phiên bản secret thử nghiệm mới; xác minh hành vi trước/sau refresh hoặc restart.
6. Nếu dùng hai vault, kiểm tra thứ tự ưu tiên bằng secret giả trùng tên.
7. Thử lỗi mạng hoặc quota ở môi trường kiểm thử và quan sát tác động tới thời gian khởi động.

Không chạy rotation thử nghiệm trên vault production.

### 12.3. Kiểm tra nguồn mà không in giá trị

Khi cần tìm property bị thiếu, có thể tạm bổ sung một diagnostic trong môi trường dev:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

@Configuration
class SecretSourceDiagnostic {
    @Bean
    ApplicationRunner reportSource(ConfigurableEnvironment environment) {
        return args -> {
            String key = "payments-api-token";
            System.out.println("Configured: " + environment.containsProperty(key));
            for (PropertySource<?> source : environment.getPropertySources()) {
                if (source.containsProperty(key)) {
                    System.out.println("PropertySource: " + source.getName());
                }
            }
        };
    }
}
~~~

Đoạn code chỉ in **có/không** và **tên nguồn**, không in `environment.getProperty(key)`. Gỡ diagnostic sau khi dùng và tránh kiểm tra các secret không cần thiết.

## 13. Khắc phục sự cố

| Biểu hiện | Nguyên nhân cần kiểm tra | Gợi ý xử lý |
| --- | --- | --- |
| 401 ở Key Vault | Credential chain, token, tenant sai | Kiểm tra identity SDK thực sự dùng |
| 403 dù đã login Azure | Thiếu data-plane role, sai scope hoặc vault dùng mô hình access policy khác | Gán `Key Vault Secrets User` đúng principal hoặc quyền `Get` phù hợp |
| Lỗi khi provider liệt kê secret | Thiếu `List` ở mô hình access policy hoặc vault quá nhiều secret | Dùng `secret-keys` và phân quyền phù hợp |
| Secret không tồn tại | Sai tên, sai vault, disabled/expired, phiên bản không hợp lệ | Xác minh metadata, không in value |
| `@Value` báo thiếu property | Sai alias, secret chưa nạp hoặc property name không khớp | Kiểm tra endpoint, `secret-keys` và tên placeholder |
| Tên secret có dấu `.` không tạo được | Quy tắc đặt tên của Key Vault | Đổi sang dấu `-`; tạo alias Spring khi cần |
| Secret có nhưng `spring.datasource-password` không hoạt động | Không phải phép ánh xạ được bảo đảm | Dùng `spring.datasource.password` hoặc placeholder rõ |
| Đổi secret nhưng bean giữ token cũ | Chưa refresh, bean/client cache giá trị | Kiểm tra `refresh-interval` và vòng đời client |
| Local chạy được, Azure deploy lỗi | Managed Identity khác principal local; firewall/private endpoint khác | Kiểm tra principal, RBAC, DNS/VNet |
| Hai vault có cùng key trả về nguồn bất ngờ | Thứ tự `property-sources` | Nguồn khai báo đầu tiên được ưu tiên theo tài liệu |
| Test vô tình truy cập Azure | Chưa tắt PropertySource | Set `property-source-enabled=false` và dùng property giả |

## 14. Bài tập tổng hợp

Dịch vụ `shipping-service` có timeout vận hành `shipping.timeout=PT4S` và token nhà vận chuyển cần giữ bí mật.

Yêu cầu:

1. Lưu token trong Key Vault với tên `shipping-provider-token`.
2. Trong Spring, bean muốn đọc nó qua property `shipping.provider.token`.
3. Ứng dụng chỉ được đọc secret; không được tạo/xóa secret.
4. Khi token được thay, client phải thực sự sử dụng giá trị mới.
5. Test binding chạy local không gọi Azure; integration test dùng vault dev.

Một cấu hình giải được bài tập:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - name: shipping-vault
              endpoint: "${AZURE_KEYVAULT_ENDPOINT}"
              secret-keys:
                - shipping-provider-token

shipping:
  timeout: PT4S
  provider:
    token: "${shipping-provider-token}"
~~~

Bind vào Java:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shipping.provider")
public record ProviderCredentials(String token) {
    @Override
    public String toString() {
        return "ProviderCredentials[REDACTED]";
    }
}
~~~

Nhớ bật `@ConfigurationPropertiesScan` trên ứng dụng. Sau khi cấu hình, hãy giải thích:

- Vì sao không đặt token thật vào `application.yml`?
- Vì sao tên secret và tên Spring property có thể khác nhau?
- Nếu thiếu quyền đọc, vấn đề xảy ra ở lớp Azure hay Spring Binder?
- Nếu PropertySource refresh xong, vì sao client đã tạo vẫn có thể giữ token cũ?
- Nếu một secret tồn tại ở hai vault, quy tắc chọn nguồn nào được áp dụng?
- Khi nào có thể thay hoàn toàn password bằng Managed Identity?

**Đáp án định hướng:** Key Vault bảo vệ secret và phân quyền, alias ánh xạ property, lỗi quyền xảy ra khi truy xuất Key Vault, refresh nguồn không tự tái tạo client, KeyVaultPropertySource đầu danh sách ưu tiên, Managed Identity phù hợp khi dịch vụ đích hỗ trợ phương thức xác thực đó.

## 15. Tài liệu tham khảo chính thức

- [Microsoft Learn – Spring Cloud Azure secret management](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/secret-management): cấu hình PropertySource, `secret-keys`, tên secret, ưu tiên và refresh.
- [Microsoft Learn – Load a secret from Azure Key Vault in Spring Boot](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configure-spring-boot-starter-java-app-with-azure-key-vault): hai cách đọc qua `SecretClient` và PropertySource.
- [Microsoft Learn – Spring Cloud Azure configuration](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configuration): cấu hình credential, retry và client theo cấp global/service.
- [Microsoft Learn – Key Vault RBAC guide](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide): phân quyền đọc/ghi, role và phạm vi.
- [Microsoft Learn – Assign a Key Vault access policy](https://learn.microsoft.com/en-us/azure/key-vault/general/assign-access-policy): mô hình access policy cũ và phạm vi quyền.
- [Microsoft Learn – Key Vault Secrets PropertySource sample](https://learn.microsoft.com/en-us/samples/azure-samples/azure-spring-boot-samples/loading-secrets-from-azure-key-vault-to-property-source-in-spring-boot-application/): tải một hoặc nhiều vault và chọn secret.
- [Spring Boot – Externalized configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): `Environment`, placeholder và nguồn ưu tiên.

**Điểm cốt lõi:** tích hợp Key Vault Secrets phải giải quyết **ba vấn đề riêng**: danh tính có quyền đọc vault, phép ánh xạ tên secret sang Spring property, và kế hoạch cập nhật những bean/client đang sử dụng secret khi giá trị thay đổi. Hoàn thành cả ba mới bảo đảm hệ thống sử dụng secret đúng và không vô tình làm lộ thông tin.
