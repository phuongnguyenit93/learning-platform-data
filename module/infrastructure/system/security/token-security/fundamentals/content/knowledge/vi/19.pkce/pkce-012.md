# Kiểm thử PKCE success và failure

Một ứng dụng nhận **authorization code** sau khi người dùng đăng nhập. Để đổi code lấy access token, ứng dụng gửi **code_verifier** đến token endpoint của Authorization Server. Nếu verifier không khớp với **code_challenge** đã gửi khi bắt đầu flow, hệ thống có bắt buộc từ chối phát token không? **Có.** Đây là điều kiện bảo mật cốt lõi của **Proof Key for Code Exchange (PKCE)**.

Tuy nhiên, chỉ có một bài test “verifier đúng thì nhận HTTP 200” là chưa đủ. Một triển khai PKCE an toàn phải chứng minh được cả hai chiều: **success khi chứng cứ và toàn bộ grant hợp lệ**, và **failure khi thiếu, sai, bị tráo, bị phát lại hoặc bị hạ cấp bất kỳ chứng cứ thiết yếu nào**. Quan trọng hơn, các trường hợp thất bại phải **không tạo ra access token hay refresh token hợp lệ**.

Bài học thuộc chương **PKCE** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Phạm vi bao gồm kiểm thử PKCE trong OAuth 2.0/OIDC Authorization Code Flow, liên hệ mô hình tin cậy của Authorization Server và Resource Server, token JWT/opaque, claims, scope, audience, refresh token, lưu trữ, thu hồi và chống credential bị đánh cắp hoặc phát lại.

Sau bài học, bạn có thể tạo cặp verifier/challenge đúng chuẩn, viết test vector, kiểm tra flow thành công từ authorization request đến token response, xây dựng negative tests và concurrency tests, phân biệt lỗi PKCE với lỗi client/redirect/code, đồng thời thiết lập kiểm thử hồi quy cho hệ thống thật.

## 1. Phải kiểm thử điều gì ở PKCE?

PKCE theo **RFC 7636** bổ sung một bí mật theo **từng authorization transaction** để bảo vệ Authorization Code Flow trước nguy cơ **authorization code interception**. Client tạo một **code_verifier** ngẫu nhiên, gửi **code_challenge** dẫn xuất từ verifier cho Authorization Server (AS) ở authorization request. Khi đổi code tại token endpoint, client chứng minh mình giữ đúng verifier đó.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as OAuth Client
    participant A as Authorization endpoint
    participant T as Token endpoint
    C->>C: Tạo V1 ngẫu nhiên
    C->>C: Challenge H1 = BASE64URL(SHA256(ASCII(V1)))
    C->>A: client_id, redirect_uri, state, H1, S256
    A->>U: Xác thực / consent theo flow
    U-->>A: Hoàn tất
    A-->>C: Authorization code C1 + state
    C->>C: Đối chiếu state và giao dịch
    C->>T: C1 + code_verifier V1
    T->>T: Kiểm client, code, URI, S256(V1) == H1
    T->>T: Tiêu thụ C1 một lần
    T-->>C: Token response nếu mọi điều kiện đạt
~~~

Bốn cam kết cần xác minh:

| Cam kết | Positive test | Negative test |
|---|---|---|
| **Challenge được ràng buộc với code** | C1 được đổi bằng verifier V1 của flow F1 | Verifier V2 của flow F2 không đổi được C1 |
| **Biến đổi S256 chuẩn xác** | AS chấp nhận giá trị challenge đúng RFC 7636 | AS từ chối verifier không tạo ra challenge đã lưu |
| **PKCE được bắt buộc khi áp dụng** | Flow có challenge hợp lệ đi hết token exchange | Không có đường bỏ verifier, đổi method hoặc fallback sang code-only |
| **Authorization code dùng một lần** | Lần đổi đầu hợp lệ thành công | Code đã dùng không tạo thêm token, kể cả yêu cầu song song |

**PKCE không thay thế** xác thực confidential client, exact redirect URI matching, **state** của client, kiểm issuer, hoặc quyền trên Resource Server. Vì vậy các bài kiểm thử tích hợp phải tách rõ lỗi PKCE với những điều kiện giao thức liên quan.

## 2. Chuẩn bị dữ liệu PKCE chính xác theo RFC 7636

**code_verifier** phải là chuỗi khó đoán, dùng ký tự unreserved của URI:

~~~text
unreserved = ALPHA / DIGIT / "-" / "." / "_" / "~"
code_verifier = 43*128unreserved
~~~

Nghĩa là verifier dài **43–128 ký tự**, chỉ dùng chữ cái Latin, chữ số và bốn ký tự **- . _ ~**. Dùng bộ sinh số ngẫu nhiên mật mã **CSPRNG** để đảm bảo entropy thực tế; một cách thông dụng là sinh **32 byte ngẫu nhiên**, rồi Base64url **không padding**, tạo verifier dài **43 ký tự**.

Với phương thức **S256**:

~~~text
code_challenge = BASE64URL-ENCODE(
    SHA256(ASCII(code_verifier))
)
code_challenge_method = S256
~~~

