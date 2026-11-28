# Threat (Mối đe dọa) trong quản lý rủi ro bảo mật

## 1. Threat là gì và vì sao phải nhận diện?

**Threat** (mối đe dọa) là một hoàn cảnh, sự kiện hoặc tác nhân có **khả năng gây tác động bất lợi** đến tài sản, hoạt động hoặc mục tiêu bảo mật của hệ thống. Threat có thể bắt nguồn từ hành vi cố ý như đánh cắp tài khoản, từ sai sót không chủ ý như gửi dữ liệu cho nhầm người, hoặc từ sự kiện vật lý như mất điện và thiên tai. Trong an ninh thông tin, hậu quả có thể ảnh hưởng đến:

- **Confidentiality – Tính bí mật:** dữ liệu chỉ đến được những đối tượng được phép.
- **Integrity – Tính toàn vẹn:** dữ liệu và hoạt động không bị sửa sai, giả mạo hoặc phá hoại trái phép.
- **Availability – Tính sẵn sàng:** dịch vụ và dữ liệu có thể được sử dụng khi cần.
- **Các mục tiêu bổ sung:** tính xác thực, khả năng truy vết, trách nhiệm giải trình, quyền riêng tư và khả năng phục hồi.

Threat là thành phần trung tâm của **quản lý rủi ro**. Nếu không biết điều gì có thể xảy ra và tác động đến tài sản nào, tổ chức khó chọn đúng security controls, thiết kế kiểm thử hoặc xác định bằng chứng cần thu thập.

Trong module **SECURITY_SECURITY_ASSURANCE**, nhận diện threat không chỉ nhằm lập danh sách “các kiểu tấn công”. Kết quả phải giúp nối **tài sản → threat scenario → rủi ro → yêu cầu bảo mật → control → bằng chứng kiểm thử/audit → khắc phục** để chứng minh mức độ đáp ứng mục tiêu bảo mật trong quá trình phát triển và vận hành.

> Threat **không đồng nghĩa** sự cố đã xảy ra, lỗi phần mềm hay rủi ro đã được xác nhận. Đây là nguồn hoặc tình huống **có tiềm năng gây hại**. Mức rủi ro chỉ được đánh giá sau khi xem xét điều kiện xảy ra, điểm yếu, các control đang có, khả năng xảy ra và hậu quả trong bối cảnh cụ thể.

## 2. Phân biệt Threat, Vulnerability, Risk và Incident

Những khái niệm này thường đi cùng nhau nhưng đảm nhiệm các vai trò khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ với API quản lý đơn hàng |
| --- | --- | --- |
| **Asset (tài sản)** | Dữ liệu, hệ thống, quy trình hoặc năng lực cần bảo vệ | Đơn hàng và thông tin của khách hàng |
| **Threat source/actor** | Nguồn tạo ra mối đe dọa; có thể là con người, sự kiện môi trường hoặc hệ thống | Người dùng tò mò, kẻ gian có tài khoản, lỗi vận hành |
| **Threat event** | Sự kiện có thể gây hại cho tài sản | Người dùng thử truy cập đơn hàng của người khác |
| **Threat scenario** | Mô tả có bối cảnh về nguồn, hành vi, điều kiện và hậu quả | A thay ID đơn hàng trên URL và API trả dữ liệu của B |
| **Vulnerability (điểm yếu)** | Lỗ hổng thiết kế, triển khai, cấu hình hoặc quy trình có thể bị khai thác | API chỉ kiểm tra đăng nhập mà thiếu kiểm tra quyền trên đơn |
| **Exposure / precondition** | Điều kiện khiến sự kiện khả thi hoặc tác động lớn hơn | Endpoint truy cập qua Internet; ID có thể đoán được |
| **Risk (rủi ro)** | Khả năng chịu hậu quả bất lợi khi threat tác động lên tài sản trong bối cảnh hiện có | Rò rỉ thông tin khách hàng qua truy cập chéo đơn hàng |
| **Control (kiểm soát)** | Biện pháp giảm khả năng xảy ra, giảm tác động hoặc tăng phát hiện | Kiểm tra quyền theo từng đơn hàng, giám sát truy cập |
| **Incident (sự cố)** | Sự kiện đã xảy ra gây hoặc có thể gây ảnh hưởng và được xử lý theo tiêu chí tổ chức | Xác nhận có truy cập trái phép vào dữ liệu đơn hàng |

Ví dụ, **kẻ tấn công** là một *threat actor*, **thử ID của đơn hàng khác** là một *threat event*, **thiếu phân quyền cấp đối tượng** là *vulnerability*, còn **khả năng rò rỉ dữ liệu và hậu quả của nó** là *risk*. Khi phát hiện hành vi truy cập bất thường trong log, tổ chức cần điều tra để biết đó là kiểm thử hợp lệ, sự kiện đáng ngờ hay một sự cố thật.

### 2.1. Threat và vulnerability có luôn tồn tại cùng nhau?

Một threat có thể tồn tại **ngay cả khi chưa thấy lỗ hổng cụ thể**. Ví dụ, nguy cơ lũ lụt ảnh hưởng trung tâm dữ liệu tồn tại trước khi đánh giá các biện pháp chống ngập, vị trí thiết bị hoặc phương án dự phòng. Tương tự, hành vi dò mật khẩu là threat dù dịch vụ đã có MFA và phát hiện đăng nhập bất thường.

