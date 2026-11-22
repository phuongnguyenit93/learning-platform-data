# Những điều JWT không tự bảo đảm: bí mật, thu hồi và chống phát lại

JSON Web Token (JWT) là định dạng biểu diễn các claims giữa những bên trao đổi dữ liệu. Việc một hệ thống sử dụng JWT **không tự động bảo đảm** nội dung được giữ bí mật, token có thể bị thu hồi tức thời, hoặc một thông điệp hợp lệ không thể bị gửi lại. Những thuộc tính này cần được thiết kế và kiểm soát bằng các cơ chế phù hợp với mô hình đe dọa.

Bài học thuộc chương **Nền tảng tin cậy** của module **Security – JSON Web Token (JWT)**. Nội dung tập trung vào ba giới hạn quan trọng: **confidentiality (bí mật)**, **revocation (thu hồi)** và **replay resistance (chống phát lại)**; áp dụng cho browser, ứng dụng di động, backend và API ở mọi nền tảng, không phụ thuộc ngôn ngữ lập trình hay framework.

## 1. JWT là định dạng, không phải lời cam kết bảo mật toàn diện

JWT định nghĩa cách biểu diễn một tập claims. Bản thân tên JWT không nói rằng token đã được ký, mã hóa, gắn với người gửi hay có cơ chế thu hồi. Cách bảo vệ phụ thuộc vào cấu trúc JOSE được sử dụng:

| Dạng | Cơ chế | Thuộc tính có thể cung cấp | Điều không tự bảo đảm |
| --- | --- | --- | --- |
| JWS có chữ ký số | Chữ ký bằng khóa riêng, xác minh bằng khóa công khai | Toàn vẹn và xác thực nguồn ký khi khóa được gắn với issuer đáng tin | Bí mật payload, thu hồi tức thời, chống replay |
| JWS dùng MAC | MAC/HMAC bằng khóa bí mật chung | Toàn vẹn và xác thực trong nhóm biết khóa | Bí mật payload, phân biệt bên nào trong nhóm tạo MAC, thu hồi, chống replay |
| JWE với AEAD phù hợp | Mã hóa nội dung và xác thực mật mã | Bí mật cùng toàn vẹn của ciphertext và dữ liệu liên kết được bảo vệ | Danh tính issuer trong mọi mô hình, thu hồi và chống replay |
| JWT không được bảo vệ | Chỉ biểu diễn claims, ví dụ JWS unsecured | Không có bảo vệ mật mã đáng tin cho claims | Toàn vẹn, nguồn gốc, bí mật, thu hồi và chống replay |

Trong phần lớn hệ thống truy cập API, access token phải được bảo vệ bằng cơ chế xác thực mật mã theo profile được chấp nhận. Một token có cấu trúc parse được hoặc payload giải mã Base64url được **không phải** bằng chứng token hợp lệ.

Ba câu hỏi cần tách biệt:

1. **Bí mật:** người không được phép có đọc được claims hay dữ liệu không?
2. **Thu hồi:** khi token hoặc quyền không còn được chấp nhận, resource server biết điều đó bằng cách nào và trong bao lâu?
3. **Chống phát lại:** nếu token hoặc request hợp lệ bị sao chép, hệ thống có ngăn việc sử dụng lại không?

Chữ ký JWS chủ yếu giải quyết toàn vẹn và nguồn ký. Nó không tự trả lời ba câu hỏi trên.

## 2. JWT không tự bảo đảm tính bí mật

### 2.1. Base64url không phải mã hóa bảo mật

Một JWS Compact thường có ba phần:

~~~text
BASE64URL(protected_header).BASE64URL(payload).BASE64URL(signature)
~~~

Header và payload được mã hóa biểu diễn bằng Base64url để có thể truyền dưới dạng chuỗi. Đây không phải mã hóa mật mã để giữ bí mật. Người có token có thể giải mã Base64url và đọc nội dung mà không cần khóa ký.

Ví dụ payload đã giải mã:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user-42",
  "aud": "https://billing-api.example.org",
  "scope": "invoice:read",
  "email": "user@example.org",
  "tenant_id": "company-7",
  "exp": 2000000000
}
~~~

Người cầm JWS có thể đọc email, tenant và các claims khác. Chữ ký chỉ giúp phát hiện thay đổi trái phép trên dữ liệu đã ký; nó không che giấu nội dung.

**Không đưa vào JWS các dữ liệu mà người cầm token không được phép đọc**, chẳng hạn mật khẩu, số thẻ thanh toán, khóa bí mật, dữ liệu sức khỏe hoặc thông tin cá nhân không cần thiết. Hãy áp dụng nguyên tắc claims tối thiểu và tra cứu dữ liệu nhạy cảm qua API có kiểm soát quyền.

### 2.2. Chữ ký không phải mã hóa

