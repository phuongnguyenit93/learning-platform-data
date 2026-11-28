# Kiểm tra authorization ở server

## 1. Vì sao server phải tự quyết định quyền truy cập?

**Authorization** là quyết định một chủ thể có được thực hiện một hành động trên một tài nguyên trong bối cảnh cụ thể hay không. Kiểm tra authorization ở server nghĩa là thành phần thực thi phía máy chủ phải dựa vào danh tính, dữ liệu và chính sách đáng tin để cho phép hoặc từ chối trước khi trả dữ liệu được bảo vệ hay tạo tác động nghiệp vụ.

Giao diện có thể ẩn nút xóa, vô hiệu hóa ô sửa hoặc chỉ hiển thị các tài liệu được phép. Những hành vi đó giúp trải nghiệm sử dụng rõ ràng, nhưng người dùng vẫn có thể gửi yêu cầu HTTP trực tiếp, sửa payload, gọi một phiên bản API khác hoặc sử dụng client do họ tự viết. Vì vậy, giao diện không phải nơi quyết định cuối cùng về quyền.

Một yêu cầu như “chỉ quản trị viên thấy nút xóa” chưa cam kết rằng người không có quyền không thể xóa. Yêu cầu phía server cần cụ thể hơn:

> Mọi đường thực thi xóa tài liệu phải kiểm tra quyền `document.delete` của principal trên chính tài liệu trong tenant đã được xác minh. Nếu không có quyết định cho phép còn hiệu lực, hệ thống không được xóa, tạo job xóa hoặc phát sự kiện như thể thao tác đã thành công.

Principal là biểu diễn chủ thể được hệ thống chấp nhận sau khi kiểm tra bằng chứng xác thực. Tenant là phạm vi tổ chức hoặc khách hàng trong một hệ thống dùng chung. Chỉ biết principal đang đăng nhập không đủ để biết họ được xóa tài liệu nào.

Trong thiết kế yêu cầu bảo mật, mục tiêu là biến nguyên tắc “kiểm tra ở server” thành các cam kết về phạm vi, thời điểm, nguồn dữ liệu, hành vi khi lỗi và bằng chứng kiểm thử.

### 1.1. Xác thực và phân quyền vẫn là hai việc khác nhau

| Kiểm tra | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Authentication — xác thực | Bằng chứng có hợp lệ để thiết lập chủ thể không? | Phiên hoặc token được kiểm tra theo chính sách và gắn với tài khoản Lan. |
| Authorization — phân quyền | Chủ thể có được làm hành động này với tài nguyên này không? | Lan có được sửa tài liệu của Minh trong tenant hiện tại không? |

Token có chữ ký hợp lệ hoặc phiên còn hạn chỉ cung cấp một phần đầu vào. Server vẫn cần quyết định quyền nghiệp vụ. Ngược lại, API công khai có thể cho chủ thể khách đọc một số nội dung theo chính sách rõ ràng; không phải mọi endpoint đều bắt buộc đăng nhập, nhưng mọi quyền truy cập cần được xác định có chủ đích.

## 2. Từ mô hình đe dọa đến phạm vi thực thi

Giả sử một cổng tài liệu có người dùng cá nhân, người được chia sẻ quyền sửa và quản trị viên trong từng tenant. Tài liệu có trạng thái nháp hoặc đã khóa; tệp đính kèm và chức năng xuất dữ liệu được xử lý qua các thành phần riêng.

Chính sách minh họa:

- Người dùng chỉ hoạt động trong tenant mà họ là thành viên hợp lệ.
- Chủ sở hữu hoặc người được chia sẻ quyền phù hợp có thể đọc, sửa theo trạng thái tài liệu.
- Xóa và quản lý chia sẻ là các quyền riêng, không được suy ra từ quyền đọc.
- Quản trị quyền không tự đồng nghĩa với quyền đọc toàn bộ nội dung.
- Job làm thay người dùng phải tuân theo phạm vi được ủy nhiệm, không dùng toàn bộ quyền kỹ thuật của worker thay cho quyền người yêu cầu.

Các ngưỡng thời gian trong bài là giả định thiết kế của tình huống này, cần điều chỉnh theo rủi ro và khả năng vận hành của hệ thống thật.

### 2.1. Các rủi ro cần chuyển thành yêu cầu

| Mã | Kịch bản | Điều server phải bảo đảm |
| --- | --- | --- |
| R-S01 | Người dùng gọi trực tiếp API mà giao diện không hiển thị. | Kiểm tra quyền chức năng tại đường thực thi thực tế. |
| R-S02 | Thay ID tài nguyên, tenant hoặc ID tài nguyên con. | Kiểm tra đúng đối tượng và ranh giới tenant. |
| R-S03 | Gửi thêm vai trò, owner hoặc trường nhạy cảm trong payload. | Không tin thuộc tính quyền do client tự khai báo; giới hạn trường được sửa. |
| R-S04 | Bỏ qua gateway hoặc gọi một kênh cũ không có kiểm tra. | Mọi đường vào được bảo vệ, kể cả nội bộ và xử lý nền. |
| R-S05 | Quyền hoặc trạng thái thay đổi sau kiểm tra nhưng trước cập nhật. | Kiểm tra và tác động có tính nhất quán phù hợp. |
| R-S06 | Cache cũ hoặc lỗi dịch vụ chính sách bị biến thành cho phép. | Độ mới và hành vi lỗi được quy định, không tự mở quyền. |
| R-S07 | Dịch vụ có quyền rộng bị lợi dụng để thao tác thay sai người. | Ràng buộc danh tính dịch vụ với quyền của chủ thể được đại diện. |
| R-S08 | API trả lỗi nhưng dữ liệu hoặc tác động đã phát sinh. | Từ chối trước khi tiết lộ hoặc tạo tác động được bảo vệ. |

