# Chọn thời hạn dựa trên rủi ro và yêu cầu trải nghiệm

Thời hạn token quyết định một credential bị đánh cắp hoặc sử dụng sai có thể tiếp tục được chấp nhận trong bao lâu, đồng thời ảnh hưởng đến số lần người dùng phải xác thực lại, độ trễ khi làm mới token và khả năng vận hành của hệ thống. Token quá dài làm tăng cửa sổ lạm dụng; token quá ngắn có thể khiến ứng dụng liên tục refresh, gián đoạn phiên làm việc hoặc phụ thuộc quá nhiều vào dịch vụ cấp token.

Bài này thuộc chương **Vòng đời token** của module **Security - JSON Web Token (JWT)**. Nội dung áp dụng cho bảo mật JWT nói chung, độc lập ngôn ngữ lập trình, nền tảng và framework.

## 1. Mục tiêu và nguyên tắc ra quyết định

Sau bài học, người đọc có thể:

1. Xác định các yếu tố bảo mật và trải nghiệm ảnh hưởng đến thời hạn token.
2. Phân biệt thời hạn access token, refresh token, ID token và phiên đăng nhập.
3. Thiết kế access-token lifetime, refresh-token lifetime, idle timeout và absolute session lifetime.
4. Hiểu vai trò của `exp`, `iat`, `nbf` và clock skew trong JWT.
5. Chọn chính sách refresh, rotation, revocation và re-authentication phù hợp.
6. Điều chỉnh thời hạn theo loại client, mức độ nhạy cảm của tài nguyên và khả năng phát hiện sự cố.
7. Đánh giá trade-off bằng tình huống, chỉ số và kiểm thử thay vì chọn một con số cố định cho mọi token.

**Nguyên tắc cốt lõi:** thời hạn nên là khoảng thời gian tối đa mà hệ thống chấp nhận rủi ro một credential có thể bị lạm dụng, trong giới hạn trải nghiệm và vận hành đã được xác định. Không có một TTL đúng cho mọi hệ thống.

## 2. Thời hạn token ảnh hưởng đến điều gì?

Thời hạn token tạo ra trade-off giữa bảo mật, trải nghiệm và vận hành.

| Khi TTL dài hơn | Khi TTL ngắn hơn |
| --- | --- |
| Ít lần refresh hoặc xác thực lại hơn. | Cửa sổ sử dụng token bị đánh cắp ngắn hơn. |
| Ít request đến authorization server hơn. | Thay đổi quyền hoặc chính sách có thể được phản ánh sớm hơn khi token mới được cấp. |
| Ứng dụng có thể tiếp tục hoạt động lâu hơn khi authorization server gián đoạn. | Phụ thuộc nhiều hơn vào refresh flow và availability của authorization server. |
| Token bị lộ có thể bị replay lâu hơn. | Tăng số lần refresh, khả năng race condition và lỗi đồng bộ client. |
| Quyền cũ có thể tồn tại lâu sau khi user bị khóa hoặc scope bị thu hồi. | Tăng nguy cơ gián đoạn nếu refresh token hết hạn, bị thu hồi hoặc không thể làm mới. |

TTL không phải biện pháp duy nhất để kiểm soát rủi ro. Khả năng thu hồi, sender-constraining, phát hiện hành vi bất thường, giới hạn audience/scope và yêu cầu xác thực lại cho hành động nhạy cảm đều ảnh hưởng đến quyết định.

## 3. Xác định threat model trước khi chọn TTL

Trước khi chọn con số, cần trả lời:

- Token được lưu ở đâu: memory, browser storage, cookie, mobile secure storage hay workload secret store?
- Ai có thể lấy được token nếu client, thiết bị hoặc máy chủ bị xâm nhập?
- Token là bearer token hay được ràng buộc với client/khóa của người gửi?
- Token có quyền truy cập tài nguyên nào và phạm vi ảnh hưởng lớn đến đâu?
- Có thể phát hiện token bị đánh cắp hoặc sử dụng bất thường nhanh đến mức nào?
- Có thể revoke token, session, refresh-token family hoặc key ngay lập tức không?
- Hệ thống có hỗ trợ re-authentication hoặc step-up authentication không?
- Người dùng cần duy trì công việc trong bao lâu và có thể chấp nhận gián đoạn nào?
- Authorization server và dependency refresh có mức availability ra sao?

### 3.1. Những yếu tố làm tăng rủi ro

