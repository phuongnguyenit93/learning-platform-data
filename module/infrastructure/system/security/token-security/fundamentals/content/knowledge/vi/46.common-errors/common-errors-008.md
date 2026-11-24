# Không dùng PKCE cho public client

## Mục tiêu

Public client là ứng dụng OAuth 2.0 không thể giữ bí mật client một cách đáng tin cậy, ví dụ ứng dụng native cài trên thiết bị người dùng hoặc ứng dụng chạy trong trình duyệt. Nếu public client dùng Authorization Code Flow mà không có **Proof Key for Code Exchange (PKCE)**, authorization code bị đánh cắp hoặc chèn vào luồng đổi token có thể bị kẻ tấn công sử dụng.

PKCE gắn authorization code với một bí mật ngẫu nhiên tạm thời do client tạo ra. Authorization server chỉ đổi code thành token khi client trình đúng `code_verifier` tương ứng với `code_challenge` đã gửi trong authorization request.

Sau bài này, bạn có thể:

- Giải thích vì sao public client không thể bảo vệ client secret như confidential client.
- Mô tả cuộc tấn công authorization code interception và cách PKCE ngăn kẻ đánh cắp code đổi token.
- Tạo `code_verifier` và `code_challenge` bằng phương thức `S256`.
- Thực hiện Authorization Code Flow có PKCE từ authorization request đến token request.
- Phân biệt PKCE với `state`, OIDC `nonce`, redirect URI validation và client authentication.
- Nhận biết lỗi cấu hình khi server không yêu cầu hoặc không xác minh PKCE.
- Xây dựng test âm cho thiếu verifier, verifier sai, challenge sai và code bị dùng lại.

## 1. Public client không thể giữ client secret

OAuth 2.0 phân loại ứng dụng theo khả năng bảo vệ thông tin xác thực của client:

| Loại client | Ví dụ | Khả năng giữ secret |
| --- | --- | --- |
| Public client | Native mobile app, desktop app phân phối cho người dùng, SPA chạy trong browser | Không thể bảo vệ một secret được nhúng chung trong ứng dụng |
| Confidential client | Backend web app chạy trên server do tổ chức kiểm soát | Có thể giữ secret hoặc private key trong môi trường server được bảo vệ |

Một chuỗi `client_secret` được đóng gói trong ứng dụng mobile, JavaScript bundle hoặc file cài đặt có thể bị trích xuất. Obfuscation, minification hay mã hóa secret trong source không biến public client thành confidential client.

Vì vậy, public client không thể dựa vào client secret để chứng minh rằng bên gửi token request là cùng ứng dụng đã khởi tạo authorization request. Một kẻ tấn công lấy được authorization code có thể thử gửi code đến token endpoint để nhận access token.

PKCE giải quyết phần ràng buộc authorization code với lần khởi tạo giao dịch của client. Nó không biến public client thành confidential client và không chứng minh danh tính thiết bị theo cách một khóa client được bảo vệ có thể làm.

## 2. Authorization code interception xảy ra như thế nào?

Giả sử một ứng dụng mobile dùng Authorization Code Flow:

1. Ứng dụng mở trình duyệt hệ thống và chuyển người dùng đến authorization server.
2. Người dùng đăng nhập và cấp quyền.
3. Authorization server redirect về URI của ứng dụng với authorization code.
4. Ứng dụng gửi code đến token endpoint để nhận token.

Nếu URI callback dùng custom scheme hoặc môi trường có thể bị ứng dụng khác đăng ký/tranh chấp, ứng dụng độc hại có thể nhận được authorization code trước ứng dụng hợp pháp. Nếu token endpoint chỉ cần code và thông tin client công khai, kẻ tấn công có thể đổi code đó lấy token.

~~~mermaid
sequenceDiagram
    participant U as User
    participant A as Legitimate App
    participant AS as Authorization Server
    participant X as Malicious App

    A->>AS: Authorization request
    AS->>U: Login and consent
    AS-->>X: Redirect URI bị chiếm, kèm authorization code
    X->>AS: Token request với code bị đánh cắp
    AS-->>X: Access token nếu không có PKCE
