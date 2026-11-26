# Phân biệt client gọi trực tiếp với đọc dữ liệu Agent đã ghi ra

Trong chương **Tích hợp ứng dụng**, một quyết định kiến trúc quan trọng là **ứng dụng Java trực tiếp gọi HashiCorp Vault** hay **ứng dụng chỉ đọc file secret do Vault Agent chuẩn bị**. Hai cách đều có thể nhận cùng dữ liệu từ KV, Database hoặc PKI, nhưng khác nhau ở nơi xác thực, thời điểm đọc, vòng đời token/lease, độ mới của dữ liệu và cách ứng dụng xử lý lỗi.

Trong module **SPRING_VAULT**, chúng ta sử dụng Spring Vault với `VaultTemplate`/`VaultOperations`, xác thực theo workload, policy tối thiểu, KV secrets, Transit encryption, PKI, token/lease và kiểm thử tích hợp. Không phải dịch vụ nào cũng cần biết API Vault: một dịch vụ cũ, một chương trình bên thứ ba hoặc ứng dụng chỉ đọc cấu hình khi khởi động có thể dùng file do Agent render. Ngược lại, ứng dụng muốn chủ động đọc secret, gọi Transit, yêu cầu chứng thư hoặc kiểm soát lỗi API theo từng thao tác thường cần client trực tiếp.

Xuyên suốt bài này, giả sử KV v2 được mount ở `secret/`, và một bản ghi chứa `apiKey` của dịch vụ `orders` nằm tại đường dẫn logic `orders/config`. Cùng một khóa có thể được lấy bằng:

- **Client trực tiếp**: `VaultOperations.opsForKeyValue("secret", KV_2).get("orders/config")`.
- **Vault Agent template**: Agent đọc `secret/data/orders/config` rồi ghi giá trị `apiKey` ra file `/vault/secrets/orders-api-key`; Java đọc file đó.

Ví dụ sử dụng chuỗi khóa giả trong môi trường thử nghiệm. Không đưa API key, token Vault hoặc private key thật vào mã nguồn, log hay kho Git.

## 1. Hai luồng dữ liệu khác nhau

### Mô hình A — Ứng dụng Java gọi Vault trực tiếp

~~~mermaid
sequenceDiagram
    participant App as Spring Boot + Spring Vault
    participant Auth as Vault Auth
    participant KV as Vault KV v2
    App->>Auth: Đăng nhập bằng workload identity
    Auth-->>App: Vault token + policies + TTL
    App->>KV: GET secret/data/orders/config
    KV-->>App: data.data.apiKey
    App->>App: Kiểm tra và sử dụng apiKey
    Note over App,Auth: Spring Vault quản lý session/token theo cấu hình
~~~

Ứng dụng biết Vault ở đâu, dùng phương thức xác thực nào và cần gọi engine gì. Spring Vault giúp xây client HTTP, gửi token và diễn giải response. Với KV v2, API mức cao xử lý khác biệt đường dẫn `data/` và cấu trúc JSON; code không cần ghép mọi endpoint thủ công.

Khi business code chủ động gọi `get(...)`, đó là **một lần truy vấn Vault tại thời điểm được gọi**. Nếu ứng dụng tự cache kết quả, hoặc dùng một lớp cấu hình nạp lúc khởi động, các lần sử dụng tiếp theo có thể vẫn dùng dữ liệu cũ. Vì vậy “gọi trực tiếp” **không mặc định** đồng nghĩa mọi request đều truy vấn giá trị mới nhất.

### Mô hình B — Vault Agent đọc và ghi file trước cho ứng dụng

~~~mermaid
sequenceDiagram
    participant Agent as Vault Agent
    participant Auth as Vault Auth
    participant KV as Vault KV v2
    participant File as Shared secret volume
    participant App as Spring Boot
    Agent->>Auth: Auto-auth bằng workload identity
    Auth-->>Agent: Vault token + TTL
    Agent->>KV: GET secret/data/orders/config
    KV-->>Agent: data.data.apiKey
    Agent->>File: Render /vault/secrets/orders-api-key
    App->>File: Đọc chuỗi từ file
    File-->>App: apiKey
    Note over Agent,File: Agent theo dõi việc cập nhật/renew theo loại secret
    Note over File,App: Java phải có cách sử dụng dữ liệu mới
~~~

Vault Agent là thành phần chạy cạnh ứng dụng, thường dưới dạng process riêng hoặc **sidecar** ở Kubernetes. Agent có thể auto-auth, lấy secret, duy trì token/lease theo loại secret và render dữ liệu ra file bằng Consul Template. Java chỉ cần đọc file, có thể không cần dependency Spring Vault trong đường đi nhận secret này.

