# Object-level authorization

## 1. Object-level authorization bảo vệ điều gì?

Object-level authorization là việc xác định một chủ thể có được thực hiện một hành động cụ thể trên một đối tượng cụ thể hay không.

Trong API quản lý tài liệu:

```http
GET /api/documents/8b183981-38d8-44cf-a19e-2a8d57a74d35
```

xác thực thành công chỉ cho biết ai đang gọi. Quyền gọi nhóm API tài liệu cũng chưa chứng minh người đó được đọc tài liệu mang ID này.

Câu hỏi cần trả lời là:

> Người dùng đang có phiên hợp lệ có được đọc đúng tài liệu này, trong tenant này, với quan hệ và trạng thái hiện tại hay không?

Nếu hệ thống chỉ kiểm tra đăng nhập rồi truy xuất bản ghi bằng ID, người dùng có thể truy cập dữ liệu ngoài phạm vi được phép bằng cách thay ID trong request. Nhóm lỗi thiếu hoặc sai kiểm tra ở mức đối tượng thường được gọi là Broken Object Level Authorization, viết tắt BOLA. Thuật ngữ IDOR thường dùng cho những trường hợp tham chiếu đối tượng bị sử dụng trực tiếp mà không có kiểm tra quyền phù hợp.

Trong thiết kế yêu cầu bảo mật, mục tiêu không phải chỉ thêm một annotation hoặc middleware. Cần biến quan hệ sở hữu, phạm vi tenant, quyền được chia sẻ và trạng thái nghiệp vụ thành chính sách thực thi được, có tiêu chí chấp nhận rõ ràng.

### 1.1. Đối tượng không nhất thiết là một hàng cơ sở dữ liệu

Đối tượng được bảo vệ có thể là:

- Tài liệu, hóa đơn, đơn hàng hoặc hồ sơ cá nhân.
- Tệp đính kèm và phiên bản của một tài liệu.
- Phiên xử lý, tác vụ export hoặc kết quả báo cáo.
- Một collection tài nguyên.
- Một bản ghi lồng dưới tài nguyên cha.
- Một tài nguyên được tham chiếu trong message hoặc job bất đồng bộ.

Một API trả về metadata, số lượng kết quả hoặc trạng thái tác vụ vẫn có thể tiết lộ thông tin đối tượng. Không giới hạn kiểm soát vào endpoint tải toàn bộ nội dung.

### 1.2. ID xuất hiện ở nhiều vị trí

Tham chiếu đối tượng có thể nằm trong:

| Vị trí | Ví dụ |
|---|---|
| Path | /documents/{documentId} |
| Query | ?invoiceId=... |
| Request body | documentIds, ownerId, parentId |
| Header theo hợp đồng API | Một khóa tham chiếu tài nguyên |
| Biến của truy vấn | ID trong variables của GraphQL |
| Nội dung message | reportId trong yêu cầu xử lý nền |
| Token hoặc liên kết được chia sẻ | Tham chiếu tới file hoặc tác vụ |

Không được chỉ bảo vệ những route có mẫu path quen thuộc rồi bỏ qua ID trong body hoặc các API phụ trợ.

## 2. Phân biệt các lớp kiểm soát

### 2.1. Xác thực, quyền chức năng và quyền đối tượng

Ba câu hỏi liên quan nhưng không thay thế nhau:

| Lớp kiểm soát | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication | Chủ thể là ai? | Token hợp lệ thuộc người dùng U |
| Function-level authorization | Chủ thể được gọi chức năng nào? | U được sử dụng chức năng đọc tài liệu |
| Object-level authorization | Chủ thể được thao tác đối tượng nào? | U được đọc tài liệu D cụ thể |

Một scope như documents:read có thể là điều kiện cần để sử dụng API. Nó không tự nói U được đọc mọi tài liệu trong hệ thống.

Tương tự, vai trò editor không tự xác định phạm vi dữ liệu. Có thể đó là editor của một dự án, một workspace hoặc một tenant, chứ không phải editor toàn cục.

### 2.2. Quyền đối tượng và quyền thuộc tính

Nếu người dùng được sửa tài liệu, chưa chắc họ được sửa mọi thuộc tính của tài liệu đó.

Ví dụ, được sửa title không đồng nghĩa được sửa:

- tenantId.
- ownerId.
- classification.
- approvalState.
- accessPolicy.
- createdBy.

Object-level authorization quyết định khả năng thao tác tài nguyên. Property-level authorization quyết định những trường nào được đọc hoặc thay đổi trong thao tác đó.

Hai kiểm soát cần phối hợp. Một API kiểm tra đúng chủ sở hữu nhưng bind toàn bộ JSON vào entity vẫn có thể cho phép chuyển quyền sở hữu hoặc thay đổi tenant ngoài hợp đồng.

### 2.3. Validation không phải authorization

UUID hợp lệ, ID đúng định dạng hoặc đối tượng tồn tại là điều kiện dữ liệu. Chúng không chứng minh chủ thể có quyền.

