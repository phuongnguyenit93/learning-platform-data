# Scope quá rộng và nguy cơ over-privilege

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích vì sao **scope được cấp vượt nhu cầu thực tế** làm tăng thiệt hại tiềm tàng khi access token hoặc client bị xâm nhập.
- Phân biệt scope mà client **yêu cầu**, scope mà Authorization Server **cấp**, và scope mà Resource Server **thực thi**.
- Thiết kế phạm vi quyền truy cập theo nguyên tắc **least privilege** trong OAuth 2.0/OIDC.
- Nhận ra các dạng cấp quyền quá rộng: wildcard, scope quản trị, token dùng chung nhiều API, quyền ghi khi chỉ cần đọc và scope tồn tại quá lâu.
- Kết hợp kiểm tra scope với audience, permission, tenant, thời hạn token và thu hồi quyền để ngăn truy cập vượt phép.

## 1. Vấn đề: token có nhiều quyền hơn nhiệm vụ cần thiết

Một ứng dụng báo cáo chỉ cần hiển thị tổng hợp số đơn hàng, nhưng lại được cấp access token chứa các scope:

~~~text
reports:read orders:read orders:write customers:read payments:refund admin:all
~~~

Nếu token này bị sao chép từ log, trình duyệt hoặc một máy chủ, bên nắm giữ có thể **thử** truy cập nhiều endpoint hơn chức năng báo cáo thực sự cần. Những hành động có thành công không còn phụ thuộc audience, permission và các chính sách của Resource Server, nhưng số thao tác có thể bị thử đã tăng lên không cần thiết.

Đây là một dạng **over-privilege**: một principal, client hoặc token được cấp khả năng truy cập rộng hơn mức cần thiết cho nhiệm vụ. Trong OAuth 2.0, scope rộng là dấu hiệu đáng kiểm tra vì scope biểu thị phạm vi truy cập được cấp cho client/token.

| Thiết kế | Scope được cấp | Tác động nếu bearer token bị lộ |
| --- | --- | --- |
| Phù hợp nhiệm vụ | **reports:read** | Token chỉ mở phạm vi yêu cầu đọc báo cáo; API vẫn phải kiểm tra quyền hiện hành. |
| Quá rộng | **reports:read orders:write payments:refund admin:all** | Nếu các điều kiện khác cho phép, bản sao token có thể được dùng thử cho cả thao tác sửa và hoàn tiền. |

Các tên scope trên là ví dụ tự định nghĩa, **không phải giá trị chuẩn bắt buộc của OAuth 2.0**. Mức thiệt hại thực sự phụ thuộc chính sách cấp quyền và cách API thực thi.

> Nguyên tắc: Chỉ cấp khả năng truy cập cần thiết cho **tác vụ, đối tượng nhận và khoảng thời gian hiện tại**. Token có chữ ký đúng không đồng nghĩa token nên mang mọi quyền có thể có.

## 2. Scope là gì và khác permission, role ra sao?

Theo OAuth 2.0 (RFC 6749), scope biểu thị phạm vi truy cập client yêu cầu và được Authorization Server chấp thuận. Khi biểu diễn trong tham số scope chuẩn, các giá trị là những chuỗi phân tách bằng dấu cách, chẳng hạn:

~~~text
scope = "orders:read orders:approve"
~~~

OAuth không tự định nghĩa ý nghĩa của **orders:read** hoặc **orders:approve**; hệ thống phải công bố và thực thi hợp đồng giữa Authorization Server (AS) với Resource Server (RS).

Ba khái niệm cần tách biệt:

- **Scope**: giới hạn quyền truy cập OAuth được cấp cho client/token đối với API.
- **Permission**: quyền nghiệp vụ để chủ thể thực hiện hành động trên một loại hoặc một tài nguyên cụ thể.
- **Role**: vai trò trong tổ chức, thường được ánh xạ sang permission theo chính sách RBAC.

Ví dụ, một quản lý có permission duyệt đơn hàng ở tenant A. Nếu dashboard chỉ nhận scope **orders:read**, nó không thể dùng access token ấy để vượt sang thao tác duyệt. Ngược lại, token có **orders:approve** không có nghĩa người dùng được duyệt mọi đơn hàng trong mọi tenant.

