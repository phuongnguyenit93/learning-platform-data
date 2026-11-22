# Thời gian chồng lấn khóa cũ, khóa mới và token chưa hết hạn

Khi **Authorization Server** thay khóa ký JWT, không thể đơn giản xóa khóa công khai cũ khỏi JWK Set ngay khi bắt đầu dùng khóa mới. Những **access token đã được ký bằng khóa cũ** có thể vẫn còn hiệu lực tới thời điểm `exp` và đang được các client sử dụng để gọi **Spring Security OAuth 2.0 Resource Server**. Nếu Resource Server không còn tìm thấy khóa xác minh cũ, các token này sẽ bị từ chối **mặc dù chưa hết hạn**.

Giải pháp thường dùng là **key rollover có giai đoạn chồng lấn**: Authorization Server công bố khóa mới trước khi sử dụng nó, giữ khóa cũ trong **JWKS** cùng với khóa mới trong thời gian các token cũ còn hiệu lực, và chỉ loại bỏ khóa cũ sau khi mọi token liên quan không còn được chấp nhận theo chính sách. Bài học này giải thích chính xác **chồng lấn bắt đầu từ khi nào, kết thúc khi nào, vì sao không thể chỉ nhìn TTL của JWKS**, và cách phối hợp hệ thống phát hành với Spring Security Resource Server để chuyển khóa không gián đoạn.

> Phạm vi chính là **JWT access token được ký bằng JWS** và được Resource Server xác minh bằng khóa công khai từ **JWK Set**. Những ví dụ issuer, endpoint, key ID, giờ và token đều là dữ liệu giả lập. Nếu hệ thống sử dụng opaque token với introspection thì cơ chế xác minh mỗi request khác, dù vòng đời khóa JWT của các hệ thống liên quan vẫn cần được quản lý.

## 1. Từ JWT đến JWK Set: những thành phần tham gia

Một JWT access token dạng compact JWS thường gồm ba phần:

~~~text
BASE64URL(JOSE_HEADER).BASE64URL(JWT_CLAIMS).BASE64URL(SIGNATURE)
~~~

Ví dụ JOSE header trước khi mã hóa:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "orders-signing-2026-11"
}
~~~

Payload minh họa:

~~~json
{
  "iss": "https://idp.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1794733200,
  "nbf": 1794733200,
  "exp": 1794735000
}
~~~

Các giá trị timestamp trong ví dụ chỉ dùng để giải thích quan hệ thời gian; đây **không phải** token thật hoặc bằng chứng token đang hợp lệ. `typ=at+jwt` minh họa một JWT access token theo profile phù hợp như RFC 9068; không phải Authorization Server nào cũng phát hành đúng giá trị này, nên Resource Server cần biết token profile chính thức.

| Thành phần | Vai trò trong vòng đời khóa | Ai quản lý |
|---|---|---|
| **Signing private key** | Khóa bí mật ký access token | Authorization Server; phải giữ bí mật |
| **Public verification key** | Khóa công khai để kiểm tra chữ ký | Authorization Server công bố; Resource Server nhận qua nguồn tin cậy |
| **JWK** | Định dạng JSON biểu diễn thông số một khóa, ví dụ RSA `n` và `e` | Hạ tầng quản lý khóa/issuer |
| **JWKS / JWK Set** | Tập nhiều JWK, cho phép công bố khóa cũ và mới đồng thời | Authorization Server |
| **`kid`** | Key identifier trong JOSE header giúp chọn khóa phù hợp | Được gắn lúc ký và khi công bố JWK |
| **`alg`** | Thuật toán ký được khai báo trong JOSE header | Issuer dùng, Resource Server phải có allowlist |
| **`iss`** | Issuer phát hành token | Resource Server đối chiếu trusted issuer |
| **`exp` / `nbf` / `iat`** | Hạn kết thúc, bắt đầu hiệu lực và thời điểm phát hành token | Chính sách cấp token và validator |
| **JWKS cache** | Bản sao tập public keys Resource Server giữ để tránh gọi mạng thường xuyên | Resource Server / decoder / hạ tầng |

**Khóa cũ bị loại khỏi JWKS** không đồng nghĩa mọi token ký bằng khóa đó đã hết hạn. Ngược lại, **khóa còn trong JWKS** cũng không đồng nghĩa token sẽ được chấp nhận: JWT còn phải qua kiểm tra chữ ký, issuer, audience, thời gian hiệu lực, token type và các điều kiện phân quyền.

### 1.1. JWKS công bố public key, không phải private key

Ví dụ hình dạng JWK RSA công khai:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-key-old",
      "use": "sig",
      "alg": "RS256",
      "n": "<BASE64URL_PUBLIC_MODULUS_OLD>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "signing-key-new",
      "use": "sig",
      "alg": "RS256",
      "n": "<BASE64URL_PUBLIC_MODULUS_NEW>",
      "e": "AQAB"
    }
  ]
}
~~~

Các giá trị `n` dạng placeholder không phải public key RSA thật. Chỉ những trường public key thích hợp mới được công bố; **không đưa thông số private key như `d`, `p`, `q`** vào endpoint JWKS. Một JWKS có thể chứa nhiều khóa để phục vụ giai đoạn rotation và các mục đích khác nhau; Resource Server phải chọn khóa đúng theo `kid`, `kty`, thuật toán và trust policy.

### 1.2. `kid` không phải chứng cứ tin cậy độc lập

JOSE header của token có thể khai báo:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-new"
}
~~~

Resource Server có thể dùng `kid` để tìm key trong **JWK Set đã được cấu hình là tin cậy**, nhưng không được coi `kid` là bằng chứng issuer, token type hoặc quyền truy cập. Kẻ tấn công có thể đặt `kid` bất kỳ trong JWT chưa được xác minh. **Tên `kid` trùng không đủ để xác thực JWT**; hệ thống vẫn phải kiểm tra chữ ký thực bằng đúng khóa, thuật toán được phép và các validator liên quan.

## 2. Vì sao phải có thời gian chồng lấn?

Xét một tình huống đơn giản:

1. Authorization Server đang ký JWT bằng private key **K_old**.
2. Resource Server tải JWKS có public key **K_old** và dùng để xác minh request.
3. Một access token được ký bằng K_old lúc 09:00, `exp` ở 09:30.
4. Lúc 09:10, Authorization Server bắt đầu ký token mới bằng **K_new**.
5. Nếu đồng thời xóa public key K_old khỏi JWKS, những Resource Server vừa refresh sẽ không còn khóa để kiểm tra token phát hành trước 09:10.

Kết quả là **token cũ chưa hết hạn nhưng bị trả 401**, gây lỗi ngắt quãng trên nhiều client tùy thời điểm Resource Server refresh JWKS. Một số instance còn giữ cache K_old có thể tạm chấp nhận token, trong khi instance khác từ chối; hiện tượng này càng khó chẩn đoán vì cùng token có lúc hoạt động, có lúc thất bại.

Vì vậy, vòng đời của **khóa dùng để ký** và vòng đời của **khóa công khai còn được dùng để xác minh** không giống nhau:

~~~text
Signing:
    K_old  ────────────┐
                      └───────────── K_new ───────────────>

Verification JWKS:
    K_old  ───────────────────────────┐
    K_new        ┌────────────────────────────────────────>
                 └──── CHỒNG LẤN ────┘

Tokens:
    Token ký K_old ───────── có thể chưa hết hạn ────────┐
                                                        └─ sau mới loại K_old
~~~

Một private key cũ có thể được **ngừng sử dụng để ký** ngay lúc chuyển sang K_new, nhưng **public key tương ứng phải được tiếp tục công bố** khi còn token ký bằng K_old có khả năng hợp lệ.

## 3. Bốn mốc thời gian cần thống nhất

Ký hiệu:

| Mốc | Ý nghĩa |
|---|---|
| **T_publish_new** | K_new xuất hiện trong JWKS để Resource Server có thể nhận biết |
| **T_start_new_signing** | Authorization Server bắt đầu ký token bằng K_new |
| **T_last_old_signing** | Thời điểm phát hành **cuối cùng** của token ký bằng K_old, tính trên **mọi node** phát hành |
| **T_remove_old** | K_old bị loại khỏi JWKS do issuer công bố |