Đổi ID tăng dần thành UUID làm giảm khả năng đoán một số tham chiếu. Nó không giải quyết việc một ID đã lộ qua log, liên kết, danh sách hoặc một người dùng khác có thể được dùng trái phép.

Yêu cầu phải coi ID là tham chiếu, không phải bằng chứng quyền, trừ trường hợp hệ thống chủ ý thiết kế một capability token với hợp đồng bảo mật riêng.

## 3. Mô hình hóa quyết định chủ thể–hành động–đối tượng

Một quyết định có thể được diễn đạt:

```text
allow(subject, action, object, context)
```

Trong đó:

| Thành phần | Dữ liệu thường cần |
|---|---|
| Subject | Định danh người dùng hoặc service, quan hệ thành viên, quyền đã cấp |
| Action | Đọc, sửa nội dung, xóa, chia sẻ, tải xuống, duyệt |
| Object | ID, tenant, chủ sở hữu, dự án, trạng thái, mức phân loại |
| Context | Tenant đang hoạt động, thời điểm, mục đích, trạng thái phiên |

Không phải hệ thống nào cũng cần mọi thuộc tính trên. Cần chọn những yếu tố thực sự tham gia chính sách, xác định nguồn dữ liệu và độ mới của chúng.

### 3.1. Ví dụ chính sách đơn giản

Giả sử sản phẩm có tài liệu thuộc tenant:

- Thành viên đang hoạt động được đọc tài liệu của mình.
- Người có quyền đọc toàn bộ tài liệu trong tenant được đọc tài liệu của tenant đó.
- Chỉ chủ sở hữu hoặc người có quyền sửa toàn bộ bản nháp được sửa nội dung bản nháp.
- Không vai trò nào trong tenant A được dùng quyền đó cho tài liệu tenant B.
- Tài liệu đã duyệt không được sửa qua hành động sửa bản nháp.

Có thể viết:

```text
Cho phép đọc khi:
    chủ thể có scope đọc tài liệu
    AND là thành viên đang hoạt động của tenant đang chọn
    AND tài liệu thuộc tenant đang chọn
    AND (là chủ sở hữu OR có quyền đọc toàn bộ tài liệu trong tenant)

Cho phép sửa bản nháp khi:
    chủ thể có scope ghi tài liệu
    AND là thành viên đang hoạt động của tenant đang chọn
    AND tài liệu thuộc tenant đang chọn
    AND tài liệu đang ở trạng thái DRAFT
    AND (là chủ sở hữu OR có quyền sửa mọi bản nháp trong tenant)
```

Dấu ngoặc có ý nghĩa bảo mật. Nếu vô tình viết điều kiện theo dạng:

```text
cùng tenant AND là chủ sở hữu OR có vai trò editor
```

mà không ràng buộc editor vào tenant, nhánh cuối có thể mở rộng quyền ra ngoài phạm vi dự kiến.

### 3.2. Quyền theo quan hệ và thuộc tính

Những chính sách phổ biến gồm:

- Ownership: tài nguyên thuộc chủ thể.
- Membership: chủ thể thuộc nhóm hoặc dự án của tài nguyên.
- Sharing: tài nguyên có grant cụ thể cho chủ thể.
- Delegation: chủ thể được ủy quyền trong thời hạn và phạm vi xác định.
- Attribute-based rules: kết hợp tenant, trạng thái và thuộc tính tài nguyên.

Không nên chọn một mô hình chỉ vì tên gọi quen thuộc. Cần mô hình hóa quan hệ nghiệp vụ đủ để giải thích tại sao một thao tác được phép.

Đặc biệt, “admin” phải có phạm vi. Tenant admin, project admin và platform operator là những quyền khác nhau. Không để một chuỗi role chung chung trở thành ngoại lệ bỏ qua mọi ranh giới dữ liệu.

### 3.3. Mặc định từ chối

Khi không có quy tắc cho phép phù hợp, quyết định phải là từ chối.

Ví dụ:

- Một action mới được thêm vào enum không tự được phép cho mọi chủ sở hữu.
- Không tìm thấy membership không được hiểu là thành viên mặc định.
- Không tải được grant không được suy ra rằng tài nguyên là công khai.
- Dữ liệu trạng thái không nhận diện được không rơi vào nhánh cho phép.

Điều này cần được phản ánh trong cấu trúc code và cách xử lý lỗi phụ thuộc.

## 4. Ranh giới tenant phải có nguồn tin cậy

### 4.1. Tenant ID từ client là một yêu cầu lựa chọn

Client có thể gửi tenantId trong path hoặc header để chọn workspace đang thao tác. Giá trị đó chỉ thể hiện mong muốn lựa chọn tenant, không chứng minh người dùng là thành viên.

Hệ thống cần:

1. Xác thực chủ thể.
2. Xác minh chủ thể có quan hệ được phép với tenant được chọn.
3. Tạo ngữ cảnh tenant đáng tin cho các bước xử lý.
4. Chỉ truy xuất tài nguyên trong phạm vi đó.
5. Áp dụng tiếp các điều kiện theo đối tượng và hành động.

Nếu tenant được lấy từ token, vẫn cần xác định token được cấp bởi ai, audience nào được chấp nhận và quyền có thể trở nên lỗi thời ra sao. Một claim không được kiểm chứng không thể là căn cứ phân quyền.

