# Consent là quyết định cấp quyền

Một người dùng đăng nhập vào ứng dụng quản lý đơn hàng và nhìn thấy màn hình:

> **“Ứng dụng Báo cáo bán hàng muốn xem danh sách đơn hàng của bạn. Cho phép hay Từ chối?”**

Người dùng đã đăng nhập thành công, nhưng đó **chưa phải** lý do để ứng dụng Báo cáo bán hàng tự động được đọc mọi đơn hàng. Việc xác thực trả lời câu hỏi **“Ai đang đăng nhập?”**; còn **consent** trong một luồng OAuth 2.0 thường thể hiện quyết định **“Có đồng ý cho OAuth client này được thực hiện những quyền được mô tả, trong những điều kiện cụ thể, hay không?”**.

**Consent là một quyết định cấp quyền có ngữ cảnh, không phải thao tác nhập mật khẩu, không phải access token, không phải bảo đảm client được phép làm mọi việc và cũng không thay thế việc phân quyền tại Resource Server.** Authorization Server (AS) phải kết hợp quyết định của chủ thể có quyền, các grant/policy và giới hạn của client trước khi phát hành token. Khi API nhận access token, nó vẫn phải xác minh issuer, audience, scope, thời hạn và quyền trên đối tượng cụ thể.

Bài học thuộc chương **Consent** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung liên kết consent với mô hình tin cậy và vòng đời **JWT, opaque token, access token, refresh token**, OAuth 2.0/OpenID Connect (OIDC), claims, scope, audience, lưu trữ, thu hồi và phòng chống token/ủy quyền bị đánh cắp hoặc lạm dụng.

Sau bài học, bạn sẽ giải thích được consent quyết định điều gì, phân biệt **authentication – user approval – authorization grant – token issuance – API authorization**, thiết kế consent screen và consent record đúng ranh giới, xử lý cho phép/từ chối, tránh OAuth consent phishing và xây dựng kiểm thử bảo mật.

## 1. Consent không đồng nghĩa đăng nhập

Hãy tách bốn bước có thể xuất hiện trong một OAuth flow:

| Câu hỏi | Khái niệm | Bên chịu trách nhiệm chính |
|---|---|---|
| **Người này là ai?** | Authentication (xác thực người dùng) | Identity Provider / Authorization Server theo kiến trúc |
| **Người/cơ chế có quyền có chấp thuận client xin quyền này không?** | Consent / approval (quyết định chấp thuận) | Chủ thể được quyền quyết định, qua AS và chính sách liên quan |
| **AS có được cấp credential thể hiện quyền đã được phép không?** | Authorization grant evaluation và token issuance | Authorization Server |
| **Request này có được đọc/sửa tài nguyên cụ thể không?** | Resource authorization | Resource Server và policy nghiệp vụ |

Một phiên đăng nhập hợp lệ chỉ chứng minh danh tính theo độ bảo đảm nhất định. Người dùng có thể đăng nhập để xem tài khoản, nhưng **từ chối** cho ứng dụng của bên thứ ba đọc lịch sử đơn hàng. Khi đó AS không được xem đăng nhập thành công là đồng ý cho mọi scope.

Ngược lại, việc người dùng bấm **“Cho phép”** cũng không thể cấp quyền mà họ **không sở hữu** hoặc không được tổ chức/chính sách cho phép ủy quyền. AS phải giới hạn quyền theo cả **user, client, resource, policy**; Resource Server phải tiếp tục đánh giá quyền khi thực sự truy cập.

**Một mô hình dễ nhớ:**

~~~text
Authentication   = xác minh danh tính
Consent          = quyết định chấp thuận quyền được yêu cầu
Authorization grant = cơ sở/ủy quyền mà AS chấp nhận để cấp token
Access token     = credential truy cập API trong phạm vi được cấp
Resource policy  = quyết định có cho thao tác với tài nguyên cụ thể không
~~~

Không phải flow OAuth nào cũng hiện màn hình consent; phần này sẽ được phân biệt rõ ở mục sau.

## 2. Consent nằm ở đâu trong bốn vai trò OAuth 2.0?

OAuth 2.0 mô tả **Resource Owner**, **Client**, **Authorization Server** và **Resource Server**.

| Vai trò | Liên hệ với consent |
|---|---|
| **Resource Owner** | Chủ thể có quyền cấp quyền truy cập tài nguyên; thường là người dùng, nhưng có thể là tổ chức/chủ thể khác theo mô hình |
| **Client** | Ứng dụng xin được truy cập tài nguyên bằng một tập quyền; không tự quyết định mình đã được chấp thuận |
| **Authorization Server** | Xác thực, xác định điều kiện ủy quyền, thu thập hoặc áp dụng quyết định cấp quyền theo chính sách và phát hành token |
| **Resource Server** | Chấp nhận access token phù hợp, kiểm tra và đánh giá quyền đối với request/tài nguyên |

Ví dụ:

~~~text
Người dùng:         user-42
OAuth client:       sales-report-app
Authorization AS:   https://auth.example.org
Resource Server:    orders-api
Requested scope:    orders:read
Requested resource: Orders API
~~~

Ứng dụng **sales-report-app** muốn đọc đơn hàng. AS kiểm xem client có đăng ký hợp lệ, user đang xác thực là ai, quyền nào có thể ủy quyền, có cần consent mới hay grant trước đó còn phù hợp không. Nếu được chấp thuận và không vi phạm policy, AS có thể phát authorization code, sau đó cấp access token khi code được đổi hợp lệ.

Resource Server nhận access token **không cần nhận chính màn hình consent**, nhưng phải có đủ thông tin tin cậy từ token/AS để kiểm audience, scope và chủ thể theo hợp đồng.

## 3. Consent là quyết định, không phải token hay scope

Một request OAuth có thể mang:

~~~text
client_id = sales-report-app
scope     = orders:read
resource  = https://api.example.org/orders
~~~

Những giá trị này biểu diễn **điều client muốn**, không phải điều đã được cấp.

Phân biệt các lớp:

1. **Requested scope:** các quyền client yêu cầu.
2. **Eligible scope:** quyền tối đa AS/policy cho phép client và chủ thể có thể được cấp.
3. **Approved/consented scope:** phạm vi đã được chủ thể có thẩm quyền chấp thuận khi consent được yêu cầu.
4. **Granted scope:** quyền AS thực tế chấp nhận trong grant/token response.
5. **Effective permissions:** những thao tác Resource Server cuối cùng cho phép với tài nguyên cụ thể.

Ví dụ:

| Trường hợp | Kết quả hợp lý |
|---|---|
| Client yêu cầu **orders:read**, user có quyền đọc đơn và chấp thuận | AS có thể cấp **orders:read**, tùy các điều kiện còn lại |
| Client yêu cầu **orders:write** nhưng người dùng chỉ có quyền xem | Consent không thể tạo quyền viết; AS/RS phải từ chối hoặc không cấp quyền đó |
| User chấp thuận **orders:read**, client lén xin **payments:charge** tại token endpoint | AS không được cấp scope vượt grant đã được cho phép |
| Token có scope **orders:read** nhưng đang truy cập đơn hàng của tenant khác | RS phải từ chối nếu user/client không có quyền với đơn hàng ấy |

