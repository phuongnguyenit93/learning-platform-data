# Tenant isolation: cô lập tenant trong hệ thống IAM đa khách hàng

## 1. Tenant là gì và vì sao phải cô lập?

Trong một ứng dụng đa tenant, nhiều tổ chức hoặc nhóm khách hàng sử dụng cùng một sản phẩm, nhưng mỗi tenant có một phạm vi dữ liệu và quản trị riêng. Ví dụ, công ty An Bình và công ty Minh Hải cùng dùng một dịch vụ quản lý hợp đồng. Hai công ty có thể chạy trên cùng cụm máy chủ, nhưng tài khoản, hợp đồng, cấu hình SSO và quyết định phân quyền của công ty này không được tự động tác động đến công ty kia.

**Tenant isolation** là việc duy trì ranh giới đó trên mọi đường truy cập. Trong IAM, ranh giới không chỉ nằm ở dữ liệu nghiệp vụ. Nó còn bao gồm danh tính, quan hệ thành viên, vai trò, chính sách, phiên đăng nhập, thông tin xác thực, danh tính workload và hoạt động quản trị.

Một người dùng có thể là thành viên của nhiều tenant. Vì vậy, “đã đăng nhập” chưa trả lời được “đang thao tác cho tổ chức nào” hoặc “được làm gì trong tổ chức đó”.

Bài học sử dụng tình huống xuyên suốt:

- Tenant `tenant-an-binh` sở hữu hợp đồng `contract-417`.
- Lan là quản trị viên của An Bình, đồng thời là người xem tại Minh Hải.
- Minh Hải có một người dùng khác cũng mang vai trò có tên `admin`.
- Một worker nền xuất hợp đồng theo yêu cầu của từng tenant.

Yêu cầu quan trọng là: quyền của Lan ở An Bình không đi theo Lan sang Minh Hải; vai trò `admin` của Minh Hải không mở được hợp đồng của An Bình; worker nền cũng phải tuân thủ ranh giới tương tự.

## 2. Xác thực, phân quyền và cô lập tenant là ba câu hỏi khác nhau

| Câu hỏi | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Chủ thể là ai? | Xác thực danh tính người dùng hoặc workload | Phiên hợp lệ xác định Lan là người dùng `user-73` |
| Chủ thể được làm gì? | Phân quyền theo hành động, tài nguyên và điều kiện | Lan được đọc hợp đồng trong một phạm vi nhất định |
| Quyết định thuộc tenant nào? | Cô lập phạm vi của thành viên, quyền và tài nguyên | Quyền được đánh giá cho `tenant-an-binh` |

Một token hợp lệ không mặc nhiên cho phép truy cập mọi tenant được nêu trong URL. Tương tự, việc tài nguyên có cột `tenant_id` không tự bảo vệ dữ liệu nếu ứng dụng quên áp dụng cột đó khi truy vấn.

Có thể mô tả điều kiện cho phép đọc một tài nguyên thuộc tenant như sau:

```text
CHO_PHÉP =
    danh_tính_đã_được_xác_thực
    VÀ ngữ_cảnh_tenant_được_chấp_nhận
    VÀ chủ_thể_có_quan_hệ_hợp_lệ_với_tenant
    VÀ tài_nguyên_thuộc_đúng_phạm_vi_tenant
    VÀ chính_sách_cho_phép_hành_động
```

Đây là mô hình tư duy cho đường truy cập tenant thông thường. Hệ thống có chia sẻ tài nguyên giữa các tenant phải bổ sung một quan hệ chia sẻ tường minh, thay vì bỏ qua điều kiện phạm vi.

## 3. Xác định rõ các ranh giới cần bảo vệ

### 3.1. Danh tính và quan hệ thành viên

Danh tính toàn cục và tư cách thành viên trong tenant là hai khái niệm khác nhau.

