# Yêu cầu wrap theo từng lần gọi API

## 1. Vì sao cần yêu cầu wrap cho từng request?

Trong **Spring Vault**, ứng dụng Java sử dụng `VaultTemplate` / `VaultOperations` để truy cập HashiCorp Vault bằng danh tính workload và Vault policy. Một số API trả về thông tin đặc biệt nhạy cảm như AppRole `secret_id`, token đăng nhập, chứng thư kèm khóa riêng hoặc dữ liệu KV. Nếu bên cấp phát phải chuyển kết quả đó sang tiến trình khác, việc đưa nguyên bí mật vào message, biến môi trường, log hoặc công cụ triển khai làm tăng khả năng rò rỉ.

**Response wrapping** giải quyết bước **bàn giao kết quả của một API call**: thay vì trả ngay nội dung, Vault đặt phản hồi thật vào vùng `cubbyhole` gắn với một **wrapping token** chỉ dùng một lần, rồi trả về metadata/token đó cho bên yêu cầu. Bên nhận kiểm tra nguồn gốc và unwrap khi cần.

Điểm cốt lõi của bài học **“Yêu cầu wrap theo từng lần gọi API”** là: client yêu cầu wrapping **ngay trên HTTP request cụ thể**, bằng header `X-Vault-Wrap-TTL`. Điều này cho phép cùng một `VaultTemplate` thực hiện một request bình thường và một request có wrapping mà không thay đổi cấu hình chung của các request còn lại.

Ví dụ xuyên suốt: hệ thống điều phối cấp `secret_id` của AppRole `orders` cho một dịch vụ mới. Hệ thống điều phối được Vault cho phép sinh SecretID, nhưng nó chỉ nhận **wrapping token** để chuyển tới workload. Workload là bên cuối cùng unwrap và dùng SecretID để đăng nhập Vault.

Sau bài này, người học có thể:

- Giải thích cơ chế `X-Vault-Wrap-TTL`, `wrap_info` và cubbyhole của wrapping token.
- Gửi request có wrapping bằng Vault CLI, HTTP API và Spring Vault.
- Dùng `VaultWrappingOperations.lookup/read` để kiểm tra nguồn và unwrap **một lần**.
- Phân biệt wrapping per-request với `sys/wrapping/wrap` và cơ chế lưu KV/cubbyhole thông thường.
- Cấu hình policy yêu cầu wrapping, xử lý TTL, lỗi token đã dùng và kiểm thử tích hợp.

> **Phạm vi:** Một request chỉ có thể trả wrapping token nếu Vault chấp nhận wrapping và caller vẫn có quyền thực hiện **API gốc**. Wrapping không cấp thêm quyền tạo/đọc secret và không thay thế xác thực workload, TLS, Vault ACL hay chính sách cấp phát bí mật.

## 2. Hiểu đúng luồng wrapping và cubbyhole

~~~mermaid
sequenceDiagram
    participant Issuer as Provisioner (Spring Vault)
    participant Vault as HashiCorp Vault
    participant Receiver as Orders workload
    Issuer->>Vault: POST /auth/approle/role/orders/secret-id
    Note over Issuer,Vault: X-Vault-Wrap-TTL: 90s
    Vault->>Vault: Tạo SecretID; lưu response vào cubbyhole của wrapping token
    Vault-->>Issuer: wrap_info { token, ttl, creation_path, ... }
    Issuer-->>Receiver: Chuyển wrapping token qua kênh được bảo vệ
    Receiver->>Vault: POST /sys/wrapping/lookup
    Vault-->>Receiver: creation_path, creation_time, creation_ttl
    Receiver->>Receiver: Kiểm tra đúng API nguồn, token chưa hết hạn
    Receiver->>Vault: POST /sys/wrapping/unwrap
    Vault-->>Receiver: Phản hồi gốc chứa SecretID
    Receiver->>Vault: Đăng nhập AppRole bằng RoleID + SecretID
    Vault-->>Receiver: Vault session token theo policy
~~~

**Quy trình tại Vault:**

1. Vault nhận yêu cầu API bình thường và header `X-Vault-Wrap-TTL` có thời lượng dương.
2. Vault thực thi request theo quyền của token caller và tạo phản hồi gốc.
3. Vault tạo **wrapping token** có TTL tương ứng, lưu phản hồi gốc vào cubbyhole liên kết với token.
4. Response mà caller nhận có `wrap_info`, trong đó `token` là **bearer token** cho quyền lấy phản hồi đã gói.
5. Bên nhận có thể lookup metadata mà không xem bí mật, sau đó unwrap **đúng một lần**; unwrap thành công sẽ tiêu thụ wrapping token.

