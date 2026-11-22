# Đánh đổi giữa chống phát lại, trạng thái và tính sẵn sàng

## 1. Vì sao chống phát lại luôn có chi phí?

Một JSON Web Token (JWT) có chữ ký hợp lệ có thể được gửi lại nhiều lần trong thời hạn hiệu lực. Với bearer token, bên nào lấy được token thường có thể sử dụng token đó cho đến khi token hết hạn hoặc bị hệ thống từ chối. Chữ ký bảo vệ tính toàn vẹn và nguồn ký; nó không tự chứng minh token chưa từng được sử dụng.

Đây là bài toán **replay attack**: kẻ tấn công ghi lại một thông điệp, proof hoặc token hợp lệ rồi phát lại để khiến hệ thống thực hiện lại hành động. Phát lại có thể nhằm:

- Dùng lại access token bị đánh cắp để gọi API.
- Gửi lại một request đã được ký hoặc xác thực.
- Redeem lại authorization code hoặc refresh token đã dùng.
- Lặp lại một thao tác nghiệp vụ như chuyển tiền, tạo đơn hoặc xác nhận giao dịch.

Muốn phát hiện một giá trị đã được dùng trước đó, hệ thống thường phải nhớ trạng thái đã thấy nó. Điều này tạo ra một đánh đổi:

- **Ít trạng thái hơn:** giảm lưu trữ và độ trễ, nhưng khó phát hiện cùng token/proof được dùng lại.
- **Nhiều trạng thái hơn:** phát hiện replay chính xác hơn, nhưng cần kho dữ liệu, đồng bộ giữa instance và xử lý khi kho trạng thái không khả dụng.
- **Tăng tính sẵn sàng:** có thể tiếp tục xử lý khi kho trạng thái lỗi, nhưng nguy cơ chấp nhận replay tăng nếu bỏ qua kiểm tra.

Không có một cơ chế duy nhất phù hợp cho mọi loại replay. Cần xác định hành động nào cần bảo vệ, hậu quả của việc lặp lại, thời gian replay có thể xảy ra và mức độ sẵn sàng mà hệ thống phải duy trì.

## 2. Phân biệt ba loại replay

Các khái niệm thường được gọi chung là replay prevention nhưng có mục tiêu khác nhau:

| Loại | Kẻ tấn công phát lại | Mục tiêu phòng vệ |
| --- | --- | --- |
| Bearer token replay | Access token hoặc refresh token bị đánh cắp | Ngăn bên không sở hữu token hợp lệ sử dụng token |
| Proof/request replay | Một proof có chữ ký, nonce hoặc request đã xác thực | Ngăn cùng bằng chứng/request được chấp nhận nhiều lần hoặc ngoài thời gian cho phép |
| Business operation replay | Yêu cầu nghiệp vụ đã gửi trước đó | Ngăn tạo tác động nghiệp vụ trùng lặp như trừ tiền hoặc tạo đơn hai lần |

Một cơ chế chỉ bảo vệ một lớp có thể không bảo vệ hai lớp còn lại. Ví dụ:

- DPoP có thể ràng buộc access token với proof-of-possession và phát hiện proof bị phát lại, nhưng không tự bảo đảm một thao tác thanh toán chỉ được ghi sổ một lần.
- Idempotency key có thể ngăn một yêu cầu tạo đơn bị thực hiện hai lần, nhưng không chứng minh access token gửi kèm chưa bị đánh cắp.
- JWT có thời hạn ngắn làm giảm cửa sổ sử dụng token bị lộ, nhưng không ngăn token được dùng lại nhiều lần trong cửa sổ đó.

Thiết kế cần nêu rõ đang ngăn loại replay nào và ở lớp nào.

## 3. Vì sao JWT thuần túy không tự phát hiện token đã dùng?

JWT có chữ ký thường được xác minh bằng dữ liệu trong token và khóa tin cậy. Hai request mang cùng một token sẽ có cùng nội dung và cùng chữ ký. Nếu token vẫn còn hạn, có đúng issuer/audience và thỏa các điều kiện khác, verifier không có thông tin nào trong chính token để biết request thứ hai là replay.

Ví dụ:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user_42",
  "aud": "https://api.payments.example.org",
  "exp": 1893456900,
  "jti": "token-83af",
  "scope": "payments:submit"
}
~~~

Claim **jti** cung cấp định danh cho JWT. Nó không tự tạo ra hành vi one-time-use. Nếu resource server không lưu hoặc kiểm tra trạng thái của jti, cùng token có thể được gửi lại nhiều lần.

