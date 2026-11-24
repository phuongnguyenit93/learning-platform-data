# Downgrade and plain method policy

## 1. Vì sao chính sách PKCE method là một quyết định bảo mật?

Trong chương **PKCE** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, bài này giải thích một lớp lỗi dễ bị bỏ sót: hệ thống đã *có PKCE* nhưng vẫn cho phép **hạ cấp xuống phương thức `plain`** hoặc **bỏ qua kiểm tra PKCE** trong một số nhánh. Đối với OAuth 2.0 Authorization Code flow, điều đó có thể khiến authorization code bị đánh cắp được đổi thành access token.

Xét ứng dụng **Shop Mobile** truy cập **Orders API**. Client tạo một bí mật tạm thời `code_verifier`, gửi giá trị suy ra `code_challenge` trong authorization request, sau đó gửi `code_verifier` đến token endpoint khi đổi code. Với **S256**, challenge được tính bằng SHA-256; với **plain**, challenge chính là verifier. Chọn phương thức sai có thể làm lộ ngay bí mật vốn được kỳ vọng chỉ xuất hiện khi đổi code.

Trong bài này, **downgrade** là việc một luồng lẽ ra phải được bảo vệ bằng PKCE S256 bị chuyển sang `plain`, không có PKCE, hoặc có PKCE trên danh nghĩa nhưng token endpoint không còn thực thi kiểm tra. Đây không chỉ là chuyện tương thích thuật toán: nó thay đổi **bằng chứng mà bên đang giữ authorization code phải cung cấp để được cấp token**.

### 1.1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt `code_verifier`, `code_challenge`, `code_challenge_method` và vì sao S256 mạnh hơn `plain` trước nguy cơ code interception.
2. Nêu rõ ranh giới giữa **hỗ trợ kỹ thuật theo RFC 7636** và **chính sách chỉ cho phép S256** của một Authorization Server (AS).
3. Nhận diện các đường hạ cấp: bỏ challenge, bỏ tham số method, thay method/challenge, bỏ kiểm tra ở token endpoint và fallback im lặng.
4. Thiết kế policy theo client và grant, bao gồm client cũ, migration, audit và cách từ chối an toàn.
5. Viết kiểm thử end-to-end bảo đảm code được ràng buộc với đúng method/challenge và chỉ đổi một lần.
6. Liên hệ PKCE với client authentication, state/issuer, redirect URI, access token, refresh token và quyền resource/action.

### 1.2. Phạm vi và thuật ngữ

**PKCE** là viết tắt của *Proof Key for Code Exchange* (RFC 7636), dùng cho **Authorization Code flow**. Hai phương thức challenge chuẩn được định nghĩa trong RFC 7636 là `plain` và `S256`. PKCE **không phải** thuật toán ký JWT, không phải cơ chế mã hóa access token và không phải cách xác thực người dùng.

| Thuật ngữ | Ý nghĩa |
|---|---|
| `code_verifier` | Giá trị ngẫu nhiên có entropy cao, client giữ riêng cho **một** authorization request |
| `code_challenge` | Giá trị gửi trong authorization request, được suy ra từ verifier |
| `code_challenge_method` | Cách tính challenge: `S256` hoặc `plain` theo RFC 7636 |
| Authorization code | Credential ngắn hạn dùng một lần, AS trả qua browser redirect rồi client đổi ở token endpoint |
| Code interception | Bên khác đọc được authorization code trước khi client hợp lệ đổi code |
| Downgrade | Luồng bị nới yêu cầu bảo vệ từ S256 xuống plain/không PKCE, hoặc PKCE không được thực thi |
| Method policy | Quy tắc của AS/client về phương thức PKCE **được phép** cho từng loại client/flow |

**Ghi nhớ:** hỗ trợ một phương thức trong giao thức **không đồng nghĩa** AS nên cho phép phương thức ấy với mọi client.

## 2. PKCE hoạt động thế nào khi dùng S256 và plain?

Trước khi điều hướng trình duyệt tới authorization endpoint, client sinh một verifier mật mã riêng biệt. RFC 7636 quy định verifier gồm **43–128 ký tự** trong tập unreserved `[A-Z] [a-z] [0-9] "-" "." "_" "~"` và đủ entropy để khó đoán.

### 2.1. S256: gửi hash của verifier qua front channel

Với `S256`, client tính:

~~~text
code_verifier = chuỗi ngẫu nhiên, khó đoán và chỉ dùng cho một request
code_challenge = BASE64URL_NO_PADDING(SHA256(ASCII(code_verifier)))
code_challenge_method = S256
~~~

Ví dụ authorization request (giá trị được rút gọn để minh họa):

~~~http
GET /oauth2/authorize?response_type=code&client_id=shop-mobile&redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&scope=orders%3Aread&state=<RANDOM_STATE>&code_challenge=<S256_CHALLENGE>&code_challenge_method=S256 HTTP/1.1
Host: login.example.com
~~~

AS lưu challenge và method **gắn với authorization code được cấp**. Sau khi nhận code từ redirect URI, client gửi:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<AUTHORIZATION_CODE>&redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&client_id=shop-mobile&code_verifier=<ORIGINAL_CODE_VERIFIER>
~~~

AS tính lại S256 từ verifier và so với **challenge lưu từ authorization request**. Bên chỉ thấy `code_challenge` trên front channel thông thường không thể suy ra verifier đủ mạnh bằng phép đảo SHA-256.

### 2.2. plain: gửi nguyên verifier trong authorization request

Với `plain`:

~~~text
code_challenge = code_verifier
code_challenge_method = plain
~~~

Nghĩa là giá trị chứng minh ở token endpoint đã **xuất hiện nguyên dạng trong authorization request**. Đường đi minh họa:

~~~mermaid
sequenceDiagram
    participant C as Public client
    participant B as Browser
    participant AS as Authorization Server
    participant X as Bên đọc được request/code
    C->>C: Sinh verifier V
    C->>B: /authorize?code_challenge=V&method=plain
    B->>AS: Authorization request mang V
    X-->>X: Đọc được V từ front channel/log
    AS-->>B: Redirect với code C1
    X-->>X: Chiếm được C1 qua đường yếu
    X->>AS: POST /token: code=C1, verifier=V
    Note over AS: Nếu không còn ràng buộc khác ngăn, X có thể đổi code
~~~

Không phải mọi người nhìn thấy URL đều tự động đổi được code: attacker còn phải **lấy authorization code**, đáp ứng client/redirect binding, client authentication nếu áp dụng, TTL và trạng thái code. Tuy nhiên với **public client**, chỉ có `client_id` không phải bằng chứng bí mật. Khi cả code và challenge plain bị lộ, PKCE plain không tạo được lớp bảo vệ như S256 đối với tình huống đó.

### 2.3. So sánh đúng trọng tâm bảo mật

| Đặc điểm | `S256` | `plain` |
|---|---|---|
| Challenge xuất hiện ở front channel | Hash Base64url của verifier | **Chính verifier** |
| Người đọc challenge có suy được verifier? | Không khả thi về mặt tính toán nếu verifier có entropy phù hợp | **Có ngay** |
| Bảo vệ khi attacker quan sát authorization request **và** lấy code | Có ích, nếu verifier không bị lộ theo đường khác | Không tạo lớp bí mật bổ sung |
| Cách AS kiểm tra ở token endpoint | Hash verifier rồi so challenge đã lưu | So verifier với challenge đã lưu |
| Mức khuyến nghị cho client mới | **Bắt buộc theo policy an toàn của bài này** | Không cho phép mặc định |
| Tính tương thích giao thức RFC 7636 | Có, là phương thức phải triển khai hỗ trợ theo RFC | Có thể hỗ trợ theo chuẩn, nhưng cần hạn chế chính sách |

**RFC 7636 quy định S256 là phương thức bắt buộc AS hỗ trợ; `plain` là tùy chọn.** Client có khả năng dùng S256 phải dùng S256; `plain` chỉ dành cho tình huống client có lý do kỹ thuật không hỗ trợ S256 và biết qua cấu hình ngoài luồng rằng AS hỗ trợ `plain`. Trong hệ thống hiện đại có thể tính SHA-256, **không có lý do thông thường để phát hành client mới với `plain`**.

### 2.4. PKCE không biến authorization request thành bí mật

