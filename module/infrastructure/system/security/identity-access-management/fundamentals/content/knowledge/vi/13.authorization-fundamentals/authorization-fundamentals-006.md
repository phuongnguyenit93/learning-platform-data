# Resource ownership — Quyền sở hữu tài nguyên trong phân quyền

## 1. Resource ownership có ý nghĩa gì trong IAM?

**Resource ownership** là quan hệ giữa một tài nguyên và chủ thể được hệ thống ghi nhận là chủ sở hữu theo mô hình nghiệp vụ. Chủ sở hữu có thể là người dùng, nhóm hoặc tổ chức. Quan hệ này thường được dùng làm đầu vào cho quyết định truy cập.

Ví dụ, một tài liệu cá nhân thuộc người dùng A. Chính sách có thể cho A đọc và sửa tài liệu của mình, trong khi người dùng B không có quyền đó. Trong một hệ thống khác, tài liệu thuộc một nhóm và quyền truy cập phụ thuộc vai trò của người dùng trong nhóm.

Ownership trong bài là khái niệm kỹ thuật phục vụ phân quyền. Nó không tự kết luận về quyền sở hữu pháp lý của dữ liệu, cũng không có nghĩa chủ sở hữu được phép thực hiện mọi thao tác.

Một người có thể sở hữu tài nguyên nhưng không được xóa khi tài nguyên đã bị khóa theo quy trình. Một người khác có thể không sở hữu tài nguyên nhưng được cấp quyền đọc hoặc quản trị trong phạm vi rõ ràng. Chính sách cần diễn đạt các trường hợp đó thay vì chỉ dựa vào một phép so sánh ID ở mọi nơi.

Trong nền tảng IAM, ownership kết nối danh tính đã xác thực với từng đối tượng được bảo vệ. Nó bổ sung phạm vi cho permission, phối hợp với RBAC, ABAC, quan hệ chia sẻ, vòng đời quyền và kiểm toán.

Sau bài học, người học có thể:

- Phân biệt chủ sở hữu, người tạo và người được chia sẻ tài nguyên.
- Mô hình hóa ownership trong hệ thống nhiều tenant.
- Thực thi kiểm tra quyền trên từng đối tượng ở backend.
- Bảo vệ thao tác tạo và chuyển chủ sở hữu.
- Kiểm chứng tác động của chuyển ownership, thu hồi quyền và thay đổi tài nguyên.

## 2. Phân biệt những quan hệ thường gặp

| Quan hệ | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| Chủ sở hữu | Tài nguyên thuộc ai theo mô hình nghiệp vụ? | Tài liệu thuộc nhóm thiết kế |
| Người tạo | Ai đã tạo bản ghi hoặc khởi tạo thao tác? | Bot nhập liệu tạo tài liệu cho nhóm |
| Người phụ trách | Ai chịu trách nhiệm xử lý hoặc chăm sóc tài nguyên? | Nhân viên được giao xử lý một ticket |
| Người được chia sẻ | Ai nhận một quyền cụ thể trên tài nguyên? | Cộng tác viên được đọc tài liệu |
| Quản trị viên | Ai có quyền quản trị trong phạm vi được cấp? | Quản trị viên của tenant A |
| Tác nhân thực thi | Danh tính nào thực sự gọi hoặc chạy thao tác? | Workload xuất báo cáo thay mặt người dùng |

Các quan hệ có thể trùng nhau trong một trường hợp nhưng không nên bị gộp thành một trường duy nhất chỉ vì thuận tiện.

Ví dụ, workload tạo báo cáo tự động không nên mặc định trở thành chủ sở hữu lâu dài của mọi báo cáo. Người tạo ticket cũng không nhất thiết được phép sửa mọi nội dung sau khi ticket đã chuyển sang bộ phận xử lý.

`created_by` thường phục vụ truy vết lịch sử. Nếu ownership được chuyển từ A sang B, việc ghi đè `created_by` thành B sẽ làm mất thông tin ai tạo tài nguyên. Nên giữ các ý nghĩa riêng nếu hệ thống cần cả hai.

## 3. Mô hình dữ liệu và ranh giới tenant