Các claim thời gian cũng không tự chống replay:

- **exp** giới hạn thời điểm token không còn được chấp nhận.
- **nbf** giới hạn thời điểm token bắt đầu có hiệu lực.
- **iat** cho biết thời điểm phát hành.
- **jti** định danh token.

Chúng hữu ích cho giới hạn thời gian, kiểm toán và tra cứu, nhưng không thay thế một cơ chế phát hiện sử dụng lặp lại. Muốn một JWT chỉ được dùng một lần, hệ thống phải thực thi trạng thái đã sử dụng hoặc một cơ chế tương đương.

## 4. Các cơ chế chống replay và chi phí của chúng

| Cơ chế | Trạng thái cần lưu | Khả năng chống replay | Chi phí/giới hạn |
| --- | --- | --- | --- |
| Access token ngắn hạn | Không nhất thiết | Giảm thời gian có thể replay | Replay vẫn xảy ra trong thời hạn |
| Denylist theo jti | Có, cho token bị thu hồi | Từ chối token đã bị đánh dấu | Cần tra cứu và đồng bộ trạng thái |
| One-time token/nonce | Có, trạng thái đã dùng hoặc đang chờ | Có thể chấp nhận đúng một lần | Cần thao tác ghi nguyên tử |
| Replay cache cho proof | Có, định danh proof đã thấy | Từ chối proof trùng trong cửa sổ | Tốn bộ nhớ, độ trễ và tính nhất quán |
| DPoP | Có thể cần replay cache/nonce phía server | Ràng buộc token với khóa và phát hiện proof replay | Client phải quản lý khóa; server cần validation bổ sung |
| mTLS certificate-bound token | Trạng thái binding/cấu hình chứng thư | Token bị đánh cắp riêng lẻ khó sử dụng | Không ngăn mọi request lặp từ bên giữ khóa hợp lệ |
| Refresh token rotation | Có, trạng thái token/family | Phát hiện refresh token cũ bị dùng lại | Cần lưu trạng thái và xử lý request đồng thời |
| Idempotency key | Có, kết quả thao tác | Ngăn tác động nghiệp vụ bị lặp | Cần lưu kết quả và xử lý transaction |

Không nên bật tất cả cơ chế cho mọi endpoint. Chọn theo giá trị cần bảo vệ và hậu quả của replay.

## 5. Access token ngắn hạn: giảm cửa sổ, không bảo đảm one-time-use

Giảm thời hạn access token là cách đơn giản để giới hạn khoảng thời gian token bị đánh cắp còn có giá trị. Nếu token chỉ sống vài phút, kẻ tấn công có ít thời gian hơn để sử dụng token.

Ưu điểm:

- Không cần replay cache cho từng request.
- Không phát sinh một lần ghi trạng thái cho mỗi lần sử dụng.
- Dễ mở rộng khi nhiều resource server xác minh độc lập.
- Giới hạn thời gian ảnh hưởng khi token bị lộ.

Giới hạn:

- Cùng một token vẫn có thể được dùng nhiều lần trước khi hết hạn.
- Token có thể bị phát lại ngay sau khi phát hành.
- Token bị đánh cắp vẫn có giá trị trong cửa sổ hiệu lực.
- Giảm TTL quá mức có thể tăng số lần refresh, tải authorization server và rủi ro lỗi khi refresh.

Ví dụ, access token có thời hạn 5 phút không đồng nghĩa request thanh toán chỉ được thực hiện một lần. Nó chỉ có nghĩa token không còn được chấp nhận sau thời hạn đó. Nếu nghiệp vụ cần chống thanh toán trùng, cần thêm kiểm soát ở cấp thao tác.

## 6. Replay cache và định danh proof

### 6.1. Nguyên tắc hoạt động

Replay cache lưu định danh của token/proof đã được chấp nhận trong một cửa sổ thời gian. Khi nhận một proof mới:

1. Xác minh cấu trúc, chữ ký và các ràng buộc của proof.
2. Xác định định danh duy nhất, chẳng hạn issuer + key thumbprint + jti.
3. Thực hiện thao tác insert-if-absent một cách nguyên tử.
4. Nếu định danh chưa tồn tại, lưu nó đến hết cửa sổ replay và tiếp tục xử lý.
5. Nếu định danh đã tồn tại, từ chối proof vì có dấu hiệu replay.