| Cơ chế | Người không có khóa có đọc payload không? | Có thể phát hiện sửa đổi? |
| --- | --- | --- |
| JWS có chữ ký số | Có | Có, nếu xác minh đúng chữ ký và khóa |
| JWS có HMAC | Có | Có, nếu kiểm tra đúng MAC |
| JWE | Không đọc được plaintext nếu không có khóa giải mã phù hợp | Có với cấu hình mã hóa có xác thực như AEAD |

Chữ ký số và HMAC cung cấp bằng chứng toàn vẹn/xác thực trong mô hình khóa tương ứng. Muốn bảo vệ bí mật, cần mã hóa. Không nên tự ghép các thuật toán mật mã theo cách riêng; hãy sử dụng chuẩn JOSE và thư viện đáng tin cậy.

### 2.3. JWE cung cấp bí mật, nhưng vẫn có giới hạn

JWE (JSON Web Encryption) mã hóa nội dung JWT cho người nhận được phép giải mã. JWE Compact Serialization thường có năm phần:

~~~text
BASE64URL(protected_header).BASE64URL(encrypted_key).BASE64URL(iv).BASE64URL(ciphertext).BASE64URL(authentication_tag)
~~~

Với thuật toán mã hóa có xác thực như AES-GCM:

- Claims trong ciphertext không hiển thị ở dạng rõ với người không có khóa giải mã.
- Tag cho phép phát hiện ciphertext hoặc dữ liệu liên kết được bảo vệ đã bị thay đổi.
- Protected header vẫn có thể đọc được; không đặt bí mật trong header.
- Kích thước, thời điểm, người gửi/nhận hoặc metadata ngoài payload vẫn có thể tiết lộ thông tin.

**JWE không tự xác thực danh tính issuer trong mọi mô hình.** Ví dụ, bất kỳ ai có khóa công khai của người nhận đều có thể tạo dữ liệu mã hóa gửi cho người nhận. Người nhận giải mã thành công không vì thế mà biết nội dung do một issuer cụ thể phát hành. Nếu cần xác thực độc lập nguồn phát hành, có thể ký nội dung bằng JWS rồi mã hóa JWS thành JWE, sau đó giải mã và xác minh chữ ký bên trong theo đúng thứ tự.

### 2.4. TLS bảo vệ đường truyền, không thay thế bảo vệ token

TLS bảo vệ dữ liệu khi truyền giữa các đầu cuối kết nối và giúp xác thực endpoint theo cấu hình chứng chỉ. TLS không:

- Ngăn XSS đọc token từ JavaScript storage.
- Ngăn mã độc hoặc người có quyền trên thiết bị lấy token.
- Ngăn ứng dụng ghi token vào log hoặc gửi nhầm sang analytics.
- Che payload JWS sau khi token đến tay người nhận.
- Thu hồi token đã bị sao chép.

Một request có thể được truyền an toàn qua HTTPS nhưng token vẫn bị lộ ở browser, proxy, backend log hoặc hệ thống quan sát. Bảo vệ bí mật cần bao gồm cả nơi lưu, nơi xử lý và nơi ghi nhận dữ liệu.

### 2.5. Cách giảm rủi ro lộ claims

1. Chỉ đưa các claims cần thiết cho quyết định truy cập.
2. Không đưa password, private key, shared secret, dữ liệu thanh toán hoặc thông tin nhạy cảm không cần thiết vào token.
3. Dùng JWE khi thật sự cần mã hóa payload tới người nhận cụ thể và có quy trình quản lý khóa giải mã.
4. Nếu dữ liệu nhạy cảm có thể tra cứu qua API, ưu tiên giữ dữ liệu ở resource server và kiểm soát bằng phân quyền.
5. Bảo vệ token khi lưu và truyền; không đặt token trong URL, log, trace, ticket hoặc ảnh chụp.
6. Giới hạn người và workload được phép giải mã JWE; mã hóa không giúp ích nếu mọi thành phần đều có khóa giải mã.

## 3. JWT không tự cung cấp cơ chế thu hồi tức thời

### 3.1. Vì sao JWT có thể còn hợp lệ sau khi người dùng bị khóa?

Một resource server có thể xác minh chữ ký JWT offline bằng khóa công khai mà không cần hỏi authorization server ở mỗi request. Điều này giảm độ trễ và phụ thuộc mạng, nhưng server thường chỉ biết những claims được phát hành trước đó.

Giả sử access token được phát hành lúc 09:00, có thời hạn đến 10:00. Lúc 09:20, quản trị viên khóa tài khoản hoặc thu hồi quyền. Nếu resource server chỉ xác minh chữ ký và claim thời gian, token có thể vẫn được chấp nhận đến 10:00.

~~~mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant C as Client
    participant API as Resource Server
    AS->>C: Cấp JWT exp = 10:00
    C->>API: Request với JWT lúc 09:10
    API->>API: Xác minh offline thành công
    AS->>AS: Thu hồi quyền lúc 09:20
    C->>API: Request với JWT lúc 09:25
    API->>API: Chỉ kiểm tra chữ ký và exp
    API-->>C: Có thể vẫn chấp nhận
    Note over AS,API: Resource Server chưa biết trạng thái thu hồi mới