Một vulnerability chỉ tạo rủi ro đáng kể nếu có **bối cảnh phơi nhiễm và kịch bản gây hại phù hợp**. Ví dụ, một thành phần có lỗi nhưng không được sử dụng trên đường tấn công khả thi có thể có mức rủi ro thấp hơn thành phần trực tiếp xử lý dữ liệu nhạy cảm từ Internet.

Vì vậy, việc quét lỗ hổng là nguồn dữ liệu hữu ích nhưng **không thay thế được nhận diện threat theo kiến trúc, dữ liệu và hoạt động kinh doanh**.

## 3. Các thành phần tạo nên một kịch bản Threat

Một mô tả “Có hacker tấn công hệ thống” quá chung để đưa ra quyết định. Một **threat scenario** hữu ích cần trả lời:

1. **Tài sản/mục tiêu:** cái gì cần bảo vệ, thuộc hệ thống hoặc nghiệp vụ nào?
2. **Nguồn đe dọa:** ai hoặc điều gì có thể tạo sự kiện? Có khả năng, động cơ hoặc điều kiện nào?
3. **Hành động/sự kiện:** hoạt động gây hại dự kiến diễn ra như thế nào?
4. **Đường tiếp cận:** endpoint, giao diện, tài khoản, thành phần phụ thuộc hoặc vị trí vật lý nào có thể được sử dụng?
5. **Điều kiện và điểm yếu:** điều gì khiến hành vi khả thi? Những giả định nào chưa được xác minh?
6. **Control hiện có:** cơ chế nào phòng ngừa, phát hiện, phản ứng hoặc giảm thiểu hậu quả?
7. **Hậu quả:** ảnh hưởng đến dữ liệu, vận hành, khách hàng, nghĩa vụ hoặc uy tín như thế nào?
8. **Bằng chứng:** nguồn nào cho thấy khả năng xảy ra, phạm vi phơi nhiễm hoặc hiệu lực control?
9. **Người phụ trách:** ai sở hữu rủi ro, ai sở hữu control và ai thực hiện hành động?

Một cấu trúc mô tả đơn giản:

> Khi **[nguồn đe dọa]** thực hiện **[hành động]** qua **[đường tiếp cận]**, trong điều kiện **[điểm yếu/tiền đề]**, thì **[tài sản]** có thể chịu **[tác động]**; các **[control]** hiện tại cần được kiểm chứng bằng **[bằng chứng]**.

Ví dụ: “Một người dùng đã xác thực có thể gửi ID của đơn hàng không thuộc mình qua API công khai. Nếu tầng nghiệp vụ không kiểm tra quyền theo đối tượng, hệ thống có thể tiết lộ thông tin người mua. Nhóm phát triển cần chứng minh các yêu cầu không có quyền bị từ chối trên phiên bản triển khai.”

Cách viết này chỉ ra **điều cần kiểm thử** và **điều kiện để kết luận**, thay vì chỉ dán nhãn “IDOR” hoặc “High risk”.

## 4. Những loại nguồn và sự kiện Threat thường gặp

### 4.1. Phân loại theo nguồn và ý định

| Loại | Đặc điểm | Ví dụ | Lưu ý khi đánh giá |
| --- | --- | --- | --- |
| **Đối tượng bên ngoài có chủ đích** | Cố tình tìm cách truy cập, phá hoại, trục lợi hoặc gián đoạn | Credential stuffing, khai thác API, tấn công từ chối dịch vụ | Xem khả năng, động cơ, mức tiếp cận, biện pháp phòng thủ |
| **Đối tượng nội bộ có chủ đích** | Người có quyền hợp pháp nhưng lạm dụng quyền | Trích xuất dữ liệu vượt nhu cầu, sửa log để che giấu | Xem đặc quyền, giám sát, tách nhiệm vụ và kiểm soát dữ liệu |
| **Sai sót vô ý** | Lỗi của con người hoặc quy trình | Đăng cấu hình công khai, gửi file sai người, xóa nhầm dữ liệu | Không mặc định mọi sự cố đều có kẻ tấn công |
| **Lỗi kỹ thuật hoặc phụ thuộc** | Hỏng hóc, hành vi bất thường của thành phần | Hệ quản trị cơ sở dữ liệu dừng, chứng chỉ hết hạn, nhà cung cấp lỗi | Xem phụ thuộc, dự phòng, giám sát và khả năng khôi phục |
| **Môi trường/vật lý** | Sự kiện ngoài hệ thống phần mềm | Mất điện, cháy, ngập, đứt kết nối | Xem vị trí, cấu hình vùng triển khai, sao lưu và kế hoạch liên tục |
| **Chuỗi cung ứng** | Rủi ro đến từ phần mềm, dịch vụ hoặc nhà cung cấp thứ ba | Package bị cài mã độc, build pipeline bị chiếm quyền | Xem nguồn phụ thuộc, quyền CI/CD, xác minh artifact và trách nhiệm hợp đồng |

Một nguồn có thể tạo nhiều threat event, và cùng một sự kiện có thể bắt nguồn từ nhiều nguồn. Ví dụ, dữ liệu bị sửa sai có thể do kẻ gian, nhân viên nhập liệu nhầm hoặc lỗi tích hợp.

### 4.2. Phân loại theo mục tiêu bị ảnh hưởng

