# Tenant-scoped policy

## 1. Chính sách phải trả lời cả câu hỏi “trong tenant nào?”

Trong một hệ thống nhiều tenant, biết người gọi là ai và có vai trò gì vẫn chưa đủ để quyết định quyền truy cập. Hệ thống còn phải biết quyền đó có hiệu lực trong tenant nào, đối với tài nguyên nào và trong điều kiện nào.

Giả sử một ứng dụng quản lý dự án phục vụ hai khách hàng:

- Tenant `alpha` có dự án `project-101`.
- Tenant `beta` có dự án `project-202`.
- An là quản trị viên trong `alpha`, nhưng chỉ là người xem trong `beta`.

Nếu ứng dụng chỉ kiểm tra `role == "admin"`, quyền quản trị của An tại `alpha` có thể bị hiểu nhầm thành quyền quản trị trên toàn hệ thống. Ngay cả khi đã xác thực đúng An, quyết định phân quyền vẫn sai vì bỏ qua phạm vi tenant.

**Tenant-scoped policy** là chính sách mà việc cấp quyền và đánh giá quyền được ràng buộc với một tenant xác định. Câu hỏi phân quyền đầy đủ là:

> Chủ thể này có được thực hiện hành động này trên tài nguyên này, trong tenant này, với ngữ cảnh hiện tại hay không?

Tenant-scoped policy giúp bảo vệ ranh giới giữa khách hàng trong cùng nền tảng. Nó phải được thực thi tại nơi truy cập thực sự xảy ra, không chỉ thể hiện bằng bộ lọc trên giao diện.

## 2. Mô hình của một quyết định phân quyền

Một quyết định có thể được mô tả bằng bộ dữ liệu:

```text
authorize(subject, action, resource, tenant, context)
```

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `subject` | Người dùng hoặc workload đã được xác thực | An hoặc dịch vụ xuất báo cáo |
| `action` | Hành động được yêu cầu | `project.read`, `project.update` |
| `resource` | Tài nguyên đích và thuộc tính đáng tin cậy của nó | Dự án `project-101` thuộc `alpha` |
| `tenant` | Phạm vi đang được đánh giá | `alpha` |
| `context` | Điều kiện liên quan đến quyết định | Phiên, thời gian, trạng thái cấp quyền |

Với một API chỉ phục vụ tài nguyên nội bộ tenant, có thể khái quát điều kiện cho phép như sau:

```text
ALLOW khi đồng thời:
    chủ thể đã được xác thực hợp lệ
    tenant đích đã được xác định và đang hợp lệ
    chủ thể có quan hệ truy cập còn hiệu lực trong tenant đích
    tài nguyên thuộc tenant đích
    chính sách của tenant cho phép hành động
    không có điều kiện từ chối áp dụng

Còn lại: DENY
```

“Quan hệ truy cập” có thể là membership của người dùng, binding của workload hoặc một ủy quyền được định nghĩa rõ. Không nên giả định mọi chủ thể đều là nhân viên trong một tenant.

Mô hình trên dành cho truy cập nội bộ tenant. Chia sẻ tài nguyên liên tenant hoặc quản trị nền tảng cần có luồng chính sách riêng, thay vì âm thầm bỏ một điều kiện trong mô hình này.

## 3. Xác định tenant từ nguồn nào?

Tenant thường xuất hiện trong đường dẫn, subdomain, header, phiên hoặc token. Điểm quan trọng là phân biệt **tenant được yêu cầu** với **tenant mà chủ thể được phép truy cập**.

Ví dụ:

```http
GET /tenants/alpha/projects/project-101
Authorization: Bearer <access-token>
```

Đường dẫn cho biết người gọi muốn làm việc trong `alpha`. Nó không chứng minh người gọi là thành viên của `alpha`.

