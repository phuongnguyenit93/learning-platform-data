# Kiểm thử PKCE thiếu, sai verifier, downgrade và code replay

PKCE (Proof Key for Code Exchange) bổ sung một bí mật ngẫu nhiên do client tạo vào authorization code flow. Client gửi bản băm của bí mật trong authorization request, sau đó gửi bí mật gốc khi đổi authorization code lấy token. Authorization Server chỉ cấp token nếu hai giá trị khớp nhau. Cơ chế này giảm nguy cơ kẻ tấn công lấy được authorization code rồi tự đổi code đó thành token.

Một cấu hình có bật PKCE vẫn cần được kiểm thử bằng các trường hợp thất bại. Cần chứng minh server từ chối authorization request thiếu challenge, từ chối verifier không hợp lệ, áp dụng chính sách chống hạ cấp thuật toán và chỉ cho phép sử dụng authorization code một lần. Các bài kiểm thử phải chạy qua endpoint thực của Spring Authorization Server để bao gồm cả filter, client authentication, lưu trữ authorization và xử lý lỗi.

## 1. Các bất biến bảo mật cần kiểm tra

Với authorization code flow, mỗi lần cấp code cần thỏa mãn các điều kiện sau:

1. Client thuộc nhóm bắt buộc PKCE phải gửi code_challenge trong authorization request.
2. Server chỉ chấp nhận code_challenge_method nằm trong chính sách đã công bố. Với hệ thống mới, nên yêu cầu S256 và từ chối plain.
3. Token request phải có code_verifier hợp lệ và giá trị này phải tạo ra đúng challenge đã gắn với authorization code.
4. Authorization code phải còn hiệu lực, chưa được sử dụng, thuộc đúng client và khớp redirect_uri ban đầu.
5. Chỉ một lần đổi code được phép thành công, kể cả khi hai request đổi cùng code đến gần như đồng thời.

Các điều kiện này liên quan với nhau nhưng kiểm tra những lỗi khác nhau. Ví dụ, kiểm tra requireProofKey chỉ chứng minh client phải dùng PKCE; nó không tự chứng minh server chỉ cho phép thuật toán S256. Tương tự, kiểm tra verifier đúng không chứng minh code đã được tiêu thụ theo cách an toàn trước các request replay đồng thời.

## 2. Hiểu đúng challenge và verifier

Client tạo một chuỗi code_verifier ngẫu nhiên có độ dài từ 43 đến 128 ký tự, dùng các ký tự không dành riêng theo RFC 3986: chữ cái, chữ số, dấu gạch ngang, dấu chấm, dấu gạch dưới và dấu ngã. Client tạo challenge theo một trong hai phương pháp:

| Phương pháp | Công thức | Chính sách khuyến nghị |
|---|---|---|
| S256 | BASE64URL-NOPAD(SHA256(ASCII(code_verifier))) | Chấp nhận |
| plain | code_challenge = code_verifier | Từ chối trong chính sách S256-only |

Với S256, server lưu challenge và phương pháp cùng authorization code. Khi token request đến, server tính lại challenge từ verifier nhận được rồi so sánh với challenge đã lưu. So sánh phải được thực hiện bằng logic an toàn cho dữ liệu xác thực; không log verifier hoặc challenge nếu chúng có thể được dùng để tái tạo luồng kiểm thử hay làm lộ thông tin client.

RFC 7636 có test vector hữu ích để kiểm tra hàm tính challenge:

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
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;

static String s256Challenge(String verifier) {
    try {
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(verifier.getBytes(StandardCharsets.US_ASCII));
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
    } catch (NoSuchAlgorithmException ex) {
        throw new IllegalStateException("SHA-256 is unavailable", ex);
    }
}
~~~

Hãy có một unit test riêng xác nhận hàm trên tạo đúng challenge của test vector. Unit test này bắt lỗi sai charset, dùng Base64 thông thường thay vì Base64 URL-safe, giữ padding hoặc băm nhầm dữ liệu. Nó chưa thay thế integration test với Authorization Server.

~~~java
assertThat(s256Challenge(
        "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"))
        .isEqualTo("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM");
~~~

## 3. Cấu hình client kiểm thử trong Spring Authorization Server

Tạo một client chuyên dùng cho các bài kiểm thử authorization code và bật yêu cầu PKCE trong ClientSettings:

~~~java
RegisteredClient pkceClient = RegisteredClient.withId("pkce-client-row")
        .clientId("pkce-client")
        .clientSecret(passwordEncoder.encode("test-secret"))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://client.example/callback")
        .scope("profile.read")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .build())
        .build();

registeredClientRepository.save(pkceClient);
~~~

