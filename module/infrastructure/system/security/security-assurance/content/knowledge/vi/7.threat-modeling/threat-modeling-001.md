# Threat modeling là gì?

## 1. Khái niệm và mục đích

**Threat modeling** (mô hình hóa mối đe dọa) là hoạt động **phân tích có cấu trúc một hệ thống hoặc quy trình** để hiểu điều cần bảo vệ, cách hệ thống vận hành, những tình huống có thể gây hại và biện pháp cần có để giảm rủi ro. Nhóm thực hiện thường mô tả kiến trúc, luồng dữ liệu, ranh giới tin cậy (*trust boundaries*), mục tiêu của đối tượng tấn công, các điểm yếu giả định và hậu quả kinh doanh.

Ví dụ, trước khi xây dựng API tra cứu đơn hàng, nhóm đặt câu hỏi: **“Điều gì ngăn khách hàng A thay ID trong URL để đọc đơn hàng của khách hàng B?”** Câu hỏi này có thể dẫn đến yêu cầu kiểm tra phân quyền theo từng đơn hàng, thiết kế truy vấn giới hạn theo chủ sở hữu và kiểm thử truy cập chéo tài khoản.

Threat modeling có thể thực hiện **trước khi viết mã, trong lúc thay đổi kiến trúc và khi hệ thống đang vận hành**. Nhờ đó, nhóm phát hiện giả định thiết kế sai sớm và chọn đúng những kiểm tra cần bổ sung.

Trong module **SECURITY_SECURITY_ASSURANCE**, threat modeling là một nguồn đầu vào quan trọng cho **security assurance liên tục**: kết quả mô hình hóa phải có thể truy vết từ **rủi ro → yêu cầu → security control → kiểm thử/audit → bằng chứng → phát hiện và khắc phục**. Bản threat model không tự chứng minh hệ thống an toàn; nó cung cấp một cách lập luận có hệ thống để xác định **cần chứng minh điều gì**.

### 1.1. Bốn câu hỏi nền tảng

Một cách tiếp cận đơn giản và hữu ích là đặt bốn câu hỏi:

1. **Chúng ta đang xây dựng hoặc vận hành điều gì?** Tài sản, kiến trúc, người dùng, luồng dữ liệu, hệ thống bên ngoài và ranh giới tin cậy ra sao?
2. **Điều gì có thể xảy ra theo hướng bất lợi?** Ai/cái gì có thể tác động lên tài sản, qua đường nào, với điều kiện và hậu quả nào?
3. **Chúng ta sẽ xử lý như thế nào?** Ngăn ngừa, phát hiện, hạn chế, phục hồi hoặc quyết định xử lý rủi ro còn lại ra sao?
4. **Chúng ta đã làm đủ tốt chưa?** Security controls có tiêu chí đo rõ và bằng chứng kiểm chứng được hay không; threat model có được cập nhật theo thay đổi hay không?

Bốn câu hỏi tạo ra một vòng lặp, không phải một biểu mẫu điền xong rồi cất đi.

### 1.2. Threat modeling tạo ra giá trị gì?

| Giá trị | Cơ chế | Kết quả có thể quan sát |
| --- | --- | --- |
| Nhìn thấy rủi ro từ lúc thiết kế | Phân tích luồng dữ liệu, trust boundary và các kịch bản lạm dụng | Yêu cầu bảo mật được bổ sung trước khi phát hành |
| Tập trung vào rủi ro theo nghiệp vụ | Hỏi điều gì có thể gây hại với dữ liệu và quy trình quan trọng | Ưu tiên kiểm soát thay vì quét lỗi không có ngữ cảnh |
| Tăng sự phối hợp giữa nhóm | Developer, kiến trúc, security, vận hành và chủ nghiệp vụ xem cùng một mô hình | Các giả định và trách nhiệm được ghi rõ |
| Cải thiện chất lượng kiểm thử | Chuyển từng kịch bản thành *security claim* và ca kiểm thử | Test từ chối truy cập, thử thất bại thành phần phụ thuộc |
| Hỗ trợ assurance, audit | Lưu lý do thiết kế control và liên kết đến bằng chứng | Có thể truy vết threat, requirement, control, test và kết quả |
| Duy trì hiệu quả sau thay đổi | Đánh giá lại khi thêm endpoint, role, dữ liệu hoặc nhà cung cấp | Nhận ra các threat mới và kiểm tra lại control bị ảnh hưởng |

Threat modeling **không bảo đảm tìm ra mọi kịch bản tấn công** và không thay thế triển khai control, kiểm thử thực tế, quản lý lỗ hổng hay ứng cứu sự cố.

## 2. Threat modeling khác những hoạt động liên quan như thế nào?

Các hoạt động thường hỗ trợ lẫn nhau nhưng trả lời những câu hỏi khác nhau:

| Hoạt động | Câu hỏi chính | Đầu ra điển hình |
| --- | --- | --- |
| **Threat modeling** | Với hệ thống và tài sản này, những kịch bản bất lợi nào có thể xảy ra và cần control gì? | Sơ đồ kiến trúc, threat scenario, giả định, yêu cầu và biện pháp |
| **Risk assessment** | Kịch bản đó đáng quan tâm đến mức nào, khả năng xảy ra và tác động ra sao? | Mức rủi ro, độ tin cậy, phương án xử lý, risk owner |
| **Vulnerability assessment** | Những điểm yếu đã biết hoặc có thể phát hiện đang tồn tại ở đâu? | Danh sách phát hiện và bằng chứng kiểm tra |
| **Penetration testing** | Trong phạm vi và điều kiện được phép, có thể khai thác những đường tấn công nào trên hệ thống thực? | Kịch bản thử, bằng chứng kết quả, mức ảnh hưởng và kiến nghị |
| **Secure design/code review** | Thiết kế hoặc mã triển khai có đáp ứng tiêu chí an toàn không? | Nhận xét về thiết kế/mã, điểm thiếu, đề xuất sửa |
| **Security assurance** | Những mục tiêu bảo mật đã đặt ra có được đáp ứng với bằng chứng đủ tin cậy không? | Security claims, bằng chứng, kết luận có phạm vi và phát hiện cần xử lý |

