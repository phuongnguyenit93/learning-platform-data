# Quyền truy cập, hành vi khi nguồn từ xa lỗi và kiểm thử cấu hình

Một ứng dụng Spring Boot có thể chạy đúng trên máy lập trình nhưng thất bại ngay khi triển khai lên Azure vì **danh tính runtime không có quyền đọc dữ liệu**, endpoint bị chặn hoặc cấu hình bắt buộc không tải được. Cũng có trường hợp ứng dụng khởi động thành công với cấu hình mặc định nhưng dùng nhầm giá trị cũ, thiếu secret hoặc không phát hiện lỗi từ nguồn từ xa.

Khi tích hợp **Azure App Configuration** và **Azure Key Vault**, cần thiết kế đồng thời ba phần: **ai được phép đọc**, **ứng dụng phản ứng thế nào khi nguồn từ xa không hoạt động**, và **kiểm thử ra sao để phát hiện lỗi trước production**. Spring Cloud Azure tạo các Spring `PropertySource` từ dịch vụ Azure; do đó, lỗi truy cập có thể xảy ra ngay trong giai đoạn nạp cấu hình, trước khi controller hoặc service được tạo.

Bài thuộc chương **Cấu hình Azure** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud, bao gồm danh tính/quyền, storage, messaging, dữ liệu, secret, kiểm thử tích hợp và so sánh cloud provider. Mục tiêu là biết cấp đúng quyền, chọn chiến lược fail-safe/fail-closed phù hợp với từng loại cấu hình và xây dựng bộ kiểm thử có thể xác minh hành vi khi Azure gặp sự cố.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Phân biệt **authentication** (xác thực danh tính) và **authorization** (cấp quyền truy cập dữ liệu).
2. Cấp đúng Azure RBAC role cho App Configuration và Key Vault; phân biệt quyền quản lý resource với quyền đọc data-plane.
3. Chọn Managed Identity/DefaultAzureCredential cho local, CI và môi trường Azure.
4. Giải thích hành vi startup khi App Configuration import hoặc Key Vault PropertySource không truy cập được.
5. Phân biệt cấu hình bắt buộc, cấu hình có thể dùng default an toàn và secret không được phép fallback tùy tiện.
6. Hiểu thay đổi của thuộc tính `fail-fast` giữa các dòng Spring Cloud Azure và lựa chọn cơ chế high availability hiện hành.
7. Kiểm thử binding, context startup, RBAC, lỗi nguồn từ xa, refresh và cấu hình theo môi trường.

Tình huống xuyên suốt: `checkout-service` đọc `payments.timeout` từ App Configuration, lấy `payments.api-token` qua Key Vault reference và sử dụng Managed Identity để truy cập cả hai dịch vụ. Timeout có default vận hành an toàn; token thanh toán là **bắt buộc**.

~~~mermaid
flowchart TD
    A["Spring Boot khởi động"] --> B["Xác thực danh tính bằng Microsoft Entra ID"]
    B --> C["Đọc App Configuration"]
    C --> D["Đọc Key Vault nếu có reference"]
    D --> E["Bind và validate Spring properties"]
    E --> F{"Cấu hình bắt buộc hợp lệ?"}
    F -->|Có| G["ApplicationContext sẵn sàng"]
    F -->|Không| H["Startup thất bại / instance chưa Ready"]
    C -->|Lỗi kết nối / quyền| H
    D -->|Lỗi kết nối / quyền| H
~~~

**Nguyên tắc:** ứng dụng chỉ được xem là sẵn sàng khi đã có đủ cấu hình bắt buộc để thực hiện nghiệp vụ an toàn. Không dùng một giá trị giả hoặc secret hard-code để che lỗi quyền truy cập.

## 2. Authentication và authorization là hai bước khác nhau

Với Microsoft Entra ID, quá trình truy cập dịch vụ gồm:

1. **Authentication:** ứng dụng chứng minh danh tính và nhận OAuth 2.0 access token.
2. **Authorization:** dịch vụ Azure kiểm tra token/principal đó có quyền thực hiện thao tác trên resource hoặc dữ liệu hay không.

Vì vậy, `az login` thành công hoặc Managed Identity lấy được token **không chứng minh** ứng dụng có quyền đọc App Configuration hay Key Vault.

| Thành phần | Câu hỏi cần trả lời | Ví dụ lỗi |
| --- | --- | --- |
| Authentication | Ứng dụng là ai? Token có lấy được không? | Sai tenant, credential không tồn tại, identity chưa bật |
| Authorization | Principal có quyền đọc dữ liệu không? | 403 Forbidden, thiếu data-plane role |
| Network | Ứng dụng có tới được endpoint không? | DNS failure, timeout, TLS, firewall |
| Configuration selection | Có chọn đúng key/label/secret không? | Ứng dụng không thấy property dù gọi Azure thành công |