~~~

Đây là ví dụ khái niệm về interception. Trong thực tế, code có thể bị lộ qua custom URI scheme, log, lịch sử redirect, proxy lỗi cấu hình hoặc một thành phần khác trong hệ thống. Authorization code thường có thời hạn ngắn và dùng một lần, nhưng các thuộc tính đó không tự ngăn người lấy được code sử dụng nó trước client hợp pháp.

### PKCE thay đổi luồng như thế nào?

Trước khi mở browser, client tạo một chuỗi ngẫu nhiên `code_verifier`, rồi tính `code_challenge`. Client chỉ gửi challenge trong authorization request. Khi đổi code, client gửi verifier gốc. Authorization server kiểm tra verifier có khớp challenge đã lưu cùng authorization code hay không.

~~~mermaid
sequenceDiagram
    participant A as Public Client
    participant AS as Authorization Server
    participant U as User

    A->>A: Tạo verifier ngẫu nhiên
    A->>A: Tính S256 challenge
    A->>AS: Authorization request + code_challenge
    AS->>U: Login and consent
    U->>AS: Xác thực và cấp quyền
    AS-->>A: Redirect với authorization code
    A->>AS: Token request + code_verifier
    AS->>AS: Tính challenge từ verifier
    AS->>AS: So sánh với challenge gắn với code
    AS-->>A: Token nếu khớp; từ chối nếu sai
~~~

Nếu kẻ tấn công chỉ lấy được authorization code nhưng không lấy được verifier, họ không thể hoàn tất token exchange. Code bị đánh cắp vì thế không đủ để lấy token.

## 3. Cách tạo PKCE đúng chuẩn

PKCE được định nghĩa trong RFC 7636. Client tạo `code_verifier` là chuỗi ngẫu nhiên mật mã, dài từ 43 đến 128 ký tự, sử dụng tập ký tự unreserved theo chuẩn.

Với phương thức `S256`:

~~~text
code_challenge =
    BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
~~~

Các bước:

1. Sinh ít nhất 32 byte ngẫu nhiên từ cryptographically secure random number generator (CSPRNG).
2. Mã hóa thành Base64URL không padding để tạo verifier có entropy cao và độ dài hợp lệ.
3. Tính SHA-256 trên ASCII bytes của verifier.
4. Mã hóa digest bằng Base64URL, bỏ padding để tạo challenge.
5. Gửi `code_challenge` và `code_challenge_method=S256` trong authorization request.
6. Lưu verifier gắn với đúng giao dịch đăng nhập để dùng một lần khi đổi code.

Ví dụ minh họa:

~~~text
code_verifier  = random-generated-string
code_challenge = BASE64URL(SHA256(code_verifier))
method         = S256
~~~

**Không dùng `plain` nếu có thể dùng `S256`.** Với `plain`, challenge chính là verifier; ai quan sát được authorization request sẽ biết luôn bí mật cần gửi ở token request. `S256` chỉ công khai giá trị băm, không công khai verifier gốc.

### Java: tạo verifier và challenge

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

final class Pkce {
    private static final SecureRandom RANDOM = new SecureRandom();

    static String createVerifier() {
        byte[] random = new byte[32];
        RANDOM.nextBytes(random);

        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(random);
    }

    static String createS256Challenge(String verifier)
            throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(verifier.getBytes(StandardCharsets.US_ASCII));

        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);
    }
}
~~~

32 byte ngẫu nhiên được Base64URL mã hóa thành verifier 43 ký tự, đáp ứng giới hạn tối thiểu của RFC 7636. Trong production, không thay `SecureRandom` bằng `Random`, timestamp, UUID được tạo theo cách không có bảo đảm CSPRNG hoặc chuỗi cố định.

### Kiểm tra verifier trước khi sử dụng

Client nên bảo đảm:

- Độ dài nằm trong khoảng 43–128 ký tự.
- Ký tự thuộc tập unreserved được RFC 7636 cho phép.
- Verifier được tạo mới cho mỗi authorization transaction.
- Verifier không xuất hiện trong authorization URL, analytics, crash report hoặc log.
- Challenge được tính đúng trên ASCII bytes và mã hóa Base64URL không padding.
- Method gửi lên server là `S256`.

Không tự normalize verifier (trim, đổi chữ hoa/thường, decode/encode lại) sau khi đã tạo challenge. Bất kỳ thay đổi nào cũng làm phép so sánh không khớp.

## 4. Authorization Code Flow với PKCE

### Authorization request

Ví dụ request đến authorization endpoint:

~~~http
GET /authorize?
  response_type=code&
  client_id=mobile-app&
  redirect_uri=com.example.app%3A%2F%2Fcallback&
  scope=openid%20profile%20orders.read&
  state=STATE_RANDOM&
  nonce=NONCE_RANDOM&
  code_challenge=CHALLENGE_BASE64URL&
  code_challenge_method=S256 HTTP/1.1
Host: identity.example.test
~~~

Ý nghĩa:

- `client_id`: định danh public client đã đăng ký.
- `redirect_uri`: callback URI phải khớp chính xác một URI đã đăng ký theo policy của authorization server.
- `state`: giá trị ngẫu nhiên liên kết request với callback, hỗ trợ chống CSRF và ghép đúng giao dịch.
- `nonce`: dùng trong OIDC để liên kết ID token với authentication request và chống replay ID token.
- `code_challenge`: giá trị dẫn xuất từ verifier.
- `code_challenge_method`: phương thức biến đổi challenge; ưu tiên `S256`.

`state`, `nonce` và PKCE có mục đích liên quan nhưng khác nhau. Đừng bỏ `state` hoặc OIDC `nonce` chỉ vì đã bật PKCE.

### Token request

Sau khi nhận authorization code, client gửi verifier:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
client_id=mobile-app&
code=AUTHORIZATION_CODE&
redirect_uri=com.example.app%3A%2F%2Fcallback&
code_verifier=ORIGINAL_CODE_VERIFIER
~~~

Public client không gửi một `client_secret` được nhúng trong ứng dụng như bằng chứng bảo mật. Authorization server tìm challenge gắn với authorization code, tính challenge từ verifier nhận được và so sánh.

Nếu challenge khớp, server tiếp tục xử lý code, redirect URI, thời hạn, trạng thái dùng một lần và các điều kiện khác. Nếu verifier thiếu hoặc sai, token endpoint phải từ chối token exchange.

### Kiểm tra phía authorization server

Server cần thực hiện các bước:

1. Khi nhận authorization request, xác định client và redirect URI theo registry.
2. Nếu PKCE được yêu cầu, xác thực challenge và method hợp lệ.
3. Lưu challenge, method và ngữ cảnh giao dịch gắn với authorization code.
4. Khi token request đến, xác định code và client/redirect URI phù hợp.
5. Yêu cầu `code_verifier` khi code được tạo với PKCE hoặc khi policy bắt buộc PKCE.
6. Tính challenge từ verifier bằng method đã lưu.
7. So sánh an toàn và từ chối nếu không khớp.
8. Đảm bảo authorization code chỉ đổi thành token một lần và hết hạn theo policy.

Authorization server phải thực thi PKCE ở token endpoint. Chỉ hiển thị tham số `code_challenge` trong URL nhưng không xác minh `code_verifier` không tạo ra bảo vệ thực sự.

## 5. Lưu verifier an toàn trong vòng đời đăng nhập

Verifier là bí mật tạm thời. Nó phải tồn tại đủ lâu để client hoàn tất callback, nhưng không được chia sẻ giữa các giao dịch.

Một giao dịch đăng nhập có thể lưu:

~~~text
transaction_id
state
nonce (OIDC)
code_verifier
created_at
redirect_uri
client_id
~~~

Khi callback đến:

1. Xác minh `state` khớp giao dịch đã bắt đầu.
2. Lấy đúng verifier gắn với giao dịch đó.
3. Gửi verifier cùng authorization code đến token endpoint.
4. Xóa verifier và dữ liệu giao dịch sau khi thành công hoặc khi giao dịch hết hạn.
5. Không dùng lại verifier cho lần đăng nhập tiếp theo.

