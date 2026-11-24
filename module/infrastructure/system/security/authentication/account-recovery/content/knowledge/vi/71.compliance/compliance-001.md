# Recovery control mapping — Ánh xạ kiểm soát khôi phục tài khoản

## 1. Vấn đề cần giải quyết

Một nhóm phát triển có thể đã triển khai token dùng một lần, xác minh MFA và nhật ký khôi phục nhưng vẫn lúng túng khi được hỏi: “Kiểm soát này đáp ứng yêu cầu nào, áp dụng cho luồng nào và bằng chứng ở đâu?”. Chiều ngược lại cũng thường xảy ra: bảng tuân thủ ghi “đã đáp ứng” nhưng chỉ liên kết tới tài liệu thiết kế, trong khi helpdesk vẫn có quyền bỏ qua xác minh danh tính.

**Recovery control mapping** là việc lập quan hệ có thể kiểm chứng giữa yêu cầu, rủi ro, kiểm soát và hành vi thực tế của hệ thống khôi phục tài khoản. Kết quả tốt cho phép người đọc đi theo cả hai chiều:

```text
Yêu cầu có phiên bản và phạm vi
    → rủi ro cần xử lý
    → mục tiêu kiểm soát
    → điểm thực thi trong hệ thống
    → kiểm thử và bằng chứng vận hành
    → kết luận cùng giới hạn của kết luận

Một thay đổi ở endpoint recovery
    → kiểm soát bị ảnh hưởng
    → yêu cầu cần đánh giá lại
    → bằng chứng phải thu thập lại
```