Kết quả S256 là Base64url của digest 32 byte, thường dài **43 ký tự**, không có dấu **=** padding. Đừng dùng Base64 thường có **+**, **/** hoặc padding khi giao thức đòi Base64url không padding. Đừng băm chuỗi challenge một lần nữa ở token endpoint hoặc dùng MD5/SHA-1.

### Test vector công khai của RFC 7636

RFC 7636 cung cấp một vector để kiểm thuật toán:

~~~text
code_verifier:
dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

code_challenge_method:
S256

expected code_challenge:
E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

Nếu thư viện tạo challenge không khớp **chính xác** chuỗi dự kiến, hãy sửa thuật toán trước khi chạy end-to-end tests. Vector này là **dữ liệu thử nghiệm công khai**, tuyệt đối không dùng verifier cố định đó cho các authorization transactions thực tế.

### Hai loại dữ liệu cho hai cấp kiểm thử

- **Unit tests:** dùng verifier cố định từ RFC để xác minh thuật toán và kiểm kiểu/độ dài; không cần browser hay Authorization Server.
- **Integration/E2E tests:** mỗi flow tạo **verifier mới** và lưu với đúng transaction/state; không tái sử dụng verifier từ test trước, ngoại trừ khi test cố ý mô phỏng sự tráo đổi.

Khi test tạo một verifier sai, cần phân biệt **sai cú pháp** và **đúng cú pháp nhưng không khớp challenge**; cả hai phải thất bại, nhưng nguyên nhân và mã lỗi có thể khác theo giao thức/chính sách.

## 3. Chuẩn bị môi trường kiểm thử OAuth an toàn

Để test PKCE có ý nghĩa, phải kiểm tra **Authorization Server đang chạy thật trong môi trường test**, không chỉ xác minh client tự tạo challenge đúng.

Ví dụ cấu hình giả định:

~~~text
issuer:                  https://auth.test.example.org
authorization_endpoint:  https://auth.test.example.org/authorize
token_endpoint:          https://auth.test.example.org/oauth2/token
client_id:               shop-web-test
client_type:             public
redirect_uri:            https://app.test.example.org/oauth/callback
expected_audience:       orders-api-test
requested_scope:         orders:read
PKCE policy:             require S256
authorization_code TTL:  ngắn, theo cấu hình test
~~~

Đây chỉ là hợp đồng test; không suy rằng mọi nhà cung cấp có cùng URL hoặc cấu hình. Đối với production, endpoint phải được lấy từ **issuer/metadata đáng tin** hoặc cấu hình quản trị chứ không chọn từ một URL chưa xác minh.

**Thiết lập test harness** nên có:

1. Client test đã đăng ký đúng **redirect URI** và grant **authorization_code**.
2. Tài khoản hoặc user test với scope/resource đã được cho phép, không dùng credential production.
3. Cách tạo giao dịch authorization mới, thu callback và lấy code một lần.
4. HTTP client gửi request **application/x-www-form-urlencoded** qua TLS đến token endpoint.
5. Cách kiểm kết quả phía AS: token issuance records, grant state hoặc audit events an toàn khi hệ thống cho phép.
6. Resource Server test hoặc token introspection để chứng minh token thành công **thực sự hợp lệ cho API**.
7. Cơ chế cô lập dữ liệu giữa test cases, tránh session/cookie/code/verifier từ test trước làm sai kết quả.

Không log raw authorization code, code_verifier, access token, refresh token hoặc ID token để “tiện đối chiếu” trong CI. Sử dụng **request ID và kết quả kiểm thử**; chỉ sử dụng credential giả có thời hạn và môi trường giới hạn.

## 4. Positive test: Authorization Code + PKCE S256 thành công

Một positive test đầy đủ cần xác minh cả request đầu và token exchange:

**Given:** client **shop-web-test** được đăng ký, PKCE S256 bật, redirect URI hợp lệ, người dùng test được phép cấp **orders:read**.

**When:** client tạo verifier V1, challenge H1 từ V1, bắt đầu authorization flow, nhận code C1, kiểm state, rồi gửi **chính V1** tới token endpoint với C1.

**Then:** AS chấp nhận grant, đánh dấu C1 đã dùng, cấp **access token với phạm vi/audience được chấp thuận**; có thể cấp refresh token hoặc ID token **chỉ nếu** flow và chính sách cho phép.

### Bước 1. Authorization request

~~~http
GET /authorize?response_type=code&client_id=shop-web-test&redirect_uri=https%3A%2F%2Fapp.test.example.org%2Foauth%2Fcallback&scope=orders%3Aread&state=<random-state-S1>&code_challenge=<S256-of-V1>&code_challenge_method=S256 HTTP/1.1
Host: auth.test.example.org
~~~

Các giá trị trong dấu ngoặc nhọn là placeholder. Trong request thật, cần **URL-encode** tham số theo đúng form/query encoding. **Không gửi code_verifier** ở authorization request.

### Bước 2. Client xử lý callback

AS redirect về URI đã đăng ký với authorization code C1 và state S1. Client test cần:

- Xác nhận **state khớp giao dịch F1** và chưa được xử lý.
- Lấy đúng **V1** đã tạo với giao dịch F1.
- Xác nhận issuer/AS đang xử lý là AS dự kiến nếu hệ thống có nhiều issuer.
- Không chuyển code qua open redirect hoặc ghi code/state vào analytics.

### Bước 3. Token request

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.test.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<C1>&redirect_uri=https%3A%2F%2Fapp.test.example.org%2Foauth%2Fcallback&client_id=shop-web-test&code_verifier=<V1>
~~~

Đây là public client minh họa. **Confidential client** phải xác thực bằng phương thức đã đăng ký; PKCE **bổ sung**, không thay thế client authentication.

### Bước 4. Kiểm token response

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<test-access-token>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders:read"
}
~~~

Đây là một **ví dụ**, không phải danh sách field bắt buộc giống nhau ở mọi profile. **expires_in=900** là TTL minh họa của access token, không phải TTL của code. Không yêu cầu **refresh_token** luôn xuất hiện: điều đó phụ thuộc client, flow và chính sách. Trong OIDC, **id_token** có thể xuất hiện theo profile.

### Assertions cho success path

- Token endpoint trả success **chỉ khi code, client, redirect URI và verifier đúng**.
- Response có access token hợp lệ, token_type và metadata theo hợp đồng.
- Resource Server test **chấp nhận access token** đúng issuer, audience, thời hạn, scope và quyền đối tượng.
- Với JWT access token, thư viện verifier kiểm chữ ký, profile và claims, không chỉ Base64url-decode payload. Với opaque access token, dùng introspection hoặc nguồn trạng thái tin cậy.
- AS xác nhận authorization code **chỉ được tiêu thụ một lần**; dùng C1 lần hai phải thất bại.
- Không có credential thô trong log, trace, analytics hay báo cáo test.

## 5. Failure test 1: verifier đúng cú pháp nhưng không khớp

Đây là negative test **quan trọng nhất** để chứng minh AS thực sự kiểm PKCE, không chỉ kiểm có field **code_verifier**.

~~~text
Flow F1:
  V1 = verifier ngẫu nhiên hợp lệ
  H1 = S256(V1)
  Authorization request gửi H1
  AS cấp code C1

Token request:
  code = C1
  code_verifier = V2   # V2 khác V1, nhưng vẫn đúng cú pháp RFC

Expected:
  Token endpoint từ chối, thường error=invalid_grant
  Không phát access/refresh token từ yêu cầu này
~~~

**V2 phải là một verifier hợp lệ về độ dài và bộ ký tự.** Nếu test cố ý gửi một chuỗi sai cú pháp, bạn chỉ chứng minh được AS kiểm format, **chưa chứng minh nó có so khớp hash/challenge**.

Một điểm dễ kiểm sai: sau request V2 thất bại, AS có thể áp dụng chính sách riêng về việc code C1 **còn được phép thử lại hay bị vô hiệu hóa**. Không mặc định đây là yêu cầu bắt buộc của RFC 7636 ở mọi triển khai. Assertion cốt lõi là **yêu cầu sai verifier không được cấp token**. Hãy tách test riêng cho chính sách tiêu thụ code khi kiểm chứng thất bại.

## 6. Failure test 2: thiếu verifier hoặc verifier sai định dạng

### 6.1. Không gửi code_verifier tại token endpoint

Nếu authorization request dùng **S256 challenge**, token request đổi code **phải chứng minh verifier**. Test gửi code C1 nhưng bỏ field code_verifier:

~~~text
grant_type=authorization_code
code=C1
client_id=shop-web-test
redirect_uri=https://app.test.example.org/oauth/callback
# Không có code_verifier
~~~

**Kỳ vọng:** AS từ chối và **không phát token**. Mã lỗi có thể là **invalid_request** khi thiếu tham số hoặc **invalid_grant** theo cách AS/profile xử lý sai proof; không nên viết test bắt buộc một mã cụ thể khi hợp đồng chưa quy định.

### 6.2. Trường rỗng, sai chiều dài hoặc bộ ký tự

Các ca cần chạy riêng:

| code_verifier gửi đến token endpoint | Trường hợp | Kết quả mong đợi |
|---|---|---|
| Không có field | Missing | Từ chối |
| Chuỗi rỗng | Empty | Từ chối |
| 42 ký tự hợp lệ | Dưới giới hạn 43 | Từ chối |
| 43 ký tự hợp lệ nhưng khác V1 | Sai chứng cứ dù đúng cú pháp | Từ chối |
| 128 ký tự hợp lệ, challenge khớp và các ràng buộc đúng | Biên tối đa hợp lệ | Có thể success |
| 129 ký tự hợp lệ | Vượt giới hạn 128 | Từ chối |
| Chứa dấu cách hoặc ký tự **+**, **/**, **=** | Sai bộ ký tự verifier | Từ chối |
| Chứa ký tự Unicode ngoài bộ unreserved | Không đúng ABNF | Từ chối |
| V1 bị thêm newline cuối chuỗi | Giá trị không còn khớp/cú pháp sai | Từ chối |

