# Không suy luận quyền từ việc object tồn tại

Một request gọi `GET /api/invoices/inv-2048` có thể tìm thấy hóa đơn `inv-2048` trong cơ sở dữ liệu. Điều đó chỉ chứng minh bản ghi tồn tại. Nó chưa chứng minh người gửi request được phép đọc hóa đơn, càng chưa chứng minh họ được sửa, hủy hoặc tải tệp đính kèm của hóa đơn đó.

Đây là nguyên tắc cốt lõi của **object-level authorization**: hệ thống phải đánh giá quyền của principal đối với đúng object và đúng hành động. Không được suy luận quyền từ việc object có mặt trong database, từ việc ID hợp lệ hoặc khó đoán, từ việc người dùng đã đăng nhập, hay từ việc giao diện đang hiển thị một liên kết.

Ví dụ, Alice và Bob đều là người dùng hợp lệ. Hóa đơn của Bob tồn tại và Alice có thể đoán hoặc biết ID của hóa đơn đó. API xác thực Alice thành công, truy vấn được hóa đơn, rồi trả dữ liệu mà không kiểm tra quan hệ giữa Alice và hóa đơn. Đây là lỗi Broken Object Level Authorization (BOLA), thường được gọi là IDOR trong nhiều ngữ cảnh. Kẻ tấn công không cần vượt qua đăng nhập; họ lợi dụng việc API không kiểm tra quyền trên object cụ thể.

## 1. Existence và authorization là hai câu hỏi độc lập

Khi xử lý một object, máy chủ cần trả lời ít nhất hai câu hỏi riêng:

1. **Object có tồn tại và thuộc phạm vi dữ liệu mà endpoint có thể tra cứu không?** Đây là câu hỏi về dữ liệu và định danh.
2. **Principal hiện tại có được phép thực hiện action trên object đó trong ngữ cảnh này không?** Đây là câu hỏi về chính sách truy cập.

Một object có thể tồn tại nhưng principal không có quyền. Một object cũng có thể không tồn tại. Hai trường hợp có thể được biểu diễn bằng cùng một HTTP response để tránh tiết lộ thông tin, nhưng quyết định bảo mật phía máy chủ vẫn phải phân biệt được chúng khi cần.

| Trạng thái dữ liệu | Quyền của principal | Kết luận bảo mật |
|---|---|---|
| Object tồn tại | Được phép với action hiện tại | Có thể thực hiện action sau khi kiểm tra các điều kiện còn lại |
| Object tồn tại | Không được phép | Từ chối action; không trả dữ liệu hoặc tạo thay đổi |
| Object không tồn tại | Không có object để cấp quyền | Không thực hiện action |
| Object tồn tại nhưng bị xóa mềm, khóa hoặc ngoài trạng thái cho phép | Có thể có quyền đọc nhưng không có quyền sửa/xóa | Áp dụng policy theo trạng thái và action; không coi quyền đọc là quyền ghi |

Điểm quan trọng là kết quả truy vấn database không phải là một quyết định authorization. `findById()` thành công chỉ trả về dữ liệu để ứng dụng đánh giá tiếp; nó không tự cấp quyền cho caller.

### 1.1. Định danh object không phải là bằng chứng quyền

Các giá trị như `invoiceId`, `userId`, `projectId`, `documentId` hay `tenantId` thường xuất hiện trong path, query hoặc body. Chúng giúp API xác định object mà client muốn thao tác. Chúng không chứng minh caller sở hữu object đó.

Một số giả định sai thường gặp:

- ID là số khó đoán nên người dùng không thể truy cập object của người khác.
- ID là UUID nên không cần kiểm tra owner hoặc tenant.
- Caller biết URL hoặc nhận được link nên chắc chắn được phép mở object.
- Object được trả về trong một danh sách trước đó nên caller luôn được phép sửa nó.
- Client gửi `ownerId` hoặc `tenantId` khớp với object nên request hợp lệ.
- User có role `CUSTOMER` hoặc `EMPLOYEE` nên được phép truy cập mọi object cùng loại.

ID khó đoán có thể giảm khả năng dò tìm nhưng không phải access control. Link có thể bị chia sẻ, lưu trong lịch sử, xuất hiện trong log hoặc bị lộ. Quyền có thể thay đổi sau khi danh sách được tải. Role thường mô tả loại công việc, trong khi quyền trên object còn phụ thuộc quan hệ sở hữu, tenant, trạng thái và ngữ cảnh.

### 1.2. Authentication không tự tạo ra quyền trên mọi object