Các rủi ro này không được giải quyết chỉ bằng UUID khó đoán, kiểm tra định dạng ID hoặc cấu hình CORS. CORS điều chỉnh một số hành vi của trình duyệt; client ngoài trình duyệt vẫn có thể gọi API. Ranh giới bảo vệ cần nằm ở điểm thực thi có đủ dữ liệu và thẩm quyền.

## 3. Phân bổ trách nhiệm giữa gateway, backend và dữ liệu

### 3.1. Gateway không biết mọi điều kiện nghiệp vụ

Gateway có thể kiểm tra token, giới hạn lưu lượng hoặc quyền gọi một nhóm API. Backend thường biết chủ sở hữu tài liệu, phạm vi chia sẻ, trạng thái khóa và hành động thực sự đang được yêu cầu. Một token có scope `document.write` không mặc nhiên cho phép sửa mọi tài liệu.

Kiến trúc có thể phân tách các vai trò sau:

| Vai trò | Trách nhiệm |
| --- | --- |
| Điểm thực thi chính sách | Chặn hoặc cho hành động đi tiếp dựa trên kết quả đánh giá; thường nằm ở middleware, lớp nghiệp vụ hoặc truy vấn. |
| Thành phần đánh giá chính sách | Tính quyết định từ principal, hành động, tài nguyên và ngữ cảnh. |
| Nguồn thuộc tính | Cung cấp thành viên tenant, quan hệ sở hữu, chia sẻ, vai trò và trạng thái đáng tin. |
| Quản lý chính sách | Quản lý phiên bản, phê duyệt và triển khai quy tắc quyền. |

Các vai trò có thể cùng nằm trong một ứng dụng hoặc được phân tán. Tách ra thành nhiều dịch vụ không tự tạo bảo mật; quan trọng là không có đường thực thi nào tạo tác động khi chưa có quyết định hợp lệ.

### 3.2. Chọn vị trí kiểm tra theo mức thông tin cần có

- Middleware phù hợp với điều kiện chung, như endpoint cần principal hợp lệ hoặc có một quyền chức năng sơ bộ.
- Lớp nghiệp vụ phù hợp với điều kiện trên đối tượng, trạng thái và hành động cụ thể.
- Lớp truy vấn có thể giới hạn tài nguyên theo tenant và tập được phép, giảm nguy cơ trả nhầm dữ liệu.
- Ràng buộc dữ liệu và cập nhật có điều kiện hỗ trợ giữ đúng các bất biến khi có đồng thời.

Không cần lặp cùng một chính sách bằng các bản sao không kiểm soát ở mọi lớp. Cần phân bổ trách nhiệm rõ, tái sử dụng logic phù hợp và có kiểm thử chứng minh rằng một đường gọi khác không bỏ qua điểm bắt buộc.

Một hàm nghiệp vụ được cả HTTP controller và worker gọi nên có hợp đồng quyền rõ ràng. Nếu hàm dựa vào một quyết định đã được cấp từ trước, quyết định đó phải được ràng buộc với chủ thể, hành động, tài nguyên, phiên bản và thời hạn thích hợp; một tham số `authorized=true` do bên gọi tùy ý đặt không phải bằng chứng.

### 3.3. Bảo vệ đường tin cậy giữa các thành phần

Nếu gateway chuyển danh tính tới backend qua header, backend phải xác thực nguồn gateway và bảo đảm client không thể tự đưa cùng header vào một đường trực tiếp. Cần loại bỏ hoặc ghi đè header không đáng tin tại ranh giới và bảo vệ kênh nội bộ theo thiết kế.

Không mặc định tin `X-User-Id`, `X-Role` hoặc `X-Tenant-Id` chỉ vì chúng xuất hiện trong request. Một dịch vụ nội bộ có danh tính hợp lệ cũng chỉ được cung cấp các thuộc tính và thực hiện các hành động trong phạm vi được cấp.

## 4. Xây dựng ngữ cảnh quyết định từ nguồn đáng tin

Một quyết định có thể được mô tả bằng:

```text
Decision = Policy(Subject, Action, Resource, Context)
```

### 4.1. Chủ thể và tenant

Subject phải đến từ bằng chứng được kiểm tra theo giao thức: chẳng hạn phiên server quản lý hoặc token đúng bên phát hành, bên nhận, thời hạn và loại sử dụng. Payload chứa `userId` không được thay thế principal.

Tenant do client chọn chỉ là phạm vi được yêu cầu. Backend phải xác minh tư cách thành viên hoặc cơ chế ủy nhiệm tương ứng. Sau đó phải đối chiếu tenant của tài nguyên; có tư cách thành viên ở A không đủ để dùng một ID thuộc B.