Một cách rà soát phổ biến trong thiết kế ứng dụng là **STRIDE**. Đây là công cụ nhắc nhóm xem nhiều lớp mối đe dọa, **không phải** thang mức độ nghiêm trọng:

| Nhóm STRIDE | Câu hỏi cần đặt | Ví dụ ở ứng dụng Java/API |
| --- | --- | --- |
| **S – Spoofing** (giả mạo danh tính) | Có thể giả làm người dùng hoặc dịch vụ khác không? | Dùng token bị đánh cắp để truy cập |
| **T – Tampering** (sửa đổi trái phép) | Có thể thay đổi dữ liệu, thông điệp hoặc cấu hình trái phép không? | Thay giá tiền trong yêu cầu và máy chủ tin giá do client gửi |
| **R – Repudiation** (chối bỏ hành động) | Có thể thực hiện hành động quan trọng mà thiếu bằng chứng truy vết không? | Thao tác hoàn tiền không có audit trail |
| **I – Information disclosure** (lộ thông tin) | Dữ liệu nhạy cảm có thể đến người không có quyền không? | Truy cập chéo dữ liệu qua ID trên URL |
| **D – Denial of service** (mất khả dụng) | Có thể làm dịch vụ cạn tài nguyên hoặc ngừng hoạt động không? | API tạo báo cáo tiêu tốn CPU không có giới hạn |
| **E – Elevation of privilege** (leo thang đặc quyền) | Người dùng có thể đạt quyền cao hơn mức được cấp không? | Người dùng thường gọi endpoint chỉ dành cho admin |

STRIDE giúp nhóm đặt câu hỏi có hệ thống, nhưng vẫn cần xét **rủi ro nghiệp vụ, kiến trúc, nhà cung cấp, vận hành và môi trường vật lý** mà phân loại này không bao quát đầy đủ.

### 4.3. Threat theo giai đoạn và bề mặt tấn công

Threat không chỉ hiện diện ở ứng dụng sản xuất. Một hệ thống có nhiều bề mặt cần xem xét:

- **Thiết kế và yêu cầu:** thiếu phân loại dữ liệu, nhầm lẫn ranh giới tin cậy, bỏ sót trường hợp lạm dụng.
- **Mã nguồn và phụ thuộc:** lỗi lập trình, thư viện chứa thành phần độc hại, lộ khóa trong repository.
- **CI/CD:** chiếm quyền tài khoản build, sửa artifact, pipeline thiếu kiểm tra quyền.
- **Triển khai:** cấu hình cloud công khai, quyền dịch vụ quá rộng, bí mật tiêm qua biến môi trường không được bảo vệ.
- **Ứng dụng và API:** xác thực, phân quyền, dữ liệu đầu vào, xử lý lỗi, rate limiting, thao tác nghiệp vụ.
- **Vận hành:** thiếu log, thiếu cảnh báo, lỗi backup, mất kết nối đến dịch vụ phụ thuộc.
- **Nhà cung cấp và bên thứ ba:** thay đổi SLA, sự cố phụ thuộc, chuyển dữ liệu sai phạm vi.
- **Con người và quy trình:** phishing, cấp quyền dư thừa, phê duyệt thay đổi hình thức, mất thiết bị.

Một threat scenario thường đi qua **nhiều bề mặt**. Ví dụ, kẻ xấu có thể đánh cắp token CI, sửa pipeline build và đưa artifact chứa mã độc lên sản xuất. Khi đó chỉ rà quét endpoint không đủ để đánh giá toàn bộ kịch bản.

## 5. Nhận diện Threat trong hệ thống thực tế

### Bước 1. Xác định phạm vi và tài sản quan trọng

Lập danh mục những thành phần và dữ liệu cần bảo vệ:

- Ứng dụng, dịch vụ, API, database, message queue, hệ thống danh tính.
- Dữ liệu khách hàng, thông tin thanh toán, bí mật ứng dụng, khóa ký và log.
- Nghiệp vụ quan trọng: đăng nhập, phê duyệt giao dịch, hoàn tiền, xuất dữ liệu.
- Mục tiêu phi chức năng: tính sẵn sàng, toàn vẹn, phục hồi và khả năng điều tra.
- Phạm vi môi trường: phát triển, thử nghiệm, production, sao lưu, tích hợp đối tác.

**Ưu tiên theo tài sản và mục tiêu** giúp tránh danh sách đe dọa quá dài nhưng thiếu những điều hệ thống thực sự phải bảo vệ.

### Bước 2. Phác họa luồng dữ liệu và ranh giới tin cậy

Xác định ai hoặc thành phần nào gửi dữ liệu cho ai, dữ liệu được xử lý/lưu ở đâu và **niềm tin thay đổi ở điểm nào**:

~~~mermaid
flowchart LR
    U["Người dùng / client không tin cậy"] --> G["API Gateway"]
    G --> A["Orders API (Spring Boot)"]
    A --> DB[("Orders DB")]
    A --> Q["Message broker"]
    Q --> B["Billing worker"]
    A --> IDP["Identity Provider"]

    U -. "Token và tham số yêu cầu" .-> A
    A -. "Truy vấn dữ liệu theo quyền" .-> DB
~~~