### 2.1. DefaultAzureCredential và Managed Identity

Spring Cloud Azure hỗ trợ các credential như `DefaultAzureCredential`, `ManagedIdentityCredential`, `WorkloadIdentityCredential`, `ClientSecretCredential` và `AzureCliCredential`.

Một cấu hình endpoint tối thiểu:

~~~yaml
spring:
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
~~~

Khi không khai báo credential riêng, client dùng cơ chế credential mặc định của Spring Cloud Azure/Azure Identity. `DefaultAzureCredential` có thể sử dụng credential từ môi trường triển khai hoặc môi trường phát triển, ví dụ Managed Identity, Workload Identity, Azure CLI hoặc IDE tùy cấu hình và thứ tự credential của phiên bản SDK.

**Local development:** có thể đăng nhập bằng `az login`, nhưng phải cấp quyền cho đúng user/service principal được credential chain lựa chọn.

**Azure runtime:** ưu tiên Managed Identity để tránh lưu client secret dài hạn. Với system-assigned identity, identity gắn với vòng đời resource. Với user-assigned identity, cấu hình client ID khi cần chọn identity cụ thể:

~~~yaml
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
        client-id: "${AZURE_CLIENT_ID}"
~~~

`AZURE_CLIENT_ID` là client ID của user-assigned identity, không phải secret. Không cần cấu hình client ID khi dùng system-assigned identity duy nhất và credential được chọn đúng.

### 2.2. Cấp quyền riêng cho từng dịch vụ

Nếu ứng dụng tải key-value từ App Configuration và giải Key Vault reference, danh tính runtime cần quyền đọc trên **cả hai resource**:

| Resource | Azure RBAC role phù hợp | Mục đích |
| --- | --- | --- |
| Azure App Configuration store | **App Configuration Data Reader** | Đọc key-value, label, feature flag và Key Vault reference |
| Azure Key Vault | **Key Vault Secrets User** | Đọc secret value mà reference trỏ tới |

Không cấp `App Configuration Data Owner` hoặc `Key Vault Administrator` cho một ứng dụng chỉ cần đọc. Các role quản lý resource như `Contributor` không mặc nhiên cấp quyền đọc dữ liệu data-plane.

Nếu Key Vault vẫn dùng **Vault access policy** (mô hình cũ), cấp `Get` cho secret; nếu provider cần liệt kê secret, xem xét thêm `List`. Với RBAC, ưu tiên role chuyên dụng ở scope vault cần thiết.

**Lưu ý:** quyền đọc reference và quyền đọc secret là hai quyền độc lập. Khi App Configuration trả về URI nhưng Key Vault trả 403, cần kiểm tra role ở vault chứ không phải thay key filter.

### 2.3. Ví dụ gán role bằng Azure CLI

Ví dụ cấp App Configuration Data Reader cho một principal:

~~~bash
az role assignment create \
  --role "App Configuration Data Reader" \
  --assignee "<principal-object-or-client-id>" \
  --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.AppConfiguration/configurationStores/<store-name>"
~~~

Cấp Key Vault Secrets User:

~~~bash
az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee "<principal-object-or-client-id>" \
  --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.KeyVault/vaults/<vault-name>"
~~~

Thay placeholder bằng ID thực tế. Cần phân biệt **object ID của principal** với client ID khi dùng lệnh gán role; kiểm tra tham số phù hợp với loại principal và phiên bản Azure CLI. Role assignment có thể mất thời gian để truyền tới data-plane. Nếu vừa cấp role, chờ đồng bộ rồi kiểm tra lại token/principal.

### 2.4. Tách quyền runtime và quyền quản trị

Một mô hình có thể dùng:

| Principal | Quyền | Việc được phép |
| --- | --- | --- |
| Spring runtime identity | App Configuration Data Reader | Đọc cấu hình |
| Spring runtime identity | Key Vault Secrets User | Đọc secret |
| Release pipeline/operator | App Configuration Data Owner hoặc quyền ghi giới hạn | Tạo/sửa key-value và reference |
| Secret administrator/rotation workflow | Role có quyền ghi secret phù hợp | Tạo version, cập nhật hoặc thu hồi secret |

Không dùng chung một principal có quyền Owner cho runtime chỉ vì dễ triển khai. Khi workload bị xâm nhập, quyền đọc bị giới hạn sẽ giảm phạm vi tác động.

## 3. Quyền truy cập không thay thế yêu cầu mạng

Một identity có đúng RBAC role vẫn có thể không truy cập được nếu endpoint bị chặn.

Các điểm cần kiểm tra:

- DNS có phân giải endpoint App Configuration và Key Vault đúng không?
- Private endpoint có nằm trong VNet mà workload truy cập được không?
- Private DNS zone có được liên kết đúng với VNet?
- Firewall có cho phép subnet hoặc đường outbound của ứng dụng không?
- Proxy, TLS certificate, route và network security group có cản kết nối không?
- Ứng dụng đang dùng đúng endpoint của cloud environment, không nhầm public Azure với sovereign cloud?

