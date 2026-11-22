# Xử lý yêu cầu đồng thời trong quá trình làm mới

## 1. Vì sao refresh token dễ gặp race condition?

Access token thường có thời hạn ngắn. Khi access token hết hạn hoặc sắp hết hạn, client gửi refresh token tới authorization server để nhận access token mới và, tùy chính sách, một refresh token mới. Trong ứng dụng thực tế, nhiều request có thể cùng phát hiện access token hết hạn và đồng thời gọi refresh endpoint.

Ví dụ một trang web tải hồ sơ, danh sách đơn hàng và thông báo cùng lúc. Ba request API đều nhận 401 vì access token đã hết hạn. Nếu mỗi request tự gọi refresh endpoint bằng cùng một refresh token, server có thể nhận ba yêu cầu gần như đồng thời.

Với **refresh token rotation**, mỗi lần sử dụng refresh token hợp lệ sẽ phát hành token kế tiếp và vô hiệu hóa token cũ. Khi nhiều request cùng dùng token cũ:

- Request đầu tiên có thể xoay token thành công.
- Request thứ hai đến sau có thể thấy token cũ đã được sử dụng.
- Server có thể coi lần sử dụng thứ hai là dấu hiệu replay và thu hồi cả token family.
- Client có thể bị đăng xuất dù các request ban đầu đều xuất phát từ cùng một ứng dụng hợp lệ.

Đây là **race condition trong vòng đời token**. Thiết kế phải bảo đảm chỉ có một lần chuyển trạng thái hợp lệ, đồng thời xử lý được retry, mất phản hồi, nhiều tab, nhiều thiết bị và nhiều instance server.

Bài thuộc chương **Vòng đời token** của module **Security - JSON Web Token (JWT)**. Nội dung áp dụng chung cho OAuth 2.0/JWT và các hệ thống quản lý phiên, không phụ thuộc Java hay framework.

## 2. Refresh token rotation và trạng thái của một token family

### 2.1. Refresh token không nên là credential dùng vô hạn

Refresh token có thời hạn dài hơn access token và có thể dùng để cấp access token mới. Nếu một refresh token bị đánh cắp và vẫn được chấp nhận nhiều lần, attacker có thể duy trì phiên truy cập trong thời gian dài.

Với **refresh token rotation**, mỗi lần refresh thành công sẽ:

1. Xác thực refresh token hiện tại.
2. Đánh dấu token hiện tại đã được sử dụng/tiêu thụ.
3. Cấp access token mới.
4. Cấp refresh token kế tiếp.
5. Liên kết token mới với cùng phiên hoặc token family.

Refresh token cũ không còn được dùng cho lần refresh tiếp theo. Nếu token cũ xuất hiện lại, đó có thể là dấu hiệu token bị sao chép và sử dụng đồng thời bởi hai bên.

### 2.2. Token family

Một **token family** là chuỗi refresh token thuộc cùng một phiên đăng nhập hoặc cùng một lần cấp quyền. Mỗi token mới là hậu duệ của token trước:

~~~text
Family F-123
    RT-0 --refresh--> RT-1 --refresh--> RT-2 --refresh--> RT-3
      |                 |                 |
   consumed          consumed          consumed
~~~

Token family thường được gắn với subject, client/application, phiên đăng nhập hoặc thiết bị, thời điểm tạo, thời hạn tối đa và trạng thái hiện tại.

Tách family theo phiên hoặc thiết bị giúp thu hồi đúng phạm vi. Nếu người dùng đăng nhập trên điện thoại và máy tính, replay ở phiên điện thoại không nhất thiết phải đăng xuất máy tính, trừ khi chính sách yêu cầu thu hồi toàn bộ phiên.

### 2.3. State machine

Trạng thái của một refresh token:

| Trạng thái | Ý nghĩa | Có được refresh? |
| --- | --- | --- |
| ACTIVE | Token hiện tại còn hiệu lực và chưa sử dụng | Có, nếu mọi kiểm tra khác đạt |
| CONSUMED | Đã dùng để tạo token kế tiếp | Không |
| REVOKED | Bị thu hồi chủ động hoặc do sự cố | Không |
| EXPIRED | Đã hết thời hạn | Không |

Trạng thái family:

| Trạng thái | Ý nghĩa |
| --- | --- |
| ACTIVE | Phiên còn hoạt động và có thể refresh |
| REVOKED | Phiên bị thu hồi; mọi refresh token trong family đều không được dùng |
| EXPIRED | Đã vượt thời hạn tối đa của phiên |

Một token có thể còn hạn theo claim `exp` nhưng đã ở trạng thái CONSUMED hoặc REVOKED. Vì vậy, chữ ký JWT hợp lệ và thời hạn chưa hết không đủ để chứng minh refresh token còn được phép sử dụng.

## 3. Race condition điển hình

### 3.1. Hai request cùng dùng một refresh token

Giả sử client đang giữ RT-0. Hai request A và B được gửi gần như cùng lúc:

~~~text
Client                 Authorization Server
  |                             |
  |---- refresh(RT-0) ---------->|
  |                             |
  |---- refresh(RT-0) ---------->|
  |                             |
  |                       A kiểm tra RT-0
  |                       B kiểm tra RT-0
  |                       A phát hành RT-1
  |                       B cũng phát hành RT-2?
  |                             |
  |<--- access-1, RT-1 ----------|
  |<--- access-2, RT-2 ----------|
~~~

Nếu server chỉ đọc trạng thái token rồi mới cập nhật mà không có thao tác nguyên tử, cả A và B có thể cùng thấy RT-0 đang active. Kết quả là hai token kế tiếp được tạo ra từ cùng một token cha. Điều này phá vỡ giả định single-use và khiến server không biết nhánh nào là nhánh hợp lệ.

### 3.2. Race sau khi server đã rotation

Một triển khai khác có thể xử lý A trước:

~~~text
RT-0 ACTIVE
    |
    +-- Request A: consume RT-0, create RT-1
    |
    +-- Request B: sees RT-0 already consumed
~~~

Nếu chính sách reuse detection nghiêm ngặt, B có thể làm cả family bị thu hồi. Cách này phát hiện replay tốt, nhưng có thể gây false positive khi A và B thực chất là hai request hợp lệ của cùng client.