Trong Kubernetes Vault Agent Injector, một **init container** thường chuẩn bị secret trước khi container ứng dụng chạy, còn **sidecar** tiếp tục render khi ứng dụng đang chạy; cách triển khai phụ thuộc annotation/cấu hình thực tế. Dữ liệu thường được chia sẻ dưới `/vault/secrets`. Agent chỉ có thể phục vụ các secret mà **policy của danh tính Agent** cho phép đọc. App không cần nhận token Vault nếu chỉ dùng file đã render.

**Điểm quyết định:** Agent ghi file mới không đồng nghĩa mọi bean, connection pool hoặc HTTP client của Spring Boot tự đọc lại file. Việc cập nhật state trong bộ nhớ hay tạo kết nối mới thuộc trách nhiệm của ứng dụng/nền tảng.

## 2. Bảng so sánh để lựa chọn

| Tiêu chí | Spring Vault gọi trực tiếp | Đọc file do Vault Agent render |
| --- | --- | --- |
| Ai xác thực với Vault? | Process ứng dụng / Spring Vault client | Vault Agent auto-auth |
| Ai giữ Vault token? | Session/token manager của client ứng dụng | Agent; ứng dụng đọc file không cần token |
| Ai gọi API secret engine? | Code Spring Vault (`VaultOperations`, `VaultTemplate`) | Agent Template gọi `secret`/`pkiCert` |
| Dữ liệu ứng dụng đọc | Response từ Vault tại lúc gọi, trừ cache | Snapshot nội dung file tại lúc đọc |
| Khi Vault tạm ngừng | Lượt gọi mới có thể lỗi ngay | File đã render có thể còn đọc được, nhưng độ mới/TTL có thể không còn đạt yêu cầu |
| Khi secret đổi | App cần gọi lại hoặc được refresh theo thiết kế | Agent có thể render lại; app vẫn phải reload/re-read |
| Khi token hết hạn | Client/session manager xử lý renew/login theo cấu hình | Agent auto-auth/renew theo cấu hình |
| Khi dynamic lease hết hạn | App/secret-lease component phải renew hoặc lấy credential mới | Agent xử lý lease của secret trong template, app phải dùng dữ liệu mới |
| Thao tác động như Transit sign/encrypt | Phù hợp vì cần request/response theo từng lần | Template file không thay thế lời gọi mật mã nghiệp vụ theo request |
| Bề mặt bí mật trong filesystem | Có thể tránh tạo file secret, trừ khi app tự ghi | Có bản secret ở file/volume: phải kiểm soát UID/GID, permissions, backup |
| Quan sát lỗi | Lỗi Vault xuất hiện trong code/metrics Java | Cần giám sát cả Agent, việc render, file và runtime Java |
| Tái sử dụng với ứng dụng không biết Vault | Cần tích hợp API/SDK | Dễ hơn: app chỉ đọc file thông thường |

**Không có lựa chọn tối ưu tuyệt đối.** Nếu yêu cầu nghiệp vụ là mỗi giao dịch gọi Transit để mã hóa một payload, client trực tiếp thường rõ ràng hơn. Nếu ứng dụng chỉ cần đọc cấu hình từ file hoặc phần mềm bên thứ ba không có SDK Vault, Agent template thường giảm công tích hợp. Nhiều hệ thống dùng kết hợp: Agent cung cấp một số file còn Java gọi Vault trực tiếp cho các thao tác có tham số ở runtime.

## 3. Chuẩn bị cùng một secret và quyền đọc

Giả sử đã có KV **version 2** tại mount `secret/`, với khóa logic `orders/config`. Ví dụ dữ liệu dùng cho lab:

~~~json
{
  "apiKey": "DEMO_ONLY_NOT_A_REAL_SECRET"
}
~~~

Trong Vault CLI, người vận hành có thể tạo bản ghi thử:

~~~bash
# Chỉ dùng giá trị giả trong lab; không truyền secret thật trên CLI công khai.
vault kv put -mount=secret orders/config \
  apiKey="DEMO_ONLY_NOT_A_REAL_SECRET"

vault kv get -mount=secret orders/config
~~~

API KV v2 thực sự đọc qua đường dẫn HTTP `GET /v1/secret/data/orders/config`. Quyền Vault ACL liên quan:

~~~hcl
# Policy tối thiểu cho role/workload cần đọc dữ liệu.
path "secret/data/orders/config" {
  capabilities = ["read"]
}
~~~

Trong cách **trực tiếp**, policy này phải gắn với token mà Spring Vault nhận qua phương thức xác thực ứng dụng. Trong cách **Agent**, policy này gắn với Vault role của Agent, ví dụ role Kubernetes dùng service account của Pod. Policy giống nhau ở đường dữ liệu nhưng danh tính sở hữu token và cách quan sát token khác nhau.

Để phân biệt đường dẫn:

| Ngữ cảnh | Đường dẫn |
| --- | --- |
| KV logic path, dùng với `VaultKeyValueOperations` | `orders/config` |
| KV mount, dùng trong `opsForKeyValue` | `secret` |
| HTTP API KV v2 | `secret/data/orders/config` |
| Vault Agent template `secret` function | `secret/data/orders/config` |
| File local sau render | `/vault/secrets/orders-api-key` |

