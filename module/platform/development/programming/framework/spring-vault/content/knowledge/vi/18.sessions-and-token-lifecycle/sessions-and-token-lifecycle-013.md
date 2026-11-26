# Kiểm thử lỗi gia hạn, hết hạn và đóng ApplicationContext trong Spring Vault

Ứng dụng Java sử dụng **Spring Vault** thường xác thực với **HashiCorp Vault** qua `ClientAuthentication`, lấy Vault token bằng `SessionManager` và gửi yêu cầu qua `VaultTemplate`. Khi token hoặc secret lease hết hạn, ứng dụng có thể bắt đầu trả lỗi `403 permission denied`, đọc secret thất bại, không tạo được credential database hoặc không xin được chứng chỉ từ PKI. Một lỗi khác khó nhận ra hơn là **đóng Spring `ApplicationContext` nhưng tác vụ gia hạn vẫn chạy hoặc phiên không được xử lý đúng vòng đời**.

Bài học thuộc chương **Phiên và vòng đời token**, tập trung vào cách **kiểm thử lỗi gia hạn (renewal failure), hết hạn (expiration) và đóng `ApplicationContext` (shutdown/cleanup)**. Các ví dụ sử dụng Vault token TTL ngắn trên môi trường thử nghiệm, JUnit 5, Spring `VaultTemplate` và quan sát API Vault. Mục đích là phát hiện đúng lỗi ở các tầng **xác thực, phiên, lease và lifecycle**, đồng thời bảo đảm ứng dụng vẫn tuân thủ policy tối thiểu khi truy cập KV secrets, Transit hoặc PKI.

## 1. Phân biệt vòng đời token, phiên và secret lease

| Đối tượng | Nó đại diện cho gì? | Ai quản lý? | Lỗi hết hạn thường thấy |
| --- | --- | --- | --- |
| **Credential đăng nhập** | Kubernetes JWT, AppRole `role_id/secret_id`, GCP identity, chứng chỉ client hoặc token cung cấp sẵn. | Nền tảng workload và lớp `ClientAuthentication`. | Không thể đăng nhập lại dù Vault vẫn hoạt động. |
| **Vault client token** | Quyền gọi API Vault theo policy và TTL; có thể có khả năng renew. | Vault, `SessionManager` và cấu hình auth. | HTTP `403` khi yêu cầu token đã hết hạn hoặc bị thu hồi. |
| **Phiên Spring Vault** | Cách lấy, cache, dùng, gia hạn hoặc tạo lại Vault token cho HTTP requests. | `SessionManager` và lifecycle của Spring. | Request dùng token không còn hợp lệ; tác vụ gia hạn thất bại hoặc không dừng khi shutdown. |
| **Dynamic secret lease** | Quyền sống còn của credential động do engine như Database/PKI cấp; có `lease_id` và TTL khi áp dụng. | Vault secret engine; ứng dụng hoặc `SecretLeaseContainer` nếu được cấu hình. | Mật khẩu DB bị thu hồi dù Vault token của client vẫn còn hiệu lực. |
| **Chứng chỉ PKI** | Danh tính TLS với `notBefore/notAfter`, certificate chain, private key tương ứng. | PKI và TLS consumer. | TLS handshake thất bại do chứng chỉ hết hạn, kể cả Vault token vẫn hợp lệ. |

**Không dùng một TTL để suy ra TTL khác.** Ví dụ: Vault token còn 20 phút không bảo đảm password database dynamic còn hiệu lực 20 phút. Việc renew Vault token cũng không tự renew một dynamic secret lease hoặc chứng chỉ TLS đã cấp.

### Những lớp quan trọng trong Spring Vault

- `ClientAuthentication` biểu diễn cách đăng nhập hoặc lấy token. Một nguồn token cố định, chẳng hạn `TokenAuthentication`, có đặc điểm vòng đời khác cơ chế có thể đăng nhập lại qua AppRole/Kubernetes.
- `SessionManager` cung cấp token cho client. `SimpleSessionManager` có cách quản lý đơn giản; `LifecycleAwareSessionManager` hỗ trợ quản lý vòng đời token và các hoạt động nền theo cấu hình/kiểu token.
- `VaultTemplate` là client gửi request tới các endpoint KV, Transit, PKI, auth... Nó dùng token của session nhưng không có nghĩa một lần gọi `read()` tự xử lý mọi lease mà engine trả về.
- `SecretLeaseContainer` giúp quản lý một số secret lease và sự kiện vòng đời secret, nếu ứng dụng chủ động khai báo sử dụng. Nó có lifecycle riêng và không phải tên khác của token session.
- Spring `ApplicationContext` quản lý tạo/hủy các bean. Các bean lifecycle phải được đăng ký đúng cách để callback cleanup chạy khi context đóng **có trật tự**.

