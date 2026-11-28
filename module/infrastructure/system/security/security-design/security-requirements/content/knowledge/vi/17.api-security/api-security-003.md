# API authorization

## 1. Mục tiêu và phạm vi

API authorization là quá trình quyết định một chủ thể đã được nhận diện có được thực hiện một hành động cụ thể trên một tài nguyên cụ thể, trong ngữ cảnh hiện tại hay không. Quyết định này phải được thực thi ở phía hệ thống cung cấp API; việc giao diện có hiển thị một nút hay không không phải là ranh giới bảo mật.

Trong thiết kế yêu cầu bảo mật, câu “API phải có phân quyền” chưa đủ để triển khai. Đội phát triển cần biết phân quyền theo điều gì, dữ liệu nào làm căn cứ, kiểm tra ở đâu và khi không xác định được quyền thì hệ thống xử lý thế nào. Đội kiểm thử cần các tình huống được phép và bị từ chối có kết quả quan sát được.

Sau bài này, người học có thể:

- Phân biệt authentication với authorization trong xử lý một API request.
- Đặc tả quyền theo chức năng, đối tượng, tenant, thuộc tính dữ liệu và trạng thái nghiệp vụ.
- Xác định dữ liệu đáng tin cậy dùng để ra quyết định và nơi bắt buộc thực thi quyết định.
- Thiết kế ma trận quyền có điều kiện cho phép và mặc định từ chối.
- Viết tiêu chí nghiệm thu cho truy cập ngang, truy cập dọc, thao tác hàng loạt và thu hồi quyền.

Bài sử dụng ví dụ API quản lý các yêu cầu bảo mật của nhiều tổ chức. Mỗi tổ chức được xem là một tenant; một yêu cầu bảo mật có tác giả, trạng thái và phiên bản dữ liệu. Các quy tắc của ví dụ là lựa chọn nghiệp vụ để minh họa cách đặc tả, không phải bộ quyền bắt buộc cho mọi hệ thống.

## 2. Authentication xác định chủ thể, authorization xác định hành động được phép

Một request có access token hợp lệ mới chỉ cung cấp căn cứ để hệ thống nhận diện chủ thể và một số thông tin liên quan. Nó không tự chứng minh chủ thể có thể đọc mọi tài nguyên hoặc gọi mọi thao tác của API.

Ví dụ:

```http
GET /api/requirements/req-108
Authorization: Bearer <access-token>
```

Các câu hỏi cần tách biệt:

| Câu hỏi | Loại quyết định |
| --- | --- |
| Token có được chấp nhận cho API này không? | Authentication và kiểm tra token theo hợp đồng bảo mật |
| Chủ thể đang hoạt động trong tenant nào? | Xác lập ngữ cảnh đáng tin cậy |
| Chủ thể có quyền đọc yêu cầu bảo mật không? | Authorization theo chức năng |
| `req-108` có thuộc tenant và phạm vi được phép của chủ thể không? | Authorization theo đối tượng và phạm vi |
| Chủ thể được xem những trường nào trong kết quả? | Authorization theo thuộc tính dữ liệu |

Một token có scope tổng quát như `requirements:read` có thể là điều kiện cần cho thao tác đọc, nhưng vẫn chưa đủ nếu `req-108` thuộc tenant khác hoặc thuộc một phạm vi không được cấp cho chủ thể.

Tương tự, một người có role `ADMIN` của tenant A không mặc nhiên có quyền quản trị tenant B. Cần xác định role đó được cấp ở phạm vi nào, thay vì coi tên role là quyền lực toàn hệ thống.

## 3. Mô hình hóa quyết định phân quyền

Một quyết định có thể được mô tả bằng bốn thành phần:

```text
Chủ thể + Hành động + Tài nguyên + Ngữ cảnh → Cho phép hoặc Từ chối
```

### 3.1. Chủ thể

Chủ thể có thể là người dùng, tài khoản dịch vụ hoặc một dịch vụ thực hiện công việc theo ủy quyền của người dùng. Những thuộc tính có thể cần gồm định danh, tenant được chọn và đã xác minh, trạng thái hoạt động, quyền được cấp và phiên bản thông tin phân quyền.

Không lấy `userId`, `role` hoặc `tenantId` do request tự khai làm sự thật chỉ vì trường đó có trong JSON. Nếu client có quyền chọn một tenant làm việc, hệ thống vẫn phải kiểm tra chủ thể có quyền tham gia tenant đó và xây dựng ngữ cảnh đã xác minh.

### 3.2. Hành động

Hành động bảo mật nên phản ánh ý nghĩa nghiệp vụ, không chỉ HTTP method. Cùng là POST nhưng tạo bản nháp, gửi duyệt và phê duyệt là các hành động khác nhau.

```text
requirement.read
requirement.create
requirement.update-content
requirement.submit
requirement.approve
requirement.export
```

Định danh hành động rõ ràng giúp đặc tả quyền và bằng chứng kiểm thử không phụ thuộc hoàn toàn vào cách đặt URL. Nếu API có nhiều đường dẫn thực hiện cùng một hành động, các đường dẫn đó phải đáp ứng cùng chính sách liên quan.