Nếu dùng private endpoint, phải kiểm tra **từng dịch vụ**. App Configuration và Key Vault có endpoint, DNS và firewall riêng. Một dịch vụ truy cập được không có nghĩa dịch vụ còn lại cũng truy cập được.

## 4. Hành vi khi App Configuration không truy cập được lúc khởi động

Khi khai báo:

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

Spring Boot xử lý App Configuration trong giai đoạn **Config Data loading**. Nếu nguồn từ xa bắt buộc không tải được, lỗi có thể xảy ra trước khi Spring tạo xong ApplicationContext.

Các tình huống phổ biến:

| Lỗi | Hành vi cần dự kiến |
| --- | --- |
| Endpoint sai, DNS hoặc network timeout | Không tải được config; import bắt buộc có thể làm startup thất bại |
| Credential không lấy được token | Startup thất bại nếu không có nguồn credential thay thế hợp lệ |
| Identity không có App Configuration Data Reader | Azure trả 403; không được xem là lỗi cấu hình có thể fallback an toàn |
| Key/label không tồn tại | Có thể không có property tương ứng; validation của ứng dụng quyết định startup có hợp lệ không |
| Azure trả 429/5xx | Có thể retry hoặc failover nếu cấu hình và tài nguyên hỗ trợ |
| App Configuration primary unavailable nhưng replica còn hoạt động | Client có thể failover sang replica được cấu hình/khám phá |

### 4.1. Cấu hình bắt buộc và import optional

Với cấu hình bắt buộc, dùng import không có prefix optional:

~~~properties
spring.config.import=azureAppConfiguration
~~~

Nếu store không tải được, ứng dụng nên thất bại khởi động. Đây là lựa chọn phù hợp khi remote config chứa endpoint, policy hoặc tham số cần thiết để phục vụ nghiệp vụ đúng.

Spring Boot hỗ trợ prefix `optional:` cho một Config Data location có thể không tồn tại:

~~~properties
spring.config.import=optional:azureAppConfiguration
~~~

Tuy nhiên, `optional:` chỉ là cơ chế optional của Spring Config Data đối với lỗi location không tồn tại được resolver báo về. **Không xem nó là cơ chế tổng quát để bắt mọi lỗi 401/403, timeout, TLS, DNS hoặc 429 của dịch vụ Azure.** Hành vi cụ thể phụ thuộc cách provider phiên bản đang dùng chuyển đổi lỗi; phải có integration test trước khi dựa vào optional import trong production.

Nếu nguồn từ xa có thể vắng mặt và ứng dụng có default cục bộ an toàn, có thể thiết kế theo hướng optional. Nhưng nếu một giá trị bắt buộc không có cả ở local lẫn remote, hãy dùng validation để ngăn ứng dụng khởi động với cấu hình thiếu.

### 4.2. Không dùng thuộc tính fail-fast cũ cho Spring Cloud Azure 6.x/7.x

Các tài liệu Spring Cloud Azure đời cũ (5.x và trước đó) có thuộc tính `spring.cloud.azure.appconfiguration.stores[0].fail-fast`. Trong dòng 6.0.0, thuộc tính này đã **bị loại bỏ** cùng thay đổi chuyển sang Config Data import chuẩn. Vì vậy, không sao chép cấu hình:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].fail-fast=false
~~~

vào ứng dụng dùng Spring Cloud Azure 6.x/7.x và kỳ vọng nó bỏ qua lỗi remote source. Hãy kiểm tra tài liệu đúng phiên bản BOM. Nếu cần tính sẵn sàng cao, ưu tiên **replicas/geo-replication** thay vì giả định một store lỗi có thể bị bỏ qua an toàn.

### 4.3. Phân biệt optional config với default nghiệp vụ

Giả sử file local có:

~~~yaml
payments:
  timeout: PT3S
  max-retries: 2
~~~

Remote App Configuration có thể override các giá trị trên khi được tải thành công. Nhưng việc tồn tại local default **không tự động bảo đảm** ứng dụng sẽ khởi động với local default nếu quá trình import bắt buộc thất bại trước khi context được tạo.

Nếu timeout là tham số không nhạy cảm và có default đã được kiểm thử, có thể thiết kế nguồn remote là optional theo hành vi provider/Spring Boot đã xác minh. Nếu secret thanh toán bị thiếu, không dùng một chuỗi mặc định để giả lập secret production.

## 5. High availability cho App Configuration: replicas và failover

Spring Cloud Azure 6.0 loại bỏ fail-fast property và release notes khuyến nghị dùng **replicas** để tăng tính sẵn sàng. Azure App Configuration hỗ trợ geo-replication; các replica có endpoint riêng và có thể phục vụ workload ở khu vực khác.