**Scope mô tả quyền tương đối thô, còn consent là quyết định về quyền được xin trong một ngữ cảnh cụ thể.** Hai thứ liên quan nhưng không đồng nghĩa. Một token có claim `scope` không chứng minh màn hình consent đã được hiển thị theo đúng UI; AS phải quản lý quá trình ra quyết định phù hợp.

## 4. Luồng Authorization Code + PKCE có consent

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as sales-report-app
    participant A as Authorization Server
    participant T as Token endpoint
    participant R as Orders API
    U->>C: Chọn kết nối tài khoản
    C->>C: Tạo state, code_verifier và S256 challenge
    C->>A: Authorization request: client, scope, resource, redirect, PKCE
    A->>U: Xác thực người dùng nếu cần
    A->>A: Kiểm client và policy được phép cấp quyền
    A->>U: Hiển thị consent: ai xin, xin quyền gì, dùng ở đâu
    alt Chấp thuận hợp lệ
        U->>A: Approve
        A->>A: Ghi nhận grant/consent phù hợp
        A-->>C: Redirect code + state
        C->>T: Đổi code + PKCE verifier + client proof
        T->>T: Kiểm code, redirect, client, grant, PKCE, TTL
        T-->>C: Access token và token khác nếu được cấp
        C->>R: Bearer access token
        R->>R: Kiểm issuer, audience, scope, policy tài nguyên
        R-->>C: Kết quả được phép
    else Từ chối
        U->>A: Deny
        A-->>C: Authorization error, ví dụ access_denied
        Note over C,R: Không cấp access token cho quyền bị từ chối
    end
~~~

Trong thực tế, AS có thể không hỏi consent lại nếu có **grant hợp lệ đã được ghi nhận**, chính sách tổ chức có thẩm quyền cho phép, hoặc flow không áp dụng consent màn hình. **Không nên hiểu diagram là OAuth bắt buộc phải hiện nút Approve ở mọi lần gọi.**

### Hai ranh giới quan trọng

**Ranh giới 1 — Authorization endpoint:** kiểm **client, redirect URI đã đăng ký, state/flow, scope/resource và quyết định ủy quyền**. AS chỉ gửi code tới redirect URI tin cậy.

**Ranh giới 2 — Token endpoint:** client mang code tới AS, AS kiểm **code một lần, đúng client, redirect URI và PKCE**, trạng thái grant và policy trước khi cấp token. **Bấm Approve không cho phép bỏ qua PKCE hoặc xác thực confidential client.**

Sau đó, **Resource Server** vẫn có ranh giới thứ ba là xác minh token và phân quyền trên từng request.

## 5. Một consent screen có ý nghĩa phải trả lời được những câu hỏi nào?

Người dùng cần hiểu **ai đang xin quyền gì, với dữ liệu nào và điều gì xảy ra nếu cho phép**.

Một màn hình minh họa:

~~~text
CHO PHÉP ỨNG DỤNG KẾT NỐI?

Ứng dụng: Sales Report (được xác định từ client đăng ký)
Tài khoản: user-42@example.org
Hệ thống dữ liệu: Orders API

Ứng dụng yêu cầu:
  ✓ Xem danh sách và chi tiết đơn hàng

Ứng dụng KHÔNG được yêu cầu:
  - Sửa hoặc xóa đơn hàng
  - Thực hiện thanh toán

Bạn có thể xem lại và thu hồi kết nối trong phần Quản lý ứng dụng.

[Từ chối]                    [Cho phép]
~~~

Ví dụ này **không tự áp đặt một mẫu giao diện chuẩn**. Các yêu cầu thực tế tùy độ nhạy cảm dữ liệu, UI của AS, client và chính sách tổ chức.

### Những thông tin nên có

| Thông tin | Vì sao quan trọng? |
|---|---|
| **Tên và danh tính ứng dụng/client** | Người dùng phải biết bên nào nhận quyền; tên hiển thị cần dựa trên đăng ký đáng tin |
| **Tài khoản đang dùng** | Ngăn chấp thuận trên nhầm tài khoản hoặc tenant |
| **Quyền được yêu cầu, diễn giải dễ hiểu** | Scope như `orders:read` nên được mô tả bằng hành động gần với người dùng |
| **Resource/dữ liệu mà quyền áp dụng** | Tránh hiểu “xem đơn hàng” thành quyền với mọi ứng dụng/API |
| **Phạm vi ảnh hưởng/điều kiện duy trì** | Ví dụ có thể dùng lại kết nối, làm mới token hoặc thu hồi ở đâu |
| **Hành động Từ chối rõ ràng** | Người dùng có thể không cấp quyền mà không cần đánh lừa giao diện |
| **Cách quản lý hoặc thu hồi sau này** | Consent không phải quyết định bất biến |

Không dùng **tên ứng dụng tự khai trong query parameter** để tạo cảm giác tin cậy. AS cần lấy tên và trạng thái client từ **client registration đã xác minh**; với ứng dụng bên thứ ba, có thể bổ sung thông tin publisher/verification khi hệ thống hỗ trợ.

## 6. Ai được phép cho consent và khi nào có thể không cần hỏi lại?

OAuth 2.0 nói về **Resource Owner** và authorization grants; trong nhiều ứng dụng, resource owner chính là người dùng. Nhưng có trường hợp **tổ chức, quản trị viên hoặc chính sách hệ thống** có quyền đưa ra quyết định cấp quyền thay vì mỗi người dùng đều bấm một nút.

| Tình huống | Quyết định cấp quyền có thể đến từ đâu? | Lưu ý |
|---|---|---|
| Ứng dụng bên thứ ba đọc dữ liệu cá nhân của user | Người dùng có quyền và policy của AS | Cần thông tin đủ hiểu và scope giới hạn |
| Ứng dụng nội bộ đã được tổ chức phê duyệt | Chính sách tổ chức/grant có trước | Không tự suy rằng mọi ứng dụng nội bộ đều được đọc mọi dữ liệu |
| Doanh nghiệp cho phép admin phê duyệt một tập quyền | Admin có đúng quyền phê duyệt theo mô hình tổ chức | Admin consent không mặc nhiên cấp quyền ngoài tổ chức/tenant |
| Client Credentials grant cho service | Policy và quyền của chính client/service | Thường **không có end user consent screen** |
| User đã chấp thuận cùng client, scope và resource trước đó | Grant còn hiệu lực theo policy | Có thể dùng lại; không được ngầm nâng scope hoặc chuyển tenant |

**Consent UI không phải điều kiện bắt buộc của mọi OAuth grant.** RFC 6749 để nhiều chi tiết tương tác phê duyệt theo cách triển khai; điều cốt lõi là AS phải có **cơ sở ủy quyền hợp lệ** cho quyền nó cấp.

Một AS có thể dùng **existing grant** để không hỏi lại nếu yêu cầu mới nằm trong chính xác phạm vi được cho phép và còn hợp lệ. Nhưng nếu client thay đổi quyền, resource, tenant hoặc điều kiện rủi ro, AS phải áp dụng policy quyết định có cần **consent mới** hay không. Không mặc định “đã đồng ý một lần” thành cấp phép vĩnh viễn cho mọi quyền tương lai.

### Consent OAuth khác consent theo pháp luật dữ liệu cá nhân

