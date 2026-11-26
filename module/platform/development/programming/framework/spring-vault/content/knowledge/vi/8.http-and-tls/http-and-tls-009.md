# Kiểm soát đường dẫn và URL tuyệt đối truyền vào client

## 1. Vì sao đường dẫn Vault cần được kiểm soát?

Ứng dụng Java sử dụng **Spring Vault** để truy cập **HashiCorp Vault** qua `VaultTemplate`: xác thực theo workload, đọc/ghi KV secrets, quản lý token và lease, mã hóa bằng Transit hoặc cấp chứng chỉ từ PKI. Những thao tác này thường có một phần đường dẫn cố định và một phần được chọn theo ngữ cảnh nghiệp vụ.

Ví dụ dịch vụ đọc cấu hình cho ứng dụng `payments`:

```text
Vault endpoint:  https://vault.example.internal:8200
Namespace:       engineering/payments      (nếu triển khai hỗ trợ)
KV v2 mount:     secret
Vault API path:  /v1/secret/data/apps/payments/config
```

Nếu người viết ứng dụng nhầm **đường dẫn logic trong Vault** với **URL tuyệt đối** hoặc nối thẳng chuỗi do người dùng nhập vào path, hậu quả có thể là:

- Đọc nhầm key/mount/namespace, kể cả secret có mức nhạy cảm cao hơn.
- Đi vào API không mong muốn, ví dụ endpoint ghi, quản lý token hoặc PKI.
- Tạo lỗi `403`, `404`, nhầm lẫn KV v1/v2 hoặc sai path prefix qua gateway.
- Với HTTP client cấp thấp nhận URL tuyệt đối: phát sinh **server-side request forgery (SSRF)** tới host khác.
- Nghiêm trọng hơn, làm **rò Vault token** nếu HTTP client vẫn gắn header xác thực khi gọi sang một origin không được tin cậy.

Mục tiêu là **khóa địa chỉ Vault ở cấu hình đáng tin cậy**, chỉ cho phép các đường dẫn nghiệp vụ có cấu trúc, rồi để Spring Vault hoặc HTTP client được cấu hình đúng xây request.

## 2. Tách bốn khái niệm: endpoint, namespace, API path và secret key

Một request có thể được biểu diễn như sau:

```http
GET /v1/secret/data/apps/payments/config HTTP/1.1
Host: vault.example.internal:8200
X-Vault-Namespace: engineering/payments
X-Vault-Token: <token-của-workload>
```

Đây là HTTP request minh họa; **không đưa token thật vào tài liệu, log hoặc source code**.

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| **Vault endpoint** | `https://vault.example.internal:8200` | Scheme, hostname, port; đích mạng và tên cần xác minh chứng chỉ TLS. |
| **Namespace** | `engineering/payments` | Phạm vi tenant của Vault Enterprise/HCP khi được hỗ trợ; thường truyền bằng `X-Vault-Namespace`. |
| **Vault API path** | `/v1/secret/data/apps/payments/config` | Chọn HTTP API, secrets engine mount và key cần thao tác. |
| **Logical secret path** | `apps/payments/config` | Đường dẫn key bên trong KV mount; API KV v2 có thêm `data/`. |

Đừng coi phần `engineering/payments` là hostname hoặc luôn thêm nó vào đường dẫn KV. Khi namespace đã được chọn bằng header, path của API thường **tương đối với namespace đó**.

**Tiền tố `/v1`** thuộc Vault HTTP API. Với `VaultTemplate.read(String path)`, `path` thường là Vault API path **không có `/v1` ở đầu**, ví dụ `secret/data/apps/payments/config`; template tạo URL hoàn chỉnh dựa trên endpoint. Không ghép tay `/v1` vào tất cả các tầng rồi để nó bị lặp.

## 3. Logical path khác URL tuyệt đối thế nào?

### 3.1. Dạng đường dẫn ứng dụng nên truyền vào Vault operations

Khi dùng Spring Vault ở tầng nghiệp vụ:

