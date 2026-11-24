# Delegation và token đại diện cho ai?

Trong hệ thống dùng OAuth 2.0, OpenID Connect (OIDC) và API, một ứng dụng có thể truy cập dữ liệu **thay mặt người dùng**, hoặc truy cập bằng **quyền của chính ứng dụng**. Cả hai trường hợp đều có thể dùng access token, nhưng hai mô hình tin cậy hoàn toàn khác nhau. Nếu API chỉ thấy “token hợp lệ” rồi mặc định token đại diện cho người đang đăng nhập, hệ thống rất dễ cấp nhầm quyền.

Hãy tưởng tượng Mai cho phép ứng dụng **ReportHub** đọc các hóa đơn của mình để lập báo cáo. Khi ReportHub gọi Invoice API, có ít nhất ba danh tính liên quan:

- **Mai**: người có dữ liệu và có thể cấp quyền để ứng dụng truy cập.
- **ReportHub**: ứng dụng đang thực hiện yêu cầu.
- **Invoice API**: tài nguyên nhận token và quyết định có trả hóa đơn hay không.

**Delegation (ủy quyền thực hiện thay)** là việc một chủ thể cho phép một chủ thể khác thực hiện những hành động **có giới hạn**, theo chính sách đã định, thay mặt mình. Ủy quyền truy cập không đồng nghĩa chuyển giao toàn bộ danh tính, mật khẩu, hay mọi quyền của người dùng cho ứng dụng.

Mục tiêu của bài này là xác định **token đại diện cho chủ thể nào**, ai đang **thực sự sử dụng token**, quyền được **ủy quyền từ đâu**, và API cần kiểm tra gì để không nhầm **quyền của người dùng** với **quyền của ứng dụng/dịch vụ**.

## 1. Tách bốn câu hỏi trong mô hình tin cậy

Trước khi diễn giải một access token, hãy trả lời bốn câu hỏi độc lập:

| Câu hỏi | Ý nghĩa | Ví dụ |
|---|---|---|
| **Ai phát hành token?** | Issuer / Authorization Server (AS) mà API cấu hình tin cậy | `https://auth.example.test` |
| **Token mô tả chủ thể nào?** | Subject và các thuộc tính được AS khẳng định; có thể là người dùng **hoặc** client/service | `user:mai` |
| **Ứng dụng nào được cấp token?** | OAuth client được AS cấp token; không nhất thiết là chủ thể của dữ liệu | `reporthub-web` |
| **Token dành cho ai dùng và để làm gì?** | Audience, scope và chính sách truy cập tài nguyên | `invoice-api`, `invoice:read` |

Một câu hỏi thứ năm rất quan trọng là **ai đang cầm token tại thời điểm gọi API?** Với **bearer token**, bên nào có được token có thể thử sử dụng nó; nếu bị đánh cắp, token có thể bị dùng bởi kẻ tấn công. Bởi vậy, việc token có `sub=user:mai` **không tự chứng minh** HTTP request hiện tại do Mai trực tiếp gửi.

Các vai trò cần phân biệt:

- **Resource owner**: chủ thể có quyền kiểm soát việc truy cập tài nguyên được bảo vệ. Trong nhiều ứng dụng là người dùng như Mai, nhưng không bắt buộc luôn là người.
- **Client**: phần mềm xin và dùng access token, chẳng hạn ReportHub. Client có thể là ứng dụng di động, frontend, backend hoặc một dịch vụ tự động.
- **Authorization Server (AS)**: phát hành token theo grant, chính sách, quyền đã cho phép và cách xác thực phù hợp.
- **Resource Server (RS)**: API chứa dữ liệu và kiểm token lẫn quyền trên tài nguyên cụ thể.
- **Subject**: chủ thể mà một token/claim mô tả. Ý nghĩa chi tiết phải được đọc theo **loại token** và **hợp đồng với issuer**.
- **Actor**: bên hành động **thay mặt** subject, nếu cơ chế ủy quyền có biểu diễn vai trò này; không phải token nào cũng có actor claim.

