# EnvironmentVaultConfiguration và nhóm thuộc tính vault.*

Trong module **SPRING_VAULT**, ứng dụng Java cần xác định địa chỉ HashiCorp Vault, cơ chế xác thực của workload và cấu hình TLS trước khi dùng `VaultTemplate` đọc KV secrets hoặc thực hiện các thao tác Transit encryption, PKI, token và lease. Ở chương **Cấu hình Java**, cách viết một lớp `AbstractVaultConfiguration` và tự triển khai `vaultEndpoint()`, `clientAuthentication()` mang lại sự chủ động; nhưng nhiều ứng dụng chỉ cần thay đổi các giá trị cấu hình theo môi trường.

`EnvironmentVaultConfiguration` giải quyết tình huống đó: đây là lớp cấu hình có sẵn trong **Spring Vault**, sử dụng `Environment` và những khóa thuộc tính chuẩn bắt đầu bằng **`vault.*`** để dựng các thành phần Vault. Thay vì viết code Java riêng cho mỗi phương thức xác thực, ta có thể cấp endpoint, TLS và credential bằng những `PropertySource` đã có của Spring.

**Mục tiêu bài học:** import được `EnvironmentVaultConfiguration`, hiểu đúng các nhóm `vault.uri`, `vault.authentication`, `vault.token`, `vault.app-role.*`, `vault.kubernetes.*` và `vault.ssl.*`; kiểm tra bằng một lần đọc KV v2; biết khi nào cần quay lại cấu hình Java tùy chỉnh và phân biệt các khóa này với cấu hình **Spring Cloud Vault**.

## 1. EnvironmentVaultConfiguration là gì?

`org.springframework.vault.config.EnvironmentVaultConfiguration` là một lớp được đánh dấu `@Configuration`, **kế thừa `AbstractVaultConfiguration`** và triển khai `ApplicationContextAware`. Nó đọc thuộc tính từ `Environment` của Spring để xác định:

- **Vault endpoint:** server mà ứng dụng kết nối tới.
- **SSL/TLS:** key store, trust store, kiểu store, protocol và cipher suite khi cần.
- **Authentication:** chọn phương thức lấy Vault token.
- **Thông số riêng của auth method:** token có sẵn, AppRole RoleID/SecretID, Kubernetes role và đường dẫn ServiceAccount JWT, hoặc các lựa chọn khác được phiên bản thư viện hỗ trợ.

Lớp này tận dụng hạ tầng của `AbstractVaultConfiguration` để đăng ký `VaultTemplate` và các thành phần liên quan. Bạn thường **import lớp có sẵn**, không cần tự subclass nó chỉ để đặt `vault.uri` hay `vault.token`.

~~~mermaid
flowchart LR
    A["Spring Environment<br/>application.yml, env vars,<br/>system properties"] --> B["EnvironmentVaultConfiguration"]
    B --> C["VaultEndpoint<br/>vault.uri"]
    B --> D["ClientAuthentication<br/>vault.authentication + options"]
    B --> E["TLS configuration<br/>vault.ssl.*"]
    C --> F["VaultTemplate + SessionManager"]
    D --> F
    E --> F
    F --> G["KV v2 / Transit / PKI"]
~~~

`Environment` kết hợp nhiều nguồn giá trị với quy tắc ưu tiên của Spring. Ví dụ, một ứng dụng có thể dùng `application-local.yml` ở máy phát triển, còn production được cấp giá trị qua biến môi trường hoặc hệ thống cấu hình triển khai. **Không có nghĩa Vault tự cấp quyền dựa vào tên thuộc tính**: Vault policy vẫn quyết định token được phép truy cập API path nào.

### So sánh với cấu hình Java thủ công

| Cách làm | Ứng dụng cần khai báo | Phù hợp khi |
| --- | --- | --- |
| `AbstractVaultConfiguration` | Tự override `vaultEndpoint()` và `clientAuthentication()`, tùy chỉnh nếu cần | Muốn kiểm soát cơ chế xây client hoặc xác thực đặc biệt |
| `EnvironmentVaultConfiguration` | `@Import` và các khóa `vault.*` từ `Environment` | Auth method thuộc danh sách hỗ trợ, cấu hình thông dụng |
| Tự tạo `@Bean VaultTemplate` | Endpoint/client/auth/session tùy thiết kế | Có tích hợp HTTP hoặc nhiều client Vault rất riêng |
| Spring Cloud Vault Config | Starter, `spring.cloud.vault.*` và cơ chế nạp property sources | Muốn tích hợp Vault secrets vào cấu hình ứng dụng qua Spring Cloud |

