# Rate limit authentication

## 1. Giới hạn tốc độ xác thực để làm gì?

**Rate limiting cho authentication** là kiểm soát số lượng hoặc nhịp độ yêu cầu xác thực được xử lý trong một phạm vi nhất định. Phạm vi có thể là tài khoản, nguồn gọi, challenge, ứng dụng hoặc toàn bộ dịch vụ xác thực.

Mục tiêu là hạn chế việc thử credential tự động và bảo vệ tài nguyên của hệ thống. Một lần xác minh mật khẩu có thể tiêu tốn CPU; một lần gửi OTP có thể phát sinh chi phí và gây phiền cho người nhận. Do đó, không chỉ kết quả đăng nhập thất bại mới đáng quan tâm: cả số lần yêu cầu gửi mã, số phép xác minh đồng thời và các luồng phục hồi cũng cần được kiểm soát.

Ví dụ, một API có mật khẩu được lưu an toàn nhưng chấp nhận không giới hạn số lần đoán trực tuyến vẫn tạo cơ hội cho việc thử credential. Ngược lại, khóa tài khoản vĩnh viễn sau một ngưỡng rất thấp có thể cho phép người khác làm chủ tài khoản hợp lệ không đăng nhập được.

Một thiết kế tốt phải cân bằng khả năng chống lạm dụng, độ sẵn sàng và trải nghiệm người dùng. Không có một con số “bao nhiêu lần mỗi phút” phù hợp cho mọi loại authenticator và mọi sản phẩm.

