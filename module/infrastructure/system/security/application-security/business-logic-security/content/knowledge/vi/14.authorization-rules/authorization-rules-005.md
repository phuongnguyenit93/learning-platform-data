# Phân quyền theo quyền sở hữu đối tượng (Ownership authorization)

Một người đã đăng nhập không mặc nhiên được đọc hoặc sửa mọi đối tượng mà họ biết mã định danh. Với nhiều nghiệp vụ, quyền phụ thuộc quan hệ giữa chủ thể và đối tượng: ai sở hữu hồ sơ, ai đang được giao xử lý, đối tượng thuộc tenant nào và hành động đang yêu cầu là gì.

Ví dụ, nhân viên A có thể sửa đơn đề nghị mua hàng do mình sở hữu khi đơn còn là bản nháp. Nếu A đổi ID trên đường dẫn thành đơn của B, máy chủ phải chặn. Nếu A vẫn dùng đúng đơn của mình nhưng muốn tự phê duyệt hoặc sửa nội dung đã được duyệt, quan hệ sở hữu cũng không đủ để cho phép.

Bài học thuộc chương **Authorization Rules** trong bảo mật logic nghiệp vụ. Trọng tâm là dùng ownership như một quan hệ phân quyền có nguồn đáng tin cậy, thực thi trên mọi đường truy cập và giữ đúng trước thay đổi đồng thời, retry hoặc chuyển chủ sở hữu.

## 1. Ownership là quan hệ có phạm vi, không phải quyền tuyệt đối

Có thể biểu diễn một quan hệ:

```text
Owns(subject, resource, tenant)
```

Tuy nhiên, quyết định phân quyền cần thêm hành động và điều kiện:

```text
Allow(subject, action, resource, context) =

    subject đã được xác thực theo yêu cầu
    AND subject được hoạt động trong tenant tương ứng
    AND resource thuộc đúng phạm vi
    AND quan hệ sở hữu hoặc quyền được cấp phù hợp với action
    AND trạng thái và các điều kiện nghiệp vụ cho phép
```

Đối tượng thuộc về người gọi chỉ là một điều kiện trong quyết định. Nó không cho phép bỏ qua phê duyệt độc lập, hạn mức, tính hợp lệ của giá, trạng thái đã khóa hoặc cơ chế chống yêu cầu trùng.

### 1.1. Ví dụ về quyền của chủ sở hữu

Với đơn đề nghị mua hàng trong bài:

| Hành động | Chủ sở hữu có được làm không? |
|---|---|
| Xem đơn trong tenant được phép | Có, theo chính sách đọc |
| Sửa nội dung bản nháp | Có, nếu có quyền nền và dữ liệu hợp lệ |
| Gửi bản nháp vào xét duyệt | Có, nếu đáp ứng điều kiện gửi |
| Tự duyệt chính đơn mình lập | Không, nếu vi phạm phân tách nhiệm vụ |
| Sửa giá trị đã được phê duyệt mà giữ nguyên quyết định cũ | Không |
| Chuyển đơn sang tenant khác | Không chỉ dựa vào ownership |
| Chuyển quyền sở hữu | Chỉ qua hành động và quy tắc chuyển riêng |
| Xem tài liệu không thuộc đơn | Không chỉ vì là chủ một đơn khác |

Bảng này mô tả chính sách ví dụ. Một hệ thống khác có thể cho phép tập hành động khác, nhưng phải xác định rõ theo từng action.

### 1.2. Không nhầm các quan hệ gần nhau

| Trường hoặc quan hệ | Ý nghĩa |
|---|---|
| `createdBy` | Danh tính thực sự tạo bản ghi, phục vụ nguồn gốc và audit |
| `ownerSubjectId` | Chủ thể sở hữu theo mô hình nghiệp vụ hiện tại |
| `assignedTo` | Người hoặc nhóm đang được giao một công việc |
| `requestedFor` | Chủ thể được đại diện hoặc được hưởng kết quả đề nghị |
| `tenantId` | Phạm vi tổ chức của đối tượng |
| Vai trò quản trị tenant | Một tập thẩm quyền của tổ chức, không tự đồng nhất với ownership của từng tài nguyên |

Người tạo và chủ sở hữu có thể trùng lúc ban đầu nhưng thay đổi khác nhau về sau. Nếu có chức năng tạo hộ, không nên thay `createdBy` bằng người được khai trong body rồi làm mất danh tính thực.

Tương tự, một người được giao duyệt không nhất thiết trở thành chủ sở hữu có thể sửa nội dung cần duyệt.

## 2. Xác định chủ sở hữu từ nguồn có thẩm quyền

Để kiểm tra ownership, hai phía của phép so sánh đều cần đáng tin cậy:

```text
chủ thể hiện tại từ ngữ cảnh xác thực và ánh xạ danh tính có thẩm quyền
    so với
quan hệ sở hữu hiện tại từ dữ liệu phía máy chủ
```

Không lấy cả hai giá trị từ request rồi so sánh chúng với nhau.

### 2.1. Khi tạo đối tượng

Một endpoint tự phục vụ có thể nhận nội dung nghiệp vụ:

```http
POST /purchase-requests
Content-Type: application/json

{
  "purpose": "Thiết bị cho nhóm triển khai",
  "lines": [
    { "productId": "PRD-10", "quantity": 2 }
  ]
}
```

