# Abuse case

Trong chương **Threat modeling**, **abuse case** là kịch bản mô tả cách một tác nhân có thể **lạm dụng chức năng, dữ liệu, quy trình hoặc quyền truy cập của hệ thống** để đạt kết quả trái với mục tiêu bảo mật và lợi ích hợp lệ của người dùng. Thay vì chỉ hỏi *người dùng muốn làm gì*, nhóm phân tích hỏi thêm: **Một người có động cơ bất lợi, hoặc một tài khoản đã bị chiếm quyền, có thể khiến chức năng này hoạt động theo cách gây hại nào?**

Ví dụ, một nền tảng học trực tuyến có chức năng để giảng viên xuất danh sách học viên thuộc lớp của mình. Use case bình thường là “giảng viên xuất dữ liệu lớp được phân công”. Một abuse case tương ứng là “người có tài khoản giảng viên cố truy cập dữ liệu của lớp không được phân công thông qua chức năng xuất”. Sự khác biệt dẫn đến những yêu cầu mà đặc tả chức năng thường bỏ sót: kiểm tra quyền theo từng lớp ở server, giới hạn đối tượng được xuất, giám sát xuất dữ liệu bất thường và kiểm thử truy cập chéo lớp.

Bài học thuộc module **SECURITY_SECURITY_ASSURANCE**: mục tiêu không dừng ở việc liệt kê các kịch bản đáng ngại. Cần chuyển chúng thành **mục tiêu bảo mật, yêu cầu, security controls, kiểm thử, bằng chứng và kết luận có giới hạn**, sau đó theo dõi finding và rủi ro còn lại trong cả phát triển lẫn vận hành.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích abuse case và phân biệt nó với use case, misuse case, threat scenario, vulnerability và test case.
2. Nhận diện tài sản, actor, mục tiêu lạm dụng, điểm vào, điều kiện, ranh giới tin cậy và tác động trong một abuse case.
3. Khai thác sơ đồ luồng dữ liệu (DFD), user journey và chức năng nghiệp vụ để tìm các cách lạm dụng có ý nghĩa.
4. Viết kịch bản đủ cụ thể để thiết kế control và phép thử mà không phụ thuộc vào một lỗ hổng hoặc công cụ tấn công cụ thể.
5. Ánh xạ abuse case sang security requirement, preventive/detective controls, tiêu chí đạt và evidence phục vụ assurance.
6. Ưu tiên abuse cases theo rủi ro, quản lý ngoại lệ và tái đánh giá khi chức năng hoặc kiến trúc thay đổi.

## 2. Abuse case là gì?

### 2.1. Từ hành vi hợp lệ đến hành vi lạm dụng

Một **use case** thường nêu mục tiêu hợp lệ, actor, điều kiện bắt đầu, các bước chính và kết quả thành công của người dùng. **Abuse case** nhìn từ góc tác nhân sử dụng hoặc thao túng cùng hệ thống để tạo ra kết quả không mong muốn.

| Câu hỏi | Use case bình thường | Abuse case |
|---|---|---|
| Ai thực hiện? | Người dùng/nhân viên/ứng dụng được kỳ vọng | Kẻ ngoài, người dùng lạm dụng quyền, tài khoản bị chiếm, đối tác hoặc tác nhân khác |
| Mục tiêu? | Hoàn thành công việc được cho phép | Đọc/sửa dữ liệu ngoài quyền, vượt hạn mức, giả mạo, phá gián đoạn, che giấu hành động |
| “Thành công” nghĩa là gì? | Nghiệp vụ trả kết quả đúng | Hậu quả bất lợi xảy ra hoặc control bị vượt qua |
| Điều gì được kiểm tra? | Luồng hợp lệ, tính đúng đắn chức năng | Ranh giới quyền, điều kiện lạm dụng, trạng thái lỗi, giám sát và giới hạn tác động |
| Đầu ra? | Tiêu chí chức năng và test trường hợp sử dụng | Yêu cầu bảo mật, các kiểm thử âm, log/cảnh báo, biện pháp kiểm soát |

Abuse case **không đồng nghĩa luôn có kẻ tấn công bên ngoài**. Một giảng viên có tài khoản hợp lệ nhưng cố tải dữ liệu lớp khác, một nhân sự dùng quyền hỗ trợ để truy cập thông tin không phục vụ nhiệm vụ, hay một service account bị lạm dụng đều là những actor cần xem xét.

Abuse case cũng không bắt buộc phải mô tả chuỗi khai thác chi tiết. **Kịch bản lạm dụng ở mức hành vi và kết quả** thường bền vững hơn mô tả phụ thuộc vào phiên bản thư viện hoặc payload cụ thể.

### 2.2. Abuse case, misuse case và threat scenario

Thuật ngữ **misuse case** và **abuse case** đôi khi được dùng gần như tương đương trong tài liệu, phương pháp threat modeling và nhóm phát triển. Không có một ranh giới thuật ngữ bắt buộc áp dụng cho mọi tổ chức. Có nhóm dùng *misuse case* để mô tả việc dùng sai chức năng, *abuse case* để nhấn mạnh ý đồ lạm dụng, nhưng hãy **định nghĩa quy ước trước khi làm việc chung**.

| Khái niệm | Trọng tâm | Ví dụ |
|---|---|---|
| **Use case** | Hành vi hợp lệ mà sản phẩm cần hỗ trợ | Giảng viên xuất dữ liệu lớp mình quản lý |
| **Abuse/misuse case** | Hành vi sử dụng hệ thống theo cách tạo hậu quả bất lợi | Giảng viên cố xuất dữ liệu lớp không được phân công |
| **Threat scenario** | Bối cảnh mối đe dọa, đường xảy ra và hậu quả; có thể rộng hơn một chức năng | Tài khoản giảng viên bị chiếm và bị dùng để trích xuất dữ liệu học viên |
| **Vulnerability** | Điểm yếu cho phép hoặc làm tăng khả năng kịch bản xảy ra | Backend chỉ kiểm tra đăng nhập, không kiểm tra quyền theo đối tượng |
| **Risk** | Ảnh hưởng bất định lên mục tiêu, đánh giá cùng likelihood/impact | Nguy cơ lộ dữ liệu học viên và vi phạm cam kết |
| **Security requirement** | Hành vi bảo mật hệ thống phải đáp ứng | Mỗi yêu cầu xuất phải kiểm tra quyền lớp học phía server |
| **Security test case** | Phép kiểm tra có tiền đề, thao tác, expected result và evidence | Request của giảng viên lớp A tới dữ liệu lớp B phải bị từ chối |

Một abuse case có thể tồn tại **trước khi xác nhận vulnerability**, ví dụ “tác nhân cố thao túng quy trình hoàn tiền”. Threat modeling tìm điều cần phòng ngừa, còn kiểm thử và đánh giá kiến trúc tìm xem hệ thống có đường thực hiện kịch bản đó hay không.

## 3. Vì sao abuse case quan trọng đối với security assurance?

Một ứng dụng có thể vượt qua hàng trăm bài kiểm thử chức năng nhưng vẫn có lỗi bảo mật nghiêm trọng, bởi test chỉ xác nhận **những gì người dùng được phép làm**. Abuse cases giúp kiểm tra thêm **những gì hệ thống tuyệt đối không được cho phép**, kể cả khi request có định dạng hợp lệ và người gửi đã đăng nhập.

Những lợi ích chính:

- **Phát hiện khoảng trống trong yêu cầu:** đặc tả “xuất file thành công” thường không nói “không được xuất file của người khác”.
- **Làm rõ ranh giới tin cậy:** actor có thể cung cấp tham số, metadata, danh tính hoặc tác vụ async; server phải quyết định dữ liệu nào đáng tin.
- **Định hướng thiết kế control:** từ hành vi lạm dụng suy ra authorization, validation, rate limiting, approval, logging và các biện pháp khác phù hợp.
- **Tạo test âm có chủ đích:** kiểm thử phân quyền, thay đổi trạng thái, giới hạn tiêu thụ tài nguyên, chống replay, thu hồi quyền.
- **Cung cấp cơ sở đánh giá rủi ro:** liên kết khả năng xảy ra và tác động tới tài sản, không chỉ một danh sách lỗ hổng kỹ thuật.
- **Hỗ trợ audit và assurance:** chứng minh một yêu cầu bảo mật đã được thiết kế, triển khai, vận hành và kiểm tra trong phạm vi xác định.

**Không nên đo mức bao phủ bảo mật chỉ bằng số abuse cases được viết.** Chất lượng thể hiện ở việc đã nhận diện những đường lạm dụng quan trọng, kiểm tra đúng control, khắc phục phát hiện và cập nhật khi có thay đổi.

## 4. Cấu trúc đầy đủ của một abuse case

Một abuse case có thể trình bày tự nhiên bằng văn bản, bảng hoặc mẫu có cấu trúc. Các trường hữu ích gồm:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| **ID và tên** | Kịch bản được gọi và theo dõi bằng mã nào? |
| **Use case bị lạm dụng** | Chức năng hoặc quy trình hợp lệ nào bị lợi dụng? |
| **Tài sản và mục tiêu** | Tài sản/dữ liệu nào phải được bảo vệ, mục tiêu CIA hoặc nghiệp vụ nào bị ảnh hưởng? |
| **Abuse actor/persona** | Ai có thể thực hiện? Quyền, tri thức, tài nguyên và động cơ giả định là gì? |
| **Entry point** | Web, API, mobile, background job, queue, webhook, integration hay quy trình quản trị? |
| **Preconditions** | Cần đăng nhập, có role nào, có tài nguyên nào tồn tại hoặc phải xảy ra điều kiện trước? |
| **Trust boundaries** | Dữ liệu/thao tác đi qua ranh giới nào: client–server, tenant, role, service, nhà cung cấp? |
| **Abusive action/path** | Hành vi lạm dụng chính theo chuỗi logic ở mức phân tích là gì? |
| **Undesired outcome** | Kết quả xấu quan sát được và hậu quả đối với mục tiêu là gì? |
| **Assumptions** | Đang dựa vào những giả định nào chưa được kiểm chứng? |
| **Controls và requirements** | Hệ thống phải chặn/phát hiện/giới hạn/khôi phục bằng cơ chế nào? |
| **Verification và evidence** | Test nào chứng minh đạt/không đạt, kết quả lưu ở đâu, giới hạn gì? |
| **Risk owner và priority** | Ai chịu rủi ro, mức ưu tiên do phân tích nào xác định? |
| **Lifecycle** | Trạng thái thiết kế, kiểm thử, finding, khắc phục, retest, thời điểm đánh giá lại? |

Kịch bản nên tập trung vào **một mục tiêu lạm dụng rõ ràng**. Nếu một tiêu đề bao gồm “chiếm tài khoản, lộ dữ liệu, sửa điểm, xóa backup, tắt log”, nên tách thành các abuse cases có tiền đề, control và test riêng; vẫn có thể liên kết chúng trong một chuỗi tấn công rộng hơn.

### Mẫu viết nhanh bằng ngôn ngữ tự nhiên

> **Với tư cách là [actor có năng lực/quyền nhất định], tôi muốn [lạm dụng chức năng hoặc quy trình] để [đạt kết quả gây hại], trong điều kiện [preconditions], có thể ảnh hưởng đến [tài sản/mục tiêu]. Hệ thống phải [security invariant hoặc control] và phép thử cần xác nhận [tiêu chí].**

Dạng “user story đối nghịch” giúp brainstorming nhưng cần bổ sung evidence, risk owner và kiểm soát cụ thể trước khi dùng trong chương trình assurance.

## 5. Quy trình khám phá abuse cases

### Bước 1 — Chọn phạm vi và xác định use cases

Bắt đầu từ những hành trình có ý nghĩa bảo mật: đăng ký/đăng nhập, đặt lại mật khẩu, ghi điểm, nộp bài, thanh toán, xuất dữ liệu, chia sẻ file, cập nhật quyền, quản trị production, tích hợp với đối tác.

Với mỗi use case, ghi **actor hợp lệ**, **đầu vào**, **quy tắc nghiệp vụ**, **dữ liệu được trả về hoặc thay đổi**, **điểm phụ thuộc** và **kết quả kỳ vọng**.

### Bước 2 — Liệt kê tài sản, ranh giới và nguồn tin cậy

Vẽ luồng dữ liệu và đánh dấu các ranh giới như:

- Trình duyệt/mobile ↔ backend API.
- Người dùng lớp A ↔ dữ liệu lớp B, tenant A ↔ tenant B.
- User thường ↔ tài khoản có quyền hỗ trợ hoặc quản trị.
- API ↔ worker/queue ↔ object storage.
- Hệ thống nội bộ ↔ nhà cung cấp nhận webhook hoặc gọi API.
- Pipeline CI/CD ↔ production credentials và artifact phát hành.

Một tham số như classId hoặc tenantId do client gửi **không tự chứng minh quyền** của người gửi. Một callback từ hệ thống bên ngoài cũng chưa mặc nhiên đáng tin nếu chưa xác thực nguồn, ràng buộc nội dung, thời gian và xử lý lặp.

### Bước 3 — Chọn actor và năng lực có cơ sở

Có thể xem xét khách chưa đăng nhập, người dùng đã đăng nhập, tài khoản hợp lệ nhưng vượt quyền, admin nội bộ, tài khoản bị chiếm, workload/service account, bên tích hợp, hoặc actor có thể gửi lượng lớn request.

**Không cần giả định kẻ tấn công có toàn quyền hệ thống** để phát hiện mọi vấn đề. Tài khoản có quyền thấp đôi khi là điểm khởi đầu thực tế hơn. Ghi rõ năng lực nào là **giả định**, tránh xem đó là sự kiện đã xác nhận.

### Bước 4 — Hỏi các câu hỏi lạm dụng

Với từng bước sử dụng hợp lệ, đặt các câu hỏi:

1. Nếu actor **thay đối tượng** (ID, chủ sở hữu, tenant, lớp học) thì sao?
2. Nếu actor **lặp lại, thực hiện sai thứ tự hoặc bỏ qua một bước** thì sao?
3. Nếu actor **gửi dữ liệu ngoài phạm vi dự kiến** hoặc bản ghi đã hết hạn thì sao?
4. Nếu actor **gọi API trực tiếp** thay vì qua giao diện thì sao?
5. Nếu actor **tận dụng giới hạn quyền khác nhau** giữa gateway, service và worker thì sao?
6. Nếu actor **lạm dụng tính năng hợp pháp ở quy mô lớn** (bulk export, gửi email hàng loạt) thì sao?
7. Nếu actor **thay đổi trạng thái bên ngoài** khi giao dịch đang diễn ra (thu hồi quyền, hết hạn token, chuyển lớp) thì sao?
8. Nếu **logging, rate limit, queue, nhà cung cấp hoặc cơ chế khôi phục** mất hiệu lực thì sao?
9. Ai được lợi, ai chịu tác động, và điều gì sẽ cho thấy hành vi lạm dụng thành công?