### 4.2. Không tin các thuộc tính quyền trong body

Client có thể gửi:

```json
{
  "documentId": "6b93d41c-2eaa-4d84-8acd-0d9552072b32",
  "tenantId": "tenant-b",
  "ownerId": "current-user",
  "isAdmin": true
}
```

Hệ thống không được dùng tenantId, ownerId hoặc isAdmin do client tự khai như sự thật về đối tượng đang tồn tại.

Các thuộc tính phục vụ quyết định phải đến từ nguồn có thẩm quyền: ngữ cảnh xác thực, dữ liệu membership và bản ghi tài nguyên. Nếu API cho phép yêu cầu chuyển chủ sở hữu, đó phải là hành động riêng được kiểm soát, không phải cập nhật trường tự do.

### 4.3. Ranh giới tenant cần theo suốt luồng

Một lớp service kiểm tra tenant nhưng repository khác lại tải file bằng ID toàn cục có thể phá vỡ kiểm soát.

Ranh giới phải tồn tại cả khi:

- Tải tài liệu chính và các attachment.
- Tìm kiếm, đếm kết quả hoặc export.
- Chạy job nền.
- Sử dụng cache.
- Gửi sự kiện tới dịch vụ khác.
- Truy xuất object storage bằng khóa nội bộ.

Không nhất thiết truyền tenantId qua mọi hàm như một string tùy ý. Có thể dùng context hoặc kiểu dữ liệu đã xác minh, nhưng cần bảo đảm nguồn và phạm vi không bị đánh mất.

## 5. Đặt điểm thực thi ở đâu?

### 5.1. Gateway không biết đủ mọi thuộc tính đối tượng

Gateway có thể xác thực token, giới hạn API được gọi và áp dụng một số chính sách tổng quát. Nhưng nó thường không có trạng thái hiện tại của từng tài liệu, membership dự án hoặc grant chia sẻ.

Vì vậy, kiểm tra scope ở gateway không thay thế kiểm tra quyền tại service sở hữu tài nguyên.

Ngược lại, kiểm tra ở service cũng không làm xác thực và kiểm soát đầu vào tại ranh giới HTTP trở nên không cần thiết. Mỗi lớp cần có trách nhiệm được định nghĩa.

### 5.2. Truy vấn theo phạm vi được phép

Cách tải dữ liệu có thể kết hợp ranh giới tenant:

```sql
SELECT id, tenant_id, owner_id, status, title
FROM document
WHERE tenant_id = :trusted_tenant_id
  AND id = :document_id;
```

tenant_id trong điều kiện phải lấy từ context đã xác minh, không lấy nguyên từ body.

Truy vấn này giới hạn cross-tenant, nhưng chưa đủ cho chính sách “chỉ chủ sở hữu hoặc có quyền đọc toàn bộ”. Cần kiểm tra tiếp các điều kiện tương ứng, hoặc biểu diễn toàn bộ phạm vi được phép ngay trong truy vấn theo thiết kế.

Ví dụ cho chính sách chủ sở hữu đơn giản:

```sql
SELECT id, title
FROM document
WHERE tenant_id = :trusted_tenant_id
  AND owner_id = :authenticated_user_id
  AND id = :document_id;
```

Mỗi ví dụ phản ánh một chính sách khác nhau. Không tự thêm owner_id vào mọi truy vấn nếu sản phẩm cho phép chia sẻ hoặc quyền theo dự án; làm vậy có thể phá chức năng hợp lệ.

### 5.3. Repository có điều kiện và policy có tên rõ ràng

Hai cách thường phối hợp:

- Repository giới hạn tenant và một phần phạm vi truy cập.
- Policy kiểm tra hành động cụ thể trên dữ liệu đã tải.

Lợi ích là giảm khả năng lấy nhầm tài nguyên toàn cục, đồng thời giữ chính sách nghiệp vụ dễ đọc.

Một hàm findById dùng chung có thể bị gọi nhầm từ một đường mới. Tên như findInTenant hoặc findVisibleToSubject giúp thể hiện hợp đồng, nhưng tên hàm không tự bảo đảm câu truy vấn đúng; implementation vẫn phải thực thi điều kiện đã công bố.

### 5.4. Không kiểm tra ở giao diện làm căn cứ cuối

Ẩn nút xóa giúp giao diện phù hợp với quyền, nhưng client có thể tạo request trực tiếp. API phải kiểm tra độc lập trên server cho mỗi thao tác.

Một danh sách đã lọc không chứng minh endpoint chi tiết an toàn. Người dùng có thể biết ID từ một nguồn khác.

## 6. Ví dụ Java: policy rõ chủ thể, hành động và phạm vi

Ví dụ dưới đây minh họa một policy thuần, dùng record trên Java 17 trở lên. Membership và Document phải được tải từ nguồn có thẩm quyền; request không được tự xây các đối tượng này từ thuộc tính quyền do client gửi.

