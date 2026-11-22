# JWT là định dạng token, không phải toàn bộ giao thức đăng nhập

## 1. Hiểu đúng vấn đề: JWT trả lời câu hỏi về dữ liệu, không trả lời toàn bộ câu hỏi đăng nhập

Khi phát triển Spring Security, nhiều tài liệu minh họa thao tác đăng nhập như sau: client gửi username/password, server trả một chuỗi có ba phần ngăn cách bằng dấu chấm, client giữ chuỗi đó để gửi trong header Authorization. Chuỗi ấy thường là **JWT (JSON Web Token)**. Từ đó, rất dễ kết luận sai rằng **JWT chính là giao thức đăng nhập**.

Thực tế, **JWT là một định dạng biểu diễn các claim** (các phát biểu về danh tính, quyền, thời gian hoặc ngữ cảnh) ở dạng gọn, phù hợp vận chuyển giữa các bên. JWT có thể được bảo vệ tính toàn vẹn bằng **JWS** hoặc mã hóa bằng **JWE**. Việc chọn JWT không tự quy định người dùng được xác thực như thế nào, ai cấp token, client nào được nhận token, token có thời hạn bao lâu, API nào được sử dụng, cách gia hạn, thu hồi và đăng xuất.

Một hệ thống an toàn cần phân biệt ít nhất bốn câu hỏi:

1. **Authentication:** Người dùng/client chứng minh danh tính bằng phương pháp nào? Password, passkey, MFA, session, client certificate, OAuth/OIDC redirect?
2. **Token issuance:** Bên nào được tin cậy để phát hành credential và có quyền ký/mã hóa token?
3. **Token presentation và validation:** Client trình credential qua đâu? Server kiểm tra chữ ký, người phát hành, người nhận, thời hạn, mục đích sử dụng, quyền như thế nào?
4. **Authorization và lifecycle:** Principal đã xác thực được làm gì, credential bị thu hồi hoặc hết hạn ra sao, khi nào yêu cầu đăng nhập lại?

**JWT không tự hoàn thành bốn bước đó.** JWT có thể xuất hiện trong một giao thức như OpenID Connect, được dùng làm access token của một triển khai OAuth 2.0, làm token nội bộ hoặc không được dùng trong hệ thống đăng nhập nào cả.

### Mục tiêu học tập

Sau bài này, bạn có thể:
- Đọc cấu trúc JWT, hiểu JWS/JWE và phân biệt mã hóa Base64url với bảo mật.
- Giải thích vai trò của **OAuth 2.0**, **OpenID Connect (OIDC)**, **Authorization Server**, **Resource Server** và JWT.
- Phân biệt **ID token, access token, refresh token và session cookie**; không sử dụng sai mục đích.
- Biết các điều kiện cần xác minh JWT trước khi coi request là authenticated.
- Cấu hình Spring Boot 3.x / Spring Security 6.x làm **JWT Resource Server** dựa trên issuer đáng tin cậy.
- Chạy chương trình Java 17+ minh họa chữ ký và hiện tượng sửa payload làm chữ ký mất hiệu lực.
- Nhận biết sai lầm như tin payload sau khi Base64 decode, bỏ qua audience hoặc dùng ID token thay access token.

Phạm vi bài: tập trung kiến thức nền tảng **token và giao thức**; không tự triển khai Authorization Server hay một giao thức đăng nhập hoàn chỉnh từ đầu.

## 2. Phân biệt bốn khái niệm thường bị gộp lại

| Khái niệm | Bản chất | Ví dụ | Không đồng nghĩa với |
| --- | --- | --- | --- |
| **JWT** | Định dạng truyền claims theo RFC 7519 | Một JWS compact có ba phần | Đăng nhập, OAuth 2.0, OIDC hoặc phân quyền |
| **OAuth 2.0** | Framework ủy quyền, quy định vai trò/luồng lấy và dùng access token | Authorization Code + PKCE | Bắt buộc dùng JWT hoặc tự cung cấp chứng nhận danh tính user cho client |
| **OpenID Connect (OIDC)** | Lớp **xác thực danh tính** xây trên OAuth 2.0 | OIDC login nhận ID token | Mọi access token đều là ID token |
| **HTTP session** | Trạng thái phía server có thể tồn tại qua nhiều request | HttpSession gắn với cookie JSESSIONID | JWT hay token do authorization server ký |
| **Bearer access token** | Credential: người cầm token hợp lệ có thể xuất trình để truy cập tài nguyên trong phạm vi cho phép | Authorization: Bearer ... | Luôn ở dạng JWT; Bearer token có thể opaque |
| **Spring SecurityContext** | Ngữ cảnh chứa Authentication phục vụ xử lý và authorization | SecurityContextHolder trong request | Tự động là một JWT hoặc một HttpSession |

Điểm quan trọng: **OAuth 2.0 có thể dùng opaque access token**, không chỉ JWT. Một ứng dụng **không dùng OAuth/OIDC** vẫn có thể tự phát hành JWT theo giao thức riêng, nhưng khi ấy developer phải tự thiết kế rất nhiều chi tiết quan trọng về bảo mật, vận hành và vòng đời credential. Với nhu cầu đăng nhập phổ biến, nên ưu tiên các giao thức và thành phần tiêu chuẩn đã được kiểm chứng.

### Hai hệ thống đều dùng JWT nhưng có thể khác hoàn toàn

**Hệ thống A:** SPA chuyển hướng người dùng tới Identity Provider dùng OIDC Authorization Code + PKCE. Authorization Server thực hiện xác thực, trả authorization code, client đổi code lấy token theo giao thức. API sử dụng access token JWT đã được xác minh.

**Hệ thống B:** Client POST /api/login với JSON username/password đến backend riêng. Backend tự kiểm tra password rồi tự ký JWT và trả lại. Không có OAuth Authorization Code, không có OIDC discovery, không có ID token hay bên Identity Provider độc lập.

**Cả A và B có thể trả JWT**, nhưng trình tự, giao thức, trust boundary, cơ chế chống tấn công, quyền hạn và trách nhiệm kỹ thuật rất khác nhau. Nhìn thấy ba đoạn Base64url không thể suy ra A hoặc B.

## 3. JWT thực sự có cấu trúc gì?

Theo RFC 7519, JWT chứa tập hợp claims được đóng gói trong cấu trúc **JWS** (JSON Web Signature) hoặc **JWE** (JSON Web Encryption). Trường hợp thông dụng nhất ở các REST API là **JWS compact serialization** gồm ba phần:

~~~text
BASE64URL(Protected Header) . BASE64URL(Payload) . BASE64URL(Signature)
          phần 1                  phần 2                  phần 3
~~~