Các API, constructor và mặc định renewal có thể khác theo phiên bản Spring Vault/Spring Cloud Vault. Trong kiểm thử, cần ghi lại phiên bản đang sử dụng và đối chiếu bean/session manager *thực sự được khởi tạo*, đặc biệt nếu ứng dụng tự tạo `VaultTemplate` thay vì dùng auto-configuration.

## 2. Trạng thái vòng đời cần chứng minh

~~~mermaid
stateDiagram-v2
    [*] --> Login: ClientAuthentication
    Login --> Active: Vault phát token + TTL
    Login --> LoginFailed: Không thể chứng minh danh tính
    LoginFailed --> [*]: Báo lỗi có kiểm soát
    Active --> Renewal: Đến thời điểm renew
    Renewal --> Active: Gia hạn thành công
    Renewal --> RenewalFailed: 403 / 5xx / timeout
    RenewalFailed --> Active: Retry hợp lệ hoặc reauthenticate thành công
    RenewalFailed --> Expired: Hết TTL / mất quyền
    Active --> Expired: TTL hết / token bị revoke
    Expired --> Login: Cơ chế có khả năng đăng nhập lại
    Expired --> RequestFailed: Không thể lấy token hợp lệ
    Active --> Shutdown: ApplicationContext.close()
    RenewalFailed --> Shutdown: ApplicationContext.close()
    Expired --> Shutdown: ApplicationContext.close()
    Shutdown --> Stopped: Dừng scheduler / cleanup theo quyền sở hữu token
    Stopped --> [*]
~~~

Cần kiểm thử ba tuyến chính:

1. **Gia hạn được:** một token đủ điều kiện renew vẫn hợp lệ sau mốc TTL ban đầu, request nghiệp vụ tiếp tục thành công và không bị tăng số lần login không cần thiết.
2. **Gia hạn không được hoặc token hết hạn:** ứng dụng phân biệt mất kết nối tạm thời, token không renewable, đã vượt TTL tối đa, bị revoke hoặc credential đăng nhập lại đã mất hiệu lực. Kết quả phải quan sát được và không retry vô hạn.
3. **Đóng context:** các tác vụ renewal/lease liên quan dừng, tài nguyên được giải phóng và token/lease được revoke nếu cơ chế sở hữu và cấu hình yêu cầu. Không giả định callback shutdown chạy khi tiến trình bị `SIGKILL` hoặc host mất điện.

### Hai câu hỏi phải hỏi trước mỗi assertion

- **Token này do ứng dụng tạo ra hay được cấp sẵn bởi một bên khác?** Không nên mặc định ứng dụng thu hồi một token dùng chung mà nó không sở hữu.
- **Bảo đảm nào do framework cung cấp, bảo đảm nào do cấu hình của hệ thống tạo ra?** Một `ApplicationContext.close()` không tự chứng minh rằng Vault đã nhận và xử lý HTTP revoke; nó chỉ khởi động các callback của bean và phải được quan sát riêng.

## 3. Ma trận kiểm thử bắt buộc

| ID | Kịch bản | Điều kiện chủ động tạo | Kết quả cần xác minh |
| --- | --- | --- | --- |
| R1 | Renew thành công | Service token renewable, TTL ngắn, auth/session hỗ trợ renewal. | Token còn hợp lệ sau TTL đầu; có bằng chứng renew trong Vault/audit hoặc lookup. |
| R2 | Token không renewable | Cấp token với `renewable=false` hoặc kiểu không hỗ trợ gia hạn. | Không gọi renew vô nghĩa mãi; request có phản hồi rõ ràng hoặc reauth hợp lệ nếu hỗ trợ. |
| R3 | Chạm giới hạn thời gian sống | Token có `max_ttl`/explicit maximum TTL ngắn. | Renew không kéo dài token vô hạn vượt giới hạn; xử lý expiration/reauth đúng. |
| R4 | Renew API trả lỗi | Fault injection HTTP `403` hoặc `5xx` tại endpoint renew. | Báo lỗi và áp dụng retry/backoff phù hợp, không làm lộ token; không báo renew thành công giả. |
| R5 | Mạng gián đoạn | Ngắt đường tới Vault trong khoảng ngắn. | Timeout hữu hạn; phục hồi khi mạng trở lại nếu token/credential vẫn hợp lệ. |
| R6 | Token bị revoke ngoài ứng dụng | Quản trị viên/test harness revoke token đang dùng. | Lần gọi tiếp theo không còn quyền; session có thể reauth nếu được hỗ trợ, hoặc báo lỗi chính xác. |
| E1 | Token hết hạn thật | TTL ngắn và không renew, quan sát đến sau `expire_time`. | Yêu cầu với token cũ bị từ chối; không nhầm với lỗi DNS/TLS hay policy sai. |
| E2 | Credential đăng nhập lại không còn hiệu lực | Thu hồi/mất AppRole secret ID hoặc workload identity. | Không tạo được token mới; hệ thống không tự fallback sang root token. |
| L1 | Dynamic lease hết hạn | Database credential TTL ngắn; không renew. | Credential DB cũ không còn dùng được theo backend; ứng dụng luân chuyển connection nếu thiết kế hỗ trợ. |
| C1 | Đóng context bình thường | Gọi `ApplicationContext.close()`. | Bean lifecycle được destroy; không còn task renew/lease của context. |
| C2 | Đóng context lặp/đồng thời | Gửi yêu cầu close/stop khi có renew đang diễn ra. | Không phát sinh retry vô tận, không deadlock và không tạo tài nguyên mới sau khi dừng. |
| C3 | Token cấp sẵn/dùng chung | Cấu hình `TokenAuthentication` với token ngoài ứng dụng. | Không tự giả định token bị revoke khi context đóng; kiểm tra đúng contract ownership. |

