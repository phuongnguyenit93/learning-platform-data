# Phân tách cấu hình giữa máy cá nhân, kiểm thử và triển khai

## 1. Mục tiêu của bài thực hành

Trong ứng dụng Java dùng **Spring Vault**, cùng một lời gọi **VaultTemplate** có thể đọc KV v2, sử dụng Transit encryption hoặc xin chứng chỉ PKI ở nhiều môi trường. Tuy nhiên, địa chỉ Vault, cách xác thực workload, chính sách phân quyền, mount và cơ chế tin cậy TLS thường khác nhau giữa **máy cá nhân**, **kiểm thử tích hợp** và **triển khai thật**. Nếu các giá trị này bị trộn lẫn, một lần chạy test có thể đọc nhầm secret thật, một ứng dụng production có thể dùng nhầm root token dev hoặc một bản build phải chứa thông tin bí mật.

Bài học thuộc chương **Môi trường thực hành**, tập trung thiết kế ranh giới cấu hình để thay đổi môi trường mà không sửa code nghiệp vụ. Trọng tâm là **ai đang chạy ứng dụng, ứng dụng kết nối Vault nào, được cấp quyền gì và lấy thông tin tin cậy từ đâu**.

Kết thúc bài, người học có thể:

1. Lập ma trận cấu hình cho máy cá nhân, test/CI, staging và production.
2. Phân biệt **cấu hình không nhạy cảm**, **credential đăng nhập** và **giá trị secret do Vault quản lý**.
3. Tách Spring Boot profile, biến môi trường và cơ chế cấp credential theo workload mà không hardcode token.
4. Cấu hình đúng endpoint, mount KV v2, logical key, CA/truststore và policy cho từng môi trường.
5. Cô lập Vault phục vụ kiểm thử tích hợp, kiểm tra quyền và vòng đời token/lease.
6. Xây dựng tiêu chí ngăn ứng dụng hoặc pipeline vô tình kết nối sai Vault và thực hiện rollout/rollback có kiểm soát.

**Phạm vi an toàn:** Các địa chỉ và giá trị ví dụ đều là giả lập. Root token cố định, Vault dev mode và HTTP chỉ phục vụ local/CI lab. Không lưu token, AppRole secret ID, private key hoặc dữ liệu thật trong YAML thuộc repository, JAR, log hay ảnh chụp màn hình.

## 2. Ba lớp cần được phân tách

Khi nói “cấu hình Vault”, cần phân biệt ba lớp:

| Lớp | Ví dụ | Nơi nên quản lý |
| --- | --- | --- |
| **Cấu hình kết nối và định tuyến** | Vault URL, mount KV v2, logical key, timeout, tên auth method, vị trí truststore | Spring profile, biến môi trường, cấu hình triển khai |
| **Thông tin xác thực workload** | Client token ngắn hạn, AppRole secret ID, Kubernetes service account JWT, chứng chỉ client mTLS nếu dùng | Nền tảng triển khai, identity provider, kênh phân phối credential bảo mật |
| **Dữ liệu nghiệp vụ bí mật** | Mật khẩu DB, API key, cấu hình nhạy cảm, khóa mã hóa do Transit giữ | Secrets engine của Vault, với policy và vòng đời riêng |

Ví dụ **VAULT_ADDR** là địa chỉ dịch vụ, không nhất thiết là bí mật; **VAULT_TOKEN** là credential và cần được bảo vệ. **database.password** đọc được từ KV là dữ liệu bí mật, không nên được lấy trước rồi ghi trở lại tệp **application-prod.yml** trong repository.

Sơ đồ luồng đề xuất:

~~~mermaid
flowchart TB
    Code["Một codebase Java<br/>Spring Vault / VaultTemplate"]
    Local["local profile<br/>Vault dev 127.0.0.1"]
    CI["it profile<br/>Vault container tạm thời"]
    Stage["staging profile<br/>Vault staging HTTPS"]
    Prod["prod profile<br/>Vault production HTTPS"]
    Code --> Local
    Code --> CI
    Code --> Stage
    Code --> Prod
    Local --> LAuth["Token lab giới hạn"]
    CI --> IAuth["Credential test ngắn hạn"]
    Stage --> SAuth["Identity staging + policy staging"]
    Prod --> PAuth["Workload identity + policy production"]
~~~

Tập mã xử lý **KV v2**, **Transit**, **PKI** và kết quả lỗi có thể giống nhau; khác biệt môi trường nằm ở cấu hình kết nối, danh tính, quyền và tài nguyên mà danh tính đó được phép dùng.

## 3. Ma trận máy cá nhân, kiểm thử và triển khai

### 3.1. Chọn ranh giới theo môi trường

