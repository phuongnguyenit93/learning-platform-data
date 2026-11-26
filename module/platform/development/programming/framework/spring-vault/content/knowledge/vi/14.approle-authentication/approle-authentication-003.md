# Cung cấp trực tiếp RoleId và SecretId

## Mục tiêu và phạm vi

Trong chương **Xác thực AppRole** của **SPRING_VAULT**, bài này tập trung vào trường hợp ứng dụng Java **đã nhận được RoleID và SecretID từ hệ thống triển khai** và cung cấp trực tiếp hai giá trị đó cho Spring Vault bằng:

~~~java
.roleId(RoleId.provided(roleId))
.secretId(SecretId.provided(secretId))
~~~

Đây là một cách cấu hình `AppRoleAuthenticationOptions` để `AppRoleAuthentication` có thể đăng nhập HashiCorp Vault, lấy client token và cho `VaultTemplate` truy cập KV secrets, Transit hoặc PKI theo chính sách phân quyền. Bài làm rõ ý nghĩa của “cung cấp trực tiếp”, cách lấy và chuyển giao credential, cách viết ứng dụng hoàn chỉnh, giới hạn vòng đời và các lỗi thường gặp.

Sau bài học, bạn có thể:

- Giải thích chính xác **RoleID, SecretID và client token** có vai trò gì khi Java đăng nhập bằng AppRole.
- Phân biệt **`provided(...)`** với cơ chế `pull(...)` và `wrapped(...)`; biết lúc nào chọn cung cấp trực tiếp.
- Cấu hình một AppRole với policy tối thiểu, chuyển RoleID/SecretID tới ứng dụng qua kênh được quản lý và triển khai `AbstractVaultConfiguration`.
- Đọc dữ liệu từ KV v2 bằng `VaultTemplate` mà không dùng token quản trị trong ứng dụng.
- Phát hiện tình huống SecretID hết hạn, hết lượt dùng, bị lộ, token hết hạn hoặc token không đủ quyền.

Ví dụ dùng Vault dev/lab và Spring Vault **4.1.x** với Java 17 trở lên. Tùy phiên bản Spring Vault, một vài constructor có thể khác; nên kiểm tra Javadoc của bản dependency đang chạy. Những giá trị TTL, tên role và path trong bài chỉ là ví dụ có thể thay đổi. Không đưa credential thực vào mã nguồn, Git hoặc log.

## 1. “Cung cấp trực tiếp” nghĩa là gì?

Giả sử ứng dụng `invoice-worker` chạy trong một môi trường triển khai nội bộ. Một **provisioner** có quyền quản lý AppRole ở Vault sẽ đọc RoleID và phát SecretID. Provisioner chuyển hai giá trị tới instance ứng dụng qua kênh tin cậy như secret injection hoặc file mount có quyền truy cập hạn chế. Ứng dụng **không cần tự gọi API quản trị để tạo SecretID**; nó nhận giá trị rồi đăng nhập.

~~~mermaid
sequenceDiagram
    autonumber
    participant Ops as Vault admin / provisioner
    participant Vault as HashiCorp Vault
    participant Deploy as Hệ thống triển khai
    participant Java as Spring Vault / Java
    participant KV as KV v2
    Ops->>Vault: Cấu hình role và policy
    Ops->>Vault: Đọc RoleID, tạo SecretID
    Vault-->>Ops: RoleID + SecretID
    Ops->>Deploy: Phân phối credential an toàn
    Deploy-->>Java: VAULT_ROLE_ID, VAULT_SECRET_ID
    Java->>Java: RoleId.provided + SecretId.provided
    Java->>Vault: POST /v1/auth/approle/login
    Vault-->>Java: client_token + TTL + policies
    Java->>KV: Đọc secret bằng client_token
    KV-->>Java: Dữ liệu hoặc lỗi ACL
~~~

**Ba khái niệm phải tách biệt:**

| Thành phần | Ai cấp / quản lý? | Dùng ở đâu? | Có thể sử dụng để đọc KV trực tiếp? |
| --- | --- | --- | --- |
| **RoleID** | Vault tạo cho AppRole; provisioner đọc và chuyển cho workload | Trường `role_id` của yêu cầu AppRole login | **Không** |
| **SecretID** | Vault phát cho AppRole hoặc nhận SecretID tùy chỉnh; provisioner chuyển cho workload | Trường `secret_id` của yêu cầu AppRole login | **Không** |
| **Client token** | Vault cấp sau khi login thành công | Header `X-Vault-Token` của các request tiếp theo | **Có**, trong phạm vi policy, TTL và ràng buộc token |