Thao tác kiểm tra rồi ghi phải nguyên tử. Nếu hai request đồng thời cùng đọc thấy định danh chưa tồn tại trước khi một request ghi vào cache, cả hai có thể được chấp nhận. Một thao tác compare-and-set, unique constraint hoặc primitive atomic add giúp bảo đảm chỉ một request thắng.

### 6.2. Chọn khóa định danh trong cache

Không nên dùng riêng jti nếu nhiều issuer hoặc nhiều loại proof có thể sinh cùng giá trị. Khóa cache nên được tạo từ các thành phần định danh theo profile, ví dụ:

~~~text
replay-key = issuer || proof-key-thumbprint || jti
~~~

Với DPoP, server cần áp dụng đúng quy tắc của RFC 9449 về proof JWT, bao gồm định danh proof và public key thumbprint. Với giao thức khác, chọn namespace và định danh theo profile tương ứng.

Có thể lưu hash của replay key thay vì dữ liệu định danh thô nếu điều đó giúp giảm lộ thông tin trong kho cache/log. Hash không thay thế yêu cầu namespace, tính duy nhất và thời hạn lưu.

### 6.3. TTL của replay cache

Entry cần tồn tại đủ lâu để bao phủ cửa sổ mà proof có thể được chấp nhận. Thời gian này phụ thuộc:

- Thời gian hợp lệ của proof.
- Clock skew cho phép.
- Cách server kiểm tra iat/nonce.
- Độ trễ truyền request và retry hợp lệ.
- Thời điểm token/proof không còn được chấp nhận.

Nếu xóa entry quá sớm, cùng proof có thể được phát lại sau khi entry hết TTL nhưng vẫn còn hợp lệ theo kiểm tra thời gian. Nếu giữ entry quá lâu, bộ nhớ tăng và dữ liệu trạng thái tồn tại lâu hơn cần thiết.

Khi proof đã được ghi nhận là đã dùng, nó vẫn phải được xem là đã tiêu thụ nếu xử lý nghiệp vụ phía sau gặp lỗi. Client muốn retry cần tạo proof mới với định danh mới. Nếu thao tác nghiệp vụ phải giữ cùng một ý định qua nhiều lần retry, hãy dùng idempotency key riêng cho thao tác đó. Nhờ vậy, proof mới chứng minh request mới, còn idempotency key giữ cho side effect không bị lặp.

## 7. DPoP và nonce: ràng buộc request với khóa của client

Demonstrating Proof of Possession (DPoP) theo RFC 9449 bổ sung một proof JWT do client ký bằng khóa riêng. Resource server kiểm tra proof và mối liên hệ giữa proof với access token, method và URI của request.

Proof thường chứa các thông tin như:

- **jti:** định danh duy nhất của proof.
- **htm:** HTTP method.
- **htu:** HTTP target URI theo quy tắc DPoP.
- **iat:** thời điểm tạo proof.
- **ath:** hash của access token khi proof được gửi cùng access token.
- **nonce:** nonce do server cấp, nếu server yêu cầu.

Server kiểm tra chữ ký proof bằng public key được nhúng/được tham chiếu trong header theo profile, kiểm tra method/URI, thời gian, token binding và các điều kiện nonce. Để phát hiện cùng proof được phát lại, server có thể lưu jti trong replay cache trong cửa sổ phù hợp.

Với DPoP-bound access token, resource server còn đối chiếu thumbprint của khóa trong proof với thông tin confirmation của token (thường là claim cnf.jkt theo RFC 9449). Việc kiểm tra chữ ký proof mà không kiểm tra binding này sẽ không chứng minh proof được tạo bằng khóa đã ràng buộc với access token.

### 7.1. DPoP không phải một cờ bật chống replay tự động

Chỉ kiểm tra chữ ký DPoP proof là chưa đủ. Nếu server không kiểm tra thời gian, method, URI, access-token hash và nonce khi được yêu cầu, proof có thể bị dùng sai ngữ cảnh. Nếu không có cơ chế phát hiện proof jti đã được dùng, proof hợp lệ có thể được gửi lại trong cửa sổ được chấp nhận.

Server nonce có thể tăng khả năng chống replay bằng cách yêu cầu proof gắn với một giá trị mới do server cấp. Nonce cần được quản lý theo giao thức, có thời hạn và được kiểm tra đúng client/session hoặc ngữ cảnh yêu cầu. Nonce không phải bí mật lâu dài và không thay thế các kiểm tra còn lại.

### 7.2. DPoP và replay cache phân bổ trạng thái ở đâu?