```java
// VaultTemplate đã được cấu hình sẵn VaultEndpoint và authentication.
var response = vaultTemplate.read("secret/data/apps/payments/config");
```

Trong ví dụ, `secret/data/apps/payments/config` là **path API tương đối**, không chứa:

- `https://` hoặc `http://`
- hostname và port
- `/v1` lặp ở đầu
- query string tùy ý
- username/password hay token nhúng trong URL

Với Spring Vault KV abstractions, có thể tránh tự quản lý thành phần `data/` của KV v2:

```java
import org.springframework.vault.core.VaultKeyValueBackend;

var kv = vaultTemplate.opsForKeyValue(
        "secret", VaultKeyValueBackend.KV_2);
var response = kv.get("apps/payments/config");
```

Trong ví dụ thứ hai, `secret` là **KV mount**, còn `apps/payments/config` là key bên trong mount. Hãy chọn **một API abstraction nhất quán** để không vô tình nhân đôi `secret/data`.

### 3.2. Dạng URL tuyệt đối

URL tuyệt đối chứa scheme và authority:

```text
https://vault.example.internal:8200/v1/secret/data/apps/payments/config
```

URL tuyệt đối hữu ích cho **cấu hình endpoint hoặc kiểm tra HTTP trực tiếp bằng curl**, nhưng không phải đầu vào được tùy ý đưa vào mọi phương thức `VaultTemplate` vốn mong đợi Vault logical path.

Một số HTTP client tổng quát (`RestTemplate`, `WebClient`, Apache HttpClient) có API nhận **URL tuyệt đối** và sẽ kết nối tới host trong URL ấy. Nếu ứng dụng chuyển nguyên URL từ người dùng vào API đó, **VaultEndpoint được cấu hình ở chỗ khác không tự bảo vệ request cấp thấp**.

> Không giả định `VaultTemplate.read("https://...")` được phép hoặc tự sửa URL tuyệt đối về Vault host. Đây không phải cách dùng được khuyến nghị cho API path; cách xử lý chi tiết phụ thuộc phương thức, client và phiên bản. Hãy coi full URL là **cấu hình được kiểm soát**, còn input nghiệp vụ là **path hoặc key đã kiểm tra**.

## 4. `URI.resolve` và các đầu vào gây lệch đích

Trong Java, `URI.resolve(...)` có thể thay đổi cả host hoặc đường dẫn tùy loại reference:

```java
import java.net.URI;

URI base = URI.create("https://vault.example.internal:8200/v1/");

System.out.println(base.resolve("secret/data/apps/payments/config"));
// https://vault.example.internal:8200/v1/secret/data/apps/payments/config

System.out.println(base.resolve("../sys/health"));
// https://vault.example.internal:8200/sys/health

System.out.println(base.resolve("//other.example.net/v1/"));
// https://other.example.net/v1/

System.out.println(base.resolve("https://other.example.net/v1/"));
// https://other.example.net/v1/
```

Điều đáng chú ý:

- `../` có thể làm path đi lên ngoài khu vực dự định.
- `//other.example.net/...` là **network-path reference**: giữ scheme nhưng **đổi host**.
- `https://other.example.net/...` là **absolute URI**: nó thay thế base URI.
- Chuỗi bắt đầu bằng `/` có thể thay phần path gốc của base.

Nếu một HTTP client được gắn `X-Vault-Token` và tiếp tục gửi request đến `other.example.net` do ghép URL không kiểm soát, token có nguy cơ bị chuyển tới đích không tin cậy.

**Không dùng `URI.resolve(untrustedInput)` làm cơ chế bảo vệ.** Hãy kiểm tra input trước khi xây request và bảo đảm HTTP client cuối cùng vẫn nhắm đúng origin, ngay cả sau redirect.

## 5. Mô hình tấn công cần phòng tránh

### 5.1. Path traversal và nhảy sang mount khác

Nếu API nhận `appId` rồi xây:

```text
secret/data/apps/{appId}/config
```