Nếu dùng KV v1, cấu trúc endpoint và map response **khác KV v2**. Không dùng `.Data.data` một cách máy móc cho mọi engine, cũng không thêm `data/` vào tham số `get(...)` khi đã chọn API `KV_2` của Spring Vault.

## 4. Cách A: Đọc trực tiếp bằng `VaultOperations`

Ứng dụng Spring Boot đã cấu hình Vault endpoint, CA trust, workload authentication và bean `VaultOperations` có thể lấy dữ liệu như sau:

~~~java
import java.util.Map;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;

// Giao diện chung cho hai cách lấy secret trong bài.
interface OrdersApiKeySource {
    String currentApiKey();
}

@Service
@Profile("vault-direct")
public class DirectVaultApiKeySource implements OrdersApiKeySource {

    private final VaultKeyValueOperations kv;

    public DirectVaultApiKeySource(VaultOperations vault) {
        this.kv = vault.opsForKeyValue("secret", KeyValueBackend.KV_2);
    }

    @Override
    public String currentApiKey() {
        VaultResponse response = kv.get("orders/config");
        if (response == null) {
            throw new IllegalStateException(
                    "Không tìm thấy KV secret orders/config");
        }

        Map<String, Object> data = response.getRequiredData();
        Object value = data.get("apiKey");
        if (!(value instanceof String key) || key.isEmpty()) {
            throw new IllegalStateException("KV secret thiếu apiKey");
        }

        return key;
    }
}
~~~

Ví dụ sử dụng Java 17+ vì cú pháp `instanceof String key`. `@Profile("vault-direct")` chỉ dùng để minh họa lựa chọn triển khai; phải kích hoạt profile tương ứng và cấu hình `VaultOperations` trong ứng dụng thật.

Lợi ích của API `opsForKeyValue("secret", KV_2)`:

- Tách đường dẫn logic khỏi đường dẫn HTTP KV v2; giảm lỗi nhầm `/data/`.
- Có response đối tượng Java thay vì tự parse JSON thô.
- Dùng Vault session manager/HTTP transport được cấu hình, không cần tự ghép `X-Vault-Token` ở từng business method.
- Có thể bổ sung metadata/version-aware KV API khi cần quản lý phiên bản hoặc điều kiện CAS.

Tuy nhiên, ứng dụng phải quyết định khi nào `currentApiKey()` được gọi. Nếu gọi mỗi lần gửi request thì mỗi lần có thể tốn thêm round trip đến Vault. Nếu chỉ gọi lúc startup và giữ chuỗi trong field, **secret không tự cập nhật** khi KV được sửa. Có thể bổ sung cache có TTL, cơ chế refresh có kiểm soát hoặc đọc theo sự kiện, nhưng phải cân bằng độ mới và khả năng Vault chịu tải.

### Vòng đời token và lỗi ở client trực tiếp

Spring Vault hỗ trợ session management; khi sử dụng cơ chế xác thực/renew phù hợp, client có thể quản lý token theo chính sách đã cấu hình. Không nên mặc định mọi loại token đều renew được: batch token, periodic token, token có giới hạn `max_ttl` và AppRole/Kubernetes auth có đặc điểm riêng.

Cần phân loại ít nhất:

| Tình huống | Hành vi ứng dụng |
| --- | --- |
| Đăng nhập workload thất bại | Không có token hợp lệ, báo lỗi rõ ràng; kiểm tra auth mount/role và policy |
| `403 permission denied` khi đọc KV | Đối chiếu policy `secret/data/orders/config`; không trả chuỗi rỗng như secret hợp lệ |
| `404` / không có bản ghi | Fail theo hợp đồng secret bắt buộc, không suy diễn secret mặc định |
| Timeout / 429 / 5xx | Retry hữu hạn có backoff/jitter khi phù hợp, giữ circuit breaker và giới hạn tải |
| Secret đã thay trong KV | Đọc lại hoặc refresh cache, tránh giữ mã cũ vô hạn |
| Dynamic credential đã hết lease | Đổi connection/credential; không nghĩ renew token đồng nghĩa renew lease của secret |

Đối với Transit/PKI, API cần request động (plaintext cần mã hóa, CSR, TTL, principal...) nên đường đọc KV bên trên **không thay thế** các operation riêng `opsForTransit()` hoặc `opsForPki()`.

## 5. Cách B: Vault Agent tự render ra file

Vault Agent có thể thực hiện **auto-auth** rồi dùng Consul Template đọc secret và ghi file. Ví dụ HCL dưới đây áp dụng cho Agent chạy trong Pod có Kubernetes service-account token và đã được cấu hình Vault Kubernetes auth; người vận hành điều chỉnh đường dẫn Vault, CA và quyền filesystem cho môi trường thực tế.