Những câu hỏi này giúp tạo kịch bản. Không cần biến toàn bộ câu trả lời thành risk nghiêm trọng; cần đánh giá tác động và khả năng xảy ra có ngữ cảnh.

### Bước 5 — Mô tả đường hành vi và hậu quả

Xác định preconditions, điểm vào, hành vi lạm dụng, nơi quyết định tin cậy bị sai và kết quả có thể quan sát. Nêu **điều kiện để kịch bản thành công**, không dự đoán rằng hệ thống chắc chắn có lỗi nếu chưa kiểm tra.

### Bước 6 — Đề xuất security invariants và controls

**Security invariant** là điều kiện phải luôn đúng qua mọi đường thao tác, ví dụ: “người dùng không được đọc dữ liệu học viên ngoài lớp mà họ có quyền tại thời điểm yêu cầu”. Từ đó lựa chọn control phòng ngừa, phát hiện, ứng phó và khôi phục.

### Bước 7 — Thiết kế verification và liên kết evidence

Đặt phép kiểm thử rõ tiền đề, dữ liệu, hành động, expected result và cách xác minh trạng thái cuối. Lưu liên kết tới requirements, control IDs, test suite, build/deployment, log và các finding.

### Bước 8 — Ưu tiên và theo dõi

Đánh giá risk theo tác động, độ phơi bày, điều kiện cần, control hiện có và độ bất định. Gán owner và deadline, theo dõi các trường hợp chưa đủ bằng chứng, retest sau khi khắc phục.

### Bước 9 — Tái đánh giá khi hệ thống thay đổi

Abuse case có thể thay đổi khi thêm endpoint, tenant, luồng import, vai trò người dùng, nhà cung cấp hoặc cách lưu file. Threat modeling cần quay lại theo sự kiện thay đổi, không chỉ trước release đầu tiên.

## 6. Dùng DFD để tìm ranh giới bị lạm dụng

Giả sử nền tảng học trực tuyến có tính năng xuất hồ sơ học viên. Luồng hợp lệ:

~~~mermaid
flowchart LR
    U["Giảng viên trên trình duyệt"] -->|"Yêu cầu export(classId)"| API["Learning API"]
    API -->|"Xác thực và quyết định quyền"| IAM["Identity / Authorization"]
    API -->|"Tạo export job"| Q["Queue"]
    Q --> W["Export Worker"]
    W --> DB[("CSDL học viên")]
    W --> S[("Private Object Storage")]
    API -->|"Trả kết quả được phép"| U
    S -->|"Tải file qua cơ chế có kiểm soát"| U
~~~

Sơ đồ giúp đặt câu hỏi tại mỗi ranh giới, chứ **không tự chứng minh** có hoặc không có lỗ hổng:

- Trình duyệt gửi classId: ai xác nhận giảng viên có quyền với classId?
- API phát job: queue message có chứa actor, lớp, scope và quyết định quyền đủ tin cậy không?
- Worker đọc DB: worker chỉ được xử lý dữ liệu trong phạm vi job, hay có quyền đọc mọi lớp?
- Object storage: file có private không, link tải có bị sử dụng bởi người khác, thời gian hiệu lực có hợp lý?
- Kết quả export: nếu giảng viên đã bị thu hồi quyền trước khi tải, hệ thống xử lý thế nào theo chính sách?
- Audit: có thể truy vết ai xuất dữ liệu, khi nào, loại dữ liệu nào, mà không ghi lộ dữ liệu nhạy cảm vào log không?

Một số rủi ro xuất hiện **giữa các thành phần**, ví dụ API kiểm tra quyền lúc tạo job nhưng worker bỏ qua scope đã được xác minh, hoặc file được lưu private rồi bị phát qua liên kết tải không có kiểm soát thích hợp. Vì thế abuse cases cần bao trùm **luồng end-to-end**, không chỉ mỗi endpoint.

## 7. Ví dụ xuyên suốt: lạm dụng chức năng xuất danh sách học viên

### 7.1. Use case hợp lệ

**UC-EXPORT-01 — Giảng viên xuất dữ liệu lớp mình quản lý.**

- Actor hợp lệ: giảng viên đã đăng nhập, đang được phân công quản lý lớp 42.
- Precondition: lớp tồn tại và chính sách cho phép xuất dữ liệu tương ứng.
- Luồng chính: chọn lớp → yêu cầu export → hệ thống kiểm tra quyền → tạo file phù hợp → cho phép tải file.
- Hậu điều kiện: chỉ dữ liệu thuộc phạm vi được cấp được xuất, có ghi dấu vết cần thiết.
- Tài sản: kết quả học tập, thông tin học viên, quyền truy cập, audit trail.

Từ use case này phát triển ít nhất những kịch bản lạm dụng sau.

### 7.2. Danh sách abuse cases

| ID | Abuse case | Actor và hành vi | Mục tiêu bị ảnh hưởng |
|---|---|---|---|
| AB-EXPORT-01 | Truy cập chéo lớp | Giảng viên lớp 42 yêu cầu export lớp 43 | Bí mật dữ liệu, phân quyền đối tượng |
| AB-EXPORT-02 | Lạm dụng liên kết tải | Người không được cấp quyền dùng lại URL hoặc file reference | Bí mật dữ liệu, thời hạn/quyền truy cập |
| AB-EXPORT-03 | Xuất dữ liệu quá mức | Actor hợp lệ tạo nhiều job hoặc export vượt mục đích hợp lệ | Giới hạn sử dụng, tài nguyên và privacy |
| AB-EXPORT-04 | Bỏ qua quyền ở worker | Job giả định đã được xác minh nhưng chứa scope sai hoặc không có ràng buộc đáng tin | Tính toàn vẹn quyết định ủy quyền |
| AB-EXPORT-05 | Quyền bị thu hồi giữa các bước | Quyền hợp lệ lúc tạo job, không còn hợp lệ khi phát file | Quản lý vòng đời quyền và chia sẻ |
| AB-EXPORT-06 | Lạm dụng chức năng hỗ trợ | Nhân sự hỗ trợ dùng quyền đặc biệt để export ngoài nhiệm vụ | Phân tách nhiệm vụ, accountability |
| AB-EXPORT-07 | Log không phản ánh export thật | Job hoàn thành nhưng sự kiện không đến hệ thống giám sát | Khả năng điều tra, phát hiện bất thường |

Các kịch bản trên chưa khẳng định lỗ hổng tồn tại. Chúng là **giả thuyết cần kiểm tra** và có thể được ưu tiên khác nhau theo threat model, tài sản và control thực tế.

### 7.3. Viết đầy đủ abuse case AB-EXPORT-01

~~~yaml
id: AB-EXPORT-01
title: "Giảng viên xuất dữ liệu học viên ngoài lớp được phân công"
legitimate_use_case: UC-EXPORT-01
asset: "Kết quả học tập và thông tin cá nhân của học viên"
security_objective: "Chỉ người được phân quyền mới truy cập dữ liệu lớp"
abuse_actor:
  role: "Giảng viên đã đăng nhập"
  assumed_capabilities:
    - "Có tài khoản hợp lệ và quyền export lớp của mình"
    - "Có thể gửi request API bằng client hợp lệ"
entry_point: "API yêu cầu tạo export job"
preconditions:
  - "Actor quản lý lớp 42 nhưng không có quyền lớp 43"
  - "Dữ liệu lớp 43 thuộc phạm vi bảo vệ"
