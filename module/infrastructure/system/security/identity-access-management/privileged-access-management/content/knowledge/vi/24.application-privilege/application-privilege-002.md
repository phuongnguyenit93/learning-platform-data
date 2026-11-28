# API administrative scope

Một API quản trị có thể tạo tài khoản, đổi quyền, luân chuyển credential, sửa chính sách truy cập hoặc triển khai mã mới. Nếu ứng dụng gọi API được cấp quyền quá rộng, một lỗi ứng dụng hoặc credential bị lộ có thể trở thành đường chiếm quyền trên nhiều hệ thống.

**API administrative scope** là phạm vi quyền quản trị mà một danh tính được phép thực hiện qua API. Trong bài học này, khái niệm được dùng theo nghĩa thiết kế kiểm soát: hành động nào, trên tài nguyên nào, trong môi trường hoặc tenant nào, với điều kiện gì và trong khoảng thời gian nào. Một chuỗi scope nằm trong token chỉ là một phần biểu diễn của phạm vi đó, không thay thế toàn bộ quyết định cấp quyền.

Trong Privileged Access Management (PAM), mục tiêu là biến quyền quản trị API thành quyền có thể kiểm kê, giới hạn, cấp có điều kiện, giám sát và thu hồi. Không nên coi tài khoản ứng dụng là ít nhạy cảm hơn tài khoản quản trị viên chỉ vì nó không đăng nhập qua giao diện.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận diện thao tác API có tác động quản trị trực tiếp hoặc gián tiếp.
- Phân biệt scope của token với role, quyền trên đối tượng và chính sách thực thi tại API.
- Thiết kế quyền theo hành động, tài nguyên, tenant, môi trường và thời gian.
- Phân biệt ứng dụng tự hoạt động với ứng dụng gọi thay mặt người dùng.
- Xác định vị trí phải kiểm tra cấp quyền trong API đồng bộ, hàng đợi và tác vụ nền.
- Thiết kế JIT, phê duyệt và thu hồi phù hợp cho thao tác API đặc biệt.
- Xây dựng kiểm thử âm tính và bằng chứng đối soát cho truy cập quản trị.

Các scope, endpoint và cấu hình trong bài là ví dụ minh họa, không phải tên quyền chuẩn chung hoặc cấu hình áp dụng trực tiếp cho một nhà cung cấp.

## 2. Thế nào là một quyền quản trị qua API?

### 2.1. Phân loại theo tác động, không chỉ theo URL

Một endpoint không cần có tiền tố `/admin` để mang đặc quyền. Ví dụ:

- Tạo hoặc vô hiệu hóa tài khoản.
- Gắn danh tính vào một workload.
- Tạo khóa truy cập hoặc thay credential.
- Cấp role, sửa policy hoặc quan hệ tin cậy.
- Thay cấu hình triển khai.
- Sửa đường nhận bản sao lưu.
- Tắt audit hoặc thay đích gửi log.
- Đọc hàng loạt dữ liệu nhạy cảm.
- Cho phép gọi thay mặt một danh tính khác.

Ngược lại, một endpoint dưới `/admin` có thể chỉ đọc trạng thái không nhạy cảm. Phân loại phải dựa trên tài nguyên và hậu quả thực tế.

Quyền đọc cũng có thể là quyền đặc biệt. API xuất toàn bộ dữ liệu khách hàng, lấy cấu hình chứa tham chiếu hạ tầng hoặc đọc secret không trở nên an toàn chỉ vì dùng phương thức GET.

### 2.2. Quyền gián tiếp có thể mạnh hơn tên gọi

Một ứng dụng không có quyền đọc secret nhưng được sửa cấu hình triển khai có thể thay mã để workload khác đọc secret cho nó.

Tương tự:

~~~text
Sửa trust policy
    -> cho phép danh tính do mình kiểm soát nhận quyền
    -> gọi API quản trị

Gắn danh tính đặc quyền vào workload
    -> chạy mã dưới danh tính đó
    -> sử dụng quyền trên tài nguyên

Sửa đường xuất dữ liệu
    -> chuyển dữ liệu nhạy cảm tới đích khác
~~~

Vì vậy, inventory phải ghi cả quyền cấp quyền, quyền sửa đường thực thi và quyền làm suy yếu kiểm soát. Chỉ thống kê các endpoint có tên “delete” hoặc “administrator” sẽ bỏ sót các đường tác động quan trọng.

### 2.3. Bản ghi quyền phải trả lời được nhiều chiều

Một mô hình tư duy:

~~~text
Phạm vi quản trị =
  danh tính bên gọi
  + danh tính được đại diện nếu có
  + hành động
  + tập tài nguyên
  + tenant / môi trường
  + điều kiện và thời gian
~~~

Ví dụ, “được luân chuyển credential” chưa đủ rõ. Cần biết ứng dụng nào được phép luân chuyển credential nào, trong môi trường nào, theo yêu cầu được phê duyệt nào, và có được nhận giá trị secret mới hay chỉ kích hoạt một quy trình quản lý.

## 3. Scope, role và quyền trên đối tượng

### 3.1. Scope là nhãn quyền theo hợp đồng của hệ thống

