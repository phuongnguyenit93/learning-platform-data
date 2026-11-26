# Tạo nhiều client cho các đích hoặc danh tính riêng

Trong module **SPRING_VAULT**, một ứng dụng Java thường inject một `VaultTemplate` để gọi HashiCorp Vault. Tuy nhiên, một dịch vụ có thể phải đọc secret từ **hai cụm Vault**, hoặc dùng **hai danh tính có policy khác nhau trên cùng một cụm**. Khi đó, một bean `VaultTemplate` duy nhất không đủ để biểu diễn ranh giới truy cập.

Bài học thuộc chương **Cấu hình Java** này hướng dẫn tạo **nhiều client Spring Vault** một cách rõ ràng, kiểm soát endpoint, authentication, session và quyền truy cập riêng cho từng client. Ví dụ thực hành dùng hai bean `VaultTemplate` với `@Qualifier` và đọc KV v2 ở hai Vault dev server. Sau đó, chúng ta mở rộng sang hai workload identity trên cùng Vault, vận hành token/lease, TLS, Transit/PKI và kiểm thử cách ly.

**Mục tiêu:**
- Phân biệt **nhiều Vault server** với **nhiều danh tính trên cùng Vault server**.
- Khởi tạo hai `VaultTemplate` hoặc `VaultOperations` mà không gây lỗi ambiguous bean.
- Chọn đúng client ở từng service bằng `@Qualifier`, không ngầm dùng một token cho mọi nghiệp vụ.
- Thiết kế policy ít quyền nhất, session/token lifecycle và TLS độc lập.
- Kiểm thử rằng không thể vô tình dùng client A để truy cập tài nguyên chỉ dành cho client B.

## 1. Hai tình huống cần nhiều client

### Tình huống A: Hai đích Vault độc lập

Giả sử một Java service có hai nhiệm vụ:
1. Xử lý đơn hàng, lấy cấu hình từ **Vault Orders**.
2. Tạo báo cáo, lấy cấu hình từ **Vault Reports**.

Trong kiến trúc này, hai Vault có thể khác cluster, region, namespace, DNS, CA hoặc auth backend.

~~~mermaid
flowchart LR
    S["Ứng dụng Java"] --> O["ordersVaultTemplate"]
    S --> R["reportsVaultTemplate"]
    O --> OA["Endpoint Orders<br/>Token/identity Orders"]
    R --> RA["Endpoint Reports<br/>Token/identity Reports"]
    OA --> OV["Vault Orders<br/>KV, Transit"]
    RA --> RV["Vault Reports<br/>KV, PKI"]
~~~

Điểm quan trọng: **không chỉ có hai URL, mà còn có hai ngữ cảnh bảo mật**. Token của Vault Orders thường không có giá trị trên Vault Reports. Mỗi client cần được cấu hình đúng với đích và danh tính của nó.

### Tình huống B: Một Vault nhưng hai danh tính

Một ứng dụng cũng có thể dùng cùng endpoint `https://vault.internal:8200` nhưng tách danh tính:

- **Orders identity:** chỉ có quyền `read` trên `secret/data/orders/*`.
- **Reports identity:** chỉ có quyền `read` trên `secret/data/reports/*`.

~~~mermaid
flowchart TD
    A["Một HashiCorp Vault"] --> B["Auth role: orders-reader"]
    A --> C["Auth role: reports-reader"]
    B --> D["ordersVaultTemplate"]
    C --> E["reportsVaultTemplate"]
    D --> F["Đọc secret/orders/..."]
    E --> G["Đọc secret/reports/..."]
~~~

Hai template có thể cùng `VaultEndpoint` nhưng phải giữ **`ClientAuthentication` và `SessionManager` riêng** nếu chúng đại diện cho hai danh tính khác nhau. Không nên thay token trên một client dùng chung trước mỗi request; cách đó có thể tạo race condition khi nhiều request chạy đồng thời.

### Bảng lựa chọn kiến trúc

| Nhu cầu | Endpoint | Identity/session | Có nên tách client? |
| --- | --- | --- | --- |
| Một workload đọc nhiều secret bằng cùng quyền | Giống nhau | Giống nhau | Thường **không cần** |
| Hai cụm Vault khác nhau | Khác nhau | Thường khác nhau | **Có** |
| Một cụm Vault, hai policy rạch ròi | Giống nhau | Khác nhau | **Có** |
| Một cụm, hai namespace với binding khác nhau | Có thể giống nhau | Có thể khác | **Có** khi cần tách ngữ cảnh |
| Một service cần thêm API Transit từ cùng identity | Giống nhau | Giống nhau | Thường tái sử dụng một `VaultOperations` |
| Mỗi HTTP request mang một tenant bất kỳ | Phụ thuộc thiết kế | Phụ thuộc thiết kế | Cần registry có kiểm soát; không tạo tùy tiện mỗi request |

Đừng tạo nhiều bean chỉ vì nhiều API nghiệp vụ: `VaultTemplate` hỗ trợ KV, Transit, PKI và các operations khác. Tách client khi cần phân định **đích kết nối hoặc ranh giới danh tính**.

## 2. Những đối tượng cần tách và có thể dùng chung

Mỗi client có thể được biểu diễn bằng bộ phụ thuộc:

~~~text
Client A = (VaultEndpoint A, ClientAuthentication A, SessionManager A,
            HTTP client/TLS A, Namespace A, VaultTemplate A)

Client B = (VaultEndpoint B, ClientAuthentication B, SessionManager B,
            HTTP client/TLS B, Namespace B, VaultTemplate B)
~~~

