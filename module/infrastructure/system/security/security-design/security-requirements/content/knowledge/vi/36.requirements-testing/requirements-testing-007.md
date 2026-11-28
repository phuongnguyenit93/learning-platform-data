# Authorization test — Kiểm thử việc thực thi phân quyền

## 1. Authorization test kiểm chứng điều gì?

**Authorization test** kiểm tra hệ thống có thực thi đúng quyết định **ai được làm hành động gì trên tài nguyên nào, trong điều kiện nào** hay không.

Trong chương **Kiểm thử yêu cầu**, mục tiêu là tạo bằng chứng cho yêu cầu phân quyền đã được đặc tả, đồng thời phát hiện đường truy cập hoặc điều kiện chưa được bảo vệ đầy đủ.

Ví dụ, yêu cầu “người dùng chỉ được xem đề nghị mua sắm của mình” cần được kiểm chứng bằng cả hai phía:

- Người có quyền thực sự đọc được dữ liệu thuộc phạm vi.
- Người đã đăng nhập nhưng không có quyền không đọc được dữ liệu của người khác.

Chỉ gửi yêu cầu không có token rồi nhận lỗi chưa đủ đánh giá phân quyền giữa những người đã được xác thực.

### Ba khái niệm cần phân biệt

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Authentication — xác thực | Chủ thể là ai? | Token có hợp lệ và xác định đúng người dùng không? |
| Access authorization — phân quyền truy cập | Chủ thể được làm gì trên tài nguyên? | Người này có được duyệt đề nghị cụ thể không? |
| Security authorization — phê duyệt vận hành | Có chấp nhận rủi ro của hệ thống trong phạm vi đã xác định không? | Quyết định cho hệ thống vận hành dựa trên hồ sơ rủi ro |

Bài học tập trung vào **access authorization**. Xác thực tạo đầu vào danh tính, nhưng danh tính hợp lệ không tự mang quyền với mọi đối tượng.

