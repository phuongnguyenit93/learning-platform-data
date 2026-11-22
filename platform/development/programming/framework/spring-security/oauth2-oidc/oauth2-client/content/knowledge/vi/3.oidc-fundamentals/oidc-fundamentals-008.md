# 3.8. State, nonce và PKCE trong luồng đăng nhập

Khi một ứng dụng Spring Security dùng **OpenID Connect (OIDC)** để đăng nhập qua nhà cung cấp danh tính, trình duyệt thường được chuyển hướng từ ứng dụng sang OpenID Provider (OP), rồi quay lại ứng dụng cùng một **authorization code**. Một câu hỏi quan trọng xuất hiện: làm sao ứng dụng biết callback này thuộc về yêu cầu đăng nhập mà chính nó đã khởi tạo, ID Token nhận được tương ứng với lần đăng nhập đó, và authorization code không bị một bên khác sử dụng?

Ba cơ chế bổ sung cho nhau để trả lời câu hỏi đó:

- **`state`**: liên kết **authorization response** với **authorization request** ban đầu; là một thành phần bảo vệ luồng chuyển hướng khỏi CSRF/login CSRF.
- **`nonce`**: liên kết **ID Token** với **lần yêu cầu xác thực OIDC**, giúp phát hiện việc dùng lại hoặc tráo ID Token trong những tình huống tấn công phù hợp.
- **PKCE (Proof Key for Code Exchange)**: buộc bên đổi **authorization code** tại token endpoint phải chứng minh rằng mình sở hữu **`code_verifier`** đã liên kết với authorization request.

Không cơ chế nào trong ba cơ chế trên thay thế hai cơ chế còn lại. Bài học đặt chúng trong **OIDC Authorization Code Flow** của ứng dụng web Spring Boot sử dụng Spring Security và giải thích cách chúng đi qua HTTP redirect, session và back-channel.

## 1. Vì sao cần ba lớp bảo vệ?

Giả sử ứng dụng `https://app.example.com` cung cấp nút “Đăng nhập”. Khi nhấn nút, người dùng được chuyển đến OP `https://login.example.com`. OP xác thực người dùng rồi điều hướng về callback:

```http
GET /login/oauth2/code/academy?code=AUTHORIZATION_CODE&state=STATE_RETURNED HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_ID
```

Các rủi ro cần xét không giống nhau:

| Rủi ro | Vấn đề cần giải quyết | Cơ chế trực tiếp liên quan |
| --- | --- | --- |
| Callback giả mạo hoặc callback không thuộc lần đăng nhập đã bắt đầu | Trình duyệt bị dẫn vào endpoint callback với response do bên khác khởi tạo | `state`, đối chiếu với authorization request đã lưu |
| ID Token bị dùng lại hoặc tráo trong quá trình xác thực | Client nhận ID Token hợp lệ về chữ ký nhưng không tương ứng với lần yêu cầu xác thực hiện tại | `nonce`, kiểm tra trong ID Token cùng các kiểm tra OIDC khác |
| Authorization code bị chặn/cướp đoạt | Bên có code thử gửi request đến token endpoint để lấy token | PKCE: `code_challenge` + `code_verifier` |
| Token được cấp bởi sai issuer hoặc dành cho sai client | Chữ ký hợp lệ nhưng sai nguồn hoặc sai đối tượng sử dụng | Xác minh `iss`, `aud`, khóa chữ ký và ràng buộc nhà cung cấp |
| Một website khác lợi dụng browser đang có cookie để gửi request thay đổi dữ liệu | **CSRF của ứng dụng web** ngoài callback OIDC | CSRF token cho các request thay đổi trạng thái, kiểm soát cookie và origin |

Điểm cuối cùng rất quan trọng: **`state` bảo vệ việc tương quan giữa các thông điệp của luồng OAuth2/OIDC**, còn cơ chế **CSRF của Spring Security** bảo vệ nhiều request nghiệp vụ sử dụng session cookie. Không được tắt `csrf()` chỉ vì đã có `state`.

## 2. Toàn cảnh Authorization Code Flow với `state`, `nonce` và PKCE

Trong ví dụ này, **Spring application là OAuth 2.0 Client / OIDC Relying Party**, OP vừa là Authorization Server vừa là bên phát hành ID Token; browser là user agent. Luồng dùng HTTPS trên các kết nối công khai.

```mermaid
sequenceDiagram
    autonumber
    actor B as Browser
    participant C as Spring Security OIDC Client
    participant P as OpenID Provider
    B->>C: GET /oauth2/authorization/academy
    Note over C: Tạo state S, nonce N, verifier V<br/>challenge Cc = BASE64URL(SHA256(V))<br/>Lưu S, N, V với yêu cầu đăng nhập
    C-->>B: 302 Location: OP /authorize?...<br/>state=S, nonce=N, code_challenge=Cc
    B->>P: GET /authorize?... qua HTTPS
    P->>B: Xác thực người dùng và consent nếu cần
    P-->>B: 302 /login/oauth2/code/academy?code=CODE&state=S
    B->>C: GET callback + cookie phiên
    Note over C: Đọc yêu cầu đã lưu; kiểm tra state
    C->>P: POST /token: code=CODE, code_verifier=V<br/>+ client authentication khi áp dụng
    Note over P: So sánh challenge của V<br/>với challenge đã gắn với CODE
    P-->>C: access_token + id_token (+ các trường khác)
    Note over C: Xác minh ID Token: chữ ký, iss, aud,<br/>hạn dùng, nonce=N và các quy tắc OIDC
    C-->>B: Tạo phiên đăng nhập ứng dụng; chuyển đến trang đích
    B->>C: GET /account + session cookie
    C-->>B: Nội dung dành cho người đã xác thực
```

