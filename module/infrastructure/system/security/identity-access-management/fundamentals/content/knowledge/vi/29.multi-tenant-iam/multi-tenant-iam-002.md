# Tenant identifier

## 1. Tenant identifier xác định phạm vi nào?

Trong hệ thống nhiều tenant, một tenant thường đại diện cho một tổ chức, khách hàng hoặc không gian làm việc có phạm vi quản trị và dữ liệu riêng. **Tenant identifier**, thường gọi là `tenant_id`, là định danh để hệ thống tham chiếu nhất quán đến phạm vi đó.

Ví dụ, nền tảng quản lý dự án phục vụ hai công ty:

| Đối tượng | Công ty Sao Mai | Công ty Đại Dương |
| --- | --- | --- |
| Tên hiển thị | Sao Mai | Đại Dương |
| Tenant identifier | `tnt_7c91a2` | `tnt_b03f84` |
| URL thuận tiện cho người dùng | `/workspaces/sao-mai` | `/workspaces/dai-duong` |
| Một thành viên dùng chung | Người dùng Lan | Người dùng Lan |
| Vai trò của Lan | Quản trị viên | Người xem |

Các mã trong bài chỉ dùng để minh họa, không phải khuyến nghị về độ dài hay thuật toán sinh mã.

Lan vẫn là một người dùng, nhưng có hai quan hệ thành viên và hai bộ quyền khác nhau. Khi Lan gửi yêu cầu xóa dự án, hệ thống cần biết đồng thời:

- Ai đang thực hiện yêu cầu?
- Yêu cầu đang áp dụng cho tenant nào?
- Người đó có quyền xóa dự án trong tenant ấy không?
- Dự án đích có thuộc đúng tenant ấy không?

Tenant identifier trả lời câu hỏi thứ hai và hỗ trợ kiểm tra câu hỏi thứ tư. Bản thân mã tenant không chứng minh danh tính hoặc quyền hạn.

Một nguyên tắc cần giữ xuyên suốt:

> Biết mã tenant không có nghĩa là được truy cập tenant. Tenant identifier là dữ liệu định danh, không phải credential hay bằng chứng cấp quyền.

## 2. Phân biệt tenant với người dùng, ứng dụng và tài nguyên

Những đối tượng sau có thể liên quan với nhau nhưng không thay thế nhau:

| Định danh | Đại diện cho | Không tự chứng minh |
| --- | --- | --- |
| `tenant_id` | Phạm vi khách hàng hoặc tổ chức trong ứng dụng | Người gọi là thành viên tenant |
| `user_id` hoặc định danh principal nội bộ | Một danh tính người dùng | Quyền của người đó trong mọi tenant |
| `client_id` | Ứng dụng khách trong một hệ thống OAuth/OIDC | Tenant đích của mọi yêu cầu |
| `project_id`, `document_id` | Một tài nguyên nghiệp vụ | Người gọi được truy cập tenant chứa tài nguyên |
| Domain email | Một thuộc tính của địa chỉ email | Tư cách thành viên hoặc quyền quản trị tenant |
| Mã tổ chức từ IdP | Tổ chức hoặc phạm vi do IdP định nghĩa | Quan hệ một-một với tenant nghiệp vụ nội bộ |

Một tenant có thể sử dụng nhiều kết nối IdP. Ngược lại, cùng một nhà cung cấp danh tính có thể xác thực người thuộc nhiều tenant trong ứng dụng.

Không nên mặc định `tenant_id` của nhà cung cấp, tên realm, mã subscription và tenant nghiệp vụ của ứng dụng đều có cùng ý nghĩa. Nếu cần liên kết, hãy lưu ánh xạ rõ ràng giữa định danh ngoài và định danh tenant nội bộ.

Ví dụ:

```text
Tenant nội bộ: tnt_7c91a2
  ├─ Kết nối SSO nhân viên: connection_workforce_01
  ├─ Kết nối SSO đối tác:   connection_partner_02
  └─ Tài khoản cục bộ dự phòng được quản trị riêng
```

Trong liên kết danh tính OIDC, cặp `issuer + subject` giúp phân biệt danh tính từ các nguồn phát hành. Quan hệ giữa danh tính đó và tenant vẫn cần được ứng dụng xác lập, thay vì suy ra chỉ từ email trùng nhau.

## 3. Thiết kế một tenant identifier ổn định

### 3.1. Tách khóa nội bộ khỏi tên hiển thị và slug