DPoP ràng buộc token với khóa của client, nên việc chỉ đánh cắp access token thường không đủ để sử dụng token. Tuy nhiên, nếu attacker lấy được cả private key hoặc một proof hợp lệ, họ vẫn có thể tìm cách phát lại proof trong cửa sổ cho phép.

Replay cache giúp phát hiện proof đã thấy, còn nonce giúp server yêu cầu proof mới. Cả hai có thể cần trạng thái và cơ chế phân phối giữa các instance. Cần cân nhắc độ trễ, tính nhất quán và hành vi khi kho nonce/replay cache lỗi.

## 8. mTLS certificate-bound access token

Với access token ràng buộc chứng thư theo RFC 8705, authorization server liên kết token với chứng thư client. Resource server kiểm tra client đang sử dụng kết nối TLS có chứng thư phù hợp với thông tin binding trong token.

Điều này làm giảm khả năng sử dụng token bị đánh cắp riêng lẻ từ một thiết bị hoặc client khác không sở hữu private key của chứng thư.

Tuy nhiên, mTLS binding không tự bảo đảm một request đã xác thực chỉ được thực hiện một lần. Client hợp lệ có chứng thư và token vẫn có thể gửi cùng một thao tác nhiều lần. Nếu cần one-time-use hoặc chống thanh toán trùng, vẫn cần nonce, replay state hoặc idempotency ở lớp phù hợp.

## 9. Refresh token rotation và phát hiện reuse

Refresh token thường có vòng đời dài hơn access token và có giá trị cao vì nó có thể tạo access token mới. OAuth 2.0 Security Best Current Practice (RFC 9700) mô tả các biện pháp bảo vệ refresh token cho public client, gồm sender-constrained refresh token hoặc refresh token rotation với phát hiện reuse.

Với rotation:

1. Client gửi refresh token hiện tại.
2. Authorization server xác minh token và trạng thái phiên/family.
3. Server vô hiệu hóa refresh token cũ và phát hành refresh token mới.
4. Nếu refresh token cũ đã bị vô hiệu hóa lại xuất hiện, có thể là dấu hiệu token bị sao chép và sử dụng đồng thời.
5. Server có thể thu hồi toàn bộ token family hoặc phiên liên quan theo chính sách.

### 9.1. Tradeoff của rotation

Rotation giúp phát hiện việc một refresh token đã dùng bị phát lại, nhưng cần trạng thái phía server để biết token nào đang hoạt động và quan hệ giữa các token trong family.

Một vấn đề vận hành là request đồng thời: client có thể gửi hai yêu cầu refresh gần như cùng lúc do retry, nhiều tab hoặc nhiều tiến trình. Một yêu cầu thành công và làm token cũ mất hiệu lực; yêu cầu còn lại dùng token cũ có thể bị xem là reuse. Client cần đồng bộ refresh để tránh gửi nhiều lần ngoài dự kiến.

Chính sách xử lý reuse phải cân bằng an toàn và trải nghiệm:

- Thu hồi cả family giúp containment mạnh khi phát hiện token bị sao chép.
- Một khoảng grace period có thể giảm false positive do request đồng thời nhưng kéo dài thời gian token cũ còn được chấp nhận.
- Cho phép token cũ dùng lại vô hạn làm mất mục tiêu phát hiện replay.

Không tự thêm grace period nếu profile hoặc chính sách bảo mật không cho phép. Nếu có, phải giới hạn rõ thời gian, số lần, điều kiện và khả năng quan sát.

## 10. Chống phát lại ở cấp nghiệp vụ: idempotency

Chống replay token và chống thực hiện nghiệp vụ trùng là hai vấn đề riêng. Một access token hợp lệ có thể được sử dụng cho nhiều request khác nhau; điều đó thường là hành vi bình thường. Nhưng một request tạo thanh toán bị gửi lại do timeout có thể tạo tác động trùng nếu API không xử lý idempotency.

API có thể nhận một idempotency key do client tạo cho một thao tác:

~~~http
POST /payments
Authorization: Bearer <access-token>
Idempotency-Key: 6c7f2f7b-7b72-4a10-9c9f-1f6f1b1f2a20
Content-Type: application/json
~~~

Server lưu khóa cùng principal/client, endpoint, hash nội dung yêu cầu và kết quả xử lý:

- Lần đầu: tạo bản ghi đang xử lý một cách nguyên tử, thực hiện thao tác và lưu kết quả.
- Cùng key, cùng nội dung: trả lại kết quả trước đó hoặc trạng thái đang xử lý.
- Cùng key, nội dung khác: từ chối vì key bị tái sử dụng không đúng.
- Key mới: xử lý như một thao tác mới.