Các tên như `credential.rotate`, `identity.read` hoặc `policy.write` chỉ có ý nghĩa khi bên phát hành, ứng dụng gọi và API thống nhất cách diễn giải.

Không có quy tắc chung rằng:

- `write` tự bao gồm `read`.
- `admin` tự bao gồm mọi scope khác.
- Dấu chấm biểu thị quan hệ kế thừa.
- Một chuỗi có dấu sao sẽ được mọi API hiểu là wildcard.
- Hai API dùng cùng tên scope có cùng quyền.

Cần mô tả từng scope bằng hành động thực tế, tài nguyên và những điều không được phép. Một tên ngắn dễ đọc không đủ làm hợp đồng bảo mật.

### 3.2. Role là cách tập hợp hoặc gắn quyền

Một role như “Credential Operator” có thể bao gồm nhiều quyền. Role cũng có thể bị giới hạn theo tenant hoặc tập tài nguyên khi gắn cho một principal.

Quan hệ role–scope không bắt buộc một-một. Có hệ thống biểu diễn quyền ứng dụng bằng role hoặc permission riêng thay vì claim scope. Không nên ép mọi nền tảng vào một định dạng token duy nhất.

Điều cần kiểm soát là quyền hiệu lực tại API, bất kể nó được phát hành dưới tên gọi nào.

### 3.3. Scope không thay thế kiểm tra đối tượng

Giả sử client có `credential.rotate`. API nhận:

~~~http
POST /v1/tenants/tenant-a/credentials/cred-017:rotate
~~~

API vẫn phải kiểm tra client có quyền đối với `cred-017` trong `tenant-a`. Nếu chỉ kiểm tra scope rồi dùng ID người gọi truyền vào để tìm credential, client có thể đổi ID sang đối tượng của dịch vụ hoặc tenant khác.

Có hai câu hỏi riêng:

1. Bên gọi có được thực hiện loại hành động này không?
2. Bên gọi có được thực hiện hành động đó trên đúng đối tượng này không?

Cả hai phải được trả lời trước khi gây tác động. Mã định danh khó đoán không thay thế kiểm tra cấp quyền.

### 3.4. Scope được cấp không nhất thiết là toàn bộ quyền hiệu lực

API có thể cần kết hợp:

- Quyền được hệ thống danh tính cấp cho ứng dụng.
- Quyền của người dùng được đại diện.
- Chính sách tại tài nguyên.
- Ranh giới tenant.
- Trạng thái phê duyệt.
- Thời gian hoặc cửa sổ thay đổi.
- Điều kiện bảo mật và quy tắc từ chối.

Không nên mô tả quyết định như phép hợp đơn giản của mọi quyền tìm được. Cách kết hợp và ưu tiên phải rõ ràng, nhất quán, đặc biệt khi có điều kiện từ chối.

## 4. Ứng dụng tự hoạt động và ứng dụng đại diện người dùng

### 4.1. Quyền ứng dụng tự hoạt động

Một dịch vụ tự động có thể xác thực bằng danh tính riêng và thực hiện công việc không gắn với phiên tương tác của một người.

Ví dụ:

- Job luân chuyển credential.
- Dịch vụ đồng bộ inventory.
- Pipeline triển khai.
- Agent thu thập cấu hình.

Quyền này phải được cấp cho danh tính ứng dụng và giới hạn theo công việc. Việc một kỹ sư từng phê duyệt tạo ứng dụng không có nghĩa mỗi lời gọi về sau mang quyền cá nhân của kỹ sư đó.

Nếu một credential dài hạn của ứng dụng có quyền quản trị toàn tổ chức, bật MFA cho tài khoản người tạo ứng dụng không tự bảo vệ credential lúc chạy. Cần kiểm soát chính danh tính ứng dụng, nguồn credential, quyền và đường gọi.

### 4.2. Quyền được ủy quyền từ người dùng

Ứng dụng có thể gọi API trong ngữ cảnh một người dùng đã xác thực. Khi đó, quyết định cần xét cả ứng dụng và người dùng theo mô hình ủy quyền của nền tảng.

Ví dụ, một cổng vận hành được phép gọi thao tác vô hiệu hóa tài khoản, nhưng người đang sử dụng cổng chỉ được quản lý nhóm tài khoản của dịch vụ mình phụ trách.

Không nên lấy toàn bộ quyền của ứng dụng làm quyền cho mọi người dùng của cổng. Cũng không nên bỏ qua giới hạn ứng dụng chỉ vì người dùng có role cao.

### 4.3. Không tin danh tính người dùng từ một header tùy ý

Một API nhận `X-Requested-By: alice` không được coi đó là bằng chứng rằng Alice đã xác thực và ủy quyền.

Danh tính được đại diện phải đến từ cơ chế ủy quyền và chuỗi tin cậy đã xác minh. Nếu một gateway truyền thông tin danh tính, hệ thống phải bảo vệ đường truyền, xác định gateway được tin cậy và ngăn người gọi bên ngoài tự chèn thông tin tương tự.

Log nên phân biệt:

- Principal trực tiếp gọi API.
- Ứng dụng hoặc client.
- Người dùng được đại diện nếu có.
- Danh tính hiệu lực tại tài nguyên.
- Yêu cầu phê duyệt liên quan.