```java
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

public final class DocumentPolicy {
    public enum Action {
        READ,
        EDIT_DRAFT
    }

    public enum Status {
        DRAFT,
        APPROVED,
        ARCHIVED
    }

    public record Subject(
            UUID userId,
            UUID activeTenantId,
            Set<String> scopes
    ) {
        public Subject {
            Objects.requireNonNull(userId);
            Objects.requireNonNull(activeTenantId);
            scopes = Set.copyOf(scopes);
        }
    }

    public record Membership(
            UUID userId,
            UUID tenantId,
            boolean active,
            boolean canReadAllDocuments,
            boolean canEditAllDrafts
    ) {
    }

    public record Document(
            UUID id,
            UUID tenantId,
            UUID ownerId,
            Status status
    ) {
    }

    private DocumentPolicy() {
    }

    public static boolean allows(
            Subject subject,
            Membership membership,
            Action action,
            Document document
    ) {
        if (subject == null || membership == null
                || action == null || document == null) {
            return false;
        }

        if (membership.userId() == null
                || membership.tenantId() == null
                || document.id() == null
                || document.tenantId() == null
                || document.ownerId() == null
                || document.status() == null) {
            return false;
        }

        boolean validMembership =
                membership.active()
                && subject.userId().equals(membership.userId())
                && subject.activeTenantId().equals(membership.tenantId());

        boolean sameTenant =
                subject.activeTenantId().equals(document.tenantId());

        if (!validMembership || !sameTenant) {
            return false;
        }

        boolean owner = subject.userId().equals(document.ownerId());

        return switch (action) {
            case READ ->
                    subject.scopes().contains("documents:read")
                    && (owner || membership.canReadAllDocuments());

            case EDIT_DRAFT ->
                    subject.scopes().contains("documents:write")
                    && document.status() == Status.DRAFT
                    && (owner || membership.canEditAllDrafts());
        };
    }
}
```

Điểm cần chú ý:

- Scope không thay thế điều kiện cùng tenant và quan hệ với đối tượng.
- Membership phải khớp cả user và tenant của context.
- Quyền đọc toàn bộ không tự suy ra quyền sửa toàn bộ.
- Quyền sửa còn phụ thuộc trạng thái DRAFT.
- Không có nhánh cho phép chung chỉ vì người gọi có một role bất kỳ.
- Thiếu thông tin cần thiết dẫn đến từ chối.

Policy này chỉ là ví dụ cho các quy tắc đã nêu. Nó chưa mô hình hóa sharing, delegation, phân loại tài liệu hoặc quyền platform operator. Nếu sản phẩm cần những khả năng đó, cần thêm quy tắc có phạm vi rõ ràng thay vì mở một nhánh bypass chung.

### 6.1. Luồng service minh họa

```text
readDocument(authenticatedContext, requestedDocumentId):
    subject = lấy chủ thể và tenant đã xác minh từ context

    membership = đọc quan hệ thành viên hiện hành của subject
    document = repository.findInTenant(
        subject.activeTenantId,
        requestedDocumentId
    )

    nếu không có document:
        trả lỗi tài nguyên không khả dụng theo hợp đồng

    nếu policy không cho READ:
        trả lỗi tài nguyên không khả dụng theo chính sách che tồn tại

    trả DTO chỉ chứa các trường được phép đọc
```

DTO là cần thiết vì một đối tượng được phép đọc có thể chứa thuộc tính chỉ dành cho một nhóm khác. Policy đối tượng và chọn trường response phải nhất quán.

### 6.2. Không để caller bỏ qua policy

Nếu controller A dùng service có policy nhưng controller B gọi repository trực tiếp, ranh giới bị phân tán.

Thiết kế nên xác định:

- Điểm vào nào bắt buộc qua service có kiểm soát.
- Những tác vụ nội bộ nào có quyền khác và tại sao.
- Cách background job hoặc message consumer lấy context.
- Cách tránh một helper tải tài nguyên toàn cục được dùng nhầm cho request người dùng.

Một annotation tổng quát có thể hỗ trợ thực thi, nhưng cần biết nó có thực sự đánh giá đối tượng và hành động hay chỉ kiểm tra role.

## 7. Chống sai lệch giữa kiểm tra và cập nhật

### 7.1. TOCTOU ở quyền và trạng thái

TOCTOU là khoảng cách giữa thời điểm kiểm tra và thời điểm sử dụng. Ví dụ:

1. Service tải tài liệu đang ở trạng thái DRAFT.
2. Service xác nhận người dùng được sửa.
3. Một request khác duyệt tài liệu.
4. Request đầu tiên ghi nội dung dù trạng thái đã thay đổi.

Tương tự, quyền sở hữu hoặc grant có thể bị thu hồi giữa hai bước.

Yêu cầu cần xác định những điều kiện nào phải vẫn đúng tại thời điểm commit và cơ chế bảo đảm phù hợp.

### 7.2. Một số cơ chế thực thi

Tùy hệ thống, có thể dùng:

- Transaction với khóa phù hợp trên đối tượng.
- Optimistic locking bằng version.
- Cập nhật có điều kiện trong câu lệnh.
- Kiểm tra lại các thuộc tính liên quan tại ranh giới commit.
- Mô hình nhất quán quyền và trạng thái có giới hạn độ trễ được công bố.

