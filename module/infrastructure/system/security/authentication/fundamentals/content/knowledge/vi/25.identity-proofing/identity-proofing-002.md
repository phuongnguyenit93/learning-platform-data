# Thu thập thuộc tính

## 1. Thu thập thuộc tính trong identity proofing là gì?

**Thu thập thuộc tính (attribute collection)** là quá trình lấy những thông tin cần thiết để xác lập và đánh giá một danh tính trong quy trình **identity proofing**. Thuộc tính có thể là họ tên, ngày sinh, địa chỉ, mã định danh, thông tin liên hệ hoặc dữ liệu khác cần thiết cho mục đích cụ thể. Nguồn dữ liệu có thể do người dùng tự khai, lấy từ giấy tờ/bằng chứng, xác minh với nguồn có thẩm quyền hoặc nhận từ một nhà cung cấp danh tính đáng tin cậy.

Identity proofing nhằm đánh giá một người có tồn tại và người đang thực hiện quy trình có liên hệ đủ tin cậy với danh tính được khai báo hay không. Thu thập dữ liệu chỉ là một phần của quy trình. Việc người dùng nhập họ tên và ngày sinh **không tự chứng minh** các thuộc tính đó đúng; việc nhận một bản ảnh giấy tờ cũng chưa chứng minh giấy tờ là thật hoặc người gửi là chủ thể trên giấy tờ.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, thu thập thuộc tính là bước nền để hiểu liên kết giữa danh tính, credential, xác thực, liên kết tài khoản và khôi phục. Một quy trình tốt phải xác định rõ cần biết điều gì, lấy từ đâu, kiểm tra ra sao, lưu trong bao lâu và sử dụng kết quả ở đâu. Thu thập quá nhiều dữ liệu làm tăng rủi ro riêng tư và hậu quả khi xảy ra rò rỉ; thu thập thiếu hoặc sai mục đích có thể dẫn tới ghép nhầm người, mở tài khoản giả hoặc từ chối nhầm người dùng hợp lệ.

Sau bài học, người học có thể:

- Phân biệt thuộc tính, định danh, bằng chứng và credential.
- Xác định tập thuộc tính tối thiểu theo mục đích và mức rủi ro.
- Đánh giá nguồn dữ liệu và độ tin cậy của từng thuộc tính.
- Phân biệt capture, validation và verification.
- Ghi nhận nguồn gốc, thời điểm, độ mới và kết quả kiểm tra của dữ liệu.
- Xử lý khác biệt tên, địa chỉ, ngày sinh và dữ liệu không nhất quán.
- Bảo vệ dữ liệu cá nhân, giới hạn lưu trữ và thiết kế quy trình sửa/đổi thuộc tính.
- Nhận diện gian lận danh tính, synthetic identity và các điểm yếu trong thu thập từ xa.

## 2. Thuộc tính, định danh, bằng chứng và credential

Các khái niệm có liên quan nhưng không thể thay thế cho nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Attribute (thuộc tính)** | Một thông tin mô tả chủ thể | Họ tên, ngày sinh, địa chỉ, email |
| **Identifier (định danh)** | Giá trị dùng để phân biệt hoặc tra cứu một bản ghi/chủ thể trong một phạm vi | Mã khách hàng, số hồ sơ, subject ID |
| **Evidence (bằng chứng)** | Tài liệu, nguồn hoặc tín hiệu được dùng để hỗ trợ xác minh thuộc tính/danh tính | Giấy tờ do cơ quan có thẩm quyền cấp, dữ liệu từ nguồn chính thức |
| **Credential** | Vật/bí mật/phương tiện mà chủ thể dùng để chứng minh quyền kiểm soát khi xác thực | Password, passkey, security key, chứng chỉ |
| **Identity record** | Bản ghi danh tính nội bộ gồm các thuộc tính và metadata có liên quan | Hồ sơ người dùng gắn với các thuộc tính đã được kiểm tra |

Ví dụ: email là một thuộc tính liên hệ. Khi người dùng nhấp liên kết xác minh email, hệ thống có bằng chứng họ kiểm soát hộp thư tại thời điểm đó. Điều này **không tự chứng minh** họ là người có tên pháp lý tương ứng với email. Tương tự, OTP gửi tới số điện thoại chứng minh quyền truy cập kênh nhận mã trong một thời điểm, không tự chứng minh danh tính pháp lý của người nhận.

Một passkey chứng minh quyền kiểm soát khóa riêng tương ứng với credential đã đăng ký cho relying party. Nó không tự xác nhận ngày sinh, địa chỉ hoặc danh tính pháp lý của người dùng. Identity proofing và authentication giải quyết hai câu hỏi khác nhau, dù sản phẩm có thể kết hợp chúng trong cùng một hành trình.

## 3. Bắt đầu từ mục đích: cần thu thập thuộc tính nào?

Trước khi tạo form hoặc tích hợp nguồn dữ liệu, hãy viết rõ mục đích cần đạt. Mỗi thuộc tính phải có lý do sử dụng cụ thể.

Ví dụ:

- Tạo tài khoản đọc nội dung có thể chỉ cần một định danh đăng nhập và phương thức liên hệ.
- Mở tài khoản có giao dịch tài chính có thể cần thêm thuộc tính theo quy định, kiểm tra danh tính và đánh giá rủi ro phù hợp.
- Cấp quyền truy cập cho nhân viên có thể cần mã nhân sự, đơn vị, trạng thái công việc và nguồn xác nhận từ hệ thống HR.
- Cấp chứng chỉ chuyên môn có thể cần tên trên chứng chỉ, mã chứng chỉ và xác nhận từ tổ chức phát hành.

Không nên yêu cầu ngày sinh, số giấy tờ, địa chỉ nhà hoặc ảnh khuôn mặt chỉ vì các trường đó có sẵn trong mẫu form. Hãy xác định mỗi thuộc tính có cần cho quyết định, nghĩa vụ pháp lý, an toàn tài khoản hoặc vận hành hay không.

### 3.1. Data minimization