Trong các hệ thống đơn giản, subject và client đôi lúc có vẻ là một. Trong hệ thống có người dùng, đối tác, gateway và nhiều microservice, chúng thường **khác nhau**.

## 2. Delegation diễn ra như thế nào trong OAuth 2.0?

OAuth 2.0 cung cấp cơ chế để client nhận access token có phạm vi truy cập nhất định từ AS. Với một luồng có người dùng, ứng dụng có thể được cấp quyền truy cập dữ liệu của người dùng mà **không cần nhận mật khẩu của họ**.

Ví dụ về một luồng **Authorization Code + PKCE**:

~~~mermaid
sequenceDiagram
    autonumber
    actor Mai as Mai (resource owner)
    participant App as ReportHub (client)
    participant AS as Authorization Server
    participant API as Invoice API (resource server)
    Mai->>App: Chọn kết nối dữ liệu hóa đơn
    App-->>Mai: Chuyển tới AS để xác thực/cấp quyền
    Mai->>AS: Xác thực và chấp thuận nếu cần
    AS-->>App: Authorization code qua redirect
    App->>AS: Đổi code kèm code_verifier
    AS-->>App: Access token với phạm vi đã cấp
    App->>API: GET /invoices với access token
    API->>API: Kiểm token, audience, scope và chính sách dữ liệu
    API-->>App: Trả hóa đơn được phép hoặc từ chối
~~~

Ở đây, Mai có thể cho ReportHub quyền **đọc hóa đơn**, nhưng không cho **xóa hóa đơn**. Access token mà ReportHub nhận được thường phản ánh các giới hạn do AS quyết định, ví dụ `invoice:read`, `aud=invoice-api` và thời hạn ngắn.

Tuy nhiên, cần hiểu đúng ba điểm:

1. **Đồng ý của người dùng (consent) không phải là nguồn cấp quyền duy nhất.** AS còn phải kiểm chính sách tổ chức, quyền sẵn có của resource owner, quyền được phép của client và giới hạn của grant. Có hệ thống dùng quyền phê duyệt của quản trị viên hoặc chính sách đã thiết lập mà không hiển thị màn hình consent cho mỗi lần.
2. **PKCE bảo vệ việc đổi authorization code**, đặc biệt trước việc đánh cắp code trong một số kịch bản. PKCE không tự trả lời ReportHub được đọc hóa đơn nào, cũng không biến access token thành chứng minh người gọi hiện tại là Mai.
3. **API vẫn thực thi phân quyền.** Dù AS cấp scope `invoice:read`, API phải đối chiếu hóa đơn thuộc ai, tenant nào và giới hạn theo chính sách kinh doanh.

### Delegation không đồng nghĩa đăng nhập

**Authentication** trả lời “ai đã được xác thực, bằng chứng nào?”. **Authorization/delegation** trả lời “ai cho phép ứng dụng thực hiện hành động gì?”. OAuth 2.0 tập trung vào cấp quyền truy cập; **OIDC** bổ sung lớp xác thực và **ID token** để client xác định thông tin đăng nhập của người dùng.

Một ID token hợp lệ cho ReportHub **không** phải là vé gọi Invoice API. API cần một **access token dành cho chính API**, với audience và quyền phù hợp.

## 3. Đọc claims: token đại diện cho ai?

Không được suy danh tính chỉ từ việc token là JWT. JWT là **định dạng** có thể mang claims; access token có thể là JWT hoặc opaque token. Với JWT, resource server xác minh chữ ký, issuer, audience, thời hạn và các ràng buộc của profile token trước khi tin claims. Với opaque token, resource server lấy thông tin từ cơ chế tra cứu/introspection đáng tin cậy.

### Trường hợp A: ứng dụng được ủy quyền truy cập dữ liệu người dùng

