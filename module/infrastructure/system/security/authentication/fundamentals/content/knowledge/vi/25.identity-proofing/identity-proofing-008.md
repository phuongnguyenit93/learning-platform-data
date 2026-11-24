# Đánh giá mức độ tin cậy

> **Chương:** Identity proofing  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Đánh giá mức độ tin cậy của quy trình xác minh danh tính, chất lượng bằng chứng, liên kết người nộp hồ sơ với danh tính được khai báo, mức bảo đảm, rủi ro gian lận và quyết định chấp nhận hoặc yêu cầu kiểm tra bổ sung.

## 1. Mức độ tin cậy trong identity proofing là gì?

**Identity proofing (xác minh danh tính ban đầu)** là quy trình thu thập và đánh giá bằng chứng để xác định một người nộp hồ sơ có thực sự là cá nhân mà họ tuyên bố hay không. Quy trình có thể được thực hiện khi tạo tài khoản, cấp credential, mở dịch vụ tài chính, cấp quyền truy cập dữ liệu nhạy cảm hoặc thiết lập quan hệ với một tổ chức.

**Mức độ tin cậy (assurance)** mô tả mức tự tin mà hệ thống có cơ sở để đặt vào kết quả proofing. Mức này phụ thuộc vào chất lượng nguồn bằng chứng, cách kiểm tra tài liệu/thuộc tính, mức độ liên kết người đang làm thủ tục với danh tính được khai báo, khả năng chống giả mạo và rủi ro còn lại.

Ví dụ, một người đăng ký tài khoản ngân hàng từ xa gửi ảnh giấy tờ tùy thân và video selfie. Việc nhận đủ hai tệp không tự động chứng minh danh tính. Hệ thống còn phải đánh giá giấy tờ có thật và còn hiệu lực không, dữ liệu có khớp nguồn đáng tin cậy không, người trong video có liên hệ hợp lý với giấy tờ không, có dấu hiệu ảnh/video giả hay không và quy trình có đủ mạnh cho loại tài khoản đang mở không.

Mức tin cậy không phải một con số có thể suy ra chỉ từ số lượng tài liệu. Hai bản sao của cùng một nguồn không tạo thành hai bằng chứng độc lập; một giấy tờ có vẻ chính thức nhưng không thể xác minh cũng không nhất thiết đáng tin hơn một nguồn điện tử có thẩm quyền.

### Kết quả học tập

Sau bài này, người học có thể:

- Phân biệt identity proofing với authentication và authorization.
- Phân tích chất lượng bằng chứng và độ tin cậy của nguồn phát hành.
- Giải thích các bước resolution, validation và verification.
- Phân biệt IAL với AAL và FAL trong mô hình assurance.
- Chọn quy trình proofing phù hợp với hậu quả khi xác minh sai.
- Đánh giá rủi ro của proofing từ xa, sinh trắc học, phát hiện giả mạo và kiểm tra thủ công.
- Thiết kế quyết định chấp nhận, từ chối, chuyển kiểm tra bổ sung và xử lý khiếu nại có thể kiểm toán.

## 2. Phân biệt proofing, authentication và authorization

Ba hoạt động này giải quyết ba câu hỏi khác nhau:

| Hoạt động | Câu hỏi | Ví dụ |
|---|---|---|
| **Identity proofing** | Người đăng ký có phải người mà họ tuyên bố không? | Kiểm tra giấy tờ, nguồn dữ liệu và liên kết người thật với hồ sơ |
| **Authentication** | Người đang truy cập có kiểm soát credential đã đăng ký không? | Đăng nhập bằng passkey, mật khẩu và MFA |
| **Authorization** | Danh tính đã xác thực được phép làm gì? | Kiểm tra quyền xem hồ sơ hoặc phê duyệt giao dịch |

Một quy trình proofing tốt không bảo đảm mọi lần đăng nhập về sau đều do đúng người thực hiện. Credential có thể bị đánh cắp sau khi proofing. Ngược lại, một passkey chống phishing chứng minh quyền kiểm soát credential mạnh nhưng tự nó không chứng minh tên pháp lý hoặc địa chỉ của người đã đăng ký.

~~~mermaid
flowchart TD
    A["Người nộp hồ sơ khai danh tính"] --> B["Identity proofing"]
    B --> C{"Đủ bằng chứng và liên kết?"}
    C -->|"Không"| D["Bổ sung / kiểm tra thủ công / từ chối"]
    C -->|"Có"| E["Tạo hoặc xác nhận tài khoản"]
    E --> F["Đăng ký authenticator"]
    F --> G["Authentication khi truy cập"]
    G --> H["Authorization theo tài nguyên và hành động"]
~~~

Proofing thường diễn ra ở đầu vòng đời tài khoản, nhưng có thể cần làm lại khi thay đổi định danh trọng yếu, khôi phục tài khoản rủi ro cao hoặc có dấu hiệu gian lận. Không nên nhầm việc xác thực lại bằng passkey với việc proofing lại danh tính pháp lý.

## 3. Các bước cốt lõi: resolution, validation và verification

Một quy trình proofing có thể được mô hình hóa thành ba hoạt động liên quan:

| Bước | Mục tiêu | Câu hỏi chính |
|---|---|---|
| **Identity resolution** | Xác định hồ sơ/danh tính được khai báo có thể được phân biệt trong phạm vi cần thiết | Có đủ thuộc tính để tìm đúng hồ sơ và phân biệt với người khác không? |
| **Evidence/attribute validation** | Kiểm tra bằng chứng và thuộc tính có thật, hợp lệ, còn hiệu lực và đến từ nguồn đáng tin | Tài liệu/thuộc tính này có xác thực và đáng tin không? |
| **Identity verification** | Liên kết người đang làm thủ tục với danh tính hoặc bằng chứng đã được kiểm tra | Người trước hệ thống có phải người được thể hiện trong bằng chứng không? |

### Identity resolution

Resolution thu thập và đối chiếu các thuộc tính như tên, ngày sinh, địa chỉ hoặc mã định danh để tìm hồ sơ phù hợp. Mục tiêu là tránh nhầm hai người có tên giống nhau hoặc tạo nhiều hồ sơ cho cùng một người khi chính sách yêu cầu một danh tính duy nhất.

Resolution phải xử lý khác biệt chính tả, tên đổi theo thời gian, tên có dấu/không dấu, cấu trúc họ tên khác nhau, ngày tháng theo định dạng địa phương và dữ liệu thiếu. Không nên từ chối tự động chỉ vì tên được nhập có dấu khác với nguồn dữ liệu nếu có thể xác minh bằng thuộc tính khác.

### Evidence và attribute validation

Validation đánh giá tính xác thực và độ tin cậy của giấy tờ hoặc dữ liệu:

- Tài liệu có phải do cơ quan/đơn vị được chấp nhận phát hành không?
- Tài liệu còn hiệu lực, chưa bị thu hồi hoặc báo mất không?
- Dữ liệu trên tài liệu có nhất quán và có dấu hiệu chỉnh sửa không?
- Nguồn điện tử có thẩm quyền, cập nhật và được truy cập qua kênh xác thực không?
- Thuộc tính có phù hợp với mục đích và phạm vi sử dụng không?

### Identity verification

Verification kiểm tra người đang thực hiện thủ tục có liên hệ đủ mạnh với danh tính được khai báo hay không. Có thể dùng đối chiếu trực tiếp, video có giám sát, kiểm tra sinh trắc học hoặc một quy trình khác tùy mức rủi ro.

Một tài liệu hợp lệ không chứng minh người cầm nó là chủ thể được ghi trên tài liệu. Ngược lại, nhận diện khuôn mặt thành công không xác nhận tài liệu dùng làm hồ sơ là tài liệu thật. Validation và verification cần được xem xét riêng rồi kết hợp.

## 4. Đánh giá chất lượng bằng chứng

Không phải mọi bằng chứng đều có giá trị như nhau. Có thể đánh giá một bằng chứng theo các chiều:

| Chiều đánh giá | Nội dung | Dấu hiệu cần xem xét |
|---|---|---|
| **Nguồn phát hành** | Ai tạo và chịu trách nhiệm về bằng chứng? | Cơ quan có thẩm quyền, tổ chức được công nhận, nguồn dữ liệu chính thức |
| **Tính xác thực** | Có thể chứng minh bằng chứng không bị giả hoặc sửa không? | Chữ ký số, chip, kiểm tra bảo mật, xác minh trực tiếp với nguồn |
| **Tính hiện hành** | Dữ liệu còn đúng ở thời điểm sử dụng không? | Ngày hết hạn, trạng thái thu hồi, thời điểm đồng bộ |
| **Độ chính xác thuộc tính** | Thuộc tính có khớp người và mục đích cần xác minh không? | Tên, ngày sinh, mã định danh, địa chỉ |
| **Liên kết với người nộp hồ sơ** | Có chứng minh người đang làm thủ tục liên quan đến bằng chứng không? | Đối chiếu trực tiếp, kiểm tra hiện diện, xác minh nguồn |
| **Khả năng chống giả mạo** | Kẻ gian có dễ tạo hoặc sửa bằng chứng không? | Chất lượng chống giả, kênh xác minh, kiểm soát quy trình |
| **Tính độc lập** | Bằng chứng có thực sự độc lập với bằng chứng khác không? | Nguồn, phương thức thu thập và bí mật gốc khác nhau |
| **Phạm vi sử dụng** | Bằng chứng có phù hợp mục đích và khu vực pháp lý không? | Loại dịch vụ, đối tượng, thời hạn, quy định áp dụng |

### Nguồn có thẩm quyền và nguồn tự khai

Nguồn dữ liệu do cơ quan có thẩm quyền quản lý có thể cung cấp độ tin cậy cao hơn một biểu mẫu do chính người đăng ký tự khai, nhưng điều đó phụ thuộc khả năng xác minh nguồn, độ cập nhật, phạm vi dữ liệu và quyền truy cập hợp pháp.

Ví dụ:

- Một thuộc tính được xác nhận trực tiếp qua API của cơ quan phát hành, với kênh và quyền truy cập được kiểm soát.
- Một giấy tờ có thể kiểm tra tính xác thực bằng tính năng bảo mật hoặc dữ liệu điện tử.
- Một bản scan được tải lên nhưng không thể kiểm tra với nguồn phát hành.
- Một câu trả lời tự khai trong biểu mẫu.

