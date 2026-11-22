# 17.10. Refresh trong nhiều instance và điều phối cập nhật kho token

## 1. Bài toán: một refresh token nhưng nhiều instance cùng sử dụng

Trong Spring Security OAuth 2.0/OIDC Client, ứng dụng thường giữ một <code>OAuth2AuthorizedClient</code> gồm ClientRegistration, principal name, access token và refresh token (nếu Authorization Server đã cấp). Khi access token hết hạn hoặc sắp hết hạn, <code>OAuth2AuthorizedClientManager</code> có thể dùng refresh token để xin access token mới.

Ở môi trường **một instance, ít request đồng thời**, thao tác này khá dễ hình dung. Nhưng khi triển khai nhiều replica sau load balancer hoặc nhiều worker dùng chung database, những request gần như đồng thời có thể đọc **cùng một bản token cũ** và cùng quyết định refresh.

Ví dụ:

~~~text
Kho token đang có:
    registrationId = company
    principalName  = user-123
    access token   = A0 (sắp hết hạn)
    refresh token  = R0

Instance A đọc R0
Instance B đọc R0
Instance A gửi R0 tới Token Endpoint
Instance B cũng gửi R0 tới Token Endpoint
~~~

Nếu OpenID Provider/Authorization Server sử dụng **refresh token rotation**, mỗi lần refresh thành công có thể phát refresh token mới và làm refresh token cũ không còn dùng được:

~~~text
R0  --refresh thành công-->  A1 + R1
R0  --dùng lại------------->  invalid_grant hoặc phát hiện reuse
~~~

Kết quả không chỉ là thêm một HTTP request. Tùy chính sách provider, việc dùng lại R0 còn có thể kích hoạt cơ chế **reuse detection** và vô hiệu hóa cả một token family, khiến R1 vừa được cấp cũng không thể dùng tiếp.

Vì vậy, bài toán của hệ thống nhiều instance là:

> Làm thế nào bảo đảm các lượt refresh của **cùng một authorized client** được phối hợp, và dữ liệu access token/refresh token trong kho luôn được cập nhật nhất quán?

Chủ đề này nằm ở ranh giới giữa **OAuth2 Client**, **concurrency control**, **persistent storage** và **distributed systems**. Không có một câu lệnh <code>refreshToken()</code> đơn lẻ có thể tự giải quyết tất cả.

## 2. Mục tiêu và thuật ngữ

Sau bài học, người học có thể:

1. Giải thích race condition khi nhiều instance cùng refresh một authorized client.
2. Phân biệt refresh token rotation, token reuse detection và access token expiry.
3. Hiểu rằng authorized client cần lưu theo đúng <code>(registrationId, principalName)</code>, có phân vùng issuer/tenant khi cần.
4. Thiết kế **single-flight refresh** theo khóa, tức một thời điểm chỉ có một lượt refresh hữu hiệu cho một authorized client.
5. Chọn đúng cơ chế **distributed lock**, **optimistic concurrency/CAS**, **fencing** hoặc mô hình single writer.
6. Đảm bảo lưu **access token và refresh token mới như một bản cập nhật nhất quán**.
7. Xử lý lỗi <code>invalid_grant</code> và các failure handler mà không xóa nhầm bản token mới của instance khác.
8. Tích hợp vào Spring Security manager/service mà không nhầm giữa storage, refresh provider và lock nghiệp vụ.

Một số thuật ngữ:

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Authorized client** | Liên kết một ClientRegistration, principal name và các token được cấp |
| **Refresh token rotation** | Refresh thành công phát refresh token mới và làm token cũ không tiếp tục dùng như trước |
| **Single-flight** | Các request cùng cần một kết quả thì chỉ một request thực hiện công việc, những request còn lại dùng kết quả |
| **Lost update** | Bản ghi mới bị một ghi đè muộn bằng dữ liệu cũ |
| **CAS (compare-and-swap)** | Chỉ ghi khi phiên bản/trạng thái hiện tại còn đúng như đã quan sát |
| **Fencing token** | Số thế hệ/quyền sở hữu tăng dần, giúp storage từ chối một writer cũ dù lease lock của nó hết hạn |
| **Lease** | Lock có thời hạn, cần được gia hạn hoặc kiểm tra trước khi thực hiện thao tác |
| **Token family** | Nhóm refresh token liên quan trong chính sách rotation/reuse detection của provider |

## 3. Spring Security quản lý refresh token như thế nào?

Các thành phần chính:

~~~mermaid
flowchart TD
    APP["Request hoặc background job"] --> M["OAuth2AuthorizedClientManager"]
    M --> REG["ClientRegistrationRepository"]
    M --> STORE["OAuth2AuthorizedClientService hoặc Repository"]
    M --> P["OAuth2AuthorizedClientProvider"]
    P --> RT["Refresh Token Provider"]
    RT --> OP["Authorization Server /token"]
    OP --> RT
    RT --> M
    M --> STORE
    STORE --> DB["Database / Session / Distributed Store"]
~~~

Trong một lần sử dụng:

1. Manager chọn ClientRegistration.
2. Manager tải <code>OAuth2AuthorizedClient</code> theo registration và principal.
3. Refresh token provider kiểm tra access token đã/sắp hết hạn và refresh token có sẵn.
4. Nếu đủ điều kiện, provider gửi refresh token grant tới Token Endpoint.
5. Authorization Server trả access token mới và có thể trả refresh token mới.
6. Manager lưu authorized client đã cập nhật qua success handler và service/repository tương ứng.

### 3.1. Những abstraction cần phân biệt

| Component | Vai trò | Tự tạo distributed lock? |
|---|---|---|
| <code>ClientRegistrationRepository</code> | Cấu hình Client, issuer, grant, endpoint | Không |
| <code>OAuth2AuthorizedClient</code> | Trạng thái token hiện tại cho principal | Không |
| <code>OAuth2AuthorizedClientService</code> | Lưu, tải, xóa authorized client theo registration/principal | Không mặc định đảm bảo single-flight refresh |
| <code>OAuth2AuthorizedClientRepository</code> | Lưu authorized client trong ngữ cảnh Servlet | Không mặc định đảm bảo điều phối giữa node |
| <code>OAuth2AuthorizedClientProvider</code> | Thực hiện refresh grant khi phù hợp | Không mặc định tạo distributed lock |
| <code>OAuth2AuthorizedClientManager</code> | Điều phối provider và persistence | Không mặc định serialize refresh trên toàn cluster |
| Lock/CAS adapter của ứng dụng | Kiểm soát đồng thời tại ranh giới token state | Phải được thiết kế hoặc cung cấp riêng |

Điểm quan trọng: **chuyển từ in-memory service sang JDBC service không tự động ngăn hai node cùng refresh**. JDBC giúp chia sẻ bản ghi token, nhưng nếu cả hai đọc cùng phiên bản cũ và đều gọi Token Endpoint, race vẫn tồn tại.

### 3.2. Khóa định danh authorized client

Với <code>OAuth2AuthorizedClientService</code>, tra cứu thường dựa trên:

~~~text
registrationId + principalName
~~~

Ví dụ:

~~~text
(company, user-123)
(partner, user-123)
(company, user-456)
~~~

Đây là ba authorized client khác nhau; không nên khóa toàn bộ ứng dụng chỉ để refresh một người dùng.

Trong hệ thống multi-tenant/multi-issuer, principal name phải được thiết kế không va chạm. Một subject <code>123</code> từ issuer A không mặc nhiên là cùng người với subject <code>123</code> từ issuer B. Nếu registration ID và principal name không đủ phân vùng tenant, cần sửa thiết kế identity/storage trước khi thêm lock.

## 4. Timeline race condition với refresh token rotation

