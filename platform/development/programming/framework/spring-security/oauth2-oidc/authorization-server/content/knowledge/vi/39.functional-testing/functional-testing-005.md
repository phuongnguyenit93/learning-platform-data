# Kiểm thử Device Authorization và các trạng thái polling

Device Authorization Grant giải quyết tình huống thiết bị có kết nối Internet nhưng không có trình duyệt phù hợp hoặc khó nhập thông tin, chẳng hạn smart TV, máy chơi game, thiết bị streaming, máy in hoặc CLI trên máy chủ từ xa. Thiết bị bắt đầu yêu cầu ủy quyền và hiển thị một mã ngắn cùng địa chỉ xác minh. Người dùng mở trình duyệt trên điện thoại hoặc máy tính khác, đăng nhập, nhập mã và chấp thuận quyền truy cập. Thiết bị ban đầu tiếp tục hỏi token endpoint theo chu kỳ cho đến khi người dùng hoàn tất, từ chối hoặc phiên hết hạn.

Luồng này được định nghĩa trong RFC 8628, là một OAuth 2.0 extension grant. Spring Authorization Server có sẵn Device Authorization endpoint, Device Verification endpoint và xử lý device_code tại Token endpoint. Phần cần kiểm thử kỹ là vòng đời của hai mã, giao diện xác minh trên trình duyệt, cách client polling, và việc hệ thống phản ứng chính xác với từng trạng thái.

Bài thực hành tập trung vào các mục tiêu:

- Phân biệt device_code và user_code, hiểu vai trò của từng endpoint.
- Đăng ký client được phép dùng Device Authorization Grant trong Spring Authorization Server.
- Hoàn thiện trang xác minh người dùng và consent.
- Viết client polling tuân thủ interval, authorization_pending, slow_down, access_denied và expired_token.
- Kiểm thử các trạng thái hợp lệ, lỗi, hết hạn, polling quá nhanh và replay.
- Bảo vệ user_code khỏi brute force, device_code khỏi rò rỉ và người dùng khỏi remote phishing.

## 1. Hiểu luồng Device Authorization

Device Authorization Grant tách thiết bị khởi tạo yêu cầu khỏi thiết bị người dùng dùng để xác thực. Thiết bị đầu tiên không cần nhận callback từ trình duyệt. Nó chỉ cần một kết nối outbound đến Authorization Server để xin mã và polling Token endpoint.

Ví dụ: người dùng mở ứng dụng trên TV và chọn “Đăng nhập”. TV gọi Device Authorization endpoint, nhận mã, hiển thị địa chỉ xác minh và user_code. Người dùng mở điện thoại, truy cập địa chỉ đó, đăng nhập vào tài khoản và xác nhận TV đang hiển thị đúng mã. Sau khi người dùng chấp thuận, TV nhận access token ở lần polling tiếp theo.

~~~text
TV / CLI / thiết bị hạn chế nhập liệu
       |
       | 1. POST device_authorization
       v
Spring Authorization Server
       |
       | 2. device_code + user_code
       |    verification_uri + expires_in + interval
       v
Thiết bị hiển thị mã và hướng dẫn
       |
       |                         Điện thoại / trình duyệt
       |                                  |
       |                                  | 3. Mở verification_uri
       |                                  v
       |                         Đăng nhập người dùng
       |                                  |
       |                                  | 4. Nhập user_code
       |                                  v
       |                         Hiển thị client và scope
       |                                  |
       |                                  | 5. Approve / Deny
       |                                  v
       |                         Authorization Server
       |
       | 6. Poll token endpoint bằng device_code
       |    authorization_pending / slow_down
       |    (hoặc access_denied / expired_token)
       |
       | 7. Người dùng approve
       v
Token endpoint trả access token
~~~

Thiết bị không gửi người dùng về một redirect_uri như Authorization Code Flow. Nó cũng không nhận authorization code để tự đổi token. Device Authorization endpoint trả về hai mã có mục đích khác nhau:

| Giá trị | Dùng ở đâu | Ai sử dụng | Cách bảo vệ |
|---|---|---|---|
| device_code | Token endpoint | Thiết bị đang chờ cấp quyền | Bí mật, entropy cao, không hiển thị cho người dùng, không ghi log |
| user_code | Trang xác minh | Người dùng nhập trên trình duyệt thứ hai | Mã ngắn dễ nhập nhưng phải có entropy, giới hạn lần thử và thời hạn |
| verification_uri | Màn hình thiết bị và trình duyệt | Người dùng | URL HTTPS ngắn, ổn định và thuộc đúng Authorization Server |
| verification_uri_complete | QR/NFC hoặc deep link | Trình duyệt thứ hai | Có thể chứa user_code; vẫn cần người dùng xác nhận đúng thiết bị |
| expires_in | Thiết bị và server | Cả client và server | Xác định thời hạn của phiên device authorization |
| interval | Client polling | Thiết bị | Khoảng chờ tối thiểu giữa các lần poll |

