# Kiểm tra đăng nhập, gia hạn, hết hạn và thu hồi token

## 1. Vì sao phải kiểm thử toàn bộ vòng đời Vault token?

Một ứng dụng Spring Boot tích hợp **HashiCorp Vault** có thể đăng nhập bằng Kubernetes ServiceAccount, AppRole hoặc JWT, nhận **Vault authentication token**, rồi gọi `VaultTemplate`/`VaultOperations` để đọc KV secret, mã hóa Transit, lấy dynamic database credential hoặc thao tác PKI. Lúc khởi động, mọi thứ có thể hoạt động tốt; nhưng sau vài phút hoặc vài giờ, token hết hạn, renewal thất bại hoặc token bị thu hồi. Nếu chỉ kiểm thử “đọc secret thành công”, chúng ta chưa biết ứng dụng sẽ phản ứng thế nào khi quyền truy cập thay đổi.

Bài học thuộc chương **Kiểm thử** của module **SPRING_VAULT**, tập trung vào **kiểm tra đăng nhập, gia hạn, hết hạn và thu hồi token** trong môi trường test tách biệt. Mục tiêu không chỉ là kiểm tra một HTTP status, mà là chứng minh ứng dụng:

- Đăng nhập bằng **đúng danh tính workload**, nhận token có policy và TTL phù hợp.
- Gia hạn token khi **được phép**, đọc lại TTL thực tế, không giả định token luôn renewable.
- Phát hiện token **hết hạn** và tránh tiếp tục sử dụng token cũ.
- Xác minh token **đã revoke** không còn dùng được; không nhầm sự tự động đăng nhập lại của Spring Vault với token cũ vẫn hợp lệ.
- Xử lý lỗi `403` do token không hợp lệ **khác** lỗi policy thiếu quyền.
- Bảo đảm mọi test cô lập, có cleanup, không để lộ Vault token, SecretID hoặc private key vào log.

**Lưu ý:** đây là kiểm thử **Vault auth token**. TTL của **Database dynamic secret lease**, **PKI certificate**, **response wrapping token** và **KV version** là các khái niệm riêng; không thể lấy kết quả test token để kết luận lease/secret đã hết hạn hoặc bị thu hồi.

## 2. Khái niệm cần nắm trước khi kiểm thử

### 2.1. Phân biệt auth method, Vault token và quyền truy cập

Một workload cần chứng thực với Vault qua một **auth method**. Ví dụ AppRole dùng `role_id` và `secret_id`; Kubernetes auth dùng JWT của ServiceAccount. Khi đăng nhập thành công, Vault thường trả về `auth.client_token`, các thông tin như `auth.lease_duration`, `auth.renewable`, policy và metadata.

~~~json
{
  "auth": {
    "client_token": "<VAULT_AUTH_TOKEN>",
    "accessor": "<TOKEN_ACCESSOR>",
    "policies": ["default", "orders-read"],
    "lease_duration": 60,
    "renewable": true
  }
}
~~~

Đây là ví dụ rút gọn, **không phải token thật**. `lease_duration` trong phần `auth` của phản hồi login liên quan tới vòng đời token được cấp. Trái lại, `lease_id` của dynamic database credential là lease của **một bí mật động**, có thể có thời hạn khác.

Token là bearer credential: ai có giá trị token hợp lệ có thể sử dụng quyền gắn với token đó. Vì vậy test phải giữ token kín, tuyệt đối không ghi `client_token`, `secret_id` hoặc header `X-Vault-Token` vào log, assertion message, report hay trace.

### 2.2. Trạng thái token và chuyển đổi quan sát được

~~~mermaid
stateDiagram-v2
    [*] --> Unauthenticated
    Unauthenticated --> Active: Workload login thành công
    Unauthenticated --> Rejected: Login sai danh tính hoặc auth role
    Active --> Renewed: Renew được chấp nhận
    Renewed --> Active: Tiếp tục gọi Vault
    Active --> Expired: TTL kết thúc
    Renewed --> Expired: Hết hiệu lực khi không thể renew
    Active --> Revoked: Revoke token
    Renewed --> Revoked: Revoke token
    Expired --> Unauthenticated: Xác thực lại theo cơ chế được phép
    Revoked --> Unauthenticated: Xác thực lại theo cơ chế được phép
    Rejected --> Unauthenticated: Sửa danh tính/cấu hình
~~~

`Active`, `Expired` và `Revoked` là **nhãn giải thích trong bài**, không phải status enum bắt buộc trong API Vault. Sau khi token hết hạn hoặc bị revoke, các API gọi bằng **chính token đó** sẽ không còn được phép; ứng dụng có thể **đăng nhập lại để nhận token mới** nếu thông tin xác thực workload vẫn hợp lệ.

### 2.3. Service token, batch token và quyền renew

Để kiểm thử renewal, hãy chọn **service token** có `renewable=true` và cấu hình TTL rõ ràng. **Batch token** có đặc điểm vòng đời khác, chẳng hạn không được gia hạn như service token; không sử dụng batch token để kết luận lỗi của chương trình renew. Token có thể không renewable hoặc bị chặn bởi TTL tối đa, explicit max TTL, policy, auth method hay trạng thái parent.

**Không được giả định token gia hạn được vô hạn:** một lời gọi renew có thể thành công và trả TTL ngắn hơn `increment` mong muốn. Với một số loại token periodic/renewable, quy tắc và giới hạn thời hạn khác nhau; test phải đọc metadata thực tế từ Vault và dùng đúng loại token đang đánh giá.

## 3. Môi trường kiểm thử an toàn, có thể tái lập

### 3.1. Kiến trúc fixture

