# Nonce, thời hạn ngắn và ràng buộc với ngữ cảnh yêu cầu

> **Module:** `SECURITY_TOKEN_SECURITY_JWT` — **Security - JSON Web Token (JWT)**. **Chương:** Chống phát lại. Bài viết áp dụng cho hệ thống JWT nói chung, không phụ thuộc ngôn ngữ lập trình, nền tảng hoặc framework.

## 1. Replay là gì và vì sao JWT có nguy cơ bị phát lại?

Replay attack (tấn công phát lại) xảy ra khi kẻ tấn công thu được một thông điệp hoặc credential hợp lệ rồi gửi lại nó để lặp lại hành động, truy cập tài nguyên hoặc hoàn tất một giao dịch. Thông điệp ban đầu có thể hoàn toàn hợp lệ; vấn đề nằm ở việc hệ thống chấp nhận cùng một bằng chứng nhiều lần hoặc trong một ngữ cảnh khác.

JWT dạng bearer thường được gửi trong mỗi request bằng Authorization header. Bất kỳ ai có được bearer token đều có thể sử dụng token đó trong phạm vi mà resource server chấp nhận. Chữ ký JWT chứng minh token được phát hành bởi issuer giữ khóa tương ứng và nội dung chưa bị sửa; chữ ký **không chứng minh người gửi request hiện tại chính là client ban đầu**.

Ví dụ: client nhận access token hợp lệ có quyền `payments:transfer`. Token bị lộ qua log hoặc thiết bị bị xâm nhập. Kẻ tấn công sao chép token và gửi request tới Payments API. Resource server xác minh chữ ký, issuer, audience, thời hạn và scope; tất cả đều hợp lệ. Vì token là bearer credential, server có thể chấp nhận request của kẻ tấn công.

Replay có thể xuất hiện ở nhiều lớp:

| Đối tượng bị phát lại | Ví dụ | Mục tiêu bảo vệ |
| --- | --- | --- |
| Access token bearer | Gửi lại JWT bị đánh cắp để gọi API | Giảm thời gian hữu dụng và ràng buộc token với người giữ khóa |
| ID Token | Gửi lại ID Token từ giao dịch đăng nhập trước | Liên kết ID Token với Authentication Request hiện tại |
| JWT assertion | Dùng lại assertion đã được chấp nhận để xin token | Định danh assertion duy nhất và lưu trạng thái đã dùng |
| Proof/request | Phát lại một proof ký hợp lệ hoặc request nhạy cảm | Ràng buộc proof với request, nonce và cửa sổ thời gian |
| Business operation | Gửi lại lệnh chuyển tiền hoặc tạo đơn hàng | Transaction ID dùng một lần và xử lý nghiệp vụ nguyên tử |

Không có một claim đơn lẻ nào giải quyết mọi dạng replay. Cần kết hợp nonce, thời hạn, định danh duy nhất, ràng buộc ngữ cảnh, proof-of-possession và trạng thái tiêu thụ theo đúng threat model.

## 2. Phân biệt nonce, jti, exp và request binding

| Cơ chế | Vai trò | Tự ngăn replay không? |
| --- | --- | --- |
| `nonce` | Liên kết token/proof với challenge hoặc giao dịch cụ thể | Không, nếu không kiểm tra và quản lý trạng thái |
| `jti` | Định danh duy nhất của một JWT | Không; verifier phải lưu và từ chối ID đã dùng nếu cần one-time |
| `exp` | Giới hạn thời điểm token còn được chấp nhận | Chỉ thu hẹp cửa sổ replay |
| `iat` | Cho biết thời điểm token/proof được tạo | Chỉ hỗ trợ kiểm tra độ mới; không chứng minh chưa từng được dùng |
| `nbf` | Xác định thời điểm token bắt đầu có hiệu lực | Không ngăn phát lại trong khoảng hợp lệ |
| `aud` | Ràng buộc token với recipient/resource dự kiến | Ngăn dùng token sai audience, không ngăn replay tại đúng audience |
| Request binding | Gắn proof với method, URI, client, transaction hoặc nội dung request | Có thể ngăn chuyển proof sang request khác nếu kiểm tra đầy đủ |
| Proof-of-possession | Yêu cầu người gửi chứng minh đang giữ khóa tương ứng | Ngăn người chỉ đánh cắp token dùng nó nếu khóa vẫn an toàn |
| Replay cache / one-time state | Ghi nhận nonce, jti hoặc transaction đã tiêu thụ | Có thể ngăn lần dùng lặp nếu thao tác kiểm tra và ghi là nguyên tử |

**Định danh không đồng nghĩa với trạng thái.** `jti` có thể khác nhau cho từng JWT nhưng nếu server không ghi nhận nó, cùng một JWT vẫn được chấp nhận nhiều lần trước khi hết hạn. Tương tự, nonce ngẫu nhiên có thể gắn một proof với challenge, nhưng nếu server không kiểm tra challenge còn tồn tại, chưa hết hạn và chưa được tiêu thụ, nonce chỉ là một chuỗi dữ liệu trong token.

## 3. Nonce: giá trị dùng một lần để ràng buộc giao dịch

### 3.1. Khái niệm và thuộc tính

Nonce (number used once) là giá trị được tạo để sử dụng trong một giao dịch hoặc proof cụ thể. Bên xác minh dùng nonce để kiểm tra thông điệp đang xử lý gắn với đúng challenge/giao dịch đã được khởi tạo và chưa bị tiêu thụ.

Một nonce an toàn thường có các thuộc tính:

- được tạo bằng CSPRNG;
- đủ entropy để không thể đoán thực tế;
- duy nhất trong phạm vi giao dịch và thời gian chấp nhận;
- có ngữ cảnh sử dụng rõ ràng;
- có thời hạn ngắn;
- chỉ được chấp nhận một lần khi policy yêu cầu one-time;
- được tiêu thụ theo thao tác nguyên tử.

128 bit entropy ngẫu nhiên trở lên là một lựa chọn thực tế phổ biến cho challenge khó đoán. Hệ thống có yêu cầu cao hơn có thể dùng giá trị dài hơn. Không dùng timestamp, counter đơn giản, username, email, session ID tuần tự hoặc giá trị do client tự chọn làm nonce bí mật.

Nonce không cần mang ý nghĩa nghiệp vụ. Không mã hóa user ID, tenant hoặc quyền vào nonce; lưu ngữ cảnh ở server và liên kết nonce với transaction bằng khóa tra cứu phù hợp.

### 3.2. Ai tạo nonce?

Có hai mô hình phổ biến:

- **Client-generated nonce:** client tạo nonce trước khi gửi Authentication Request. OP đưa lại giá trị vào ID Token theo quy tắc OIDC. Client kiểm tra giá trị trả về có khớp transaction đang chờ hay không.
- **Server-generated challenge nonce:** server tạo nonce và trả cho client trước khi client tạo proof/request. Client đưa nonce vào proof; server xác minh nonce thuộc challenge còn hiệu lực và chưa được dùng.

Không nhầm hai mô hình. OIDC nonce trong ID Token là claim liên kết Authentication Request; DPoP có thể dùng nonce do authorization server hoặc resource server phát hành để ràng buộc proof với challenge hiện tại. Tên trường giống nhau nhưng giao thức, nơi lưu và quy tắc kiểm tra khác nhau.

### 3.3. Quản lý nonce phía server

Nếu nonce phải dùng một lần, server cần giữ trạng thái tối thiểu:

| Trường | Mục đích |
| --- | --- |
| Nonce digest/reference | Tra cứu challenge mà không phải lưu giá trị nguyên bản nếu không cần |
| Transaction ID | Liên kết với giao dịch đang chờ |
| Subject/session reference | Giới hạn người dùng hoặc phiên được dùng |
| Client ID | Ràng buộc với client đã xác minh |
| Operation/purpose | Giới hạn mục đích, ví dụ `payment-confirm` |
| Resource/audience | Giới hạn API hoặc resource được phép |
| Expected method/URI | Ràng buộc request nếu giao thức yêu cầu |
| Created/expiry time | Xác định cửa sổ hợp lệ |
| Status | Issued, consumed, expired hoặc revoked |

Không nhất thiết lưu tất cả trường trong mọi hệ thống. Tuy nhiên, server phải đủ thông tin để không chấp nhận nonce từ transaction, client, subject hoặc operation khác.

Có thể lưu digest/HMAC của nonce thay vì nonce nguyên bản. Khi client gửi nonce, server tính digest tương ứng và tra cứu. Nếu dùng HMAC, khóa HMAC phải được quản lý riêng và bảo vệ. Với nonce entropy cao, hash phù hợp có thể đủ cho mục đích tra cứu; không dùng digest làm cơ chế thay thế cho kiểm soát truy cập.

### 3.4. Tiêu thụ nonce đúng cách

Quy trình one-time:

1. Tra cứu nonce trong namespace đúng.
2. Kiểm tra nonce tồn tại, chưa hết hạn và đang ở trạng thái `issued`.
3. Kiểm tra transaction, client, subject, resource và purpose khớp.
4. Xác minh proof/chữ ký và các điều kiện liên quan.
5. Chuyển trạng thái nonce sang `consumed` theo thao tác nguyên tử.
6. Chỉ thực hiện hành động sau khi thao tác tiêu thụ thành công.

Không thực hiện theo kiểu “đọc nonce còn active, xử lý giao dịch, rồi cuối cùng mới đánh dấu used” nếu hai request có thể chạy đồng thời. Cả hai request có thể cùng đọc trạng thái active và cùng thực hiện hành động.

Với thao tác nghiệp vụ quan trọng, việc tiêu thụ nonce và ghi nhận trạng thái giao dịch nên được phối hợp trong một transaction bền vững hoặc cơ chế chống xử lý trùng tương đương.

## 4. Nonce trong OpenID Connect

OIDC dùng claim `nonce` để liên kết ID Token với Authentication Request. Client có thể tạo nonce, gửi trong request và lưu giá trị gắn với transaction. Nếu request đã gửi nonce, ID Token trả về phải chứa giá trị tương ứng theo OIDC Core.

Quy trình:

1. Client tạo nonce ngẫu nhiên riêng cho Authentication Request.
2. Client lưu nonce cùng state/transaction đang chờ.
3. Client gửi nonce tới OpenID Provider.
4. OP đưa nonce vào ID Token khi request có nonce.
5. Client xác minh chữ ký, issuer, audience, thời gian và các quy tắc ID Token.
6. Client so sánh nonce trong ID Token với giá trị của đúng transaction.
7. Client từ chối nếu nonce thiếu, sai hoặc transaction không còn hiệu lực; sau đó tiêu thụ transaction.

OIDC nonce giúp ngăn ID Token từ một lần đăng nhập trước bị gắn nhầm vào giao dịch hiện tại. Nó không biến access token bearer thành proof-of-possession và không tự ngăn việc phát lại một API request đã được xác thực.

`state` và PKCE vẫn có vai trò riêng:

- `state` liên kết request với callback và hỗ trợ bảo vệ luồng điều hướng khỏi CSRF.
- `nonce` liên kết ID Token với Authentication Request.
- PKCE ràng buộc việc đổi authorization code với client giữ `code_verifier`.