Ma trận nên tách thành **unit test**, **integration test với Vault thật** và **test lifecycle của context**. Unit test phát hiện logic retry/callback, nhưng chỉ kết nối Vault thật mới chứng minh được TTL, renewal, revoke và policy của server.

## 4. Dựng Vault thử nghiệm với TTL ngắn

Chạy Vault **chỉ cho môi trường kiểm thử**, bằng instance cô lập hoặc Testcontainers với image/tag đã được dự án kiểm soát. Không giảm TTL hoặc tắt TLS ở Vault production để thử lỗi.

Một lựa chọn đơn giản khi học tập là Vault dev server trên máy phát triển:

~~~bash
# Terminal riêng. Chỉ dùng local test, không triển khai production.
vault server -dev \
  -dev-root-token-id=dev-root \
  -dev-listen-address=127.0.0.1:8200
~~~

Ở terminal khác:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_TOKEN="dev-root"

vault status
vault auth enable approle
vault secrets enable -path=secret -version=2 kv
~~~

Nếu dev server đã có KV mount tại `secret/`, không enable trùng; kiểm tra `vault secrets list -detailed` và dùng mount hiện có. Root token `dev-root` là giá trị giả/riêng cho server thử nghiệm, tuyệt đối không dùng trong ứng dụng hay pipeline production.

### Tạo policy và AppRole cho kiểm thử

~~~bash
cat > test-read.hcl <<'POLICY'
path "secret/data/orders/config" {
  capabilities = ["read"]
}
POLICY

vault policy write test-read test-read.hcl
vault kv put secret/orders/config mode=integration-test

vault write auth/approle/role/short-lived \
  bind_secret_id=true \
  token_type=service \
  token_policies=test-read \
  token_ttl=15s \
  token_max_ttl=45s \
  token_num_uses=0 \
  secret_id_ttl=10m \
  secret_id_num_uses=0
~~~

**Giải thích:** role tạo token kiểu `service` có TTL ban đầu 15 giây và tối đa 45 giây theo cấu hình ví dụ; `token_num_uses=0` tránh token bị vô hiệu chỉ vì số lần gọi trong test. TTL thực tế còn chịu giới hạn của auth mount/system và chính sách Vault đang chạy. Lấy giá trị `ttl`, `renewable`, `explicit_max_ttl` từ phản hồi server để xác nhận điều kiện test trước khi assert.

Nhận `role_id` và `secret_id` để test đăng nhập AppRole:

~~~bash
vault read -field=role_id auth/approle/role/short-lived/role-id
vault write -f -field=secret_id auth/approle/role/short-lived/secret-id
~~~

Hai giá trị này là credential thử nghiệm; không commit hoặc xuất sang CI logs. Trong hệ thống test tự động, dùng cơ chế secret input có bảo vệ và dọn tài nguyên khi kết thúc.

### Đăng nhập và kiểm tra token từ CLI

~~~bash
# Ví dụ yêu cầu login; không in toàn bộ response trên hệ thống chia sẻ.
vault write -format=json auth/approle/login \
  role_id="<role-id-test>" \
  secret_id="<secret-id-test>" |
jq '{token_received: (.auth.client_token != null),
     ttl: .auth.lease_duration,
     renewable: .auth.renewable,
     policies: .auth.policies}'
~~~

Khi cần kiểm tra token cụ thể, harness có thể giữ nó trong bộ nhớ và gọi `auth/token/lookup-self` qua đúng token đó. Không in token ra console hoặc file log. Nếu dùng CLI để kiểm tra renew, có thể thử `vault token renew -increment=20s` **sau khi bảo đảm phiên CLI đang sử dụng chính token thử nghiệm**; lệnh này mặc định renew token của CLI, không phải token của ứng dụng Java khác. Đừng vô tình thử trên token root `dev-root` còn nằm trong biến môi trường. So sánh TTL trước/sau; Vault có quyền giới hạn TTL theo policy và max TTL nên không phải yêu cầu renew nào cũng được tăng đúng số giây đã xin.