### 5.1. Tự động khám phá replica

Theo tài liệu hiện hành, provider có thể tự khám phá các replica của store. Khi endpoint đang dùng gặp lỗi mạng, HTTP 500 trở lên hoặc throttling 429, client có thể thử endpoint replica phù hợp. Khi primary hoạt động trở lại, client có thể quay lại primary.

Cơ chế này hỗ trợ các trường hợp lỗi dịch vụ/hạ tầng, nhưng **không sửa được lỗi authorization**. Nếu mọi endpoint dùng cùng một principal thiếu role, failover sang replica cũng có thể trả 403.

### 5.2. Khai báo danh sách endpoint ưu tiên

Ví dụ cấu hình endpoint primary và replica:

~~~yaml
spring:
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoints:
              - "https://checkout-config-primary.azconfig.io"
              - "https://checkout-config-replica.azconfig.io"
~~~

Các endpoint phải thuộc cùng cấu hình store có replication được thiết lập phù hợp. Danh sách được thử theo thứ tự ưu tiên. Kiểm tra tài liệu provider cho phiên bản cụ thể về cơ chế tự khám phá và cách kết hợp với danh sách endpoint.

Có thể tắt auto-discovery nếu muốn kiểm soát endpoint hoàn toàn:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].replica-discovery-enabled=false
~~~

Chỉ tắt khi đã có chiến lược failover khác và đã kiểm thử. Nếu không, ứng dụng có thể mất khả năng tự chuyển sang replica được khám phá.

### 5.3. Replica không thay thế thiết kế cấu hình

- Cần bảo đảm key-value, label và snapshot được replicate theo cơ chế Azure.
- Kiểm tra quyền đọc của identity trên tài nguyên/replica theo mô hình Azure RBAC.
- Theo dõi latency, lỗi kết nối và số lần failover.
- Xác minh ứng dụng không phụ thuộc một endpoint hard-code ở môi trường khác.
- Kiểm thử primary down, replica down và primary phục hồi.

Replica tăng tính sẵn sàng của **nguồn cấu hình**; nó không làm cho các secret hoặc giá trị sai trở nên hợp lệ.

## 6. Retry và phân loại lỗi từ xa

Retry hữu ích với lỗi tạm thời như network interruption, 429 hoặc 5xx. Retry không giải quyết được lỗi cấu hình hoặc quyền như 401, 403, tên resource sai hay secret không tồn tại.

### 6.1. Retry với exponential backoff

Spring Cloud Azure hỗ trợ cấu hình retry cho các Azure SDK client. Ví dụ cấu hình chung:

~~~yaml
spring:
  cloud:
    azure:
      retry:
        mode: exponential
        exponential:
          max-retries: 4
          base-delay: PT0.0801S
          max-delay: PT9S
~~~

Cấu hình theo service có thể ghi đè cấu hình chung. Với Key Vault PropertySource, có thể đặt retry riêng:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - name: checkout-vault
              endpoint: "${AZURE_KEYVAULT_ENDPOINT}"
              retry:
                mode: exponential
                exponential:
                  max-retries: 4
                  base-delay: PT0.0801S
                  max-delay: PT9S
~~~

Các con số trên là ví dụ từ tài liệu Spring Cloud Azure, không phải giá trị tối ưu cho mọi workload. Chọn theo timeout tổng của startup, latency dịch vụ và ngân sách request. Retry nhiều tầng (SDK retry + ứng dụng retry + orchestrator restart) có thể nhân số lần gọi và tạo áp lực lớn hơn khi dịch vụ đang gặp sự cố.

### 6.2. Phân loại lỗi trước khi retry

| Mã/lỗi | Nhóm | Hướng xử lý |
| --- | --- | --- |
| 401 Unauthorized | Credential/token | Kiểm tra identity, tenant, credential chain; không retry vô hạn |
| 403 Forbidden | Authorization/RBAC | Cấp đúng role, kiểm tra scope và propagation |
| 404 Not Found | Sai resource/key/secret hoặc version | Kiểm tra endpoint, key, label, secret name và trạng thái |
| 429 Too Many Requests | Throttling | Tôn trọng retry-after nếu SDK hỗ trợ, exponential backoff, giảm tải |
| 500–599 | Lỗi dịch vụ | Retry giới hạn, failover replica nếu có |
| DNS/connection timeout | Network | Retry có giới hạn; kiểm tra DNS, firewall, route và private endpoint |
| TLS/certificate validation | Trust/configuration | Sửa certificate/proxy/endpoint; không tắt TLS verification để chữa lỗi |
| Property thiếu sau khi tải | Mapping/selection/validation | Kiểm tra key filter, label, secret-keys và binding |

