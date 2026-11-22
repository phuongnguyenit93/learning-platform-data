# Tránh phát hành token có quyền hoặc phạm vi vượt yêu cầu

> **Module:** `SECURITY_TOKEN_SECURITY_JWT` — **Security - JSON Web Token (JWT)**. **Chương:** Cấp phát token. Bài viết áp dụng cho hệ thống JWT nói chung, không phụ thuộc ngôn ngữ lập trình, nền tảng hoặc framework.

## 1. Vì sao token không được mang quyền vượt nhu cầu?

Access token là credential mà client trình cho resource server để yêu cầu truy cập tài nguyên. Những claim như `scope`, `roles`, `permissions`, `tenant_id` hoặc các quyền riêng theo nghiệp vụ có thể ảnh hưởng trực tiếp đến quyết định authorization.

Nếu issuer phát hành token với quyền rộng hơn nhu cầu, một lỗi ở client, API hoặc quy trình xử lý có thể biến thành quyền truy cập vượt mức. Khi token bị lộ, phạm vi thiệt hại cũng lớn hơn. Vì vậy, mỗi token cần tuân theo nguyên tắc **least privilege (đặc quyền tối thiểu)**: chỉ chứa những quyền cần thiết cho mục đích, chủ thể, client, resource và thời hạn cụ thể.

Cần phân biệt ba tập quyền:

- **Requested permissions/scopes:** quyền mà client hoặc người dùng yêu cầu.
- **Eligible permissions:** quyền mà subject, client, grant và chính sách có thể cho phép trong ngữ cảnh hiện tại.
- **Granted permissions:** quyền thực tế issuer quyết định cấp và ghi vào token.

Thông thường:

\[
Granted \subseteq Requested \cap Eligible
\]

Tập quyền được cấp không được vượt quá yêu cầu hoặc quyền hợp lệ của chủ thể/client/grant. Tùy giao thức và chính sách, issuer có thể cấp tập con (downscope) hoặc từ chối toàn bộ yêu cầu nếu không thể đáp ứng an toàn.

**Không lấy nguyên scope/role từ request rồi đưa vào JWT.** Request chỉ là đề xuất; issuer phải tính quyền ở phía máy chủ từ nguồn có thẩm quyền.

## 2. Xác định chính xác nhu cầu trước khi cấp quyền

Trước khi tạo access token, cần hiểu rõ token được dùng để làm gì. Chỉ nhìn vào chuỗi scope yêu cầu là chưa đủ. Cần xét:

1. **Subject:** người dùng, client, service account hoặc workload nào được đại diện?
2. **Client:** ứng dụng nào yêu cầu token và client đó được phép dùng grant nào?
3. **Resource/audience:** token dành cho API hoặc tài nguyên nào?
4. **Action:** thao tác nào thực sự cần thiết, chẳng hạn đọc, tạo, cập nhật, xóa, hoàn tiền?
5. **Object/tenant boundary:** quyền áp dụng cho bản ghi, tài khoản, tổ chức hoặc tenant nào?
6. **Context:** trạng thái phiên, mức xác thực, consent, chính sách tổ chức và rủi ro hiện tại?
7. **Duration:** quyền cần tồn tại trong bao lâu và có cần xác thực lại khi thao tác nhạy cảm?

Ví dụ, ứng dụng quản lý đơn hàng chỉ cần xem danh sách đơn thuộc `tenant-a`. Một yêu cầu token có `orders:read` cho Orders API có thể phù hợp. Việc cấp thêm `orders:write`, `orders:refund`, `users:manage` hoặc quyền của tenant khác là không cần thiết và có thể gây vượt quyền.

### 2.1. Mô tả quyền theo hành động và tài nguyên

Scope nên có ngữ nghĩa rõ ràng. Ví dụ:

| Scope minh họa | Ý nghĩa |
| --- | --- |
| `orders:read` | Đọc đơn hàng theo chính sách tài nguyên |
| `orders:create` | Tạo đơn hàng |
| `orders:update` | Cập nhật thuộc tính được phép |
| `orders:cancel` | Hủy đơn hàng |
| `orders:refund` | Thực hiện hoặc yêu cầu hoàn tiền |
| `users:read` | Đọc dữ liệu người dùng trong phạm vi được cấp |
| `users:manage` | Quản trị người dùng theo policy riêng |