Để tránh phá hỏng các token thật, nên dùng **Vault test riêng** (ví dụ Vault container do test harness quản lý) với KV v2, một AppRole dành riêng cho test và các policy tối thiểu. Có thể chạy Vault ở dev mode **chỉ trong môi trường cô lập**, với địa chỉ chỉ phục vụ test; dev root token không bao giờ dùng ngoài test.

~~~text
JUnit 5 / Spring Boot Test
          |
          | HTTPS nếu môi trường hỗ trợ và phù hợp
          v
    Vault test instance
      |-- auth/approle: orders-test
      |-- KV v2: secret/orders/config
      |-- policy: orders-test-read
      |-- disposable service tokens
          |
          v
Test verify: login -> lookup -> read -> renew -> expire/revoke
~~~

Tách vai trò test:

- **Fixture administrator:** chỉ dùng trong setup/teardown để tạo mount, policy, AppRole, token test và thu hồi những gì test tạo.
- **Workload under test:** đăng nhập qua AppRole/Kubernetes/JWT như service thật, chỉ được đọc đúng một secret.
- **HTTP probe:** gọi Vault bằng **token cụ thể** để kiểm tra token đó còn hợp lệ hay không; không tự login thay token.
- **Spring Vault client:** kiểm thử hành vi session manager của ứng dụng, có thể tự renew hoặc xác thực lại tùy cấu hình.

Không dùng root token để thực hiện toàn bộ test rồi kết luận một workload có đủ quyền. Root token có đặc điểm quyền và TTL không đại diện cho token ứng dụng.

### 3.2. Ví dụ provisioning trong Vault test

Giả sử Vault test đã khởi động và người chạy fixture có quyền quản trị:

~~~bash
# Trong môi trường test cô lập. Chỉ enable nếu mount chưa tồn tại.
vault secrets enable -path=secret -version=2 kv

# Secret vô hại dành cho bài test.
vault kv put -mount=secret orders/config \
  testFlag=enabled

# Tạo policy HCL cho workload đọc đúng một path.
vault policy write orders-test-read - <<'HCL'
path "secret/data/orders/config" {
  capabilities = ["read"]
}
HCL

# AppRole auth method dành cho fixture.
vault auth enable approle

# Token của AppRole được cấp TTL ngắn để kiểm thử.
vault write auth/approle/role/orders-test \
  token_policies=orders-test-read \
  token_type=service \
  token_ttl=30s \
  token_max_ttl=2m

# Đọc role_id và phát hành secret_id cho test;
# tuyệt đối không đẩy output này lên CI log công khai.
vault read auth/approle/role/orders-test/role-id
vault write -f auth/approle/role/orders-test/secret-id
~~~

Lệnh giả định mount/auth path chưa được dùng; fixture thực cần idempotency hoặc mỗi test run có namespace/mount riêng. Nếu sử dụng policy `default` của Vault, service token thường có quyền self-lookup/renew/revoke phù hợp; nếu tắt default policy phải **cấp quyền cụ thể** cho các endpoint self cần test. AppRole SecretID cần quản lý đúng `secret_id_ttl` và `secret_id_num_uses` nếu thiết lập giới hạn sử dụng.

Để test token **hết hạn**, có thể cấp riêng một **service token ngắn và không renewable** trong fixture, với TTL/explicit max TTL nhỏ được Vault chấp nhận. Không dựa vào root token không hết hạn hoặc service token được Spring Vault tự renew để kiểm thử expiry.

### 3.3. Nguyên tắc cô lập và cleanup

Mỗi test cần có một mã chạy riêng (test run ID), và token test nên được thu hồi khi kết thúc, kể cả assertion thất bại. Với các token được tạo từ parent, việc revoke parent có thể ảnh hưởng token con; vì vậy **không dùng chung parent bị thu hồi giữa các test song song**. Nếu thử revoke parent-child chain, phải tạo cây token riêng cho đúng test.

Một fixture nên thực hiện cleanup trong `finally`, JUnit `@AfterEach` hoặc khi container dừng; bảo đảm lỗi cleanup không che mất nguyên nhân test chính. Không để token tồn tại lâu hơn TTL cần thiết và không bỏ quên AppRole SecretID đã cấp.

## 4. Kịch bản A: đăng nhập và kiểm tra quyền của token mới

### 4.1. Đăng nhập bằng AppRole

Ví dụ HTTP:

~~~http
POST /v1/auth/approle/login
Content-Type: application/json

{
  "role_id": "<ORDERS_TEST_ROLE_ID>",
  "secret_id": "<ORDERS_TEST_SECRET_ID>"
}
~~~

Khi thành công, phải kiểm tra phản hồi **không chỉ có HTTP 200** mà còn có `auth.client_token` khác rỗng, TTL dương và chính sách phù hợp với role. Không tin một client token lấy từ environment cũ hoặc cache cũ là kết quả của lần login test này.

### 4.2. Lookup token của chính mình

~~~http
GET /v1/auth/token/lookup-self
X-Vault-Token: <NEW_WORKLOAD_TOKEN>
~~~

Dữ liệu rút gọn có thể có:

~~~json
{
  "data": {
    "id": "<NEW_WORKLOAD_TOKEN>",
    "policies": ["default", "orders-test-read"],
    "ttl": 27,
    "renewable": true,
    "type": "service"
  }
}
~~~

**Không log response lookup-self nguyên vẹn**, vì `id` có thể chứa giá trị token. Để kiểm tra, chương trình chỉ nên trích các trường an toàn cần thiết, ví dụ `ttl` và tập policy, rồi đưa assertion không in toàn bộ đối tượng.