Authentication xác định principal là ai. Ví dụ token hợp lệ cho biết request đại diện cho `user-42`. Authorization tiếp tục xác định `user-42` có được `invoice:read` trên `inv-2048` hay không.

```text
Credential hợp lệ
        |
        v
Principal = user-42
        |
        v
Action = invoice:read
Object = inv-2048
Context = tenant, ownership, relationship, trạng thái, thời điểm
        |
        v
Chính sách authorization
        |
        +---- ALLOW: tiếp tục xử lý
        |
        +---- DENY: từ chối request
```

Không nên viết logic kiểu `if (authenticated) return invoice;`. Việc đã đăng nhập chỉ cho phép hệ thống nhận diện caller; quyền đọc object vẫn phải được đánh giá riêng.

## 2. Đánh giá quyền trên bộ principal, action, object và context

Một quyết định object authorization thường phụ thuộc vào bốn thành phần:

- **Principal:** user, service account hoặc client đã được xác thực.
- **Action:** thao tác cụ thể như `read`, `update`, `delete`, `approve`, `download` hoặc `share`.
- **Object:** bản ghi hoặc tài nguyên cụ thể mà request nhắm tới.
- **Context:** tenant, quan hệ với object, trạng thái nghiệp vụ, thời gian, mức xác thực, nguồn gọi hoặc các thuộc tính chính sách khác.

Có thể biểu diễn quyết định dưới dạng:

```text
decision = authorize(principal, action, object, context)
```

Ví dụ, một nhân viên có thể xem hóa đơn của khách hàng thuộc cửa hàng mình phụ trách nhưng chỉ được tải bản PDF khi hóa đơn đã phát hành. Một kế toán có thể cập nhật mã tham chiếu nhưng không được thay đổi tổng tiền. Một quản trị viên tenant có thể xem object trong tenant của mình nhưng không được truy cập tenant khác.

Vì vậy, kiểm tra quyền không nên chỉ dựa vào role chung:

```pseudo
// Thiếu: role không chứng minh quan hệ với object
if principal.role == "CUSTOMER":
    return invoice
```

Nên kiểm tra policy cho đúng hành động và object:

```pseudo
if authorization.can(principal, "invoice:read", invoice, context):
    return serializeInvoice(invoice, fieldsAllowedFor(principal, invoice))

return deny
```

### 2.1. Role, attribute và relationship

Các mô hình phổ biến có thể được kết hợp:

| Mô hình | Dựa trên điều gì? | Ví dụ |
|---|---|---|
| RBAC (Role-Based Access Control) | Vai trò được gán cho principal | `ACCOUNTANT` có thể xem hóa đơn |
| ABAC (Attribute-Based Access Control) | Thuộc tính của principal, object và context | Nhân viên chỉ xem hóa đơn thuộc `storeId` họ phụ trách |
| ReBAC (Relationship-Based Access Control) | Quan hệ giữa principal và object | Thành viên dự án có quyền đọc tài liệu của dự án |
| ACL (Access Control List) | Danh sách principal hoặc nhóm được cấp quyền trên object | Alice có `read`, Bob có `read` và `update` trên file cụ thể |

RBAC có thể trả lời ai có loại quyền nào, nhưng thường cần ABAC/ReBAC/ACL để xác định quyền đó áp dụng cho object nào. Không cần chọn một mô hình duy nhất cho toàn hệ thống; điều quan trọng là policy rõ ràng, có thể kiểm thử và được thực thi nhất quán.

### 2.2. Quyền thay đổi theo action

Được phép đọc không đồng nghĩa được phép sửa. Được phép sửa một số trường không đồng nghĩa được phép sửa mọi trường. Được phép xem metadata không đồng nghĩa được phép tải nội dung file.

Ví dụ với tài liệu dự án:

| Action | Điều kiện ví dụ |
|---|---|
| `document:read` | Thành viên dự án có quyền xem tài liệu |
| `document:update` | Chủ sở hữu hoặc editor của dự án; tài liệu chưa khóa |
| `document:delete` | Owner hoặc project admin; thỏa điều kiện lưu trữ |
| `document:share` | Có quyền chia sẻ và người nhận nằm trong phạm vi cho phép |
| `document:download` | Có quyền đọc nội dung và file chưa bị hạn chế tải |

Nếu chỉ kiểm tra `canAccess(document)` mà không truyền action, hàm đó dễ trở thành một quyền tổng quát quá rộng. Hãy đặt tên policy theo hành động hoặc dùng permission cụ thể để người đọc hiểu chính xác điều gì đang được cho phép.

