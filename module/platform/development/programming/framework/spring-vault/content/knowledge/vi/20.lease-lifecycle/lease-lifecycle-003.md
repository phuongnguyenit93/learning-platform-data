# Yêu cầu gia hạn và thời hạn thực tế được máy chủ cấp trong Spring Vault

Trong ứng dụng Java sử dụng **Spring Vault** (ví dụ `VaultTemplate`) để truy cập **HashiCorp Vault**, một ứng dụng có thể nhận secret động với lease 30 phút rồi đề nghị gia hạn thêm 60 phút. Điều đó **không có nghĩa Vault sẽ cấp đúng 60 phút**. Máy chủ đánh giá loại token/lease, giới hạn TTL, chính sách của auth method hoặc secret engine và trạng thái của credential trước khi quyết định. Phản hồi gia hạn mới là bằng chứng về **thời hạn thực tế được cấp**.

Bài học thuộc chương **Vòng đời lease**, đi sâu vào cách đọc yêu cầu gia hạn và kết quả của Vault, phân biệt vòng đời **Vault client token** với **dynamic secret lease**, tích hợp cơ chế gia hạn vào Spring Vault, giám sát và kiểm thử. Các ví dụ đặt trong bối cảnh ứng dụng Java xác thực theo workload, đọc KV secrets, nhận mật khẩu Database động, dùng Transit encryption và PKI theo chính sách phân quyền tối thiểu.

## 1. Mục tiêu và những khái niệm cần phân biệt

Sau bài học, bạn có thể:

1. Giải thích sự khác nhau giữa **TTL ban đầu**, **`increment` được yêu cầu**, **`lease_duration` được cấp**, **TTL còn lại** và **giới hạn tuổi thọ tối đa**.
2. Phân biệt gia hạn Vault token với gia hạn lease do secret engine cấp.
3. Dùng Vault CLI/API đọc phản hồi gia hạn và lập lịch theo kết quả máy chủ trả về.
4. Phát hiện lease không renewable, đã bị revoke, đã hết hạn hoặc chạm giới hạn max TTL.
5. Áp dụng `SecretLeaseContainer` đúng trường hợp trong Spring Vault và kiểm thử timeout, lỗi gia hạn và đóng `ApplicationContext`.

| Thuật ngữ | Diễn giải | Nguồn kiểm chứng |
| --- | --- | --- |
| **Initial TTL** | Thời gian sống được cấp lúc tạo token/secret. | Trường `lease_duration` lúc phát hành hoặc lookup. |
| **Requested increment** | Khoảng thời gian client muốn có khi gọi API renew, ví dụ `increment=1h`. | Request gửi từ client; **không phải cam kết từ Vault**. |
| **Granted duration** | Khoảng thời gian Vault thực sự cho phép sau khi renew. | `lease_duration` trong phản hồi gia hạn, hoặc `ttl` khi lookup. |
| **Remaining TTL** | Khoảng thời gian còn lại tính tại thời điểm quan sát; giảm theo thời gian. | `ttl` từ API lookup hoặc tính xấp xỉ từ response và đồng hồ. |
| **Renewable** | Lease/token có thể đề nghị renew khi các điều kiện vẫn cho phép. | `renewable` của token/lease; `true` không đảm bảo mọi lần renew đều được chấp nhận. |
| **Maximum TTL / giới hạn lease** | Giới hạn do Vault và backend áp dụng theo chính sách cụ thể. | Cấu hình hệ thống, mount, role/engine và kết quả thực nghiệm. |
| **Lease ID** | Định danh lease cho dynamic secret, dùng ở API lookup/renew/revoke. | `lease_id` từ phản hồi của engine; không phải Vault token. |

**Điểm mấu chốt:** nhận `renewable: true` không có nghĩa được gia hạn vô hạn; gửi `increment=3600` không có nghĩa TTL mới bằng 3.600 giây; HTTP 200 từ renew cũng chưa cho biết secret có thể dùng thêm đúng 3.600 giây nếu không đọc phản hồi.

## 2. Lease hoạt động như một hợp đồng có điều kiện

~~~mermaid
stateDiagram-v2
    [*] --> Issued: Engine cấp secret + lease_id + TTL
    Issued --> Active: Consumer nhận secret
    Active --> RenewalRequested: Client yêu cầu renew(increment)
    RenewalRequested --> Active: Vault chấp thuận và trả TTL thực cấp
    RenewalRequested --> RenewalRejected: Vault từ chối / timeout / không renewable
    RenewalRejected --> Active: Lease vẫn còn hạn (nếu chưa revoke/expire)
    Active --> Expired: Đến thời điểm hết hạn
    Active --> Revoked: Revoke chủ động / cascading revoke
    RenewalRejected --> Expired: Không renew trước hạn
    Expired --> [*]
    Revoked --> [*]
~~~

Bằng một lần gọi API, ứng dụng chỉ yêu cầu Vault **đánh giá gia hạn**. Quyết định cuối cùng nằm ở máy chủ và secret engine. Cần quan sát cả **mã HTTP**, **nội dung response**, **thời điểm nhận response** và **trạng thái thực tế của credential trên hệ thống đích**.