**OAuth consent** trong bài này là cơ chế/quyết định **ủy quyền truy cập** theo giao thức và policy. Nó **không tự động đồng nghĩa** sự đồng ý hợp lệ theo pháp luật bảo vệ dữ liệu cá nhân, hợp đồng, marketing hoặc mục đích xử lý dữ liệu khác. Một hệ thống cần đánh giá nghĩa vụ riêng theo bối cảnh pháp lý; không coi việc có `scope` và nút Allow là đã đáp ứng mọi yêu cầu pháp luật.

## 7. Scope, resource, audience và least privilege

Người dùng không thể đưa ra quyết định có ý nghĩa nếu ứng dụng xin quyền quá rộng hoặc diễn đạt mơ hồ.

Ví dụ AS quản lý ba loại tài nguyên:

| Tài nguyên | Audience token minh họa | Scope có thể cấp |
|---|---|---|
| **Orders API** | `orders-api` | `orders:read`, `orders:write` |
| **Payments API** | `payments-api` | `payments:read`, `payments:charge` |
| **Profile API** | `profile-api` | `profile:read` |

Giả sử client chỉ cần hiển thị biểu đồ đơn hàng. Quyền phù hợp là **orders:read**, không phải **orders:write + payments:charge**. Áp dụng **least privilege** từ ba phía:

1. **Client** chỉ yêu cầu quyền cần cho tính năng.
2. **Authorization Server** chỉ cho phép những quyền client/user/policy và consent chấp thuận.
3. **Resource Server** chỉ thực thi quyền cụ thể thuộc token và policy tài nguyên.

**Audience không phải scope.** Access token có scope `orders:read` nhưng **aud=payments-api** không được dùng ở Orders API. Tương tự, đúng audience không cho phép mọi thao tác nếu thiếu scope hoặc quyền với đối tượng cụ thể.

Khi AS hỗ trợ **OAuth 2.0 Resource Indicators (RFC 8707)**, client có thể yêu cầu tài nguyên cụ thể qua tham số `resource`. AS quyết định tài nguyên nào được phép và cách phát hành audience; **không mặc định `aud` luôn là nguyên văn tham số `resource`**. Mọi yêu cầu resource mới cần được đánh giá theo grant/policy thay vì mặc nhiên mở rộng quyền.

### Consent không biến quyền bị cấm thành quyền hợp lệ

Ví dụ user chỉ có quyền đọc đơn của tenant A. Dù user chấp thuận ứng dụng xem đơn hàng, Orders API vẫn phải từ chối truy cập đơn thuộc tenant B. Chính sách tổ chức, quyền đối tượng và trạng thái tài khoản có thể thay đổi sau khi consent được ghi nhận.

## 8. Consent trong OIDC: đăng nhập khác cho phép API truy cập

**OpenID Connect (OIDC)** bổ sung lớp xác thực danh tính trên OAuth 2.0. Client có thể xin scope `openid` và nhận **ID token** để xác minh phiên đăng nhập. Điều này khác với consent cho ứng dụng truy cập resource APIs.

| Dữ liệu/khái niệm | Mục đích |
|---|---|
| **OIDC ID token** | Client xác minh kết quả authentication theo issuer, audience là client, thời hạn và điều kiện flow |
| **OAuth access token** | Client gọi Resource Server đúng audience/scope |
| **Refresh token** | Xin access token mới qua token endpoint theo grant/client policy |
| **Consent** | Quyết định cho phép những quyền/claims/resource được yêu cầu theo policy |
| **Login session** | Trạng thái xác thực của người dùng tại AS hoặc ứng dụng |

### `prompt=consent` có nghĩa gì?

Trong OIDC, tham số **`prompt=consent`** cho OpenID Provider biết client **muốn hiển thị giao diện consent cho người dùng**, kể cả khi đã có đồng ý trước đó, theo các quy tắc của profile. Điều này **không có nghĩa** client được phép ép AS cấp thêm quyền hoặc bỏ qua bất kỳ policy nào.

Một authorization request OIDC minh họa:

~~~http
GET /authorize?response_type=code&client_id=shop-web&redirect_uri=https%3A%2F%2Fapp.example.org%2Fcallback&scope=openid%20profile%20orders%3Aread&state=<random-state>&code_challenge=<S256-challenge>&code_challenge_method=S256&prompt=consent HTTP/1.1
Host: auth.example.org
~~~

Đây là request minh họa có tham số PKCE. Các giá trị được **URL encode** và chỉ được dùng với issuer/redirect URI đã đăng ký đáng tin. AS cần kiểm client, scope, prompt và chính sách thực tế; `prompt=consent` không tự xác thực người dùng.

### `offline_access` không đồng nghĩa refresh token vô hạn

Trong OIDC, scope **`offline_access`** là yêu cầu liên quan đến khả năng truy cập khi người dùng không trực tiếp hiện diện; OpenID Provider áp dụng điều kiện về flow, consent và policy trước khi cấp quyền. **Yêu cầu `offline_access` không bảo đảm có refresh token**, và refresh token nếu được cấp vẫn chịu expiration, rotation, client binding, revocation hoặc sender-constraining theo kiến trúc.

**Không dùng ID token thay access token** khi gọi API; **không dùng refresh token để gọi Resource Server**. Consent có thể dẫn đến grant được cấp, nhưng token nào được phát vẫn phụ thuộc loại flow và chính sách AS.

## 9. Grant được ghi nhận như thế nào?

Trong hệ thống có consent tồn tại lâu hơn một HTTP request, AS có thể lưu một **authorization grant/consent record** để quyết định liệu yêu cầu mới có nằm trong phạm vi đã chấp thuận hay không.

Ví dụ mô hình dữ liệu logic:

~~~json
{
  "grant_ref": "grant-example-017",
  "issuer": "https://auth.example.org",
  "client_id": "sales-report-app",
  "subject_ref": "user-42",
  "tenant_ref": "tenant-A",
  "resource": "orders-api",
  "approved_scopes": ["orders:read"],
  "decision": "APPROVED",
  "approved_at": "2026-11-23T09:00:00Z",
  "expires_at": "2026-12-23T09:00:00Z",
  "revoked_at": null,
  "consent_policy_version": "policy-v3",
  "decision_source": "resource_owner"
}
~~~

Đây là **ví dụ nội bộ**, không phải response OAuth hay schema tiêu chuẩn bắt buộc. Những giá trị về thời gian chỉ để minh họa. Một grant có thể có quy tắc hết hạn khác, dữ liệu khác hoặc được quản lý mà không lưu thành JSON.

**Các thuộc tính quan trọng khi thiết kế:**

- **Client identity:** client nào được phép hưởng quyết định, không chuyển consent sang client khác.
- **Subject/resource owner:** chủ thể nào đã phê duyệt, trong đúng account/tenant.
- **Scope/resource:** chính xác quyền nào và tài nguyên nào được phép; tránh một flag `consented=true` cho mọi API.
- **Decision source:** người dùng, admin hoặc policy có thẩm quyền, được ghi nhận đúng ngữ cảnh.
- **Time và status:** khi nào được cấp, có hết hạn hoặc bị thu hồi chưa.
- **Policy version:** giúp đánh giá quyết định cũ còn phù hợp khi quy tắc thay đổi hay không.
- **Auditability:** ghi metadata đủ điều tra nhưng không tạo bản sao access/refresh token.

**Grant record không phải bearer credential**. Client không được dùng `grant_ref` như token để gọi API. Nếu hệ thống dùng một **approval reference** trong luồng bất đồng bộ, nơi nhận phải xác minh record thuộc client, subject, scope, resource, tenant và trạng thái hiện hành.