Thứ tự kiểm tra có ý nghĩa:

1. Trước khi redirect, client **tạo và lưu** các dữ liệu thuộc một lần đăng nhập.
2. Khi browser trở về, client **đối chiếu `state`** và tìm đúng authorization request ban đầu.
3. Khi backend đổi code lấy token, OP **xác minh PKCE**.
4. Khi client nhận ID Token, client **xác minh token và `nonce`**.
5. Chỉ sau khi xác thực thành công, Spring Security mới thiết lập `Authentication`/`SecurityContext` cho người dùng.

`state` và `nonce` xuất hiện trên authorization request ở trình duyệt, nhưng **`code_verifier` phải được client giữ để gửi qua token request**, không có trong URL điều hướng đến OP.

## 3. `state`: gắn callback với yêu cầu đăng nhập ban đầu

### 3.1. `state` làm việc như thế nào?

`state` là giá trị do client sinh ra cho authorization request. Client đưa nó vào redirect tới OP, đồng thời giữ thông tin tương ứng phía ứng dụng.

Ví dụ request đến OP (rút gọn):

```http
GET /authorize?response_type=code
    &client_id=academy-web
    &redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Facademy
    &scope=openid%20profile
    &state=RANDOM_STATE
    &nonce=RANDOM_NONCE
    &code_challenge=CODE_CHALLENGE
    &code_challenge_method=S256 HTTP/1.1
Host: login.example.com
```

Sau khi xác thực, OP trả về:

```http
HTTP/1.1 302 Found
Location: https://app.example.com/login/oauth2/code/academy?code=SHORT_LIVED_CODE&state=RANDOM_STATE
```

Ứng dụng không nên chỉ kiểm tra “callback có `state` hay không”. Nó phải biết **`state` nào được phát ra cho authorization request đang chờ**, so sánh chính xác và sử dụng thông tin tương quan đúng một lần. Nếu state sai, thiếu hoặc không tìm thấy yêu cầu tương ứng, **luồng xác thực phải bị từ chối**.

Một ví dụ về **login CSRF**: kẻ tấn công tạo authorization response gắn với tài khoản của họ rồi cố buộc browser của nạn nhân gửi response đó cho ứng dụng. Nếu client chỉ nhận code và tạo session mà không gắn response với yêu cầu của nạn nhân, nạn nhân có thể bị đăng nhập nhầm vào tài khoản do kẻ tấn công kiểm soát. `state` được ràng buộc với browser/session khởi tạo luồng sẽ giúp chặn kiểu tấn công này.

### 3.2. Tạo, lưu, kiểm tra và tiêu thụ `state`

Một thiết kế đúng cần:

- **Khó đoán:** dùng bộ sinh ngẫu nhiên an toàn về mật mã; không dùng timestamp, số tăng dần, username hoặc chuỗi cố định.
- **Mới cho mỗi authorization request:** không dùng chung `state` cho mọi phiên đăng nhập.
- **Gắn với ngữ cảnh browser/client:** lưu một bản ghi authorization request ở server và nhận diện ngữ cảnh đó qua session cookie hoặc cơ chế tương đương đã được bảo vệ.
- **Có thời hạn ngắn:** yêu cầu chờ callback không nên tồn tại vô thời hạn.
- **Đối chiếu và tiêu thụ đúng lần:** hoàn tất hoặc thất bại thì dọn dữ liệu tạm phù hợp; không tái sử dụng response để đăng nhập lại.

`state` **không phải là quyền truy cập**, **không phải access token** và không chứng minh danh tính người dùng. Giá trị xuất hiện trong URL, nên không được xem là một bí mật có thể dùng thay cho token. Tính bảo vệ đến từ việc nó khó đoán và được **đối chiếu với trạng thái đăng nhập do client lưu**.

Nếu cần chuyển người dùng về trang đã yêu cầu trước khi đăng nhập, hãy dùng cơ chế lưu request an toàn của framework hoặc chỉ cho phép URL nội bộ đã kiểm tra. **Đừng ghép trực tiếp một URL tùy ý do người dùng cung cấp vào `state` rồi redirect tới URL đó**, vì có thể mở ra lỗ hổng open redirect. `state` có thể là khóa tra cứu một bản ghi phía server thay vì bản thân dữ liệu điều hướng.

### 3.3. `state` chưa giải quyết mọi vấn đề

So khớp state giúp client nhận ra callback thuộc luồng đang chờ, nhưng **không thay**:

- PKCE để bảo vệ việc đổi authorization code.
- Kiểm tra issuer và audience để chống nhận token từ nhầm OP/client.
- Xác minh ID Token, gồm `nonce` nếu đã gửi.
- Các biện pháp chống CSRF cho request nghiệp vụ của ứng dụng.

Với client liên kết nhiều OP, phải ràng buộc mỗi request với **đúng provider dự kiến**. Việc xác thực issuer và các biện pháp phòng *authorization server mix-up* vẫn cần thiết; `state` tự nó không đủ.

