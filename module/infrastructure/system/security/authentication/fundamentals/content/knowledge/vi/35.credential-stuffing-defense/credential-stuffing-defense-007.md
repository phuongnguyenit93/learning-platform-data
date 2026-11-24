# Backoff

## 1. Backoff là gì?

**Backoff** là cơ chế buộc một yêu cầu thử lại phải chờ lâu hơn sau những lần thất bại liên tiếp hoặc khi hệ thống nhận thấy dấu hiệu lạm dụng. Trong đăng nhập, backoff làm chậm việc thử password, OTP hoặc các bước xác thực khác, khiến credential stuffing và password guessing tốn thời gian, giảm tốc độ thử và khó mở rộng trên nhiều tài khoản.

Credential stuffing thường dùng username/email và password bị lộ từ dịch vụ khác. Attacker tự động thử các cặp credential này trên nhiều website vì một số người dùng tái sử dụng password. Password spraying thử một password phổ biến trên nhiều tài khoản; brute force thử nhiều password cho một tài khoản. Backoff giúp giảm tốc độ các hành vi này, nhưng cần phối hợp với rate limiting, MFA, phát hiện bot, kiểm tra password đã lộ và giám sát rủi ro.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, backoff là một kiểm soát chống lạm dụng đăng nhập. Nó tác động trực tiếp tới trải nghiệm hợp lệ, khả năng sẵn sàng và quyền truy cập tài khoản. Nếu chỉ khóa một tài khoản sau vài lần sai, attacker có thể cố ý nhập sai để ngăn chủ tài khoản đăng nhập. Vì vậy, thiết kế phải cân bằng giữa làm chậm attacker, tránh account enumeration và ngăn denial of service.

Sau bài học, người học có thể:

- Phân biệt backoff, rate limiting, temporary lockout và account suspension.
- Thiết kế progressive delay và exponential backoff có giới hạn.
- Kết hợp counter theo account, IP, device, network và transaction.
- Xử lý đồng thời và phân tán để không bỏ qua giới hạn.
- Bảo vệ password, OTP, MFA, recovery và reset endpoint.
- Giảm account enumeration và lockout DoS.
- Chọn cách reset/decay counter và xử lý retry công bằng.
- Giám sát credential stuffing và kiểm thử các trường hợp lạm dụng.

## 2. Backoff giải quyết vấn đề gì?

Nếu endpoint đăng nhập chấp nhận hàng nghìn lần thử mỗi phút, attacker có thể thử danh sách credential bị lộ trên quy mô lớn. Ngay cả khi mỗi lần xác minh password có chi phí tính toán cao, hệ thống vẫn có thể bị lạm dụng để dò credential hoặc tiêu tốn CPU.

Backoff thêm chi phí thời gian vào chuỗi thử thất bại. Ví dụ, sau một số lần nhập sai, hệ thống tăng thời gian chờ từ ngắn tới dài. Attacker không thể tiếp tục gửi request với tốc độ không giới hạn; người dùng hợp lệ vẫn có thể đăng nhập sau khi chờ hoặc hoàn tất bước xác minh bổ sung.

Các mục tiêu chính:

- Giảm tốc độ thử password hoặc mã xác minh.
- Làm cho automation quy mô lớn đắt đỏ hơn.
- Tăng thời gian phát hiện và phản ứng của hệ thống.
- Bảo vệ tài nguyên xác thực khỏi tải bất thường.
- Tạo cơ hội chuyển sang MFA, challenge hoặc review theo rủi ro.
- Giảm khả năng attacker thử đi thử lại ngay sau mỗi thất bại.

Backoff không chứng minh người dùng là attacker. Một lần nhập sai có thể do quên password, bàn phím, autofill cũ hoặc lỗi đồng bộ. Vì vậy, không nên áp dụng hình phạt quá mạnh chỉ từ một lỗi đơn lẻ.

## 3. Phân biệt backoff và các kiểm soát liên quan

| Kiểm soát | Cách hoạt động | Mục tiêu |
| --- | --- | --- |
| **Backoff** | Tăng thời gian chờ giữa các lần thử sau thất bại | Giảm tốc độ retry |
| **Rate limiting** | Giới hạn số request trong cửa sổ thời gian | Bảo vệ endpoint và tài nguyên |
| **Temporary lockout** | Tạm từ chối một loại thao tác hoặc principal | Chặn tạm thời khi có dấu hiệu mạnh |
| **Account suspension** | Vô hiệu tài khoản theo quyết định quản trị/rủi ro | Ngăn truy cập trong sự cố hoặc vi phạm |
| **CAPTCHA / bot challenge** | Yêu cầu thêm bằng chứng tương tác hoặc kiểm tra bot | Tăng chi phí automation |
| **MFA / step-up** | Yêu cầu yếu tố hoặc context xác thực bổ sung | Tăng assurance |
| **Credential screening** | Kiểm tra password có phổ biến hoặc đã lộ | Ngăn dùng secret yếu/tái sử dụng |

