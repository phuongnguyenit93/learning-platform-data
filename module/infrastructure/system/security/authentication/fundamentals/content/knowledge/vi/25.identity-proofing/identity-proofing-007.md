# Proofing risk — Đánh giá và kiểm soát rủi ro trong xác minh danh tính

Một dịch vụ tài chính cho phép khách hàng mở tài khoản từ xa. Người đăng ký tải ảnh giấy tờ, chụp khuôn mặt và thực hiện kiểm tra sống. Hệ thống có thể đọc được giấy tờ, so khớp khuôn mặt và kiểm tra người đang thao tác hiện diện trước camera. Tuy nhiên, kẻ gian vẫn có thể dùng giấy tờ bị đánh cắp, danh tính tổng hợp, video deepfake, thiết bị bị điều khiển hoặc thông tin thật của người khác. Vì vậy, kết quả kỹ thuật “pass” không tự động có nghĩa rủi ro chiếm đoạt danh tính đã được loại bỏ.

**Proofing risk** là rủi ro hệ thống chấp nhận một tuyên bố danh tính sai, liên kết bằng chứng với nhầm người, hoặc tạo account có assurance thấp hơn mức dịch vụ cần. Đánh giá rủi ro phải xét tài sản được bảo vệ, hậu quả khi nhận nhầm người, loại bằng chứng, cách thu thập, nguồn xác minh, khả năng gian lận, kênh khôi phục và các biện pháp kiểm soát. Đây là một phần của identity proofing — quy trình xác lập rằng người đăng ký tương ứng với danh tính được tuyên bố.

Trong module `SECURITY_AUTHENTICATION_FUNDAMENTALS`, bài học này giúp người học phân tích rủi ro trong xác minh danh tính trực tiếp và từ xa, phân biệt identity proofing với authentication, đánh giá bằng chứng và tín hiệu rủi ro, thiết kế step-up/manual review, bảo vệ quyền riêng tư và xử lý trường hợp không đủ bằng chứng. Mục tiêu là đưa ra quyết định có thể giải thích, kiểm toán và tương xứng với hậu quả của việc nhận nhầm danh tính.

## 1. Identity proofing và authentication giải quyết hai câu hỏi khác nhau

Identity proofing diễn ra khi thiết lập hoặc xác nhận mối liên hệ giữa một người và danh tính được tuyên bố. Authentication diễn ra khi người đó quay lại và chứng minh họ đang kiểm soát một authenticator đã đăng ký.

| Hoạt động | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Identity resolution** | Người này đang tuyên bố danh tính nào? Có thể phân biệt với người khác không? | Thu thập tên, ngày sinh, địa chỉ hoặc mã định danh |
| **Evidence validation** | Bằng chứng có thật, hợp lệ, còn hiệu lực và đúng loại không? | Kiểm tra giấy tờ, chữ ký số, nguồn phát hành hoặc dữ liệu xác minh |
| **Identity verification** | Người đang đăng ký có phải chủ thể mà bằng chứng mô tả không? | So khớp người với ảnh trên giấy tờ hoặc xác minh qua nguồn đáng tin |
| **Proofing decision** | Bằng chứng và kiểm soát có đủ ở assurance yêu cầu không? | Chấp nhận, yêu cầu bổ sung, chuyển review hoặc từ chối |
| **Enrollment** | Gắn authenticator với account đã proofing | Đăng ký passkey, security key hoặc MFA |
| **Authentication** | Người quay lại có kiểm soát authenticator đã đăng ký không? | WebAuthn assertion, chứng chỉ client, mật khẩu và MFA |
| **Authorization** | Chủ thể đã xác thực có quyền làm hành động này không? | Kiểm tra role, tenant, account status và quyền trên tài nguyên |

Một passkey có thể chứng minh người dùng đang kiểm soát private key được đăng ký cho RP; nó không tự chứng minh người dùng là người có tên trên giấy tờ. Ngược lại, proofing danh tính tốt không chứng minh lần đăng nhập sau do chính người đó thực hiện. Hệ thống cần quản lý cả hai vòng đời và không dùng kết quả của bước này thay cho bước kia.

~~~mermaid
flowchart TD
    A[Người đăng ký khai danh tính] --> B[Resolution: phân biệt subject]
    B --> C[Thu thập evidence và thuộc tính]
    C --> D[Validation: kiểm tra bằng chứng]
    D --> E[Verification: liên kết người với danh tính]
    E --> F[Đánh giá risk và assurance]
    F -->|Đủ điều kiện| G[Proofing decision và audit]
    F -->|Cần thêm bằng chứng| H[Step-up hoặc manual review]
    F -->|Không thể xác minh / gian lận| I[Từ chối hoặc giữ pending]
    G --> J[Enrollment authenticator]
    J --> K[Authentication và lifecycle]
~~~

Các bước có thể diễn ra qua nhiều kênh và không nhất thiết tuyến tính. Mỗi kết luận cần có nguồn bằng chứng, thời điểm, mức tin cậy, phạm vi và quyết định được lưu lại.

## 2. Mô hình hóa proofing risk

Trước khi chọn công nghệ OCR, liveness hoặc database lookup, hãy xác định rủi ro cần kiểm soát. Một mô hình định tính có thể xem xét:

- **Impact:** hậu quả nếu hệ thống chấp nhận nhầm danh tính hoặc từ chối nhầm người hợp lệ.
- **Likelihood:** khả năng xảy ra gian lận trong nhóm người dùng, kênh và bối cảnh cụ thể.
- **Exposure:** giá trị tài khoản, quyền, giao dịch và dữ liệu có thể truy cập sau proofing.
- **Detectability:** khả năng phát hiện sai sót trước hoặc sau khi cấp account.
- **Recovery cost:** mức thiệt hại và chi phí khôi phục khi account bị cấp nhầm hoặc bị chiếm.