## 5. Test renew thành công: đo trạng thái thực tế

### Arrange

- Token do auth method phát ra có `renewable=true` và quyền renew đúng contract.
- Dùng `LifecycleAwareSessionManager` hoặc thành phần session mà framework thực sự cấu hình để quản lý login/renew.
- Đặt thời gian sống ngắn để kiểm thử, nhưng đủ dư địa cho độ trễ CI; ví dụ TTL 15–30 giây và max TTL dài hơn.
- Gắn listener/telemetry phù hợp nếu phiên bản Spring Vault cung cấp sự kiện renewal; dùng Vault audit/lookup để đối chiếu hành vi.

### Act

1. Lấy token thông qua `SessionManager` và thực hiện một `VaultTemplate` read có policy hợp lệ.
2. Ghi **thời điểm cấp, TTL server trả về, lease/token metadata không nhạy cảm và mốc dự kiến renew**.
3. Đợi bằng polling có deadline đến sau TTL ban đầu, nhưng trước khi tổng max TTL kết thúc; trong khi đó cho scheduler của ứng dụng chạy.
4. Thực hiện lại cùng request KV và đọc trạng thái token/renewal từ Vault.

### Assert

- Request trước và sau mốc TTL ban đầu đều thành công, **nếu** renewal được kích hoạt đúng.
- Có bằng chứng server cho phép gia hạn, không chỉ thấy một HTTP 200 từ cache.
- Bộ lập lịch không tạo vô hạn token mới hoặc gọi renew dồn dập.
- Sau khi đóng context, hoạt động renew ngừng theo contract.

**Chú ý về cách chứng minh:** nếu session tự **đăng nhập lại** để lấy token mới thì request sau TTL vẫn có thể thành công, nhưng đó **không phải** chứng minh renew token cũ thành công. Muốn kiểm thử renew, cần theo dõi token accessor (hoặc định danh được phép quan sát) và sự kiện renew; hạn chế log giá trị token bí mật.

## 6. Test renew thất bại và quá TTL

### 6.1. Renew bị Vault từ chối

Lỗi có thể đến từ token đã revoke, không renewable, đạt giới hạn max TTL hoặc chính sách/route thay đổi. Với bộ giả lập HTTP hoặc fault proxy trong test, tạo phản hồi lỗi đúng endpoint renew mà không cần phá các endpoint còn lại.

**Assertion cần có:**

- Renewal failure được bắt và báo qua cơ chế callback/error/metric của phiên bản framework.
- Nếu có retry, retry phải hữu hạn hoặc có backoff, không tạo vòng gọi `/auth/token/renew-self` liên tục trong vài mili giây.
- Không log bearer token trong exception, HTTP trace hay request body.
- Nếu còn credential đăng nhập hợp lệ và session manager được thiết kế để reauth, phải kiểm tra việc tạo phiên mới bằng kiểm chứng độc lập.
- Nếu không thể khôi phục, request nghiệp vụ thất bại rõ ràng; không tự mở rộng policy hoặc âm thầm dùng credential quyền cao.

Một lần nhận `403` không đủ để kết luận lỗi gia hạn: kiểm tra đó là `403` từ `renew-self`, `login` hay từ endpoint KV/Transit/PKI.

### 6.2. Renew bị timeout/HTTP 5xx

Trong môi trường staging, có thể dùng proxy gây lỗi có điều kiện:

~~~text
Java + Spring Vault
  → fault proxy (chỉ renew-self bị delay/503)
  → Vault test instance
~~~

Giữ endpoint login và secret read hoạt động để cô lập lỗi renew. Sau khi bật fault, xác nhận request deadline, số lần retry và cảnh báo. Gỡ fault trước khi TTL hết và xác nhận client khôi phục nếu token còn hạn; chạy thêm kịch bản fault kéo dài qua TTL để xem ứng dụng báo hết hạn và reauth theo contract.

Nếu ngắt **toàn bộ** mạng giữa Java và Vault, HTTP read và renew đều lỗi. Kịch bản đó kiểm tra khả năng chịu lỗi mạng chung, không cô lập riêng logic renewal.

### 6.3. Không renewable hoặc đã đạt max TTL

Không có một quy tắc “cứ gọi renew là kéo dài được mãi”. Vault có thể giới hạn theo TTL/token type/max TTL/explicit max TTL hoặc cấu hình của auth method. Hãy kiểm tra phản hồi metadata của token:

~~~json
{
  "renewable": true,
  "ttl": 15,
  "creation_ttl": 15,
  "explicit_max_ttl": 0
}
~~~