### 4.2. Hành động và tài nguyên

Hành động nên phản ánh nghiệp vụ, chẳng hạn `document.read`, `document.edit` hoặc `document.share`. Không suy ra đầy đủ quyền chỉ từ HTTP method. Một endpoint `POST /documents/search` có thể chỉ đọc, còn một endpoint tải có thể kích hoạt xuất dữ liệu nhạy cảm.

ID tài nguyên là đầu vào để tìm mục tiêu, không phải bằng chứng có quyền. Chủ sở hữu, quan hệ cha–con, nhãn nhạy cảm và trạng thái cần lấy từ nguồn có thẩm quyền. Server có thể đọc metadata nội bộ cần thiết để quyết định, nhưng không trả nội dung được bảo vệ cho client trước khi được phép.

### 4.3. Điều kiện và độ mới

Vai trò, chia sẻ, trạng thái thành viên và thời điểm xác thực có thể thay đổi. Cần xác định nguồn nào được tin, dữ liệu được dùng cũ tối đa bao lâu và trường hợp thiếu thuộc tính được xử lý thế nào.

Ví dụ, thao tác xóa có thể cần quyền xóa và bằng chứng xác thực mới không quá năm phút. Người không có quyền vẫn bị từ chối dù hoàn tất MFA; cờ `recentlyAuthenticated=true` từ client không chứng minh điều kiện đó.

Chính sách không có quy tắc cho một hành động mới phải mặc định không cho phép, trừ trường hợp công khai được khai báo rõ. Việc thiếu policy, lỗi đánh giá hoặc thuộc tính không xác định không được tự chuyển thành quyền quản trị hoặc quyền mặc định rộng.

## 5. Luồng xử lý một yêu cầu được bảo vệ

### 5.1. Trình tự trách nhiệm

```text
Tiếp nhận và kiểm tra đầu vào cơ bản
    -> Xác thực bằng chứng và thiết lập principal
    -> Xác minh phạm vi tenant hoặc ủy nhiệm
    -> Xác định hành động và lấy metadata cần thiết
    -> Đánh giá quyền trên tài nguyên
    -> Thực hiện trong phạm vi được cho phép
    -> Giới hạn dữ liệu trả ra và ghi sự kiện phù hợp
```

Một số bước có thể phối hợp trong truy vấn hoặc giao dịch. Không nhất thiết mọi hệ thống có cùng thứ tự gọi hàm, nhưng phải giữ hai thuộc tính: dữ liệu đầu vào của quyết định đáng tin và không tạo tác động được bảo vệ trước khi điều kiện bắt buộc đạt.

### 5.2. Mã giả cho API sửa tài liệu

```text
principal = authentication.requireValidPrincipal(request.credentials)
tenant = membership.requireActiveMembership(principal, request.tenantId)
patch = input.parseDocumentPatch(request.body)

document = repository.findWithinTenant(request.documentId, tenant.id)
if document is absent:
    return responseAccordingToDisclosurePolicy()

decision = authorization.evaluate(
    subject = principal,
    action = "document.edit",
    resource = document,
    context = trustedContext(tenant)
)

if decision is not PERMIT:
    return responseAccordingToDisclosurePolicy()

result = documentService.applyAuthorizedPatch(
    principal,
    document.id,
    expectedVersion = document.version,
    permittedPatch = patch,
    decisionContext = decision
)

return permittedDocumentView(principal, result)
```

`parseDocumentPatch` chỉ nhận trường được API cho phép; nó không chứng minh người gọi có quyền sửa tài liệu. Ngược lại, quyền sửa không có nghĩa client được cập nhật mọi trường của đối tượng.

`applyAuthorizedPatch` phải kiểm tra các điều kiện có thể thay đổi tại thời điểm ghi hoặc sử dụng cơ chế nhất quán đáp ứng hợp đồng. Quyết định phía trước không phải giấy phép dùng vô thời hạn, không được dùng lại cho tài liệu khác hoặc một hành động khác.

Đường xử lý lỗi cũng phải kết thúc trước tác động. Một lỗi thường gặp là ghi thay đổi trước, sau đó mới kiểm tra quyền để chọn có trả kết quả hay không. Khi đó phản hồi bị từ chối không chứng minh thao tác đã được ngăn.

### 5.3. Kiểm tra quyền theo hành động cụ thể

Quyền đọc, sửa nội dung, chia sẻ, chuyển chủ và xóa nên có tên và điều kiện phân biệt. Nếu người dùng được sửa nội dung, backend không được tự suy ra họ được cấp quyền cho người khác.

Một endpoint có nhiều loại thay đổi cần kiểm tra tập hành động thực tế. Ví dụ, yêu cầu vừa sửa tiêu đề vừa đổi chế độ công khai cần quyền sửa và quyền công bố theo chính sách. Không đánh giá một quyền chung rồi thực hiện mọi trường mà JSON chứa.

## 6. Bảo vệ tập dữ liệu, đối tượng và thuộc tính

### 6.1. Kiểm tra chức năng chưa đủ cho đối tượng

