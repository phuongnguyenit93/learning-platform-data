# Kiểm thử luân chuyển, khóa không khớp và nguồn JWKS bị gián đoạn

Trong **Spring Security OAuth 2.0 / OIDC Resource Server**, một JWT access token có thể được xác minh bằng khóa công khai lấy từ **JSON Web Key Set (JWKS)** của Authorization Server. Khóa ký không tồn tại mãi mãi: tổ chức có thể thay khóa định kỳ, thay khẩn cấp khi nghi bị lộ hoặc thay đổi thuật toán theo kế hoạch. Trong các thời điểm chuyển tiếp, Resource Server phải xử lý đúng token ký bằng khóa cũ, khóa mới và những token có chữ ký/khóa không khớp. Đồng thời, JWKS endpoint có thể tạm ngừng do mạng, DNS, TLS, proxy hoặc chính Authorization Server gặp sự cố.

Điểm khó nằm ở chỗ **ba việc khác nhau cần được kiểm thử riêng**:

1. **Luân chuyển khóa (key rotation):** Tập khóa được công bố thay đổi theo thời gian, trong khi JWT cũ và mới có thể cùng còn hiệu lực.
2. **Khóa không khớp (key mismatch):** JWT mang `kid` lạ, chữ ký không tương ứng public key, thuật toán sai hoặc khóa không thuộc issuer tin cậy.
3. **Nguồn JWKS gián đoạn:** Resource Server không tải được tập khóa, hoặc cache cũ không đủ để kiểm tra token mới.

Nếu xử lý sai, hệ thống có thể từ chối hàng loạt token hợp lệ trong lúc chuyển khóa; nghiêm trọng hơn, API có thể vô tình **bỏ xác minh chữ ký** để khắc phục lỗi tạm thời. Mục tiêu của kiểm thử là duy trì khả năng phục vụ trong giới hạn an toàn, **không bao giờ chấp nhận token chưa xác minh**.

> **Nguyên tắc xuyên suốt:** JWKS cho Resource Server biết *những khóa công khai nào được tin để xác minh chữ ký*; `kid` giúp *tìm khóa ứng viên*; chữ ký và các JWT validators mới xác nhận token có được API chấp nhận. Khi thiếu khóa hoặc JWKS không truy cập được, API không được tự coi Bearer token là hợp lệ.

## 1. Mô hình đơn giản để hiểu quá trình xác minh

Giả sử một hệ thống bán hàng có:

- **Identity Server:** Authorization Server phát hành JWT access token cho ứng dụng.
- **Orders API:** Spring Security Resource Server chỉ nhận access token có `aud` chứa `orders-api`.
- **Shop Web:** OAuth2 Client mang token gọi Orders API.
- **JWKS endpoint:** `https://identity.example.test/realms/shop/protocol/openid-connect/certs` (URI minh họa).

Ở thời điểm ban đầu, Identity Server ký JWT bằng private key **A**. JWKS công bố public key **A**. JWT có JWS header:

~~~json
{
  "alg": "RS256",
  "kid": "key-A",
  "typ": "at+jwt"
}
~~~

JWT payload minh họa:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1893456000,
  "exp": 1893456900
}
~~~

Khi Orders API nhận token, một trình tự khái niệm là:

~~~mermaid
sequenceDiagram
    participant C as OAuth2 Client
    participant R as Orders API
    participant J as JWKS Endpoint

    C->>R: Authorization: Bearer JWT (kid=key-A)
    R->>R: Phân tích JOSE header theo chính sách
    opt Chưa có khóa công khai phù hợp
        R->>J: Yêu cầu JWKS từ issuer đã tin
        J-->>R: Public JWK A, B, ...
    end
    R->>R: Chọn JWK ứng viên theo kid/alg/kty
    R->>R: Xác minh chữ ký JWS
    R->>R: Kiểm tra iss, aud, exp, nbf, loại token
    R->>R: Kiểm tra scope và quyền trên dữ liệu
    R-->>C: Tài nguyên hoặc lỗi
~~~

**Có thể đọc `kid` trước khi xác minh**, vì thư viện cần nó để chọn khóa ứng viên. Tuy nhiên, `kid` và toàn bộ header lúc đó là dữ liệu do phía gửi kiểm soát, chỉ được dùng trong **tập khóa/thuật toán đã ràng buộc với issuer tin cậy**. Không cho phép token tự chọn một JWKS URI tùy ý và bắt API tin public key từ đó.

### 1.1. JWK, JWKS, `kid` và thuật toán khác nhau thế nào?

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **JWK (JSON Web Key)** | Biểu diễn một khóa bằng JSON | RSA public key có `kty`, `n`, `e`, `kid` |
| **JWKS (JSON Web Key Set)** | Tập hợp các JWK, cho phép công bố nhiều khóa cùng lúc | `{"keys":[keyA,keyB]}` |
| **`kid` (Key ID)** | Gợi ý chọn khóa ứng viên từ JWKS | `key-A`, `key-B` |
| **`alg`** | Thuật toán bảo vệ được khai báo trong JOSE header | `RS256` |
| **Issuer (`iss`)** | Nguồn phát hành mà API chấp nhận | `https://identity.example.test/realms/shop` |
| **Audience (`aud`)** | API được phép nhận access token | `orders-api` |

Một public RSA JWK có hình thức:

~~~json
{
  "kty": "RSA",
  "use": "sig",
  "kid": "key-A",
  "alg": "RS256",
  "n": "<base64url-modulus>",
  "e": "AQAB"
}
~~~

Giá trị `n` ở đây được viết thành placeholder, **không phải khóa thật**. Trong một public JWKS, không được công bố các trường private key như RSA `d`, `p`, `q`. Private signing key phải được quản lý ở Authorization Server/HSM/KMS hoặc dịch vụ ký được ủy quyền.

Không phải mọi issuer đều cung cấp `alg` hoặc `use` trong từng JWK. Bộ xác minh phải kết hợp yêu cầu của định dạng khóa, JOSE header và **chính sách thuật toán được cấu hình**, không suy ra tin cậy chỉ từ một field.

### 1.2. Kiểm thử JWKS khác kiểm thử quyền

**Xác minh chữ ký** trả lời “JWT này có phù hợp khóa ký được tin cậy không?”; **validate claims** trả lời “Token có từ issuer đúng, dành cho API này, còn hạn và đúng mục đích không?”; **authorization** trả lời “Caller có đủ scope và quyền truy cập dữ liệu không?”.

Một JWT ký đúng bằng key B nhưng có `aud = billing-api` vẫn phải bị Orders API từ chối. Không nên để các bài kiểm thử rotation chỉ kiểm tra chữ ký mà bỏ qua những điều kiện còn lại.

## 2. Vòng đời luân chuyển khóa an toàn

Khi thay khóa ký định kỳ, cách triển khai phổ biến là **công bố khóa mới trước khi bắt đầu ký bằng khóa mới**, giữ khóa cũ khi còn token cũ hợp lệ, rồi mới rút khóa cũ.