```text
User
  id = user-73

Membership
  user = user-73, tenant = tenant-an-binh, state = ACTIVE
  user = user-73, tenant = tenant-minh-hai, state = ACTIVE

RoleAssignment
  membership tại An Bình  -> tenant_admin
  membership tại Minh Hải -> contract_viewer
```

Tách các khái niệm này giúp hệ thống thu hồi quyền của Lan tại An Bình mà không nhất thiết xóa danh tính của Lan hoặc tư cách thành viên tại Minh Hải.

Tên vai trò không phải phạm vi quyền. Một bản ghi chỉ ghi `user-73 -> admin` là thiếu thông tin nếu vai trò đó dành cho một tenant cụ thể.

### 3.2. Danh tính liên kết và cấu hình xác thực

Một tenant có thể dùng nhà cung cấp danh tính riêng để đăng nhập SSO. Hệ thống cần biết cấu hình liên kết nào được quản trị viên có thẩm quyền thiết lập cho tenant nào.

Với danh tính từ nhà cung cấp bên ngoài, không nên coi địa chỉ email là khóa duy nhất đủ để xác định chủ thể. Một ánh xạ thường cần xét cả nhà phát hành danh tính và định danh chủ thể tại nhà phát hành đó; quan hệ thành viên với tenant vẫn là dữ liệu riêng của ứng dụng.

Một claim tự khai như `organization=an-binh`, một email có cùng tên miền hoặc một tham số callback không tự tạo ra quyền thành viên. Việc xác minh nguồn danh tính và quy trình gia nhập tenant phải có quy tắc rõ ràng.

### 3.3. Tài nguyên và cấu hình quản trị

Ngoài hợp đồng hoặc hóa đơn, các đối tượng sau cũng cần có phạm vi sở hữu:

- Vai trò tùy chỉnh, chính sách phân quyền và nhóm người dùng.
- Cấu hình SSO, quy tắc MFA và thiết lập phiên của tenant.
- API key, client tích hợp, webhook và thông tin kết nối.
- Nhật ký kiểm toán, báo cáo xuất dữ liệu và kho lưu trữ tệp.

Nếu màn hình quản trị SSO chỉ kiểm tra “người dùng là admin” mà thiếu phạm vi tenant, lỗi có thể cho phép một tenant sửa cơ chế đăng nhập của tenant khác. Đây là lỗi cô lập ngay cả khi chưa có truy vấn dữ liệu nghiệp vụ nào xảy ra.

## 4. Tạo ngữ cảnh tenant đáng tin cậy

### 4.1. Dữ liệu do client gửi chỉ là yêu cầu chọn tenant

Tenant có thể xuất hiện trong hostname, đường dẫn, header hoặc nội dung request:

```http
GET /tenants/tenant-an-binh/contracts/contract-417
X-Tenant-ID: tenant-an-binh
```

Các giá trị này cho biết client muốn thao tác ở đâu. Chúng chưa chứng minh client được quyền thao tác ở đó.

Một luồng xử lý cần:

1. Xác thực người dùng hoặc workload.
2. Đọc tenant mà request yêu cầu.
3. Kiểm tra tenant có tồn tại và ở trạng thái được phép phục vụ.
4. Kiểm tra chủ thể có quan hệ truy cập hợp lệ với tenant đó.
5. Nếu thông tin xác thực có phạm vi tenant, kiểm tra phạm vi đó phù hợp với request.
6. Tạo ngữ cảnh tenant đã kiểm chứng để các tầng phía sau sử dụng.

Nếu request mang nhiều tenant ID mâu thuẫn, ví dụ URL chỉ An Bình nhưng token chỉ Minh Hải, hệ thống phải xử lý theo một hợp đồng rõ ràng và từ chối trường hợp không phù hợp. Không âm thầm chọn giá trị giúp request đi tiếp.

### 4.2. Ngữ cảnh nên được truyền tường minh

Một đối tượng ngữ cảnh có thể chứa:

```text
TenantContext
  tenantId
  actorId
  membershipId hoặc serviceGrantId
  authenticationContext
  correlationId
```

Ngữ cảnh được tạo sau bước kiểm tra và truyền đến nơi quyết định quyền, truy vấn dữ liệu, ghi audit hoặc gọi dịch vụ tiếp theo.

Không nên để từng hàm tự đọc lại `X-Tenant-ID` rồi coi đó là dữ liệu đáng tin cậy. Khi thiếu ngữ cảnh bắt buộc, đường xử lý phải từ chối hoặc báo lỗi; không dùng tenant đầu tiên, tenant mặc định hay tenant của request trước.

Trong mô hình xử lý song song, biến toàn cục hoặc trạng thái dùng chung có thể làm rò ngữ cảnh giữa các request. Nếu dùng cơ chế gắn ngữ cảnh theo luồng hoặc tác vụ, phải hiểu cách nó được truyền và dọn dẹp khi đổi luồng, tái sử dụng luồng hoặc chạy bất đồng bộ.

### 4.3. Token có claim tenant vẫn cần được kiểm tra đúng cách

Claim tenant chỉ có giá trị sau khi token đã được xác minh theo hợp đồng của hệ thống, gồm các kiểm tra như chữ ký, nhà phát hành, đối tượng nhận và thời hạn.

Sau đó vẫn phải xét ý nghĩa của claim:

- Token này dành cho đúng một tenant hay một danh tính có thể chọn tenant?
- Vai trò trong token có phạm vi nào?
- Trạng thái thành viên đã bị thay đổi sau lúc cấp token chưa?
- Dịch vụ nhận token có phải đúng đối tượng được phép sử dụng token đó không?

Không giải mã phần payload rồi sử dụng ngay `tenant_id` hoặc `roles` như một quyết định cấp quyền.

## 5. Kiểm tra quyền cùng với quyền sở hữu tài nguyên

Xét luồng đọc hợp đồng. Mã giả sau thể hiện thứ tự kiểm tra, không phải triển khai đầy đủ cho một framework:

```text
function readContract(request, credential):
    actor = authenticateAndValidate(credential)

    requestedTenant = request.path.tenantId
    context = establishTenantContext(actor, requestedTenant)

    contract = contractRepository.findByTenantAndId(
        context.tenantId,
        request.path.contractId
    )

    if contract is absent:
        return responseForUnavailableResource()

    if not policyAllows(context, "contract:read", contract):
        return responseForDeniedAccess()

    auditRead(context, contract.id)
    return contract
```

Điểm quan trọng là repository nhận cả tenant và ID tài nguyên. Việc một ID tài nguyên khó đoán không thay thế kiểm tra quyền.

Các câu lệnh SQL minh họa với tham số đặt tên:

```sql
SELECT id, tenant_id, title, state
FROM contract
WHERE tenant_id = :tenant_id
  AND id = :contract_id;

UPDATE contract
SET state = :new_state
WHERE tenant_id = :tenant_id
  AND id = :contract_id;
```

Trong đó `:tenant_id` được lấy từ ngữ cảnh đã kiểm chứng, không lấy trực tiếp từ một trường tùy ý trong payload.

Bộ lọc tenant chỉ giới hạn tập tài nguyên được tìm thấy. Nó chưa thay thế điều kiện nghiệp vụ như “chỉ người phụ trách hợp đồng được sửa” hoặc “người xem chỉ đọc bản đã phát hành”.

Khi tạo mới tài nguyên, server cần gán hoặc xác minh tenant sở hữu. Khi cập nhật, không cho phép người dùng chuyển quyền sở hữu sang tenant khác bằng cách gửi thêm `tenant_id` vào đối tượng cập nhật thông thường.

Với truy cập theo danh sách ID, mọi phần tử phải được kiểm tra trong cùng phạm vi được phép. Kiểm tra tenant cho phần tử đầu tiên rồi xử lý toàn bộ danh sách là chưa đủ.

