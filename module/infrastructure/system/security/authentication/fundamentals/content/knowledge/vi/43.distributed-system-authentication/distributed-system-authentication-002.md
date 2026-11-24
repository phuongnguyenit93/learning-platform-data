# Clock skew

> **Chương:** Authentication trong distributed system  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Hiểu sai lệch đồng hồ giữa các máy và tác động của nó tới token, chứng chỉ, MFA, session, chữ ký request, chống replay và audit trong hệ thống phân tán.

## 1. Clock skew là gì?

**Clock skew** là độ lệch giữa thời gian mà các hệ thống khác nhau đang quan sát. Hai máy có thể cùng dùng UTC nhưng đồng hồ vẫn khác nhau vài mili giây, vài giây hoặc lâu hơn. Độ lệch có thể đến từ sai số phần cứng, cấu hình đồng bộ, mạng, máy ảo bị suspend/resume, lỗi time source hoặc thao tác chỉnh giờ.

Ví dụ, Authorization Server phát hành JWT lúc 10:00:00 với thời hạn đến 10:05:00. Resource Server đang chạy chậm 40 giây so với Authorization Server có thể tiếp tục chấp nhận token lâu hơn dự kiến. Ngược lại, nếu Resource Server chạy nhanh hơn 40 giây, nó có thể từ chối token trước thời điểm hết hạn theo đồng hồ của issuer.

Trong distributed system, thời gian thường được dùng để quyết định credential còn hiệu lực hay không. Một sai lệch nhỏ có thể gây lỗi đăng nhập ngẫu nhiên giữa các node; một sai lệch lớn hoặc bị attacker điều khiển có thể mở rộng cửa sổ replay, kéo dài hiệu lực credential đã hết hạn hoặc làm hỏng quá trình thu hồi.

### Kết quả học tập

Sau bài này, người học có thể:

- Phân biệt wall clock, monotonic clock, offset, drift và uncertainty.
- Giải thích vì sao các node trong một hệ thống không có cùng thời điểm tuyệt đối.
- Hiểu tác động của clock skew tới JWT, OIDC, certificate, TOTP, Kerberos và request signing.
- Chọn tolerance hợp lý mà không mở rộng quá mức cửa sổ credential.
- Thiết kế đồng bộ thời gian có giám sát và nguồn tin cậy.
- Phân biệt thời gian dùng để xác thực với thời gian dùng để đo duration.
- Kiểm thử lệch giờ, clock rollback, suspend/resume và lỗi time source.

## 2. Wall clock, monotonic clock và các loại sai lệch

Không phải mọi loại clock đều phù hợp cho mọi mục đích.

| Khái niệm | Ý nghĩa | Dùng cho |
|---|---|---|
| Wall clock / realtime clock | Thời gian lịch mà hệ điều hành biểu diễn, thường quy về UTC | JWT exp/iat, certificate validity, TOTP, audit timestamp |
| Monotonic clock | Bộ đếm chỉ tiến về phía trước trong phạm vi clock được định nghĩa | Timeout, elapsed duration, retry delay, đo latency |
| Offset | Chênh lệch thời điểm giữa hai clock tại một thời điểm quan sát | Đánh giá máy chạy nhanh/chậm |
| Drift | Tốc độ sai lệch tăng dần theo thời gian do clock không chạy đúng tốc độ tham chiếu | Dự báo sai lệch nếu không đồng bộ |
| Jitter | Dao động của phép đo offset hoặc độ trễ | Đánh giá chất lượng đồng bộ |
| Uncertainty | Biên độ không chắc chắn của ước lượng thời gian | Quyết định tolerance và độ tin cậy |
| Clock step | Thay đổi wall clock đột ngột | Có thể làm timestamp nhảy tiến hoặc lùi |
| Clock slew | Điều chỉnh tốc độ clock trong một khoảng thời gian | Đồng bộ dần, hạn chế nhảy thời gian |

### Wall clock có thể nhảy