~~~mermaid
flowchart LR
    S0["T0: JWKS có A; AS ký A"]
    S1["T1: JWKS có A+B; AS vẫn ký A"]
    S2["T2: JWKS có A+B; AS chuyển sang ký B"]
    S3["T3: Token ký A hết hạn; JWKS giữ B"]
    S0 --> S1 --> S2 --> S3
~~~

| Giai đoạn | JWKS công bố | Khóa AS dùng ký token mới | Token mà Resource Server cần chấp nhận |
| --- | --- | --- | --- |
| **T0 — trước rotation** | A | A | A nếu token còn hạn, đúng audience/quyền |
| **T1 — pre-publish** | A và B | A | Token A; API đã có cơ hội tải B |
| **T2 — chuyển ký** | A và B | B | Token A và token B còn hạn |
| **T3 — kết thúc grace period** | B | B | B; token A chỉ còn được chấp nhận nếu chính sách tin cậy vẫn cho phép, nhưng mục tiêu là A đã hết hạn |

Các khoảng T1–T3 không có độ dài cố định theo OAuth2/JWKS. Đội quản lý Authorization Server phải tính đến:

- **Thời hạn access token dài nhất** được ký bằng A, cộng dung sai clock skew và thời gian chậm truyền/lưu trữ theo chính sách.
- **Khoảng refresh/cache JWKS** của các Resource Server, kể cả pod ít lưu lượng.
- **Rolling deployment**, autoscaling, instance mới và instance đang có cache cũ.
- **Replication/CDN/Proxy cache** của endpoint JWKS, nếu có.
- Quy tắc thu hồi khóa khẩn cấp, khác rotation định kỳ.

### 2.1. Vì sao cần pre-publish khóa B?

Nếu AS bắt đầu ký bằng B **trước khi** mọi API có khả năng thấy public key B, nhiều token hợp lệ sẽ bị từ chối do `kid = key-B` chưa được biết đến. Một số thư viện JWKS có cơ chế refresh khi gặp `kid` mới; nhưng refresh vẫn cần endpoint JWKS phục vụ ổn định, và hành vi cụ thể phụ thuộc cache/phiên bản thư viện.

**Pre-publish giúp giảm rủi ro**, nhưng kiểm thử phải chứng minh API cuối cùng tải/chọn được khóa B theo cơ chế thực sự của ứng dụng. Không được giả định rằng một request `kid` lạ luôn khiến cache refresh tức thời.

### 2.2. Vì sao chưa được rút A ngay khi bắt đầu ký B?

Access token đã phát hành bằng A vẫn còn hạn sau thời điểm T2. Nếu JWKS lập tức xóa A, instance mới hoặc instance refresh JWKS có thể không xác minh được những token cũ ấy. Kết quả là logout/lỗi 401 hàng loạt dù token chưa đến `exp`.

Trong rotation theo kế hoạch, giữ public key A ở JWKS **đủ lâu** để các token do A ký hết hạn theo chính sách. Chỉ sau đó mới ngừng công bố A. Với khóa **nghi đã bị lộ**, phải đánh giá ngoại lệ bảo mật: có thể cần rút/khóa A ngay và chấp nhận việc token cũ mất hiệu lực, thay vì ưu tiên trải nghiệm đăng nhập liên tục.

## 3. Mục tiêu của bộ kiểm thử

Bộ kiểm thử nên bao phủ cả **đúng** và **sai**, trong ít nhất ba trạng thái hạ tầng:

1. **JWKS hoạt động bình thường** và công bố một hoặc nhiều public key.
2. **JWKS trả dữ liệu lỗi/không phù hợp** như key khác với `kid`, định dạng sai, HTTP 5xx hoặc phản hồi không hợp lệ.
3. **JWKS không truy cập được** trong lúc cache có/không có khóa đã biết.

Mỗi test cần chỉ ra:

- **Tập khóa phía AS công bố** trước khi gửi request.
- **Khóa thực tế dùng ký JWT** (A, B hay khóa của một bên không đáng tin).
- **JOSE header**, nhất là `alg` và `kid`.
- **Trạng thái bộ nhớ/cache JWKS của Resource Server**.
- **Issuer, audience và thời hạn token**.
- **Phản hồi dự kiến**: authenticated, denied do token không hợp lệ, hay lỗi dependency; không chỉ nhìn một mã HTTP.

Một bảng test có thể dùng:

| Test | JWKS hiện tại | JWT dùng khóa | Điều kiện thêm | Kết quả mong đợi |
| --- | --- | --- | --- | --- |
| R1 — baseline | A | A | `kid = A`, còn hạn | Chữ ký hợp lệ; tiếp tục kiểm tra claims/quyền |
| R2 — pre-publish | A+B | A | B chưa ký token mới | Token A tiếp tục hợp lệ |
| R3 — switch signer | A+B | B | API đã có B hoặc làm mới JWKS được | Token B hợp lệ |
| R4 — grace period | A+B | A | Token A chưa hết hạn | Token A vẫn hợp lệ |
| R5 — retire old key | B | A | Token A đã hết hạn | Token bị từ chối; không được dùng key A đã hết hạn tin cậy theo chính sách |
| R6 — unknown kid | A+B | C | `kid = C` không nằm trong nguồn khóa tin cậy | Token bị từ chối |
| R7 — wrong signature | A+B | C | Header ghi `kid = A` nhưng ký bằng private key C | Chữ ký không hợp lệ; từ chối |
| R8 — wrong algorithm | A+B | Khóa không phù hợp | `alg` không được API cho phép | Từ chối |
| R9 — wrong issuer | A+B | A | `iss` khác issuer được cấu hình | Từ chối |
| R10 — wrong audience | A+B | A | `aud = billing-api` | Từ chối |
| R11 — expired | A+B | A | `exp` trong quá khứ | Từ chối |
| R12 — insufficient scope | A+B | A | Token đúng nhưng không có `orders.read` | Chữ ký/token hợp lệ; authorization từ chối |

**Quan trọng ở R5:** Một bản sao cache còn public key A có thể tiếp tục xác minh chữ ký A về mặt mật mã. Điều bảo đảm token cũ không được dùng sau grace period trước hết là **`exp`**, chính sách tin cậy khóa và cơ chế refresh/retirement. Nếu kiểm thử chính sách rút khóa trước khi token hết hạn, phải kiểm soát cache hoặc cơ chế blocklist để tất cả instance ngừng tin A theo yêu cầu. Chỉ xóa A khỏi JWKS không đảm bảo mọi cache lập tức quên A.

## 4. Kiểm thử luân chuyển khóa theo từng bước

### 4.1. Bước chuẩn bị: hai cặp khóa độc lập

Trong test, tạo hai cặp RSA khác nhau:

~~~text
KeyPair A:
  private A -> ký JWT cũ
  public  A -> công bố qua JWKS, kid=key-A

KeyPair B:
  private B -> ký JWT mới
  public  B -> công bố qua JWKS, kid=key-B
~~~

Để test tái lập được, mỗi khóa có `kid` khác nhau. **Không dùng khóa ký production trong fixture**. Trong bài kiểm thử, JWKS mock chỉ công bố **public key**, còn private key chỉ tồn tại trong process/test fixture.

### 4.2. Bước T0: xác minh token A

Mock JWKS ban đầu:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "key-A",
      "alg": "RS256",
      "n": "<A-public-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

