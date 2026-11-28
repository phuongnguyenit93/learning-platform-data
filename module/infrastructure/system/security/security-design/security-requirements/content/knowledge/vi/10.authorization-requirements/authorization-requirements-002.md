# Authentication khác authorization

## 1. Hai câu hỏi khác nhau trong kiểm soát truy cập

**Authentication** là xác thực: hệ thống kiểm tra bằng chứng để xác lập chủ thể đang gửi yêu cầu. Chủ thể có thể là người dùng, ứng dụng hoặc dịch vụ. **Authorization** là phân quyền: hệ thống quyết định chủ thể đó có được thực hiện một hành động cụ thể trên một tài nguyên cụ thể trong bối cảnh hiện tại hay không.

Một người đăng nhập thành công có thể vẫn bị từ chối đọc hóa đơn của người khác. Một dịch vụ có chứng thư hợp lệ có thể vẫn không được gọi API quản trị. Ngược lại, một trang được công khai có thể cho phép người chưa đăng nhập đọc nội dung theo chính sách dành cho khách.

Sự khác biệt cốt lõi nằm ở **đối tượng của quyết định**:

- Xác thực đánh giá bằng chứng về danh tính hoặc quyền kiểm soát một phương thức đã đăng ký.
- Phân quyền đánh giá quyền thực hiện một hành động đối với tài nguyên và ngữ cảnh cụ thể.

Trong thiết kế yêu cầu bảo mật, không thể thay hai câu hỏi này bằng câu “chỉ người đã đăng nhập mới được sử dụng”. Yêu cầu cần nêu rõ ai được nhận diện bằng bằng chứng nào, rồi ai được làm gì, với dữ liệu nào và trong điều kiện nào. Đây là bước chuyển từ mục tiêu bảo vệ sang hành vi có thể triển khai, đo và kiểm chứng.

### 1.1. Một ví dụ ngắn

Lan và Minh đều là khách hàng của một cổng hóa đơn. Lan hoàn tất đăng nhập bằng mật khẩu và MFA, tức xác thực đa yếu tố. Hệ thống cấp cho Lan một phiên hợp lệ.

Lan gửi yêu cầu:

```http
GET /api/invoices/inv-204
Cookie: session=<ma-phien-minh-hoa>
```

Phiên cho biết chủ thể là Lan. Tuy nhiên, hóa đơn `inv-204` thuộc Minh. Nếu hệ thống trả hóa đơn chỉ vì phiên hợp lệ, hệ thống đã làm đúng một phần xác thực nhưng thiếu kiểm tra phân quyền đối với tài nguyên.

Yêu cầu đúng phải gồm hai điều kiện riêng:

1. Bằng chứng của yêu cầu được kiểm tra và gắn với tài khoản Lan.
2. Lan có quyền `invoice.read` đối với chính hóa đơn `inv-204` theo chính sách đang áp dụng.

Không có điều kiện thứ hai, đổi một mã hóa đơn trong URL có thể trở thành cách đọc dữ liệu của người khác. Mã tài nguyên khó đoán chỉ làm việc tìm mục tiêu khó hơn; nó không thay thế kiểm tra quyền.

## 2. Bảng phân biệt để viết đúng yêu cầu

| Khía cạnh | Authentication — xác thực | Authorization — phân quyền |
| --- | --- | --- |
| Câu hỏi | Chủ thể có bằng chứng hợp lệ cho danh tính được khai báo không? | Chủ thể có được làm hành động này với tài nguyên này không? |
| Đầu vào chính | Credential, thử thách, kết quả từ nhà cung cấp danh tính, trạng thái phiên. | Chủ thể, hành động, tài nguyên, chính sách và bối cảnh đáng tin. |
| Kết quả | Ngữ cảnh danh tính và thuộc tính xác thực, hoặc từ chối xác thực. | Cho phép, từ chối, hoặc yêu cầu điều kiện bổ sung theo thiết kế. |
| Ví dụ cơ chế | Mật khẩu, WebAuthn, MFA, kiểm tra phiên, xác thực dịch vụ bằng chứng thư. | Kiểm tra quyền, vai trò, quan hệ sở hữu, tenant, thuộc tính và trạng thái nghiệp vụ. |
| Thời điểm | Khi đăng nhập, khi kiểm tra bằng chứng trong yêu cầu, khi xác thực lại. | Tại các hành động được bảo vệ, kể cả sau khi người dùng đã đăng nhập. |
| Thay đổi làm mất hiệu lực | Credential bị thu hồi, phiên hết hạn, bằng chứng không hợp lệ. | Vai trò bị gỡ, tài nguyên đổi chủ, thành viên rời nhóm, chính sách thay đổi. |
| Lỗi thường gặp | Chấp nhận token sai bên phát hành, phiên giả hoặc bằng chứng bị phát lại. | Chỉ kiểm tra đăng nhập, bỏ kiểm tra quyền trên đối tượng hoặc tin vai trò từ client. |
| Bằng chứng kiểm thử | Bằng chứng sai, hết hạn hoặc không đúng mục đích bị từ chối. | Chủ thể hợp lệ nhưng không có quyền vẫn bị từ chối, không lộ dữ liệu hay tạo tác động. |

Credential là thông tin hoặc phương thức dùng để chứng minh quyền xác thực, chẳng hạn mật khẩu, khóa hoặc mã phiên. Ngữ cảnh danh tính sau xác thực thường được gọi là **principal**; nó biểu diễn chủ thể mà các thành phần tiếp theo sử dụng để quyết định truy cập.