**Data minimization** là chỉ thu thập dữ liệu phù hợp, liên quan và cần thiết cho mục đích đã xác định. Nguyên tắc này giảm lượng dữ liệu có thể bị lộ, giảm chi phí lưu trữ và giúp người dùng hiểu vì sao hệ thống cần thông tin.

Một số cách áp dụng:

- Chỉ yêu cầu các trường thực sự cần thiết; không đánh dấu mọi trường là bắt buộc.
- Nếu chỉ cần biết người dùng đủ tuổi, cân nhắc nhận kết quả “đạt ngưỡng tuổi” từ nguồn đáng tin thay vì lưu ngày sinh đầy đủ, khi quy định và thiết kế cho phép.
- Nếu chỉ cần xác nhận địa chỉ, cân nhắc lưu trạng thái/địa chỉ đã xác minh và nguồn xác minh thay vì giữ bản sao hóa đơn dài hạn.
- Nếu chỉ cần xác minh một giấy tờ, không mặc định lưu cả ảnh mặt trước/mặt sau sau khi quy trình hoàn tất.
- Không thu thập số giấy tờ, dữ liệu sinh trắc hoặc thông tin gia đình để “phòng khi cần” mà không có mục đích rõ.
- Tách dữ liệu bắt buộc theo luật/chính sách khỏi dữ liệu tùy chọn phục vụ trải nghiệm.

Data minimization không có nghĩa bỏ qua bằng chứng cần thiết. Với mục đích có rủi ro cao hoặc nghĩa vụ pháp lý, có thể cần tập dữ liệu lớn hơn; quyết định đó phải được ghi nhận, giới hạn truy cập và có thời hạn lưu phù hợp.

### 3.2. Ma trận mục đích và thuộc tính

| Mục đích | Thuộc tính có thể cần | Câu hỏi phải trả lời |
| --- | --- | --- |
| Tạo tài khoản cơ bản | Tên hiển thị, email hoặc số điện thoại | Có cần xác minh danh tính thật hay chỉ cần định danh liên hệ? |
| Khôi phục tài khoản | Credential dự phòng, kênh liên hệ đã xác minh, lịch sử tài khoản phù hợp | Bằng chứng recovery có đủ tin cậy và không tạo đường vòng yếu? |
| Kiểm tra độ tuổi | Kết quả đạt ngưỡng, hoặc ngày sinh khi thực sự cần | Có thể giảm dữ liệu được lưu không? |
| Nhân sự nội bộ | Mã nhân viên, trạng thái làm việc, đơn vị | Nguồn HR nào là nguồn có thẩm quyền? |
| Tài khoản có yêu cầu KYC | Thuộc tính và bằng chứng theo quy định áp dụng | Yêu cầu pháp lý nào bắt buộc và thời hạn lưu là bao lâu? |
| Cấp chứng chỉ | Tên, mã hồ sơ, thông tin đơn vị cấp | Làm sao xác minh trực tiếp với đơn vị phát hành? |

Bảng chỉ là ví dụ thiết kế. Tập thuộc tính thực tế phụ thuộc mục đích, luật áp dụng, loại dịch vụ và mức rủi ro; không dùng bảng này làm danh sách thu thập bắt buộc cho mọi sản phẩm.

## 4. Phân loại thuộc tính và độ nhạy

Không phải mọi thuộc tính đều có cùng mức nhạy cảm hoặc cùng giá trị xác minh.

| Nhóm | Ví dụ | Lưu ý |
| --- | --- | --- |
| **Thuộc tính mô tả** | Họ tên, tên hiển thị, ngày sinh | Có thể thay đổi hoặc có nhiều biến thể |
| **Định danh chính thức** | Số giấy tờ, mã định danh do cơ quan cấp | Có thể có rủi ro cao nếu bị lộ hoặc bị dùng để mạo danh |
| **Thuộc tính liên hệ** | Email, số điện thoại, địa chỉ nhận thư | Cần phân biệt thông tin khai báo với quyền kiểm soát kênh |
| **Thuộc tính quan hệ/ngữ cảnh** | Đơn vị, vai trò, quan hệ đại diện | Cần nguồn có thẩm quyền và thời điểm hiệu lực |
| **Thuộc tính sinh trắc** | Ảnh khuôn mặt, mẫu vân tay, giọng nói | Rất nhạy cảm; có rủi ro không thể đổi như mật khẩu |
| **Thuộc tính kỹ thuật/rủi ro** | Thiết bị, IP, tín hiệu phiên, vị trí ước lượng | Là tín hiệu hỗ trợ, không tự chứng minh danh tính |

### 4.1. Tách thông tin khai báo và thông tin đã xác minh

Không nên lưu một trường email duy nhất rồi coi giá trị đó luôn đúng và đã xác minh. Hãy biểu diễn trạng thái:

- Giá trị người dùng khai báo.
- Giá trị được nguồn xác nhận.
- Trạng thái xác minh.
- Nguồn và thời điểm xác minh.
- Phạm vi sử dụng và thời điểm hết hiệu lực nếu có.

Ví dụ, một địa chỉ email có thể ở trạng thái chưa xác minh, sau đó chuyển thành đã xác minh khi người dùng hoàn tất thử thách xác minh. Nếu người dùng đổi email, giá trị mới cần một lần xác minh riêng; trạng thái cũ không tự chuyển sang email mới.

### 4.2. Giá trị có thể thay đổi theo thời gian

Tên pháp lý có thể đổi, địa chỉ có thể cũ, số điện thoại có thể được cấp lại cho người khác, trạng thái nhân viên có thể chấm dứt. Vì vậy, một thuộc tính đã được xác minh tại thời điểm T không đồng nghĩa luôn đúng ở thời điểm T+n.

Với mỗi thuộc tính quan trọng, xác định:

- Có ổn định hay thường xuyên thay đổi?
- Nguồn nào có thể cập nhật khi thay đổi?
- Khi nào cần xác minh lại?
- Có thể dùng trong bao lâu?
- Khi phát hiện sai lệch thì xử lý bản ghi và quyền đang phụ thuộc vào nó ra sao?

## 5. Nguồn thu thập và mức độ tin cậy