Sau đó dùng token vừa cấp để đọc `secret/data/orders/config`. Kiểm tra **đọc được path được phép** và **bị từ chối ở path khác** (nếu tồn tại), để chứng minh policy áp dụng đúng. Một token có thể còn thời hạn nhưng thiếu quyền đọc path nào đó; đây là **authorization failure**, không phải token đã hết hạn.

### 4.3. Trường hợp đăng nhập âm tính

Các test bổ sung:

| Đầu vào | Kỳ vọng |
| --- | --- |
| `role_id` sai | Không có client token hợp lệ được cấp |
| `secret_id` sai/hết TTL/hết số lần dùng | Login thất bại |
| Đúng thông tin nhưng auth mount sai | Không đăng nhập được qua mount đó |
| Token được cấp nhưng policy không có `read` trên KV path | Login thành công; đọc KV bị từ chối |
| Vault không sẵn sàng | Lỗi hạ tầng; không đánh đồng với sai credential |

Mã HTTP cụ thể có thể thay đổi theo auth method, Vault version, proxy và lỗi đầu vào; test nên xác minh **hợp đồng**: không nhận token khi login thất bại, và không truy cập được tài nguyên khi thiếu quyền.

## 5. Kịch bản B: gia hạn token trước khi hết hạn

### 5.1. Gia hạn là gì?

**Renewal** làm Vault đánh giá điều kiện gia hạn và có thể kéo dài TTL của **cùng token**. Nó không phải một lần login mới và thường không thay đổi quyền của token. Khả năng renew phụ thuộc token, auth method, TTL tối đa và policy.

Cách gọi self-renew:

~~~http
POST /v1/auth/token/renew-self
X-Vault-Token: <RENEWABLE_WORKLOAD_TOKEN>
Content-Type: application/json

{
  "increment": "60s"
}
~~~

Ví dụ phản hồi rút gọn:

~~~json
{
  "auth": {
    "client_token": "<SAME_WORKLOAD_TOKEN>",
    "lease_duration": 60,
    "renewable": true
  }
}
~~~

Đây là giá trị minh họa. Vault có thể trả TTL thực tế **ngắn hơn 60 giây**, hoặc từ chối renewal. Với service token được phép renew, `auth.client_token` thường vẫn là cùng token, không phải token mới.

### 5.2. Những assertion đáng tin

Một bài test renewal nên:

1. Cấp token service `renewable=true` với TTL ngắn nhưng có khoảng thời gian đủ để gửi request.
2. Gọi `lookup-self` ngay trước renew để ghi nhận `ttl`, `renewable` và danh tính token.
3. Gọi `renew-self` với increment hợp lệ.
4. Kiểm tra phản hồi hợp lệ, danh tính token giữ nguyên và TTL thực tế dương, trong giới hạn cấu hình.
5. Gọi lookup-self và đọc KV bằng **chính token đó** để xác nhận vẫn có quyền sau renew.
6. Nếu cần chứng minh renew kéo dài lifetime, chọn điểm kiểm tra sau **thời hạn lẽ ra token cũ đã hết**, nhưng trước TTL mới thực tế; phải đo TTL từ response, không tự lấy increment làm cam kết.

**Không chỉ assert `ttlAfter > ttlBefore` trong mọi test:** thời gian mạng, granularity của TTL, max TTL và cơ chế periodic token có thể làm giá trị không tăng như dự kiến dù API thực hiện đúng hợp đồng. Tốt hơn là kiểm chứng renewal được chấp nhận, TTL hợp lệ và token tiếp tục dùng được theo cửa sổ thời gian có chủ đích.

### 5.3. Renewal thất bại là một phần bắt buộc

Cần có test cho token:

- `renewable=false`.
- Đã hết hạn hoặc đã bị revoke.
- Đạt giới hạn thời hạn tối đa nên không thể kéo dài theo mong muốn.
- Không có quyền endpoint renew-self (ví dụ token test bỏ default policy và không cấp quyền thay thế).
- Có sự cố mạng hoặc Vault tạm thời không sẵn sàng.

Với các lỗi này, **không bao giờ** kết luận “renew thành công” chỉ vì request đã gửi; trạng thái mới phải dựa trên response Vault và lookup theo token cụ thể.

## 6. Kịch bản C: token hết hạn tự nhiên

### 6.1. Thiết kế test expiry ổn định

Nếu dùng auth client tự động renew token, token có thể **không bao giờ hết hạn trong thời gian test**. Vì vậy kịch bản expiry riêng phải sử dụng token test **không renewable** hoặc vô hiệu hóa renewal cho phép quan sát chính token.

Ví dụ fixture quản trị tạo token test:

~~~bash
# Chỉ dùng trong Vault test riêng biệt.
# Token được xuất ra stdout: xử lý qua kênh kín, không đẩy vào CI log.
vault token create \
  -policy=orders-test-read \
  -ttl=10s \
  -explicit-max-ttl=10s \
  -renewable=false
~~~

TTL cuối cùng còn phụ thuộc cấu hình Vault. Bài test phải đọc TTL được Vault trả về để biết thời gian hợp lệ thực tế; nếu môi trường không cho TTL ngắn như yêu cầu, cần điều chỉnh fixture hoặc bỏ qua test theo lý do rõ ràng, không giả định thời hạn chắc chắn bằng 10 giây.

### 6.2. Quan sát expiry từ cùng token

