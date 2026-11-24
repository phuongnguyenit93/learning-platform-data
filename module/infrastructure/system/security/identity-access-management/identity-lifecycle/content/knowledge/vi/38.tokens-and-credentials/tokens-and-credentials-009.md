# Token rotation: đổi refresh token an toàn, phát hiện sử dụng lại và kiểm soát vòng đời IAM

**Token rotation (luân chuyển token)** là cơ chế **thay token hiện hành bằng token mới theo chính sách**, đồng thời giới hạn hoặc chấm dứt khả năng dùng lại token cũ. Trong OAuth 2.0, chủ đề thường tập trung vào **refresh token rotation**: mỗi lần client dùng một refresh token hợp lệ để lấy token mới, Authorization Server cấp **refresh token kế tiếp** và làm refresh token vừa dùng **không còn hợp lệ để làm mới thêm lần nữa**. Các token có quan hệ với nhau tạo thành một **token family/lineage**, giúp máy chủ phát hiện tình huống token cũ xuất hiện lại.

Ví dụ: Ứng dụng mobile có refresh token `RT-1`. Khi nó dùng `RT-1` hợp lệ để xin access token mới, server phát `AT-2` và `RT-2`, đồng thời đánh dấu `RT-1` đã sử dụng. Nếu sau đó có yêu cầu khác trình `RT-1`, server ghi nhận **reuse/replay signal** và thực hiện chính sách phòng vệ, chẳng hạn vô hiệu hóa family có nguy cơ và buộc xác thực lại.

**Điểm quan trọng:** **Rotation không phải chỉ tăng `exp` của token**, không đồng nghĩa “mỗi API request phải cấp access token mới”, và cũng **không tự thu hồi access token đã phát** tại Resource Server. Để an toàn, phải xét **token family, lưu trữ, atomicity, khả năng mất kết nối, nhiều tab/thiết bị, replay detection, event-driven revocation** và tác động lên **IAM theo Joiner–Mover–Leaver**.

Bài này thuộc chương **Token và credential** trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Mô-đun học quản lý vòng đời danh tính từ Joiner, Mover, Leaver, kết nối **IdP/SSO, OAuth/OIDC, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư**. Nội dung ưu tiên **token rotation như một kiểm soát thực thi** trong hệ thống IAM, không coi việc đổi token là bằng chứng duy nhất rằng quyền đã được thu hồi.

**Nguyên tắc cốt lõi:** **Một refresh token không nên được sử dụng lại ngoài quy tắc của Authorization Server**. Nhưng **reuse được quan sát không đủ để kết luận chắc chắn đã có tấn công**, vì lỗi mạng và yêu cầu đồng thời của client hợp lệ cũng có thể tạo sự kiện giống nhau. Phản ứng cần theo thiết kế bảo mật, có evidence và khả năng phục hồi trải nghiệm người dùng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **access token, refresh token, ID token, authorization grant, session, client credential, signing key** và vai trò của từng thành phần.
2. Mô tả **refresh token rotation** với các bước phát, sử dụng một lần, vô hiệu token cũ, tạo token kế tiếp và xử lý token family.
3. Giải thích **reuse detection, replay, token theft, token family invalidation, suspicious activity** và giới hạn suy luận từ log.
4. Hiểu vì sao **client đồng thời ở nhiều tab, retry, lỗi mạng, timeout và refresh storms** có thể tạo reuse ngoài ý muốn.
5. Thiết kế **server-side atomic update** và **client-side singleflight** để kiểm soát vòng đời refresh token.
6. Lựa chọn cách bảo vệ token cho **browser/BFF, mobile/native client, ứng dụng server và multi-device sessions**.
7. Phân biệt refresh token rotation với **sender-constrained tokens**, **client secret/API key rotation** và **JWT signing-key rollover/JWKS**.
8. Giải thích giới hạn của **access token `exp`**, token revocation, IdP logout, SSO session, SCIM và việc thay đổi quyền RBAC/ABAC.
9. Liên kết rotation với **Joiner–Mover–Leaver, quyền đặc quyền, service account/workload và sự kiện rủi ro**.
10. Đề xuất log/metrics/runbook và kiểm thử để đảm bảo **token bị dùng lại không được chấp nhận sai**, nhưng không vô tình gây lỗi diện rộng.

## 2. Bản đồ các loại token và credential

Trong IAM, chữ “token” có thể chỉ nhiều hiện vật khác nhau:

| Thành phần | Chức năng chính | Ai trình nó cho ai? | Có phải đối tượng rotation theo cùng một nghĩa? |
|---|---|---|---|
| **Access token** | Cho Resource Server biết request có thể được xét quyền | Client → API | Thường **phát token mới khi cần** và để token cũ hết hạn/thu hồi; không tự có token family kiểu refresh token |
| **Refresh token** | Giúp client xin access token mới theo grant được phép | Client → Authorization Server | **Có thể áp rotation mỗi lần sử dụng** |
| **ID token (OIDC)** | Chuyển thông tin về authentication event cho Relying Party | IdP → OIDC client | Có `exp` riêng; không dùng làm refresh token hoặc API bearer access token |
| **Authorization code** | Giá trị ngắn hạn, dùng trong authorization flow | Client → Token endpoint | Có tính chất **single-use**, nhưng không gọi là refresh token rotation |
| **Session cookie/ID** | Nhận diện phiên ứng dụng/IdP | Browser → ứng dụng/IdP | Có thể tái tạo/rotate session ID khi authentication/privilege đổi; khác token family |
| **Client secret/private key** | Chứng minh client identity | Client → Token endpoint hoặc hệ khác | **Credential rotation**; cần quy trình chuyển đổi và thu hồi secret/key |
| **JWT signing key** | Ký JWT để bên nhận xác minh issuer | Authorization Server/IdP ký token | **Signing-key rollover**; có giai đoạn tin nhiều khóa |
| **API key/PAT** | Credential hoặc token tích hợp theo hệ thống | Tool/client → API | Phát key mới, thay client và revoke key cũ; semantics tùy sản phẩm |
| **PAM/JIT activation token** | Cho phép kích hoạt hoặc dùng đặc quyền theo hạn | Subject/PAM → target | Cần TTL/revocation/session controls; không mặc định cùng OAuth refresh rotation |

**Không được dùng ID token làm access token.** Đối với OAuth/OIDC, Resource Server phải xác minh **đúng token type/audience/issuer/expiry/scope** theo thiết kế, không chỉ kiểm JWT signature.

### 2.1. Ba vòng đời phải tách rời

- **Authentication/session lifecycle:** Người hoặc workload có đang được xác thực và session có hợp lệ?
- **Authorization/grant lifecycle:** Subject hiện có quyền gì trên resource, tenant, action?
- **Credential/token lifecycle:** Token/secret còn hiệu lực, đã rotate, bị revoke hoặc quá hạn chưa?

Rotation xử lý **một phần của credential/token lifecycle**, nhưng **không thay thế** việc cập nhật grant khi subject Mover/Leaver hoặc tài nguyên thay owner.

## 3. Phân biệt rotation, renewal, expiration, revocation và rollover

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Rotation** | Thay token/credential đang dùng bằng giá trị mới, hạn chế dùng lại giá trị cũ | `RT-1 → RT-2` |
| **Renewal/refresh** | Xin access token mới bằng cơ chế được phép | Dùng `RT-2` nhận `AT-3` |
| **Expiration** | Một token hết thời hạn được tin tại bên kiểm | `AT-3.exp` đã qua |
| **Revocation** | Chủ động làm token/grant mất hiệu lực trước expiry theo cơ chế hỗ trợ | Leaver khiến refresh-token family bị revoke |
| **Replay/reuse detection** | Phát hiện trình lại token vốn đã được sử dụng/không còn hợp lệ | `RT-1` xuất hiện sau khi `RT-2` đã phát |
| **Credential rotation** | Thay secret, API key, private key hoặc certificate | Đổi OAuth client secret |
| **Signing-key rollover** | Đổi khóa server dùng ký token và cập nhật nguồn public keys | `kid=old` sang `kid=new` |
| **Session renewal** | Làm mới ngữ cảnh phiên sau auth/reauth hợp lệ | Browser nhận session ID mới |

Một tổ chức có thể thực hiện **nhiều loại rotation cùng lúc**, nhưng tác động lên client, Authorization Server, API và người dùng **khác nhau**.

### 3.1. Hai câu hỏi không được nhầm

- **“Refresh token cũ còn được dùng để lấy token mới không?”** → Authorization Server/refresh rotation.
- **“Access token đã phát còn cho gọi API không?”** → Resource Server/introspection/revocation/authorization.

Hai câu hỏi có thể cho **hai câu trả lời khác nhau tại cùng thời điểm**.

## 4. Vì sao refresh token là mục tiêu bảo vệ quan trọng?

Một access token có thể được thiết kế sống tương đối ngắn, còn refresh token cho phép client **tiếp tục lấy access token mới** trong một khoảng dài hơn. Nếu refresh token bị lấy cắp và được dùng như bearer token, attacker có thể cố kéo dài quyền truy cập.

Rotation tạo ra **tín hiệu bất thường khi cùng một refresh token được trình hơn một lần**, nếu server có cơ chế lưu và nhận biết lineage:

~~~text
Tình huống không rotation:
  RT-X -> AT-1
  RT-X -> AT-2
  RT-X -> AT-3
  Ai có RT-X có thể tiếp tục refresh trong thời hạn cho phép.

Tình huống rotation:
  RT-1 -> AT-1 + RT-2  (RT-1 không còn hợp lệ)
  RT-2 -> AT-2 + RT-3  (RT-2 không còn hợp lệ)
  RT-1 lại xuất hiện -> REUSE SIGNAL / REJECT / DEFENSE POLICY
~~~

**Không khẳng định rotation ngăn được mọi token theft.** Nếu attacker đánh cắp **refresh token hiện hành và sử dụng trước client hợp lệ**, attacker có thể nhận token kế tiếp. Khi client thật sau đó dùng token cũ, server thấy reuse và có thể chặn family, nhưng không tự biết chắc ai là attacker. Do đó rotation là **phát hiện/làm giảm cửa sổ lạm dụng**, cần kết hợp lưu trữ an toàn, sender constraint, audit và revoke.

## 5. Mô hình refresh token rotation cơ bản

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client hợp lệ
    participant AS as Authorization Server
    participant STORE as Token family store
    participant API as Resource Server
    participant SEC as Security monitoring

    C->>AS: Refresh request dùng RT-1
    AS->>STORE: Kiểm RT-1 ACTIVE + grant, client, family
    STORE-->>AS: Hợp lệ, generation=1
    AS->>STORE: Atomically: RT-1 USED; tạo RT-2 ACTIVE
    STORE-->>AS: Commit thành công
    AS-->>C: AT-2 + RT-2
    C->>API: Gọi API với AT-2
    API->>API: Kiểm token + scope + resource policy
    API-->>C: Response theo authorization
    C->>AS: Lần refresh tiếp dùng RT-2
    AS->>STORE: Atomically: RT-2 USED; tạo RT-3 ACTIVE
    AS-->>C: AT-3 + RT-3
    Note over AS,STORE: Nếu RT-1 hoặc RT-2 bị trình lại<br/>theo chính sách, ghi reuse event
    AS-->>SEC: Token reuse signal / revoke event
~~~

**Điều kiện quan trọng:**