### 3.3. Tài nguyên

Tài nguyên không chỉ là một ID trong request. Chính sách có thể cần tenant thực sự của bản ghi, tác giả, nhóm phụ trách, trạng thái và độ nhạy của dữ liệu.

Các thuộc tính này cần được lấy từ nguồn có thẩm quyền của hệ thống. Ví dụ, khi sửa `req-108`, không dùng trường `authorId` trong body để kết luận người gửi là tác giả. Phải đối chiếu với tác giả đang được lưu của `req-108`.

### 3.4. Ngữ cảnh

Ngữ cảnh có thể gồm trạng thái workflow, phạm vi ủy quyền, thời điểm hiệu lực của quyền và yêu cầu phân tách nhiệm vụ. Chỉ đưa vào chính sách những yếu tố hệ thống có thể xác lập và kiểm chứng được.

Một điều kiện như “người dùng đáng tin thì cho phép” không đủ cụ thể. Một điều kiện như “chủ thể có quyền phê duyệt trong cùng tenant, yêu cầu ở trạng thái SUBMITTED và chủ thể không phải tác giả” có thể triển khai và kiểm thử.

## 4. Những chiều phân quyền cần đặc tả riêng

### 4.1. Quyền theo chức năng

API phải kiểm tra chủ thể có được thực hiện hành động hay không. Quyền xem danh sách không tự bao gồm quyền xuất toàn bộ dữ liệu; quyền cập nhật nội dung không tự bao gồm quyền phê duyệt.

Một hệ thống chỉ chặn giao diện quản trị nhưng vẫn cho mọi tài khoản gọi endpoint quản trị có lỗi ở ranh giới chức năng. Thay URL hoặc gọi trực tiếp API không được làm xuất hiện quyền mà chủ thể chưa được cấp.

### 4.2. Quyền theo đối tượng

Có quyền gọi một API không có nghĩa có quyền trên mọi ID mà API nhận. Ví dụ, tác giả được sửa bản nháp của mình nhưng không được sửa bản nháp của đồng nghiệp chỉ bằng cách thay `requirementId`.

ID khó đoán giúp hạn chế khả năng tìm ra định danh, nhưng không thay kiểm tra quyền. Một ID có thể được biết qua liên kết được chia sẻ, lịch sử hoạt động hoặc một response hợp lệ khác.

### 4.3. Quyền theo tenant

Phạm vi tenant cần được thực thi ở mỗi lần truy cập tài nguyên liên quan. Cần kiểm tra cả đối tượng chính lẫn các ID liên quan trong request.

Ví dụ, một yêu cầu bảo mật của tenant A không được gắn với `projectId` thuộc tenant B chỉ vì chủ thể được phép cập nhật yêu cầu chính. Khi tạo mới tài nguyên chưa có bản ghi để kiểm tra quyền sở hữu, hệ thống vẫn phải kiểm tra quyền trên tenant hoặc tài nguyên cha nơi đối tượng sẽ được tạo.

Một URL chứa `/tenants/A/` không phải bằng chứng chủ thể có quyền trong A. Một body khai `tenantId=A` cũng không tạo ra quyền đó.

### 4.4. Quyền theo thuộc tính dữ liệu

Quyền đọc một đối tượng không luôn đồng nghĩa được đọc mọi trường của nó. Quyền cập nhật một đối tượng cũng không luôn bao gồm quyền sửa mọi thuộc tính.

Ví dụ:

| Thuộc tính | Tác giả được sửa nội dung bản nháp | Người duyệt |
| --- | --- | --- |
| `title`, `description` | Được sửa khi bản nháp thuộc phạm vi của mình | Theo chính sách biên tập được đặc tả riêng |
| `tenantId`, `authorId` | Không được tự gán lại qua API sửa nội dung | Không được tự gán lại qua API phê duyệt |
| `status` | Chỉ thay đổi qua hành động workflow được cấp quyền | Chỉ thay đổi qua hành động workflow được cấp quyền |
| `approvalNote` | Không được giả danh người phê duyệt để ghi | Được ghi trong thao tác phê duyệt hợp lệ |
| `internalRiskDetail` | Chỉ được đọc nếu có quyền xem dữ liệu này | Phụ thuộc phạm vi quyền đã cấp |

DTO nhận vào và DTO trả về cần được thiết kế theo hợp đồng quyền. Việc bind toàn bộ JSON vào entity hoặc serialize toàn bộ entity có thể làm lộ hoặc cho sửa các trường vượt phạm vi.

### 4.5. Quyền theo trạng thái và phân tách nhiệm vụ

Một chủ thể có thể được sửa nội dung khi tài nguyên ở DRAFT nhưng không được sửa cùng nội dung sau khi đã APPROVED. Quyền phê duyệt có thể yêu cầu người duyệt khác tác giả.

Đây không chỉ là điều kiện giao diện. Trạng thái và quan hệ giữa chủ thể với tài nguyên phải được kiểm tra trong luồng thực thi phía máy chủ, bao gồm cả khi hai request cạnh tranh nhau.