Nguồn dữ liệu ảnh hưởng trực tiếp tới chất lượng identity proofing. Cần đánh giá **nguồn nào phát hành hoặc biết thuộc tính**, cách dữ liệu được truyền tới hệ thống và khả năng giả mạo.

| Nguồn | Ví dụ | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| **Self-asserted** | Người dùng tự nhập tên/ngày sinh | Dễ thu thập, ít ma sát | Chưa có xác minh độc lập |
| **Document evidence** | Giấy tờ do cơ quan/tổ chức phát hành | Có thể chứa nhiều thuộc tính và dấu hiệu xác thực | Có thể giả, hết hạn, bị sửa hoặc thuộc người khác |
| **Authoritative source** | Cơ sở dữ liệu chính thức hoặc tổ chức phát hành | Có thể xác nhận thuộc tính trực tiếp | Cần quyền truy cập, tính hợp pháp, chất lượng và độ mới |
| **Trusted identity provider** | Nhà cung cấp danh tính liên kết | Có thể trả kết quả đã proofing theo profile | Cần đánh giá issuer, assurance, claims và trách nhiệm |
| **In-person proofing** | Nhân viên kiểm tra giấy tờ và chủ thể trực tiếp | Có thể xử lý trường hợp phức tạp | Tốn nguồn lực, vẫn có sai sót/insider risk |
| **Contact-channel challenge** | Email link, SMS OTP, cuộc gọi xác minh | Xác nhận quyền truy cập kênh | Không tự chứng minh danh tính pháp lý |
| **Organizational source** | HR, trường học, hệ thống quản lý thành viên | Phù hợp xác minh quan hệ trong tổ chức | Chỉ đáng tin trong phạm vi và thời điểm nguồn quản lý |

Không có một thứ hạng nguồn áp dụng cho mọi thuộc tính. HR có thể là nguồn có thẩm quyền về trạng thái nhân viên nhưng không phải nguồn xác nhận ngày sinh pháp lý. Nhà mạng có thể cung cấp tín hiệu về số thuê bao nhưng không tự xác nhận người đang cầm điện thoại là chủ thể của một hồ sơ cụ thể.

### 5.1. Đánh giá nguồn có thẩm quyền

Trước khi tích hợp một nguồn, cần biết:

1. Ai chịu trách nhiệm phát hành hoặc duy trì dữ liệu?
2. Nguồn có thẩm quyền đối với thuộc tính nào?
3. Dữ liệu được cập nhật khi nào và có độ trễ ra sao?
4. Có thể xác minh tính toàn vẹn, issuer và kênh truyền không?
5. Có cơ chế tra cứu trạng thái, sửa sai hoặc xử lý dữ liệu không tìm thấy không?
6. Việc truy vấn và lưu kết quả có cơ sở pháp lý, hợp đồng và thông báo phù hợp không?
7. Nguồn có thể bị chiếm quyền, thao túng hoặc gián đoạn như thế nào?

Không suy ra “nguồn chính thức” chỉ từ logo hoặc tên miền nhìn thấy trong giao diện. Cần xác minh endpoint, chứng chỉ/kênh kết nối, hợp đồng tích hợp và issuer theo quy trình quản trị.

### 5.2. Bằng chứng nguồn và độ tin cậy theo từng thuộc tính

Một tài liệu có thể xác nhận một số thuộc tính tốt hơn các thuộc tính khác. Ví dụ giấy tờ tùy thân có thể hỗ trợ xác minh tên và ngày sinh theo profile phát hành, nhưng địa chỉ trên đó có thể đã cũ. Hãy đánh giá kết quả theo từng thuộc tính thay vì gắn một nhãn “đã xác minh toàn bộ” cho cả hồ sơ.

## 6. Capture, validation và verification

Một quy trình thu thập thường có ba hoạt động khác nhau:

- **Capture (thu nhận):** lấy dữ liệu từ người dùng, tài liệu, thiết bị hoặc nguồn bên ngoài.
- **Validation (kiểm tra bằng chứng/định dạng):** đánh giá dữ liệu có đúng cấu trúc, còn hiệu lực, hợp lệ về mặt kỹ thuật và nguồn phát hành có đáng tin hay không.
- **Verification (đối chiếu chủ thể):** đánh giá người đang thực hiện quy trình có phải người liên quan tới thuộc tính/danh tính trên bằng chứng hay không.

Các thuật ngữ có thể được định nghĩa chi tiết khác nhau trong từng tiêu chuẩn hoặc quy trình. Điều quan trọng là không gộp việc đọc được dữ liệu thành việc đã chứng minh dữ liệu đúng và thuộc về người đang đăng ký.

~~~mermaid
flowchart TD
    A[Xác định mục đích và thuộc tính cần thiết] --> B[Capture: người dùng / tài liệu / nguồn]
    B --> C[Kiểm tra định dạng và tính đầy đủ]
    C --> D[Validate bằng chứng và issuer]
    D --> E[Verify chủ thể gắn với bằng chứng]
    E --> F[Đối chiếu nguồn và xử lý sai lệch]
    F --> G[Ghi thuộc tính + provenance + trạng thái]
    G --> H[Ra quyết định theo policy]
    H --> I[Lưu tối thiểu, review và xóa theo lịch]
~~~

### 6.1. Capture không phải proof

Ví dụ người dùng tải ảnh giấy tờ lên. Hệ thống OCR trích được tên, ngày sinh và số giấy tờ. OCR chỉ là quá trình nhận dạng ký tự; kết quả có thể sai do ảnh mờ, bố cục, ngôn ngữ hoặc ký tự tương tự. OCR không xác minh tài liệu là thật và không xác minh người tải lên là chủ thể trên giấy tờ.

Một flow hoàn chỉnh có thể cần kiểm tra tính hợp lệ của tài liệu, đối chiếu nguồn phát hành, kiểm tra người đang đăng ký với ảnh trên tài liệu và xử lý rủi ro giả mạo. Mỗi kiểm tra cần được ghi nhận riêng.

### 6.2. Validation của tài liệu

Tùy loại bằng chứng và kênh, kiểm tra có thể gồm:

- Định dạng, cấu trúc, trường bắt buộc và checksum nếu loại mã định danh có quy tắc đó.
- Issuer, chữ ký số, mã QR hoặc dữ liệu chip khi có thể xác minh bằng nguồn đáng tin.
- Ngày phát hành, ngày hết hạn và trạng thái bị hủy/thu hồi nếu có nguồn tra cứu.
- Dấu hiệu sửa ảnh, ghép lớp, chỉnh sửa metadata hoặc tái sử dụng ảnh.
- Tính nhất quán giữa các trường và giữa các mặt/trang của tài liệu.

Một kiểm tra kỹ thuật đạt không tự bảo đảm tài liệu thuộc về người gửi. Cần kiểm tra liên kết chủ thể với bằng chứng theo mức rủi ro.

### 6.3. Verification chủ thể

Có thể đối chiếu người đang thực hiện với bằng chứng qua quy trình trực tiếp, video có giám sát, so khớp ảnh theo policy hoặc phương thức khác được chấp nhận. Nếu dùng sinh trắc, cần đánh giá độ chính xác, khả năng giả mạo, liveness/presentation attack detection, injection attack, sai lệch theo nhóm người dùng và phương án thay thế.

Không coi kết quả face match hoặc liveness là bằng chứng tuyệt đối. Đây là thành phần của một quy trình có nhiều kiểm soát và cần có ngưỡng, giám sát, xử lý trường hợp không kết luận được và con đường review phù hợp.

## 7. Thu thập từ xa và trực tiếp

### 7.1. Trực tiếp

Khi proofing tại quầy hoặc gặp trực tiếp, nhân viên có thể quan sát tài liệu và người xuất trình, hỏi làm rõ và hỗ trợ trường hợp ngoại lệ. Nhưng quy trình trực tiếp vẫn cần:

- Hướng dẫn nhân viên nhận biết giới hạn của từng loại giấy tờ.
- Phân tách người thu thập, người phê duyệt và người có quyền sửa hồ sơ khi rủi ro yêu cầu.
- Ghi nhận nguồn, thời điểm và kết quả kiểm tra.
- Bảo vệ bản sao giấy tờ và thiết bị chụp/scan.
- Có quy trình khi tài liệu không đọc được hoặc người dùng không thể cung cấp loại bằng chứng mặc định.
- Kiểm tra hành vi nội bộ bất thường và truy cập dữ liệu ngoài nhiệm vụ.

Gặp trực tiếp không tự loại bỏ giả mạo giấy tờ, thông đồng hoặc lỗi con người.

### 7.2. Từ xa

Thu thập từ xa có thể dùng web/mobile để chụp giấy tờ, đọc chip NFC, kiểm tra dữ liệu từ nguồn, so khớp khuôn mặt hoặc thực hiện video proofing. Rủi ro gồm:

- Ảnh chụp màn hình hoặc ảnh in được dùng thay tài liệu thật.
- Video/deepfake hoặc mặt nạ vượt qua kiểm tra yếu.
- Camera stream bị thay thế bằng virtual camera hoặc injection.
- App/device bị root, hook hoặc điều khiển từ xa.
- Tài liệu thật bị đánh cắp và dùng bởi người khác.
- Người dùng bị hướng dẫn qua social engineering trong lúc proofing.

Biện pháp có thể gồm kiểm tra chip/chữ ký số, challenge ngẫu nhiên, liveness phù hợp, kiểm soát phiên và thiết bị, đối chiếu nguồn độc lập, giám sát rủi ro và review thủ công. Tín hiệu IP, thiết bị hoặc vị trí chỉ nên là tín hiệu bổ trợ; không nên từ chối một người chỉ vì họ dùng mạng di động, VPN hoặc thiết bị cũ nếu không có cơ sở rủi ro rõ ràng.

## 8. Thuộc tính liên hệ không phải danh tính

Email, số điện thoại và địa chỉ liên lạc thường được thu thập để gửi thông báo, xác minh quyền truy cập hoặc hỗ trợ khôi phục. Cần ghi rõ loại bằng chứng chúng cung cấp.

| Thuộc tính | Thử thách thường dùng | Điều có thể kết luận | Điều không thể tự kết luận |
| --- | --- | --- | --- |
| **Email** | Link hoặc mã gửi tới hộp thư | Người dùng kiểm soát hộp thư tại thời điểm xác minh | Tên pháp lý hoặc danh tính thật |
| **Số điện thoại** | SMS OTP hoặc cuộc gọi | Người dùng truy cập được kênh nhận mã tại thời điểm đó | Người dùng là chủ thuê bao pháp lý hoặc số không bị chuyển giao |
| **Địa chỉ thư tín** | Thư/mã gửi tới địa chỉ | Có khả năng nhận thư tại địa chỉ đó theo điều kiện kiểm tra | Người dùng có quyền sở hữu bất động sản |
| **Địa chỉ cư trú** | Nguồn có thẩm quyền hoặc bằng chứng phù hợp | Có thể hỗ trợ xác minh nơi cư trú theo thời điểm/profile | Địa chỉ luôn hiện tại nếu dữ liệu cũ |

Số điện thoại có thể được nhà mạng tái cấp sau khi thuê bao cũ ngừng sử dụng. Email có thể là hộp thư dùng chung hoặc được chuyển tiếp. Do đó, các kênh này cần được xem là thuộc tính liên hệ có vòng đời riêng, không phải định danh vĩnh viễn.

## 9. Độ chính xác, chuẩn hóa và đối chiếu thuộc tính

Dữ liệu thực tế thường không có cùng cách viết hoặc định dạng. Hệ thống cần chuẩn hóa để so sánh nhưng phải tránh làm mất thông tin quan trọng.

### 9.1. Họ tên

Tên có thể có thứ tự khác nhau, dấu tiếng Việt, tên đệm, bí danh, tên đã đổi, transliteration hoặc khác biệt do hệ thống nguồn. Một số nguyên tắc:

- Lưu giá trị gốc như được cung cấp/đọc từ nguồn.
- Có thể lưu thêm dạng chuẩn hóa phục vụ tìm kiếm, nhưng không ghi đè giá trị gốc.
- Không tự động bỏ dấu hoặc đổi thứ tự tên rồi kết luận hai người là một.
- Cho phép xử lý tên trước đây, tên pháp lý hiện tại và tên hiển thị theo mục đích.
- Dùng nhiều thuộc tính và bằng chứng khi cần phân giải bản ghi trùng.
- Cung cấp quy trình sửa lỗi chính tả và cập nhật tên có bằng chứng.

Tên giống nhau không chứng minh hai bản ghi cùng một người; tên khác nhau không tự chứng minh hai bản ghi thuộc hai người khác nhau.

### 9.2. Ngày tháng và địa chỉ

Ngày sinh nên được lưu theo kiểu dữ liệu ngày nếu không cần giờ; tránh biến ngày địa phương thành timestamp UTC rồi vô tình lệch ngày. Địa chỉ có thể có cấu trúc khác nhau giữa quốc gia, vùng và nguồn dữ liệu; không giả định mọi nơi đều có cùng tỉnh/quận/mã bưu chính.

Với dữ liệu có nhiều định dạng, lưu giá trị gốc, giá trị chuẩn hóa, quy tắc chuyển đổi và nguồn. Nếu không thể chuẩn hóa chắc chắn, đánh dấu cần review thay vì tự đoán.

### 9.3. Matching và false match

Khi đối chiếu hai nguồn, có thể dùng exact match, fuzzy match hoặc nhiều thuộc tính kết hợp. Fuzzy matching giúp xử lý sai khác nhỏ nhưng có thể ghép nhầm người có tên phổ biến.

Một quyết định matching nên xem xét:

- Độ phân biệt của thuộc tính.
- Độ tin cậy và độ mới của nguồn.
- Số lượng thuộc tính độc lập cùng khớp.
- Khả năng một thuộc tính bị dùng chung hoặc thay đổi.
- Tác động khi false positive (ghép nhầm) và false negative (không ghép được).
- Ngưỡng nào tự động chấp nhận, ngưỡng nào cần review và ngưỡng nào từ chối.

Không dùng một điểm similarity duy nhất như kết luận danh tính nếu không đánh giá calibration, dữ liệu kiểm thử và tác động theo nhóm người dùng.

## 10. Provenance: ghi nhận nguồn gốc của thuộc tính

Một thuộc tính đã thu thập cần đi kèm thông tin về nguồn gốc và quá trình xử lý. Nếu chỉ lưu giá trị cuối cùng, đội vận hành khó biết tại sao hệ thống tin nó hoặc khi nào cần xác minh lại.

Một bản ghi provenance có thể bao gồm:

| Metadata | Nội dung |
| --- | --- |
| **Attribute name** | Tên thuộc tính, ví dụ date_of_birth |
| **Value / reference** | Giá trị hoặc tham chiếu tới nơi lưu bảo mật |
| **Source type** | Self-asserted, document, authoritative source, IdP |
| **Source/issuer** | Tổ chức hoặc hệ thống cung cấp |
| **Evidence reference** | Mã tham chiếu tới bằng chứng, không nhất thiết là bản sao |
| **Collected at** | Thời điểm thu thập |
| **Verified at** | Thời điểm xác minh |
| **Method** | Kiểm tra thủ công, API nguồn, chữ ký số, so khớp theo policy |
| **Status** | Unverified, verified, disputed, expired, revoked hoặc trạng thái tương ứng |
| **Confidence/decision** | Kết quả hoặc mức tin cậy theo mô hình đã định nghĩa |
| **Expiry/review date** | Thời điểm cần xác minh lại nếu có |
| **Actor/case ID** | Hệ thống/nhân viên và hồ sơ xử lý liên quan |

Ví dụ bản ghi khái niệm:

~~~json
{
  "attribute": "email",
  "value": "user@example.test",
  "source": "user_asserted",
  "status": "verified",
  "method": "one_time_link",
  "verified_at": "2026-11-22T05:00:00Z",
  "purpose": "account_contact"
}
~~~

Đây là ví dụ cấu trúc minh họa, không phải schema chuẩn. Không đưa dữ liệu cá nhân thật vào log hoặc ví dụ kiểm thử công khai. Nếu bằng chứng chứa dữ liệu nhạy cảm, metadata nên tham chiếu tới kho được bảo vệ thay vì sao chép toàn bộ tài liệu vào nhiều hệ thống.

### 10.1. Confidence phải có ý nghĩa

Nếu dùng điểm tin cậy, định nghĩa rõ điểm được tính từ nguồn, phương thức, độ mới và kết quả kiểm tra nào. Điểm số không thay thế quyết định policy. Một giá trị “0,95” không có ý nghĩa nếu không biết dữ liệu hiệu chỉnh, tập kiểm thử, ngưỡng và tỷ lệ sai.

Có thể dùng trạng thái rõ ràng như verified, pending, disputed, expired thay vì tạo cảm giác chính xác giả bằng một con số không giải thích được.

## 11. Xử lý thiếu, mâu thuẫn và thay đổi thuộc tính

Nguồn có thể không trả dữ liệu, dữ liệu có thể mâu thuẫn hoặc người dùng có thể khai thông tin khác với tài liệu.

Một quy trình xử lý nên:

1. Xác định thuộc tính nào đang mâu thuẫn.
2. So sánh nguồn, thẩm quyền, thời điểm và phương pháp thu thập.
3. Kiểm tra khả năng dữ liệu cũ, lỗi nhập, transliteration hoặc đổi tên hợp pháp.
4. Yêu cầu bằng chứng bổ sung tối thiểu cần thiết.
5. Đưa trường hợp chưa rõ vào review thay vì tự chọn nguồn theo thứ tự cứng.
6. Ghi quyết định, lý do và người/hệ thống phê duyệt.
7. Cho người dùng biết cách sửa dữ liệu hoặc khiếu nại nếu quyết định ảnh hưởng quyền truy cập.

Không ghi đè giá trị trước bằng giá trị mới mà không lưu lịch sử cần thiết. Với thuộc tính quan trọng, lưu lịch sử thay đổi có kiểm soát để hỗ trợ audit, phát hiện takeover và điều tra tranh chấp.