## 4. `nonce`: gắn ID Token với lần yêu cầu xác thực OIDC

### 4.1. `nonce` khác `state` ở vị trí kiểm tra

`nonce` là giá trị ngẫu nhiên do **OIDC Client** tạo và đưa vào authorization request:

```http
GET /authorize?...&scope=openid%20profile&nonce=RANDOM_NONCE HTTP/1.1
Host: login.example.com
```

Khi nhận tham số `nonce`, OP phải đưa giá trị này vào **claim `nonce` của ID Token** phát hành cho yêu cầu đó. Client so sánh claim nhận được với nonce đã lưu trước khi chấp nhận ID Token.

Ví dụ payload ID Token *sau khi giải mã* (chữ ký và dữ liệu chỉ minh họa):

```json
{
  "iss": "https://login.example.com",
  "sub": "user-734",
  "aud": "academy-web",
  "iat": 1794800000,
  "exp": 1794800600,
  "nonce": "RANDOM_NONCE"
}
```

Điều kiện cơ bản:

```text
nonce_đã_gửi_cho_yêu_cầu == nonce_claim_trong_ID_Token
```

Với OIDC Authorization Code Flow, `nonce` không bắt buộc trong mọi request theo đặc tả OIDC Core, nhưng **nếu client đã gửi nonce thì phải xác minh giá trị claim tương ứng**. Trong thực hành OIDC hiện đại, dùng nonce đúng cách là biện pháp phòng vệ hữu ích; đừng mặc định rằng một token hợp lệ về chữ ký đã gắn với request hiện tại.

### 4.2. `nonce` giúp chống kiểu tấn công nào?

Một ID Token có thể được OP ký đúng và còn hạn nhưng **được tạo cho một lần xác thực khác**. Nếu ứng dụng không kiểm tra ràng buộc giữa ID Token và authorization request, một bên tấn công có thể tìm cách sử dụng lại hoặc tráo ID Token trong một số luồng/xử lý lỗi. `nonce` làm ID Token gắn với lần đăng nhập đã khởi tạo.

Ví dụ:

1. Client bắt đầu login A và gửi `nonce=N_A`.
2. Một ID Token khác có `nonce=N_B` được đưa vào quá trình xử lý login A.
3. Dù chữ ký, `iss` và `exp` của token kia đều hợp lệ, kiểm tra `N_A != N_B` buộc client **từ chối ID Token**.

**Nonce không phải là mật khẩu.** Browser có thể nhìn thấy nonce trong URL authorization request. Nó cần khó đoán và mới cho từng request; khả năng bảo vệ dựa vào việc OP phản ánh giá trị đó trong một ID Token được xác minh và client kiểm tra ràng buộc đúng phiên.

### 4.3. Ngoài `nonce`, ID Token cần được kiểm tra những gì?

Một ID Token đúng nonce vẫn **chưa đủ**. OIDC Client cần xác minh theo luồng và cấu hình thực tế, gồm tối thiểu các điều kiện thích hợp:

| Trường/kiểm tra | Ý nghĩa |
| --- | --- |
| **Chữ ký / thuật toán** | ID Token phải được xác minh bằng khóa và thuật toán cho phép của OP tin cậy. |
| **`iss`** | Issuer phải khớp nhà cung cấp danh tính đã cấu hình cho request. |
| **`aud`** | Audience phải bao gồm `client_id` của OIDC Client. |
| **`azp`** | Khi có điều kiện phát sinh yêu cầu kiểm tra authorized party, phải đánh giá theo quy tắc OIDC. |
| **`exp`, `iat`** | Token chưa hết hạn và các ràng buộc thời gian khác được áp dụng phù hợp. |
| **`nonce`** | Nếu authorization request có nonce, claim phải có và khớp giá trị đã gửi. |
| **`auth_time`, `acr`, `amr`** | Kiểm tra thêm khi nghiệp vụ hoặc request xác thực yêu cầu độ mới/độ mạnh xác thực cụ thể. |

Không dùng **ID Token làm access token** để gọi API chỉ vì nó chứa thông tin người dùng. ID Token xác thực sự kiện đăng nhập cho client; **access token** phục vụ truy cập tài nguyên theo chính sách của API.

## 5. PKCE: ràng buộc authorization code với bên đã khởi tạo flow

### 5.1. Nếu không có PKCE, code có thể bị đánh cắp rồi đổi lấy token

Authorization Code Flow tách làm hai bước:

1. Browser quay lại client với một **authorization code** có thời hạn ngắn.
2. Client dùng code đó để gọi **token endpoint** và nhận token.

Code là một giá trị nhạy cảm: bên nhận được code có thể thử đổi nó thành token. Client authentication, redirect URI binding, HTTPS và code dùng một lần là những bảo vệ quan trọng, nhưng **PKCE bổ sung bằng chứng mật mã để liên kết authorization request với token request**.

PKCE vốn được thiết kế để bảo vệ public client (như native app) trước việc chặn authorization code. Hướng dẫn bảo mật OAuth 2.0 hiện đại khuyến nghị rộng rãi PKCE với Authorization Code Flow, gồm cả nhiều confidential client. Tùy provider, PKCE có thể là yêu cầu bắt buộc.

### 5.2. `code_verifier` và `code_challenge`