| Đối tượng | Có thể dùng chung? | Khuyến nghị |
| --- | --- | --- |
| `VaultEndpoint` | Có, nếu cùng server | Có thể là một instance bất biến hoặc hai instance cùng giá trị |
| `ClientAuthentication` | Chỉ nếu thật sự là cùng danh tính | Tách khi policy/role/token khác nhau |
| `SessionManager` | Thường **không** khi identity khác | Mỗi identity có phiên token riêng |
| `VaultTemplate` / `VaultOperations` | Có nếu cùng ngữ cảnh quyền và đích | Đặt tên riêng khi cần cách ly |
| HTTP request factory/trust store | Có nếu yêu cầu TLS/proxy trùng nhau | Tách nếu CA, mTLS, timeout hay proxy khác |
| `TaskScheduler` | Có thể dùng chung hạ tầng thread pool | Tránh renew token/lease của một client làm đói client khác |
| Vault namespace | Phụ thuộc topology | Cấu hình tường minh, không ngầm chuyển namespace bằng chuỗi path |
| Secret path/KV mount | Có thể trùng tên trên hai cụm | Luôn đi cùng đúng client và policy |

**Không đồng nhất endpoint với identity.** Một `VaultEndpoint` chỉ chứa địa chỉ; policy được Vault áp lên token của request. Cùng đường dẫn `secret/orders/app` có thể trả dữ liệu khác nhau trên hai Vault hoặc bị chặn với các token khác nhau.

## 3. Cấu hình thuộc tính riêng cho hai client

Ví dụ dùng Spring Boot với hai Vault server tại local:

- Vault Orders: `http://127.0.0.1:8200`.
- Vault Reports: `http://127.0.0.1:8300`.

Các port này là **giá trị lab**; staging/production phải dùng endpoint HTTPS và chính sách mạng phù hợp.

Trong `src/main/resources/application.yml`, yêu cầu biến môi trường có sẵn:

~~~yaml
app:
  vault:
    orders:
      uri: ${ORDERS_VAULT_ADDR}
      token: ${ORDERS_VAULT_TOKEN}
    reports:
      uri: ${REPORTS_VAULT_ADDR}
      token: ${REPORTS_VAULT_TOKEN}
~~~

Trong `src/main/resources/application-local.yml`, chỉ cấu hình **fallback endpoint local**:

~~~yaml
app:
  vault:
    orders:
      uri: ${ORDERS_VAULT_ADDR:http://127.0.0.1:8200}
    reports:
      uri: ${REPORTS_VAULT_ADDR:http://127.0.0.1:8300}
~~~

Không đặt root token demo vào file YAML. Ở môi trường thật, tách nguồn credential và thay `TokenAuthentication` bằng auth theo workload.

**Lưu ý:** `app.vault.orders.*` và `app.vault.reports.*` là các khóa **do ví dụ này tự định nghĩa**. Chúng không được `EnvironmentVaultConfiguration` mặc định hiểu là hai cấu hình Vault độc lập. `EnvironmentVaultConfiguration` dùng nhóm `vault.*` cho một bộ cấu hình chuẩn; bài này cố ý tự xây bean để có hai bộ phụ thuộc không xung đột.

### Phân biệt với Spring Cloud Vault

Nếu dự án đã sử dụng Spring Cloud Vault Config và `spring.cloud.vault.*`, starter có thể tự đăng ký hạ tầng Vault. Khi đó cần xác định rõ client nào thuộc auto-configuration, client nào do ứng dụng tự tạo. Không import thêm `AbstractVaultConfiguration` hoặc `EnvironmentVaultConfiguration` cho cùng một client rồi tiếp tục khai báo `@Bean VaultTemplate` nếu chưa kiểm tra bean definitions. Cách đơn giản cho bài học là **không bật một cơ chế khác tự tạo VaultTemplate**.

## 4. Cấu hình Java hoàn chỉnh: hai bean VaultTemplate riêng

Chúng ta chọn constructor phổ biến `VaultTemplate(VaultEndpoint, ClientAuthentication)`, dùng được trên những nhánh Spring Vault thông dụng (3.2, 4.0, 4.1), để tập trung vào **nhiều đích và nhiều danh tính**.

Dependency Maven (dự án cần BOM hoặc `dependencyManagement` tương thích):

~~~xml
<dependency>
    <groupId>org.springframework.vault</groupId>
    <artifactId>spring-vault-core</artifactId>
</dependency>
~~~

Ví dụ Java 17+, Spring Boot. Tạo `MultiVaultConfiguration.java`:

~~~java
package com.example.vault;

import java.net.URI;
import java.util.Locale;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

@Configuration(proxyBeanMethods = false)
public class MultiVaultConfiguration {

    @Bean("ordersVaultTemplate")
    public VaultTemplate ordersVaultTemplate(
            @Value("${app.vault.orders.uri}") String address,
            @Value("${app.vault.orders.token}") String token) {

        return createTemplate(address, token);
    }

    @Bean("reportsVaultTemplate")
    public VaultTemplate reportsVaultTemplate(
            @Value("${app.vault.reports.uri}") String address,
            @Value("${app.vault.reports.token}") String token) {

        return createTemplate(address, token);
    }

    private static VaultTemplate createTemplate(
            String address, String token) {

        if (address == null || address.isBlank()) {
            throw new IllegalArgumentException(
                    "Vault endpoint không được rỗng");
        }
        if (token == null || token.isBlank()) {
            throw new IllegalArgumentException(
                    "Vault token không được rỗng");
        }

        URI uri = URI.create(address.trim());
        String scheme = uri.getScheme();

        if (uri.getHost() == null
                || (!"http".equalsIgnoreCase(scheme)
                    && !"https".equalsIgnoreCase(scheme))
                || uri.getRawUserInfo() != null
                || uri.getRawQuery() != null
                || uri.getRawFragment() != null
                || (uri.getRawPath() != null
                    && !uri.getRawPath().isEmpty()
                    && !"/".equals(uri.getRawPath()))) {
            throw new IllegalArgumentException(
                    "Vault endpoint phải là base URL http(s)://host[:port]");
        }

        int port = uri.getPort();
        if (port < 0) {
            port = "https".equalsIgnoreCase(scheme) ? 443 : 80;
        }
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException(
                    "Cổng kết nối Vault không hợp lệ");
        }

        VaultEndpoint endpoint = VaultEndpoint.create(
                uri.getHost(), port);
        endpoint.setScheme(scheme.toLowerCase(Locale.ROOT));

        ClientAuthentication authentication =
                new TokenAuthentication(token);

        return new VaultTemplate(endpoint, authentication);
    }
}
~~~

**Những điểm cần hiểu:**

1. `@Bean("ordersVaultTemplate")` và `@Bean("reportsVaultTemplate")` tạo **hai bean khác tên** nhưng cùng kiểu `VaultTemplate`.
2. Hai method nhận **hai bộ property riêng**. Không có fallback tự động từ Reports token sang Orders token khi cấu hình thiếu.
3. `createTemplate(...)` dùng helper chung để tránh lặp logic; helper tạo **một endpoint và authentication mới cho mỗi client**.
4. `@Configuration(proxyBeanMethods = false)` phù hợp vì các `@Bean` method ở đây không tự gọi chéo lẫn nhau.
5. Validation kiểm tra URL gốc, không cho path, userinfo, query, fragment. Nó chỉ kiểm tra cú pháp: TLS, DNS và policy vẫn cần được thử bằng request thật.
6. Không định nghĩa `@Primary` trong ví dụ. Việc bắt buộc chọn `@Qualifier` giúp phát hiện dependency injection mơ hồ, thay vì ngầm dùng client không đúng.
7. `TokenAuthentication` **chỉ dành cho lab**. Nó sử dụng token có sẵn; không tự đăng nhập lại khi token hết hạn hoặc bị revoke.

**Chú ý security:** validation trên chưa áp chính sách “HTTPS bắt buộc ngoài local”. Trong staging/prod, bổ sung kiểm tra scheme hoặc kiểm soát cấu hình triển khai, dùng HTTPS với trust store đúng và không vô hiệu hóa hostname verification.

### Vì sao không khai báo một bean VaultEndpoint duy nhất?

Hai đích Vault có endpoint khác nhau. Nếu cả hai `VaultTemplate` đều inject một bean `VaultEndpoint` không tên, rất dễ dùng nhầm. Bài này dựng endpoint tại helper để tránh ambiguous injection. Trong hệ thống lớn, bạn có thể khai báo `ordersVaultEndpoint` và `reportsVaultEndpoint` riêng, cùng `@Qualifier` ở mọi điểm sử dụng.

**Không tạo `VaultTemplate` mới ở mỗi HTTP request.** Nó là client hạ tầng, nên được tạo và quản lý cùng Spring context. Tạo mới liên tục làm tăng overhead, khó quản lý session/connection và có nguy cơ cấp phát token không cần thiết.

## 5. Tiêu thụ đúng client bằng @Qualifier

Giả sử một service cần kiểm tra sự tồn tại của hai secret nhưng không được xuất nội dung ra log. Tạo `MultiVaultSecretReader.java`:

~~~java
package com.example.vault;

import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class MultiVaultSecretReader {

    private final VaultOperations ordersVault;
    private final VaultOperations reportsVault;

    public MultiVaultSecretReader(
            @Qualifier("ordersVaultTemplate")
            VaultOperations ordersVault,
            @Qualifier("reportsVaultTemplate")
            VaultOperations reportsVault) {

        this.ordersVault = ordersVault;
        this.reportsVault = reportsVault;
    }

    public boolean ordersSecretPresent() {
        return hasField(ordersVault, "orders/app", "apiKey");
    }

    public boolean reportsSecretPresent() {
        return hasField(reportsVault, "reports/app", "apiKey");
    }

    private boolean hasField(
            VaultOperations vault,
            String secretPath,
            String fieldName) {

        VaultResponse response = vault
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get(secretPath);

        Map<String, Object> data =
                response == null ? null : response.getData();

        return data != null
                && data.get(fieldName) instanceof String value
                && !value.isBlank();
    }
}
~~~

`VaultTemplate` triển khai `VaultOperations`, nên service có thể khai báo kiểu interface. Nhưng vì có **hai bean cùng triển khai interface**, constructor phải có `@Qualifier` để Spring biết đối tượng nào dành cho Orders và đối tượng nào dành cho Reports.

Khi gọi:

~~~java
reader.ordersSecretPresent();
reader.reportsSecretPresent();
~~~

mỗi operation sẽ dùng đúng token và endpoint của client mà field tham chiếu. `secret` là mount KV, `orders/app` hoặc `reports/app` là đường dẫn **tương đối trong mount**. Đối với KV v2, API đọc là `GET /v1/secret/data/orders/app` hoặc `GET /v1/secret/data/reports/app`; không chèn `data/` vào `get(...)`.

### Hệ quả nếu bỏ @Qualifier

Nếu viết:

~~~java
public MultiVaultSecretReader(VaultOperations vault) {
    // Có hai bean VaultOperations, Spring không biết chọn cái nào.
}
~~~

ứng dụng thường báo `NoUniqueBeanDefinitionException` khi tạo service (nếu không có `@Primary` hoặc cơ chế phân giải khác). Đây là một lỗi hữu ích vì tránh chọn nhầm Vault trong ngữ cảnh security-sensitive.

Có thể dùng `@Primary` cho một default client, nhưng trong bài toán **phân quyền rõ ràng** nên cân nhắc tránh nó. Nếu dùng `@Primary`, mọi dependency injection không có qualifier có thể âm thầm dùng cùng một Vault, làm mất khả năng cách ly.

## 6. Chạy thử với hai Vault dev server

### 6.1. Tạo hai server độc lập

Mở terminal 1 cho Vault Orders:

~~~bash
vault server -dev \
  -dev-listen-address=127.0.0.1:8200 \
  -dev-root-token-id=orders-dev-token
~~~

Mở terminal 2 cho Vault Reports:

~~~bash
vault server -dev \
  -dev-listen-address=127.0.0.1:8300 \
  -dev-root-token-id=reports-dev-token
~~~

Hai server hoạt động trong bộ nhớ để thực hành và có thể có dữ liệu hoàn toàn riêng. **Không sử dụng dev root token hoặc HTTP localhost ở production.**

### 6.2. Ghi secret tại đúng server

Trong Bash, có thể đặt biến cho từng lệnh:

~~~bash
VAULT_ADDR=http://127.0.0.1:8200 \
VAULT_TOKEN=orders-dev-token \
vault kv put secret/orders/app apiKey=orders-demo-key

VAULT_ADDR=http://127.0.0.1:8300 \
VAULT_TOKEN=reports-dev-token \
vault kv put secret/reports/app apiKey=reports-demo-key
~~~

Trong PowerShell, đặt biến lần lượt trước mỗi nhóm lệnh:

~~~powershell
$env:VAULT_ADDR = "http://127.0.0.1:8200"
$env:VAULT_TOKEN = "orders-dev-token"
vault kv put secret/orders/app apiKey=orders-demo-key

$env:VAULT_ADDR = "http://127.0.0.1:8300"
$env:VAULT_TOKEN = "reports-dev-token"
vault kv put secret/reports/app apiKey=reports-demo-key
~~~

Vault dev server thường có KV v2 ở mount `secret`. Nếu cấu hình khác, dùng `vault secrets list -detailed` trên từng server để kiểm tra engine version. Một secret được tạo ở server này **không tự xuất hiện** trên server kia.

### 6.3. Cấp cấu hình cho ứng dụng Java

Trước khi chạy Spring Boot với profile `local`, đặt bốn biến:

~~~bash
export SPRING_PROFILES_ACTIVE=local
export ORDERS_VAULT_ADDR=http://127.0.0.1:8200
export ORDERS_VAULT_TOKEN=orders-dev-token
export REPORTS_VAULT_ADDR=http://127.0.0.1:8300
export REPORTS_VAULT_TOKEN=reports-dev-token
~~~

Với PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:ORDERS_VAULT_ADDR = "http://127.0.0.1:8200"
$env:ORDERS_VAULT_TOKEN = "orders-dev-token"
$env:REPORTS_VAULT_ADDR = "http://127.0.0.1:8300"
$env:REPORTS_VAULT_TOKEN = "reports-dev-token"
~~~

Biến môi trường phải được cấp trong **process Java**. Biến đã đặt ở một terminal khác không nhất thiết được truyền cho tiến trình khởi chạy ứng dụng.

### 6.4. Kiểm tra sau khi Spring context sẵn sàng

Trong lớp `@SpringBootApplication`, thêm method bean:

~~~java
@Bean
CommandLineRunner verifyBothVaults(MultiVaultSecretReader reader) {
    return args -> {
        if (!reader.ordersSecretPresent()
                || !reader.reportsSecretPresent()) {
            throw new IllegalStateException(
                    "Chưa đọc được secret của cả hai Vault");
        }
        System.out.println("Orders và Reports Vault: kết nối OK");
    };
}
~~~

Đây là phương thức **đặt bên trong một lớp Spring configuration**, không phải file Java riêng. Cần import `org.springframework.boot.CommandLineRunner` và `org.springframework.context.annotation.Bean`.

Kết quả mong đợi:

~~~text
Orders và Reports Vault: kết nối OK
~~~

Chỉ in **trạng thái**, không in nội dung `apiKey`, token, `VaultResponse` hoặc connection details nhạy cảm. Trong production, việc bắt buộc cả hai Vault đều sẵn sàng lúc startup là một quyết định kiến trúc: service có thể cần startup fail-fast, hoặc chấp nhận suy giảm chức năng một phần khi một đích đang unavailable.

## 7. Cùng một Vault, hai danh tính và policy khác nhau

Trong hệ thống thật, bạn có thể dùng một endpoint chung mà vẫn cần hai template riêng để thực thi nguyên tắc **least privilege**.

Ví dụ cùng endpoint:

~~~yaml
app:
  vault:
    orders:
      uri: ${SHARED_VAULT_ADDR}
      token: ${ORDERS_VAULT_TOKEN}
    reports:
      uri: ${SHARED_VAULT_ADDR}
      token: ${REPORTS_VAULT_TOKEN}
~~~

Cấu hình Java và service ở mục 4–5 **không đổi**. Điều khác nhau là `ORDERS_VAULT_TOKEN` và `REPORTS_VAULT_TOKEN` phải đại diện cho **hai token/identity khác nhau**, được Vault gán policy riêng.

Ví dụ policy HCL cho Orders:

~~~hcl
path "secret/data/orders/*" {
  capabilities = ["read"]
}
~~~

Policy HCL cho Reports:

~~~hcl
path "secret/data/reports/*" {
  capabilities = ["read"]
}
~~~

Trong KV v2, policy `read` dùng đường dẫn API `secret/data/...`, không phải `secret/orders/...` của kiểu KV v1. Chỉ cấp quyền cần thiết cho từng vai trò; với thao tác `list`, `metadata` hoặc `write` phải cấp riêng theo path và khả năng thực tế, không mở rộng `*` một cách tùy tiện.

### Cần kiểm tra phép thử âm tính

Đừng chỉ kiểm tra:

- Orders token đọc `orders/app` thành công.
- Reports token đọc `reports/app` thành công.

Hãy kiểm tra **truy cập chéo thất bại**:

- Orders token không được `read` trên `secret/data/reports/app`.
- Reports token không được `read` trên `secret/data/orders/app`.

Chính phép thử âm tính chứng minh ranh giới quyền được cấu hình như mong muốn. Trong dev server, dùng **root token** sẽ che giấu lỗi policy vì token này có quyền rộng. Phải tạo token gắn policy thực tế để kiểm chứng.

### Tránh trộn danh tính trong code

Không nên viết một helper singleton có biến mutable `currentToken` rồi thay giá trị trước mỗi request:

~~~java
// Không nên thiết kế một shared mutable token như thế này:
sharedVaultClient.setCurrentToken(ordersToken);
callOrders();
sharedVaultClient.setCurrentToken(reportsToken);
callReports();
~~~

Đoạn trên minh họa **anti-pattern**, không phải API của `VaultTemplate`. Nếu có hai luồng chạy đồng thời, request có thể dùng sai token. Thiết kế đúng là **mỗi identity có provider/session/template riêng** hoặc một registry cố định có kiểm soát và không thay danh tính giữa các request.

## 8. Vòng đời token: nhiều client cần nhiều SessionManager phù hợp

Ở các ví dụ local, constructor `new VaultTemplate(endpoint, authentication)` dùng `TokenAuthentication` để cung cấp token có sẵn, **không phải giải pháp quản lý token dài hạn đầy đủ**. Trong production:

- Client Orders có thể login bằng **Kubernetes auth role orders-reader**.
- Client Reports có thể login bằng **AppRole reports-reader** hoặc danh tính cloud phù hợp.
- Mỗi client cần token và policy riêng.
- Việc renew, login lại và revoke token phải được xét **cho từng identity**, không chia sẻ manager khi identity khác nhau.

Bảng trách nhiệm:

| Vấn đề | Orders client | Reports client |
| --- | --- | --- |
| Auth method | Ví dụ Kubernetes | Ví dụ AppRole |
| Credential nguồn | JWT của Orders ServiceAccount | RoleID/SecretID của Reports workload |
| Vault token | Token cấp cho Orders | Token cấp cho Reports |
| `SessionManager` | Instance riêng | Instance riêng |
| TTL/renew/revoke | Theo auth role Orders | Theo auth role Reports |
| Policy | Orders KV/Transit theo nhu cầu | Reports KV/PKI theo nhu cầu |

`SessionManager` là abstraction cung cấp Vault token cho request. `LifecycleAwareSessionManager` có thể quản lý refresh/renew trong điều kiện token và auth method cho phép; `SimpleSessionManager` đơn giản hơn và không tự gia hạn token. Đối với hai identity, cần các manager/renewal state **riêng**, dù scheduler thread pool có thể được chia sẻ với cơ chế lifecycle rõ ràng.

### Tùy biến constructor khi cần SessionManager

Ở Spring Vault 3.2/4.0, một overload thường dùng là:

~~~java
new VaultTemplate(endpoint, requestFactory, sessionManager);
~~~

Trong đó `requestFactory` là `ClientHttpRequestFactory`, và `sessionManager` được tạo cho identity cụ thể. Từ Spring Vault 4.1 có thể dùng:

~~~java
VaultClient client = VaultClient.create(endpoint);
VaultTemplate template = new VaultTemplate(client, sessionManager);
~~~

`VaultClient` ở đây thuộc Spring Vault **4.1 trở lên**. Hai đoạn chỉ minh họa **constructor hợp lệ trong phiên bản tương ứng**, không phải code hoàn chỉnh để copy vào cùng một dự án. Không dùng `VaultClient` trong nhánh Spring Vault chưa hỗ trợ.

Nếu dùng Spring Vault 4.1+ với hai đích cần timeout, trust store hoặc proxy khác nhau, tạo **hai `VaultClient`** qua builder và truyền đúng `SessionManager` tương ứng. Nếu sử dụng 3.x, tạo hai HTTP request factory khi cấu hình TLS khác biệt, thay vì bắt cả hai template dùng một factory sai CA.

### Token và secret lease là hai vòng đời khác nhau

- Token có TTL/policy và quyết định **request được phép làm gì**.
- Dynamic database credential có thể có `lease_id`, `lease_duration` và cần renew/revoke riêng.
- Một lần đọc **KV tĩnh** thường không sinh secret lease riêng.
- `SecretLeaseContainer` hoặc cơ chế quản lý lease của ứng dụng theo dõi các secret động được đăng ký, không tự động phân quyền chúng theo tên bean `VaultTemplate`.

Nếu cả Orders và Reports dùng dynamic secrets, cần bảo đảm lease container/logic của mỗi nhóm sử dụng đúng client, session và callback rotation. Không được dùng một token để gia hạn lease thuộc ranh giới mà token đó không được cấp quyền.

## 9. TLS, namespace và Vault HA theo từng đích

Với nhiều Vault server, không chỉ địa chỉ mà cả hạ tầng HTTP có thể khác nhau:

| Khía cạnh | Orders | Reports | Rủi ro nếu dùng chung sai |
| --- | --- | --- | --- |
| URI | `https://vault-orders.internal:8200` | `https://vault-reports.internal:8200` | Gửi request tới sai cụm |
| CA/trust store | CA Orders | CA Reports | TLS handshake lỗi |
| mTLS | Chứng chỉ client Orders nếu cần | Chứng chỉ client Reports nếu cần | Xác thực bằng certificate sai |
| Auth mount/role | Role Orders | Role Reports | Login không hợp lệ |
| Namespace | Ví dụ `orders` | Ví dụ `reports` | Tìm mount sai hoặc áp nhầm policy |
| Timeout/proxy | Theo SLO Orders | Theo SLO Reports | Gây chậm hoặc failover sai |
| HA routing | LB/Service Orders | LB/Service Reports | Mất kết nối khi active node thay đổi |

Ở staging/production, dùng HTTPS và **không tắt xác minh hostname/certificate**. `VaultEndpoint` không tự chứa CA trust store, mTLS certificate hoặc proxy. Những thành phần này nằm ở HTTP client/request factory và cấu hình triển khai.

Với Vault Enterprise namespace, namespace là ngữ cảnh request, **không phải phần secret path tự nối vào endpoint**. Khi tạo hai client cho hai namespace, thiết kế namespace và role gắn với policy tương ứng, đồng thời kiểm thử path thật.

Trong Kubernetes/Docker, `127.0.0.1` thường chỉ chính container hoặc Pod, không đại diện cho một Vault Service khác. Dùng DNS Service/ingress/load balancer phù hợp với hạ tầng và chứng chỉ TLS. Đối với Vault HA, tránh hardcode IP node active; lựa chọn điểm truy cập ổn định và cơ chế failover đã được vận hành.

## 10. Nếu dùng AbstractVaultConfiguration hoặc EnvironmentVaultConfiguration?

`AbstractVaultConfiguration` và `EnvironmentVaultConfiguration` tiện lợi khi tạo **một bộ hạ tầng Vault chính**. Nhưng với hai client/danh tính khác nhau, việc tạo hai subclass `AbstractVaultConfiguration` mà không xem xét các tên bean mặc định có thể gây xung đột `vaultTemplate`, `sessionManager`, scheduler hoặc các bean infrastructure khác.

Lựa chọn:

| Kiến trúc | Cách làm phù hợp |
| --- | --- |
| Một đích/danh tính đơn giản | Dùng `AbstractVaultConfiguration` hoặc `EnvironmentVaultConfiguration` |
| Hai đích độc lập | Định nghĩa `@Bean VaultTemplate` có tên rõ như ví dụ |
| Một đích, hai identity/policy | Hai bean template + auth/session riêng, cùng endpoint nếu cần |
| Cần properties riêng theo target | Prefix `app.vault.orders.*`, `app.vault.reports.*` do ứng dụng định nghĩa |
| Nhiều đích có lifecycle phức tạp | Quản lý từng cấu hình hạ tầng, bean names, qualifiers, scheduler/session và teardown rõ |
| Có Spring Cloud Vault Config | Đối chiếu auto-config đang có, tránh đăng ký bean chồng chéo |

**Không giả định** `@Import(EnvironmentVaultConfiguration.class)` hai lần cùng cấu hình khác nhau sẽ tự tạo hai template độc lập. Lớp đó đọc một nhóm `vault.*` trong `Environment`; nếu cần nhiều bộ properties, cấu hình bean riêng hoặc thiết kế factory rõ ràng sẽ dễ kiểm soát hơn.

Trong Spring Boot, một module chung có thể cung cấp factory `VaultTemplate` để tái sử dụng, nhưng mọi consumer phải khai báo danh tính/target cần dùng; đừng thêm `@Primary` chỉ để “chữa” injection ambiguous mà không xác định ranh giới quyền.

## 11. Kiểm thử khởi tạo hai bean mà không cần Vault thật

`ApplicationContextRunner` từ `spring-boot-test` có thể xác minh hai bean được tạo đúng tên và không phải cùng một instance. Đây là test **cấu hình Spring context**, chưa chứng minh Vault thực tế có quyền.

~~~java
package com.example.vault;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.vault.core.VaultTemplate;

import static org.assertj.core.api.Assertions.assertThat;

class MultiVaultConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(MultiVaultConfiguration.class);

    @Test
    void createsTwoDistinctVaultTemplates() {
        runner.withPropertyValues(
                "app.vault.orders.uri=http://127.0.0.1:8200",
                "app.vault.orders.token=orders-test-token",
                "app.vault.reports.uri=http://127.0.0.1:8300",
                "app.vault.reports.token=reports-test-token")
                .run(context -> {
                    assertThat(context).hasBean("ordersVaultTemplate");
                    assertThat(context).hasBean("reportsVaultTemplate");

                    VaultTemplate orders = context.getBean(
                            "ordersVaultTemplate", VaultTemplate.class);
                    VaultTemplate reports = context.getBean(
                            "reportsVaultTemplate", VaultTemplate.class);

                    assertThat(orders).isNotSameAs(reports);
                });
    }

    @Test
    void missingReportsTokenFailsFast() {
        runner.withPropertyValues(
                "app.vault.orders.uri=http://127.0.0.1:8200",
                "app.vault.orders.token=orders-test-token",
                "app.vault.reports.uri=http://127.0.0.1:8300")
                .run(context -> assertThat(context).hasFailed());
    }
}
~~~