Giả sử R0 chỉ dùng thành công một lần và OP trả R1 sau refresh.

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Instance A
    participant B as Instance B
    participant DB as Authorized Client Store
    participant OP as Token Endpoint
    A->>DB: load(company, user-123)
    DB-->>A: A0, R0, version=7
    B->>DB: load(company, user-123)
    DB-->>B: A0, R0, version=7
    A->>OP: refresh_token=R0
    OP-->>A: A1, R1
    B->>OP: refresh_token=R0
    OP-->>B: invalid_grant / reuse detection
    A->>DB: save A1,R1
    B->>DB: error handler có thể xóa authorized client
    Note over DB: Nếu xóa không điều kiện, bản A1,R1 vừa lưu có thể bị mất
~~~

Race này có ít nhất ba hậu quả:

**1. Request thứ hai thất bại.** B nhận <code>invalid_grant</code> dù từ góc nhìn ban đầu cả A và B đều có token đang nằm trong storage.

**2. Trạng thái mới bị xóa.** Nếu B nhận lỗi rồi chạy failure handler xóa authorized client chỉ bằng registration/principal, nó có thể xóa bản A1/R1 mà A vừa lưu.

**3. Token family bị ảnh hưởng.** Nếu OP xem hành vi dùng lại R0 là dấu hiệu token bị đánh cắp, nó có thể vô hiệu hóa các refresh token liên quan. Tùy chính sách OP, R1 trong database cũng có thể không dùng được.

Không phải provider nào cũng có cùng chính sách. Có provider cho phép một khoảng grace period, có provider trả refresh token mới theo từng lần, có provider không rotation. **Không được giả định provider sẽ chấp nhận hai request refresh đồng thời** chỉ vì môi trường thử nghiệm chưa thấy lỗi.

### 4.1. Race không chỉ xuất hiện giữa hai server

Hai thread trên cùng instance cũng có thể gặp race nếu đồng thời xử lý hai HTTP request của một principal. Các nguồn gây refresh cạnh tranh gồm:

- Hai tab trình duyệt đồng thời gọi backend.
- API gateway retry request.
- Một request web và một background job dùng cùng authorized client.
- Hai replica sau load balancer.
- Một scheduler chạy trên nhiều node.
- Một instance bị timeout rồi retry khi lần refresh cũ vẫn đang xử lý.

Vì vậy điều phối cần xét **mọi code path có thể thực hiện refresh**, không chỉ một controller.

## 5. Race thứ hai: lost update và stale write

Ngay cả khi OP không vô hiệu hóa token family vì reuse, storage có thể bị ghi sai thứ tự.

Ví dụ:

~~~text
T0  Kho token: access=A0, refresh=R0, version=7
T1  A đọc version=7
T2  B đọc version=7
T3  A refresh thành công: A1,R1
T4  A lưu A1,R1, version=8
T5  B lưu một snapshot cũ hoặc kết quả chậm dựa trên R0
T6  Kho token bị ghi đè bằng trạng thái cũ/không còn hợp lệ
~~~

Trong một refresh rotation nghiêm ngặt, B có thể không nhận token mới; nhưng **stale write** còn xảy ra khi:

- Có nhiều nơi cùng gọi <code>saveAuthorizedClient()</code>.
- Một node cập nhật authorities/session state rồi vô tình lưu lại authorized client cũ.
- Hai lượt refresh có kết quả khác nhau do provider cho phép reuse/grace period.
- Lock hết lease nhưng writer cũ vẫn hoàn thành request và ghi muộn.

Một giải pháp chỉ ngăn request đến Token Endpoint đồng thời nhưng không bảo vệ bước ghi vẫn có thể gặp lost update.

### 5.1. Cần bảo toàn nguyên cặp access/refresh token

Sau khi refresh thành công:

~~~text
Before: access=A0, refresh=R0
After:  access=A1, refresh=R1
~~~

Không được lưu A1 nhưng vẫn giữ R0 khi OP đã rotation. Nếu response không trả refresh token mới, OAuth2 refresh logic thường cần duy trì refresh token trước đó theo hợp đồng của token response; nếu có R1 thì phải thay đúng R1.

**Toàn bộ authorized client phải được lưu như một trạng thái nhất quán**, không cập nhật access token và refresh token bằng hai thao tác rời nhau để các node khác nhìn thấy trạng thái nửa cũ nửa mới.

## 6. Các chiến lược điều phối

Không có một giải pháp duy nhất phù hợp cho mọi kiến trúc.

| Chiến lược | Ý tưởng | Ưu điểm | Rủi ro/giới hạn |
|---|---|---|---|
| **Một instance sở hữu refresh** | Mọi yêu cầu refresh cho cùng key qua một worker/single writer | Dễ suy luận thứ tự | Cần hàng đợi/routing và cơ chế failover |
| **Distributed lock theo key** | Chỉ một node giữ lock khi refresh | Tránh gọi Token Endpoint đồng thời nếu mọi node tuân thủ | Lease hết hạn, node pause/crash, stale writer |
| **Optimistic CAS/version** | Chỉ ghi nếu version chưa đổi | Ngăn lost update | Một mình CAS **không ngăn hai request dùng R0 tại OP** |
| **Lock + CAS/fencing** | Serialize refresh rồi bảo vệ cập nhật state | Chống cả duplicate refresh và stale write tốt hơn | Triển khai phức tạp hơn, cần thời hạn lock và storage đúng |
| **Database row lock** | Dùng transaction/row-level lock để serialize | Tận dụng DB có sẵn | Giữ transaction trong HTTP call có thể tạo bottleneck/timeout |
| **Single-flight cache trong JVM** | Các thread một node dùng chung future | Giảm refresh trùng nội bộ | Không phối hợp giữa các replica |

**Khuyến nghị thực hành:** Với hệ thống nhiều instance có refresh token rotation, thường cần **điều phối per-key trước khi gọi Token Endpoint**, **đọc lại token sau khi có quyền refresh**, và **bảo vệ cập nhật storage bằng version/fencing** nếu lock có thể hết hạn hoặc có code path khác ghi dữ liệu.

### 6.1. Khóa theo key, không khóa toàn cục

Không nên dùng một lock duy nhất:

~~~text
lock = "oauth2-refresh-global"
~~~

Khi đó user A refresh sẽ chặn user B dù không liên quan.

Thay bằng key ổn định dựa trên:

~~~text
oauth2-refresh:{registrationId}:{principalKey}
~~~

Trong môi trường multi-tenant, thêm namespace tenant hoặc issuer đã được xác minh. Không dùng chuỗi principal tùy ý chưa xác thực để tạo khóa có thể chiếm tài nguyên.

Nếu khóa được lưu ở Redis hoặc hệ thống quan sát được, có thể **băm principal identifier** để tránh lộ PII trong tên key. Cần dùng một cách canonicalize duy nhất để tất cả node tính ra cùng key.

## 7. Thuật toán single-flight với double-check

Một quy trình an toàn hơn:

~~~text
function authorizeWithCoordinatedRefresh(registration, principal):
    key = stableKey(registration, principal)

    current = store.load(key)
    if current đã có access token còn dùng được theo chính sách:
        return current

    acquire distributed lock cho key, có timeout
    try:
        latest = store.load(key)  // đọc lại sau khi giữ lock

        if latest đã được node khác refresh và token còn dùng được:
            return latest

        result = refresh bằng refresh token mới nhất trong latest

        save result atomically với version/fencing
        return trạng thái đã commit
    finally:
        release lock chỉ nếu vẫn là owner
~~~

Đây là **pseudocode**, không phải mã thư viện Spring Security.

### 7.1. Vì sao phải load hai lần?

Giả sử A và B đều thấy A0 sắp hết hạn. A lấy lock trước, refresh rồi lưu A1/R1; B chờ.

