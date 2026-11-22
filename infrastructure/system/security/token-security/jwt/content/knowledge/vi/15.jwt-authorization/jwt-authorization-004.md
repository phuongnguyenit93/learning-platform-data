# Kiểm tra quyền tại tài nguyên thay vì chỉ kiểm tra có JWT

## 1. JWT hợp lệ chưa có nghĩa là được truy cập mọi tài nguyên

Một API có thể xác minh access token dạng JSON Web Token (JWT) thành công: chữ ký đúng, issuer đáng tin cậy, audience phù hợp, token chưa hết hạn và mục đích sử dụng đúng. Kết quả đó cho biết API có thể tin vào danh tính hoặc chủ thể được token đại diện trong phạm vi đã xác minh.

Nhưng câu hỏi tiếp theo vẫn phải được trả lời: **chủ thể này có được phép thực hiện hành động cụ thể trên đúng tài nguyên đang yêu cầu hay không?**

Giả sử một nhân viên có access token hợp lệ với:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-514",
  "aud": "https://api.example.test/billing",
  "scope": "invoice:read",
  "tenant_id": "company-a"
}
~~~

Nhân viên gọi:

~~~http
GET /invoices/INV-100 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

Token hợp lệ và có scope đọc hóa đơn chỉ chứng minh rằng request vượt qua các điều kiện xác thực và có thể yêu cầu thao tác đọc trong phạm vi API. Nó **không chứng minh** hóa đơn INV-100 thuộc về người gọi, thuộc tổ chức được phép, đang ở trạng thái có thể đọc hoặc không bị một quy tắc nghiệp vụ giới hạn.

Nếu hóa đơn thuộc company-b, thuộc người dùng khác hoặc bị giới hạn theo chính sách, API phải từ chối dù JWT hoàn toàn hợp lệ.

Quy tắc cốt lõi:

> **Xác minh JWT để nhận diện chủ thể; kiểm tra quyền trên từng tài nguyên và từng hành động trước khi thực thi.**

Bài học này thuộc phạm vi Security chung của JSON Web Token (JWT), áp dụng cho API và hệ thống phân tán nói chung, không phụ thuộc một ngôn ngữ lập trình hoặc framework cụ thể.

## 2. Phân biệt xác thực, quyền ở endpoint và quyền ở tài nguyên

Ba lớp kiểm soát thường bị nhầm lẫn:

| Lớp kiểm soát | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Xác thực (authentication)** | Token có hợp lệ và chủ thể được xác nhận là ai? | JWT được ký bởi issuer tin cậy, sub = user-514. |
| **Quyền ở chức năng/endpoint** | Chủ thể có được gọi loại chức năng này không? | Token có scope invoice:read để yêu cầu API đọc hóa đơn. |
| **Quyền ở tài nguyên (object-level authorization)** | Chủ thể có được làm hành động đó trên đúng đối tượng này không? | user-514 được đọc INV-100 vì là người sở hữu hoặc có quan hệ kiểm toán phù hợp. |

Một endpoint có thể được bảo vệ ở lớp thứ nhất và thứ hai nhưng vẫn mắc lỗi ở lớp thứ ba.

### 2.1. Ví dụ endpoint đã bảo vệ nhưng tài nguyên chưa được bảo vệ

Giả sử API có kiểm tra:

~~~text
1. Request phải có JWT hợp lệ.
2. Token phải có scope invoice:read.
3. Nếu hai điều kiện đúng, đọc hóa đơn theo invoiceId trong URL.
~~~

Một người dùng hợp lệ có thể thay:

~~~text
/invoices/INV-100
~~~

thành:

~~~text
/invoices/INV-101
~~~

Nếu API chỉ tải hóa đơn theo ID và trả kết quả, người dùng có thể xem hóa đơn của người khác. Đây là lỗi kiểm soát quyền truy cập đối tượng dù endpoint đã yêu cầu đăng nhập và scope.

**ID trong URL không phải bằng chứng quyền sở hữu.** ID có thể tuần tự, ngẫu nhiên, UUID hoặc khó đoán; việc khó đoán ID không thay thế kiểm tra quyền.

### 2.2. BOLA và IDOR

**Broken Object Level Authorization (BOLA)** là tên gọi trong OWASP API Security Top 10 cho lỗi API không kiểm tra đầy đủ quyền của chủ thể đối với đối tượng được tham chiếu trong request. **Insecure Direct Object Reference (IDOR)** thường mô tả tình huống ứng dụng cho phép người dùng thao tác đối tượng bằng một định danh trực tiếp mà không kiểm tra quyền phù hợp.

Hai khái niệm có vùng giao nhau lớn: một lỗi IDOR trong API thường là một trường hợp BOLA. Điểm cần nhớ không nằm ở tên gọi mà ở nguyên nhân: **API tin ID đối tượng do client gửi mà không xác minh quan hệ quyền giữa principal và resource**.

Ví dụ thường gặp:

- Thay invoiceId, orderId, documentId hoặc userId trong đường dẫn.
- Thay ID trong JSON body hoặc query parameter.
- Gọi API tải tệp bằng ID tài liệu của người khác.
- Đọc bản ghi qua endpoint lồng như accounts/{accountId}/transactions/{transactionId} mà không kiểm tra quan hệ giữa hai ID.
- Gửi một danh sách ID để xuất hoặc xóa hàng loạt đối tượng ngoài phạm vi quyền.

## 3. Mô hình quyết định: principal, action, resource và context

Một quyết định phân quyền ở mức tài nguyên có thể mô tả bằng:

**Decision = Policy(Principal, Action, Resource, Context)**