### 11.1. Thay đổi thuộc tính sau proofing

Thay đổi email, số điện thoại, tên, địa chỉ hoặc thông tin định danh có thể ảnh hưởng account recovery và liên kết tài khoản. Policy cần phân biệt:

- Thay đổi thuộc tính hiển thị ít rủi ro.
- Thay đổi kênh liên hệ dùng cho recovery.
- Thay đổi định danh chính hoặc thuộc tính pháp lý.
- Thay đổi do nguồn authoritative cập nhật.
- Thay đổi do người dùng yêu cầu nhưng chưa có bằng chứng.

Các thay đổi nhạy cảm có thể cần reauthentication, MFA/step-up, xác minh kênh mới, thông báo qua kênh cũ và thời gian chờ. Không cho phép một session vừa bị chiếm quyền tự thay toàn bộ thuộc tính recovery rồi dùng chúng để khóa chủ tài khoản thật.

## 12. Rủi ro gian lận trong thu thập thuộc tính

| Mối đe dọa | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **Identity impersonation** | Dùng dữ liệu/giấy tờ của người khác | Xác minh bằng chứng, đối chiếu chủ thể, nguồn độc lập |
| **Document forgery** | Sửa ảnh hoặc tạo giấy tờ giả | Kiểm tra issuer, chữ ký/chip/QR, dấu hiệu sửa đổi và nguồn tra cứu |
| **Synthetic identity** | Kết hợp thuộc tính thật và giả để tạo hồ sơ mới | Đối chiếu nguồn, lịch sử, quan hệ thuộc tính và review rủi ro |
| **Account farming** | Tạo nhiều hồ sơ với dữ liệu biến thể | Phát hiện mẫu lặp, rate limit và kiểm soát theo rủi ro |
| **Deepfake/presentation attack** | Dùng ảnh/video giả trong proofing từ xa | PAD/liveness phù hợp, challenge, kiểm tra nguồn và phương án review |
| **Injection attack** | Thay camera stream hoặc dữ liệu trước khi tới verifier | Bảo vệ app/session, integrity signals và kiểm tra luồng capture |
| **Data poisoning** | Đưa dữ liệu sai vào nguồn nội bộ hoặc quy trình thủ công | Phân quyền, dual control, audit và kiểm tra nguồn |
| **Insider misuse** | Nhân viên xem/sửa thuộc tính ngoài nhiệm vụ | Least privilege, logging, review truy cập và phân tách nhiệm vụ |
| **Replay evidence** | Dùng lại ảnh/tài liệu/video từ hồ sơ khác | Challenge freshness, duplicate detection và transaction binding |
| **False matching** | Ghép nhầm hai người do thuộc tính giống nhau | Matching nhiều tín hiệu, ngưỡng review và quy trình sửa sai |

Không có một biện pháp nào loại bỏ toàn bộ gian lận. Hãy kết hợp nguồn có thẩm quyền, kiểm tra bằng chứng, ràng buộc phiên, kiểm soát thao tác và đánh giá rủi ro; đồng thời bảo đảm người dùng hợp lệ có con đường xử lý khi tự động hóa không kết luận được.

## 13. Bảo vệ quyền riêng tư và dữ liệu cá nhân

Thuộc tính identity thường có khả năng nhận diện một cá nhân và một số loại dữ liệu có độ nhạy cao. Thiết kế cần đáp ứng luật áp dụng, hợp đồng, chính sách tổ chức và kỳ vọng hợp lý của người dùng.

### 13.1. Minh bạch và cơ sở xử lý

Trước khi thu thập, giải thích:

- Ai thu thập và chịu trách nhiệm dữ liệu?
- Thu thập thuộc tính nào?
- Mục đích của từng nhóm dữ liệu?
- Dữ liệu lấy từ người dùng hay nguồn bên ngoài?
- Có chia sẻ với nhà cung cấp nào?
- Lưu trong bao lâu và khi nào xóa?
- Người dùng có thể truy cập, sửa, phản đối hoặc yêu cầu xử lý ra sao?

Không mặc định consent là cơ sở pháp lý duy nhất hoặc luôn phù hợp. Tùy luật và bối cảnh, việc xử lý có thể dựa trên hợp đồng, nghĩa vụ pháp lý, lợi ích hợp pháp hoặc cơ sở khác được công nhận. Khi cần consent, nó phải cụ thể, có thông tin và có thể rút lại theo quy định; việc rút consent cũng cần được xử lý theo nghĩa vụ lưu trữ khác nếu có.

### 13.2. Bảo vệ khi truyền và lưu

- Dùng TLS cho kênh truyền.
- Mã hóa dữ liệu nhạy cảm khi lưu và quản lý khóa riêng.
- Phân quyền theo vai trò và mục đích công việc.
- Tách kho bằng chứng khỏi dữ liệu ứng dụng thông thường nếu phù hợp.
- Không ghi ảnh giấy tờ, số định danh, sinh trắc hoặc token vào log.
- Che/mask dữ liệu trong giao diện hỗ trợ và công cụ vận hành.
- Theo dõi truy cập và tải dữ liệu hàng loạt.
- Có quy trình xóa, backup expiry và xử lý bản sao.

Hash một số định danh ít entropy không tự làm dữ liệu trở nên vô danh; kẻ tấn công có thể thử các giá trị có thể đoán. Cần dùng phương pháp bảo vệ phù hợp, kiểm soát truy cập và tránh công bố hash như mã định danh công khai.

### 13.3. Retention và deletion

Định nghĩa thời hạn lưu cho từng loại dữ liệu: giá trị thuộc tính, bản sao bằng chứng, ảnh sinh trắc, log xác minh và metadata. Không lưu mọi thứ vĩnh viễn chỉ vì có thể hữu ích trong điều tra sau này.

Khi hết mục đích hoặc hết thời hạn pháp lý, xóa hoặc ẩn danh theo chính sách. Xem xét backup, bản sao phân tích, nhà cung cấp và hệ thống log; việc xóa ở giao diện chính không đồng nghĩa mọi bản sao đã biến mất.