Client tạo một **`code_verifier`** ngẫu nhiên, dài và khó đoán. Đặc tả PKCE quy định chuỗi verifier dài **43–128 ký tự** thuộc tập ký tự URL-safe không dành riêng. Cách phổ biến là lấy **32 byte ngẫu nhiên** rồi Base64URL không padding: kết quả có 43 ký tự.

Với phương thức **S256**:

```text
code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))
code_challenge_method = S256
```

Client gửi **`code_challenge`** và `code_challenge_method` trong authorization request, nhưng giữ **`code_verifier`** để dùng ở token request.

```text
Trên client khi bắt đầu:
  verifier V  --SHA-256 + Base64URL-->  challenge C

Trên authorization endpoint:
  OP gắn challenge C và method S256 với authorization code

Trên token endpoint:
  Client gửi code + verifier V
  OP tính BASE64URL(SHA256(ASCII(V))) và so sánh với C
  Khớp + các điều kiện token request khác => có thể cấp token
```

Điều này làm cho một kẻ chỉ **lấy được authorization code** nhưng **không có verifier** khó đổi code lấy token, dù đã biết challenge trong URL. Với hàm băm và verifier đủ entropy, việc suy ngược từ challenge không khả thi trong điều kiện thực tế.

### 5.3. Authorization request và token request có gì khác?

**Front-channel qua browser:** 

```http
GET /authorize?response_type=code
    &client_id=academy-web
    &redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Facademy
    &scope=openid
    &state=S
    &nonce=N
    &code_challenge=C
    &code_challenge_method=S256 HTTP/1.1
Host: login.example.com
```

**Back-channel từ backend tới OP:**

```http
POST /token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=AUTH_CODE&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Facademy&code_verifier=V
```

Ví dụ POST được rút gọn: **confidential client** còn phải thực hiện **client authentication** bằng phương thức OP hỗ trợ (ví dụ `client_secret_basic`, `private_key_jwt`). `code_verifier` không thay thế client authentication, và client secret không thay thế PKCE.

Điểm cần để ý là **`code_verifier` tuyệt đối không đặt vào authorization redirect**, vì browser và các thành phần thấy URL front-channel không phải nơi cần biết verifier.

### 5.4. Cách sinh verifier/challenge minh họa bằng Java