Ví dụ, một công cụ quét có thể không nhận diện quy tắc nghiệp vụ “A không được xem dữ liệu B”. Threat modeling giúp **nêu ra** kịch bản này; nhóm thiết kế **control phân quyền**; kiểm thử tích hợp hoặc pentest **kiểm chứng** hành vi; risk assessment và security assurance **đánh giá mức rủi ro và chất lượng bằng chứng**.

Threat modeling có thể thực hiện mà không có công cụ chuyên dụng. Đầu ra quan trọng hơn loại phần mềm dùng để vẽ sơ đồ.

## 3. Những thành phần cần được mô hình hóa

Một threat model có ích phải mô tả **hệ thống cụ thể**, không chỉ danh sách các kiểu tấn công phổ biến.

### 3.1. Tài sản và mục tiêu bảo mật

**Asset** có thể là dữ liệu khách hàng, token, khóa ký, dữ liệu giao dịch, tính sẵn sàng của API, quyền quản trị hoặc tính toàn vẹn của pipeline triển khai.

Đặt câu hỏi: dữ liệu này nhạy cảm tới đâu, ai được phép sử dụng, có thể bị sửa hoặc bị mất thế nào, tổn thất nào khiến doanh nghiệp lo ngại?

Gắn tài sản với mục tiêu bảo mật:

- **Bí mật (Confidentiality):** ngăn truy cập và tiết lộ trái phép.
- **Toàn vẹn (Integrity):** ngăn sửa/xóa/giả mạo trái phép.
- **Sẵn sàng (Availability):** duy trì dịch vụ và khả năng phục hồi.
- **Tính xác thực, truy vết và trách nhiệm giải trình:** biết ai thực hiện thao tác, có khả năng xác minh khi điều tra.
- **Quyền riêng tư và nghĩa vụ áp dụng:** xử lý dữ liệu đúng quyền, mục đích và phạm vi.

### 3.2. Các thành phần trong sơ đồ luồng dữ liệu

Một cách biểu diễn thông dụng là **Data Flow Diagram (DFD)**:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **External entity** | Tác nhân hoặc hệ thống ngoài phạm vi xử lý đang xét | Trình duyệt khách hàng, hệ thống đối tác |
| **Process** | Thành phần xử lý dữ liệu | API Spring Boot, dịch vụ tính phí |
| **Data store** | Nơi lưu dữ liệu | Database đơn hàng, object storage |
| **Data flow** | Dữ liệu và lệnh được truyền giữa các thành phần | Request HTTP, sự kiện trên message queue |
| **Trust boundary** | Nơi thay đổi giả định tin cậy hoặc phạm vi kiểm soát | Internet → gateway; gateway → ứng dụng; ứng dụng → hệ thống đối tác |

**Trust boundary** không đồng nghĩa với “có firewall” hay “mạng nội bộ chắc chắn an toàn”. Đây là ranh giới mà nhóm cần làm rõ: danh tính và thông tin nào còn đáng tin, cần xác thực hoặc phân quyền lại ở đâu, ai kiểm soát thành phần phía bên kia và sự cố của nó có tác động gì.

Các luồng quan trọng nên nêu dữ liệu gì đi qua, giao thức nào được dùng, đầu gửi/nhận, vị trí lưu và mức tin cậy. Đừng giả định một request trở nên đáng tin chỉ vì đã qua API gateway.

### 3.3. Điểm vào, mối đe dọa và giả định

Ngoài DFD, cần xác định:

- **Entry points:** API công khai, form, webhook, upload, admin console, cron job, queue, CI/CD.
- **Threat sources/actors:** người dùng bên ngoài, người nội bộ, nhà cung cấp, lỗi vô ý, hỏng hóc và sự kiện môi trường.
- **Threat events:** giả mạo token, sửa tham số, gửi request quá tải, đọc dữ liệu vượt quyền, làm sai chuỗi cung ứng.
- **Preconditions và vulnerabilities:** điều kiện để sự kiện có thể gây hại; những điểm yếu đã biết hoặc mới là giả thuyết.
- **Control hiện hữu:** xác thực, phân quyền, mã hóa, phân đoạn mạng, kiểm tra đầu vào, rate limit, log, sao lưu và ứng cứu.
- **Assumptions:** điều nhóm đang tin nhưng chưa có bằng chứng, chẳng hạn “mọi endpoint đều áp dụng chung middleware phân quyền”.

Một mô hình tốt **phân biệt rõ sự thật đã kiểm chứng với giả định**. Nếu chưa có dữ liệu chứng minh gateway bảo vệ một endpoint mới, ghi “cần xác minh”, không coi đó là một control hoạt động.

## 4. Quy trình threat modeling từng bước

### Bước 1. Xác định mục tiêu, phạm vi và người tham gia

Trước khi vẽ sơ đồ, thống nhất:

1. **Đối tượng đánh giá:** dịch vụ, tính năng, luồng nghiệp vụ hoặc thay đổi kiến trúc nào?
2. **Giới hạn phạm vi:** môi trường, phiên bản, các tích hợp và dữ liệu liên quan.
3. **Mục tiêu bảo mật:** bí mật, toàn vẹn, sẵn sàng và các nghĩa vụ cần đạt.
4. **Thông tin đầu vào:** tài liệu kiến trúc, mô tả nghiệp vụ, hợp đồng API, cấu hình, lịch sử sự cố, kết quả test/audit nếu có.
5. **Vai trò:** ai biết nghiệp vụ, ai hiểu kỹ thuật, ai hỗ trợ phân tích threat, ai quyết định rủi ro còn lại.
6. **Tiêu chí hoàn tất:** đầu ra và bằng chứng tối thiểu để một vòng mô hình hóa được xem là đủ phục vụ quyết định.

Ví dụ, yêu cầu “threat model toàn bộ doanh nghiệp trong một cuộc họp” thường quá rộng. Có thể bắt đầu với luồng **khách hàng đăng nhập → xem đơn hàng → thanh toán**, rồi mở rộng các thành phần phụ thuộc theo rủi ro.