Một token thực có các phần là các chuỗi ký tự Base64url. Dấu chấm phân tách các phần. Để minh họa hình dạng mà không đưa ra chữ ký giả có thể bị hiểu nhầm là token hợp lệ:

~~~text
<encoded-header>.<encoded-payload>.<encoded-signature>
~~~

Dòng trên là **sơ đồ**, không phải credential dùng được. JWT JWS compact thường có ba phần; JWE compact có **năm phần** với cấu trúc mã hóa khác. Không khẳng định mọi JWT đều có ba phần; cũng cần nhận biết những dạng serialization khác của JOSE.

### 3.1. Header

Header mô tả thông tin xử lý mật mã, ví dụ:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "signing-key-2026"
}
~~~

- **alg**: thuật toán bảo vệ tính toàn vẹn/chữ ký; ví dụ RS256, ES256 hoặc HS256 tùy hệ thống.
- **typ**: loại đối tượng; có thể giúp phân biệt loại JWT trong profile có quy định kiểu cụ thể.
- **kid**: gợi ý key ID để bên xác minh chọn public key tương ứng trong một **bộ khóa tin cậy đã cấu hình**.

**Header là dữ liệu do bên gửi cung cấp, không phải danh sách mệnh lệnh đáng tin.** Resource Server phải có chính sách algorithm/key rõ ràng, không tự động chấp nhận thuật toán nào mà header yêu cầu, không coi bất kỳ URL được đưa trong header làm nguồn tải khóa đáng tin cậy.

### 3.2. Payload và claim

Ví dụ claims của một access token theo profile riêng:

~~~json
{
  "iss": "https://idp.example.org/realms/training",
  "sub": "user-123",
  "aud": "reports-api",
  "iat": 1793800000,
  "nbf": 1793800000,
  "exp": 1793800900,
  "scope": "reports.read reports.write"
}
~~~

Các số thời gian chỉ **minh họa Unix timestamp**, không phải token đang còn hạn ở thời điểm bạn đọc. Trường scope ở trên đại diện một quy ước cấp quyền của hệ thống; **scope** không phải registered claim bắt buộc của mọi JWT.

| Claim | Ý nghĩa điển hình | Kiểm tra cần quan tâm |
| --- | --- | --- |
| **iss** | Issuer: bên phát hành | Phải khớp **issuer mà hệ thống tin cậy** theo đúng định danh |
| **sub** | Subject: danh tính chủ thể | Phải được diễn giải trong ngữ cảnh issuer; không tùy tiện coi là email duy nhất toàn hệ thống |
| **aud** | Audience: bên nhận dự kiến | Phải chứa API/client nhận token đúng với mục đích; không chấp nhận token phát cho hệ thống khác |
| **exp** | Thời điểm token hết hạn | Từ chối token quá hạn theo quy tắc thời gian và clock skew hợp lý |
| **nbf** | Not before: trước thời điểm này không sử dụng | Từ chối token chưa có hiệu lực |
| **iat** | Issued at: thời điểm phát hành | Có thể dùng để áp dụng chính sách token age nếu profile yêu cầu |
| **jti** | JWT ID | Có thể phục vụ chống replay hoặc danh sách thu hồi nếu hệ thống thiết kế cơ chế liên quan |
| **scope / scp** | Scope được cấp theo profile OAuth/token issuer | Ánh xạ đúng thành authority và chỉ cho phép thao tác thuộc scope |
| **roles / permissions** | Quyền nghiệp vụ tự định nghĩa | Không tự được Spring Security hiểu thành GrantedAuthority nếu không có converter phù hợp |

Không phải mọi claim trên đều bắt buộc theo định dạng JWT; **profile giao thức và policy của từng ứng dụng** mới quyết định claim nào phải có và cách kiểm tra. Ví dụ **exp không được tự động sinh chỉ vì payload là JSON**.

### 3.3. Base64url không phải mã hóa bí mật

Trong JWS thông thường, header và payload chỉ được **mã hóa để vận chuyển**, không được che giấu. Bất kỳ ai có token đều có thể decode hai phần đầu và đọc claims; không cần private key.

Vì vậy:
- **Không đặt mật khẩu, OTP, private key, secret, dữ liệu cá nhân không cần thiết** trong JWS payload.
- Không coi việc người dùng không biết cách Base64url decode là một hàng rào bảo mật.
- **Không lấy việc decode thành công làm bằng chứng token hợp lệ.** Chuỗi giả mạo cũng có thể là JSON đọc được.
- Chữ ký đúng bảo đảm **tính toàn vẹn/xác thực nguồn ký** theo key và thuật toán được phép, **không bảo đảm confidentiality**.
- Nếu cần bảo mật nội dung token trong đường truyền/lưu trữ, hãy cân nhắc JWE hoặc không đưa dữ liệu nhạy cảm vào token, đồng thời vẫn sử dụng TLS.

### 3.4. JWS và JWE khác nhau

| Đặc điểm | JWS | JWE |
| --- | --- | --- |
| Mục tiêu chính | Integrity và authentication của nội dung được ký/MAC | Confidentiality thông qua mã hóa |
| JWT compact phổ biến | 3 phần | 5 phần |
| Payload dễ đọc khi Base64url decode? | **Có**, trong trường hợp JWS compact thông thường | **Không**, ciphertext cần giải mã |
| Xử lý bắt buộc | Xác minh chữ ký/MAC theo policy, sau đó kiểm claims | Giải mã bằng key được tin cậy, sau đó kiểm đầy đủ claims và những bảo vệ liên quan |
| Có thể kết hợp? | Có: nested JWT theo profile phù hợp | Có: mã hóa JWT đã ký và xử lý theo thứ tự quy định |

**JWT không tự đồng nghĩa JWT đã được ký.** Format và profile có các khả năng khác nhau, kể cả tình huống không bảo vệ tính toàn vẹn. Một hệ thống dùng JWT làm credential bảo mật phải **không chấp nhận token không có cơ chế bảo vệ phù hợp hoặc thuật toán ngoài allowlist**.

## 4. Bài Java 17+ độc lập: đọc payload khác xác minh chữ ký

Ví dụ sau chạy với **JDK 17+**, không cần Spring Boot, Maven hay thư viện JSON. Nó tự tạo một JWS với **HS256** dùng secret chỉ dành cho phòng lab, xác minh chữ ký HMAC và cho thấy việc sửa subject từ alice thành admin làm chữ ký không hợp lệ.

Bài thực hành này **không tạo ra một giao thức đăng nhập**, **không xác thực username/password**, và **không phải thư viện JWT để sử dụng production**. Mục tiêu duy nhất là quan sát cấu trúc, Base64url và integrity. Để dùng JWT thật, cần thư viện chuẩn và chính sách xác minh claims, issuer, audience, token type, thời gian, key rotation.

### 4.1. Mã nguồn