Máy chủ xác định tenant và chủ sở hữu theo danh tính, quyền và chính sách. Client không được tự chèn:

```json
{
  "ownerSubjectId": "person-B",
  "tenantId": "tenant-other",
  "createdBy": "director-01",
  "status": "APPROVED"
}
```

Nếu endpoint cho phép tạo hộ hoặc chọn nhóm sở hữu, cần kiểm tra quyền riêng cho việc đó và lưu cả người thực hiện lẫn chủ thể được chỉ định. Không dùng cùng một DTO cập nhật chung để vô tình cho mọi người thay owner.

### 2.2. Danh tính phải phù hợp với mô hình ownership

Một account, một con người và một tổ chức có thể là các định danh khác nhau. Hệ thống cần chọn rõ ownership được gắn với loại chủ thể nào.

Ví dụ, nếu một người có hai tài khoản liên kết, việc đổi account không nhất thiết tạo ra một chủ thể nghiệp vụ khác. Ngược lại, chỉ có cùng tên hiển thị hoặc cùng địa chỉ liên hệ không đủ để kết luận là cùng chủ thể.

Nếu hỗ trợ nhóm sở hữu, nên mô hình hóa loại chủ thể và ID tương ứng:

```text
ownerType = PERSON hoặc TEAM
ownerId   = định danh theo đúng loại
```

Quyền của một thành viên nhóm phải được kiểm tra theo vai trò trong nhóm và hành động, không mặc định mọi thành viên được chuyển nhượng hoặc xóa tài nguyên.

Mã Java trong bài chỉ minh họa nhánh sở hữu trực tiếp bởi một chủ thể cá nhân. Nhánh nhóm hoặc ủy quyền cần chính sách riêng được kiểm chứng.

### 2.3. Thuộc tính trong phiên đăng nhập không thay thế owner của đối tượng

Một phiên có thể chứa tenant hoặc vai trò đã được cấp tại thời điểm phát hành. Nó không tự chứng minh một đối tượng cụ thể vẫn thuộc người dùng.

Không nhận `ownerId` từ query, hidden field hoặc claim do client tự tạo làm nguồn chân lý. Khi quan hệ sở hữu thay đổi, các quyết định dùng dữ liệu cũ cần được vô hiệu hoặc đánh giá lại theo hợp đồng nhất quán của hệ thống.

## 3. Chặn truy cập sai đối tượng trên từng hành động

Một lỗi điển hình:

```java
// Chỉ chứng minh đã đăng nhập, chưa chứng minh quyền với đối tượng.
requireAuthenticated();
return repository.findById(requestId);
```

Người A có thể đổi `requestId` thành mã của B. Rủi ro tương tự xuất hiện ở thao tác sửa, xóa, tải tài liệu, xuất báo cáo và endpoint con.

ID khó đoán không thay thế phân quyền đối tượng. Đường kiểm tra phải xác định người gọi có quyền với chính đối tượng được sử dụng trong hành động.

### 3.1. Phạm vi tenant và owner phải cùng đúng

Trong mô hình trực tiếp của bài:

```text
resource.tenantId == authorizedTenant
AND resource.ownerSubjectId == authenticatedSubject
```

Chỉ so owner có thể sai nếu ID chủ thể không có ý nghĩa toàn cục hoặc một người hoạt động trong nhiều tổ chức với quyền khác nhau. Chỉ so tenant lại cho phép mọi thành viên tenant truy cập dữ liệu của nhau.

Tenant được chọn trên giao diện cũng cần được kiểm tra với quyền hiện tại của người gọi. Một header `X-Tenant-Id` không tự tạo quyền tham gia tenant đó.

### 3.2. Tách quyền đọc, sửa và quyền đặc biệt

Một chính sách có thể cho phép:

- Chủ sở hữu đọc và sửa bản nháp của mình.
- Người duyệt đọc nội dung cần xét và ghi quyết định khi được phân công hợp lệ.
- Nhân viên hỗ trợ đọc một phần dữ liệu trong phạm vi được cấp.
- Một vai trò riêng thực hiện chuyển ownership theo quy trình.

Không nên gộp thành một điều kiện rộng:

```java
// Quá rộng nếu nhánh admin không xét phạm vi và hành động.
if (isOwner || isAdmin) {
    allowEverything();
}
```

Mỗi nhánh cho phép cần có action, phạm vi và guard rõ ràng. Nếu hệ thống cần quyền hỗ trợ hoặc quản trị xuyên đối tượng, đó là một chính sách có thẩm quyền riêng, có audit phù hợp.

## 4. Giới hạn truy vấn đọc và danh sách

Với tài nguyên chỉ chủ sở hữu được đọc, truy vấn có thể giới hạn ngay từ nguồn:

```sql
SELECT id,
       state,
       purpose,
       content_revision,
       row_version
FROM purchase_request
WHERE tenant_id = :authorized_tenant_id
  AND owner_subject_id = :authenticated_subject_id
  AND id = :request_id;
```

Các placeholder là tham số bind. Hai giá trị về tenant và subject đến từ ngữ cảnh đã được kiểm tra, không phải lời khai tùy ý của request.