Với Database secrets engine, Vault có thể phát sinh username/password tạm thời với lease; khi đến hạn hoặc bị revoke, engine thực hiện hành động thu hồi theo cấu hình backend. Với KV v2, đọc một static secret thông thường **không tạo dynamic lease có thể renew**. Với Transit, thao tác encrypt/decrypt cũng không tự phát sinh secret lease như Database credentials. Với PKI, TTL và hiệu lực certificate cần kiểm tra riêng, không coi việc renew token là gia hạn một chứng chỉ đã phát hành.

## 3. Phản hồi máy chủ mới quyết định thời hạn còn lại

Giả sử Vault cấp dynamic database credential lúc 10:00:

~~~json
{
  "lease_id": "database/creds/orders-read/<id-da-luoc-bo>",
  "lease_duration": 1800,
  "renewable": true
}
~~~

Đây là **trích đoạn metadata minh họa**, không phải toàn bộ phản hồi. `lease_duration: 1800` thể hiện TTL ban đầu **1.800 giây (30 phút)** tại thời điểm cấp; response đầy đủ có thể còn chứa username/password cần bảo vệ.

Đến 10:15, ứng dụng xin gia hạn với `increment=3600` (1 giờ). Vault kiểm tra giới hạn thực tế và chấp thuận:

~~~json
{
  "lease_id": "database/creds/orders-read/<id-da-luoc-bo>",
  "lease_duration": 600,
  "renewable": true
}
~~~

**Điều phải ghi nhận:** sau lần gia hạn này, thời hạn được thông báo là **600 giây (10 phút)**, dù client đã xin 3.600 giây. Nếu nhận response lúc 10:15:02, mốc hết hạn ước tính là **10:25:02**, cần dự phòng độ trễ và sai số đo; **không** được tự ghi 11:15 hay coi đây là 60 phút được cộng vào mốc cũ.

Ví dụ trên chỉ nhằm minh họa sự khác biệt giữa yêu cầu và phê duyệt. Không thể suy ra chính xác thuật toán giới hạn chỉ từ hai con số: nguyên nhân có thể nằm ở TTL tối đa, tuổi thọ tính từ lúc cấp, lease backend, token/role hoặc cấu hình mount. Để biết vì sao Vault chỉ cấp 600 giây, cần xem metadata và cấu hình tương ứng trên hệ thống thật.

### Phân biệt ba mốc thời gian

| Mốc | Giá trị ví dụ | Ý nghĩa |
| --- | --- | --- |
| T0 – cấp lần đầu | 10:00, granted TTL = 1.800 s | Thời điểm tham chiếu để lập lịch ban đầu. |
| T1 – gửi renew | 10:15, requested increment = 3.600 s | Điều ứng dụng mong muốn; chưa nói lên kết quả. |
| T2 – nhận renew response | 10:15:02, granted TTL = 600 s | Dùng TTL mới và thời điểm nhận response để tính hạn và lịch renew tiếp theo. |

Nếu request renew **timeout**, client không biết Vault đã xử lý request hay chưa. Không tự giả định nó thành công hoặc thất bại hoàn toàn; thực hiện lookup có kiểm soát (nếu còn quyền), xử lý theo trạng thái server và tránh retry dồn dập.

## 4. Vì sao Vault cấp thời hạn ngắn hơn đề nghị?

Vault có nhiều tầng ràng buộc; tùy loại token/secret và phiên bản cấu hình, tầng giới hạn cụ thể có thể khác nhau.

| Giới hạn/điều kiện | Tác động đến renew | Gợi ý kiểm tra |
| --- | --- | --- |
| **Vault system max TTL** | Đặt một giới hạn trong hệ thống cho một số loại lease/token. | Đối chiếu cấu hình thời hạn của server. |
| **Auth mount/secret mount TTL** | `default_lease_ttl` và `max_lease_ttl` tại mount có thể giới hạn token/secret tương ứng. | Đọc `vault auth tune` hoặc `vault secrets tune` theo quyền. |
| **Role hoặc engine** | Role của AppRole, Database, PKI, secret engine có thể giới hạn TTL/renewability riêng. | Đọc chính role/engine liên quan; không sửa đại trà. |
| **Tuổi thọ tối đa tính từ lúc cấp** | Một lease không được kéo dài vô hạn chỉ bằng các lần renew ngắn. | Kiểm creation time/TTL, max TTL và kết quả lookup. |
| **`explicit_max_ttl` của token** | Với token bị ràng buộc tuổi thọ tuyệt đối, renew phải tôn trọng giới hạn. | `vault token lookup`, cấu hình auth/role. |
| **Token định kỳ (periodic token)** | Có quy tắc renewal theo period riêng, nhưng vẫn có thể bị giới hạn bởi explicit max TTL hoặc revoke. | Xác định token type, period và các giới hạn đang áp dụng. |
| **Secret backend không cho renew** | Lease có thể không renewable hoặc renew bị backend từ chối. | `renewable`, endpoint engine và server audit logs. |
| **Token/lease đã hết hạn hoặc revoke** | Không còn đối tượng hợp lệ để renew. | Lookup hoặc thử operation với quyền phù hợp, kiểm event revoke/expiry. |