Nếu B lấy lock xong **vẫn dùng bản A0/R0 đã đọc trước khi chờ**, B lại gửi R0 tới OP, tái tạo race ban đầu.

Do đó sau khi B lấy lock, nó phải:

1. **Đọc lại** authorized client mới nhất từ storage.
2. Kiểm tra access token mới còn dùng được hay không.
3. Nếu A1 vẫn hợp lệ, **không refresh nữa**.
4. Nếu vẫn cần refresh, dùng refresh token của **bản mới nhất**.

### 7.2. Khi không lấy được lock

Không nên lập tức bỏ qua lock và refresh bằng bản cũ.

Các lựa chọn:

- Chờ một khoảng giới hạn và thử đọc lại storage.
- Trả lỗi tạm thời/503 ở API nội bộ nếu không thể chờ mà token không còn hợp lệ.
- Với một số workload, có thể sử dụng **access token cũ còn đủ thời hạn** để hoàn thành request, nếu policy và margin an toàn cho phép.
- Với background job, có thể trì hoãn lượt xử lý theo retry policy có giới hạn.

Không sử dụng refresh token cũ để “đi đường vòng” khi một node khác đang refresh.

### 7.3. Khi lock holder crash

Nếu A crash trước khi gọi Token Endpoint, lock có thể hết lease và B có thể tiếp tục. Nếu A crash **sau khi OP chấp nhận R0 nhưng trước khi lưu R1**, kho vẫn giữ R0 dù OP có thể đã vô hiệu hóa R0.

Đây là **khoảng trống không thể giải quyết tuyệt đối chỉ bằng lock/database transaction** vì Token Endpoint và storage là hai hệ thống độc lập, thường không hỗ trợ một distributed transaction chung.

Hệ thống phải có chính sách phục hồi:

- Nếu provider hỗ trợ grace period/idempotency, dùng đúng hợp đồng đó.
- Nếu refresh token trở nên không dùng được, đánh dấu cần reauthorization.
- Với delegated user token, yêu cầu người dùng đăng nhập/ủy quyền lại khi phù hợp.
- Không tự phát token mới hay giả định kết quả trước khi xác minh.

## 8. Distributed lock: lease, ownership và fencing

### 8.1. Lock có thời hạn

Ví dụ lock storage:

~~~text
key = oauth2-refresh:company:hash-user-123
owner = random-owner-id-for-this-attempt
lease = 15 seconds
~~~

Thời hạn phải đủ cho hoạt động token request thông thường, nhưng không thể dài vô hạn. HTTP timeout, GC pause, network delay và token endpoint outage khiến thời gian thực thi khó đoán.

Nếu lease hết hạn trong khi node A vẫn xử lý, node B có thể lấy lock. Khi A trở lại và ghi, có **hai owner theo thời gian**, và chỉ lock không đủ bảo vệ storage.

### 8.2. Release phải kiểm tra owner

Mẫu nguy hiểm:

~~~text
DEL oauth2-refresh:company:hash-user-123
~~~

Nếu A hết lease, B đã giành lock mới, rồi A chạy <code>DEL</code> không điều kiện, A có thể xóa lock của B.

Release phải là thao tác atomic kiểu:

~~~text
if lock.owner == myOwnerId:
    delete lock
~~~

Trong Redis thường cần cơ chế atomic phù hợp, ví dụ script/lệnh được thiết kế để so sánh owner rồi xóa. Không kiểm tra bằng GET và DEL tách rời nếu giữa hai lệnh lock có thể đổi chủ.

### 8.3. Fencing token

Fencing token là một **số thứ tự tăng dần** được cấp mỗi khi lock có owner mới:

~~~text
A lấy lock: fencing=41
B lấy lock sau: fencing=42
~~~

Khi A trở lại muộn và cố ghi với fencing=41, storage có thể từ chối vì nó đã chấp nhận owner mới fencing=42.

Pseudocode:

~~~text
saveIfFenceIsCurrent(key, newTokens, fencing):
    if fencing < persistedFence:
        reject stale writer
    else:
        update authorized client and persistedFence atomically
~~~

Fencing phải được **thực thi tại nơi nhận write**; chỉ tạo một số fencing mà storage không kiểm tra thì không có tác dụng.

Fencing bảo vệ **ghi đè muộn**, nhưng không thể thu hồi một request refresh đã đến OP và tiêu thụ R0. Vì vậy muốn tránh reuse, vẫn cần điều phối **trước khi gọi Token Endpoint**.

### 8.4. Không giữ database transaction mở vô hạn khi gọi /token

Một giải pháp dễ nghĩ là <code>SELECT ... FOR UPDATE</code> rồi gọi HTTP Token Endpoint trong cùng transaction:

~~~text
BEGIN TRANSACTION
SELECT token FOR UPDATE
POST /token  ← chờ mạng bên ngoài
UPDATE token
COMMIT
~~~

Cách này có thể serialize theo hàng trong database, nhưng transaction giữ lock trong suốt thời gian network call; khi OP chậm, có thể gây contention, tăng số connection chờ và deadlock/timeout.

Nếu sử dụng DB lock, cần tính rất kỹ timeout, transaction isolation, lock lease và khả năng phục hồi. Với nhiều hệ thống, distributed lock bên ngoài transaction cùng CAS update ngắn sẽ dễ vận hành hơn.

## 9. Optimistic concurrency và CAS trên kho token

**CAS không làm cho refresh HTTP trở thành một thao tác atomic với database**, nhưng có thể ngăn stale writer ghi đè phiên bản token mới.

Giả sử bảng có cột <code>version</code>:

~~~text
registration_id | principal_name | access_token | refresh_token | version
company         | user-123       | A0           | R0            | 7
~~~

Khi refresh thành công, A muốn ghi A1/R1 từ version 7:

~~~sql
UPDATE oauth2_authorized_client_state
SET access_token_ciphertext = :new_access_token,
    refresh_token_ciphertext = :new_refresh_token,
    access_token_expires_at = :new_expires_at,
    version = version + 1
WHERE registration_id = :registration_id
  AND principal_name = :principal_name
  AND version = :expected_version;
~~~

Nếu số hàng cập nhật là **1**, A thành công. Nếu là **0**, dữ liệu không còn ở version dự kiến: có writer khác đã thay đổi/xóa bản ghi, hoặc key không tồn tại.

Phải **kiểm tra affected row count**. Không chạy một <code>UPDATE</code> có WHERE version rồi bỏ qua kết quả.

### 9.1. CAS bảo vệ điều gì?

~~~text
A và B đều đọc version=7

A CAS version 7 → 8: thành công
B CAS version 7 → 8: thất bại vì version đã là 8
~~~

Như vậy B không ghi đè A1/R1 bằng dữ liệu cũ.

### 9.2. CAS không bảo vệ điều gì?

CAS xảy ra **sau** khi node đã gọi Token Endpoint. Nếu cả A và B cùng gửi R0 trước khi ghi, OP vẫn có thể phát hiện reuse.

Vì vậy:

> **CAS giải quyết lost update tại storage; per-key coordination giải quyết duplicate refresh ở Token Endpoint.**

Hai cơ chế bổ sung cho nhau khi refresh token rotation có rủi ro.

### 9.3. Không phải schema JDBC mặc định có version

<code>JdbcOAuth2AuthorizedClientService</code> của Spring Security cung cấp lưu trữ authorized client qua JDBC, nhưng không nên giả định schema và API mặc định của phiên bản bạn dùng đã hỗ trợ optimistic version hoặc fencing theo thiết kế ở trên.

Nếu cần CAS, ứng dụng có thể phải:

- Tạo table/column version riêng, tùy biến SQL của service/DAO.
- Tạo wrapper hoặc implementation <code>OAuth2AuthorizedClientService</code> có compare-and-set.
- Thiết kế serialization và encryption cho token values.
- Bảo vệ cả <code>save</code> lẫn <code>remove</code> khỏi stale operations.