Không được nhầm device_code với user_code. Device_code là mã xác minh thiết bị gửi lại ở Token endpoint và không dành cho người dùng. User_code là mã dễ nhập để liên kết phiên chờ với hành động xác minh trên trình duyệt.

## 2. Các endpoint và request/response

Theo tài liệu Spring Authorization Server 1.5.8, các endpoint mặc định gồm:

| Endpoint | Mặc định | Vai trò |
|---|---|---|
| Device Authorization | /oauth2/device_authorization | Client xin device_code và user_code |
| Device Verification | /oauth2/device_verification | Nhận user_code từ trình duyệt và xử lý xác minh |
| Token | /oauth2/token | Client polling bằng device_code để lấy token |

Device Authorization request dùng HTTP POST với form URL encoded. Public client gửi client_id. Confidential client phải xác thực theo phương thức đã đăng ký, giống các yêu cầu OAuth khác.

~~~http
POST /oauth2/device_authorization HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

client_id=tv-device-client&scope=media.read%20profile
~~~

Nếu client là confidential và đăng ký client_secret_basic, request phải có Authorization header tương ứng. Không gửi client secret trong firmware của thiết bị công cộng hoặc ứng dụng có thể bị người dùng trích xuất. RFC 8628 xem các thiết bị như vậy là public client trừ khi có biện pháp bảo vệ bổ sung đáng tin cậy.

Response thành công có dạng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "device_code": "DEVICE_CODE_HIGH_ENTROPY",
  "user_code": "WDJB-MJHT",
  "verification_uri": "https://auth.example.test/activate",
  "verification_uri_complete": "https://auth.example.test/activate?user_code=WDJB-MJHT",
  "expires_in": 600,
  "interval": 5
}
~~~

Các trường bắt buộc là device_code, user_code, verification_uri và expires_in. verification_uri_complete và interval là tùy chọn. Nếu response không có interval, client phải dùng mặc định 5 giây. Server cần trả response không được cache; các mã này có thể dùng để hoàn tất một authorization session.

Client nên hiển thị:

- Địa chỉ verification_uri đầy đủ và dễ đọc.
- user_code có khoảng cách hoặc dấu gạch nối để người dùng nhập chính xác.
- Thời gian còn lại trước khi mã hết hạn.
- Hướng dẫn mở trình duyệt trên thiết bị khác và chấp thuận quyền.
- Trạng thái chờ, thành công, bị từ chối hoặc hết hạn.

Không hiển thị device_code. Không tự khởi tạo Device Authorization request khi ứng dụng khởi động hoặc khi phiên trước hết hạn. Chỉ bắt đầu khi người dùng chủ động chọn đăng nhập hoặc liên kết thiết bị, nhằm tránh tạo nhiều phiên và tải polling không cần thiết.

### Token request

Sau khi hiển thị hướng dẫn, thiết bị gửi Token request bằng grant type đã đăng ký trong RFC 8628:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:device_code&
device_code=DEVICE_CODE_HIGH_ENTROPY&
client_id=tv-device-client
~~~

Với confidential client, xác thực client theo phương thức đã đăng ký. client_id là bắt buộc khi client không xác thực bằng client credentials. device_code phải là giá trị nhận từ Device Authorization response và phải thuộc chính client đang gửi request.

Khi người dùng đã chấp thuận, Token endpoint trả token response thông thường của OAuth 2.0, có thể gồm access_token, token_type, expires_in, scope và refresh_token nếu client/policy được phép. Không giả định mọi Device Authorization client đều nhận refresh token. Hãy kiểm tra RegisteredClient và TokenSettings.

## 3. Vòng đời và trạng thái của device authorization

Có thể mô hình hóa một phiên device authorization bằng các trạng thái sau:

~~~text
                  Device Authorization request
                              |
                              v
                           PENDING
                         /    |     \
                        /     |      \
                       v      v       v
                  APPROVED  DENIED  EXPIRED
                     |
                     | Token endpoint poll hợp lệ
                     v
                   ISSUED
                     |
                     v
                 CONSUMED
~~~

Ý nghĩa của từng trạng thái:

| Trạng thái | Điều kiện | Hành vi ở Token endpoint | Hành vi ở trang xác minh |
|---|---|---|---|
| PENDING | Đã tạo mã, người dùng chưa hoàn tất | authorization_pending | Cho phép đăng nhập, nhập mã và xem yêu cầu |
| APPROVED | Người dùng đã xác thực và chấp thuận | Lần poll hợp lệ tiếp theo có thể nhận token | Hiển thị hoàn tất và yêu cầu quay lại thiết bị |
| DENIED | Người dùng từ chối | access_denied | Hiển thị đã từ chối |
| EXPIRED | device_code/user_code hết hạn | expired_token | Từ chối mã hết hạn, yêu cầu tạo phiên mới |
| ISSUED/CONSUMED | Token đã được phát hành và mã đã sử dụng | Không phát hành lại token từ cùng device_code | Không cho xác nhận hoặc sử dụng lại phiên |

Đây là mô hình nghiệp vụ để thiết kế và kiểm thử. Trạng thái nội bộ thực tế có thể được biểu diễn bằng token metadata, authorization attributes và trạng thái token trong OAuth2Authorization. Không nên giả định tên enum nội bộ phải trùng với các nhãn trong bảng.