Xác thực tài khoản không mặc nhiên xác minh danh tính pháp lý ngoài đời. Chứng minh đang kiểm soát một hộp thư cũng không tự chứng minh có quyền xem mọi dữ liệu liên quan đến địa chỉ đó. Mỗi kết luận phải giới hạn trong bằng chứng và chính sách của hệ thống.

## 3. Mô hình một yêu cầu truy cập

Một quyết định phân quyền có thể được mô tả bằng:

```text
Decision = Policy(Subject, Action, Resource, Context)
```

Trong đó:

- **Subject:** chủ thể, lấy từ ngữ cảnh đã được thiết lập theo chính sách; có thể là tài khoản, workload hoặc khách chưa đăng nhập.
- **Action:** hành động nghiệp vụ, như `invoice.read`, `invoice.approve` hoặc `member.remove`.
- **Resource:** tài nguyên và các thuộc tính liên quan, như chủ sở hữu, tenant và trạng thái hóa đơn.
- **Context:** điều kiện hiện tại, như phiên, mức xác thực, thời gian hoặc việc thao tác diễn ra trong quy trình được phê duyệt.

Workload là một đơn vị phần mềm đang thực thi, chẳng hạn dịch vụ hoặc tác vụ nền. Tenant là phạm vi khách hàng hoặc tổ chức được tách biệt trong một hệ thống dùng chung.

### 3.1. Nguồn dữ liệu phải đáng tin

Client có thể yêu cầu thao tác trên hóa đơn nào, nhưng không được tự quyết định hóa đơn đó thuộc ai. Client có thể chọn tenant muốn làm việc, nhưng lựa chọn đó chưa chứng minh tư cách thành viên. Client gửi `role=admin` cũng không biến principal thành quản trị viên.

| Thông tin | Cách sử dụng an toàn trong quyết định |
| --- | --- |
| Danh tính tài khoản | Lấy từ phiên hoặc token đã được kiểm tra theo giao thức và chính sách. |
| Vai trò, quyền | Lấy từ nguồn được phê duyệt, có quy tắc về độ mới và thu hồi. |
| Chủ sở hữu tài nguyên | Đọc từ trạng thái có thẩm quyền của hệ thống, không tin trường do client tự khai báo. |
| Tenant được yêu cầu | Xác minh quyền tham gia và phạm vi thao tác; không chỉ sao chép header. |
| Mức và thời điểm xác thực | Lấy từ bằng chứng đã được xác minh, không nhận cờ tự khai báo từ giao diện. |
| Trạng thái nghiệp vụ | Kiểm tra tại thời điểm phù hợp với giao dịch để tránh dùng trạng thái đã lỗi thời. |

Một chữ ký hợp lệ có thể chứng minh dữ liệu đến từ bên ký được tin cậy, nhưng vẫn cần xác định bên đó có thẩm quyền cung cấp thuộc tính cho quyết định này hay không. Chấp nhận mọi trường trong một token mà không xét mục đích, phạm vi và độ mới là một bước suy diễn nguy hiểm.

### 3.2. Xác thực được tái sử dụng nhưng phân quyền vẫn theo hành động

Không cần yêu cầu người dùng nhập lại mật khẩu ở mọi API. Hệ thống có thể kiểm tra phiên hoặc token để tái sử dụng ngữ cảnh xác thực còn hợp lệ. Tuy nhiên, mỗi hành động được bảo vệ phải đi qua kiểm tra quyền tương ứng; không suy ra quyền từ việc “đã kiểm tra ở màn hình trước”.

Với nội dung công khai, chính sách có thể cho phép chủ thể khách thực hiện `article.read`. Đó vẫn là một quyết định truy cập có chủ đích. Quy tắc mặc định từ chối cần đi cùng các quyền công khai được khai báo rõ, không biến thành giả định rằng mọi chức năng đều bắt buộc đăng nhập.

## 4. Nhầm lẫn hai quyết định dẫn đến những rủi ro nào?

### 4.1. Truy cập ngang: đúng tài khoản, sai tài nguyên

Lan đăng nhập hợp lệ rồi thay `invoiceId` để đọc hóa đơn của Minh. Kiểm tra phiên không phát hiện được vấn đề vì phiên thật sự thuộc Lan. Điều thiếu là kiểm tra quyền trên đúng đối tượng mà yêu cầu đang nhắm tới.

Yêu cầu nên viết:

> API đọc hóa đơn chỉ được trả dữ liệu khi principal có quyền đọc hóa đơn đó trong tenant đã được xác minh. Kiểm tra phải dùng thuộc tính sở hữu và phạm vi quyền từ nguồn có thẩm quyền. Việc thay mã hóa đơn không được làm vượt phạm vi truy cập.

### 4.2. Truy cập dọc: đúng người dùng, sai chức năng

Một nhân viên gửi trực tiếp yêu cầu tới API quản lý quyền, dù giao diện của họ không có nút quản trị. Nếu backend chỉ kiểm tra “đã đăng nhập”, việc ẩn nút không bảo vệ được chức năng.

Yêu cầu cần chỉ rõ quyền nghiệp vụ cho từng hành động đặc quyền. Việc API nằm dưới đường dẫn `/admin` hoặc nằm trong ứng dụng dành cho quản trị viên không tự tạo ra kiểm soát phân quyền.