### Với SPA

Ứng dụng chạy trong browser cần giữ verifier qua chuyển hướng trang. Có thể dùng bộ nhớ theo transaction hoặc `sessionStorage` tùy kiến trúc, nhưng phải cân nhắc XSS: JavaScript độc hại chạy cùng origin có thể đọc dữ liệu lưu trong browser. Giảm rủi ro bằng CSP, dependency hygiene, output encoding, hạn chế script bên thứ ba và thời gian tồn tại ngắn.

Không ghi verifier vào `localStorage` lâu dài nếu không có lý do rõ ràng. Không đưa verifier vào URL hoặc fragment. Với kiến trúc backend-for-frontend (BFF), có thể giữ verifier phía server gắn với session và chỉ gửi cookie session được bảo vệ cho browser.

### Với native app

- Dùng external user-agent/system browser cho authorization theo thực hành native app.
- Tạo verifier trong ứng dụng cho từng giao dịch.
- Lưu tạm trong bộ nhớ hoặc secure storage phù hợp với vòng đời callback.
- Bảo vệ callback bằng redirect URI đã đăng ký; ưu tiên claimed HTTPS/app-claimed links khi nền tảng hỗ trợ.
- Xóa verifier sau token exchange hoặc timeout.
- Không coi custom URI scheme là cơ chế chống interception duy nhất; PKCE vẫn cần thiết.

PKCE bảo vệ authorization code khỏi người chỉ chặn được code. Nó không bảo vệ verifier nếu thiết bị đã bị compromise hoặc ứng dụng có lỗ hổng cho phép mã độc đọc bộ nhớ/storage.

## 6. Vì sao `state`, `nonce` và client secret không thay thế PKCE?

| Cơ chế | Mục đích chính | Không thay thế |
| --- | --- | --- |
| PKCE | Ràng buộc authorization code với verifier của giao dịch client | Redirect URI validation, `state`, token validation |
| `state` | Liên kết authorization response với request đã khởi tạo, chống CSRF trong redirect flow | Proof possession verifier khi đổi code |
| OIDC `nonce` | Liên kết ID token với authentication request, chống replay ID token | Bảo vệ authorization code tại token endpoint |
| Client secret | Xác thực confidential client theo cơ chế đã đăng ký | Không thể giữ an toàn trong public app |
| Redirect URI validation | Giới hạn nơi authorization response được gửi | Không chứng minh bên nhận code có verifier |

Một lỗi phổ biến là thêm `client_secret` vào SPA hoặc mobile app rồi cho rằng code đã an toàn. Secret nằm trong binary/bundle có thể bị trích xuất. Một lỗi khác là chỉ kiểm tra `state`; kẻ lấy được authorization code vẫn có thể thử đổi code nếu token endpoint không yêu cầu PKCE.

## 7. Cấu hình authorization server: bắt buộc PKCE cho public client

Authorization server cần phân loại client chính xác và áp dụng policy:

- Public client dùng Authorization Code Flow phải dùng PKCE.
- Authorization server phải hỗ trợ PKCE và thực thi kiểm tra verifier.
- Nên ưu tiên `S256`; không chấp nhận method không hỗ trợ hoặc không an toàn.
- Nếu authorization request có PKCE, token request phải cung cấp verifier khớp challenge.
- Không cho phép client bỏ PKCE ở token request để hạ cấp giao dịch.
- Gắn challenge với đúng authorization code, client, redirect URI và giao dịch.
- Authorization code phải ngắn hạn, dùng một lần và được tiêu thụ nguyên tử.
- Không cho code phát hành cho client A được đổi bởi client B.
- Áp dụng redirect URI exact matching theo quy định, tránh wildcard rộng.
- Không dựa vào một client secret dùng chung được nhúng trong public app.

