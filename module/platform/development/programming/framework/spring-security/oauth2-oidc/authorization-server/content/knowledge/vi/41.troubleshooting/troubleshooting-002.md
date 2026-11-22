# invalid_grant: code hết hạn, dùng lại, sai PKCE hoặc refresh token

invalid_grant cho biết authorization grant hoặc credential dùng để đổi token không còn hợp lệ trong ngữ cảnh request. Với Spring Authorization Server, lỗi thường liên quan đến authorization code đã hết hạn hoặc đã được dùng, code không khớp client hay redirect URI, PKCE verifier sai, hoặc refresh token đã hết hạn, bị thu hồi hay bị thay thế sau rotation. Mỗi trường hợp có nguyên nhân khác nhau dù response OAuth có thể giống nhau.

Không chẩn đoán chỉ dựa vào HTTP status. Hãy đọc trường error trong response OAuth, đối chiếu request ID với log phía server và kiểm tra trạng thái authorization được lưu. invalid_grant thường được trả về từ token endpoint với HTTP 400, nhưng proxy hoặc gateway có thể thay đổi response. Luôn xác định request đã đến đúng Authorization Server và đúng endpoint trước khi kết luận.

## 1. Phân biệt ba lỗi

| Lỗi OAuth | Ý nghĩa | Lớp cần kiểm tra đầu tiên |
|---|---|---|
| invalid_client | Authorization Server không xác thực được client theo phương thức đã đăng ký | Client ID, secret hoặc credential, authentication method, RegisteredClientRepository |
| unauthorized_client | Client đã được nhận diện nhưng không được phép dùng grant type hoặc hành động được yêu cầu | AuthorizationGrantType và chính sách cấp quyền của client |
| invalid_grant | Authorization grant hoặc credential dùng để đổi token không hợp lệ, hết hạn, bị thu hồi, đã dùng hoặc không khớp ngữ cảnh | Authorization code, refresh token, redirect URI, PKCE, trạng thái lưu trữ |

Ví dụ:

- Client gửi sai client secret: thường là invalid_client.
- Client xác thực thành công nhưng không được đăng ký grant type client_credentials: unauthorized_client hoặc lỗi grant tương ứng theo provider và phiên bản.
- Client gửi authorization code đã hết hạn hoặc đã redeem: invalid_grant.

Một số lỗi khác có thể xuất hiện trong cùng luồng. invalid_request thường biểu thị thiếu hoặc sai tham số; unsupported_grant_type biểu thị server không hỗ trợ grant type được gửi; invalid_scope biểu thị scope yêu cầu không hợp lệ hoặc không được cấp cho client. Không đổi các lỗi này thành một trong ba lỗi trên chỉ để đơn giản hóa log hoặc response.

## 2. Thu thập bằng chứng an toàn trước khi sửa

Với mỗi lỗi, ghi lại metadata đủ để tái hiện và truy vết:

- Thời điểm UTC, request ID và trace ID do server sinh.
- Endpoint, HTTP method, grant_type và client authentication method dự kiến.
- Bí danh client hoặc mã tham chiếu nội bộ.
- HTTP status, OAuth error code và kết quả thành công/thất bại.
- Phiên bản ứng dụng, instance xử lý request và môi trường.
- Với authorization code hoặc refresh token, ghi nhận trạng thái như tồn tại, còn hiệu lực, đã tiêu thụ hoặc đã thu hồi; không ghi giá trị token.

Không ghi Authorization header, client secret, client assertion, authorization code, refresh token, access token, ID token, code_verifier, cookie hoặc toàn bộ request body. Không đưa các giá trị này vào exception message, MDC, trace attribute hay báo cáo CI. Nếu cần liên kết một authorization qua nhiều log, dùng request ID và mã tham chiếu giả danh được thiết kế riêng.

Đầu tiên xác nhận request đã đến token endpoint đúng của Authorization Server. Kiểm tra DNS, TLS, reverse proxy, path mapping và issuer nếu client gọi qua nhiều môi trường. Một response do API gateway tạo ra không chứng minh Spring Authorization Server đã trả invalid_grant. Nếu response là JSON OAuth, đọc error và đối chiếu request ID ở server.

## 3. Chẩn đoán authorization code hết hạn hoặc đã được dùng

Authorization code có thời hạn ngắn và chỉ được đổi một lần. Spring Authorization Server lưu code cùng authorization; provider kiểm tra code còn hiệu lực trước khi phát token. Nếu client gửi code quá hạn, code không tồn tại trong OAuth2AuthorizationService, hoặc code đã được đánh dấu invalidated sau lần đổi trước, token endpoint thường trả invalid_grant.

