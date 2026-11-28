# API security requirement

## 1. Yêu cầu bảo mật API là cam kết về hành vi

API là điểm mà một chủ thể yêu cầu hệ thống đọc dữ liệu, thay đổi trạng thái hoặc tiêu thụ tài nguyên. Chủ thể đó có thể là người dùng qua ứng dụng web, ứng dụng di động, dịch vụ nội bộ hoặc đối tác tích hợp. Giao diện không quyết định mức tin cậy: một lời gọi từ mạng nội bộ vẫn cần có danh tính và quyền phù hợp với tác vụ.

**API security requirement** là yêu cầu xác định API phải cho phép điều gì, từ chối điều gì, bảo vệ dữ liệu và tài nguyên ra sao, đồng thời tạo bằng chứng nào để kiểm chứng các quyết định đó. Yêu cầu cần gắn với một thao tác và rủi ro cụ thể, thay vì chỉ nêu tên công nghệ.

Ví dụ:

> API phải dùng HTTPS và JWT.

Đây mới là một phần lựa chọn thiết kế. Một token có thể hợp lệ nhưng người giữ token vẫn không được đọc báo cáo của tổ chức khác. Yêu cầu rõ hơn là:

> Khi một thành viên đọc báo cáo, dịch vụ phải xác thực danh tính, xác định tổ chức được phép hoạt động và kiểm tra quyền đọc đối với báo cáo đó. Việc thay đổi `reportId`, `projectId` hoặc header do client gửi không được làm mở rộng phạm vi dữ liệu trả về.

Yêu cầu sau nói được tài sản cần bảo vệ, điều kiện cho phép và hành vi cần kiểm thử. Nó cũng giúp phân công trách nhiệm giữa nhóm danh tính, gateway, dịch vụ nghiệp vụ và kiểm thử.

Trong module thiết kế yêu cầu bảo mật, mục tiêu không phải áp dụng cùng một bộ cấu hình cho mọi API. Mục tiêu là chuyển mô hình đe dọa thành hợp đồng có phạm vi, chủ sở hữu và bằng chứng nghiệm thu. Một API công khai xem dữ liệu thời tiết khác một API phê duyệt thanh toán; cả hai vẫn cần yêu cầu về tài nguyên, tính toàn vẹn và quản lý vòng đời phù hợp.

## 2. Xác định đối tượng trước khi chọn biện pháp

### 2.1. Bắt đầu từ thao tác, không chỉ từ URL

Một endpoint có thể có nhiều đường thực thi: gọi trực tiếp, gọi qua batch, tạo tác vụ nền hoặc lấy kết quả từ cache. Một chức năng cũng có thể xuất hiện trên nhiều phiên bản API. Nếu chỉ kiểm kê URL hiển thị trên tài liệu mới nhất, các đường cũ dễ bị bỏ sót.

Một mục kiểm kê API nên có:

| Thông tin | Câu hỏi cần trả lời |
| --- | --- |
| Thao tác và phiên bản | Đây là hành động nào, thuộc phiên bản nào? |
| Chủ sở hữu | Nhóm nào chịu trách nhiệm yêu cầu và vận hành? |
| Chủ thể gọi | Người dùng, dịch vụ hay đối tác nào được gọi? |
| Dữ liệu | Trường nào nhạy cảm, thuộc tổ chức hoặc người dùng nào? |
| Tác động | Chỉ đọc, thay đổi dữ liệu, chi tiền hay gọi dịch vụ trả phí? |
| Cơ chế xác thực | Danh tính được chứng minh và kiểm tra bằng cách nào? |
| Chính sách quyền | Quyền theo chức năng, đối tượng và trường dữ liệu là gì? |
| Phụ thuộc | Identity provider, cơ sở dữ liệu, hàng đợi và API ngoài nào tham gia? |
| Vòng đời | Đang hoạt động, sắp ngừng hay chỉ dành cho quản trị? |