Một giá trị độc hại như `../admin` hoặc `payments/../../admin` có thể làm đường dẫn sai ý đồ **nếu một tầng URI/proxy thực hiện chuẩn hóa hoặc giải mã theo cách không kiểm soát**. Không dựa vào giả định rằng mọi thành phần sẽ giữ nguyên chuỗi `..` hay giải mã ký tự giống nhau.

### 5.2. Encoded slash, percent-encoding và double decoding

Đầu vào như:

```text
payments%2Fadmin
%2e%2e
%252e%252e
payments%5Cadmin
```

có thể bị diễn giải khác nhau giữa Java URI builder, reverse proxy và Vault API nếu các tầng decode/normalize không thống nhất. Đây là lý do nên **chỉ chấp nhận tập ký tự đúng nhu cầu** cho một segment như `appId`, thay vì tự tìm cách loại bỏ mọi chuỗi traversal nguy hiểm có thể tưởng tượng ra.

**Không tự gọi `URLDecoder.decode` nhiều lần**, không tự encode/decode lặp lại và không dùng một kết quả kiểm tra trước normalize rồi lại gửi biến thể khác sau normalize.

### 5.3. SSRF và truy cập endpoint nội bộ

Nếu ứng dụng nhận `vaultUrl` từ một request người dùng rồi gọi:

```text
GET https://attacker.example/v1/...
GET http://127.0.0.1:...
GET http://169.254.169.254/...
```

HTTP client có thể bị điều khiển truy cập dịch vụ khác thay vì Vault. Các địa chỉ trên là **ví dụ rủi ro**, không phải endpoint hợp lệ để dùng cho Spring Vault. Việc cho phép `https` thôi vẫn không đủ; **hostname, port, redirect và đường egress** phải được kiểm soát.

### 5.4. URL prefix trông đúng nhưng host sai

Các kiểm tra chuỗi như:

```java
if (url.startsWith("https://vault.example.internal")) {
    // KHÔNG đủ để chứng minh URL an toàn.
}
```

có thể chấp nhận các authority không mong muốn, ví dụ `https://vault.example.internal.attacker.example/...`. Thậm chí URI chứa userinfo hoặc cách biểu diễn authority khác có thể làm phép so prefix sai. Khi **bắt buộc** tiếp nhận full URL từ nguồn đáng tin, hãy parse bằng `URI` và kiểm tra **scheme, host, effective port, userinfo, path, query, fragment** theo allowlist rõ ràng.

## 6. Cách an toàn hơn: nhận định danh, không nhận Vault URL

Một dịch vụ nghiệp vụ thông thường không cần cho người gọi tự quyết định URL hoặc mount. Chỉ cho caller đưa **định danh ứng dụng**, còn namespace, endpoint, secrets engine và cấu trúc path do server cấu hình.

Ví dụ Spring service đọc config của một app, với quy tắc app ID chỉ cho phép chữ thường, số, dấu `_` và `-`:

```java
import java.util.regex.Pattern;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class AppSecretReader {
    private static final Pattern APP_ID =
            Pattern.compile("[a-z0-9][a-z0-9_-]{0,63}");

    private final VaultOperations vault;

    public AppSecretReader(VaultOperations vault) {
        this.vault = vault;
    }

    public VaultResponse readAppConfig(String appId) {
        if (appId == null || !APP_ID.matcher(appId).matches()) {
            throw new IllegalArgumentException("appId không hợp lệ");
        }

        String path = "secret/data/apps/" + appId + "/config";
        return vault.read(path);
    }
}
```

Những ưu điểm của cách này:

1. `appId` là **một segment**, không được phép chứa dấu `/`, `\\`, `.`, `%`, `?`, `#`, `:` hoặc ký tự điều khiển. Do đó nó không thể biến thành full URL hay chèn thêm path segment.
2. Endpoint Vault và namespace do cấu hình Spring Vault quyết định, **không do người gọi API chọn**.
3. Mount `secret`, KV v2 API `data/` và hậu tố `config` luôn cố định.
4. Việc kiểm tra xảy ra **trước** khi gọi `VaultOperations`.