Một số thời hạn có thể bị làm tròn hoặc điều chỉnh so với giá trị xin; do đó luôn lấy **kết quả quan sát thực tế** làm cơ sở lập lịch. Không tự động tăng giá trị `increment` cho đến khi được 200: hành vi này có thể làm tăng lỗi, không thay đổi giới hạn tối đa và có thể bị rate limit.

**Phân biệt loại giới hạn:** `default_lease_ttl` là giá trị mặc định khi không có yêu cầu/thiết lập khác; `max_lease_ttl` hoặc max TTL của role/engine là ràng buộc cao hơn. Tuy nhiên, không phải mọi cơ chế dùng các tham số này theo cách giống hệt nhau, nên phải kiểm nghiệm trên engine thực tế.

## 5. Gia hạn **dynamic secret lease** qua Vault CLI và HTTP API

Để kiểm chứng hành vi, sử dụng **Vault thử nghiệm cô lập**, đã enable Database secrets engine với role `orders-read` có quyền cấp credential động. Tình huống này đòi hỏi backend database thật hoặc môi trường test mô phỏng đầy đủ; không tự nhận Vault dev server mặc định đã có Database role.

### 5.1. Quan sát lease khi cấp secret

~~~bash
# VAULT_ADDR, CA và quyền xác thực được cấp an toàn từ môi trường.
# Không hardcode Vault token hay DB password vào source code.
vault read -format=json database/creds/orders-read |
  jq '{
    lease_id: .lease_id,
    lease_duration: .lease_duration,
    renewable: .renewable
  }'
~~~

Lệnh cố ý chỉ hiện metadata. Nếu hệ thống giám sát/log chia sẻ rộng, cũng nên **ẩn hoặc hash lease ID**, vì đó là định danh vận hành có thể liên quan đến quyền revoke/lookup. Phản hồi gốc có thể chứa username/password và không nên được lưu vào file hay log.

Nếu không có `lease_id` hoặc `renewable=false`, không tự đăng ký renew bằng cách suy ID từ đường KV/path. Static KV secret thông thường không có dynamic lease để xin gia hạn.

### 5.2. Gia hạn bằng CLI

~~~bash
# Chỉ dùng lease ID của credential thử nghiệm do bạn sở hữu.
# Ví dụ cố tình dùng placeholder, không chứa secret thật.
vault lease renew -format=json -increment=30m \
  "database/creds/orders-read/<lease-id-test>" |
  jq '{
    lease_id: .lease_id,
    granted_seconds: .lease_duration,
    renewable: .renewable
  }'
~~~

`-increment=30m` là **thời gian đề nghị**. Trường `granted_seconds` trong JSON đã lọc là `lease_duration` mà Vault trả về sau khi xử lý. Nếu lệnh bị lỗi, đọc mã lỗi và phân loại: token không có quyền, lease hết hạn, lease không renewable, sai ID hoặc backend từ chối.

Đọc trạng thái sau gia hạn:

~~~bash
vault lease lookup -format=json \
  "database/creds/orders-read/<lease-id-test>" |
  jq '.data | {
    ttl: .ttl,
    renewable: .renewable,
    expire_time: .expire_time
  }'
~~~

`ttl` từ lookup là **TTL còn lại tại lúc lookup**, vì thời gian đã tiếp tục trôi sau lần renew. Do đó không kỳ vọng `ttl` bằng tuyệt đối `lease_duration` của response trước; có thể nhỏ hơn do độ trễ. Một số trường metadata phụ thuộc bản Vault, policy và loại lease.

### 5.3. Gia hạn bằng API

Endpoint thường dùng cho dynamic lease:

~~~http
PUT /v1/sys/leases/renew
X-Vault-Token: <Vault client token>
Content-Type: application/json

{
  "lease_id": "database/creds/orders-read/<lease-id-test>",
  "increment": 1800
}
~~~

Vault chỉ chấp nhận request khi token/permission đủ điều kiện và lease phù hợp. Response renew thường chứa `lease_id`, `lease_duration` và `renewable`. Tùy API/engine, có thể có thêm `data`; tuyệt đối không ghi toàn bộ response vào log chỉ để tìm TTL.

Ví dụ kiểm tra kết quả mong đợi ở môi trường test:

~~~text
Request increment:    1800 s
Server lease_duration: 900 s
Client next schedule:  dựa trên 900 s và thời điểm nhận response
~~~

Không lấy `increment` làm giá trị TTL mới của lease.

## 6. Gia hạn **Vault client token** là một luồng khác

Vault client token là credential mà Spring Vault dùng để gọi API. Nó có `ttl`, `renewable` và giới hạn riêng. Nó **không có cùng ý nghĩa** với `lease_id` của database dynamic secret.

