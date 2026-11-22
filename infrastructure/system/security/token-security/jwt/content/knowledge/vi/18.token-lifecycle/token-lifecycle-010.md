# Phối hợp kiểm tra trạng thái tập trung với JWT tự chứa

> **Module:** SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)  
> **Chương:** Vòng đời token  
> **Phạm vi:** Kết hợp xác minh JWT tại chỗ với trạng thái thu hồi/phiên tập trung ở mức giao thức và kiến trúc hệ thống; không phụ thuộc Java, Spring hay framework cụ thể.

JWT thường được gọi là token tự chứa vì resource server có thể đọc claims và xác minh chữ ký bằng khóa công khai mà không cần hỏi authorization server trong mỗi request. Cách này giảm phụ thuộc mạng và giúp nhiều API xác minh độc lập. Tuy nhiên, token đã ký vẫn có thể cần bị vô hiệu hóa trước thời điểm **exp**: người dùng đăng xuất, tài khoản bị khóa, refresh token bị tái sử dụng, quyền bị thu hồi hoặc khóa ký bị xâm phạm.

Nếu mọi API chỉ kiểm tra chữ ký và thời hạn, token bị thu hồi có thể tiếp tục được chấp nhận đến khi hết hạn. Nếu mọi request đều gọi một dịch vụ trạng thái tập trung, hệ thống lại phụ thuộc vào độ sẵn sàng, độ trễ và tính nhất quán của dịch vụ đó.

Giải pháp thường dùng là **mô hình lai (hybrid)**: resource server tự xác minh chữ ký, issuer, audience, token type, thời hạn và quyền cơ bản; sau đó kiểm tra thêm trạng thái tập trung ở mức cần thiết theo rủi ro. Trạng thái tập trung có thể đại diện cho token cụ thể, session, grant, tài khoản hoặc phiên bản quyền. Hợp đồng cần xác định rõ dữ liệu nào là nguồn quyết định, độ trễ thu hồi tối đa, cache và cách xử lý khi dịch vụ trạng thái không khả dụng.

## 1. JWT tự chứa và giới hạn của xác minh offline

### 1.1. Xác minh offline có thể kiểm tra điều gì?

Với một JWS JWT, resource server có thể thực hiện tại chỗ:

- Kiểm tra cấu trúc và giới hạn đầu vào.
- Chọn khóa từ nguồn tin cậy đã gắn với issuer.
- Xác minh chữ ký bằng thuật toán nằm trong allowlist.
- Kiểm tra **iss**, **aud**, token type/profile và claims bắt buộc.
- Kiểm tra **exp**, **nbf**, **iat**, lifetime và các giới hạn thời gian.
- Đánh giá scope/permission có trong token theo policy đã cấu hình.

Các bước này không cần truy vấn trạng thái của từng token nếu hệ thống chỉ dựa vào dữ liệu đã ký và cấu hình cục bộ.

### 1.2. Điều gì không thể biết chỉ từ chữ ký?

Chữ ký hợp lệ chứng minh dữ liệu được ký bằng khóa tương ứng và chưa bị thay đổi kể từ lúc ký, theo giả định khóa còn an toàn. Nó không cho biết:

- Người dùng vừa đăng xuất hay session đã bị quản trị viên thu hồi.
- Refresh token hoặc grant đã bị thu hồi sau khi access token được phát hành.
- Tài khoản vừa bị khóa hoặc bị đánh dấu rủi ro.
- Quyền truy cập vừa bị thay đổi.
- Token một lần đã được sử dụng ở request khác.
- Một giao dịch đã bị hủy hoặc đã hoàn tất.
- Một token cụ thể đã bị đưa vào denylist.

Các sự kiện trên xảy ra **sau thời điểm phát hành** và không thể sửa payload đã ký. Nếu cần phản ứng trước khi **exp**, resource server phải nhận thông tin trạng thái mới từ một nguồn có thẩm quyền.

### 1.3. Tự chứa không đồng nghĩa hoàn toàn stateless

Một hệ thống vẫn có thể dùng JWT tự chứa nhưng tra cứu thêm:

- Denylist theo **jti**.
- Trạng thái session hoặc grant.
- Trạng thái tài khoản.
- Phiên bản quyền hoặc phiên bản thông tin xác thực.
- Kết quả introspection.

JWT vẫn tự chứa các claims cần để xác minh và định tuyến; trạng thái tập trung bổ sung thông tin thay đổi theo thời gian. Khi có tra cứu này, hệ thống không còn stateless tuyệt đối ở bước authorization, nhưng có thể đạt được khả năng thu hồi nhanh hơn.

## 2. Những loại trạng thái có thể kiểm tra tập trung

Không nên lưu mọi thứ vào một bảng denylist duy nhất. Trước tiên cần xác định đối tượng nào có thể bị vô hiệu hóa và phạm vi ảnh hưởng mong muốn.