Đây là **quy tắc validation riêng của ví dụ**, không phải quy định chung rằng Vault chỉ hỗ trợ các ký tự này trong mọi secret key. Nếu nghiệp vụ cần đường dẫn nhiều cấp, hãy biểu diễn thành **danh sách segment được kiểm tra riêng** hoặc ánh xạ từ định danh sang path nội bộ đã được phê duyệt, không nhận nguyên một chuỗi path tùy ý.

**Lưu ý bảo mật:** Validation chỉ giới hạn path về mặt cú pháp. Ứng dụng vẫn phải kiểm tra **người dùng có quyền truy cập appId đó không**, và Vault token phải có **least-privilege policy**. Một `appId` hợp lệ về ký tự không tự đồng nghĩa người gọi được quyền đọc secret của ứng dụng ấy.

### 6.1. Trường hợp cần KV v2 abstraction

Trong lớp xử lý KV chuyên biệt, có thể dùng:

```java
import org.springframework.vault.core.VaultKeyValueBackend;

// appId đã được validate và authorize theo quy tắc ở trên.
var kv = vaultTemplate.opsForKeyValue(
        "secret", VaultKeyValueBackend.KV_2);
var value = kv.get("apps/" + appId + "/config");
```

Ở cách này, Spring Vault quản lý phần API path của KV v2; code nghiệp vụ chỉ xử lý key tương đối. Không đồng thời truyền `secret/data/apps/...` vào `kv.get(...)` rồi gây nhân đôi mount và `data`.

## 7. Kiểm soát URL tuyệt đối khi thật sự phải dùng HTTP client cấp thấp

Một số tác vụ vận hành hoặc tích hợp đặc thù cần HTTP endpoint không có abstraction tương ứng. Khi đó ứng dụng có thể cần `RestOperations`, `RestTemplate` hoặc `VaultClient` với path/method cụ thể.

**Nguyên tắc ưu tiên:** thay vì chấp nhận một full URL từ caller, hãy sử dụng **endpoint cố định** và một tập **route cố định** được code định nghĩa:

```text
Trusted endpoint: https://vault.example.internal:8200
Allowed route:     /v1/sys/health
Allowed route:     /v1/auth/token/lookup-self
Rejected input:    https://other.example.net/v1/...
```

Ví dụ chỉ xây URI cho endpoint quản lý được phép:

```java
import java.net.URI;
import org.springframework.web.client.RestTemplate;

URI healthUri = URI.create(
        "https://vault.example.internal:8200/v1/sys/health");

RestTemplate publicHealthClient = new RestTemplate();
String body = publicHealthClient.getForObject(healthUri, String.class);
```

Đoạn này chỉ minh họa **URI cố định**, không phải khuyến nghị tạo `RestTemplate` mới ở mỗi request. `/sys/health` có thể trả status khác `200` tùy trạng thái Vault; không dùng response này để suy ra workload được quyền đọc KV. Ứng dụng sản xuất nên chia sẻ client đã cấu hình timeout/TLS phù hợp.

### 7.1. Khi đầu vào là cấu hình vận hành của một endpoint

Nếu thực sự phải nhận **full URL từ cấu hình quản trị** (không phải API caller), cần:

- Parse với `java.net.URI`; từ chối URI tương đối, `userInfo`, query/fragment không mong muốn và scheme không phải `https`.
- Kiểm tra **hostname đã parse** với allowlist cụ thể và port hợp lệ; tránh so sánh `startsWith` trên chuỗi.
- Kiểm tra path theo **danh sách operation được phép**, không chỉ prefix `/v1/` vì prefix ấy còn chứa rất nhiều API nhạy cảm.
- Dùng DNS/egress/firewall policy hạn chế các host có thể truy cập; hostname allowlist không thay thế kiểm soát mạng.
- Hạn chế hoặc vô hiệu hóa redirect ra ngoài tập origin được duyệt; không tin `Location` một cách mù quáng.
- Không gắn `X-Vault-Token`, `Authorization` hoặc cookie vào một HTTP client tổng quát có thể gọi các URL không thuộc Vault.