Không log access token, connection string, secret value hoặc toàn bộ HTTP header. Khi báo lỗi, ghi loại lỗi, resource name không nhạy cảm, correlation/request ID nếu có và principal đã được xác định an toàn.

## 7. Hành vi khi Key Vault hoặc secret không truy cập được

Key Vault có thể được sử dụng theo hai cách trong Spring Cloud Azure:

- **Key Vault Secrets PropertySource trực tiếp:** tải secret vào Spring Environment ngay giai đoạn khởi tạo.
- **Key Vault reference trong App Configuration:** App Configuration provider nhận reference và gọi Key Vault để resolve secret.

### 7.1. Secret bắt buộc phải fail closed

Nếu `payments.api-token` là bắt buộc để gọi cổng thanh toán, ứng dụng không nên tiếp tục khởi động với token rỗng, token cũ đã bị thu hồi hoặc chuỗi demo. Hãy dùng validation để phát hiện thiếu secret:

~~~java
package com.example.checkout;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payments")
public record PaymentProperties(
        @NotBlank String apiToken,
        @NotNull Duration timeout) {
}
~~~

Bật `@ConfigurationPropertiesScan` trong class ứng dụng và thêm dependency Bean Validation tương thích Spring Boot nếu chưa có. Khi secret không resolve được hoặc property thiếu, validation sẽ làm ApplicationContext không hợp lệ thay vì tạo client với credential giả.

### 7.2. Không có một fail-fast switch chung cho mọi nguồn

App Configuration và Key Vault có lifecycle khác nhau:

| Nguồn | Cơ chế điều khiển | Khi lỗi |
| --- | --- | --- |
| App Configuration Config Data import | `spring.config.import`, provider enable/disable, replicas và Config Data optional semantics | Import bắt buộc không tải được có thể làm startup thất bại |
| Key Vault reference | App Configuration provider resolve reference bằng identity có quyền Key Vault | Resolve lỗi có thể làm thiếu property hoặc startup thất bại khi property bắt buộc |
| Key Vault PropertySource trực tiếp | `property-source-enabled`, danh sách `secret-keys`, retry và refresh interval | Lỗi tải secret ở giai đoạn khởi tạo có thể ngăn context khởi động |
| `SecretClient` gọi trong code | Ứng dụng quyết định thời điểm gọi và xử lý exception | Lỗi có thể xảy ra lúc runtime, cần xử lý ở service boundary |

Không giả định rằng thuộc tính `fail-fast=false` của App Configuration cũ cũng áp dụng cho Key Vault PropertySource hoặc App Configuration 6.x/7.x. Bảng thuộc tính hiện hành của Key Vault PropertySource không cung cấp một công tắc fail-fast chung tương đương để biến secret bắt buộc thành optional.

### 7.3. Secret không được fallback sang giá trị giả

Ví dụ **không nên dùng trong production**:

~~~yaml
payments:
  api-token: "${payments.api-token:demo-token}"
~~~

Nếu secret bị thiếu, placeholder fallback có thể làm ứng dụng khởi động với giá trị demo và chỉ thất bại khi giao dịch thật diễn ra. Với credential, hãy để property bắt buộc và validation làm ứng dụng fail closed.

Có thể dùng fallback cho một **tham số không nhạy cảm** đã có default an toàn, chẳng hạn timeout. Không dùng fallback để che lỗi xác thực hoặc secret bị mất quyền.

## 8. Readiness, liveness và hành vi khi Azure tạm ngừng

Nếu ứng dụng không thể khởi động vì cấu hình bắt buộc, orchestrator sẽ không nhận được instance Ready. Nếu ứng dụng đã khởi động và Azure tạm ngừng, cần quyết định có tiếp tục phục vụ bằng **last-known-good configuration** hay chuyển instance sang Not Ready.

| Trạng thái | Hướng xử lý gợi ý |
| --- | --- |
| Cấu hình bắt buộc chưa tải lần đầu | Startup thất bại; không đưa instance vào load balancer |
| Cấu hình không nhạy cảm đã tải và vẫn dùng được | Có thể tiếp tục dùng last-known-good trong thời gian chính sách cho phép |
| Secret đã hết hạn/thu hồi hoặc không còn hợp lệ | Không tiếp tục giao dịch bằng credential cũ; chuyển Not Ready hoặc từ chối nghiệp vụ cần secret |
| Azure lỗi tạm thời nhưng ứng dụng vẫn có cache hợp lệ | Giữ cache trong giới hạn an toàn, cảnh báo và retry có kiểm soát |
| Cấu hình mới không hợp lệ | Không thay last-known-good bằng cấu hình lỗi; báo lỗi refresh và giữ trạng thái đã xác thực trước đó nếu provider hỗ trợ |