Không dùng nonce thay state hoặc PKCE; cũng không coi việc kiểm tra nonce là thay thế xác minh chữ ký và issuer của ID Token.

## 5. Nonce trong DPoP và proof-of-possession

### 5.1. Vì sao bearer token cần ràng buộc người gửi?

Với bearer token, việc có token là đủ để sử dụng. Proof-of-possession (PoP) thay đổi mô hình: client phải chứng minh đang kiểm soát khóa được ràng buộc với token.

DPoP là cơ chế ở tầng ứng dụng trong OAuth 2.0 để client tạo proof JWT ký bằng khóa riêng. Access token có thể được ràng buộc với public key tương ứng; resource server kiểm tra proof và token binding trước khi chấp nhận request.

Một DPoP proof thường chứa các thông tin như:

- `jti`: định danh proof duy nhất;
- `htm`: HTTP method;
- `htu`: HTTP target URI;
- `iat`: thời điểm tạo proof;
- `ath`: hash của access token khi proof được gửi cùng access token;
- `nonce`: challenge nonce nếu server yêu cầu.

DPoP proof không phải access token. Nó là bằng chứng client đang giữ khóa và proof được tạo cho một request cụ thể.

### 5.2. Server nonce trong DPoP

Authorization server hoặc resource server có thể yêu cầu client sử dụng nonce bằng cách gửi challenge nonce trong response. Client tạo DPoP proof tiếp theo và đưa nonce vào claim `nonce`.

Verifier kiểm tra nonce proof khớp nonce server đã phát hành và nonce vẫn trong thời hạn. Nonce server giúp chống việc kẻ tấn công tạo trước proof hoặc dùng proof trong một challenge/ngữ cảnh khác. Tuy nhiên, nếu cùng nonce vẫn được chấp nhận cho nhiều proof trong cửa sổ hiệu lực, một proof đã bị thu thập vẫn có thể bị gửi lại trong cửa sổ đó. Khi cần chống phát lại proof đã dùng, verifier còn phải áp dụng phát hiện `jti` trùng lặp hoặc cơ chế trạng thái one-time tương đương.

Cần phân biệt:

- nonce do server phát hành là challenge;
- nonce được client đưa vào proof là bằng chứng trả lời challenge;
- `jti` của proof định danh proof cụ thể;
- `iat` giới hạn tuổi proof;
- `htm`/`htu` gắn proof với method và URI;
- `ath` gắn proof với access token được dùng.

DPoP nonce không phải claim `nonce` của ID Token OIDC, dù tên giống nhau.

### 5.3. Ràng buộc access token với khóa

Trong DPoP, access token có thể chứa confirmation claim `cnf` với thumbprint của public key (ví dụ `jkt`). Resource server xác minh proof được ký bởi private key tương ứng với public key mà token ràng buộc.

Nếu kẻ tấn công chỉ đánh cắp access token nhưng không có private key, họ không thể tạo proof hợp lệ cho request. Nếu token và private key cùng bị xâm nhập, cơ chế này không còn ngăn được kẻ tấn công.

DPoP giảm nguy cơ sử dụng token bị đánh cắp đơn lẻ; nó không thay thế bảo vệ thiết bị, khóa, TLS, TTL, authorization và giám sát.

### 5.4. Không tự mở rộng ý nghĩa chuẩn của DPoP

DPoP chuẩn ràng buộc proof với HTTP method, URI, access token và các thông tin proof như `jti`, `iat`, nonce. Nó không mặc định ký toàn bộ request body. Nếu ứng dụng cần chống thay đổi hoặc phát lại nội dung body cụ thể, phải dùng cơ chế request signing/body digest có đặc tả rõ ràng, canonicalization thống nhất và kiểm tra ở bên nhận.

Không tự thêm claim body hash rồi tuyên bố đó là DPoP chuẩn. Có thể thiết kế extension hoặc dùng chuẩn ký thông điệp HTTP phù hợp, nhưng mọi bên phải thống nhất semantics và cách canonicalize dữ liệu.

## 6. Thời hạn ngắn: thu hẹp cửa sổ replay

### 6.1. Access token TTL ngắn

Claim `exp` xác định thời điểm JWT hết hạn. Access token có TTL ngắn làm giảm khoảng thời gian kẻ tấn công có thể sử dụng bearer token bị lộ.

TTL nên được chọn dựa trên:

- độ nhạy cảm của API và dữ liệu;
- scope/permission được cấp;
- loại client và khả năng bảo vệ token;
- khả năng revoke/introspection hoặc kiểm tra trạng thái;
- tần suất refresh và năng lực authorization server;
- yêu cầu trải nghiệm và khả năng chịu lỗi.

Không có một giá trị TTL duy nhất đúng cho mọi hệ thống. Một access token có quyền thanh toán hoặc quản trị có thể cần TTL ngắn hơn token chỉ đọc dữ liệu ít nhạy cảm.

### 6.2. TTL ngắn không ngăn replay trong cửa sổ hợp lệ

Giả sử access token có TTL 5 phút và bị đánh cắp ngay sau khi phát hành. Kẻ tấn công vẫn có thể sử dụng nó trong gần 5 phút nếu resource server chấp nhận bearer token.

Do đó:

- TTL ngắn **giảm thời gian phơi nhiễm**;
- nonce/challenge **liên kết thông điệp với giao dịch**;
- `jti` và replay cache **phát hiện hoặc từ chối lần dùng lặp**;
- PoP **ràng buộc người gửi với khóa**;
- request binding **giới hạn proof vào ngữ cảnh request**;
- revoke/introspection **cho phép kiểm tra trạng thái hiện tại**.