Một annotation hoặc middleware như “có vai trò nhân viên” có thể chặn người ngoài, nhưng chưa chứng minh nhân viên được đọc tài liệu cụ thể. Cần thêm điều kiện đối tượng, tenant và phạm vi chia sẻ.

Tương tự, quyền trên tài liệu cha không tự chứng minh một `attachmentId` thuộc cha đó. Backend phải kiểm tra quan hệ thực tế. Không được ghép ID cha hợp lệ và ID con ngoài quyền để truy cập tệp khác.

### 6.2. Danh sách, tìm kiếm và tổng số

Đối với danh sách, hệ thống nên áp dụng phạm vi quyền trong cách xây tập dữ liệu truy vấn được phép. Không lấy toàn bộ tài nguyên rồi chỉ lọc phần hiển thị trong giao diện.

Phân trang, tổng số, bộ lọc, gợi ý và dữ liệu tổng hợp phải có chính sách cùng phạm vi. Nếu danh sách chỉ trả tài liệu được phép nhưng trường `total` đếm mọi tài liệu trong tenant, hệ thống vẫn có thể tiết lộ thông tin ngoài phạm vi công bố.

Truy vấn có tham số bảo vệ một nhóm rủi ro về đầu vào SQL nhưng không tự tạo phân quyền. Câu truy vấn `WHERE id = :id` vẫn có thể lấy đối tượng của người khác nếu không có giới hạn hoặc kiểm tra quyền phù hợp.

### 6.3. Giới hạn trường vào và trường ra

Payload sửa nội dung chỉ nên có các trường được định nghĩa cho hành động đó. Những trường như `owner_id`, `tenant_id`, `role`, `approved_by` hoặc trạng thái xác minh phải được bảo vệ bằng luồng và quyền riêng nếu sản phẩm có cho phép thay đổi.

Phản hồi cũng cần giới hạn thuộc tính. Một người được đọc tài liệu có thể chưa được đọc ghi chú quản trị, khóa chia sẻ hoặc thông tin liên hệ nhạy cảm. Tránh trả nguyên đối tượng lưu trữ rồi trông chờ client tự bỏ trường.

Phải chốt hành vi với trường không được phép: từ chối toàn bộ payload hoặc một quy tắc bỏ qua được mô tả rõ. Trong tình huống minh họa, API sửa nội dung từ chối payload có trường thay đổi quyền và không cập nhật một phần.

### 6.4. Vai trò của lớp dữ liệu

Lọc theo tenant, ràng buộc tham chiếu và chính sách mức hàng nếu hạ tầng hỗ trợ có thể bổ sung bảo vệ. Cần xác định chúng áp dụng cho tài khoản ứng dụng nào, câu truy vấn nào và trường hợp nào có quyền vượt qua.

Nếu ngữ cảnh tenant được gắn với kết nối cơ sở dữ liệu, phải quản lý đúng vòng đời kết nối. Kết nối trả về pool mà còn giữ tenant cũ có thể làm yêu cầu sau dùng nhầm phạm vi. Ngữ cảnh quyền trong bộ nhớ dùng chung hoặc thread-local cũng cần được quản lý đúng khi có tác vụ bất đồng bộ. Việc dùng cơ chế ở lớp dữ liệu không tự loại bỏ yêu cầu kiểm tra nghiệp vụ.

## 7. Giữ quyền và tác động nhất quán khi có đồng thời

### 7.1. Khoảng trống giữa kiểm tra và sử dụng

Giả sử server đọc tài liệu khi Lan là chủ, đánh giá cho sửa, rồi người khác hoàn tất chuyển chủ trước khi lệnh cập nhật của Lan chạy. Nếu lệnh cập nhật chỉ dựa trên ID, quyết định dựa vào trạng thái cũ vẫn có thể sửa tài liệu sau chuyển giao.

Đây là rủi ro kiểm tra tại một thời điểm nhưng sử dụng ở thời điểm khác, thường gọi là TOCTOU. Yêu cầu phải nêu điều kiện nào cần còn đúng khi hành động được cam kết và cách xử lý nếu chúng thay đổi.

### 7.2. Cập nhật có điều kiện trong một luồng hẹp

Đoạn SQL minh họa dưới đây dành cho một luồng mà chính sách chỉ cho chủ sở hữu sửa tài liệu nháp trong tenant đang hoạt động. Các tham số danh tính được thiết lập ở server; cú pháp bind tham số phụ thuộc công cụ triển khai.

```sql
UPDATE document
SET title = :title,
    version = version + 1
WHERE id = :document_id
  AND tenant_id = :verified_tenant_id
  AND owner_user_id = :principal_id
  AND state = 'DRAFT'
  AND version = :expected_version
  AND EXISTS (
      SELECT 1
      FROM membership m
      WHERE m.tenant_id = document.tenant_id
        AND m.user_id = :principal_id
        AND m.status = 'ACTIVE'
  );
```

Nếu không có hàng nào được cập nhật, server không được tự chạy lại bằng câu lệnh bỏ tenant, owner hoặc phiên bản. Phản hồi cần tuân thủ chính sách lỗi và không tiết lộ tài nguyên ngoài quyền.

Câu lệnh này bảo vệ những điều kiện được thể hiện trong nó. Nó chưa triển khai các nhánh chia sẻ, quyền quản trị, trạng thái tài khoản hoặc thuộc tính ở hệ thống khác. Khi mở rộng chính sách, cần thiết kế lại hợp đồng nhất quán và kiểm thử các trường hợp tương ứng.