Client này dùng client_secret_basic để bài kiểm thử tập trung vào PKCE. Khi kiểm thử public client, đăng ký một client riêng với phương thức xác thực none và không cấu hình secret. Không trộn lỗi client authentication với lỗi PKCE: trước khi đánh giá kết quả PKCE, bảo đảm request đã xác thực client thành công theo đúng loại client.

requireProofKey(true) thể hiện rằng client bắt buộc dùng PKCE. Cần bổ sung chính sách ở bước xác thực authorization request để chỉ chấp nhận S256 nếu đó là yêu cầu của hệ thống. Không giả định rằng bật requireProofKey đồng nghĩa với việc mọi phiên bản Spring Authorization Server đều tự động từ chối plain. Hãy kiểm tra hành vi của phiên bản đang dùng và kiểm thử nó qua HTTP.

Phần kiểm tra thuật toán trong custom validator có thể diễn đạt như sau:

~~~java
// Pseudocode: đặt tại validator xử lý authorization request
// sau khi xác định client này thuộc nhóm bắt buộc PKCE.
if (!"S256".equals(codeChallengeMethod)) {
    rejectAuthorizationRequest("invalid_request");
}
~~~

Đây là logic chính sách, không phải tên một API Spring cụ thể. Hãy gắn logic vào extension point validator mà phiên bản Spring Authorization Server của dự án hỗ trợ. Nếu code_challenge_method bị bỏ trống, RFC 7636 mặc định phương pháp là plain; do đó chính sách S256-only cũng phải từ chối trường hợp không gửi method.

## 4. Thiết lập integration test qua endpoint thật

Dùng MockMvc với filter chain của ứng dụng, repository client và authorization service giống cấu hình tích hợp. Mỗi test nên tạo authorization code mới để kết quả không phụ thuộc vào test trước. Helper authorizeAndExtractCode trong ví dụ đại diện cho bước gửi authorization request với người dùng đã đăng nhập, hoàn tất consent nếu ứng dụng yêu cầu và trích code từ redirect URI. Cách này giúp các test bên dưới tập trung vào hành vi PKCE.

Ví dụ helper đổi code:

~~~java
private ResultActions redeemCode(String code, String verifier) throws Exception {
    MockHttpServletRequestBuilder request = post("/oauth2/token")
            .with(httpBasic("pkce-client", "test-secret"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("grant_type", "authorization_code")
            .param("code", code)
            .param("redirect_uri", "https://client.example/callback");

    if (verifier != null) {
        request.param("code_verifier", verifier);
    }

    return mockMvc.perform(request);
}
~~~

Các import thường dùng gồm MockMvc, MockHttpServletRequestBuilder, MediaType, get, post, httpBasic, user, status và jsonPath từ Spring Test/Spring Security Test. Cấu hình test phải nạp filter chain Authorization Server và xác thực người dùng. Nếu ứng dụng yêu cầu consent, chuẩn bị consent trong fixture hoặc hoàn tất màn hình consent trong helper.

## 5. Kiểm thử thiếu challenge và method không được hỗ trợ

Với client có requireProofKey(true), gửi authorization request không có code_challenge. Server phải từ chối request và không phát hành authorization code:

~~~java
@Test
void rejectsAuthorizationRequestWithoutChallenge() throws Exception {
    mockMvc.perform(get("/oauth2/authorize")
                    .with(user("alice"))
                    .param("response_type", "code")
                    .param("client_id", "pkce-client")
                    .param("redirect_uri", "https://client.example/callback")
                    .param("scope", "profile.read")
                    .param("state", "state-missing-challenge"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern(
                    "https://client.example/callback?error=invalid_request*"));
}
~~~

Authorization endpoint thường trả lỗi OAuth bằng redirect đến URI đã đăng ký, vì vậy không nên mặc định rằng mọi lỗi ở endpoint này đều là HTTP 400. Hãy kiểm tra error=invalid_request, bảo đảm không có code trong redirect và xác nhận authorization service không lưu một authorization code hợp lệ cho request bị từ chối.

Tiếp theo, gửi một code_challenge_method không được hỗ trợ, chẳng hạn S512, cùng challenge có hình thức hợp lệ. Server phải từ chối authorization request với invalid_request. Test này bảo đảm server không âm thầm diễn giải một thuật toán lạ thành plain hoặc một phương pháp khác.

## 6. Kiểm thử verifier thiếu, sai và sai định dạng

Trước tiên, tạo code hợp lệ với challenge S256 từ verifier đã biết:

~~~java
String verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
String challenge = s256Challenge(verifier);
String code = authorizeAndExtractCode(
        "pkce-client", challenge, "S256");
~~~

Với client authentication hợp lệ và authorization code còn hiệu lực, bỏ code_verifier khỏi token request. Server phải từ chối đổi code và trả invalid_grant theo cách xử lý lỗi của token endpoint:

~~~java
redeemCode(code, null)
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error").value("invalid_grant"));
~~~

Tạo một authorization code mới cho test verifier sai. Không tái sử dụng code đã dùng trong test thiếu verifier:

~~~java
String verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
String code = authorizeAndExtractCode(
        "pkce-client", s256Challenge(verifier), "S256");

redeemCode(code, "wrong-verifier-value-0123456789-ABCDEFGHIJKLM")
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error").value("invalid_grant"))
        .andExpect(jsonPath("$.access_token").doesNotExist());
~~~

Ngoài verifier không khớp, kiểm thử chuỗi ngắn hơn 43 ký tự, dài hơn 128 ký tự và chứa ký tự ngoài tập cho phép. Server không được phát token từ verifier sai định dạng. Chuẩn hóa kết quả thành lỗi OAuth phù hợp với phiên bản server; với authorization code không thể xác minh, kết quả mong đợi là invalid_grant. Không để exception nội bộ hoặc stack trace xuất hiện trong response.

Một lần thử verifier sai không được làm phát sinh access token, refresh token hoặc ID token. Kiểm tra cả response lẫn trạng thái authorization đã lưu. Nếu hệ thống chọn chính sách thu hồi code ngay khi có lần xác minh PKCE thất bại, hãy kiểm thử rõ chính sách đó; đừng mặc định hành vi này nếu ứng dụng chưa quy định.

## 7. Kiểm thử downgrade từ S256 xuống plain

Downgrade xảy ra khi một request có thể bị thay đổi để dùng phương pháp yếu hơn. Với plain, challenge chính là verifier, vì vậy giá trị cần bảo vệ không còn được băm trước khi đi qua authorization request. Đối với client yêu cầu PKCE, hệ thống áp dụng chính sách S256-only nên từ chối cả hai dạng:

- code_challenge_method=plain.
- Không gửi code_challenge_method, vì RFC 7636 mặc định trường hợp này là plain.

Ví dụ test:

~~~java
@Test
void rejectsPlainChallengeMethod() throws Exception {
    mockMvc.perform(get("/oauth2/authorize")
                    .with(user("alice"))
                    .param("response_type", "code")
                    .param("client_id", "pkce-client")
                    .param("redirect_uri", "https://client.example/callback")
                    .param("scope", "profile.read")
                    .param("state", "state-plain")
                    .param("code_challenge", "plain-verifier-value-0123456789-ABCDEFGHIJKLM")
                    .param("code_challenge_method", "plain"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern(
                    "https://client.example/callback?error=invalid_request*"));
}
~~~

Tạo thêm test bỏ hẳn code_challenge_method nhưng vẫn gửi code_challenge; kết quả cũng phải là invalid_request theo chính sách S256-only. Không chỉ kiểm tra client có gửi S256 trong happy path. Phải chứng minh server từ chối downgrade ở phía server, kể cả khi client gửi request không tuân thủ chính sách.

Nếu sản phẩm có client cũ cần plain, hãy định nghĩa ngoại lệ theo client, có chủ sở hữu và thời hạn loại bỏ. Không tự động cho phép plain cho mọi client chỉ để tương thích. Ghi nhận chính sách này trong cấu hình client và tạo test riêng cho từng nhóm.

## 8. Kiểm thử authorization code replay

Authorization code là credential dùng một lần. Sau khi đổi code thành công, gửi lại chính code đó với verifier đúng phải thất bại. Không cấp token mới, không tạo refresh token mới và không trả lại token response cũ:

~~~java
@Test
void rejectsAuthorizationCodeReplay() throws Exception {
    String verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
    String code = authorizeAndExtractCode(
            "pkce-client", s256Challenge(verifier), "S256");

    redeemCode(code, verifier)
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.access_token").exists());

    redeemCode(code, verifier)
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error").value("invalid_grant"))
            .andExpect(jsonPath("$.access_token").doesNotExist());
}
~~~

Bài test trên kiểm tra replay tuần tự. Nó chưa phát hiện được race condition khi hai request cùng đọc trạng thái code còn hiệu lực trước khi một request kịp lưu trạng thái đã tiêu thụ. Vì vậy, nếu authorization service dùng JDBC hoặc kho lưu trữ tùy chỉnh, cần có integration test đồng thời với hai request token đến từ hai thread hoặc hai client HTTP độc lập:

1. Tạo một authorization code hợp lệ và chỉ dùng một verifier đúng.
2. Đồng bộ hai request để chúng gửi cùng code gần như đồng thời.
3. Đợi cả hai response hoàn tất.
4. Xác nhận chính xác một response thành công và response còn lại nhận invalid_grant.
5. Xác nhận chỉ một lần phát hành token được ghi nhận trong trạng thái lưu trữ.

Để đạt điều kiện này, thao tác tiêu thụ authorization code phải có tính nguyên tử trong kho lưu trữ. Có thể cần transaction cùng khóa bản ghi, optimistic version hoặc thao tác cập nhật có điều kiện chỉ thành công khi code vẫn chưa bị tiêu thụ. Chỉ dựa vào kiểm tra trạng thái trong bộ nhớ rồi lưu sau đó có thể để lọt hai request đồng thời. Hãy kiểm tra hành vi thực tế của implementation đang triển khai, đặc biệt khi chạy nhiều instance Authorization Server.

## 9. Ma trận test và kết quả mong đợi

| Trường hợp | Điểm kiểm tra | Kết quả mong đợi |
|---|---|---|
| Thiếu code_challenge với client bắt buộc PKCE | Authorization endpoint | invalid_request, không phát hành code |
| Method không được hỗ trợ | Authorization endpoint | invalid_request, không fallback |
| plain với chính sách S256-only | Authorization endpoint | invalid_request |
| Bỏ code_challenge_method trong chính sách S256-only | Authorization endpoint | invalid_request |
| Thiếu code_verifier | Token endpoint | invalid_grant, không phát token |
| Verifier không khớp challenge | Token endpoint | invalid_grant, không phát token |
| Verifier sai độ dài hoặc ký tự | Token endpoint | Request bị từ chối, không phát token |
| Dùng code lần thứ hai | Token endpoint | invalid_grant, không phát token mới |
| Hai request đổi cùng code đồng thời | Token endpoint và authorization store | Chính xác một request thành công |

Trong mọi test token endpoint, xác thực client thành công trước để tránh invalid_client che mất lỗi PKCE. Với lỗi authorization endpoint, kiểm tra redirect URI đã đăng ký và tham số OAuth error; với lỗi token endpoint, kiểm tra HTTP status, mã lỗi JSON và trạng thái token.

## 10. Giữ test độc lập và tránh false positive

Mỗi tình huống phải dùng authorization code riêng, state riêng và verifier riêng. Không dùng một code đã đổi thành công cho bài test verifier sai hoặc thiếu verifier. Không chỉ assert status code: cần kiểm tra mã lỗi, không có token trong response và trạng thái authorization sau request.

Test nên chạy với cùng loại authorization service mà production dùng. Nếu production lưu authorization trong JDBC, test H2 hoặc in-memory có thể bỏ sót vấn đề transaction và cạnh tranh. Với test replay đồng thời, dùng database tương thích production và tạo transaction ở các thread độc lập. Chạy test trên một instance giúp xác minh logic cơ bản; chạy nhiều instance hoặc nhiều worker giúp phát hiện lỗi khi trạng thái code được chia sẻ.

Dùng client secret, verifier và authorization code giả lập. Không ghi các giá trị này vào test report, log CI hoặc assertion message. Nếu test thất bại, chỉ in request ID, tên test case, endpoint, status và mã lỗi đã chuẩn hóa.

## 11. Checklist trước khi phát hành

- [ ] Mọi client thuộc chính sách bắt buộc PKCE đều từ chối authorization request thiếu challenge.
- [ ] Test vector S256 xác nhận chính xác SHA-256 và Base64 URL-safe không padding.
- [ ] Server chỉ chấp nhận S256 với các client thuộc chính sách S256-only.
- [ ] plain và trường hợp bỏ method đều bị từ chối theo chính sách.
- [ ] Verifier thiếu, sai, quá ngắn, quá dài hoặc chứa ký tự không hợp lệ không thể đổi code lấy token.
- [ ] Authorization code đã dùng không thể đổi lần nữa.
- [ ] Test đồng thời chứng minh chỉ một request có thể tiêu thụ cùng authorization code.
- [ ] Các test chạy với authorization service và kho lưu trữ tương ứng production.
- [ ] Response lỗi không chứa access token, refresh token, ID token hoặc thông tin nội bộ.

Khi các bài kiểm thử này chạy ổn định trong CI, nhóm phát triển có thể phát hiện sớm việc cấu hình PKCE bị nới lỏng, thuật toán bị hạ cấp hoặc authorization code bị sử dụng lại trước khi thay đổi được đưa lên môi trường production.