Các biện pháp bổ sung nhau, không thay thế nhau.

### 6.3. Kiểm tra iat, exp và nbf

Verifier nên kiểm tra:

- `exp` tồn tại nếu token profile yêu cầu và có kiểu NumericDate hợp lệ;
- token chưa hết hạn, với clock skew nhỏ được cấu hình;
- `iat` không nằm trong tương lai vượt leeway;
- tuổi token không vượt giới hạn tối đa của profile;
- `nbf` nếu có phải phù hợp thời điểm hiện tại;
- thời gian phát hành và hết hạn không mâu thuẫn.

Với proof ngắn hạn, verifier thường cần kiểm tra `iat` nằm trong một cửa sổ tuổi hẹp hơn TTL access token. Không chỉ kiểm tra `exp`: một proof có thể được phát hành từ lâu nhưng vẫn chưa hết hạn theo một cấu hình quá rộng.

### 6.4. Clock skew và đồng bộ thời gian

Các node có thể lệch đồng hồ. Nếu mỗi node dùng một leeway khác nhau, token/proof có thể được chấp nhận ở node này nhưng bị từ chối ở node khác.

- Đồng bộ đồng hồ bằng nguồn thời gian tin cậy.
- Đặt clock skew nhỏ, thống nhất.
- Tính thời gian replay cache bao phủ cả cửa sổ chấp nhận và leeway.
- Không tăng leeway lớn để che lỗi đồng bộ.
- Dùng UTC/NumericDate nhất quán khi tạo và xác minh.

## 7. jti và replay cache cho JWT dùng một lần

### 7.1. jti không tự tạo one-time semantics

`jti` là registered claim định danh JWT. Issuer nên tạo giá trị duy nhất cho mỗi token trong phạm vi phù hợp. Tuy nhiên, cùng một JWT có thể được gửi nhiều lần và vẫn có cùng `jti`; verifier chỉ từ chối lần thứ hai nếu có lưu trạng thái đã dùng.

Một verifier có thể xây dựng replay key từ:

- issuer (`iss`);
- client hoặc subject theo profile;
- loại token/purpose;
- `jti`.

Namespace tránh việc hai issuer độc lập vô tình dùng cùng một `jti` hoặc một loại token bị lẫn với loại khác.

### 7.2. Khi nào cần lưu jti đã dùng?

Replay cache phù hợp với:

- JWT client assertion dùng một lần để xác thực client;
- JWT bearer assertion trong một giao thức yêu cầu chống replay;
- token xác nhận một hành động hoặc giao dịch duy nhất;
- proof JWT có `jti` cần từ chối sử dụng lại;
- thông điệp ký có thời hạn ngắn và semantics one-time.

Không phải mọi access token JWT đều cần đánh dấu `jti` đã dùng sau request đầu tiên. Access token thường được thiết kế để dùng nhiều lần trong TTL; nếu resource server tiêu thụ `jti` sau request đầu, token sẽ không thể gọi API tiếp theo. Chỉ áp dụng one-time semantics khi giao thức hoặc nghiệp vụ thực sự yêu cầu.

### 7.3. Thao tác insert-if-absent nguyên tử

Một mẫu replay cache:

~~~text
function acceptOneTimeJwt(token):
    claims = verifyJwtAndValidateProfile(token)

    require claims.jti exists
    require claims.exp > now
    require tokenAgeWithinPolicy(claims.iat)

    replayKey = namespace(
        claims.iss,
        claims.client_id,
        claims.purpose,
        claims.jti
    )

    inserted = replayStore.insertIfAbsent(
        replayKey,
        expiresAt = claims.exp + allowedClockSkew
    )

    require inserted == true
    return ACCEPT
~~~

Điểm quyết định là `insertIfAbsent` phải nguyên tử. Không dùng thao tác riêng biệt `GET` rồi `SET`, vì hai request đồng thời có thể cùng thấy key chưa tồn tại và cùng được chấp nhận.

TTL của cache entry phải bao phủ toàn bộ khoảng thời gian token còn có thể được chấp nhận, gồm leeway và độ trễ cần thiết. Nếu xóa entry quá sớm, token cũ có thể được replay trong khi verifier vẫn chấp nhận theo clock skew.

## 8. Ràng buộc proof với ngữ cảnh yêu cầu

Một proof hoặc token cần được kiểm tra trong ngữ cảnh mà nó được tạo ra. Tùy giao thức, ngữ cảnh có thể gồm:

| Thành phần | Ý nghĩa |
| --- | --- |
| Issuer | Ai phát hành token/proof |
| Subject | Danh tính hoặc chủ thể được đại diện |
| Client/actor | Thành phần đang thực hiện request |
| Audience/resource | API hoặc tài nguyên đích |
| HTTP method | GET, POST, PATCH, DELETE... |
| Target URI | Endpoint cụ thể mà proof được tạo cho |
| Access token hash | Token mà proof đang sử dụng |
| Transaction ID | Giao dịch nghiệp vụ đang chờ |
| Tenant | Phạm vi tổ chức/dữ liệu |
| Purpose/action | Hành động cụ thể như xác nhận thanh toán |
| Body digest | Hash nội dung request nếu cơ chế ký hỗ trợ và quy định rõ |

### 8.1. Audience và resource

`aud` ràng buộc token với recipient dự kiến. Verifier phải kiểm tra audience phù hợp với API hiện tại. Không chấp nhận token chỉ vì chữ ký đúng.

Tuy nhiên, audience đúng không ngăn replay tại đúng API đó. Nếu bearer token dành cho Payments API bị đánh cắp, kẻ tấn công vẫn có thể gửi tới Payments API cho đến khi token hết hạn hoặc bị chặn. Cần PoP, request binding hoặc kiểm tra trạng thái nếu threat model yêu cầu.

