# Tính an toàn vận hành

Trong chương **Mục tiêu bảo mật**, **tính an toàn vận hành** (operational safety trong ngữ cảnh vận hành hệ thống số) là khả năng tổ chức và vận hành hệ thống sao cho các hoạt động thường ngày, thay đổi, lỗi và sự cố không đẩy hệ thống vào trạng thái gây ra hậu quả bảo mật vượt mức rủi ro được chấp nhận. Mục tiêu này đòi hỏi hệ thống duy trì các kiểm soát bảo mật cần thiết khi triển khai, cấu hình, giám sát, xử lý sự cố và phục hồi.

Ví dụ, một nền tảng học trực tuyến có thể bảo vệ dữ liệu khi phát triển phần mềm nhưng vẫn gặp rủi ro nếu bản phát hành mới vô tình mở công khai API quản trị, tài khoản cũ chưa bị thu hồi, hệ thống cảnh báo ngừng hoạt động hoặc bản sao lưu không thể khôi phục. Những tình huống này xảy ra **trong quá trình vận hành**, vì vậy cần được đưa vào mục tiêu bảo mật và chương trình đánh giá có bằng chứng.

Bài học thuộc module **SECURITY_SECURITY_ASSURANCE**: xây dựng lập luận và bằng chứng để xác nhận hệ thống đạt các mục tiêu bảo mật, từ rủi ro, yêu cầu và security controls đến kiểm thử, audit, xử lý phát hiện và cải tiến liên tục trong phát triển, vận hành.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích ý nghĩa và phạm vi của tính an toàn vận hành, phân biệt nó với tính sẵn sàng, độ tin cậy và an toàn chức năng.
2. Chuyển các nguy cơ trong vận hành thành **mục tiêu bảo mật cụ thể**, **tiêu chí chấp nhận** và **security controls**.
3. Thiết kế kiểm soát cho thay đổi cấu hình, cấp quyền, quản lý lỗ hổng, giám sát, ứng phó và khôi phục.
4. Chọn bằng chứng phù hợp để xác nhận **thiết kế**, **triển khai** và **hiệu quả vận hành** của các kiểm soát.
5. Duy trì assurance khi hệ thống, con người, dữ liệu, nhà cung cấp và mức rủi ro thay đổi.

## 2. Hiểu đúng “an toàn vận hành”

### 2.1. Phạm vi của mục tiêu

Trong bài này, tính an toàn vận hành đề cập đến **bảo mật trong quá trình chạy và quản trị hệ thống**: ngăn thao tác hoặc sự kiện gây mất kiểm soát bảo mật, phát hiện sai lệch, giới hạn tác động, xử lý sự cố và đưa hệ thống trở lại trạng thái đã xác minh.

Các hoạt động điển hình:

- **Vận hành thường ngày:** quản lý quyền truy cập, bí mật, cấu hình, phiên bản, tài nguyên và dữ liệu.
- **Thay đổi:** triển khai ứng dụng, thay đổi hạ tầng, chính sách bảo mật, khóa mã hóa, nhà cung cấp hoặc tuyến mạng.
- **Giám sát:** theo dõi sự kiện bảo mật, dấu hiệu tấn công, suy giảm khả năng phát hiện và trạng thái của các control.
- **Sự cố:** cô lập thành phần bị ảnh hưởng, bảo toàn bằng chứng, khắc phục lỗ hổng, thông báo theo nghĩa vụ áp dụng.
- **Phục hồi:** khôi phục dịch vụ và dữ liệu, xác minh tính toàn vẹn, ngăn tái xâm nhập, rút kinh nghiệm.

Mục tiêu không phải lời hứa “không bao giờ có lỗi”. Mục tiêu thực tế là **giảm xác suất xảy ra sai lệch**, **phát hiện kịp thời**, **giới hạn mức độ ảnh hưởng** và **khôi phục có kiểm soát**, với bằng chứng đủ để kiểm chứng từng khẳng định.

### 2.2. So sánh các khái niệm gần nhau

| Khái niệm | Câu hỏi chính | Ví dụ |
|---|---|---|
| **Tính an toàn vận hành về bảo mật** | Khi vận hành hoặc xử lý sự cố, hệ thống có giữ rủi ro bảo mật trong giới hạn chấp nhận không? | Bản triển khai sai chính sách mạng bị phát hiện và chặn trước khi phục vụ người dùng |
| **Tính sẵn sàng (availability)** | Người dùng hợp lệ có tiếp cận chức năng/dữ liệu khi cần không? | API vẫn phục vụ yêu cầu trong giới hạn SLO |
| **Độ tin cậy (reliability)** | Hệ thống có thực hiện chức năng dự định một cách nhất quán không? | Job xử lý dữ liệu hoàn thành đúng và ít lỗi |
| **Khả năng phục hồi (resilience/recoverability)** | Sau lỗi hoặc tấn công, hệ thống có thể chịu đựng và trở lại trạng thái mong muốn không? | Khôi phục dữ liệu sạch và chỉ mở lại dịch vụ sau khi kiểm tra |
| **An toàn chức năng (functional safety)** | Lỗi của hệ thống có thể gây nguy hiểm cho con người/môi trường không? | Bộ điều khiển thiết bị chuyển sang trạng thái an toàn theo thiết kế |

Các khái niệm có vùng giao nhau. Ví dụ, cuộc tấn công ransomware gây mất tính sẵn sàng và có thể phá hỏng khả năng khôi phục. Nhưng **dịch vụ đang chạy** chưa chắc **đang chạy an toàn**: một endpoint công khai có thể vẫn có độ sẵn sàng cao trong khi làm lộ dữ liệu.