## 6. Lựa chọn mô hình lưu trữ không thay thế IAM

| Mô hình | Ranh giới lưu trữ | Điều cần chú ý trong IAM |
| --- | --- | --- |
| Chung bảng, có `tenant_id` | Các tenant chia sẻ bảng dữ liệu | Phải áp dụng phạm vi tenant nhất quán cho đọc, ghi và quan hệ dữ liệu |
| Tách schema theo tenant | Mỗi tenant có một không gian schema | Việc chọn schema và quyền kết nối vẫn phải xuất phát từ ngữ cảnh hợp lệ |
| Tách cơ sở dữ liệu theo tenant | Mỗi tenant có cơ sở dữ liệu riêng | Cần ngăn kết nối nhầm tenant và giới hạn danh tính dịch vụ |
| Tách môi trường hoặc tài khoản hạ tầng | Có thêm ranh giới triển khai và quyền hạ tầng | Vẫn cần kiểm tra người dùng, tenant và hành động ở ứng dụng |

Không có một lựa chọn phù hợp cho mọi sản phẩm. Chi phí vận hành, nhu cầu khôi phục riêng, mức độ tách biệt cần thiết và khả năng quản lý nhiều môi trường đều ảnh hưởng đến quyết định.

Với dữ liệu dùng chung bảng, ràng buộc cơ sở dữ liệu có thể giúp ngăn liên kết sai tenant. Ví dụ, một chi tiết hợp đồng mang cặp `(tenant_id, contract_id)` cần tham chiếu đến hợp đồng trong cùng tenant, thay vì chỉ tham chiếu `contract_id`.

Tính duy nhất cũng phải đúng phạm vi. Nếu tên nhóm chỉ cần duy nhất trong tenant, ràng buộc nên thể hiện cặp `(tenant_id, group_name)`, thay vì vô tình cấm hai tenant dùng cùng tên nhóm.

Một số cơ sở dữ liệu cung cấp chính sách bảo mật theo hàng để bổ sung lớp bảo vệ. Hiệu quả của lớp này phụ thuộc vào chính sách, vai trò kết nối, khả năng bỏ qua chính sách và cách thiết lập ngữ cảnh trong từng đơn vị xử lý. Nó cần được kiểm thử cùng ứng dụng, không chỉ bật một tùy chọn rồi coi là đã cô lập.

Cô lập IAM cũng không đồng nghĩa cô lập tài nguyên tính toán. Giới hạn tải, hàng đợi và hạn mức sử dụng giúp giảm ảnh hưởng vận hành giữa các tenant, nhưng không tự ngăn đọc dữ liệu chéo tenant.

## 7. Vai trò và chính sách phải có phạm vi tenant

Trong RBAC, nên hiểu một phép gán quyền theo dạng:

```text
(chủ thể, tenant, vai trò)
```

Ví dụ:

```text
(user-73, tenant-an-binh, tenant_admin)
(user-73, tenant-minh-hai, contract_viewer)
```

Tên `tenant_admin` cho biết phạm vi quản trị của một tenant, không phải quyền quản trị toàn nền tảng. Các thao tác như sửa thông tin tenant khác hoặc thay đổi chính sách vận hành chung phải thuộc quyền nền tảng riêng.

Trong ABAC, thuộc tính tenant của chủ thể, tài nguyên và ngữ cảnh có thể tham gia quyết định:

```text
cho phép contract:read khi:
    membership.state == ACTIVE
    membership.tenantId == context.tenantId
    resource.tenantId == context.tenantId
    role cho phép đọc hợp đồng
    các điều kiện nghiệp vụ khác được thỏa mãn
```

Thuộc tính dùng để quyết định quyền phải có nguồn đáng tin cậy. Nếu client có thể tự gửi `resource.tenantId` hoặc `role=admin` mà server không xác minh, biểu thức chính sách đúng về hình thức vẫn có thể cho kết quả sai.

