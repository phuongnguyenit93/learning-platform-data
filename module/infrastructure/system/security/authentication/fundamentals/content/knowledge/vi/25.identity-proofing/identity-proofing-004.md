# Knowledge-based verification

## 1. Knowledge-based verification là gì?

**Knowledge-based verification (KBV)** là cách kiểm tra một người có biết thông tin được cho là chỉ người có liên quan tới một danh tính mới biết hay không. Trong quy trình identity proofing từ xa, hệ thống có thể đặt câu hỏi dựa trên hồ sơ đã được một nguồn dữ liệu tin cậy thu thập trước đó, rồi so sánh câu trả lời với hồ sơ.

Ví dụ, một nhà cung cấp dịch vụ muốn kiểm tra người đang yêu cầu mở tài khoản có liên hệ với hồ sơ danh tính đã khai báo. Hệ thống có thể yêu cầu chọn một thông tin trong số các lựa chọn được tạo từ dữ liệu lịch sử đã xác minh. Nếu câu trả lời khớp, đó là một tín hiệu hỗ trợ quy trình kiểm tra.

Tuy nhiên, **biết một thông tin cá nhân không đồng nghĩa với chứng minh chắc chắn danh tính**. Dữ liệu có thể đã bị lộ, được chia sẻ trong gia đình, xuất hiện trên mạng hoặc bị suy đoán. KBV chỉ cho biết người trả lời có khả năng biết thông tin được hỏi; nó không tự chứng minh người đó là chủ thể hợp pháp của hồ sơ.

Trong module `SECURITY_AUTHENTICATION_FUNDAMENTALS`, KBV cần được hiểu trong bối cảnh identity proofing: hệ thống phải đánh giá nguồn dữ liệu, độ tin cậy của câu hỏi, nguy cơ lộ thông tin, sai lệch hồ sơ và hậu quả khi chấp nhận nhầm.

## 2. Phân biệt identity proofing, authentication và KBV

Ba khái niệm thường bị gộp làm một:

| Khái niệm | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Identity proofing** | Thu thập và đánh giá bằng chứng để xác lập một danh tính trong một mức bảo đảm cụ thể. | Kiểm tra giấy tờ, đối chiếu dữ liệu với nguồn có thẩm quyền, xác minh người đang hiện diện. |
| **Authentication** | Xác minh người dùng hiện tại đang kiểm soát credential đã đăng ký với tài khoản. | Passkey ký challenge, mật khẩu và MFA. |
| **Knowledge-based verification** | Kiểm tra người trả lời có biết một số thông tin liên quan tới hồ sơ hay không. | Trả lời câu hỏi được tạo từ dữ liệu lịch sử đã có. |

KBV có thể được dùng như một tín hiệu trong identity proofing hoặc trong một số quy trình hỗ trợ tài khoản. Nó không tự thay thế việc xác minh giấy tờ, xác minh nguồn dữ liệu, kiểm tra quyền kiểm soát credential hay xác thực phiên đăng nhập.

Một người có thể biết địa chỉ cũ hoặc thông tin giao dịch của người khác vì họ là người thân, đồng nghiệp, nhân viên hỗ trợ hoặc đã mua được dữ liệu bị lộ. Điều đó không chứng minh họ là chính chủ. Ngược lại, chủ thể thật có thể không nhớ chính xác dữ liệu cũ hoặc dữ liệu nguồn có thể sai, khiến họ trả lời không khớp.

## 3. Các loại knowledge-based verification

### 3.1. Static KBA

**Static knowledge-based authentication/verification** dùng câu hỏi và câu trả lời được thiết lập trước, thường do người dùng chọn hoặc khai báo khi tạo tài khoản.

Ví dụ kiểu câu hỏi thường gặp trong các hệ thống cũ là thông tin về nơi sinh, trường học, tên người thân hoặc một sự kiện cá nhân. Những dữ liệu này thường có thể xuất hiện trong mạng xã hội, hồ sơ công khai, rò rỉ dữ liệu hoặc được người quen biết.

Rủi ro chính:

- Câu trả lời thường có entropy thấp hoặc có thể suy đoán.
- Người dùng có thể chọn câu trả lời dễ nhớ nhưng cũng dễ tìm.
- Cùng một câu trả lời có thể được dùng ở nhiều dịch vụ.
- Câu trả lời lâu ngày không còn đúng hoặc người dùng quên.
- Nếu database lưu câu trả lời dạng đọc được, việc lộ dữ liệu có thể tạo thêm một kho bí mật yếu.

Static KBA không nên được xem là một yếu tố xác thực mạnh hay là biện pháp duy nhất để khôi phục tài khoản nhạy cảm.

### 3.2. Dynamic KBA

**Dynamic knowledge-based verification** tạo câu hỏi tại thời điểm kiểm tra từ dữ liệu đã tồn tại trong một hoặc nhiều nguồn, ví dụ hồ sơ lịch sử, dữ liệu tài chính hoặc dữ liệu của nhà cung cấp có thẩm quyền.

Hệ thống thường đưa ra nhiều lựa chọn, trong đó chỉ một lựa chọn khớp với hồ sơ. Người trả lời cần chọn thông tin đúng mà họ được cho là biết.

Dynamic KBA tránh việc người dùng tự chọn câu trả lời yếu từ đầu, nhưng không giải quyết được vấn đề căn bản: dữ liệu nguồn có thể bị lộ, sai, cũ hoặc được chia sẻ. Nhiều lựa chọn cũng làm giảm lượng thông tin cần đoán so với một câu trả lời mở.

### 3.3. So sánh

| Tiêu chí | Static KBA | Dynamic KBA |
| --- | --- | --- |
| Nguồn câu hỏi | Người dùng khai báo hoặc chọn trước. | Tạo từ hồ sơ dữ liệu có sẵn. |
| Trải nghiệm | Có thể quen thuộc nhưng dễ quên. | Có thể bất ngờ và khó hiểu nếu dữ liệu cũ. |
| Rủi ro đoán | Câu trả lời thường dễ đoán hoặc tìm. | Phụ thuộc chất lượng, độ bí mật và độ phủ của nguồn dữ liệu. |
| Rủi ro lộ dữ liệu | Câu trả lời có thể bị lộ qua dịch vụ lưu trữ. | Dữ liệu nguồn có thể bị rò rỉ từ nhà cung cấp hoặc nguồn công khai. |
| Độ chính xác | Phụ thuộc câu trả lời đã đăng ký và khả năng nhớ. | Phụ thuộc độ mới, độ đúng và cách liên kết hồ sơ. |
| Vai trò phù hợp | Tín hiệu phụ có rủi ro thấp; không dùng làm kiểm soát mạnh duy nhất. | Tín hiệu phụ trong quy trình proofing được thiết kế và đánh giá rủi ro. |

## 4. Luồng dynamic KBV

Một luồng minh họa:

~~~mermaid
sequenceDiagram
    participant U as Người yêu cầu
    participant P as Proofing service
    participant D as Nguồn dữ liệu
    participant R as Risk / policy engine
    U->>P: Cung cấp thông tin định danh cần kiểm tra
    P->>D: Truy vấn dữ liệu theo mục đích được phép
    D-->>P: Bản ghi và thông tin chất lượng dữ liệu
    P->>R: Đánh giá khả năng dùng dữ liệu để tạo câu hỏi
    R-->>P: Cho phép, yêu cầu bổ sung hoặc từ chối KBV
    P-->>U: Câu hỏi với các lựa chọn
    U->>P: Gửi câu trả lời
    P->>R: Đánh giá kết quả cùng tín hiệu khác
    R-->>P: Quyết định theo policy
    P-->>U: Tiếp tục, yêu cầu phương thức khác hoặc dừng
~~~

Luồng này không nên tiết lộ câu trả lời đúng hoặc cho biết quá nhiều về dữ liệu đang được kiểm tra. Hệ thống cũng cần giới hạn số lần thử và thời gian hiệu lực của thử thách.

Các bước chính:

1. Xác định mục đích và mức bảo đảm của quy trình proofing.
2. Kiểm tra nguồn dữ liệu có được phép sử dụng cho mục đích này hay không.
3. Đánh giá độ mới, độ chính xác và mức liên kết của hồ sơ với danh tính cần kiểm tra.
4. Chỉ tạo câu hỏi nếu dữ liệu đủ chất lượng và không có dấu hiệu rủi ro khiến KBV không phù hợp.
5. Trình bày câu hỏi theo cách dễ hiểu, không gây lộ dữ liệu quá mức.
6. Kiểm tra câu trả lời, giới hạn số lần thử và ghi nhận kết quả tối thiểu cần thiết.
7. Kết hợp với các bằng chứng và tín hiệu khác để quyết định bước tiếp theo.

## 5. Chất lượng nguồn dữ liệu quyết định chất lượng KBV

Dynamic KBA thường được quảng bá là dựa trên dữ liệu lịch sử, nhưng dữ liệu lịch sử không tự động trở thành dữ liệu đáng tin. Trước khi sử dụng một nguồn, cần đánh giá:

| Thuộc tính | Câu hỏi đánh giá |
| --- | --- |
| **Authority** | Nguồn có thẩm quyền hoặc có quan hệ hợp lệ với thông tin cần xác minh không? |
| **Provenance** | Dữ liệu đến từ đâu, được thu thập và cập nhật bằng quy trình nào? |
| **Accuracy** | Tỷ lệ sai, thiếu hoặc gán nhầm bản ghi là bao nhiêu? |
| **Freshness** | Dữ liệu được cập nhật lần cuối khi nào? |
| **Coverage** | Nguồn có đủ dữ liệu cho nhóm người dùng mục tiêu không? |
| **Uniqueness** | Bản ghi có phân biệt được người có cùng tên hoặc thông tin tương tự không? |
| **Security** | Nhà cung cấp bảo vệ dữ liệu, API, tài khoản và log như thế nào? |
| **Permitted use** | Hợp đồng, luật và thông báo quyền riêng tư có cho phép dùng dữ liệu để proofing không? |

Không nên tạo câu hỏi từ dữ liệu thiếu nguồn gốc, đã lỗi thời hoặc có nhiều bản ghi xung đột. Nếu hồ sơ không đủ chất lượng, hệ thống nên chuyển sang phương thức proofing khác thay vì tạo câu hỏi mà ngay cả chủ thể thật cũng khó trả lời.

## 6. Câu hỏi tốt và câu hỏi yếu

Một câu hỏi KBV chỉ có ích nếu câu trả lời:

- Liên quan đủ chặt tới hồ sơ của chủ thể.
- Không dễ tìm kiếm công khai hoặc suy ra từ dữ liệu phổ biến.
- Có không gian câu trả lời đủ lớn để khó đoán.
- Có một đáp án rõ ràng theo nguồn dữ liệu.
- Không đòi hỏi người dùng tiết lộ thêm thông tin nhạy cảm ngoài mục đích.
- Không gây bất lợi có hệ thống cho người có lịch sử sống, gia đình hoặc nơi cư trú khác nhau.

Ví dụ về câu hỏi yếu:

- Thông tin thường xuất hiện trên hồ sơ mạng xã hội.
- Tên người thân hoặc thú cưng.
- Địa chỉ hiện tại được đăng công khai.
- Thông tin dễ đoán từ ngày sinh, tên hoặc nơi làm việc.

Ngay cả câu hỏi có vẻ riêng tư cũng có thể bị biết bởi người thân, người cùng nhà, nhân viên có quyền truy cập hoặc attacker mua dữ liệu bị lộ. Không nên coi “không công khai trên Google” là “chỉ chủ thể biết”.

### 6.1. Không nhầm số lựa chọn với entropy thực

Một câu hỏi có bốn lựa chọn không cung cấp bốn lựa chọn có xác suất ngang nhau nếu một đáp án phổ biến hơn nhiều. Attacker có thể chọn đáp án có xác suất cao nhất hoặc dùng dữ liệu phụ để loại trừ lựa chọn.