- Token có scope rộng, audience lớn hoặc quyền quản trị.
- Token được dùng từ nhiều thiết bị hoặc nhiều mạng không tin cậy.
- Token được lưu ở môi trường có nguy cơ XSS, malware, log leakage hoặc backup không được bảo vệ.
- Hệ thống không có revocation hoặc phát hiện bất thường.
- Token có thể thực hiện giao dịch không thể đảo ngược.
- Người dùng có quyền truy cập dữ liệu nhạy cảm hoặc nhiều tenant.
- Token được chia sẻ giữa nhiều service hoặc nhiều ứng dụng.

### 3.2. Những yếu tố ảnh hưởng đến trải nghiệm

- Phiên làm việc điển hình kéo dài bao lâu?
- Ứng dụng có thao tác dài, upload, chỉnh sửa hoặc giao dịch đang chờ không?
- Người dùng có thể xác thực lại nhanh và an toàn không?
- Client có thể refresh trong nền khi không có tương tác không?
- Thiết bị có thể offline hoặc mạng không ổn định trong thời gian dài không?
- Có nhiều tab hoặc nhiều tiến trình cùng refresh một session không?

Không nên để yêu cầu “người dùng không bao giờ phải đăng nhập lại” tự động quyết định TTL. Hãy xác định trải nghiệm mong muốn, sau đó chọn cơ chế duy trì phiên có kiểm soát.

## 4. Phân biệt các loại thời hạn

Một hệ thống có thể có nhiều mốc hết hạn độc lập:

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Access token lifetime** | Khoảng thời gian resource server chấp nhận access token. |
| **Refresh token lifetime** | Khoảng thời gian client có thể dùng refresh token để xin token mới, tùy policy. |
| **ID token lifetime** | Khoảng thời gian ID Token có giá trị trong ngữ cảnh xác thực của client. Không dùng nó thay access token. |
| **Idle timeout** | Thời gian tối đa phiên không có hoạt động được công nhận trước khi phải xác thực lại. |
| **Absolute session lifetime** | Tổng thời gian tối đa của phiên, kể cả khi người dùng vẫn hoạt động. |
| **Maximum token age** | Tuổi tối đa được chấp nhận tính từ thời điểm phát hành, có thể được kiểm tra bằng `iat` và policy. |
| **Re-authentication interval** | Khoảng thời gian tối đa trước khi yêu cầu người dùng xác thực lại hoặc step-up. |
| **Key acceptance window** | Khoảng thời gian verifier còn tin public key cũ để xác minh token đã phát hành trước đó. |

Các mốc này không đồng nghĩa. Ví dụ, refresh token còn hạn không có nghĩa access token cũ còn hạn; session còn hoạt động cũng không có nghĩa mọi token từng cấp cho session đó đều phải được chấp nhận.

## 5. Access token: thời hạn ngắn theo phạm vi và rủi ro

Access token thường được gửi đến resource server để truy cập API. Nếu là bearer token, bên nắm token có thể sử dụng nó trong phạm vi audience, scope và thời hạn mà server chấp nhận.

Khi chọn access-token lifetime, cân nhắc:

- Mức độ nhạy cảm của API và dữ liệu.
- Scope và audience có rộng hay hẹp.
- Nơi lưu token và nguy cơ bị lấy cắp.
- Có sender-constraining như DPoP hoặc mTLS hay không.
- Khả năng refresh nền và availability của authorization server.
- Mức độ nhanh cần thiết để quyền mới hoặc việc khóa tài khoản có hiệu lực.
- Độ trễ và tải do refresh trên quy mô toàn hệ thống.

Với API có quyền cao hoặc dữ liệu nhạy cảm, access token thường nên có lifetime ngắn hơn và scope hẹp hơn. Với một tác vụ ít nhạy cảm, thời gian xử lý dài hoặc môi trường kết nối không ổn định, có thể cần cân bằng khác. Quyết định phải dựa trên threat model và khả năng kiểm soát thực tế.

### 5.1. TTL ngắn không tự bảo đảm an toàn

Token 5 phút vẫn có thể bị lạm dụng trong 5 phút nếu attacker lấy được nó ngay sau khi phát hành. Nếu hệ thống không có revocation, giới hạn quyền hoặc phát hiện replay, TTL ngắn chỉ giới hạn một phần thời gian.

Ngược lại, TTL rất ngắn có thể tạo nhiều refresh request, khiến authorization server thành điểm phụ thuộc lớn và làm tăng rủi ro lỗi đồng thời. TTL phải đi cùng refresh strategy, retry policy và rate limiting.

### 5.2. Không kéo dài access token bằng cách sửa `exp`

