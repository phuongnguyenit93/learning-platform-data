# Quy trình tái hiện lỗi bằng log đã che dữ liệu và request tối thiểu

Khi Authorization Server gặp lỗi, log thường cho biết request đi qua những thành phần nào, endpoint trả về trạng thái gì và OAuth báo lỗi nào. Tuy nhiên, log đầy đủ request hoặc bật DEBUG trên diện rộng có thể làm lộ authorization code, access token, refresh token, cookie phiên, client secret và dữ liệu người dùng. Một quy trình chẩn đoán tốt cần giữ đủ bằng chứng để dựng lại diễn biến, đồng thời loại bỏ giá trị có thể dùng để đăng nhập hoặc gọi API.

Bài học này trình bày cách điều tra lỗi OAuth 2.0/OpenID Connect bằng log có cấu trúc đã che dữ liệu, cách liên kết sự kiện qua nhiều dịch vụ, cách thu gọn một luồng thành request tối thiểu và cách tái hiện có kiểm soát trong môi trường kiểm thử Spring Authorization Server.

Sau khi hoàn thành, bạn có thể:

- Tạo timeline từ log của reverse proxy, Authorization Server và Resource Server bằng request ID hoặc trace ID.
- Xác định trường nào cần giữ, trường nào phải loại bỏ hoặc thay bằng bí danh.
- Chuyển một lỗi quan sát được thành giả thuyết có thể kiểm chứng.
- Tạo lại authorization request và token request tối thiểu bằng client kiểm thử.
- Ghi lại kết quả tái hiện để người khác có thể xác minh mà không cần nhận bí mật.

## 1. Nguyên tắc chẩn đoán

Mục tiêu của tái hiện lỗi là chứng minh một điều kiện cụ thể tạo ra hành vi quan sát được. Không cần sao chép toàn bộ phiên làm việc của người dùng nếu lỗi có thể được tái hiện bằng một request nhỏ hơn.

Quy trình nên giữ bốn nguyên tắc:

1. **Bắt đầu từ bằng chứng**: dùng thời điểm, endpoint, HTTP status, OAuth error và request/trace ID để xác định luồng đã xảy ra.
2. **Giữ cấu trúc, bỏ bí mật**: log cần cho biết tham số nào có mặt và kiểm tra nào thất bại, không cần lưu giá trị credential.
3. **Thay đổi từng biến**: mỗi lần thử chỉ thay một điều kiện như redirect URI, code verifier, scope hoặc cấu hình client.
4. **Tái hiện bằng dữ liệu kiểm thử**: dùng client, tài khoản và authorization code mới trong môi trường kiểm thử; không phát lại token hoặc code lấy từ sự cố thật.

Log là bằng chứng về hành vi của hệ thống. Log không phải bản sao hoàn chỉnh của request, nhất là khi dữ liệu nhạy cảm đã được loại bỏ. Khi thiếu một trường cần thiết, hãy bổ sung một sự kiện chẩn đoán an toàn ở lần thử tiếp theo thay vì khôi phục giá trị bí mật từ log cũ.

## 2. Chuẩn bị khả năng liên kết log

Một request OAuth có thể đi qua CDN, load balancer, ingress, Authorization Server, kho dữ liệu và Resource Server. Nếu mỗi thành phần dùng một mã nhận diện khác nhau hoặc đồng hồ lệch nhau, việc dựng lại thứ tự sự kiện sẽ khó khăn.

### 2.1. Request ID và trace ID

Mỗi request nên có một request ID duy nhất ở biên tiếp nhận. Nếu hệ thống dùng distributed tracing, hãy truyền trace context theo chuẩn đang triển khai, chẳng hạn W3C Trace Context với header traceparent. Log ở mỗi dịch vụ ghi lại cùng trace ID và span ID tương ứng.