Nếu câu trả lời chỉ có một số ít khả năng, nhiều lần thử sẽ làm xác suất đoán thành công tăng lên. Vì vậy cần giới hạn số lần thử, tránh cho phép tạo câu hỏi mới liên tục và không để phản hồi tiết lộ đáp án gần đúng.

### 6.2. Tránh câu hỏi gây phân biệt hoặc loại trừ

Người dùng có thể:

- Thường xuyên chuyển nhà hoặc chưa từng có địa chỉ tín dụng.
- Dùng tên hợp pháp khác nhau theo thời gian.
- Có lịch sử tài chính ngắn hoặc không có hồ sơ tại nguồn dữ liệu.
- Sống trong gia đình nhiều thế hệ hoặc dùng chung địa chỉ.
- Có dữ liệu bị ghi sai, thiếu hoặc liên kết nhầm.

Những trường hợp này không chứng minh người dùng là gian lận. Quy trình phải có phương án thay thế và hỗ trợ khi dữ liệu không đủ hoặc không khớp.

## 7. Mối đe dọa đối với KBV

### 7.1. Dữ liệu cá nhân bị rò rỉ

Attacker có thể thu thập câu trả lời từ các vụ rò rỉ dữ liệu, môi giới dữ liệu, hồ sơ công khai hoặc tài khoản bị chiếm. Khi đó, câu hỏi vốn được xem là bí mật không còn bí mật.

### 7.2. OSINT và suy luận

Thông tin về nơi học, công việc, gia đình, địa chỉ hoặc hoạt động có thể xuất hiện trong nhiều nguồn. Attacker ghép các dữ liệu rời rạc để suy ra đáp án mà không cần truy cập trực tiếp hồ sơ gốc.

### 7.3. Insider hoặc người có quan hệ gần

Người thân, đồng nghiệp, nhân viên hỗ trợ hoặc người từng cùng sống có thể biết thông tin mà hệ thống cho là chỉ chủ tài khoản biết. KBV không chứng minh người trả lời có quyền đại diện cho danh tính đó.

### 7.4. Brute force và enumeration

Nếu hệ thống cho thử nhiều lần, attacker có thể đoán đáp án. Nếu thông báo lỗi khác nhau theo câu trả lời hoặc nguồn dữ liệu, phản hồi có thể tiết lộ thông tin về hồ sơ.

### 7.5. Synthetic identity và hồ sơ bị trộn

Attacker có thể kết hợp thông tin thật của nhiều người để tạo hồ sơ tổng hợp. Ngược lại, nhà cung cấp dữ liệu có thể ghép nhầm thông tin của nhiều người thành một hồ sơ. Một câu trả lời khớp không loại trừ khả năng hồ sơ đã bị trộn hoặc danh tính bị mạo danh.

### 7.6. Tấn công quy trình hỗ trợ

Nếu nhân viên hỗ trợ được phép bỏ qua KBV hoặc đặt lại kết quả chỉ bằng một cuộc gọi, attacker có thể nhắm vào quy trình con người thay vì phá câu hỏi. Quy trình ngoại lệ phải có xác minh, phân quyền và audit tương xứng.

## 8. Biện pháp giảm thiểu

KBV không nên là tuyến phòng thủ duy nhất. Khi vẫn sử dụng, cần có các kiểm soát sau:

1. **Data minimization:** chỉ truy vấn và giữ dữ liệu cần thiết cho mục đích proofing.
2. **Nguồn đáng tin:** đánh giá nguồn, provenance, độ mới, độ chính xác và quyền sử dụng dữ liệu.
3. **Challenge ngắn hạn:** câu hỏi gắn với một proofing flow, có thời hạn và không dùng lại.
4. **Attempt limit:** giới hạn số lần trả lời và áp dụng rate limit theo phiên, danh tính, thiết bị và tín hiệu rủi ro.
5. **Generic failure:** không tiết lộ đáp án đúng, số trường dữ liệu khớp hoặc lý do chi tiết cho attacker.
6. **Risk-based fallback:** khi dữ liệu thiếu, câu trả lời không khớp hoặc có dấu hiệu rủi ro, chuyển sang phương thức khác đã được phê duyệt.
7. **Independent evidence:** kết hợp bằng chứng từ nguồn độc lập; không tính nhiều câu hỏi từ cùng một database là nhiều yếu tố độc lập.
8. **Secure processing:** mã hóa dữ liệu khi truyền/lưu, kiểm soát truy cập, audit và quản lý nhà cung cấp.
9. **Abuse monitoring:** phát hiện thử nhiều danh tính, nhiều thiết bị, nhiều IP hoặc pattern câu hỏi bất thường; không dựa vào một tín hiệu đơn lẻ.
10. **Human review:** cung cấp quy trình xử lý ngoại lệ có kiểm soát và kiểm tra lại khi quyết định có tác động lớn.