| Đối tượng trạng thái | Khóa tra cứu thường dùng | Phạm vi thu hồi | Ví dụ |
|---|---|---|---|
| Token cụ thể | **iss + jti** hoặc token identifier đã chuẩn hóa | Một token | Một access token bị lộ |
| Session | **sid** hoặc session ID phía server | Mọi token gắn với session | Người dùng đăng xuất một thiết bị |
| Grant/authorization | Grant ID hoặc refresh-token family ID | Các token phát sinh từ một lần cấp quyền | Người dùng thu hồi quyền của ứng dụng |
| Tài khoản/subject | **iss + sub** hoặc principal ID nội bộ | Nhiều session/token của một tài khoản | Tài khoản bị khóa |
| Phiên bản thông tin xác thực | Subject ID + credential/authentication version | Token được phát hành trước phiên bản hiện tại | Đổi mật khẩu hoặc thu hồi mọi phiên |
| Phiên bản quyền | Subject/client/tenant + policy version | Token có quyền cũ | Role hoặc tenant membership thay đổi |
| Giao dịch/nghiệp vụ | Transaction ID hoặc request ID | Một hành động nghiệp vụ | Reset password hoặc phê duyệt giao dịch đã dùng |

Các trường **sid**, grant ID, credential version hoặc authorization version thường là claim riêng hoặc dữ liệu liên kết phía server; không phải mọi JWT đều có sẵn. Hợp đồng phải định nghĩa tên, kiểu, issuer, tính bắt buộc và cách kiểm tra nếu sử dụng.

### 2.1. Thu hồi token cụ thể bằng jti

Claim **jti** là JWT ID. Nếu issuer phát hành **jti** duy nhất trong phạm vi issuer và verifier kiểm tra trạng thái theo cặp **iss + jti**, hệ thống có thể chặn một token mà không thu hồi các token khác của cùng user.

Ví dụ trạng thái:

~~~json
{
  "issuer": "https://id.example.com",
  "jti": "access-7f19a2",
  "status": "revoked",
  "reason": "suspected_token_theft",
  "revoked_at": "2026-11-16T12:00:00Z",
  "expires_at": "2026-11-16T12:10:00Z"
}
~~~

Đây là record trạng thái minh họa, không phải JWT claim hay schema RFC. Không lưu raw bearer token nếu chỉ cần một định danh đã xác minh để tra cứu.

Nếu token không có **jti**, hoặc issuer không bảo đảm tính duy nhất, không thể dựa vào một chuỗi ngẫu nhiên không có hợp đồng để thu hồi chính xác. Có thể cần bổ sung jti trong profile hoặc thu hồi theo session/grant.

### 2.2. Thu hồi theo session

Một access token có thể chứa claim **sid** hoặc session reference riêng. Verifier tra cứu trạng thái session để xác định session còn hoạt động không.

Phù hợp khi:

- Người dùng đăng xuất một thiết bị.
- Quản trị viên chấm dứt một phiên cụ thể.
- Có dấu hiệu session bị chiếm đoạt.
- Muốn thu hồi tất cả access token được cấp trong cùng session.

Nếu người dùng có nhiều thiết bị, thu hồi theo session giúp không cần đăng xuất tất cả thiết bị. Ngược lại, logout toàn bộ tài khoản có thể thu hồi mọi session hoặc tăng credential version theo policy.

### 2.3. Thu hồi theo grant hoặc refresh-token family

Refresh token đại diện cho quyền tiếp tục xin access token. Khi grant bị thu hồi hoặc phát hiện refresh-token reuse, authorization server cần chặn việc phát hành token mới từ grant/family đó.

Tuy nhiên, access token đã phát hành trước đó có thể vẫn hợp lệ nếu resource server chỉ xác minh offline. Muốn chặn ngay, cần:

- Liên kết access token với grant/session ID và kiểm tra trạng thái; hoặc
- Thu hồi từng access token đã phát hành; hoặc
- Dùng introspection/central status có thẩm quyền; hoặc
- Giữ access token có lifetime đủ ngắn để giới hạn cửa sổ rủi ro.

Không giả định thu hồi refresh token tự động làm mọi access token đã cấp mất hiệu lực.

### 2.4. Thu hồi theo subject, tài khoản hoặc phiên bản

Nếu cần vô hiệu hóa hàng loạt token của một người dùng, hệ thống có thể duy trì credential version hoặc token version ở phía server. Token mang phiên bản tại thời điểm phát hành; verifier so sánh với phiên bản hiện tại.

Ví dụ claim riêng:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-42",
  "credential_version": 12,
  "exp": 1794800600
}
~~~

Nếu phiên bản hiện tại của user-42 tăng lên 13, token mang phiên bản 12 bị từ chối. Đây là mô hình ứng dụng, không phải registered claim chuẩn. Cần định nghĩa rõ thời điểm tăng version, phạm vi ảnh hưởng, cache và cách xử lý khi không tìm thấy trạng thái.

## 3. Các mô hình kết hợp JWT với trạng thái tập trung

### 3.1. Xác minh hoàn toàn offline

Resource server xác minh chữ ký và claims từ token, không tra cứu trạng thái từng request.

Ưu điểm:

- Độ trễ thấp và ít phụ thuộc mạng.
- Resource server có thể hoạt động khi authorization server tạm thời không truy cập được.
- Dễ mở rộng số lượng verifier.

Giới hạn:

- Token bị thu hồi có thể tiếp tục được chấp nhận đến **exp**.
- Thay đổi trạng thái tài khoản/quyền không tự lan tới token đã phát hành.
- Muốn giảm cửa sổ rủi ro phải dùng lifetime ngắn hoặc cơ chế chặn bổ sung.