Giao dịch, khóa hoặc kiểm tra phiên bản cần được chọn theo ngữ nghĩa thực tế của kho dữ liệu. Nếu quyền ở một hệ thống còn tài nguyên ở hệ thống khác, việc đọc hai lần không tự tạo một ảnh chụp nguyên tử; phải xác định thời điểm hiệu lực và mức dữ liệu cũ được chấp nhận.

### 7.3. Tác động bên ngoài và thao tác hàng loạt

Chỉ gửi email nghiệp vụ, phát sự kiện thành công hoặc gọi dịch vụ ngoài sau khi điều kiện quyền và trạng thái được đáp ứng theo thiết kế. Một outbox ghi cùng giao dịch có thể hỗ trợ liên kết thay đổi dữ liệu với sự kiện bền vững; bên nhận vẫn cần xử lý truyền lại và phạm vi quyền của mình.

Với batch, phải kiểm tra từng đối tượng. Chọn rõ hợp đồng tất cả hoặc từng phần và bảo đảm không thực hiện tác động trước khi biết điều kiện của phần đó đã đạt. Kiểm tra một ID đầu tiên không cấp quyền cho toàn bộ tập.

Retry phải giữ cùng hành động và phạm vi được ủy nhiệm, đồng thời đánh giá lại các điều kiện cần mới. Không cho một quyết định cũ tiếp tục chạy lại vô hạn sau khi quyền đã bị thu hồi.

## 8. Bao phủ các kênh và đường truy cập khác

| Kênh | Điểm dễ bỏ sót | Yêu cầu cần có |
| --- | --- | --- |
| REST hoặc RPC | Endpoint cũ, phiên bản khác, route nội bộ. | Mỗi hành động được ánh xạ tới chính sách và đi qua điểm thực thi bắt buộc. |
| GraphQL | Kiểm tra ở truy vấn ngoài nhưng resolver con trả đối tượng khác. | Các trường và quan hệ được bảo vệ phải thực hiện quyền tương ứng; cache tải dữ liệu không dùng nhầm phạm vi giữa principal hoặc tenant. |
| WebSocket | Chỉ kiểm tra lúc bắt tay kết nối. | Kiểm tra quyền với thông điệp nghiệp vụ và đăng ký nhận dữ liệu; thu hồi được áp dụng cho đăng ký đang tồn tại theo thời hạn công bố. |
| Job và worker | Dùng tài khoản dịch vụ mạnh để thực hiện yêu cầu cũ. | Giữ ngữ cảnh ủy nhiệm và kiểm tra quyền tại lúc thực thi theo giới hạn độ mới. |
| Callback, webhook | Nguồn gửi hợp lệ nhưng target trong payload bị thay đổi. | Kiểm tra thẩm quyền của nguồn đối với hành động và ràng buộc với đối tượng hoặc giao dịch đã được hệ thống chấp nhận. |
| Tải tệp, bản xuất | API chính chặn nhưng kho tệp hoặc liên kết cũ vẫn mở. | Cơ chế tải thực thi phạm vi tài nguyên, thời hạn và thu hồi phù hợp cam kết. |
| Batch, nhập dữ liệu | Một quyền chung được dùng cho mọi dòng hoặc đối tượng. | Kiểm tra quyền cho từng tác động và áp dụng hợp đồng kết quả đã xác định. |

### 8.1. Phân biệt dịch vụ gọi và người được đại diện

Khi dịch vụ A gọi B thay Lan, B cần biết A có được gọi loại thao tác đó không và thao tác thay Lan có nằm trong phạm vi được ủy nhiệm không. Header chứa tên Lan do một bên không được phép tự khai báo không đủ làm bằng chứng ủy nhiệm.

Nếu dùng token ủy nhiệm hoặc quyết định được ký, bên nhận phải kiểm tra bên phát hành được tin cậy, bên nhận dự kiến, chủ thể, hành động, tài nguyên, thời hạn và các ràng buộc của giao thức. Token được ký không tự cho phép gọi mọi API dưới mọi danh nghĩa.

Một tác vụ hệ thống độc lập có thể dùng danh tính workload và chính sách riêng. Cần nêu rõ phạm vi và mục đích của loại tác vụ đó, tránh ngầm biến mọi job thành một đường có quyền cao hơn người dùng.

### 8.2. Liên kết tải là một cơ chế cấp khả năng truy cập

URL tải có chữ ký có thể cho người giữ URL truy cập mà không cần phiên người dùng. Do đó, lúc cấp URL phải kiểm tra quyền và giới hạn tài nguyên, hành động, thời gian cùng các điều kiện mà cơ chế hỗ trợ.

Nếu yêu cầu thu hồi quyền trong 30 giây nhưng URL cũ dùng được một giờ và không thể thu hồi, thiết kế chưa đáp ứng yêu cầu. Cần thay cơ chế kiểm tra, giới hạn thời hạn hoặc điều chỉnh cam kết qua quyết định rủi ro phù hợp. Chỉ xóa liên kết khỏi giao diện không chặn được bản sao đã cấp.