1. Client được xác thực/nhận diện đúng **client type** và phương thức đang dùng.
2. Refresh token gắn với **grant/client/subject/session/device context** theo thiết kế.
3. Server kiểm **family state, expiry, revocation, subject eligibility, client binding**.
4. Chỉ **một request có thể tiêu thụ token hiện hành một lần**.
5. Phát token kế tiếp với entropy và metadata đầy đủ.
6. **Token cũ không được phép tiếp tục refresh**, trừ cơ chế ngoại lệ/grace được cân nhắc rất chặt.
7. Dữ liệu thay đổi phải **atomic** để không tạo hai nhánh active ngoài ý muốn.
8. Security/audit ghi sự kiện đủ truy vết nhưng **không lưu token nguyên văn**.

### 5.1. Rotation không nhất thiết được bật ở mọi client

Không phải Authorization Server nào cũng cấp refresh token cho mọi OAuth flow, và một số ứng dụng dùng **sender-constrained refresh tokens** hoặc chiến lược khác tùy rủi ro/khả năng. Phải **xác nhận contract của IdP/Authorization Server**, không tự giả định response luôn có `refresh_token` mới.

## 6. Token family: một chuỗi kế nhiệm, không phải tập token độc lập

Một token family là tập refresh token có quan hệ phát sinh từ một grant/session:

~~~text
Family F-77 (client: mobile-app, subject: P-2048, device: D-5)
  RT-1 [USED]
    └─ RT-2 [USED]
         └─ RT-3 [ACTIVE]
              └─ RT-4 [NOT YET ISSUED]

Một RT mới được phát từ refresh hợp lệ.
Tại một thời điểm thông thường chỉ một token hiện hành
được coi ACTIVE trong một chuỗi rotation đơn tuyến.
~~~

Các trường dữ liệu thường cần trong hệ thống:

| Field logic | Ý nghĩa |
|---|---|
| `familyId` | Nhóm token kế nhiệm cùng grant |
| `tokenId` | ID nội bộ; không phải raw refresh token |
| `parentTokenId` | Quan hệ token trước → sau |
| `generation` | Phiên bản/đời trong family |
| `clientId` | Client được phép refresh |
| `subjectId` | Người hoặc chủ thể mà grant gắn với |
| `sessionId`/`deviceId` | Tách session/device theo kiến trúc |
| `issuedAt`/`expiresAt` | Thời gian phát và hết hạn |
| `usedAt` | Lần tiêu thụ hợp lệ |
| `status` | ACTIVE, USED, REVOKED, EXPIRED... |
| `familyRevokedAt` | Thời điểm vô hiệu cả family |
| `reasonCode` | REUSE_DETECTED, LEAVER, USER_LOGOUT... |

**Một family không nhất thiết tương đương mọi phiên của một người.** Người dùng có thể đăng nhập trên hai thiết bị, mỗi thiết bị có grant/family riêng. Thu hồi một family có thể chỉ đăng xuất thiết bị đó; **thu hồi toàn bộ** cần chính sách và khả năng định danh theo subject/client.

### 6.1. Grant provenance quan trọng

Family nên liên kết với nguồn cho phép: client registration, consent/grant, authentication event và policy. Nếu user Mover làm mất quyền dự án A, grant liên quan đến A có thể phải bị thu hồi hoặc giới hạn; không được coi token family còn ACTIVE là bằng chứng quyền A vẫn hợp lệ.

## 7. Replay/reuse detection hoạt động như thế nào?

Ví dụ chuỗi hợp lệ:

~~~text
09:00:00  RT-A ACTIVE
09:05:00  Client refresh RT-A -> RT-B ACTIVE; RT-A USED
09:20:00  Client refresh RT-B -> RT-C ACTIVE; RT-B USED
~~~

Sau đó có yêu cầu dùng `RT-A`:

- Server xác nhận token từng thuộc family nhưng đã **USED**.
- Server **không cấp token mới từ RT-A**.
- Ghi sự kiện `REFRESH_TOKEN_REUSE_DETECTED` hoặc trạng thái tương đương.
- Theo policy, có thể **revoke cả family**, buộc reauthentication, thông báo user/security hoặc xem xét device risk.
- Audit ghi **token reference/family/client/session**, thời điểm, IP/device signals nếu được phép và cần thiết.

### 7.1. Phát hiện reuse không chỉ là “invalid_grant”

Một response OAuth `invalid_grant` có thể đến từ nhiều nguyên nhân:

- Token chưa từng tồn tại hoặc sai định dạng.
- Token đã expired.
- Token bị revoke sau logout/Leaver.
- Token không thuộc client hiện tại.
- Token đã USED, có dấu hiệu replay.
- Grant không còn hợp lệ theo policy.

**Không coi mọi `invalid_grant` là token theft**. Phân loại nguyên nhân nội bộ để security triage, đồng thời tránh response công khai tiết lộ quá nhiều trạng thái token cho attacker.

### 7.2. Không thể luôn phân biệt ai là attacker

Nếu cả client thật và attacker trình cùng refresh token, server thường biết **đã có reuse** nhưng có thể **không biết request nào là hợp lệ**. IP/User-Agent có thể hỗ trợ điều tra nhưng không phải bằng chứng chắc chắn, đặc biệt với NAT, VPN và mobile networks.

## 8. Khi nào cần revoke cả token family?

Một thiết kế an toàn thường có chiến lược **family invalidation** khi phát hiện reuse đáng ngờ, vì token kế tiếp hiện hành có thể đang do attacker sở hữu.

~~~text
RT-1 đã dùng để tạo RT-2.
RT-1 xuất hiện lại.

Không thể giả định:
  "RT-2 chắc chắn đang ở client hợp lệ."

Phản ứng có thể:
  REVOKE FAMILY F
  -> chặn mọi lần refresh tiếp theo của family
  -> yêu cầu reauthentication để lập grant mới
  -> phát sự kiện bảo mật
~~~

### 8.1. Family revoke khác subject-wide revoke

| Phạm vi | Tác động | Dùng khi |
|---|---|---|
| **Một refresh token** | Chặn token cụ thể | Một token đã USED/expired |
| **Một family/session** | Chặn việc tiếp tục refresh của phiên/thiết bị | Reuse hoặc logout thiết bị |
| **Mọi family của một client** | Đăng xuất client trên nhiều thiết bị/sessions | Client credential/registration compromise |
| **Mọi grant/session của subject** | Chặn truy cập rộng theo identity | Leaver/serious compromise tùy policy |
| **Mọi token do key bị lộ ký** | Cần ứng phó sự cố trust rộng | Signing-key compromise, yêu cầu IR riêng |

Không nên gây **logout toàn doanh nghiệp** chỉ vì một client tạo duplicate request trên một family; nhưng cũng **không giảm mức xử lý** nếu có bằng chứng compromise diện rộng.

### 8.2. Response sau family revoke

Client thường phải **dừng retry token cũ**, xóa state không còn hợp lệ và hướng user qua authentication/authorization flow lại. Một số app cần xử lý lưu nháp, session recovery và thông báo phù hợp thay vì lặp vô hạn lệnh refresh.

## 9. Race condition: hai request cùng trình một refresh token

Một ứng dụng có thể có nhiều thành phần làm mới token:

- Hai tab browser cùng phát hiện access token gần hết hạn.
- Hai HTTP requests trong mobile app cùng nhận 401.
- Hai worker processes dùng chung một credential store.
- Browser background timer và request foreground gọi refresh đồng thời.
- Load balancer/retry gửi request trùng.
- Network timeout khiến client gửi lại request cũ.

Ví dụ:

~~~text
RT-9 ACTIVE

Tab A: POST /token dùng RT-9
Tab B: POST /token dùng RT-9 gần cùng lúc

Server:
  A thắng -> RT-10 ACTIVE, RT-9 USED.
  B thua -> RT-9 đã USED -> reuse/invalid_grant.

Nếu B ghi đè token state của A bằng giá trị cũ:
  Client mất RT-10, vòng refresh tiếp theo thất bại.
~~~

### 9.1. Phía server phải kiểm atomicity

Nếu cả hai request đọc `RT-9 ACTIVE` trước khi update, **không được cùng tạo hai successor ACTIVE** một cách ngoài ý muốn. Cần transaction/CAS/unique constraint hoặc cơ chế đồng bộ tương đương.

### 9.2. Phía client cần singleflight

**Singleflight** là cơ chế gộp những yêu cầu refresh đồng thời trong cùng một process/client context, để chỉ có **một refresh đang chạy**, những request khác chờ kết quả:

~~~text
Request A thấy AT expired -> bắt đầu refresh RT-9
Request B thấy AT expired -> chờ promise của A
Request C thấy AT expired -> chờ promise của A

Refresh A thành công:
  AT-10, RT-10 lưu an toàn
  A, B, C dùng AT-10 cho request mới
~~~

**Singleflight theo một JavaScript process không tự giải quyết nhiều tab, nhiều worker, nhiều server hoặc hai thiết bị**. Cần thiết kế state ownership và đồng bộ phù hợp architecture.

## 10. Retry, mất response và “token đã dùng nhưng client không nhận token mới”

Kịch bản khó:

1. Client gửi `RT-7`.
2. Authorization Server **commit rotation**: `RT-7 USED`, `RT-8 ACTIVE`.
3. Response chứa `RT-8` bị mất do mạng.
4. Client chỉ còn `RT-7`.
5. Client retry `RT-7` và bị báo reuse/invalid_grant.

Điều này không nhất thiết là tấn công. Nhưng **server không thể vô tư cho dùng lại RT-7** vì attacker có thể lợi dụng cửa sổ đó.

### 10.1. Các phương án thiết kế và đánh đổi

| Phương án | Lợi ích | Rủi ro/điều kiện |
|---|---|---|
| **Fail closed, reauthenticate** | Đơn giản, không cho token cũ dùng lại | Có thể gây đăng xuất do mất mạng |
| **Client singleflight + retry policy hạn chế** | Giảm duplicate do chính client | Không giải quyết response đã commit nhưng mất |
| **Refresh coordination giữa tabs/processes** | Giảm race cục bộ | Phải quản lý ownership, storage và failure |
| **Server grace/overlap rất hạn chế** | Giảm lỗi do request tới sát nhau | Có thể mở cửa sổ replay nếu thiết kế sai |
| **Idempotent refresh recovery được ràng buộc chặt** | Có thể trả đúng kết quả cho retry hợp lệ | Cần cơ chế chứng minh retry không phải attacker, storage/expiry/consistency phức tạp |
| **Sender-constrained refresh token** | Token bị lấy riêng có thể khó dùng ở nơi khác | Cần bảo vệ private key và triển khai hỗ trợ |

**Không có mẹo “grace period 30 giây” an toàn cho mọi trường hợp**. Nếu áp grace, phải định nghĩa **cách phân biệt request hợp lệ, có cấp lại successor không, giới hạn replay và phản ứng khi lạm dụng**, dựa trên threat model.

### 10.2. Retry phải hiểu OAuth error

Không tiếp tục gửi cùng refresh token vô hạn khi nhận lỗi rõ ràng `invalid_grant`. Client nên dừng refresh loop, xóa grant state không hợp lệ và yêu cầu tái xác thực hoặc xử lý theo policy. Retry các lỗi mạng/5xx cần được thiết kế với hiểu biết rằng **server có thể đã commit rotation**.

## 11. Atomic rotation ở Authorization Server

Server phải đảm bảo **một phép chuyển trạng thái duy nhất** từ token hiện hành sang token kế nhiệm.