### Bước 2. Vẽ mô hình hệ thống và xác nhận thực tế

Sơ đồ không cần đẹp nhưng phải thể hiện đúng đường dữ liệu và ranh giới tin cậy quan trọng. Nhóm kỹ thuật và vận hành nên xác nhận kiến trúc hiện tại, nhất là những phần khác môi trường thử nghiệm hoặc tài liệu ban đầu.

Đầu ra tối thiểu gồm: các thành phần, những luồng nhạy cảm, điểm vào, dữ liệu lưu trữ, quyền/identity được truyền và boundary cần kiểm tra.

Ví dụ, đừng chỉ vẽ “người dùng → API → database” khi một token thực tế còn đi qua gateway, nhà cung cấp danh tính và một service nội bộ được phép gọi API.

### Bước 3. Nhận diện threat theo từng thành phần và boundary

Đặt câu hỏi có hệ thống, chẳng hạn bằng **STRIDE** (xem mục 5), các *abuse/misuse cases*, cây tấn công hoặc cách tiếp cận dựa trên tài sản. Cần xét:

- Một người dùng có thể giả làm chủ thể khác không?
- Có thể sửa dữ liệu, tham số, sự kiện hoặc artifact trái phép không?
- Thao tác quan trọng có đủ log để điều tra không?
- Dữ liệu có thể bị lộ khi truyền, lưu hoặc trả response không?
- Có thể làm cạn CPU, database connections, queue hoặc dịch vụ phụ thuộc không?
- Vai trò thấp có thể đạt quyền quản trị, đi vòng qua check quyền hoặc lợi dụng service-to-service trust không?
- Những lỗi vô ý, hỏng hóc và sai cấu hình có thể ảnh hưởng mục tiêu nào?

**Không dừng ở nhãn** như “spoofing”, “IDOR” hoặc “DoS”. Mỗi mục phải có một kịch bản với đầu vào, bước gây hại, tiền đề và hậu quả đủ rõ để kiểm thử hoặc đánh giá.

### Bước 4. Viết threat scenario cụ thể

Một cấu trúc tham khảo:

> **[Nguồn đe dọa]** có thể thực hiện **[hành động]** qua **[đường vào/luồng]** nếu **[điều kiện/điểm yếu]**, khiến **[tài sản]** chịu **[hậu quả]**. Control cần có là **[biện pháp]**; việc đáp ứng được kiểm tra bằng **[bằng chứng]**.

Ví dụ: “Người dùng đã đăng nhập thay ID đơn hàng trên API. Nếu dịch vụ chỉ kiểm tra token hợp lệ mà không xác minh quyền trên bản ghi, người này có thể đọc thông tin khách hàng khác. Cần có kiểm tra phân quyền cấp đối tượng và test tích hợp bằng hai tài khoản tách biệt.”

Những điều **chưa biết** phải được ghi riêng: “Chưa xác minh API hiện kiểm tra theo owner hay không”, “Chưa biết endpoint export có dùng chung chính sách phân quyền”.

### Bước 5. Ưu tiên theo rủi ro và đề xuất xử lý

Không phải threat nào cũng có khả năng và hậu quả giống nhau. Đánh giá bối cảnh:

- **Khả năng xảy ra / likelihood:** đường tiếp cận có hiện hữu, kẻ tấn công cần quyền gì, tiền đề có được xác minh, control hiện có hoạt động không?
- **Tác động / impact:** dữ liệu bị lộ/sửa/xóa, dịch vụ gián đoạn, ảnh hưởng khách hàng, nghĩa vụ và hoạt động kinh doanh.
- **Mức độ tin cậy / confidence:** đánh giá dựa trên test thực tế, cấu hình đang chạy hay suy luận chưa xác minh?
- **Rủi ro còn lại:** sau khi áp dụng những control **đã được kiểm chứng**, còn khả năng và hậu quả gì?

Có thể dùng thang định tính Thấp/Trung bình/Cao theo tiêu chí của tổ chức. **STRIDE là phương pháp tìm nhóm threat, không phải thang xếp severity**. Không suy mức “Cao” chỉ vì threat có tên đáng sợ hoặc mức “Thấp” vì chưa thấy log tấn công.

Phương án xử lý có thể là giảm thiểu, tránh, chia sẻ/chuyển giao một phần hoặc chấp nhận rủi ro theo quy trình. Quyền **chấp nhận residual risk** thuộc risk owner hoặc cấp có thẩm quyền; người vẽ threat model hoặc người triển khai control không tự động có quyền này.

### Bước 6. Biến kịch bản thành yêu cầu, control và kiểm thử

Đây là bước tạo giá trị lớn cho security assurance: với mỗi threat đáng quan tâm, xác định **security claim** có thể chứng minh.

| Threat scenario | Security requirement/claim | Control | Bằng chứng cần lấy |
| --- | --- | --- | --- |
| A đọc đơn hàng của B bằng cách thay ID | Mọi lần đọc đơn hàng phải kiểm tra quyền theo đối tượng | Authorization ở tầng nghiệp vụ/dữ liệu | Test âm A/B, review các endpoint và truy vấn |
| Token bị giả mạo hoặc được dùng sai đối tượng | Chỉ token hợp lệ, đúng issuer/audience và phạm vi mới được chấp nhận | Kiểm tra token, issuer, audience, expiry và quyền | Test token không hợp lệ, cấu hình xác thực, security review |
| Dữ liệu bị sửa trái phép trong sự kiện queue | Người gửi và thông điệp được xác thực, dữ liệu nghiệp vụ được kiểm tra | Service identity, authorization, integrity validation | Test publisher không có quyền, log xử lý và review |
| Chức năng xuất dữ liệu làm cạn tài nguyên | Có giới hạn phù hợp và khả năng xử lý quá tải | Rate limit, quota, timeout, queue và giới hạn đồng thời | Load/abuse test, telemetry và cảnh báo |
| Thao tác quản trị không truy vết được | Hành động trọng yếu có audit trail phù hợp | Event logging, phân quyền log, retention | Kiểm thử audit event và xác minh quyền truy cập log |
| Backup không phục hồi được sau sự cố | Dữ liệu và dịch vụ đáp ứng mục tiêu khôi phục đã phê duyệt | Backup và diễn tập restore | Kết quả restore trên phạm vi phù hợp |