| Trường | Mục đích | Lưu ý |
|---|---|---|
| request_id | Tra cứu một request tại một dịch vụ | Sinh ở gateway hoặc ứng dụng; kiểm tra định dạng và giới hạn độ dài |
| trace_id | Liên kết các span trong một luồng qua nhiều dịch vụ | Không dùng làm credential hoặc dữ liệu xác thực |
| span_id | Xác định một thao tác trong trace | Mỗi thành phần có thể có span riêng |
| event | Tên sự kiện nghiệp vụ hoặc kỹ thuật | Dùng tên ổn định như oauth.token.exchange.failed |
| timestamp | Sắp xếp sự kiện | Ghi UTC và đồng bộ đồng hồ giữa các node |
| route | Endpoint đã chuẩn hóa | Dùng route template, không ghi query string |

Không tin vô điều kiện request ID do Internet gửi đến. Gateway nên xóa giá trị tùy ý từ client rồi tạo ID mới, hoặc xác thực định dạng trước khi chấp nhận. ID chỉ phục vụ quan sát, không được dùng để cấp quyền.

Nếu chưa có tracing, vẫn có thể dùng request ID được tạo tại reverse proxy và chuyển tiếp qua header nội bộ. Ứng dụng phải chỉ nhận header này từ proxy đáng tin cậy. Khi có nhiều hop, ghi rõ ID được giữ nguyên hay được ánh xạ sang ID nội bộ.

### 2.2. Đồng bộ thời gian và định danh dịch vụ

Ghi timestamp theo UTC, có độ chính xác đủ để sắp xếp các sự kiện gần nhau. Đồng bộ thời gian trên node bằng NTP hoặc dịch vụ tương đương. Trong log nên có tên service, môi trường, phiên bản ứng dụng và instance/pod để nhận ra lỗi chỉ xảy ra trên một replica.

Khi gom log, sắp xếp theo timestamp nhưng dùng trace/span relationship để xác định quan hệ nhân quả. Hai request có timestamp sát nhau chưa chắc thuộc cùng một luồng.

### 2.3. Những sự kiện nên có

Với Authorization Server, nên ghi các sự kiện đã chuẩn hóa cho những bước quan trọng:

- Nhận authorization request và kết quả kiểm tra client, redirect URI, response type, scope, PKCE.
- Bắt đầu và kết thúc xác thực người dùng; kết quả đăng nhập ở mức thành công/thất bại.
- Hiển thị hoặc hoàn tất consent theo trạng thái, không ghi nội dung dữ liệu cá nhân.
- Phát hành authorization code và kết quả đổi code tại token endpoint.
- Xác thực client, kiểm tra grant, redirect URI, PKCE và kết quả phát hành token.
- Từ chối request với HTTP status và OAuth error code.
- Kiểm tra access token tại Resource Server, chỉ ghi kết quả và loại lỗi cần thiết.

Tên sự kiện nên mô tả hành động và kết quả, ví dụ oauth.authorization_request.rejected, oauth.user_authentication.failed, oauth.token.exchange.failed hoặc oauth.access_token.validation.failed. Tránh dùng một thông báo chung như authentication error cho mọi trường hợp.

## 3. Che dữ liệu nhạy cảm trước khi ghi log

Hãy thiết kế log theo allowlist: chỉ ghi các trường cần thiết cho chẩn đoán. Không ghi toàn bộ header, query string hoặc request body rồi trông chờ một bộ lọc xóa bí mật ở bước xuất log.

### 3.1. Các giá trị cần loại bỏ hoặc thay bằng bí danh

| Dữ liệu | Cách xử lý khi ghi log | Lý do |
|---|---|---|
| Authorization header, Basic credential | Không ghi giá trị; nếu cần, chỉ ghi authentication method | Có thể chứa client secret hoặc access token |
| access_token, refresh_token, id_token | Không ghi giá trị | Có thể dùng để truy cập tài nguyên hoặc phiên đăng nhập |
| authorization code | Không ghi giá trị; chỉ ghi sự kiện issued, redeemed, expired hoặc rejected | Code có thời hạn ngắn nhưng có thể bị đổi lấy token |
| client_secret, client_assertion, private_key_jwt | Không ghi giá trị hoặc JWT assertion | Là bằng chứng xác thực client |
| code_verifier | Không ghi giá trị; chỉ ghi present và kết quả PKCE validation | Có thể dùng để hoàn tất việc đổi authorization code |
| state, nonce | Không ghi giá trị; chỉ ghi có/không hoặc kết quả đối chiếu | Liên quan đến tương quan phiên và chống replay |
| Cookie, Set-Cookie, session ID, CSRF token | Không ghi giá trị | Có thể chiếm quyền phiên hoặc giả mạo request |
| Password, OTP, recovery code | Không ghi dưới bất kỳ dạng nào | Là thông tin xác thực trực tiếp |
| Request object, JWT assertion, SAML response | Không ghi payload hoặc chữ ký nguyên vẹn | Có thể chứa claim cá nhân và dữ liệu xác thực |
| Private key, keystore password | Không ghi; không đưa vào diagnostic bundle | Là bí mật hạ tầng |
| Email, số điện thoại, subject người dùng | Dùng bí danh hoặc mã giả lập khi cần liên kết | Có thể nhận diện cá nhân |
| Chứng thư client | Chỉ ghi fingerprint hoặc bí danh khi thực sự cần; không ghi private key | Fingerprint vẫn có thể là định danh ổn định |