Đây là quy ước riêng của hệ thống, không phải danh sách scope chuẩn chung. Một scope quá rộng như `admin` hoặc `full_access` thường khó kiểm soát và dễ được sử dụng ngoài mục đích ban đầu. Nếu buộc phải có scope rộng cho một số tác vụ, cần giới hạn đối tượng, audience, thời hạn và điều kiện xác thực tăng cường.

### 2.2. Scope không thay thế kiểm tra quyền trên từng tài nguyên

Scope trong token thường thể hiện loại thao tác mà client/subject có thể yêu cầu. Nó không tự động chứng minh chủ thể được truy cập mọi bản ghi thuộc loại tài nguyên đó.

Ví dụ, `orders:read` không đồng nghĩa người dùng được xem mọi đơn hàng. Resource server vẫn cần kiểm tra:

- đơn hàng có thuộc subject hoặc tổ chức được phép không;
- subject có membership hợp lệ ở tenant chứa đơn hàng không;
- có quy tắc ownership, phân vùng dữ liệu hoặc quan hệ nghiệp vụ nào phải áp dụng không;
- tài nguyên có trạng thái cho phép thao tác đó không.

Đây là khác biệt giữa **coarse-grained permission** trong token và **fine-grained authorization** tại thời điểm truy cập.

## 3. Tính quyền được cấp từ nhiều ràng buộc

Một cách mô hình hóa an toàn là tính quyền cuối cùng bằng giao của các ràng buộc:

\[
Granted = Requested \cap SubjectPolicy \cap ClientPolicy \cap GrantPolicy \cap ResourcePolicy
\]

Trong đó:

- `Requested`: scope/action mà request đề nghị.
- `SubjectPolicy`: quyền hiện tại của subject.
- `ClientPolicy`: quyền mà client được phép yêu cầu.
- `GrantPolicy`: quyền được consent hoặc ủy quyền trong grant.
- `ResourcePolicy`: quyền hợp lệ cho audience, tenant và tài nguyên.

Tập quyền này còn phải chịu các điều kiện bổ sung như mức xác thực, trạng thái tài khoản, thời hạn, chính sách rủi ro và giới hạn nghiệp vụ.

Ví dụ:

| Ràng buộc | Quyền được phép |
| --- | --- |
| Client yêu cầu | `orders:read orders:refund` |
| Quyền của subject | `orders:read orders:cancel` |
| Grant/consent | `orders:read orders:refund` |
| Client policy | `orders:read orders:refund` |
| Resource policy cho tenant hiện tại | `orders:read` |
| **Kết quả** | **`orders:read`** |

Dù subject và client có thể được cấp quyền hoàn tiền ở ngữ cảnh khác, resource policy hiện tại chỉ cho phép đọc. Issuer chỉ đưa `orders:read` vào token.

### 3.1. Không tự mở rộng quyền bằng default scope

Một số hệ thống có default scope khi request không gửi trường scope. Cần xác định rõ default là gì và không để nó vô tình cấp quyền rộng:

- Default phải là tập quyền tối thiểu, phù hợp client và resource.
- Không mặc định cấp `admin`, `write` hoặc quyền quản trị nếu request thiếu scope.
- Nếu client không khai báo scope và không có default an toàn, từ chối hoặc áp dụng profile đã được thống nhất.
- Không để scope mặc định khác nhau ngầm giữa các node hoặc môi trường.

**Thiếu yêu cầu không có nghĩa là đồng ý cấp toàn bộ quyền.**

### 3.2. Không dùng wildcard thiếu kiểm soát

Các giá trị như `*`, `orders:*` hoặc `admin:*` có thể tiện lợi nhưng làm tăng phạm vi quyền. Nếu hỗ trợ wildcard:

- định nghĩa chính xác wildcard bao phủ những hành động nào;
- chỉ cho phép các client/role được phê duyệt sử dụng;
- kiểm tra audience và tenant;
- không cho wildcard vượt qua deny rule;
- ghi audit và kiểm thử các tổ hợp quyền;
- ưu tiên danh sách action tường minh khi quyền nhạy cảm.

## 4. Phân biệt role, scope và permission

Ba khái niệm thường liên quan nhưng không đồng nhất:

- **Role:** nhóm trách nhiệm hoặc chức năng được gán cho subject trong một phạm vi.
- **Permission:** quyền cụ thể đối với action/resource.
- **Scope:** phạm vi truy cập mà client được phép sử dụng theo giao thức hoặc authorization server.

