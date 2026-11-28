# Resource ownership

## 1. Quyền sở hữu tài nguyên là một phần của mô hình bảo mật

Trong chương **File và resource security**, resource ownership là quan hệ xác định chủ thể nào sở hữu hoặc chịu trách nhiệm đối với một tài nguyên theo mô hình nghiệp vụ của ứng dụng. Tài nguyên có thể là tệp, thư mục, bản xuất dữ liệu, ảnh dẫn xuất, tài liệu hoặc một đối tượng nghiệp vụ chứa các tài nguyên đó.

Quan hệ này giúp trả lời ai được quản lý tài nguyên, ai có thể chia sẻ, ai chịu trách nhiệm khi chủ thể rời hệ thống và điều gì xảy ra khi tài nguyên đổi chủ. Nó phải được lưu và kiểm tra ở phía có thẩm quyền, không chỉ được hiển thị trong giao diện.

Ví dụ, một người biết file ID và đã đăng nhập chưa chắc có quyền tải tệp. Hệ thống phải kiểm tra đúng tenant, quan hệ sở hữu hoặc quyền được cấp, hành động yêu cầu và trạng thái hiện tại.

Một yêu cầu như “người dùng chỉ được xem file của mình” vẫn còn thiếu:

- “Của mình” là do mình tải lên, do mình tạo, được chuyển cho mình hay được chia sẻ?
- Một người có thể thuộc nhiều tổ chức; tệp đang nằm trong tổ chức nào?
- Chủ sở hữu có mặc nhiên được chia sẻ, xóa hoặc chuyển chủ không?
- Bản preview, phiên bản cũ và link đã cấp có theo cùng quyền không?
- Điều kiện nào áp dụng khi chủ sở hữu bị vô hiệu hoặc tài nguyên được khôi phục?

Bài học chuyển quan hệ sở hữu thành chuỗi yêu cầu:

**Tài nguyên và chủ thể → ranh giới tenant → quyền theo hành động → vòng đời → bằng chứng kiểm chứng.**

Các mô hình, thời hạn và luồng trong bài là ví dụ thiết kế. Cần lựa chọn theo nghiệp vụ, mô hình đe dọa và kiến trúc thực tế.

## 2. Phân biệt chủ sở hữu với các danh tính liên quan

| Thuộc tính hoặc chủ thể | Ý nghĩa | Vì sao không được đánh đồng với owner? |
|---|---|---|
| `created_by` | Người hoặc dịch vụ tạo record | Tài nguyên có thể được tạo thay người khác hoặc đã chuyển chủ |
| `uploaded_by` | Chủ thể đưa byte vào hệ thống | Người nhập liệu không nhất thiết có quyền quản lý lâu dài |
| Business owner | Chủ sở hữu theo mô hình nghiệp vụ | Cần được định nghĩa theo người, nhóm hoặc tổ chức |
| Custodian | Chủ thể được giao quản lý hoặc vận hành | Có trách nhiệm kỹ thuật nhưng không mặc nhiên được chia sẻ dữ liệu |
| Tenant | Ranh giới tổ chức hoặc miền dữ liệu | Một owner cá nhân vẫn có thể chỉ có quyền trong tenant này |
| Storage owner | Danh tính ứng dụng hoặc tài khoản sở hữu object ở kho lưu trữ | Không phải danh tính người dùng được phép đọc tệp |
| Người được chia sẻ | Có một tập quyền được cấp | Quyền đọc không đồng nghĩa với quyền chuyển chủ |
| Service principal | Danh tính máy thực hiện thao tác | Quyền kỹ thuật không thay thế điều kiện nghiệp vụ của người gọi |

Ví dụ, một service account tải bản hóa đơn lên thay người dùng. Nếu hệ thống gán mọi tệp cho service account rồi cho rằng quyền của người dùng đã được giải quyết, mô hình sở hữu vẫn chưa đầy đủ.

Ngược lại, lấy `created_by` làm owner mãi mãi khiến người đã rời dự án tiếp tục được quyền sau khi tài nguyên đã bàn giao.

### 2.1. Chọn loại chủ sở hữu

Một hệ thống có thể chọn:

- Người dùng sở hữu tài nguyên cá nhân trong một tenant.
- Nhóm sở hữu tài liệu dùng chung, thành viên có quyền theo vai trò.
- Tổ chức sở hữu tài nguyên, còn người cụ thể chỉ là người quản lý.
- Nhiều quan hệ khác nhau, ví dụ tổ chức sở hữu và một nhóm chịu trách nhiệm.

Không nên thêm field `owner_id` mà chưa định nghĩa nó trỏ tới loại chủ thể nào và có được đổi không. Nếu hỗ trợ nhiều loại owner, cần namespace hoặc kiểu tham chiếu rõ ràng, không để ID của người và ID của nhóm bị hiểu lẫn.

## 3. Sở hữu không đồng nghĩa với mọi quyền

### 3.1. Quyết định theo chủ thể, tài nguyên, hành động và ngữ cảnh

Một quyết định có thể được mô tả như sau:

```text
allow =
    authenticated_subject_is_eligible
    AND trusted_tenant_context_matches
    AND resource_state_allows_action
    AND policy_allows(subject, action, owner_relationship, explicit_grants, context)
```

Đây là mô hình logic, không yêu cầu mọi hệ thống dùng cùng một engine policy. Điểm quan trọng là ownership chỉ là một đầu vào, không phải một cờ cho phép mọi hành động.

Cần đặc tả riêng các quyền:

```text
read_metadata
read_content
create_preview
update_content
share
revoke_share
transfer_ownership
delete
restore
export
```

Một người có quyền tải tệp chưa chắc được tạo link công khai. Chủ sở hữu cũng có thể bị chặn chia sẻ bởi phân loại dữ liệu, trạng thái cách ly hoặc policy của tổ chức.

### 3.2. Mô hình quyền tối thiểu minh họa

| Quan hệ | Quyền có thể được cấp theo policy | Điều cần kiểm soát thêm |
|---|---|---|
| Owner | Đọc và quản lý nội dung của mình | Không mặc nhiên vượt trạng thái bảo mật hoặc giới hạn chia sẻ |
| Editor được chia sẻ | Chỉnh sửa trong phạm vi được cấp | Không tự chuyển chủ hoặc cấp thêm quyền |
| Viewer | Đọc metadata hoặc nội dung được phép | Không suy ra quyền tải bản gốc, phiên bản cũ hoặc xuất hàng loạt |
| Quản trị tenant | Thao tác quản trị đã liệt kê | Phạm vi tenant, lý do và audit; không phải quyền toàn hệ thống |
| Worker | Xử lý một công việc kỹ thuật được giao | Ràng buộc tenant, resource, action và phiên bản |
| Chủ thể không có quan hệ hợp lệ | Không được phép | Không cho qua chỉ vì biết ID hoặc đường dẫn |

Thứ tự áp dụng cho phép và từ chối phải rõ ràng. Ví dụ, quyền owner không vượt được lệnh cách ly do nội dung chưa đạt kiểm tra.

### 3.3. ID khó đoán không phải bằng chứng quyền

Một file ID ngẫu nhiên có thể giảm khả năng tìm thấy tài nguyên nhưng không thay thế kiểm tra truy cập ở mức đối tượng. ID có thể xuất hiện trong log, link, lịch sử trình duyệt hoặc response hợp lệ của một người khác.

Tương tự, đường dẫn `tenant-A/user-B/file-X` không tự chứng minh caller thuộc tenant A hoặc sở hữu file X. Prefix lưu trữ chỉ là tổ chức dữ liệu nếu không có cơ chế quyền thực thi phù hợp.

## 4. Nguồn tin cậy và mô hình dữ liệu

### 4.1. Metadata có thẩm quyền

Một record có thể gồm:

```text
resource_id
tenant_id
owner_type, owner_subject_id
created_by
parent_resource_id nếu có
content_reference, content_version
ownership_version
classification
lifecycle_state
created_at, updated_at
```

Các field như tenant, owner và tham chiếu nội dung phải do server thiết lập hoặc kiểm tra bằng quyền riêng. Không để một request upload tự chọn owner bất kỳ rồi được chấp nhận chỉ vì field hợp lệ về kiểu dữ liệu.

Nếu chức năng tạo thay người khác là hợp lệ, phải có action như `create_for_subject` với kiểm tra phạm vi, người nhận và audit tương ứng.

### 4.2. Chủ thể và tenant phải có ý nghĩa ổn định

Không dùng email hoặc tên hiển thị đơn lẻ làm danh tính sở hữu nếu chúng có thể đổi hoặc được tái sử dụng. Cần định danh chủ thể ổn định, có phạm vi nguồn danh tính khi cần.

Một người thuộc nhiều tenant không được dùng quyền trong tenant A để truy cập tài nguyên ở B. Tenant đang thao tác phải được chọn và xác minh qua membership, quan hệ tài nguyên và policy, không chỉ tin header client gửi.

Cần xác định owner có phải thành viên còn hiệu lực hay có loại chủ thể đặc biệt nào được phép đứng tên. Không có membership hợp lệ không đồng nghĩa tài nguyên tự trở thành public.

### 4.3. Quan hệ cha con và tài nguyên dẫn xuất

Một tệp có thể thuộc một dự án, đơn hoặc hồ sơ. Đường API dạng:

```text
/projects/{project_id}/files/{file_id}
```

cần chứng minh file thực sự thuộc project đó và caller có quyền với đúng hành động. Kiểm tra quyền trên project A rồi dùng file ID của project B là lỗi ràng buộc đối tượng.

Preview, thumbnail, bản xuất, phiên bản cũ và tệp tạm cần liên kết với tài nguyên gốc hoặc có policy riêng rõ ràng. Không để bản gốc được bảo vệ nhưng thumbnail hoặc đường tải phiên bản cũ lại công khai.

Nếu nội dung dẫn xuất chưa có metadata hợp lệ, mặc định không công bố. Không suy owner từ người vừa truy cập hoặc từ tên object khi metadata bị thiếu.