Cubbyhole là secrets engine gắn với danh tính token. Trong response wrapping, Vault sử dụng cubbyhole **nội bộ** để cất phản hồi. Client không cần thao tác trực tiếp `cubbyhole/response`. Hãy dùng các endpoint `sys/wrapping/lookup` và `sys/wrapping/unwrap`: chúng có kiểm tra token và cơ chế audit phù hợp.

**Wrapping token không phải token phiên làm việc dài hạn:** nó chủ yếu có thể lookup/unwrap/rewrap kết quả tương ứng, không mang các policy tùy ý cho ứng dụng đọc các secrets khác. Dẫu vậy, ai có wrapping token còn hiệu lực đều có thể thử unwrap, nên bản thân token vẫn là **bí mật phải bảo vệ**.

## 3. Header `X-Vault-Wrap-TTL`: quyết định theo từng request

### 3.1. Cú pháp và ý nghĩa

HTTP header:

~~~http
X-Vault-Wrap-TTL: 90s
~~~

Vault chấp nhận số giây hoặc duration như `15s`, `2m`, `1h`. Giá trị biểu thị **thời gian sống của wrapping token**, chứ **không phải** thời gian sống của SecretID, Vault token gốc, KV secret, PKI certificate hoặc lease liên quan.

| Request | Có header? | Kết quả kỳ vọng |
| --- | --- | --- |
| `POST /v1/auth/approle/role/orders/secret-id` | `X-Vault-Wrap-TTL: 90s` | `wrap_info` chứa wrapping token, dữ liệu SecretID chưa xuất hiện trong response caller |
| Cùng endpoint, một request sau | Không | Response bình thường chứa `data.secret_id` nếu policy không bắt buộc wrapping |
| `GET /v1/secret/data/orders/config` | `X-Vault-Wrap-TTL: 2m` | Response KV v2 được wrap, khi unwrap mới thấy `data.data` |
| `POST /v1/sys/wrapping/unwrap` | Không đặt wrapping header | Bên nhận lấy phản hồi gốc; tránh tạo wrapping lồng nhau ngoài ý muốn |

**Mỗi request cần tự khai báo TTL.** Không mặc định mọi lệnh `read`, `write` của `VaultOperations` đều wrapped. Đặc biệt, đừng thêm `X-Vault-Wrap-TTL` vào interceptor chung của HTTP client: nó có thể bao phủ nhầm request đăng nhập, kiểm tra trạng thái, renew token hoặc chính các call unwrap.

### 3.2. TTL nên chọn như thế nào?

TTL phải đủ cho thời gian điều phối, truyền token, startup và độ trễ mạng, nhưng đủ ngắn để giảm thời gian kẻ khác có thể sử dụng token bị lộ.

| Tình huống | TTL minh họa | Điều cần cân nhắc |
| --- | --- | --- |
| Provisioner và workload chạy cùng cluster, truyền ngay | 60–120 giây | Độ trễ hàng đợi và lịch khởi động |
| Cấp phát qua job orchestration có độ trễ dự đoán được | Vài phút | Backoff, clock skew, retry có giới hạn |
| Chuyển giao giữa hệ thống không có SLA rõ ràng | Không mặc định tăng TTL | Cải thiện quy trình bàn giao và giám sát |

Các khoảng trên chỉ là **ví dụ vận hành**, không phải giá trị bắt buộc. Vault policy có thể đặt mức `min_wrapping_ttl` và `max_wrapping_ttl`; khi vượt giới hạn, API bị từ chối. Nếu response đã wrap mà token hết hạn trước lúc unwrap, bên nhận không thể lấy lại phản hồi bằng token đó. Tùy tác vụ, phải tạo request/secret mới theo quy trình có kiểm soát.

## 4. Gửi một HTTP request yêu cầu response wrapping

Giả sử AppRole auth được mount tại `auth/approle/`, role `orders` đã tồn tại, caller có policy cho phép tạo SecretID và kết nối Vault qua HTTPS đáng tin cậy.

~~~http
POST /v1/auth/approle/role/orders/secret-id HTTP/1.1
Host: vault.internal.example
X-Vault-Token: <session-token-cua-provisioner>
X-Vault-Wrap-TTL: 90s
Content-Type: application/json

{}
~~~

Response minh họa (giá trị đã thay bằng placeholder, **không phải token thật**):

~~~json
{
  "request_id": "<id>",
  "lease_id": "",
  "renewable": false,
  "lease_duration": 0,
  "data": null,
  "wrap_info": {
    "token": "<wrapping-token-secret>",
    "accessor": "<wrapping-accessor>",
    "ttl": 90,
    "creation_time": "2026-11-25T08:00:00Z",
    "creation_path": "auth/approle/role/orders/secret-id"
  },
  "warnings": null
}
~~~