Ở đây `ApplicationContextRunner` nạp cấu hình với token giả. Vì test không gửi request mạng, nó xác minh **số lượng, tên và lifecycle khởi tạo bean**, không chứng minh endpoint đang nghe, TLS hay policy hoạt động.

### Test qualifier của service

Một test context khác nên nạp thêm `MultiVaultSecretReader` và xác nhận service được khởi tạo với cả hai dependency. Nếu bỏ `@Qualifier` khỏi constructor, phải quan sát context bị lỗi ambiguous bean trong cấu hình không có `@Primary`. Với request thực, cần kiểm tra mỗi phương thức đọc đúng Vault.

## 12. Kiểm thử tích hợp: thành công và cách ly thất bại

Với hai Vault test instance hoặc Testcontainers, hãy thiết kế ma trận:

| Kịch bản | Kết quả cần quan sát |
| --- | --- |
| Orders client -> Orders Vault -> `secret/orders/app` | Đọc thành công bằng identity Orders |
| Reports client -> Reports Vault -> `secret/reports/app` | Đọc thành công bằng identity Reports |
| Đổi sai endpoint trong property Orders | Startup/request thất bại rõ, không tự fallback sang Reports |
| Đổi sai token Reports | Chỉ đường Reports thất bại; Orders không bị thay token |
| Server Reports tạm ngừng | Đánh giá tình huống degraded mode, timeout và retry có giới hạn |
| URI có `/v1/secret` | Validation của bean từ chối |
| Thiếu `ORDERS_VAULT_TOKEN` hoặc `REPORTS_VAULT_TOKEN` | Cấu hình thất bại sớm, không tạo root token mặc định |
| Cùng Vault, identity Orders đọc secret Reports | **403/permission denied**, chứng minh policy isolation |
| Cùng Vault, identity Reports đọc secret Orders | **403/permission denied** |
| KV v1/v2 không khớp | Lỗi path/404/null, không tự coi là secret rỗng hợp lệ |
| Token hết TTL/bị revoke | Manager xử lý theo auth method/lifecycle, không đổi token của client kia |
| HTTPS với CA sai của một Vault | Client tương ứng lỗi TLS; không hạ xuống HTTP |
| Hai client có session/lease riêng | Renew/revoke/rotation không trộn state hoặc credential |
| App shutdown | Scheduler/session/HTTP resources của cả hai client được đóng phù hợp |