Ở hệ thống có tác động đến sức khỏe, thiết bị công nghiệp hoặc hạ tầng trọng yếu, **an toàn cho con người và môi trường** phải được xem xét theo các yêu cầu safety chuyên ngành tương ứng. Không được tự động coi biện pháp bảo mật kiểu “chặn tất cả truy cập” là giải pháp an toàn nhất trong mọi bối cảnh.

### 2.3. Gắn với CIA và nguyên tắc quản trị rủi ro

Tính an toàn vận hành góp phần giữ gìn:

- **Confidentiality:** hạn chế lộ dữ liệu khi thay cấu hình, cấp quyền hoặc xử lý log.
- **Integrity:** ngăn thay đổi trái phép và xác minh dữ liệu, bản build, cấu hình sau sự cố.
- **Availability:** chống gián đoạn, khôi phục dịch vụ và kiểm soát rủi ro khi chuyển đổi hệ thống.
- **Accountability/traceability:** truy vết ai đã thực hiện thay đổi, vào thời điểm nào, theo phê duyệt nào và kết quả ra sao.

Một hoạt động vận hành có thể tối ưu một mục tiêu nhưng làm tăng rủi ro của mục tiêu khác. Ví dụ, khóa tài khoản bị nghi chiếm quyền giúp bảo vệ dữ liệu nhưng có thể khiến người vận hành mất quyền xử lý sự cố; mở cơ chế truy cập khẩn cấp giúp khôi phục nhưng tạo thêm nguy cơ lạm dụng. Quyết định cần dựa trên threat model, mức độ ảnh hưởng, vai trò phê duyệt và control bù trừ.

## 3. Chuyển mối nguy vận hành thành mục tiêu kiểm chứng được

Một tuyên bố như **“hệ thống được vận hành an toàn”** quá rộng để kiểm thử. Hãy xây dựng chuỗi:

~~~mermaid
flowchart TD
    A["Tài sản và quy trình vận hành"] --> B["Sự kiện đe dọa, sai sót và tác động"]
    B --> C["Đánh giá rủi ro và mức chấp nhận"]
    C --> D["Mục tiêu bảo mật vận hành"]
    D --> E["Tiêu chí đạt và control"]
    E --> F["Kiểm thử và giám sát"]
    F --> G{"Bằng chứng đủ và đạt?"}
    G -->|Có| H["Kết luận assurance có phạm vi"]
    G -->|Không| I["Finding, khắc phục và retest"]
    I --> E
    H --> J["Theo dõi thay đổi và đánh giá lại"]
    J --> B
~~~

Một mục tiêu tốt phải xác định:

1. **Đối tượng:** hệ thống, môi trường, loại dữ liệu hoặc nhóm tài khoản nào?
2. **Hành vi mong muốn:** phải ngăn chặn, phát hiện, ghi nhận, xử lý hoặc khôi phục điều gì?
3. **Điều kiện:** hoạt động thường ngày, thay đổi production, lỗi cấu hình hay sự cố nào?
4. **Tiêu chí đánh giá:** dựa vào phép thử, độ phủ, thời hạn và điều kiện đạt nào?
5. **Chủ sở hữu và kỳ hiệu lực:** ai chịu trách nhiệm, trong khoảng thời gian nào?

Ví dụ, thay câu “backup an toàn” bằng: **“Dữ liệu học tập production thuộc phạm vi được sao lưu theo chính sách, có cảnh báo lỗi backup; bản sao lưu được bảo vệ và kết quả khôi phục thử chứng minh đáp ứng mục tiêu RPO/RTO đã phê duyệt.”**

### 3.1. Ví dụ bộ mục tiêu minh họa

Các ngưỡng và tần suất dưới đây là **ví dụ về chính sách nội bộ**, không phải yêu cầu bắt buộc chung của ISO, NIST hay mọi chương trình audit.

| Mã | Mục tiêu an toàn vận hành | Tiêu chí có thể kiểm chứng |
|---|---|---|
| OPS-01 | Thay đổi production có kiểm soát | Mọi thay đổi thuộc phạm vi có ticket/phê duyệt thích hợp; triển khai qua quy trình có kiểm tra và khả năng rollback |
| OPS-02 | Bảo vệ quyền đặc quyền | Tài khoản admin được cấp tối thiểu, có xác thực phù hợp; quyền được rà soát/thu hồi theo chính sách |
| OPS-03 | Phát hiện sự kiện bảo mật trọng yếu | Log nguồn cần thiết được thu thập; cảnh báo ưu tiên cao đến đúng người xử lý trong thời hạn nội bộ |
| OPS-04 | Xử lý lỗ hổng theo rủi ro | Lỗ hổng thuộc phạm vi được kiểm kê, phân loại, khắc phục/giảm thiểu và kiểm chứng lại |
| OPS-05 | Khả năng phục hồi dữ liệu đáng tin | Sao lưu được giám sát, bảo vệ; restore test chứng minh đạt tiêu chí phục hồi cho hệ thống trọng yếu |
| OPS-06 | Ứng phó sự cố có trách nhiệm | Có vai trò trực, quy trình escalation, hành động ngăn chặn, lưu bằng chứng và kiểm thử kế hoạch |
| OPS-07 | Giảm tác động do phụ thuộc | Phụ thuộc trọng yếu được xác định, theo dõi và có phương án xử lý khi nhà cung cấp gặp sự cố |

Nên gán owner, phạm vi, mức rủi ro và phiên bản chính sách cho từng mục tiêu. Một tiêu chí có thể yêu cầu **bao phủ toàn bộ**, trong khi tiêu chí khác áp dụng **lấy mẫu**; phải ghi rõ cách diễn giải kết quả.

## 4. Những rủi ro vận hành thường gặp

### 4.1. Sai cấu hình và thay đổi ngoài kiểm soát