| Nguồn | Có thể cho biết điều gì? | Điều không được mặc định |
| --- | --- | --- |
| Path, query, header do client gửi | Tenant người gọi lựa chọn | Người gọi có quyền trong tenant đó |
| Subdomain đã được hệ thống định tuyến và ánh xạ | Tenant tương ứng với địa chỉ ứng dụng | Mọi người truy cập địa chỉ đều là thành viên |
| Thuộc tính trong token đã được kiểm tra hợp lệ | Thông tin mà bên phát hành được tin cậy đã xác nhận | Thuộc tính đó luôn có cùng ý nghĩa ở mọi issuer hoặc mọi ứng dụng |
| Membership/binding từ kho quyền đáng tin cậy | Quan hệ hiện tại giữa chủ thể và tenant | Quan hệ này cho phép mọi hành động trong tenant |
| `tenant_id` của tài nguyên trong kho dữ liệu | Tài nguyên thuộc tenant nào | Chỉ cần biết ID tài nguyên là được truy cập |

Nếu tenant xuất hiện ở nhiều nơi, ứng dụng cần quy tắc nhất quán. Chẳng hạn, endpoint yêu cầu token gắn với một tenant cụ thể phải kiểm tra tenant trong đường dẫn phù hợp với tenant của token. Không được tự chọn một nguồn bất kỳ khi các nguồn mâu thuẫn.

Một hệ thống khác có thể cho phép cùng một phiên chọn giữa nhiều tenant mà người dùng có membership. Khi đó, việc đổi tenant phải tạo ngữ cảnh hợp lệ cho tenant mới và đánh giá quyền lại, thay vì mang nguyên vai trò của tenant cũ sang.

Đối với API, sử dụng loại token được thiết kế cho truy cập API và kiểm tra theo mô hình xác thực của hệ thống. Không coi một ID token dùng cho đăng nhập là bằng chứng phân quyền API mặc định.

## 4. Ràng buộc danh tính và vai trò với tenant

### 4.1. Danh tính toàn cục và quyền cục bộ là hai việc khác nhau

Một người có thể có một danh tính dùng trên nền tảng nhưng nhiều membership với vai trò khác nhau:

```text
subject = (trusted-issuer, subject-id)

membership:
    (subject, alpha) -> project-admin
    (subject, beta)  -> project-viewer
```

Trong hệ thống liên kết danh tính, định danh chủ thể cần được diễn giải cùng nguồn phát hành đã được tin cậy. Không ghép người dùng từ các nguồn khác nhau chỉ vì chuỗi `subject-id` hoặc email giống nhau.

Email có thể là thuộc tính liên hệ hoặc phục vụ một quy trình mời thành viên, nhưng không nên tự động trở thành khóa duy nhất để suy ra quyền liên tenant. Việc liên kết danh tính cần một quy trình có kiểm soát.

### 4.2. Role assignment phải chứa phạm vi

Một role assignment thiếu tenant dễ dẫn đến quyền toàn cục ngoài ý muốn:

```text
Không đủ phạm vi:
    subject = an
    role = project-admin

Có phạm vi:
    subject = an
    tenant = alpha
    role = project-admin
    status = active
```

Tên vai trò giống nhau ở hai tenant không nhất thiết có cùng tập quyền. Nếu tenant được phép tùy chỉnh vai trò, định danh vai trò phải bao gồm namespace tenant hoặc sử dụng định danh duy nhất có liên kết tenant rõ ràng.

Trong RBAC, hệ thống đánh giá vai trò được gán cho chủ thể **ở tenant đang xét**. Trong ABAC, điều kiện phải dùng các thuộc tính tenant và quan hệ đáng tin cậy. Cả hai cách đều cần kiểm tra tài nguyên thuộc đúng phạm vi.

### 4.3. Quản trị viên tenant không phải quản trị viên nền tảng

Quyền tạo thành viên, sửa vai trò hoặc đổi cấu hình trong `alpha` không mặc nhiên cho phép thao tác tương tự trong `beta` hoặc thay đổi chính sách của nền tảng.

Nếu quản trị viên tenant được tạo vai trò tùy chỉnh, phải giới hạn những quyền họ có thể đưa vào vai trò. Không cho phép họ gán quyền quản trị nền tảng, đổi tenant sở hữu tài nguyên hoặc sửa dữ liệu kiểm soát ranh giới chỉ bằng một cập nhật nghiệp vụ thông thường.

## 5. Ví dụ chính sách theo phạm vi tenant