Ví dụ cập nhật chỉ cho chủ sở hữu của bản nháp:

```sql
UPDATE document
SET title = :new_title,
    version = version + 1
WHERE tenant_id = :trusted_tenant_id
  AND id = :document_id
  AND owner_id = :authenticated_user_id
  AND status = 'DRAFT'
  AND version = :expected_version;
```

Nếu số hàng cập nhật bằng 0, service không được coi thao tác là thành công. Nó phải xử lý theo hợp đồng lỗi phù hợp.

Câu lệnh này chưa kiểm tra membership hiện hành và chưa hỗ trợ editor theo tenant. Đây là minh họa cho một chính sách hẹp, không phải truy vấn dùng nguyên vẹn cho mọi hệ thống.

Khóa một hàng document cũng không tự khóa grant hoặc membership nằm ở nơi khác. Độ nhất quán quyền phải được thiết kế cho tất cả dữ liệu tham gia quyết định, không chỉ bản ghi chính.

### 7.3. Tác dụng phụ cũng phải sau kiểm soát

Không được gửi email, tạo liên kết tải xuống, phát sự kiện thành công hoặc ghi dữ liệu bên ngoài trước khi quyền được xác nhận.

Với thao tác nhiều bước, cần xác định ranh giới transaction và cách chỉ phát tác dụng phụ sau khi thay đổi hợp lệ được commit. Một response bị từ chối nhưng đã tạo file export vẫn là vi phạm yêu cầu.

## 8. Collection, bulk và tài nguyên lồng nhau

### 8.1. API danh sách phải trả phạm vi được phép

Đối với:

```http
GET /api/documents
```

không nên tải mọi tài liệu rồi lọc sau khi phân trang. Cách đó có thể gây:

- Trang thiếu dữ liệu không ổn định.
- Tổng số kết quả làm lộ tài liệu không được phép.
- Dữ liệu nhạy cảm đi qua cache hoặc mapping trước khi bị loại.
- Hiệu năng kém khi phần lớn dữ liệu không thuộc phạm vi truy cập.

Nên đưa phạm vi được phép vào truy vấn hoặc cơ chế tìm kiếm trước khi tính phân trang, count và aggregate, theo hợp đồng chức năng.

Nếu có trường hợp chỉ trả một thống kê công khai, đó phải là quyền riêng được mô hình hóa, không phải sản phẩm phụ của bộ đếm toàn cục.

### 8.2. API bulk cần chính sách lỗi rõ ràng

Ví dụ:

```http
POST /api/documents/bulk-archive
Content-Type: application/json

{
  "documentIds": [
    "e3b8361a-b663-4a81-ae6c-8fedfa0c47fe",
    "a7ea694d-1b15-47f3-a6c1-33e71f577a42"
  ]
}
```

Hệ thống phải kiểm tra quyền đối với mọi đối tượng, không chỉ phần tử đầu tiên.

Cần chọn một hợp đồng:

| Hợp đồng | Hành vi |
|---|---|
| Atomic | Một đối tượng không được phép làm toàn bộ thao tác không thay đổi dữ liệu |
| Partial result | Mỗi đối tượng có kết quả riêng; chỉ đối tượng được phép bị tác động |

Cả hai đều có thể phù hợp tùy nghiệp vụ. Yêu cầu phải nói rõ cách xử lý ID không tồn tại, không được phép, trùng lặp, số lượng tối đa và cấu trúc response.

Với partial result, thông tin lỗi theo từng ID không được làm lộ sự tồn tại hoặc metadata trái chính sách. Với atomic, không được cập nhật một phần rồi chỉ trả lỗi chung.

### 8.3. Tài nguyên con phải khớp tài nguyên cha

Đối với:

```http
GET /api/projects/{projectId}/documents/{documentId}
```

cần xác minh:

- Người gọi có quyền thực hiện hành động trong project.
- Document thực sự thuộc project được tham chiếu.
- Document và project thuộc phạm vi tenant hợp lệ.
- Những điều kiện riêng của document cũng được đáp ứng.

Chỉ kiểm tra quyền với project rồi tải documentId toàn cục là chưa đủ. Người gọi có thể ghép một project được phép với document của project khác.

Một truy vấn theo tenant, projectId và documentId có thể thực thi phần quan hệ. Các quy tắc chia sẻ hoặc trạng thái vẫn cần được áp dụng theo chính sách.

### 8.4. File, phiên bản và export

Quyền đọc document chưa chắc tự bao gồm mọi phiên bản, attachment hoặc định dạng export. Cần xác định rõ quyền kế thừa.

Tác vụ export có ít nhất hai đối tượng cần quan tâm:

1. Phạm vi dữ liệu được đưa vào export.
2. Tác vụ và artifact kết quả được ai xem hoặc tải.

Một người không được đọc dữ liệu gốc không được lấy nó bằng cách truy cập jobId hoặc đường dẫn file kết quả.

## 9. Cache, xử lý nền và quyền thay đổi theo thời gian