Cần kiểm chứng cả **design effectiveness** (thiết kế có giải quyết rủi ro không) và **operating effectiveness** (trên hệ thống thực tế control có đang vận hành như thiết kế không). Sơ đồ và biên bản threat modeling là bằng chứng của **hoạt động phân tích thiết kế**, chưa phải bằng chứng rằng mọi control đã chạy đúng ở production.

### Bước 7. Ghi nhận, theo dõi và đánh giá lại

Lưu mô hình và quyết định để lần thay đổi tiếp theo có thể biết:

- Phiên bản hệ thống, thời điểm, phạm vi và người tham gia.
- Threat scenario, ID, nguồn đe dọa, tài sản và hậu quả.
- Các giả định, giới hạn, độ tin cậy và câu hỏi chưa trả lời.
- Mức ưu tiên, risk owner, control owner và action owner.
- Requirement, control, test, kết quả và nơi lưu bằng chứng.
- Phát hiện, kế hoạch sửa, kết quả kiểm thử lại và quyết định liên quan.
- Trigger tái đánh giá: thay đổi code/role, thêm API, nâng cấp phụ thuộc, thay môi trường, sự cố hoặc phát hiện audit.

Threat modeling cần cập nhật theo **hệ thống thực**, không chỉ theo bản vẽ kiến trúc đầu tiên.

## 5. STRIDE: công cụ gợi mở khi tìm threat

**STRIDE** giúp kiểm tra sáu nhóm tình huống an ninh thường gặp. Có thể dùng câu hỏi STRIDE cho thành phần, luồng dữ liệu hoặc ranh giới tin cậy phù hợp; không nhất thiết mọi mục đều áp dụng giống nhau lên mọi đối tượng.

| Nhóm | Câu hỏi dẫn dắt | Ví dụ | Điều nên kiểm chứng |
| --- | --- | --- | --- |
| **S — Spoofing** (giả mạo) | Có thể giả làm người dùng hay service khác không? | Dùng token giả hoặc service identity bị đánh cắp | Cơ chế xác thực, kiểm tra token và danh tính service |
| **T — Tampering** (sửa đổi trái phép) | Có thể sửa thông điệp, dữ liệu hoặc cấu hình trái phép không? | Thay giá bán trong request rồi server tin trực tiếp | Xác minh dữ liệu nghiệp vụ, toàn vẹn và quyền sửa |
| **R — Repudiation** (chối bỏ) | Người thực hiện thao tác quan trọng có thể phủ nhận vì không có bằng chứng không? | Hoàn tiền nhưng không có audit trail | Log đúng sự kiện, thời gian và kiểm soát truy cập log |
| **I — Information disclosure** (lộ dữ liệu) | Dữ liệu nhạy cảm có bị tiết lộ ngoài quyền không? | Đọc đơn hàng của tài khoản khác | Phân quyền, dữ liệu trong response và log |
| **D — Denial of service** (mất khả dụng) | Có thể làm cạn tài nguyên hoặc dịch vụ phụ thuộc không? | Tạo nhiều báo cáo nặng khiến DB quá tải | Quota, rate limit, backpressure, timeout, load test |
| **E — Elevation of privilege** (leo thang quyền) | Có thể đạt quyền cao hơn quyền được cấp không? | Người dùng thường gọi API quản trị | Kiểm tra authorization theo chức năng, role và tài nguyên |

### 5.1. STRIDE không phải danh sách lỗi đầy đủ

STRIDE giúp nhóm đặt câu hỏi, nhưng vẫn có những mối quan tâm cần cách tiếp cận bổ sung, như:

- **An toàn dữ liệu và quyền riêng tư:** thu thập quá mức, mục đích xử lý, lưu trữ lâu hơn cần thiết.
- **Chuỗi cung ứng:** artifact bị thay đổi, dependency bị cài mã độc, quyền pipeline CI/CD.
- **Nghiệp vụ:** lợi dụng hoàn tiền, điểm thưởng, thao tác trùng lặp, race condition.
- **Con người và môi trường:** xóa nhầm, gửi nhầm dữ liệu, mất điện và thiên tai.
- **Khả năng phục hồi:** thiếu phương án khôi phục hoặc phụ thuộc vào một dịch vụ duy nhất.

Sử dụng STRIDE như **bộ câu hỏi dẫn dắt**, rồi bổ sung theo loại tài sản, mô hình vận hành và nghĩa vụ của tổ chức.

## 6. Một số kỹ thuật threat modeling khác

Không có một kỹ thuật duy nhất tối ưu trong mọi bối cảnh.

| Kỹ thuật | Cách tiếp cận | Phù hợp khi |
| --- | --- | --- |
| **STRIDE dựa trên DFD** | Từ thành phần, dữ liệu và ranh giới tin cậy, hỏi theo sáu nhóm threat | Ứng dụng, API, service và kiến trúc có nhiều luồng dữ liệu |
| **Attack tree** (cây tấn công) | Bắt đầu từ mục tiêu bất lợi, phân rã thành các bước/điều kiện để đạt mục tiêu | Phân tích sâu một mục tiêu như chiếm tài khoản hoặc gian lận |
| **Misuse/abuse cases** | Viết tình huống đối lập với use case bình thường của người dùng | Ứng dụng có quy tắc nghiệp vụ phức tạp |
| **PASTA** | Tiếp cận theo quy trình có cấu trúc, lấy tác động kinh doanh và rủi ro làm trung tâm | Dự án cần liên kết chặt threat với đánh giá rủi ro |
| **LINDDUN** | Hỗ trợ nhận diện mối đe dọa đến quyền riêng tư và liên kết dữ liệu | Sản phẩm xử lý dữ liệu cá nhân, luồng phân tích và chia sẻ dữ liệu |

Có thể kết hợp: dùng DFD/STRIDE để rà soát diện rộng, chọn một kịch bản có tác động cao rồi dựng attack tree, sau đó dùng risk assessment để quyết định thứ tự xử lý. Điều quan trọng là **phạm vi, giả định, kết luận và hành động** được ghi đủ rõ để tái kiểm tra.

