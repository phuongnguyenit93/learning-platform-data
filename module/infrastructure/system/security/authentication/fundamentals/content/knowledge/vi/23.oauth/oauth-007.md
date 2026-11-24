# Scope và consent

## 1. Scope trong OAuth là gì?

Trong OAuth 2.0, **scope** là chuỗi định danh quyền truy cập mà client yêu cầu authorization server (AS) cấp cho một access token. Scope mô tả client muốn thực hiện loại thao tác nào đối với tài nguyên được bảo vệ, ví dụ đọc hồ sơ, xem đơn hàng hoặc tạo báo cáo.

Ví dụ một ứng dụng quản lý đơn hàng cần:

- `orders.read` để đọc đơn hàng.
- `orders.write` để tạo hoặc cập nhật đơn hàng.
- `customers.read` để xem thông tin khách hàng.

Client gửi các scope cần thiết trong authorization request. AS kiểm tra chính sách, quyền của người dùng, cấu hình client và yêu cầu consent nếu cần. Token được cấp có thể mang toàn bộ hoặc một tập con scope được yêu cầu. Resource server (RS/API) phải kiểm tra scope thực tế của token trước khi thực hiện thao tác.

Scope không phải là một vai trò người dùng, cũng không tự động là một quyền được thực thi. Nó là một phần của mô hình ủy quyền OAuth mà AS và RS cùng phải hiểu theo hợp đồng đã thống nhất.

| Thành phần | Vai trò liên quan tới scope |
| --- | --- |
| **Resource owner** | Người dùng hoặc chủ thể có quyền cho phép client truy cập tài nguyên. |
| **Client** | Yêu cầu scope để thực hiện chức năng cần thiết. |
| **Authorization server (AS)** | Kiểm tra client, người dùng, chính sách và quyết định scope được cấp. |
| **Resource server (RS)** | Kiểm tra access token và scope trước khi cho phép thao tác API. |
| **Consent UI** | Giải thích cho người dùng loại quyền mà client đang yêu cầu, khi consent được áp dụng. |

Trong module `SECURITY_AUTHENTICATION_FUNDAMENTALS`, scope và consent là phần quan trọng của ranh giới tin cậy: người dùng có thể cho phép một client yêu cầu quyền, nhưng ứng dụng vẫn phải kiểm tra quyền theo tài nguyên, tenant, chính sách và trạng thái hiện tại.

## 2. Scope không đồng nghĩa với role hoặc identity claim

Ba khái niệm này có liên quan nhưng trả lời các câu hỏi khác nhau:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Scope** | Client được phép yêu cầu loại truy cập API nào theo authorization grant/token? | `invoices.read`, `payments.create`. |
| **Role** | Chủ thể thuộc nhóm trách nhiệm hoặc chức năng nào trong hệ thống? | `billing-admin`, `support-agent`. |
| **Identity claim** | Người dùng là ai hoặc có thuộc tính nào? | `sub`, `email`, `department`. |

Một người dùng có role `billing-admin` không có nghĩa mọi client đều tự động nhận scope `payments.write`. AS phải đánh giá client, resource, người dùng và chính sách. Tương tự, một token chứa scope `invoices.read` không chứng minh người dùng có quyền đọc mọi hóa đơn trong mọi tenant. RS vẫn phải kiểm tra quyền trên đối tượng cụ thể.

Scope cũng không phải permission engine hoàn chỉnh. Một API thường cần kết hợp:

- Scope token: loại thao tác client được cấp.
- Principal/user: người dùng hoặc service đứng sau request.
- Tenant/resource ownership: tài nguyên thuộc tổ chức hoặc chủ thể nào.
- Policy nghiệp vụ: trạng thái, giới hạn, phân tách nhiệm vụ và điều kiện bổ sung.

Ví dụ: token có `orders.read` cho phép gọi chức năng đọc đơn hàng, nhưng RS vẫn phải xác định đơn hàng có thuộc tenant mà principal được truy cập hay không.

## 3. Cú pháp và ngữ nghĩa của scope