Nếu truy vấn không có kết quả, API có thể trả phản hồi không tìm thấy theo chính sách che giấu sự tồn tại. Không chạy thêm truy vấn toàn cục rồi trả tên chủ thật cho người đang bị chặn.

### 4.1. Danh sách, tìm kiếm và thống kê

Endpoint danh sách cũng cần cùng phạm vi:

```sql
SELECT id, state, purpose
FROM purchase_request
WHERE tenant_id = :authorized_tenant_id
  AND owner_subject_id = :authenticated_subject_id
ORDER BY id;
```

Phân trang, bộ lọc trạng thái và sắp xếp phải hoạt động trên tập đã được phân quyền. Không tải một trang dữ liệu của mọi người rồi loại bản ghi không được xem sau đó mà vẫn để lộ tổng số, nhóm thống kê hoặc các trường liên quan.

Nếu có chế độ “đơn của nhóm”, “đơn chờ tôi duyệt” và “đơn của tôi”, cần xác định chính sách của từng chế độ. Một tham số `ownerId` do người dùng đổi không tự cho phép chuyển sang xem của người khác.

### 4.2. Không đánh đổi quyền lấy tiện lợi của giao diện

Giao diện có thể giữ `canEdit` để hướng dẫn người dùng. Máy chủ vẫn phải kiểm tra khi nhận lệnh vì owner, trạng thái hoặc quyền thành viên có thể thay đổi.

Một API trả metadata ít hơn hoặc một tài liệu xem trước vẫn có thể làm lộ nội dung. Cần xét đúng dữ liệu được truy cập, không chỉ endpoint chính.

## 5. Bảo vệ thao tác ghi bằng quyền, trạng thái và transaction

Với việc sửa bản nháp, cần cùng lúc xác nhận:

1. Người gọi hoạt động hợp lệ trong tenant.
2. Đối tượng hiện thuộc người gọi trong nhánh ownership trực tiếp.
3. Người gọi có quyền nền thực hiện loại hành động.
4. Đối tượng vẫn là bản nháp và version còn khớp.
5. Đầu vào nghiệp vụ hợp lệ, chỉ tác động những trường được phép.
6. Quyền và dữ liệu đã kiểm tra vẫn được bảo vệ đến khi ghi.

### 5.1. DTO theo ý định nghiệp vụ

```java
record LineInput(String productId, int quantity) {}

record UpdateDraftCommand(
        String requestId,
        long expectedVersion,
        String purpose,
        List<LineInput> lines,
        String idempotencyKey) {}
```

DTO không chứa `ownerSubjectId`, `tenantId`, `createdBy`, `approvedBy` hoặc `status`. Thao tác sửa nội dung không đồng thời là thao tác chuyển owner, chuyển tenant hay phê duyệt.

Nếu nghiệp vụ cho phép chọn đơn giá trong một loại giao dịch riêng, giá trị đó cũng cần quyền và quy tắc tương ứng. Với ví dụ này, client chỉ gửi sản phẩm, số lượng và mục đích; giá cùng các thành phần tổng tiền do máy chủ tính theo quy tắc có thẩm quyền.

### 5.2. Ví dụ Java ở nhánh chủ sở hữu trực tiếp

Đây là mã giả theo cú pháp Java, thể hiện thứ tự và hợp đồng giữa các thành phần. Nó chưa bao gồm cấu hình framework, repository hoặc cơ chế idempotency có thể chạy độc lập.

```java
DraftUpdated updateOwnDraft(
        UpdateDraftCommand command,
        ActorContext actor) {

    return transactions.required(() -> {
        memberships.requireActiveTenantAccess(actor);

        PurchaseRequest request = requests
                .findOwnedForUpdate(
                        actor.tenantId(),
                        actor.subjectId(),
                        command.requestId())
                .orElseThrow(ResourceNotFound::new);

        authorizer.requireActionCapability(
                actor, Action.UPDATE_OWN_PURCHASE_DRAFT);

        CommandClaim claim = commandLog.claimOrReplay(
                actor, "UPDATE_OWN_PURCHASE_DRAFT",
                command.idempotencyKey(), fingerprintOf(command));

        if (claim.isCompletedReplay()) {
            return claim.savedDraftUpdated();
        }

        request.requireVersion(command.expectedVersion());
        request.requireState(RequestState.DRAFT);

        // Kiểm tra sản phẩm, số lượng và dựng giá theo quy tắc máy chủ.
        DraftContent content = draftBuilder.fromServerRules(
                actor.tenantId(), command.purpose(), command.lines());

        long previousVersion = request.rowVersion();
        request.replaceDraftContent(content);
        request.advanceContentRevision();

        int changed = requests.saveOwnedDraftIfVersion(
                request, actor.subjectId(), previousVersion);

        if (changed != 1) {
            throw new ConcurrentChange();
        }

        requestLines.replaceForRequest(
                actor.tenantId(), request.id(), content.lines());

        audit.appendDraftUpdated(
                request.id(), actor.actorId(),
                request.contentRevision());

        outbox.appendPurchaseDraftChanged(
                request.id(), request.contentRevision());

        DraftUpdated result = DraftUpdated.from(request);
        commandLog.complete(claim, result);
        return result;
    });
}
```

Các hợp đồng cần có:

- `actor` lấy từ nguồn xác thực và ánh xạ danh tính đáng tin cậy. `actorId` nhận diện tác nhân thực, còn `subjectId` là chủ thể dùng trong quan hệ sở hữu của mô hình này.
- Mã giả chỉ dành cho luồng trực tiếp. Tạo ngữ cảnh “thực hiện thay” phải có kiểm tra ủy quyền; không cho client tùy ý chọn `subjectId`.
- `findOwnedForUpdate` lọc cả tenant, owner và ID trước khi trả đối tượng, đồng thời giữ khóa phù hợp tới hết transaction.
- `saveOwnedDraftIfVersion` cập nhật có điều kiện theo phạm vi, owner, trạng thái và version; mọi đường sửa có liên quan phải tuân thủ giao thức nhất quán.
- Ghi root, các dòng hàng, audit thành công, outbox và kết quả idempotency cùng transaction cục bộ trong thiết kế minh họa.
- `transactions.required` chỉ trả kết quả sau commit; lỗi kiểm tra hoặc lỗi ghi phải rollback các thay đổi tương ứng.
- Nguồn giá, chính sách và quyền thành viên cần quy tắc hiệu lực rõ ràng. Khóa hàng đơn không tự khóa một dịch vụ danh mục hay một hệ thống danh tính bên ngoài.

Nhánh replay được đặt sau kiểm tra truy cập hiện tại nhưng trước các guard của một lần sửa mới. Nếu owner đã chuyển, người cũ không được nhận kết quả nhạy cảm chỉ vì biết idempotency key.

### 5.3. Cập nhật có điều kiện tại nơi ghi

Một câu lệnh cho phần dữ liệu gốc có thể có dạng:

```sql
UPDATE purchase_request
SET purpose = :validated_purpose,
    total_minor_units = :server_calculated_total,
    content_revision = content_revision + 1,
    row_version = row_version + 1
WHERE tenant_id = :authorized_tenant_id
  AND id = :request_id
  AND owner_subject_id = :authenticated_subject_id
  AND state = 'DRAFT'
  AND row_version = :expected_row_version;
```

Câu lệnh này không sửa owner và không nhận tổng tiền tự khai làm dữ liệu có thẩm quyền.

- Một hàng được cập nhật: điều kiện ghi đã khớp; vẫn chờ transaction hoàn tất.
- Không hàng nào: có xung đột hoặc điều kiện không còn đúng; không tiếp tục sửa bảng con như thể đã thành công.
- Nhiều hơn một hàng: giả định định danh hoặc truy vấn sai; rollback và điều tra.

Không dùng số hàng bằng không để tự suy ra tên owner mới rồi tiết lộ cho người đã mất quyền. Phân loại lỗi cần phù hợp chính sách bảo mật và ngữ nghĩa API.

## 6. Tài nguyên con, đường dẫn lồng nhau và tài liệu

Đường dẫn chứa ID của một đối tượng mà người gọi sở hữu chưa đủ để cho phép truy cập mọi ID con đi kèm.

Ví dụ:

```http
GET /purchase-requests/PR-A/attachments/ATT-B
```

A sở hữu `PR-A`, nhưng `ATT-B` thuộc đơn của B. Nếu handler chỉ kiểm tra `PR-A` rồi tải attachment bằng ID toàn cục, A vẫn lấy được tài liệu của B.

Cần chứng minh cả:

```text
người gọi có quyền với parent
AND child thật sự thuộc đúng parent đó
AND child cùng tenant hoặc quan hệ phạm vi hợp lệ
AND action với child được chính sách cho phép
```

Một truy vấn minh họa:

```sql
SELECT a.id, a.storage_key, a.document_version
FROM purchase_attachment a
JOIN purchase_request p
  ON p.tenant_id = a.tenant_id
 AND p.id = a.request_id
WHERE p.tenant_id = :authorized_tenant_id
  AND p.owner_subject_id = :authenticated_subject_id
  AND p.id = :parent_id_from_path
  AND a.id = :attachment_id_from_path;
```

Nếu tài nguyên con có chính sách riêng, phải đánh giá thêm chính sách đó. Không dùng sự tồn tại của quan hệ parent như một quyền tuyệt đối.

### 6.1. Tránh nhiều bản sao owner không nhất quán

Nếu bảng con sao chép owner của parent, một lần chuyển owner có thể cập nhật bảng gốc nhưng bỏ sót tài liệu, bình luận hoặc cache.

Cần chọn nguồn có thẩm quyền và cách duy trì nhất quán. Có thể suy quyền qua parent hoặc có một mô hình quyền riêng được đồng bộ rõ ràng; tránh để từng endpoint chọn ngẫu nhiên một cột owner khác nhau.

Các quan hệ dữ liệu cũng cần giữ tenant và parent đúng. Một khóa ngoại tới ID tồn tại chưa đủ biểu đạt mọi ràng buộc tenant nếu schema không thiết kế cho điều đó.

### 6.2. Link tải và kho tệp

Kiểm tra quyền trước khi cấp quyền tải tài liệu hoặc sinh link truy cập. Không suy ra quyền đọc từ việc người dùng đã biết tên tệp hay storage key.

