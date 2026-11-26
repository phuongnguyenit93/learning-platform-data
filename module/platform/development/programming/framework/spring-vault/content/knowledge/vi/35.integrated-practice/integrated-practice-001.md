# Đọc cấu hình nhạy cảm từ KV bằng VaultTemplate

## 1. Tình huống thực hành và mục tiêu

Bạn đang phát triển `orders-api` bằng **Java + Spring Boot**. Dịch vụ cần một API key để gọi cổng thanh toán và một giá trị `region` để chọn khu vực xử lý. Đưa key vào `application.yml`, source code, Docker image hoặc Git là lựa chọn không phù hợp: bí mật sẽ bị sao chép sang nhiều môi trường, khó thu hồi và không có kiểm soát truy cập ở cấp workload.

Trong module **Spring Vault**, ứng dụng dùng `VaultTemplate` (triển khai của `VaultOperations`) để đọc bí mật từ **HashiCorp Vault**, xác thực theo workload và tuân theo Vault policy. Bài thực hành tổng hợp này tập trung vào một kịch bản cụ thể: **đọc cấu hình nhạy cảm được lưu ở KV version 2, kiểm tra dữ liệu rồi chuyển cho consumer Java mà không làm lộ giá trị**.

Dữ liệu mẫu (chỉ dành cho lab):

| Trường | Giá trị thử nghiệm | Ý nghĩa |
| --- | --- | --- |
| Vault KV mount | `secret/` | Secrets engine KV v2 |
| Secret path trong mount | `orders/payment` | Cấu hình thanh toán của `orders-api` |
| `apiKey` | `TEST_ONLY_PAYMENT_KEY_A` | API key giả, không thể dùng ngoài lab |
| `region` | `sandbox-eu` | Thông tin cấu hình không nhạy cảm |
| Java client | `VaultTemplate` | Đọc secret qua HTTP API có xác thực |
| Quyền | `read` trên `secret/data/orders/payment` | Không cấp quyền đọc cả mount |

**Kết quả hoàn thành** là một reader Java có thể gọi `vaultTemplate.read("secret/data/orders/payment")`, bóc đúng `data.data`, xác minh các field bắt buộc, đọc KV version và không log API key. Test phải phát hiện được cấu hình sai, token thiếu quyền và việc rotate sang phiên bản mới.

Các thành phần Transit encryption, PKI, token/lease và giám sát vẫn liên quan trong hệ thống hoàn chỉnh, nhưng **không trộn chúng vào cùng một thao tác KV**. KV v2 lưu secret tĩnh có version; nó không tự cấp credential động có lease, không làm Transit encrypt và không tự rotate certificate.

## 2. Kiến trúc luồng đọc secret

~~~mermaid
sequenceDiagram
    participant App as orders-api
    participant VT as VaultTemplate
    participant Auth as ClientAuthentication / SessionManager
    participant Vault as HashiCorp Vault KV v2
    participant Payment as Payment client
    App->>VT: read("secret/data/orders/payment")
    VT->>Auth: Lấy token workload còn hiệu lực
    Auth-->>VT: Vault session token
    VT->>Vault: GET /v1/secret/data/orders/payment
    Note over VT,Vault: X-Vault-Token: <token không log>
    Vault->>Vault: Kiểm tra Vault policy trên path
    Vault-->>VT: JSON data.data + data.metadata
    VT-->>App: VaultResponse
    App->>App: Validate apiKey, region, version
    App->>Payment: Cung cấp apiKey nội bộ khi cần
~~~

**Hai ranh giới cần nhớ:**

1. **Vault xác thực và phân quyền:** một token chỉ được đọc khi Vault policy của token đó cấp capability `read` trên path KV v2. Biết path không phải là có quyền đọc; health endpoint trả 200 không chứng minh quyền đọc KV.
2. **Ứng dụng chịu trách nhiệm xử lý payload:** `VaultTemplate` trả đối tượng `VaultResponse`, còn Java phải kiểm tra dữ liệu và quyết định khi nào giữ, refresh hoặc ngừng sử dụng secret. Không được đưa `VaultResponse` hay raw `Map` chứa secret ra HTTP response/log.

## 3. Hiểu path KV v2 trước khi viết Java

Vault KV secrets engine có hai phiên bản API: **KV v1** và **KV v2**. Trong bài này mount là `secret/`, **phiên bản 2**.

| Công việc | Lệnh Vault CLI | HTTP API / path cho `VaultTemplate` |
| --- | --- | --- |
| Ghi giá trị | `vault kv put -mount=secret orders/payment ...` | `POST /v1/secret/data/orders/payment` |
| Đọc giá trị | `vault kv get -mount=secret orders/payment` | `GET /v1/secret/data/orders/payment` |
| Đọc phiên bản cụ thể | `vault kv get -mount=secret -version=2 orders/payment` | `GET /v1/secret/data/orders/payment?version=2` |
| Đọc metadata của key | `vault kv metadata get -mount=secret orders/payment` | `GET /v1/secret/metadata/orders/payment` |

**Không viết `vaultTemplate.read("secret/orders/payment")` cho KV v2.** Đoạn `data/` là một phần của API path KV v2. Đồng thời, quyền `read` ở `secret/data/...` **không tự cấp** quyền `list` tại `secret/metadata/...`.

### 3.1. Hai lớp `data` trong phản hồi

Phản hồi HTTP minh họa của Vault:

~~~json
{
  "request_id": "<opaque-request-id>",
  "data": {
    "data": {
      "apiKey": "TEST_ONLY_PAYMENT_KEY_A",
      "region": "sandbox-eu"
    },
    "metadata": {
      "created_time": "2026-11-25T08:00:00Z",
      "deletion_time": "",
      "destroyed": false,
      "version": 1
    }
  }
}
~~~

Khi gọi `VaultTemplate.read(...)`, `VaultResponse.getData()` đã tương ứng với **`data` ngoài cùng** của HTTP response; kết quả bên trong nó là một `Map`:

~~~text
VaultResponse.getData()
   |
   +-- "data"      -> { "apiKey": "...", "region": "sandbox-eu" }
   |
   +-- "metadata"  -> { "version": 1, "created_time": "...", ... }
~~~

Vì vậy:

~~~java
VaultResponse response =
        vaultTemplate.read("secret/data/orders/payment");

// Phản hồi KV v2 cần thêm một lớp "data".
Map<String, Object> envelope = response.getRequiredData();
Object values = envelope.get("data"); // Chưa phải apiKey!
~~~

Nếu `response.getData().get("apiKey")` trả `null`, chưa chắc secret bị thiếu: rất có thể bạn đang bóc **sai lớp JSON**. Một API khác như `opsForKeyValue("secret", KV_2).get("orders/payment")` sẽ chủ động bỏ bớt lớp bao; không nên copy parser từ API đó sang `VaultTemplate.read` mà không kiểm tra.

### 3.2. KV version không phải lease TTL

`metadata.version` tăng khi tạo phiên bản KV mới. Nó không cho biết credential còn hợp lệ trong bao lâu. KV v2 là **versioned static secrets engine**; nếu giá trị `apiKey` bị nhà cung cấp thanh toán thu hồi, việc lưu version cũ trong Vault không khiến key đó tiếp tục có hiệu lực. Vòng đời Vault session token, dynamic credential lease và certificate expiration là các khái niệm khác.

## 4. Chuẩn bị môi trường Vault lab

### 4.1. Yêu cầu

- Java 17+ và dự án Spring Boot có `spring-vault-core`.
- Docker + CLI `vault` trên máy thực hành, hoặc Vault dev/test riêng do bạn kiểm soát.
- `curl` và `jq` để xem **cấu trúc** phản hồi khi cần; đừng dùng chúng để in secret thật vào log.
- Kết nối chỉ tới Vault lab, **không dùng môi trường production**.

Ví dụ bật một Vault dev container (chạy ở terminal riêng):

~~~bash
docker run --rm --name spring-vault-kv-lab \
  -p 127.0.0.1:8200:8200 \
  -e VAULT_DEV_ROOT_TOKEN_ID=dev-only-root-token \
  hashicorp/vault:1.20 \
  server -dev -dev-listen-address=0.0.0.0:8200
~~~

Ở terminal thao tác Vault:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_TOKEN="dev-only-root-token"

# Chỉ xem mount và phiên bản engine; không ghi secret vào log.
vault secrets list
~~~

**Cảnh báo bảo mật:** Vault dev mode lưu dữ liệu tạm và dùng token thử nghiệm có quyền rộng; HTTP không có TLS trong ví dụ **chỉ chấp nhận với loopback/local lab**. Không mở port dev mode lên mạng chung, không copy token này vào ứng dụng production. Production phải dùng HTTPS, CA đã kiểm chứng, workload auth và Vault ACL tối thiểu. Tag Docker cố định là ví dụ; trong CI cần khóa phiên bản Vault theo ma trận hỗ trợ của dự án.

Nếu `secret/` chưa là KV v2 ở môi trường test, quản trị viên có thể tạo mount riêng, ví dụ `secret/` với `vault secrets enable -path=secret -version=2 kv` **chỉ khi mount chưa tồn tại**. Không tắt/xóa mount đang có dữ liệu để chạy lab.

### 4.2. Ghi secret giả bằng CLI

~~~bash
# Chỉ dữ liệu giả, không dùng key thật.
vault kv put -mount=secret orders/payment \
  apiKey="TEST_ONLY_PAYMENT_KEY_A" \
  region="sandbox-eu"

# Đọc metadata mà không hiển thị giá trị apiKey.
vault kv metadata get -mount=secret orders/payment
~~~

Khi chạy `vault kv get ...` trong dev lab, CLI có thể **in giá trị bí mật**. Với secret thật, không in toàn bộ response vào terminal, CI log hoặc ticket. Đọc từng field có kiểm soát chỉ trong môi trường được phê duyệt.

### 4.3. Ghi policy chỉ được đọc một secret

Quản trị viên dùng token có quyền phù hợp để tạo policy:

~~~bash
vault policy write orders-kv-read - <<'HCL'
path "secret/data/orders/payment" {
  capabilities = ["read"]
}
HCL
~~~

Đây là policy chính xác cho **KV v2 API path**, không phải `secret/orders/payment`.

| Quyền | Lab `orders-kv-read` | Lý do |
| --- | --- | --- |
| `read` tại `secret/data/orders/payment` | **Cho phép** | Ứng dụng cần lấy hai field |
| `create`/`update`/`patch` tại path đó | Không cấp | Ứng dụng không phải bên quản trị cấu hình |
| `delete`/`destroy` | Không cấp | Ngăn xoá dữ liệu/version |
| `list` tại `secret/metadata/*` | Không cấp | Không cần liệt kê danh sách secrets |
| `read` tại `secret/data/orders/*` | Không cấp | Hạn chế blast radius khi token bị lộ |
| `sudo` hay quyền admin | Không cấp | Không cần cho bài đọc KV |