Backoff và rate limiting bổ sung cho nhau. Backoff có thể áp dụng theo chuỗi thất bại của một account hoặc challenge; rate limit thường giới hạn request theo nguồn hoặc endpoint trong một khoảng thời gian. Không nên xem backoff là thay thế cho rate limit toàn hệ thống.

Temporary lockout có thể cần trong tình huống rủi ro cao, nhưng khóa cứng theo account có thể bị dùng để DoS. Hãy ưu tiên làm chậm, step-up hoặc giới hạn theo nguồn trước khi khóa tài khoản lâu dài.

## 4. Progressive delay và exponential backoff

Một chính sách progressive delay tăng thời gian chờ khi số lần thất bại tăng. Có thể dùng các bậc đơn giản:

| Số lần thất bại liên tiếp trong cửa sổ | Thời gian chờ ví dụ |
| --- | --- |
| 1–2 | Không thêm delay hoặc delay rất nhỏ |
| 3 | 2 giây |
| 4 | 5 giây |
| 5 | 10 giây |
| 6 | 20 giây |
| 7 | 40 giây |
| 8 trở lên | 60 giây hoặc mức trần policy |

Các con số chỉ minh họa. Hệ thống cần chọn ngưỡng dựa trên UX, tải xác thực, khả năng bot và mức rủi ro. Không có một bảng delay đúng cho mọi ứng dụng.

### 4.1. Exponential backoff

Exponential backoff tăng thời gian chờ theo cấp số nhân sau ngưỡng bắt đầu:

~~~text
delay(n) = min(max_delay, base_delay * 2^(n - threshold))
~~~

Trong đó:
- n là số lần thất bại liên tiếp được tính trong cửa sổ.
- threshold là số lần thất bại bắt đầu áp dụng delay.
- base_delay là thời gian chờ ban đầu.
- max_delay là giới hạn trên.

Ví dụ, nếu base_delay là 2 giây và max_delay là 60 giây, delay có thể tăng 2, 4, 8, 16, 32 rồi dừng ở 60 giây. Mục tiêu là tăng chi phí retry nhưng không làm người dùng hợp lệ phải chờ vô hạn.

### 4.2. Jitter

Nếu mọi client đều bị delay cùng một lịch cố định, nhiều request có thể cùng retry tại một thời điểm, tạo ra đợt tải dồn. Jitter thêm một độ ngẫu nhiên nhỏ vào thời gian chờ.

~~~text
scheduled_delay = min(max_delay, base_delay * 2^attempt)
actual_delay = scheduled_delay * random_factor
~~~

random_factor có thể được chọn trong một khoảng hẹp quanh 1 theo policy. Jitter hữu ích cho retry phân tán và giảm đồng bộ hóa request. Với đăng nhập tương tác, cần bảo đảm thông báo thời gian chờ vẫn dễ hiểu; không nên khiến thời gian chờ thay đổi khó giải thích quá nhiều.

### 4.3. Giới hạn trần và thời gian phục hồi

Backoff cần một mức trần. Nếu delay tăng vô hạn, người dùng hợp lệ có thể bị mắc kẹt sau lỗi nhập liệu hoặc attacker có thể gây khóa kéo dài. Khi đạt trần, hệ thống có thể giữ delay tối đa, yêu cầu step-up hoặc chuyển sang recovery có kiểm soát.

Đặt quy tắc phục hồi rõ:
- Counter có thể giảm dần sau một khoảng không có thất bại.
- Đăng nhập thành công có thể reset counter theo account sau khi xác minh đầy đủ.
- Counter theo IP/network có thể không reset chỉ vì một tài khoản đăng nhập thành công.
- Một reset password thành công không nên tự xóa mọi tín hiệu lạm dụng trên các nguồn khác.
- Sự kiện compromise có thể yêu cầu giữ counter hoặc tăng mức giám sát.

## 5. Backoff nên áp dụng theo nhiều chiều

Chỉ đếm thất bại theo account là chưa đủ. Attacker có thể phân tán thử qua nhiều tài khoản hoặc nhiều IP. Chỉ đếm theo IP cũng không đủ vì botnet có nhiều nguồn, trong khi nhiều người dùng hợp lệ có thể dùng chung NAT, VPN hoặc mạng doanh nghiệp.

Một thiết kế thường kết hợp nhiều chiều:

| Dimension | Counter / tín hiệu | Điều cần lưu ý |
| --- | --- | --- |
| **Account candidate** | Số lần thất bại gắn với identifier/principal | Tránh khóa cứng khiến attacker DoS một nạn nhân |
| **Source IP** | Số lần thử từ địa chỉ mạng | NAT/VPN có thể dùng chung bởi nhiều người |
| **Network / ASN** | Mẫu lạm dụng từ dải mạng hoặc nhà cung cấp | Không chặn toàn bộ mạng lớn chỉ từ một tín hiệu |
| **Device/session** | Dấu hiệu từ thiết bị hoặc session đã biết | Fingerprint có thể thay đổi và không phải định danh chắc chắn |
| **Identifier velocity** | Một nguồn thử nhiều identifier trong thời gian ngắn | Phát hiện password spraying và enumeration |
| **Endpoint / tenant** | Tải và lỗi trên endpoint hoặc tenant | Bảo vệ một tenant không làm suy giảm tenant khác |
| **Challenge / factor** | Số lần thử OTP, TOTP hoặc push approval | Counter riêng cho từng challenge và phương thức |