## 3. Ví dụ BOLA: object tồn tại nhưng caller không được đọc

Giả sử API có endpoint:

```http
GET /api/invoices/inv-2048
Authorization: Bearer <alice-access-token>
```

Trong database, hóa đơn thuộc Bob:

| invoice_id | owner_id | tenant_id | status |
|---|---|---|---|
| `inv-2048` | `user-bob` | `tenant-7` | `ISSUED` |

Alice có token hợp lệ và biết `inv-2048`. Nếu API chỉ truy vấn theo ID, nó sẽ trả hóa đơn của Bob.

### 3.1. Cách triển khai dễ mắc lỗi

```java
public Invoice getInvoice(String invoiceId) {
    return invoiceRepository.findById(invoiceId)
        .orElseThrow(() -> new NotFoundException());
}
```

Phương thức này không nhận principal và không kiểm tra quan hệ sở hữu, tenant hay quyền được chia sẻ. Nó chỉ trả object nếu tìm thấy. Nếu controller gọi phương thức này sau khi xác thực token, endpoint vẫn có BOLA.

### 3.2. Cách xử lý có kiểm tra quyền

```java
public InvoiceDto getInvoice(String invoiceId, Principal principal) {
    Invoice invoice = invoiceRepository.findById(invoiceId)
        .orElseThrow(() -> new NotFoundException());

    if (!authorization.can(principal, "invoice:read", invoice)) {
        throw new NotFoundException(); // khi policy cần che giấu sự tồn tại
    }

    return invoiceMapper.toDto(invoice, principal);
}
```

Ở ví dụ này, API kiểm tra quyền sau khi tìm thấy object và trước khi serialize dữ liệu. Tùy chính sách, lỗi từ chối có thể là `403` nếu được phép tiết lộ object tồn tại, hoặc `404` nếu cần che giấu sự tồn tại. Điểm bắt buộc là không trả dữ liệu trước khi authorization thành công.

### 3.3. Giới hạn truy vấn theo tenant hoặc quan hệ

Nếu hệ thống có thể giới hạn ngay trong truy vấn, hãy tận dụng điều đó để giảm nguy cơ truy cập nhầm object. Ví dụ, truy vấn hóa đơn thuộc tenant của principal:

```sql
SELECT invoice_id, owner_id, tenant_id, status, total
FROM invoices
WHERE invoice_id = :invoiceId
  AND tenant_id = :principalTenantId;
```

Trong trường hợp chỉ chủ sở hữu được đọc:

```sql
SELECT invoice_id, owner_id, tenant_id, status, total
FROM invoices
WHERE invoice_id = :invoiceId
  AND tenant_id = :principalTenantId
  AND owner_id = :principalUserId;
```

`principalTenantId` và `principalUserId` phải lấy từ principal đã xác thực hoặc security context đáng tin cậy. Không lấy trực tiếp từ query/body do client gửi rồi coi đó là phạm vi quyền.

Nếu có quyền chia sẻ, vai trò quản trị tenant hoặc quan hệ phức tạp, truy vấn tenant/owner chỉ là một phần của policy. Có thể truy vấn object trong phạm vi tenant rồi gọi policy service để kiểm tra relationship, ACL, action và trạng thái. Không được bỏ qua bước này chỉ vì object đã nằm trong tenant.

## 4. Không tin ownerId, tenantId hoặc quyền do client tự khai báo

Một lỗi phổ biến là để client gửi trường xác định chủ sở hữu:

```json
{
  "invoiceId": "inv-2048",
  "ownerId": "user-alice",
  "tenantId": "tenant-7",
  "status": "APPROVED"
}
```

Các trường này là input không đáng tin cậy. Alice không thể tự cấp quyền bằng cách gửi `ownerId` bằng chính user ID của mình, cũng không thể tự chuyển object sang tenant mà cô ấy quản lý. API cần xác định principal từ credential đã xác minh và đọc quan hệ sở hữu/tenant từ dữ liệu được quản lý ở phía server.

Khi tạo object, server nên tự gán owner và tenant theo principal hoặc theo nghiệp vụ đã được authorization kiểm tra:

```pseudo
principal = requireAuthenticatedPrincipal(request)
targetProject = loadProject(request.projectId)
require authorization.can(principal, "project:document:create", targetProject)

document = Document(
    projectId = targetProject.id,
    tenantId = targetProject.tenantId,
    ownerId = principal.userId,
    title = validate(request.title)
)
save(document)
```

Nếu một nghiệp vụ cho phép tạo object thay mặt người khác, đó phải là quyền riêng, có điều kiện và audit rõ ràng. Không để một trường request thông thường âm thầm thay đổi owner.