Tạo token thử nghiệm có đúng policy cho **local lab**, thay vì để Java dùng root token:

~~~bash
# VAULT_TOKEN vẫn là token admin của lab trong terminal này.
# Lệnh này tạo child token và chỉ truyền giá trị qua biến môi trường.
export APP_VAULT_DEV_TOKEN="$(
  vault token create -policy=orders-kv-read -field=token
)"

# Java lab dùng địa chỉ + token read-only qua environment.
export APP_VAULT_URL="$VAULT_ADDR"
~~~

Không chạy `echo "$APP_VAULT_DEV_TOKEN"` để debug hoặc dùng shell tracing `set -x`. Quy trình production nên dùng **Kubernetes auth, AppRole có kiểm soát hoặc workload identity** để nhận token ngắn hạn; ví dụ token ở biến môi trường chỉ dùng cho lab và minh họa `TokenAuthentication`.

### 4.4. Kiểm tra quyền của token lab

Trước khi chạy Java, thử dưới token read-only trong một subshell:

~~~bash
(
  export VAULT_TOKEN="$APP_VAULT_DEV_TOKEN"
  vault token capabilities secret/data/orders/payment
  vault token capabilities secret/data/orders/other
)
~~~

Kỳ vọng: path `payment` có `read`, path khác không có quyền (`deny`). Dùng token read-only để thử `vault kv put` tại cùng path phải bị Vault từ chối; **không cần thực hiện ghi thất bại nhiều lần**. Khi kiểm tra quyền phải chú ý Vault Enterprise namespace nếu tổ chức dùng namespace khác root.

## 5. Khai báo dependency và cấu hình Java

### 5.1. Dependency tối thiểu

Trong dự án Spring Boot, thêm module Spring Vault (phiên bản do BOM/dependency management của dự án kiểm soát):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.vault</groupId>
        <artifactId>spring-vault-core</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đây là **đoạn dependency**, không phải toàn bộ `pom.xml`. Bạn vẫn cần parent/BOM phù hợp và phiên bản Spring Boot/Spring Vault tương thích. Không ghép tùy ý các bản major vì API client hoặc Spring Framework có thể thay đổi.

Spring Cloud Vault cung cấp tích hợp cấu hình (`spring.config.import=vault://`), nhưng bài này **chủ động gọi `VaultTemplate`** để điều khiển rõ thời điểm đọc, xử lý schema và vòng đời secret. Không vô tình bật hai cơ chế cấu hình Vault cùng lúc nếu chưa xác định bean nào sở hữu authentication/session.

### 5.2. Tạo `VaultTemplate` dành riêng cho profile local

~~~java
import java.net.URI;
import java.util.Objects;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

@Configuration
@Profile("local")
public class LocalVaultConfiguration {

    @Bean
    VaultTemplate vaultTemplate() {
        String url = Objects.requireNonNull(
                System.getenv("APP_VAULT_URL"),
                "APP_VAULT_URL is required");

        String token = Objects.requireNonNull(
                System.getenv("APP_VAULT_DEV_TOKEN"),
                "APP_VAULT_DEV_TOKEN is required");

        return new VaultTemplate(
                VaultEndpoint.from(URI.create(url)),
                new TokenAuthentication(token));
    }
}
~~~

Ví dụ trên dành riêng cho `local`, dùng `APP_VAULT_URL` và `APP_VAULT_DEV_TOKEN` đã export trong lab. **Không bật profile `local` hoặc `TokenAuthentication` với token hardcoded ở production**. Nếu ứng dụng có sẵn Spring Cloud Vault auto-configuration, phải thống nhất cấu hình bean để tránh trùng hai `VaultTemplate`.

Trong production, thường **không cần ứng dụng tự parse token từ env**: platform cung cấp một `ClientAuthentication` đúng workload (Kubernetes/AppRole/JWT, v.v.) và cấu hình TLS của Vault client/session manager. Để nhấn mạnh phần kết hợp, constructor thông dụng của Spring Vault là:

~~~java
// Pseudocode cấu hình production: authentication và endpoint
// phải được tạo bởi cấu hình nền tảng có xác minh TLS/identity.
VaultTemplate vaultTemplate = new VaultTemplate(
        approvedVaultEndpoint,
        configuredClientAuthentication);
~~~

`VaultTemplate` có thể tái sử dụng giữa nhiều thread sau khi cấu hình. Dùng dependency injection để các service chia sẻ instance thay vì khởi tạo client mới theo mỗi HTTP request.

## 6. Xây dựng reader đọc KV v2 bằng `VaultTemplate`

Đây là **trọng tâm của bài**. Đọc đúng path và bóc hai lớp `data`; nếu Vault không trả dữ liệu, thiếu field hoặc kiểu dữ liệu sai, fail rõ ràng và **không thay bằng API key rỗng**.

### 6.1. DTO nội bộ không tự lộ API key khi log

~~~java
public record PaymentSettings(
        String apiKey,
        String region,
        long kvVersion) {

    public PaymentSettings {
        if (apiKey == null || apiKey.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing required payment credential");
        }
        if (region == null || region.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing required payment region");
        }
    }

    @Override
    public String toString() {
        return "PaymentSettings[apiKey=REDACTED, region="
                + region + ", kvVersion=" + kvVersion + "]";
    }
}
~~~