Client không được tự thay `exp`, `iat` hoặc claims trong JWT để kéo dài thời hạn. Việc sửa payload làm chữ ký không còn hợp lệ. Chỉ issuer được phép phát hành token mới sau khi xác minh refresh credential và áp dụng policy hiện hành.

## 6. Refresh token: thời hạn dài hơn nhưng phải kiểm soát chặt

Refresh token cho phép client xin access token mới mà không yêu cầu người dùng đăng nhập lại ở mọi lần access token hết hạn. Refresh token thường có giá trị cao hơn access token vì nó có thể tạo ra nhiều access token trong tương lai.

Refresh token không nhất thiết phải là JWT. Một chuỗi opaque ngẫu nhiên được lưu và quản lý phía authorization server thường giúp thu hồi, rotation và phát hiện reuse dễ hơn. Nếu refresh token là JWT, vẫn cần cơ chế trạng thái hoặc policy bổ sung khi muốn revoke/rotate từng token hoặc session.

Khi chọn refresh-token lifetime, cân nhắc:

- Mức độ bảo vệ nơi lưu refresh token.
- Client có phải public client hay confidential client.
- Thiết bị có khóa bảo mật phần cứng hoặc secure storage không.
- Có refresh-token rotation và reuse detection không.
- Có idle expiration và absolute expiration không.
- Có thể revoke token family khi mất thiết bị hoặc nghi ngờ compromise không.
- Người dùng có thể re-authenticate hoặc khôi phục tài khoản như thế nào.

Không nên chỉ đặt refresh token “rất dài” để đạt trải nghiệm lâu dài. Thời hạn dài cần đi kèm bảo vệ lưu trữ, rotation, giới hạn thiết bị/client và khả năng thu hồi.

## 7. Idle lifetime và absolute lifetime

Hai giới hạn này giải quyết hai rủi ro khác nhau.

### 7.1. Idle timeout

Idle timeout giới hạn thời gian phiên không có hoạt động được xem là hợp lệ. Khi người dùng không sử dụng ứng dụng trong khoảng thời gian quy định, refresh credential hoặc session cần hết hiệu lực.

Chỉ cập nhật idle timer dựa trên hoạt động có ý nghĩa và đã được xác thực. Không để một background polling vô hạn tự động giữ phiên sống mãi nếu đó không phải ý định policy.

### 7.2. Absolute lifetime

Absolute lifetime giới hạn tổng thời gian phiên từ lúc được tạo hoặc xác thực gần nhất theo policy. Hoạt động liên tục hoặc refresh access token không được tự động kéo dài giới hạn này vô hạn.

Ví dụ:

~~~text
session_created_at = 09:00
idle_timeout       = 30 minutes
absolute_lifetime  = 8 hours

last_meaningful_activity = 10:15
idle_expiry               = 10:45
absolute_expiry           = 17:00
effective_session_expiry  = min(idle_expiry, absolute_expiry)
~~~

Các con số chỉ minh họa cách tính, không phải khuyến nghị chung. Khi phiên hết hạn theo bất kỳ giới hạn nào, client cần thực hiện lại authentication flow theo policy.

### 7.3. Không để refresh biến absolute lifetime thành sliding vô hạn

Nếu mỗi lần refresh đều đặt lại cả idle và absolute lifetime, một refresh token có thể duy trì quyền truy cập vô hạn khi client hoạt động định kỳ. Hãy giữ mốc absolute expiry gốc hoặc yêu cầu re-authentication sau khoảng thời gian tối đa.

## 8. JWT claims liên quan đến thời hạn

JWT Registered Claims cung cấp các mốc thời gian thường dùng:

| Claim | Ý nghĩa | Cách dùng trong policy |
| --- | --- | --- |
| `exp` | Expiration Time | Token không được chấp nhận tại hoặc sau thời điểm hết hạn. |
| `iat` | Issued At | Thời điểm phát hành; có thể dùng để kiểm tra token age hoặc phát hiện thời gian bất thường. |
| `nbf` | Not Before | Token không được chấp nhận trước thời điểm này. |

Các claim thời gian trong JWT dùng NumericDate, biểu diễn số giây từ Unix epoch theo UTC, có thể có phần thập phân theo chuẩn. Không diễn giải chúng như chuỗi ngày giờ local.

### 8.1. `exp` là giới hạn chấp nhận

Theo RFC 7519, token không được chấp nhận tại hoặc sau thời điểm hết hạn. Verifier nên có policy yêu cầu `exp` đối với loại token cần thời hạn hữu hạn, dù chuẩn JWT tổng quát không bắt mọi JWT đều phải có claim này.