Phù hợp với token ngắn hạn, rủi ro thấp hơn hoặc hệ thống chấp nhận một khoảng trễ thu hồi đã được xác định.

### 3.2. Introspection mỗi request

Resource server gọi authorization server hoặc dịch vụ introspection để hỏi token còn active không. RFC 7662 định nghĩa OAuth 2.0 Token Introspection; phản hồi có trường **active** và có thể chứa thêm metadata tùy authorization server.

Ưu điểm:

- Authorization server có thể áp dụng trạng thái mới trước khi token hết hạn.
- Resource server không cần tự duy trì toàn bộ trạng thái grant/session.
- Một nguồn quyết định tập trung giúp đồng nhất policy giữa nhiều API.

Giới hạn:

- Mỗi request thêm một lượt gọi mạng và độ trễ.
- Introspection service trở thành dependency quan trọng.
- Cần xác thực resource server, bảo vệ endpoint, kiểm soát tải và xử lý lỗi.
- Nếu dịch vụ introspection bị gián đoạn, hành vi fail-open/fail-closed ảnh hưởng trực tiếp availability.

Không phải mọi JWT đều bắt buộc phải introspect. Đây là lựa chọn kiến trúc theo mức độ cần thu hồi và khả năng vận hành.

### 3.3. JWT offline + denylist theo jti

Verifier xác minh chữ ký/claims tại chỗ, sau đó tra cứu xem **iss + jti** có nằm trong danh sách thu hồi không.

Ưu điểm:

- Chỉ lưu các token bị thu hồi thay vì trạng thái mọi token.
- Có thể chặn token cụ thể.
- Có thể dùng cache cục bộ và sự kiện invalidation.

Giới hạn:

- Cần jti duy nhất và định nghĩa namespace.
- Denylist phải được phân phối nhanh tới mọi verifier.
- Mỗi request có thể cần tra cứu hoặc cache.
- Nếu attacker tạo token giả bằng signing key bị lộ, denylist các jti đã biết không bao phủ token giả mới; phải chặn key identity hoặc issuer theo incident policy.

### 3.4. JWT offline + session/grant/version lookup

Verifier kiểm tra chữ ký rồi tra cứu session, grant, trạng thái subject hoặc version. Mô hình này phù hợp khi một thay đổi cần ảnh hưởng đến nhiều token cùng lúc.

Ví dụ:

- Logout một thiết bị: đánh dấu session ID đã revoked.
- Khóa tài khoản: đánh dấu subject inactive hoặc tăng credential version.
- Thu hồi quyền của client: đánh dấu grant revoked.
- Thay đổi quyền tenant: tăng authorization version cho tenant/principal.

Nhược điểm là trạng thái tra cứu có thể trở thành điểm nóng; cần cache, partitioning, event propagation và chính sách nhất quán.

### 3.5. Mô hình lai theo mức rủi ro

Không nhất thiết mọi endpoint đều tra cứu cùng một loại trạng thái:

| Nhóm request | Xác minh cơ bản | Trạng thái bổ sung |
|---|---|---|
| Đọc dữ liệu thông thường | Chữ ký, issuer, audience, exp, scope | Có thể dùng cache trạng thái ngắn hoặc offline nếu risk policy cho phép |
| Thay đổi dữ liệu quan trọng | Xác minh JWT đầy đủ | Session/grant/revocation check mới |
| Thanh toán hoặc hành động nhạy cảm | Xác minh JWT và quyền tài nguyên | Trạng thái trực tuyến, transaction state và step-up khi cần |
| Token reset/verification một lần | Xác minh profile, thời hạn | Tra cứu trạng thái đã dùng/chưa dùng bắt buộc |
| Token sau sự cố khóa hoặc account compromise | Xác minh JWT | Denylist/key block/subject status có ưu tiên cao |

Phân loại phải được ghi trong contract và áp dụng nhất quán. Không bỏ qua kiểm tra chữ ký/issuer/audience ở endpoint “ít rủi ro”.

## 4. Pipeline xác minh kết hợp

Một pipeline điển hình:

~~~mermaid
flowchart TD
    A[Request mang JWT] --> B[Chọn contract theo endpoint]
    B --> C[Parse giới hạn và xác minh chữ ký]
    C --> D{Chữ ký, issuer, audience, type và time hợp lệ?}
    D -->|Không| X[Từ chối]
    D -->|Có| E[Đọc jti, sid, grant hoặc version đã xác minh]
    E --> F{Contract yêu cầu central status?}
    F -->|Không| J[Kiểm tra scope và quyền tài nguyên]
    F -->|Có| G[Tra cứu introspection hoặc status store]
    G --> H{Active và chưa bị thu hồi?}
    H -->|Không| X
    H -->|Có| J
    J --> K{Được phép?}
    K -->|Không| X
    K -->|Có| L[Chấp nhận request]
~~~

Thứ tự chính xác có thể tối ưu theo chi phí, nhưng không được dùng claims chưa xác minh để cấp quyền hoặc truy cập status store tùy ý. Chỉ sau khi xác minh mật mã và xác định contract tin cậy mới sử dụng issuer, jti, sid hoặc grant ID từ token làm khóa tra cứu.