Mẫu này che `apiKey` khi gọi `toString()`. Nó **không biến object thành an toàn để serialize ra JSON**: getter `apiKey()` vẫn có thể được framework xuất ra. Giữ DTO trong package nội bộ, không trả trực tiếp từ controller, không đặt vào log MDC, metrics label, APM hay exception. Secret vẫn tồn tại trong heap Java cho đến khi ứng dụng ngừng giữ tham chiếu; `String` không bảo đảm xóa dữ liệu tức thì.

### 6.2. Service `PaymentSettingsReader`

~~~java
import java.util.Map;
import java.util.Objects;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

@Service
public final class PaymentSettingsReader {

    // API path thực của KV v2, không phải path kiểu CLI.
    private static final String VAULT_PATH =
            "secret/data/orders/payment";

    private final VaultTemplate vaultTemplate;

    public PaymentSettingsReader(VaultTemplate vaultTemplate) {
        this.vaultTemplate = Objects.requireNonNull(vaultTemplate);
    }

    public PaymentSettings loadFresh() {
        VaultResponse response = vaultTemplate.read(VAULT_PATH);

        // Một số tình huống key không tồn tại có thể trả null;
        // lỗi HTTP/auth khác có thể ném VaultException.
        if (response == null || response.getData() == null) {
            throw new IllegalStateException(
                    "Payment settings are unavailable");
        }

        // VaultResponse.getData() là lớp "data" bên ngoài.
        Map<String, Object> envelope = response.getData();

        // KV v2 có data.data và data.metadata.
        Object valuesObject = envelope.get("data");
        if (!(valuesObject instanceof Map<?, ?> values)) {
            throw new IllegalStateException(
                    "Unexpected KV v2 response structure");
        }

        Object apiKeyObject = values.get("apiKey");
        Object regionObject = values.get("region");

        if (!(apiKeyObject instanceof String apiKey)
                || apiKey.isBlank()) {
            throw new IllegalStateException(
                    "Required payment API key is missing");
        }
        if (!(regionObject instanceof String region)
                || region.isBlank()) {
            throw new IllegalStateException(
                    "Required payment region is missing");
        }

        long version = -1L;
        Object metadataObject = envelope.get("metadata");
        if (metadataObject instanceof Map<?, ?> metadata) {
            Object versionObject = metadata.get("version");

            if (versionObject instanceof Number n) {
                version = n.longValue();
            }
        }

        return new PaymentSettings(apiKey, region, version);
    }
}
~~~

**Giải thích từng bước:**

1. `vaultTemplate.read(VAULT_PATH)` gửi request tới `GET /v1/secret/data/orders/payment` thông qua context xác thực của Spring Vault. Không tự ghép `X-Vault-Token` vào source code.
2. Kiểm tra response/null để phân biệt key vắng mặt với dữ liệu hợp lệ; theo phiên bản HTTP client, Vault có thể ném exception cho một số mã non-2xx.
3. `envelope.get("data")` lấy map giá trị ở **lớp KV v2 thứ hai**.
4. Kiểm tra `apiKey` và `region` **đúng kiểu String** và không rỗng. Không chuyển bất kỳ object nào thành chuỗi để “cứ dùng được” (ví dụ map hoặc số sai schema).
5. `metadata.version` là metadata cho KV v2; giá trị `-1` là sentinel nếu không đọc được metadata theo cấu trúc dự kiến. Với hệ thống phải kiểm soát rotation chặt, nên **fail** khi version không hợp lệ thay vì chấp nhận `-1`.
6. Trả DTO nội bộ; không log response, map, API key hoặc HTTP request headers.

Trong một hệ thống thực, hãy tách lỗi `missing key`, `invalid schema`, `access denied` và `temporarily unavailable` bằng loại exception/hệ telemetry phù hợp. Các chuỗi lỗi ở ví dụ được viết cố định, không nối nội dung secret vào exception message.

### 6.3. Tại sao không hardcode `VaultOperations.write(...)` vào reader?

Reader của `orders-api` chỉ cần đọc; không nên có khả năng ghi secret. Dữ liệu được cấp qua CLI/terraform/admin pipeline với quyền riêng. Dù Java có phương thức `vaultTemplate.write`, Vault policy giới hạn token đọc chỉ cấp `read` nên thao tác ghi vẫn bị từ chối. Tách bên phát hành cấu hình khỏi bên sử dụng giúp giữ nguyên tắc **least privilege**.

## 7. Gọi reader đúng thời điểm trong ứng dụng

### 7.1. Đọc ngay khi khởi động nếu secret bắt buộc

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PaymentStartupChecks {

    @Bean
    ApplicationRunner verifyPaymentSettings(PaymentSettingsReader reader) {
        return args -> {
            PaymentSettings loaded = reader.loadFresh();
            // Chỉ log kết quả và KV version (nếu đã được phê duyệt).
            // Không log loaded hoặc loaded.apiKey().
            if (loaded.kvVersion() < 1) {
                throw new IllegalStateException(
                        "Payment KV version unavailable");
            }
        };
    }
}
~~~