## 7. Ví dụ xuyên suốt: threat modeling dịch vụ Orders API dùng Java/Spring Boot

Giả sử một nền tảng thương mại điện tử có:

- Ứng dụng web cho khách hàng.
- API gateway tiếp nhận HTTP request.
- Orders API viết bằng Java/Spring Boot.
- Identity Provider (IdP) phát token đăng nhập.
- Cơ sở dữ liệu lưu đơn hàng.
- Message queue phát sự kiện cập nhật trạng thái đơn cho worker thanh toán.

### 7.1. Mô hình và ranh giới tin cậy

~~~mermaid
flowchart LR
    subgraph Z1["Vùng người dùng / Internet - không tin cậy"]
        U["Trình duyệt khách hàng"]
    end
    subgraph Z2["Vùng tiếp nhận và xác thực request"]
        G["API Gateway"]
        I["Identity Provider"]
    end
    subgraph Z3["Vùng dịch vụ ứng dụng"]
        A["Orders API (Spring Boot)"]
        Q["Message Queue"]
        W["Billing Worker"]
    end
    subgraph Z4["Vùng lưu dữ liệu"]
        DB[("Orders Database")]
    end

    U -->|"HTTPS: token, orderId"| G
    G -->|"Forward request + security context"| A
    G <-->|"Xác minh/tra cứu danh tính khi cần"| I
    A -->|"Query theo quyền"| DB
    A -->|"Order event"| Q
    Q -->|"Consume event"| W
~~~

Các vùng trong sơ đồ là **đơn vị để thảo luận trust boundary**, không khẳng định hạ tầng thật có đúng số lớp mạng hoặc mức bảo vệ đó. Người làm threat model cần xác minh các luồng thực tế: token được kiểm tra ở đâu, API có xác thực lại không, dịch vụ nội bộ dùng identity nào, queue phân quyền người gửi/người nhận ra sao, và database cấp quyền cho tài khoản nào.

### 7.2. Tài sản, điểm vào và giả định cần kiểm tra

| Đối tượng | Mục tiêu bảo mật | Câu hỏi threat modeling |
| --- | --- | --- |
| Token và phiên đăng nhập | Chỉ danh tính hợp lệ được xác thực | Gateway/API có kiểm tra issuer, audience, expiry và chữ ký không? |
| Thông tin đơn hàng | Chỉ chủ thể được ủy quyền mới đọc/sửa | Có check quyền theo từng orderId, kể cả với đường export và batch? |
| Message queue | Chỉ service được phép mới gửi/nhận sự kiện | Có quyền theo topic/queue và chống giả mạo event không? |
| Orders Database | Bảo vệ tính bí mật/toàn vẹn, giới hạn đặc quyền | Tài khoản dịch vụ có quyền tối thiểu, truy vấn có ràng buộc dữ liệu? |
| Orders API và DB connection | Duy trì tính sẵn sàng | Request tốn tài nguyên có bị giới hạn không? |
| Audit trail | Truy vết thao tác quan trọng | Có log đủ thông tin nhưng tránh lộ token và dữ liệu nhạy cảm không? |

**Giả định thường nguy hiểm:** “Đã đăng nhập qua gateway nên API được phép truy cập mọi đơn hàng.” Xác thực chỉ xác nhận chủ thể, **không tự quyết định** quyền của họ trên một bản ghi cụ thể.

### 7.3. Lập các threat scenario có thể kiểm chứng

| ID | Kịch bản và hậu quả | Control dự kiến | Cách kiểm chứng |
| --- | --- | --- | --- |
| TM-01 | A thay orderId và đọc thông tin của B → lộ dữ liệu | Authorization theo từng đơn hàng | Test A/B qua API; review nơi truy xuất dữ liệu |
| TM-02 | Token không phù hợp audience/issuer vẫn được chấp nhận → giả mạo truy cập | Validate token đầy đủ, không tin header client tự khai | Test token sai issuer/audience, review security configuration |
| TM-03 | Service không có quyền phát event giả → sai trạng thái thanh toán | Service identity, phân quyền publish, kiểm tra integrity và trạng thái nghiệp vụ | Test publisher trái quyền, kiểm tra log và state machine |
| TM-04 | Yêu cầu tạo báo cáo liên tục gây cạn kết nối DB → gián đoạn đặt hàng | Timeout, rate limit, quota, giới hạn query/đồng thời | Load/abuse test và giám sát tài nguyên |
| TM-05 | Thao tác hoàn tiền không được ghi nhận → khó điều tra | Audit logging có bảo vệ log và chính sách retention | Test tạo audit event, review quyền sửa/xóa log |

Các kịch bản trên là **giả thuyết để thiết kế kiểm tra**, chưa phải phát hiện hoặc sự cố đã xác nhận. Với mỗi mục cần bổ sung người sở hữu, mức rủi ro theo tiêu chí tổ chức và trạng thái bằng chứng.

### 7.4. Phân tích chi tiết TM-01: truy cập chéo đơn hàng

Request minh họa:

~~~http
GET /api/orders/841
Authorization: Bearer <token-cua-khach-hang-A>
~~~

Giả sử đơn 841 thuộc khách hàng B. Nếu Orders API chỉ xác minh token hợp lệ mà lấy đơn theo ID bất kỳ, khách hàng A có thể đọc đơn B. Đây là một threat scenario về **information disclosure**, thường liên quan đến lỗi **broken object-level authorization** nếu được xác nhận.

**Security claim cần chứng minh:** “Chỉ chủ sở hữu hoặc chủ thể có quyền được ủy quyền theo chính sách mới được đọc đơn hàng.”

Ví dụ ở tầng service, truy vấn ràng buộc đơn hàng theo customer ID **lấy từ context xác thực đáng tin**, không lấy customer ID do client tự gửi:

~~~java
@Service
public class OrderReadService {
    private final OrderRepository orderRepository;
    private final CurrentCustomer currentCustomer;

    public OrderReadService(OrderRepository orderRepository,
                            CurrentCustomer currentCustomer) {
        this.orderRepository = orderRepository;
        this.currentCustomer = currentCustomer;
    }