### 3.3. Phản hồi bị mất sau khi server đã commit

Một race khó xử lý hơn:

1. Client gửi refresh bằng RT-0.
2. Server đánh dấu RT-0 consumed, tạo RT-1 và commit transaction.
3. Server gửi phản hồi chứa RT-1.
4. Mạng bị ngắt hoặc client timeout trước khi nhận được phản hồi.
5. Client vẫn chỉ biết RT-0.
6. Client retry bằng RT-0.

Từ góc nhìn server, lần retry giống hệt một lần replay token đã dùng. Nhưng từ góc nhìn client, đây chỉ là retry của một giao dịch đã thành công mà phản hồi bị mất.

Nếu server thu hồi family ngay lập tức, phiên hợp lệ có thể bị hủy. Nếu server luôn chấp nhận token cũ, attacker có thể lợi dụng cửa sổ đó. Thiết kế cần phân biệt **duplicate request có thể chứng minh** với **replay không thể tin cậy**.

### 3.4. Nhiều tab hoặc nhiều tiến trình client

Race có thể xuất hiện khi nhiều tab cùng mở ứng dụng, nhiều component cùng xử lý 401, một request nền refresh trong lúc người dùng thao tác, ứng dụng desktop/mobile có nhiều worker, service worker và trang chính cùng gọi API, hoặc hai thiết bị dùng chung một refresh token.

Không nên giả định mỗi phiên đăng nhập chỉ có một request refresh tại một thời điểm nếu client chưa có cơ chế điều phối.

## 4. Vì sao kiểm tra rồi cập nhật riêng rẽ không an toàn?

### 4.1. Mẫu check-then-act có race

Logic sau không an toàn khi có nhiều request:

~~~text
token = database.find(refreshTokenId)

if token.status == ACTIVE:
    successor = createNewRefreshToken()
    database.markConsumed(token.id)
    database.insert(successor)
    return successor
~~~

Hai request có thể cùng đọc ACTIVE trước khi request nào kịp cập nhật. Việc đọc và chuyển trạng thái phải được bảo vệ bằng một thao tác nguyên tử hoặc transaction có mức cô lập và khóa phù hợp.

### 4.2. Mutex trong một instance là chưa đủ

Một mutex trong bộ nhớ có thể tuần tự hóa request trên cùng tiến trình. Nhưng nếu hệ thống có nhiều instance:

~~~text
              Load Balancer
               /        \
              v          v
          Server A    Server B
           lock A      lock B
              \          /
               Shared Database
~~~

Lock A và lock B không chia sẻ trạng thái. Hai request có thể đi vào hai instance khác nhau và cùng refresh một token. Cơ chế đồng bộ phải có hiệu lực trên toàn bộ instance, thường dựa vào database hoặc hệ thống điều phối phân tán.

### 4.3. Distributed lock không tự giải quyết mọi vấn đề

Distributed lock có thể hữu ích, nhưng cần xử lý lease hết hạn khi request vẫn đang chạy, client giữ lock bị pause, lock được cấp lại khi request cũ vẫn tiếp tục, mạng phân vùng và node không đồng bộ.

Nếu dùng distributed lock, cần lease có giới hạn, fencing token hoặc cơ chế kiểm tra phiên bản để ngăn chủ sở hữu lock cũ ghi đè trạng thái mới. Database vẫn nên có điều kiện cập nhật nguyên tử và ràng buộc duy nhất làm lớp bảo vệ cuối cùng.

## 5. Đồng bộ phía client: chỉ một refresh đang chạy

### 5.1. Single-flight refresh

Client nên gom các request refresh đồng thời thành một thao tác duy nhất:

~~~text
API request A ----\
API request B -----+--> refresh coordinator --> one refresh request
API request C ----/                              |
                                                  v
                                         store new credentials
                                                  |
                         +------------------------+------------------+
                         v                        v                  v
                    retry A                  retry B             retry C
~~~

Khi nhiều API request cùng nhận 401 do access token hết hạn:

1. Request đầu tiên tạo một refresh operation.
2. Các request khác chờ cùng operation đó.
3. Client chỉ gửi một refresh request.
4. Khi refresh thành công, cập nhật credential mới một lần.
5. Các request đang chờ được retry bằng access token mới.
6. Chỉ retry request gốc khi có thể bảo đảm thao tác chưa được thực hiện hoặc request có idempotency protection riêng.
7. Mỗi request gốc chỉ retry có giới hạn; không tạo vòng lặp 401 vô hạn.

Đây thường được gọi là **single-flight**, **refresh deduplication** hoặc **request coalescing**.

### 5.2. Đồng bộ giữa nhiều tab

Trong trình duyệt, các tab có thể phối hợp bằng BroadcastChannel, Web Locks API, SharedWorker, service worker hoặc cơ chế điều phối phiên phía server.

Không gửi refresh token thô qua BroadcastChannel hoặc message bus chỉ để đồng bộ. Nếu token được lưu trong cookie HttpOnly, JavaScript không đọc được giá trị cookie; các tab có thể điều phối trạng thái refresh mà không cần trao đổi giá trị cookie.

Các tab cũng cần đồng bộ trạng thái access token và kết quả refresh. Một tab đã refresh thành công nên thông báo rằng credential đã thay đổi để tab khác không tiếp tục dùng access token cũ. Thông điệp chỉ nên chứa trạng thái hoặc phiên bản credential, không chứa refresh token.

Local storage không phải mutex an toàn tuyệt đối: thao tác đọc/ghi có thể đua nhau và không cung cấp transaction compare-and-swap đáng tin cậy cho mọi tình huống. Không lưu refresh token dài hạn trong localStorage chỉ để giải quyết đồng bộ.

### 5.3. Đồng bộ trên mobile/desktop

Ứng dụng có nhiều worker hoặc tiến trình nên có một refresh coordinator theo từng session/account. Các thao tác cần refresh được xếp hàng hoặc cùng chờ một operation. Khi credential đổi, các request đang chờ dùng phiên bản mới.

Nếu ứng dụng hỗ trợ nhiều tài khoản, khóa điều phối phải gắn với đúng session/account; không để refresh của tài khoản A chặn hoặc ghi đè credential của tài khoản B.