~~~hcl
vault {
  address = "https://vault.example.internal:8200"
  ca_cert = "/etc/vault/tls/ca.pem"
}

auto_auth {
  method "kubernetes" {
    mount_path = "auth/kubernetes"
    config = {
      role       = "orders-file"
      token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    }
  }
}

template_config {
  static_secret_render_interval = "1m"
  exit_on_retry_failure = true
}

template {
  # KV v2: giá trị nằm trong .Data.data.
  contents = "{{ with secret \"secret/data/orders/config\" }}{{ .Data.data.apiKey }}{{ end }}"
  destination = "/vault/secrets/orders-api-key"
  perms = "0440"
  backup = false
  error_on_missing_key = true
}
~~~

Các điểm cần hiểu:

1. `auto_auth.method "kubernetes"` dùng danh tính service account của Pod để nhận Vault token; **role `orders-file`** phải được bind đúng Kubernetes service account/namespace và gắn policy đọc KV.
2. `secret "secret/data/orders/config"` truy cập endpoint **KV v2**. Cú pháp `.Data.data.apiKey` phản ánh cấu trúc response của engine; nó không phải thuộc tính Java.
3. `destination` là **file cục bộ**, không phải path Vault hay URL ứng dụng.
4. `perms="0440"` giúp tránh mặc định file quá rộng quyền; phải bảo đảm UID/GID của Agent và ứng dụng có thể đọc theo thiết kế. Nếu khác user, cần group/volume phù hợp.
5. `backup=false` tránh lưu lại một bản file bí mật trước đó do tính năng backup template; chính sách backup chung của hệ thống vẫn cần được kiểm tra.
6. `error_on_missing_key=true` ngăn việc một trường không có giá trị âm thầm biến thành text `<no value>`. `exit_on_retry_failure` ảnh hưởng hành vi lỗi khi Agent retry; không thể thay thế kiểm tra file ở phía Java.
7. `static_secret_render_interval="1m"` đặt chu kỳ kiểm tra/render cho các secret không leased như KV v2; **không phải cơ chế push tức thì** khi Vault thay đổi.

Ví dụ này **không có `sink` token** vì chỉ cần render secret: ứng dụng không cần đọc Vault token. Nếu Agent còn được dùng để proxy cho client Vault, hoặc hệ thống dùng token sink, cần xét quyền đọc token và luồng xác thực như một thiết kế riêng.

### Nếu dùng Vault Agent Injector trên Kubernetes

Khi Vault Agent Injector đã được cài và cấu hình, Pod có thể dùng annotation tương đương để yêu cầu render:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: orders-demo
  annotations:
    vault.hashicorp.com/agent-inject: "true"
    vault.hashicorp.com/role: "orders-file"
    vault.hashicorp.com/agent-inject-secret-orders-api-key: "secret/data/orders/config"
    vault.hashicorp.com/agent-inject-template-orders-api-key: |
      {{- with secret "secret/data/orders/config" -}}
      {{ .Data.data.apiKey }}
      {{- end -}}
    vault.hashicorp.com/agent-inject-perms-orders-api-key: "0440"
spec:
  serviceAccountName: orders-app
  containers:
    - name: orders
      image: example.invalid/orders-demo:1.0
      # App phải đọc /vault/secrets/orders-api-key sau khi file có sẵn.
~~~

Đây là đoạn minh họa annotation, không phải manifest triển khai production hoàn chỉnh. Image là tên giả. Injector thường dùng init container để chuẩn bị dữ liệu rồi sidecar tiếp tục render; kiểm tra các annotation bật/tắt init/sidecar và phiên bản injector thực tế. **Chỉ init container** có nghĩa dữ liệu có thể được render một lần rồi không được cập nhật trong suốt vòng đời Pod.

Nếu muốn đọc file có tên khác, cần cấu hình tên `destination` hoặc annotation tương ứng và cập nhật đường dẫn Java. Đường dẫn mặc định `/vault/secrets/orders-api-key` chỉ có ý nghĩa trong Pod/volume được mount. Không suy đoán Agent đang viết file vào container host hoặc vào máy của Spring Boot khác.

## 6. Java đọc file Agent đã ghi

Nếu cùng interface `OrdersApiKeySource` ở mục 4, bản file-based chỉ cần Java NIO:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;

@Service
@Profile("vault-file")
public class AgentFileApiKeySource implements OrdersApiKeySource {

    private static final Path SECRET_FILE =
            Path.of("/vault/secrets/orders-api-key");

    @Override
    public String currentApiKey() {
        try {
            // Đọc khi cần dùng để nhận nội dung hiện có trên file.
            String key = Files.readString(SECRET_FILE, StandardCharsets.UTF_8);
            if (key.isEmpty() || key.isBlank()) {
                throw new IllegalStateException(
                        "Agent secret file rỗng hoặc chỉ có khoảng trắng");
            }
            // Không tự trim/strip secret: có thể làm thay đổi giá trị thật.
            return key;
        } catch (IOException e) {
            throw new UncheckedIOException(
                    "Không đọc được file Agent đã render", e);
        }
    }
}
~~~