Authorization request đi qua user agent và có thể được ghi tại browser, reverse proxy, observability hoặc các thành phần xử lý redirect. Với S256, challenge **không phải verifier**, nhưng vẫn có thể là dữ liệu correlation nên không cần log nguyên URL nếu không phục vụ mục đích an toàn. Với plain, chính URL ấy có thể chứa verifier; log challenge tương đương lưu credential để đổi code.

TLS vẫn bắt buộc, nhưng **HTTPS không bảo vệ dữ liệu khỏi các thành phần đã nhận và giải mã request**. Đây là lý do S256 quan trọng ngay cả khi hệ thống đã có HTTPS.

## 3. Bốn kiểu downgrade thường gặp

Cần phân biệt **thiếu PKCE**, **plain được chấp nhận**, **method/challenge bị thay** và **server không kiểm tra verifier**. Những lỗi này có điểm khắc phục khác nhau.

### 3.1. Downgrade loại A: authorization request mất code_challenge

Client dự định gửi:

~~~text
code_challenge=<HASH_OF_V>
code_challenge_method=S256
~~~

nhưng vì SDK lỗi, cấu hình proxy, client cũ hoặc kẻ tấn công có khả năng sửa request, request thực tế tới AS lại **không có `code_challenge`**. Nếu AS cho phép tiếp tục cấp code không ràng buộc PKCE, client vô tình đi vào Authorization Code flow yếu hơn.

**Kiểm soát:** AS có policy yêu cầu PKCE cho client/grant thuộc phạm vi cần bảo vệ; **từ chối ngay tại authorization endpoint** khi thiếu challenge hoặc method bắt buộc. Không đợi tới token endpoint rồi thử đổi code theo nhánh "legacy" không PKCE.

### 3.2. Downgrade loại B: plain được chọn thay vì S256

Ví dụ một client có hỗ trợ S256 nhưng do cấu hình fallback gửi:

~~~text
code_challenge=<RAW_VERIFIER>
code_challenge_method=plain
~~~

Nếu AS chấp nhận mặc dù registration yêu cầu S256, verifier xuất hiện trên front channel. Một attacker có thể đọc được challenge và lấy code sẽ có điều kiện thuận lợi để đổi code.

**Kiểm soát:** AS kiểm tra **giá trị method ở authorization endpoint** so với allowlist của client; với client yêu cầu S256, phải từ chối `plain`, không chỉ cảnh báo. Client cũng tự kiểm tra cấu hình SDK và không retry tự động bằng plain khi gặp lỗi.

### 3.3. Downgrade loại C: thay method hoặc challenge trên đường đi

Kẻ tấn công có khả năng can thiệp authorization request có thể muốn đổi:

~~~text
Trước:
    code_challenge = S256(V_client)
    code_challenge_method = S256

Sau (bị sửa):
    code_challenge = V_attacker
    code_challenge_method = plain
~~~

Nếu AS chấp nhận plain và code sau đó cũng bị attacker lấy, attacker có thể biết verifier tương ứng với **challenge mà AS thực sự lưu**. Trường hợp này đòi hỏi attacker có khả năng **thay đổi authorization request** và thu thập code; không nên mô tả nó là kết quả tự động của việc chỉ thay chuỗi method.

Nếu chỉ đổi method từ S256 sang plain nhưng giữ nguyên challenge là hash, client hợp lệ sẽ gửi verifier gốc và **không khớp**; thông thường kết quả có thể là **DoS** chứ chưa đủ để attacker lấy token. Để mạo danh thành công, attacker cần kiểm soát các giá trị và ranh giới phù hợp.

**Kiểm soát:** chính sách S256 từ chối plain, client/AS phải giữ request binding, và với threat model cần chống sửa tham số mạnh hơn có thể sử dụng **PAR** (Pushed Authorization Requests, RFC 9126) và **JAR** (JWT-Secured Authorization Request, RFC 9101) theo profile phù hợp để bảo vệ request integrity.

### 3.4. Downgrade loại D: token endpoint bỏ kiểm tra PKCE

Mẫu code sai nghiêm trọng:

~~~java
// SAI: code đã có challenge nhưng token endpoint bỏ qua nếu thiếu verifier.
if (request.codeVerifier() == null) {
    return issueTokenFromCode(request.code());
}
~~~

Một phiên bản nguy hiểm khác:

~~~java
// SAI: client gửi lại method ở token endpoint để yêu cầu
// kiểm tra theo phương thức khác hoặc bỏ qua kiểm tra.
String method = request.pkceMethodOrDefault("plain");
if (method.equals("plain")) {
    return issueTokenAfterWeakOrNoCheck();
}
~~~

**Token endpoint không được để caller chọn lại method.** Method/challenge là thuộc tính của **authorization request đã được AS chấp nhận và gắn với code**. Nếu code có PKCE challenge, thiếu/sai verifier phải bị từ chối. Không có nhánh "đã xác thực client nên bỏ PKCE" cho một code đã được cấp với PKCE.

### 3.5. Tóm tắt theo đúng điểm chặn

| Lỗi | Điểm chặn đầu tiên | Điểm chặn tiếp theo |
|---|---|---|
| Thiếu challenge | Authorization endpoint kiểm tra PKCE required | Không phát code không PKCE |
| Method là plain | Authorization endpoint kiểm tra allowed methods | Không tự downgrade sau lỗi |
| Challenge/method bị thay | AS policy, request integrity theo profile | Code binding, state/issuer, PKCE check |
| Thiếu/sai verifier khi exchange | Token endpoint kiểm tra method/challenge **đã lưu** | Không phát token, audit lỗi |
| Code bị đổi hai lần | Token endpoint tiêu thụ code nguyên tử | Phát hiện replay và xử lý grant |

## 4. Quy tắc bắt buộc theo chuẩn và policy riêng của hệ thống

Việc "giao thức có định nghĩa plain" thường bị hiểu nhầm thành "server phải cho plain hoạt động". Cần phân biệt:

**Điều RFC 7636 yêu cầu về khả năng tương thích:** S256 được định nghĩa và là phương thức cần hỗ trợ; plain có thể được triển khai vì lý do tương thích. Với một authorization request có challenge, token endpoint kiểm tra verifier theo **method gắn với request ban đầu**. Khi tham số `code_challenge_method` không được gửi, RFC 7636 quy định **giá trị mặc định là plain**.

**Điều policy mới an toàn nên áp dụng:** client phải có challenge, phải gửi rõ `code_challenge_method=S256`, và AS chỉ chấp nhận S256 cho registration này. Vì RFC mặc định thiếu method thành plain, **đừng để thiếu method vô tình được diễn giải và chấp nhận** trong policy S256-only.

### 4.1. Bảng policy gợi ý

| Authorization request | AS theo policy S256-only |
|---|---|
| Challenge hợp lệ + `code_challenge_method=S256` | Có thể tiếp tục nếu các điều kiện khác đạt |
| Challenge hợp lệ + `code_challenge_method=plain` | **Từ chối** |
| Challenge có nhưng không gửi method | **Từ chối** vì mặc định giao thức là plain |
| Có method S256 nhưng thiếu challenge | **Từ chối** |
| Method viết sai, ví dụ `s256` | **Từ chối**; method identifier phải đúng giá trị đã định nghĩa |
| Method không được hỗ trợ | **Từ chối**, không fallback |
| Challenge sai tập ký tự hoặc độ dài | **Từ chối** |
| Không có cả challenge và method | **Từ chối** |
| Có hai giá trị `code_challenge_method` mâu thuẫn | **Từ chối** request mơ hồ |

Auth-scheme HTTP như Bearer có quy tắc chữ hoa khác với PKCE method identifier. **Không tự chuẩn hóa `s256`, `S-256`, `SHA256` thành `S256`** nếu chuẩn/client registration chỉ cho đúng `S256`.

### 4.2. RFC 9700 và ranh giới hạ cấp

OAuth 2.0 Security Best Current Practice (RFC 9700) thúc đẩy dùng PKCE trong Authorization Code flow, đặc biệt cho public clients, và đặt ra yêu cầu bảo vệ khỏi các downgrade khiến PKCE không còn được kiểm tra. Các chính sách ở bài này được trình bày theo hướng **nghiêm ngặt hơn mức tương thích tối thiểu**: bật bắt buộc PKCE và S256 cho mọi client Authorization Code mới, không chấp nhận plain chỉ vì khả năng hỗ trợ kỹ thuật của AS.

Với confidential client, PKCE **bổ sung** bảo vệ code interception/injection; nó **không thay** client authentication đã đăng ký như `client_secret_basic`, `private_key_jwt` hoặc mTLS.