Không nên dùng KBV để khôi phục một tài khoản đặc quyền chỉ vì người yêu cầu trả lời đúng vài câu hỏi. Với thao tác rủi ro cao, cần credential đã đăng ký, proofing độc lập hoặc quy trình phê duyệt có bảo đảm phù hợp.

## 9. KBV và các yếu tố xác thực

Thông tin người dùng biết có thể được gọi là yếu tố knowledge trong mô hình xác thực. Nhưng KBV dựa trên thông tin cá nhân thường không có đặc tính của một bí mật xác thực tốt:

- Người dùng không kiểm soát độc quyền thông tin.
- Thông tin có thể bị lộ mà chủ thể không biết.
- Không thể dễ dàng thay đổi một số dữ kiện lịch sử như nơi sinh hoặc tên trường.
- Cùng một thông tin có thể được nhiều người biết.

Vì vậy, không nên xem việc trả lời câu hỏi KBV là MFA mạnh. Nó cũng không tương đương passkey, security key hoặc OTP được tạo từ secret đã đăng ký.

| Phương thức | Nguồn bằng chứng | Khả năng chống phishing/replay |
| --- | --- | --- |
| KBV | Kiến thức về thông tin hồ sơ | Thấp nếu thông tin có thể bị thu thập hoặc đoán; không có ràng buộc origin tự nhiên. |
| Password | Bí mật người dùng đã đăng ký | Có thể bị phishing, credential stuffing và replay nếu giao thức yếu. |
| TOTP | Secret chia sẻ và thời gian | Có thể bị relay/phishing trong cửa sổ mã. |
| Passkey/WebAuthn | Private key được authenticator giữ và ký challenge | Có ràng buộc RP ID/origin giúp chống phishing theo thiết kế. |
| Security key | Credential khóa công khai trên thiết bị phần cứng | Có thể chống phishing tốt khi dùng đúng giao thức và policy. |

Nếu cần xác minh danh tính từ xa, nên đánh giá bằng chứng danh tính và kiểm tra quyền kiểm soát credential theo tiêu chuẩn/mức bảo đảm mục tiêu. KBV chỉ nên đóng vai trò phụ khi mô hình rủi ro chứng minh nó có giá trị.

## 10. Quyết định khi câu trả lời đúng hoặc sai

Không nên xây dựng policy kiểu “đúng một câu là chấp nhận, sai một câu là kết luận gian lận”. Kết quả KBV cần được diễn giải cùng chất lượng nguồn dữ liệu và các tín hiệu độc lập.

Một mô hình quyết định:

| Kết quả | Hướng xử lý |
| --- | --- |
| Dữ liệu đủ chất lượng, câu trả lời khớp và không có tín hiệu rủi ro khác | Tiếp tục quy trình proofing theo policy; không tự động nâng mức bảo đảm vượt quá bằng chứng. |
| Dữ liệu thiếu, cũ hoặc không có câu hỏi phù hợp | Chuyển sang bằng chứng/phương thức khác; không xem là thất bại của người dùng. |
| Câu trả lời không khớp nhưng dữ liệu có thể sai | Cho phép phương án kiểm tra lại hoặc hỗ trợ có kiểm soát. |
| Vượt giới hạn thử hoặc có dấu hiệu tự động hóa | Tạm dừng, rate limit và đánh giá rủi ro. |
| Nhiều tín hiệu độc lập cho thấy mạo danh | Chuyển human review hoặc từ chối theo policy có giải trình phù hợp. |