Tạo file **JwtFormatLab.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.Base64;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class JwtFormatLab {

    // Chỉ dành cho thí nghiệm cục bộ.
    // Không hard-code signing secret trong sản phẩm thật.
    private static final byte[] LAB_KEY =
            "classroom-key-not-for-real-token-signing-2026"
                .getBytes(StandardCharsets.UTF_8);

    private static final String HEADER =
            "{\"alg\":\"HS256\",\"typ\":\"JWT\"}";

    private static String encode(String text) {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(
                    text.getBytes(StandardCharsets.UTF_8));
    }

    private static String encodeBytes(byte[] bytes) {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(bytes);
    }

    private static String decode(String encoded) {
        return new String(
            Base64.getUrlDecoder().decode(encoded),
            StandardCharsets.UTF_8);
    }

    private static byte[] sign(String signingInput) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(LAB_KEY, "HmacSHA256"));
        return mac.doFinal(
            signingInput.getBytes(StandardCharsets.UTF_8));
    }

    private static boolean hasValidSignature(String token)
            throws Exception {
        String[] parts = token.split("\\.", -1);
        if (parts.length != 3) {
            return false;
        }

        try {
            // Lab chỉ cho một protected header cố định, tránh
            // chọn thuật toán do dữ liệu đầu vào tùy ý yêu cầu.
            if (!HEADER.equals(decode(parts[0]))) {
                return false;
            }

            byte[] expected = sign(parts[0] + "." + parts[1]);
            byte[] received =
                    Base64.getUrlDecoder().decode(parts[2]);

            return MessageDigest.isEqual(expected, received);
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        long expiresAt = Instant.now()
                .plusSeconds(60)
                .getEpochSecond();

        String claims =
            "{\"iss\":\"https://issuer.example\"," +
            "\"sub\":\"alice\"," +
            "\"aud\":\"reports-api\"," +
            "\"exp\":" + expiresAt + "}";

        String signingInput = encode(HEADER) + "." + encode(claims);
        String token = signingInput + "." +
                encodeBytes(sign(signingInput));

        String[] parts = token.split("\\.", -1);

        // Decode chỉ chứng minh rằng payload đọc được.
        boolean payloadReadable = decode(parts[1])
                .contains("\"sub\":\"alice\"");

        // Đổi subject nhưng giữ signature cũ.
        String changedClaims = claims.replace(
                "\"sub\":\"alice\"", "\"sub\":\"admin\"");
        String modifiedToken = parts[0] + "." +
                encode(changedClaims) + "." + parts[2];

        System.out.println("segments=" + parts.length);
        System.out.println("payloadReadable=" + payloadReadable);
        System.out.println("signatureValid=" +
                hasValidSignature(token));
        System.out.println("modifiedSignatureValid=" +
                hasValidSignature(modifiedToken));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac JwtFormatLab.java
java JwtFormatLab
~~~

**Stdout dự kiến chính xác**:

~~~text
segments=3
payloadReadable=true
signatureValid=true
modifiedSignatureValid=false
~~~

Vì exp được tạo theo thời điểm chạy nên compact token sẽ khác nhau giữa các lần thực thi, nhưng chương trình không in token ra stdout. Phần chữ ký được kiểm tra bằng **MessageDigest.isEqual** để tránh dùng phép so sánh byte tùy tiện; JCA Mac xây HMAC SHA-256 bằng secret cho lab.

### 4.2. Giới hạn bảo mật của bài lab

**Đặc biệt quan trọng:** Phương thức **hasValidSignature** chỉ chứng minh một kiểm tra **HMAC trên đúng signing input** bằng key lab. Nó **không** kiểm tra:
- Authentication của người dùng đã được thực hiện hay chưa.
- Issuer có nằm trong danh sách tin cậy không.
- Audience có đúng API đang nhận hay không.
- Token hết hạn, chưa có hiệu lực, bị thu hồi hoặc sai mục đích sử dụng.
- Quyền được cấp, ownership của dữ liệu, session hoặc MFA.
- Key rotation, thuật toán cho từng issuer, nested JWT và mọi biến thể JOSE thực tế.

Một token có chữ ký hợp lệ **vẫn có thể bị từ chối** nếu exp đã qua, aud sai hoặc issuer không được chấp nhận. Do vậy, **không chép code tự xử lý JWT ở trên vào API production**. Hãy dùng Nimbus thông qua Spring Security hoặc thư viện được duy trì, có cấu hình allowlist algorithm và validation profile thích hợp.

**Kết luận của thí nghiệm:** Payload đọc được không chứng minh token hợp lệ; chữ ký đúng chứng minh integrity theo key được chọn, nhưng **vẫn chưa xây thành toàn bộ quy trình đăng nhập/ủy quyền**.

## 5. OAuth 2.0 và OpenID Connect dùng JWT ở chỗ nào?

### 5.1. OAuth 2.0 là framework ủy quyền

OAuth 2.0 mô tả các vai trò quan trọng:

| Vai trò | Vai trò trong thực tế |
| --- | --- |
| **Resource Owner** | Chủ thể có quyền ủy quyền truy cập tài nguyên |
| **Client** | Ứng dụng muốn truy cập tài nguyên |
| **Authorization Server** | Hệ thống xác thực/ủy quyền và cấp token theo grant |
| **Resource Server** | API nắm tài nguyên, xác minh access token rồi áp dụng quyền |

Một OAuth 2.0 flow quy định cách client được cấp quyền nhận access token, các bước trao đổi với authorization server và cách token được sử dụng với API. **OAuth 2.0 không buộc access token là JWT.** Một server có thể cấp opaque token không có cấu trúc ý nghĩa với client; resource server dùng introspection với hệ thống cấp token.

OAuth 2.0 cũng không phải lúc nào là “đăng nhập người dùng”. **Client Credentials Grant** có thể phục vụ service-to-service, không liên quan một user đang login bằng giao diện browser.

### 5.2. OpenID Connect bổ sung lớp định danh người dùng

**OpenID Connect (OIDC)** xây trên OAuth 2.0 để hỗ trợ **xác thực danh tính end-user** cho client. Nó định nghĩa **ID token**, các claim định danh, discovery, chuẩn xác minh và các hành vi giao thức khác.

Trong một OIDC Authorization Code flow điển hình:

~~~text
Browser / User        Application Client          Identity Provider / AS
     |                        |                              |
     | Mở ứng dụng            |                              |
     |----------------------->|                              |
     |                        | Redirect đến authorization   |
     |<-----------------------|                              |
     |------------------------------------------------------>|
     |                        |   Đăng nhập / MFA / consent   |
     |<------------------------------------------------------|
     |                        |  Redirect về callback + code |
     |----------------------->|                              |
     |                        | POST token endpoint + code   |
     |                        | + PKCE verifier              |
     |                        |----------------------------->|
     |                        |<-----------------------------|
     |                        | ID token và/hoặc access token|
     |                        | theo response chuẩn          |
     |                        |                              |
     |                        | Validate ID token, gắn login |
     |<-----------------------|                              |
     | Ứng dụng cho vào UI    |                              |
~~~

Sơ đồ cố ý khái quát các bước. Trong triển khai thật còn cần state, nonce khi áp dụng, redirect URI matching, PKCE S256, client authentication khi thích hợp, token endpoint security, cookie/session và cách client lưu credential. **JWT chỉ là một cấu trúc dữ liệu nằm ở một số bước trong flow; nó không thay thế flow.**

**Authorization Code + PKCE** là lựa chọn phổ biến và được khuyến nghị cho các client phù hợp. RFC 9700 đưa ra best practices cập nhật về PKCE, redirect URI, refresh token, sender-constrained token và những luồng không an toàn cần tránh.

### 5.3. Ba loại token không được dùng lẫn

| Token | Mục đích | Bên thường nhận/xác minh | Có bắt buộc là JWT? |
| --- | --- | --- | --- |
| **ID token** | Thông tin về sự kiện xác thực end-user cho OIDC client | OIDC Client / Relying Party | **Có**, theo OIDC Core ID token là JWT |
| **Access token** | Credential để gọi API/resource server theo scope/quyền được cấp | Resource Server | **Không**, có thể JWT hoặc opaque |
| **Refresh token** | Đề nghị cấp access token mới mà không lặp lại toàn bộ grant flow | Authorization Server / token endpoint | **Không**, thường xử lý như credential opaque với vòng đời riêng |

**Không dùng ID token làm Bearer access token để gọi API** trừ khi API được thiết kế một cách đúng chuẩn cho loại token đó. ID token thường có audience là **client ứng dụng**, không phải resource server API; việc chấp nhận nó ở API gây ra **token substitution / cross-JWT confusion**.

Tương tự, không gửi refresh token cho resource server để gọi API. Refresh token dùng theo giao thức với authorization server, thường có yêu cầu storage, binding và rotation/revocation nghiêm ngặt.

### 5.4. JWT access token không phải ID token

Một token có các claim sub, iss, aud, exp chưa đủ để biết loại token. Phải xem **issuer profile, kiểu token được phát hành, audience và yêu cầu validation**. Có những tiêu chuẩn riêng cho JWT access token profile; hai JWT từ cùng issuer có thể có mục đích hoàn toàn khác nhau.

Bên nhận cần có quy tắc **mutually exclusive validation** khi hệ thống hỗ trợ nhiều loại JWT. Không cho một token được phát cho client đăng nhập lọt sang API quản trị chỉ vì chữ ký hợp lệ và đều có sub.

## 6. Resource Server nhận JWT: từ byte string tới Authentication

Đây là nơi JWT xuất hiện rõ trong Spring Security:

~~~text
HTTP request: Authorization: Bearer <access-token>
                             |
                             v
                   BearerTokenAuthenticationFilter
                             |
                             v
                     JwtAuthenticationProvider
                             |
                             v
                          JwtDecoder
                             |
                +------------+--------------+
                |                           |
        Chữ ký/key/alg hợp lệ?       iss, exp, nbf, aud,
                |                    token profile hợp lệ?
                +------------+--------------+
                             |
                       Token được chấp nhận
                             |
                             v
                  JwtAuthenticationConverter
                             |
                  Principal + GrantedAuthority
                             |
                             v
                   SecurityContext / authorization
                             |
            +----------------+----------------+
            |                                 |
        Cho phép API                     HTTP 401/403
~~~

**Giải thích:**

1. Spring Security lấy Bearer token từ header Authorization theo cấu hình Resource Server.
2. **JwtDecoder** kiểm tra token dựa vào key/issuer/validator; chưa có bằng chứng hợp lệ thì không coi payload là danh tính tin cậy.
3. Khi xác thực thành công, Spring Security tạo **Authentication**. Với thiết lập mặc định, principal thường là **Jwt**, và tên Authentication thường dựa trên claim sub.
4. Scope trong claim **scope/scp** thông dụng được ánh xạ thành **GrantedAuthority** với prefix **SCOPE_**; ví dụ reports.read → SCOPE_reports.read.
5. **SecurityFilterChain / AuthorizationManager** quyết định endpoint được phép hay không.

Nếu token hợp lệ nhưng thiếu quyền **SCOPE_reports.read**, một request đã được xác thực vẫn có thể bị **403 Forbidden**. Nếu token sai chữ ký, sai issuer, hết hạn hoặc không có Bearer token ở endpoint yêu cầu xác thực, thường là **401 Unauthorized** cùng WWW-Authenticate phù hợp.

**Resource Server không phải Authorization Server.** Việc Spring Security có thể kiểm tra JWT **không có nghĩa nó đã có API login, đăng ký tài khoản, MFA, OAuth authorization endpoint, token issuance hoặc refresh token**.

## 7. Spring Boot 3.x: cấu hình Resource Server kiểm tra JWT đúng issuer

Phần này tạo một ứng dụng Spring Boot Servlet thực sự nhận **JWT access token từ một issuer đã có** và phân quyền theo scope. Nó là **mẫu resource server**, không phải một hệ thống phát hành token; bạn cần kết nối nó với **Authorization Server/Identity Provider hợp lệ của môi trường mình** để thử những request có token.

### 7.1. Khởi tạo dự án

Dùng Spring Initializr:
- Java **17+**, Spring Boot **3.x**, Gradle.
- Group **com.example**, package **com.example.demo**.
- Dependencies: **Spring Web** và **OAuth2 Resource Server** (spring-boot-starter-web, spring-boot-starter-oauth2-resource-server).

Starter resource server của Spring Boot kéo theo các phần tích hợp cần thiết để xác minh JWT/JWS theo cấu hình được hỗ trợ. Không viết thủ công một AuthenticationFilter nhận bất kỳ chuỗi ba phần rồi tự đánh dấu authenticated.

### 7.2. Toàn bộ Java backend cho resource server

Tạo file **src/main/java/com/example/demo/JwtResourceServerApplication.java**:

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JwtResourceServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(JwtResourceServerApplication.class, args);
    }
}