Đối tượng JSON trên chỉ **minh họa một tập trường có thể xem bằng token lookup**, không phải phản hồi luôn có các giá trị này. `explicit_max_ttl: 0` không đồng nghĩa token có thể sống vô hạn; giới hạn khác vẫn có thể áp dụng. Test nên sử dụng deadline dựa trên thông tin thực tế từ Vault, không chỉ dựa vào cấu hình role mong đợi.

## 7. Test token hết hạn hoặc bị revoke

Token `expired` và token `revoked` đều có thể khiến request API bị từ chối, nhưng đường gây lỗi và khả năng khôi phục khác nhau.

### Hết hạn tự nhiên

1. Trong test cô lập, tạo token TTL rất ngắn và không có thành phần auto-renew.
2. Dùng token đó đọc một KV secret được cấp quyền; xác nhận thành công.
3. Dùng polling đến khi server xác định token không còn hợp lệ.
4. Gọi lại đúng endpoint KV với token cũ; xác nhận bị từ chối, không xem `403` là secret “không tồn tại”.
5. Nếu đang kiểm thử session có cơ chế reauth, kích hoạt một request qua session và kiểm chứng client có cấp token mới hợp lệ hay trả lỗi đúng thiết kế.

Không dùng `Thread.sleep(15000)` như assertion duy nhất: CI có thể chậm, TTL thực tế khác TTL request, scheduler có jitter và token có thể đã được renew. Polling theo deadline và đọc dấu hiệu từ server đáng tin cậy hơn.

### Revoke chủ động

Có thể dùng token quản trị *chỉ trong test* để revoke token đang dùng bởi ứng dụng. Trước revoke, phải xác minh token đó **do test tạo ra** và không dùng chung với công việc khác. Sau revoke, endpoint `auth/token/lookup-self` hoặc KV read với token cũ phải bị từ chối. Quan sát đường xử lý của `SessionManager` sau đó.

**Cảnh báo về kiểm thử:** không dùng token root hoặc shared service token để thử revoke. Revoke token có thể ảnh hưởng các lease/child token tùy quan hệ token và cơ chế Vault; chỉ làm trên môi trường cô lập.

### Phân biệt revoke và permission denied

| Kết quả | Khả năng | Test tiếp theo |
| --- | --- | --- |
| `auth/token/lookup-self` từ chối token | Token hết hạn, bị revoke hoặc không hợp lệ. | Đối chiếu thời điểm, audit event và hành động revoke/expiry. |
| `lookup-self` thành công nhưng KV read `403` | Token hợp lệ nhưng thiếu capability trên path. | Kiểm policy, KV v1/v2, path và `capabilities-self` khi có quyền. |
| Login `403` | Credential auth/role bị từ chối. | Kiểm auth mount, identity, bind constraint, credential. |
| TCP/TLS failure trước HTTP | Mạng hoặc truststore chưa hoạt động. | Kiểm DNS, cổng, CA, SAN, timeout rồi mới kiểm token. |

## 8. Test vòng đời dynamic secret lease riêng biệt

Một lỗi phổ biến là chỉ kiểm thử `VaultTemplate` đọc được credential từ `database/creds/orders-reader` rồi kết luận hệ thống đã xử lý vòng đời đúng. Thực tế Vault có thể phát lease `lease_id` và `lease_duration` cho credential mới. Việc tự gọi `VaultTemplate.read(...)` **không tự đảm bảo** đã đăng ký lease đó với `SecretLeaseContainer`.

Ma trận cho dynamic secret:

| Tình huống | Test cần làm |
| --- | --- |
| Lấy credential lần đầu | Xác nhận data đúng schema, `lease_id` và TTL nếu engine trả lease. |
| Lease sắp hết hạn | Nếu dùng `SecretLeaseContainer`, quan sát sự kiện renewal/rotation đúng cấu hình. |
| Lease không renewable | Xác minh cấp credential mới hoặc đường thất bại được xử lý có kiểm soát. |
| Lease bị revoke | Credential cũ không còn quyền trên hệ thống đích, không chỉ Vault API trả một mã lỗi. |
| Connection pool giữ credential cũ | Xác minh connection mới thật sự dùng credential mới; pool đã refresh/recreate phù hợp. |
| Context đóng | Đóng lease container, dừng job và cleanup/revoke theo ownership và cấu hình. |

Nếu cần dùng Transit encryption, test quyền token và lỗi khi token hết hạn bằng một request `transit/encrypt/<key>` phù hợp. Với PKI, phân biệt **lease/revocation** do Vault quản lý và **certificate `notAfter`**: cert vẫn có thể hết hạn độc lập với Vault token, và việc đổi token không tự reload keystore TLS.

## 9. Đóng ApplicationContext: phải kiểm tra điều gì?