### 5.4. Client coordination chỉ là lớp giảm race

Client có thể crash, bị kill, mất mạng hoặc bị attacker bỏ qua hoàn toàn. Một client tùy biến cũng có thể gửi nhiều refresh request song song. Vì vậy single-flight ở client cải thiện trải nghiệm và giảm tải, nhưng **server vẫn phải bảo đảm rotation nguyên tử**.

## 6. Xử lý nguyên tử ở server

### 6.1. Mục tiêu của transaction

Một lần refresh thành công cần được xem là một chuyển trạng thái duy nhất:

~~~text
PRECONDITION:
  token is ACTIVE
  family is ACTIVE
  token belongs to expected client/session
  token is not expired or revoked

ATOMIC TRANSITION:
  old token ACTIVE -> CONSUMED
  create exactly one successor token
  link old token -> successor
  update family current token/version
  store idempotency result if used

POSTCONDITION:
  exactly one successor is current
  old token cannot be used again as a new refresh
~~~

Nếu bất kỳ thao tác nào thất bại, transaction phải rollback toàn bộ thay đổi liên quan. Không được đánh dấu token cũ consumed rồi thất bại khi lưu token mới mà không có cơ chế phục hồi.

### 6.2. Conditional update / compare-and-swap

Một cách phổ biến là chỉ cho phép chuyển trạng thái nếu token vẫn đang active:

~~~sql
UPDATE refresh_tokens
SET status = 'CONSUMED',
    consumed_at = CURRENT_TIMESTAMP,
    successor_id = :successor_id
WHERE token_id = :token_id
  AND family_id = :family_id
  AND status = 'ACTIVE'
  AND expires_at > CURRENT_TIMESTAMP;
~~~

Server kiểm tra số dòng được cập nhật:

- Đúng một dòng: request đã giành quyền tiêu thụ token.
- Không dòng nào: token không còn active, không tồn tại, sai family hoặc đã hết hạn.
- Nhiều hơn một dòng: vi phạm invariant dữ liệu; dừng xử lý và báo lỗi nghiêm trọng.

Việc tạo successor và cập nhật family phải nằm trong cùng transaction. Không gửi token mới cho client trước khi transaction commit thành công.

### 6.3. Transaction và khóa bản ghi

Một lựa chọn khác là khóa bản ghi token/family trong transaction:

~~~text
BEGIN TRANSACTION

SELECT token, family
  FOR UPDATE

validate token and family state

mark old token CONSUMED
insert successor token
update family.current_token_id

COMMIT
~~~

Khóa phải được lấy trên đúng tài nguyên đại diện cho family hoặc token hiện tại. Mọi đường ghi trạng thái refresh phải tuân thủ cùng quy tắc; nếu một đường code bỏ qua lock, race vẫn có thể xảy ra.

Mức cô lập transaction và cơ chế khóa phụ thuộc database. Cần kiểm tra hành vi thật khi hai transaction cùng cập nhật một token, bao gồm deadlock, serialization failure và retry transaction.

### 6.4. Ràng buộc dữ liệu ở database

Ngoài logic ứng dụng, dùng constraint để bảo vệ invariant:

- Mỗi token ID là duy nhất.
- Một token chỉ có tối đa một successor.
- Một family chỉ có một token current/active theo mô hình dữ liệu đã chọn.
- Quan hệ parent-child không tạo chu trình.
- Token successor phải thuộc cùng family và đúng session/client.
- Trạng thái consumed không thể quay lại active bằng thao tác thông thường.

Constraint cụ thể có thể là unique index, foreign key, check constraint hoặc thiết kế bảng phù hợp. Không chỉ dựa vào một câu điều kiện ở tầng ứng dụng.

### 6.5. Thứ tự tạo token và commit

Server thường cần tạo giá trị refresh token mới trước khi lưu hash/identifier của nó. Một trình tự an toàn:

1. Tạo token successor ngẫu nhiên hoặc ký JWT successor theo policy.
2. Tính hash/identifier cần lưu.
3. Trong transaction, atomically consume token cũ, insert successor và cập nhật family.
4. Commit.
5. Chỉ sau commit mới gửi access token và refresh token mới về client.

Nếu commit thất bại, không gửi token successor. Nếu commit thành công nhưng response bị mất, xử lý bằng idempotency/recovery policy; không tạo một successor thứ hai tùy tiện.

Với thao tác ký qua KMS/HSM từ xa, cân nhắc tạo chữ ký trước transaction để không giữ lock trong thời gian gọi mạng. Token chưa được gửi ra ngoài nên có thể bị bỏ đi nếu transaction không thắng. Cần tránh để token được ký nhưng trạng thái lưu trữ không thể commit rồi lại bị client nhận.

Có thể tạo trước candidate successor và access token, sau đó transaction chỉ persist candidate của request thắng. Candidate của request thua phải bị loại bỏ và không được trả cho client. Nếu token được tạo trước transaction, không được xem việc tạo chữ ký là bằng chứng rotation đã thành công; điểm thành công vẫn là commit trạng thái.

## 7. Xử lý duplicate request và idempotency

### 7.1. Idempotency có tác dụng gì?

Một request refresh có thể thành công ở server nhưng client không nhận được phản hồi. Nếu client gửi lại đúng thao tác, server cần biết đây là retry của cùng một operation hay một lần sử dụng lại token cũ độc lập.

**Idempotency key** là định danh do client tạo cho một operation refresh. Server lưu kết quả theo khóa đó trong phạm vi session/client và một thời gian giới hạn. Khi nhận lại cùng operation, server có thể trả lại kết quả đã ghi nhận thay vì xoay token lần nữa.

~~~http
POST /oauth/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Idempotency-Key: 7f4c...unique-operation-id

grant_type=refresh_token&refresh_token=<RT-0>
~~~

Header minh họa; idempotency key không phải chuẩn bắt buộc của OAuth token endpoint và cần được định nghĩa trong hợp đồng riêng giữa client/server.

### 7.2. Idempotency key không phải bằng chứng xác thực

Attacker có thể tự tạo idempotency key. Vì vậy, không được chỉ dựa vào key này để trả lại credential mới. Operation phải được ràng buộc với refresh token cũ hợp lệ, client/session phù hợp, sender constraint nếu có, dấu vân tay request và thời hạn lưu idempotency result ngắn.

