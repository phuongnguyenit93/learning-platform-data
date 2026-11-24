# Code challenge binding

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **code challenge binding** trong Proof Key for Code Exchange (**PKCE**) là gì và vì sao không thể chỉ kiểm “có code_verifier” ở token endpoint.
- Mô tả chính xác chuỗi liên kết giữa **client tạo code_verifier**, **code_challenge + code_challenge_method trong authorization request**, **authorization code được AS cấp** và **code_verifier trong token request**.
- Tính code_challenge theo phương thức **S256 = BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))** và phân biệt nó với phương thức **plain**.
- Thiết kế cách Authorization Server (**AS**) lưu, truy xuất và xác minh **challenge/method gắn với từng authorization code**, đồng thời kiểm client, redirect URI, TTL và nguyên tắc dùng một lần.
- Nhận biết các lỗi như **code interception, code substitution, PKCE downgrade, missing verifier, challenge bị thay thế, code được tái sử dụng** và dùng nhầm verifier giữa nhiều tab.
- Phân biệt bảo vệ của PKCE với **state, OIDC nonce, client authentication, TLS, issuer validation** và permission ở Resource Server.
- Thiết kế mã Java, HTTP example, sơ đồ Mermaid và negative tests để kiểm PKCE thực sự chống được trường hợp kẻ tấn công chỉ lấy được authorization code.

## 1. Code challenge binding là gì?

Trong luồng **OAuth 2.0 Authorization Code**, Authorization Server cấp **authorization code** cho client thông qua một authorization response, thường đi qua trình duyệt hoặc user agent. Client sau đó đổi code tại **token endpoint** để nhận access token.

Vấn đề: nếu kẻ tấn công chỉ lấy được **authorization code**, liệu họ có thể đưa code đó tới token endpoint và đổi lấy access token hay không?

**PKCE** thêm một bằng chứng chỉ giao dịch đó mới có:

1. Client tạo một chuỗi ngẫu nhiên mật mã gọi là **code_verifier**.
2. Client dẫn xuất **code_challenge** từ verifier và gửi challenge trong **authorization request**.
3. AS **gắn chặt code_challenge và code_challenge_method với authorization code** được cấp trong chính giao dịch đó.
4. Khi nhận **token request**, AS yêu cầu code_verifier và tính lại challenge theo **phương thức đã lưu**.
5. AS chỉ cấp token nếu giá trị tính lại **khớp chính xác challenge đã gắn với code**, đồng thời mọi điều kiện khác của authorization code/grant đều đúng.

Ràng buộc này là ý nghĩa của **code challenge binding**. Nó không đơn giản là “thêm hai tham số có tên giống nhau” vào các request.

~~~text
Client tạo:
    code_verifier = bí mật ngẫu nhiên theo giao dịch
    code_challenge = S256(code_verifier)

Authorization request tới AS:
    code_challenge + code_challenge_method=S256

AS lưu cùng authorization code:
    code -> expected challenge + method + client/grant context

Token request tới AS:
    code + code_verifier

AS kiểm:
    S256(received code_verifier) == stored challenge của CHÍNH code này
~~~

**Nếu client gửi một verifier đúng định dạng nhưng không phải verifier của code tương ứng, AS phải từ chối.**

## 2. PKCE nằm ở đâu trong hệ thống token security?

Bốn vai trò OAuth 2.0 gồm **Resource Owner**, **Client**, **Authorization Server** và **Resource Server**. Trong PKCE:

- **Client** sinh verifier/challenge, giữ verifier theo giao dịch và gửi verifier khi đổi code.
- **Authorization Server** ghi nhận challenge/method và xác minh binding tại token endpoint.
- **Resource Owner hoặc browser** tham gia authorization redirect; browser có thể nhìn thấy challenge, nhưng không cần biết verifier.
- **Resource Server** nhận access token sau đó; RS **không kiểm code_verifier**, vì PKCE là cơ chế bảo vệ giai đoạn phát hành token, không phải cơ chế phân quyền mỗi API request.

~~~mermaid
flowchart LR
    C["OAuth Client"] -->|"1. Authorization request: challenge + method"| AS["Authorization Server"]
    AS -->|"2. Authorization code có binding"| C
    C -->|"3. Token request: code + verifier"| AS
    AS -->|"4. Verify binding; cấp access token"| C
    C -->|"5. Access token cho đúng audience"| RS["Resource Server"]
    RS -->|"6. Kiểm token, scope, quyền tài nguyên"| R[("Protected Resource")]
~~~

**PKCE xác minh bên đổi code có bằng chứng thuộc giao dịch ban đầu.** Nó không xác minh người dùng có quyền đọc Order #123 và không làm access token trở thành token chống phát lại.

## 3. Ba giá trị cần phân biệt: verifier, challenge và method

| Thành phần | Ai tạo/giữ? | Nó xuất hiện ở đâu? | Vai trò |
| --- | --- | --- | --- |
| **code_verifier** | Client tạo bằng CSPRNG, giữ theo transaction. | **Token request** khi đổi authorization code. | Bằng chứng gốc, khó đoán. |
| **code_challenge** | Client dẫn xuất từ verifier. | **Authorization request** và record được AS lưu. | Giá trị cam kết để AS kiểm verifier sau này. |
| **code_challenge_method** | Client chọn trong tập AS hỗ trợ. | **Authorization request** và binding được AS lưu. | Xác định quy tắc biến đổi verifier thành challenge. |
| **authorization code** | AS cấp sau khi giải quyết yêu cầu ủy quyền. | Authorization response, rồi token request. | Grant ngắn hạn, dùng một lần, gắn với challenge và client. |

Hai nguyên tắc cần nhớ:

- **Verifier không phải authorization code.** Một verifier không tự đổi được token nếu thiếu code/grant phù hợp.
- **Challenge không phải secret.** Nó đi qua front channel, có thể nhìn thấy trong authorization URL; với S256, biết challenge không đủ để suy ra một verifier mạnh trong thực tế.

### Binding phải nằm ở AS

Client không thể bảo đảm PKCE an toàn nếu AS chỉ kiểm rằng request có trường code_verifier nhưng **không đối chiếu với challenge đã gắn code lúc phát hành**.

Ví dụ kiểm tra sai:

~~~text
if tokenRequest.code_verifier != null:
    issueTokens(tokenRequest.code)
~~~

Kiểm tra đúng về mặt ý tưởng:

~~~text
grant = findAndValidateAuthorizationCode(tokenRequest.code)
expectedChallenge = grant.pkceChallenge
expectedMethod = grant.pkceMethod

computedChallenge = transform(
    tokenRequest.code_verifier,
    expectedMethod
)

if computedChallenge != expectedChallenge:
    reject("invalid_grant")
~~~

Đây vẫn chỉ là một phần của token endpoint. AS còn phải kiểm **client, redirect URI, code expiry, code one-time, grant policy** và mọi client authentication phù hợp.

## 4. Cách tạo code challenge với S256

RFC 7636 định nghĩa phép biến đổi:

~~~text
S256:
    code_challenge =
        BASE64URL-ENCODE(
            SHA256(
                ASCII(code_verifier)
            )
        )

plain:
    code_challenge = code_verifier
~~~

Trong đó:

- **SHA-256** tạo ra giá trị digest 32 byte.
- **Base64URL** biểu diễn digest bằng bảng ký tự an toàn URL.
- Với PKCE, phép Base64URL **không dùng dấu padding =** ở cuối.
- **code_verifier** dùng các ký tự **unreserved** được phép trong RFC 7636, không phải chuỗi Unicode tùy ý.
- **S256** là phương thức được ưu tiên và nên sử dụng khi client/AS hỗ trợ; **plain** chỉ có ý nghĩa cho tương thích hạn chế và kém an toàn hơn trước việc lộ authorization request.