Với những test **biên 43 và 128 ký tự**, phải tạo một challenge tương ứng từ đúng verifier để phân biệt **kiểm tra cú pháp** với **kiểm tra hash**. Không dùng chuỗi quá ngắn rồi kết luận vì “PKCE mismatch” khi thực tế server từ chối do format.

### 6.3. Body và encoding không đúng

Token request OAuth 2.0 thông thường dùng **POST** và **application/x-www-form-urlencoded**. Test client phải URL-encode các trường, không để **+** hoặc **%** từ thao tác mã hóa form làm biến đổi verifier một cách ngoài ý muốn. Trường hợp body không hợp lệ nên được phân loại là lỗi request; không ghi nguyên body chứa code/verifier ra log.

## 7. Failure test 3: challenge hoặc method không an toàn tại authorization endpoint

Kiểm PKCE **không bắt đầu ở token endpoint**. Authorization Server cần lưu đúng **code_challenge và code_challenge_method** của authorization request rồi ràng buộc chúng với code sẽ phát.

### Các ca cần thử

| Authorization request | Điều phải kiểm |
|---|---|
| S256 hợp lệ | AS gắn chính challenge và method vào code |
| Thiếu code_challenge khi client/AS policy yêu cầu PKCE | **Từ chối hoặc không phát code có thể đổi theo đường code-only** |
| Có challenge nhưng thiếu code_challenge_method | RFC 7636 định nghĩa giá trị mặc định **plain**; nếu policy chỉ chấp nhận S256 phải từ chối, không tự coi mặc định là S256 |
| code_challenge_method không được AS hỗ trợ | Từ chối tại authorization endpoint theo quy tắc giao thức |
| Method được tự ý đổi từ S256 sang plain | Không được downgrade ràng buộc đã thiết lập |
| Challenge có ký tự/độ dài không hợp lệ | Từ chối theo quy tắc RFC/profile |
| Client gửi **code_verifier** ở authorization request | Không dùng verifier bị lộ để thay challenge; không ghi vào telemetry |
| Bắt đầu flow F1 rồi bắt đầu F2 | AS phải ràng buộc challenge theo **từng code**, không giữ “challenge cuối cùng của client” |