Để kiểm tra policy, **không sử dụng root token**: root token thường có quyền đủ rộng và làm phép thử “truy cập chéo phải bị chặn” mất giá trị. Có thể tạo token có policy giới hạn hoặc dùng workload auth role của từng nhóm.

### Tình huống ít được chú ý: cùng tên secret, khác Vault

Nếu cả hai server có `secret/config/app` nhưng chứa **giá trị khác nhau**, bạn cần chắc chắn client A nhận kết quả A và client B nhận kết quả B. Chỉ kiểm tra dữ liệu “không rỗng” chưa chứng minh không lẫn endpoint. Test tích hợp nên dùng dữ liệu mẫu **khác nhau, không nhạy cảm**, rồi assert đúng giá trị từ từng đích.

## 13. Lỗi thường gặp khi có nhiều VaultTemplate

| Triệu chứng | Nguyên nhân có khả năng | Cách xử lý |
| --- | --- | --- |
| `NoUniqueBeanDefinitionException` cho `VaultTemplate`/`VaultOperations` | Hai bean cùng kiểu, injection thiếu qualifier | Thêm `@Qualifier` đúng tên hoặc thiết kế interface riêng |
| Một service đọc nhầm Vault | Qualifier bị gán sai hoặc code dùng default bean | Kiểm tra bean names và test dữ liệu cách ly |
| Reports dùng token Orders | Dùng chung auth/session hoặc nhầm property | Mỗi identity cần credential/session độc lập |
| Lỗi thiếu property khi khởi động | Một `ORDERS_*`/`REPORTS_*` chưa được cấp | Kiểm tra env vars process và profile |
| HTTP 401/403 | Token sai, hết hạn hoặc policy không đủ | Xác minh identity thật và path policy |
| HTTP 404/null | Sai mount, KV version, secret path hoặc namespace | Kiểm tra từng target và engine cụ thể |
| `SSLHandshakeException` chỉ ở một client | CA/trust store hoặc hostname của target đó khác | Cấu hình TLS riêng, không tắt validation |
| Timeout chỉ ở một target | Network/proxy/Vault node của target đó không sẵn sàng | Quan sát SLO và timeout theo client |
| Failover làm một client mất kết nối | Endpoint node tĩnh hoặc LB/HTTP stack chưa phù hợp | Dùng DNS/LB ổn định, kiểm tra HA |
| Token Orders bị revoke làm cả hai client lỗi | Có thể đang dùng chung token/session sai | Tách identity và kiểm thử revoke độc lập |
| Tạo quá nhiều bean/scheduler lúc runtime | Tạo client mỗi request/tenant không giới hạn | Dùng registry bounded và lifecycle rõ |
| Trùng bean `vaultTemplate` | Kết hợp config thủ công với auto-config không kiểm soát | Chọn một nguồn hạ tầng hoặc qualifier |
| Token rotation không có tác dụng | `TokenAuthentication` giữ token cũ | Sử dụng auth/session lifecycle hoặc redeploy có kiểm soát |