Sơ đồ chỉ minh họa hệ thống. Những điểm cần rà soát gồm client → gateway, gateway → API, API → cơ sở dữ liệu, API → message broker và API → nhà cung cấp danh tính. Ở từng ranh giới, hỏi: ai được tin cậy, danh tính nào được mang theo, dữ liệu có được kiểm tra không, quyền có bị mở rộng không?

### Bước 3. Liệt kê sự kiện có thể gây hại

Kết hợp nhiều góc nhìn:

1. **Lạm dụng nghiệp vụ:** ai được lợi khi phá quy tắc, ví dụ đọc đơn hàng người khác hay hoàn tiền hai lần?
2. **STRIDE:** kiểm tra giả mạo, sửa đổi, chối bỏ, lộ dữ liệu, mất khả dụng và tăng đặc quyền.
3. **Lịch sử thực tế:** sự cố và near-miss đã ghi nhận trong phạm vi tổ chức.
4. **Kết quả kiểm thử/audit:** điểm yếu được phát hiện có gợi ra kịch bản gây hại nào?
5. **Threat intelligence phù hợp:** chiến thuật và kỹ thuật đang được dùng nhắm vào loại tài sản, nền tảng hoặc ngành tương ứng.
6. **Sai sót và phụ thuộc:** lỗi thao tác, lỗi cấu hình, mất dịch vụ, lỗi vật lý và nhà cung cấp.

Thông tin tình báo về mối đe dọa (*threat intelligence*) là đầu vào để hình thành giả thuyết và ưu tiên; cần đánh giá nguồn, độ tin cậy, thời điểm và mức phù hợp. Không coi mọi chiến thuật đang phổ biến trên Internet đều có khả năng tác động ngang nhau đến hệ thống.

### Bước 4. Mô tả từng kịch bản đủ cụ thể để kiểm chứng

Với mỗi threat, ghi nguồn, hành động, tiền đề, control, hậu quả và điều chưa chắc chắn. Tránh các mục chỉ gồm một từ như “SQL injection”, “ransomware” hoặc “insider”.

Thay vào đó:

- “Đầu vào tìm kiếm được nối trực tiếp vào truy vấn dữ liệu; một request được tạo có chủ đích có thể thay đổi ý nghĩa truy vấn và truy xuất dữ liệu ngoài phạm vi.”
- “Tài khoản vận hành bị lộ khóa phiên và không có bước xác minh bổ sung khi thực hiện thao tác xóa; kẻ chiếm tài khoản có thể xóa dữ liệu quan trọng.”
- “Dịch vụ báo cáo chạy truy vấn nặng không có giới hạn đồng thời; một tập request lặp lại có thể làm cạn kết nối database và ảnh hưởng dịch vụ khác.”

Bản mô tả càng rõ, việc thiết kế **security claim và ca kiểm thử** càng dễ.

### Bước 5. Rà soát giả định với nhiều vai trò

Threat workshop hữu ích khi có đủ đại diện ứng dụng, kiến trúc, an ninh, vận hành và chủ nghiệp vụ. Ví dụ:

- Nhà phát triển hiểu đường xử lý đầu vào và cơ chế phân quyền.
- Vận hành biết cấu hình thực tế, phụ thuộc và nguồn log.
- Chủ nghiệp vụ hiểu thao tác nào gây tổn thất hoặc vi phạm cam kết.
- Nhóm bảo mật biết kỹ thuật tấn công, điểm mù và cách kiểm thử.
- Người sở hữu rủi ro quyết định hậu quả nào là trọng yếu.

Nếu có bất đồng về điều kiện khai thác, ghi **giả định và bằng chứng cần bổ sung**, không tự nâng một suy đoán thành sự thật.

### Bước 6. Cập nhật khi hệ thống thay đổi

Danh sách threat cần được tái xem xét khi thêm API, thay chính sách quyền, mở tích hợp, triển khai vùng mới, cập nhật thư viện quan trọng, đổi nhà cung cấp, có sự cố hoặc bằng chứng cho thấy threat mới. Việc nhận diện phải đi cùng **vòng đời phát triển và vận hành**, không chỉ diễn ra một lần trước ngày phát hành.

## 6. Từ Threat sang đánh giá Risk

Một threat chưa tự tạo ra **mức rủi ro**. Đánh giá cần xem xét kịch bản cụ thể với các yếu tố:

- **Khả năng xảy ra:** nguồn đe dọa có thể tiếp cận tài sản không, cần kỹ năng/nguồn lực nào, tiền đề có tồn tại không, các control phòng ngừa/phát hiện có hiệu quả không?
- **Tác động:** dữ liệu nào có thể bị lộ/sửa/xóa; quy mô người dùng ảnh hưởng; thiệt hại hoạt động, tài chính, pháp lý hoặc uy tín?
- **Phơi nhiễm và độ bất định:** có bao nhiêu endpoint, tài khoản, môi trường liên quan; bằng chứng nào chưa được xác minh?
- **Hiệu lực control:** mức độ giảm khả năng xảy ra hoặc giảm hậu quả sau các biện pháp hiện có.

Có thể ước lượng định tính như **Thấp / Trung bình / Cao / Rất cao** nếu tổ chức đã định nghĩa tiêu chí. Ma trận ví dụ dưới đây chỉ là **mô hình minh họa**, không phải chuẩn đánh giá bắt buộc:

| Khả năng xảy ra \\ Tác động | Thấp | Trung bình | Cao |
| --- | --- | --- | --- |
| **Thấp** | Thấp | Thấp | Trung bình |
| **Trung bình** | Thấp | Trung bình | Cao |
| **Cao** | Trung bình | Cao | Cao |

**Cảnh báo quan trọng:** ma trận không tự biến dữ liệu thiếu chắc chắn thành con số khách quan. Nhóm cần nêu căn cứ cho mức likelihood và impact, các giả định, độ tin cậy, và chuẩn chuyển cấp của tổ chức. Với rủi ro nghiêm trọng, có thể cần mô hình chi tiết hơn, kịch bản định lượng hoặc đánh giá chuyên gia.

### 6.1. Inherent risk và residual risk

- **Inherent risk** (rủi ro vốn có) thường là mức rủi ro của kịch bản trước khi xét các control cụ thể được đánh giá, theo phương pháp tổ chức.
- **Residual risk** (rủi ro còn lại) là mức rủi ro sau khi xét các control và biện pháp xử lý thực tế.

Ví dụ, một API chứa dữ liệu nhạy cảm có thể đối mặt với rủi ro lộ thông tin cao nếu không kiểm tra quyền. Sau khi áp dụng kiểm tra quyền cấp đối tượng, test hồi quy và giám sát, rủi ro có thể giảm; nhưng chỉ được kết luận theo **bằng chứng về thiết kế và vận hành** của những control này.

Không lấy mức inherent trừ một số điểm tùy ý để tuyên bố residual thấp. Đặc biệt, nếu bằng chứng control thiếu hoặc đã quá hạn, cần nêu rõ **mức tin cậy của kết luận residual risk**.

### 6.2. Threat, risk và mức ưu tiên sửa lỗi

Một lỗ hổng có điểm kỹ thuật cao chưa chắc luôn gây rủi ro kinh doanh lớn nhất; ngược lại, lỗi logic nghiệp vụ không được công cụ quét gắn điểm cao vẫn có thể làm lộ lượng lớn dữ liệu. Khi ưu tiên, hãy kết hợp **khả năng khai thác trong bối cảnh, tác động tài sản, phạm vi phơi nhiễm, khả năng phát hiện và các control còn hiệu lực**.

Quyết định cuối cùng về **chấp nhận rủi ro còn lại** thuộc risk owner hoặc cấp có thẩm quyền theo quy chế. Control owner và nhóm bảo mật cung cấp bằng chứng, đánh giá kỹ thuật và phương án; họ không tự động có quyền chấp nhận mọi rủi ro.

## 7. Ví dụ xuyên suốt: Threat truy cập chéo tài khoản ở API Java/Spring Boot

Giả sử dịch vụ đơn hàng cung cấp API:

~~~http
GET /api/orders/841
Authorization: Bearer <token-cua-nguoi-dung-A>
~~~

Người dùng A có tài khoản hợp lệ, nhưng đơn hàng 841 thuộc người dùng B.

### 7.1. Threat scenario

| Thành phần | Nội dung minh họa |
| --- | --- |
| Tài sản | Đơn hàng, tên người nhận, địa chỉ giao hàng và dữ liệu nghiệp vụ liên quan |
| Threat source | Người dùng bên ngoài có tài khoản hợp lệ nhưng không có quyền trên đơn hàng 841 |
| Threat event | Thay ID trong URL để truy cập một đối tượng của người khác |
| Tiền đề | Endpoint cho phép truy vấn bằng ID; cần xác minh cách ứng dụng kiểm tra quyền |
| Vulnerability tiềm năng | Chỉ kiểm tra đăng nhập; không ràng buộc bản ghi với danh tính/quyền của chủ thể |
| Tác động | Tiết lộ dữ liệu đơn hàng, ảnh hưởng tính bí mật và nghĩa vụ bảo vệ dữ liệu |
| Control đề xuất | Authorization tại tầng nghiệp vụ/dữ liệu, mặc định từ chối nếu không đủ quyền |
| Bằng chứng cần có | Review luồng phân quyền, test A/B, test role được ủy quyền, kết quả trên bản phát hành |
| Chủ sở hữu | Control owner của Orders API; risk owner của sản phẩm chịu trách nhiệm xử lý rủi ro còn lại |

Nếu người dùng A thử truy vấn và API thực sự trả nội dung của B, đó là **phát hiện cần xác minh và xử lý**, không chỉ là suy đoán threat. Nếu chưa thử, nhóm không được trình bày kịch bản như một sự cố đã xảy ra.

### 7.2. Thiết kế control tương ứng

Một cách thực thi ở tầng dữ liệu là truy vấn đồng thời theo **ID đơn hàng và customer ID tin cậy lấy từ context xác thực**, chẳng hạn:

~~~java
@Service
public class OrderQueryService {
    private final OrderRepository repository;
    private final CurrentCustomer currentCustomer;

    public OrderQueryService(OrderRepository repository,
                             CurrentCustomer currentCustomer) {
        this.repository = repository;
        this.currentCustomer = currentCustomer;
    }