Cũng cần kiểm soát quyền gán vai trò: một quản trị viên tenant không được tạo hoặc gán quyền nền tảng chỉ bằng cách chọn một tên vai trò trong request.

## 8. Chuyển tenant, phiên và thu hồi quyền

Khi Lan chuyển từ An Bình sang Minh Hải, ứng dụng cần thiết lập lại ngữ cảnh và tính lại quyền. Chỉ đổi tên tổ chức trên giao diện không đủ.

Một luồng chuyển tenant có thể thực hiện:

1. Nhận yêu cầu chọn tenant đích từ Lan.
2. Kiểm tra lại quan hệ thành viên với tenant đích.
3. Thiết lập ngữ cảnh hoặc cấp thông tin phiên/token phù hợp với thiết kế.
4. Làm mới dữ liệu và quyền hiển thị của tenant đích.
5. Bảo đảm request tiếp theo không tiếp tục dùng quyền của tenant trước.

Nếu một người mở hai tab cho hai tenant, mỗi request vẫn cần thể hiện phạm vi một cách nhất quán. Một biến “tenant đang chọn” dùng chung cho toàn bộ phiên có thể gây nhầm lẫn giữa các tab nếu thiết kế không tính đến trường hợp này.

Khi thành viên bị khóa hoặc vai trò bị thu hồi, quyền có thể còn tồn tại trong token, cache hay tác vụ đã xếp hàng. Hệ thống phải xác định khoảng thời gian chấp nhận thay đổi có hiệu lực và cơ chế thực hiện, chẳng hạn kiểm tra trạng thái hiện hành, làm mất hiệu lực cache hoặc giới hạn thời gian tồn tại của quyền đã chụp trong token.

Không được mặc định rằng xóa một bản ghi thành viên sẽ lập tức vô hiệu hóa mọi bản sao quyền đã phát hành.

## 9. Duy trì ranh giới ngoài API đồng bộ

### 9.1. Cache và kết quả phân quyền

Khóa cache cho dữ liệu hoặc quyền cần chứa đủ phạm vi của giá trị được lưu.

```text
Không đủ:
  contract:417
  permissions:user-73

Có phạm vi rõ hơn:
  contract:tenant-an-binh:417
  permissions:tenant-an-binh:user-73:<policy-version>
```

Mẫu khóa cụ thể tùy hệ thống. Nguyên tắc là không để kết quả tính cho một tenant được tái sử dụng cho tenant khác. Nếu quyết định còn phụ thuộc hành động, trạng thái tài nguyên hoặc điều kiện khác thì khóa và cơ chế làm mới cũng phải phản ánh các phụ thuộc đó.

### 9.2. Hàng đợi và công việc nền

Một job xuất hợp đồng cần mang thông tin đủ để bên xử lý xác định tenant, chủ thể yêu cầu, hành động và phạm vi dữ liệu.

```text
ExportJob
  tenantId = tenant-an-binh
  requestedBy = user-73
  operation = export_contracts
  selection = ...
```

Thông điệp có tenant ID chưa tự tạo ra quyền. Bên xử lý phải xác minh nguồn gửi và áp dụng mô hình ủy quyền đã định. Có hệ thống yêu cầu kiểm tra lại quyền lúc chạy; có hệ thống dùng một quyền ủy nhiệm giới hạn được cấp lúc tạo job. Lựa chọn đó cần được xác định tường minh, nhất là khi thành viên bị thu hồi trong lúc job chờ.

Dù theo mô hình nào, worker phải giới hạn truy vấn và tệp đầu ra vào tenant đã được chấp nhận. Thiếu tenant không được hiểu là “xuất toàn bộ”.

### 9.3. Dịch vụ nội bộ và danh tính workload

Một dịch vụ có khả năng truy cập nhiều tenant dễ trở thành nơi thực hiện nhầm yêu cầu thay cho bên gọi. Ngoài xác thực dịch vụ gọi, dịch vụ nhận cần biết tenant đích và lý do bên gọi có quyền yêu cầu hành động đó.