Nếu dùng link có chữ ký, cần hiểu nó là một khả năng truy cập theo hợp đồng của cơ chế đó. Phạm vi, hiệu lực và khả năng thu hồi cần được xác định; việc owner đổi trong cơ sở dữ liệu không tự làm mọi link đã phát mất hiệu lực.

Thông tin trong thông báo và bản xem trước cũng cần cùng chính sách dữ liệu. Không chặn endpoint chính nhưng để lộ nội dung qua hình thu nhỏ hoặc URL tải công khai.

## 7. Chuyển ownership là một hành động có kiểm soát riêng

Cho phép sửa nội dung không có nghĩa được sửa `ownerSubjectId`.

Một lệnh chuyển owner cần kiểm tra:

| Điều kiện | Câu hỏi cần trả lời |
|---|---|
| Quyền chuyển | Người gọi có được chuyển đối tượng này không? |
| Trạng thái | Đối tượng có đang ở giai đoạn được phép chuyển không? |
| Người nhận | Chủ thể mới có tồn tại, đang hoạt động và đủ điều kiện trong tenant không? |
| Phạm vi | Đây là chuyển owner trong tenant hay một quy trình chuyển dữ liệu khác? |
| Chấp nhận | Có cần người nhận đồng ý trước khi nhận trách nhiệm không? |
| Nội dung và phê duyệt | Việc chuyển có ảnh hưởng quyết định, phân công hoặc điều kiện độc lập không? |
| Đồng thời | Version, owner hiện tại và đề nghị chuyển có còn khớp không? |

Nếu cần chấp nhận hai phía, có thể tạo đề nghị chuyển rồi chỉ đổi owner sau khi người nhận chấp nhận hợp lệ. Trong thời gian chờ, phải xác định ai còn quyền gì và có đóng băng thao tác nào không.

Không cấp cho người được đề nghị nhận mọi quyền chỉ vì tên họ xuất hiện trong một yêu cầu chuyển chưa được chấp nhận. Họ có thể chỉ được xem những thông tin tối thiểu cần thiết theo chính sách.

### 7.1. Giữ nguyên nguồn gốc và chống né phân tách nhiệm vụ

Chuyển owner không được xóa hoặc viết lại `createdBy`, người lập nội dung hay lịch sử các quyết định.

Nếu người A lập đơn, chuyển owner sang B rồi tự quay lại duyệt, chính sách không được quên A là người đã thực hiện hành động xung đột. Quy tắc phân tách nhiệm vụ cần dùng đúng quan hệ lịch sử mà nó định nghĩa.

Các phê duyệt hoặc quyền liên quan có thể phải được đánh giá lại nếu ownership là thuộc tính ảnh hưởng quyết định. Điều đó cần một quy trình rõ ràng; không giữ nguyên mọi quyết định cũ một cách ngẫu nhiên.

### 7.2. Chuyển owner phải thay đổi version phù hợp

Việc owner đổi là thay đổi có ý nghĩa với phân quyền. Mọi đường chuyển cần phối hợp với đường sửa đối tượng, tăng version hoặc thế hệ quyền tương ứng và ghi audit.

Chỉ cập nhật một bảng danh bạ phụ mà không làm các đường truy cập biết quan hệ đã đổi có thể để owner cũ tiếp tục ghi bằng dữ liệu hoặc cache cũ.

## 8. Thay đổi đồng thời và dữ liệu phân quyền cũ

Xét một luồng không được bảo vệ:

```text
T1: đọc đối tượng, thấy owner là A
T2: chuyển owner từ A sang B, commit
T1: ghi đối tượng chỉ theo id
```

Lệnh của A có thể ghi sau khi A đã mất ownership. Một lần kiểm tra trước đó không đủ nếu điều kiện có thể đổi trước khi sử dụng.

Có thể kiểm soát bằng khóa hàng đối tượng trong transaction hoặc bằng cập nhật có điều kiện theo owner và version, kết hợp giao thức của mọi đường ghi. Trong ví dụ Java, truy vấn giữ khóa và câu cập nhật vẫn củng cố điều kiện.

### 8.1. Phạm vi của bảo đảm nhất quán

Khóa hàng tài nguyên không tự khóa:

- Quyền thành viên tenant ở một bảng hoặc dịch vụ khác.
- Tư cách thành viên nhóm sở hữu.
- Chính sách phân quyền và quan hệ ủy quyền.
- Kho tệp, cache hoặc projection phục vụ truy vấn khác.

Nếu yêu cầu nghiệp vụ đòi thu hồi quyền có hiệu lực tại một mốc chặt chẽ, cần cơ chế phối hợp đúng các dữ kiện đó, như khóa liên quan, version chính sách, thế hệ quyền hoặc chiến lược kiểm chứng tương ứng.

Một transaction cục bộ không tự tạo transaction toàn cục với hệ thống danh tính bên ngoài. Thiết kế phải nêu rõ mốc mà quyền được đánh giá và cách xử lý dữ liệu chưa xác minh được.

### 8.2. Cache quyết định phân quyền

Cache có thể giảm chi phí, nhưng quyết định `ALLOW` cũ có thể tiếp tục cho owner cũ truy cập.

Khóa cache cần biểu đạt đủ ngữ cảnh liên quan, chẳng hạn tenant, subject, resource, action và các phiên bản ownership, membership, policy hoặc ủy quyền mà quyết định phụ thuộc.