Không chỉ thêm một cột <code>version</code> vào database rồi kỳ vọng manager tự động sử dụng nó.

## 10. Thiết kế kho token có version

Một schema khái niệm cho authorized-client state:

~~~sql
CREATE TABLE oauth2_authorized_client_state (
    registration_id           VARCHAR(100) NOT NULL,
    principal_name            VARCHAR(255) NOT NULL,
    access_token_ciphertext   BYTEA NOT NULL,
    refresh_token_ciphertext  BYTEA,
    access_token_issued_at    TIMESTAMP WITH TIME ZONE,
    access_token_expires_at   TIMESTAMP WITH TIME ZONE,
    version                   BIGINT NOT NULL DEFAULT 0,
    fencing_sequence          BIGINT NOT NULL DEFAULT 0,
    updated_at                TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (registration_id, principal_name)
);
~~~

Đây là **DDL minh họa kiểu PostgreSQL**, chưa phải schema copy-paste của Spring Security. Một implementation thực tế còn cần token type, scope, ClientRegistration metadata/reference, refresh-token timestamps, serialization format và các trường khác theo <code>OAuth2AuthorizedClient</code>.

<code>access_token_ciphertext</code> và <code>refresh_token_ciphertext</code> nhấn mạnh rằng token là **credential**, không phải dữ liệu bình thường. Cần chính sách encryption-at-rest, key management, quyền database, TLS, backup protection và retention phù hợp.

### 10.1. Atomic update cả hai token

Không tách:

~~~text
UPDATE access_token = A1
COMMIT
UPDATE refresh_token = R1
COMMIT
~~~

Giữa hai commit, node B có thể thấy access token A1 nhưng refresh token R0 đã bị rotation.

Thay bằng **một transaction/update atomic** cho toàn bộ trạng thái token và version.

### 10.2. Delete cũng cần điều kiện

Khi một request refresh thất bại <code>invalid_grant</code>, thao tác:

~~~sql
DELETE FROM oauth2_authorized_client_state
WHERE registration_id = :registration_id
  AND principal_name = :principal_name;
~~~

có thể xóa bản mới do node khác vừa lưu.

Nếu có version:

~~~sql
DELETE FROM oauth2_authorized_client_state
WHERE registration_id = :registration_id
  AND principal_name = :principal_name
  AND version = :expected_version;
~~~

Chỉ xóa khi bản trong DB **vẫn là bản đã gây lỗi**. Nếu không xóa được hàng nào, nên đọc lại state, kiểm tra việc một node khác đã refresh và quyết định tiếp theo, không retry xóa không điều kiện.

### 10.3. Refresh token rotation và mã hóa token

Nếu encryption dùng nonce/IV ngẫu nhiên, hai ciphertext của cùng refresh token có thể khác nhau. Vì vậy so sánh ciphertext để biết “cùng R0” không đáng tin khi mã hóa không quyết định.

Ưu tiên:

- Version/CAS gắn với mỗi record.
- Hash/fingerprint không đảo ngược (HMAC với khóa riêng) nếu cần so sánh token mà không lộ giá trị.
- Không log raw token để đối chiếu.

Hash/fingerprint là dữ liệu vận hành nhạy cảm và cũng cần giới hạn cách lưu/sử dụng. CAS version thường đơn giản và rõ hơn để chống stale write.

## 11. Tích hợp với Spring Security: chọn manager theo ngữ cảnh

Với Servlet web app:

~~~java
DefaultOAuth2AuthorizedClientManager
~~~

thường phối hợp <code>OAuth2AuthorizedClientRepository</code> và HTTP request.

Với service/background:

~~~java
AuthorizedClientServiceOAuth2AuthorizedClientManager
~~~

phối hợp <code>OAuth2AuthorizedClientService</code> và không phụ thuộc Servlet request.

Trong cả hai trường hợp, điều phối phải bao phủ **đúng chỗ thực hiện refresh**. Nếu ứng dụng có cả web manager và service manager cùng truy cập một authorized client, đặt lock ở mỗi nơi một cách không nhất quán sẽ không đảm bảo single-flight.

### 11.1. Cấu hình Refresh Token Provider

Ví dụ service manager chỉ dùng refresh token đối với những authorized clients đã có:

~~~java
package example.security;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class RefreshManagerConfig {

    @Bean("refreshAuthorizedClientManager")
    OAuth2AuthorizedClientManager refreshManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService service) {

        var provider = OAuth2AuthorizedClientProviderBuilder.builder()
            .refreshToken(configurer ->
                configurer.clockSkew(Duration.ofSeconds(45)))
            .build();

        var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, service);
        manager.setAuthorizedClientProvider(provider);

        return manager;
    }
}
~~~

Điểm cần lưu ý:

- Manager trên **không tự tạo authorization code login** khi chưa có authorized client.
- <code>refreshToken()</code> chỉ hoạt động nếu có refresh token và điều kiện refresh phù hợp.
- Các bean service/repository phải trỏ tới storage phù hợp với cách ứng dụng đã lưu authorized client sau login.
- <code>clockSkew</code> làm token được coi là cần refresh sớm; khi rất nhiều request cùng tới gần mốc đó, concurrency có thể tăng.
- **Cấu hình manager này chưa có distributed lock.** Phải thêm tầng điều phối riêng nếu ứng dụng có nhiều instance và cần chống refresh song song.

Nếu ứng dụng không cần refresh trong job nền, không nên tạo service manager chỉ vì có một OIDC login. Chọn điểm mở rộng theo luồng thật.

### 11.2. Không nên bọc manager một cách hời hợt

Một ý tưởng là:

~~~text
lock.acquire(key)
manager.authorize(request)
lock.release(key)
~~~

Nếu **mọi lượt refresh** đi qua wrapper, lock luôn còn hiệu lực và manager đọc lại storage bên trong lock, cách này có thể hạn chế race.

Tuy nhiên manager thường **lưu kết quả bên trong lời gọi <code>authorize(...)</code>** qua success handler. Nếu lease hết hạn hoặc có code path khác dùng manager không qua lock, wrapper bên ngoài không thể ngăn stale write bằng CAS.

Vì vậy khi cần an toàn trước lease expiry/partial failure:

1. Tất cả code paths phải dùng cùng coordinator.
2. Storage hoặc custom success/failure handler phải có **conditional update/delete**.
3. Có khả năng kiểm tra ownership/fencing tại thời điểm commit.
4. Sau khi chờ lock, phải load lại token mới nhất.

Không nên mô tả một <code>synchronized</code> Java method hoặc một distributed lock sơ sài là “đã giải quyết hoàn toàn refresh token rotation trong cluster”.

## 12. Java: coordinator ở tầng ứng dụng

Ví dụ dưới đây tách việc khóa theo key khỏi Spring Security. <code>DistributedKeyMutex</code> là một **interface kiến trúc**, không phải class Spring Security có sẵn. Ứng dụng production phải cung cấp implementation bằng Redis/DB/distributed lock service phù hợp.

### 12.1. Interface khóa theo key

~~~java
package example.security.refresh;

import java.time.Duration;
import java.util.function.Supplier;

public interface DistributedKeyMutex {

    /**
     * Chỉ một owner cho một key tại một thời điểm.
     * Nếu không lấy được lock trong waitTimeout, ném exception phù hợp.
     * Implementation phải release theo owner và bảo vệ lease.
     */
    <T> T withLock(
        String key,
        Duration waitTimeout,
        Supplier<T> work);
}
~~~

### 12.2. Coordinator gọi manager bên trong lock

~~~java
package example.security.refresh;

import java.time.Duration;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;