Thứ tự an toàn thông thường:

~~~text
T_publish_new
      |
      |  Thời gian cho cache JWKS cập nhật khóa mới
      v
T_start_new_signing
      |
      |  K_old vẫn phải có trong JWKS;
      |  một số node có thể còn ký K_old nếu rollout lệch
      v
T_last_old_signing
      |
      |  Chờ toàn bộ token ký K_old hết hạn
      |  + dung sai đồng hồ + margin đã quyết định
      v
T_remove_old
~~~

Không nhất thiết `T_start_new_signing` trùng `T_last_old_signing`: trong cluster nhiều node, rollout có thể theo rolling deployment và một vài node vẫn dùng K_old sau khi node đầu tiên đã dùng K_new. Vì vậy **thời điểm dùng để tính ngày xóa khóa cũ phải là lần ký cuối cùng thực tế**, không phải lúc bắt đầu phát hành khóa mới.

### 3.1. Hai giai đoạn chồng lấn khác nhau

Thường có hai khoảng cần theo dõi riêng:

**Khoảng A — Prepublication của K_new**: tính từ lúc JWKS công bố K_new đến lúc Authorization Server bắt đầu dùng K_new để ký. Mục tiêu là để Resource Server/proxy/cache biết khóa mới trước khi token có `kid` mới xuất hiện.

**Khoảng B — Giữ K_old sau khi ngừng ký**: tính từ lúc không còn node nào ký K_old đến lúc K_old có thể được loại khỏi JWKS. Mục tiêu là để **mọi token còn hiệu lực được ký bằng K_old** tiếp tục xác minh thành công.

Khoảng A phụ thuộc nhiều vào **JWKS cache/propagation**. Khoảng B phụ thuộc chủ yếu vào **tuổi thọ token lớn nhất và dung sai thời gian**. Hai khoảng **không thể thay thế cho nhau**.

## 4. Tính thời điểm an toàn để xóa khóa cũ

Gọi:

- `T_last_old_signing`: thời điểm issuer cuối cùng phát hành token ký bằng K_old.
- `L_max_old`: tuổi thọ hiệu lực tối đa của token ký bằng K_old, theo hợp đồng token thực tế.
- `S_validation`: dung sai đồng hồ tối đa Resource Server cho phép khi xác minh `exp`.
- `M`: biên an toàn thêm cho độ trễ ghi nhận thời điểm phát hành, rolling rollout, sự khác biệt đồng hồ hoặc lỗi quan sát đã xác định.

Một **quy tắc lên lịch thận trọng**:

~~~text
T_remove_old >= T_last_old_signing + L_max_old + S_validation + M
~~~

Điều này chỉ đúng khi:

1. Authorization Server **thực sự không còn ký K_old** sau `T_last_old_signing`.
2. Mọi token dùng K_old tuân thủ giới hạn tuổi thọ `L_max_old` và có `exp` hợp lệ.
3. Các Resource Server áp giới hạn clock skew trong `S_validation`.
4. Hợp đồng không có loại token đặc biệt, chẳng hạn token cực dài hạn hoặc issued-token cũ không có `exp`, được phép dùng cùng K_old.

Nếu **không thể bảo đảm tuổi thọ tối đa**, không thể suy ra lịch xóa khóa chỉ từ một con số TTL kỳ vọng. Phải tra cứu chính sách cấp phát và token thực tế, hoặc có chiến lược vô hiệu hóa/thu hồi có kiểm soát.

### 4.1. Ví dụ tính theo phút

Giả định:

~~~text
Last token signed by K_old: 09:10
Maximum token lifetime:     30 minutes
Verifier clock skew:         2 minutes
Additional safety margin:    8 minutes
~~~

Khi đó:

~~~text
Token K_old cuối có thể có exp: 09:40
Verifier có thể chấp nhận tới: 09:42
Mốc xóa theo kế hoạch:        từ 09:50 trở đi
                              (09:10 + 30 + 2 + 8)
~~~

Lựa chọn **09:50** là ví dụ chính sách vận hành, không phải giá trị bắt buộc của Spring Security hay một RFC. Nếu AS vẫn ký K_old lúc 09:25 vì một node rollout chậm, **mốc 09:10 không còn đúng**; phải tính lại với lần ký cuối thực tế.

### 4.2. Token chưa hết hạn quan trọng hơn thời điểm đổi khóa

Khi issuer ký JWT lúc `T_issue`, nó gắn `exp`. Resource Server không thể kết luận token đã hết hiệu lực chỉ vì JWT dùng K_old. Chữ ký K_old có thể vẫn hoàn toàn hợp lệ trong thời gian public key K_old còn được trust.

Ngược lại, dù K_old **vẫn nằm trong JWKS**, một JWT có `exp` quá khứ vẫn phải bị từ chối. Chỉ khi đồng thời thỏa:

~~~text
Chữ ký hợp lệ với public key tin cậy
    AND issuer/audience/token profile hợp lệ
    AND thời gian hiệu lực hợp lệ
    AND các điều kiện xác thực bắt buộc khác
~~~

thì token mới được coi là đã xác thực. Chồng lấn khóa là **điều kiện duy trì khả năng xác minh**, không phải cách kéo dài tuổi thọ token.

## 5. Timeline ví dụ hoàn chỉnh: đổi từ K_old sang K_new

Giả định môi trường:

- Issuer: `https://idp.example.test/realms/company`.
- Resource Server: Orders API, expected audience `orders-api`.
- Thuật toán ký: `RS256`, key ID riêng `key-old` và `key-new`.
- Access token TTL tối đa: 30 phút.
- Clock skew được chấp nhận: tối đa 2 phút.
- Cache JWKS ở các Resource Server/proxy có thể stale tối đa 5 phút theo thiết kế đã biết.
- Biên vận hành thêm cho xóa K_old: 8 phút.

| Thời điểm | Authorization Server làm gì? | JWKS công bố | Resource Server cần làm gì? |
|---|---|---|---|
| 08:55 | Chỉ ký bằng K_old | `[K_old]` | Xác minh token cũ bình thường |
| **09:00** | Sinh K_new an toàn, **công bố K_new nhưng chưa ký** | `[K_old, K_new]` | Cache có thời gian nhận JWK mới |
| **09:10** | Bắt đầu ký K_new; xác nhận các node không còn ký K_old | `[K_old, K_new]` | Token mới có `kid=key-new`; token cũ vẫn được xác minh |
| 09:20 | K_new là khóa ký chính | `[K_old, K_new]` | Chấp nhận cả JWT ký K_old (nếu chưa hết hạn) và K_new |
| **09:40** | Token K_old cuối cùng đạt `exp` tối đa theo giả định | `[K_old, K_new]` | Dung sai skew có thể còn cho phép token cũ |
| 09:42 | Hết cửa sổ clock skew 2 phút giả định | `[K_old, K_new]` | Không nên còn token K_old hợp lệ theo hợp đồng |
| **09:50** | Sau margin, có thể loại K_old theo quy trình bình thường | `[K_new]` | Chỉ còn dùng K_new để xác minh các token hợp lệ mới |

Sơ đồ:

~~~mermaid
gantt
    title Ví dụ rollover không gián đoạn (giờ minh họa)
    dateFormat HH:mm
    axisFormat %H:%M
    section Khóa ký
    K_old có thể ký           :a1, 08:55, 15m
    K_new bắt đầu ký          :milestone, m1, 09:10, 0m
    K_new ký token            :a2, 09:10, 40m
    section JWKS công bố
    Chỉ K_old                 :b1, 08:55, 5m
    K_old và K_new cùng có    :b2, 09:00, 50m
    Chỉ K_new                 :b3, 09:50, 10m
    section Token K_old
    Token cuối còn khả dụng   :c1, 09:10, 32m
    Margin trước khi loại key :c2, 09:42, 8m