API token tự renew:

~~~http
POST /v1/auth/token/renew-self
X-Vault-Token: <Vault token đang được gia hạn>
Content-Type: application/json

{
  "increment": 1800
}
~~~

Phản hồi của token renewal thường đặt thời hạn token ở `auth.lease_duration`, không phải luôn ở root `lease_duration` như lease response của secret engine. Một số thông tin khác như `auth.renewable` và metadata token cũng nằm trong đối tượng `auth`.

Đối với token test đang được gắn vào môi trường CLI:

~~~bash
# XÁC NHẬN đang sử dụng token test có thể revoke, không phải root/shared token.
vault token lookup -format=json |
  jq '.data | {
    ttl: .ttl,
    renewable: .renewable,
    explicit_max_ttl: .explicit_max_ttl
  }'

# Renew chính token mà CLI đang dùng, rồi chỉ hiển thị metadata.
vault token renew -format=json -increment=30m |
  jq '.auth | {
    granted_seconds: .lease_duration,
    renewable: .renewable
  }'
~~~

**Lưu ý quan trọng:** `vault token renew` không có token ID thường tác động lên **token hiện tại của CLI**. Nếu `VAULT_TOKEN` hoặc credential helper đang trỏ tới token quản trị/root, bạn sẽ thao tác nhầm token đó. Không dùng token production hoặc shared token để thực hành.

Khi token hết hạn hoặc không renew được, `SessionManager` có thể cần **đăng nhập lại** qua `ClientAuthentication` (Kubernetes JWT, AppRole, GCP workload identity...) nếu cơ chế đang dùng hỗ trợ. `TokenAuthentication` nhận token tĩnh không tự sở hữu cách thay mới credential. Việc đăng nhập lại có thể tạo **token mới** chứ không phải renew token cũ; giám sát và test cần phân biệt hai sự kiện.

## 7. Tính lịch gia hạn từ TTL *thực cấp*

Một quy tắc bảo thủ là lên lịch renew **trước** khi hết hạn, dùng thời hạn mới nhất server trả về và một khoảng dự phòng cho độ trễ mạng/scheduler. Không thể đảm bảo mọi request renew sẽ được chấp nhận, nên khi bị từ chối phải có đường xử lý lỗi.

Giả sử phản hồi renew nhận lúc 13:00:00 với `lease_duration=600` giây. Một chính sách đơn giản đặt cửa sổ an toàn là 20% TTL hoặc tối thiểu 10 giây (với TTL đủ dài). Khi đó thử renew vào khoảng 13:08:00, để lại khoảng 120 giây xử lý lỗi. Đây chỉ là *chính sách ví dụ*; Spring Vault có thể dùng lịch và khoảng dự phòng khác theo phiên bản/cấu hình, không được áp đặt công thức này như lịch mặc định của framework.

### Công thức tham khảo

Với:

- \(t_r\): mốc thời gian nhận phản hồi, được đo bằng đồng hồ monotonic khi có thể.
- \(T_{\mathrm{granted}}\): số giây do Vault trả về.
- \(M\): biên an toàn tối thiểu phù hợp với SLA/network.

Ta có thể đặt:

\[
t_{\mathrm{estimated\ expiry}} \approx t_r + T_{\mathrm{granted}}
\]

và:

\[
t_{\mathrm{next\ renew}} = t_r + \max(0, T_{\mathrm{granted}} - M)
\]

Đây là **ước tính bảo thủ ở phía client**. Server quyết định expiration thực tế; do độ trễ truyền và thời điểm server tính TTL, phải có biên an toàn. Với TTL quá ngắn, không nên đợi gần hết hạn mà cần kiểm tra lại cấu hình role/mount, timeout và tải hệ thống.

### Java: biểu diễn logic lập lịch riêng, có thể unit test

Đoạn sau **không tự gọi Vault** và **không thay thế `SecretLeaseContainer`**. Nó minh họa cách một adapter tùy biến tính khoảng chờ theo TTL *đã được cấp*.

~~~java
import java.time.Duration;

public final class LeaseRenewalSchedule {

    private LeaseRenewalSchedule() {}

    /**
     * grantedTtl lấy từ phản hồi Vault; chỉ gọi cho lease renewable.
     * Trả khoảng trễ từ lúc nhận phản hồi đến khi thử renew tiếp.
     */
    public static Duration nextAttemptAfter(Duration grantedTtl) {
        if (grantedTtl == null || grantedTtl.isZero() || grantedTtl.isNegative()) {
            throw new IllegalArgumentException("Granted TTL must be positive");
        }

        long seconds = grantedTtl.getSeconds();
        if (seconds < 3) {
            return Duration.ZERO; // Không đủ biên an toàn cho scheduler.
        }

        long safetySeconds = Math.max(2, Math.min(60, seconds / 5));
        long delaySeconds = Math.max(0, seconds - safetySeconds);
        return Duration.ofSeconds(delaySeconds);
    }
}
~~~