## 5. Kiểm soát quyền trên mọi đường sử dụng tài nguyên

### 5.1. Tạo và tiếp nhận nội dung

Khi tạo tài nguyên, server cần:

1. Xác thực chủ thể và xác định tenant đủ điều kiện.
2. Kiểm tra quyền tạo ở vị trí hoặc đối tượng cha.
3. Gán owner theo policy, hoặc xác minh quyền tạo thay người khác.
4. Tạo định danh và tham chiếu lưu trữ không phụ thuộc tên tệp tự khai.
5. Ràng buộc upload với đúng resource, tenant và phiên bản.
6. Giữ trạng thái chưa sẵn sàng cho tới khi đủ điều kiện nội dung và vòng đời.

Một request hoàn tất upload không được phép trỏ tới object bất kỳ rồi nhận ownership. Server phải kiểm tra object đó thuộc phiên cấp upload đã giao và không phải nội dung của tài nguyên khác.

Field nhạy cảm như `owner_subject_id`, `tenant_id` hoặc trạng thái chia sẻ không được tự động cập nhật qua một API sửa metadata chung. Chúng cần action, điều kiện và audit riêng.

### 5.2. Đọc, liệt kê, tìm kiếm và tải hàng loạt

Kiểm tra không chỉ áp dụng khi mở một file:

- Danh sách và tìm kiếm phải giới hạn kết quả theo tenant và quyền tương ứng.
- Metadata, tên tệp, số lượng kết quả và preview có thể tiết lộ thông tin.
- API tải hàng loạt phải kiểm tra từng tài nguyên trong tập yêu cầu.
- Export từ một bộ lọc cần xác định phạm vi quyền và dữ liệu được chốt ở thời điểm nào.
- Phiên bản cũ không được có một đường đọc bỏ qua policy của tài nguyên.

Lọc kết quả sau khi đã tính tổng hoặc phân trang có thể làm sai hành vi và tiết lộ thông tin. Cần thiết kế truy vấn và policy phù hợp, không chỉ ẩn các dòng trên giao diện.

Thông báo cho người không có quyền phải nhất quán với chính sách che giấu sự tồn tại. Có thể chọn phản hồi như không tìm thấy trong trường hợp cần thiết; bên trong vẫn ghi được lý do từ chối để điều tra. Không cần công bố owner hoặc tenant của đối tượng bị từ chối.

### 5.3. Ghi và thay đổi trạng thái

Một lần kiểm tra owner rồi ghi sau đó có thể gặp lỗi TOCTOU nếu ownership đổi ở giữa. Khi quyền ghi phụ thuộc owner hiện tại, thay đổi phải được ràng buộc với phiên bản hoặc quyết định có hiệu lực phù hợp.

Mã giả:

```text
update_resource(subject, resource_id, change):
    context = resolve_and_validate_tenant(subject)
    resource = load_trusted_resource(resource_id, context)

    verify action-specific policy using current ownership and state
    expected_ownership_version = resource.ownership_version

    at the authoritative mutation boundary:
        verify tenant, resource state and ownership version still match
        verify required authorization conditions remain valid
        apply only the permitted change
        record the committed result and audit reference
```

Đây là yêu cầu ngữ nghĩa. Một transaction ở service A không tự giữ nguyên quyền nếu nguồn ownership hoặc policy có thể thay đổi độc lập ở service B. Nhóm kiến trúc phải xác định phạm vi nhất quán và cửa sổ hiệu lực được phép.

### 5.4. Chia sẻ và link truy cập

Chia sẻ là một cấp quyền có phạm vi: chủ thể nhận, hành động, tài nguyên hoặc phiên bản, thời hạn và khả năng cấp tiếp. Quyền đọc không tự bao gồm quyền chia sẻ.

Một URL ký sẵn có thể hoạt động như một capability: ai có link trong điều kiện còn hiệu lực có thể dùng quyền mà link mang theo. Nếu cần ràng buộc người nhận cụ thể, phải có cơ chế kiểm tra danh tính phù hợp; không suy rằng người cầm link luôn là người được chủ sở hữu dự định gửi.

Cần đặc tả:

- Ai được cấp link hoặc grant.
- Link áp dụng cho đúng artifact và phiên bản nào.
- Thời hạn và phạm vi thao tác.
- Cách xử lý sau chuyển chủ, xóa, cách ly hoặc thu hồi.
- Cận hiệu lực của cache và các link đã được phát.

Đổi owner trong database không mặc nhiên vô hiệu mọi link trực tiếp còn hiệu lực. Nếu yêu cầu chặn ở lần truy cập kế tiếp, phải có cổng thực thi kiểm tra được trạng thái hiện tại hoặc cơ chế thu hồi tương đương.

### 5.5. Worker và mô hình hành động thay người dùng

Một job xuất dữ liệu do người dùng yêu cầu cần ngữ cảnh có nguồn tin cậy: người yêu cầu, tenant, resource, action và phiên bản liên quan. Quyền đọc rộng của worker không phải lý do bỏ qua quyền của người yêu cầu.