### 4.3. Vượt ranh giới tenant

Một người có quyền quản lý hóa đơn tại tổ chức A không đương nhiên có cùng quyền tại tổ chức B. Nếu vai trò không có phạm vi, hoặc backend tin `X-Tenant-Id` do client gửi, tài khoản hợp lệ có thể truy cập chéo tổ chức.

Cần mô hình hóa quyền theo tenant và kiểm tra cả danh tính thành viên lẫn tài nguyên. “Quản trị viên” phải có định nghĩa phạm vi; quản trị một tenant và vận hành toàn nền tảng là hai loại quyền khác nhau.

### 4.4. Sửa thuộc tính nhạy cảm ngoài quyền

Người dùng được sửa hồ sơ không có nghĩa được sửa `role`, `tenantId`, trạng thái xác minh hoặc chủ sở hữu. Nếu backend đưa toàn bộ JSON vào đối tượng dữ liệu, một API sửa thông tin thông thường có thể trở thành đường nâng quyền.

Yêu cầu phân quyền cần bao gồm mức thuộc tính và hành động. Với các trường được máy chủ quản lý, quy định rõ trường bị cấm gửi, bị từ chối hay được bỏ qua có kiểm soát; không để hành vi phụ thuộc vào cách ánh xạ đối tượng tình cờ của framework.

### 4.5. Dịch vụ có danh tính hợp lệ nhưng thực hiện thay sai người

Một dịch vụ xuất báo cáo có quyền đọc nhiều dữ liệu để làm việc. Người dùng gửi yêu cầu xuất báo cáo không tự được hưởng toàn bộ quyền kỹ thuật của dịch vụ đó.

Cần phân biệt danh tính dịch vụ đang gọi và người dùng mà thao tác đại diện. Trong luồng ủy nhiệm của ví dụ này, chỉ cho phép khi cả dịch vụ được phép thực hiện loại tác vụ và người dùng có quyền đối với dữ liệu được xuất. Quyền thực thi phải bị giới hạn theo chính sách ủy nhiệm, không chỉ theo tài khoản dịch vụ mạnh nhất trên đường đi.

Nếu tác vụ là công việc hệ thống độc lập với người dùng, phải có yêu cầu riêng về phạm vi và mục đích. Không tự gắn một principal giả để né việc quyết định mô hình quyền.

## 5. Phân bổ kiểm soát trong kiến trúc

### 5.1. Luồng xử lý cho một API được bảo vệ

```text
Nhận yêu cầu
    -> Kiểm tra bằng chứng xác thực
    -> Thiết lập principal và ngữ cảnh đáng tin
    -> Xác định hành động, tenant và tài nguyên
    -> Đánh giá chính sách phân quyền
    -> Thực hiện trong phạm vi được cho phép
    -> Trả dữ liệu được phép và ghi sự kiện phù hợp
```

Luồng này mô tả API cần đăng nhập. API công khai có thể thiết lập chủ thể khách theo chính sách thay vì bắt có credential. Một số kiểm tra an toàn hoặc giới hạn tải có thể diễn ra sớm hơn; điều bắt buộc là không đọc ra dữ liệu cho client hoặc tạo tác động được bảo vệ trước khi kiểm tra quyền cần thiết đã đạt.

Gateway có thể kiểm tra token và quyền gọi nhóm API. Backend hiểu tài nguyên và nghiệp vụ thường vẫn phải kiểm tra quyền trên đối tượng, tenant và trạng thái. Nếu một kênh nội bộ, job hoặc API khác đi vòng gateway, yêu cầu bảo vệ tài nguyên vẫn phải được thực hiện ở điểm có trách nhiệm.

### 5.2. Ví dụ mã giả

Đoạn dưới đây minh họa trách nhiệm, không phụ thuộc vào framework hoặc thư viện cụ thể:

```text
principal = authentication.requireValidPrincipal(request.credentials)

tenant = membership.requireActiveMembership(
    principal,
    request.selectedTenantId
)

invoice = invoiceRepository.findByIdWithinTenant(
    request.invoiceId,
    tenant.id
)

if invoice is absent:
    return responseAccordingToDisclosurePolicy()

decision = authorization.evaluate(
    subject = principal,
    action = "invoice.read",
    resource = invoice,
    context = trustedContext(tenant)
)

if decision is not PERMIT:
    return responseAccordingToDisclosurePolicy()

return invoiceView.allowedFields(principal, invoice)
```

Tư cách thành viên không thay thế quyền đọc hóa đơn. Tên hàm `requireActiveMembership` chỉ thể hiện một điều kiện đầu vào. Quyết định `invoice.read` vẫn cần chính sách phù hợp, chẳng hạn cho chủ sở hữu hoặc nhân viên có quyền đọc trong phạm vi được cấp.

Tương tự, việc truy vấn theo tenant giúp giới hạn phạm vi nhưng không tự giải quyết quyền trên từng đối tượng bên trong tenant. Lớp trả dữ liệu cũng cần bảo đảm không đưa thêm các trường mà principal không được xem.

### 5.3. Các mô hình quyền hỗ trợ quyết định