Khi tìm hiểu thuật toán, có thể tự tính để hiểu mối quan hệ; trong ứng dụng Spring Security thực tế, **ưu tiên dùng chức năng PKCE của framework**, tránh tự cài lại state/token exchange.

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public final class PkceDemo {
    private static final SecureRandom RANDOM = new SecureRandom();

    private PkceDemo() {}

    public static String newVerifier() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }

    public static String challengeS256(String verifier)
            throws NoSuchAlgorithmException {
        byte[] hash = MessageDigest.getInstance("SHA-256")
                .digest(verifier.getBytes(StandardCharsets.US_ASCII));
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(hash);
    }

    public static void main(String[] args) throws Exception {
        String verifier = newVerifier();
        String challenge = challengeS256(verifier);

        System.out.println("S256 challenge: " + challenge);
        // Không ghi verifier ra log trong ứng dụng thực tế.
    }
}
```

Verifier dài 43 ký tự Base64URL không padding khi đầu vào là 32 byte. Challenge S256 cũng có 43 ký tự. **Không dùng `Math.random()`, thời gian hệ thống hay chuỗi cố định** để sinh verifier. Việc chỉ biết challenge không được coi là đủ quyền đổi code lấy token.

### 5.5. Vì sao ưu tiên `S256`?

PKCE hỗ trợ tên phương thức `plain` trong đặc tả cho trường hợp tương thích đặc biệt, nhưng `plain` công khai verifier dưới dạng challenge và không đem lại cùng mức bảo vệ khi authorization request bị lộ. **S256 là lựa chọn nên sử dụng** nếu được OP hỗ trợ; các deployment hiện đại thường yêu cầu nó.

Client không nên im lặng chuyển sang luồng không PKCE khi gặp lỗi trao đổi với OP. **Bảo vệ phải được cả client và Authorization Server thực thi**: chỉ gửi `code_challenge` từ phía client mà token endpoint không ràng buộc code với challenge thì chưa tạo ra bảo vệ.

### 5.6. PKCE không bảo vệ khỏi mọi rủi ro

PKCE không tự ngăn:

- Kẻ tấn công đồng thời lấy được **code lẫn verifier**.
- XSS hoặc server compromise làm lộ dữ liệu lưu trong client.
- Dùng ID Token sai issuer/audience/nonce.
- CSRF cho các thao tác nghiệp vụ sau khi đăng nhập.
- Việc OP phát token không đúng audience/scope hoặc API kiểm tra token sai.

Vì vậy PKCE là **một lớp ràng buộc bổ sung**, phải triển khai cùng HTTPS, client authentication khi phù hợp, kiểm tra `state` và OIDC token validation.

## 6. Phân biệt nhanh ba giá trị

| Tiêu chí | `state` | `nonce` | PKCE `code_verifier` / `code_challenge` |
| --- | --- | --- | --- |
| Ai sinh? | OAuth2/OIDC Client | OIDC Client | OAuth2 Client |
| Gửi trong authorization request? | **state** | **nonce** | **challenge + method**, không gửi verifier |
| Gửi/kiểm tra khi callback? | `state` được trả lại cùng code và so với bản đã lưu | Không dùng giá trị nonce từ callback thay cho bản đã lưu | Không kiểm tra verifier ở callback browser |
| Có trong ID Token? | Không bắt buộc/không dùng cho mục tiêu này | **Claim nonce** nếu client đã gửi | Không |
| Gửi tại token endpoint? | Thông thường không | Thông thường không | **`code_verifier`** |
| Bên kiểm tra chính? | Client | Client khi nhận ID Token | Authorization Server tại token endpoint |
| Mối đe dọa trọng tâm | Callback/login CSRF, liên kết request–response | ID Token substitution/replay, liên kết ID Token–request | Authorization code interception/injection theo ngữ cảnh |
| Lưu ý | Phải khó đoán và ràng buộc đúng phiên | Phải so claim trong ID Token sau khi xác minh token | Verifier khó đoán, dùng đúng một request và không lộ front-channel |

**Ghi nhớ theo thời điểm xác minh:** `state` được kiểm tra **khi trình duyệt quay về**, PKCE được kiểm tra **khi đổi authorization code lấy token**, còn `nonce` được kiểm tra **khi xác thực ID Token**.

## 7. Spring Security lưu và xử lý ba giá trị ở đâu?

Trong ứng dụng **Spring MVC/Servlet** sử dụng `oauth2Login()`, Spring Security có sẵn nhiều cơ chế cần thiết. Không cần tự viết endpoint callback, tự gọi token endpoint hay tự giải mã ID Token để xử lý luồng đăng nhập cơ bản.

### 7.1. Các thành phần trong luồng login

| Thành phần | Việc đảm nhiệm |
| --- | --- |
| `OAuth2AuthorizationRequestRedirectFilter` | Nhận điểm bắt đầu login, tạo authorization request và redirect đến Authorization Server. |
| `OAuth2AuthorizationRequestResolver` / `DefaultOAuth2AuthorizationRequestResolver` | Dựng request gồm client registration, redirect URI, scope, state và các tham số tùy biến như PKCE. |
| `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` | Lưu authorization request trước redirect để callback có thể tìm lại thông tin tương quan. |
| `HttpSessionOAuth2AuthorizationRequestRepository` | Triển khai repository thông dụng/default, giữ request OAuth2 trong HTTP session. |
| `OAuth2LoginAuthenticationFilter` | Nhận callback `/login/oauth2/code/{registrationId}` và khởi động bước xác thực authorization code. |
| Các authentication provider của OAuth2/OIDC login | Trao đổi code lấy token, xác minh thông tin và tạo principal/`Authentication` theo giao thức. |
| `SecurityContext` / session repository | Duy trì phiên đăng nhập của ứng dụng sau khi xác thực thành công. |

Ở cấu hình mặc định, browser truy cập:

```text
GET /oauth2/authorization/academy
```

Sau đó nhận callback:

```text
GET /login/oauth2/code/academy?code=...&state=...
```

Spring Security dùng thông tin trong authorization request đã lưu để đối chiếu callback. Với request OIDC, các bước xử lý ID Token áp dụng các quy tắc OIDC, trong đó có nonce nếu nonce được sử dụng. Giá trị PKCE verifier được giữ trong ngữ cảnh của authorization request để gửi tại token request khi PKCE được bật.

**Không nên viết custom callback controller** trùng với `/login/oauth2/code/{registrationId}` trừ khi có lý do kiến trúc rõ ràng; dễ vô tình bỏ qua các bước ràng buộc của framework.

### 7.2. Ví dụ cấu hình một OIDC Client

Giả sử OP hỗ trợ OIDC discovery và client đã được đăng ký với callback tương ứng.

**Dependency Maven** (ứng dụng Spring Boot có dependency management):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
```

**`application.yml`**:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          academy:
            provider: academy-provider
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          academy-provider:
            issuer-uri: https://login.example.com/realms/academy
```

Đây là domain minh họa; thay `issuer-uri` bằng issuer thực tế được OP công bố. `scope=openid` là dấu hiệu quan trọng cho luồng OIDC. Cần cấu hình client secret từ môi trường hoặc secret store; không commit bí mật vào Git.

**`SecurityFilterChain`** cơ bản:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

Cấu hình này để Spring Security quản lý redirect, callback, validation và session theo các tính năng tích hợp. **Khả năng bật PKCE mặc định có thể tùy thuộc phiên bản Spring Security và cách đăng ký client** (public/confidential). Không nên suy ra PKCE đang hoạt động chỉ từ việc `oauth2Login()` đăng nhập thành công; cần xác định cấu hình hoặc nhìn vào authorization request xem có `code_challenge`/`code_challenge_method=S256` hay không.

### 7.3. Chủ động bật PKCE bằng request customizer

Với Spring Security phiên bản có `OAuth2AuthorizationRequestCustomizers.withPkce()`, có thể áp dụng customizer cho authorization request resolver, kể cả khi client có secret:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OAuth2PkceConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        var resolver = new DefaultOAuth2AuthorizationRequestResolver(
                registrations, "/oauth2/authorization");

        resolver.setAuthorizationRequestCustomizer(
                OAuth2AuthorizationRequestCustomizers.withPkce());

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth2 -> oauth2
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)));

        return http.build();
    }
}
```