### 4.1. Pseudocode

~~~text
authorizeRequest(endpoint, jwt, request):
    contract = trustedContracts.forEndpoint(endpoint)
    reject nếu contract không tồn tại

    claims = verifyJwtCompletely(jwt, contract)
    reject nếu chữ ký, iss, aud, type, claims hoặc time không hợp lệ

    if contract.statusPolicy.requiresCentralCheck:
        status = statusService.lookup(
            issuer = verified claims.iss,
            tokenId = verified claims.jti,
            sessionId = verified claims.sid,
            grantId = verified claims.grant_id,
            subject = verified claims.sub
        )
        reject nếu trạng thái không active theo policy

    reject nếu scope hoặc quyền tài nguyên không đủ
    ACCEPT
~~~

Các trường **sid** và **grant_id** chỉ được truyền nếu contract định nghĩa chúng. Không cần gửi mọi định danh trong mọi lần tra cứu; chỉ gửi khóa trạng thái cần thiết, giảm dữ liệu cá nhân và tải.

## 5. Thiết kế status store và trạng thái token

### 5.1. Mô hình dữ liệu tối thiểu

Một record trạng thái có thể gồm:

| Trường | Ý nghĩa |
|---|---|
| issuer_id | Định danh issuer đã được chuẩn hóa theo trust configuration |
| token_id / jti | JWT ID nếu thu hồi theo token |
| session_id | Session liên quan nếu có |
| grant_id | Grant hoặc refresh-token family nếu có |
| subject_id | Principal liên quan, theo namespace issuer |
| status | active, revoked, expired hoặc consumed theo mô hình |
| reason | Mã lý do nội bộ |
| created_at | Thời điểm tạo record |
| revoked_at | Thời điểm thu hồi |
| expires_at | Thời điểm record có thể được dọn |
| version | Phiên bản record hoặc trạng thái |

Không nhất thiết một bảng phải có tất cả trường. Tách token status, session, grant và subject status theo access pattern có thể hiệu quả hơn. Không lưu nguyên JWT hoặc secret nếu chỉ cần định danh và metadata tối thiểu.

### 5.2. Trạng thái và chuyển trạng thái

Một mô hình đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> Active
    Active --> Revoked: logout / admin revoke / compromise
    Active --> Consumed: one-time token used
    Active --> Expired: exp reached
    Revoked --> [*]
    Consumed --> [*]
    Expired --> [*]
~~~

Không phải mọi token đều cần lưu trạng thái **active**. Với denylist, hệ thống chỉ lưu trạng thái revoked/consumed; nếu không có record, token có thể tiếp tục theo các kiểm tra còn lại. Với allowlist/session store, token/session phải có record active mới được chấp nhận. Hai mô hình có hành vi khác nhau khi dữ liệu bị thiếu hoặc kho trạng thái mất kết nối.

### 5.3. Denylist và allowlist

| Mô hình | Cách quyết định | Ưu điểm | Rủi ro/chi phí |
|---|---|---|---|
| Denylist | Không có record revoked thì tiếp tục nếu các kiểm tra khác đạt | Ít record khi rất ít token bị thu hồi | Mất kết nối có thể không thấy revoke mới; cần đồng bộ deny events |
| Allowlist | Chỉ token/session có record active mới được chấp nhận | Trạng thái rõ, dễ vô hiệu hóa | Cần ghi trạng thái mọi token/session; phụ thuộc kho dữ liệu |
| Version check | So phiên bản token với phiên bản hiện tại | Thu hồi hàng loạt hiệu quả | Lookup subject/session; cần quản lý version và cache |
| Introspection | Authorization server trả trạng thái active | Central policy | Thêm dependency và độ trễ |

Chọn mô hình theo tần suất thu hồi, số lượng token, độ trễ cho phép, yêu cầu hoạt động khi mất kết nối và khả năng lưu trạng thái. Không mặc định denylist luôn nhẹ hơn; với số lượng revoke lớn hoặc yêu cầu fail-closed, allowlist/version có thể hợp lý hơn.

### 5.4. TTL và dọn dữ liệu

Record denylist theo jti chỉ cần tồn tại đến khi token chắc chắn không còn được chấp nhận. TTL nên dựa trên:

- **exp** đã xác minh.
- Leeway/clock skew được contract cho phép.
- Độ trễ đồng bộ giữa các verifier.
- Thời gian cache tối đa.
- Quy tắc lưu giữ phục vụ điều tra nếu có.

Không xóa record đúng tại exp nếu verifier còn được phép chấp nhận token trong một khoảng leeway sau exp. Ngược lại, không giữ dữ liệu trạng thái vô thời hạn nếu không có mục đích pháp lý/vận hành rõ.

## 6. Cache và tính nhất quán

### 6.1. Vì sao cần cache?

Tra cứu trạng thái tập trung trên mọi request có thể tạo tải lớn và tăng độ trễ. Cache cục bộ hoặc distributed cache giúp:

- Giảm số lượt gọi introspection/status service.
- Giảm độ trễ ở resource server.
- Giảm tải cho kho dữ liệu trạng thái.
- Duy trì khả năng phục vụ trong một số lỗi mạng ngắn theo policy.