Nếu cùng một idempotency key được dùng với refresh token khác, client khác hoặc request có tham số khác, phải từ chối và ghi nhận bất thường.

Idempotency key chỉ giúp nhận diện một operation đã được ghi nhận; nó không chứng minh người gửi là client hợp lệ. Với bearer refresh token, nếu attacker đánh cắp được cả token và thông tin operation cần thiết, server có thể không phân biệt được retry của client thật với replay của attacker. Sender-constrained token hoặc proof-of-possession giúp tăng khả năng phân biệt, nhưng vẫn phải có policy xử lý trường hợp không thể chứng minh nguồn gửi.

### 7.3. Trả lại cùng kết quả sau retry

Để trả lại cùng refresh token successor sau khi response bị mất, server phải có cách khôi phục chính xác kết quả đã phát hành. Nếu chỉ lưu hash của successor, server không thể dựng lại raw token.

Một số lựa chọn:

1. Lưu response credential đã mã hóa bằng khóa server, với thời gian sống ngắn và quyền truy cập rất hạn chế.
2. Dùng cơ chế token có thể tái tạo an toàn từ dữ liệu operation đã lưu, nếu thiết kế mật mã và quản lý khóa chứng minh được tính an toàn.
3. Không trả lại token cũ; yêu cầu reauthentication khi kết quả refresh không thể khôi phục.

Không lưu refresh token thô trong bảng idempotency hoặc log chỉ để tiện retry. Nếu lưu response mã hóa, phải bảo vệ encryption key, giới hạn retention và xóa dữ liệu sau khi cửa sổ retry kết thúc.

### 7.4. Ràng buộc fingerprint của request

Server có thể lưu fingerprint gồm client ID, family/session ID, token ID cũ, idempotency key, loại grant, tham số liên quan và sender key thumbprint nếu có.

Không đưa raw refresh token vào log hoặc dùng nó trực tiếp làm idempotency key. Fingerprint phải được tạo an toàn, tránh lộ credential và không cho phép va chạm phạm vi giữa các client.

Client ID thường là định danh công khai, không phải bằng chứng xác thực. Không dùng riêng client ID, IP address hoặc User-Agent để kết luận hai request đến từ cùng một client đáng tin cậy.

### 7.5. Thời gian lưu idempotency result

Thời gian này phải đủ cho retry mạng hợp lệ nhưng không dài vô hạn. Ví dụ, hệ thống có thể chọn cửa sổ vài chục giây hoặc vài phút dựa trên timeout/retry của client. Con số cụ thể là policy triển khai, không phải giá trị chuẩn áp dụng cho mọi hệ thống.

Sau khi cửa sổ kết thúc, operation cũ không được tạo successor mới; token cũ vẫn consumed và chính sách reuse detection được áp dụng.

### 7.6. Hai request đồng thời dùng cùng idempotency key

Hai request retry có thể đến cùng lúc trước khi operation record được tạo. Cả hai transaction đều có thể chưa nhìn thấy bản ghi idempotency. Vì vậy, thao tác lưu operation result cũng cần bảo vệ bằng unique constraint, ví dụ trên cặp client/family và hash của operation key.

Một cách xử lý:

1. Cả hai request xác thực và tính cùng request fingerprint.
2. Mỗi request thử tạo operation record trong transaction.
3. Unique constraint chỉ cho một transaction tạo bản ghi.
4. Transaction thắng thực hiện rotation và lưu response đã bảo vệ.
5. Transaction thua rollback phần xử lý trùng, đọc lại operation record đã commit.
6. So khớp fingerprint, client/session binding và sender proof; nếu khớp thì trả lại cùng kết quả trong cửa sổ idempotency.

Nếu request thua không tìm thấy operation record sau khi transaction thắng rollback, nó có thể thử lại theo giới hạn. Không để hai transaction cùng tạo hai successor chỉ vì cùng một operation key.

## 8. Grace period: lợi ích và rủi ro

### 8.1. Grace period là gì?

Một số hệ thống cho phép token cũ được gửi lại trong một khoảng ngắn sau rotation để giảm false positive do request đồng thời hoặc response bị mất. Đây thường được gọi là **grace period** hoặc overlap window.

Grace period có thể cải thiện trải nghiệm khi nhiều request cùng được gửi trước khi client nhận token mới, response refresh bị trễ/mất hoặc nhiều tab chưa kịp đồng bộ credential.

### 8.2. Vì sao grace period nguy hiểm nếu quá rộng?

Nếu token cũ vẫn được chấp nhận tùy ý trong một khoảng thời gian, attacker có token bị đánh cắp cũng có thể sử dụng nó trong cửa sổ đó. Nếu mỗi lần dùng token cũ lại tạo một successor mới, server có thể tạo nhiều nhánh token family.

Do đó, grace period không nên đơn giản có nghĩa là “chấp nhận token cũ thêm một lúc”. Cần xác định có trả lại cùng successor hay tạo token mới, request được ràng buộc với client/session thế nào, có idempotency key hoặc sender proof không, số lần retry tối đa và cách ghi nhận reuse.

### 8.3. Các chính sách thường gặp

| Chính sách | Hành vi | Đánh đổi |
| --- | --- | --- |
| Strict single-use | Lần đầu thành công; lần sau dùng token cũ bị xem là reuse | Bảo mật đơn giản, dễ false positive với concurrency/retry |
| Idempotent retry | Cùng operation đã nhận diện được trả lại cùng kết quả | Trải nghiệm tốt hơn; cần lưu kết quả nhạy cảm an toàn |
| Bounded grace | Cho phép retry giới hạn trong cửa sổ ngắn và có ràng buộc | Giảm lỗi mạng nhưng mở thêm cửa sổ replay |
| Reauthentication | Không thể xác định kết quả; yêu cầu đăng nhập lại | An toàn và đơn giản, nhưng tăng ma sát người dùng |

Không có grace period mặc định phù hợp mọi hệ thống. Nếu chọn grace, phải coi đó là quyết định rủi ro có chủ đích và kiểm thử replay.

## 9. Reuse detection và thu hồi token family