RFC 8252 yêu cầu native app sử dụng PKCE trong Authorization Code Flow. OAuth 2.0 Security Best Current Practice (RFC 9700) củng cố việc dùng PKCE cho client và yêu cầu authorization server hỗ trợ, thực thi đúng khi PKCE được dùng. Với public client, cần cấu hình server yêu cầu PKCE thay vì chỉ hỗ trợ tùy chọn. Với confidential client, PKCE cũng là lớp bảo vệ bổ sung hữu ích và được khuyến nghị theo threat model.

### Ngăn downgrade

Nếu client đã gửi `code_challenge`, authorization server phải ràng buộc code với challenge đó. Kẻ tấn công không được phép loại bỏ challenge hoặc thay đổi method trong một request khác rồi dùng cùng code để đổi token.

Server cần từ chối:

- Token request không có verifier khi authorization code được phát hành với PKCE.
- Verifier không khớp challenge.
- Method không được hỗ trợ.
- Authorization request dùng `plain` khi policy chỉ chấp nhận `S256`.
- Token request cố đổi code thuộc giao dịch khác.
- Authorization code đã được sử dụng hoặc hết hạn.

Không được mặc định một giao dịch không có challenge là hợp lệ chỉ vì client được đánh dấu public trong registry; nếu policy yêu cầu PKCE, thiếu challenge phải bị từ chối ngay từ authorization request.

## 8. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Public client không gửi PKCE | Code bị đánh cắp có thể đổi thành token | Bắt buộc PKCE với public client |
| Dùng verifier cố định | Kẻ tấn công có thể biết hoặc tái sử dụng verifier | Sinh verifier ngẫu nhiên cho mỗi giao dịch |
| Dùng `plain` | Challenge tiết lộ verifier | Dùng `S256` |
| Sinh verifier bằng PRNG yếu | Có thể đoán verifier | Dùng CSPRNG |
| Đưa verifier lên URL/log | Bí mật bị lộ qua lịch sử, proxy hoặc telemetry | Chỉ gửi verifier ở token request qua TLS |
| Dùng một verifier cho nhiều request | Giao dịch có thể bị trộn hoặc replay | Một verifier cho mỗi transaction |
| Không gắn verifier với `state` | Callback có thể lấy nhầm verifier | Lưu theo transaction và kiểm tra state |
| Token endpoint bỏ qua verifier | PKCE chỉ còn hình thức | Server bắt buộc xác minh challenge |
| Chấp nhận verifier sai khi có lỗi parser | Code có thể bị đổi trái phép | Validate format và fail closed |
| Public app chứa client secret | Secret bị trích xuất | Không dựa vào client secret; dùng PKCE |
| Bỏ redirect URI exact matching | Code có thể bị gửi tới callback ngoài dự kiến | Đăng ký và so khớp URI chính xác |
| Bỏ OIDC nonce vì có PKCE | ID token có thể không được liên kết đúng request | Dùng nonce khi OIDC yêu cầu |
| Không tiêu thụ code nguyên tử | Code có thể bị đổi nhiều lần trong race | Atomic single-use code redemption |

## 9. Kiểm thử PKCE

Test phải chứng minh cả client và authorization server phối hợp đúng. Với test token endpoint, tạo authorization code fixture đã lưu challenge và method tương ứng.

### Ma trận test

| ID | Authorization request | Token request | Kết quả |
| --- | --- | --- | --- |
| P01 | Challenge S256 hợp lệ | Verifier tương ứng | Đổi code thành công |
| P02 | Challenge S256 hợp lệ | Verifier khác | Từ chối |
| P03 | Challenge S256 hợp lệ | Thiếu verifier | Từ chối |
| P04 | Không có challenge, client public bị policy yêu cầu PKCE | Không có verifier | Từ chối ngay ở authorization request |
| P05 | Challenge method không hỗ trợ | Verifier bất kỳ | Từ chối |
| P06 | Challenge method `plain` khi policy chỉ cho S256 | Verifier bằng challenge | Từ chối |
| P07 | Challenge hợp lệ của code A | Dùng verifier của code B | Từ chối |
| P08 | Challenge hợp lệ | Code đã được đổi trước đó | Từ chối |
| P09 | Challenge hợp lệ | Code hết hạn | Từ chối |
| P10 | Challenge hợp lệ | Client ID hoặc redirect URI không khớp | Từ chối |
| P11 | Hai token request cùng đổi một code | Cùng verifier | Chỉ một request thành công |
| P12 | Verifier quá ngắn, quá dài hoặc có ký tự ngoài tập cho phép | Verifier không hợp lệ | Từ chối |