## 5. Xây dựng ma trận quyền có thể kiểm chứng

Giả sử hệ thống có các quyền trong phạm vi tenant:

- `READ_OWN`: đọc yêu cầu do chính mình là tác giả.
- `READ_ALL`: đọc yêu cầu trong tenant đang được cấp quyền này.
- `UPDATE_OWN`: sửa nội dung bản nháp do chính mình là tác giả.
- `APPROVE`: phê duyệt yêu cầu đã được gửi duyệt, với điều kiện không phải tác giả.

Một ma trận cho các hành động trọng tâm có thể là:

| Hành động | Điều kiện về quyền | Điều kiện về tài nguyên | Điều kiện chung |
| --- | --- | --- | --- |
| Đọc | `READ_ALL`, hoặc `READ_OWN` khi là tác giả | Tài nguyên thuộc phạm vi tenant được xác minh | Chủ thể đang hoạt động |
| Sửa nội dung | `UPDATE_OWN` | Cùng tenant, là tác giả, trạng thái DRAFT | Chỉ sửa các trường được hợp đồng cho phép |
| Phê duyệt | `APPROVE` | Cùng tenant, trạng thái SUBMITTED, không phải tác giả | Chuyển trạng thái và ghi người duyệt trong cùng thao tác hợp lệ |

Những quyền trên không tự kế thừa nhau. Theo ma trận minh họa, `APPROVE` không tự động tạo `READ_ALL`; nếu công việc duyệt cần quyền đọc, gói quyền nghiệp vụ phải cấp rõ cả hai. Điều này tránh việc suy ra quyền ngầm chỉ vì tên role nghe có vẻ cao hơn.

Mặc định là từ chối nếu không khớp một quy tắc cho phép đã xác định. Một action mới hoặc một trạng thái mới không nên tự được chấp nhận chỉ vì chưa có nhánh xử lý.

Ma trận cần chỉ rõ phạm vi role và cách chuyển role thành permission. Nếu quyền `READ_ALL` là quyền trong một tenant, một biến có tên chung như `isAdmin` không đủ để biểu diễn phạm vi này một cách an toàn.

## 6. Đặc tả yêu cầu bảo mật cho API

### 6.1. Yêu cầu nền tảng

```text
REQ-API-AUTHZ-01 — Quyết định phân quyền phía máy chủ

Trước khi trả dữ liệu được bảo vệ hoặc thực hiện một tác động nghiệp vụ,
hệ thống phải xác định chủ thể từ ngữ cảnh đã được xác minh và đánh giá
quyền cho hành động, tài nguyên, tenant cùng các điều kiện nghiệp vụ liên quan.

Chỉ thực hiện hành động khi có một quyết định cho phép hợp lệ. Trường hợp
thiếu thuộc tính bắt buộc, không có quy tắc cho phép hoặc không xác định
được quyết định phải không dẫn tới việc cấp quyền.
```

Câu cuối yêu cầu giữ ranh giới bảo mật khi chính sách hoặc dữ liệu phân quyền có lỗi. Nó không bắt buộc mọi lỗi đều trả cùng một HTTP status; cách phản hồi lỗi cần được đặc tả riêng.

### 6.2. Yêu cầu theo từng ranh giới

| Mã | Nội dung yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| REQ-API-AUTHZ-02 | Mỗi action được bảo vệ phải có quy tắc cho phép và phạm vi áp dụng rõ ràng; action chưa có quy tắc phải bị từ chối | Danh mục action và ma trận quyền |
| REQ-API-AUTHZ-03 | Mọi thao tác nhận ID phải xác minh quyền trên đối tượng thực tế; không chỉ kiểm tra role của caller | Tình huống đổi ID trong cùng tenant và khác tenant |
| REQ-API-AUTHZ-04 | Tenant và các thuộc tính quyết định quyền phải lấy từ nguồn đã xác minh; dữ liệu tự khai trong request không được nâng quyền | Luồng xây dựng subject context và tải tài nguyên |
| REQ-API-AUTHZ-05 | API phải có danh sách trường được phép nhận và trả theo quyền; trường được bảo vệ không được tự động bind từ request | DTO, mapping và kết quả request chứa trường ngoài quyền |
| REQ-API-AUTHZ-06 | Trạng thái và điều kiện phân tách nhiệm vụ phải được thực thi cùng thao tác nghiệp vụ mà chúng bảo vệ | Kết quả chuyển trạng thái hợp lệ, bị từ chối và cạnh tranh |
| REQ-API-AUTHZ-07 | Các biến thể đọc, tìm kiếm, thống kê, export và batch phải áp dụng phạm vi quyền tương ứng | Kết quả theo từng đường truy cập |
| REQ-API-AUTHZ-08 | Khi thành phần ra quyết định lỗi hoặc không có đủ dữ liệu, hệ thống không được dùng một nhánh mặc định cho phép | Kịch bản lỗi policy, timeout và dữ liệu thiếu |

Một yêu cầu tốt cần có điều kiện thành công và điều kiện bị từ chối. Ví dụ, “tác giả sửa bản nháp của mình thành công” phải đi cùng “cùng tác giả không sửa được yêu cầu đã duyệt” và “người khác có cùng role không sửa được bản nháp này”.