Tên công ty có thể đổi. Slug trên URL có thể đổi vì thương hiệu, trùng tên hoặc yêu cầu sản phẩm. Tenant identifier nên duy trì ổn định để quyền truy cập, dữ liệu và lịch sử kiểm toán tiếp tục tham chiếu đúng đối tượng.

```text
id:           tnt_7c91a2
display_name: Công ty Sao Mai
slug:         sao-mai
status:       ACTIVE
```

Nếu công ty đổi tên thành Sao Mai Group, chỉ cần thay tên hiển thị và slug theo quy trình của ứng dụng. Không cần đổi mọi khóa ngoại hay viết lại toàn bộ quyền của tenant.

Đường dẫn có thể dùng slug để dễ đọc, nhưng phía máy chủ phải ánh xạ slug thành tenant identifier chuẩn trước khi kiểm tra quyền hoặc truy cập dữ liệu.

### 3.2. Các thuộc tính nên có

Một hợp đồng định danh tenant cần nêu rõ:

- **Duy nhất trong phạm vi sử dụng:** không có hai tenant khác nhau cùng một khóa trong registry mà các dịch vụ đang dùng.
- **Ổn định:** đổi tên, thay domain hay thay IdP không tự làm đổi khóa.
- **Có định dạng xác định:** kiểu dữ liệu, độ dài, ký tự hợp lệ và quy tắc phân biệt chữ hoa/chữ thường phải nhất quán.
- **Không chứa ý nghĩa nhạy cảm:** tránh nhúng tên cá nhân, email hoặc thông tin kinh doanh vào khóa.
- **Được cấp phát có kiểm soát:** thao tác tạo tenant phải kiểm tra tính duy nhất và lưu thành công trước khi cấp quyền sử dụng.
- **Có vòng đời rõ ràng:** phân biệt tenant hoạt động, tạm khóa, đang xóa và đã xóa.

Có thể dùng UUID hoặc một cơ chế sinh mã phù hợp với kiến trúc. Dù thuật toán có xác suất va chạm rất thấp, ràng buộc duy nhất trong nơi lưu registry vẫn là lớp bảo vệ cần thiết.

Mã khó đoán giúp giảm khả năng liệt kê trực tiếp, nhưng không thay thế kiểm tra quyền. Một UUID hợp lệ bị lộ trong URL hoặc log vẫn không được biến thành vé truy cập.

Nên tránh tái sử dụng mã của tenant đã xóa cho một tenant mới. Token cũ, sự kiện cũ hoặc dữ liệu lưu trữ còn tham chiếu mã ấy có thể bị diễn giải nhầm thành tenant mới.

### 3.3. Xác định phạm vi duy nhất giữa các môi trường

Nếu tenant identifier chỉ duy nhất trong từng môi trường, các hệ thống tổng hợp phải mang thêm ngữ cảnh môi trường.

```text
(production, tnt_7c91a2)
(staging,    tnt_7c91a2)
```

Không được dùng một khóa chỉ duy nhất cục bộ như thể đó là khóa toàn cục khi hợp nhất log, dữ liệu phân tích hoặc sự kiện giữa nhiều deployment. Cũng không để một tenant chưa được nhận diện tự động rơi vào tenant mặc định trong môi trường vận hành.

## 4. Tenant được yêu cầu và tenant đã được xác minh

Ứng dụng thường nhận thông tin tenant từ nhiều vị trí:

| Nguồn | Ví dụ | Cách hiểu ban đầu |
| --- | --- | --- |
| Hostname | `sao-mai.example.com` | Gợi ý tenant mà người dùng muốn mở |
| Đường dẫn | `/tenants/tnt_7c91a2/projects` | Tenant đích được client yêu cầu |
| Header | `X-Tenant-ID: tnt_7c91a2` | Dữ liệu do bên gửi header cung cấp |
| Body hoặc query | `tenantId=tnt_7c91a2` | Tham số đầu vào cần kiểm tra |
| Phiên phía máy chủ | Tenant đang chọn trong phiên | Ngữ cảnh đã lưu, có thể cần kiểm tra lại |
| Access token đã được chấp nhận | Claim tenant theo hợp đồng ứng dụng | Khẳng định của bên phát hành đã được xác thực, vẫn cần diễn giải và cấp quyền |

Điểm khác biệt quan trọng là **nguồn gốc và độ tin cậy**, không phải tên field. Một header có tên `X-Verified-Tenant` do client gửi vẫn chưa được xác minh.