Thông báo tới người dùng nên tránh tiết lộ dữ liệu nguồn. Ví dụ, nói “Chúng tôi chưa thể xác minh bằng phương thức này” an toàn hơn việc chỉ rõ trường dữ liệu nào không khớp.

## 11. Quyền riêng tư và quản trị dữ liệu

KBV thường cần truy vấn dữ liệu cá nhân từ bên thứ ba. Đây là hoạt động xử lý dữ liệu cần mục đích rõ ràng và kiểm soát:

- Chỉ thu thập trường dữ liệu cần cho câu hỏi.
- Không lưu câu trả lời thô lâu hơn thời gian cần thiết.
- Không đưa câu hỏi, đáp án hoặc dữ liệu nguồn vào log ứng dụng, analytics hay ticket hỗ trợ.
- Mã hóa dữ liệu khi truyền và khi lưu; giới hạn quyền truy cập theo vai trò và mục đích.
- Xác định thời hạn lưu giữ, xóa và cách xử lý yêu cầu của chủ thể dữ liệu.
- Đánh giá nhà cung cấp, bên xử lý phụ, nơi lưu trữ và việc chia sẻ dữ liệu.
- Ghi nhận nguồn và phiên bản dữ liệu đủ để điều tra, nhưng không sao chép toàn bộ hồ sơ nếu không cần.
- Đánh giá tác động sai lệch và khả năng loại trừ các nhóm người dùng không có hồ sơ trong nguồn dữ liệu.

Nếu lưu một câu trả lời để dùng lại như secret, hệ thống đang tạo ra một kho credential mới. Điều đó làm tăng rủi ro và thường không cần thiết. Nếu cần lưu kết quả proofing, ưu tiên lưu quyết định, thời điểm, phương thức, nguồn và mã tương quan tối thiểu thay vì plaintext answer.

## 12. Ví dụ thiết kế: mở tài khoản dịch vụ trực tuyến

Một dịch vụ tài chính đang xây dựng quy trình onboarding từ xa. Họ cân nhắc dùng dynamic KBV để bổ sung cho kiểm tra giấy tờ và đối chiếu danh tính.

**Thiết kế có kiểm soát:**

1. Người dùng cung cấp dữ liệu cần thiết và đồng ý với mục đích xử lý được thông báo.
2. Dịch vụ kiểm tra dữ liệu từ nguồn có thẩm quyền theo hợp đồng và chính sách.
3. Risk engine đánh giá hồ sơ có đủ mới, đủ chính xác và đủ độc nhất để tạo câu hỏi không.
4. Nếu phù hợp, hệ thống tạo một challenge ngẫu nhiên gắn với flow, hết hạn nhanh và giới hạn số lần thử.
5. Câu hỏi không hiển thị quá nhiều dữ liệu cá nhân; phản hồi sai không tiết lộ trường nào đúng.
6. Kết quả chỉ là một tín hiệu trong quyết định tổng thể, cùng kiểm tra giấy tờ, kiểm tra tính nhất quán và các bằng chứng độc lập khác.
7. Nếu dữ liệu không đủ hoặc người dùng không trả lời được, dịch vụ cung cấp phương án thay thế như quy trình kiểm tra thủ công hoặc bằng chứng khác.
8. Kết quả, nguồn và lý do quyết định được audit ở mức tối thiểu; câu trả lời thô được loại bỏ theo chính sách lưu giữ.

**Tình huống sai lệch:** người dùng thật vừa chuyển nhà nên hồ sơ nguồn chưa cập nhật. Hệ thống không nên kết luận họ là kẻ mạo danh chỉ vì địa chỉ cũ không khớp với thông tin họ vừa khai. Quy trình cần cho phép xác minh bằng nguồn khác và ghi nhận chất lượng dữ liệu.

