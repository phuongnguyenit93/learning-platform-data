# Cung cấp ClientAuthentication và tùy chọn xác thực

Trong chương **Cấu hình Java** của **SPRING_VAULT**, `VaultEndpoint` cho biết ứng dụng kết nối đến HashiCorp Vault nào, còn **`ClientAuthentication` quyết định ứng dụng lấy hoặc cung cấp credential dùng để gọi Vault như thế nào**. Sau khi xác thực thành công, Vault kiểm tra policy của danh tính đó trước khi cho phép đọc KV secrets, thực hiện Transit encryption hoặc truy cập PKI.

Bài học này tập trung vào việc cung cấp `ClientAuthentication` khi cấu hình Spring Vault bằng Java, lựa chọn phương thức đăng nhập theo môi trường và hiểu mối liên hệ giữa **authentication, authorization, token, session và lease**. Ví dụ chạy được ở local sử dụng `TokenAuthentication`; các phương án production như **AppRole** và **Kubernetes authentication** được phân tích theo luồng xác thực và yêu cầu cấu hình, tránh nhầm token demo với xác thực theo workload.

## 1. Vai trò của ClientAuthentication trong Spring Vault

`ClientAuthentication` là một giao diện trong package `org.springframework.vault.authentication`. Nó là điểm mở rộng cho cơ chế lấy token Vault đại diện cho danh tính mà ứng dụng sẽ sử dụng. Về mặt khái niệm, một triển khai cung cấp thao tác `login()` và trả một `VaultToken`; cách tạo token phụ thuộc vào phương thức authentication.

Điều quan trọng là phân biệt ba tầng:

| Tầng | Câu hỏi cần trả lời | Thành phần tiêu biểu |
| --- | --- | --- |
| Endpoint | Gửi request đến Vault server nào? | `VaultEndpoint` |
| Authentication | Workload chứng minh danh tính và có token bằng cách nào? | `ClientAuthentication` |
| Authorization | Token đó được phép thao tác API/path nào? | Vault policy gắn với token/role |

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng Spring
    participant Auth as ClientAuthentication
    participant Vault as HashiCorp Vault
    participant Ops as VaultTemplate

    App->>Auth: Yêu cầu credential
    alt TokenAuthentication
        Auth-->>App: Sử dụng token đã được cấp
    else Workload login
        Auth->>Vault: Đăng nhập bằng danh tính workload
        Vault-->>Auth: Trả token và thông tin TTL/policy
        Auth-->>App: Cung cấp token
    end
    App->>Ops: Đọc secret KV v2
    Ops->>Vault: Request dùng token
    Vault->>Vault: Kiểm tra policy
    Vault-->>Ops: Dữ liệu hoặc lỗi 403/404
~~~

Sơ đồ diễn đạt trách nhiệm logic, không áp đặt rằng mọi implementation luôn login mạng cho từng request. Spring Vault có thể dùng cơ chế **session/token management** để tái sử dụng hoặc làm mới token tùy cấu hình và khả năng của phương thức đăng nhập.

### Token có hợp lệ chưa đồng nghĩa có đủ quyền

Khi Vault chấp nhận một token, nó còn đánh giá các policy áp vào API path được gọi. Ví dụ, với KV v2 tại mount `secret` và secret `orders/api`, quyền đọc tối thiểu thường là:

~~~hcl
path "secret/data/orders/api" {
  capabilities = ["read"]
}
~~~

Một token dùng được để gọi API health hoặc đọc secret khác **không có nghĩa** token được phép đọc `secret/data/orders/api`. Nếu đọc bị từ chối, cần kiểm tra cả trạng thái xác thực lẫn policy.

## 2. Những phương thức xác thực thường dùng

Spring Vault hỗ trợ nhiều chiến lược xác thực, nhưng **không có một lựa chọn tốt nhất cho mọi workload**. Cách chọn phụ thuộc nơi ứng dụng chạy và credential gốc có thể được cấp an toàn theo cách nào.