Cần chốt kiểm tra ở lúc enqueue, lúc thực thi và trước công bố kết quả. Nếu ownership hoặc quyền đã đổi, job không được phát lại snapshot quyền cũ như một nguồn thẩm quyền mới.

Phân biệt:

- **Job thay người dùng:** bị ràng buộc bởi quyền và vòng đời yêu cầu của người đó theo policy.
- **Job hệ thống:** thực hiện công việc như bảo trì, retention hoặc đối soát bằng quyền riêng có phạm vi.

Không dùng một cờ do client tự khai để biến job người dùng thành job hệ thống.

## 6. Vòng đời sở hữu: chuyển chủ, rời tổ chức, xóa và khôi phục

### 6.1. Chuyển chủ là một nghiệp vụ nhạy cảm

Chuyển chủ cần xác định:

- Người có quyền khởi tạo và người nhận đủ điều kiện.
- Có cần người nhận xác nhận hay không.
- Có cho chuyển khác tenant hay chỉ trong cùng tenant.
- Tài nguyên con, phiên bản và artifact nào đi cùng.
- Grant cũ nào bị hủy, giữ hoặc cần xét lại.
- Job, link, quota và trạng thái quản trị chịu ảnh hưởng ra sao.

Không chỉ cập nhật một field rồi để các cache, ACL và job tiếp tục dùng owner cũ.

Nếu hai yêu cầu chuyển chủ cùng dựa trên một phiên bản, hệ thống phải có một kết quả được chấp nhận hoặc quy tắc xung đột rõ ràng. Không cho hai người nhận cùng tin rằng mình đã được cấp ownership độc quyền.

### 6.2. Chủ thể bị vô hiệu hoặc rời tổ chức

Không nên xóa dữ liệu ngay hoặc làm tài nguyên public vì owner không còn hoạt động. Có thể cần bàn giao cho nhóm, người quản lý hoặc tổ chức theo policy.

Quy trình cần kiểm kê tài nguyên và grant liên quan, thu hồi quyền trực tiếp, xử lý link, job đang chờ và người nhận bàn giao. Không gán lại tài nguyên cho một account mới chỉ vì nó dùng cùng email với account cũ.

Nếu chưa xác định được người tiếp nhận, có thể đưa tài nguyên vào trạng thái chờ xử lý với quyền quản trị có kiểm soát. “Không có owner hợp lệ” phải là tình huống được quản lý, không phải điều kiện cho phép mọi người truy cập.

### 6.3. Xóa, retention và dữ liệu mồ côi

Soft delete vẫn phải chặn các đường sử dụng không được phép, gồm preview, phiên bản và export. Việc ẩn record ở danh sách không đủ nếu download còn hoạt động.

Xóa metadata và xóa byte có thể không xảy ra cùng lúc. Trong thời gian đó, object còn lại không được tự trở thành tài nguyên có thể nhận về bằng cách đoán key hoặc gọi finalize.

Retention và tác vụ xóa vật lý dùng quyền hệ thống riêng, có phạm vi và bằng chứng. Một owner không mặc nhiên được vượt điều kiện giữ lại do policy của tổ chức áp dụng.

### 6.4. Khôi phục không được hồi sinh quyền cũ ngoài ý muốn

Restore cần xem lại owner hiện tại, membership, grant, trạng thái cách ly và phiên bản quyền. Không áp dụng mù quáng metadata cũ từ backup nếu tài nguyên đã được chuyển chủ hoặc người dùng đã bị thu hồi quyền.

Cần có nguồn đối soát và quy tắc chọn trạng thái có thẩm quyền. Nếu không đủ bằng chứng về quyền, giữ trạng thái hạn chế để xử lý thay vì công bố cho owner suy đoán.

Tái sử dụng resource ID hoặc đặt lại `ownership_version` cũng có thể làm grant cũ có hiệu lực trở lại. Định danh, phiên bản và tombstone phải có vòng đời được đặc tả.

### 6.5. Chuyển giữa các tenant không phải sửa một nhãn

Nếu nghiệp vụ cho phép đưa dữ liệu sang tenant khác, cần đánh giá quyền xuất và quyền nhập, policy tại đích, dữ liệu con, phân loại, link và quyền lưu trữ.

Một hướng là tạo tài nguyên mới tại đích qua quy trình nhập, giữ quan hệ nguồn để audit và thu hồi phần cần thiết ở nguồn. Không mặc định chỉ đổi `tenant_id` sẽ di chuyển an toàn toàn bộ phụ thuộc.

Chuyển owner cũng không được làm biến mất mức sử dụng hoặc reset quota ngoài thiết kế. Nếu có quota theo owner, cần chuyển phần ghi nhận phù hợp; cận tenant vẫn phải được bảo toàn.

## 7. Ví dụ đặc tả: tài liệu cá nhân trong một tenant

### 7.1. Bối cảnh và rủi ro