Ví dụ `finance_manager` có thể là role trong một tổ chức, nhưng không nhất thiết được cấp mọi quyền tài chính trên mọi tenant. Policy engine có thể chuyển role thành các permission cụ thể theo resource, trạng thái và ngữ cảnh. Token nên chứa scope/permission phù hợp với audience và nhu cầu thực tế, thay vì sao chép tất cả role của người dùng.

| Dữ liệu | Cách sử dụng an toàn |
| --- | --- |
| Role từ directory | Đầu vào để policy engine đánh giá; kiểm tra nguồn và phạm vi |
| Permission từ policy engine | Có thể đưa vào token nếu cần và đúng audience |
| Scope từ request | Chỉ là yêu cầu; phải giới hạn bằng grant và policy |
| Admin flag từ client | Không tin; phải lấy từ nguồn có thẩm quyền |
| Tenant membership | Kiểm tra trạng thái hiện tại và ràng buộc với subject/resource |

Không biến mọi group trong directory thành scope. Một nhóm có thể dùng cho tổ chức, báo cáo hoặc phân loại nhân sự mà không có nghĩa là quyền API.

## 5. Audience và resource cũng là ranh giới quyền

Token có scope đúng nhưng audience quá rộng vẫn có thể bị chấp nhận ở nhiều nơi hơn dự kiến. Cần giới hạn quyền đồng thời theo resource:

- Chọn audience từ resource registry hoặc chính sách đã cấu hình.
- Không để client tự yêu cầu URL tùy ý rồi biến URL đó thành audience.
- Cấp token riêng theo resource server khi kiến trúc và giao thức yêu cầu.
- Không tái sử dụng access token cho API có mô hình authorization khác.
- Nếu profile hỗ trợ nhiều audience, từng resource server phải kiểm tra quyền và audience của chính mình; tránh cấp nhiều recipient không cần thiết.

Ví dụ, `orders:read` dành cho Orders API không được mặc định dùng cho Payments API. Dù cùng một subject và client, quyền phải được đánh giá lại cho từng resource.

OAuth Resource Indicators (RFC 8707) cung cấp cơ chế để client chỉ định resource dự kiến; authorization server vẫn phải xác minh client/grant có quyền truy cập resource đó. Resource indicator không phải giấy phép để client chọn một resource bất kỳ.

## 6. Xử lý yêu cầu scope: cấp tập con hay từ chối?

Nếu client yêu cầu nhiều scope hơn mức có thể cấp, issuer cần có chính sách nhất quán:

### 6.1. Downscope

Cấp tập con khi:

- giao thức/profile cho phép;
- phần quyền còn lại vẫn đáp ứng mục đích hợp lệ của request;
- client có thể xử lý kết quả thực tế;
- response mô tả rõ scope được cấp để client không hiểu nhầm.

Ví dụ, client yêu cầu `orders:read orders:refund` nhưng chỉ được cấp `orders:read`. Issuer trả access token với đúng scope đã cấp và phản ánh tập scope thực tế theo quy tắc giao thức.

### 6.2. Từ chối toàn bộ yêu cầu

Nên từ chối khi:

- một scope bắt buộc cho mục đích nghiệp vụ không được phép;
- việc cấp tập con khiến giao dịch không còn ý nghĩa hoặc có thể tạo trạng thái không an toàn;
- client yêu cầu audience hoặc grant không hợp lệ;
- phát hiện yêu cầu vượt quyền, giả mạo hoặc vi phạm chính sách;
- không thể xác định rõ quyền nào được phép cấp.

Không âm thầm cấp một tập scope khác mà client không thể biết. Hợp đồng API cần xác định cách biểu diễn scope thực tế, lỗi và quyền bị từ chối.

### 6.3. Không tự nâng scope trong refresh

Refresh token chỉ cho phép xin access token mới trong phạm vi grant/phiên hiện tại và các chính sách còn hiệu lực. Nếu client yêu cầu thêm scope ở lần refresh:

- kiểm tra grant có cho phép mở rộng hay không;
- yêu cầu consent hoặc authorization mới khi giao thức yêu cầu;
- đánh giá lại quyền subject, client, audience và tenant;
- không tự mở rộng chỉ vì client đang giữ refresh token hợp lệ.

Refresh token là bằng chứng cho việc tiếp tục một grant đã được cấp, không phải quyền để tạo một grant mới tùy ý.

## 7. Phân biệt client credentials và delegated access

### 7.1. Client credentials / machine-to-machine

Trong luồng client credentials, client hành động thay mặt chính nó. Issuer cần giới hạn:

- danh tính client/workload đã được xác thực;
- audience/resource mà client được phép gọi;
- scope đã đăng ký và được cấp cho workload;
- tenant, môi trường hoặc tài nguyên mà workload được phép truy cập;
- TTL và điều kiện rotation của credential.

Không cấp quyền của người dùng chỉ vì client gửi một user ID. Nếu nghiệp vụ cần workload hành động thay mặt người dùng, phải dùng cơ chế delegation phù hợp.

### 7.2. Delegated access

Trong delegated access, client hành động thay mặt một subject. Quyền cuối cùng phải bị giới hạn bởi cả quyền của subject và quyền/consent của client:

\[
DelegatedGrant \subseteq SubjectPermissions \cap ClientPermissions \cap Consent
\]

Ví dụ, người dùng cho dashboard quyền đọc và cập nhật đơn hàng, nhưng dashboard chỉ được đăng ký scope đọc. Token của dashboard không được nhận scope cập nhật dù người dùng có quyền cập nhật khi sử dụng ứng dụng khác.

Cần xác định rõ:

- subject là ai;
- client/actor nào đang hành động;
- quyền được ủy quyền trong phạm vi nào;
- consent còn hiệu lực không;
- có giới hạn resource, tenant, thời gian hoặc điều kiện nào không.

Với token exchange, subject token và actor token có thể mang các vai trò khác nhau. Token mới chỉ được cấp quyền trong phạm vi delegation và chính sách cho phép; không biến token đầu vào có quyền rộng thành token mới có quyền rộng hơn.

## 8. Kiểm soát quyền theo tenant và đối tượng

Trong hệ thống đa tenant, scope chung có thể chưa đủ để giới hạn truy cập. Cần kết hợp tenant context và kiểm tra quyền trên từng object.

Ví dụ request:

~~~json
{
  "resource": "orders-api",
  "tenant_id": "tenant-a",
  "scope": "orders:read orders:refund"
}
~~~

Issuer không được mặc định tin `tenant_id` và `scope` trong request. Cần:

1. Xác minh subject đã được xác thực.
2. Kiểm tra subject có membership còn hiệu lực tại `tenant-a`.
3. Xác minh client/grant được phép truy cập tenant và resource.
4. Tính scope thực tế từ policy engine cho subject/client/tenant.
5. Chỉ đưa tenant và scope được phép vào JWT.
6. Resource server tiếp tục kiểm tra ownership hoặc policy theo từng đơn hàng.

Nếu subject thuộc tenant A và tenant B nhưng chỉ được cấp quyền đọc tại tenant A, token có tenant B hoặc quyền của tenant B là không hợp lệ. Không trộn cache quyền giữa các tenant và không tra cứu role bằng khóa subject đơn lẻ khi dữ liệu cần tenant context.

## 9. Claim quyền cần tối thiểu và đúng thời điểm

Không đưa mọi quyền của subject vào token chỉ vì issuer có thể truy vấn được. Payload cần phục vụ đúng audience và thời điểm:

- Chỉ đưa scope/permission mà resource server cần để ra quyết định.
- Tránh claim role tổng quát nếu API cần permission cụ thể.
- Giới hạn số lượng và độ dài scope/permission.
- Không đưa thông tin quản trị nội bộ hoặc quyền thuộc API khác.
- Tính lại quyền ở thời điểm phát hành, đặc biệt sau khi refresh hoặc token exchange.
- Dùng access token ngắn hạn và cơ chế thu hồi/kiểm tra trạng thái phù hợp nếu quyền thay đổi nhanh.
- Không coi claim quyền là thay thế kiểm tra tài nguyên cụ thể.

Quyền trong JWT là snapshot tại thời điểm phát hành. Nếu role hoặc membership bị thu hồi ngay sau đó, token tự chứa có thể còn hiệu lực đến `exp` nếu resource server không có kiểm tra trạng thái bổ sung. Thời hạn token, introspection, denylist hoặc cơ chế policy động cần được chọn theo mức rủi ro.

## 10. Quy trình tính quyền trước khi ký