### 9.1. Cache phải giữ ranh giới truy cập

Cache chỉ theo documentId có thể trả nội dung đã được tạo cho một người dùng khác nếu nội dung hoặc trường response phụ thuộc quyền.

Yêu cầu cần phân biệt:

- Cache dữ liệu nội bộ trước phân quyền.
- Cache quyết định allow/deny.
- Cache response đã được chiếu trường theo người gọi.
- Cache CDN hoặc proxy ở ranh giới HTTP.

Mỗi loại có khóa, thời gian sống và chính sách vô hiệu hóa khác nhau. Dữ liệu được lấy từ cache vẫn cần kiểm tra quyền nếu cache đó không mang bảo đảm truy cập tương ứng.

Nếu cache quyết định, khóa có thể cần subject, tenant, action, object và phiên bản quyền. Không coi danh sách này là công thức duy nhất; cần dựa trên những yếu tố thực tế tham gia policy.

### 9.2. Thu hồi quyền cần có thời hạn hiệu lực

Một thành viên bị loại khỏi dự án có thể vẫn còn token, cache hoặc tác vụ đang chờ.

Yêu cầu cần chỉ rõ:

- Thời gian tối đa để thay đổi quyền có hiệu lực.
- Dữ liệu nào cần đọc lại hoặc vô hiệu hóa.
- Cách xử lý request đang thực thi.
- Cách xử lý liên kết tải xuống đã cấp.
- Chính sách với job đã tạo nhưng chưa chạy.

Không thể tuyên bố “thu hồi ngay lập tức” nếu kiến trúc vẫn dùng cache quyền vài phút mà không có cơ chế vô hiệu hóa.

### 9.3. Job bất đồng bộ không được nhận quyền ngầm toàn cục

Khi người dùng yêu cầu export:

```text
HTTP request → queue → worker export → object storage
```

cần xác định job đang thực hiện thay mặt người dùng hay dưới quyền hệ thống cho một mục đích riêng.

Nếu thay mặt người dùng, phải có cách ràng buộc subject, tenant, phạm vi và hành động. Worker không được tin ownerId hoặc tenantId tùy ý trong message như bằng chứng quyền.

Cũng cần chọn chính sách thời điểm:

- Quyền được xác nhận lúc tạo job.
- Quyền được xác nhận lại lúc thực thi.
- Quyền được xác nhận lại khi tải kết quả.
- Hoặc một mô hình snapshot quyền có thời hạn và lý do nghiệp vụ rõ ràng.

Các lựa chọn có tác động khác nhau khi quyền bị thu hồi. Không để hành vi phụ thuộc ngẫu nhiên vào tốc độ xử lý queue.

## 10. Response và nhật ký phân quyền

### 10.1. 401, 403 và 404

Ở mức thiết kế:

- 401 gắn với việc cần xác thực hoặc thông tin xác thực không được chấp nhận.
- 403 thường dùng khi chủ thể đã được xác định nhưng không được phép thực hiện thao tác.
- 404 có thể được dùng để không tiết lộ sự tồn tại của tài nguyên ngoài phạm vi.

Chính sách cụ thể phải nhất quán với hợp đồng HTTP và mô hình tiết lộ thông tin của API. Không bắt buộc mọi hệ thống trả cùng một mã cho mọi loại từ chối.

Nếu dùng 404 để che tồn tại, response không nên chứa tên tài liệu, chủ sở hữu hoặc tenant thực tế. Không để nhánh “không tồn tại” và “tồn tại nhưng không được phép” khác nhau rõ ràng qua nội dung lỗi không cần thiết.

Thời gian xử lý cũng có thể tạo kênh tiết lộ. Cần đánh giá theo mức nhạy cảm, nhưng không hứa thời gian hoàn toàn giống nhau chỉ vì status code giống nhau.

### 10.2. Client nhận lỗi gọn; hệ thống giữ nguyên nhân nội bộ

Một response công khai có thể là:

```json
{
  "code": "RESOURCE_NOT_AVAILABLE",
  "message": "Tài nguyên không khả dụng.",
  "requestId": "req-example-004"
}
```

Nhật ký nội bộ có thể ghi mã lý do để phục vụ điều tra:

```text
action=DOCUMENT_READ
decision=DENY
reason=TENANT_SCOPE_MISMATCH
subject=<internal-subject-reference>
requestedObject=<controlled-reference>
requestId=req-example-004
```

Không ghi nguyên access token, credential, nội dung tài liệu hoặc dữ liệu cá nhân không cần thiết. ID đối tượng và subject cũng cần được bảo vệ theo chính sách log, không mặc định là dữ liệu công khai.

### 10.3. Nhật ký không thay thế chặn truy cập

Ghi một sự kiện deny sau khi response đã trả nội dung là quá muộn. Điều kiện bắt buộc là không có dữ liệu hoặc tác dụng phụ trái phép; log chỉ là bằng chứng và hỗ trợ vận hành.

## 11. Đặc tả yêu cầu có thể kiểm chứng

### 11.1. Từ phát biểu mơ hồ đến quy tắc rõ ràng

Phát biểu mơ hồ:

> API phải kiểm tra quyền trên tài liệu.

Phát biểu cụ thể:

> Với thao tác đọc tài liệu, service phải sử dụng subject từ ngữ cảnh xác thực và tenant đã xác minh. Tài liệu chỉ được trả về nếu thuộc tenant đó, subject còn membership hợp lệ, có scope đọc và là chủ sở hữu hoặc có grant đọc phù hợp. ID, ownerId hoặc role do request tự khai không được dùng làm căn cứ thay thế. Nếu không đáp ứng, không trả metadata hoặc nội dung ngoài chính sách lỗi đã công bố.

Yêu cầu sửa bản nháp:

> Thao tác sửa nội dung chỉ được commit khi subject có quyền EDIT_DRAFT trên tài liệu và trạng thái vẫn cho phép sửa tại ranh giới cập nhật. Request không được thay tenant, owner hoặc trạng thái duyệt qua DTO sửa nội dung.

Yêu cầu collection:

> Danh sách, count, tìm kiếm và export phải sử dụng cùng phạm vi dữ liệu được phép theo chủ thể. Tổng số và aggregate không được tính trên tài nguyên ngoài quyền, trừ khi có quyền thống kê riêng được đặc tả.

### 11.2. Mẫu một yêu cầu hoàn chỉnh

```text
ID yêu cầu: API-OBJ-READ-01
Tài sản: nội dung và metadata tài liệu nội bộ
Chủ thể: người dùng đã xác thực
Hành động: READ
Phạm vi: tenant đã xác minh
Điều kiện:
    membership đang hoạt động
    scope đọc hợp lệ
    tài liệu thuộc tenant
    ownership hoặc grant đọc phù hợp
Điểm thực thi:
    service tài liệu và truy vấn theo phạm vi
Hành vi từ chối:
    lỗi theo chính sách che tồn tại, không trả nội dung
Bằng chứng:
    các tình huống cùng tenant, khác tenant, grant bị thu hồi
Chủ sở hữu:
    nhóm phụ trách service tài liệu
```

Số hiệu chỉ là ví dụ cho cách truy vết. Hệ thống nên dùng quy ước yêu cầu chung của dự án và liên kết với rủi ro đã nhận diện.

### 11.3. Truy vết rủi ro tới kiểm soát

| Rủi ro | Yêu cầu kiểm soát | Bằng chứng chấp nhận |
|---|---|---|
| Đổi ID để đọc dữ liệu người khác | Kiểm tra ownership hoặc grant cho từng đối tượng | Người cùng tenant nhưng không có quan hệ bị từ chối |
| Truy cập chéo tenant | Ràng buộc tenant từ context đáng tin | Cùng role ở tenant A không truy cập tài nguyên B |
| Ghép cha và con khác nhau | Kiểm tra quan hệ parent-child | Document không thuộc project bị từ chối |
| Bulk bỏ sót một ID | Kiểm tra mọi phần tử | Không có đối tượng ngoài quyền bị thay đổi |
| Sửa sau khi trạng thái đổi | Bảo đảm điều kiện tại commit | Cạnh tranh không làm sửa tài liệu đã khóa |
| Export vượt quyền | Ràng buộc phạm vi dữ liệu và artifact | Không tải được dữ liệu qua jobId của người khác |
| Quyền cũ còn trong cache | Giới hạn độ trễ thu hồi và vô hiệu hóa | Quyền mất hiệu lực trong thời hạn đã cam kết |
| Response làm lộ tồn tại | Chính sách lỗi thống nhất | Không trả metadata trái phép trong nhánh lỗi |

## 12. Ma trận tình huống chấp nhận

Các tình huống dưới đây là cơ sở thiết kế kiểm thử khi triển khai, không phải kết quả kiểm thử đã chạy cho một hệ thống cụ thể.

| Chủ thể và đối tượng | Hành động | Kết quả theo chính sách ví dụ |
|---|---|---|
| Chủ sở hữu, cùng tenant, membership active, đủ scope | READ | Cho phép |
| Người khác cùng tenant, không có grant đọc | READ | Từ chối |
| Có quyền đọc mọi tài liệu trong tenant hiện tại | READ | Cho phép trong tenant đó |
| Có quyền đọc ở tenant A, tài liệu thuộc B | READ | Từ chối |
| Chủ sở hữu, thiếu scope cần thiết | READ | Từ chối |
| Chủ sở hữu nhưng membership đã vô hiệu | READ | Từ chối |
| Chủ sở hữu bản nháp, đủ điều kiện | EDIT_DRAFT | Cho phép |
| Chủ sở hữu tài liệu đã duyệt | EDIT_DRAFT | Từ chối theo chính sách trạng thái |
| Có quyền đọc toàn bộ nhưng không có quyền sửa | EDIT_DRAFT | Từ chối |
| Client tự khai ownerId khớp user | READ hoặc EDIT | Không ảnh hưởng căn cứ quyền |
| ID tồn tại nhưng ngoài phạm vi | READ | Không trả metadata hoặc nội dung |
| Project được phép nhưng document thuộc project khác | READ | Từ chối |
| Bulk có một tài nguyên ngoài quyền | BULK | Tuân thủ đúng atomic hoặc partial contract |
| Grant bị thu hồi trong lúc có cache | READ | Từ chối trong thời hạn hiệu lực đã công bố |