**Scope là điều kiện giới hạn của token; permission theo tài nguyên mới giúp Resource Server ra quyết định cuối cùng.** Một hệ thống an toàn thường kiểm cả hai.

Trong OIDC, những scope như **openid**, **profile**, **offline_access** phục vụ ngữ nghĩa xác thực, claims hoặc yêu cầu truy cập ngoại tuyến theo điều kiện giao thức. Chúng không mặc nhiên là quyền thao tác dữ liệu nghiệp vụ.

## 3. Over-privilege xuất hiện ở ba thời điểm

Một access token thường đi qua ba bước **yêu cầu → cấp → sử dụng**. Lỗi có thể nằm ở bất cứ bước nào.

| Lớp | Trách nhiệm | Ví dụ over-privilege | Biện pháp |
| --- | --- | --- | --- |
| **Client** | Xin đúng các scope cần cho tính năng. | Mọi màn hình đều xin **admin:all** dù chỉ cần xem dữ liệu. | Chia scope theo tác vụ, chỉ xin thêm khi có nhu cầu. |
| **Authorization Server** | Cấp phạm vi phù hợp client, sự ủy quyền và chính sách. | Cấp tất cả scope client yêu cầu mà không xét allowlist. | Giới hạn scope theo client, grant, tài nguyên và chính sách. |
| **Resource Server** | Kiểm access token, scope và quyền cho từng yêu cầu. | Cho thao tác ghi chỉ vì token được ký hợp lệ. | Xác minh audience, scope chính xác và permission theo tài nguyên. |

**Scope được yêu cầu không nhất thiết là scope được cấp.** Client có thể xin **orders:read orders:write**, nhưng AS chỉ cấp **orders:read** theo chính sách. Client cần xử lý kết quả thực tế, không mặc định rằng mình được tất cả quyền đã xin.

**Scope được cấp cũng chưa đồng nghĩa được phép thao tác với một bản ghi.** Resource Server phải kiểm xem principal có permission tương ứng tại tenant và tài nguyên hiện tại hay không.

## 4. Đo mức rộng theo nhiều chiều

Một token có thể quá quyền ở nhiều chiều khác nhau, không chỉ ở số lượng scope.

| Chiều | Ví dụ rộng | Cách giới hạn |
| --- | --- | --- |
| **Hành động** | **admin:all** bao gồm đọc, sửa, xóa, duyệt. | Tách phạm vi đọc, cập nhật, phê duyệt khi có giá trị bảo mật. |
| **Loại dữ liệu** | **data:read** mở mọi loại dữ liệu. | Chỉ cấp **reports:read** hoặc nhóm tài nguyên cần thiết. |
| **API đích** | Một token được nhiều API chấp nhận không kiểm audience. | Kiểm **audience** đúng Resource Server; cấp token đích hẹp. |
| **Tenant** | Một role ở tenant A bị áp lên tenant B. | Policy kiểm tenant thực của tài nguyên và membership hiện hành. |
| **Thời gian** | Access token đặc quyền sống quá lâu. | Giới hạn TTL, trạng thái thu hồi, xác thực lại theo rủi ro. |
| **Client** | Client ít tin cậy cũng được cấp scope quản trị. | Allowlist riêng theo client, loại client và luồng ủy quyền. |
| **Gia hạn** | Refresh token duy trì phạm vi quá rộng trong thời gian dài. | Kiểm lại chính sách khi refresh, rotation/thu hồi và giới hạn phiên. |

Không phải tất cả chiều đều nên nhồi vào tên scope. **Audience**, **tenant**, **thời hạn**, **loại principal** thường có claims, dữ liệu và chính sách riêng. Scope nên đủ dễ hiểu để AS cấp và RS thực thi nhất quán, còn chính sách động vẫn do hệ thống phân quyền kiểm soát.

## 5. Ví dụ xuyên suốt: ứng dụng báo cáo và API thanh toán

Giả sử hệ thống gồm:

- **Reports API**: xuất số liệu tổng hợp.
- **Orders API**: đọc và sửa đơn hàng.
- **Payments API**: tạo yêu cầu hoàn tiền.

Ứng dụng **reporting-client** chỉ thực sự gọi Reports API. Thiết kế thiếu kiểm soát:

~~~text
client_id = reporting-client
aud = nhiều API hoặc audience không được kiểm nhất quán
scope = "reports:read orders:read orders:write payments:refund admin:all"
~~~

Các vấn đề: client mang nhiều quyền không cần thiết; nếu một API chấp nhận sai audience hoặc policy kiểm không đủ, token có thể bị dùng sang thao tác rủi ro cao; việc theo dõi và thu hồi chọn lọc cũng khó hơn.

Thiết kế giới hạn hơn:

~~~text
client_id = reporting-client
aud = reports-api
scope = "reports:read"
ttl = thời hạn ngắn được quyết định theo rủi ro

Reports API:
    xác minh đúng issuer và audience
    kiểm scope reports:read chính xác
    kiểm quyền xem báo cáo tại tenant hiện hành
~~~

Nếu tính năng mới cần cập nhật đơn hàng, nhóm phát triển phải xác định thêm scope, API đích và điều kiện ủy quyền tương ứng. Không nên mở sẵn quyền sửa đơn hàng cho tất cả token của chức năng báo cáo.

~~~mermaid
flowchart TD
    A["Client xin scope vượt nhiệm vụ"] --> B["AS cấp token có quyền rộng"]
    B --> C["Token bị sao chép hoặc client bị xâm nhập"]
    C --> D["Thử endpoint ngoài mục đích ban đầu"]
    D --> E{"RS kiểm aud, scope, permission và tài nguyên?"}
    E -->|Thiếu kiểm tra| F["Có nguy cơ truy cập vượt quyền"]
    E -->|Đầy đủ| G["Yêu cầu trái phép bị từ chối"]
    B --> H["Giới hạn scope/audience, TTL và thu hồi"]
    H --> I["Giảm phạm vi có thể lạm dụng"]
~~~

Sơ đồ mô tả **nguy cơ có điều kiện**. Scope rộng không bảo đảm kẻ tấn công vượt mọi lớp phòng vệ; vấn đề là tạo thêm cơ hội không cần thiết khi một lớp bị cấu hình sai hoặc bị xâm nhập.

## 6. Scope tổng quát, wildcard và quyền ngầm

Các tên scope **all**, **full_access**, **admin:all** hoặc **orders:\*** chỉ có tác dụng nếu hệ thống định nghĩa. OAuth 2.0 không tự đưa ra wildcard hay phép kế thừa giữa các tên scope.

Những scope quá tổng quát gây các khó khăn:

1. **Khó xét duyệt:** người dùng, quản trị viên hoặc bên cấp quyền không nhìn rõ được những endpoint bị ảnh hưởng.
2. **Khó kiểm toán:** nhật ký cho thấy token mang **full_access**, nhưng không mô tả quyền nào thực sự cần.
3. **Dễ mở rộng ngầm:** một chức năng mới có thể vô tình được tính vào scope cũ.
4. **Khó thu hồi riêng:** quyền đọc và quyền duyệt bị gộp, không thể thu hẹp một phần bằng cấu hình scope đơn giản.
5. **Tăng phạm vi lạm dụng:** nhiều chức năng bị lộ cùng lúc khi token bị sao chép.

Một số hệ thống có lý do nghiệp vụ chính đáng để dùng scope quản trị rộng, chẳng hạn công cụ vận hành nội bộ được kiểm soát chặt. Khi đó cần **xác định đối tượng được cấp, thời hạn, audit, xác thực bổ sung và chính sách approval** rõ ràng, thay vì coi wildcard là giá trị mặc định.

### Scope có cần nhỏ tới từng bản ghi?

Không nhất thiết. Một thiết kế có hàng trăm nghìn scope tương ứng từng order ID sẽ khó duy trì. Thường hợp lý hơn khi scope cho biết **nhóm khả năng** (đọc đơn hàng, cập nhật đơn hàng), còn policy engine kiểm quan hệ **người dùng – tenant – đơn hàng** theo thời điểm.