### 5.1. Account-based backoff

Counter theo account giúp phát hiện nhiều lần thử vào cùng một principal. Tuy nhiên, nếu hệ thống trả thông báo “tài khoản bị khóa” hoặc ngăn mọi đăng nhập sau vài lần sai, attacker chỉ cần biết identifier để gây gián đoạn.

Giảm rủi ro bằng cách:
- Dùng delay tăng dần thay vì khóa account lâu ngay lập tức.
- Giữ một đường đăng nhập hợp lệ có step-up hoặc recovery.
- Không tiết lộ account state cho người gọi chưa xác thực.
- Kết hợp account counter với nguồn, device và risk signal.
- Không cho request unauthenticated reset counter hoặc kéo dài lockout vô hạn.
- Có quy trình hỗ trợ khi người dùng thật bị ảnh hưởng.

### 5.2. IP và network-based backoff

Counter theo IP có thể làm chậm bot từ một nguồn. Nhưng IP không đồng nghĩa một người dùng: văn phòng, trường học, nhà mạng di động và VPN có thể gom nhiều người vào cùng địa chỉ công khai.

Không khóa cả IP trong thời gian dài chỉ vì một tài khoản nhập sai nhiều lần. Có thể dùng quota theo endpoint, ngưỡng mềm, challenge hoặc scoring; kết hợp account và device signal để quyết định.

### 5.3. Device và browser signals

Device cookie hoặc dấu hiệu thiết bị có thể giúp phân biệt các phiên, nhưng không nên được coi là bằng chứng danh tính. Cookie có thể bị xóa, thiết bị dùng chung, fingerprint có thể giả mạo và browser privacy có thể thay đổi tín hiệu.

Không cho phép client tự gửi một số lần thử hoặc thời điểm retry rồi server tin giá trị đó. Backoff phải được tính và áp dụng ở server hoặc một lớp kiểm soát tin cậy.

## 6. Tránh account lockout denial of service

Một lỗi thiết kế phổ biến là khóa tài khoản sau N lần sai password. Attacker có thể gửi N lần thử vào email công khai của nạn nhân, khiến nạn nhân không đăng nhập được. Đây là **account lockout DoS**.

Cần phân biệt:
- **Delay của một request/source:** làm chậm nguồn đang thử.
- **Risk state của account:** ghi nhận tài khoản đang bị nhắm tới.
- **Credential failure:** một lần xác minh secret không thành công.
- **Account suspension:** quyết định khóa account có tác động rộng.

Các biện pháp giảm DoS:
1. Không cho unauthenticated attacker khóa vĩnh viễn account chỉ bằng password sai.
2. Dùng progressive delay và giới hạn theo nhiều dimension.
3. Cho phép challenge hoặc step-up an toàn khi account bị nhắm mục tiêu.
4. Giữ thông báo lỗi bên ngoài nhất quán.
5. Không cho attacker đặt lại counter bằng cách tạo request thành công giả hoặc gửi recovery request.
6. Cung cấp kênh khôi phục đã xác minh.
7. Giám sát số account bị nhắm cùng lúc và các đợt lockout bất thường.
8. Cho phép người dùng đăng nhập từ một kênh đã được xác thực mạnh nếu policy cho phép.

Nếu account thực sự có dấu hiệu bị chiếm quyền, có thể tạm đình chỉ hoặc thu hồi session theo incident policy. Quyết định đó cần dựa trên nhiều bằng chứng hơn là một số lần password sai đơn thuần.

## 7. Backoff trong credential stuffing và password spraying

Credential stuffing phân tán một danh sách cặp username/password trên nhiều tài khoản. Password spraying dùng một vài password phổ biến trên nhiều username để tránh ngưỡng account lockout.

Các mẫu hành vi:

| Kiểu tấn công | Dấu hiệu | Backoff phù hợp |
| --- | --- | --- |
| **Brute force một account** | Nhiều password thử trên một identifier | Account counter + source/device limit |
| **Password spraying** | Một hoặc ít password thử trên nhiều account | Source/network velocity + identifier cardinality |
| **Credential stuffing** | Nhiều cặp credential bị lộ, nhiều account và nguồn | Risk scoring, breached-password detection, bot defense, multi-dimensional rate limits |
| **Distributed stuffing** | Nguồn IP thay đổi liên tục | Account/identifier velocity, device signals và global behavior analytics |
| **Enumeration** | Nhiều identifier được dò để tìm account tồn tại | Response chung, lookup limits và monitoring |

Backoff theo account có thể không bắt được password spraying vì mỗi account chỉ bị thử một lần. Backoff theo IP có thể không bắt được distributed stuffing. Do đó cần quan sát ở cấp hệ thống: số identifier duy nhất, tỷ lệ thất bại, độ phân tán nguồn, user-agent pattern và các dấu hiệu automation.