@Service
public class CoordinatedRefreshService {

    private final OAuth2AuthorizedClientManager manager;
    private final DistributedKeyMutex mutex;

    public CoordinatedRefreshService(
        @Qualifier("refreshAuthorizedClientManager")
        OAuth2AuthorizedClientManager manager,
        DistributedKeyMutex mutex) {
        this.manager = manager;
        this.mutex = mutex;
    }

    public OAuth2AuthorizedClient authorize(
        String registrationId,
        String trustedPrincipalKey) {

        Objects.requireNonNull(registrationId);
        Objects.requireNonNull(trustedPrincipalKey);

        // Lock key thực tế nên canonicalize và băm định danh nhạy cảm.
        String lockKey =
            "oauth2:refresh:" + registrationId + ":" + trustedPrincipalKey;

        return mutex.withLock(
            lockKey,
            Duration.ofSeconds(5),
            () -> {
                OAuth2AuthorizeRequest request =
                    OAuth2AuthorizeRequest
                        .withClientRegistrationId(registrationId)
                        .principal(trustedPrincipalKey)
                        .build();

                OAuth2AuthorizedClient client = manager.authorize(request);
                if (client == null) {
                    throw new IllegalStateException(
                        "No authorized client or refresh capability");
                }
                return client;
            });
    }
}
~~~

**Giới hạn rất quan trọng của ví dụ:** Đây là ví dụ **phối hợp cấp ứng dụng khi mọi lời gọi manager đều đi qua cùng mutex**, không phải triển khai production hoàn chỉnh chống stale writes. <code>DistributedKeyMutex</code> chưa có implementation; cần xác định lease/renewal, owner-checked release, lock acquisition timeout và fencing/CAS tại storage. Nếu manager tự ghi vào <code>OAuth2AuthorizedClientService</code> không hỗ trợ conditional write, một stale writer sau khi lease hết hạn vẫn có thể ghi đè token.

Nếu cần độ bảo đảm cao, nên kết hợp custom versioned storage và/hoặc custom refresh workflow để **đưa version/fencing tới điểm ghi**; không chỉ đặt lock ở controller mà để các nơi khác bypass.

### 12.3. Đọc lại sau khi lấy lock

Ở ví dụ trên, manager tải authorized client trong phạm vi lời gọi <code>authorize()</code> sau khi coordinator đã lấy lock. Điều này tốt hơn việc caller giữ một <code>OAuth2AuthorizedClient</code> đã đọc trước khi chờ rồi tiếp tục refresh với snapshot đó.

Khi tự viết refresh workflow chi tiết hơn, quy tắc đọc lại cần xuất hiện tường minh:

~~~text
withLock(key):
    latest = authorizedClientStore.load(key)
    if latest.accessToken vẫn dùng được:
        return latest
    if latest.refreshToken không có:
        require reauthorization
    response = tokenClient.refresh(latest.refreshToken)
    compareAndSet(latest.version, response)
~~~

Với <code>OAuth2AuthorizedClientManager</code> mặc định, cần hiểu khi nào provider quyết định token “sắp hết hạn” dựa trên clock skew. Không dùng một điều kiện thời gian ở coordinator khác hẳn provider khiến coordinator trả token mà provider thực ra đã muốn refresh.

## 13. Java: mô hình versioned storage để tránh stale write

Để minh họa CAS mà không phụ thuộc schema mặc định, định nghĩa một API chuyên biệt:

~~~java
package example.security.refresh;

import java.util.Optional;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;

public interface VersionedAuthorizedClientStore {

    Optional<VersionedClient> load(
        String registrationId,
        String principalName);

    /**
     * Chỉ ghi khi version hiện tại bằng expectedVersion.
     * Trả false nếu có concurrent modification.
     */
    boolean compareAndSave(
        String registrationId,
        String principalName,
        long expectedVersion,
        OAuth2AuthorizedClient newClient);

    /**
     * Chỉ xóa version thực sự đã gây lỗi.
     */
    boolean compareAndRemove(
        String registrationId,
        String principalName,
        long expectedVersion);

    record VersionedClient(
        OAuth2AuthorizedClient client,
        long version) {
    }
}
~~~

Đây là **thiết kế interface do ứng dụng tự định nghĩa**, không phải API sẵn có trong <code>OAuth2AuthorizedClientService</code>.

Implementation JDBC có thể sử dụng <code>UPDATE ... WHERE version = ?</code> và kiểm tra <code>rowsUpdated == 1</code>.

Nếu <code>compareAndSave(...)</code> trả <code>false</code>:

1. Không ghi đè token bằng kết quả cũ.
2. Đọc lại bản state mới nhất.
3. Kiểm tra xem token mới đã hợp lệ cho request hay chưa.
4. Nếu chưa, phân loại lỗi và quyết định recovery; không tự động dùng lại refresh token cũ.

### 13.1. CAS khi row chưa tồn tại

Không có hàng nào để cập nhật bằng <code>WHERE version</code> nếu authorized client chưa từng được lưu. Trong thực tế cần xử lý create:

- <code>INSERT</code> với unique key <code>(registrationId, principalName)</code>.
- Nếu duplicate key, đọc lại và áp dụng CAS.
- Không dùng <code>UPSERT</code> unconditional khiến writer cũ thay token mới.

Trạng thái “tạo ban đầu” và “refresh bản đã có” là hai phép chuyển trạng thái khác nhau. Đặc biệt trong Authorization Code callback, người dùng có thể bắt đầu hai lần đăng nhập song song; cần có policy để quyết định authorized client mới nào được phép thay thế bản cũ.

### 13.2. CAS và encryption

Token store nên mã hóa dữ liệu nhạy cảm; version nằm trong metadata không cần tiết lộ token value. Tại thời điểm ghi:

~~~text
read version=7
refresh using R0
encrypt A1/R1
CAS version 7 -> 8, atomic row update
~~~

Không ghi token value trực tiếp vào SQL log; dùng bind parameters và kiểm soát logging driver/ORM. Hệ thống lưu ciphertext vẫn cần bảo vệ khóa mã hóa và backup.

## 14. Spring Security failure handler và nguy cơ xóa nhầm token mới

Một số manager có mặc định xử lý lỗi refresh nhất định, ví dụ loại bỏ authorized client sau một <code>invalid_grant</code>. Hành vi chính xác phụ thuộc manager và phiên bản/configuration.

Trong môi trường nhiều instance, cần đánh giá:

~~~text
A: refresh R0 thành công, lưu A1/R1
B: refresh R0 thất bại invalid_grant
B: removeAuthorizedClient(company, user-123)
~~~

Nếu B xóa không điều kiện theo key, bản A1/R1 có thể bị xóa.

### 14.1. Conditional removal

Một policy an toàn hơn là:

~~~text
if lỗi invalid_grant:
    re-read authorized client
    if current.version != version của request refresh thất bại:
        không xóa trạng thái mới
    else:
        compareAndRemove(expectedVersion)
        đánh dấu cần reauthorization
~~~

Điểm chính: **xóa trạng thái lỗi**, không xóa mọi phiên bản của cùng key.

Nếu Authorization Server đã phát hiện refresh token reuse và vô hiệu hóa token family, bản mới A1/R1 có thể cũng đã bị ảnh hưởng. Không thể kết luận nó còn hợp lệ chỉ vì database có version mới. Ứng dụng cần dựa trên hành vi OP, lỗi subsequent token requests và policy recovery để xác định người dùng phải đăng nhập lại hay không.

### 14.2. Không coi tất cả lỗi là invalid_grant

Lỗi timeout, DNS, TLS, HTTP 429 hoặc HTTP 503 không có cùng ngữ nghĩa với <code>invalid_grant</code>. Nếu xóa authorized client ở mọi lỗi transport, ứng dụng có thể khiến nhiều user phải đăng nhập lại chỉ vì OP bị outage vài phút.