Thay toàn bộ giá trị nhạy cảm bằng ký hiệu như [REDACTED]. Không chỉ che vài ký tự đầu/cuối của token, code hoặc secret vì phần còn lại vẫn có thể làm lộ dữ liệu và tạo thói quen chia sẻ credential.

### 3.2. Trường nên giữ lại

Các trường sau thường hữu ích và ít rủi ro hơn nếu đã được chuẩn hóa:

- HTTP method, route template, status code, duration và tên service.
- OAuth error code như invalid_request, unauthorized_client, invalid_grant hoặc invalid_scope.
- Grant type, response type, PKCE method và authentication method.
- Bí danh client như diagnostic-public-client thay cho định danh production khi xuất log ra ngoài.
- Bí danh redirect URI đã đăng ký, ví dụ callback-main, cùng kết quả redirect_uri_match.
- Danh sách scope đã được allowlist nếu scope không tiết lộ dữ liệu nhạy cảm.
- Trạng thái kiểm tra như client_authenticated, redirect_uri_match, code_expired, code_already_used và pkce_validation.
- Request ID, trace ID, phiên bản ứng dụng và instance.

Với state, nonce, code và code verifier, thông tin có mặt hay không thường đủ để chẩn đoán. Với redirect URI, nên ghi bí danh cấu hình và kết quả so khớp thay vì ghi URL thô có thể chứa query hoặc dữ liệu người dùng.

### 3.3. Ví dụ log trước và sau khi che dữ liệu

Một log không an toàn có thể chứa URL kèm query, Authorization header, cookie và request body. Không đưa loại log này vào ticket hoặc gửi qua chat để nhờ phân tích.

Ví dụ log có cấu trúc đã chuẩn hóa:

~~~json
{
  "timestamp": "2026-11-16T14:20:31.418Z",
  "level": "WARN",
  "service": "authorization-server",
  "environment": "test",
  "event": "oauth.token.exchange.failed",
  "request_id": "req-7f21a9",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "instance": "authorization-server-2",
  "method": "POST",
  "route": "/oauth2/token",
  "http_status": 400,
  "client_alias": "diagnostic-public-client",
  "grant_type": "authorization_code",
  "pkce_method": "S256",
  "code_present": true,
  "code_verifier_present": true,
  "redirect_uri_alias": "callback-main",
  "redirect_uri_match": true,
  "pkce_validation": "failed",
  "oauth_error": "invalid_grant",
  "duration_ms": 14
}
~~~

Log này cho biết token request thất bại tại bước kiểm tra PKCE, đồng thời cho biết redirect URI đã khớp. Nó không chứa authorization code, verifier, token, cookie hay thông tin người dùng.

Không phải mọi hệ thống đều có thể xác định chính xác code_expired, code_already_used hoặc pkce_validation. Chỉ ghi các kết quả mà ứng dụng thực sự quan sát được; không suy đoán rồi ghi thành sự thật.

## 4. Ghi log an toàn tại reverse proxy và ứng dụng

### 4.1. Reverse proxy

Access log nên ghi URI đã chuẩn hóa, không ghi toàn bộ request line có query string. Với Nginx, có thể định nghĩa một log format tối giản:

~~~nginx
log_format oauth_safe
    '$time_iso8601 request_id=$request_id '
    'method=$request_method uri=$uri '
    'status=$status request_time=$request_time';

access_log /var/log/nginx/oauth_access.log oauth_safe;
~~~

Trong ví dụ, biến uri chỉ ghi path đã chuẩn hóa, còn request line có thể chứa query string. Không thêm các biến như http_authorization, http_cookie hoặc request_body vào access log. Nếu cần địa chỉ client để điều tra, áp dụng chính sách riêng về quyền truy cập, thời hạn lưu và ẩn danh hóa.

Nếu có load balancer phía trước Nginx, cấu hình trusted proxy và real IP module theo đúng dải địa chỉ của load balancer. Không dùng giá trị X-Forwarded-For do client tự gửi để kết luận danh tính hoặc nguồn request.

### 4.2. Spring Boot và Spring Security

Ở tầng ứng dụng, hãy log sự kiện theo các trường đã chọn thay vì serialize HttpServletRequest, toàn bộ header hoặc body:

~~~java
log.info(
    "oauth.request.completed requestId={} traceId={} route={} method={} " +
    "status={} durationMs={} clientAlias={} oauthError={}",
    requestId,
    traceId,
    routeTemplate,
    requestMethod,
    statusCode,
    durationMs,
    clientAlias,
    oauthError
);
~~~

routeTemplate nên lấy từ route hoặc tên endpoint cố định, ví dụ /oauth2/authorize và /oauth2/token. Không dùng request.getRequestURL() cộng query string làm trường route. clientAlias nên được ánh xạ từ client registration đã biết, không lấy một giá trị tùy ý từ request rồi ghi thẳng vào log.

Nếu dùng OncePerRequestFilter hoặc interceptor để tạo request ID, chỉ thêm ID vào MDC sau khi đã kiểm tra định dạng và xóa MDC trong finally để tránh rò dữ liệu giữa các request dùng chung thread. Không đặt token, code hoặc session ID vào MDC.

Không bật DEBUG/TRACE toàn cục cho Spring Security trong production chỉ để tìm một lỗi. Một số log framework hoặc thư viện có thể in chi tiết request, principal hoặc thông tin xác thực. Ưu tiên sự kiện chẩn đoán có allowlist; nếu cần tăng mức log tạm thời, giới hạn package, instance, thời gian và quyền truy cập, sau đó khôi phục cấu hình ngay khi đủ bằng chứng.

## 5. Quy trình điều tra từ log đến giả thuyết

### Bước 1: Mô tả triệu chứng có thể kiểm chứng

Ghi lại điều người dùng quan sát được bằng dữ kiện cụ thể:

- Thời điểm xảy ra và múi giờ.
- Môi trường, phiên bản ứng dụng và instance nếu biết.
- Endpoint, HTTP status và OAuth error code.
- Luồng bị ảnh hưởng: authorization request, đăng nhập, consent, token exchange hay gọi Resource Server.
- Hành vi mong đợi và hành vi thực tế.
- Request ID hoặc trace ID đã được che dữ liệu.

Tránh mô tả chung như OAuth bị lỗi. Ví dụ cụ thể hơn là: token endpoint trả HTTP 400 với invalid_grant cho client kiểm thử sau khi người dùng hoàn tất authorization code flow.

### Bước 2: Thu thập log theo cùng request hoặc trace

Tra cứu request ID trong log reverse proxy và Authorization Server. Nếu request kích hoạt các dịch vụ khác, dùng trace ID để tìm các span liên quan. Lấy một khoảng thời gian vừa đủ trước và sau sự kiện để thấy bước khởi đầu và kết quả cuối cùng.

Không chỉ lọc theo client ID hoặc địa chỉ IP vì một client có thể tạo nhiều request đồng thời. Không gộp các sự kiện chỉ vì chúng xuất hiện gần nhau.

### Bước 3: Dựng timeline

Sắp xếp các sự kiện theo thời gian UTC, rồi ghi rõ thành phần phát sinh sự kiện và kết quả:

| Thứ tự | Thành phần | Sự kiện | Dữ kiện cần đối chiếu |
|---|---|---|---|
| 1 | Ingress | Request đến Authorization Server | Route, method, status, request ID |
| 2 | Authorization Server | Authorization request được kiểm tra | Client alias, response type, redirect URI match, PKCE method |
| 3 | Login/session | Xác thực người dùng | Kết quả đăng nhập, trạng thái phiên; không ghi cookie |
| 4 | Consent | Người dùng chấp thuận hoặc từ chối | Kết quả consent và scope alias |
| 5 | Authorization Server | Authorization code được phát hành | Trạng thái phát hành, client alias, thời điểm hết hạn; không ghi code |
| 6 | Token endpoint | Code được đổi lấy token | Grant type, client authentication result, redirect URI match, PKCE result |
| 7 | Resource Server | Access token được kiểm tra | Kết quả validation và mã lỗi; không ghi token |

Không phải request nào cũng đi qua tất cả bước. Hãy đánh dấu bước không xuất hiện là chưa quan sát được thay vì kết luận nó đã thất bại.

### Bước 4: Đối chiếu mong đợi với thực tế

Ở mỗi bước, đặt hai câu hỏi: hệ thống đã kiểm tra điều gì và kết quả thực tế là gì? Với authorization code flow, các điểm thường cần đối chiếu gồm:

- Client có được phép dùng authorization_code grant và response_type=code không?
- Redirect URI có khớp chính xác URI đã đăng ký không?
- PKCE có được yêu cầu và dùng đúng code_challenge_method không?
- Người dùng đã xác thực và consent theo chính sách chưa?
- Authorization code còn hạn, chưa được sử dụng và thuộc đúng client không?
- Token request có dùng cùng redirect URI đã gắn với authorization request không?
- Code verifier có tương ứng với code challenge đã phát hành không?
- Client authentication có đúng với loại client và phương thức đã đăng ký không?

### Bước 5: Viết giả thuyết và phép thử

Mỗi giả thuyết cần có bằng chứng hỗ trợ và một phép thử có thể bác bỏ nó.

| Giả thuyết | Dấu hiệu cần tìm | Phép thử tối thiểu |
|---|---|---|
| Redirect URI không khớp | redirect_uri_match=false hoặc invalid_request tại authorization endpoint | Gửi authorization request với URI đúng và URI sai trên client kiểm thử |
| PKCE verifier không khớp | pkce_validation=failed ở token endpoint | Tạo code mới, đổi bằng verifier đúng rồi thử lại bằng verifier khác |
| Authorization code hết hạn hoặc đã dùng | code_expired hoặc code_already_used nếu hệ thống có ghi trạng thái | Tạo code mới; đổi một lần rồi thử lại bằng code đã dùng trong môi trường test |
| Client authentication thất bại | client_authenticated=false hoặc invalid_client | Dùng đúng phương thức xác thực đã đăng ký và kiểm tra cấu hình client test |
| Sai scope hoặc grant | unauthorized_client hoặc invalid_scope | Bỏ từng scope hoặc dùng grant đã được client cho phép |
| Sai URL công khai sau proxy | Metadata/redirect dùng host hoặc scheme nội bộ | So sánh Forwarded header đã tin cậy với issuer và metadata công bố |

Không coi invalid_grant là bằng chứng duy nhất của lỗi PKCE. Lỗi này có thể xuất hiện khi code không hợp lệ, hết hạn, đã được sử dụng, gắn với client khác, redirect URI không khớp hoặc verifier sai. Cần dùng các sự kiện nội bộ an toàn để phân biệt nguyên nhân.

## 6. Thu gọn thành request tối thiểu

Request tối thiểu chỉ chứa các tham số bắt buộc cho tình huống đang kiểm tra. Bỏ header tùy chọn, cookie cũ, scope không liên quan và các tham số ứng dụng không cần thiết. Mỗi lần thử dùng một authorization code mới vì code thường chỉ được sử dụng một lần và có thời hạn ngắn.

### 6.1. Chuẩn bị client kiểm thử

Tạo một client riêng trong môi trường test với cấu hình đã biết:

- Client alias: diagnostic-public-client.
- Grant: authorization_code.
- Client type: public, không dùng client secret.
- PKCE: bắt buộc, method S256.
- Redirect URI: https://client.example.test/callback.
- Scope: chỉ giữ scope cần cho ca kiểm thử, ví dụ openid.

Địa chỉ example.test là tên miền dành cho ví dụ. Thay bằng endpoint và redirect URI thuộc môi trường kiểm thử của bạn. Nếu kiểm tra confidential client, dùng đúng phương thức xác thực client đang cấu hình; không chèn secret hoặc client assertion trực tiếp vào lệnh, ticket hay log.

Tài khoản kiểm thử nên không chứa dữ liệu thật. Dùng browser profile riêng cho mỗi lần chạy nếu luồng cần đăng nhập và consent, để cookie hoặc session từ lần trước không làm sai kết quả.

### 6.2. Authorization request tối thiểu

Một authorization request dùng authorization code và PKCE có dạng:

~~~bash
curl --silent --show-error --output /dev/null \
  --write-out 'HTTP %{http_code}\n' \
  --get 'https://auth.example.test/oauth2/authorize' \
  --data-urlencode 'response_type=code' \
  --data-urlencode 'client_id=diagnostic-public-client' \
  --data-urlencode 'redirect_uri=https://client.example.test/callback' \
  --data-urlencode 'scope=openid' \
  --data-urlencode 'state=<fresh-random-state>' \
  --data-urlencode 'code_challenge=<S256-challenge-for-this-test>' \
  --data-urlencode 'code_challenge_method=S256'
~~~

State và code challenge phải được tạo mới cho lần kiểm thử. Code challenge là giá trị Base64URL của SHA-256 trên code verifier tương ứng. Lệnh trên chỉ kiểm tra request và status ở endpoint; nó không tự hoàn tất đăng nhập, consent hoặc callback. Với luồng tương tác, dùng browser test profile để hoàn tất các bước đó.

Không bật curl -v khi thu thập bằng chứng chia sẻ. Verbose output có thể hiển thị URL đầy đủ, header hoặc cookie. Nếu cần kiểm tra redirect, xem tại môi trường test và che query chứa code/state trước khi lưu ảnh hoặc log.

### 6.3. Token request tối thiểu

Sau khi hoàn tất authorization flow kiểm thử, dùng authorization code mới được cấp trong chính lần chạy đó để gọi token endpoint:

~~~bash
curl --silent --show-error --output /dev/null \
  --write-out 'HTTP %{http_code}\n' \
  --request POST 'https://auth.example.test/oauth2/token' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=authorization_code' \
  --data-urlencode 'client_id=diagnostic-public-client' \
  --data-urlencode 'redirect_uri=https://client.example.test/callback' \
  --data-urlencode 'code=<fresh-authorization-code-from-this-test>' \
  --data-urlencode 'code_verifier=<matching-test-code-verifier>'
~~~

Lệnh này chỉ in HTTP status và bỏ response body để tránh in access token, refresh token hoặc ID Token ra terminal. Dùng log đã chuẩn hóa ở Authorization Server để đọc OAuth error code và bước validation thất bại. Nếu cần xem response body trong môi trường test, lưu ở vị trí được bảo vệ, chỉ trích xuất trường error đã allowlist và xóa file chứa token ngay sau khi kiểm tra.

Với confidential client, request còn cần client authentication theo đúng phương thức đăng ký như client_secret_basic, private_key_jwt hoặc mTLS. Không chuyển các credential đó thành tham số dòng lệnh hoặc đưa vào ví dụ có thể sao chép. Dùng secret manager hoặc công cụ kiểm thử có cơ chế nhập credential an toàn.

### 6.4. Giữ request thật sự tối thiểu

Khi đã có một request thành công làm baseline, tạo một bản sao chỉ thay một yếu tố:

- Đổi redirect URI để kiểm tra exact match.
- Dùng verifier khác để kiểm tra PKCE.
- Dùng code mới và hết hạn có chủ đích trong môi trường test để kiểm tra expiration.
- Dùng client test không được phép grant để kiểm tra unauthorized_client.
- Bỏ một scope để kiểm tra scope policy.

Ghi lại biến duy nhất đã thay đổi, status, OAuth error và request ID. Không tái sử dụng code hoặc token của người dùng thật để thử một trường hợp khác.