| Cách mô hình hóa | Vai trò trong authorization | Điểm cần đặc tả |
| --- | --- | --- |
| RBAC — quyền theo vai trò | Gắn tập quyền với vai trò rồi gán vai trò cho chủ thể. | Phạm vi vai trò, quyền thành phần và ai được cấp/gỡ vai trò. |
| ABAC — quyền theo thuộc tính | Đánh giá thuộc tính chủ thể, tài nguyên và bối cảnh. | Nguồn thuộc tính, độ mới và cách xử lý thiếu hoặc mâu thuẫn. |
| Quyền theo quan hệ | Dùng quan hệ như thành viên dự án, chủ sở hữu hoặc người được chia sẻ. | Quan hệ nào được phép tạo, kế thừa ra sao và khi nào bị thu hồi. |

Các mô hình có thể phối hợp. Với hóa đơn, nhân viên có vai trò kế toán, thuộc đúng tenant và chỉ được sửa khi hóa đơn còn ở trạng thái nháp. Đây vẫn là một quyết định phân quyền; cách mô hình hóa không làm thay đổi sự khác biệt với xác thực.

## 6. Token, OAuth và MFA không tự cấp quyền nghiệp vụ

### 6.1. Token hợp lệ còn thiếu điều gì?

Một token có chữ ký hợp lệ chưa đủ để được ứng dụng chấp nhận. Bên nhận còn phải kiểm tra bên phát hành, bên nhận dự kiến, thời hạn, loại sử dụng và các ràng buộc của giao thức. Sau khi chấp nhận ngữ cảnh danh tính, hệ thống vẫn cần quyết định quyền đối với thao tác đang được yêu cầu.

JWT là một định dạng token có thể mang các thuộc tính, không phải một mô hình phân quyền. Một trường `role` trong JWT cần được hiểu theo nguồn phát, phạm vi, thời điểm cấp và chính sách thu hồi. Nếu tài khoản bị gỡ quyền sau khi token được cấp, quyết định chỉ dựa vào token cũ có thể tiếp tục cho phép trong khoảng thời gian không còn phù hợp.

Yêu cầu cần chốt độ trễ chấp nhận được của thay đổi quyền. Ví dụ giả định: việc gỡ quyền phê duyệt có hiệu lực tại mọi API phê duyệt trong tối đa 30 giây sau khi thay đổi được xác nhận. Kiến trúc có thể dùng tra cứu trạng thái, phiên bản quyền hoặc cơ chế lưu đệm với giới hạn phù hợp; chỉ ghi “JWT hết hạn sau một giờ” không đáp ứng lời hứa 30 giây.

### 6.2. OAuth và đăng nhập liên kết

OAuth là khuôn khổ ủy quyền truy cập; OpenID Connect bổ sung lớp danh tính phục vụ các luồng đăng nhập phù hợp. Không nên dùng câu “có OAuth nên đã đăng nhập và có đủ quyền” để bỏ qua hai quyết định.

Access token và scope có thể giới hạn quyền mà client được cấp để gọi API. Tuy nhiên, scope như `invoice.read` không mặc nhiên cho phép đọc mọi hóa đơn. API vẫn phải thực thi giới hạn người dùng, tenant, tài nguyên và các điều kiện mà chính sách yêu cầu. Nếu hệ thống chọn mô hình cấp quyền toàn bộ cho một phạm vi tài nguyên, đó phải là quyết định được đặc tả rõ, không phải suy đoán từ tên scope.

ID token phục vụ thông tin về lần xác thực cho client theo OIDC; không mặc định dùng nó thay access token cho mọi API. Dùng đúng loại token là điều kiện về giao thức, còn quyền nghiệp vụ vẫn cần kiểm tra tại bên tài nguyên.

### 6.3. MFA và xác thực lại chỉ đáp ứng một điều kiện

Một hành động nhạy cảm có thể yêu cầu xác thực mới hoặc phương thức mạnh hơn. Ví dụ, quản trị viên cần bằng chứng MFA mới không quá năm phút trước khi đổi chính sách quyền.

Khi đó phải có đồng thời:

1. Principal có quyền đổi chính sách trong phạm vi liên quan.
2. Phiên đáp ứng điều kiện về phương thức và độ mới của xác thực.

Người không có quyền quản trị dù hoàn thành MFA vẫn phải bị từ chối. Ngược lại, người có quyền nhưng bằng chứng xác thực quá cũ có thể được yêu cầu xác thực bổ sung, sau đó hệ thống phải kiểm tra lại quyền tại thời điểm thực hiện. Một bước MFA thành công không được biến thành quyền quản trị dùng chung cho các thao tác khác.

## 7. Từ mục tiêu bảo vệ đến ma trận quyền và đặc tả API

### 7.1. Tình huống hóa đơn nhiều tenant

Giả sử cổng hóa đơn có ba nhóm chủ thể: khách hàng, nhân viên kế toán và người quản trị quyền trong từng tenant. Các quyền dưới đây là chính sách minh họa của sản phẩm này, không phải quy tắc chung cho mọi hệ thống hóa đơn.