Có thể tách hai khái niệm trong thiết kế:

```text
RequestedTenant
  Tenant mà bên gọi muốn thao tác.

AuthorizedTenantContext
  Tenant mà máy chủ đã xác định là phù hợp
  với principal, trạng thái tenant và chính sách truy cập.
```

Chỉ ngữ cảnh thứ hai mới được đưa vào các thao tác nghiệp vụ yêu cầu quyền tenant.

### 4.1. Chuỗi xử lý cho một yêu cầu

Một luồng thông thường có các bước:

1. Xác thực credential hoặc phiên để có principal đáng tin cậy.
2. Đọc và chuẩn hóa tenant đích từ vị trí mà API đã quy định.
3. Tra registry để xác định tenant tồn tại và trạng thái cho phép thao tác.
4. Kiểm tra principal có quan hệ truy cập hợp lệ với tenant đó.
5. Tạo tenant context cho đúng yêu cầu.
6. Kiểm tra quyền đối với hành động và tài nguyên trong tenant.
7. Truy cập dữ liệu đã được giới hạn bởi tenant context.

Các quan hệ ở bước 4 có thể là membership của người dùng, quyền được giao cho workload hoặc một cơ chế hỗ trợ đặc biệt đã được quản trị. Không nên ép mọi principal thành người dùng có membership thông thường.

Đối với các endpoint chưa có principal, như trang đăng nhập hoặc trang giới thiệu workspace công khai, tenant từ URL có thể phục vụ định tuyến hoặc chọn giao diện. Việc tìm được tenant ở giai đoạn này không được cấp quyền truy cập dữ liệu riêng của tenant.

### 4.2. Không âm thầm xử lý các nguồn mâu thuẫn

Giả sử:

```text
Đường dẫn: /tenants/tnt_7c91a2/projects
Token bị ràng buộc với tenant: tnt_b03f84
```

Nếu token chỉ có hiệu lực cho một tenant, máy chủ phải từ chối yêu cầu mâu thuẫn này. Không lấy tenant ở token để ghi dữ liệu nhưng lấy tenant ở URL để tạo cache key hoặc ghi audit.

Nếu sản phẩm dùng token danh tính chung và tra membership theo từng yêu cầu, tenant trong đường dẫn có thể chọn phạm vi thao tác. Đây là một hợp đồng khác và phải được thiết kế rõ ràng.

Hãy chọn một quy tắc nhất quán, thay vì để từng controller tự quyết định ưu tiên path, token hoặc header.

## 5. Tenant identifier trong token và phiên đăng nhập

### 5.1. Claim tenant không tự trở thành quyền truy cập

Ví dụ payload của một access token do ứng dụng quy định:

```json
{
  "iss": "https://identity.example.com/",
  "sub": "user_82a6",
  "aud": "project-api",
  "exp": 2000000000,
  "tenant_id": "tnt_7c91a2",
  "scope": "projects:read"
}
```

`tenant_id` trong ví dụ là claim theo hợp đồng của hệ thống; không phải mọi access token đều có claim này hoặc dùng cùng tên và ý nghĩa.

API cần chấp nhận đúng loại access token và thực hiện validation theo cơ chế đã thống nhất, chẳng hạn xác minh chữ ký và thuật toán được cho phép đối với JWT, issuer, audience, thời hạn cùng các điều kiện liên quan. Chỉ giải mã payload là chưa đủ. Không dùng ID token như một access token của API.

Sau khi token hợp lệ, máy chủ vẫn phải kiểm tra:

- Bên phát hành có được tin cậy để khẳng định tenant này không?
- Tenant trong token có khớp tenant đích của yêu cầu không?
- Tenant có đang được phép hoạt động không?
- Scope, vai trò hoặc policy có cho phép hành động cụ thể không?
- Tài nguyên có thực sự thuộc tenant đó không?
- Quyền trong token có còn phù hợp với cơ chế thu hồi và độ trễ quyền mà hệ thống chấp nhận không?

Một token có chữ ký hợp lệ nhưng dành cho API khác không được trở thành nguồn tenant context hợp lệ cho API hiện tại.

### 5.2. Hai mô hình chọn tenant thường gặp