Spring Boot đóng `ApplicationContext` khi dừng ứng dụng có trật tự, ví dụ `SpringApplication.exit(...)` hoặc nhận tín hiệu dừng có hỗ trợ shutdown hook. Khi đó Spring gọi lifecycle của các bean được quản lý. Đóng context không tương đương JVM bị kill cưỡng bức.

### Kịch bản C1: Đóng bình thường

Chuẩn bị một ứng dụng test với:

- `ClientAuthentication` và `SessionManager` đã được đăng ký trong context, không phải instance tạm được tạo ngoài Spring rồi quên đóng.
- Thành phần renewal/lease đang chạy và có telemetry đếm hành động.
- Token do test cấp (nếu cần kiểm tra revoke) được cô lập khỏi môi trường khác.
- `ApplicationContext` có thể đóng bằng `close()` trong `try/finally`.

Sau khi gọi `close()`, xác minh:

1. Callback `destroy`/`close` được thực thi cho bean lifecycle đúng contract.
2. Tác vụ gia hạn/đọc lease của context **không phát sinh request mới sau khi context đã dừng** (cho phép xử lý race của request đã bắt đầu trước khi close).
3. Tài nguyên như scheduler, executor, HTTP connection pool và listener được giải phóng theo ownership.
4. Nếu session manager được thiết kế để thu hồi token do mình quản lý, phải kiểm tra **Vault audit/lookup** để chứng minh revoke thực sự thành công; không suy luận chỉ từ callback.
5. Nếu credential được cấp sẵn bằng `TokenAuthentication` và dùng chung, không tự kỳ vọng hoặc ép ứng dụng revoke nó khi shutdown.

### Kịch bản C2: Renew và close cạnh tranh

Tạo rào đồng bộ trong HTTP test server/fault proxy để một request renew đang in-flight, sau đó gọi `context.close()` từ thread kiểm thử. Giải phóng rào và xác minh:

- Không deadlock hoặc chờ vô hạn.
- Không có yêu cầu renew mới sau khi scheduler dừng.
- Nếu renew và revoke cùng xảy ra, kết quả không làm tái phát token hoặc khởi tạo session mới sau khi close.
- Mọi exception từ cleanup được ghi nhận theo chính sách logging, không bị xem là thông báo “shutdown thành công” khi tài nguyên vẫn rò rỉ.

Tùy phiên bản framework, một request đang chạy có thể hoàn tất hoặc bị hủy khi context đóng. Assertion ổn định nên tập trung vào **trạng thái cuối và absence of new tasks**, thay vì bắt một thứ tự callback vô căn cứ.

### Kịch bản C3: Container bị kill

`SIGKILL`, OOM kill hoặc mất điện không cho Java chạy shutdown hooks. Không đặt tính an toàn của hệ thống hoàn toàn vào callback `destroy()`. Cần thêm TTL hữu hạn, revoke từ điều phối/quản trị khi cần, lease expiration phía Vault và giới hạn chính sách phù hợp. Trong Kubernetes, xác minh `terminationGracePeriodSeconds` và thời gian để workload dừng có trật tự, nhưng luôn có phương án cho việc shutdown hook không chạy.

## 10. Mẫu JUnit 5: xác minh Spring context gọi callback hủy

Ví dụ sau là **unit test cho cơ chế đăng ký lifecycle của Spring**. Nó không cần Vault thật và **không khẳng định token đã được revoke**, nhưng giúp phát hiện trường hợp resource không nằm trong `ApplicationContext` nên không được destroy.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class ContextShutdownTest {

    static class TrackedResource implements DisposableBean {
        final AtomicInteger destroyCalls = new AtomicInteger();

        @Override
        public void destroy() {
            destroyCalls.incrementAndGet();
        }
    }

    @Test
    void closeInvokesDestroyExactlyOnce() {
        TrackedResource resource = new TrackedResource();

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {

            context.registerBean(TrackedResource.class, () -> resource);
            context.refresh();

            assertSame(resource, context.getBean(TrackedResource.class));
            assertEquals(0, resource.destroyCalls.get());
        }

        assertEquals(1, resource.destroyCalls.get());
    }
}
~~~

Khi chuyển ví dụ sang ứng dụng Spring Vault thật, cần kiểm tra chính **bean `LifecycleAwareSessionManager`/`SecretLeaseContainer` và HTTP client** có được quản lý bởi context hay không. Không thay một integration test bằng việc chỉ kiểm `TrackedResource`. Nếu code tự khởi tạo session manager ngoài Spring, phải đăng ký và đóng nó theo đúng lifecycle thay vì trông đợi `ApplicationContext.close()` có thể tìm được object không phải bean.

### Mẫu JUnit 5 kiểm chứng token sai bị từ chối (cần Vault test instance)

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

class InvalidTokenIntegrationTest {