@Configuration
class ResourceServerSecurityConfiguration {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET, "/api/public")
                        .permitAll()
                    .requestMatchers(HttpMethod.GET, "/api/me")
                        .authenticated()
                    .requestMatchers(HttpMethod.GET, "/api/reports")
                        .hasAuthority("SCOPE_reports.read")
                    .anyRequest().denyAll())
                .oauth2ResourceServer(oauth ->
                    oauth.jwt(Customizer.withDefaults()))
                .build();
    }
}

@RestController
class ApiController {

    @GetMapping("/api/public")
    String publicInfo() {
        return "public";
    }

    @GetMapping("/api/me")
    Map<String, String> currentUser(Authentication authentication) {
        return Map.of("subject", authentication.getName());
    }

    @GetMapping("/api/reports")
    String reports() {
        return "reports-ok";
    }
}
~~~

**Code Java này có cấu trúc class hợp lệ**: chỉ JwtResourceServerApplication là public class và trùng tên file; các class còn lại cùng package được Spring scan. Nó xây Spring Security filter chain và ba endpoint GET; không cần tạo HttpSession để xác thực Bearer theo mô hình resource server điển hình.

### 7.3. Cấu hình issuer và audience

Tạo file **src/main/resources/application.yml**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/training
          audiences: reports-api