Với TTL được cấp 600 giây, đoạn code lấy biên an toàn 60 giây (`min(60, 600/5)`), nên trả 540 giây. Với TTL 120 giây, biên an toàn 24 giây, trả 96 giây. Ở ứng dụng thật, cần thêm jitter để tránh nhiều instance renew cùng lúc, giới hạn concurrency, timeout hữu hạn và xử lý khi `renewable=false` hoặc Vault không liên lạc được.

**Không nhầm thời lượng trễ với timestamp tuyệt đối:** sau khi nhận renew response mới, phải cập nhật lại TTL và lịch. Không tiếp tục dùng deadline của phản hồi cũ.

## 8. Tích hợp với Spring Vault: tự quản lý hay dùng SecretLeaseContainer?

### Trường hợp A: `VaultTemplate` đọc secret một lần

~~~java
VaultResponse response =
        vaultTemplate.read("database/creds/orders-read");
~~~

Lệnh gọi này lấy một dynamic credential nếu engine đã được cấu hình. Nhưng **chỉ đọc `VaultResponse` không có nghĩa client đã tự quản lý gia hạn lease**. Ứng dụng cần quyết định ai theo dõi `lease_id`, cập nhật credential, renew/revoke và làm mới kết nối database. Đừng để một task nền tự phát sinh credential mới mỗi vài giây mà không xử lý account cũ.

### Trường hợp B: dùng `SecretLeaseContainer`

Spring Vault cung cấp `SecretLeaseContainer` để quản lý một số requested secrets, phát ra sự kiện về lease và thực hiện các thao tác renewal/rotation theo tính chất secret và cấu hình. Mẫu đăng ký bean minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.core.lease.SecretLeaseContainer;
import org.springframework.vault.core.lease.domain.RequestedSecret;

@Configuration
class VaultLeaseConfig {

    @Bean
    SecretLeaseContainer secretLeaseContainer(VaultTemplate vaultTemplate) {
        SecretLeaseContainer container = new SecretLeaseContainer(vaultTemplate);
        container.addRequestedSecret(
                RequestedSecret.renewable("database/creds/orders-read"));
        return container;
    }
}
~~~

Mẫu này minh họa ý tưởng cho các phiên bản Spring Vault có các API tương ứng. Khi dùng trong dự án, kiểm tra cách bean `SecretLeaseContainer` khởi động/dừng trong Spring context, listener, minimum renewal interval và cách người tiêu thụ nhận credential mới theo phiên bản cụ thể. Nếu Spring Cloud Vault đã tự cấu hình secret lease management, tránh đăng ký hai container quản lý cùng secret mà không có chủ đích.

Một consumer như JDBC pool phải có cơ chế **chuyển sang credential được rotate**; việc `SecretLeaseContainer` nhận sự kiện không tự đảm bảo mọi kết nối DB cũ được thay thế. Với secret không renewable, cơ chế có thể phải xin cấp lại thay vì renew lease cũ.

### Trường hợp C: token lifecycle bằng `SessionManager`

`SessionManager` như `LifecycleAwareSessionManager` quản lý **Vault token** theo cấu hình xác thực. `SecretLeaseContainer` quản lý **secret leases**; hai thứ có tương tác, nhưng không thể thay thế trực tiếp cho nhau. Khi token của parent/session bị revoke, khả năng tồn tại của secret leases liên quan có thể bị ảnh hưởng bởi quan hệ lease/token và cơ chế revocation của Vault.

~~~mermaid
flowchart TD
    A["ClientAuthentication"] --> B["SessionManager: Vault client token"]
    B --> C["VaultTemplate"]
    C --> D["Database secrets engine"]
    D --> E["Dynamic secret + lease_id + lease_duration"]
    E --> F["SecretLeaseContainer hoặc custom lease manager"]
    F --> G["Renew request: increment"]
    G --> H["Vault renew response: actual lease_duration"]
    H --> I["Cập nhật deadline + credential consumer"]
    B --> J["Token renew/reauth độc lập"]
~~~

## 9. Xử lý lỗi: máy chủ cấp ít hơn, từ chối hoặc mất kết nối

| Tình huống | Điều được quan sát | Cách xử lý phù hợp |
| --- | --- | --- |
| Renew 2h, Vault cấp 15m | HTTP thành công; `lease_duration=900`. | Cập nhật TTL/deadline thành 900 giây, tìm giới hạn nếu điều này không phù hợp SLA. |
| Renew trả `renewable=false` | Không thể giả định có lần renew tiếp theo. | Lập kế hoạch cấp credential mới hoặc giảm service nếu không thể thay thế. |
| Renew trả `403 permission denied` | Token chưa đủ quyền, không hợp lệ hoặc lease bị từ chối tùy endpoint. | Phân biệt quyền `sys/leases/renew` với auth/policy và trạng thái lease; không dùng token quyền cao để che lỗi. |
| Renew `404`/invalid lease | Lease ID không tồn tại, đã expire/revoke hoặc sai mount/path. | Đối chiếu nguồn phát hành và lookup (nếu được phép), xin credential mới khi thích hợp. |
| Renew HTTP `5xx` | Lỗi server/backend tạm thời. | Retry có giới hạn, backoff/jitter, theo dõi TTL còn lại; không báo thành công giả. |
| Timeout hoặc kết nối bị từ chối | Không chắc server đã nhận/áp dụng renew. | Kiểm kết nối, lookup có kiểm soát sau khi hồi phục, tránh cấp trùng credential vô hạn. |
| Hết TTL trong lúc Vault outage | Credential có thể mất hiệu lực dù ứng dụng vẫn giữ password trong bộ nhớ. | Chuyển trạng thái degraded, dừng hành động đòi quyền không còn, thử phục hồi/rotate theo quy trình. |
| Context đóng trong lúc renew | Scheduler/job và HTTP request có thể tranh chấp. | Dừng sạch tác vụ mới, đóng tài nguyên, xác minh kết quả revoke nếu có yêu cầu. |