Ví dụ dưới đây mô tả ý tưởng chính sách. Đây là cấu trúc minh họa, không phải cú pháp của một policy engine cụ thể.

```yaml
policyId: alpha-project-update
policyTenant: alpha
defaultDecision: DENY
allowWhenAll:
  - subject.authenticated == true
  - request.tenant == policyTenant
  - binding.subject == subject.id
  - binding.tenant == policyTenant
  - binding.status == active
  - binding.role == project-admin
  - resource.tenant == policyTenant
  - request.action == project.update
  - resource.state != archived
```

Để thực thi an toàn ý tưởng này, dữ liệu đầu vào phải có nguồn rõ ràng:

- `subject.authenticated` do thành phần xác thực cung cấp sau khi kiểm tra bằng chứng đăng nhập.
- `binding` được lấy từ kho quyền hoặc nguồn cấp quyền đã được xác minh, không lấy từ role mà client tự khai báo.
- `resource.tenant` và `resource.state` được lấy từ dữ liệu phía server.
- `request.tenant` là tenant đã qua bước xác lập ngữ cảnh và kiểm tra quan hệ truy cập.
- `request.action` do endpoint và nghiệp vụ xác định, không cho client tùy ý biến một thao tác cập nhật thành một thao tác đọc.

Thiếu thuộc tính bắt buộc, không xác định được tenant hoặc không tìm thấy binding hợp lệ phải dẫn đến từ chối. Ví dụ, một tài nguyên thiếu `tenant_id` không được coi là tài nguyên “dùng chung cho tất cả”.

Chính sách dùng cho toàn nền tảng có thể cung cấp các điều kiện nền bắt buộc. Chính sách tenant chỉ được tùy chỉnh trong phạm vi được cấp. Cần định nghĩa rõ cách kết hợp các chính sách, đặc biệt khi có cả điều kiện cho phép và từ chối; không dựa vào thứ tự ngẫu nhiên của các bản ghi.

## 6. Luồng thực thi trên một API

Với yêu cầu cập nhật dự án, luồng xử lý có thể là:

```text
Request
   |
   v
Kiểm tra thông tin xác thực -> subject đáng tin cậy
   |
   v
Xác lập tenant đích + kiểm tra membership/binding
   |
   v
Tải tài nguyên bằng tenant + resource ID
   |
   v
Đánh giá action + vai trò + thuộc tính + điều kiện
   |
   v
Thực hiện thay đổi trong cùng phạm vi đã kiểm tra
   |
   v
Ghi nhật ký quyết định và kết quả
```

Mã giả:

```text
updateProject(request):
    subject = authentication.requireValidApiPrincipal(request)
    tenant = tenantResolver.resolveCanonicalTenant(request.path.tenant)

    binding = bindings.requireActive(subject.id, tenant.id)

    project = projects.findByTenantAndId(
        tenant.id,
        request.path.projectId
    )
    require project exists

    decision = policy.evaluate(
        subject = subject,
        binding = binding,
        tenant = tenant,
        action = "project.update",
        resource = project,
        context = trustedRequestContext(request)
    )
    require decision == ALLOW

    changes = parseAllowedProjectChanges(request.body)
    projects.updateWithinTenant(tenant.id, project.id, changes)
    audit.recordDecisionAndOutcome(subject, tenant, project, decision)
```

Đây là mã giả về thứ tự kiểm tra, chưa mô tả đầy đủ giao dịch, xử lý lỗi hay cơ chế ghi nhật ký khi bị từ chối.

Một vài chi tiết quyết định chất lượng của thiết kế:

- Việc tải tài nguyên đã gắn với tenant. Không tải tùy ý một tài nguyên của tenant khác rồi trả dữ liệu trước khi kiểm tra.
- Nội dung cập nhật chỉ gồm các trường được phép. Client không được tự sửa `tenant_id`, chủ sở hữu hoặc trường quyền nhạy cảm qua cơ chế gán hàng loạt.
- Lệnh ghi tiếp tục chứa điều kiện tenant và ID; không đánh giá có phạm vi rồi thực hiện một lệnh ghi chỉ dựa trên dữ liệu chưa kiểm soát.
- Nếu có thay đổi đồng thời về trạng thái hoặc quyền, thiết kế giao dịch và kiểm tra phiên bản phải bảo vệ các điều kiện mà nghiệp vụ yêu cầu tại thời điểm ghi.
- Phản hồi lỗi cần nhất quán với chính sách chống lộ sự tồn tại của tài nguyên. Không trả thông tin nhạy cảm về tài nguyên thuộc tenant khác chỉ để giải thích vì sao bị từ chối.