Khi mở một rule firewall để khắc phục sự cố kết nối, nhóm vận hành có thể vô tình cho phép Internet truy cập cổng quản trị. Khi triển khai bản mới, một feature flag hoặc biến môi trường có thể tắt kiểm tra phân quyền.

**Hậu quả:** lộ dữ liệu, thay đổi trái phép, mở thêm bề mặt tấn công.  
**Control liên quan:** Infrastructure as Code (IaC), kiểm tra policy trước deploy, code review/approval, tách môi trường, xác minh hậu triển khai, drift detection, rollback.  
**Bằng chứng:** diff của thay đổi, kết quả pipeline, ticket phê duyệt, trạng thái cấu hình production và log kiểm tra.

### 4.2. Quyền truy cập bị tích lũy hoặc bị lạm dụng

Nhân sự đổi vai trò vẫn giữ quyền quản trị, service account có token tồn tại lâu, tài khoản khẩn cấp không được giám sát hoặc một nhóm người có thể tự tạo và tự phê duyệt thay đổi.

**Control:** nguyên tắc least privilege, phân tách nhiệm vụ khi phù hợp, vòng đời cấp/thu hồi quyền, xác thực mạnh, giới hạn thời gian sử dụng quyền và theo dõi phiên đặc quyền.

### 4.3. Lỗ hổng tồn đọng và tài sản không được quản lý

Một thư viện có lỗ hổng được công bố nhưng không có owner, máy chủ thử nghiệm vẫn truy cập được từ mạng công cộng hoặc image chạy production không được kiểm kê.

**Control:** inventory tài sản và phiên bản, theo dõi cảnh báo lỗ hổng, ưu tiên dựa trên khả năng khai thác và tác động, kiểm tra sau vá, kiểm soát ngoại lệ có thời hạn.

### 4.4. Giám sát mất hiệu lực

Ứng dụng đổi định dạng log nhưng rule phát hiện không được cập nhật; agent ngừng gửi sự kiện; cảnh báo quá nhiều khiến người trực bỏ qua dấu hiệu quan trọng.

**Control:** kiểm tra sức khỏe pipeline log, phát sinh sự kiện thử, điều chỉnh luật phát hiện, phân loại mức ưu tiên, giao ca và escalation có kiểm chứng.

### 4.5. Sao lưu có nhưng không khôi phục được

Job backup vẫn chạy, song chỉ chứa một phần dữ liệu; bản sao lưu bị mã độc mã hóa cùng hệ thống chính; thao tác restore thiếu khóa mã hóa hoặc mất quá lâu.

**Control:** xác định dữ liệu cần bảo vệ, backup có cô lập và quyền tối thiểu, giám sát lỗi, kiểm tra tính toàn vẹn, diễn tập khôi phục theo kịch bản.

### 4.6. Ứng phó sự cố gây thêm rủi ro

Đội phản ứng xóa log trước khi điều tra, mở rộng quyền tạm thời rồi quên thu hồi, hoặc đưa hệ thống hoạt động trở lại khi nguyên nhân xâm nhập chưa được xử lý.

**Control:** runbook, phân vai và thẩm quyền, bảo toàn bằng chứng, kiểm tra điều kiện mở lại dịch vụ, rà soát hậu sự cố, quản lý quyền truy cập khẩn cấp.

## 5. Các lớp kiểm soát trong vòng đời vận hành

Một chương trình an toàn vận hành đầy đủ cần có **phòng ngừa**, **phát hiện**, **ứng phó**, **phục hồi** và **học từ kết quả**.

| Lớp | Mục đích | Ví dụ | Câu hỏi kiểm chứng |
|---|---|---|---|
| Phòng ngừa | Giảm khả năng sai phạm xuất hiện | RBAC, MFA, policy-as-code, review thay đổi, quản lý secret | Control có bao phủ đúng đường truy cập và loại thay đổi không? |
| Phát hiện | Nhận biết sai lệch và hành vi bất thường | Audit log, alert, drift detection, health check | Sự kiện được tạo có xuất hiện và được chuyển đến đúng nơi không? |
| Ứng phó | Giới hạn tác động và kiểm soát sự cố | Cô lập workload, thu hồi token, điều phối incident | Người trực có thể thực hiện đúng hành động trong kịch bản thực tế không? |
| Phục hồi | Trở lại trạng thái đã xác minh | Restore, redeploy từ artifact tin cậy, rotate secret | Phục hồi có giữ tính toàn vẹn và đạt mục tiêu thời gian/dữ liệu không? |
| Cải tiến | Ngăn tái diễn và cập nhật assurance | Root cause analysis, retest, cập nhật threat model | Finding đã thực sự được đóng bằng bằng chứng mới chưa? |

### 5.1. Thiết kế quy trình thay đổi production an toàn

Một luồng thay đổi thông thường có thể gồm:

1. **Đề xuất:** mô tả mục đích, hệ thống, dữ liệu, cấu hình bị tác động và người phụ trách.
2. **Phân tích rủi ro:** xác định ảnh hưởng đến IAM, bí mật, network, dữ liệu, logging, backup và các control khác.
3. **Review và kiểm tra:** peer review, quét IaC/secret/dependency, test chức năng và test tiêu chí bảo mật có liên quan.
4. **Phê duyệt phù hợp rủi ro:** xác định ai có quyền cho phép triển khai và ai chịu trách nhiệm sau triển khai.
5. **Triển khai có thể quan sát:** theo dõi log, metric, trạng thái policy, lỗi bất thường và drift sau deploy.
6. **Rollback/khôi phục:** có điều kiện rollback rõ ràng; nếu rollback không an toàn, phải có phương án forward fix hoặc cô lập.
7. **Đóng thay đổi:** lưu phiên bản artifact, kết quả triển khai, bất thường và phép kiểm chứng các mục tiêu quan trọng.