abuse_goal: "Nhận file kết quả học tập của lớp 43"
abuse_path: >
  Actor cung cấp mã lớp ngoài phạm vi và cố nhận kết quả
  từ API, worker hoặc đường tải file.
trust_boundaries:
  - "Trình duyệt tới backend"
  - "Backend tới queue/worker"
  - "Worker tới storage và đường tải file"
undesired_outcome: "Xuất trái phép dữ liệu học viên"
security_invariant: >
  Mỗi tác vụ xuất và lượt tải phải tuân theo chính sách
  quyền truy cập đối tượng trong toàn bộ vòng đời.
controls:
  - "Object-level authorization ở phía server"
  - "Scope ràng buộc chặt vào export job"
  - "Đường tải file được kiểm soát; log có truy vết"
verification:
  - "Negative test: actor lớp 42 yêu cầu export lớp 43 bị từ chối"
  - "Không có job/file ngoài quyền được tạo hoặc phát hành"
  - "Audit event được tạo theo chính sách"
risk_owner: "Chủ sở hữu dịch vụ học tập"
control_owner: "Backend/Platform"
status: "Cần assessment theo phiên bản và môi trường cụ thể"
~~~

Mẫu này là tài liệu minh họa. Các mã, role và tiêu chí phải được điều chỉnh theo phạm vi sản phẩm thật. **Actor lớp 42** không nhất thiết biết cách khai thác kỹ thuật cụ thể; ta kiểm tra liệu hệ thống có thực thi security invariant khi tham số thay đổi hay không.

### 7.4. Security requirements suy ra từ abuse case

| Requirement ID | Điều hệ thống phải bảo đảm | Control/điểm thực thi | Điều kiện đánh giá |
|---|---|---|---|
| REQ-EXPORT-01 | Mọi yêu cầu tạo export phải kiểm tra quyền đọc/xuất trên **đúng lớp và tập dữ liệu** | Authorization tại backend/service | Actor không có quyền phải bị từ chối |
| REQ-EXPORT-02 | Quyền không phụ thuộc vào classId/tenantId client khai mà không xác minh | Trust boundary và nguồn dữ liệu phân quyền đáng tin | Thay tham số không nâng được quyền |
| REQ-EXPORT-03 | Export job phải gắn scope đã xác minh và không thể bị đổi sang đối tượng khác | Queue job validation, worker enforcement | Job sai scope bị từ chối, không xuất dữ liệu |
| REQ-EXPORT-04 | File phát sinh không thể tải qua đường không được phê duyệt | Private storage và download authorization | Người không có quyền không tải được file |
| REQ-EXPORT-05 | Hệ thống áp dụng chính sách khi quyền thay đổi trong vòng đời export | Reauthorization/expiry theo kiến trúc đã chọn | Test quyền thu hồi có expected behavior rõ |
| REQ-EXPORT-06 | Hoạt động xuất dữ liệu nhạy cảm được ghi dấu vết và giám sát | Audit log, phát hiện xuất bất thường | Sự kiện thử đi đến nơi quan sát và owner |
| REQ-EXPORT-07 | Giới hạn quy mô export theo chính sách dữ liệu và rủi ro | Giới hạn số lượng, rate/quota, phê duyệt theo trường hợp | Test trường hợp vượt ngưỡng không làm lộ/thực hiện quá mức |

Các requirement phải **đo được**: ví dụ “API an toàn” không có tiêu chí chấp nhận; “actor không quản lý lớp 43 không được tạo hoặc nhận file chứa dữ liệu lớp 43” có thể kiểm chứng được.

### 7.5. Ví dụ phác thảo kiểm tra quyền ở Java

Đoạn Java sau chỉ minh họa **nguyên tắc kiểm tra quyền phía server** tại ranh giới tạo job, không phải triển khai hoàn chỉnh. Trong hệ thống thật cần dùng API authorization, mô hình dữ liệu và giao dịch phù hợp.

~~~java
public ExportJobId requestExport(
        AuthenticatedUser actor,
        long requestedClassId) {

    // Chỉ tin danh tính đã xác thực qua cơ chế phía server.
    if (!classAccessPolicy.canExportLearners(
            actor.userId(), requestedClassId)) {
        throw new AccessDeniedException("Export not permitted");
    }

    // Tạo job với actor, scope và quyền đã được xác định ở server.
    // Worker và đường tải vẫn phải thực thi invariant liên quan.
    return exportJobService.createAuthorizedJob(
            actor.userId(), requestedClassId);
}
~~~

Điểm quan trọng không phải tên hàm mà là **quyết định quyền dựa trên nguồn đáng tin**, không dựa duy nhất vào một role chung như TEACHER hoặc một classId do client tự khai. Worker và download flow phải được xem xét tiếp: một lần check ở controller chưa bảo vệ toàn bộ vòng đời nếu job payload hoặc file reference có thể bị thay đổi.

Các quyết định về **kiểm tra lại quyền tại thời điểm tải**, thời hạn file, việc xử lý khi actor đổi vai trò và quyền của admin đặc biệt cần được **đặc tả theo policy**, thay vì để team tự suy đoán.

### 7.6. Thiết kế test case cho AB-EXPORT-01

| Test ID | Tiền điều kiện | Thao tác kiểm thử | Kỳ vọng và evidence |
|---|---|---|---|
| TC-01 | Giảng viên A được quyền lớp 42 | Yêu cầu export lớp 42 | Cho phép đúng phạm vi; audit event hợp lệ |
| TC-02 | Giảng viên A không được quyền lớp 43 | Yêu cầu export lớp 43 | Từ chối; không có job/file lộ dữ liệu 43 |
| TC-03 | Người chưa đăng nhập | Yêu cầu export lớp bất kỳ | Từ chối theo chính sách xác thực |
| TC-04 | User đã bị thu hồi quyền lớp 42 | Yêu cầu export lớp 42 | Từ chối theo trạng thái quyền hiện tại |
| TC-05 | Job có scope không hợp lệ theo chính sách | Cho worker xử lý bản ghi test có kiểm soát | Worker không tạo file trái scope; có log phù hợp |
| TC-06 | Có file xuất lớp 42 | Actor không được cấp quyền thử cơ chế tải | Không đọc được file; kiểm tra trạng thái storage |
| TC-07 | Quyền thay đổi giữa tạo và tải | Thu hồi quyền theo quy trình test rồi kiểm tra đường tải | Kết quả đúng theo policy vòng đời quyền |
| TC-08 | Có một sự kiện export được phê duyệt | Kiểm tra đường log và rule quan sát | Log đầy đủ trường cần thiết, không ghi token hoặc nội dung dữ liệu |

Phép thử âm cần xác nhận cả **response** và **side effects**: server có thể trả 403 nhưng worker vẫn tạo file, hoặc trả lỗi nhưng log đã chứa dữ liệu nhạy cảm. Khi có hành vi bất đồng bộ, cần theo dõi kết quả job và file phát sinh theo ID để kết luận đúng.

Các phép thử phải chạy trong môi trường và dữ liệu kiểm soát phù hợp. Kết quả chỉ hỗ trợ claim cho **phiên bản, môi trường, tuyến API và tài khoản đã kiểm thử**; muốn kết luận về production phải có bằng chứng triển khai và tính tương đương hoặc kiểm tra phù hợp tại production.

## 8. Những abuse cases khác trong nền tảng học

### 8.1. Đặt lại mật khẩu

**Use case:** người dùng quên mật khẩu và xác minh danh tính để đặt lại.