~~~mermaid
flowchart TD
    A["Nhận yêu cầu token"] --> B["Xác minh client, grant và subject"]
    B --> C{"Bằng chứng và grant hợp lệ?"}
    C -- "Không" --> X["Từ chối"]
    C -- "Có" --> D["Xác định resource, audience và tenant"]
    D --> E{"Client được phép resource/tenant?"}
    E -- "Không" --> X
    E -- "Có" --> F["Đọc yêu cầu scope/action"]
    F --> G["Tính quyền subject, client, consent và resource policy"]
    G --> H["Lấy giao các quyền được phép"]
    H --> I{"Quyền đáp ứng mục đích request?"}
    I -- "Không" --> J["Từ chối hoặc downscope theo giao thức"]
    I -- "Có" --> K["Xây dựng claims theo allowlist"]
    J --> L{"Có tập quyền hợp lệ để cấp?"}
    L -- "Không" --> X
    L -- "Có" --> K
    K --> M["Validate schema và giới hạn quyền"]
    M --> N{"Payload hợp lệ?"}
    N -- "Không" --> X
    N -- "Có" --> O["Ký JWT và trả scope thực tế"]
~~~

Các bước cốt lõi:

1. Xác minh client, grant, subject và trạng thái.
2. Chọn resource/audience và tenant từ nguồn được phép.
3. Đọc scope/action được yêu cầu như một đề xuất.
4. Tính quyền hiệu lực từ policy engine và consent.
5. Lấy tập quyền giao giữa yêu cầu và các ràng buộc.
6. Downscope hoặc từ chối theo hợp đồng.
7. Dựng payload từ allowlist, không sao chép request.
8. Kiểm tra schema, scope, audience, tenant và thời hạn.
9. Ký bằng khóa cấu hình; trả về quyền thực tế đã cấp.

## 11. Mã giả phát hành token theo nguyên tắc least privilege

~~~text
function issueLeastPrivilegeToken(request, verifiedContext):
    client = clientRegistry.requireActive(verifiedContext.client)
    subject = identityStore.resolveVerifiedSubject(verifiedContext)
    grant = grantStore.requireActive(verifiedContext.grant)

    resource = resourceRegistry.requireKnown(request.resource)
    require clientPolicy.permitsResource(client, resource)
    require grantPolicy.permitsResource(grant, resource)

    tenant = tenantPolicy.resolveAndVerify(
        subject,
        client,
        grant,
        request.requestedTenant
    )

    requested = scopeParser.parse(request.requestedScopes)
    require requested.hasValidSyntax

    subjectPermissions = policyEngine.permissionsFor(
        subject,
        resource,
        tenant
    )
    clientPermissions = clientPolicy.permissionsFor(client, resource)
    grantPermissions = grantPolicy.permissionsFor(grant, resource)
    resourcePermissions = resource.policyAllowedPermissions

    eligible = intersect(
        subjectPermissions,
        clientPermissions,
        grantPermissions,
        resourcePermissions
    )

    granted = intersect(requested, eligible)
    if not policy.permitsDownscoping and granted != requested:
        reject("requested_scope_not_fully_granted")

    if granted is empty:
        reject("no_permitted_scope")

    claims = buildClaimsFromTrustedSources(
        issuer = configuredIssuer,
        subject = subject.stableId,
        audience = resource.audience,
        client = client.id,
        tenant = tenant.id,
        scopes = granted,
        expiration = tokenPolicy.expirationFor(resource, granted)
    )

    tokenProfile.validate(claims)
    return signWithConfiguredKey(claims, grantedScopeResponse = granted)
~~~

Mã giả giả định quyền được biểu diễn trong cùng một miền so sánh. Trong hệ thống thực, scope, permission và resource policy có thể có cấu trúc khác nhau; cần định nghĩa phép giao theo semantics của policy, không chỉ so sánh chuỗi. Việc từ chối/downscope và định dạng response phải tuân thủ giao thức đang sử dụng.

## 12. Ví dụ thực tế: dashboard yêu cầu quyền rộng hơn

Một dashboard muốn hiển thị đơn hàng của người dùng trong tenant A. Client gửi yêu cầu:

~~~json
{
  "resource": "orders-api",
  "requested_scope": "orders:read orders:update orders:refund",
  "requested_tenant": "tenant-a"
}
~~~

Sau khi xác minh:

| Ràng buộc | Kết quả |
| --- | --- |
| Subject | `user-84` đang hoạt động |
| Membership | `user-84` thuộc `tenant-a` |
| Client | `dashboard` được phép truy cập Orders API |
| Grant/consent | Chỉ cho phép `orders:read` và `orders:update` |
| Subject policy | Có `orders:read` và `orders:update`; không có `orders:refund` |
| Client policy | Dashboard chỉ được yêu cầu đọc và cập nhật |
| Resource policy | Orders API cho phép hai scope trên |
| **Granted scopes** | **`orders:read orders:update`** |