## 10. Một quyết định phải gắn với đúng OAuth transaction

Một yêu cầu consent có thể bị tấn công bằng cách **trộn phiên**: hiển thị quyền của giao dịch A nhưng ghi nhận phê duyệt cho giao dịch B, hoặc chuyển kết quả cho client khác.

Ràng buộc cần thiết ở AS:

~~~text
authorization_transaction:
  transaction_id  -> tx-401
  client_id       -> sales-report-app
  redirect_uri    -> https://app.example.org/oauth/callback
  subject_ref     -> user-42 (sau xác thực)
  tenant_ref      -> tenant-A
  requested_scope -> orders:read
  requested_aud   -> orders-api
  pkce_challenge  -> <S256 challenge>
  current_state   -> WAITING_FOR_DECISION
~~~

Khi người dùng bấm Approve, AS phải **chấp thuận chính giao dịch đã được hiển thị và kiểm tra**, không chấp nhận việc browser tùy ý sửa `client_id`, `scope` hoặc `resource` qua hidden inputs rồi AS ghi nhận quyền mới.

### Luồng phê duyệt an toàn

~~~mermaid
flowchart TD
    A["AS nhận authorization request"] --> B{"Client, redirect, flow hợp lệ?"}
    B -->|Không| X["Reject, không chuyển tới URI chưa tin"]
    B -->|Có| C["Xác thực/chọn account theo policy"]
    C --> D["Tính scope/resource tối đa được cấp"]
    D --> E{"Grant còn phù hợp hoặc cần hỏi consent?"}
    E -->|Có thể dùng grant hợp lệ| J["Ghi nhận quyền được phép theo grant"]
    E -->|Cần quyết định mới| F["Hiển thị client, account, scope, resource"]
    F --> G{"Approve hay Deny?"}
    G -->|Deny| Y["access_denied; không cấp grant mới"]
    G -->|Approve| H{"Session, transaction và policy còn hợp lệ?"}
    H -->|Không| X
    H -->|Có| I["Commit decision/grant nguyên tử"]
    I --> J
    J --> K["Phát code có PKCE/client/redirect binding"]
    K --> L["Token endpoint kiểm code/grant rồi cấp token"]
~~~

Các trạng thái minh họa; triển khai thực tế có thể sắp xếp kiểm policy và tương tác theo flow khác nhau. Nhưng **việc bấm Approve không được tạo ra quyền vượt eligible scope**, cũng không được áp dụng cho giao dịch đã hết hạn hoặc đã bị thay đổi.

### Chống CSRF, clickjacking và double submit

- Bảo vệ session và **anti-CSRF** cho thao tác consent theo cơ chế AS; không xem `state` của OAuth client là đủ cho mọi form của AS.
- Cấu hình **Content Security Policy** và các biện pháp ngăn clickjacking trên trang consent, đặc biệt với quyền nhạy cảm.
- Không cho browser sửa quyền/identifiers quan trọng mà AS không đối chiếu lại với transaction tin cậy.
- Nếu hai tab cùng thao tác cùng transaction, chỉ ghi nhận **một kết quả nhất quán**; không tạo grant trái chiều hoặc cấp token nhiều nhánh trái policy.
- Chống approval replay: quyết định của transaction đã hoàn tất không được áp dụng cho một giao dịch mới.

## 11. Quyết định Từ chối phải được tôn trọng từ đầu tới cuối

**Deny** là kết quả hợp lệ của một quy trình consent; không phải lỗi client nên lén retry để né quyết định của người dùng.

Khi Resource Owner từ chối một authorization request hợp lệ, Authorization Server có thể trả lỗi **`access_denied`** tới **redirect URI đã được xác minh**, theo quy tắc của authorization endpoint:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.org/oauth/callback?error=access_denied&state=<original-state>
~~~

Đây là ví dụ, không phải mọi flow đều chuyển hướng theo đúng URL/cấu trúc này. **Nếu client_id hoặc redirect URI không hợp lệ, AS không được tự redirect tới URI không tin cậy**, kể cả để trả lỗi.

Client nên:

1. Phân biệt **user denied** với lỗi mạng hoặc token endpoint.
2. Không hiển thị thông báo “đăng nhập thất bại” nếu thực tế người dùng đã xác thực nhưng từ chối quyền.
3. Không tự đổi flow sang scope rộng hơn hoặc thử lại âm thầm nhiều lần.
4. Cho phép tiếp tục trải nghiệm không cần quyền đó khi có thể.
5. Chỉ bắt đầu lại yêu cầu consent khi có **hành động mới rõ ràng** từ người dùng hoặc một chính sách hợp lệ.

AS phải đảm bảo quyết định Deny **không phát authorization code mới có thể đổi lấy quyền vừa bị từ chối** và **không cấp access token** cho request ấy. Nếu đã có grant cũ, cách Deny ảnh hưởng đến grant cũ cần được **quy định riêng**: từ chối một authorization request mới **không nhất thiết tự thu hồi toàn bộ access token đã cấp trước đó**.

## 12. Consent bị thay đổi, hết hạn hoặc bị thu hồi thì sao?

Consent không nên được hiểu là một cờ vĩnh viễn. Tùy chính sách, người dùng hoặc admin có thể:

- **Thu hồi kết nối** với một client.
- **Giảm quyền** từ `orders:read orders:write` xuống `orders:read`.
- **Ngừng cho phép offline access** hoặc vô hiệu hóa refresh token.
- **Đổi tenant/account** mà app được phép truy cập.
- **Hết hạn một grant** theo thời gian hoặc policy.
- **Bị thu hồi quyền nền tảng** do tài khoản/role/membership thay đổi.

Sự thay đổi cần đi qua các lớp:

| Lớp | Khi thu hồi/quyền giảm |
|---|---|
| **Grant/consent record tại AS** | Đánh dấu revoked/expired, cập nhật quyền được phép |
| **Authorization endpoint** | Không tự cấp lại quyền đã bị thu hồi từ grant cũ |
| **Token endpoint** | Từ chối refresh hoặc chỉ cấp quyền còn được phép theo policy |
| **Refresh token** | Có thể cần thu hồi token hoặc token family để ngăn tiếp tục xin access token |
| **Access token đang còn hạn** | Cần chính sách thu hồi sớm hoặc chấp nhận cửa sổ hiệu lực còn lại |
| **Resource Server** | Kiểm token và quyền hiện hành; không cho phép chỉ vì consent record từng APPROVED |

**Thu hồi consent không đồng nghĩa tất cả JWT access token đã phát trước đó lập tức vô hiệu**. Một Resource Server chỉ kiểm chữ ký và `exp` có thể vẫn nhận access token cho tới khi hết hạn, nếu không có denylist/token epoch/kiểm tra trạng thái hoặc biện pháp tương đương.

Với **opaque access token**, introspection có thể phản ánh trạng thái bị vô hiệu hóa, nhưng **cache introspection** có thể tạo độ trễ. Với **refresh token rotation**, AS còn cần xử lý các token cũ và phát hiện reuse theo chính sách.

### Phân biệt revoke với logout

**Đăng xuất** khỏi ứng dụng hoặc AS session và **thu hồi quyền truy cập OAuth** là hai thao tác khác nhau. Logout ở một browser không bảo đảm app bên thứ ba mất mọi access/refresh token đã lưu. Nếu người dùng muốn ngừng cấp quyền, cần cơ chế **disconnect/revoke grant/token** phù hợp; token revocation theo **RFC 7009** là một công cụ ở tầng OAuth, không phải bản thân định nghĩa consent.