Có thể dùng ma trận định tính để bắt đầu, nhưng không nên biến một phép nhân điểm đơn giản thành quyết định tự động cho mọi trường hợp. Rủi ro có xác suất thấp nhưng hậu quả rất lớn vẫn có thể yêu cầu kiểm soát mạnh. Một tín hiệu bất thường cũng không đồng nghĩa người đăng ký là gian lận.

### 2.1. Xác định tài sản và hậu quả

| Tài sản / khả năng sau proofing | Hậu quả nếu nhận nhầm danh tính | Ví dụ kiểm soát |
| --- | --- | --- |
| Tài khoản đọc nội dung công khai | Spam, lạm dụng dịch vụ hoặc ảnh hưởng dữ liệu cá nhân nhỏ | Email/phone verification, rate limit, abuse detection |
| Hồ sơ cá nhân có dữ liệu nhạy cảm | Rò rỉ dữ liệu, chiếm account, thay đổi thông tin | Proofing mạnh hơn, authenticator chống phishing, recovery chặt |
| Tài khoản tài chính hoặc thanh toán | Gian lận tiền, nghĩa vụ pháp lý và tổn thất lớn | Evidence đáng tin, kiểm tra độc lập, risk review và transaction controls |
| Tài khoản quản trị | Chiếm hệ thống, thay đổi quyền và dữ liệu diện rộng | Proofing assurance cao, phê duyệt, hardware-backed authenticator |
| Danh tính nhân viên/workload | Truy cập nội bộ, dữ liệu và hạ tầng | HR/device/workload source, PKI hoặc identity lifecycle có quản trị |
| Account dùng để cấp credential cho người khác | Lan truyền danh tính sai sang nhiều account | Phân tách nhiệm vụ, audit và xác minh người phê duyệt |

Rủi ro phụ thuộc cả vào những gì account có thể làm sau khi tạo. Nếu proofing chỉ cấp account giới hạn, kiểm soát ban đầu có thể khác với account được phép chuyển tiền, thay đổi recovery hoặc cấp quyền cho người khác. Proofing decision cần gắn với intended use và mức assurance, không chỉ với một nhãn “verified”.

### 2.2. Threat actors và năng lực

Threat model nên mô tả attacker có thể làm gì:

1. **Kẻ mạo danh cá nhân:** dùng giấy tờ giả, thông tin bị đánh cắp hoặc ảnh của người khác.
2. **Kẻ dùng danh tính tổng hợp:** kết hợp dữ liệu thật và giả để tạo hồ sơ trông nhất quán nhưng không tương ứng với một người hợp lệ.
3. **Kẻ dùng dữ liệu rò rỉ:** có tên, ngày sinh, địa chỉ, số giấy tờ hoặc câu trả lời bảo mật của nạn nhân.
4. **Kẻ tấn công kênh từ xa:** can thiệp camera, giả lập thiết bị, replay ảnh/video, dùng deepfake hoặc điều khiển phiên.
5. **Kẻ lạm dụng nội bộ:** nhân viên bỏ qua kiểm tra, sửa kết quả hoặc thông đồng với người đăng ký.
6. **Kẻ chiếm kênh recovery:** dùng help desk, email, SIM hoặc quy trình thay đổi thông tin để chiếm account.
7. **Kẻ lạm dụng nhà cung cấp:** khai thác API hoặc nguồn xác minh bên thứ ba, hoặc làm giả response qua integration yếu.

Hãy ghi rõ attacker kiểm soát thiết bị, giấy tờ, mạng, email, số điện thoại, nguồn dữ liệu hoặc nhân viên nào; từ đó xác định kiểm soát nào thực sự làm tăng chi phí tấn công.

## 3. Evidence: bằng chứng danh tính và giới hạn của chúng

Identity evidence có thể là giấy tờ do cơ quan có thẩm quyền cấp, chứng chỉ số, dữ liệu từ nguồn đáng tin, thông tin tài khoản hiện hữu hoặc bằng chứng vật lý. Giá trị của evidence phụ thuộc nguồn phát hành, khả năng giả mạo, trạng thái còn hiệu lực, cách thu thập và khả năng kiểm tra độc lập.

| Nhóm evidence | Ví dụ | Điểm cần đánh giá |
| --- | --- | --- |
| Giấy tờ chính thức | Hộ chiếu, căn cước, giấy phép lái xe | Cơ quan phát hành, mẫu bảo an, thời hạn, trạng thái, ảnh và thuộc tính |
| Credential số | Chứng chỉ số, credential có chữ ký hoặc QR có thể xác minh | Chain, issuer, chữ ký, revocation, audience/purpose và binding |
| Nguồn authoritative | Registry được pháp luật hoặc tổ chức chỉ định | Quyền truy cập, độ mới, phạm vi dữ liệu, chất lượng và audit |
| Bằng chứng sở hữu kênh | Email hoặc số điện thoại nhận OTP/link | Chỉ chứng minh kiểm soát kênh tại thời điểm đó, không tự chứng minh danh tính |
| Bằng chứng hiện diện | Video trực tiếp, liveness hoặc kiểm tra trực tiếp | Khả năng chống replay/deepfake, thiết bị, chất lượng và giới hạn |
| Bằng chứng liên kết account | Account doanh nghiệp đã quản lý, HR record hoặc sponsor | Nguồn có đáng tin, quy trình cấp account và xung đột lợi ích |
| Bằng chứng xã hội/hỗ trợ | Người giới thiệu, help desk, xác nhận của quản lý | Mức độc lập, khả năng social engineering và audit |

### 3.1. Đánh giá evidence theo thuộc tính

Mỗi loại evidence nên được mô tả ít nhất bằng:

- **Issuer/source:** ai tạo hoặc xác nhận bằng chứng?
- **Authority:** nguồn có thẩm quyền cho thuộc tính cần xác minh không?
- **Authenticity:** có kiểm tra được tính thật và tính toàn vẹn không?
- **Validity:** bằng chứng còn hiệu lực, chưa bị thu hồi hoặc thay thế không?
- **Binding:** bằng chứng gắn với người đăng ký bằng cách nào?
- **Freshness:** dữ liệu được cập nhật khi nào?
- **Purpose:** evidence được cấp để chứng minh điều gì, có dùng được cho proofing này không?
- **Fraud resistance:** attacker có thể tạo, sửa, replay hoặc mua bán evidence dễ đến mức nào?
- **Privacy:** thu thập thuộc tính nào, có thể giảm dữ liệu hoặc dùng kết quả xác minh thay cho bản sao không?

Một ảnh chụp giấy tờ rõ nét chỉ chứng minh hệ thống đọc được nội dung ảnh. Nó không tự chứng minh giấy tờ là thật, còn hiệu lực hoặc thuộc về người đang cầm điện thoại. Một email OTP thành công chỉ chứng minh người đó nhận được mã tại thời điểm kiểm tra; không thể dùng nó làm bằng chứng độc lập về tên pháp lý.

### 3.2. Evidence strength và independence

Nhiều bằng chứng không tự động tạo assurance cao hơn. Nếu tất cả bằng chứng đều đến từ cùng một nguồn bị chiếm, chúng có thể thất bại cùng lúc. Ví dụ, tên, ngày sinh, địa chỉ và số điện thoại đều lấy từ một hồ sơ dữ liệu bị rò rỉ; việc kiểm tra cả bốn thuộc tính không tạo ra bốn bằng chứng độc lập.

Hãy xem:

- **Độ độc lập:** các bằng chứng có nguồn và cơ chế kiểm tra độc lập không?
- **Độ tương quan:** một cuộc tấn công có thể làm giả tất cả cùng lúc không?
- **Coverage:** evidence chứng minh được thuộc tính nào và còn thiếu thuộc tính nào?
- **Assurance ceiling:** tổng thể có bị giới hạn bởi thành phần yếu nhất hoặc kênh thu thập không?

Không nên cộng điểm tuyến tính cho nhiều tín hiệu tương quan. Một nguồn xác minh authoritative có thể có giá trị hơn nhiều trường dữ liệu tự khai; ngược lại, nguồn authoritative nhưng dữ liệu đã cũ hoặc không có quyền truy cập hợp pháp cũng không đủ.

## 4. Resolution, validation và verification

Ba hoạt động này cần được tách rõ để tránh nhầm một kết quả OCR với một kết luận danh tính.

### 4.1. Identity resolution

Resolution tìm hoặc xác định hồ sơ mà người đăng ký đang tuyên bố. Tùy dịch vụ, thuộc tính có thể gồm tên, ngày sinh, địa chỉ, mã định danh, tổ chức hoặc mã nhân viên. Cần xác định:

- Có thể phân biệt người này với người khác không?
- Thuộc tính có nhất quán giữa các nguồn không?
- Có nhiều hồ sơ trùng hoặc mâu thuẫn không?
- Có dấu hiệu synthetic identity hoặc dữ liệu bị tái sử dụng không?
- Việc truy vấn nguồn có hợp pháp và đúng mục đích không?

Resolution không phải là chứng minh người đăng ký đang hiện diện hoặc kiểm soát danh tính đó. Nó chỉ xác định hồ sơ cần kiểm tra.

### 4.2. Evidence validation

Validation kiểm tra evidence có thật, hợp lệ, còn hiệu lực và phù hợp với mục đích. Ví dụ:

- Đọc vùng máy đọc được (MRZ) và kiểm tra checksum theo loại giấy tờ hỗ trợ.
- Kiểm tra chữ ký số và certificate chain của credential điện tử.
- Xác minh QR hoặc mã tham chiếu với endpoint của issuer qua kênh đã cấu hình.
- Kiểm tra thời hạn, trạng thái và dữ liệu bảo an của giấy tờ theo nguồn phù hợp.
- Phát hiện chỉnh sửa ảnh, font bất thường, layer ghép hoặc dữ liệu mâu thuẫn.

OCR chỉ trích xuất dữ liệu; nó không phải validation hoàn chỉnh. Kiểm tra checksum chỉ chứng minh một số trường có cấu trúc hợp lệ; dữ liệu giả vẫn có thể được tạo với checksum đúng. Chữ ký số cần xác minh đúng issuer, chain, mục đích, thời hạn và trạng thái thu hồi.

### 4.3. Identity verification

Verification liên kết người đang đăng ký với danh tính được tuyên bố. Các phương thức có thể gồm:

- Kiểm tra trực tiếp giấy tờ và người sở hữu bởi nhân viên được đào tạo.
- So khớp khuôn mặt trực tiếp với ảnh trên evidence, nếu có cơ sở pháp lý và kiểm soát phù hợp.
- Kiểm tra qua nguồn authoritative hoặc credential có binding với chủ thể.
- Xác minh qua quy trình tổ chức đáng tin, chẳng hạn HR/sponsor có trách nhiệm.

So khớp sinh trắc học là một phương thức có giới hạn, không phải chân lý tuyệt đối. Kết quả phụ thuộc chất lượng camera, ánh sáng, góc mặt, tuổi, thiết bị, thuật toán và nhóm người dùng. Liveness có thể giảm một số replay presentation attack nhưng không chứng minh giấy tờ là thật hoặc account không phải danh tính tổng hợp.

## 5. Risk signals: tín hiệu hỗ trợ quyết định, không phải bằng chứng danh tính

Hệ thống proofing từ xa thường dùng nhiều tín hiệu để quyết định có cần thêm kiểm tra. Những tín hiệu này hữu ích cho fraud detection nhưng dễ bị hiểu nhầm thành bằng chứng.