Gộp tất cả thành một cột “user” sẽ làm khó điều tra khi một dịch vụ gọi thay mặt người khác.

## 5. Thiết kế bộ quyền quản trị

### 5.1. Tách quyền theo chức năng có ý nghĩa

Một bộ quyền minh họa:

| Quyền | Ý nghĩa | Không mặc nhiên bao gồm |
| --- | --- | --- |
| `identity.read` | Đọc metadata danh tính trong phạm vi được cấp | Đọc credential hoặc dữ liệu nghiệp vụ |
| `identity.disable` | Vô hiệu hóa danh tính được phép quản lý | Tạo mới hoặc sửa quyền |
| `credential.metadata.read` | Đọc loại, trạng thái và hạn của credential | Đọc giá trị secret |
| `credential.rotate` | Khởi động quy trình luân chuyển được hỗ trợ | Nhận plaintext secret hoặc đổi mọi credential |
| `role.assignment.write` | Thay đổi việc gắn role trong phạm vi được cấp | Sửa định nghĩa role hoặc tự cấp mọi quyền |
| `policy.write` | Sửa chính sách được chỉ định | Tắt audit hoặc sửa mọi quan hệ tin cậy |
| `audit.read` | Đọc bằng chứng được phép | Xóa log hoặc thay cấu hình thu thập |
| `workload.deploy` | Triển khai workload trong phạm vi được cấp | Tự động có quyền đọc dữ liệu runtime |

Bộ quyền thực tế cần theo chức năng và khả năng kiểm soát của API. Chia nhỏ tới mức khó vận hành cũng có thể dẫn tới cấp cả bộ quyền để tránh lỗi. Mục tiêu là đủ rõ để ra quyết định, thử nghiệm và rà soát.

### 5.2. Tách đọc metadata khỏi đọc secret

Ứng dụng kiểm kê thường chỉ cần metadata. Nếu scope `credential.read` vừa cho đọc trạng thái vừa trả giá trị secret, rất nhiều consumer sẽ được cấp quyền vượt nhu cầu.

Một thiết kế tốt có thể cung cấp:

- API đọc metadata riêng.
- API yêu cầu thao tác quản lý credential.
- Luồng nhận secret riêng khi thật sự cần, với điều kiện và bằng chứng phù hợp.

Việc trả secret là hành động nhạy cảm độc lập. Không coi nó là tác dụng phụ bình thường của một API quản trị.

### 5.3. Tách quyền dùng khỏi quyền cấp quyền

Quyền luân chuyển một credential không nên tự động cho phép:

- Gán credential cho chủ thể khác.
- Sửa trust policy.
- Tạo role mới có quyền cao hơn.
- Tự mở rộng tập tài nguyên.
- Tắt kiểm tra phê duyệt.

Các thao tác quản trị hệ thống cấp quyền cần được nhận diện riêng. Nếu một role được quyền sửa chính định nghĩa role của nó mà không có giới hạn, quyền hiệu lực có thể vượt xa danh sách scope ban đầu.

### 5.4. Ràng buộc tập tài nguyên

Có thể giới hạn bằng tập ID cụ thể hoặc thuộc tính được quản lý đáng tin cậy. Ví dụ:

~~~yaml
# Chính sách khái niệm, không phải schema của một sản phẩm.
principal_ref: app/invoice-credential-operator
allowed_actions:
  - credential.rotate

resource_boundary:
  tenant_ref: tenant-finance
  environment: production
  credential_refs:
    - cred-invoice-export
    - cred-invoice-retry

conditions:
  approved_change_required: true
  request_bound_to_resource: true

excluded_capabilities:
  - secret_value_read
  - role_assignment_write
  - trust_policy_write
~~~

Nếu dựa trên nhãn tài nguyên, cần kiểm soát ai được sửa nhãn. Một ứng dụng có thể tự gắn nhãn “thuộc phạm vi của tôi” rồi truy cập tài nguyên sẽ làm mất ý nghĩa ranh giới.

## 6. Ranh giới tenant và môi trường

### 6.1. Tenant trong URL không phải bằng chứng quyền

Người gọi có thể đổi:

- Tenant trong đường dẫn.
- Tenant trong request body.
- ID tài nguyên.
- Header chỉ định tổ chức.
- Tham số lọc hoặc nguồn dữ liệu.

API phải lấy ngữ cảnh được phép từ danh tính và chính sách đã xác minh, rồi đối chiếu với tenant và tài nguyên được yêu cầu.

Có trường hợp một principal quản trị hợp lệ nhiều tenant. Khi đó, tập tenant được cấp phải được ghi và kiểm tra rõ; không mặc định principal chỉ có một tenant hoặc được truy cập tất cả.

### 6.2. Tra cứu tài nguyên phải giữ ranh giới

Một mẫu thiết kế an toàn hơn về mặt ý tưởng:

~~~text
Xác minh principal
    -> xác định tập tenant được phép
    -> xác định tenant của yêu cầu
    -> kiểm tra tenant thuộc tập được phép
    -> tải tài nguyên trong đúng tenant đó
    -> kiểm tra hành động và điều kiện trên tài nguyên
~~~