Một mô hình giao dịch:

~~~text
Input: RT-old
  -> tính token lookup/hash; kiểm client, family, expiry, grant
  -> lock / compare-and-set current generation
  -> xác nhận RT-old == ACTIVE current token
  -> tạo RT-new không đoán được
  -> đánh dấu RT-old USED
  -> lưu RT-new ACTIVE với parent và family
  -> commit cùng transaction
  -> response AT-new + RT-new

Nếu commit thất bại:
  Không trả token chưa có trạng thái nhất quán.

Nếu RT-old đã USED:
  Không phát successor mới từ token cũ.
  Phân loại replay/duplicate theo policy.
~~~

### 11.1. Những bất biến nên kiểm thử

1. **Một token đã USED không được tiếp tục mint access token.**
2. **Trong mỗi nhánh rotation đơn tuyến, không có hai current successor ngoài policy.**
3. **Nếu family bị REVOKED, mọi token thuộc family bị từ chối để refresh.**
4. **Token mới gắn đúng client/grant/subject và scope được phép.**
5. **Không cho token expired/unknown/client-mismatched tạo family mới.**
6. **Concurrent requests không có đường đua làm token cũ ACTIVE trở lại.**
7. **Một response không được nói thành công nếu cập nhật trạng thái thất bại.**
8. **Log không chứa raw refresh token hoặc secret.**

### 11.2. Database design phải xét multi-region

Nếu token service hoạt động trên nhiều vùng, một request có thể tới region A, request khác tới B. Nếu cả hai đọc bản sao chưa đồng bộ, họ có thể cùng thấy token ACTIVE. Cần **nguồn ghi nhất quán, lock/CAS, sticky routing có bảo đảm thích hợp hoặc protocol tránh split-brain**, không chỉ TTL cache.

## 12. Mã giả server minh họa rotation một lần

Ví dụ sau thể hiện các bước ở mức **logic nghiệp vụ**, không phải implementation production:

~~~python
def rotate_refresh_token(raw_refresh_token, authenticated_client, now, store):
    # raw_refresh_token chỉ tồn tại trong bộ nhớ cần thiết.
    # Không log, không đưa raw token vào exception/tracing.
    lookup_id = store.lookup_reference(raw_refresh_token)

    with store.transaction_for_token(lookup_id) as tx:
        token = tx.get_token_for_update(lookup_id)

        if token is None:
            return {"error": "invalid_grant"}

        if token.client_id != authenticated_client.client_id:
            tx.audit("CLIENT_BINDING_MISMATCH", token.reference)
            return {"error": "invalid_grant"}

        family = tx.get_family_for_update(token.family_id)

        if family.revoked or token.expires_at <= now:
            return {"error": "invalid_grant"}

        if token.state != "ACTIVE":
            tx.audit("REFRESH_TOKEN_REUSE_SIGNAL", token.reference)
            tx.revoke_family_if_policy_requires(family, "REUSE_DETECTED")
            return {"error": "invalid_grant"}

        if not tx.subject_and_grant_currently_eligible(token):
            tx.revoke_family(family, "GRANT_OR_SUBJECT_INELIGIBLE")
            return {"error": "invalid_grant"}

        successor = tx.create_secure_successor(
            family_id=family.id,
            parent_id=token.id,
            client_id=token.client_id,
            now=now,
        )

        tx.mark_used(token.id, used_at=now)
        tx.set_current_token(family.id, successor.id)
        tx.commit()

    # Ở implementation thật, access token cũng cần issuance policy,
    # scope/audience/session checks và transaction boundaries phù hợp.
    return {
        "access_token": "AT_NEW_PLACEHOLDER",
        "refresh_token": successor.one_time_response_value,
        "token_type": "Bearer",
        "expires_in": 600,
    }
~~~

**Quan trọng:** Đây là **pseudocode học thuật**. Không có schema storage, crypto, transaction API, idempotency, key management, token format/entropy, rate limiting hoặc error consistency thật. Không sao chép để triển khai Authorization Server production.

### 12.1. Lưu token tại server như thế nào?

Với refresh token **opaque đủ entropy**, có thể lưu **giá trị băm/định danh tra cứu được bảo vệ** thay vì plaintext; lựa chọn hashing và indexing phải phù hợp kiến trúc và khả năng kiểm. Nếu server cần trả token mới, **giá trị response phải được phát an toàn trong quy trình issuance**; không giữ plaintext cũ tùy tiện để phục vụ debug.

Nếu dùng refresh token dạng JWT, dù đã kiểm signature/`exp`, **rotation vẫn cần state** để biết token đã USED/revoked và xác định family. **Chỉ dựa vào chữ ký JWT không phát hiện reuse theo đúng nghĩa**.

## 13. Phía client: singleflight và lưu token mới nguyên tử

Một client có thể bị lỗi nếu **response cũ đến sau response mới** và ghi đè token state.

Ví dụ mô hình logic:

~~~javascript
// Pseudocode: chỉ gộp refresh trong cùng một process.
// Không dùng nguyên xi cho browser đa tab hoặc production.
let inFlightRefresh = null;

async function getFreshAccessToken() {
  if (hasUsableAccessToken()) {
    return readAccessTokenFromSecureStore();
  }

  if (!inFlightRefresh) {
    inFlightRefresh = refreshThroughTrustedTokenHandler()
      .then(async (result) => {
        // Token handler phải kiểm response, bảo vệ storage,
        // và cập nhật AT/RT như một thay đổi nhất quán.
        await persistTokenPairAtomically(result);
        return result.accessToken;
      })
      .finally(() => {
        inFlightRefresh = null;
      });
  }

  return inFlightRefresh;
}
~~~

**Giới hạn:** Đây là logic một process. Không giải quyết multi-tab, service worker, hai backend workers, crash giữa save và response, leak trong browser JS hoặc replay detection của server. Storage cần phù hợp **client type, threat model và nền tảng**.

### 13.1. Các lưu ý thực tế

- **Không gửi cùng RT cũ từ nhiều request đồng thời** trong cùng client context.
- Lưu **AT và RT successor như một phiên bản state nhất quán** khi có thể.
- Bảo vệ refresh token khỏi log, error report, analytics, query string.
- Khi storage bị lỗi sau refresh, cần luồng phục hồi/reauth rõ.
- Không âm thầm phát lại token cũ sau `invalid_grant`.
- Tránh **refresh storm** khi hàng trăm requests cùng nhận 401.
- Không coi mọi 401 là “refresh token hết hạn”; có thể là **authorization DENY** do RBAC/ABAC.

## 14. TTL của refresh token: thời hạn tuyệt đối và thời hạn không hoạt động

**Rotation sau mỗi lần dùng** không tự xác định refresh grant có thể kéo dài bao lâu. Có thể cần hai loại giới hạn:

- **Absolute refresh token/grant lifetime:** Mốc cuối mà family có thể tiếp tục tồn tại bất kể refresh nhiều lần.
- **Inactivity expiration:** Nếu client không refresh hoặc không có hoạt động phù hợp trong thời gian quy định, grant/family hết hạn.

Ví dụ:

~~~text
Family createdAt:        01/12 08:00
Absolute grant expiry:  31/12 08:00
Inactivity limit:       7 ngày (giả lập)

01/12: RT-1 -> RT-2
02/12: RT-2 -> RT-3
20/12: RT-3 bị trình sau 18 ngày im lặng
       -> Từ chối nếu inactivity policy đã hết.

Kể cả refresh hằng ngày:
  31/12: absolute grant expiry vẫn có hiệu lực
         nếu policy quy định hard stop.
~~~

Các mốc chỉ minh họa, **không phải thời hạn bắt buộc**. Một provider có thể triển khai sliding expiration, absolute bound hoặc kết hợp. Hệ thống phải đọc contract và cấu hình thực tế.

### 14.1. Sai lầm: reset absolute expiry mỗi lần rotation

Nếu mỗi lần refresh server đặt `grantExpiresAt = now + 30 days`, một grant có thể **tồn tại vô hạn** dù policy muốn giới hạn cứng. Cần tách **refresh token instance TTL** và **family/grant absolute lifetime**.

## 15. Access token còn hiệu lực sau refresh-token reuse

Xét timeline:

~~~text
10:00: RT-1 -> AT-1 + RT-2
10:01: Dùng lại RT-1 -> phát hiện reuse -> family REVOKED
10:02: AT-1 vẫn có exp đến 10:10

Nếu API chỉ kiểm JWT signature/exp/audience:
  AT-1 có thể vẫn được chấp nhận đến 10:10.

Nếu policy yêu cầu chặn ngay:
  Cần revocation/status enforcement hoặc biện pháp khác
  ở Authorization Server/Resource Server/PEP.
~~~

**Đóng refresh token family không tự làm access token đã phát hết hạn ngay.** Hệ thống có thể lựa chọn **access token TTL ngắn, token introspection, revoke list/token version, kiểm subject state, proof-of-possession** hoặc cơ chế phù hợp để đáp ứng risk window.

### 15.1. Độ trễ thu hồi phải được thiết kế

Một ứng dụng đọc báo cáo ít nhạy cảm và API quản trị production có thể yêu cầu **revocation latency** khác nhau. Cần xác định độ trễ tối đa tổ chức chấp nhận và **đo tại Resource Server**, không chỉ tại Authorization Server.

## 16. Token revocation và trạng thái Grant/Session

Rotation phải phối hợp với **revocation** khi có tín hiệu:

- Người dùng logout trên thiết bị.
- User chọn “đăng xuất mọi thiết bị”.
- Refresh token reuse đáng ngờ.
- User/contractor **Leaver**.
- User **Mover** làm grant cũ không còn scope hợp lệ.
- Client registration bị thu hồi hoặc credential bị lộ.
- Security phát hiện account takeover, device compromise.
- Access review quyết định REVOKE.
- Consent/permission bị rút.
- Workload bị decommission.

### 16.1. Các lớp cần cùng hiểu trạng thái

| Nơi xử lý | Trách nhiệm |
|---|---|
| **Authorization Server** | Không cấp token mới từ grant/family đã revoked |
| **IdP/session service** | Xử lý session/reauth theo scope được hỗ trợ |
| **Resource Server/PEP** | Không cho action trái chính sách với access token hiện hữu |
| **IAM/IGA** | Chuyển JML/role/review events, quản lý desired access |
| **SCIM/target app** | Cập nhật account/role khi hỗ trợ |
| **PAM/PIM** | Revoke privileged grant/eligible role và kiểm target session |
| **Audit/monitoring** | Ghi decision, effect, lỗi và trạng thái chưa xác minh |

**Một nút “Revoke refresh token” ở giao diện không tự chứng minh mọi token, local session và direct ACL tại mọi ứng dụng đã mất hiệu lực.**

## 17. OIDC, SSO và refresh-token rotation

Trong hệ thống OIDC, một ứng dụng có thể:

1. Dùng Authorization Code flow với PKCE khi phù hợp.
2. Nhận token từ Authorization Server sau khi người dùng xác thực.
3. Duy trì app session riêng.
4. Nếu được cấp refresh token, sử dụng nó để xin access token mới theo policy.
5. Khi refresh token rotation bật, phải thay token cũ trong storage.
6. Khi reuse hoặc grant revoke, xử lý reauthentication đúng quy trình.