### 4.3. Chính sách phải được thực thi ở cả hai endpoint

**Authorization endpoint:**

- Chỉ chấp nhận client đã đăng ký, grant type `authorization_code`, redirect URI hợp lệ.
- Khi policy yêu cầu S256, từ chối request thiếu challenge, method hoặc dùng plain/unknown method.
- Lưu exact challenge và method đã chấp nhận cùng code, client, redirect URI, grant, TTL.
- Không cấp code trước rồi kỳ vọng token endpoint đoán ra rằng client đáng lẽ dùng PKCE.

**Token endpoint:**

- Xác thực confidential client, hoặc nhận diện public client theo registration và kiểm tra code-to-client binding.
- Kiểm tra code còn hạn, chưa dùng, thuộc đúng client, redirect URI và issuer.
- Đọc **method/challenge đã lưu từ code**, không nhận method mới để hạ cấp.
- Kiểm tra verifier đúng định dạng và S256, nếu sai trả lỗi theo OAuth; không phát token.
- Tiêu thụ code chỉ một lần bằng transaction/compare-and-swap phù hợp.
- Chỉ cấp subject, scope, resource/audience theo grant được phê duyệt.

**Client SDK:**

- Chỉ tạo S256, dùng verifier ngẫu nhiên riêng cho một request.
- Lưu verifier và issuer/state/redirect URI trong pending authorization context được bảo vệ.
- Không tự thử plain hoặc bỏ PKCE khi token request bị từ chối.
- Không gửi verifier qua URL authorization request, log hoặc analytics.

### 4.4. Vì sao client và AS đều phải có policy?

Nếu client chỉ tự cam kết S256 nhưng AS vẫn nhận plain, client khác, bản build lỗi hoặc request bị can thiệp có thể dùng phương thức yếu. Nếu AS chỉ kiểm tra ở authorization endpoint nhưng token endpoint bỏ verifier, challenge đã lưu trở thành trang trí. **Phải bảo vệ cả bước cấp code lẫn bước đổi code.**

## 5. Cấu hình PKCE theo client registration

Một AS có thể phục vụ SPA, native mobile, backend web, BFF và client cũ. Không nên dùng một biến toàn cục `pkceOptional=true` không phân biệt loại client. Hãy xác định policy từ **client registration, grant và môi trường bảo mật**, đồng thời ghi nhận phiên bản/chính sách áp dụng.

### 5.1. Ma trận client type và chính sách đề xuất

| Client | Cách giữ secret | PKCE cho Authorization Code | `plain` |
|---|---|---|---|
| SPA/browser public client mới | Không có client secret bảo mật dài hạn | **Bắt buộc S256** | **Không cho phép** |
| Native/mobile public client mới | Secret nhúng trong app không đáng tin | **Bắt buộc S256** | **Không cho phép** |
| BFF/confidential web app mới | Backend giữ client credential | **Bắt buộc S256 theo policy** và xác thực client | **Không cho phép** |
| Confidential backend tích hợp lâu năm | Có secret/khóa được bảo vệ | Migration sang S256 + client auth | Chỉ xem xét ngoại lệ có kiểm soát nếu thực sự chưa thể chuyển |
| Legacy public client không hỗ trợ S256 | Không giữ bí mật mạnh | **Chưa đạt mục tiêu S256-only** | Không mặc định cho phép; ưu tiên nâng cấp hoặc chặn |
| Machine-to-machine `client_credentials` | Workload authentication | **Không áp dụng PKCE** vì không có authorization code | Không áp dụng |

**Chú ý về bảng:** đây là **chính sách khuyến nghị cho hệ thống mới**, không phải khẳng định RFC bắt buộc tất cả confidential client đang tồn tại phải dùng S256 trong mọi profile. Việc nâng policy cần được thực thi nhất quán với khả năng thực tế của client và AS.

### 5.2. Ví dụ registration metadata nội bộ

~~~yaml
# Dữ liệu minh họa nội bộ của Authorization Server, KHÔNG phải
# schema/thuộc tính chuẩn của OAuth hay Spring Authorization Server.
client_id: shop-mobile
client_type: public
allowed_grant_types:
  - authorization_code
pkce:
  required: true
  allowed_methods:
    - S256
  reject_missing_method: true
  reject_legacy_plain: true
redirect_uris:
  - https://app.example.com/oauth/callback
allowed_resources:
  - https://orders.example.com
~~~

Ý nghĩa: dù một phiên bản thư viện Authorization Server có hỗ trợ cả `plain`, hệ thống vẫn **từ chối** `plain` cho `shop-mobile` ngay khi nhận authorization request.

Không được đưa tùy chọn như `pkce_required=false` vào authorization request để client tự quyết định tắt policy của chính mình. Policy phải được đọc từ cấu hình tin cậy ở AS, không dựa vào tham số do browser gửi.

### 5.3. Thay đổi policy sau khi đã cấp authorization code

Giả sử code C1 đã được cấp theo S256. Sau đó quản trị viên thay policy của client. Khi C1 được đổi, AS vẫn phải kiểm tra **S256 challenge được gắn với chính C1**; không được coi policy hiện tại là lý do bỏ verifier.

Ngược lại, nếu hệ thống vừa chuyển từ plain sang S256-only, những code cũ đang còn sống theo plain cần được xử lý có chủ đích:

- **An toàn nhất:** không cấp code plain mới; cân nhắc vô hiệu hóa code plain còn tồn tại.
- Nếu có giai đoạn chuyển tiếp ngắn, phải quy định ranh giới thời gian/issuer/client và không trộn method giữa các code.
- Không bao giờ tái diễn giải một code đã cấp với method plain thành method S256; điều đó thường khiến verifier của client không khớp và làm sai bất biến.
- Không hạ policy tại token endpoint theo báo lỗi do client gửi.

### 5.4. Mọi callback vẫn cần request binding

PKCE kiểm tra bên đổi code biết verifier. Client cũng phải biết **authorization response thuộc request nào**. Trong OIDC, thêm yêu cầu nonce/ID token verification khi tương ứng theo profile. Với nhiều Authorization Server, phải ràng buộc issuer của response với issuer đã chọn.

~~~text
pending_authorization:
    state_random
    issuer_expected
    client_registration_id
    redirect_uri
    verifier_secret
    method = S256
    created_at / expires_at
    consumed = false
~~~

Không dùng một verifier cố định cho nhiều tab hoặc nhiều user; một biến toàn cục có thể bị ghi đè khiến client lẫn request. **PKCE không thay thế state/CSRF protection hoặc issuer mix-up protection.**

## 6. Ngoại lệ `plain` và kế hoạch loại bỏ client legacy

Trong thực tế có thể tồn tại client rất cũ dùng `plain`, hoặc AS trước đây cho phép thiếu PKCE. Đây là một vấn đề **thay đổi hợp đồng bảo mật**, không nên giải quyết bằng cách nới toàn hệ thống.

### 6.1. Khi nào được cân nhắc ngoại lệ?

Chỉ cân nhắc khi đồng thời:

1. Đã xác minh client **thực sự** không thể hỗ trợ S256 vì nguyên nhân kỹ thuật cụ thể, không chỉ do cấu hình sai.
2. Đã đánh giá dữ liệu/tài nguyên có thể truy cập nếu authorization code bị chặn, loại client và độ tin cậy kênh redirect.
3. Có lý do nghiệp vụ và **ngày chấm dứt ngoại lệ**, owner chịu trách nhiệm và kế hoạch nâng cấp.
4. Ngoại lệ **chỉ gắn với client_id/registration cụ thể** và được ghi vào policy AS ở phía server.
5. Đã triển khai biện pháp giảm rủi ro thích hợp, đồng thời thừa nhận rằng các biện pháp ấy **không biến plain thành S256**.

Với **public client** có thể bị lộ cả code và authorization request, cho plain hoạt động có thể không đạt mục tiêu phòng code interception. Đối với dữ liệu nhạy cảm hoặc mối đe dọa đã xác định, **từ chối client cũ** có thể là quyết định cần thiết.

### 6.2. Những biện pháp giảm rủi ro không thay thế S256