Một phiên cần được liên kết với client đã yêu cầu, scope, thời điểm tạo, thời hạn, user_code, device_code và trạng thái consent. Khi người dùng approve, authorization phải gắn với đúng client và scope ban đầu. Không được cho phép người dùng nhập một mã rồi vô tình chấp thuận quyền của một phiên khác.

## 4. Hiểu polling interval và các trạng thái trả về

Polling là điểm khác biệt quan trọng nhất của Device Authorization Grant. Thiết bị gửi token request lặp lại vì không có kênh callback trực tiếp từ trình duyệt thứ hai. Client phải điều chỉnh tốc độ dựa trên interval và error code.

Các lỗi đặc thù của RFC 8628:

| Error | Ý nghĩa | Client phải làm gì |
|---|---|---|
| authorization_pending | Người dùng chưa hoàn tất xác minh/consent | Tiếp tục polling sau ít nhất interval |
| slow_down | Client polling quá nhanh hoặc server yêu cầu giảm tần suất | Tăng interval thêm 5 giây và giữ khoảng mới cho các lần poll tiếp theo |
| access_denied | Người dùng từ chối | Dừng polling, thông báo bị từ chối |
| expired_token | device_code hết hạn và phiên kết thúc | Dừng polling; chỉ tạo phiên mới khi người dùng chủ động yêu cầu |
| invalid_client / invalid_grant / lỗi khác | Client hoặc grant request không hợp lệ | Dừng polling và xử lý lỗi theo loại |

### Quy tắc thời gian

1. Client phải chờ ít nhất số giây trong interval trước mỗi lần poll. Nếu response không có interval, dùng 5 giây.
2. Khi nhận authorization_pending, tiếp tục polling với khoảng chờ hiện tại.
3. Khi nhận slow_down, tăng khoảng chờ thêm 5 giây cho lần tiếp theo và tất cả các lần sau của phiên đó.
4. Khi request bị timeout kết nối, client phải giảm tần suất polling trước khi retry. Exponential backoff, ví dụ nhân đôi khoảng chờ sau mỗi timeout, được RFC khuyến nghị.
5. Với mọi error khác authorization_pending và slow_down, dừng polling và hiển thị kết quả phù hợp.
6. Không gửi nhiều poll song song cho cùng một device_code. Chỉ có một vòng lặp polling cho mỗi phiên.
7. Không tiếp tục poll sau expires_in hoặc sau khi nhận trạng thái terminal.

Ví dụ: server trả interval = 5. Client đợi ít nhất 5 giây trước poll đầu tiên. Nếu server trả authorization_pending, client đợi ít nhất 5 giây nữa. Nếu server trả slow_down, client tăng interval thành 10 giây và dùng 10 giây cho các lần tiếp theo. Nếu một request bị timeout, client có thể tăng tiếp khoảng chờ theo exponential backoff; không được giảm xuống dưới interval hiện tại.

### State machine phía client

~~~text
Nhận device authorization response
             |
             v
Tính deadline từ expires_in
             |
             v
Đợi interval (hoặc 5 giây)
             |
             v
POST token endpoint
             |
       +-----+-------------------------+
       |                               |
       v                               v
  HTTP 200 token                    OAuth error
       |                               |
       v                    +----------+-----------+
  Hoàn tất phiên             |          |           |
                             v          v           v
                   authorization_pending slow_down  Terminal error
                             |          |           |
                             v          v           v
                      Đợi interval  interval + 5s  Dừng polling
                             |          |
                             +-----+----+
                                   |
                                   v
                             Poll tiếp nếu
                             chưa hết hạn
~~~

Client nên dùng monotonic clock để tính deadline, tránh thay đổi đồng hồ hệ thống làm kéo dài phiên. Khi response có expires_in, lưu deadline cục bộ. Nếu thiết bị ngủ hoặc mất mạng trong thời gian dài, kiểm tra deadline trước khi poll lại.

## 5. Thiết kế trang xác minh trên trình duyệt

Người dùng truy cập verification_uri qua TLS, đăng nhập vào Authorization Server, nhập user_code và xem yêu cầu đang chờ. Authorization Server phải cho người dùng biết họ đang cấp quyền cho ứng dụng hoặc thiết bị nào và những scope nào sẽ được cấp.

Một trình tự UI nên có:

1. Trang GET verification_uri hiển thị form nhập user_code.
2. Người dùng nhập mã trên thiết bị thứ hai.
3. Server chuẩn hóa định dạng mã và tìm phiên đang chờ.
4. Nếu chưa đăng nhập, chuyển đến trang đăng nhập rồi quay lại bước xác minh.
5. Hiển thị tên client/ứng dụng, scope và thông tin thiết bị đáng tin cậy nếu có.
6. Yêu cầu người dùng approve hoặc deny rõ ràng.
7. Sau khi hoàn tất, thông báo quay lại thiết bị ban đầu.
8. Token endpoint phản ánh quyết định trong lần poll tiếp theo.