AS mock tạo JWT JWS RS256 với `kid = key-A`, `iss` và `aud` đúng. Resource Server xác minh thành công, ánh xạ `scope = orders.read` thành authority tương ứng, và endpoint dùng quyền đó có thể thực thi.

Nên thực hiện hai lần gọi liên tiếp để quan sát trường hợp **khóa được tải lần đầu** và **khóa đã có ở cache**. Không dựa duy nhất vào HTTP 200; cần xác nhận request thực sự qua validator và policy, đồng thời kiểm tra số lần fetch JWKS nếu muốn hiểu cache.

### 4.3. Bước T1: JWKS công bố đồng thời A và B

Mock JWKS đổi thành:

~~~json
{
  "keys": [
    { "kty": "RSA", "use": "sig", "kid": "key-A",
      "alg": "RS256", "n": "<A-public-modulus>", "e": "AQAB" },
    { "kty": "RSA", "use": "sig", "kid": "key-B",
      "alg": "RS256", "n": "<B-public-modulus>", "e": "AQAB" }
  ]
}
~~~

AS vẫn ký A. Kiểm tra JWT A không bị từ chối do tập JWKS thêm B. Đây là phép thử regression quan trọng: thêm khóa không được làm vô hiệu những khóa vẫn hợp lệ.

Với cache của Resource Server, **thay đổi payload ở mock JWKS chưa chắc đã lập tức thay đổi tập khóa đang dùng trong decoder**. Nếu test cần chứng minh behavior sau refresh, hãy kiểm soát cơ chế cache/TTL, kích hoạt refresh theo đặc tính thư viện hoặc dùng một decoder mới cho phép thử không phụ thuộc cache.

### 4.4. Bước T2: chuyển AS sang ký B

AS bắt đầu tạo JWT có `kid = key-B`, ký bằng private key B. Resource Server phải tìm được public key B từ nguồn tin cậy và chấp nhận JWT B sau khi kiểm tra đầy đủ claims.

Đồng thời gửi lại một JWT ký A **chưa hết hạn**. Trong giai đoạn chuyển tiếp, **cả hai JWT A/B đều phải xác minh được** nếu chính sách vẫn tin hai khóa.

Đây là test có giá trị nhất của rotation: kiểm tra nhiều token còn hiệu lực cùng tồn tại khi hệ thống cập nhật signer.

### 4.5. Bước T3: hoàn tất thời gian chuyển tiếp

Khi JWT A cuối cùng đã hết hạn và kế hoạch rotation cho phép, JWKS chỉ giữ B. Kiểm thử JWT mới ký B tiếp tục hợp lệ, JWT A hết hạn bị từ chối. Nếu muốn thử việc **rút A trong lúc một JWT A vẫn chưa hết hạn**, đó là kịch bản thu hồi khóa khác và phải xác định rõ xử lý cache còn A thế nào.

## 5. Khóa không khớp: không chỉ có `kid` lạ

Các lỗi “key mismatch” có hình thức khác nhau. Nếu gom tất cả thành một case, dễ bỏ sót rủi ro bảo mật.

### 5.1. `kid` không tồn tại trong JWKS

JWKS công bố A và B; token có header:

~~~json
{"alg": "RS256", "kid": "key-C", "typ": "at+jwt"}
~~~

Nếu không có public key ứng viên được phép để xác minh token này, Resource Server phải từ chối. Một số JWKS client thử refresh khi gặp `kid` chưa biết; refresh chỉ được truy cập **JWKS URI đã cấu hình đáng tin**. Sau khi refresh mà vẫn không có khóa, kết quả vẫn là thất bại xác minh.

### 5.2. `kid` đúng nhưng chữ ký được tạo bởi khóa khác

Token ghi `kid = key-A` nhưng ký bằng private key C. Đây là test mạnh hơn việc chỉ kiểm tra `kid` lạ:

~~~text
JWKS        -> public key A
JWS header  -> kid = key-A
JWS signer  -> private key C
Kết quả     -> verify thất bại
~~~

Nếu API chỉ tra `kid` rồi tin claim, test này sẽ phát hiện lỗi. `kid` **không phải bằng chứng** token được ký bởi private key tương ứng.

### 5.3. Có đúng `kid` nhưng key material bị thay

JWKS trả về một JWK có `kid = key-A` nhưng `n`/`e` khác public key A đã dùng để ký token. Chữ ký không thể xác minh bằng key material ấy. Tình huống này có thể do cấu hình sai, cache/proxy cũ hoặc sự cố nhà phát hành.

**Không khắc phục bằng cách bỏ xác minh chữ ký.** Kiểm tra tính nhất quán của JWKS đang công bố, thời điểm signer thay đổi, cache và định danh khóa.

### 5.4. Thuật toán hoặc loại khóa không phù hợp

Các trường hợp cần từ chối:

- API được cấu hình nhận **RS256**, token tự khai `alg = HS256`.
- JWT dùng `alg = none` trong ngữ cảnh bắt buộc signed access token.
- JWKS chỉ có khóa EC nhưng header yêu cầu thuật toán RSA không phù hợp.
- JWK không được phép dùng cho mục đích ký theo chính sách, hoặc header dùng thuật toán không nằm trong allowlist.
- Token chỉ tới nguồn JWK không được cấu hình đáng tin.

Danh sách thuật toán được chấp nhận phải do Resource Server cấu hình theo hợp đồng với issuer, **không do token tự quyết định**. Kiểm thử nên tạo JWT theo đúng dạng không được cho phép rồi xác nhận không có `Authentication` đáng tin.

### 5.5. Chữ ký đúng nhưng claims sai

Một JWT dùng private key A hợp lệ nhưng có `iss` sai, `aud` sai, `exp` đã qua hoặc token sai mục đích vẫn phải bị từ chối. Cần đưa các test này vào cùng suite để tránh suy diễn “rotate đúng” đồng nghĩa “security đúng”.

### 5.6. JWKS malformed hoặc không phù hợp

Hãy thử JWKS trả:

~~~json
{"keys": []}
~~~

hoặc JSON sai cú pháp, JWK thiếu trường bắt buộc, trường khóa không thể parse, nhiều khóa gây mơ hồ hoặc HTTP response không đúng định dạng. **Kết quả an toàn là không có chữ ký nào được xem là đã xác minh khi thiếu khóa phù hợp**. Tùy implementation, ứng dụng có thể dùng cache cũ còn hợp lệ hoặc trả lỗi xác thực/phụ thuộc; không được tạo authority từ payload chưa xác minh.

## 6. Nguồn JWKS gián đoạn: kiểm tra cache nóng và cache lạnh

Một câu dễ gây hiểu nhầm là “JWT là self-contained nên Authorization Server có down thì API vẫn chạy”. JWT ký bất đối xứng **có thể** được xác minh cục bộ **khi Resource Server có khóa công khai phù hợp**. Việc tải khóa từ JWKS vẫn tạo phụ thuộc mạng tại một số thời điểm.

### 6.1. Cache nóng: đã có public key

Kịch bản:

1. JWKS đang hoạt động, trả public key A.
2. Resource Server xác minh JWT A thành công, có cơ hội lưu A trong cache của JWKS client.
3. JWKS endpoint bắt đầu trả 503 hoặc không thể kết nối.
4. Client tiếp tục gửi JWT A còn hạn, đúng issuer, audience và scope.

Trong nhiều cấu hình, **JWT A có thể tiếp tục được xác minh** nếu public key A còn ở cache và cache được phép sử dụng. Kết quả phụ thuộc vào thư viện, phiên bản, TTL, chính sách refresh, cơ chế retry và thời điểm kiểm thử.

**Không khẳng định cache tồn tại vô hạn.** Test phải xác định rõ cache được cấu hình thế nào; nếu cache hết hạn/bị loại, decoder có thể cần fetch JWKS và request thất bại.

### 6.2. Cache lạnh: instance mới chưa có key

Kịch bản:

1. Resource Server được dựng mới, chưa từng tải JWKS.
2. JWKS endpoint trả 503, timeout hoặc DNS lỗi.
3. Client gửi JWT A còn hạn.

Nếu không có khóa A từ nguồn tin cậy, API không xác minh được chữ ký. Request phải **thất bại an toàn**. Dù JSON chứa `scope = orders.read`, không được biến claim này thành authority.

### 6.3. Cache có A, token mới ký B

Kịch bản:

1. Resource Server chỉ đang giữ public key A.
2. Authorization Server chuyển sang ký bằng B.
3. JWKS endpoint down.
4. Client gửi JWT B với `kid = key-B`.

Vì không có public key B phù hợp, API không thể xác minh chữ ký của JWT B. Đây là rủi ro lớn khi không pre-publish B hoặc rotation trùng đợt outage.

### 6.4. Cache có A, nhưng JWKS đã rút A

Đây là trường hợp chiều ngược lại. JWKS mới chỉ công bố B, nhưng một pod vẫn còn A trong cache. Token A có thể vẫn qua được **bước chữ ký** trong khoảng cache còn tin A. Việc có nên tiếp tục chấp nhận phụ thuộc:

- Token A còn hạn hay không.
- Chính sách rotation bình thường hay **thu hồi khóa khẩn cấp**.
- Thời gian tối đa cho phép giữ cache.
- Cơ chế phân phối tín hiệu thu hồi hoặc tái tạo decoder khi cần.

**Xóa khóa khỏi endpoint chưa đủ để bảo đảm rút khóa ngay trên mọi pod.** Bài kiểm thử emergency rotation phải chứng minh yêu cầu về thời gian ngừng chấp nhận khóa cũ, không dựa vào suy đoán.

### 6.5. Ma trận outage có thể đưa vào integration test

| Trạng thái Resource Server | Trạng thái JWKS | Token gửi đến | Kỳ vọng |
| --- | --- | --- | --- |
| Cache lạnh | JWKS hoạt động | Token A | Có thể tải A và xác minh |
| Cache lạnh | JWKS 503/timeout | Token A | Không có key thì không thể xác minh |
| Cache ấm, chứa A và còn được dùng | JWKS 503/timeout | Token A còn hạn | Có thể xác minh theo cache policy |
| Cache ấm, chỉ có A | JWKS 503/timeout | Token B | Không thể xác minh B |
| Cache A+B | JWKS 503/timeout | Token A/B còn hạn | Có thể xác minh nếu cache được phép dùng |
| Cache quá hạn/bị loại | JWKS 503/timeout | Token từng hợp lệ | Có thể thất bại do không còn key sử dụng được |
| Cache A, JWKS vừa rút A | JWKS hoạt động | Token A chưa hết hạn | Hành vi phụ thuộc cache/retirement policy; không mặc nhiên fail ngay |
| Cache B, JWKS hoạt động | Token A ký sai/không có A | Token A | Phải từ chối nếu không có khóa A tin cậy |

**Điểm cần đo:** không chỉ status của request, mà cả số lần HTTP GET JWKS, thời gian chờ, tỷ lệ cache hit/miss nếu có metric, key id được sử dụng, số lần retry và hành vi khi key mới xuất hiện.

## 7. Khởi tạo Resource Server khi discovery hoặc JWKS down

Hai endpoint phục vụ hai mục tiêu:

- **Issuer discovery:** tìm metadata, bao gồm JWKS URI, từ issuer.
- **JWKS retrieval:** lấy public keys để kiểm tra JWT.

Với Spring Boot, một cấu hình ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}
~~~

Khi đã biết trực tiếp `jwk-set-uri`, ứng dụng có thể không cần liên lạc metadata endpoint chỉ để *tìm vị trí khóa* trong quá trình khởi tạo. Vẫn phải kiểm tra issuer. Tuy nhiên, `jwk-set-uri` **không có nghĩa khóa đã được tải sẵn**; request đầu tiên vẫn có thể cần gọi JWKS.

Nếu chỉ có `issuer-uri`, tùy phiên bản/cách cấu hình decoder, issuer discovery có thể diễn ra khi khởi tạo hoặc được trì hoãn. Vì vậy cần kiểm thử đúng phiên bản Spring Boot/Spring Security sử dụng, thay vì suy ra hành vi startup từ tên property.

### Ba phép thử startup hữu ích

1. **Chỉ issuer URI, metadata không truy cập được:** quan sát decoder/app khởi tạo thế nào và request đầu tiên thất bại ở bước nào.
2. **Issuer URI + JWKS URI rõ ràng, metadata không truy cập được:** xác nhận không bắt buộc discovery để định vị JWKS, đồng thời vẫn kiểm tra `iss`.
3. **JWKS URI rõ ràng nhưng endpoint JWKS down:** xác nhận startup và request verification là hai giai đoạn riêng; ứng dụng có thể chạy nhưng request không xác minh được.

Không giải quyết outage bằng cách tắt signature validator. Mục tiêu là làm rõ phụ thuộc và thời điểm tải khóa để xây chiến lược availability phù hợp.

## 8. Cấu hình Spring Security để kiểm tra JWT và audience

Ví dụ với **Spring Boot 3 / Spring Security 6**, Orders API dùng signed JWT:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}

app:
  security:
    audience: ${OAUTH_API_AUDIENCE}
~~~

Ví dụ environment values:

~~~text
OAUTH_ISSUER_URI=https://identity.example.test/realms/shop
OAUTH_JWKS_URI=https://identity.example.test/realms/shop/protocol/openid-connect/certs
OAUTH_API_AUDIENCE=orders-api
~~~

Các URI chỉ minh họa; phải sử dụng endpoint chính xác do issuer tin cậy công bố.

### 8.1. Decoder với kiểm tra chữ ký, issuer, audience và thời hạn

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class JwtVerificationConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}")
            String jwksUri,
            @Value("${app.security.audience}")
            String expectedAudience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withJwkSetUri(jwksUri)
                // Ví dụ hợp đồng issuer sử dụng RS256.
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(expectedAudience)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                            "invalid_token",
                            "Token has an unexpected audience",
                            null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(standard, audience));
        return decoder;
    }
}
~~~