### 8.2. HTTP method và URI

Proof gắn với `POST /payments/confirm` không nên được chấp nhận cho `DELETE /payments/123` hoặc một URI khác. DPoP dùng `htm` và `htu` để ràng buộc proof với method và target URI theo quy tắc chuẩn.

Khi xác minh URI, các bên phải áp dụng cùng quy tắc chuẩn hóa. Reverse proxy có thể thay đổi scheme, host hoặc path được nhìn thấy ở phía ứng dụng. Chỉ tin forwarded headers từ proxy được cấu hình tin cậy; không lấy Host hoặc forwarding header do client tự khai để tạo ngữ cảnh xác minh.

Không tự ý decode, đổi thứ tự query parameters hoặc chuẩn hóa path khác nhau giữa signer và verifier. Nếu hai bên tính URI khác nhau, proof hợp lệ có thể bị từ chối hoặc binding có thể bị suy yếu.

### 8.3. Access token hash

Với DPoP, `ath` là hash của access token theo quy tắc giao thức. Nó liên kết proof với đúng access token đang được gửi. Proof được tạo cho token A không thể tùy ý dùng kèm token B nếu verifier kiểm tra `ath`.

Không tự thay thuật toán hash hoặc cách mã hóa digest. Hãy tuân thủ chính xác profile DPoP và thư viện JOSE tương thích.

### 8.4. Body digest và request signing

Nếu nghiệp vụ yêu cầu proof bao phủ nội dung body, phải xác định:

- byte sequence nào được hash;
- encoding và canonicalization của JSON;
- có tính các header quan trọng hay không;
- digest được ký ở đâu và bằng thuật toán nào;
- server kiểm tra digest trên đúng byte nhận được hay trên bản parse/serialize lại;
- cách xử lý content encoding, multipart hoặc streaming body.

JSON có thể có nhiều biểu diễn byte khác nhau nhưng cùng ý nghĩa. Nếu signer hash JSON trước serialization còn server hash JSON sau khi serialize lại, digest có thể khác. Ngược lại, nếu canonicalization không rõ, hai payload khác nhau có thể bị coi là tương đương.

DPoP chuẩn không tự ràng buộc body. Với yêu cầu ký request đầy đủ, cân nhắc chuẩn HTTP Message Signatures (RFC 9421) hoặc profile ứng dụng được đặc tả rõ, thay vì tự thêm một claim tùy ý rồi gọi đó là DPoP.

## 9. Kết hợp nonce, thời hạn, jti và request binding

Một mô hình proof one-time có thể dùng:

- server tạo nonce ngẫu nhiên và gắn với client/session/operation;
- client tạo proof JWT có `jti` mới, `iat` mới và nonce challenge;
- proof mang audience/resource, method/URI hoặc các thành phần request theo profile;
- proof được ký bằng private key mà client kiểm soát;
- server xác minh chữ ký, key binding, nonce, thời gian, request context;
- server tiêu thụ nonce và `jti` theo thao tác nguyên tử;
- server chỉ thực hiện nghiệp vụ sau khi proof được chấp nhận.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    participant R as Replay Store

    C->>S: Yêu cầu challenge cho operation
    S->>R: Lưu nonce + context + expiry
    S-->>C: Nonce challenge
    C->>C: Tạo proof (jti, iat, nonce, request binding)
    C->>S: Request + access token + proof
    S->>S: Verify token, proof, key, time, method/URI
    S->>R: Atomic consume nonce/jti
    alt Challenge còn hợp lệ và chưa dùng
        R-->>S: Consume thành công
        S->>S: Thực hiện operation
        S-->>C: Kết quả
    else Đã hết hạn hoặc đã dùng
        R-->>S: Consume thất bại
        S-->>C: Từ chối request
    end
~~~

Trình tự có thể khác theo giao thức cụ thể. Điều quan trọng là không thực hiện side effect trước khi xác minh proof và bảo đảm trạng thái one-time không bị race.

## 10. Thời hạn nonce và cache entry

Nonce/challenge thường cần thời hạn ngắn để giảm cơ hội bị đánh cắp và phát lại. Thời hạn phải đủ để client nhận challenge, tạo proof và gửi request trong điều kiện mạng thực tế.

Khi chọn TTL, cân nhắc:

- độ trễ mạng p95/p99;
- thao tác người dùng có cần xác nhận hoặc tương tác không;
- thời gian client tạo proof;
- clock skew giữa client/server;
- số lần retry được phép;
- độ trễ đồng bộ trạng thái giữa các node;
- mức độ nhạy cảm của operation.

Không dùng TTL dài chỉ để tránh người dùng phải lấy challenge lại. Với thao tác có tương tác lâu, có thể tách transaction lifetime khỏi proof nonce lifetime: transaction có thể còn chờ, nhưng mỗi proof cần nonce mới theo chính sách.

Replay cache phải giữ entry ít nhất đến khi token/proof không còn được chấp nhận ở bất kỳ verifier nào. Nếu `exp` là 10:00 và server chấp nhận clock skew 30 giây, entry không nên bị xóa trước khi mọi verifier chắc chắn từ chối token sau cửa sổ đó. Cần tính thêm độ trễ replication hoặc propagation nếu cache phân tán.

## 11. Concurrency, retry và phân tán

### 11.1. Race condition khi dùng một nonce

Hai request có thể cùng trình một nonce hợp lệ gần như đồng thời. Nếu hệ thống chỉ đọc trạng thái rồi mới ghi used, cả hai có thể vượt qua.

Giải pháp:

- thao tác compare-and-set hoặc insert-if-absent nguyên tử;
- khóa theo transaction/nonce khi cần;
- unique constraint trong kho dữ liệu bền vững;
- cập nhật trạng thái transaction và side effect trong cùng ranh giới giao dịch nếu có thể;
- idempotency record cho kết quả nghiệp vụ khi client retry.

### 11.2. Nhiều node và nhiều region

Replay cache local trên từng node không đủ nếu cùng một proof có thể được gửi tới node khác. Ví dụ request đầu tới Region A, request phát lại tới Region B trước khi trạng thái replay được đồng bộ; cả hai có thể được chấp nhận.

Các lựa chọn:

- kho trạng thái dùng chung với consistency phù hợp;
- phân vùng nonce theo transaction và định tuyến request về một vùng có thẩm quyền;
- dùng cơ chế consensus/atomic uniqueness khi mức rủi ro yêu cầu;
- dùng lease hoặc partitioned ownership có giới hạn rõ;
- chấp nhận cửa sổ propagation chỉ khi threat model và nghiệp vụ cho phép.

Không giả định eventual consistency đủ cho one-time payment hoặc thao tác không thể hoàn tác. Với hành động tài chính hoặc side effect quan trọng, cần kiểm soát duplicate ở tầng nghiệp vụ/database.

### 11.3. Retry không đồng nghĩa replay attack

Client có thể không nhận được response dù server đã thực hiện operation. Khi retry, cùng một request có thể xuất hiện lần nữa. Hệ thống cần phân biệt retry hợp lệ và replay độc hại bằng transaction/idempotency key, proof mới hoặc trạng thái giao dịch.

- **Nonce/proof one-time:** bảo đảm proof cụ thể chỉ được chấp nhận một lần.
- **Idempotency key:** cho phép cùng một thao tác được gửi lại mà không thực hiện side effect lần hai, thường trả lại kết quả đã lưu.
- **Transaction ID:** liên kết các lần thử vào cùng một nghiệp vụ.
- **Replay cache:** từ chối credential/proof đã được dùng.

Idempotency key không phải bằng chứng xác thực và không thay thế nonce/PoP. Một kẻ tấn công có thể gửi idempotency key giống request hợp lệ; server vẫn phải xác minh quyền và proof. Ngược lại, từ chối mọi request retry chỉ vì nonce đã dùng có thể làm client không khôi phục được kết quả khi response bị mất.

### 11.4. Thứ tự xử lý với side effect

Với giao dịch nhạy cảm, cần phối hợp:

1. xác minh access token và proof;
2. kiểm tra request context và quyền;
3. kiểm tra trạng thái transaction;
4. tiêu thụ proof/nonce một cách nguyên tử;
5. ghi nhận operation hoặc idempotency result;
6. thực hiện side effect theo transaction/outbox phù hợp;
7. trả kết quả và ghi audit.

Nếu hệ thống không thể gộp tất cả trong một transaction, phải có state machine và cơ chế recovery rõ ràng. Tránh tình huống nonce đã consumed nhưng nghiệp vụ chưa thực hiện và không thể retry, hoặc nghiệp vụ đã thực hiện nhưng nonce chưa consumed nên bị chạy lại.

## 12. Ví dụ: xác nhận thanh toán một lần

Một ứng dụng yêu cầu người dùng xác nhận khoản thanh toán. Chỉ có access token bearer ngắn hạn là chưa đủ để ngăn request bị phát lại trong thời hạn token.

Mô hình có challenge:

1. Client đã có phiên và access token hợp lệ.
2. Client yêu cầu server tạo challenge cho payment transaction cụ thể.
3. Server tạo nonce ngẫu nhiên, liên kết với subject, client, payment ID, amount, currency, purpose và expiry.
4. Client ký proof hoặc dùng cơ chế PoP đã thỏa thuận để chứng minh quyền kiểm soát khóa.
5. Request gửi kèm access token, proof và payment data.
6. Server xác minh token, chữ ký proof, nonce, transaction context và quyền.
7. Server kiểm tra amount/currency/payment ID khớp dữ liệu giao dịch đã lưu.
8. Server atomically consume challenge và chuyển payment transaction sang trạng thái xử lý.
9. Nếu cùng proof hoặc challenge được gửi lại, server từ chối hoặc trả kết quả idempotent đã lưu mà không thực hiện thanh toán lần hai.

Không chỉ đưa `payment_id` vào JWT rồi coi đó là chống replay. Kẻ tấn công có thể phát lại toàn bộ JWT. Phải kiểm tra trạng thái giao dịch và đảm bảo side effect chỉ xảy ra một lần.

## 13. Mã giả tạo và xác minh challenge

### 13.1. Tạo challenge

~~~text
function createChallenge(authenticatedContext, operation):
    require authenticatedContext.isValid
    require operation is allowed for authenticatedContext.subject

    nonce = secureRandomBytes(32)
    transactionId = createUniqueTransactionId()

    challengeStore.insert(
        nonceDigest = secureDigest(nonce),
        transactionId = transactionId,
        subject = authenticatedContext.subject,
        client = authenticatedContext.client,
        purpose = operation.purpose,
        resource = operation.resource,
        expectedMethod = operation.method,
        expectedUri = operation.uri,
        expiresAt = now + challengeTtl,
        status = ISSUED
    )

    return {
        nonce: base64url(nonce),
        transactionId: transactionId,
        expiresAt: now + challengeTtl
    }
~~~

Ví dụ dùng 32 byte ngẫu nhiên (256 bit). Kích thước thực tế phải phù hợp protocol và threat model. Giá trị nonce trả về là challenge, không phải access token.

### 13.2. Xác minh proof và tiêu thụ challenge