~~~mermaid
sequenceDiagram
    autonumber
    participant Test as JUnit test
    participant Vault as Vault
    Test->>Vault: Tạo token không renewable, TTL ngắn
    Vault-->>Test: T + TTL thực tế
    Test->>Vault: GET lookup-self với T
    Vault-->>Test: Đang hợp lệ
    Test->>Vault: GET KV với T
    Vault-->>Test: Secret test
    Note over Test,Vault: Chờ có giới hạn, Vault quyết định expiry
    Test->>Vault: GET lookup-self với T
    Vault-->>Test: Token không còn hợp lệ
    Test->>Vault: GET KV với T
    Vault-->>Test: Truy cập bị từ chối
~~~

Đừng dùng một `Thread.sleep(10000)` rồi khẳng định hết hạn: thời gian nhận token, độ lệch và scheduling khiến test dễ flaky. Dùng **polling có timeout hữu hạn** (ví dụ Awaitility) và kiểm tra trạng thái trên Vault thật. Trước khi polling phải xác nhận token ban đầu thực sự hợp lệ và `renewable=false` để tránh false positive.

Ví dụ phác thảo:

~~~java
// Fixture tạo token không renewable và bảo đảm TTL thực tế ngắn.
String token = testFixture.createShortNonRenewableServiceToken();

assertThat(tokenProbe.canReadKv(token)).isTrue();

await()
        .atMost(Duration.ofSeconds(30))
        .pollInterval(Duration.ofMillis(250))
        .until(() -> !tokenProbe.canLookupSelf(token));

assertThat(tokenProbe.canReadKv(token)).isFalse();
~~~

`testFixture` và `tokenProbe` là fixture do dự án xây dựng; `await()` thuộc thư viện Awaitility, không phải API Spring Vault. Cần triển khai `canReadKv()` để phân biệt đúng lỗi HTTP do token hết hiệu lực với lỗi đường truyền/proxy; **mất kết nối không chứng minh token đã hết hạn**.

### 6.3. Hết hạn không làm ứng dụng tự có token mới

Token hết hạn làm request dùng token cũ bị từ chối. Nếu Spring Vault được cấu hình `LifecycleAwareSessionManager` và một `ClientAuthentication` còn hợp lệ, ứng dụng có thể **đăng nhập lại**. Token mới là một credential khác và phải được kiểm tra riêng.

Nếu AppRole SecretID đã hết hạn hoặc hết số lần dùng, **đăng nhập lại có thể thất bại** dù Vault đang khỏe mạnh. Vì vậy test session recovery cần xem cả vòng đời nguồn authentication, không chỉ TTL token.

## 7. Kịch bản D: thu hồi token theo yêu cầu

### 7.1. Revoke-self

Một workload có quyền tương ứng có thể chủ động revoke **chính token đang dùng**:

~~~http
POST /v1/auth/token/revoke-self
X-Vault-Token: <DISPOSABLE_WORKLOAD_TOKEN>
Content-Type: application/json

{}
~~~

Vault có thể trả response thành công **không có JSON body**; không nên bắt buộc response chứa một trường `revoked=true` không được API cam kết.

Sau khi revoke thành công:

1. Gọi `lookup-self` bằng **đúng token vừa revoke** phải không còn cho thấy token hợp lệ.
2. Gọi KV bằng **cùng token** phải bị từ chối.
3. Test xác nhận token khác vẫn hợp lệ nếu nó không phải token bị thu hồi hoặc descendant của token đó.
4. Ghi trạng thái nghiệp vụ `REVOKED` khi có bằng chứng, không chỉ vì lệnh revoke được khởi tạo.

### 7.2. Revoke bởi quản trị viên

Trong tình huống incident hoặc cleanup, admin có quyền có thể gọi endpoint `auth/token/revoke` với token ID. Lệnh CLI minh họa:

~~~bash
# Không dùng token thật trong command line ở môi trường nhạy cảm:
# shell history và process inspection có thể làm lộ bearer credential.
vault token revoke "<DISPOSABLE_TOKEN_ID>"
~~~

Nên dùng fixture/helper bảo vệ token và cấp quyền tối thiểu trong test. Không tự động chạy revoke trên root/admin token đang dùng bởi các test khác.

### 7.3. Parent-child và phạm vi ảnh hưởng

Vault có mô hình **cây token** đối với một số loại service token. Revoke parent có thể ảnh hưởng token con và các lease liên quan. Khi kiểm thử hành vi này, phải dùng một cây token **riêng** và xác minh từng token liên quan; không revoke một parent dùng chung giữa nhiều test hoặc workload.

**Đừng đồng nhất revoke Vault auth token với revoke mọi loại secret độc lập:** dynamic secret có lease, token con và các đối tượng do Vault quản lý có quan hệ lifecycle theo quy tắc riêng. Một chứng thư X.509 đã cấp không mặc nhiên bị thu hồi theo PKI chỉ vì token đã gọi API cấp chứng thư bị revoke; phải có quy trình revoke certificate riêng.

## 8. Điểm dễ sai: SessionManager có thể che mất token đã hết hiệu lực

Đây là điểm quan trọng nhất của các bài test vòng đời token trong Spring Vault.

### 8.1. Hai câu hỏi khác nhau

**Câu hỏi A:** “Token T tôi vừa revoke/hết hạn còn dùng được không?” Cần gọi Vault bằng **đúng T**, không tự thay token giữa các request.

**Câu hỏi B:** “Ứng dụng Spring Vault có tiếp tục truy cập Vault được sau khi token hiện tại hết hạn/revoke không?” Có thể **có**, nếu client/session manager thực hiện reauthentication thành công.

Một test chỉ gọi `vaultOperations.read("secret/data/orders/config")` sau khi đã revoke một token rồi thấy thành công **không chứng minh token đó vẫn còn hợp lệ**. Spring Vault có thể đang dùng token khác được cấp sau khi login lại, hoặc một token được cache ở một session manager khác.