Wall clock có thể được điều chỉnh bởi dịch vụ đồng bộ thời gian, quản trị viên, hypervisor hoặc cấu hình hệ điều hành. Vì vậy, không nên dùng phép trừ hai lần đọc wall clock để đo timeout hoặc thời gian chạy nếu ứng dụng cần duration ổn định.

### Monotonic clock không thay thế UTC

Monotonic clock phù hợp để đo một khoảng thời gian trong cùng môi trường thực thi, nhưng không phải timestamp lịch có thể so sánh trực tiếp giữa nhiều máy. Giá trị monotonic của hai host không có cùng epoch và không nên được gửi như thời điểm phát hành token.

Quy tắc thực tế:

- Dùng UTC wall clock cho thời điểm phát hành, hết hạn và audit.
- Dùng monotonic clock cho timeout, elapsed time và backoff.
- Không dùng timezone hoặc giờ địa phương làm cơ sở kiểm tra credential.
- Không giả định monotonic clock của mọi nền tảng xử lý suspend/sleep giống nhau; kiểm tra semantics của hệ điều hành và runtime.

## 3. Vì sao đồng hồ giữa các node bị lệch?

Các nguyên nhân thường gặp:

- Oscillator phần cứng có sai số và thay đổi theo nhiệt độ, tuổi thiết bị.
- Máy khởi động lâu hoặc mất kết nối time source.
- NTP server không sẵn sàng, cấu hình sai hoặc bị truy vấn qua đường mạng bất ổn.
- VM bị pause, snapshot, migrate hoặc resume.
- Container phụ thuộc clock của host; lỗi đồng bộ host ảnh hưởng nhiều container.
- Máy có nhiều time source xung đột.
- Quản trị viên chỉnh giờ thủ công hoặc hệ thống tự đồng bộ sai.
- Network latency và asymmetric routing làm phép đo offset kém chính xác.
- Leap second hoặc cơ chế leap smear khác nhau giữa nhà cung cấp.

Một cluster có thể có các node lệch nhau dù tất cả đều hiển thị cùng timezone. Timezone chỉ thay đổi cách hiển thị giờ; nó không sửa offset của clock.

## 4. NTP, PTP và nguồn thời gian tin cậy

### NTP

Network Time Protocol (NTP) đồng bộ clock qua mạng bằng cách trao đổi timestamp với time server. NTP ước lượng offset và round-trip delay, rồi điều chỉnh clock theo thuật toán của client.

Các khái niệm thường gặp:

- **Stratum:** khoảng cách logic tới nguồn tham chiếu; số stratum thấp hơn không tự động chứng minh nguồn chính xác hoặc đáng tin hơn.
- **Offset:** ước lượng clock local nhanh/chậm bao nhiêu so với peer.
- **Delay:** độ trễ đo được của trao đổi.
- **Jitter:** độ biến động của các phép đo.
- **Reachability:** khả năng liên lạc với peer theo các lần poll.

Không nên chỉ cấu hình một NTP server bất kỳ trên Internet rồi mặc định thời gian chính xác. Chọn time source được tổ chức quản lý, cấu hình nhiều nguồn độc lập khi phù hợp và giám sát trạng thái đồng bộ.

### NTS và bảo vệ nguồn thời gian

NTP thông thường không mặc nhiên xác thực mọi nguồn thời gian. Kẻ tấn công có thể cố làm sai lệch phản hồi, giả mạo nguồn hoặc gây từ chối đồng bộ. Network Time Security (NTS) bổ sung cơ chế xác thực và bảo vệ trao đổi NTP dựa trên TLS và cơ chế xác thực gói tin.

Nếu nền tảng hỗ trợ, cân nhắc NTS hoặc cơ chế bảo vệ tương đương. Nếu không, giới hạn nguồn NTP bằng network policy, firewall và cấu hình peer tin cậy; giám sát thay đổi bất thường và tránh để máy chủ thời gian nội bộ có thể bị truy cập/chỉnh sửa tùy tiện.

### PTP

Precision Time Protocol (PTP, IEEE 1588) có thể cung cấp đồng bộ chính xác hơn trong môi trường có hỗ trợ phần cứng và mạng phù hợp, chẳng hạn hệ thống công nghiệp hoặc trung tâm dữ liệu cần độ chính xác cao. PTP đòi hỏi thiết kế grandmaster, boundary clock/transparent clock và hạ tầng tương thích; không phải lựa chọn mặc định cho mọi ứng dụng web.