| Tín hiệu | Có thể gợi ý | Không chứng minh |
| --- | --- | --- |
| IP reputation / ASN / proxy indicator | Kết nối qua hạ tầng bất thường hoặc automation | Người dùng là attacker; IP có thể dùng chung hoặc thuộc VPN hợp lệ |
| Device fingerprint / device integrity | Thiết bị quen thuộc, thay đổi môi trường hoặc dấu hiệu giả lập | Danh tính thật của người sử dụng |
| Geolocation / impossible travel | Mâu thuẫn vị trí theo thời gian | Gian lận chắc chắn; vị trí có thể sai do VPN, carrier hoặc định vị |
| Velocity / attempt rate | Nhiều lần thử, tạo account hàng loạt | Mỗi lần thử đều độc hại; có thể là người dùng gặp lỗi |
| Email/phone tenure hoặc reputation | Kênh mới, rủi ro SIM/email hoặc dữ liệu liên hệ bất thường | Người đó không sở hữu danh tính được khai |
| Document anomaly | Ảnh/giấy tờ có dấu hiệu chỉnh sửa hoặc mẫu không khớp | Giấy tờ giả chắc chắn; cần kiểm tra nguồn và lỗi false positive |
| Face match / liveness score | Mức tương đồng hoặc khả năng hiện diện theo model | Danh tính pháp lý, ý định hoặc quyền sở hữu account |
| Data consistency | Thuộc tính khớp hoặc mâu thuẫn giữa nguồn | Mọi nguồn đều độc lập hoặc dữ liệu chắc chắn chính xác |
| Account linkage / graph signal | Nhiều account dùng chung thiết bị, kênh hoặc thuộc tính | Các account thuộc cùng một người hoặc cùng là fraud |

Tín hiệu rủi ro nên được đánh giá trong ngữ cảnh, có nguồn, thời điểm, độ tin cậy và giới hạn. Không từ chối tự động chỉ vì một IP thuộc VPN hoặc người dùng đổi thiết bị. Một thiết bị quen thuộc cũng không đủ để bỏ qua kiểm tra evidence bắt buộc.

### 5.1. Risk-based decision

Một policy có thể phân loại kết quả:

- **Accept:** evidence và verification đáp ứng assurance yêu cầu, không có xung đột chưa giải quyết.
- **Step-up:** yêu cầu thêm một phương thức độc lập hoặc evidence mạnh hơn.
- **Manual review:** chuyển cho nhân viên có thẩm quyền khi tín hiệu mâu thuẫn hoặc automation không đủ chắc chắn.
- **Pending:** chưa có kết luận; giữ quyền hạn chế cho đến khi hoàn tất.
- **Reject:** evidence không hợp lệ, không thể xác minh hoặc có dấu hiệu gian lận đủ mạnh theo policy.
- **Escalate:** yêu cầu kiểm tra chuyên sâu, bảo toàn bằng chứng và quy trình incident khi có nghi ngờ tổ chức.

Không nên dùng một điểm rủi ro duy nhất để tự động quyết định trong mọi sản phẩm. Nếu dùng scoring, cần ghi rõ feature, nguồn, trọng số, ngưỡng, version model, calibration, drift và quy trình appeal. Quyết định từ model phải có giới hạn quyền và khả năng giải thích tương xứng.

## 6. Rủi ro trong proofing từ xa

Remote proofing giúp người dùng đăng ký không cần gặp trực tiếp, nhưng mở thêm bề mặt tấn công vì hệ thống không trực tiếp kiểm soát thiết bị, camera và môi trường thu thập.

### 6.1. Document presentation attack

Attacker có thể dùng:

- Ảnh chụp màn hình hoặc ảnh in thay cho giấy tờ vật lý.
- Giấy tờ giả hoặc giấy tờ thật bị chỉnh sửa thuộc tính.
- Ảnh/scan của giấy tờ bị đánh cắp.
- Video replay trên màn hình hoặc camera ảo.
- Ảnh cắt ghép, thay mặt hoặc nội dung được tạo bằng AI.

Kiểm soát nên kết hợp kiểm tra mẫu bảo an khi phù hợp, MRZ/barcode/QR validation, kiểm tra issuer, phân tích ảnh và đối chiếu với nguồn tin cậy. Không dựa riêng vào OCR hoặc một model phát hiện ảnh giả.

### 6.2. Face presentation và injection attack

Các hình thức tấn công có thể gồm ảnh in, video replay, mặt nạ, deepfake, camera ảo, can thiệp luồng video hoặc điều khiển thiết bị. Presentation attack detection và liveness có thể giúp giảm một số loại, nhưng không bao phủ mọi phương thức.

Kiểm soát:

1. Dùng SDK/thiết bị thu thập có nguồn gốc và integrity signal phù hợp; không tin metadata client tự khai.
2. Chọn liveness theo threat model và kiểm tra chất lượng độc lập; hiểu tỷ lệ false accept/false reject và điều kiện vận hành.
3. Dùng challenge ngẫu nhiên hoặc tương tác phù hợp để giảm replay đơn giản, nhưng không coi challenge là chống deepfake tuyệt đối.
4. Kết hợp kiểm tra giấy tờ và nguồn xác minh độc lập.
5. Giám sát thiết bị ảo, automation và thay đổi luồng bất thường mà không xem một tín hiệu đơn lẻ là kết luận.
6. Có kênh thay thế cho người không thể hoàn thành sinh trắc học, tránh loại trừ người khuyết tật hoặc thiết bị chất lượng thấp.

### 6.3. Synthetic identity và identity farming

Danh tính tổng hợp có thể kết hợp dữ liệu thật của một người, địa chỉ ảo, số điện thoại mới và lịch sử tín dụng/tài khoản được tạo dần. Một hồ sơ có thể vượt qua kiểm tra từng thuộc tính vì mỗi thuộc tính đều trông hợp lệ riêng lẻ.

Kiểm soát cần xét tính nhất quán theo thời gian và quan hệ giữa thuộc tính, nguồn authoritative, lịch sử account, velocity và hành vi sau enrollment. Graph/linkage signal có thể tạo false positive với gia đình, trường học, công ty hoặc mạng dùng chung; cần review theo ngữ cảnh và hạn chế sử dụng thuộc tính nhạy cảm.