Trong cùng một lần triển khai, chỉ kích hoạt một profile `vault-direct` hoặc `vault-file` để Spring tạo đúng bean `OrdersApiKeySource`. Với cách file, ứng dụng **không phải giữ Vault token**, cũng không cần biết mount `secret/`. Tuy nhiên runtime phải có quyền đọc file, đường dẫn chính xác, nội dung đúng định dạng và cơ chế xử lý khi file chưa xuất hiện hoặc bị lỗi.

Ví dụ dùng giá trị mới khi gửi yêu cầu:

~~~java
import org.springframework.http.HttpHeaders;

HttpHeaders headers = new HttpHeaders();
headers.set("X-API-Key", apiKeySource.currentApiKey());
// Dùng headers trong HTTP request đã được bảo vệ bởi TLS.
~~~

Nếu mã nguồn đọc secret **một lần tại startup** rồi gắn vào một HTTP client singleton, việc Agent render bản mới **không thay đổi** header đã bị giữ trong client đó. Đọc lại mỗi lần cần dùng như ví dụ là cách minh họa đơn giản; ở hệ thống tải cao có thể dùng cache/refresh có kiểm soát, với quy tắc cập nhật đồng bộ và giới hạn thời gian dữ liệu cũ.

### Nạp file vào Spring Boot config khác với đọc lại ở runtime

Với file dạng `.properties` do Agent render, ứng dụng cũng có thể cấu hình:

~~~yaml
spring:
  config:
    import: "file:/vault/secrets/orders.properties"
~~~

Spring Boot sẽ nhập file cấu hình **trong quá trình dựng Environment khi khởi động**. Lần Agent thay đổi file sau đó **không tự động cập nhật** mọi `@Value`, `@ConfigurationProperties` bean hoặc connection pool đã tạo. Nếu file là bắt buộc, dùng đường dẫn không có tiền tố `optional:` để fail fast khi thiếu.

Với Agent template tạo `.properties`, phải bảo đảm các ký tự đặc biệt của secret được escape đúng chuẩn Java Properties; nếu không có quy tắc encode an toàn, dùng format JSON/keystore hoặc file một giá trị theo hợp đồng rõ ràng. Tránh ghi nhiều trường mật trong các file riêng khi cần đồng bộ phiên bản: ứng dụng có thể đọc xen kẽ hai lần render khác nhau.

## 7. Tính “mới” của secret: vấn đề dễ bị nhầm nhất

Giả sử thời điểm `t0` Agent render API key `K1`. Đến `t1` người quản trị đổi KV v2 thành `K2`. Đến `t2` Agent tới kỳ đọc lại và render file. Đến `t3` Java đọc file lần tiếp theo.

| Thời điểm | Vault | File Agent | Java đọc được |
| --- | --- | --- | --- |
| `t0` | `K1` | `K1` | `K1` |
| `t1` (KV đổi) | `K2` | `K1` | `K1` nếu vẫn đọc file |
| `t2` (Agent render) | `K2` | `K2` | `K2` nếu đọc lại |
| `t3` (app re-read) | `K2` | `K2` | `K2` |

*Bảng trên là kịch bản minh họa khi mọi bước thành công, không phải cam kết thời gian cập nhật.*

Với direct client, một lần gọi KV **sau `t1`** thường thấy phiên bản mới ở Vault nếu không có cache/phân vùng đặc biệt và request thành công. Với Agent file, còn độ trễ tới khi Agent kiểm tra/render, sau đó tới khi app đọc lại hoặc reload. Đây là cơ chế **eventual refresh** chứ không phải dữ liệu thay đổi đồng bộ tại cùng một thời điểm.

Với KV v2, Agent template thường coi secret là **non-leased static secret** và kiểm tra lại theo `static_secret_render_interval` (mặc định thường là 5 phút; ví dụ đặt 1 phút). Vì thế, chỉ kiểm tra token của Agent còn hiệu lực **không chứng minh** file chứa giá trị mới nhất.

### Lease của secret động khác với refresh KV

- Với **KV v2**, dữ liệu tĩnh thường không có lease thuê credential; vòng cập nhật chủ yếu dựa trên lần Agent refetch và app reload.
- Với **Database dynamic credentials**, response có `lease_id`, `lease_duration` và cờ `renewable`. Agent template có thể renew hoặc lấy credential mới theo loại lease. Ứng dụng đọc file vẫn phải cập nhật connection pool/connection đang dùng khi username/password đổi, tránh dùng credential đã bị thu hồi hoặc hết hạn.
- Với **PKI certificates**, Agent có `pkiCert` dành cho chứng thư để kiểm soát việc cấp lại; kể cả file certificate/key đã thay, TLS runtime vẫn phải reload SSL context hoặc rolling restart và xác minh handshake.
- Với **Transit encrypt/sign**, thông điệp đưa vào API thay đổi theo mỗi thao tác; một file được Agent render sẵn **không** là cơ chế thay thế phù hợp cho response mật mã động.