### 3.1. Một mô hình minh họa

```text
resource_id
tenant_id
owner_type
owner_id
created_by
status
version
ownership_changed_at
```

Trong mô hình này:

- `resource_id` định danh tài nguyên.
- `tenant_id` xác định phạm vi tổ chức hoặc khách hàng.
- `owner_type` phân biệt owner là người dùng, nhóm hay tổ chức.
- `owner_id` định danh owner trong loại đã chọn.
- `created_by` lưu tác nhân tạo bản ghi theo thiết kế kiểm toán.
- `status` và `version` hỗ trợ kiểm soát nghiệp vụ cùng thay đổi đồng thời.

Tên trường là lựa chọn minh họa. Một hệ thống có thể dùng bảng quan hệ riêng thay vì cột trực tiếp trên tài nguyên, nhất là khi có nhiều loại quan hệ hoặc nhiều chủ thể cùng quản lý.

### 3.2. Không chỉ so sánh owner ID

Giả sử tenant A và tenant B đều có một người dùng mang số nội bộ 17. So sánh `owner_id == 17` mà bỏ qua phạm vi có thể làm lẫn danh tính hoặc tài nguyên giữa hai tenant.

Cần định nghĩa tính duy nhất của ID và ràng buộc tenant rõ ràng. Ngay cả khi ID người dùng là duy nhất toàn hệ thống, chính sách tenant vẫn có thể là một điều kiện bắt buộc độc lập.

Ngoài ra, `owner_type=USER, owner_id=17` và `owner_type=TEAM, owner_id=17` không phải cùng một chủ sở hữu. Mô hình cần ngăn tham chiếu đến sai loại hoặc một chủ thể không hợp lệ.

### 3.3. Dùng định danh bền vững

Tên hiển thị, email hoặc username có thể thay đổi hoặc được tái sử dụng. Một quan hệ ownership quan trọng nên gắn với định danh nội bộ ổn định và có quy tắc rõ khi danh tính bị xóa hoặc vô hiệu hóa.

Nếu một người nghỉ việc, không nên để việc tạo lại một username giống cũ tự làm người mới nhận ownership của mọi tài nguyên trước đây. Hệ thống cần quy trình chuyển giao hoặc xử lý tài nguyên còn lại.

## 4. Ownership là điều kiện của chính sách, không phải toàn bộ quyền

### 4.1. Kết hợp permission và quan hệ tài nguyên

Một chính sách sửa tài liệu cá nhân có thể yêu cầu:

```text
Cho phép sửa khi đồng thời:
  - Chủ thể và phiên còn hợp lệ.
  - Chủ thể có permission document:update trong phạm vi thích hợp.
  - Tài nguyên thuộc tenant mà chủ thể được phép truy cập.
  - Tài nguyên có owner_type USER và owner_id là chủ thể hiện tại.
  - Trạng thái tài liệu cho phép chỉnh sửa.
```

Đây là chính sách minh họa, không phải quy tắc bắt buộc của mọi ứng dụng. Nó cho thấy permission trả lời phần loại thao tác, còn ownership và tenant xác định phạm vi đối tượng.

Nếu chỉ kiểm tra `document:update`, người dùng có thể tác động mọi tài liệu mà endpoint tải được. Nếu chỉ kiểm tra ownership, chủ sở hữu có thể thực hiện một thao tác mà vai trò hoặc trạng thái của tài nguyên không cho phép.

### 4.2. Chia sẻ và quản trị cần nhánh chính sách rõ ràng

Một tài liệu được chia sẻ cho B với quyền đọc không tự biến B thành owner. Quyền chia sẻ cũng không mặc định bao gồm quyền sửa, xóa, chuyển ownership hoặc chia sẻ tiếp.

Nếu quản trị viên được truy cập tài nguyên của người khác, đó là một quyền quản trị được định nghĩa, với phạm vi và kiểm toán riêng. Không thêm một ngoại lệ `isAdmin` toàn hệ thống trong mọi hàm kiểm tra owner mà không xem xét ranh giới tenant.