Trong OAuth 2.0, tham số `scope` là một danh sách các scope value được phân tách bằng dấu cách. Scope value là chuỗi do authorization server và resource server định nghĩa; OAuth core không quy định một danh mục scope dùng chung cho mọi API.

Ví dụ:

~~~http
scope=orders.read%20customers.read
~~~

Các nguyên tắc quan trọng:

- Scope value phân biệt chữ hoa/chữ thường theo quy tắc của OAuth.
- Mỗi giá trị scope là một đơn vị riêng; dấu cách phân tách các giá trị.
- Ý nghĩa và quyền cụ thể của từng scope do AS/RS công bố và thực thi.
- Không giả định scope có thứ bậc hoặc kế thừa nếu hệ thống không định nghĩa rõ.
- Không tự hiểu `admin`, `read` hoặc `write` theo nghĩa phổ quát; ngữ nghĩa phải thuộc hợp đồng API.

Ví dụ, `orders.read` và `orders.write` có thể là hai scope độc lập. Có scope `orders.write` không nhất thiết ngụ ý có `orders.read`, trừ khi chính sách của hệ thống nói rõ như vậy.

### 3.1. Đặt tên scope có chủ đích

Một quy ước đặt tên dễ hiểu thường biểu diễn tài nguyên và hành động:

| Scope | Ý nghĩa dự kiến |
| --- | --- |
| `profile.read` | Đọc một tập thông tin hồ sơ được định nghĩa. |
| `orders.read` | Đọc đơn hàng trong phạm vi được phép. |
| `orders.create` | Tạo đơn hàng. |
| `orders.cancel` | Hủy đơn hàng theo chính sách nghiệp vụ. |
| `reports.export` | Xuất báo cáo, có thể chứa dữ liệu nhạy cảm. |
| `users.manage` | Quản lý người dùng, cần kiểm soát chặt. |

Tên scope nên ổn định, cụ thể, có tài liệu và không gây hiểu nhầm. Tránh một scope rộng như `all` hoặc `full_access` nếu client chỉ cần một vài thao tác. Nếu cần thay đổi ngữ nghĩa, hãy quản lý phiên bản hoặc định nghĩa tương thích rõ ràng; không âm thầm đổi quyền mà client cũ đang dựa vào.

### 3.2. Scope không tự mang ý nghĩa giữa các API

Hai hệ thống có thể cùng dùng tên `profile.read` nhưng định nghĩa tập dữ liệu khác nhau. Không nên chuyển token hoặc scope giữa hai resource server nếu audience và hợp đồng không cho phép.

Một scope phải được hiểu trong ngữ cảnh issuer, client, resource/audience và chính sách tương ứng. RS không được chấp nhận một scope chỉ vì chuỗi của nó trông quen thuộc.

## 4. Scope trong authorization request

Trong Authorization Code Flow, client gửi authorization request tới AS. Ví dụ minh họa:

~~~http
GET /authorize?
  response_type=code&
  client_id=web-portal&
  redirect_uri=https%3A%2F%2Fportal.example.test%2Fcallback&
  scope=orders.read%20profile&
  state=random-state-value&
  code_challenge=BASE64URL_CHALLENGE&
  code_challenge_method=S256
~~~

Các thành phần chính:

- `client_id` nhận diện client đã đăng ký.
- `redirect_uri` phải khớp URI được đăng ký theo quy tắc của AS.
- `scope` liệt kê quyền client cần.
- `state` giúp client tương quan phản hồi và bảo vệ luồng trước CSRF.
- `code_challenge` và `code_challenge_method` hỗ trợ PKCE, ràng buộc authorization code với client giữ code verifier.

Ví dụ chỉ minh họa cấu trúc. Client phải dùng thư viện OAuth/OIDC phù hợp và tạo giá trị ngẫu nhiên đúng chuẩn; không dùng chuỗi cố định cho state hoặc PKCE.

AS có thể:

1. Xác minh client và redirect URI.
2. Kiểm tra scope có được client đăng ký yêu cầu không.
3. Xác thực người dùng nếu chưa có session.
4. Áp dụng policy theo người dùng, tenant, resource và rủi ro.
5. Xác định có cần hiển thị consent hay không.
6. Cấp authorization code với grant và scope đã được quyết định.