| Mô hình | Cách hoạt động | Điểm cần xử lý |
| --- | --- | --- |
| Phiên hoặc token gắn với một tenant | Người dùng chọn tenant, máy chủ tạo ngữ cảnh hoặc cấp token cho tenant đó | Chuyển tenant cần xác minh lại; token cũ không đổi ý nghĩa |
| Danh tính chung, chọn tenant theo yêu cầu | API nhận tenant đích và kiểm tra quyền truy cập tenant cho từng yêu cầu | Mọi đường vào phải dùng cùng cơ chế xác lập tenant context |

Với người dùng thuộc nhiều tenant, không nên mặc định đưa mọi quyền của mọi tenant vào một tập vai trò không có phạm vi. Ví dụ `ADMIN` ở tenant A không được hiểu thành `ADMIN` ở tenant B.

Nếu lưu tenant đang chọn trong phiên phía máy chủ, cần đặc biệt chú ý nhiều tab trình duyệt. Tab A có thể đang mở tenant A trong khi tab B chuyển phiên sang tenant B. Endpoint thay đổi dữ liệu nên kiểm tra tenant đích cụ thể và tính nhất quán với ngữ cảnh phiên, để thao tác từ tab cũ không âm thầm ghi vào tenant khác.

Khi membership bị thu hồi hoặc tenant bị khóa, thiết kế phải quy định quyền mất hiệu lực khi nào. Token còn hạn hoặc cache membership cũ có thể làm quyền tiếp tục tồn tại trong một khoảng thời gian nếu không có cơ chế kiểm tra hoặc vô hiệu hóa tương ứng.

## 6. Gắn tenant vào mô hình quyền và truy cập dữ liệu

### 6.1. Membership là quan hệ có phạm vi tenant

Một mô hình tối giản có thể là:

```text
Tenant(id, status, ...)
User(id, ...)
Membership(tenant_id, user_id, status, ...)
RoleAssignment(tenant_id, user_id, role_id, ...)
Project(tenant_id, id, name, ...)
```

Tùy hệ thống, role definition có thể dùng chung hoặc do từng tenant tạo. Tuy vậy, một role assignment cấp cho người dùng trong tenant nào phải có phạm vi rõ ràng.

Ví dụ với Lan:

```text
(tnt_7c91a2, user_lan, ADMIN)
(tnt_b03f84, user_lan, VIEWER)
```

Không gom thành:

```text
user_lan -> [ADMIN, VIEWER]
```

Dạng thứ hai đánh mất thông tin tenant và có thể làm lan quyền quản trị sang phạm vi khác.

### 6.2. Truy vấn tài nguyên phải ràng buộc tenant

Ví dụ truy vấn dùng tham số:

```sql
SELECT id, name
FROM projects
WHERE tenant_id = :authorized_tenant_id
  AND id = :project_id;
```

`:authorized_tenant_id` phải lấy từ tenant context do máy chủ xác lập, không lấy nguyên giá trị tùy ý trong body.

Truy vấn trên ngăn việc tìm một dự án thuộc tenant khác trong phạm vi truy vấn này, nhưng chưa tự chứng minh quyền đọc dự án. Quyền theo vai trò, chủ sở hữu hoặc policy vẫn phải được kiểm tra.

Các thao tác `UPDATE`, `DELETE`, đếm bản ghi, export và tìm kiếm cũng phải giữ cùng ràng buộc. Chỉ bảo vệ màn hình danh sách mà bỏ qua endpoint tải file hoặc endpoint cập nhật là chưa đủ.

Khi tạo tài nguyên:

```text
project.tenant_id = authorizedTenantContext.tenantId
```

Nếu API cho phép client truyền `tenant_id` trong body, hãy quy định rõ cách kiểm tra với tenant đích. Không dùng cơ chế tự động bind mọi field của body để ghi đè tenant đã được máy chủ xác lập.

### 6.3. Bảo vệ quan hệ giữa các tài nguyên

Giả sử task tham chiếu project. Chỉ kiểm tra task có tenant đúng chưa đủ nếu `project_id` lại trỏ sang project của tenant khác.

Một thiết kế quan hệ có thể dùng:

```text
Project:
  UNIQUE (tenant_id, id)

Task:
  FOREIGN KEY (tenant_id, project_id)
    REFERENCES Project (tenant_id, id)
```

Cú pháp triển khai phụ thuộc cơ sở dữ liệu và cấu trúc khóa thực tế. Ý nghĩa cần giữ là task và project được ràng buộc về cùng tenant, thay vì chỉ trông chờ mọi đoạn code đều nhớ kiểm tra.