### 6.4. Social engineering và assisted proofing

Kẻ tấn công có thể hướng dẫn nạn nhân tự thực hiện proofing, thuê người mở account, giả làm nhân viên hỗ trợ hoặc thuyết phục nhân viên bỏ qua bước kiểm tra. Kiểm soát gồm nội dung hướng dẫn rõ, xác nhận ý định, đào tạo nhân viên, callback qua kênh đã xác minh, phân tách nhiệm vụ và audit thay đổi quyết định.

## 7. Assurance và chọn mức proofing theo mục đích

Mức proofing nên phản ánh rủi ro và mục đích sử dụng. Một ứng dụng đọc tin không cần cùng mức kiểm tra với dịch vụ cấp quyền quản trị hoặc tài khoản chuyển tiền lớn.

| Mục đích | Mức kiểm soát có thể phù hợp | Rủi ro cần cân nhắc |
| --- | --- | --- |
| Tạo account dùng thử, quyền thấp | Email/phone verification, abuse rate limits, giới hạn tính năng | Account farming, spam; không tuyên bố đã xác minh danh tính pháp lý |
| Account có dữ liệu cá nhân | Evidence phù hợp và verification bổ sung theo rủi ro | Account takeover, lộ PII, liên kết nhầm người |
| Dịch vụ tài chính hoặc giao dịch có hậu quả lớn | Evidence authoritative, validation/verification độc lập, fraud review và step-up | Gian lận danh tính, nghĩa vụ pháp lý, tổn thất tài chính |
| Nhân viên truy cập hệ thống nội bộ | HR/sponsor source, kiểm tra employment status, device/workforce lifecycle | Nhân viên giả, quyền tồn tại sau khi nghỉ việc |
| Quản trị viên hoặc người cấp credential | Proofing mạnh, kiểm tra độc lập, phê duyệt nhiều bên và authenticator chống phishing | Privilege escalation và ảnh hưởng diện rộng |
| Workload/service identity | Xác minh workload/source, deployment identity, certificate hoặc workload attestation | Giả mạo service và cấp credential trái phép |

Không gán một mức assurance chỉ dựa vào việc người dùng đã thực hiện nhiều bước. Cần đánh giá toàn bộ quy trình: evidence, nguồn, binding, verification, enrollment, authenticator, recovery và vận hành. Một proofing mạnh nhưng recovery yếu có thể bị bypass sau đó.

### 7.1. Assurance là kết luận có phạm vi

Khi nói account đã được proofing, hãy ghi rõ:

- Đã xác minh những thuộc tính nào?
- Bằng chứng đến từ nguồn nào và thời điểm nào?
- Kết luận áp dụng cho account, tổ chức, giao dịch hay quyền nào?
- Phương thức verification nào đã được dùng?
- Có giới hạn, ngoại lệ hoặc bước review nào không?
- Khi nào cần proofing lại hoặc kiểm tra lại?

Không biến một kết quả “đã xác minh” thành nhãn vĩnh viễn. Địa chỉ, trạng thái nhân viên, giấy tờ, quyền đại diện và tình trạng account có thể thay đổi.

## 8. Step-up, manual review và xử lý mâu thuẫn

Một hệ thống tốt không cần ép mọi người đi qua luồng kiểm tra mạnh nhất. Nó cần biết khi nào bằng chứng hiện tại chưa đủ và chọn bước tiếp theo phù hợp.

### 8.1. Step-up

Step-up là yêu cầu thêm bằng chứng hoặc kiểm tra có assurance cao hơn. Ví dụ:

- Xác minh giấy tờ qua nguồn issuer thay vì chỉ OCR.
- Chuyển từ kiểm tra tự động sang video-assisted review.
- Yêu cầu một credential doanh nghiệp hoặc sponsor đã được xác minh.
- Kiểm tra một thuộc tính qua nguồn độc lập.
- Yêu cầu xác thực lại bằng authenticator hiện có trước khi thay đổi identity attribute.

Step-up phải gắn với subject, transaction, purpose và thời hạn. Không để người dùng gửi bằng chứng cho account A rồi dùng kết quả để proof account B. Nếu step-up thất bại, không âm thầm hạ assurance hoặc chuyển sang kênh yếu hơn mà không có policy.

### 8.2. Manual review

Manual review hữu ích khi:

- Nguồn dữ liệu mâu thuẫn nhưng có thể giải thích hợp lệ.
- Hệ thống tự động không hỗ trợ loại giấy tờ hoặc thiết bị của người dùng.
- Tín hiệu gian lận cần đánh giá ngữ cảnh.
- Account có quyền hoặc hậu quả cao.
- Người dùng cần quy trình hỗ trợ thay thế.

Reviewer cần checklist rõ, quyền truy cập tối thiểu, đào tạo, ghi nhận lý do và bằng chứng đã xem. Các trường hợp nhạy cảm nên có dual control hoặc phê duyệt độc lập. Reviewer không nên được phép sửa trực tiếp evidence hoặc xóa audit trail.

### 8.3. Kết quả không rõ ràng

Nếu không thể xác minh, kết quả đúng có thể là `PENDING` hoặc `REVIEW_REQUIRED`, không nhất thiết là `REJECTED`. Phân biệt:

- **Invalid evidence:** bằng chứng không hợp lệ hoặc bị giả mạo theo tiêu chí đáng tin.
- **Insufficient evidence:** chưa đủ bằng chứng để kết luận.
- **Technical failure:** nguồn hoặc hệ thống tạm thời không khả dụng.
- **Inconsistent data:** các nguồn mâu thuẫn cần điều tra.
- **Policy ineligible:** dịch vụ không thể hỗ trợ trường hợp theo chính sách.

Không đánh đồng lỗi kỹ thuật hoặc thiếu khả năng tiếp cận với gian lận. Cung cấp lý do ở mức phù hợp và quy trình appeal/retry có giới hạn.

## 9. Enrollment và recovery là phần tiếp nối của proofing