## 5. Kiểm tra quyền với nested resource và quan hệ cha-con

API thường có route lồng nhau:

```http
GET /api/projects/project-10/documents/doc-90
```

Chỉ kiểm tra `project-10` tồn tại và caller có quyền đọc project là chưa đủ nếu `doc-90` thực tế thuộc project khác. Ngược lại, chỉ tìm document theo `doc-90` cũng không chứng minh nó thuộc project trên URL.

API phải kiểm tra cả quan hệ cha-con:

```sql
SELECT d.document_id, d.project_id, d.title
FROM documents d
JOIN projects p ON p.project_id = d.project_id
WHERE d.document_id = :documentId
  AND p.project_id = :projectId
  AND p.tenant_id = :principalTenantId;
```

Sau đó áp dụng policy cho action trên document, có thể cần cả quyền đối với project:

```pseudo
project = loadProject(projectId)
document = loadDocument(documentId)

if document.projectId != project.id:
    deny

if not authorization.can(principal, "document:read", document):
    deny

return document
```

Đây là vấn đề thường xuất hiện với project/task, account/transaction, organization/member, order/item và folder/file. Mỗi ID trong path đều cần được ràng buộc với đúng quan hệ; không nên coi URL lồng nhau tự tạo ra quyền.

## 6. Danh sách, tìm kiếm, phân trang và batch cũng phải có object authorization

Object authorization không chỉ áp dụng cho `GET /resource/{id}`. Các endpoint trả nhiều object thường dễ bỏ sót hơn:

- `GET /api/invoices?status=ISSUED`
- `POST /api/invoices/search`
- `POST /api/invoices/batch-read`
- `POST /api/invoices/export`

### 6.1. Lọc quyền trước khi phân trang

Một cách làm sai là lấy 100 bản ghi đầu tiên, rồi mới lọc những object caller không được phép đọc. Cách đó có thể làm lộ số lượng, tạo trang thiếu dữ liệu, bỏ sót object hợp lệ ở trang sau hoặc làm sai total count.

Nên áp dụng điều kiện truy cập ngay trong truy vấn trước khi sắp xếp và phân trang:

```sql
SELECT i.invoice_id, i.status, i.total
FROM invoices i
WHERE i.tenant_id = :principalTenantId
  AND (
      i.owner_id = :principalUserId
      OR EXISTS (
          SELECT 1
          FROM invoice_permissions p
          WHERE p.invoice_id = i.invoice_id
            AND p.principal_id = :principalId
            AND p.permission = 'READ'
      )
  )
ORDER BY i.created_at DESC
LIMIT :pageSize OFFSET :offset;
```

Điều kiện trên chỉ là ví dụ cho một policy cụ thể. Nếu có role hoặc relationship phức tạp, hãy xây dựng truy vấn hoặc policy evaluator tương ứng. Total count, facet, thống kê và export cũng phải áp dụng cùng phạm vi quyền; không được để endpoint đếm tiết lộ số object mà caller không được xem.

### 6.2. Batch request phải kiểm tra từng object

Với request chứa nhiều ID, không nên kiểm tra một lần rằng caller “có quyền với loại invoice” rồi xử lý toàn bộ danh sách. Mỗi object có thể có owner, tenant, trạng thái hoặc ACL khác nhau.

```pseudo
for invoiceId in request.invoiceIds:
    invoice = loadInvoice(invoiceId)
    if invoice exists and authorization.can(principal, "invoice:read", invoice):
        results.add(serialize(invoice))
    else:
        results.add(policyDefinedUnavailableResult(invoiceId))
```

API cần quy định rõ batch là atomic (toàn bộ thành công hoặc thất bại) hay partial success. Không trả chi tiết phân biệt object không tồn tại và object bị từ chối nếu chính sách cần che giấu sự tồn tại. Với batch lớn, giới hạn kích thước và thời gian xử lý để tránh resource abuse.

## 7. Quyền đọc, quyền sửa và quyền trên từng thuộc tính

Object authorization cần kết hợp với property-level authorization. Một principal có thể được đọc object nhưng không được đọc mọi field; có thể sửa một số thuộc tính nhưng không được sửa trường quyết định quyền hoặc trạng thái tài chính.

Ví dụ một hóa đơn có `invoiceId`, `customerName`, `total`, `tax`, `paymentStatus`, `approvedBy` và `internalNote`. Khách hàng có thể xem tên và tổng tiền, nhưng không được xem ghi chú nội bộ hoặc sửa `paymentStatus`. Nhân viên kế toán có thể cập nhật mã đối chiếu nhưng không được tự phê duyệt hóa đơn của mình.