Startup hook giúp **phát hiện sớm** path/ACL/schema sai. Nếu secret bắt buộc cho việc nhận traffic, readiness phải chưa đạt khi thiếu secret; không được chỉ dựa vào cổng web server đã bind để quyết định có thể nhận request. Chỉ kiểm tra rồi bỏ DTO không có nghĩa consumer đã sẵn sàng: trong ứng dụng thực, cần **cài snapshot vào payment client** và xác minh nó có thể dùng được.

### 7.2. Đọc theo nhu cầu nếu secret chỉ dùng ở một tính năng

~~~java
public final class PaymentGatewayFacade {

    private final PaymentSettingsReader reader;
    private final PaymentProviderClient provider;

    public PaymentGatewayFacade(
            PaymentSettingsReader reader,
            PaymentProviderClient provider) {
        this.reader = reader;
        this.provider = provider;
    }

    public Receipt charge(ApprovedPayment payment) {
        // Các bước authenticate/authorize nghiệp vụ diễn ra trước đây.
        PaymentSettings settings = reader.loadFresh();

        // Chuyển apiKey nội bộ, không đưa vào URL/log của request.
        return provider.charge(
                settings.apiKey(), settings.region(), payment);
    }

    // Interface thuộc ứng dụng, không phải API Spring Vault.
    public interface PaymentProviderClient {
        Receipt charge(String apiKey, String region, ApprovedPayment data);
    }
    public record ApprovedPayment(String orderId) {}
    public record Receipt(String receiptId) {}
}
~~~

Với on-demand, request đầu tiên chịu latency Vault và lỗi Vault xuất hiện trên đường nghiệp vụ. Nếu tần suất thanh toán cao, đọc KV mỗi request gây tải không cần thiết; có thể cache snapshot **có TTL và invalidation** theo policy. Nhưng API key bị rotate/revoke ở hệ thống ngoài có thể không còn hợp lệ, nên đừng dùng stale-if-error vô hạn.

### 7.3. Chu kỳ đọc và cơ chế refresh

| Chiến lược | Điểm mạnh | Điểm cần kiểm soát |
| --- | --- | --- |
| Startup snapshot | Phát hiện thiếu secret sớm, request nhanh | Cần refresh nếu secret đổi |
| On-demand mỗi lần | Luôn hỏi Vault ở mỗi lần sử dụng | Latency, quota, rủi ro khi Vault tạm down |
| On-demand + cache TTL | Giảm số call, cân bằng latency | Dữ liệu cũ trong TTL, invalidate và single-flight |
| Startup + scheduled refresh | Sẵn sàng ban đầu, chủ động cập nhật | Cần atomic swap và xử lý reload lỗi |

**Đừng nhầm KV version với expiration.** KV v2 có lịch sử phiên bản, còn tính hợp lệ của API key do hệ thống thanh toán quyết định. Đối với dynamic credentials `database/creds/...` có `lease_id`/`lease_duration`, Spring Vault `SecretLeaseContainer` phù hợp hơn một cache TTL thuần túy. Đối với Transit, ứng dụng phải gọi Vault để encrypt/decrypt thay vì tải raw encryption key từ KV về. Với PKI, cần quản lý `notAfter` và cập nhật TLS identity đúng quy trình.

## 8. Xử lý lỗi không làm lộ secret

Một bài lab đọc thành công cần được mở rộng để bao phủ lỗi thật:

| Hiện tượng | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| `read(...)` trả null hoặc path không tồn tại | Sai path, key chưa được tạo, version soft-deleted | Kiểm tra mount/key/version bằng kênh admin; không tạo key rỗng mặc định |
| HTTP `403` | Workload token thiếu quyền `read` ở `secret/data/orders/payment` | Sửa policy/auth của role; không dùng root token để tránh lỗi |
| HTTP `404` | Sai KV mount/version/path hoặc dữ liệu không tồn tại | Xem `vault secrets list` và KV version; không retry vô hạn |
| `data` bên trong không phải Map | Code đọc nhầm KV v1/v2 hoặc response schema sai | Fail closed; kiểm tra cấu trúc JSON, không dùng ép kiểu mù |
| Thiếu `apiKey`/`region` | Dữ liệu viết thiếu hoặc sai kiểu | Không chấp nhận cấu hình không hợp lệ |
| Vault sealed hoặc uninitialized | Health `503`/`501` ở endpoint hệ thống | Không tự unseal/initialize; chuyển tín hiệu tới vận hành |
| Network timeout / HA failover | DNS/TLS/LB/leader thay đổi | Retry **bounded** cho KV read; deadline, backoff/jitter |
| Token hết hạn | Workload authentication/session lifecycle | Renew/re-login đúng cơ chế; không dùng token cũ vô hạn |
| Secret được rotate nhưng app vẫn dùng bản cũ | Cache hoặc startup snapshot chưa refresh | Reload theo TTL/version/event, thay consumer atomically |

**Không log nguyên `VaultResponse` hoặc exception có thể chứa HTTP body/headers.** Thay vào đó ghi event dạng `operation=kv_read_payment`, `outcome=failure`, `failure_category=permission_denied`, `duration_ms=...` và correlation ID đã được kiểm soát. Không đưa API key vào message của `IllegalStateException`, HTTP response, metrics, tracing baggage hay ticket.

### 8.1. Retry phải xét idempotency