Nếu token profile yêu cầu `exp`, thiếu claim phải bị từ chối. Không tự gán một expiration mặc định dài ở verifier khi issuer quên phát hành `exp`.

### 8.2. `iat` không thay thế `exp`

`iat` cho biết thời điểm phát hành, không tự tạo ra thời hạn. Một token có `iat` nhưng không có `exp` vẫn có thể không có giới hạn hết hạn nếu verifier không có policy maximum age.

Nếu cần giới hạn tuổi tối đa:

~~~text
token_age = current_time - iat
accept only if token_age <= max_token_age
~~~

Phải kiểm tra `iat` hợp lệ, không ở tương lai quá mức cho phép và không bị chấp nhận nếu vượt maximum age. `max_token_age` là policy riêng, không phải ý nghĩa mặc định của claim.

### 8.3. `nbf` và thời gian bắt đầu hiệu lực

`nbf` có thể hữu ích khi token được phát hành trước một thời điểm bắt đầu sử dụng. Không dùng `nbf` để kéo dài token hoặc thay thế `exp`. Verifier cần từ chối token khi thời gian hiện tại còn trước `nbf`, có xét clock skew nhỏ theo policy.

## 9. Clock skew và đồng bộ thời gian

Các hệ thống phân tán có thể lệch đồng hồ. Nếu issuer và verifier dùng thời gian khác nhau, token vừa phát hành hoặc vừa hết hạn có thể bị từ chối ngoài dự kiến.

Một số verifier hỗ trợ leeway/clock skew:

- Có thể cho phép sai lệch nhỏ khi kiểm tra `exp` và `nbf`.
- Leeway phải được giới hạn và cấu hình thống nhất.
- Không dùng leeway lớn để bù cho đồng hồ hệ thống sai.
- Đồng bộ thời gian máy chủ bằng nguồn thời gian đáng tin cậy.
- Theo dõi clock drift và cảnh báo khi vượt ngưỡng.

Leeway làm tăng thời gian token được chấp nhận. Nếu `exp` là 10:00 và verifier cho phép leeway 60 giây, token có thể được chấp nhận đến khoảng 10:01 theo cách triển khai. Vì vậy, phải tính leeway vào cửa sổ rủi ro và rotation.

## 10. Cách xây dựng chính sách TTL

Một quy trình thực tế:

1. Phân loại token theo profile và audience.
2. Xác định hậu quả khi token bị lộ hoặc replay.
3. Đo thời gian xử lý tác vụ và phiên làm việc điển hình.
4. Xác định mức gián đoạn chấp nhận được khi refresh service lỗi.
5. Đặt giới hạn tối đa về access-token lifetime.
6. Thiết kế refresh token, idle timeout, absolute lifetime và re-authentication.
7. Tính clock skew, cache, retry và thời gian thu hồi.
8. Kiểm thử tải, refresh concurrency và sự cố dependency.
9. Theo dõi metrics thực tế rồi điều chỉnh theo quy trình change management.

Có thể biểu diễn ràng buộc ở mức khái niệm:

~~~text
access_token_ttl <= maximum_exposure_window
refresh_token_ttl <= approved_session_lifetime
session_expiry = min(idle_expiry, absolute_expiry)
~~~

`maximum_exposure_window` và `approved_session_lifetime` phải được xác định từ risk assessment. Không lấy các biểu thức này làm công thức tự động sinh ra con số nếu chưa có dữ liệu và policy.

### 10.1. Ma trận quyết định định tính

| Rủi ro / yêu cầu | Hướng điều chỉnh |
| --- | --- |
| Quyền quản trị hoặc giao dịch giá trị cao | Giảm access TTL, scope hẹp, step-up/re-auth cho hành động nhạy cảm. |
| Dữ liệu ít nhạy cảm, tác vụ dài | Có thể cân nhắc access TTL dài hơn trong giới hạn policy và có refresh/revocation phù hợp. |
| Thiết bị công cộng hoặc dễ bị mất | Session ngắn hơn, idle timeout nghiêm ngặt, refresh credential dễ revoke. |
| Thiết bị cá nhân có secure storage | Có thể cải thiện trải nghiệm bằng refresh flow, nhưng vẫn cần absolute expiry và rotation. |
| Client offline lâu | Cân nhắc khả năng re-auth, queued operation và giới hạn hành động khi offline; không mặc định tăng TTL vô hạn. |
| Không có revocation hiệu quả | Giảm lifetime và phạm vi token; cải thiện cơ chế revoke là ưu tiên kiến trúc. |
| Có refresh rotation và reuse detection | Có thể hỗ trợ phiên dài hơn trong policy, nhưng vẫn cần absolute expiry và bảo vệ refresh token. |