Tính hạt của scope cần cân bằng giữa **giới hạn quyền thực chất** và **khả năng vận hành**.

## 7. Không suy diễn quan hệ scope nếu không có hợp đồng

Ba chuỗi sau không tự bao hàm nhau:

~~~text
orders:read
orders:write
orders:*
~~~

Chuẩn OAuth không quy định rằng **orders:write** luôn bao gồm **orders:read** hoặc **orders:\*** luôn bao gồm tất cả. Nếu tổ chức muốn có quan hệ bao hàm, phải định nghĩa, thực thi và kiểm thử nhất quán tại AS và RS.

Cũng tránh so khớp bằng chuỗi con:

~~~text
Granted scope = "orders:readall"
Required scope = "orders:read"

Sai:   chuoi_scope.contains("orders:read")  => true
Đúng:  parse thành tập scope và so khớp phần tử chính xác => false
~~~

Với biểu diễn scope tiêu chuẩn là danh sách phân tách bằng dấu cách, parser phải xử lý từng phần tử chính xác. Một số issuer có claim riêng như **scp** hoặc mảng scope; chỉ dùng định dạng đã quy định trong hợp đồng với issuer, không tự đoán theo tên trường.

Đừng dùng chuỗi scope từ **header/query mà client tự khai** để cấp quyền. RS phải lấy phạm vi được cấp từ access token đã xác minh hoặc phản hồi introspection đáng tin.

## 8. Audience và scope cần được kiểm tra cùng nhau

**Audience** trả lời **token cấp cho Resource Server nào**; **scope** trả lời **token được cấp phạm vi truy cập nào**.

Ví dụ payload access token JWT:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders:read",
  "iat": 1730000000,
  "exp": 1730000900
}
~~~

Đây chỉ là payload minh họa, không phải JWT hoàn chỉnh. Payments API phải từ chối token có **aud=orders-api** khi Payments API đòi audience riêng, ngay cả khi chuỗi scope có tên nghe liên quan đến tài chính.

Một thiết kế sai có thể cho các microservice chấp nhận mọi access token của cùng issuer mà không phân biệt audience. Khi một service hoặc token bị xâm nhập, token có thể bị sử dụng sai đích (**token substitution/confused deputy**).

Với hệ thống nhiều Resource Server, có thể cân nhắc **Resource Indicators for OAuth 2.0 (RFC 8707)** nếu AS hỗ trợ, để client chỉ ra tài nguyên đích. Việc cấp token audience hẹp vẫn phụ thuộc cấu hình AS và chính sách của hệ thống.

## 9. Kiểm tra token, scope và quyền hiện hành ở ba lớp

**Lớp 1 – Token có đáng tin cho API này không?** Resource Server xác minh token đúng loại **access token**; issuer, audience, chữ ký/khóa/thuật toán JWT hoặc opaque introspection đúng cấu hình; thời hạn và trạng thái thu hồi theo chính sách. ID token OIDC và refresh token không được dùng thay access token.

**Lớp 2 – Scope đã được cấp có đủ cho endpoint?** Hợp đồng API định nghĩa scope cần thiết. RS parse phạm vi đã cấp theo profile issuer, so khớp chính xác, không suy diễn wildcard hoặc quyền bao hàm. Khi sử dụng DPoP/mTLS-bound token, phải kiểm proof hoặc chứng chỉ đúng profile.

**Lớp 3 – Principal có quyền với tài nguyên cụ thể không?** Kiểm account hoạt động, permission hiện hành, vai trò trong tenant, ownership/relationship, trạng thái bản ghi và điều kiện nghiệp vụ. Scope đúng chỉ cho phép yêu cầu tiếp tục được đánh giá.

Một điều kiện minh họa:

~~~text
ALLOW if and only if:
    valid_access_token_for_orders_api
    AND token_within_accepted_lifetime
    AND exact_scope_present("orders:approve")
    AND account_active
    AND principal_has_current_permission("order:approve", order.tenant)
    AND order_eligible_for_approval
    AND separation_of_duties_satisfied