Nếu một workload chỉ phục vụ An Bình, quyền của nó nên giới hạn vào An Bình. Với workload phục vụ nhiều tenant, từng yêu cầu vẫn cần kiểm tra tenant và hành động được ủy nhiệm; không coi quyền kỹ thuật của tài khoản dịch vụ là quyền nghiệp vụ của người yêu cầu.

### 9.4. Tìm kiếm, tệp và kênh tích hợp

Các đường truy cập thường bị bỏ sót gồm:

- Bộ lọc tenant trong công cụ tìm kiếm và báo cáo tổng hợp.
- Phạm vi subscription và sự kiện trên kết nối thời gian thực.
- Quyền tạo đường dẫn tải tệp, cùng phạm vi và thời hạn của đường dẫn.
- Đích webhook và thông tin xác thực tích hợp thuộc từng tenant.
- Dữ liệu nhạy cảm được ghi vào log hoặc hiển thị trong thông báo lỗi.

Tên thư mục hoặc tiền tố của object chỉ là cách tổ chức dữ liệu nếu không có kiểm tra quyền tương ứng. Kiểm tra ở màn hình danh sách cũng không bảo vệ đường dẫn tải tệp được gọi trực tiếp.

## 10. Quyền hỗ trợ và truy cập xuyên tenant có chủ đích

Một số thao tác cần vượt qua ranh giới tenant thông thường, chẳng hạn hỗ trợ sự cố hoặc vận hành nền tảng. Những thao tác đó cần một đường cấp quyền riêng, có phạm vi và khả năng kiểm toán.

Một thiết kế có thể yêu cầu:

- Danh tính nền tảng chuyên biệt, tách khỏi vai trò quản trị tenant.
- Cấp quyền cho đúng tenant, đúng nhóm hành động và khoảng thời gian cần thiết.
- Xác thực tăng cường hoặc phê duyệt khi mức nhạy cảm yêu cầu.
- Ghi rõ người thực hiện thật, tenant đích, lý do và mã yêu cầu hỗ trợ.
- Thu hồi quyền và kết thúc ngữ cảnh đặc quyền sau khi xử lý.

Nếu hỗ trợ thao tác thay người dùng, audit cần phân biệt người thực hiện thật với người dùng được đại diện. Chỉ ghi danh tính được đại diện sẽ làm mất dấu vết trách nhiệm.

Tránh tạo một tham số như `ignoreTenant=true` cho API thông thường. Quyền xuyên tenant cần được kiểm soát như một năng lực riêng, không phải một nhánh tiện lợi có thể kích hoạt từ request.

Với chia sẻ tài nguyên hợp lệ giữa hai tenant, cần biểu diễn bên chia sẻ, bên nhận, tài nguyên, hành động được chia sẻ và điều kiện thu hồi. Thành viên của tenant nhận không vì vậy trở thành thành viên của tenant sở hữu.

## 11. Ví dụ phân tích một lỗi truy cập chéo tenant

API ban đầu nhận:

```http
GET /contracts/contract-417
Authorization: Bearer <token của người dùng Minh Hải>
```

Server kiểm tra token hợp lệ, thấy người dùng có vai trò `contract_viewer`, sau đó truy vấn hợp đồng theo ID. Hợp đồng `contract-417` của An Bình bị trả về.

Từng thành phần riêng lẻ có thể có vẻ hợp lệ: token đúng, vai trò cho phép đọc, ID tồn tại. Nhưng phép kết nối giữa chủ thể, tenant và tài nguyên đã bị thiếu.

Cách sửa về thiết kế là:

1. Xác lập tenant được phép cho request.
2. Tìm hợp đồng trong phạm vi tenant đó.
3. Đánh giá quyền đọc trong đúng tenant và trên đúng hợp đồng.
4. Áp dụng cùng nguyên tắc cho xem chi tiết, cập nhật, tìm kiếm và tải tệp.
5. Bổ sung kiểm thử đối nghịch giữa hai tenant.