**Abuse cases:** một actor cố xác định tài khoản có tồn tại dựa trên khác biệt thông báo; dùng lại reset token đã dùng; dùng token sau khi hết hạn; kích hoạt gửi nhiều email đặt lại để quấy rối; lợi dụng quy trình support để chiếm quyền.

**Invariants và controls** có thể gồm: phản hồi không tiết lộ thông tin tài khoản không cần thiết, reset token khó dự đoán và được bảo vệ, dùng một lần, có hạn theo policy, vô hiệu hóa thích hợp, rate/abuse controls và audit. Các giá trị TTL/rate cụ thể phụ thuộc threat model và yêu cầu của tổ chức.

**Tests:** xác nhận token đã dùng không thể dùng lại, token hết hạn bị từ chối, quy trình không cho phép chiếm tài khoản người khác, và ghi log không lộ token. Không nên suy ra “an toàn” chỉ từ việc email được gửi thành công.

### 8.2. Thay đổi điểm và trạng thái bài nộp

**Use case:** giảng viên sửa điểm cho học viên được phân công trong thời kỳ cho phép.

**Abuse cases:** người khác gửi request đổi điểm; giảng viên thao tác sau hạn chốt; gửi nhiều update đồng thời để vượt kiểm tra trạng thái; gửi dữ liệu ngoài ràng buộc nghiệp vụ; tài khoản support dùng quyền cao để sửa điểm không qua phê duyệt.

**Controls:** authorization theo đối tượng và hành động, quy tắc nghiệp vụ trên server, kiểm soát trạng thái/phiên bản phù hợp, audit thay đổi có before/after hợp lệ, quy trình phê duyệt đặc biệt.

**Tests:** negative test cho role, lớp và thời hạn; kiểm tra cạnh tranh cập nhật theo kịch bản; xác minh log và khả năng truy vết người phê duyệt.

### 8.3. Gửi thông báo hoặc lời mời hàng loạt

**Use case:** giảng viên gửi thông báo cho lớp được phân công.

**Abuse cases:** tạo lượng lớn thông báo tới người không thuộc lớp; lợi dụng chức năng để spam, làm cạn quota nhà cung cấp hoặc gây gián đoạn; chèn nội dung không phù hợp theo chính sách.

**Controls:** scope người nhận trên server, quota/rate limit dựa trên ngữ cảnh, chống lặp và khả năng hủy/khóa chiến dịch, monitoring về số lượng bất thường, xử lý dữ liệu cá nhân trong danh sách nhận.

**Tests:** đối chiếu danh sách nhận thực tế, test giới hạn và hành vi retry trong môi trường kiểm soát, kiểm tra cảnh báo khi vượt ngưỡng theo chính sách.

### 8.4. Lạm dụng luồng thanh toán, hoàn tiền hoặc cấp quyền học

**Use case:** thanh toán hợp lệ kích hoạt quyền truy cập khóa học; hoàn tiền thực hiện theo quy tắc nghiệp vụ.

**Abuse cases:** callback bị lặp/giả mạo, trạng thái giao dịch bị dùng sai thứ tự, quyền khóa học được cấp trước khi có bằng chứng thanh toán, yêu cầu hoàn tiền nhiều lần, nhân viên hỗ trợ thao tác ngoài thẩm quyền.

**Controls:** xác thực tính hợp lệ thông điệp từ nhà cung cấp, kiểm tra trạng thái nghiệp vụ phía server, tính idempotent cho hành động lặp, phân tách quyền, audit và đối soát giao dịch.

**Tests:** callback hợp lệ, callback lặp, thứ tự trạng thái bất thường, dữ liệu không khớp đơn hàng, quyền hỗ trợ ngoài phạm vi; xác nhận không phát sinh cấp quyền hoặc hoàn tiền ngoài tiêu chí. Cần mô phỏng trong hệ thống kiểm thử, tránh tạo giao dịch tài chính thật ngoài phê duyệt.

## 9. Phân loại câu hỏi lạm dụng để tránh bỏ sót

Có thể dùng các nhóm sau như một **checklist gợi ý**, không xem là danh sách đầy đủ:

| Nhóm | Câu hỏi abuse case | Control thường liên quan |
|---|---|---|
| **Identity/session** | Ai có thể mạo danh, dùng lại hoặc duy trì phiên không hợp lệ? | Xác thực, vòng đời session, quản lý token, MFA |
| **Authorization** | Có thể đổi đối tượng, vai trò, tenant hoặc gọi đường API khác để vượt quyền? | Kiểm tra object/function-level, least privilege |
| **Business logic/state** | Có thể lặp, đổi thứ tự, bỏ bước, tạo race hoặc lợi dụng chuyển trạng thái? | State machine phía server, idempotency, consistency |
| **Input/output** | Input có thể gây dữ liệu/chức năng ngoài phạm vi? | Validation, encoding thích hợp, kiểm soát file |
| **Data handling/privacy** | Có thể xuất/đọc/chia sẻ dữ liệu rộng hơn mục đích hợp lệ? | Data minimization, scope, download control, audit |
| **Resource abuse** | Chức năng hợp pháp có bị dùng để làm cạn quota hoặc gián đoạn? | Quota, rate limit, backpressure, capacity planning |
| **Integration/trust** | Service có tin nhầm callback, queue message hoặc identity từ đối tác? | Authentication, integrity, replay protection, context validation |
| **Privileged operations** | Có thể lạm dụng quyền support/admin hoặc bỏ qua phê duyệt? | Separation of duties, approvals, privileged access monitoring |
| **Detection/recovery** | Nếu control lỗi, có phát hiện, giới hạn tác động, khôi phục được? | Log health, alert test, incident runbook, backup/restore |
| **Human workflow** | Có thể thao túng phê duyệt, offboarding, hỗ trợ người dùng? | Xác minh qua kênh thích hợp, audit, phân vai |

Mỗi nhóm cần đặt câu hỏi với **nghiệp vụ cụ thể**, không chỉ liệt kê tên kỹ thuật rồi đánh dấu “đã threat model”.

## 10. Liên hệ abuse cases với STRIDE và các phương pháp threat modeling

Một đội có thể dùng **STRIDE** để brainstorm loại mối đe dọa trong kiến trúc:

- **S — Spoofing:** mạo danh actor hoặc nguồn thông điệp.
- **T — Tampering:** thay đổi dữ liệu, request, bản ghi hoặc trạng thái ngoài quyền.
- **R — Repudiation:** khó truy vết/chối bỏ hành động do thiếu bằng chứng đáng tin.
- **I — Information Disclosure:** lộ dữ liệu ra ngoài phạm vi cho phép.
- **D — Denial of Service:** làm cạn tài nguyên/gián đoạn dịch vụ.
- **E — Elevation of Privilege:** vượt lên quyền cao hơn hoặc thực hiện hành động ngoài thẩm quyền.

Ví dụ abuse case **giảng viên xuất dữ liệu ngoài lớp** liên quan **Information Disclosure** và có thể liên quan **Elevation of Privilege** nếu actor vượt giới hạn quyền. Kịch bản **gửi hàng loạt notification** có thể liên quan Denial of Service hoặc lạm dụng tài nguyên. **Xóa audit log khi làm sai điểm** liên quan Tampering và Repudiation.

STRIDE giúp tạo ý tưởng về **loại tác động/kỹ thuật**, còn abuse case kết hợp **actor, chức năng, tiền đề, hậu quả và cách kiểm chứng**. Không cần ép một abuse case vào đúng một ô STRIDE; một kịch bản có thể chạm nhiều nhóm. DFD, attack tree, checklist ứng dụng và phân tích quy tắc nghiệp vụ có thể hỗ trợ lẫn nhau.