~~~

Nếu người tạo đơn không được tự duyệt thì dù token có scope duyệt và principal có role quản lý, policy vẫn phải từ chối.

### Ví dụ pseudocode

~~~text
function approveOrder(request, orderId):
    token = extractAccessToken(request)
    context = validateTokenUsingConfiguredProfile(
        token,
        trustedIssuer = service.trustedIssuer,
        expectedAudience = "orders-api",
        expectedTokenType = "access"
    )

    if context.invalidOrExpired:
        return HTTP_401

    scopes = parseGrantedScopesAccordingToIssuerContract(context)
    if not scopes.containsExact("orders:approve"):
        return HTTP_403

    order = orderRepository.find(orderId)
    if order == null:
        return HTTP_404

    principal = principalDirectory.resolveVerifiedSubject(context)
    if principal == null or not principal.active:
        return HTTP_403

    if not policyEngine.allows(
        principal = principal,
        client = context.verifiedClientId,
        action = "order:approve",
        tenant = order.tenantId,
        resource = order
    ):
        return HTTP_403

    return orderRepository.approveIfCurrentRulesAllow(order)
~~~

Đây là **mã giả**, không phải code xác minh JWT production. Nó tách trách nhiệm kiểm token, scope và policy nghiệp vụ. **Tenant của đơn hàng** cần lấy từ nguồn dữ liệu server, không chỉ dựa vào giá trị trong đường dẫn do client gửi.

Theo HTTP Bearer token usage (RFC 6750), token thiếu hoặc không hợp lệ thường dẫn đến **401 Unauthorized**; token đã chấp nhận nhưng thiếu scope thường dẫn đến **403 Forbidden**, có thể kèm lỗi **insufficient_scope** phù hợp. Không nên tiết lộ thông tin nội bộ về tài nguyên và quyền trong thông báo lỗi.

## 10. Chọn scope theo loại client và luồng OAuth

### 10.1 Client có người dùng

Trong Authorization Code flow, ứng dụng có thể yêu cầu scope cho tính năng mà người dùng đang sử dụng. AS cần xét:

- Client đã được đăng ký/cho phép xin scope nào?
- Sự ủy quyền hoặc consent của người dùng có hợp lệ và đủ không?
- Chính sách tổ chức có cho phép cấp scope đó không?
- API đích là API nào, dữ liệu và hành động nào cần được bảo vệ?
- Có thể xin thêm scope **khi người dùng sử dụng tính năng mới** thay vì xin tất cả lúc đăng nhập không?

Cách xin thêm quyền theo thời điểm sử dụng thường được gọi là **incremental authorization**. Chi tiết phụ thuộc khả năng của AS và luồng cấp quyền; không mặc định mọi AS đều hỗ trợ như nhau.

**Consent không thể thay thế permission:** người dùng bấm đồng ý cho một client không đồng nghĩa họ có quyền cấp khả năng truy cập vượt giới hạn tổ chức.

### 10.2 Client credentials và service-to-service

Trong luồng **client credentials**, token có thể đại diện cho client/workload, không nhất thiết có người dùng cuối. Mỗi service nên được giới hạn theo mục đích:

~~~text
nightly-report-worker:
    audience = reports-api
    scope = reports:generate

payment-settlement-worker:
    audience = payments-api
    scope = payments:settle
~~~

Tránh dùng chung một service account và token với scope **admin:all** cho mọi batch job. Nếu một worker bị xâm nhập, token giới hạn theo audience và scope giúp giảm hệ thống bị ảnh hưởng.

### 10.3 SPA và mobile

Client chạy trên thiết bị người dùng có nguy cơ lộ token qua XSS, log, backup hoặc thiết bị bị chiếm quyền. Cần giảm scope, TTL và giữ refresh token ở nơi phù hợp. Với public client được cấp refresh token, OAuth 2.0 Security BCP (RFC 9700) yêu cầu biện pháp bảo vệ như rotation hoặc sender-constraining theo mô hình được áp dụng.