Không nên áp dụng cùng mức thủ tục cho mọi thay đổi. Ví dụ thay văn bản giao diện có thể sử dụng cơ chế xét duyệt nhẹ hơn thay chính sách quyền quản trị. **Thay đổi khẩn cấp** vẫn cần ghi nhận lý do, quyền phê duyệt thích hợp, bằng chứng và rà soát sau khi ổn định.

### 5.2. Giữ quyền truy cập trong giới hạn có thể kiểm soát

Những điểm cần thiết kế:

- **Định danh riêng:** không chia sẻ tài khoản vận hành thường ngày; định danh workload/service account rõ ràng.
- **Quyền tối thiểu:** quyền được gán theo vai trò, nhiệm vụ và môi trường, tránh quyền toàn cục nếu không cần.
- **Xác thực phù hợp:** MFA cho thao tác người dùng đặc quyền nếu khả thi; workload dùng phương thức xác thực máy và bí mật ngắn hạn khi hỗ trợ.
- **Quy trình vòng đời:** cấp quyền có duyệt, thay đổi vai trò, thu hồi khi không còn nhu cầu, rà soát định kỳ.
- **Truy cập khẩn cấp:** tài khoản break-glass có điều kiện dùng, logging, cảnh báo và kiểm tra sau mỗi lần kích hoạt.
- **Không ghi lộ thông tin nhạy cảm:** hạn chế token/password trong log, ảnh chụp và ticket; quản lý quyền đọc evidence.

Một tài khoản có MFA **không tự động** chứng minh quyền của nó là hợp lệ. Assurance phải kiểm tra cả **đúng danh tính**, **đúng quyền** và **đúng cách sử dụng quyền**.

### 5.3. Vận hành giám sát có khả năng tự kiểm tra

Giám sát an toàn cần trả lời **“có sự kiện nguy hiểm không?”** và **“hệ thống phát hiện còn hoạt động không?”**.

Ví dụ các phép kiểm thử:

- Tạo một sự kiện đăng nhập thất bại đã được cho phép trong môi trường kiểm thử, rồi kiểm tra nó xuất hiện đầy đủ tại nơi phân tích.
- Giả lập trong phạm vi an toàn một sự kiện thay đổi quyền đặc quyền để xác nhận rule, routing và escalation.
- Kiểm tra log agent, thời gian trễ ingest, retention, phân vùng log và quyền được đọc log.
- Rà soát cảnh báo không được xử lý, rule bị tắt, alert noise và việc bàn giao người trực.

Cần cấu hình bảo vệ log khỏi chỉnh sửa hoặc xóa trái phép, đồng thời tuân thủ thời hạn lưu giữ, phân loại dữ liệu và quyền riêng tư áp dụng.

### 5.4. Phát hiện và xử lý lỗ hổng theo mức rủi ro

Không thể chỉ dựa vào tổng số CVE để đánh giá an toàn vận hành. Quyết định khắc phục cần cân nhắc mức độ dễ khai thác, tài sản có phơi bày hay không, dữ liệu xử lý, khả năng khai thác thực tế, khả năng gián đoạn do vá và biện pháp giảm thiểu hiện có.

Một workflow điển hình:

~~~text
Inventory tài sản/phiên bản
  -> Nhận thông tin lỗ hổng và xác minh áp dụng
  -> Đánh giá ảnh hưởng, mức ưu tiên, owner
  -> Vá/giảm thiểu/cô lập có kiểm soát
  -> Kiểm tra sau thay đổi và re-scan
  -> Ghi bằng chứng, đóng hoặc theo dõi ngoại lệ
~~~

Với trường hợp chưa thể vá, cần xác định control bù trừ, người phê duyệt, thời hạn và lịch tái đánh giá. Chấp nhận rủi ro nội bộ không tự loại bỏ nghĩa vụ pháp lý hoặc hợp đồng.

## 6. Hành vi an toàn khi lỗi và suy giảm dịch vụ

Một khía cạnh quan trọng là **hệ thống xử lý thế nào khi một thành phần bảo mật gặp lỗi**.

- **Fail closed trong kiểm soát truy cập:** nếu không xác minh được quyền, hệ thống mặc định từ chối thao tác nhạy cảm. Điều này thường phù hợp với API quản trị, nhưng có thể ảnh hưởng availability.
- **Graceful degradation có giới hạn:** nếu dịch vụ đề xuất khóa học lỗi, chỉ tắt chức năng đó; không để sự cố lan thành việc bỏ qua xác thực hoặc phân quyền.
- **Cô lập vùng ảnh hưởng:** sự cố một tenant, service hoặc tài khoản không được tự động làm lộ dữ liệu của tenant khác.
- **Tính toàn vẹn khi phục hồi:** không chỉ “khởi động lại” mà phải xác minh code, cấu hình, khóa và dữ liệu không bị sửa trái phép.
- **Quyền khẩn cấp được kiểm soát:** khi đường quản trị chính bị gián đoạn, cơ chế emergency access có điều kiện rõ ràng, theo dõi, thu hồi và kiểm tra sau sử dụng.

**Không có một quy tắc fail-open hay fail-closed phù hợp mọi hệ thống.** Với hệ thống có liên quan trực tiếp đến an toàn tính mạng hoặc thiết bị vật lý, việc chặn một hành động có thể tạo nguy hiểm mới. Cần phối hợp đánh giá rủi ro bảo mật với thiết kế an toàn chức năng và yêu cầu chuyên ngành.

## 7. Tình huống xuyên suốt: thay đổi cấu hình làm lộ API quản trị