~~~text
function verifyOneTimeRequest(request):
    access = verifyAccessToken(request.accessToken)
    proof = verifyProofSignatureAndKeyBinding(request.proof)

    require proof.iat is within allowedProofAge
    require proof.jti exists and is unique
    require proof.nonce exists
    require proof.method == request.method
    require proof.uri == canonicalTrustedRequestUri(request)
    require proof.audience == expectedResource
    require proof.subject == access.subject

    challenge = challengeStore.find(
        secureDigest(decodeNonce(proof.nonce))
    )

    require challenge.status == ISSUED
    require challenge.expiresAt > now
    require challenge.subject == access.subject
    require challenge.client == access.client
    require challenge.purpose == request.operation
    require challenge.resource == expectedResource
    require challenge.expectedMethod == request.method
    require challenge.expectedUri == canonicalTrustedRequestUri(request)

    require replayStore.insertIfAbsent(
        namespace(access.issuer, access.client, proof.jti),
        expiresAt = proof.iat + proofAcceptanceWindow
    )

    require challengeStore.consumeAtomically(challenge.id)
    return executeOperationIdempotently(request)
~~~

Mã giả minh họa ranh giới kiểm tra. Thực tế cần phối hợp việc tiêu thụ challenge, ghi `jti` đã dùng, idempotency result và side effect trong một giao dịch hoặc state machine bền vững. Nếu các bước không thể nằm trong cùng transaction, cần có cơ chế rollback/recovery rõ ràng để tránh trạng thái nửa chừng. Với DPoP, dùng đúng claim và quy tắc RFC 9449; không tự coi các trường pseudocode là claim chuẩn DPoP.

## 14. Các lỗi thiết kế thường gặp

| Lỗi | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| Nghĩ nonce trong JWT tự ngăn token bị phát lại | Token vẫn có thể được gửi lại nguyên vẹn | Kiểm tra nonce theo transaction và trạng thái |
| Chỉ dùng `exp` | Replay vẫn xảy ra trong TTL | Kết hợp PoP, jti/replay cache hoặc one-time challenge |
| Dùng `jti` nhưng không lưu trạng thái đã dùng | Verifier không biết JWT đã được chấp nhận trước đó | Dùng replay cache nguyên tử khi one-time semantics cần thiết |
| Tái sử dụng nonce | Proof cũ có thể được gắn vào giao dịch khác | Nonce mới cho từng challenge/transaction |
| Nonce không gắn với subject/client/purpose | Challenge có thể bị chuyển giữa người dùng hoặc operation | Lưu và kiểm tra ngữ cảnh |
| TTL challenge quá dài | Tăng cửa sổ replay | TTL ngắn theo thời gian thực hiện và threat model |
| Replay cache local theo node | Phát lại tới node khác có thể được chấp nhận | Dùng state chung/partition có thẩm quyền |
| Kiểm tra nonce rồi mới đánh dấu used không nguyên tử | Hai request đồng thời cùng vượt qua | Atomic consume/unique constraint |
| Tiêu thụ nonce trước khi kiểm tra proof | Request không hợp lệ có thể làm cạn challenge | Xác minh proof và context trước; consume nguyên tử ở ranh giới commit |
| Tin forwarded headers tùy ý | URI binding có thể bị giả mạo | Chỉ tin proxy headers từ intermediary đã cấu hình |
| Dùng IP/User-Agent làm sender binding | Dễ thay đổi, chia sẻ hoặc giả mạo | Dùng PoP/khóa và transaction binding |
| Coi DPoP tự ký body | Proof chuẩn không bao phủ body theo mặc định | Dùng request signing/body digest được đặc tả |
| Nhầm idempotency key với nonce | Idempotency không chứng minh danh tính/người giữ khóa | Kết hợp idempotency với authentication và PoP |
| Refresh token làm mới access token nhưng giữ nguyên quyền cũ | Quyền đã thu hồi có thể được cấp lại | Tính lại policy/grant trước mỗi lần refresh |

## 15. Kiểm thử chống replay

| Nhóm | Ca kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| Nonce | Nonce đúng, còn hạn, đúng transaction | Chấp nhận một lần |
| Nonce | Nonce sai hoặc không tồn tại | Từ chối |
| Nonce | Nonce hết hạn | Từ chối |
| Nonce | Nonce đã consumed | Từ chối lần dùng lại |
| Context | Nonce của subject A dùng bởi subject B | Từ chối |
| Context | Nonce của client A dùng bởi client B | Từ chối |
| Purpose | Challenge xác nhận payment dùng cho thao tác khác | Từ chối |
| Request binding | Proof cho POST được gửi tới DELETE | Từ chối |
| Request binding | Proof cho URI A gửi tới URI B | Từ chối |
| Token binding | DPoP proof gắn token A nhưng request gửi token B | Từ chối |
| Proof age | `iat` quá cũ hoặc nằm trong tương lai ngoài leeway | Từ chối |
| jti | Proof `jti` đã được chấp nhận trước đó | Từ chối |
| Concurrency | Hai request đồng thời dùng cùng nonce/jti | Chỉ một request tiêu thụ thành công |
| Distributed | Request đầu vào node/region A, replay vào B | Replay bị từ chối |
| Lost response | Server đã xử lý nhưng client retry | Không tạo side effect lần hai; trả kết quả theo idempotency policy |
| Access token | Bearer token bị phát lại trong TTL | Bị hạn chế bởi PoP/revoke hoặc policy được chọn; không giả định TTL tự ngăn |
| Cache expiry | Replay entry bị xóa trước cửa sổ chấp nhận kết thúc | Test phải phát hiện và ngăn cấu hình sai |
| Key compromise | Token và khóa PoP cùng bị lộ | Hành vi được giới hạn bằng revoke, TTL, monitoring và recovery |