### 6.3. Định nghĩa ngoại lệ có chủ ý

Endpoint công khai vẫn có thể tồn tại, nhưng phải được đánh dấu rõ theo hợp đồng sản phẩm. Không suy ra public chỉ vì endpoint chưa được gắn cấu hình phân quyền.

Nếu có vai trò quản trị toàn hệ thống, cần mô tả riêng điều kiện được sử dụng, hành động được cấp, phạm vi tenant và bằng chứng audit. Không tạo ngoại lệ chung như “admin bỏ qua mọi kiểm tra” rồi kỳ vọng mọi nhóm hiểu giống nhau.

## 7. Ví dụ Java: biểu diễn chính sách một cách tường minh

Ví dụ sau dùng cú pháp record của Java để minh họa một policy thuần. Nó chỉ biểu diễn ba action trong ma trận ở trên; việc xác thực caller, tải dữ liệu, bảo vệ transaction và ánh xạ lỗi API thuộc luồng tích hợp.

```java
import java.util.Objects;
import java.util.Set;

public final class RequirementAuthorization {

    public enum Action {
        READ, UPDATE_CONTENT, APPROVE
    }

    public enum Permission {
        READ_OWN, READ_ALL, UPDATE_OWN, APPROVE
    }

    public enum Status {
        DRAFT, SUBMITTED, APPROVED
    }

    public record Subject(
            String userId,
            String tenantId,
            boolean active,
            Set<Permission> permissions) {

        public Subject {
            Objects.requireNonNull(userId);
            Objects.requireNonNull(tenantId);
            permissions = Set.copyOf(permissions);
        }
    }

    public record Requirement(
            String id,
            String tenantId,
            String authorId,
            Status status,
            long version) {

        public Requirement {
            Objects.requireNonNull(id);
            Objects.requireNonNull(tenantId);
            Objects.requireNonNull(authorId);
            Objects.requireNonNull(status);
        }
    }

    public boolean isAllowed(
            Subject subject,
            Action action,
            Requirement resource) {

        if (subject == null || action == null || resource == null) {
            return false;
        }

        if (!subject.active()) {
            return false;
        }

        if (!subject.tenantId().equals(resource.tenantId())) {
            return false;
        }

        boolean isAuthor = subject.userId().equals(resource.authorId());
        Set<Permission> permissions = subject.permissions();

        switch (action) {
            case READ:
                return permissions.contains(Permission.READ_ALL)
                        || (isAuthor
                            && permissions.contains(Permission.READ_OWN));

            case UPDATE_CONTENT:
                return isAuthor
                        && permissions.contains(Permission.UPDATE_OWN)
                        && resource.status() == Status.DRAFT;

            case APPROVE:
                return !isAuthor
                        && permissions.contains(Permission.APPROVE)
                        && resource.status() == Status.SUBMITTED;

            default:
                return false;
        }
    }
}
```

Một số chi tiết có ý nghĩa bảo mật:

- Quy tắc cùng tenant được đánh giá trước mọi nhánh cho phép của ví dụ.
- Permission được xét cùng quan hệ với đối tượng và trạng thái; không chỉ kiểm tra chuỗi role.
- Tập permission được sao chép thành một tập không cho sửa trực tiếp qua record.
- Action không khớp một nhánh cho phép không được tự cấp quyền.
- `version` có trong dữ liệu nhưng policy không tự giải quyết cạnh tranh; luồng ghi phải xử lý việc tài nguyên thay đổi sau khi được kiểm tra.

Đối tượng `Subject` phải do thành phần tin cậy xây dựng từ quá trình nhận diện và phân quyền đã xác minh. Nếu controller bind trực tiếp JSON của client thành `Subject`, mọi điều kiện trên đều có thể dựa vào dữ liệu do chính caller tự khai.

Tương tự, `Requirement` dùng để đánh giá phải phản ánh bản ghi thật. Không tạo nó từ các trường tenant, tác giả hoặc trạng thái trong request rồi gọi policy để chứng minh request hợp lệ.

## 8. Thực thi quyết định ở đúng ranh giới

### 8.1. Gateway không biết đủ mọi thuộc tính của tài nguyên

Gateway có thể kiểm tra token, route và một số quyền tổng quát. Nhưng nhiều quyết định cần dữ liệu nghiệp vụ như tác giả thực tế, trạng thái hiện tại và phạm vi dự án mà dịch vụ sở hữu tài nguyên mới biết.

Một luồng có thể được tổ chức như sau:

```text
Xác lập subject context đã kiểm chứng
    → xác định action của request
    → tải tài nguyên trong phạm vi tenant phù hợp
    → đánh giá policy với thuộc tính thực tế
    → thực thi thao tác hoặc tạo response trong phạm vi được phép
```

Nếu gateway là một phần của ranh giới tin cậy, dịch vụ phía sau cần biết thông tin chủ thể đã được bảo vệ khỏi giả mạo trên đường truyền. Việc chấp nhận tùy ý header `X-User-Id` hoặc `X-Role` từ mọi nguồn không tạo ra một subject context đáng tin cậy.