### 7.1. Breached-password screening

Nếu password vừa được người dùng nhập nhưng không đúng, backoff không giúp password yếu trở nên an toàn. Khi tạo hoặc đổi password, kiểm tra password có nằm trong danh sách phổ biến hoặc đã bị lộ theo phương pháp bảo vệ quyền riêng tư phù hợp.

Không gửi password plaintext tới dịch vụ bên ngoài. Nếu dùng dịch vụ kiểm tra breach, tuân theo giao thức bảo vệ được thiết kế cho mục đích đó, hoặc dùng danh sách nội bộ đã được cập nhật.

### 7.2. Bot và automation detection

Có thể kết hợp:
- Request rate và pattern thời gian.
- Header consistency và TLS/client signals.
- JavaScript challenge hoặc CAPTCHA theo rủi ro.
- Device reputation và dấu hiệu automation.
- Mẫu thử credential trên nhiều account.
- Threat intelligence hoặc nguồn abuse đã được kiểm chứng.

Không dùng CAPTCHA như biện pháp duy nhất; bot có thể giải hoặc thuê người giải, trong khi người dùng có nhu cầu accessibility có thể gặp khó khăn.

## 8. Backoff cho password, OTP và MFA

Mỗi factor có đặc tính riêng. Dùng chung một counter cho mọi luồng có thể tạo lỗ hổng hoặc gây khóa không cần thiết.

### 8.1. Password attempts

- Đếm thất bại phía server sau khi xác minh credential.
- Dùng password hashing chuyên dụng và cost phù hợp.
- Giới hạn request trước và trong quá trình hash để tránh CPU exhaustion.
- Áp dụng account/source/network controls.
- Dùng thông báo lỗi không tiết lộ account existence hoặc trạng thái khóa.
- Sau thành công, reset counter account theo policy nhưng vẫn giữ telemetry nguồn.

Password hashing có cost cao giúp chống offline cracking nếu database bị lộ, nhưng attacker có thể lạm dụng endpoint online để khiến server tính hash liên tục. Cần rate limit trước khi thực hiện phép xác minh đắt đỏ, đồng thời không tạo timing oracle dễ dò account.

### 8.2. TOTP và OTP code

OTP có không gian giá trị nhỏ hơn password dài, nên cần giới hạn số lần thử nghiêm ngặt theo challenge và account. Một challenge TOTP/SMS/email có thể có:
- TTL ngắn.
- Số lần nhập tối đa.
- Resend quota riêng.
- Cooldown sau thất bại.
- Ràng buộc với account, purpose và transaction.
- Consume-once khi thành công.
- Hủy challenge cũ khi phát hành challenge mới theo policy.

Không để attacker gửi mã vô hạn trong cùng time window. Với TOTP, xác minh theo time step và cửa sổ lệch nhỏ; không mở rộng time window vô hạn để bù clock drift. Với SMS/email OTP, rate limit cả gửi mã lẫn nhập mã.

### 8.3. Push approval

Backoff cho push cần giới hạn số prompt, tần suất gửi và số lần người dùng từ chối. Nếu có quá nhiều prompt, attacker có thể gây MFA fatigue.

- Chỉ gửi push sau khi có login transaction hợp lệ.
- Hiển thị thông tin đủ để người dùng nhận ra request.
- Dùng number matching hoặc challenge context khi hỗ trợ.
- Áp dụng cooldown sau nhiều lần từ chối hoặc timeout.
- Cho phép người dùng báo cáo prompt không chủ động.
- Không tự động gửi lại push liên tục khi không có phản hồi.

### 8.4. Recovery code và backup factor

Recovery code thường là secret một lần. Cần giới hạn thử, consume atomically và không cho brute force cả bộ mã. Nếu có nhiều mã, cần bảo đảm entropy đủ cao, rate limit theo account và cảnh báo khi sử dụng.

## 9. Backoff cho recovery và password reset

Recovery endpoint cũng có thể bị lạm dụng để dò tài khoản, gửi spam hoặc gây gián đoạn.

Các điểm cần bảo vệ:
- Rate limit yêu cầu reset theo account candidate và source.
- Giới hạn resend email/SMS theo destination.
- Dùng token reset ngẫu nhiên, TTL ngắn và one-time.
- Không trả lời trực tiếp email có tài khoản hay không.
- Giới hạn thử token và challenge.
- Không để yêu cầu reset liên tục làm vô hiệu mọi link hợp lệ mà không có UX rõ.
- Thông báo an toàn cho kênh đã xác minh.
- Sau reset thành công, xử lý session/token và credential cũ theo policy.

Không dùng backoff reset password như cách khóa account hoàn toàn. Attacker có thể spam recovery để làm người dùng mất quyền sử dụng link hoặc bị ngập email. Có thể áp dụng cooldown resend và giữ một token mới nhất có trạng thái rõ, đồng thời cung cấp hướng dẫn an toàn.

## 10. Counter, cửa sổ thời gian và reset policy

Một counter cần có định nghĩa rõ ràng: đếm sự kiện gì, trong cửa sổ nào, được chia sẻ giữa các node ra sao và khi nào được reset.