Không bind trực tiếp request body vào entity đầy đủ:

```java
// Rủi ro mass assignment: request có thể chứa ownerId, tenantId, approvedBy...
BeanUtils.copyProperties(request, invoice);
```

Hãy xác định field được phép cập nhật và kiểm tra policy cho từng action:

```pseudo
invoice = loadInvoice(invoiceId)
require authorization.can(principal, "invoice:update", invoice)

if request.total exists:
    require authorization.can(principal, "invoice:change-total", invoice)
    invoice.total = validateMoney(request.total)

if request.internalNote exists:
    require authorization.can(principal, "invoice:update-internal-note", invoice)
    invoice.internalNote = validateText(request.internalNote)

save(invoice)
```

Response cũng cần serialize theo danh sách field caller được đọc. Quyền đọc object không có nghĩa được trả toàn bộ entity hoặc các trường nội bộ.

## 8. Object authorization với file, media và signed URL

Một API có thể bảo vệ metadata của file nhưng vô tình để lộ nội dung qua object storage hoặc CDN. Ví dụ, endpoint kiểm tra user được phép xem document rồi trả URL tải file có thời hạn quá dài hoặc có thể chia sẻ cho bất kỳ ai.

Khi xử lý file:

- Xác minh quyền trên object metadata và quyền `download` riêng nếu nghiệp vụ yêu cầu.
- Ràng buộc file key với object đã được authorization; không nhận storage path tùy ý từ client.
- Nếu tạo signed URL, giới hạn thời hạn, method, object key và quyền cần thiết; không tạo URL cho object mà caller chưa được phép tải.
- Hiểu rằng signed URL thường là bearer capability: ai có URL trong thời hạn hiệu lực có thể sử dụng. Không ghi URL đầy đủ vào log hoặc analytics.
- Khi quyền bị thu hồi, cân nhắc thời hạn URL ngắn, proxy download hoặc cơ chế thu hồi phù hợp; signed URL đã phát hành có thể tiếp tục hoạt động cho đến khi hết hạn tùy nhà cung cấp.
- Kiểm tra quyền cả ở thumbnail, preview, export, attachment và API lấy metadata.

Không nên coi việc file nằm trong bucket private là đủ. Ứng dụng vẫn phải xác minh người yêu cầu có quyền với object logic đang tham chiếu tới file.

## 9. Che giấu sự tồn tại của object và chọn HTTP response

Khi caller không được phép đọc một object, API cần quyết định có tiết lộ object tồn tại hay không. Đây là quyết định về thông tin được công khai, không phải cách thay thế authorization.

- **`403 Forbidden`:** phù hợp khi hệ thống có thể tiết lộ object tồn tại nhưng principal không được phép thực hiện action.
- **`404 Not Found`:** có thể được dùng cho cả object không tồn tại và object mà caller không được biết đến, nhằm giảm khả năng dò tài nguyên.

Ví dụ, với hóa đơn cá nhân, việc tiết lộ “hóa đơn này tồn tại nhưng thuộc Bob” cũng có thể làm lộ quan hệ khách hàng. API có thể trả cùng một response `404` cho ID không tồn tại và ID nằm ngoài phạm vi Alice được phép thấy.

Nếu chọn che giấu bằng `404`, cần áp dụng nhất quán cho các endpoint liên quan: đọc chi tiết, tải file, xem lịch sử, tìm kiếm, batch, export và thao tác thay đổi trạng thái. Nếu `GET` trả 404 nhưng `PATCH` trả 403 hoặc endpoint kiểm tra riêng trả “owner là Bob”, API vẫn tiết lộ sự tồn tại.

Ngoài status code, hãy xem xét side-channel:

- Body và mã lỗi có khác nhau giữa object tồn tại nhưng bị cấm và object không tồn tại không?
- Thời gian phản hồi có khác biệt rõ ràng do một nhánh tải thêm nhiều dữ liệu hoặc gọi dịch vụ ngoài không?
- Header, redirect, kích thước response hoặc pagination có để lộ sự khác nhau không?
- Endpoint search/count có thể cho biết object có tồn tại dù endpoint detail đã che giấu không?

Không phải lúc nào cũng cần làm thời gian phản hồi giống hệt nhau; mục tiêu là tránh tạo khác biệt dễ khai thác và không cần thiết. Hãy chọn mức che giấu dựa trên độ nhạy của object và mô hình đe dọa. Trong log nội bộ có kiểm soát, vẫn cần reason code đủ rõ để điều tra object không tồn tại, object ngoài phạm vi hay lỗi policy.