**Bối cảnh.** Nền tảng học trực tuyến chạy backend và admin console trên cloud. Một engineer thay đổi cấu hình network để sửa lỗi kết nối với hệ thống báo cáo. Thay đổi vô tình mở API quản trị ra Internet; API vẫn yêu cầu đăng nhập nhưng có một endpoint cũ kiểm tra phân quyền chưa đầy đủ.

**Mục tiêu bảo mật vận hành:**

- OPS-01: Mọi thay đổi vào bề mặt mạng của production phải được đánh giá và kiểm tra trước/ sau triển khai.
- OPS-02: API quản trị chỉ được truy cập qua tuyến mạng và danh tính được cấp phép.
- OPS-03: Sự kiện drift quan trọng phải được phát hiện và xử lý theo runbook.
- OPS-04: Sau sự cố phải chứng minh đã đóng đường truy cập sai và đã xem xét khả năng dữ liệu bị tác động.

### 7.1. Phân tích rủi ro và xác định control

| Rủi ro/đường lỗi | Control phòng ngừa | Phát hiện và phản ứng | Bằng chứng assurance |
|---|---|---|---|
| Rule mở rộng truy cập ngoài ý muốn | IaC, peer review, policy-as-code kiểm tra ingress | Alert khi thay security group, kiểm tra exposure | Pull request, kết quả policy check, cấu hình thực tế |
| Endpoint bỏ sót phân quyền | Test authorization, gateway policy, code review | API log, alert truy cập trái phép, khóa endpoint | Test report, cấu hình route, log truy cập |
| Kẻ tấn công khai thác trước khi sửa | Hạn chế bề mặt công khai, quyền tối thiểu | Incident triage, cô lập, rà soát truy cập và dữ liệu | Timeline incident, truy vấn log, kết quả phân tích |
| Sửa rule nhưng quên nguyên nhân | Root cause, IaC làm nguồn cấu hình chuẩn | Retest, drift detection, hành động ngăn tái diễn | Diff sửa đổi, kiểm tra hậu triển khai, ticket finding |

### 7.2. Bốn kịch bản kết quả khác nhau

**Kịch bản A — Chặn trước khi triển khai.** Pipeline phát hiện rule mở public ingress và fail. Có bằng chứng về kiểm tra phòng ngừa; vẫn cần xác minh chính sách pipeline không bị bỏ qua và các hệ thống thuộc phạm vi đều đi qua nó.

**Kịch bản B — Triển khai rồi phát hiện sớm.** Monitoring phát hiện drift, ca trực xác nhận và rollback. Có thể đánh giá khả năng phát hiện/ứng phó, nhưng cần ghi nhận việc phòng ngừa đã không chặn lỗi.

**Kịch bản C — Hệ thống chạy bình thường, không có alert.** Availability có thể đạt SLO trong khi tính an toàn vận hành không đạt; không được kết luận an toàn chỉ vì người dùng vẫn truy cập được.

**Kịch bản D — Đã đóng cổng nhưng chưa xác minh tác động.** Không nên coi finding hoàn thành nếu còn nghi vấn truy cập trái phép, log thiếu hoặc chưa retest authorization. Việc cô lập là bước giảm tác động, chưa phải toàn bộ kết luận assurance.

### 7.3. Ghi nhận một claim có bằng chứng

Một hồ sơ minh họa có thể biểu diễn như sau:

~~~yaml
claim_id: OPS-NET-01
claim: "Các đường truy cập API quản trị production bị giới hạn và được kiểm tra khi thay đổi"
scope:
  environment: production
  assets: ["admin-api", "api-gateway", "network-policy"]
criteria:
  - "Không có đường truy cập quản trị ngoài phạm vi phê duyệt"
  - "Mọi thay đổi network-policy có kết quả kiểm tra bắt buộc"
controls:
  - "IaC review và policy-as-code"
  - "Runtime exposure monitoring"
  - "Authorization regression testing"
evidence:
  - "Commit/PR và kết quả pipeline có dấu thời gian"
  - "Bản xuất cấu hình thực tế của gateway và network"
  - "Kết quả thử truy cập từ nguồn không được phép"
  - "Alert và incident ticket nếu có sai lệch"
owner: "Platform Security"
limitations:
  - "Phạm vi kiểm tra không bao gồm hệ thống báo cáo của bên thứ ba"
status: "Chỉ xác định sau khi đánh giá đủ bằng chứng"
~~~

Tên control và tiêu chí trong ví dụ là quy ước nội bộ. Đánh giá thực tế cần bổ sung mốc thời gian, phiên bản hệ thống, tập đường truy cập và ngoại lệ được chấp thuận.

## 8. Từ control đến kết luận assurance

Để có assurance đáng tin cậy, không chỉ hỏi **“có control không?”** mà cần kiểm tra ba lớp:

| Lớp | Câu hỏi | Ví dụ bằng chứng |
|---|---|---|
| **Design effectiveness** | Control được thiết kế có xử lý đúng rủi ro và các đường lỗi chính? | Threat model, tiêu chí policy, sơ đồ kiến trúc, review |
| **Implementation effectiveness** | Control có thực sự áp dụng cho hệ thống/trạng thái production đang xét? | Cấu hình đã xuất, danh sách tài sản, kết quả kiểm tra thực tế |
| **Operating effectiveness** | Control có hoạt động nhất quán trong kỳ đánh giá và khi xảy ra sự kiện? | Lịch sử pipeline, mẫu thay đổi, log, alert, incident, kết quả retest |

### 8.1. Mô hình Claim–Argument–Evidence (CAE)

- **Claim — điều muốn khẳng định:** “Các thay đổi nhạy cảm trên production có kiểm soát”.
- **Argument — lý do chứng minh:** Quy trình xác định phạm vi thay đổi, thực thi policy trước deploy, phê duyệt theo rủi ro và theo dõi trạng thái sau deploy; nếu một lớp bỏ sót thì còn lớp phát hiện/ứng phó.
- **Evidence — dữ liệu kiểm chứng:** chính sách có phiên bản, tập thay đổi production của kỳ đánh giá, kết quả pipeline, biên bản phê duyệt, log deploy, alert drift và kết quả xử lý ngoại lệ.