Không nên tải tài nguyên chỉ bằng ID toàn cục rồi dựa vào tham số người gọi để gắn tenant sau đó.

Nếu hệ thống dùng cache quyết định hoặc cache dữ liệu, khóa cache phải giữ những chiều liên quan như principal, tenant, tài nguyên, hành động và phiên bản chính sách khi cần. Dùng lại kết quả cho một tenant khác có thể phá vỡ việc kiểm tra đúng ở lớp trước.

### 6.3. Tách production khỏi môi trường khác

Một ứng dụng thử nghiệm không nên nhận quyền production chỉ vì dùng cùng mã nguồn hoặc cùng tên dịch vụ.

Tách danh tính, quyền, quan hệ tin cậy và credential theo ranh giới thích hợp. Đối chiếu cả quyền sửa cấu hình: nếu pipeline thử nghiệm có thể đổi endpoint hoặc gắn danh tính production, sự tách biệt trên giấy chưa đủ.

## 7. Đặt kiểm tra cấp quyền tại đâu?

### 7.1. Gateway không thay thế kiểm tra tại dịch vụ

Gateway có thể kiểm tra token, giới hạn lưu lượng hoặc chặn một số route. Dịch vụ xử lý tài nguyên vẫn cần bảo đảm kiểm tra hành động và đối tượng phù hợp.

Lý do:

- Có thể có đường gọi nội bộ khác.
- Gateway không có đủ trạng thái đối tượng.
- Một route có nhiều thao tác nghiệp vụ.
- Phiên bản API mới có thể bị cấu hình khác.
- Quyền có thể phụ thuộc tenant hoặc dữ liệu chỉ dịch vụ biết.

Ẩn nút trên giao diện cũng không phải kiểm soát API. Người gọi có thể tạo request trực tiếp.

### 7.2. Bao phủ mọi đường thực hiện cùng một hành động

Một hành động có thể xuất hiện qua:

- Endpoint đơn lẻ.
- Endpoint batch.
- API phiên bản cũ.
- RPC hoặc mutation trong một giao diện khác.
- Công cụ nội bộ.
- Job nền.
- Luồng import cấu hình.

Nếu route mới kiểm tra đầy đủ nhưng API batch chỉ kiểm tra quyền tổng quát, người gọi có thể đi vòng qua đường batch.

Cần lập bản đồ **hành động nghiệp vụ → mọi điểm vào → điểm thực thi → kiểm tra cấp quyền**. Bản đồ này hữu ích hơn một danh sách route có middleware bảo mật.

### 7.3. Mặc định từ chối khi chưa có quy tắc rõ

Một hành động mới chưa được gắn chính sách không nên tự kế thừa quyền quản trị chung chỉ vì nằm trong cùng controller hoặc service.

Quy tắc mặc định phải rõ và có kiểm thử. Các lớp framework hoặc annotation giúp thực thi, nhưng không tự chứng minh rằng mọi hành động đã được ánh xạ đúng.

## 8. Ví dụ kiểm tra một thao tác luân chuyển credential

API minh họa:

~~~http
POST /v1/tenants/tenant-finance/credentials/cred-invoice-export:rotate
Content-Type: application/json

{
  "changeRequestId": "chg-2048",
  "expectedVersion": 12
}
~~~

Ý định là yêu cầu hệ thống quản lý luân chuyển credential, không trả secret mới cho người gọi.

### 8.1. Pseudocode của quyết định

~~~text
function requestRotation(request):
    principal = verifyAccessCredential(request.authorization)
    command = parseAndValidateRotationRequest(request)

    tenant = resolveRequestedTenant(command.tenantId)
    requirePrincipalAllowedInTenant(principal, tenant)

    credential = loadCredentialWithinTenant(
        tenant.id,
        command.credentialId
    )

    approval = loadTrustedApproval(command.changeRequestId)

    decision = authorize(
        principal = principal,
        action = "credential.rotate",
        resource = credential,
        tenant = tenant,
        approval = approval,
        currentTime = trustedClock.now()
    )

    require decision.allowed

    job = createAuthorizedRotationJob(
        principal = principal,
        resource = credential,
        expectedVersion = command.expectedVersion,
        authorizationContext = decision.context
    )

    recordAuditEvent(job, decision, principal)
    return metadataOnly(job)
~~~

Đây là pseudocode để thể hiện trách nhiệm, không phải triển khai hoàn chỉnh của xác thực, transaction hoặc chống replay.

### 8.2. Những điều phải kiểm tra thêm

- Credential thực sự thuộc tenant được chỉ định.
- Principal có quyền trên credential đó, không chỉ có scope tổng quát.
- Phê duyệt đến từ nguồn tin cậy, còn hiệu lực và gắn với đúng hành động, tài nguyên.
- Người gọi không tự khai “đã phê duyệt” trong request rồi được tin.
- Thao tác được bảo vệ khỏi thực hiện lặp ngoài ý muốn.
- Phiên bản tài nguyên và chính sách không bị thay đổi theo cách làm mất điều kiện đã kiểm tra.
- Job nền không dùng một tài khoản toàn quyền để thực hiện mọi nội dung người gọi có thể đưa vào.
- Kết quả trả về không chứa secret nếu người gọi không có nhu cầu và quyền nhận secret.