## 11. Scope rộng kết hợp token bị đánh cắp hoặc phát lại

Bản thân scope rộng không phải lỗi chữ ký JWT. Nó làm tăng **blast radius** (phạm vi thiệt hại) khi token bị sao chép hoặc client bị chiếm quyền.

| Tình huống | Rủi ro khi scope rộng | Biện pháp |
| --- | --- | --- |
| Access token lọt vào log, URL hoặc telemetry. | Bản sao có thể được dùng thử ở nhiều endpoint có giá trị. | Che token trong log, dùng TLS, TTL và scope/audience hẹp, thu hồi khi phát hiện lộ. |
| XSS trên SPA. | Mã độc có thể đọc token nếu nơi lưu cho phép. | Chống XSS/CSP; cân nhắc BFF/cookie an toàn, giảm scope và bảo vệ phiên. |
| Mobile bị xâm nhập. | Token có nhiều quyền và có thể bị lấy/tận dụng. | Lưu trữ an toàn, ràng buộc token khi phù hợp, thu hồi thiết bị/phiên. |
| Token được chuyển giữa nhiều microservice. | Token có thể bị dùng sai audience hoặc quyền lan sang service khác. | Cấp token đúng audience; không chuyển tiếp tùy tiện token đặc quyền. |
| Refresh token đặc quyền bị lấy. | Kẻ tấn công có thể thử xin thêm access token còn quyền rộng. | Bảo vệ nơi lưu, rotation/sender constraint, giới hạn sự ủy quyền. |
| Lặp request nghiệp vụ. | Cùng token có thể được dùng gửi cùng thao tác nhiều lần. | Idempotency/nonce theo giao dịch; kiểm scope không thay thế chống lặp. |

Một **bearer token** thường có thể bị sử dụng bởi bên nắm giữ bản sao, nếu các kiểm tra khác đều đạt. Với **DPoP** (RFC 9449) hoặc **mTLS-bound token** (RFC 8705), AS/RS có thể ràng buộc việc dùng token với khóa/chứng chỉ. Các cơ chế này giảm nguy cơ sao chép token đơn thuần, nhưng không thay thế scope hẹp hay quyền nghiệp vụ và không ngăn mọi tấn công vào client đã bị chiếm quyền.

Cả JWT và opaque access token đều có thể bị cấp scope quá rộng; **định dạng token không tự quyết định mức quyền**.

## 12. Scope trong vòng đời access token và refresh token

**Access token ngắn hạn** giảm cửa sổ sử dụng nếu bị lộ, nhưng JWT ngoại tuyến không tự biết tài khoản bị khóa hoặc quyền bị rút giữa chừng. Nếu cần thu hồi sớm, phải có danh sách thu hồi, introspection, trạng thái phiên hoặc chính sách quyền động theo mức rủi ro.

**Refresh token** dùng tại Authorization Server để xin access token mới khi điều kiện còn hợp lệ. Khi xử lý refresh, AS cần tôn trọng ràng buộc client, phiên, chính sách và phạm vi đã được ủy quyền. Refresh grant **không thể tự tăng scope vượt sự ủy quyền ban đầu**; AS có thể chỉ cấp phạm vi nhỏ hơn theo chính sách.

**Revocation** (RFC 7009) cho phép yêu cầu thu hồi token theo giao thức, nhưng hiệu lực trên các API phụ thuộc cách chúng kiểm trạng thái. Với opaque token, cache introspection active có thể khiến kết quả thu hồi đến chậm. Với JWT xác minh ngoại tuyến, chữ ký và claims có thể vẫn hợp lệ tới khi hết hạn nếu RS không kiểm trạng thái bổ sung.

Nếu doanh nghiệp yêu cầu ngừng quyền hoàn tiền gần như ngay khi quản trị viên rút role, một JWT còn **payments:refund** trong payload không được xem là bằng chứng rằng permission vẫn còn. Cần kiểm quyền hiện hành hoặc cơ chế thu hồi đáp ứng **độ trễ tối đa chấp nhận được**.

## 13. Thu hẹp scope đang được sử dụng