| Biện pháp | Lợi ích | Không giải quyết |
|---|---|---|
| HTTPS/TLS | Chống nghe lén thụ động trên kênh truyền | Bản sao URL/log sau TLS |
| Code TTL ngắn | Giảm cửa sổ đổi code | Attacker đổi code nhanh khi biết verifier plain |
| Code dùng một lần | Chặn lần đổi thứ hai | Attacker có thể đổi **trước** client thật |
| Client authentication | Bảo vệ confidential client nếu secret/khóa chưa lộ | Public client không có bí mật dài hạn |
| Redirect URI binding | Hạn chế dùng code sai redirect/client | Không giấu verifier plain trong authorization request |
| Scope/audience tối thiểu | Giới hạn tác động access token nếu được cấp | Không ngăn code bị đổi trái phép |
| PAR/JAR theo profile | Có thể giảm sửa tham số authorization request | Không bảo đảm plain chống lộ verifier trong mọi bối cảnh |
| Logging redaction | Giảm bản sao credential bị lưu | Không biến plain challenge thành hash một chiều |

Kết hợp các biện pháp giúp phòng thủ sâu hơn, nhưng **rủi ro cấu trúc của plain vẫn tồn tại** khi attacker quan sát được authorization request/challenge và authorization code.

### 6.3. Quy trình migration gợi ý

1. **Kiểm kê:** xác định client sử dụng `plain`, thiếu method hoặc không có challenge. Chỉ ghi `client_id`, method, số lượng, phiên bản SDK và mã kết quả, **không log challenge/verifier/code thô**.

2. **Thông báo thay đổi:** công bố hợp đồng bắt buộc `code_challenge_method=S256`, thời hạn chuyển đổi và mã lỗi kỳ vọng; cung cấp ví dụ cho từng nền tảng.

3. **Thử nghiệm:** bật S256-only ở môi trường kiểm thử và với client được chọn, kiểm tra việc đổi code, refresh, đăng nhập nhiều tab và logout.

4. **Chặn plain theo nhóm:** tắt method plain theo từng registration, không bật lại toàn cục chỉ vì một client thất bại.

5. **Giám sát:** theo dõi lỗi `invalid_request`, `invalid_grant`, loại method bị từ chối, tỷ lệ authorization thành công mà không thu thập raw secrets.

6. **Loại bỏ ngoại lệ:** thu hồi quyền dùng plain, kiểm tra code đang sống và xóa cấu hình tương thích đã hết hạn.

**Rollback:** nếu cần khôi phục do sự cố vận hành, chỉ rollback theo phạm vi đã phê duyệt, có đánh giá rủi ro và audit. Không tự động fallback sang plain để "cho đăng nhập hoạt động lại" mà không có quyết định bảo mật.

### 6.4. Một số lỗi triển khai legacy nên phát hiện

| Dấu hiệu | Khả năng gốc |
|---|---|
| Client gửi challenge nhưng thiếu method | SDK kỳ vọng RFC mặc định plain |
| Client gửi `S256` nhưng AS trả unsupported | AS cũ/cấu hình sai, không được AS hỗ trợ đúng chuẩn |
| Client dùng method `SHA256` hoặc `s256` | Tên method sai định nghĩa |
| Client gửi `code_challenge=code_verifier` dù method `S256` | Chưa hash verifier hoặc hash sai |
| Client gửi hash hex | Sai encoding; cần Base64url không padding |
| Client dùng Base64 thường với `+`, `/`, `=` | Sai biểu diễn chuẩn của S256 challenge |
| Client dùng verifier của request trước | Lỗi lưu trữ/pending request hoặc multi-tab |
| Token endpoint chấp nhận code khi bỏ verifier | Lỗi kiểm tra PKCE ở AS, phải sửa ngay |

## 7. Sinh verifier và challenge S256 đúng bằng Java

Ví dụ Java tự chứa cho việc tính **S256**. Ứng dụng thực tế nên sử dụng OAuth/OIDC SDK/framework đã được duy trì để quản lý toàn bộ Authorization Code flow thay vì tự ghép redirect và token request.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

public final class PkceS256 {
    private static final SecureRandom SECURE_RANDOM = new SecureRandom();

    public record Pair(String verifier, String challenge) {}

    public static Pair createForOneAuthorizationRequest() throws Exception {
        byte[] random = new byte[32]; // 256 bit entropy
        SECURE_RANDOM.nextBytes(random);

        // 32 byte ngẫu nhiên -> 43 ký tự Base64url không padding.
        String verifier = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(random);

        byte[] sha256 = MessageDigest.getInstance("SHA-256").digest(
            verifier.getBytes(StandardCharsets.US_ASCII));

        String challenge = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(sha256);

        return new Pair(verifier, challenge);
    }
}
~~~

### 7.1. Tại sao chọn 32 byte từ SecureRandom?

- `SecureRandom` là nguồn ngẫu nhiên mật mã phù hợp trong Java nếu môi trường hệ thống được cấu hình an toàn.
- 32 byte tạo **256 bit entropy đầu vào**; Base64url không padding thường ra 43 ký tự, đạt độ dài tối thiểu verifier theo RFC 7636.
- Không dùng `Math.random()`, timestamp, user ID, UUID tự dựng thiếu kiểm chứng hay cùng một verifier cố định cho nhiều authorization requests.
- Một verifier phải được lưu an toàn và **liên kết với đúng state/authorization request**, rồi xóa khi hoàn tất/hết hạn.

Ví dụ không tự cài đặt browser redirect, callback state, client authentication hoặc token storage; đó là trách nhiệm của thư viện OAuth/OIDC và kiến trúc ứng dụng.

### 7.2. Tạo URL authorization request

Client tạo request có method S256 **một cách tường minh**:

~~~http
GET /oauth2/authorize?response_type=code&client_id=shop-mobile&redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&state=<RANDOM_STATE>&code_challenge=<BASE64URL_SHA256_OF_VERIFIER>&code_challenge_method=S256 HTTP/1.1
Host: login.example.com
~~~

Không nối URL một cách thủ công thiếu mã hóa tham số trong production. Dùng URI builder/SDK chuẩn để bảo vệ các ký tự đặc biệt và tránh duplicate/malformed query parameters.

### 7.3. Token request không được chọn lại method

Sau khi callback được kiểm tra, client gửi:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<AUTHORIZATION_CODE>&redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&client_id=shop-mobile&code_verifier=<ORIGINAL_VERIFIER>
~~~

**Không thêm `code_challenge_method=plain` ở token endpoint** để đổi cách so khớp. AS phải dùng method/challenge đã lưu theo code. Với confidential client, request còn có **client authentication** đã đăng ký ngoài PKCE.

## 8. Java pseudocode: enforce method policy và fail closed

Đây là **pseudocode định hướng thiết kế**, không phải API/class có sẵn của Spring Authorization Server. Các kiểu `ClientRegistration`, `AuthorizationRequest`, `AuthorizationCodeRecord`, `OAuthError` và `TokenIssuer` được giả định để minh họa.

### 8.1. Authorization endpoint từ chối downgrade

~~~java
void validatePkceForNewCode(
        ClientRegistration client,
        AuthorizationRequest request) {

    require(client.allowedGrant("authorization_code"));
    require(client.registeredRedirectUri(request.redirectUri()));

    // Policy do AS lưu, không lấy từ query của browser.
    if (client.pkceS256Required()) {
        if (request.codeChallenge() == null
                || !"S256".equals(request.codeChallengeMethod())) {
            throw OAuthError.invalidRequest(
                "PKCE S256 required for this client");
        }
    }

    require(pkceSyntax.isValidChallenge(request.codeChallenge()));
    // Code phải lưu cả challenge và method đã được chấp nhận.
}
~~~

Trong cấu hình S256-only, **thiếu `code_challenge_method` cũng phải từ chối**. Dù RFC 7636 định nghĩa default là `plain`, policy S256-only không được im lặng cho request đó đi tiếp.

### 8.2. Token endpoint không kiểm tra method do client tự khai

~~~java
void verifyPkceAtTokenEndpoint(
        AuthorizationCodeRecord code,
        String presentedVerifier) {

    // Method chỉ được lấy từ record đã cấp với code.
    String storedMethod = code.codeChallengeMethod();

    if (!"S256".equals(storedMethod)) {
        throw OAuthError.invalidGrant();
    }
    if (!pkceSyntax.isValidVerifier(presentedVerifier)) {
        throw OAuthError.invalidGrant();
    }

    byte[] hashed = sha256.ascii(presentedVerifier);
    String computed = base64url.noPadding(hashed);
    boolean valid = constantTime.equals(
        computed, code.codeChallenge());

    if (!valid) {
        throw OAuthError.invalidGrant();
    }
}
~~~

Chú thích:

- `sha256`, `base64url` và `constantTime` là **helpers giả định**.
- Kiểm tra `storedMethod` trước khi xác minh; không coi method thiếu là S256.
- Client không được sửa method/challenge bằng tham số gửi khi đổi code.
- Nếu hỗ trợ plain cho client legacy có ngoại lệ, AS phải có nhánh **riêng, có policy rõ ràng**, không đi chung vào nhánh S256 rồi tự hạ cấp.

### 8.3. Gắn PKCE với kiểm tra code một lần

~~~java
TokenResponse exchange(
        VerifiedClient client,
        TokenRequest request) {

    require(client.allowedGrant("authorization_code"));

    return transaction.run(() -> {
        AuthorizationCodeRecord code =
            codeStore.lockAndRead(request.code());

        require(code != null);
        require(code.isActiveAndNotExpired());
        require(code.clientId().equals(client.id()));
        redirectUriPolicy.verifyOriginalBinding(
            code.redirectUri(), request.redirectUri());

        verifyPkceAtTokenEndpoint(
            code, request.codeVerifier());

        ApprovedGrant grant = grantPolicy.recheck(
            code.grantedSubject(),
            code.grantedScopes(),
            code.allowedResources(),
            client);

        codeStore.markConsumedExactlyOnce(code.id());
        return issuer.issueWithinApprovedGrant(grant);
    });
}
~~~

Mã này chỉ biểu diễn logic. Trong production, phải có **atomic consume**, trạng thái grant/token nhất quán, bảo đảm không ký/trả hai bộ token từ cùng code, định nghĩa error response và xử lý rollback, revoke/audit đúng. Một cách triển khai thực tế thường dùng **framework Authorization Server** đáng tin thay vì tự tạo token endpoint.

**Lỗi cần tránh:** nếu phát hiện code đã USED rồi tạo audit/revoke trong transaction nhưng ném exception khiến toàn transaction rollback, hành động bảo mật có thể không được ghi nhận. Cần ranh giới transaction đảm bảo thay đổi trạng thái được commit **trước khi phản hồi lỗi** khi policy yêu cầu.

## 9. Spring Security và Spring Authorization Server: policy ở đúng vị trí

Trong ứng dụng Java/Spring, cần phân biệt **bên tạo PKCE request** và **bên kiểm tra PKCE rồi phát token**.

| Thành phần | Vai trò |
|---|---|
| **Spring Security OAuth2 Client / OAuth2 Login** | Client tạo authorization request, lưu verifier, xử lý callback và đổi code |
| **Spring Authorization Server** | AS nhận authorization request, áp PKCE/client policy, lưu code challenge/method, xử lý token endpoint |
| **Spring Security OAuth2 Resource Server** | Orders API nhận access token, kiểm tra JWT/opaque token và quyền trên resource |

Việc Shop Web đã cấu hình `oauth2Login` **không đảm bảo** một AS bên ngoài từ chối plain. Ngược lại, AS có policy S256-only nhưng client không tạo challenge đúng sẽ bị từ chối. Phải cấu hình cả hai đầu phù hợp.

### 9.1. Ví dụ client registration cho web backend

~~~yaml
# application.yml - cấu hình OAuth2 client minh họa.
spring:
  security:
    oauth2:
      client:
        registration:
          shop:
            provider: company
            client-id: shop-web
            client-secret: ${OAUTH_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - orders:read
        provider:
          company:
            issuer-uri: https://login.example.com
~~~

Đây là cấu hình **client**, không phải khai báo chính sách allowed PKCE methods trên AS. Client secret phải được giữ trong secret manager/backend, không commit vào repository. Với những AS không hỗ trợ OIDC discovery, cấu hình provider có thể cần authorization URI, token URI và metadata khác.

Trong Spring Security, cách kích hoạt PKCE và tùy biến authorization request **phụ thuộc phiên bản/framework và loại client**. Với public client, client framework thường có hỗ trợ PKCE; với confidential client, **cần xác minh S256 đã được bật** thay vì mặc định suy rằng client secret đồng nghĩa mọi flow đã có PKCE.

### 9.2. Kiểm tra client gửi ra giá trị gì

Trong môi trường test, có thể kiểm tra authorization request từ client:

~~~text
response_type=code
client_id=shop-web
redirect_uri=https://shop.example.com/login/oauth2/code/shop
code_challenge=<43_CHAR_BASE64URL_SHA256_DIGEST>
code_challenge_method=S256
state=<REQUEST_SPECIFIC_VALUE>
~~~

**Không cần ghi raw verifier** để kiểm thử. Test có thể sử dụng fixture verifier giả hoặc truy cập kho test được bảo vệ để tính expected challenge mà không đưa secret production vào trace.

Một assertion hữu ích:

~~~java
// Pseudocode kiểm thử trên authorization request đã parse:
assertEquals("S256", request.codeChallengeMethod());
assertTrue(request.codeChallenge() != null);
assertEquals(43, request.codeChallenge().length());
assertFalse(request.hasParameter("code_verifier"));
~~~

Độ dài 43 là kết quả Base64url không padding của SHA-256 32 byte. Nó là điều kiện hữu ích để bắt lỗi format S256, **không thay kiểm tra chính challenge có được tính từ verifier đúng hay không**.

### 9.3. Cấu hình Spring Authorization Server

Spring Authorization Server có các thành phần/provider xử lý authorization code request và token exchange, đồng thời cung cấp cơ chế validator/customizer tùy phiên bản. Khi hệ thống muốn bắt buộc S256:

1. Xác định client registrations có thể dùng authorization_code.
2. Tại **authorization endpoint validation**, yêu cầu challenge và exact method `S256`.
3. Không cấp code nếu request thiếu/chứa plain/sai cú pháp.
4. Ghi challenge và method đã được chấp nhận vào authorization/code state.
5. Tại **token endpoint**, để provider xác minh verifier dựa trên dữ liệu đã lưu, không tự tạo nhánh fallback.
6. Kiểm thử bằng HTTP thật và nhiều AS instances; không chỉ unit test method parser.

Ví dụ mô hình kiểm tra policy (pseudocode, không phải API cụ thể của Spring):

~~~java
void validateAuthorizationRequest(
        RegisteredClient client,
        ParsedAuthorizationRequest request) {

    if (!"authorization_code".equals(request.responseType())) {
        return; // Các flow khác có validator riêng.
    }

    require(client.isAllowedForAuthorizationCode());
    require(client.isRedirectUriAllowed(request.redirectUri()));

    // Mặc định cho client mới: PKCE S256 luôn bắt buộc.
    require("S256".equals(request.codeChallengeMethod()));
    require(pkceSyntax.isValidS256Challenge(request.codeChallenge()));
}
~~~

Không sao chép các tên type giả định trên để biên dịch như class thật. **Cần đối chiếu API extension/validation thực tế của Spring Authorization Server phiên bản đang sử dụng**. Nếu framework đã có check PKCE chuẩn, customization nên **bổ sung policy**, không thay thế và vô tình bỏ những kiểm tra mặc định về redirect/client/consent.

### 9.4. Lỗi cấu hình hay gặp trong migration

~~~text
Spring OAuth2 Client:
    code_challenge_method = S256  (đúng)

AS:
    pkceRequired = false
    allowPlain = true

=> Client hiện tại có thể hoạt động, nhưng AS vẫn nhận request plain
   hoặc không có PKCE cho client khác/cấu hình lỗi.
~~~

Ngược lại:

~~~text
AS:
    pkceRequired = true
    allowedMethods = [S256]

Client:
    code_challenge_method vắng mặt

=> AS từ chối; không hạ AS xuống plain để chữa lỗi client.
~~~

Khi debug, phân biệt **lỗi ở request đầu tiên** và **lỗi tại token exchange**; một `invalid_grant` do verifier sai không nên được xử lý bằng cách tắt PKCE.

## 10. Error handling: từ chối đúng điểm, không tiết lộ bí mật

### 10.1. Authorization endpoint nhận request không đạt policy

Với authorization request thiếu challenge hoặc dùng method sai, AS nên từ chối request bằng **OAuth error response thích hợp** với `invalid_request` hoặc lỗi tương ứng theo profile.

Ví dụ mô tả nội bộ:

~~~text
Authorization request:
  client_id=shop-mobile
  code_challenge=<VALUE>
  code_challenge_method=plain

Policy:
  required=S256

Decision:
  REJECT
  category=PKCE_METHOD_DISALLOWED
~~~

Phản hồi cho client nên ngắn và không ghi lại raw verifier/challenge. Khi **redirect URI không hợp lệ**, không chuyển error hoặc code đến URI đó. Cách trả lỗi ở authorization endpoint còn phụ thuộc trạng thái URI hợp lệ và chuẩn OAuth.

### 10.2. Token endpoint nhận verifier sai hoặc thiếu

Với code đã ràng buộc S256 nhưng token request thiếu/sai verifier, AS phải **không cấp token**. Một mẫu phản hồi:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_grant"
}
~~~