Việc client gửi scope chỉ là **yêu cầu**. Client không thể tự cấp quyền cho mình bằng cách thêm một scope bất kỳ vào URL.

## 5. Scope được cấp có thể khác scope được yêu cầu

AS không nhất thiết cấp toàn bộ scope client yêu cầu. Chính sách có thể giới hạn theo:

- Quyền người dùng hiện có.
- Scope client được phép yêu cầu theo đăng ký.
- Consent đã cấp hoặc bị thu hồi.
- Loại tài nguyên, audience và tenant.
- Mức độ nhạy cảm, rủi ro hoặc yêu cầu step-up.
- Chính sách tổ chức và loại grant.

Ví dụ:

~~~text
Client yêu cầu:
  orders.read orders.write customers.read

AS quyết định cấp:
  orders.read customers.read

Client không được mặc định rằng orders.write đã được cấp.
~~~

Trong OAuth 2.0, token response có thể chứa trường `scope`. Nếu scope được cấp giống hệt scope yêu cầu, trường này có thể được lược bỏ theo quy tắc chuẩn; nếu scope được cấp khác với scope yêu cầu, authorization server phải trả scope thực tế được cấp. Client nên xử lý trường hợp bị giảm quyền và không giả định request luôn được cấp đầy đủ.

Resource server phải dựa trên scope thực tế trong access token hoặc kết quả introspection, không dựa vào scope mà client từng yêu cầu.

## 6. Consent là gì?

**Consent** là quyết định cho phép client truy cập một tập dữ liệu hoặc thực hiện một nhóm hành động thay mặt resource owner, theo cách trình bày và quy trình do AS cung cấp. Consent thường xuất hiện khi người dùng kết nối một ứng dụng bên thứ ba với tài khoản của mình.

Ví dụ, một ứng dụng lập ngân sách yêu cầu:

- Đọc số dư tài khoản.
- Đọc lịch sử giao dịch.
- Không yêu cầu chuyển tiền.

Consent UI cần giải thích rõ ứng dụng nào đang yêu cầu quyền, dữ liệu nào sẽ được truy cập, hành động nào có thể thực hiện, phạm vi thời gian hoặc mục đích nếu có, và cách thu hồi quyền.

Consent không phải là một nút “đồng ý” chung chung. Một màn hình yêu cầu `full access` mà không giải thích quyền cụ thể khiến người dùng không thể đánh giá rủi ro.

### 6.1. Consent không thay thế policy của AS

Người dùng đồng ý không có nghĩa AS phải cấp mọi scope. AS có thể từ chối scope bị cấm, scope không được client đăng ký, scope yêu cầu quyền quản trị hoặc scope không phù hợp với tenant/policy.

Tương tự, consent không thay thế authorization tại RS. RS vẫn phải kiểm tra token, scope, principal, tenant, ownership và điều kiện nghiệp vụ ở mỗi request.

### 6.2. Consent không phải xác thực danh tính

Consent trả lời người dùng có cho phép client yêu cầu quyền hay không. Authentication xác minh chủ thể đang đăng nhập là ai hoặc đang kiểm soát credential nào. Hai quy trình có thể diễn ra trong cùng một luồng browser nhưng có mục đích khác nhau.

Một session IdP đang đăng nhập không tự chứng minh người dùng đã đọc hoặc chấp thuận consent mới. Với scope nhạy cảm, AS có thể yêu cầu xác thực lại hoặc step-up trước khi ghi nhận consent.

## 7. Thiết kế consent screen dễ hiểu

Một consent screen tốt nên cho người dùng thấy:

| Thành phần | Nội dung cần hiển thị |
| --- | --- |
| Client identity | Tên ứng dụng, nhà phát triển hoặc tổ chức phát hành đã được xác minh theo chính sách. |
| Resource | Dữ liệu hoặc dịch vụ mà ứng dụng muốn truy cập. |
| Actions | Đọc, tạo, sửa, xóa, chia sẻ hoặc thực hiện giao dịch. |
| Scope detail | Giải thích bằng ngôn ngữ người dùng, không chỉ hiện chuỗi kỹ thuật. |
| Duration | Thời gian quyền có hiệu lực hoặc cách token/session hết hạn, nếu hệ thống có thể mô tả chính xác. |
| Revocation | Nơi người dùng có thể xem và thu hồi quyền đã cấp. |
| Decision | Chấp thuận hoặc từ chối rõ ràng; không dùng nút gây nhầm lẫn. |