Nhưng cache làm phát sinh một cửa sổ mà verifier có thể chưa nhìn thấy sự kiện thu hồi mới.

### 6.2. Giới hạn TTL cache hợp lệ

Cache kết quả active không được sống lâu hơn giới hạn nhỏ nhất trong các yếu tố liên quan:

\[
TTL_{active} \leq \min(
TTL_{policy},
exp-now,
revocation\_latency\_budget
)
\]

Đây là mô hình thiết kế. Nếu còn session/grant/version check, TTL cũng phải phù hợp với độ mới tối đa được phép của các trạng thái đó. Với token nhạy cảm, có thể không cache active status hoặc dùng TTL rất ngắn.

Ví dụ: contract yêu cầu thu hồi có hiệu lực tối đa trong 15 giây. Cache active 60 giây vi phạm mục tiêu dù token còn hạn 10 phút. Cache TTL phải được đặt sao cho tổng thời gian phát hiện, phân phối sự kiện và cache invalidation không vượt ngân sách 15 giây.

### 6.3. Cache trạng thái revoked

Trạng thái revoked/consumed có thể cache lâu hơn vì trạng thái này thường đơn điệu: token đã bị thu hồi thì không tự trở lại active. Tuy nhiên:

- Cần xác định TTL và lưu giữ đến khi token hết hạn + leeway.
- Không cho một cập nhật cũ ghi đè trạng thái revoked mới.
- Chống race condition khi nhiều node xử lý đồng thời.
- Với trạng thái one-time token, thao tác consume phải atomic để chỉ một request thành công.

### 6.4. Invalidation chủ động

Thay vì chờ TTL hết hạn, status service có thể phát sự kiện tới các verifier/cache:

~~~mermaid
flowchart LR
    A[Logout / revoke / account disable] --> B[Central status store]
    B --> C[Publish revocation event]
    C --> D[API Gateway]
    C --> E[Orders API]
    C --> F[Inventory API]
    D --> G[Invalidate active cache]
    E --> H[Invalidate active cache]
    F --> I[Invalidate active cache]
~~~

Sự kiện nên chứa định danh tối thiểu như issuer + jti, session ID, grant ID hoặc subject/version. Không gửi raw JWT trong event. Consumer cần xử lý idempotent, retry và duplicate event.

### 6.5. Eventual consistency và ngân sách thu hồi

Trong hệ thống nhiều region, một event có thể đến trễ hoặc thất lạc tạm thời. Hợp đồng nên định nghĩa:

- Mục tiêu thời gian từ revoke tới khi mọi verifier chặn.
- Cơ chế retry, dead-letter và replay event.
- Cách phát hiện consumer lag.
- Cơ chế reconcile định kỳ giữa cache và nguồn trạng thái.
- Hành vi khi event stream hoặc status store mất kết nối.

Nếu yêu cầu “thu hồi tức thời” là bắt buộc, cần định nghĩa chính xác tức thời ở mức nào. Trong hệ thống phân tán, thường phải diễn đạt bằng một ngân sách thời gian và điều kiện kiểm chứng, không chỉ một từ chung chung.

## 7. Introspection và endpoint trạng thái

### 7.1. Introspection theo RFC 7662

RFC 7662 định nghĩa endpoint để resource server hỏi authorization server về trạng thái token. Phản hồi có trường **active**; các trường khác có thể bao gồm scope, client, subject, audience, issuer và thời gian tùy authorization server.

Resource server cần:

- Xác thực với introspection endpoint theo cơ chế đã cấu hình.
- Gửi token qua kênh bảo mật; không đặt token trong URL.
- Chỉ gọi endpoint thuộc authorization server tin cậy.
- Xác minh phản hồi đến từ endpoint đó và diễn giải **active** theo profile.
- Không tự coi thiếu trường **active** là active.
- Không log raw token hoặc phản hồi chứa dữ liệu nhạy cảm không cần thiết.

### 7.2. Introspection JWT không thay thế mọi bước

Nếu hệ thống dùng JWT access token nhưng gọi introspection, có thể để authorization server là nguồn quyết định trạng thái tập trung. Resource server vẫn phải tuân thủ contract về issuer, audience, loại token và cách tin cậy introspection response. Tùy profile/kiến trúc, resource server có thể xác minh chữ ký cục bộ trước hoặc dựa vào introspection response đã được xác thực; lựa chọn phải được ghi rõ.

Không trộn hai mô hình một cách mơ hồ, ví dụ vừa coi chữ ký local là đủ vừa bỏ qua trạng thái inactive từ introspection. Nếu introspection trả **active=false**, token phải bị từ chối theo hợp đồng.

### 7.3. Bảo vệ endpoint trạng thái

Endpoint introspection/status là thành phần nhạy cảm:

- Chỉ resource server được ủy quyền mới được gọi.
- Dùng TLS và cơ chế xác thực client phù hợp.
- Giới hạn tốc độ, kích thước request và thời gian xử lý.
- Không cho endpoint trở thành oracle tiết lộ thông tin tài khoản cho caller bất kỳ.
- Không phản hồi quá nhiều dữ liệu principal nếu verifier chỉ cần active/inactive.
- Theo dõi lỗi, latency, request volume và truy cập bất thường.