- **Principal:** chủ thể được nhận diện từ token đã xác minh, ví dụ cặp (iss, sub), loại chủ thể và thông tin tổ chức.
- **Action:** hành động cụ thể như invoice.read, invoice.update, invoice.approve, document.download.
- **Resource:** đối tượng thực tế được tải từ nguồn dữ liệu đáng tin cậy, gồm ID, tenant, owner, trạng thái và các thuộc tính liên quan.
- **Context:** ngữ cảnh bổ sung như membership hiện hành, quan hệ chia sẻ, mức xác thực, thời gian, trạng thái phiên hoặc điều kiện nghiệp vụ.

Ví dụ chính sách đọc hóa đơn:

~~~text
ALLOW invoice.read khi:
    JWT đã được xác minh cho billing API
    AND token có scope invoice:read
    AND principal là thành viên đang hoạt động của tenant
    AND invoice thuộc tenant đó
    AND (
        principal là owner của invoice
        OR principal có quyền kiểm toán còn hiệu lực trong tenant
    )
    AND invoice không bị khóa theo chính sách

Mọi trường hợp khác: DENY
~~~

Điểm quan trọng là Resource phải là dữ liệu được API lấy từ kho dữ liệu hoặc nguồn quản lý tài nguyên đáng tin cậy. API không được lấy owner_id, tenant_id, classification hoặc approval_state từ request của client rồi coi đó là sự thật.

### 3.1. Danh tính principal từ JWT

Trong nhiều hệ thống, sub chỉ duy nhất trong phạm vi một issuer. Vì vậy, khi ánh xạ chủ thể sang tài khoản nội bộ, nên xét cặp:

~~~text
Principal identity = (iss, sub)
~~~

Không mặc định:

- sub luôn là người dùng con người; nó có thể đại diện tài khoản dịch vụ hoặc một chủ thể khác.
- client_id là danh tính người dùng cuối.
- tenant_id trong token chứng minh tài nguyên bất kỳ thuộc tenant đó.
- Claim role hoặc permission là quyền trên tất cả tài nguyên.

API cần biết loại principal mà endpoint chấp nhận. Ví dụ, một hành động phê duyệt có thể chỉ dành cho người dùng được ủy quyền, trong khi một tác vụ đồng bộ có thể chấp nhận service principal với chính sách riêng.

### 3.2. Scope là điều kiện ở mức khả năng, không phải quyền trên mọi object

Scope invoice:read có thể là điều kiện cần để API thực hiện chức năng đọc. Sau đó, chính sách tài nguyên vẫn quyết định hóa đơn nào được đọc.

~~~text
Token có invoice:read
    ├── Đọc hóa đơn thuộc phạm vi được phép  -> có thể ALLOW
    ├── Đọc hóa đơn của tenant khác          -> DENY
    └── Đọc hóa đơn bị hạn chế                -> DENY
~~~

Nếu API bỏ qua kiểm tra tài nguyên, scope rộng có thể trở thành quyền đọc toàn bộ dữ liệu.

## 4. Xác minh quyền trên tài nguyên theo từng bước

Một luồng kiểm tra có thể triển khai như sau:

1. **Nhận token:** lấy bearer token từ vị trí đã quy định, thường là header Authorization.
2. **Xác minh JWT:** kiểm tra chữ ký, thuật toán cho phép, issuer, audience, thời gian, loại token và schema claims cần thiết.
3. **Tạo principal:** ánh xạ (iss, sub) và loại principal sang danh tính nội bộ đã biết.
4. **Xác định action:** ánh xạ method/route hoặc thao tác nghiệp vụ sang action ổn định như invoice.read; không lấy tên quyền tùy ý từ client.
5. **Kiểm tra quyền chức năng:** scope hoặc giới hạn quyền của token có cho phép yêu cầu action hay không.
6. **Tải resource đáng tin cậy:** lấy đối tượng theo ID và phạm vi dữ liệu; xác định tenant, owner, trạng thái và quan hệ thật.
7. **Đánh giá chính sách:** kết hợp principal, action, resource và context; kiểm tra membership hoặc quyền hiện hành nếu cần.
8. **Thực thi có kiểm soát:** chỉ đọc, sửa, xóa, tải hoặc trả dữ liệu khi quyết định là ALLOW.
9. **Ghi audit phù hợp:** ghi chủ thể, action, resource, kết quả và lý do cần thiết, tránh lưu bearer token.

~~~mermaid
flowchart TD
    A["Request + JWT + resource ID"] --> B{"JWT hợp lệ cho API?"}
    B -- "Không" --> X["401 hoặc từ chối xác thực"]
    B -- "Có" --> C["Tạo principal từ claims đã xác minh"]
    C --> D{"Scope/khả năng cho phép action?"}
    D -- "Không" --> Y["DENY"]
    D -- "Có" --> E["Tải resource từ nguồn dữ liệu tin cậy"]
    E --> F{"Resource tồn tại và thuộc phạm vi tra cứu?"}
    F -- "Không" --> N["404 theo chính sách"]
    F -- "Có" --> G["Đánh giá owner, tenant, relationship, state và context"]
    G --> H{"Policy trả ALLOW?"}
    H -- "Không" --> Y
    H -- "Có" --> I["Thực thi action trên resource"]
~~~

Không phải mọi API đều cần cùng một số bước hoặc cùng một dịch vụ chính sách. Nhưng mỗi request truy cập dữ liệu phải có một quyết định quyền tương ứng với đối tượng thực tế.

## 5. Những mô hình kiểm tra quyền ở mức tài nguyên

### 5.1. Quyền dựa trên chủ sở hữu (ownership)

Chỉ chủ sở hữu mới được thực hiện một số hành động:

~~~text
ALLOW document.read nếu document.owner_id = principal.id
~~~