**Refresh-token family và IdP SSO session không nhất thiết là một đối tượng**. Một refresh family bị revoke có thể yêu cầu client quay lại OIDC authorization flow, nhưng IdP có thể còn SSO session và không hỏi mật khẩu, tùy mức `max_age`, `prompt`, `auth_time` và policy.

### 17.1. Rotation không phải kiểm tra MFA mới

Client nhận access token mới qua refresh token **không có nghĩa người dùng vừa vượt MFA**. Với hành động nhạy cảm, ứng dụng phải đánh giá **authentication freshness/assurance** và yêu cầu reauthentication/step-up khi cần.

### 17.2. Refresh token khác ID token

Một ID token có `exp` hết hạn không có nghĩa “refresh token đã bị sử dụng lại”. Đừng triển khai rotation bằng cách dùng ID token làm credential gọi token endpoint hoặc gọi API.

## 18. Browser client: lưu refresh token ở đâu?

Browser là môi trường có threat model đặc biệt: JavaScript có thể bị ảnh hưởng bởi **XSS hoặc dependency compromise**, và các tab có thể cùng tồn tại.

Các kiến trúc nên cân nhắc:

| Kiến trúc | Cách làm | Đánh đổi |
|---|---|---|
| **Backend for Frontend (BFF)** | Backend giữ refresh token; browser dùng cookie phiên được bảo vệ | Giảm phơi bày RT cho JavaScript, nhưng backend/session/CSRF cần bảo vệ |
| **Server-rendered app** | Server giữ grant/refresh token trong storage kiểm soát | Cần quản lý server session, encryption và revoke |
| **Browser public client với RT** | Browser giữ token theo khả năng và chính sách Authorization Server | Rủi ro XSS/storage và đa tab cao hơn; cần rotation/hoặc sender constraint phù hợp |
| **Không phát RT cho browser** | Dựa vào session/BFF/reauth và flows được hỗ trợ | Có thể nhiều reauthentication hơn |

### 18.1. Cookie không phải tự động an toàn

BFF có thể dùng cookie `HttpOnly`, `Secure`, `SameSite` thích hợp để giảm JS đọc token, nhưng vẫn phải có:

- Chống CSRF theo cơ chế phù hợp.
- Session ID mạnh, giới hạn idle/absolute.
- Server-side logout và grant revocation.
- Scope cookie/domain tối thiểu.
- Chính sách chống session fixation/hijacking.
- Bảo vệ backend token store và log.

### 18.2. LocalStorage không phải vault bí mật

Nếu refresh token xuất hiện trong localStorage hoặc JavaScript runtime, **XSS có thể đọc hoặc sử dụng token** tùy kịch bản. Rotation làm giảm một phần khả năng dùng token cũ nhưng không thay ngăn XSS, CSP, dependency review hoặc lựa chọn BFF.

## 19. Mobile/native client và storage an toàn

Ứng dụng native có thể cần phiên dài và hoạt động offline. Khi được cấp refresh token, nên:

- Sử dụng secure storage của nền tảng phù hợp threat model.
- Không ghi RT vào log, backup không được bảo vệ hoặc analytics.
- Bảo vệ luồng refresh khi ứng dụng chạy foreground/background.
- Đồng bộ token state giữa các request cùng process.
- Xử lý crash/mất mạng và `invalid_grant` có kiểm soát.
- Tách grant/family theo thiết bị khi server cho phép.
- Cho user/security thu hồi một thiết bị hoặc tất cả thiết bị.
- Không coi device ID tự khai là chứng minh possession.
- Cân nhắc sender-constrained token theo khả năng.
- Định nghĩa session lock/reauth cho dữ liệu nhạy cảm.

### 19.1. Device binding phải có trust

Một chuỗi `deviceId=phone123` do client tự gửi không chứng minh request thật đến từ đúng điện thoại. Nếu thiết kế dùng **sender-constrained token**, cần binding bằng khóa hoặc phương thức có khả năng chứng minh possession theo giao thức, không chỉ header tùy ý.

## 20. Token rotation và sender-constrained tokens

**Sender-constrained token** là token được ràng buộc với một **bằng chứng sở hữu khóa hoặc yếu tố mật mã** của client. Ví dụ kiến trúc OAuth có thể sử dụng **mTLS-bound tokens** hoặc **DPoP** khi nền tảng hỗ trợ.

- Với **bearer token**, ai có token có thể thử sử dụng nó nếu không có hạn chế khác.
- Với **sender-constrained token**, chỉ trình token thường **chưa đủ**; bên nhận còn phải kiểm bằng chứng possession tương ứng.
- **Refresh token rotation** khiến việc dùng lại token cũ có thể bị phát hiện.
- Sender constraint có thể **kết hợp** với rotation để giảm rủi ro token bị lấy riêng.

### 20.1. Sender constraint không phải phép màu

Nếu attacker chiếm luôn thiết bị/runtime hoặc lấy được private key, attacker có thể tạo proof hợp lệ theo khả năng bị xâm phạm. Cần:

- Quản lý khóa an toàn.
- Kiểm issuer, audience, proof, time/jti/nonce/replay theo giao thức.
- Đảm bảo Authorization Server và Resource Server thực sự hỗ trợ.
- Rotation/revoke khi credential/thiết bị bị compromise.
- Đánh giá tác động khi mất khóa, cài lại app hoặc đổi thiết bị.

**Không chỉ thêm header `DPoP` vào request rồi coi token đã sender-constrained**. Phải triển khai đầy đủ các bước xác minh của giao thức.


## 21. Rotation khác thay OAuth client secret hoặc API key

**Client secret rotation** là thay **credential client dùng xác thực với Authorization Server**. Nó khác **refresh token rotation**, vốn thay token dùng duy trì một grant đã cấp.

Ví dụ:

~~~text
OAuth client: billing-integration
Client credential hiện tại: SECRET-v1
Refresh token hiện tại: RT-25
Access token đang dùng: AT-101

Rotate client secret:
  SECRET-v1 -> SECRET-v2
  Không tự có nghĩa RT-25/AT-101 bị revoke ngay.

Rotate refresh token:
  RT-25 -> RT-26
  Không tự có nghĩa SECRET-v1 mất hiệu lực.

Revoke access grant:
  RT family bị revoke
  API có thể còn chấp nhận AT-101 tới khi
  token expiry/status enforcement có hiệu lực.
~~~

### 21.1. Quy trình đổi client credential an toàn

1. Đăng ký việc thay secret/key và owner theo policy.
2. Tạo **credential mới** bằng phương pháp an toàn; không sao chép plaintext vào ticket.
3. Nếu target cho phép **overlap hai credential**, thiết kế cửa sổ chuyển đổi hạn chế.
4. Cập nhật workload/BFF/CI/CD từ secret store hoặc key reference mới.
5. Thử xác thực bằng credential mới và kiểm quyền đúng scope.
6. Revoke credential cũ **tại Authorization Server/target**, không chỉ xóa file cấu hình.
7. Kiểm credential cũ không còn được dùng.
8. Đánh giá access/refresh token đã phát và quyền còn hiệu lực.
9. Ghi audit, owner, expiry và xử lý lỗi một phần.

Nếu client secret đã **bị lộ**, có thể cần hành động khẩn cấp hơn quy trình rotation thường ngày: revoke nhanh, đánh giá token đã phát, chặn target nếu chính sách yêu cầu.

### 21.2. Đừng dùng API key cho mọi mục đích

API key là dạng credential của nhiều hệ thống, **không đồng nhất với OAuth refresh token**. Không thể mặc nhiên áp family/reuse detection OAuth lên một API key có thể dùng lặp lại bình thường. Với API key, cần cấp key mới, chuyển client, revoke key cũ, giới hạn scope và theo dõi khả năng sử dụng.

## 22. JWT signing-key rotation và JWKS rollover là quy trình khác

Một IdP/Authorization Server có thể ký JWT bằng private key và công bố **public key** qua JWKS để client/Resource Server xác minh. **Signing-key rotation** thay khóa ký của issuer, không phải refresh-token rotation.

### 22.1. Luồng thay khóa ký có kiểm soát

~~~mermaid
flowchart TD
    A["Issuer đang ký bằng key-old<br/>JWKS có public key-old"] --> B["Tạo key-new an toàn<br/>Private key không công bố"]
    B --> C["Công bố public key-new trong JWKS<br/>vẫn giữ public key-old"]
    C --> D["Xác minh consumer có thể đọc<br/>và cache key-new"]
    D --> E["Issuer bắt đầu ký JWT mới<br/>bằng key-new/kid=new"]
    E --> F["Duy trì khả năng validate<br/>JWT hợp lệ ký bằng key-old"]
    F --> G["Sau TTL + clock skew + cache policy<br/>và đánh giá consumer"]
    G --> H["Retire old verification key<br/>kèm audit + monitoring"]
~~~

Các bước là **mô hình rollover thông thường**; quy trình khi **private signing key bị compromise** khác về mức cấp bách và có thể buộc thu hồi/hạn chế các JWT cũ trước khi hết `exp`.

### 22.2. Các chi tiết phải kiểm

- **`kid`** giúp bên nhận chọn key xác minh; không phải quyền tự quyết nguồn trust.
- Public key trong JWKS không được chứa **private key**.
- API phải giới hạn **issuer, audience và thuật toán được phép**, không tin một JWT vì header tự nêu thuật toán.
- Cần xử lý **JWKS cache**, refresh khi gặp `kid` chưa biết theo chính sách, tránh mạng lỗi làm xác minh không ổn định.
- Duy trì old public key đủ lâu để xác minh **token còn hiệu lực** trong rollover thường.
- Không giữ old key vô thời hạn nếu nó đã bị ngừng tin cậy.
- Theo dõi tỷ lệ token verification failure, key lookup failure và latency.
- Có rollback hợp lệ nếu key-new gây lỗi, nhưng **không “rollback trust”** khi key-old đã bị lộ.

### 22.3. Token family và JWT key là hai lớp độc lập

Một JWT access token được ký bằng key-new vẫn có thể bị từ chối vì **subject Leaver hoặc RBAC deny**. Một refresh token đã dùng lại vẫn phải bị phát hiện, dù Authorization Server vừa thay signing key.

**Đổi `kid` không thay thế refresh-token reuse detection.**

## 23. Scope, audience và grant khi rotation

Khi dùng refresh token để xin access token mới, server không nên tự **mở rộng quyền** chỉ vì client muốn.

Các điều kiện cần kiểm:

- **Client:** Refresh token được phát cho client nào, phương thức xác thực/binding hợp lệ?
- **Subject:** Human/workload có còn eligible?
- **Grant:** Consent/authorization còn tồn tại?
- **Scope:** Quyền yêu cầu có nằm trong phạm vi đã được cấp và policy hiện tại?
- **Audience/resource:** Token mới dành cho API dự kiến hay một hệ thống khác?
- **Tenant/project:** Quyền có còn thuộc assignment hiện hành?
- **Risk:** Có security hold, SoD conflict hoặc hành vi bất thường?
- **Freshness:** Hành động nhạy cảm có cần reauthentication mới thay vì refresh?
- **Lifetime:** Token mới có vượt mốc absolute grant/session không?

### 23.1. Rotation không phải cơ chế đổi role

Nếu nhân viên Mover từ Sales sang Finance, việc phát `RT-2` từ `RT-1` **không tự cập nhật mọi vai trò**. Authorization Server có thể chỉ cấp scope đã thu hẹp theo policy, yêu cầu authorization lại hoặc revoke grant cũ, tùy thiết kế.

