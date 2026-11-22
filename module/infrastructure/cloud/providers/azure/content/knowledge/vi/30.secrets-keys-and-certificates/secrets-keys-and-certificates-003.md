# Secret version, hạn sử dụng và chiến lược luân chuyển

Một ứng dụng Spring Boot chạy trên Azure Container Apps cần gọi API của đối tác thanh toán. API yêu cầu một client secret được lưu trong **Azure Key Vault**. Hôm nay đội an ninh tạo secret mới và đánh dấu secret cũ hết hạn sau 60 ngày. Tuy nhiên một số container vẫn dùng credential cũ do cache; một số job lại gắn cứng URL chứa version ID cũ; sau khi đối tác vô hiệu hóa credential cũ, ứng dụng bắt đầu gặp lỗi `401 Unauthorized`. Đội vận hành thử cập nhật secret thêm lần nữa nhưng sự cố không hết.

Đây không chỉ là bài toán “đổi chuỗi bí mật”. **Luân chuyển secret** là một quá trình có nhiều trạng thái, liên quan đến **nguồn phát hành credential**, **phiên bản của secret trong vault**, **thời gian hiệu lực**, **cách ứng dụng lấy và cache giá trị**, **thứ tự triển khai**, **khả năng rollback** và **giám sát hậu triển khai**.

Một kiến trúc đáng tin phải trả lời:

1. **Giá trị secret hiện hành là phiên bản nào?** Ứng dụng gọi theo tên hay version ID cố định?
2. **Secret có thể dùng tới khi nào?** Trường `expiresOn` trong Key Vault có đồng bộ với hạn thật của credential tại hệ thống đích không?
3. **Ai sinh credential mới?** Key Vault lưu giá trị nhưng thường không có quyền tự thay credential ở hệ thống đối tác.
4. **Consumers chuyển sang giá trị mới thế nào?** Re-fetch, refresh, restart, rolling deployment hay cấu hình đồng bộ?
5. **Có thể giữ hai credentials cùng có hiệu lực tạm thời không?** Nếu không, phải chọn quy trình downtime/atomic cutover phù hợp.
6. **Khi gặp lỗi có thể quay lại bản cũ không?** Nếu bản cũ đã bị thu hồi ở nguồn, “rollback version trong vault” cũng không thể hồi sinh nó.

Ví dụ kiến trúc:

```text
                  NGUỒN CREDENTIAL
          API provider / Database / Identity provider
                       |
                Generate new credential
                       |
                       v
                ROTATION WORKFLOW
          policy → validate → publish → rollout
                       |
                       v
               AZURE KEY VAULT
          secret "partner-api-credential"
                 ├── version A (old)
                 └── version B (new)
                       |
            +----------+----------+
            |                     |
            v                     v
       App Service             Container Apps
       Key Vault ref           Java SecretClient
       refresh/restart         refresh/cache TTL
            |                     |
            +----------+----------+
                       |
                       v
            Authenticate with upstream
                       |
               Verify → retire old
```

Bài thuộc chương **Secret, khóa và chứng chỉ**, trong module `CLOUD_PROVIDERS_AZURE`. Module khảo sát hệ sinh thái Microsoft Azure từ subscription, resource group, Microsoft Entra ID, mạng ảo, tính toán, lưu trữ và dữ liệu tới triển khai, giám sát, bảo vệ và kiểm soát chi phí. Vì thế nội dung đặt **secret lifecycle** trong toàn bộ ứng dụng và quy trình vận hành Azure, không chỉ hướng dẫn một lệnh tạo secret.

> **Phạm vi:** Azure Key Vault **Secrets** là chủ đề chính. **Keys** và **Certificates** có cơ chế và chính sách rotation/renewal riêng, không được đánh đồng. Những API, event types, hạn mức, chu kỳ refresh của App Service/AKS và khả năng tự động hóa có thể thay đổi theo sản phẩm, phiên bản SDK và cấu hình. Kiểm tra tài liệu và thử nghiệm trên vault lab trước khi áp dụng vào Production. Tất cả tên vault/secret, thời gian và credential trong ví dụ đều giả lập; không dùng secret thật trong terminal, tài liệu, logs hoặc Git.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích secret, secret name, value, version ID, attributes, tags và secret identifier.
2. Phân biệt truy xuất **versionless** với truy xuất **version-pinned** và tác động của caching.
3. Mô tả `enabled`, `notBefore`, `expiresOn` và giá trị hạn thực tế của credential tại upstream.
4. Giải thích vì sao **đặt hạn sử dụng không đồng nghĩa tự động luân chuyển hay thu hồi**.
5. Thiết kế **rotation interval, lead time, overlap window, rollback window, max secret age và emergency revocation**.
6. So sánh **dual-credential rotation**, **single-credential cutover** và **dynamic/short-lived credentials**.
7. Thiết kế automation với **Event Grid, Azure Functions, scheduler và Key Vault**.
8. Dùng **managed identity/Entra RBAC** để consumers và rotation worker chỉ có quyền tối thiểu.
9. Thực hiện quy trình create new version → rollout → verify → disable/revoke old theo đúng thứ tự.
10. Xử lý App Service Key Vault references, AKS Secrets Store CSI, Spring Boot/Java SDK và các loại consumer cache.
11. Quản lý secrets bị lộ, phiên bản đã hết hạn, quyền truy cập bị từ chối và lỗi cache phiên bản.
12. Đọc **metadata phiên bản** bằng Azure CLI/Java SDK mà không lộ secret values.
13. Dựng alerts, audit, runbooks và kiểm soát soft delete/purge protection.
14. Hoàn thành bài lab rotation có kiểm thử thành công, lỗi và rollback.

## 2. Secret trong Azure Key Vault là gì?

Một **Key Vault secret** là giá trị cần bảo mật được lưu dưới một **tên**; mỗi lần đặt một giá trị mới dưới tên đó có thể tạo một **phiên bản mới**. Ví dụ:

```text
Vault:
  kv-orders-prod

Secret name:
  partner-api-credential

Versions:
  7b9... (created first, value A)
  a61... (created later, value B)

Application:
  uses "partner-api-credential"
  → resolves to a suitable version through data-plane API/reference
```

Các loại dữ liệu thường được lưu dưới dạng secret:

- API token/credential cấp bởi một nhà cung cấp bên ngoài.
- Password của hệ thống chưa hỗ trợ Entra/managed identity.
- Client secret cho hệ thống legacy.
- Shared credential theo hợp đồng tích hợp.
- Một số chuỗi cấu hình nhạy cảm không có cơ chế passwordless tương ứng.

**Key Vault Secrets không phải cơ sở dữ liệu config tùy ý**. Dữ liệu không nhạy cảm như feature flags nên cân nhắc App Configuration hoặc configuration store phù hợp. Nếu có thể **loại bỏ bí mật** bằng managed identity/workload identity, đó thường là bước bảo mật tốt hơn việc liên tục quản lý một mật khẩu dài hạn.

## 3. Phân biệt Secrets, Keys và Certificates

| Đối tượng Key Vault | Giá trị/khả năng | Đặc điểm rotation |
|---|---|---|
| **Secret** | Giá trị bí mật như password/token, tiêu thụ bằng ứng dụng/SDK. | Tạo version mới của giá trị và đồng bộ với hệ thống nguồn; automation thường do ứng dụng/rotation worker triển khai. |
| **Key** | Khóa mật mã cho thao tác encrypt/decrypt/sign/verify theo loại key. | Có **key rotation policy**/cơ chế versioning riêng tùy loại vault/key/tính năng. |
| **Certificate** | Chứng chỉ TLS, cùng metadata/policy và các thành phần liên quan. | Có chính sách issuance/renewal/integration và vòng đời CA/chứng chỉ riêng. |

Một certificate được quản lý qua Key Vault có thể có **secret backing chứa nội dung chứng chỉ**, nhưng **đổi một secret tùy ý không tương đương gia hạn chứng chỉ từ CA**.

Một cryptographic key có thể cho phép dùng nhiều key versions để giải mã dữ liệu cũ. Với password/API token, phiên bản cũ thường phải bị **thu hồi tại hệ thống xác thực gốc**. Không copy rotation policy dành cho keys sang secrets mà không hiểu sự khác biệt.

## 4. Secret name, version và identifier

Một secret có tên logic ổn định và các versions riêng:

```text
https://kv-orders-prod.vault.azure.net/secrets/partner-api-credential
                                   ↑          ↑
                                /secrets/    secret name

https://kv-orders-prod.vault.azure.net/secrets/partner-api-credential/a61...
                                                                  ↑
                                                             version ID
```

| Thành phần | Ý nghĩa |
|---|---|
| **Vault URI** | Endpoint của Key Vault, gắn với môi trường/tenant và network path. |
| **Secret name** | Định danh logic ổn định cho credential trong vault. |
| **Version identifier** | Định danh một snapshot giá trị secret tại thời điểm được tạo. |
| **Versionless identifier** | URI theo tên, không chỉ rõ version ID. |
| **Versioned identifier** | URI gồm tên và version ID, chỉ đích danh phiên bản. |
| **Secret value** | Dữ liệu mật; không xuất hiện trong URI và không được log. |
| **Secret properties** | Attributes và metadata như enabled/notBefore/expiresOn, content type, tags. |

**Version ID không phải secret value.** Tuy nhiên full identifier có thể tiết lộ tên hệ thống/vault/credential, nên không đưa vào log public nếu chính sách tổ chức cấm. Không coi version ID là quyền truy cập; ứng dụng vẫn phải được xác thực/ủy quyền.