Trong phạm vi `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, ánh xạ phải bao quát việc mất mật khẩu, MFA, passkey hoặc thiết bị xác thực; đồng thời xem xét chống lạm dụng, xác minh danh tính và session sau khôi phục. Chỉ kiểm tra trang “Quên mật khẩu” sẽ bỏ sót phần lớn đường đi có thể dẫn tới chiếm đoạt tài khoản.

Sau bài học, người đọc cần có khả năng xây dựng một ma trận kiểm soát recovery, phân biệt yêu cầu nguồn với quyết định thiết kế nội bộ, xác định bằng chứng phù hợp và diễn đạt chính xác mức độ đáp ứng. Một ma trận kỹ thuật hỗ trợ đánh giá tuân thủ; bản thân nó không tạo ra chứng nhận hoặc kết luận pháp lý cho toàn tổ chức.

## 2. Phân biệt những đối tượng thường bị gộp chung

| Đối tượng | Câu hỏi nó trả lời | Ví dụ trong recovery |
| --- | --- | --- |
| Yêu cầu nguồn | Điều gì được yêu cầu trong bối cảnh áp dụng? | Một yêu cầu thuộc phiên bản tiêu chuẩn đã chọn |
| Rủi ro | Điều gì có thể gây thiệt hại? | Người kiểm soát hộp thư dùng reset password để vô hiệu hóa MFA |
| Mục tiêu kiểm soát | Tính chất bảo vệ nào cần được duy trì? | Khôi phục mật khẩu không tự cấp quyền thay thế yếu tố MFA |
| Cơ chế triển khai | Hệ thống duy trì tính chất đó bằng cách nào? | Recovery grant có purpose riêng; endpoint MFA không chấp nhận grant reset password |
| Bằng chứng | Dữ liệu nào cho phép kiểm tra tuyên bố? | Phiên bản policy, kết quả test, cấu hình triển khai, mẫu sự kiện đã che dữ liệu |
| Kết quả kiểm thử | Hành vi nào đã được quan sát? | Grant reset password bị từ chối khi gọi endpoint thay MFA |
| Kết luận đánh giá | Có thể khẳng định điều gì trong phạm vi nào? | Luồng web ở release được kiểm thử đáp ứng mục tiêu này; luồng helpdesk còn thiếu bằng chứng |

“Có dùng JWT” là mô tả công nghệ. “Không thể dùng quyền reset mật khẩu để thay MFA” là mục tiêu kiểm soát. “Test trên release X đã từ chối thao tác chéo purpose” là một mẩu bằng chứng. Ba câu không thay thế được nhau.

Một kiểm soát có thể liên quan đến nhiều yêu cầu; một yêu cầu cũng có thể cần nhiều kiểm soát. Quan hệ này thường là nhiều–nhiều. Không ép bảng thành một yêu cầu tương ứng đúng một API hoặc một bài test.

## 3. Chốt phạm vi trước khi điền ma trận

### 3.1. Liệt kê mọi đường khôi phục và quyền được cấp

Một ứng dụng có thể có các đường đi sau:

| Đường đi | Điểm tin cậy cần xem xét | Quyền cuối luồng cần kiểm tra |
| --- | --- | --- |
| Quên mật khẩu, còn MFA | Bằng chứng được dùng để cho phép đặt mật khẩu mới | Đặt mật khẩu; không mặc nhiên xóa MFA |
| Mất MFA, còn yếu tố khác | Policy cho phép thay thế yếu tố nào, dựa trên tổ hợp bằng chứng nào | Đăng ký yếu tố thay thế và xử lý yếu tố bị mất |
| Mất một thiết bị có passkey | Có còn authenticator hợp lệ khác không; ai quản lý việc phục hồi credential | Quản lý credential đúng tài khoản và đúng phạm vi |
| Mất toàn bộ phương tiện xác thực | Cơ chế recovery đã thiết lập trước và điều kiện xác minh lại | Gắn authenticator mới sau khi đủ điều kiện |
| Helpdesk hỗ trợ | Quyền của nhân viên, nguồn xác minh, phê duyệt và ghi nhận quyết định | Quyền khôi phục có giới hạn, không phải quyền đăng nhập tùy ý |
| Tài khoản qua IdP | Phần nào do IdP thực thi, phần nào do ứng dụng thực thi | Đồng bộ trạng thái tài khoản, credential và session theo hợp đồng |
| Recovery khi nghi bị chiếm đoạt | Những kênh hoặc session nào có thể đã bị đối phương kiểm soát | Khôi phục quyền kiểm soát và chặn tiếp tục truy cập trái phép |

Không giả định passkey luôn đồng bộ hoặc luôn gắn với một thiết bị. Thuộc tính triển khai ảnh hưởng tới việc “mất điện thoại” có thực sự làm mất khả năng xác thực hay không. Khi chưa xác định được mô hình, ghi điều kiện chưa rõ thay vì tự coi mọi passkey có cùng khả năng phục hồi.

### 3.2. Chốt các chiều phạm vi

Mỗi bản đánh giá cần nhận diện ít nhất sản phẩm, release, môi trường, loại tài khoản, tenant, kênh truy cập và thành phần có thẩm quyền quyết định. Với hệ thống nhiều tenant, “tenant A đã bật policy” không chứng minh tenant B được bảo vệ.

Ví dụ một tuyên bố phạm vi đủ cụ thể:

> Đánh giá luồng recovery tự phục vụ trên web và luồng helpdesk của tài khoản khách hàng thuộc tenant thử nghiệm T-A, release minh họa R-42. IdP bên ngoài được đánh giá theo phần trách nhiệm chia sẻ; tài khoản nhân viên và ứng dụng di động nằm ngoài mẫu thử này.

Đây là phạm vi minh họa, không phải bằng chứng một cuộc đánh giá thực tế đã diễn ra. Khi dùng trong công việc, thay bằng dữ liệu thật và ghi riêng phần chưa được kiểm tra.

## 4. Chọn nguồn và quản lý phiên bản yêu cầu

### 4.1. Các loại nguồn có vai trò khác nhau

| Loại nguồn | Cách sử dụng trong mapping | Điều cần tránh |
| --- | --- | --- |
| Quy định pháp luật có áp dụng | Xác định nghĩa vụ cùng điều kiện áp dụng | Suy nghĩa vụ cụ thể chỉ từ tên một điều luật |
| Tiêu chuẩn hoặc khung đánh giá được lựa chọn | Lấy yêu cầu đúng phiên bản và phạm vi cam kết | Gắn nhãn đáp ứng toàn bộ tiêu chuẩn từ vài kiểm soát |
| Hướng dẫn kỹ thuật | Hỗ trợ thiết kế, test và phân tích khoảng trống | Gọi mọi khuyến nghị là nghĩa vụ pháp lý |
| Hợp đồng và cam kết khách hàng | Xác định yêu cầu bổ sung cho dịch vụ hoặc tenant | Áp dụng một điều khoản của khách hàng này cho mọi khách hàng |
| Policy nội bộ | Ghi quyết định của tổ chức và người phê duyệt | Gán ngược quyết định nội bộ thành yêu cầu nguyên văn của tiêu chuẩn |

Một yêu cầu “thu hồi mọi session cũ sau recovery nghi bị chiếm đoạt” có thể là policy nội bộ phù hợp với rủi ro của sản phẩm. Khi nguồn chỉ yêu cầu cung cấp một lựa chọn thu hồi, không ghi rằng nguồn bắt buộc tự động thu hồi trong mọi trường hợp.

### 4.2. Một số điểm tham chiếu đã đối chiếu

Các điểm sau được đối chiếu ngày 24/11/2026. Phần diễn giải phục vụ bài học; khi lập hồ sơ chính thức cần đọc điều kiện và thuật ngữ của nguồn.

**NIST SP 800-63B-4:** mục 4.2 phân biệt recovery với thay authenticator khi vẫn còn khả năng xác thực. Mục 4.2.2 quy định điều kiện theo IAL/AAL; mục 4.2.3 đề cập thông báo recovery. Không suy “có email OTP” là đủ cho mọi mức bảo đảm. Xem [NIST — Authenticator Event Management](https://pages.nist.gov/800-63-4/sp800-63b/events/) và [bản công bố SP 800-63B-4](https://csrc.nist.gov/pubs/sp/800/63/B/4/final).

**OWASP ASVS 5.0.0:** `6.4.3` liên quan reset mật khẩu không vượt qua MFA; `6.4.4` liên quan mức bằng chứng danh tính khi mất yếu tố MFA; `6.4.6` giới hạn khả năng quản trị viên chọn mật khẩu người dùng. `6.3.7` liên quan thông báo thay đổi thông tin xác thực. Đây là các điểm tham chiếu, không phải toàn bộ yêu cầu của chương. Xem [ASVS 5.0.0 — Authentication](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x15-V6-Authentication.md).

**OWASP ASVS 5.0.0 về session:** `7.4.3` yêu cầu cung cấp lựa chọn kết thúc các session khác sau thay đổi hoặc loại bỏ yếu tố xác thực; `7.5.1` liên quan tái xác thực trước thay đổi thuộc tính nhạy cảm ảnh hưởng đến recovery. Xem [ASVS 5.0.0 — Session Management](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x16-V7-Session-Management.md).

**OWASP Forgot Password Cheat Sheet:** gợi ý phản hồi tránh tiết lộ tài khoản, chống yêu cầu tự động quá mức và token ngẫu nhiên, hết hạn, dùng một lần. Tài liệu này tập trung vào reset mật khẩu. Xem [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

**GDPR, khi thuộc phạm vi áp dụng:** Điều 5 liên quan nguyên tắc xử lý dữ liệu, gồm tối thiểu hóa và giới hạn lưu trữ; Điều 25 liên quan bảo vệ dữ liệu theo thiết kế và mặc định; Điều 32 liên quan an toàn xử lý phù hợp rủi ro và đánh giá hiệu quả biện pháp. Các điều này không tự quy định một TTL recovery token hoặc một thời hạn log cố định cho mọi hệ thống. Xem [Regulation (EU) 2016/679 trên EUR-Lex](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng).

### 4.3. Lưu provenance của từng yêu cầu

Một bản ghi nguồn nên có tên tài liệu, phiên bản, mã hoặc mục yêu cầu, URL, ngày đối chiếu, phần diễn giải nội bộ và người chịu trách nhiệm xác nhận tính áp dụng. Liên kết vào nhánh `master` của một kho mã có thể thay đổi nội dung theo thời gian; với hồ sơ dùng phiên bản ASVS 5.0.0, liên kết tag `v5.0.0` giúp giữ đúng ngữ cảnh.

Nếu hai nguồn dùng thuật ngữ hoặc điều kiện khác nhau, giữ hai yêu cầu độc lập và phân tích quan hệ. Không ghép một câu từ nguồn thứ nhất với ngưỡng của nguồn thứ hai rồi trình bày thành một yêu cầu thống nhất.

## 5. Quy trình xây dựng mapping theo rủi ro

### Bước 1 — Mô tả kịch bản gây hại

Viết thành hành động có thể quan sát: “Một người đã chiếm hộp thư yêu cầu reset password, sau đó dùng quyền vừa nhận để thay MFA của nạn nhân”. Câu này chỉ rõ tài sản bị đe dọa, quyền mà đối phương đã có và quyền họ muốn đạt được.

Không dùng “recovery không an toàn” làm kịch bản duy nhất. Nó quá rộng để quyết định test hoặc chọn bằng chứng.

### Bước 2 — Viết mục tiêu kiểm soát thành một bất biến

Ví dụ: “Grant được cấp cho reset password không được phép dùng cho thao tác thay MFA hoặc gắn passkey”. Đây là mệnh đề có thể kiểm tra ở backend, không phụ thuộc nhãn nút trên giao diện.

Một mục tiêu tốt có chủ thể, hành động, điều kiện và kết quả cần ngăn hoặc duy trì. Các từ “an toàn”, “mạnh”, “phù hợp” cần được cụ thể hóa trong policy hoặc tiêu chí đánh giá.

### Bước 3 — Xác định mọi điểm thực thi

Liệt kê endpoint web, endpoint mobile, admin console, helpdesk tool, tác vụ nền và lời gọi từ đối tác có thể tạo cùng tác động. Nếu giao diện khách hàng chặn thay MFA nhưng công cụ hỗ trợ vẫn cho phép làm trực tiếp, mục tiêu chưa được bao phủ đầy đủ.

### Bước 4 — Chọn kiểm thử có khả năng bác bỏ tuyên bố

Thử grant sai purpose, tài khoản khác, tenant khác, proof hết hạn, replay, request đồng thời và thao tác từ nhân viên không đủ quyền. Một bài test chỉ xác nhận trường hợp hợp lệ thường chưa đủ để chứng minh ranh giới thẩm quyền.

### Bước 5 — Gắn kết quả với cấu hình và bản phát hành

Một báo cáo test không cho biết commit, policy, feature flag và môi trường không giúp xác định hệ thống triển khai có giống hệ thống đã kiểm thử hay không. Gắn bằng chứng với phiên bản; ghi lại thay đổi nào làm kết quả cũ cần đánh giá lại.

### Bước 6 — Kết luận theo phần được quan sát

Nếu mới có bằng chứng thiết kế, ghi “thiết kế đã được rà soát”. Nếu test tích hợp đã chạy nhưng chưa có dữ liệu vận hành, ghi rõ giới hạn đó. Không nâng trạng thái lên “hiệu quả trong vận hành” chỉ vì mã nguồn đã được merge.

## 6. Danh mục kiểm soát recovery nội bộ minh họa

Các mã `RC-*` dưới đây do bài học đặt để tổ chức ma trận. Chúng không phải mã chính thức của NIST, OWASP hoặc pháp luật. Các cơ chế và bài test là đề xuất kỹ thuật cần điều chỉnh theo threat model và phạm vi sản phẩm.

| Mã | Mục tiêu kiểm soát | Điểm thực thi cần xác định | Bằng chứng và phép thử chủ yếu |
| --- | --- | --- | --- |
| RC-01 | Chỉ chủ thể đáp ứng policy mới nhận quyền khôi phục | Policy engine, dịch vụ xác minh, helpdesk | Policy có phiên bản; test proof thiếu, sai, cũ và không phù hợp loại tài khoản |
| RC-02 | Mỗi proof hoặc grant chỉ được dùng đúng ngữ cảnh được cấp | Kho token, backend recovery, endpoint tiêu thụ | Ràng buộc account/tenant/purpose; test dùng chéo ngữ cảnh |
| RC-03 | Quyền dùng một lần không tạo nhiều thay đổi có hiệu lực | Transaction, cơ chế chống replay, workflow state | Test replay tuần tự và đồng thời; quan sát trạng thái bền vững |
| RC-04 | Reset một yếu tố không tự cho quyền thay yếu tố khác | Endpoint mật khẩu, MFA, passkey và admin | Test các đường vượt qua policy, kể cả công cụ hỗ trợ |
| RC-05 | Hạn chế đoán mã, enumeration và quấy rối qua recovery | API public, bộ giới hạn, hàng đợi gửi tin | Kiểm tra phản hồi, giới hạn nhiều chiều và thử tải trên tài khoản thử nghiệm |
| RC-06 | Thay đổi recovery có thể được phát hiện và phản ứng | Notification service, kênh liên hệ, luồng báo gian lận | Bản ghi gửi tin, xử lý lỗi, test đường khiếu nại |
| RC-07 | Session và token cũ được xử lý đúng policy sau recovery | Session store, refresh token service, API gateway, IdP | Test từng loại session và service với credential hoặc token cũ |
| RC-08 | Recovery thủ công có quyền hạn và quyết định truy vết được | Helpdesk, IAM, approval service | Danh sách quyền, log phê duyệt, test người không đủ quyền và tự phê duyệt |
| RC-09 | Bằng chứng danh tính và log có phạm vi dữ liệu được kiểm soát | Evidence store, pipeline log, công cụ quan sát | Danh mục trường dữ liệu, quyền đọc, test redaction và xóa theo policy |
| RC-10 | Recovery không vượt ranh giới tenant | Backend phân quyền, truy vấn DB, callback provider | Test cùng email khác tenant, ID bị tráo và callback bị gắn sai tenant |
| RC-11 | Phụ thuộc lỗi không biến thành nhánh recovery yếu hơn | Workflow, provider adapter, circuit breaker | Fault injection; test timeout, retry, callback trễ và hành vi dừng an toàn |
| RC-12 | Thay đổi policy không làm mapping cũ tiếp tục được coi là hợp lệ | Change management, CI, control registry | Lịch sử phiên bản; danh sách kiểm soát và bằng chứng bị ảnh hưởng |

Ma trận này cố ý tách RC-02 và RC-03: một token có thể đúng account và purpose nhưng vẫn bị tiêu thụ hai lần do race condition. Tách RC-06 và RC-07 cũng cần thiết: gửi email cảnh báo không làm session của đối phương mất hiệu lực.

## 7. Ánh xạ nguồn tới kiểm soát: ghi quan hệ và giới hạn

Một hàng mapping cần giải thích **vì sao** kiểm soát liên quan đến yêu cầu. Chỉ đặt tên framework vào một cột không đủ.

| Điểm tham chiếu nguồn | Kiểm soát nội bộ liên quan | Quan hệ được đề xuất | Phần còn cần đánh giá |
| --- | --- | --- | --- |
| NIST SP 800-63B-4, mục 4.2.2 | RC-01, RC-04 | Hỗ trợ xem xét policy recovery theo mức bảo đảm đã xác định | Phải xác định IAL/AAL và điều kiện của đúng tài khoản; chưa thể kết luận từ tên phương thức |
| NIST SP 800-63B-4, mục 4.2.3 | RC-06 | Hỗ trợ kiểm tra thông báo trong luồng recovery | Phải đánh giá cả tình huống kênh liên hệ hoặc provider có vấn đề |
| ASVS 5.0.0, 6.4.3 | RC-02, RC-04 | Kiểm tra ranh giới quyền giữa reset mật khẩu và MFA | Cần đủ các kênh thay đổi, gồm công cụ hỗ trợ |
| ASVS 5.0.0, 6.4.6 | RC-08 | Kiểm tra giới hạn chức năng hỗ trợ reset | Cần kiểm tra quyền thực tế và mọi đường chọn mật khẩu thay người dùng |
| ASVS 5.0.0, 7.4.3 | RC-07 | Kiểm tra khả năng thu hồi session theo yêu cầu nguồn | Policy tự động thu hồi là quyết định riêng nếu tổ chức lựa chọn |
| GDPR, Điều 5, 25, 32 khi áp dụng | RC-09 cùng các kiểm soát bảo vệ liên quan | Đóng góp bằng chứng cho đánh giá xử lý dữ liệu recovery | Chưa bao phủ toàn bộ nghĩa vụ về dữ liệu cá nhân của dịch vụ |

Đây là các **quan hệ đề xuất**, không phải bảng tuyên bố tuân thủ. Những điểm tham chiếu nguồn và liên kết hỗ trợ được nêu ở mục 4.2. Đánh giá thực tế cần xác nhận từng quan hệ trong phạm vi đã chốt.

Có thể dùng các giá trị quan hệ nội bộ như:

- `supports`: kiểm soát đóng góp vào yêu cầu, chưa khẳng định bao phủ toàn bộ.
- `direct`: có tiêu chí cụ thể tương ứng với yêu cầu, vẫn cần bằng chứng đáp ứng.
- `partial`: chỉ bao phủ một phần hoặc một tập luồng.
- `inherited`: dựa trên thành phần khác, cần bằng chứng về trách nhiệm và cấu hình.

Không dùng `equivalent` chỉ vì hai nguồn cùng đề cập recovery. Tương đương đòi hỏi so sánh điều kiện, đối tượng, mức bảo đảm và kết quả bảo vệ, không chỉ so sánh từ khóa.

## 8. Đi sâu một kiểm soát: quyền recovery chỉ được tiêu thụ một lần

### 8.1. Tuyên bố kiểm soát có thể kiểm thử

Với RC-03, một mục tiêu nội bộ có thể là:

> Trong cùng một recovery transaction, mỗi grant hợp lệ chỉ cho phép một lần chuyển trạng thái có hiệu lực theo purpose đã cấp. Request lặp hoặc đồng thời không tạo thêm credential, thêm tác động quyền hạn hoặc thêm lần hoàn tất recovery.

Định nghĩa “một lần” phải gắn với tác động nghiệp vụ. Nếu hai request cùng trả `200` vì cơ chế idempotency trả lại kết quả cũ nhưng chỉ một lần thay đổi bền vững được tạo ra, đó không nhất thiết là lỗi replay. Ngược lại, một request trả lỗi sau khi đã tạo credential có thể che giấu tác động thứ hai.

### 8.2. Điểm thực thi và trạng thái

Một mô hình trạng thái đơn giản dùng cho thảo luận:

```text
ISSUED → VERIFIED → CONSUMED
   │         │
   ├─────────┴──→ EXPIRED
   └────────────→ REVOKED