Lưu bản ghi job và sự kiện audit cần có tính nhất quán phù hợp. Chỉ ghi “đã yêu cầu” rồi mất dấu việc thực thi không đủ chứng minh thao tác quản trị đã được kiểm soát.

## 9. API bất đồng bộ và thao tác batch

### 9.1. Phê duyệt lúc gửi không giải quyết mọi quyết định lúc chạy

Một request được nhận lúc 10:00 nhưng job chạy lúc 10:30. Trong khoảng đó:

- Quyền của ứng dụng có thể bị thu hồi.
- Phê duyệt có thể hết hạn.
- Đối tượng có thể đổi owner.
- Chính sách có thể thay đổi.
- Yêu cầu có thể bị hủy.

Hệ thống cần quy định rõ một trong các mô hình phù hợp:

- Kiểm tra lại điều kiện cần thiết khi thực thi.
- Hoặc chấp nhận một quyền thực hiện bền vững đã được tạo hợp lệ, với hành động, tài nguyên, hạn và điều kiện hủy được ràng buộc rõ.

Không nên âm thầm để worker chạy mọi job đã vào hàng đợi bất kể thay đổi bảo mật. Cũng không nên giả định hết hạn token bắt buộc hủy ngược mọi giao dịch nghiệp vụ đã được chấp nhận. Đây là quyết định thiết kế cần ghi và thử nghiệm.

### 9.2. Ràng buộc nội dung đã được phê duyệt

Phê duyệt cho “luân chuyển credential A” không được dùng để:

- Luân chuyển credential B.
- Đọc secret thay vì luân chuyển.
- Đổi tenant.
- Mở rộng thành batch toàn bộ tài khoản.
- Thay đổi tham số quan trọng sau khi duyệt.

Có thể cần lưu snapshot hoặc biểu diễn bất biến của yêu cầu cùng phiên bản và định danh phê duyệt. Cơ chế cụ thể phụ thuộc hệ thống, nhưng nội dung được thực hiện phải khớp nội dung được cho phép.

### 9.3. Mỗi phần tử batch cần nằm trong phạm vi

Một batch gồm 100 tài nguyên không trở nên hợp lệ chỉ vì phần tử đầu tiên được phép.

Cần xác định:

- Kiểm tra cấp quyền cho từng phần tử.
- Batch thất bại toàn bộ hay xử lý từng phần.
- Kết quả có làm lộ tài nguyên không được phép hay không.
- Giới hạn số lượng và phạm vi.
- Cách ghi bằng chứng thành công, thất bại và retry.

Giới hạn lưu lượng và kích thước batch giúp giảm tác động vận hành, nhưng không thay thế quyền trên từng tài nguyên.

### 9.4. Idempotency không phải quyền truy cập

Một idempotency key giúp tránh thực hiện lặp theo hợp đồng API. Nó không chứng minh người gọi có quyền, và kết quả cũ không được trả cho principal hoặc tenant khác chỉ vì họ gửi cùng key.

Phạm vi lưu và tra cứu idempotency phải giữ các ranh giới danh tính, tenant và nội dung quan trọng của thao tác.

## 10. JIT và phê duyệt cho quyền API

### 10.1. Tách quyền thường trực và quyền theo nhu cầu

Một ứng dụng kiểm kê có thể cần quyền đọc metadata thường xuyên. Quyền sửa policy hoặc vô hiệu hóa nhiều tài khoản có thể chỉ được cấp trong một cửa sổ công việc cụ thể.

Một luồng JIT có thể gồm:

~~~text
Yêu cầu công việc
    -> kiểm tra owner và phạm vi
    -> phê duyệt khi cần
    -> cấp grant hoặc quyền có hạn
    -> phát hành credential phù hợp
    -> API kiểm tra grant cùng quyền
    -> hết hạn / thu hồi
    -> đối soát kết quả
~~~

Cấp token mới có ít scope hơn không tự thu hẹp token cũ còn hiệu lực. Cơ chế JIT phải tính cả quyền đang tồn tại và cách API nhận biết grant hết hiệu lực.

### 10.2. Thời hạn và phạm vi đều phải được giới hạn

Một grant minh họa:

~~~yaml
# Mô hình dữ liệu ý tưởng.
grant_id: grant-rotation-2048
principal_ref: app/invoice-credential-operator
action: credential.rotate
tenant_ref: tenant-finance
resource_refs:
  - cred-invoice-export
change_request_ref: chg-2048
valid_from: "2026-11-26T02:00:00Z"
valid_until: "2026-11-26T02:30:00Z"
maximum_accepted_operations: 1
secret_return_allowed: false
~~~

Nếu hệ thống có giới hạn số lần sử dụng, việc kiểm tra và tiêu thụ grant phải xử lý được các request đồng thời. Một cột “còn 1 lượt” được đọc rồi cập nhật không nguyên tử có thể cho phép nhiều thao tác cùng vượt qua.

Không phải mọi nền tảng hỗ trợ đầy đủ mô hình này. Phải mô tả những ràng buộc nào được thực thi kỹ thuật và những ràng buộc nào còn dựa vào quy trình.