| Chủ thể | Đọc hóa đơn | Sửa hóa đơn | Phê duyệt hóa đơn | Cấp quyền người dùng |
| --- | --- | --- | --- | --- |
| Khách chưa đăng nhập | Không. | Không. | Không. | Không. |
| Khách hàng | Hóa đơn của mình trong tenant hợp lệ. | Không. | Không. | Không. |
| Nhân viên có `invoice.read` | Hóa đơn trong tenant và phạm vi công việc được cấp. | Chỉ khi có thêm `invoice.edit`, hóa đơn nháp và thuộc phạm vi. | Không nếu thiếu `invoice.approve`. | Không. |
| Nhân viên có `invoice.approve` | Theo quyền đọc riêng được cấp. | Theo quyền sửa riêng được cấp. | Hóa đơn thuộc phạm vi và thỏa điều kiện nghiệp vụ; không tự phê duyệt hóa đơn mình tạo. | Không. |
| Quản trị quyền của tenant | Theo quyền dữ liệu được cấp riêng. | Theo quyền dữ liệu được cấp riêng. | Theo quyền nghiệp vụ được cấp riêng. | Chỉ trong tenant và tập quyền được phép cấp. |

Ma trận tách quyền quản trị tài khoản khỏi quyền đọc dữ liệu nghiệp vụ. Một sản phẩm có thể chọn chính sách khác, nhưng phải ghi rõ thay vì để vai trò `admin` mặc nhiên vượt mọi ranh giới.

Các điều kiện như “không tự phê duyệt” thuộc kiểm soát nghiệp vụ và phân quyền, không được giải quyết bằng cách yêu cầu người tạo nhập lại mật khẩu. Người đó vẫn là cùng một principal sau xác thực lại.

### 7.2. Ví dụ đặc tả cho API phê duyệt

**Mã yêu cầu:** AZ-APPROVE-01.

**Mục tiêu:** ngăn người dùng hợp lệ phê duyệt hóa đơn ngoài phạm vi hoặc tự phê duyệt hóa đơn mình tạo.

**Phạm vi:** mọi đường có khả năng chuyển hóa đơn từ chờ duyệt sang đã duyệt, gồm API trực tiếp, thao tác hàng loạt và tác vụ xử lý thay mặt người dùng.

**Điều kiện xác thực:** yêu cầu phải có principal hợp lệ theo chính sách phiên; bằng chứng sai, hết hạn hoặc không dành cho API này không được tạo principal được chấp nhận.

**Điều kiện phân quyền:**

1. Principal đang là thành viên hoạt động của tenant chứa hóa đơn.
2. Principal có quyền `invoice.approve` trong phạm vi bao gồm hóa đơn đó.
3. Principal không phải người tạo hóa đơn, theo quy tắc tách trách nhiệm của tình huống này.
4. Hóa đơn đang ở trạng thái chờ duyệt và phiên bản dữ liệu phù hợp với giao dịch được thực hiện.
5. Nếu thao tác yêu cầu xác thực mới, bằng chứng phải đáp ứng đúng phương thức và thời hạn theo chính sách; điều này không thay thế bốn điều kiện trên.

**Hành vi từ chối:** nếu bất kỳ điều kiện bắt buộc nào không đạt hoặc không thể xác minh bằng nguồn tin cậy còn hiệu lực, hệ thống không được chuyển trạng thái, gửi lệnh thanh toán hay phát sự kiện “đã phê duyệt”. Phản hồi cho client tuân thủ chính sách tiết lộ tài nguyên, không trả kèm dữ liệu hóa đơn ngoài quyền.

**Tính nhất quán:** kiểm tra trạng thái, người tạo và phạm vi áp dụng phải gắn với phiên bản dữ liệu thực sự được phê duyệt. Nếu hóa đơn thay đổi trong lúc xử lý, thao tác phải kiểm tra lại hoặc thất bại theo quy tắc đồng thời đã xác định. Có thể dùng giao dịch, kiểm tra phiên bản hoặc cập nhật có điều kiện; một kiểm tra tách rời từ trước không tự bảo đảm trạng thái vẫn đúng lúc ghi.

**Thu hồi quyền:** trong ví dụ này, quyền `invoice.approve` bị gỡ phải ngừng được chấp nhận tại mọi điểm thực thi trong tối đa 30 giây từ khi thay đổi quyền được xác nhận. Mỗi yêu cầu mới hoặc lần thực thi job sau hạn đó phải dùng trạng thái đáp ứng giới hạn. Một quyền đã kiểm tra khi đưa job vào hàng đợi không đủ để job dùng mãi về sau.

Giới hạn 30 giây là cửa sổ thu hồi được chấp nhận trong giả định thiết kế, không có nghĩa thu hồi tức thời. Nếu rủi ro yêu cầu chặn ngay hoặc bao phủ cả thao tác đang chạy, phải đặc tả cơ chế và thời điểm hiệu lực mạnh hơn, đồng thời kiểm chứng khả năng thực hiện.

**Bằng chứng:** kiểm thử API, kiểm thử thay đổi quyền và dữ liệu đồng thời, đối chiếu trạng thái hóa đơn, sự kiện nghiệp vụ và các tác động bên ngoài. Không chỉ kiểm tra mã phản hồi.

### 7.3. Danh sách, thuộc tính, xuất tệp và thao tác hàng loạt

Kiểm tra quyền ở một API đọc chi tiết không tự bảo vệ các đường khác:

- Danh sách và tìm kiếm phải giới hạn tập tài nguyên trước khi trả dữ liệu, phân trang và tính tổng mà client được phép thấy. Lọc sau khi đã tính tổng có thể lộ số lượng dữ liệu ngoài quyền.
- Phản hồi phải giới hạn trường nhạy cảm; quyền xem hóa đơn không mặc nhiên cho phép xem mọi ghi chú nội bộ hoặc thông tin thanh toán.
- Thao tác hàng loạt phải có chính sách rõ: tất cả cùng thành công hoặc trả kết quả từng phần được phép tiết lộ. Mỗi tài nguyên vẫn cần điều kiện quyền tương ứng.
- Job xuất dữ liệu phải xác định chủ thể đại diện và kiểm tra quyền tại thời điểm thực thi theo chính sách. Quyền tải kết quả cũng phải được đánh giá hoặc được cấp bằng một cơ chế giới hạn rõ ràng.
- Liên kết tải có chữ ký là một dạng khả năng truy cập được cấp cho người giữ liên kết trong phạm vi nhất định. Nó cần giới hạn tài nguyên, hành động, thời hạn và cách xử lý lộ hoặc thu hồi; không được coi là công khai chỉ vì không có màn hình đăng nhập.

## 8. Liên kết yêu cầu với rủi ro và bằng chứng

Các mã dưới đây minh họa một chuỗi truy vết gọn. Ngưỡng thời gian và phạm vi phải được chốt trong thiết kế thực tế trước khi nghiệm thu.

| Mã | Rủi ro cần giảm | Yêu cầu có thể kiểm chứng | Bằng chứng tiêu biểu |
| --- | --- | --- | --- |
| AN-01 | Giả mạo principal bằng phiên hoặc token không hợp lệ. | Mọi API hóa đơn yêu cầu principal được thiết lập từ bằng chứng hợp lệ theo đúng bên phát hành, bên nhận, thời hạn và chính sách giao thức. | Sai chữ ký, sai bên nhận, phiên hết hạn đều không được truy cập API được bảo vệ. |
| AZ-01 | Đọc hóa đơn của người khác bằng cách đổi ID. | API chỉ trả đối tượng khi principal có `invoice.read` trên chính đối tượng trong tenant đã xác minh. | Hai tài khoản cùng đăng nhập hợp lệ nhưng không đọc chéo hóa đơn ngoài quyền. |
| AZ-02 | Người thường gọi trực tiếp chức năng quản trị. | Mọi đường cấp quyền phải kiểm tra quyền quản trị tương ứng ở backend. | Gọi API bằng principal không có quyền vẫn bị từ chối, dù bỏ qua giao diện. |
| AZ-03 | Truy cập chéo tenant. | Tư cách thành viên, phạm vi quyền và tenant của tài nguyên phải phù hợp; client không tự xác nhận tenant. | Thay header, đường dẫn hoặc ID chéo tenant không lộ dữ liệu hoặc tạo tác động. |
| AZ-04 | Nâng quyền qua trường dữ liệu. | API sửa hồ sơ không chấp nhận thay đổi vai trò, tenant hoặc thuộc tính do máy chủ quản lý ngoài luồng được phép. | Gửi thêm trường nhạy cảm không làm thay đổi trạng thái quyền. |
| AZ-05 | Quyền đã gỡ vẫn có hiệu lực qua token cũ. | Gỡ quyền phê duyệt có hiệu lực tại các điểm thực thi trong tối đa 30 giây theo chính sách minh họa. | Token còn hạn nhưng quyền đã bị gỡ không phê duyệt được sau cửa sổ này. |
| AZ-06 | Dịch vụ làm thay người dùng với quyền quá rộng. | Luồng ủy nhiệm phải kiểm tra quyền dịch vụ và quyền chủ thể được đại diện trên tài nguyên. | Dịch vụ hợp lệ không xuất dữ liệu ngoài quyền người yêu cầu. |
| AZ-07 | Dùng lỗi phụ thuộc để bỏ kiểm tra quyền. | Không thực hiện thao tác khi không có quyết định cho phép từ nguồn chính sách còn hiệu lực. | Hết hạn cache và mất nguồn quyền dẫn tới hành vi từ chối đã định nghĩa. |
| AZ-08 | Nhầm MFA thành quyền quản trị. | Thao tác đặc quyền phải đồng thời đáp ứng quyền nghiệp vụ và điều kiện xác thực bổ sung. | Người không có quyền dù MFA thành công vẫn bị từ chối. |

AN-01 và AZ-01 giải quyết hai rủi ro khác nhau. Một ca kiểm thử token sai không chứng minh AZ-01. Muốn kiểm tra phân quyền, cần một principal hợp lệ nhưng không có quyền đối với hành động hoặc tài nguyên đang thử.

Yêu cầu “không có quyết định cho phép thì không thực hiện” không bắt buộc mọi yêu cầu đều gọi từ xa tới một bộ máy chính sách. Dữ liệu hoặc quyết định lưu đệm có thể được sử dụng nếu thiết kế đã quy định phạm vi, độ mới và giới hạn thu hồi; khi không còn đáp ứng các điều kiện đó, hệ thống không được tự cho phép vì phụ thuộc đang lỗi.

## 9. Thiết kế kiểm thử để không nhầm hai lớp bảo vệ

### 9.1. Giữ bằng chứng hợp lệ khi kiểm tra phân quyền

Một bộ kiểm thử nên thay đổi có chủ đích từng nhóm điều kiện:

| Ca | Xác thực | Điều kiện phân quyền | Kết quả cần quan sát |
| --- | --- | --- | --- |
| Không có phiên | Thiếu bằng chứng cho API cần đăng nhập. | Chưa có principal được chấp nhận. | Không trả dữ liệu hóa đơn, không thực hiện tác động. |
| Phiên giả hoặc hết hạn | Không hợp lệ. | Không sử dụng principal tự khai báo. | Từ chối theo chính sách xác thực. |
| Đúng chủ sở hữu | Hợp lệ. | Đúng tenant, đúng quyền, đúng tài nguyên. | Trả đúng trường được phép. |
| Sai chủ sở hữu | Hợp lệ. | Không có quyền trên hóa đơn của người khác. | Từ chối, không kèm dữ liệu của đối tượng đó. |
| Sai tenant | Hợp lệ. | Có vai trò ở A nhưng yêu cầu tài nguyên B. | Không được dùng vai trò ở A để truy cập B. |
| Thiếu quyền chức năng | Hợp lệ. | Không có `invoice.approve`. | Không chuyển trạng thái hóa đơn. |
| Tự phê duyệt | Hợp lệ. | Có quyền phê duyệt nhưng là người tạo. | Từ chối theo quy tắc tách trách nhiệm. |
| MFA mạnh nhưng thiếu quyền | Hợp lệ, đủ mức xác thực. | Không có quyền quản trị. | Không thực hiện thao tác quản trị. |
| Quyền bị gỡ | Phiên còn hợp lệ. | Quyền phê duyệt đã bị gỡ và quá cửa sổ hiệu lực. | Không phê duyệt được bằng token cũ. |
| Nguồn quyền không khả dụng | Bằng chứng xác thực vẫn hợp lệ. | Không có dữ liệu hoặc quyết định còn hiệu lực để cho phép. | Không tự chuyển sang cho phép. |

Ca được cho phép cũng cần thiết. Nếu mọi yêu cầu đều bị từ chối do cấu hình sai, các ca phủ định có thể vượt qua nhưng sản phẩm không đáp ứng yêu cầu sử dụng hợp lệ.

### 9.2. Kiểm tra cả dữ liệu và tác động

Không chỉ xác nhận HTTP trả lỗi. Với yêu cầu bị từ chối, cần đối chiếu:

- Nội dung phản hồi, header và thông tin lỗi không chứa dữ liệu ngoài quyền.
- Cơ sở dữ liệu không bị thay đổi bởi thao tác được bảo vệ.
- Không tạo job, phát sự kiện thành công, gửi thông báo hoặc gọi hệ thống bên ngoài như thể đã được cho phép.
- Bộ đếm, tệp xuất và kết quả tìm kiếm không tiết lộ gián tiếp tài nguyên bị hạn chế ngoài chính sách công bố.

Với thao tác hàng loạt, trộn ID được phép và không được phép để kiểm tra đúng quy tắc tất cả hoặc từng phần. Với job, gỡ quyền sau khi tạo job nhưng trước thời điểm thực thi. Với dữ liệu thay đổi đồng thời, đổi trạng thái hóa đơn giữa lúc yêu cầu bắt đầu và lúc cập nhật để kiểm tra ràng buộc còn đúng tại thời điểm ghi.

### 9.3. Đo giới hạn thu hồi

Để kiểm tra yêu cầu 30 giây, cần xác định mốc bắt đầu là thời điểm hệ thống xác nhận gỡ quyền, rồi gửi yêu cầu tới các nút và kênh thực thi liên quan bằng cùng phiên còn hạn. Sau hạn đó, không điểm nào trong phạm vi được tiếp tục chấp nhận quyền đã gỡ.

Cần thử cả nút có cache, kết nối đang tồn tại và job mới đến lượt thực thi. Một phép thử chỉ đăng xuất rồi đăng nhập lại không chứng minh token cũ đã bị hạn chế đúng thời gian. Nếu không thể đáp ứng giới hạn đã cam kết, phải sửa cơ chế hoặc đưa giới hạn thực tế vào quyết định rủi ro được phê duyệt.

## 10. Phản hồi và logging phải phản ánh đúng quyết định

### 10.1. Không suy ra mọi trường hợp từ một mã HTTP

Trong nhiều API HTTP, `401` dùng khi yêu cầu thiếu hoặc không có bằng chứng xác thực hợp lệ; `403` thường dùng khi từ chối thực hiện dù đã có ngữ cảnh phù hợp để đánh giá quyền. Một hệ thống có thể dùng phản hồi giống `404` để hạn chế tiết lộ sự tồn tại của tài nguyên theo chính sách đã chọn.

Đặc tả phải nêu hành vi cho từng luồng, gồm cả các yêu cầu của cơ chế xác thực HTTP đang dùng. Không chọn mã phản hồi rồi xem như đã hoàn thành kiểm soát. Một phản hồi `403` sau khi dữ liệu đã được trả hoặc tác động đã xảy ra vẫn không đáp ứng yêu cầu bảo vệ.

Khi cần che sự tồn tại của đối tượng, phải xem xét cả nội dung, cấu trúc lỗi, dữ liệu phân trang và các khác biệt có thể khai thác. Việc đổi riêng mã phản hồi không tự loại bỏ mọi kênh suy đoán.

### 10.2. Tách sự kiện xác thực và quyết định truy cập

Một phiên hợp lệ bị từ chối đọc hóa đơn ngoài quyền nên tạo dấu vết quyết định phân quyền phù hợp, không bị ghi nhầm thành “mật khẩu sai”. Nếu gộp mọi lỗi truy cập vào số lần đăng nhập thất bại, cảnh báo và cơ chế khóa tài khoản có thể hoạt động sai.