### 9.1. Phát hiện refresh token đã bị dùng lại

Với rotation nghiêm ngặt, server ghi nhận token cũ đã consumed. Nếu token đó được trình bày lại ngoài một operation duplicate hợp lệ đã được nhận diện, đây có thể là dấu hiệu token bị sao chép.

~~~text
RT-0 --valid refresh--> RT-1
  |
  +-- presented again by unknown operation
          |
          v
      reuse detected
          |
          v
      revoke family F
~~~

Server có thể thu hồi family để ngăn cả attacker và client hợp lệ tiếp tục dùng các hậu duệ của token bị lộ. Hành động này gây gián đoạn phiên nhưng hạn chế khả năng attacker giữ quyền sau khi bị phát hiện.

### 9.2. Không phải mọi duplicate đều chứng minh token bị đánh cắp

Hai request cùng xuất phát từ một client có thể tạo ra cùng dấu hiệu với attacker replay. Các tín hiệu giúp phân biệt gồm operation đã ghi nhận, client/session và sender key, retry window, dấu thời gian và proof-of-possession nếu có.

IP address hoặc User-Agent không phải bằng chứng danh tính chắc chắn: chúng có thể thay đổi, bị chia sẻ hoặc bị giả mạo. Không dùng riêng chúng làm căn cứ duy nhất để miễn reuse detection.

### 9.3. Thu hồi family

Khi xác định replay đáng tin cậy:

1. Đánh dấu family là revoked một cách nguyên tử.
2. Không cho phép refresh từ bất kỳ token nào trong family.
3. Ghi nhận sự kiện bảo mật và thời điểm phát hiện.
4. Vô hiệu hóa session liên quan theo chính sách.
5. Thông báo cho người dùng hoặc yêu cầu đăng nhập lại khi phù hợp.
6. Điều tra nguồn lộ token và xem xét các phiên khác.

Nếu token family được tách theo thiết bị, có thể thu hồi riêng family bị ảnh hưởng. Nếu chính sách sự cố yêu cầu mức cao hơn, có thể thu hồi tất cả phiên của subject.

### 9.4. Access token đã cấp vẫn có thể còn hiệu lực

Thu hồi refresh token family không tự động làm một access JWT stateless đã phát hành trở nên vô hiệu. Access token có thể tiếp tục được chấp nhận đến `exp` nếu resource server chỉ xác minh chữ ký và claims cục bộ.

Các biện pháp giới hạn thời gian ảnh hưởng:

- Access token có TTL ngắn.
- Resource server kiểm tra session/family status hoặc denylist khi cần thu hồi tức thì.
- Dùng introspection hoặc một cơ chế revocation state được chia sẻ.
- Với hệ thống phù hợp, ràng buộc token với sender key để giảm khả năng sử dụng token bị đánh cắp.

Chọn mức độ kiểm tra trạng thái online dựa trên yêu cầu thu hồi, độ trễ, khả năng chịu lỗi và chi phí vận hành.

## 10. JWT refresh token và trạng thái phía server

### 10.1. Chữ ký JWT không ngăn sử dụng lại

Một refresh JWT có thể chứa `jti`, `sub`, `iss`, `aud`, `exp` và thông tin session/family. Chữ ký chứng minh token do issuer ký và chưa bị sửa, nhưng không chứng minh token chưa từng được dùng.

Để rotation và reuse detection có hiệu lực, server cần trạng thái phía server hoặc cơ chế đồng bộ tương đương:

- Lưu `jti`/token identifier và trạng thái active/consumed/revoked.
- Lưu family/session ID và token hiện tại.
- Ghi nhận quan hệ parent-successor.
- Thực hiện chuyển trạng thái nguyên tử.

Nếu không lưu trạng thái đã dùng, hai request đồng thời có thể cùng xác minh JWT hợp lệ và tạo hai successor. Một hệ thống hoàn toàn stateless không thể tự biết token đã được tiêu thụ ở request trước.

### 10.2. Opaque refresh token

Một lựa chọn là refresh token opaque, ngẫu nhiên, không chứa claims đọc được:

~~~text
client receives: random high-entropy token
server stores: hash(token), family_id, status, expiry, successor_id
~~~

Server tra hash để tìm trạng thái và xoay token. Vì token opaque không tự mang claims, mọi thông tin phiên được tra từ kho trạng thái. Token phải đủ ngẫu nhiên để không thể đoán; hash của token entropy cao có thể được lưu thay cho giá trị thô.

### 10.3. Lựa chọn lưu token identifier hay hash toàn token

Với refresh JWT, có thể lưu `jti` hoặc hash của toàn bộ token:

- Lưu `jti` giúp tra cứu nhanh nhưng phải bảo đảm `jti` ngẫu nhiên/duy nhất và token không thể bị giả mạo.
- Lưu hash toàn token giúp đối chiếu chính xác credential được trình bày và tránh lưu token thô.
- Có thể kết hợp `jti`, family ID và hash để đáp ứng audit/rotation.

Không lưu raw refresh token trong database nếu không có lý do rõ ràng và cơ chế bảo vệ tương xứng. Nếu cần trả lại cùng successor sau retry, lưu response mã hóa trong kho idempotency riêng có retention ngắn.

## 11. Hệ thống phân tán và nhiều vùng dữ liệu

### 11.1. Read replica có thể làm hỏng quyết định refresh

Nếu request A cập nhật token ở primary nhưng request B đọc trạng thái từ read replica chưa đồng bộ, B có thể vẫn thấy token active. Khi đó B có thể cố refresh lần nữa.

Đối với quyết định single-use, việc đọc trạng thái hiện tại phải có tính nhất quán đủ mạnh. Không dùng dữ liệu eventual-consistent làm căn cứ duy nhất để tiêu thụ token.

### 11.2. Nhiều region

Nếu cùng một token family có thể được refresh ở nhiều region, cần một cơ chế đảm bảo chỉ một region thắng:

- Ghi trạng thái family vào datastore có consistency phù hợp.
- Partition/route family về một region chủ sở hữu.
- Dùng transaction hoặc compare-and-swap toàn cục.
- Có quy tắc xử lý khi region mất kết nối hoặc failover.

Nếu hai region độc lập đều có thể ghi ACTIVE -> CONSUMED mà không đồng bộ, mỗi region có thể phát hành successor khác nhau.