```

Chuyển trạng thái cần được kiểm soát tại backend có thẩm quyền. Client không được tự khai `verified=true` để có quyền chuyển tiếp. Thời điểm hết hạn phải được kiểm tra khi thực hiện hành động có hiệu lực, không chỉ khi mở trang nhập mật khẩu.

Trong một cơ sở dữ liệu, có thể dùng conditional update hoặc cơ chế transaction phù hợp để chỉ một tiến trình nhận quyền thực hiện thay đổi. Điều kiện phải bao gồm ngữ cảnh cần bảo vệ và trạng thái chưa tiêu thụ. Số bản ghi được cập nhật là một tín hiệu để xác định request nào thực sự có quyền tiếp tục.

Nếu credential nằm ở dịch vụ khác, không nên hứa rằng một transaction database cục bộ đã làm toàn bộ chuỗi trở nên nguyên tử. Cần thiết kế giao thức idempotency, lưu dấu quyết định bền vững, xử lý retry và trạng thái trung gian. Nếu dùng outbox cho thông báo, phân biệt “ý định gửi đã được lưu” với “người nhận đã nhận tin”.

### 8.3. Bộ bằng chứng cho RC-03

| Bằng chứng | Điều nó giúp xác nhận | Điều nó chưa chứng minh |
| --- | --- | --- |
| Tài liệu bất biến và state machine | Nhóm có định nghĩa rõ hành vi mong muốn | Backend thực thi đúng |
| Review điểm tiêu thụ grant | Mã có cơ chế kiểm tra và tranh chấp trạng thái | Mọi deployment đang dùng đúng cấu hình |
| Test replay tuần tự | Grant cũ không tạo tác động tiếp theo trong trường hợp đã thử | Không có race giữa nhiều worker xử lý |
| Test đồng thời | Hành vi khi nhiều request tranh cùng một grant | Mọi điều kiện lỗi phân tán đều đã được kiểm tra |
| Test crash và retry | Khả năng phục hồi sau các điểm lỗi đã chọn | Provider bên ngoài không có lỗi hoặc luôn đúng |
| Mẫu sự kiện đã che dữ liệu | Khả năng theo dõi transaction và kết quả | Mẫu đó đại diện cho toàn bộ khoảng thời gian vận hành |

Một test có giá trị nên kiểm tra số thay đổi credential, số lần chuyển trạng thái và quyền có được sau thao tác. Chỉ kiểm tra mã HTTP sẽ bỏ sót side effect.

## 9. Mẫu control record để nhóm dùng nội bộ

YAML sau minh họa một hồ sơ kiểm soát độc lập. Nó không phải schema của file thông tin bài học và không phải cấu hình triển khai recovery. Các giá trị đều là dữ liệu mẫu; trạng thái cố ý để chưa được đánh giá.

```yaml
controlId: RC-04
title: Password reset cannot authorize MFA replacement
scope:
  service: SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY
  flows:
    - self-service-password-reset
    - helpdesk-password-reset
  accountClasses:
    - customer
  tenantCoverage: not-yet-assessed