### 8.2. Tách “raw token probe” và “application client”

| Thành phần test | Token được chọn thế nào? | Dùng để chứng minh |
| --- | --- | --- |
| **HTTP probe có header cố định** | Mỗi request truyền đúng T | Lookup, renew, expiry, revoke của **token T** |
| **Spring Vault client có SessionManager** | Client lấy token từ session lifecycle | Application recovery, login/renew tự động và hiệu ứng cấu hình |
| **Fixture admin** | Token quản trị test riêng | Setup/teardown, tạo role/token và cleanup |

Có thể dùng `RestClient` (Spring Framework 6.1+) làm HTTP probe với token được truyền tường minh, không cấu hình auto-login. Với Spring Framework phiên bản khác, sử dụng `RestTemplate` hoặc HTTP client phù hợp.

## 9. Ví dụ Java: kiểm tra một token cụ thể qua HTTP

Mẫu Java 17+ dưới đây dùng `RestClient` để gọi các endpoint token trực tiếp. Nó **bổ trợ cho Spring Vault**, không thay thế `VaultOperations` trong ứng dụng. Mục đích là giữ token đang test cố định, tránh session manager tự đổi token khi xác minh lỗi.

~~~java
package com.example.vault.testing;

import java.util.Map;
import java.util.Objects;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

public final class VaultTokenProbe {

    private final RestClient rest;

    public VaultTokenProbe(String vaultBaseUrl) {
        this.rest = RestClient.builder()
                .baseUrl(vaultBaseUrl)
                .build();
    }

    public JsonNode loginAppRole(String roleId, String secretId) {
        return Objects.requireNonNull(
                rest.post()
                        .uri("/v1/auth/approle/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(Map.of(
                                "role_id", roleId,
                                "secret_id", secretId))
                        .retrieve()
                        .body(JsonNode.class));
    }

    public JsonNode lookupSelf(String token) {
        return Objects.requireNonNull(
                rest.get()
                        .uri("/v1/auth/token/lookup-self")
                        .header("X-Vault-Token", token)
                        .retrieve()
                        .body(JsonNode.class));
    }

    public JsonNode renewSelf(String token, String increment) {
        return Objects.requireNonNull(
                rest.post()
                        .uri("/v1/auth/token/renew-self")
                        .header("X-Vault-Token", token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(Map.of("increment", increment))
                        .retrieve()
                        .body(JsonNode.class));
    }

    public void revokeSelf(String token) {
        rest.post()
                .uri("/v1/auth/token/revoke-self")
                .header("X-Vault-Token", token)
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of())
                .retrieve()
                .toBodilessEntity();
    }

    public JsonNode readTestKv(String token) {
        return Objects.requireNonNull(
                rest.get()
                        .uri("/v1/secret/data/orders/config")
                        .header("X-Vault-Token", token)
                        .retrieve()
                        .body(JsonNode.class));
    }
}
~~~

Mã minh họa yêu cầu Jackson và Spring Framework có `RestClient`. Trong môi trường TLS thực tế, phải cấu hình HTTP client của probe với truststore/hostname verification phù hợp; không tắt xác minh TLS để “cho test chạy”. Nếu dùng Vault Enterprise namespace, phải truyền namespace đã xác định theo đúng môi trường vào request. `roleId`, `secretId` và token phải được bảo vệ trong test process.

**Hợp đồng của probe:**

- Lấy token ở `loginAppRole()` từ `response.path("auth").path("client_token").asText()` và xác nhận không rỗng.
- `lookupSelf()` trả metadata trong `response.path("data")`.
- `renewSelf()` trả dữ liệu `auth` khi renewal thành công.
- `revokeSelf()` có thể thành công mà không có body.
- Với token không hợp lệ hoặc policy thiếu quyền, `RestClient` thường ném `RestClientResponseException` khi nhận 4xx/5xx.
- Một HTTP timeout/network error **không phải bằng chứng expiry hoặc revoke**. Test helper phải phân loại riêng lỗi I/O và HTTP từ Vault.

### 9.1. Ví dụ test login → renew → revoke

~~~java
@Test
void appRoleTokenCanRenewThenCannotBeUsedAfterRevoke() {
    JsonNode login = probe.loginAppRole(
            fixture.roleId(), fixture.secretId());

    JsonNode auth = login.path("auth");
    String token = auth.path("client_token").asText();

    assertThat(token).isNotBlank();
    assertThat(auth.path("lease_duration").asInt()).isPositive();
    assertThat(auth.path("renewable").asBoolean()).isTrue();

    JsonNode before = probe.lookupSelf(token).path("data");
    assertThat(before.path("ttl").asInt()).isPositive();

    JsonNode renewed = probe.renewSelf(token, "30s").path("auth");
    assertThat(renewed.path("client_token").asText())
            .isEqualTo(token);
    assertThat(renewed.path("lease_duration").asInt())
            .isPositive();

    assertThat(probe.readTestKv(token)
            .path("data").path("data").path("testFlag").asText())
            .isEqualTo("enabled");

    probe.revokeSelf(token);

    assertThatThrownBy(() -> probe.lookupSelf(token))
            .isInstanceOf(
                    org.springframework.web.client.RestClientResponseException.class);
    assertThatThrownBy(() -> probe.readTestKv(token))
            .isInstanceOf(
                    org.springframework.web.client.RestClientResponseException.class);
}
~~~