**Điểm chuẩn quan trọng:** Trong RFC 7636, nếu **code_challenge_method bị bỏ trống**, phương thức mặc định là **plain**. Vì vậy test **“bỏ method phải tự hiểu S256” là sai**. Một triển khai yêu cầu S256 nên **từ chối** request không chỉ rõ phương thức phù hợp thay vì chấp nhận hạ cấp.

Phương thức **plain** tồn tại vì khả năng tương thích của RFC, nhưng trong triển khai hiện đại nên **yêu cầu S256** khi có thể. Không viết negative test “plain luôn bị RFC cấm” cho mọi hệ thống; hãy khẳng định **plain bị từ chối vì policy S256-only** của ứng dụng đang kiểm.

### Kiểm chống downgrade

Một thử nghiệm có ý nghĩa:

1. Cấu hình AS/client **yêu cầu PKCE S256**.
2. Gửi authorization request đã bị bỏ **code_challenge** hoặc đổi phương thức thành **plain**.
3. Nếu AS vẫn phát code, thử đổi code ấy **không có verifier**.
4. **Kỳ vọng tổng thể:** không có cách nào từ yêu cầu bị hạ cấp nhận được access token hợp lệ.

Một AS chỉ kiểm PKCE khi thấy challenge nhưng cho phép client vốn phải dùng PKCE **bỏ challenge để đổi code-only** vẫn có đường bypass. Test phải đánh giá cả **authorization endpoint và token endpoint**, không chỉ test hàm băm.

## 8. Failure test 4: verifier bị tráo giữa hai flow

Đây là ca thường lộ lỗi khi client dùng biến **global/latestVerifier** hoặc AS lưu challenge theo client_id thay vì theo code.

~~~text
Flow F1:
  state=S1, code=C1, verifier=V1, challenge=H1

Flow F2:
  state=S2, code=C2, verifier=V2, challenge=H2

Case A: redeem C1 với V1 => success nếu các điều kiện khác đạt
Case B: redeem C2 với V1 => reject
Case C: redeem C1 với V2 => reject
Case D: redeem C2 với V2 => success nếu C2 chưa dùng
~~~

Để tránh trạng thái code dùng một lần làm nhiễu kết quả, **mỗi case** nên tạo những giao dịch mới, hoặc định nghĩa thứ tự rõ ràng. Chẳng hạn không thử **C1 với V1 thành công** rồi dùng chính C1 kiểm mismatch mà chỉ kết luận “PKCE đã từ chối”: khi đó AS có thể đang từ chối do code đã tiêu thụ.

**Test tốt tách từng nguyên nhân thất bại**:

- Test mismatch với code **còn hạn, chưa dùng**.
- Test reuse với code **đã dùng** nhưng verifier đúng.
- Test redirect mismatch với code chưa dùng và verifier đúng.

Đặc biệt trong SPA, mobile hoặc server nhiều phiên, client cần lưu **state → code_verifier + issuer + redirect_uri** theo từng giao dịch. Không dùng một verifier duy nhất cho tất cả phiên đăng nhập.

## 9. Failure test 5: client, redirect URI và issuer binding

PKCE không được kiểm độc lập khỏi các ràng buộc khác của Authorization Code Flow.

| Đầu vào bị thay | Kỳ vọng | Bước bảo vệ |
|---|---|---|
| Code C1 phát cho client A, client B cố đổi cùng V1 | Từ chối | **Client binding** |
| Client đúng, verifier đúng, nhưng redirect URI trong token request khác URI của authorization request | Từ chối | **Redirect URI binding** |
| Authorization request dùng redirect URI chưa đăng ký | AS không gửi code hoặc lỗi OAuth đến URI không tin cậy | **Exact redirect URI matching** |
| Client dùng code của AS1 để gọi token endpoint AS2 | Từ chối; không chuyển credential sang issuer không mong đợi | **Issuer/AS binding** |
| Confidential client gửi verifier đúng nhưng client authentication sai | Từ chối | **Client authentication** |
| Client callback nhận **state** không khớp giao dịch | Client từ chối trước khi đổi code | **Client-side CSRF/transaction defense** |

Lưu ý về test: **Verifier đúng không được “cứu” một grant sai client hoặc redirect URI**. Nên kiểm mỗi biến thể trong giao dịch mới, còn tất cả điều kiện khác hợp lệ, để xác định đúng cơ chế đang từ chối.

Trong OIDC, client còn phải kiểm **ID token** phù hợp issuer/audience/nonce theo flow. Việc PKCE thành công không tự chứng minh ID token hợp lệ và **ID token không thể dùng thay access token** tại Resource Server.

## 10. Failure test 6: code replay và race condition

**Authorization code chỉ được dùng một lần**, bất kể verifier có đúng bao nhiêu lần. Theo **RFC 6749**, lần dùng lại phải bị từ chối; khi nhận thấy replay, AS nên cân nhắc **thu hồi các token đã cấp từ code đó nếu có thể**.

### Replay tuần tự

~~~text
Given:
  C1 còn hạn, verifier V1 khớp challenge H1.

When:
  POST /token với (C1,V1) lần 1
  POST /token với (C1,V1) lần 2