Ví dụ, người dùng xem hồ sơ cá nhân của mình. owner_id phải lấy từ bản ghi hồ sơ, không lấy từ tham số ownerId mà client tự gửi.

Ownership đơn giản và dễ hiểu, nhưng không đủ cho hệ thống có chia sẻ, cộng tác, quản trị hoặc quan hệ nhiều-nhiều. Người không sở hữu vẫn có thể có quyền thông qua một quan hệ được cấp hợp lệ.

### 5.2. Quyền theo tenant hoặc tổ chức

Trong hệ thống multi-tenant, một chủ thể chỉ được truy cập tài nguyên trong tenant mà họ đang có tư cách phù hợp:

~~~text
ALLOW invoice.read nếu:
    principal có membership active trong tenant T
    AND invoice.tenant_id = T
~~~

Tenant trong token có thể giúp chọn ngữ cảnh, nhưng API vẫn cần xác minh membership hiện hành và đối chiếu tenant của tài nguyên. Không tin tenant ID chỉ vì client đưa vào URL hoặc body.

### 5.3. RBAC - quyền theo vai trò

Role có thể cấp một nhóm permission:

~~~text
role invoice_auditor:
    invoice.read
    invoice.export
~~~

Sau khi xác định role và permission, API vẫn phải giới hạn tài nguyên theo tenant, loại dữ liệu hoặc quan hệ. invoice_auditor của company-a không mặc nhiên có quyền đọc hóa đơn company-b.

### 5.4. ABAC - quyền theo thuộc tính

Attribute-Based Access Control (ABAC) đánh giá các thuộc tính của principal, action, resource và context.

Ví dụ:

~~~text
ALLOW invoice.approve nếu:
    principal.department = "finance"
    AND principal.clearance >= invoice.classification
    AND invoice.amount <= principal.approval_limit
    AND invoice.state = "PENDING"
    AND principal.id != invoice.created_by
~~~

ABAC phù hợp với chính sách phụ thuộc nhiều thuộc tính. Các thuộc tính phải đến từ nguồn có thẩm quyền và được cập nhật theo yêu cầu nhất quán.

### 5.5. ReBAC - quyền theo quan hệ

Relationship-Based Access Control (ReBAC) quyết định dựa trên quan hệ giữa principal và resource:

- Người dùng là thành viên của workspace.
- Người dùng được chia sẻ một tài liệu.
- Người dùng thuộc nhóm có quyền trên thư mục.
- Người dùng là người quản lý của chủ sở hữu tài nguyên.

Ví dụ:

~~~text
ALLOW document.read nếu:
    principal là owner
    OR principal có direct_share còn hiệu lực
    OR principal thuộc group được chia sẻ document
~~~

Quan hệ có thể được lưu ở ACL, bảng membership, graph quan hệ hoặc dịch vụ chính sách. Khi quan hệ bị thu hồi, API cần đọc trạng thái đủ mới để không tiếp tục dùng quyền đã cũ.

### 5.6. Kết hợp nhiều mô hình

Một hệ thống thực tế thường kết hợp:

- RBAC để quản lý nhóm trách nhiệm.
- ABAC để xét thuộc tính và điều kiện nghiệp vụ.
- ReBAC để xét chia sẻ, sở hữu và quan hệ tổ chức.
- Scope để giới hạn khả năng được cấp cho token.

Không nên chọn mô hình theo tên gọi. Hãy mô tả quy tắc quyền cần thực hiện, nguồn dữ liệu, yêu cầu thu hồi và cách kiểm thử trước.

## 6. Bảo vệ ranh giới tenant

Lỗi truy cập chéo tenant thường có tác động lớn vì một người dùng hợp lệ có thể nhìn thấy dữ liệu của tổ chức khác.

Giả sử:

~~~text
Principal: user-514
Token tenant: company-a
Invoice INV-100: tenant company-a
Invoice INV-200: tenant company-b
~~~

Người dùng có scope invoice:read và membership hợp lệ ở company-a. Họ được xem INV-100 nếu các điều kiện khác đạt, nhưng không được xem INV-200.

### 6.1. Giới hạn truy vấn ngay từ tầng dữ liệu

Một mẫu truy vấn nguy hiểm:

~~~sql
SELECT *
FROM invoices
WHERE invoice_id = :invoice_id;
~~~

Truy vấn này chỉ tìm theo ID, không giới hạn tenant. Nếu tầng sau quên kiểm tra tenant, dữ liệu có thể bị trả nhầm.

Một cách an toàn hơn là ràng buộc tenant trong truy vấn:

~~~sql
SELECT *
FROM invoices
WHERE invoice_id = :invoice_id
  AND tenant_id = :authorized_tenant_id;
~~~

authorized_tenant_id phải được xác định từ ngữ cảnh đã xác minh và membership phù hợp. Việc giới hạn truy vấn giúp giảm khả năng một object ngoài tenant lọt vào luồng xử lý.

Tuy vậy, truy vấn có tenant không thay thế mọi kiểm tra. API vẫn cần xác minh action, membership, owner/relationship và điều kiện nghiệp vụ. Cũng cần bảo đảm tenant_id của bản ghi được quản lý đúng và không thể bị thay đổi tùy tiện qua request cập nhật.

### 6.2. Không để client chọn tenant rồi tự tin vào lựa chọn đó

Một request như:

~~~http
GET /tenants/company-b/invoices/INV-200 HTTP/1.1
Authorization: Bearer <token-for-company-a>
~~~

không thể được chấp nhận chỉ vì URL chỉ định company-b. API cần kiểm tra tenant được phép của principal và tenant thật của hóa đơn. Nếu người dùng có nhiều tenant, cơ chế chuyển ngữ cảnh phải xác định tenant được chọn từ một membership hợp lệ.