Không gắn nhãn “đáng tin” chỉ dựa trên định dạng đẹp hoặc tên cơ quan xuất hiện trên ảnh. Hãy xác minh nguồn và cách thu thập.

### Nhiều bằng chứng không đồng nghĩa nhiều nguồn độc lập

Giả sử người đăng ký cung cấp ảnh giấy tờ, bản PDF của cùng giấy tờ và ảnh chụp màn hình từ ứng dụng lưu bản PDF. Đây có thể là ba tệp nhưng chỉ một nguồn thông tin. Nếu nguồn gốc bị giả, cả ba cùng sai.

Đánh giá tính độc lập bằng cách hỏi liệu một lỗi hoặc một hành vi gian lận có thể làm sai lệch đồng thời các bằng chứng hay không. Hai nguồn cùng sao chép từ một cơ sở dữ liệu không nhất thiết độc lập.

## 5. Mức bảo đảm danh tính: IAL

Trong các khung assurance như NIST Digital Identity Guidelines, **Identity Assurance Level (IAL)** mô tả mức bảo đảm của quy trình proofing và liên kết một người với danh tính được khai báo. IAL tập trung vào độ tin cậy của danh tính đã được xác lập.

IAL không phải điểm số chất lượng chung cho toàn bộ hệ thống. Nó không tự mô tả độ mạnh của mật khẩu, passkey hoặc cách ứng dụng ký assertion.

### Hiểu các mức IAL theo mục tiêu

Các phiên bản tiêu chuẩn và hồ sơ triển khai có thể quy định yêu cầu chi tiết khác nhau. Ở mức khái niệm:

| Mức bảo đảm | Mục tiêu khái quát | Cách cân nhắc |
|---|---|---|
| **IAL1** | Rủi ro khi danh tính khai báo sai tương đối thấp; mức proofing có thể tối thiểu theo profile áp dụng | Dịch vụ ít nhạy cảm, không cần xác lập danh tính pháp lý mạnh |
| **IAL2** | Cần bằng chứng và liên kết danh tính mạnh hơn, có kiểm tra thuộc tính/nguồn theo profile | Dịch vụ cần tin cậy rõ hơn vào danh tính của người dùng |
| **IAL3** | Mức proofing cao, quy trình xác minh chặt chẽ và kiểm soát trực tiếp hơn theo profile áp dụng | Trường hợp hậu quả giả mạo danh tính rất lớn hoặc yêu cầu pháp lý đặc thù |

Bảng chỉ giúp hình dung sự khác nhau về mục tiêu; **không phải danh sách yêu cầu triển khai đầy đủ hoặc thay thế tiêu chuẩn**. Khi tuyên bố tuân thủ một IAL, phải đối chiếu đúng phiên bản NIST/profile, loại bằng chứng, quy trình, kiểm soát nhân sự, phương thức từ xa/trực tiếp và yêu cầu kiểm toán đang áp dụng.

### IAL không phải AAL hay FAL

| Mức | Đánh giá điều gì? | Ví dụ câu hỏi |
|---|---|---|
| **IAL — Identity Assurance Level** | Mức tin cậy của danh tính được proofing | Người này có phải người họ khai báo không? |
| **AAL — Authenticator Assurance Level** | Mức bảo đảm của quá trình authentication | Người đang truy cập có kiểm soát authenticator phù hợp không? |
| **FAL — Federation Assurance Level** | Mức bảo đảm của việc truyền assertion/token trong federation | Bằng chứng liên kết được bảo vệ và gửi đến RP đúng cách không? |

Một tài khoản có thể được proofing ở mức cao nhưng người dùng lại đăng nhập bằng mật khẩu yếu, làm AAL thấp. Một người có passkey mạnh có thể đạt authentication tốt nhưng danh tính pháp lý ban đầu chưa được proofing. Một assertion được ký đúng nhưng RP không kiểm tra audience cũng có thể làm suy yếu federation.

Không cộng IAL, AAL và FAL thành một con số. Chúng đo các rủi ro khác nhau trong cùng hệ thống.

## 6. Chọn mức proofing theo rủi ro

Không phải mọi dịch vụ đều cần thu thập giấy tờ và sinh trắc học. Quy trình proofing nên tương xứng với hậu quả nếu chấp nhận nhầm một danh tính.

Đánh giá tối thiểu:

1. **Tài sản được bảo vệ:** dữ liệu, tiền, quyền truy cập hoặc lợi ích nào gắn với tài khoản?
2. **Hậu quả khi giả mạo:** thiệt hại tài chính, quyền riêng tư, an toàn hoặc pháp lý là gì?
3. **Động cơ và năng lực tấn công:** kẻ gian có thể thu lợi bao nhiêu và có thể chuẩn bị bằng chứng giả ở mức nào?
4. **Đối tượng sử dụng:** người dùng có giấy tờ chuẩn, thiết bị hiện đại, kết nối ổn định và khả năng tiếp cận quy trình không?
5. **Khả năng giảm thiểu sau proofing:** có thể giới hạn giao dịch, chờ xác minh bổ sung hoặc thu hồi tài khoản không?
6. **Nghĩa vụ pháp lý:** ngành và khu vực hoạt động có yêu cầu cụ thể nào không?

