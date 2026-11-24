# Tham chiếu Key Vault trong App Configuration

Khi một ứng dụng Spring Boot cần token thanh toán, mật khẩu database hoặc khóa API đối tác, nhóm phát triển thường muốn quản lý **tên cấu hình ứng dụng** ở một nơi nhưng giữ **giá trị bí mật** trong kho có phân quyền và vòng đời riêng. **Azure App Configuration Key Vault reference** giải quyết nhu cầu đó: App Configuration lưu **URI chỉ tới secret**, trong khi giá trị thật nằm tại **Azure Key Vault**.

Với thư viện **Spring Cloud Azure App Configuration**, một key kiểu Key Vault reference được đọc như một key cấu hình. Client ở phía **ứng dụng** nhận URI, truy vấn Key Vault bằng danh tính có quyền, rồi đưa giá trị đã giải tham chiếu vào Spring `Environment`. Sau đó, `@Value`, `@ConfigurationProperties` hoặc auto-configuration của Spring Boot có thể dùng property như bình thường.

Đây là bài trong chương **Cấu hình Azure**, thuộc mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud, bao gồm cấu hình danh tính/quyền, storage, messaging, dữ liệu, secret, kiểm thử tích hợp và so sánh provider. Bài này tập trung vào **Key Vault reference của App Configuration**, quyền truy cập tới **hai dịch vụ**, quy tắc nạp vào Spring và việc xoay vòng secret an toàn.

## 1. Học xong cần biết và làm được gì?

1. Phân biệt **App Configuration key-value thường**, **Key Vault reference**, và **Key Vault Secrets PropertySource trực tiếp**.
2. Tạo secret trong Key Vault và tạo reference chứa URI trong App Configuration bằng portal hoặc Azure CLI.
3. Cấp **App Configuration Data Reader** và **Key Vault Secrets User** cho đúng danh tính chạy ứng dụng.
4. Cấu hình `spring.config.import=azureAppConfiguration`, chọn key/label và bind property nhận từ reference vào Java.
5. Hiểu URI có/không có **version**, tác động của refresh, cache và vòng đời bean khi rotate secret.
6. Chẩn đoán lỗi quyền/mạng/selector, kiểm thử binding riêng và kiểm thử tích hợp với hai dịch vụ.

Tình huống xuyên suốt là `checkout-service`. Ứng dụng sử dụng `payments.api-token` để kết nối nhà cung cấp thanh toán và `payments.timeout` để đặt thời gian chờ. Token bí mật nằm trong Key Vault; timeout không nhạy cảm nằm trong App Configuration. Cả hai cuối cùng trở thành Spring properties.

## 2. Kiến trúc: tham chiếu chứa con trỏ, không chứa secret

Ví dụ ba đối tượng độc lập:

| Đối tượng | Ví dụ | Chứa gì? |
| --- | --- | --- |
| Secret trong Key Vault | `payments-api-token` | Giá trị token thực và các phiên bản của nó |
| Key Vault reference trong App Configuration | `/application/payments.api-token` | URI `https://demo-checkout-kv.vault.azure.net/secrets/payments-api-token` |
| Property trong Spring | `payments.api-token` | Giá trị đã được client giải tham chiếu, sử dụng trong runtime |

**App Configuration không tự đi tới Key Vault để lấy secret rồi trả giá trị ấy cho Spring**. Bộ cung cấp cấu hình chạy trong ứng dụng chịu trách nhiệm nhận reference và gọi Key Vault. Hai dịch vụ không trực tiếp trao đổi giá trị trong quy trình này.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant Provider as Spring Cloud Azure App Configuration provider
    participant Config as Azure App Configuration
    participant Vault as Azure Key Vault
    participant Spring as Spring Environment / Bean
    App->>Provider: spring.config.import=azureAppConfiguration
    Provider->>Config: Đọc /application/payments.api-token
    Config-->>Provider: Key Vault reference chứa secret URI
    Provider->>Vault: GET secret bằng credential ứng dụng
    Vault-->>Provider: Secret value nếu được cấp quyền
    Provider->>Spring: Property payments.api-token = giá trị đã resolve
    Note over Spring: Dùng giá trị, không ghi ra log
~~~

Vì vậy, cần phân biệt **hai yêu cầu xác thực**:

- Client cần quyền **đọc key-value** từ App Configuration.
- Client cần quyền **đọc giá trị secret** từ Key Vault.

Đọc được App Configuration nhưng thiếu quyền Key Vault chỉ cho phép thấy **con trỏ**, không lấy được token. Ngược lại, có quyền Key Vault nhưng thiếu quyền App Configuration vẫn không tải được key tham chiếu theo luồng này.

### 2.1. Dữ liệu nào nên tạo reference?

| Dữ liệu | Cách quản lý | Vì sao |
| --- | --- | --- |
| `payments.timeout=PT3S` | Key-value thường trong App Configuration | Tham số vận hành không nhạy cảm |
| `payments.api-token` | Key Vault reference trong App Configuration | Tên logic ở App Configuration, bí mật ở Key Vault |
| Mật khẩu PostgreSQL | Secret ở Key Vault, có thể tham chiếu từ App Configuration | Không lưu plaintext trong cấu hình |
| `feature.NewCheckout` | Feature Manager của App Configuration | Là quyết định bật/tắt tính năng, không phải secret |
| Khóa ký không được xuất | Key Vault Keys và Cryptography API | Key Vault reference kiểu secret không thay thế thao tác ký bằng khóa |