## 10. Tránh TOCTOU: quyền có thể thay đổi giữa lúc kiểm tra và lúc thao tác

TOCTOU (Time-of-check to time-of-use) xảy ra khi hệ thống kiểm tra quyền ở một thời điểm, nhưng trạng thái object hoặc quan hệ quyền thay đổi trước khi thao tác thật sự diễn ra.

Ví dụ:

1. Alice là editor của project và API kiểm tra Alice được sửa document.
2. Quản trị viên thu hồi quyền editor của Alice.
3. Request cũ tiếp tục cập nhật document bằng kết quả authorization đã cache hoặc đã kiểm tra trước đó.

Với thao tác nhạy cảm, nên gắn kiểm tra quyền và thay đổi dữ liệu trong cùng transaction hoặc dùng điều kiện cập nhật nguyên tử. Ví dụ, nếu chỉ owner hiện tại trong tenant được hủy hóa đơn đang ở trạng thái `PENDING`:

```sql
UPDATE invoices
SET status = 'CANCELLED', updated_at = CURRENT_TIMESTAMP
WHERE invoice_id = :invoiceId
  AND tenant_id = :principalTenantId
  AND owner_id = :principalUserId
  AND status = 'PENDING';
```

Sau đó kiểm tra số dòng bị cập nhật. Nếu bằng 0, API không được giả định rằng thao tác thành công; object có thể không tồn tại, caller ngoài phạm vi hoặc trạng thái đã thay đổi. Response được chọn theo chính sách tiết lộ thông tin.

Với policy phức tạp dựa trên ACL/relationship, cần cân nhắc isolation level, khóa, version column hoặc kiểm tra điều kiện ngay trong câu lệnh cập nhật. Không giữ một quyết định `ALLOW` trong cache lâu hơn thời gian policy có thể thay đổi mà không có cơ chế invalidation.

## 11. Những nơi dễ bỏ sót object authorization

| Bề mặt API | Rủi ro | Kiểm soát cần có |
|---|---|---|
| Detail endpoint | Đổi ID để đọc object của người khác | Kiểm tra principal-action-object |
| Update/delete | Sửa hoặc xóa object ngoài phạm vi | Authorization cho action và điều kiện trạng thái |
| Nested resource | Child ID không thuộc parent ID trong URL | Kiểm tra quan hệ cha-con và quyền trên child |
| Search/list/count | Lộ object, tổng số hoặc metadata qua bộ lọc | Lọc theo quyền trước pagination/aggregation |
| Batch/export | Một số ID không được phép bị xử lý chung | Kiểm tra từng object, xác định semantics partial/atomic |
| GraphQL | Resolver con trả object mà resolver cha đã kiểm tra không đủ | Kiểm tra quyền tại resolver/service truy cập object, tránh tin ID từ arguments |
| File/attachment | Metadata được bảo vệ nhưng URL tải file bị lộ | Quyền download, signed URL ngắn hạn, ràng buộc object key |
| WebSocket/event stream | Subscription tiếp tục nhận dữ liệu sau khi quyền bị thu hồi | Xác thực subscription và re-check quyền khi ACL/tenant thay đổi |
| Background job | Job dùng object ID cũ sau khi quyền hoặc owner đổi | Xác định principal/delegation, kiểm tra quyền tại thời điểm thực thi |
| Cache | Response của Alice được phục vụ cho Bob | Cache key và policy phải cô lập theo principal/tenant; không cache công khai dữ liệu riêng tư |

### 11.1. Cache không được biến thành đường vòng authorization

Nếu cache response chỉ theo URL `/api/invoices/inv-2048`, Alice có quyền đọc có thể làm nóng cache. Sau đó Bob hoặc người dùng khác có thể nhận response đó nếu cache không phân biệt danh tính hoặc phạm vi truy cập.

Với dữ liệu riêng tư, cần dùng cache policy phù hợp như `private` hoặc `no-store` khi cần; nếu cache ở tầng ứng dụng, key phải bao gồm phạm vi authorization cần thiết và phải invalidation khi quyền thay đổi. Không chỉ dựa vào `Vary: Authorization` mà bỏ qua cấu hình CDN/proxy thực tế. Cần kiểm thử cache ở mọi tầng, gồm browser, gateway, reverse proxy và CDN.

### 11.2. Quyền trong job bất đồng bộ