**Không nên làm liveness probe phụ thuộc trực tiếp vào mọi lần gọi Azure.** Nếu Azure tạm thời chậm, liveness thất bại có thể làm orchestrator restart hàng loạt instance và tạo thêm tải. Readiness có thể phản ánh ứng dụng còn phục vụ an toàn hay không; liveness nên tập trung vào khả năng tiến triển của tiến trình.

Nếu cần giữ last-known-good, hãy thiết kế và kiểm thử rõ: cache được lưu ở đâu, bao lâu được phép dùng, secret bị thu hồi xử lý thế nào và cách phục hồi sau khi Azure trở lại. Không mặc định rằng Spring Cloud Azure sẽ lưu bền cấu hình remote ra disk để dùng sau restart.

## 9. Kiểm thử cấu hình theo nhiều lớp

Không một loại test nào chứng minh được toàn bộ tích hợp. Tách test binding, Spring context, quyền Azure và hành vi nguồn từ xa.

~~~mermaid
flowchart TD
    A["Unit test: Binder / validation"] --> B["Spring context test: tắt provider Azure"]
    B --> C["Integration test: App Configuration + Key Vault dev"]
    C --> D["Failure test: 401/403/404/429/network"]
    D --> E["Deployment test: Managed Identity + private endpoint"]
~~~

### 9.1. Unit test cho binding, không gọi Azure

Dùng `MockEnvironment` và `Binder` để kiểm tra tên property, kiểu dữ liệu và default:

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
    void bindsNonSecretSettings() {
        var environment = new MockEnvironment()
                .withProperty("payments.timeout", "PT3S");

        Duration timeout = Binder.get(environment)
                .bind("payments.timeout", Duration.class)
                .orElseThrow();

        assertThat(timeout).isEqualTo(Duration.ofSeconds(3));
    }
}
~~~

Test này không cần Azure credentials và không đưa secret giả vào log. Có thể viết thêm test validation để xác minh thiếu `payments.api-token` sẽ làm cấu hình không hợp lệ.

### 9.2. Spring context test với provider đã tắt

Nếu `application.yml` có import App Configuration và Key Vault PropertySource, test nghiệp vụ không nên vô tình gọi Azure thật. Tạo `application-test.yml`:

~~~yaml
spring:
  cloud:
    azure:
      appconfiguration:
        enabled: false
      keyvault:
        secret:
          property-source-enabled: false

payments:
  api-token: test-only-placeholder
  timeout: PT3S
~~~

Test context:

~~~java
package com.example.checkout;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class CheckoutConfigurationContextTest {
    @Autowired
    PaymentProperties properties;

    @Test
    void startsWithExplicitTestConfiguration() {
        assertThat(properties.apiToken()).isEqualTo("test-only-placeholder");
        assertThat(properties.timeout().getSeconds()).isEqualTo(3);
    }
}
~~~

`spring.cloud.azure.appconfiguration.enabled=false` vô hiệu hóa việc tải store; `property-source-enabled=false` tắt Key Vault PropertySource. Hãy dùng BOM Spring Cloud Azure đã sửa các lỗi liên quan đến disable provider ở các bản phát hành trước. Kiểm tra test log và network để chắc chắn không có request tới Azure.

Giá trị `test-only-placeholder` chỉ tồn tại trong test profile; không dùng profile này khi deploy production.

### 9.3. Integration test với tài nguyên dev riêng

Để xác minh RBAC và provider thật, cần App Configuration store và Key Vault dev/sandbox:

1. Tạo key-value không nhạy cảm `/application/payments.timeout`.
2. Tạo secret giả trong Key Vault và reference `/application/payments.api-token`.
3. Gán App Configuration Data Reader và Key Vault Secrets User cho identity test.
4. Chạy ứng dụng bằng credential tương ứng và xác nhận Spring bind được cả hai property.
5. Chạy test với identity chỉ có quyền App Configuration để xác nhận reference không resolve khi thiếu Key Vault permission.
6. Thu hồi quyền App Configuration trong môi trường test để xác minh lỗi 403 được phân loại đúng.
7. Thử key/label không tồn tại và secret bị disable/đổi tên.
8. Kiểm tra log không chứa token, secret value, access token hoặc connection string.

Không chạy test mất quyền, xóa secret hay rotation trên tài nguyên production. Tạo identity và resource thử nghiệm riêng để các tình huống âm tính không làm gián đoạn dịch vụ thật.

### 9.4. Kiểm thử khi nguồn từ xa lỗi