Các cách phổ biến:

| Chiến lược | Cách tính | Lưu ý |
| --- | --- | --- |
| **Fixed window** | Đếm trong các cửa sổ cố định | Có thể tạo burst ở ranh giới hai cửa sổ |
| **Sliding window** | Đếm trong khoảng thời gian trượt | Chính xác hơn nhưng cần lưu/truy vấn event hoặc cấu trúc phù hợp |
| **Token bucket** | Tích lũy token theo tốc độ; mỗi request tiêu thụ token | Phù hợp quota request, không trực tiếp biểu diễn chuỗi thất bại |
| **Leaky bucket** | Xử lý request theo tốc độ đều hoặc queue | Có thể làm mượt tải, cần tránh queue quá dài |
| **Consecutive failure counter** | Đếm thất bại liên tiếp kể từ thành công hoặc reset | Phù hợp progressive delay nhưng cần expiry/decay |

### 10.1. Sliding window và decay

Một cửa sổ trượt giúp tránh việc attacker gửi nhiều lần ngay trước và sau ranh giới fixed window. Có thể lưu timestamp của các thất bại gần đây hoặc dùng cấu trúc đếm có decay.

Ví dụ policy khái niệm:
- Mỗi thất bại tăng score.
- Sau khoảng không có thất bại, score giảm dần.
- Một đăng nhập thành công đã xác minh có thể reset counter account.
- Các tín hiệu IP/network abuse tiếp tục tồn tại theo cửa sổ riêng.
- Sự kiện compromise giữ trạng thái risk cho tới khi được xử lý.

Không reset mọi counter sau một lần thành công từ cùng IP. Attacker có thể đăng nhập được một tài khoản đã bị chiếm rồi dùng thành công đó để xóa lịch sử lạm dụng của nguồn.

### 10.2. Atomic counter update

Trong hệ thống nhiều instance, hai request có thể cùng đọc counter cũ và cùng ghi giá trị mới, làm mất một lần thất bại. Dùng thao tác atomic tại kho chia sẻ, script transaction hoặc primitive tương đương để tăng counter và xác định delay.

Counter và quyết định cho phép/thử lại cần được phối hợp nhất quán. Nếu một node tính delay nhưng node khác không biết trạng thái, attacker có thể luân phiên request giữa các node để né backoff.

### 10.3. TTL và bounded storage

Không lưu counter vô hạn. Dùng TTL theo cửa sổ và giới hạn số key để tránh attacker tạo hàng triệu identifier giả làm đầy cache. Identifier không tồn tại có thể cần shadow counter để giảm enumeration, nhưng cần bảo vệ key bằng HMAC, TTL và quota để không trở thành nguồn tiêu tốn bộ nhớ.

## 11. Distributed systems và nhiều tầng kiểm soát

Một hệ thống đăng nhập có thể gồm CDN/WAF, API gateway, authentication service, identity store, MFA provider và risk engine. Backoff có thể được áp dụng ở nhiều tầng:

- Edge: giới hạn burst theo IP/network và endpoint.
- Gateway: quota theo route, tenant và client.
- Authentication service: counter theo account candidate, challenge và factor.
- Risk engine: phân tích hành vi phân tán qua nhiều account.
- Identity provider: áp dụng policy đăng nhập và step-up.
- Notification service: giới hạn resend và cảnh báo.

Không để mỗi tầng có một quy tắc mâu thuẫn. Ví dụ edge trả 429 nhưng authentication service vẫn tăng account counter; hoặc gateway cho qua nhưng một node không áp dụng shared counter.

### 11.1. Tránh phụ thuộc một kho counter duy nhất

Nếu Redis/cache dùng cho counter gặp sự cố, hệ thống cần quyết định:
- Fail closed cho endpoint có nguy cơ cao.
- Dùng local conservative limit tạm thời.
- Giảm tốc độ hoặc tạm dừng một số luồng.
- Ghi nhận telemetry để reconciliation sau khi kho phục hồi.

Không mặc định fail-open hoàn toàn, vì attacker có thể chờ kho counter lỗi để thử credential hàng loạt. Cũng không nên làm sập toàn bộ login nếu một dịch vụ phụ trợ không quan trọng bị lỗi. Quyết định phải theo threat model và mức độ ảnh hưởng.

### 11.2. Không dùng sleep để giữ request/thread

Một implementation có thể gọi sleep trong request handler để tạo delay. Nếu nhiều request cùng ngủ, attacker có thể chiếm thread/connection và gây DoS.

Tốt hơn:
- Trả response có thời gian retry phù hợp khi API contract cho phép.
- Dùng scheduler hoặc queue cho flow bất đồng bộ nếu cần.
- Enforce thời gian chờ phía server bằng trạng thái/counter, không dựa vào việc giữ thread.
- Giới hạn số request đang xử lý và timeout.
- Không tin client chỉ vì nó chờ đủ thời gian; server phải kiểm tra lại.