**Khoanh vùng theo từng client.** Sự cố phía Reports không nhất thiết nghĩa là endpoint Orders sai; log, metric và traces nên có tên client **không nhạy cảm** (ví dụ `orders` hoặc `reports`), nhưng không chứa token, SecretID, JWT hay nội dung secret.

## 14. Vận hành, giám sát và an toàn khi có nhiều client

Trong production, mỗi client nên có bảng thông tin cấu hình và trách nhiệm riêng:

| Nội dung | Điều cần quyết định |
| --- | --- |
| Nguồn cấu hình | URI và auth method của từng đích được cấp từ đâu? |
| Danh tính workload | Kubernetes/AppRole/cloud identity nào thực hiện login? |
| Vault policy | API/path nào được cấp `read`, `write`, Transit hoặc PKI? |
| Token lifecycle | Ai renew/login lại, TTL tối đa là bao nhiêu, khi nào revoke? |
| Lease lifecycle | Dynamic secret nào cần theo dõi, cập nhật credential ở đâu? |
| HTTP & TLS | Trust store, mTLS, proxy, timeout và retry của từng client |
| Failure isolation | Một Vault bị gián đoạn có làm dừng toàn service không? |
| Giám sát | Latency, tỷ lệ lỗi 4xx/5xx, auth failures, token renew errors |
| Security logging | Có vô tình xuất secret, token hoặc thông tin nhạy cảm không? |