Ví dụ nội dung:

~~~text
Ứng dụng: Budget Planner

Ứng dụng muốn:
  [x] Xem số dư tài khoản
  [x] Đọc lịch sử giao dịch
  [ ] Thực hiện chuyển tiền

Ứng dụng không được cấp quyền chuyển tiền trong yêu cầu này.

[Từ chối]  [Cho phép truy cập]
~~~

Đây là ví dụ giao diện, không phải danh sách scope tiêu chuẩn. UI nên hiển thị đúng những quyền AS định cấp, không chỉ lặp lại nội dung client gửi.

Không dùng dark pattern như nút từ chối khó tìm, mặc định chọn scope nhạy cảm, mô tả quyền mơ hồ hoặc gây áp lực để người dùng đồng ý.

## 8. Ghi nhận và quản lý consent

Nếu AS lưu consent lâu dài, bản ghi nên đủ thông tin để biết ai đã chấp thuận điều gì, cho client nào, trong ngữ cảnh nào và theo phiên bản policy nào.

Một bản ghi khái niệm:

~~~json
{
  "consentId": "consent_123",
  "subject": "user_42",
  "clientId": "budget-planner",
  "resource": "banking-api",
  "scopes": ["balance.read", "transactions.read"],
  "grantedAt": "2026-11-22T10:00:00Z",
  "policyVersion": "consent-ui-v3",
  "status": "active"
}
~~~

Các trường cụ thể tùy sản phẩm và yêu cầu pháp lý. Bản ghi cần bảo vệ tính toàn vẹn, tenant isolation, thời hạn lưu giữ và quyền truy cập. Không lưu dữ liệu vượt quá nhu cầu chỉ để tạo lịch sử chi tiết.

AS có thể dùng consent record để quyết định scope nào có thể cấp lại mà không hỏi người dùng lần nữa. Tuy nhiên, cần yêu cầu consent lại khi:

- Client yêu cầu scope mới hoặc quyền nhạy cảm hơn.
- Ngữ nghĩa scope thay đổi đáng kể.
- Client identity hoặc publisher thay đổi theo cách ảnh hưởng niềm tin.
- Consent đã hết hạn hoặc bị thu hồi.
- Policy hoặc quy định yêu cầu xác nhận lại.

Consent cũ không nên được diễn giải rộng hơn những gì người dùng đã chấp thuận ban đầu.

## 9. Incremental authorization và least privilege

**Incremental authorization** là cách yêu cầu thêm scope khi người dùng bắt đầu dùng một tính năng cần quyền mới, thay vì xin mọi quyền ngay lần đầu cài đặt hoặc đăng nhập.

Ví dụ:

1. Người dùng kết nối ứng dụng và chỉ cấp `profile.read`.
2. Sau đó họ chọn “Xuất báo cáo giao dịch”.
3. Client bắt đầu một authorization request mới để xin `transactions.read`.
4. AS giải thích quyền mới và yêu cầu consent nếu policy cần.
5. Client nhận token có scope được cấp và thực hiện tính năng.

Lợi ích:

- Giảm quyền mà client giữ khi người dùng chưa cần tính năng.
- Consent screen ngắn và dễ hiểu hơn.
- Giới hạn tác động nếu client bị xâm nhập.
- Cho phép người dùng đánh giá quyền tại thời điểm họ hiểu mục đích sử dụng.

Incremental authorization vẫn phải dùng state/PKCE, redirect URI hợp lệ và kiểm tra scope ở RS. Không nên âm thầm mở rộng scope của token đang tồn tại.

## 10. Scope trong access token và resource server

Access token có thể là token opaque hoặc JWT. Cách biểu diễn scope phụ thuộc profile và nhà cung cấp:

- Token opaque: RS thường gọi introspection endpoint hoặc cơ chế xác minh nội bộ để biết token active, client, subject, audience và scope.
- JWT access token: scope có thể nằm trong claim `scope` dưới dạng chuỗi phân tách bằng dấu cách hoặc claim khác theo profile/provider. Không tự giả định tên claim nếu chưa có hợp đồng.

Ví dụ payload JWT minh họa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user_42",
  "aud": "orders-api",
  "client_id": "web-portal",
  "scope": "orders.read customers.read",
  "exp": 1795345200
}
~~~

Đây chỉ là ví dụ claim, không phải schema bắt buộc cho mọi access token. RS cần xác minh chữ ký hoặc introspection, issuer, audience, thời hạn, trạng thái và scope theo profile thực tế.

Ví dụ logic authorization:

~~~ts
function canReadOrder(token, order) {
  const scopes = new Set(token.scope.split(" "));

  if (!scopes.has("orders.read")) return false;
  if (token.tenant_id !== order.tenantId) return false;
  if (!policyAllows(token.sub, "order:read", order)) return false;

  return true;
}
~~~

Đây là pseudocode minh họa. Production cần xử lý định dạng scope an toàn, kiểm tra token trước đó, tenant claim tin cậy và policy engine thực tế. Không dùng dữ liệu do request body tự khai để xác định tenant hoặc principal.

**Không chỉ kiểm tra scope ở client.** UI có thể ẩn nút khi thiếu quyền để cải thiện trải nghiệm, nhưng RS phải là nơi thực thi authorization cuối cùng.

## 11. Scope, audience và resource

Scope mô tả loại quyền; audience/resource xác định token dành cho API hoặc dịch vụ nào. Hai yếu tố bổ sung cho nhau:

| Kiểm soát | Ví dụ câu hỏi |
| --- | --- |
| Scope | Token có quyền đọc đơn hàng không? |
| Audience | Token có được phát cho Orders API không? |
| Subject/client | Ai hoặc client nào đang sử dụng token? |
| Tenant/resource policy | Đơn hàng cụ thể có thuộc phạm vi được phép không? |

Một token có scope `orders.read` nhưng audience là `reports-api` không nên được chấp nhận tại Orders API. Tương tự, token dành cho đúng API nhưng không có scope cần thiết vẫn phải bị từ chối.

OAuth Resource Indicators cho phép client chỉ rõ resource/audience dự kiến trong authorization request theo cơ chế tương ứng. Dù dùng cơ chế nào, AS phải kiểm tra resource hợp lệ và RS phải xác minh token được phát cho chính nó.

## 12. Scope đặc biệt trong OpenID Connect

OpenID Connect xây dựng lớp xác thực danh tính trên OAuth 2.0. OIDC định nghĩa một số scope chuẩn để yêu cầu thông tin danh tính:

| Scope OIDC | Ý nghĩa khái quát |
| --- | --- |
| `openid` | Bắt buộc để yêu cầu OIDC authentication và nhận ID Token. |
| `profile` | Yêu cầu một nhóm claim hồ sơ chuẩn, tùy dữ liệu được cung cấp. |
| `email` | Yêu cầu claim email và trạng thái xác minh email nếu có. |
| `address` | Yêu cầu thông tin địa chỉ theo claim chuẩn. |
| `phone` | Yêu cầu số điện thoại và trạng thái xác minh nếu có. |
| `offline_access` | Yêu cầu khả năng nhận refresh token để truy cập khi người dùng không hiện diện, theo policy và điều kiện OIDC. |

Các scope OIDC này không thay thế scope API nghiệp vụ. Ví dụ `openid profile email` yêu cầu thông tin xác thực/danh tính; nó không tự cấp quyền `orders.read` hoặc `payments.create`.

ID Token dành cho client để biểu diễn kết quả xác thực theo OIDC. Access token dành cho resource server. Không gửi ID Token tới API như thể đó là access token, và không dùng claim email thay cho authorization.

## 13. Consent và các loại client/grant

Consent không phải lúc nào cũng có giao diện người dùng. Cách xử lý phụ thuộc loại client, quan hệ giữa người dùng và tổ chức, grant type và policy:

- **Ứng dụng bên thứ ba:** thường cần consent rõ ràng từ resource owner cho các quyền truy cập.
- **Ứng dụng first-party:** tổ chức có thể áp dụng consent ngầm định hoặc policy khác, nhưng vẫn cần minh bạch và kiểm soát scope.
- **Service-to-service/client credentials:** thường không có người dùng cuối trong luồng. Quyền được cấp dựa trên client identity, đăng ký, policy quản trị và scope được phép; không giả lập màn hình consent người dùng.
- **Thiết bị hoặc ứng dụng native:** UX consent phải phù hợp nền tảng, nhưng authorization request vẫn cần được bảo vệ theo OAuth/OIDC.

Không nên đưa mọi grant vào cùng một mô hình “người dùng bấm Allow”. Client credentials không có resource owner người dùng cuối để consent trong flow đó; quản trị viên hoặc chủ hệ thống có thể cấp quyền cho workload qua quy trình khác.

## 14. Thu hồi consent và vòng đời quyền

Khi người dùng thu hồi consent, AS cần xác định tác động tới:

- Consent record.
- Refresh token và token family liên quan.
- Access token còn hiệu lực.
- Session hoặc grant đang tồn tại.
- Client có quyền tiếp tục yêu cầu token hay không.

Thu hồi consent không tự động vô hiệu hóa JWT access token tự chứa tại mọi RS nếu RS chỉ kiểm tra chữ ký và claim tĩnh. Hệ thống cần chính sách token lifetime, introspection, denylist, token version hoặc cơ chế thu hồi khác nếu cần hiệu lực gần như tức thời.

Các bước quản lý:

1. Hiển thị danh sách ứng dụng đã kết nối, client identity và quyền đã cấp.
2. Cho phép thu hồi toàn bộ grant hoặc một phần scope nếu hệ thống hỗ trợ an toàn.
3. Đánh dấu consent inactive và ngăn cấp token mới dựa trên grant đã thu hồi.
4. Thu hồi refresh token liên quan.
5. Xử lý access token đang còn hạn theo chính sách.
6. Ghi audit event và thông báo thay đổi quan trọng khi phù hợp.

Không nên chỉ ẩn ứng dụng khỏi giao diện mà vẫn giữ refresh token hoạt động.

## 15. Các lỗi bảo mật thường gặp

| Lỗi | Hậu quả | Kiểm soát |
| --- | --- | --- |
| Client tự chọn scope bất kỳ và AS cấp không kiểm tra | Client vượt quyền đã đăng ký hoặc policy. | Allowlist scope theo client/resource và kiểm tra policy. |
| RS tin scope client yêu cầu thay vì token | Request có thể vượt quyền thực tế được cấp. | Kiểm tra scope trong token/introspection. |
| Dùng một scope quá rộng | Token bị lộ có tác động lớn. | Scope nhỏ, least privilege và incremental authorization. |
| Coi scope là role | Nhầm quyền client với vai trò người dùng. | Kết hợp scope với principal, tenant và policy. |
| Không kiểm tra audience | Token cho API khác được dùng tại RS. | Xác minh audience/resource. |
| Consent UI mô tả mơ hồ | Người dùng đồng ý mà không hiểu dữ liệu/hành động. | Hiển thị tên client, dữ liệu, hành động và phạm vi rõ ràng. |
| Ghi consent quá rộng hoặc không có version | Consent cũ bị diễn giải cho quyền mới. | Lưu scope, resource, client, policy version và thời điểm. |
| Tự động cấp scope nhạy cảm trong incremental flow | Người dùng không được hỏi khi quyền tăng. | Yêu cầu consent/step-up theo policy. |
| Thu hồi consent nhưng giữ refresh token | Client tiếp tục lấy access token mới. | Thu hồi grant và token family liên quan. |
| Nghĩ logout/consent revoke làm JWT biến mất ngay | RS vẫn chấp nhận token tới exp. | TTL ngắn hoặc cơ chế kiểm tra trạng thái/denylist. |
| Dùng email hoặc profile claim làm quyền | Claim danh tính bị dùng sai cho authorization. | Policy dựa trên subject ổn định và dữ liệu quyền tin cậy. |
| Consent cho service client như người dùng cuối | Mô hình quyền không phản ánh workload ownership. | Cấp quyền qua admin/policy cho client credentials. |