Ví dụ form HTML rút gọn:

~~~html
<form method="post" action="/oauth2/device_verification">
    <label for="user_code">Mã hiển thị trên thiết bị</label>
    <input id="user_code"
           name="user_code"
           autocomplete="one-time-code"
           required>
    <button type="submit">Tiếp tục</button>
</form>
~~~

Ví dụ này chỉ minh họa field và endpoint. Trang thực tế phải tích hợp CSRF token theo cấu hình Spring Security, validation, thông báo lỗi thân thiện, accessibility và chính sách session. Không tắt CSRF toàn ứng dụng chỉ để form hoạt động.

Trong Spring Authorization Server, deviceVerificationEndpoint filter xử lý việc gửi user_code. verificationUri trong Device Authorization response là địa chỉ trang người dùng truy cập; trang GET có thể do ứng dụng cung cấp. Hai URI này có thể khác nhau:

- /activate: trang GET để người dùng nhập mã.
- /oauth2/device_verification: endpoint nhận POST user_code và chuyển qua các authentication provider của Spring Authorization Server.

Khi sử dụng verification_uri_complete, server có thể điền sẵn user_code vào form. Tuy nhiên, không tự động approve. Hãy hiển thị mã trên trình duyệt và yêu cầu người dùng so sánh với mã đang hiển thị trên thiết bị để giảm remote phishing.

### Nội dung cần hiển thị trước khi approve

Người dùng nên nhìn thấy thông tin đủ để nhận ra yêu cầu bất thường:

- Tên ứng dụng/client đã đăng ký.
- Loại thiết bị hoặc mô tả thiết bị nếu dữ liệu đó đến từ nguồn đáng tin.
- Các quyền/scope được yêu cầu bằng ngôn ngữ dễ hiểu.
- Thời điểm yêu cầu và thời hạn còn lại.
- Mã xác nhận để so sánh với thiết bị.
- Hai hành động rõ ràng: chấp thuận hoặc từ chối.

Không coi tên thiết bị do client tự khai báo là bằng chứng nhận dạng. Nếu cần hiển thị nhãn thiết bị, hãy quản lý qua provisioning hoặc registry tin cậy. Device Authorization Grant có nguy cơ remote phishing: kẻ tấn công có thể khởi tạo flow trên thiết bị của họ rồi dụ người dùng nhập mã vào trang thật. Hãy nói rõ người dùng đang cấp quyền cho thiết bị nào và khuyến khích họ xác nhận thiết bị đó đang ở trước mặt.

## 6. Cấu hình Device Authorization trong Spring Authorization Server

Spring Authorization Server 1.5.8 có sẵn các filter và provider cho Device Authorization endpoint, Device Verification endpoint và Device Code grant ở Token endpoint. Cấu hình mặc định của Authorization Server bao gồm các endpoint này; Token endpoint có converter/provider xử lý device_code. Các ví dụ API dưới đây theo tài liệu 1.5.8; đối chiếu phiên bản dependency đã pin trong dự án trước khi áp dụng vì API có thể thay đổi giữa các nhánh.

### Cấu hình endpoint

Có thể khai báo đường dẫn endpoint tường minh trong AuthorizationServerSettings:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.test")
            .deviceAuthorizationEndpoint("/oauth2/device_authorization")
            .deviceVerificationEndpoint("/oauth2/device_verification")
            .tokenEndpoint("/oauth2/token")
            .build();
}
~~~

Cấu hình Authorization Server có thể tùy chỉnh verification URI và consent page:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
            .with(authorizationServerConfigurer, authorizationServer ->
                    authorizationServer
                            .deviceAuthorizationEndpoint(device ->
                                    device.verificationUri("/activate"))
                            .deviceVerificationEndpoint(device ->
                                    device.consentPage("/oauth2/device-consent")));

    return http.build();
}
~~~

Ở đây /activate là URI được trả cho người dùng. Ứng dụng cần cung cấp trang GET tương ứng. POST user_code được xử lý tại deviceVerificationEndpoint đã cấu hình trong AuthorizationServerSettings. Nếu thay đổi path, đồng bộ form action và security filter chain.

Đây là phần cấu hình device endpoint, không thay thế toàn bộ cấu hình đăng nhập. Ứng dụng vẫn cần filter chain cho form login, trang /activate, consent UI, error page và static resources. Bảo vệ endpoint quản trị và health endpoint riêng. Giữ CSRF cho các thao tác web có thay đổi trạng thái theo chính sách.

### Đăng ký client

Device client thường không thể giữ client secret bí mật vì người dùng có thể truy cập firmware hoặc binary. Trong trường hợp đó, đăng ký public client với ClientAuthenticationMethod.NONE. Nếu client thực sự có khả năng giữ credential trong môi trường được bảo vệ, có thể dùng confidential client và phương thức xác thực phù hợp.

~~~java
AuthorizationGrantType DEVICE_CODE_GRANT =
        new AuthorizationGrantType(
                "urn:ietf:params:oauth:grant-type:device_code");