Một request có thể tạo job export hoặc gửi file sau vài phút. Nếu chỉ kiểm tra quyền lúc tạo job, quyền có thể bị thu hồi trước khi job chạy. Thiết kế cần quyết định rõ job chạy dưới quyền của ai: service account với quyền hệ thống, hay user đã yêu cầu với quyền được ủy quyền. Nếu chạy thay mặt user, nên lưu principal/delegation context đáng tin và đánh giá lại quyền trên object khi thực thi. Không dùng một user ID tự do trong payload làm bằng chứng ủy quyền.

## 12. Kiểm thử object authorization theo ma trận

Kiểm thử cần tạo nhiều principal và object với quan hệ khác nhau. Một test chỉ xác minh user A đọc object của A thành công chưa đủ; cần xác minh user A không đọc object của B, kể cả khi biết chính xác ID.

Ví dụ ma trận cho hai tenant và hai user:

| Principal | Object | Quan hệ | `read` | `update` |
|---|---|---|---|---|
| Alice / tenant A | Invoice A1 | Owner | Allow | Allow nếu trạng thái cho phép |
| Alice / tenant A | Invoice A2 | Được chia sẻ read-only | Allow | Deny |
| Alice / tenant A | Invoice B1 | Thuộc tenant B | Deny | Deny |
| Bob / tenant B | Invoice B1 | Owner | Allow | Allow nếu trạng thái cho phép |
| Tenant admin A | Invoice A2 | Admin trong tenant A | Theo policy | Theo policy |
| Tenant admin A | Invoice B1 | Khác tenant | Deny | Deny |

Nên có các nhóm kiểm thử sau:

1. **Object tồn tại và được phép:** principal đúng quan hệ, action hợp lệ, trạng thái cho phép.
2. **Object tồn tại nhưng không được phép:** dùng ID chính xác của user/tenant khác; xác minh không có dữ liệu hoặc side effect.
3. **Object không tồn tại:** response không tiết lộ thông tin ngoài policy.
4. **Object tồn tại nhưng trạng thái không cho phép:** đã thanh toán, đã khóa, đã xóa mềm hoặc đang chờ phê duyệt.
5. **Sai quan hệ cha-con:** child ID thuộc project khác với parent ID trong URL.
6. **Sai thuộc tính:** gửi `ownerId`, `tenantId`, `role`, `approvedBy` hoặc field nhạy cảm trong body.
7. **Bulk/list/search:** kiểm tra từng object, total count, pagination, aggregate và export.
8. **Thay đổi quyền đồng thời:** thu hồi ACL/role trong lúc request hoặc job đang xử lý.
9. **Cache/file:** xác minh response, signed URL và file không bị dùng lại bởi principal khác.
10. **Nhiều action:** read, update, delete, approve, share và download có policy riêng.

Với mỗi test từ chối, hãy kiểm tra cả response lẫn trạng thái hệ thống: database không bị thay đổi, event không được phát, job không được tạo và file không bị tải. Một endpoint trả `403` nhưng đã thực hiện side effect trước đó vẫn là lỗi bảo mật.

### 12.1. Kiểm thử bằng cách thay object ID

Một bài test BOLA đơn giản có thể thực hiện:

```text
1. Đăng nhập bằng Alice và lấy access token A.
2. Dùng token A gọi GET /api/invoices/invoice-A.
   Kỳ vọng: thành công theo policy.
3. Thay ID bằng invoice-B, thuộc Bob, giữ nguyên token A.
   Kỳ vọng: bị từ chối, không trả dữ liệu Bob.
4. Dùng token B của Bob gọi invoice-B.
   Kỳ vọng: thành công theo policy.
5. Dùng token A gọi PATCH/DELETE invoice-B.
   Kỳ vọng: bị từ chối và dữ liệu không thay đổi.
```

Không nên chỉ thử ID ngẫu nhiên. Test phải dùng object thật của principal khác để chứng minh API kiểm tra quyền chứ không đơn thuần trả 404 vì không tìm thấy.

## 13. Ghi log và giám sát quyết định object authorization

Để phát hiện dò object hoặc truy cập chéo tenant, log bảo mật cần cung cấp ngữ cảnh đủ để điều tra:

- Principal đã xác thực và loại principal.
- Action và route template, không nhất thiết ghi nguyên URL có ID nhạy cảm.
- Object type và định danh nội bộ đã được xử lý theo chính sách dữ liệu.
- Tenant/phạm vi truy cập được xác minh.
- Kết quả `ALLOW`/`DENY` và reason code như `NOT_OWNER`, `TENANT_MISMATCH`, `ACL_DENIED` hoặc `STATE_NOT_ALLOWED`.
- Request ID, trace ID, thời gian, client và kết quả HTTP.