~~~

Đây là một timeline **giả định có cache staleness tối đa 5 phút**. Công bố K_new trước 10 phút tạo khoảng dự phòng, nhưng trong hệ thống thật phải xét thời gian refresh JWKS, cache của gateway/CDN, mạng phân vùng, cơ chế xử lý unknown `kid` và trạng thái toàn bộ node. Đừng áp dụng lịch cố định nếu không biết những giới hạn đó.

### 5.1. Vì sao không chỉ “chờ 5 phút vì JWKS cache TTL là 5 phút”?

**TTL JWKS cache** trả lời “bao lâu Resource Server có thể tiếp tục giữ bản key set đã đọc?”. **JWT TTL** trả lời “token được cấp còn giá trị đến khi nào?”. Hai đại lượng không cùng ý nghĩa:

~~~text
JWKS cache TTL = 5 phút
JWT TTL        = 30 phút
~~~

Sau 5 phút, Resource Server có thể cập nhật khóa mới. Nhưng JWT được ký bằng K_old **lúc cuối giai đoạn phát hành** vẫn có thể hợp lệ thêm 30 phút, cộng clock skew. Xóa K_old sau 5 phút làm các token chưa hết hạn không thể được xác minh.

Ngược lại, nếu chỉ giữ K_old 30 phút mà K_new không được prepublish đủ lâu hoặc cache không refresh khi gặp `kid` mới, token K_new đầu tiên vẫn có thể bị từ chối. **Phải giải quyết đồng thời cả hai phía của quá trình rollover.**

## 6. JWKS cache, propagation và `kid` mới

Resource Server thường không tải JWKS từ mạng cho **mỗi JWT**. Decoder có thể giữ khóa trong bộ nhớ hoặc sử dụng cache do thư viện/JWK source quản lý. Nếu ứng dụng chạy nhiều instance, mỗi instance còn có **trạng thái cache riêng**.

~~~mermaid
flowchart LR
    AS["Authorization Server<br/>JWKS: K_old + K_new"] --> CDN["CDN / reverse proxy cache<br/>(nếu có)"]
    CDN --> RS1["Resource Server instance A<br/>JWKS cache"]
    CDN --> RS2["Resource Server instance B<br/>JWKS cache"]
    CDN --> RS3["Resource Server instance C<br/>JWKS cache"]
    C["Client gửi JWT<br/>kid=K_new"] --> LB["Load balancer"]
    LB --> RS1
    LB --> RS2
    LB --> RS3
~~~

Nếu instance A vừa refresh JWKS còn instance B chưa refresh, một token mới có `kid=K_new` có thể được A chấp nhận và bị B từ chối. Nếu đã xóa K_old nhưng instance A vẫn cache bộ khóa cũ, có thể xuất hiện trạng thái ngược lại: A còn xác minh được token cũ trong khi instance B đã refresh và không tìm thấy K_old.

### 6.1. Những điểm làm độ trễ lan truyền tăng lên

| Tầng | Nguồn trễ | Hệ quả khi rollover |
|---|---|---|
| Authorization Server cluster | Các node công bố JWKS hoặc đổi khóa ký không đồng thời | Một node ký K_new trong khi node khác vẫn chỉ công bố K_old |
| CDN/reverse proxy | Cache-Control, TTL, stale-while-revalidate, purge không đồng nhất | JWKS mới chưa đến Resource Server |
| Resource Server JVM | In-memory cache của decoder/JWK source | Từng instance thấy bộ keys khác nhau |
| Networking | DNS/TLS/timeout/proxy/firewall | Không lấy được JWKS khi gặp key mới |
| Clock | Thời gian các node không đồng bộ | Kéo dài hoặc rút ngắn cửa sổ chấp nhận `exp`/`nbf` |
| Deployment | Rolling rollout, nhiều phiên bản cấu hình | K_old vẫn có thể được sử dụng sau thời điểm lên kế hoạch |

Vì vậy, khi thiết kế **T_publish_new → T_start_new_signing**, hãy dựa trên giới hạn thực tế của toàn bộ pipeline, không chỉ HTTP `max-age` trả về từ một node issuer.

### 6.2. Cách xử lý token có `kid` chưa biết

Khi Resource Server nhận một JWT ký bằng K_new mà cache chỉ có K_old, decoder/JWK source có thể **thử refresh JWKS** nếu triển khai hỗ trợ cơ chế đó. Tuy nhiên:

- Không phải mọi version hoặc custom decoder đều refresh cùng một cách.
- Một proxy/CDN có thể vẫn trả **bản JWKS cũ** ngay cả khi decoder gửi GET mới.
- Refresh có thể lỗi DNS/TLS/timeout.
- Nếu issuer công bố K_new **sau** khi ký token bằng K_new, mọi lần refresh trước khi công bố đều vô ích.
- Nếu K_new dùng thuật toán không nằm trong allowlist của decoder, có key mới cũng không giúp xác thực thành công.

**Không dựa hoàn toàn vào “unknown `kid` sẽ tự refresh” mà bỏ qua prepublication.** Đường triển khai an toàn là công bố K_new đủ sớm, quan sát Resource Server đã nhận key, sau đó mới kích hoạt việc ký bằng K_new.

### 6.3. Chú ý response cache của JWKS endpoint

Một JWKS endpoint có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=300
ETag: "jwks-version-17"
~~~

Ở đây `max-age=300` tương đương 5 phút theo HTTP caching, nhưng **không có nghĩa mọi Java decoder tự động dùng đúng TTL đó**, và cũng không bảo đảm các proxy không có chính sách cache bổ sung. `ETag` hỗ trợ conditional requests nếu client/proxy dùng HTTP caching phù hợp.

Đặc biệt, **`Cache-Control` cho phép cache public keys, không cho phép cache private signing keys**. Không đặt client secret hoặc thông tin khóa riêng vào JWKS response chỉ vì endpoint công khai.

### 6.4. Đồng bộ cache cho nhiều Resource Server

Với một hệ thống có nhiều service, hãy xác định:

1. Mỗi service lấy JWKS của issuer nào?
2. Có proxy/CDN chung hay mỗi service gọi issuer trực tiếp?
3. Cache hiệu lực bao lâu; có refresh theo `kid` mới không?
4. Khi rollback AS có thể dùng lại K_old không?
5. Key mới được công bố trước bao lâu so với lúc ký thực sự?
6. Làm sao quan sát từng service/instance đã cập nhật JWKS mà không log token?
7. Khi JWKS endpoint lỗi, service có thể xác minh những JWT đã có khóa hợp lệ trong cache không, và khi nào sẽ fail closed?

Một cách giảm rủi ro khi lên lịch rollout là dùng môi trường staging tích hợp giống production về network/cache, phát hành JWT thử với K_new và xác nhận các Resource Server được ủy quyền xác minh thành công **trước khi đưa K_new thành khóa ký chính**.

## 7. Cấu hình Spring Security Resource Server để cùng sống với rollover

Ở Spring MVC/Servlet, Spring Security thường dùng `NimbusJwtDecoder` để xác minh JWT dựa trên JWK Set. Nếu cấu hình theo issuer, ứng dụng có thể lấy khóa qua metadata/discovery của issuer tin cậy. Với những hệ thống muốn biết trước đường dẫn JWK Set, có thể khai báo đồng thời issuer và JWKS URI.

### 7.1. Phụ thuộc cần thiết

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 7.2. Cấu hình issuer và JWK Set URI

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/company
          jwk-set-uri: https://idp.example.test/realms/company/protocol/openid-connect/certs
~~~

Giải thích:

- `issuer-uri` xác định **nhà phát hành được tin cậy** và cho phép Spring Security áp chính sách issuer phù hợp.
- `jwk-set-uri` cho biết đường dẫn JWK Set cố định đã được đội Identity công bố. Tùy phiên bản Boot/Security, cấu hình cả hai giúp tránh phụ thuộc discovery ở giai đoạn khởi động nhưng vẫn giữ issuer validation.
- JWK Set có thể chứa **K_old và K_new cùng lúc**. Decoder chọn khóa phù hợp từ key set theo JOSE header và chính sách xác minh; ứng dụng không nên ép chỉ một `kid` nếu đang trong giai đoạn rollover.