Đây là **test skeleton**, phụ thuộc fixture `probe` và `fixture` cung cấp AppRole, policy cùng secret test. `assertThat` và `assertThatThrownBy` thuộc AssertJ; `@Test` thuộc JUnit 5. Nếu role test hoặc token đang không renewable, phải dùng fixture chuyên cho renewal trước khi chạy. Để cleanup, nên thu hồi token còn sống trong `finally`/fixture teardown; ví dụ cố ý không in token trong assertion.

Để test “sau revoke bị từ chối” chặt chẽ hơn, helper có thể phân loại 403/permission denied từ Vault so với lỗi network và khẳng định endpoint nhận được request; không chỉ bắt một exception bất kỳ.

## 10. Kiểm thử Spring Vault SessionManager trong ứng dụng

### 10.1. Cấu hình đúng workload authentication

Một ứng dụng có thể dùng `ClientAuthentication` tương ứng auth method và `SessionManager` để nhận/cung cấp token. Với các cấu hình hỗ trợ lifecycle, `LifecycleAwareSessionManager` có thể quản lý renewal hoặc xác thực lại theo chính sách. Hành vi cụ thể phụ thuộc Spring Vault/Spring Cloud Vault version, loại token và auth method.

Trong test ứng dụng, nên có các scenario tách biệt:

1. **Startup login:** chưa có token; gọi Vault lần đầu khiến client đăng nhập bằng đúng workload identity rồi đọc KV thành công.
2. **Token renewal:** token renewable; client duy trì phiên qua khoảng thời gian đủ để renewal xảy ra, kiểm tra metric/event thật thay vì chỉ suy ra từ read thành công.
3. **Expiry khi không renew:** client không renewal hoặc token không renewable; khi token cũ hết hạn, kiểm tra khả năng đăng nhập lại nếu nguồn auth còn hợp lệ.
4. **Revoke token ngoài ứng dụng:** fixture admin revoke token hiện tại; kiểm tra client xử lý như cấu hình (reauth, báo lỗi, circuit breaker), không che giấu sự cố nếu đăng nhập lại thất bại.
5. **Nguồn auth không còn hợp lệ:** AppRole SecretID hết hạn/hết use, Kubernetes JWT không hợp lệ hoặc auth role bị ràng buộc sai; reauth phải thất bại và ứng dụng không được fallback sang root token.

Khi kiểm tra token cũ, dùng probe cố định. Khi kiểm tra hành vi ứng dụng, quan sát **thời điểm client được cấp token mới**, metric token renewal/reauth và API call sau đó. Không khẳng định chỉ một lời gọi `VaultOperations.read()` thành công chứng minh một cơ chế session cụ thể đã xảy ra.

### 10.2. Cẩn trọng với Spring Cloud Vault bootstrap

Spring Cloud Vault có thể đọc secret **trong bootstrap/config import** trước khi business bean được tạo. Nếu token hết hạn hoặc Vault không sẵn sàng, lỗi có thể xuất hiện ngay lúc application context khởi tạo, khác với lỗi runtime. Cần test cả bootstrap và runtime theo đúng version/cách cấu hình.

Không để test token TTL quá ngắn khiến context khởi tạo chậm một chút là hỏng; với phép kiểm thử expiry hãy cấp token chuyên dụng cho probe. Với phép kiểm thử session recovery hãy dùng TTL đủ dài, đưa ra điều kiện thời gian quan sát và assert các sự kiện đã xác minh.

## 11. Ma trận kiểm thử lỗi và kết quả kỳ vọng

| Trường hợp | Điều phải quan sát | Không được kết luận nhầm |
| --- | --- | --- |
| Login hợp lệ | Có token, TTL/policy phù hợp, KV read thành công | Root token cũng đọc được nên workload chắc có quyền |
| Login sai SecretID | Không được cấp token mới | Mọi lỗi mạng đều là sai SecretID |
| Token hợp lệ nhưng thiếu policy | Lookup-self còn hợp lệ; path KV bị từ chối | Token hết hạn |
| Token renewable | Renew được chấp nhận, TTL theo phản hồi và token vẫn dùng được | Increment mong muốn chính là TTL thực tế |
| Token nonrenewable | Renew không tạo ra lifetime mới | Vault luôn lỗi cùng mã HTTP |
| Token đã hết TTL | Probe dùng token cũ bị từ chối sau thời hạn Vault ghi nhận | SessionManager không thể đăng nhập lại |
| Token bị revoke | Probe với đúng token cũ không còn được phép | Kết nối TLS còn mở chứng minh token còn hợp lệ |
| Revoke parent token | Các token con/lease có quan hệ bị ảnh hưởng theo semantics Vault | Mọi token độc lập đều bị revoke |
| Timeout khi renew | Chưa xác định renewal có được xử lý hay không | Renewal chắc chắn thất bại hoặc thành công |
| Vault 5xx khi login | Lỗi hạ tầng, có retry/backoff hữu hạn | Sửa policy sẽ chữa được lỗi server |
| Session reauth thành công | Client ứng dụng nhận token hợp lệ mới | Token cũ đã hết hạn/revoke vẫn dùng được |
| Vault bị gián đoạn khi startup | Bootstrap xử lý lỗi theo chính sách | Mọi lỗi đều do config KV thiếu |

Không assert các chuỗi thông báo lỗi chính xác nếu chúng không phải hợp đồng ổn định. Có thể xác minh mã HTTP hoặc nhóm trạng thái, nhưng phải lưu ý proxy và các phiên bản Vault.

## 12. Kiểm thử thời gian và lỗi mạng không bị flaky

### 12.1. Tránh phụ thuộc đồng hồ máy test

TTL được Vault quản lý. Kết quả `lookup-self.data.ttl` là số giây còn lại tại thời điểm lookup, không phải một mốc tuyệt đối không đổi. Test nên:

- Poll trạng thái token **từ Vault** với timeout hữu hạn.
- Đo thời gian chờ bằng clock đơn điệu `System.nanoTime()` hoặc công cụ hỗ trợ, không so đồng hồ tường tại máy test với `creation_time` rồi quyết định chính xác từng mili giây.
- Không dùng `Thread.sleep()` duy nhất làm điều kiện chứng minh expiry.
- Tránh chạy test renewal và test expiry dùng **cùng token** trong hai luồng; một test có thể renew token trong lúc test kia chờ hết hạn.
- Giới hạn TTL test, dọn token cuối test, không để suite kéo dài bất thường.

### 12.2. Fault injection

Trong integration test cô lập, có thể mô phỏng:

- **DNS/network failure** khi login, lookup, renew hoặc revoke.
- **HTTP 503/429** tại proxy kiểm thử, để xác minh retry có backoff và giới hạn.
- **Timeout sau khi Vault nhận renewal**; không thể kết luận renewal thất bại chỉ vì Java không nhận response.
- **Lỗi kết nối sau khi gửi revoke-self**; token có thể đã bị revoke, cần dùng probe/admin để đối soát.
- **Vault restart**: phân biệt môi trường dev (có thể mất trạng thái do storage không bền) với môi trường test có storage bền vững. Không dùng hành vi mất token do dev restart để kết luận Vault production cũng làm vậy.
- **Ngắt kết nối đang hoạt động**: kiểm tra request sau khi revoke/expiry, không khẳng định mọi request đã được Vault chấp nhận trước đó sẽ bị hủy ngay.

### 12.3. Retry riêng cho từng thao tác

Không thiết kế “retry mọi 4xx”:

- Login sai role/SecretID hoặc 403 do policy: sửa thông tin/quyền; retry cùng input thường không giúp ích.
- Renew bị từ chối do nonrenewable/max TTL: chuyển sang reauth hoặc báo lỗi theo policy ứng dụng, không retry vô hạn.
- Lookup token đã revoke: không retry để khôi phục token.
- Lỗi mạng/503: backoff+jitter, retry budget và deadline, nhưng phải **đối soát trường hợp response bị mất**.
- Revoke sau timeout: cần xác định token còn hợp lệ hay đã thu hồi trước khi coi thao tác thất bại; không phục hồi tự động bằng token cũ.

## 13. Audit, metrics và an toàn thông tin trong kiểm thử

Các test vòng đời token dễ làm lộ bearer credential qua assertion, CI output hoặc tool ghi HTTP traffic. Khuyến nghị:

1. **Tắt log raw HTTP body/header:** nhất là `X-Vault-Token`, `auth.client_token`, `secret_id` và response lookup-self chứa token ID.
2. **Đừng dùng token làm test name, correlation ID hoặc metric label.** Sử dụng mã ngẫu nhiên test run không liên quan tới secret.
3. **Bảo vệ artifact CI:** báo cáo test chỉ lưu status, thời gian và mã lỗi đã chuẩn hóa; không lưu toàn bộ fixture configuration.
4. **Chặn quyền quá rộng:** fixture admin chỉ dùng setup/cleanup; workload test chỉ có policy cần thiết.
5. **Dọn fixture:** revoke token còn sống, SecretID và các lease/secret test phát sinh; dừng Vault test environment.
6. **Quan sát qua audit Vault:** khi bật, xác minh xử lý dữ liệu nhạy cảm đúng cách và kiểm soát quyền xem log. Không đưa audit log chứa thông tin nhạy cảm vào output công khai.

Những metric gợi ý:

| Metric | Ý nghĩa |
| --- | --- |
| `vault_login_attempt_total` | Số lần workload login theo kết quả |
| `vault_token_renew_success_total` | Số lần renew xác nhận thành công |
| `vault_token_renew_failure_total` | Số lần renew thất bại |
| `vault_token_reauth_total` | Số lần session đăng nhập lại |
| `vault_token_ttl_seconds_remaining` | TTL còn lại của token đang sử dụng |
| `vault_auth_forbidden_total` | Lỗi gọi API do auth/policy |
| `vault_token_lifecycle_latency_seconds` | Độ trễ login/lookup/renew/revoke |

Đây là **metric ứng dụng có thể tự instrument**, không phải danh sách tên mặc định của Spring Vault hay Vault. Không đưa token ID/accessor, username riêng của mỗi credential hoặc payload secret vào labels. TTL cần được đọc/thu thập theo quyền hợp lệ, không tạo thêm hàng loạt request chỉ để lấy metrics.

## 14. Kế hoạch kiểm thử tối thiểu cho CI

Một pipeline CI có thể tổ chức theo thứ tự:

| Nhóm | Môi trường | Điều kiện PASS |
| --- | --- | --- |
| Unit test response mapper | Không cần Vault thật | Phân tích auth/lookup/renew response và exception đúng |
| Integration login | Vault test + AppRole test | Login hợp lệ nhận token, login sai không có token |
| Authorization | Vault test + KV v2 | Đúng policy read được, thiếu policy bị từ chối |
| Renewal | Service token renewable | Renew được xác nhận và token tiếp tục hợp lệ |
| Expiry | Token test TTL ngắn, nonrenewable | Token cũ bị từ chối sau TTL theo polling hữu hạn |
| Revoke | Token riêng cho từng test | Revoke xong probe của token cũ bị từ chối |
| Session recovery | Spring Vault + auth method test | Client ứng dụng hoạt động theo chính sách reauth/renew |
| Failure injection | Vault/proxy test | Có backoff, timeout, lỗi được phân loại đúng |
| Cleanup | Fixture admin | Không còn token/lease test ngoài phạm vi cho phép |