### Dùng đúng ASCII và không thêm bước mã hóa

Một lỗi phổ biến là thêm các bước không có trong RFC:

~~~text
Sai:
    SHA256(UTF8(URL_ENCODE(code_verifier)))
    SHA256(Base64(code_verifier))
    BASE64_STANDARD(SHA256(verifier))
    BASE64URL(SHA256(challenge))
~~~

Nếu code_verifier tuân thủ tập ký tự RFC 7636, biểu diễn ASCII và UTF-8 của nó sẽ giống nhau về byte. Nhưng nên viết phép biến đổi đúng đặc tả để không vô tình chấp nhận giá trị Unicode ngoài profile.

**Không thêm salt tùy ý, không hash hai lần, không chuyển chữ hoa/thường và không giữ dấu Base64 padding** khi tính S256.

### Ví dụ chuẩn trong RFC 7636

RFC 7636 cung cấp một bộ giá trị kiểm thử **công khai**, không dùng làm verifier thật:

~~~text
code_verifier:
dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

code_challenge (S256):
E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

Nếu tính đúng S256 trên verifier ở trên, kết quả phải trùng challenge. Đây là **test vector**, không được copy vào ứng dụng production như verifier cố định.

## 5. Sinh code_verifier đủ entropy và đúng định dạng

Theo RFC 7636, code_verifier là chuỗi **43–128 ký tự**, gồm các ký tự unreserved:

~~~text
ALPHA / DIGIT / "-" / "." / "_" / "~"
~~~

RFC khuyến nghị tạo một chuỗi ngẫu nhiên entropy mạnh; cách đơn giản là lấy **32 octet (256 bit)** từ CSPRNG rồi Base64URL không padding, cho ra **43 ký tự**.

Những ví dụ không phù hợp:

~~~text
code_verifier = "123456"
code_verifier = userId
code_verifier = accessToken
code_verifier = clientSecret
code_verifier = Math.random().toString()
code_verifier = hardcodedConstantInApp
code_verifier = codeChallengeFromPreviousLogin
~~~

Lưu ý:

- **Client secret không phải code_verifier.** PKCE cần verifier mới theo từng authorization request, kể cả client là confidential.
- **State cũng không phải verifier.** Chúng có thể đều ngẫu nhiên, nhưng dùng để kiểm ở các bước và ranh giới tin cậy khác nhau.
- Verifier không nên được ghi vào browser URL hoặc query của authorization request.
- Verifier cần được giữ cho đến khi token exchange kết thúc hoặc transaction bị hủy/hết hạn, rồi xóa theo chính sách.

### Khi verifier sai định dạng thì sao?

AS cần từ chối verifier không tuân profile, chẳng hạn:

- Dưới 43 hoặc trên 128 ký tự.
- Có dấu cách, ký tự Unicode ngoài tập cho phép, dấu **/** hoặc **+** không thuộc tập unreserved.
- Có chuỗi bị thay đổi vì encoding, trimming hay decoding sai.
- Có nhiều tham số code_verifier trùng nhau dẫn đến parse không nhất quán.

Không “sửa” input sai bằng cách cắt chuỗi hoặc tự động đổi định dạng rồi kiểm, trừ khi chính profile đã quy định bước xử lý đó.

## 6. Authorization Server phải lưu những gì cùng authorization code?

Đây là phần trọng tâm của **binding**.

Khi AS nhận authorization request hợp lệ chứa **code_challenge** và **code_challenge_method=S256**, rồi phát authorization code, nó cần lưu một record có thể được sử dụng khi client đổi code.

~~~text
AuthorizationCodeGrant:
    code_hash                lookup key của authorization code
    client_id                client đã đăng ký
    redirect_uri             URI đã dùng khi phát code
    subject_or_grant_context kết quả ủy quyền đã xác minh
    granted_scopes           phạm vi được AS chấp thuận
    audience_or_resource     resource đích đã được phép
    expires_at               thời điểm code hết hạn
    consumed                 false
    code_challenge           challenge từ authorization request
    code_challenge_method    S256
    issuer_id                issuer đã phát code
    session_or_auth_context  nếu policy cần
~~~

Đây là schema **minh họa**, không phải định dạng OAuth bắt buộc.

**Không được tách challenge thành một biến toàn cục của client hoặc một session cookie không gắn với từng code.** Một client có thể mở hai luồng authorization cùng lúc; mỗi code phải có binding riêng.

### Gắn cả method vào cùng grant

Nếu một code được phát với:

~~~text
challenge = ABC...
method = S256
~~~

thì khi đổi code, AS phải sử dụng **S256 được lưu ở grant**, không lấy method từ token request rồi cho client lựa chọn lại.

Nếu client có thể đổi method từ S256 sang plain sau khi code đã được cấp, nó có thể biến quy tắc kiểm bằng chứng thành một quy tắc khác. **Method là một phần của binding tại thời điểm phát hành code**.

### Không lưu verifier tại authorization endpoint

Thông thường AS **không cần biết verifier** khi nhận authorization request. Nó chỉ biết **challenge** và **method**. Verifier được client trình ra khi token exchange.

Nếu client đặt verifier trực tiếp trong authorization request trong khi dùng S256, giá trị bí mật sẽ xuất hiện trên front channel và làm suy yếu một lợi ích chính của PKCE.

## 7. Luồng đầy đủ: từ challenge tới token

~~~mermaid
sequenceDiagram
    participant B as Browser / User Agent
    participant C as OAuth Client
    participant AS as Authorization Server
    participant DB as Authorization Code Store
    participant RS as Resource Server

    C->>C: Sinh verifier; tính S256 challenge; sinh state
    C->>B: Redirect tới AS /authorize
    B->>AS: HTTPS /authorize + code_challenge + method=S256
    AS->>AS: Kiểm client, redirect URI, grant, user/consent
    AS->>DB: Lưu grant/code cùng challenge, method, client, redirect, TTL
    AS-->>B: Redirect callback với authorization code + state
    B->>C: code + state
    C->>C: Kiểm state và lấy verifier đúng giao dịch
    C->>AS: HTTPS POST /token với code + code_verifier
    AS->>DB: Load/consume code và binding
    DB-->>AS: Challenge, method=S256, client, redirect, scope
    AS->>AS: Kiểm client/grant và S256(verifier)==challenge
    alt Mọi điều kiện hợp lệ
        AS-->>C: Access token; RT/ID token nếu được cấp
        C->>RS: Access token cho đúng audience
        RS->>RS: Kiểm token, scope và quyền tài nguyên
    else Thiếu verifier hoặc binding không khớp
        AS-->>C: OAuth error invalid_grant
    end
~~~

### Bước 1 — Client tạo giao dịch

Client sinh:

~~~text
code_verifier = random high-entropy string
code_challenge = S256(code_verifier)
state = independent random transaction correlation value
~~~

Client lưu verifier theo **pending authorization transaction**. State có thể là khóa để tìm đúng verifier khi callback đến.

### Bước 2 — Gửi authorization request

Client gửi challenge và method, **không gửi verifier**.

### Bước 3 — AS ghi binding

AS kiểm request; khi phát code, nó lưu **challenge + method trên chính grant gắn với code**.

### Bước 4 — Trình duyệt quay lại client

Callback chứa code/state. Client kiểm **state, issuer và context** theo profile rồi tra đúng verifier.

### Bước 5 — Client đổi code

Client gửi **code và verifier** qua HTTPS đến token endpoint của AS đã tin cậy, kèm client authentication nếu là confidential client.

### Bước 6 — AS đối chiếu binding

AS xác minh code/grant và tính lại S256 từ verifier. Nếu không khớp, **không phát token**. Nếu khớp, AS vẫn tiếp tục/hoàn tất các kiểm tra token issuance khác.

## 8. HTTP example của một giao dịch PKCE

Các giá trị bên dưới là placeholder, không phải token thật.

### 8.1 Authorization request

~~~http
GET /oauth2/authorize?response_type=code&client_id=dashboard-client&redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback&scope=orders%3Aread&state=EXAMPLE_STATE&code_challenge=EXAMPLE_S256_CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: identity.example.test
~~~

Bên gửi thực tế dùng **https://identity.example.test**. Dạng GET hiển thị đường dẫn để người học phân biệt front channel.

AS phải kiểm client và redirect URI theo registration. Trước khi cấp code, AS kiểm challenge đúng syntax/method được hỗ trợ và chính sách yêu cầu PKCE.

### 8.2 AS lưu authorization code binding

~~~text
authorization_code = EXAMPLE_CODE_A

record:
  code = EXAMPLE_CODE_A
  client_id = dashboard-client
  redirect_uri = https://app.example.test/callback
  code_challenge = EXAMPLE_S256_CHALLENGE
  code_challenge_method = S256
  used = false
  expires_at = <short-lived deadline>
~~~

Lưu **hash của code** thay plaintext trong code store có thể là lựa chọn phù hợp nếu AS chỉ cần tra cứu/đối chiếu code đủ entropy. Binding của challenge/method vẫn phải được lấy từ **record đúng code**.

### 8.3 Authorization response

~~~http
HTTP/1.1 302 Found
Location: https://app.example.test/callback?code=EXAMPLE_CODE_A&state=EXAMPLE_STATE
~~~

Client kiểm state được echo, issuer/transaction context rồi lấy **verifier của giao dịch này**.

### 8.4 Token request

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=EXAMPLE_CODE_A&redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback&client_id=dashboard-client&code_verifier=EXAMPLE_VALID_VERIFIER
~~~

Đây là mẫu cho **public client**. Confidential client còn cần client authentication theo phương thức đã đăng ký. Nếu dùng DPoP/mTLS hoặc profile khác, phải bổ sung bằng chứng tương ứng.

AS không kiểm verifier bằng cách so trực tiếp nó với challenge nếu method đã lưu là **S256**; AS phải **tính S256(verifier)**.

### 8.5 Thành công hoặc thất bại

Khi tất cả điều kiện hợp lệ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "EXAMPLE_AT",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders:read"
}
~~~

Khi verifier không phù hợp:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "invalid_grant"
}
~~~

**900 giây** chỉ là TTL access token minh họa; nó không phải TTL authorization code, và không có giá trị chuẩn bắt buộc trong PKCE.

## 9. Vì sao code interception không còn đủ để đổi token?

Kẻ tấn công có thể lấy được authorization code bằng nhiều đường: redirect handler bị cấu hình sai, browser history, extension độc hại, log URL, deep link bị chặn hoặc đường callback bị chiếm trong một môi trường nhất định.

Một luồng thiếu PKCE:

~~~text
Attacker có authorization code
    -> POST /token với code, client_id và các tham số cần thiết
    -> có thể đổi token nếu các điều kiện khác không chặn
~~~

Với PKCE S256 và binding đúng:

~~~text
Attacker có code nhưng không có verifier
    -> POST /token
    -> AS tải challenge S256 đã gắn với code
    -> không chứng minh được verifier
    -> từ chối
~~~

Biết **code_challenge công khai** không giúp tìm được verifier mạnh trong thời gian thực tế nhờ tính chống đảo của SHA-256 và entropy của verifier.

**Giới hạn:** Nếu attacker cũng chiếm được verifier, hoặc kiểm soát hoàn toàn runtime của client và có thể tự tạo authorization request/đổi code, PKCE không còn đáp ứng giả định “attacker chỉ lấy được code”. Khi đó cần bảo vệ client, TLS, session và credential khác.

### PKCE không phải mã hóa authorization code

Code có thể vẫn là một chuỗi opaque ngẫu nhiên. PKCE **không mã hóa** code hoặc payload, mà thêm một **bằng chứng phải có khi redeem code** tại AS.

## 10. Code substitution và authorization response injection

**Code substitution** là việc thay code trong authorization response bằng một code từ giao dịch khác. Mục tiêu có thể là làm client tạo phiên không đúng chủ thể hoặc đổi sai grant.

Nếu client chỉ nhận bất kỳ code nào và đổi bằng một verifier chung, khả năng nhầm giao dịch tăng lên.

Một client đúng cần:

1. Sinh **state mới và verifier mới** cho mỗi authorization request.
2. Lưu **state → verifier + issuer + redirect_uri + session context**.
3. Kiểm state khi callback đến, trước token exchange.
4. Dùng đúng verifier của transaction tìm được.
5. AS kiểm challenge gắn với **code thực tế được gửi**, không gắn với một session mặc định của client.
6. Client xác minh token/ID token đúng profile rồi mới hoàn tất phiên.

Nếu attacker đưa **code của transaction B** vào callback của **transaction A**, client có thể lấy verifier-A từ state-A. AS có code-B gắn challenge-B nên phải từ chối nếu verifier-A không tương ứng.

PKCE mang lại lớp chống tráo code khi mỗi transaction có verifier độc lập và AS kiểm binding đúng. **State/correlation vẫn cần để tránh nhầm context và các kiểu tấn công ở callback.**

## 11. PKCE downgrade: khi method hoặc challenge bị bỏ qua

Một hệ thống có thể tuyên bố “hỗ trợ PKCE” nhưng thực tế vẫn dễ bị downgrade nếu xử lý parameter không nhất quán.

### 11.1 Không lưu method cùng authorization code

Authorization request:

~~~text
code_challenge = CHALLENGE_X
code_challenge_method = S256
~~~

Nhưng token endpoint dùng phương thức mặc định **plain** hoặc một method do caller tùy chọn. Khi đó AS **không kiểm theo cam kết ban đầu** và binding có thể bị phá vỡ.

**Sửa:** lưu **method=S256** cùng code, áp đúng method đó khi kiểm.

### 11.2 Cho client tự bỏ PKCE tại authorization endpoint

Nếu AS yêu cầu PKCE cho một loại client nhưng vẫn cấp code **không có challenge** khi request bỏ tham số, attacker có thể cố dùng một flow yếu hơn.

**Sửa:** AS phải **thực thi chính sách PKCE tại authorization endpoint**, từ chối request thiếu challenge/method hợp lệ khi client/flow yêu cầu PKCE.

### 11.3 Chấp nhận token request không có verifier

Nếu grant đã ghi code_challenge, token endpoint **phải yêu cầu code_verifier**. Không phát token chỉ vì code đúng.

### 11.4 Cho fallback sang plain

**plain** là một phương thức có trong RFC 7636, nhưng kém an toàn nếu request chứa challenge bị quan sát, vì challenge chính là verifier.

Theo RFC 7636, nếu **code_challenge_method** không có thì semantics mặc định là **plain**. Tuy nhiên, một chính sách hiện đại muốn **chỉ cho S256** nên từ chối request thiếu method hoặc yêu cầu plain, thay vì âm thầm chấp nhận một flow yếu hơn.

**Không tự động retry login với plain chỉ để vượt lỗi AS không chấp nhận S256.** Hãy xác minh metadata/hợp đồng và cấu hình tương thích một cách có chủ đích.

### 11.5 Thêm verifier muộn để hợp thức hóa code cũ

Khi code được phát **không có challenge**, AS không nên cho một token request bổ sung verifier mới rồi coi đó là PKCE hợp lệ. Bằng chứng phải được **cam kết từ authorization request ban đầu**, không phải xuất hiện lần đầu khi redeem code.

### 11.6 Tham số trùng hoặc parser không nhất quán

Ví dụ một authorization request gửi hai giá trị **code_challenge** hoặc hai giá trị **code_challenge_method**. Nếu gateway đọc một giá trị còn AS lưu giá trị khác, hệ thống có thể lệch binding.

**Sửa:** parse strict, từ chối yêu cầu không hợp lệ/ambiguous theo giao thức và profile; không cố đoán giá trị “đúng hơn”.

## 12. Mối quan hệ giữa PKCE và client authentication

Một nhầm lẫn phổ biến:

**“Confidential client đã có client_secret nên không cần PKCE.”**

Hai biện pháp có vai trò khác nhau:

| Cơ chế | Kiểm điều gì? | Vị trí kiểm | Rủi ro nó giúp giảm |
| --- | --- | --- | --- |
| **Client authentication** | Client có bằng chứng secret/private key/certificate đã đăng ký. | Token endpoint, đôi khi endpoint khác. | Client impersonation với confidential client. |
| **PKCE** | Bên đổi code có verifier được cam kết với authorization code. | Token endpoint, dựa trên challenge từ authorization request. | Authorization code interception/injection. |
| **state** | Callback thuộc giao dịch/phiên client đã mở. | Client tại callback. | Login CSRF và nhầm response. |
| **TLS** | Endpoint kết nối đúng và dữ liệu được bảo vệ trên đường truyền. | Mỗi hop HTTPS/TLS. | Nghe lén/sửa request trên mạng. |

Ngay cả khi confidential backend xác thực bằng **private_key_jwt**, PKCE vẫn thêm ràng buộc code theo từng authorization transaction. Hướng dẫn hiện đại khuyến khích dùng PKCE cho Authorization Code cả ở confidential clients khi khả thi.

**Public client** như SPA/native app không thể tạo ra một secret cố định có thể giữ kín khỏi người sở hữu thiết bị. Client ID công khai không phải bí mật. PKCE đặc biệt quan trọng ở các loại client này, nhưng vẫn không thay client registration, redirect URI checks hay policy của AS.

## 13. PKCE khác state, OIDC nonce và issuer identification

| Dữ liệu | Bên tạo | Bên xác minh | Điều kiện |
| --- | --- | --- | --- |
| **state** | Client. | Client ở authorization callback. | Giá trị echo khớp pending transaction đã tạo đúng phiên. |
| **code_verifier/code_challenge** | Client. | AS ở token endpoint. | S256(verifier) khớp challenge của code. |
| **OIDC nonce** | OIDC client. | Client khi kiểm ID token theo profile. | Nonce trong ID token khớp nonce của authorization request. |
| **issuer (iss)** | AS/OP theo profile. | Client/RS ở bước tương ứng. | Response/token thuộc issuer đã tin cậy và mong đợi. |
| **audience (aud)** | AS phát hành trong token khi profile áp dụng. | Client/Resource Server phù hợp. | Token dành cho đúng đối tượng nhận. |

### State và verifier cần là các giá trị độc lập

Ví dụ client mở hai luồng:

~~~text
Transaction A:
    state-A
    verifier-A
    challenge-A
    issuer-A

Transaction B:
    state-B
    verifier-B
    challenge-B
    issuer-B
~~~

Client dùng **state-A** lấy đúng **verifier-A**, sau đó AS kiểm verifier-A với challenge **được lưu dưới code-A**.

Dùng một **verifier chung cho tất cả tab** làm suy yếu ràng buộc theo transaction và dễ gây lỗi khi callback đến ngoài thứ tự.

### OIDC nonce không thay PKCE

Nonce thường được kiểm trong **ID token**, là credential dành cho client/relying party. PKCE được kiểm bởi AS khi **đổi authorization code**. ID token có nonce đúng không chứng minh một code bị đánh cắp không thể bị đổi ở token endpoint.

### Issuer và mix-up

Trong ứng dụng có nhiều AS, client phải gửi code/verifier đến **token endpoint của AS đã được chọn trong transaction**. State giúp lấy expected issuer nhưng không luôn đủ chống mix-up. Với profile áp dụng **RFC 9207 Authorization Server Issuer Identification**, client có thể kiểm tham số iss trong authorization response.

Không tự gửi **code_verifier/client secret** đến một token endpoint URL được truyền như tham số tùy ý trong callback. Challenge binding không có tác dụng bảo vệ secret bị gửi đến attacker-controlled endpoint.

## 14. Multi-tab, multi-instance và tính nhất quán của PKCE

Một lỗi thường xuất hiện khi frontend dùng một biến toàn cục:

~~~text
let currentVerifier = ...

Tab A: begin login -> verifier-A
Tab B: begin login -> verifier-B (ghi đè)
Tab A: callback code-A -> client gửi verifier-B
AS: S256(verifier-B) khác challenge-A -> invalid_grant
~~~

Trong trường hợp này AS thực thi binding đúng; lỗi ở client quản lý transaction.

### Lưu pending transaction theo state

~~~text
session.pendingOAuth = {
  state-A: {
    verifier: verifier-A,
    issuer: issuer-A,
    redirectUri: redirect-A,
    expiresAt: deadline-A
  },
  state-B: {
    verifier: verifier-B,
    issuer: issuer-B,
    redirectUri: redirect-B,
    expiresAt: deadline-B
  }
}
~~~

Mỗi callback dùng đúng record. Khi callback đã xử lý, client **consume transaction** để tránh dùng lại verifier/code/context.

Các tình huống cần kiểm:

- **Tab A/B** bắt đầu cùng lúc rồi hoàn tất ngược thứ tự.
- User đóng tab và mở lại: pending transaction có thể không tồn tại, phải fail closed.
- SPA **sessionStorage** theo tab khiến callback ở tab khác không thấy verifier.
- BFF nhiều instances dùng shared session store; callback tới node khác phải tìm được transaction.
- Một user hoàn tất hai flow đăng nhập hai tài khoản; cần policy tránh callback cũ ghi đè phiên mới không mong muốn.
- Retry token request sau network timeout: authorization code có thể đã được redeem; không phát lại code/verifier vô hạn.

**Không bỏ xác minh PKCE hoặc state để “sửa” lỗi đa tab.** Cần sửa cách quản lý giao dịch.

## 15. Authorization code phải dùng một lần và tồn tại ngắn

Ngay cả với PKCE, authorization code vẫn phải có **vòng đời ngắn, dùng một lần và ràng buộc client/redirect/grant**.

Giả sử attacker có code và verifier do một lỗi ở client. Nếu code đã được đổi và AS **đánh dấu dùng một lần**, attacker không được đổi lại để lấy thêm token.

AS cần thực hiện an toàn dưới concurrency:

~~~text
code state:
    ISSUED -> REDEEMING -> CONSUMED

Nếu hai POST /token cùng code đến:
    chỉ một luồng được phép redeem thành công
    luồng còn lại -> invalid_grant
~~~

Việc chỉ kiểm code “chưa dùng” rồi cập nhật trạng thái sau khi phát token **không có atomicity** có thể cho hai request đồng thời cùng qua:

~~~text
Request A: SELECT used=false
Request B: SELECT used=false
Request A: issue tokens
Request B: issue tokens
Request A/B: UPDATE used=true
~~~

**Sửa:** dùng giao dịch atomic, compare-and-set, lock hoặc cơ chế tương đương ở code store. Giữ trạng thái hợp lý khi các bước phát token hoặc trả response thất bại.

PKCE không thay **single-use authorization code**; cả hai phải được thực thi cùng nhau.

## 16. Pseudocode phía Authorization Server

Mã giả tập trung vào code challenge binding và lược bỏ nhiều chi tiết AS production:

~~~text
function authorize(request, userContext):
    client = registeredClient(request.client_id)

    require client exists
    require validRedirectUri(client, request.redirect_uri)
    require grantTypeAllowed(client, "authorization_code")

    if policyRequiresPkce(client):
        require request.code_challenge is present
        require request.code_challenge_method == "S256"

    requireValidChallengeSyntax(request.code_challenge)
    requireSupportedChallengeMethod(request.code_challenge_method)

    grant = authorizeRequestedScopeAndResource(
        client,
        userContext,
        request
    )

    code = createStrongOneTimeAuthorizationCode()
    storeCodeGrant(
        codeLookup = secureLookupValue(code),
        clientId = client.id,
        redirectUri = request.redirect_uri,
        issuer = trustedIssuer,
        scope = grant.scope,
        resource = grant.resource,
        subject = grant.subject,
        pkceChallenge = request.code_challenge,
        pkceMethod = normalizedMethodFromAuthorizationRequest,
        expiresAt = shortCodeDeadline,
        consumed = false
    )

    redirectToRegisteredClientWithCodeAndState(code, request.state)

function tokenEndpoint(request):
    require HTTPS
    require POST and validFormEncoding
    require request.grant_type == "authorization_code"

    client = resolveAndAuthenticateClientAccordingToRegistration(request)

    grant = findAndLockAuthorizationCode(request.code)

    if grant missing or expired or consumed:
        reject("invalid_grant")

    if grant.clientId != client.id:
        reject("invalid_grant")

    if redirectBindingDoesNotMatch(grant, request.redirect_uri):
        reject("invalid_grant")

    if grant.pkceChallenge is present:
        verifier = parseExactlyOneCodeVerifier(request)
        if verifier missing or invalidSyntax:
            reject("invalid_grant")

        computed = transformByStoredMethod(
            verifier,
            grant.pkceMethod
        )

        if not securelyEqual(computed, grant.pkceChallenge):
            reject("invalid_grant")
    else if policyRequiresPkce(client):
        reject("invalid_grant")

    require grant and current issuance policy still permit token

    markCodeConsumedAtomically(grant)
    issueTokensWithApprovedScopeAudienceAndClaims(grant)
~~~

### Những điều code production còn phải làm

- Tránh để lookup/decode lỗi tạo oracle hoặc tiết lộ code/grant.
- Kiểm client authentication đúng phương thức đã đăng ký; không coi client_id public là bí mật.
- Parse form nghiêm ngặt, không chấp nhận nhiều tham số trùng gây ambiguous interpretation.
- Phân biệt policy cho **legacy plain/no-PKCE** (nếu có) và policy **S256 bắt buộc**, không tự fallback khi lỗi.
- Code grant phải được gắn **issuer, client, redirect, scope, subject và resource**, không chỉ challenge.
- Kiểm grant expiry, one-time và phát token trong transaction/concurrency model an toàn.
- Không log code, verifier, client secret, token response hay thông tin cá nhân không cần thiết.
- Chống brute force/rate abuse và áp giám sát lỗi theo mức độ.
- Khi policy/DB/KMS lỗi, **không phát token theo nhánh mặc định cho phép**.

## 17. Java: tạo verifier và challenge đúng S256

Đoạn Java 17 sau minh họa cách sinh verifier và tính S256. Nó **không tạo authorization request đầy đủ, không thực hiện token exchange và không thay OAuth library production**.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

public final class PkceGenerator {

    private static final SecureRandom RANDOM = new SecureRandom();

    public record PkcePair(String verifier, String challenge) {}

    public static PkcePair newS256() throws Exception {
        byte[] entropy = new byte[32]; // 256-bit random
        RANDOM.nextBytes(entropy);

        String verifier = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(entropy);

        String challenge = s256(verifier);
        return new PkcePair(verifier, challenge);
    }

    public static String s256(String verifier) throws Exception {
        byte[] ascii = verifier.getBytes(StandardCharsets.US_ASCII);
        byte[] sha256 = MessageDigest.getInstance("SHA-256")
                .digest(ascii);

        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(sha256);
    }

    private PkceGenerator() {}
}
~~~

Với 32 byte entropy, verifier có **43 ký tự**; kết quả S256 cũng có **43 ký tự Base64URL không padding**. Những con số này là hệ quả của encoding, không phải lý do để bỏ kiểm cú pháp verifier ở AS.

### Kiểm bằng test vector RFC 7636

~~~java
import java.util.Objects;

public final class PkceVectorExample {
    static void verifyRfcExample() throws Exception {
        String verifier =
                "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
        String expected =
                "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM";

        if (!Objects.equals(PkceGenerator.s256(verifier), expected)) {
            throw new IllegalStateException("Wrong PKCE S256");
        }
    }
}
~~~

Dùng test vector để kiểm **tính toán challenge**, không dùng verifier đó làm bí mật thật vì nó đã được công khai.

## 18. Java: xác minh verifier với challenge đã lưu

Phần này mô phỏng một hàm AS nhận **stored challenge/method của authorization code đã được xác minh** và verifier do client trình ra.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.regex.Pattern;

public final class PkceBindingChecks {

    private static final Pattern VERIFIER =
            Pattern.compile("[A-Za-z0-9._~-]{43,128}");

    public static boolean matchesS256(
            String receivedVerifier,
            String expectedChallenge,
            String storedMethod
    ) throws Exception {
        if (receivedVerifier == null
                || !VERIFIER.matcher(receivedVerifier).matches()) {
            return false;
        }

        if (!"S256".equals(storedMethod)) {
            return false; // Ví dụ chỉ hỗ trợ S256.
        }

        if (expectedChallenge == null
                || !expectedChallenge.matches("[A-Za-z0-9_-]{43}")) {
            return false;
        }

        String computed = PkceGenerator.s256(receivedVerifier);

        return MessageDigest.isEqual(
                computed.getBytes(StandardCharsets.US_ASCII),
                expectedChallenge.getBytes(StandardCharsets.US_ASCII)
        );
    }

    private PkceBindingChecks() {}
}
~~~

**Điều kiện quan trọng:** expectedChallenge và storedMethod **không được lấy từ token request**. Chúng phải được lấy từ **grant record của đúng authorization code**. Hàm này không tự kiểm code còn hạn, client, redirect URI hay one-time; các bước đó phải có ở token endpoint.

Một phương thức **plain** có thể được một AS hỗ trợ riêng theo profile, nhưng ví dụ trên cố ý **chỉ chấp nhận S256**, tránh dạy fallback ngầm sang một method yếu hơn.

### Vì sao dùng MessageDigest.isEqual?

Nó giúp so sánh các byte đã được mã hóa theo cách phù hợp để tránh những khác biệt về thời gian không cần thiết của so sánh ký tự đơn giản. Dù vậy, PKCE an toàn **không thể chỉ dựa vào constant-time comparison**: verifier phải entropy mạnh, AS phải lưu đúng binding theo code và code phải dùng một lần.

### Cẩn trọng với dữ liệu chưa đáng tin

Một token endpoint public có thể nhận chuỗi rất dài/không hợp lệ. Trong production, cần giới hạn kích thước request/field trước khi tạo các object hoặc hash, áp rate limiting và tránh các phép biến đổi “sửa lỗi” làm hai input khác nhau trở thành một giá trị giống nhau.

## 19. Client/BFF: gắn verifier vào state transaction

Client nên lưu **verifier riêng cho từng authorization request**, đồng thời gắn state để callback lấy đúng record.

~~~text
function beginLogin(browserSession, issuer):
    require issuer in configuredTrustedIssuers

    state = newCsprngState()
    verifier = newCsprngPkceVerifier()
    challenge = S256(verifier)

    browserSession.pending[state] = {
        issuer: issuer,
        verifier: verifier,
        redirectUri: configuredRedirectUri(issuer),
        createdAt: now(),
        expiresAt: now() + shortTtl
    }

    redirectToAuthorizationEndpoint(
        issuer = issuer,
        state = state,
        code_challenge = challenge,
        code_challenge_method = "S256"
    )

function handleCallback(browserSession, callback):
    state = strictParseCallbackState(callback)
    tx = browserSession.pending.removeAtomically(state)

    if tx missing or expired:
        reject("unexpected_callback")

    verifyIssuerResponseAndContext(callback, tx)

    if callback has error:
        handleErrorWithoutCreatingSession(callback.error)
        stop

    code = strictParseCode(callback)
    tokens = exchangeCode(
        tokenEndpoint = trustedTokenEndpoint(tx.issuer),
        authorizationCode = code,
        redirectUri = tx.redirectUri,
        codeVerifier = tx.verifier
    )

    validateTokenAndOidcResponse(tokens, tx)
    completeSessionAccordingToPolicy()
~~~

**BFF/server-side client** thường giữ verifier trong server-side session. **SPA** có thể dùng một pending store theo tab/session (ví dụ sessionStorage), nhưng phải hiểu Web Storage không chống được mã độc JavaScript cùng origin. Với mobile, dùng các cơ chế transaction state phù hợp với system browser/native app flow.

**Verifier không nên được đưa vào URL callback, lưu vô hạn hoặc dùng lại giữa các transaction.**

## 20. Các kiểu thất bại làm mất binding

| Lỗi triển khai | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Client dùng **verifier cố định** cho mọi login. | Kẻ biết verifier có thể đổi code tương ứng nếu các điều kiện khác cho phép. | CSPRNG verifier mới cho mỗi giao dịch. |
| AS **không lưu challenge** cùng code. | Token endpoint không thể kiểm commitment ban đầu. | Lưu binding per-grant. |
| AS **không lưu method**. | Có thể kiểm sai S256/plain hoặc bị downgrade. | Lưu challenge_method cùng code. |
| AS chỉ kiểm **verifier tồn tại**. | Verifier bất kỳ có thể qua. | Tính lại challenge và so với record đúng code. |
| AS chấp nhận **verifier thiếu** khi grant có challenge. | Bỏ qua PKCE. | Từ chối token request. |
| AS lấy **challenge từ token request**. | Attacker tự chọn giá trị expected. | Chỉ lấy challenge đã lưu ở authorization step. |
| AS cho fallback từ S256 sang plain khi check không khớp. | Ràng buộc có thể bị hạ cấp. | Không fallback; từ chối. |
| Client dùng **global verifier** trong multi-tab. | Callback dễ lấy sai verifier; PKCE fail hoặc session sai. | Store keyed by state. |
| AS không kiểm **redirect URI/client**. | Code có thể được đổi sai context. | Bind code với client và redirect URI. |
| AS không đảm bảo code **one-time**. | Cùng code có thể phát token nhiều lần khi race. | Consume atomic. |
| Client không kiểm **state/issuer**. | Có thể nhận callback sai phiên hoặc AS, dù token exchange có PKCE. | State binding, issuer verification. |
| Plain được chấp nhận tùy tiện. | Verifier bị lộ ở front channel vì plain challenge = verifier. | Ưu tiên/restrict S256. |
| Client ghi verifier vào **log/URL**. | Người khác có thể lấy cả code lẫn verifier. | Redact; giữ verifier trong transaction store. |
| AS bị lỗi DB thì bỏ qua PKCE. | Cấp token khi không kiểm được binding. | Fail closed. |

## 21. Một bài toán multi-AS: challenge binding đúng vẫn có thể sai endpoint

Giả sử dashboard hỗ trợ:

~~~text
Issuer A:
    https://identity-a.example.test

Issuer B:
    https://identity-b.example.test
~~~

Client mở flow với AS-A, sinh **state-A** và **verifier-A**. Nếu callback bị tấn công khiến client gửi code/verifier tới token endpoint **không thuộc AS-A**, verifier có thể bị lộ dù PKCE được sinh đúng.

Vì vậy client phải:

1. Lưu expected issuer, client ID, redirect URI và verifier trong cùng transaction.
2. Xác minh authorization response thuộc issuer đã chọn theo profile (ví dụ **RFC 9207 iss**).
3. Chỉ gửi verifier tới token endpoint đã được xác minh từ **trusted issuer metadata/configuration**.
4. Không tin một tham số **token_endpoint** tự khai trong callback hoặc trong URL người dùng nhập.
5. Dùng HTTPS và kiểm certificate/hostname của endpoint.

**PKCE proof không thay thế endpoint trust.** Nếu gửi secret tới sai server, không thể dùng phép hash S256 để thu hồi những byte đã rò rỉ.

## 22. PKCE với JWT, opaque code, access token và refresh token

**Authorization code** trong OAuth thường được xem như một credential ngắn hạn dùng một lần. Nó có thể là chuỗi opaque do AS quản lý hoặc một representation khác được kiểm soát nghiêm ngặt theo kiến trúc AS. PKCE không bắt buộc code phải là JWT.

**Code challenge binding thuộc authorization code, không phải access token claim.** Khi AS phát access token JWT, nó có thể có claims như iss, aud, exp, scope, sub theo profile; điều đó không có nghĩa RS phải lấy code_verifier để kiểm mỗi request.

Ví dụ:

~~~text
Tại AS token endpoint:
    Verify code + verifier + grant
    -> issue access token

Tại RS Orders API:
    Verify issuer/signature or introspection
    Verify audience, exp, scope and permissions
    -> allow or deny resource request
~~~

**Refresh token** dùng cho refresh_token grant, không phải một authorization code để kiểm PKCE lại mỗi lần refresh. RT cần các bảo vệ vòng đời riêng: storage an toàn, client binding, rotation hoặc sender-constraining theo profile, thời hạn và revocation.

**ID token OIDC** dành cho client/relying party, có rules OIDC như issuer, audience, nonce và exp; không được thay access token để gọi Resource Server.

### PKCE không tự ngăn token bị sao chép

Sau khi một access token bearer được cấp hợp lệ, kẻ tấn công có bản sao token có thể thử dùng nó. PKCE đã kết thúc nhiệm vụ tại token exchange. Cần TLS, audience/scope hẹp, TTL, thu hồi, sender-constrained token (DPoP/mTLS) và quyền tài nguyên để bảo vệ giai đoạn sử dụng token.

## 23. DPoP và mTLS có thay code challenge binding không?

**DPoP (RFC 9449)** và **mutual TLS/certificate-bound tokens (RFC 8705)** giúp chứng minh bên gọi sở hữu khóa/chứng chỉ phù hợp trong một số ngữ cảnh. Chúng là những cơ chế bổ sung, không phải PKCE.

| Cơ chế | Bằng chứng | Bảo vệ giai đoạn nào? |
| --- | --- | --- |
| **PKCE** | code_verifier khớp challenge đã ràng với authorization code. | Đổi authorization code ở AS. |
| **Client authentication** | Secret/private key/certificate của confidential client. | Xác thực client với AS. |
| **DPoP** | Proof chữ ký của khóa client cho request/token theo profile. | Sender-constraining tại token endpoint và/hoặc RS. |
| **mTLS** | Client certificate trong TLS và binding khi áp dụng. | Xác thực kênh/client, ràng buộc token theo profile. |
| **TLS** | Certificate và bảo vệ kênh truyền. | Dữ liệu trong từng kết nối. |

Một thiết kế có thể dùng **Authorization Code + PKCE + DPoP** hoặc **Authorization Code + PKCE + confidential client authentication**. Không nên tự bỏ PKCE chỉ vì thêm một cơ chế khác khi kiến trúc/profile vẫn yêu cầu code challenge binding.

Với mọi cơ chế proof, phải hiểu **rủi ro khi client runtime/khóa bị chiếm**: một attacker có quyền thực thi cùng ứng dụng có thể gọi những thao tác được phép dù khóa không thể trích xuất trực tiếp.

## 24. Error handling và observability khi PKCE thất bại

Khi verifier không hợp lệ, không khớp hoặc authorization code không còn dùng được, token endpoint thường trả lỗi OAuth **invalid_grant**, theo RFC 7636 và RFC 6749.

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_grant"
}
~~~

Client cần:

- Không cố tự đổi **S256 → plain** để retry cùng giao dịch.
- Không retry cùng authorization code vô hạn; code có thể đã hết hạn hoặc dùng một lần.
- Đối chiếu log/metrics theo **transaction ID nội bộ không nhạy cảm**.
- Nếu verifier bị mất hoặc callback không khớp, hủy giao dịch và bắt đầu authorization flow mới.
- Không dùng một access token cũ, ID token hoặc refresh token để “điền vào” vị trí authorization code.
- Không tự chuyển token request sang AS khác để thử.

AS cần phân biệt lỗi nội bộ để vận hành nhưng không cung cấp một oracle chi tiết cho attacker. Ví dụ metric/log metadata:

~~~text
OAUTH_PKCE_CHALLENGE_MISSING
OAUTH_PKCE_UNSUPPORTED_METHOD
OAUTH_PKCE_VERIFIER_MISSING
OAUTH_PKCE_VERIFIER_INVALID_FORMAT
OAUTH_PKCE_CHALLENGE_MISMATCH
OAUTH_CODE_EXPIRED
OAUTH_CODE_ALREADY_REDEEMED
OAUTH_CLIENT_BINDING_MISMATCH
OAUTH_REDIRECT_BINDING_MISMATCH
~~~

**Không log raw code, code_verifier, access/refresh token, client secret hoặc full token request body**. Có thể log issuer/client và mã lỗi theo privacy/security policy, với retention và giới hạn quyền đọc.

### Các dấu hiệu phân tích sự cố

- Mismatch tăng sau bản release frontend: có thể code_verifier bị lưu sai tab hoặc code_challenge bị tính sai.
- Mismatch tập trung ở một client: kiểm encoding, CSPRNG và PKCE transaction store.
- Code already redeemed tăng: kiểm callback duplicate, retry hoặc race.
- Thiếu challenge nhiều: AS/client có thể cấu hình sai, hoặc đang có cố gắng downgrade.
- Một issuer nhiều lỗi: kiểm đúng metadata, endpoint trust và response issuer binding.

**Không giải quyết lỗi bằng cách tắt PKCE trong production.** Cần xác định luồng nào thiếu binding hoặc lưu sai transaction.

## 25. Negative tests dành cho code challenge binding

Một bộ test tốt phải chứng minh AS **từ chối verifier không thuộc code**.

| Test | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| **S256 đúng** | Code-A gắn challenge-A, gửi verifier-A. | Đạt PKCE, còn phải đạt các bước kiểm khác. |
| **Verifier sai** | Code-A, gửi verifier-B. | **invalid_grant**. |
| **Thiếu verifier** | Code-A có challenge, token request không có verifier. | **invalid_grant**. |
| **Verifier quá ngắn** | Dưới 43 ký tự. | Từ chối. |
| **Verifier quá dài** | Trên 128 ký tự. | Từ chối. |
| **Verifier có ký tự sai** | Chứa khoảng trắng, Unicode, dấu + hoặc /. | Từ chối schema. |
| **Chuyển chữ thường/hoa** | Sửa một ký tự verifier đúng. | Challenge mismatch, từ chối. |
| **Base64URL sai** | Client dùng Base64 chuẩn có +, / hoặc padding = trong challenge. | Không khớp/sai syntax theo profile. |
| **Challenge sai** | Authorization request gửi challenge khác S256(verifier). | Token exchange từ chối. |
| **Method sai** | Code lưu method=S256, token endpoint cố xử lý plain. | Không fallback, từ chối. |
| **Method thiếu khi S256 required** | Authorization request bỏ method. | Từ chối ở authorization endpoint theo policy. |
| **Challenge thiếu** | Client phải dùng PKCE nhưng authorization request không có challenge. | Từ chối authorization request. |
| **PKCE thêm muộn** | Code không có binding; token request mới có verifier. | Không coi verifier mới là binding ban đầu. |
| **Code thuộc client khác** | Client-B cố redeem code của client-A. | Từ chối. |
| **Redirect URI sai** | Token request dùng URI không khớp grant. | Từ chối. |
| **Code hết hạn** | TTL code đã qua. | Từ chối dù verifier đúng. |
| **Code dùng hai lần** | Hai token requests cùng code/verifier. | Tối đa một request được phát token. |
| **Request song song** | Token endpoint race khi code chưa consumed. | Atomic consume, không phát nhiều bộ token. |
| **State thuộc tab khác** | Callback-A bị xử lý bằng verifier-B. | Client không tráo transaction; AS từ chối nếu vẫn gửi sai. |
| **Authorization response bị chèn code** | State-A hợp lệ nhưng code-B bị thay vào. | PKCE challenge mismatch tại AS. |
| **Issuer sai** | Callback từ AS-B trong flow đã chọn AS-A. | Client từ chối theo issuer/mix-up policy. |
| **Endpoint giả** | Callback tự khai token_endpoint của attacker. | Client chỉ dùng trusted endpoint, không tiết lộ verifier. |
| **Duplicate parameters** | Nhiều code_verifier hoặc code_challenge. | Parser strict từ chối request ambiguous. |
| **Store thiếu binding** | Code record bị thiếu challenge/method trái policy. | Không phát token vì dữ liệu không đủ. |
| **AS backend lỗi** | Không đọc được grant/challenge hoặc KMS/policy store. | Fail-safe, không bỏ PKCE. |
| **Đổi code đúng nhưng API sai aud** | AT có audience API khác. | RS từ chối theo audience; PKCE không thay RS validation. |

### Tối thiểu bốn phép thử cần có

~~~text
Grant A:
    verifier-A -> challenge-A
    method = S256

Grant B:
    verifier-B -> challenge-B
    method = S256

1. Redeem(code-A, verifier-A) => PKCE OK
2. Redeem(code-A, verifier-B) => DENY
3. Redeem(code-B, verifier-A) => DENY
4. Redeem(code-B, verifier-B) => PKCE OK
~~~

Trong test thực, **mỗi grant nên được tạo mới** cho lần redeem; nếu redeem thành công ở bước 1, code-A sẽ đã dùng rồi. Muốn cô lập kiểm tra mismatch thì tạo các authorization code tương ứng mới theo từng ca, không dựa vào việc code có thể đổi nhiều lần.

## 26. Kịch bản tổng hợp: Dashboard và Orders API

Giả sử một doanh nghiệp có:

~~~text
Client:
    dashboard-web

Authorization Server:
    https://identity.example.test

Resource Server:
    https://orders.example.test

Grant:
    authorization_code

Requested audience:
    orders-api

Requested scope:
    orders:read
~~~

### Bắt đầu đăng nhập

Client sinh một cặp ngẫu nhiên:

~~~text
verifier = verifier-123        // KÝ HIỆU MINH HỌA, KHÔNG ĐÚNG FORMAT PKCE
challenge = S256(realVerifier)
state = independentRandomState
~~~

Ở đây **verifier-123 chỉ là tên ký hiệu**; trong thực tế verifier phải có 43–128 ký tự đúng chuẩn và entropy đủ mạnh.

Client lưu **state → realVerifier + issuer + redirectURI + expiry**, gửi challenge tới AS.

### AS cấp code có binding

Sau khi xác thực user và kiểm grant, AS lưu:

~~~text
code-A:
    client_id = dashboard-web
    redirect_uri = https://app.example.test/callback
    code_challenge = challenge-A
    code_challenge_method = S256
    scope = orders:read
    audience = orders-api
    expires_at = short deadline
    consumed = false
~~~

### Kẻ tấn công lấy code-A

Một log cấu hình sai vô tình chứa code-A. Attacker thử token request với code-A nhưng không biết verifier-A.

**Kết quả đúng:** AS tính S256 của verifier attacker gửi, thấy không khớp challenge-A và **không cấp access token**.

### Client hợp lệ đổi code-A

Dashboard nhận callback, kiểm state/issuer, lấy verifier-A và gửi tới token endpoint. AS kiểm challenge binding, client, redirect URI, TTL và one-time.

**Kết quả đúng:** AS có thể cấp access token cho **orders-api** với **orders:read**, nếu mọi policy khác đều đạt.

### Orders API nhận access token

Orders API **không nhìn thấy code_verifier**. Nó xác minh access token theo issuer/chữ ký hoặc trạng thái introspection, audience, exp/nbf, scope rồi kiểm permission đọc từng đơn hàng theo user/tenant.

**Bài học:** PKCE bảo vệ **cánh cửa đổi code thành token**; audience/scope và quyền tài nguyên bảo vệ **cánh cửa dùng token ở API**.

## 27. Checklist triển khai code challenge binding

Trước khi đưa Authorization Code + PKCE vào production, hãy xác nhận:

1. **Verifier:** Mỗi authorization request có verifier ngẫu nhiên mới, CSPRNG, 43–128 ký tự unreserved?
2. **S256:** Client tính S256 theo SHA-256 trên ASCII verifier và Base64URL không padding, không hash/encode thêm?
3. **Authorization request:** Có code_challenge và code_challenge_method=S256 theo policy, **không có verifier** trong front channel?
4. **AS policy:** AS có từ chối request thiếu PKCE khi client/flow yêu cầu, không downgrade ngầm sang plain?
5. **Code binding:** AS lưu challenge **và method trên chính record của authorization code**, cùng client/redirect/grant?
6. **Token endpoint:** AS lấy challenge/method từ code record tin cậy, không lấy từ token request?
7. **Verifier check:** Token request thiếu/sai verifier bị từ chối; không chấp nhận chỉ vì có tham số?
8. **Method check:** Luôn dùng method đã lưu, không để caller chọn lại hoặc fallback nếu S256 mismatch?
9. **Code one-time:** Authorization code có TTL ngắn, consume atomic khi redeem và không được dùng lại?
10. **Client binding:** Code chỉ được redeem bởi client đã gắn và theo client authentication/redirect URI policy?
11. **Transaction store:** Client lưu state → verifier + issuer + redirectUri + TTL theo phiên, không dùng biến global chung?
12. **State:** Callback kiểm state/CSRF correlation trước khi đổi code; không nhầm state với verifier?
13. **OIDC:** Nonce/ID token validation được thực hiện theo OIDC nếu sử dụng?
14. **Multi-AS:** Client có issuer binding/mix-up defense và chỉ gửi verifier tới trusted token endpoint?
15. **Transport:** Mọi endpoint cần thiết dùng HTTPS/TLS đúng certificate/hostname; không redirect credential sang HTTP/host khác?
16. **Storage/logs:** Không đưa verifier, code, RT/AT hoặc client secret vào log, URL không cần thiết hoặc analytics?
17. **Multi-tab/multi-instance:** Mỗi giao dịch có verifier riêng; callback không lấy nhầm verifier và shared store có atomicity?
18. **Error handling:** invalid_grant được xử lý an toàn, không tự retry bằng plain hay bỏ PKCE?
19. **Resource Server:** Sau khi AS cấp token, RS vẫn kiểm issuer, audience, type, exp, scope và permission tài nguyên?
20. **Negative tests:** Có kiểm verifier sai/missing, method downgrade, code replay, cross-client, wrong redirect, race, wrong issuer và lỗi grant store?

## Kết luận

**Code challenge binding là lõi bảo vệ của PKCE.** Client tạo **code_verifier** ngẫu nhiên, gửi **code_challenge và method** trước khi AS phát authorization code; AS lưu hai giá trị đó **gắn chặt với chính code/grant**. Khi đổi code, token endpoint chỉ chấp nhận **verifier tạo ra challenge tương ứng theo method đã lưu**, cùng với client, redirect URI, thời hạn, single-use và policy hợp lệ.

Với **S256**, code_challenge công khai không tiết lộ verifier có entropy mạnh trong thực tế. Nhờ vậy, kẻ tấn công chỉ lấy được authorization code thường **không thể đổi code thành token**. Tuy nhiên, PKCE không thay **state, issuer verification, client authentication, TLS, quản lý refresh token, audience, scope hoặc quyền nghiệp vụ ở Resource Server**.

Một câu hỏi review hiệu quả là: **“Với authorization code cụ thể này, AS lấy challenge và method từ đâu, chúng được gắn ở bước nào, và điều gì xảy ra nếu verifier sai hoặc code bị dùng lại?”** Nếu câu trả lời không thể chỉ ra binding per-code và xác minh một lần tại token endpoint, triển khai chưa thực sự bảo đảm PKCE.

### Tài liệu tham khảo

- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 7636 — Section 4: Protocol](https://www.rfc-editor.org/rfc/rfc7636#section-4)
- [RFC 7636 — Section 4.1: Client Creates a Code Verifier](https://www.rfc-editor.org/rfc/rfc7636#section-4.1)
- [RFC 7636 — Section 4.2: Client Creates the Code Challenge](https://www.rfc-editor.org/rfc/rfc7636#section-4.2)
- [RFC 7636 — Section 4.4: Server Returns the Authorization Code](https://www.rfc-editor.org/rfc/rfc7636#section-4.4)
- [RFC 7636 — Section 4.6: Server Verifies Code Verifier](https://www.rfc-editor.org/rfc/rfc7636#section-4.6)
- [RFC 7636 — Appendix B: Example for the S256 code_challenge_method](https://www.rfc-editor.org/rfc/rfc7636#appendix-B)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252)
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