Nên phân loại:

| Loại lỗi | Điều có thể suy luận | Hướng xử lý |
|---|---|---|
| <code>invalid_grant</code> tại Token Endpoint | Refresh token/grant bị từ chối | Kiểm tra race, rotation, revocation, reauthorization |
| <code>invalid_client</code> | Client authentication thất bại | Kiểm tra secret/credential/registration |
| HTTP 429 | Provider giới hạn tốc độ | Backoff, giảm request refresh |
| HTTP 5xx | Lỗi phía OP/gateway | Retry có giới hạn, circuit breaker |
| Timeout sau khi gửi refresh | Chưa biết OP có xử lý request hay không | Không dùng lại R0 một cách mù quáng |
| Storage CAS conflict | Có concurrent update | Đọc lại state; không ghi đè |
| Lock timeout | Node khác có thể đang refresh | Chờ/reload hoặc trả lỗi tạm thời |

### 14.3. Trường hợp kết quả refresh không xác định

Giả sử A gửi R0, OP đã đổi sang R1 nhưng response bị mất do mạng. Kho local vẫn giữ R0. Nếu A hoặc B retry ngay bằng R0, OP có thể coi đó là reuse.

Không có cách chung để Client **tái tạo R1** nếu nó chưa từng nhận được R1.

Biện pháp phụ thuộc provider:

- Nếu OP có idempotency/grace-window semantics, tuân thủ hợp đồng đó.
- Nếu OP không hỗ trợ, đánh dấu authorized client cần reauthorization khi refresh không còn dùng được.
- Với user-facing OIDC Login, yêu cầu người dùng thực hiện Authorization Code Flow mới khi cần.
- Có thể giữ access token cũ còn hạn cho những request không cần refresh nếu policy cho phép, nhưng không được coi refresh đã thành công.

## 15. On-demand refresh và proactive refresh

Có hai cách kích hoạt refresh.

### 15.1. On-demand

Khi một HTTP request chuẩn bị gọi Resource Server, manager kiểm tra access token và refresh nếu sắp hết hạn.

Ưu điểm:

- Không xin token mới khi user không hoạt động.
- Dễ gắn refresh với nhu cầu thật.

Rủi ro:

- Nhiều request cùng đến mốc token sắp hết hạn có thể tạo burst.
- Người dùng phải chờ token endpoint response.
- Nếu OP outage, nhiều request người dùng có thể thất bại đồng thời.

### 15.2. Proactive refresh

Một background task chủ động quét authorized clients sắp hết hạn và refresh trước khi có request của người dùng.

Ưu điểm:

- Giảm latency của request đầu tiên sau expiry.
- Có thể kiểm soát rate và phân phối công việc theo lịch.

Rủi ro:

- Refresh các token không còn cần dùng, tăng tải OP.
- Nhiều replica chạy cùng scheduler nếu không có distributed coordination.
- Dễ đua với on-demand refresh nếu cả hai cùng xử lý một key.
- Vòng đời refresh token kéo dài tùy policy, tăng nhu cầu kiểm soát secret và revocation.

**Quan trọng:** Nếu ứng dụng dùng cả proactive và on-demand, cả hai phải dùng **cùng coordinator/lock key/storage versioning**. Không thể chỉ khóa scheduler mà cho phép web request refresh trực tiếp ngoài lock.

### 15.3. Jitter giảm burst nhưng không thay lock

Khi hàng nghìn authorized clients có token cùng hết hạn, việc refresh đồng loạt có thể gây rate limit. Có thể làm đều tải bằng **jitter** và batch scheduling:

~~~text
target refresh time = expiresAt - safetyMargin - randomJitter
~~~

Tuy nhiên jitter chỉ giảm xác suất nhiều workload cùng refresh tại một thời điểm; nó **không đảm bảo single-flight cho cùng authorized client**. Vẫn cần điều phối theo key trong hệ thống có yêu cầu chống token reuse.

## 16. Token store, session và multi-instance

Một ứng dụng Servlet OIDC Login có thể có:

~~~text
HTTP Session / SecurityContext:
    người dùng đang authenticated

OAuth2AuthorizedClientService:
    token đã được cấp gắn với principal/registration

AuthorizationRequestRepository:
    state/PKCE đang chờ callback (ngắn hạn)
~~~

Ba loại dữ liệu khác nhau và có vòng đời khác nhau.

Nếu dùng Spring Session/Redis để chia sẻ HTTP session, **không mặc định** điều đó có nghĩa <code>OAuth2AuthorizedClientService</code> cũng dùng Redis. Nếu service vẫn là <code>InMemoryOAuth2AuthorizedClientService</code>, mỗi instance có thể có token state riêng.

Ngược lại, dùng JDBC authorized-client service chia sẻ token không tự làm HTTP session được chia sẻ hoặc callback OIDC chạy đúng trên mọi node.

### 16.1. Khi nào cần kho token chia sẻ?

Kho chia sẻ thường cần khi:

- Nhiều instance cùng xử lý request của một principal và phải thấy token cập nhật mới.
- Muốn token tồn tại qua restart.
- Có worker chuyên trách refresh cho các web nodes.
- Muốn quản lý revocation/cleanup tập trung.

Nếu mỗi node độc lập xử lý một tập principal không giao nhau và token không cần roaming, kiến trúc khác có thể hợp lý. Quan trọng là **nói rõ ownership**; không để các instance vô tình dùng chung một refresh token mà không có cơ chế điều phối.

### 16.2. Multi-tenant isolation

Trong hệ thống đa tenant:

~~~text
tenant-a / registration=company / principal=user-123
tenant-b / registration=company / principal=user-123
~~~

Nếu hai identity này không cùng người dùng, storage key và lock key phải phân biệt. Cặp <code>(iss, sub)</code> của OIDC identity hoặc internal principal key duy nhất có thể là nền tảng, tùy thiết kế.

Không dùng email do browser khai báo hoặc các tham số <code>tenant</code>/<code>principal</code> chưa xác thực để chọn refresh token.

## 17. Bảo mật khi phối hợp refresh

Việc đưa token vào một kho dùng chung làm tăng yêu cầu bảo vệ dữ liệu.

### 17.1. Bảo vệ token và database

- Chỉ lưu access/refresh token khi thực sự cần.
- Mã hóa dữ liệu nhạy cảm at rest và quản lý khóa an toàn.
- Dùng TLS tới database, Redis, Authorization Server và API.
- Giới hạn service account có quyền đọc/ghi authorized-client table.
- Tránh quyền SQL tổng quát trên toàn bộ token store cho những thành phần chỉ cần một workload.
- Bảo vệ backup, snapshot và log database khỏi lộ token.
- Có chính sách xóa token khi logout, unlink provider, thu hồi quyền hoặc kết thúc vòng đời dữ liệu.

### 17.2. Không log credential trong race trace

Tránh log:

- <code>accessToken.getTokenValue()</code>.
- <code>refreshToken.getTokenValue()</code>.
- Client secret, HTTP <code>Authorization</code> header.
- Authorization code, PKCE verifier, nonce/state thật.
- Raw token response.
- SQL bind parameters chứa ciphertext/token.

Có thể log thông tin an toàn hơn:

~~~text
registrationId=company
principalKeyHash=...
refreshLockAcquired=true
storageVersionBefore=7
storageVersionAfter=8
refreshOutcome=success
refreshDurationMs=430
~~~

Ngay cả principal hash hoặc registration ID cũng cần tuân thủ chính sách telemetry của tổ chức. Không gắn raw exception message từ Token Endpoint vào nhãn metric.

### 17.3. Những metric hữu ích