### 10.1. Idempotency key không phải bằng chứng xác thực

Idempotency key thường do client tạo và có thể bị đoán, sao chép hoặc phát lại. Nó chỉ hỗ trợ nhận diện một thao tác logic trong phạm vi được định nghĩa. Server vẫn phải xác thực token, kiểm tra quyền và ràng buộc key với principal/client, endpoint và dữ liệu yêu cầu.

Không dùng một idempotency key toàn cục không có namespace. Hai người dùng khác nhau có thể vô tình hoặc cố ý dùng cùng chuỗi key; phạm vi nên bao gồm danh tính và loại thao tác.

### 10.2. Idempotency và transaction

Để tránh hai request đồng thời cùng thực hiện side effect, việc đăng ký idempotency key và chuyển trạng thái nghiệp vụ cần được đồng bộ nguyên tử hoặc có cơ chế khóa/unique constraint phù hợp. Nếu side effect nằm ở hệ thống bên ngoài, cần thiết kế retry, outbox/inbox hoặc đối soát để không tạo tác động lặp khi kết quả bên ngoài không rõ ràng.

Idempotency không có nghĩa mọi HTTP request đều chỉ được gửi một lần. Nó có nghĩa nhiều lần gửi cùng một yêu cầu logic tạo ra hiệu ứng được kiểm soát theo hợp đồng API.

Idempotency key chỉ bảo vệ trong phạm vi và thời gian server lưu trạng thái. Nếu xóa bản ghi quá sớm, một retry muộn có thể được xem là thao tác mới. Cần chọn retention period dựa trên thời gian retry/đối soát và quy định khi key hết hạn. Với side effect ở hệ thống ngoài, idempotency key một mình không tạo ra bảo đảm exactly-once xuyên nhiều hệ thống; cần transaction/outbox/inbox, deduplication ở bên nhận hoặc quy trình đối soát phù hợp.

## 11. Trạng thái phân tán: nhất quán hay sẵn sàng?

Replay prevention thường cần nhiều instance cùng biết một proof/token đã được sử dụng. Nếu mỗi instance giữ replay cache riêng trong bộ nhớ:

- Request đầu tiên đến instance A được ghi nhận.
- Request phát lại đến instance B không nhìn thấy entry của A.
- Cả hai instance có thể chấp nhận cùng proof.

Dùng một kho trạng thái dùng chung giúp chia sẻ kết quả nhưng tạo thêm phụ thuộc mạng và một điểm cần quản lý tính sẵn sàng.

### 11.1. Strong consistency và eventual consistency

| Cách lưu trạng thái | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Bộ nhớ cục bộ từng instance | Độ trễ thấp, không phụ thuộc mạng | Không phát hiện replay đi qua instance khác |
| Kho dùng chung có thao tác nguyên tử/nhất quán mạnh | Các instance có thể cùng phát hiện lần dùng đầu | Độ trễ, chi phí và phụ thuộc kho trạng thái |
| Replication eventual consistency | Có thể tăng khả năng phục vụ và mở rộng vùng | Hai vùng có thể cùng chấp nhận replay trước khi đồng bộ |
| Sharding theo định danh | Phân tải và giữ cùng key trên một shard | Cần routing ổn định và xử lý shard lỗi |

Với thao tác rủi ro cao, eventual consistency có thể để lại cửa sổ mà cùng proof được chấp nhận ở hai vùng. Nếu yêu cầu bảo đảm one-time-use toàn cục, cần cơ chế cấp quyền ghi nguyên tử hoặc điều phối nhất quán phù hợp.

### 11.2. Partition và lỗi mạng

Khi resource server không liên lạc được với replay store, nó phải quyết định:

- Từ chối request cho đến khi kiểm tra replay hoạt động trở lại.
- Cho phép request đi tiếp mà không có kiểm tra replay.
- Chuyển sang vùng/dịch vụ dự phòng có cùng đảm bảo nhất quán.

Không có lựa chọn nào miễn phí. Từ chối làm giảm availability; bỏ qua kiểm tra làm giảm khả năng chống replay. Lựa chọn phải dựa trên hậu quả nghiệp vụ và yêu cầu bảo mật, không chỉ dựa vào việc giảm lỗi hệ thống.

## 12. Fail-closed hay fail-open?

**Fail-closed** nghĩa là khi không thể xác minh trạng thái replay, hệ thống từ chối hoặc tạm dừng thao tác. **Fail-open** nghĩa là hệ thống tiếp tục xử lý dù kiểm tra replay không thực hiện được.