Trong thực tế, `invalid_grant` thường bao phủ code sai, đã dùng, hết hạn, sai redirect/client hoặc verifier không khớp theo profile/implementation. Không nên đưa chính giá trị `code_verifier` vào `error_description` để debug.

Nếu **confidential client authentication** sai, lỗi phù hợp thường là `invalid_client` (có quy tắc status và `WWW-Authenticate` riêng theo RFC 6749), không tự đổi sang public client để retry.

### 10.3. Không fallback theo lỗi

Ví dụ client sai:

~~~javascript
// SAI: không thử plain khi authorization request S256 thất bại.
try {
  await beginAuthorization("S256");
} catch (_) {
  await beginAuthorization("plain"); // Security downgrade
}
~~~

Nếu AS từ chối S256 do không hỗ trợ, nguyên nhân cần được sửa ở issuer/registration hoặc SDK; **không tự động giảm method chỉ để tiếp tục đăng nhập**. Nếu một ngoại lệ plain đã được phê duyệt, client phải có cấu hình rõ với owner/expiry, không tùy ý chuyển dựa trên response lỗi chưa xác minh.

### 10.4. Đừng để thông tin lỗi hỗ trợ dò code/verifier

| Chi tiết trong response/log | Rủi ro |
|---|---|
| "Verifier đúng 35 ký tự đầu" | Tiết lộ thông tin secret |
| Ghi đầy đủ verifier/challenge plain | Tạo bản sao credential |
| In raw authorization code | Có thể bị người có quyền xem log dùng trước expiry |
| Ghi raw client secret/private_key_jwt | Rò credential xác thực confidential client |
| In scope/tenant ngoài quyền | Rò thông tin chính sách hoặc dữ liệu |

AS có thể ghi event với `requestId`, `clientId`, `method`, `reasonCode`, `authRequestId` đã bảo vệ; không cần credential thật để phân tích downgrade.

### 10.5. Lỗi ở token endpoint khác lỗi ở Orders API

PKCE được kiểm tra khi **đổi authorization code**. Khi client đã có access token, Orders API kiểm tra token theo loại và ràng buộc của resource server:

~~~text
Authorization Code exchange:
    invalid_grant -> Không phát access token.

Orders API resource request:
    invalid_token / HTTP 401 -> Access token không được chấp nhận.
    insufficient_scope / HTTP 403 -> Token hợp lệ nhưng thiếu scope.
    resource authorization / HTTP 403 hoặc 404 -> Không có quyền trên object.
~~~

**Đừng thêm kiểm tra code_verifier vào mỗi request API nghiệp vụ.** PKCE không phải cơ chế proof-of-possession cho bearer access token đã cấp. Nếu cần chống replay của access token, cân nhắc DPoP/mTLS sender constraint theo profile thích hợp.

## 11. Kiểm thử đầy đủ downgrade và plain policy

### 11.1. Authorization endpoint: positive và negative cases

| Test | Policy S256-only mong đợi |
|---|---|
| S256 challenge 43 ký tự hợp lệ + method S256 | Qua kiểm tra PKCE, tiếp tục điều kiện authorization khác |
| Challenge thiếu, method thiếu | **Từ chối**, không cấp code |
| Challenge có, method thiếu | **Từ chối** vì mặc định RFC sẽ là plain |
| Method S256, challenge thiếu | **Từ chối** |
| Method plain, challenge hợp lệ | **Từ chối** |
| Method `s256` hoặc `SHA256` | **Từ chối**, không tự normalize |
| Method không biết | **Từ chối** |
| Challenge sai tập ký tự | **Từ chối** |
| Challenge S256 không có đúng độ dài | **Từ chối** |
| Tham số method/challenge bị trùng | **Từ chối** trường hợp mơ hồ |
| Request cố tự đặt `allow_plain=true` | Không nới policy AS |
| Client registration khác thử dùng client_id của client S256-only | Áp policy theo client thực đã đăng ký/xác minh, không theo claim tùy ý |
| Client dùng grant không phải authorization_code | PKCE không tự áp; dùng validator của grant tương ứng |

**Một request có challenge đúng 43 ký tự vẫn có thể bị giả** nếu người gửi tự chọn chuỗi; bước token endpoint phải xác minh verifier thực sự tạo ra challenge ấy.

### 11.2. Token endpoint: verifier và method binding

| Test | Kỳ vọng |
|---|---|
| Code S256 còn hạn + đúng client + đúng verifier | Có thể phát token trong grant |
| Verifier thiếu | Từ chối |
| Verifier sai | Từ chối |
| Verifier 42 ký tự hoặc 129 ký tự | Từ chối theo RFC |
| Verifier chứa ký tự không hợp lệ | Từ chối |
| Verifier hash ra challenge khác | Từ chối |
| Verifier đúng nhưng token request khai method plain | Bỏ qua/từ chối trường method không hợp lệ theo contract; không đổi method lưu |
| Challenge của code A, verifier của code B | Từ chối |
| Code của client A dùng tại client B | Từ chối |
| Confidential client có secret đúng nhưng verifier sai | Từ chối; không bỏ PKCE |
| Code đã được sử dụng trước đó | Từ chối, theo policy replay |
| Hai request đồng thời dùng một code | Tối đa một lần tiêu thụ và cấp token |
| Redirect URI token request khác URI ban đầu | Từ chối theo quy tắc OAuth |
| Code hết hạn | Từ chối |

### 11.3. Test downgrade đường đi

Mô phỏng **bốn biến thể**:

1. Client tạo request S256 nhưng trước AS challenge bị bỏ; AS phải từ chối **ngay authorization endpoint**.
2. Request S256 bị thay bằng `plain`, challenge vẫn là hash; AS phải từ chối thay vì chỉ gây mismatch ở token endpoint.
3. Request bị thay cả method `plain` và challenge thành verifier do attacker biết; AS phải từ chối **dựa trên policy**, không chờ xem attacker có lấy được code hay không.
4. Authorization request S256 được AS chấp nhận, sau đó token request bỏ verifier hoặc cố yêu cầu method plain; AS phải từ chối **ở token endpoint**.

Các bài test cần dùng client registration S256-only thật tại AS, không chỉ mock một hàm utility ở client.

### 11.4. Test với mã chứng minh từ RFC 7636

RFC 7636 Appendix B cung cấp test vector:

~~~text
code_verifier:
dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

S256 code_challenge:
E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

Client helper Java và token endpoint validator có thể dùng cặp giá trị này để xác minh SHA-256 + Base64url **không padding**. Nó chỉ kiểm tra tính toán S256, **không thay kiểm thử policy từ chối plain hoặc code replay**.

### 11.5. Browser, BFF và nhiều tab

- Mỗi authorization request phải có verifier/state riêng, không dùng shared mutable global chung cho tất cả tab.
- Callback tab B không được dùng verifier tab A.
- Nếu user từ chối consent hoặc callback báo lỗi, client không đổi code giả/sai.
- Client không gửi verifier qua authorization request URL; không đưa code/challenge plain/verifier vào client logs.
- Nếu BFF giữ pending request ở server, browser không được tự gửi verifier khác để "sửa lỗi".
- Khi callback sai issuer, client không gửi code sang token endpoint của issuer do URL callback tự khai.
- Khi token request timeout sau khi AS đã commit code=USED, không cho retry vô hạn cùng code.

### 11.6. Test resource server và vòng đời token

Ngay cả khi PKCE đạt:

- JWT access token sai chữ ký, issuer, audience, thời gian hoặc loại token phải bị từ chối.
- Opaque token inactive phải bị từ chối theo introspection/policy.
- ID token OIDC không được dùng thay access token ở Orders API.
- Token `orders:read` không cho Alice đọc đơn hàng Bob ngoài quyền.
- Refresh token cho public client phải có cơ chế chống replay phù hợp (rotation hoặc sender constraint).
- Token revocation và JWT offline expiry phải hoạt động đúng thiết kế, không suy PKCE đã chống replay của access token.

## 12. Tình huống suy luận về downgrade

### Tình huống A — client không gửi method