## 7. Ví dụ điều tra lỗi invalid_grant do PKCE

Giả sử một client test hoàn tất đăng nhập nhưng token endpoint trả HTTP 400 và invalid_grant. Log đã che dữ liệu cho thấy:

~~~json
{
  "event": "oauth.token.exchange.failed",
  "request_id": "req-7f21a9",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "route": "/oauth2/token",
  "http_status": 400,
  "client_alias": "diagnostic-public-client",
  "grant_type": "authorization_code",
  "redirect_uri_match": true,
  "pkce_method": "S256",
  "pkce_validation": "failed",
  "oauth_error": "invalid_grant"
}
~~~

Từ log này có thể loại bớt giả thuyết redirect URI không khớp, nhưng chưa đủ để kết luận code verifier sai nếu hệ thống chưa ghi nhận trạng thái code. Hãy kiểm tra thêm sự kiện phát hành code và kết quả lookup/expiration/redeemed nếu có.

Một phép thử có kiểm soát:

1. Tạo code verifier A ngẫu nhiên và tính code challenge S256 tương ứng.
2. Gửi authorization request mới với challenge đó, hoàn tất đăng nhập bằng tài khoản test và nhận một code mới.
3. Gửi token request với verifier A. Ghi lại status và sự kiện PKCE validation.
4. Tạo một authorization request mới với verifier B và challenge của B.
5. Khi đổi code của lần chạy thứ hai, cố ý gửi verifier A. Kết quả dự kiến là token endpoint từ chối với invalid_grant và log ghi pkce_validation=failed.
6. Đổi code mới tiếp theo bằng verifier B. Kết quả dự kiến là thành công nếu các điều kiện client, redirect URI và code đều hợp lệ.

Mỗi authorization code chỉ dùng cho một lần đổi. Không thử verifier A rồi verifier B trên cùng một code để so sánh vì lần đổi đầu tiên có thể đã tiêu thụ code. Hãy tạo một authorization flow mới cho mỗi phép thử.

Kết quả này xác nhận phép kiểm tra PKCE hoạt động theo kỳ vọng trong môi trường test. Nếu phép thử với verifier đúng vẫn thất bại, mở rộng điều tra sang thời hạn code, client binding, redirect URI, trạng thái code và cấu hình PKCE của client.

## 8. Những lỗi thường gặp khi tái hiện

| Cách làm gây sai lệch | Vì sao kết quả không đáng tin | Cách xử lý |
|---|---|---|
| Phát lại authorization code đã dùng | Code có thể đã được tiêu thụ hoặc hết hạn | Tạo authorization flow và code mới cho mỗi lần thử |
| Dùng cookie phiên từ browser khác | Session, CSRF hoặc consent state có thể không tương ứng | Dùng browser profile test mới và ghi nhận bước tương tác |
| Thay nhiều tham số cùng lúc | Không biết thay đổi nào gây ra lỗi | Chỉ thay một biến trên mỗi lần thử |
| Bật DEBUG toàn bộ production | Có thể ghi thông tin xác thực và tạo lượng log lớn | Dùng event allowlist, phạm vi nhỏ và thời gian ngắn |
| Chia sẻ ảnh Network tab nguyên trạng | URL callback, cookie hoặc response có thể chứa code/token | Che dữ liệu trước khi xuất ảnh và chỉ giữ trường cần thiết |
| Dùng thời gian local khác múi giờ | Timeline có thể sai thứ tự | Chuẩn hóa UTC và kiểm tra clock drift |
| Chỉ dựa vào HTTP status | Một status có thể ứng với nhiều nguyên nhân OAuth | Đối chiếu OAuth error và validation event |
| Gửi request trực tiếp đến backend để bỏ qua proxy | Có thể khác header, scheme, host và chính sách TLS thực tế | Tái hiện qua cùng đường ingress như request ban đầu; kiểm tra backend riêng khi cần cô lập |
| Dùng client production để thử lỗi | Có thể tạo grant, token hoặc consent ảnh hưởng người dùng thật | Tạo client và tài khoản test có cấu hình tương đương |