Nếu chỉ có một Vault endpoint, **hardcode URI nguồn tin cậy trong cấu hình ứng dụng** và cung cấp qua dependency injection thường đơn giản, ít rủi ro hơn một bộ validator URL tổng quát tự viết.

### 7.2. Redirect trong Vault HA và reverse proxy

Vault HA có thể công bố một `api_addr` để phục vụ các tình huống chuyển hướng/định tuyến. Nếu client gặp redirect, đích mới có thể là một Vault node khác hoặc một URL qua gateway.

Trường hợp hợp lệ cần được thiết kế từ trước: host của `Location` phải có **DNS, mạng và TLS SAN/CA** được client tin, đồng thời được cho phép theo chính sách egress. Khi dùng HTTP client kèm token, cần xác minh client có theo redirect không và **headers nhạy cảm được xử lý ra sao khi đổi origin**; đừng suy diễn mọi thư viện tự loại token hoặc đều giữ nó giống nhau.

Với API có side effect (PKI issue, tạo credential, ghi KV), một redirect/retry không phù hợp còn có thể làm request được gửi lại ngoài ý muốn. Cần phân biệt HTTP redirect, lỗi mạng, idempotency và chính sách retry.

## 8. Kiểm soát mount path, KV version và các thao tác Vault

Một chuỗi `path` nhìn có vẻ hợp lệ nhưng có thể là **sai operation**:

| Mục tiêu | Ví dụ Vault logical API path | Ghi chú |
| --- | --- | --- |
| KV v1 read | `secret/app/config` | Chỉ đúng khi mount `secret` là KV v1. |
| KV v2 read | `secret/data/app/config` | `data/` là phần API của KV v2. |
| KV v2 metadata | `secret/metadata/app/config` | Không đồng nghĩa đọc secret value; có quyền và API khác. |
| Transit encrypt | `transit/encrypt/app-key` | Thường là thao tác `POST`, không phải KV read. |
| PKI issue | `pki/issue/app-role` | Có thể tạo chứng chỉ, là thao tác có tác dụng phụ. |
| Kubernetes login | `auth/kubernetes/login` | Auth mount phải được thiết lập đúng. |
| Token renewal | `auth/token/renew-self` | Dùng trong lifecycle, không phải secret key. |

**Không cho client bên ngoài tự chỉ định mount hoặc operation** chỉ bằng một string `path`. Một API như `GET /config/{appId}` chỉ nên map tới một operation cố định (KV read của app), không phải một proxy HTTP tùy ý cho toàn bộ Vault.

Việc Vault phân quyền là lớp bảo vệ độc lập. Ví dụ policy cho token nghiệp vụ chỉ cho phép đọc đúng nhánh KV:

```hcl
path "secret/data/apps/payments/config" {
  capabilities = ["read"]
}
```

Nếu workload cần nhiều app riêng, thiết kế policy theo cơ chế cấp quyền thực tế, tránh cấp `sudo` hoặc quyền ghi/quản trị rộng chỉ để ứng dụng có thể đọc config. Bảo vệ ở **cả tầng Java (validation + business authorization)** và **Vault (policy)**.

## 9. Namespace, proxy và path prefix có thể làm phức tạp việc ghép URL

### 9.1. Namespace header không phải prefix của Vault endpoint

Ở một triển khai Vault Enterprise có namespace `engineering/payments`:

```text
Endpoint:     https://vault.example.internal:8200
Namespace:    engineering/payments
API path:     /v1/secret/data/app/config
```

Với Spring Cloud Vault:

```yaml
spring:
  cloud:
    vault:
      uri: "https://vault.example.internal:8200"
      namespace: "engineering/payments"
      kv:
        backend: secret
        backend-version: 2
```

Nếu namespace được gửi bằng `X-Vault-Namespace`, đừng tiếp tục nhân đôi `engineering/payments` trong `kv.backend` hoặc `VaultTemplate.read`. Namespace chọn không gian logic, trong khi `secret/data/...` là path trong không gian đó.