`GET` của KV v2 chỉ đọc giá trị, nên có thể retry có giới hạn khi lỗi transport hoặc 5xx tạm thời. Tuy nhiên **không phải mọi API Vault GET đều không có side effect**: endpoint đọc dynamic database credential có thể **phát hành một user/lease mới**. Không gắn retry interceptor chung lên mọi `VaultTemplate` API. PKI issue và AppRole SecretID issue cũng có thể phát hành bí mật mới nếu gọi lại sau timeout.

## 9. Kiểm thử tích hợp với Testcontainers Vault

Mục tiêu integration test là chạy **Vault thật ở dev/test mode**, ghi secret giả rồi đọc lại qua `VaultTemplate`. Không mock Vault response cho phép thử này vì mục tiêu là kiểm tra cả path `secret/data`, xác thực HTTP và lớp `data.data`.

### 9.1. Dependency kiểm thử

Ngoài `spring-boot-starter-test`, thêm **Testcontainers Vault module** và JUnit Jupiter integration (phiên bản theo Testcontainers BOM phù hợp với dự án):

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-vault</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
~~~

Đoạn snippet sử dụng tên artifact dành cho Testcontainers **2.x**; với Testcontainers 1.x, tọa độ module JUnit Jupiter có thể khác. Kiểm tra tài liệu dependency của phiên bản được chọn và khai báo BOM phù hợp để không trộn các version. Spring Boot Starter Test đã cung cấp JUnit Jupiter cho các ví dụ này.

### 9.2. Test đọc KV v2 thực

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.vault.VaultContainer;

@Testcontainers
class PaymentSettingsReaderIT {

    private static final String TEST_TOKEN = "test-only-root-token";

    @Container
    static final VaultContainer<?> VAULT =
            new VaultContainer<>("hashicorp/vault:1.20")
                    .withVaultToken(TEST_TOKEN)
                    .withInitCommand(
                            "kv put secret/orders/payment "
                            + "apiKey=TEST_ONLY_PAYMENT_KEY_A "
                            + "region=sandbox-eu");

    @Test
    void readsRequiredFieldsAndVersion() {
        URI address = URI.create(VAULT.getHttpHostAddress());
        VaultTemplate client = new VaultTemplate(
                VaultEndpoint.from(address),
                new TokenAuthentication(TEST_TOKEN));

        PaymentSettingsReader reader = new PaymentSettingsReader(client);
        PaymentSettings settings = reader.loadFresh();

        assertEquals("sandbox-eu", settings.region());
        assertTrue(settings.kvVersion() >= 1);
        assertEquals(
                "TEST_ONLY_PAYMENT_KEY_A", settings.apiKey());

        // DTO khi ghi dưới dạng text phải che API key.
        assertFalse(settings.toString().contains(settings.apiKey()));
    }
}
~~~

**Điều kiện:** Testcontainers cần Docker và module `testcontainers-vault`; container test của Vault dev mode dùng **HTTP** và token root **chỉ trong phạm vi test**. Vì class test tạo `VaultTemplate` thủ công, không cần Spring Boot context để xác minh API path/response; có thể mở rộng `@SpringBootTest` và `@DynamicPropertySource` để kiểm thử dependency injection nếu muốn.

Không đưa token root thử nghiệm vào cấu hình production, không chạy integration test với `VAULT_ADDR` production. Khi Testcontainers version hoặc Vault version đổi, hãy kiểm tra lại mount `secret/` có đúng KV v2 và init commands hoạt động; đừng vì test lỗi mà sửa Java parser bằng hardcode sai schema.

### 9.3. Test quyền truy cập và tình huống thất bại

Một integration test có chất lượng nên tách các trường hợp:

| Test | Cách dựng fixture | Assertion |
| --- | --- | --- |
| Thành công | KV v2 có `apiKey` và `region` | DTO trả đúng giá trị thử, version hợp lệ |
| Secret không tồn tại | Đọc `secret/data/orders/missing` | Reader báo thiếu dữ liệu, không tạo giá trị thay thế |
| Token thiếu quyền | Tạo test token policy không cho read path | Vault trả lỗi quyền phù hợp; không chuyển thành “không tìm thấy” |
| Sai schema | Ghi KV thiếu `apiKey` hoặc đổi kiểu field | Parser fail closed, không in map |
| Truy cập nhầm KV v1 path | Cố tình gọi `secret/orders/payment` với KV v2 | Không bóc được secret; test phơi bày lỗi path |
| Rotate secret | Viết version B rồi `loadFresh()` | Reader nhận version mới, không lấy lại bản cũ do cache |
| Token hết hạn/revoke | Revoke test token hoặc TTL ngắn | Lần đọc mới lỗi; auth/session xử lý theo thiết kế |
| Không được ghi | Token chỉ có `read`, thử `put` | Vault từ chối (negative ACL test) |
| TLS/timeout | Dùng endpoint test khác hoặc giả lập network fault | Phân loại lỗi transport riêng, không log secret |
| Đồng thời | N request cùng reader `VaultTemplate` | Đọc đúng; không có trạng thái mutable per-request bị trộn |
| Không lộ secret | Log appender/capture HTTP response của ứng dụng | Không thấy sentinel `TEST_ONLY_PAYMENT_KEY_A` |

**Lưu ý về cách xây fixture:** Test đọc có thể dùng root token **chỉ để khởi tạo container**, nhưng negative ACL test phải dùng **token bị giới hạn thực sự**. Test với root token không thể chứng minh least privilege. Nên tạo test token riêng, không trộn với token seed fixture.