Một cổng tài liệu lưu mỗi tệp với owner là một người trong tenant. Tenant có policy quản trị riêng; owner được đọc, sửa và chia sẻ trong phạm vi được phép, nhưng không vượt điều kiện cách ly hoặc giới hạn phân loại.

Rủi ro `R-OWN-01` là truy cập tài liệu của chủ thể khác bằng ID, giả mạo owner khi tạo, hoặc tiếp tục dùng quyền cũ sau khi tài liệu đã chuyển chủ.

Ví dụ chọn các quy tắc:

- Chuyển chủ chỉ trong cùng tenant, tới một người khác còn đủ điều kiện.
- Người khởi tạo phải có quyền `transfer_ownership` và là owner hiện tại.
- Người nhận phải xác nhận trong 24 giờ.
- Ownership chưa đổi khi đề nghị còn chờ.
- Lúc chấp nhận phải kiểm tra lại cả hai chủ thể, phiên bản và policy.
- Sau commit, quyền suy ra từ owner cũ và grant chia sẻ do owner cấp trước đó bị thu hồi.
- Quyền quản trị tổ chức độc lập tiếp tục được xét theo policy, không bị nhầm với quyền owner.

Luồng người quản trị bàn giao tài liệu của người đã nghỉ việc là một action riêng, có điều kiện và audit riêng. Không dùng nó như đường không cần kiểm tra của chức năng chuyển chủ thông thường.

### 7.2. Ranh giới truy cập của ví dụ

Mọi lượt tải dành cho người dùng đi qua gateway xác thực và kiểm tra metadata có thẩm quyền; không phát URL object storage trực tiếp cho client trong ví dụ.

Cam kết thu hồi áp dụng cho quyết định truy cập mới sau commit. Byte đã gửi hoặc một lượt đọc đã được cho phép trước đó không tự bị thu hồi khỏi người nhận. Nếu sản phẩm cần dừng cả phiên đang truyền, phải bổ sung cơ chế và tiêu chí riêng.

Thiết kế này tránh việc hứa chặn tức thì trong khi vẫn có link trực tiếp chưa hết hạn. Một sản phẩm dùng URL ký sẵn cần thay cam kết bằng cơ chế và cận hiệu lực thực tế.

### 7.3. Tập yêu cầu có thể kiểm chứng

| ID | Yêu cầu |
|---|---|
| SEC-OWN-01 | Mỗi resource có tenant và owner hợp lệ từ nguồn có thẩm quyền. Khi tạo mặc định owner là chủ thể người đã được xác minh; tạo thay người khác cần quyền riêng. |
| SEC-OWN-02 | Mọi thao tác trên metadata, nội dung, phiên bản, preview và export phải kiểm tra action và phạm vi. Biết ID, object key hoặc URL nội bộ không đủ để được truy cập. |
| SEC-OWN-03 | Quyền trên đối tượng cha chỉ được dùng nếu tài nguyên con thực sự thuộc đối tượng đó. Truy vấn và cập nhật phải ràng buộc tenant, resource và quan hệ tương ứng. |
| SEC-OWN-04 | API sửa metadata không được tự thay owner hoặc tenant. Các field này chỉ đổi qua workflow được phân quyền. |
| SEC-OWN-05 | Đề nghị chuyển chủ gắn với resource, owner nguồn, người nhận, tenant, `ownership_version`, policy version và thời hạn. Tất cả được server xác minh. |
| SEC-OWN-06 | Chỉ người nhận đúng đề nghị mới được chấp nhận. Tại điểm quyết định, hai chủ thể phải còn đủ điều kiện, owner nguồn vẫn là owner hiện tại và request chưa hết hạn. |
| SEC-OWN-07 | Chấp nhận, đổi owner, tăng ownership version, vô hiệu quyền chia sẻ bị ảnh hưởng và ghi audit phải có ranh giới nhất quán đáp ứng cam kết. Hai chuyển chủ cạnh tranh không được cùng thắng trên một phiên bản. |
| SEC-OWN-08 | Sau commit, quyết định mới tại gateway không cho phép chỉ dựa trên owner cũ hoặc grant đã bị vô hiệu. Cache quyền nếu có phải được đối chiếu với phiên bản có thẩm quyền, không tự kéo dài quyền cũ. |
| SEC-OWN-09 | Artifact dẫn xuất và phiên bản cũ dùng quan hệ với resource gốc hoặc policy tương đương; đổi owner không để lại đường tải riêng còn quyền cũ. |
| SEC-OWN-10 | Job thay người dùng không được công bố kết quả dựa trên snapshot ownership đã cũ. Khi ownership đổi, job phải xử lý theo policy phiên bản và quyền hiện tại, không gán lại owner từ dữ liệu enqueue. |
| SEC-OWN-11 | Retry chấp nhận dùng cùng transfer ID và có thể tra được kết quả commit. Mất response không được tạo thêm chuyển chủ hoặc tăng phiên bản lần nữa cho cùng thao tác. |
| SEC-OWN-12 | Khi owner bị vô hiệu, dữ liệu được giữ trong phạm vi tenant và đưa vào quy trình bàn giao; không trở thành public hoặc tự gán cho account trùng email. |
| SEC-OWN-13 | Xóa và restore phải kiểm soát cả nội dung lẫn quan hệ quyền. Restore không làm grant cũ, chủ thể đã bị thu hồi hoặc phiên bản quyền cũ tự có hiệu lực. |
| SEC-OWN-14 | Ghi nhận được người thao tác, hành động, resource, tenant, owner trước/sau, phiên bản, kết quả và tham chiếu workflow mà không log nội dung nhạy cảm dư thừa. |