Một hệ thống cũ có thể dùng scope **api:all** cho mọi chức năng. Nên tiến hành chuyển đổi theo các bước:

1. **Kiểm kê** client, API, endpoint, hành động thực tế và scope đang được yêu cầu/cấp.
2. **Định nghĩa hợp đồng mới** theo nhóm hành động thực sự cần: **reports:read**, **orders:read**, **orders:update**, **orders:approve**, **payments:refund**.
3. **Lập ma trận client → API → scope** để biết chính xác client nào cần phạm vi nào.
4. **Cấu hình AS** với allowlist scope theo client, grant, audience và policy người dùng/tổ chức.
5. **Cập nhật RS** để xác minh token và thực thi scope mới, cùng kiểm permission theo tài nguyên.
6. **Chuyển đổi client** sang yêu cầu scope hẹp; theo dõi lỗi hợp lệ bị chặn và các yêu cầu trái phép.
7. **Ngừng cấp scope rộng**; có kế hoạch hết hạn/thu hồi token hoặc grant cũ theo chính sách.
8. **Đo lại rủi ro** bằng negative tests, giám sát và SLA thu hồi quyền.

Ví dụ ma trận chuyển đổi:

| Client | Tác vụ | Scope cũ | Scope mục tiêu |
| --- | --- | --- | --- |
| reporting-client | Xem báo cáo | api:all | reports:read |
| order-dashboard | Xem và cập nhật đơn | api:all | orders:read orders:update |
| approval-console | Duyệt đơn | api:all | orders:read orders:approve |
| refund-worker | Hoàn tiền đã phê duyệt | api:all | payments:refund |

Trong giai đoạn tương thích, scope rộng cũ cần có **thời hạn ngừng sử dụng, chủ sở hữu và phạm vi client cho phép**. Không duy trì quyền đặc biệt vĩnh viễn chỉ để tránh sửa client.

## 14. Kiểm thử những yêu cầu phải bị từ chối

Chỉ kiểm thử truy cập thành công không đủ chứng minh hạn chế quyền. Cần thử các trường hợp âm tính:

| Phép thử | Kết quả kỳ vọng |
| --- | --- |
| Client báo cáo yêu cầu **payments:refund** dù không có allowlist. | AS từ chối hoặc không cấp scope đó theo hợp đồng. |
| Token có **reports:read** gọi endpoint sửa đơn hàng. | RS từ chối do thiếu scope hoặc sai audience. |
| Token có **orders:readall**, endpoint đòi **orders:read**. | Từ chối nếu không có quy tắc bao hàm rõ; không so chuỗi con. |
| User có role quản lý nhưng token chỉ có **orders:read**. | Không được thực hiện ghi/duyệt bằng token này. |
| Token có **orders:write**, nhưng user chỉ có permission đọc. | RS từ chối theo policy nghiệp vụ. |
| Token đúng scope nhưng **aud=reports-api** được gửi tới Orders API. | Từ chối vì audience không hợp lệ. |
| User có role ở tenant A, truy cập dữ liệu tenant B. | RS từ chối nếu không có quyền đúng tenant B. |
| Role bị rút trong lúc JWT chưa hết hạn. | Kết quả tuân thủ SLA thu hồi đã thiết kế; không tin role cũ vô hạn. |
| Opaque token bị thu hồi nhưng introspection cache chưa hết hạn. | Hệ thống đo và kiểm soát thời gian phản ánh thu hồi. |
| API kiểm chính sách bị lỗi hoặc timeout. | Xử lý theo fail-safe policy; không tự mở quyền nhạy cảm. |
| Client gửi ID token OIDC thay access token. | RS từ chối do sai mục đích/loại token. |
| Client bị mất quyền scope rộng nhưng refresh token còn tồn tại. | AS áp chính sách hiện hành, không cấp tiếp quyền không hợp lệ. |

Với API có thao tác thay đổi trạng thái hoặc giao dịch, cần thêm kiểm thử **retry và idempotency**: sau khi refresh access token, gửi lại request không được vô tình tạo giao dịch trùng.

## 15. Bài tập tình huống