RoleID luôn bắt buộc ở AppRole login. Với cấu hình mặc định `bind_secret_id=true`, SecretID cũng bắt buộc. RoleID không thay thế SecretID, và SecretID không phải Vault token. Token do Vault cấp mới mang policy cho các endpoint KV, Transit hoặc PKI.

### 1.1. Cách “provided” hoạt động

`AppRoleAuthenticationOptions.RoleId.provided(String)` và `AppRoleAuthenticationOptions.SecretId.provided(String)` nhận **chuỗi credential đã có**. Spring Vault giữ các giá trị trong đối tượng cấu hình để dùng khi login. API này **không tự tạo** RoleID, SecretID và **không tự xoay vòng** credential.

~~~java
String roleId = obtainRoleIdFromTrustedSource();
String secretId = obtainSecretIdFromTrustedSource();

AppRoleAuthenticationOptions options =
        AppRoleAuthenticationOptions.builder()
                .roleId(RoleId.provided(roleId))
                .secretId(SecretId.provided(secretId))
                .build();
~~~

Hai hàm `obtain...FromTrustedSource()` là chỗ tích hợp với nền tảng triển khai của bạn, không phải API Spring Vault. Ví dụ hoàn chỉnh bên dưới sẽ dùng biến môi trường cho lab. `.build()` chỉ tạo options, còn `AppRoleAuthentication.login()` mới thực hiện request xác thực.

### 1.2. Khi nào nên dùng `provided(...)`?

- Provisioner đã cấp RoleID/SecretID và có cơ chế secret injection tại thời điểm khởi động.
- Ứng dụng không được cấp token có quyền đọc/cấp phát credential AppRole.
- Workload có vòng đời phù hợp với TTL và giới hạn số lần sử dụng SecretID, hoặc có quy trình cấp credential mới khi restart.
- Môi trường triển khai có thể quản lý quyền truy cập, audit và rotation của credential.

Nếu hệ thống muốn ứng dụng **tự lấy SecretID** bằng một bootstrap Vault token, đó là `SecretId.pull(...)`, với rủi ro và quyền ACL khác. Nếu môi trường chuyển giao **wrapping token chỉ dùng một lần** rồi mới unwrap lấy SecretID, đó là `SecretId.wrapped(...)`. `provided(...)` không nhận wrapping token thay cho SecretID: truyền wrapping token vào `SecretId.provided(...)` sẽ khiến login không hợp lệ.

## 2. Chuẩn bị Vault: policy, role và dữ liệu thử nghiệm

Các lệnh phần này chỉ chạy bởi **Vault admin/provisioner** trong môi trường lab. Giả sử Vault đã init/unseal, CLI có token đủ quyền quản trị và `VAULT_ADDR` trỏ tới Vault dev.

### Bước 1. Kích hoạt AppRole và KV v2

~~~bash
# Địa chỉ HTTP chỉ dùng trong local lab.
export VAULT_ADDR="http://127.0.0.1:8200"

# Chỉ chạy nếu AppRole chưa được mount tại auth/approle:
vault auth enable approle

# Chỉ chạy nếu KV v2 chưa được mount tại secret/:
vault secrets enable -path=secret -version=2 kv

# Secret giả dùng để kiểm tra. Không đặt dữ liệu sản xuất vào shell history.
vault kv put secret/apps/invoice-worker greeting="vault-ready"
~~~

Nếu mount đã tồn tại, lệnh enable sẽ báo lỗi trùng; hãy kiểm tra cấu hình hiện có và bỏ qua lệnh bật trùng, không tạo nhiều mount ngoài ý muốn.

### Bước 2. Tạo policy chỉ đọc đúng một secret

Tạo tệp `invoice-worker-read.hcl` trên máy quản trị:

~~~hcl
path "secret/data/apps/invoice-worker" {
  capabilities = ["read"]
}
~~~

Ghi policy vào Vault:

~~~bash
vault policy write invoice-worker-read invoice-worker-read.hcl
~~~

Path `secret/data/apps/invoice-worker` là **API path của KV v2**. CLI `vault kv get secret/apps/invoice-worker` và lời gọi `opsForKeyValue("secret", KV_2).get("apps/invoice-worker")` đều tương ứng với dữ liệu đó. Không cấp `create`, `update`, `delete` hoặc quyền quản trị AppRole cho workload chỉ cần đọc.