Issuer có thể downscope thành hai scope hợp lệ nếu giao thức cho phép và client có thể xử lý. Nếu nghiệp vụ yêu cầu quyền hoàn tiền là bắt buộc để thực hiện tác vụ, issuer nên từ chối thay vì trả token khiến client hiểu nhầm giao dịch đã được cấp đủ quyền.

JWT payload sau khi cấp có thể là:

~~~json
{
  "iss": "https://auth.example.net",
  "sub": "user-84",
  "aud": "https://api.example.net/orders",
  "client_id": "dashboard",
  "tenant_id": "tenant-a",
  "scope": "orders:read orders:update",
  "iat": 1900000000,
  "exp": 1900000600
}
~~~

Token không chứa `orders:refund` vì quyền đó không được cấp. Orders API vẫn phải xác minh token, kiểm tra scope và xác thực quyền của subject trên đơn hàng cụ thể.

## 13. Kiểm thử chống phát hành vượt quyền

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Client yêu cầu scope không thuộc allowlist | Từ chối hoặc bỏ phần không hợp lệ theo hợp đồng; không cấp quyền |
| Client yêu cầu scope rộng hơn grant | Downscope rõ ràng hoặc từ chối |
| Subject không có permission | Không cấp permission đó dù client yêu cầu |
| Client không được đăng ký scope | Không cấp scope |
| Consent bị thu hồi | Từ chối quyền delegated bị thu hồi |
| Audience không được phép | Từ chối phát hành cho resource đó |
| Tenant không thuộc subject | Từ chối hoặc yêu cầu chọn tenant hợp lệ |
| Request gửi `role=admin` | Không ảnh hưởng claim quyền |
| Request thiếu scope | Không tự cấp full access; chỉ dùng default tối thiểu đã định nghĩa |
| Refresh yêu cầu scope mới | Không tự mở rộng grant |
| Quyền đã bị thu hồi trước refresh | Token mới không được mang quyền cũ |
| Policy engine không phản hồi | Fail-safe theo chính sách; không fallback sang quyền mặc định rộng |
| Scope chứa wildcard | Chỉ cấp nếu wildcard được định nghĩa và policy cho phép |
| Token có nhiều audience không cần thiết | Từ chối hoặc giới hạn theo profile |

Nên kiểm thử thêm các trường hợp tổ hợp: subject có quyền nhưng client không có; client có quyền nhưng consent thiếu; quyền hợp lệ ở tenant A nhưng request nhắm tenant B; scope hợp lệ với API A nhưng audience là API B; và token đã phát hành trước khi permission bị thu hồi.

## 14. Các sai lầm cần tránh

- Sao chép scope hoặc role từ request vào JWT.
- Cấp toàn bộ role của người dùng thay vì tính permission theo audience và mục đích.
- Coi scope yêu cầu là quyền đã được cấp.
- Dùng wildcard hoặc `admin` làm default.
- Không giao nhau giữa quyền subject, client, grant, consent và resource policy.
- Cho phép audience tùy ý hoặc token dùng chung giữa các API.
- Coi scope là quyền truy cập mọi object trong resource.
- Cấp quyền của user cho service-to-service chỉ vì client gửi user ID.
- Dùng refresh token để mở rộng scope mà không có authorization/consent mới.
- Không tính lại quyền khi refresh hoặc token exchange.
- Dùng cache quyền không ràng buộc tenant hoặc không kiểm tra độ mới.
- Khi policy engine lỗi, fallback sang tập quyền rộng.
- Không trả rõ scope thực tế đã cấp cho client.
- Không có kiểm thử negative case chống privilege escalation.

## 15. Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): tham số scope, authorization grant và quy tắc cấp access token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo vệ OAuth, refresh token và quyền truy cập.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token và các claim liên quan đến quyền.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): chỉ định resource/audience dự kiến cho access token.
- [RFC 9396 — OAuth 2.0 Rich Authorization Requests](https://www.rfc-editor.org/rfc/rfc9396): biểu diễn yêu cầu quyền chi tiết qua authorization details.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): subject, actor và giới hạn delegation khi trao đổi token.

**Ghi nhớ:** Token chỉ nên mang tập quyền nhỏ nhất đủ đáp ứng mục đích, sau khi đã giao nhau giữa yêu cầu, quyền của subject, client, grant/consent, resource và tenant. Request không phải quyết định authorization; JWT có chữ ký hợp lệ cũng không thể hợp thức hóa việc cấp quyền vượt mức.