Một lỗi điển hình là cho rằng “Vault Agent tự renew lease” đồng nghĩa “Spring Boot đã thay JDBC credentials”. Agent chỉ bảo đảm phần việc **của Agent** theo cấu hình; phần cập nhật HikariCP hoặc những connection đã thiết lập phải được kiểm thử riêng.

## 8. Bảo mật: bí mật ở đâu và ai có quyền?

### 8.1. Khi client gọi trực tiếp

Process Java có Vault token hoặc quyền sử dụng token thông qua client/session manager; mạng từ process phải đến được Vault. Phải bảo vệ cấu hình workload authentication, token, TLS trust và secret trong bộ nhớ ứng dụng. Đừng gửi Vault token hoặc giá trị secret vào HTTP response, tracing baggage, exception message hoặc log.

Policy ứng dụng nên hạn chế đúng các endpoint sử dụng, ví dụ chỉ `read` với `secret/data/orders/config`. Không cấp `sys/mounts`, `sys/auth`, quyền tạo Transit key hay quyền quản trị PKI chỉ để đọc một API key.

### 8.2. Khi dùng Agent template

Vault token nằm ở Agent, nhưng **secret rõ** nằm trong file chia sẻ. Do đó:

- Phải thiết lập quyền owner/group và permission cho file. Mặc định template có thể tạo file với quyền rộng (ví dụ `0644` nếu chưa tồn tại); cần đặt `perms` cụ thể phù hợp container.
- Kiểm soát filesystem/volume. Tránh dùng volume ghi bền vững ngoài nhu cầu, backup không mã hóa, log file contents, chụp heap/core dump chứa secret hoặc tạo bản sao trong image.
- Mặc định Agent template có thể **backup** bản file trước khi render (`backup=true`); cấu hình `backup=false` nếu không muốn lưu thêm một bản secret cũ, đồng thời kiểm tra chính sách backup ở cấp volume.
- Nếu container app chạy UID khác Agent, có thể cần cấu hình nhóm dùng chung hoặc security context. Quyền `0440` sẽ **chặn** ứng dụng nếu user/group không đúng.
- Không để app tự sửa nội dung file từ Agent. Nếu attacker ghi được file, họ có thể thay credential mà Java tin tưởng, dù không truy cập được Vault.
- Phân biệt **token bị thu hồi** với **dữ liệu file còn tồn tại**: thu hồi token Vault không tự xóa ngay mọi bản secret đã được render. Quy trình revoke/rotate phải tính đến dữ liệu đã nằm trong filesystem và bộ nhớ ứng dụng.

Một file có `mtime` mới có thể là dấu hiệu Agent vừa render, nhưng không đủ chứng minh secret đang hợp lệ. Cần kết hợp chất lượng nội dung, tình trạng Agent, thời gian hiệu lực thực và kiểm thử chức năng. Với credential động hoặc X.509, tuyệt đối không đánh giá độ mới chỉ qua `mtime`.

## 9. Kết hợp cả hai: khi nào hợp lý?

Hệ thống lớn không cần chọn một cách cho **mọi** engine:

| Nhu cầu | Cách triển khai gợi ý | Lý do |
| --- | --- | --- |
| Đọc một API key lúc khởi động ở ứng dụng bên thứ ba | Agent render file | Không yêu cầu sửa ứng dụng để biết Vault |
| Java đọc cấu hình KV theo request có cache TTL | Spring Vault trực tiếp | Ứng dụng kiểm soát thời điểm truy vấn và lỗi |
| Tạo Transit HMAC cho payload riêng mỗi request | Spring Vault trực tiếp | API dùng input và trả output theo từng request |
| Lấy TLS certificate/key cho proxy có cơ chế reload | Agent `pkiCert` hoặc controller PKI riêng | File/secret volume phù hợp với TLS consumer, nếu reload được kiểm thử |
| Dùng database credentials động của connection pool Java | Cân nhắc Spring Vault lease-aware hoặc Agent + reload pool | Cần kiểm soát đồng thời lease và các kết nối đang dùng |
| Runtime ở mạng chỉ truy cập file, không tới Vault | Agent cạnh workload có thể truy cập Vault | Tách phần Vault client khỏi process ứng dụng |
| Điều tra lỗi ngay khi từng call Vault thất bại | Direct client có phân loại exception rõ | App có request context và khả năng quyết định retry |