Kiểm tra TokenSettings.authorizationCodeTimeToLive để hiểu thời hạn code đang áp dụng. So sánh thời điểm phát hành với thời điểm token request đến theo UTC. Một client chậm xử lý callback, người dùng mở lại trang cũ hoặc mạng retry request có thể khiến code hết hạn hoặc đã được sử dụng. Không kéo dài thời hạn code chỉ để che lỗi callback; trước hết kiểm tra độ trễ và hành vi retry của client.

Các nguyên nhân thường gặp:

- Client đổi code sau khi authorization code đã hết hạn.
- Callback được xử lý hai lần do người dùng refresh trang hoặc ứng dụng retry POST.
- Một request đổi code thành công nhưng response bị mất; client gửi lại cùng code vì không biết lần đầu đã thành công.
- Code được phát hành ở node hoặc môi trường khác với nơi token request đang được xử lý.
- Dữ liệu authorization bị xóa, không được commit hoặc không được chia sẻ giữa các instance.

Test replay tuần tự phải chứng minh lần đầu thành công và lần thứ hai thất bại:

~~~java
@Test
void rejectsAuthorizationCodeReplay() throws Exception {
    String code = authorizeAndExtractCode(
            "browser-client", validRedirectUri, validChallenge, "S256");

    redeemCode(code, validVerifier)
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.access_token").exists());

    redeemCode(code, validVerifier)
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error").value("invalid_grant"))
            .andExpect(jsonPath("$.access_token").doesNotExist());
}
~~~

Mỗi lần chạy test cần tạo code mới. Không dùng cùng một code cho nhiều test âm tính vì kết quả có thể bị chi phối bởi việc test trước đã tiêu thụ code.

Replay đồng thời là trường hợp khác. Nếu hai request gửi cùng code gần như đồng thời, kho lưu trữ phải bảo đảm chỉ một request tiêu thụ code thành công. Với JDBC hoặc repository tùy chỉnh, kiểm thử bằng hai thread hoặc hai client HTTP độc lập, đồng bộ thời điểm gửi request và xác nhận chính xác một response thành công. Thao tác kiểm tra và đánh dấu code đã dùng phải có tính nguyên tử; kiểm tra trạng thái trong bộ nhớ rồi cập nhật sau có thể tạo race condition.

## 4. Chẩn đoán PKCE verifier sai hoặc không khớp

Với client bắt buộc PKCE, authorization request lưu code_challenge và code_challenge_method cùng authorization code. Khi đổi code, client phải gửi code_verifier tương ứng. Nếu verifier thiếu, sai, sai định dạng hoặc không tạo ra challenge đã lưu, server không được phát token và thường trả invalid_grant.

Với phương pháp S256, challenge được tính theo công thức BASE64URL-NOPAD(SHA256(ASCII(code_verifier))). Kiểm tra các điểm sau:

- Client có giữ đúng verifier được tạo trước khi chuyển người dùng đến authorization endpoint không.
- Callback có lấy verifier từ đúng phiên hoặc giao dịch bắt đầu authorization request không.
- Client có gửi code_verifier trong form body của token request không.
- Verifier có từ 43 đến 128 ký tự và chỉ dùng tập ký tự được RFC 7636 cho phép không.
- Challenge được tạo bằng SHA-256 và Base64 URL-safe không padding, không phải Base64 thông thường.
- code_challenge_method có đúng S256 như authorization request ban đầu không.

RFC 7636 test vector có thể dùng để xác minh hàm tính challenge:

~~~text
code_verifier:
dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

code_challenge_method:
S256

code_challenge:
E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

Hàm Java tương ứng:

~~~java
static String s256Challenge(String verifier) throws Exception {
    byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(verifier.getBytes(StandardCharsets.US_ASCII));
    return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);
}
~~~

Nếu áp dụng chính sách S256-only, từ chối code_challenge_method=plain và trường hợp bỏ method (RFC 7636 mặc định plain). Tuy nhiên, khi một authorization code đã được phát hành với challenge hợp lệ nhưng token request gửi verifier không khớp, lỗi cần được điều tra như invalid_grant. Không thay đổi chính sách PKCE hoặc tắt requireProofKey để làm request thành công.

Test âm tính cần tạo code mới với verifier hợp lệ, sau đó gửi một verifier khác có độ dài hợp lệ:

~~~java
redeemCode(code, "wrong-verifier-value-0123456789-ABCDEFGHIJKLM")
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error").value("invalid_grant"))
        .andExpect(jsonPath("$.access_token").doesNotExist());
~~~

Không ghi verifier, challenge hoặc authorization code vào log test. Chỉ ghi request ID, test case, endpoint và error code.

## 5. Kiểm tra client binding và redirect URI của authorization code