### 23.2. Tránh quyền quá rộng khi token thiếu scope cụ thể

Một token có `role=reader` không đủ bảo vệ cross-tenant nếu API **không kiểm resource tenant**. RBAC/ABAC/PBAC tại Resource Server cần đảm bảo action trên resource thật sự nằm trong **desired access**.

## 24. Non-human account và OAuth Client Credentials

Trong machine-to-machine (M2M), nhiều client dùng **OAuth Client Credentials grant** để nhận access token bằng cách xác thực chính client, thường **không cần refresh token**: khi access token hết hạn, workload có thể xin access token mới bằng cơ chế client authentication còn hợp lệ.

~~~mermaid
sequenceDiagram
    autonumber
    participant W as Workload / Service Account
    participant AS as Authorization Server
    participant API as Resource Server
    participant I as IAM / Service catalog
    W->>AS: Client authentication + token request
    AS->>I: Kiểm client, workload, allowed scope
    I-->>AS: Eligible + policy-bound grants
    AS-->>W: Access token với TTL/scope/audience
    W->>API: API call dùng access token
    API->>API: Validate issuer, audience, time, access
    API-->>W: Response
    Note over W,AS: Token hết hạn -> xin token mới<br/>bằng client authentication thích hợp
~~~

### 24.1. Bốn nhóm rotation khác nhau ở workload

1. **Access token issuance/renewal:** Xin token mới khi token cũ hết hạn hoặc gần hết hạn.
2. **Client credential rotation:** Đổi secret/private key/certificate nếu đang dùng.
3. **Workload identity trust/key management:** Đổi certificate hoặc trust config của platform khi cần.
4. **OAuth refresh token rotation:** **Chỉ áp dụng nếu thực sự có refresh token** và provider/flow hỗ trợ.

**Không tạo một refresh token giả cho Client Credentials chỉ để sử dụng cùng code với mobile login.**

### 24.2. Owner của workload cũng là thành phần vòng đời

Một service principal cần technical owner, mục đích, tenant, environment, allowed audience, credential reference và deadline/review trigger. **Token tự hết hạn không xóa role assignment hoặc principal đã bỏ dùng**.

## 25. Token rotation cho quyền đặc quyền PAM/PIM

Một privileged session có thể dùng:

- Cookie/session của cloud admin console.
- OAuth access/refresh token ở administrative client.
- PIM/JIT activation token.
- PAM session handle hoặc credential checkout.
- CLI credential tạm thời của cloud.
- Database/SSH session mở lâu.

**Không phải tất cả những hiện vật trên đều cần hay hỗ trợ OAuth refresh token rotation.** Nhưng chúng có chung mục tiêu: **giới hạn thời gian và khả năng sử dụng lại quyền cao**.

Ví dụ:

~~~text
20:00  Kỹ sư mở emergency/PIM grant tới 20:30
20:05  Admin client nhận AT-1, RT-1
20:15  RT-1 -> AT-2, RT-2
20:30  JIT grant hết hạn
20:32  Client tiếp tục refresh RT-2?

Kỳ vọng an toàn:
  Authorization Server phải xét JIT/grant eligibility,
  không chỉ "RT-2 còn ACTIVE".
  Resource Server/target phải chặn action privileged
  sau mốc policy, kể cả token/session còn hạn.
~~~

### 25.1. Timeout activation khác rotation

Nếu `RT-2` còn hợp lệ sau khi JIT grant hết hạn, server vẫn phải từ chối cấp scope đặc quyền không còn căn cứ. Rotation **không kéo dài activation TTL**.

### 25.2. Break-glass và hoạt động khẩn cấp

Phiên khẩn cấp có thể cần phương án authentication/credential dự phòng khi IdP/PAM lỗi. Nhưng không nên để các refresh family/token đặc quyền tồn tại không giới hạn sau khi incident kết thúc. Cần **revoke, session termination, log/alert và hậu kiểm** phù hợp khả năng phục hồi.

## 26. Joiner: phát token theo account và quyền ban đầu

Trong mô hình **Joiner**, tổ chức xác minh person, tạo account và cấp role theo nhiệm vụ:

- HR/VMS xác nhận **identity/engagement/effectiveAt**.
- IAM/IGA cấp role ban đầu theo catalog đã được duyệt.
- IdP/Authorization Server chỉ phát token/grant cho subject/client đủ điều kiện.
- Client lưu token theo cơ chế phù hợp, dùng rotation khi có refresh token.
- API/PEP kiểm scope, tenant và resource, không chỉ token signature.
- Các account onboarding/test cần được xử lý riêng; không dùng credential của nhân viên tiền nhiệm.
- Token family có nguồn grant và thời điểm phát rõ, gắn với session/client/device nếu cần.

**Không được phát token có quyền làm việc trước mốc bắt đầu** chỉ vì account Joiner đã được chuẩn bị. Nếu policy cho account setup trước ngày đi làm, cần tách **onboarding access** khỏi quyền nghiệp vụ production.

## 27. Mover: quyền đã thay đổi không chờ rotation “tự chữa”

Khi nhân viên đổi vai trò, phòng ban, dự án hoặc địa điểm, một access token cũ có thể chứa claims/scope của quyền trước đây. Refresh token family có thể còn ACTIVE.

Ví dụ:

~~~text
Trước Mover:
  P-2048: sales.export@tenant-A
  RT-FIN? Không, đây là grant của CRM Sales
  AT-1: scope=sales.export

Sau Mover:
  P-2048: finance.read@project-B
  sales.export phải bị thu hồi theo policy.

Nếu client dùng RT-2 để mint AT-3:
  Không được tự động cấp sales.export chỉ vì
  RT-2 có status ACTIVE.
~~~

### 27.1. Quy trình phối hợp

1. HR/VMS phát **Mover event** với identity và effective time.
2. IAM/IGA tính lại **desired access** theo role mới.
3. Rút role/group/direct ACL và đánh giá các grant liên quan vai trò cũ.
4. Authorization Server quyết định **revoke token family, thu scope hoặc yêu cầu authorization lại** tùy policy.
5. Resource Server thực thi permission hiện hành cho tenant/resource/action.
6. Kiểm access token/session đã phát còn cửa sổ nào thực hiện quyền cũ không.
7. Đối soát quyền mới phục vụ nhiệm vụ hợp lệ.
8. Lưu audit và readback, theo dõi lỗi đồng bộ/regrant.

**Một refresh token mới không chứng minh quyền đã được cập nhật**; chỉ target permission check hoặc bằng chứng enforcement tương ứng mới trả lời được.

### 27.2. Hai engagement và nhiều token families

Một contractor có dự án A và B có thể có các grants/families riêng. A kết thúc nhưng B còn hợp lệ: nên **thu hồi grant A và các quyền liên quan**, không nhất thiết xóa mọi session B nếu policy không yêu cầu.

## 28. Leaver: thu hồi theo sự kiện, không đợi RT hết hạn

**Leaver** là ví dụ rõ nhất về việc **token rotation không đủ**. Khi employment/engagement kết thúc, tổ chức cần chặn quyền theo mốc policy, không đợi refresh token tiếp tục được rotate đến absolute expiry.

~~~mermaid
flowchart TD
    H["HR/VMS<br/>Leaver event + effectiveAt"] --> I["IAM/IGA<br/>Canonical subject + engagements"]
    I --> AS["Authorization Server<br/>Revoke grants/token families"]
    I --> IDP["IdP / SSO<br/>Disable auth + revoke sessions"]
    I --> SCIM["SCIM/API/Directory<br/>Remove role, group, local account"]
    I --> PAM["PAM/PIM<br/>Revoke elevated grants/sessions"]
    AS --> R["Resource Servers / PEP<br/>Enforce state & deny actions"]
    IDP --> R
    SCIM --> R
    PAM --> R
    R --> V["Readback/negative tests<br/>Effective access"]
    V --> Q{"Đúng desired state<br/>theo policy?"}
    Q -->|Có| C["Verified closure + audit"]
    Q -->|Không / Unknown| E["Exception / owner / mitigation"]
    E --> R
~~~

### 28.1. Một token tự chứa vẫn có thể sống sau revoke family

Nếu API không kiểm trạng thái hiện hành và chỉ dựa vào `iss/aud/exp`, access token được phát trước Leaver có thể còn được chấp nhận tới `exp`. Với chính sách chặn ngay, cần cơ chế **revocation, authorization state check, token lifetime rất phù hợp hoặc PEP control** đáp ứng thời gian yêu cầu.

### 28.2. Đừng coi `SCIM active=false` là “đã logout tất cả”

SCIM có thể cập nhật account/role tại target hỗ trợ, nhưng không mặc nhiên thu hồi **local session, refresh token, JWT, PAT, SSH key hoặc direct ACL**. Workflow cần inventory và readback ở đúng hệ thống.

### 28.3. Rejoiner không tự khôi phục family cũ

Người quay lại tổ chức cần xác minh/eligibility theo nhiệm vụ hiện tại, lập grant/session hợp lệ mới. Không kích hoạt lại refresh-token family đã revoke do Leaver chỉ vì email hoặc tên account cũ được dùng lại.

## 29. Phân quyền và thu hồi theo RBAC/ABAC/PBAC

Token rotation là **kiểm soát về sử dụng credential**, còn RBAC/ABAC/PBAC kiểm **quyền trên resource**.

Giả sử:

~~~text
Client đã refresh thành công:
  AT-new còn 10 phút
  scope: "reports.read"

Subject sau Mover:
  allowedTenant: tenant-B

Request:
  GET /tenants/tenant-A/reports

Kết quả đúng:
  DENY do resource/tenant không hợp lệ,
  dù AT-new vừa được phát và signature hợp lệ.
~~~

### 29.1. Claims cũ và authorization state

JWT có thể chứa role/scope snapshot từ thời điểm phát token. Nếu IAM thay đổi policy, Resource Server cần quyết định **claims nào đủ ổn định trong TTL** và **quyền nào phải tra trạng thái hiện hành**. Không có một TTL cache phù hợp mọi rủi ro.

### 29.2. Token refresh không nâng quyền tự động

Với một request tăng scope mới, thường cần **authorization/consent/approval** theo policy. Không cho client dùng RT để “xin thêm `admin`” ngoài grant hiện hành chỉ vì `scope` trong request body rộng hơn.

## 30. Phát hiện và xử lý reuse trong vận hành

Một event reuse cần được **triage theo ngữ cảnh**, tránh vừa bỏ sót compromise vừa gây logout hàng loạt do race thông thường.

| Tín hiệu | Có thể có nghĩa | Kiểm tra tiếp |
|---|---|---|
| Token đã USED xuất hiện lại gần như đồng thời | Two-tab race, retry hoặc theft | Client version, request correlation, family timeline |
| Reuse từ vị trí/thiết bị khác | Có thể là token bị lấy cắp | Binding, device proof, network risk, identity telemetry |
| Reuse sau nhiều giờ/ngày | Stale storage, backup restore hoặc attacker | Device reset, leaked token, credential exposure |
| Cùng client tạo hàng trăm `invalid_grant` | Refresh loop hoặc tấn công | SDK logs, rate limiting, issued family count |
| Một grant bị revoke rồi tiếp tục refresh | Client dùng stale state hoặc cố lạm dụng | Revoke reason, target IP, session history |
| JWT/API vẫn hoạt động sau reuse revoke | Resource Server không kiểm trạng thái hoặc token còn hạn | Revocation propagation, `exp`, API enforcement |
| Nhiều user đồng loạt lỗi sau triển khai | SDK/backend race hoặc provider config thay đổi | Release ID, feature flags, rollback strategy |
| Refresh request mang client binding không khớp | Sai client configuration hoặc misuse | Client registration, secret/key changes, tampering |
| Token xuất hiện trong log | Credential leak | Secret exposure response, purge/rotation/revoke |