Shop Mobile gửi `code_challenge=<VALUE>` nhưng bỏ `code_challenge_method`, vì lập trình viên cho rằng AS tự dùng SHA-256.

**Câu hỏi:** Theo RFC 7636, AS sẽ hiểu method nào nếu chỉ dùng mặc định giao thức? Với policy S256-only phải làm gì?

**Trả lời:** Khi method bị bỏ, RFC 7636 định nghĩa mặc định là **`plain`**, không phải `S256`. AS có policy S256-only phải **từ chối**, yêu cầu client gửi tường minh `code_challenge_method=S256`.

### Tình huống B — fallback khi nhận unsupported challenge method

SDK client gửi S256 và được AS cấu hình sai trả lỗi, rồi tự retry với plain để người dùng đăng nhập được.

**Câu hỏi:** Fallback có nên được chấp nhận không?

**Trả lời:** Không. Đây là downgrade. Client nên dừng, báo lỗi cấu hình/khả năng của AS, kiểm tra issuer và nâng cấp AS/SDK. Một ngoại lệ plain cần quyết định chính sách riêng, giới hạn client và có ngày chấm dứt; không phát sinh tự động từ một response lỗi.

### Tình huống C — verifier plain lọt vào access log

Một client legacy dùng `code_challenge_method=plain` và reverse proxy ghi đầy đủ URL authorization request. Attacker lấy được cả URL và authorization code.

**Câu hỏi:** PKCE plain còn bảo vệ bước exchange như S256 không?

**Trả lời:** Không. Challenge chính là verifier nên URL đã tiết lộ giá trị cần trình ở token endpoint. Nếu attacker cũng đáp ứng được các điều kiện khác như code/client/redirect binding và code chưa được đổi, họ có thể thử đổi code trước client hợp lệ.

### Tình huống D — AS chấp nhận S256 nhưng token endpoint có nhánh bỏ kiểm tra

Authorization request có S256 challenge đúng. Token endpoint phát token khi không gửi verifier nếu code có trạng thái ACTIVE.

**Câu hỏi:** Chính sách S256 ở authorization endpoint có đủ chưa?

**Trả lời:** Không. Đó là PKCE trên danh nghĩa. Token endpoint phải kiểm tra verifier theo **challenge và method đã lưu gắn với code**; nếu thiếu/sai phải từ chối, dù client đã được xác thực.

### Tình huống E — chỉ sửa method mà giữ challenge

Request gốc có challenge S256(V). Attacker đổi method thành plain nhưng giữ challenge là hash S256(V). Client gửi verifier V đúng như trước.

**Câu hỏi:** Có thể khẳng định attacker đã đổi được code thành token không?

**Trả lời:** Không thể kết luận vậy. Với method plain, AS sẽ so V với hash S256(V), thường **không khớp**, nên có thể gây DoS. Muốn dùng plain để chiếm token, attacker còn cần kiểm soát challenge tương ứng và có code/đáp ứng các ràng buộc khác. Dù sao AS policy S256-only phải từ chối request plain ngay từ đầu.

### Tình huống F — confidential client có secret tốt

Shop Web dùng `client_secret_basic` qua HTTPS; đội phát triển muốn bỏ PKCE vì cho rằng client secret đã đủ.

**Câu hỏi:** Có thể bỏ mọi yêu cầu PKCE không?

**Trả lời:** PKCE và client authentication bảo vệ những ranh giới khác nhau. Secret giúp AS xác thực confidential client, còn PKCE ràng buộc code với request có verifier. Với hệ thống mới có policy S256-only, hãy áp dụng **cả hai** và không cho một yếu tố "miễn" kiểm tra yếu tố còn lại.

### Tình huống G — public client tự khai chính sách

Authorization request thêm `pkce_required=false`, còn registration của client yêu cầu S256.

**Câu hỏi:** AS nên tin cấu hình nào?

**Trả lời:** Policy từ client registration và cấu hình bảo mật **phía AS**. Tham số trong request do caller/browser kiểm soát không được phép nới ràng buộc bắt buộc.

### Tình huống H — code đã dùng ở một node khác

AS chạy ba instances, dùng cache cục bộ để lưu trạng thái consumed. Node A đổi code và cấp token; node B chưa nhận cập nhật nên cũng phát token khi cùng code được gửi lần nữa.

**Câu hỏi:** PKCE đúng có ngăn lỗi này không?

**Trả lời:** Không. Một verifier đúng có thể được trình lại. Authorization code cần **single-use nguyên tử trên toàn cụm**; PKCE không thay thế transaction, locking hoặc compare-and-swap nhất quán.

### Tình huống I — bật S256-only làm client legacy lỗi

Một app mobile cũ không hỗ trợ SHA-256 theo SDK hiện tại, trong khi API chỉ cung cấp dữ liệu có độ nhạy cao.

**Câu hỏi:** Giữ plain để tránh gián đoạn luôn là lựa chọn tốt nhất?

**Trả lời:** Không. Cần đánh giá rủi ro, khả năng nâng cấp, phạm vi quyền và cam kết bảo mật. Có thể **không cấp tiếp token** cho client cũ cho đến khi nâng cấp. Một ngoại lệ plain nếu được chấp nhận phải có owner, thời hạn và kiểm soát bổ sung, không nới toàn AS.

### Tình huống J — PKCE đúng nhưng access token có audience rộng

Client đổi code bằng S256 thành công, AS trả JWT có audience gồm mọi API trong tổ chức và scope không đúng grant.

**Câu hỏi:** PKCE có khiến token đó an toàn không?

**Trả lời:** Không. PKCE bảo vệ **code exchange**, không quyết định quyền phát hành. AS phải cấp token đúng subject, client, scope, audience và TTL; resource server phải kiểm tra quyền trên từng object/action.

### Tình huống K — token endpoint được lấy từ query callback

Một client hỗ trợ hai AS. Callback có `issuer=other` và `token_endpoint=https://attacker.example/token`; code và verifier được gửi tới endpoint này.

**Câu hỏi:** Vấn đề gì xảy ra?

**Trả lời:** Đây là nguy cơ mix-up và lộ secret. Token endpoint phải đến từ **metadata tin cậy** của issuer gắn với pending request; client cần kiểm tra issuer authorization response theo profile. Không chuyển code, verifier hay client secret tới endpoint từ URL callback tự khai.

### Tình huống L — refresh token bị lộ sau login

Ứng dụng dùng PKCE S256 đúng nhưng ghi refresh token vào crash report.

**Câu hỏi:** PKCE có ngăn replay refresh token không?

**Trả lời:** Không. Refresh token cần secret storage, redaction, client/grant binding, rotation hoặc sender constraint theo threat model, TTL và revocation. PKCE không phải cơ chế chống replay cho refresh token đã cấp.

## 13. Xử lý sự cố khi phát hiện AS chấp nhận downgrade

Nếu kiểm thử chứng minh AS cấp authorization code không PKCE hoặc `plain` cho một client được yêu cầu S256, hãy xử lý như **lỗ hổng trong boundary phát hành**, không chỉ là lỗi hiển thị thông báo đăng nhập.

1. **Xác định phạm vi:** client registrations, issuer, endpoint, phiên bản AS, thời gian bật cấu hình, những grant bị ảnh hưởng.
2. **Ngừng cấp code yếu:** từ chối method plain/thiếu challenge theo policy; không sửa bằng cách tự cho token endpoint nhận method mới.
3. **Xác định các authorization codes còn sống:** cân nhắc vô hiệu hóa code không đạt policy, bảo đảm không ảnh hưởng code S256 hợp lệ ngoài phạm vi.
4. **Đánh giá token đã phát hành:** scope/audience/subject, các lần code reuse, sự kiện đổi code bất thường, khả năng thu hồi grants/tokens.
5. **Rà soát log/telemetry:** authorization URL có `code_challenge` plain, callback code, token endpoint verifier, client secret và token response đã được lưu ở đâu.
6. **Thông báo và nâng cấp client:** loại bỏ fallback, đồng bộ registration policy và kiểm thử end-to-end.
7. **Khôi phục kiểm soát:** thêm test chặn downgrade ở authorization endpoint **và** token endpoint, giám sát lỗi/hành vi bất thường.

**Lưu ý revocation:** nếu refresh token/grant bị thu hồi, một JWT access token đã cấp và được resource server xác minh offline có thể tiếp tục hợp lệ tới `exp` khi không có cơ chế denylist/session state. Ứng cứu phải đánh giá cả **quyền đang hoạt động tại API**, không chỉ trạng thái refresh token.