**Lỗi 403 cần phân tách theo endpoint.** `/v1/auth/token/renew-self` liên quan token, `/v1/sys/leases/renew` liên quan lease, `/v1/secret/data/...` là truy cập KV. Lỗi Vault policy hoặc token hết hạn có thể cùng mã HTTP, nhưng hành động khắc phục khác nhau.

Khi lấy lại credential sau khi renew thất bại, cần tránh cắt kết nối hiện tại trước khi credential mới được xác minh hoạt động. Với database pool, có thể cần giai đoạn chuyển tiếp để đóng dần connection cũ và tạo connection mới; với TLS client certificate, cần reload `SSLContext`/keystore hoặc rolling restart, đồng thời kiểm thời hạn chứng chỉ độc lập.

## 10. Thực hành phân tích TTL theo timeline

Xét lease cấp tại 09:00 với TTL ban đầu 1.200 giây. Ứng dụng bắt đầu dùng credential, rồi có hai lần renew:

| Thời điểm | Operation | Mong muốn | Vault trả | Hạn dự kiến từ kết quả mới |
| --- | --- | --- | --- | --- |
| 09:00 | Cấp lease | Xin credential DB | `lease_duration=1200` (20m) | 09:20 |
| 09:12 | Renew A | `increment=3600` (60m) | `lease_duration=900` (15m) | Khoảng 09:27 |
| 09:23 | Renew B | `increment=3600` (60m) | `lease_duration=240` (4m) | Khoảng 09:27 |
| 09:25 | Lookup | Đo TTL còn lại | `ttl≈120` | Khoảng 09:27 |
| 09:27 | Expiry | Không gia hạn được tiếp | Lease hết hạn | Phải xin cấp mới theo engine |

Bảng là **tình huống giả định** có giờ được làm tròn. TTL server trả là số giây tương đối từ thời điểm xử lý/đáp ứng; thời hạn thực tế có thể lệch vì độ trễ, lịch xử lý hoặc cơ chế backend. Điều đáng chú ý: **renew B thành công nhưng không đẩy expiry vượt mốc 09:27**. Đây là dấu hiệu có thể đã gặp giới hạn tuổi thọ tổng thể; cần đối chiếu dữ liệu thật mới kết luận được nguyên nhân.

### Ba câu hỏi chẩn đoán

1. Máy khách có đang tính deadline bằng `requested increment` thay vì `granted lease_duration` không?
2. Token dùng để renew còn hiệu lực, có quyền và có bị giới hạn max TTL/role không?
3. Lease này có thật sự renewable trong engine và vẫn được backend chấp nhận không, hay cần phát hành credential mới?

Nếu chỉ nhìn HTTP 200 và tưởng renew luôn kéo dài 60 phút, hệ thống có thể tiếp tục dùng password DB sau khi backend đã thu hồi, dẫn tới lỗi xác thực đột ngột.

## 11. Kiểm thử tích hợp: phải xác minh TTL thực cấp

### Tầng unit test: phản hồi giả

Dùng một giả lập cho API renew với:

~~~json
{
  "lease_id": "database/creds/orders-read/<lease-id-test>",
  "renewable": true,
  "lease_duration": 240
}
~~~

Giả sử client đã yêu cầu `increment=3600`. Assertion đúng là **lịch mới dựa vào 240 giây** (với biên an toàn), không phải 3.600 giây.

Ví dụ test Java cho hàm tính lịch ở phần 7:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Duration;
import org.junit.jupiter.api.Test;

class LeaseRenewalScheduleTest {

    @Test
    void usesGrantedTtlRatherThanRequestedIncrement() {
        // Request giả định: increment=3600; server chỉ cho 600 giây.
        Duration grantedByServer = Duration.ofSeconds(600);

        assertEquals(
                Duration.ofSeconds(540),
                LeaseRenewalSchedule.nextAttemptAfter(grantedByServer));
    }

    @Test
    void rejectsAbsentOrInvalidTtl() {
        assertThrows(IllegalArgumentException.class,
                () -> LeaseRenewalSchedule.nextAttemptAfter(Duration.ZERO));
    }
}
~~~