| Phương thức | Credential khởi đầu | Trường hợp phù hợp | Lưu ý vận hành |
| --- | --- | --- | --- |
| **Token** | Token Vault có sẵn | Local, thử nghiệm, tích hợp tạm thời được kiểm soát | Không tự login, không tự gia hạn chỉ nhờ `TokenAuthentication` |
| **AppRole** | RoleID và thông thường là SecretID | Workload tự vận hành ngoài Kubernetes, CI hoặc máy chủ có kênh cấp SecretID an toàn | Bảo vệ SecretID, xét wrapping, giới hạn TTL/uses, role và policy |
| **Kubernetes** | JWT của ServiceAccount | Ứng dụng chạy trong Kubernetes | Vault role phải khớp ServiceAccount, namespace và audience khi dùng |
| **AWS IAM/EC2** | Bằng chứng danh tính AWS từ môi trường chạy | Workload chạy trên AWS | Hạn chế IAM role/principal, bảo đảm cơ chế ký và endpoint Vault phù hợp |
| **GCP IAM/GCE** | Bằng chứng danh tính Google Cloud | Workload chạy trên Google Cloud | Ràng buộc service account và quyền cấp token đúng mục đích |
| **TLS certificate auth** | Chứng chỉ client và private key | Môi trường đã vận hành mTLS/PKI cho workload | Yêu cầu quản lý khóa riêng, CA và vòng đời chứng chỉ |
| **Userpass/LDAP/OIDC** | Thông tin đăng nhập hoặc phiên người dùng | Người dùng hoặc công cụ tương tác | Thường không phải lựa chọn chính cho service chạy lâu dài |

Một số tên class được dùng phổ biến trong Spring Vault là `TokenAuthentication`, `AppRoleAuthentication` và `KubernetesAuthentication`; các provider và chữ ký constructor/options cụ thể có thể thay đổi theo phiên bản Spring Vault. Với cloud hoặc TLS authentication, kiểm tra module và API được hỗ trợ trong **phiên bản thư viện thực tế** trước khi tích hợp.

**Nguyên tắc lựa chọn:** ưu tiên danh tính mà môi trường chạy có thể chứng minh một cách tự nhiên. Workload trong Kubernetes thường nên dùng Kubernetes auth; một quy trình chạy trong môi trường AWS/GCP có thể dùng danh tính cloud tương ứng. Token tĩnh là công cụ học tập thuận tiện nhưng không nên trở thành mặc định cho service production.

## 3. Cấu hình Java tối thiểu với TokenAuthentication

Để nhìn thấy rõ vai trò của giao diện `ClientAuthentication`, bắt đầu với một Vault dev server và một token đã được tạo.

### 3.1. Thêm dependency

Với dự án Spring Boot, bổ sung thư viện chính của Spring Vault:

~~~xml
<dependency>
    <groupId>org.springframework.vault</groupId>
    <artifactId>spring-vault-core</artifactId>
</dependency>
~~~

Ví dụ này giả định project có dependency management hoặc BOM quản lý phiên bản Spring Vault tương thích với Spring Framework. Nếu không có, cần khai báo phiên bản cụ thể phù hợp. Đoạn mã dùng Java 17 trở lên.

### 3.2. Chuẩn bị Vault local và secret thử nghiệm

Khởi chạy dev server trong terminal riêng:

~~~bash
vault server -dev -dev-root-token-id=dev-only-token
~~~

Trong terminal khác trên Bash:

~~~bash
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=dev-only-token

vault kv put secret/orders/api apiKey=demo-only-key
vault kv get secret/orders/api
~~~

Với PowerShell, đặt biến môi trường như sau:

~~~powershell
$env:VAULT_ADDR = "http://127.0.0.1:8200"
$env:VAULT_TOKEN = "dev-only-token"
~~~

Ví dụ giả định dev server có KV v2 ở mount `secret`. Có thể xác nhận bằng `vault secrets list -detailed`. Lệnh `kv put` phải chạy trong môi trường đã có `VAULT_ADDR` và `VAULT_TOKEN`.

**Root token của dev server chỉ dùng trong lab.** Ứng dụng production không dùng root token, token mẫu hay kết nối HTTP plaintext.

### 3.3. Cung cấp ClientAuthentication bằng AbstractVaultConfiguration

Tạo `AppVaultConfiguration.java` trong package được Spring Boot quét:

~~~java
package com.example.vault;