### 13.1. Quan sát mà không lưu secret

Các metric/event gợi ý:

~~~text
issuerId
clientId
authorizationRequestCount
pkceMethod=S256|plain|missing|unsupported
pkcePolicyDecision=ALLOW|DENY
tokenExchangeResult=SUCCESS|INVALID_GRANT|INVALID_CLIENT
codeReuseDetected=true|false
policyVersion
requestId
~~~

Không ghi `code_verifier`, raw authorization code, token response, client assertion, private key hoặc full URL chứa credential. Nếu dùng hashed event identifiers để liên kết sự cố, cần đánh giá chính sách dữ liệu và khả năng truy vết người dùng.

### 13.2. Ngăn policy drift khi triển khai nhiều môi trường

Có thể production từ chối plain nhưng staging lại cho phép vì thiếu cấu hình. Khi phát hành SDK mới, test cần xác nhận:

- Mọi AS instances/regions dùng cùng registration policy.
- Môi trường test phản ánh tính bắt buộc của S256, không có nhánh khác biệt che lỗi.
- Token endpoint không cho verify method khác challenge đã lưu.
- Deploy/rollback không tạo cửa sổ chấp nhận plain ngoài phạm vi được duyệt.
- Bộ test downgrade được chạy trong CI với client fixtures riêng, không sử dụng production tokens.

## 14. Sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm? | Cách sửa |
|---|---|---|
| Nghĩ thiếu method nghĩa là S256 | RFC 7636 mặc định thiếu method là **plain** | Yêu cầu khai báo `S256` tường minh |
| Chấp nhận plain với mọi client vì RFC có định nghĩa | Verifier lộ ngay trong challenge | Chỉ cho S256 với client mới |
| Client tự fallback sang plain khi lỗi S256 | Nới yếu phương thức dưới tác động lỗi/can thiệp | Fail closed, sửa AS/SDK |
| Authorization endpoint cấp code khi thiếu PKCE | Code có thể đổi không cần verifier | Bắt buộc challenge theo registration |
| Token endpoint bỏ verifier nếu client đã xác thực | Bỏ qua bảo vệ code-specific | Áp đồng thời client auth và PKCE |
| Token endpoint đọc method từ request đổi code | Attacker có thể yêu cầu hạ phương thức | Dùng method được lưu cùng code |
| Lưu challenge nhưng không lưu method | Không biết kiểm tra verifier thế nào | Lưu cả hai và chính sách gốc |
| Một verifier dùng chung nhiều tab/người dùng | Lẫn request và tăng rủi ro lộ | Verifier riêng từng authorization |
| Sinh verifier bằng timestamp/Math.random | Dễ dự đoán | CSPRNG đủ entropy |
| Dùng hash hex làm S256 challenge | Không đúng RFC encoding | SHA-256 rồi Base64url không padding |
| Chỉ kiểm tra PKCE ở client | AS vẫn có thể cấp token sai | AS cưỡng chế chính sách |
| Phát token trước khi đánh dấu code USED | Race đổi code thành công nhiều lần | Atomic single-use, transaction |
| Log URL authorization request chứa plain verifier | Tạo bản sao secret | Loại plain, redact URL/secret |
| Dùng PKCE như bằng chứng đăng nhập OIDC | Sai vai trò của PKCE | Xác minh ID token và nonce khi áp dụng |
| Dùng PKCE thay audience/scope checks | Token có thể được cấp quá quyền | Grant policy và RS authorization |
| Cho rằng PKCE chống replay access token | Bearer token vẫn có thể bị dùng lại | TTL, token storage, DPoP/mTLS khi phù hợp |

## 15. Checklist kết thúc bài

Khi thiết kế một client và AS triển khai Authorization Code + PKCE:

1. **Client type:** xác định public/confidential; confidential client phải xác thực ở token endpoint theo phương thức đăng ký.
2. **Method:** client mới **chỉ phát S256**; AS từ chối plain, thiếu method, thiếu challenge, method lạ theo policy.
3. **Verifier:** CSPRNG, 43–128 ký tự trong tập unreserved; riêng từng request, giữ trong pending state được bảo vệ.
4. **Challenge:** `BASE64URL_NO_PADDING(SHA256(ASCII(verifier)))`; không gửi verifier ở authorization endpoint.
5. **Binding:** code gắn client ID, redirect URI, challenge+method, issuer, grant, expiry và trạng thái single-use.
6. **Token exchange:** HTTP POST qua TLS, kiểm tra client, code, redirect URI và verifier theo **method đã lưu**.
7. **Fail closed:** không fallback plain, không bỏ verifier khi thiếu, không đổi code đã USED/hết hạn.
8. **Concurrency:** atomic consume code trên mọi AS nodes; xử lý retry/network timeout và revocation/audit.
9. **Request context:** state/CSRF, issuer binding, OIDC nonce khi phù hợp; không suy endpoint từ callback.
10. **Token issuance:** subject/scope/audience/TTL và client binding đúng grant; không tăng quyền tại token endpoint.
11. **Token usage:** access token đúng API, JWT/opaque validation, resource/action/tenant authorization.
12. **Refresh/lifecycle:** bảo vệ refresh token và phát hiện reuse; PKCE không thay refresh rotation.
13. **Observability:** giám sát method/rejection/attempts nhưng không log code, verifier, access/refresh token.
14. **Legacy:** ngoại lệ plain có owner, thời hạn, giới hạn registration và kế hoạch nâng cấp; ưu tiên chặn nếu rủi ro vượt ngưỡng.
15. **Kiểm thử:** authorization endpoint, token endpoint, multi-tab, multi-AS, replay, scope/audience và anti-downgrade end-to-end.

### Ghi nhớ trong một phút

~~~text
S256:
    Authorization request  -> code_challenge = BASE64URL(SHA256(verifier))
    Token request          -> code_verifier = verifier
    AS                    -> tính lại S256 và so với challenge đã lưu

plain:
    Authorization request  -> code_challenge = verifier (lộ trên front channel)
    Token request          -> code_verifier = verifier
    => Không bảo vệ như S256 khi code và request bị quan sát.

S256-only policy:
    missing challenge/method -> DENY
    method=plain             -> DENY
    method unknown           -> DENY
    verifier sai/thiếu       -> DENY
    code USED/expired        -> DENY
~~~

**Kết luận:** PKCE chỉ có ý nghĩa bảo mật khi **AS bắt buộc method phù hợp, lưu method/challenge gắn với code và kiểm tra verifier khi đổi code**. Với hệ thống mới, chọn **S256-only** thay vì cho phép `plain` hoặc tự hạ cấp vì lỗi tương thích. Ngay cả khi S256 hoạt động đúng, vẫn cần **client authentication khi áp dụng, state/issuer/redirect binding, code single-use, scope/audience phù hợp, bảo vệ access/refresh token và authorization trên tài nguyên**.

## Tài liệu tham khảo

- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636): cú pháp verifier/challenge, phương thức S256/plain, yêu cầu hỗ trợ và Appendix B test vector.
- [RFC 7636, §4.3 — Client Sends the Code Challenge with Authorization Request](https://www.rfc-editor.org/rfc/rfc7636#section-4.3): tham số `code_challenge`, `code_challenge_method` và mặc định `plain`.
- [RFC 7636, §4.6 — Server Verifies code_verifier](https://www.rfc-editor.org/rfc/rfc7636#section-4.6): xác minh verifier theo method gắn với code.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): PKCE, downgrade, code interception/injection, refresh token replay.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Authorization Code Grant, client authentication, redirect URI, token endpoint và lỗi.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): chống authorization server mix-up.
- [RFC 9101 — The OAuth 2.0 Authorization Framework: JWT-Secured Authorization Request](https://www.rfc-editor.org/rfc/rfc9101): JAR và tính toàn vẹn của authorization request khi áp dụng.
- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126): PAR và back-channel request registration.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): native redirect, external user agent và PKCE.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): khám phá issuer và endpoints đáng tin.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): issuer, audience và các claims access token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): trạng thái opaque access token.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token sau sự cố.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained tokens chống access token replay.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, nonce và liên kết với OIDC Authorization Code flow.
- [Spring Security Reference — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): authorized client và Authorization Code flow trên Java.
- [Spring Authorization Server Reference](https://docs.spring.io/spring-authorization-server/reference/): authorization endpoint, token endpoint và custom validation.
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): hướng dẫn thực hành phòng ngừa OAuth code/token leakage.