Header Retry-After có thể giúp client hợp lệ biết thời điểm thử lại trong API rate limit. Với login response cần tránh tiết lộ account state; nội dung và status code phải nhất quán theo policy.

## 12. Trải nghiệm người dùng và phản hồi lỗi

Thông báo backoff cần rõ ràng nhưng không tiết lộ thông tin nội bộ hoặc tạo account enumeration.

Một số nguyên tắc:
- Dùng thông báo chung cho identifier không tồn tại và credential sai.
- Khi áp dụng cooldown, giải thích rằng có thể thử lại sau một khoảng thời gian hoặc dùng phương thức recovery an toàn.
- Không hiển thị số lần thất bại chính xác nếu thông tin đó hỗ trợ attacker.
- Không tiết lộ ngưỡng lockout hoặc trạng thái risk engine.
- Cung cấp accessibility và hỗ trợ người dùng bị khóa do lỗi thiết bị.
- Tránh yêu cầu CAPTCHA liên tục cho người dùng hợp lệ.
- Cho phép phương thức xác thực thay thế đã được thiết lập và đủ tin cậy.

Không nói “email này đã bị khóa” cho một người chưa được xác thực. Có thể hiển thị thông điệp như “Không thể hoàn tất đăng nhập ngay lúc này. Hãy thử lại sau hoặc dùng quy trình khôi phục tài khoản nếu bạn cần trợ giúp.” Nội dung cụ thể phụ thuộc sản phẩm và policy.

### 12.1. Thông tin Retry-After

Với API công khai, 429 Too Many Requests và Retry-After có thể phù hợp khi giới hạn request theo client/source. Nhưng nếu delay chỉ áp dụng cho một account candidate, phản hồi riêng có thể làm lộ trạng thái tài khoản.

Có thể trả thông điệp chung và thực thi delay server-side; không nhất thiết phải công bố counter hoặc delay chính xác. Client không được phép tự bỏ qua backoff bằng cách đổi header hoặc mở tab mới.

## 13. Logging, metrics và phát hiện credential stuffing

Backoff chỉ hữu ích nếu hệ thống đo được hiệu quả và phát hiện hành vi vượt qua từng lớp.

Nên theo dõi:
- Số lần thất bại theo endpoint, tenant, account candidate và source.
- Tỷ lệ thất bại trên số lần đăng nhập.
- Số identifier duy nhất được thử từ một nguồn.
- Số nguồn thử cùng một identifier.
- Tần suất retry sau delay.
- Số lần OTP resend và verification failure.
- Số challenge bị từ chối hoặc timeout.
- Số tài khoản bị nhắm đồng thời.
- Tỷ lệ người dùng hợp lệ bị delay/challenge.
- Tỷ lệ đăng nhập thành công sau backoff.
- Tỷ lệ request bị rate limit ở từng tầng.

Không log password, OTP, recovery code, activation token, cookie hoặc access token. Identifier trong log nên được mask hoặc dùng keyed pseudonymous reference phù hợp. Hạn chế quyền truy cập dashboard vì dữ liệu đăng nhập có thể tiết lộ danh sách người dùng.

### 13.1. Phân biệt tấn công với lỗi người dùng

Một người có thể nhập sai nhiều lần do password manager lưu secret cũ. Hệ thống cần phân biệt hành vi lặp từ một thiết bị/session đã biết với pattern phân tán, nhiều identifier hoặc nhiều nguồn bất thường.

Không tự động kết luận một người là attacker chỉ vì một chỉ số. Kết hợp nhiều tín hiệu, theo dõi false positive và có quy trình hỗ trợ.

### 13.2. Alert và response

Khi phát hiện credential stuffing:
1. Tăng giám sát trên endpoint/tenant bị ảnh hưởng.
2. Áp dụng rate limit và backoff theo dimension phù hợp.
3. Yêu cầu challenge/step-up theo risk policy.
4. Chặn nguồn rõ ràng độc hại nếu có đủ bằng chứng.
5. Kiểm tra account takeover và session bất thường.
6. Thu hồi session/token cho tài khoản bị xác định compromise.
7. Thông báo cho người dùng bị ảnh hưởng qua kênh đã xác minh.
8. Cập nhật password screening hoặc threat intelligence.
9. Theo dõi tỷ lệ false positive và tác động tới người dùng hợp lệ.

## 14. Ví dụ policy backoff

Một dịch vụ web có thể dùng policy minh họa sau:

- Ở edge, giới hạn burst request theo IP và endpoint.
- Với account candidate, bắt đầu progressive delay sau một số lần password thất bại trong cửa sổ ngắn.
- Delay tăng theo exponential backoff nhưng có mức trần.
- Jitter nhẹ để tránh đồng bộ retry.
- Nếu một IP thử nhiều identifier, áp dụng network-level challenge hoặc throttle.
- Nếu một identifier bị thử từ nhiều IP, tăng risk score và có thể yêu cầu step-up.
- Sau login thành công đã xác minh, reset consecutive-failure counter của account theo policy.
- Không reset network abuse counter chỉ vì một account đăng nhập thành công.
- Với OTP, dùng counter và TTL riêng cho từng challenge, cộng thêm quota gửi mã.
- Với recovery, dùng response chung, resend cooldown và token one-time.
- Không khóa vĩnh viễn account chỉ vì password sai.
- Giám sát false positive, login completion và abuse rate.