### 12.1. Kiểm tra theo chiều ngang và chiều dọc

Chiều ngang: hai người có cùng vai trò nhưng khác tài nguyên. Đây là trường hợp dễ bị bỏ sót nếu chỉ thử admin và user.

Chiều dọc: chủ thể quyền thấp hơn thử một hành động được dành cho chủ thể quyền cao hơn. Cần kết hợp cả quyền chức năng và quyền đối tượng.

Thêm chiều tenant và trạng thái để tránh một ma trận chỉ bao phủ role:

```text
subject × action × tenant × relation × object state
```

Không nhất thiết thử mọi tích tổ hợp một cách máy móc. Chọn các trường hợp đại diện cho từng nhánh cho phép, từ chối và những giao điểm có rủi ro.

### 12.2. Kiểm tra tác dụng phụ khi từ chối

Kết quả 403 hoặc 404 không đủ nếu dữ liệu đã thay đổi.

Cần quan sát:

- Bản ghi có bị cập nhật không.
- Có phát sự kiện nghiệp vụ thành công không.
- Có tạo file hoặc liên kết tải xuống không.
- Có gửi email hoặc thông báo không.
- Cache có bị thay đổi theo thao tác không được phép không.
- Bulk có vô tình cập nhật một phần trái hợp đồng không.

Bằng chứng cần phù hợp với hành vi của endpoint, không chỉ kiểm tra status code.

### 12.3. Kiểm tra đường dẫn tương đương

Một tài liệu có thể được truy cập qua:

- Endpoint chi tiết.
- Endpoint preview.
- Endpoint tải file.
- Endpoint phiên bản.
- Search hoặc danh sách gần đây.
- Export.
- Job nền hoặc liên kết chia sẻ.

Tất cả các đường phải áp dụng quyền tương ứng. Không coi việc endpoint chính đã được bảo vệ là bằng chứng cho các đường còn lại.

## 13. Những sai lầm thường gặp

### 13.1. Chỉ kiểm tra đăng nhập

Token hợp lệ xác nhận chủ thể, không xác nhận quyền trên tài nguyên cụ thể. Mỗi thao tác cần ràng buộc đối tượng và hành động.

### 13.2. Coi UUID là cơ chế phân quyền

ID khó đoán vẫn có thể bị biết hoặc được chia sẻ. Khi đã biết ID, quyền phải tiếp tục được kiểm tra.

### 13.3. So userId với một trường bất kỳ

Không phải tài nguyên nào cũng thuộc trực tiếp một người dùng. Có thể quyền theo nhóm, tenant hoặc grant. So sánh một userId không đúng quan hệ có thể vừa chặn người hợp lệ vừa cho phép người không phù hợp.

### 13.4. Tin tenantId hoặc ownerId trong request

Client có thể yêu cầu một tài nguyên, không được tự xác nhận thuộc tính phân quyền của tài nguyên đó. Dùng bản ghi và context có thẩm quyền.

### 13.5. Dùng role admin làm bypass toàn cục

Vai trò phải có phạm vi, hành động và điều kiện. Những quyền vận hành đặc biệt cần được mô hình hóa, ghi nhận và kiểm soát riêng.

### 13.6. Kiểm tra sau khi đã đọc hoặc tạo kết quả nhạy cảm

Tải nội dung vào response, tạo export hoặc phát tác dụng phụ trước quyết định quyền có thể gây lộ dữ liệu dù sau đó trả lỗi.

### 13.7. Bảo vệ chi tiết nhưng bỏ qua danh sách và aggregate

Danh sách, count và kết quả tìm kiếm cũng là biểu diễn dữ liệu. Chúng cần cùng phạm vi quyền hoặc một chính sách riêng được công bố.

### 13.8. Coi service account là quyền vô hạn

Tác vụ nền và dịch vụ nội bộ cũng có chủ thể, phạm vi và mục đích. Việc không có người dùng tương tác không làm ranh giới đối tượng biến mất.

## 14. Điểm cần ghi nhớ

Object-level authorization trả lời một câu hỏi cụ thể: chủ thể này có được thực hiện hành động này trên đối tượng này, trong phạm vi và trạng thái hiện tại hay không.

Yêu cầu tốt chỉ rõ nguồn dữ liệu quyền, ranh giới tenant, quan hệ với đối tượng, điểm thực thi, độ mới của quyết định và hành vi khi từ chối. Truy vấn có phạm vi, policy rõ ràng và kiểm soát tại thời điểm cập nhật giúp biến yêu cầu thành hành vi thực tế.

Bằng chứng chấp nhận phải bao phủ cả người được phép lẫn người không được phép, truy cập chéo tài nguyên và tenant, collection, bulk, tài nguyên con, cache và xử lý nền. Một response từ chối chỉ được coi là đạt khi không có dữ liệu hoặc tác dụng phụ trái phép đã thoát qua ranh giới bảo vệ.