### Nguồn thời gian là một phần của trust boundary

Nếu hệ thống dựa vào thời gian để chấp nhận token hoặc chứng chỉ, time source có ảnh hưởng trực tiếp đến quyết định bảo mật. Hãy quản lý quyền thay đổi cấu hình NTP/PTP, xác thực nguồn khi có thể, phân vùng mạng, giám sát offset và có quy trình xử lý khi nguồn thời gian bị nghi compromise.

## 5. Clock skew ảnh hưởng đến JWT như thế nào?

JWT có thể chứa các claim thời gian:

- iat (Issued At): thời điểm token được phát hành.
- nbf (Not Before): token không được chấp nhận trước thời điểm này.
- exp (Expiration Time): token không được chấp nhận tại hoặc sau thời điểm hết hạn.

Theo semantics của JWT, resource server kiểm tra thời gian hiện tại so với nbf và exp. Một số thư viện hỗ trợ **clock tolerance/leeway** để bù sai lệch nhỏ giữa issuer và verifier.

### Ví dụ

Issuer phát token:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": "orders-api",
  "iat": 1795341600,
  "nbf": 1795341600,
  "exp": 1795341900
}
~~~

Nếu resource server chạy nhanh hơn issuer 45 giây, nó có thể thấy token chưa đến nbf ngay sau khi token vừa được phát hành. Nếu server chạy chậm, nó có thể chấp nhận token sau exp theo thời gian thực của issuer.

### Chọn leeway

- Đồng bộ clock trước, dùng leeway chỉ để hấp thụ sai lệch nhỏ còn lại.
- Chọn tolerance dựa trên số liệu offset thực tế và mức rủi ro.
- Không dùng leeway lớn để che giấu NTP hỏng hoặc host không đồng bộ.
- Áp dụng nhất quán cho nbf và exp; cân nhắc kiểm tra iat ở profile ứng dụng.
- Không kéo dài lifetime token chỉ vì node có clock sai.
- Theo dõi số lần token bị từ chối do thời gian và so sánh giữa node.

Leeway là một phần của cửa sổ chấp nhận credential. Nếu cho phép sai lệch 2 phút, token có thể được chấp nhận sớm hoặc muộn thêm khoảng thời gian tương ứng theo cách thư viện định nghĩa. Hãy đọc semantics cụ thể của thư viện đang dùng.

### Xác minh JWT vẫn phải đầy đủ

Clock hợp lý không thay thế xác minh chữ ký. Resource server vẫn phải kiểm tra thuật toán, key, issuer, audience, thời hạn và quyền. Không decode token rồi tin exp hoặc sub khi chưa xác minh chữ ký.

## 6. Clock skew trong OAuth 2.0 và OpenID Connect

OAuth/OIDC dùng nhiều timestamp và nonce/state có vòng đời khác nhau:

- Authorization code có thời hạn ngắn và thường dùng một lần.
- Access token có thời điểm hết hạn.
- ID token có iat và exp, đôi khi có auth_time.
- Refresh token có chính sách lifetime/rotation riêng.
- OIDC nonce và OAuth state liên kết request với callback, không thay thế kiểm tra thời gian hoặc replay.

### Các lỗi có thể gặp

- Backend từ chối ID token vì iat có vẻ nằm trong tương lai.
- Resource server từ chối access token sớm do clock chạy nhanh.
- Một node chấp nhận token đã hết hạn vì clock chạy chậm.
- Authorization code hết hạn ở token endpoint nhưng client nghĩ vẫn còn hiệu lực.
- Callback hợp lệ bị lỗi ngẫu nhiên khi các node xử lý có clock lệch khác nhau.

### Thiết kế