| Loại thao tác | Hướng xử lý thường phù hợp | Lý do |
| --- | --- | --- |
| Thanh toán, chuyển tiền, cấp quyền quản trị | Fail-closed hoặc chuyển sang quy trình dự phòng có kiểm soát | Replay có thể gây thiệt hại trực tiếp |
| Redeem one-time code, reset credential | Fail-closed | Dùng lại có thể chiếm tài khoản hoặc vượt bước xác minh |
| API đọc dữ liệu ít nhạy cảm với bearer token ngắn hạn | Có thể chấp nhận rủi ro có giới hạn theo threat model | Replay không tạo side effect và token có cửa sổ ngắn |
| Telemetry hoặc sự kiện có thể loại trùng ở downstream | Có thể tiếp tục với deduplication bù trừ | Có thể phục hồi/đối soát sau |
| Refresh token rotation | Fail-closed khi không thể xác định trạng thái family | Chấp nhận token cũ có thể bỏ lỡ reuse |

Đây là gợi ý theo mức rủi ro, không phải quy tắc tuyệt đối. Ví dụ API đọc dữ liệu nhạy cảm vẫn có thể cần fail-closed nếu token replay gây rò rỉ dữ liệu nghiêm trọng.

### 12.1. Phân biệt lỗi hạ tầng với replay đã xác nhận

Không nên biến mọi lỗi cache thành kết luận token đã bị replay. Hệ thống cần phân biệt:

- **Replay detected:** định danh đã tồn tại; từ chối theo chính sách.
- **Replay store unavailable:** không thể xác minh; áp dụng fail-open/closed đã định.
- **Invalid proof:** chữ ký, nonce, thời gian hoặc binding sai.
- **Duplicate business request:** idempotency key đã tồn tại và xử lý theo hợp đồng.

Log và metric riêng giúp vận hành nhận diện lỗi bảo mật thực sự và lỗi phụ thuộc hạ tầng.

## 13. Ước lượng chi phí trạng thái

Số entry sống trong replay cache phụ thuộc lưu lượng và cửa sổ chống replay. Ước lượng đơn giản:

~~~text
Số entry đồng thời ≈ số proof/request mỗi giây × thời gian lưu (giây)
~~~

Ví dụ, nếu hệ thống nhận 1.000 proof mỗi giây và giữ mỗi định danh trong 120 giây, cache có thể cần chứa khoảng 120.000 entry hoạt động, chưa tính metadata, replication, index và overhead của kho dữ liệu.

Chi phí thực tế còn phụ thuộc:

- Kích thước key/value và cấu trúc index.
- Số bản sao/replica.
- Tỷ lệ request retry và proof hết hạn.
- Cách phân vùng và phân phối tải.
- Thời gian giữ dữ liệu sau khi token/proof hết hiệu lực.

Các cách giảm chi phí:

- Giữ entry đúng bằng cửa sổ cần thiết, cộng clock skew có kiểm soát.
- Chỉ áp dụng replay cache cho endpoint/proof có yêu cầu.
- Dùng định danh ngắn hoặc hash có namespace.
- Shard theo định danh ổn định.
- Dùng TTL tự động và theo dõi memory pressure.
- Đặt giới hạn kích thước và tốc độ tạo proof để chống cache exhaustion.

Bloom filter có thể giúp lọc nhanh một số trường hợp, nhưng có false positive và không phù hợp làm nguồn quyết định cuối cùng cho thao tác giá trị cao nếu không có bước xác minh chính xác. Không dùng cấu trúc xác suất như thể nó bảo đảm one-time-use tuyệt đối.

## 14. Clock skew, thời gian và cửa sổ replay

Proof có timestamp thường được chấp nhận trong một cửa sổ thời gian. Nếu đồng hồ các node lệch nhau, một proof có thể được một node coi là còn hạn nhưng node khác coi là quá hạn.

Cần:

- Đồng bộ đồng hồ của issuer, client và verifier theo nguồn thời gian đáng tin cậy.
- Định nghĩa clock skew tối đa và kiểm tra timestamp theo cùng quy tắc.
- Giữ replay entry đủ lâu để không có node nào còn chấp nhận proof sau khi entry đã bị xóa.
- Không mở rộng cửa sổ chỉ để che lỗi đồng hồ kéo dài.
- Theo dõi độ lệch thời gian và cảnh báo khi vượt ngưỡng.