~~~

Chữ ký hợp lệ chứng minh token không bị sửa sau khi ký; nó không chứng minh quyền và trạng thái tài khoản vẫn còn hiệu lực ở thời điểm hiện tại.

### 3.2. Claim exp giới hạn thời gian, không phải danh sách thu hồi

Các claim thời gian thường gặp:

- **exp (expiration time):** sau thời điểm này token không được chấp nhận.
- **nbf (not before):** trước thời điểm này token chưa được chấp nhận.
- **iat (issued at):** thời điểm phát hành; có thể dùng trong chính sách về tuổi token.

**exp** tạo giới hạn trên cho cửa sổ hiệu lực. Nó không cho biết token đã bị thu hồi trước thời điểm đó hay chưa. Hệ thống có thể cho phép một độ lệch đồng hồ nhỏ theo chính sách, nhưng không nên dùng clock skew quá rộng để che lỗi đồng bộ thời gian.

### 3.3. Claim jti không tự thu hồi token

Claim **jti** (*JWT ID*) có thể định danh duy nhất một token. Nó hữu ích khi xây denylist hoặc đối chiếu sự kiện, nhưng bản thân claim này không làm token mất hiệu lực.

Để chặn token theo jti, resource server phải có trạng thái tra cứu:

1. Đọc jti sau khi token được xác minh.
2. Tra cứu jti trong denylist hoặc trạng thái thu hồi.
3. Nếu jti bị chặn, từ chối token.
4. Lưu bản ghi đủ lâu để bao phủ thời gian token có thể còn được chấp nhận.

Nếu API không tra cứu trạng thái, chỉ thêm jti vào JWT không tạo ra khả năng thu hồi.

### 3.4. Thu hồi refresh token không đồng nghĩa thu hồi access token đã cấp

Refresh token cho phép client xin access token mới. Khi refresh token bị thu hồi, authorization server có thể từ chối việc cấp token mới. Nhưng access token đã phát hành trước đó có thể vẫn hợp lệ với resource server xác minh offline.

Do đó cần phân biệt:

| Hành động | Tác động thường thấy | Điều còn phải xử lý |
| --- | --- | --- |
| Thu hồi refresh token | Ngăn dùng refresh token đó để xin access token mới | Access token hiện có có thể vẫn được chấp nhận |
| Đăng xuất phiên tại authorization server | Chấm dứt hoặc vô hiệu phiên/refresh token theo chính sách | Resource server cần biết trạng thái nếu muốn chặn access token ngay |
| Thu hồi access token qua revocation endpoint | Authorization server ghi nhận token bị thu hồi theo giao thức | Resource server phải introspect hoặc nhận trạng thái thu hồi bằng cách khác |
| Thêm jti vào denylist | Chặn token có ID tương ứng tại nơi tra cứu denylist | Mọi resource server liên quan phải kiểm tra danh sách kịp thời |
| Xoay khóa ký | Có thể ngừng xác minh token ký bằng khóa cũ | Tác động rộng tới token cùng khóa; cần phân biệt rotation bình thường và key compromise |

## 4. Các cách quản lý thu hồi và trạng thái token

Không có một cách duy nhất phù hợp với mọi hệ thống. Lựa chọn phụ thuộc vào thời gian thu hồi tối đa chấp nhận được, số lượng API, yêu cầu sẵn sàng và khả năng vận hành trạng thái.

### 4.1. Access token có thời hạn ngắn

Access token TTL ngắn giới hạn thời gian kẻ tấn công có thể sử dụng token sau khi bị lộ hoặc sau khi quyền thay đổi.

**Ưu điểm:**

- Resource server có thể xác minh offline.
- Không cần tra cứu trạng thái trên mỗi request.
- Cửa sổ hiệu lực của token bị lộ được giới hạn.

**Giới hạn:**

- Không thu hồi tức thời; token vẫn có thể được chấp nhận đến khi hết hạn.
- TTL quá ngắn làm tăng tần suất refresh, tải hệ thống và nguy cơ lỗi trải nghiệm.
- Refresh token vẫn cần được bảo vệ và thu hồi.

TTL nên được chọn theo độ nhạy tài nguyên, mức quyền, rủi ro thiết bị và SLA thu hồi. Một token chỉ đọc dữ liệu công khai có thể có yêu cầu khác token thực hiện thanh toán hoặc quản trị.

### 4.2. Token introspection

OAuth Token Introspection cho phép resource server hỏi authorization server về trạng thái và metadata của token. Authorization server có thể trả về thông tin như token còn active hay không, subject, client, scope và thời hạn theo profile.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as Resource Server
    participant AS as Authorization Server
    C->>API: Request kèm access token
    API->>AS: Introspection request
    AS-->>API: active = true/false và metadata
    alt Token active và quyền phù hợp
        API-->>C: Xử lý request
    else Token inactive hoặc không đủ quyền
        API-->>C: Từ chối
    end