Thành phần thực thi chính sách tại API hoặc service thường được gọi là điểm thực thi chính sách. Thành phần đưa ra quyết định có thể nằm trong cùng ứng dụng hoặc một dịch vụ chính sách riêng. Dù bố trí thế nào, trách nhiệm bảo vệ tài nguyên không được dừng ở việc giao diện đã ẩn nút thao tác.

## 7. Áp dụng ranh giới tenant xuống dữ liệu

Chính sách ở tầng ứng dụng và cơ chế cách ly dữ liệu cần bổ trợ nhau. Một truy vấn quên tenant vẫn có thể gây rò rỉ dù phần lớn endpoint khác kiểm tra đúng.

Ví dụ truy vấn có phạm vi:

```sql
SELECT id, name, state
FROM projects
WHERE tenant_id = :authorized_tenant
  AND id = :project_id;
```

Trong đó `authorized_tenant` được lấy từ ngữ cảnh đã được kiểm tra phía server, không chỉ sao chép một header của client.

Với thao tác ghi:

```sql
UPDATE projects
SET name = :new_name
WHERE tenant_id = :authorized_tenant
  AND id = :project_id
  AND version = :expected_version;
```

Ứng dụng phải kiểm tra kết quả cập nhật và xử lý trường hợp không có bản ghi phù hợp. Tham số `expected_version` minh họa một cơ chế phát hiện thay đổi đồng thời; chi tiết phụ thuộc hệ thống.

Khi tạo tài nguyên mới, server gán tenant từ ngữ cảnh đã được cho phép. Những đối tượng được tham chiếu — dự án cha, nhóm, thành viên hoặc thư mục — cũng cần được kiểm tra thuộc cùng phạm vi hoặc có quan hệ chia sẻ được cho phép.

Các khóa duy nhất và quan hệ dữ liệu có thể cần bao gồm tenant. Chẳng hạn, nếu mã dự án chỉ duy nhất trong từng tenant thì khóa nghiệp vụ là `(tenant_id, project_code)`. Quan hệ giữa hai bảng cũng cần tránh việc một bản ghi của tenant A tham chiếu trái phép đến bản ghi của tenant B.

Nếu dùng cơ chế kiểm soát ở cơ sở dữ liệu, cần xác lập đúng ngữ cảnh cho mỗi lần sử dụng kết nối và tránh để ngữ cảnh tenant cũ tồn tại khi tái sử dụng kết nối. Cơ chế cụ thể phải được thiết kế theo công nghệ đang dùng; nó không thay thế việc kiểm tra hành động nghiệp vụ ở tầng IAM.

Ranh giới tương tự áp dụng cho tìm kiếm, file, báo cáo, bản xuất dữ liệu và nội dung tải xuống. Một endpoint đọc dự án đúng phạm vi nhưng tạo liên kết tải file của tenant khác vẫn là vi phạm ranh giới tenant.

## 8. Cache, batch và tác vụ nền

### 8.1. Cache quyết định phải chứa tenant

Khóa cache dạng `(subject, action, resourceId)` có thể không đủ nếu vai trò, ID tài nguyên hoặc chính sách có ý nghĩa theo tenant.

Một khóa minh họa có thể bao gồm:

```text
subject-identity
+ tenant-id
+ action
+ resource-identity
+ relevant-policy-version
+ relevant-authorization-version
+ các điều kiện ngữ cảnh ảnh hưởng quyết định
```

Không phải hệ thống nào cũng dùng đúng tất cả trường trên, nhưng mọi yếu tố có thể làm thay đổi quyết định phải được xử lý bằng khóa, thời hạn hoặc cơ chế vô hiệu hóa phù hợp. Không dùng lại kết quả `ALLOW` tại `alpha` cho `beta`.