Đây chỉ là test helper lập lịch; để kiểm thử client hoàn chỉnh phải xác minh khâu parse response, update deadline, đổi trạng thái `renewable` và lỗi timeout. Không coi `LeaseRenewalSchedule` là API có sẵn của Spring Vault; nó là lớp minh họa tự tạo trong bài.

### Tầng integration: Vault + engine thật

Tạo môi trường staging/test có Database secrets engine kết nối một DB thử nghiệm, role cấp credential với TTL thấp và chính sách renewal rõ ràng. Các bước:

1. Dùng workload/token **chỉ trong test** đọc `database/creds/orders-read`, lưu metadata lease trong bộ nhớ và kiểm tra account DB có hoạt động.
2. Gọi renew với `increment` lớn hơn giới hạn được cấu hình cho backend; đọc lại `lease_duration` thực cấp.
3. Dùng lookup và polling có deadline để xác minh TTL còn lại, không dùng `Thread.sleep` cứng như nguồn chân lý.
4. Làm mới credential/connection pool trước khi lease thực sự hết hạn; khi cần, kiểm tra account cũ bị backend thu hồi theo thiết kế.
5. Test riêng nonrenewable, token hết hạn/revoke, backend không sẵn sàng, HTTP `5xx`/timeout, lỗi quyền policy và shutdown.
6. Dọn lease/account/test role sau khi kết thúc, không để tài nguyên DB thử nghiệm tồn tại ngoài ý muốn.

Đừng giảm TTL hoặc revoke token production để thử. Dùng dữ liệu không nhạy cảm, Vault riêng và DB riêng. Khi định nghĩa thời gian kiểm thử, kiểm tra TTL thực tế được cấp ở lần đầu; Vault có thể áp dụng giới hạn khác giá trị mong muốn của role.

### Ma trận xác nhận

| Test | Request | Kỳ vọng cần assert |
| --- | --- | --- |
| Gia hạn được toàn bộ khoảng đề nghị | `increment=300s` | `lease_duration` thực trả và deadline tương ứng; không cần bằng tuyệt đối 300s nếu server điều chỉnh. |
| Gia hạn bị giới hạn | `increment=3600s` | TTL cấp nhỏ hơn mong muốn; client lưu TTL thực cấp. |
| Renew gần max TTL | Yêu cầu lớn khi thời gian còn ít | Có thể còn TTL ngắn/renew bị từ chối; không vòng lặp xin tăng vô hạn. |
| Lease `renewable=false` | Cố renew lease không renewable | Lỗi được báo rõ; ứng dụng chuẩn bị lấy credential mới. |
| Token dùng renew hết hạn | Renew secret lease | Trước hết xử lý token/session; không mặc định secret đã hết hạn cùng lúc. |
| Mất mạng sau khi gửi renew | Timeout | Xử lý trạng thái không chắc chắn, tra cứu lại khi an toàn. |
| Dynamic credential bị revoke | Renew và sử dụng DB | Lease/credential cũ bị từ chối; consumer xử lý rotation. |
| `ApplicationContext.close()` | Đóng Spring context khi scheduler hoạt động | Dừng task mới; tài nguyên đóng, không để retry tiếp sau shutdown. |

## 12. Vận hành và giám sát sự chênh lệch TTL

Không log credential, client token, secret payload hoặc private key. Chỉ quan sát metadata đủ để phát hiện sự cố:

| Metric/sự kiện gợi ý | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| `vault_lease_renew_requested_seconds` | Khoảng gia hạn client đề nghị. | So với TTL máy chủ thực cấp. |
| `vault_lease_renew_granted_seconds` | TTL từ response renew. | Là đầu vào cho lập lịch mới. |
| `vault_lease_remaining_seconds` | TTL còn lại tại lúc lookup/quan sát. | Cảnh báo khi dưới ngưỡng xoay credential. |
| `vault_lease_renew_failure_total` | Renew lỗi theo nguyên nhân/engine. | Phát hiện retry loop, quyền sai, outage. |
| `vault_token_renew_failure_total` | Lỗi gia hạn token riêng. | Phân biệt với lỗi secret lease. |
| `vault_secret_rotation_success_total` | Consumer đã dùng credential mới. | Tránh “đã nhận secret mới” nhưng pool chưa reload. |
| `vault_lease_expired_before_refresh_total` | Credential hết hạn trước khi được thay. | Báo lỗi về lịch renew/rotation hoặc outage. |

Đây là **tên metric đề xuất**, không phải metric mặc định mà Spring Vault chắc chắn xuất ra. Nên phân tách nhãn theo service, engine, loại operation và kết quả; không dùng `lease_id` nguyên văn hoặc token làm label gây rủi ro lộ metadata và cardinality cao.

Một quy tắc cảnh báo hữu ích là **tỷ lệ TTL thực cấp/thời gian đề nghị giảm liên tục** hoặc nhiều lần renew thành công nhưng deadline không tiến lên. Tình huống này có thể dự báo sắp chạm max TTL hoặc thay đổi chính sách backend, và là thời điểm chuẩn bị cấp credential mới.