~~~

**https://idp.example.org/realms/training là issuer giả định chỉ để minh họa cách cấu hình**. Muốn kiểm tra token thực, phải thay bằng issuer URL chính xác do Identity Provider của bạn công bố; IDP phải cung cấp metadata/JWK Set để Spring Security có thể tìm public key phù hợp và token thực phải có claim **iss** tương ứng. Thuộc tính **audiences** áp dụng kiểm tra claim aud; ở ví dụ, token phát cho API khác không được chấp nhận vào reports-api.

Theo Spring Security 6.5, cấu hình tối thiểu qua issuer-uri có thể dùng discovery của issuer để tìm JWK Set, xác minh chữ ký, **iss**, **exp** và **nbf**, đồng thời ánh xạ scope thành **SCOPE_...**. Audience là ràng buộc cần cấu hình bổ sung theo API cụ thể; Spring Boot hỗ trợ thuộc tính **audiences** như trên.

**Không lấy URL JWK từ header của token chưa được tin cậy một cách tùy tiện.** Danh sách issuer, key source và thuật toán hợp lệ phải bắt nguồn từ cấu hình đáng tin cậy. Nếu có nhiều issuer, cần thiết kế xử lý multi-tenant/multi-issuer có ranh giới tin cậy rõ ràng, không chỉ giải mã claim iss rồi tin theo nó.

### 7.4. Chạy và kiểm tra

Trong thư mục Gradle:

~~~bash
./gradlew bootRun
~~~

Windows dùng **gradlew.bat bootRun**. Khi chạy với issuer giả định ở trên, **không có token thật để xác thực**. Để kiểm tra đường /api/me và /api/reports có 200, bạn cần một IDP thật với issuer, audience và scope đúng. Không giả tạo token ký bằng secret lab rồi hy vọng resource server dùng public key IDP sẽ chấp nhận.

Các lệnh thử:

~~~bash
# Endpoint public:
curl -i http://localhost:8080/api/public

# Endpoint bảo vệ, không có token:
curl -i http://localhost:8080/api/me

# Khi đã có access token hợp lệ từ IDP được cấu hình:
curl -i -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/me

# Token còn cần scope reports.read:
curl -i -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/reports
~~~

Bảng kết quả **dự kiến theo chính sách**, không phải log chạy thực tế:

| Request / token | Status điển hình | Giải thích |
| --- | --- | --- |
| GET /api/public, không token | **200** | permitAll, body public |
| GET /api/me, không token | **401** | Cần Authentication |
| GET /api/me, token sai chữ ký | **401** | JwtDecoder từ chối token |
| GET /api/me, token exp đã qua | **401** | Token không còn hợp lệ |
| GET /api/me, token iss/aud sai | **401** | Không đúng nguồn/mục tiêu tin cậy |
| GET /api/me, access token hợp lệ | **200** | Authentication được tạo từ token |
| GET /api/reports, token hợp lệ nhưng không có scope reports.read | **403** | Thiếu SCOPE_reports.read |
| GET /api/reports, token hợp lệ có scope reports.read | **200** | Body reports-ok |
| GET endpoint chưa được cấp phép | **403** nếu request đã xác thực và match denyAll | Rule cuối từ chối |

Status và header lỗi thực tế phụ thuộc Spring Security và các filter/entry point được cấu hình. Đặc biệt, với request chưa xác thực rơi vào denyAll, kết quả có thể là **401**, không phải lúc nào cũng 403. API trên chỉ có GET; nếu thêm POST/PUT/DELETE, cần thiết kế phân quyền và đánh giá CSRF theo cách client gửi credential, không tắt CSRF toàn bộ bằng thói quen.

**Không có POST /login trong ví dụ**. Spring Resource Server chỉ xác minh JWT đã được cấp bởi một bên khác. Muốn có login OIDC, ứng dụng client cần cấu hình OAuth2 Client/OIDC, còn bên cấp token cần Authorization Server phù hợp.

### 7.5. Quyền từ scope và role không tự giống nhau

Một claim như:

~~~json
{"scope": "reports.read reports.write"}
~~~

theo quy tắc converter mặc định được ánh xạ thành **SCOPE_reports.read**, **SCOPE_reports.write**. Nó **không tự tạo ROLE_ADMIN**. Ngược lại, JWT từ một provider có claim roles kiểu tùy biến chưa chắc được chuyển sang Spring GrantedAuthority.

Ví dụ:
- **hasAuthority("SCOPE_reports.read")** kiểm tra scope ở trên.
- **hasRole("ADMIN")** thường kiểm tra GrantedAuthority **ROLE_ADMIN**.
- **hasAuthority("reports.read")** sẽ không khớp quyền **SCOPE_reports.read** nếu chưa cấu hình converter khác.

Khi cần ánh xạ claims tùy biến, hãy viết **JwtAuthenticationConverter / JwtGrantedAuthoritiesConverter** được kiểm thử, xác định rõ issuer profile và chỉ ánh xạ quyền được cấp tin cậy. Không lấy danh sách role do client tự gửi trong request JSON để xây authority.

## 8. Phát hành token và xác minh token là hai trách nhiệm khác nhau

### 8.1. Authorization Server cần những gì ngoài JWT?

Để hệ thống thực sự cung cấp đăng nhập hoặc cấp quyền theo giao thức, cần thiết kế nhiều thành phần mà cấu trúc JWT không bao hàm:

- **Cách xác thực ban đầu**: user/password với PasswordEncoder, passkey, MFA, federation hoặc client authentication.
- **Bản ghi client**: client_id, redirect URI, loại client public/confidential, allowed scopes, client authentication.
- **Luồng xin quyền (grant)**: authorization code, PKCE, consent, state/nonce khi phù hợp.
- **Token endpoint**: phát hành access token, refresh token, ID token theo profile; không phải luôn phát hành mọi loại.
- **Signing keys / JWK**: sinh khóa, lưu secret/private key an toàn, công bố public key, rotate và thu hồi key.
- **Định nghĩa claims**: issuer/audience/subject, scope và quyền, expiration, token type, version.
- **Token validation**: resource server kiểm key/alg, issuer/audience, thời gian, mục đích sử dụng, quyền.
- **Vòng đời và thu hồi**: revoke, refresh token rotation, logout, expiration, thay đổi mật khẩu/quyền.
- **Tấn công và giám sát**: brute force, token replay, redirect attacks, token leakage, audit và rate limit.