import java.net.URI;
import java.util.Locale;

import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.config.AbstractVaultConfiguration;

@Configuration
public class AppVaultConfiguration extends AbstractVaultConfiguration {

    private final Environment environment;

    public AppVaultConfiguration(Environment environment) {
        this.environment = environment;
    }

    @Override
    public VaultEndpoint vaultEndpoint() {
        URI uri = URI.create(
                environment.getRequiredProperty("VAULT_ADDR"));

        String scheme = uri.getScheme();
        if (uri.getHost() == null
                || (!"http".equalsIgnoreCase(scheme)
                    && !"https".equalsIgnoreCase(scheme))) {
            throw new IllegalArgumentException(
                    "VAULT_ADDR phải là URL http(s)://host[:port]");
        }

        int port = uri.getPort() >= 0
                ? uri.getPort()
                : ("https".equalsIgnoreCase(scheme) ? 443 : 80);

        VaultEndpoint endpoint = VaultEndpoint.create(uri.getHost(), port);
        endpoint.setScheme(scheme.toLowerCase(Locale.ROOT));
        return endpoint;
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        String token = environment.getRequiredProperty("VAULT_TOKEN");
        if (token.isBlank()) {
            throw new IllegalArgumentException(
                    "VAULT_TOKEN không được để trống");
        }
        return new TokenAuthentication(token);
    }
}
~~~

Ở lớp kế thừa `AbstractVaultConfiguration`, hai phương thức cần cung cấp là:

- `vaultEndpoint()`: xác định địa chỉ server Vault.
- `clientAuthentication()`: trả về cách xác thực dùng bởi hạ tầng Spring Vault.

`AbstractVaultConfiguration` cung cấp các bean hạ tầng, trong đó có `VaultTemplate`, nên không cần định nghĩa thêm một `@Bean VaultTemplate` riêng cho ví dụ này.

**Vì sao lấy token từ môi trường?** `Environment.getRequiredProperty("VAULT_TOKEN")` buộc ứng dụng có giá trị token tại runtime và tránh ghi token vào source. Tuy nhiên, biến môi trường vẫn là một kênh cấp credential cần kiểm soát quyền truy cập, log và công cụ chẩn đoán. Khi đưa lên production, thay `TokenAuthentication` bằng phương án auth theo workload.

**Vì sao không mặc định token?** Nếu quên cấp token, ứng dụng nên lỗi sớm thay vì tự sử dụng root token demo. Trong thực tế, việc tạo bean `TokenAuthentication` thành công chỉ chứng tỏ có chuỗi token, **chưa chứng tỏ token được Vault chấp nhận**; phải gửi request thực để kiểm tra.

## 4. Đọc KV v2 qua VaultTemplate sau khi xác thực

Tạo `OrdersSecretReader.java`:

~~~java
package com.example.vault;

import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

@Service
public class OrdersSecretReader {

    private final VaultTemplate vaultTemplate;