Dù vậy, chỉ thêm `ownershipVersion` vào khóa chưa giải quyết được gì nếu hệ thống vẫn lấy version cũ từ chính cache đã lỗi thời. Cần cách biết phiên bản hiện tại hoặc một hợp đồng hết hiệu lực, làm mới phù hợp mức nhất quán yêu cầu.

Thông báo vô hiệu cache bất đồng bộ có thể có độ trễ. Không xem nó như bảo đảm thu hồi tức thì nếu hệ thống chưa có cơ chế đáp ứng điều đó.

Khi cache hoặc nguồn quyền lỗi, không chuyển sang cho phép mọi người trong tenant hoặc coi người gọi là owner. Cách từ chối, thử lại và báo lỗi cần theo hợp đồng rõ ràng.

### 8.3. Quyền tạo lập trước đây và quyền hiện tại

Một người đã tạo đối tượng hoặc đã từng sửa được nó không mặc nhiên còn quyền hiện tại. Tương tự, biết idempotency key hoặc requestId của lệnh cũ không phải một grant truy cập mới.

Kết quả replay phải được bảo vệ như dữ liệu bình thường. Trong ví dụ, người gọi phải qua kiểm tra owner hiện tại trước khi được nhận lại kết quả nhạy cảm của lần sửa trước.

Một số nghiệp vụ cho người tạo giữ quyền xem lịch sử sau chuyển owner. Nếu có, đó là chính sách đọc riêng với phạm vi cụ thể, không phải hệ quả ngầm của `createdBy`.

## 9. Batch, tác vụ nền và đường truy cập thay thế

Ownership phải được kiểm tra ở nơi thực hiện hành động, bao gồm các đường ngoài giao diện chính.

### 9.1. Thao tác nhiều đối tượng

Một endpoint nhận danh sách ID có thể bị trộn đối tượng của A và B:

```json
{
  "requestIds": ["PR-A1", "PR-A2", "PR-B1"]
}
```

Không kiểm tra phần tử đầu rồi áp dụng kết quả cho toàn bộ danh sách.

Hai hợp đồng có thể dùng:

| Hợp đồng | Điều cần bảo đảm |
|---|---|
| Tất cả cùng thành công hoặc cùng thất bại | Mọi đối tượng được kiểm tra và ghi trong ranh giới nhất quán phù hợp; một phần tử không hợp lệ không để lại cập nhật dở dang |
| Xử lý từng phần tử | Mỗi phần tử có kiểm tra quyền và điều kiện riêng; kết quả không làm lộ nội dung của đối tượng bị chặn |

Với nhiều khóa, chọn thứ tự khóa ổn định để hạn chế deadlock. Bộ lọc tenant, owner và trạng thái vẫn cần được áp dụng ở các câu truy vấn liên quan.

Một câu lệnh ghi theo `id IN (...)` không tự mang theo các điều kiện đã được kiểm tra ở một phần tử khác.

### 9.2. Tác vụ xuất dữ liệu và báo cáo

Job tạo báo cáo cần giữ danh tính yêu cầu, tenant, action và phạm vi được cấp một cách đáng tin cậy. Không để job chạy bằng tài khoản kỹ thuật rộng quyền rồi lấy toàn bộ dữ liệu khớp những ID mà người dùng đã gửi.

Cần xác định quyền được đánh giá tại lúc tiếp nhận, lúc xử lý và lúc tải kết quả. Với báo cáo theo ownership hiện tại trong ví dụ, việc tạo hoặc tải sau chuyển owner phải được đánh giá lại theo chính sách đó.

Một snapshot báo cáo tạo ra trước khi chuyển owner cũng là dữ liệu cần bảo vệ. Chỉ kiểm tra quyền với đối tượng gốc nhưng để tệp báo cáo công khai vẫn làm lộ nội dung.

### 9.3. Tác vụ đã được chấp nhận và lệnh mới

Một lệnh nghiệp vụ đã được chấp nhận hợp lệ có thể tiếp tục xử lý bất đồng bộ theo hợp đồng của workflow. Ownership thay đổi sau đó có chặn execution đã xếp hàng hay không là điều cần quy định, không thể suy ra từ một cờ owner.

Nếu chính sách yêu cầu người gọi vẫn có quyền tại điểm thực thi, consumer phải kiểm tra điều kiện tương ứng trước tác dụng quan trọng. Nếu execution đã được cấp phép tại một mốc cụ thể, cần giữ căn cứ và giới hạn đó, đồng thời có quy tắc hủy hoặc thu hồi nếu áp dụng.

Đọc lại một message không được tạo thêm quyền hoặc thực hiện trùng tác dụng chỉ vì worker có tài khoản kỹ thuật mạnh.

### 9.4. Đại diện và dịch vụ gọi thay

Một dịch vụ nội bộ có thể gọi thay người dùng, nhưng sự hiện diện của một header `userId` không tự chứng minh quyền đại diện.

Cần xác minh dịch vụ, chủ thể được đại diện, phạm vi action và resource, cùng điều kiện hiệu lực. Audit cần phân biệt tác nhân thực và chủ thể nghiệp vụ.