## 5. Vòng đời một secret version

Tình huống đơn giản:

```text
Provision external credential A
        |
        v
Publish Key Vault version A
        |
        v
Active (consumer uses A)
        |
        v
Rotation preparation
        |
        v
Provision credential B at upstream
        |
        v
Publish Key Vault version B
        |
        v
Consumers migrate and validate B
        |
        +-- Success → disable/revoke A after overlap window
        |
        +-- Failure → pause, fix or rollback while A still valid
        |
        v
Retain metadata/audit under retention policy
```

**Hai vòng đời phải đồng bộ**:

1. Phiên bản lưu ở **Key Vault**.
2. Credential được **hệ thống đích** chấp nhận.

Một phiên bản B mới trong Key Vault chưa chắc đã được API partner chấp nhận, chẳng hạn do key chưa kích hoạt. Ngược lại, credential B đã tồn tại ở upstream nhưng chưa được publish đúng vault khiến ứng dụng không thể dùng.

## 6. Tạo version mới có ghi đè version cũ không?

Thông thường, việc đặt một **giá trị mới cho cùng secret name** thông qua API `setSecret` tạo một **new secret version**. Version cũ vẫn là phiên bản riêng theo vòng đời và chính sách lưu giữ của vault, chứ không bị ghi đè giá trị.

```text
T0: setSecret("partner-api-credential", "A")
    → version v1

T1: setSecret("partner-api-credential", "B")
    → version v2

v1.value = "A"  (giá trị cũ)
v2.value = "B"  (giá trị mới)
```

**Giá trị secret của một version không được sửa tại chỗ** theo cách “đổi A thành B trong v1”. Khi cần thay giá trị, tạo version mới.

Nhưng metadata/attributes của **một version** có thể được cập nhật theo API và quyền tương ứng, ví dụ thay đổi `enabled` hoặc `expiresOn`. Điều này **không tạo credential mới ở upstream**.

### Hệ quả cho audit

Phân biệt:

- “**Thêm secret version**”: một giá trị mới được publish.
- “**Update secret properties**”: một số metadata đổi.
- “**Revoke upstream credential**”: secret thật ngừng được hệ thống đích chấp nhận.
- “**Delete/purge secret**”: thao tác xóa tài nguyên trong vault, không phải bước luân chuyển mặc định.

## 7. Versionless và version-pinned access

**Versionless:**

```text
.../secrets/partner-api-credential
```

**Version-pinned:**

```text
.../secrets/partner-api-credential/<exact-version-id>
```

| Cách dùng | Ưu điểm | Nguy cơ |
|---|---|---|
| **Versionless / get by name** | Consumer có thể lấy phiên bản mới mà không đổi secret URI/config. | Cần quản lý cache/refresh, xác thực behavior khi latest version disabled/invalid. |
| **Version-pinned / get by name + version** | Tái lập cấu hình; xác minh chính xác phiên bản theo release. | Không tự chuyển sang version mới; rotation phải update deployment/config. |
| **Versionless nhưng app cache vô hạn** | Tránh request tới vault sau startup. | Thực tế vẫn dùng giá trị cũ; versionless URL không tự làm bộ nhớ cập nhật. |
| **Version-pinned theo release/canary** | Có thể xác minh v2 trên tập consumer nhỏ. | Nếu v1 bị revoke trước khi đổi tất cả deployments, phần còn lại sẽ fail. |

**Không mặc định versionless secret sẽ tự fallback về một version cũ đang enabled** nếu newest version có vấn đề. Hành vi select/version eligibility phải được kiểm chứng với dịch vụ/API/consumer cụ thể; workflow tốt nhất là **không publish bản chưa được kiểm tra**.

## 8. Version identifier trong ứng dụng

Một ứng dụng Java dùng Key Vault SDK có thể gọi:

```java
KeyVaultSecret current = secretClient.getSecret("partner-api-credential");
// Truy xuất theo tên, không chỉ rõ version.

KeyVaultSecret specific = secretClient.getSecret(
    "partner-api-credential", "REPLACE_WITH_VERSION_ID");
// Truy xuất một version cụ thể.
```

Hai lời gọi trên **đều yêu cầu data-plane permission phù hợp**. Không in `current.getValue()` hoặc `specific.getValue()` ra console.

Khi triển khai canary, có thể pin version B ở environment staging hoặc một số replicas để kiểm chứng; khi Production cutover xong, chọn trở lại versionless nếu đó là chiến lược ứng dụng được duyệt. Đừng trộn pin/versionless không được tài liệu hóa giữa các service instances.

## 9. Attributes: enabled, notBefore và expiresOn

Ba thuộc tính thường gặp:

| Thuộc tính | Ý nghĩa thực tế | Điều không nên suy luận |
|---|---|---|
| **`enabled`** | Metadata/bật-tắt khả năng sử dụng một version theo semantics Key Vault. | Không đồng nghĩa credential bên upstream bị thu hồi. |
| **`notBefore`** | Thời điểm version bắt đầu có hiệu lực theo chính sách/vault semantics. | Không bảo đảm consumer đã sẵn sàng dùng tại thời điểm đó. |
| **`expiresOn`** | Thời điểm hết hạn được gắn cho version, hỗ trợ quản trị/truy xuất và các cơ chế cảnh báo theo dịch vụ. | Không tự sinh version mới và không tự đổi password ở upstream. |

Lưu ý các SDK/CLI có thể hiển thị các thời điểm dưới dạng UTC/ISO hoặc timestamp; ứng dụng nên giữ **UTC**, không so sánh ngày theo múi giờ máy chủ tùy ý.

Không tự hạ bật/tắt/expiry metadata thành “bảng boolean” rồi coi nó là sự thật duy nhất: authentication của API provider và trạng thái session/connection của consumer cũng quan trọng.

### Content type và tags

Secret properties còn có thể có `contentType` và `tags`:

- Content type có thể ghi kiểu dữ liệu khái quát.
- Tags hỗ trợ owner, hệ thống, rotation policy ID, environment và ticket reference.

**Không ghi password/token hoặc PII vào tags**; metadata thường dễ bị liệt kê hơn secret value và có chính sách log khác.

## 10. Expiration metadata không tự luân chuyển credential

Đây là điểm quan trọng nhất.

```text
Secret.version A:
  expiresOn = 2027-01-20T00:00:00Z

Không đồng nghĩa:
  - Azure tự đổi API key bên đối tác lúc đó
  - Azure tự tạo version B với giá trị hợp lệ
  - Spring Boot tự đọc version B
  - Consumer sessions lập tức ngừng dùng A
  - API provider đã revoke A
```

**Hạn sử dụng trong Key Vault** là một phần vòng đời của **secret object/version**; **hạn thật của credential ở hệ thống nguồn** có thể độc lập. Việc vault/API cho phép hay từ chối đọc một version quanh `notBefore/expiresOn/enabled` cần tuân theo hành vi sản phẩm cụ thể, nhưng **không được coi metadata đó là phương pháp duy nhất thu hồi một credential đã phát ra ngoài**.

Nếu đối tác vô hiệu hóa credential A, một ứng dụng còn giữ A trong memory không thể “cứ đọc cache tiếp” để gọi API thành công. Ngược lại, nếu một version bị disable trong vault, một client đã lấy được giá trị và còn credential hợp lệ ở upstream có thể tiếp tục dùng bản sao trong memory cho tới khi credential thực bị thu hồi hoặc session bị cắt.

**Thu hồi cần thực hiện ở nơi xác thực credential**, cùng quy trình kiểm soát consumer đang online.

## 11. Hai đồng hồ: vault expiry và upstream validity

Tưởng tượng:

```text
Key Vault version A:
  expiresOn = 2027-01-20T00:00Z

Partner API credential A:
  upstream expiration = 2027-01-10T00:00Z

Application:
  reload interval = 24 hours
```

Nếu chỉ nhìn `expiresOn` trong vault, ứng dụng có thể mất quyền từ **ngày 10/01**, trước mốc trên vault. Chiều ngược lại, metadata trên vault có thể hết hạn trước khi upstream vô hiệu hóa credential.

Mẫu dữ liệu quản trị nên có:

| Trường | Nguồn |
|---|---|
| Secret name/version | Key Vault metadata. |
| Credential provider/account | Registry tích hợp/owner. |
| Upstream validUntil | API provider/issuer contract. |
| Vault expiresOn | Key Vault secret attributes. |
| Rotation window | Chính sách nội bộ, có lead time. |
| Consumer refresh interval | App Service/AKS/SDK implementation. |
| Revocation date | Quy trình cutover có audit. |
| Last validation | Synthetic test/health telemetry. |

**Không dùng một trường expiry duy nhất làm bằng chứng credential còn hữu hiệu hoặc consumer đã chuyển phiên bản.**

## 12. Hạn sử dụng, TTL và thời gian cache là ba thứ khác nhau

Phân biệt:

- **Credential lifetime:** upstream chấp nhận giá trị trong bao lâu?
- **Key Vault version expiry:** metadata thời gian quản lý một secret version.
- **Consumer cache TTL/refresh cadence:** thời gian app giữ bản sao trước khi yêu cầu lại.
- **Token/session lifetime:** một token được sinh từ credential có thể có hạn độc lập.
- **Secret rotation interval:** khoảng cách giữa các lần cấp credential mới.
- **Overlap window:** khoảng thời gian credential cũ và mới cùng có thể được dùng.

Ví dụ:

```text
Rotation every 30 days
Credential expires after 60 days
Consumer reload every 15 minutes
Overlap after publish 48 hours
```

Đây là **chính sách ví dụ**, không phải cấu hình mặc định hay khuyến nghị chung của Microsoft. Thời lượng thực phụ thuộc rủi ro, provider, lượng replicas, mức độ offline và khả năng rollback.

### Đừng dùng TTL như authorization policy

Một cache giữ secret 15 phút không thay thế việc thu hồi credential tại upstream khi có lộ lọt. TTL chỉ giới hạn tốc độ nhận giá trị mới nếu hệ thống refresh đúng.

## 13. Lập lịch rotation dựa trên rủi ro

Không phải mọi secret cần đổi cùng chu kỳ. Xây một bảng risk-based:

| Credential | Tác động khi lộ | Khả năng dual-key | Chiến lược |
|---|---|---|---|
| API key đọc dữ liệu công khai từ provider | Thấp–trung bình. | Có thể. | Định kỳ và đo adoption. |
| Token ghi vào hệ thống thanh toán | Cao. | Tùy provider. | Chu kỳ ngắn hơn, approval, anomaly monitoring. |
| Password DB legacy | Cao nếu chia sẻ rộng. | Có thể có dual user hoặc không. | Rotation có kế hoạch, test connection pools và rollback. |
| Signing secret webhook | Rủi ro giả mạo nếu lộ. | Thường cần chấp nhận nhiều keys/versions tạm thời. | Key IDs, verify dual signature trong overlap. |
| Service principal client secret | Rủi ro giả mạo ứng dụng. | Có thể nhiều credentials đồng thời theo nền tảng. | Ưu tiên managed identity; nếu còn cần thì dual credential có lịch. |
| Secret lab ngắn hạn | Thấp khi giả lập. | Có. | TTL ngắn, tự cleanup theo policy. |

Chính sách nên tính:

- Mức độ dữ liệu và hành động mà credential cho phép.
- Khả năng phát hiện compromise.
- Số consumers, môi trường và vị trí.
- Khả năng provider cấp đồng thời nhiều credentials.
- Điều kiện SLA/downtime/rollback.
- Yêu cầu pháp lý/hợp đồng.
- Chi phí API và vận hành rotation.
- Thời gian triển khai và cache dài nhất.
- Mức sẵn sàng của automation và human approval.

**Rotation quá thường xuyên nhưng automation không đáng tin có thể tăng downtime**. Bài toán là giảm rủi ro tổng thể, không chỉ giảm số ngày tồn tại của secret trên giấy.

## 14. Tính lead time và rotation deadline

Giả sử credential upstream hết hạn tại `E`, các khoảng:

- `T_provision`: tạo/duyệt credential mới.
- `T_rollout`: thời gian triển khai đến mọi consumers.
- `T_verify`: kiểm thử, đối soát và phát hiện lỗi.
- `T_buffer`: dự phòng cho sự cố hoặc ngày nghỉ.

Cần bắt đầu muộn nhất trước:

```text
Rotation start deadline =
  upstream expiry
  - T_provision
  - T_rollout
  - T_verify
  - T_buffer
```

Ví dụ nội bộ:

```text
Credential expiry: T0 + 60 days
Provision/approval: 2 days
Rollout max: 1 day
Verification: 1 day
Buffer: 7 days

Start no later than day 49.
```

**Đây là bài toán lập kế hoạch**, không phải giá trị mặc định của Key Vault. Với hệ thống rủi ro cao, có thể yêu cầu hoàn tất cutover sớm hơn để không sát hạn.

## 15. Dual-credential rotation: ưu tiên khi upstream hỗ trợ

Khi provider cho phép hai credentials cùng hiệu lực:

```text
T0: Credential A valid, app uses A
T1: Create B at provider; A still valid
T2: Store B as new Key Vault version
T3: Canary with B; A still valid
T4: Rollout/reload all consumers to B
T5: Verify traffic uses B, no auth failures
T6: Revoke A at provider
T7: Disable old Key Vault version / retain under policy
```

**Ưu điểm**:

- Rollout ít hoặc không gián đoạn.
- Có thể canary và rollback trong thời gian overlap.
- Ứng dụng có thể chuyển từ A sang B theo từng replica.
- Có thời gian kiểm tra dependency ngoài dự kiến.

**Đánh đổi**:

- Tạm thời tồn tại **hai credentials hợp lệ**; phải bảo vệ và audit cả hai.
- Cần biết consumer nào còn dùng A.
- Provider có thể giới hạn số active keys.
- Nếu B publish quá sớm và consumer tự refresh khi chưa được kiểm thử, sẽ gây rủi ro.

**Không revoke A chỉ vì đã tạo version B trong vault.** Phải có bằng chứng các consumers đã chuyển và upstream chấp nhận B.

## 16. Single-credential cutover: khi không có overlap

Một số hệ thống chỉ cho phép một password/API token active tại một thời điểm:

```text
Old A valid
   |
   v
Maintenance window / quiesce traffic
   |
   v
Change upstream credential A → B
   |
   v
Publish B to vault + force reload all consumers
   |
   v
Health checks / resume traffic
```

Rủi ro là **khoảng lệch** giữa upstream thay password và consumers nhận B. Các giải pháp khả dĩ:

1. Dùng **two-account/two-user strategy** nếu provider có thể cấp tài khoản song song.
2. Có maintenance window và degrade mode rõ ràng.
3. Điều phối bằng một deployment controller có trạng thái/approval.
4. Giảm connection pooling/cache TTL trong giai đoạn cutover.
5. Kiểm tra tác động đến background jobs và long-lived connections.
6. Có quy trình phục hồi nếu publish/refresh thất bại.
7. Nếu rollback không khả thi, cần plan **roll forward** nhanh tới một credential mới khác.
8. Không chạy nhiều rotation workers đồng thời.

Không tuyên bố zero-downtime nếu nguồn chỉ cho phép một credential và không có thiết kế để chuyển đổi nguyên tử.

## 17. Rotation đột xuất khi credential nghi bị lộ

**Scheduled rotation** và **emergency rotation** có ưu tiên khác nhau.

Khi nghi lộ secret:

1. Kích hoạt quy trình incident response và ghi thời điểm/impact.
2. Khoanh phạm vi: vault/version, upstream provider, consumers và logs.
3. Cấp hoặc kích hoạt credential sạch trong môi trường được kiểm soát.
4. Chuyển consumers sang credential mới càng sớm càng tốt theo quy trình an toàn.
5. **Revoke credential bị lộ tại upstream**, kể cả nếu overlap bình thường chưa kết thúc.
6. Kiểm tra token/session sinh từ credential cũ có cần bị hủy không.
7. Rotate các credential liên quan nếu có lateral exposure.
8. Kiểm tra Git/CI artifacts/logs/backups có lưu bản sao không.
9. Không gửi nguyên giá trị compromised credential vào ticket/chat.
10. Theo dõi hành vi bất thường và hoàn tất postmortem.

Emergency rotation có thể yêu cầu **ngừng dịch vụ có kiểm soát** để ngăn abuse. Không “giữ bản cũ thêm 48 giờ cho chắc” nếu đó là credential đã bị rò.

## 18. Vì sao chỉ sửa metadata của secret chưa đủ?

Một thao tác như “đặt `expiresOn` về ngày mai” hoặc “`enabled=false`” thay đổi trạng thái trong Key Vault, nhưng:

- Không tạo credential B tại upstream.
- Không cập nhật biến môi trường đã đọc khi container khởi động.
- Không đóng tất cả database connections đã xác thực.
- Không vô hiệu hóa token đã được sinh trước.
- Không xóa bản sao trong memory của pods/VMs.
- Không tự rotate client secret của một đối tác bên ngoài.
- Không kiểm chứng ứng dụng đã dùng bản mới.

Vì vậy cần **reconciliation** giữa Key Vault, upstream và consumers. Với credential còn có thể sử dụng tại upstream, **disable trong vault không phải biện pháp revoke duy nhất**.

## 19. Kiến trúc rotation automation trên Azure

Một mô hình phổ biến:

```text
Key Vault secret expiresOn / inventory
                |
        Event Grid events hoặc scheduler
                |
                v
        Azure Function / Logic App
                |
       +--------+-----------+
       |                    |
       v                    v
   Policy & lock       Upstream credential API
   state store              |
       |                     v
       |                 New value B
       |                     |
       +----------+----------+
                  |
                  v
             Key Vault
          setSecret(name, B)
                  |
                  v
          Deployment/refresh signal
                  |
                  v
          Consumers validate B
                  |
                  v
         Revoke A + audit + alert
```

**Key Vault không tự biết cách tạo credential hợp lệ ở mọi bên thứ ba.** Rotation worker phải tích hợp provider API và có quyền riêng, theo policy least privilege. Nếu upstream là một hệ thống legacy cần người đổi mật khẩu thủ công, automation nên tạo ticket/approval chứ không giả định API có sẵn.

## 20. Event Grid: theo dõi vòng đời secret

Key Vault có thể phát **Event Grid events** liên quan đến vòng đời secret theo khả năng hỗ trợ, ví dụ:

- `Microsoft.KeyVault.SecretNewVersionCreated`.
- `Microsoft.KeyVault.SecretNearExpiry`.
- `Microsoft.KeyVault.SecretExpired`.

Tên chính xác, thời điểm phát, điều kiện metadata và loại sự kiện phải được kiểm tra với **Event Grid schema/tính năng thực** của vault.

### Không coi near-expiry event là scheduler đáng tin duy nhất