~~~

**Ưu điểm:** trạng thái tập trung; token bị thu hồi có thể được phản ánh ở lần introspection kế tiếp; có thể dùng với opaque token và một số profile JWT.

**Giới hạn:** tăng độ trễ, phụ thuộc tính sẵn sàng của authorization server, cần xác thực resource server khi gọi introspection và phải thiết kế cache. Nếu cache kết quả active quá lâu, thời gian thu hồi thực tế bị kéo dài tương ứng.

### 4.3. Denylist theo jti hoặc fingerprint

Resource server hoặc một dịch vụ trạng thái có thể lưu các token đã bị thu hồi. Khóa tra cứu có thể là cặp issuer/jti hoặc fingerprint an toàn của token.

Nguyên tắc:

- Chỉ ghi nhận jti sau khi xác minh token và issuer.
- Namespace theo issuer để tránh trùng jti giữa các nguồn phát hành.
- Đặt TTL bản ghi ít nhất đến thời điểm token không còn được chấp nhận, có tính tới clock skew.
- Đảm bảo tất cả resource server liên quan đều tra cứu trạng thái.
- Xử lý cache và đồng bộ để không tiếp tục chấp nhận token đã bị chặn.

Denylist làm tăng trạng thái và chi phí tra cứu. Nếu cần thu hồi mọi token của một phiên hoặc một subject, có thể cần session identifier, token version, trạng thái tài khoản hoặc cơ chế quản lý phiên riêng thay vì chỉ chặn từng jti.

### 4.4. Kiểm tra trạng thái tài khoản hoặc phiên

Với thao tác nhạy cảm, resource server có thể kiểm tra trạng thái tài khoản, phiên, tenant hoặc quyền hiện tại từ một nguồn dữ liệu đáng tin. Ví dụ:

- Tài khoản đã bị khóa?
- Phiên đăng nhập có bị thu hồi?
- Quyền quản trị có còn hiệu lực?
- Tenant có bị đình chỉ?
- Phiên bản quyền hiện tại có khớp claim version trong token?

Cách này phản ánh trạng thái nghiệp vụ mới nhất nhưng có thể tăng phụ thuộc dữ liệu trung tâm. Có thể cache theo SLA, nhưng cache lâu sẽ làm tăng độ trễ thu hồi.

### 4.5. Luân chuyển khóa ký

Xoay khóa ký theo lịch là thực hành quản lý khóa bình thường. Khi private key bị xâm phạm, ngừng tin khóa đó có thể chặn toàn bộ token được ký bằng khóa cũ sau khi các resource server cập nhật cấu hình.

Tuy nhiên, rotation khóa có tác động rộng:

- Các token hợp lệ còn hạn được ký bằng khóa cũ cũng có thể bị từ chối.
- JWKS cache và thời gian cập nhật giữa các API cần được tính tới.
- Nếu khóa bị lộ, kẻ tấn công có thể đã tạo token giả; cần đánh giá phạm vi token và sự kiện đã xảy ra.
- Không nên xóa khóa cũ quá sớm trong rotation bình thường; nhưng khi compromise, ưu tiên ngừng tin khóa theo kế hoạch khẩn cấp.

### 4.6. So sánh lựa chọn thu hồi

| Cơ chế | Tốc độ thu hồi | Trạng thái cần lưu | Chi phí vận hành | Phù hợp khi |
| --- | --- | --- | --- | --- |
| TTL ngắn | Sau khi token hết hạn | Không cần trạng thái từng token | Thấp đến vừa | Có thể chấp nhận cửa sổ hiệu lực ngắn |
| Introspection | Gần thời gian thực tùy cache | Trạng thái tại authorization server | Vừa đến cao | Cần trạng thái tập trung và thu hồi nhanh |
| Denylist jti | Nhanh tùy đồng bộ/cache | Danh sách token bị chặn | Vừa | Cần thu hồi một số token cụ thể |
| Kiểm tra phiên/tài khoản | Theo độ trễ truy vấn/cache | Trạng thái phiên hoặc tài khoản | Vừa đến cao | Quyền và trạng thái thay đổi thường xuyên |
| Xoay khóa ký | Có thể chặn hàng loạt sau khi cập nhật | Quản lý khóa và JWKS | Cao khi sự cố | Khóa ký bị lộ hoặc cần thay khóa khẩn cấp |

Hãy xác định một mục tiêu cụ thể, ví dụ “token bị thu hồi phải bị từ chối trong tối đa 60 giây”. Từ mục tiêu đó mới chọn cache TTL, cơ chế đồng bộ và cách kiểm thử. Không tuyên bố “thu hồi tức thời” nếu hệ thống có cache hoặc resource server vẫn xác minh offline.