**Không chạy các test lifecycle mang tính phá hủy song song với cùng một token hoặc cùng parent token.** Nếu cần tăng tốc suite, phát hành token và role/SecretID tách riêng từng test, tránh chia sẻ trạng thái khiến kết quả phụ thuộc thứ tự chạy.

### 14.1. Các assertion nên có

Ví dụ các điều kiện test tránh “false positive”:

- Token được dùng cho lookup/renew/revoke phải **chính là token vừa phát hành cho test**.
- Token mới và token cũ được định danh trong bộ nhớ test, nhưng không được đưa vào log.
- Trước expiry/revoke, phải có ít nhất một thao tác **thành công bằng token cũ** để khẳng định fixture hợp lệ.
- Sau expiry/revoke, phải có bằng chứng **HTTP từ Vault** token cũ không còn dùng được; không coi lỗi DNS/connection là token đã mất hiệu lực.
- Login thành công không đủ: phải kiểm tra **policy thực sự cho/không cho** truy cập đúng KV path.
- Renew thành công không đủ: phải đọc TTL thật và kiểm chứng token còn hợp lệ, không giả định increment luôn được đáp ứng.
- Reauthentication thành công không đủ: phải chứng minh token dùng sau recovery **khác token cũ** khi tình huống bắt buộc như vậy.

## 15. Bài thực hành: hoàn chỉnh một suite token lifecycle

**Tình huống:** ứng dụng `orders-api` chạy trên Kubernetes, dùng Spring Vault để đọc `secret/data/orders/config`. Nhóm phát triển muốn chứng minh ứng dụng không bị gián đoạn khi token tới hạn cần renew, đồng thời vẫn chặn một token đã bị thu hồi.

Thực hành trong Vault test:

1. Tạo KV v2 mount, secret test, policy read-only và AppRole test như mẫu. Nếu hệ thống có Kubernetes auth test tương ứng, thực hiện thêm một test đăng nhập bằng JWT của ServiceAccount test.
2. Dùng probe đăng nhập và kiểm tra `auth.client_token`, TTL, policies, rồi đọc KV với **đúng token vừa nhận**.
3. Cấp token renewable có TTL ngắn; gọi `renew-self`, đọc lại TTL và xác minh cùng token còn hợp lệ.
4. Cấp token **không renewable**, xác nhận đọc KV được lúc đầu, chờ theo polling hữu hạn rồi xác nhận token cũ hết hiệu lực.
5. Cấp token riêng cho revoke; gọi `revoke-self`, rồi xác minh lookup và KV read bằng token đó bị từ chối.
6. Dùng một client Spring Vault có session manager thích hợp; kiểm tra hành vi renew/reauth, đồng thời dùng probe xác minh token cũ không trở lại hợp lệ.
7. Cố ý dùng token thiếu KV policy để chứng minh lỗi permission không phải token expiry.
8. Mô phỏng Vault 503 và timeout khi renew/revoke; xác minh trạng thái chưa chắc chắn không bị báo thành công.
9. Ghi lại metrics login, renew, reauth và lỗi auth; kiểm tra không có token/SecretID trong CI logs hoặc test reports.
10. Cleanup mọi token test, role test và môi trường Vault cô lập theo đúng ownership.

**Câu hỏi tự kiểm tra:**

1. Vault auth token và dynamic database credential lease khác nhau như thế nào?
2. Tại sao một token còn TTL vẫn có thể bị từ chối khi đọc KV?
3. Vì sao dùng root token để test AppRole workload là sai mục tiêu?
4. Vì sao renewal increment 60 giây không bảo đảm TTL cuối cùng đúng 60 giây?
5. Cần cấu hình loại token nào để test expiry mà không bị auto-renew che lấp?
6. Vì sao `VaultOperations.read()` vẫn thành công sau revoke chưa chứng minh token cũ còn sống?
7. Tại sao timeout trong revoke không thể được coi ngay là revoke thất bại?
8. Tại sao cần polling có timeout thay vì một lệnh sleep cố định?
9. Revoke parent token có thể ảnh hưởng gì tới token con?
10. Những trường dữ liệu nào phải loại bỏ khỏi log, trace và assertions?

## 16. Kết luận

Kiểm thử **đăng nhập, gia hạn, hết hạn và thu hồi Vault token** cần kiểm chứng toàn bộ vòng đời danh tính workload, chứ không dừng ở một lần đọc secret thành công. Test login phải xác minh token, policy và quyền thực tế; test renew phải xem trạng thái/TTL Vault xác nhận; test expiry/revoke phải dùng **đúng token cũ**, có bằng chứng từ Vault và phân biệt với lỗi hạ tầng.

Với **Spring Vault**, việc `ClientAuthentication` và `SessionManager` có thể cấp hoặc làm mới token khiến test cần phân tách **token probe cố định** và **application client có vòng đời tự động**. Kết hợp Vault test cô lập, timeout/polling hữu hạn, fault injection, audit bảo mật và cleanup chặt chẽ sẽ tạo một suite tích hợp đáng tin cậy cho KV, token/lease và các workload dùng Transit, PKI hay database secrets.

**Tài liệu tham khảo:** [HashiCorp Vault Token API](https://developer.hashicorp.com/vault/api-docs/auth/token), [HashiCorp AppRole auth](https://developer.hashicorp.com/vault/docs/auth/approle) và [Spring Vault Reference](https://docs.spring.io/spring-vault/reference/). Khi triển khai, đối chiếu quyền endpoint self, token types, lifetime limits và APIs với phiên bản Vault/Spring Vault đang sử dụng.