Một event near-expiry có thể bị bỏ qua nếu:

- Secret không có expiry metadata theo điều kiện event.
- Subscription/endpoint route lỗi.
- Function bị disable hoặc deployment sai.
- Retry/DLQ không được xử lý.
- Rotation worker đã chạy nhưng thất bại.
- Credential upstream hết hạn **trước** metadata expiresOn.
- Event tới trong kỳ bảo trì/không có owner nhận cảnh báo.

Kết hợp **event-driven trigger + inventory reconciliation định kỳ**. Có thể đặt scheduler quét mỗi ngày hoặc theo mức rủi ro để phát hiện thiếu events.

### Event không được tin mù

Event Grid delivery có thể retry/duplicate; worker phải xác minh nguồn/event type, không dùng raw event body làm credential, không tạo vô hạn versions vì nhận cùng event nhiều lần.

## 21. Cấu trúc workflow có trạng thái

Một rotation workflow phải có state rõ:

```text
PLANNED
   |
   v
PROVISIONING
   |
   v
UPSTREAM_NEW_READY
   |
   v
VAULT_VERSION_PUBLISHED
   |
   v
CANARY_VALIDATED
   |
   v
CONSUMERS_MIGRATING
   |
   v
ADOPTION_CONFIRMED
   |
   v
OLD_REVOKED
   |
   v
COMPLETE
```

Các trạng thái lỗi:

```text
PROVISIONING_FAILED
VAULT_PUBLISH_FAILED
CANARY_FAILED
ROLLOUT_TIMEOUT
REVOKE_FAILED
RECONCILIATION_REQUIRED
```

Lưu **operationId**, secret name, provider resource ID, old/new version IDs, policy version, timestamps, attempt count, approvals và kết quả kiểm tra trong **state store có kiểm soát**. **Không lưu raw secret value** trong workflow record, logs hoặc Event Grid payload.

### Vì sao không chỉ làm một Function duy nhất?

Nếu Function thực hiện tạo upstream credential B nhưng timeout **trước khi publish B vào Key Vault**, lần retry không được tạo vô hạn credentials. Cần trạng thái/idempotency và khả năng đối soát với nguồn.

## 22. Idempotency và concurrency trong rotation

Giả sử có hai triggers:

```text
09:00 SecretNearExpiry event
09:01 Daily schedule sees same expiry
09:02 Event Grid retries old event
```

Nếu cả ba chạy độc lập, có thể tạo B, C, D rồi ghi ba new versions, khiến consumer nhận credential không dự kiến.

Cách thiết kế:

1. Một **rotation operation key** như `vault+secret+policyCycleId`.
2. Lock/lease hoặc optimistic concurrency ở state store.
3. Mỗi operation ghi rõ trạng thái và version đã tạo.
4. Duplicate event → tra operation và tiếp tục bước còn thiếu, không tạo key mới tùy ý.
5. Upstream API có idempotency token nếu hỗ trợ.
6. Nếu không có, trước retry phải đối chiếu credential đã tạo.
7. Không publish một version mới nếu previous rotation chưa qua kiểm thử, trừ emergency có approval.
8. Giới hạn concurrent rotation của cùng secret.
9. Lưu audit/version IDs thay vì giá trị mật.
10. Alert khi workflow treo ở một trạng thái quá SLA.

**Event Grid giao sự kiện không phải một transaction toàn hệ thống**. Thiết kế phải an toàn khi process bị crash giữa bất kỳ hai bước nào.

## 23. Chọn thời điểm publish vào Key Vault

Quy trình double-key nên:

1. Yêu cầu tạo B ở upstream.
2. Đợi upstream xác nhận B active.
3. Test B bằng phép thử **ít quyền, không có side effect**, qua môi trường đã phê duyệt.
4. Publish B vào Key Vault dưới **cùng secret name** để tạo new version.
5. Ghi nhận new version ID (không ghi value).
6. Canary rollout tới consumer hạn chế.
7. Xác nhận B hoạt động và không có nghiệp vụ lỗi.
8. Rollout toàn bộ consumers.
9. Chỉ sau khi adoption đủ → revoke A.

**Publish bản mới trong versionless path trước khi test** có thể khiến những consumers tự refresh bắt đầu dùng credential chưa sẵn sàng. Do đó thứ tự publish và khả năng chạy canary cần được thiết kế theo refresh semantics của từng client.

Một lựa chọn kỹ thuật khác là **staging secret name** và kiểm thử B riêng, rồi publish vào production name sau approval. Nhưng không để staging credential active vĩnh viễn hoặc lưu trùng value quá lâu.

## 24. Consumer adoption: khi nào được thu hồi version cũ?

Không chỉ dựa trên lời ghi “deploy thành công”. Cần đo:

- Bao nhiêu instances/pods/VMs đã nhận version B?
- Những background workers/cron jobs có còn khởi động bằng A không?
- Connection pools đã reconnect/authenticate bằng B chưa?
- Ứng dụng có 401/403 hoặc authentication errors sau refresh không?
- Provider có metrics cho credential ID/key ID đang được gọi không?
- Job hiếm chạy mỗi tuần đã được kiểm thử chưa?
- Có DR site/standby environment chưa được reload không?
- Có long-lived offline edge clients cần thời gian riêng không?

**Không log raw credential**. Nếu provider trả **credential ID/key ID** không nhạy cảm, có thể đo adoption theo identifier. Nếu không, tạo ứng dụng-level version marker/telemetry phi nhạy cảm, không ghi secret hash có thể bị lạm dụng như verifier.

### Cutover gate

```text
Revoke A only if:
  B validated at upstream
  AND all required consumer classes updated
  AND auth failures within SLO
  AND rollback/forward plan approved
  AND overlap deadline not exceeded
```

Với cảnh báo compromise, gate phải ưu tiên containment thay vì duy trì overlap thường lệ.

## 25. Caching và refresh trong ứng dụng

Các cách consumer đọc secret:

| Cách | Hành vi | Cần làm khi rotate |
|---|---|---|
| **SDK getSecret mỗi lần dùng** | Nhận dữ liệu theo API và version selection; tăng calls/latency. | Xử lý throttling và đảm bảo không in value. |
| **SDK đọc lúc startup** | Giá trị giữ trong memory cho tới restart/reload. | Chủ động refresh/restart/rollout. |
| **App cache có TTL** | Bản sao còn sống đến lần refresh kế tiếp. | Đo max cache age và lỗi khi refresh fail. |
| **Environment variable** | Giá trị thường được cố định trong process. | Restart/redeploy hoặc cơ chế platform refresh phù hợp. |
| **App Service Key Vault reference** | Nền tảng resolve và cache theo semantics riêng. | Xác minh chu kỳ refresh/trigger; thử nghiệm. |
| **AKS Secrets Store CSI** | Driver/provider mount dữ liệu và có tùy chọn rotation/sync. | Cấu hình refresh; hiểu container env vars không tự update. |
| **Spring Boot Key Vault property source** | Có thể load tại startup/refresh tùy line. | Xác minh version và bean rebind behavior. |

**Versionless identifier không đồng nghĩa refresh tức thì**. Luôn có một **data flow từ vault tới consumer**; nếu một mắt xích giữ giá trị trong memory, version mới chưa được dùng.

### Caching thất bại nên xử lý ra sao?

- Không giữ credential cũ vô hạn không quan sát.
- Với lỗi tạm thời, có thể dùng cached credential trong khoảng được phê duyệt **nếu vẫn hợp lệ và rủi ro chấp nhận**.
- Khi credential bị compromise/revoked, không dùng cache làm fallback.
- Có circuit breaker, bounded retries, backoff và alert khi refresh thất bại.
- Mỗi secret có max-staleness policy phù hợp.

## 26. App Service Key Vault references

Azure App Service/Functions có thể dùng **Key Vault references** trong application settings khi tính năng hỗ trợ:

```text
@Microsoft.KeyVault(SecretUri=https://kv-orders-prod.vault.azure.net/secrets/partner-api-credential)
```

Đây là **reference không pin version**, giúp nền tảng lấy secret theo tên và cơ chế refresh của App Service.

Reference có pin version:

```text
@Microsoft.KeyVault(SecretUri=https://kv-orders-prod.vault.azure.net/secrets/partner-api-credential/<version-id>)
```

### Rủi ro khi rotate

- Versionless ref có thể **được cache**; không giả định lập tức dùng B sau `setSecret`.
- Version-pinned ref **không tự chuyển** sang B cho tới khi sửa reference/deployment.
- Cần xác minh settings refresh behavior của platform, có thể có cách buộc refresh/restart theo tài liệu hiện hành.
- Managed identity của App Service cần quyền đọc đúng vault và đường mạng hợp lệ.
- App settings có thể trở thành environment values trong process, nên **application code vẫn phải quản lý vòng đời dữ liệu nhạy cảm**.
- Đổi reference có thể gây restart/redeploy tùy thao tác; phải đánh giá downtime.

**Không dùng một con số refresh cố định cho mọi Azure hosting service**. App Service, Functions, Container Apps và các versions khác có semantics khác nhau.

## 27. AKS Secrets Store CSI và secret rotation

Một workload AKS có thể dùng **Secrets Store CSI Driver với Azure Key Vault provider** để mount secrets/certificates/keys theo cấu hình và khả năng hỗ trợ.

```text
Azure Key Vault
     |
     v
Azure Key Vault Provider for Secrets Store CSI
     |
     v
Pod mounted file
     |
     v
Application reads credential file / refreshes
```