## 9. Đóng gói bằng chứng để chuyển giao

Một báo cáo tốt cho phép người khác tái hiện lỗi mà không cần truy cập credential hoặc dữ liệu cá nhân. Báo cáo nên có:

1. **Triệu chứng**: hành vi mong đợi, hành vi thực tế, endpoint, status và OAuth error.
2. **Môi trường**: test/staging/production, phiên bản ứng dụng, instance và cấu hình liên quan đã được làm sạch.
3. **Timeline**: các sự kiện theo UTC, request ID/trace ID và service phát sinh.
4. **Log đã che dữ liệu**: chỉ các trường allowlist, không chứa header/body thô.
5. **Request tối thiểu**: method, endpoint, tên tham số và giá trị giả lập; thay credential bằng placeholder.
6. **Kết quả**: status, OAuth error, validation result và điều kiện đã thay đổi.
7. **Giả thuyết còn lại**: điều đã được loại trừ và phép thử tiếp theo cần thực hiện.

Mẫu báo cáo:

~~~text
Symptom:
  Expected: token endpoint returns success for a valid test authorization code.
  Actual: HTTP 400, invalid_grant.

Environment:
  Environment: test
  Service version: <version>
  Client alias: diagnostic-public-client

Evidence:
  Timestamp UTC: <timestamp>
  Request ID: <request-id>
  Trace ID: <trace-id>
  Route: POST /oauth2/token
  Redirect URI match: true
  PKCE method: S256
  PKCE validation: failed

Minimal reproduction:
  Use a fresh authorization flow and code.
  Exchange with a verifier that does not match the issued challenge.

Observed result:
  HTTP 400
  OAuth error: invalid_grant

Secrets and personal data:
  Redacted before sharing.
~~~

Chỉ đính kèm log và cấu hình mà người nhận thực sự cần. Giới hạn quyền đọc, thời hạn lưu và nơi chia sẻ theo chính sách của tổ chức. Trước khi chuyển giao, tìm lại các chuỗi nhạy cảm phổ biến như Bearer, client_secret, refresh_token, code_verifier, Cookie, Set-Cookie và private key header để bảo đảm không còn dữ liệu bị bỏ sót.

## 10. Checklist trước khi kết luận

- [ ] Đã xác định chính xác luồng lỗi và endpoint xảy ra lỗi.
- [ ] Log của proxy và ứng dụng có request ID hoặc trace ID liên kết được.
- [ ] Timestamp đã chuẩn hóa UTC và node đã đồng bộ thời gian.
- [ ] Log chỉ ghi trường allowlist; query, body, Authorization header và cookie thô không được ghi.
- [ ] Authorization code, token, client secret, assertion, verifier, state và nonce đã được loại bỏ.
- [ ] Client, redirect URI và người dùng trong ví dụ đã được thay bằng bí danh hoặc dữ liệu test.
- [ ] Timeline thể hiện các bước đã quan sát và phân biệt rõ bước chưa có bằng chứng.
- [ ] Mỗi giả thuyết có một phép thử có thể xác nhận hoặc bác bỏ.
- [ ] Mỗi lần thử dùng code mới và chỉ thay một biến.
- [ ] Response chứa token không bị in vào terminal hoặc đưa vào báo cáo.
- [ ] Đã kiểm tra cả OAuth error và kết quả validation nội bộ; không kết luận từ HTTP status đơn lẻ.
- [ ] Diagnostic bundle đã được rà soát bí mật trước khi chia sẻ.

## Kết luận

Tái hiện lỗi đáng tin cậy bắt đầu từ log có cấu trúc và định danh liên kết được giữa các thành phần. Allowlist giúp giữ lại thông tin cần cho chẩn đoán như route, grant type, OAuth error và kết quả validation, trong khi credential và dữ liệu cá nhân được loại bỏ ngay tại nguồn. Khi đã dựng được timeline và giả thuyết, hãy thu gọn luồng thành request kiểm thử, thay từng biến và dùng authorization code mới cho mỗi lần chạy. Báo cáo cuối cùng cần đủ request shape, log đã che dữ liệu và kết quả để người khác xác minh mà không phải tiếp cận bí mật của sự cố.