Các thuộc tính metadata có thể khác nhau theo phiên bản Vault và loại response; không dựa vào vị trí/số lượng trường ngoài những gì code đã kiểm tra. Trên đường trả trực tiếp không wrap, response sẽ chứa `data.secret_id` và `data.secret_id_accessor` của AppRole.

**Lưu ý quyền:** Vault xác minh token của provisioner khi xử lý endpoint `auth/approle/.../secret-id`. Wrapping chỉ thay đổi **hình thức giao kết quả**; việc cấp SecretID vẫn có thể tạo trạng thái mới trong Vault. Nếu mất response hoặc retry mù, rất có thể đã phát hành nhiều SecretID khác nhau.

### 4.1. Đọc các trường của `wrap_info`

| Trường | Ý nghĩa | Sử dụng |
| --- | --- | --- |
| `token` | Wrapping token để lookup/unwrap | Chuyển đến đúng bên nhận, không đưa vào log |
| `ttl` | TTL token tính bằng giây tại thời điểm cấp | Kiểm tra có đủ thời gian giao nhận |
| `creation_time` | Thời điểm tạo wrapping token | Tính tuổi của token, phát hiện giao nhận quá chậm |
| `creation_path` | Đường dẫn Vault đã tạo phản hồi được wrap | Kiểm tra **chính xác** API nguồn mong đợi trước khi unwrap |
| `accessor` / `wrapped_accessor` nếu có | Metadata phục vụ quản trị, đặc biệt với phản hồi token | Không nhầm accessor với wrapping token hoặc secret thật |

`data: null` là dấu hiệu hữu ích trong ví dụ này, nhưng bằng chứng quan trọng nhất là **`wrap_info.token` tồn tại hợp lệ**. Nếu ứng dụng yêu cầu wrap mà response chỉ chứa secret thô, phải coi đó là lỗi quy trình và không chuyển raw secret qua tuyến bàn giao dành cho wrapping token.

## 5. Thực hành CLI: chỉ wrap một lệnh

Vault CLI hỗ trợ `-wrap-ttl` tương ứng với header `X-Vault-Wrap-TTL`. Dùng flag **trên đúng lệnh cấp phát**:

~~~bash
# Môi trường dev/test đã bật AppRole và tạo role orders.
# Lệnh này tạo một SecretID mới và chỉ trả wrapping token.
vault write -f -wrap-ttl=90s -format=json \
  auth/approle/role/orders/secret-id
~~~

Kết quả thường có `wrap_info.token` cùng `creation_path`. Trong môi trường thật, provisioner chuyển token này qua kênh đã xác thực đến workload đích. Để xem token còn nguyên và đúng nguồn, workload có thể gọi API lookup. Minh họa bằng shell test:

~~~bash
# WRAPPED_TOKEN là token mẫu lấy từ một kênh bí mật trong môi trường test.
# Không gõ token thật trực tiếp vào lịch sử shell.
vault write -format=json sys/wrapping/lookup \
  token="$WRAPPED_TOKEN" \
  | jq '.data | {creation_path, creation_time, creation_ttl}'

# Chỉ thực hiện sau khi đã so creation_path với giá trị kỳ vọng.
# Lệnh này sẽ in secret ra stdout: CHỈ dùng với dữ liệu giả trong test.
vault unwrap "$WRAPPED_TOKEN"
~~~

Sau unwrap thành công, gọi lại `vault unwrap` với token cũ sẽ thất bại. Lệnh `vault unwrap` in dữ liệu gốc và có thể lộ secret vào stdout; trong production hãy xử lý trong ứng dụng, giới hạn log và lifetime của dữ liệu trong bộ nhớ.

**Không dùng biến môi trường `VAULT_WRAP_TTL` làm mặc định toàn bộ tiến trình CLI** khi mục tiêu là wrap một request cụ thể: cài đặt toàn cục có thể vô tình khiến các lệnh tiếp theo cũng yêu cầu wrapping. Chỉ set `-wrap-ttl` trên lệnh cần thiết.

Một thử nghiệm đối chứng: gọi lại endpoint với cùng role **không có `-wrap-ttl`** trong môi trường test. Nếu policy không ép wrapping, response chứa SecretID bình thường. Nếu policy đã buộc wrap, thao tác không đặt TTL phải bị từ chối.

## 6. Spring Vault: gắn header vào đúng API call

### 6.1. Vì sao dùng `doWithSession(...)`?

API đơn giản của Spring Vault như `vaultOperations.write(path, body)` phục vụ nhiều request thông thường nhưng không có tham số `wrapTtl` cho từng lời gọi. Spring Vault cung cấp callback `VaultOperations.doWithSession(...)` để thao tác bằng `RestOperations` **trong phiên Vault đã xác thực**, cho phép dựng `HttpEntity` với header riêng của request.