## 11. Ví dụ lựa chọn theo từng loại client

### 11.1. Trình duyệt web

Đặc điểm:

- Cookie có thể được gửi tự động.
- XSS có thể thao túng trang và thực hiện request bằng quyền người dùng, dù cookie `HttpOnly`.
- Browser có thể bị đóng, mở nhiều tab hoặc chạy background.
- Cần cân nhắc CSRF nếu credential nằm trong cookie.

Hướng thiết kế:

- Access token có lifetime ngắn hoặc giữ trong server-side session tùy kiến trúc.
- Refresh/session credential được bảo vệ bằng cookie attributes và CSRF defenses.
- Có idle timeout và absolute session lifetime.
- Yêu cầu re-authentication cho thay đổi mật khẩu, thay đổi yếu tố xác thực hoặc giao dịch nhạy cảm.
- Không coi background activity vô hạn là hoạt động người dùng.

### 11.2. Ứng dụng di động

Đặc điểm:

- Thiết bị có thể offline hoặc mất kết nối.
- Refresh token có thể được lưu trong secure storage của hệ điều hành.
- Thiết bị có thể bị mất, root/jailbreak hoặc backup không an toàn.

Hướng thiết kế:

- Access token ngắn để giảm cửa sổ replay.
- Refresh token có rotation, reuse detection và ràng buộc client khi phù hợp.
- Lưu refresh token trong vùng lưu trữ bảo mật được hệ điều hành cung cấp.
- Có khả năng revoke theo thiết bị/session khi mất máy.
- Có absolute lifetime và yêu cầu đăng nhập lại sau thời gian tối đa.

Secure storage làm giảm rủi ro nhưng không biến thiết bị thành môi trường tuyệt đối tin cậy.

### 11.3. Service-to-service

Đặc điểm:

- Không có người dùng tương tác thường xuyên.
- Workload có thể xin token mới tự động.
- Token thường đại diện cho service identity và scope hẹp.

Hướng thiết kế:

- Access token ngắn, audience giới hạn cho service đích.
- Workload dùng client authentication mạnh hoặc workload identity.
- Thường xin token mới bằng client credentials hoặc cơ chế workload federation thay vì giữ refresh token dài hạn nếu không cần.
- Có cache token trong thời gian hợp lý để tránh mỗi request đều xin token mới.
- Có retry jitter và single-flight refresh để tránh thundering herd.

### 11.4. Batch job và tác vụ chạy dài

Không nên phát hành token có thời hạn nhiều giờ chỉ vì batch job chạy lâu. Có thể:

- Chia tác vụ thành các bước có thể tiếp tục an toàn.
- Làm mới access token khi cần bằng workload identity.
- Giới hạn audience/scope cho từng bước.
- Dùng idempotency key và checkpoint để xử lý retry.
- Dừng tác vụ nếu credential bị thu hồi hoặc policy thay đổi.

## 12. Refresh strategy và trải nghiệm người dùng

Refresh token giúp access token ngắn mà không bắt người dùng đăng nhập lại liên tục. Nhưng refresh phải được thiết kế để không gây vòng lặp, race condition hoặc gia hạn phiên ngoài ý muốn.

### 12.1. Refresh trước khi access token hết hạn

Client có thể bắt đầu refresh trước `exp` một khoảng đệm để tránh request đang chạy bị token hết hạn giữa chừng. Khoảng đệm cần tính đến:

- Clock skew giữa client và issuer.
- Độ trễ mạng.
- Thời gian xử lý refresh.
- Request đang chạy hoặc hàng đợi request.
- Khả năng server chấp nhận token theo leeway.

Không refresh quá sớm một cách liên tục. Client nên dùng một timer dựa trên thời điểm hết hạn đã xác minh hoặc metadata tin cậy và có backoff khi lỗi.

### 12.2. Single-flight refresh

Nếu nhiều request cùng phát hiện access token sắp hết hạn, client có thể gửi nhiều refresh request đồng thời. Với refresh-token rotation, chỉ một request có thể dùng refresh token cũ thành công; các request còn lại có thể bị coi là reuse.

Giải pháp:

- Dùng một refresh operation dùng chung cho các request đang chờ.
- Các request khác chờ kết quả refresh đó.
- Cập nhật access và refresh token như một cặp nhất quán.
- Không để response đến trễ ghi đè token mới bằng token cũ.
- Có xử lý khi refresh thất bại hoặc session đã bị revoke.

### 12.3. Không tạo vòng lặp refresh vô hạn