Với tài nguyên thuộc nhóm, quyền có thể phụ thuộc quan hệ thành viên và vai trò trong nhóm. Thành viên đã rời nhóm không nên tiếp tục có quyền chỉ vì từng truy cập tài nguyên trước đó.

### 4.3. Khi thiếu dữ liệu để quyết định

Nếu không xác định được owner hoặc quan hệ cần thiết, không suy ra ai cũng được truy cập. Có thể cần từ chối, đánh dấu dữ liệu cần xử lý hoặc áp dụng một nhánh quản trị riêng theo chính sách.

OWASP khuyến nghị deny by default và kiểm tra quyền ở mỗi request. Tham khảo [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

## 5. Ownership và lỗi truy cập đối tượng trực tiếp

### 5.1. Tài nguyên được định danh chưa chắc được phép truy cập

Một endpoint `GET /documents/{documentId}` cần biết người gọi được đọc tài liệu cụ thể đó không. Việc người gọi đã đăng nhập hoặc có quyền mở màn hình tài liệu chưa trả lời được câu hỏi này.

Nếu backend nhận ID rồi tải và trả tài nguyên mà thiếu kiểm tra ở mức đối tượng, có thể xuất hiện IDOR hoặc broken object-level authorization. OWASP mô tả BOLA là lỗi kiểm tra quyền đối với đối tượng được yêu cầu, khác với việc người gọi không được phép sử dụng cả chức năng. Xem [OWASP API1:2023 — Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/).

Ownership là một cách mô hình hóa phạm vi đối tượng, nhưng không phải mọi chính sách đều chỉ có owner. Với tài nguyên chia sẻ, nhóm hoặc tổ chức, cần xét đúng quan hệ thay vì áp một phép so sánh user ID đơn giản cho mọi trường hợp.

### 5.2. UUID và trường ẩn không thay thế kiểm tra quyền

ID khó đoán giảm khả năng dò tìm, nhưng người gọi có thể biết ID qua liên kết, thông báo hoặc một tính năng hợp lệ khác. Backend vẫn cần từ chối nếu không có quyền trên đối tượng đó.

Tương tự, `ownerId` trong một hidden input, query parameter hoặc JSON body vẫn là dữ liệu client có thể thay đổi. Không dùng một giá trị do client gửi làm bằng chứng rằng người gọi sở hữu tài nguyên.

OWASP hướng dẫn tra cứu trong tập tài nguyên chủ thể được phép và kiểm tra quyền trên từng đối tượng; định danh phức tạp chỉ là lớp bổ sung. Tham khảo [OWASP IDOR Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html).

### 5.3. Tài nguyên lồng nhau

Với đường dẫn như:

```text
/projects/{projectId}/documents/{documentId}
```

Cần kiểm tra cả quyền trên tài liệu và quan hệ tài liệu thực sự thuộc dự án được nêu. Chỉ kiểm tra người dùng được truy cập projectId rồi tải documentId độc lập có thể bỏ qua ràng buộc giữa hai đối tượng.

Các file đính kèm, comment, bản xuất và phiên bản cũ của tài liệu cũng cần được đưa vào mô hình. Một endpoint tải file không được bỏ qua quyền chỉ vì file được coi là phần phụ của tài nguyên chính.

## 6. Gán ownership khi tạo tài nguyên

### 6.1. Tạo tài nguyên cá nhân

Trong mô hình tài liệu cá nhân, backend có thể lấy owner từ principal đã xác thực:

```text
principal = requireTrustedPrincipal()
tenant = requireAuthorizedTenant(principal, requestedTenant)
requirePermission(principal, "document:create", tenant)

document.ownerType = USER
document.ownerId = principal.subjectId
document.tenantId = tenant.id
document.createdBy = principal.actorId
```

Đây là pseudocode mô tả trách nhiệm, không phải implementation hoàn chỉnh. Principal và tenant được phép phải được xác định qua nguồn tin cậy, không chỉ đổi tên dữ liệu từ request.

Nếu API không hỗ trợ chọn owner, nên loại trường owner khỏi dữ liệu được phép bind hoặc từ chối nó theo hợp đồng API. Không để client truyền thêm `ownerId`, `tenantId` hoặc trạng thái đặc quyền rồi gắn trực tiếp vào entity.

### 6.2. Tạo thay mặt nhóm hoặc người khác

Một ứng dụng có thể cho phép nhân viên tạo tài liệu cho nhóm hoặc cho người khác. Khi đó owner đích là một phần của yêu cầu cần được kiểm tra, không phải dữ liệu được tin vì có trong form.

Backend cần xác định người gọi có quyền tạo trong phạm vi đó, owner đích hợp lệ, quan hệ tenant phù hợp và thao tác không vượt giới hạn ủy quyền. Tác nhân thực hiện vẫn được ghi riêng để truy vết.

Với workload nhập dữ liệu, cần xác định owner theo quy tắc nghiệp vụ đã phê duyệt. Không tự dùng service account làm owner của mọi tài nguyên chỉ vì nó là danh tính gọi API.

## 7. Truy vấn và thực thi tại backend

### 7.1. Ví dụ Java cho tài liệu cá nhân

Giả sử chính sách của endpoint chỉ cho người dùng đọc tài liệu cá nhân do chính họ sở hữu trong tenant đang được phép sử dụng. Ví dụ tích hợp Spring Security:

```java
@PreAuthorize("hasAuthority('document:read')")
public DocumentView getOwnedDocument(UUID documentId) {
    var principal = principalContext.requireActiveTenantMember();

    var document = documentRepository
            .findByIdAndTenantIdAndOwnerTypeAndOwnerId(
                    documentId,
                    principal.tenantId(),
                    OwnerType.USER,
                    principal.subjectId())
            .orElseThrow(ResourceNotAccessibleException::new);

    return DocumentView.from(document);
}
```

Các dependency và kiểu dữ liệu do ứng dụng cung cấp. Ví dụ giả định method security đã được bật, method được gọi qua cơ chế bảo vệ của Spring và authority đã được ánh xạ từ nguồn tin cậy. Tham khảo [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html).

`requireActiveTenantMember()` cần kiểm tra thành viên tenant hợp lệ. Phương thức repository thể hiện truy vấn bị giới hạn bởi tài nguyên, tenant, loại owner và chủ thể hiện tại. `DocumentView` cần chỉ chứa dữ liệu endpoint được phép trả.

Ví dụ không bao phủ tài liệu của nhóm hoặc tài liệu được chia sẻ. Nếu sản phẩm hỗ trợ chúng, cần mở rộng chính sách và truy vấn có chủ đích thay vì bỏ điều kiện owner để xử lý nhanh.

### 7.2. Cập nhật có điều kiện

Một câu lệnh cập nhật cho mô hình cá nhân có thể ràng buộc ownership ngay tại thao tác ghi:

```sql
UPDATE documents
SET title = :new_title,
    version = version + 1
WHERE id = :document_id
  AND tenant_id = :authorized_tenant_id
  AND owner_type = 'USER'
  AND owner_id = :authenticated_subject_id
  AND version = :expected_version;
```

Các tham số principal và tenant phải đến từ context đã được xác minh. Câu lệnh là ví dụ giới hạn đối tượng và kiểm soát cạnh tranh; permission chức năng, trạng thái tài liệu cùng các điều kiện khác vẫn cần được thực thi.

Không có hàng nào được cập nhật có thể do nhiều nguyên nhân: tài nguyên không có trong phạm vi, ownership đã thay đổi hoặc version không còn khớp. Cách trả lỗi ra ngoài phải theo hợp đồng API, đồng thời tránh tiết lộ sự tồn tại của tài nguyên không được phép biết.

### 7.3. Mọi đường truy cập đều cần cùng hiệu lực

Không chỉ kiểm tra ở màn hình chi tiết. Danh sách, tìm kiếm, count, export, batch update, tải file và API quản trị cần cùng mô hình phạm vi thích hợp.

Lọc những tài nguyên không thuộc quyền sau khi đã phân trang hoặc tính tổng có thể làm kết quả sai hoặc tiết lộ metadata. Nên đưa điều kiện vào quá trình xác định tập dữ liệu được phép trước khi tính những kết quả đó.

## 8. Chuyển ownership là thao tác đặc quyền

### 8.1. Không gộp vào cập nhật thông thường

Cho phép sửa tiêu đề không tự cho phép đổi `owner_id`. Nếu cùng một API bind toàn bộ entity, người dùng có thể vô tình hoặc cố ý thay các quan hệ phân quyền.

Nên thiết kế thao tác chuyển ownership riêng khi nghiệp vụ cần, với quyền và điều kiện rõ ràng. Ví dụ:

```text
POST /documents/{documentId}/ownership-transfer
```

Đây chỉ là tên endpoint minh họa. Backend phải xác minh người thực hiện, quyền chuyển, phạm vi tài nguyên và owner đích trước khi thay đổi.

### 8.2. Các điều kiện cần xem xét

Một quy trình chuyển trong cùng tenant có thể gồm:

1. Xác định người gọi và tenant được phép từ context đáng tin.
2. Kiểm tra tài nguyên hiện hành và quyền chuyển ownership.
3. Kiểm tra owner đích tồn tại, thuộc loại hợp lệ và nằm trong phạm vi cho phép.
4. Kiểm tra trạng thái tài nguyên có cho phép chuyển hay cần phê duyệt bổ sung.
5. Cập nhật ownership cùng version theo cách tránh xung đột.
6. Xử lý các quyền dẫn xuất, cache và tác vụ liên quan.
7. Ghi lại owner cũ, owner mới, actor, lý do và kết quả; thông báo theo chính sách.

Chuyển sang tenant khác không nên được coi là đổi một trường đơn giản. Nó có thể kéo theo dữ liệu liên quan, chính sách chia sẻ, cách lưu trữ và trách nhiệm quản trị. Cần một quy trình chuyển phạm vi riêng nếu được hỗ trợ.

### 8.3. Quyền cũ có mất hết không?

Nếu A mất quyền sửa vì không còn là owner, đó là quyền dẫn xuất từ ownership. Nhưng A có thể vẫn có quyền đọc qua một grant chia sẻ hoặc role khác. Ngược lại, một grant được tạo vì A là owner có thể cần bị thu hồi khi ownership đổi, nếu chính sách yêu cầu.

Hệ thống phải định nghĩa hành vi với từng nguồn quyền. Không báo “A không còn truy cập được” chỉ vì `owner_id` đã đổi mà chưa xét các grant còn lại.

Tương tự, B trở thành owner không mặc định được mọi quyền. Tài nguyên có thể đang bị khóa hoặc một số thao tác vẫn yêu cầu permission riêng và xác thực lại.

## 9. Quan hệ kế thừa và thay đổi đồng thời

### 9.1. Tài nguyên con và quyền kế thừa

Nếu tài liệu kế thừa quyền từ thư mục, di chuyển tài liệu sang thư mục khác có thể thay đổi người được truy cập. Nếu tài nguyên có owner riêng đồng thời có quyền từ nhóm cha, cần định nghĩa cách kết hợp và ưu tiên chính sách.

Ví dụ, chuyển một file sang thư mục chia sẻ không nên âm thầm làm lộ dữ liệu nếu sản phẩm yêu cầu xác nhận thay đổi phạm vi. Ngược lại, nếu đó là hành vi được thiết kế, giao diện và backend cần thể hiện đúng tác động.

Không dùng vị trí đường dẫn hoặc prefix của file như bằng chứng quyền duy nhất nếu người gọi có thể tác động vào đường dẫn đó. Cần kiểm tra metadata và quan hệ đáng tin cậy theo kiến trúc lưu trữ.

### 9.2. Quyết định cũ có thể hết hiệu lực

Giả sử một request xác nhận A là owner. Trước khi request ghi dữ liệu, một giao dịch khác chuyển tài nguyên sang B. Nếu cập nhật tiếp tục chỉ dựa vào kết quả đã đọc, A có thể thay đổi tài nguyên sau khi mất ownership.

Cần xác định những điều kiện nào phải được kiểm tra tại ranh giới ghi. Có thể dùng khóa, version hoặc cập nhật có điều kiện tùy kiến trúc. Kiểm tra version tài nguyên giúp xử lý thay đổi trên tài nguyên nhưng không tự kiểm tra một grant hoặc membership vừa bị thu hồi ở nơi khác.

### 9.3. Cache và dữ liệu quyền dẫn xuất

Một cache quyết định chỉ theo `resourceId` có thể trả kết quả của A cho B. Một cache chỉ theo user và resource nhưng không xét tenant, action hoặc thay đổi chính sách cũng có thể sai.

Thiết kế cache cần phản ánh các chiều quyết định và có cơ chế hết hiệu lực khi ownership, membership hoặc grant liên quan thay đổi. TTL là một lựa chọn có giới hạn độ trễ, không phải bằng chứng quyền cũ bị thu hồi ngay.

Nếu resource server dùng token hoặc snapshot chứa dữ liệu quyền cũ, cần hiểu khi nào nó nhận biết chuyển ownership. Việc cập nhật cơ sở dữ liệu không tự sửa mọi snapshot đang được dùng.

## 10. Tác vụ nền, liên kết tải và vòng đời danh tính

### 10.1. Tác vụ chạy sau

Một job export được tạo khi A là owner có thể chạy sau khi tài nguyên đã chuyển cho B. Chính sách cần xác định job thực thi theo bằng chứng ủy quyền nào, có kiểm tra lại không và ai được tải kết quả.

Không tự lấy quyền rộng của worker để xuất mọi tài nguyên theo ID client gửi. Danh tính thực thi của workload và quyền của người yêu cầu cần được phân biệt.

### 10.2. Liên kết tải được cấp trước

Một hệ thống có thể cấp liên kết tải có thời hạn dựa trên quyền tại thời điểm cấp. Nếu ownership thay đổi, liên kết đã cấp có còn dùng được hay không phụ thuộc cơ chế thực thi của hệ thống lưu trữ và thiết kế thu hồi.

Không khẳng định quyền tải đã mất ngay chỉ vì owner trong cơ sở dữ liệu đã đổi. Cần xác định giới hạn thời gian, cơ chế thu hồi hoặc lớp kiểm tra bổ sung nếu yêu cầu bảo mật đòi hỏi hiệu lực sớm hơn.

### 10.3. Chủ thể bị vô hiệu hóa hoặc rời tổ chức

Tài nguyên có thể vẫn cần tồn tại khi owner nghỉ việc. Quy trình offboarding cần xác định tài nguyên nào chuyển cho nhóm, tài nguyên nào được lưu trữ và ai được phê duyệt việc chuyển giao.

Vô hiệu hóa đăng nhập không tự sửa mọi quan hệ ownership. Tuy nhiên, không nên giữ account của người cũ hoạt động chỉ để tiếp tục quản lý tài nguyên. Cần tách vòng đời tài nguyên khỏi khả năng xác thực của cá nhân.

Nếu không còn owner hợp lệ, không chuyển tài nguyên thành công khai để tránh lỗi. Có thể đưa vào trạng thái cần xử lý bởi một vai trò được cấp quyền, với dấu vết và phạm vi rõ ràng.

## 11. Kiểm toán và kiểm chứng

### 11.1. Theo dõi thay đổi quan hệ

Sự kiện chuyển ownership minh họa:

```text
event_type: RESOURCE_OWNERSHIP_TRANSFERRED
actor_id: internal-operator-id
resource_type: DOCUMENT
resource_reference: document-204
tenant_id: tenant-a
previous_owner_type: USER
previous_owner_id: subject-a
new_owner_type: TEAM
new_owner_id: team-b
reason_code: APPROVED_HANDOVER
policy_version: document-ownership-v2
result: SUCCESS
correlation_id: opaque-request-reference
```

Metadata phục vụ giải thích ai thay đổi quan hệ nào. Nó không cần chứa toàn bộ nội dung tài liệu, cookie hoặc token. Quyền đọc và thời hạn lưu audit event cũng cần được quản lý.

Ngoài chuyển owner, có thể cần ghi các quyết định từ chối quan trọng, thao tác quản trị và thay đổi quan hệ chia sẻ. Quyết định cho phép và kết quả ghi dữ liệu là hai trạng thái khác nhau, cần được phân biệt khi điều tra.

### 11.2. Ma trận tình huống

Bảng dưới đây là tiêu chí kiểm chứng triển khai, không phải báo cáo chạy thử một ứng dụng:

| Tình huống | Điều kiện cần xác minh |
| --- | --- |
| A truy cập tài nguyên của A trong phạm vi hợp lệ | Được phép theo action và các điều kiện chính sách |
| B có cùng role với A nhưng không có quan hệ với tài nguyên | Không nhận quyền chỉ vì role giống nhau |
| Tài nguyên thuộc tenant khác | Không vượt ranh giới bằng cách thay ID |
| Client gửi ownerId tùy ý khi tạo tài liệu cá nhân | Backend không coi đó là bằng chứng ownership |
| Client thêm ownerId vào payload sửa tiêu đề | Không chuyển ownership ngoài luồng được phép |
| ID là UUID hoặc liên kết khó đoán | Vẫn kiểm tra quyền trên đối tượng |
| DocumentId không thuộc projectId trong URL | Không bỏ qua quan hệ cha-con |
| B chỉ được chia sẻ quyền đọc | Không tự có quyền sửa, xóa hoặc chuyển owner |
| Owner muốn sửa tài nguyên đang khóa | Thực thi ràng buộc trạng thái, không mặc định owner được mọi quyền |
| Chuyển owner khi có request cũ đang ghi | Không cho quyết định cũ vượt ranh giới nhất quán đã thiết kế |
| Chuyển owner khi A còn grant chia sẻ | Kết quả truy cập phản ánh đúng nguồn quyền còn lại |
| Danh sách, count, file đính kèm và export | Cùng bảo vệ phạm vi thích hợp |
| Membership của nhóm bị thu hồi | Quyền dẫn xuất thay đổi theo cơ chế được thiết kế |
| Cache còn kết quả allow cũ | Không vượt giới hạn hiệu lực quyền đã cam kết |
| Job hoặc liên kết tải tồn tại trước chuyển giao | Hành vi khớp chính sách ủy quyền và thu hồi |
| Owner bị vô hiệu hóa hoặc xóa | Tài nguyên được xử lý theo quy trình, không tự công khai |

Phép kiểm chứng nên dùng các tài khoản thử nghiệm có cùng quyền chức năng nhưng khác owner, tenant và quan hệ chia sẻ. Điều này giúp phát hiện trường hợp kiểm tra endpoint đúng nhưng kiểm tra đối tượng còn thiếu.

## 12. Bài tập thiết kế

Một hệ thống tài liệu có tài liệu cá nhân, tài liệu của nhóm và liên kết chia sẻ chỉ đọc. API sửa tài liệu hiện nhận toàn bộ entity, gồm `tenantId`, `ownerId` và `title`. Một job xuất tài liệu được tạo trước khi nhân viên nghỉ việc; trong quy trình bàn giao, tài liệu được chuyển sang nhóm mới.

Hãy thiết kế lại:

1. Dữ liệu nào mô tả owner, người tạo và tác nhân thực hiện?
2. Những trường nào client được sửa qua API cập nhật thông thường?
3. Backend kiểm tra tenant, ownership, quyền chia sẻ và trạng thái tài nguyên ở đâu?
4. Chuyển ownership cần quyền và điều kiện gì, cùng cách xử lý request đồng thời?
5. Các grant cũ, cache, job export và liên kết tải có hiệu lực thế nào sau chuyển giao?
6. Người rời tổ chức bị vô hiệu hóa ra sao mà không làm mất khả năng quản lý tài nguyên?
7. Dữ liệu kiểm toán và tình huống thử nào chứng minh các quan hệ được thực thi đúng?

Một mô hình ownership có ích phải giữ được ý nghĩa quan hệ trong suốt vòng đời tài nguyên. Quyền truy cập cuối cùng cần phản ánh đúng chủ thể, hành động, tài nguyên và trạng thái hiện hành, kể cả khi tài nguyên được chia sẻ, chuyển giao hoặc sử dụng qua tác vụ nền.