    @Test
    void vaultRejectsUnknownClientToken() {
        // Chỉ chạy khi Vault test instance HTTP local đang hoạt động.
        VaultEndpoint endpoint = VaultEndpoint.create("127.0.0.1", 8200);
        endpoint.setScheme("http");

        VaultTemplate vault = new VaultTemplate(
                endpoint, new TokenAuthentication("invalid-integration-token"));

        assertThrows(RuntimeException.class,
                () -> vault.read("secret/data/orders/config"));
    }
}
~~~

Ví dụ này xác minh token không hợp lệ bị server/test client từ chối. Trong suite thực tế, bổ sung điều kiện setup xác nhận Vault đang chạy và kiểm tra **mã HTTP cụ thể hoặc loại exception phù hợp phiên bản**, tránh test pass do một lỗi socket/DNS ngẫu nhiên. Có thể dùng Testcontainers để khởi động Vault bằng image cố định rồi dựng auth role, secrets và policy trong setup. Token ở ví dụ là chuỗi giả, không phải credential thật.

## 11. Polling có deadline thay cho sleep cố định

Kiểm thử TTL và scheduler cần tránh assertion phụ thuộc cứng vào tốc độ máy CI. Với Java/JUnit 5, có thể dùng helper polling nhỏ:

~~~java
import static org.junit.jupiter.api.Assertions.fail;

import java.time.Duration;
import java.util.function.BooleanSupplier;

final class Eventually {
    private Eventually() {}

    static void until(Duration timeout, BooleanSupplier condition)
            throws InterruptedException {
        long deadline = System.nanoTime() + timeout.toNanos();
        do {
            if (condition.getAsBoolean()) {
                return;
            }
            Thread.sleep(200);
        } while (System.nanoTime() < deadline);

        fail("Expected condition not reached before deadline");
    }
}
~~~

Ví dụ dùng test condition đến khi token test không còn lookup được, hoặc đến khi listener đã nhận sự kiện renew:

~~~java
Eventually.until(Duration.ofSeconds(30),
        () -> renewalEvents.get() >= 1);
~~~

`renewalEvents` chỉ là biến đếm trong fixture test (ví dụ `AtomicInteger`), **không phải một API có sẵn của Spring Vault**. Trong môi trường có thư viện Awaitility, có thể dùng nó thay helper này. Khi điều kiện ném exception tạm thời, cần thiết kế wrapper phân loại lỗi mong đợi, tránh nuốt mọi exception và biến lỗi cấu hình thành timeout khó chẩn đoán.

Đừng để thời hạn polling vượt quá mức hợp lý của suite. TTL 5 giây có thể quá thấp cho JVM khởi động và networking CI; chọn giá trị đủ nhỏ để test gọn nhưng đủ rộng để không tạo flaky test.

## 12. Test lỗi cùng lúc và tính phục hồi

Không phải mọi lỗi token đều có cùng hướng giải quyết. Thực hành thử theo trình tự:

~~~mermaid
flowchart TD
    A["VaultTemplate request thất bại"] --> B{"Có HTTP response từ Vault?"}
    B -- "Không" --> C["DNS / TCP / TLS / timeout"]
    B -- "Có" --> D{"Endpoint nào lỗi?"}
    D -- "/auth/token/renew-self" --> E["Kiểm TTL, renewable, revoke, max TTL"]
    D -- "/auth/.../login" --> F["Kiểm workload identity, role, auth mount"]
    D -- "/secret/... hoặc /transit/... hoặc /pki/..." --> G["Kiểm token validity, policy, engine path"]
    E --> H{"Có thể tái xác thực?"}
    H -- "Có, theo thiết kế" --> I["Xin token mới bằng credential hợp lệ"]
    H -- "Không" --> J["Báo lỗi/giảm tính sẵn sàng có kiểm soát"]
    C --> K["Retry có giới hạn/backoff nếu lỗi tạm thời"]
~~~

### Kịch bản thực tế 1: Token renew thất bại nhưng request vẫn chạy

Trong khoảng trước khi token hết hạn, một renew thất bại do Vault trả `503`, nhưng KV read tiếp theo vẫn có thể thành công vì token còn TTL. Test phải phát hiện renew failure thông qua callback/metric/audit, không chờ đến lúc request nghiệp vụ lỗi mới biết. Khi Vault phục hồi, kiểm tra renewal hoặc reauth theo cơ chế session đã cấu hình.

### Kịch bản thực tế 2: KV read 403 ngay sau khi đổi policy

Token chưa hết hạn nhưng mất quyền trên secret path. Nếu `lookup-self` vẫn thành công mà KV đọc `403`, việc renew token không nhất thiết giải quyết policy. Kiểm tra identity, token policies, namespace Vault (nếu dùng Enterprise), mount và KV v2 `data` path. Test không nên coi mọi 403 là “session expired”.

### Kịch bản thực tế 3: Agent cấp token, ứng dụng giữ bản cũ