Thời hạn 24 giờ là thời gian của đề nghị chuyển chủ, không phải thời hạn sở hữu của người nhận sau khi hoàn tất.

Nếu mô hình thực tế phân tán membership, policy và ownership ở nhiều dịch vụ, cần chứng minh cơ chế kiểm tra và chuyển phiên bản đáp ứng những điều kiện trên. Một transaction trong kho resource không tự làm các thay đổi ở dịch vụ danh tính có hiệu lực nguyên tử.

### 7.4. Mã giả xử lý chấp nhận chuyển chủ

```text
accept_transfer(actor, transfer_id):
    load the trusted transfer and its tenant/resource scope
    verify actor is the intended recipient

    at the authoritative ownership decision boundary:
        if this transfer already committed:
            verify actor may read that result
            return the existing committed result

        verify transfer is pending and before its expiry
        verify current policy, memberships and transfer authority
        verify resource is in an eligible state
        verify current owner and ownership version match the proposal

        change owner to the verified recipient
        increment ownership version
        invalidate the affected owner-issued sharing grants
        commit transfer result and audit record

    return the committed result
```

Đây là ngữ nghĩa cần đạt, không phải mã triển khai chạy nguyên trạng. Nếu ACL hoặc cache nằm ngoài transaction, có thể dùng version/epoch và cổng kiểm tra hiện tại để không chấp nhận quyền cũ trong lúc đồng bộ. Việc cập nhật cache sau bằng một message chưa tự đủ nếu gateway vẫn cho phép từ cache cũ.

Một transfer đã hoàn tất không được bị phát lại để “chuyển thêm lần nữa”. Nếu resource về sau đổi chủ tiếp, kết quả lịch sử vẫn là kết quả của thao tác cũ, không phải quyền tác động lên trạng thái mới.

## 8. Tiêu chí kiểm thử và bằng chứng

### 8.1. Chuẩn bị chủ thể và tài nguyên

Cần ít nhất hai tenant, nhiều người trong một tenant, một người thuộc cả hai tenant, một người đã bị vô hiệu, một nhóm và service principal nếu mô hình có hỗ trợ.

Chuẩn bị tệp gốc, preview, phiên bản cũ, tài nguyên đã chia sẻ, tài nguyên bị cách ly và tài nguyên đã xóa. Không chỉ kiểm thử trên đối tượng mà caller tự tạo.

### 8.2. Ma trận kiểm chứng

| Ca kiểm thử | Thiết lập và kích thích | Kết quả mong đợi |
|---|---|---|
| T01 — Owner hợp lệ | Owner thực hiện hành động được policy cho phép trên tài nguyên hoạt động | Thành công đúng phạm vi; vẫn chịu điều kiện nội dung và trạng thái |
| T02 — Biết ID của người khác | Caller thay file ID bằng tài nguyên không có quyền | Không trả metadata hoặc nội dung vượt policy; không dựa vào độ khó đoán ID |
| T03 — Truy cập chéo tenant | Người thuộc A hoặc thuộc cả A/B gửi context và resource không khớp | Không dùng quyền ở A để truy cập B; context được xác minh phía server |
| T04 — Giả owner khi tạo | Gửi `owner_subject_id` hoặc tenant khác trong upload và PATCH metadata | Không tự nhận field nhạy cảm; tạo thay cần đúng quyền riêng |
| T05 — Sai đối tượng cha | Caller có quyền project A nhưng cung cấp file thuộc project B | Không cho qua từ quyền trên cha không liên quan |
| T06 — Đường dẫn xuất | Truy cập preview, phiên bản cũ và export của tệp không có quyền | Không có đường phụ làm lộ nội dung |
| T07 — Danh sách và bulk | Tìm kiếm, liệt kê hoặc tải tập trộn tài nguyên có và không có quyền | Kết quả, số liệu và nội dung tuân thủ policy; không trả dữ liệu ngoài quyền |
| T08 — Chuyển chủ hợp lệ | A đề nghị chuyển cho B cùng tenant, B chấp nhận khi mọi điều kiện còn đúng | Owner đổi một lần, phiên bản tăng, quyền cũ bị xử lý theo policy và audit đầy đủ |
| T09 — Người nhận hoặc tenant sai | Người khác chấp nhận transfer ID hoặc đề nghị sang tenant không cho phép | Bị từ chối; ownership không đổi |
| T10 — Hết hạn hoặc mất quyền | Đề nghị quá 24 giờ, người nhận bị vô hiệu hoặc owner nguồn mất quyền trước quyết định | Không hoàn tất theo điều kiện cũ; lý do được ghi rõ |
| T11 — Hai chuyển chủ cạnh tranh | Hai đề nghị cùng dựa trên một ownership version, người nhận chấp nhận đồng thời | Chỉ một thao tác thắng phiên bản đó; không có hai owner độc quyền |
| T12 — Mất response | Transfer commit rồi mất phản hồi; gửi lại cùng transfer ID | Trả hoặc tra được kết quả cũ, không tăng phiên bản thêm |
| T13 — Quyền cũ sau bàn giao | Owner cũ chỉ có quyền từ ownership hoặc grant đã bị hủy, gửi request mới | Gateway không cho phép bằng quyền cũ; preview và phiên bản cũ cũng tuân thủ |
| T14 — Quyền độc lập | Một chủ thể mất quyền owner nhưng vẫn có role quản trị hợp lệ được policy cấp | Xét theo quyền độc lập, không suy mất owner là mất mọi quyền hoặc ngược lại |
| T15 — Job cũ | Job thay người dùng chờ trong queue khi ownership hoặc quyền đổi | Không công bố dựa vào snapshot cũ, không ghi đè owner hiện tại |
| T16 — Chủ thể rời hệ thống | Vô hiệu owner rồi tạo account khác dùng cùng email | Không nhận lại ownership từ email; tài nguyên theo quy trình bàn giao |
| T17 — Xóa và restore | Xóa, thay đổi quyền rồi thử restore từ dữ liệu cũ | Không hồi sinh grant đã thu hồi hoặc mở đường tải ngoài policy |
| T18 — Object không có metadata | Thử nhận về hoặc tải object mồ côi bằng key biết trước | Không tự gán owner hoặc công bố chỉ vì caller biết tham chiếu |