### Ma trận quyết định minh họa

| Dịch vụ | Hậu quả nếu xác minh sai | Hướng proofing có thể phù hợp |
|---|---|---|
| Tài khoản xem nội dung công khai | Thấp | Thu thập tối thiểu, có thể không cần proofing giấy tờ |
| Tài khoản diễn đàn có quyền đăng bài | Thấp đến trung bình | Xác minh liên hệ hoặc tín hiệu phù hợp với abuse risk |
| Cổng nhân viên nội bộ | Trung bình đến cao | Dựa trên nguồn nhân sự có thẩm quyền và quy trình onboarding |
| Ví điện tử hoặc tài khoản tài chính | Cao | Proofing theo yêu cầu pháp lý, chống giả mạo và kiểm soát gian lận |
| Tài khoản quản trị hạ tầng trọng yếu | Rất cao | Xác lập danh tính chặt chẽ, phê duyệt độc lập và credential mạnh |

Các ví dụ không thay thế phân tích pháp lý hoặc đánh giá rủi ro của tổ chức. Không chọn mức proofing cao nhất cho mọi dịch vụ một cách máy móc: thu thập quá mức có thể làm tăng rủi ro dữ liệu và loại trừ người dùng hợp lệ.

## 7. Proofing trực tiếp và từ xa

### Trực tiếp (in-person)

Người nộp hồ sơ xuất trình bằng chứng trước nhân viên hoặc điểm tiếp nhận được kiểm soát. Nhân viên có thể kiểm tra tài liệu, đối chiếu người thật và thực hiện quy trình theo hướng dẫn.

Ưu điểm:

- Có thể quan sát trực tiếp tài liệu và người nộp hồ sơ.
- Có thể dùng thiết bị kiểm tra tài liệu chuyên dụng.
- Có cơ hội giải quyết khác biệt hoặc câu hỏi ngay tại chỗ.

Giới hạn:

- Nhân viên có thể bị đánh lừa bởi giấy tờ giả hoặc bị ép buộc.
- Chất lượng phụ thuộc đào tạo, thiết bị và quy trình.
- Điểm tiếp nhận có thể không tiếp cận được với người ở xa hoặc người khuyết tật.
- Rủi ro nội gián và thông đồng vẫn tồn tại.

### Từ xa (remote)

Người nộp hồ sơ gửi dữ liệu điện tử hoặc thực hiện xác minh qua ứng dụng/video. Quy trình có thể kết hợp kiểm tra tài liệu, nguồn dữ liệu, selfie, kiểm tra hiện diện và tín hiệu thiết bị.

Ưu điểm:

- Tiếp cận người dùng ở nhiều địa điểm.
- Có thể tự động hóa kiểm tra và ghi lại bằng chứng kiểm toán.
- Giảm phụ thuộc vào điểm tiếp nhận vật lý.

Giới hạn:

- Ảnh/video có thể bị chỉnh sửa, phát lại hoặc tạo bằng công nghệ giả mạo.
- Thiết bị, camera, ánh sáng và kết nối ảnh hưởng chất lượng.
- Malware hoặc điều khiển từ xa có thể can thiệp quy trình.
- Tín hiệu IP/thiết bị có thể sai lệch hoặc tạo thiên lệch.
- Người dùng thiếu giấy tờ hoặc thiết bị tương thích có thể bị loại nhầm.

Không có phương thức nào tự động đáng tin chỉ vì được thực hiện trực tiếp hoặc từ xa. Mức assurance phụ thuộc tổng thể bằng chứng, kiểm soát và quy trình theo profile đã chọn.

## 8. Sinh trắc học và kiểm tra hiện diện

Sinh trắc học như khuôn mặt, vân tay hoặc giọng nói có thể hỗ trợ liên kết người nộp hồ sơ với tài liệu hoặc xác nhận người dùng đang có mặt. Tuy nhiên, sinh trắc học có giới hạn và không nên được xem là bằng chứng danh tính độc lập trong mọi tình huống.

### Face match và liveness

- **Face match:** so sánh đặc trưng khuôn mặt trong ảnh/video với ảnh tham chiếu.
- **Liveness/presentation attack detection:** tìm dấu hiệu ảnh in, màn hình phát lại, mặt nạ hoặc hình thức trình bày giả trước cảm biến.
- **Remote presence check:** đánh giá tương tác trực tiếp trong phiên từ xa theo một quy trình xác định.

Một kết quả face match cao không chứng minh giấy tờ là thật, cũng không bảo đảm người đang xuất hiện không bị ép buộc. Liveness detection có thể bị vượt qua và có tỷ lệ từ chối nhầm. Cần đánh giá hiệu năng trong điều kiện sử dụng thực tế, nhóm người dùng khác nhau và loại tấn công liên quan.

### Không đồng nhất xác minh sinh trắc học với proofing

Vân tay mở khóa điện thoại thường chứng minh người dùng đã vượt qua cơ chế mở khóa cục bộ của thiết bị. Nó không tự chứng minh người đó có tên pháp lý nào. Passkey có thể dùng sinh trắc học cục bộ để cho phép authenticator sử dụng khóa riêng; RP nhận bằng chứng mật mã, không cần nhận mẫu sinh trắc học thô.