Sự kiện phân quyền có thể chứa mã chủ thể nội bộ, hành động, tham chiếu tài nguyên phù hợp chính sách, tenant, kết quả, mã nguyên nhân, phiên bản chính sách và mã tương quan. Thông tin về yếu tố hoặc thời điểm xác thực có thể được liên kết khi cần giải thích quyết định.

Không ghi mật khẩu, mã MFA, cookie hoặc token truy cập. Không sao chép nội dung hóa đơn ngoài quyền vào log chỉ để giải thích vì sao từ chối. Quyền đọc log và thời hạn lưu cũng cần đặc tả vì các sự kiện này có thể tiết lộ quan hệ giữa chủ thể và tài nguyên.

## 11. Những cách viết yêu cầu cần sửa

| Cách viết chưa đủ | Vấn đề | Cách làm rõ |
| --- | --- | --- |
| “Chỉ người đăng nhập mới xem được hóa đơn.” | Chưa giới hạn hóa đơn nào, tenant nào và trường nào. | Nêu quyền, tài nguyên, phạm vi và điều kiện trả dữ liệu. |
| “Có JWT nên API đã bảo mật.” | Định dạng token không chứng minh xác thực đúng hoặc có kiểm tra quyền. | Tách yêu cầu kiểm tra bằng chứng khỏi quyết định truy cập. |
| “Ẩn nút quản trị với người thường.” | Người dùng vẫn gọi trực tiếp backend. | Đặc tả kiểm tra quyền tại mọi đường thực thi chức năng. |
| “Admin được làm mọi việc.” | Không rõ phạm vi tenant, dữ liệu và trách nhiệm cấp quyền. | Liệt kê quyền và giới hạn rõ cho từng loại quản trị. |
| “Nhập lại mật khẩu để được phê duyệt.” | Tăng độ tin cậy danh tính nhưng chưa có quyền phê duyệt. | Yêu cầu đồng thời quyền nghiệp vụ và điều kiện xác thực cần thiết. |
| “Quyền được cập nhật ngay.” | Không có mốc thời gian hoặc giới hạn cho token, cache và job. | Chốt thời điểm hiệu lực, giới hạn đo được và điểm phải áp dụng. |
| “Dịch vụ nội bộ đã được tin cậy.” | Danh tính dịch vụ không xác định đủ quyền và chủ thể được đại diện. | Nêu hành động, tài nguyên và quy tắc ủy nhiệm cụ thể. |

Khi duy trì yêu cầu qua vòng đời phát triển, cần giữ liên kết từ rủi ro tới mã yêu cầu, thành phần thực thi và bằng chứng kiểm thử. Thêm một API xuất dữ liệu, đổi mô hình tenant hoặc chuyển công việc sang xử lý nền đều có thể tạo đường truy cập chưa được kiểm soát.

Chủ sở hữu yêu cầu phải xác định các điểm cần cập nhật khi vai trò, chính sách hoặc giao thức xác thực thay đổi. Bằng chứng rằng “đăng nhập vẫn hoạt động” sau thay đổi không chứng minh quyền trên dữ liệu vẫn đúng; ngược lại, một ma trận quyền đúng cũng không chứng minh token được kiểm tra an toàn.

## 12. Bài tập áp dụng

Một nhóm đưa ra yêu cầu: “API báo cáo chỉ dành cho nhân viên đã đăng nhập bằng MFA; tài khoản quản trị được tải mọi báo cáo.”

Hãy hoàn thiện yêu cầu bằng các bước sau:

1. Tách yêu cầu về danh tính, phương thức xác thực và độ mới của bằng chứng khỏi yêu cầu về quyền tải báo cáo.
2. Xác định báo cáo thuộc tenant, dự án hoặc chủ sở hữu nào; làm rõ phạm vi của quản trị viên.
3. Viết điều kiện quyền cho xem danh sách, xem chi tiết, tạo bản xuất và tải tệp đã tạo.
4. Chốt hành vi khi gỡ quyền trong thời gian job đang chờ, khi cache cũ và khi nguồn chính sách bị lỗi.
5. Tạo ca kiểm thử cho một principal hợp lệ nhưng sai tài nguyên, sai tenant, thiếu quyền và có MFA nhưng không có quyền quản trị.

Ví dụ một phần đáp án: MFA là điều kiện xác thực của phiên, còn quyền `report.export` quyết định khả năng yêu cầu xuất trong phạm vi được cấp. Job phải giữ ngữ cảnh người yêu cầu và kiểm tra quyền khi thực thi theo giới hạn thu hồi đã chốt. Kết quả chỉ chứa dữ liệu được phép và đường tải phải đáp ứng chính sách truy cập riêng. Việc dịch vụ xuất báo cáo có danh tính hợp lệ không cho phép nó bỏ qua phạm vi của người được đại diện.

Một đặc tả rõ ràng cho phép trả lời độc lập hai câu hỏi: bằng chứng nào khiến hệ thống chấp nhận principal, và chính sách nào cho phép principal thực hiện hành động trên tài nguyên cụ thể. Khi cả hai được gắn với rủi ro và tiêu chí kiểm thử, nhóm có thể chứng minh hệ thống vừa nhận diện đúng chủ thể vừa giới hạn đúng khả năng truy cập.