- Đồng bộ thời gian trên browser-facing backend, callback handler, authorization server và resource server.
- Kiểm tra token tại server bằng thư viện OIDC/OAuth đã được kiểm chứng.
- Dùng thời hạn code/token ngắn theo threat model, nhưng bảo đảm hạ tầng clock đáp ứng.
- Không tái sử dụng authorization code nếu đổi code thất bại; xử lý retry theo protocol.
- Lưu state/nonce theo session và kiểm tra đúng request, không chỉ dựa trên timestamp.
- Ghi reason code và node ID để xác định lỗi do clock hay do token.

## 7. Clock skew và chứng chỉ số

X.509 certificate có khoảng hiệu lực:

- notBefore: chứng chỉ bắt đầu có hiệu lực.
- notAfter: chứng chỉ hết hiệu lực.

TLS client/server kiểm tra thời gian hiện tại so với khoảng này. Nếu client chạy nhanh, chứng chỉ mới có thể bị coi là chưa có hiệu lực. Nếu client chạy chậm, chứng chỉ hết hạn có thể vẫn được chấp nhận theo clock sai.

### Ví dụ

Một chứng chỉ được CA cấp với notBefore lúc 12:00 UTC. Một node có đồng hồ sớm hơn 90 giây có thể từ chối chứng chỉ mới khi handshake xảy ra ngay sau thời điểm cấp.

### Biện pháp

- Đồng bộ thời gian trên host, container node và thiết bị TLS termination.
- Theo dõi certificate expiry và cảnh báo trước hạn.
- Khi triển khai certificate mới, cân nhắc khoảng overlap hợp lý giữa chứng chỉ cũ và mới.
- Không đặt notBefore quá xa trong tương lai chỉ để bù clock skew nếu không có lý do PKI rõ ràng.
- Không bỏ qua kiểm tra validity để khắc phục lỗi đồng hồ.
- Xác minh chain, hostname, EKU, key usage và trạng thái thu hồi theo policy.

Certificate overlap xử lý chuyển đổi vòng đời, còn clock tolerance xử lý sai số thời gian; hai biện pháp không thay thế nhau.

## 8. Clock skew trong TOTP và MFA

Time-based One-Time Password (TOTP, RFC 6238) tính mã từ secret và time counter chia thời gian thành các bước cố định, thường là 30 giây theo cấu hình phổ biến. Authenticator và server phải có thời gian đủ gần nhau để sinh cùng mã trong cửa sổ được chấp nhận.

### Tại sao lệch giờ gây lỗi?

Nếu điện thoại chạy nhanh hoặc chậm nhiều bước, mã người dùng nhìn thấy có thể không khớp với bước mà server đang kiểm tra. Người dùng có thể nhập đúng mã được app hiển thị nhưng login vẫn thất bại.

### Cửa sổ chấp nhận

Server có thể kiểm tra step hiện tại và một số step lân cận để hấp thụ sai lệch nhỏ. Cửa sổ càng rộng thì trải nghiệm càng dễ chịu, nhưng khoảng thời gian một mã có thể được chấp nhận càng dài.

Thiết kế an toàn:

- Đồng bộ thời gian server bằng nguồn đáng tin.
- Giữ cửa sổ TOTP nhỏ theo threat model và cấu hình đã kiểm thử.
- Giới hạn số lần thử và rate limit theo account/device/risk.
- Không cho phép dùng lại một mã đã chấp nhận trong cùng step nếu policy yêu cầu chống replay.
- Theo dõi lỗi TOTP theo node, vùng và loại thiết bị.
- Cung cấp hướng dẫn sửa thời gian tự động trên authenticator thay vì nới cửa sổ vô hạn.

### TOTP và HOTP

HOTP dùng counter tăng dần thay vì thời gian. Clock skew không ảnh hưởng trực tiếp đến HOTP như TOTP, nhưng server và authenticator phải quản lý counter đồng bộ; một cửa sổ look-ahead quá rộng cũng có thể tăng rủi ro dò mã.

## 9. Clock skew trong Kerberos và giao thức xác thực dựa trên timestamp

Kerberos dùng timestamp trong authenticator để chống replay. Client và KDC/service cần đồng hồ đủ gần nhau. Nhiều triển khai có cấu hình maximum clock skew; một số môi trường mặc định khoảng vài phút, nhưng giá trị chính xác phụ thuộc implementation và policy.