### Quyền riêng tư và an toàn sinh trắc học

- Chỉ thu thập sinh trắc học khi có căn cứ và nhu cầu rõ ràng.
- Ưu tiên xử lý cục bộ hoặc cơ chế giảm tiết lộ nếu phù hợp.
- Không lưu ảnh/mẫu thô lâu hơn cần thiết.
- Bảo vệ template, dữ liệu so khớp và kết quả liveness như dữ liệu nhạy cảm.
- Có phương thức thay thế cho người không thể sử dụng sinh trắc học.
- Không cho phép kết quả sinh trắc học đơn lẻ tự động mở mọi quyền có giá trị cao.

Sinh trắc học không giống mật khẩu: người dùng không thể dễ dàng thay đổi khuôn mặt hoặc vân tay khi dữ liệu bị lộ.

## 9. Rủi ro gian lận trong proofing

Kẻ tấn công có thể nhắm vào từng bước của quy trình:

| Tấn công | Mục tiêu | Ví dụ kiểm soát |
|---|---|---|
| Tài liệu giả hoặc chỉnh sửa | Vượt qua validation | Kiểm tra tính năng bảo mật, nguồn phát hành và dữ liệu điện tử |
| Synthetic identity | Ghép dữ liệu thật và giả để tạo người không tồn tại | Đối chiếu nhiều nguồn độc lập, kiểm tra lịch sử và tính nhất quán |
| Identity theft | Dùng danh tính thật của người khác | Verification liên kết người nộp hồ sơ với bằng chứng |
| Replay ảnh/video | Dùng lại dữ liệu đã thu thập | Challenge ngẫu nhiên, kiểm tra phiên và phát hiện phát lại |
| Deepfake / injection | Thay hoặc chèn luồng camera | Kiểm soát thiết bị, phát hiện injection và đánh giá nhiều tín hiệu |
| Social engineering | Lừa nhân viên hoặc người dùng bỏ qua quy trình | Kịch bản hỗ trợ chuẩn, phê duyệt và đào tạo |
| Insider fraud | Nhân viên cố tình duyệt hồ sơ sai | Phân tách nhiệm vụ, audit và kiểm tra mẫu |
| Account farming | Tạo nhiều tài khoản giả | Phân tích trùng lặp, rate limit và kiểm soát abuse |
| Coercion | Người thật bị ép thực hiện proofing | Cơ chế hỗ trợ an toàn và quy trình xử lý ngoại lệ |
| Data-source compromise | Khai thác nguồn đối chiếu bị sửa hoặc bị chiếm | Xác thực kênh, giám sát nguồn và kiểm tra độc lập |

### Đừng dựa vào một tín hiệu rủi ro

Địa chỉ IP, vị trí, loại thiết bị, tốc độ thao tác hoặc dấu hiệu bất thường có thể giúp phát hiện gian lận nhưng không phải bằng chứng kết luận danh tính giả. Người dùng hợp lệ có thể dùng VPN, thiết bị cũ, mạng công cộng hoặc công nghệ hỗ trợ.

Kết hợp nhiều tín hiệu với bằng chứng có thẩm quyền và mức độ ảnh hưởng. Khi tín hiệu mâu thuẫn, chuyển sang kiểm tra bổ sung thay vì tự động kết luận gian lận nếu chưa có căn cứ.

## 10. Đánh giá tổng thể và quyết định proofing

Một quyết định proofing nên ghi rõ:

- Danh tính/thuộc tính nào đã được xác minh.
- Bằng chứng và nguồn nào đã được dùng.
- Các bước validation và verification nào đã hoàn tất.
- Mức assurance/profile được áp dụng.
- Rủi ro còn lại và ngoại lệ được chấp nhận.
- Người hoặc hệ thống chịu trách nhiệm ra quyết định.
- Thời điểm, phiên bản quy trình và dữ liệu kiểm toán cần thiết.

### Các kết quả có thể có

| Kết quả | Khi nào dùng | Hành động |
|---|---|---|
| **Accept** | Bằng chứng đạt yêu cầu, rủi ro còn lại trong ngưỡng | Hoàn tất proofing và chuyển sang đăng ký authenticator |
| **Step-up / additional evidence** | Thiếu một phần bằng chứng hoặc có tín hiệu cần kiểm tra thêm | Yêu cầu nguồn/bước độc lập bổ sung |
| **Manual review** | Tự động không đủ cơ sở, dữ liệu có ngoại lệ hoặc cần chuyên viên | Chuyển hồ sơ theo hàng đợi và quy trình kiểm soát |
| **Pending** | Đang chờ nguồn xác minh hoặc người nộp hồ sơ hoàn tất bước | Giữ trạng thái giới hạn, không cấp quyền vượt mức |
| **Reject** | Có bằng chứng không đạt hoặc rủi ro không thể chấp nhận | Từ chối theo quy trình, giải thích phù hợp và cho phép khiếu nại khi cần |