### 10.3. Phân tách trách nhiệm theo mức rủi ro

Có thể cần tách:

- Người tạo yêu cầu và người duyệt.
- Bên sửa role và bên gán role.
- Bên vận hành workload và bên cấp danh tính đặc quyền.
- Bên thực hiện thao tác và bên quản lý bằng chứng.

Mức tách phụ thuộc nhu cầu và rủi ro. Với tác vụ tự động lặp thường xuyên, có thể phê duyệt chính sách hoặc kế hoạch trong phạm vi hẹp thay vì yêu cầu một người duyệt mọi API call. Tuy nhiên, thay đổi vượt phạm vi đã duyệt phải được xử lý riêng.

## 11. Credential, token và thu hồi

### 11.1. Xác thực đúng loại credential

API phải chấp nhận loại access credential được thiết kế cho nó. Không tự coi token đăng nhập người dùng hoặc token dành cho dịch vụ khác là bằng chứng hợp lệ.

Với token có thể tự xác minh hoặc credential cần kiểm tra qua dịch vụ khác, phải áp dụng cơ chế phù hợp: nguồn phát hành, đối tượng nhận, hiệu lực, danh tính và trạng thái cần thiết. Giải mã payload không phải xác minh.

Ứng dụng nên dùng cơ chế nhận credential được quản lý, có thời hạn khi phù hợp, và tránh đưa credential vào mã nguồn hoặc log. Kho lưu trữ được quản lý giúp bảo vệ secret dài hạn còn cần cho hệ thống cũ, nhưng không thay thế việc giới hạn quyền API.

### 11.2. Tắt ứng dụng chưa chắc chấm dứt mọi token ngay

Tùy kiến trúc, việc ngừng cấp token mới có thể không làm token cũ hoặc phiên đã thiết lập bị từ chối ngay.

Muốn có mục tiêu thu hồi rõ, cần xem xét:

- API có kiểm tra trạng thái hiện tại hay chỉ kiểm tra dữ liệu trong token.
- Thời hạn credential.
- Cache quyền và cache trạng thái.
- Grant tại server.
- Tác vụ đã được chấp nhận.
- Kết nối hoặc phiên downstream.

Không cam kết “thu hồi tức thì” nếu chỉ có bằng chứng đã chặn phát hành token mới.

### 11.3. Luân chuyển credential không làm giảm scope

Một ứng dụng có quyền quản trị quá rộng vẫn có quyền đó sau khi đổi khóa. Hai hoạt động cần được quản lý riêng:

- Bảo vệ và đổi phương tiện xác thực.
- Rà soát và giảm phạm vi quyền.

Nếu credential bị lộ, có thể phải vừa thu hồi credential, vừa xem xét quyền bị sử dụng, grant được tạo và thay đổi chính sách do kẻ tấn công thực hiện.

## 12. Bằng chứng và giám sát

### 12.1. Ghi quyết định, không chỉ mã trạng thái HTTP

Một sự kiện kiểm toán có ích nên cho biết:

- Thời điểm và ID tương quan.
- Principal trực tiếp, ứng dụng và người được đại diện nếu có.
- Hành động nghiệp vụ.
- Tenant và tài nguyên.
- Kết quả xác thực và cấp quyền.
- Lý do cho phép hoặc từ chối ở mức phù hợp.
- Grant, yêu cầu thay đổi hoặc phê duyệt liên quan.
- Phiên bản chính sách hoặc cấu hình khi có.
- ID job và kết quả thực thi.
- Thay đổi quan trọng trước và sau, đã loại bỏ secret.

Mã 200 chỉ cho biết API trả một kết quả thành công theo hợp đồng, không giải thích ai đã được phép làm gì. Mã lỗi cũng cần được diễn giải theo thiết kế API; không nên dùng riêng một mã HTTP để kết luận chính sách đã hoạt động đúng.

### 12.2. Không ghi bí mật vào audit

Không ghi access token, header xác thực, private key, mật khẩu hoặc plaintext secret. Request body của API quản trị có thể chứa dữ liệu nhạy cảm, vì vậy cần thiết kế bộ trường được phép ghi và quy tắc che dữ liệu.

Bằng chứng về thay đổi credential có thể ghi ID credential, phiên bản, kết quả và consumer liên quan, thay vì giá trị mới.

Log cũng là tài nguyên cần giới hạn quyền đọc, sửa, xóa và thời gian lưu. Nếu ứng dụng quản trị có thể tự xóa toàn bộ bằng chứng của mình, khả năng đối soát sẽ yếu.

### 12.3. Tín hiệu cần điều tra

Ví dụ:

- Ứng dụng gọi hành động chưa từng được giao.
- Nhiều lần thử tài nguyên hoặc tenant ngoài phạm vi.
- Thay đổi trust policy rồi ngay sau đó phát sinh quyền mới.
- Tăng đột biến thao tác hàng loạt.
- Hoạt động sau khi grant đã hết hiệu lực theo chính sách.
- Tác vụ nền chạy dưới principal khác với ngữ cảnh đã được phê duyệt.
- Cấu hình audit hoặc nơi lưu bằng chứng bị thay đổi.