`VaultWrappingOperations` trong Spring Vault quản lý **lookup, read/unwrap, rewrap** và `wrap(Object, Duration)` qua endpoint hệ thống. Hàm `opsForWrapping().wrap(...)` gói dữ liệu **client gửi lên endpoint `sys/wrapping/wrap`**; nó không tự bật wrapping cho một lần gọi `pki/issue`, `transit/encrypt`, `kv get` hoặc `auth/approle/.../secret-id` vốn đã có response riêng.

### 6.2. Java: provisioner chỉ nhận wrapping token

Ví dụ này dùng Java 17+, Spring Vault có `VaultOperations.doWithSession` và Spring Web `RestOperations`. JSON được ánh xạ bằng Jackson, có thể đã có sẵn trong Spring Boot. Workload authentication/TLS/Vault endpoint được cấu hình từ trước; AppRole role `orders` đã được tạo với policy tương ứng.

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Duration;
import java.util.Map;
import java.util.Objects;

import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.vault.core.VaultOperations;

public final class WrappedSecretIdIssuer {

    private static final String ISSUE_PATH =
            "auth/approle/role/orders/secret-id";
    private static final String WRAP_TTL = "90s";

    private final VaultOperations vaultOperations;

    public WrappedSecretIdIssuer(VaultOperations vaultOperations) {
        this.vaultOperations = Objects.requireNonNull(vaultOperations);
    }

    public WrappedDelivery issueForOrders() {
        // Headers thuộc một HttpEntity của đúng request này.
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("X-Vault-Wrap-TTL", WRAP_TTL);

        HttpEntity<Map<String, Object>> entity =
                new HttpEntity<>(Map.of(), headers);

        return vaultOperations.doWithSession(rest -> {
            ResponseEntity<JsonNode> response = rest.exchange(
                    ISSUE_PATH,
                    HttpMethod.POST,
                    entity,
                    JsonNode.class
            );

            JsonNode body = Objects.requireNonNull(
                    response.getBody(), "Vault response is null");
            JsonNode wrap = body.path("wrap_info");

            String token = wrap.path("token").asText("");
            String path = wrap.path("creation_path").asText("");
            long ttlSeconds = wrap.path("ttl").asLong(0L);

            if (token.isBlank()) {
                throw new IllegalStateException(
                        "Expected response wrapping but no token returned");
            }
            if (!ISSUE_PATH.equals(path)) {
                throw new IllegalStateException(
                        "Unexpected wrapping creation_path");
            }
            if (ttlSeconds <= 0 || ttlSeconds > 90) {
                throw new IllegalStateException(
                        "Unexpected wrapping TTL");
            }

            return new WrappedDelivery(
                    token, path, Duration.ofSeconds(ttlSeconds));
        });
    }

    // Chỉ chuyển record này qua kênh bảo mật được cấp phép.
    // Không cho record tự tạo toString() trong application logs.
    public record WrappedDelivery(
            String token,
            String creationPath,
            Duration ttl) {
        @Override
        public String toString() {
            return "WrappedDelivery[redacted]";
        }
    }
}
~~~

**Điểm cần quan sát:**

- `headers.set("X-Vault-Wrap-TTL", "90s")` chỉ nằm trong `HttpEntity` của lệnh phát hành SecretID.
- `doWithSession` dùng context xác thực mà Spring Vault quản lý; không gắn root token vào source code.
- Kết quả được xác minh có token và `creation_path` đúng như yêu cầu; không tự lấy `data.secret_id` từ response.
- `token` vẫn là một `String` chứa bí mật trong heap; việc giảm thời gian sống, kiểm soát log/trace và bảo vệ kênh giao vẫn cần thiết.
- Đối tượng nhận dữ liệu được đặt tên `WrappedDelivery` để tránh nhầm với SecretID hay Vault session token.

Code minh họa dạng imperative. Với Spring Vault 4.x, các abstraction HTTP client mới có thể hỗ trợ API request wrapping trực tiếp; `doWithSession` vẫn là lựa chọn ổn định khi muốn sử dụng `RestOperations` tương thích phiên bản được nêu. Nếu dùng Vault namespace khác mặc định, cấu hình namespace và endpoint thông qua client/session chính thức, không tự ý ghép URL từ input không tin cậy.

### 6.3. Java: bên nhận kiểm tra rồi unwrap

Spring Vault cung cấp `VaultWrappingOperations` qua `vaultOperations.opsForWrapping()`:

~~~java
import java.util.Map;
import java.util.Objects;

import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultWrappingOperations;
import org.springframework.vault.support.VaultResponse;
import org.springframework.vault.support.VaultToken;
import org.springframework.vault.support.WrappedMetadata;