| Test case | Cách mô phỏng an toàn | Kết quả cần xác minh |
| --- | --- | --- |
| 401 | Dùng identity test không lấy được token hoặc tenant sai | Startup/runtime báo authentication error |
| 403 App Configuration | Identity test thiếu App Configuration Data Reader | Không có key-value remote; lỗi authorization rõ |
| 403 Key Vault | Có quyền App Configuration nhưng không có Key Vault Secrets User | Reference không resolve; secret bắt buộc làm app không Ready |
| 404 key/secret | Dùng tên key hoặc secret không tồn tại ở store dev | Validation phát hiện property bắt buộc bị thiếu |
| 429 | Test tải trên tài nguyên riêng hoặc mock SDK response | Retry/backoff có giới hạn, không tạo retry storm |
| 5xx/network | Dùng endpoint/replica thử nghiệm hoặc mock client | Retry/failover hoạt động; log có correlation ID |
| Private endpoint/DNS | Chạy workload từ subnet thử nghiệm chưa có route phù hợp | Lỗi network được phân biệt với 403 |
| Refresh thất bại sau startup | Ngắt kết nối dev sau khi app đã nạp cấu hình | Xác minh last-known-good/Readiness theo chính sách |

Test lỗi nguồn remote cần quan sát **cả exit code khởi động và trạng thái Spring context**, không chỉ kiểm tra một exception message.

## 10. Kiểm tra cấu hình bắt buộc bằng validation

Một số lỗi remote không xuất hiện dưới dạng exception ngay khi tải: key có thể không tồn tại, label sai hoặc tên property bị mapping sai. Vì vậy, ứng dụng cần xác minh cấu hình sau khi nạp.

Ví dụ `PaymentProperties`:

~~~java
package com.example.checkout;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payments")
public record PaymentProperties(
        @NotBlank String apiToken,
        @NotNull Duration timeout) {
}
~~~

Bật scan:

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

Thêm dependency validation tương thích Spring Boot nếu dự án chưa có:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Khi `payments.api-token` không được resolve hoặc `payments.timeout` không có, validation làm context thất bại. Đây là một cách bảo vệ quan trọng: **tải được một PropertySource không có nghĩa cấu hình ứng dụng đã hợp lệ**.

Không override `toString()` của object chứa secret bằng cách in toàn bộ field. Nếu cần log trạng thái, chỉ ghi boolean đã cấu hình hoặc tên property không nhạy cảm.

## 11. Quan sát và vận hành khi nguồn lỗi

Một hệ thống có thể theo dõi:

- Số lần tải App Configuration/Key Vault thành công và thất bại.
- Latency, timeout, 401/403, 404, 429 và 5xx.
- Số lần retry, failover và thời gian phục hồi.
- Thời điểm refresh thành công gần nhất và tuổi của cấu hình đã nạp.
- Trạng thái Ready của từng instance.
- Version hoặc metadata secret đã được nạp nếu có thể ghi nhận mà không tiết lộ value.

Không log secret, token hoặc toàn bộ `Environment`. Nếu log URI Key Vault, hãy cân nhắc chỉ ghi vault/secret name và loại lỗi, không ghi credential hay query chứa token.

### 11.1. Health check không nên tạo tải vô hạn

Không gọi App Configuration và Key Vault ở mọi lần readiness probe nếu probe được chạy mỗi vài giây. Thay vào đó, có thể kiểm tra trạng thái cache/refresh gần nhất và thời hạn hợp lệ của cấu hình theo chính sách ứng dụng. Nếu cần kiểm tra kết nối chủ động, dùng interval có giới hạn và không để health check tạo thêm một request Azure trên mỗi lần probe.

### 11.2. Quy tắc giữ last-known-good

Với cấu hình không nhạy cảm, có thể tiếp tục dùng giá trị đã tải gần nhất trong một cửa sổ cho phép nếu refresh thất bại. Cần xác định:

- TTL tối đa của last-known-good.
- Cấu hình nào được phép dùng giá trị cũ.
- Cách cảnh báo khi vượt TTL.
- Điều kiện đưa instance về Not Ready.
- Cách nạp lại và validate khi nguồn trở lại.

Với secret đã bị thu hồi hoặc có nguy cơ lộ, last-known-good không phải lúc nào cũng an toàn. Cần quy trình incident riêng để vô hiệu hóa credential, cập nhật client và không tiếp tục giao dịch bằng token cũ.

## 12. Ma trận quyết định fail-open hay fail-closed

| Loại dữ liệu | Khi nguồn từ xa lỗi | Quyết định gợi ý |
| --- | --- | --- |
| Banner, thông điệp hiển thị | Có thể dùng giá trị cục bộ | Fail-open nếu default không ảnh hưởng nghiệp vụ |
| Timeout/retry có default an toàn | Có thể dùng local default đã kiểm thử | Fail-open có giới hạn và cảnh báo |
| Endpoint dịch vụ thanh toán | Sai endpoint có thể gửi dữ liệu tới đích không mong muốn | Thường fail-closed hoặc chỉ dùng endpoint local đã được kiểm soát |
| API token/mật khẩu | Không có secret hợp lệ thì không thể xác thực an toàn | Fail-closed |
| Quy tắc bảo mật/authorization | Thiếu policy có thể mở quyền quá mức | Fail-closed |
| Feature flag rollout | Có thể chọn nhánh cũ nếu đã kiểm thử | Quy định default theo từng flag; không thay authorization |
| Cấu hình định tuyến dữ liệu | Có thể gây ghi sai tenant/region | Fail-closed hoặc giữ last-known-good có kiểm soát |