**Chỉ chọn một nguồn tạo hạ tầng chính** trong ví dụ thực hành. Import đồng thời `EnvironmentVaultConfiguration`, một lớp `AbstractVaultConfiguration` khác và auto-configuration Spring Cloud Vault có thể gây trùng bean hoặc khiến service inject nhầm `VaultTemplate`.

## 2. Các khóa vault.* quan trọng nhất

Những khóa sau do **`EnvironmentVaultConfiguration`** đọc, không phải khóa tùy ý do bài học đặt tên:

| Khóa | Ví dụ | Tác dụng |
| --- | --- | --- |
| `vault.uri` | `https://vault.internal:8200` | URL gốc của Vault server |
| `vault.authentication` | `TOKEN`, `APPROLE`, `KUBERNETES` | Chọn auth method; mặc định `TOKEN` nếu không chỉ định |
| `vault.token` | Giá trị cấp tại runtime | Token có sẵn cho `TOKEN`; cũng dùng trong trường hợp `CUBBYHOLE` |
| `vault.ssl.trust-store` | `file:/etc/vault/ca-truststore.jks` | Nguồn trust store khi dùng CA được quản lý riêng |
| `vault.ssl.trust-store-password` | Biến môi trường được inject | Mật khẩu mở trust store nếu cần |
| `vault.ssl.trust-store-type` | `jks` | Loại trust store (ví dụ JKS; phụ thuộc API/định dạng hỗ trợ) |
| `vault.ssl.key-store` | `file:/etc/vault/client-keystore.jks` | Key store cho client certificate nếu cần |
| `vault.ssl.key-store-password` | Giá trị cấp tại runtime | Mật khẩu key store |
| `vault.ssl.key-store-type` | `jks` | Loại key store |
| `vault.ssl.enabled-protocols` | `TLSv1.3,TLSv1.2` | Danh sách giao thức TLS được cho phép |
| `vault.ssl.enabled-cipher-suites` | Tên cipher suites cụ thể | Giới hạn cipher suite khi chính sách vận hành yêu cầu |

**Chú ý:** `vault.uri` là URL của **server**, không phải `/v1/secret/data/...`. Trong `VaultTemplate`, đường dẫn mount và secret sẽ được truyền ở thao tác nghiệp vụ.

`vault.authentication` phải là một giá trị mà **phiên bản đang chạy** nhận diện. Các lựa chọn phổ biến trong Spring Vault 4.1 gồm `TOKEN`, `APPROLE`, `AWS_EC2`, `AWS_IAM`, `AZURE`, `CERT`, `CUBBYHOLE` và `KUBERNETES`. Những release cũ có thể liệt kê thêm `APPID`; không nên sao chép một giá trị từ tài liệu phiên bản khác mà không kiểm tra.

### Phân biệt vault.* với VAULT_ADDR/VAULT_TOKEN

HashiCorp Vault CLI thường đọc `VAULT_ADDR` và `VAULT_TOKEN`. Nhưng **`vault.uri` và `vault.token` mới là hai khóa mà `EnvironmentVaultConfiguration` mong đợi**. Không nên giả định `VAULT_ADDR` tự động biến thành `vault.uri`.

Trong Spring Boot, có thể ánh xạ tường minh:

~~~yaml
vault:
  uri: ${VAULT_ADDR}
  authentication: TOKEN
  token: ${VAULT_TOKEN}
~~~

Khi Spring Boot nạp `application.yml`, các placeholder `${VAULT_ADDR}` và `${VAULT_TOKEN}` lấy giá trị từ môi trường chạy. Đây là **cầu nối do ứng dụng khai báo**, không phải tự động chuyển đổi tên biến đặc biệt của HashiCorp CLI.

## 3. Import cấu hình có sẵn vào ứng dụng Java

Đối với ứng dụng Spring Boot, có thể đặt `@Import(EnvironmentVaultConfiguration.class)` trực tiếp trên lớp chính:

~~~java
package com.example.vault;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;
import org.springframework.vault.config.EnvironmentVaultConfiguration;

@SpringBootApplication
@Import(EnvironmentVaultConfiguration.class)
public class VaultLearningApplication {

    public static void main(String[] args) {
        SpringApplication.run(VaultLearningApplication.class, args);
    }
}
~~~

Đây là toàn bộ phần Java cần thiết để **nạp cấu hình Vault có sẵn**. Sau đó, code service có thể inject `VaultTemplate` hoặc interface `VaultOperations` để gọi API Vault. Không cần viết lại `vaultEndpoint()` và `clientAuthentication()`.

Trong một ứng dụng Spring Framework không sử dụng cơ chế tải `application.yml` của Spring Boot, có thể đăng ký `PropertySource` dạng properties theo mẫu:

~~~java
package com.example.vault;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.PropertySource;
import org.springframework.vault.config.EnvironmentVaultConfiguration;