Ví dụ payload của một **JWT access token** do AS cấp theo một hợp đồng xác định:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user:mai",
  "aud": "invoice-api",
  "client_id": "reporthub-web",
  "scope": "invoice:read",
  "tenant_id": "company-a",
  "iat": 1800000000,
  "exp": 1800000900
}
~~~

Ý nghĩa theo hợp đồng ví dụ:

- `iss`: AS đã phát hành token, là **nguồn tin cậy** sau khi được xác minh.
- `sub`: subject được token mô tả là **Mai**.
- `client_id`: client nhận quyền truy cập là **ReportHub**. Claim này xuất hiện theo profile/hợp đồng phát hành, không phải JWT nào cũng có.
- `aud`: token dành cho **Invoice API**, không được tự ý chuyển sang các API có audience khác.
- `scope`: khả năng truy cập đã được AS cấp, ở đây là **đọc hóa đơn**.
- `tenant_id`: thuộc tính riêng của hệ thống, phải do issuer đáng tin cậy bảo đảm và được API đối chiếu với dữ liệu thực.
- `iat`, `exp`: thời gian phát hành và hết hạn; các số ở đây chỉ để minh họa.

**Cách đọc đúng:** Token này cho biết AS cấp cho client ReportHub một access token liên quan đến subject Mai, có phạm vi `invoice:read` và audience Invoice API. Nó **không nói rằng Mai đang trực tiếp gửi từng HTTP request**, cũng không tự cấp quyền đọc hóa đơn của người khác.

Chú ý: Claim `sub` không luôn mang cùng một loại đối tượng trong mọi grant/profile. Claim `client_id` giúp nhận diện client được cấp token **khi issuer thực sự phát hành và bảo đảm claim đó**; với bearer token, claim này không tự chứng minh tiến trình hiện cầm token chính là client hợp pháp.

### Trường hợp B: service gọi API với quyền của chính mình

Một tác vụ chạy lịch `billing-batch` dùng grant **client_credentials** để xin access token. Luồng này có thể không có người dùng cuối:

~~~mermaid
sequenceDiagram
    participant Job as billing-batch (client)
    participant AS as Authorization Server
    participant API as Invoice API
    Job->>AS: Xác thực client + xin token với client_credentials
    AS-->>Job: Access token dành cho Invoice API
    Job->>API: Gọi API với access token
    API->>API: Kiểm token và quyền của service
    API-->>Job: Cho phép hoặc từ chối theo chính sách service
~~~

Payload JWT minh họa theo hợp đồng riêng của AS:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "service:billing-batch",
  "client_id": "billing-batch",
  "aud": "invoice-api",
  "scope": "invoice:reconcile",
  "exp": 1800000900
}
~~~

Trong ví dụ này, `sub` đại diện cho **service**, không phải Mai. Quy ước `service:...` là do hệ thống tự đặt; các profile access token khác có thể dùng biểu diễn khác. API phải dựa trên **hợp đồng phát hành token**, không dựa trên tiền tố minh họa.

Nếu client credentials của `billing-batch` hợp lệ, điều đó chỉ chứng minh client được AS chấp nhận và cấp token. Nó **không** cho phép service giả danh một người dùng tùy ý hoặc đọc dữ liệu ngoài quyền của service.

### So sánh nhanh các ngữ cảnh

| Tình huống | Subject/ngữ cảnh quyền | Client nhận token | Có người dùng cuối không? | API nên kiểm gì? |
|---|---|---|---|---|
| Mai cho ReportHub đọc hóa đơn | Quyền liên quan đến Mai, trong phạm vi AS cấp | ReportHub | Có | Token hợp lệ; scope; tenant; quyền sở hữu dữ liệu; chính sách với client nếu áp dụng |
| Job tự động đối soát hóa đơn | Quyền của service `billing-batch` | `billing-batch` | Không bắt buộc | Audience, scope và chính sách riêng cho service |
| Dịch vụ A gọi B **thay mặt Mai** | Mai là subject; có thể cần thể hiện actor là A | Dịch vụ A hoặc downstream client theo cơ chế cấp token | Có thể có | Quyền của Mai **và** quyền được phép của actor/client; audience của B; ràng buộc ủy quyền |
| Mai đăng nhập vào ReportHub bằng OIDC | ID token mô tả sự kiện xác thực của Mai | ReportHub | Có | **Client** kiểm ID token theo OIDC; không chuyển ID token thành access token của API |