Cổng vào nội bộ cũng cần được xét. Một API không được phép mất kiểm tra quyền chỉ vì request đi từ mạng nội bộ hoặc từ một dịch vụ khác thay vì từ trình duyệt.

### 8.2. Ràng buộc truy vấn theo phạm vi được phép

Khi đọc một đối tượng, repository có thể truy vấn bằng cả ID và tenant đã được xác minh:

```sql
SELECT id, tenant_id, author_id, status, version
FROM security_requirement
WHERE id = :requirement_id
  AND tenant_id = :verified_tenant_id;
```

Điều này giúp giới hạn tập dữ liệu mà dịch vụ tải. Tuy nhiên, điều kiện cùng tenant chưa tự chứng minh quyền theo tác giả, permission hoặc trạng thái. Các điều kiện khác trong policy vẫn phải được thực thi.

Ngược lại, nếu API được thiết kế cho một chủ thể có quyền đa tenant, phạm vi truy vấn phải phản ánh đúng danh sách hoặc quan hệ đã được cấp. Không cố áp một tenant cố định rồi thêm nhánh bỏ qua mọi kiểm tra khi gặp tài khoản quản trị.

### 8.3. Giữ điều kiện phân quyền đúng đến lúc ghi

Một lỗi có thể xuất hiện theo thứ tự:

```text
Request A đọc tài nguyên ở trạng thái DRAFT và được phép sửa.
Request B chuyển tài nguyên sang SUBMITTED.
Request A ghi nội dung mà không kiểm tra trạng thái hoặc phiên bản nữa.
```

Policy lúc đầu có thể đúng, nhưng thao tác ghi thực tế không còn đáp ứng điều kiện “chỉ sửa bản nháp”. Đây là khoảng cách giữa thời điểm kiểm tra và thời điểm sử dụng kết quả.

Luồng ghi cần dùng transaction và chiến lược cạnh tranh phù hợp. Ví dụ, thao tác cập nhật nội dung có thể thêm điều kiện trạng thái, tác giả, tenant và phiên bản:

```sql
UPDATE security_requirement
SET title = :title,
    description = :description,
    version = version + 1
WHERE id = :requirement_id
  AND tenant_id = :verified_tenant_id
  AND author_id = :verified_user_id
  AND status = 'DRAFT'
  AND version = :expected_version;
```

Câu SQL minh họa việc giữ các điều kiện về tài nguyên đến thời điểm ghi. Nó không tự kiểm tra chủ thể có `UPDATE_OWN`; lớp nghiệp vụ vẫn cần quyết định permission hợp lệ.

Nếu số hàng cập nhật là 0, không được báo thành công. Luồng tích hợp phải phân loại theo hợp đồng lỗi mà không làm lộ dữ liệu ngoài quyền, đồng thời tránh suy ra rằng tất cả trường hợp 0 hàng đều có cùng nguyên nhân.

Đối với phê duyệt, việc kiểm tra trạng thái, áp dụng chuyển trạng thái, ghi người duyệt và tạo dữ liệu audit nghiệp vụ cần có tính nhất quán phù hợp. Nếu thao tác thất bại, không được để tài nguyên ở trạng thái duyệt dở hoặc phát sự kiện thành công như thể việc duyệt đã hoàn tất.

### 8.4. Ràng buộc dữ liệu đầu vào

API sửa nội dung chỉ nên nhận các trường thuộc hợp đồng sửa nội dung:

```json
{
  "title": "Yêu cầu kiểm soát quyền truy cập",
  "description": "Mô tả đã được cập nhật",
  "expectedVersion": 7
}
```

Hệ thống không được lấy `tenantId`, `authorId`, `approvedBy` hoặc `status` từ body để cập nhật entity qua cùng đường này. Chính sách API cần nói rõ trường ngoài hợp đồng bị từ chối hay bị bỏ qua; trong cả hai cách, trường đó không được làm thay đổi dữ liệu được bảo vệ.

Phiên bản kỳ vọng do client gửi là đầu vào phục vụ phát hiện xung đột, không phải bằng chứng client có quyền. Caller vẫn phải được phân quyền trên tài nguyên thực tế.

## 9. Danh sách, batch, export và API tổng hợp

### 9.1. Danh sách không phải nhiều lần đọc tùy ý

Một endpoint danh sách cần giới hạn tập dữ liệu theo quyền trước khi tạo kết quả trả về. Nếu chỉ lấy một trang dữ liệu toàn tenant rồi loại các bản ghi không được xem sau khi phân trang, kết quả có thể thiếu hoặc sai thông tin phân trang.

Các trường như tổng số bản ghi, số lượng theo trạng thái hoặc gợi ý tìm kiếm cũng phải phản ánh đúng phạm vi được phép. Trả về danh sách đã lọc nhưng vẫn kèm tổng số của toàn hệ thống có thể tiết lộ thông tin ngoài phạm vi.

Việc thực thi có thể nằm trong truy vấn, mô hình dữ liệu phục vụ truy cập hoặc một lớp policy thích hợp. Yêu cầu cần đặc tả kết quả được phép quan sát, không ép một kỹ thuật khi kiến trúc chưa được quyết định.