public final class WrappedSecretIdConsumer {

    private static final String EXPECTED_PATH =
            "auth/approle/role/orders/secret-id";

    private final VaultWrappingOperations wrapping;

    public WrappedSecretIdConsumer(VaultOperations vaultOperations) {
        this.wrapping = vaultOperations.opsForWrapping();
    }

    public String unwrapOrdersSecretId(String tokenValue) {
        if (tokenValue == null || tokenValue.isBlank()) {
            throw new IllegalArgumentException("Missing wrapping token");
        }

        VaultToken wrappingToken = VaultToken.of(tokenValue);

        // Lookup không tiết lộ SecretID và không tiêu thụ token.
        WrappedMetadata metadata = wrapping.lookup(wrappingToken);
        if (metadata == null) {
            throw new IllegalStateException(
                    "Invalid, expired or already used wrapping token");
        }
        if (!EXPECTED_PATH.equals(metadata.getPath())) {
            throw new IllegalStateException(
                    "Unexpected source of wrapped secret");
        }

        // read() unwrap một lần, token không dùng được nữa.
        VaultResponse unwrapped = wrapping.read(wrappingToken);
        if (unwrapped == null || unwrapped.getData() == null) {
            throw new IllegalStateException("Unwrap returned no data");
        }

        Map<String, Object> data = unwrapped.getData();
        Object secretId = data.get("secret_id");

        if (!(secretId instanceof String id) || id.isBlank()) {
            throw new IllegalStateException(
                    "Wrapped response has no AppRole SecretID");
        }

        return id; // Chỉ bàn giao cho bộ phận AppRole login nội bộ.
    }
}
~~~

Lưu ý: ví dụ `read` này phù hợp với phản hồi `data` của API cấp SecretID. Nếu wrapper bao một **authentication response**, payload gốc có thể nằm trong trường `auth`; cần deserialize theo định dạng response thực. Tốt nhất là client nhận biết trước endpoint nguồn và schema phù hợp, không cố đoán kiểu dữ liệu bằng chuỗi JSON.

Việc kiểm tra `creation_path` **phải thực hiện trước** khi unwrap. Nếu chỉ kiểm tra tiền tố rộng như `auth/approle/`, token từ role khác cũng có thể được chấp nhận. Với KV v2, phân biệt chính xác `secret/data/...`, `secret/metadata/...` và namespace/mount mà ứng dụng mong đợi.

### 6.4. Phân biệt ba thao tác Spring Vault

| Gọi | Nội dung | Nguồn chứng thực của response |
| --- | --- | --- |
| `doWithSession(... X-Vault-Wrap-TTL ...)` | Wrap **response của API nguồn** trên một request được chọn | `creation_path` là đường dẫn API gốc |
| `opsForWrapping().wrap(body, ttl)` | Gửi một body do client tạo tới `sys/wrapping/wrap` để Vault wrap | `creation_path` là `sys/wrapping/wrap`, không chứng minh dữ liệu ban đầu đến từ secret engine nào |
| `opsForWrapping().lookup(token)` / `read(token)` | Kiểm tra metadata / unwrap response đã wrap | Dùng để xác minh nguồn và lấy nội dung một lần |

**Hệ quả bảo mật:** Nếu bên nhận cần biết Vault thực sự đã cấp SecretID, nên yêu cầu token với `creation_path=auth/approle/role/orders/secret-id`. Một token mới từ `sys/wrapping/wrap` có thể chứa một chuỗi tùy ý do bên gửi tạo và không phải bằng chứng Vault đã sinh SecretID ở endpoint đó.

## 7. Ràng buộc wrapping bằng Vault policy

Nếu hệ thống yêu cầu mọi lần phát hành SecretID ở một path phải được wrap, có thể đặt chính sách dạng:

~~~hcl
path "auth/approle/role/orders/secret-id" {
  capabilities = ["create", "update"]

  min_wrapping_ttl = "1s"
  max_wrapping_ttl = "2m"
}
~~~

Policy do nhóm quản trị Vault áp dụng cho token của provisioner. `min_wrapping_ttl = "1s"` làm wrapping **bắt buộc** cho path này; `max_wrapping_ttl = "2m"` giới hạn thời gian sống token. Bài dùng request `90s` nên nằm trong khoảng cho phép.

Không tùy tiện tăng TTL trong client khi policy chặn request: cần xem lại độ trễ bàn giao thực tế, mục đích của cơ chế wrapping và quyết định bảo mật của nhóm vận hành. Cũng không nên cấp `sudo` hoặc quyền rộng đến `auth/approle/role/*` chỉ để tránh lỗi 403.

**Tách các quyền:**