### 9.4. Bài tập rotation đơn giản

Trong lab CLI với token admin test:

~~~bash
vault kv put -mount=secret orders/payment \
  apiKey="TEST_ONLY_PAYMENT_KEY_B" \
  region="sandbox-ap"

# Xem version, không in API key:
vault kv metadata get -mount=secret orders/payment
~~~

Chạy `reader.loadFresh()` lại phải thấy `region=sandbox-ap` và `kvVersion` tăng. Giá trị API key mới vẫn **không được log**; trong bài test chỉ assert đúng trên dữ liệu giả. Với ứng dụng có cache, phải đợi TTL/invalidate hoặc kích hoạt refresh có kiểm soát: `VaultTemplate` không tự “push” secret mới vào biến đã đọc lần trước.

## 10. Phân quyền và xử lý dữ liệu đúng vòng đời

### 10.1. Phân tách vai trò

| Thành phần | Quyền Vault | Nhiệm vụ |
| --- | --- | --- |
| Config administrator / CI pipeline tin cậy | Có quyền tạo/cập nhật KV tại path cụ thể | Provision và rotate API key |
| `orders-api` workload | Chỉ `read` path `secret/data/orders/payment` | Lấy cấu hình khi hoạt động |
| Monitoring | Health/metrics ở phạm vi được phê duyệt | Quan sát lỗi, latency và version |
| Vault administrator | Quản lý auth mounts/policies/seal/audit | Vận hành nền tảng, không phải business code |

Production nên xác thực ứng dụng bằng workload identity, đặt Vault policy theo service và môi trường. Không dùng root token, không đặt AppRole SecretID hoặc Vault token vào Git, Dockerfile, log, ticket. Nếu một workload phục vụ nhiều tenant, phải thêm isolation ở **authorization của ứng dụng** và/hoặc Vault identity/policy; không cho request bên ngoài chọn raw Vault path.

### 10.2. Cache, TTL và khả năng phục hồi

- **KV version** phản ánh lịch sử cấu hình; không phải credential TTL.
- **Cache TTL** là quyết định ứng dụng chấp nhận dữ liệu cũ bao lâu, không phải TTL do Vault áp cho KV.
- **Vault token TTL** quyết định client còn được Vault cho phép đọc hay không; sử dụng session manager/reauth theo workload.
- **Lease TTL** của dynamic secret cần renew/rotate, không được kéo dài chỉ bằng cache KV.
- **PKI `notAfter`** quyết định hiệu lực chứng thư; cần cấp/nạp mới trước hạn.
- **Transit** thực hiện phép toán trong Vault; nếu Vault sealed hoặc mất mạng thì không có phép encrypt/decrypt mới, dù KV cache đang hợp lệ.

Chọn chiến lược **startup fail-fast** nếu API key là điều kiện bắt buộc để phục vụ mọi request. Chọn **on-demand** nếu chỉ tính năng phụ cần secret. Với KV được dùng thường xuyên, có thể dùng cache TTL ngắn và single-flight để giảm số lần đọc; chính sách **stale-if-error** phải giới hạn thời gian và cân nhắc revocation.

### 10.3. Readiness, lỗi và audit

Readiness của `orders-api` nên phản ánh liệu consumer thanh toán đã có cấu hình hợp lệ hay chưa; liveness không nên restart JVM liên tục khi Vault tạm mất kết nối. Khi `vaultTemplate.read` thất bại, ghi loại thao tác và lỗi an toàn, không ghi raw `VaultResponse`. Vault audit log của hệ thống có thể được dùng để truy nguyên request với quyền truy cập phù hợp, nhưng không thay thế kiểm tra logs ứng dụng.

## 11. Các lỗi thường gặp và cách xác minh

### 11.1. “Đã put nhưng Java đọc null”

Đi lần lượt qua checklist:

1. Mount `secret/` đang dùng **KV v2**, không phải KV v1?
2. Lệnh CLI `vault kv put -mount=secret orders/payment` đã chạy thành công?
3. Java dùng `secret/data/orders/payment`, không thiếu `data/`?
4. Java đang trỏ đúng Vault URL/namespace và đúng môi trường?
5. Token của Java có `read` trên **path API** `secret/data/orders/payment`?
6. Code đọc `response.getData().get("data")` trước khi tìm `apiKey`?
7. Secret có bị soft delete, destroy hoặc version cụ thể không tồn tại?

Không in API key để trả lời các câu hỏi trên. Metadata, HTTP status và fixture test giả thường đủ để phân biệt.

### 11.2. “CLI đọc được, Java nhận 403”

CLI có thể đang dùng token admin `VAULT_TOKEN`, còn Java dùng `APP_VAULT_DEV_TOKEN` policy hẹp. Phải kiểm tra token **của chính workload**, không lấy kết quả admin làm bằng chứng Java cũng có quyền. Đối chiếu `vault token capabilities` và mount path; tránh cấp thêm `secret/*` chỉ để “chạy cho được”.

### 11.3. “Java báo ClassCastException”

Khả năng lớn là code ép `Map<String,String>` trực tiếp từ `VaultResponse.getData()` mà quên lớp bao của KV v2, hoặc giá trị được lưu dưới dạng khác String. Dùng `instanceof Map<?, ?>` và kiểm tra từng field như reader. Không chuyển object sang String một cách im lặng nếu schema yêu cầu String.