### 11.3. Không dùng timestamp làm khóa đồng bộ

Timestamp, thời điểm request hoặc thứ tự đến từ các máy khác nhau không đủ để quyết định request nào thắng. Đồng hồ có thể lệch và hai request có thể cùng timestamp.

Dùng version/sequence tăng đơn điệu, transaction hoặc compare-and-swap trên trạng thái authoritative. Đồng hồ phục vụ kiểm tra thời hạn và audit, không thay thế cơ chế loại trừ tương tranh.

### 11.4. Eventual consistency cho dữ liệu phụ, không cho quyền tiêu thụ

Analytics, audit stream hoặc notification có thể được xử lý bất đồng bộ. Nhưng quyết định token còn active và việc consume token phải có một điểm commit có tính nhất quán rõ ràng.

Có thể phát event sau commit qua transactional outbox để đồng bộ cache, metrics và notification. Không phát sự kiện “rotation thành công” trước khi transaction chính commit.

## 12. Sender-constrained refresh token

### 12.1. Ràng buộc token với client

Sender-constrained token gắn quyền sử dụng token với khóa hoặc chứng thư của client. Ví dụ:

- Mutual TLS client certificate.
- Demonstrating Proof-of-Possession (DPoP).

Khi refresh request đến, server xác minh token và bằng chứng client sở hữu khóa tương ứng. Điều này giảm nguy cơ attacker chỉ đánh cắp chuỗi refresh token rồi sử dụng từ client khác.

### 12.2. Sender constraint không thay thế rotation

Sender constraint không giải quyết mọi race:

- Cùng client hợp lệ vẫn có thể gửi hai request đồng thời.
- Một thiết bị bị xâm nhập có thể bị lộ cả token và khóa proof.
- Retry sau khi mất response vẫn cần idempotency hoặc recovery policy.
- Server vẫn cần trạng thái family và atomic transition để ngăn hai successor.

Do đó sender constraint là lớp giảm replay từ bên ngoài; rotation và đồng bộ vẫn cần thiết.

### 12.3. Ràng buộc idempotency với proof key

Nếu dùng idempotent retry, có thể yêu cầu operation duplicate phải gắn với cùng sender key thumbprint. Một request cùng idempotency key nhưng proof key khác không được tự động nhận lại successor credential.

Không coi IP address hoặc User-Agent là sender constraint. Chúng không chứng minh client đang sở hữu khóa bí mật.

## 13. Xử lý timeout, retry và trạng thái không xác định

### 13.1. Phân biệt thất bại trước và sau commit

Client thường không biết server đã commit hay chưa khi request timeout:

| Trạng thái thực tế | Client quan sát | Cách xử lý |
| --- | --- | --- |
| Server chưa xử lý | Timeout hoặc mất kết nối | Có thể retry cùng operation theo policy |
| Server đã xử lý và commit, response mất | Timeout hoặc mất kết nối | Retry phải được nhận diện idempotent hoặc dùng recovery flow |
| Server xử lý nhưng transaction rollback | Timeout/lỗi | Retry có thể được phép vì token cũ vẫn active |

Không nên coi mọi timeout là “server chưa làm gì”. Đây là lỗi phổ biến dẫn đến refresh token reuse ngoài ý muốn.

### 13.2. Retry cùng operation

Khi client retry:

- Dùng lại cùng idempotency key cho cùng operation.
- Không tạo operation ID mới cho mỗi lần retry mạng.
- Giữ nguyên client/session binding và proof key.
- Áp dụng số lần retry và thời hạn hữu hạn.
- Không retry vô hạn khi server trả lỗi token đã bị thu hồi.

Nếu server không hỗ trợ idempotency/recovery, client có thể phải yêu cầu đăng nhập lại khi kết quả refresh không xác định. Đây là lựa chọn rõ ràng hơn việc thử dùng token cũ nhiều lần.

### 13.3. Tránh retry mọi lỗi

Phân biệt:

- Timeout/network failure: có thể retry theo idempotency policy.
- `invalid_grant` do token expired/revoked/consumed: không retry mù quáng.
- Client authentication failure: không lặp refresh với cùng credential sai.
- Server unavailable: backoff có giới hạn, giữ trạng thái session chưa xác định.
- Policy denial/reuse detected: dừng refresh và xử lý phiên theo hướng dẫn server.

Không để interceptor tự động refresh lại chính refresh endpoint hoặc tạo vòng lặp retry khi access token mới vẫn bị từ chối.

## 14. Ví dụ thiết kế luồng refresh an toàn

### 14.1. Dữ liệu trạng thái tối thiểu

Một mô hình dữ liệu minh họa:

| Bản ghi | Trường chính | Mục đích |
| --- | --- | --- |
| Token family | family_id, subject_id, client_id, status, current_token_id, version, expires_at | Trạng thái phiên |
| Refresh token | token_id, family_id, token_hash, status, issued_at, expires_at, consumed_at, successor_id | Trạng thái từng refresh token |
| Idempotency operation | client_id, family_id, operation_key_hash, request_fingerprint, result_ciphertext, expires_at | Khôi phục response duplicate |

Đây là mô hình khái niệm. Có thể dùng schema khác nếu vẫn bảo đảm cùng invariant và tính nguyên tử.

### 14.2. Pseudocode phía server

~~~text
function refresh(request):
    policy = loadTrustedRefreshPolicy()
    require policy is valid

    presented = validateRefreshCredential(request.refreshToken)
    require presented is valid

    clientBinding = validateClientOrSenderProof(request)
    require clientBinding is valid

    operation = normalizeAndFingerprint(
        request.idempotencyKey,
        presented.tokenId,
        clientBinding,
        request.grantParameters
    )

    BEGIN TRANSACTION

    previousResult = findOperationForUpdate(operation.key)
    if previousResult exists:
        require previousResult.fingerprint == operation.fingerprint
        require previousResult.clientBinding == clientBinding
        require previousResult.notExpired
        response = decryptStoredResult(previousResult)
        COMMIT
        return response

    family = loadFamilyForUpdate(presented.familyId)
    token = loadTokenForUpdate(presented.tokenId)

    require family.status == ACTIVE
    if token.status == CONSUMED:
        revoke family atomically
        record reuse event
        COMMIT
        return DENY(invalid_grant)

    require token.status == ACTIVE
    require token.familyId == family.id
    require token is current token for family
    require token is not expired
    require clientBinding matches family

    successor = createNewRefreshCredential()
    accessToken = createNewAccessToken()

    atomically mark token CONSUMED
    insert successor record
    update family current token and version
    store encrypted idempotent response

    COMMIT

    return accessToken and successor