## 13. Consent không thay được Resource Server authorization

Một người dùng có thể chấp thuận cho **sales-report-app** đọc đơn hàng, nhưng điều đó **không chứng minh** ứng dụng được đọc mọi đơn hàng trên hệ thống.

Ví dụ:

~~~text
Access token đã được AS cấp:
  iss        = https://auth.example.org
  sub        = user-42
  client_id  = sales-report-app
  aud        = orders-api
  scope      = orders:read

Request:
  GET /tenants/tenant-B/orders/order-99

Thực tế:
  user-42 chỉ có quyền đọc đơn của tenant-A
~~~

**Resource Server phải từ chối** nếu request truy cập ngoài tenant hoặc quyền đối tượng, dù chữ ký JWT đúng và `scope=orders:read`.

~~~text
authorizeReadOrder(request):
    token = requireBearerAccessToken(request)
    principal = trustedAccessTokenValidator.validate(
        token,
        issuer = configuredIssuer,
        audience = "orders-api",
        tokenKind = "access_token"
    )
    if principal invalid:
        return 401

    if not principal.hasScope("orders:read"):
        return 403

    order = orderRepository.findInVerifiedTenant(request.orderId)
    if order missing:
        return 404

    if not currentPolicy.canRead(principal, order):
        return 403

    return 200, allowedOrderFields(order)
~~~

Pseudocode này minh họa trách nhiệm, **không phải validator có thể dùng trực tiếp**. JWT access token cần kiểm chữ ký, issuer, audience, time claims và profile; opaque token cần xác minh qua introspection/nguồn trạng thái đáng tin. Các điều kiện quyền tài nguyên phải được thực thi sau khi biết principal đáng tin.

**Một claim tự ghi `consent=true` trong token chưa xác minh không có giá trị tin cậy.** Kể cả claim đã ký, nó chỉ có ý nghĩa theo hợp đồng AS–RS và không thay kiểm policy hiện hành.

## 14. Consent phishing: khi người dùng bị dụ cấp quyền cho ứng dụng lạ

Một kiểu tấn công không cần đánh cắp mật khẩu là **OAuth consent phishing**:

1. Kẻ tấn công tạo hoặc kiểm soát một OAuth client có tên/biểu tượng dễ gây nhầm.
2. Họ gửi cho nạn nhân liên kết “xem tài liệu”, “đồng bộ dữ liệu”, “xác minh bảo mật”.
3. Nạn nhân được đưa đến **Authorization Server thật** và đăng nhập.
4. Trang consent yêu cầu scope có giá trị cao, chẳng hạn quyền đọc dữ liệu.
5. Nếu nạn nhân chấp thuận, AS có thể cấp token cho **client của attacker** trong phạm vi được cấp.

~~~mermaid
sequenceDiagram
    participant X as Client do attacker kiểm soát
    actor U as Người dùng
    participant AS as Authorization Server thật
    participant API as Resource Server
    X-->>U: Link dụ kết nối ứng dụng
    U->>AS: Đăng nhập tại AS thật
    AS->>U: Consent của client attacker, scope yêu cầu
    U->>AS: Chấp thuận do hiểu nhầm
    AS-->>X: Authorization code qua redirect hợp lệ của client attacker
    X->>AS: Đổi code theo grant/client binding
    AS-->>X: Access token nếu grant hợp lệ
    X->>API: Gọi API bằng token đã được cấp
~~~

**Trang đăng nhập thật và chữ ký token hợp lệ không tự chứng minh quyết định cấp quyền là khôn ngoan.** AS có thể phát token đúng giao thức cho một client không đáng tin mà người dùng vừa bị dụ phê duyệt.

### Giảm nguy cơ consent phishing

- **Xác minh publisher/client** khi có khả năng; không để tên ứng dụng tự khai tạo cảm giác được chứng nhận.
- **Least privilege:** hạn chế scope nhạy cảm, đặc biệt quyền ghi/xóa hoặc truy cập lâu dài.
- **Consent screen rõ ràng:** ai xin, loại dữ liệu, phạm vi, tài khoản và cách thu hồi.
- **Admin/client governance:** với tenant doanh nghiệp, quản lý app cho phép, scope nhạy cảm và quyền phê duyệt admin theo chính sách.
- **Step-up/risk-based controls:** tăng kiểm tra cho quyền tác động lớn, nhưng không xem MFA là bảo đảm người dùng đã hiểu scope.
- **Monitoring:** phát hiện số lượng phê duyệt bất thường, client mới xin quyền rộng, grant/token usage bất thường.
- **User awareness:** không chấp thuận ứng dụng từ link không mong muốn; kiểm chính tên ứng dụng và quyền, không chỉ domain login.

Trong **Device Authorization Grant**, attacker còn có thể dụ nạn nhân nhập **user_code của thiết bị do attacker khởi tạo** trên trang AS thật. Nguyên tắc chung vẫn là **chỉ phê duyệt giao dịch bạn chủ động khởi tạo, với client và quyền đúng dự kiến**.

## 15. Other threats: CSRF, clickjacking, scope tampering và mix-up

| Tấn công / lỗi | Cách xảy ra | Kiểm soát |
|---|---|---|
| **Consent CSRF** | Browser bị dụ gửi thao tác Approve cho transaction không mong muốn | CSRF protection và session/transaction binding tại AS |
| **Clickjacking** | Trang consent bị lồng/che khiến người dùng bấm nhầm | CSP `frame-ancestors` và bảo vệ UI theo chính sách |
| **Scope tampering** | Browser sửa hidden input từ read thành write | AS đối chiếu với transaction server-side, không tin form body |
| **Client impersonation trong UI** | Client khai tên/logo gây nhầm | Hiển thị metadata đăng ký đáng tin, kiểm publisher khi cần |
| **Authorization response injection** | Client nhận callback không thuộc phiên của mình | `state`, PKCE, issuer/AS binding, redirect URI chuẩn |
| **AS mix-up** | Code được đưa sang token endpoint issuer khác | Client gắn issuer với từng flow và kiểm theo profile |
| **Overbroad consent** | Ứng dụng xin nhiều scope không cần | Scope review, least privilege, consent rõ từng nhóm quyền |
| **Silent permission expansion** | App dùng grant cũ để xin tài nguyên mới | AS so approved scope/resource, yêu cầu ủy quyền mới khi cần |
| **Replayed approval** | Cùng thao tác Approve tác động hai transaction | Atomic state transition, one-time transaction |
| **Stale membership** | Quyền bị thu hồi nhưng token JWT vẫn chứa claims cũ | RS kiểm policy hiện hành hoặc cơ chế revocation/epoch |

**Không có một lớp duy nhất đủ thay các lớp khác.** Ví dụ PKCE giúp chống authorization code interception nhưng không giải thích cho người dùng vì sao app xin `payments:charge`; consent UI giúp người dùng quyết định nhưng không bảo vệ Resource Server khi audience sai.

## 16. Incremental authorization: xin thêm quyền khi thật sự cần

Một ứng dụng nên bắt đầu với quyền tối thiểu và chỉ xin thêm khi người dùng chủ động dùng chức năng cần quyền đó.

Ví dụ:

| Thời điểm | Nhu cầu thực | Quyền hợp lý |
|---|---|---|
| Lần đầu liên kết | Xem danh sách đơn hàng | `orders:read` |
| Khi user muốn cập nhật trạng thái đơn | Sửa đơn hàng theo quyền của user | Xin thêm `orders:write` nếu được phép |
| Khi user muốn thanh toán | Tác vụ payment riêng | Một grant/quyền phù hợp cho Payments API, kiểm rủi ro và xác nhận |

**Incremental authorization** là mô hình giảm phạm vi quyền được cấp sớm; cách AS hỗ trợ yêu cầu scope thêm và diễn giải consent có thể khác nhau giữa providers. Không mặc định mọi AS tự gộp grant mới vào grant cũ, hoặc tự động cấp toàn bộ tập scope từng được yêu cầu.

Đối với quyền có cấu trúc phức tạp (ví dụ chỉ xem giao dịch trong một tài khoản cụ thể), **OAuth 2.0 Rich Authorization Requests (RFC 9396)** định nghĩa cách mang `authorization_details` trong những hệ thống hỗ trợ. Nhưng **authorization_details không tự sinh ra quyền**: AS vẫn cần kiểm policy/approval, và API vẫn cần thực thi ràng buộc được cấp.

### Không dùng dark patterns ở consent

Một UI có nút “Đồng ý” thật lớn và “Không đồng ý” gần như vô hình có thể làm người dùng cấp quyền ngoài ý muốn. Ngoài yêu cầu giao thức, chất lượng quyết định phụ thuộc vào giao diện:

- Dùng ngôn ngữ dễ hiểu, tách rõ quyền đọc và quyền sửa.
- Không gom quyền không liên quan thành một lựa chọn mơ hồ nếu có thể phân quyền hẹp.
- Không gọi consent là “xác minh bảo mật bắt buộc” khi thực tế đang xin quyền truy cập mới.
- Không tự chuyển sang màn hình cấp quyền rộng hơn sau khi user vừa từ chối.
- Cung cấp đường xem lại/thu hồi các ứng dụng đã kết nối.

## 17. Multi-tenant và admin consent: quyết định phải đúng phạm vi

Một user có thể thuộc **tenant-A** và **tenant-B**, nhưng chỉ có quyền admin ở tenant-A. Khi người này chấp thuận app cho tổ chức:

~~~text
subject:      user-42
client:       sales-report-app
tenant:       tenant-A
approved:     orders:read
decision:     tenant-admin-consent
~~~

Không được suy quyết định ấy áp dụng cho tenant-B. Mỗi grant/consent record cần được gắn với **tenant, người có thẩm quyền, quyền và resource** theo chính sách.

**Admin consent không phải quyền truy cập vô điều kiện vào mọi tài nguyên.** Ví dụ tổ chức có thể chấp thuận cho app khả năng gọi Orders API, nhưng Resource Server vẫn kiểm client/service principal, tenant boundary, user delegation (nếu cần) và giới hạn dữ liệu.

Những kiểm tra tối thiểu:

1. Người bấm Approve có đúng **vai trò được phép chấp thuận thay tổ chức** không?
2. Quyền đó thuộc **đúng tenant** và không vượt khỏi chính sách của tổ chức?
3. App có được đăng ký/phê duyệt cho những **scopes và resources** đang xin không?
4. Nếu app cần thao tác thay mặt end user, **sự chấp thuận của admin** có đủ theo policy hay vẫn cần kiểm quyền của user từng request?
5. Khi admin mất quyền hoặc app bị cấm, grant/token có được đánh giá lại/thu hồi phù hợp?

Đừng trộn **user delegation** và **application permission**. Client Credentials grant thường biểu diễn **quyền của service/client**, không tự đại diện cho user. Những quyền application-level có thể cần quy trình cấp phép quản trị, không phải consent của một người dùng bình thường.

## 18. Ví dụ triển khai: state machine và policy evaluation

Một AS có thể biểu diễn authorization transaction như sau:

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED: Client khởi tạo
    REQUESTED --> WAITING_FOR_USER: AS kiểm client/policy
    REQUESTED --> REJECTED: Request không hợp lệ
    WAITING_FOR_USER --> APPROVED: Quyết định chấp thuận hợp lệ
    WAITING_FOR_USER --> DENIED: Từ chối
    WAITING_FOR_USER --> EXPIRED: Quá thời hạn giao dịch
    APPROVED --> CODE_ISSUED: Phát code gắn grant/PKCE
    CODE_ISSUED --> TOKEN_ISSUED: Đổi code hợp lệ, một lần
    CODE_ISSUED --> EXPIRED: Code hết hạn
    DENIED --> [*]
    REJECTED --> [*]
    EXPIRED --> [*]
    TOKEN_ISSUED --> [*]
~~~

Đây là **mô hình khái niệm**, không phải tập trạng thái bắt buộc của OAuth 2.0. Grant có thể tiếp tục tồn tại sau khi code đã dùng, và access/refresh token có vòng đời riêng.

### Pseudocode tại Authorization Server

~~~text
handleConsentDecision(httpRequest, authenticatedSession):
    requireAsSessionAndCsrfProtection(httpRequest, authenticatedSession)
    tx = trustedTransactionStore.lock(httpRequest.transactionId)

    if tx missing or tx.expired or tx.alreadyCompleted:
        rejectWithoutGrant()

    if tx.subject != authenticatedSession.subject:
        rejectWithoutGrant()

    client = trustedClientRegistry.get(tx.clientId)
    require client.active and registeredRedirectMatches(tx.redirectUri)

    eligible = policyEngine.computeMaxAuthorizedScopeAndResource(
        subject = authenticatedSession.subject,
        tenant = tx.tenant,
        client = client,
        resource = tx.requestedResource
    )

    requireDecisionWasShownForSameTransaction(tx, authenticatedSession)
    if httpRequest.decision == DENY:
        tx.atomicallyCompleteAsDenied()
        return authorizationError("access_denied", verifiedRedirectOnly)

    require httpRequest.decision == APPROVE
    approved = intersect(tx.displayedScopes, eligible)
    require approved not empty when policy requires an allowed grant
    grant = tx.atomicallyRecordApproval(
        subject, client.id, tx.tenant, tx.resource, approved
    )
    return issueAuthorizationCodeBoundTo(
        grant, client.id, tx.redirectUri, tx.pkceChallenge
    )
~~~

**Pseudocode thiết kế**, không phải thư viện OAuth hoàn chỉnh. Trong một hệ thống thật, cần kiểm đúng **authorization request**, CSRF, session binding, code single-use, PKCE, redirect URI, issuer, persistence, concurrency và error semantics. Không thể chỉ cho client gửi `approved=true` rồi ký token.

### Tính nguyên tử khi người dùng bấm hai lần

Nếu cùng transaction được gửi **Approve** và **Deny** từ hai tab khác nhau gần như đồng thời, AS cần có **state transition nhất quán**, không phát token từ một nhánh sau khi nhánh kia đã hoàn tất. Nếu giao dịch đang bị thay đổi scope/resource, phải yêu cầu quyết định mới hoặc từ chối, không dùng phê duyệt cũ cho dữ liệu mới.

## 19. Consent và audit: cần ghi gì, không ghi gì?

Để giải quyết khiếu nại “Tôi chưa cấp quyền cho ứng dụng này”, AS có thể cần audit có kiểm soát:

~~~json
{
  "event": "oauth_consent_decision",
  "request_id": "req-example-519",
  "grant_ref": "grant-example-017",
  "client_id": "sales-report-app",
  "subject_ref": "user-42",
  "tenant_ref": "tenant-A",
  "requested_scope_set": "orders-read",
  "decision": "APPROVED",
  "policy_version": "policy-v3",
  "decision_source": "resource_owner"
}
~~~

Các giá trị chỉ minh họa. **subject_ref, tenant_ref và grant_ref** là dữ liệu có khả năng liên kết hoạt động với người dùng; lưu theo mục đích, phân quyền, retention và yêu cầu riêng tư phù hợp. Trường `requested_scope_set` có thể là **nhãn chuẩn hóa** do AS kiểm soát để tránh đưa raw input tùy ý hoặc dữ liệu có độ phân biệt cao vào metrics.

**Không log**:

~~~text
Authorization: Bearer <access-token>
refresh_token=<refresh-token>
id_token=<id-token>
authorization_code=<code>
code_verifier=<pkce-verifier>
client_secret=<secret>
raw-consent-page-with-session-cookies
~~~

Mã lỗi, request ID và grant reference đáng tin thường đủ để tra cứu. Với **JWT access token**, payload JWS có thể đọc được dù chữ ký hợp lệ; không lưu toàn bộ token hoặc claims không cần. **Refresh token có thể duy trì truy cập lâu hơn access token** và cần tránh xuất hiện trong analytics, APM hoặc log.

Không thu thập mọi dữ liệu vì “để sau này audit”; hãy xác định trường cần, ai được xem và xóa khi nào. Một consent record được lưu để chứng minh quyết định **không đồng nghĩa bản sao của access token phải được lưu cùng record**.

## 20. Ba tình huống xuyên suốt

### Tình huống A — Cho ứng dụng đọc báo cáo

User-42 chọn kết nối Sales Report với Orders API.

1. Client xin `orders:read` qua Authorization Code + PKCE.
2. AS kiểm client, redirect URI và quyền tối đa; hiển thị thông tin cho user.
3. User chấp thuận quyền đọc, không chấp thuận quyền sửa.
4. AS ghi nhận grant phù hợp và phát code.
5. Client đổi code tại token endpoint, nhận access token dành cho **orders-api**.
6. Orders API kiểm token và quyền với từng đơn hàng.

**Điểm cần nhớ:** consent quyết định phạm vi được phép cấp, không biến app thành chủ sở hữu mọi đơn hàng.

### Tình huống B — Từ chối quyền quá rộng

Ứng dụng bất ngờ yêu cầu `orders:read payments:charge`. Người dùng chỉ muốn xem báo cáo, nên bấm Từ chối.

- AS không cấp token cho request vừa bị từ chối.
- Client hiển thị tình trạng “Chưa kết nối” thay vì âm thầm xin lại quyền.
- Nếu client muốn cung cấp tính năng chỉ đọc, nó có thể khởi tạo **một request mới với phạm vi hẹp** theo hành động rõ ràng của người dùng.
- Nếu tồn tại grant cũ, việc grant ấy còn hiệu lực hay không theo **quy trình thu hồi/đổi quyền** riêng; Deny request mới không tự xóa mọi token cũ.

### Tình huống C — Người dùng thu hồi consent

Sau một tháng, user-42 vào trang **Ứng dụng đã kết nối** và thu hồi Sales Report.

- AS đánh dấu grant revoked, chặn refresh token hoặc lần cấp token mới liên quan theo policy.
- Ứng dụng bị từ chối khi xin token tiếp theo.
- Access token đang còn hạn cần được xử lý theo thiết kế thu hồi: JWT có thể tiếp tục được chấp nhận tới `exp` nếu RS không có kiểm tra trạng thái bổ sung.
- Nếu ứng dụng đã tải dữ liệu và lưu bên ngoài, **thu hồi OAuth token không tự xóa dữ liệu đã sao chép**; đây là một vấn đề quản trị dữ liệu riêng.

## 21. Ma trận kiểm thử Consent là quyết định cấp quyền

| ID | Trường hợp | Kết quả mong đợi |
|---|---|---|
| **S01** | Client hợp lệ, user có quyền, chấp thuận scope tối thiểu | AS cấp grant/code/token đúng phạm vi nếu các điều kiện khác đạt |
| **S02** | User đã có grant cùng client/scope/resource còn hiệu lực | AS chỉ dùng lại trong giới hạn policy; không tăng quyền |
| **S03** | User từ chối một request hợp lệ | Trả `access_denied` theo flow, không cấp quyền của request đó |
| **S04** | Người dùng xem danh sách app đã cấp quyền và revoke | AS cập nhật grant/trạng thái token theo policy |
| **F01** | User chưa xác thực mà request cần xác thực | Không tự cấp quyền |
| **F02** | Browser gửi `approved=true` nhưng AS chưa có consent transaction hợp lệ | Từ chối |
| **F03** | User bấm Approve với một transaction đã hết hạn | Từ chối, không cấp code/token |
| **F04** | Consent của user A bị áp dụng vào phiên user B | Từ chối |
| **F05** | Consent tenant-A bị áp dụng vào tenant-B | Từ chối |
| **F06** | Client A cố dùng grant/consent của client B | Từ chối |
| **F07** | Client yêu cầu scope ngoài quyền user hoặc ngoài policy | Không cấp scope vượt quyền |
| **F08** | User duyệt `orders:read`, client đổi code để đòi thêm `orders:write` | Không cấp thêm quyền |
| **F09** | Client xin resource/audience chưa được consent/cho phép | Từ chối hoặc yêu cầu flow mới theo policy |
| **F10** | Authorization request có redirect URI chưa đăng ký | Không redirect code/error đến URI không tin cậy |
| **F11** | Code/PKCE verifier sai sau consent thành công | Token endpoint từ chối |
| **F12** | Authorization code đã dùng bị replay | Từ chối; không cấp thêm token |
| **F13** | User chọn Deny nhưng client vẫn nhận access token từ request đó | Test phải phát hiện lỗi nghiêm trọng |
| **F14** | Consent form bị CSRF hoặc clickjacking | Biện pháp CSRF/frame restriction phải chặn đường thao túng |
| **F15** | Hidden input scope được sửa trên trang consent | AS dùng transaction/policy server-side, không cấp quyền bị sửa |
| **F16** | Approve và Deny đồng thời cùng transaction | Một quyết định nhất quán, không tạo grant mâu thuẫn |
| **F17** | Quyền tenant/role của user bị gỡ trước khi cấp token hoặc truy cập API | AS/RS áp dụng policy hiện hành theo yêu cầu |
| **F18** | Access token đúng scope nhưng truy cập order của người khác | Resource Server từ chối |
| **F19** | Token `aud=orders-api` được gửi đến Payments API | Resource Server từ chối sai audience |
| **F20** | Client dùng OIDC ID token như access token | Resource Server từ chối sai loại |
| **F21** | Client dùng refresh token như Bearer ở API | Resource Server từ chối sai loại |
| **F22** | Refresh token bị dùng sau khi grant revoked | Authorization Server từ chối theo revoke policy |
| **F23** | JWT access token cũ sau khi revoke consent | RS hành xử đúng chính sách thu hồi/TTL, không giả định token hết hiệu lực tức thì |
| **F24** | Ứng dụng lạ xin scope rộng và người dùng mở trang consent | Hiển thị tên client, quyền/account/resource đúng, có thể Deny |
| **F25** | OIDC `prompt=consent` hoặc `offline_access` được yêu cầu | Áp dụng quy tắc OIDC/policy, không tự cấp refresh token vô hạn |
| **F26** | Gateway/AS/APM bật debug trong flow consent | Không ghi access/refresh token, code, verifier, session cookie |
| **F27** | Đổi policy version hoặc client registration sau khi consent cũ | Re-evaluate grant theo quy tắc, không tự mở rộng quyền |