Nếu lệch vượt ngưỡng, request có thể bị từ chối với lỗi clock skew. Nếu nới ngưỡng quá lớn, attacker có thêm thời gian để phát lại authenticator bị lấy cắp, tùy cơ chế cache và replay detection.

Biện pháp:

- Đồng bộ client, KDC và service.
- Giữ maximum skew theo tiêu chuẩn/policy của môi trường.
- Không tắt replay cache để chữa lỗi lệch giờ.
- Kiểm tra trạng thái NTP và thời gian của VM/domain controller.
- Ghi log có node, principal và thời điểm; không ghi secret ticket.

Các giao thức ký request như AWS-style signed requests hoặc HTTP Message Signatures cũng có thể dùng timestamp để giới hạn freshness. Cần tuân theo profile của giao thức, không suy ra một cửa sổ chấp nhận chung cho mọi hệ thống.

## 10. Timestamp và chống replay

Timestamp thường được dùng để giới hạn thời gian một request đã ký còn hợp lệ. Tuy nhiên, timestamp đơn lẻ không bảo đảm request chỉ được dùng một lần.

### Ví dụ request signing

Client ký method, path, body digest và timestamp. Server chấp nhận nếu timestamp nằm trong cửa sổ cho phép. Nếu attacker lấy được request đã ký và gửi lại trong cửa sổ đó, chữ ký vẫn hợp lệ trừ khi có cơ chế chống replay bổ sung.

### Các lớp bảo vệ

- Timestamp hoặc creation time có cửa sổ freshness nhỏ.
- Nonce hoặc request ID duy nhất.
- Replay cache lưu nonce đã dùng trong suốt cửa sổ chấp nhận.
- Idempotency key cho hành động nghiệp vụ có thể retry.
- Ràng buộc chữ ký với method, path, body và các header quan trọng.
- Giới hạn audience/service nhận.
- Xác thực sender bằng key/certificate phù hợp.

Nonce store cần xử lý atomicity và race condition. Nếu hai node cùng nhận nonce lần đầu gần như đồng thời, một hệ thống cache không nhất quán có thể cho cả hai request đi qua. Với thao tác nhạy cảm, cần một cơ chế lưu/claim nonce có tính nguyên tử trên phạm vi các node.

### Đừng nhầm idempotency với authentication

Idempotency key giúp ngăn xử lý nghiệp vụ lặp khi client retry. Nó không chứng minh caller là ai và không thay thế chữ ký, token hoặc authorization. Một attacker có thể tự tạo idempotency key nếu API không xác thực request.

## 11. Clock skew trong session và token lifecycle

Session có thể được quản lý bằng timestamp server-side hoặc token tự chứa.

### Server-side session

Session store thường lưu created_at, last_seen_at, expires_at hoặc thời điểm hết hạn idle. Nếu nhiều app node có clock lệch, node này có thể coi session hết hạn trong khi node khác còn chấp nhận.

Biện pháp:

- Đồng bộ clock trên mọi node.
- Dùng một nguồn thời gian nhất quán ở session store khi phù hợp.
- Với timeout duration, dùng monotonic clock trong process để đo elapsed time.
- Với session state chia sẻ, quy định rõ timestamp và clock authority.
- Tránh cập nhật last_seen_at theo request nền vô hạn.

### JWT và refresh token

JWT access token thường tự chứa thời điểm hết hạn. Refresh token thường được quản lý trong database hoặc authorization server với trạng thái rotation/revocation. Nếu node dùng clock khác nhau, access token có thể bị chấp nhận không đồng nhất; nếu refresh token được kiểm tra theo timestamp, vấn đề tương tự có thể xảy ra.

Không cộng leeway ở mọi tầng một cách độc lập. Nếu gateway, resource server và cache đều thêm tolerance, tổng cửa sổ chấp nhận có thể lớn hơn dự kiến. Tài liệu hóa clock policy thống nhất và kiểm thử end-to-end.

## 12. Timezone, daylight saving và leap second

### Timezone không phải clock synchronization