## 5. JWT không tự chống phát lại

### 5.1. Replay attack là gì?

Replay attack xảy ra khi kẻ tấn công ghi lại một thông điệp hoặc bằng chứng xác thực hợp lệ rồi gửi lại sau đó. Nội dung có thể không bị sửa; chữ ký vẫn hợp lệ.

Có ít nhất ba dạng cần phân biệt:

1. **Token replay:** sao chép bearer token rồi dùng token ở request khác.
2. **Request replay:** ghi lại toàn bộ HTTP request hợp lệ, gồm method, URL, body và credential, rồi gửi lại.
3. **Proof replay:** sao chép bằng chứng ký hoặc nonce/proof của giao thức rồi gửi lại trong ngữ cảnh mà server vẫn chấp nhận.

Ví dụ, một request tạo lệnh thanh toán được xác thực hợp lệ. Kẻ tấn công ghi lại request và gửi lần nữa. Nếu API không có cơ chế chống trùng lặp hoặc xác nhận nghiệp vụ, cùng một hành động có thể xảy ra hai lần.

### 5.2. Vì sao chữ ký JWT không ngăn replay?

Chữ ký JWS bảo vệ nội dung token khỏi sửa đổi. Khi token được sao chép nguyên vẹn:

- Header không đổi.
- Payload không đổi.
- Chữ ký vẫn khớp.
- Claims thời gian vẫn hợp lệ nếu chưa hết hạn.

Vì vậy, resource server có thể chấp nhận nhiều request dùng cùng bearer token. JWT không tự ghi nhớ token đã được dùng, không tự ràng buộc token với một thiết bị, và không tự đảm bảo request chỉ được thực hiện một lần.

### 5.3. exp chỉ giới hạn cửa sổ replay

Token có TTL ngắn làm giảm khoảng thời gian token bị lộ có thể bị sử dụng. Tuy nhiên, trong thời gian token còn hiệu lực, kẻ tấn công vẫn có thể phát lại token nhiều lần.

TTL là biện pháp giảm thiểu tác động, không phải cơ chế chống replay hoàn chỉnh.

### 5.4. jti chỉ hỗ trợ chống replay khi có trạng thái

Một token có jti duy nhất:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user-42",
  "aud": "https://payments.example.org",
  "jti": "request-or-token-id-123",
  "exp": 2000000000
}
~~~

Nếu API chỉ đọc jti rồi bỏ qua, token vẫn có thể được phát lại. Để dùng jti phát hiện replay, API cần lưu dấu đã sử dụng hoặc bị chặn và kiểm tra một cách nhất quán. Với nhiều instance, thao tác kiểm tra-và-ghi phải có tính nguyên tử để hai request đồng thời không cùng vượt qua kiểm tra.

Ngoài ra, cần phân biệt jti định danh **token** với một nonce định danh **proof/request**. Một access token có thể được sử dụng hợp lệ cho nhiều request khác nhau; chặn mọi lần sử dụng lại jti của token sẽ vô tình biến token thành one-time token và làm hỏng mô hình bearer thông thường.

## 6. Các biện pháp chống replay

Chọn biện pháp theo loại replay cần ngăn chặn. Chống sử dụng lại token, chống sử dụng lại proof và ngăn thực thi giao dịch trùng lặp là ba bài toán có liên quan nhưng khác nhau.

### 6.1. Sender-constrained token

Sender-constrained token ràng buộc access token với bằng chứng sở hữu một khóa hoặc chứng chỉ. Kẻ tấn công chỉ lấy được token nhưng không có khóa tương ứng sẽ khó dùng bản sao token.

Hai cơ chế thường gặp:

- **DPoP:** client ký proof cho request bằng khóa riêng; access token được ràng buộc với khóa công khai tương ứng.
- **mTLS-bound access token:** token được ràng buộc với chứng chỉ client; resource server xác minh kết nối mTLS và thông tin ràng buộc.

Sender constraint giảm rủi ro token bị sao chép, nhưng không giải quyết mọi trường hợp endpoint bị chiếm quyền. Nếu mã độc có thể sử dụng khóa trên thiết bị hoặc gọi ứng dụng ký proof, nó vẫn có thể tạo request hợp lệ.

### 6.2. DPoP: proof gắn với request

DPoP proof thường chứa các thông tin như:

- **htm:** phương thức HTTP.
- **htu:** URI đích theo quy tắc DPoP.
- **iat:** thời điểm tạo proof.
- **jti:** định danh duy nhất của proof.
- **ath:** hash của access token trong proof dùng cùng access token.
- **nonce:** giá trị do server cung cấp khi triển khai yêu cầu nonce.

Resource server xác minh chữ ký proof, khóa công khai và sự ràng buộc với access token; kiểm tra method, URI, thời gian, nonce theo chính sách. Để phát hiện proof bị phát lại, server có thể lưu jti của proof trong một cửa sổ thời gian và từ chối jti đã thấy. Nonce do server cấp giúp ràng buộc proof với một thử thách mới.