## 9. Cache, thu hồi và hành vi khi không thể quyết định

### 9.1. Quyết định cho phép có phạm vi và thời hạn

Trong ví dụ này, việc gỡ quyền sửa có hiệu lực tại mọi điểm thực thi thuộc phạm vi trong tối đa 30 giây từ lúc thay đổi được xác nhận. Giới hạn phải tính tới token chứa quyền cũ, cache ở từng nút, đăng ký nhận dữ liệu và job đang chờ.

Cache cần phân biệt các chiều làm thay đổi quyết định: subject, tenant, action, resource, điều kiện liên quan và phiên bản chính sách hoặc quyền. Chỉ cache theo `userId`, theo URL hoặc theo tên vai trò thường không đủ cho quyết định trên tài nguyên.

Thêm phiên bản vào khóa cũng chưa chứng minh các nút biết phiên bản mới. Cần cách tra cứu, truyền vô hiệu hóa hoặc thời hạn cứng đáp ứng giới hạn. Không được gia hạn một quyền cũ vô hạn chỉ vì cache liên tục được đọc.

Giới hạn 30 giây mô tả cửa sổ dữ liệu cũ được chấp nhận trong giả định này. Những hành động cần hiệu lực mạnh hơn phải có yêu cầu riêng. Phải xác định cách xử lý thao tác đang chạy; thu hồi đối với yêu cầu mới không tự dừng mọi dữ liệu đang truyền hoặc thu lại bản sao người dùng đã tải.

### 9.2. Lỗi không tạo ra quyền

Khi policy không tồn tại, dữ liệu bắt buộc bị thiếu hoặc bộ máy đánh giá trả lỗi, điểm thực thi không được coi đó là `PERMIT`. Một đoạn xử lý ngoại lệ kiểu “nếu dịch vụ quyền lỗi thì cho qua để giữ sẵn sàng” tạo một đường bỏ qua chính sách.

Điều này không buộc mỗi yêu cầu phải gọi từ xa. Quyết định hoặc thuộc tính lưu đệm vẫn có thể được dùng nếu còn đáp ứng toàn bộ điều kiện đã được phê duyệt. Khi không còn dữ liệu tin cậy đủ mới để cho phép, thao tác phải bị chặn theo hành vi lỗi đã định nghĩa.

Cần đặt timeout, giới hạn tài nguyên và theo dõi lỗi của luồng đánh giá quyền. Phải phân biệt lỗi xác thực, từ chối phân quyền và lỗi hạ tầng để client xử lý đúng, đồng thời tránh lộ chi tiết nội bộ hoặc sự tồn tại của tài nguyên ngoài quyền.

### 9.3. Ghi sự kiện phù hợp

Sự kiện phân quyền nên có mã chủ thể nội bộ, tenant, hành động, tham chiếu tài nguyên phù hợp, kết quả, mã nguyên nhân, phiên bản chính sách và mã tương quan. Khi cần, lưu tuổi dữ liệu quyết định hoặc thông tin nguồn để điều tra cache cũ.

Không ghi mật khẩu, mã MFA, cookie, token truy cập hoặc toàn bộ nội dung tài nguyên bị từ chối. Quyền đọc, xuất và lưu giữ log cần được quản lý riêng. Một lần bị từ chối đọc tài liệu ngoài quyền không được ghi nhầm thành mật khẩu sai và làm sai bộ đếm đăng nhập.

## 10. Bộ yêu cầu có thể kiểm chứng

| Mã | Cam kết cần thực hiện | Rủi ro | Thành phần chịu trách nhiệm | Bằng chứng chính |
| --- | --- | --- | --- | --- |
| SAZ-01 | Mọi hành động được bảo vệ phải đi qua kiểm tra phía server; chức năng công khai được khai báo rõ, hành động chưa có chính sách không tự được cho phép. | R-S01, R-S04 | Chủ API và lớp nghiệp vụ. | Gọi trực tiếp mọi route trong phạm vi bằng principal thiếu quyền vẫn bị chặn. |
| SAZ-02 | Quyết định trên đối tượng dùng principal đáng tin, tenant đã xác minh và thuộc tính tài nguyên từ nguồn có thẩm quyền. | R-S02, R-S03 | Backend và nguồn quyền. | Đổi ID, tenant, owner hoặc header danh tính không vượt phạm vi. |
| SAZ-03 | API chỉ nhận và trả các trường được phép cho hành động và chủ thể; không ánh xạ tự do trường quản lý quyền. | R-S03, R-S08 | Lớp nhập dữ liệu và phản hồi. | Chèn trường nhạy cảm không sửa trạng thái quyền, phản hồi không lộ trường bị hạn chế. |
| SAZ-04 | Điều kiện quyền và trạng thái cần thiết phải còn đúng tại điểm tác động theo hợp đồng nhất quán đã định nghĩa. | R-S05 | Dịch vụ nghiệp vụ và kho dữ liệu. | Thử đổi owner hoặc trạng thái đồng thời không tạo cập nhật trái phép. |
| SAZ-05 | Job, callback, tài nguyên con và đường tải thực hiện quyền theo phạm vi của từng kênh, bao gồm chủ thể được đại diện. | R-S04, R-S07 | Worker, tích hợp và lưu trữ. | Kênh ngoài API chính không truy cập hoặc thao tác ngoài quyền. |
| SAZ-06 | Gỡ quyền sửa có hiệu lực trên các điểm trong phạm vi trong tối đa 30 giây từ xác nhận thay đổi theo chính sách minh họa. | R-S06 | Nguồn quyền, cache và điểm thực thi. | Phiên còn hạn, nhiều nút và job cũ đều không dùng quyền bị gỡ quá giới hạn. |
| SAZ-07 | Lỗi đánh giá, thiếu policy hoặc cache hết điều kiện sử dụng không được chuyển thành cho phép. | R-S06 | Bộ máy đánh giá và điểm thực thi. | Mô phỏng lỗi phụ thuộc, timeout và thiếu thuộc tính vẫn không có tác động được bảo vệ. |
| SAZ-08 | Yêu cầu bị từ chối không được trả dữ liệu hoặc tạo tác động nghiệp vụ như thể được cho phép. | R-S08 | Toàn bộ đường xử lý. | Đối chiếu phản hồi, dữ liệu, hàng đợi, sự kiện và lời gọi hệ thống ngoài. |
| SAZ-09 | Quyết định quan trọng có dấu vết đủ liên kết, không ghi bí mật xác thực hoặc nội dung ngoài quyền. | R-S04, R-S06, R-S08 | Producer kiểm toán và nền tảng quan sát. | Truy vết được quyết định bằng mã tương quan và kiểm tra dữ liệu log. |