Thay vì viết tất cả bằng một @RestController trả JWT tự ký, các ứng dụng có thể tích hợp **OpenID Provider/Authorization Server** đã có hoặc sử dụng Spring Authorization Server theo một thiết kế bảo mật đầy đủ. Spring Security Resource Server **không** tự đảm nhận các trách nhiệm phát hành ở trên.

### 8.2. Authentication một lần, phân quyền nhiều lần

Một lần login OIDC có thể kết thúc bằng client session cookie để duy trì giao diện người dùng. Trong khi đó, API có thể yêu cầu Bearer access token riêng. Hai cơ chế **có thể cùng tồn tại**:

~~~text
User login tại Identity Provider
        |
        v
OIDC client xác thực thành công
        |
        +--> Ứng dụng web tạo session cho browser
        |
        +--> OAuth client có access token để gọi API
                 |
                 v
           Resource Server kiểm Bearer token
~~~

Nhìn thấy browser có cookie phiên không cho biết API dùng JWT hay opaque token. Nhìn thấy API nhận JWT cũng không chứng minh browser đang dùng JWT làm phiên đăng nhập.

## 9. Những bước xác minh JWT bắt buộc phải suy nghĩ

Không nên thiết kế một hàm **decodeJwt()** đọc claims rồi trả về UserDetails mà không có bước xác minh đầy đủ.

### 9.1. Allowlist thuật toán, khóa và issuer

- Cho phép **các thuật toán cụ thể** theo cấu hình; không chọn một thuật toán khác chỉ vì trường **alg** của token yêu cầu.
- Đối với **HS256**, bên ký và bên kiểm tra cùng giữ secret; ai có secret đều có thể tạo chữ ký. Nếu nhiều service cùng giữ secret, phạm vi tin cậy rộng hơn.
- Đối với **RS256/ES256**, issuer thường giữ private key để ký; resource server nhận public key để xác minh. Resource server không cần giữ private signing key.
- Chỉ lấy key từ **issuer/JWK Set URI được cấu hình là tin cậy**; xử lý kid bằng bộ khóa của issuer đó.
- Thiết kế key rotation, cache/JWKS refresh và kế hoạch loại bỏ key cũ; không viết key/secret trực tiếp vào source production.

### 9.2. Kiểm tra claims theo resource và loại token

| Bước | Nếu bỏ qua có thể xảy ra |
| --- | --- |
| Verify chữ ký/MAC và thuật toán hợp lệ | Attacker sửa payload thành quyền admin hoặc giả mạo issuer |
| Kiểm tra **iss** | Chấp nhận token do bên khác cấp |
| Kiểm tra **aud** | Dùng token được phát cho API/client khác để truy cập nhầm tài nguyên |
| Kiểm tra **exp/nbf** | Token hết hạn/chưa có hiệu lực vẫn dùng được |
| Kiểm tra token type / profile | Dùng nhầm ID token, refresh token hoặc loại JWT khác thành access token |
| Kiểm tra scope/authority | Một token hợp lệ về mật mã nhưng không đủ quyền vẫn đọc/sửa dữ liệu |
| Kiểm tra resource ownership/tenant | Scope đúng nhưng user xem tài nguyên của người khác |
| Kiểm soát replay/revocation khi cần | Token bị lấy cắp vẫn được tái dùng đến hết hạn |
| Kiểm tra trust boundary của issuer/key | Token từ bên không được phép tạo ra quyền tin cậy |

**Chữ ký đúng chỉ là điều kiện cần trong nhiều trường hợp, không đủ để authorization thành công.**

### 9.3. Key confusion, algorithm confusion và cross-JWT confusion

RFC 8725 nhấn mạnh những kiểu lỗi nghiêm trọng:
- **Algorithm confusion**: chấp nhận thuật toán không mong muốn hoặc dùng key sai loại.
- **Cross-JWT confusion**: chấp nhận JWT phát hành cho mục đích khác, ví dụ ID token tại API vốn yêu cầu access token.
- **Weak key/secret management**: sử dụng secret dễ đoán, chia sẻ quá rộng hoặc không rotate.
- **Không ràng buộc issuer/audience**: cho phép token từ bối cảnh khác đi vào resource server.
- **Tra cứu dữ liệu từ claim không đáng tin**: có thể dẫn tới injection, SSRF hoặc truy cập tài nguyên sai tenant.

**kid không phải một lệnh truy cập filesystem**. Không nối trực tiếp kid vào đường dẫn để đọc private key và không tự fetch URL bất kỳ do token chỉ định. Chỉ chọn key trong bộ key tin cậy đã đăng ký.

### 9.4. JWT không tự bảo vệ khỏi đánh cắp/replay

Một access token dạng **Bearer** có nghĩa ai cầm token hợp lệ có thể xuất trình token trong phạm vi của nó, trừ khi token có cơ chế ràng buộc người gửi. Chữ ký đúng không ngăn người khác dùng bản sao token lấy cắp. Các biện pháp thường cân nhắc:
- Bắt buộc **HTTPS**; không đưa token vào URL, lịch sử trình duyệt hoặc log.
- Access token sống ngắn theo threat model; rotate signing keys có quản lý.
- Bảo vệ token ở client; không lưu thông tin bí mật lộ ra cho JavaScript khi không cần.
- Sender-constrained access token như **DPoP/mTLS** khi yêu cầu bảo mật cao.
- Với refresh token của public client, sử dụng **sender-constraining hoặc refresh token rotation** theo RFC 9700.
- Thiết kế thu hồi quyền/phiên khi đổi mật khẩu, mất thiết bị, khóa tài khoản hoặc phát hiện xâm nhập.

Nếu token JWT được tự xác minh và còn hạn, chỉ “logout trên UI” không bảo đảm API từ chối bản sao token ngay lập tức. Cần thiết kế TTL và/hoặc kiểm tra revocation/session/version phù hợp.

## 10. Session, CSRF, CORS và cookie vẫn liên quan dù có JWT

Một vài kết luận sai thường thấy:

**Sai:** “Dùng JWT nên không cần CSRF.”  
**Đúng:** CSRF phụ thuộc cách browser tự gửi credential. Nếu JWT được đặt trong cookie và browser tự gửi cookie theo request, phải đánh giá CSRF như hệ thống cookie-authentication phù hợp. Nếu bearer token được client thêm chủ động vào Authorization header, threat model khác nhưng vẫn cần chống XSS/token theft.