App Configuration mã hóa key-value khi lưu và truyền, nhưng việc mã hóa đó không biến nó thành hệ thống quản lý vòng đời secret. Secret nên được bảo vệ trong Key Vault.

## 3. Cấu trúc reference và việc chọn key/label

Một Key Vault reference nhìn từ Azure App Configuration vẫn là **một key-value có key, label và content type**. Khác biệt là **value có cấu trúc tham chiếu**, không chứa plaintext secret.

| Trường | Ví dụ |
| --- | --- |
| Key | `/application/payments.api-token` |
| Label | *(No Label)* |
| Content type | `application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8` |
| Value về mặt dữ liệu | JSON có thuộc tính `uri` chỉ tới Key Vault secret |
| Giá trị sau khi Spring provider xử lý | Secret value được resolve, gán vào `payments.api-token` |

Biểu diễn cấu trúc reference (để hiểu dữ liệu, **không tự tạo key-value thường theo nội dung này**):

~~~json
{
  "uri": "https://demo-checkout-kv.vault.azure.net/secrets/payments-api-token"
}
~~~

Khi tạo bằng **Configuration Explorer → Create → Key vault reference** hoặc lệnh `az appconfig kv set-keyvault`, Azure thiết lập content type chính xác. Nếu tự tạo một key-value thường chứa nguyên chuỗi URL, Spring sẽ xem đó là **chuỗi cấu hình**, không mặc nhiên giải tham chiếu thành secret.

### 3.1. Tên key của App Configuration khác tên secret của Key Vault

Tên secret trong Key Vault thường dùng chữ, số và dấu `-`, ví dụ `payments-api-token`; nó không cho phép dấu chấm `.` trong tên secret. Trái lại, key của App Configuration có thể dùng dấu `.` để đặt tên Spring property, ví dụ `/application/payments.api-token`.

Vì vậy, mapping trong ví dụ là:

~~~text
Azure Key Vault:              payments-api-token
         ^
         | URI chỉ tới secret
         |