Mỗi mã cần liên kết với thiết kế và ca kiểm thử. Ví dụ, SAZ-05 phải liệt kê cụ thể job, resolver, route tệp và callback thuộc phạm vi; ghi chung “các kênh khác cũng kiểm tra” không giúp phát hiện một kênh bị bỏ sót.

## 11. Ví dụ đặc tả và ma trận nghiệm thu

### 11.1. SAZ-DELETE-01 — Xóa tài liệu tại server

**Mục tiêu:** ngăn người dùng hợp lệ xóa tài liệu ngoài quyền hoặc xóa tài liệu không còn được phép thay đổi.

**Phạm vi:** API xóa trực tiếp và job xóa thay mặt người dùng trong cổng minh họa.

**Điều kiện bắt buộc:** principal và tư cách thành viên hợp lệ; tài liệu thuộc tenant đã xác minh; chủ thể có `document.delete` trên tài liệu; trạng thái cho phép xóa; các điều kiện này được đánh giá với độ mới và tính nhất quán đã cam kết. Quyền đọc hoặc sửa không tự cấp quyền xóa.

**Hành vi bắt buộc:**

1. Backend kiểm tra quyền trước khi đánh dấu xóa, tạo job hoặc phát sự kiện xóa thành công.
2. Quyết định được ràng buộc với principal, tenant, ID tài liệu và hành động xóa; không được tái sử dụng quyết định đọc hoặc quyết định cho một tài liệu khác.
3. Nếu trạng thái, quyền hoặc phiên bản cần kiểm tra không còn phù hợp tại điểm tác động, không thực hiện xóa bằng quyết định cũ.
4. Job làm thay người dùng phải kiểm tra lại quyền tại lúc thực thi theo chính sách, kể cả khi được tạo lúc người dùng còn quyền.
5. Khi không đủ bằng chứng để cho phép, hệ thống trả phản hồi theo hợp đồng lỗi và không làm lộ tài liệu ngoài quyền. Các tác động kiểm toán về việc bị từ chối vẫn có thể được ghi theo chính sách.

**Tiêu chí chấp nhận:**

| Ca | Thiết lập và thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Được phép | Principal đúng tenant, có quyền xóa trên tài liệu ở trạng thái cho phép. | Xóa theo hợp đồng, tạo bằng chứng thành công phù hợp. |
| Gọi trực tiếp | Người thiếu quyền dùng client riêng gọi API, bỏ qua giao diện. | Bị từ chối, không tạo job xóa. |
| Sai đối tượng | Có quyền trên A nhưng thay ID thành B ngoài phạm vi. | B không bị thay đổi, không trả dữ liệu của B. |
| Sai tenant | Tài khoản hợp lệ ở A gửi ID tài liệu B và sửa header tenant. | Không dùng được quyền ở A với tài nguyên B. |
| Giả danh tính | Client tự đặt header vai trò hoặc user ID trên đường không được tin cậy. | Không thiết lập được principal hay quyền từ lời khai đó. |
| Chỉ có quyền sửa | Người dùng sửa được nội dung nhưng không có quyền xóa. | Không được xóa. |
| Thay đổi đồng thời | Tài liệu chuyển sang trạng thái khóa trước khi thao tác xóa cam kết. | Không xóa dựa trên trạng thái cũ theo hợp đồng nhất quán. |
| Quyền bị gỡ | Phiên còn hạn, quyền xóa đã bị gỡ theo thời hạn áp dụng cho hành động này. | Không dùng phiên cũ để tiếp tục xóa ngoài cửa sổ được chấp nhận. |
| Lỗi policy | Bộ máy đánh giá timeout, không có dữ liệu hoặc quyết định còn hiệu lực. | Không cho phép và không tạo tác động xóa. |
| Job đến muộn | Job chờ trong hàng đợi, người yêu cầu mất quyền trước khi thực thi. | Quyết định cũ không tự đủ; job tuân thủ quyền hiện hành theo chính sách. |