Sau proofing, hệ thống thường đăng ký passkey, security key, MFA hoặc recovery channel. Nếu attacker chiếm được phiên enrollment hoặc help desk, họ có thể gắn authenticator của mình vào danh tính đã proofing.

### Enrollment controls

- Yêu cầu session có assurance phù hợp và ràng buộc thao tác thêm authenticator với đúng subject.
- Step-up trước khi thêm, xóa hoặc thay đổi credential.
- Challenge/transaction một lần, TTL ngắn và chống CSRF.
- Ghi nhận loại authenticator, thời điểm, thiết bị và actor ở mức cần thiết.
- Thông báo qua kênh đã xác minh khi thêm phương thức mới.
- Không cho phép một reviewer tự phê duyệt thay đổi nhạy cảm của chính họ.

### Recovery controls

Recovery phải có assurance tương xứng với account và quyền được khôi phục. Email hoặc SMS có thể là kênh thông báo/khôi phục trong một số sản phẩm, nhưng không tự động là bằng chứng đủ mạnh cho tài khoản nhạy cảm.

Một quy trình recovery có thể gồm:

1. Tiếp nhận yêu cầu và xác định account mà không tiết lộ dữ liệu nhạy cảm.
2. Xác minh người yêu cầu bằng credential dự phòng hoặc quy trình proofing/recovery độc lập.
3. Kiểm tra thay đổi gần đây: email, số điện thoại, địa chỉ, thiết bị, MFA và recovery channel.
4. Áp dụng phê duyệt/cooldown cho account đặc quyền hoặc yêu cầu rủi ro cao.
5. Thu hồi session/token và authenticator có thể bị chiếm.
6. Đăng ký credential mới qua enrollment chuẩn, ghi audit và thông báo.
7. Theo dõi hoạt động sau recovery và hỗ trợ khi người dùng báo thao tác không phải của họ.

Nếu quy trình recovery cho phép nhân viên hỗ trợ bỏ qua proofing bằng một cuộc gọi hoặc thông tin công khai, attacker sẽ nhắm vào recovery thay vì proofing ban đầu.

## 10. Quyền riêng tư, công bằng và khả năng tiếp cận

Identity proofing thường xử lý dữ liệu nhạy cảm: giấy tờ, khuôn mặt, ngày sinh, địa chỉ, dữ liệu sinh trắc học và thông tin tổ chức. Kiểm soát rủi ro phải cân bằng bảo mật với mục đích sử dụng, quyền riêng tư và khả năng tiếp cận.

### 10.1. Data minimization

- Chỉ thu thập thuộc tính cần cho mục đích proofing đã xác định.
- Nếu chỉ cần biết một điều kiện đúng/sai, cân nhắc lưu kết quả xác minh thay vì bản sao toàn bộ giấy tờ.
- Xác định thời hạn lưu evidence, bản ghi review, ảnh và video; xóa hoặc ẩn danh khi hết mục đích.
- Mã hóa khi truyền và lưu; hạn chế người, service và vendor có thể truy cập.
- Không đưa ảnh giấy tờ, ảnh khuôn mặt, token hoặc số định danh vào log/analytics.
- Ghi nhận consent hoặc cơ sở xử lý phù hợp theo pháp luật và chính sách áp dụng.

### 10.2. Biometric fairness và false rejection

Face match/liveness có thể có hiệu năng khác nhau theo thiết bị, ánh sáng, độ tuổi, màu da, đặc điểm khuôn mặt, khuyết tật và điều kiện môi trường. Đánh giá model bằng dữ liệu đại diện và theo nhóm phù hợp; đo false acceptance và false rejection riêng. Không chỉ xem accuracy trung bình.

Người dùng có thị lực/vận động hạn chế, đặc điểm khuôn mặt khác biệt hoặc camera chất lượng thấp có thể không hoàn tất một flow nhất định. Cần phương thức thay thế an toàn, dễ tiếp cận và không buộc người dùng cung cấp dữ liệu sinh trắc học nếu có cách proofing khác phù hợp.

### 10.3. Giải thích và appeal

Khi từ chối hoặc yêu cầu review, thông báo nên nói rõ bước tiếp theo mà không tiết lộ rule fraud có thể bị attacker khai thác. Có quy trình appeal, người đánh giá độc lập và khả năng sửa dữ liệu sai. Không để một quyết định tự động không giải thích được trở thành rào cản vĩnh viễn.

## 11. Quản trị vendor và nguồn xác minh bên thứ ba

Nếu dùng dịch vụ OCR, liveness, document verification, identity graph hoặc database lookup của vendor, trách nhiệm quyết định cuối cùng vẫn thuộc tổ chức sử dụng dịch vụ.

Trước khi tích hợp, đánh giá:

- Nguồn dữ liệu và quyền truy cập của vendor; dữ liệu có authoritative hay chỉ là commercial signal?
- Model/version, hiệu năng theo nhóm, false accept/false reject và giới hạn tài liệu hỗ trợ.
- Cách truyền dữ liệu, vị trí lưu, thời hạn lưu, subprocessors và khả năng xóa.
- API authentication, TLS, request signing, tenant isolation và bảo vệ webhook.
- Cách vendor thông báo model update, outage, incident và thay đổi policy.
- Auditability: có lưu decision ID, evidence references, reason codes và version không?
- Khả năng export hoặc thay vendor để tránh phụ thuộc không kiểm soát.

Không tin response JSON chỉ vì nó đến từ một endpoint có tên “verified”. Phải xác thực nguồn, TLS, chữ ký webhook nếu có, tenant/request correlation và trạng thái transaction. Nếu vendor outage, giữ trạng thái pending hoặc chuyển kênh thay thế; không tự động accept mọi hồ sơ.

## 12. Pseudocode: quyết định proofing có ràng buộc rủi ro

Đoạn sau minh họa cách tách evidence validation, verification, risk policy và quyết định. Đây là pseudocode, không phải thuật toán chấm điểm pháp lý hay model fraud dùng trực tiếp trong production.