[OWASP WSTG v4.2 — Testing for Bypassing Authorization Schema](https://wstg.owasp.org/v4.2/4-Web_Application_Security_Testing/05-Authorization_Testing/02-Testing_for_Bypassing_Authorization_Schema/) mô tả kiểm tra việc vượt quyền ngang và dọc giữa các danh tính hoặc vai trò. Đây là nguồn tham chiếu cho nhóm tình huống phân quyền của bài.

Sau bài học, người học cần có thể:

1. Chuyển yêu cầu phân quyền thành ma trận tình huống được phép và bị từ chối.
2. Chuẩn bị danh tính, tài nguyên và trạng thái giúp phân biệt lỗi phân quyền với lỗi khác.
3. Kiểm tra quyền ở mức chức năng, đối tượng, thuộc tính và ngữ cảnh.
4. Xác minh dữ liệu trả về và tác động nghiệp vụ, thay vì chỉ nhìn mã HTTP.
5. Liên kết kết quả với yêu cầu, rủi ro, phiên bản và điều kiện đánh giá.

## 2. Mô hình quyết định quyền cần được kiểm thử

Có thể diễn đạt một quyết định quyền như sau:

**Quyết định = chính sách(chủ thể, hành động, tài nguyên, ngữ cảnh).**

| Thành phần | Ví dụ |
| --- | --- |
| Chủ thể | Người dùng, tài khoản dịch vụ, tác vụ chạy theo ủy quyền |
| Hành động | Đọc, sửa, xóa, duyệt, xuất dữ liệu, cấp quyền |
| Tài nguyên | Đề nghị, tệp đính kèm, nhóm dự án, tài khoản |
| Quan hệ | Người tạo, người được phân công, thành viên tenant |
| Thuộc tính | Vai trò, trạng thái tài nguyên, phạm vi ủy quyền |
| Ngữ cảnh | Quyền hiện hành, thời điểm, luồng xử lý, trạng thái phụ thuộc |

Một bảng chỉ có “Admin được truy cập, User bị từ chối” thường chưa mô tả đủ chính sách.

Các mô hình quyền có thể dùng vai trò, thuộc tính hoặc quan hệ. Khi kiểm thử, cần đi theo quy tắc thực tế của hệ thống; không giả định vai trò cao hơn tự động có mọi quyền của vai trò khác.

Ví dụ, người quản trị thành viên có thể được cấp quyền tài khoản nhưng không có quyền đọc hồ sơ nghiệp vụ. Một người đồng thời có hai vai trò vẫn có thể bị ràng buộc bởi quy tắc không tự duyệt yêu cầu của mình.

### Những kết quả cần quan sát

Một ca kiểm thử có thể cần đánh giá đồng thời:

- Quyết định được phép hay bị từ chối.
- Nội dung, trường dữ liệu và tệp được trả về.
- Trạng thái lưu trữ trước và sau.
- Sự kiện nghiệp vụ, tác vụ nền hoặc thông báo phát sinh.
- Sự kiện audit theo yêu cầu.
- Thời điểm quyết định khi quyền hoặc tài nguyên thay đổi.

Không phải ca nào cũng cần kiểm tra tất cả. Chọn điểm quan sát theo điều mà yêu cầu đang bảo vệ.

## 3. Đầu vào trước khi viết ca kiểm thử

### 3.1. Yêu cầu và chính sách có nguồn

Trước hết cần có:

- Mã, phiên bản và phát biểu yêu cầu.
- Vai trò, quan hệ và phạm vi tài nguyên.
- Hành vi mặc định khi không đủ thông tin quyền.
- Quy tắc ngoại lệ hoặc hỗ trợ đặc quyền nếu có.
- Hợp đồng phản hồi API.
- Điều kiện thời gian, thu hồi hoặc thay đổi quyền.
- Những tác động bị cấm và sự kiện cần ghi.

Nếu nghiệp vụ chưa quyết định người nào được đọc một loại tài nguyên, ca kiểm thử không nên tự trở thành nơi đặt chính sách.

Kết quả mong đợi cần được xác nhận độc lập với cách triển khai. Nếu bộ kiểm thử gọi chính hàm quyết định quyền của sản phẩm để tính kết quả mong đợi, một lỗi trong hàm có thể khiến cả hai phía cùng sai mà kiểm thử vẫn xanh.

### 3.2. Danh mục đường truy cập

Liệt kê các đường có thể thực hiện cùng hành động:

| Nhóm đường | Ví dụ cần xem xét |
| --- | --- |
| API chi tiết | Đọc, sửa hoặc xóa theo mã đối tượng |
| API tập hợp | Danh sách, tìm kiếm, phân trang, thống kê |
| Hành động nghiệp vụ | Submit, approve, reject, assign |
| Tệp và bản xuất | Tải trực tiếp, xem trước, xuất đồng bộ hoặc bất đồng bộ |
| API quản trị | Cấp vai trò, quản lý thành viên, thay cấu hình |
| Giao diện khác | Mobile, GraphQL hoặc API phiên bản cũ nếu có |
| Thành phần phía sau | Worker, consumer, dịch vụ nhận lệnh theo ủy quyền |

Không xem việc ẩn nút trên UI là bằng chứng máy chủ thực thi quyền. Cần kiểm tra yêu cầu trực tiếp đến giao diện thực sự xử lý hành động.

### 3.3. Môi trường và dữ liệu kiểm thử

Dùng tài khoản, tenant và dữ liệu được tạo cho đánh giá trong môi trường thuộc phạm vi đã cho phép. Với một bài học hoặc bộ kiểm thử của dự án, các tình huống nên tái lập được và không cần dữ liệu thật của khách hàng.

Cần có kênh quan sát đáng tin cậy để kiểm tra trạng thái, sự kiện hoặc tệp. Kênh này có thể có quyền cao hơn chủ thể đang được thử, nhưng phải được tách khỏi phiên gửi yêu cầu nghiệp vụ.

Ví dụ, dùng tài khoản đánh giá riêng để xác nhận bản ghi tồn tại không có nghĩa được dùng token của tài khoản đó cho ca kiểm thử người dùng thông thường.

## 4. Ví dụ chính sách: hệ thống đề nghị mua sắm nhiều tenant

Toàn bộ quy tắc và dữ liệu trong ví dụ là giả định để học cách kiểm thử.

### 4.1. Quy tắc nghiệp vụ

Hệ thống có các tenant độc lập và dự án trong từng tenant:

- **Requester** được đọc đề nghị do mình tạo trong tenant của mình; chỉ được sửa nội dung khi đề nghị còn ở trạng thái DRAFT.
- **Approver** được đọc đề nghị SUBMITTED hoặc APPROVED của dự án được phân công; chỉ được duyệt đề nghị SUBMITTED thuộc phạm vi đó.
- Một người không được duyệt đề nghị do chính mình tạo, kể cả khi đồng thời có vai trò Approver.
- **Auditor** được đọc đề nghị trong tenant của mình nhưng không được thay đổi hoặc duyệt.
- **TenantAdmin** được quản lý thành viên trong tenant; vai trò này không tự cấp quyền đọc hoặc duyệt đề nghị.
- Không vai trò nào trong ví dụ có quyền xuyên tenant.
- Trường internalReviewNote chỉ được đọc bởi Approver đủ phạm vi hoặc Auditor; người tạo không tự có quyền với trường đó.
- Các trường do máy chủ quản lý như tenantId, ownerId, status và approvedBy không được thay đổi qua API sửa nội dung thông thường.

Nếu một người có nhiều vai trò, quyền được xét theo các quy tắc tương ứng; quy tắc cấm tự duyệt vẫn phải có hiệu lực.

### 4.2. Các yêu cầu cần kiểm chứng

| Mã | Yêu cầu |
| --- | --- |
| AUTHZ-TENANT-01 | Không đọc hoặc thay đổi đề nghị thuộc tenant ngoài phạm vi của chủ thể |
| AUTHZ-READ-01 | Đọc đề nghị theo đúng quan hệ người tạo, phân công dự án hoặc vai trò Auditor |
| AUTHZ-APPROVE-01 | Chỉ Approver đúng phạm vi được duyệt đề nghị SUBMITTED và không được tự duyệt |
| AUTHZ-ADMIN-01 | Chỉ TenantAdmin được quản lý thành viên trong tenant của mình |
| AUTHZ-PROP-01 | Giới hạn trường dữ liệu được đọc và thay đổi theo chính sách |
| AUTHZ-REVOKE-01 | Quyền bị thu hồi phải có hiệu lực trong giới hạn thời gian đã xác nhận |
| AUTHZ-JOB-01 | Bản xuất chỉ được bàn giao dữ liệu mà người nhận còn quyền đọc tại thời điểm quy định |
| AUTHZ-AUDIT-01 | Nỗ lực duyệt bị từ chối phải có sự kiện audit theo lược đồ, không tạo tác động duyệt |

Mỗi yêu cầu có thể có nhiều ca kiểm thử. Một ca cũng có thể hỗ trợ nhiều yêu cầu, nhưng cần biết quan sát nào chứng minh phần nào.

### 4.3. Danh tính và tài nguyên mẫu

| Danh tính | Tenant | Vai trò và quan hệ |
| --- | --- | --- |
| reqA1 | A | Requester |
| reqA2 | A | Requester khác reqA1 |
| appA | A | Approver được phân công dự án P1 |
| dualA | A | Requester và Approver của P1 |
| admA | A | Chỉ có TenantAdmin |
| audA | A | Auditor |
| reqB | B | Requester |

| Tài nguyên | Tenant/dự án | Người tạo | Trạng thái |
| --- | --- | --- | --- |
| A-DRAFT-1 | A/P1 | reqA1 | DRAFT |
| A-SUB-1 | A/P1 | reqA1 | SUBMITTED |
| A-SUB-2 | A/P2 | reqA2 | SUBMITTED |
| A-SELF-1 | A/P1 | dualA | SUBMITTED |
| B-SUB-1 | B/P9 | reqB | SUBMITTED |

Dùng các mã có sẵn trong fixture giúp kiểm tra truy cập trái quyền mà không phải đoán tài nguyên. Phải xác nhận tài nguyên thực sự tồn tại và có trạng thái phù hợp trước khi chạy ca kiểm thử.

## 5. Lập ma trận quyền và chọn tình huống đối chứng

[OWASP Authorization Testing Automation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Testing_Automation.html) trình bày cách dùng ma trận chức năng, vai trò và dữ liệu làm đầu vào cho kiểm thử tự động. Trong thực hành, cần bổ sung các chiều ngữ cảnh mà chính sách của dự án sử dụng.

### 5.1. Ma trận tình huống ban đầu

| Chủ thể | Hành động và tài nguyên | Kết quả mong đợi | Điều đang kiểm chứng |
| --- | --- | --- | --- |
| reqA1 | Đọc A-DRAFT-1 | Cho phép, giới hạn trường theo vai trò | Người tạo đọc được dữ liệu của mình |
| reqA2 | Đọc A-SUB-1 | Từ chối | Cùng tenant không có nghĩa cùng quyền |
| appA | Đọc A-SUB-1 | Cho phép | Phân công P1 có hiệu lực với trạng thái phù hợp |
| appA | Đọc A-DRAFT-1 | Từ chối | Approver không tự đọc mọi trạng thái |
| appA | Đọc A-SUB-2 | Từ chối | Không được phân công P2 |
| audA | Đọc A-SUB-2 | Cho phép | Phạm vi Auditor trong tenant A |
| admA | Đọc A-SUB-1 | Từ chối | Quản trị thành viên không tự có quyền nội dung |
| appA | Duyệt A-SUB-1 | Cho phép | Approver đúng phạm vi |
| reqA1 | Duyệt A-SUB-1 | Từ chối | Requester không có quyền duyệt |
| dualA | Duyệt A-SELF-1 | Từ chối | Cấm tự duyệt dù có nhiều vai trò |
| reqA1 | Quản lý thành viên tenant A | Từ chối | Chức năng quản trị cần quyền riêng |
| admA | Quản lý thành viên tenant A | Cho phép | Tình huống đối chứng cho chức năng quản trị |
| audA | Đọc B-SUB-1 | Từ chối | Quyền đọc rộng vẫn bị giới hạn tenant |
| admA | Quản lý thành viên tenant B | Từ chối | Quyền quản trị không xuyên tenant |

Từng ca thay đổi dữ liệu cần có fixture độc lập hoặc khôi phục trạng thái đúng cách. Nếu ca cho phép đã chuyển A-SUB-1 sang APPROVED, ca tiếp theo không được vô tình đánh giá trên trạng thái khác mà không biết.

### 5.2. Vì sao cần ca được phép?

Nếu endpoint không tồn tại, dữ liệu không được tạo hoặc hệ thống từ chối mọi người, tất cả ca âm có thể “đạt”. Ca được phép giúp xác nhận tuyến xử lý và dữ liệu thử hoạt động.

Một cách chuẩn bị:

1. Xác nhận tài nguyên tồn tại qua kênh đánh giá đáng tin cậy.
2. Chứng minh một danh tính phù hợp thực hiện được hành động trên fixture tương ứng.
3. Tạo hoặc đặt lại fixture để tránh tác động của bước đối chứng.
4. Thực hiện ca bị từ chối bằng danh tính cần đánh giá.
5. Xác minh quyết định và trạng thái sau xử lý.

Không bắt buộc chạy lại mọi ca dương ngay trước mọi ca âm nếu bộ fixture đã đảm bảo các điều kiện này. Nhưng khi kết quả khó giải thích, cần kiểm tra lại điều kiện đối chứng.

### 5.3. Đừng cố bao phủ mọi tổ hợp bằng một bảng phẳng

Số tổ hợp tăng theo chủ thể, hành động, tài nguyên, tenant, trạng thái và thời điểm. Có thể nhóm thành các lớp tương đương để chọn đại diện.

Tuy vậy, những tổ hợp rủi ro cao phải được chỉ định rõ: chéo tenant, tự duyệt, tài khoản nhiều vai trò, quyền vừa bị thu hồi và tác vụ đang chạy. Một kỹ thuật chọn tổ hợp tổng quát không tự bảo đảm đã kiểm tra các quy tắc này.

## 6. Kiểm thử quyền ngang, quyền dọc và quan hệ đối tượng

### 6.1. Quyền ngang: đổi đối tượng hoặc danh tính cùng cấp

Hai Requester cùng tenant không mặc nhiên đọc được đề nghị của nhau. Dùng token hợp lệ của reqA2 để yêu cầu A-SUB-1 do reqA1 tạo.

~~~http
GET /api/purchase-requests/A-SUB-1 HTTP/1.1
Host: test.example
Authorization: Bearer <valid-token-of-reqA2>
~~~

Cần xác minh:

- Không trả nội dung thuộc đề nghị.
- Không trả tệp đính kèm hoặc liên kết tải có hiệu lực.
- Không xuất hiện trường dữ liệu bị hạn chế trong phản hồi lỗi.
- Không có tác động nghiệp vụ ngoài hành vi được cho phép.

Tham chiếu đối tượng có thể nằm trong path, query, body, header hoặc cấu trúc lồng nhau. Không chỉ thay một tham số URL rồi coi mọi đường đã được kiểm tra.

[OWASP WSTG v4.2 — Testing for Insecure Direct Object References](https://wstg.owasp.org/v4.2/4-Web_Application_Security_Testing/05-Authorization_Testing/04-Testing_for_Insecure_Direct_Object_References/) đề xuất dùng nhiều người dùng với các tài nguyên đã biết để đánh giá kiểm soát truy cập theo tham chiếu đối tượng.

### 6.2. Quyền dọc: gọi chức năng của vai trò khác

Gửi yêu cầu quản lý thành viên bằng phiên Requester hợp lệ. Không phụ thuộc việc UI có hiển thị nút hay không.

Yêu cầu thử cần có cấu trúc hợp lệ và các điều kiện phụ trợ hợp lệ. Nếu request bị từ chối vì JSON sai hoặc thiếu thông tin bắt buộc, chưa thể kết luận chức năng đã kiểm tra quyền.

[OWASP API5:2023 — Broken Function Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa5-broken-function-level-authorization/) tập trung vào quyền gọi chức năng, bao gồm ranh giới giữa chức năng quản trị và chức năng thông thường.

Đối với ví dụ, cần kiểm tra cả:

- reqA1 không quản lý được thành viên tenant A.
- admA quản lý được thành viên tenant A.
- admA không quản lý được thành viên tenant B.

### 6.3. Quyền trên đối tượng: được gọi hàm chưa đủ

appA có vai trò Approver nhưng chỉ được phân công P1. Việc appA gọi được endpoint duyệt không chứng minh appA có quyền với A-SUB-2 thuộc P2.

[OWASP API1:2023 — Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/) phân biệt kiểm soát ở mức đối tượng với quyền truy cập chức năng. Mã đối tượng có thể là số, UUID hoặc chuỗi; tính khó đoán không thay thế việc kiểm tra quyền.

Ca kiểm thử cần giữ nguyên phiên hợp lệ và thay tài nguyên trong phạm vi fixture để đánh giá đúng quyết định quyền trên đối tượng.

### 6.4. Kiểm tra quan hệ cha–con

Một đường dẫn có thể chứa nhiều mã:

~~~http
GET /api/projects/P1/purchase-requests/A-SUB-2/attachments/F1 HTTP/1.1
Host: test.example
Authorization: Bearer <valid-token-of-appA>
~~~

Trong fixture, A-SUB-2 thuộc P2. Dù chủ thể có quyền với P1, hệ thống không được chỉ kiểm tra mã dự án ở ngoài rồi dùng mã đề nghị bên trong để trả dữ liệu.

Tình huống nên bao gồm:

- Cha hợp lệ nhưng con không thuộc cha.
- Đối tượng con thuộc tenant khác.
- Tệp được gọi trực tiếp mà không qua đường dẫn đề nghị.
- Mã đối tượng trong body mâu thuẫn với path.

Kết quả phản hồi phải theo hợp đồng API; điều kiện bảo mật cốt lõi là không truy cập hoặc thay đổi tài nguyên ngoài quyền.

## 7. Kiểm thử thuộc tính, danh sách và hành động hàng loạt

### 7.1. Được đọc đối tượng không đồng nghĩa đọc mọi trường

reqA1 được đọc A-SUB-1 nhưng không được đọc internalReviewNote. Kiểm tra biểu diễn dữ liệu thực tế trên API chi tiết, danh sách, bản xuất và giao diện có thể yêu cầu thêm trường.

Cần kiểm tra rằng trường bị hạn chế không được trả theo hợp đồng đã xác định. Nếu hợp đồng yêu cầu bỏ hẳn trường, trả khóa với giá trị thật hoặc một biểu diễn lồng nhau khác đều là không đạt.

[OWASP API3:2023 — Broken Object Property Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/) đề cập cả việc đọc và thay đổi thuộc tính ngoài quyền. Do đó, chỉ kiểm tra quyền đối với toàn đối tượng là chưa đủ.

### 7.2. Kiểm tra các trường do máy chủ quản lý

Trong ca sửa bản nháp của chính mình, thêm các trường không được sửa qua API thông thường:

~~~http
PATCH /api/purchase-requests/A-DRAFT-1 HTTP/1.1
Host: test.example
Authorization: Bearer <valid-token-of-reqA1>
Content-Type: application/json

{
  "description": "Updated test description",
  "tenantId": "B",
  "ownerId": "reqA2",
  "status": "APPROVED",
  "approvedBy": "appA"
}
~~~

Hợp đồng cần xác định sẽ từ chối payload hay bỏ qua trường không được phép. Bộ kiểm thử phải dùng đúng lựa chọn đã thống nhất.

Dù phản hồi thế nào, không được xảy ra việc chuyển tenant, đổi chủ sở hữu hoặc tự đặt trạng thái APPROVED qua đường sửa nội dung. Đọc lại bằng kênh kiểm tra đáng tin cậy để xác minh trạng thái thực tế.

### 7.3. Danh sách, tìm kiếm và thống kê

Một API chi tiết được bảo vệ đúng không chứng minh API danh sách đã lọc đúng.

Dữ liệu thử nên có cả bản ghi được phép và không được phép. Kiểm tra:

- Phần tử trong từng trang.
- Bộ lọc do client gửi.
- Phân trang, con trỏ và sắp xếp.
- Tìm kiếm theo một chuỗi đánh dấu chỉ có ở tài nguyên bị hạn chế.
- Tệp đính kèm, preview và bản xuất từ kết quả.
- Metadata hoặc thống kê thuộc phạm vi bảo vệ.

Nếu total được định nghĩa là tổng bản ghi nhìn thấy được, số đó phải tương ứng phạm vi quyền. Nếu nghiệp vụ cho phép một thống kê tổng hợp rộng hơn, cần yêu cầu riêng xác định mức thông tin được công bố; không để người viết test tự quyết định.

### 7.4. Batch chứa cả tài nguyên được phép và bị cấm

Ví dụ một yêu cầu batch gồm A-SUB-1 và B-SUB-1. Có ít nhất hai kiểu hợp đồng:

- Từ chối toàn bộ batch.
- Xử lý riêng từng mục, trả kết quả theo từng mục được phép.

Kiểm thử phải theo hợp đồng đã chấp thuận. Trong cả hai cách, B-SUB-1 không được đọc hoặc thay đổi trái quyền.

Với thao tác ghi, kiểm tra tính nguyên tử nếu yêu cầu quy định. Không kết luận “đạt” chỉ vì phần tử bị cấm trả lỗi trong khi dữ liệu của nó đã bị thay đổi.

## 8. Kiểm tra tác động nghiệp vụ ngoài phản hồi HTTP

### 8.1. Một lỗi phản hồi có thể xuất hiện sau tác động trái quyền

Giả sử reqA1 gửi yêu cầu duyệt A-SUB-1 và nhận phản hồi từ chối. Nếu bản ghi đã chuyển APPROVED trước khi phản hồi được tạo, AUTHZ-APPROVE-01 vẫn bị vi phạm.

Với ca duyệt bị từ chối, cần xem xét:

- Trạng thái đề nghị vẫn giữ nguyên.
- approvedBy và thời điểm duyệt không được ghi trái quyền.
- Không phát sinh sự kiện nghiệp vụ RequestApproved.
- Không xếp lịch tác vụ hoặc thông báo mang ý nghĩa đã duyệt.
- Có sự kiện audit từ chối theo AUTHZ-AUDIT-01.

Sự kiện audit từ chối là tác động được mong đợi. Không dùng điều kiện “không được có bất kỳ thay đổi hoặc sự kiện nào” nếu điều đó mâu thuẫn yêu cầu truy vết.

### 8.2. Thuật toán kiểm thử minh họa

~~~text
given:
  một đề nghị SUBMITTED có chủ sở hữu reqA1
  reqA1 có phiên hợp lệ nhưng không có quyền duyệt
  payload và các điều kiện phụ trợ đều hợp lệ

before:
  ghi nhận trạng thái nghiệp vụ của đề nghị
  tạo định danh tương quan riêng cho ca thử

act:
  gọi hành động duyệt bằng phiên reqA1

observe:
  kiểm tra phản hồi từ chối theo hợp đồng
  xác minh trạng thái và các trường duyệt không thay đổi
  kiểm tra sự kiện nghiệp vụ và tác vụ có cùng định danh tương quan
  kiểm tra sự kiện audit từ chối nếu thuộc yêu cầu

pass only if:
  không có tác động duyệt trái quyền
  không có dữ liệu bị cấm trong phản hồi
  yêu cầu audit liên quan được đáp ứng
~~~

Đây là mã giả mô tả ý định; các hàm quan sát phụ thuộc hạ tầng kiểm thử của dự án.

### 8.3. Chờ xử lý bất đồng bộ bằng điều kiện rõ

Không thấy sự kiện ngay sau phản hồi chưa chứng minh không có sự kiện. Hệ thống có thể dùng outbox, hàng đợi hoặc worker.

Cần biết ranh giới hoàn tất và giới hạn quan sát: sự kiện đã được xử lý đến đâu, tác vụ nào hoàn tất, hoặc cửa sổ giao nhận nào thuộc hợp đồng thử. Dùng cơ chế đồng bộ và chờ có giới hạn phù hợp, thay vì chèn một khoảng ngủ tùy ý rồi kết luận.

Không chỉ kiểm tra log “access denied”. Log đó có thể được ghi trong khi một nhánh xử lý khác đã tạo tác động.

## 9. Kiểm thử thay đổi quyền, cache và tác vụ nền

### 9.1. Quyền vừa được thu hồi

Giả sử AUTHZ-REVOKE-01 được đặc tả là: không muộn hơn 60 giây sau khi thay đổi phân công được xác nhận thành công, yêu cầu mới dùng phiên hoặc token cũ không được duyệt đề nghị thuộc dự án đã mất quyền.

Ngưỡng 60 giây là giả định minh họa.

Kịch bản:

1. appA duyệt được tài nguyên thích hợp của P1 trong fixture đối chứng.
2. Tạo fixture SUBMITTED mới cho ca thu hồi.
3. Thu hồi phân công P1 và ghi mốc xác nhận.
4. Dùng phiên hoặc token cũ gửi yêu cầu mới đến các đường xử lý liên quan.
5. Sau giới hạn, xác minh quyết định từ chối và không có tác động duyệt.

Chỉ đăng nhập lại rồi thử có thể bỏ sót token cũ còn được hệ thống tin. Cần bao phủ các loại phiên được hỗ trợ và các nút xử lý có thể có cache khác nhau.

### 9.2. Cache không được làm lẫn phạm vi quyền

Có thể làm nóng cache bằng chủ thể có quyền, rồi yêu cầu cùng tài nguyên bằng chủ thể không có quyền.

Ví dụ:

- audA đọc A-SUB-1, sau đó reqA2 đọc cùng tài nguyên.
- Một chủ thể tenant B đọc tài nguyên của B, sau đó chủ thể A gọi đường có cùng dạng định danh hoặc tham số.
- Người dùng mất quyền rồi gọi lại đường từng được cache.

Mục tiêu là kiểm tra kết quả bảo vệ, không bắt buộc một thiết kế cache duy nhất. Dữ liệu đối tượng có thể được cache nếu việc thực thi quyền vẫn đúng.

### 9.3. Tác vụ nền chạy theo ủy quyền

Một service account có quyền kỹ thuật rộng không có nghĩa người yêu cầu được nhận mọi dữ liệu mà service account đọc được.

Với bản xuất bất đồng bộ, cần kiểm tra:

- Người khởi tạo có quyền yêu cầu tập dữ liệu đó.
- Phạm vi tenant và tài nguyên được giữ đúng qua hàng đợi.
- Quyền được xét tại thời điểm mà yêu cầu quy định.
- Người tải bản xuất được xác minh đúng quyền.
- URL hoặc mã tác vụ không cho người khác tải dữ liệu ngoài phạm vi.

Nếu AUTHZ-JOB-01 yêu cầu quyền hiện hành tại thời điểm bàn giao, hãy thu hồi quyền sau khi xếp hàng nhưng trước khi bàn giao và xác minh dữ liệu bị loại hoặc bàn giao bị từ chối theo hợp đồng.

Một phản hồi 202 chỉ cho biết yêu cầu đã được tiếp nhận theo giao thức của ứng dụng; chưa chứng minh tác vụ sau đó không tạo hoặc không bàn giao dữ liệu trái quyền.

### 9.4. Thời điểm kiểm tra và thay đổi đồng thời

Quyền hoặc trạng thái có thể đổi giữa kiểm tra và tác động. Cần đặc tả thời điểm nào là điểm quyết định có hiệu lực đối với hành động đang chạy.

Đối với một nghiệp vụ yêu cầu kiểm tra lại trước khi ghi hoặc bàn giao, ca thử có thể dùng điểm đồng bộ có kiểm soát để thay đổi quyền giữa các giai đoạn. Tránh chỉ chạy nhiều luồng rồi hy vọng tái hiện được một khoảng thời gian rất nhỏ.

Không áp đặt cùng hành vi cho mọi nghiệp vụ nếu yêu cầu chưa quyết định cách xử lý hành động đang chạy. Đây có thể là khoảng trống đặc tả cần làm rõ trước khi kết luận hệ thống sai.

## 10. Tránh kết luận sai từ những lỗi không phải phân quyền

Một ca âm chỉ có giá trị khi nó đi đến đúng điều kiện cần đánh giá.

| Kết quả quan sát | Vì sao chưa đủ kết luận phân quyền đúng? | Cách làm rõ |
| --- | --- | --- |
| Token sửa tay bị từ chối | Có thể mới kiểm tra tính hợp lệ của xác thực | Dùng token hợp lệ của chủ thể thiếu quyền |
| Payload sai định dạng bị lỗi | Có thể request dừng ở bước parse hoặc validation | Dùng payload hợp lệ tương đương ca đối chứng |
| Thiếu thông tin chống CSRF bị chặn | Có thể cơ chế CSRF chặn trước khi xét quyền | Chuẩn bị phiên và điều kiện phụ trợ hợp lệ |
| Nhận 404 | Có thể sai route, sai phiên bản hoặc tài nguyên không tồn tại | Xác nhận endpoint và fixture tồn tại; theo hợp đồng từ chối đã định |
| Nhận 405 | Có thể dùng sai HTTP method | Dùng method thực sự thực hiện hành động |
| Nhận 500 | Có thể lỗi hạ tầng hoặc xử lý chưa hoàn tất | Điều tra nguyên nhân, không coi mặc định là ca đạt |
| Không nhìn thấy nút trên UI | Có thể API vẫn nhận yêu cầu trực tiếp | Gọi đường xử lý bằng danh tính cần đánh giá |
| Nhận lỗi nhưng dữ liệu đã đổi | Quyết định từ chối không ngăn được tác động | Kiểm tra trạng thái, sự kiện và tác vụ sau xử lý |
| Ca âm luôn đạt trên môi trường rỗng | Không có tài nguyên để gây lộ hoặc thay đổi | Xác nhận fixture và có đối chứng được phép |

### 10.1. Mã HTTP là một phần hợp đồng

Ứng dụng có thể dùng cách biểu diễn từ chối khác nhau, bao gồm che giấu sự tồn tại của tài nguyên. Bộ kiểm thử phải kiểm tra hợp đồng cụ thể và thuộc tính bảo vệ.

Không dùng điều kiện “bất kỳ mã 4xx nào cũng đạt”. Một lỗi validation không chứng minh yêu cầu đã được phân quyền.

Nếu hợp đồng của fixture quy định trả 403 cho ca thiếu quyền, hãy kiểm tra 403 cùng các điều kiện dữ liệu và tác động. Nếu quy định che giấu bằng 404, ca thử phải biết tài nguyên thực sự tồn tại và phản hồi không lộ thông tin bị hạn chế.

### 10.2. Tách các lớp kiểm tra để biết bằng chứng có giới hạn gì

| Lớp | Giá trị | Giới hạn |
| --- | --- | --- |
| Kiểm tra hàm chính sách | Bao phủ nhiều tổ hợp quyền nhanh | Không chứng minh endpoint đã gọi hàm đó |
| Kiểm tra thành phần nghiệp vụ | Xem quyền gắn với hành động và dữ liệu | Có thể bỏ qua cấu hình ở lớp HTTP hoặc gateway |
| Kiểm tra tích hợp API | Đánh giá từ request đến dữ liệu và tác động | Cần fixture và môi trường phù hợp |
| Kiểm tra qua cấu hình triển khai | Phát hiện sai khác routing, proxy, cache và danh tính | Thường tốn tài nguyên hơn |
| Đánh giá thủ công theo rủi ro | Tìm đường mới, quan hệ phức tạp và khoảng trống chính sách | Cần ghi rõ phạm vi và bằng chứng để tái lập |

Giả lập principal ở một bài kiểm tra thành phần là hữu ích, nhưng không chứng minh token thật được xác minh hoặc ánh xạ vai trò đúng trong triển khai. Cần các ca tích hợp tương ứng.

Ngược lại, một ca đăng nhập thành công không chứng minh quyền đối tượng và dữ liệu đã được thực thi đúng.

## 11. Tự động hóa theo yêu cầu và ma trận quyền

### 11.1. Biểu diễn ca thử bằng dữ liệu rõ ràng

Một vector kiểm thử có thể gồm:

- Mã ca và mã yêu cầu.
- Chủ thể, tenant, vai trò và quan hệ fixture.
- Hành động, tài nguyên và trạng thái trước.
- Điều kiện phụ trợ.
- Quyết định mong đợi.
- Hợp đồng phản hồi.
- Những trường dữ liệu và tác động cần quan sát.
- Điều kiện hoàn tất xử lý.
- Cách chuẩn bị và dọn fixture.

Ví dụ dưới đây là dữ liệu minh họa cho một harness do dự án xây dựng, không phải định dạng chuẩn bắt buộc.

~~~yaml
case_id: AUTHZ-APPROVE-NEG-01
requirement_ids:
  - AUTHZ-APPROVE-01
  - AUTHZ-AUDIT-01
subject: reqA1
fixture: A-SUB-1-initial
request:
  method: POST
  path: /api/purchase-requests/A-SUB-1/approve
expected:
  decision: deny
  http_status: 403
  forbidden_response_fields:
    - internalReviewNote
  business_state:
    status: SUBMITTED
    approvedBy: null
  forbidden_business_events:
    - RequestApproved
  required_audit_event:
    action: approve
    outcome: denied
~~~

Ở đây 403 và các trường trạng thái là lựa chọn của hợp đồng ví dụ. Việc audit có cần chứa mã tài nguyên đầy đủ hay đã giảm chi tiết phải theo lược đồ và yêu cầu bảo vệ dữ liệu.

### 11.2. Tách dữ liệu chính sách khỏi mã gửi request

Harness nên dùng mã chung cho đăng nhập, tạo dữ liệu, gửi request và quan sát kết quả. Các trường hợp quyền đến từ ma trận được kiểm soát phiên bản và đã được xác nhận.

Không tính kết quả mong đợi bằng cùng nhánh triển khai mà đang cần đánh giá. Có thể dùng cùng bộ thuật ngữ và nguồn chính sách, nhưng kỳ vọng phải được người có trách nhiệm xem xét độc lập.

Đối với kiểm thử nhiều tham số:

1. Chuẩn bị fixture riêng cho từng ca có thể thay đổi trạng thái.
2. Xác nhận điều kiện trước.
3. Gửi yêu cầu bằng đúng danh tính.
4. Kiểm tra phản hồi.
5. Chờ và quan sát các tác động liên quan theo hợp đồng.
6. Ghi bằng chứng.
7. Dọn dữ liệu ngay cả khi ca thất bại.

Không chia sẻ một tài nguyên có thể bị duyệt hoặc xóa giữa các ca chạy song song nếu điều đó làm kết quả phụ thuộc thứ tự.

### 11.3. Sinh thêm tình huống theo thuộc tính bảo vệ

Một số thuộc tính giúp tạo nhiều ca thử:

- Thay tenant bằng một tenant ngoài phạm vi thì không được mở rộng dữ liệu nhìn thấy.
- Gỡ một quan hệ cấp quyền cần thiết thì hành động không còn được phép.
- Thêm tham số do client gửi không được tự cấp vai trò hoặc đổi chủ sở hữu.
- Một hành động bị từ chối không được tạo tác động nghiệp vụ bị cấm.
- Một người có thêm vai trò vẫn không được tự duyệt nếu quy tắc cấm này áp dụng.

Các thuộc tính chỉ đúng trong phạm vi chính sách đã nêu. Ví dụ, một quyền được ủy nhiệm hợp lệ có thể làm kết quả khác; bộ sinh cần giữ và mô tả các tiền điều kiện.

Dữ liệu sinh phải có các đối tượng và quan hệ hợp lệ. Sinh ngẫu nhiên toàn mã không tồn tại rồi nhận 404 không tạo bằng chứng có ích về cách ly tenant.

### 11.4. Cập nhật khi có chức năng mới

Khi thêm endpoint, trường dữ liệu, vai trò hoặc tác vụ:

- Xác định nó thuộc yêu cầu nào.
- Bổ sung vào danh mục đường truy cập.
- Cập nhật ca được phép và bị từ chối.
- Xem xét ảnh hưởng đến các tổ hợp quyền cũ.
- Chạy lại phần kiểm thử liên quan.

Không suy rằng endpoint mới được bảo vệ chỉ vì các endpoint cùng controller đã có kiểm thử.

## 12. Logging, phục hồi và các ranh giới bảo vệ liên quan

Authorization test có liên hệ trực tiếp với các nhóm yêu cầu bảo mật khác trong module.

### 12.1. Danh tính phải được ánh xạ đúng

Một token hợp lệ nhưng bị ánh xạ nhầm tenant hoặc vai trò có thể dẫn đến quyết định quyền sai. Ca tích hợp cần bao phủ đường từ danh tính được xác minh đến principal mà thành phần nghiệp vụ thực sự sử dụng.

Các thông tin tenant, owner hoặc role do client gửi phải được xử lý theo mức tin cậy của nguồn. Kiểm thử rằng chỉ thay header hoặc payload không tạo được quyền mà danh tính không có.

### 12.2. Dữ liệu và log đều có phạm vi quyền

Quyền xem đề nghị không tự bao gồm quyền xem mọi tệp, bản xuất hoặc log chứa nội dung đó.

Khi kiểm tra audit:

- Xác minh sự kiện được ghi theo đúng yêu cầu.
- Không ghi token, cookie phiên hoặc bí mật vào báo cáo và log.
- Đối chiếu chủ thể, hành động và kết quả.
- Không dùng audit như đường đọc nội dung mà vai trò đó không được xem.

Các mã tương quan giúp nối request với tác động và bằng chứng, nhưng không nên dùng quyền truy cập report hoặc log rộng hơn để che lấp dữ liệu bị trả trái quyền trên API.

### 12.3. Trạng thái quyền sau phục hồi cũng cần đánh giá

Nếu kịch bản phục hồi có thể khôi phục bản sao dữ liệu quyền cũ, cần yêu cầu xác định cách xử lý trước khi mở dịch vụ.

Ví dụ câu hỏi cần trả lời:

- Thành viên đã bị thu hồi có bị khôi phục quyền ngoài ý muốn không?
- Cấu hình cache hoặc dịch vụ danh tính có giữ phạm vi cũ không?
- Dữ liệu tài nguyên và dữ liệu quyền có nhất quán không?
- Các endpoint phục hồi có dùng đúng baseline phân quyền không?

Authorization test sau phục hồi phải dựa trên yêu cầu đã thống nhất, không mặc định rằng quyền trước và sau backup luôn giống nhau. Đây là điểm nối giữa kiểm thử phân quyền và yêu cầu RTO/RPO, tính toàn vẹn, cấu hình phục hồi.

## 13. Ghi kết quả và tạo bằng chứng có thể xem xét

### 13.1. Một bản ghi kết quả cần gì?

| Trường | Nội dung |
| --- | --- |
| Mã ca và yêu cầu | Cho biết bằng chứng đang kiểm chứng nghĩa vụ nào |
| Phiên bản chính sách | Tránh dùng ma trận quyền đã lỗi thời |
| Phần mềm và cấu hình | Bản phát hành, môi trường và đường triển khai |
| Danh tính thử | Vai trò, tenant, quan hệ cần thiết; không ghi token thật |
| Tài nguyên và trạng thái | Xác nhận fixture có ý nghĩa |
| Request đã giảm thông tin nhạy cảm | Method, đường dẫn, payload cần thiết |
| Kỳ vọng | Quyết định, dữ liệu, tác động và audit |
| Thực tế | Quan sát tại các điểm kiểm tra |
| Phạm vi và giới hạn | Đường nào đã thử, điều kiện nào chưa thực hiện |
| Hiện vật | Tham chiếu report, trace, dữ liệu trạng thái và sự kiện |
| Kết luận | Đạt, không đạt, bị chặn hoặc chưa chạy |

“Bị chặn” có thể do không tạo được danh tính hoặc môi trường không sẵn sàng. Nó không đồng nghĩa đã kiểm chứng từ chối đúng quyền.

### 13.2. Ví dụ phát hiện có giá trị

~~~text
Ca: AUTHZ-APPROVE-PROJECT-NEG-01
Yêu cầu: AUTHZ-APPROVE-01
Chủ thể: appA, Approver tenant A, chỉ được phân công P1
Tài nguyên: A-SUB-2, tenant A, dự án P2, trạng thái SUBMITTED

Kỳ vọng:
Không được duyệt; trạng thái giữ SUBMITTED;
không có RequestApproved.

Thực tế:
API trả kết quả thành công;
trạng thái thành APPROVED và có RequestApproved.

Tác động:
Người có vai trò Approver duyệt được đề nghị ngoài dự án được phân công.

Bằng chứng:
Request đã loại token, ảnh chụp trạng thái trước/sau và sự kiện
có cùng định danh tương quan trong môi trường đánh giá.

Giới hạn:
Phát hiện được xác nhận trên endpoint duyệt;
các đường duyệt khác cần kiểm tra tác động tương ứng.
~~~

Bản ghi chỉ ra điều kiện, kỳ vọng, thực tế và tác động. Không cần sao chép thông tin xác thực hoặc dữ liệu khách hàng để làm bằng chứng.

### 13.3. Báo cáo độ bao phủ đúng nghĩa

Nếu ma trận có 20 tình huống bắt buộc, đã chạy 18 và cả 18 đạt, cần báo còn hai tình huống chưa được đánh giá. Không ghi toàn bộ yêu cầu đã đạt chỉ vì các ca đã chạy đều xanh.

Độ bao phủ nên thể hiện theo các chiều quan trọng:

- Vai trò và quan hệ.
- Tenant và dự án.
- Hành động.
- Mức đối tượng và thuộc tính.
- Giao diện.
- Trạng thái và thay đổi quyền.
- Kết quả được phép và bị từ chối.

Số lượng ca không tự thể hiện mức bảo đảm. Nhiều ca lặp cùng một điều kiện không bù cho thiếu đường xuất dữ liệu hoặc thiếu trường hợp chéo tenant.

## 14. Tích hợp vào CI/CD và xử lý phát hiện

Có thể tổ chức:

- Kiểm tra chính sách và thành phần nghiệp vụ trong các thay đổi liên quan.
- Kiểm thử tích hợp API với fixture ổn định.
- Bộ hồi quy trọng yếu cho chéo tenant, cấp quyền và hành động đặc quyền.
- Kiểm tra tác vụ nền, thu hồi quyền và cấu hình triển khai ở môi trường phù hợp.
- Đánh giá thủ công khi có vai trò, quan hệ hoặc luồng mới khó mô tả đầy đủ bằng bộ tự động hiện có.

[OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) khuyến nghị có kiểm thử đơn vị và tích hợp cho logic phân quyền, đồng thời chỉ rõ chúng không thay thế hoàn toàn đánh giá bảo mật chuyên biệt.

Khi có ca thất bại:

1. Xác nhận fixture, chính sách kỳ vọng và điểm từ chối thực tế.
2. Nếu phát hiện đúng, ghi tác động và phạm vi bị ảnh hưởng.
3. Sửa cơ chế thực thi quyền hoặc làm rõ yêu cầu nếu kỳ vọng chưa thống nhất.
4. Kiểm tra lại ca tái hiện và các đường có cùng nguyên nhân.
5. Giữ kiểm thử hồi quy phù hợp để ngăn lỗi xuất hiện lại.

Tiêu chí chặn phát hành phải theo yêu cầu và cơ chế quản lý rủi ro của tổ chức. Không tự biến một tỷ lệ pass cao thành quyền bỏ qua ca chéo tenant hoặc hành động đặc quyền còn sai.

Nếu phải xử lý ngoại lệ, giữ rõ yêu cầu, phát hiện và người quyết định. Không sửa kỳ vọng sang “cho phép” chỉ để bộ kiểm thử đạt.

## 15. Tiêu chí tự rà soát bộ Authorization test

Đây là tiêu chí về thiết kế và bằng chứng của bộ kiểm thử, không phải chứng nhận hệ thống không còn lỗi phân quyền.

- [ ] Mỗi nhóm ca quan trọng có yêu cầu và chính sách kỳ vọng rõ ràng.
- [ ] Danh tính có token hoặc phiên hợp lệ trong ca đánh giá quyền của người đã đăng nhập.
- [ ] Có nhiều người dùng, tenant, quan hệ và vai trò cần thiết.
- [ ] Tài nguyên thực sự tồn tại, thuộc đúng phạm vi và trạng thái.
- [ ] Có ca được phép để tránh kết luận sai do hệ thống từ chối mọi thứ.
- [ ] Có ca quyền ngang, quyền dọc và chéo tenant.
- [ ] Có kiểm tra quyền trên đối tượng và các thuộc tính bị hạn chế.
- [ ] Có ca nhiều vai trò và quy tắc như không tự duyệt nếu áp dụng.
- [ ] Có đường danh sách, tìm kiếm, tải tệp, batch và tác vụ nền liên quan.
- [ ] Không chỉ kiểm tra mã HTTP; có quan sát dữ liệu và tác động cần thiết.
- [ ] Hành vi bị từ chối không phát sinh tác động nghiệp vụ bị cấm.
- [ ] Các yêu cầu audit liên quan được kiểm tra riêng.
- [ ] Quyền thay đổi, cache và các thời điểm xử lý được đánh giá theo hợp đồng.
- [ ] Lỗi token, CSRF, validation hoặc route không bị coi nhầm là bằng chứng phân quyền.
- [ ] Ca bất đồng bộ có ranh giới hoàn tất và giới hạn quan sát rõ.
- [ ] Fixture và trạng thái không bị lẫn giữa các ca chạy song song.
- [ ] Kỳ vọng không được tính bằng chính logic sản phẩm đang được thử.
- [ ] Report nêu các ca bị chặn, chưa chạy và giới hạn độ bao phủ.
- [ ] Bằng chứng gắn với phiên bản phần mềm, chính sách và cấu hình.
- [ ] Các thay đổi endpoint, vai trò hoặc dữ liệu kích hoạt cập nhật bộ kiểm thử.

## 16. Tài liệu tham khảo

- [OWASP WSTG v4.2 — Testing for Bypassing Authorization Schema](https://wstg.owasp.org/v4.2/4-Web_Application_Security_Testing/05-Authorization_Testing/02-Testing_for_Bypassing_Authorization_Schema/): kiểm tra vượt quyền ngang và dọc.
- [OWASP WSTG v4.2 — Testing for Insecure Direct Object References](https://wstg.owasp.org/v4.2/4-Web_Application_Security_Testing/05-Authorization_Testing/04-Testing_for_Insecure_Direct_Object_References/): kiểm tra tham chiếu đối tượng và dùng nhiều danh tính thử.
- [OWASP API1:2023 — Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/): phân quyền ở mức đối tượng.
- [OWASP API3:2023 — Broken Object Property Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/): giới hạn đọc và thay đổi thuộc tính.
- [OWASP API5:2023 — Broken Function Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa5-broken-function-level-authorization/): phân quyền chức năng.
- [OWASP Authorization Testing Automation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Testing_Automation.html): cách tổ chức tự động hóa dựa trên ma trận quyền.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): hướng dẫn thực thi và kiểm thử kiểm soát truy cập.