Một dashboard chỉ cần lấy số liệu tổng hợp từ Reports API nhưng nhận access token với:

~~~text
aud = reports-api
scope = "reports:read orders:read customers:read"
~~~

**Tình huống A — Scope nào có thể là dư quyền?** Nếu dashboard thực sự chỉ gọi Reports API và phần tổng hợp xử lý ở backend, **orders:read** và **customers:read** là những scope cần đặt câu hỏi. Chỉ giữ những scope thực sự dùng theo hợp đồng của Reports API.

**Tình huống B — Có audience hẹp rồi thì còn cần giới hạn scope không?** Có. Audience giúp ngăn dùng token sai API; scope hẹp tiếp tục giới hạn quyền trong API đích và giảm thiểu tác hại khi hợp đồng hoặc cấu hình thay đổi.

**Tình huống C — Một nhân viên có role manager, có được bỏ kiểm scope không?** Không. Role/permission và scope giải quyết hai lớp khác nhau; token không có scope đúng thì không được vượt qua chỉ vì principal có role cao.

**Tình huống D — AS thu hồi token đã lộ; có chắc mọi API từ chối ngay không?** Không nhất thiết. JWT xác minh ngoại tuyến và cache introspection có thể làm trạng thái đến chậm. Cần cơ chế và SLA thu hồi cụ thể.

**Tình huống E — Có nên cấp wildcard để tránh phải xin scope mới trong tương lai?** Thường không. Nên cấp theo nhu cầu đã được đánh giá; chức năng mới cần quy trình xin quyền và kiểm tra chính sách phù hợp.

## 16. Checklist áp dụng least privilege

Trước khi triển khai, nhóm phát triển nên xác nhận:

- **Nhu cầu thực:** Client có xin scope chỉ vì “có thể dùng sau này” không?
- **Ngữ nghĩa:** Từng scope có định nghĩa hành động/tài nguyên và chủ sở hữu hợp đồng rõ ràng không?
- **Cấp phát:** AS có giới hạn theo client, grant, audience, sự ủy quyền và policy không?
- **Audience:** Mỗi Resource Server có từ chối token dành cho API khác không?
- **Loại token:** API có ngăn ID token/refresh token bị dùng làm access token không?
- **So khớp:** Scope có được parse đúng schema và so khớp giá trị chính xác, tránh substring/wildcard tự suy diễn không?
- **Quyền nghiệp vụ:** Có kiểm permission, tenant thực và quan hệ với tài nguyên sau khi kiểm scope không?
- **Vòng đời:** Access token, refresh token, rotation và thu hồi có thời hạn/SLA phù hợp rủi ro không?
- **Phòng lộ:** Token có bị ghi vào URL, log, analytics, clipboard hoặc backup không an toàn không?
- **Giám sát:** Có theo dõi cấp scope bất thường, dùng token sai audience, lỗi insufficient_scope và thay đổi quyền không?
- **Kiểm thử:** Có negative tests cho thiếu scope, dư scope, sai audience, cross-tenant, stale role và token bị thu hồi không?

## Kết luận

**Scope quá rộng làm tăng khả năng truy cập mà token hoặc client có thể yêu cầu**, đặc biệt khi token bị đánh cắp hoặc Resource Server thực thi phân quyền thiếu chặt chẽ. Biện pháp giảm over-privilege là **xin ít, cấp đúng, xác minh và thực thi chặt**, kết hợp với audience, thời hạn, thu hồi và bảo vệ token.

Scope vẫn chỉ là **một lớp giới hạn OAuth**. Một access token hợp lệ với scope phù hợp không tự có quyền trên mọi tài nguyên: Resource Server phải kiểm permission, tenant, quan hệ và chính sách nghiệp vụ hiện hành. Mục tiêu là khi một token bị lộ, phạm vi bị ảnh hưởng nhỏ và những hành động ngoài nhiệm vụ luôn bị từ chối.

### Tài liệu tham khảo

- [RFC 6749 — OAuth 2.0 Authorization Framework, Section 3.3 Scope](https://www.rfc-editor.org/rfc/rfc6749#section-3.3)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