~~~java
ProofingDecision evaluateProofing(ProofingCase proofingCase) {
    if (proofingCase.isExpired() || proofingCase.isAlreadyConsumed()) {
        return ProofingDecision.reject("INVALID_TRANSACTION");
    }

    EvidenceBundle evidence = evidenceStore.loadForCase(proofingCase.id());
    if (evidence.isEmpty()) {
        return ProofingDecision.pending("EVIDENCE_REQUIRED");
    }

    ValidationResult validation = evidenceValidator.validate(
        evidence,
        proofingCase.allowedEvidenceTypes(),
        proofingCase.trustedIssuers(),
        proofingCase.purpose()
    );
    if (validation.hasKnownForgeryOrInvalidSignature()) {
        return ProofingDecision.reject("EVIDENCE_INVALID");
    }
    if (validation.hasUnavailableSource()) {
        return ProofingDecision.pending("SOURCE_UNAVAILABLE");
    }
    if (!validation.isSufficientForResolution()) {
        return ProofingDecision.stepUp("MORE_EVIDENCE_REQUIRED");
    }

    VerificationResult verification = identityVerifier.verifyBinding(
        proofingCase.claimedSubject(),
        evidence,
        proofingCase.verificationPolicy()
    );
    if (verification.isInconclusive()) {
        return ProofingDecision.manualReview("BINDING_INCONCLUSIVE");
    }
    if (!verification.matchesClaimedSubject()) {
        return ProofingDecision.reject("SUBJECT_MISMATCH");
    }

    RiskContext risk = riskEngine.evaluate(
        proofingCase.purpose(),
        validation,
        verification,
        proofingCase.contextSignals()
    );

    return proofingPolicy.decide(
        proofingCase.requiredAssurance(),
        validation.assurance(),
        verification.assurance(),
        risk
    );
}
~~~

Khi triển khai:

- Claimed subject, evidence và context phải gắn với case phía server; không cho client đổi subject sau khi bắt đầu proofing.
- Trusted issuers và allowed evidence types đến từ policy đã onboard, không từ input tùy ý.
- Kết quả lỗi OCR hoặc timeout không được tự động phân loại thành gian lận.
- Risk engine cần versioning, calibration, monitoring drift và review bias; không dùng score đơn lẻ như sự thật.
- Quyết định **ACCEPT** phải lưu policy version, evidence references, timestamps, reviewer/model và assurance scope.
- Không lưu raw biometric/evidence lâu hơn mục đích; áp dụng access control, encryption và retention.
- Enrollment authenticator là bước riêng sau khi case được chấp nhận; không tạo credential khi decision còn **PENDING**.

## 13. Audit trail và chỉ số vận hành

Một quyết định proofing cần tái dựng được mà không phải lưu mọi dữ liệu nhạy cảm trong log. Audit record nên có:

| Trường | Mục đích |
| --- | --- |
| **proofing_case_id** | Liên kết các bước của cùng một case |
| **subject_reference** | Tham chiếu subject nội bộ; tránh ghi PII thô không cần thiết |
| **purpose / required_assurance** | Lý do và mức yêu cầu của proofing |
| **evidence_type / issuer_reference** | Loại và nguồn evidence |
| **validation_result** | Kết quả kiểm tra tính hợp lệ và reason code |
| **verification_method / result** | Cách liên kết người với danh tính và kết quả |
| **risk_policy_version** | Policy/model đã tạo quyết định |
| **decision / decision_reason** | Accept, step-up, review, pending hoặc reject |
| **reviewer_id / approval_reference** | Người/phê duyệt nếu có |
| **created_at / completed_at** | Thời gian xử lý và độ trễ |
| **enrollment_reference** | Credential được tạo sau proofing nếu có |

Không ghi raw giấy tờ, ảnh/video khuôn mặt, private key, password, OTP hoặc recovery code vào log. Audit cần kiểm soát quyền, integrity, retention và khả năng truy cập phục vụ điều tra.

### Metrics nên theo dõi

- Tỷ lệ hoàn tất proofing theo kênh, evidence type, thiết bị và phiên bản flow.
- Tỷ lệ step-up, manual review, pending, reject và appeal.
- False accept/false reject được ước lượng qua kiểm tra độc lập và incident.
- Thời gian xử lý, tỷ lệ timeout và availability của nguồn xác minh.
- Tỷ lệ mismatch theo issuer/document type và drift theo model version.
- Account takeover/fraud sau proofing, thời gian phát hiện và tổn thất.
- Tỷ lệ recovery bypass, credential enrollment bất thường và thay đổi account sau proofing.
- Chênh lệch kết quả giữa nhóm người dùng hoặc điều kiện thiết bị, trong phạm vi thu thập dữ liệu hợp pháp.

Không tối ưu chỉ số conversion bằng cách giảm assurance mà không đánh giá fraud. Cũng không tối ưu tỷ lệ từ chối thấp bằng cách chấp nhận mọi trường hợp không rõ. Cần xem đồng thời fraud loss, false rejection, user friction, privacy và accessibility.