- **Provisioner** có quyền tạo SecretID cho chính role `orders` và policy yêu cầu wrap. Nó chỉ chuyển wrapping token cho workload đích.
- **Workload** có quyền dùng wrapping token để lookup/unwrap nội dung gắn với token đó. Sau khi unwrap SecretID, workload thực hiện `auth/approle/login` theo AppRole và nhận token ứng dụng với ACL riêng.
- **Admin** quản lý AppRole, rotation, các mount, policy và audit. Không dùng admin/root token trong job cấp phát thường xuyên.

Một wrapping token được cấp ra từ một token có policy phù hợp không làm cho bên nhận có đầy đủ quyền của token provisioner.

## 8. Nhận, lookup, unwrap và rewrap an toàn

### 8.1. Checklist của bên nhận trước khi unwrap

1. Nhận wrapping token qua kênh được bảo vệ; biết trước **API nguồn chính xác** mà token phải đại diện.
2. Gọi `sys/wrapping/lookup` hoặc `VaultWrappingOperations.lookup` để kiểm tra token còn hiệu lực.
3. Đối chiếu `creation_path` với đúng API, mount, role, namespace mong đợi; kiểm tra thời điểm tạo và TTL theo quy tắc nghiệp vụ.
4. Chỉ sau khi kiểm tra đạt, gọi `sys/wrapping/unwrap` hoặc `VaultWrappingOperations.read`.
5. Deserialize response gốc theo schema của API và sử dụng secret trong thời gian ngắn nhất cần thiết.
6. Xóa/gỡ reference wrapping token khỏi cơ chế giao nhận; không retry unwrap bằng cùng token sau khi đã thành công.

Nếu lookup thất bại, token có thể đã hết hạn, đã bị unwrap, bị thu hồi hoặc chưa từng tồn tại. Đây **chưa tự động chứng minh** bị đánh cắp, nhưng cần cảnh báo và điều tra audit log tương ứng trong hệ thống nhạy cảm.

### 8.2. Hai cách gọi HTTP unwrap

Khi gọi API trực tiếp, Vault hỗ trợ hai dạng:

~~~http
POST /v1/sys/wrapping/unwrap HTTP/1.1
X-Vault-Token: <wrapping-token>

{}
~~~

Hoặc dùng một token khác có quyền phù hợp làm bearer để gửi wrapping token trong body:

~~~http
POST /v1/sys/wrapping/unwrap HTTP/1.1
X-Vault-Token: <authorized-session-token>
Content-Type: application/json

{"token": "<wrapping-token>"}
~~~

**Không đặt cùng wrapping token đồng thời ở `X-Vault-Token` và trường body `token`**: Vault có thể xem đây là sử dụng token hai lần, làm token bị thu hồi mà không lấy được dữ liệu. Bên nhận nên thống nhất **một** cách gọi theo SDK/client.

Sau unwrap, kết quả trả về là **response gốc ở định dạng wire format**; nội dung có thể là `data`, `auth` hoặc cấu trúc khác. Hãy xử lý tùy endpoint nguồn đã xác minh.

### 8.3. Lookup khác unwrap và rewrap

| Thao tác | Có trả bí mật bên trong? | Wrapping token cũ có tiếp tục sử dụng được? |
| --- | --- | --- |
| `lookup` | Không | Có, nếu chưa hết hạn và hợp lệ |
| `unwrap` / Spring Vault `read` | **Có** | Không, token đã được tiêu thụ sau lần unwrap thành công |
| `rewrap` | Không; chỉ trả metadata/token mới | **Không**; token cũ bị vô hiệu, token mới thay thế |

`rewrap` hữu ích khi cần thay wrapping token mà vẫn giữ dữ liệu bên trong, ví dụ cơ chế chuyển giao qua nhiều chặng. Nó không đồng nghĩa với KV versioning, rotation Transit key hay cấp lại SecretID; và không phải cách khôi phục dữ liệu đã unwrap hay token đã hết hạn. Token mới vẫn là bí mật, cần kiểm tra metadata/source và TTL.

## 9. Wrapping token TTL, secret TTL và lease là ba vòng đời khác nhau

| Vòng đời | Ví dụ | Điều gì hết hạn? |
| --- | --- | --- |
| **Wrapping TTL** | `X-Vault-Wrap-TTL: 90s` | Quyền unwrap phản hồi, hết hạn có thể mất khả năng lấy payload |
| **AppRole SecretID TTL** | Cấu hình `secret_id_ttl` theo role | Quyền dùng SecretID để login AppRole |
| **Vault token TTL** | Token được cấp sau AppRole login | Quyền thực thi API theo chính sách token |
| **Secret lease TTL** | Dynamic database credentials hoặc secret khác | Thời gian sử dụng của secret được cấp và quy tắc renew/revoke tương ứng |