objective: >-
  A password-reset grant cannot authorize removal or replacement
  of an MFA factor or registration of a new passkey.

sourceMappings:
  - source: OWASP ASVS
    version: 5.0.0
    requirement: "6.4.3"
    relation: supports
    sourceUrl: https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x15-V6-Authentication.md

implementation:
  enforcementOwner: identity-platform
  points:
    - password-reset-consumer
    - mfa-management-authorization
    - helpdesk-recovery-authorization
  policyVersion: pending-selection

verificationPlan:
  - reject-password-grant-at-mfa-endpoint
  - reject-password-grant-at-passkey-enrollment
  - verify-helpdesk-has-no-direct-mfa-bypass
  - verify-current-mfa-remains-after-password-reset

evidence:
  designReview: null
  deploymentSnapshot: null
  testReport: null
  operatingSample: null

assessment:
  implementationState: unknown
  designAssessment: not-assessed
  operatingAssessment: not-assessed
  openGaps: []
  assessedRelease: null
  assessor: null
  assessedAt: null
```

`null` ở phần bằng chứng thể hiện chưa có bằng chứng. Nó tốt hơn một đường dẫn giả trông như báo cáo đã tồn tại. Việc ghi tên các bài test vào `verificationPlan` không có nghĩa các bài test đã được triển khai hoặc đã chạy thành công.

`relation: supports` cũng không phải kết luận đáp ứng. Khi có đủ bằng chứng, hồ sơ vẫn cần ghi rõ kết luận, phạm vi và người đánh giá. Nếu helpdesk chưa được kiểm tra, không nâng kết luận của cả kiểm soát chỉ từ test self-service.

## 10. Phân biệt thiết kế, triển khai và hiệu quả vận hành

Một mô hình theo dõi nội bộ có thể sử dụng ba trục độc lập:

| Trục | Ví dụ giá trị | Ý nghĩa |
| --- | --- | --- |
| Trạng thái triển khai | Chưa triển khai / một phần / đã triển khai | Cơ chế đã có ở những điểm nào |
| Đánh giá thiết kế | Chưa đánh giá / phù hợp / còn khoảng trống | Thiết kế có khả năng đạt mục tiêu trong phạm vi đã chọn không |
| Đánh giá vận hành | Chưa đánh giá / có bằng chứng hỗ trợ / thất bại | Dữ liệu quan sát nói gì về cách cơ chế hoạt động thực tế |

Ví dụ, notification service đã triển khai và test tích hợp thành công. Tuy nhiên, dữ liệu vận hành cho thấy một tenant đang tắt thông báo do cấu hình cũ. Trục triển khai có thể ghi “đã triển khai”, nhưng kết luận vận hành của phạm vi gồm tenant đó phải phản ánh khoảng trống.

Không đặt một cột `status: PASS` duy nhất cho mọi tầng. Cách này làm người đọc nhầm giữa “có code”, “có test” và “đang bảo vệ đúng trong vận hành”.

### 10.1. Bằng chứng cần có ngữ cảnh

Một evidence record nên chỉ ra:

- Kiểm soát và tiêu chí nào đang được kiểm tra.
- Phiên bản ứng dụng, policy và cấu hình có liên quan.
- Môi trường, tenant hoặc tập mẫu được kiểm tra.
- Thời điểm hoặc khoảng thời gian quan sát.
- Người hoặc hệ thống tạo bằng chứng và người đánh giá.
- Kết quả, ngoại lệ và liên kết tới issue cần xử lý.

Đường dẫn evidence phải có kiểm soát truy cập. Không đưa reset token, OTP, recovery code, session cookie hoặc ảnh giấy tờ vào tệp tổng hợp chỉ để hồ sơ trông đầy đủ. Một bản ghi sự kiện có mã tham chiếu và kết quả thường hữu ích hơn một ảnh chụp chứa bí mật.

### 10.2. Tính toàn vẹn và tính đúng đắn là hai thuộc tính

Checksum giúp nhận ra một tệp đã thay đổi so với bản được ghi nhận. Nó không chứng minh tệp mô tả sự thật, không chứng minh cách lấy mẫu hợp lý và không tự chứng minh ai tạo ra tệp. Bằng chứng vẫn cần provenance, quyền truy cập, phương pháp thu thập và mối liên hệ với hệ thống được đánh giá.

Tương tự, log không sửa được vẫn có thể ghi thiếu một đường recovery. Khả năng bảo vệ log và độ bao phủ log là hai câu hỏi cần trả lời riêng.

## 11. Kiểm thử âm, lỗi và trách nhiệm chia sẻ

### 11.1. Ma trận test theo đường đi

| Tình huống thử nghiệm | Kiểm soát liên quan | Quan sát cần có |
| --- | --- | --- |
| Dùng password-reset grant để thay MFA | RC-02, RC-04 | Backend từ chối; MFA hiện tại còn nguyên; không tạo grant mạnh hơn |
| Gửi đồng thời hai request dùng cùng grant | RC-03 | Một tác động có hiệu lực theo định nghĩa policy; không xuất hiện credential bổ sung |
| Tráo tenant trong request hoặc callback | RC-02, RC-10 | Không đọc hoặc thay đổi tài khoản ở tenant khác |
| Giới hạn yêu cầu bị thử từ nhiều IP | RC-05 | Đánh giá được giới hạn theo account hoặc transaction và ảnh hưởng lên người dùng hợp lệ |
| Email provider timeout sau khi đã nhận yêu cầu | RC-06, RC-11 | Retry có kiểm soát; phân biệt chưa rõ kết quả gửi với chắc chắn chưa gửi |
| Dịch vụ đánh giá rủi ro không trả kết quả | RC-01, RC-11 | Hành vi đúng policy lỗi; không tự cấp quyền từ việc thiếu kết quả |
| Helpdesk thao tác ngoài phạm vi quyền | RC-08 | Từ chối tại backend và ghi được lý do quyết định |
| Session cũ gọi API sau mốc thu hồi | RC-07 | Quan sát tại từng thành phần đúng thời hạn hiệu lực đã cam kết |
| Dữ liệu xác minh tới hạn xóa theo policy | RC-09 | Xử lý được đối tượng đến hạn và giải thích đối tượng được giữ theo ngoại lệ hợp lệ |

Các test cần dùng tài khoản và dữ liệu thử nghiệm được phép. Với giới hạn chống lạm dụng, kiểm tra cả khả năng đối phương gây từ chối dịch vụ bằng cách cố ý làm tài khoản nạn nhân chạm ngưỡng. Một giới hạn quá dễ kích hoạt có thể tạo thêm rủi ro khóa người dùng ra ngoài.

### 11.2. Kiểm soát kế thừa từ nhà cung cấp

Khi IdP thực hiện recovery, ứng dụng vẫn phải biết kết quả đó cho phép làm gì tại hệ thống của mình. Bằng chứng từ nhà cung cấp có thể đóng góp cho phần do họ thực thi, nhưng cần kiểm tra cấu hình tenant, phạm vi dịch vụ và phần tích hợp của ứng dụng.

Ví dụ phân chia trách nhiệm:

| Thành phần | Trách nhiệm cần ghi | Bằng chứng phù hợp |
| --- | --- | --- |
| IdP | Quy trình xác minh và quản lý authenticator trong dịch vụ của IdP | Tài liệu cấu hình tenant, tài liệu trách nhiệm, bằng chứng đánh giá đúng phạm vi |
| Ứng dụng | Quyền nội bộ được cấp sau sự kiện recovery | Policy phân quyền, integration test và log quyết định |
| Gateway hoặc session service | Áp dụng trạng thái thu hồi đối với token/session | Cấu hình, test gọi lại bằng token cũ, đo khoảng trễ |
| Helpdesk | Thực hiện các bước con người và phê duyệt | Hướng dẫn, phân quyền, mẫu hồ sơ quyết định đã che dữ liệu |

Không ghi `inherited` để làm biến mất một hàng khó đánh giá. Hàng kế thừa cần chỉ rõ ai cung cấp bằng chứng và phần nào nhóm triển khai vẫn phải kiểm tra.

### 11.3. Thu hồi session trong hệ thống phân tán

Recovery có thể thay đổi mật khẩu ở một dịch vụ, vô hiệu refresh token ở dịch vụ khác và để access token đã phát hành còn hiệu lực ở gateway. Ma trận cần ghi từng loại token, nơi kiểm tra và độ trễ thu hồi được chấp nhận.

Policy nội bộ có thể định nghĩa một mốc hoặc cửa sổ áp dụng cụ thể. Khi đó kiểm thử phải đo hành vi từ mốc đó ở từng nơi, bao gồm cache và IdP nếu nằm trong phạm vi. Không coi “đã xóa session ở database” là đủ để kết luận mọi lời gọi API đều bị chặn.

## 12. Ánh xạ dữ liệu cá nhân mà không mở rộng thu thập vô hạn

Recovery có thể xử lý địa chỉ liên hệ, tín hiệu thiết bị, địa chỉ IP, tài liệu chứng minh danh tính và quyết định của nhân viên hỗ trợ. Danh mục dữ liệu phải nối từng nhóm dữ liệu với mục đích, quyền truy cập và quy tắc lưu giữ.

Một mẫu phân tích kỹ thuật nội bộ:

| Nhóm dữ liệu | Mục đích cần xác định | Cách giảm rủi ro cần xem xét |
| --- | --- | --- |
| Định danh account và tenant | Gắn quyết định với đúng chủ thể | Dùng mã nội bộ phù hợp; phân quyền truy vấn |
| OTP, reset token, recovery code | Chứng minh quyền thực hiện một bước | Bảo vệ trong truyền và lưu trữ; tránh xuất hiện trong log hoặc công cụ phân tích |
| Tài liệu hoặc dữ liệu xác minh | Hỗ trợ quyết định danh tính trong luồng được phép | Tách kho chứng cứ, giới hạn người đọc, xác định quy tắc xóa |
| Tín hiệu rủi ro | Phân tích bất thường và chống lạm dụng | Chỉ thu trường cần thiết; ghi mục đích và giới hạn sử dụng |
| Nhật ký quyết định | Truy vết tác động và điều tra | Ghi policy, loại kết quả, mã lý do; hạn chế sao chép dữ liệu gốc |

Đây là đề xuất quản trị dữ liệu cho bài toán recovery. Khi ánh xạ tới pháp luật, cần xác định phạm vi pháp lý, cơ sở xử lý và yêu cầu thực tế của tổ chức; không suy ra chúng chỉ từ bảng kỹ thuật này.

Thời hạn lưu dữ liệu xác minh có thể khác thời hạn lưu dấu quyết định đã che dữ liệu. Đừng dùng một thời hạn cho mọi loại dữ liệu chỉ vì chúng cùng được tạo ra trong một recovery transaction. Nếu có ngoại lệ lưu giữ, ghi căn cứ, người phê duyệt, phạm vi và cơ chế xem xét lại thay vì giữ vô thời hạn bằng một cờ không ai quản lý.

Sự kiện recovery, sự cố an toàn và vi phạm dữ liệu cũng cần phân loại riêng. Một lần người dùng quên mật khẩu không tự chứng minh đã có vi phạm dữ liệu; quy trình sự cố phải đánh giá dấu hiệu thực tế và nghĩa vụ tương ứng nếu phát sinh.

## 13. Quản lý khoảng trống và ngoại lệ

Khi một kiểm soát thiếu hoặc thất bại, bản ghi gap nên mô tả hành vi quan sát được, luồng bị ảnh hưởng, tác động, owner, kế hoạch xử lý và điều kiện kiểm thử lại. “Cần cải thiện recovery” không đủ để giao việc hoặc xác nhận đã khắc phục.

Ví dụ một gap minh họa:

```text
GAP: GAP-RC-07-EXAMPLE
Control: RC-07
Observation: Refresh token cũ bị chặn nhưng access token cũ vẫn được
             một service chấp nhận quá cửa sổ thu hồi của policy mẫu.