Các cơ chế bổ sung như phân vùng lưu trữ, schema riêng hoặc row-level security có thể tăng khả năng cô lập. Chúng cần cấu hình và kiểm thử theo kiến trúc thực tế; việc có một cột `tenant_id` không tự tạo ra tenant isolation.

## 7. Ví dụ luồng xử lý ở tầng ứng dụng

Pseudocode theo phong cách Java:

```java
record AuthorizedTenantContext(
    String tenantId,
    Principal principal
) {}

ProjectView readProject(
    HttpRequest request,
    String requestedTenantId,
    String projectId
) {
    Principal principal = authentication.requirePrincipal(request);

    Tenant tenant = tenantRegistry.requireActive(
        tenantIds.parseCanonical(requestedTenantId)
    );

    AuthorizedTenantContext context =
        tenantAccess.requireContext(principal, tenant);

    Project project = projectRepository
        .findByTenantAndId(context.tenantId(), projectId)
        .orElseThrow(this::notFound);

    authorization.require(context, "project:read", project);

    return projectViews.forAuthorizedReader(context, project);
}
```

Đây là ví dụ kiến trúc, không phải mã hoàn chỉnh để chạy trực tiếp. Các hàm `requireContext` và `authorization.require` đại diện cho kiểm tra bắt buộc của hệ thống.

Các điểm cần quan sát:

1. Tenant đầu vào được parse theo định dạng quy định.
2. Principal đến từ cơ chế xác thực.
3. Quyền truy cập tenant được kiểm tra trước khi truy vấn dữ liệu nghiệp vụ.
4. Repository nhận tenant đã được xác lập cùng project ID.
5. Quyền đọc được kiểm tra trước khi trả dữ liệu.

API cần có chính sách nhất quán khi tài nguyên không tồn tại hoặc người gọi không được phép biết nó tồn tại. Có hệ thống trả `404` để hạn chế tiết lộ sự tồn tại, có hệ thống sử dụng `403` theo hợp đồng sản phẩm. Dù chọn cách nào, không được trả nội dung của tenant khác hoặc ghi thông tin nhạy cảm vào thông báo lỗi.

Tenant context nên được truyền tường minh hoặc qua cơ chế request context có vòng đời được kiểm soát. Nếu dùng thread-local, phải dọn sau yêu cầu và xử lý đúng việc chuyển luồng, executor hoặc reactive context; không giả định tác vụ bất đồng bộ tự nhận được ngữ cảnh an toàn.

## 8. Duy trì tenant context ngoài HTTP request

### 8.1. Cache

Một khóa cache chỉ có project ID có thể làm hai tenant dùng chung kết quả khi ID chỉ duy nhất trong tenant.

```text
Không đủ trong mô hình ID cục bộ:
  project:42

Có phạm vi tenant:
  tenant:tnt_7c91a2:project:42
```

Ngay cả khi project ID duy nhất toàn hệ thống, việc đặt tenant vào cache key vẫn có thể giúp thể hiện và quản lý phạm vi. Tuy nhiên, cache key chứa tenant không thay thế kiểm tra quyền trước khi trả giá trị.

Đối với cache quyền, thường phải xét cả tenant, principal và những thông tin ảnh hưởng đến policy. Khi membership hoặc policy đổi, phải có cơ chế hết hạn hoặc vô hiệu hóa phù hợp.

### 8.2. Tác vụ nền và hàng đợi

Một job cần mang tenant đích rõ ràng:

```json
{
  "job_id": "job_319",
  "tenant_id": "tnt_7c91a2",
  "operation": "EXPORT_PROJECTS",
  "requested_by": "user_lan"
}
```

Payload này chỉ mô tả dữ liệu nghiệp vụ, chưa đủ để chứng minh job hợp lệ. Consumer cần dựa vào danh tính producer, quyền gửi thông điệp và hợp đồng xử lý để tin cậy nguồn job.

Khi thực thi, cần xác định ai là chủ thể có quyền:

- Job chạy thay mặt người dùng theo quyền còn hiệu lực tại thời điểm thực thi.
- Job chạy bằng workload identity đã được cấp quyền cho tenant.
- Job chạy theo một cơ chế ủy quyền có thời hạn và phạm vi cụ thể.

Đây là lựa chọn nghiệp vụ và bảo mật phải được công bố trong thiết kế. Không coi `requested_by` do bên gửi tự khai là bằng chứng ủy quyền.

Consumer phải thiết lập tenant context cho mỗi job và dọn sau khi xử lý, kể cả khi job thất bại hoặc retry. Tránh giữ tenant của job trước trong tiến trình xử lý job kế tiếp.