Đoạn code này không thực hiện rotation bằng tay; **NimbusJwtDecoder** dùng khóa từ JWKS endpoint đã cấu hình để xác minh JWS theo các cơ chế thư viện hỗ trợ. Khả năng fetch/refresh/cache/timeout cụ thể phải được kiểm tra với phiên bản đang chạy. `JwtValidators.createDefaultWithIssuer` giúp giữ các kiểm tra JWT mặc định và issuer; validator bổ sung bảo đảm audience phù hợp Orders API.

Nếu nhà phát hành dùng thuật toán khác hoặc cần danh sách thuật toán được cho phép rộng hơn, hãy cấu hình **đúng theo hợp đồng issuer**, không lấy `alg` của token chưa tin cậy làm chính sách.

### 8.2. Chỉ ánh xạ quyền sau khi xác minh thành công

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersApiSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Ví dụ giả định `/api/**` là REST API xác thực chỉ bằng Bearer token, vì thế CSRF được tắt trong filter chain này. Nếu ứng dụng phục vụ browser dùng cookie/session, phải thiết kế CSRF và filter chain riêng phù hợp. Scope `orders.read` là điều kiện gọi endpoint; quyền đọc **đơn hàng cụ thể** vẫn cần kiểm tra owner/tenant ở service nghiệp vụ.

**Ranh giới không được phá vỡ khi JWKS down:** `JwtDecoder` thất bại thì không tạo một `Authentication` giả với `SCOPE_orders.read` chỉ để request “đi tiếp”. Endpoint phải từ chối token chưa xác minh.

## 9. Tạo môi trường kiểm thử JWKS có thể điều khiển

Khi kiểm thử rotation/outage, không nên dùng JWKS production thật. Tốt hơn là dùng **HTTP mock server** có thể thay tập JWK và trạng thái phản hồi theo kịch bản. Các lựa chọn quen thuộc là **OkHttp MockWebServer** hoặc **WireMock** trong integration test.

Các thành phần fixture:

~~~text
Test issuer       = https://issuer.example.test (giá trị claim)
Local JWKS URL    = http://127.0.0.1:<random-port>/jwks
RSA private key A = test-only signer cũ
RSA public  key A = JWKS entry kid=key-A
RSA private key B = test-only signer mới
RSA public  key B = JWKS entry kid=key-B
JWT audience      = orders-api
JWT scope         = orders.read
~~~

**Issuer claim có thể là một URI logic** trong bài kiểm thử trong khi JWKS HTTP endpoint nằm tại localhost, miễn decoder được cấu hình riêng issuer và JWKS URI; không dùng quy tắc này để bỏ kiểm tra issuer trong production. Khi test end-to-end cả metadata discovery, mock metadata phải khai báo issuer và `jwks_uri` nhất quán theo hợp đồng.

### 9.1. Tạo JWK và signed JWT thật cho fixture

Với Java, có thể dùng thư viện **Nimbus JOSE + JWT** (được Spring Security dùng cho xử lý JWT) để tạo cặp khóa và ký token trong test. Ví dụ helper cho test:

~~~java
import java.time.Instant;
import java.util.Date;
import java.util.List;

import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

final class TestJwtKeys {

    static RSAKey newRsaKey(String kid) throws Exception {
        return new RSAKeyGenerator(2048)
                .keyID(kid)
                .generate();
    }

    static String publicJwks(RSAKey... keys) {
        return new JWKSet(
                java.util.Arrays.stream(keys)
                    .map(RSAKey::toPublicJWK)
                    .toList())
                .toString();
    }

    static String signedAccessToken(
            RSAKey signingKey,
            String issuer,
            String audience,
            String subject) throws Exception {

        Instant now = Instant.now();

        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .issuer(issuer)
                .subject(subject)
                .audience(audience)
                .issueTime(Date.from(now))
                .notBeforeTime(Date.from(now.minusSeconds(5)))
                .expirationTime(Date.from(now.plusSeconds(300)))
                .claim("scope", "orders.read")
                .build();

        JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256)
                .keyID(signingKey.getKeyID())
                .type(new JOSEObjectType("at+jwt"))
                .build();

        SignedJWT jwt = new SignedJWT(header, claims);
        jwt.sign(new RSASSASigner(signingKey.toPrivateKey()));
        return jwt.serialize();
    }

    private TestJwtKeys() {}
}
~~~

Helper tạo **token đã được ký thật bằng RSA** chứ không chỉ xây JSON hay Base64URL. Khi test key mismatch, nên tạo private key C độc lập, cho JWT header báo `kid = key-A` nhưng ký bằng C; cách đó xác nhận Resource Server **thật sự kiểm tra chữ ký**.

Đoạn ví dụ dùng `Stream.toList()` nên giả định **Java 16+**; ứng dụng dùng Java thấp hơn có thể thay bằng `Collectors.toList()`. Các khóa sinh ra chỉ dành cho fixture và không lưu vào repository dưới dạng private key dùng chung.

### 9.2. Mock JWKS endpoint: thay tập khóa và giả lập lỗi

Ví dụ pseudocode cho fixture HTTP:

~~~java
// Pseudocode minh họa; tên API cụ thể phụ thuộc MockWebServer/WireMock.
setJwksResponse(200, publicJwks(keyA));          // T0
assertAccepted(sign(keyA, "key-A"));

setJwksResponse(200, publicJwks(keyA, keyB));    // T1
refreshJwksAccordingToTestCachePolicy();
assertAccepted(sign(keyA, "key-A"));

assertAccepted(sign(keyB, "key-B"));              // T2
assertAccepted(sign(keyA, "key-A"));              // Grace period

setJwksResponse(503, "Service Unavailable");     // Outage
assertNeverAcceptedIfSignatureCannotBeVerified();
~~~

Pseudocode này **không phải test có thể chạy nguyên xi**; những helper như `refreshJwksAccordingToTestCachePolicy()` được viết theo thư viện/cache thực tế. Mục đích là tách **state của JWKS server** khỏi **state cache của decoder**, để mỗi test kiểm soát và ghi nhận trạng thái đang được kiểm thử.

### 9.3. Integration test tối thiểu bằng MockWebServer

Ví dụ một test có thể chạy với **JUnit Jupiter, OkHttp MockWebServer và Nimbus JOSE/JWT**, sau khi thêm các test dependencies tương ứng:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.nimbusds.jose.jwk.RSAKey;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

class JwksVerificationTest {
    private static final String ISSUER =
            "https://issuer.example.test";
    private static final String AUDIENCE = "orders-api";

    private MockWebServer jwksServer;
    private RSAKey keyA;
    private NimbusJwtDecoder decoder;