~~~mermaid
flowchart TD
    A[Login request] --> B[Edge rate limit]
    B --> C[Validate input + normalize identifier]
    C --> D[Load risk counters]
    D --> E{Source / account risk?}
    E -- High --> F[Throttle / challenge / deny by policy]
    E -- Normal --> G[Verify credential]
    G --> H{Success?}
    H -- Yes --> I[Create session after policy checks]
    I --> J[Reset account failure counter as policy allows]
    H -- No --> K[Atomic failure counter update]
    K --> L[Calculate capped backoff + jitter]
    L --> M[Generic response; enforce retry time server-side]
    F --> N[Audit + monitor]
    M --> N
    J --> N
~~~

### 14.1. Pseudocode

~~~text
function authenticate(request):
    sourceDecision = edgeLimiter.check(request.source, request.endpoint)
    if sourceDecision.denied:
        return genericThrottledResponse()

    identifier = normalizeIdentifier(request.identifier)
    accountKey = keyedReference(identifier, tenantContext(request))
    sourceKey = sourceReference(request.source)
    deviceKey = trustedDeviceSignal(request)

    decision = sharedRiskStore.evaluate(
        accountKey = accountKey,
        sourceKey = sourceKey,
        deviceKey = deviceKey,
        endpoint = "login"
    )

    if decision.requiresChallenge:
        return genericChallengeResponse()

    if decision.retryNotBefore > serverNow():
        return genericRetryResponse()

    principal = lookupPrincipal(identifier, tenantContext(request))
    verifier = principal.passwordVerifier if principal exists else fakeVerifier

    valid = verifyPassword(request.password, verifier)

    if not valid or principal is absent or principal is disabled:
        failure = sharedRiskStore.recordFailureAtomically(
            accountKey, sourceKey, deviceKey
        )
        delay = cappedExponentialBackoff(failure.count) + boundedJitter()
        sharedRiskStore.setRetryNotBefore(accountKey, serverNow() + delay)
        auditSafeFailure(failure.reasonCode)
        return genericLoginFailure()

    if not policyAllowsAuthentication(principal, request):
        return genericLoginFailure()

    sharedRiskStore.resetAccountFailureCounter(principal.id)
    session = createSession(principal)
    auditSafeSuccess(principal.id)
    return success(session)
~~~

Pseudocode chỉ mô tả luồng. Implementation cần xử lý timing differences, fake verifier, disabled account, MFA, password hashing, transaction atomic, race, retry semantics và distributed consistency. Không trả nội dung khác nhau để tiết lộ principal có tồn tại hay không.

## 15. Kiểm thử backoff

| Test case | Kết quả mong đợi |
| --- | --- |
| Một lần nhập sai | Không gây lockout quá mức |
| Nhiều lần sai cùng account | Delay tăng theo policy và có mức trần |
| Nhiều account từ một IP | Source/network controls phát hiện velocity |
| Một account từ nhiều IP | Account risk tăng mà không lộ trạng thái |
| Password spraying | Phát hiện một nguồn thử nhiều identifier |
| Distributed credential stuffing | Risk analytics phát hiện mẫu phân tán |
| Request đồng thời trên nhiều node | Counter không mất update và delay được áp dụng nhất quán |
| Retry ngay trước retryNotBefore | Server từ chối hoặc throttle |
| Client đổi IP | Account/identifier controls vẫn có tác dụng |
| Nhiều người dùng chung NAT | Không khóa toàn bộ người dùng hợp lệ |
| Account không tồn tại | Phản hồi không tiết lộ trạng thái |
| OTP nhập sai liên tiếp | Challenge counter và cooldown hoạt động |
| OTP resend liên tục | Resend quota/cooldown được áp dụng |
| Push bị từ chối nhiều lần | Prompt throttle và risk policy kích hoạt |
| Recovery request spam | Response chung, resend cooldown và audit |
| Login thành công | Reset account counter theo policy, không xóa network abuse history |
| Reset password | Session/token và counter được xử lý theo policy |
| Counter store tạm lỗi | Fallback theo threat model, không fail-open tùy tiện |
| Attacker tạo nhiều identifier giả | Shadow counter có TTL và bounded storage |
| Thread exhaustion test | Backoff không giữ hàng loạt request thread bằng sleep |
| Audit/log inspection | Không có password, OTP, token hoặc identifier thô không cần thiết |
| Người dùng accessibility | Có phương thức challenge thay thế phù hợp |
| Lockout DoS simulation | Attacker không thể khóa vĩnh viễn account nạn nhân chỉ bằng request sai |

### 15.1. Đo false positive