Nếu refresh token hết hạn, bị revoke hoặc không hợp lệ, client phải kết thúc phiên và yêu cầu đăng nhập lại theo policy. Không tự lặp refresh request vô hạn hoặc tiếp tục gửi access token cũ.

## 13. Refresh-token rotation và reuse detection

Refresh-token rotation phát hành refresh token mới mỗi lần refresh thành công và vô hiệu hóa token cũ. Nếu token cũ được dùng lại, hệ thống có thể phát hiện khả năng refresh token đã bị sao chép.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    C->>AS: Refresh token R1
    AS->>AS: Kiểm tra R1 và session/token family
    AS-->>C: Access token A2 + refresh token R2
    Note over AS: R1 được đánh dấu đã sử dụng
    C->>AS: Refresh token R2
    AS-->>C: Access token A3 + refresh token R3
    C->>AS: R1 được dùng lại
    AS->>AS: Phát hiện reuse theo token family
    AS->>AS: Thu hồi family hoặc áp dụng incident policy
~~~

### 13.1. Lưu trạng thái token family

Authorization server cần theo dõi quan hệ giữa các refresh token đã rotate trong cùng một grant/session. Khi token cũ được dùng lại, server có thể xác định token family liên quan và thu hồi các token còn hiệu lực trong family đó.

### 13.2. Xử lý reuse và request đồng thời

Reuse detection cần phân biệt tấn công với lỗi client do race condition, retry hoặc response bị mất. Thiết kế client single-flight là rất quan trọng. Server có thể dùng grace policy rất hẹp nếu cần cho retry an toàn, nhưng không được tạo cửa sổ cho phép replay kéo dài.

Khi phát hiện reuse đáng tin cậy:

- Thu hồi refresh token family theo policy.
- Có thể thu hồi session/grant liên quan.
- Yêu cầu người dùng xác thực lại.
- Ghi security event và cảnh báo.
- Không log raw refresh token.

## 14. Revocation và giới hạn của JWT stateless

JWT access token có thể được xác minh cục bộ bằng chữ ký và claims. Vì vậy, sau khi phát hành, verifier có thể tiếp tục chấp nhận token cho đến `exp` nếu không có cơ chế kiểm tra trạng thái bổ sung.

Các lựa chọn:

| Cơ chế | Cách hoạt động | Trade-off |
| --- | --- | --- |
| Short-lived access token | Đợi token tự hết hạn | Đơn giản, nhưng không revoke tức thời. |
| Denylist theo `jti` | Verifier kiểm tra token ID bị thu hồi | Có trạng thái, cần storage và đồng bộ. |
| Session/version check | So claim version với trạng thái hiện tại | Có thể revoke theo user/session, nhưng cần lookup. |
| OAuth token introspection | Resource server hỏi authorization server về trạng thái token | Tăng dependency và latency; có thể cache theo policy. |
| Key revocation/denylist | Ngừng tin một `kid` hoặc key | Ảnh hưởng mọi token ký bằng key đó. |
| Sender-constrained token | Gắn token với khóa của client | Giảm replay bởi bên chỉ lấy được token, nhưng không thay thế revoke. |

Short TTL giảm khoảng thời gian phải chờ khi không có revocation. Nếu cần logout hoặc khóa tài khoản có hiệu lực gần như tức thời, phải có cơ chế trạng thái/revocation phù hợp; chỉ rút ngắn `exp` có thể chưa đủ.

## 15. Re-authentication và step-up authentication

Một phiên còn hiệu lực không có nghĩa mọi hành động đều nên được thực hiện mà không xác thực lại.

Yêu cầu re-authentication hoặc step-up khi:

- Đổi mật khẩu hoặc yếu tố xác thực.
- Thêm/xóa phương thức MFA.
- Thay đổi email/điện thoại khôi phục.
- Tạo hoặc export API credential.
- Thực hiện giao dịch giá trị cao.
- Truy cập dữ liệu nhạy cảm đặc biệt.
- Có tín hiệu rủi ro như thiết bị mới, vị trí bất thường hoặc hành vi đáng ngờ.

Có thể dùng `auth_time`, `acr` hoặc `amr` trong profile hỗ trợ OIDC để đánh giá lần xác thực gần nhất và mức độ xác thực. Verifier phải kiểm tra claims theo profile; không tự suy ra MFA chỉ từ sự tồn tại của JWT.

Re-authentication interval là policy riêng. Không nhất thiết phải kết thúc toàn bộ session khi cần step-up; có thể yêu cầu một lần xác thực bổ sung cho hành động nhạy cảm.