@Configuration
@PropertySource("classpath:vault.properties")
@Import(EnvironmentVaultConfiguration.class)
public class VaultImportConfiguration {
}
~~~

Và file `vault.properties` tương ứng:

~~~properties
vault.uri=https://vault.internal:8200
vault.authentication=TOKEN
vault.token=placeholder-for-local-demo
~~~

Mẫu `@PropertySource` dành cho trường hợp **bạn chủ động dùng một file properties**. Trong Spring Boot, `application.yml` hoặc `application.properties` đã được nạp theo cơ chế chuẩn, nên không cần `@PropertySource` chỉ để tải chúng. Đồng thời, `@PropertySource` chuẩn **không tự giải mã YAML** nếu không có factory phù hợp.

Không commit một `vault.properties` chứa token thật. Token demo trong mẫu chỉ là chuỗi mô tả, không phải credential hoạt động.

### Dependency

Ví dụ sử dụng thư viện Spring Vault cốt lõi:

~~~xml
<dependency>
    <groupId>org.springframework.vault</groupId>
    <artifactId>spring-vault-core</artifactId>
</dependency>
~~~

Đây là dependency không có `<version>` vì ví dụ giả định dự án đã quản lý phiên bản tương thích bằng BOM hoặc `dependencyManagement`. Nếu không, phải khai báo phiên bản phù hợp với Spring Framework/Spring Boot của dự án. Mã Java trong bài dùng Java 17 trở lên và các thành phần Spring Boot.

## 4. Cấu hình token cho local: ví dụ chạy được

Bắt đầu từ trường hợp đơn giản nhất để quan sát được cấu hình hoạt động. **Token tĩnh chỉ phục vụ lab**, không phải lựa chọn mặc định cho production.

### 4.1. Bật Vault dev server

Trong terminal thứ nhất:

~~~bash
vault server -dev -dev-root-token-id=dev-only-token
~~~

Trong terminal thứ hai (Bash):

~~~bash
export SPRING_PROFILES_ACTIVE=local
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=dev-only-token

vault kv put secret/demo/app apiKey=demo-key
vault kv get secret/demo/app
~~~

Với PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:VAULT_ADDR = "http://127.0.0.1:8200"
$env:VAULT_TOKEN = "dev-only-token"

vault kv put secret/demo/app apiKey=demo-key
vault kv get secret/demo/app
~~~

Vault dev server thường gắn mount `secret` kiểu KV v2; nếu môi trường thực hành đã được thay đổi, kiểm tra bằng `vault secrets list -detailed`. Tạo secret trước khi chạy ứng dụng sẽ giúp phân biệt lỗi “secret không tồn tại” và lỗi khởi tạo kết nối.

### 4.2. File application-local.yml

Trong `src/main/resources/application-local.yml`:

~~~yaml
vault:
  uri: ${VAULT_ADDR:http://127.0.0.1:8200}
  authentication: TOKEN
  token: ${VAULT_TOKEN}
~~~

Khi profile `local` được kích hoạt, Spring Boot đọc các khóa `vault.*` này vào `Environment`. `EnvironmentVaultConfiguration` dùng chúng để dựng endpoint và `TokenAuthentication`.

**Vì sao fallback chỉ nằm ở local?** Địa chỉ `http://127.0.0.1:8200` trỏ tới Vault dev server trên cùng máy. Nếu để fallback HTTP ở production, một deployment thiếu `VAULT_ADDR` có thể âm thầm kết nối sai đích. Ở staging/production, nên bắt buộc cấu hình endpoint TLS có chứng chỉ được xác minh.

`vault.token: ${VAULT_TOKEN}` buộc token phải được cấp tại runtime. Khi chuyển sang authentication theo workload, **không giữ lại token demo** hoặc đặt `vault.authentication` mặc định là `TOKEN` một cách vô ý.

## 5. Đọc KV v2 bằng VaultTemplate được tạo từ EnvironmentVaultConfiguration

Tạo `DemoSecretReader.java` trong package được Spring Boot component scan:

~~~java
package com.example.vault;

import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class DemoSecretReader {

    private final VaultOperations vault;

    public DemoSecretReader(VaultOperations vault) {
        this.vault = vault;
    }

    public boolean canReadSampleSecret() {
        VaultResponse response = vault
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("demo/app");

        Map<String, Object> data =
                response == null ? null : response.getData();

        return data != null
                && data.get("apiKey") instanceof String apiKey
                && !apiKey.isBlank();
    }
}
~~~

Bean `VaultTemplate` do hạ tầng import vào quản lý triển khai `VaultOperations`, nên service chỉ cần inject interface. `"secret"` là mount, còn `"demo/app"` là path tương đối bên trong mount. Spring Vault tạo request HTTP KV v2 tương ứng với `GET /v1/secret/data/demo/app`; không thêm `data/` vào tham số `get(...)`.

Có thể thêm bean kiểm tra vào lớp `VaultLearningApplication`:

~~~java
@Bean
CommandLineRunner checkVault(DemoSecretReader reader) {
    return args -> {
        if (!reader.canReadSampleSecret()) {
            throw new IllegalStateException(
                    "Secret KV v2 chưa có dữ liệu mẫu hợp lệ");
        }
        System.out.println("Đã đọc được KV v2 qua EnvironmentVaultConfiguration");
    };
}
~~~

Đoạn trên là **phương thức nằm bên trong lớp `@SpringBootApplication`**, cần hai import:

~~~java
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
~~~

Kết quả mong đợi khi chạy với Vault dev và token đúng:

~~~text
Đã đọc được KV v2 qua EnvironmentVaultConfiguration
~~~

Không in token, `apiKey` hoặc toàn bộ `VaultResponse` vào log. Một phép đọc thành công chỉ xác minh kết nối, xác thực, policy và dữ liệu **tại thời điểm chạy**, không chứng minh token sẽ tồn tại vô hạn hoặc cơ chế Vault HA đã sẵn sàng.

## 6. Chuyển sang AppRole bằng các thuộc tính vault.app-role.*

AppRole phù hợp với những workload có thể nhận **RoleID** và **SecretID** qua kênh phân phối credential được kiểm soát. Thay vì đưa một Vault token dài hạn vào ứng dụng, workload dùng hai giá trị đầu vào để **login và xin Vault token**.

### 6.1. Các khóa cấu hình AppRole

| Khóa | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `vault.authentication` | `APPROLE` | Chọn AppRole auth |
| `vault.app-role.app-role-path` | `approle` | Tên auth mount trong Vault; mặc định thường là `approle` |
| `vault.app-role.role-id` | Giá trị được cấp tại runtime | RoleID của Vault AppRole |
| `vault.app-role.secret-id` | Giá trị được cấp tại runtime | SecretID khi role yêu cầu; field optional theo API |

Ví dụ `src/main/resources/application-approle.yml`:

~~~yaml
vault:
  uri: ${VAULT_ADDR}
  authentication: APPROLE
  app-role:
    app-role-path: ${VAULT_APPROLE_PATH:approle}
    role-id: ${VAULT_ROLE_ID}
    secret-id: ${VAULT_SECRET_ID}
~~~

Những `VAULT_*` trong placeholder là **quy ước biến môi trường ví dụ**; `EnvironmentVaultConfiguration` đọc kết quả theo tên `vault.app-role.*`. SecretID phải được cấp an toàn, không lưu trong Git hay in lên stdout.

### 6.2. Những gì cần được cấu hình ở phía Vault

Ứng dụng không tự tạo AppRole từ file YAML. Quản trị viên Vault cần bật đúng auth method, tạo role, gán policy và thiết lập các giới hạn token/SecretID.

Luồng logic:

~~~mermaid
sequenceDiagram
    participant Deploy as Nền tảng triển khai
    participant App as Ứng dụng Java
    participant Vault as Vault AppRole
    Deploy-->>App: RoleID, SecretID được cấp an toàn
    App->>Vault: auth/approle/login
    Vault-->>App: Vault token có TTL và policy
    App->>Vault: Đọc KV v2 bằng token
    Vault-->>App: Secret hoặc lỗi permission
~~~

Nếu một role được thiết lập để **không dùng SecretID**, property `vault.app-role.secret-id` có thể không cần thiết, nhưng phải phù hợp policy vận hành của tổ chức; đừng bỏ SecretID để “sửa lỗi login” khi role thực tế yêu cầu nó. Hãy cân nhắc giới hạn số lần sử dụng, TTL, response wrapping và rotation đối với SecretID.

**Điểm mạnh khi dùng `EnvironmentVaultConfiguration`:** Java service ở mục 5 không đổi. Bạn thay cấu hình và bảo đảm Vault auth backend cấp đúng token. Service vẫn dùng `VaultOperations`.

## 7. Chuyển sang Kubernetes authentication bằng vault.kubernetes.*

Khi ứng dụng Java chạy trong Kubernetes, cách xác thực phổ biến là dùng **ServiceAccount JWT** của Pod để login Vault. Workload không cần nhận một Vault token tĩnh trong file cấu hình.

### 7.1. Các khóa Kubernetes

| Khóa | Ví dụ | Vai trò |
| --- | --- | --- |
| `vault.authentication` | `KUBERNETES` | Chọn Kubernetes auth |
| `vault.kubernetes.kubernetes-path` | `kubernetes` | Auth mount của Kubernetes trong Vault |
| `vault.kubernetes.role` | `orders-reader` | Vault role ràng buộc workload |
| `vault.kubernetes.service-account-token-file` | `/var/run/secrets/kubernetes.io/serviceaccount/token` | Đường dẫn file JWT được mount vào Pod |

Ví dụ `src/main/resources/application-kubernetes.yml`:

~~~yaml
vault:
  uri: ${VAULT_ADDR}
  authentication: KUBERNETES
  kubernetes:
    kubernetes-path: ${VAULT_K8S_AUTH_PATH:kubernetes}
    role: ${VAULT_K8S_ROLE}
    service-account-token-file: ${VAULT_K8S_JWT_FILE:/var/run/secrets/kubernetes.io/serviceaccount/token}
~~~

Bật profile `kubernetes` và cấp `VAULT_ADDR` là HTTPS URL có chứng chỉ đáng tin cậy đối với Pod. Role ở Vault cần bind đúng ServiceAccount, namespace và khi yêu cầu cả audience/issuer phù hợp với JWT; chúng **không được tự tạo bởi Java configuration**.

### 7.2. Luồng xác thực

~~~mermaid
sequenceDiagram
    participant Pod as Java Pod
    participant K8s as Kubernetes
    participant Vault as Vault Kubernetes Auth
    K8s-->>Pod: Projected ServiceAccount JWT
    Pod->>Vault: auth/kubernetes/login (role, jwt)
    Vault->>Vault: Kiểm tra token, namespace, role
    Vault-->>Pod: Vault token
    Pod->>Vault: KV/Transit/PKI theo policy
~~~

Các lỗi điển hình là file JWT không tồn tại, Pod không được mount token, ServiceAccount sai, namespace/role không khớp hoặc JWT có audience không được Vault chấp nhận. **Đổi `vault.uri` không sửa được sai cấu hình role**. Sau khi login, token vẫn phải có policy đọc đúng path.

## 8. Nhóm xác thực khác và giới hạn của cấu hình bằng thuộc tính

`EnvironmentVaultConfiguration` hỗ trợ các phương thức có sẵn theo release. Những nhóm thường gặp:

| Auth method | Khóa ví dụ | Bối cảnh |
| --- | --- | --- |
| `AWS_EC2` | `vault.aws-ec2.role`, `vault.aws-ec2.aws-ec2-path` | Danh tính EC2 và auth backend phía Vault |
| `AWS_IAM` | `vault.aws-iam.role` | Danh tính IAM của workload trên AWS |
| `AZURE` | `vault.azure-msi.role`, `vault.azure-msi.azure-path` | Managed identity ở Azure |
| `CERT` | Nhóm SSL key store/client certificate; không có khóa auth-specific riêng | Client certificate authentication |
| `CUBBYHOLE` | `vault.token` | Trường hợp có initial token và cubbyhole workflow |
| `APPROLE` | `vault.app-role.role-id`, `vault.app-role.secret-id` | Workload có kênh cấp RoleID/SecretID |
| `KUBERNETES` | `vault.kubernetes.role`, `vault.kubernetes.service-account-token-file` | Pod/ServiceAccount JWT |

Một số bản cũ còn mô tả `APPID`; hãy dùng danh sách enum của đúng phiên bản thư viện. **Không suy rằng bất kỳ auth method nào của Vault đều được cấu hình tự động bằng một giá trị `vault.authentication` bất kỳ.** Những phương thức không được lớp này hỗ trợ hoặc yêu cầu tích hợp đặc biệt có thể cần kế thừa `AbstractVaultConfiguration` và tự dựng `ClientAuthentication`.

Cũng không nên dùng auth method tương tác theo người dùng thay cho workload identity chỉ vì nó dễ thử trên laptop.

## 9. Cấu hình vault.ssl.* để kết nối HTTPS an toàn

Ở staging và production, nên dùng HTTPS với hostname khớp chứng chỉ. Khi Vault sử dụng CA riêng hoặc cần mTLS, `EnvironmentVaultConfiguration` có nhóm thuộc tính SSL/TLS để cung cấp store và lựa chọn giao thức.

Ví dụ trust store JKS:

~~~yaml
vault:
  uri: ${VAULT_ADDR}
  authentication: KUBERNETES
  kubernetes:
    role: ${VAULT_K8S_ROLE}
  ssl:
    trust-store: file:/etc/vault/ca-truststore.jks
    trust-store-type: jks
    trust-store-password: ${VAULT_TRUST_STORE_PASSWORD}
    enabled-protocols: TLSv1.3,TLSv1.2
~~~

File `/etc/vault/ca-truststore.jks` phải tồn tại trong **filesystem của container hoặc máy chạy Java**. Mật khẩu trust store do nền tảng triển khai cấp; không ghi trực tiếp vào repository.

Nếu cần xác thực bằng certificate của client, có thể thêm:

~~~yaml
vault:
  authentication: CERT
  ssl:
    key-store: file:/etc/vault/client-keystore.jks
    key-store-type: jks
    key-store-password: ${VAULT_KEY_STORE_PASSWORD}
    trust-store: file:/etc/vault/ca-truststore.jks
    trust-store-type: jks
    trust-store-password: ${VAULT_TRUST_STORE_PASSWORD}
~~~

Đây là **mảnh YAML minh họa các thuộc tính liên quan CERT**; vẫn cần `vault.uri` hợp lệ và cấu hình Vault cert auth backend tương ứng. `CERT` auth khác với việc chỉ **tin cậy certificate của Vault server**: một bên trình bày chứng chỉ client để xác thực, bên kia xác minh server để bảo vệ kết nối.

Một số nguyên tắc:

1. `vault.ssl.trust-store` dùng để tin cậy CA/server certificate, không cấp policy cho workload.
2. `vault.ssl.key-store` có thể chứa private key/certificate client, phải được bảo vệ cẩn thận.
3. `vault.ssl.enabled-protocols`/`enabled-cipher-suites` là lựa chọn tương thích với hạ tầng Vault; cấu hình sai có thể làm TLS handshake thất bại.
4. `vault.uri` dùng `https://` mới khởi tạo luồng TLS; không bật HTTP plaintext trong staging/prod để “chữa” lỗi chứng chỉ.
5. Có thể dùng trust store chuẩn của JVM nếu certificate chain đã đáng tin cậy; không phải môi trường nào cũng cần `vault.ssl.*` riêng.
6. Tên chuẩn là **`vault.ssl.trust-store-type`**; một số Javadoc cũ có lỗi đánh máy ở mô tả trường này, nên đối chiếu với Spring Vault Reference và API đúng phiên bản.

## 10. Phân biệt vault.* với spring.cloud.vault.*

Đây là lỗi cấu hình dễ gặp khi dự án vừa tham khảo **Spring Vault** vừa tham khảo **Spring Cloud Vault**.

| Đặc điểm | Spring Vault `EnvironmentVaultConfiguration` | Spring Cloud Vault Config |
| --- | --- | --- |
| Cấu hình endpoint | `vault.uri` | `spring.cloud.vault.uri` hoặc host/port/scheme |
| Authentication | `vault.authentication` | `spring.cloud.vault.authentication` theo starter/phiên bản |
| Token có sẵn | `vault.token` | `spring.cloud.vault.token` |
| Cơ chế kích hoạt | `@Import(EnvironmentVaultConfiguration.class)` | Auto-configuration/starter và cơ chế import cấu hình Cloud Vault |
| Mục đích chính | Tạo hạ tầng dùng `VaultTemplate` | Nạp Vault secrets làm nguồn cấu hình và tích hợp Boot |
| Kiểm soát vòng đời | Qua hạ tầng Spring Vault được tạo | Theo cơ chế auto-config và lifecycle của tích hợp đang dùng |

**Không thay `vault.*` bằng `spring.cloud.vault.*` trong ví dụ `@Import`** rồi cho rằng hai nhóm khóa tương đương. Tương tự, đặt `vault.uri` không đảm bảo Spring Cloud Vault sẽ đọc nó nếu starter đang tìm `spring.cloud.vault.uri`.

Nếu dự án đã dùng Spring Cloud Vault và `spring.config.import=vault://`, cần xem xét kỹ việc thêm `EnvironmentVaultConfiguration`: có thể xuất hiện bean `VaultTemplate` trùng hoặc hai cấu hình auth khác nhau. Khi dùng cả hai vì lý do đặc biệt, xác định rõ từng bean và qualifier thay vì đoán thứ tự ưu tiên.

## 11. Policy, token/session và lease vẫn phải được thiết kế riêng

Các thuộc tính `vault.*` giúp chọn endpoint và phương thức xác thực; **chúng không cấp quyền trong Vault**.

Với KV v2 ở mount `secret` và path `demo/app`, policy đọc tối thiểu:

~~~hcl
path "secret/data/demo/app" {
  capabilities = ["read"]
}
~~~

Token được cấp qua `TOKEN`, AppRole hoặc Kubernetes auth cần có policy này (hoặc policy tương đương được quản trị viên cho phép). Nếu token hợp lệ nhưng thiếu quyền, request vẫn có thể nhận `403 permission denied`.

Phân biệt các vòng đời:

- **`ClientAuthentication`:** chọn cơ chế login/cung cấp token. `EnvironmentVaultConfiguration` tạo implementation theo thuộc tính.
- **`SessionManager`:** cung cấp token cho các request và quản lý vòng đời theo implementation. Vì lớp môi trường kế thừa `AbstractVaultConfiguration`, nó dùng hạ tầng session của Spring Vault; token renewable có thể được quản lý gia hạn nếu Vault và auth method cho phép.
- **Token tĩnh:** `vault.token` không tự biến thành một cơ chế đăng nhập lại. Token bị revoke hoặc hết TTL có thể phải được cấp lại theo quy trình triển khai.
- **Secret lease:** credential động (chẳng hạn database dynamic secret) có lease riêng; đọc KV tĩnh không tạo một secret lease mới cho mỗi lần đọc. Theo dõi lease cần `SecretLeaseContainer` hoặc cơ chế chuyên biệt và cách xử lý credential rotation.
- **Transit/PKI:** truy cập những engine này cũng sử dụng authentication và Vault policy, nhưng API path và lifecycle tài nguyên riêng; không coi `vault.authentication` là quyền gọi Transit hoặc PKI.

**Vận hành production:** ưu tiên auth gắn với danh tính workload, cấp quyền ít nhất, đặt TTL phù hợp, quan sát renew/revoke và kiểm thử khi Vault tạm unavailable.

## 12. Xử lý lỗi cấu hình và kết nối

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Không có bean `VaultOperations`/`VaultTemplate` | Chưa import `EnvironmentVaultConfiguration` hoặc cấu hình không được Spring load | Xác nhận `@Import` và component scan |
| Không resolve được `VAULT_ADDR` | Placeholder ở YAML chưa được cấp giá trị | Kiểm tra `Environment` hiệu lực của process Java |
| Token thiếu khi `vault.authentication=TOKEN` | Chưa có `vault.token`, placeholder sai hoặc token rỗng | Cấp đúng token ở runtime, không tạo root token mặc định |
| Không login AppRole | RoleID/SecretID sai, hết hạn hoặc auth mount khác | Kiểm tra `vault.app-role.*` và Vault role thực tế |
| Kubernetes login lỗi | ServiceAccount token file thiếu/sai, role/namespace/audience không khớp | Kiểm tra JWT của Pod và Vault Kubernetes auth role |
| `SSLHandshakeException` hoặc PKIX | CA/trust store, hostname hoặc giao thức TLS sai | Sửa `vault.ssl.*` và trust chain; không tắt TLS |
| Timeout, connection refused | DNS, cổng, network hoặc Vault không chạy | Kiểm tra `vault.uri` từ đúng pod/container |
| HTTP 401/403 | Token không hợp lệ, đã revoke hoặc thiếu policy | Xem auth backend, token status, path của request |
| HTTP 404, response null | Mount/path sai, KV_1/KV_2 không khớp hoặc namespace sai | Kiểm tra `secret`, `demo/app`, backend KV v2 |
| Có hai bean `VaultTemplate` | Import `EnvironmentVaultConfiguration` cùng config khác | Bỏ cấu hình trùng hoặc dùng qualifier có chủ đích |
| Chuyển profile rồi vẫn gọi nhầm Vault | Nguồn property ưu tiên cao ghi đè URI | Kiểm tra giá trị `vault.uri` cuối cùng, không chỉ một YAML |
| Đọc được ban đầu rồi thất bại | Token hết hạn, bị revoke hoặc renew/login lại lỗi | Kiểm tra session/token lifecycle |

**Đừng dùng việc CLI đọc thành công bằng root token để kết luận service có quyền.** Cần kiểm tra bằng đúng auth role/token mà Java workload sử dụng. Trong log, chỉ ghi loại lỗi, status và thông tin không nhạy cảm; tránh in `vault.token`, JWT, SecretID hay giá trị secret.

### Thứ tự khoanh vùng hợp lý

~~~mermaid
flowchart TD
    A["Đọc Vault thất bại"] --> B{"Spring có VaultTemplate?"}
    B -- "Không" --> C["Kiểm tra @Import và bean trùng"]
    B -- "Có" --> D{"Kết nối HTTP/TLS được?"}
    D -- "Không" --> E["vault.uri, DNS, network, vault.ssl.*"]
    D -- "Có" --> F{"Login/token hợp lệ?"}
    F -- "Không" --> G["vault.authentication và auth-specific keys"]
    F -- "Có" --> H{"Policy cho phép path?"}
    H -- "Không" --> I["Role, token policy, KV v2 path"]
    H -- "Có" --> J["Kiểm tra mount, version, secret data"]
~~~

Sơ đồ dùng để định hướng chẩn đoán, không phải quy tắc rằng một HTTP code nhất định luôn xác định duy nhất nguyên nhân.

## 13. Kiểm thử tích hợp và giám sát

Một test unit mock `VaultOperations` chỉ kiểm tra logic Java đọc response; để chứng minh `EnvironmentVaultConfiguration` hoạt động thật, cần nạp Spring Context với properties hiệu lực và có Vault instance để gửi request.

| Trường hợp thử | Điều cần xác minh |
| --- | --- |
| `@Import` + local profile | `VaultOperations` được inject và đọc KV v2 thành công |
| Thiếu `vault.uri`/`VAULT_ADDR` | Có lỗi cấu hình hoặc kết nối rõ ràng, không tự chuyển sang production |
| `vault.authentication=TOKEN`, token sai | Request bị Vault từ chối, không tạo một secret giả |
| `APPROLE` với credential hợp lệ | Login nhận token gắn role/policy như dự kiến |
| `APPROLE` SecretID sai hoặc hết hạn | Login thất bại có thể quan sát |
| `KUBERNETES` với JWT/role hợp lệ | Workload đăng nhập qua đúng ServiceAccount |
| `KUBERNETES` sai namespace/audience | Login bị từ chối |
| Trust store CA hợp lệ | HTTPS kết nối được, hostname verification vẫn bật |
| Trust store sai | Handshake thất bại, không “chữa” bằng HTTP |
| KV v2 path và policy đúng | Đọc `apiKey` hợp lệ |
| KV v2 policy không có `read` | Trả lỗi quyền; không lẫn với 404 |
| Token hết TTL hoặc Vault unavailable | Hành vi renew/login lại/timeout đúng với thiết kế |
| Có Spring Cloud Vault cùng class import | Không tạo cấu hình trùng hoặc bean ambiguous |

Có thể dùng Vault dev/test container cho test TOKEN và AppRole. Kiểm thử Kubernetes auth cần cluster hoặc test setup có khả năng xác minh JWT phù hợp, không chỉ mock một chuỗi `jwt`.

Về giám sát, nên thu thập latency gọi Vault, tỷ lệ lỗi kết nối/TLS, login failures, HTTP 4xx/5xx và tình trạng token renew. Audit log của Vault giúp điều tra danh tính và policy trong phạm vi được phép. **Không xuất token, AppRole SecretID, JWT, private key PKI, Transit key material hoặc nội dung KV vào log, trace hay metric labels.**

## 14. Câu hỏi tự luyện

1. `EnvironmentVaultConfiguration` khác `AbstractVaultConfiguration` ở chỗ nào? Khi nào nên dùng từng cách?
2. Ba khóa `vault.uri`, `vault.authentication` và `vault.token` có vai trò gì? Vì sao `vault.authentication` mặc định `TOKEN` cần được kiểm soát?
3. Khi CLI có `VAULT_ADDR`, điều gì bảo đảm `EnvironmentVaultConfiguration` đọc đúng `vault.uri`?
4. Vì sao trong Spring Boot thường không cần `@PropertySource` để tải `application.yml`?
5. Với AppRole, hãy nêu ba khóa cần đặt ngoài `vault.uri` và ý nghĩa của SecretID.
6. Trong Kubernetes auth, file nào cung cấp JWT và vì sao chỉ đặt đúng `vault.kubernetes.role` chưa đủ?
7. `vault.ssl.trust-store` và `vault.ssl.key-store` khác nhau như thế nào?
8. Nếu Spring Cloud Vault đang dùng `spring.cloud.vault.*`, import thêm `EnvironmentVaultConfiguration` có rủi ro gì?
9. Token có quyền `read` trên `secret/demo/app` kiểu KV v1 có tự đọc được path KV v2 `secret/data/demo/app` không?
10. Nếu `vault.uri` đúng, tại sao request vẫn có thể trả 403 hoặc lỗi TLS?
11. Đọc KV tĩnh có tự tạo một secret lease mới cho mỗi request không? Token dùng đọc KV có TTL không?
12. Làm sao kiểm thử cấu hình AppRole/Kubernetes thật, thay vì chỉ mock `ClientAuthentication`?

**Kết quả mong đợi:** bạn có thể import `EnvironmentVaultConfiguration`, chọn đúng các khóa `vault.*` cho endpoint, TLS và auth method theo workload, dùng `VaultTemplate` đọc KV v2, biết tách cấu hình Spring Vault khỏi `spring.cloud.vault.*`, và xử lý lỗi theo tầng endpoint/authentication/policy/data. Đây là nền tảng để mở rộng SPRING_VAULT sang token/lease lifecycle, Transit encryption, PKI, giám sát và kiểm thử tích hợp.

### Tài liệu chính thức

- [Spring Vault Reference: Using EnvironmentVaultConfiguration](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html#vault.core.template.environment)
- [Javadoc: EnvironmentVaultConfiguration (Spring Vault 4.1)](https://docs.spring.io/spring-vault/reference/4.1/api/java/org/springframework/vault/config/EnvironmentVaultConfiguration.html)
- [Spring Vault Reference: Authentication Methods](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Cloud Vault Reference: Quick Start](https://docs.spring.io/spring-cloud-vault/reference/5.0/quickstart.html)