Ví dụ này là **cấu hình thay thế** `SecurityConfig` ở phần trước, không đặt cả hai bean `SecurityFilterChain` có cùng phạm vi mặc định vào một ứng dụng. Điều kiện sử dụng là Spring Security/OP hỗ trợ PKCE cho client đó. Customizer cho Spring Security tạo và giữ verifier cùng authorization request, gửi challenge đi và dùng verifier khi đổi code; không cần tự tạo param bằng JavaScript.

Trong ứng dụng thực, những tùy biến cho authorization request như `prompt`, `login_hint`, scope bổ sung hoặc param của OP cần được thiết kế sao cho **không vô hiệu hóa các xử lý mặc định cho `state`, `nonce` và PKCE**. Nếu thay hẳn resolver/repository, phải giữ đầy đủ các ràng buộc bảo mật tương ứng.

### 7.4. Nơi dữ liệu được giữ và mối liên hệ với session

Với `HttpSessionOAuth2AuthorizationRequestRepository` mặc định, Spring lưu authorization request tạm ở HTTP session. Browser lưu session cookie (thường là `JSESSIONID`), rồi gửi lại khi truy cập callback.

```text
Browser                           Spring application
   |                                   |
   | GET /oauth2/authorization/...     |
   |---------------------------------->|
   |                                   | Lưu yêu cầu tạm trong session:
   |                                   | state, thông tin nonce/PKCE khi dùng
   |<----------------------------------|
   | 302 Location: OP + Set-Cookie     |
   |                                   |
   | (đi qua OP, quay lại callback)    |
   |---------------------------------->|
   | GET /login/oauth2/code/...?code...|
   | Cookie: JSESSIONID                |
   |                                   | Tìm lại yêu cầu ban đầu
   |                                   | Đối chiếu state, tiếp tục đổi code
```

Nếu browser không gửi lại cookie sau redirect, Spring có thể không tìm được authorization request đã lưu dù `state` trong URL trông đúng. Nguyên nhân hay gặp: cookie domain/path không đúng, `Secure`/HTTPS hoặc TLS proxy chưa cấu hình tốt, chính sách `SameSite`, session hết hạn, chuyển request sang instance không chia sẻ session, hoặc nhiều flow đăng nhập đồng thời làm mất thông tin lưu tạm trong một cấu hình cụ thể.

**`SameSite=Lax` thường tương thích với top-level GET redirect callback**; nếu provider dùng response mode `form_post`, cần đánh giá lại hành vi cookie cross-site và bảo vệ CSRF phù hợp. Không bật `SameSite=None` một cách máy móc mà chưa hiểu mục đích và hạ tầng triển khai.

## 8. Theo dõi một lần đăng nhập để thấy rõ ba giá trị

Xét chuỗi request minh họa, trong đó:

- `S_A`: state cho lần đăng nhập A.
- `N_A`: nonce cho lần đăng nhập A.
- `V_A`: verifier được giữ ở phía ứng dụng.
- `C_A`: challenge được tính từ `V_A`.
- `CODE_A`: authorization code ngắn hạn, một lần sử dụng.

**Bước 1 — Bắt đầu**

```text
GET https://app.example.com/oauth2/authorization/academy

Spring lưu tạm trong session:
  state         = S_A
  nonce         = N_A
  code_verifier = V_A
  provider      = academy-provider
  redirect_uri  = https://app.example.com/login/oauth2/code/academy
```

**Bước 2 — Chuyển hướng tới OP**

```text
GET https://login.example.com/authorize
  ?response_type=code
  &client_id=academy-web
  &redirect_uri=...
  &scope=openid%20profile
  &state=S_A
  &nonce=N_A
  &code_challenge=C_A
  &code_challenge_method=S256
```

Browser có thể nhìn thấy `S_A`, `N_A` và `C_A`; nó **không cần biết `V_A`**.

**Bước 3 — Callback**

```text
GET https://app.example.com/login/oauth2/code/academy
  ?code=CODE_A
  &state=S_A
```

Client đọc authorization request đã lưu, so sánh state và kiểm tra request gắn với provider đã chọn. Nếu URL trả `state=S_B` hoặc browser không còn session chứa `S_A`, callback phải bị từ chối.

**Bước 4 — Token request**

```text
POST https://login.example.com/token

grant_type=authorization_code
code=CODE_A
redirect_uri=https://app.example.com/login/oauth2/code/academy
code_verifier=V_A
(+ client authentication nếu áp dụng)
```

OP tính lại challenge từ `V_A` rồi đối chiếu với `C_A` đã gắn với `CODE_A`. Nếu verifier bị đổi sang `V_B`, OP phải từ chối yêu cầu đổi code.

**Bước 5 — Xác minh ID Token**

OP trả ID Token có `nonce=N_A`. Spring xác minh đầy đủ ID Token và so `N_A` với nonce đã lưu. Nếu token có `nonce=N_B`, ID Token không thuộc lần đăng nhập A và phải bị từ chối.

**Bước 6 — Thiết lập đăng nhập**

Sau khi xác thực hoàn tất, ứng dụng tạo hoặc cập nhật session đăng nhập. Dữ liệu tương quan tạm của luồng OAuth2 được tiêu thụ/dọn phù hợp. Request nghiệp vụ sau đó thường dựa vào session của ứng dụng; browser **không cần gửi lại `state`, `nonce` hoặc `code_verifier`** ở mỗi lần vào trang.