| Thuộc tính | Máy cá nhân (**local**) | Tích hợp/CI (**it**) | Staging | Production (**prod**) |
| --- | --- | --- | --- | --- |
| Vault server | Một Vault dev Docker cục bộ | Vault container tạm thời cho test run | Vault staging non-dev | Vault production non-dev |
| Địa chỉ ví dụ | **http://127.0.0.1:8200** | Host + cổng ngẫu nhiên do test container cấp | **https://vault-stg.example.invalid** | **https://vault-prod.example.invalid** |
| Mount KV v2 | **lab-kv/** | **ci-kv/** | **apps-kv/** trong Vault staging | **apps-kv/** trong Vault production |
| Logical key | **apps/orders/config** | **apps/orders/config** | **apps/orders/config** | **apps/orders/config** |
| Xác thực | Token thử nghiệm giới hạn; có thể học AppRole | Token/role test phát mới mỗi suite | AppRole/Kubernetes/JWT/cloud auth phù hợp | Danh tính workload được cấp riêng |
| Chính sách | Quyền tối thiểu cho ứng dụng demo | Policy riêng cho test | Policy staging | Policy production |
| TLS | HTTP chỉ ở loopback | Có thể HTTP trong container biệt lập; test TLS riêng khi cần | HTTPS, xác minh CA và SAN | HTTPS, xác minh CA và SAN |
| Dữ liệu | Giá trị giả, dễ seed lại | Dữ liệu tổng hợp, tái tạo từ bootstrap | Secret staging riêng | Secret thật được quản lý và xoay vòng |
| Vòng đời | Xóa/tạo lại tùy bài | Test run tạo và dọn tự động | Được vận hành và kiểm soát thay đổi | HA, backup/restore, audit, cảnh báo |
| Kết quả khi sai credential | Fail và hướng dẫn tạo token lab | Test fail rõ nguyên nhân | Fail closed; báo vận hành | Fail closed; không fallback sang local |

**example.invalid** là tên miền dùng làm chỗ giữ chỗ, không phải máy chủ hoạt động. Khi triển khai, thay bằng DNS nội bộ thực sự và certificate có SAN khớp. Bảng trên dùng hai Vault server khác nhau cho staging và production; cùng mount name **apps-kv/** không có nghĩa chúng dùng chung dữ liệu khi nằm trên hai cụm tách biệt.

### 3.2. Có thể tách bằng cụm, namespace hoặc mount

Một vài chiến lược cách ly:

- **Cụm Vault riêng:** production và staging dùng backend Vault độc lập; ranh giới vận hành rõ ràng, thích hợp khi yêu cầu phân tách mạnh.
- **Namespace Vault**, nếu phiên bản/edition và hạ tầng hỗ trợ: tách đường dẫn và quản trị theo namespace; cần tính cả namespace trong cấu hình client.
- **Mount và policy riêng trong cùng Vault:** dễ thử nghiệm với **lab-kv/** và **ci-kv/** nhưng có cùng phạm vi hạ tầng; không mặc định coi là mức cô lập tương đương cụm độc lập.

Không suy ra rằng đặt tiền tố **prod/** trước logical key là đủ bảo vệ dữ liệu. Ranh giới thật phụ thuộc mount, Vault namespace/cụm, danh tính và policy. Quan trọng hơn, test phải **không có credential và đường mạng cho production** nếu không cần thiết.

### 3.3. Giữ key logic ổn định, tách đích qua cấu hình

Một thiết kế dễ kiểm thử là giữ logical key **apps/orders/config** cho cả ba môi trường, nhưng chọn mount/cluster từ cấu hình:

~~~text
local:   http://127.0.0.1:8200    + lab-kv  + apps/orders/config
it:      testcontainer:random-port + ci-kv   + apps/orders/config
stage:   https://vault-stg...      + apps-kv + apps/orders/config
prod:    https://vault-prod...     + apps-kv + apps/orders/config
~~~

Trong KV v2, câu lệnh CLI:

~~~bash
vault kv get -mount=lab-kv apps/orders/config
~~~

tương ứng API **GET /v1/lab-kv/data/apps/orders/config**. Nếu môi trường CI dùng mount **ci-kv/**, endpoint đổi thành **/v1/ci-kv/data/apps/orders/config**. Policy của token CI cũng phải trỏ đến **ci-kv/data/**. Spring Vault không tự sửa policy khi một profile chỉ thay tên mount.

## 4. Cấu trúc các tệp Spring Boot

Để tránh một file chứa cấu hình của mọi nơi, có thể tổ chức:

~~~text
src/main/resources/
├── application.yml
├── application-local.yml
├── application-it.yml
├── application-staging.yml
└── application-prod.yml
src/test/
└── ... test bootstrap và assertions ...
~~~

**application.yml** chứa các giá trị chung không nhạy cảm; các file profile chỉ có override cần thiết. Quy ước profile **it** là tên tùy chọn do dự án đặt. Các ví dụ dưới đây dùng namespace tùy chỉnh **training.vault** để ứng dụng tự bind vào client; **đây không phải thuộc tính Spring Vault tự động đọc**.

### 4.1. application.yml: các quy ước chung

~~~yaml
spring:
  application:
    name: orders-api

training:
  vault:
    config-key: apps/orders/config
    connect-timeout: 3s
    read-timeout: 5s
~~~

Đặt key logic ổn định, timeout theo yêu cầu quan sát và giới hạn chờ. Không đặt token hoặc mật khẩu thật. **connect-timeout** và **read-timeout** ở đây cũng là key tùy chỉnh: muốn có hiệu lực phải ánh xạ chúng vào HTTP client của Spring Vault trong cấu hình Java, chứ chỉ khai báo YAML không tự cấu hình timeout.

### 4.2. application-local.yml: dùng Vault cá nhân

~~~yaml
training:
  vault:
    uri: ${APP_VAULT_URI:http://127.0.0.1:8200}
    mount: lab-kv
    auth-kind: token
~~~

Chạy local bằng **SPRING_PROFILES_ACTIVE=local** hoặc tham số profile tương ứng. Cho phép địa chỉ loopback mặc định để việc học thuận tiện. Credential đọc KV nằm trong biến môi trường **APP_VAULT_TOKEN**, không nằm trong YAML. Root token dành cho bootstrap; ứng dụng local phải dùng token có policy giới hạn.

### 4.3. application-it.yml: test container do bộ kiểm thử cung cấp

~~~yaml
training:
  vault:
    uri: ${APP_VAULT_URI}
    mount: ci-kv
    auth-kind: token
~~~

**Không có địa chỉ mặc định** cho profile tích hợp: framework kiểm thử cần khởi chạy Vault tạm thời, lấy **đúng mapped host/port**, sau đó cấp **APP_VAULT_URI** và token test. Không dùng **http://127.0.0.1:8200** làm fallback vì CI có thể vô tình kết nối tới Vault cục bộ của một runner dùng chung.

### 4.4. application-staging.yml

~~~yaml
training:
  vault:
    uri: ${APP_VAULT_URI}
    mount: apps-kv
    auth-kind: workload
    expected-environment: staging
~~~

### 4.5. application-prod.yml

~~~yaml
training:
  vault:
    uri: ${APP_VAULT_URI}
    mount: apps-kv
    auth-kind: workload
    expected-environment: production
~~~

Hai profile deploy đều **bắt buộc** bên triển khai cung cấp URI và thực hiện xác thực workload. Mẫu không có **APP_VAULT_TOKEN** hay AppRole secret ID hardcoded. Cấu hình **auth-kind** và **expected-environment** ở đây chỉ là metadata của ứng dụng để chọn adapter và chạy kiểm tra: chưa có ý nghĩa bảo mật nếu chương trình không đọc và thực thi nó.

Một ví dụ triển khai đúng cần đảm bảo:

- **APP_VAULT_URI** do môi trường triển khai quản lý và khớp hostname TLS.
- Credential do hệ thống danh tính workload cấp; không lấy từ bản build.
- Vault policy giới hạn các mount/endpoint cần dùng.
- Java có truststore chứa CA phù hợp, xác minh SAN và không tắt kiểm tra TLS.
- Một lỗi thiếu biến môi trường hoặc auth config phải khiến ứng dụng thất bại có thông điệp rõ ràng.

### 4.6. Kích hoạt profile và thứ tự override

Trên máy cá nhân:

~~~bash
# Bash / zsh: dùng token thử nghiệm do Vault lab cấp
export SPRING_PROFILES_ACTIVE=local
export APP_VAULT_TOKEN="<token-local-read-only>"
./gradlew bootRun
~~~

Trên PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:APP_VAULT_TOKEN = "<token-local-read-only>"
./gradlew.bat bootRun
~~~

Các lệnh Gradle chỉ minh họa cách **người học** chạy ứng dụng có Spring Boot Gradle plugin; nếu dự án dùng Maven hoặc không có Gradle wrapper thì dùng công cụ của dự án. Không có lệnh nào ở đây là lệnh đã chạy trong môi trường biên soạn tài liệu.

Spring Boot kết hợp cấu hình từ nhiều nguồn; profile-specific file, biến môi trường và tham số khởi chạy có thứ tự ưu tiên theo quy tắc externalized configuration của phiên bản Boot đang dùng. Vì vậy cần **quan sát giá trị hiệu lực**, không chỉ đọc một YAML rồi kết luận. Tránh đặt cùng một key trong quá nhiều nguồn mà không có chủ sở hữu rõ ràng.

Không gắn **spring.profiles.active** bên trong file profile-specific để tự kích hoạt chính nó. Profile phải được chọn từ môi trường chạy, test annotation hoặc cấu hình được kiểm soát. Với production, cần chặn việc ghép profile **local** và **prod** nếu điều đó gây ra cấu hình thiếu nhất quán.

## 5. Tách việc kết nối Vault và việc lấy secret

Một ứng dụng nên có ranh giới rõ giữa:

1. **Environment adapter**: tạo Vault client với endpoint, TLS trust và authentication của môi trường hiện tại.
2. **Domain adapter/repository**: gọi KV/Transit/PKI trên những mount và key đã cấu hình.
3. **Business code**: dùng dữ liệu đã được kiểm tra mà không cần biết URL, token hoặc tên auth mount.

Ví dụ tách trách nhiệm:

~~~mermaid
flowchart TB
    P["Spring profile + deployment config"] --> C["Vault client configuration"]
    Id["Workload identity / test token"] --> C
    TLS["CA trust / HTTPS"] --> C
    C --> T["VaultTemplate"]
    T --> KV["KV v2 reader<br/>mount + logical key"]
    T --> TR["Transit adapter<br/>encrypt/decrypt policy"]
    T --> PKI["PKI adapter<br/>issue role + renewal plan"]
    KV --> Service["Orders service"]
    TR --> Service
    PKI --> Service
~~~

Nên tránh để mọi service tự ghép địa chỉ **https://.../v1/...**, tự đọc môi trường và tự lưu token. Nếu mỗi lớp tự biết về root token hoặc tự quyết định endpoint, một thay đổi từ staging sang production dễ tạo cấu hình lệch nhau. **VaultTemplate** nên nhận một authentication/session manager nhất quán; các adapter nghiệp vụ chỉ cần biết thao tác và mount liên quan.

Điều này cũng giúp thay xác thực local bằng AppRole/Kubernetes/JWT ở triển khai mà không sửa code đọc **apps/orders/config**. Chính sách và role vẫn do Vault quản lý, không được tự động mở rộng dựa trên tên Spring profile.

## 6. Cấu hình Spring Vault Core theo từng môi trường

### 6.1. Adapter local và integration test

Với dependency **org.springframework.vault:spring-vault-core** và **Spring Boot** phù hợp, có thể tạo một **VaultTemplate** chỉ dành cho profile **local** hoặc **it**. Trong hai profile đó, token được cấp riêng và đưa từ biến môi trường **APP_VAULT_TOKEN**:

~~~java
import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

@Configuration
@Profile({"local", "it"})
public class LabVaultClientConfiguration {

    @Bean
    VaultTemplate vaultTemplate(
            @Value("${training.vault.uri}") String vaultUri) {

        String token = System.getenv("APP_VAULT_TOKEN");
        if (token == null || token.isBlank()) {
            throw new IllegalStateException(
                    "APP_VAULT_TOKEN must be supplied for local/it");
        }
        if (vaultUri == null || vaultUri.isBlank()) {
            throw new IllegalStateException(
                    "training.vault.uri must be configured");
        }

        return new VaultTemplate(
                VaultEndpoint.from(URI.create(vaultUri)),
                new TokenAuthentication(token));
    }
}
~~~

Đây là cách ghép nối cụ thể giữa **training.vault.uri** trong YAML và Spring Vault Core. Class được giới hạn bằng **@Profile({"local", "it"})**, vì vậy không có cơ chế dùng token lab mặc định khi kích hoạt production. Với deployment, cần cung cấp **một bean VaultTemplate khác** dùng workload authentication và HTTP client TLS phù hợp; không nên sao chép class này rồi đổi tên profile thành prod.

Đối với ứng dụng chạy lâu dài, **TokenAuthentication** trực tiếp chỉ là minh họa cơ bản. Token có TTL, có thể bị revoke và có thể cần renew hoặc login lại. **Spring Vault SessionManager** và **ClientAuthentication** phù hợp với auth method được chọn mới chịu trách nhiệm thiết kế vòng đời phiên.

### 6.2. Adapter đọc secret không biết đang ở môi trường nào

Code nghiệp vụ có thể đọc mount/key từ cấu hình, sử dụng VaultTemplate đã được tạo:

~~~java
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.Versioned;

@Component
public class OrdersConfigReader {
    private final VaultTemplate vaultTemplate;
    private final String mount;
    private final String key;

    public OrdersConfigReader(
            VaultTemplate vaultTemplate,
            @Value("${training.vault.mount}") String mount,
            @Value("${training.vault.config-key}") String key) {
        this.vaultTemplate = vaultTemplate;
        this.mount = mount;
        this.key = key;
    }

    public Map<String, Object> load() {
        Versioned<Map<String, Object>> result = vaultTemplate
                .opsForVersionedKeyValue(mount)
                .get(key);
        if (result == null || result.getData() == null) {
            throw new IllegalStateException("Vault config was not found");
        }
        // Phương thức trả data cho logic dùng tiếp; không ghi data vào log.
        return result.getData();
    }
}
~~~

Ở local, class đọc **lab-kv/data/apps/orders/config**; ở CI, nếu profile **it** chỉ định **ci-kv**, lời gọi sẽ đọc **ci-kv/data/apps/orders/config**. Tên key không thay đổi và business code không cần biết token là gì.

Nếu ứng dụng chỉ dùng **Spring Vault Core**, các thuộc tính **spring.cloud.vault.*** không tự trở thành cấu hình Spring Vault Core và **training.vault.*** cũng không tự sinh bean. **Spring Cloud Vault** là tích hợp khác, có thể tự nạp property từ Vault khi thêm starter và cấu hình tương ứng (chẳng hạn **spring.config.import=vault://** trên các phiên bản hỗ trợ). Chỉ chọn một cơ chế cấu hình làm nguồn chính cho mỗi vai trò, kiểm tra tài liệu của phiên bản Spring Cloud Vault đang dùng và tránh để cả ứng dụng tự đọc KV bằng VaultTemplate lẫn cơ chế import property vô tình đọc cùng key với thứ tự ưu tiên không rõ ràng.

### 6.3. Adapter staging/production cần xác thực theo workload

Trong môi trường triển khai, cách tạo **ClientAuthentication** có thể khác theo nền tảng:

| Môi trường chạy | Phương thức phù hợp để xem xét | Credential đầu vào | Lưu ý vòng đời |
| --- | --- | --- | --- |
| VM hoặc workload không có identity provider khác | **AppRole** | **role_id** và **secret_id** được cấp bảo mật | Secret ID có TTL/lượt dùng; cần cơ chế cấp lại |
| Kubernetes | **Kubernetes auth** hoặc JWT auth phù hợp | Service account token / JWT của pod | Chú ý audience, rotation, role binding và auth mount |
| AWS/Azure/GCP | Auth method theo nền tảng cloud | Workload identity / metadata / bằng chứng ký | Không dùng access key tĩnh nếu cơ chế workload identity đáp ứng |
| Bài test mô phỏng | Token có TTL ngắn | Token mới của test fixture | Xóa token và container khi kết thúc suite |

AppRole, Kubernetes và cloud auth đều có mục đích cuối là **lấy client token với policy phù hợp**. Hãy giữ chính sách **read data**, **Transit encrypt/decrypt** và **PKI issue** độc lập với phương pháp xác thực; việc đổi auth method không tự động cấp thêm quyền.

Không triển khai kiểu “nếu AppRole/Kubernetes login lỗi thì tự dùng root token lab” vì đó là một lỗi thiết kế an toàn. Thiếu credential, lỗi CA hay login thất bại phải được báo chính xác, có retry giới hạn khi phù hợp, và ngăn ứng dụng phục vụ các chức năng cần secret cho tới khi xác thực thành công.

## 7. Bootstrap KV v2 và policy theo môi trường

### 7.1. Tạo dữ liệu local với quyền quản trị lab

Trên một Vault dev local chỉ chứa dữ liệu giả, quản trị viên có thể tạo mount và secret bằng Vault CLI:

~~~bash
# Khởi tạo khi mount chưa tồn tại; không chạy enable lặp lại.
vault secrets enable -path=lab-kv kv-v2

vault kv put -mount=lab-kv apps/orders/config \
  app_name=orders-api \
  jdbc_url=jdbc:postgresql://127.0.0.1:5432/orders_lab \
  db_password=demo-only

vault kv get -mount=lab-kv apps/orders/config
~~~

Đây là lệnh mẫu chạy khi Vault CLI đã có **VAULT_ADDR** và quyền quản trị lab; nếu CLI nằm trong Docker, dùng **docker compose exec** tương ứng. Không dùng secret thật trong CLI vì lệnh có thể được ghi vào history hoặc log. Với KV v2, **kv put** tạo thêm một version nếu key đã tồn tại.

Policy chỉ đọc dành cho **orders-api** ở local:

~~~hcl
path "lab-kv/data/apps/orders/config" {
  capabilities = ["read"]
}
~~~

Policy CI phải dùng **mount riêng**:

~~~hcl
path "ci-kv/data/apps/orders/config" {
  capabilities = ["read"]
}
~~~

Policy production trên Vault production:

~~~hcl
path "apps-kv/data/apps/orders/config" {
  capabilities = ["read"]
}
~~~

**Không dùng wildcard toàn mount chỉ để khắc phục một lỗi 403.** Ví dụ không nên cấp **path "apps-kv/*"** cho mọi ứng dụng, vì KV v2 tách endpoint dữ liệu, metadata, xóa version và thao tác quản trị. Policy phải cấp đúng capability (ví dụ **read** trên **data/**; **list** trên **metadata/** nếu cần liệt kê).

### 7.2. Transit và PKI cũng phải có ranh giới môi trường

Khi ứng dụng dùng Transit encryption hoặc PKI, phải xác định **mount** và **role/key** theo môi trường. Ví dụ:

| Nghiệp vụ | Local | CI | Production |
| --- | --- | --- | --- |
| Transit encrypt | **lab-transit/encrypt/orders** | **ci-transit/encrypt/orders** | **transit/encrypt/orders** |
| Transit decrypt | Chỉ cấp cho thành phần cần giải mã | Test bằng policy riêng để xác minh bị chặn | Policy độc lập với encrypt |
| PKI issue | **lab-pki/issue/lab-server** | **ci-pki/issue/test-server** | **pki/issue/orders-service** |

Các mount, key và role trên là **quy ước thiết kế**, không tự tồn tại. Người quản trị phải tạo engine, khóa hoặc role PKI trước khi test; role PKI giới hạn tên miền và TTL, còn policy cấp quyền gọi endpoint **issue/**. Tránh dùng cùng CA và private key PKI của production cho test, và không sao chép ciphertext/credential để gắn vào dữ liệu giả rồi nhầm thành thực.

Với Transit, key được quản lý trong Vault; cùng tên khóa ở hai Vault khác nhau **không mặc định** có vật liệu khóa tương đương. Một ciphertext mã hóa ở staging có thể không giải mã được ở production; đây là lý do dữ liệu mã hóa và quản lý key/backup phải đi cùng kế hoạch di chuyển.

### 7.3. Quyền tạo dữ liệu test và quyền của ứng dụng phải khác nhau

Một CI run thường có hai giai đoạn:

1. **Bootstrap:** dùng quyền cao *bên trong container Vault test*, enable mount, tạo policy, ghi dữ liệu giả và phát token test.
2. **Execute:** ứng dụng test dùng token bị giới hạn bởi policy, xác minh thao tác được phép và không được phép.

Không chạy mọi bài test bằng token bootstrap/root; làm vậy các phép thử âm (ví dụ Orders không đọc được Billing hoặc không được gọi Transit decrypt) sẽ mất ý nghĩa. Bootstrap token là công cụ dựng fixture, không phải credential nghiệp vụ.

## 8. Cô lập kiểm thử tích hợp bằng Testcontainers

### 8.1. Vì sao không dùng Vault local của lập trình viên?

Nếu test trỏ cố định tới **http://127.0.0.1:8200**:

- Trên máy lập trình viên, test có thể chạy đỗ vì secret vô tình đã tồn tại.
- Trên CI, không chắc có Vault nào nghe cổng 8200.
- Hai suite chạy song song có thể ghi đè phiên bản KV v2 của nhau.
- Nếu profile/URL sai, test có nguy cơ truy cập một Vault dùng chung.

**Testcontainers** hoặc một container Vault tạm thời do pipeline sở hữu giải quyết vấn đề tái lập. Mỗi suite nên có state riêng, tạo mount/secret/policy trước khi khởi tạo client Spring Vault, rồi dọn container khi kết thúc.

### 8.2. Quy trình một test run

~~~mermaid
flowchart LR
    Start["Test suite bắt đầu"] --> New["Tạo Vault dev container<br/>port động"]
    New --> Init["Bootstrap ci-kv<br/>dữ liệu và policy"]
    Init --> Token["Cấp token test<br/>read-only"]
    Token --> Config["Inject endpoint<br/>và test identity"]
    Config --> Tests["VaultTemplate read<br/>kiểm tra 403/404/TTL"]
    Tests --> Stop["Dọn container<br/>và credential"]
~~~

Ví dụ phác thảo Java cho riêng bước **khởi chạy và đưa endpoint động vào Spring test context**:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.vault.VaultContainer;

@Testcontainers
@SpringBootTest
@ActiveProfiles("it")
class OrdersVaultIntegrationTest {

    @Container
    static final VaultContainer<?> vault =
            new VaultContainer<>("hashicorp/vault:1.19.0")
                    .withVaultToken("ci-bootstrap-only");

    @DynamicPropertySource
    static void vaultEndpoint(DynamicPropertyRegistry registry) {
        registry.add("training.vault.uri",
                () -> "http://" + vault.getHost() + ":"
                        + vault.getMappedPort(8200));
    }

    @Test
    void readsOrdersConfig() {
        // Gọi bean OrdersConfigReader và kiểm tra dữ liệu fixture.
        // Cần bootstrap ci-kv và token test trước khi client sử dụng.
    }
}
~~~

Đây là **khung cấu trúc**, chưa phải một test độc lập chạy được ngay: cần thêm dependency **Testcontainers Vault + JUnit Jupiter**, bootstrap dữ liệu/policy, cung cấp token test cho client và triển khai assertion. Phải thực hiện bootstrap **trước khi Spring tạo bean VaultTemplate và chạy test** (chẳng hạn qua init commands của container được hỗ trợ bởi phiên bản Testcontainers bạn chọn hoặc bước tạo fixture trước khi nạp context). Không chỉ thêm **@BeforeAll** một cách máy móc nếu trong quá trình khởi động Spring context đã có bean gọi Vault trước thời điểm đó.

Ví dụ code ở mục 6 đọc token từ biến môi trường **APP_VAULT_TOKEN**. Trong CI cần cấp đúng biến này **trước khi ứng dụng/test process được tạo**, hoặc dùng **@TestConfiguration** riêng cho profile **it** để cấp **ClientAuthentication** từ token do fixture phát. **@DynamicPropertySource** chỉ giải quyết endpoint nếu ứng dụng đọc cấu hình đó; nó không tự tạo token và không đặt biến môi trường của process.

Khi kiểm thử TLS, thay container HTTP bằng một Vault test có certificate/CA riêng; inject địa chỉ HTTPS và truststore tương ứng. Không tắt xác minh chứng thư để phép thử qua được.

### 8.3. Ma trận ca test cần thiết

| Ca kiểm thử | Tình huống | Kết quả cần đạt |
| --- | --- | --- |
| Đọc KV v2 | Token read đúng **ci-kv/data/apps/orders/config** | Trả dữ liệu tổng hợp |
| Cấm ghi KV | Token read gọi put | **403**, version không tăng |
| Cách ly key | Token Orders đọc Billing | **403** |
| Không tồn tại | Đọc logical key không có | Xử lý null/404 phù hợp API/client |
| Transit | Token encrypt chỉ được gọi encrypt, không được decrypt | Thành công/bị từ chối đúng policy |
| PKI | Cấp common name hợp lệ và không hợp lệ | Tuân theo role/TTL |
| Vòng đời token | Token hết hạn hoặc revoke | Request từ chối hoặc session phục hồi theo thiết kế |
| Lỗi kết nối | Dừng container Vault test | Timeout/connection error được phân loại rõ |
| TLS | CA sai hoặc hostname sai | Handshake bị từ chối |
| Sai profile | Chạy profile it mà thiếu endpoint test | Khởi động thất bại sớm, không fallback local |

Không hardcode phụ thuộc thứ tự test. Khi tests chạy song song, nên dùng container/namespace riêng hoặc cơ chế đảm bảo dữ liệu fixture không bị thay đổi bởi suite khác.

## 9. TLS, secret delivery và vòng đời credential theo profile

### 9.1. TLS của local/CI không trở thành cấu hình production

Ở local, HTTP có thể được dùng **chỉ tại loopback** để đơn giản hóa bài học. Ở staging/production, Java client cần xác minh certificate của server bằng CA tin cậy và đối chiếu SAN với hostname:

| Thành phần | Local/CI lab | Staging/production |
| --- | --- | --- |
| URL | **http://127.0.0.1:8200** hoặc endpoint container biệt lập | **https://vault-...** |
| CA | Không dùng khi HTTP; có thể dùng CA test riêng để kiểm thử TLS | CA được quản lý và phân phối qua kênh tin cậy |
| JVM truststore | Tùy bài test TLS | PKCS#12/JVM trust store hoặc cấu hình SSLContext của HTTP client |
| Xác minh hostname | Không có khi dùng HTTP | Bắt buộc đối chiếu DNS/IP SAN |
| Token | Token lab ngắn hạn | Token từ auth method gắn với danh tính workload |

Ví dụ JVM được chạy với một truststore riêng:

~~~text
-Djavax.net.ssl.trustStore=/etc/app/trust/vault-ca.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Cần cung cấp cả mật khẩu truy cập truststore theo cơ chế bảo mật phù hợp khi runtime yêu cầu. Không đặt mật khẩu vào script được commit hoặc log. Nếu ứng dụng sử dụng HTTP client được cấu hình **SSLContext riêng**, cần nạp CA/trust manager vào client đó; hai system properties ở trên chỉ có hiệu lực với thành phần dùng JSSE/default trust managers tương ứng.

**VAULT_CACERT** thường dùng để cấu hình **Vault CLI**. Nó không tự động bảo đảm JVM hoặc HTTP client của Spring Vault tin CA. Đừng chữa lỗi **PKIX path building failed** bằng cách tắt xác minh certificate; cần sửa nguồn trust, SAN, hostname hoặc chuỗi certificate.

### 9.2. Cấp credential qua môi trường chạy

Trong triển khai, không viết:

~~~yaml
# Sai: ví dụ phản-pattern, tuyệt đối không dùng với credential thật.
training:
  vault:
    token: root-or-long-lived-token
    approle-secret-id: hardcoded-secret-id
~~~

Tốt hơn, cấu hình triển khai cung cấp các **đường dẫn, role name hoặc identity reference** không nhạy cảm, còn token/secret ID được lấy qua cơ chế của nền tảng. Ví dụ trong Kubernetes, có thể ràng buộc service account của workload với Vault Kubernetes auth role và giới hạn quyền role đó trong Vault. Nếu chọn AppRole trên VM, cần bảo vệ kênh phân phối **secret_id** và kế hoạch cấp lại khi hết hạn/hết lượt dùng.

Đối với các runtime bắt buộc dùng environment variable để cung cấp credential, kiểm soát ai có quyền xem process environment, cấu hình CI, pod spec và log. Không in **env** toàn bộ hoặc dump Spring Environment trong endpoint debug; tắt/cấp quyền cho các actuator endpoint có thể chứa cấu hình.

### 9.3. Phân biệt token, lease và dữ liệu KV

- **Client token** giới hạn phiên truy cập Vault; token có TTL, có thể renew trong điều kiện cho phép, có thể bị revoke.
- **AppRole secret ID** là đầu vào đăng nhập, có TTL và giới hạn số lần dùng riêng; không phải client token.
- **Dynamic secret lease** từ engine như database có TTL/lease ID, có thể có cơ chế renew/revoke; vòng đời khác client token.
- **KV v2 version** là phiên bản của secret tĩnh; không phải TTL hay lease động.
- **Transit encryption key** ở Vault có vòng đời quản trị/rotation riêng; việc token đổi không đồng nghĩa các ciphertext đã lưu bị đổi.
- **PKI certificate validity** có thời hạn hiệu lực riêng; thường cần cấp chứng thư mới thay vì giả định có thể kéo dài bằng lease renew.

Do đó khi chuyển giữa staging và production, phải xét **cả auth token và secret được cấp**, không chỉ đổi địa chỉ Vault. Nếu workload cần tự động làm mới phiên, thiết kế **SessionManager** cho Spring Vault và kiểm thử trường hợp renew/re-login thất bại. Một token lab có TTL 15 phút chỉ có ý nghĩa kiểm chứng nhanh; không nên dùng cùng cách cấp token thủ công cho ứng dụng chạy lâu dài.

## 10. Bảo vệ chống kết nối nhầm môi trường

### 10.1. Kiểm tra ngay khi startup

Một chiến lược **fail closed** là kiểm tra cấu hình trước khi phục vụ request:

1. Profile **prod** phải có endpoint HTTPS; host nằm trong danh sách dịch vụ Vault production được phép.
2. Profile **staging** không được dùng Vault production hoặc URI local.
3. Profile **it** phải được test harness cấp endpoint động; không có fallback tới cổng 8200 trên host.
4. **auth-kind** khớp loại workload và credential có sẵn; không fallback sang root token.
5. **mount** đúng với môi trường; nếu tổ chức cùng cluster, phải xét cả **Vault namespace** và policy.
6. Certificate chain và SAN hợp lệ; không cho phép biến cấu hình tắt TLS verification trên deploy profile.
7. Nếu secret thiếu hoặc token không có quyền, báo lỗi có ngữ cảnh đã che bí mật và không tự thử các mount khác.

Ví dụ giả mã kiểm tra cấu hình khi khởi động:

~~~java
void validateVaultSettings(
        String profile, URI vaultUri, String mount) {
    if (profile.equals("prod")) {
        if (!"https".equalsIgnoreCase(vaultUri.getScheme())) {
            throw new IllegalStateException(
                    "Production Vault endpoint must use HTTPS");
        }
        if (!vaultUri.getHost().equals("vault-prod.example.invalid")) {
            throw new IllegalStateException(
                    "Unexpected production Vault endpoint");
        }
        if (!"apps-kv".equals(mount)) {
            throw new IllegalStateException(
                    "Unexpected production KV mount");
        }
    }
}
~~~

Đây là **mã minh họa nguyên tắc**, chưa phải bộ kiểm tra cấu hình hoàn chỉnh. Host production thật phải được thay bằng giá trị do đội vận hành kiểm soát; cần kiểm tra cả URI, port, scheme, namespace, trust, auth configuration và trường hợp nhiều profile cùng kích hoạt. Tránh so host bằng phép tìm chuỗi con, vì dễ vô tình chấp nhận tên miền giống nhau.

Đừng dựa vào **tên profile** như ranh giới bảo mật duy nhất: policy Vault, workload identity, mạng, ACL, namespace/cluster và quản trị credential mới là các rào chắn thực tế. Bài kiểm tra startup chỉ giúp phát hiện lỗi cấu hình sớm.

### 10.2. Không chuyển giá trị bí mật qua log và endpoint health

Khi cần giám sát, có thể ghi:

- Tên profile và **nhãn môi trường** đã cấu hình, không ghi token.
- Vai trò nghiệp vụ (**orders-api**, **orders-worker**) và loại thao tác (**KV read**, **Transit encrypt**, **PKI issue**).
- Trạng thái lỗi đã phân loại: kết nối, TLS, Vault sealed, xác thực, policy, key không tồn tại.
- Độ trễ, tỉ lệ lỗi, số lần retry và mã tương quan khi không chứa dữ liệu bí mật.

Không ghi raw response từ Vault, plaintext, password, private key, client token, AppRole secret ID hoặc nội dung chứng chỉ có private key. Health endpoint của ứng dụng nên báo **readiness** theo nhu cầu thực, không tự trả toàn bộ trạng thái Vault hay cấu hình được dùng. Nếu Vault bị sealed hoặc mất mạng, cân nhắc ứng dụng cần tạm ngừng readiness hay vẫn phục vụ các tính năng độc lập với Vault.

### 10.3. Kiểm tra quyền âm trước khi phát hành

Một test đọc KV thành công **chưa đủ** chứng minh quyền tối thiểu. Ít nhất cần khẳng định:

~~~text
orders-api:
  GET  <mount>/data/apps/orders/config   -> được phép
  POST <mount>/data/apps/orders/config   -> bị từ chối
  GET  <mount>/data/apps/billing/config  -> bị từ chối
  POST <transit>/decrypt/orders          -> bị từ chối
  POST <pki>/issue/another-role          -> bị từ chối
~~~

Với KV v2, policy data read là **path ".../data/..."**, còn **list** hoặc metadata read là quyền trên **".../metadata/..."**. Không cấp quyền trên cả mount để tránh lỗi 403 khi không chắc endpoint nào đang được gọi. Khi một phép thử âm thành công ngoài ý muốn, xác định có phải token đang là root token hoặc token mang policy cộng dồn rộng hơn dự kiến không.

## 11. Quy trình chuyển từ local sang triển khai

| Giai đoạn | Việc cần hoàn thành | Điều kiện trước khi đi tiếp |
| --- | --- | --- |
| **Local** | Vault dev, seed dữ liệu giả, token hạn chế, kiểm tra VaultTemplate | Đọc đúng KV v2, ghi trái quyền bị chặn |
| **Integration/CI** | Tạo Vault tạm, mount ci-kv, seed data, cấp token mới, chạy test lỗi | Test không phụ thuộc máy người học; không dùng production URL/token |
| **Staging** | Dựng Vault non-dev, TLS, auth workload, policy staging, Transit/PKI test | Kiểm thử cùng kiểu workload identity và TLS như deploy dự kiến |
| **Production readiness** | Xác nhận DNS/TLS, mounts, roles, permissions, backup, audit, monitoring | Không còn secret trong artifact; kiểm thử quyền và failover theo yêu cầu |
| **Rollout** | Deploy cấu hình prod, xác nhận login, KV read, health, latency và cảnh báo | Không có lỗi TLS/403 bất thường, hoạt động trong giới hạn |
| **Rollback** | Khôi phục bản ứng dụng/cấu hình trước theo kế hoạch | Không dùng chung credential quá rộng hoặc xóa secret/version tùy tiện |

**Tách code build khỏi environment deploy:** Một artifact có thể chạy ở nhiều môi trường với config bên ngoài, nhưng cần cố định phiên bản thư viện, tài nguyên phụ thuộc và chính sách kiểm thử. Nếu staging dùng chính sách/mount khác quá xa production, việc “staging xanh” có thể không phản ánh rủi ro thực tế.

### 11.1. Quản lý thay đổi khi đổi mount, key hoặc role

Khi đổi một mount hoặc logical key ở production:

1. Tạo mount/key/role/policy mới (nếu cần) với quản trị Vault và backup phù hợp.
2. Xác minh workload identity có quyền cần thiết, tránh cấp tạm **root**.
3. Cập nhật tham số mount/key trong cấu hình deploy và chạy test tương ứng.
4. Chuyển ứng dụng từng bước, theo dõi lỗi 403/404, TLS, độ trễ và các thao tác liên quan.
5. Chỉ thu hồi quyền cũ hoặc dọn secret cũ sau khi xác nhận không còn workload phụ thuộc và kế hoạch rollback không cần chúng.

Với Transit và PKI, đổi khóa hoặc CA có thể ảnh hưởng ciphertext, private key, certificate chain và khả năng giải mã dữ liệu cũ. Không coi đổi **mount name** hoặc **PKI role** tương đương việc đổi một chuỗi vô hại trong YAML.

### 11.2. Một lỗi cấu hình điển hình

Giả sử một bản deploy mang profile **prod** nhưng vẫn còn:

~~~yaml
training:
  vault:
    uri: http://127.0.0.1:8200
    mount: lab-kv
~~~

Trong Kubernetes, **127.0.0.1** trỏ đến chính container ứng dụng, có thể gây **connection refused**. Tệ hơn, nếu một container khác hoặc sidecar vô tình cung cấp dịch vụ ở loopback, ứng dụng có thể kết nối sai đích. Kiểm tra startup và mạng phải phát hiện cấu hình này trước khi phục vụ traffic.

Một tình huống khác: production URL đúng nhưng truststore JVM chứa CA của lab; request thất bại với **PKIX** ngay ở TLS. Thay token hoặc mở rộng policy sẽ không giải quyết lỗi đó. Ngược lại, khi TLS đã thành công nhưng policy chỉ cho **lab-kv/data/...** trong khi production dùng **apps-kv/data/...**, Vault trả **403** do sai policy path.

## 12. Ma trận xử lý sự cố

| Hiện tượng | Tầng nghi ngờ | Cách kiểm tra không làm lộ secret |
| --- | --- | --- |
| Không tìm thấy property **training.vault.uri** | Spring profile / biến môi trường | Profile đang active, tên property, nguồn override |
| Java gọi đúng URI nhưng không kết nối | DNS, service discovery, port, network policy | DNS/port, health endpoint, timeout |
| **PKIX path building failed** | Truststore JVM không có CA phù hợp | Alias, fingerprint CA, đường dẫn truststore |
| Certificate hostname mismatch | URI không khớp SAN | Certificate SAN và hostname thực tế |
| **Vault sealed / 503** | Trạng thái máy chủ Vault | Vault health/status, quy trình unseal/auto-unseal |
| **403** khi login | Auth method, workload identity, AppRole secret ID/JWT | Role binding, auth mount, TTL/lượt dùng |
| **403** khi KV get | Token policy, sai mount/data path | Policy **data/**, token policies, namespace |
| **404** hoặc null với KV | Secret chưa seed, sai key/version, KV v1/v2 nhầm | CLI với đúng mount, metadata/version |
| Local chạy nhưng CI fail | Test phụ thuộc dữ liệu cá nhân hoặc URI cố định | Container fixture, bootstrap order, dynamic port |
| Staging chạy nhưng prod fail | Khác auth role, TLS CA, policy, mount, key | So ma trận môi trường và cấu hình hiệu lực |
| Token hết hạn sau khi app chạy lâu | Thiếu renew/re-login hoặc credential cấp lại | Token TTL, session manager, auth provider |
| Transit/PKI lỗi dù KV vẫn đọc được | Mount/role/policy riêng hoặc giới hạn engine | Transit key, PKI role, capability endpoint |

Phải phân biệt **lỗi config từ Spring**, **lỗi TLS/mạng**, **Vault chưa sẵn sàng**, **auth/token** và **policy của secrets engine**. Retry có giới hạn có thể phù hợp với lỗi mạng tạm thời, nhưng retry vô hạn không giải quyết policy **403**, sai CA hoặc logical key chưa được tạo.

## 13. Bài tập thực hành

### Bài 1 — Hoàn thiện ma trận môi trường

Từ ứng dụng **orders-api**, lập bảng cho local, it, staging và prod gồm **Spring profile**, **Vault URI**, **mount KV v2**, **logical key**, **auth method**, **nguồn cấp credential**, **TLS/CA** và **policy**. Phân loại giá trị nào có thể ghi trong Git, giá trị nào chỉ được cung cấp khi chạy.

### Bài 2 — Tạo hai mount không chia sẻ dữ liệu

Trên một Vault dev cục bộ, tạo **lab-kv/** và **ci-kv/** đều là KV v2. Ghi key **apps/orders/config** ở cả hai với hai giá trị **app_name** khác nhau. Dùng CLI kiểm tra mỗi mount trả dữ liệu riêng, sau đó cấu hình **training.vault.mount** theo profile để VaultTemplate đọc đúng.

### Bài 3 — Kiểm tra policy âm

Tạo token chỉ có **read** trên **ci-kv/data/apps/orders/config**. Chứng minh token không đọc được **lab-kv/data/apps/orders/config**, không ghi được **ci-kv/data/apps/orders/config** và không đọc được key Billing. Giải thích vì sao cùng logical key chưa có nghĩa cùng quyền.

### Bài 4 — Thất bại khi thiếu cấu hình

Chạy profile **it** mà không cung cấp URI test; xác nhận ứng dụng thất bại sớm. Cố ý cấu hình profile **prod** với HTTP hoặc URI local trong bộ kiểm tra startup và xác minh nó bị từ chối. Không cần kết nối tới Vault production thật để chạy phép thử này.

### Bài 5 — TLS và workload authentication

Thiết kế cách cung cấp CA truststore và auth method cho một pod Java tại staging. Giải thích sự khác nhau giữa cấu hình **VAULT_CACERT** của CLI và JVM truststore, giữa Kubernetes/JWT auth và AppRole secret ID, và cách xử lý token hết hạn.

### Bài 6 — Transit và PKI khi đổi môi trường

Liệt kê các yếu tố phải đổi khi một worker đang mã hóa qua Transit ở staging được triển khai sang production: **URL**, **auth role**, **policy**, **Transit mount/key**, khả năng giải mã ciphertext cũ và việc bảo vệ khóa. Đề xuất cách kiểm tra quyền **encrypt** mà không tự cấp **decrypt**. Làm tương tự với PKI issue role và CA.

## 14. Checklist hoàn thành

- [ ] Có profile **local**, **it**, **staging**, **prod** với các giá trị kết nối phù hợp và không chứa credential thật.
- [ ] **training.vault.*** đã được ứng dụng bind vào VaultTemplate/HTTP client; không giả định property tùy chỉnh có hiệu lực tự động.
- [ ] Local dùng dữ liệu giả và token giới hạn; root token chỉ dùng để bootstrap.
- [ ] CI chạy trên Vault tạm thời có mount/secret/policy riêng, endpoint động và token test được cấp lại mỗi run.
- [ ] Staging/production dùng **HTTPS**, kiểm tra CA/SAN và authentication dựa trên workload.
- [ ] KV v2 data path và metadata path được phân biệt; policy tối thiểu đúng mount và logical key.
- [ ] Transit encryption, PKI role, TTL/lease và yêu cầu rotation được xét riêng cho mỗi môi trường.
- [ ] Profile deploy không thể fallback sang localhost, root token lab hoặc mount thử nghiệm.
- [ ] Các tình huống thiếu biến môi trường, sai CA, sai quyền, Vault sealed và token hết hạn đã có phép thử hoặc phương án xử lý.
- [ ] Kế hoạch rollout/rollback không yêu cầu đưa secret vào artifact hoặc cấp quyền rộng ngoài nhu cầu.

**Kết quả mong đợi:** Cùng một codebase Java có thể sử dụng VaultTemplate trên máy cá nhân, trong kiểm thử và khi triển khai bằng **cấu hình, identity và policy riêng cho từng môi trường**. Ranh giới được kiểm chứng ở cả client lẫn Vault, giúp tránh truy cập nhầm secret, bảo vệ vòng đời credential và làm các ví dụ KV, Transit, PKI có thể lặp lại một cách an toàn.