### 9.2. Batch phải có quyền cho từng phần tử liên quan

Ví dụ:

```json
{
  "requirementIds": ["req-108", "req-109", "req-902"]
}
```

Một chủ thể có quyền trên `req-108` không vì thế được phép thao tác trên cả ba ID. Hệ thống phải xác định quyền cho từng đối tượng hoặc cho toàn phạm vi theo một quy tắc đã được định nghĩa rõ.

Hợp đồng batch cần chọn hành vi:

- Từ chối toàn bộ nếu có phần tử không được phép, và không tạo tác động một phần.
- Hoặc xử lý từng phần tử độc lập, với kết quả và tác động của từng phần tử được mô tả rõ.

Không để hành vi thay đổi tùy việc đối tượng trái phép xuất hiện đầu hay cuối danh sách. Nếu có tác động một phần, cách trả lỗi cũng phải tránh tiết lộ dữ liệu của phần tử ngoài quyền.

### 9.3. Export là một hành động cần được cấp quyền

Quyền mở một trang danh sách không tự đồng nghĩa được tải toàn bộ dữ liệu hoặc các trường nhạy cảm trong bản xuất. API export cần áp dụng cả phạm vi hàng và phạm vi thuộc tính dữ liệu.

Khi tạo tệp bất đồng bộ, cần xác định ai được tạo tác vụ, phạm vi dữ liệu mà tác vụ được đọc và ai được tải kết quả. Một ID tác vụ hoặc đường dẫn tệp không được trở thành cách bỏ qua chính sách đọc dữ liệu.

### 9.4. API tổng hợp cần giữ nguồn gốc quyền

Một endpoint có thể gộp dữ liệu từ nhiều dịch vụ. Nếu caller được xem yêu cầu bảo mật nhưng không được xem hồ sơ nhân sự chi tiết, việc dữ liệu nhân sự được lấy bằng tài khoản dịch vụ không tự cấp quyền trả nó cho caller.

Dịch vụ tổng hợp phải giữ được ngữ cảnh chủ thể hoặc một phạm vi ủy quyền phù hợp cho các thành phần phía sau. Tránh dùng quyền rộng của tài khoản dịch vụ để vô tình làm thay việc mà người gọi bị cấm thực hiện.

## 10. Thu hồi quyền, cache và tác vụ bất đồng bộ

### 10.1. Quyền có vòng đời

Một quyền có thể bị thu hồi, một người dùng có thể rời tenant hoặc tài nguyên có thể đổi phạm vi. Kiểm tra quyền chỉ khi đăng nhập không đáp ứng được yêu cầu nếu phiên hoặc token còn hiệu lực lâu hơn thời gian cho phép thu hồi.

Cần đặc tả thời gian tối đa để một thay đổi quyền có hiệu lực trên các API liên quan. Ví dụ sau là một quyết định mẫu, không phải con số áp dụng chung:

```text
REQ-API-AUTHZ-09 — Hiệu lực thu hồi quyền

Sau khi thao tác thu hồi được hệ thống xác nhận thành công, các request
mới dùng quyền đã thu hồi phải bị từ chối trong tối đa 30 giây.

Giới hạn này bao gồm cache quyết định và cache quyền tại mọi thành phần
phục vụ nhóm API được bảo vệ. Hành vi của tác vụ đã bắt đầu phải được
đặc tả riêng cho từng loại tác vụ.
```

Con số cần xuất phát từ rủi ro, kiến trúc và khả năng vận hành. Nếu một API có yêu cầu thu hồi tức thời, không thể dùng cache quyền hết hạn sau nhiều phút rồi chỉ tuyên bố quyền đã được kiểm tra.

### 10.2. Cache phải phản ánh đủ điều kiện của quyết định

Một cache key chỉ gồm `userId` và `role` có thể trả lại kết quả sai cho tenant, action hoặc đối tượng khác. Cache quyết định cần xem xét toàn bộ thuộc tính có thể làm thay đổi kết quả, hoặc chỉ cache phần dữ liệu mà kiến trúc có thể giữ đúng.

Tùy policy, các yếu tố liên quan có thể gồm chủ thể, tenant, action, resource, trạng thái, phiên bản quyền và phiên bản tài nguyên. Điều kiện theo thời gian hoặc ngữ cảnh biến động cũng cần được tính đến.

Không dùng một quyết định cho phép quá hạn khi nguồn policy không truy cập được, trừ khi đã có một chính sách sử dụng dữ liệu cache được xác định rõ và vẫn đáp ứng điều kiện hiệu lực. Nhánh xử lý timeout không được âm thầm mở quyền rộng hơn hợp đồng.

### 10.3. Job cần giữ một mô hình quyền rõ ràng

Một job có thể được đưa vào hàng đợi khi người dùng còn quyền, nhưng bắt đầu chạy sau khi quyền đã bị thu hồi. Cần xác định job được chạy theo quyền hiện tại của người khởi tạo, theo một ủy quyền có thời hạn hay theo một quy tắc nghiệp vụ đã phê duyệt khác.