    @BeforeEach
    void setUp() throws Exception {
        keyA = TestJwtKeys.newRsaKey("key-A");
        jwksServer = new MockWebServer();
        jwksServer.start();

        decoder = NimbusJwtDecoder
                .withJwkSetUri(jwksServer.url("/jwks").toString())
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> expectedAudience = jwt ->
                jwt.getAudience().contains(AUDIENCE)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                "invalid_token",
                                "wrong audience",
                                null));
        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                expectedAudience));
    }

    @AfterEach
    void tearDown() throws Exception {
        jwksServer.shutdown();
    }

    @Test
    void acceptsTokenSignedWithTrustedKey() throws Exception {
        jwksServer.enqueue(new MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody(TestJwtKeys.publicJwks(keyA)));

        String token = TestJwtKeys.signedAccessToken(
                keyA, ISSUER, AUDIENCE, "user-42");

        Jwt verified = decoder.decode(token);
        assertEquals("user-42", verified.getSubject());
    }

    @Test
    void rejectsTokenSignedWithDifferentPrivateKey() throws Exception {
        jwksServer.enqueue(new MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody(TestJwtKeys.publicJwks(keyA)));

        // Key vật lý khác A nhưng dùng cùng kid để thử signature.
        RSAKey fakeA = TestJwtKeys.newRsaKey("key-A");
        String forged = TestJwtKeys.signedAccessToken(
                fakeA, ISSUER, AUDIENCE, "user-42");

        assertThrows(JwtException.class,
                () -> decoder.decode(forged));
    }

    @Test
    void refusesColdCacheWhenJwksIsUnavailable() throws Exception {
        jwksServer.enqueue(new MockResponse()
                .setResponseCode(503));

        String token = TestJwtKeys.signedAccessToken(
                keyA, ISSUER, AUDIENCE, "user-42");

        assertThrows(JwtException.class,
                () -> decoder.decode(token));
    }
}
~~~

Đây là **ví dụ minh họa cho bài học**, áp dụng API JUnit/MockWebServer/Nimbus phổ biến; phiên bản dự án thực tế cần khai báo các test dependencies tương ứng và có thể điều chỉnh package/API của thư viện. Ba test đã tách được: **khóa đúng**, **`kid` trùng nhưng chữ ký sai**, và **JWKS không truy cập được khi cache lạnh**.

Trong bộ test rotation đầy đủ, cần thêm HTTP mock có thể thay phản hồi giữa chừng và kiểm soát cache decoder. Không viết assertion giả định JWKS refresh đúng ngay request đầu tiên khi chưa hiểu chính sách cache của phiên bản hiện tại.

### 9.4. Kiểm thử API HTTP thay vì chỉ decoder

Test `JwtDecoder` tập trung vào xác minh token. Ở lớp HTTP, dùng `MockMvc` hoặc test client với **JWT thật** để chứng minh token bị từ chối **trước khi** request vào controller. Ví dụ ma trận:

~~~text
GET /api/orders/42
  Token ký A đúng issuer/aud/scope -> qua lớp JWT/scope;
                                      sau đó data policy quyết định
  Token ký sai                      -> authentication thất bại
  Token đúng chữ ký nhưng aud sai  -> authentication thất bại
  Token đúng nhưng thiếu scope     -> authentication thành công,
                                      authorization thất bại
~~~

Với test API bảo vệ OAuth2, **`SecurityMockMvcRequestPostProcessors.jwt()`** hữu ích khi muốn test mapping authority hoặc chính sách endpoint mà **không cần** chữ ký. Nhưng nó **không thay thế được** kiểm thử JWS/JWKS/rotation thật, vì helper này tạo authentication cho request test mà không đi qua xác minh chữ ký như Bearer token production.

Muốn test rotation hoặc mismatch, phải gửi **Bearer JWT đã được ký thật** qua filter chain sử dụng decoder đang cấu hình, hoặc kiểm thử trực tiếp decoder bằng các token đã ký như ví dụ ở trên.

## 10. Giải thích lỗi trong quá trình kiểm thử

Các lỗi có thể giống nhau ở HTTP layer nhưng xuất phát từ nhiều nguồn:

| Dấu hiệu | Nguyên nhân khả dĩ | Cách phân biệt |
| --- | --- | --- |
| Unknown `kid` | JWT do khóa mới, JWKS chưa refresh, hoặc token giả | So khớp `kid` với JWKS từ issuer tin cậy và lịch rotation |
| Signature mismatch | Private key ký không khớp public JWK; token bị sửa | Xác nhận signer và public key; không chỉ nhìn `kid` |
| Unsupported `alg` | Token khai thuật toán ngoài allowlist hoặc sai loại khóa | Kiểm tra policy thuật toán của decoder |
| HTTP 404/500/503 ở JWKS | Endpoint sai, dependency gặp sự cố | Kiểm tra URL, network, server logs, status |
| Timeout/DNS/TLS error | Không thể lấy khóa từ nguồn tin cậy | Kiểm tra DNS, CA/truststore, network policy, timeout |
| Invalid JWKS JSON | Response không đúng format hoặc khóa không parse được | Kiểm tra JWK shape, JSON, Content-Type và log parser |
| Token expired | `exp` trong quá khứ | Xem thời gian, clock skew, thời gian sống |
| Invalid issuer/audience | Token không dành cho môi trường/API này | Kiểm tra `iss`/`aud` và cấu hình theo môi trường |
| Insufficient scope | JWT hợp lệ nhưng thiếu authority cần thiết | Xem `scope`/`scp` mapping và endpoint policy |

Với Bearer authentication, **token không hợp lệ** thường dẫn đến **401 Unauthorized**. Token hợp lệ nhưng **thiếu quyền** thường dẫn đến **403 Forbidden**. Tuy nhiên lỗi **không tải được JWKS** là lỗi dependency/network; mã HTTP cụ thể có thể khác theo phiên bản, cách map exception và configuration. Trong test nên khẳng định **không có thao tác được bảo vệ nào được thực thi**, đồng thời phân loại lỗi ở lớp decoder/observability; không chỉ hardcode mọi outage phải có cùng một mã 401.

### 10.1. Các log nên có

Khi cần chẩn đoán, nên ghi:

- Request/correlation ID, instance/pod ID và endpoint.
- Trạng thái truy cập JWKS, độ trễ fetch, lỗi mạng và mã HTTP.
- Issuer/JWKS URI **được cấu hình**; `kid` và `alg` từ token chỉ được xem là **input chưa tin cậy** cho tới khi xác minh.
- Loại lỗi: unknown key, invalid signature, issuer mismatch, audience mismatch, expired token, insufficient scope.
- Số lần refresh JWKS, cache hits/misses nếu thư viện/công cụ quan sát cung cấp.

**Không log nguyên access token**, private signing key, client secret hoặc những claims không cần thiết. Khi dùng `kid` trong log hay metric, cần giới hạn độ dài/số lượng giá trị vì token chưa xác minh có thể mang `kid` do attacker đặt, dẫn tới cardinality cao hoặc log injection nếu không xử lý.

## 11. Key rotation và caching: các giả định cần tránh

### 11.1. Không áp đặt một TTL cố định cho mọi phiên bản

Không nên viết test:

~~~text
JWKS chắc chắn được cache 5 phút.
Sau đúng 5 phút mọi pod phải refresh.
Gặp kid lạ mọi phiên bản Nimbus sẽ fetch JWKS ngay.
~~~

Thời gian cache, chính sách refresh khi key miss, HTTP cache headers, retry và eager/lazy fetching là chi tiết **implementation**. Chúng có thể khác giữa phiên bản Spring Security, Nimbus JOSE/JWT, cấu hình decoder và cache tùy biến.

Khi test:

1. Xác định thư viện/phiên bản đang chạy.
2. Cố định cơ chế cache dùng trong fixture nếu cần tính xác định.
3. Khi mô phỏng cache cũ, **đảm bảo thực sự đã làm ấm cache A trước**.
4. Khi mô phỏng cache lạnh, dùng **decoder/instance mới**.
5. Khi mô phỏng refresh, kiểm soát/quan sát request tới mock JWKS.
6. Đo hành vi khi cache hết hạn, key không tìm thấy hoặc mạng timeout.

### 11.2. Không tin rằng JWKS endpoint rút khóa sẽ vô hiệu lập tức token cũ

Token `kid = key-A` có thể tiếp tục xác minh bằng public key A đang cache, dù endpoint JWKS không còn công bố A. Trong rotation định kỳ điều này đôi khi được tính đến; trong sự cố khóa bị lộ, đây là rủi ro lớn.

Một phương án **emergency key revocation** có thể cần:

- Rút khả năng ký bằng private key A ở Authorization Server.
- Ngừng tin A ở Resource Server bằng refresh cache bắt buộc/tái cấu hình decoder/đẩy deny-list khóa hoặc cơ chế tương đương đã được thiết kế.
- Thu hồi các credential liên quan và đánh giá token đã phát.
- Quan sát tất cả pod/region để bảo đảm không nơi nào còn chấp nhận A ngoài chính sách.

Không có bảo đảm thu hồi tức thời chỉ bằng một thao tác xóa entry trong JWKS. Đây là điểm cần kiểm thử end-to-end theo thời gian mục tiêu của tổ chức.

### 11.3. Đồng thời có nhiều instance

Trong một deployment có 10 pod, mỗi pod có thể có trạng thái cache và thời điểm JWKS refresh khác nhau:

~~~text
Pod 1: cache A+B  -> nhận token B
Pod 2: cache A    -> phải refresh khi thấy B
Pod 3: cache trống, JWKS down -> không xác minh được
Pod 4: cache A+B nhưng hết hạn -> phụ thuộc refresh/cache policy
~~~

Do đó, bài kiểm thử staging nên có **rolling restart**, **autoscaling**, **đa vùng**, **restart giữa lúc rotation** và **outage trùng thời điểm key B bắt đầu được dùng**. Một test đơn JVM không đủ chứng minh rủi ro cache lệch giữa nhiều instance đã được kiểm soát.

## 12. Quy trình kiểm thử gợi ý cho CI và staging

### Tầng 1 — Unit test logic validation

Tập trung:

- Audience phải chứa `orders-api`.
- Issuer phải đúng issuer tin cậy.
- Token chưa hết hạn, `nbf` hợp lệ.
- Scope được ánh xạ đúng thành `SCOPE_orders.read`.
- Không chấp nhận ID token thay OAuth2 access token theo profile.

Các test này không nhất thiết phải dùng JWKS thật, vì mục tiêu là validator và quy tắc authorization.

### Tầng 2 — Integration test decoder với local JWKS

Sử dụng **JWT ký thật**, mock JWKS và các case R1–R12. Thêm scenario:

- Key B được pre-publish, rồi AS chuyển sang ký B.
- Token A/B cùng còn hạn trong grace period.
- Không có key / sai chữ ký / sai `alg`.
- JWKS trả 503, timeout, JSON lỗi.
- Cache lạnh và cache đã có khóa phù hợp.

Khi test ràng buộc trên thời gian, nên sử dụng clock có thể kiểm soát cho chính sách application hoặc tạo JWT có `exp` đủ xa/gần một cách có chủ đích; tránh phụ thuộc `Thread.sleep` dài và các race condition khó tái lập.

### Tầng 3 — Kiểm thử filter chain

Gửi HTTP Bearer JWT thật đến Spring Security Resource Server:

~~~text
Valid JWT + scope + đúng quyền dữ liệu -> 2xx
Invalid signature                     -> từ chối trước controller
Unknown kid, không có trusted key    -> từ chối
Wrong issuer/audience                -> từ chối
Valid JWT thiếu scope                -> 403 theo security config
Valid JWT đủ scope, sai owner        -> 403/404 theo data policy
~~~

Test cần bảo đảm controller/service không nhận một `Authentication` đáng tin khi chữ ký JWT sai, kể cả trong lúc JWKS endpoint down.

### Tầng 4 — Staging fault injection

Trong staging, có thể mô phỏng:

1. Khóa A đang dùng và cache đã ấm trên các pod.
2. Chặn endpoint JWKS bằng network fault hoặc trả 503.
3. Gửi token A còn hạn và token B chưa từng công bố.
4. Quan sát các pod cũ/mới và retry.
5. Cho JWKS hoạt động lại, pre-publish B rồi đổi signer sang B.
6. Chạy rolling restart/autoscaling.
7. Rút A sau grace period hoặc thử emergency rotation trong môi trường cách ly.

Lưu ý **không gây sự cố thật ở production** chỉ để chứng minh bài học. Staging cần có khóa ký riêng, token riêng và dữ liệu riêng, không dùng private key production để tạo test.

### 12.1. Bảng bằng chứng cần lưu

| Bằng chứng | Nội dung |
| --- | --- |
| Phiên bản | Spring Boot, Spring Security, Nimbus/JWK client, thư viện test |
| Kịch bản | JWKS A/A+B/B, signer A/B/C, trạng thái cache, outage |
| Hợp đồng token | Issuer, audience, thuật toán, thời hạn, scope |
| Kết quả | Token được chấp nhận hay từ chối, vị trí failure |
| Quan sát | Số HTTP request tới JWKS, latency, timeout, loại lỗi, pod |
| Khả năng phục hồi | Khi JWKS phục hồi hoặc khi cache refresh được, token hợp lệ mới có được xác minh không |
| Quyết định bảo mật | Không có token chưa xác minh nào được phép qua policy |

Giữ bằng chứng **không chứa private key hoặc nguyên Bearer token**. Có thể lưu test `kid`, kết quả validator và request ID theo chính sách nội bộ.

## 13. Runbook khi key rotation hoặc JWKS gặp lỗi

### Trường hợp 1 — Token mới bị 401 ngay sau rotation

Kiểm tra theo thứ tự:

1. Token mới thực tế dùng `kid` nào và thuật toán nào? Đây là dữ liệu chưa đáng tin cho tới khi token được xác minh, nhưng giúp xác định hướng lỗi.
2. JWKS được API cấu hình có công bố public key tương ứng không?
3. Key material có thực sự khớp private key signer mới không?
4. Pod bị lỗi đã refresh JWKS hay còn cache cũ?
5. Issuer/audience/thời hạn của token có đúng không?
6. AS có chuyển signer **trước khi** B được pre-publish và các API có cơ hội làm mới cache không?

Nếu nguyên nhân là khóa chưa công bố hoặc cache chưa refresh, sửa quy trình rotation/khả năng tải JWKS. **Không tắt verify JWS** để API tạm nhận token.

### Trường hợp 2 — Cùng token chạy ở pod A, lỗi ở pod B

Khả năng cao là trạng thái cache khác nhau, nhưng vẫn cần xác minh từ log decoder. Kiểm tra:

- Thời điểm startup/restart của từng pod.
- JWKS GET gần nhất, kết quả và cache expiration.
- `kid`/thuật toán của token, cùng cấu hình issuer/JWKS/audience trên cả hai pod.
- Network route, TLS truststore và DNS giữa từng pod và endpoint JWKS.

Không nên kết luận token bị sửa chỉ từ việc một instance thành công và một instance thất bại.

### Trường hợp 3 — JWKS tạm ngừng

1. Kiểm tra endpoint thực sự down hay do DNS/TLS/firewall/proxy.
2. Xác định instance nào còn khóa phù hợp trong cache theo policy.
3. Giữ các kiểm tra chữ ký/claims; **không fail open**.
4. Hạn chế retry storm bằng timeout/backoff phù hợp.
5. Theo dõi 401/lỗi phụ thuộc và tình trạng token mới có `kid` chưa biết.
6. Khi endpoint hồi phục, theo dõi refresh/cập nhật khóa và phục hồi xác minh.

**Cache nóng có thể duy trì xác minh một số JWT**, nhưng đây không phải lý do cho phép token lạ hoặc kéo dài thời hạn token.

### Trường hợp 4 — Nghi ngờ private key bị lộ

Đây là **rotation khẩn cấp**, không theo chu kỳ bình thường:

- Ngừng ký token mới bằng khóa nghi bị lộ, tạo khóa thay thế theo quy trình quản trị khóa.
- Phối hợp giữa AS, Resource Server, nền tảng phân phối cấu hình và đội ứng phó sự cố để ngừng tin khóa cũ trong khoảng thời gian mục tiêu.
- Đánh giá các token đã phát và các ảnh hưởng tới người dùng/Client.
- Xác nhận từng pod/region không còn chấp nhận JWT giả mạo bằng khóa bị thu hồi.
- Theo dõi kết quả và rà soát root cause, log truy cập khóa, quyền vận hành.

Không mặc định rằng xóa public JWK khỏi endpoint lập tức thu hồi mọi JWT đã ký; cần xử lý cache và trạng thái instance như một phần của plan.

## 14. Những nhầm lẫn cần tránh

**“`kid` đúng thì chữ ký đúng.”** Không. `kid` chỉ là gợi ý chọn khóa; token ghi `kid = A` nhưng ký bằng C phải bị từ chối.

**“Đổi signer sang B là có thể xóa A ngay.”** Với rotation bình thường, token A chưa hết hạn vẫn cần public key A. Cần grace period và kế hoạch rút khóa.

**“JWKS trả 503 thì cứ dùng nội dung payload để cấp quyền.”** Không. Chưa xác minh chữ ký thì `sub`/`scope`/`roles` chỉ là dữ liệu do caller cung cấp.

**“JWT có thể xác minh offline nên không cần kiểm tra JWKS outage.”** Không. Một instance mới, cache lạnh hoặc token dùng key mới có thể phụ thuộc JWKS.

**“Xóa A khỏi JWKS sẽ làm mọi API ngừng tin A ngay.”** Không chắc. Cache cũ có thể còn A; emergency revocation phải được thiết kế và kiểm thử riêng.

**“Đã kiểm tra JWT signature là đủ bảo vệ API.”** Chưa đủ. Cần issuer, audience, thời hạn, token profile, scope và quyền trên từng tài nguyên.

**“Test với `jwt()` của Spring MockMvc là đã test JWKS.”** Không. Helper kiểm thử authentication/authorization không tương đương với gửi Bearer JWT có chữ ký và đi qua `JwtDecoder` thực.

**“Một lần retry JWKS thành công chứng minh rotation an toàn.”** Chưa đủ. Cần test cache lạnh/nóng, token A+B còn hạn, nhiều pod và outage trùng rotation.

**“Cho phép thuật toán do token tự khai sẽ linh hoạt hơn.”** Không an toàn. Resource Server phải chỉ chấp nhận thuật toán được cấu hình tin cậy, tránh algorithm confusion.

**“Dùng cùng `kid` cho nhiều khóa khác nhau không sao.”** Dễ gây chọn khóa mơ hồ và khó vận hành. Cần quy trình định danh khóa nhất quán và kiểm chứng chữ ký bằng đúng key material.

## 15. Bài tập tình huống

**Tình huống A:** JWKS hiện có A+B, AS ký token mới bằng B; Resource Server chỉ cache A. Token B bị từ chối lần đầu nhưng thành công sau khi decoder refresh JWKS. Đây có phải lỗ hổng?

Không nhất thiết. Nó cho thấy **thời điểm refresh/key cache** ảnh hưởng khả dụng. Cần bảo đảm không có token chưa xác minh nào được chấp nhận và thiết kế pre-publish/caching phù hợp để tránh 401 không cần thiết.

**Tình huống B:** JWT header ghi `kid = A` nhưng được ký bằng private key C. JWKS công bố public key A. API nên làm gì?

Từ chối vì chữ ký không khớp. `kid` không thay thế chữ ký.

**Tình huống C:** JWKS down, pod A có cache A còn dùng được; pod B vừa khởi động cache trống. Cùng JWT A còn hạn hoạt động ở A nhưng thất bại ở B. Vì sao?

Chìa khóa là **trạng thái khóa ở từng instance**. A có thể xác minh cục bộ; B thiếu public key và không thể tải nó. Cần quan sát startup/cache/network, không bỏ qua xác minh ở B.

**Tình huống D:** Sau khi bị nghi lộ private key A, AS rút A khỏi JWKS. Một số pod vẫn chấp nhận token ký A vì cache. Có thể coi việc thu hồi đã hoàn tất?

Chưa. Cần cơ chế ngừng tin A ở mọi Resource Server theo thời hạn mục tiêu, kiểm tra lại trên các pod/region và đánh giá các token đã phát.

**Tình huống E:** JWT được ký bằng B hợp lệ nhưng `aud = payments-api`. Orders API phải xử lý gì?

Từ chối theo audience. Chữ ký chỉ chứng minh token phù hợp khóa ký tin cậy, không chứng minh token dành cho Orders API.

**Tình huống F:** Một test dùng `MockMvc.jwt()` với `scope = orders.read` và endpoint trả 200, sau đó kết luận JWKS rotation hoạt động. Kết luận có đúng?

Không. `MockMvc.jwt()` là cơ chế tiện ích để thử logic security ở lớp request; test đó không chứng minh decoder đã tải JWK hoặc xác minh chữ ký token thật. Cần integration test signed JWT và JWKS endpoint thực.

---

**Ghi nhớ:** Để kiểm thử vòng đời JWK trong Spring Security Resource Server, hãy tạo **ít nhất hai cặp khóa A/B**, phát JWT có chữ ký thật, dùng **JWKS mock có thể thay nội dung và giả lập 5xx/timeout**, rồi kiểm tra lần lượt **pre-publish → đổi signer → grace period → retire key**. Bổ sung các phép thử **unknown `kid`, same `kid` but wrong signature, sai thuật toán, sai issuer/audience, cache lạnh/nóng và outage**. Một hệ thống được xem là hoạt động an toàn khi token hợp lệ tiếp tục được chấp nhận trong những điều kiện đã thiết kế, còn mọi token không thể xác minh được đều **bị từ chối mà không bỏ qua JWT validation hay authorization**.