| Metric | Ý nghĩa |
|---|---|
| <code>oauth2_refresh_attempt_total</code> | Số lượt refresh thực sự gửi tới OP |
| <code>oauth2_refresh_success_total</code> | Số lượt refresh thành công |
| <code>oauth2_refresh_failure_total{kind}</code> | Phân loại lỗi chuẩn hóa |
| <code>oauth2_refresh_lock_wait_ms</code> | Thời gian chờ lock |
| <code>oauth2_refresh_lock_timeout_total</code> | Số lần không lấy được lock |
| <code>oauth2_refresh_cas_conflict_total</code> | Số xung đột cập nhật storage |
| <code>oauth2_refresh_stale_writer_rejected_total</code> | Số ghi bị từ chối do version/fencing |
| <code>oauth2_refresh_reauthorization_required_total</code> | Số lượt cần authorization lại |

Không đưa token value hoặc principalName raw làm metric label; sẽ gây lộ dữ liệu và cardinality không kiểm soát.

## 18. Các lựa chọn khắc phục theo mức độ hệ thống

### 18.1. Ứng dụng nhỏ, một node

Có thể dùng <code>OAuth2AuthorizedClientManager</code> với storage phù hợp. Tuy vậy, một node vẫn có nhiều thread đồng thời, nên nếu provider dùng rotation nghiêm ngặt, vẫn cần cân nhắc single-flight theo key **trong JVM** hoặc một coordinator thống nhất.

Nếu có kế hoạch scale-out, nên thiết kế abstraction coordinator sớm để thay local mutex bằng distributed lock mà không phải sửa toàn bộ controller.

### 18.2. Nhiều node, traffic vừa

Một chiến lược thường hợp lý:

1. Dùng authorized-client storage chia sẻ.
2. Tạo lock theo <code>(registrationId, principalKey)</code>.
3. Sau khi lấy lock, đọc lại record.
4. Chỉ refresh nếu token vẫn cần refresh.
5. Atomic update cả access/refresh token.
6. Bảo vệ save/remove bằng CAS/version khi lock có thể hết lease.
7. Giới hạn timeout và đo metrics.

### 18.3. Hệ thống lớn với nhiều provider/tenant

Có thể tiến tới:

- Single-writer refresh service hoặc hàng đợi partition theo authorized-client key.
- Dedicated token vault/service với versioning và audit.
- Rate limiter/token request budget theo provider.
- Distributed lock có fencing token và lease renewal.
- Batch proactive refresh, ưu tiên những authorized clients đang hoạt động.
- Chính sách revoke/reauthorize tự động theo loại lỗi và capability provider.

Những lựa chọn này tăng chi phí vận hành, không nên triển khai toàn bộ ngay nếu hệ thống không có nhu cầu. Mục tiêu là **đúng mức nhất quán với đặc tính rotation/reuse của Authorization Server**.

## 19. Các lỗi thiết kế thường gặp

| Thiết kế sai | Vì sao sai | Cách sửa |
|---|---|---|
| Dùng <code>synchronized</code> và cho rằng đã khóa cả cluster | Chỉ khóa trong một JVM | Distributed lock/coordinator hoặc single writer |
| Dùng JDBC service rồi mặc định tránh được race | DB chia sẻ không ngăn hai node cùng gọi OP | Lock theo key + reread |
| Dùng CAS nhưng không khóa trước HTTP refresh | Hai node vẫn có thể dùng R0 tại OP | Điều phối trước Token Endpoint |
| Lấy lock rồi dùng token snapshot trước lock | Snapshot có thể đã cũ | Đọc lại token sau khi lấy lock |
| Release lock không kiểm tra owner | Node cũ có thể xóa lock của node mới | Owner-checked atomic release |
| Không giới hạn lease | Crash có thể treo lock vô hạn | Lease/timeout/renewal + recovery |
| Chỉ tin lock, bỏ CAS/fencing | Lease có thể hết trước write | Conditional storage update |
| Lưu access và refresh token ở hai commit | Có thể nhìn thấy trạng thái không nhất quán | Atomic update cả token pair |
| Xóa authorized client không điều kiện sau <code>invalid_grant</code> | Có thể xóa token mới do node khác lưu | Conditional delete theo version |
| Retry R0 ngay sau timeout | OP có thể đã tiêu thụ R0 | Phân loại kết quả chưa xác định |
| Mọi lỗi đều yêu cầu logout | Outage 5xx/timeout không nhất thiết là token bị thu hồi | Phân loại lỗi và recovery |
| Lock global duy nhất | User A chặn user B | Lock per authorized-client key |
| Principal key thay đổi tùy request | Mất khả năng dùng chung state đúng cách | Stable trusted principal key |
| Log refresh token để so sánh | Lộ credential | Version/fingerprint an toàn |
| Chỉ khóa proactive job, để web request refresh tự do | Hai code path vẫn tranh chấp | Coordinator chung cho mọi writer |

## 20. Chẩn đoán sự cố trong production

Khi thấy <code>invalid_grant</code> xuất hiện đột ngột sau khi scale từ 1 lên nhiều replica:

1. **Xác định grant:** lỗi xuất hiện ở refresh token grant hay authorization code/token endpoint khác?
2. **Xác định provider policy:** OP có refresh token rotation, reuse detection, grace period hoặc token family revocation không?
3. **Kiểm tra số instance/thời điểm:** có hai request cùng principal/registration trong thời gian token gần expiry không?
4. **Đối chiếu storage version:** hai node có đọc cùng version và cùng refresh token state không?
5. **Kiểm tra lock:** có shared lock thật, stable key, owner-checked release và lease hợp lý không?
6. **Kiểm tra reread:** node B sau khi lấy lock có tải trạng thái mới hay dùng snapshot cũ?
7. **Kiểm tra writes/deletes:** success/failure handler có cập nhật/xóa không điều kiện sau khi version đổi không?
8. **Kiểm tra timeout:** request refresh trước có thể đã được OP xử lý dù Client không nhận response không?
9. **Kiểm tra downstream:** API 401 do token expired, audience sai hay bị provider revoke?
10. **Kiểm tra recovery:** ứng dụng có yêu cầu reauthorization đúng lúc, hay lặp vô hạn cùng refresh token lỗi?

Sơ đồ khoanh vùng:

~~~text
Nhiều instance cùng thấy access token sắp hết hạn?
    |
    v
Mọi code path có dùng cùng coordinator?
    |--- Không ---> bổ sung single-flight chung
    |
    v
Có load lại sau khi lấy lock?
    |--- Không ---> tránh dùng refresh token stale
    |
    v
Storage save/remove có CAS/fencing?
    |--- Không ---> ngăn stale update/delete
    |
    v
Provider rotation/reuse policy ra sao?
    |
    +--- Refresh thành công ---> atomic save A1/R1
    |
    +--- invalid_grant --------> phân loại race/revocation
    |
    +--- timeout -------------> trạng thái kết quả chưa rõ
    |
    v
Retry/relogin và metrics theo policy
~~~

Không cần thu thập raw refresh token để điều tra. Có thể dùng correlation ID nội bộ, version, timestamps đã làm sạch, provider registration ID và loại lỗi.

## 21. Bài tập và tình huống thực hành

### Bài 1 — Hai node dùng cùng refresh token

~~~text
A đọc: version=5, refresh=R0
B đọc: version=5, refresh=R0
A gọi OP và nhận A1/R1
B gọi OP với R0 và nhận invalid_grant
~~~

**Câu hỏi:** Chỉ chuyển storage từ memory sang database có giải quyết tận gốc không?

**Đáp án:** Không. Database cho phép hai node nhìn thấy cùng trạng thái nhưng không tự ngăn cùng gửi R0. Cần điều phối trước khi gọi OP, đọc lại sau khi lấy lock và bảo vệ ghi bằng CAS/fencing.