### Bước 3. Tạo role với giới hạn nhận biết được

~~~bash
vault write auth/approle/role/invoice-worker \
  bind_secret_id=true \
  token_policies="invoice-worker-read" \
  secret_id_ttl=20m \
  secret_id_num_uses=3 \
  token_ttl=15m \
  token_max_ttl=1h \
  token_type=service \
  token_num_uses=0

vault read auth/approle/role/invoice-worker
~~~

Các lựa chọn trên có nghĩa:

- AppRole yêu cầu **RoleID và SecretID** khi login.
- SecretID mới có thời hạn tối đa 20 phút và được dùng đăng nhập nhiều nhất 3 lần.
- Client token có TTL ban đầu được cấu hình là 15 phút, chịu giới hạn gia hạn tối đa và các giới hạn chung của Vault. `token_type=service` phù hợp khi có nhu cầu quản lý/gia hạn phiên.
- Token gắn policy `invoice-worker-read`; `token_num_uses=0` không giới hạn số request được gửi bằng token trong TTL.
- TTL của SecretID **không phải** TTL của token. SecretID hết hạn không lập tức vô hiệu một token đã phát hành, nhưng việc login mới bằng SecretID đó sẽ thất bại.

Đây là cấu hình cho bài tập ngắn. Một service lâu dài cần cơ chế cấp SecretID mới khi token không thể gia hạn hoặc instance khởi động lại. Trong production nên xem xét CIDR ràng buộc role/token, token policy và mức TTL theo kiến trúc mạng thực tế.

### Bước 4. Lấy RoleID và sinh SecretID

Trong một terminal quản trị của lab:

~~~bash
# RoleID gắn với role "invoice-worker".
vault read -field=role_id auth/approle/role/invoice-worker/role-id

# Mỗi lần chạy lệnh này có thể phát một SecretID mới.
vault write -f auth/approle/role/invoice-worker/secret-id
~~~

Kết quả của lệnh thứ hai thường chứa `secret_id`, `secret_id_accessor`, `secret_id_ttl` và `secret_id_num_uses`. **SecretID accessor** dùng để tra cứu hoặc hủy credential qua endpoint quản trị, không thể dùng thay SecretID khi login.

RoleID thường ổn định, còn SecretID là credential cần bảo mật chặt chẽ và có thể phát riêng theo từng instance. Trong môi trường thật, hạn chế in SecretID ra terminal; provisioner nên nhận response qua API và chuyển trực tiếp bằng kênh bảo vệ. Token quản trị hoặc token có quyền tạo SecretID **không được đưa cho JVM** nếu workload chỉ sử dụng chế độ `provided`.

## 3. Cấp trực tiếp credential cho ứng dụng

### 3.1. Hình thức truyền giá trị

Ứng dụng chỉ cần nhận được hai chuỗi trước lúc khởi tạo `ClientAuthentication`. Có một số cơ chế thường gặp:

| Hình thức | Ưu điểm | Rủi ro / điều kiện vận hành |
| --- | --- | --- |
| **Biến môi trường** do orchestrator inject | Dễ tích hợp với `System.getenv(...)`, không cần SDK khác | Có thể lộ qua process inspection, diagnostic dump hoặc trang quản trị triển khai nếu phân quyền sai |
| **Secret file mount** với quyền đọc hạn chế | Không cần đưa credential vào command line, dễ thay file theo chính sách nền tảng | Phải quản lý owner, permission, đường dẫn mount và việc ứng dụng reload |
| **Broker/sidecar cung cấp khi startup** | Có thể cấp credential riêng cho từng replica và ghi nhận audit | Cần xử lý broker mất kết nối, TTL và cơ chế refresh |
| **Cấu hình ứng dụng tĩnh chứa giá trị thật** | Đơn giản khi thử tay | Không phù hợp production; dễ rò rỉ qua Git, image, backup hoặc artifact |

**Quan trọng:** “provided” mô tả cách **Spring Vault nhận giá trị**, không bắt buộc credential phải được hard-code. Với Java, tham số của `provided(String)` có thể được nạp từ biến môi trường, file mount hoặc một adapter tới secret broker.

Trong ví dụ dưới, môi trường chạy ứng dụng phải cấp hai biến **`VAULT_ROLE_ID`** và **`VAULT_SECRET_ID`** một cách an toàn. Không chép giá trị thực vào `application.yml`, `Dockerfile`, `pom.xml` hay mã test.