Then:
  Lần 1 có thể success.
  Lần 2 phải reject (thường invalid_grant).
  Lần 2 không tạo thêm access/refresh token.
~~~

### Replay đồng thời

~~~text
AS instance A nhận (C1,V1)
AS instance B nhận (C1,V1)
Hai request được bắt đầu gần như cùng lúc.

Expected:
  Tối đa MỘT request giành quyền redeem C1.
  Không có hai bộ token hợp lệ phát hành từ cùng C1.
~~~

Không dùng khóa chỉ nằm trong **bộ nhớ một instance** để bảo vệ code khi AS chạy nhiều node. Cần cơ chế atomic compare-and-swap, row locking, transaction hoặc primitive tương đương trên **state dùng chung**.

### Một state transition khái niệm

~~~text
ISSUED
  |
  | atomic consume với code/client/redirect/PKCE hợp lệ
  v
CONSUMED  ---> mọi lần redeem tiếp theo: REJECT

ISSUED  ---> EXPIRED/REVOKED: REJECT
~~~

**Điểm kiểm thử:** Đếm cả **token issuance records** và **kết quả truy cập Resource Server**, không chỉ số lượng HTTP 200. Một AS có thể trả lỗi 500 ở một request nhưng vẫn phát token hợp lệ trong backend; đó vẫn là lỗi cần phát hiện.

## 11. Failure test 7: timeout, retry và code đã bị tiêu thụ

Giả sử client gửi C1+V1 tới token endpoint, AS đã tiêu thụ code và cấp token, nhưng response bị mất do lỗi mạng. Client không biết request có thành công không và tự động gửi lại C1+V1.

**Kỳ vọng an toàn:** AS không phát token mới từ cùng code. Client không nên retry token request như một thao tác idempotent thông thường; nếu không có cơ chế khôi phục được bảo vệ riêng và phù hợp giao thức, hãy bắt đầu **authorization flow mới**.

| Tình huống | Kết quả mong đợi |
|---|---|
| Client nhận response thành công | Lưu token hợp lệ, dừng sử dụng C1 |
| Response bị mất sau khi C1 được consume | Retry cùng C1 bị từ chối; client xử lý flow mới |
| AS lỗi trước khi trạng thái consume được commit | Không phát token không có bản ghi hợp lệ; retry chịu kiểm tra lại và policy |
| Browser callback được nạp lại | Client không gửi lại C1 như một authorization mới |
| Hai tab xử lý cùng callback | Client dùng state/transaction single-use để giảm double redemption; AS vẫn bảo vệ atomic |

**Không sửa lỗi retry bằng cách kéo dài TTL của code hoặc cho phép code được đổi hai lần**. TTL và single-use là hai yêu cầu độc lập. Nếu có cơ chế phục hồi riêng, cần phân tích bảo mật đầy đủ và không được làm mất yêu cầu chống replay.

## 12. Các mã lỗi: assert theo đúng nguyên nhân và hợp đồng

PKCE failure thường được thể hiện qua response lỗi của token endpoint theo OAuth 2.0:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_grant"
}
~~~

**invalid_grant** là mã điển hình khi **code không hợp lệ hoặc verifier không khớp**. Tuy nhiên cần phân biệt:

| Ngữ cảnh | Mã lỗi thường gặp | Assertion quan trọng hơn |
|---|---|---|
| Verifier sai dù đúng cú pháp | **invalid_grant** | Không có token được phát |
| Code hết hạn/đã dùng/sai binding | **invalid_grant** | Không có token được phát |
| Token request thiếu trường bắt buộc hoặc sai định dạng | **invalid_request** hoặc lỗi grant thích hợp theo profile | Không có token được phát |
| Authorization request dùng method/challenge không hợp lệ | Lỗi tại authorization endpoint, thường **invalid_request** hoặc mã tương ứng | Không phát hành code đổi được theo đường bypass |
| Confidential client xác thực thất bại | **invalid_client**, có thể HTTP 401/challenge | Không được bỏ qua xác thực client |
| Client không được phép dùng grant | **unauthorized_client** | Không phát token |

**Không phải mọi lỗi đều HTTP 400**, đặc biệt với client authentication. Tests nên kiểm **error code theo spec/profile đang áp dụng**, không bắt buộc mọi AS trả cùng error_description. Không đưa **code, verifier, access token hoặc refresh token** vào error response.

**HTTP 4xx chưa đủ chứng minh PKCE được bảo vệ.** Sau một negative request, hãy xác nhận token issuance count không tăng và không có token nào vừa được tạo có thể gọi Resource Server.

## 13. Java: tạo verifier/challenge và unit tests với RFC vector

Ví dụ Java dưới đây nhằm **minh họa tính toán PKCE phía client và unit testing**, không phải một OAuth client hoặc Authorization Server hoàn chỉnh.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.regex.Pattern;

public final class Pkce {
    private static final SecureRandom RNG = new SecureRandom();
    private static final Pattern VERIFIER =
            Pattern.compile("[A-Za-z0-9._~-]{43,128}");

    private Pkce() {}