Các tín hiệu là đầu vào điều tra, chưa tự chứng minh có xâm phạm. Cần đối chiếu triển khai, công việc hợp lệ và chất lượng nguồn.

## 13. Kế hoạch triển khai quyền tối thiểu

### Bước 1: Kiểm kê hành động quản trị

Liệt kê hành động nghiệp vụ, không chỉ route. Với mỗi hành động, ghi điểm vào, tài nguyên, tác động trực tiếp và đường tác động gián tiếp.

### Bước 2: Kiểm kê principal đang gọi

Xác định ứng dụng, service account, owner, môi trường, credential và cách sử dụng. Phân biệt app-only với gọi thay mặt người dùng.

### Bước 3: Đối chiếu quyền được cấp và nhu cầu

Kết hợp tài liệu công việc, cấu hình, log và xác nhận owner. Không thấy một quyền được dùng trong cửa sổ ngắn chưa đủ để kết luận không cần, nhất là quyền phục hồi hoặc tác vụ cuối kỳ.

### Bước 4: Thiết kế scope và ranh giới tài nguyên

Tách chức năng có ý nghĩa, định nghĩa rõ quyền bao gồm gì và loại trừ gì. Đặt giới hạn tenant, môi trường và khả năng cấp quyền.

### Bước 5: Đặt điểm thực thi

Bảo đảm mọi đường gọi đều tới kiểm tra phù hợp. Bao phủ batch, job nền, công cụ nội bộ và phiên bản API còn được hỗ trợ.

### Bước 6: Kiểm thử và chuyển đổi

Chạy cả phép thử được phép và bị cấm. Chuyển principal sang quyền hẹp hơn có kế hoạch, theo dõi lỗi và giữ khả năng khôi phục phù hợp.

### Bước 7: Thu hồi quyền rộng cũ

Kiểm tra role, grant, credential hoặc đường gọi cũ. Quyền mới đã đúng nhưng quyền quản trị chung cũ vẫn còn thì mục tiêu chưa đạt.

### Bước 8: Duy trì

Rà soát khi thêm endpoint, đổi owner, đổi môi trường, thay cách ủy quyền hoặc phát hiện đường tác động mới. Một scope được định nghĩa đúng hôm nay có thể rộng lên nếu API gắn thêm chức năng vào nó mà không đánh giá.

## 14. Bài thực hành: ứng dụng vận hành credential

### 14.1. Bối cảnh

Ứng dụng Atlas Operator hiện có quyền `platform.admin` để:

- Đọc trạng thái credential của dịch vụ hóa đơn.
- Khởi động luân chuyển hai credential production.
- Theo dõi kết quả job.

Thực tế quyền hiện tại còn cho phép tạo tài khoản, gán role, đọc secret và đổi cấu hình audit. Ứng dụng được triển khai cả staging và production. Một endpoint batch nhận danh sách credential ID và một trường `tenantId` từ request.

### 14.2. Yêu cầu

Thiết kế lại quyền sao cho:

1. Ứng dụng đọc được metadata cần thiết.
2. Chỉ principal production được yêu cầu luân chuyển đúng hai credential.
3. Không được nhận plaintext secret.
4. Không được sửa role, trust policy hoặc audit.
5. Mọi phần tử batch đều được kiểm tra.
6. Yêu cầu luân chuyển gắn với một thay đổi được phê duyệt.
7. Có cách chặn cấp mới và xử lý request hoặc job đang tồn tại.
8. Có bằng chứng danh tính, phạm vi và kết quả thực thi.

### 14.3. Ma trận kiểm thử tham khảo

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Principal production đọc metadata credential được cấp | Cho phép |
| Principal production luân chuyển đúng credential với phê duyệt hợp lệ | Cho phép và trả metadata job |
| Principal staging yêu cầu thao tác production | Từ chối |
| Đổi tenant trong URL hoặc body sang tenant khác | Từ chối theo ranh giới tenant |
| Có scope luân chuyển nhưng đổi sang credential ngoài tập cho phép | Từ chối |
| Batch gồm một đối tượng hợp lệ và một đối tượng ngoài phạm vi | Xử lý theo hợp đồng batch, đối tượng ngoài phạm vi không được thực hiện |
| Dùng phê duyệt của credential A cho credential B | Từ chối |
| Yêu cầu đọc giá trị secret | Từ chối |
| Thử gán role hoặc tắt audit | Từ chối |
| Gửi lại request cùng idempotency key hợp lệ | Không tạo thao tác lặp trái hợp đồng |
| Principal khác dùng cùng idempotency key | Không được nhận kết quả hoặc thực hiện ngoài quyền |
| Quyền bị thu hồi trước khi job chạy | Thực hiện đúng chính sách đã định cho job đang chờ |

Một kết quả từ chối do lỗi mạng không đủ để chứng minh quyền bị chặn. Bằng chứng phải cho thấy yêu cầu đã tới đúng điểm kiểm tra và bị từ chối vì điều kiện mong đợi.

### 14.4. Đầu ra cần nộp

- Danh sách hành động và scope minh họa.
- Ranh giới principal, tenant, môi trường và tài nguyên.
- Sơ đồ điểm kiểm tra từ API tới worker.
- Chính sách phê duyệt và hành vi job sau thay đổi quyền.
- Ma trận kiểm thử và kết quả mong đợi.
- Mẫu sự kiện audit không có secret.
- Kế hoạch thu hồi `platform.admin` và các credential hoặc grant cũ liên quan.