Không ghi access token, cookie, secret hoặc toàn bộ dữ liệu object vào log. Cần bảo vệ log khỏi sửa đổi, giới hạn người được đọc và đặt thời hạn lưu phù hợp.

Các dấu hiệu có thể tạo alert:

- Một principal thử truy cập nhiều object ID liên tiếp nhưng phần lớn bị từ chối.
- Một client liên tục thay `userId`, `tenantId`, `projectId` hoặc `invoiceId` trong request.
- Tỷ lệ `403`/`404` tăng đột biến trên endpoint chứa object ID.
- Một principal đọc số lượng object lớn hoặc export dữ liệu vượt mức thông thường.
- Có request thành công với quan hệ tenant/owner bất thường hoặc truy cập từ version API cũ.

Alert cần dựa trên baseline và ngữ cảnh. Người dùng hợp lệ có thể gặp nhiều lỗi khi mở link cũ; một đợt từ chối lớn không tự động chứng minh tấn công. Hãy kết hợp tần suất, loại object, principal, client và kết quả hành động.

## 14. Checklist trước khi phát hành endpoint truy cập object

- [ ] Endpoint xác định rõ object type và action mà nó cung cấp.
- [ ] Principal được tạo từ authentication đã xác minh; không lấy danh tính từ header/body tùy ý.
- [ ] Mọi object ID trong path, query, body và nested route đều được ràng buộc với đúng object/tenant.
- [ ] Quyền được kiểm tra trên bộ principal-action-object-context, không chỉ kiểm tra role hoặc object existence.
- [ ] Quyền read, update, delete, approve, share và download được phân biệt khi nghiệp vụ yêu cầu.
- [ ] Owner, tenant và relationship được lấy từ dữ liệu đáng tin cậy; client không thể tự gán quyền qua mass assignment.
- [ ] List/search/count/export lọc object theo quyền trước pagination và aggregation.
- [ ] Batch xử lý từng object và có semantics partial/atomic rõ ràng.
- [ ] Child resource được kiểm tra quan hệ với parent trong URL.
- [ ] File, signed URL, cache, GraphQL, event stream và background job có kiểm tra quyền tương ứng.
- [ ] Quyết định `403`/`404` phù hợp với chính sách tiết lộ sự tồn tại và nhất quán trên các endpoint.
- [ ] Thao tác nhạy cảm xử lý TOCTOU bằng transaction hoặc điều kiện cập nhật nguyên tử.
- [ ] Có negative tests với object thật của user/tenant khác và xác minh không có side effect.
- [ ] Logs và alerts đủ để phát hiện object enumeration, truy cập chéo tenant và hành vi bất thường.

## 15. Nguyên tắc cần ghi nhớ

Object tồn tại chỉ có nghĩa là hệ thống tìm thấy dữ liệu. Nó không chứng minh caller là chủ sở hữu, thuộc đúng tenant, có quan hệ được chia sẻ hoặc có quyền thực hiện action. Mỗi request cần được đánh giá theo principal đã xác thực, action cụ thể, object cụ thể và context hiện tại.

UUID, URL khó đoán, nút bị ẩn hoặc một lần kiểm tra đăng nhập không thay thế object authorization. Cần kiểm tra quyền trên detail, nested resource, list, search, batch, export, file và các luồng bất đồng bộ. Khi che giấu sự tồn tại bằng `404`, hãy áp dụng nhất quán và xem cả side-channel; khi quyền hoặc trạng thái có thể thay đổi, hãy tránh dùng quyết định cũ cho thao tác mới.

Một cách tự kiểm tra đơn giản là giữ nguyên token của Alice, thay ID sang object thật của Bob và thử mọi action quan trọng. Nếu API vẫn trả dữ liệu hoặc tạo side effect, endpoint chưa bảo vệ đúng object. Đây là kiểm tra cơ bản nhưng rất hiệu quả để phát hiện BOLA trong API.

## Tài liệu tham khảo

- OWASP API Security Top 10 (2023) — API1:2023 Broken Object Level Authorization.
- OWASP Authorization Cheat Sheet — nguyên tắc deny by default và kiểm tra quyền trên mọi request.
- OWASP Insecure Direct Object Reference Prevention Cheat Sheet.
- OWASP Access Control Cheat Sheet — kiểm soát quyền theo đối tượng và action.
- RFC 9110 — HTTP Semantics: ý nghĩa của `403 Forbidden` và `404 Not Found`.