~~~

Mã giả rút gọn để minh họa transaction; triển khai phải xử lý rollback, uniqueness conflict, serialization failure, lock timeout và lỗi mã hóa response. Nếu operation key đã tồn tại nhưng fingerprint hoặc client binding khác, không trả credential cũ.

Nếu thao tác tạo operation record và transaction refresh bị tranh chấp, unique constraint phải quyết định một request thắng. Request còn lại cần đọc lại operation result sau khi transaction thắng commit. Khi token đã consumed mà không có operation hợp lệ tương ứng, áp dụng reuse detection theo policy; không tự động coi đó là retry an toàn.

### 14.3. Pseudocode phía client

~~~text
function getValidAccessToken():
    if accessToken is still valid with safety margin:
        return accessToken

    if refreshOperation is already running:
        return await refreshOperation

    refreshOperation = startOneRefreshOperation()
    try:
        result = await refreshWithStableOperationId()
        atomicallyStoreNewCredentials(result)
        return result.accessToken
    catch error:
        if result is unknown because of network timeout:
            recoverOrRetrySameOperation()
        else:
            handleRefreshFailure(error)
    finally:
        clearRefreshOperation()
~~~

Client chỉ cần một refresh operation đang chạy cho cùng session. Khi trạng thái không xác định, phải dùng cùng operation ID để retry nếu server hỗ trợ; không tự tạo nhiều refresh operation độc lập.

Khi retry request nghiệp vụ sau refresh, cần xét riêng tính idempotent của request đó. Một POST tạo đơn hàng hoặc chuyển tiền có thể đã được xử lý dù client không nhận được response. Dùng idempotency key riêng cho thao tác nghiệp vụ hoặc chỉ retry khi server chứng minh request trước chưa thực hiện; không dùng idempotency key của refresh để bảo đảm tính duy nhất cho API nghiệp vụ.

### 14.4. Sequence diagram

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant AS as Authorization Server
    participant DB as State Store
    C->>A: Request 1 với access token hết hạn
    A-->>C: 401
    C->>A: Request 2 với access token hết hạn
    A-->>C: 401
    Note over C: Single-flight gộp hai yêu cầu refresh
    C->>AS: Refresh RT-0 + operation key
    AS->>DB: Transaction consume RT-0, create RT-1
    DB-->>AS: Commit thành công
    AS-->>C: Access token mới + RT-1
    C->>A: Retry Request 1 và 2 với access token mới
    A-->>C: Kết quả API
~~~

## 15. Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân | Hậu quả | Cách xử lý |
| --- | --- | --- | --- |
| Mỗi API request tự refresh | Không có single-flight | Nhiều request cùng dùng RT cũ | Gộp refresh operation ở client |
| Check active rồi update riêng | Không có atomic transition | Hai successor từ một token cha | CAS/transaction/lock và constraint |
| Chỉ dùng mutex trong process | Nhiều server instance | Race giữa các instance | Đồng bộ trên datastore authoritative |
| Đọc từ replica trễ | Eventual consistency | Token consumed vẫn được thấy active | Đọc/ghi trạng thái refresh với consistency đủ mạnh |
| Response mất sau commit | Client retry token cũ | False positive reuse detection | Idempotency/recovery hoặc reauthentication |
| Grace period không giới hạn | Muốn tránh lỗi đồng thời | Attacker có cửa sổ replay dài | Bounded policy, ràng buộc client và audit |
| Idempotency key không ràng buộc | Coi key như credential | Có thể trả kết quả cho request khác | Bind với token, family, client và proof |
| Lưu raw successor trong log | Muốn debug | Lộ refresh credential | Không log token; bảo vệ result mã hóa nếu cần |
| Thu hồi cả user vì một device race | Family không tách theo phiên | Đăng xuất không cần thiết | Token family riêng theo session/device |
| Chỉ thu hồi refresh token | Quên access token còn hiệu lực | Access JWT cũ vẫn dùng được tới exp | TTL ngắn hoặc revocation check |
| Retry vô hạn | Không phân loại lỗi | Tải tăng và lặp invalid_grant | Retry hữu hạn, backoff, dừng khi policy deny |
| Hai region cùng refresh | Không có điểm commit chung | Hai nhánh token family | Strong consistency/partition ownership |

## 16. Checklist thiết kế và vận hành

### 16.1. Phía client

- [ ] Có một refresh coordinator cho mỗi session/account.
- [ ] Các request cùng gặp access token hết hạn được gộp vào một refresh operation.
- [ ] Nhiều tab/worker có cơ chế phối hợp phù hợp.
- [ ] Request gốc chỉ retry có giới hạn sau refresh thành công.
- [ ] Retry mạng dùng lại cùng operation ID nếu server hỗ trợ idempotency.
- [ ] Không phát tán refresh token thô qua message bus hoặc log.
- [ ] Khi kết quả refresh không xác định và không thể recovery, xử lý đăng nhập lại rõ ràng.

### 16.2. Phía server

- [ ] Refresh token có trạng thái và token family/session rõ ràng.
- [ ] Rotation là chuyển trạng thái nguyên tử.
- [ ] Chỉ một request có thể consume token hiện tại.
- [ ] Successor và cập nhật family cùng commit trong một transaction.
- [ ] Database constraint bảo vệ quan hệ token và trạng thái active.
- [ ] Reuse detection phân biệt duplicate operation đã nhận diện với lần dùng lại độc lập.
- [ ] Idempotency key được ràng buộc với token/client/session và request fingerprint.
- [ ] Nếu cần trả lại successor, kết quả được bảo vệ mã hóa và có retention ngắn.
- [ ] Grace period có giới hạn, có lý do và được kiểm thử replay.
- [ ] Family revoke ngăn mọi refresh token thuộc family tiếp tục sử dụng.
- [ ] Chính sách xử lý access token đã phát hành được xác định.