## 4. Chủ thể được đại diện và bên đang hành động là hai vai trò khác nhau

Trong một hệ thống nhiều dịch vụ, câu nói “service A gọi service B thay mặt Mai” có hai lớp ý nghĩa:

- **Subject (on behalf of whom):** Mai là người có quyền gốc đối với một số dữ liệu.
- **Actor (who is acting):** service A là thành phần thực hiện thao tác để đáp ứng yêu cầu của Mai.

Nếu hệ thống chỉ chuyển một chuỗi `user_id=mai` trong HTTP header, B không có bằng chứng đáng tin rằng A thực sự có quyền đại diện cho Mai. Header do client tự khai báo không phải một cơ chế delegation an toàn.

Hệ thống có thể dùng **token exchange** (RFC 8693), hoặc cơ chế cấp token downstream tương đương được AS và các API hỗ trợ. Theo mô hình token exchange, A nộp token đầu vào cùng thông tin cần thiết cho AS; AS đánh giá chính sách và có thể cấp token mới **dành riêng cho B** với actor/subject/phạm vi thích hợp.

~~~mermaid
sequenceDiagram
    autonumber
    actor Mai as Mai
    participant Front as Web app
    participant A as Report Service (A)
    participant AS as Authorization Server
    participant B as Invoice API (B)
    Mai->>Front: Yêu cầu lập báo cáo
    Front->>A: Yêu cầu kèm token dành cho A
    A->>A: Kiểm token và quyền gọi A
    A->>AS: Xin token downstream cho B theo chính sách
    AS->>AS: Xác thực client, kiểm nguồn và giới hạn delegation
    AS-->>A: Access token mới, aud=B, scope giới hạn
    A->>B: Gọi API bằng token dành cho B
    B->>B: Xác minh token và quyền trên hóa đơn
    B-->>A: Dữ liệu được phép hoặc từ chối
    A-->>Front: Báo cáo
~~~

Trong kịch bản này, **không nên lấy nguyên token dành cho A gửi sang B** khi audience không khớp. Token downstream phải được AS phát hành cho B hoặc được cấp bằng cơ chế mà B thực sự tin cậy. Token exchange là một lựa chọn **tùy mức độ hỗ trợ của AS**; không phải mọi hệ thống OAuth 2.0 đều hỗ trợ.

### Claim `act` có ý nghĩa gì?

Một security token có thể ghi rõ actor hiện tại bằng claim `act` theo cơ chế token exchange. Ví dụ minh họa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user:mai",
  "act": {
    "sub": "service:reporting"
  },
  "aud": "invoice-api",
  "scope": "invoice:read",
  "tenant_id": "company-a",
  "exp": 1800000900
}
~~~

Khi AS và resource server thống nhất dùng `act`, cách đọc là: **service reporting đang hành động thay mặt Mai** trong phạm vi token này. `sub` vẫn mô tả chủ thể được đại diện; `act.sub` mô tả actor. Các chain có nhiều actor có thể được biểu diễn sâu hơn theo profile token, nhưng API chỉ được dùng các trường mà cơ chế tin cậy của nó thực sự định nghĩa và kiểm chứng.

**Không tự thêm `act`, `sub` hoặc `scope` vào payload rồi coi như đã ủy quyền.** Phải có quyết định phát hành từ AS đáng tin cậy và token còn hợp lệ cho audience nhận. Sự xuất hiện của `act` không tự quyết định actor được làm gì; resource server vẫn phải áp dụng chính sách.