### 6.3. Tenant trong URL, header hoặc body

Tenant có thể được truyền qua path, header, query hoặc body vì lý do thiết kế API. Vị trí truyền không làm nó trở thành dữ liệu đáng tin cậy. Giá trị đó chỉ là **đầu vào để tra cứu ngữ cảnh**; server phải xác minh chủ thể có quyền dùng tenant đó và tài nguyên thật sự thuộc tenant.

## 7. Kiểm tra quyền cho từng loại thao tác

Quyền không chỉ áp dụng cho GET. Mỗi thao tác có rủi ro và điều kiện riêng.

| Thao tác | Điều cần kiểm tra |
| --- | --- |
| **Read / GET** | Chủ thể có được xem object này và các trường dữ liệu này không? |
| **List / Search** | Tập kết quả, bộ lọc, tổng số, facet và phân trang có chỉ chứa object được phép không? |
| **Create / POST** | Chủ thể có được tạo loại tài nguyên này trong tenant/ngữ cảnh đã chọn không? Owner và tenant phải do server xác định theo chính sách. |
| **Update / PATCH / PUT** | Chủ thể có quyền sửa object này và từng trường được gửi lên không? Trạng thái hiện tại có cho phép sửa không? |
| **Delete** | Có quyền xóa đúng object không? Có điều kiện lưu trữ, retention hoặc phê duyệt bổ sung không? |
| **Approve / Execute** | Có quyền thực hiện chuyển trạng thái này không? Có giới hạn người tạo/người duyệt, số tiền hoặc trạng thái không? |
| **Download / Export** | Có quyền đọc nội dung tệp hoặc tập dữ liệu này không? Đường dẫn tệp có vượt qua kiểm tra quyền không? |
| **Share / Grant** | Có quyền cấp quyền cho người khác không? Có thể cấp quyền rộng hơn quyền của chính mình không? |
| **Bulk action** | Mọi object trong tập yêu cầu có được phép thao tác không? Xử lý nguyên tử hay từng phần theo hợp đồng nào? |

### 7.1. Tạo tài nguyên: owner và tenant phải được kiểm soát

Ví dụ client gửi:

~~~json
{
  "tenant_id": "company-a",
  "owner_id": "user-999",
  "title": "Báo cáo quý"
}
~~~

API không được mặc nhiên chấp nhận owner_id hoặc tenant_id do client chỉ định. Theo chính sách, server có thể gán owner là principal hiện tại, xác định tenant từ ngữ cảnh đã được xác minh và kiểm tra người tạo có quyền tạo trong tenant đó hay không.

Nếu nghiệp vụ cho phép tạo thay mặt người khác, phải có permission riêng và kiểm tra quan hệ ủy quyền rõ ràng.

### 7.2. Cập nhật: chống mass assignment

Một API cập nhật tài liệu có thể nhận:

~~~json
{
  "title": "Kế hoạch mới",
  "owner_id": "attacker",
  "tenant_id": "company-b",
  "classification": "PUBLIC",
  "approved": true
}
~~~

Nếu API tự động gán mọi trường trong body vào object, client có thể đổi owner, chuyển tenant, hạ phân loại hoặc tự đánh dấu đã duyệt.

Hãy định nghĩa rõ:

- Những trường client được phép cập nhật.
- Những trường chỉ hệ thống hoặc quy trình nghiệp vụ được phép thay đổi.
- Permission riêng cho thao tác nhạy cảm.
- Quy tắc chuyển trạng thái hợp lệ.
- Kiểm tra lại quyền và trạng thái ngay tại lúc ghi.

**Có quyền sửa tài nguyên không đồng nghĩa có quyền sửa mọi thuộc tính của tài nguyên.**

### 7.3. Xóa và chuyển trạng thái

Một người có thể được phép sửa mô tả hóa đơn nhưng không được xóa hoặc duyệt hóa đơn. Hãy ánh xạ từng hành động thành permission riêng và kiểm tra state transition:

~~~text
DRAFT -> SUBMITTED -> APPROVED -> PAID
   \          \
    \          -> REJECTED
     -> CANCELLED
~~~

Không chấp nhận một request chỉ vì principal có permission invoice.update nếu thao tác thực tế là invoice.approve hoặc trạng thái hiện tại không cho phép chuyển.

## 8. Collection, tìm kiếm và phân trang

Kiểm tra quyền ở một object đơn lẻ chưa đủ nếu endpoint trả danh sách.

Ví dụ:

~~~http
GET /invoices?status=PENDING&page=1
~~~

API có thể xác minh JWT và scope invoice:read, nhưng nếu truy vấn lấy tất cả hóa đơn rồi trả danh sách, người dùng có thể nhìn thấy object ngoài tenant hoặc ngoài quan hệ được phép.

### 8.1. Lọc theo quyền trước khi phân trang

Quy trình đúng về mặt logic:

~~~text
1. Xác định tập resource mà principal có quyền đọc.
2. Áp dụng bộ lọc nghiệp vụ do client yêu cầu trên tập được phép.
3. Tính thứ tự và phân trang trên tập kết quả được phép.
4. Trả dữ liệu, total và metadata chỉ từ tập được phép.
~~~

Nếu phân trang trên toàn bộ dữ liệu trước rồi mới loại object không được phép, hệ thống có thể:

- Trả trang thiếu dữ liệu dù vẫn còn object được phép ở trang sau.
- Tạo kết quả phân trang không ổn định.
- Làm lộ số lượng hoặc sự tồn tại của object không được phép qua total, facet, cursor hoặc khoảng trống ID.

### 8.2. Không chỉ lọc phần tử, phải lọc metadata

Các dữ liệu sau cũng có thể tiết lộ thông tin:

- Tổng số bản ghi (total_count).
- Số lượng theo trạng thái hoặc nhóm (facets).
- Gợi ý autocomplete.
- Thống kê, dashboard và biểu đồ.
- Cursor hoặc ID kế tiếp.
- Tên file và metadata trong kết quả tìm kiếm.

Mọi phần metadata phản ánh tài nguyên đều phải được tính từ tập dữ liệu mà principal được phép biết.

### 8.3. Pseudocode cho danh sách

~~~text
function listInvoices(request):
    principal = validateAndResolvePrincipal(request.token)
    requireScope(principal, "invoice:read")

    membership = loadCurrentMembership(
        principal,
        request.selectedTenant
    )
    if membership is not active:
        deny

    allowedQuery = buildAuthorizedInvoiceQuery(
        principal,
        membership,
        request.filters
    )

    total = count(allowedQuery)
    page = paginate(allowedQuery, request.cursor, request.limit)

    return {
        items: page.items,
        total: total,
        nextCursor: page.nextCursor
    }
~~~

buildAuthorizedInvoiceQuery phải đưa điều kiện quyền vào truy vấn hoặc sử dụng một cơ chế tương đương bảo đảm không trả object ngoài phạm vi. Không nên tải tất cả bản ghi rồi lọc ở giao diện.

## 9. Tài nguyên lồng nhau và nhiều ID trong cùng request

API thường có cấu trúc lồng:

~~~text
/accounts/{accountId}/transactions/{transactionId}
/workspaces/{workspaceId}/documents/{documentId}
/projects/{projectId}/members/{memberId}
~~~

Không được giả định transactionId thuộc accountId chỉ vì cả hai ID xuất hiện trong URL. Một client có thể ghép ID hợp lệ nhưng thuộc hai đối tượng khác nhau.

### 9.1. Xác minh quan hệ cha-con

Ví dụ request:

~~~http
GET /accounts/ACC-A/transactions/TXN-B
~~~

API phải xác minh:

1. Principal có quyền truy cập account ACC-A.
2. Transaction TXN-B thật sự thuộc ACC-A.
3. Principal có quyền đọc transaction theo chính sách hiện hành.

Một truy vấn có thể ràng buộc quan hệ:

~~~sql
SELECT t.*
FROM transactions t
JOIN accounts a ON a.account_id = t.account_id
WHERE a.account_id = :account_id
  AND t.transaction_id = :transaction_id
  AND a.tenant_id = :authorized_tenant_id;
~~~

Sau đó vẫn cần đánh giá quan hệ principal-account và permission cho hành động cụ thể.

### 9.2. Bulk operations

Một request có thể gửi:

~~~json
{
  "invoice_ids": ["INV-100", "INV-101", "INV-999"]
}
~~~

Nếu người dùng có quyền với hai hóa đơn đầu nhưng không có quyền với hóa đơn thứ ba, API cần có hợp đồng rõ:

- **All-or-nothing:** từ chối toàn bộ nếu có bất kỳ object nào không được phép; phù hợp khi thao tác phải nhất quán như chuyển một nhóm giao dịch.
- **Per-item result:** xử lý từng object và trả kết quả riêng; chỉ phù hợp nếu API không tiết lộ thông tin ngoài quyền và nghiệp vụ chấp nhận kết quả từng phần.

Không âm thầm bỏ qua object ngoài quyền rồi báo thành công toàn bộ nếu điều đó khiến client hiểu sai trạng thái. Cũng không trả quá nhiều chi tiết về object mà người gọi không được biết.

## 10. Quyền trên trường dữ liệu và nội dung trả về

Được phép đọc một object không nhất thiết có nghĩa được đọc mọi trường. Ví dụ hồ sơ nhân sự có thể chứa:

~~~json
{
  "name": "An",
  "department": "Finance",
  "salary": 5000,
  "national_id": "...",
  "medical_notes": "..."
}
~~~

Một quản lý có thể xem tên và phòng ban của nhân viên trong nhóm nhưng không được xem thông tin định danh hoặc ghi chú nhạy cảm. API cần kiểm soát **field-level authorization** hoặc phân loại dữ liệu theo chính sách.

Các nguyên tắc:

- Chỉ trả trường cần thiết cho mục đích của endpoint.
- Không serialize toàn bộ object nội bộ rồi hy vọng client tự ẩn trường.
- Quyền đọc từng trường phải được đánh giá ở server.
- Tập field được phép có thể phụ thuộc role, quan hệ, mục đích hoặc mức phân loại.
- Kiểm soát tương tự phải áp dụng cho export, log, search index và bản sao dữ liệu.

Field-level authorization bổ sung cho object-level authorization. Nó không thay thế câu hỏi chủ thể có được truy cập object hay không.

## 11. Download, file storage và đường truy cập gián tiếp

Một API có thể kiểm tra quyền khi trả metadata tài liệu nhưng lại tạo URL tải tệp công khai hoặc URL ký số tồn tại quá lâu.

Ví dụ:

~~~text
GET /documents/DOC-100
    -> kiểm tra quyền thành công
    -> trả URL tải file dùng được trong 24 giờ
~~~

Nếu quyền chia sẻ bị thu hồi sau 1 phút, URL có thể vẫn cho tải trong gần 24 giờ tùy cơ chế lưu trữ. Đây là một đường truy cập gián tiếp có vòng đời riêng.

Khi thiết kế tải tệp:

- Kiểm tra quyền trên document trước khi tạo URL.
- URL ký số phải có thời hạn ngắn và giới hạn đúng object, method, bucket/path hoặc thao tác.
- Không dùng URL ký số như một cơ chế phân quyền dài hạn.
- Nếu yêu cầu thu hồi nhanh, cân nhắc proxy download qua API hoặc cơ chế kiểm tra trạng thái bổ sung.
- Không để CDN hoặc cache công khai phục vụ dữ liệu riêng tư sau khi quyền thay đổi.
- Xem xét quyền trên thumbnail, preview, export, bản sao và tệp đính kèm.

Một người được quyền xem metadata không mặc nhiên được quyền tải nội dung đầy đủ.

## 12. GraphQL, batch API, background job và các đường gọi khác

Quyền tài nguyên có thể bị bỏ sót ở những đường truy cập không giống REST endpoint thông thường.

### 12.1. GraphQL

Một GraphQL request có thể truy vấn nhiều object trong một lần:

~~~graphql
query {
  invoice(id: "INV-100") {
    id
    amount
    tenantId
  }
}
~~~

Kiểm tra quyền ở endpoint /graphql chỉ chứng minh request được vào GraphQL service. Resolver hoặc lớp truy cập dữ liệu phải kiểm tra quyền tương ứng với từng object và field được trả về. Không dựa vào việc người dùng chỉ gửi một query duy nhất.

### 12.2. Batch và nested resolver

Batch loader có thể gom nhiều ID để giảm số lần truy vấn. Việc tối ưu này không được làm mất ngữ cảnh principal hoặc tenant. Cache của batch loader phải được phân vùng theo principal/context thích hợp; không tái sử dụng object đã tải cho người dùng khác mà không đánh giá quyền lại.

### 12.3. Background job

Một người dùng có thể yêu cầu export, rồi hệ thống chạy job sau đó. Cần xác định:

- Quyền được kiểm tra lúc tạo job, lúc chạy job hay cả hai?
- Nếu quyền bị thu hồi trước khi job chạy, job có bị hủy/từ chối không?
- Job thực hiện thay mặt người dùng hay bằng service principal?
- File kết quả có kiểm tra quyền khi tải xuống không?
- Người khác có thể đoán job ID và tải kết quả không?

Đối với tác vụ nhạy cảm hoặc chạy trễ, thường cần lưu principal, tenant, action và phạm vi được ủy quyền trong job context; xác minh lại trạng thái quyền theo chính sách khi thực thi và khi truy cập kết quả.

## 13. Kiểm tra quyền và thao tác ghi phải nhất quán

Một lỗi có thể xảy ra khi API kiểm tra quyền rồi dữ liệu thay đổi trước lúc ghi. Đây là vấn đề **time-of-check to time-of-use (TOCTOU)**.

Ví dụ:

1. 10:00:00.000, API xác minh người dùng còn quyền sửa hóa đơn.
2. 10:00:00.050, quản trị viên gỡ quyền hoặc hóa đơn bị khóa.
3. 10:00:00.100, API vẫn ghi thay đổi theo kết quả kiểm tra cũ.

Với thao tác nhạy cảm, cân nhắc:

- Đặt kiểm tra quyền và thay đổi dữ liệu trong một giao dịch hoặc ranh giới đồng bộ phù hợp.
- Kiểm tra version của resource và trạng thái khi cập nhật.
- Dùng điều kiện ghi để chỉ cập nhật khi resource còn ở trạng thái cho phép.
- Kiểm tra lại quyền nếu thao tác kéo dài hoặc cần nhiều bước.
- Ghi audit theo kết quả đã thực thi, không chỉ theo kết quả kiểm tra ban đầu.

Ví dụ cập nhật có điều kiện:

~~~sql
UPDATE invoices
SET status = 'APPROVED',
    approved_by = :principal_id,
    version = version + 1
WHERE invoice_id = :invoice_id
  AND tenant_id = :authorized_tenant_id
  AND status = 'PENDING'
  AND version = :expected_version;
~~~

Truy vấn này minh họa kiểm tra tenant, trạng thái và version ở thời điểm ghi. Hệ thống vẫn phải bảo đảm principal có quyền phê duyệt; điều kiện dữ liệu không thay thế toàn bộ chính sách.

## 14. HTTP response và nguy cơ rò rỉ thông tin

API cần thống nhất cách phản hồi khi object không tồn tại hoặc người gọi không có quyền.

| Trường hợp | Phản hồi thường gặp |
| --- | --- |
| Không có token hoặc token không hợp lệ | 401 Unauthorized |
| Token hợp lệ nhưng không có quyền cho action | 403 Forbidden |
| Object không tồn tại | 404 Not Found |
| Object tồn tại nhưng không được phép biết sự tồn tại | Có thể trả 404 Not Found để che giấu |
| Request sai định dạng hoặc thiếu trường bắt buộc | 400 Bad Request hoặc lỗi validation theo hợp đồng |

Không có quy tắc rằng mọi BOLA phải trả một mã HTTP cố định. Một API có thể trả 404 cho cả object không tồn tại và object ngoài phạm vi để giảm khả năng dò tìm. Nhưng cách làm này phải nhất quán và không tạo side channel khác qua thời gian phản hồi, kích thước response, log hoặc metadata.

Không nên trả thông báo như “Hóa đơn INV-200 tồn tại nhưng thuộc công ty khác” cho principal không được phép biết. Lý do nội bộ có thể được ghi trong audit nhưng response công khai cần tối thiểu hóa thông tin.

## 15. Pseudocode tổng hợp: đọc một hóa đơn an toàn

Ví dụ sau thể hiện một đường kiểm tra độc lập ngôn ngữ. Hàm validateAccessToken phải xác minh đầy đủ JWT trước khi claims được tin cậy.