Không dùng danh tính tài khoản kết nối cơ sở dữ liệu làm owner của mọi đối tượng, cũng không gán owner bằng một trường body để khiến kiểm tra luôn khớp.

### 9.5. Kiểm tra đúng đối tượng cuối cùng được sử dụng

Nếu đường dẫn chứa `PR-A` nhưng body hoặc message trỏ tới `PR-B`, handler không được kiểm tra A rồi ghi B.

Controller nên tạo lệnh từ hợp đồng rõ ràng và phát hiện định danh mâu thuẫn. Repository thực hiện ghi cũng cần dùng đúng phạm vi đã được kiểm tra. Quy tắc này áp dụng cả khi chuyển dữ liệu qua nhiều tầng hoặc ánh xạ giữa mã công khai và khóa nội bộ.

## 10. Phản hồi và audit

Phản hồi cần giúp người có quyền xử lý tình huống, đồng thời tránh tiết lộ đối tượng của người khác.

| Tình huống | Hành vi có thể áp dụng |
|---|---|
| Chưa xác thực | Phản hồi theo cơ chế xác thực |
| Không có quyền với đối tượng | Từ chối hoặc che giấu sự tồn tại theo chính sách |
| Đúng owner nhưng trạng thái không cho phép | Báo điều kiện nghiệp vụ không đạt ở mức người gọi được biết |
| Version cũ | Báo xung đột, tải lại và xác nhận nội dung hiện tại |
| Owner đã chuyển | Không tiếp tục thao tác bằng quan hệ cũ; chỉ trả thông tin được phép |
| Chuyển owner thành công | Phản ánh kết quả chuyển, không hàm ý người nhận được mọi quyền đặc biệt |

Không nên thông báo “đơn này thuộc người B, phòng tài chính, trị giá X” cho người đang bị chặn chỉ để giải thích lỗi. Mã lỗi và thời điểm phản hồi cũng cần được thiết kế nhất quán với chính sách tiết lộ.

Các thao tác nhạy cảm nên có audit đủ để xác định tenant, đối tượng, action, chủ thể thực, chủ thể được đại diện nếu có, version và kết quả.

Với chuyển ownership, cần lưu owner cũ, owner mới, người chuyển, căn cứ và mốc có hiệu lực trong phạm vi dữ liệu được bảo vệ. Giữ lịch sử nguồn gốc và các quyết định liên quan.

Audit thành công cần nhất quán với transaction. Lần thử bị chặn có thể được ghi qua đường quan sát thích hợp sau rollback; không tạo sự kiện báo sửa hoặc chuyển owner thành công cho lệnh thất bại.

Nhiều lần đổi ID, truy cập đối tượng khác tenant hoặc thử lại sau khi mất quyền có thể là tín hiệu cần điều tra. Cần xem cùng ngữ cảnh và lưu lượng hợp lệ thay vì kết luận chỉ từ một lỗi đơn lẻ.

## 11. Kiểm thử các đường vượt quyền ownership

### 11.1. Ma trận người gọi, đối tượng và hành động

| Tình huống | Kết quả cần kiểm chứng |
|---|---|
| A đọc hoặc sửa bản nháp của A trong tenant hợp lệ | Cho phép khi đủ các điều kiện action và nghiệp vụ |
| A đổi ID sang đơn của B cùng tenant | Chặn theo chính sách đối tượng |
| A truy cập đối tượng tenant khác dù cùng một subject có mặt ở nhiều nơi | Không dùng quyền của tenant hiện tại cho phạm vi khác |
| Client giả `ownerSubjectId` khi tạo hoặc sửa | Không thay đổi owner ngoài lệnh có thẩm quyền |
| Có quyền đọc nhưng không có quyền sửa | Không cho phép ghi chỉ vì đã tải được đối tượng |
| Đúng owner nhưng đơn đã được duyệt | Không sửa nội dung trái quy tắc trạng thái |
| Đúng owner nhưng tự duyệt đơn mình lập | Phân tách nhiệm vụ vẫn chặn |
| Quyền hỗ trợ chỉ cho đọc một phần dữ liệu | Không mở rộng thành quyền sửa hoặc xem mọi tài nguyên |
| Parent thuộc A nhưng attachment thuộc B | Không tải được child không thuộc parent đã kiểm tra |
| Path và body dùng hai requestId khác nhau | Không kiểm tra một đối tượng rồi cập nhật đối tượng khác |
| Danh sách có đối tượng của nhiều owner | Phân trang, tổng số và kết quả đều theo phạm vi được phép |
| Batch trộn ID của A và B | Thực hiện đúng hợp đồng toàn bộ hoặc từng phần tử, không ghi trái quyền |
| Owner chuyển từ A sang B | A mất quyền theo chính sách; B nhận đúng quyền được chuyển |
| A là người tạo cũ sau khi chuyển owner | Không tự suy ra còn quyền ghi hiện tại |
| Grant hoặc ủy quyền đã hết hiệu lực | Không tiếp tục cho phép qua nhánh đại diện |
| Cùng cache key tài nguyên nhưng người gọi khác | Không dùng quyết định cho phép của A cho B |
| Job xuất chạy sau thay đổi owner | Áp dụng đúng mốc phân quyền đã công bố |
| Retry lệnh cũ sau khi mất quyền truy cập | Không lộ kết quả nhạy cảm chỉ nhờ idempotency key |