Với T13, phải chọn chủ thể không có một quyền hợp lệ độc lập để chứng minh thu hồi quyền owner. Nếu người cũ vẫn là quản trị tenant, một lần đọc thành công có thể đúng theo policy; cần phân biệt nguồn cấp quyền.

Với T11, dùng barrier để các thao tác cùng tới điểm quyết định và kiểm tra trạng thái cuối trong kho có thẩm quyền. Không chỉ đếm response vì một response có thể là replay của kết quả đã commit.

### 8.3. Bằng chứng cần đối chiếu

```text
subject và tenant context đã xác minh
  -> resource/parent/owner có thẩm quyền
  -> action và policy version
  -> ownership version tại quyết định
  -> thay đổi hoặc byte thực sự được trả
  -> audit và kết quả workflow
```

Kiểm thử nhiều replica, đường nội bộ và worker nếu đó là phạm vi cam kết. Một giao diện ẩn nút hoặc một endpoint trả từ chối không chứng minh object storage, preview và export đều an toàn.

Cần kiểm thử cả cho phép và từ chối. Một hệ thống từ chối mọi tài nguyên cũng không đáp ứng yêu cầu người có quyền phải sử dụng được dữ liệu.

## 9. Liên kết rủi ro, yêu cầu và kiến trúc

| Rủi ro hoặc mục tiêu | Yêu cầu liên quan | Quyết định kiến trúc | Bằng chứng |
|---|---|---|---|
| R-OWN-01: Dùng ID để truy cập ngoài quyền | SEC-OWN-01, 02, 03 | Metadata có thẩm quyền, policy theo action và ràng buộc tenant/parent | T02, T03, T05, T07 |
| Giả owner hoặc nhận nhầm object | SEC-OWN-01, 04 | Tạo owner phía server, upload gắn resource và phiên bản | T04, T18 |
| Chuyển chủ cạnh tranh hoặc replay | SEC-OWN-05, 06, 07, 11 | Workflow có phiên bản, quyết định nguyên tử và kết quả ổn định | T08–T12 |
| Tiếp tục truy cập sau đổi owner | SEC-OWN-08, 09 | Gateway kiểm tra hiện tại, artifact liên kết resource gốc | T06, T13, T14 |
| Worker dùng quyền cũ | SEC-OWN-10 | Ngữ cảnh job tin cậy và kiểm tra trước công bố | T15 |
| Tài khoản mới nhận dữ liệu cũ hoặc restore hồi sinh quyền | SEC-OWN-12, 13 | Định danh ổn định, bàn giao và đối soát khi restore | T16, T17 |
| Không giải thích được nguồn quyền | SEC-OWN-14 | Audit có cấu trúc, nguồn cấp quyền và workflow reference | Đối chiếu quyết định với tài nguyên thực tế |

Khi thêm tài nguyên con, thay cache, chuyển storage hoặc mở kênh export mới, cần đánh giá lại các hàng tương ứng. Yêu cầu ownership phải đi cùng vòng đời phát triển, không chỉ được kiểm tra lúc thiết kế bảng đầu tiên.

## 10. Logging, dữ liệu và vận hành

Một record có thể chứa:

```text
request_id hoặc operation_id
actor_reference, acting_on_behalf_of nếu có
tenant_reference
resource_reference, parent_reference
action
authorization_basis
owner_before, owner_after khi thay đổi
ownership_version_before, ownership_version_after
policy_version
decision, reason_code
transfer_reference hoặc job_reference
committed_at
```

Nguồn cấp quyền cần đủ để phân biệt owner, share, vai trò quản trị và quyền hệ thống. Không ghi credential, bearer link, nội dung tệp hoặc toàn bộ hồ sơ danh tính chỉ để điều tra quyền.

Quyền xem audit cũng phải được giới hạn. Dữ liệu về owner và quan hệ chia sẻ có thể tiết lộ cấu trúc tổ chức hoặc sự tồn tại của tài nguyên.

Các chỉ số hữu ích:

- Số yêu cầu bị từ chối theo nhóm action và lý do.
- Số lần ràng buộc tenant, parent hoặc ownership version không khớp.
- Số tài nguyên không có owner đủ điều kiện hoặc chờ bàn giao.
- Đề nghị chuyển chủ đang chờ, hết hạn hoặc xung đột.
- Grant và job bị vô hiệu sau đổi owner.
- Object mồ côi, dữ liệu xóa chưa hoàn tất và restore cần đối soát.

Tránh đưa resource ID, user ID hoặc filename thành nhãn metric không giới hạn. Dữ liệu chi tiết nên nằm trong hệ thống log được phân quyền.

Tỷ lệ từ chối tăng có thể do lỗi client, policy mới, cache sai hoặc lạm dụng. Không sửa bằng cách bỏ điều kiện tenant/owner. Cần đối chiếu nguồn quyền và phiên bản để tìm nguyên nhân.

Công cụ vận hành sửa ownership phải có action và audit riêng. Không dùng chỉnh sửa trực tiếp một field như cách bàn giao thông thường nếu việc đó bỏ qua ACL, job và phiên bản.

## 11. Các lỗi đặc tả thường gặp

| Phát biểu | Điểm thiếu | Cách viết rõ hơn |
|---|---|---|
| “File thuộc người upload” | Người upload có thể làm thay và ownership có thể đổi | Tách uploader, creator, owner và quy tắc gán |
| “Chỉ owner được truy cập” | Không có mô hình chia sẻ, quản trị và action | Liệt kê quan hệ, quyền và điều kiện từ chối |
| “ID ngẫu nhiên nên an toàn” | Người khác vẫn có thể biết ID | Kiểm tra quyền ở mức đối tượng trên mọi đường sử dụng |
| “Tenant nằm trong URL là đủ” | Caller có thể tự chọn URL | Xác minh membership và ràng buộc resource với tenant tin cậy |
| “Đổi owner xong là đã thu hồi hết” | Share, cache, link và job có thể còn quyền cũ | Nêu cách xử lý từng loại quyền và cận hiệu lực |
| “Worker có quyền storage nên được đọc” | Nhầm quyền máy với quyền nghiệp vụ | Ràng buộc người yêu cầu, job, action và resource |
| “Preview không quan trọng” | Vẫn có thể lộ nội dung | Áp dụng policy cho mọi artifact và phiên bản |
| “Owner bị xóa thì ai cũng dùng được” | Tài nguyên mồ côi trở thành đường lộ dữ liệu | Giữ hạn chế và dùng quy trình bàn giao |
| “Restore nguyên metadata là đúng” | Có thể hồi sinh quyền đã thu hồi | Đối soát trạng thái quyền hiện tại và nguồn có thẩm quyền |
| “Scan đạt thì cho mọi người tải” | Kiểm tra nội dung không xác định quyền sở hữu | Giữ riêng điều kiện nội dung và điều kiện truy cập |

## 12. Bài tập áp dụng

Bạn thiết kế kho tài liệu của một công ty có nhiều nhóm và nhiều tenant. Một người có thể chuyển nhóm hoặc rời tổ chức. Hãy viết tập yêu cầu gồm:

1. Loại owner, quan hệ với tenant, creator, uploader và nhóm quản lý.
2. Ma trận quyền đọc, sửa, chia sẻ, chuyển chủ, xóa và restore.
3. Quy tắc tạo resource và upload thay người khác.
4. Cách ràng buộc tệp con, preview, phiên bản và export.
5. Workflow chuyển chủ, xử lý quyền cũ, job đang chờ và thao tác đồng thời.
6. Hành vi khi owner bị vô hiệu, object mồ côi hoặc restore thiếu bằng chứng quyền.
7. Ca kiểm thử truy cập chéo tenant, người dùng đa tenant, hai chuyển chủ cạnh tranh và grant cũ.
8. Chuỗi truy vết từ rủi ro tới yêu cầu, kiến trúc và bằng chứng.

Tự kiểm tra: **Với mỗi hành động, hệ thống có biết ai đang yêu cầu, tài nguyên thực sự thuộc phạm vi nào và quan hệ quyền hiện tại đến từ đâu không?** Nếu chỉ biết tên tệp, người upload hoặc một ID khó đoán, yêu cầu ownership chưa đủ cụ thể.