## 13. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng KBV làm bằng chứng danh tính duy nhất | Người biết hoặc mua được dữ liệu có thể vượt qua. | Kết hợp bằng chứng độc lập và proofing phù hợp mức bảo đảm. |
| Coi câu hỏi cá nhân là bí mật | Thông tin có thể bị lộ, chia sẻ hoặc suy đoán. | Đánh giá threat model; không dựa vào dữ liệu công khai/dễ tìm. |
| Không giới hạn số lần thử | Attacker có thể brute force đáp án. | Rate limit, attempt limit và phát hiện lạm dụng. |
| Phản hồi tiết lộ trường nào sai | Attacker thu thập thêm dữ liệu về hồ sơ. | Dùng thông báo chung và tránh oracle thông tin. |
| Dùng dữ liệu cũ hoặc sai | Từ chối nhầm chủ thể thật. | Đánh giá freshness/accuracy và cung cấp fallback. |
| Dùng nhiều câu hỏi từ cùng một nguồn như bằng chứng độc lập | Đánh giá quá cao độ tin cậy. | Xem xét sự phụ thuộc nguồn và kết hợp bằng chứng thực sự độc lập. |
| Lưu đáp án thô trong log/database | Tạo kho thông tin cá nhân dễ bị khai thác. | Data minimization, mã hóa, hạn chế truy cập và xóa sớm. |
| Bỏ qua người không có hồ sơ dữ liệu | Loại trừ người dùng hợp lệ. | Có phương thức thay thế và quy trình hỗ trợ dễ tiếp cận. |
| Cho nhân viên hỗ trợ override không kiểm soát | Attacker chuyển sang social engineering. | Phân quyền, xác minh độc lập, phê duyệt và audit. |
| Coi KBV là MFA chống phishing | Đánh giá sai mức bảo đảm. | Phân biệt knowledge check với credential authentication và phishing resistance. |

## 14. Checklist đánh giá KBV

Trước khi dùng KBV trong quy trình identity proofing, hãy kiểm tra:

1. Mục đích sử dụng là gì và mức bảo đảm yêu cầu có phù hợp với KBV không?
2. KBV đang là static hay dynamic? Vì sao chọn loại đó?
3. Nguồn dữ liệu có thẩm quyền, provenance, độ chính xác, độ mới và quyền sử dụng hợp lệ không?
4. Câu hỏi có thể bị tìm thấy, mua, suy luận hoặc biết bởi người thân/insider không?
5. Đáp án có đủ không gian khó đoán, và hệ thống có giới hạn thử/rate limit không?
6. Challenge có ngắn hạn, gắn với đúng flow và không thể tái sử dụng không?
7. Thông báo lỗi có tránh tiết lộ đáp án hoặc thuộc tính hồ sơ không?
8. Có phương án thay thế cho dữ liệu thiếu, cũ, sai hoặc người dùng không có hồ sơ không?
9. KBV có được kết hợp với bằng chứng độc lập và risk policy không?
10. Quy trình hỗ trợ/override có xác minh, phân quyền, phê duyệt và audit không?
11. Dữ liệu câu hỏi/câu trả lời có được tối thiểu hóa, mã hóa, hạn chế truy cập và xóa đúng hạn không?
12. Có đánh giá nhà cung cấp, tác động quyền riêng tư, sai lệch và khả năng tiếp cận không?
13. Có kiểm thử brute force, enumeration, dữ liệu bị lộ, hồ sơ trộn, replay và lỗi nguồn dữ liệu không?

**Kết luận:** Knowledge-based verification kiểm tra khả năng biết thông tin liên quan tới hồ sơ, nhưng thông tin cá nhân không phải bí mật độc quyền và có thể bị lộ, đoán hoặc chia sẻ. Static KBA và dynamic KBA đều có giới hạn; dynamic KBA còn phụ thuộc mạnh vào chất lượng và quyền sử dụng nguồn dữ liệu. Nếu được dùng, KBV nên là tín hiệu phụ có giới hạn thử, challenge ngắn hạn, bảo vệ quyền riêng tư và phương án thay thế. Không dùng câu trả lời KBV đơn lẻ để kết luận chắc chắn danh tính hoặc thay thế credential authentication chống phishing.