## 14. Kiểm thử proofing risk

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Ảnh giấy tờ đọc được nhưng issuer/source không xác minh được | Không coi OCR thành validation; pending hoặc yêu cầu nguồn khác |
| Giấy tờ hết hạn hoặc chữ ký số sai | Từ chối evidence theo policy |
| QR/credential hợp lệ nhưng thuộc subject khác | Không liên kết với người đăng ký |
| Người dùng dùng ảnh in/video replay | Kiểm soát presentation attack phát hiện hoặc chuyển step-up/review theo khả năng |
| Camera ảo hoặc luồng video bị inject | Không dựa vào client metadata; phát hiện/giới hạn theo threat model |
| Liveness score cao nhưng giấy tờ không hợp lệ | Không accept; evidence validation vẫn bắt buộc |
| Nhiều thuộc tính từ cùng một nguồn bị rò rỉ | Không đếm như nhiều evidence độc lập |
| IP VPN nhưng evidence và verification đáng tin | Không tự động reject chỉ vì VPN |
| Nhiều lần thử tạo account trên cùng thiết bị | Rate limit/risk review; không tự kết luận mọi account là cùng người |
| Nguồn authoritative timeout | Pending/retry hoặc alternative channel; không fail-open |
| Dữ liệu giữa hai nguồn mâu thuẫn | Manual review hoặc step-up; lưu reason code |
| Người dùng không thể hoàn thành face liveness | Cung cấp phương thức thay thế an toàn và dễ tiếp cận |
| Reviewer tự phê duyệt case của mình | Từ chối theo segregation-of-duties policy |
| Client đổi subject sau khi evidence đã thu thập | Transaction binding phát hiện; không dùng evidence cho subject khác |
| Account được accept nhưng enrollment chưa hoàn tất | Không tạo session/credential vượt policy; giữ trạng thái chờ |
| Recovery chỉ dựa vào email/phone yếu cho account đặc quyền | Yêu cầu assurance cao hơn và review |
| Vendor webhook giả hoặc sai tenant/case ID | Từ chối response và audit sự kiện |
| Model version thay đổi làm false reject tăng | Cảnh báo drift, rollback có kiểm soát và review |
| Proofing decision đã dùng lại để tạo account khác | Transaction/case one-time ngăn tái sử dụng |
| Audit trail chứa ảnh giấy tờ hoặc biometric thô | Privacy test phát hiện; redaction và retention controls áp dụng |

### Tình huống thực hành

Một nền tảng cho phép mở tài khoản tài chính từ xa. Flow hiện tại chỉ yêu cầu ảnh căn cước, OCR tên/ngày sinh và selfie liveness. Nếu OCR đọc được và liveness trả score trên ngưỡng, hệ thống đánh dấu **VERIFIED**. Sau đó người dùng có thể chuyển tiền và thay đổi email recovery. Một số account gian lận sử dụng giấy tờ thật bị đánh cắp và thiết bị ảo; đội vận hành cũng phát hiện một nhóm người dùng hợp lệ bị từ chối do camera chất lượng thấp.

**Yêu cầu:** thiết kế lại proofing risk và decision flow, bảo vệ cả người dùng hợp lệ lẫn tài khoản.

**Hướng phân tích:**

1. Tách resolution, evidence validation và identity verification. OCR chỉ trích xuất dữ liệu; liveness chỉ là tín hiệu hiện diện, không chứng minh giấy tờ thật hoặc chủ thể hợp lệ.
2. Thêm kiểm tra authenticity/validity và nguồn xác minh phù hợp cho giấy tờ; kiểm tra thuộc tính qua nguồn độc lập khi có cơ sở pháp lý.
3. Đánh giá rủi ro stolen identity, device injection, replay, velocity và account linkage. Không dùng một IP/device signal làm căn cứ từ chối duy nhất.
4. Với kết quả mâu thuẫn hoặc không chắc chắn, chuyển step-up/manual review; phân biệt technical failure với evidence invalid và suspected fraud.
5. Giới hạn quyền account ở trạng thái pending/low assurance. Chỉ mở chức năng tài chính sau khi proofing đạt assurance được policy yêu cầu và enrollment authenticator phù hợp.
6. Yêu cầu step-up cho thay đổi email/recovery và giao dịch rủi ro; thông báo qua kênh đã xác minh và áp dụng cooldown khi phù hợp.
7. Cung cấp phương thức thay thế cho người có camera yếu/không thể dùng liveness; theo dõi false rejection theo nhóm và thiết bị.
8. Thiết lập audit, retention, vendor controls, fraud monitoring và quy trình appeal; kiểm thử cả false accept lẫn false reject.

## 15. Câu hỏi tự kiểm tra

1. **Identity proofing khác authentication thế nào?** Proofing xác lập mối liên hệ giữa người và danh tính được khai; authentication xác minh người quay lại đang kiểm soát authenticator đã đăng ký.
2. **OCR thành công có chứng minh giấy tờ thật không?** Không. OCR chỉ trích xuất nội dung; cần validation về issuer, tính toàn vẹn, hiệu lực và nguồn.
3. **Liveness có chứng minh người đang thao tác là chủ giấy tờ không?** Không. Nó có thể giảm một số presentation attack nhưng cần kết hợp evidence validation và identity verification.
4. **Vì sao nhiều tín hiệu từ cùng nguồn không phải evidence độc lập?** Vì một nguồn bị chiếm hoặc sai có thể làm tất cả tín hiệu sai cùng lúc.
5. **VPN hoặc IP reputation xấu có đủ để từ chối proofing không?** Không. Đây là risk signal cần đặt trong ngữ cảnh, không phải bằng chứng danh tính.
6. **Khi nào dùng manual review?** Khi evidence mâu thuẫn, automation không đủ chắc, rủi ro cao hoặc người dùng cần phương thức thay thế; reviewer phải có quyền hạn và audit rõ.
7. **Vì sao recovery phải có assurance tương xứng?** Vì attacker có thể bypass proofing ban đầu bằng cách chiếm kênh recovery hoặc lừa help desk.
8. **Một nhãn VERIFIED cần đi kèm thông tin gì?** Phạm vi thuộc tính, nguồn evidence, phương thức, thời điểm, policy/version, assurance và giới hạn của kết luận.

**Ghi nhớ:** Proofing risk không được giải quyết bằng một điểm liveness, OCR hay fraud score. Hãy xác định hậu quả của việc nhận nhầm người, đánh giá **nguồn và độ độc lập của evidence**, tách resolution/validation/verification, kết hợp risk signals đúng vai trò, và chọn accept/step-up/review/pending/reject có lý do. Bảo vệ enrollment, recovery, privacy và khả năng tiếp cận để assurance của danh tính được duy trì sau lần proofing đầu tiên.