Bí mật bên trong có thể **hết hạn trước** wrapping token hoặc token session được cấp sau khi unwrap có TTL hoàn toàn độc lập. Việc đặt `90s` **không đảm bảo** SecretID hay dynamic credential bên trong còn hợp lệ 90 giây kể từ lúc bên nhận unwrap. Client phải xử lý metadata của loại secret gốc theo chính sách riêng.

**Không gọi renew lease để kéo dài wrapping token**, và không coi rewrap là hành động renew hoặc gia hạn bí mật bên trong. Nếu nhu cầu là vận hành lâu dài sau khi đã nhận secret, hãy dùng session/token lifecycle, lease renewal và cấp lại secret đúng loại.

## 10. Các lỗi thường gặp khi yêu cầu wrap từng lần

| Dấu hiệu | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| Response có `data.secret_id` thay vì `wrap_info` | Chưa gửi `X-Vault-Wrap-TTL`, sai header, hoặc client đi đường API khác | Kiểm tra đúng request gửi đi và fail closed; không forward secret thô |
| `400`/`403` khi yêu cầu wrapping | TTL ngoài policy, token không có quyền trên path gốc, role/mount sai | Kiểm tra TTL, policy trên đúng path và auth workload |
| `wrap_info.token` rỗng/null | Wrapping không được thực hiện hoặc deserialize sai | Không tiếp tục bàn giao; kiểm tra HTTP/raw response một cách an toàn |
| Token lookup báo invalid/expired | Token hết hạn, đã dùng, bị revoke, sai namespace hoặc token truyền sai | Điều tra audit, đánh giá khả năng tạo request mới; không retry vô hạn |
| `creation_path` không khớp | Token trỏ đến API khác hoặc wrapper tạo từ `sys/wrapping/wrap` | Từ chối trước unwrap; kiểm tra nhà cấp phát và chuỗi bàn giao |
| Unwrap lần hai không thành công | Wrapping token chỉ dùng một lần | Xử lý response lần đầu an toàn; nếu mất phải dùng quy trình cấp lại |
| Unwrap mất secret dù HTTP đã thành công | Token bị tiêu thụ, client crash trước khi xử lý/persist an toàn | Thiết kế giao nhận idempotent ở nghiệp vụ, cấp mới khi cần |
| Spring Vault tự wrap cả request không liên quan | Header đặt trong interceptor chung hoặc `VAULT_WRAP_TTL` được set toàn cục cho CLI | Đưa header vào `HttpEntity` của request duy nhất |
| Bên nhận có secret nhưng AppRole login thất bại | SecretID TTL/num_uses đã hết, RoleID không đúng, IP bind/CIDR policy | Chẩn đoán AppRole riêng; wrapping thành công không chứng minh secret còn dùng được |

Ở môi trường production, logging chỉ nên ghi endpoint được allowlist, loại yêu cầu, thời điểm, latency, kết quả thành công/thất bại và mã lỗi đã làm sạch. **Không** log wrapping token, request/response gốc, SecretID, Vault session token hoặc dữ liệu bí mật sau unwrap. Đặc biệt tránh ghi `WrappedDelivery` bằng serializer/logging mặc định.

## 11. Kiểm thử tích hợp theo từng lần gọi

Chuẩn bị Vault test riêng với AppRole role `orders`, quyền tạo SecretID và một client Java xác thực bằng workload identity. Có thể dùng container Vault dev/test trong CI, nhưng cần bảo đảm policy và đường dẫn setup nhất quán.

| Trường hợp | Hành động test | Điều cần khẳng định |
| --- | --- | --- |
| Wrap một request | POST cấp SecretID có `X-Vault-Wrap-TTL: 90s` | Có `wrap_info.token`, `data` không trả SecretID |
| Request kế tiếp bình thường | Gọi cùng API không gắn header khi policy cho phép | Nhận response thông thường, không còn wrap |
| Header chỉ áp dụng một call | Dùng cùng instance `VaultOperations` gọi API khác sau request wrapped | Request sau không tự có wrapping header |
| Metadata của wrapping token | Gọi `lookup` trước unwrap | `creation_path` đúng và không lộ SecretID |
| Unwrap một lần | Gọi `read(token)` rồi gọi lại | Lần đầu có SecretID hợp lệ, lần hai bị từ chối/null |
| Sai nguồn | Đưa token từ `sys/wrapping/wrap` hoặc role khác | Consumer từ chối trước unwrap |
| TTL quá hạn | Cấp token TTL rất ngắn trong test rồi xử lý sau thời hạn | Token invalid, không trả secret; workflow báo lỗi |
| Policy bắt buộc wrapping | `min_wrapping_ttl` dương; gọi không header | Request bị Vault từ chối |
| Policy giới hạn max TTL | Yêu cầu TTL vượt max | Bị từ chối, không tự gia hạn |
| Lỗi 403 | Gọi endpoint bằng token thiếu quyền | Không lộ secret, không tạo kết quả thành công giả |
| Sự cố mạng/lặp request | Mô phỏng đứt kết nối sau khi Vault đã xử lý | Không tự retry vô hạn tạo nhiều SecretID |