Điểm cần hiểu:

1. Cần cấu hình identity/workload identity hoặc phương thức auth được hỗ trợ.
2. Rotation refresh của CSI/provider cần được bật/cấu hình theo phiên bản/cluster.
3. **File mount update** không bảo đảm Java singleton tự đọc lại file.
4. Nếu sync thành Kubernetes Secret, các quy tắc refresh của Kubernetes và ứng dụng khác với direct mount.
5. Kubernetes **env vars được lấy lúc container start**; một Secret được cập nhật không làm env var của process hiện tại đổi ngay.
6. Pods offline hoặc bị lỗi driver có thể giữ bản cũ.
7. Kiểm tra theo từng application deployment/namespace.
8. Secret data trong Kubernetes Secret cần được bảo vệ bởi RBAC, encryption at rest và vận hành an toàn.

**Không để Pod dùng version A sau khi A bị revoke chỉ vì CSI đã refresh file**; ứng dụng phải có logic reload hoặc rollout để tiêu thụ dữ liệu mới.

## 28. Spring Boot/Java: đọc secret bằng Azure SDK

Dành cho ứng dụng Java, có thể dùng `azure-security-keyvault-secrets` với `azure-identity`. Dự án Maven có thể quản lý phiên bản bằng BOM phù hợp được phê duyệt.

```xml
<dependencies>
    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-security-keyvault-secrets</artifactId>
        <version>REPLACE_WITH_APPROVED_SDK_VERSION</version>
    </dependency>
    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-identity</artifactId>
        <version>REPLACE_WITH_APPROVED_IDENTITY_VERSION</version>
    </dependency>
</dependencies>
```

**Không tự chọn hai versions bất kỳ.** Trong project thật, nên dùng **Azure SDK BOM** hoặc Spring Cloud Azure BOM tương thích với project, theo policies đã duyệt.

Java client cơ bản:

```java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;

public final class SecretReader {
    public static void main(String[] args) {
        String vaultUrl = System.getenv("KEY_VAULT_URL");
        if (vaultUrl == null || vaultUrl.isBlank()) {
            throw new IllegalArgumentException("KEY_VAULT_URL is required");
        }

        SecretClient client = new SecretClientBuilder()
            .vaultUrl(vaultUrl)
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();

        KeyVaultSecret current = client.getSecret("partner-api-credential");
        System.out.println("Current version: "
            + current.getProperties().getVersion());

        // KHÔNG log current.getValue().
        // Dùng value qua vòng đời ngắn, không lưu vào static field vô hạn.
    }
}
```

Lời gọi getSecret trong ví dụ **thực sự lấy giá trị secret vào bộ nhớ** nếu chạy; chỉ dùng với vault lab và người dùng có data-plane permission. Lệnh in chỉ hiển thị **version ID**, không in value.

## 29. Java: liệt kê metadata các versions

Một tác vụ inventory không cần in giá trị bí mật:

```java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import com.azure.security.keyvault.secrets.models.SecretProperties;

public final class VersionInventory {
    public static void main(String[] args) {
        SecretClient client = new SecretClientBuilder()
            .vaultUrl(System.getenv("KEY_VAULT_URL"))
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();

        for (SecretProperties p :
             client.listPropertiesOfSecretVersions("partner-api-credential")) {

            System.out.printf(
                "version=%s enabled=%s expires=%s%n",
                p.getVersion(),
                p.isEnabled(),
                p.getExpiresOn()
            );
        }
    }
}
```

Đây là **metadata-only listing** theo interface của SDK. Data-plane role cho việc list properties có thể khác với role đọc value, tùy role definitions và vault permission model. Dù không in value, **metadata cũng không được public** nếu chính sách che tên tài nguyên/tên credential.

### Không dùng getSecret trong inventory không cần value

Một inventory job chỉ để kiểm tra expiry/version **không nên fetch mọi secret value**. Giảm quyền và dữ liệu tiếp xúc bằng cách dùng danh sách properties/attributes.

## 30. Java: publish version mới trong lab

Ví dụ Java đơn giản dành **chỉ cho môi trường lab đã phê duyệt**:

```java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

public final class LabCreateSecretVersion {
    public static void main(String[] args) {
        String value = System.getenv("LAB_NEW_SECRET_VALUE");
        String vaultUrl = System.getenv("KEY_VAULT_URL");
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Lab value must be set");
        }

        SecretClient client = new SecretClientBuilder()
            .vaultUrl(vaultUrl)
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();

        KeyVaultSecret candidate = new KeyVaultSecret(
            "partner-api-credential-lab",
            value
        );
        candidate.getProperties().setExpiresOn(
            OffsetDateTime.now(ZoneOffset.UTC).plusDays(45)
        );

        KeyVaultSecret created = client.setSecret(candidate);

        // Chỉ log version ID và mã tracking, KHÔNG log value.
        System.out.println("New version: "
            + created.getProperties().getVersion());
    }
}
```

**Cảnh báo:**

- Ví dụ này **chỉ lưu giá trị B vào vault**, không tự tạo credential hợp lệ trong API provider.
- Môi trường thực không nên đưa secret vào shell history, crash dumps hoặc long-lived environment variables. Cách cấp qua env chỉ để minh họa giao diện SDK; rotation worker Production nên lấy value an toàn từ nguồn/secret transport đã phê duyệt và giảm thời gian tồn tại trong memory.
- Cần scope `set secret` phù hợp và kiểm soát ai có thể publish versions.
- Trước khi chạy lệnh phải xác minh vault URL là **lab vault**, không phải Production.
- Một lần chạy lại sẽ tạo **version mới**, vì vậy workflow thật phải có idempotency/operation state.
- Không nên dùng `System.out.println(value)` hoặc serialize `KeyVaultSecret` trực tiếp.

## 31. Azure CLI: kiểm tra metadata an toàn

Những lệnh sau **chỉ đọc metadata** khi dùng đúng `--query` và không redirect raw response có value vào log.

```bash
# Thay bằng VAULT và SECRET của môi trường được phép.
VAULT="kv-orders-lab"
SECRET="partner-api-credential-lab"

az account show \
  --query "{Subscription:id,Tenant:tenantId,Name:name}" \
  --output table

# Liệt kê tên, thuộc tính; không yêu cầu xuất value.
az keyvault secret list \
  --vault-name "$VAULT" \
  --query "[].{name:name,enabled:attributes.enabled,expires:attributes.expires}" \
  --output table

# Liệt kê versions và expiry; giữ output giới hạn ở metadata.
az keyvault secret list-versions \
  --vault-name "$VAULT" \
  --name "$SECRET" \
  --query "[].{id:id,enabled:attributes.enabled,expires:attributes.expires}" \
  --output table
```

**Không dùng** `az keyvault secret show` với output mặc định khi chỉ muốn kiểm tra version: command có thể trả trường `value`. Nếu cần dùng để lấy một thuộc tính, phải cố định `--query` chỉ chọn metadata, không copy response full vào terminal logs.

### Kiểm tra version cụ thể

```bash
az keyvault secret show \
  --vault-name "$VAULT" \
  --name "$SECRET" \
  --version "REPLACE_WITH_VERSION_ID" \
  --query "{id:id,enabled:attributes.enabled,expires:attributes.expires}" \
  --output json
```

Đây là ví dụ query chỉ metadata, **nhưng** thao tác `show/get` có thể yêu cầu quyền đọc giá trị đầy đủ tại data plane. Với inventory job cần ít quyền hơn, ưu tiên API liệt kê properties.

## 32. Azure CLI: tạo version và sửa attributes chỉ trong lab

Cú pháp khái niệm:

```text
az keyvault secret set
  --vault-name <LAB_VAULT>
  --name <LAB_SECRET>
  --value <SENSITIVE_VALUE>
  --expires <UTC_DATE>

az keyvault secret set-attributes
  --vault-name <LAB_VAULT>
  --name <LAB_SECRET>
  --version <VERSION_ID>
  --enabled {true|false}
  --expires <UTC_DATE>
```

Đây là **sơ đồ lệnh**, không phải block copy-run đầy đủ. Không gõ raw credential sau `--value` trong shell có history/process logging. Trong lab có thể dùng giá trị **giả** và phương thức nhập/phân phối bí mật không ghi lịch sử; trong Production dùng automation SDK/trusted credential transport.

**Nhớ rằng:**

- `set secret` tạo version mới.
- `set-attributes` sửa metadata của version được chọn.
- `--enabled false` không thu hồi bản sao credential đã phát ra ngoài vault.
- Cập nhật expiry của một version không tự rotate password tại upstream.
- Không chạy ví dụ trên secret thật để thử vì có thể ảnh hưởng ứng dụng production.

## 33. Tags và metadata để quản trị rotation

Metadata ví dụ:

```json
{
  "owner": "payments-platform",
  "environment": "production",
  "rotationPolicy": "external-api-dualkey-v2",
  "upstreamSystem": "partner-api",
  "changeTicket": "CHG-EXAMPLE-2026",
  "criticality": "high"
}
```

Các metadata này có thể gắn trong tags/registry theo chính sách; **không coi đây là schema cố định của Key Vault**.

Một registry nội bộ nên giữ:

- System owner và escalation contact.
- Secret name/vault/tenant/environment.
- Upstream credential identifier, không phải raw value.
- Last/next rotation windows.
- Actual upstream expiry.
- Required consumer classes và refresh SLA.
- Revocation confirmation.
- Last success/failure và incident references.