### 3.2. Thử đăng nhập bằng CLI trước khi chạy Java

Trong lab bảo mật, có thể dùng CLI để xác nhận cặp credential được cấp thuộc đúng role:

~~~bash
vault write auth/approle/login \
  role_id="<ROLE_ID_LAB>" \
  secret_id="<SECRET_ID_LAB>"
~~~

Kết quả thành công có token, TTL và policy. Lệnh trên minh họa payload, không nên dùng nguyên dạng có credential thật trên terminal dùng chung vì command line/history có thể bị quan sát. Nếu đã thử login bằng SecretID bị giới hạn lượt, mỗi lần thành công **tiêu thụ một lượt**; hãy phát SecretID mới cho lần chạy Java tiếp theo.

HTTP request tương đương:

~~~http
POST /v1/auth/approle/login HTTP/1.1
Content-Type: application/json

{
  "role_id": "<ROLE_ID_LAB>",
  "secret_id": "<SECRET_ID_LAB>"
}
~~~

Bước login không cần token quản trị trong header. Nếu role có ràng buộc CIDR, địa chỉ IP mà Vault nhìn thấy cũng phải hợp lệ.

## 4. Cấu hình Spring Vault với `RoleId.provided` và `SecretId.provided`

### 4.1. Cấu hình `ClientAuthentication` hoàn chỉnh

Với Spring Vault Core dùng Spring Context, `AbstractVaultConfiguration` cung cấp các bean nền tảng, trong đó có `VaultTemplate` và `SessionManager`. Ứng dụng hiện thực hai method `vaultEndpoint()` và `clientAuthentication()`:

~~~java
package example.vault;

import java.net.URI;

import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.AppRoleAuthentication;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.RoleId;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.SecretId;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.config.AbstractVaultConfiguration;

@Configuration
public class InvoiceVaultConfiguration extends AbstractVaultConfiguration {

    @Override
    public VaultEndpoint vaultEndpoint() {
        // Production: HTTPS và trust CA/TLS phù hợp với hệ thống Vault.
        URI uri = URI.create(requiredEnv("VAULT_ADDR"));
        return VaultEndpoint.from(uri);
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        String roleId = requiredEnv("VAULT_ROLE_ID");
        String secretId = requiredEnv("VAULT_SECRET_ID");

        AppRoleAuthenticationOptions options =
                AppRoleAuthenticationOptions.builder()
                        .path("approle")
                        .roleId(RoleId.provided(roleId))
                        .secretId(SecretId.provided(secretId))
                        .build();

        return new AppRoleAuthentication(options, vaultClient());
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Missing required environment variable: " + name);
        }
        return value;
    }
}
~~~

Các điểm mấu chốt:

1. `RoleId.provided(roleId)` chỉ đưa **giá trị RoleID** vào options; không gọi Vault endpoint `role-id`.
2. `SecretId.provided(secretId)` chỉ đưa **giá trị SecretID** vào options; không gọi Vault endpoint tạo `secret-id`.
3. `.path("approle")` chỉ rõ **mount path của auth method**. Nếu Vault mount ở `auth/team-approle/`, sử dụng `.path("team-approle")`. Không truyền `auth/approle` hoặc URL đầy đủ vào `path`.
4. Không cần `.appRole("invoice-worker")` cho trường hợp cả hai credential đều `provided`. Khi login, Vault dựa trên `role_id` để chọn role; tên `invoice-worker` chỉ cần cho các endpoint quản lý/cấp credential.
5. `AppRoleAuthentication` là `ClientAuthentication`; `vaultClient()` là API client được Spring Vault cung cấp trong phiên bản tham chiếu. Ở phiên bản Spring Vault cũ hơn, constructor có thể nhận `RestOperations`; hãy kiểm tra API của phiên bản dự án.

Đoạn code chỉ tạo object và cấu hình bean; thông thường **không cần tự gọi `clientAuthentication.login()`** trong `@PostConstruct` hay mỗi lần xử lý request. `SessionManager` sẽ lấy token khi cần và quản lý phiên theo loại token/trạng thái phù hợp.

### 4.2. Giải thích một request đăng nhập

Khi Spring Vault cần phiên, `AppRoleAuthentication` dùng hai chuỗi đã được cung cấp để gửi request tương đương:

~~~json
{
  "role_id": "gia-tri-RoleID-tu-runtime",
  "secret_id": "gia-tri-SecretID-tu-runtime"
}
~~~

Vault xác thực cặp credential và các ràng buộc trên role, sau đó trả về response có `auth.client_token` và thông tin như TTL, khả năng gia hạn, token policies. `SessionManager` nhận token để các request tiếp theo của `VaultTemplate` dùng token đó.

**Lưu ý:** Spring Vault lưu chuỗi credential đã nạp trong cấu hình `provided`; việc thay biến môi trường hay file mount sau khi object được tạo không tự làm bean đọc lại giá trị. Phải có cơ chế tái tạo/refresh cấu hình hoặc cấp credential từ nguồn thay đổi được nếu muốn rotation khi JVM vẫn chạy.

### 4.3. Đọc KV v2 bằng `VaultTemplate`

Ví dụ một service nhận `VaultTemplate` từ Spring và đọc secret giả đã ghi ở bước chuẩn bị:

~~~java
package example.vault;

import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

@Service
public class InvoiceGreetingService {

    private final VaultTemplate vaultTemplate;

    public InvoiceGreetingService(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public String greeting() {
        VaultResponse response = vaultTemplate
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("apps/invoice-worker");

        if (response == null) {
            throw new IllegalStateException("Vault secret not found");
        }

        Map<String, Object> data = response.getRequiredData();
        Object greeting = data.get("greeting");

        if (!(greeting instanceof String value)) {
            throw new IllegalStateException(
                    "Vault field 'greeting' is missing or invalid");
        }
        return value;
    }
}
~~~

Gọi `greeting()` trong môi trường lab sẽ trả chuỗi `vault-ready` nếu KV đã có dữ liệu và AppRole token mang đúng policy. Không log dữ liệu secret thật hoặc đưa nó ra HTTP response chỉ để chứng minh Vault hoạt động.

Ở góc nhìn authorization, `VaultTemplate` cần quyền `read` trên **`secret/data/apps/invoice-worker`**, dù Java sử dụng logical path `apps/invoice-worker` và mount `secret`. Đăng nhập thành công không cấp tự động quyền đọc mọi path.

### 4.4. Trường hợp dùng Spring Cloud Vault

Nếu dự án dùng **Spring Cloud Vault**, framework có cơ chế cấu hình `spring.cloud.vault.authentication=APPROLE` và các thuộc tính `spring.cloud.vault.app-role.role-id`, `spring.cloud.vault.app-role.secret-id`. Đây là lớp tích hợp khác với cấu hình `AbstractVaultConfiguration` đang minh họa. Chỉ dùng property phù hợp với dependency hiện có; `spring.cloud.vault.*` không tự có tác dụng nếu dự án chỉ cài `spring-vault-core`.

## 5. Mở rộng: truyền credential từ file được bảo vệ

Với môi trường inject credential vào file, một phương án vẫn dùng **`provided(String)`** là nạp giá trị file thay vì `System.getenv()`.

Ví dụ mã thay thế chỗ lấy `roleId` và `secretId`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

private static String readCredentialFile(Path path) {
    try {
        // Chỉ dùng nếu định dạng SecretID/RoleID của hệ thống không có
        // whitespace có ý nghĩa; strip() bỏ newline do secret mount thêm.
        String value = Files.readString(path, StandardCharsets.UTF_8).strip();
        if (value.isEmpty()) {
            throw new IllegalStateException(
                    "Credential file is empty: " + path);
        }
        return value;
    } catch (IOException ex) {
        throw new IllegalStateException(
                "Cannot read credential file: " + path, ex);
    }
}

// Trong clientAuthentication():
// String roleId = readCredentialFile(Path.of("/run/secrets/vault-role-id"));
// String secretId = readCredentialFile(Path.of("/run/secrets/vault-secret-id"));
// ... roleId(RoleId.provided(roleId)), secretId(SecretId.provided(secretId))
~~~

Dùng file mount cho ứng dụng chạy container đòi hỏi bảo vệ namespace, filesystem permissions, truy cập backup và logging. File chứa SecretID phải giới hạn chỉ cho process cần sử dụng; không để mọi container trong pod hoặc mọi người dùng trên host đều đọc được.

Ví dụ này chỉ đọc file **một lần khi khởi tạo bean**. Việc secret volume tự cập nhật không bảo đảm AppRoleAuthentication đang chạy có credential mới; quy trình rotation cần phối hợp reload/restart hoặc thiết kế lại cơ chế cấp phát.

## 6. Vòng đời SecretID khi dùng `provided`

Chế độ `provided` dễ hiểu nhưng giới hạn TTL/lượt dùng có tác động lớn đến khả năng khởi động lại.

~~~mermaid
flowchart TD
    A["Ứng dụng nhận RoleID + SecretID"] --> B["Spring Vault login"]
    B --> C{"Credential và ràng buộc hợp lệ?"}
    C -- Không --> D["Login thất bại; cấp lại credential"]
    C -- Có --> E["Vault cấp client token"]
    E --> F["VaultTemplate dùng token đọc secret"]
    F --> G{"Token còn hiệu lực?"}
    G -- Có --> F
    G -- Cần renew --> H{"Token renewable và còn giới hạn gia hạn?"}
    H -- Có --> I["SessionManager renew token"]
    I --> F
    H -- Không --> J["Cần AppRole login mới"]
    G -- Hết hạn / bị revoke --> J
    J --> B
~~~

Bảng minh họa với role `secret_id_ttl=20m` và `secret_id_num_uses=3`:

| Tình huống | Kết quả cần kỳ vọng |
| --- | --- |
| Login lần 1 bằng SecretID hợp lệ | Nhận client token; SecretID còn tối đa 2 lượt login và vẫn chịu TTL 20 phút |
| Đọc KV 10 lần bằng **cùng client token** | Không tiêu thụ 10 lượt SecretID; token phải còn hiệu lực, đủ policy |
| Token còn hạn và được renew | Có thể tiếp tục dùng token hiện tại mà không login lại; vẫn chịu chính sách và trần TTL |
| Login lần 4 bằng SecretID đã đủ 3 lượt | Vault từ chối, dù trước đó có token đang hoạt động |
| Login sau khi SecretID đã hết 20 phút | Vault từ chối, dù số lượt sử dụng chưa hết |
| Ứng dụng restart và dùng lại SecretID cũ | Có thể thành công hoặc thất bại tùy TTL, số lượt còn lại, CIDR và tình trạng role |
| Xóa SecretID qua accessor | Chặn các login mới với SecretID đó; token đã cấp phải đánh giá/thu hồi riêng nếu cần |

**Sai lầm phổ biến:** đặt `secret_id_num_uses=1`, dùng cùng SecretID được cung cấp trực tiếp cho nhiều replica, rồi kỳ vọng mọi replica đều đăng nhập thành công. Replica đầu tiên có thể dùng hết lượt. Khi scaling, cấp **SecretID riêng theo instance/job** hoặc chọn thiết kế cấp phát phù hợp.

Spring Vault `LifecycleAwareSessionManager` có thể lên lịch gia hạn client token khi token cho phép. Nó không thay đổi TTL/lượt dùng của SecretID đã cung cấp, và cũng không làm mới chuỗi `SecretId.provided(...)`. Khi token hết hạn hoặc không thể renew, lần login mới sẽ cần **credential còn hợp lệ**; thiết kế production phải có cơ chế đáp ứng việc này.

## 7. Bảo mật khi cung cấp credential trực tiếp

### 7.1. Phân tách quyền provisioner và workload

Có ba danh tính/đường quyền độc lập:

1. **Vault administrator/IaC:** tạo role, mount, policy, cấu hình TTL/CIDR.
2. **Provisioner:** có quyền đọc `auth/approle/role/invoice-worker/role-id` và tạo SecretID tại `auth/approle/role/invoice-worker/secret-id` cho đúng role; không mặc nhiên cần đọc secret nghiệp vụ.
3. **Workload Java:** chỉ nhận RoleID/SecretID và token có policy `invoice-worker-read`; không cần quyền tạo SecretID hay quản lý role.

Chỉ nên cấp token quản trị trong môi trường của provisioner. Khi ứng dụng chạy, nó dùng `provided` để login; không gắn root token hoặc provisioner token vào `VaultTemplate`.

### 7.2. Các điểm có thể làm lộ credential

| Nguồn rủi ro | Cách giảm rủi ro |
| --- | --- |
| Hard-code `VAULT_SECRET_ID` vào Java, YAML, Docker image hoặc repository | Inject qua runtime bằng cơ chế quản lý bí mật; kiểm tra secret scanning và quyền truy cập artifact |
| In giá trị credential trong log, exception, trace hoặc health endpoint | Chỉ log trạng thái, loại lỗi, tên biến thiếu; tuyệt đối không log giá trị |
| Truyền SecretID trực tiếp trên command line hoặc CI output | Dùng broker/API và kênh phân phối được bảo vệ; hạn chế hiển thị lệnh có secret |
| Dùng chung SecretID trên nhiều replica | Phát theo instance, giới hạn TTL/lượt dùng, thu hồi riêng theo accessor |
| SecretID có thời hạn vô hạn, không có rotation | Xác định TTL, số lượt và quy trình cấp mới trước khi triển khai |
| Token có policy quá rộng | Chỉ cấp capability/path thật sự cần; test yêu cầu ngoài quyền |
| Đường truyền HTTP hoặc TLS không được xác minh trong production | Dùng HTTPS, CA trust đúng, kiểm tra proxy và đường mạng |
| Tin rằng đổi SecretID sẽ tự thu hồi token cũ | Thu hồi token/session liên quan khi cần; rà soát audit log và ACL |

**RoleID cũng nên được bảo vệ**, dù SecretID mới là credential bí mật được yêu cầu mặc định. Sự kết hợp của hai giá trị có thể tạo ra token cho workload. Token trả về từ login cũng phải được bảo vệ tương đương token truy cập dịch vụ.

### 7.3. Có nên dùng response wrapping thay `provided`?

Với pipeline hoặc broker phân phối credential, response wrapping giúp chuyển **wrapping token dùng một lần** đến bên nhận thay vì chuyển SecretID thuần. Spring Vault hỗ trợ `SecretId.wrapped(VaultToken.of(wrappingToken))` cho tình huống đó.

Tuy nhiên, bài này cố ý chọn **cấp trực tiếp SecretID** để minh họa đường xác thực đơn giản nhất. Không thể lấy wrapping token rồi truyền thẳng vào `SecretId.provided(...)`: Vault sẽ coi đó là SecretID sai. Nếu cần wrapping, phải đổi cấu hình và xây dựng quy trình cấp token bọc mới khi restart hoặc cần re-authentication.

## 8. Xác minh từng bước và xử lý lỗi

### 8.1. Kịch bản kiểm chứng tối thiểu

Thử trên Vault lab riêng với dữ liệu giả:

1. Kiểm tra policy `invoice-worker-read` chỉ có quyền đọc `secret/data/apps/invoice-worker`.
2. Cấp **SecretID mới** cho lần chạy Java, inject `VAULT_ADDR`, `VAULT_ROLE_ID` và `VAULT_SECRET_ID` vào môi trường ứng dụng.
3. Khởi động Spring Context với `InvoiceVaultConfiguration`; gọi `InvoiceGreetingService.greeting()` và xác nhận nhận được `vault-ready`.
4. Thử một thao tác `update` vào cùng KV path bằng token ứng dụng. Mong đợi **403** vì policy chỉ có `read`.
5. Đổi một ký tự trong SecretID và khởi động ứng dụng lại. Mong đợi lỗi **đăng nhập** trước khi đọc KV.
6. Thử giới hạn số lần: sử dụng cùng SecretID để login độc lập đến hết `secret_id_num_uses`, quan sát lỗi lần tiếp theo.
7. Sau khi token được cấp, kiểm chứng nhiều thao tác đọc KV vẫn chạy với cùng session và **không** trừ thêm lượt SecretID.

Đối với môi trường CI, có thể dùng Vault dev/test chạy độc lập để xác minh những hành vi này thay vì kiểm tra mỗi việc tạo builder. Không dùng credential và KV data của môi trường sản xuất cho kiểm thử.

### 8.2. Bảng xử lý lỗi

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra an toàn |
| --- | --- | --- |
| Lỗi `Missing required environment variable` khi tạo bean | Runtime chưa inject một trong ba biến | Kiểm tra tên biến và chính sách injection; không in nội dung của biến |
| `400` hoặc `403` khi AppRole login | RoleID/SecretID sai, SecretID hết hạn/hết lượt, role bị đổi, CIDR bị chặn | Kiểm tra role, ràng buộc, SecretID accessor theo quyền provisioner |
| `404` tại `auth/approle/login` | Vault không mount AppRole ở đường dẫn đã cấu hình | Kiểm tra `path("approle")` và mount auth thực tế |
| Login được nhưng KV trả `403` | Token thiếu policy `read`, token bị revoke hoặc token-bound CIDR không phù hợp | Xem token policies/path và IP source; phân biệt auth với authorization |
| KV trả `404` hoặc `null` | Sai logical path, sai mount/phiên bản KV, secret không tồn tại | So sánh `secret/`, `apps/invoice-worker` và KV v2 API path |
| Chạy ổn lúc đầu, restart thất bại | SecretID đã hết TTL hoặc bị sử dụng hết lượt | Cấp SecretID mới theo quy trình, tránh dùng lại giá trị quá hạn |
| Chạy một thời gian rồi lỗi đọc secret | Token hết TTL, không renew được hoặc mất kết nối Vault | Kiểm tra session events, Vault audit và TTL/renewal; chuẩn bị đường re-login |
| Một replica chạy, replica khác login thất bại | Dùng chung SecretID ít lượt hoặc CIDR khác | Cấp riêng credential cho replica và đánh giá egress IP |
| `VaultTemplate` bị lỗi TLS/SSL | CA chưa được tin cậy hoặc Vault endpoint sai | Cấu hình truststore/CA đúng; không tắt xác minh TLS |

Việc `AppRoleAuthentication` có credential hợp lệ **không bảo đảm** thao tác đọc KV được cấp quyền. Hãy phân biệt:

~~~text
Chưa có token:
    AppRole login -> 400/403 => sai credential/ràng buộc hoặc không thể login

Đã có token:
    KV GET -> 403 => token policy, bound CIDR, token validity hoặc request path
    KV GET -> 404 => có thể path hoặc secret không tồn tại
~~~

Cách quan sát an toàn là dùng metric cho số lần login/renew thất bại, thông báo lỗi được làm sạch thông tin nhạy cảm và Vault audit log giới hạn quyền truy cập. Không ghi RoleID, SecretID, client token hay giá trị secret vào log/metric labels.

## 9. Câu hỏi thực hành và mở rộng

**Bài tập 1 — cấu hình trực tiếp.** Tạo AppRole `invoice-worker` và policy chỉ đọc KV v2. Trình bày đúng luồng: provisioner phát credential → runtime inject → `RoleId.provided`/`SecretId.provided` → AppRole login → `VaultTemplate` đọc dữ liệu.

**Bài tập 2 — kiểm chứng phân quyền.** Giữ nguyên RoleID/SecretID, thay token policy chỉ đọc một path khác và quan sát lỗi 403 tại KV. Vì sao thay credential không giải quyết quyền truy cập?

**Bài tập 3 — số lần dùng.** Thiết lập `secret_id_num_uses=1` và chạy hai lần login độc lập. Sau lần login đầu thành công, hãy dùng lại token đầu tiên đọc KV nhiều lần. Giải thích vì sao các request đọc đó không phải lần login mới.

**Bài tập 4 — rotation.** Thiết kế quy trình cấp SecretID mới khi triển khai một replica mới và khi instance hiện tại restart. Cần làm gì nếu SecretID cũ bị lộ nhưng đã tạo ra client token hợp lệ?

**Bài tập 5 — phương thức phân phối.** So sánh biến môi trường với file mount có quyền đọc hạn chế cho cùng cách dùng `SecretId.provided(...)`. Trình bày cách tránh lộ trong CI logs, Docker image và diagnostic dump.

**Tiêu chí hoàn thành:** cấu hình Java đăng nhập thành công bằng RoleID/SecretID được cung cấp trực tiếp, sử dụng `VaultTemplate` đọc đúng KV v2 path với policy tối thiểu, xác minh được lỗi do SecretID và lỗi do token policy, đồng thời giải thích được yêu cầu cấp phát lại credential theo TTL và số lượt.

## Tài liệu tham khảo

- [Spring Vault — Authentication Methods / AppRole](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault — VaultTemplate và quản lý phiên](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
- [Spring Vault API — AppRoleAuthenticationOptions.RoleId](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthenticationOptions.RoleId.html)
- [Spring Vault API — AppRoleAuthenticationOptions.SecretId](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthenticationOptions.SecretId.html)
- [Spring Vault API — AppRoleAuthentication](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthentication.html)
- [HashiCorp Vault — AppRole authentication](https://developer.hashicorp.com/vault/docs/auth/approle)
- [HashiCorp Vault — AppRole HTTP API](https://developer.hashicorp.com/vault/api-docs/auth/approle)
- [HashiCorp Vault — Token concepts](https://developer.hashicorp.com/vault/docs/concepts/tokens)