### Bài 2 — Load lại sau lock

B chờ lock 2 giây. Trong thời gian đó A đã lưu version 6 cùng A1/R1. B lấy lock xong nhưng vẫn giữ object version 5 từ trước.

**Câu hỏi:** B có nên refresh R0 từ object version 5 không?

**Đáp án:** Không. B phải tải lại latest authorized client từ shared storage. Nếu A1 còn dùng được thì B dùng A1, không cần refresh.

### Bài 3 — CAS conflict

A và B đều muốn cập nhật version 7. A update thành version 8; B chạy:

~~~sql
UPDATE oauth2_authorized_client_state
SET version = 8
WHERE registration_id = 'company'
  AND principal_name = 'user-123'
  AND version = 7;
~~~

và số hàng cập nhật là 0.

**Câu hỏi:** B có được bỏ điều kiện version để ép ghi không?

**Đáp án:** Không. Có concurrent modification. B phải đọc lại state; nếu có authorized client mới thì dùng/đánh giá trạng thái đó. Bỏ điều kiện version tái tạo lost update.

### Bài 4 — Xóa nhầm token mới

A lưu version 8 với R1. B nhận <code>invalid_grant</code> của R0 rồi gọi <code>removeAuthorizedClient(registration, principal)</code> không điều kiện.

**Câu hỏi:** Có rủi ro gì và nên làm gì?

**Đáp án:** B có thể xóa bản R1 mới. Xóa có điều kiện theo version đã gây lỗi; nếu version hiện tại khác, không xóa. Ngoài ra vẫn phải cân nhắc OP có revoke cả token family vì phát hiện R0 bị dùng lại hay không.

### Bài 5 — Lock bị hết hạn

A lấy lock 10 giây, gọi Token Endpoint mất 12 giây. B lấy lock sau giây thứ 10 và bắt đầu refresh.

**Câu hỏi:** Tại sao distributed lock đơn giản chưa đủ?

**Đáp án:** Lease hết hạn khiến hai node có thể xử lý đồng thời. Cần timeout/renewal phù hợp, kiểm soát owner, fencing tại storage và thiết kế recovery. Fencing không ngăn tuyệt đối request đã tới OP, nên phải kiểm soát việc cấp lock và điều phối trước HTTP call.

### Bài 6 — Dùng CAS nhưng không có lock

Hai node cùng đọc version 12 và đều gọi OP với R0. Chỉ một node được cập nhật database nhờ CAS.

**Câu hỏi:** Có an toàn với OP bật reuse detection không?

**Đáp án:** Chưa. CAS ngăn lost update ở DB nhưng OP vẫn có thể thấy R0 bị dùng hai lần. Single-flight trước refresh mới giảm rủi ro reuse.

### Bài 7 — Timeout sau refresh

Client gửi R0, bị read timeout và không nhận token response.

**Câu hỏi:** Có thể chắc chắn R0 chưa được tiêu thụ không?

**Đáp án:** Không. OP có thể đã xử lý và cấp R1 nhưng response bị mất. Không retry R0 liên tục; dùng chính sách provider, bounded retry khi an toàn, và reauthorization khi không thể khôi phục.

### Bài 8 — Multi-tenant

Issuer A và B có subject cùng là <code>123</code>. Hệ thống dùng một kho token và lock key <code>oauth2-refresh:123</code>.

**Câu hỏi:** Vấn đề là gì?

**Đáp án:** Hai identity có thể va chạm lock/storage. Khóa phải phân vùng bằng registration và principal namespace tin cậy, có issuer/tenant nếu cần. Không coi subject trùng là cùng một người.

### Bài 9 — Proactive và on-demand

Một scheduler refresh token trước expiry, trong khi web controller dùng manager riêng và có thể refresh trực tiếp.

**Câu hỏi:** Chỉ đặt distributed lock trong scheduler có đủ không?

**Đáp án:** Không. Controller có thể dùng lại R0 đồng thời. Mọi đường thực hiện refresh cho cùng authorized client phải dùng chung cơ chế điều phối và điều kiện ghi.

### Bài 10 — Thiết kế giải pháp cho hệ thống ba replica

Thiết kế hệ thống gồm:

1. Shared authorized-client store với <code>version</code> và cập nhật atomic cả token pair.
2. Stable key từ <code>(registrationId, trustedPrincipalKey)</code>.
3. Distributed lock có lease, kiểm tra owner khi release và khả năng chống stale writer.
4. Đọc lại authorized client sau khi lấy lock.
5. Chỉ refresh khi token vẫn cần refresh.
6. CAS save/remove, xử lý version conflict.
7. Phân loại <code>invalid_grant</code>, timeout, 429, 5xx và khả năng phải reauthorize.
8. Metrics lock wait, refresh success/failure, CAS conflict và token request rate.
9. Chính sách cleanup khi logout hoặc thu hồi ủy quyền.
10. Bảo vệ token values, secret, SQL logging và telemetry.

Hãy giải thích điều gì xảy ra nếu node crash **trước** Token Endpoint, **sau** OP refresh nhưng **trước** DB save, và **sau** DB save nhưng **trước** release lock.

## 22. Ghi nhớ

- Khi nhiều instance cùng dùng một authorized client, **refresh token rotation có thể khiến hai node cùng dùng R0 và tạo <code>invalid_grant</code> hoặc reuse detection**.
- <code>OAuth2AuthorizedClientManager</code> và JDBC service **không mặc định cung cấp distributed single-flight refresh**. Storage chia sẻ chỉ là một phần của kiến trúc.
- **Distributed lock theo đúng authorized-client key** giúp hạn chế duplicate refresh. **Đọc lại sau khi lấy lock** là bước bắt buộc để tránh dùng snapshot cũ.
- **CAS/version** bảo vệ storage khỏi lost update; **fencing** có thể từ chối stale writer sau khi lease đổi chủ. CAS một mình không ngăn R0 được gửi hai lần tới OP.
- Access token và refresh token phải được **cập nhật nguyên cặp một cách atomic**, đặc biệt khi OP phát refresh token mới.
- Failure handler sau <code>invalid_grant</code> không nên **xóa không điều kiện** authorized client của cùng key, vì instance khác có thể vừa lưu version mới.
- Timeout sau khi gửi refresh token tạo ra **kết quả chưa xác định**: OP có thể đã tiêu thụ token dù Client chưa nhận response. Không retry mù cùng R0.
- Mọi code path (web, API, scheduler, proactive refresh) dùng chung authorized client phải đi qua **cùng chính sách điều phối**.
- Bảo vệ token storage, principal namespace, TLS, secret và logs; theo dõi lock wait, refresh failure và CAS conflict để phát hiện race trong production.

### Tài liệu tham khảo

- **Spring Security Reference — OAuth2 Client:** <code>OAuth2AuthorizedClientManager</code>, authorized client persistence và refresh token provider.
- **Spring Security Java API:** <code>OAuth2AuthorizedClient</code>, <code>OAuth2AuthorizedClientService</code>, <code>OAuth2AuthorizedClientRepository</code>, <code>OAuth2AuthorizedClientProviderBuilder</code>.
- **Spring Security Java API:** <code>DefaultOAuth2AuthorizedClientManager</code>, <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code>, authorization success/failure handlers.
- **RFC 6749 — The OAuth 2.0 Authorization Framework**, mục 6: Refreshing an Access Token.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** refresh token protection, rotation và replay detection.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token tại Authorization Server.
- **OpenID Connect Core 1.0:** Authorization Code Flow, ID Token, quan hệ với OAuth2 token response.
- **Tài liệu của Authorization Server đang tích hợp:** refresh token rotation, reuse policy, grace period và token revocation semantics; các hành vi này có thể khác nhau giữa provider.