Cache dữ liệu cũng cần phạm vi tenant. Cách ly quyết định phân quyền không có ích nếu phản hồi sau đó lấy nhầm dữ liệu từ cache của khách hàng khác.

### 8.2. Batch phải kiểm tra toàn bộ đối tượng

Với một yêu cầu cập nhật nhiều dự án, không chỉ kiểm tra tenant của dự án đầu tiên. Có thể truy vấn tất cả ID trong tenant đã xác thực và xác nhận đủ các đối tượng cần xử lý trước khi ghi.

Nếu API chỉ cho phép một tenant mỗi request, đầu vào chứa đối tượng thuộc tenant khác phải được xử lý theo quy tắc lỗi đã định nghĩa. Không tự đổi tenant giữa các phần tử của batch.

### 8.3. Tác vụ nền cần mang theo ngữ cảnh có kiểm soát

Một job xuất báo cáo cần biết tenant nào, tài nguyên nào, ai yêu cầu và danh tính workload nào thực hiện. Không lấy tenant từ một biến toàn cục hoặc từ request gần nhất mà worker xử lý.

Thông điệp gửi vào hàng đợi có thể mang định danh tenant và chủ thể, nhưng bên xử lý vẫn phải xác minh nguồn gửi và đánh giá quyền theo thiết kế. Một trường `tenant_id` trong thông điệp không tự trở thành bằng chứng cấp quyền.

Cần xác định tác vụ được đánh giá quyền lúc tiếp nhận, lúc thực thi hay ở cả hai thời điểm. Với tác vụ chạy sau khi membership đã bị thu hồi, hệ thống phải có cách xử lý đã được định nghĩa; không mặc định quyền cũ có hiệu lực vô hạn.

Khi một workload có khả năng truy cập nhiều tenant, mỗi thao tác vẫn cần phạm vi rõ ràng. Quyền rộng của workload không phải lý do để tin mọi tenant hoặc resource ID do client gửi tới.

## 9. Chia sẻ liên tenant và quản trị nền tảng

Một số sản phẩm cần cho tenant A chia sẻ tài nguyên cho một đối tác trong tenant B. Đây là yêu cầu có chủ đích, không phải lỗi trong điều kiện so sánh tenant cần bỏ qua cho tiện.

Chính sách chia sẻ cần mô tả rõ:

- Tenant nào sở hữu tài nguyên.
- Chủ thể hoặc tenant nào được nhận quyền.
- Hành động nào được phép và điều kiện nào áp dụng.
- Quyền có được chuyển tiếp hay không.
- Khi nào quyền hết hạn hoặc bị thu hồi.
- Nhật ký thể hiện bên sở hữu, bên sử dụng và hành động thực tế như thế nào.

Một tài nguyên được chia sẻ quyền đọc không trở thành tài nguyên thuộc tenant của người nhận. Các thao tác cập nhật, tải xuống hoặc chia sẻ tiếp vẫn phải được đánh giá riêng.

Tương tự, nhân viên hỗ trợ nền tảng có thể cần truy cập tenant theo yêu cầu hỗ trợ. Quyền này nên có đường cấp phát riêng, phạm vi rõ, thời hạn phù hợp và nhật ký truy vết được. Không dùng một điều kiện chung như `isAdmin == true` để bỏ mọi kiểm tra tenant trong các API thông thường.

Việc quản lý cấu hình nền tảng và việc truy cập dữ liệu khách hàng cũng là hai phạm vi cần phân biệt. Một vai trò có quyền vận hành hạ tầng không nên tự động được diễn giải thành quyền đọc mọi dữ liệu nghiệp vụ.

## 10. Vòng đời chính sách, membership và phiên

Tenant-scoped policy không chỉ có ý nghĩa lúc cấp quyền ban đầu. Những sự kiện sau đều có thể làm thay đổi quyết định:

- Người dùng bị xóa khỏi tenant hoặc chuyển vai trò.
- Workload hết nhu cầu truy cập một tenant.
- Một vai trò tùy chỉnh thay đổi tập quyền.
- Tenant bị đình chỉ hoạt động.
- Tài nguyên chuyển trạng thái, được chia sẻ hoặc bị thu hồi chia sẻ.
- Chính sách nền của nền tảng thay đổi.