    public static String newVerifier() {
        byte[] randomBytes = new byte[32];
        RNG.nextBytes(randomBytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(randomBytes);
    }

    public static String s256(String verifier)
            throws NoSuchAlgorithmException {
        if (verifier == null ||
                !VERIFIER.matcher(verifier).matches()) {
            throw new IllegalArgumentException("Invalid PKCE verifier");
        }
        byte[] hash = MessageDigest.getInstance("SHA-256")
                .digest(verifier.getBytes(StandardCharsets.US_ASCII));
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(hash);
    }
}
~~~

**Vì sao chọn 32 byte ngẫu nhiên?** Base64url không padding của 32 byte tạo chuỗi 43 ký tự phù hợp RFC 7636 và giữ 256 bit entropy từ CSPRNG. Không lấy verifier từ timestamp, email, user ID, UUID cố định hay **Math.random**.

JUnit 5 test:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

public class PkceTest {
    @Test
    void rfc7636S256Vector() throws Exception {
        String verifier =
                "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
        assertEquals(
                "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                Pkce.s256(verifier));
    }

    @Test
    void generatedVerifierHasValidShape() throws Exception {
        String verifier = Pkce.newVerifier();
        assertEquals(43, verifier.length());
        assertTrue(verifier.matches("[A-Za-z0-9._~-]{43,128}"));
        assertEquals(43, Pkce.s256(verifier).length());
    }

    @Test
    void changedVerifierProducesDifferentChallenge() throws Exception {
        String original =
                "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
        String changed = "A" + original.substring(1);
        assertNotEquals(Pkce.s256(original), Pkce.s256(changed));
    }

    @Test
    void verifierOutsideRfcSyntaxIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> Pkce.s256("too-short"));
        assertThrows(IllegalArgumentException.class,
                () -> Pkce.s256("a".repeat(129)));
    }
}
~~~

Những test này kiểm **thuật toán client**. Chúng **không chứng minh Authorization Server thực thi PKCE**. Một AS có lỗi bỏ qua code_verifier vẫn cho phép unit tests trên pass. Vì vậy phải có **integration tests chạy qua authorization endpoint/token endpoint thật của môi trường kiểm thử**.

## 14. Thiết kế integration tests: Given – When – Then

Một harness nên có thao tác:

~~~text
newAuthorizationFlow(client, redirect, scopes, challenge, method)
    -> { code, state, expectedIssuer, flowId }

redeem(code, verifier, client, redirect)
    -> { httpStatus, oauthError, tokensOrNone }

inspectIssuedTokens(flowId)
    -> token issuance records / safe counters

callTestResourceServer(accessToken)
    -> Permit hoặc Reject theo audience/scope/policy
~~~

Đây là **giao diện khái niệm** để viết test, không phải API có sẵn của thư viện cụ thể. Đừng bỏ qua bước authorization bằng cách tự chế ra authorization code trong database nếu mục tiêu là kiểm tra AS có **lưu challenge gắn với code** thật hay không.

### Case success

~~~text
given:
  V1 = randomValidVerifier()
  H1 = s256(V1)
  F1 = beginAuthorizationWithS256(H1)
when:
  result = redeem(F1.code, V1, expectedClient, expectedRedirect)
then:
  assert result.success
  assert tokenIsValidForExpectedResource(result.accessToken)
  assert exactlyOneRedemption(F1.code)
~~~

### Case wrong verifier

~~~text
given:
  V1, V2 = twoDifferentValidVerifiers()
  F1 = beginAuthorizationWithS256(s256(V1))
when:
  result = redeem(F1.code, V2, expectedClient, expectedRedirect)
then:
  assert result.rejected
  assert noNewAccessOrRefreshTokenForThisRequest()
~~~

### Case downgrade

~~~text
given:
  AS policy requires S256
when:
  authorization request omits code_challenge
  OR declares code_challenge_method=plain
then:
  assert noAuthorizationCodeUsableWithoutS256Proof()
  assert noSuccessfulCodeOnlyExchange()
~~~

**Điểm cốt lõi:** test cần đảm bảo dữ liệu đầu vào không vô tình sai thêm các điều kiện khác. Nếu muốn chứng minh **PKCE mismatch** được phát hiện, hãy dùng **client, redirect, code, TTL đều hợp lệ**, chỉ đổi verifier.

## 15. Ma trận kiểm thử PKCE success và failure

| ID | Test case | Kết quả kỳ vọng |
|---|---|---|
| **S01** | S256 đúng, verifier đúng, code chưa dùng, client/redirect hợp lệ | **Success**, cấp token trong quyền được phép |
| **S02** | Verifier 43 ký tự hợp lệ, challenge được tính đúng | Success khi toàn flow hợp lệ |
| **S03** | Verifier 128 ký tự hợp lệ, challenge được tính đúng | Success khi toàn flow hợp lệ |
| **S04** | RFC 7636 known vector | Challenge khớp chính xác giá trị chuẩn |
| **F01** | Verifier hợp lệ nhưng khác verifier gốc | **Reject**, không cấp token |
| **F02** | Thiếu code_verifier | Reject |
| **F03** | code_verifier rỗng | Reject |
| **F04** | Verifier dài 42 ký tự | Reject |
| **F05** | Verifier dài 129 ký tự | Reject |
| **F06** | Verifier có dấu cách, Unicode hoặc ký tự ngoài ABNF | Reject |
| **F07** | Challenge S256 được tạo sai, verifier gửi đúng giá trị client đã giữ | Reject vì không khớp challenge |
| **F08** | Thiếu challenge khi client/AS yêu cầu PKCE | Không có code-only path được cấp token |
| **F09** | Bỏ code_challenge_method trên hệ thống S256-only | Reject, không fallback sang plain |
| **F10** | Method không được hỗ trợ | Reject |
| **F11** | Đổi method từ S256 sang plain | Reject theo policy, không downgrade |
| **F12** | Dùng verifier flow F2 cho code flow F1 | Reject |
| **F13** | Code của client A được đổi bởi client B | Reject |
| **F14** | Code đúng nhưng redirect_uri ở token request khác URI gốc | Reject |
| **F15** | Code hết hạn | Reject |
| **F16** | Code đã dùng gửi lại cùng verifier đúng | Reject, không phát token mới |
| **F17** | Hai token requests cùng code trên hai AS instances | Tối đa một lần redeem thành công |
| **F18** | state callback không khớp flow | Client không đổi code |
| **F19** | Code của issuer A được gửi đến token endpoint issuer B | Reject/chặn sai issuer |
| **F20** | Confidential client có PKCE đúng nhưng client authentication thất bại | Reject |
| **F21** | Token endpoint mất response sau khi code đã consume | Retry không tạo token mới; client phục hồi an toàn |
| **F22** | JWT/opaque access token đúng nhưng thiếu scope với API | API từ chối phân quyền, dù PKCE đã success |
| **F23** | ID token được gửi như access token đến Resource Server | API từ chối sai loại/audience |
| **F24** | Bật debug/tracing trên callback và token endpoint | Không có code/verifier/access/refresh token thô trong telemetry |