**Không ghi raw RT vào log để “đối chiếu cho dễ”.** Sử dụng **token reference, family ID, generation, event ID, client ID, subject ID theo chính sách riêng tư**.

### 30.1. Mẫu xử lý reuse đáng ngờ

1. Server từ chối sử dụng lại token đã USED theo policy.
2. Đánh dấu sự kiện và family state đáng tin.
3. Xem có cần revoke family và gửi cảnh báo tới client/user/security.
4. Nếu có dấu hiệu compromise rộng, đánh giá scope subject/client và access tokens đã phát.
5. Hỗ trợ client tái xác thực có kiểm soát.
6. Theo dõi API còn chấp nhận quyền nào sau revoke.
7. Điều tra concurrent refresh, lỗi mạng và storage để tránh tái diễn.
8. Ghi thời gian từ tín hiệu tới **verified blocking** theo mức rủi ro.

## 31. Schema minh họa: token family và trạng thái rotation

~~~json
{
  "familyId": "FAM-8801",
  "clientId": "mobile-finance-app",
  "subjectId": "P-2048",
  "deviceContextRef": "DEV-REGISTERED-72",
  "grantRef": "GRANT-144",
  "status": "ACTIVE",
  "familyCreatedAt": "2026-12-01T08:00:00+07:00",
  "absoluteExpiresAt": "2027-01-01T08:00:00+07:00",
  "currentTokenRef": "RT-REF-4",
  "currentGeneration": 4,
  "lastRotationAt": "2026-12-05T10:00:00+07:00",
  "tokenInstances": [
    {
      "tokenRef": "RT-REF-3",
      "parentTokenRef": "RT-REF-2",
      "generation": 3,
      "status": "USED",
      "usedAt": "2026-12-05T10:00:00+07:00"
    },
    {
      "tokenRef": "RT-REF-4",
      "parentTokenRef": "RT-REF-3",
      "generation": 4,
      "status": "ACTIVE",
      "usedAt": null
    }
  ],
  "security": {
    "reuseDetected": false,
    "revokedAt": null,
    "revocationReason": null
  }
}
~~~

**Dữ liệu chỉ để học**, không phải format chuẩn của OAuth hoặc một sản phẩm IAM. Các giá trị `tokenRef` chỉ là **ID tham chiếu**, không phải token plaintext dùng được. Bản ghi production cần bảo vệ PII, kiểm concurrency, retention, transaction và các policy fields cần thiết.

### 31.1. Không gửi lineage đầy đủ cho browser

Dữ liệu family/usedAt/risk signals chủ yếu dành cho Authorization Server và audit. Client không cần biết toàn bộ history để refresh; cấp quá nhiều thông tin có thể làm lộ nội bộ hoặc tăng nguy cơ tấn công.

## 32. Policy rotation mẫu có thể kiểm toán

~~~yaml
# Ví dụ học tập, KHÔNG phải cấu hình chuẩn cho provider.
policyId: oauth-refresh-rotation-v1
owner: iam-security
humanInteractiveClients:
  refreshTokenRotation: true
  rejectAlreadyUsedRefreshToken: true
  reuseResponse: REVOKE_AFFECTED_FAMILY_AND_REQUIRE_REAUTH
  familyAbsoluteLifetime: POLICY_DEFINED
  inactivityLifetime: POLICY_DEFINED
  concurrentRefreshBehavior: SINGLE_SUCCESSOR
  lostResponseRecovery: REAUTH_IF_NO_SECURE_RECOVERY
  rawTokenLogging: PROHIBITED
  requireScopeAndAudienceValidation: true
browser:
  preferBackendManagedTokenStorageWhereFeasible: true
  requireCsrfAndSessionProtection: true
native:
  requirePlatformAppropriateSecureStorage: true
workloadClients:
  humanRefreshTokenRulesNotAssumed: true
  preferShortLivedAccessTokenAndStrongClientAuthentication: true
  ownerAndCredentialLifecycleRequired: true
revocationTriggers:
  - LEAVER
  - GRANT_WITHDRAWN
  - SECURITY_COMPROMISE
  - REUSE_DETECTED
  - AUTHORIZED_LOGOUT
resourceServers:
  enforceTokenIssuerAudienceAndExpiry: true
  enforceCurrentAuthorizationByRisk: true
  trackRevocationPropagation: true
audit:
  tokenReferencesOnly: true
  recordFamilyAndPolicyVersions: true
  verifyNoResidualAccessWhenRequired: true
~~~

### 32.1. Policy không thay implementation

Một field `refreshTokenRotation=true` trong YAML **không tự làm Authorization Server atomic**. Cần kiểm bản thân provider có hỗ trợ, client SDK thay RT đúng cách, database có concurrency control và Resource Server có cơ chế revoke/authorization tương ứng.

## 33. Audit events cần theo dõi

| Event | Ý nghĩa | Các trường quan trọng |
|---|---|---|
| **REFRESH_TOKEN_ISSUED** | Tạo RT đầu tiên hoặc successor | Family, token ref, client, subject, issuance time |
| **REFRESH_TOKEN_ROTATED** | RT hợp lệ được tiêu thụ và thay | Parent ref, successor ref, generation, time |
| **REFRESH_TOKEN_REUSE_DETECTED** | Một RT đã dùng được trình lại | Family, token ref, classification, client, time |
| **TOKEN_FAMILY_REVOKED** | Dừng mọi refresh trong family | Reason, actor/system, time, policy version |
| **REFRESH_FAILED** | Làm mới thất bại | Error category, correlation ID, không log raw token |
| **REAUTH_REQUIRED** | Client cần auth flow mới | Subject/client/session ref, reason |
| **ACCESS_TOKEN_ISSUED** | Cấp AT mới | Token ref, audience, allowed scope, TTL |
| **CLIENT_CREDENTIAL_ROTATED** | Thay client auth material | Client ref, old/new key reference |
| **SIGNING_KEY_ACTIVATED** | Issuer đổi active signing key | `kid`, key ref, rollout version |
| **JML_GRANT_REVOKE** | Mover/Leaver thay eligibility | Event, effectiveAt, impacted grants |
| **RESOURCE_ACCESS_DENIED** | API từ chối action | Subject/client, resource, reason, policy |
| **REVOCATION_VERIFIED** | Quyền thực tế đã không còn theo scope | Verification method, target, time |
| **REMEDIATION_EXCEPTION** | Chưa xác minh/thu hồi được | Owner, risk, deadline, mitigating controls |

### 33.1. Một event mẫu

~~~json
{
  "eventType": "REFRESH_TOKEN_REUSE_DETECTED",
  "eventId": "EVT-2026-1142",
  "time": "2026-12-05T10:00:04+07:00",
  "familyRef": "FAM-8801",
  "tokenRef": "RT-REF-3",
  "clientId": "mobile-finance-app",
  "subjectRef": "P-2048",
  "observedTokenState": "USED",
  "responsePolicy": "REVOKE_FAMILY",
  "familyStatusAfter": "REVOKED",
  "confidence": "REUSE_OBSERVED_ACTOR_UNKNOWN",
  "correlationId": "AUTH-REQ-7719",
  "policyVersion": "oauth-refresh-rotation-v1",
  "rawTokenStored": false
}
~~~

Đây là ví dụ **chỉ ghi nhận reuse quan sát được**, không kết luận chắc ai là attacker. `rawTokenStored=false` là mục tiêu audit; không thể tự chứng minh không có leak ở mọi log/trace khác nếu chưa kiểm tra.

## 34. Metrics: theo dõi đúng điều gì?

| Chỉ số | Mục tiêu | Cảnh báo diễn giải |
|---|---|---|
| **Rotation success rate** | Tỷ lệ refresh hợp lệ thành công | Thành công 100% không chứng minh RT được bảo vệ khỏi XSS |
| **Reuse signal count/rate** | Phát hiện token cũ xuất hiện | Race và network retry cũng là nguyên nhân |
| **Family revoke rate** | Đo impact khi reuse/security event | Tăng đột ngột có thể do SDK lỗi |
| **Unexpected reauthentication rate** | UX/availability sau rotation | Cần phân loại security vs legitimate failures |
| **Lost-response/retry incidents** | Khả năng chịu lỗi mạng | Không log token để debug |
| **Concurrent refresh collision** | Race trong client/server | Chưa chắc tấn công |
| **AT issued after grant revoke** | Vi phạm hoặc độ trễ propagation | Phải xét nguồn thời gian chính xác |
| **Residual API access after revoke** | Cửa sổ quyền còn lại | Cần đo ở Resource Server |
| **P95 revocation latency** | Thời gian đến khi target từ chối | P95 có thể che long-tail nguy hiểm |
| **Signing key validation failure** | Lỗi JWKS/`kid` sau rollover | Không luôn là compromise |
| **Client-credential expiry failures** | Rotation secret/key bị thiếu | Không biến thành lý do giữ key cũ mãi |
| **Orphan grant/family count** | Grant không owner hoặc subject không eligible | Có thể cần cleanup sau JML |
| **Device-specific revocations** | Thu hồi đúng phiên/thiết bị | Tránh quá rộng hoặc quá hẹp |
| **Auth retry storms** | Token endpoint chịu tải bất thường | Rate limit và xử lý client |
| **Audit coverage/retention** | Có nguồn bằng chứng đáng tin | Không chỉ đếm số log đã gửi |

### 34.1. Bẫy của “tỷ lệ rotation cao”

Một client phát hàng triệu lần refresh do bug vẫn có thể đạt rotation success rate cao, nhưng gây tải và tăng bề mặt rủi ro. Cần đo **số lần refresh bất thường trên mỗi session/client**, cache token đúng cách và cơ chế giới hạn tốc độ.

### 34.2. Security event không thay quyền thực tế

“Family REVOKED” là **trạng thái tại Authorization Server**. Nếu policy yêu cầu chặn API trước `exp`, phải đo **Resource Server denial/readback** riêng.

## 35. Runbook khi phát hiện reuse hoặc refresh storm

1. **Xác định phạm vi:** Family ID, client, subject, device context và loại grant.
2. **Đối chiếu trạng thái token:** RT đã USED/EXPIRED/REVOKED hay token không đúng client?
3. **Kiểm thời điểm và correlation:** Hai request đồng thời, network retry, token endpoint errors?
4. **Giữ bất biến an toàn:** Không mở lại USED token tùy tiện để chữa UX.
5. **Áp family revoke theo policy:** Nếu cần, thông báo reauthentication và lưu reason.
6. **Kiểm threat signals:** Credential leak, device compromise, token xuất hiện trong log, IP bất thường.
7. **Nếu có compromise:** Mở security incident response và đánh giá access tokens/credential liên quan.
8. **Kiểm API còn quyền:** Xác minh Resource Server đã chặn action đúng lúc.
9. **Khôi phục client:** Tránh refresh loop; hướng người dùng xác thực lại hoặc phục hồi bằng cơ chế được duyệt.
10. **Sửa nguyên nhân:** Multi-tab coordination, singleflight, token storage, network recovery, SDK version.
11. **Giám sát sau sửa:** Reuse rate, login failures, revocation latency và residual accesses.
12. **Audit:** Kết luận grounded, không tự gán malicious actor khi dữ liệu chỉ chứng minh duplicate.