Không nên biến điểm số của một nhà cung cấp thành quyết định duy nhất nếu không hiểu dữ liệu, ngưỡng, tỷ lệ sai và điều kiện áp dụng. Tổ chức cần biết trường hợp nào bị từ chối tự động, ai có quyền override và override phải được ghi nhận ra sao.

### False accept và false reject

- **False accept:** hệ thống chấp nhận người không phải chủ thể hợp lệ. Có thể dẫn đến chiếm danh tính, gian lận hoặc truy cập trái phép.
- **False reject:** hệ thống từ chối người hợp lệ. Có thể khiến người dùng mất quyền tiếp cận dịch vụ hoặc phải tiết lộ thêm dữ liệu.

Thiết kế cần cân bằng hai loại lỗi theo hậu quả, đồng thời cung cấp đường hỗ trợ và khiếu nại. Không tối ưu một tỷ lệ chính xác tổng thể mà bỏ qua nhóm người dùng bị ảnh hưởng không cân xứng.

## 11. Kiểm tra thủ công và quản trị ngoại lệ

Kiểm tra thủ công hữu ích khi tài liệu khó đọc, tên không khớp do thay đổi hợp pháp, nguồn dữ liệu tạm thời không truy cập được hoặc hệ thống tự động phát hiện bất thường. Tuy nhiên, nhân viên cũng là một phần của ranh giới tin cậy.

Kiểm soát cần có:

1. Hướng dẫn quyết định thống nhất và ví dụ tình huống.
2. Đào tạo về giấy tờ, giả mạo, social engineering và quyền riêng tư.
3. Phân tách nhiệm vụ với hồ sơ có giá trị cao.
4. Phê duyệt thứ hai cho trường hợp override hoặc ngoại lệ đặc biệt.
5. Audit người xem, người sửa và người ra quyết định.
6. Giới hạn khả năng tải xuống hoặc sao chép dữ liệu nhạy cảm.
7. Kênh khiếu nại và quy trình sửa dữ liệu sai.

Không để nhân viên hỗ trợ bỏ qua proofing chỉ vì người gọi biết một số thông tin cá nhân. Thông tin có thể tìm thấy trên mạng hoặc bị lộ từ sự cố dữ liệu trước đó.

## 12. Quyền riêng tư, công bằng và khả năng tiếp cận

Proofing có thể yêu cầu dữ liệu rất nhạy cảm: ảnh giấy tờ, địa chỉ, ngày sinh, video khuôn mặt, dữ liệu sinh trắc học hoặc thông tin từ nguồn chính phủ. Thu thập càng nhiều không đồng nghĩa mức assurance càng cao.

### Data minimization

- Chỉ thu thập thuộc tính cần cho mục đích xác minh.
- Xác định dữ liệu nào cần lưu, dữ liệu nào chỉ cần kiểm tra rồi xóa.
- Đặt thời hạn lưu và quy tắc xóa bản sao.
- Mã hóa khi truyền và lưu trữ; giới hạn quyền truy cập.
- Không đưa ảnh giấy tờ, sinh trắc học hoặc mã định danh vào log thông thường.
- Hạn chế chia sẻ dữ liệu proofing với nhà cung cấp; xác định vai trò và trách nhiệm xử lý.

### Công bằng và accessibility

Một quy trình chỉ hỗ trợ giấy tờ của một số quốc gia, camera mới hoặc khả năng thực hiện thao tác nhất định có thể loại trừ người dùng hợp lệ. Các trường hợp cần xem xét:

- Người cao tuổi hoặc người khuyết tật.
- Người có ngoại hình thay đổi, đặc điểm khuôn mặt khác biệt hoặc không thể dùng camera.
- Người không có giấy tờ chuẩn hoặc đang chờ cấp lại giấy tờ.
- Người sống ở vùng mạng yếu hoặc không có thiết bị phù hợp.
- Tên có cấu trúc, dấu, phiên âm hoặc cách viết khác nhau.
- Người dùng cần hỗ trợ ngôn ngữ hoặc công nghệ hỗ trợ.

Nên cung cấp phương thức thay thế có mức kiểm soát tương xứng, hỗ trợ trực tiếp hoặc quy trình ngoại lệ được kiểm toán. Phương thức thay thế không nên trở thành đường vòng dễ bị tấn công hơn.

### Đánh giá nhà cung cấp proofing

Nếu dùng dịch vụ bên thứ ba, cần hiểu:

- Nguồn dữ liệu và quyền truy cập của nhà cung cấp.
- Tỷ lệ false accept/false reject và cách đo.
- Hiệu năng trên các nhóm người dùng và điều kiện thiết bị khác nhau.
- Cách xử lý ảnh/video, template sinh trắc học và dữ liệu lưu trữ.
- Khả năng giải thích quyết định, audit và hỗ trợ khiếu nại.
- Cơ chế thông báo sự cố, xóa dữ liệu và chuyển đổi nhà cung cấp.

Không coi chứng nhận hoặc điểm benchmark là bằng chứng rằng hệ thống phù hợp mọi bối cảnh. Cần đánh giá theo use case và điều kiện vận hành thật.

## 13. Proofing và vòng đời danh tính

Proofing ban đầu là một mốc trong vòng đời danh tính, không phải bảo đảm vĩnh viễn rằng mọi thuộc tính luôn đúng.