**Sai:** “Dùng JWT là không có session trên toàn hệ thống.”  
**Đúng:** Resource server có thể xác thực JWT per-request mà không dùng HttpSession để lưu Authentication, nhưng browser client, Identity Provider và Authorization Server vẫn có thể dùng session; refresh token cũng có thể gắn với một grant hoặc phiên server-side.

**Sai:** “CORS được phép là API đã an toàn.”  
**Đúng:** CORS là cơ chế browser kiểm soát chia sẻ cross-origin; server vẫn phải xác thực token và kiểm tra quyền. Client ngoài browser không bị ràng buộc giống browser.

**Sai:** “Payload chỉ có sub và role, ký lại rồi gửi thì đăng nhập được.”  
**Đúng:** Token chỉ được chấp nhận nếu chữ ký được tạo bằng key của issuer đáng tin cậy, đúng thuật toán và thỏa điều kiện iss/aud/type/time/quyền. Client không có quyền tự đề xuất role rồi bắt server tin nó.

### Vị trí lưu token ở frontend

- **Memory:** hạn chế một số rủi ro lưu trữ lâu dài, nhưng refresh hoặc reload cần chiến lược lấy token lại.
- **LocalStorage/SessionStorage:** JavaScript cùng origin có thể truy cập, nên XSS là rủi ro đặc biệt quan trọng.
- **HttpOnly cookie:** JavaScript không đọc trực tiếp cookie nếu thuộc tính HttpOnly; tuy nhiên cookie có thể tự gửi, cần chính sách SameSite/Secure/CSRF và hiểu browser session.
- **Backend-for-Frontend (BFF):** có thể giữ token phía backend và dùng session cookie cho browser; giảm việc đưa access token vào JavaScript, nhưng vẫn phải bảo vệ session/cookie và CSRF.

Không có một lựa chọn storage an toàn tuyệt đối cho mọi ứng dụng; phải xem loại client, kiến trúc origin, CSRF, XSS và khả năng thu hồi.

## 11. Kiểm thử JWT và giao thức phải tách hai lớp

### 11.1. Kiểm thử Resource Server

Tạo ma trận test tối thiểu:

| Đầu vào | Kết quả đúng cần kiểm tra |
| --- | --- |
| Không có Bearer token gọi endpoint protected | 401 |
| Token sai định dạng/chữ ký/thuật toán | 401 |
| Token issuer lạ | 401 |
| Token audience không phải API này | 401 |
| Token hết hạn hoặc chưa có hiệu lực | 401 |
| Token hợp lệ nhưng thiếu scope được yêu cầu | 403 |
| Token hợp lệ có scope và đúng resource policy | 200 |
| Token có scope nhưng thuộc tenant khác | Bị từ chối theo chính sách dữ liệu |
| ID token được gửi thay access token | Bị từ chối theo validation profile |
| Token đã thu hồi/credential bị khóa | Bị từ chối nếu hệ thống có yêu cầu thu hồi tức thời |
| Header alg hoặc kid bất thường | Không được tự chọn khóa/thuật toán thiếu kiểm soát |

### 11.2. Phân biệt mock JWT test với kiểm thử crypto

Trong Spring Security Test, helper **jwt()** có thể dựng Authentication cho MockMvc để kiểm thử authorization rule mà **không thực hiện full cryptographic validation của JWT**. Ví dụ test này là fragment minh họa bên trong một @SpringBootTest / @AutoConfigureMockMvc test, cần dependency spring-security-test:

~~~java
mvc.perform(get("/api/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());

mvc.perform(get("/api/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_profile"))))
    .andExpect(status().isForbidden());
~~~

Các static imports trong test: **MockMvcRequestBuilders.get**, **MockMvcResultMatchers.status**, **SecurityMockMvcRequestPostProcessors.jwt**; kiểu GrantedAuthority có thể dùng **SimpleGrantedAuthority**. Đây **không** phải class test độc lập để chạy bằng javac.

**Hai test trên chứng minh cách endpoint xét authority khi context đã có JWT Authentication**, nhưng không chứng minh JwtDecoder từ chối chữ ký sai, aud sai hoặc issuer giả. Muốn kiểm tra hệ thống thật, cần bài test tích hợp dùng **token thực/fixture đã ký** và **JwtDecoder đã được cấu hình**, hoặc môi trường issuer/JWKS test kiểm soát được. Đừng khẳng định security hoàn chỉnh chỉ vì mọi MockMvc test dùng jwt() đều xanh.

### 11.3. Kiểm thử client login OIDC khác với kiểm thử API

Đối với OIDC client, cần kiểm:
- Authorization Code flow và PKCE chính xác, chống code injection.
- state/nonce khi cần, redirect URI và client authentication.
- ID token validation với issuer/audience/nonce theo profile.
- Không dùng ID token làm API Bearer access token.
- Login session/cookie, logout, refresh và các lỗi provider.
- Token bị lộ trong URL/log hoặc bị tái sử dụng ngoài mục đích.

Một API resource server không tự chứng minh OIDC client login hoạt động; ngược lại login thành công không tự chứng minh API đang xác minh access token đúng.

## 12. Chẩn đoán những nhầm lẫn phổ biến

| Hiện tượng/nhận định | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| “Token có ba phần thì chắc chắn hợp lệ” | Chỉ kiểm format, chưa verify chữ ký và claims | Dùng JwtDecoder/validator đầy đủ |
| “Base64 decode ra role ADMIN nên cho quyền” | Tin payload chưa xác minh | Kiểm signature, issuer, audience, token type và authority |
| “JWT là OAuth” | Nhầm định dạng token với framework ủy quyền | Tách token serialization khỏi grant/authorization |
| “OAuth 2.0 luôn trả JWT” | OAuth không cố định encoding access token | Hỗ trợ JWT hoặc opaque theo issuer |
| “Có ID token thì dùng để gọi API” | Sai audience/mục đích token | API chỉ nhận access token theo profile |
| “JWT là encryption” | JWS thông thường chỉ Base64url + signature | Không chứa thông tin bí mật trong payload; dùng JWE khi cần |
| “Chữ ký đúng thì mọi API phải chấp nhận” | Chưa ràng buộc issuer/aud và scope | Kiểm resource-specific claims/policy |
| “Bearer token tự bảo vệ khỏi replay” | Token là credential có thể bị sao chép | TLS, TTL, secure storage, DPoP/mTLS khi phù hợp |
| “Spring Resource Server tự có endpoint login” | Chỉ cấu hình xác minh token nhận được | Dùng OAuth/OIDC client và Authorization Server phù hợp |
| “Tắt CSRF là bắt buộc khi JWT” | Nhầm định dạng token với browser credential transport | Đánh giá CSRF theo cách trình duyệt gửi credential |
| “JwtDecoder tự hiểu claim roles tùy biến” | Converter mặc định chú trọng scope/scp | Cấu hình JwtAuthenticationConverter có kiểm thử |
| “Token không có JSESSIONID thì thiếu SecurityContext” | SecurityContext cho request vẫn tồn tại | Hiểu stateless per-request authentication |
| “Logout xóa JWT khỏi server ngay” | JWT tự xác minh có thể còn hiệu lực | TTL, revocation/introspection/token version tùy yêu cầu |
| “kid có thể chỉ tới mọi key URL” | Tin header của token chưa xác minh | Chỉ chọn key từ JWKS/issuer được tin cậy |
| “MockMvc jwt() test chữ ký” | Helper thường giả lập Authentication | Bổ sung decoder/issuer/JWKS integration tests |