### 9.2. Forward proxy và reverse proxy

**Forward proxy** (egress) quyết định đường mạng mà HTTP client dùng để kết nối tới Vault. Nó không phải base URL của Vault API. Không bao giờ cho người dùng nhập `proxyUrl` để ghi đè host của Vault endpoint.

**Reverse proxy/ingress** có thể công bố `https://gateway.example.com/vault` rồi rewrite `/vault/v1/...` thành `/v1/...`. Nếu thiết kế bắt buộc dùng path prefix, phải cấu hình và kiểm thử **đúng cách client xây base URI** cho phiên bản Spring Vault đang chạy. Không mặc định chỉ thêm `/vault` vào mọi `spring.cloud.vault.uri` là đủ, vì client có thể tự ghép hoặc chuẩn hóa path theo cách khác.

Một lỗi thường gặp:

```text
Mong muốn:
  Client → /vault/v1/secret/data/app/config
  Proxy  → /v1/secret/data/app/config

Sai:
  Client → /vault/v1/secret/data/app/config
  Proxy  → /vault/v1/secret/data/app/config
  Vault  → 404
```

Khi debug, hãy xác minh **request path cuối cùng tại Vault**, không chỉ log “Vault URL” ở tầng controller.

## 10. Kiểm thử validation và HTTP request thực tế

### 10.1. Test các `appId` không hợp lệ trước khi gọi Vault

Dùng JUnit 5 và Mockito theo ví dụ service ở mục 6:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.vault.core.VaultOperations;

class AppSecretReaderTest {
    @ParameterizedTest
    @ValueSource(strings = {
        "../admin", "payments/other", "https://evil.example",
        "payments%2Fadmin", "payments?list=true", "payments#x",
        "payments\\admin", ".", ".."
    })
    void rejectsUnsafeAppId(String candidate) {
        VaultOperations vault = mock(VaultOperations.class);
        AppSecretReader reader = new AppSecretReader(vault);

        assertThrows(IllegalArgumentException.class,
                () -> reader.readAppConfig(candidate));
        verifyNoInteractions(vault);
    }
}
```

Đây là **unit test** cho ranh giới input. Để tăng độ tin cậy, còn cần test trường hợp `appId` hợp lệ tạo đúng path và các kiểm tra **business authorization** của người dùng/tenant.

### 10.2. Integration test với HTTP mock server

Mock HTTP server có thể ghi nhận **HTTP method, Host, path, query, headers** mà client thực sự phát ra. Các kiểm tra có giá trị:

1. Client luôn kết nối đến **Vault endpoint đã cấu hình**, không phải một URL do caller kiểm soát.
2. `readAppConfig("payments")` tạo đúng `GET /v1/secret/data/apps/payments/config`.
3. Đầu vào có `../`, `%2F`, `?`, `#` hoặc URL tuyệt đối bị từ chối **trước khi phát HTTP request**.
4. Khi dùng namespace, request có đúng `X-Vault-Namespace` và không nhân đôi namespace trong path.
5. Khi dùng KV v2 abstraction, phần `data/` và mount không lặp hoặc bị bỏ sót.
6. Trường hợp gateway thêm/bỏ path prefix phải được test qua đúng route triển khai.
7. Redirect ngoài allowlist không khiến request được gửi đến host khác cùng Vault token.
8. Token/session manager và luồng token/lease renewal dùng đúng endpoint, namespace và transport được cấu hình.

Mock server chứng minh **request được xây đúng**; nó không thay việc kiểm thử policy, namespace và semantics KV/Transit/PKI trên Vault thử nghiệm thật.

## 11. Chẩn đoán các lỗi do URL hoặc đường dẫn