Scope: Luồng recovery sau nghi bị chiếm đoạt trong môi trường thử nghiệm.
Impact: Chủ thể đã có access token có thể tiếp tục gọi service đó.
Owner: Session platform cùng owner của service bị ảnh hưởng.
Remediation: Sửa cơ chế kiểm tra trạng thái thu hồi và cấu hình cache.
Retest: Thử token cũ ở mọi điểm kiểm tra trong phạm vi đã nêu.
Assessment: Open; chưa thể kết luận kiểm soát vận hành hiệu quả.
```

Nếu tổ chức chấp nhận rủi ro tạm thời, hồ sơ cần thể hiện người có thẩm quyền, lý do, thời hạn, điều kiện dừng và biện pháp bù. Việc chấp nhận rủi ro nội bộ không tự miễn trừ nghĩa vụ pháp lý hoặc nghĩa vụ hợp đồng đang áp dụng.

Một biện pháp bù phải được đánh giá theo rủi ro thực tế. Chẳng hạn, tăng giám sát có thể giúp phát hiện sớm nhưng không ngăn một thao tác thay MFA đã được cấp sai quyền. Không mô tả biện pháp phát hiện như thể nó có cùng tác dụng với một ranh giới phân quyền.

Không để ngoại lệ tự biến thành policy lâu dài. Khi đến hạn hoặc khi giả định nền thay đổi, phải đánh giá lại. Trạng thái `not applicable` cũng cần căn cứ: một luồng không tồn tại trong sản phẩm khác với một luồng tồn tại nhưng nhóm chưa muốn kiểm tra.

## 14. Giữ mapping đồng bộ với thay đổi hệ thống

Những thay đổi sau có thể làm bằng chứng cũ không còn đủ:

- Thêm kênh recovery mobile hoặc API đối tác.
- Cho phép helpdesk thực hiện một hành động trước đây chỉ người dùng tự làm.
- Thay đổi cách xác minh, loại grant hoặc điều kiện MFA.
- Thêm IdP, thay provider thông báo hoặc thay cơ chế retry.
- Thay cache, gateway hoặc cách thu hồi token.
- Tách tenant, thay mô hình định danh hoặc thêm loại tài khoản đặc quyền.
- Đổi quy tắc lưu dữ liệu hoặc quyền đọc kho evidence.

Một change request nên liên kết đến các `controlId` bị ảnh hưởng. Nếu chưa xác định tác động, ghi yêu cầu phân tích thay vì tự đánh dấu “không ảnh hưởng tuân thủ”.

Tự động hóa có thể giúp phát hiện control thiếu owner, source thiếu version, đường dẫn bằng chứng hỏng hoặc một flow chưa được liệt kê. Những kiểm tra cấu trúc này không đánh giá được bằng chứng có đủ sức chứng minh mục tiêu hay không. Người đánh giá vẫn phải đọc kết quả và xem các nhánh bị bỏ sót.

Tần suất rà soát định kỳ là quyết định dựa trên rủi ro và nghĩa vụ áp dụng của tổ chức. Không lấy một con số tùy ý trong ví dụ rồi gọi nó là chu kỳ bắt buộc của mọi framework. Ngoài lịch định kỳ, thay đổi lớn hoặc sự cố phải là tín hiệu xem xét lại các mapping liên quan.

## 15. Tình huống thực hành: bảng đều xanh nhưng helpdesk vẫn vượt policy

Giả sử một sản phẩm có web recovery, ứng dụng di động và helpdesk. Nhóm chỉ kiểm thử web. Email reset cho phép đặt mật khẩu mới, MFA không bị tắt và token chỉ tiêu thụ một lần. Ma trận đánh dấu RC-02, RC-03 và RC-04 đã đáp ứng cho toàn sản phẩm.

Trong một buổi kiểm tra, nhóm phát hiện công cụ helpdesk có chức năng “reset all authentication”. Một vai trò hỗ trợ có thể dùng chức năng này sau khi đánh dấu một ticket đã xử lý; backend không kiểm tra policy xác minh tương ứng. Sau thao tác, người gọi có thể đăng ký MFA mới.

### 15.1. Kết luận nào cần sửa?

RC-04 chưa được chứng minh cho phạm vi toàn sản phẩm. Bằng chứng web vẫn có giá trị trong phạm vi web, nhưng không bao phủ helpdesk. RC-08 cũng có khoảng trống về thẩm quyền và quyết định. Nếu helpdesk thao tác qua tenant không phù hợp, cần đánh giá thêm RC-10; không tự kết luận có lỗi tenant khi chưa thử.

Đây là lỗi về độ bao phủ mapping và có thể kèm lỗi triển khai. Đổi màu một ô trong bảng chỉ sửa hồ sơ; thay đổi quyền và cơ chế backend mới xử lý nguyên nhân kỹ thuật.

### 15.2. Cách xử lý có thể kiểm chứng

1. Ghi chính xác thao tác, quyền và điều kiện đã quan sát trong môi trường được phép.
2. Khoanh phạm vi các vai trò, tenant và phiên bản có thể bị ảnh hưởng.
3. Xác định quyền hợp lệ mà helpdesk thực sự cần; sửa điểm thực thi backend theo policy đã được phê duyệt.
4. Kiểm thử người không đủ quyền, proof thiếu, thao tác chéo purpose và nhánh phê duyệt nếu có.
5. Kiểm tra tác động tới MFA hiện tại, authenticator bị mất và session theo policy của luồng.
6. Cập nhật bằng chứng và kết luận cho cả web, mobile và helpdesk; phần chưa kiểm tra phải được ghi rõ.

Mục tiêu không phải làm tất cả hàng trở lại màu xanh nhanh nhất. Mục tiêu là mỗi kết luận phản ánh đúng hành vi đã được xác minh trong phạm vi công bố.

## 16. Những lỗi mapping dễ tạo cảm giác an toàn sai

| Lỗi | Vì sao kết luận không đứng vững | Cách sửa |
| --- | --- | --- |
| Ghi tên tiêu chuẩn mà không có phiên bản hoặc mục yêu cầu | Không biết nhóm đã đánh giá điều gì | Ghi nguồn, version, requirement và điều kiện áp dụng |
| Một test happy path đại diện mọi luồng | Không thử ranh giới quyền hoặc đường thay thế | Bổ sung test âm và inventory đường recovery |
| Có cấu hình provider nên coi kiểm soát đã hiệu quả | Cấu hình có thể sai tenant hoặc không được thực thi | Đối chiếu deployment và quan sát hành vi |
| Token ký hợp lệ nên được coi là chống replay | Chữ ký không tự giới hạn số lần tiêu thụ | Kiểm tra trạng thái, ngữ cảnh và tranh chấp đồng thời |
| Đã gửi cảnh báo nên coi tài khoản đã được bảo vệ | Phát hiện không tự thu hồi quyền của đối phương | Đánh giá riêng notification, phản ứng và session |
| Vendor có báo cáo nên toàn bộ phần tích hợp được kế thừa | Báo cáo không tự bao phủ cấu hình và code của ứng dụng | Lập trách nhiệm chia sẻ và kiểm tra phần do mình thực thi |
| Thu càng nhiều giấy tờ càng dễ chứng minh tuân thủ | Tăng dữ liệu nhạy cảm và trách nhiệm quản lý | Chốt mục đích, tính cần thiết và bằng chứng quyết định |
| Không có evidence nên ghi not applicable | Nhầm thiếu bằng chứng với không áp dụng | Ghi chưa đánh giá hoặc gap cùng căn cứ |
| Tất cả hàng được gán cùng ngày hết hiệu lực | Che mất sự khác nhau giữa thay đổi và phạm vi bằng chứng | Xác định điều kiện cần đánh giá lại cho từng loại kiểm soát |

## 17. Câu hỏi tự kiểm tra

**Câu 1:** Reset password qua web đạt mọi test đã chọn. Helpdesk chưa được kiểm tra. Có thể kết luận RC-04 đáp ứng cho toàn sản phẩm không?

Không. Có thể kết luận giới hạn ở luồng web, release và điều kiện đã kiểm tra. Helpdesk là phần phạm vi còn thiếu bằng chứng; cần đánh giá trước khi mở rộng kết luận.

**Câu 2:** Một yêu cầu nguồn nói về khả năng kết thúc session; tổ chức chọn tự động thu hồi mọi session trong recovery nghi bị chiếm đoạt. Mapping cần ghi thế nào?

Giữ nguyên ý nghĩa và điều kiện của yêu cầu nguồn; ghi policy tự động thu hồi là quyết định nội bộ riêng. Kiểm thử cả khả năng được nguồn đề cập và hành vi bổ sung mà tổ chức đã cam kết, không biến phần bổ sung thành trích dẫn của nguồn.

**Câu 3:** Hai request dùng cùng một grant đều trả thành công. Đây có chắc chắn là lỗi dùng lại không?

Chưa đủ dữ liệu. Cần xem chúng có tạo hai tác động có hiệu lực hay chỉ trả lại cùng một kết quả idempotent. Đánh giá dựa trên bất biến nghiệp vụ, trạng thái bền vững và quyền được cấp.

**Câu 4:** File test report có checksum và được lưu ở nơi chỉ đọc. Điều đó chứng minh kiểm soát hiệu quả trong vận hành chưa?

Chưa. Nó hỗ trợ kiểm tra tính toàn vẹn của file, nhưng còn cần nguồn gốc, phạm vi, phương pháp thử, cấu hình triển khai và dữ liệu vận hành phù hợp với tuyên bố.

**Câu 5:** Hệ thống có email OTP và kiểm tra tài liệu ở helpdesk. Có thể tự gán một mức bảo đảm NIST cho toàn bộ recovery không?

Không thể suy mức bảo đảm từ tên hai cơ chế. Cần xác định mô hình tài khoản, policy, điều kiện yêu cầu tương ứng và bằng chứng thực thi; phần chưa rõ phải được giữ ở trạng thái chưa đánh giá.

## 18. Sản phẩm đầu ra của một đợt mapping tốt

Một hồ sơ recovery control mapping có thể bàn giao khi người đọc nhận diện được phạm vi, nguồn yêu cầu, danh mục đường recovery, rủi ro, kiểm soát, owner, điểm thực thi, kế hoạch test, bằng chứng và kết luận có giới hạn. Các khoảng trống và ngoại lệ phải có trạng thái rõ ràng, không bị ẩn trong ghi chú chung.

Trước khi dùng hồ sơ để hỗ trợ quyết định, kiểm tra những câu hỏi cuối cùng:

- Có đường recovery hoặc công cụ hỗ trợ nào chưa nằm trong inventory không?
- Mỗi kết luận có truy ngược được đến yêu cầu và bằng chứng đúng phiên bản không?
- Test có kiểm tra tác động lên MFA, passkey và session sau recovery không?
- Kiểm soát do vendor thực thi và phần ứng dụng chịu trách nhiệm đã được tách rõ chưa?
- Dữ liệu dùng làm bằng chứng có được bảo vệ và giới hạn theo mục đích không?
- Một thay đổi policy hoặc deployment có làm ai biết cần đánh giá lại hồ sơ không?

Giá trị của mapping nằm ở khả năng giải thích và kiểm chứng từng quyết định bảo vệ tài khoản. Một bảng đẹp chỉ hữu ích khi nó dẫn người đọc tới đúng hành vi, đúng bằng chứng và đúng giới hạn của điều đã được xác nhận.