    public OrdersSecretReader(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public String readApiKey() {
        VaultResponse response = vaultTemplate
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("orders/api");

        Map<String, Object> data =
                response == null ? null : response.getData();

        Object value = data == null ? null : data.get("apiKey");
        if (!(value instanceof String key) || key.isBlank()) {
            throw new IllegalStateException(
                    "Secret thiếu trường apiKey tại secret/orders/api");
        }
        return key;
    }
}
~~~

Trong lớp có `@SpringBootApplication`, có thể thêm bean để xác minh khi khởi động:

~~~java
@Bean
CommandLineRunner verifyVault(OrdersSecretReader reader) {
    return args -> {
        reader.readApiKey();
        System.out.println("Đã xác thực và đọc secret KV v2 thành công");
    };
}
~~~

Đoạn trên cần import `org.springframework.boot.CommandLineRunner` và `org.springframework.context.annotation.Bean`; nó là phương thức đặt trong một class Spring configuration, không phải file Java độc lập. Chỉ in trạng thái, **không in token hay apiKey**.

Request đọc tương ứng với đường dẫn HTTP:

~~~text
GET /v1/secret/data/orders/api
~~~

Trong `opsForKeyValue("secret", KV_2)`, `secret` là **mount**; trong `get("orders/api")`, `orders/api` là **đường dẫn secret tương đối**. Spring Vault xử lý đoạn `data` của KV v2. Nếu token thiếu quyền `read` trên `secret/data/orders/api`, request có thể bị Vault từ chối dù endpoint kết nối tốt.

## 5. Từ token tĩnh đến AppRole

**AppRole** là một auth method của Vault thường dùng với workload tự vận hành hoặc hệ thống tự động có thể nhận credential qua kênh cấp phát an toàn. Nó không yêu cầu người dùng tương tác mỗi lần ứng dụng khởi động.

### 5.1. RoleID, SecretID và token khác nhau thế nào?

| Thành phần | Vai trò | Cách xử lý |
| --- | --- | --- |
| RoleID | Định danh AppRole cần login | Không coi là credential đủ để login trong cấu hình có SecretID |
| SecretID | Bằng chứng bổ sung để login | Bảo vệ như secret; cấp qua kênh an toàn, giới hạn TTL/uses khi phù hợp |
| Vault token | Được Vault trả sau khi AppRole login hợp lệ | Có policy, TTL và khả năng renew/revoke phụ thuộc cấu hình |
| Vault role/policy | Ràng buộc quyền và vòng đời token | Thiết lập bên Vault; không tự sinh từ client Java |

Luồng thường gặp:

~~~mermaid
sequenceDiagram
    participant Deploy as Hệ thống triển khai
    participant Java as Ứng dụng Java
    participant Vault as Vault AppRole
    Deploy-->>Java: Cấp RoleID và SecretID an toàn
    Java->>Vault: POST auth/approle/login
    Note right of Java: role_id + secret_id
    Vault-->>Java: Client token và TTL
    Java->>Vault: Gọi KV API với client token
    Vault-->>Java: Kết quả theo policy
~~~

Để hình dung cấu hình phía Vault, giả sử quản trị viên đã tạo policy `orders-read` với quyền đọc KV v2. Một ví dụ lab cấp role:

~~~bash
vault auth enable approle
vault write auth/approle/role/orders-reader \
  token_policies="orders-read" \
  token_ttl="30m" \
  token_max_ttl="1h"

vault read auth/approle/role/orders-reader/role-id
vault write -f auth/approle/role/orders-reader/secret-id
~~~

**Không ghi SecretID vào log hay tài liệu chia sẻ.** Có thể sử dụng response wrapping, giới hạn SecretID TTL/uses và kênh giao nhận credential của nền tảng để giảm nguy cơ lộ. Trong production, hệ thống vận hành cần thiết kế cách cấp RoleID/SecretID và thu hồi/luân chuyển chúng.

### 5.2. Cung cấp AppRoleAuthentication trong Java

Ở tầng Java, `clientAuthentication()` vẫn phải **trả một `ClientAuthentication`**. Khác với `TokenAuthentication`, triển khai AppRole cần options (RoleID, SecretID, auth mount path nếu khác mặc định) **và HTTP client/RestOperations phục vụ login**. Ví dụ dạng định hướng:

~~~text
RoleID + SecretID (do workload nhận an toàn)
    |
    v
AppRoleAuthenticationOptions
    |
    v
AppRoleAuthentication(options, loginRestOperations)
    |
    v
ClientAuthentication -> Vault token -> VaultTemplate
~~~

Các class thường dùng là `AppRoleAuthentication` và `AppRoleAuthenticationOptions`. Khi code trên phiên bản Spring Vault cụ thể, sử dụng API builder và constructor của phiên bản đó; bảo đảm `loginRestOperations` trỏ tới Vault endpoint phù hợp và **không phụ thuộc vòng vào một `VaultTemplate` đang đòi token để khởi tạo**.

Đừng tạo `VaultTemplate` chỉ để login rồi dùng chính instance đó để xây authentication, vì có thể tạo vòng phụ thuộc hoặc khiến request login đòi token chưa tồn tại. Trách nhiệm của client login và client gọi API đã xác thực nên được tách rõ trong cấu hình.

**Đổi sang AppRole không có nghĩa bỏ qua policy.** Chính Vault xác định policy của token được phát hành theo role.

## 6. Xác thực Kubernetes theo danh tính workload

Trên Kubernetes, một service chạy trong Pod thường có một ServiceAccount. Khi Vault Kubernetes auth đã được cấu hình, ứng dụng có thể chứng minh danh tính bằng **ServiceAccount JWT** được Kubernetes phát hành và nhận Vault token theo role tương ứng.

### 6.1. Các thành phần liên quan

| Thành phần | Nơi cấu hình | Ý nghĩa |
| --- | --- | --- |
| Kubernetes ServiceAccount | Kubernetes | Danh tính của Pod/workload |
| Projected ServiceAccount JWT | Pod filesystem hoặc cơ chế cấp token được cấu hình | Bằng chứng gửi khi login vào Vault |
| Vault Kubernetes auth mount | Vault | Endpoint `auth/kubernetes/login` (hoặc mount khác) |
| Vault Kubernetes role | Vault | Ràng buộc ServiceAccount, namespace, audience và policy |
| `KubernetesAuthentication` | Ứng dụng Spring Vault | Provider thực hiện login để lấy token |

Ví dụ thiết kế role phía Vault, giả định Kubernetes auth đã được bật và cấu hình để xác minh JWT:

~~~bash
vault write auth/kubernetes/role/orders-reader \
  bound_service_account_names=orders-api \
  bound_service_account_namespaces=production \
  policies=orders-read \
  ttl=1h
~~~

Khi triển khai thật, role có thể cần audience và các ràng buộc bổ sung phù hợp issuer, phiên bản Kubernetes, cách mount ServiceAccount token và chính sách của cluster. Không mặc nhiên giả định mọi Pod đều tự mount JWT hoặc JWT được chấp nhận cho mọi audience.

Luồng logic:

~~~mermaid
sequenceDiagram
    participant Pod as Orders Pod
    participant K8s as Kubernetes
    participant Vault as Vault Kubernetes Auth
    K8s-->>Pod: ServiceAccount JWT
    Pod->>Vault: auth/kubernetes/login (role, jwt)
    Vault->>Vault: Kiểm tra ServiceAccount/namespace/audience
    Vault-->>Pod: Vault token gắn policy
    Pod->>Vault: Đọc secret bằng Vault token
~~~

### 6.2. Điều gì thay đổi trong mã Java?

Phần `vaultEndpoint()` có thể giữ nguyên vì địa chỉ Vault độc lập với cách đăng nhập. Phần `clientAuthentication()` sẽ tạo provider `KubernetesAuthentication` với options tương ứng như **tên role**, đường dẫn hoặc nguồn đọc JWT, auth mount path và HTTP client đăng nhập.

Điểm quan trọng không nằm ở việc hardcode một JWT vào source, mà ở việc provider đọc được **JWT thuộc Pod hiện tại**, xử lý đúng vị trí của file token và vòng đời token sau khi Vault cấp. API constructor/builder của `KubernetesAuthentication` thay đổi theo thế hệ Spring Vault; tham chiếu tài liệu của phiên bản đang dùng khi hiện thực chi tiết.

Các lỗi thường gặp trong Kubernetes auth bao gồm:
- Pod chạy bằng ServiceAccount khác tên role đã bind.
- Namespace của Pod nằm ngoài phạm vi role.
- JWT hết hạn, không còn mount hoặc sai audience/issuer.
- Vault chưa cấu hình Kubernetes auth đúng với cluster.
- Login thành công nhưng policy của Vault token thiếu quyền đọc secret.

Đối với các lỗi trên, việc đổi `VAULT_ADDR` hoặc lặp lại request KV sẽ không tự giải quyết sai role, audience hay policy.

## 7. Xác thực cloud, TLS certificate và các trường hợp khác

Nếu ứng dụng không chạy trên Kubernetes, có thể chọn hình thức xác thực phù hợp với môi trường nền tảng:

- **AWS IAM/EC2 authentication:** Vault xác minh bằng chứng danh tính AWS, phù hợp workload AWS có IAM role phù hợp. Tránh phát hành và lưu một Vault token dài hạn khi môi trường đã có identity có thể kiểm chứng.
- **GCP IAM/GCE authentication:** Workload sử dụng danh tính Google Cloud phù hợp với Vault auth role đã ràng buộc service account.
- **TLS certificate authentication:** Client có chứng chỉ và private key được cấp an toàn, Vault ràng buộc thông tin chứng chỉ với role/policy. Ngoài xác minh TLS của server, phải quản lý vòng đời chứng chỉ client và khả năng thu hồi.
- **Userpass, LDAP hoặc OIDC:** Phù hợp hơn với các tình huống tương tác theo người dùng hoặc những hệ thống có yêu cầu đặc thù; cần tránh để mật khẩu cá nhân thành credential của dịch vụ chạy liên tục.

Ở mọi trường hợp, `ClientAuthentication` chỉ giải quyết **cách xác thực**. Vault auth mount, role binding và policy của token phải được thiết lập ở phía Vault. Không gửi một credential của cloud A đến auth backend của cloud B hoặc cho rằng role có cùng tên trên hai môi trường tương đương nhau.

## 8. SessionManager, vòng đời token và lease

Phân biệt bốn khái niệm là bắt buộc khi thiết kế ứng dụng chạy lâu dài:

| Khái niệm | Mục đích | Ví dụ |
| --- | --- | --- |
| `ClientAuthentication` | Có token Vault từ credential khởi đầu | Token, AppRole, Kubernetes |
| Vault token | Credential gọi các API Vault; mang policy và TTL | Token được trả sau login |
| Session/token management | Tái sử dụng, kiểm tra hoặc làm mới token tùy khả năng | `SessionManager` và cơ chế lifecycle của Spring Vault |
| Lease của secret động | Vòng đời quyền truy cập một secret do engine phát hành | Database dynamic credentials, một số loại chứng chỉ |

Spring Vault có abstraction như `SessionManager` và triển khai quản lý vòng đời token. Tuy nhiên, **`ClientAuthentication` và session manager không phải một đối tượng**, và việc có `AbstractVaultConfiguration` không đồng nghĩa tất cả token đều được tự động gia hạn bất kể loại token.

Đặc biệt:

1. `TokenAuthentication` nhận **token có sẵn**; bản thân nó không tự login lại để tạo token mới khi token cũ bị revoke.
2. Với phương thức auth tạo token mới, khả năng login lại hoặc renew token phụ thuộc vào loại token, quyền renew, TTL, session manager, version và cấu hình.
3. Một token đã revoke sẽ không còn dùng được; không nên retry vô hạn cùng một credential thất bại.
4. Đọc secret **KV tĩnh** thường không tạo lease mới cho mỗi lần đọc, nhưng **token gọi Vault vẫn có TTL** và khả năng bị thu hồi.
5. Transit encryption và PKI có API và quyền riêng; credential cấp cho các API này vẫn được quản lý ở tầng token/authentication.

Do đó, không nên kết luận “service chạy được lúc khởi động” nghĩa là nó luôn đọc được secret sau nhiều giờ. Cần kiểm thử thời điểm token hết TTL, renew thất bại, credential gốc thay đổi và Vault tạm thời unavailable.

### Chọn mô hình lấy token khi deploy

| Tình huống | Cách tiếp cận |
| --- | --- |
| Bài thực hành vài phút | Token demo đọc từ biến môi trường |
| Service Kubernetes chạy nhiều ngày | Kubernetes auth, session management phù hợp, role/policy ít quyền |
| Batch job ngoài Kubernetes | AppRole hoặc identity nền tảng, TTL giới hạn tương ứng job |
| Service AWS/GCP | Ưu tiên auth gắn với danh tính cloud hiện hữu khi khả thi |
| Credential động có lease | Quản lý thêm renew/revoke của secret tùy secrets engine |

Không in token hoặc metadata nhạy cảm vào stdout khi kiểm tra thời gian sống; dùng chỉ số, mã lỗi và thông tin trạng thái đã kiểm soát.

## 9. Thiết kế cấu hình cho nhiều môi trường

Có hai cách phổ biến để áp dụng các lựa chọn xác thực mà không phân tán logic đăng nhập ở mọi service:

**Cách 1: Mỗi môi trường có một lớp cấu hình được chọn rõ ràng.** Ví dụ profile `local` cấu hình `TokenAuthentication`, profile `prod-k8s` cấu hình `KubernetesAuthentication`. Cách này giúp mỗi đường đăng nhập có dependencies rõ, nhưng phải tránh tạo hai `AbstractVaultConfiguration` cùng lúc.

**Cách 2: Một lớp cấu hình phân nhánh theo thuộc tính `app.vault.auth-method`.** Thuộc tính có thể chọn `token`, `approle` hoặc `kubernetes`; mỗi nhánh tạo provider khác. Cách này phù hợp nếu số phương án ít và code quản lý được đầy đủ options, session và phụ thuộc HTTP login.

Dù chọn cách nào, hãy tách các cấu hình:

~~~yaml
# Ví dụ quy ước thuộc tính ứng dụng, không phải auto-config chuẩn của Spring Vault
app:
  vault:
    auth-method: kubernetes
    auth-role: orders-reader
    auth-mount: kubernetes
~~~

**Không thêm `role_id`, `secret_id`, JWT hay token thật trực tiếp vào file YAML commit vào Git.** Đây là các giá trị bí mật hoặc thông tin định danh phụ thuộc môi trường, cần được cấp qua kênh phù hợp tại runtime.

Đặc biệt tránh hai tình huống:
- Vừa kế thừa `AbstractVaultConfiguration` để đăng ký `VaultTemplate`, vừa kích hoạt một cấu hình khác tạo cùng hạ tầng mà không kiểm soát bean name/qualifier.
- Tạo provider login phụ thuộc vào bean `VaultTemplate` đã xác thực để rồi chính `VaultTemplate` lại phụ thuộc vào provider login đó.

Nếu đã dùng **Spring Cloud Vault Config**, kiểm tra khả năng auto-configuration và quản lý authentication của nó trước khi chủ động thêm một `AbstractVaultConfiguration` nữa.

## 10. Xử lý lỗi: xác thực hay phân quyền?

Các triệu chứng dưới đây có thể có cùng kết quả “đọc secret thất bại”, nhưng cách xử lý khác nhau.

| Triệu chứng | Giả thuyết cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Thiếu `VAULT_TOKEN` khi tạo bean local | Chưa cấp credential runtime | Cấp biến môi trường cho process Java; không hardcode mặc định |
| Kết nối bị từ chối, timeout, DNS lỗi | `VaultEndpoint` hoặc mạng | Kiểm tra URL, cổng, DNS, firewall, trạng thái Vault |
| TLS handshake lỗi | CA/trust store, chứng chỉ, hostname | Sửa trust/TLS; không tắt xác minh chứng chỉ |
| Login AppRole không thành công | RoleID/SecretID sai, hết TTL/uses, auth mount sai | Kiểm tra role, kênh cấp SecretID và cấu hình auth mount |
| Login Kubernetes thất bại | ServiceAccount/namespace/audience không khớp | Kiểm tra JWT, ràng buộc role và cấu hình Kubernetes auth |
| Lỗi permission denied/403 | Token không hợp lệ **hoặc** policy thiếu quyền | Kiểm tra identity thực tế, trạng thái token, policy và đường dẫn API |
| Secret KV không tồn tại/null/404 | Sai mount, secret path hoặc KV version | Kiểm tra `secret`, `orders/api` và `KV_2` |
| Chạy được ban đầu, sau đó bị từ chối | Token hết TTL, revoke hoặc session refresh lỗi | Kiểm tra chiến lược token/session và vòng đời credential |
| App có nhiều bean `VaultTemplate` | Cấu hình hạ tầng chồng lấn | Kiểm tra cấu hình Spring Vault/Cloud Vault và bean được inject |

Một HTTP status riêng lẻ không luôn xác định duy nhất nguyên nhân: tùy endpoint/auth method, lỗi token và lỗi quyền có thể xuất hiện dưới những dạng khác nhau. Cần kết hợp thông tin từ policy, auth role, trạng thái token và audit log Vault, đồng thời **không log credential hoặc nội dung secret**.

### Tình huống minh họa

Ứng dụng Kubernetes login thành công, nhận token, nhưng `vaultTemplate.opsForKeyValue("secret", KV_2).get("orders/api")` bị 403.

Cách phân tích:
1. Xác nhận request đang dùng danh tính của Pod/role mong muốn, không phải token người vận hành.
2. Xác nhận policy gắn với Vault token có quyền `read` trên `secret/data/orders/api`.
3. Xác nhận mount thực sự là KV v2 tại `secret`; KV v1 dùng path khác.
4. Sau khi sửa policy/role, xác minh token mới nhận policy đúng và chạy lại một phép đọc có kiểm soát.

Lặp request liên tục hoặc thay mật khẩu ứng dụng không giải quyết được lỗi thiếu `read`.

## 11. Kiểm thử tích hợp và giám sát

Một test đơn vị mock `ClientAuthentication` chỉ kiểm tra cách service sử dụng abstraction. Muốn chứng minh cơ chế login thực sự hoạt động, cần Vault test instance hoặc môi trường tích hợp có auth backend và role được cấu hình đúng.

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| Token demo hợp lệ + policy `read` KV v2 | `VaultTemplate` đọc được `apiKey` |
| Token không hợp lệ hoặc đã revoke | Thao tác bị từ chối; không trả một secret mặc định giả |
| Token đúng, policy không có `read` | Lỗi quyền được nhận diện, không bị xử lý thành “secret không tồn tại” |
| Sai mount KV v1/KV v2 | Không nhầm đường dẫn API hoặc bao dữ liệu trả về |
| AppRole SecretID sai/hết hạn | Login thất bại theo đúng cơ chế; không tự chuyển sang root token |
| Kubernetes role không bind ServiceAccount/namespace | Login bị từ chối an toàn |
| Token hết TTL hoặc Vault tạm unavailable | Hành vi renew/login lại/retry đúng với chiến lược đã thiết kế |
| Thay nguồn auth theo môi trường | Chỉ provider dự kiến được tạo và service dùng đúng `VaultTemplate` |

Có thể sử dụng Vault dev server hoặc Testcontainers để chạy test tích hợp cho Token/AppRole trong môi trường cô lập; Kubernetes auth cần hạ tầng kiểm thử mô phỏng hoặc cluster phù hợp với cơ chế xác minh JWT. Đừng suy ra Kubernetes auth hoạt động chỉ vì mock provider trả một token tùy ý.

Chỉ số giám sát hữu ích gồm tỷ lệ login thành công/thất bại, lỗi refresh hoặc renew token, độ trễ đọc Vault, nhóm HTTP status và khả năng kết nối. Tránh đưa token, SecretID, JWT, khóa Transit, private key PKI hoặc nội dung KV vào log, span hoặc metric label. Audit log Vault có thể giúp điều tra danh tính và policy khi được vận hành với quyền truy cập thích hợp.

## 12. Câu hỏi tự luyện

1. `ClientAuthentication` khác `VaultEndpoint` và Vault policy ở điểm nào?
2. Vì sao `new TokenAuthentication(token)` không có nghĩa token sẽ tự đăng nhập lại khi hết hạn?
3. Trong AppRole, RoleID và SecretID có vai trò khác nhau thế nào? Vì sao không nên lưu SecretID trong repository?
4. Một Pod dùng ServiceAccount khác với role binding của Vault có thể được cấp token không?
5. Với secret KV v2 tại `secret/orders/api`, policy `read` cần cấp trên đường dẫn nào?
6. Vì sao service có thể đọc KV secret thành công ngay sau deploy nhưng vài giờ sau lại nhận lỗi xác thực?
7. Khi ứng dụng báo 403, nên kiểm tra token/policy ra sao trước khi nghi ngờ DNS hoặc TLS?

**Kết quả mong đợi:** bạn có thể cung cấp một `ClientAuthentication` hợp lệ qua cấu hình Java, chạy ví dụ `TokenAuthentication` để đọc KV v2, giải thích khi nào chuyển sang AppRole hoặc Kubernetes auth, đồng thời phân biệt rõ vòng đời token/session với lease của secret động. Từ đó, ứng dụng Java có nền tảng để tích hợp VaultTemplate với policy ít quyền nhất, Transit encryption, PKI, xử lý lỗi và kiểm thử tích hợp trong SPRING_VAULT.