Đối với mô hình kiểm tra lại khi thực thi, worker nghiệp vụ cần khôi phục ngữ cảnh chủ thể từ nguồn tin cậy và đánh giá lại phạm vi tài nguyên trước khi đọc hoặc tạo tác động. Chỉ lưu `requestedBy` để hiển thị lịch sử không tương đương việc thực thi theo quyền của người đó.

Đối với mô hình cấp ủy quyền cho tác vụ, phạm vi action, tài nguyên, thời hạn và điều kiện hủy cần được quy định. Không biến việc xếp hàng thành một quyền vô thời hạn để truy cập mọi dữ liệu sau này.

### 10.4. Lỗi thành phần phân quyền

Khi hệ thống dùng dịch vụ policy riêng, có thể tách nơi ra quyết định và nơi thực thi. Nơi thực thi phải kiểm tra kết quả hợp lệ, không bỏ qua lỗi kết nối hoặc kết quả không đủ dữ liệu.

Yêu cầu vận hành có thể quy định timeout, cơ chế dự phòng và phản hồi lỗi. Dù chọn cách nào, yêu cầu bảo mật phải xác nhận rằng một sự cố không dẫn tới truy cập mặc định được cho phép.

## 11. Phản hồi lỗi và audit

### 11.1. Phân biệt lỗi nhận diện và lỗi quyền

API cần hợp đồng phản hồi nhất quán. Thông thường, request chưa đáp ứng yêu cầu xác thực nhận phản hồi 401; request đã được nhận diện nhưng không được phép có thể nhận 403. Một số API chọn che sự tồn tại của tài nguyên bằng 404 cho các trường hợp được định nghĩa trước.

Quyết định che bằng 404 cần được áp dụng nhất quán giữa tài nguyên không tồn tại và tài nguyên ngoài phạm vi mà API muốn che. Không để response body, trường bổ sung hoặc đường xử lý khác vô tình công khai lại thông tin đã chọn che.

Lỗi của dịch vụ policy có thể được ánh xạ thành lỗi dịch vụ theo hợp đồng API; không nên giả vờ đó là quyết định quyền bình thường. Điểm bắt buộc là không trả dữ liệu hoặc tạo tác động khi chưa có quyết định cho phép hợp lệ.

### 11.2. Phản hồi bị từ chối phải đi cùng việc không tạo tác động

Một API trả 403 nhưng đã cập nhật dữ liệu, đưa email vào hàng đợi hoặc phát sự kiện thành công vẫn không đáp ứng yêu cầu authorization.

Tiêu chí nghiệm thu cần quan sát trạng thái tài nguyên và các tác động liên quan, không chỉ HTTP status. Đối với thao tác bị từ chối, phải xác định rõ tác động nào bị cấm; audit ghi nhận lần bị từ chối có thể vẫn là hành vi được thiết kế.

### 11.3. Audit đủ để điều tra

Một bản ghi quyết định có thể gồm định danh chủ thể, tenant đã xác minh, action, định danh tài nguyên theo chính sách log, kết quả, mã lý do, thời điểm và mã liên kết request. Với hệ thống dùng policy phiên bản hóa, ghi phiên bản có thể giúp giải thích vì sao request được phép tại thời điểm đó.

Không ghi access token hoặc toàn bộ dữ liệu nhạy cảm của request chỉ để chứng minh đã kiểm tra quyền. Quyền truy cập audit log và thời gian lưu cũng cần được thiết kế theo loại dữ liệu chứa trong đó.

Mã lý do chi tiết có thể phục vụ điều tra nội bộ, trong khi client nhận một thông báo tổng quát theo hợp đồng lỗi. Không phải thông tin nào cần cho vận hành cũng nên được trả về người gọi.

## 12. Ma trận nghiệm thu cho API authorization

### 12.1. Kết hợp tình huống được phép và bị từ chối

Giả sử tenant A có tác giả An và tác giả Bình; tenant B có tác giả Chi. Người duyệt Dũng có quyền `APPROVE` trong tenant A và không phải tác giả của tài nguyên được duyệt.

| Tình huống | Kết quả theo chính sách mẫu | Điều cần quan sát |
| --- | --- | --- |
| An có `READ_OWN`, đọc yêu cầu do An tạo trong A | Cho phép | Chỉ trả trường An được xem |
| An có `READ_OWN`, đổi ID sang yêu cầu của Bình trong A | Từ chối hoặc che theo hợp đồng | Không trả dữ liệu của Bình |
| An có `READ_ALL` trong A, đọc yêu cầu của Chi trong B | Từ chối hoặc che theo hợp đồng | Quyền trong A không mở rộng sang B |
| An có `UPDATE_OWN`, sửa bản nháp của mình | Cho phép | Chỉ trường nội dung được thay đổi |
| An có `UPDATE_OWN`, sửa yêu cầu của mình đã APPROVED | Từ chối thao tác theo hợp đồng | Không đổi nội dung và phiên bản do thao tác bị từ chối |
| Tác giả có `APPROVE`, tự phê duyệt yêu cầu của mình | Từ chối | Quy tắc phân tách nhiệm vụ vẫn được giữ |
| Dũng phê duyệt yêu cầu SUBMITTED trong A mà Dũng không tạo | Cho phép | Ghi trạng thái và người duyệt nhất quán |
| Caller gửi thêm `tenantId`, `authorId`, `status` vào API sửa nội dung | Không cho thay các trường này | Body không được biến thành quyền |
| Caller không có quyền export nhưng có quyền xem danh sách | Từ chối export | Không tạo tệp hoặc job export thành công |
| Thành phần policy timeout trước quyết định | Không cấp quyền | Không có dữ liệu hoặc tác động được bảo vệ |