Một điểm dễ nhầm khác: trong OIDC, **`azp` (authorized party)** có ngữ nghĩa riêng ở ID token. Không nên dùng `azp` như cách thay thế chung cho `client_id` hoặc `act` trên mọi access token. Trường nào có giá trị phải dựa trên token profile đang triển khai.

## 5. Delegation khác impersonation như thế nào?

Hai thuật ngữ thường bị trộn lẫn:

| Đặc điểm | Delegation (ủy quyền thay mặt) | Impersonation (thực thi như một danh tính khác) |
|---|---|---|
| Ý tưởng | Một actor được trao khả năng thực hiện một số việc thay subject | Hệ thống cho một actor vận hành dưới danh tính/quyền của chủ thể khác |
| Dấu vết chủ thể | Thiết kế tốt giữ thông tin **subject và actor** khi có thể | Có thể khó phân biệt actor thực sự nếu bị thay hoàn toàn danh tính |
| Phạm vi quyền | Thường giới hạn theo hành động, tài nguyên, audience và thời gian | Có thể rộng nếu hệ thống triển khai không chặt |
| Rủi ro | Vượt scope, chuyền token sai audience, nhầm quyền của client và user | Mạo danh ngoài ý muốn, mất tính truy vết và vượt quyền |
| Kiểm soát cần có | AS kiểm chính sách ủy quyền; API thực thi quyền đối tượng | Cần quyền đặc biệt, giới hạn rõ ràng, ghi audit actor thực và cơ chế cho phép |

**Không được coi mọi delegation là impersonation.** Ví dụ, ReportHub chỉ cần đọc hóa đơn để lập báo cáo; nó không nên được phép đổi mật khẩu, thay hồ sơ hay ký giao dịch như Mai. Nếu ứng dụng hỗ trợ nhân viên hỗ trợ đăng nhập “với tư cách khách hàng”, cần chính sách impersonation riêng, thời hạn rõ, quyền giới hạn và audit cho biết nhân viên nào thực hiện thao tác.

### Quyền hiệu lực là giao của các giới hạn

Trong một ứng dụng có chính sách phù hợp, quyết định cho phép thường phải đáp ứng đồng thời:

~~~text
ChoPhep(yeu_cau) =
    token_duoc_xac_minh
    AND token_danh_cho_API_nay
    AND scope_cho_phep_hanh_dong
    AND subject_co_quyen_tren_tai_nguyen
    AND client_or_actor_duoc_phep_thuc_hien
    AND tenant_va_dieu_kien_nghiep_vu_hop_le
~~~

Đây là **mẫu tư duy**, không phải công thức cố định của mọi API. Với `client_credentials` không có user, chính sách sẽ dùng quyền của service thay cho điều kiện về subject là người dùng. Quan trọng là không mặc định **quyền của Mai + quyền của ReportHub = hợp mọi quyền của hai bên**. Một cách thiết kế an toàn là chỉ cho phép những hành động đáp ứng **đồng thời** các giới hạn thích hợp của mỗi bên.

Ví dụ:

- Mai có quyền đọc hóa đơn số 42 nhưng không có quyền xóa.
- ReportHub được AS cấp scope `invoice:read`, không có `invoice:delete`.
- Invoice API kiểm hóa đơn 42 thuộc tenant và quan hệ sở hữu hợp lệ của Mai.

**Đọc** hóa đơn 42 có thể được cho phép; **xóa** phải bị từ chối dù Mai đã từng đăng nhập thành công và ReportHub đang giữ token hợp lệ.

## 6. Kiểm tra quyền tại API: mã giả thực tế

API nên tách việc **xác thực token** khỏi việc **ra quyết định phân quyền**. Ví dụ API đọc hóa đơn có thể áp dụng hợp đồng sau:

~~~text
function getInvoice(request, accessToken, invoiceId):
    ctx = validateAccessToken(
        accessToken,
        expectedIssuer = "https://auth.example.test",
        expectedAudience = "invoice-api",
        requiredTokenPurpose = "access"
    )
    if ctx.invalidOrExpired:
        return HTTP_401

    if not ctx.scopes.contains("invoice:read"):
        return HTTP_403

    invoice = repository.findInvoiceById(invoiceId)
    if invoice == null:
        return HTTP_404

    if invoice.tenantId != ctx.verifiedTenantId:
        return HTTP_403_or_404_by_policy

    if ctx.grantContext == "delegated_user":
        if not policy.userMayReadInvoice(ctx.subject, invoice):
            return HTTP_403_or_404_by_policy
        if not policy.clientMayActForUser(ctx.clientId, ctx.subject, invoice):
            return HTTP_403
        if ctx.actor != null and not policy.actorIsAllowed(ctx.actor, invoice):
            return HTTP_403
    else if ctx.grantContext == "service":
        if not policy.serviceMayReadInvoice(ctx.servicePrincipal, invoice):
            return HTTP_403
    else:
        return HTTP_403

    audit.record(
        subject = ctx.subject,
        clientId = ctx.clientId,
        actor = ctx.actor,
        resource = invoiceId,
        action = "invoice:read"
    )
    return HTTP_200_with_invoice
~~~

Các trường `grantContext`, `verifiedTenantId` và `servicePrincipal` ở đây là **ngữ cảnh đã được API xác minh/xây dựng theo hợp đồng với AS**, không phải các trường OAuth/JWT tiêu chuẩn luôn có sẵn. Không suy `grantContext` từ một header tùy ý do client gửi, hoặc đoán “có `sub` là token người dùng”.

Với dữ liệu nhiều tenant, nên giới hạn truy vấn ngay theo tenant được phép, kết hợp kiểm quyền từng bản ghi. API có thể chọn **404** thay cho **403** khi muốn hạn chế tiết lộ tài nguyên tồn tại; lựa chọn mã phản hồi không thay thế kiểm tra quyền.

## 7. Các ranh giới tin cậy trong đường đi của token

| Ranh giới | Câu hỏi tin cậy | Kiểm soát cần có |
|---|---|---|
| **Người dùng → AS** | Người dùng được xác thực đúng chưa? Có quyền cho phép client truy cập không? | Phương thức AuthN phù hợp, kiểm chính sách và consent/phê duyệt khi cần |
| **Client → AS** | Client có đúng danh tính, được dùng grant và scope này không? | Xác thực client khi áp dụng, PKCE trong luồng phù hợp, hạn chế redirect, chính sách cấp token |
| **AS → Client** | Token có bị lộ trong quá trình nhận và lưu không? | TLS, nơi lưu an toàn, giảm thời hạn và scope, không ghi token vào log/URL |
| **Client → Resource Server** | Token do AS tin cậy cấp, còn hiệu lực, đúng audience không? | Xác minh chữ ký/claims hoặc introspection; kiểm scope và trạng thái |
| **Resource Server → Dữ liệu** | Chủ thể/client/actor có thực sự được phép thao tác lên đối tượng này không? | Kiểm quyền từng đối tượng, tenant, chính sách nghiệp vụ; audit |
| **Service A → Service B** | A có quyền gọi B thay subject không? B có chấp nhận token này không? | Token dành cho B, giới hạn delegation và actor; không chuyền nhầm token audience A |

**Bearer token và token bị đánh cắp:** Nếu ReportHub lưu access token ở nơi dễ bị XSS, log hoặc rò rỉ qua đường truyền, kẻ khác có thể thử gọi API bằng token đó. API vẫn có thể thấy `sub=user:mai` và `client_id=reporthub-web` trong token hợp lệ, mặc dù request thực tế đến từ kẻ tấn công.

Để giảm rủi ro:

1. Áp dụng **HTTPS/TLS**, bảo vệ dữ liệu trong nơi lưu và tránh đưa token vào URL, analytics hay log.
2. Giới hạn **scope**, **audience** và **thời hạn**; không tái sử dụng một token cho mọi API.
3. Xem xét **sender-constrained access token** (ví dụ mTLS hoặc DPoP) khi hệ thống hỗ trợ để giảm khả năng dùng lại token đã bị đánh cắp. Cơ chế này cần resource server kiểm đúng bằng chứng ràng buộc.
4. Sử dụng chính sách **thu hồi**, introspection, token sống ngắn hoặc đối chiếu trạng thái phiên/quyền tùy kiến trúc. Token JWT tự xác minh chữ ký có thể vẫn hợp lệ cho đến khi hết hạn nếu không có kiểm soát bổ sung.
5. Giới hạn và bảo vệ **refresh token**, vì nó có thể được dùng để xin access token mới. Không gửi refresh token đến resource API hay dịch vụ downstream không có chức năng làm mới token.
6. Ghi audit đầy đủ **subject, client, actor (nếu có), tài nguyên, hành động, kết quả**, trong khi tránh ghi toàn bộ token hoặc dữ liệu bí mật.

## 8. Những sai lầm thường dẫn tới vượt quyền

| Cách hiểu hoặc triển khai sai | Nguy cơ | Cách sửa đúng |
|---|---|---|
| “Token có `sub=Mai` nên request chắc chắn do Mai gửi” | Người giữ bearer token bị đánh cắp được xem là Mai | Xác minh token; bảo vệ nơi lưu, thời hạn, áp dụng ràng buộc người gửi khi phù hợp; không suy nguồn phát request chỉ từ `sub` |
| “Client giữ token thì được dùng toàn bộ quyền của user” | Client vượt scope, truy cập bản ghi sai hoặc lạm dụng quyền | Kiểm scope **và** chính sách resource owner/tenant/actor |
| “Mọi access token đều đại diện người dùng cuối” | Quyền của `client_credentials` bị nhầm thành quyền người dùng | Phân biệt grant/ngữ cảnh chủ thể theo hợp đồng token; policy riêng cho service |
| “Có thể chuyển token của service A sang B” | Token dùng sai audience, tăng rủi ro lộ quyền | B kiểm audience; dùng cơ chế cấp token dành cho B khi cần |
| “Header `X-User-Id` là bằng chứng được ủy quyền” | Client tự giả mạo người dùng | Chỉ tin context do cơ chế xác thực/ủy quyền đáng tin cung cấp |
| “Có `act` thì không cần kiểm actor” | Service chưa được phép vẫn hành động thay user | Kiểm actor và phạm vi delegation theo chính sách resource server |
| “Consent nghĩa là API phải chấp nhận mọi truy cập” | Bỏ qua ràng buộc quyền đối tượng, tenant và thời điểm | AS quyết định cấp token; RS vẫn thực thi chính sách từng yêu cầu |
| “Dùng ID token thay access token cho API” | Nhầm mục đích và audience token, có nguy cơ token confusion | Client dùng ID token cho mục đích OIDC; API dùng access token dành cho API |
| “Chỉ cần xác minh chữ ký JWT” | Token sai issuer, audience, hết hạn hoặc mục đích vẫn được chấp nhận | Kiểm đầy đủ chính sách token, loại token/profile, scope và quyền dữ liệu |

Một biến thể nguy hiểm là **confused deputy**: dịch vụ có quyền mạnh bị bên ít quyền lừa thực hiện hành động vượt quyền bằng cách truyền tham số hoặc token không phù hợp. Để phòng tránh, dịch vụ phải xác định **ai đang yêu cầu**, **hành động thay ai**, **token dành cho dịch vụ nào**, và **quyền thực tế trên tài nguyên** trước khi thực hiện.

## 9. Tình huống kiểm tra hiểu biết

Giả sử:

- Mai thuộc tenant A, sở hữu hóa đơn **#42**.
- Bình thuộc tenant B, sở hữu hóa đơn **#99**.
- ReportHub được cấp access token liên quan đến Mai với scope `invoice:read`, audience `invoice-api`.
- BillingBatch là một service có token từ `client_credentials` với scope `invoice:reconcile`.

Hãy xác định kỳ vọng của API:

| Yêu cầu | Token/ngữ cảnh | Kết quả hợp lý |
|---|---|---|
| ReportHub đọc hóa đơn #42 | Token của Mai, đúng scope/tenant; chính sách cho phép client đọc | **Cho phép**, nếu các điều kiện và token đều hợp lệ |
| ReportHub xóa hóa đơn #42 | Token chỉ có `invoice:read` | **Từ chối** vì không có quyền xóa |
| ReportHub đọc hóa đơn #99 | Token của Mai thuộc tenant A | **Từ chối** theo chính sách tenant/quyền dữ liệu |
| BillingBatch yêu cầu đối soát đúng tập hóa đơn được phép | Token service có `invoice:reconcile`; chính sách cho phép service | **Có thể cho phép**, không cần tự gán danh tính Mai |
| BillingBatch gửi header `X-User-Id: user:mai` để gọi chức năng dành riêng cho Mai | Header không chứng minh delegation | **Từ chối** nếu không có ngữ cảnh ủy quyền đáng tin cậy |
| Report Service A mang token có `aud=report-api` gọi Invoice API B | Token không dành cho B | **Từ chối** token vì audience sai |

**Bài tập suy luận:** API kiểm chữ ký và `exp` thành công, nhìn thấy `sub=user:mai` rồi trả hóa đơn #99. Lỗi nào xảy ra?

**Đáp án:** API mới chỉ xác minh một phần ngữ cảnh token; nó chưa kiểm **audience/mục đích token** đầy đủ và, quan trọng trong tình huống này, chưa thực thi **quyền trên hóa đơn thuộc tenant B**. Dù JWT hợp lệ và subject đúng là Mai, quyền đọc hóa đơn của Bình không phát sinh tự động.

## 10. Checklist khi thiết kế API dùng delegation

Trước khi cho phép một yêu cầu, đội phát triển nên xác định:

1. **Loại token:** Đây có phải **access token** đúng profile dành cho API, hay là ID token/refresh token bị dùng nhầm?
2. **Nguồn phát hành:** Token được xác minh bằng khóa/thuật toán tin cậy hoặc introspection? `iss`, thời gian và trạng thái có hợp lệ?
3. **Đích nhận:** `aud` có bao gồm API hiện tại? Token có bị chuyển qua nhầm service?
4. **Subject:** Token đại diện cho **user** hay **client/service** theo hợp đồng issuer?
5. **Client/actor:** Ứng dụng nào được cấp token và actor nào thực sự được hệ thống cho phép hành động thay subject? Có cơ chế chứng minh phù hợp, hay chỉ là thông tin tự khai báo?
6. **Quyền:** Scope và chính sách cấp quyền có cho phép hành động này? Người dùng và actor/client có thỏa các giới hạn áp dụng không?
7. **Tài nguyên:** Đối tượng cần truy cập có thuộc đúng owner, tenant và bối cảnh kinh doanh không?
8. **Vòng đời:** Khi quyền bị gỡ, token hết hạn hoặc bị đánh cắp, cơ chế nào giới hạn thời gian và phạm vi lạm dụng?
9. **Truy vết:** Có thể audit đúng subject, client, actor và quyết định phân quyền mà không làm lộ token không?

**Kết luận:** Trong mô hình tin cậy của token security, “token đại diện cho ai?” không thể trả lời chỉ bằng việc đọc một trường `sub`. Cần đặt token vào **grant, issuer, audience, client, subject, actor và chính sách tài nguyên**. Delegation an toàn là quyền truy cập **có phạm vi và có thể kiểm tra**, giúp client hành động thay chủ thể trong giới hạn rõ ràng mà không nhầm quyền của người dùng, ứng dụng và dịch vụ.