### 35.1. Nếu toàn bộ người dùng cùng bị logout

Ưu tiên kiểm **thay đổi Authorization Server, SDK, cache consistency, token family logic, key rollover và client deployments**. Không tự tắt replay detection toàn hệ thống để “chữa cháy” nếu chưa đánh giá rủi ro; có thể giảm blast radius bằng rollback cấu hình ứng dụng hợp lệ và xử lý theo sự cố.

## 36. Test matrix cho token rotation

| Test case | Kết quả kỳ vọng |
|---|---|
| Refresh token ACTIVE dùng lần đầu | Phát successor mới; old chuyển USED |
| Dùng lại old token | Không mint successor; áp reuse policy |
| Hai refresh đồng thời cùng RT | Không có hai successor ACTIVE ngoài thiết kế |
| Retry sau response bị mất | Không tái dùng token cũ trái policy; có đường recovery |
| Client A dùng RT của Client B | Từ chối client binding |
| Token family bị revoke | Mọi RT trong family không còn refresh được |
| Family hết absolute lifetime | Rotation không kéo dài vượt mốc cứng |
| Grant hết inactivity lifetime | Refresh bị từ chối dù token instance chưa hiển thị expiry |
| Client chỉ có access token, không có RT | Không giả lập rotation RT |
| Mover gỡ quyền dự án A | Token mới/Resource Server không cho action A |
| Leaver trước RT/AT expiry | Quyền bị chặn theo JML policy, không chờ token tự hết |
| Logout một thiết bị | Đúng family/device được revoke theo thiết kế |
| Logout tất cả | Các family trong scope bị revoke |
| OIDC SSO session còn, RT revoked | Client đi lại auth flow đúng freshness policy |
| Browser nhiều tab gọi refresh | Singleflight/coordination giảm collision |
| Mobile app background/foreground race | Storage state nhất quán, không ghi đè RT mới |
| BFF session logout | Backend revoke grant và cookie/session đúng scope |
| Replay qua khác vùng datacenter | Atomicity/consistency không tạo hai nhánh token |
| Token mới bị nhận nhưng DB commit thất bại | Không xuất hiện successor “mồ côi” được chấp nhận |
| 401 từ API do thiếu role | Client không refresh vô hạn để “xin quyền” |
| JWKS có old/new keys | JWT cũ còn hạn được verify trong rollover bình thường |
| Bỏ old signing key quá sớm | Test phát hiện verification failure |
| Compromised signing key | Incident path xử lý nhanh hơn rollover thông thường |
| Client secret đổi nhưng AT còn hạn | Kiểm đúng khác biệt giữa credential và token lifecycle |
| Workload Client Credentials | Xin AT bằng client auth, không cần RT nếu flow không cấp |
| Revoke event gặp connector/target outage | Giữ exception và đo target readback |
| Access token bị lộ trong logs | Incident response, không dùng logs làm token store |
| Token payload/client gửi `scope=admin` | Server không mở rộng quyền ngoài grant |
| Concurrent subject state update | Leaver/security deny thắng trạng thái refresh cũ |

### 36.1. Negative test không được gây tác hại

Có thể dùng endpoint kiểm quyền, môi trường thử nghiệm, kiểm trạng thái server và request chỉ đọc được thiết kế để từ chối. Tránh kiểm `delete`/`export` trên dữ liệu production thật chỉ để chứng minh token không còn quyền. Ghi **time, token reference, resource, expected/observed decision, policy version**.

## 37. Các tình huống thực hành

### 37.1. Tình huống A — Hai tab browser cùng refresh

**Bối cảnh:** Browser mở hai tab CRM. `AT-1` hết hạn gần như đồng thời; cả hai tab dùng cùng `RT-1`. Authorization Server xử lý tab A trước, tab B trở thành reuse.

**Sai lầm:** Tắt rotation hoặc cho mọi RT đã USED refresh lại trong thời gian dài.

**Hướng xử lý:**

1. Xem token family timeline và request correlation.
2. Dùng BFF hoặc cơ chế phối hợp multi-tab phù hợp architecture.
3. Đảm bảo một token pair mới được lưu nhất quán.
4. Nếu family đã revoke theo policy, reauthenticate đúng quy trình.
5. Test điều kiện race, reload và tab ngủ lâu.
6. Theo dõi reuse false positives mà không bỏ bảo vệ.

**Bài học:** **Client concurrency là thành phần của thiết kế rotation**, không chỉ trách nhiệm Authorization Server.

### 37.2. Tình huống B — Response rotation bị mất

**Bối cảnh:** Mobile gửi `RT-8`, server tạo `RT-9` nhưng response bị mất. Mobile retry `RT-8` và bị `invalid_grant`.

**Hướng xử lý:** Phân biệt transport failure với definitive token response; không mint từ RT cũ ngoài policy. Thiết kế recovery an toàn hoặc reauthentication. Kiểm việc retry/backoff và hiển thị thông báo không làm mất dữ liệu nháp quan trọng.

**Bài học:** **Commit server và nhận response client là hai sự kiện khác nhau**.

### 37.3. Tình huống C — Attacker dùng RT trước client hợp lệ

**Bối cảnh:** Một refresh token bị lấy qua log không được bảo vệ. Attacker dùng nó để nhận successor. Client thật sau đó gửi token cũ và server phát hiện reuse.

**Hướng xử lý:**

1. Revoke family theo chính sách, chặn refresh tiếp theo.
2. Đánh giá access token hiện có và khả năng Resource Server revoke nhanh.
3. Điều tra nguồn leak/token logs, không chia sẻ raw token trong ticket.
4. Yêu cầu người dùng tái xác thực qua kênh tin cậy.
5. Ghi security event, thời gian tác động và target access thực tế.
6. Khắc phục log sanitization và secret access.

**Bài học:** Rotation **phát hiện xung đột trong family** nhưng không tự xác định người sở hữu successor là ai.

### 37.4. Tình huống D — Token còn hạn sau Leaver

**Bối cảnh:** Contractor kết thúc hợp đồng lúc 18:00. IGA revoke refresh-token family và SCIM disable user. JWT access token ký trước đó vẫn có `exp` lúc 18:45, API tiếp tục chấp nhận export.

**Hướng xử lý:** Xác định quyền phải chặn tại mốc nào; kiểm token status/authorization state tại Resource Server, điều chỉnh token TTL hoặc PEP block theo khả năng. Không tuyên bố “Leaver đã xong” chỉ từ trạng thái family REVOKED.

**Bài học:** **Refresh-token revoke không tự thu hồi access token bearer đã phát**.

### 37.5. Tình huống E — Mover giữ scope cũ trong token mới

**Bối cảnh:** An đổi Sales → Finance, nhưng Authorization Server tiếp tục dùng grant cached để phát `AT-new` có `customer.export` mỗi khi refresh token rotate.

**Hướng xử lý:** Review grant provenance, đồng bộ desired access, invalidation cache, API ABAC và quyền direct ACL. Thu hồi hoặc thu hẹp grant, kiểm API từ chối export tenant cũ.

**Bài học:** **Token mới không đồng nghĩa quyền mới chính xác**.

### 37.6. Tình huống F — Đổi client secret nhưng quên workload

**Bối cảnh:** Team rotate client secret ở IdP. Một integration chạy ban đêm vẫn dùng secret cũ và dừng khi key bị revoke.

**Hướng xử lý:** Inventory dependency, rollout credential mới, positive test client authentication và negative test secret cũ, đánh giá có cần overlap có giới hạn hay không. Không giữ secret cũ vô hạn để tránh outage.

**Bài học:** **Client credential rotation là thay trust giữa client và issuer**, không phải RT rotation.

### 37.7. Tình huống G — Signing-key rollover làm API lỗi hàng loạt

**Bối cảnh:** Authorization Server đổi `kid` và ký JWT mới bằng key mới trước khi Resource Servers cập nhật JWKS cache. API trả 401 dù user có session hợp lệ.

**Hướng xử lý:** Công bố public key mới trước, kiểm khả năng JWKS refresh, theo dõi TTL/cache, giữ old key cần thiết trong rollover bình thường. Nếu khóa cũ bị compromise, áp sự cố riêng với ưu tiên thu hồi trust.

**Bài học:** **Luân chuyển key ký JWT cần overlap có kiểm soát; không liên quan trực tiếp đến RT family**.

### 37.8. Tình huống H — Workload được cấp refresh token không cần thiết

**Bối cảnh:** Một batch job dùng Client Credentials với client secret được bảo vệ nhưng team tự tạo “refresh-token cache” dài hạn để giảm token endpoint calls.

**Hướng xử lý:** Kiểm flow/provider có phát RT hay không; nếu không, không mô phỏng. Dùng access token theo TTL, cache/reissue có kiểm soát, strong client auth, owner và rate limiting. Xem managed identity hoặc workload federation để giảm secret dài hạn.

**Bài học:** **Không đưa cơ chế token người vào NHA khi không phù hợp**.

### 37.9. Tình huống I — User logout một điện thoại nhưng tablet vẫn hoạt động

**Bối cảnh:** Người dùng có hai phiên mobile độc lập. Khi logout trên điện thoại, team định revoke mọi refresh token của subject để đơn giản, làm tablet cũng bị đăng xuất.

**Hướng xử lý:** Thiết kế family per device/session; chọn scope revoke theo yêu cầu người dùng và risk. Với account compromise hoặc “logout all devices”, việc revoke rộng có thể cần thiết và phải audit.

**Bài học:** **Family scope quyết định ảnh hưởng của revocation**.

### 37.10. Tình huống J — Cấp quyền admin bằng cách tăng `scope` lúc refresh

**Bối cảnh:** Client đang có grant `reports.read`, gửi refresh request kèm `scope=reports.read admin`. Backend token endpoint tin chuỗi `scope` do client đề nghị và cấp AT admin.

**Sai lầm:** Nhầm quyền đề nghị với quyền đã được grant.

**Hướng xử lý:** Authorization Server kiểm scope được cấp trước đây và policy hiện hành; không tăng quyền qua refresh nếu chưa qua authorization/approval tương ứng. Resource Server kiểm role và target resource.

**Bài học:** **Rotation không phải đường nâng quyền**.

### 37.11. Tình huống K — Token family bị chia nhánh ở multi-region

**Bối cảnh:** Hai region của Authorization Server cùng đọc RT hiện hành từ bản sao không nhất quán và mỗi bên phát một successor ACTIVE.

**Hướng xử lý:** Kiểm database consistency, transaction boundary, CAS/lock và thiết kế routing/quorum. Test concurrent refresh cross-region và điều kiện mất kết nối; không dùng mỗi cache TTL làm bảo đảm atomic.

**Bài học:** **One-time use phải được chứng minh dưới concurrency thật**, không chỉ chạy được ở một server.