Một Vault Agent có thể ghi token mới vào sink file, nhưng nếu ứng dụng chỉ đọc token một lần khi khởi động, session manager sử dụng token cố định cũ sau rotation. Test phải mô phỏng file update và xác minh ứng dụng **có cơ chế reload** hoặc restart đúng kế hoạch. Nếu chỉ cấu hình `TokenAuthentication` với chuỗi cố định, đừng giả định Spring Vault sẽ tự quan sát thay đổi tệp bên ngoài.

### Kịch bản thực tế 4: Context đóng khi request renew đang chờ timeout

Test cần đặt network timeout hữu hạn, đóng context khi renew vẫn in-flight và xác minh không có job mới, pool được giải phóng và shutdown không treo vô hạn. Nếu cleanup HTTP không đến được Vault, ghi nhận revoke chưa được xác minh; TTL server là lớp bảo vệ còn lại.

## 13. Giám sát và logging phục vụ kiểm thử vòng đời

| Chỉ số/sự kiện | Ý nghĩa | Tránh ghi |
| --- | --- | --- |
| `vault_auth_login_success/failure` | Bao nhiêu lần app login/reauth và nguyên nhân lỗi. | JWT, AppRole secret ID, Vault token. |
| `vault_token_renew_success`, `vault_token_renew_failure` | Renewal có diễn ra và lỗi tại sao. | Token string, toàn bộ HTTP request/response. |
| `vault_token_ttl_remaining` | TTL còn lại theo metadata đã được phép đọc. | Secret nội dung, accessor trong nhãn metrics có cardinality cao. |
| `vault_secret_lease_renew_failure` | Renewal lease dynamic secret gặp lỗi. | Username/password, lease data nhạy cảm. |
| `vault_context_shutdown_duration` | Thời gian chạy cleanup và đóng context. | Payload chứa token hoặc private key. |
| `vault_post_shutdown_renew_requests` | Có request renewal sau khi context dừng hay không (mục tiêu bằng 0). | Header `X-Vault-Token`. |

Các tên trên là **gợi ý tên metric của hệ thống**, không phải metric mặc định mà Spring Vault cam kết xuất ra. Tùy phiên bản, có thể lấy tín hiệu từ listener, log đã lọc, Vault audit device hoặc HTTP client instrumentation.

Log nên kèm **tên logical service**, auth method, mã HTTP, operation (login/renew/lookup/read), thời điểm và loại exception. Khi kiểm tra lỗi TLS hoặc policy, tránh bật HTTP wire log toàn bộ vì body đăng nhập và header có thể chứa bearer credential. Cần phân biệt token value với token accessor: accessor ít nhạy cảm hơn token nhưng vẫn phải bảo vệ theo quy định nội bộ, không đưa vào label công khai.

## 14. Tiêu chí hoàn thành kiểm thử

Một bộ kiểm thử vòng đời đủ đáng tin cậy phải trả lời được:

1. **Nguồn token:** request dùng `SessionManager` nào, auth method nào, token được ứng dụng sở hữu hay cấp sẵn?
2. **Đăng nhập:** thành công khi identity hợp lệ; bị từ chối khi auth role/identity sai.
3. **Gia hạn:** token renewable được renew theo thời gian; có bằng chứng API/lookup hoặc sự kiện, không nhầm với re-login.
4. **Hết hạn/revoke:** token cũ không còn dùng được; đường khôi phục theo thiết kế được kiểm chứng.
5. **Secret lease:** dynamic credentials/PKI được quản lý theo TTL riêng, không gộp với Vault token.
6. **Tắt ứng dụng:** `ApplicationContext.close()` gọi lifecycle của bean được quản lý, scheduler/lease listeners dừng; hành vi revoke được xác minh riêng nếu bắt buộc.
7. **Lỗi đồng thời:** renew và close, revoke và request, mất mạng và reauth không gây vòng lặp hoặc rò rỉ thread.
8. **Quyền:** test dùng policy tối thiểu, không fallback sang token root hay nới wildcard khi request bị `403`.
9. **Quan sát:** đo được lỗi ở đúng tầng mà không lộ token, secret, private key.
10. **Tính lặp lại:** môi trường Vault thử nghiệm được cô lập, setup/cleanup rõ ràng, TTL và polling không gây false positive.

**Kết luận:** kiểm thử vòng đời trong Spring Vault cần chứng minh cả **đường hoạt động bình thường**, **đường lỗi khi token hoặc lease không còn hợp lệ**, và **đường đóng tài nguyên của `ApplicationContext`**. Kiểm tra có chủ đích từng bước từ `ClientAuthentication` → `SessionManager` → `VaultTemplate` → secret engine giúp ngăn phiên hết hạn âm thầm, retry vô tận, rò rỉ scheduler và việc dùng credential vượt quá quyền hoặc thời gian sống đã được Vault cấp.