RegisteredClient tvClient = RegisteredClient.withId(
                UUID.randomUUID().toString())
        .clientId("tv-device-client")
        .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
        .authorizationGrantType(DEVICE_CODE_GRANT)
        .scope("media.read")
        .scope("profile")
        .clientSettings(ClientSettings.builder()
                .requireAuthorizationConsent(true)
                .build())
        .tokenSettings(TokenSettings.builder()
                .deviceCodeTimeToLive(Duration.ofMinutes(10))
                .accessTokenTimeToLive(Duration.ofMinutes(5))
                .build())
        .build();
~~~

Ví dụ trên minh họa public device client. Trong production, lưu RegisteredClient bằng repository bền vững, ví dụ JDBC. Client ID phải ổn định và được provision theo quy trình quản trị; không tạo client ID ngẫu nhiên mới mỗi lần ứng dụng khởi động. Không thêm authorization_code hoặc refresh_token grant nếu thiết bị không cần chúng.

deviceCodeTimeToLive đặt thời hạn device code. Thời hạn này phải đủ để người dùng lấy điện thoại, mở trình duyệt, đăng nhập và xác nhận, nhưng không quá dài đến mức tăng rủi ro phishing hoặc chiếm phiên. Dùng cùng chính sách hết hạn cho trải nghiệm user_code và device_code, đồng thời kiểm tra cả hai phía.

### Repository và persistence

Device authorization state cần tồn tại qua các request và giữa các instance nếu triển khai nhiều node. Dùng OAuth2AuthorizationService phù hợp với kiến trúc, thường là JdbcOAuth2AuthorizationService khi dùng JDBC. Không lưu pending device flow trong memory nếu client có thể poll vào node khác hoặc ứng dụng chạy nhiều instance.

Kiểm tra persistence có thể truy xuất authorization bằng device_code và user_code theo cơ chế của phiên bản SAS đang dùng. Đừng tự tạo một kho mã thứ hai mà không đồng bộ transaction với OAuth2AuthorizationService; nếu state user_code và device_code tách rời, có thể xảy ra trường hợp trang xác minh approve một phiên nhưng token endpoint không thấy trạng thái đó.

## 7. Triển khai client polling

Client cần một vòng polling duy nhất cho mỗi device authorization session. Pseudocode sau thể hiện quy tắc xử lý; phần HTTP, JSON parsing, cancellation và clock cần được triển khai bằng thư viện phù hợp với thiết bị.

~~~text
response = requestDeviceAuthorization()
interval = response.interval if present else 5 seconds
deadline = monotonicNow + response.expires_in
timeoutBackoff = interval

while monotonicNow < deadline:
    wait(interval)

    if monotonicNow >= deadline:
        stop with expired state

    result = requestToken(device_code)

    if result is success:
        store token securely
        stop with authorized state

    if result.error == authorization_pending:
        interval = max(interval, response.interval or 5 seconds)
        continue

    if result.error == slow_down:
        interval = interval + 5 seconds
        timeoutBackoff = interval
        continue

    if result is connection timeout:
        timeoutBackoff = max(interval, timeoutBackoff * 2)
        interval = timeoutBackoff
        continue

    stop polling and display terminal error
~~~

Một số điểm triển khai cần giữ:

- Đợi interval trước poll đầu tiên, không poll ngay sau Device Authorization response.
- authorization_pending không phải lỗi kết thúc; đó là trạng thái chờ bình thường.
- slow_down làm tăng khoảng chờ thêm 5 giây và không giảm lại trong cùng phiên.
- Timeout phải làm client giảm tần suất polling trước khi retry.
- access_denied, expired_token và các lỗi khác là terminal; dừng vòng lặp.
- Không khởi tạo phiên mới tự động sau expired_token. Hiển thị hướng dẫn và đợi người dùng chủ động bắt đầu lại.
- Không để hai thread hoặc hai process poll cùng device_code đồng thời.
- Hủy poll khi người dùng hủy đăng nhập hoặc đóng ứng dụng.
- Không lưu device_code vào log, analytics, crash report hoặc telemetry.

Nếu client có thể nhận notification qua một kênh khác, ví dụ push hoặc kết nối riêng, có thể chờ notification rồi mới poll. Tuy nhiên, đó là tối ưu ngoài luồng polling cơ bản của RFC 8628; vẫn cần kiểm tra trạng thái ở Token endpoint trước khi sử dụng token.

## 8. Kiểm thử Device Authorization endpoint

Dùng MockMvc với Spring ApplicationContext thật để kiểm tra endpoint và Security filter chain. Client fixture phải có Device Code grant và phương thức xác thực phù hợp.