Authorization code được gắn với RegisteredClient đã khởi tạo authorization. Token request phải được xác thực bằng đúng client đó. Nếu code của browser-client được gửi cùng credential của một client khác, server phải từ chối đổi code. Kiểm tra client_id và client authentication method ở token request, sau đó đối chiếu client ID gắn trong authorization đã lưu. Không dùng RegisteredClient.id (khóa bản ghi nội bộ) thay cho client_id của giao thức.

redirect_uri cũng là một phần của giao dịch authorization. Nếu client gửi redirect_uri trong authorization request, token request phải gửi lại đúng URI đã dùng. So sánh phải giữ nguyên path, port, scheme và các thành phần có ý nghĩa; không tự chuẩn hóa hai URI khác nhau thành một. Không sửa cấu hình redirect URI thành wildcard để chữa invalid_grant.

Một test tiêu biểu cho redirect URI không khớp:

~~~java
@Test
void rejectsAuthorizationCodeWithDifferentRedirectUri() throws Exception {
    // authorizeAndExtractCode tạo code với redirect URI đã đăng ký.
    String code = authorizeAndExtractCode(
            "browser-client",
            "https://client.example/callback",
            validChallenge,
            "S256");

    mockMvc.perform(post("/oauth2/token")
                    .with(httpBasic("browser-client", "test-secret"))
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("grant_type", "authorization_code")
                    .param("code", code)
                    .param("redirect_uri", "https://attacker.example/callback")
                    .param("code_verifier", validVerifier))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error").value("invalid_grant"))
            .andExpect(jsonPath("$.access_token").doesNotExist());
}
~~~

Helper trong ví dụ cần hoàn tất đăng nhập và consent như ứng dụng yêu cầu. Mỗi test phải tạo code riêng để không nhầm lỗi redirect URI với lỗi code đã được redeem.

## 6. Chẩn đoán invalid_grant cho refresh token

Refresh token có thể bị từ chối khi không tồn tại, hết hạn, bị thu hồi, thuộc client khác, đã bị thay thế hoặc không thỏa mãn chính sách rotation. Kiểm tra các điểm sau:

- Client gửi refresh token có đúng client đã nhận token ban đầu không.
- Token còn hiệu lực và authorization chưa bị thu hồi không.
- Refresh token có hết hạn theo TokenSettings.refreshTokenTimeToLive không.
- Nếu cấu hình reuseRefreshTokens(false), client có lưu và dùng refresh token mới sau mỗi lần refresh không.
- Một request đồng thời hoặc request retry có đang dùng lại refresh token cũ sau khi rotation thành công không.
- Server có nhiều instance dùng chung OAuth2AuthorizationService và cập nhật trạng thái nhất quán không.

Khi bật rotation, response refresh thành công có thể chứa refresh token mới. Client phải thay thế token cũ một cách nguyên tử trong kho lưu trữ của nó. Nếu ứng dụng lưu token mới thất bại nhưng vẫn gửi lại token cũ, lần tiếp theo có thể nhận invalid_grant. Kiểm tra retry policy và thứ tự ghi dữ liệu phía client.

Đừng giả định mọi refresh token đều được rotate mặc định. Hành vi phụ thuộc TokenSettings và cấu hình phiên bản. Hãy kiểm tra giá trị reuseRefreshTokens và viết test tương ứng với chính sách đang triển khai. Ví dụ cấu hình rotation:

~~~java
TokenSettings tokenSettings = TokenSettings.builder()
        .reuseRefreshTokens(false)
        .refreshTokenTimeToLive(Duration.ofDays(30))
        .build();
~~~

Sau khi refresh thành công, client phải lưu refresh token mới trước khi xóa token cũ. Bài test cần xác nhận token mới dùng được và token cũ không thể dùng lại:

~~~java
RefreshTokenResponse rotated = refresh(initialRefreshToken);

refresh(rotated.refreshToken())
        .andExpect(status().isOk());

refresh(initialRefreshToken)
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error").value("invalid_grant"));
~~~

RefreshTokenResponse và helper refresh trong ví dụ là fixture của test, không phải kiểu dữ liệu có sẵn của Spring Authorization Server. Hãy ánh xạ response JSON của token endpoint vào helper tương ứng với test harness của dự án.

## 7. Kiểm tra dữ liệu lưu trữ và nhiều instance

Spring Authorization Server dùng RegisteredClientRepository để tra client và OAuth2AuthorizationService để lưu authorization cùng token state. Nếu một node phát hành code nhưng node khác không tìm thấy code, kiểm tra hai node có dùng cùng database, schema, tenant, serializer và cấu hình repository không.