## 9. Tình huống lỗi và cách khoanh vùng

| Quan sát | Cơ chế cần nhìn trước | Nguyên nhân thường gặp |
| --- | --- | --- |
| Callback báo `invalid_state` hoặc không tìm được request tương ứng | `state` + lưu trữ session | Cookie không được gửi, session hết hạn, callback quay sai host, session không chia sẻ giữa instance, auth request bị ghi đè. |
| Token endpoint trả `invalid_grant` | PKCE hoặc các điều kiện của authorization code | Verifier sai/thiếu, redirect URI không khớp, code hết hạn, code đã dùng, code thuộc client khác. |
| OP nói bắt buộc `code_challenge` | PKCE trên authorization request | Client chưa bật PKCE hoặc request customizer không được áp dụng đúng chain/resolver. |
| ID Token bị từ chối vì `nonce` | OIDC nonce binding | Nonce trong token thiếu/khác, lưu sai ngữ cảnh request hoặc cấu hình OP có vấn đề. |
| ID Token hợp chữ ký nhưng bị từ chối vì `iss`/`aud` | OIDC token validation | Sai issuer, client ID, OP registration hoặc metadata/khóa ký. |
| Login qua OP thành công nhưng quay lại ứng dụng và login tiếp | Session/cookie | Browser mất cookie hoặc SecurityContext/session không được duy trì sau login. |
| Một tab đăng nhập thành công, tab khác báo state sai | Nhiều request đồng thời | Authorization request repository/configuration không giữ được nhiều luồng đang chờ theo thiết kế; cần xử lý concurrency có chủ đích. |
| Callback hợp lệ bị lỗi chỉ sau khi đặt app sau reverse proxy | Redirect URI, TLS, cookies | `X-Forwarded-Proto` / `Forwarded`, external URL, cookie `Secure` hoặc host public chưa thống nhất. |

Đối với `invalid_grant`, **không kết luận ngay rằng PKCE sai**: theo OAuth2, nhiều lỗi khác nhau có thể được OP gộp vào cùng mã. Xem log phía OP ở mức không lộ token, so cấu hình client, hạn code và redirect URI; nếu cần quan sát token request, hãy che các secret và credential.

### 9.1. Kiểm tra request trong trình duyệt và phía server

Trong môi trường học tập có thể theo dõi luồng bằng Network tab của developer tools:

1. Mở `/oauth2/authorization/academy`, bật **Preserve log** để nhìn thấy redirect.
2. Kiểm tra URL tới OP có `state`, `nonce` (khi dùng) và `code_challenge_method=S256` / `code_challenge` không.
3. Quan sát callback chứa `code` và `state` tương ứng.
4. Nhớ rằng **token request thường chạy server-to-server**, nên không hiện trong Network tab của browser. Cần tracing/log được kiểm soát ở backend để xác định nó có diễn ra.
5. Sau callback thành công, thử truy cập một trang đã bảo vệ để hiểu mối liên hệ với session cookie.

**Giữ kín dữ liệu quan sát được**: không đăng ảnh chụp đầy đủ URL callback, session cookie, token, `client_secret` hoặc `code_verifier` lên issue/public chat. Authorization code dùng một lần nhưng vẫn là credential nhạy cảm trong thời gian còn hiệu lực.

### 9.2. Những “cách sửa nhanh” sai hướng

- **Bỏ so `state`** để callback thành công: mất ràng buộc response–request.
- **Tắt PKCE** vì OP từ chối `code_verifier`: cần kiểm tra xem client gửi challenge/verifier nhất quán và OP có hỗ trợ `S256` không.
- **Bỏ kiểm tra `nonce`** để nhận ID Token: biến mất lớp liên kết ID Token với phiên xác thực.
- **Tắt CSRF toàn ứng dụng** khi login lỗi: nhầm bảo vệ callback với bảo vệ request nghiệp vụ dùng cookie.
- **Tắt TLS certificate verification** vì token endpoint lỗi HTTPS: mở thêm rủi ro tấn công man-in-the-middle.
- **Tự viết controller callback chỉ đọc `code`**: thường bỏ qua những kiểm tra mà Spring Security đã cung cấp.

## 10. Những trường hợp mở rộng cần lưu ý

### 10.1. Confidential client và public client

**Confidential client** là thành phần backend có khả năng giữ thông tin xác thực client (ví dụ secret hay private key) an toàn. **Public client** như ứng dụng chạy hoàn toàn trong browser hoặc ứng dụng mobile không thể bảo vệ secret nhúng sẵn.

- Public client cần PKCE vì không thể dựa vào client secret làm bằng chứng sở hữu của code.
- Confidential client **vẫn nên dùng PKCE khi OP hỗ trợ**, vì PKCE bổ sung ràng buộc từng authorization request, đồng thời thực hiện client authentication riêng nếu được yêu cầu.
- Bảo vệ của PKCE phát huy tác dụng khi verifier không bị lộ cùng code; với ứng dụng Spring MVC server-side, verifier có thể được giữ ở session phía server.

### 10.2. Nhiều OP và nguy cơ mix-up