Nếu client tạo timestamp xa trong tương lai hoặc quá khứ, server phải từ chối theo profile. Không dùng timestamp do client tự khai báo như một cơ chế thay thế nonce hoặc trạng thái đã sử dụng.

## 15. Chọn cơ chế theo threat model và giá trị nghiệp vụ

Một ma trận lựa chọn đơn giản:

| Nhu cầu | Cơ chế phù hợp | Trạng thái cần thiết |
| --- | --- | --- |
| Giảm thiệt hại khi bearer access token bị lộ | Access token ngắn hạn, scope hẹp, bảo vệ nơi lưu trữ | Thường không cần per-request replay state |
| Token chỉ dùng cho một hành động | One-time token + atomic consumed marker | Có |
| Proof-of-possession bị phát lại | DPoP proof validation + replay cache/nonce theo profile | Thường có |
| Token bị dùng từ thiết bị/client khác | DPoP hoặc mTLS certificate-bound token | Khóa/chứng thư binding; replay proof nếu cần |
| Refresh token bị sao chép và dùng lại | Rotation + reuse detection hoặc sender constraint | Có |
| Thanh toán/tạo đơn bị gửi lại | Idempotency key + transaction/deduplication | Có |
| Logout hoặc thu hồi một phiên | Session/refresh-token revocation hoặc introspection | Có |

Khi lựa chọn, hãy trả lời:

1. Tài sản nào bị ảnh hưởng nếu request bị phát lại?
2. Attacker có thể lấy token, private key, proof hay chỉ request đã ghi lại?
3. Replay có thể xảy ra trong bao lâu?
4. Cần bảo đảm một lần trên một instance, một region hay toàn hệ thống?
5. Nếu replay store không khả dụng, thiệt hại của fail-open và fail-closed là gì?
6. Có thể bù trừ/đối soát nghiệp vụ nếu side effect bị lặp không?
7. Độ trễ và chi phí trạng thái có phù hợp lưu lượng không?

## 16. Kiểm thử chống phát lại và tính sẵn sàng

Không chỉ kiểm tra request lặp liên tiếp trong một tiến trình. Cần kiểm tra concurrency, nhiều instance, nhiều vùng và lỗi hạ tầng.

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Gửi lại cùng one-time token lần thứ hai | Bị từ chối |
| Hai request đồng thời dùng cùng jti | Chỉ một request được đánh dấu lần đầu |
| Cùng proof đến hai instance khác nhau | Instance thứ hai phát hiện replay |
| Cùng proof đến hai region có replication trễ | Hệ thống thể hiện đúng giới hạn nhất quán đã chọn; thao tác rủi ro cao không được âm thầm chấp nhận hai lần |
| Replay store không khả dụng | Hành vi fail-open/closed đúng policy |
| Proof hết hạn nhưng cache entry còn | Từ chối theo thời gian; entry được dọn theo TTL |
| Cache entry hết hạn trước khi proof hết cửa sổ hợp lệ | Kiểm thử phải phát hiện cấu hình sai vì proof có thể replay |
| DPoP proof dùng sai method/URI/ath | Từ chối |
| DPoP proof jti đã được dùng | Từ chối trong cửa sổ replay |
| Nonce không khớp hoặc đã hết hạn | Từ chối theo profile |
| Refresh token cũ được dùng lại sau rotation | Phát hiện reuse và xử lý family theo policy |
| Hai refresh request đồng thời từ cùng client | Xử lý theo chính sách concurrency; không vô tình cấp nhiều nhánh token |
| Idempotency key trùng với payload khác | Từ chối xung đột |
| Cùng idempotency key và cùng payload được retry | Trả kết quả trước đó, không lặp side effect |
| Đồng hồ giữa các node lệch | Từ chối timestamp ngoài cửa sổ và phát cảnh báo |
| Cache bị đầy hoặc bị flood bằng jti ngẫu nhiên | Có quota/rate limit; không làm sập toàn bộ xác minh |

Nên đo ít nhất:

- Tỷ lệ replay bị phát hiện.
- Tỷ lệ lỗi replay store và thời gian không khả dụng.
- Độ trễ p95/p99 khi kiểm tra replay.
- Số entry đang lưu, tốc độ tăng và bộ nhớ.
- Độ trễ đồng bộ giữa region.
- Tỷ lệ false positive do retry/refresh đồng thời.
- Số thao tác nghiệp vụ bị deduplicate hoặc cần đối soát.