**Rất quan trọng:** `jwk-set-uri` không đồng nghĩa `issuer-uri`. Khi ứng dụng tự tạo `JwtDecoder` bằng JWKS URI, phải giữ issuer validator rõ ràng. Ngoài issuer, Resource Server nên kiểm tra audience theo hợp đồng API.

### 7.3. Cấu hình bảo vệ endpoint

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Với cấu hình này, JWT được xác thực trước khi scope `orders.read` được ánh xạ thành `SCOPE_orders.read`. Một token ký bằng K_old **vẫn có thể được chấp nhận** nếu public key K_old còn trong nguồn tin cậy, chữ ký đúng, thời hạn chưa kết thúc, issuer/audience hợp lệ và scope đủ. Một token ký bằng K_new cũng vậy.

Spring Security **không tự phát hành, luân chuyển hoặc xóa khóa ký**. Việc xuất bản JWK Set và quyết định khóa private key nào ký JWT thuộc Authorization Server. Resource Server chịu trách nhiệm có nguồn key đáng tin cậy và xác minh request theo chính sách.

### 7.4. Tùy biến `JwtDecoder` nhưng vẫn cho phép nhiều JWK

Giả sử Orders API cần thêm validation audience và giới hạn thuật toán ký:

~~~yaml
app:
  security:
    jwt:
      issuer: https://idp.example.test/realms/company
      jwk-set-uri: https://idp.example.test/realms/company/protocol/openid-connect/certs
      audience: orders-api
~~~

`app.security.jwt.*` là namespace do ứng dụng mẫu định nghĩa, **không** phải thuộc tính auto-configuration sẵn có của Spring Boot.

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
class OrdersJwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwk-set-uri}") String jwks,
            @Value("${app.security.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwks)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> expectedAudience = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Access token not intended for Orders API",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                expectedAudience
            )
        );
        return decoder;
    }
}
~~~

Đây là **một phương án thay thế decoder do Boot tự tạo**. Nếu đăng ký bean trên, bean `JwtDecoder` của ứng dụng thường được sử dụng, và các property default không được tự động “ghép vào” mọi validator của custom bean. Vì thế ví dụ chủ động dùng `JwtValidators.createDefaultWithIssuer(...)` để giữ kiểm tra issuer và thời gian, rồi thêm audience validator.

Trong rollover, JWKS chứa cả K_old và K_new sẽ cho phép decoder tìm các public key tương ứng; **không cần sửa code Java theo từng `kid`**. Nếu AS đổi sang thuật toán JWS mới, phải thỏa thuận và cấu hình các thuật toán được phép; việc chỉ xuất bản thêm JWK không tự mở rộng allowlist thuật toán.

**Không viết custom decoder “chọn key” bằng cách lấy JWK URL từ JWT header `jku` chưa xác minh.** JWKS URI cần xuất phát từ cấu hình tin cậy/issuer metadata, không từ input tùy ý của client.

### 7.5. Thời gian cache của Nimbus và Spring Security

Trong các phiên bản Spring Security/Nimbus khác nhau, có thể có cache JWK mặc định, tùy chọn tùy biến cache, HTTP client và hành vi refresh khi gặp `kid` lạ. Không nên dựa trên một hằng số “JWKS luôn cache 5 phút” cho mọi triển khai.

Nếu cần giới hạn cụ thể, phải xác định:

- Phiên bản `spring-security-oauth2-jose` và thư viện Nimbus được dùng.
- Decoder hiện đang do Boot auto-config hay do ứng dụng tạo.
- HTTP cache/proxy và custom `Cache` nào được dùng.
- Hành vi khi nhận token có `kid` chưa xuất hiện trong cache.
- Chính sách retry/timeout/tải lại từ JWKS endpoint.
- Cách theo dõi key refresh thành công trên tất cả instance.

Giới hạn cache là **tham số vận hành** để lựa chọn `T_publish_new`, không phải lý do bỏ kiểm tra token expiry hoặc issuer.

## 8. Spring WebFlux: nguyên tắc vòng đời khóa không đổi

Trên Spring WebFlux, Resource Server dùng `ReactiveJwtDecoder`, thường là `NimbusReactiveJwtDecoder`, và security chain dùng `SecurityWebFilterChain`.

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ReactiveOrdersSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Property `issuer-uri` và `jwk-set-uri` vẫn thuộc nhóm cấu hình JWT Resource Server. Nếu tự tạo decoder reactive, phải dùng `ReactiveJwtDecoder`/`NimbusReactiveJwtDecoder` với issuer/time/audience validators phù hợp; không gắn bean `JwtDecoder` của Servlet vào stack WebFlux rồi kỳ vọng nó xử lý reactive request.

Rollover vẫn phải đảm bảo:

1. K_new công bố đủ sớm trước khi ký.
2. K_old tiếp tục công bố tới khi mọi JWT K_old không còn khả năng hợp lệ.
3. Source/alg/issuer/audience vẫn được kiểm tra.
4. Cache/HTTP client reactive được cấu hình và quan sát phù hợp.

Sự khác biệt Servlet và WebFlux chủ yếu là **API lập trình và mô hình xử lý HTTP**, không phải sự khác biệt về quy tắc an toàn của vòng đời khóa JWT.

## 9. Key rotation bình thường, key revocation và compromise là ba tình huống khác nhau

Một kế hoạch chồng lấn có ý nghĩa khi K_old **không bị lộ** và tổ chức muốn thay khóa theo chu kỳ. Nếu private key cũ đã bị xâm phạm, yêu cầu bảo mật có thể **ưu tiên thu hồi ngay** dù làm token hợp lệ bị gián đoạn.

| Tình huống | Mục tiêu | K_old trong JWKS |
|---|---|---|
| **Routine rotation** theo lịch | Không gián đoạn xác thực các token còn hiệu lực | Giữ tới khi token K_old hết hiệu lực + skew/margin |
| **Emergency rotation** vì nghi ngờ lộ private key | Chặn khả năng attacker giả mạo JWT | Có thể phải loại/trust-revoke ngay theo incident response |
| **Khóa cũ hết hạn sử dụng theo policy** nhưng không lộ | Ngừng phát hành token mới, bảo toàn token cũ | Tách quyền ký mới khỏi quyền xác minh token cũ |
| **Thu hồi một access token cụ thể** | Chặn token bị lộ/bị hủy quyền | Không nhất thiết xóa cả K_old; cần token revocation policy |
| **Đổi issuer/tenant trust boundary** | Di chuyển nguồn phát hành đáng tin | Phải có migration policy riêng; không chỉ đổi `kid` |

### 9.1. Vì sao không thể cứ giữ K_old nếu private key bị lộ?

Khi private key K_old bị lộ, attacker có thể tạo JWT mới ký bằng K_old, tự khai báo `exp`, `scope` và các claim khác. Nếu Resource Server tiếp tục tin public key K_old, chỉ “đợi token cũ hết hạn” **không đủ ngăn token giả** nếu không có cơ chế khác như denylist, giới hạn token age, token inventory hoặc khóa ký đã bị vô hiệu hóa ở tầng verifier.

Trong tình huống này, đội ứng cứu có thể quyết định:

- Loại K_old khỏi JWKS và buộc Resource Server refresh/invalidate cache.
- Hủy tin cậy K_old ở decoder/configuration nếu hệ thống có cơ chế.
- Thu hồi session/token, yêu cầu client nhận token mới qua quy trình hợp lệ.
- Giảm thời gian chấp nhận token cũ hoặc tạm chặn các endpoint nhạy cảm.
- Kiểm tra audit trail để xác định phạm vi ảnh hưởng.

**Điều này có thể làm những token K_old chưa hết hạn bị 401**. Đây là đánh đổi có chủ đích giữa availability và security trong incident response. Không áp dụng quy tắc rollover bình thường một cách máy móc khi đã có bằng chứng compromise.