Hệ thống cần đồng bộ thay đổi đến các điểm đánh giá, xử lý cache và kiểm soát phiên/token còn tồn tại. Nếu quyền được ghi vào token, phải hiểu thông tin đó có thể tồn tại đến khi token hết hiệu lực hoặc được xử lý bằng cơ chế thu hồi/kiểm tra bổ sung của hệ thống.

Không nên hứa rằng xóa membership làm mọi quyền mất ngay lập tức nếu kiến trúc thực tế chưa bảo đảm điều đó. Yêu cầu về thời gian thu hồi phải được chuyển thành thiết kế cụ thể và được kiểm chứng.

Việc đổi tenant sở hữu tài nguyên cũng không phải một thao tác sửa trường thông thường. Nó có thể ảnh hưởng quyền, quan hệ tham chiếu, dữ liệu dẫn xuất, cache và nhật ký. Nếu sản phẩm hỗ trợ chuyển tenant, cần một quy trình chuyên biệt thay vì cho client cập nhật `tenant_id` trực tiếp.

## 11. Nhật ký và kiểm chứng ranh giới

Một sự kiện phân quyền nên giúp trả lời được: ai, trong tenant nào, làm gì, trên tài nguyên nào, theo chính sách nào và kết quả ra sao.

Ví dụ sự kiện minh họa:

```json
{
  "subjectId": "principal-1042",
  "tenantId": "alpha",
  "action": "project.update",
  "resourceId": "project-101",
  "policyId": "alpha-project-update",
  "decision": "DENY",
  "reasonCode": "MEMBERSHIP_INACTIVE",
  "correlationId": "request-901"
}
```

Trong triển khai thực tế, có thể cần thêm thời gian, phiên bản chính sách, danh tính workload hoặc kết quả thao tác. Không ghi token, mật khẩu hay dữ liệu bí mật vào nhật ký. Quyền đọc nhật ký cũng cần có phạm vi; log của tenant khác có thể chứa thông tin nhạy cảm.

Các tình huống dưới đây giúp kiểm chứng thiết kế:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| An là admin của `alpha`, cập nhật dự án trong `alpha` với đủ điều kiện | Cho phép |
| An chỉ là viewer của `beta`, yêu cầu cập nhật dự án trong `beta` | Từ chối |
| An giữ nguyên token nhưng sửa path từ `alpha` sang một tenant không có quyền | Từ chối |
| Path chỉ `alpha` nhưng resource ID thuộc `beta` | Không trả hoặc sửa dữ liệu của `beta` |
| Body gửi `tenant_id` của tenant khác khi tạo dự án | Không cho client chuyển phạm vi được cấp |
| Membership bị thu hồi trong khi còn phiên hoặc cache | Thu hồi theo yêu cầu và cơ chế đã thiết kế |
| Batch chứa ID thuộc nhiều tenant trên API một tenant | Xử lý theo quy tắc lỗi, không vượt ranh giới |
| Job nền được chạy sau khi quyền người yêu cầu thay đổi | Đánh giá theo chính sách vòng đời job đã xác định |
| Cache có kết quả cho phép ở `alpha`, sau đó gọi cùng hành động tại `beta` | Đánh giá theo `beta`, không tái sử dụng quyền của `alpha` |
| Quản trị viên tenant sửa vai trò để thêm quyền nền tảng | Từ chối quyền vượt phạm vi được ủy quyền |

Các kiểm chứng cần bao phủ cả API, service, truy vấn dữ liệu, file tải xuống, cache và tác vụ bất đồng bộ. Một điểm kiểm tra đúng ở đầu request không tự bảo đảm mọi đường truy cập phía sau đều giữ đúng phạm vi.

Tenant-scoped policy có hiệu quả khi cùng một ranh giới được duy trì xuyên suốt: danh tính được xác thực, quan hệ với tenant được xác minh, quyền được đánh giá tại tenant đó và mọi thao tác thực tế tiếp tục giới hạn trong phạm vi đã được cho phép.