UTC+7 và UTC là hai cách biểu diễn cùng một thời điểm với offset khác nhau. Việc đổi timezone không làm đồng hồ chính xác hơn. Dùng UTC/Unix time cho protocol timestamp; chỉ chuyển sang timezone địa phương khi hiển thị.

### Daylight saving time

Daylight saving làm giờ địa phương nhảy tiến/lùi ở một số khu vực. Nếu ứng dụng lưu hoặc so sánh giờ địa phương thay vì instant UTC, có thể xuất hiện timestamp trùng hoặc không tồn tại. Không dùng local time để kiểm tra exp, certificate validity hoặc TOTP.

### Leap second và leap smear

Leap second có thể được xử lý khác nhau giữa hệ điều hành, time service và cloud provider. Một số nhà cung cấp dùng leap smear để phân bổ điều chỉnh trong một khoảng thời gian; hai hệ thống dùng cách khác nhau có thể lệch nhau tạm thời.

Không tự cộng/trừ một giây trong logic authentication. Dùng time service của nền tảng, thư viện thời gian chuẩn và hiểu chính sách leap handling của các host. Khi triển khai nhiều cloud/region, xác nhận chúng có cách xử lý tương thích.

## 13. Clock rollback và time manipulation

Clock rollback xảy ra khi wall clock bị chỉnh lùi. Clock jump forward xảy ra khi đồng hồ nhảy tiến đột ngột. Cả hai đều có thể ảnh hưởng authentication:

- Clock lùi có thể làm token hoặc certificate hết hạn bị coi là còn hiệu lực.
- Clock tiến có thể làm token/session/certificate hợp lệ bị từ chối.
- TOTP có thể sinh step cũ hoặc step tương lai.
- Nonce/replay cache dựa trên timestamp có thể giữ hoặc xóa record sai thời điểm.
- Audit log có thể xuất hiện sự kiện không theo thứ tự.
- Job scheduler có thể chạy lặp hoặc bỏ qua công việc.

### Phòng vệ

- Phát hiện thay đổi wall clock vượt ngưỡng và phát cảnh báo.
- Dùng monotonic clock cho timeout và retry.
- Không cho ứng dụng tự chỉnh system clock.
- Giới hạn quyền quản trị time service.
- Dùng NTS hoặc nguồn thời gian được bảo vệ khi hỗ trợ.
- Khi clock không đáng tin, từ chối hành động bảo vệ hoặc chuyển sang trạng thái degraded có kiểm soát.
- Không tự động nới token leeway, certificate check hoặc TOTP window khi thấy nhiều lỗi.

Một clock rollback lớn nên được xem là sự kiện vận hành và có thể là tín hiệu bảo mật. Điều tra nguồn thay đổi trước khi khôi phục dịch vụ.

## 14. Thời gian trong audit và thứ tự sự kiện

Timestamp giúp tìm kiếm và tương quan sự kiện, nhưng không phải lúc nào cũng đủ để xác định thứ tự chính xác giữa các node. Hai sự kiện có thể được ghi cùng timestamp hoặc lệch nhau vì clock offset và network delay.

Audit nên lưu khi phù hợp:

- UTC timestamp.
- Node/region/service ID.
- Event ID duy nhất.
- Correlation/trace ID.
- Principal, actor, action và kết quả.
- Authentication method/context.
- Nguồn thời gian hoặc trạng thái đồng bộ nếu phục vụ điều tra.

Không ghi access token, session cookie, password, OTP hoặc private key vào audit. Nếu cần thứ tự nhân quả, dùng event sequence, database commit order, message offset hoặc trace relationship thay vì chỉ so sánh wall clock.

## 15. Thiết kế clock tolerance có căn cứ

Tolerance là khoảng sai lệch mà hệ thống chấp nhận. Không có một con số chung an toàn cho mọi giao thức.

### Cách chọn