## 14. Sinh trắc học trong thu thập thuộc tính

Ảnh khuôn mặt hoặc mẫu sinh trắc có thể được dùng trong một số quy trình để đối chiếu chủ thể với bằng chứng. Tuy nhiên, dữ liệu sinh trắc có rủi ro đặc biệt:

- Khó hoặc không thể thay đổi nếu bị lộ.
- Có thể tạo liên kết giữa các dịch vụ hoặc mục đích khác nhau.
- Có nguy cơ sai lệch hiệu năng giữa nhóm người dùng.
- Có thể gây khó khăn cho người khuyết tật, người có thay đổi ngoại hình hoặc thiết bị không hỗ trợ.
- Dữ liệu gốc và template dẫn xuất đều cần được bảo vệ.

Nếu sử dụng, xác định rõ mục đích, cơ sở xử lý, cách lưu, retention, nhà cung cấp, nơi xử lý và phương án thay thế. Không dùng sinh trắc như bằng chứng duy nhất nếu quy trình yêu cầu nhiều thành phần. Kết quả so khớp là một tín hiệu với sai số, không phải chân lý tuyệt đối.

Khi có thể, ưu tiên xử lý cục bộ hoặc giảm dữ liệu gửi tới hệ thống trung tâm; lưu kết quả/claim cần thiết thay vì giữ ảnh/video thô lâu dài. Cần đánh giá cả việc vendor có giữ dữ liệu, dùng cho huấn luyện hoặc chuyển tiếp cho bên khác hay không.

## 15. Accessibility và công bằng trong proofing

Một quy trình chỉ hoạt động với người có smartphone đời mới, giấy tờ chuẩn hóa hoặc khả năng tự chụp ảnh tốt có thể loại nhầm người dùng hợp lệ.

Cần cung cấp:

- Kênh trực tiếp hoặc hỗ trợ khi proofing từ xa thất bại.
- Cách xử lý giấy tờ cũ, tên có dấu/không dấu, tên nhiều thành phần và thay đổi hợp pháp.
- Hỗ trợ người dùng không có điện thoại cá nhân hoặc không truy cập được email/SMS.
- Giao diện tương thích công nghệ hỗ trợ và ngôn ngữ phù hợp.
- Cơ chế review thủ công có thời hạn và thông báo rõ.
- Quy trình khiếu nại, sửa thuộc tính và cung cấp bằng chứng thay thế.

Không dùng một tín hiệu như thiết bị, vị trí, accent, cách viết tên hoặc khả năng hoàn thành sinh trắc làm đại diện cho độ tin cậy của một con người. Các tín hiệu đó có thể phản ánh điều kiện truy cập hoặc khác biệt cá nhân, không phải danh tính gian lận.

## 16. Ví dụ thiết kế một flow thu thập thuộc tính

Giả sử một dịch vụ cần xác minh người đăng ký là nhân viên đang làm việc tại tổ chức. Mục đích không phải proofing danh tính pháp lý ngoài đời cho mọi mục tiêu; dịch vụ cần xác minh mối quan hệ nhân viên và cấp tài khoản nội bộ.

Một flow hợp lý có thể:

1. Yêu cầu mã nhân viên và email công việc.
2. Tra cứu mã nhân viên trong hệ thống HR được chỉ định làm nguồn có thẩm quyền.
3. Kiểm tra trạng thái làm việc, đơn vị và thời điểm hiệu lực.
4. Gửi thử thách tới email công việc nếu policy yêu cầu xác nhận quyền truy cập hộp thư.
5. Đối chiếu người đăng ký với principal/identity record nội bộ hiện có.
6. Ghi nguồn HR, thời điểm tra cứu, kết quả và trạng thái email đã xác minh.
7. Cấp credential đăng nhập theo quy trình riêng; không dùng mã nhân viên làm password.
8. Khi nhân viên chuyển đơn vị hoặc nghỉ việc, nhận cập nhật từ HR và điều chỉnh quyền/thu hồi session theo policy.

Trong ví dụ này, email công việc đã xác minh chứng minh quyền truy cập hộp thư; HR xác nhận quan hệ nhân viên. Hai nguồn trả lời hai câu hỏi khác nhau. Không cần thu thập ngày sinh hoặc ảnh căn cước nếu mục đích và policy không yêu cầu.

~~~mermaid
sequenceDiagram
    participant P as Người đăng ký
    participant A as Ứng dụng
    participant H as Hệ thống HR
    participant M as Email service
    participant I as Identity store
    P->>A: Mã nhân viên + email công việc
    A->>H: Tra cứu mã và trạng thái nhân viên
    H-->>A: Thuộc tính + nguồn + thời điểm
    A->>M: Gửi thử thách email
    M-->>P: Link/mã xác minh
    P->>A: Hoàn tất thử thách
    A->>I: Ghi thuộc tính, provenance và trạng thái
    A-->>P: Kết quả onboarding
~~~

### 16.1. Ví dụ record thuộc tính

~~~json
{
  "subject_id": "employee-4821",
  "attributes": {
    "employee_status": {
      "value": "active",
      "source": "hr-system",
      "status": "verified",
      "verified_at": "2026-11-22T05:00:00Z"
    },
    "work_email": {
      "value": "person@example.test",
      "source": "user_asserted",
      "status": "verified",
      "method": "email_challenge"
    }
  }
}
~~~

Đây là mô hình khái niệm. Dữ liệu thực tế cần kiểm soát quyền đọc/ghi, tenant, lịch sử, retention và quy tắc đồng bộ. Không dùng employee ID do client tự khai làm bằng chứng duy nhất nếu không tra cứu nguồn HR.

## 17. Chỉ số vận hành cho attribute collection

Đo lường giúp phát hiện điểm gây ma sát và sai lệch:

| Nhóm | Chỉ số gợi ý | Ý nghĩa |
| --- | --- | --- |
| **Completion** | Tỷ lệ hoàn thành theo bước và theo loại bằng chứng | Người dùng rời flow ở đâu? |
| **Data quality** | Tỷ lệ thiếu, lỗi định dạng, mâu thuẫn hoặc phải sửa | Form/nguồn có tạo dữ liệu tốt không? |
| **Verification** | Tỷ lệ xác minh thành công, thất bại và cần review | Bằng chứng/nguồn hoạt động ra sao? |
| **Fraud** | Tỷ lệ nghi ngờ giả mạo, replay, duplicate hoặc account farming | Kiểm soát phát hiện gì? |
| **False decisions** | Tỷ lệ khiếu nại được chấp nhận, false match/false reject theo kiểm tra | Có người hợp lệ bị từ chối nhầm không? |
| **Privacy** | Số trường thu thập, thời gian lưu, truy cập và xóa đúng hạn | Có thu thập quá mức hoặc lưu quá lâu không? |
| **Accessibility** | Tỷ lệ hoàn thành theo thiết bị/kênh hỗ trợ phù hợp | Có nhóm người dùng bị loại khỏi flow không? |
| **Operations** | Thời gian review, chi phí xử lý, tỷ lệ lỗi nguồn ngoài | Quy trình có thể vận hành ổn định không? |

Phân tích chỉ số theo nhóm thiết bị, ngôn ngữ, loại bằng chứng và phương thức truy cập có thể phát hiện vấn đề công bằng. Cần bảo vệ dữ liệu phân tích và tránh tạo thêm hồ sơ nhạy cảm không cần thiết. Không tối ưu completion bằng cách âm thầm hạ tiêu chuẩn proofing cho mọi trường hợp.

## 18. Checklist review thu thập thuộc tính

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Mục đích thu thập đã rõ? | Mỗi trường có mục đích và owner |
| Có thu thập tối thiểu? | Không lấy dữ liệu chỉ vì tiện hoặc có sẵn |
| Thuộc tính có phân loại độ nhạy? | Sinh trắc/định danh chính thức được bảo vệ cao hơn |
| Nguồn có thẩm quyền với thuộc tính? | Xác định issuer, phạm vi, độ mới và kênh |
| Đã phân biệt self-asserted với verified? | Có trạng thái và provenance riêng |
| Capture/validation/verification có tách? | OCR không bị coi là proof; chủ thể được đối chiếu |
| Có kiểm tra freshness? | Biết dữ liệu thay đổi và khi nào cần xác minh lại |
| Matching có kiểm soát false positive? | Có nhiều tín hiệu, ngưỡng review và quy trình sửa sai |
| Có xử lý mâu thuẫn? | Không tự chọn nguồn hoặc ghi đè thiếu audit |
| Email/phone được diễn giải đúng? | Xác minh quyền kiểm soát kênh, không suy thành danh tính pháp lý |
| Sinh trắc có thực sự cần? | Có đánh giá rủi ro, sai số, privacy và phương án thay thế |
| Dữ liệu được bảo vệ? | TLS, encryption at rest, least privilege và audit |
| Retention/deletion rõ? | Có lịch lưu, xóa và xử lý backup/vendor |
| Có hỗ trợ accessibility? | Có kênh thay thế và quy trình khiếu nại |
| Có kiểm soát gian lận? | Document fraud, synthetic identity, replay và insider risk |
| Có test negative cases? | Nguồn sai, tài liệu hết hạn, mâu thuẫn, dữ liệu trùng và session takeover |

### Tình huống tự kiểm tra

**Tình huống 1:** Người dùng nhập email và nhấp link xác minh. Hệ thống có thể kết luận họ là người có tên pháp lý ghi trong hồ sơ không?

**Trả lời:** Không. Điều này chỉ cho thấy họ kiểm soát hộp thư tại thời điểm xác minh theo điều kiện của flow.

**Tình huống 2:** OCR đọc được họ tên và ngày sinh trên ảnh căn cước. Đã hoàn tất identity proofing chưa?

**Trả lời:** Chưa. OCR là capture/extraction. Cần kiểm tra tính xác thực của bằng chứng và liên kết người đang đăng ký với chủ thể trên tài liệu.

**Tình huống 3:** Hai bản ghi có cùng họ tên và ngày sinh. Có thể tự động gộp không?

**Trả lời:** Không nên chỉ dựa vào hai thuộc tính này. Cần xem nguồn, định danh phân biệt, độ mới và rủi ro false match; trường hợp không chắc chắn cần review.

**Tình huống 4:** Một dịch vụ chỉ cần biết người dùng đủ 18 tuổi nhưng yêu cầu lưu ảnh giấy tờ và ngày sinh đầy đủ. Có hợp lý không?

**Trả lời:** Chưa chắc. Hãy xem có thể nhận kết quả đạt ngưỡng tuổi từ nguồn tin cậy và không lưu dữ liệu chi tiết hay không, đồng thời đáp ứng luật và yêu cầu bằng chứng áp dụng.

**Tình huống 5:** Số điện thoại đã được xác minh hai năm trước. Có thể dùng nó làm bằng chứng recovery mạnh hiện tại không?

**Trả lời:** Không mặc nhiên. Số có thể đã đổi chủ hoặc bị chiếm quyền. Cần xem độ mới, rủi ro, trạng thái kênh và kết hợp bằng chứng khác theo policy.

## 19. Ghi nhớ

**Thu thập thuộc tính là quá trình lấy thông tin cần thiết và ghi rõ nguồn gốc của thông tin trong identity proofing.** Giá trị người dùng tự khai, kết quả OCR, thuộc tính từ nguồn có thẩm quyền và dữ liệu đã được xác minh có mức tin cậy khác nhau. Email/phone challenge chứng minh quyền truy cập kênh; credential chứng minh quyền kiểm soát phương tiện xác thực; chúng không tự thay thế việc proofing danh tính.

Một quy trình đáng tin bắt đầu từ mục đích và data minimization, chọn nguồn phù hợp cho từng thuộc tính, tách capture khỏi validation/verification, ghi provenance và freshness, xử lý mâu thuẫn có review, bảo vệ dữ liệu và giới hạn retention. Thiết kế phải chống giả mạo nhưng vẫn hỗ trợ người dùng hợp lệ, quyền riêng tư và khả năng tiếp cận.