Một claim phù hợp phải có **phạm vi, thời kỳ, tiêu chí, giả định, bằng chứng và giới hạn**. Không nên khẳng định “mọi thay đổi đều an toàn” dựa trên một lần chạy pipeline thành công.

### 8.2. Chất lượng bằng chứng

Đánh giá ít nhất các tiêu chí:

1. **Đúng mục tiêu:** evidence có liên quan đến rủi ro và claim đang xét không?
2. **Đủ phạm vi:** có bao gồm mọi môi trường, tài sản và luồng triển khai liên quan không?
3. **Đúng thời gian:** có phản ánh cả kỳ vận hành, không chỉ một ảnh chụp cấu hình?
4. **Đáng tin về nguồn gốc:** có thể xác minh nguồn, timestamp, phiên bản và quyền sửa đổi?
5. **Đủ tính đại diện:** dữ liệu toàn bộ hay mẫu; cách chọn mẫu và giới hạn đã được công bố?
6. **Có thể tái kiểm tra:** assessor có thể đối chiếu với hệ thống gốc hoặc lặp lại phép thử trong điều kiện phù hợp?

Một screenshot cho thấy dashboard cảnh báo “healthy” chỉ phản ánh trạng thái hiển thị tại thời điểm chụp. Nó chưa chứng minh rule sẽ phát hiện đúng sự kiện hoặc người trực sẽ xử lý đúng thời hạn. Với các claim về vận hành, cần bằng chứng **về sự kiện thực tế hoặc phép thử được kiểm soát trong kỳ**.

### 8.3. Trạng thái đánh giá

Một bộ trạng thái quản lý nội bộ có thể gồm:

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| **Đạt** | Control đáp ứng tiêu chí trong phạm vi và kỳ đã xác định, bằng chứng đủ | Duy trì giám sát và lịch tái đánh giá |
| **Không đạt** | Có sai lệch xác minh được so với tiêu chí | Tạo finding, đánh giá tác động, khắc phục và retest |
| **Chưa đủ bằng chứng** | Không thể kết luận vì thiếu phạm vi, dữ liệu hoặc kiểm thử | Bổ sung evidence hoặc thu hẹp claim được phép khẳng định |
| **Không áp dụng** | Yêu cầu không liên quan trong phạm vi với lý do đã ghi rõ | Lưu quyết định, đánh giá lại khi thay đổi |

Phân loại báo cáo chính thức phải tuân theo quy tắc của chương trình audit hoặc tiêu chuẩn đang áp dụng.

## 9. Kiểm thử tính an toàn vận hành

Không một bài test duy nhất có thể xác nhận toàn bộ mục tiêu. Chọn phép thử theo loại rủi ro và mức ảnh hưởng.

### 9.1. Kiểm thử trước triển khai

- Kiểm tra cấu hình IaC và rule phân quyền/network.
- Test chức năng bảo mật cho đường truy cập nhạy cảm.
- Phân tích dependency, image và secret bị nhúng.
- Kiểm thử rollback hoặc khả năng vô hiệu hóa bản thay đổi.
- Xác minh pipeline chỉ triển khai artifact được phê duyệt.

Mục tiêu là ngăn lỗi phổ biến và phát hiện điều kiện gây hại **trước khi hệ thống tiếp xúc với người dùng thật**.

### 9.2. Kiểm thử khi vận hành

- Đối chiếu cấu hình được phê duyệt với trạng thái production (drift).
- Kiểm tra tài khoản/quyền thực tế, thử truy cập trái phép có kiểm soát.
- Kiểm tra một sự kiện cảnh báo giả lập có đi hết chuỗi phát hiện → ticket → escalation không.
- Thử restore từ bản backup theo kịch bản, ghi nhận dữ liệu và thời gian phục hồi.
- Kiểm tra việc thu hồi secret/token sau sự kiện nghi bị lộ.
- Rà soát sự kiện thay đổi khẩn cấp và tình trạng đóng ngoại lệ.

Các phép thử xâm nhập hoặc diễn tập gây suy giảm dịch vụ phải có phạm vi, thời điểm, phê duyệt và phương án dừng rõ ràng. Với hệ thống production quan trọng, ưu tiên môi trường tương đương hoặc thử nghiệm giới hạn tác động khi phù hợp.

### 9.3. Diễn tập sự cố (tabletop/incident drill)

Một buổi tabletop cho tình huống “token CI/CD bị lộ” nên xác định:

1. Ai nhận cảnh báo và xác minh sự cố?
2. Ai được phép tạm dừng pipeline, thu hồi token, cô lập runner?
3. Làm sao xác định artifact/configuration đã bị sửa?
4. Có cần khôi phục artifact đáng tin hoặc rotate secret liên quan?
5. Cần lưu bằng chứng nào, ai xử lý liên lạc theo nghĩa vụ hiện hành?
6. Điều kiện nào cho phép mở lại pipeline, và ai xác nhận?
7. Sau diễn tập, finding nào cần owner, deadline và retest?

**Kết quả diễn tập** là bằng chứng về mức sẵn sàng của quy trình trong phạm vi kịch bản, không tự động chứng minh toàn bộ năng lực ứng phó với mọi kiểu sự cố.

## 10. Thiết lập chỉ số và ngưỡng chấp nhận

Chỉ số giúp theo dõi khả năng đạt mục tiêu; cần phân biệt **chỉ số hoạt động** (activity metrics) với **chỉ số kết quả bảo mật**.