### 9.2. Vì sao xóa public key khỏi JWKS chưa chắc có hiệu lực ngay?

Resource Server có thể đang giữ bản JWKS chứa K_old trong cache. Nếu chỉ xóa K_old ở endpoint của issuer nhưng không làm mới trust/cache ở các verifier, một số instance có thể tiếp tục chấp nhận token ký bằng K_old.

Trong incident:

~~~text
AS xóa K_old khỏi JWKS
    |
    +--> RS instance A refresh ngay, không còn tin K_old
    |
    +--> RS instance B vẫn cache K_old, tiếp tục xác minh token cũ
    |
    +--> Gateway/CDN có bản stale trả về K_old
~~~

Do đó quy trình thu hồi khẩn cấp phải bao gồm **kế hoạch vô hiệu hóa cache/trust** ở Resource Server và các lớp proxy, hoặc các biện pháp bù trừ theo kiến trúc. Việc “JWKS đã đổi” chỉ phản ánh nguồn công bố, chưa chứng minh mọi verifier đã đổi trạng thái.

### 9.3. Phân biệt khóa ký với access token bị thu hồi

JWT self-contained thường được Resource Server xác minh **cục bộ**. Khi Authorization Server thu hồi một access token, Resource Server không tự biết điều đó chỉ từ chữ ký và `exp` nếu không có cơ chế truyền thông tin thu hồi/denylist/introspection đặc biệt.

Xóa K_old khỏi JWKS sẽ ảnh hưởng **tất cả token ký bằng K_old**, chứ không chỉ một token bị đánh cắp. Nếu mục tiêu là thu hồi một token riêng lẻ, cần chiến lược token revocation phù hợp, ví dụ access token TTL ngắn, denylist theo `jti` trong một số kiến trúc, hoặc validation thời gian thực theo chính sách đã định.

## 10. Một quy trình triển khai key rollover có kiểm soát

Rollover bình thường cần sự phối hợp của ít nhất ba bên: **đội Authorization Server**, **đội Resource Server** và **đội vận hành hạ tầng/cache**. Trong doanh nghiệp có nhiều API, một issuer có thể phục vụ hàng chục Resource Server, nên việc chỉ thông báo “đã tạo key mới” là chưa đủ.

### Giai đoạn A — Chuẩn bị trước khi công bố khóa mới

Đội Authorization Server xác định:

1. Issuer và JWKS URI chính thức của môi trường.
2. Danh sách khóa đang được sử dụng để ký, `kid` và thuật toán của từng khóa.
3. TTL access token **tối đa thực tế**; có ngoại lệ grant, client, tenant hoặc token profile nào không?
4. JWT có bắt buộc `exp` không, độ lệch đồng hồ được phép là bao nhiêu?
5. Tất cả node phát hành có dùng cùng cấu hình signing key không?
6. Đội nào có quyền kích hoạt K_new, dừng K_old và thu hồi khẩn cấp?

Đội Resource Server cần xác nhận:

1. Decoder lấy public keys từ JWKS URI nào, có kiểm tra issuer/audience không?
2. Cache JWKS nằm trong JVM hay còn có gateway/CDN/proxy?
3. Runtime có refresh key khi nhận `kid` mới không?
4. Key rotation có liên quan tới thay đổi `alg`, token profile, audience hay issuer không?
5. Có hệ thống nào pin public key K_old thay vì theo JWKS động?
6. Có telemetry phân loại lỗi validation/JWKS mà không tiết lộ token không?

Nếu một service dùng public key cố định và không có kế hoạch cập nhật, chỉ công bố K_new trên JWKS **không đảm bảo** service đó chấp nhận JWT ký K_new. Phải cập nhật trust source ở mọi Resource Server liên quan.

### Giai đoạn B — Sinh khóa K_new và công bố trước

Tạo key pair bằng hệ thống quản lý khóa phù hợp (KMS/HSM hoặc giải pháp được phê duyệt), bảo vệ private key, gắn một `kid` mới **không dùng lại cho khóa khác**. Công bố **public JWK K_new** cùng K_old:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-old",
      "alg": "RS256",
      "use": "sig",
      "n": "<OLD_PUBLIC_MODULUS>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "key-new",
      "alg": "RS256",
      "use": "sig",
      "n": "<NEW_PUBLIC_MODULUS>",
      "e": "AQAB"
    }
  ]
}
~~~

Trong giai đoạn này, Authorization Server **vẫn ký token bằng K_old**. Mục tiêu là cho các verifier có cơ hội tải K_new, đồng thời không có thay đổi nào đối với token mà client nhận.

### Giai đoạn C — Kích hoạt K_new để ký

Sau khi khoảng prepublication đủ an toàn:

- Chuyển signing configuration sang K_new, nhưng **giữ K_old trong JWKS**.
- Xác nhận mọi Authorization Server node đã ngừng ký K_old.
- Ghi nhận **T_last_old_signing** từ nguồn audit/metric an toàn, không đoán bằng thời điểm rollout bắt đầu.
- Theo dõi lỗi `kid` chưa biết, chữ ký không hợp lệ, issuer/audience và 401 ở các Resource Server.
- Nếu có rollback ngắn hạn quay về K_old, phải ghi nhận lại thời điểm ký cuối mới; đồng thời giữ cả hai public keys trong JWKS.

Khi K_new trở thành khóa ký, không được làm token ký bằng K_old trước đó mất hiệu lực chỉ vì client chưa refresh token. Client vẫn được phép dùng access token K_old cho tới khi nó thực sự hết hạn hoặc bị thu hồi theo chính sách.

### Giai đoạn D — Chờ token cũ hết hạn

Tiếp tục công bố **K_old và K_new**. Tính thời điểm retirement từ:

~~~text
Last actual signing with K_old
+ longest legitimate lifetime of K_old JWT
+ maximum accepted clock skew
+ documented safety margin
~~~

Không chỉ dựa vào default token TTL nếu hệ thống có:

- Token service-to-service dài hạn hơn user token.
- Token scope đặc biệt với tuổi thọ khác.
- Authorization Server cluster chưa đồng bộ.
- Một issuer ký cả access token và loại JWT khác bằng K_old mà Resource Server vẫn dự kiến xác minh.
- Các token được gia hạn theo cơ chế không tạo chữ ký mới hoặc chính sách chấp nhận tuổi token khác.

**Refresh token thường không phải JWT access token và không được Resource Server xác minh bằng cùng pipeline.** Nếu issuer dùng cùng key pair để ký những JWT khác, lịch retirement phải xét **mọi loại token còn được phép xác minh bằng key đó**, không chỉ Orders API access token.

### Giai đoạn E — Loại K_old và theo dõi

Sau khi điều kiện an toàn về thời gian và chính sách được đáp ứng:

1. Loại public JWK K_old khỏi JWKS.
2. Đảm bảo signing service không còn sử dụng private K_old.
3. Theo dõi JWKS refresh, số lỗi `kid=key-old` và request bị từ chối sau cutover.
4. Thực hiện quy trình quản lý/vô hiệu hóa private key cũ theo policy của tổ chức; không nhất thiết xóa dữ liệu audit/backup đã được quy định giữ lại.
5. Cập nhật hồ sơ vòng đời khóa, thời điểm kích hoạt, ngừng ký, retirement và người phê duyệt.

Lưu ý **không cần coi mọi 401 với `kid=key-old` sau retirement là lỗi**: nếu token đó đã hết hạn, từ chối là đúng. Điều đáng quan tâm là token hợp lệ theo hợp đồng nhưng bị từ chối do việc retire quá sớm hoặc do key source/cache không đúng kỳ vọng.

## 11. Rollback: điều gì xảy ra nếu phải quay về K_old?

Có hai loại rollback cần phân biệt:

**Rollback signing**: Authorization Server chuyển tạm về ký bằng K_old do K_new gặp sự cố. Đây là phương án chỉ phù hợp khi **private K_old vẫn an toàn, chưa bị vô hiệu hóa**, và K_old còn nằm trong JWKS. Sau rollback, thời điểm `T_last_old_signing` phải được cập nhật theo token cuối cùng ký K_old.