### Unit test cho challenge

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class PkceTest {

    @Test
    void matchesRfc7636S256Example() throws Exception {
        String verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";

        assertEquals(
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            Pkce.createS256Challenge(verifier)
        );
    }

    @Test
    void challengeIsDeterministicForSameVerifier() throws Exception {
        String verifier = Pkce.createVerifier();

        assertEquals(
            Pkce.createS256Challenge(verifier),
            Pkce.createS256Challenge(verifier)
        );
    }

    @Test
    void differentVerifierProducesDifferentChallenge() throws Exception {
        String first = Pkce.createVerifier();
        String second = Pkce.createVerifier();

        assertNotEquals(
            Pkce.createS256Challenge(first),
            Pkce.createS256Challenge(second)
        );
    }

    @Test
    void verifierHasValidLength() {
        String verifier = Pkce.createVerifier();

        assertTrue(verifier.length() >= 43);
        assertTrue(verifier.length() <= 128);
    }

    @Test
    void verifierUsesUnreservedCharacters() {
        String verifier = Pkce.createVerifier();

        assertTrue(verifier.matches("^[A-Za-z0-9._~-]+$"));
    }
}
~~~

Test này kiểm tra helper tạo verifier/challenge. Nó chưa chứng minh authorization server lưu và xác minh challenge đúng. Cần thêm integration test qua authorization endpoint và token endpoint.

### Integration test cho token endpoint

Một test server có thể lưu authorization code fixture:

~~~text
authorization_code = code-123
client_id          = mobile-app
redirect_uri       = com.example.app://callback
code_challenge     = S256(verifier-expected)
code_challenge_method = S256
status             = ACTIVE
expires_at         = future timestamp
~~~

Sau đó gửi token request với verifier đúng, verifier sai và thiếu verifier. Với verifier sai hoặc thiếu, assert:

- HTTP response là lỗi OAuth phù hợp, thường `invalid_grant` cho authorization code/PKCE verification failure theo implementation.
- Không phát hành access token hoặc refresh token.
- Authorization code không được đánh dấu redeemed thành công.
- Không có session hoặc side effect nghiệp vụ.
- Event bảo mật ghi nhận lỗi theo policy mà không log verifier hoặc code nguyên văn.

Với hai request đồng thời dùng cùng code và verifier đúng, chỉ một request được phép redeem thành công. Thao tác kiểm tra code, xác minh PKCE và đánh dấu redeemed cần được thực hiện nguyên tử để tránh double redemption.

## 10. PKCE trong SPA, native app và confidential client

| Client | Cần PKCE? | Lưu ý |
| --- | --- | --- |
| SPA | Có | Không có client secret an toàn; bảo vệ verifier trước XSS |
| Native mobile app | Có | Dùng external browser và redirect URI phù hợp nền tảng |
| Desktop app | Có | Cùng vấn đề public distribution; bảo vệ callback và verifier |
| Backend web app confidential | Nên dùng | PKCE bổ sung bảo vệ code interception/injection ngoài client authentication |
| Service-to-service dùng client credentials | Không áp dụng cùng cách | Không có authorization code cần đổi; dùng client authentication phù hợp |

PKCE áp dụng cho Authorization Code Flow. Không thêm `code_challenge` vào Client Credentials Flow như một thay thế cho client authentication. Với luồng device authorization hoặc các grant khác, áp dụng biện pháp bảo vệ tương ứng với giao thức và threat model.

### Native app redirect URI