| Chỉ số | Ý nghĩa khi theo dõi | Giới hạn |
|---|---|---|
| Tỷ lệ thay đổi production có đủ kết quả kiểm tra bắt buộc | Độ bao phủ control trước deploy | Một pipeline pass không đảm bảo policy đúng hoặc không bị bypass |
| Tỷ lệ drift quan trọng được xử lý trong hạn | Khả năng phát hiện và khắc phục sai cấu hình | Phụ thuộc khả năng quan sát đủ các tài sản |
| Thời gian từ phát hiện đến xác nhận và cô lập sự cố | Năng lực phản ứng | Cần xem cả mức độ khó, mức ảnh hưởng và thời gian bắt đầu được ghi nhận |
| Tỷ lệ quyền đặc quyền còn hợp lệ theo mẫu/tổng thể | Kiểm soát quyền truy cập | Mẫu không đại diện có thể che giấu tài khoản bị bỏ sót |
| Tỷ lệ restore test đạt mục tiêu RPO/RTO | Mức tin cậy vào khả năng phục hồi | Phải kiểm tra tính toàn vẹn và đúng loại dữ liệu, không chỉ thời gian |
| Lỗ hổng quá hạn theo mức rủi ro | Nợ khắc phục bảo mật | Điểm severity đơn lẻ không đại diện hoàn toàn cho khả năng khai thác |
| Tuổi và số lượng ngoại lệ control chưa đóng | Mức độ rủi ro tồn đọng | Ít ngoại lệ có thể do quy trình ghi nhận chưa đầy đủ |

**RTO (Recovery Time Objective)** là mục tiêu thời gian tối đa mong muốn để phục hồi chức năng/dịch vụ sau gián đoạn. **RPO (Recovery Point Objective)** là mức mất dữ liệu tối đa chấp nhận được tính theo thời điểm dữ liệu có thể khôi phục. Cả hai do tổ chức quyết định theo tác động kinh doanh và rủi ro, cần được kiểm chứng bằng phép thử thực tế phù hợp.

Một chỉ số tăng hoặc giảm không đủ để khẳng định chương trình an toàn hơn. Ví dụ số alert giảm có thể là ít sự kiện nguy hiểm hơn, nhưng cũng có thể là rule đã bị tắt. Vì vậy, các chỉ số phải được đọc cùng kiểm tra **độ phủ, chất lượng nguồn dữ liệu và khả năng phát hiện**.

## 11. Kết nối với audit và compliance

Chương trình security assurance liên tục và đánh giá compliance có liên hệ trực tiếp:

- **Yêu cầu/tiêu chí:** rút từ luật, hợp đồng, chính sách hoặc framework áp dụng (chẳng hạn một tập kiểm soát truy cập, quản lý thay đổi hoặc kế hoạch ứng phó).
- **Control owner:** đảm bảo control được thiết kế, triển khai và vận hành đúng.
- **Evidence owner:** bảo đảm dữ liệu nguồn được thu thập, bảo vệ và cung cấp trong kỳ.
- **Assessor/auditor:** kiểm tra phương pháp, độ tin cậy của bằng chứng, điều kiện đạt và các ngoại lệ.
- **Risk owner:** quyết định phương án xử lý rủi ro còn lại trong phạm vi thẩm quyền.

Việc phù hợp một checklist compliance có thể hỗ trợ assurance nhưng **không thay thế kiểm chứng thực tế**. Ngược lại, hệ thống có nhiều control hoạt động tốt vẫn có thể chưa đáp ứng một nghĩa vụ hợp đồng hoặc pháp lý cụ thể.

Không nên tuyên bố “chứng nhận hệ thống an toàn vận hành” chỉ vì có kết quả test hoặc audit nội bộ. Mỗi framework/chương trình đánh giá có **phạm vi, điều kiện và cơ chế xác nhận riêng**; claim cần bám vào bằng chứng và tiêu chí thực sự đã áp dụng.

## 12. Xử lý finding và duy trì assurance liên tục

Khi phát hiện một control không đạt, hãy tạo vòng phản hồi rõ trách nhiệm:

~~~mermaid
flowchart LR
    A["Finding có bằng chứng"] --> B["Đánh giá tác động và ưu tiên"]
    B --> C["Owner, kế hoạch và hạn xử lý"]
    C --> D["Khắc phục hoặc control bù trừ"]
    D --> E["Retest và thu thập bằng chứng mới"]
    E --> F{"Đạt tiêu chí?"}
    F -->|Chưa| C
    F -->|Đạt| G["Cập nhật claim, đóng finding"]
    G --> H["Giám sát tái diễn"]
~~~

Hồ sơ finding nên có: mã yêu cầu và control, điều kiện phát hiện, bằng chứng, tài sản bị ảnh hưởng, nguyên nhân gốc, mức rủi ro, owner, hạn xử lý, quyết định chấp nhận rủi ro nếu có, kết quả retest và người phê duyệt đóng.

**Ví dụ:** Kết quả kiểm tra cho thấy một service account còn quyền quản trị sau khi ứng dụng đã ngừng sử dụng. Finding không nên đóng chỉ vì ticket ghi “đã thu hồi”. Cần xác minh quyền thực tế đã bị gỡ, credential liên quan đã vô hiệu hóa nếu cần, đường truy cập thay thế không tồn tại và quy trình offboarding được sửa để ngăn lặp lại.

### 12.1. Sự kiện kích hoạt tái đánh giá

Tính an toàn vận hành phải được đánh giá lại khi:

- Thêm môi trường, dịch vụ, tenant hoặc nhóm dữ liệu nhạy cảm.
- Đổi identity provider, công cụ CI/CD, luồng deploy, network policy hoặc hệ thống log.
- Có lỗ hổng mới ảnh hưởng đến control hiện có.
- Nhà cung cấp trọng yếu thay đổi trách nhiệm, kiến trúc hoặc hợp đồng.
- Xảy ra sự cố, near miss, diễn tập thất bại hoặc phát hiện audit.
- Thay đổi mức chấp nhận rủi ro, tiêu chí nội bộ hoặc nghĩa vụ compliance.