Nên kiểm thử fuzzing các trường nonce, `jti`, URI, method, timestamp và token header. Kiểm thử tải đồng thời và multi-region đặc biệt quan trọng vì lỗi replay thường xuất hiện ở race condition hoặc độ trễ đồng bộ trạng thái.

## 16. Giám sát và ứng phó khi phát hiện replay

Các sự kiện nên được ghi nhận ở mức đủ điều tra:

- nonce không tồn tại, hết hạn hoặc đã dùng;
- `jti` trùng lặp;
- DPoP proof sai method/URI hoặc token hash;
- proof có `iat` ngoài cửa sổ;
- sender constraint thất bại;
- cùng transaction được gửi từ nhiều client/device;
- cùng refresh token/proof xuất hiện bất thường;
- replay cache lỗi, mất kết nối hoặc consistency suy giảm.

Event nên có issuer, client, subject reference đã giả danh hóa, transaction ID, purpose, audience, reason code và thời điểm. Không log access token, refresh token, private key hoặc nonce nguyên vẹn.

Khi phát hiện replay:

1. Từ chối proof/request lặp.
2. Xác định credential, transaction, client và resource bị ảnh hưởng.
3. Đánh giá token hoặc khóa có thể đã bị lộ hay không.
4. Thu hồi grant/token hoặc yêu cầu xác thực lại khi cần.
5. Bảo toàn audit event và điều tra side effect đã xảy ra.
6. Kiểm tra cache/atomicity/replication để xác định vì sao replay vượt qua.
7. Cập nhật policy, TTL, key binding hoặc quy trình recovery.

Không tự động khóa mọi tài khoản từ cùng một IP; có thể có NAT hoặc proxy dùng chung. Hành động phải dựa trên nhiều tín hiệu và phạm vi ảnh hưởng.

## 17. Checklist triển khai

**Nonce và transaction:**

- [ ] Nonce được tạo bằng CSPRNG với entropy phù hợp.
- [ ] Mỗi transaction/challenge có nonce riêng.
- [ ] Nonce gắn với client, subject/session, resource và purpose khi cần.
- [ ] Challenge có expiry ngắn và được lưu ở nơi bảo vệ.
- [ ] Nonce được tiêu thụ nguyên tử; không chấp nhận lần dùng lại.
- [ ] Phân biệt OIDC nonce, server challenge và DPoP nonce.

**Token/proof freshness:**

- [ ] Access token có TTL phù hợp rủi ro và audience.
- [ ] Verifier kiểm tra `iat`, `nbf`, `exp` và clock skew.
- [ ] Proof có `jti` mới và cửa sổ tuổi ngắn khi profile yêu cầu.
- [ ] Replay cache giữ entry tới hết cửa sổ chấp nhận.
- [ ] Không coi `jti`, `nonce` hoặc `exp` riêng lẻ là replay protection hoàn chỉnh.

**Request binding và PoP:**

- [ ] Audience/resource được kiểm tra.
- [ ] Method/URI được ràng buộc theo profile.
- [ ] URI canonicalization và proxy trust được thống nhất.
- [ ] DPoP proof được kiểm tra với đúng access token (`ath`) và khóa (`cnf`/key thumbprint).
- [ ] mTLS/DPoP sender constraint được kiểm tra khi token yêu cầu.
- [ ] Body digest chỉ dùng khi có đặc tả ký request rõ ràng.

**Phân tán và nghiệp vụ:**

- [ ] Replay cache có thao tác nguyên tử.
- [ ] Nhiều node/region không chấp nhận cùng proof do propagation delay.
- [ ] Retry được phân biệt với replay bằng transaction/idempotency state.
- [ ] Side effect và trạng thái one-time có recovery/transaction rõ.
- [ ] Có kiểm thử concurrency, lost response và replay cross-region.

**Vận hành:**

- [ ] Có metric/alert cho nonce reuse, jti duplicate và proof failure.
- [ ] Không log token, secret, private key hoặc nonce nguyên vẹn.
- [ ] Có quy trình revoke và điều tra credential bị lộ.
- [ ] Có chính sách khi replay store unavailable; thao tác nhạy cảm không âm thầm bỏ qua kiểm tra one-time.

## 18. Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): registered claims `jti`, `iat`, `nbf`, `exp`, `iss` và `aud`.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh JWT theo profile và tránh nhầm lẫn giữa các loại token.
- [OpenID Connect Core 1.0 — ID Token](https://openid.net/specs/openid-connect-core-1_0.html#IDToken): claim nonce và xác minh ID Token.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): DPoP proof, `jti`, `htm`, `htu`, `ath`, nonce và token binding.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): ràng buộc access token với chứng thư client.
- [RFC 7523 — JSON Web Token (JWT) Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523): JWT assertion và các claim dùng trong OAuth.
- [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421): ký các thành phần HTTP message và ràng buộc chữ ký với request.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access token, refresh token và authorization server.

**Ghi nhớ:** Nonce liên kết proof hoặc token với một challenge/giao dịch; thời hạn ngắn chỉ thu hẹp cửa sổ replay; `jti` chỉ là định danh cho tới khi verifier lưu trạng thái đã dùng; request binding và proof-of-possession giúp giới hạn ai có thể dùng proof và dùng trong ngữ cảnh nào. Muốn chống replay thực sự, hãy xác minh đầy đủ token/proof, kiểm tra freshness và context, tiêu thụ trạng thái one-time một cách nguyên tử, đồng thời thiết kế retry và side effect để không thực hiện giao dịch hai lần.