**Không gắn toàn bộ metadata nhạy cảm trong tags** nếu vault có nhiều người được phép đọc properties. Chọn field nào ở Key Vault, field nào ở state store riêng theo access controls.

## 34. Phân quyền: consumer và rotation worker là hai vai trò khác nhau

| Principal | Nhu cầu | Không nên cấp |
|---|---|---|
| **Application runtime** | `get secret value` cho đúng vault/scope. | Quyền tạo/xóa/purge secret hoặc cấp roles. |
| **Rotation worker** | Tạo version mới, đọc metadata/đặt expiry, có thể disable old khi policy cho phép. | Quyền quản trị toàn subscription nếu không cần. |
| **Security operator** | Audit, review policy, khởi động emergency rotation. | Credential value nếu chỉ cần giám sát metadata. |
| **Platform engineer** | Quản lý vault/network/IaC. | Quyền mọi secret value mặc định nếu không cần. |
| **Incident responder** | Thu hồi, điều tra, truy cập theo break-glass policy. | Quyền thường trực không audit. |

Một số Azure RBAC roles thường gặp:

- **Key Vault Secrets User**: có quyền đọc nội dung secret trong phạm vi cho phép.
- **Key Vault Secrets Officer**: có quyền quản lý secrets theo định nghĩa role, cần kiểm tra phạm vi.
- **Key Vault Reader**: đọc metadata/control-plane, không được mặc định dùng để xem secret value.

**Không suy ra quyền chỉ dựa trên tên role**: vault có thể dùng **Azure RBAC** hoặc **access policy permission model** theo cấu hình và loại vault. Kiểm tra đúng model, scope, built-in role definitions và quy trình phê duyệt.

### Vault-per-boundary

Với hệ thống lớn, cân nhắc tách vault theo **environment/application/tenant/trust boundary**. Tránh một vault chứa mọi secrets và gán một role rộng cho tất cả apps chỉ để đơn giản hóa.

## 35. Managed identity trước static secret

Ưu tiên lựa chọn theo thứ tự có điều kiện:

1. **Managed identity/workload identity** để gọi Azure resources hỗ trợ Entra authentication.
2. **Federated identity** thay client secret trong CI/CD hoặc workload bên ngoài nếu hỗ trợ.
3. **Short-lived tokens** được issue đúng audience/scope thay long-lived shared secret.
4. Nếu dịch vụ đối tác bắt buộc static credential, lưu qua Key Vault và rotation workflow.
5. Với password legacy, lập kế hoạch chuyển đổi sang identity/role model hiện đại khi có thể.

```text
Spring Boot on Azure
    |
    +-- To Blob Storage:
    |      managed identity + Azure RBAC
    |
    +-- To third-party API:
           Key Vault secret + external rotation workflow
```

**Không tạo và rotate secret nếu có thể loại bỏ nhu cầu phải giữ nó.** Đây là giải pháp giảm rủi ro căn bản hơn cả việc quay key mỗi tuần.

## 36. Mạng, TLS và data residency

Một consumer có version đúng nhưng vẫn không đọc được Key Vault nếu:

- Vault firewall chặn outbound IP/subnet.
- Private Endpoint chưa cấu hình đúng.
- Private DNS zone chưa link VNet hoặc resolution sai.
- App Service/Container Apps/AKS chưa có network route.
- Token audience/tenant/RBAC sai.
- TLS certificate validation bị cấu hình sai.
- Proxy outbound chặn Entra token endpoint.
- Vault đang bị hạn chế/truy cập qua cloud environment khác.
- Event Grid endpoint/Function không có network/identity hợp lệ.

### Nguyên tắc

- Dùng HTTPS/TLS, không tắt hostname verification để debug.
- Kiểm tra private access và DNS **từ runtime thực**.
- Xem đường mạng của **cả rotation worker lẫn consumers**.
- Giữ vault/automation/logs trong data boundary được phê duyệt.
- Không đưa secrets vào diagnostic events qua Event Grid.
- Không mở public network access để sửa một 403 trước khi xác định nguyên nhân.

**Private Endpoint không thay thế authorization.** Một actor có mạng tới vault vẫn cần identity/data-plane permissions.

## 37. Soft delete, purge protection và ý nghĩa khi rotate

**Soft delete** và **purge protection** là các biện pháp bảo vệ vòng đời/xóa tài nguyên trong Key Vault theo cấu hình hiện hành.

- Soft delete giúp có cơ chế khôi phục đối tượng bị xóa trong thời hạn giữ.
- Purge protection ngăn purge sớm theo retention policy khi tính năng được bật.
- Các điều kiện và thời hạn retention cần được xác minh theo tenant/vault policy.
- Không xem soft delete là **backup lịch sử upstream credentials**.
- Không coi xóa secret là bước bắt buộc khi rotate.
- Không purge version/secret chỉ vì muốn “dọn cho gọn” khi còn consumers/forensics/compliance obligations.

### Vì sao rotation không được đồng nghĩa delete?

Nếu xóa secret name trong vault, những consumers dùng versionless URI có thể bị gián đoạn. Thường **tạo version mới, migrate và revoke upstream old credential** là hướng phù hợp hơn; version cũ được lưu/disable hoặc xóa theo chính sách retention được phê duyệt.

**Thu hồi upstream credential** và **soft-delete trong vault** giải quyết các mục tiêu khác nhau.

## 38. Audit, metrics và cảnh báo

Những tín hiệu cần quan sát:

| Tín hiệu | Câu hỏi | Nguồn dự kiến |
|---|---|---|
| Secret near-expiry inventory | Credential nào sắp đến hạn? | Key Vault metadata + rotation registry. |
| Rotation overdue | Có bỏ lỡ policy cycle? | Scheduler/state store. |
| New version created | Ai/automation nào publish? | Key Vault events/diagnostic logs. |
| Unexpected version created | Có actor ngoài workflow tạo secret? | Audit/change detection. |
| Consumer version adoption | Mọi replicas đã dùng bản mới? | Application metrics/version markers. |
| Upstream auth errors | Có tăng 401/403 sau cutover? | Consumer/provider metrics. |
| Vault get/permission errors | Consumer không lấy được secret? | Key Vault diagnostics + app logs. |
| Event Grid delivery failures | Automation có bị mất trigger? | Event Grid/Event handler monitoring. |
| Rotation workflow failures | Tắc ở bước nào, bao lâu? | Durable state/alerts. |
| Secret access anomalies | Truy cập bất thường/vượt scope? | Azure Monitor/SIEM theo cấu hình. |
| Network errors | DNS/private endpoint/timeout? | Client traces và network observability. |
| Cost | Calls/version growth/log ingestion. | Cost Management + service meters. |

**Không giả định tất cả là built-in Azure Monitor metrics cùng tên**; nhiều chỉ số phải ghi từ rotation worker hoặc ứng dụng. Azure Activity Log phục vụ kiểm toán control-plane; data-plane diagnostic logging phải cấu hình phù hợp và không được ghi raw secret.

## 39. Alert policy: đừng chỉ chờ expiry event

Ví dụ alert policy nội bộ:

```text
30 days before upstream expiry:
  create ticket + schedule rotation (example policy)

14 days before:
  check rotation state and owner acknowledgement

7 days before:
  escalation to operations/security owner

At rotation:
  verify new version published + consumers adopted

After overlap:
  verify upstream old credential revoked

If any gate fails:
  page owner according to severity, do not mark COMPLETE
```

Các mốc 30/14/7 ngày là **minh họa**, không phải Microsoft Key Vault guarantee. Một số credentials có thời hạn vài giờ, khi đó các mốc trên không hợp lý; chọn theo interval thật.

### Event plus polling

```text
Key Vault Event Grid events ─┐
                            ├── Rotation state machine
Daily/periodic inventory ───┘         |
                                     v
                               Alerts + dashboard
```

Có schedule bù trừ để phát hiện event đến muộn/mất. Lưu `nextRotationDueUtc` dựa trên upstream validity và policy, không chỉ suy từ metadata của secret đang nằm trong vault.

## 40. Chi phí: rotation và đọc secret cũng có giá

Một hệ thống secret rotation có thể phát sinh:

- Key Vault secret operations (get/list/set/properties updates) theo meter.
- Azure Functions/Logic Apps và state store.
- Event Grid delivery.
- Monitoring/Log Analytics ingestion và retention.
- Managed identities/RBAC administration overhead.
- Private Endpoint/egress/network theo chính sách tính phí.
- Retry storms khi consumer lỗi credential.
- Chi phí nhân sự on-call/approval và kiểm tra integration.
- Downtime và thất bại nghiệp vụ nếu rotation sai.

**Không yêu cầu getSecret cho mọi HTTP request** nếu một cache TTL an toàn đáp ứng nhu cầu: tần suất gọi vault cao làm tăng latency, quota/throttling và chi phí. Ngược lại **không cache vô hạn** vì tiết kiệm vài request mà mất khả năng rotation.

### Ví dụ số calls

Giả sử 100 pods, mỗi pod đọc một secret mỗi 10 phút:

```text
100 pods × 6 reads/hour = 600 reads/hour
600 × 24 = 14,400 reads/day
```

Đây là **dự báo đơn giản**, chưa tính retries, startup, nhiều secrets hoặc SDK caching. Sử dụng workload thực và pricing hiện hành để tối ưu interval/architecture.

## 41. Runbook: secret đã hết hạn, ứng dụng lỗi xác thực

**Triệu chứng:** nhiều requests bắt đầu trả `401 Unauthorized` khi gọi API provider.

### Điều tra