## 17. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| JWT có chữ ký thì không thể replay | Chữ ký bảo vệ nội dung, không ngăn gửi lại token |
| Có jti là token chỉ dùng một lần | jti chỉ là định danh; cần lưu/kiểm tra trạng thái |
| exp ngắn nghĩa là chống replay | Chỉ thu hẹp cửa sổ replay |
| DPoP tự động giải quyết mọi replay | Cần kiểm tra đầy đủ proof, binding, nonce và replay policy |
| mTLS ngăn mọi request bị gửi lại | mTLS ràng buộc token với chứng thư, không tự ngăn thao tác lặp từ client hợp lệ |
| Idempotency key thay thế access token | Idempotency không xác thực hoặc cấp quyền |
| Cache cục bộ đủ cho hệ thống nhiều instance | Instance khác không thấy trạng thái đã ghi |
| Eventual consistency tương đương one-time-use toàn cục | Replication trễ có thể cho phép hai lần sử dụng |
| Fail-open luôn tăng availability mà không có hậu quả | Có thể chấp nhận replay và tạo side effect không thể đảo ngược |
| Fail-closed luôn là lựa chọn tốt nhất | Có thể làm gián đoạn thao tác; cần xét rủi ro và quy trình dự phòng |

## 18. Tình huống tự kiểm tra

Một API thanh toán nhận access token JWT có thời hạn 10 phút. Token có jti nhưng API chỉ xác minh chữ ký, issuer, audience và exp. Người dùng gửi yêu cầu thanh toán; do timeout, client gửi lại cùng request đến một instance khác. API tạo hai giao dịch.

**Câu hỏi 1:** Vì sao jti không ngăn được giao dịch thứ hai?

**Trả lời:** API không lưu hoặc kiểm tra trạng thái jti đã dùng. Cùng một JWT có thể được xác minh thành công nhiều lần trong thời hạn hiệu lực.

**Câu hỏi 2:** Có nên đánh dấu access token đã dùng sau request đầu tiên để ngăn mọi request tiếp theo không?

**Trả lời:** Không nhất thiết. Access token thường được thiết kế để gọi nhiều API/request trong thời hạn được cấp. Nếu đánh dấu toàn token là dùng một lần, các request hợp lệ tiếp theo cũng bị từ chối. Cần chống replay theo proof hoặc theo thao tác nghiệp vụ.

**Câu hỏi 3:** Cơ chế nào ngăn thanh toán bị tạo hai lần khi client retry?

**Trả lời:** Dùng idempotency key gắn với principal, endpoint và nội dung yêu cầu; lưu trạng thái/kết quả bằng thao tác nguyên tử. Request retry cùng key và payload trả lại kết quả trước đó thay vì tạo giao dịch mới.

**Câu hỏi 4:** Nếu kho idempotency không khả dụng, API có nên tiếp tục tạo thanh toán không?

**Trả lời:** Với thao tác tài chính, thường nên fail-closed hoặc chuyển sang quy trình dự phòng có khả năng bảo đảm tính duy nhất. Tiếp tục mà không kiểm tra có thể tạo giao dịch trùng; quyết định cuối cùng cần được quy định trong policy vận hành.

## 19. Ghi nhớ

JWT có chữ ký không tự chống replay. Thời hạn ngắn chỉ giảm cửa sổ sử dụng; jti chỉ cung cấp định danh; nonce và replay cache cần trạng thái; DPoP/mTLS ràng buộc token với khóa của client; refresh token rotation phát hiện reuse; idempotency bảo vệ side effect nghiệp vụ.

Khi cần bảo đảm một lần sử dụng, phải xác định phạm vi nhất quán: một tiến trình, nhiều instance hay toàn hệ thống. Thao tác kiểm tra và ghi trạng thái phải nguyên tử; cache và replication phải đáp ứng cửa sổ replay. Khi kho trạng thái lỗi, fail-open hay fail-closed cần dựa trên hậu quả của hành động.

**Chống replay là một quyết định kiến trúc giữa mức bảo vệ, trạng thái phải duy trì, độ trễ và tính sẵn sàng. Hãy áp dụng trạng thái ở đúng lớp cần bảo vệ, thay vì mặc định mọi JWT đều phải dùng một lần.**

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): claims, NumericDate và JWT ID (jti).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): đặc tính bearer token và rủi ro khi token bị lộ.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): ràng buộc access token với chứng thư client.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): proof-of-possession, proof JWT, nonce và chống replay.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): sender-constrained token và refresh token rotation/reuse detection.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ngữ nghĩa method và tính idempotent của HTTP.