RFC 8252 mô tả các cách redirect URI cho native app, gồm private-use URI scheme, claimed HTTPS URI và loopback redirect cho ứng dụng desktop. Dù chọn loại nào, PKCE vẫn cần thiết để code bị chặn không thể đổi thành token nếu kẻ tấn công không có verifier.

Không đăng ký wildcard redirect URI rộng. Kiểm tra scheme, host, path và port theo loại redirect được phép; dùng browser hệ thống để giữ credential của IdP ngoài embedded webview khi thực hiện đăng nhập native.

## 11. Giới hạn của PKCE

PKCE bảo vệ authorization code trong giai đoạn exchange, nhưng không phải giải pháp cho mọi loại tấn công:

- Nếu verifier bị đánh cắp cùng với code, kẻ tấn công có thể hoàn tất exchange.
- XSS có thể đọc verifier nếu nó nằm trong vùng JavaScript truy cập được.
- Malware kiểm soát thiết bị có thể quan sát bộ nhớ hoặc callback.
- PKCE không thay thế kiểm tra chữ ký, issuer, audience, thời hạn và token type ở resource server.
- PKCE không thay thế refresh token rotation, sender-constrained token hoặc secure token storage.
- PKCE không tự ngăn CSRF ở authorization response nếu client không xác minh `state` theo đúng thiết kế.
- PKCE không xác thực danh tính người dùng; đó là nhiệm vụ của authentication flow và ID token validation trong OIDC.

Vì vậy, dùng PKCE cùng redirect URI validation, `state`, OIDC `nonce` khi cần, TLS, token validation, bảo vệ verifier và chính sách vòng đời token.

## 12. Checklist triển khai production

- [ ] Public client dùng Authorization Code Flow với PKCE.
- [ ] Authorization server yêu cầu PKCE đối với public client.
- [ ] Client tạo verifier mới bằng CSPRNG cho từng giao dịch.
- [ ] Verifier dài 43–128 ký tự và dùng tập ký tự hợp lệ.
- [ ] Challenge được tính bằng SHA-256 và Base64URL không padding.
- [ ] Authorization request gửi `code_challenge_method=S256`.
- [ ] Verifier chỉ gửi ở token request qua TLS.
- [ ] Server lưu challenge/method cùng authorization code.
- [ ] Token endpoint bắt buộc verifier và xác minh challenge.
- [ ] Không downgrade từ PKCE sang không PKCE.
- [ ] Code gắn với client và redirect URI, hết hạn ngắn và dùng một lần.
- [ ] `state` vẫn được kiểm tra; OIDC `nonce` vẫn được xác minh khi dùng OIDC.
- [ ] Verifier được bảo vệ trong browser/native app và xóa sau giao dịch.
- [ ] Không nhúng client secret dùng chung trong public app.
- [ ] Có test verifier đúng/sai/thiếu, challenge method, code replay và concurrency.
- [ ] Log, metric và trace không chứa verifier, authorization code hoặc token.

## Ghi nhớ

- Public client không thể giữ một client secret được nhúng trong ứng dụng.
- PKCE ràng buộc authorization code với một verifier ngẫu nhiên chỉ client đang thực hiện giao dịch biết.
- Dùng `S256`; không dùng verifier cố định và không để verifier lộ trong URL hoặc log.
- Authorization server phải lưu challenge với code và xác minh verifier tại token endpoint.
- `state`, OIDC `nonce`, redirect URI validation và PKCE bảo vệ các khía cạnh khác nhau; cần phối hợp.
- PKCE giảm nguy cơ code interception, nhưng không thay thế token validation, secure storage hoặc bảo vệ thiết bị.

### Tiêu chuẩn tham khảo

- **RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients:** định nghĩa verifier, challenge và S256.
- **RFC 8252 — OAuth 2.0 for Native Apps:** thực hành OAuth cho ứng dụng native và yêu cầu PKCE.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** khuyến nghị hiện hành về PKCE và bảo vệ authorization code.
- **RFC 6749 — OAuth 2.0 Authorization Framework:** Authorization Code Grant và token endpoint.
- **OpenID Connect Core 1.0:** `nonce`, ID token và xác minh authentication response.