## 8. Chính sách khi status service không khả dụng

### 8.1. Fail-closed

Nếu contract yêu cầu kiểm tra trạng thái tập trung và không thể xác minh trạng thái, verifier từ chối request hoặc trả lỗi dịch vụ theo giao thức. Phù hợp với:

- Thanh toán, chuyển tiền hoặc thay đổi thông tin bảo mật.
- Password reset/email verification một lần.
- Token có nguy cơ bị thu hồi cao.
- Sự cố khóa hoặc tài khoản đang trong quá trình containment.

Ưu điểm là không chấp nhận token khi không thể biết nó đã bị thu hồi chưa. Đổi lại, availability phụ thuộc status service.

### 8.2. Fail-open có điều kiện

Một số API ít rủi ro có thể tiếp tục dùng kết quả active đã cache trong một khoảng rất ngắn khi status service gặp lỗi. Chỉ áp dụng nếu:

- Contract cho phép rõ.
- Cache được tạo từ nguồn tin cậy và chưa vượt TTL.
- JWT vẫn hợp lệ về chữ ký, issuer, audience, token type và thời gian.
- Không có denylist/key block khẩn cấp mới hơn cache.
- Hành động được phép trong chế độ degraded được giới hạn.
- Có cảnh báo và giới hạn thời gian degraded.

Fail-open không được dùng để bỏ qua chữ ký, audience, token type hoặc kiểm tra thuật toán. Nếu có tín hiệu compromise khẩn cấp, ưu tiên denylist/key block mới phải thắng cache active cũ.

### 8.3. Ma trận quyết định

| Tình huống | Chính sách thường phù hợp | Lý do |
|---|---|---|
| Status service lỗi, không có cache hợp lệ | Fail-closed nếu central check là bắt buộc | Không biết trạng thái token |
| Status service lỗi, cache active còn trong TTL và endpoint rủi ro thấp | Có thể degraded theo contract | Cân bằng availability và độ trễ thu hồi |
| Có key compromise hoặc emergency revoke event | Fail-closed cho key/subject bị ảnh hưởng | Cache active cũ không còn đáng tin |
| Token one-time cần atomic consume nhưng store lỗi | Fail-closed | Không thể bảo đảm chống replay |
| Chỉ một dependency phụ trợ không ảnh hưởng quyết định trạng thái | Tiếp tục nếu contract cho phép | Không biến lỗi không liên quan thành từ chối toàn bộ |

Không có một chính sách fail-open/closed duy nhất cho mọi endpoint. Phải phân loại theo rủi ro, nhưng không được để từng service tự chọn hành vi ngoài contract.

## 9. Thu hồi và sự kiện vòng đời

### 9.1. Logout một session

Một luồng logout có thể:

1. Xác định session từ cookie/session context hoặc claim đã xác minh.
2. Đánh dấu session revoked trong nguồn trạng thái có thẩm quyền.
3. Phát sự kiện invalidation tới verifier/cache.
4. Thu hồi refresh token/grant gắn với session nếu policy yêu cầu.
5. Xóa cookie hoặc token ở client.
6. Ghi audit event mà không ghi raw token.

Nếu chỉ xóa token khỏi localStorage hoặc sessionStorage, token đã sao chép vẫn có thể được sử dụng.

### 9.2. Khóa tài khoản hoặc thay đổi thông tin xác thực

Khi tài khoản bị khóa hoặc mật khẩu bị thay đổi:

- Đánh dấu subject inactive hoặc tăng credential version theo policy.
- Thu hồi session/refresh grant cần thiết.
- Phát sự kiện tới các verifier đang cache trạng thái subject.
- Xác định token nào cần bị từ chối ngay và token nào được phép tồn tại tới exp.
- Không giả định thay mật khẩu tự động vô hiệu hóa mọi JWT offline.

### 9.3. Thay đổi quyền hoặc tenant membership

Nếu scope/role trong JWT là snapshot tại thời điểm phát hành, thay đổi quyền phía server không tự sửa token đã phát hành.

Có thể chọn:

- Chấp nhận quyền cũ tới exp với access token ngắn hạn.
- Tra cứu authorization version/tenant membership cho request nhạy cảm.
- Thu hồi session hoặc grant khi thay đổi đủ nghiêm trọng.
- Dùng introspection để authorization server trả trạng thái hiện hành.

Quyết định phải tính cả tính nhất quán và trải nghiệm người dùng. Không phải mọi thay đổi role đều cần thu hồi mọi token ngay, nhưng phải ghi rõ độ trễ chấp nhận được.

### 9.4. Token một lần

Với password reset, email verification hoặc transaction token, kiểm tra trạng thái phải gắn với thao tác consume nguyên tử:

~~~text
consumeOneTimeToken(issuer, jti):
    begin atomic operation
    record = load token status
    reject nếu record không active
    reject nếu token expired
    mark record consumed
    commit
    ACCEPT
~~~

Nếu hai request đồng thời cùng dùng token, chỉ một request được phép chuyển active → consumed thành công. Không thực hiện kiểu “đọc active rồi cập nhật consumed” tách rời mà không có transaction/conditional update, vì cả hai request có thể cùng vượt qua.