Các sự kiện có thể cần kiểm tra lại:

- Thay đổi tên pháp lý hoặc mã định danh.
- Tài liệu hết hạn hoặc bị thu hồi.
- Thay đổi tư cách nhân viên, khách hàng hoặc người đại diện.
- Khôi phục tài khoản bằng quy trình có rủi ro cao.
- Dấu hiệu synthetic identity hoặc chiếm danh tính.
- Thay đổi tổ chức/tenant hoặc chuyển quyền sở hữu tài khoản.
- Yêu cầu pháp lý hoặc chính sách mới.

### Re-proofing không phải đăng nhập lại

Đăng nhập lại bằng passkey xác nhận người dùng kiểm soát authenticator đã đăng ký. Re-proofing kiểm tra lại danh tính hoặc thuộc tính nền tảng. Hai việc có thể được kích hoạt bởi cùng một sự kiện nhưng không thể thay thế nhau.

Ví dụ, một người đổi số điện thoại khôi phục không nhất thiết phải proofing lại toàn bộ giấy tờ nếu quy trình xác minh số điện thoại đủ mạnh. Nhưng nếu có dấu hiệu tài khoản được tạo bằng danh tính giả, hệ thống có thể phải đánh giá lại bằng chứng gốc.

### Tách dữ liệu proofing khỏi dữ liệu đăng nhập

Ảnh giấy tờ và kết quả proofing thường có yêu cầu lưu trữ/quyền truy cập khác với session ID hoặc password verifier. Nên tách kho dữ liệu và quyền truy cập để một lỗi ở dịch vụ đăng nhập không tự động cho phép đọc toàn bộ hồ sơ proofing.

## 14. Tình huống thực hành: mở tài khoản dịch vụ tài chính từ xa

**Bối cảnh:** Một ứng dụng tài chính cho phép khách hàng mở tài khoản từ điện thoại. Hậu quả khi chấp nhận nhầm danh tính cao, nhưng quy trình cần hỗ trợ người dùng ở nhiều địa phương và nhiều loại thiết bị.

### Thiết kế proofing

1. Giải thích mục đích và dữ liệu cần thu thập trước khi bắt đầu.
2. Thu thập thuộc tính tối thiểu để resolution và chọn nguồn đối chiếu hợp pháp.
3. Nhận bằng chứng danh tính theo loại được chính sách chấp nhận.
4. Validation tài liệu bằng các đặc điểm bảo mật và nguồn xác minh phù hợp.
5. Verification liên kết người nộp hồ sơ với bằng chứng bằng quy trình từ xa đã được đánh giá.
6. Phân tích tín hiệu gian lận nhưng không dùng IP hoặc điểm khuôn mặt đơn lẻ làm quyết định.
7. Chuyển trường hợp không rõ ràng sang manual review hoặc kênh thay thế.
8. Ghi nhận quyết định, nguồn, phiên bản quy trình và thời điểm.
9. Sau khi proofing đạt, mới thiết lập tài khoản và đăng ký authenticator.
10. Áp dụng authentication và authorization phù hợp cho các lần sử dụng sau.

### Bảng đánh giá mẫu

| Thành phần | Câu hỏi | Kết quả giả định |
|---|---|---|
| Resolution | Thuộc tính có xác định đúng hồ sơ không? | Khớp một hồ sơ trong nguồn được chấp nhận |
| Validation | Tài liệu có thật và còn hiệu lực không? | Các kiểm tra bắt buộc đạt |
| Verification | Người đang làm thủ tục có liên hệ với tài liệu không? | Đạt theo quy trình đã đánh giá |
| Fraud signals | Có dấu hiệu phát lại hoặc giả mạo không? | Không có tín hiệu vượt ngưỡng; vẫn ghi nhận rủi ro còn lại |
| Accessibility | Người dùng có cần phương thức thay thế không? | Có lựa chọn hỗ trợ khi camera không đáp ứng |
| Decision | Quy trình đạt profile đã chọn không? | Accept hoặc manual review theo quy tắc, không dựa vào một điểm tổng hợp duy nhất |

### Nếu giấy tờ hợp lệ nhưng khuôn mặt không khớp

Không nên tự động kết luận gian lận chỉ từ một lần so khớp thất bại. Có thể do ánh sáng, camera, thay đổi ngoại hình, chất lượng ảnh hoặc lỗi kỹ thuật. Hệ thống có thể cho phép thử lại có giới hạn, yêu cầu phương thức thay thế hoặc chuyển manual review. Nếu có bằng chứng giả mạo độc lập, xử lý theo quy trình sự cố.

### Nếu người dùng không có smartphone phù hợp

Cung cấp phương thức thay thế được kiểm soát như điểm tiếp nhận, xác minh qua kênh hỗ trợ có giám sát hoặc quy trình giấy tờ khác được phê duyệt. Không giảm yêu cầu bảo đảm một cách âm thầm chỉ để tăng tỷ lệ hoàn tất.

## 15. Kiểm thử và đo lường chất lượng proofing