1. Xác định lỗi từ **upstream provider** hay Key Vault get operation.
2. Lấy requestId, thời gian UTC, secret name và **version ID phi nhạy cảm**.
3. Kiểm tra upstream credential còn valid không; đừng chỉ nhìn Key Vault `expiresOn`.
4. Kiểm tra consumer có dùng versionless hay pinned reference.
5. Kiểm tra logs/metrics adoption tại tất cả pods/VMs/jobs.
6. Kiểm tra rotation workflow đã đến trạng thái nào.
7. Xác định có source credential B đã được cấp nhưng chưa publish không.
8. Kiểm tra Key Vault get/RBAC/network không bị lỗi riêng.
9. Kiểm tra app cache/restart/refresh mechanisms.
10. Không in secret value để debug.

### Khắc phục

- Nếu B hợp lệ ở upstream: publish/refresh/migrate consumers theo runbook.
- Nếu B chưa có: rotate tại provider qua workflow/owner.
- Nếu A đã revoke: **không thử “đọc lại version A” như cách khôi phục**.
- Nếu workflow chưa rõ trạng thái: dùng operation state/idempotency để đối soát.
- Giới hạn retry, giảm impact và kiểm chứng end-to-end.
- Thêm test/alert chống gần-expiry và stale consumer.

## 42. Runbook: Key Vault có version mới nhưng app vẫn dùng bản cũ

**Triệu chứng:** rotation worker ghi B thành công nhưng Pod/app vẫn xác thực bằng A.

### Kiểm tra

- Có dùng version-pinned URI trong App Service settings hoặc config không?
- Java/Spring Boot có lấy secret lúc startup rồi cache không?
- AKS CSI file mount có refresh chưa; process có re-read file không?
- Kubernetes env var có cần restart pod không?
- App Service Key Vault ref có cần refresh/restart theo behavior thực không?
- Có nhiều deployments/regions/DR sites dùng cùng secret?
- Credentials ở upstream có cho A và B cùng có hiệu lực không?
- Có cache hoặc config server khác giữ bản sao A?
- Có instance cũ chưa được drain/rollout?
- Metrics/version marker đã được cập nhật chưa?

### Khắc phục

1. Xác định consumer classes và pinning/caching.
2. Kích hoạt refresh/redeployment đúng cách.
3. Kiểm tra canary B tại upstream.
4. Rollout toàn bộ và xác minh adoption.
5. Sau khi đủ điều kiện mới revoke A.
6. Đưa “refresh verified” vào release checklist.

**Đổi secret value trong vault không có nghĩa đã hoàn tất rotation.**

## 43. Runbook: version mới sai, cần rollback

**Triệu chứng:** B đã publish nhưng test API provider fail, A vẫn còn valid.

### Quy trình

1. Dừng rollout B và tạm ngừng automation chạy lặp.
2. Xác minh A **vẫn valid ở upstream**.
3. Chuyển consumers về cấu hình/credential A theo phương thức có thể kiểm chứng.
4. Với versionless consumers, một số ứng dụng có thể cần **publish lại giá trị A như một new version** qua trusted workflow; không giả định versionless sẽ tự chọn version A cũ.
5. Tránh copy secret A ra terminal hay tickets trong quá trình rollback.
6. Nếu A bị revoke, **không thể rollback về A**; phải roll forward B sửa đúng hoặc cấp C mới.
7. Xác định upstream credential B có cần revoke sau khi xử lý không.
8. Ghi audit và incident analysis.
9. Sửa validation gates trước lần rotation kế tiếp.

**Rollback secret không phải thao tác đổi một số version ID đơn giản**. Nó phụ thuộc upstream validity và cách consumers resolve/cache.

## 44. Runbook: rotation worker liên tục tạo versions

**Triệu chứng:** xuất hiện hàng chục versions mới trong vài phút, worker logs có retries/timeouts.

### Nguyên nhân có thể

- Event Grid redelivery được coi như một lệnh độc lập.
- Scheduler và event trigger chạy cùng lúc.
- Không có distributed lock hoặc idempotency key.
- Workflow timeout sau khi upstream đã tạo credential.
- Worker không lưu version ID/operation state.
- Trigger “new version created” gây vòng lặp vào chính rotation logic.
- Secret name bị loop do policy sai.

### Khắc phục

1. Dừng trigger lỗi có kiểm soát.
2. Không xóa hàng loạt versions bằng script chưa review.
3. Xác định phiên bản nào được upstream chấp nhận và consumers đang dùng.
4. Đối soát credentials đã tạo ở provider và audit trail.
5. Thêm state store, idempotency, lock và retry budget.
6. Ngăn event feedback loop bằng origin/correlation filters.
7. Khôi phục chiến lược active version/consumer adoption.
8. Thêm cảnh báo unexpected new-version rate.
9. Chạy fault injection test ở lab trước bật lại.

## 45. Bài thực hành: rotation secret với hai phiên bản

**Bối cảnh:** một vault lab và một API provider giả lập cho phép hai tokens A/B cùng có hiệu lực. Dùng **giá trị giả** hoặc test credentials không cấp quyền thật. Không dùng Key Vault Production.

### Tài nguyên

| Thành phần | Vai trò |
|---|---|
| `kv-orders-lab` | Vault chứa secret versions. |
| `partner-api-credential-lab` | Tên logic ổn định. |
| Mock provider | Chấp nhận hai token A/B trong overlap. |
| Rotation worker lab | Thực hiện có trạng thái, không log value. |
| Consumer A | Đọc versionless. |
| Consumer B | Đọc version ID cụ thể. |
| State store | Theo dõi operationId, old/new version, status. |
| Metrics | Đếm requests/auth success và adoption. |

### Nhiệm vụ

1. Vẽ sơ đồ vault–provider–worker–consumers.
2. Xác định secret lifetime, expiry metadata và cache TTL khác nhau ra sao.
3. Định nghĩa vòng đời A→B với overlap window.
4. Xác minh subscription, vault URL và identity của lab.
5. Tạo secret A **chỉ trong lab** bằng trusted method, không đưa giá trị vào Git/logs.
6. Gắn `expiresOn` giả lập cho version A.
7. Liệt kê metadata versions bằng CLI hoặc SDK, **không in values**.
8. Cho Consumer A gọi theo secret name, Consumer B pin version A.
9. Tạo credential B ở mock provider, để A còn valid.
10. Kiểm tra B có thể authenticate với mock provider.
11. Publish B thành new version trong vault.
12. Ghi new version ID vào state store, không ghi raw value.
13. Kiểm tra Consumer A chưa refresh có thể vẫn dùng A.
14. Kiểm tra Consumer B pinned A không tự chuyển sang B.
15. Cho một canary instance refresh sang B, đo auth success.
16. Rollout/reload các consumers còn lại.
17. Xác nhận mọi required consumers dùng B trước khi retire A.
18. Revoke A trong mock provider.
19. Kiểm tra A không còn dùng được ngay cả khi consumer còn bản sao.
20. Thử Event Grid duplicate trigger; không được tạo C vô ý.
21. Thử Function crash sau upstream create, kiểm tra recovery/idempotency.
22. Thử lỗi vault 403 và phân biệt với provider 401.
23. Thử phiên bản B sai trong môi trường giả lập; rollback khi A còn valid.
24. Tạo alert khi secret gần expiry nhưng workflow chưa hoàn tất.
25. Viết runbook emergency compromise và test tình huống A bị revoke sớm.
26. Dự toán số lần gọi vault và vận hành automation.
27. Dọn tài nguyên lab theo quy trình, không purge vault dùng chung.

### Kỳ vọng nghiệm thu

- Có ít nhất hai versions với **cùng secret name**.
- Phân biệt metadata của mỗi version.
- Có bằng chứng upstream B hoạt động **trước** full rollout.
- Consumer versionless và pinned có behavior được ghi rõ.
- Không tạo version mới lặp do duplicate events.
- Có xác minh adoption, revoke A và hậu kiểm.
- Không log raw secret, access token, password hay connection string.
- Có least-privilege RBAC/network policy.
- Có kế hoạch rollback hoặc roll-forward rõ ràng.
- YAML/config lab không chứa credential production.

## 46. Checklist Production trước khi bật rotation

**Inventory và chính sách**

- [ ] Mỗi secret có owner, environment, hệ thống nguồn và người phê duyệt.
- [ ] Có upstream expiry/validity độc lập với vault metadata.
- [ ] Có policy rotation interval, start deadline, overlap/rollback windows.
- [ ] Có emergency revocation và blast-radius plan.
- [ ] Đã đánh giá có thể thay static secret bằng managed identity hay không.
- [ ] Không dùng một shared credential cho nhiều ứng dụng nếu có thể tách quyền.

**Phiên bản và consumers**

- [ ] Hiểu versionless vs pinned URIs.
- [ ] Có danh sách đầy đủ consumers, cron, background jobs và DR sites.
- [ ] Có quy trình refresh/restart/rollout cho từng runtime.
- [ ] Có kiểm tra upstream B active trước khi publish/ramp-up.
- [ ] Có gate xác minh adoption trước khi revoke A.
- [ ] Có kế hoạch rollback khi A còn valid, roll-forward khi A đã revoke.
- [ ] Không giữ secret vô thời hạn trong caches hoặc environment.

**Automation và an toàn**