    @Transactional(readOnly = true)
    public OrderView findById(long orderId) {
        long customerId = currentCustomer.customerId();

        return orderRepository.findByIdAndCustomerId(orderId, customerId)
            .map(OrderView::from)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
~~~

Đoạn mã chỉ minh họa **một phương án kiểm soát**; các kiểu OrderRepository, CurrentCustomer, OrderView cần được định nghĩa trong dự án. CurrentCustomer phải xác định khách hàng từ danh tính đã xác thực và được kiểm chứng. Ứng dụng cần có chính sách riêng cho các vai trò được ủy quyền; response 403 hoặc 404 phải nhất quán với chính sách API và yêu cầu hạn chế lộ thông tin.

**Ma trận kiểm thử tối thiểu:**

| Tình huống | Kết quả mong đợi |
| --- | --- |
| A đọc đơn do A sở hữu | Trả đúng dữ liệu đơn A |
| A đọc đơn B | Từ chối và không trả dữ liệu đơn B |
| Request thiếu hoặc sai xác thực | Từ chối |
| A được ủy quyền hợp lệ theo chính sách | Chỉ trả dữ liệu trong phạm vi được ủy quyền |
| A đã bị thu hồi quyền | Không tiếp tục cấp quyền sai |
| Endpoint export/list/batch cùng dùng dữ liệu | Mỗi đường truy cập kiểm tra quyền phù hợp |
| orderId không tồn tại | Không tiết lộ thông tin nhạy cảm |

Một ca test âm A/B đạt chỉ chứng minh **kịch bản đó trên phiên bản, cấu hình và môi trường đã kiểm tra**. Không được suy ra mọi endpoint hay mọi chính sách phân quyền đều đúng. Nhóm assurance cần đánh giá phạm vi và những giả định chưa xác minh.

### 7.5. Ví dụ ghi kết quả threat modeling

Mẫu sau chỉ là **hồ sơ minh họa**, chưa có test run thật:

~~~yaml
model_id: "TM-ORDERS-DEMO-001"
service: "orders-api"
scope:
  component: "Orders API va Orders Database"
  flow: "Khach hang xem don hang qua HTTP"
  environment: "Ban thiet ke truoc phat hanh"
threat:
  id: "TM-01"
  category: "Information disclosure"
  scenario: "Khach A truy cap orderId cua khach B"
  asset: "Du lieu don hang khach hang"
  assumption: "Can xac minh authorization cap doi tuong"
security_claim: "Chi chu the co quyen moi xem don hang"
requirements:
  - "REQ-ORD-AUTHZ-01"
controls:
  - "CTRL-ORD-AUTHZ-01"
evidence_plan:
  - "Review phan quyen theo luong doc don hang"
  - "Integration test A doc don cua B"
  - "Test tren build va cau hinh duoc trien khai"
evidence_status: "CHUA_XAC_MINH"
risk_owner: "Chu so huu san pham Orders"
control_owner: "Nguoi phu trach Orders API"
action_owner: "Nhom phat trien Orders"
next_action: "Review thiet ke va chay integration test"
~~~

Trong dự án thật, record cần thêm người đánh giá, thời gian, phiên bản, tham chiếu kiến trúc, liên kết đến kết quả test, đánh giá rủi ro và quyết định xử lý. Trạng thái **CHUA_XAC_MINH** thể hiện chính xác rằng thiết kế kiểm tra **chưa phải** bằng chứng kết quả.

## 8. Threat modeling liên kết với security assurance như thế nào?

Threat modeling có thể tạo **đầu vào và bằng chứng về quyết định thiết kế**, nhưng một chương trình assurance liên tục cần tiến xa hơn.

~~~mermaid
flowchart TD
    A["Mục tiêu kinh doanh, tài sản và kiến trúc"] --> B["Threat modeling: giả định và kịch bản"]
    B --> C["Đánh giá, ưu tiên rủi ro"]
    C --> D["Yêu cầu bảo mật và security claims"]
    D --> E["Thiết kế, triển khai security controls"]
    E --> F["Kiểm thử, review, audit, bằng chứng vận hành"]
    F --> G{"Bằng chứng đáp ứng claim?"}
    G -- "Thiếu" --> H["Bổ sung kiểm tra, đánh giá giới hạn"]
    H --> F
    G -- "Không đạt" --> I["Ghi phát hiện, sửa và kiểm thử lại"]
    I --> E
    G -- "Đạt trong phạm vi" --> J["Kết luận assurance, đánh giá residual risk"]
    J --> K["Theo dõi thay đổi, đánh giá lại threat model"]
    K --> B
~~~

### 8.1. Phân biệt bằng chứng của quy trình và bằng chứng của control

| Tài liệu/kết quả | Có thể hỗ trợ kết luận gì? | Không tự chứng minh điều gì? |
| --- | --- | --- |
| Sơ đồ DFD có người duyệt | Đã xem xét các thành phần, luồng và boundary được mô tả | Kiến trúc production hoàn toàn giống sơ đồ |
| Threat register có ID và owner | Kịch bản đã được nhận diện và phân công | Tất cả threat đã bị chặn |
| Biên bản review thiết kế | Các quyết định và giả định đã được thảo luận | Code đã thực thi đúng từng quyết định |
| Pull request và cấu hình | Control đã được triển khai trong artifact/phạm vi cụ thể | Control hoạt động trên mọi môi trường |
| Integration/security test | Kịch bản đã chạy có kết quả cụ thể | Các kịch bản chưa được kiểm tra đều an toàn |
| Bằng chứng vận hành/log | Một số hành vi và trạng thái control trong khoảng quan sát | Không có cảnh báo đồng nghĩa không có cuộc tấn công |
| Audit độc lập | Kết luận của bên đánh giá trong phạm vi, tiêu chí và thời điểm cụ thể | Toàn hệ thống an toàn vĩnh viễn |

Nhóm phải gắn mỗi **security claim** với bằng chứng phù hợp, kiểm tra **tính liên quan, độ bao phủ, tính hiện hành và khả năng truy vết**. Bằng chứng cũ hoặc từ môi trường khác không mặc định hợp lệ cho phiên bản mới.

### 8.2. Khi phát hiện control không đáp ứng threat

Quy trình xử lý nên gồm:

1. **Xác nhận** sai lệch trên môi trường, phiên bản và kịch bản cụ thể.
2. **Đánh giá tác động, độ phơi nhiễm và risk**, phối hợp risk owner và security.
3. **Giao action owner** khắc phục, chọn biện pháp giảm thiểu tạm thời khi cần.
4. **Kiểm thử lại** cả kịch bản thất bại và những đường truy cập liên quan.
5. **Cập nhật threat register, risk register và bằng chứng**, ghi rõ quyết định theo thẩm quyền.
6. **Đưa test hồi quy** vào quy trình thay đổi/CI nếu phù hợp.

**Đóng ticket không đồng nghĩa đã khắc phục** nếu bản sửa chưa được xác minh. Risk owner hoặc cấp có quyền mới được phê duyệt chấp nhận rủi ro còn lại; threat modeler và control owner cung cấp thông tin phục vụ quyết định.

## 9. Ai nên tham gia threat modeling?

Threat modeling thường là một **buổi làm việc liên chức năng**, do nhóm hiểu hệ thống sở hữu nội dung và được chuyên gia an ninh hướng dẫn. Không nhất thiết tất cả bên liên quan dự mọi cuộc họp, nhưng cần đúng người cho các giả định quan trọng.

| Vai trò | Đóng góp | Trách nhiệm sau buổi làm việc |
| --- | --- | --- |
| **Kiến trúc sư / tech lead** | Mô tả kiến trúc, boundary, sự phụ thuộc và quyết định thiết kế | Bảo đảm mô hình phản ánh cấu trúc kỹ thuật |
| **Developer** | Giải thích luồng thực thi, kiểm tra quyền, xử lý lỗi và đầu vào | Triển khai control, viết test theo threat |
| **Security architect / analyst** | Hướng dẫn phương pháp, đặt câu hỏi phản biện, nhận diện đường tấn công | Xem chất lượng threat scenario và tiêu chí kiểm tra |
| **SRE / vận hành** | Cung cấp cấu hình chạy, log, giám sát, dependency và phục hồi | Kiểm tra control vận hành, theo dõi thay đổi |
| **Product/data owner** | Giải thích nghiệp vụ, loại dữ liệu, hậu quả và hành vi lạm dụng | Định hướng yêu cầu và tác động kinh doanh |
| **Risk owner** | Xác định mức chấp nhận, lựa chọn xử lý và quyết định trong thẩm quyền | Theo dõi residual risk và quyết định xử lý |
| **Assurance reviewer/auditor** (khi cần) | Đặt câu hỏi về tính đủ, truy vết và độc lập của bằng chứng | Đánh giá trong phạm vi được giao, giữ tính độc lập |

**Người trực tiếp triển khai control** có thể tạo bằng chứng kiểm thử, nhưng với control rủi ro cao thường cần review chéo hoặc đánh giá độc lập phù hợp. RACI và thẩm quyền phê duyệt nên được ghi theo cơ cấu thực tế, không tự suy từ chức danh.

## 10. Khi nào phải cập nhật threat model?

Một threat model chỉ phù hợp với **kiến trúc và giả định tại thời điểm được lập**. Những sự kiện nên kích hoạt xem xét lại gồm:

- Thêm endpoint, chức năng nhập/xuất dữ liệu, quy trình nghiệp vụ hoặc vai trò mới.
- Thay đổi hệ thống định danh, phân quyền, secret, khóa hoặc trust boundary.
- Thêm nhà cung cấp, dịch vụ bên thứ ba, message queue hoặc kết nối mạng mới.
- Thay đổi cơ sở dữ liệu, cơ chế lưu trữ, phạm vi dữ liệu cá nhân, cloud hoặc vùng triển khai.
- Thay đổi quan trọng trong CI/CD, artifact, dependency hoặc đặc quyền vận hành.
- Phát hiện bảo mật, sự cố, audit hoặc threat intelligence mới cho thấy giả định trước đây không còn đúng.
- Kết quả kiểm thử lại chứng minh control không hoạt động như kỳ vọng.
- Đến kỳ rà soát theo mức rủi ro đã thống nhất.

Mô hình nên được **phiên bản hóa cùng hệ thống/kiến trúc**, có chủ sở hữu, ngày xem lại và liên kết đến các thay đổi quan trọng. Quy trình CI/CD có thể yêu cầu cập nhật mô hình hoặc bổ sung test khi thay đổi liên quan trust boundary và control trọng yếu.

## 11. Một buổi threat modeling gọn nhưng đủ ích

Đối với một tính năng nhỏ như “đọc chi tiết đơn hàng”, có thể tổ chức buổi làm việc ngắn theo trình tự:

1. **Nêu mục tiêu:** chỉ khách hàng có quyền được đọc đơn của họ; dữ liệu và tính sẵn sàng cần được bảo vệ.
2. **Vẽ luồng:** client → gateway → Orders API → Orders DB; thêm IdP và các luồng được gọi thực tế.
3. **Chọn boundary:** nơi token được xác thực, nơi quyền theo đối tượng được quyết định và nơi dữ liệu được truy xuất.
4. **Hỏi các tình huống xấu:** có thể giả mạo danh tính, thay ID, lộ dữ liệu trong log, gây quá tải hay làm sai trạng thái đơn?
5. **Viết threat scenario:** theo mẫu nguồn → hành động → tiền đề → hậu quả.
6. **Gắn mức ưu tiên và control:** có chủ sở hữu, security claim và đường xử lý rủi ro.
7. **Xác định bằng chứng:** test âm A/B, review xử lý quyền, cấu hình gateway/API, logging phù hợp.
8. **Giao việc:** người triển khai, hạn hoàn thành, người review và trigger xem lại.

Đầu ra có thể là một sơ đồ cập nhật, vài threat scenario có chất lượng, danh sách quyết định và các ca kiểm thử được đưa vào backlog. **Ít mục có thể kiểm chứng** thường hữu ích hơn một danh sách dài thiếu điều kiện và chủ sở hữu.

### 11.1. Checklist hoàn tất một vòng threat modeling

- [ ] Phạm vi hệ thống, môi trường, phiên bản và mục tiêu bảo mật được mô tả.
- [ ] Tài sản quan trọng, dữ liệu nhạy cảm và các vai trò truy cập được nhận diện.
- [ ] Có sơ đồ luồng dữ liệu và trust boundaries chính đã được các bên xác nhận.
- [ ] Điểm vào, phụ thuộc, nhà cung cấp và các luồng quản trị được xem xét.
- [ ] Threat scenario nêu rõ nguồn, hành động, điều kiện, tài sản và hậu quả.
- [ ] Kịch bản có ID, chủ sở hữu và liên kết đến risk/requirement khi phù hợp.
- [ ] Các giả định chưa xác minh và giới hạn độ bao phủ được ghi rõ.
- [ ] Mỗi threat ưu tiên có phương án xử lý và control hoặc lý do chưa xử lý.
- [ ] Các security claims trọng yếu có kế hoạch test/review/giám sát.
- [ ] Phát hiện có action owner, hạn, tiêu chí retest và đường chuyển cấp.
- [ ] Quyết định chấp nhận residual risk (nếu có) do đúng người có thẩm quyền đưa ra.
- [ ] Mô hình có người duy trì và trigger cập nhật theo thay đổi.

Checklist giúp nhóm thực hiện có cấu trúc; nó **không phải chứng chỉ** rằng hệ thống đã chống được mọi threat.

## 12. Những hiểu lầm thường gặp

### 12.1. “Threat modeling là liệt kê tất cả cách hacker tấn công”

Không thể bảo đảm mọi đường tấn công được dự đoán. Threat modeling cần **kịch bản liên quan đến tài sản và thiết kế thực tế**, được ưu tiên theo rủi ro và chuyển thành hành động kiểm chứng được.

### 12.2. “Chỉ đội security mới làm được threat modeling”

Nhóm security có chuyên môn về kỹ thuật tấn công, nhưng developer và vận hành biết các giả định kiến trúc, luồng xử lý và triển khai thực tế. Thiếu hiểu biết nghiệp vụ hoặc hệ thống, threat model dễ trở thành một danh sách chung chung.

### 12.3. “Hoàn tất sơ đồ là hoàn tất bảo mật”

Sơ đồ giúp đặt câu hỏi; control phải được triển khai, kiểm thử và giám sát. Threat modeling là **đầu vào của security assurance**, chưa thay thế bằng chứng operating effectiveness.

### 12.4. “Có WAF, HTTPS hoặc JWT thì đã giải quyết threat”

Một control chỉ giải quyết một tập điều kiện nhất định. JWT hợp lệ không tự chứng minh người dùng có quyền trên đơn hàng; HTTPS không thay thế kiểm tra dữ liệu nhập; WAF không sửa lỗi nghiệp vụ.

### 12.5. “Mức STRIDE quyết định độ nghiêm trọng”

STRIDE phân nhóm câu hỏi để nhận diện threat, **không đánh giá likelihood và impact**. Mức rủi ro cần bối cảnh tài sản, điểm yếu, điều kiện khai thác, control và bằng chứng.

### 12.6. “Chạy threat modeling một lần lúc thiết kế là đủ”

Các endpoint, quyền, phụ thuộc và threat thay đổi sau mỗi lần phát hành. Mô hình cũ có thể không còn tương ứng production; cần cập nhật theo các trigger có rủi ro.

### 12.7. “Chưa có bằng chứng xấu nghĩa là control đã đạt”

Không thấy sự cố hoặc lỗi trong log chưa chứng minh việc phòng ngừa đầy đủ. Nếu không có test/đánh giá đúng kịch bản, phải ghi **chưa xác minh**, không mặc định residual risk thấp.

## 13. Câu hỏi tự kiểm tra

1. Threat modeling trả lời những câu hỏi nào mà chỉ quét lỗ hổng thường không trả lời được?
2. Trong sơ đồ của Orders API, ranh giới tin cậy nào cần được rà soát? Vì sao request qua gateway vẫn cần kiểm tra quyền tại tầng ứng dụng?
3. Phân biệt **threat event**, **vulnerability**, **risk** và **incident** trong ví dụ truy cập đơn hàng của người khác.
4. STRIDE giúp nhóm tìm gì? Có thể dựa vào chữ cái “I” để kết luận rủi ro “Cao” không?
5. Hãy viết một threat scenario về message queue bị lạm dụng, gồm nguồn, điều kiện, hành động, hậu quả và control cần kiểm chứng.
6. Vì sao test phân quyền A/B đạt trên một endpoint chưa đủ để chứng minh mọi đường truy cập dữ liệu đơn hàng an toàn?
7. Một team đã có DFD và threat register, nhưng không có kết quả test. Họ có thể kết luận security assurance ở mức nào?
8. Khi thêm một API export dữ liệu, phần nào của threat model và bằng chứng phải được cập nhật?
9. Ai có quyền chấp nhận residual risk, và vai trò của control owner, developer và reviewer là gì?
10. Một threat model chất lượng nên được đo bằng số threat ghi được hay bằng khả năng tạo yêu cầu, control, bằng chứng và quyết định đúng? Giải thích.

## 14. Ghi nhớ

**Threat modeling** là cách **nhìn hệ thống dưới góc độ những điều có thể đi sai**: hiểu kiến trúc và tài sản, nhận diện các kịch bản gây hại, đề xuất control và kiểm chứng theo mức rủi ro. Giá trị lớn nhất đến từ việc biến câu hỏi **“Điều gì có thể xảy ra?”** thành **“Yêu cầu nào phải đạt, control nào thực thi, bằng chứng nào chứng minh và ai chịu trách nhiệm?”**. Trong chương trình **security assurance liên tục**, threat model được cập nhật theo phát triển và vận hành, giúp phát hiện sớm các giả định sai và cung cấp đường truy vết từ thiết kế đến kiểm thử, audit, khắc phục và quyết định rủi ro.