Kiểm thử nên đánh giá cả khả năng phát hiện gian lận lẫn tác động tới người dùng hợp lệ.

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Tài liệu hết hạn | Không được chấp nhận như tài liệu còn hiệu lực |
| Tài liệu có dấu hiệu chỉnh sửa | Chuyển kiểm tra bổ sung hoặc từ chối theo chính sách |
| Nguồn xác minh không truy cập được | Không tự coi là đạt; chuyển pending/fallback |
| Thuộc tính xung đột giữa hai nguồn | Xử lý theo quy tắc ưu tiên và manual review |
| Hai bằng chứng cùng từ một nguồn gốc | Không tính là hai nguồn độc lập |
| Ảnh/video phát lại | Kiểm soát chống replay phát hiện hoặc yêu cầu bước bổ sung |
| Kết quả sinh trắc học thấp do chất lượng ảnh | Có retry/fallback công bằng, không tự động gán gian lận |
| Subject có tên tương tự người khác | Resolution không ghép nhầm hồ sơ |
| Nhân viên override quyết định | Có lý do, phê duyệt và audit |
| Nguồn dữ liệu bị lỗi hoặc cũ | Có trạng thái pending và cảnh báo, không chấp nhận mù quáng |
| Dữ liệu proofing bị truy cập trái quyền | Bị chặn và có audit |
| Người dùng khiếu nại quyết định | Có quy trình xem xét lại bởi người có thẩm quyền |
| Thay đổi giấy tờ hoặc thuộc tính trọng yếu | Kích hoạt kiểm tra lại theo chính sách |
| Account recovery rủi ro cao | Không chỉ dựa vào một yếu tố dễ giả mạo |

### Chỉ số nên theo dõi

- Tỷ lệ hoàn tất proofing theo phương thức và nhóm thiết bị.
- Tỷ lệ false accept/false reject theo đánh giá độc lập phù hợp.
- Tỷ lệ chuyển manual review và thời gian xử lý.
- Tỷ lệ khiếu nại được chấp thuận sau xem xét.
- Tỷ lệ gian lận được phát hiện sau khi tài khoản đã mở.
- Tỷ lệ lỗi từ nguồn dữ liệu hoặc nhà cung cấp.
- Thời gian thu hồi/điều chỉnh tài khoản sau phát hiện sai.
- Chênh lệch kết quả giữa các nhóm người dùng và điều kiện tiếp cận.

Chỉ số cần được diễn giải trong bối cảnh. Tỷ lệ từ chối thấp không có nghĩa proofing tốt nếu hệ thống chấp nhận nhiều danh tính giả; tỷ lệ phát hiện gian lận cao cũng không tốt nếu false reject tăng mạnh.

## 16. Checklist đánh giá mức độ tin cậy

- [ ] Mục đích proofing, danh tính/thuộc tính cần xác minh và hậu quả khi sai đã rõ.
- [ ] Phân biệt resolution, validation và verification.
- [ ] Nguồn bằng chứng có thẩm quyền và kênh xác minh được kiểm tra.
- [ ] Tài liệu/thuộc tính được đánh giá về tính xác thực, hiện hành, chính xác và phạm vi.
- [ ] Người nộp hồ sơ được liên kết với bằng chứng theo quy trình phù hợp.
- [ ] Tính độc lập của nhiều bằng chứng được đánh giá; không đếm số tệp thay cho nguồn độc lập.
- [ ] Mức IAL/profile được chọn theo rủi ro và phiên bản tiêu chuẩn áp dụng.
- [ ] IAL, AAL và FAL được phân biệt; không gộp thành một chỉ số.
- [ ] Proofing từ xa/trực tiếp có threat model và kiểm soát phù hợp.
- [ ] Sinh trắc học/liveness được đánh giá về false accept, false reject, spoofing và accessibility.
- [ ] Tín hiệu rủi ro không tự động thay thế bằng chứng danh tính có thẩm quyền.
- [ ] Có quyết định accept, pending, step-up, manual review và reject rõ ràng.
- [ ] Có phân tách nhiệm vụ, audit và phê duyệt khi override.
- [ ] Có cơ chế khiếu nại và phương thức thay thế cho người dùng hợp lệ.
- [ ] Thu thập/lưu trữ dữ liệu tối thiểu, giới hạn truy cập và thời hạn lưu.
- [ ] Có quy trình re-proofing, cập nhật thuộc tính và offboarding.
- [ ] Kiểm thử cả fraud detection, false reject, quyền riêng tư và tác động công bằng.

## Ghi nhớ

Đánh giá mức độ tin cậy trong identity proofing là đánh giá xem bằng chứng và quy trình có đủ cơ sở để liên kết người nộp hồ sơ với danh tính họ khai báo hay không. Hãy tách **resolution** (tìm đúng hồ sơ), **validation** (kiểm tra bằng chứng/thuộc tính) và **verification** (liên kết người thật với danh tính).

IAL nói về bảo đảm danh tính; AAL nói về bảo đảm xác thực; FAL nói về bảo đảm federation. Chọn mức proofing theo hậu quả khi xác minh sai, chất lượng và tính độc lập của nguồn bằng chứng, rủi ro gian lận, quyền riêng tư và khả năng tiếp cận. Kết quả proofing không thay thế authentication về sau, và một quyết định tốt phải có thể giải thích, kiểm toán và xem xét lại.