- [ ] Worker có managed identity/data-plane role tối thiểu.
- [ ] Event Grid + scheduler inventory cùng cấp alert bù.
- [ ] Workflow có state, operationId, lock và idempotency.
- [ ] Có retry budgets/backoff/DLQ, ngăn vòng lặp event.
- [ ] Secret values không xuất hiện trong events/logs/tickets.
- [ ] Rotation worker không có quyền quản trị toàn subscription không cần thiết.
- [ ] Soft delete/purge protection và retention policy đã được review.
- [ ] Network/TLS/Private DNS đã kiểm thử từ worker và consumers.

**Quan sát và chi phí**

- [ ] Có alert near-expiry, overdue rotation, workflow failure.
- [ ] Theo dõi 401/403 provider và Key Vault separately.
- [ ] Ghi audit new version, role changes và unexpected access.
- [ ] Metrics adoption theo version marker không nhạy cảm.
- [ ] Có test fault injection/partial failure trong lab.
- [ ] Có capacity/Key Vault operation limits và budget alerts.
- [ ] Có runbook expired/stale/compromised secret và on-call owner.

## 47. Câu hỏi tự kiểm tra

**Câu 1.** Secret name và version ID khác nhau thế nào?

**Đáp án:** Tên là định danh logic của secret; version ID xác định một lần publish giá trị riêng của cùng tên.

**Câu 2.** Gọi `setSecret` cùng tên với giá trị mới có ghi đè giá trị version cũ tại chỗ không?

**Đáp án:** Không. Nó tạo một phiên bản mới theo cơ chế Key Vault Secrets.

**Câu 3.** Versionless URI có nghĩa mọi consumer ngay lập tức dùng version mới không?

**Đáp án:** Không. Consumer/platform có thể cache hoặc không re-read, cần refresh/restart/rollout và xác minh adoption.

**Câu 4.** Version-pinned URI có tự cập nhật khi có B không?

**Đáp án:** Không. Nó chỉ rõ version và phải đổi reference/config khi rotation.

**Câu 5.** Metadata `expiresOn` có tự thay password tại đối tác không?

**Đáp án:** Không. Phải có rotation workflow tạo credential ở upstream và cập nhật consumers.

**Câu 6.** `enabled=false` trên version cũ có bảo đảm credential A đã bị revoke tại provider không?

**Đáp án:** Không. Nó tác động trạng thái vault; provider cần thu hồi credential thật riêng.

**Câu 7.** `notBefore` có nghĩa ứng dụng đã sẵn sàng cutover vào thời điểm đó không?

**Đáp án:** Không. Nó là thuộc tính thời gian của version; consumer readiness phải được đo.

**Câu 8.** Vì sao cần giữ cả upstream expiry và Key Vault expiry?

**Đáp án:** Hai hệ thống có thể có hạn khác nhau; credential có thể ngừng được chấp nhận trước/sau metadata vault.

**Câu 9.** Dual-key rotation có lợi gì?

**Đáp án:** Cho phép A/B cùng valid tạm thời để canary, rollout và rollback với downtime thấp khi provider hỗ trợ.

**Câu 10.** Có thể revoke A ngay sau khi publish B không?

**Đáp án:** Không nên trong rotation thông thường; phải xác minh consumers đã adopt B, trừ emergency containment.

**Câu 11.** Nếu upstream chỉ cho một password active, có chắc zero-downtime không?

**Đáp án:** Không. Cần alternate account/controlled cutover, maintenance hoặc cơ chế đồng bộ đặc biệt.

**Câu 12.** Tại sao Event Grid near-expiry không nên là trigger duy nhất?

**Đáp án:** Có thể thiếu metadata/event/route hoặc worker fail; cần inventory reconciliation theo lịch.

**Câu 13.** Event Grid duplicate delivery có thể gây lỗi gì?

**Đáp án:** Nhiều rotation workers tạo nhiều credentials/versions nếu không có idempotency.

**Câu 14.** Workflow state nên lưu raw secret value không?

**Đáp án:** Không. Lưu operationId, version IDs, status, timestamps và audit metadata thôi.

**Câu 15.** Một worker timeout sau khi tạo upstream B nên làm gì khi retry?

**Đáp án:** Đối soát trạng thái/idempotency, không tạo thêm C vô điều kiện.

**Câu 16.** App Service Key Vault reference versionless có đồng nghĩa instant refresh không?

**Đáp án:** Không. Phải hiểu cache/refresh/restart semantics của platform.

**Câu 17.** Khi AKS CSI đã update mounted file, Java process có chắc dùng value mới không?

**Đáp án:** Không. App cần re-read/reload/rollout phù hợp.

**Câu 18.** Kubernetes env var từ Secret được cập nhật có tự đổi trong process đang chạy không?

**Đáp án:** Không. Thông thường phải restart/redeploy để process nhận giá trị mới.

**Câu 19.** Role Key Vault Reader có mặc định cho đọc raw secret value không?

**Đáp án:** Không. Cần role/permission data plane đọc secret value tương ứng.

**Câu 20.** Vì sao tách consumer và rotation worker identities?

**Đáp án:** Consumer thường chỉ cần read; worker cần publish/update, giảm blast radius khi ứng dụng bị compromise.

**Câu 21.** Managed identity có thể giảm secret rotation workload thế nào?

**Đáp án:** Loại bỏ nhu cầu lưu static credential cho Azure services hỗ trợ identity-based access.

**Câu 22.** Soft delete/purge protection có tự revoke password ở upstream không?

**Đáp án:** Không. Chúng bảo vệ vòng đời xóa/khôi phục trong Key Vault.

**Câu 23.** Một ứng dụng bị 401 từ provider, có nhất thiết là Key Vault 403 không?

**Đáp án:** Không. Provider 401 có thể do credential hết hạn/revoked; vault 403 liên quan permission/data plane, cần tách nguồn lỗi.

**Câu 24.** Khi B lỗi và A đã bị revoke, có thể rollback bằng cách đọc version A không?

**Đáp án:** Không. Cần roll forward tới credential hợp lệ hoặc khôi phục A ở upstream nếu provider cho phép theo quy trình.

**Câu 25.** Tại sao không nên log `KeyVaultSecret` object nguyên vẹn?

**Đáp án:** Nó có thể chứa secret value và metadata nhạy cảm, gây lộ qua logs.

**Câu 26.** Vì sao không nên gọi getSecret trên mỗi HTTP request nếu không cần?

**Đáp án:** Tăng latency, operations/quota và chi phí; nên cache với TTL/refresh phù hợp rủi ro.

**Câu 27.** Tại sao tags không nên chứa secret value?

**Đáp án:** Tags là metadata có thể được liệt kê/log theo quyền rộng hơn, không phải nơi chứa thông tin bí mật.

**Câu 28.** Emergency rotation khác scheduled rotation ở đâu?

**Đáp án:** Khi bị lộ, ưu tiên containment/revocation và chấp nhận giảm overlap hoặc gián đoạn có kiểm soát.

**Câu 29.** Tiêu chí hoàn tất rotation là gì?

**Đáp án:** Credential mới hợp lệ tại upstream, consumers đã chuyển, bản cũ được revoke theo policy, metrics/alerts bình thường và audit đầy đủ.

**Câu 30.** Nguyên tắc quan trọng nhất?

**Đáp án:** **Một secret version mới trong Key Vault chưa có nghĩa credential đã luân chuyển an toàn**; cần quản lý song song upstream validity, versioning, consumer refresh, cutover, revocation, rollback và observability.

## 48. Bảng thuật ngữ và lưu ý thực thi

| Thuật ngữ | Giải thích ngắn |
|---|---|
| **Secret version** | Giá trị riêng được publish dưới một secret name. |
| **Versionless URI** | Secret identifier không chỉ rõ version. |
| **Pinned version** | Consumer chọn đúng một version ID. |
| **expiresOn** | Metadata thời gian hết hạn của secret version. |
| **notBefore** | Metadata thời điểm có hiệu lực. |
| **enabled** | Thuộc tính bật/tắt version theo semantics Key Vault. |
| **Upstream provider** | Hệ thống thực sự xác thực credential. |
| **Rotation policy** | Quy tắc khi nào và cách nào thay credential. |
| **Overlap/grace window** | Khoảng A và B cùng hợp lệ để migrate. |
| **Adoption** | Bằng chứng consumers đã bắt đầu dùng B. |
| **Revocation** | Vô hiệu hóa credential tại nơi xác thực nó. |
| **Idempotency** | Retry cùng một operation không tạo side effects lặp. |
| **Reconciliation** | So sánh vault, provider, consumers để phát hiện lệch. |
| **Emergency rotation** | Rotation phản ứng nhanh với nguy cơ compromise. |
| **Soft delete** | Cơ chế giữ khả năng khôi phục sau xóa theo policy. |
| **Purge protection** | Bảo vệ chống purge trước hạn retention. |

**Tóm lại:** Quản lý **secret version, hạn sử dụng và chiến lược luân chuyển** trong Azure Key Vault đòi hỏi nhiều hơn việc tạo một version mới hoặc gán `expiresOn`. Phải hiểu **versionless và pinned access**, hai vòng đời độc lập **vault metadata và upstream credential**, cách consumers **cache/refresh**, và triển khai **rotation có trạng thái, idempotency, canary, xác minh adoption, revoke và rollback**. Với Azure Event Grid/Functions, managed identity, RBAC, Private Endpoint, auditing và alerts, doanh nghiệp có thể giảm nguy cơ credential hết hạn hoặc bị lộ mà không tạo sự cố không cần thiết. **Bước cuối của rotation không phải “set secret thành công” mà là “tất cả consumers sử dụng credential hợp lệ mới, bản cũ được xử lý theo policy, và hệ thống vẫn vận hành an toàn”.**