Việc trả lỗi “không tìm thấy” hay “không có quyền” cần phù hợp với hợp đồng API và chính sách tiết lộ sự tồn tại tài nguyên. Dù chọn cách nào, không trả nội dung hoặc metadata nhạy cảm trước khi kiểm tra quyền hoàn tất.

## 12. Kiểm thử ranh giới bằng ít nhất hai tenant

Dùng An Bình và Minh Hải với dữ liệu, vai trò và thành viên riêng. Nên có cả trường hợp ID cục bộ trùng nhau để phát hiện các giả định sai về tính duy nhất.

| Tình huống | Kết quả cần đạt |
| --- | --- |
| Người xem An Bình đọc hợp đồng An Bình trong phạm vi được cấp | Được cho phép |
| Người xem Minh Hải thay ID để đọc hợp đồng An Bình | Không nhận dữ liệu của An Bình |
| Lan chuyển từ vai trò admin An Bình sang tenant Minh Hải | Chỉ còn quyền của Lan tại Minh Hải |
| URL chỉ An Bình nhưng thông tin xác thực chỉ có phạm vi Minh Hải | Request bị từ chối theo hợp đồng |
| Request thiếu tenant ở đường xử lý bắt buộc có tenant | Không dùng tenant mặc định để tiếp tục |
| Payload cập nhật cố đổi `tenant_id` của hợp đồng | Không chuyển tài nguyên qua đường cập nhật thông thường |
| Truy vấn danh sách hoặc xuất dữ liệu chứa ID của hai tenant | Không xử lý tài nguyên ngoài phạm vi được phép |
| Cache được làm nóng bằng dữ liệu An Bình rồi nhận request Minh Hải | Không trả lại dữ liệu hoặc quyền của An Bình |
| Job nền không có hoặc có tenant context không hợp lệ | Không chạy truy vấn toàn cục |
| Quản trị viên Minh Hải gọi API sửa cấu hình SSO của An Bình | Không thay đổi cấu hình của An Bình |
| Thành viên bị thu hồi trong lúc token hoặc job còn tồn tại | Hành vi đúng với chính sách thu hồi đã công bố |
| Hai request của hai tenant chạy đồng thời | Ngữ cảnh không bị trao đổi giữa các request |

Ngoài kết quả HTTP, cần quan sát tác động thực tế: bản ghi nào bị sửa, tệp nào được tạo, sự kiện nào được phát và audit ghi tenant nào. Một response bị từ chối sau khi side effect đã xảy ra vẫn là lỗi bảo vệ.

## 13. Những dấu hiệu thiết kế cần chú ý

Các dấu hiệu sau thường cho thấy ranh giới tenant chưa được thể hiện đầy đủ:

- Chỉ kiểm tra tenant trong giao diện mà không kiểm tra ở server.
- Vai trò quản trị tenant và quản trị nền tảng dùng chung một cờ `isAdmin`.
- Mỗi repository tự quyết định có cần lọc `tenant_id` hay không.
- Dùng email, tên miền hoặc ID khó đoán thay cho kiểm tra quan hệ thành viên.
- Dịch vụ nội bộ tin mọi tenant ID do một dịch vụ đã xác thực truyền vào.
- Cache, job nền và đường tải tệp không có phạm vi tenant.
- Cho phép trường tenant trong payload thay đổi quyền sở hữu dữ liệu.
- Không có bài kiểm thử với hai tenant độc lập.

Mục tiêu khi thiết kế IAM đa tenant là để phạm vi tenant xuất hiện rõ ràng trong danh tính thành viên, quyền, ngữ cảnh request và quyền sở hữu tài nguyên. Ranh giới đó phải được duy trì đến tận nơi dữ liệu được đọc, thay đổi hoặc gửi ra ngoài.