### Retry và SLA

- Chỉ retry có giới hạn các lỗi có khả năng hồi phục như network hoặc 5xx; dùng backoff và jitter.
- Với `renewable=false`, sai lease ID, bị revoke hoặc policy 403, ưu tiên khôi phục đúng nguồn và cấp credential mới theo quyền được phép.
- TTL thực cấp quá ngắn cần được so với thời gian nhận credential mới, thời gian kết nối lại DB, độ trễ TLS và lịch triển khai. Nếu TTL nhỏ hơn thời gian phục hồi cần thiết, một vòng renew “thành công” vẫn không đủ đảm bảo sẵn sàng.
- Khi shutdown, dừng scheduler/`SecretLeaseContainer` đúng lifecycle; việc revoke token/lease phải tuân quyền sở hữu để tránh vô tình thu hồi credential được chia sẻ.

## 13. Lỗi thường gặp và cách sửa

**Lỗi 1 – Dùng giá trị `increment` làm TTL được cấp.** Client xin 1 giờ rồi đặt cache sống thêm 1 giờ mặc dù Vault chỉ cho 10 phút. Cách sửa: parse `lease_duration` từ renew response và lập lại lịch theo TTL mới.

**Lỗi 2 – Chỉ đọc cờ `renewable`.** Cờ `true` không đảm bảo quyền renew vẫn còn hoặc chưa chạm max TTL. Cách sửa: kiểm tra cả kết quả API renew, TTL thực trả và tình trạng token/backend.

**Lỗi 3 – Nhầm token renew với secret lease renew.** Client renew Vault token qua `auth/token/renew-self` rồi tiếp tục dùng mật khẩu DB đã bị revoke. Cách sửa: quản lý riêng lifecycle token và từng dynamic secret lease, kiểm tra credential ở consumer.

**Lỗi 4 – Đọc static KV như dynamic lease.** Một lần `VaultTemplate.read("secret/data/...")` không đồng nghĩa có lease renewable. Cách sửa: kiểm tra `lease_id`/`renewable` của engine thực, dùng rotation/versioning cho static secret.

**Lỗi 5 – Cho rằng HTTP timeout tức là renew bị từ chối.** Vault có thể đã xử lý request trước khi client mất kết nối. Cách sửa: xử lý trạng thái chưa xác định, lookup khi đủ quyền/đường mạng và hạn chế retry.

**Lỗi 6 – Chỉ đo thành công của renew, không đo deadline.** Server có thể trả 200 nhưng TTL giảm dần vì max TTL. Cách sửa: quan sát granted TTL và dự kiến expiration sau mỗi lần renew.

**Lỗi 7 – Không cập nhật consumer khi có secret mới.** Agent/`SecretLeaseContainer` đã cấp credential khác nhưng JDBC pool hay TLS runtime còn dùng credential cũ. Cách sửa: đăng ký event/refresh phù hợp, test kết nối mới thực sự dùng bản mới.

## 14. Checklist áp dụng trong dự án

Trước khi vận hành, đội phát triển cần xác nhận được:

1. **Đúng đối tượng:** đang renew Vault token hay dynamic secret lease? Static secret có thực sự có lease không?
2. **Đúng định danh:** có `lease_id` thật từ engine và quyền renew phù hợp hay không?
3. **Đúng trường phản hồi:** đọc `auth.lease_duration` cho token response và `lease_duration` cho secret lease response theo API thực tế.
4. **Đúng thời hạn:** lịch được tính theo TTL thực cấp và thời điểm nhận response, có buffer/timeout/jitter.
5. **Đúng giới hạn:** đã kiểm system/mount/role/backend TTL và hiểu điều kiện renewable, max TTL, expiration.
6. **Đúng consumer:** password DB, kết nối pool hoặc cert/key đã được rotate/reload khi cần.
7. **Đúng phản ứng lỗi:** phân loại lỗi network, HTTP 403, lease không renewable, đã revoke, max TTL; không retry mù.
8. **Đúng quyền:** token/session dùng policy tối thiểu, không mở root/wildcard chỉ để gia hạn.
9. **Đúng quan sát:** có log/metric được lọc, có bằng chứng server cấp TTL nào mà không lộ secret/token.
10. **Đúng kiểm thử:** thử cả trường hợp server cấp đủ, cấp ít hơn, từ chối và mất kết nối; kiểm tra `ApplicationContext` dừng task nền.

**Kết luận:** trong Spring Vault, `increment` là **yêu cầu** gia hạn của client; `lease_duration`/`ttl` máy chủ trả là **kết quả thực tế** cần sử dụng. Khi phân biệt rõ token và secret lease, đọc lại phản hồi sau mỗi lần gia hạn, kiểm soát giới hạn TTL và đảm bảo consumer thay credential trước khi hết hạn, ứng dụng Java có thể dùng KV, Database, Transit và PKI ổn định hơn mà vẫn tôn trọng chính sách Vault và vòng đời credential.