### Cách debug trong Spring Security

1. Xem request có đúng **Authorization: Bearer** và token dành cho API này không.
2. Kiểm tra issuer-uri/JWK Set URI, key rotation, algorithm whitelist.
3. Kiểm tra **iss, aud, exp, nbf**, token profile/type.
4. Sau khi token hợp lệ, xem **Authentication.getAuthorities()**, scope mapping và request matcher.
5. Phân biệt **401** (không xác thực được) với **403** (đã xác thực nhưng thiếu quyền hoặc bị chặn bởi lớp khác).
6. Rà soát session/cookie nếu browser còn một bước OIDC login hoặc BFF.
7. Không log nguyên JWT, refresh token, Authorization header hoặc private signing key.

Dùng mức DEBUG trong môi trường phát triển nếu cần, nhưng cấu hình logging phải tránh thu thập credential.

## 13. Tình huống thực tế: API quản lý báo cáo

Giả sử ứng dụng gồm:

~~~text
Browser (OIDC Client)
        |
        | Authorization Code + PKCE
        v
Identity Provider / Authorization Server
        |
        | cấp access token JWT với:
        | iss = issuer được tin cậy
        | aud = reports-api
        | scope = reports.read
        v
Backend (Spring Security Resource Server)
        |
        | JwtDecoder xác minh token
        | JwtAuthenticationConverter tạo SCOPE_reports.read
        v
GET /api/reports -> được phép nếu policy phù hợp
~~~

Giả sử attacker sửa payload JWT từ **reports.read** thành **reports.write** nhưng không có private signing key. Chữ ký sẽ không hợp lệ, request bị từ chối. Nếu attacker thay bằng một JWT khác có chữ ký hợp lệ nhưng **aud = billing-api**, API báo cáo cũng phải từ chối vì sai audience. Nếu người dùng có scope reports.read nhưng yêu cầu báo cáo của người khác, ứng dụng còn phải kiểm tra **ownership/tenant**.

Sự an toàn có được từ **chuỗi quyết định tin cậy và kiểm soát**, không phải từ ba dấu chấm trong JWT.

### Khi nào nên dùng opaque token?

Opaque token phù hợp khi Resource Server cần kiểm tra trạng thái và quyền tại một hệ thống trung tâm qua **introspection** hoặc không muốn tiết lộ nội dung claims cho client. Nó không được tự coi là tốt hơn hoặc kém hơn JWT trong mọi hoàn cảnh: phải tính đến latency, availability, thu hồi, cache, trust boundary và quy mô hệ thống.

Spring Security có hỗ trợ **OAuth2 Resource Server Opaque Token** bên cạnh JWT. Chọn JWT hay opaque là **lựa chọn token representation/validation**, độc lập với việc ứng dụng dùng OAuth/OIDC flow nào để cấp quyền.

## 14. Câu hỏi tự đánh giá

1. JWT mô tả **định dạng** gì và tại sao nó không tự định nghĩa endpoint đăng nhập?
2. Vì sao client có thể đọc payload JWS mà không có private key?
3. JWS compact thông thường có bao nhiêu phần? JWE compact có bao nhiêu phần? Chúng bảo vệ những tính chất gì?
4. Một JWT có chữ ký hợp lệ nhưng **aud** là API khác có nên được chấp nhận không? Vì sao?
5. OAuth 2.0 có bắt buộc access token là JWT không? Client Credentials có bắt buộc user login không?
6. OIDC bổ sung điều gì so với OAuth 2.0? ID token phục vụ mục đích gì?
7. Vì sao không nên gửi **ID token** để gọi một API vốn yêu cầu **access token**?
8. Phân biệt **iss**, **sub**, **aud**, **exp** và **scope**.
9. Trong Spring Security, **JwtDecoder** và **JwtAuthenticationConverter** có trách nhiệm khác nhau ra sao?
10. Token có scope reports.read tương ứng authority mặc định nào? **hasRole("ADMIN")** có tự khớp không?
11. Vì sao MockMvc sử dụng helper **jwt()** không đủ để chứng minh decoder xác minh chữ ký đúng?
12. Logout có làm mọi JWT còn hạn ngay lập tức mất hiệu lực không? Cần những chiến lược nào nếu yêu cầu thu hồi ngay?
13. JWT được lưu trong cookie HttpOnly có tự loại bỏ nguy cơ CSRF không? Giải thích theo cách credential được gửi.
14. Khi nào cần key rotation, revocation và token sender-constraining?
15. Nếu xây chức năng đăng nhập OIDC cho SPA, vì sao JWT không thay thế được Authorization Code + PKCE, state và những bước xác minh liên quan?

**Ghi nhớ cuối bài:** **JWT = định dạng claims/token**. **OAuth 2.0 = framework ủy quyền**. **OIDC = lớp định danh/xác thực dựa trên OAuth 2.0**. **Spring Security Resource Server = thành phần nhận và xác minh access token để bảo vệ API**, không phải mặc nhiên là nơi phát hành token. Muốn xây hệ thống đăng nhập đúng, phải thiết kế đủ **cách xác thực, cấp token, kiểm tra token, phân quyền, gia hạn, thu hồi và bảo vệ credential**.

## Tài liệu tham khảo chính thức

- RFC 7519 — JSON Web Token (JWT): https://www.rfc-editor.org/rfc/rfc7519
- RFC 7515 — JSON Web Signature (JWS): https://www.rfc-editor.org/rfc/rfc7515
- RFC 7516 — JSON Web Encryption (JWE): https://www.rfc-editor.org/rfc/rfc7516
- RFC 8725 — JSON Web Token Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
- RFC 6749 — OAuth 2.0 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
- RFC 9700 — Best Current Practice for OAuth 2.0 Security: https://www.rfc-editor.org/rfc/rfc9700
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- Spring Security 6.5 — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security 6.5 — OAuth2 Resource Server opaque tokens: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html
- Spring Security 6.5 — OAuth2 Login: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html