### 16.3. Hạ tầng phân tán

- [ ] Nhiều instance dùng cùng cơ chế atomic state transition.
- [ ] Refresh không dựa vào read replica có thể trễ.
- [ ] Multi-region có một điểm đồng bộ/ownership rõ ràng.
- [ ] Distributed lock có lease/fencing nếu được sử dụng.
- [ ] Transaction retry xử lý deadlock và serialization failure an toàn.
- [ ] Event thông báo rotation chỉ phát sau commit, có thể dùng transactional outbox.
- [ ] Có metrics cho duplicate, reuse, rotation conflict và family revoke.

## 17. Kiểm thử race condition

### 17.1. Kiểm thử đồng thời cơ bản

Với một refresh token active:

1. Gửi đồng thời N request dùng cùng token.
2. Kiểm tra chỉ có một transition consume thành công.
3. Kiểm tra family chỉ có một successor current.
4. Kiểm tra không có hai token con active.
5. Kiểm tra request thua cuộc có kết quả theo đúng policy duplicate/reuse.

Không chỉ kiểm tra HTTP response; phải xác minh invariant trong datastore.

### 17.2. Kiểm thử response bị mất

- Server commit thành công nhưng cắt kết nối trước khi response tới client.
- Client retry cùng operation key.
- Xác minh server trả cùng kết quả đã lưu hoặc thực hiện recovery policy đã thiết kế.
- Xác minh không phát hành successor thứ hai.
- Thử lại với operation key khác để kiểm tra reuse detection.

### 17.3. Kiểm thử đa instance và multi-region

- Gửi request A tới instance 1, request B tới instance 2.
- Cố ý làm chậm transaction để tăng khả năng đua.
- Đọc từ replica trễ trong môi trường test để xác minh luồng refresh không dựa vào dữ liệu stale.
- Mô phỏng lock lease hết hạn và request cũ tiếp tục chạy.
- Mô phỏng failover region khi refresh đang commit.
- Kiểm tra constraint vẫn bảo đảm chỉ một successor.

### 17.4. Kiểm thử bảo mật

- Attacker dùng lại token consumed với client binding khác.
- Dùng idempotency key hợp lệ nhưng refresh token khác.
- Dùng cùng refresh token nhưng sender proof khác.
- Dùng token đã revoke hoặc family đã expired.
- Thử token cũ sau khi grace window kết thúc.
- Kiểm tra log không chứa raw refresh token hoặc response credential.
- Xác minh family revoke không bị ghi đè bởi request đang chạy.

### 17.5. Tiêu chí đạt

- Không có hai successor cùng được xem là current.
- Không có đường code bỏ qua trạng thái consumed/revoked.
- Retry hợp lệ không tạo nhánh token mới ngoài ý muốn.
- Replay độc lập được phát hiện theo policy.
- Một request thất bại không để lại trạng thái nửa cập nhật.
- Mất kết nối không khiến server phát hành token không được lưu hoặc client nhận token chưa commit.

## 18. Những hiểu lầm phổ biến

**“Chỉ cần client không gửi refresh đồng thời là đủ.”** Sai. Client có thể crash, nhiều tab hoặc bị thay thế; server phải bảo vệ atomicity.

**“Dùng mutex trong một server là đủ.”** Sai khi có nhiều instance hoặc nhiều region.

**“Hai request cùng token chắc chắn là attacker.”** Không hẳn. Có thể là request hợp lệ đồng thời hoặc retry sau khi response bị mất; cần policy duplicate/reuse rõ ràng.

**“Grace period càng dài càng thân thiện.”** Sai. Cửa sổ chấp nhận token cũ càng dài thì cơ hội replay càng lớn.

**“Idempotency key tự nó chứng minh request hợp lệ.”** Sai. Nó phải được ràng buộc với refresh token, family, client và sender proof nếu có.

**“JWT có chữ ký nên không cần database trạng thái.”** Sai nếu cần rotation single-use và reuse detection. Chữ ký không cho biết token đã bị tiêu thụ.

**“Thu hồi refresh token là access token cũng mất hiệu lực ngay.”** Sai với access JWT được xác minh hoàn toàn stateless.

**“Timestamp đến trước sẽ thắng.”** Sai. Đồng hồ các instance có thể lệch; dùng transaction, version hoặc compare-and-swap.

**“Nếu response timeout thì server chắc chắn chưa xử lý.”** Sai. Server có thể đã commit và chỉ mất response trên đường về.

## 19. Câu hỏi tự kiểm tra

1. Vì sao refresh token rotation tạo ra race khi nhiều request dùng cùng một token?
2. Token family là gì và vì sao nên tách theo session/device?
3. Vì sao check-then-act không bảo đảm single-use?
4. Compare-and-swap hoặc transaction bảo vệ invariant nào?
5. Vì sao mutex trong một process không giải quyết race giữa nhiều server instance?
6. Mô tả tình huống server đã commit RT-1 nhưng client chỉ nhận timeout; retry RT-0 nên được xử lý thế nào?
7. Idempotency key giúp gì và vì sao không phải bằng chứng xác thực?
8. Grace period giảm false positive như thế nào và mở ra rủi ro gì?
9. Reuse detection có thể thu hồi token family ra sao?
10. Vì sao refresh JWT vẫn cần trạng thái phía server nếu muốn rotation single-use?
11. Vì sao read replica eventual-consistent có thể làm hỏng quyết định refresh?
12. Sender-constrained token giảm replay ra sao nhưng không loại bỏ concurrency?
13. Thu hồi refresh token family có làm access JWT đã phát hành mất hiệu lực ngay không?
14. Những test nào chứng minh không có hai successor được tạo từ cùng một token cha?

## 20. Tiêu chuẩn và tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749), refresh token grant và lỗi invalid_grant.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009), thu hồi access token và refresh token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700), bảo vệ refresh token, rotation và phát hiện reuse.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449), sender-constrained token bằng proof-of-possession.
- [RFC 6819 — OAuth 2.0 Threat Model and Security Considerations](https://www.rfc-editor.org/rfc/rfc6819), mô hình đe dọa và rủi ro token.