Ứng dụng có thể cấu hình cả `google`, `enterprise-sso` và `academy`. Khi đó callback phải được liên kết với đúng registration/issuer. Ngoài kiểm tra state, cần xác minh issuer của ID Token/token và cấu hình authorization/token endpoint. Đối với bối cảnh có nguy cơ *mix-up*, các hướng dẫn OAuth2 đề xuất cơ chế phát hiện issuer như authorization response `iss` (RFC 9207) khi được hỗ trợ hoặc các biện pháp ràng buộc nhà cung cấp tương đương.

Một chữ ký ID Token hợp lệ từ **OP B** không được tự động coi là hợp lệ cho phiên đăng nhập dự định với **OP A**.

### 10.3. Nhiều tab hoặc nhiều authorization request đồng thời

Một số cơ chế lưu authorization request đơn giản chỉ giữ một yêu cầu đang chờ cho mỗi session tại một thời điểm. Khi người dùng liên tục nhấn login hoặc mở nhiều tab, thông tin tương quan của request cũ có thể bị thay thế và callback báo thiếu state.

Nếu ứng dụng phải hỗ trợ nhiều flow đồng thời, cần một `AuthorizationRequestRepository`/mô hình lưu trữ có khả năng phân biệt các request chưa hoàn thành, hạn chế replay và dọn dữ liệu đúng cách. **Không bỏ xác minh state để hỗ trợ nhiều tab.**

### 10.4. Response mode và chính sách cookie

Authorization Code Flow truyền code/state trong query string là lựa chọn phổ biến. OIDC còn có thể dùng `response_mode=form_post`, khiến browser POST callback từ site của OP về site ứng dụng.

Nếu browser không gửi session cookie do quy tắc cross-site, ứng dụng không tìm lại authorization request và state. Trong cấu hình này cần xác định rõ browser policy, `SameSite=None; Secure` khi có lý do, chiến lược CSRF và bảo vệ điểm callback. Không mặc định rằng đổi cookie toàn hệ thống sẽ tự giải quyết mọi vấn đề.

## 11. Bài tập tư duy

**Bài tập 1 — State đúng, PKCE sai.** Callback trả `state` đúng, nhưng backend gửi `code_verifier` không tương ứng với challenge ban đầu. Điều gì xảy ra?

> Client có thể vượt qua bước kiểm tra callback, nhưng OP phải từ chối đổi code vì PKCE thất bại. Đúng `state` không thay thế `code_verifier`.

**Bài tập 2 — PKCE đúng, nonce sai.** OP chấp nhận verifier và cấp token; ID Token chứa nonce khác với nonce đã gửi.

> Client phải từ chối ID Token theo ràng buộc OIDC. Việc token request thành công không chứng minh ID Token thuộc đúng lần xác thực.

**Bài tập 3 — ID Token hợp lệ, state không khớp.** Token có chữ ký, issuer, audience và nonce hợp lệ nhưng callback không thuộc authorization request trong session.

> Client phải từ chối callback trước khi coi đó là một phiên đăng nhập hợp lệ. Các kiểm tra token không thể sửa một authorization response không được ràng buộc với flow đã khởi tạo.

**Bài tập 4 — Code rò rỉ từ URL callback.** Kẻ tấn công biết `CODE_A` và `code_challenge=C_A`, nhưng không biết `code_verifier=V_A`.

> Nếu PKCE `S256` được triển khai và OP thực thi đúng, kẻ tấn công không thể đổi code chỉ với code và challenge. Client vẫn phải bảo vệ cookie, session, logs, token và back-channel.

**Bài tập 5 — Login website thành công nhưng API trả `401`.** Có nên gửi `state` hoặc `nonce` trong header `Authorization`?

> Không. API thường cần **access token** phù hợp với audience, scope và chính sách API. `state` và `nonce` phục vụ luồng đăng nhập OIDC, không phải credential để gọi API.

## 12. Những điểm cần nhớ

Ba giá trị này cùng tham gia một lần đăng nhập nhưng gắn với **ba chặng kiểm tra khác nhau**:

```text
Trước redirect:
  tạo state + nonce + PKCE verifier/challenge
                    |
                    v
Authorization response về callback:
  đối chiếu state với authorization request đã lưu
                    |
                    v
Token request từ backend đến OP:
  OP kiểm tra code_verifier bằng code_challenge đã lưu
                    |
                    v
Nhận ID Token:
  client kiểm tra chữ ký, issuer, audience, hạn dùng,
  nonce và các yêu cầu OIDC liên quan
                    |
                    v
Tạo Authentication + phiên đăng nhập của ứng dụng
```

Với Spring Security OIDC Client, hãy **để framework quản lý những ràng buộc này**, cấu hình đúng client registration, redirect URI, session/cookie, issuer và PKCE, rồi đọc các lỗi theo từng điểm xác minh. Khi tự tùy biến authorization request, token exchange hoặc callback, bảo đảm không làm mất cơ chế bảo vệ đã có.

### Tài liệu tham khảo để đọc sâu

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749), đặc biệt `state` và Authorization Code Grant.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636), định nghĩa verifier, challenge và `S256`.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700), các cập nhật bảo mật cho authorization code, PKCE và client.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html), các yêu cầu về nonce và ID Token validation.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207), biện pháp bảo vệ liên quan nhiều authorization server.
- [Spring Security Reference — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html).
- [Spring Security Reference — Advanced OAuth2 Login Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html).