**S01–S03** yêu cầu không chỉ token endpoint success, mà token phải được tạo cho **issuer/audience/scope thực sự được chấp thuận**. **F01, F07, F12** cần cẩn thận tránh nhiễu bởi code đã dùng hoặc hết hạn. **F16/F17** phải kiểm token issuance ở backend, không chỉ HTTP response.

## 16. PKCE success không thay thế token validation và authorization

Sau khi AS cấp token từ một authorization code có PKCE hợp lệ, Resource Server vẫn phải kiểm các điều kiện khác:

| Điều kiện | JWT access token | Opaque access token |
|---|---|---|
| **Issuer** | Chữ ký/key và **iss** của nguồn AS được tin | Introspection/nguồn trạng thái từ AS được cấu hình tin |
| **Audience** | **aud** chứa API dự kiến | Metadata/audience binding theo hợp đồng introspection |
| **Thời hạn** | **exp**, **nbf** và các điều kiện profile | Trạng thái **active** và thời hạn theo nguồn đáng tin |
| **Token type** | Access token đúng profile, không phải ID/refresh token | Nguồn introspection phân biệt access/refresh token |
| **Scope** | Quyền được cấp phù hợp endpoint | Scope được xác nhận theo hợp đồng |
| **Quyền tài nguyên** | Tenant, ownership, role, trạng thái hiện hành | Cùng chính sách nghiệp vụ |

**Không được lấy success PKCE làm chứng cứ đủ để gọi mọi API.** Ví dụ, code đã đổi thành access token có **aud=orders-api, scope=orders:read** không cho phép gọi **payments-api** hoặc thao tác **orders:write**. Resource Server tiếp tục xác minh nguồn phát hành và chính sách quyền của chính mình.

Refresh token nếu được cấp phải **chỉ gửi tới Authorization Server** khi cần làm mới, có client binding, rotation hoặc sender-constraining theo chính sách; nó **không** được dùng để thay access token trong header Bearer ở Resource Server.

Với OIDC, client còn phải xác minh ID token theo issuer, audience là **client_id**, thời hạn và nonce/điều kiện flow khi áp dụng. PKCE không làm OIDC ID token trở thành access token.

## 17. Chống lộ credential khi viết test và báo cáo CI

PKCE thử nghiệm liên quan đến các giá trị nhạy cảm:

- **Authorization code:** credential ngắn hạn, dùng một lần.
- **code_verifier:** bí mật của giao dịch; cùng với code có thể đủ để thử đổi code trong một số mô hình.
- **Access token:** có thể bị phát lại tại đúng Resource Server khi còn hiệu lực.
- **Refresh token:** có thể được dùng xin access token mới nếu còn hợp lệ và không bị các cơ chế ràng buộc chặn.
- **Client secret/private key:** credential xác thực confidential client, phải được bảo vệ độc lập.

**Không in raw Authorization headers, token request bodies, redirect URLs có code/state, JWT payload đầy đủ hoặc token responses vào CI artifacts**. Debug một test PKCE thất bại nên ghi lý do được chuẩn hóa:

~~~json
{
  "test": "pkce_wrong_verifier_rejected",
  "outcome": "passed",
  "expected_error": "invalid_grant",
  "observed_error": "invalid_grant",
  "trace_id": "test-trace-184",
  "issued_token_count_delta": 0
}
~~~

Đây là dữ liệu giả. Một số field, như **trace_id**, phải là giá trị an toàn được tạo bởi test/ứng dụng, không lấy nguyên token làm correlation ID. Nếu thực sự cần nhận diện một giao dịch ở AS, dùng **flow reference/grant reference nội bộ** đã được bảo vệ, không ghi raw code hoặc verifier.

Đừng dùng token production trong công cụ online để “kiểm chữ ký hoặc decode JWT”. Dùng môi trường test, test issuer, test clients và test secrets có vòng đời ngắn; xóa dữ liệu test, giới hạn quyền xem CI artifacts và giám sát log/tracing collector.

## 18. Những lỗi khiến test pass nhưng hệ thống vẫn không an toàn