**Fail-open** có nghĩa ứng dụng tiếp tục hoạt động với giá trị thay thế khi nguồn lỗi. **Fail-closed** có nghĩa từ chối khởi động hoặc từ chối nghiệp vụ nếu không xác minh được cấu hình cần thiết. Chọn theo hậu quả khi dùng giá trị sai, không chọn chỉ để tăng tỷ lệ startup thành công.

## 13. Bài tập thực hành tổng hợp

Một `order-service` dùng:

- `orders.timeout` từ App Configuration, default cục bộ là `PT3S`.
- `orders.partner-token` là Key Vault reference và bắt buộc.
- Managed Identity để đọc cả hai dịch vụ.
- Hai App Configuration replicas ở hai khu vực.
- Spring Boot chạy ba instance sau load balancer.

**Yêu cầu:**

1. Gán App Configuration Data Reader và Key Vault Secrets User cho đúng runtime identity.
2. Thiết kế import để timeout có thể dùng default khi chính sách cho phép, nhưng token thiếu phải làm instance không Ready.
3. Cấu hình replica endpoints và xác minh failover khi primary gặp 503/429.
4. Viết unit test binding với giá trị giả.
5. Viết context test tắt cả hai provider.
6. Viết integration test với identity test thiếu Key Vault permission.
7. Kiểm tra log không in token và readiness không restart instance liên tục khi Azure tạm lỗi.

**Câu hỏi tự đánh giá:**

- Vì sao lấy được access token không chứng minh ứng dụng đọc được secret?
- Khác nhau giữa App Configuration Data Reader và Contributor là gì?
- Vì sao thuộc tính `fail-fast` trong tài liệu Spring Cloud Azure 5.x không nên dùng cho dòng 6.x/7.x?
- Khi nào `optional:azureAppConfiguration` có ích và vì sao không phải cơ chế chữa mọi lỗi mạng/403?
- Nếu App Configuration có replica nhưng identity thiếu role ở mọi endpoint, failover có giải quyết được không?
- Vì sao secret bắt buộc nên fail closed nhưng banner có thể dùng default?
- Unit test Binder chứng minh được điều gì và không chứng minh được điều gì?

**Đáp án định hướng:** authentication cấp token, authorization cấp quyền data-plane; role Data Reader chỉ đọc dữ liệu còn Contributor quản lý resource; fail-fast bị loại bỏ từ 6.0; optional chỉ xử lý trường hợp Config Data location optional chứ không thay thế retry/replica; replica không sửa 403; secret không được fallback sang credential giả; unit test kiểm tra binding, integration test mới kiểm tra identity và Azure thật.

## 14. Tài liệu tham khảo chính thức

- [Microsoft Learn – Spring Cloud Azure authentication](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/authentication): DefaultAzureCredential, Managed Identity, Microsoft Entra ID và Azure RBAC.
- [Microsoft Learn – Developer Guide for Using Spring Cloud Azure App Configuration](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/app-configuration-support): Config Data import, authentication, geo-replication và failover.
- [Spring Cloud Azure – App Configuration client README](https://github.com/Azure/azure-sdk-for-java/blob/main/sdk/spring/spring-cloud-azure-starter-appconfiguration-config/README.md): thuộc tính provider và cấu hình endpoint/replica.
- [Spring Cloud Azure – App Configuration release notes](https://github.com/Azure/AppConfiguration/blob/main/releaseNotes/SpringCloudAzureAppConfigurationConfig.md): thay đổi breaking change 6.0, bao gồm việc loại bỏ `fail-fast`.
- [Microsoft Learn – Key Vault RBAC guide](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide): role đọc/ghi secret và phạm vi cấp quyền.
- [Microsoft Learn – Spring Cloud Azure secret management](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/secret-management): Key Vault PropertySource, secret-keys, retry và refresh.
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): Config Data import, optional location và thứ tự property source.
- [Microsoft Learn – Use dynamic configuration in a Spring Boot app](https://learn.microsoft.com/en-us/azure/azure-app-configuration/enable-dynamic-configuration-java-spring-app): manual/automatic refresh và tác động tới refresh-scoped beans.

**Ghi nhớ:** kiểm thử tích hợp Azure cần xác minh đúng **principal, role, network, resource và property mapping**. Với nguồn từ xa, hãy phân loại lỗi trước khi retry, dùng replicas cho tính sẵn sàng, chỉ dùng fallback cho cấu hình có default an toàn và luôn fail closed khi secret hoặc policy bắt buộc không hợp lệ.