Thời hạn thu hồi của quyền xóa phải được chốt riêng trong hồ sơ triển khai. Không tự suy từ ví dụ 30 giây của quyền sửa sang mọi hành động nếu rủi ro và yêu cầu khác nhau.

### 11.2. Bằng chứng cần kiểm tra ngoài mã phản hồi

Một kết quả HTTP bị từ chối chưa chứng minh dữ liệu được bảo vệ. Cần kiểm tra nội dung, header, trạng thái dữ liệu, bản ghi job, sự kiện nghiệp vụ và lời gọi ngoài để xác nhận không có tác động trái phép.

Với danh sách, trộn dữ liệu được phép và không được phép, kiểm tra cả tổng số và phân trang. Với batch, trộn các đối tượng khác quyền. Với GraphQL, gọi quan hệ con và nhiều trường trong cùng truy vấn. Với WebSocket, gỡ quyền khi kết nối còn mở và theo dõi dữ liệu tiếp tục được gửi theo giới hạn đã cam kết.

Dùng principal hợp lệ nhưng thiếu quyền để kiểm thử authorization. Nếu mọi ca đều dùng token giả hoặc hết hạn, bộ kiểm thử có thể chỉ chứng minh authentication. Cũng cần ca được phép để phát hiện hệ thống từ chối tất cả do cấu hình sai.

Đo thu hồi từ mốc xác nhận thay đổi quyền tới các điểm thực thi, gồm nút có cache và job đang chờ. Thử lỗi phụ thuộc, yêu cầu đồng thời và đường gọi bỏ qua gateway theo phạm vi triển khai thực tế. Các bằng chứng cần có cấu hình và phiên bản chính sách tương ứng để có thể tái kiểm tra.

## 12. Duy trì yêu cầu trong vòng đời phát triển

Mỗi hành động mới cần có chủ thể, tài nguyên, điều kiện và điểm thực thi được xác định trước khi phát hành. Danh mục route, resolver, job và đường tải phải liên kết với mã yêu cầu và ca kiểm thử. Việc thêm một endpoint không đi qua middleware cũ hoặc chuyển xử lý sang worker có thể mở đường bỏ kiểm tra nếu chỉ dựa vào thói quen triển khai.

Một chuỗi truy vết minh họa:

```text
R-S02: Đổi documentId để truy cập tài liệu ngoài quyền
    -> SAZ-02: Kiểm tra principal, tenant và tài nguyên đáng tin
    -> Truy vấn trong tenant + policy trên đối tượng tại backend
    -> Ca principal hợp lệ, đối tượng sai và tenant sai
    -> Theo dõi quyết định từ chối cùng mã tương quan
```

Thay chính sách, cache hoặc nguồn thuộc tính cần cập nhật cả yêu cầu về thu hồi, cấu hình triển khai và bằng chứng. Bản thân việc hệ thống vẫn đăng nhập được không chứng minh phân quyền còn đúng. Khi phục hồi hoặc quay lại phiên bản cũ, phải kiểm tra chính sách và dữ liệu quyền có tương thích, tránh khôi phục một trạng thái từng cho phép rộng hơn.

### 12.1. Bài tập áp dụng

Một nhóm nói: “Gateway đã kiểm tra token; frontend chỉ hiển thị nút xóa cho chủ tài liệu; worker nội bộ có thể tin mọi job.”

Hãy hoàn thiện yêu cầu bằng cách:

1. Liệt kê các đường đọc, sửa, xóa, xuất và tải dữ liệu cần thực thi quyền.
2. Chỉ ra nguồn đáng tin của principal, tenant, chủ sở hữu và quyền chia sẻ.
3. Viết điều kiện server phải kiểm tra cho một hành động trên đối tượng cụ thể.
4. Quy định hành vi khi quyền đổi giữa kiểm tra và cập nhật, hoặc khi job đến lượt thực thi sau khi thu hồi.
5. Chốt phạm vi cache, thời hạn thu hồi và hành vi khi nguồn policy ngừng hoạt động.
6. Viết ca gọi trực tiếp API bằng principal hợp lệ nhưng sai đối tượng, sai tenant và thiếu quyền chức năng.

Ví dụ một phần đáp án: backend kiểm tra `document.delete` trên tài liệu hiện hành, tenant được xác minh và trạng thái cho phép trước khi tạo tác động. Worker nhận ngữ cảnh ủy nhiệm đáng tin và đánh giá quyền khi thực thi theo chính sách. Header từ client, nút bị ẩn hoặc quyết định đọc cũ không cấp quyền xóa.

Yêu cầu kiểm tra authorization ở server đạt mục tiêu khi nhóm thiết kế chỉ ra được mọi điểm thực thi, nhóm phát triển giữ được quyết định đúng đến thời điểm tác động và nhóm kiểm thử chứng minh được người dùng hợp lệ vẫn bị chặn ở hành động ngoài phạm vi. Đó là cơ sở để quyền truy cập được bảo vệ xuyên suốt kiến trúc và vòng đời phát triển.