Với JDBC hoặc repository tùy chỉnh, kiểm tra transaction commit, cập nhật trạng thái token, thời gian hết hạn và việc đánh dấu code đã invalidated. Khi nhiều request đồng thời redeem cùng code hoặc refresh cùng token, thao tác tiêu thụ cần có tính nguyên tử. Một mô hình chỉ đọc trạng thái, kiểm tra rồi ghi lại mà không khóa hoặc kiểm soát cạnh tranh có thể cho phép hai request cùng vượt qua bước kiểm tra.

Kiểm tra thời gian hệ thống trên các node bằng NTP. Sai lệch đồng hồ có thể làm token bị xem là chưa có hiệu lực hoặc đã hết hạn. So sánh thời điểm phát hành và thời điểm kiểm tra theo UTC; không suy luận từ múi giờ hiển thị của log.

## 8. Dùng log và breakpoint đúng chỗ

Để định vị lỗi, theo dõi các điểm xử lý theo thứ tự:

- Client authentication filter/provider: xác định client và xác thực phương thức credential.
- Token endpoint filter/converter: đọc grant_type và chuyển request thành authentication tương ứng.
- Grant authentication provider: kiểm tra authorization code, refresh token, scope và điều kiện grant.
- RegisteredClientRepository: tra cấu hình client và grant type.
- OAuth2AuthorizationService: tìm authorization, đọc token state và lưu thay đổi.
- OAuth2TokenGenerator: chỉ quan sát kết quả và loại token, không in giá trị token.

Có thể tăng mức log cho package liên quan trong môi trường test ngắn hạn, nhưng không bật TRACE rộng trong production khi chưa kiểm tra dữ liệu được phát ra. Ưu tiên log event name, client alias, grant type, request ID và OAuth error code. Nếu dùng debugger, không mở hoặc copy secret, code, token, verifier hay toàn bộ OAuth2Authorization vào ảnh chụp hoặc báo cáo.

Không trả exception nội bộ, SQL, tên bảng, stack trace hoặc chi tiết secret encoder cho client. Client-facing error_description nên ngắn và không tiết lộ việc một client cụ thể có tồn tại hay không. Thông tin chi tiết dành cho log nội bộ có kiểm soát truy cập.

## 9. Bảng quyết định xử lý nhanh

| Quan sát | Khả năng cao | Việc kiểm tra tiếp theo |
|---|---|---|
| Code hợp lệ trước đó nhưng request đến muộn | Authorization code đã hết hạn | TokenSettings.authorizationCodeTimeToLive, callback latency và clock UTC |
| Code đổi lần đầu thành công, lần hai thất bại | Hành vi dùng một lần bình thường | Kiểm tra retry hoặc callback bị xử lý hai lần |
| Code mới vẫn invalid_grant | Client binding, redirect URI hoặc PKCE không khớp | Đối chiếu dữ liệu authorization và tham số token request |
| Verifier đúng theo client nhưng server từ chối | Sai verifier được lưu, sai phiên hoặc tính challenge sai | Kiểm tra luồng tạo/lưu verifier và S256 test vector |
| Refresh token đột nhiên invalid_grant sau refresh | Token rotation hoặc revoke | Kiểm tra reuseRefreshTokens, lưu token mới và retry |
| Chỉ một node trả invalid_grant | Storage, cache hoặc cấu hình giữa node không đồng nhất | So sánh repository, database, serializer và clock |
| HTTP 400 nhưng không có OAuth error JSON | Gateway hoặc proxy đã tạo response | Kiểm tra response headers, access log và request ID ở từng lớp |

## 10. Checklist trước khi kết luận sự cố

- [ ] Đã xác nhận request đến đúng token endpoint và response chứa OAuth error code nào.
- [ ] Đã xác nhận client authentication thành công trước khi điều tra authorization grant.
- [ ] Authorization code hoặc refresh token còn hiệu lực, chưa bị dùng hoặc thu hồi ngoài dự kiến.
- [ ] Redirect URI, client binding và PKCE verifier khớp với authorization ban đầu.
- [ ] Token rotation, retry và cập nhật trạng thái phía client đã được kiểm tra.
- [ ] Các instance dùng chung repository và có thời gian hệ thống đồng bộ.
- [ ] Log không chứa secret, authorization code, token, verifier hoặc dữ liệu cá nhân.

Nếu response thực tế là invalid_client hoặc unauthorized_client, quay lại kiểm tra client authentication hoặc quyền grant trước khi phân tích grant. Khi error là invalid_grant, tập trung vào vòng đời và ngữ cảnh của authorization. Giữ nguyên các kiểm tra bảo mật trong lúc khắc phục giúp lỗi được xử lý tận gốc mà không làm suy yếu luồng OAuth 2.0/OIDC.