Các tài khoản thử nghiệm phải có permission xác định rõ, không chỉ tên role giống nhau. Nếu một tài khoản thử vô tình có quyền rộng hơn, kết quả có thể bị diễn giải sai thành chính sách không hoạt động.

### 12.2. Tiêu chí cho một thao tác bị từ chối

```text
Given:
  An có UPDATE_OWN trong tenant A.
  req-109 là bản nháp trong A do Bình tạo.
  Dữ liệu trước request và phiên bản của req-109 đã được xác định.

When:
  An gọi API sửa nội dung với ID req-109.

Then:
  API trả phản hồi từ chối hoặc che tài nguyên theo hợp đồng đã chọn.
  Không có nội dung được bảo vệ nào của req-109 được trả cho An.
  Nội dung, tác giả, tenant và phiên bản không thay đổi do thao tác này.
  Không có sự kiện thành công hoặc tác vụ tiếp theo giả định sửa thành công.
  Có bằng chứng audit phù hợp với chính sách ghi log.
```

### 12.3. Tiêu chí cho cạnh tranh và batch

Với cạnh tranh, cần kiểm chứng rằng request được đánh giá khi DRAFT không thể ghi đè trái quy tắc sau khi tài nguyên đã chuyển trạng thái. Kết quả phải theo chiến lược đồng thời đã chọn, không chỉ theo thứ tự thuận lợi trong một lần thử.

Với batch, dùng ít nhất một tập gồm đối tượng được phép và đối tượng ngoài quyền. Nếu hợp đồng yêu cầu toàn bộ hoặc không gì cả, phải xác nhận không phần tử nào bị thay đổi khi có một phần tử không được phép. Nếu hợp đồng cho phép từng phần, phải quan sát đúng kết quả từng phần mà không lộ dữ liệu ngoài quyền.

### 12.4. Tiêu chí cho thu hồi quyền

Thực hiện một hành động thành công trước khi thu hồi để xác nhận tài khoản thật sự có quyền. Sau đó thu hồi quyền, ghi nhận thời điểm hệ thống xác nhận và kiểm tra các request mới trong cửa sổ hiệu lực đã đặc tả.

Nếu có nhiều instance hoặc nhiều lớp cache, bằng chứng cần bao phủ các đường phục vụ liên quan. Một request bị từ chối trên một instance chưa chứng minh mọi instance đều đã nhận thay đổi.

Các kiểm tra này là tiêu chí của yêu cầu sản phẩm. Chúng không thay việc đánh giá tính đúng đắn của chính sách và cũng không chứng minh những action chưa được kiểm kê đã được bảo vệ.

## 13. Hồ sơ yêu cầu mẫu và điểm cần giữ

Một hồ sơ ngắn cho API sửa nội dung có thể viết:

```text
Action: requirement.update-content.
Tài sản: tính toàn vẹn của yêu cầu bảo mật và ranh giới dữ liệu giữa tenant.
Chủ thể: người dùng đang hoạt động trong tenant đã được xác minh.
Quyền cần có: UPDATE_OWN trong tenant đó.

Điều kiện tài nguyên:
  - Bản ghi thuộc tenant được phép.
  - Chủ thể là tác giả thực tế của bản ghi.
  - Trạng thái tại lúc ghi vẫn là DRAFT.

Đầu vào được phép:
  - title, description và phiên bản kỳ vọng theo hợp đồng API.
  - Không cho tự thay tenant, tác giả, người duyệt hoặc trạng thái workflow.

Thực thi:
  - Kiểm tra policy bằng thuộc tính được tải từ nguồn có thẩm quyền.
  - Giữ điều kiện trạng thái và cạnh tranh đúng đến lúc cập nhật.
  - Không tạo tác động thành công nếu quyết định bị từ chối hoặc không có.

Bằng chứng:
  - Ma trận quyền; vị trí thực thi policy; mapping dữ liệu đầu vào.
  - Trường hợp được phép, khác tác giả, khác tenant, sai trạng thái.
  - Trường hợp request cạnh tranh và lỗi thành phần phân quyền.
```

API authorization đáp ứng mục tiêu khi mỗi hành động được thực hiện đúng phạm vi đã cấp và không thể mở rộng quyền bằng cách đổi ID, tenant, thuộc tính hoặc đường truy cập. Yêu cầu bảo mật cần nối được chủ thể, action, tài nguyên, điều kiện nghiệp vụ, nơi thực thi và bằng chứng nghiệm thu thành một hợp đồng rõ ràng.