Các nhóm rủi ro trong [OWASP API Security Top 10 phiên bản 2023](https://api-security.owasp.org/editions/2023/en/0x11-t10/) có thể dùng để rà soát câu hỏi còn thiếu, gồm quyền theo đối tượng, quyền theo thuộc tính, chức năng, tiêu thụ tài nguyên và quản lý danh mục API. Danh sách rủi ro không tự trở thành bộ tiêu chí nghiệm thu cho một hệ thống cụ thể.

### 2.2. Tình huống xuyên suốt: API báo cáo theo tổ chức

Giả sử một nền tảng quản lý báo cáo có nhiều tổ chức, gọi là tenant. Mỗi dự án thuộc đúng một tenant; mỗi báo cáo thuộc một dự án. Trong một tenant có các quyền nghiệp vụ:

- `REPORT_VIEWER`: đọc báo cáo được cấp quyền.
- `REPORT_EDITOR`: tạo và sửa báo cáo nháp theo phạm vi dự án.
- `REPORT_APPROVER`: phê duyệt báo cáo đã gửi trong dự án được phân công.
- `TENANT_ADMIN`: quản lý thành viên của tenant, không mặc nhiên được phê duyệt mọi báo cáo.

Một tập thao tác minh họa:

```text
GET   /v1/projects/{projectId}/reports/{reportId}
PATCH /v1/projects/{projectId}/reports/{reportId}
POST  /v1/projects/{projectId}/reports/{reportId}/approvals
POST  /v1/projects/{projectId}/report-exports
GET   /v1/report-exports/{jobId}
```

Các tên, quyền và giới hạn trong bài là lựa chọn của tình huống này, không phải tiêu chuẩn bắt buộc cho mọi sản phẩm. Đặc biệt, việc quản trị thành viên và phê duyệt báo cáo được tách để minh họa rằng tên vai trò có chữ “admin” không tự xác định mọi quyền.

Tài sản cần bảo vệ gồm nội dung báo cáo, ranh giới tenant, trạng thái phê duyệt, chi phí xuất báo cáo và lịch sử quyết định. Một yêu cầu chỉ nói “người dùng phải đăng nhập” không bao phủ đủ các tài sản đó.

## 3. Viết yêu cầu theo cấu trúc có thể kiểm chứng

Một yêu cầu đủ rõ thường có các thành phần:

```text
Mã yêu cầu + phạm vi áp dụng
Chủ thể + thao tác + tài nguyên
Điều kiện phải thỏa để cho phép
Hành vi khi thiếu điều kiện hoặc phụ thuộc lỗi
Dữ liệu và tác dụng phụ được phép
Tiêu chí nghiệm thu + chủ sở hữu
```

Ví dụ chưa đủ rõ:

> Hệ thống phải kiểm tra quyền người dùng khi gọi API.

Ví dụ có thể chuyển thành ca kiểm thử:

> Với API đọc báo cáo v1, dịch vụ chỉ trả báo cáo khi tenant của báo cáo khớp tenant đã được xác lập trong ngữ cảnh danh tính và chủ thể có quyền đọc trên dự án chứa báo cáo. Trường hợp không thuộc phạm vi được phép phải không trả nội dung, trường nhạy cảm hoặc thông tin về tenant khác.

Không nhất thiết nhồi mọi kiểm soát vào một câu dài. Có thể tách thành các yêu cầu về xác thực, quyền đối tượng và nội dung phản hồi, rồi liên kết chúng với cùng thao tác.

| Mã minh họa | Kết quả bắt buộc | Cách quan sát |
| --- | --- | --- |
| API-ID-01 | Request tới thao tác riêng tư phải có danh tính hợp lệ theo profile đã công bố | Thiếu credential, credential sai và credential hợp lệ |
| API-AZ-01 | Quyền phải áp dụng đúng tenant, dự án và báo cáo | Đổi từng định danh trong path và dữ liệu đầu vào |
| API-AZ-02 | Chỉ chủ thể có quyền phê duyệt được gọi thao tác phê duyệt | Ma trận vai trò, phạm vi và trạng thái |
| API-DATA-01 | Client không được ghi trường thuộc quyền quản lý của dịch vụ | Gửi thêm `tenantId`, `ownerId`, `approvalStatus` |
| API-COST-01 | Xuất báo cáo không vượt giới hạn tác vụ và dung lượng đã công bố | Ca tại biên và ca gọi đồng thời |
| API-AUD-01 | Quyết định nhạy cảm phải có audit với trường đã quy định | Đối chiếu request, kết quả và sự kiện audit |
| API-FAIL-01 | Lỗi xác định quyền không được chuyển thành truy cập cho phép | Làm lỗi phụ thuộc và quan sát tác dụng phụ |

Một yêu cầu ghi “nhanh”, “an toàn” hoặc “đủ log” vẫn còn quyết định chưa chốt. Cần thay bằng điều kiện và ngưỡng có đơn vị, hoặc ghi rõ quyết định đang chờ, người chịu trách nhiệm và hạn xử lý. Không để một giá trị chưa được thống nhất xuất hiện như tiêu chuẩn đã được phê duyệt.

## 4. Danh tính: API biết ai đang yêu cầu điều gì?

### 4.1. Phân biệt người dùng, ứng dụng và dịch vụ

Một request có thể liên quan đến cả người dùng và ứng dụng đại diện người dùng. API cần biết chính sách áp dụng cho chủ thể nào. Một service account phục vụ đồng bộ dữ liệu không nên được coi là một người dùng có quyền quản trị toàn bộ tenant.

Yêu cầu về danh tính cần xác định:

- Loại chủ thể được hỗ trợ và thao tác nào cho phép truy cập ẩn danh.
- Nguồn danh tính được tin cậy, cơ chế kiểm chứng và phạm vi credential.
- Cách xác định tenant hoặc tập tenant mà chủ thể được hoạt động.
- Thời hạn credential, xoay vòng và hành vi sau khóa tài khoản hoặc thu hồi quyền.
- Hành vi khi không kiểm chứng được danh tính hoặc cấu hình xác thực bị lỗi.

Không nhận `X-User-Id`, `X-Tenant-Id` hoặc vai trò trong body như bằng chứng danh tính chỉ vì header hoặc trường đó có tên thuận tiện. Nếu gateway truyền ngữ cảnh đã xác thực, cần có ranh giới tin cậy: gateway loại bỏ giá trị client tự gửi, bảo vệ đường truyền tới backend và backend chỉ nhận ngữ cảnh từ nguồn được phép.

Khi người dùng được chọn tenant trong số nhiều tenant đã tham gia, giá trị lựa chọn là đầu vào cần kiểm tra quan hệ thành viên. Nó không tự trở thành tenant được tin cậy. Phải nêu rõ nơi xác lập ngữ cảnh này để tránh mỗi endpoint tự diễn giải khác nhau.

### 4.2. Đặc tả profile credential thay vì chỉ ghi “dùng token”

Nếu chọn JWT access token, yêu cầu phải nói rõ issuer, audience, thuật toán được phép, loại token, thời hạn và tập claim cần kiểm tra theo profile. Kiểm chứng chữ ký không thay thế kiểm tra token có dành cho API này hay không. ID token dành cho đăng nhập cũng không được mặc định là access token được chấp nhận tại mọi resource server. Các vấn đề về kiểm tra thuật toán, issuer và audience được thảo luận trong [RFC 8725, JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html).

Nếu chọn token opaque, API cần cơ chế kiểm chứng hoặc tra cứu phù hợp với thiết kế đó. Không áp đặt bước decode JWT cho một credential không có cấu trúc JWT. Với xác thực bằng chứng chỉ hoặc cơ chế workload identity, yêu cầu cần liên kết danh tính kỹ thuật với quyền nghiệp vụ cụ thể.

Credential không nên nằm trong query string vì URL có thể đi qua lịch sử, access log và nhiều lớp trung gian. Cần bảo vệ kênh truyền và xác định cách lưu secret ở phía client; khuyến nghị về HTTPS và xử lý credential được trình bày trong [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html).

### 4.3. Quyền vừa bị thu hồi có hiệu lực khi nào?

Yêu cầu “thu hồi quyền ngay” chưa đủ nếu dịch vụ chấp nhận token hoặc kết quả phân quyền từ cache. Cần xác định thời gian có thể quan sát việc thu hồi, phạm vi tác vụ đang chạy và cách xử lý khi không cập nhật được trạng thái.

Ví dụ đặc tả cho tình huống báo cáo:

> Sau khi quyền phê duyệt bị thu hồi, mọi quyết định phê duyệt mới phải phản ánh việc thu hồi trong thời hạn tối đa đã thống nhất. Cơ chế cache không được giữ quyền vượt thời hạn đó. Tác vụ đã vào giai đoạn commit được xử lý theo quy tắc giao dịch và ghi audit đã công bố.

Con số cụ thể phải phù hợp rủi ro và khả năng đồng bộ thực tế. Không ghi một thời hạn ngắn hơn điều kiến trúc có thể chứng minh chỉ để yêu cầu trông nghiêm ngặt.

## 5. Phân quyền phải bao phủ chức năng, đối tượng và thuộc tính

### 5.1. Có quyền gọi chức năng chưa chắc có quyền với đối tượng

Kiểm tra `REPORT_VIEWER` chỉ trả lời một phần câu hỏi. Người có quyền đọc ở dự án P1 không mặc nhiên đọc được báo cáo của P2, kể cả hai dự án cùng tenant. Cần xác định đầy đủ:

```text
Chủ thể nào?
Thao tác nào?
Tenant nào?
Dự án và báo cáo nào?
Trạng thái hoặc quan hệ nghiệp vụ nào?
Trường dữ liệu nào được đọc hoặc sửa?
```

Một ma trận minh họa cho nghiệp vụ:

| Chủ thể | Báo cáo trong dự án được cấp quyền | Báo cáo ngoài dự án được cấp quyền | Báo cáo tenant khác | Phê duyệt |
| --- | --- | --- | --- | --- |
| Viewer | Đọc tập trường được phép | Từ chối | Từ chối | Từ chối |
| Editor | Đọc; sửa phần được phép khi còn nháp | Từ chối | Từ chối | Từ chối nếu không có quyền approver |
| Approver được phân công | Đọc theo phạm vi được cấp | Từ chối | Từ chối | Cho phép khi thỏa trạng thái và quy tắc phân tách trách nhiệm |
| Tenant admin | Theo quyền dữ liệu được cấp riêng | Theo quyền dữ liệu được cấp riêng | Từ chối | Không tự động được phép |
| Service account xuất báo cáo | Chỉ tập dữ liệu theo grant của dịch vụ | Từ chối | Từ chối | Từ chối |

Ma trận không thay thế chính sách chi tiết, nhưng giúp phát hiện những ô chưa có quyết định. Một ô trống không nên được hiểu thành cho phép. Nguyên tắc từ chối mặc định và kiểm tra quyền ở mỗi request được giải thích trong [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

### 5.2. Định danh khó đoán không phải là quyền truy cập

UUID hoặc định danh ngẫu nhiên có thể làm việc dò đoán khó hơn, nhưng người dùng vẫn có thể biết định danh từ một liên kết, log hoặc thông điệp được chia sẻ. API phải kiểm tra quyền khi định danh đã bị biết, không chỉ khi kẻ tấn công cần đoán nó.

Đối với path có cả `projectId` và `reportId`, dịch vụ phải xác minh quan hệ giữa hai đối tượng. Không kiểm tra quyền dự án P1 rồi đọc một báo cáo của P2 chỉ vì `reportId` tồn tại. Một hướng triển khai là truy vấn tài nguyên trong phạm vi tenant và dự án được phép, sau đó áp dụng chính sách nghiệp vụ còn lại.

Các thao tác liệt kê, tìm kiếm, thống kê và batch cũng phải giữ cùng phạm vi. Chặn đọc một báo cáo riêng lẻ nhưng để endpoint tìm kiếm trả tên và nội dung của nó vẫn là lộ dữ liệu. Với batch, hợp đồng cần chọn rõ từ chối toàn bộ hay xử lý từng phần; kết quả lỗi từng phần cũng không được tiết lộ dữ liệu ngoài quyền.

### 5.3. Quyền đọc và quyền ghi từng trường

Giả sử API sửa báo cáo chỉ cho phép `title` và `description`. Client gửi thêm:

```json
{
  "title": "Báo cáo quý",
  "description": "Nội dung đề xuất",
  "tenantId": "tenant-khac",
  "ownerId": "nguoi-khac",
  "approvalStatus": "APPROVED"
}
```

Trong hợp đồng minh họa, các trường ngoài danh sách cho phép phải gây lỗi validation và không có cập nhật nào được commit. Nếu một sản phẩm chọn bỏ qua trường không biết vì lý do tương thích, phải ghi rõ và chứng minh chúng không bao giờ được bind vào trường nhạy cảm. Không để hành vi phụ thuộc ngầm vào mapper hoặc entity ORM.

Phản hồi cũng phải được thiết kế theo trường. Việc client không hiển thị `internalRiskScore` không có nghĩa trường đó không được gửi qua mạng. API cần response model phù hợp thay vì tuần tự hóa nguyên đối tượng lưu trữ rồi trông chờ giao diện tự ẩn dữ liệu.

## 6. Trạng thái nghiệp vụ là một phần của yêu cầu API

Một request có danh tính và quyền đúng vẫn có thể không được thực hiện nếu trạng thái nghiệp vụ không phù hợp. Ví dụ, chỉ báo cáo `SUBMITTED` mới được phê duyệt; người tạo không được tự phê duyệt nếu có yêu cầu phân tách trách nhiệm.

```text
DRAFT --gửi duyệt--> SUBMITTED --phê duyệt--> APPROVED
                              |
                              +--từ chối--> REJECTED
```

Đặc tả cần quy định ai được thực hiện mỗi chuyển trạng thái, dữ liệu nào được phép thay đổi và điều kiện nào phải còn đúng tại thời điểm commit. Không để client sửa trực tiếp `approvalStatus` thông qua API cập nhật văn bản để đi vòng qua thao tác phê duyệt.

Một yêu cầu minh họa:

> Thao tác phê duyệt chỉ được commit khi chủ thể có quyền phê duyệt trên dự án, không phải người tạo báo cáo, báo cáo đang ở trạng thái `SUBMITTED` và phiên bản dữ liệu vẫn khớp điều kiện cạnh tranh đã công bố. Hai request đồng thời không được tạo hai lần chuyển trạng thái hoặc hai hiệu ứng nghiệp vụ tương đương.

Kiểm tra trạng thái rồi cập nhật trong hai bước không có bảo vệ cạnh tranh có thể không đáp ứng yêu cầu. Thiết kế có thể dùng transaction, cập nhật có điều kiện, version hoặc cơ chế khác, nhưng phải chứng minh được tính chất tại biên commit. Việc kiểm tra quyền có thể còn phụ thuộc vào cơ chế đồng bộ chính sách; tính nguyên tử dữ liệu không tự giải quyết mọi trường hợp thu hồi quyền đồng thời.

Đối với tác vụ nền, request tạo job, worker xử lý và request tải kết quả là các điểm kiểm soát riêng. Cần nêu rõ quyền được đánh giá lại khi nào, job chạy dưới danh tính nào và kết quả có được tải sau khi người yêu cầu mất quyền hay không. Chỉ bảo vệ endpoint tạo job chưa đủ để bảo vệ artifact cuối cùng.

## 7. Hợp đồng dữ liệu đầu vào và đầu ra

### 7.1. Validation phải bao phủ hình dạng và ngữ nghĩa

Yêu cầu nên chỉ rõ method, media type, schema, trường bắt buộc, giá trị cho phép và giới hạn. Với một API JSON, các lựa chọn minh họa có thể là:

- Chỉ nhận `application/json` cho thao tác có body theo hợp đồng.
- Từ chối body vượt kích thước cho phép trước khi xử lý nghiệp vụ tốn kém.
- Giới hạn độ dài chuỗi, số phần tử mảng và độ sâu cấu trúc.
- Chỉ chấp nhận những trường được phép ghi; xử lý trường không biết theo chính sách đã chọn.
- Từ chối khóa trùng nếu hợp đồng yêu cầu một giá trị duy nhất và các lớp parse có thể diễn giải khác nhau.
- Kiểm tra quan hệ nghiệp vụ, chẳng hạn kỳ báo cáo thuộc dự án và ngày kết thúc không trước ngày bắt đầu.

Giới hạn ở gateway và giới hạn trong ứng dụng cần tương thích. Nếu tầng trước chấp nhận một dạng request mà tầng sau hiểu khác, yêu cầu validation phải làm rõ cách biểu diễn được hỗ trợ thay vì để hai lớp tự suy đoán.

Validation không thay thế bảo vệ tại nơi sử dụng dữ liệu. Dữ liệu đã qua schema vẫn cần query có tham số khi truy vấn cơ sở dữ liệu, encoding theo ngữ cảnh khi hiển thị và kiểm soát đích khi được dùng để gọi URL. Cần liên kết các yêu cầu đó với đúng bước sử dụng, không gộp mọi thứ thành “lọc ký tự nguy hiểm”.

### 7.2. Phản hồi, cache và phân trang

API đọc báo cáo phải trả tập trường đúng quyền và giữ phạm vi tenant qua cache. Một cache dùng riêng `reportId` trong khi quyền phụ thuộc tenant, chủ thể hoặc tập trường có thể trả nhầm dữ liệu. Thiết kế cần xác định cache có dùng chung được không, thành phần khóa và điều kiện vô hiệu hóa khi quyền thay đổi.

Với dữ liệu nhạy cảm trong tình huống này, hợp đồng có thể chọn không cho lưu ở cache dùng chung và đặt chính sách cache phù hợp tại biên HTTP. Đây là quyết định theo dữ liệu và hạ tầng; không thay việc phân tích cache bằng một header được chép giống nhau vào mọi endpoint.

Phân trang cần giới hạn kích thước và giữ phạm vi truy vấn. Cursor không được coi là quyền truy cập. Nếu cursor mang tenant, bộ lọc hoặc vị trí dữ liệu, phải kiểm tra tính hợp lệ và đối chiếu với danh tính của request hiện tại. Không để đổi cursor trở thành cách bỏ qua điều kiện lọc tenant.

## 8. Tài nguyên, lạm dụng nghiệp vụ và retry

### 8.1. Rate limit không phải giới hạn tài nguyên duy nhất

Một request xuất báo cáo có thể đọc hàng triệu bản ghi hoặc gọi dịch vụ trả phí. Hạn chế số request mỗi phút không tự chặn một request quá đắt, tác vụ chạy quá lâu hoặc hàng nghìn job đã nằm trong queue.

Một profile giới hạn minh họa cho thao tác xuất báo cáo:

| Đại lượng | Lựa chọn của ví dụ | Điều cần xác minh |
| --- | --- | --- |
| Body sau giải nén | Tối đa 64 KiB | Áp dụng tại nơi thực sự đọc nội dung sau giải nén |
| Số báo cáo được chọn | Tối đa 500 định danh | Không mở rộng qua trường lồng hoặc batch phụ |
| Job chưa kết thúc | Tối đa 2 trên mỗi tenant | Tính cả job chờ và đang chạy trên mọi instance |
| Tốc độ tạo job | Tối đa 5 lần được chấp nhận trong cửa sổ trượt 60 giây trên mỗi tenant | Request bị từ chối không tạo job mới |
| Artifact | Tối đa 20 MiB | Không công bố artifact thiếu khi chạm giới hạn |

Các con số trên phục vụ ví dụ, chưa phải cấu hình sản xuất. Chúng phải được chọn từ nhu cầu nghiệp vụ, kiểm thử năng lực, chi phí và thỏa thuận với bên sử dụng. Một cửa sổ trượt cũng khác một bộ đếm chia phút cố định; tên thuật toán và hành vi ở biên cần thống nhất nếu tiêu chí nghiệm thu phụ thuộc chúng.

Với giới hạn trên toàn tenant, mở rộng thêm instance không được nhân hạn mức ngoài ý muốn. Đặc tả phải nói hạn mức có tính toàn cục hay từng instance và sai số được chấp nhận. Giới hạn theo IP có thể bổ sung tại biên nhưng không thay thế hạn mức chủ thể hoặc tenant, vì nhiều người dùng có thể dùng chung IP và một chủ thể có thể đổi IP.

Khi áp dụng `429 Too Many Requests`, hợp đồng cần mô tả cách client biết khi nào thử lại. `Retry-After` có thể được dùng nếu hệ thống tính được thời gian phù hợp; không được giả định mọi loại quota đều tự có một thời điểm phục hồi. Mã 429 và khả năng dùng header này được quy định trong [RFC 6585](https://www.rfc-editor.org/rfc/rfc6585.html).

### 8.2. Hạn chế lạm dụng một luồng hợp lệ

Người dùng có quyền vẫn có thể gọi một thao tác quá nhiều lần để làm cạn tài nguyên hoặc gây thiệt hại nghiệp vụ. Ví dụ, gửi lại yêu cầu phê duyệt, tạo nhiều bản xuất hoặc kích hoạt thông báo hàng loạt. Cần xác định chi phí và tác động của cả luồng, không chỉ request đơn lẻ.

Yêu cầu có thể bao gồm hạn mức theo tenant, giới hạn đồng thời, ngân sách cho dịch vụ ngoài, điều kiện chống tự động hóa hoặc bước xác nhận tăng cường cho thao tác rủi ro cao. Mỗi kiểm soát phải gắn với vấn đề thực tế; không bắt mọi thao tác đọc dữ liệu công khai thực hiện cùng quy trình như một lệnh chi tiền.

### 8.3. Idempotency phải có phạm vi và thời hạn

Nếu API tạo job nhận `Idempotency-Key`, hợp đồng nên xác định:

- Khóa được ràng buộc với chủ thể hoặc client, tenant và thao tác nào.
- Cách nhận biết cùng nội dung yêu cầu và cách xử lý khóa trùng với nội dung khác.
- Thời gian giữ kết quả, trạng thái đang xử lý và hành vi sau khi hết hạn.
- Cách xử lý hai request cùng khóa đến đồng thời hoặc tới hai instance khác nhau.
- Việc kiểm tra quyền hiện tại trước khi trả lại một kết quả đã lưu.

Ví dụ, cùng tenant và cùng thao tác, khóa K với cùng nội dung được phép trả lại định danh job trước đó; khóa K với nội dung khác bị từ chối theo mã lỗi đã công bố. Tenant khác không được nhận lại kết quả của tenant đầu tiên dù gửi cùng chuỗi K.

Không dùng idempotency như lời hứa “exactly once” không có giới hạn. Nếu job gọi dịch vụ ngoài rồi tiến trình dừng trước khi ghi nhận kết quả, cần có cơ chế phối hợp, đối soát hoặc chống trùng phù hợp. Yêu cầu nên mô tả hiệu ứng nghiệp vụ và cách phục hồi thay vì chỉ yêu cầu thêm một header.

## 9. Ranh giới gateway, dịch vụ và hệ thống ngoài

### 9.1. Gateway không biết mọi chính sách nghiệp vụ

Gateway có thể xử lý TLS, kiểm tra credential, giới hạn request và chuẩn hóa đường vào. Dịch vụ nghiệp vụ thường biết báo cáo thuộc dự án nào, ai là người tạo và trạng thái nào cho phép phê duyệt. Yêu cầu phải đặt trách nhiệm kiểm tra ở nơi có đủ ngữ cảnh.

```text
Client
  |
  v
Gateway: kênh truyền, credential, giới hạn tại biên
  |
  v
Dịch vụ: tenant, đối tượng, trường dữ liệu, trạng thái nghiệp vụ
  |
  v
Kho dữ liệu / hàng đợi / API đối tác
```

Không bắt buộc mỗi tầng thực hiện lại mọi bước theo cùng cách. Điều cần chứng minh là không có đường tới chức năng nghiệp vụ bỏ qua kiểm soát bắt buộc. Nếu backend chỉ được gọi qua gateway, cần giới hạn kết nối và xác thực nguồn gọi tương ứng. Nếu backend còn được các dịch vụ khác gọi trực tiếp, các đường đó cũng phải có chính sách danh tính và quyền rõ ràng.

### 9.2. Dữ liệu đối tác vẫn phải được kiểm tra

Phản hồi từ API đối tác có thể sai schema, quá lớn, chậm hoặc chứa URL không phù hợp. Không coi dữ liệu đó là đáng tin chỉ vì kết nối có TLS hoặc đối tác đã có hợp đồng thương mại.

Yêu cầu tích hợp cần nêu giới hạn thời gian, kích thước phản hồi, cách kiểm tra định dạng, xử lý mã lỗi, số lần retry và hành vi khi kết quả không xác định. Nếu dịch vụ tải URL do client cung cấp, cần chính sách đích được phép, chuyển hướng và kết nối mạng; đây là một yêu cầu kiểm soát outbound riêng, không được thay bằng validation chuỗi URL đơn giản.

### 9.3. CORS và CSRF phải theo loại client

CORS điều khiển một số hành vi truy cập chéo origin của trình duyệt, không cấp quyền truy cập nghiệp vụ cho mọi loại client. Một lời gọi bằng công cụ HTTP hoặc dịch vụ nền không bị bảo vệ chỉ vì origin của nó không nằm trong cấu hình CORS.

Nếu API dùng cookie mà trình duyệt tự gửi, yêu cầu cho thao tác thay đổi trạng thái cần xem xét CSRF theo kiến trúc xác thực đó. Nếu dùng credential trong header do ứng dụng chủ động gắn, mô hình tấn công và cách bảo vệ có khác biệt; không suy ra mọi rủi ro phía trình duyệt đã biến mất. Cần ghi rõ loại client và cơ chế mang credential trước khi chọn yêu cầu.

## 10. Lỗi, audit và hành vi khi phụ thuộc thất bại

### 10.1. Mã lỗi là một phần của hợp đồng

Một lựa chọn minh họa cho API báo cáo:

| Trường hợp | Phản hồi theo hợp đồng |
| --- | --- |
| Thiếu hoặc sai credential | `401` và challenge xác thực phù hợp |
| Danh tính hợp lệ nhưng thiếu quyền chức năng | `403`, không có tác dụng phụ |
| Báo cáo không có trong phạm vi được phép | `404` theo chính sách che giấu tồn tại |
| Request không đúng cấu trúc hợp đồng | `400`, mã lỗi ổn định cho client |
| Media type không được hỗ trợ | `415` |
| Nội dung quá lớn | `413` |
| Trạng thái nghiệp vụ xung đột | `409` |
| Vượt hạn mức request được định nghĩa | `429` theo chính sách hạn mức |
| Không thể quyết định quyền vì phụ thuộc bắt buộc lỗi | Lỗi dịch vụ tạm thời đã đặc tả; không thực hiện thao tác |

Ý nghĩa 401, 403 và khả năng dùng 404 để không tiết lộ sự tồn tại của tài nguyên được nêu trong [RFC 9110, mục Client Error 4xx](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5). Phản hồi 401 cần có `WWW-Authenticate` với challenge áp dụng cho tài nguyên. Lựa chọn cụ thể về mã validation và cấu trúc lỗi còn cần thống nhất trong hợp đồng API.

Nếu quyết định che giấu sự tồn tại, nội dung lỗi, header và hành vi cache cũng phải phù hợp. Không trả `404` nhưng ghi “báo cáo thuộc tenant B” trong message. Cũng không hứa chống mọi suy luận qua thời gian chỉ nhờ đổi status code; nếu đó là yêu cầu, cần mô hình và phép đo riêng.

Một body lỗi có thể chỉ gồm mã ổn định và định danh tương quan:

```json
{
  "code": "REPORT_NOT_AVAILABLE",
  "message": "Không thể truy cập báo cáo theo yêu cầu.",
  "requestId": "req-example-001"
}
```

Không trả stack trace, câu truy vấn, token, secret hoặc cấu hình nội bộ cho client. Mã lỗi công khai và lý do chi tiết trong audit có thể khác nhau theo quyền truy cập của từng đối tượng.

### 10.2. Audit phải chứng minh điều gì đã xảy ra

Với thao tác phê duyệt, audit cần ghi được ai yêu cầu, tenant nào, thao tác nào, tài nguyên nào, quyết định gì, thời điểm nào và định danh tương quan. Có thể bổ sung phiên bản chính sách, trạng thái trước/sau và nguồn xác thực theo nhu cầu truy vết.

Ví dụ sự kiện minh họa:

```json
{
  "eventType": "REPORT_APPROVAL_DENIED",
  "actorId": "user-A",
  "tenantId": "tenant-A",
  "projectId": "project-A",
  "reportId": "report-A",
  "decision": "DENY",
  "reasonCode": "SELF_APPROVAL_NOT_ALLOWED",
  "requestId": "req-example-001"
}
```

Trong ví dụ, các định danh chỉ là dữ liệu giả; ở sản phẩm thật cần phân loại và bảo vệ log tương ứng. Không log toàn bộ authorization header hay body nhạy cảm. Audit cũng cần giới hạn quyền đọc, chống sửa trái phép và chính sách lưu giữ phù hợp.

Yêu cầu “log mọi request” có thể tạo chi phí hoặc rủi ro dữ liệu lớn. Nên phân biệt audit nghiệp vụ bắt buộc, sự kiện an ninh và telemetry vận hành; xác định trường nào không được sampling và trường nào có thể tổng hợp. Nếu phát hiện dò tài nguyên hoặc tăng đột biến lỗi quyền là mục tiêu, cần mô tả điều kiện cảnh báo và nơi tiếp nhận, không chỉ tạo thêm dòng log.

### 10.3. Fail-closed cần đi cùng hành vi phục hồi

Nếu không xác minh được quyền bắt buộc, API không được tự chuyển sang cho phép. Tuy nhiên, yêu cầu cần nói thêm client nhận gì, có được retry không, hệ thống có ghi nhận sự kiện không và dữ liệu có bị thay đổi một phần không.

Trường hợp audit không sẵn sàng cũng cần quyết định riêng. Với thao tác nhạy cảm, có thể yêu cầu ghi bản ghi audit hoặc outbox bền vững cùng transaction trước khi trả thành công. Với telemetry không bắt buộc, thiết kế có thể chọn cách xử lý khác. Không mặc định một lần timeout gửi log đồng nghĩa phải dừng toàn bộ API, và cũng không mặc định bỏ mất bằng chứng phê duyệt là chấp nhận được.

## 11. Một hồ sơ yêu cầu hoàn chỉnh cho thao tác phê duyệt

Đoạn YAML sau là nội dung minh họa cách ghi yêu cầu, không phải tệp cấu hình của module hay cấu hình thực thi tự động:

```yaml
id: API-APPROVE-001
title: Chỉ phê duyệt báo cáo trong phạm vi được cấp
scope:
  method: POST
  path: /v1/projects/{projectId}/reports/{reportId}/approvals
asset:
  - tenant_isolation
  - approval_integrity
preconditions:
  - authenticated_subject_is_valid
  - active_tenant_context_is_verified
allow_when:
  - report_belongs_to_active_tenant
  - report_belongs_to_requested_project
  - subject_has_current_project_approval_permission
  - subject_is_not_report_creator
  - report_status_is_SUBMITTED
effect:
  - one_committed_transition_to_APPROVED
  - durable_audit_record_for_committed_transition
deny_effect:
  - no_report_state_change
  - no_approval_notification
  - no_disclosure_of_other_tenant_data
failure_policy:
  authorization_dependency_unavailable: no_approval_commit
verification:
  - cross_tenant_request
  - mismatched_project_and_report
  - wrong_function_permission
  - self_approval
  - invalid_report_state
  - concurrent_approval_requests
owner: report_service_team
```

Hồ sơ này vẫn cần liên kết tới các quyết định chung về profile token, thời gian cập nhật quyền, mã lỗi, audit và xử lý cạnh tranh. Việc tham chiếu một yêu cầu chung giúp tránh sao chép những thông số có thể thay đổi vào mọi endpoint.

Một bản yêu cầu chỉ được xem là sẵn sàng triển khai khi các tham chiếu đó đã có chủ sở hữu và giá trị chốt. Nếu một lựa chọn còn chưa rõ, phải ghi thành vấn đề mở thay vì giả định implementation sẽ tự quyết định giống nhau ở mọi dịch vụ.

## 12. Kế hoạch nghiệm thu: kiểm tra cả điều được phép và bị cấm

Các ca dưới đây là kế hoạch kiểm chứng cho tình huống minh họa, không phải kết quả kiểm thử của một ứng dụng đã triển khai.

| Ca | Chuẩn bị | Kết quả quan sát bắt buộc |
| --- | --- | --- |
| Hợp lệ | Approver được phân công, báo cáo `SUBMITTED`, không tự tạo | Một chuyển trạng thái hợp lệ và audit tương ứng |
| Thiếu danh tính | Không gửi credential | Không thực hiện nghiệp vụ; lỗi theo profile xác thực |
| Sai đối tượng nhận token | Token không dành cho API này | Từ chối trước khi sử dụng quyền nghiệp vụ |
| Vượt tenant | Chủ thể tenant A dùng report của tenant B | Không dữ liệu B, không chuyển trạng thái B |
| Lệch dự án | Path dự án P1 nhưng report thuộc P2 | Không dùng quyền P1 để thao tác report P2 |
| Sai chức năng | Editor không có quyền approver | Không phê duyệt dù được sửa báo cáo nháp |
| Tự phê duyệt | Người tạo đồng thời có vai trò approver | Từ chối theo quy tắc phân tách trách nhiệm |
| Ghi trường cấm | PATCH kèm `approvalStatus` hoặc `tenantId` | Lỗi theo hợp đồng; không thay đổi trường nhạy cảm |
| Trạng thái không phù hợp | Report đang `DRAFT`, `APPROVED` hoặc `REJECTED` | Không chuyển trạng thái ngoài hợp đồng |
| Đồng thời | Hai request phê duyệt cùng thời điểm | Không có hai hiệu ứng phê duyệt hoặc thông báo trùng ngoài hợp đồng |
| Quyền bị thu hồi | Thay đổi grant và gọi trong các mốc thời gian đã đặc tả | Hành vi khớp giới hạn độ trễ cập nhật quyền |
| Phụ thuộc lỗi | Không thể có quyết định quyền đáng tin cậy | Không fallback thành allow; không cập nhật một phần |
| Vượt tài nguyên | Tạo job vượt giới hạn hoặc gửi nội dung quá lớn | Từ chối theo hợp đồng; không tạo thêm công việc ngoài hạn mức |
| Job và artifact | Người khác hoặc tenant khác dùng `jobId` | Không đọc trạng thái nhạy cảm hoặc tải kết quả trái quyền |
| Cache | Hai chủ thể có tập trường được phép khác nhau | Không dùng lại phản hồi làm lộ trường ngoài quyền |

### 12.1. Mã lỗi đúng chưa đủ chứng minh từ chối an toàn

Một response `403` có thể xuất hiện sau khi dữ liệu đã cập nhật hoặc thông báo đã gửi. Vì vậy, ca âm cần kiểm tra cả trạng thái lưu trữ, hàng đợi, tác dụng phụ ngoài hệ thống và phản hồi, tùy thao tác.

Với yêu cầu phê duyệt, bằng chứng nên đối chiếu trạng thái báo cáo, số bản ghi phê duyệt, sự kiện thông báo và audit. Với yêu cầu chỉ đọc, cần kiểm tra response và khả năng dữ liệu ngoài quyền xuất hiện qua cache, tổng số bản ghi hoặc metadata.

Ca dương cũng cần thiết. Một hệ thống từ chối mọi request có thể vượt qua nhiều ca âm nhưng không đáp ứng chức năng. Ma trận nghiệm thu phải có đủ chủ thể được phép, không được phép và các điều kiện biên quan trọng.

### 12.2. Kiểm thử theo ranh giới và phiên bản

Nên đối chiếu cùng yêu cầu qua các đường vào thực sự tồn tại: gateway công khai, tích hợp dịch vụ, batch và tác vụ nền. Không tạo quyền truy cập mới chỉ để kiểm thử, nhưng phải biết kiến trúc có những đường nào cần được bao phủ.

Khi có v1 và v2 cùng hoạt động, mỗi phiên bản phải liên kết với chính sách áp dụng và bằng chứng riêng. Một bản vá ở endpoint mới không chứng minh endpoint cũ đã được bảo vệ. Các tài liệu và route không dùng nữa cần có quy trình ngừng hoạt động, thay vì chỉ bị xóa khỏi trang tài liệu.

### 12.3. Phân biệt đo lường và bằng chứng bao phủ

Có thể theo dõi tỷ lệ thao tác đã có chủ sở hữu, tỷ lệ yêu cầu đã liên kết ca nghiệm thu và số endpoint đang hoạt động không có profile bảo mật. Các chỉ số này hỗ trợ quản lý tiến độ, nhưng chất lượng phụ thuộc cách xác định danh mục.

“100% test pass” không chứng minh mọi tài nguyên và đường vào đều được kiểm tra nếu danh mục còn thiếu. Vì vậy, cần giữ liên kết từ tài sản và rủi ro đến thao tác, yêu cầu, thiết kế thực thi và bằng chứng. Một phát hiện mới về đường vào phải cập nhật lại chuỗi liên kết này.

## 13. Đưa yêu cầu API vào vòng đời phát triển

Trước triển khai, nhóm cần chốt phạm vi, ma trận quyền, profile danh tính, schema, giới hạn và hành vi lỗi. Trong thiết kế, xác định điểm thực thi ở gateway, dịch vụ, dữ liệu và worker nền; tránh để một yêu cầu quan trọng chỉ tồn tại trong tài liệu mà không có thành phần chịu trách nhiệm.

Khi thay đổi API, cần đánh giá tác động đến bảo mật ngay cả khi thay đổi được gọi là “chỉ thêm trường”. Một trường mới có thể làm lộ dữ liệu, tạo khả năng mass assignment hoặc thay đổi chi phí truy vấn. Thêm bộ lọc tìm kiếm, chế độ export hoặc quan hệ lồng cũng có thể mở một đường truy cập đối tượng khác.

Trong vận hành, phải quản lý phiên bản, credential, quyền, hạn mức, cảnh báo và việc ngừng API. Một ngoại lệ tạm thời cần có lý do, phạm vi, chủ sở hữu, thời hạn và kiểm soát bù; không biến việc bỏ kiểm tra ở một endpoint thành mặc định mới cho toàn dịch vụ.

Một chuỗi truy vết gọn cho tình huống này là:

```text
Tài sản: dữ liệu tenant và tính toàn vẹn phê duyệt
    -> Đe dọa: thay ID, dùng sai quyền, vượt trạng thái, lạm dụng export
    -> Yêu cầu: danh tính + phạm vi đối tượng + trường + luồng + giới hạn
    -> Thiết kế: kiểm soát tại đúng ranh giới và bảo vệ tại commit
    -> Kiểm chứng: ma trận dương/âm, cạnh tranh, lỗi phụ thuộc, tác dụng phụ
    -> Vận hành: audit, cảnh báo, cập nhật quyền, quản lý phiên bản
```

Yêu cầu bảo mật API có giá trị khi người triển khai biết phải thực thi ở đâu, người kiểm thử biết phải quan sát điều gì và người vận hành biết hệ thống phải làm gì khi điều kiện thay đổi. Danh tính hợp lệ, quyền đúng tài nguyên, dữ liệu đúng phạm vi và hành vi phục hồi rõ ràng phải cùng tạo thành hợp đồng của từng thao tác API.
