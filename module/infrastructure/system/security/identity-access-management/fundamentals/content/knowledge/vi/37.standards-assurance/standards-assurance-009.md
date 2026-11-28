# ASVS access control: chuyển yêu cầu phân quyền thành kiểm soát có thể xác minh

Một API có thể xác thực token đúng, ghi nhận đúng người dùng và vẫn trả nhầm dữ liệu của người khác. Một màn hình có thể ẩn nút quản trị nhưng endpoint tương ứng vẫn chấp nhận yêu cầu trực tiếp. Những tình huống này cho thấy đăng nhập thành công chưa trả lời câu hỏi chủ thể được phép làm gì trên tài nguyên nào.

OWASP Application Security Verification Standard (ASVS) giúp biến câu hỏi đó thành các yêu cầu có thể đối chiếu với thiết kế, mã nguồn và kết quả kiểm thử. Trong IAM, phần access control là cầu nối giữa danh tính đã xác thực, quyền được cấp và quyết định thực tế tại ứng dụng.

## 1. Chốt phiên bản trước khi dùng mã yêu cầu

Bài học sử dụng **ASVS 5.0.0**, bản stable được OWASP công bố trong tháng 05/2025. Ở phiên bản này, phần phân quyền là **V8 Authorization**. ASVS 4.0.3 dùng tên **V4 Access Control**; không giữ nguyên số chương hoặc mã yêu cầu cũ khi chuyển phiên bản. [Giới thiệu và phiên bản ASVS](https://github.com/OWASP/ASVS), [V4 của ASVS 4.0.3](https://raw.githubusercontent.com/OWASP/ASVS/v4.0.3/4.0/en/0x12-V4-Access-Control.md).

Khi ghi finding hoặc lập tiêu chí nghiệm thu, nên dùng mã có phiên bản, chẳng hạn `v5.0.0-8.2.2`. Đây là cách OWASP khuyến nghị để tránh nhầm khi nội dung và mã thay đổi. [Cách tham chiếu yêu cầu](https://github.com/OWASP/ASVS#how-to-reference-asvs-requirements).

ASVS có ba mức L1, L2 và L3. Mức cao hơn bao gồm các yêu cầu của mức thấp hơn cùng yêu cầu bổ sung áp dụng. L1 không mặc định có nghĩa chỉ cần kiểm thử hộp đen; một số yêu cầu vẫn cần tài liệu hoặc thông tin nội bộ để xác minh. [Phạm vi và mức xác minh ASVS 5.0.0](https://raw.githubusercontent.com/OWASP/ASVS/v5.0.0_release/5.0/en/0x03-What-is-the-ASVS.md).

Trong bài này, các ví dụ là tình huống tự xây dựng để học cách triển khai và thu thập bằng chứng. Hoàn tất những ví dụ đó chưa chứng minh toàn bộ ứng dụng đạt một mức ASVS.

## 2. Authentication cung cấp chủ thể; authorization quyết định hành động

Có thể mô tả một quyết định phân quyền như sau:

~~~text
quyết định = policy(
    chủ thể,
    hành động,
    tài nguyên,
    ngữ cảnh đáng tin cậy,
    trạng thái hiện tại
)
~~~

Authentication và authorization có mục đích khác nhau. OWASP cũng khuyến nghị quyền tối thiểu, mặc định từ chối và kiểm tra quyền trên từng yêu cầu. [Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

Xét hệ thống quản lý hóa đơn của công ty An Bình:

- Lan và Minh đều đã đăng nhập.
- Cả hai có thể dùng chức năng xem hóa đơn.
- Lan chỉ được xem hóa đơn thuộc phạm vi của Lan.
- Nhóm kế toán có thể xem thêm các hóa đơn của tenant theo quyền được cấp.
- Quyền quản trị danh tính không tự động bao gồm quyền xem mọi dữ liệu tài chính.

Nếu API chỉ kiểm tra “đã đăng nhập” hoặc “có role nhân viên”, nó chưa thực thi đầy đủ các quy tắc trên.

Một quyền nên mang nghĩa hành động rõ ràng như `invoice.read.own`, `invoice.read.tenant` hoặc `invoice.approve`. Tên quyền là lựa chọn của ứng dụng; điều cần thống nhất là ý nghĩa và phạm vi, không phải một quy tắc đặt tên cố định từ ASVS.

## 3. Bản đồ đọc V8 Authorization

Bảng sau là bản đồ định vị, không thay thế nội dung đầy đủ của từng yêu cầu:

| Mã trong ASVS 5.0.0 | Trọng tâm | Mức |
| --- | --- | --- |
| 8.1.1–8.1.4 | Tài liệu policy | L1/L2/L3 tùy yêu cầu |
| 8.2.1 | Chức năng | L1 |
| 8.2.2 | Bản ghi/tài nguyên | L1 |
| 8.2.3 | Trường dữ liệu | L2 |
| 8.2.4 | Ngữ cảnh thích ứng | L3 |
| 8.3.1 | Tầng thực thi đáng tin | L1 |
| 8.3.2 | Thay đổi căn cứ quyết định | L3 |
| 8.3.3 | Quyền của chủ thể khởi tạo | L3 |
| 8.4.1 | Ranh giới tenant | L2 |
| 8.4.2 | Bảo vệ giao diện quản trị | L3 |

Nguồn đối chiếu: [V8 Authorization, ASVS 5.0.0](https://raw.githubusercontent.com/OWASP/ASVS/v5.0.0_release/5.0/en/0x17-V8-Authorization.md).

Ví dụ, ở hệ thống An Bình, chỉ kiểm tra quyền mở endpoint là chưa đủ: cùng một endpoint có thể xử lý nhiều hóa đơn, mỗi hóa đơn thuộc một người hoặc tenant khác nhau. Việc tài liệu nêu rõ những khác biệt này giúp lập trình viên và người kiểm thử dùng chung một tiêu chí.

## 4. Viết policy trước khi chọn chỗ đặt điều kiện

Một bảng policy minh họa:

| Chủ thể | Hành động | Tài nguyên | Điều kiện | Kết quả |
| --- | --- | --- | --- | --- |
| Nhân viên | Đọc hóa đơn | Hóa đơn của mình | Cùng tenant, có quyền đọc của mình | Cho phép |
| Nhân viên | Đọc hóa đơn | Hóa đơn người khác | Không có quyền bổ sung | Từ chối |
| Kế toán | Đọc hóa đơn | Hóa đơn trong tenant | Có quyền đọc theo tenant | Cho phép |
| Người duyệt | Duyệt hóa đơn | Hóa đơn đang chờ | Có quyền duyệt, không tự duyệt | Cho phép |
| Quản trị tenant A | Đổi membership | Người của tenant B | Không có phạm vi tương ứng | Từ chối |

Các quy tắc này là giả định nghiệp vụ của ví dụ. Một sản phẩm khác có thể cho phép chia sẻ hóa đơn hoặc quản trị nhiều tenant, nhưng cần biểu diễn sự cho phép đó rõ ràng.

Policy còn phải trả lời:

1. “Của mình” xác định bằng định danh ổn định nào?
2. Quyền của tenant được cấp ở đâu và hết hiệu lực khi nào?
3. Tài nguyên đã khóa có còn sửa được không?
4. Ai được thay đổi người sở hữu hoặc tenant của tài nguyên?
5. Khi không tìm được policy hoặc không lấy được dữ liệu quyền thì xử lý thế nào?

Nếu thiếu câu trả lời, nhóm phát triển dễ thêm các điều kiện khác nhau ở từng endpoint và tạo ngoại lệ khó nhìn thấy.

## 5. Kiểm tra chức năng, bản ghi và trường dữ liệu

Ba lớp này không thay thế nhau:

| Lớp | Ví dụ câu hỏi |
| --- | --- |
| Chức năng | Chủ thể có được gọi thao tác duyệt hóa đơn không? |
| Bản ghi | Chủ thể có được duyệt hóa đơn cụ thể này không? |
| Trường dữ liệu | Chủ thể có được thay đổi số tiền, người nhận hoặc trạng thái duyệt không? |

Ở mức bản ghi, chỉ biết ID không phải là quyền truy cập. IDOR có thể xảy ra với số thứ tự, UUID hoặc loại định danh khác; trọng tâm là kiểm tra chủ thể có được thực hiện hành động trên đối tượng được chọn hay không. [OWASP API1:2023 — Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/).

Ví dụ yêu cầu của Lan:

~~~http
GET /api/invoices/INV-2048
~~~

Nếu Lan đổi ID sang hóa đơn của Minh và vẫn nhận nội dung riêng tư, lỗi không nằm ở việc định danh dễ đoán. Thay bằng UUID có thể giảm khả năng dò tìm nhưng không bổ sung kiểm tra quyền bị thiếu.

Ở mức trường dữ liệu, quyền đọc một đối tượng không có nghĩa được đọc mọi thuộc tính; quyền sửa cũng không có nghĩa được ghi mọi thuộc tính. OWASP nhấn mạnh việc chọn rõ trường được trả về và trường được phép cập nhật. [OWASP API3:2023 — Broken Object Property Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/).

Trong ví dụ, Lan có thể sửa mô tả hóa đơn nhưng không được tự đặt:

~~~json
{
  "description": "Chi phí công tác",
  "approved": true,
  "ownerId": "another-user",
  "tenantId": "another-tenant"
}
~~~

Một cách xử lý là endpoint chỉ nhận DTO chứa trường được phép sửa, đồng thời kiểm tra quy tắc nghiệp vụ trước khi cập nhật. Không dùng việc client không hiển thị ô nhập làm rào cản cho các trường nhạy cảm.

Với dữ liệu trả về, API có thể dùng DTO riêng cho nhân viên và kế toán. Không serialize toàn bộ entity rồi hy vọng giao diện sẽ ẩn trường không phù hợp.

## 6. Thực thi tại đường xử lý đáng tin cậy

Tại An Bình, việc ẩn nút “Duyệt” giúp giao diện dễ dùng nhưng quyết định cuối vẫn phải được thực thi ở server. API còn có thể được gọi từ client khác hoặc qua một đường tích hợp.

Sơ đồ minh họa trách nhiệm:

~~~mermaid
flowchart LR
    C[Client] --> E[Điểm vào: xác thực và kiểm tra sơ bộ]
    E --> S[Service: kiểm tra hành động và tài nguyên]
    S --> D[Truy vấn và cập nhật đúng phạm vi]
    S --> O[Chọn trường dữ liệu trả về]
    O --> C
    S --> A[Ghi bằng chứng quyết định phù hợp]
~~~

Mỗi tầng cần có trách nhiệm rõ. Chẳng hạn, kiểm tra ở gateway có thể loại bỏ yêu cầu không đăng nhập, nhưng service vẫn biết ai sở hữu hóa đơn và hóa đơn đang ở trạng thái nào.

Mã giả sau minh họa một đường đọc, không phải framework hay thư viện phân quyền hoàn chỉnh:

~~~text
readInvoice(trustedIdentity, selectedTenantId, invoiceId):
    membership = loadCurrentMembership(
        trustedIdentity.subjectId,
        selectedTenantId
    )

    if membership không hoạt động:
        từ chối

    invoice = loadInvoiceWithinTenant(selectedTenantId, invoiceId)

    if invoice không tồn tại trong phạm vi:
        kết thúc theo policy phản hồi đã định

    canReadOwn =
        membership có quyền invoice.read.own
        và invoice.ownerId == trustedIdentity.subjectId

    canReadTenant =
        membership có quyền invoice.read.tenant

    if không canReadOwn và không canReadTenant:
        từ chối

    return employeeInvoiceProjection(invoice)
~~~

Các dữ kiện quan trọng trong ví dụ:

- `trustedIdentity` đến từ đường xác thực đã được kiểm tra, không lấy từ trường `userId` tự khai trong body.
- Tenant được chọn phải đối chiếu với membership hiện tại.
- Tài nguyên được truy xuất trong phạm vi tenant.
- Kết quả chỉ chứa các trường của projection được cho phép.

Nếu có chức năng tải file PDF của hóa đơn, đường đó cần được phân tích riêng. Việc API JSON đã kiểm tra đúng không chứng minh object storage hoặc đường download cũng có kiểm soát tương ứng.

## 7. Ranh giới tenant và những nơi dễ bỏ sót

Tenant context có thể xuất hiện ở hostname, URL hoặc header, nhưng giá trị client gửi phải được xác minh trước khi dùng làm phạm vi tin cậy. Ranh giới tenant còn liên quan tới cache, storage và các tác vụ nền. [Multi-Tenant Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html).

Ví dụ, quản trị tenant A gửi:

~~~http
GET /api/tenants/B/invoices/INV-9001
X-Tenant-Id: A
~~~

Ứng dụng phải có quy tắc xử lý nhất quán khi đường dẫn, header và tài nguyên không cùng phạm vi. Không chọn một giá trị chỉ vì nó làm truy vấn tìm thấy dữ liệu.

Bộ tình huống của An Bình bao phủ thêm:

| Đường truy cập | Sai sót cần tìm |
| --- | --- |
| Tìm kiếm | Kết quả hoặc tổng số bản ghi chứa dữ liệu tenant khác |
| Tải file | URL được tạo cho file ngoài phạm vi |
| Cache | Khóa cache chỉ có ID tài nguyên, thiếu phạm vi cần thiết |
| Bulk update | Một phần danh sách thuộc tenant khác |
| Export | Job tải cả dữ liệu không thuộc người yêu cầu |
| WebSocket | Subscription tiếp tục gửi sự kiện sai phạm vi |

Ràng buộc ở cơ sở dữ liệu có thể là một lớp bảo vệ bổ sung, nhưng nhóm vẫn phải chứng minh các đường ứng dụng sử dụng nó đúng. Không suy ra rằng chỉ thêm cột `tenant_id` đã có tenant isolation.

## 8. Đổi quyền phải ảnh hưởng tới quyết định đang diễn ra

Yêu cầu `v5.0.0-8.3.2` ở L3 đề cập áp dụng ngay thay đổi của giá trị dùng cho phân quyền. Nếu không thể áp dụng ngay, nguồn yêu cầu kiểm soát giảm thiểu để phát hiện hành động không còn được phép và hoàn tác; cách đó không xử lý được thông tin đã lộ. [Yêu cầu 8.3.2 trong V8](https://raw.githubusercontent.com/OWASP/ASVS/v5.0.0_release/5.0/en/0x17-V8-Authorization.md).

Ví dụ, quyền đọc hóa đơn của Minh bị thu hồi lúc 10:00 nhưng token cũ còn một giờ. Nhóm không thể chỉ nói “JWT đã ký đúng” rồi bỏ qua quyền đã thay đổi.

Các phương án thiết kế trong ví dụ có thể gồm kiểm tra trạng thái quyền hiện tại, phiên bản quyền, vô hiệu hóa cache hoặc cơ chế thu hồi phù hợp kiến trúc. Cần kiểm tra đặc tính thực tế, bao gồm độ trễ và tình huống mất kết nối; không coi một phương án riêng lẻ là bằng chứng tự động đáp ứng ASVS.

Ca thử minh họa:

~~~text
T0: Minh đọc được một hóa đơn trong phạm vi được cấp.
T1: Quản trị thu hồi đúng quyền đang dùng.
T2: Minh dùng lại phiên và token cũ để đọc hóa đơn đó.
T3: Thử qua instance khác, cache khác và đường export.
~~~

Báo cáo ghi kết quả ở từng đường. Nếu token cũ vẫn đọc được dữ liệu sau thay đổi trái với yêu cầu, việc ghi log rồi cảnh báo không thu hồi lại được dữ liệu đã trả.

Ngược lại, test phải chắc chắn Minh không còn một đường cấp quyền hợp lệ khác. Gỡ một membership nhưng để nguyên quyền trực tiếp có thể làm quyền vẫn tồn tại theo thiết kế.

## 9. Dịch vụ trung gian không được tự nâng quyền của người gọi

Xét ứng dụng A gọi dịch vụ hóa đơn B để lấy dữ liệu cho Lan. Credential kỹ thuật của A có thể có phạm vi lớn để phục vụ nhiều người. Điều đó không có nghĩa mọi yêu cầu đi qua A đều được dùng toàn bộ phạm vi đó.

Trong thiết kế minh họa, nhóm ghi rõ hai thông tin:

- Dịch vụ nào thực hiện kết nối kỹ thuật?
- Chủ thể nghiệp vụ nào khởi tạo hành động và có phạm vi gì?

Không truyền `X-User-Id` tùy ý rồi để B tin ngay. Cần một cơ chế truyền ngữ cảnh được bảo vệ, kiểm tra nguồn và ràng buộc phạm vi của yêu cầu.

Một mô hình có thể dùng token dành cho downstream hoặc một cơ chế delegation đã thiết kế; lựa chọn cụ thể phụ thuộc kiến trúc. Không chuyển nguyên token sang dịch vụ không nằm trong audience của nó chỉ để “giữ user context”. Việc kiểm tra token và quyết định truy cập vẫn cần thực hiện tại dịch vụ nhận. [REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html).

Tác vụ do hệ thống tự khởi chạy là một trường hợp khác với hành động thay mặt người dùng. Tài liệu cần phân biệt để bộ test không dùng nhầm quyền workload làm bằng chứng về quyền của Lan.

## 10. Fail closed, TOCTOU và thao tác hàng loạt

Ở ví dụ An Bình, nếu không tải được policy cần thiết để bảo vệ thao tác sửa hóa đơn, service không được tiếp tục ghi chỉ vì truy vấn quyền bị timeout. Phản hồi có thể là lỗi dịch vụ theo thiết kế API; điều cần giữ là không cho phép hành động khi thiếu căn cứ.

Đối với thao tác cập nhật, còn có khoảng cách giữa lúc kiểm tra và lúc ghi. Giả sử người dùng được sửa hóa đơn nháp, nhưng hóa đơn chuyển sang trạng thái đã khóa ngay sau bước kiểm tra.

Một câu lệnh cập nhật có điều kiện có thể hỗ trợ phát hiện thay đổi:

~~~sql
UPDATE invoice
SET description = :description,
    version = version + 1
WHERE id = :invoiceId
  AND tenant_id = :tenantId
  AND status = 'DRAFT'
  AND version = :expectedVersion;
~~~

Đây chỉ là một phần của ví dụ. Câu SQL không tự kiểm tra tất cả quyền của người gọi; service vẫn cần xác minh quyền phù hợp và xử lý khi số bản ghi cập nhật không như kỳ vọng.

Với bulk update, nhóm cần chốt trước một trong các hợp đồng nghiệp vụ:

1. Từ chối toàn bộ nếu bất kỳ phần tử nào không được phép.
2. Cho phép xử lý từng phần và báo kết quả theo phần tử mà không làm lộ thông tin ngoài phạm vi.

Không chỉ kiểm tra ID đầu tiên rồi áp dụng kết quả cho cả danh sách. Khi kiểm thử, có thể trộn hóa đơn của Lan với một hóa đơn khác trong cùng request để xác minh hợp đồng đã chọn.

## 11. Ma trận kiểm thử phải có cả ca được phép và bị từ chối

OWASP WSTG phân biệt truy cập ngang và leo quyền dọc; việc kiểm tra cần xét các chủ thể và tài nguyên khác nhau, không chỉ một tài khoản quản trị. [WSTG — Privilege Escalation](https://wstg.owasp.org/stable/4-Web_Application_Security_Testing/05-Authorization_Testing/03-Testing_for_Privilege_Escalation/).

Ma trận cho dữ liệu tổng hợp của An Bình:

| Chủ thể/điều kiện | Thao tác | Kết quả mong đợi theo policy ví dụ |
| --- | --- | --- |
| Lan có quyền đọc của mình | Đọc hóa đơn của Lan | Cho phép, chỉ trường được duyệt |
| Lan | Đọc hóa đơn của Minh | Từ chối |
| Kế toán tenant A | Đọc hóa đơn tenant A | Cho phép theo phạm vi |
| Kế toán tenant A | Đọc hóa đơn tenant B | Từ chối |
| Nhân viên thường | Gọi API cấp quyền quản trị | Từ chối |
| Người duyệt | Duyệt hóa đơn do chính mình tạo | Từ chối theo phân tách nhiệm vụ |
| Chủ thể vừa bị thu hồi quyền | Dùng phiên cũ thực hiện lại | Tuân theo yêu cầu thu hồi đã đặt |
| Policy service lỗi | Thử sửa hóa đơn | Không thực hiện thay đổi |
| Người chỉ được sửa mô tả | Gửi thêm trường approved | Không thay đổi trường cấm |

Mỗi ca cần biết trước tài nguyên thuộc ai và quyền đến từ đâu. Nếu cả hai tài khoản đều có quyền đọc toàn tenant, việc đổi ID giữa họ không phải phép thử phủ định phù hợp.

Kiểm tra phản hồi HTTP là chưa đủ. Một endpoint có thể trả lỗi sau khi đã ghi dữ liệu hoặc đưa job vào hàng đợi. Cần quan sát cả tác dụng phụ và dữ liệu đầu ra.

Bên cạnh đó, ca được phép giúp phát hiện một kiểm soát “an toàn” theo cách chặn toàn bộ người dùng. Mục tiêu là đúng policy, không phải càng nhiều từ chối càng tốt.

## 12. Bao phủ mọi đường thực hiện cùng một nghiệp vụ

Một sản phẩm có thể cho cùng hành động qua web, mobile, API tích hợp hoặc tác vụ nền. Bộ test cần kiểm tra việc phân quyền tại các đường thực sự tồn tại. WSTG hướng dẫn kiểm tra quyền với các chức năng, tài nguyên và vai trò của ứng dụng. [WSTG — Bypassing Authorization Schema](https://wstg.owasp.org/v4.1/4-Web_Application_Security_Testing/05-Authorization_Testing/02-Testing_for_Bypassing_Authorization_Schema/).

Ví dụ, policy “chỉ đọc hóa đơn của mình” có thể thất bại theo nhiều cách:

- Endpoint đọc một hóa đơn kiểm tra đúng nhưng endpoint tìm kiếm không lọc.
- File download chứa đủ dữ liệu dù JSON đã che trường.
- GraphQL resolver trả một quan hệ lồng chưa được kiểm tra.
- Endpoint bulk hoặc phiên bản API cũ bỏ qua điều kiện.
- Job export sử dụng quyền rộng của worker thay cho phạm vi người yêu cầu.
- Kết nối tồn tại lâu không phản ánh thay đổi quyền theo yêu cầu.

Không cần tạo cùng một test ở mọi tầng nếu nó không thêm bằng chứng. Unit test có thể bao phủ bảng policy; integration test xác minh dữ liệu và service; test đầu cuối kiểm tra những đường tích hợp quan trọng.

Mock policy trả `ALLOW` chỉ chứng minh được phần xử lý sau quyết định trong phạm vi mock. Nó không xác minh policy thật, nguồn thuộc tính hoặc việc truyền danh tính.

## 13. Tổ chức bằng chứng đánh giá ASVS

Hồ sơ đánh giá của ví dụ có thể dùng các cột:

| Trường | Nội dung cần ghi |
| --- | --- |
| Yêu cầu | Mã có phiên bản |
| Phạm vi | API, chức năng, tài nguyên và đối tượng người dùng |
| Policy | Quy tắc nghiệp vụ làm căn cứ kỳ vọng |
| Điểm thực thi | Service, truy vấn hoặc thành phần chịu trách nhiệm |
| Bằng chứng | Tài liệu, đoạn mã và kết quả test tương ứng |
| Kết luận | Đạt, không đạt, chưa kiểm tra hoặc không áp dụng có lý do |
| Giới hạn | Phần chưa được bao phủ và giả định của kết quả |

Ví dụ một finding có thể viết:

~~~text
Phạm vi: đọc hóa đơn qua API trong bản build được kiểm tra.
Policy: nhân viên chỉ có invoice.read.own không đọc hóa đơn người khác.
Thực tế: Lan dùng ID hóa đơn của Minh và nhận nội dung.
Bằng chứng: request/response đã giảm thông tin, dữ liệu tổng hợp,
           quyền của hai tài khoản và trạng thái trước/sau ca thử.
Kết luận: thiếu kiểm tra phạm vi bản ghi tại đường đã kiểm tra.
~~~

Báo cáo này có ích hơn câu “có lỗi ASVS” vì người sửa biết chính xác hành động nào và điều kiện nào bị vi phạm.

“Không áp dụng” phải có căn cứ về phạm vi, không được dùng thay cho “chưa làm” hoặc “chưa biết”. Việc một công cụ quét không báo lỗi cũng không xác minh được toàn bộ policy nghiệp vụ.

Không lưu access token, session secret hoặc dữ liệu khách hàng thật vào báo cáo chỉ để chứng minh test đã chạy. Dữ liệu tổng hợp và định danh tham chiếu thường giúp tái hiện kết quả rõ ràng hơn.

## 14. Những kết luận dễ gây nhầm

| Phát biểu | Điều cần kiểm tra tiếp |
| --- | --- |
| “Có SSO nên đã kiểm soát truy cập” | Ứng dụng thực thi quyền tài nguyên như thế nào? |
| “JWT hợp lệ nên được phép” | Token và trạng thái hiện tại có đủ quyền cho hành động này không? |
| “Đã ẩn nút quản trị” | Server có chặn yêu cầu trực tiếp không? |
| “Đã dùng UUID” | Có kiểm tra quyền của đối tượng không? |
| “Có annotation kiểm tra role” | Có bao phủ bản ghi, trường và các đường vào khác không? |
| “Đã pass phần V8” | Phạm vi, mức, phiên bản và bằng chứng cụ thể là gì? |
| “Có audit nên chấp nhận quyền cũ” | Hành động trái phép có bị chặn, và dữ liệu lộ có thể thu hồi không? |

Các câu hỏi này giúp phân biệt tính năng đã cài đặt với hành vi đã được xác minh. Một hệ thống có thể dùng thư viện phân quyền tốt nhưng vẫn thiếu một nhánh nghiệp vụ hoặc cung cấp thuộc tính sai cho policy.

## 15. Bài tập thiết kế và kiểm chứng

Hãy xây dựng policy cho một cổng hỗ trợ khách hàng đa tenant với ba nhóm: khách hàng, nhân viên hỗ trợ và quản trị tenant.

Mỗi ticket có người tạo, tenant, trạng thái và ghi chú nội bộ. Đặt các giả định nghiệp vụ rõ ràng, rồi thực hiện:

1. Xác định ai được xem, sửa, đóng và xuất ticket.
2. Phân biệt quyền đọc ticket với quyền đọc ghi chú nội bộ.
3. Xác định nguồn tin cậy của tenant và membership.
4. Thiết kế ca đổi ID, đổi tenant và gửi thêm trường cập nhật.
5. Xác định tác động khi quyền hỗ trợ bị thu hồi trong lúc export đang chờ.
6. Nối từng nhóm kiểm tra với mã ASVS 5.0.0 phù hợp sau khi đọc nguyên văn yêu cầu.

Một lời giải tốt sẽ nêu rõ cả đường được phép lẫn đường bị từ chối, nơi thực thi, dữ kiện đầu vào và bằng chứng cần thu thập. Nó cũng nhận ra những giới hạn: kiểm tra một API không chứng minh mọi kênh đã được bao phủ, và kiểm tra access control không thay thế đánh giá toàn bộ ASVS.

Các tên yêu cầu và mã trong bài được tham chiếu từ dự án OWASP ASVS, được công bố theo [CC BY-SA 4.0](https://github.com/OWASP/ASVS#license). Các tình huống An Bình, policy và mã minh họa là diễn giải phục vụ bài học, không phải bản dịch nguyên văn hoặc chứng nhận của OWASP.