NIST SP 800-63B mô tả rate limiting theo loại authenticator và số lần xác thực thất bại liên tiếp. Cần phân biệt yêu cầu về số lần thất bại đó với giới hạn lưu lượng của một endpoint trong một cửa sổ thời gian. [NIST SP 800-63B — Rate Limiting](https://pages.nist.gov/800-63-4/sp800-63b.html#rate-limiting-throttling).

## 2. Những kiểu lạm dụng cần xem xét

| Kiểu lạm dụng | Đặc điểm | Vì sao một giới hạn đơn lẻ chưa đủ? |
|---|---|---|
| Đoán mật khẩu trực tuyến | Nhiều lần thử với một tài khoản | Chỉ giới hạn theo IP chưa bảo vệ tài khoản khi nguồn gọi thay đổi |
| Credential stuffing | Thử các cặp tài khoản và mật khẩu đã bị lộ từ nơi khác | Mỗi tài khoản có thể chỉ bị thử ít lần, trong khi tổng lưu lượng lớn |
| Password spraying | Thử một số mật khẩu phổ biến trên nhiều tài khoản | Chỉ đếm thất bại của từng tài khoản có thể không thấy mẫu trên nhiều tài khoản |
| Đoán OTP hoặc mã phục hồi | Thử nhiều giá trị trong thời gian mã còn hiệu lực | TTL của mã không tự giới hạn số phép đoán được xử lý |
| Lạm dụng gửi OTP hoặc thông báo MFA | Gửi nhiều yêu cầu tới cùng người nhận | Có thể gây chi phí, quấy rối và làm người dùng dễ chấp thuận nhầm |
| Làm cạn tài nguyên xác thực | Tạo nhiều tác vụ hash hoặc lời gọi tới IdP | Giới hạn sau khi đã xử lý tốn kém không bảo vệ được đầy đủ tài nguyên |

Rate limiting chủ yếu tác động lên những yêu cầu đi qua dịch vụ đang thực thi nó. Nó không giới hạn được số lần thử offline nếu kẻ tấn công đã lấy được dữ liệu hash mật khẩu. Bảo vệ lưu trữ credential vẫn là một kiểm soát riêng.

MFA cũng không thay thế rate limiting. Một luồng có MFA vẫn có thể bị thử mật khẩu, đoán mã hoặc lạm dụng chức năng gửi thông báo nếu thiếu giới hạn thích hợp.

## 3. Phân biệt bốn loại kiểm soát

### Giới hạn số yêu cầu

Giới hạn này đếm yêu cầu được nhận hoặc được phép xử lý trong một khoảng thời gian. Nó hữu ích để bảo vệ endpoint, dịch vụ hash, hệ thống gửi tin và dependency bên ngoài.

Một yêu cầu có credential đúng vẫn có thể tiêu thụ quota lưu lượng. Nếu mọi lần thành công đều hoàn lại toàn bộ quota, một client có credential hợp lệ nhưng gửi quá nhiều yêu cầu vẫn có thể làm cạn tài nguyên.

### Đếm số lần xác thực thất bại

Bộ đếm này phản ánh các lần thử không chứng minh được quyền kiểm soát authenticator hoặc tài khoản theo policy. Nó có thể theo dõi chuỗi thất bại liên tiếp, một cửa sổ thời gian hoặc một challenge cụ thể.

Lỗi kết nối tới dịch vụ xác thực không nhất thiết là bằng chứng người dùng nhập sai. Cần phân biệt thất bại credential với lỗi kỹ thuật để tránh khóa người dùng hàng loạt khi một dependency gặp sự cố.

### Throttling hoặc thời gian chờ

Hệ thống tạm thời không chấp nhận thêm phép thử hoặc tăng thời gian phải chờ trước lần thử tiếp theo. Thời điểm được thử lại phải do máy chủ quyết định, không dựa vào đồng hồ hoặc trạng thái JavaScript trên client.

Không nên giữ một thread xử lý xác thực đang ngủ trong thời gian dài chỉ để tạo độ trễ. Có thể lưu thời điểm được phép tiếp tục và trả phản hồi có kiểm soát, giải phóng tài nguyên đang xử lý.

### Khóa hoặc vô hiệu hóa authenticator

Một ngưỡng thất bại có thể dẫn tới việc tạm khóa một luồng, khóa một tài khoản theo policy hoặc vô hiệu hóa authenticator cần được phục hồi. Đây là quyết định có tác động lớn hơn giới hạn lưu lượng thông thường.

Policy cần chỉ rõ đối tượng bị khóa, điều kiện mở lại và quy trình phục hồi. Khóa một challenge OTP không nhất thiết phải khóa mọi phiên và mọi authenticator của cùng identity.

## 4. Kết hợp nhiều phạm vi giới hạn

Một mô hình thực tế thường dùng nhiều lớp kiểm soát cùng lúc.

| Phạm vi | Mục đích | Điểm cần chú ý |
|---|---|---|
| Nguồn mạng đã xác minh | Hạn chế lưu lượng bất thường từ một nguồn | Nhiều người có thể dùng chung NAT hoặc proxy |
| Định danh tài khoản trong realm hoặc tenant | Bảo vệ một đích khỏi nhiều nguồn thử | Có thể bị lợi dụng để làm người dùng hợp lệ phải chờ |
| Tài khoản và authenticator | Kiểm soát thất bại theo phương thức xác thực | Không gộp sai các phương thức hoặc nguồn identity khác nhau |
| Challenge hoặc giao dịch MFA | Giới hạn số phép thử một mã hoặc một bước | Tạo challenge mới không được xóa mọi giới hạn tổng hợp liên quan |
| Người nhận OTP hoặc thông báo | Chống gửi tin lặp và phát sinh chi phí | Đếm số lần gửi, không chỉ số lần kiểm tra mã |
| Client hoặc ứng dụng tích hợp | Hạn chế một ứng dụng gọi quá mức | Không tin một `clientId` tự khai chưa được kiểm tra |
| Toàn dịch vụ và số tác vụ đồng thời | Bảo vệ năng lực xử lý chung | Cần tránh một nguồn chiếm hết tài nguyên của mọi người khác |

Nếu một yêu cầu phải đáp ứng nhiều quota, hệ thống chỉ được xử lý khi các điều kiện cần thiết đều cho phép. Một IP chưa hết quota không được ghi đè việc challenge đã hết số lần thử.

### Phạm vi identity phải rõ ràng

Tên đăng nhập `minh` có thể xuất hiện trong hai tenant hoặc hai realm độc lập. Khóa giới hạn chỉ chứa chuỗi `minh` có thể làm hoạt động ở tenant này tác động nhầm tenant khác.

Khóa logic có thể được mô tả như:

```text
authentication:realm-an-phu:password:<account-key>
otp-verification:realm-an-phu:<account-key>:<challenge-id>
otp-delivery:realm-an-phu:<recipient-key>
```

Đây là ví dụ tổ chức khóa, không phải định dạng bắt buộc. Tên đăng nhập cần được chuẩn hóa theo quy tắc identity của ứng dụng; không tự áp dụng một quy tắc viết hoa hoặc viết thường cho mọi loại định danh.

Với tài khoản chưa xác thực, hệ thống có thể phải bắt đầu từ định danh được trình bày thay vì một account ID đã xác minh. Cần thiết kế xử lý cả định danh không tồn tại mà không làm lộ danh sách tài khoản hoặc tạo vô hạn khóa lưu trữ.

Có thể dùng một khóa dẫn xuất có bảo vệ để giảm việc lưu trực tiếp email hoặc số điện thoại trong kho limiter. Dù vậy, khóa đó vẫn cần được bảo vệ, giới hạn số lượng và thời gian lưu phù hợp; chuyển dữ liệu thành hash không tự loại bỏ mọi rủi ro về riêng tư.

### Nguồn IP phải được xác định đáng tin cậy

Nếu ứng dụng nằm sau reverse proxy, không đọc tùy ý một header `X-Forwarded-For` do client có thể tự gửi rồi coi đó là nguồn thật. Cần xác định các proxy được tin cậy và xử lý thông tin chuyển tiếp theo cấu hình đó.

IP không phải identity của người dùng. Chặn quá mạnh một IP dùng chung có thể ảnh hưởng cả văn phòng; cho phép một dải mạng nội bộ bỏ qua toàn bộ giới hạn lại có thể mở một đường lạm dụng.

## 5. Các thuật toán phổ biến

| Thuật toán | Ý tưởng | Đặc điểm cần hiểu |
|---|---|---|
| Fixed window | Đếm số yêu cầu trong một khoảng cố định | Đơn giản, nhưng có thể tạo burst ở hai phía ranh giới cửa sổ |
| Sliding window | Xem lượng yêu cầu trong khoảng thời gian gần nhất | Phản ánh lưu lượng liên tục tốt hơn; chi phí và độ chính xác tùy cách triển khai |
| Token bucket | Tích lũy token tới một dung lượng, mỗi yêu cầu tiêu thụ token | Cho phép burst có giới hạn và duy trì tốc độ trung bình |
| Leaky bucket | Điều tiết dòng xử lý theo tốc độ định trước | Có thể làm đều lưu lượng; cần giới hạn hàng đợi nếu sử dụng queue |

### Ví dụ token bucket

Giả sử một bucket minh họa có dung lượng `C = 5` token và tốc độ nạp `r = 0,1` token mỗi giây. Mỗi yêu cầu được chấp nhận dùng một token.

```text
tokens = min(C, previousTokens + r × elapsedSeconds)

nếu tokens >= 1:
    tokens = tokens - 1
    cho phép tiêu thụ quota này
ngược lại:
    từ chối tạm thời
```

Khi bucket đầy, nó cho phép một burst tối đa năm yêu cầu, sau đó cần thời gian nạp thêm. Đây chỉ là ví dụ giải thích thuật toán, không phải cấu hình khuyến nghị cho password hoặc OTP trong production.

Token bucket không tự biểu diễn mọi yêu cầu bảo mật. Nếu một challenge chỉ được thử tối đa một số lần trong toàn bộ vòng đời, việc bucket được nạp lại không được làm challenge đó có số lần đoán vô hạn trước khi hết hạn.

Cần chọn thuật toán theo loại quota. Một hệ thống có thể dùng token bucket cho lưu lượng endpoint, bộ đếm riêng cho thất bại liên tiếp và ngân sách cố định cho từng challenge.

## 6. Đặt kiểm soát trước công việc tốn kém

Một luồng xử lý có thể được tổ chức như sau:

```text
Yêu cầu xác thực
        ↓
Kiểm tra đầu vào và nguồn gọi
        ↓
Kiểm tra quota lưu lượng, phạm vi tài khoản và challenge
        ↓
Giành quyền thực hiện phép xác minh theo giới hạn đồng thời
        ↓
Xác minh credential hoặc gọi dịch vụ xác thực
        ↓
Cập nhật kết quả, trạng thái challenge và bộ đếm liên quan
        ↓
Cấp phiên khi mọi điều kiện xác thực đều thành công
```

Những kiểm tra rẻ như kích thước đầu vào, endpoint hợp lệ và giới hạn lưu lượng nguồn có thể giảm số yêu cầu đi tới bước hash mật khẩu. Tuy nhiên, cần tránh tạo phản hồi hoặc đường xử lý công khai cho phép suy ra một tài khoản có tồn tại chỉ vì nó có hay không đi qua bước tốn kém.

Giới hạn đồng thời bảo vệ số tác vụ hash hoặc số lời gọi IdP đang chạy. Nó khác với quota mỗi phút: một lượng yêu cầu nằm trong quota thời gian vẫn có thể dồn tới cùng lúc và làm quá tải tài nguyên.

Hàng đợi, nếu được dùng, cần có dung lượng và thời gian chờ giới hạn. Giữ vô hạn yêu cầu đăng nhập cùng dữ liệu credential trong queue không phải một cách xử lý tải an toàn.

## 7. Đồng thời và triển khai trên nhiều node

### 7.1. Bộ đếm local không tự trở thành giới hạn toàn hệ thống

Nếu một ứng dụng có nhiều node và mỗi node giữ một quota độc lập, tổng số phép thử có thể cao hơn nhiều so với ngưỡng mà người thiết kế tưởng là dùng chung.

Cần xác định giới hạn nào là local để bảo vệ tài nguyên của node, giới hạn nào phải được chia sẻ và mức sai lệch nào được chấp nhận. Các giới hạn chặt cho một challenge hoặc authenticator cần được thiết kế theo đúng yêu cầu bảo mật của chúng, không dựa vào giả định mọi yêu cầu luôn tới cùng một node.

### 7.2. Đọc rồi tăng ở hai thao tác riêng có thể sai

Một thiết kế nguy hiểm là đọc bộ đếm, thấy còn lượt, thực hiện xác minh rồi mới tăng thất bại mà không kiểm soát đồng thời. Nhiều yêu cầu có thể cùng thấy một lượt còn lại và đều được xử lý.

Việc kiểm tra và tiêu thụ quota cần có tính nguyên tử phù hợp. Với giới hạn số phép xác minh còn lại của challenge, có thể cần giành một lượt thử hoặc ghi nhận phép thử đang xử lý trước khi xác minh, rồi hoàn tất trạng thái theo kết quả.

Không nhất thiết mọi lớp quota phải nằm trong một giao dịch phân tán duy nhất. Tuy nhiên, yêu cầu chỉ được đi tiếp khi đã giành được các quyền xử lý cần thiết. Nếu một lớp đã tiêu thụ quota nhưng lớp tiếp theo từ chối, cần có chính sách nhất quán về phần quota đã dùng; không hoàn lại tùy tiện theo cách tạo thêm lượt ngoài thiết kế.

### 7.3. Thời gian, TTL và khôi phục trạng thái

Limiter cần một cơ sở thời gian nhất quán đủ cho mô hình triển khai. Chênh lệch đồng hồ hoặc reset trạng thái sau khi khởi động lại có thể làm thay đổi thời hạn chờ và số lượt được xử lý.

TTL giúp dọn các khóa không còn cần thiết, nhưng TTL cũng là một phần của ngữ nghĩa bảo mật. Nếu bộ đếm challenge biến mất trước challenge, một phép thử mới có thể nhận lại ngân sách ngoài dự kiến.

Kho limiter cũng cần được bảo vệ khỏi việc tạo số lượng khóa quá lớn bằng các định danh ngẫu nhiên. Cần giới hạn cardinality, kích thước khóa, thời gian lưu và quota nguồn trước khi tạo thêm trạng thái.

## 8. Khóa tài khoản và nguy cơ gây từ chối dịch vụ

Nếu chỉ cần biết username là có thể gây khóa vĩnh viễn sau vài lần nhập sai, một bên khác có thể ngăn chủ tài khoản hợp lệ đăng nhập. Policy phải cân nhắc cả khả năng đoán credential lẫn khả năng lợi dụng cơ chế khóa.

OWASP lưu ý cần kết hợp bảo vệ theo tài khoản với cân nhắc về số lần thất bại, cửa sổ quan sát, thời gian khóa và nguy cơ khóa người dùng hợp lệ. [OWASP Authentication Cheat Sheet — Account Lockout](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#account-lockout).

Các biện pháp có thể kết hợp gồm thời gian chờ tăng dần có giới hạn, phát hiện mẫu lạm dụng, kiểm tra bổ sung theo rủi ro và quy trình phục hồi có kiểm soát. Việc chọn biện pháp phải phù hợp yêu cầu của authenticator và mức nhạy cảm tài khoản.

CAPTCHA có thể tăng chi phí tự động hóa nhưng không thay thế mật khẩu, MFA hay quota phía máy chủ. Hoàn thành CAPTCHA cũng không nên xóa mọi giới hạn tổng hợp của tài khoản, IP hoặc hệ thống gửi tin.

Khi xác thực thành công, có thể đặt lại một bộ đếm thất bại liên tiếp phù hợp với authenticator vừa được sử dụng theo policy. Không vì vậy đặt lại toàn bộ lịch sử chống lạm dụng của nguồn gọi, ngân sách gửi OTP hoặc mọi challenge khác.

Phục hồi tài khoản phải có bảo vệ riêng. Một endpoint phục hồi không giới hạn có thể trở thành đường thay thế để thử credential, gửi tin hàng loạt hoặc né giới hạn đăng nhập.

## 9. OTP, MFA và challenge cần ngân sách riêng

Mã có thời hạn ngắn vẫn cần giới hạn số lần thử. Về mặt minh họa, nếu chỉ có đúng một mã sáu chữ số phân bố đều được chấp nhận và mã không đổi, năm phép đoán khác nhau có xác suất trúng là `5 / 1.000.000`. Nếu chấp nhận nhiều mã hoặc cho phép nhiều phép thử hơn, phải xét lại mô hình đó.

Ví dụ xác suất không phải căn cứ duy nhất để chọn policy. Cần tính đến loại authenticator, vòng đời mã, khả năng thử đồng thời, yêu cầu sử dụng và các giới hạn của cơ chế xác thực đang áp dụng.

Một challenge cần được liên kết với đúng tài khoản, mục đích và giao dịch xác thực. Mã dùng để xác nhận đổi email không nên tự động có giá trị cho việc đặt lại mật khẩu.

Các kiểm soát quan trọng gồm:

- Giới hạn số lần xác minh của challenge và giới hạn tổng hợp theo tài khoản hoặc authenticator.
- Giới hạn số lần gửi, thời gian giữa các lần gửi và lưu lượng tới một người nhận.
- Hết hạn và xử lý mã sau khi sử dụng thành công.
- Quy tắc rõ ràng về mã cũ khi phát hành hoặc gửi lại mã mới.
- Kiểm soát thông báo MFA để không tạo yêu cầu chấp thuận dồn dập.

Tạo challenge mới không nên làm mất toàn bộ lịch sử thử sai liên quan. Nếu mỗi lần hết lượt chỉ cần tạo một challenge khác để nhận lại ngân sách, giới hạn ở cấp challenge chưa đủ.

Trạng thái sử dụng thành công cần được cập nhật nguyên tử để hai yêu cầu đồng thời không dùng cùng một mã cho hai kết quả ngoài dự kiến. Không cấp phiên chỉ vì bước so sánh mã thành công nếu bước xác nhận challenge chưa dùng và chuyển trạng thái lại thất bại.

Các ràng buộc này áp dụng cho luồng phục hồi và mã dự phòng theo cơ chế tương ứng. Không mặc định rằng một endpoint ít được người dùng mở sẽ ít bị tự động hóa.

## 10. Phản hồi HTTP và tránh lộ trạng thái tài khoản

Với một yêu cầu bị giới hạn tạm thời, API có thể dùng `429 Too Many Requests`. Khi có thời gian chờ phù hợp để thông báo, phản hồi có thể kèm `Retry-After`. RFC 6585 quy định ý nghĩa mã này và cho phép header đó; RFC không quyết định thay ứng dụng phải đếm theo IP hay tài khoản. [RFC 6585, mục 4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4).

Ví dụ phản hồi minh họa:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Cache-Control: no-store
Content-Type: application/json

{
  "error": "authentication_throttled",
  "message": "Chua the xu ly yeu cau. Vui long thu lai sau."
}
```

Client nên tuân thủ thời gian chờ thay vì tự gửi lại liên tục. Retry tự động của SDK, ứng dụng di động hoặc proxy cũng cần được xem xét để một lần người dùng thao tác không tạo thành nhiều lần xác thực ngoài dự kiến.

Phản hồi trước xác thực không nên tùy tiện phân biệt “không có tài khoản”, “mật khẩu sai” và “tài khoản này đang khóa” theo cách cho phép người gọi liệt kê tài khoản. Cần xem cả mã lỗi, body, header, URL chuyển hướng và khác biệt thời gian xử lý.

Không chỉ đổi nội dung thông báo thành một câu chung trong khi mọi dấu hiệu còn lại vẫn bộc lộ trạng thái. Xử lý định danh không tồn tại và quota tương ứng cũng cần nằm trong thiết kế này.

Với một challenge đã được liên kết và xác thực theo đúng luồng, sản phẩm có thể cung cấp hướng dẫn sử dụng chi tiết hơn theo policy. Cần phân biệt ngữ cảnh đó với một người gọi chưa chứng minh được quan hệ với tài khoản.

Khi hệ thống phụ thuộc bị lỗi, không nên giả vờ mọi trường hợp đều là người dùng vượt quota. Trạng thái lỗi nội bộ cần được ghi nhận đúng để vận hành, trong khi phản hồi công khai vẫn tuân theo hợp đồng API và giới hạn thông tin cần thiết.

## 11. Luồng xử lý minh họa và lựa chọn khi có lỗi

```text
function authenticate(request):
    realm = resolveConfiguredRealm(request)
    source = resolveTrustedNetworkSource(request)
    identifier = parseIdentifierUsingRealmPolicy(request, realm)

    quotas = deriveQuotaScopes(realm, source, identifier, request.flow)
    if not consumeRequiredRequestQuotas(quotas):
        return genericThrottleResponse()

    attempt = reserveAllowedVerificationAttempt(request, realm, identifier)
    if not attempt.allowed:
        return genericThrottleResponse()

    outcome = verifyCredentialWithBoundedResources(request, attempt)

    if outcome.isSystemError:
        finishAttemptAsTechnicalFailure(attempt)
        recordOperationalFailureWithoutSecrets()
        return genericUnavailableResponse()

    result = finalizeAttemptAndChallengeStateAtomically(attempt, outcome)
    recordAuthenticationOutcomeWithoutSecrets(result)

    if result.authenticationCompletedAndAccountStillAllowed:
        return createSessionWithinValidatedContext(result)

    return genericAuthenticationFailure()
```

Mã giả chỉ mô tả các trách nhiệm. Những hàm liên quan tới quota, phép thử đang chạy và challenge cần có bảo đảm đồng thời thích hợp với kho lưu trữ thực tế. `verifyCredential` cũng phải triển khai đúng cơ chế xác thực tương ứng; limiter không bù được việc xác minh credential sai.

Nếu kho limiter không truy cập được, hệ thống cần một policy lỗi đã định nghĩa trước. Với OTP, phục hồi hoặc thao tác đặc quyền cần giới hạn chặt, không nên tự cho phép vô hạn phép thử chỉ để endpoint tiếp tục trả kết quả.

Một cơ chế dự phòng có thể dùng giới hạn local bảo thủ hoặc tạm thời từ chối một số luồng, tùy kiến trúc và mức sai lệch được chấp nhận. Cần hiểu giới hạn local trên nhiều node không tự bảo đảm ngưỡng chia sẻ. Không báo cáo rằng kiểm soát vẫn đầy đủ nếu thực tế đã chuyển sang một chế độ bảo vệ yếu hơn.

Khi tích hợp IdP, cần biết giới hạn nào do ứng dụng áp dụng và giới hạn nào do IdP thực thi. Bảo vệ tại IdP không tự giới hạn số yêu cầu mà ứng dụng chuyển tiếp hoặc số lần ứng dụng gửi thông báo. Không mở một luồng đăng nhập thay thế yếu hơn chỉ vì luồng chính đang bị throttle.

## 12. Theo dõi, kiểm chứng và câu hỏi tự kiểm tra

Các chỉ số hữu ích gồm số lần được phép và bị giới hạn theo loại luồng, số thất bại credential, lỗi kỹ thuật, số phép xác minh đồng thời, độ trễ hash hoặc IdP, lượng gửi OTP và tỷ lệ người dùng hợp lệ phải chờ.

Log cần đủ để liên kết sự kiện với realm, nguồn hoặc định danh được bảo vệ và lý do quyết định nội bộ. Không ghi mật khẩu, OTP, mã phục hồi, token hoặc body xác thực đầy đủ. Tránh dùng mọi username tùy ý làm nhãn metric vì có thể tạo cardinality quá lớn và lộ dữ liệu.

Các tình huống kiểm tra quan trọng:

| Tình huống | Điều cần xác nhận |
|---|---|
| Nhiều nguồn cùng thử một tài khoản | Giới hạn ở cấp tài khoản hoặc authenticator vẫn có hiệu lực |
| Một nguồn thử nhiều tài khoản | Kiểm soát nguồn và tổng lưu lượng có thể phản ánh mẫu này |
| Nhiều người hợp lệ dùng chung IP | Không bị ảnh hưởng ngoài mức policy đã chấp nhận |
| Nhiều node xử lý đồng thời một challenge gần hết lượt | Số phép xác minh không vượt giới hạn do lỗi đọc rồi tăng |
| Tạo hoặc gửi lại challenge | Không đặt lại ngoài ý muốn mọi ngân sách liên quan |
| Cùng mã được gửi đồng thời hai lần | Trạng thái một lần sử dụng được thực thi đúng |
| Username không tồn tại | Không tạo đường liệt kê tài khoản hoặc vô hạn trạng thái lưu trữ |
| IdP hoặc kho limiter gặp lỗi | Áp dụng đúng chế độ lỗi; không mở vô hạn phép thử |
| Credential đúng sau nhiều lần sai | Chỉ đặt lại những bộ đếm phù hợp theo policy |
| Cùng luồng có endpoint web, mobile hoặc phiên bản API khác | Giới hạn bảo mật không bị bỏ qua qua đường tương đương |

Câu hỏi tự kiểm tra:

1. Vì sao giới hạn theo IP và giới hạn theo tài khoản cần bổ sung cho nhau?
2. Quota yêu cầu khác gì với số lần xác thực thất bại liên tiếp?
3. Vì sao TTL của OTP hoặc cache không thay thế giới hạn phép thử?
4. Điều gì xảy ra nếu nhiều node cùng đọc bộ đếm còn một lượt trước khi cập nhật?
5. Làm thế nào hạn chế đoán credential mà không biến cơ chế khóa thành công cụ gây gián đoạn cho người dùng hợp lệ?

Rate limit authentication cần ràng buộc đúng phạm vi, được thực thi trước công việc tốn kém và duy trì đúng ngữ nghĩa khi có nhiều node, challenge hoặc đường đăng nhập. Hiệu quả của nó phụ thuộc cả chính sách giới hạn lẫn cách xử lý đồng thời, phản hồi, phục hồi và vận hành khi có lỗi.