## 16. Token lifetime và sender-constraining

Bearer token có thể bị replay bởi bất kỳ bên nào lấy được token. Sender-constraining làm token chỉ sử dụng được khi client chứng minh đang sở hữu khóa hoặc credential gắn với token.

Ví dụ:

- **DPoP:** token được ràng buộc với public key của client; request kèm proof được ký bằng private key tương ứng.
- **mTLS-bound access token:** token gắn với certificate của client, resource server kiểm tra certificate khi nhận request.

Sender-constraining có thể giảm rủi ro token bị lấy cắp rồi dùng từ thiết bị khác. Tuy nhiên:

- Không bảo vệ hoàn toàn khi attacker kiểm soát chính client và có thể gọi thao tác ký proof.
- Không thay thế expiration, audience, scope, revocation hoặc re-authentication.
- Tăng độ phức tạp quản lý khóa client và certificate.
- Cần kiểm tra khả năng hỗ trợ end-to-end ở client, proxy, gateway và resource server.

Khi có sender-constraining tốt, risk assessment có thể cho phép một lifetime khác so với bearer token thuần, nhưng không tự động kéo dài vô hạn.

## 17. Những lỗi thiết kế thời hạn thường gặp

| Anti-pattern | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Một TTL cho mọi loại token | Access, ID và refresh token có mục đích/rủi ro khác nhau. | Định nghĩa policy riêng theo token profile. |
| Access token sống rất lâu để tránh refresh | Token bị lộ có cửa sổ replay dài; quyền cũ tồn tại lâu. | Access token ngắn hơn và refresh flow có kiểm soát. |
| Refresh token không hết hạn | Credential có thể duy trì quyền truy cập vô thời hạn. | Idle timeout, absolute lifetime, rotation và revoke. |
| Mỗi lần refresh reset absolute expiry | Phiên có thể kéo dài vô hạn. | Giữ absolute expiry gốc hoặc yêu cầu re-auth. |
| Chỉ có `iat`, không có `exp` hoặc maximum age | Token có thể không có giới hạn tuổi hiệu lực. | Bắt buộc `exp` theo profile và kiểm tra maximum age nếu cần. |
| Clock skew quá lớn | Token hết hạn vẫn được chấp nhận lâu hơn dự kiến. | Đồng bộ thời gian và đặt leeway nhỏ. |
| Refresh đồng thời từ nhiều tab | Token rotation bị race, request hợp lệ bị coi là reuse. | Single-flight refresh và cập nhật token nguyên tử. |
| Không có revoke nhưng yêu cầu logout tức thời | JWT cũ vẫn được verifier chấp nhận đến `exp`. | Denylist, session check, introspection hoặc TTL phù hợp. |
| Tăng TTL để che lỗi authorization server | Giảm dependency tạm thời nhưng mở rộng cửa sổ rủi ro. | Cải thiện availability, cache và refresh retry. |
| Gia hạn token dựa trên hoạt động nền vô hạn | Session không bao giờ kết thúc dù người dùng không hiện diện. | Meaningful activity, idle timeout và absolute lifetime. |

## 18. Ví dụ lựa chọn policy cho ba tình huống

### 18.1. Ứng dụng đọc dữ liệu thông thường

Một ứng dụng nội bộ cho phép người dùng xem dữ liệu không quá nhạy cảm. Có thể chọn access token ngắn vừa phải, refresh nền để tránh đăng nhập liên tục, idle timeout theo thời gian không hoạt động và absolute lifetime theo ca làm việc. Cần revoke session khi tài khoản bị khóa hoặc thiết bị bị mất.

### 18.2. Cổng quản trị hệ thống

Token có thể truy cập cấu hình và quyền quản trị. Nên giảm access-token lifetime, giới hạn audience/scope, đặt idle timeout ngắn hơn, absolute lifetime rõ ràng và yêu cầu step-up cho thay đổi nhạy cảm. Việc đổi quyền hoặc thu hồi tài khoản cần được phản ánh qua revocation/session check hoặc cơ chế tương đương.

### 18.3. Service xử lý batch

Một batch job chạy nhiều giờ không nhất thiết cần một access token nhiều giờ. Workload có thể lấy token mới khi cần bằng workload identity, với audience và scope giới hạn. Client cần cache token, refresh trước khi hết hạn và có retry/backoff; nếu workload bị thu hồi, job phải dừng hoặc xử lý theo checkpoint an toàn.

Các tình huống trên minh họa cách ra quyết định. Giá trị TTL thực tế phải dựa trên phân tích rủi ro, yêu cầu pháp lý, khả năng vận hành và dữ liệu đo lường của tổ chức.