Azure App Configuration:      /application/payments.api-token
         |
         | Spring provider chọn /application/*,
         | bỏ tiền tố /application/, resolve Key Vault
         v
Spring Environment:           payments.api-token
         |
         v
@ConfigurationProperties:      PaymentProperties.apiToken()
~~~

Spring code **không cần biết tên secret `payments-api-token`**: nó chỉ cần biết property logic `payments.api-token`.

### 3.2. Label xác định reference nào được chọn

Một key có thể mang nhiều reference theo label:

| Key | Label | Secret URI trỏ tới |
| --- | --- | --- |
| `/application/payments.api-token` | `dev` | Secret `payments-api-token` trong vault dev |
| `/application/payments.api-token` | `staging` | Secret cùng tên trong vault staging |
| `/application/payments.api-token` | `prod` | Secret cùng tên trong vault prod |

Khi không khai báo label filter riêng, Spring Cloud Azure App Configuration provider dùng **active Spring profiles** để chọn labels; khi không có active profile, chọn các bản ghi **(No Label)**. Có thể cấu hình tường minh `label-filter` để thay đổi hành vi này.

**Label không phải hàng rào bảo mật.** Cùng một identity có quyền đọc App Configuration store có thể xem metadata reference ở các label khác; bí mật vẫn được Key Vault kiểm soát khi truy xuất. Nếu dev/prod phải tách quyền hoặc mạng, nên cân nhắc App Configuration stores và Key Vaults riêng cho từng môi trường.

## 4. Chuẩn bị hai tài nguyên Azure

Tài nguyên ví dụ, cần thay bằng tên thực tế:

| Tài nguyên | Tên ví dụ | Endpoint |
| --- | --- | --- |
| App Configuration store | `demo-checkout-config` | `https://demo-checkout-config.azconfig.io` |
| Key Vault | `demo-checkout-kv` | `https://demo-checkout-kv.vault.azure.net/` |

Cần có Azure subscription, Java 17 trở lên, Maven, Spring Boot và đường mạng cho phép runtime truy cập **cả hai endpoint**. Nếu một dịch vụ chỉ cho truy cập private endpoint, workload phải có DNS/VNet routing phù hợp.

### 4.1. Tạo secret trong Key Vault

Trong Azure portal:

1. Mở **Key Vault → Secrets → Generate/Import**.
2. Tạo secret tên `payments-api-token` bằng giá trị **giả chỉ dùng cho dev/sandbox**.
3. Ghi nhận **Secret Identifier**, ví dụ `https://demo-checkout-kv.vault.azure.net/secrets/payments-api-token`.
4. Kiểm tra secret đang enabled và identity sẽ đọc có quyền được cấp ở mục 5.

Không đặt secret production vào câu lệnh CLI hoặc tài liệu minh họa vì có thể bị ghi vào shell history, pipeline log, audit hoặc issue.

### 4.2. Tạo một Key Vault reference qua portal

Trong Azure portal, mở **App Configuration → Configuration Explorer → Create → Key vault reference**:

- **Key:** `/application/payments.api-token`.
- **Label:** để trống *(No Label)* cho lần chạy đầu tiên.
- **Secret:** chọn Key Vault `demo-checkout-kv` và secret `payments-api-token`, hoặc nhập secret identifier khi giao diện hỗ trợ.
- **Save:** lưu reference.

Cũng tạo một key-value thường trong **Configuration Explorer**:

| Key | Label | Value |
| --- | --- | --- |
| `/application/payments.timeout` | *(No Label)* | `PT3S` |

Sau bước này, trong store có một key thường và một key kiểu reference. Không có plaintext token nào được đặt trong App Configuration.

### 4.3. Tạo reference bằng Azure CLI

Cú pháp được Azure CLI hỗ trợ:

~~~bash
az appconfig kv set-keyvault \
  --name demo-checkout-config \
  --key /application/payments.api-token \
  --secret-identifier "https://demo-checkout-kv.vault.azure.net/secrets/payments-api-token" \
  --auth-mode login
~~~

Khi không truyền `--label`, reference được tạo với **(No Label)**. Để tạo reference label `prod`, bổ sung `--label prod` và sử dụng URI thuộc vault production tương ứng.

Lệnh trên **chỉ ghi URI**, không ghi secret value. Danh tính đang chạy CLI phải có quyền **ghi dữ liệu App Configuration** (ví dụ `App Configuration Data Owner`), trong khi ứng dụng chỉ cần quyền đọc.

Để xác minh **metadata** reference mà không resolve/in giá trị secret:

~~~bash
az appconfig kv show \
  --name demo-checkout-config \
  --key /application/payments.api-token \
  --auth-mode login
~~~

Đầu ra có thể hiển thị URI và content type; **không** chọn chế độ xuất có `--resolve-keyvault` hoặc ghi nội dung secret ra terminal trong bước kiểm thử.

## 5. Phân quyền: quyền trên hai dịch vụ là độc lập

Giả sử Spring Boot chạy trên Azure App Service với **system-assigned Managed Identity** hoặc một workload đã cấu hình user-assigned identity. Với mô hình **Azure RBAC**:

| Ai cần quyền | Resource | Role phù hợp | Mục đích |
| --- | --- | --- | --- |
| **Danh tính runtime của Spring Boot** | App Configuration store | `App Configuration Data Reader` | Đọc key thường và Key Vault reference |
| **Cùng danh tính runtime** | Key Vault | `Key Vault Secrets User` | Lấy giá trị secret được tham chiếu |
| Người/pipeline quản lý reference | App Configuration store | `App Configuration Data Owner` hoặc quyền ghi tương đương | Tạo/sửa reference |
| Người/pipeline quản lý secret | Key Vault | Role có quyền ghi secret riêng, theo chính sách nhóm | Tạo version/rotation, không cấp cho runtime chỉ đọc |

Nếu vault còn dùng **Vault access policy** thay vì Azure RBAC, quyền cần thiết để truy xuất secret là `Get`; các trường hợp liệt kê cần xét thêm `List`. Không gán `Owner` hoặc `Contributor` chỉ để sửa lỗi đọc secret, vì quyền quản lý resource không luôn tương đương **data-plane role**.

Ví dụ logic role assignment theo hai resource:

~~~text
Spring workload identity (principal-id = <runtime-principal>)
    |
    +-- App Configuration store: App Configuration Data Reader
    |
    +-- Key Vault:              Key Vault Secrets User
~~~

**Không cấp role cho identity của App Configuration store với giả định store sẽ đọc secret giúp ứng dụng.** Trong luồng Spring provider, **identity của ứng dụng** mới là principal cần đọc Key Vault.

### 5.1. Chọn credential trong các môi trường

- **Local:** có thể dùng `az login` và chuỗi credential của Azure SDK nếu principal local có quyền trên cả hai tài nguyên.
- **Cloud:** ưu tiên **Managed Identity** của workload; cấp role đúng principal được triển khai.
- **CI/integration test:** dùng identity thử nghiệm riêng, giới hạn scope và dữ liệu.
- **User-assigned identity:** cấu hình rõ client ID theo hướng dẫn Spring Cloud Azure và kiểm tra credential nào được provider thực sự chọn.

Spring Cloud Azure App Configuration provider mặc định có thể sử dụng `DefaultAzureCredential`. Nếu không tùy chỉnh, provider thường dùng cùng cơ chế xác thực cho App Configuration và Key Vault. Khi hai dịch vụ cần credential khác nhau, dòng thư viện hiện đại hỗ trợ tùy biến các client builder qua `ConfigurationClientCustomizer` và `SecretClientCustomizer`; hãy kiểm tra API và thứ tự áp dụng credential của **phiên bản đang dùng**.

**Kết nối App Configuration bằng connection string không cấp quyền đọc Key Vault.** Connection string HMAC chỉ xác thực với App Configuration; Key Vault vẫn đòi identity/token và quyền secret phù hợp.

## 6. Thêm thư viện Spring Cloud Azure

Ví dụ một dự án **Spring Boot 3.5.x**, Java 17, Maven dùng BOM **Spring Cloud Azure 6.x**. Dùng `6.5.0` như phiên bản minh họa; cần đối chiếu ma trận tương thích và artifact thực tế của dự án. Với Spring Boot 4.x, chọn dòng Spring Cloud Azure 7.x tương ứng.

Trong `pom.xml` đã có Spring Boot parent/dependency management:

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
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-appconfiguration-config-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`spring-cloud-azure-appconfiguration-config-web` tải App Configuration và hỗ trợ kiểm tra refresh dựa trên hoạt động Spring Web. Nếu không dùng servlet/web hoặc không cần auto-check refresh qua request, dùng `spring-cloud-azure-appconfiguration-config` là đủ.

**Không bắt buộc thêm `spring-cloud-azure-starter-keyvault-secrets` chỉ để giải Key Vault reference.** App Configuration provider có cơ chế Key Vault reference riêng. Starter Key Vault Secrets cần thiết khi muốn ứng dụng **đồng thời** tải secret trực tiếp thành Key Vault PropertySource theo tên secret.

## 7. Khai báo Spring Config Data import

Tạo `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: checkout-service
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
~~~

Đặt **endpoint** App Configuration vào biến môi trường:

~~~text
AZURE_APPCONFIG_ENDPOINT=https://demo-checkout-config.azconfig.io
~~~

PowerShell trên Windows:

~~~powershell
$Env:AZURE_APPCONFIG_ENDPOINT = "https://demo-checkout-config.azconfig.io"
~~~

Shell Linux/macOS:

~~~bash
export AZURE_APPCONFIG_ENDPOINT="https://demo-checkout-config.azconfig.io"
~~~

Ý nghĩa:

- `spring.config.import=azureAppConfiguration` đăng ký App Configuration provider vào **Spring Config Data API** ngay ở giai đoạn bootstrap cấu hình.
- `stores[0].endpoint` chỉ định nơi tải key-value và reference; endpoint này **không phải** endpoint Key Vault.
- Mặc định, provider lấy key có tiền tố `/application/` và label **(No Label)** khi không có active profile.
- Với key `/application/payments.api-token`, provider loại bỏ prefix theo quy tắc mặc định và cung cấp Spring property `payments.api-token`.
- Khi provider gặp loại **Key Vault reference**, nó gọi Key Vault để giải URI bằng credential phù hợp.

Đường URI của Key Vault **nằm trong reference ở App Configuration**, vì vậy ví dụ không cần khai báo `AZURE_KEYVAULT_ENDPOINT` chỉ để resolve reference. Nếu dùng Key Vault PropertySource trực tiếp, đó là cấu hình riêng.

### 7.1. Nếu một profile đang hoạt động

Trong lần thử đầu, hãy chạy **không kích hoạt Spring profile**, vì hai bản ghi ở mục 4 dùng (No Label). Nếu chạy profile `dev`, provider mặc định có thể chỉ chọn label `dev`, không tự lấy No Label.

Muốn dùng lớp cấu hình chung (No Label) rồi override bằng label môi trường, với điều kiện luôn đặt đúng một active profile:

~~~yaml
spring:
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            selects:
              - key-filter: "/application/*"
                label-filter: ',${spring.profiles.active}'
~~~

Label phía **sau** được ưu tiên khi trùng key. Nếu `prod` có reference của cùng `/application/payments.api-token`, URI production sẽ thắng URI No Label trong lớp dữ liệu Azure. Đừng dùng biến thể này khi profile có thể vắng mặt mà không thiết kế giá trị mặc định cho placeholder.

## 8. Đọc reference bằng `@ConfigurationProperties` và `@Value`

Mục tiêu là mã Java nhận **property logic**, không gọi API Azure và không ghi secret ra log.

### 8.1. Bind vào record có bảo vệ `toString`

Tạo `src/main/java/com/example/checkout/CheckoutApplication.java`:

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

Tạo `src/main/java/com/example/checkout/PaymentProperties.java`:

~~~java
package com.example.checkout;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "payments")
public record PaymentProperties(String apiToken, Duration timeout) {
    public PaymentProperties {
        if (apiToken == null || apiToken.isBlank()) {
            throw new IllegalArgumentException(
                    "Required property payments.api-token is missing");
        }
    }

    @Override
    public String toString() {
        // Record mặc định sẽ in tất cả các field, kể cả secret.
        return "PaymentProperties[apiToken=REDACTED, timeout=" + timeout + "]";
    }
}
~~~

Kết quả mapping:

| Key Azure | Nguồn dữ liệu | Property Spring | Field Java |
| --- | --- | --- | --- |
| `/application/payments.api-token` | Key Vault reference đã resolve | `payments.api-token` | `apiToken` |
| `/application/payments.timeout` | Key-value thường `PT3S` | `payments.timeout` | `timeout` |

Spring Binder chuyển `payments.api-token` thành `apiToken` qua relaxed binding và `PT3S` thành `Duration.ofSeconds(3)`.

### 8.2. Service sử dụng cấu hình

~~~java
package com.example.checkout;

import org.springframework.stereotype.Service;

@Service
public class PaymentClientSettings {
    private final PaymentProperties properties;

    public PaymentClientSettings(PaymentProperties properties) {
        this.properties = properties;
    }

    public boolean hasCredential() {
        // Chỉ tiết lộ trạng thái, không trả token.
        return !properties.apiToken().isBlank();
    }

    public long timeoutMillis() {
        return properties.timeout().toMillis();
    }
}
~~~

Trong ứng dụng thật, token được truyền cho HTTP client/gateway tương ứng qua API xác thực bảo mật. Không tạo endpoint trả `properties.apiToken()`, không log cả `PaymentProperties` mặc dù đã redacted `toString()`; các bản sao khác của đối tượng vẫn có thể làm lộ dữ liệu.

### 8.3. Đọc một property bằng `@Value`

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GatewayCredentialHolder {
    private final String apiToken;

    public GatewayCredentialHolder(
            @Value("${payments.api-token}") String apiToken) {
        this.apiToken = apiToken;
    }

    public boolean configured() {
        return apiToken != null && !apiToken.isBlank();
    }
}
~~~

`@Value` thích hợp với một property, nhưng `@ConfigurationProperties` thuận tiện hơn khi có nhiều tham số liên quan. Cả hai đều lấy giá trị từ **Spring Environment** sau khi reference đã resolve; không phải thêm code giải mã URI trong lớp nghiệp vụ.

## 9. Sự khác biệt giữa reference và Key Vault Secrets PropertySource

Đây là hai cách nạp secret **độc lập**, có thể cùng xuất hiện trong một Spring Boot application:

| Tiêu chí | App Configuration Key Vault reference | Key Vault Secrets PropertySource |
| --- | --- | --- |
| Nguồn định nghĩa tên Spring property | **Key của App Configuration** như `/application/payments.api-token` | **Tên secret trong vault** và ánh xạ/alias |
| Nơi cấu hình endpoint | `spring.cloud.azure.appconfiguration.stores[]` | `spring.cloud.azure.keyvault.secret.property-sources[]` |
| Các quyền cần có | Đọc App Configuration **và** Key Vault | Đọc Key Vault |
| Cơ chế refresh | Theo App Configuration provider, monitor/reference và bean | Theo refresh interval của KeyVaultPropertySource và bean |
| Dễ đổi vault theo môi trường qua label | Có, bằng reference cùng key khác label | Phải đổi endpoint/configuration theo môi trường |
| Phù hợp khi | Muốn quản lý con trỏ secret cùng các key cấu hình ứng dụng | Ứng dụng chỉ cần đọc secret từ vault trực tiếp |

Nếu chọn **reference**, không cần tạo thêm key `payments-api-token` trong Key Vault PropertySource để App Configuration có thể resolve. Ngược lại, nếu đã dùng PropertySource trực tiếp, bạn có thể dùng placeholder trong Spring để alias tên secret mà không cần App Configuration reference.

**Đừng nhầm** App Configuration Key Vault reference với cú pháp `@Microsoft.KeyVault(...)` trong **Azure App Service application settings**. App Service có cơ chế giải tham chiếu và cache riêng, không đồng nghĩa với lifecycle/refresh của Spring Cloud Azure provider.

## 10. Phiên bản secret: URI không version và URI ghim version

Một secret Key Vault có thể có nhiều **version**. Reference cho phép đưa URI **không có version** hoặc URI có một version xác định.

~~~text
Không ghim version:
https://demo-checkout-kv.vault.azure.net/secrets/payments-api-token

Ghim một version:
https://demo-checkout-kv.vault.azure.net/secrets/payments-api-token/<version-id>
~~~

| Kiểu URI | Đặc điểm | Khi thích hợp |
| --- | --- | --- |
| **Không version** | Khi được truy xuất lại, có thể nhận phiên bản hiện hành của secret theo Key Vault | Muốn rotation mà không phải cập nhật reference mỗi lần |
| **Có version** | Trỏ cố định tới một phiên bản cụ thể; secret mới không tự đổi URI | Phát hành cần chốt secret version và kiểm soát cutover |
| **Reference khác giữa dev/prod** | Cùng tên Spring key nhưng trỏ vault khác theo label/store | Phân tách môi trường và quyền |

**Điểm cần nhớ:** tạo secret version mới trong Key Vault **không bảo đảm bean Spring đang chạy tự dùng giá trị mới**. Kể cả reference không ghim version, ứng dụng có thể đang giữ giá trị cũ trong provider cache, Spring property hoặc một HTTP client đã tạo từ trước.

### 10.1. Rotation theo phiên bản không ghim

Một quy trình chủ động:

1. Phát hành credential mới ở nhà cung cấp thanh toán; nếu có thể, giữ đồng thời credential cũ và mới trong giai đoạn chuyển.
2. Tạo version mới của `payments-api-token` trong Key Vault bằng quy trình được bảo vệ.
3. Kích hoạt cơ chế nạp lại secret hoặc **restart có kiểm soát** để client resolve URI không version lần nữa; xác minh từng instance đã sử dụng credential mới.
4. Kiểm tra giao dịch sandbox, lỗi xác thực và thời gian phục vụ.
5. Thu hồi credential cũ sau khi biết chắc không còn instance phụ thuộc.

Nếu muốn thay reference sang **một version cụ thể**, hãy cập nhật URI trong App Configuration, sau đó nạp lại cấu hình/restart, kiểm tra kết quả rồi mới thu hồi phiên bản cũ.

### 10.2. Tại sao App Configuration monitoring chưa đủ?

App Configuration monitoring chủ yếu phát hiện **thay đổi ở các key-value mà nó theo dõi trong App Configuration**. Nếu **chỉ secret value trong Key Vault đổi** còn URI/reference trong App Configuration **không thay**, không nên mặc định monitoring sẽ luôn phát hiện và cập nhật mọi ứng dụng.

Có thể lập quy trình rotation bằng một thay đổi reference/sentinel tại App Configuration kết hợp refresh, hoặc restart ứng dụng được điều phối. Tuy nhiên, ngay cả khi provider đã tải giá trị mới, những bean/HTTP client giữ token trong field vẫn cần tái tạo hoặc thay credential theo lifecycle của ứng dụng.

Lưu ý: một số hướng dẫn của **.NET App Configuration provider** có API chuyên biệt như `SetSecretRefreshInterval`. Không suy rằng Spring provider có đúng cùng API hoặc cam kết cache như App Service/.NET; kiểm tra khả năng refresh của **thư viện Java đang sử dụng**.

## 11. Refresh trong Spring Cloud Azure

Khi ứng dụng cần cập nhật cấu hình trong runtime, có thể bật monitoring của App Configuration provider. Ví dụ với bản `-web`:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].monitoring.enabled=true
spring.cloud.azure.appconfiguration.stores[0].monitoring.triggers[0].key=/application/config.refresh-sentinel
~~~

Tạo `/application/config.refresh-sentinel` trong store, label tương ứng, với giá trị ban đầu `1`. Để xuất bản một thay đổi cấu hình, cập nhật các key và reference cần thiết trước, cuối cùng đổi sentinel.

- Theo tài liệu Spring Cloud Azure, khoảng kiểm tra tối thiểu mặc định thường là **30 giây**.
- Với `spring-cloud-azure-appconfiguration-config-web`, việc kiểm tra có thể được kích hoạt bởi hoạt động **servlet request** sau khi đủ khoảng thời gian.
- Với provider không dùng web, có thể chủ động gọi API refresh thích hợp của thư viện.
- Refresh hoạt động theo cơ chế của Spring/`@RefreshScope` và quá trình bind; các object tự cache token hoặc session vẫn phải được xử lý riêng.

**Không thể lấy 30 giây làm SLA cập nhật secret.** Khoảng đó chỉ liên quan đến lịch kiểm tra cấu hình. Độ trễ thực phụ thuộc trigger, mạng, cache Key Vault reference, số instance và vòng đời bean.

## 12. Kiểm thử và chẩn đoán lỗi

### 12.1. Kiểm thử binding không cần gọi Azure

Một unit test cho logic bind `PaymentProperties` không cần có vault thật. Có thể dùng `MockEnvironment` và `Binder`:

~~~java
package com.example.checkout;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.mock.env.MockEnvironment;

class PaymentPropertiesBindingTest {
    @Test
    void bindsPropertiesWithoutAzure() {
        var env = new MockEnvironment()
                .withProperty("payments.api-token", "dummy-for-test")
                .withProperty("payments.timeout", "PT3S");

        PaymentProperties props = Binder.get(env)
                .bind("payments", Bindable.of(PaymentProperties.class))
                .orElseThrow();

        assertThat(props.apiToken()).isEqualTo("dummy-for-test");
        assertThat(props.timeout()).isEqualTo(Duration.ofSeconds(3));
        assertThat(props.toString()).doesNotContain("dummy-for-test");
    }
}
~~~

Test này xác minh **Spring Binder**, **kiểu dữ liệu** và việc redacted `toString()`. Nó không chứng minh provider đã giải tham chiếu URI, role Azure chính xác hay refresh hoạt động.

Nếu dùng `@SpringBootTest` cho ngữ cảnh Spring đầy đủ, có thể tắt provider bằng `spring.cloud.azure.appconfiguration.enabled=false` và cung cấp property giả; phải kiểm tra việc disable đã có hiệu lực trước giai đoạn import trong phiên bản dự án.

### 12.2. Integration test với tài nguyên dev

Dùng riêng một App Configuration store, Key Vault và identity dành cho dev/sandbox:

1. Tạo secret giả `payments-api-token` và reference `/application/payments.api-token` với **No Label**.
2. Cấp App Configuration Data Reader và Key Vault Secrets User cho identity thực hiện test.
3. Khởi động Spring Boot, xác minh `payments.api-token` tồn tại và một client sandbox có thể xác thực (không in giá trị).
4. Đổi label `dev` và cấu hình selector; xác minh ứng dụng lấy đúng URI/reference.
5. Với một identity test thiếu quyền Key Vault, xác minh reference có thể đọc nhưng bước resolve secret thất bại theo dự kiến.
6. Tạo version mới và thử trường hợp URI không có version so với URI ghim version; quan sát sau restart/refresh.
7. Thử thay reference sang một vault khác khi chưa cấp quyền, xác nhận lỗi được phát hiện sớm.
8. Kiểm tra các log và trace không chứa secret hoặc token.

**Không dùng vault production cho kiểm thử mất quyền hoặc rotation.** Những test này có thể thay đổi trạng thái credential và làm dịch vụ thật ngừng hoạt động.

### 12.3. Bảng xử lý sự cố

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Spring không nhận `azureAppConfiguration` | Thiếu dependency App Configuration, sai cú pháp import hoặc BOM không phù hợp | Kiểm tra `pom.xml` và `spring.config.import` |
| `payments.api-token` không tồn tại | Key/reference không khớp `/application/*`, sai label/profile hoặc sai store | Kiểm tra tên key, `key-filter`, `label-filter` và endpoint |
| Spring chỉ nhận URI thay vì secret | Key được tạo là key-value thường, thiếu content type Key Vault reference | Tạo lại bằng **Key vault reference** hoặc `set-keyvault` |
| App Configuration trả 403 | Identity thiếu `App Configuration Data Reader` hoặc role chưa đồng bộ | Xác minh đúng principal và scope App Configuration |
| Đọc được reference nhưng Key Vault trả 403 | Identity thiếu `Key Vault Secrets User` hoặc access policy `Get` | Cấp quyền trên đúng vault, kiểm tra principal runtime |
| Secret trả 404 | Tên, URI/version sai, secret chưa tồn tại/disabled | Kiểm tra metadata URI và trạng thái secret |
| Local chạy, Azure App Service lỗi | Azure workload dùng identity khác developer local | Xác minh Managed Identity, role và mạng trên môi trường cloud |
| Sau rotation vẫn nhận giá trị cũ | URI ghim version, provider cache, không refresh hoặc bean/client giữ token cũ | Kiểm tra version, thực hiện nạp lại/restart và tái tạo client |
| DNS/timeout/429 | Private endpoint, firewall, DNS, quota hoặc retry không phù hợp | Kiểm tra kết nối tới **cả hai endpoint**, dùng backoff và giám sát |
| Test khởi động vô tình truy cập Azure | Chưa vô hiệu hóa provider hoặc thiếu stub | Dùng local binding test, tắt provider trong Spring test không cần Azure |

### 12.4. Quan sát cấu hình mà không làm lộ secret

Thay vì in `environment.getProperty("payments.api-token")`, có thể kiểm tra **key có tồn tại không** và **tên PropertySource** trong môi trường dev:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

@Configuration
class ConfigSourceDiagnostic {
    @Bean
    ApplicationRunner reportSources(ConfigurableEnvironment env) {
        return args -> {
            String key = "payments.api-token";
            System.out.println("Property configured: " + env.containsProperty(key));
            for (PropertySource<?> source : env.getPropertySources()) {
                if (source.containsProperty(key)) {
                    System.out.println("Source: " + source.getName());
                }
            }
        };
    }
}
~~~

Chỉ sử dụng tạm trong môi trường kiểm thử. Không công khai `/actuator/env` hoặc `/actuator/configprops` để debug secret. Những endpoint đó có thể tiết lộ tên property, nguồn hoặc giá trị tùy cấu hình và phiên bản.

## 13. Mẫu thiết kế an toàn cho môi trường production

Một phương án thực tế:

| Thành phần | dev | prod |
| --- | --- | --- |
| App Configuration store | `checkout-config-dev` | `checkout-config-prod` |
| Key Vault | `checkout-kv-dev` | `checkout-kv-prod` |
| Spring property | `payments.api-token` | `payments.api-token` |
| Reference | URI vào vault dev | URI vào vault prod |
| Identity | Managed Identity dev | Managed Identity prod |
| Role trên mỗi store | Data Reader trong dev | Data Reader trong prod |
| Role trên mỗi vault | Secrets User trong dev | Secrets User trong prod |

Lợi ích: **mã Java không đổi**, chỉ endpoint App Configuration và identity runtime khác nhau. Prod không phải tin cậy một label trong store dùng chung để ngăn workload dev đọc nhầm URI production.

Một số nguyên tắc cần áp dụng:

- Chỉ cấp **quyền đọc** cho ứng dụng; quyền tạo/sửa secret và reference thuộc pipeline/operator có kiểm soát.
- Sử dụng Managed Identity hoặc workload identity federation thay cho client secret dài hạn khi có thể.
- Hạn chế role và network trên **cả** App Configuration và Key Vault; kiểm tra các private endpoints riêng.
- Không log giá trị trong `Environment`, Bean, exception, trace tag hay telemetry.
- Khi cần hỗ trợ rotation, chọn URI có/không version dựa trên yêu cầu và thiết kế lại client lifecycle cho phù hợp.
- Theo dõi lỗi xác thực/403, 404 secret, timeout, quá hạn secret và độ trễ refresh; tuyệt đối không đưa secret vào metric label.
- Nếu cùng một key tham chiếu tới secret bị mất quyền, thiết kế ứng dụng **fail an toàn** thay vì tự chuyển sang token hard-coded.

## 14. Bài tập thực hành

Ứng dụng `shipping-service` cần:

- `shipping.timeout=PT4S` (không nhạy cảm).
- Secret `shipping-partner-token` trong `shipping-kv-dev`.
- Property Spring `shipping.partner-token` lấy từ Key Vault reference.
- Một identity chỉ có quyền **đọc** App Configuration và **đọc** secret Key Vault.
- Có kế hoạch thay token mà không thay mã Java.

### 14.1. Thiết kế cấu hình

Trong App Configuration store `shipping-config-dev`:

| Key | Label | Kiểu | Giá trị |
| --- | --- | --- | --- |
| `/application/shipping.timeout` | *(No Label)* | Key-value thường | `PT4S` |
| `/application/shipping.partner-token` | *(No Label)* | Key Vault reference | URI tới `shipping-kv-dev/secrets/shipping-partner-token` |

Spring config:

~~~yaml
spring:
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
~~~

Java binding:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(Duration timeout, String partnerToken) {
    @Override
    public String toString() {
        return "ShippingProperties[timeout=" + timeout + ", partnerToken=REDACTED]";
    }
}
~~~

Bật `@ConfigurationPropertiesScan` và inject `ShippingProperties` vào client sử dụng token. Tránh in cả token hoặc object chứa token.

### 14.2. Câu hỏi tự kiểm tra

1. Khi reference trỏ URI đến Key Vault, App Configuration có cần được cấp `Key Vault Secrets User` để trả secret cho Spring hay không?
2. Vì sao một identity có `App Configuration Data Reader` vẫn có thể gặp lỗi 403 khi nạp reference?
3. Một key App Configuration chứa **chuỗi URI thường** có tự động được xử lý như Key Vault reference không?
4. Khi đổi secret version mới nhưng giữ URI không version, liệu mọi HTTP client Spring đang chạy sẽ tự thay token ngay không?
5. Trong mô hình nhiều môi trường, tại sao tách vault và identity thường rõ ràng hơn chỉ dùng labels?
6. Khi nào nên dùng `spring-cloud-azure-starter-keyvault-secrets` thay vì App Configuration Key Vault reference?

**Đáp án định hướng:** (1) không, ứng dụng mới đọc Key Vault; (2) thiếu quyền Key Vault hoặc lỗi URI/mạng; (3) không, phải có kiểu reference phù hợp; (4) không, cần resolve lại và cập nhật client; (5) labels là bộ lọc cấu hình, không phải biên phân quyền; (6) khi chỉ cần đọc secret trực tiếp bằng tên/PropertySource và không cần con trỏ trong App Configuration.

## 15. Nguồn tham khảo chính thức

- [Microsoft Learn – Use Key Vault references in a Java Spring app](https://learn.microsoft.com/en-us/azure/azure-app-configuration/use-key-vault-references-spring-boot): quy trình tạo secret/reference, cấp quyền và đọc qua Spring.
- [Microsoft Learn – Spring Boot App Configuration quickstart](https://learn.microsoft.com/en-us/azure/azure-app-configuration/quickstart-java-spring-app): Config Data import và dependency.
- [Microsoft Learn – Azure App Configuration CLI: `set-keyvault`](https://learn.microsoft.com/en-us/cli/azure/appconfig/kv): tạo reference đúng content type và cách dùng URI có/không version.
- [Microsoft Learn – App Configuration key-value store](https://learn.microsoft.com/en-us/azure/azure-app-configuration/concept-key-value): key, label và content type.
- [Azure SDK for Java – Spring Cloud Azure App Configuration README](https://github.com/Azure/azure-sdk-for-java/blob/main/sdk/spring/spring-cloud-azure-starter-appconfiguration-config/README.md): selectors, credential, customizer và monitoring.
- [Microsoft Learn – Spring Cloud Azure configuration reference](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configuration): cách định nghĩa và ưu tiên credential.
- [Microsoft Learn – Dynamic configuration in Spring](https://learn.microsoft.com/en-us/azure/azure-app-configuration/enable-dynamic-configuration-java-spring-app): refresh theo trigger/request.
- [Microsoft Learn – Key Vault RBAC guide](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide): phân quyền secret.
- [Azure SDK for Java – Spring Versions Mapping](https://github.com/Azure/azure-sdk-for-java/wiki/Spring-Versions-Mapping): chọn dòng Spring Cloud Azure tương thích.

**Ghi nhớ:** App Configuration giữ **tên cấu hình và URI tham chiếu**, Key Vault giữ **giá trị bí mật**, còn **Spring Cloud Azure provider chạy trong ứng dụng** kết nối cả hai và đưa giá trị vào `Environment`. Để triển khai an toàn phải kiểm soát đúng danh tính, hai role đọc dữ liệu, cách chọn key/label, version URI, refresh và vòng đời của client đang sử dụng secret.