    @Transactional(readOnly = true)
    public OrderView findOrder(long orderId) {
        long customerId = currentCustomer.customerId();

        return repository.findByIdAndCustomerId(orderId, customerId)
                .map(OrderView::from)
                .orElseThrow(() ->
                        new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
~~~

Đoạn mã là **minh họa thiết kế**, chưa phải chương trình chạy độc lập. Các kiểu OrderRepository, CurrentCustomer và OrderView phải được định nghĩa thực tế. Việc lấy customerId cần dựa trên danh tính đã xác thực và kiểm tra đáng tin, không dùng ID do client tự gửi. Chính sách phân quyền quản trị hoặc ủy quyền hợp pháp cần xử lý riêng; mã 403 hay 404 phải tuân theo chính sách API và yêu cầu không làm lộ thông tin.

Control có mục tiêu **ngăn đọc trái phép**. Nếu API còn endpoint liệt kê, xuất file, batch job hoặc luồng nội bộ truy cập cùng dữ liệu, các đường đó cũng phải được rà soát; bảo vệ một endpoint chưa chứng minh toàn bộ hệ thống an toàn.

### 7.3. Test matrix biến Threat thành bằng chứng

| Test | Tiền đề | Kết quả mong đợi |
| --- | --- | --- |
| Người dùng A đọc đơn A | A xác thực, có đơn thuộc A | Trả dữ liệu đúng quyền |
| A đọc đơn B | A xác thực, B sở hữu đơn | Từ chối và không trả thông tin đơn B |
| Request không token | Chưa xác thực | Từ chối theo cơ chế xác thực |
| Người dùng bị thu hồi quyền | Quyền đã cập nhật theo quy định | Không cho truy cập ngoài quyền hiện tại |
| Đối tượng không tồn tại | ID hợp lệ về định dạng | Không tiết lộ dữ liệu |
| Role có quyền được ủy quyền | Policy cấp quyền rõ ràng | Chỉ truy cập đúng phạm vi ủy quyền |
| Endpoint mới dùng dữ liệu đơn | API mới được thêm | Kiểm tra quyền đồng nhất và có test tương ứng |

Một test “A đọc đơn B” trả kết quả từ chối cung cấp bằng chứng **trong kịch bản được kiểm tra**. Không suy rộng rằng mọi khả năng rò rỉ khác đã được loại bỏ.

### 7.4. Threat record để theo dõi

Mẫu YAML **giả định**, chỉ minh họa cách lưu threat scenario và liên kết bằng chứng:

~~~yaml
threat_id: "THR-ORDERS-DEMO-003"
title: "Truy cap cheo don hang bang thay doi ID"
asset: "Don hang va thong tin khach hang"
threat_source: "Nguoi dung da dang nhap nhung khong co quyen"
threat_event: "Yeu cau truy cap ID cua nguoi khac"
entry_point: "GET /api/orders/{orderId}"
preconditions:
  - "Endpoint cho phep tra cuu theo ID"
  - "Can xac minh authorization cap doi tuong"
potential_impact:
  - "Lo thong tin don hang"
  - "Anh huong tinh bi mat du lieu"
control_id: "AUTHZ-ORDER-DEMO"
security_claim: "Chi tra don hang khi chu the co quyen"
required_evidence:
  - "Review authorization theo doi tuong"
  - "Integration test User A va User B"
  - "Ket qua tren version duoc phat hanh"
evidence_status: "CHUA_XAC_MINH"
risk_owner: "Chu so huu san pham Orders"
control_owner: "Nguoi phu trach kiem soat truy cap Orders API"
next_action: "Chay test va danh gia rui ro con lai"
~~~

Trạng thái **CHUA_XAC_MINH** cố ý nhắc rằng đây chưa phải kết luận assurance. Trong hồ sơ thực, cần có thời điểm, môi trường, phiên bản, link kết quả thực thi, reviewer và quyết định xử lý trong thẩm quyền.

## 8. Chuyển Threat thành yêu cầu, Control và Evidence

Một threat hữu ích phải dẫn được đến hoạt động có thể kiểm tra. Chuỗi truy vết điển hình:

~~~mermaid
flowchart TD
    A["Tài sản và mục tiêu bảo mật"] --> B["Threat source + event + precondition"]
    B --> C["Risk scenario và hậu quả"]
    C --> D["Yêu cầu bảo mật có thể kiểm chứng"]
    D --> E["Thiết kế và triển khai security control"]
    E --> F["Bằng chứng: review, test, audit, monitoring"]
    F --> G{"Control đáp ứng claim?"}
    G -- "Chưa đủ bằng chứng" --> H["Bổ sung đánh giá"]
    H --> F
    G -- "Không đáp ứng" --> I["Phát hiện, khắc phục, retest"]
    I --> E
    G -- "Đạt trong phạm vi" --> J["Kết luận assurance và đánh giá residual risk"]
    J --> K["Theo dõi thay đổi, threat mới, vận hành"]
    K --> B
~~~

Một bảng liên kết thực hành:

| Threat | Yêu cầu bảo mật | Control | Bằng chứng assurance |
| --- | --- | --- | --- |
| Truy cập đơn hàng của người khác | Mỗi lần đọc đối tượng phải xác minh quyền thực tế | Authorization theo đối tượng | Test âm A/B, review thiết kế và truy vấn dữ liệu |
| Lộ bí mật truy cập từ mã nguồn | Bí mật không xuất hiện trong repository/artifact công khai | Secrets manager, quy trình cấp/thu hồi | Secret scanning, review cấu hình, kiểm tra phân quyền secret |
| Sửa đổi bản build trong CI | Chỉ build được ủy quyền và artifact được xác minh mới triển khai | Phân quyền pipeline, bảo vệ nhánh, xác minh artifact | Log pipeline, thông tin nguồn build, kiểm tra quyền deploy |
| API báo cáo bị khai thác gây cạn tài nguyên | Giới hạn tài nguyên và chịu lỗi theo yêu cầu dịch vụ | Rate limiting, queue, timeout, quota | Load test có kịch bản lạm dụng, telemetry và cảnh báo |
| Thất bại vùng triển khai | Dịch vụ đáp ứng mục tiêu khôi phục đã phê duyệt | Backup, dự phòng, runbook khôi phục | Kết quả diễn tập restore/failover trên phạm vi thực |

**Assurance không dừng ở việc control tồn tại.** Cần xác định bằng chứng hỗ trợ **design effectiveness** (thiết kế phù hợp với threat) và **operating effectiveness** (thực tế control đang vận hành như mong đợi). Audit hoặc chứng nhận chỉ cung cấp tin cậy trong phạm vi và thời điểm đã đánh giá.

## 9. Các bên chịu trách nhiệm với Threat

| Vai trò | Việc cần làm |
| --- | --- |
| **Business/system owner** | Mô tả tài sản, luồng nghiệp vụ quan trọng, hậu quả tiềm năng |
| **Risk owner** | Chịu trách nhiệm phương án xử lý và quyết định về residual risk theo thẩm quyền |
| **Security analyst / architect** | Hỗ trợ nhận diện threat, đánh giá đường tấn công, thiết kế yêu cầu và kiểm soát |
| **Control owner** | Bảo đảm control được thiết kế, triển khai, vận hành, có bằng chứng và được khắc phục khi lệch |
| **Developer / SRE / vận hành** | Triển khai và vận hành biện pháp, tạo log và kết quả kiểm thử |
| **Test / assurance / audit** | Kiểm tra các security claims bằng bằng chứng phù hợp, báo cáo giới hạn và phát hiện |
| **Hội đồng bảo mật hoặc cấp điều hành** | Điều phối ưu tiên, nguồn lực, ngoại lệ hoặc chuyển cấp khi vấn đề vượt ranh giới nhóm |

Các vai trò có thể kiêm nhiệm, nhưng phải rõ **người quyết định, người thực hiện và người kiểm chứng**. Đặc biệt, bên thực hiện control không nên tự tuyên bố kết luận độc lập cho control rủi ro cao nếu thiếu cơ chế rà soát thích hợp.

## 10. Threat intelligence và monitoring có vai trò gì?

**Threat intelligence** là thông tin đã được phân tích về những nguồn đe dọa, phương thức, kỹ thuật và bối cảnh có liên quan. Nó giúp:

- Đặt ưu tiên cho các threat scenario có dấu hiệu xuất hiện trong môi trường phù hợp.
- Tìm những kỹ thuật hoặc đường tấn công chưa được xem trong thiết kế.
- Cập nhật test case, cảnh báo và giả định về khả năng xảy ra.
- Kết hợp tín hiệu từ sự cố nội bộ, nhà cung cấp, hoạt động vận hành và nguồn cảnh báo có độ tin cậy.

Tuy nhiên, **chỉ có IOC, tên nhóm tấn công hay một bài cảnh báo** chưa đủ để chứng minh hệ thống đang bị khai thác. Cần xác thực phạm vi áp dụng, độ mới, độ tin cậy và quan hệ với tài sản thực tế.

**Monitoring** giúp xem threat có biểu hiện thành hành vi đáng ngờ hay không, ví dụ tăng truy cập bị từ chối, nhiều lần xác thực thất bại hoặc thay đổi cấu hình bất thường. Monitoring còn cung cấp bằng chứng vận hành cho security assurance, nhưng một **khoảng thời gian không có cảnh báo không chứng minh mọi threat đều đã bị loại bỏ**: các quy tắc cảnh báo, độ bao phủ và chất lượng log cũng phải được đánh giá.

### 10.1. Theo dõi và cập nhật threat register

Đối với mỗi threat scenario, tổ chức nên ghi:

- ID, mô tả, tài sản và người phụ trách.
- Nguồn và thời điểm nhận diện.
- Kịch bản, điều kiện, threat event, hậu quả dự kiến.
- Risk ID, các giả định và mức độ chắc chắn của đánh giá.
- Các control liên quan, owner và bằng chứng còn hiệu lực.
- Những phát hiện hoặc ngoại lệ đang mở.
- Sự kiện kích hoạt phải đánh giá lại: thay đổi kiến trúc, control, sự cố, dữ liệu hoặc nguồn threat intelligence đáng tin.
- Kết luận gần nhất và người phê duyệt quyết định xử lý rủi ro.

Nếu một threat bị đánh giá là “không áp dụng”, cần ghi **lý do và căn cứ** (ví dụ thành phần không tồn tại trong kiến trúc đã kiểm chứng), không đơn thuần xóa khỏi danh sách.

## 11. Sai lầm thường gặp khi quản lý Threat

### 11.1. Chỉ liệt kê tên kỹ thuật tấn công

Danh sách "XSS, SQL injection, brute force" chưa cho biết tài sản bị ảnh hưởng, vị trí phơi nhiễm, điều kiện khai thác hoặc hậu quả. **Khắc phục:** viết threat scenario theo bối cảnh và gắn với yêu cầu kiểm chứng.

### 11.2. Coi threat là sự cố thật

Một khả năng bị tấn công không có nghĩa đã bị tấn công. **Khắc phục:** phân biệt giả thuyết, phát hiện đã được xác nhận, sự kiện quan sát và incident đã được phân loại.

### 11.3. Nhầm severity của vulnerability với risk của hệ thống

Điểm kỹ thuật của lỗ hổng là dữ kiện đầu vào, không thay thế mức phơi nhiễm, hậu quả và hiệu lực control. **Khắc phục:** đánh giá trong ngữ cảnh sản phẩm và ghi lại lý do ưu tiên.

### 11.4. Chỉ xem đối tượng tấn công có chủ đích

Lỗi cấu hình, vận hành, phụ thuộc và thiên tai cũng có thể làm mất tính bí mật, toàn vẹn hoặc sẵn sàng. **Khắc phục:** rà soát nhiều nhóm nguồn threat và cơ chế thất bại.

### 11.5. Phụ thuộc hoàn toàn vào threat intelligence bên ngoài

Danh sách mối đe dọa nổi bật trên Internet không chắc phản ánh đặc thù sản phẩm, và kịch bản lạm dụng nghiệp vụ có thể không được nhắc đến. **Khắc phục:** kết hợp luồng dữ liệu, thông tin sản phẩm, nội bộ, kiểm thử và nguồn bên ngoài.

### 11.6. Gắn control mà không kiểm tra bằng chứng

Có MFA, WAF hoặc framework bảo mật không tự chứng minh threat được kiểm soát đủ. **Khắc phục:** kiểm tra control theo security claim cụ thể, phạm vi phù hợp và phiên bản hiện hành.

### 11.7. Không tái đánh giá khi hệ thống thay đổi

Một API, role, thư viện hoặc quyền cloud mới có thể thay đổi đường tiếp cận và mức rủi ro. **Khắc phục:** định nghĩa trigger cập nhật threat scenario trong quá trình thay đổi và vận hành.

## 12. Checklist nhận diện Threat cho một dịch vụ

Trước khi kết thúc vòng rà soát threat, có thể kiểm tra:

- [ ] Tài sản, dữ liệu, chức năng và mục tiêu bảo mật đã được xác định.
- [ ] Luồng dữ liệu và các ranh giới tin cậy chính đã được mô tả.
- [ ] Đã xét đối tượng bên ngoài, nội bộ, sai sót vô ý, phụ thuộc và môi trường.
- [ ] Threat scenario nêu rõ nguồn, hành động, điều kiện và hậu quả.
- [ ] Những giả định hoặc điểm yếu chưa được xác minh đã được ghi riêng.
- [ ] Đã liên kết threat scenario với risk và người chịu trách nhiệm.
- [ ] Yêu cầu bảo mật và control liên quan có tiêu chí kiểm chứng được.
- [ ] Bằng chứng kiểm thử/review/audit gắn đúng hệ thống và phiên bản.
- [ ] Phát hiện có action owner, hạn, cách xác minh và đường chuyển cấp.
- [ ] Có trigger cập nhật khi thay đổi kiến trúc, role, phụ thuộc hoặc có sự cố.
- [ ] Kết luận về residual risk ghi rõ giới hạn và thẩm quyền phê duyệt.

Checklist hỗ trợ cấu trúc công việc, **không thay thế** đánh giá chuyên sâu khi dữ liệu nhạy cảm, giao dịch trọng yếu hoặc yêu cầu an toàn cao.

## 13. Câu hỏi tự kiểm tra

1. Trong kịch bản người dùng A đọc đơn hàng của B, đâu là threat event, vulnerability, risk và security control?
2. Vì sao một threat có thể tồn tại khi chưa phát hiện vulnerability cụ thể?
3. Hãy mô tả một threat vô ý hoặc môi trường đối với dịch vụ Java, nêu hậu quả và biện pháp kiểm soát.
4. Nhóm đã chạy quét dependency không thấy lỗ hổng nghiêm trọng. Điều đó có chứng minh ứng dụng không có threat lộ dữ liệu từ lỗi phân quyền không? Vì sao?
5. Với API công khai truy vấn theo ID, bạn thiết kế những ca kiểm thử nào để chứng minh control phân quyền cấp đối tượng?
6. Khi thay đổi hệ thống danh tính và bổ sung role mới, những threat scenario nào cần xem xét lại?
7. Nếu chưa có bằng chứng rằng một control đang hoạt động ở production, bạn sẽ diễn đạt kết luận residual risk như thế nào?
8. Ai có quyền quyết định chấp nhận rủi ro còn lại, và control owner phải cung cấp những gì cho quyết định đó?

## 14. Ghi nhớ

**Threat** là nguồn, hoàn cảnh hoặc sự kiện **có khả năng gây hại** cho tài sản và mục tiêu bảo mật; threat **khác** vulnerability, risk và incident. Quản lý threat có giá trị khi nhóm mô tả được **kịch bản cụ thể trong bối cảnh hệ thống**, nhận diện điều kiện và hậu quả, chọn security controls phù hợp và thu thập **bằng chứng kiểm chứng được**. Trong chương trình **security assurance liên tục**, các threat scenario phải được cập nhật cùng với thay đổi kiến trúc, triển khai, vận hành và thông tin mới, từ đó giúp tổ chức đưa ra quyết định rủi ro minh bạch, có trách nhiệm.