## 10. Multi-region và đồng bộ trạng thái

### 10.1. Chọn nguồn sự thật

Hệ thống nhiều region cần chỉ rõ:

- Status store nào là authoritative.
- Region nào có quyền ghi revoke.
- Cách xử lý khi mất kết nối giữa các region.
- Thứ tự và version của sự kiện.
- Cách reconcile khi cache hoặc replica lệch.
- Region nào được phép chấp nhận cache cũ trong degraded mode.

Không để mỗi region tự ghi trạng thái độc lập mà không có quy tắc hợp nhất. Một revoke event cũ không được ghi đè một trạng thái mới hơn.

### 10.2. Event version và idempotency

Mỗi sự kiện có thể mang:

- Event ID duy nhất.
- Aggregate key (token/session/grant/subject).
- Version tăng dần.
- Event type: revoked, consumed, reactivated nếu được phép.
- Thời điểm tạo và nguồn phát.

Consumer cần xử lý duplicate event an toàn. Trạng thái revoked/consumed thường không nên chuyển ngược về active; nếu cần khôi phục session, tạo session/token mới thay vì tái kích hoạt credential cũ.

### 10.3. Outbox và retry

Nếu ứng dụng cập nhật database rồi publish event ở hai thao tác độc lập, có thể xảy ra trạng thái đã revoke nhưng event không được gửi. Mô hình transactional outbox hoặc cơ chế tương đương giúp ghi thay đổi trạng thái và sự kiện trong cùng transaction, sau đó phát lại an toàn.

Ngoài event-driven invalidation, cần một cơ chế đối soát định kỳ để phát hiện consumer bị dừng, message bị mất hoặc cache không cập nhật.

## 11. Hiệu năng, quyền riêng tư và giới hạn dữ liệu

### 11.1. Giảm chi phí tra cứu

- Chỉ kiểm tra trạng thái tập trung ở profile/endpoint cần thiết.
- Dùng khóa tra cứu có index như issuer+jti, session ID hoặc subject ID.
- Cache theo TTL gắn với ngân sách thu hồi.
- Dùng batch lookup khi xử lý nhiều token trong một tác vụ nếu semantics cho phép.
- Tránh truy vấn nhiều bảng không cần thiết cho mỗi request.
- Theo dõi cache hit, miss, stale, invalidation lag và status service latency.

### 11.2. Giảm dữ liệu cá nhân

Status service không cần nhận toàn bộ JWT nếu chỉ cần tra cứu trạng thái. Chỉ truyền định danh tối thiểu đã xác minh. Log không nên lưu:

- Raw access/refresh token.
- Toàn bộ payload chứa dữ liệu cá nhân.
- Secret hoặc private key.
- Dữ liệu principal không cần cho audit.

Nếu lưu jti/session ID, áp dụng kiểm soát truy cập, thời hạn lưu giữ và chính sách bảo vệ dữ liệu phù hợp.

### 11.3. Không biến status endpoint thành nguồn tin không giới hạn

Status/introspection service phải kiểm tra caller. Nếu bất kỳ client nào cũng có thể hỏi trạng thái token tùy ý, endpoint có thể bị lạm dụng để dò token hoặc suy ra hoạt động tài khoản. Giới hạn caller theo resource server/client registration và chỉ trả dữ liệu cần thiết.

## 12. Ví dụ chính sách hybrid

### 12.1. Ví dụ contract cho access token

~~~yaml
token_validation:
  profile: oauth2-jwt-access
  issuer: "https://id.example.com"
  audience: "https://api.orders.example.com"
  verify_signature: required
  allowed_algorithms:
    - PS256
  required_claims:
    - iss
    - sub
    - aud
    - exp
    - iat
    - jti

central_status:
  mode: hybrid
  lookup:
    - token_revocation_by_issuer_and_jti
    - session_status_when_sid_present
  active_cache_ttl_seconds: 10
  revoked_cache_ttl_seconds: 600
  max_revocation_propagation_seconds: 15
  status_service_unavailable: fail_closed
  emergency_key_block_overrides_cache: true

authorization:
  required_scope: orders:read
  resource_level_check: required
~~~

Đây là ví dụ minh họa, không phải schema RFC hoặc cấu hình thư viện. Giá trị TTL, claim bắt buộc, thuật toán và fail policy phải được chọn theo contract thực tế. Nếu cache active 10 giây nhưng hệ thống có thể mất thêm 20 giây để phát sự kiện, mục tiêu thu hồi 15 giây vẫn chưa đạt; phải tính tổng độ trễ end-to-end.

### 12.2. Ví dụ xử lý request

Giả sử một access token còn hạn 8 phút, chữ ký hợp lệ và scope có orders:read:

1. Orders API xác minh chữ ký bằng khóa của issuer đã cấu hình.
2. API xác minh iss, aud, typ, exp và claims bắt buộc.
3. API đọc jti và sid từ claims đã xác minh.
4. Status service trả session active và jti chưa bị revoke.
5. API kiểm tra user có quyền đọc đơn hàng cụ thể.
6. Request được chấp nhận.

Nếu người dùng logout ngay sau bước 4, có một race window. Cách giảm cửa sổ này phụ thuộc TTL cache, event invalidation và thời điểm commit. Với hành động rất nhạy cảm, có thể kiểm tra trạng thái lại ngay trước khi commit giao dịch.