Nên quan sát riêng từng đích: số lần request thành công, lỗi network/TLS, 401/403, thời gian login/renew và sự kiện failover. Khi giám sát, có thể dùng nhãn `target=orders` hoặc `target=reports` nhưng tránh gắn secret path đầy đủ nếu nó nhạy cảm; tuyệt đối không đưa Vault token, private key PKI, Transit key material hay dữ liệu KV vào metric labels hoặc log.

**Không dùng một danh tính “siêu quyền” chỉ để tránh phải tạo hai client.** Hệ thống hai client đúng cách có thể giảm phạm vi ảnh hưởng khi một workload token bị lộ hoặc một chức năng gặp lỗi.

### Nhiều tenant có nên tạo một VaultTemplate mỗi request?

Không nên mặc định làm vậy. Với tenant động, cần registry theo định danh tenant được whitelist/authorize, giới hạn số client tồn tại, timeout và cơ chế đóng tài nguyên. User input không được trực tiếp quyết định URL Vault, namespace hoặc token để tạo kết nối tùy ý. Nếu cần client theo tenant, phải quản lý **cache key, lifecycle, policy và isolation** rõ ràng, tránh rò rỉ token giữa tenant hoặc nguy cơ SSRF do endpoint tùy ý.

## 15. Tổng kết và câu hỏi tự luyện