Không nên xem “đã chạy STRIDE” hoặc “đã viết abuse case” là bằng chứng hệ thống không có đường tấn công. Các mô hình nêu ra điều cần xem xét; hiệu quả của control cần được **thiết kế, triển khai, thử nghiệm và theo dõi** riêng.

## 11. Ưu tiên abuse cases theo rủi ro

Không phải mọi kịch bản cần cùng mức đầu tư. Có thể đánh giá:

1. **Mức ảnh hưởng:** dữ liệu nào bị lộ/sửa, dịch vụ nào gián đoạn, nghĩa vụ nào chịu tác động?
2. **Actor và đường tiếp cận:** cần tài khoản có quyền cao hay một user thường cũng có thể kích hoạt?
3. **Khả năng xảy ra:** điều kiện cần, mức phơi bày, dấu hiệu hoạt động bất thường và control hiện tại.
4. **Độ phủ control:** có control phòng ngừa, phát hiện và ứng phó đủ phù hợp không; đã test chưa?
5. **Mức bất định:** còn tuyến API, job, service hoặc dữ liệu nào chưa quan sát được?
6. **Thời gian và thay đổi:** có tính năng mới, cấp quyền mới, thêm nhà cung cấp hoặc finding quá hạn không?
7. **Tác động liên kết:** một abuse case có mở đường cho nhiều kịch bản khác không?

### Ví dụ so sánh ưu tiên

| Abuse case | Dữ kiện đã biết | Điều phải xác minh trước kết luận |
|---|---|---|
| AB-EXPORT-01: vượt quyền đọc dữ liệu lớp | Có thể ảnh hưởng thông tin cá nhân và kết quả học tập | API/worker/download có cùng kiểm tra quyền không; scope bao nhiêu lớp |
| AB-NOTIFY-01: gửi thông báo quá nhiều | Có khả năng cạn quota/ảnh hưởng trải nghiệm | Giới hạn hiện tại, khả năng retry, chi phí và độ phủ cảnh báo |
| AB-RESET-01: lặp token đặt lại mật khẩu | Có thể chiếm quyền tài khoản nếu token dùng lại | One-time/expiry/invalidation, session handling và test |
| AB-ADMIN-01: thao tác hỗ trợ ngoài nhiệm vụ | Quyền lớn có thể tạo tác động nghiêm trọng | Phân vai, approval, log, giám sát, tần suất sử dụng |

Nếu dùng risk score định tính như Likelihood × Impact, phải mô tả **thang đo, tiêu chí, giả định và ngưỡng ưu tiên nội bộ**. Một score không tự là xác suất hay lượng tổn thất. Trường hợp impact nghiêm trọng hoặc yêu cầu bắt buộc có thể cần quy tắc escalation riêng.

Khi thiếu bằng chứng quan trọng, không nên mặc định likelihood thấp. Có thể ghi **priority tạm thời** và giao nhiệm vụ điều tra/kiểm thử để giảm bất định.

## 12. Ánh xạ abuse case thành assurance case

Security assurance muốn trả lời **“Có căn cứ nào để tin mục tiêu bảo mật được đáp ứng?”**. Abuse case hỗ trợ xác định **những điều phải bị ngăn hoặc phát hiện**. Sử dụng chuỗi truy vết:

~~~mermaid
flowchart TD
    A["Use case và tài sản cần bảo vệ"] --> B["Abuse case và tác động"]
    B --> C["Đánh giá risk và mức ưu tiên"]
    C --> D["Security invariant / requirement"]
    D --> E["Control owner và thiết kế control"]
    E --> F["Kiểm thử, runtime telemetry, evidence"]
    F --> G{"Đáp ứng tiêu chí và evidence đủ?"}
    G -->|"Có"| H["Assurance claim có phạm vi, kỳ và giới hạn"]
    G -->|"Không"| I["Finding, remediation, retest"]
    I --> E
    H --> J["Residual risk và quyết định của risk owner"]
    J --> K["Theo dõi thay đổi / review"]
    K --> B
~~~

### 12.1. Mô hình Claim–Argument–Evidence (CAE)

**Claim:** “Trong phạm vi các luồng export production đã xác định, người dùng không thể nhận dữ liệu học viên ngoài lớp được cấp quyền”.

**Argument:** Mọi đường yêu cầu xuất, xử lý job và tải file thực thi hoặc bảo toàn quyền theo mô hình đã phê duyệt; các negative tests chứng minh đường ngoài quyền bị từ chối; cấu hình production tương ứng với phiên bản đã test; audit log giúp phát hiện sự kiện liên quan.

**Evidence:** Danh sách đường export thuộc phạm vi, policy/source code review, integration tests và kết quả chạy theo build, cấu hình IAM/storage, log, job trace, change record, review ngoại lệ, kết quả retest nếu trước đó fail.

**Giới hạn:** Nếu luồng export ở bên thứ ba hoặc tuyến batch chưa được kiểm tra, không được kết luận claim bao phủ chúng. Nếu thiếu log kỳ đánh giá, chỉ có thể xác nhận điều được test ở thời điểm/phiên bản cụ thể.

### 12.2. Bảng truy vết tối thiểu

| Abuse case | Requirement | Control owner | Verification | Evidence | Trạng thái |
|---|---|---|---|---|---|
| AB-EXPORT-01 | REQ-EXPORT-01 | Backend | Negative authorization tests | Test result, build, log, config | Đạt/chưa đạt/chưa đủ bằng chứng |
| AB-EXPORT-02 | REQ-EXPORT-04 | Platform | Thử tải file khi không có quyền | Storage policy, test report | Đạt/chưa đạt/chưa đủ bằng chứng |
| AB-EXPORT-04 | REQ-EXPORT-03 | Backend + worker owner | Job scope invalid/altered test | Queue schema, worker result | Đạt/chưa đạt/chưa đủ bằng chứng |
| AB-EXPORT-07 | REQ-EXPORT-06 | SecOps/Platform | Kiểm thử luồng audit event | Log, alert routing, ticket | Đạt/chưa đạt/chưa đủ bằng chứng |

Đặt **ID ổn định** cho abuse case, requirement, control, test, finding giúp kiểm tra khi thay đổi. Một control có thể giải quyết nhiều kịch bản; một kịch bản cũng thường cần nhiều lớp control. Traceability không tự chứng minh hiệu quả nếu evidence không hợp lệ.

## 13. Chất lượng test và evidence

### 13.1. Test không chỉ kiểm tra HTTP status

Một negative test về truy cập trái phép phải kiểm tra:

- **Response:** đối tượng ngoài quyền có bị từ chối theo chính sách?
- **Side effects:** request bị từ chối có vẫn tạo job, gửi email, sửa DB, tạo file hoặc phát sinh quyền không?
- **Cross-component:** worker, queue, cache, storage, webhook có giữ đúng scope?
- **Audit behavior:** sự kiện có dấu vết cần thiết mà không lộ token hoặc dữ liệu nhạy cảm không?
- **Quyền biến động:** sau khi thu hồi hoặc đổi vai trò, hành vi có đúng policy?
- **Error handling:** lỗi hệ thống có làm bỏ qua authorization, gây lộ dữ liệu hoặc tạo trạng thái không nhất quán không?

Một response 403 là tín hiệu cần thiết cho một số kịch bản, nhưng không chứng minh **không có dữ liệu đã bị xuất ở bước bất đồng bộ**.