Cần kiểm tra cả những ID có thật và ID không tồn tại theo chính sách phản hồi. Không chỉ kiểm thử với một người dùng hợp lệ và một đối tượng duy nhất.

### 11.2. Kiểm thử cạnh tranh có đồng bộ

Các ca tích hợp có giá trị:

1. **Sửa đối đầu với chuyển owner:** nếu việc chuyển đã có hiệu lực theo giao thức trước lần ghi, lệnh dựa trên owner cũ không được ghi thành công.
2. **Hai đề nghị chuyển đồng thời:** không tạo hai owner hiện tại hoặc hai kết quả được chấp nhận mâu thuẫn.
3. **Sửa đối đầu với gửi duyệt:** không để nội dung tiếp tục thay đổi âm thầm sau khi đã được chốt vào vòng duyệt.
4. **Chuyển owner cùng lúc nhận kết quả replay:** phản hồi phải tuân thủ chính sách truy cập hiện tại và ranh giới nhất quán đã định nghĩa.
5. **Thu hồi tư cách nhóm hoặc tenant:** kiểm chứng đúng bảo đảm mà cơ chế quyền đã công bố, thay vì giả định khóa tài nguyên tự bảo vệ mọi nguồn.
6. **Vô hiệu cache chậm:** owner cũ không được phép vượt quá giới hạn lỗi thời mà hệ thống đã chấp nhận.

Dùng điểm đồng bộ để tạo cuộc đua thực sự. Test chạy hai lệnh tuần tự không chứng minh được khả năng chặn thay đổi giữa kiểm tra và sử dụng.

Kiểm thử khóa và transaction cần cơ sở dữ liệu có đặc tính tương ứng triển khai. Mock repository thường chỉ kiểm tra được nhánh điều kiện, không chứng minh tính nhất quán dưới cạnh tranh.

### 11.3. Kiểm tra sự vắng mặt của thay đổi

Sau một lệnh sửa bị từ chối:

```text
nội dung và tổng tiền không đổi bởi lệnh thất bại
owner, tenant và createdBy không bị sửa
state, rowVersion và contentRevision không bị tăng dở dang
các dòng hàng hoặc tài liệu con không bị thay thế
không có audit báo sửa thành công
không có outbox hoặc tác dụng nghiệp vụ từ lệnh bị chặn
không trả dữ liệu ngoài phạm vi trong nội dung lỗi
```

Với lỗi xảy ra giữa cập nhật root và cập nhật dòng hàng, transaction phải rollback phần thay đổi liên quan. Một HTTP từ chối không đủ nếu dữ liệu thực tế đã bị ghi.

Với chuyển owner, kiểm tra cả dữ liệu phụ, quyền tài liệu, cache và các liên kết cần thay đổi theo mô hình. Không chỉ xác nhận cột owner trên bảng chính có giá trị mới.

### 11.4. Tạo dữ liệu kiểm thử đủ phân biệt các quan hệ

Nên có các trường hợp:

- Người tạo vẫn là owner.
- Người tạo đã chuyển ownership cho người khác.
- Người được giao duyệt không phải owner.
- Hai người cùng tenant nhưng sở hữu các đối tượng khác nhau.
- Một người hoạt động trong nhiều tenant với quyền khác nhau.
- Nhóm sở hữu có thành viên chỉ được đọc và thành viên được quản lý.
- Người gọi thông qua dịch vụ đại diện có scope hẹp.

Nếu mọi dữ liệu test đều có `createdBy == ownerSubjectId == assignedTo`, một lỗi dùng nhầm quan hệ rất dễ vẫn vượt qua bộ kiểm thử.

## 12. Bài tập áp dụng

Thiết kế phân quyền cho đơn đề nghị mua hàng, cho phép chủ sở hữu sửa bản nháp, người được giao duyệt đọc nội dung và một vai trò riêng chuyển ownership trong cùng tenant.

1. Viết bảng action theo từng quan hệ: owner, người tạo, người duyệt, người quản lý nhóm và người hỗ trợ.
2. Xác định nguồn có thẩm quyền cho tenant, subject, owner và membership.
3. Thiết kế DTO sửa bản nháp để không cho cập nhật owner, tenant hoặc trạng thái tùy ý.
4. Viết điều kiện truy vấn cho đọc một đơn, liệt kê đơn và tải attachment.
5. Chọn cơ chế bảo vệ trước việc owner thay đổi giữa lúc đọc và ghi.
6. Mô tả quy trình chuyển owner, quyền người nhận trong thời gian chờ và cách giữ lịch sử người lập.
7. Định nghĩa cách cache, job xuất và replay xử lý thay đổi quyền.
8. Viết một ca tấn công đổi ID tài nguyên con và một ca chuyển owner đồng thời với cập nhật nội dung.

Một thiết kế đúng cần giải thích được vì sao chủ thể này được thực hiện hành động này trên đối tượng này tại mốc kiểm tra đã định nghĩa. Quan hệ sở hữu phải đến từ dữ liệu đáng tin cậy và được áp dụng cùng phạm vi tenant, trạng thái, các quyền khác và cơ chế nhất quán ở mọi đường truy cập.