~~~text
function getInvoice(request):
    token = extractBearerToken(request.headers)

    verified = validateAccessToken(
        token,
        trustedIssuer = "https://identity.example.test",
        expectedAudience = "https://api.example.test/billing",
        allowedAlgorithms = ["RS256"]
    )
    if verified.failed:
        return HTTP 401

    principal = resolvePrincipal(verified.claims.iss, verified.claims.sub)
    if principal is null:
        return HTTP 403

    if not exactScopeContains(verified.claims.scope, "invoice:read"):
        return HTTP 403

    tenant = resolveAuthorizedTenant(
        principal,
        request.selectedTenant,
        verified.claims.tenant_id
    )
    if tenant is null:
        return HTTP 404

    invoice = loadInvoiceBoundToTenant(
        tenant.id,
        request.path.invoiceId
    )
    if invoice is null:
        return HTTP 404

    membership = loadCurrentMembership(principal, tenant.id)
    if membership is null or not membership.active:
        return HTTP 404

    decision = policy.evaluate(
        principal = principal,
        action = "invoice.read",
        resource = invoice,
        context = {
            membership: membership,
            tenant: tenant
        }
    )

    if decision != ALLOW:
        auditDenied(principal, "invoice.read", invoice.id, decision.reason)
        return HTTP 404

    auditAllowed(principal, "invoice.read", invoice.id)
    return HTTP 200 with permittedInvoiceFields(invoice, principal)
~~~

Các điểm cần lưu ý:

- request.path.invoiceId chỉ là định danh do client cung cấp; không chứa thông tin cấp quyền.
- loadInvoiceBoundToTenant giới hạn object theo tenant đã được xác minh.
- Membership được kiểm tra theo nguồn hiện hành nếu chính sách yêu cầu.
- policy.evaluate nhận resource thực tế và action đã xác định ở server.
- permittedInvoiceFields áp dụng quyền trường dữ liệu nếu cần.
- 404 được chọn trong ví dụ để che giấu object; API khác có thể dùng 403 theo chính sách đã công bố.

## 16. Những sai lầm thường gặp

| Sai lầm | Rủi ro | Cách phòng tránh |
| --- | --- | --- |
| Chỉ kiểm tra JWT hợp lệ | Người dùng đăng nhập có thể truy cập object ngoài phạm vi. | Kiểm tra quyền theo action và resource. |
| Chỉ kiểm tra scope ở endpoint | Scope đọc có thể bị hiểu thành đọc mọi object. | Kết hợp scope với ownership, tenant, relation và state. |
| Tin ID trong URL/body | Có thể đổi ID để đọc/sửa/xóa object khác. | Tải object từ nguồn tin cậy và đánh giá chính sách. |
| Dùng ID khó đoán thay authorization | ID vẫn có thể bị lộ qua log, link hoặc dữ liệu liên quan. | Luôn kiểm tra quyền dù ID là UUID hoặc ngẫu nhiên. |
| Lấy owner_id hoặc tenant_id từ client | Client có thể tự nhận quyền hoặc chuyển object sang tenant khác. | Xác định thuộc tính nhạy cảm từ server và chính sách. |
| Kiểm tra tenant ở một endpoint nhưng bỏ endpoint khác | Một đường truy cập phụ có thể vượt ranh giới tenant. | Áp dụng kiểm tra ở mọi đường đọc/ghi/export/download. |
| Lọc danh sách sau khi phân trang | Metadata, total hoặc trang kết quả có thể làm lộ dữ liệu. | Lọc theo quyền trước khi tính count và pagination. |
| Chỉ bảo vệ object, bỏ field | Trường nhạy cảm bị trả cho người không đủ quyền. | Áp dụng field-level authorization và response projection. |
| Kiểm tra object cha nhưng không kiểm tra object con | Có thể ghép hai ID không liên quan. | Xác minh quan hệ giữa tất cả object trong request. |
| Bulk xử lý mà không kiểm tra từng object | Một ID ngoài quyền làm rò rỉ hoặc thay đổi dữ liệu. | All-or-nothing hoặc per-item theo hợp đồng rõ ràng. |
| Kiểm tra quyền trước nhưng ghi sau khi trạng thái đổi | TOCTOU cho phép thao tác sau khi quyền đã bị thu hồi. | Đồng bộ kiểm tra và ghi cho thao tác nhạy cảm. |
| Chỉ kiểm tra lúc tạo job, không kiểm tra khi tải kết quả | Người mất quyền vẫn lấy được file export cũ. | Bảo vệ job context và kết quả theo vòng đời riêng. |
| Cache object mà không gắn ngữ cảnh quyền | Dữ liệu được tải bởi người này có thể bị trả cho người khác. | Phân vùng cache và đánh giá quyền ở mỗi request phù hợp. |
| Trả lỗi quá chi tiết | Làm lộ sự tồn tại, tenant hoặc thuộc tính object. | Chuẩn hóa response và chỉ ghi lý do chi tiết trong audit. |

## 17. Kiểm thử object-level authorization

Kiểm thử quyền phải có cả trường hợp được phép và bị từ chối. Chỉ kiểm tra một người dùng hợp lệ đọc được object của họ là chưa đủ.

### 17.1. Kiểm thử thay ID

Tạo hai principal và hai object:

~~~text
User A owns INV-A
User B owns INV-B
~~~

Kiểm thử:

~~~text
User A + INV-A -> ALLOW nếu các điều kiện khác đạt
User A + INV-B -> DENY
User B + INV-B -> ALLOW nếu các điều kiện khác đạt
User B + INV-A -> DENY
~~~

Thực hiện với ID tuần tự, UUID, ID lấy từ response khác, ID trong path, query và body.

### 17.2. Kiểm thử chéo tenant

~~~text
User A member of company-a
INV-A belongs to company-a
INV-B belongs to company-b