| Biểu hiện | Nguyên nhân có thể | Nơi cần kiểm tra |
| --- | --- | --- |
| `UnknownHostException` | Hostname trong absolute URL bị chọn sai, DNS không phân giải. | Vault endpoint, proxy route và host sau redirect. |
| Lỗi TLS hostname/SAN | Client kết nối sang host khác certificate được cấp. | URI cuối cùng, SNI, SAN và truststore. |
| HTTP `404` ở KV v2 | Dùng path KV v1, lặp `data/`, sai mount/namespace hoặc proxy rewrite. | HTTP path cuối, KV engine version và namespace header. |
| HTTP `403` | Token/policy không có quyền path yêu cầu, namespace khác. | Vault auth, policy, path và token lifecycle. |
| HTTP `405` | Gọi sai method trên API endpoint. | Method GET/POST/LIST và API contract của Vault. |
| HTTP `502/504` qua gateway | Upstream path/route, timeout hoặc backend không sẵn sàng. | Ingress, proxy, Vault listener và log upstream. |
| Secret của app khác được trả | Ánh xạ tenant/appId sai hoặc token quá rộng. | Authorization ở ứng dụng, mapping path và Vault policy. |
| Token xuất hiện ở log/host lạ | HTTP client tổng quát theo URL không kiểm soát hoặc redirect. | Toàn bộ outbound HTTP call, header injection, egress và secret masking. |

Khi xử lý lỗi, phân biệt **path validation bị từ chối tại ứng dụng** với **Vault trả HTTP status** và **transport thất bại**. Đừng cố “sửa” lỗi `403` bằng cách vô hiệu hóa TLS, mở rộng policy sang `*` hoặc cho phép caller truyền URL tùy ý để thử lại.

## 12. Các tình huống tự luyện

**Tình huống A — Nhầm absolute URL với logical path:** lập trình viên gọi `vaultTemplate.read("https://vault.example.internal:8200/v1/secret/data/app/config")`. Đúng hướng là giữ Vault endpoint trong cấu hình và gọi `vaultTemplate.read("secret/data/app/config")` hoặc KV v2 operations. Không dựa vào việc template tự xử lý một URL đầy đủ.

**Tình huống B — Client nhận `redirectUrl` từ request người dùng:** tầng HTTP cấp thấp ghép URL và mang theo token mặc định. Đó là nguy cơ SSRF/lộ token. Thiết kế lại để request chỉ chọn operation/path hợp lệ trên Vault host cố định; khi cần redirect cho Vault HA, dùng allowlist origin và test header.

**Tình huống C — KV v2 trả 404 sau khi chuyển sang `opsForKeyValue`:** mã cũ truyền `secret/data/apps/payments/config` vào `VaultTemplate.read`; mã mới lại đưa nguyên chuỗi đó vào `kv.get(...)`. KV abstraction mong đợi **key bên trong mount**, chẳng hạn `apps/payments/config`, không phải API path đầy đủ.

**Tình huống D — Một tenant yêu cầu đọc secret tenant khác:** giá trị `appId` chỉ có chữ và số, nên qua được kiểm tra cú pháp. Tuy nhiên, người dùng không được phép truy cập app ấy. Cần xác thực và authorize ánh xạ tenant → appId, kèm token/policy giới hạn quyền, thay vì coi regex validation là đủ.

**Tình huống E — Gateway đổi path prefix và auth login thất bại:** request nghiệp vụ đọc KV có vẻ đúng nhưng client auth tạo `/v1/auth/kubernetes/login` đi qua gateway chưa rewrite. Phải kiểm tra mọi loại request (login, KV, Transit, PKI, token/lease), không chỉ một đường dẫn thành công.

### Ghi nhớ

**Endpoint Vault là cấu hình đáng tin; path của Vault operations là một phần API; input nghiệp vụ nên là định danh đã kiểm tra, không phải full URL.** Đối với Spring Vault, ưu tiên `VaultTemplate` hoặc các operations chuyên biệt, khóa mount và API route theo mục tiêu nghiệp vụ, tách namespace khỏi path, kiểm soát redirect và mọi HTTP client có gắn token. Kết hợp **validation, business authorization, policy Vault tối thiểu, TLS và egress controls** để tránh vừa gọi sai API vừa vô tình gửi bí mật sang host không mong muốn.