DPoP không có nghĩa server tự động chống replay nếu bỏ qua việc kiểm tra proof trùng lặp hoặc nonce theo profile. Hệ thống phải triển khai đầy đủ yêu cầu của RFC 9449.

### 6.3. mTLS và certificate-bound token

Với mTLS, client trình chứng chỉ trong quá trình bắt tay TLS. Authorization server có thể ràng buộc access token với fingerprint chứng chỉ. Resource server so khớp chứng chỉ của kết nối hiện tại với thông tin ràng buộc trong token.

Nếu chỉ có bản sao access token mà không có khóa riêng của chứng chỉ, kẻ tấn công không thể dễ dàng sử dụng token trên một kết nối khác. Cần quản lý chứng chỉ, khóa riêng, gia hạn, thu hồi và proxy termination chính xác; nếu TLS kết thúc ở gateway, phải bảo đảm thông tin chứng chỉ được chuyển tiếp qua một ranh giới tin cậy đã xác thực.

### 6.4. Nonce, timestamp và request identifier

Với thông điệp hoặc giao dịch có yêu cầu một lần:

- **Nonce:** giá trị ngẫu nhiên hoặc thử thách duy nhất được cấp cho một request/phiên.
- **Timestamp:** giới hạn độ mới của thông điệp; server từ chối thông điệp quá cũ hoặc quá xa trong tương lai theo chính sách.
- **Request ID / message ID:** định danh duy nhất để phát hiện thông điệp đã được xử lý.
- **Replay cache:** lưu ID đã dùng trong cửa sổ hiệu lực và từ chối bản trùng.

Các giá trị này phải được ràng buộc bằng chữ ký/MAC hoặc cơ chế xác thực thông điệp. Nếu attacker có thể sửa timestamp hoặc request ID mà không làm xác minh thất bại, chúng không tạo ra bảo vệ.

Một quy trình khái quát:

~~~text
verify_message_authenticity(message)
verify_timestamp_within_allowed_window(message.timestamp)
verify_nonce_or_request_id_is_fresh(message.id)
atomically_record_message_id_as_used(message.id)
execute_operation_once()
~~~

Đây là pseudocode minh họa. Kiểm tra và ghi nhận ID phải được thực hiện nguyên tử trong môi trường nhiều instance; nếu không, hai request đồng thời có thể cùng thấy ID chưa tồn tại.

### 6.5. Idempotency và chống giao dịch trùng lặp

**Idempotency** là thuộc tính khi thực hiện lại cùng một thao tác với cùng định danh thì kết quả nghiệp vụ không bị nhân đôi. Ví dụ, client gửi yêu cầu thanh toán với một idempotency key; nếu timeout và phải retry, server trả kết quả đã lưu thay vì tạo giao dịch mới.

Idempotency không thay thế xác thực và chống replay:

- Request vẫn phải có token hợp lệ và quyền phù hợp.
- Idempotency key phải được ràng buộc với chủ thể/client, endpoint và nội dung nghiệp vụ phù hợp.
- Server phải lưu trạng thái xử lý và bảo đảm cập nhật nguyên tử.
- Không dùng một key chung dễ đoán cho mọi người dùng.
- Cần xác định thời hạn lưu key và cách xử lý request cùng key nhưng payload khác nhau.

Idempotency giúp ngăn tác động nghiệp vụ bị lặp khi retry hoặc phát lại một số request, nhưng không tự ngăn kẻ tấn công đọc dữ liệu hoặc gọi endpoint khác bằng token bị đánh cắp.

## 7. Kết hợp bảo vệ bí mật, thu hồi và chống replay

Ba yêu cầu cần được xử lý ở nhiều lớp. Một thiết kế tham khảo:

~~~mermaid
flowchart TD
    A["Authorization Server cấp token"] --> B["Token có scope/audience tối thiểu và TTL hợp lý"]
    B --> C["Client lưu token an toàn"]
    C --> D["Gửi request qua TLS"]
    D --> E["Resource Server xác minh issuer, audience, thời hạn và chữ ký"]
    E --> F["Kiểm tra trạng thái thu hồi khi chính sách yêu cầu"]
    F --> G["Kiểm tra sender proof / nonce / request ID nếu áp dụng"]
    G --> H["Đánh giá quyền trên tài nguyên"]
    H --> I["Thực thi có idempotency cho thao tác cần chống trùng"]
    I --> J["Audit event không chứa token bí mật"]
~~~

Các lớp không thay thế nhau:

| Mục tiêu | Biện pháp chính | Giới hạn còn lại |
| --- | --- | --- |
| Giữ claims bí mật | JWE, giảm claims, kiểm soát khóa giải mã | Metadata/header vẫn có thể lộ; bên có khóa vẫn đọc được |
| Bảo vệ token khi truyền | TLS | Endpoint, storage và log vẫn có thể làm lộ token |
| Giới hạn thời gian sử dụng | exp/TTL ngắn | Không thu hồi ngay trước exp |
| Thu hồi sớm | Introspection, denylist, session/account status | Cache và đồng bộ tạo độ trễ |
| Giảm replay token bị sao chép | DPoP hoặc mTLS-bound token | Endpoint bị kiểm soát vẫn có thể sử dụng khóa |
| Chặn proof/request bị phát lại | Nonce, timestamp, proof jti, replay cache | Cần trạng thái, đồng bộ và cửa sổ thời gian đúng |
| Ngăn giao dịch bị nhân đôi | Idempotency key và xử lý nguyên tử | Không thay thế xác thực, phân quyền hoặc bí mật |

## 8. Ví dụ thực tế

### Tình huống A — Payload JWS chứa thông tin nhạy cảm

Một ứng dụng đưa email, số điện thoại và mã khách hàng vào access token JWS. Người dùng sao chép token vào công cụ debug và người khác giải mã Base64url để đọc payload.

**Bài học:** chữ ký không che giấu claims. Giảm dữ liệu trong token; dùng JWE hoặc API có kiểm soát quyền nếu thật sự cần bảo mật nội dung.

### Tình huống B — Người dùng bị khóa nhưng JWT còn hạn

Quản trị viên khóa tài khoản lúc 09:20. JWT đã cấp lúc 09:00 còn hạn đến 10:00. API chỉ xác minh chữ ký và exp nên tiếp tục chấp nhận token.

**Bài học:** JWT offline không tự biết trạng thái mới. Chọn TTL, introspection, denylist hoặc kiểm tra phiên/tài khoản theo SLA thu hồi.

### Tình huống C — Refresh token bị thu hồi nhưng access token vẫn hoạt động

Authorization server thu hồi refresh token. Một JWT access token đã cấp trước đó vẫn được API chấp nhận vì API xác minh offline và không tra cứu trạng thái.

**Bài học:** thu hồi refresh token chặn việc xin token mới; không mặc nhiên vô hiệu hóa access token hiện có.

### Tình huống D — Gửi lại request chuyển tiền

Client gửi request tạo giao dịch. Kẻ tấn công ghi lại request có token còn hạn và gửi lại. API xác minh JWT thành công và tạo giao dịch lần nữa.

**Bài học:** chữ ký token không ngăn request replay. Dùng sender constraint, nonce/request ID hoặc idempotency cho thao tác tài chính; bảo đảm kiểm tra và ghi nhận nguyên tử.

### Tình huống E — jti có trong JWT nhưng không được kiểm tra

Issuer tạo mỗi JWT với jti duy nhất. Resource server không lưu trạng thái hoặc kiểm tra jti. Token bị sao chép và sử dụng nhiều lần.

**Bài học:** jti chỉ là định danh. Muốn chống replay hoặc thu hồi theo jti, phải có cơ chế trạng thái được resource server thực sự sử dụng.

### Tình huống F — DPoP proof bị phát lại

Client ký DPoP proof có jti và iat. Resource server chỉ kiểm tra chữ ký mà không kiểm tra proof đã dùng hoặc nonce theo yêu cầu. Kẻ tấn công sao chép proof và gửi lại trong cửa sổ chấp nhận.

**Bài học:** triển khai đầy đủ kiểm tra freshness và replay theo RFC 9449; chữ ký proof một mình không bảo đảm proof chỉ dùng một lần.

## 9. Lựa chọn biện pháp theo yêu cầu

| Yêu cầu hệ thống | Hướng thiết kế có thể phù hợp |
| --- | --- |
| Payload chỉ chứa subject, audience, scope và thời gian; nhiều API cần xác minh offline | JWS có chữ ký bất đối xứng, TLS, claims tối thiểu và TTL phù hợp |
| Claims chứa dữ liệu phải giữ bí mật khỏi người cầm token | Không đưa dữ liệu vào token nếu có thể; nếu cần thì JWE với quản lý khóa người nhận |
| Quyền có thể bị thu hồi nhanh | Opaque token + introspection, hoặc JWT kết hợp introspection/denylist/trạng thái phiên |
| Chỉ cần giới hạn thời gian token bị lộ | TTL ngắn kết hợp bảo vệ storage và refresh token |
| Bản sao access token đơn lẻ không được đủ để gọi API | DPoP hoặc mTLS-bound access token |
| Request nhạy cảm không được thực thi hai lần | Nonce/request ID, replay cache và idempotency theo nghiệp vụ |
| Một web application chỉ cần phiên đăng nhập nội bộ | Cookie session và session store có thể đơn giản hơn JWT |
| Vừa cần bí mật payload vừa cần xác thực issuer | JWS lồng trong JWE, xác minh đầy đủ từng lớp |

## 10. Checklist thiết kế

### Bí mật