Ví dụ test response của Device Authorization endpoint:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class DeviceAuthorizationEndpointTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void createsDeviceAuthorizationForRegisteredPublicClient()
            throws Exception {

        mockMvc.perform(post("/oauth2/device_authorization")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("client_id", "tv-device-client")
                        .param("scope", "media.read profile"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.device_code").isNotEmpty())
                .andExpect(jsonPath("$.user_code").isNotEmpty())
                .andExpect(jsonPath("$.verification_uri")
                        .value("https://auth.example.test/activate"))
                .andExpect(jsonPath("$.expires_in").isNumber());
    }
}
~~~

Ví dụ giả định fixture tv-device-client đã được provision và verificationUri đã cấu hình. interval là trường tùy chọn theo RFC; nếu response không có trường này, test client phải dùng default 5 giây. Test response nên xác minh Cache-Control no-store và không có thông tin secret không cần thiết.

Các trường hợp âm cần kiểm tra:

- client_id không tồn tại.
- Client không đăng ký Device Code grant.
- Scope không được cấp cho client.
- Confidential client thiếu hoặc gửi sai credential.
- Request gửi parameter trùng lặp.
- Request có scope sai định dạng.
- Device authorization endpoint không bị truy cập bằng HTTP không mã hóa ở môi trường production.

## 9. Kiểm thử polling và trạng thái token endpoint

Không nên chỉ kiểm tra một lần poll thành công. Cần kiểm tra từng nhánh trạng thái và hành vi client sau response.

| Kịch bản | Chuẩn bị | Kết quả mong đợi |
|---|---|---|
| Pending | Tạo device session, chưa nhập user_code | Token endpoint trả authorization_pending |
| Approved | User xác thực, approve đúng session | Poll tiếp theo trả token |
| Denied | User chọn deny | Poll tiếp theo trả access_denied |
| Expired | Đợi hoặc điều chỉnh clock đến hết deviceCodeTimeToLive | Token endpoint trả expired_token |
| Wrong device_code | Dùng mã không tồn tại | Request bị từ chối, không cấp token |
| Wrong client | Dùng device_code với client khác | Request bị từ chối |
| Reuse | Poll lại device_code sau khi token đã cấp | Không cấp token lần hai |
| Poll too fast | Gửi request nhanh hơn interval | Server bảo vệ capacity; nếu trả slow_down, client tăng interval đúng 5 giây |
| Network timeout | Mô phỏng timeout ở client | Client exponential backoff và không poll dồn dập |
| Scope | Yêu cầu scope ngoài policy | Không được cấp quyền vượt quá client/consent |

Ví dụ kiểm tra trạng thái pending ở Token endpoint:

~~~java
@Test
void tokenEndpointReportsAuthorizationPending() throws Exception {
    mockMvc.perform(post("/oauth2/token")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("grant_type",
                            "urn:ietf:params:oauth:grant-type:device_code")
                    .param("client_id", "tv-device-client")
                    .param("device_code", "DEVICE_CODE_FOR_PENDING_FIXTURE"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error")
                    .value("authorization_pending"));
}
~~~

Test fixture phải tạo authorization đang ở trạng thái pending trong OAuth2AuthorizationService. Không hardcode device_code giả định là hợp lệ trong một bài test chạy độc lập. Tạo session bằng Device Authorization endpoint rồi dùng giá trị thực từ response hoặc dùng fixture persistence được kiểm soát.

### Test slow_down và interval

RFC 8628 yêu cầu client tăng interval thêm 5 giây khi nhận slow_down. Cần có test riêng cho polling client để xác minh:

1. interval ban đầu được lấy từ response, hoặc default 5 giây.
2. authorization_pending không làm giảm interval.
3. slow_down làm interval tăng đúng 5 giây.
4. Các lần poll tiếp theo vẫn dùng interval đã tăng.
5. Timeout kích hoạt exponential backoff.
6. Không có request mới trước thời điểm được phép.

Không dùng Thread.sleep kéo dài trong unit test. Inject Clock, Scheduler hoặc một abstraction WaitStrategy để kiểm soát thời gian và xác minh lịch poll. Với server, kiểm tra hành vi của phiên bản Spring Authorization Server đang pin. Không giả định việc framework có Device Code provider đồng nghĩa mọi chính sách rate limit/slow_down đã được cấu hình cho hệ thống.

## 10. Kiểm thử trang xác minh và consent

Trang xác minh là một phần của security flow. Cần kiểm tra cả hành vi trình duyệt và trạng thái OAuth.

Các trường hợp cần có:

- Người dùng chưa đăng nhập được chuyển đến login và quay lại đúng phiên xác minh.
- User_code hợp lệ tìm đúng device authorization session.
- User_code không tồn tại bị từ chối với thông báo không tiết lộ quá nhiều thông tin.
- User_code đã hết hạn bị từ chối ngay ở trang xác minh.
- User_code đã được dùng hoặc phiên đã terminal không thể approve lần nữa.
- User_code sai nhiều lần bị rate limit.
- Người dùng approve thì consent được lưu và gắn với đúng client/scope.
- Người dùng deny thì Token endpoint trả access_denied.
- CSRF token được kiểm tra ở form POST.
- verification_uri_complete chỉ prefill mã; người dùng vẫn nhìn thấy mã và xác nhận đúng thiết bị.
- Người dùng có thể hủy hoặc quay lại mà không làm phát sinh token.

Một điểm cần regression test rõ ràng là thời hạn user_code ở Device Verification endpoint. Đã có báo cáo lỗi trong Spring Authorization Server về việc trang xác minh chấp nhận user_code hết hạn, trong khi lần poll tại Token endpoint mới trả expired_token. Hãy kiểm tra hành vi của phiên bản đang dùng và bảo đảm mã hết hạn bị từ chối ngay khi người dùng gửi ở trang xác minh. Không chỉ dựa vào việc Token endpoint cuối cùng từ chối token.

## 11. Bảo vệ user_code và device_code

User_code thường ngắn để người dùng nhập được trên điện thoại. Điều đó làm entropy thấp hơn device_code. Cần giới hạn số lần thử và thời hạn.

Các biện pháp cho user_code:

- Tạo bằng nguồn ngẫu nhiên mật mã, không dùng sequence tăng dần hoặc timestamp.
- Chọn tập ký tự dễ nhập, tránh ký tự dễ nhầm như O/0 và I/1.
- Chuẩn hóa chữ hoa/chữ thường và dấu gạch nối trước khi so sánh.
- Rate limit theo IP, client, session và tín hiệu tài khoản; tránh khóa tài khoản người dùng chỉ vì một nguồn IP gây brute force.
- Có thời hạn ngắn đủ dùng, không tái sử dụng code trong khoảng thời gian có thể gây nhầm phiên.
- Dùng thông báo lỗi không tiết lộ mã nào tồn tại hoặc mã thuộc user nào.
- Ghi audit số lần thất bại theo correlation ID, không ghi mã thô.

Các biện pháp cho device_code:

- Dùng entropy cao vì người dùng không cần nhập mã này.
- Không hiển thị hoặc ghi log device_code.
- Chỉ chấp nhận đúng client đã khởi tạo phiên.
- Giới hạn thời gian sống và chỉ cho phép đổi một lần.
- Không để device_code xuất hiện trong URL trình duyệt, analytics, referrer hoặc crash dump.
- Xóa/ẩn token metadata nhạy cảm theo retention policy sau khi phiên kết thúc.

### Chống remote phishing

Kẻ tấn công có thể khởi tạo device flow trên thiết bị của họ, sau đó thuyết phục nạn nhân nhập user_code trên trang Authorization Server thật. Vì vậy:

- Trang xác minh phải nói rõ người dùng đang cấp quyền cho một thiết bị.
- Hiển thị client/app name và scope cần cấp.
- Khuyến khích người dùng kiểm tra thiết bị đang hiển thị cùng user_code.
- Khi dùng QR hoặc verification_uri_complete, vẫn hiển thị mã và yêu cầu xác nhận.
- Không approve chỉ vì người dùng đã đăng nhập hoặc đã mở link.
- Không dùng thông tin do client tự khai báo làm bằng chứng duy nhất về loại thiết bị.
- Giữ thời hạn user_code đủ để thao tác nhưng ngắn để giảm giá trị của mã bị lấy cắp.

Trang verification_uri_complete có thể chứa user_code trong query string. Hạn chế third-party scripts, đặt Referrer-Policy phù hợp, tránh ghi query string vào access log và dùng Cache-Control no-store cho trang có dữ liệu phiên.

## 12. Metadata và khả năng tương thích client

RFC 8628 mở rộng OAuth Authorization Server Metadata bằng:

- device_authorization_endpoint: URL của Device Authorization endpoint.
- grant_types_supported: cần chứa urn:ietf:params:oauth:grant-type:device_code khi server hỗ trợ.

Kiểm tra metadata mà client sẽ dùng để khám phá endpoint. Với Spring Authorization Server, xác minh Authorization Server Metadata endpoint và các giá trị được công bố khớp với AuthorizationServerSettings. Nếu hệ thống đồng thời bật OIDC Discovery, phân biệt metadata OAuth với Provider Configuration metadata và kiểm tra đúng tài liệu mà client dự kiến tiêu thụ.

Không hardcode endpoint trong nhiều client nếu có thể dùng metadata. Nếu endpoint được đổi path, client cần khám phá hoặc được cập nhật cấu hình tương ứng. Kiểm thử sau thay đổi issuer, domain, reverse proxy và context path để bảo đảm verification_uri là URL công khai, dùng HTTPS và truy cập được từ thiết bị thứ hai.

## 13. Chẩn đoán sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Device Authorization trả invalid_client | Client không tồn tại hoặc authentication method sai | Kiểm tra RegisteredClient và client authentication |
| unsupported_grant_type | Client chưa đăng ký Device Code grant hoặc request sai URN | Đối chiếu grant type và form request |
| TV polling liên tục authorization_pending | Người dùng chưa nhập mã, chưa login hoặc chưa approve | Kiểm tra session user_code và trạng thái consent |
| TV nhận access_denied | Người dùng từ chối hoặc consent policy deny | Hiển thị thông báo từ chối, dừng polling |
| TV nhận expired_token | Device code hết hạn | Dừng poll, chờ người dùng chủ động bắt đầu lại |
| Trang activate báo mã không hợp lệ | User_code sai, hết hạn, đã dùng hoặc normalization khác | Kiểm tra format, TTL và lookup |
| Trang xác minh thành công nhưng token vẫn pending | Consent không được lưu hoặc authorization state không cập nhật | Kiểm tra OAuth2AuthorizationService và consent service |
| User code hết hạn vẫn được chấp thuận ở trang xác minh | Verification provider không kiểm tra expiry theo phiên bản đang dùng | Bổ sung regression test và validation ở bước verification |
| slow_down xuất hiện liên tục | Client không tăng interval hoặc nhiều poll loop chạy song song | Kiểm tra scheduler, state và interval |
| Token endpoint quá tải | Client poll quá nhanh hoặc tự khởi động flow hàng loạt | Kiểm tra interval, rate limit và việc chỉ bắt đầu flow khi có user action |
| Một node approve nhưng node khác vẫn pending | Persistence không chia sẻ hoặc cache không nhất quán | Kiểm tra JDBC store, transaction và cache invalidation |
| QR mở trang nhưng không hoàn tất | Link prefill không đúng hoặc người dùng chưa xác nhận | Kiểm tra verification_uri_complete và form workflow |

### Quy trình triage

1. Xác định client ID, thời điểm tạo phiên và correlation ID.
2. Kiểm tra response của Device Authorization endpoint đã scrub mã nhạy cảm.
3. Xác minh user_code có tồn tại, còn hạn và chưa terminal.
4. Kiểm tra người dùng đã login và consent đúng client/scope.
5. Đối chiếu trạng thái authorization trong persistence.
6. Kiểm tra interval và thời điểm các lần poll, không dựa vào log có device_code nguyên vẹn.
7. Kiểm tra node xử lý verification và node xử lý token có dùng chung persistence.
8. Chạy lại smoke test bằng client fixture mới.
9. Ghi nhận lỗi và bổ sung regression test trước khi đóng incident.

Không reset hàng loạt authorization state để chữa polling. Điều đó có thể làm mất các phiên đang chờ hợp lệ. Trước khi xóa hoặc thu hồi dữ liệu, xác định chính xác client và phiên bị ảnh hưởng.

## 14. Checklist hoàn thành lab

- [ ] Device Authorization endpoint được bật và URL công khai đúng.
- [ ] Device Verification endpoint xử lý user_code theo đúng phiên bản SAS.
- [ ] Token endpoint chấp nhận đúng grant_type device_code.
- [ ] Client được đăng ký Device Code grant và authentication method phù hợp.
- [ ] Public device client không chứa secret cố định có thể trích xuất.
- [ ] Response có device_code, user_code, verification_uri, expires_in và interval khi được cấu hình.
- [ ] Client chờ interval trước poll đầu tiên; default 5 giây khi interval vắng mặt.
- [ ] authorization_pending tiếp tục polling theo interval hiện tại.
- [ ] slow_down tăng interval thêm 5 giây cho các lần tiếp theo.
- [ ] Timeout kích hoạt exponential backoff.
- [ ] access_denied và expired_token dừng polling.
- [ ] Không có poll song song hoặc polling tự động sau khi hết hạn.
- [ ] Trang xác minh yêu cầu login, nhập mã, xem client/scope và approve/deny.
- [ ] verification_uri_complete không tự động approve và có bước xác nhận mã.
- [ ] User_code hết hạn bị từ chối ngay tại bước verification.
- [ ] User_code có rate limit và device_code có entropy cao.
- [ ] Device_code không hiển thị, không ghi log và không rò rỉ qua URL/referrer.
- [ ] Metadata công bố device_authorization_endpoint và grant type phù hợp.
- [ ] Test nhiều instance xác minh state được chia sẻ.
- [ ] Audit event ghi outcome nhưng không chứa device_code, user_code hoặc token.

Device Authorization Grant chỉ an toàn khi cả thiết bị, trình duyệt thứ hai và Authorization Server phối hợp đúng. Client phải tuân thủ polling interval và dừng khi gặp trạng thái terminal; trang xác minh phải yêu cầu người dùng nhận diện đúng thiết bị và consent; server phải bảo vệ user_code khỏi brute force, device_code khỏi rò rỉ và trạng thái khỏi bị sử dụng lại. Khi kiểm thử cả các trạng thái pending, approved, denied, expired và slow_down, hệ thống có thể phục vụ thiết bị hạn chế nhập liệu mà vẫn giữ được ranh giới ủy quyền rõ ràng.

## Tài liệu tham khảo

- RFC 8628 — OAuth 2.0 Device Authorization Grant: https://datatracker.ietf.org/doc/html/rfc8628
- Spring Authorization Server 1.5.8 — Protocol Endpoints: https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html
- Spring Authorization Server 1.5.8 — Configuration Model: https://docs.spring.io/spring-authorization-server/reference/configuration-model.html
- Spring Authorization Server 1.5.8 — AuthorizationServerSettings API: https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/AuthorizationServerSettings.html
- Spring Authorization Server 1.5.8 — TokenSettings API: https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.Builder.html
- Spring Authorization Server issue #1977 — User Code expiration report: https://github.com/spring-projects/spring-authorization-server/issues/1977