### 13.2. Ba lớp đánh giá control

| Lớp | Câu hỏi | Evidence ví dụ |
|---|---|---|
| **Design effectiveness** | Quy tắc có thực sự xử lý abuse case và đường bypass? | Threat model, security requirements, review kiến trúc |
| **Implementation effectiveness** | Quy tắc có được triển khai đúng ở các điểm thuộc phạm vi? | Code/config deployed, policy export, integration test |
| **Operating effectiveness** | Quy tắc có hoạt động qua thời gian và thay đổi? | Test theo kỳ, change history, log, sampling, incident/finding |

Để dùng trong audit hoặc quyết định rủi ro, evidence cần **đúng mục tiêu, đúng phạm vi, đúng thời kỳ, có nguồn gốc, đủ độ phủ và có thể đối chiếu/tái kiểm tra**. Log thiếu hoặc test chỉ chạy trên mock không tương đương production phải được ghi thành **evidence gap**.

Các phép thử có thể chỉ chạy trên môi trường có dữ liệu kiểm thử; cần mô tả giới hạn suy rộng sang production. Hệ thống thực có thể có đường đi thêm, cấu hình khác và dữ liệu tác động khác. Không được lấy kết quả một test làm tuyên bố “không còn lỗ hổng”.

### 13.3. Bằng chứng chống lại việc chấp nhận kết luận sai

Nếu một nhóm khẳng định AB-EXPORT-01 “đã giải quyết” vì giao diện không hiển thị lớp ngoài quyền, hãy hỏi:

- API có kiểm tra quyền **tại server** không?
- Tài khoản thử nghiệm có thực sự không được quyền với lớp 43 không?
- Worker và storage có thể phát file mà không kiểm tra scope không?
- Có đường export khác như CSV, email report, batch hoặc mobile API không?
- Kết quả test thuộc **build và môi trường nào**, có đúng bản production đang chạy không?
- Đã có thay đổi IAM/config sau thời điểm test chưa?

Nếu chưa có câu trả lời, kết luận thích hợp là **chưa đủ bằng chứng**, không phải “đạt”.

## 14. Vai trò và trách nhiệm trong abuse case review

| Vai trò | Trách nhiệm thực tế |
|---|---|
| **Product/Business owner** | Giải thích mục tiêu và quy tắc nghiệp vụ, dữ liệu quan trọng, impact, rủi ro chấp nhận |
| **Architect/Tech lead** | Mô tả kiến trúc, luồng dữ liệu, trust boundary và chọn cách thực thi security invariant |
| **Developer/Backend owner** | Thiết kế và triển khai authorization, validation, workflow controls; viết test |
| **Platform/Operations** | IAM, network, queue, storage, deployment, runtime evidence và recovery |
| **Security engineer/Threat model facilitator** | Dẫn dắt abuse case workshop, phản biện giả định, giúp xác định controls và test |
| **QA/Test engineer** | Xây test âm và test hậu điều kiện; lưu kết quả có thể lặp lại |
| **SOC/SecOps** | Định nghĩa dấu hiệu lạm dụng, log/alert, phát hiện, điều tra và phản hồi |
| **Risk owner/CISO/GRC** | Ưu tiên rủi ro, đánh giá/khuyến nghị, theo dõi finding và quyết định theo thẩm quyền |
| **Assessor/Internal audit** | Đánh giá evidence và hiệu quả control theo phạm vi/mức độc lập được giao |

Người viết abuse case không nhất thiết là người phê duyệt residual risk. Cần tách **người vận hành control**, **người kiểm tra kết quả** và **người có thẩm quyền chấp nhận rủi ro**, nhất là khi kịch bản ảnh hưởng dữ liệu nhạy cảm.

### Workshop ngắn có thể tổ chức thế nào?

Một buổi workshop có thể chia thành:

1. **Xác nhận scope và luồng hợp lệ:** product và engineering giải thích use case, data flow, quyền và những giả định.
2. **Đặt mục tiêu lạm dụng:** cả nhóm đưa ra actor, các biến thể đối tượng, trình tự, quyền và dữ liệu.
3. **Chọn đường đáng quan tâm:** ưu tiên kịch bản có tác động, điều kiện xảy ra và mức bất định đáng kể.
4. **Chốt invariant và control:** thống nhất nơi thực thi, owner và tiêu chí kiểm thử.
5. **Giao đầu ra:** tạo abuse case IDs, issue/requirements, test plan, thời hạn, điều kiện review lại.

Cần lưu **quyết định và các câu hỏi chưa trả lời**. Một cuộc họp tạo nhiều ý tưởng nhưng không có owner hay test plan sẽ khó chuyển thành assurance thực chất.

## 15. Duy trì abuse cases trong SDLC và vận hành

Threat model thay đổi cùng sản phẩm. Abuse cases nên được xem là tập giả thuyết bảo mật **có vòng đời**, không phải checklist chỉ làm một lần.

| Thời điểm | Hoạt động | Artifact/evidence |
|---|---|---|
| Ý tưởng/yêu cầu | Xem xét user journey và mục tiêu bất lợi | Abuse case candidates, security invariants |
| Thiết kế kiến trúc | Vẽ DFD, trust boundaries, review luồng async | Threat model, quyết định kiến trúc |
| Phát triển | Tạo requirements, security tests, code review | Issue, pull request, test report |
| CI/CD và release | Kiểm tra gate, build và cấu hình liên quan | Pipeline result, config snapshot, deployment proof |
| Vận hành | Theo dõi abuse signals, quyền, drift và sự cố | Log/alert, incident ticket, review control |
| Khắc phục | Sửa root cause, mở rộng test để ngăn tái diễn | Finding, fix evidence, retest |
| Thay đổi lớn | Cập nhật actor, data flow, trust boundary, tenant, nhà cung cấp | Model version mới, delta assessment |

### Trigger tái đánh giá

- Thêm endpoint export, chức năng bulk, tính năng chia sẻ hoặc quyền support mới.
- Dùng queue/worker mới, đổi storage, link tải hoặc policy khi quyền bị thu hồi.
- Thêm tenant, phân tách vùng dữ liệu, loại thông tin nhạy cảm hoặc bên thứ ba.
- Đổi quy trình đăng nhập, refresh/reset token, session hoặc cơ chế authorization.
- Xuất hiện finding phân quyền, báo cáo lạm dụng, incident hoặc dấu hiệu thử tấn công.
- Thay cấu hình network/IAM, thay SLA, hợp đồng hoặc nghĩa vụ tuân thủ liên quan.
- Một assumption quan trọng không còn đúng hoặc một control bù trừ thất bại.

Khi có trigger, không cần viết lại toàn bộ threat model từ đầu; ưu tiên đánh giá **những abuse paths bị ảnh hưởng** và cập nhật requirement, test, evidence, residual risk.

## 16. Các sai lầm thường gặp

**“Abuse case là danh sách kỹ thuật tấn công.”** Chưa đủ. Kịch bản cần mô tả actor, chức năng, tiền đề, kết quả xấu và yêu cầu kiểm chứng gắn với tài sản.

**“Đã đăng nhập nghĩa là được phép xem mọi dữ liệu mà API trả được.”** Sai. Authentication xác minh danh tính, còn authorization xác định quyền đối với hành động và đối tượng cụ thể.

**“Giao diện ẩn nút thì không thể abuse.”** Sai. API, worker, integration hoặc đường tải khác vẫn có thể nhận request; control cần thực thi ở ranh giới tin cậy phù hợp.