1. Đo offset, jitter và uncertainty thực tế của các node/region.
2. Xác định clock source và mức độ tin cậy.
3. Xác định credential nào đang được kiểm tra và hậu quả khi chấp nhận sớm/muộn.
4. Xác định replay window, lifetime và yêu cầu latency.
5. Chọn tolerance nhỏ nhất đáp ứng vận hành bình thường.
6. Đặt cảnh báo khi offset tiến gần tolerance.
7. Kiểm thử với clock nhanh, chậm, nhảy tiến, nhảy lùi và time source outage.
8. Review sau khi thay đổi hạ tầng hoặc thư viện.

### Ví dụ định hướng, không phải giá trị mặc định

| Cơ chế | Điều cần cân nhắc |
|---|---|
| JWT exp/nbf | Leeway nhỏ so với token lifetime; xác định rõ thư viện áp dụng cho claim nào |
| TOTP | Chỉ cho phép số step lân cận giới hạn; ưu tiên sửa clock thiết bị |
| Kerberos | Theo maximum skew của realm/implementation và replay cache |
| Signed request | Theo freshness window của protocol, nonce và idempotency |
| Certificate | Đồng bộ host; xử lý notBefore/expiry đúng PKI, không bỏ validation |
| Session timeout | Dùng monotonic cho duration; timestamp chia sẻ theo clock authority |

Không đặt tolerance lớn chỉ để che lỗi đồng bộ. Nếu node lệch nhiều hơn giới hạn, cần sửa time service hoặc đưa node ra khỏi traffic bảo vệ.

## 16. Monitoring và vận hành

Các chỉ số nên theo dõi:

- Offset của từng host so với time source.
- Root dispersion/uncertainty hoặc metric tương đương do time daemon cung cấp.
- NTP/PTP source reachability và trạng thái synchronization.
- Clock step/slew event và thay đổi cấu hình time service.
- Số lần JWT bị từ chối do nbf/exp/iat.
- Tỷ lệ TOTP thất bại theo region/device.
- TLS handshake failure do certificate validity.
- Kerberos clock skew errors.
- Request signature rejected do timestamp/freshness.
- Chênh lệch thời gian giữa issuer và resource server.

### Phân tích lỗi

Khi nhiều request lỗi thời gian:

1. So sánh UTC time và offset của các node liên quan.
2. Kiểm tra node nào phát hành credential và node nào xác minh.
3. Kiểm tra time source, reachability, NTP logs và clock step.
4. So sánh timestamp credential với thời điểm xác minh theo từng node.
5. Kiểm tra leeway/window đang cấu hình trong từng service.
6. Đưa node lệch quá mức ra khỏi traffic nếu cần.
7. Khôi phục đồng bộ, xác minh bằng request thử và theo dõi tỷ lệ lỗi.

Không yêu cầu người dùng reset password hoặc đăng ký lại MFA ngay khi chưa xác định lỗi do credential hay do clock.

## 17. Kiểm thử clock skew

Kiểm thử trong môi trường cô lập hoặc test harness có khả năng mô phỏng clock. Không chỉnh giờ production để thử.

| Trường hợp | Kết quả mong đợi |
|---|---|
| Issuer và verifier đồng bộ | Token hợp lệ được chấp nhận |
| Verifier chạy nhanh hơn trong tolerance | Token được xử lý theo leeway đã định |
| Verifier chạy chậm hơn trong tolerance | Token expiry được xử lý theo leeway đã định |
| Offset vượt tolerance | Credential bị từ chối và có metric/reason code |
| Token chưa đến nbf | Bị từ chối |
| Token đã qua exp | Bị từ chối theo clock policy |
| iat nằm xa trong tương lai | Bị từ chối nếu profile kiểm tra issued-at plausibility |
| Certificate chưa tới notBefore | TLS validation từ chối |
| Certificate đã qua notAfter | TLS validation từ chối |
| TOTP lệch một step | Kết quả theo cửa sổ nhỏ đã cấu hình |
| TOTP lệch nhiều step | Bị từ chối và hướng dẫn sửa clock thiết bị |
| TOTP code đã được dùng lại | Replay protection từ chối nếu policy yêu cầu |
| Kerberos authenticator lệch quá giới hạn | KDC/service từ chối; replay cache vẫn hoạt động |
| Signed request timestamp cũ | Bị từ chối |
| Signed request nonce đã dùng | Bị từ chối hoặc xử lý idempotent theo policy |
| Clock wall time nhảy lùi | Timeout vẫn không tăng ngược; cảnh báo được phát |
| Clock wall time nhảy tiến | Credential/session không bị gia hạn ngoài ý muốn |
| VM suspend rồi resume | Đồng bộ lại và xử lý session/token đúng policy |
| NTP source không khả dụng | Alert; node xử lý theo degraded policy, không tự nới tolerance |
| Hai NTP source bất đồng | Phát hiện outlier và không âm thầm chọn nguồn sai |
| Leap smear khác nhau | Sai lệch được quan sát và nằm trong giới hạn được thiết kế |
| Nhiều node cùng nhận nonce | Chỉ một request được claim nếu nonce phải dùng một lần |
| Audit event từ node lệch giờ | Có node/event ID để điều tra thứ tự nhân quả |