- [ ] Không nhầm Base64url với mã hóa.
- [ ] Không đưa mật khẩu, khóa bí mật hoặc dữ liệu nhạy cảm không cần thiết vào JWS.
- [ ] Chọn JWE khi cần bảo vệ payload và xác định rõ người được phép giải mã.
- [ ] Xem xét metadata trong protected header và dữ liệu ngoài token vẫn có thể bị lộ.
- [ ] Dùng TLS và bảo vệ storage, log, trace, URL, clipboard và endpoint.

### Thu hồi

- [ ] Xác định thời gian thu hồi tối đa có thể chấp nhận.
- [ ] Đặt TTL phù hợp với độ nhạy dữ liệu và rủi ro.
- [ ] Không coi exp là cơ chế thu hồi tức thời.
- [ ] Không coi jti tự nó là denylist.
- [ ] Phân biệt thu hồi refresh token với thu hồi access token đã cấp.
- [ ] Chọn introspection, denylist, trạng thái phiên/tài khoản hoặc rotation theo yêu cầu.
- [ ] Đưa cache TTL và độ trễ đồng bộ vào SLA thu hồi.

### Chống phát lại

- [ ] Xác định cần chống token replay, request replay hay proof replay.
- [ ] Cân nhắc DPoP/mTLS cho token cần ràng buộc người gửi.
- [ ] Kiểm tra freshness, nonce, request ID và proof jti khi profile yêu cầu.
- [ ] Lưu trạng thái replay với thao tác nguyên tử và thời gian lưu phù hợp.
- [ ] Dùng idempotency cho thao tác nghiệp vụ cần tránh giao dịch trùng lặp.
- [ ] Không nhầm idempotency với xác thực hoặc phân quyền.

## 11. Tự kiểm tra

| Câu hỏi | Đáp án |
| --- | --- |
| Người có JWS đã ký có thể đọc payload không? | **Có.** Payload thường chỉ được mã hóa Base64url, không được mã hóa bí mật. |
| Chữ ký JWT có ngăn token bị sao chép và gửi lại không? | **Không.** Token nguyên vẹn vẫn có chữ ký hợp lệ. |
| exp có thu hồi token ngay khi tài khoản bị khóa không? | **Không.** exp chỉ giới hạn thời điểm hết hạn. |
| Chỉ thêm jti có ngăn request replay không? | **Không.** Cần lưu và kiểm tra trạng thái hoặc cơ chế chống replay khác. |
| Thu hồi refresh token có tự động làm access token JWT hiện tại mất hiệu lực không? | **Không.** Resource server offline có thể tiếp tục chấp nhận access token hiện tại. |
| JWE có tự chứng minh ai đã phát hành nội dung không? | **Không trong mọi mô hình.** Cần xác minh nguồn phát hành riêng, ví dụ chữ ký JWS bên trong. |
| TLS có ngăn token bị lộ trong browser storage hoặc log không? | **Không.** TLS bảo vệ kênh truyền giữa các endpoint của kết nối. |
| DPoP có cần kiểm tra proof bị phát lại không? | **Có.** Cần kiểm tra freshness, jti/nonce và các ràng buộc theo profile. |
| Idempotency có thay thế phân quyền không? | **Không.** Request vẫn cần xác thực và quyền hợp lệ. |
| Nếu cần thu hồi trong tối đa 30 giây, chỉ dùng JWT offline với TTL 15 phút có đáp ứng không? | **Không.** Cần cơ chế trạng thái/thu hồi được kiểm tra trong SLA đã đặt ra. |

## 12. Ghi nhớ

- **JWT là định dạng claims**, không tự bảo đảm bí mật, thu hồi hay chống phát lại.
- **JWS bảo vệ toàn vẹn/xác thực nguồn theo khóa**, nhưng payload thường đọc được. Base64url không phải encryption.
- **JWE bảo vệ bí mật và toàn vẹn mật mã theo cấu hình**, nhưng không tự xác thực issuer trong mọi mô hình.
- **exp giới hạn thời gian**, không phải cơ chế thu hồi. JWT xác minh offline có thể còn được chấp nhận sau khi quyền đã thay đổi.
- **jti chỉ có ích cho thu hồi/replay khi được kiểm tra với trạng thái**; một claim không tự tạo ra trạng thái.
- **Bearer token có thể bị replay** nếu bị sao chép. DPoP và mTLS giúp ràng buộc token với người gửi; nonce, proof ID và replay cache xử lý freshness.
- **Idempotency ngăn tác động nghiệp vụ trùng lặp** trong phạm vi được thiết kế, không thay thế xác thực hoặc phân quyền.
- Thiết kế phải xác định rõ SLA về bí mật, thu hồi và chống replay, sau đó kiểm thử đúng các cam kết đó.

### Tiêu chuẩn và tài liệu tham khảo

- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7515 – JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7516 – JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 6750 – OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 – OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 – OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8705 – OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9449 – OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 – Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