## 19. Theo dõi và điều chỉnh lifetime sau triển khai

Không nên coi TTL là quyết định một lần. Theo dõi:

- Tỷ lệ refresh thành công/thất bại.
- Số lần người dùng phải đăng nhập lại ngoài dự kiến.
- Số request thất bại do token hết hạn giữa tác vụ.
- Refresh-token reuse và revoke events.
- Số token bị từ chối do `exp`, `nbf`, `iat` hoặc maximum age.
- Độ trễ và availability của authorization server.
- Số request refresh đồng thời, retry storm và quota.
- Thời gian từ khi khóa tài khoản/revoke đến khi mọi resource server ngừng chấp nhận token.

Khi điều chỉnh:

1. Thay đổi theo từng client/profile hoặc nhóm người dùng.
2. Thử nghiệm trong staging với cùng clock, cache và network behavior gần production.
3. Đánh giá ảnh hưởng đến session, refresh rotation và mobile/offline clients.
4. Triển khai có giám sát và khả năng rollback.
5. Ghi nhận policy version để điều tra token được phát hành theo quy tắc nào.

Không dùng raw JWT, `sub` hoặc `jti` làm metric label. Dùng profile ID, outcome và nhóm reason có cardinality giới hạn.

## 20. Checklist chọn thời hạn

**Risk assessment**

- [ ] Xác định token là bearer hay sender-constrained.
- [ ] Xác định audience, scope, độ nhạy dữ liệu và hậu quả khi replay.
- [ ] Đánh giá nơi lưu token, nguy cơ XSS/malware và khả năng compromise thiết bị.
- [ ] Xác định khả năng revoke và thời gian phát hiện sự cố.

**Lifetime policy**

- [ ] Có policy riêng cho access, refresh, ID và token profile đặc biệt.
- [ ] Access-token TTL phản ánh phạm vi quyền và cửa sổ rủi ro chấp nhận được.
- [ ] Refresh token có idle và absolute lifetime.
- [ ] Session có idle timeout và absolute lifetime phù hợp.
- [ ] Có re-authentication/step-up cho hành động nhạy cảm.
- [ ] Không để refresh kéo dài absolute lifetime vô hạn.

**JWT time claims**

- [ ] Token profile yêu cầu `exp` khi cần token có thời hạn hữu hạn.
- [ ] `iat` được kiểm tra nếu dùng maximum token age.
- [ ] `nbf` được kiểm tra đúng khi profile sử dụng.
- [ ] NumericDate được xử lý theo UTC/Unix time.
- [ ] Clock skew nhỏ, có giới hạn và đồng hồ được đồng bộ.

**Refresh và revocation**

- [ ] Refresh có single-flight hoặc cơ chế tránh concurrent refresh race.
- [ ] Refresh-token rotation và reuse detection được thiết kế nếu phù hợp.
- [ ] Có revoke theo token/session/family hoặc cơ chế thay thế.
- [ ] Client dừng refresh khi credential bị revoke hoặc hết absolute lifetime.
- [ ] Có retry/backoff để tránh refresh storm.

**Vận hành**

- [ ] Có metrics về expiry, refresh, revoke, latency và availability.
- [ ] Đã kiểm thử browser, mobile, M2M và batch theo profile thực tế.
- [ ] Có quy trình thay đổi TTL và rollback.
- [ ] Có runbook xử lý refresh-token reuse và token compromise.

## 21. Tài liệu chuẩn tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): `exp`, `iat`, `nbf` và NumericDate.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access token và refresh token.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra trạng thái token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): refresh token rotation, replay detection và bảo vệ authorization flow.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained token bằng proof-of-possession.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): ràng buộc access token với certificate.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, `auth_time`, `acr` và `amr`.
- [NIST SP 800-63B — Digital Identity Guidelines: Authentication and Authenticator Management](https://pages.nist.gov/800-63-4/sp800-63b.html): quản lý phiên xác thực, reauthentication và authenticator lifecycle.

**Ghi nhớ:** access token thường cần ngắn theo phạm vi quyền và khả năng bị replay; refresh token có thể sống lâu hơn nhưng phải có bảo vệ lưu trữ, rotation, reuse detection, idle timeout, absolute lifetime và revocation. `exp` giới hạn thời điểm chấp nhận token; `iat` và `nbf` bổ sung quy tắc tuổi và thời điểm hiệu lực. Chọn TTL từ rủi ro, trải nghiệm và khả năng vận hành, sau đó đo lường và điều chỉnh.