Một biến thể thứ ba là **Spring Vault gọi HTTP qua Vault Agent proxy/cache**. Khi đó ứng dụng **vẫn gọi API Vault** dù đích HTTP là Agent; không nên nhầm biến thể này với “Java chỉ đọc file Agent render”. Các vấn đề request, token, cache và khả năng Agent proxy cần đánh giá riêng.

Quyết định thiết kế nên được ghi rõ ở cấp workload: ai xác thực, ai sở hữu token, ai đọc Vault, dữ liệu vào ứng dụng qua HTTP hay file, ai chịu trách nhiệm refresh, và chứng cứ nào cho biết secret mới đã được áp dụng.

## 10. Xử lý lỗi theo đúng thành phần gây ra

| Triệu chứng | Với direct client | Với Agent file |
| --- | --- | --- |
| Lỗi `403` | Kiểm tra Vault role/policy của Java token, path KV v2 và namespace | Kiểm tra Vault role/policy/token của **Agent**, đọc Agent logs |
| Secret không tồn tại | `kv.get(...)` có thể trả `null` hoặc API báo lỗi | Agent template thất bại, file không xuất hiện hoặc giữ bản trước tùy trạng thái |
| File không tồn tại | Không áp dụng | Kiểm tra Agent init/sidecar, destination, volume mount, UID/GID |
| Secret thiếu `apiKey` | Java phát hiện map thiếu field | Template phải bật `error_on_missing_key`; app vẫn kiểm tra file rỗng |
| Secret đổi nhưng ứng dụng vẫn dùng cũ | Kiểm tra cache, code có gọi lại `get(...)` không | Kiểm tra Agent render interval, file đã thay chưa, bean/client có reload không |
| Vault bị timeout | Lệnh Java có thể ném exception ngay | Agent báo timeout, file cũ có thể còn đọc được nhưng có nguy cơ stale |
| Token hết hạn | Session manager/login của Java | Auto-auth/token của Agent; Java đọc file có thể chưa nhận thấy lỗi |
| Credential động bị thu hồi | App renew/fetch và cập nhật pool | Agent cần refresh; app vẫn phải cập nhật pool sau khi file đổi |

**Nguyên tắc an toàn:** Không âm thầm thay secret thiếu bằng chuỗi giả hoặc dữ liệu cũ quá thời hạn chỉ để ứng dụng tiếp tục chạy. Phân loại lỗi “chưa nhận được secret”, “file không thể đọc”, “secret đã hết hiệu lực” và “đã áp dụng thành công”. Với dữ liệu tĩnh có thể có chính sách fallback được đánh giá trước; với credential hết hạn hoặc bị thu hồi phải fail closed theo ràng buộc bảo mật.

### Giám sát nên đo cả hai tầng

Với direct client, theo dõi request latency, số lỗi auth/403/429/5xx, TTL token, số lần read KV và mức cache hit/age. Với Agent, theo dõi Agent sống hay chết, auto-auth/retry, lỗi render, thời điểm render thành công, độ tuổi file và dấu hiệu ứng dụng đã **nạp** bản mới.

Các tên như `vault_direct_read_failure_total`, `vault_agent_render_age_seconds` và `secret_runtime_version_age_seconds` chỉ là ví dụ metric có thể tự xây trong Micrometer/Prometheus, không mặc định là metric được Spring Vault hoặc Vault Agent xuất sẵn. Tuyệt đối không gắn raw token/secret làm label.

## 11. Kiểm thử tích hợp cho hai mô hình

Chuẩn bị Vault test instance có mount KV v2 `secret/`, secret `orders/config`, role/policy cho ứng dụng direct và role/policy riêng cho Agent. Có thể dùng Testcontainers/Docker để chạy Vault và Agent trong lab; với Kubernetes thì thử injector/sidecar trong namespace test có service account riêng.

| Kiểm thử | Direct Spring Vault | Agent render file |
| --- | --- | --- |
| Secret ban đầu | `get("orders/config")` đọc đúng `apiKey` | Agent render file với nội dung đúng |
| Thiếu policy `read` | Lời gọi trả lỗi phân quyền | Agent báo lỗi render/403, file không được tạo đúng |
| Secret không tồn tại | Java báo lỗi bắt buộc | Agent lỗi thiếu secret; app không dùng file giả |
| Thiếu field `apiKey` | Validate map thất bại | `error_on_missing_key` gây lỗi template; app không dùng `<no value>` |
| Cập nhật KV từ K1 sang K2 | Gọi lại `get(...)` quan sát K2 | Chờ Agent render và cho app re-read, quan sát K2 |
| Vault tạm mất mạng | Lượt `get(...)` lỗi, retry/circuit theo policy | File cũ có thể còn; cảnh báo stale và áp dụng giới hạn hợp lệ |
| Thay đổi token/role | Client tự refresh auth theo cấu hình | Agent tự re-auth theo cấu hình; kiểm tra log/health |
| Quyền file sai | Không áp dụng | Java bị `AccessDeniedException` và báo rõ |
| Agent dừng | Không áp dụng | App có thể còn đọc bản cuối; giám sát phải phát hiện Agent chết |
| Nạp secret vào bean lúc khởi động | Không tự đổi nếu cache cố định | Không tự đổi dù Agent render file mới |
| Không được log secret | Không log body/token | Không log nội dung file, token hoặc giá trị template |