**Rollback JWKS publication**: JWKS vô tình bỏ K_old/K_new hoặc xuất bản lỗi rồi phải phục hồi nội dung. Nếu khôi phục JWKS cũ chỉ chứa K_old trong khi Authorization Server vẫn ký bằng K_new, các token K_new có thể lập tức thất bại ở instance refresh. Khi phục hồi phải xét **mọi signing key hiện đang được dùng và token còn hiệu lực**.

| Tình huống | Rủi ro | Hướng xử lý theo nguyên tắc |
|---|---|---|
| K_new đã phát hành, JWKS bị rollback về chỉ K_old | JWT mới không xác minh được | Khôi phục JWKS chứa cả K_old và K_new |
| Rollback signer sang K_old sau khi đã tính retirement | Token K_old mới có `exp` muộn hơn | Tính lại T_last_old_signing và T_remove_old |
| K_old đã bị lộ và bị thu hồi | Quay về ký K_old tái mở rủi ro | Không rollback về key compromise; triển khai key an toàn khác |
| Resource Server cache JWKS lỗi | Kết quả xác thực khác nhau giữa instance | Khôi phục JWKS/trust source, xử lý refresh cache có kiểm soát |
| Thay `alg` đồng thời với key rotation | Decoder không hỗ trợ thuật toán mới | Cập nhật verifier allowlist trước khi chuyển signer, theo chính sách |

Trong kiến trúc được kiểm soát tốt, **key rollover là thay đổi có version và kế hoạch rollback**. Không dùng lại `kid` cũ cho material khóa mới để “đỡ sửa client”; điều đó tạo sự mơ hồ trong key selection/cache và khó điều tra sự cố.

## 12. Nếu đổi luôn thuật toán ký hoặc loại khóa

Chuyển K_old → K_new **cùng thuật toán** thường đơn giản hơn việc đồng thời đổi RSA sang EC hoặc thay `RS256` bằng `ES256`. Khi đổi thuật toán:

~~~text
Trước:
  K_old = RSA / RS256

Sau:
  K_new = EC / ES256
~~~

Cần bảo đảm Resource Server:

- Tin cậy JWK Set chứa cả khóa RSA cũ và EC mới trong giai đoạn chồng lấn.
- Cho phép đúng các JWS algorithms cần thiết; không mở rộng sang thuật toán bất kỳ.
- Có phiên bản JOSE library/JDK hỗ trợ thuật toán mới.
- Vẫn kiểm tra `iss`, `aud`, `exp`, `nbf` và token type.
- Không dùng một implementation tùy chỉnh chỉ hỗ trợ RSA để xác minh token EC.

Một rollout an toàn thường gồm:

~~~text
1. Chuẩn bị Resource Server chấp nhận đúng RS256 và ES256 đã phê duyệt.
2. Xuất bản public JWK EC mới cùng public JWK RSA cũ.
3. Chờ propagation/cache.
4. Chuyển Authorization Server ký ES256.
5. Đợi token RS256 còn hợp lệ hết hạn và tính skew/margin.
6. Loại public JWK RSA cũ; sau đó mới gỡ khả năng RS256 nếu policy cho phép.
~~~

Đừng chỉ cập nhật signer để ký ES256 rồi mới phát hiện Spring Security đang cấu hình:

~~~java
NimbusJwtDecoder.withJwkSetUri(jwks)
    .jwsAlgorithm(SignatureAlgorithm.RS256)
    .build();
~~~

Decoder này được cấu hình để tin thuật toán RS256 theo ví dụ, nên có thể từ chối token ký bằng ES256 dù JWKS có khóa EC mới. Phần allowlist thuật toán là một phần của kế hoạch rollout riêng, không tự điều chỉnh chỉ vì thấy K_new.

**Việc thay `alg` cũng không tự làm `iss`, `aud` hoặc scope đổi.** Những thay đổi khác trong hợp đồng token cần migration riêng để tránh ghép nhiều nguyên nhân lỗi vào một đợt phát hành khóa.

## 13. Nhiều issuer: chồng lấn phải tính theo từng nguồn tin cậy

Giả sử Orders API chấp nhận token từ:

~~~text
Issuer A: https://idp.example.test/realms/company
Issuer B: https://partners.example.test/oauth2/default
~~~

Mỗi issuer có JWKS, `kid`, lịch rotation, token TTL và policy riêng. Không nên trộn các khóa từ nhiều issuer thành một tập chung rồi bỏ kiểm tra `iss`. Một `kid` của Issuer A có thể trùng tên với `kid` của Issuer B, nhưng đó không phải cùng danh tính khóa.

~~~mermaid
flowchart TD
    A["Bearer JWT"] --> B["Đọc iss như gợi ý định tuyến chưa tin"]
    B --> C{"Issuer thuộc allowlist?"}
    C -->|Không| D["Từ chối"]
    C -->|Có| E["Chọn decoder và JWKS của issuer đó"]
    E --> F["Chọn kid trong JWKS tương ứng"]
    F --> G["Xác minh JWS và validators iss/aud/time"]
    G --> H["Tạo Authentication"]
~~~

Spring Security Servlet có các cách giải quyết theo issuer như `JwtIssuerAuthenticationManagerResolver`; hệ thống thực cần cấu hình registry issuer tin cậy, mapping audience và thuật toán của từng bên. **Claim `iss` chưa được xác minh có thể dùng làm gợi ý chọn resolver, nhưng không được dùng như bằng chứng tin cậy trước khi signature validation thành công.**

Mốc `T_last_old_signing` của Issuer A không dùng để tính retirement cho Issuer B. Mỗi issuer có thể đang ở một giai đoạn rollover khác nhau.

## 14. Quan hệ giữa JWKS rollover và OIDC

Trong hệ thống OpenID Connect, OpenID Provider có thể công bố `jwks_uri` trong discovery metadata và dùng các signing keys đó cho **ID token**, access token JWT hoặc các JWT khác theo cấu hình issuer. Tuy nhiên:

- **ID token hướng tới OIDC client**, không phải access token dành cho Resource Server.
- Resource Server phải xác thực access token được cấp cho audience của API và theo token profile được chấp nhận.
- Không gửi ID token đến API chỉ vì ID token có chữ ký được xác minh bằng cùng JWKS.
- Nếu issuer dùng cùng khóa ký cho nhiều loại JWT, kế hoạch loại K_old phải xét **tất cả token còn hợp lệ** mà những relying party / verifier có trách nhiệm chấp nhận.
- Một số nhà cung cấp tách khóa ký ID token, access token hoặc môi trường/tenant; phải dùng metadata/hợp đồng phù hợp với từng loại token.

Key rollover là **quản lý phương tiện xác minh chữ ký**, không phải cơ chế hoán đổi ngữ nghĩa giữa OAuth 2.0 access token, OIDC ID token hoặc refresh token.

## 15. Các dấu hiệu vận hành khi thời gian chồng lấn không phù hợp

### 15.1. Token K_new bị 401 ngay sau khi chuyển signer

Nguyên nhân thường gặp:

1. K_new chưa có trong JWKS mà Resource Server tải được.
2. JWKS cache/CDN còn trả bộ khóa cũ.
3. Resource Server không refresh khi `kid` chưa biết.
4. Thuật toán ký mới không nằm trong decoder allowlist.
5. JWK `kid`, `use`, `kty` hoặc material bị cấu hình sai.
6. Token có issuer/audience/profile khác hợp đồng, không liên quan riêng tới JWKS.

Giải quyết bằng cách kiểm tra **JWKS thực tế đang được từng instance nhìn thấy**, key selection và validation result. Đừng tắt signature validation hoặc cho phép mọi thuật toán để tạm giải quyết 401.

### 15.2. Token K_old bắt đầu 401 sau khi xóa public key

Đây là dấu hiệu K_old có thể bị **loại quá sớm** nếu có token chưa hết hạn. Những nguyên nhân hay gặp:

- Tính từ `T_start_new_signing` thay vì `T_last_old_signing`.
- Dùng TTL mặc định 15 phút trong khi một số client nhận token 60 phút.
- Quên clock skew hoặc token profile có tuổi thọ khác.
- Có Authorization Server node vẫn ký K_old sau đợt rollout.
- Đã xóa K_old khỏi JWKS nhưng client đang dùng token cũ hợp lệ.

Nếu K_old **không bị compromise**, một hành động phục hồi có thể là xuất bản lại public JWK K_old tạm thời theo kế hoạch đã phê duyệt, đồng thời điều chỉnh thời điểm retirement. Nếu K_old bị compromise, không nên khôi phục trust chỉ để giảm 401.

### 15.3. Cùng token lúc 200, lúc 401

Điều này có thể xảy ra khi Resource Server nằm sau load balancer và các instance có cache JWKS khác nhau:

~~~text
Instance A: [K_old, K_new]  → JWT K_new hợp lệ
Instance B: [K_old]         → JWT K_new chưa có key
Instance C: [K_new]         → JWT K_old chưa hết hạn bị fail
~~~

Với token test hợp lệ theo policy, kiểm tra từng instance/cấu hình/caching path và xác nhận issuer JWKS đang công bố gì. Không giải quyết bằng sticky session như một biện pháp bảo mật duy nhất; nó chỉ che giấu sự khác biệt giữa các instance.

### 15.4. Chữ ký đúng nhưng 403

Nếu JWT đã xác thực thành công và có `kid` phù hợp, nhưng thiếu scope hoặc role, Resource Server thường trả **403 Forbidden**. Đây là vấn đề authorization, không nhất thiết liên quan key rollover. Cần tách ba nhóm:

| Nhóm | Bước xử lý | Dấu hiệu |
|---|---|---|
| Thiếu key/khóa/issuer/time/audience | Authentication / JWT decoder | Thường 401 |
| Token hợp lệ nhưng scope/role thiếu | HTTP/method authorization | Thường 403 |
| Token hợp lệ, scope đủ nhưng không sở hữu tài nguyên | Domain authorization | 403 hoặc 404 theo policy |

Với lỗi tải JWKS từ mạng, status trả ra có thể khác với token invalid thực sự tùy exception handling. Bất kể HTTP status nào, **không cho request có JWT chưa được xác minh đi vào nghiệp vụ như principal đã xác thực**.

## 16. Ma trận kịch bản cần đưa vào quy trình tích hợp rollover

Việc test một token K_new thành công là chưa đủ chứng minh quá trình chồng lấn an toàn. Cần thiết kế các trường hợp tương ứng với từng giai đoạn:

| Kịch bản | JWKS Resource Server nhìn thấy | JWT được gửi | Hành vi kỳ vọng |
|---|---|---|---|
| Trước prepublication | Chỉ K_old | Token ký K_old, chưa hết hạn, policy hợp lệ | Xác thực thành công |
| Vừa công bố K_new | K_old + K_new | Token ký K_old | Vẫn xác thực thành công |
| Đang chồng lấn | K_old + K_new | Token ký K_new | Xác thực thành công |
| Đang chồng lấn | K_old + K_new | Token K_old đã hết hạn | Từ chối vì `exp` dù có public key |
| Chưa cập nhật cache | Chỉ K_old | Token mới ký K_new | Có thể cần refresh; phải có kết quả kiểm soát được |
| Xóa K_old quá sớm | Chỉ K_new | Token K_old chưa hết hạn | Có nguy cơ 401 — hành vi không mong muốn với rotation bình thường |
| Sau retirement đúng lịch | Chỉ K_new | Token K_old đã hết hạn | Từ chối theo thời gian; không còn phụ thuộc K_old |
| Sau retirement | Chỉ K_new | Token K_new hợp lệ | Xác thực thành công |
| Thay chữ ký token | K_old + K_new | JWT bị sửa payload/signature | Từ chối |
| Sai issuer | K_old + K_new | JWT ký bằng key được biết nhưng `iss` sai | Từ chối |
| Sai audience | K_old + K_new | JWT dành cho Billing API | Từ chối tại token validation |
| Thuật toán sai policy | Có JWK nhưng token dùng `alg` không cho phép | JWT ký với algorithm khác | Từ chối |
| Cùng token qua 2 instance | Cache một instance mới, một instance cũ | Token ký K_new | Nhận diện khả năng không nhất quán; tránh lỗi luân phiên |
| JWKS endpoint timeout | Cache có/không có key cần thiết | JWT hợp lệ | Không cho token chưa kiểm chứng qua; quan sát lỗi mạng riêng |
| Emergency compromise | K_old đã bị thu hồi trust | Token ký K_old dù chưa hết hạn | Bị từ chối theo incident policy |

### 16.1. Phân biệt kiểm tra decoder và kiểm tra HTTP authorization

Một test Spring Security có thể mock `JwtAuthenticationToken` hoặc dùng `jwt()` request post processor để kiểm tra `hasAuthority("SCOPE_orders.read")`. Nhưng test đó thường **bỏ qua chữ ký và JWKS lookup**, nên không chứng minh quá trình rollover có hoạt động.

Để kiểm tra **JWKS rollover thực**, môi trường tích hợp có thể:

1. Dùng hai cặp key thử nghiệm K_old/K_new được tạo riêng cho test.
2. Dựng một issuer/JWKS endpoint thử nghiệm có khả năng trả các bộ khóa `[K_old]`, `[K_old, K_new]`, `[K_new]`.
3. Phát hành hai JWT thử nghiệm bằng private key tương ứng, với `kid`, `iss`, `aud`, `exp`, `scope` phù hợp.
4. Cho Resource Server thực (hoặc decoder thật) xác minh qua JWKS endpoint thử nghiệm.
5. Mô phỏng cache stale và thời gian chuyển key.
6. Kiểm tra JWT chưa hết hạn vẫn qua được giai đoạn overlap và JWT hết hạn vẫn bị từ chối.

Không dùng private key production trong các bài test tích hợp. Nếu test điều khiển thời gian, hãy cấp clock rõ ràng cho thành phần hỗ trợ thay vì sửa đồng hồ hệ điều hành của cả máy chạy dịch vụ.

### 16.2. Quan sát bằng dữ liệu nào?

Có thể dùng metric, trace và audit ở mức metadata an toàn:

- Thời điểm công bố K_new trong JWKS.
- Thời điểm bắt đầu ký K_new và **thời điểm cuối cùng thực sự ký K_old**.
- Số token phát hành theo `kid` và phân loại token TTL/profile, **không ghi raw token**.
- Số lỗi unknown `kid`, thiếu key, signature, issuer, audience, expired token.
- Thời gian JWKS fetch/refresh và tỷ lệ lỗi mạng.
- Sự khác biệt giữa các Resource Server instance.
- Số lỗi HTTP 401 và 403 trước/trong/sau cutover theo service.

Khi dùng `kid` làm metadata trong log, chỉ ghi từ tập khóa/issuer được kiểm soát hoặc có quy tắc giới hạn dữ liệu vì `kid` trong request token chưa xác minh có thể chứa giá trị tùy ý. Tuyệt đối không ghi JWT hoàn chỉnh, private key hoặc credential khác vào dashboard/trace.

## 17. Công thức ra quyết định thực tế

Đối với một khóa cũ dùng ký JWT access token, có thể tách thành hai điều kiện:

### 17.1. Điều kiện bắt đầu ký bằng khóa mới

~~~text
Allowed to start signing K_new
    =
    K_new đã được công bố trong JWKS đáng tin
    AND các verifier cần thiết có thể nhận K_new
    AND thuật toán/key type được Resource Server hỗ trợ
    AND issuer/audience/profile không bị thay đổi ngoài kế hoạch
    AND có khả năng quan sát lỗi/rollback đã phê duyệt
~~~

Đừng dùng một tiêu chí đơn như “đã thêm JWK vào JWKS một lần” khi toàn bộ hệ thống có cache nhiều tầng và nhiều node.