## 38. Sai lầm thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Coi RT rotation là đổi `exp` | Không có replay detection đúng nghĩa | One-time successor và family state |
| Cấp RT mới nhưng RT cũ vẫn dùng mãi | Attacker có thể mint nhiều token | Invalid old theo policy và kiểm reuse |
| Ghi raw RT vào log | Leak credential nghiêm trọng | Dùng token reference + secret redaction |
| Reuse = chắc chắn hacker | Điều tra sai, gây false positive | Phân loại race/retry vs compromise có evidence |
| Cho retry vô hạn `invalid_grant` | Refresh storm, khóa family liên tục | Dừng loop và reauthenticate |
| Không xử lý multi-tab | Tự gây reuse | BFF, coordination, singleflight |
| Chỉ lock client, server không atomic | Có thể tạo hai successor | Server CAS/transaction |
| Rotation tự reset absolute lifetime | Grant sống vô hạn | Family hard expiry độc lập |
| Thu hồi RT là thu hồi mọi AT | Residual API access | Revocation/PEP/RS theo policy |
| Coi token mới có quyền chính xác | Overgrant sau Mover | Re-evaluate scopes/tenant/resource |
| Bỏ qua Leaver đến token hết hạn | Quyền trái policy tồn tại | Event-driven revocation và readback |
| M2M nào cũng phải có RT | Thừa credential và rủi ro | Client Credentials/managed identity phù hợp |
| Trộn client secret rotation và RT rotation | Không biết key cũ/token nào còn | Quản trị hai lifecycle riêng |
| Xóa old JWKS key ngay lập tức | JWT hợp lệ bị từ chối | Kế hoạch key rollover/cache |
| Giữ old signing key sau compromise | Trust rủi ro | Incident response riêng |
| `kid` quyết định trust | Key confusion | Pin issuer/alg/trust policy |
| Đánh dấu CLOSED khi API vẫn cho quyền | Báo cáo sai | Target effective access readback |
| Dùng một family cho mọi user/devices | Revoke quá rộng | Phân tách phù hợp scope |
| Không quản owner/expiry | Token/grant mồ côi | Inventory, reviews, JML triggers |
| Tắt reuse detection để tăng UX | Mất tín hiệu token theft | Sửa client race và recovery |

## 39. Câu hỏi tự kiểm tra

**Câu 1.** Refresh-token rotation khác việc access token hết hạn như thế nào?

**Gợi ý:** Rotation là tiêu thụ RT hiện hành và phát RT successor, old RT không còn được dùng; AT `exp` là thời hạn API chấp nhận một AT cụ thể.

**Câu 2.** RT đã USED lại xuất hiện có chứng minh request đó do attacker gửi không?

**Gợi ý:** Không; có thể do retry, mạng lỗi hoặc hai tab. Tuy nhiên đây vẫn là security signal cần chính sách bảo vệ.

**Câu 3.** Vì sao cần lưu `familyId` và `generation`?

**Gợi ý:** Để theo dõi lineage, tìm current token, phát hiện reuse và thu hồi đúng phạm vi.

**Câu 4.** Hai request refresh đồng thời cùng RT, server tạo hai RT successor ACTIVE. Lỗi gì?

**Gợi ý:** Thiếu atomicity/concurrency control, phá bảo đảm one-time use.

**Câu 5.** Server commit RT-1 → RT-2 nhưng response bị mất. Client có thể retry RT-1 thoải mái không?

**Gợi ý:** Không. Retry có thể trông như replay; cần recovery/reauth theo thiết kế bảo mật.

**Câu 6.** Family revoked có làm JWT access token cũ mất hiệu lực ngay không?

**Gợi ý:** Không nhất thiết; phụ thuộc Resource Server kiểm trạng thái và token expiry.

**Câu 7.** Một app dùng SSO qua IdP nhưng RT family bị revoke. User có nhất thiết phải nhập password ngay không?

**Gợi ý:** Không luôn; IdP có thể còn SSO session. Freshness/reauth policy quyết định.

**Câu 8.** Mover đã mất quyền Sales, nhưng token mới vẫn chứa `sales.export`. Vì sao?

**Gợi ý:** Grant/cache/policy chưa đồng bộ hoặc server không re-evaluate scope. Rotation không tự sửa quyền.

**Câu 9.** Contractor Leaver, SCIM disable user và revoke RT family. Có đủ chứng minh mọi API bị chặn không?

**Gợi ý:** Chưa; cần kiểm AT/local session/ACL/PEP/Resource Server và readback.

**Câu 10.** OAuth Client Credentials service có bắt buộc dùng refresh-token rotation không?

**Gợi ý:** Không; thường xin access token mới bằng client authentication, không nhất thiết có RT.

**Câu 11.** Đổi OAuth client secret có tự làm AT đã phát bị từ chối không?

**Gợi ý:** Không mặc định; client credential và access token có lifecycle riêng.

**Câu 12.** JWKS chứa public key cũ và mới trong rollover. Có luôn là cấu hình sai không?

**Gợi ý:** Không; overlap có thể cần để xác minh token cũ còn hạn trong luân chuyển bình thường.

**Câu 13.** `kid` của JWT có phải nguồn quyết định key nào được tin không?

**Gợi ý:** Không; nó là key identifier trong trust context. Issuer/alg/keys phải được cấu hình và xác minh đúng.

**Câu 14.** Vì sao mobile cần singleflight và secure storage?

**Gợi ý:** Để giảm refresh trùng, tránh ghi đè token successor và bảo vệ RT khỏi bị lấy cắp.

**Câu 15.** Nếu rotation success rate cao nhưng ReuseDetected cũng tăng mạnh, cần làm gì?

**Gợi ý:** Kiểm SDK race/refresh storm, lỗi backend, token theft và việc phân loại signal; không tắt bảo vệ theo phản xạ.

**Câu 16.** Kết quả nào chứng minh đã xử lý quyền tồn dư sau revoke?

**Gợi ý:** Bằng chứng Resource Server/target từ chối action thuộc phạm vi không còn hợp lệ, không chỉ dashboard Authorization Server.

## 40. Checklist thiết kế Token rotation

- [ ] **Phân loại:** Đã tách access token, refresh token, ID token, session, client secret, API key và signing key?
- [ ] **Grant/flow:** Client nào thực sự được cấp refresh token? Client Credentials có cần RT không?
- [ ] **Client binding:** RT chỉ sử dụng với đúng client/subject/grant theo policy?
- [ ] **Storage:** Token được bảo vệ; không vào log, URL, analytics hoặc source control?
- [ ] **One-time use:** RT sau khi refresh hợp lệ không được dùng lại?
- [ ] **Family:** Có parent/generation/current status và family ID nếu áp rotation?
- [ ] **Entropy:** Successor/token secret được phát đủ ngẫu nhiên và bảo vệ?
- [ ] **Atomicity:** Concurrent refresh không tạo hai successor ACTIVE ngoài policy?
- [ ] **Server invariants:** Không mint từ EXPIRED/REVOKED/USED token?
- [ ] **Client singleflight:** SDK giảm refresh đồng thời trong cùng process?
- [ ] **Multi-tab/process:** Có giải pháp coordination đúng boundary?
- [ ] **Retry:** Mất response có runbook an toàn; không retry `invalid_grant` vô hạn?
- [ ] **Reuse:** Có signal, response, family revoke và audit không log raw token?
- [ ] **Scope:** Reuse revoke đúng family/device/client/subject theo rủi ro?
- [ ] **Sender constraint:** Có đánh giá DPoP/mTLS/strong client auth khi hỗ trợ?
- [ ] **Absolute lifetime:** Rotation không kéo dài grant quá hạn cứng?
- [ ] **Inactivity:** Có quản hạn không dùng và refresh storm bất thường?
- [ ] **Access tokens:** Có issuer/audience/expiry/scope check và API policy?
- [ ] **Revocation:** Khi family revoked, có xác định cửa sổ AT còn hiệu lực?
- [ ] **OIDC/SSO:** RT family, ID token, IdP session và reauthentication freshness được phân biệt?
- [ ] **Browser:** BFF/server-managed RT hoặc bảo vệ public-client storage theo threat model?
- [ ] **Mobile:** Secure storage và recovery khi crash/đa request?
- [ ] **Workload:** Principal có owner, purpose, credential lifecycle, không giả lập human session?
- [ ] **Client secret:** Credential rotation có rollout, expiry, negative test và token impact review?
- [ ] **JWT signing keys:** JWKS rollover có overlap/cache/kid/issuer/alg rules?
- [ ] **Privileged:** PAM/PIM/JIT expiry được thực thi tại target, không chỉ timeout token?
- [ ] **Joiner:** Grant/token đúng effectiveAt và quyền ban đầu?
- [ ] **Mover:** Role cũ, scope/tenant cũ và stale claims được xử lý?
- [ ] **Leaver:** Không chờ RT/AT hết hạn nếu policy yêu cầu chặn theo sự kiện?
- [ ] **SCIM:** Không coi user disable là tự động revoke mọi token/session?
- [ ] **RBAC/ABAC:** Resource Server kiểm action/resource/tenant hiện hành?
- [ ] **Audit:** Có event rotation, reuse, family revoke, token issuance và verification?
- [ ] **Monitoring:** Theo dõi reuse rate, auth errors, refresh storms, revoke latency?
- [ ] **Concurrency test:** Có chạy test cross-tab, cross-region, retry và lost response?
- [ ] **Risk response:** Phân biệt benign race và compromise với bằng chứng?
- [ ] **Exceptions:** Đường quyền chưa thu hồi có owner, risk, deadline và biện pháp bù trừ?
- [ ] **Readback:** Đã kiểm quyền hiệu dụng sau grant revoke, kể cả negative tests an toàn?
- [ ] **Regrant:** Có ngăn sync/automation tái cấp lại quyền đã thu hồi?
- [ ] **Privacy:** Không giữ raw token/secret trong incident evidence hoặc analytics?
- [ ] **Mục tiêu cuối:** Token rotation vừa bảo vệ refresh grant, vừa phối hợp IAM để **không giữ quyền ngoài căn cứ**?

## 41. Kết luận

**Token rotation** là một kiểm soát quan trọng trong vòng đời token/credential, đặc biệt với **OAuth refresh token rotation**: token hiện hành được dùng để phát token kế tiếp, token cũ không còn được phép dùng lại, và hệ thống có thể phát hiện **reuse/replay** qua **token family**. Để làm được điều đó an toàn, Authorization Server cần **state có độ tin cậy, atomic update, binding đúng client/grant, expiry và policy xử lý reuse**; client cần **lưu token an toàn, giảm refresh đồng thời và xử lý lỗi mạng**.

**Không đánh đồng refresh-token rotation với access-token expiration, API key/client secret rotation hoặc JWT signing-key rollover.** Mỗi cơ chế bảo vệ một trust boundary khác nhau. Rotation có thể phát hiện dấu hiệu token bị lộ, nhưng **không tự nhận diện attacker, không tự thay đổi RBAC/ABAC, không luôn revoke JWT access token đã phát và không thay thế xác thực lại khi rủi ro yêu cầu**.

Trong vòng đời **Joiner–Mover–Leaver**, Token rotation phải gắn với **eligibility, authorization grant, session, IdP/SSO, SCIM, PAM/PIM, service/workload identity, kiểm toán và Resource Server**. Khi quyền đã hết căn cứ do Mover/Leaver hoặc security event, **revoke đúng token/grant/session và kiểm chứng hành động tại target bị từ chối theo chính sách** quan trọng hơn việc token chỉ “được đổi mới” thành công.

**Một hệ thống token rotation đạt yêu cầu không chỉ phát RT mới sau mỗi lần refresh; nó phải phát hiện dùng lại, giới hạn lạm dụng, phục hồi đúng cho client hợp lệ và chứng minh rằng những quyền không còn được phép đã thực sự bị chặn.**