## 13. Kiểm thử trạng thái và thu hồi

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| L01 | JWT hợp lệ, status active | Chấp nhận nếu quyền tài nguyên đạt |
| L02 | JWT hợp lệ nhưng jti bị revoke | Từ chối |
| L03 | JWT hợp lệ nhưng session bị revoke | Từ chối mọi token thuộc session theo policy |
| L04 | Refresh grant bị revoke, access token cũ còn exp | Xử lý theo contract; không mặc định access token tự mất hiệu lực |
| L05 | Subject inactive/credential version tăng | Token cũ bị từ chối theo policy |
| L06 | Role/tenant version thay đổi | Token cũ được xử lý theo độ trễ quyền đã công bố |
| L07 | Token thiếu jti nhưng contract yêu cầu revoke-by-jti | Từ chối |
| L08 | Status service lỗi, không có cache | Fail policy được thực thi |
| L09 | Status service lỗi, cache active hết TTL | Không dùng cache cũ |
| L10 | Emergency revoke event đến sau cache active | Invalidation/block mới phải thắng |
| L11 | Revocation event được gửi lặp | Consumer xử lý idempotent |
| L12 | Event bị trễ hoặc mất ở một region | Monitoring/reconciliation phát hiện |
| L13 | Hai request cùng consume one-time token | Chỉ một request thành công |
| L14 | Cache active TTL vượt exp còn lại | TTL bị chặn bởi exp và policy |
| L15 | Cache status của cùng jti nhưng khác issuer | Không dùng nhầm trạng thái |
| L16 | Key compromise, attacker tạo jti mới | Key identity block chặn; denylist jti đơn lẻ không đủ |
| L17 | Introspection trả active=false | Từ chối |
| L18 | Caller không được phép gọi introspection | Endpoint từ chối caller |

### 13.1. Kiểm thử độ trễ thu hồi

Đo toàn bộ thời gian:

- Thời điểm người dùng/admin gửi yêu cầu revoke.
- Thời điểm authoritative store commit trạng thái.
- Thời điểm event được publish.
- Thời điểm từng verifier nhận event.
- Thời điểm cache bị invalidated.
- Thời điểm request cuối cùng dùng token cũ bị từ chối.

Chỉ đo thời gian ghi database không chứng minh token đã bị chặn ở mọi API.

## 14. Checklist thiết kế mô hình lai

**Hợp đồng**

- [ ] Nêu rõ kiểm tra nào thực hiện offline và kiểm tra nào cần central status.
- [ ] Xác định trạng thái theo token, session, grant, subject hay policy version.
- [ ] Claim định danh trạng thái như jti/sid/grant ID có schema và namespace rõ.
- [ ] Định nghĩa độ trễ thu hồi tối đa cho từng loại request.

**Status store và cache**

- [ ] Có nguồn trạng thái authoritative và quy tắc ghi/đọc.
- [ ] TTL active cache bị giới hạn bởi exp và ngân sách thu hồi.
- [ ] Revoked/consumed state không bị ghi đè bởi dữ liệu cũ.
- [ ] One-time token được consume bằng thao tác atomic.
- [ ] Có event invalidation, retry, idempotency và reconciliation.

**Availability và bảo mật**

- [ ] Fail-open/closed được quy định theo rủi ro và endpoint.
- [ ] Emergency key block/revocation luôn thắng cache active cũ.
- [ ] Introspection/status endpoint xác thực caller và bảo vệ bằng TLS.
- [ ] Không bỏ qua chữ ký, issuer, audience hoặc token type khi status service lỗi.
- [ ] Không lưu raw JWT hoặc dữ liệu nhạy cảm không cần thiết trong status store/log.

**Kiểm thử và vận hành**

- [ ] Có test revoke theo jti, session, grant, subject và one-time token.
- [ ] Có test cache stale, event lag, multi-region và dependency outage.
- [ ] Đo độ trễ end-to-end từ revoke tới request bị từ chối.
- [ ] Có dashboard cho cache hit/miss, event lag, status latency và lỗi introspection.
- [ ] Có playbook khi status store, event stream hoặc issuer gặp sự cố.

**Điều cần nhớ:** JWT tự chứa giúp xác minh chữ ký và claims mà không phải gọi issuer trong mọi request, nhưng không tự biết những thay đổi trạng thái xảy ra sau khi phát hành. Mô hình lai giữ xác minh mật mã tại resource server và bổ sung tra cứu trạng thái tập trung theo token, session, grant hoặc subject. Thiết kế tốt phải quy định rõ nguồn sự thật, độ trễ thu hồi, cache, nhất quán nhiều region và hành vi khi dependency lỗi.

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): Cấu trúc JWT và registered claims, gồm jti.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): Endpoint kiểm tra trạng thái token và trường active.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): Thu hồi access token và refresh token.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): Profile access token và yêu cầu xác minh resource server.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): Thực hành xác minh JWT và ràng buộc profile.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): Refresh token protection, rotation và phát hiện reuse.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): Ràng buộc token với bằng chứng sở hữu khóa.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): Sender-constrained access token bằng mTLS.