### 17.2. Điều kiện loại khóa cũ

~~~text
Allowed to remove K_old in normal rotation
    =
    Không còn issuer node nào ký bằng K_old
    AND đã biết mốc ký K_old cuối thực tế
    AND mọi JWT có thể hợp lệ ký K_old đã qua exp
    AND đã xét clock skew và safety margin
    AND không còn token profile/khách hàng khác cần xác minh K_old
    AND operation policy cho phép retire
~~~

Khi tuổi thọ tối đa được kiểm soát chặt:

~~~text
T_remove_old >=
    T_last_old_signing
    + L_max_old
    + S_validation
    + M
~~~

Nếu khóa bị compromise, điều kiện **“bảo toàn token chưa hết hạn”** có thể phải nhường chỗ cho chính sách ứng cứu: thu hồi trust K_old sớm hơn, vô hiệu hóa cache và chấp nhận tác động lên availability.

## 18. Các nhầm lẫn phổ biến

**“Đã đổi private signing key nên xóa public key cũ ngay được.”** Không đúng với routine rotation. Token cũ đã ký vẫn có thể hợp lệ đến `exp`; chúng cần public key cũ để xác minh.

**“JWKS cache TTL là 5 phút, vậy giữ old key 5 phút đủ.”** Không đúng. Cache TTL liên quan việc verifier cập nhật key, còn thời gian giữ K_old liên quan lifetime của token ký K_old.

**“Token cũ sẽ tự đổi chữ ký khi client refresh.”** Không. Một JWT đã phát hành là chuỗi immutable; nó tiếp tục mang chữ ký K_old. Client có thể nhận token **mới** bằng flow phù hợp, nhưng token cũ không được sửa chữ ký.

**“Giữ old key trong JWKS làm token hết hạn vẫn dùng được.”** Không. Resource Server vẫn phải kiểm tra `exp`, `nbf` và các validator khác. Public key chỉ giải quyết khả năng xác minh chữ ký.

**“Xóa K_old khỏi JWKS là mọi verifier dừng tin K_old ngay.”** Không nhất thiết: cache ở JVM, gateway hoặc CDN có thể còn giữ bản cũ. Emergency revocation cần cơ chế vô hiệu hóa cache/trust tương ứng.

**“`kid` là duy nhất trên toàn Internet.”** Không. Nó là key identifier trong ngữ cảnh JWK Set/issuer và phải được quản lý không mơ hồ trong phạm vi hệ thống. Không dùng `kid` để thay issuer validation.

**“Cứ cho phép mọi thuật toán là sẽ tránh lỗi khi đổi key.”** Không. Resource Server phải có allowlist thuật toán được phê duyệt, thay đổi algorithm là một migration có chủ đích.

**“Nếu JWT ký đúng thì chắc chắn dành cho API này.”** Không. Token vẫn có thể sai `iss`, `aud`, loại token hoặc scope. Chữ ký chỉ là một trong các điều kiện xác thực.

**“Có thể rollback về K_old dù private key bị lộ.”** Không an toàn. Khi K_old đã bị compromise, chiến lược ưu tiên là thu hồi trust và thay bằng khóa an toàn khác.

**“Mọi JWT đều có TTL như access token của user.”** Không. Một issuer có thể phát hành nhiều loại JWT với tuổi thọ và đối tượng nhận khác nhau. Nếu cùng signing key được dùng, lịch retirement cần xét mọi verifier/token còn hợp lệ mà key đó phục vụ.

## 19. Tình huống thực hành

Giả sử hệ thống có thông số:

~~~text
Issuer:              https://idp.example.test/realms/company
Orders API audience: orders-api
Signing key cũ:      K_old
Signing key mới:     K_new
JWKS cache stale tối đa (đã đo/định nghĩa): 7 phút
Access token TTL tối đa:                   45 phút
Clock skew validator tối đa:               3 phút
Safety margin vận hành:                    5 phút
~~~

### Câu hỏi 1 — Công bố K_new lúc 10:00, có thể ký K_new lúc 10:01 không?

Không nên mặc định là an toàn. Nếu cache JWKS ở một số Resource Server còn stale tới 7 phút, chúng có thể chưa biết K_new lúc 10:01. Cần đợi đủ propagation theo chính sách (và có quan sát xác nhận) trước khi kích hoạt K_new; trong ví dụ này có thể chọn một khoảng lớn hơn 7 phút thay vì chỉ một phút.

### Câu hỏi 2 — Mọi node ngừng ký K_old lúc 10:12. Khi nào loại K_old theo công thức?

~~~text
T_last_old_signing = 10:12
L_max_old          = 45 phút
S_validation       =  3 phút
M                  =  5 phút

T_remove_old >= 10:12 + 45 + 3 + 5 = 11:05
~~~

Đây là thời điểm **sớm nhất theo giả định được cung cấp**, không phải cam kết thời gian bắt buộc. Nếu còn loại token khác ký K_old có TTL dài hơn, hoặc một node tiếp tục ký sau 10:12, mốc 11:05 phải được tính lại.

### Câu hỏi 3 — Đến 10:50, JWKS còn K_old và K_new; JWT ký K_old có `exp=10:40` có được chấp nhận không?

Không, nếu đã qua thời hạn và dung sai skew cho phép. K_old nằm trong JWKS chỉ giúp **xác minh chữ ký**, không làm token kéo dài thời gian sử dụng.

### Câu hỏi 4 — Đến 10:50, client còn JWT ký K_old với `exp=10:55`; nếu xóa K_old ngay có an toàn không?

Với **rotation định kỳ**, không nên: JWT vẫn có thể hợp lệ tới `exp` cộng dung sai, nên xóa khóa cũ có nguy cơ làm request từ chối sai kỳ vọng. Nếu **private K_old đã bị lộ**, việc thu hồi sớm có thể là lựa chọn cần thiết theo incident policy.

### Câu hỏi 5 — Token K_new bị 401 nhưng K_old dùng được, nên nới rule `permitAll`?

Không. Phải kiểm tra source JWKS Resource Server nhìn thấy, key `kid` mới, allowed `alg`, issuer/audience/time validator và khả năng refresh cache. Tắt authentication hoặc `permitAll` sẽ phá ranh giới bảo mật của API.

## 20. Kết luận

Trong hệ thống OAuth 2.0/OIDC Resource Server sử dụng JWT:

- **Khóa ký mới được công bố trước khi sử dụng**, để các Resource Server có cơ hội biết khóa và chuẩn bị cache/thuật toán xác minh.
- **Khóa ký cũ có thể ngừng phát hành ngay khi chuyển sang khóa mới**, nhưng public key cũ **phải còn được công bố** trong routine rotation khi vẫn có token ký K_old có thể hợp lệ.
- **Thời gian giữ khóa cũ phụ thuộc lần ký cuối thực tế, tuổi thọ token lớn nhất, clock skew và biên vận hành**, không phải chỉ phụ thuộc TTL của JWKS cache.
- **Spring Security Resource Server phải tiếp tục xác minh chữ ký, nguồn khóa, issuer, audience, thời gian hiệu lực, token profile và scope**, dù JWKS có đồng thời khóa cũ và khóa mới.
- **Key compromise là ngoại lệ quan trọng**: khi private key bị lộ, an toàn có thể yêu cầu thu hồi trust sớm, chủ động làm mất hiệu lực các token cũ chưa hết hạn và vô hiệu hóa những bản cache key không còn được phép tin.

Hai khoảng thời gian cần được quản lý riêng là **prepublication của K_new** và **retention của K_old sau khi ngừng ký**. Thiết kế đúng cả hai giúp thay khóa ký JWT mà không tạo cửa sổ từ chối những access token vẫn hợp lệ, đồng thời không đánh đổi các điều kiện xác thực bắt buộc để duy trì khả năng phục vụ.

## Tài liệu tham khảo

- [RFC 7517 — JSON Web Key (JWK) và JWK Set](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — NimbusJwtDecoder](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [Spring Security — JwtValidators](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/JwtValidators.html)