Bài thực hành đạt khi người rà soát giải thích được vì sao mỗi đường được phép là cần thiết và vì sao đường ngoài phạm vi sẽ bị từ chối.

## 15. Chỉ số đánh giá kiểm soát

Không nên chỉ đếm số scope đã tách. Một hệ thống có nhiều scope vẫn có thể cấp tất cả cho mọi ứng dụng.

Các chỉ số có ích:

- Số principal còn quyền quản trị rộng và lý do.
- Tỷ lệ principal có owner, mục đích và ranh giới tài nguyên được xác nhận.
- Tỷ lệ hành động quản trị có kiểm thử cấp quyền ở mọi điểm vào đã biết.
- Số ngoại lệ quyền rộng quá hạn.
- Số thao tác đặc biệt có thể liên kết tới grant hoặc phê duyệt phù hợp.
- Khoảng thời gian từ quyết định thu hồi tới khi thao tác mới bị từ chối.
- Số phát hiện khác biệt giữa quyền khai báo và quyền hiệu lực.

Mẫu số và phạm vi phải rõ. Ví dụ, “100% API có kiểm thử” chỉ có ý nghĩa nếu danh sách API đã bao gồm batch, phiên bản cũ, job và đường gọi nội bộ trong phạm vi cam kết.

## 16. Câu hỏi tự kiểm tra

**1. Token có scope quản trị là đủ để cho phép thao tác trên mọi tài nguyên không?**

Không. API phải kiểm tra đúng hành động, đối tượng, tenant, môi trường và điều kiện liên quan. Scope tổng quát không thay thế quyền trên tài nguyên.

**2. Có thể tin tenant do client gửi trong body không?**

Có thể dùng nó để biểu đạt đối tượng yêu cầu, nhưng không dùng như bằng chứng quyền. Phải đối chiếu với principal và chính sách đã xác minh.

**3. Vì sao quyền triển khai ứng dụng có thể là quyền đặc biệt?**

Người sửa mã hoặc cấu hình có thể làm workload thực hiện hành động bằng danh tính runtime. Cần đánh giá đường tác động gián tiếp này.

**4. Đổi khóa ứng dụng có thu hẹp quyền quản trị không?**

Không. Đổi credential và giảm quyền là hai việc riêng. Quyền cũ vẫn còn nếu role, grant hoặc policy chưa thay đổi.

**5. Vì sao cần kiểm tra từng phần tử batch?**

Mỗi đối tượng có thể thuộc tenant, owner hoặc ranh giới khác nhau. Một phần tử hợp lệ không cho phép toàn bộ danh sách.

**6. Token hết hạn có bắt buộc hủy mọi job đã được nhận không?**

Không có một quy tắc chung cho mọi hệ thống. Cần thiết kế rõ việc kiểm tra lúc nhận, lúc thực thi và cơ chế quyền bền vững hoặc hủy job, rồi thử nghiệm hành vi đó.

**7. API đọc metadata có nên được cấp quyền đọc secret cho tiện không?**

Không. Hai nhu cầu có mức rủi ro khác nhau và cần được tách khi hệ thống hỗ trợ. Cấp quyền vượt nhu cầu làm tăng phạm vi ảnh hưởng.

**8. Vì sao một request bị từ chối vẫn cần được đối chiếu bằng chứng?**

Để biết nó bị chặn do chính sách đúng hay chỉ do lỗi hạ tầng. Chỉ kết quả cuối không đủ chứng minh điểm kiểm soát mong muốn hoạt động.

## 17. Checklist áp dụng

- Đã kiểm kê hành động quản trị trực tiếp và gián tiếp.
- Có owner và mục đích cho từng principal gọi API.
- Phân biệt app-only và gọi thay mặt người dùng.
- Scope, role và quyền trên đối tượng có ý nghĩa được mô tả rõ.
- Tenant, môi trường và tập tài nguyên được thực thi tại API phù hợp.
- Quyền đọc secret được phân biệt với metadata và thao tác quản lý.
- Quyền dùng, quyền cấp quyền và quyền sửa kiểm soát được đánh giá riêng.
- Gateway, dịch vụ, batch và worker không tạo đường bỏ qua.
- Phê duyệt gắn với đúng nội dung, tài nguyên và thời gian.
- Có chính sách cho job khi quyền hoặc trạng thái thay đổi.
- Credential và quyền rộng cũ được thu hồi theo kế hoạch.
- Audit liên kết được principal, quyết định và kết quả mà không chứa secret.
- Kiểm thử bao gồm trường hợp ngoài scope, ngoài tài nguyên và ngoài tenant.

Phạm vi quản trị API có thể kiểm soát được khi nó được mô tả bằng hành động cụ thể và được thực thi trên đúng tài nguyên, đúng ngữ cảnh. Trong PAM, việc đó cần đi cùng quản lý danh tính ứng dụng, quyền có hạn khi phù hợp, giám sát và bằng chứng thu hồi, thay vì chỉ dựa vào một nhãn “admin” trong token.