Để test **độ mới**, nên đặt giá trị K1/K2 giả ở hai phiên bản KV khác nhau, ghi nhận mốc thay đổi và chứng minh từng tầng lần lượt nhận K2. Không chỉ assert file tồn tại: test phải xác minh **giá trị mà nghiệp vụ sử dụng** đã đổi.

Với secret có lease (Database) và PKI, mở rộng test tới hạn của credential/chứng thư, rotation, cập nhật pool/SSL context và khả năng phục hồi khi Vault không sẵn sàng. Đây là các trường hợp mà bài kiểm thử chỉ đọc KV tĩnh chưa bao phủ.

## 12. Checklist thiết kế trước khi triển khai

1. **Nguồn dữ liệu nào?** KV v1/v2, database creds, PKI hay Transit; đường logic và path HTTP của engine đã được xác định đúng?
2. **Ai xác thực?** Process Java, Vault Agent hay cả hai; mỗi danh tính dùng policy tối thiểu nào?
3. **Secret đi qua đường nào?** Response HTTP hay file; có nguy cơ lộ qua log, backup, volume hoặc heap dump không?
4. **Khi nào cập nhật?** Gọi lại API, TTL cache, Agent static render interval, lease renewal hoặc trigger riêng?
5. **Ai nạp bản mới?** Bean Spring, HTTP client, Hikari pool, TLS context hoặc proxy có hỗ trợ refresh không?
6. **Khi Vault mất kết nối?** Đường lỗi, giới hạn retry, thời gian cho phép dùng snapshot cũ và readiness được xác định chưa?
7. **Làm sao xác minh?** Có test K1→K2, lỗi auth, file sai permission, Agent chết, token/lease hết hạn và chứng cứ end-to-end không?

## 13. Ghi nhớ

**Spring Vault client trực tiếp** phù hợp khi code Java cần gọi endpoint Vault theo yêu cầu, đọc KV tại thời điểm do ứng dụng kiểm soát và chủ động xử lý response/exception. **Vault Agent render file** phù hợp khi muốn tách xác thực Vault và việc tải secret ra khỏi code ứng dụng, đặc biệt với chương trình không biết Vault.

Khác biệt lớn nhất nằm ở **trách nhiệm cập nhật**: direct client phải quyết định gọi lại hoặc refresh cache; Agent phải lấy/render lại file, còn ứng dụng vẫn phải đọc lại hoặc reload runtime state. Token renewal, secret lease renewal, ghi file và application reload là **những bước riêng**, không được suy luận rằng bước trước thành công thì bước sau tự thành công.

### Câu hỏi tự kiểm tra

1. Khi KV v2 thay `apiKey` từ K1 sang K2, tại sao Java đọc file do Agent render vẫn có thể thấy K1?
2. `VaultOperations.opsForKeyValue("secret", KV_2).get("orders/config")` khác `secret "secret/data/orders/config"` trong template như thế nào?
3. Nếu Agent renew được database lease nhưng Java Hikari pool giữ connection cũ, hệ thống có chắc sử dụng credential mới không?
4. Khi Vault token của Agent bị thu hồi, file secret đã render có tự biến mất khỏi volume ngay không?
5. Vì sao `spring.config.import=file:/vault/secrets/orders.properties` không có nghĩa mọi bean Spring tự hot reload?
6. Với yêu cầu mã hóa Transit khác nhau mỗi request, bạn chọn direct API hay file Agent render? Nêu lý do.
7. Nếu Agent template dùng `perms="0440"` nhưng app chạy UID/GID khác, bạn cần kiểm tra cấu hình nào?

### Tài liệu tham khảo

- [HashiCorp Vault — Vault Agent](https://developer.hashicorp.com/vault/docs/agent-and-proxy/agent)
- [HashiCorp Vault — Vault Agent Templates, renewal và file permissions](https://developer.hashicorp.com/vault/docs/agent-and-proxy/agent/template)
- [HashiCorp Vault — Vault Agent Injector trong Kubernetes](https://developer.hashicorp.com/vault/docs/deploy/kubernetes/injector)
- [HashiCorp Vault — Injector annotations](https://developer.hashicorp.com/vault/docs/deploy/kubernetes/injector/annotations)
- [HashiCorp Vault — Kubernetes Agent Injector examples](https://developer.hashicorp.com/vault/docs/deploy/kubernetes/injector/examples)
- [Spring Vault — Vault Secrets Engines (KV API)](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html)
- [Spring Vault — VaultKeyValueOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultKeyValueOperations.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