### 8.3. File, tìm kiếm và liên lạc giữa dịch vụ

Object storage, chỉ mục tìm kiếm, đường dẫn export và kênh thông báo cũng cần ràng buộc tenant. Một object key như `tenants/{tenant_id}/exports/{file_id}` hỗ trợ tổ chức lưu trữ, nhưng quyền tải file vẫn phải được xác minh trước khi cấp link hoặc trả dữ liệu.

Khi truyền tenant context giữa các dịch vụ, dịch vụ nhận phải xác thực bên gọi và nguồn ngữ cảnh theo mô hình tin cậy. Nếu gateway gắn header nội bộ, nó cần loại bỏ giá trị do client giả mạo; các dịch vụ phía sau cũng phải được bảo vệ khỏi đường truy cập bỏ qua gateway.

Không để một dịch vụ có quyền rộng thực hiện yêu cầu cho tenant tùy ý chỉ vì caller gửi được `tenant_id`. Đây là tình huống dịch vụ có đặc quyền bị lợi dụng để thao tác ngoài phạm vi mà caller được phép.

## 9. Tenant identifier trong kiểm toán và vận hành

Audit cần ghi lại cả chủ thể và phạm vi thao tác:

```text
actor_id=user_lan
tenant_id=tnt_7c91a2
action=project.delete
resource_id=project_42
decision=DENY
request_id=req_8f12
```

Đối với hỗ trợ khách hàng hoặc quản trị nền tảng, cần phân biệt:

- Danh tính nhân viên thực hiện thao tác.
- Tenant khách hàng bị tác động.
- Cơ chế cấp quyền đặc biệt và phạm vi được cấp.
- Danh tính được đại diện, nếu có.
- Lý do, thời hạn và kết quả thao tác khi cơ chế đó yêu cầu.

Không biến tài khoản hỗ trợ thành thành viên quản trị của mọi tenant chỉ để bỏ qua việc mô hình hóa quyền đặc biệt. Cũng không tạo một mã tenant giả như `ALL` rồi cho mọi tầng hiểu đó là quyền truy cập toàn cục.

Tenant identifier thường xuất hiện trên URL và log nên không được coi là secret. Dù vậy, nó vẫn là metadata có thể liên kết hoạt động với khách hàng; quyền xem log và khả năng tìm kiếm chéo tenant cần được quản trị. Không ghi token hoặc credential vào log để phục vụ việc tra tenant.

## 10. Các tình huống cần kiểm tra

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Thành viên tenant A thay path thành tenant B | Không truy cập được B nếu chưa có quyền tương ứng |
| Quản trị viên A đồng thời là người xem B | Quyền quản trị A không được áp dụng ở B |
| Token bị ràng buộc với A nhưng request chỉ đến B | Bị từ chối theo hợp đồng token và API |
| Body tạo project chứa tenant khác tenant context | Bị từ chối hoặc xử lý theo quy tắc rõ ràng; không ghi sang tenant kia |
| Project ID của B xuất hiện trong request thuộc A | Không trả hoặc sửa project của B |
| Task thuộc A tham chiếu project thuộc B | Bị chặn bởi kiểm tra nghiệp vụ và ràng buộc dữ liệu phù hợp |
| Hai tab đang dùng hai tenant khác nhau | Thao tác từ tab cũ không âm thầm chuyển tenant đích |
| Membership bị thu hồi nhưng token còn hạn | Hành vi đúng với cơ chế thu hồi và độ trễ quyền đã quy định |
| Job A chạy lỗi rồi consumer nhận job B | Job B không thừa hưởng tenant context của A |
| Client tự thêm header tenant nội bộ | Không được coi là ngữ cảnh đã xác minh |
| Tenant bị khóa hoặc xóa | Thao tác bị chặn theo vòng đời tenant; mã không được gán nhầm cho tenant mới |
| Cache hoặc endpoint export được dùng chéo tenant | Không rò dữ liệu hoặc quyền giữa các tenant |

Các tình huống này giúp nhận ra ranh giới trách nhiệm của tenant identifier: mã tenant phải đi cùng principal, chính sách cấp quyền và ràng buộc tài nguyên. Khi ba phần được nối nhất quán qua toàn bộ luồng xử lý, tenant identifier mới thực sự hỗ trợ cô lập quyền và dữ liệu trong hệ thống IAM nhiều tenant.