“Đánh giá liên tục” không có nghĩa mọi hoạt động phải kiểm thử liên tục từng giây. Chọn **tần suất dựa trên rủi ro** và kết hợp kiểm tra theo sự kiện thay đổi với kiểm tra theo chu kỳ.

## 13. Những sai lầm dễ mắc

**“Hệ thống có uptime cao nên vận hành an toàn.”** Uptime phản ánh một phần availability. Hệ thống có thể ổn định nhưng mở quyền quá rộng, thiếu log và không thể điều tra sự cố.

**“Có quy trình thay đổi là đủ.”** Cần chứng minh thay đổi thực tế đi qua quy trình, các trường hợp khẩn cấp được kiểm soát, không có đường bypass không quản lý và control vẫn hoạt động sau deploy.

**“Có backup là chắc chắn khôi phục được.”** Cần xác minh dữ liệu đủ, backup không bị sửa/xóa trái phép, thông tin cần cho restore còn sẵn và diễn tập đạt yêu cầu.

**“Không có alert tức là không có vấn đề.”** Có thể hệ thống phát hiện bị hỏng hoặc thiếu độ phủ. Phải kiểm tra telemetry, rule, routing và khả năng người trực phản hồi.

**“Rollback luôn là giải pháp an toàn.”** Rollback có thể khiến schema dữ liệu không tương thích, tái kích hoạt lỗ hổng hoặc mất thay đổi hợp lệ. Cần xác định điều kiện rollback an toàn từ trước.

**“Đóng ticket là đã xử lý rủi ro.”** Chỉ đóng khi có bằng chứng khắc phục và retest phù hợp, hoặc có quyết định xử lý rủi ro còn lại theo thẩm quyền và nghĩa vụ áp dụng.

## 14. Bài tập thực hành

**Tình huống:** Nền tảng học trực tuyến sử dụng cloud database, CI/CD và dịch vụ gửi email bên ngoài. Trong vòng một tuần xảy ra ba vấn đề: (a) một release sửa schema không có phương án khôi phục; (b) hai tài khoản admin của nhân sự đã nghỉ vẫn tồn tại; (c) job backup báo thành công nhưng restore test thất bại do thiếu quyền truy cập khóa giải mã.

Hãy lập một bảng cho từng sự kiện với các cột:

| Mục cần điền | Gợi ý |
|---|---|
| Tài sản/rủi ro | Dữ liệu học viên, quyền quản trị, tính sẵn sàng và toàn vẹn |
| Mục tiêu bảo mật | Viết một câu có chủ thể, điều kiện và tiêu chí đạt |
| Control | Chọn control phòng ngừa và phát hiện, bổ sung ứng phó/khôi phục nếu cần |
| Phép kiểm thử | Nêu cách kiểm chứng thực tế mà không gây tác động ngoài phạm vi |
| Bằng chứng | Nêu nguồn dữ liệu, thời gian, trạng thái, người chịu trách nhiệm |
| Kết luận | Đạt/không đạt/chưa đủ bằng chứng; giới hạn kết luận |
| Việc cần làm | Owner, mức ưu tiên, hạn, retest, trigger tái đánh giá |

**Hướng giải tham khảo:**

- **Release schema:** mục tiêu thay đổi production có kiểm soát đã bị vi phạm nếu chính sách yêu cầu phương án phục hồi trước release. Cần đánh giá tương thích migration, sao lưu dữ liệu khi cần, thiết kế tiến trình rollback/forward fix và kiểm thử có bằng chứng trước thay đổi tiếp theo.
- **Tài khoản admin cũ:** cần cô lập/thu hồi quyền ngay theo quy trình sự cố hoặc offboarding, xác minh danh sách nhân sự/tài khoản, kiểm tra lịch sử truy cập và sửa luồng thu hồi. Bằng chứng gồm IAM state, HR/offboarding events và kết quả review.
- **Backup không restore được:** không thể kết luận đạt mục tiêu phục hồi. Cần xử lý quyền khóa giải mã, bảo vệ khóa, thử restore lại trong môi trường kiểm soát và xác minh dữ liệu khôi phục đúng, đủ. Job status “success” chưa chứng minh recovery khả thi.

**Câu hỏi nâng cao:** Nếu việc khóa toàn bộ quyền quản trị trong một sự cố sẽ cản trở khôi phục dịch vụ, bạn thiết kế cơ chế truy cập khẩn cấp và bằng chứng giám sát thế nào để cân bằng an toàn vận hành, availability và accountability?

## 15. Ghi nhớ

- **Tính an toàn vận hành** là mục tiêu bảo mật về cách hệ thống được thay đổi, sử dụng, giám sát, ứng phó và khôi phục trong thực tế; nó rộng hơn một chỉ số uptime.
- Mục tiêu phải chuyển thành **tiêu chí kiểm chứng được**, có owner, phạm vi, thời kỳ và mức rủi ro chấp nhận.
- Control nên bao phủ **phòng ngừa → phát hiện → ứng phó → phục hồi → cải tiến**; các lớp bù đắp cho nhau khi một lớp thất bại.
- Assurance đáng tin đòi hỏi bằng chứng cho **thiết kế, triển khai và hiệu quả vận hành**, cùng việc nêu rõ giới hạn phép đánh giá.
- Thay đổi, sự cố và finding tạo ra nhu cầu **đánh giá lại**, khắc phục, retest và cập nhật kết luận; assurance phải sống cùng quá trình phát triển và vận hành.