1. **Chỉ test hàm S256 ở client.** Hàm có thể đúng nhưng AS bỏ qua verifier.
2. **Chỉ test success.** Không phát hiện đường bỏ PKCE hoặc chấp nhận verifier sai.
3. **Dùng verifier sai cú pháp để test mismatch.** AS có thể chỉ từ chối do regex, không phải do kiểm S256.
4. **Dùng code đã tiêu thụ khi test wrong verifier.** Từ chối có thể do replay chứ không phải mismatch.
5. **Thử method plain nhưng không biết policy.** RFC cho phép method plain trong ngữ cảnh tương thích, trong khi hệ thống có thể yêu cầu S256-only; phải xác định hợp đồng test.
6. **Test chỉ sửa client, không đi qua AS.** Không phát hiện AS không gắn challenge vào code.
7. **Tin client_id như bằng chứng client authentication.** Public client ID không phải bí mật; confidential client vẫn phải xác thực.
8. **Bỏ redirect URI và state.** PKCE đúng nhưng code có thể bị xử lý trong phiên/callback sai.
9. **Không test race condition.** Hai request có thể cùng đổi code nếu AS dùng read-then-update không atomic.
10. **Chỉ kiểm HTTP status.** AS có thể đã phát token hoặc lưu refresh token dù trả 500.
11. **Gửi lại cùng code sau timeout như retry idempotent.** Có thể tạo cảnh báo replay hoặc lỗi phiên; không phải hành vi chuẩn an toàn.
12. **Log toàn bộ token request để debug.** Làm rò code_verifier, code và credential, tự tạo nguy cơ PKCE đang cố giảm.
13. **Coi token sau PKCE là đủ phân quyền.** API vẫn phải kiểm issuer, audience, scope, thời hạn và quyền tài nguyên.
14. **Trộn verifier của nhiều tab/flow.** Dùng biến global/latestVerifier thay vì lưu theo state/transaction.

## 19. Checklist chạy kiểm thử PKCE trong CI

1. **Policy:** Client và AS có yêu cầu **S256** rõ ràng, không có đường downgrade sang code-only?
2. **CSPRNG:** Verifier được tạo ngẫu nhiên đủ entropy, không tái sử dụng giữa các flow thực tế?
3. **Format:** Verifier 43–128 ký tự unreserved và challenge đúng Base64url(SHA256(ASCII(verifier))) không padding?
4. **Vector:** Unit test khớp RFC 7636 S256 vector chính xác?
5. **Success:** Full Authorization Code Flow nhận code, đối chiếu state rồi đổi token bằng verifier đúng?
6. **Mismatch:** Verifier khác nhưng đúng cú pháp bị từ chối khi code chưa dùng và mọi điều kiện khác hợp lệ?
7. **Missing/malformed:** Thiếu, rỗng, quá ngắn/dài, sai ký tự đều bị từ chối?
8. **Challenge/method:** Challenge không hợp lệ, method sai và yêu cầu không PKCE đều bị xử lý theo policy, không bypass?
9. **Binding:** Code đúng client, redirect URI, PKCE challenge và expected issuer của giao dịch?
10. **Multi-flow:** Hai authorization transactions song song không trộn verifier/challenge/state?
11. **Single-use:** Code đã dùng không cấp thêm token; cạnh tranh giữa AS instances chỉ có tối đa một redemption?
12. **Timeout/retry:** Client không tự retry code vô hạn; AS không phát token thêm khi response mất?
13. **Result:** Success token hợp lệ cho issuer/audience/scope dự kiến; negative request không phát access/refresh token?
14. **RS:** Resource Server từ chối ID token/refresh token và access token sai audience/scope?
15. **Privacy:** CI logs, gateway/APM/tracing và callback không chứa raw code/verifier/token?
16. **Isolation:** Dùng client, tài khoản, khóa và token test; dữ liệu được reset hoặc cô lập theo từng case?
17. **Regression:** Mỗi thay đổi AS, client SDK, redirect URI, proxy hoặc OAuth/OIDC configuration đều chạy lại test suite?

## 20. Câu hỏi tự đánh giá

**1. Một PKCE success test cần chứng minh gì?** Client gửi verifier đúng của code đã được cấp, AS xác minh toàn bộ grant, cấp token hợp lệ một lần, và Resource Server chỉ nhận token đúng audience/scope/policy.

**2. Vì sao phải thử verifier sai nhưng đúng cú pháp?** Để chứng minh AS so khớp **S256(verifier)** với challenge gắn cùng code, thay vì chỉ kiểm có field hoặc kiểm regex.

**3. Verifier có thể dài 42 ký tự không?** Không. RFC 7636 quy định **43–128 ký tự** từ tập unreserved.

**4. Với S256, code_challenge có dấu = padding ở cuối không?** Không. Base64url encoding của digest được dùng **không padding**.

**5. Bỏ code_challenge_method thì AS có tự hiểu S256 không?** Không theo RFC 7636; mặc định là **plain**. Một AS dùng policy S256-only nên từ chối thay vì vô tình hạ cấp.

**6. PKCE có thay thế xác thực confidential client không?** Không. Client vẫn phải xác thực khi profile/đăng ký yêu cầu.

**7. Client có thể dùng verifier từ flow F2 để đổi code của F1 không?** Không. Challenge được gắn với từng code/transaction; F2 verifier khác phải bị từ chối.

**8. Đổi cùng code với đúng verifier lần hai có được cấp token không?** Không. Authorization code phải là **single-use** và AS phải xử lý atomic trong môi trường nhiều request/instance.

**9. Nếu token endpoint trả 400 trong negative test, đã đủ chứng minh an toàn chưa?** Chưa. Cần xác minh **không có token mới hợp lệ nào được phát** và không có side effect cấp quyền.

**10. Một access token nhận sau PKCE thành công có thể gọi bất kỳ API nào không?** Không. Resource Server vẫn kiểm issuer, audience, thời hạn, scope và quyền tài nguyên.

**Ghi nhớ:** **Kiểm thử PKCE phải chứng minh cả success và failure ở đúng Authorization Server, không chỉ kiểm hàm băm của client.** Success yêu cầu verifier khớp challenge S256 đã gắn với code hợp lệ; failure bao gồm verifier sai/thiếu, method bị hạ cấp, code sai binding, code đã dùng, request song song và retry. Mọi failure phải **không phát token mới**. Sau khi PKCE pass và token được cấp, Resource Server vẫn phải xác minh **issuer, audience, scope, thời hạn và quyền truy cập tài nguyên**.