**Đánh giá kết quả không chỉ bằng HTTP 200/400.** Với một negative test, cần kiểm **authorization grant không bị mở rộng, không phát token mới hợp lệ và Resource Server không thực hiện hành động bị cấm**. Một HTTP response lỗi vẫn có thể che một side effect ghi grant/token trái phép nếu transaction không được thiết kế nhất quán.

### Kiểm thử một quyết định Deny

~~~text
Given:
  client = sales-report-app
  user = user-42, đã xác thực
  requested scope = orders:read
  authorization transaction còn hạn

When:
  user bấm Deny

Then:
  AS ghi nhận kết quả từ chối đúng transaction
  authorization response có error=access_denied nếu redirect hợp lệ
  không có authorization code/token mới cho request bị từ chối
  không lưu refresh token cho request bị từ chối
  audit ghi decision an toàn, không ghi session/token thô
~~~

## 22. Checklist trước khi triển khai màn hình Consent

1. **Tách trách nhiệm:** Có phân biệt user authentication, consent, grant, token issuance và API authorization?
2. **Thẩm quyền:** Người hoặc cơ chế đưa ra quyết định có thực sự được quyền consent cho client/resource/tenant đó?
3. **Trusted client:** Tên, publisher, client_id và redirect URI đến từ registration đáng tin, không từ query tùy ý?
4. **Hiển thị rõ:** User biết chính app, tài khoản, resource, scope/quyền và rủi ro chính được xin?
5. **Từ chối:** Có nút Deny rõ, không ép dùng dark patterns hay tự retry sau khi bị từ chối?
6. **Least privilege:** Client xin quyền tối thiểu, AS kiểm giới hạn, token được cấp scope/audience phù hợp?
7. **Consent reuse:** Grant cũ chỉ được dùng lại trong phạm vi đã phê duyệt, còn hiệu lực và đúng policy?
8. **Scope expansion:** Client xin quyền/resource mới có cần quyết định lại theo policy, không mở rộng ngầm?
9. **Session binding:** Approve/Deny được gắn đúng user/account/tenant và authorization transaction?
10. **CSRF/clickjacking:** Form consent có CSRF protection, CSP/frame restrictions và chống double submit?
11. **OAuth flow:** Authorization Code + PKCE có exact redirect matching, state, issuer binding và code single-use?
12. **OIDC:** Có phân biệt ID token, `prompt=consent`, `offline_access` và access token của API?
13. **Token issuance:** Token endpoint kiểm grant/client/PKCE, scope/resource, refresh policy trước khi cấp?
14. **RS authorization:** API xác minh issuer, audience, token type, thời hạn, scope và quyền tài nguyên hiện hành?
15. **Revoke:** Có khả năng disconnect/revoke grant, refresh token và xử lý access token còn hạn?
16. **Multi-tenant:** User/admin consent chỉ áp dụng trong tenant và quyền được phép?
17. **Anti-phishing:** Có nhận diện client rõ, cảnh báo app lạ và quyền nhạy cảm, giám sát consent bất thường?
18. **Audit:** Ghi đúng decision, client, scope/resource, subject/tenant, version và thời điểm với bảo vệ quyền riêng tư?
19. **Secret hygiene:** Không log authorization code, PKCE verifier, access/refresh/ID tokens, session cookie hoặc raw JWT?
20. **Negative tests:** Đã kiểm Deny, CSRF, replay, stale grant, sai tenant/audience, scope escalation, revoked consent và token leak?

## 23. Câu hỏi tự đánh giá

**1. Consent trong OAuth có phải là đăng nhập không?** Không. Authentication xác minh danh tính; consent thể hiện quyết định cấp quyền trong một ngữ cảnh, khi flow/policy yêu cầu.

**2. User bấm Allow thì ứng dụng có được đọc mọi tài nguyên không?** Không. Quyền vẫn bị giới hạn bởi user, client, scope, audience, tenant và policy của Resource Server.

**3. OAuth 2.0 có bắt buộc mọi lần cấp token phải hiện màn hình consent không?** Không. AS có thể áp dụng grant đã có, policy được ủy quyền hoặc những flow không có end user consent screen như Client Credentials.

**4. Requested scope có tự trở thành granted scope không?** Không. AS phải kiểm quyền tối đa và quyết định phê duyệt; có thể từ chối hoặc giới hạn theo hợp đồng.

**5. Khi user bấm Deny, AS có được phát access token cho quyền vừa bị từ chối không?** Không. Request bị từ chối không được cấp quyền đó; không mặc định việc Deny thu hồi mọi token/grant cũ.

**6. Consent OAuth có tự đáp ứng mọi nghĩa vụ đồng ý xử lý dữ liệu theo luật không?** Không. Đó là hai phạm vi cần đánh giá riêng theo bối cảnh.

**7. OIDC ID token có thể dùng để gọi Resource Server sau khi user consent không?** Không. ID token dành cho client xác minh đăng nhập; API cần access token đúng audience.

**8. Vì sao trang đăng nhập thuộc domain AS thật vẫn có thể là consent phishing?** Attacker có thể đăng ký client của mình và dụ user cấp quyền cho chính client đó trên trang AS thật.

**9. Thu hồi consent có làm JWT access token cũ hết hiệu lực tức thì không?** Không mặc định. Cần cơ chế thu hồi sớm hoặc chấp nhận thời gian còn hiệu lực theo policy, trong khi refresh token/grant được xử lý riêng.

**10. Một admin consent cho tenant A có thể cấp quyền cho tenant B không?** Không, nếu admin không có thẩm quyền đối với tenant B. Quyết định phải ràng buộc đúng tenant/client/scope/resource.

**11. `prompt=consent` hoặc `offline_access` có tự cho phép client nhận refresh token lâu dài không?** Không. OIDC/AS vẫn áp dụng flow, consent và chính sách phát hành/thu hồi riêng.

**12. Một test Deny thành công chỉ cần nhận `access_denied` là đủ chưa?** Chưa. Cần kiểm không có grant hay token mới được cấp trái phép và không có API side effect.

**Ghi nhớ:** **Consent là quyết định cấp quyền trong một ngữ cảnh tin cậy**, không phải bằng chứng đã đăng nhập và cũng không phải token. AS phải kết hợp **đúng chủ thể có thẩm quyền, client, scope, resource, tenant, trạng thái grant và policy** trước khi phát hành credential; người dùng phải hiểu mình đang cho ứng dụng nào quyền gì và có đường **từ chối/thu hồi**. Khi token được cấp, Resource Server vẫn phải xác minh **issuer, audience, thời hạn, scope và quyền đối với tài nguyên cụ thể**. Bảo vệ consent chính là bảo vệ **cả quyết định ủy quyền lẫn việc thực thi quyền sau quyết định ấy**.