### 11.4. “Đã rotate nhưng ứng dụng vẫn gọi bằng key cũ”

`vaultTemplate.read` luôn gửi một read mới khi được gọi. Nhưng nếu bạn chỉ đọc ở startup rồi lưu vào singleton/connection pool, đối tượng đó **không tự cập nhật**. Thêm refresh có kiểm soát, cập nhật consumer atomically và ngừng dùng key cũ trước khi nhà cung cấp vô hiệu nó.

### 11.5. “Đã thêm log debug để tìm lỗi, lại xuất hiện secret trong log”

Tắt ghi HTTP body/wire log, `VaultResponse.toString()`, Map, exception raw và tracing payload. Chỉ dùng metric và enum lỗi. Khi secret thật đã bị lộ, phải điều tra phạm vi bản sao và rotate/revoke theo runbook, không chỉ xóa một dòng log.

## 12. Bài tập mở rộng tự kiểm tra

1. **Schema:** Đổi `region` thành thiếu hoặc String rỗng. Reader phải từ chối payload.
2. **Path:** Cố ý bỏ `data/` trong `VAULT_PATH`; xác minh test phát hiện lỗi và sửa lại.
3. **Policy:** Thử token chỉ cho `read`; bảo đảm Java không có đường ghi KV. Thêm negative test `403` trên path khác.
4. **Rotation:** Ghi hai version A/B; `loadFresh()` nhận B và version tăng, không log A/B.
5. **Concurrency:** Tạo 32–50 request đọc cùng `VaultTemplate`, dùng `ExecutorService` và deadline; không tạo một client mới cho mỗi thread.
6. **Startup vs on-demand:** Thử thiếu secret trước startup và khi gọi tính năng tùy chọn; chọn readiness policy phù hợp.
7. **Log sentinel:** Kiểm tra `TEST_ONLY_PAYMENT_KEY_A` không xuất hiện trong stdout, trace, API error và exception message.
8. **Lỗi Vault:** Dùng Vault test, mô phỏng timeout/sealed; ứng dụng không tự gọi initialize/unseal và không retry vô hạn.
9. **KV v2 versioned API:** Chuyển sang `vaultTemplate.opsForVersionedKeyValue("secret")` để đọc version cụ thể rồi so cách model dữ liệu khác với `vaultTemplate.read(...)`.
10. **Workload auth:** Thay local `TokenAuthentication` bằng AppRole/Kubernetes auth trong môi trường test, đối chiếu token TTL và phân quyền.

## 13. Checklist hoàn thành lab

- [ ] Có Vault dev/test cô lập; token root chỉ dùng để tạo fixture, không đi vào Java production.
- [ ] Mount `secret/` là KV v2, key `orders/payment` có hai field `apiKey`/`region` giả.
- [ ] Workload token chỉ có `read` tại `secret/data/orders/payment`.
- [ ] `VaultTemplate` được cấu hình một lần với `VaultEndpoint` và `ClientAuthentication` phù hợp.
- [ ] Reader gọi đúng `vaultTemplate.read("secret/data/orders/payment")`.
- [ ] Parser lấy `response.getData().get("data")` và kiểm tra kiểu/giá trị từng field.
- [ ] Đọc được `metadata.version`, không nhầm version với lease TTL.
- [ ] DTO chứa API key không được log/serialize ra API; lỗi không mang raw Vault response.
- [ ] 403, missing path, schema sai, token hết hạn và Vault unavailable có phản ứng rõ.
- [ ] Đã xác định startup/on-demand/cache TTL và quy tắc refresh/rotation.
- [ ] Integration test Testcontainers dùng token/secret giả, không phụ thuộc Vault production.
- [ ] Negative test chứng minh least privilege; test rotation kiểm tra version mới.
- [ ] Giám sát chỉ đo status/category/latency và giữ secret ra ngoài logs/metrics/traces.
- [ ] Nếu triển khai thật, TLS/CA/workload auth/policy và vòng đời token đã được nhóm platform phê duyệt.

## 14. Tài liệu tham khảo

- Spring Vault, [Vault Secrets Engines — KV v1/v2](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html) — so sánh `VaultTemplate.read`, `opsForKeyValue` và `opsForVersionedKeyValue`.
- Spring Vault, [VaultTemplate Java API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTemplate.html), [VaultOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultOperations.html) — Java client và đối tượng `VaultResponse`.
- Spring Vault, [Authentication methods](https://docs.spring.io/spring-vault/reference/vault/authentication.html) — xác thực workload, token và session manager.
- HashiCorp Vault, [KV v2 API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2) — `GET secret/data/...`, `data.data`, `data.metadata` và version.
- HashiCorp Vault, [KV secrets engine](https://developer.hashicorp.com/vault/docs/secrets/kv) — phân biệt path CLI với HTTP và KV v1/v2.
- HashiCorp Vault, [Vault policies](https://developer.hashicorp.com/vault/docs/concepts/policies) — least-privilege capabilities theo path.
- HashiCorp Vault, [`vault kv` CLI](https://developer.hashicorp.com/vault/docs/commands/kv) — lệnh `-mount`, phiên bản và metadata.
- Testcontainers for Java, [HashiCorp Vault Module](https://java.testcontainers.org/modules/vault/) — `VaultContainer` và `withInitCommand`.
- Spring Vault, [SecretLeaseContainer API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretLeaseContainer.html) — đối chiếu dynamic secrets có lease với KV tĩnh.