**“Một request bị từ chối chứng minh dữ liệu không bị lộ.”** Chưa chắc. Side effects và luồng bất đồng bộ có thể tạo file hoặc dữ liệu trước khi trả lỗi.

**“Threat model đã duyệt một lần thì không cần cập nhật.”** Không đúng khi actor, data flow, tài sản hoặc control thay đổi. Cần trigger review và evidence mới.

**“Số lượng abuse cases càng lớn thì bảo mật càng tốt.”** Không tự động. Chất lượng, độ phủ những rủi ro quan trọng và khả năng nối thành test/control quan trọng hơn số lượng.

**“Có WAF, SIEM hoặc SAST nên không cần kiểm tra lạm dụng nghiệp vụ.”** Những công cụ này có thể không hiểu quy tắc “giảng viên chỉ xem lớp mình” hay “mỗi giao dịch chỉ được hoàn tiền một lần”. Cần test đúng invariant nghiệp vụ.

**“Không có incident là bằng chứng kịch bản không xảy ra.”** Không đủ nếu log hoặc năng lực phát hiện chưa được xác minh.

**“Mọi abuse case đều phải sửa bằng một control.”** Một kịch bản có thể cần các lớp phòng ngừa, phát hiện, phản ứng và khôi phục; mỗi control có thể phục vụ nhiều kịch bản.

**“Đã chạy test một lần là không còn residual risk.”** Kết quả test có phạm vi và thời điểm, không loại bỏ mọi bất định. Risk owner cần biết giới hạn và rủi ro còn lại.

## 17. Bài tập thực hành

### Bài tập A — Từ use case sang abuse case

**Use case:** học viên có thể tải bài tập đã nộp của mình; giảng viên có thể tải bài nộp của học viên thuộc lớp đang được giao.

Hãy viết **ít nhất ba abuse cases** khác nhau. Với mỗi case, nêu:

1. Actor và quyền ban đầu.
2. Entry point và tài sản bị ảnh hưởng.
3. Preconditions và hành vi lạm dụng ở mức nghiệp vụ.
4. Ranh giới tin cậy bị thử vượt qua.
5. Hậu quả không mong muốn và security invariant.
6. Control, negative test và bằng chứng cần thu thập.

**Gợi ý:** thử đọc bài nộp của học viên khác; thử dùng link tải sau khi quyền lớp bị thu hồi; thử lạm dụng cơ chế chia sẻ file ngoài đối tượng được phép. Đừng mặc định có lỗ hổng khi chưa test.

### Bài tập B — Đánh giá abuse case chưa đủ cụ thể

Một tài liệu viết:

> AB-12: Hacker có thể hack hệ thống để lấy dữ liệu. Mức độ: Critical. Khắc phục: dùng WAF.

Hãy chỉ ra những thông tin còn thiếu và viết lại dưới dạng abuse case có thể kiểm chứng.

**Định hướng:** Cần xác định use case, dữ liệu/tài sản, actor và quyền, điểm vào, hành vi lạm dụng, ranh giới, hậu quả, lý do đánh giá likelihood/impact, control cần thiết và test. Nếu kịch bản là truy cập chéo tenant, WAF không mặc nhiên thay thế authorization phía server.

### Bài tập C — Threat modeling cho luồng quên mật khẩu

Hệ thống Java gửi reset link vào email khi người dùng yêu cầu. Hãy mô tả:

- Use case bình thường.
- Hai abuse cases liên quan **account enumeration** và **reset token replay**.
- Các security invariants cho response, token, thay đổi mật khẩu và trạng thái session.
- Test case cho tài khoản hợp lệ/không tồn tại, token đã dùng, token hết hạn và request lặp.
- Bằng chứng cần lưu theo build, test data, trạng thái token và log có kiểm soát.

**Gợi ý:** Không cần đặt TTL chung cho mọi hệ thống; cần định nghĩa theo chính sách rủi ro và kiểm chứng thực tế. Tránh ghi token hoặc dữ liệu xác thực vào bản evidence chia sẻ.

### Bài tập D — Kiểm tra khả năng truy vết assurance

Nhóm sản phẩm báo “đã xử lý AB-EXPORT-01” vì có một unit test trả 403. Hãy liệt kê các câu hỏi trước khi chấp nhận claim:

- Unit test có dùng chính sách phân quyền và dữ liệu tương đương thực tế không?
- Các tuyến controller, worker, storage, mobile và batch có được bao phủ?
- Có tác vụ/file ngoài quyền được tạo trong lúc test không?
- Kết quả thuộc phiên bản nào; có evidence bản đó chạy trên production?
- Đường log và alert có hoạt động trong kỳ đánh giá?
- Có tài khoản ngoại lệ, quyền support hoặc truy cập khẩn cấp chưa kiểm tra?
- Finding cũ đã retest và còn hạn chế nào phải báo risk owner?

**Kết luận gợi ý:** Test 403 là một phần evidence, chưa đủ để kết luận mọi đường export production đã bảo vệ dữ liệu theo security invariant.

## 18. Checklist chất lượng abuse case

Một abuse case đủ tốt để đưa vào threat model và chương trình assurance nên trả lời được:

- [ ] Chức năng/use case hợp lệ bị lạm dụng được xác định.
- [ ] Actor có năng lực và quyền ban đầu rõ; không dùng mô tả “hacker” chung chung.
- [ ] Tài sản, mục tiêu bảo mật và hậu quả được diễn giải bằng ngôn ngữ nghiệp vụ.
- [ ] Preconditions, entry point và trust boundaries có thể đối chiếu với kiến trúc.
- [ ] Đường hành vi và kết quả xấu đủ cụ thể để thiết kế kiểm thử.
- [ ] Đã tách giả định khỏi điều đã quan sát hoặc kiểm chứng.
- [ ] Có security invariant, requirements và controls liên quan.
- [ ] Test mô tả tiền đề, expected result, side effects, logging và evidence.
- [ ] Có owner, risk priority theo tiêu chí và trạng thái finding/remediation.
- [ ] Phạm vi, phiên bản, thời kỳ và giới hạn của kết luận được ghi.
- [ ] Có trigger để cập nhật khi actor, quyền, data flow hoặc control thay đổi.
- [ ] Các yêu cầu pháp lý/hợp đồng hoặc quyền riêng tư liên quan được đưa vào đánh giá khi áp dụng.

Checklist giúp rà soát **độ hoàn chỉnh của phân tích**, không phải giấy chứng nhận hệ thống an toàn chỉ vì đã điền đủ ô.

## 19. Ghi nhớ

- **Abuse case mô tả cách chức năng hoặc quy trình bị lạm dụng để tạo kết quả trái mục tiêu bảo mật**, với actor, tiền đề, ranh giới và tác động rõ ràng.
- Abuse case giúp mở rộng use case hợp lệ bằng **security invariants**: điều hệ thống phải luôn ngăn, bảo vệ hoặc phát hiện.
- Kịch bản cần nối được chuỗi **abuse case → risk → security requirement → control → test/evidence → assurance claim → residual risk**.
- Kiểm thử phải xem xét **đường end-to-end và side effects**, không chỉ trạng thái HTTP hay một màn hình giao diện.
- Bằng chứng có **phạm vi, thời kỳ và giới hạn**; thiếu bằng chứng không được biến thành kết luận “đạt”.
- Threat modeling và abuse case review là hoạt động **có vòng đời**, được cập nhật khi sản phẩm, dữ liệu, quyền truy cập, kiến trúc, sự cố hoặc nghĩa vụ thay đổi.