Một policy backoff tốt phải đo cả hiệu quả chống abuse và tác động lên người dùng hợp lệ. Theo dõi:
- Tỷ lệ login hợp lệ bị delay.
- Tỷ lệ người dùng phải qua challenge nhiều lần.
- Tỷ lệ support ticket liên quan tới lockout.
- Tỷ lệ tài khoản bị attacker nhắm nhưng chủ tài khoản vẫn đăng nhập được an toàn.
- Tỷ lệ abuse tiếp tục sau khi backoff được áp dụng.

Nếu false positive cao, xem lại dimension, ngưỡng và cách kết hợp tín hiệu. Không chỉ tăng delay cho tất cả người dùng.

## 16. Checklist review

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Backoff có mục tiêu rõ? | Password guessing, stuffing, OTP abuse được xác định |
| Có phân biệt backoff và rate limit? | Counter và quota có ý nghĩa riêng |
| Delay có tăng dần và có trần? | Exponential/progressive policy có max delay |
| Có jitter khi phù hợp? | Tránh retry đồng bộ |
| Counter theo nhiều dimension? | Account, source, network, device, challenge |
| Có tránh lockout DoS? | Không khóa vĩnh viễn chỉ từ unauthenticated failures |
| Enumeration được giảm? | Phản hồi ngoài nhất quán và timing được xem xét |
| Counter phân tán có atomic? | Nhiều node không thể né hoặc mất update |
| Có TTL/bounded storage? | Shadow counter không làm cạn bộ nhớ |
| Password hash được bảo vệ? | Hash chuyên dụng và rate limit trước chi phí đắt |
| OTP/MFA có quota riêng? | Challenge TTL, attempt limit và resend cooldown |
| Recovery được bảo vệ? | Token one-time, generic response và rate limit |
| Reset counter có đúng? | Thành công account không xóa abuse history nguồn |
| Không giữ thread bằng sleep? | Server-side retry enforcement và timeout |
| Failover có policy? | Counter store lỗi không mặc định fail-open |
| Metrics và alert có đủ? | Detect spraying, stuffing, distributed abuse và false positive |
| Log không lộ secret? | Không ghi password, OTP, token hoặc cookie |
| Có kiểm thử DoS và UX? | Nhiều node, NAT, recovery và accessibility được test |

### Tình huống tự kiểm tra

**Tình huống 1:** Một tài khoản bị nhập sai password nhiều lần. Có nên khóa tài khoản đó trong 24 giờ ngay lập tức?

**Trả lời:** Không mặc nhiên. Điều đó cho phép attacker gây lockout DoS. Nên dùng backoff có trần, giới hạn theo nguồn, step-up và recovery an toàn theo risk policy.

**Tình huống 2:** Một IP thử một password trên 500 tài khoản, mỗi tài khoản chỉ một lần. Account counter có phát hiện tốt không?

**Trả lời:** Không. Cần source/network velocity và phát hiện số identifier duy nhất để nhận diện password spraying.

**Tình huống 3:** Attacker phân tán credential stuffing qua hàng nghìn IP. IP rate limit đơn lẻ có đủ không?

**Trả lời:** Không. Kết hợp account/identifier velocity, device signals, risk analytics, breached credential screening và bot controls.

**Tình huống 4:** Hai server cùng xử lý lần thất bại thứ tư và đều đọc counter bằng 3. Nếu cập nhật không atomic, điều gì có thể xảy ra?

**Trả lời:** Một lần tăng có thể bị mất, khiến backoff yếu hơn. Cần atomic increment/transaction trong kho chia sẻ.

**Tình huống 5:** Người dùng nhập sai TOTP liên tục. Có thể dùng cùng counter với password không?

**Trả lời:** Nên có counter riêng theo challenge/factor và giới hạn resend. TOTP có TTL và không gian mã khác password; dùng chung có thể làm policy sai hoặc khó phát hiện abuse.

**Tình huống 6:** Một người dùng đăng nhập thành công từ IP đang bị lạm dụng. Có nên xóa toàn bộ counter của IP đó không?

**Trả lời:** Không. Có thể reset counter thất bại của account đã xác minh theo policy, nhưng network abuse history cần được giữ độc lập.

**Tình huống 7:** Backoff được triển khai bằng sleep 60 giây trong mỗi request. Có an toàn không?

**Trả lời:** Không. Nhiều request có thể giữ cạn thread và connection. Hãy thực thi retry time ở server bằng state/counter, timeout và quota mà không giữ thread ngủ.

## 17. Ghi nhớ

**Backoff làm chậm chuỗi thử xác thực thất bại để tăng chi phí của credential stuffing, password spraying và guessing.** Một chính sách hiệu quả dùng progressive hoặc exponential delay có giới hạn, jitter khi phù hợp và counter theo nhiều chiều. Nó phối hợp với rate limiting, MFA, bot detection, password screening và giám sát.

Thiết kế phải tránh khóa cứng account để attacker gây DoS, không tiết lộ account existence, xử lý counter nguyên tử trên nhiều node và có TTL/bounded storage. Password, OTP, push và recovery cần quota riêng. Server phải thực thi thời gian retry, không tin client và không giữ thread bằng sleep. Đo cả abuse reduction lẫn false positive để bảo vệ người dùng hợp lệ và khả năng sẵn sàng của dịch vụ.