User A reads INV-A -> có thể ALLOW
User A reads INV-B -> DENY
User A changes URL tenant to company-b -> DENY
User A submits tenant_id=company-b in body -> DENY
~~~

### 17.3. Kiểm thử từng action

Một principal có thể được đọc nhưng không được sửa hoặc xóa:

| Principal và tài nguyên | Read | Update | Delete | Approve |
| --- | :---: | :---: | :---: | :---: |
| Owner có quyền đọc/sửa, không có quyền xóa/duyệt | ALLOW | ALLOW | DENY | DENY |
| Auditor chỉ đọc trong tenant | ALLOW | DENY | DENY | DENY |
| Approver có quyền duyệt, object đang chờ duyệt | Theo policy | DENY nếu không có quyền sửa | DENY | ALLOW nếu không vi phạm điều kiện khác |
| Thành viên đã bị gỡ khỏi tenant | DENY | DENY | DENY | DENY |

### 17.4. Kiểm thử collection và metadata

- Danh sách chỉ chứa object principal được phép xem.
- total_count, facet và thống kê không tính object ngoài quyền.
- Cursor không làm lộ ID hoặc thứ tự object không được phép.
- Search, autocomplete và export áp dụng cùng phạm vi quyền.
- Phân trang không bị thiếu object được phép do lọc sau pagination.

### 17.5. Kiểm thử nested, bulk và file

- Parent ID hợp lệ kết hợp child ID thuộc parent khác phải bị từ chối.
- Bulk request có một object ngoài quyền phải xử lý đúng all-or-nothing/per-item contract.
- Download URL không thể tải object ngoài quyền.
- URL ký số hết hạn đúng thời gian và phạm vi.
- Job export bị thu hồi quyền trước khi chạy hoặc trước khi tải kết quả phải xử lý theo chính sách.

### 17.6. Kiểm thử thay đổi trạng thái và đồng thời

- Owner bị thay đổi giữa lúc đọc và lúc cập nhật.
- Membership bị thu hồi trong khi request đang xử lý.
- Resource chuyển từ PENDING sang APPROVED trước khi một request duyệt khác ghi.
- Permission bị thu hồi giữa kiểm tra và thao tác.
- Cache hoặc dịch vụ quyền không khả dụng.

Kiểm thử tích hợp phải gọi API thực tế và xác nhận không có side effect khi request bị từ chối. Kiểm tra riêng hàm policy không chứng minh tất cả đường truy cập đã dùng hàm đó.

## 18. Checklist thiết kế cho mỗi API

Trước khi công bố một endpoint hoặc thao tác tài nguyên, hãy trả lời:

1. JWT nào được chấp nhận: issuer, audience, loại token, thuật toán và thời hạn?
2. Principal là người dùng hay service; định danh được ánh xạ từ (iss, sub) như thế nào?
3. Action nghiệp vụ nào được thực hiện; scope hoặc permission nào là điều kiện cần?
4. Resource thực tế được tải từ nguồn nào; ID do client gửi có được coi chỉ là đầu vào không?
5. Ai là owner; object thuộc tenant nào; quan hệ chia sẻ hoặc membership nào có hiệu lực?
6. Có điều kiện theo trạng thái, thời gian, số tiền, phân loại hoặc tách nhiệm vụ không?
7. Có kiểm tra quyền riêng cho read, list, create, update, delete, approve, export, download và share không?
8. Các trường nhạy cảm có cần field-level authorization không?
9. Collection được lọc trước pagination và metadata có nằm trong phạm vi quyền không?
10. Nested ID và bulk ID được kiểm tra quan hệ và quyền ra sao?
11. Cache, URL ký số, job nền và các đường truy cập gián tiếp có cùng chính sách không?
12. Quyền được kiểm tra nhất quán với thao tác ghi và trạng thái tài nguyên không?
13. Response có làm lộ sự tồn tại hoặc thuộc tính object không được phép không?
14. Có kiểm thử chéo user, chéo tenant, thay ID, đổi action, bulk, nested và TOCTOU không?
15. Audit có đủ để điều tra nhưng không lưu token hoặc dữ liệu nhạy cảm không?

## 19. Ghi nhớ trọng tâm

- JWT hợp lệ xác nhận bằng chứng và chủ thể trong phạm vi tin cậy; nó không tự chứng minh quyền trên mọi tài nguyên.
- Kiểm tra ở endpoint hoặc scope chỉ là một lớp. API còn phải kiểm tra **principal + action + resource + context**.
- ID do client gửi không phải bằng chứng sở hữu; phải tải resource từ nguồn tin cậy và kiểm tra quan hệ quyền.
- Bảo vệ tenant, owner, relationship, trạng thái và trường dữ liệu ở mọi đường đọc/ghi, kể cả list, bulk, nested, download và background job.
- Lọc theo quyền trước khi phân trang và tính metadata; tránh làm lộ object ngoài phạm vi.
- Kiểm tra quyền và thao tác ghi cần đủ nhất quán để ngăn TOCTOU.
- Mặc định từ chối khi thiếu bằng chứng cho phép; response công khai không nên tiết lộ thông tin về object mà caller không được biết.

**Tài liệu tham khảo kỹ thuật:** OWASP API Security Top 10 (2023), đặc biệt API1: Broken Object Level Authorization; OWASP Authorization Cheat Sheet; CWE-639 (Authorization Bypass Through User-Controlled Key); CWE-862 (Missing Authorization); NIST SP 800-162 (Guide to Attribute Based Access Control). Các tài liệu này bổ sung hướng dẫn về kiểm soát truy cập và lỗi truy cập đối tượng; hợp đồng quyền cụ thể vẫn phải được định nghĩa theo mô hình dữ liệu và nghiệp vụ của từng API.