### Bài tập

1. Cho issuer phát JWT có lifetime 5 phút và verifier chạy nhanh hơn 30 giây. Giải thích khi nào token có thể bị từ chối sớm.
2. Cho verifier chạy chậm hơn 60 giây. Phân tích rủi ro khi token đã hết hạn theo issuer nhưng verifier vẫn chấp nhận.
3. Thiết kế TOTP window nhỏ và giải thích trade-off giữa usability và replay exposure.
4. Mô phỏng hai node cùng nhận một signed request có nonce giống nhau; xác định vì sao replay cache phải atomic.
5. Đề xuất dashboard thể hiện offset, synchronization status và authentication failures theo region.

## 18. Checklist thiết kế clock cho authentication

- [ ] Phân biệt wall clock và monotonic clock.
- [ ] Dùng UTC cho protocol timestamp; không dùng local timezone để xác minh credential.
- [ ] Mọi node authentication/resource server có time source được quản lý.
- [ ] NTP/PTP được cấu hình và giám sát; nguồn thời gian có trust controls.
- [ ] Có nhiều nguồn độc lập hoặc cơ chế phát hiện outlier khi phù hợp.
- [ ] Dùng NTS hoặc bảo vệ tương đương khi nền tảng hỗ trợ.
- [ ] Đo offset, jitter và uncertainty thay vì chỉ nhìn giờ hiển thị.
- [ ] JWT kiểm tra exp/nbf và các claim thời gian theo profile.
- [ ] Leeway nhỏ, thống nhất và dựa trên số liệu thực tế.
- [ ] Certificate validity không bị bỏ qua để chữa lỗi clock.
- [ ] TOTP window được giới hạn và có rate limit/replay protection.
- [ ] Kerberos maximum skew và replay cache được giữ đúng policy.
- [ ] Signed request có freshness, nonce và idempotency phù hợp.
- [ ] Session duration dùng monotonic clock khi đo elapsed time.
- [ ] Clock rollback/jump tạo cảnh báo và không tự nới tolerance.
- [ ] Async job và cache expiry có semantics thời gian được tài liệu hóa.
- [ ] Audit lưu UTC, node ID và event/correlation ID; không chỉ dựa vào timestamp để sắp thứ tự.
- [ ] Kiểm thử fast/slow clock, step, suspend/resume, source outage và leap handling.
- [ ] Có quy trình đưa node lệch quá mức ra khỏi traffic và phục hồi đồng bộ.

## Ghi nhớ

Clock skew là sai lệch thời gian giữa các thành phần và có thể làm token, certificate, TOTP, Kerberos, session hoặc signed request bị từ chối sai hoặc được chấp nhận quá lâu. Dùng UTC wall clock cho thời điểm credential; dùng monotonic clock cho duration. Đồng bộ bằng time source được quản lý, giám sát offset và không coi timezone là giải pháp.

Clock tolerance phải nhỏ, thống nhất và dựa trên số liệu. JWT vẫn cần xác minh chữ ký; TOTP và signed request vẫn cần giới hạn replay; certificate validity không được bỏ qua. Khi thời gian không đáng tin, điều tra và phục hồi time service thay vì mở rộng cửa sổ chấp nhận credential.