Một ứng dụng Spring Vault có thể có **nhiều bean `VaultTemplate`**, miễn mỗi bean biểu diễn một đích hoặc danh tính có tên rõ ràng. Sử dụng `@Qualifier` tại điểm inject để không nhầm ngữ cảnh. Với xác thực theo workload và token có TTL, mỗi identity còn cần session/renewal logic phù hợp; việc tạo thêm bean không tự giải quyết token lifecycle.

Hãy tự trả lời:

1. Khi nào nên có hai `VaultTemplate`, khi nào một template đã đủ dùng cho KV, Transit và PKI?
2. Hai bean cùng kiểu `VaultOperations` nhưng không có `@Qualifier` sẽ gây vấn đề gì?
3. Vì sao `@Primary` không phải lúc nào cũng an toàn trong một kiến trúc có nhiều identity?
4. Cùng một Vault endpoint nhưng hai policy khác nhau có cần hai `ClientAuthentication` riêng không?
5. Nếu Reports token bị revoke, vì sao Orders client không nên bị đổi token theo?
6. Với KV v2, policy Orders nên cấp trên `secret/orders/*` hay `secret/data/orders/*`?
7. Tại sao test bằng root token chưa đủ để xác minh policy isolation?
8. Khi dùng Spring Vault 4.1, `VaultClient` có thể giúp tùy chỉnh HTTP client của từng đích như thế nào?
9. `SessionManager` và `SecretLeaseContainer` quản lý hai vòng đời nào khác nhau?
10. Có nên khởi tạo một `VaultTemplate` mới cho mỗi HTTP request dựa trên URL do người dùng gửi không? Vì sao?
11. Cần theo dõi chỉ số gì để biết chỉ Vault Reports đang bị timeout mà Vault Orders vẫn bình thường?
12. Vì sao cùng tên secret trên hai Vault cần test dữ liệu khác nhau để phát hiện nhầm endpoint?

**Kết quả mong đợi:** bạn tạo được **hai `VaultTemplate` độc lập**, inject chúng qua `@Qualifier`, xác minh đọc KV v2 ở đúng đích, và chứng minh quyền truy cập chéo bị chặn khi hai danh tính dùng chung Vault. Từ nền tảng này, bạn có thể triển khai ranh giới auth và policy phù hợp cho các tác vụ Transit encryption, PKI, quản lý token/lease, xử lý lỗi, giám sát và kiểm thử tích hợp trong **SPRING_VAULT**.

### Tài liệu tham khảo

- [Spring Vault Reference: VaultTemplate và VaultOperations](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
- [Spring Vault Reference: Authentication](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault Javadoc: VaultTemplate](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/core/VaultTemplate.html)
- [Spring Framework: Using @Qualifier](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [HashiCorp Vault: KV v2](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2)