**Ví dụ kỳ vọng cấp phát an toàn (pseudo-test):**

~~~java
WrappedSecretIdIssuer.WrappedDelivery wrapped = issuer.issueForOrders();
assert wrapped != null;
assert wrapped.token() != null && !wrapped.token().isBlank();
assert "auth/approle/role/orders/secret-id".equals(wrapped.creationPath());

String secretId = consumer.unwrapOrdersSecretId(wrapped.token());
assert secretId != null && !secretId.isBlank();

// Không log secretId hoặc wrapped.token();
// Gọi consumer.unwrapOrdersSecretId(wrapped.token()) lần 2 phải thất bại.
~~~

Đây là mô tả kiểm thử ở mức logic; trong JUnit cần dùng `assertThrows`/assertion phù hợp và setup Vault test với role được quản lý riêng. Tránh thêm `Thread.sleep` dài vào test chỉ để đợi TTL: tách logic xử lý lỗi và dùng token có TTL ngắn, điều kiện đồng bộ có giới hạn khi kiểm tra tích hợp thực.

## 12. Checklist trước khi triển khai

- [ ] Đã xác định API nào thực sự cần **response wrapping** để bàn giao qua ranh giới hệ thống.
- [ ] Request duy nhất mang `X-Vault-Wrap-TTL` hợp lệ; các request khác không vô tình kế thừa header.
- [ ] TTL đáp ứng độ trễ giao nhận và giới hạn `min_wrapping_ttl` / `max_wrapping_ttl`.
- [ ] Caller được workload authentication và Vault ACL cấp đúng quyền trên endpoint gốc.
- [ ] Producer xác minh `wrap_info.token`, `ttl` và `creation_path`, không forward raw secret.
- [ ] Wrapping token được đối xử như bearer secret và chỉ chuyển qua kênh đã xác thực.
- [ ] Bên nhận lookup và so `creation_path` **chính xác** trước khi unwrap.
- [ ] Unwrap được thực hiện **một lần**; lỗi đã dùng/hết hạn được ghi nhận và cảnh báo phù hợp.
- [ ] Bên nhận phân biệt response `data` với `auth` và áp dụng schema đúng endpoint.
- [ ] Không nhầm thời hạn wrapping token với TTL của SecretID, Vault token hay secret lease.
- [ ] Không ghi token, payload hoặc bản sao dữ liệu bí mật vào log/trace, history, message queue thiếu bảo vệ.
- [ ] Test bao gồm header per-call, policy bắt buộc, TTL không hợp lệ, token đã dùng, sai nguồn và lỗi mạng.

## Tài liệu tham khảo

- HashiCorp, [Response Wrapping](https://developer.hashicorp.com/vault/docs/concepts/response-wrapping) — `X-Vault-Wrap-TTL`, cubbyhole, creation path và quy trình xác thực token.
- HashiCorp, [Vault HTTP API: wrapping lookup](https://developer.hashicorp.com/vault/api-docs/system/wrapping-lookup), [unwrap](https://developer.hashicorp.com/vault/api-docs/system/wrapping-unwrap), [rewrap](https://developer.hashicorp.com/vault/api-docs/system/wrapping-rewrap), [wrap](https://developer.hashicorp.com/vault/api-docs/system/wrapping-wrap).
- HashiCorp, [Policies — Required response wrapping TTLs](https://developer.hashicorp.com/vault/docs/concepts/policies) — `min_wrapping_ttl` / `max_wrapping_ttl`.
- HashiCorp, [Vault CLI reference](https://developer.hashicorp.com/vault/docs/commands) và [unwrap command](https://developer.hashicorp.com/vault/docs/commands/unwrap).
- Spring Vault, [VaultOperations Java API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultOperations.html) — `doWithSession` và `opsForWrapping`.
- Spring Vault, [VaultWrappingOperations Java API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultWrappingOperations.html), [WrappedMetadata](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/WrappedMetadata.html) — lookup, read, rewrap và wrap.
- Spring, [Hands on with Spring Vault 2.1](https://spring.io/blog/2018/09/24/hands-on-with-spring-vault-2-1/) — phân biệt wrapping API gốc qua callback và API `VaultWrappingOperations`.