## 16. Ví dụ thiết kế: ứng dụng báo cáo doanh nghiệp

Một công ty dùng cổng đăng nhập tập trung và API báo cáo. Nhân viên kết nối ứng dụng Report Builder để xem số liệu bán hàng.

**Yêu cầu ban đầu:**

- Client yêu cầu `reports.read`.
- AS xác minh client đã đăng ký scope này và nhân viên thuộc tenant có quyền dùng ứng dụng.
- Consent screen giải thích ứng dụng sẽ đọc dữ liệu báo cáo, không được tạo hoặc sửa giao dịch.
- AS cấp authorization code; client đổi code bằng PKCE để nhận access token.
- Token có audience là Reports API và scope được cấp.
- Reports API xác minh token, scope, tenant và quyền đọc báo cáo cụ thể.

**Khi người dùng muốn xuất dữ liệu:**

1. Người dùng chọn chức năng export.
2. Client yêu cầu thêm `reports.export` qua incremental authorization.
3. AS kiểm tra policy và hiển thị consent/step-up nếu cần.
4. Token mới chỉ có scope export nếu được cấp.
5. API kiểm tra cả scope export, quyền dữ liệu, tenant và hạn chế tải dữ liệu.

**Khi người dùng thu hồi ứng dụng:**

- AS đánh dấu consent/grant inactive và ngăn refresh token lấy token mới.
- Refresh token liên quan bị thu hồi.
- Access token hiện có được xử lý theo chính sách token lifetime/revocation.
- Audit log ghi client, subject, scope và thời điểm thu hồi, không ghi token plaintext.

Ví dụ này cho thấy consent xác lập sự cho phép của người dùng theo policy; scope giới hạn loại thao tác client có thể yêu cầu; RS vẫn quyết định truy cập tài nguyên cụ thể.

## 17. Checklist thiết kế scope và consent

Trước khi triển khai OAuth authorization, hãy kiểm tra:

1. Scope có mô tả rõ tài nguyên và hành động không?
2. Mỗi client chỉ được yêu cầu những scope đã đăng ký và phù hợp với mục đích không?
3. AS có kiểm tra quyền người dùng, tenant, resource, client và policy trước khi cấp không?
4. Scope được cấp thực tế có được trả về và xử lý đúng khi khác scope yêu cầu không?
5. RS có xác minh issuer, audience, token status, expiry và scope thực tế không?
6. RS có kết hợp scope với subject, tenant, ownership và policy nghiệp vụ không?
7. Có tránh dùng scope như role hoặc identity claim không?
8. Consent screen có hiển thị client identity, dữ liệu, hành động, phạm vi và cách thu hồi không?
9. Consent record có gắn đúng subject, client, resource, scope, thời điểm và policy version không?
10. Scope mới hoặc nhạy cảm có kích hoạt consent/step-up theo policy không?
11. Incremental authorization có dùng state/PKCE và không tự mở rộng token cũ không?
12. Consent revoke có ngăn token mới, thu hồi refresh token và xử lý access token đang tồn tại không?
13. Client credentials và service-to-service có được cấp quyền qua policy quản trị phù hợp thay vì giả consent người dùng không?
14. Có audit, rate limit, cảnh báo scope bất thường và kiểm thử truy cập chéo tenant không?

**Kết luận:** Scope mô tả quyền truy cập client yêu cầu và được cấp trong OAuth; consent ghi nhận sự cho phép của resource owner theo chính sách của authorization server. Client chỉ yêu cầu scope, AS quyết định scope được cấp, còn resource server phải xác minh token và kiểm tra quyền trên tài nguyên thực tế. Thiết kế scope nhỏ, consent dễ hiểu, audience đúng, incremental authorization và thu hồi token/grant rõ ràng giúp giảm quyền dư thừa và giới hạn tác động khi client bị xâm nhập.
