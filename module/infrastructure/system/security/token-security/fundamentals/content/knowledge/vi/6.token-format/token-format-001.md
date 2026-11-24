# Token có cấu trúc và token chỉ là chuỗi ngẫu nhiên

Giả sử hai ứng dụng đều nhận được access token sau khi đăng nhập OAuth 2.0:

- Hệ thống A trả về chuỗi có ba phần ngăn bằng dấu chấm. Khi giải mã phần giữa, lập trình viên thấy `sub`, `aud`, `scope`, `exp`.
- Hệ thống B trả về chuỗi ký tự khó đoán, không có thông tin nào đọc được. API phải hỏi máy chủ cấp token hoặc tra kho lưu trữ để biết chuỗi đó đại diện cho ai và được phép làm gì.

Cả hai token đều **có thể là access token hợp lệ và an toàn khi được thiết kế, sử dụng đúng**. Sự khác biệt cốt lõi nằm ở **cách biểu diễn dữ liệu và cách bên nhận xác minh**. Token có cấu trúc cho phép chứa thông tin và bằng chứng toàn vẹn ngay trong token; token tham chiếu ngẫu nhiên thường chỉ là một **khóa tra cứu bí mật** trỏ tới trạng thái phía máy chủ.

Trong phần **Token format** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, bài này giúp phân biệt JWT, opaque token, access token và refresh token; hiểu phát hành, kiểm tra issuer/claims/scope/audience, lưu trữ, thu hồi, bảo vệ trước đánh cắp hoặc phát lại trong OAuth 2.0 và OpenID Connect (OIDC).

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **token có cấu trúc** với **token ngẫu nhiên dạng tham chiếu**; hiểu vì sao “opaque” không đồng nghĩa bắt buộc “random”.
2. Giải thích JWT, JWS, JWE, claim, chữ ký, khóa xác minh, reference token và introspection.
3. Xác định **access token/refresh token/ID token** theo *mục đích sử dụng* thay vì suy ra từ hình thức chuỗi.
4. Thiết kế quy trình phát hành và kiểm tra JWT access token hoặc opaque access token tại Resource Server.
5. Chọn cách lưu và thu hồi token; nhận diện giới hạn của JWT tự chứa, cache introspection, tính ngẫu nhiên và độ dài token.
6. Đánh giá rủi ro token bị sửa, bị lộ, bị phát lại, bị dùng sai audience hoặc bị nhầm loại.

## 2. Hai trục phân loại phải tách riêng

Hãy đặt hai câu hỏi khác nhau:

- **Token được biểu diễn như thế nào?** Có cấu trúc tự mô tả, có chữ ký/mã hóa, hay chỉ là chuỗi tham chiếu không thể hiểu trực tiếp?
- **Token được dùng để làm gì?** Truy cập API, đổi lấy token mới, hay thông báo kết quả xác thực cho một OIDC Client?

| Trục | Nhóm | Ý nghĩa |
|---|---|---|
| **Định dạng / biểu diễn** | JWT có cấu trúc | Các thành phần được định nghĩa theo chuẩn JWT/JOSE; có thể mang claims ngay trong token. |
| **Định dạng / biểu diễn** | Opaque token | Bên cầm token **không thể hoặc không nên tự diễn giải** chuỗi theo hợp đồng giao thức; cần một cách xác minh đã được chỉ định. |
| **Cách triển khai opaque** | Random reference token | Chuỗi ngẫu nhiên có entropy cao, dùng làm khóa tham chiếu đến bản ghi trạng thái token ở phía server. |
| **Mục đích** | Access token | Chứng chỉ ủy quyền được client gửi đến **Resource Server** để gọi tài nguyên bảo vệ. |
| **Mục đích** | Refresh token | Bí mật được client gửi về **Authorization Server** để xin access token mới theo grant phù hợp. |
| **Mục đích** | ID token trong OIDC | Token xác thực được **OpenID Provider** cấp cho **OIDC Client**, không phải access token của API. |

Các kết hợp phổ biến:

- **JWT access token:** API kiểm chữ ký và claims tại chỗ bằng khóa đáng tin cậy.
- **Opaque random access token:** API tra cứu bản ghi hoặc hỏi Authorization Server bằng token introspection.
- **Opaque refresh token:** Client giữ một chuỗi bí mật và gửi đến token endpoint; AS kiểm trạng thái, client binding và rotation.
- **JWT ID token:** OIDC Client kiểm issuer, audience là client của mình, chữ ký và quy tắc OIDC.

**Không suy luận “thấy ba đoạn có dấu chấm thì chắc chắn là access token”**. Một chuỗi ba phần có thể là JWT chưa kiểm, ID token, JWT thuộc issuer khác hoặc nội dung giả mạo. Ngược lại, một access token opaque hoàn toàn có thể hợp lệ dù không giải mã thành JSON.

### 2.1. “Opaque” không luôn có nghĩa là chuỗi ngẫu nhiên

Một **random reference token** thường là opaque: nó chỉ có ý nghĩa khi được tra đúng kho trạng thái. Nhưng một token opaque **cũng có thể chứa cấu trúc nội bộ**, ví dụ blob mã hóa hoặc chuỗi định dạng riêng mà Resource Server không được giải nghĩa. “Opaque” mô tả **giao diện và kỳ vọng của bên nhận**, không cam kết thuật toán tạo chuỗi cụ thể.

Ngay cả khi Authorization Server phát JWT access token, client **nên coi access token là opaque đối với chính client**: không phụ thuộc các claim nội bộ chưa được hợp đồng API bảo đảm. Resource Server mới là bên áp dụng hồ sơ token tương ứng.

## 3. JWT: token có cấu trúc và claims

JWT (JSON Web Token, RFC 7519) định nghĩa tập claims biểu diễn trong JSON cùng các cách bảo vệ trong hệ sinh thái JOSE. Một dạng rất phổ biến là **JWS Compact Serialization** gồm ba đoạn:

~~~text
BASE64URL(protected_header).BASE64URL(payload).BASE64URL(signature)
~~~

Ví dụ dạng hiển thị rút gọn, **không phải token hợp lệ để sử dụng thật**:

~~~text
eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleS0yMDI2In0.
eyJpc3MiOiJodHRwczovL2xvZ2luLmV4YW1wbGUuY29tIn0.
<signature-bytes-base64url>
~~~

Trong truyền thực tế, ba phần sẽ nằm trên **một dòng liên tục**, không chèn xuống dòng hay dấu `< >`.

### 3.1. Header cho biết cách kiểm bảo vệ mật mã

Ví dụ protected header:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "signing-key-2026"
}
~~~

- `alg`: thuật toán chữ ký mà token khai báo. **Resource Server vẫn phải kiểm thuật toán này thuộc danh sách cho phép** theo cấu hình của issuer; không tin tùy ý header chưa kiểm.
- `typ`: gợi ý loại token. `at+jwt` được dùng trong JWT Profile for OAuth 2.0 Access Tokens (RFC 9068), giúp giảm nhầm loại khi được validator kiểm theo hồ sơ.
- `kid`: định danh **chọn khóa trong tập khóa đã tin cậy**; không phải bằng chứng khóa hoặc issuer tự nó đáng tin.

Không cho token điều khiển việc tải khóa từ một URL bất kỳ trong header, ví dụ `jku`/`x5u`, rồi tin khóa đó. Việc khám phá metadata/JWKS phải **gắn với issuer đã được cấu hình** và dùng kết nối được bảo vệ.

### 3.2. Payload chứa claims

Ví dụ JWT access token được cấp cho API đơn hàng:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": ["orders-api"],
  "client_id": "shop-web",
  "scope": "orders:read orders:create",
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893456000,
  "jti": "at-7f93"
}
~~~

| Claim | Vai trò | Lưu ý |
|---|---|---|
| `iss` | Issuer phát hành token | API so với danh sách issuer đáng tin. |
| `sub` | Chủ thể token đề cập | Có thể là user **hoặc client/service**, tùy grant và profile. |
| `aud` | Resource Server được nhận token | Phải chứa audience của **API hiện tại**. |
| `scope` | Phạm vi ủy quyền | Không thay kiểm quyền trên từng endpoint và tài nguyên. |
| `iat` | Thời điểm phát hành | Không phải thời điểm đăng nhập hay MFA gần nhất. |
| `nbf` | Mốc bắt đầu có hiệu lực | Phải được kiểm nếu token dùng claim này. |
| `exp` | Thời điểm hết hiệu lực | API từ chối sau mốc này theo đồng hồ và leeway hợp lý. |
| `jti` | Định danh token | Dùng trong audit/revocation nếu hệ thống triển khai; **không tự chống replay**. |
| `client_id` | Client được AS gắn với token | Không phải claim bắt buộc ở mọi hồ sơ JWT. |

Các claim cụ thể thay đổi theo hồ sơ token và hợp đồng AS–Resource Server. **Giải mã được JSON không chứng minh claims là thật.** Chỉ được tin claims sau khi kiểm chữ ký hoặc cơ chế bảo vệ thích hợp, issuer, audience, thời gian, loại token và chính sách.

### 3.3. JWS ký và JWE mã hóa không giống nhau

- **JWS** cung cấp bằng chứng **toàn vẹn và nguồn ký** (theo khóa, thuật toán và trust config). Payload JWT JWS Compact thường đọc được sau Base64URL decode. **Ký không đồng nghĩa mã hóa**.
- **JWE** bảo mật nội dung được mã hóa cho bên có khóa giải mã, với cơ chế bảo vệ toàn vẹn tương ứng. Compact JWE thường có **năm** phần, không phải ba.
- Có thể có **nested JWT** (ký rồi mã hóa hoặc cấu trúc khác). Cần thư viện và hồ sơ quy định chính xác bước giải mã, kiểm chữ ký và thứ tự xử lý.

Vì vậy, không lưu mật khẩu, API key, thông tin cá nhân nhạy cảm hoặc dữ liệu nội bộ không cần thiết trong payload **JWT chỉ ký**. JWT không phải kho bí mật.

## 4. Random reference token: chỉ là khóa tra cứu

Một cách phát hành token opaque là:

1. AS dùng **CSPRNG** (cryptographically secure pseudorandom number generator) sinh chuỗi có entropy đủ lớn.
2. AS lưu **bản ghi token**: mã định danh hoặc hash token, chủ thể, client, scope, audience, expiry, trạng thái và chính sách.
3. AS trả **giá trị token bí mật** cho client; client gửi giá trị này trong header `Authorization: Bearer ...` tới API.
4. Resource Server **không tự diễn giải chuỗi**, mà tra cứu thông tin tại AS (ví dụ introspection) hoặc tại kho đã được ủy thác.

Mô hình:

~~~mermaid
flowchart LR
    AS[Authorization Server] -->|Sinh token ngẫu nhiên| T[Chuỗi token bí mật]
    AS -->|Lưu hash + metadata| DB[(Kho trạng thái token)]
    T -->|Cấp cho| C[Client]
    C -->|Bearer token| API[Resource Server]
    API -->|Introspection / lookup đáng tin| AS
    AS -->|Đối chiếu trạng thái| DB
    AS -->|Active + metadata tối thiểu| API
~~~

Điểm quan trọng: **bản thân chuỗi không cần mang claims**. Năng lực của token đến từ bản ghi phía server và chính sách kiểm tra, không đến từ việc API phân tích các ký tự trong chuỗi.

### 4.1. Độ ngẫu nhiên và không thể đoán

Nếu tạo token tham chiếu, yêu cầu quan trọng là **entropy** và **khả năng dự đoán**, không phải chuỗi “nhìn phức tạp”.

- Nên dùng CSPRNG của nền tảng, không dùng `Math.random()`, `java.util.Random`, timestamp, ID tăng dần hoặc hash đơn giản của email/user ID.
- Một lựa chọn thường dùng cho bearer reference token là **32 byte ngẫu nhiên = 256 bit entropy**, rồi mã hóa Base64URL không padding (khoảng **43 ký tự**). Ví dụ này minh họa thiết kế có biên an toàn rộng; chính sách cụ thể còn tùy nguy cơ và tiêu chuẩn hệ thống.
- Tối thiểu 128 bit entropy thường được dùng cho nhiều bí mật sinh ngẫu nhiên; việc chọn độ dài phải xét số token phát hành, thời hạn, khả năng thử đoán và kiểm soát rate limit.
- Base64URL, hex hay UUID **chỉ là cách biểu diễn**. Encoding không tăng entropy của dữ liệu gốc.
- Token cần được sinh mới cho từng lần cấp. Tránh ghép `userId + timestamp + secret` rồi tin chuỗi dài là khó đoán nếu thuật toán không có bảo đảm mật mã rõ ràng.

Xác suất collision xấp xỉ theo bài toán ngày sinh nhật:

\[
P(\text{có collision}) \approx \frac{n(n-1)}{2^{k+1}}
\]

Trong đó `n` là số token sinh độc lập, `k` là số bit ngẫu nhiên đều. Với `k=256`, xác suất va chạm cực nhỏ ở quy mô phát hành thông thường; vẫn có thể thiết kế ràng buộc **unique** trong kho lưu trữ để phát hiện tình huống bất thường.

### 4.2. Ví dụ Java sinh token tham chiếu

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class ReferenceTokenGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int TOKEN_BYTES = 32;

    public static String generate() {
        byte[] value = new byte[TOKEN_BYTES];
        RANDOM.nextBytes(value);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(value);
    }

    private ReferenceTokenGenerator() {}
}
~~~

Đoạn code chỉ làm nhiệm vụ **sinh chuỗi ngẫu nhiên**. Để trở thành access/refresh token dùng thật, AS còn phải quản lý metadata, cấp đúng client/đối tượng, expiry, scope, audience, trạng thái, chống lạm dụng, logging an toàn và cơ chế thu hồi. **Không in token ra log** để chứng minh sinh thành công.

## 5. JWT được tin như thế nào?

Với **JWT access token ký bất đối xứng**, AS giữ **private key** để ký; API dùng **public key** đáng tin cậy để kiểm. Ví dụ AS công bố public key qua JWKS, API gắn JWKS đó với issuer được cấu hình trước. Key rotation cần hỗ trợ khóa mới và giai đoạn chuyển đổi hợp lý.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant AS as Authorization Server
    participant API as Resource Server
    C->>AS: OAuth grant hợp lệ
    AS->>AS: Quyết định audience, scope, claims, TTL
    AS->>AS: Ký JWT bằng khóa phát hành
    AS-->>C: JWT access token
    C->>API: Authorization: Bearer JWT
    API->>API: Chọn khóa tin cậy theo issuer/kid
    API->>API: Kiểm chữ ký, thuật toán, typ, iss, aud, exp/nbf
    API->>API: Kiểm scope, principal, quyền trên resource
    API-->>C: 200 nếu đủ điều kiện; nếu không 401/403
~~~

Resource Server **không bắt buộc gọi AS cho từng request** khi đã có khóa và đủ thông tin để xác minh cục bộ. Nhưng API vẫn có thể cần dữ liệu trạng thái (tài khoản bị khóa, quyền vừa thu hồi, tenant membership, denylist) để ra quyết định cuối cùng.

### 5.1. Quy trình validator đúng

1. Chỉ cho phép **issuer** và bộ khóa đã cấu hình; không suy tin nguồn phát hành từ `iss` chưa xác minh.
2. Giới hạn **algorithms**/kiểu khóa, không nhận `alg=none` tùy ý và không rơi vào lỗi nhầm HMAC với RSA/ECDSA.
3. Kiểm chữ ký bằng thư viện uy tín; việc chọn khóa qua `kid` chỉ thực hiện trong bộ khóa hợp lệ.
4. Kiểm `iss`, `aud`, `exp`, `nbf`, cấu trúc claim, clock skew có giới hạn, loại token/hồ sơ (`typ` nếu được yêu cầu).
5. Kiểm `scope`, role/permission, ownership/tenant và các điều kiện nghiệp vụ **sau** validation.
6. Thực thi chính sách thu hồi/denylist hoặc lookup bổ sung khi mức độ rủi ro cần vô hiệu hóa token trước `exp`.

Các phần mềm có thể hỗ trợ sẵn một số validator nhưng **không được giả định mọi validator đều bật mặc định**, đặc biệt audience và quyền trên tài nguyên.

### 5.2. Đừng nhầm chữ ký hợp lệ với quyền hợp lệ

Một token có `aud=payments-api` không được gọi `orders-api` dù cùng issuer và chữ ký hợp lệ. Token có `scope=orders:read` không được gọi endpoint xóa đơn. Token đọc đơn thuộc tenant Anpha không được đọc đơn của Beta chỉ vì user đang đăng nhập. **Quyền API dựa trên policy của Resource Server**, không chỉ dựa vào việc claims tồn tại.

## 6. Opaque access token được tin như thế nào?

Với OAuth 2.0 Token Introspection (RFC 7662), Resource Server hỏi AS để kiểm access token opaque còn hoạt động hay không và nhận metadata:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant API as Resource Server
    participant AS as Authorization Server
    participant DB as Token Store
    C->>API: Authorization: Bearer opaque_token
    API->>AS: POST /introspect (API tự xác thực)
    AS->>DB: Tìm token / kiểm hash, expiry, revocation
    DB-->>AS: Metadata/trạng thái
    AS-->>API: active + thông tin token hợp lệ
    API->>API: Kiểm active, audience, scope, quyền tài nguyên
    API-->>C: Cho phép hoặc từ chối
~~~

Ví dụ **request introspection** (giá trị minh họa, không sử dụng token thật):

~~~http
POST /introspect HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <resource-server-credentials>

token=<opaque-access-token>&token_type_hint=access_token
~~~

`token_type_hint` chỉ là *gợi ý* cho server tối ưu lookup; không thay việc AS tự kiểm token loại nào. Cách xác thực Resource Server với AS (Basic, private_key_jwt, mTLS...) phụ thuộc cấu hình triển khai. Phải dùng TLS, bảo vệ credentials và giới hạn ai được introspect token.

Ví dụ phản hồi metadata khi active:

~~~json
{
  "active": true,
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "orders-api",
  "client_id": "shop-web",
  "scope": "orders:read",
  "exp": 1893456000
}
~~~

Các metadata khác `active` phụ thuộc AS và hợp đồng. Với `{"active": false}`, API **phải từ chối**; không suy đoán token “gần đúng” hay tự cấp quyền từ thông tin đã cache quá hạn. Với `active=true`, API vẫn cần kiểm audience, scope, trạng thái quyền, tenant/resource policy. Nếu metadata không đủ để ra quyết định an toàn, **fail closed** hoặc thực hiện lookup tin cậy bổ sung.

### 6.1. Vì sao introspection chưa phải là authorization toàn phần?

Introspection trả lời token có active và metadata liên quan trong phạm vi thông tin AS cung cấp. AS thường không biết Resource Server hiện đang xử lý **đơn hàng nào, thuộc người dùng nào, tenant nào, trạng thái đã khóa chưa**. API phải thực hiện object-level authorization theo dữ liệu nghiệp vụ của chính nó.

### 6.2. Phụ thuộc tính sẵn sàng và cache

Với introspection online, API phụ thuộc mạng và AS. Có thể cache kết quả để giảm độ trễ, nhưng **cache “active=true” làm chậm hiệu lực revocation**. Phải chọn TTL cache phù hợp với giới hạn rủi ro, expiry và yêu cầu cập nhật quyền. Khi AS không sẵn sàng và không có trạng thái cache còn hợp lệ theo chính sách, API nên **từ chối an toàn**, không chấp nhận mọi bearer token.

Một số kiến trúc dùng API Gateway làm điểm introspection tập trung, nhưng downstream chỉ nên tin kết quả/hệ thống gateway **đã được xác thực**, không tin header `X-User-Id` hoặc `X-Scope` do client bên ngoài có thể giả mạo.

## 7. Bảng so sánh định dạng và cơ chế xác minh

| Tiêu chí | JWT access token tự chứa (thường JWS) | Random reference access token (opaque) |
|---|---|---|
| Chuỗi trên đường truyền | Có header/payload/signature; payload có thể giải mã | Chuỗi CSPRNG không tự mô tả |
| Metadata về subject/scope/audience | Nằm trong claims, nếu issuer đặt vào | Nằm trong kho trạng thái/metadata introspection |
| API kiểm tính xác thực | Chữ ký + issuer/audience/thời gian/loại token | Lookup hoặc introspection từ nguồn đã tin |
| Phụ thuộc AS mỗi request | Không nhất thiết sau khi có khóa | Thường có nếu introspect online; cache/kiến trúc khác có thể giảm |
| Thu hồi sớm | Cần trạng thái bổ sung hoặc chờ token hết hạn | Đổi trạng thái server có thể thấy sớm, tùy cache |
| Lộ metadata khi client thấy token | JWT ký, không mã hóa: payload đọc được | Chuỗi random thường không lộ claims |
| Quản lý khóa / lưu trữ | Cần quản lý signing keys, JWKS, rotation | Cần CSPRNG, token store, lookup/index, quản lý secrets |
| Quy mô nhiều API | Thuận tiện xác minh phân tán nếu key distribution tốt | Có chi phí tra cứu/trạng thái trung tâm |
| Nguy cơ bị phát lại khi token bị đánh cắp | Có nếu là bearer token | Có nếu là bearer token |
| Rủi ro cấu hình nổi bật | Sai `alg`/`kid`/`aud`, token substitution, stale claims | Token entropy kém, lộ store, lookup thiếu audience, cache stale |
| Dữ liệu quyền đổi nhanh | Claim cũ có thể còn hiệu lực đến `exp` | Metadata có thể cập nhật nhanh nếu API không dùng cache cũ |

Không có định dạng “tự động an toàn tuyệt đối”. **JWT đã ký vẫn có thể bị đánh cắp**; random opaque token cũng có thể bị đoán nếu entropy kém hoặc bị lộ trong log. Khả năng tự xác minh, cách thu hồi, yêu cầu bảo mật metadata và chi phí vận hành là các trade-off kiến trúc thực tế.

### 7.1. “Stateless JWT” chỉ đúng ở mức độ nào?

JWT chứa claims cho phép kiểm tại chỗ, nhưng việc **quyết định quyền thực tế** vẫn có thể cần database/policy service. Nếu cần revocation tức thời, session state hoặc kiểm membership hiện hành, hệ thống JWT cũng phải có thành phần state bổ sung. “JWT = hoàn toàn stateless” là đơn giản hóa dễ gây sai thiết kế.

### 7.2. “Opaque” có bắt buộc introspection không?

Không. Introspection chuẩn OAuth là một cách phổ biến. Nếu Resource Server và AS cùng chia sẻ token store đáng tin, API có thể tra cứu trực tiếp theo hợp đồng nội bộ. Opaque cũng có thể được xử lý bởi gateway chuyên trách. Điểm bắt buộc là **có nguồn xác minh đáng tin và policy rõ**, không phải nhất định có một endpoint mạng cụ thể.

## 8. Vòng đời phát hành và lưu trữ token

### 8.1. Với JWT access token

Một quy trình điển hình:

1. AS kiểm client/grant, danh tính/ủy quyền, audience và scope.
2. AS chọn claims tối thiểu, TTL ngắn và key/algorithm đúng chính sách.
3. AS ký token (hoặc áp dụng profile bảo vệ phù hợp), trả qua kênh TLS.
4. Client lưu token theo mức rủi ro môi trường (browser, mobile, server) và gửi bearer token đến API.
5. API xác minh JWT, kiểm quyền và xử lý request; có thể dựa vào `exp` và trạng thái bổ sung.
6. AS xoay vòng khóa bằng JWKS/metadata đáng tin; API cập nhật keys đúng cách.

**Không đưa private signing key tới Resource Server** nếu dùng chữ ký bất đối xứng: API chỉ cần public key xác minh. Với HMAC, tất cả bên giữ shared secret đều có khả năng tạo chữ ký hợp lệ, làm ranh giới phát hành/xác minh khó tách hơn.

### 8.2. Với random reference token

AS có thể lưu dữ liệu như sau:

~~~text
token_records
  token_lookup_hash    # HMAC-SHA-256 hoặc SHA-256 theo thiết kế an toàn
  token_type           # access / refresh
  subject_id
  client_id
  audience
  scopes
  issued_at
  expires_at
  revoked_at
  status
  token_family_id      # nếu refresh rotation cần theo dõi family
~~~

**Không nhất thiết lưu nguyên token dạng rõ**. Với chuỗi ngẫu nhiên đủ entropy, có thể lưu **hash** hoặc **HMAC** làm khóa tra cứu. Khi client trình token, server tính cùng giá trị và so với index/bản ghi. HMAC với khóa bí mật độc lập có thể tăng phòng vệ khi kho dữ liệu bị lộ. Khóa HMAC phải được quản lý/bảo vệ/rotation đúng cách.

Khác mật khẩu do người dùng tự đặt, random token 256 bit có entropy cao; dùng hash mật mã nhanh có thể phù hợp để tra cứu. Không áp dụng máy móc “mọi bí mật phải bcrypt/Argon2” mà bỏ qua yêu cầu lookup hiệu quả và mô hình đe dọa. Ngược lại, nếu “token” được tạo từ ID ngắn, timestamp hoặc dữ liệu dễ đoán, **hash không sửa được vấn đề entropy gốc**.

Ví dụ pseudocode mô hình store:

~~~text
function issueOpaqueAccessToken(principal, client, audience, scopes, ttl):
    raw = base64url(cryptoSecureRandomBytes(32))
    key = HMAC_SHA256(serverLookupKey, raw)
    database.insert(
        lookupHash=key,
        type="access",
        principal=principal,
        client=client,
        audience=audience,
        scopes=scopes,
        expiresAt=now() + ttl,
        revoked=false
    )
    return raw

function introspectPresentedToken(raw):
    key = HMAC_SHA256(serverLookupKey, raw)
    record = database.findByLookupHash(key)

    if record is missing or record.revoked or now() >= record.expiresAt:
        return { active: false }

    return authorizedMetadataForCallingResourceServer(record)
~~~

Đây là pseudocode; triển khai thật cần transaction/unique constraints, chống race, kiểm quyền endpoint introspection, lưu secret key an toàn, cân nhắc so sánh nhạy timing, rate limit, monitoring và quản lý lỗi. Không trả metadata vượt quyền cho Resource Server không được phép introspect token đó.

### 8.3. Lưu token phía client

- **Backend/confidential client:** giữ token trong kho secret/session có kiểm soát truy cập, tránh log, backup không bảo vệ và telemetry.
- **Browser application:** cân nhắc mô hình backend-for-frontend (BFF) hoặc session cookie `HttpOnly`/`Secure`/`SameSite` phù hợp để giảm tiếp xúc token với JavaScript; vẫn cần xử lý CSRF và XSS theo mô hình.
- **Mobile/native client:** dùng cơ chế lưu secret an toàn của nền tảng khi có, hạn chế token xuất hiện ở log hoặc deep link.
- **Authorization header qua TLS:** ưu tiên `Authorization: Bearer <token>`, không đặt bearer token vào URL/query string vì dễ lọt vào browser history, access log hoặc referrer.

Không có cơ chế lưu nào bảo vệ tuyệt đối trước thiết bị/ứng dụng đã bị chiếm quyền; TTL, scope, phát hiện bất thường và revocation vẫn cần thiết.

## 9. Token format không quyết định access hay refresh

Một AS có thể phát hành:

| Token | Định dạng khả thi | Nơi sử dụng |
|---|---|---|
| Access token cho API | JWT hoặc opaque reference | Client gửi đến **Resource Server** |
| Refresh token | Thường là chuỗi opaque bí mật; có thể thiết kế khác theo profile | Client gửi đến **token endpoint của AS** |
| ID token trong OIDC | JWT theo profile OIDC | **OIDC Client** xác minh để xử lý kết quả xác thực |

**Refresh token không nên được Resource Server chấp nhận** dù có vẻ có cấu trúc như JWT. Chữ ký hợp lệ từ cùng AS cũng không biến ID token thành access token. Cần kiểm audience, token purpose/profile và chính sách của đúng bên nhận.

### 9.1. Refresh token rotation và reuse detection

Refresh token thường có tuổi thọ dài hơn access token và phải được bảo vệ nghiêm ngặt. Khi dùng **refresh token rotation**, AS có thể:

1. Nhận refresh token đang active và kiểm client binding/phiên/grant.
2. Vô hiệu hóa token cũ và phát refresh token mới cùng access token mới.
3. Ghi quan hệ token family hoặc grant để phát hiện việc token cũ bị dùng lại.
4. Khi phát hiện reuse đáng ngờ, áp dụng chính sách thu hồi family/phiên, yêu cầu đăng nhập lại hoặc điều tra.

**Phát access token mới sau refresh không đồng nghĩa người dùng vừa xác thực lại bằng MFA**. Nếu API cần độ mới xác thực, phải dựa trên bằng chứng như `auth_time` theo hợp đồng assurance, không dùng `iat` access token thay thế.

## 10. Thu hồi token và hành vi sau đăng xuất

### 10.1. JWT tự xác minh

Khi Resource Server chỉ kiểm chữ ký và `exp`, JWT đã phát hành có thể còn được chấp nhận đến hết hạn dù người dùng vừa logout, tài khoản bị khóa hoặc role đã bị hạ. Để vô hiệu hóa sớm có thể:

- Dùng TTL access token ngắn.
- Tra trạng thái phiên/grant/principal, token version hoặc denylist theo `jti`/hash phù hợp.
- Dùng revocation/introspection hoặc cơ chế trạng thái bổ sung cho tài nguyên nhạy cảm.
- Thu hồi refresh token để ngăn cấp access token mới; lưu ý **không tự thu hồi** mọi access JWT cũ.

### 10.2. Opaque reference token

AS có thể đặt `revoked_at` hoặc `status=revoked` trong kho lưu. Nếu API introspect online và AS kiểm trạng thái đó, token sẽ bị trả `active=false`. Tuy nhiên, **cache tại API/gateway có thể trì hoãn hiệu lực**; phải xác định mức trễ chấp nhận được.

### 10.3. Không đồng nhất “logout” và “revocation everywhere”

Logout ở client, logout tại OP, thu hồi refresh token và vô hiệu hóa access token là các hành động có cơ chế, phạm vi và độ trễ khác nhau. Tài liệu thiết kế nên nói rõ token nào bị ảnh hưởng, ở đâu, khi nào và cách kiểm thử.

## 11. Phát lại: token nào dễ bị lợi dụng?

Nếu cả JWT và opaque token được dùng dưới dạng **bearer token**, bên nào có bản sao token còn hiệu lực có thể gửi lại token đến API theo khả năng/quyền của nó. Xác minh chữ ký JWT hoặc introspection opaque **không tự chứng minh người gửi request là chủ thể hợp pháp ban đầu**.

Một số biện pháp bổ trợ:

1. Bảo vệ TLS, không lộ token vào URL, log, analytics, crash report hoặc thông báo lỗi.
2. Access token sống ngắn; giới hạn audience/scope/tenant, giới hạn quyền trên tài nguyên.
3. Refresh token rotation và kiểm reuse; bảo vệ client và secret storage.
4. Dùng **DPoP** hoặc **mTLS sender-constrained token** khi kiến trúc hỗ trợ. API phải kiểm binding giữa token và khóa/chứng chỉ, bằng chứng sở hữu khóa và các điều kiện chống replay theo giao thức.
5. Với giao dịch nhạy cảm, dùng step-up authentication, transaction authorization, idempotency và risk checks phù hợp.

**`jti` chỉ là một ID; nó không tự chống replay.** Nếu muốn xử lý replay theo `jti`, hệ thống phải duy trì trạng thái và quy tắc chấp nhận cụ thể. Tương tự, random token có 256 bit entropy vẫn bị phát lại được **nếu đã bị đánh cắp**.

## 12. Rủi ro bảo mật riêng từng định dạng

### 12.1. JWT

| Lỗi | Vì sao nguy hiểm? | Cách phòng vệ |
|---|---|---|
| Chỉ decode Base64URL rồi tin payload | Người tấn công tự đặt `sub`/`scope`/`aud` | Xác minh chữ ký/kiểu token trước khi dùng claims |
| Bỏ `iss` hoặc `aud` | Token issuer khác hoặc API khác bị nhận sai | Cấu hình nguồn phát hành và audience chính xác |
| Cho header quyết định khóa tùy ý | Kẻ tấn công đưa `jku` tới JWKS của họ | Chỉ nhận khóa từ issuer/config đáng tin |
| Nhận tùy ý `alg` | Dễ gặp lỗ hổng algorithm confusion/`none` | Whitelist thuật toán và kiểu khóa |
| Lẫn ID token/access token | Token đúng chữ ký nhưng sai mục đích | Kiểm token profile/`typ`/audience/claims theo hợp đồng |
| JWT chứa thông tin bí mật | Payload của JWS đọc được | Không chứa thông tin nhạy cảm trừ khi có cơ chế mã hóa phù hợp |
| Claim quyền cũ | Membership/role thay đổi mà token còn hiệu lực | TTL ngắn, lookup trạng thái hoặc cơ chế revoke |

### 12.2. Opaque reference token

| Lỗi | Vì sao nguy hiểm? | Cách phòng vệ |
|---|---|---|
| Sinh từ timestamp/ID tăng dần | Token đoán được | Dùng CSPRNG và entropy phù hợp |
| Lưu nguyên token trong DB/log | Lộ DB hoặc log có thể dùng token trực tiếp | Lưu hash/HMAC khi phù hợp, redact log |
| Tra hash nhưng không kiểm expiry/revocation | Token hết hạn vẫn active | Kiểm toàn bộ vòng đời và trạng thái |
| Introspection trả quá nhiều metadata | Bên không đủ quyền lấy thông tin chủ thể | Xác thực Resource Server, kiểm quyền response |
| Chỉ kiểm `active=true` | Nhận token sai audience/scope | Kiểm token purpose, audience, scope, resource policy |
| Cache active quá lâu | Thu hồi không có hiệu lực đúng kỳ vọng | TTL, invalidate cache, fail closed khi không đủ căn cứ |
| Token store phụ thuộc mạng không sẵn sàng | API từ chối/đình trệ hoặc fail open | Thiết kế độ sẵn sàng, timeout, cache an toàn, fail closed |

### 12.3. Sai lầm áp dụng cho cả hai

- Nhận access token đúng định dạng nhưng không kiểm quyền đối tượng (**BOLA/IDOR**) hoặc tenant.
- Nhận refresh token/ID token làm access token.
- Giả định “token ký hợp lệ” đồng nghĩa “được phép mọi thao tác”.
- Không phân biệt client credentials principal và end user.
- Đặt access token vào cookie hoặc header rồi bỏ CSRF/XSS protection theo mô hình thực tế.
- Truyền token giữa API mà không kiểm **audience** của từng Resource Server.
- Không phân biệt token bị sửa với token bị sao chép: mật mã bảo vệ toàn vẹn nhưng bearer token sao chép vẫn có thể được dùng.

## 13. Lựa chọn kiến trúc theo nhu cầu

Giả sử hệ thống có 25 microservices, yêu cầu độ trễ thấp, nhưng một số API tài chính cần thu hồi nhanh.

| Nhu cầu | Cách cân nhắc | Rủi ro cần xử lý |
|---|---|---|
| Nhiều API kiểm độc lập, AS không cần online mỗi request | JWT access token ký bất đối xứng, TTL ngắn, JWKS rotation | Validator phải đồng nhất; claims/permission có thể stale |
| Thu hồi sớm và quản lý phiên tập trung | Opaque reference + introspection hoặc stateful validation | Độ trễ, tải và tính sẵn sàng AS; cache active |
| Quyền thay đổi nhiều theo tenant/tài nguyên | Có thể dùng **bất kỳ định dạng**, nhưng API/PDP vẫn kiểm membership/resource hiện hành | Không nhét role cũ vào token rồi coi là nguồn chân lý vĩnh viễn |
| Không muốn lộ claims ra client | Opaque random; hoặc cơ chế mã hóa phù hợp nếu cần token có cấu trúc | Bảo vệ kho token, mã hóa và key management |
| Yêu cầu giảm phát lại khi token bị sao chép | Sender-constrained token DPoP/mTLS trên format được hỗ trợ | Kiểm possession/binding thực tế, không chỉ thêm claim |
| Ứng dụng nhỏ, một API và AS cùng miền tin cậy | Random reference + lookup nội bộ có thể đơn giản | Quản lý store, expiry, revocation và lookup an toàn |
| Mỗi request phải kiểm trạng thái tài khoản | Tra lookup/introspection hoặc dùng JWT kết hợp state check | Không coi JWT tự chứa là đầy đủ mọi dữ kiện authorization |

Một hệ thống có thể **kết hợp**: JWT access token TTL ngắn cho API có mức rủi ro vừa phải; opaque access token/online authorization cho thao tác cần thu hồi nhanh; refresh token bảo vệ riêng. Kiến trúc không nhất thiết chọn một định dạng cho toàn bộ loại token.

## 14. Ví dụ thiết kế API bán hàng

Giả sử:

- Authorization Server: `https://login.example.com`.
- Resource Server: `orders-api`.
- Client: `shop-web`.
- Endpoint `GET /orders/42` cần scope `orders:read` và quyền với đơn 42.

### 14.1. Khi chọn JWT access token

~~~text
bearer = request.Authorization
claims = trustedJwtVerifier.verify(
    bearer,
    trustedIssuer = "https://login.example.com",
    audience = "orders-api",
    allowedAlgorithmsAndKeys = serverConfiguration,
    requiredTokenProfile = "access"
)
if claims.invalid:
    return 401
if "orders:read" not in claims.scopes:
    return 403
if not orderPolicy.canRead(claims.subject, orderId=42):
    return 403
return 200
~~~

### 14.2. Khi chọn opaque reference access token

~~~text
bearer = request.Authorization
metadata = trustedIntrospectionClient.introspect(bearer)
if metadata.active != true:
    return 401
if metadata.audience does not include "orders-api":
    return 401
if metadata.type is known and metadata.type != "access":
    return 401
if "orders:read" not in metadata.scopes:
    return 403
if not orderPolicy.canRead(metadata.subject, orderId=42):
    return 403
return 200
~~~

Pseudocode chỉ minh họa **các điểm quyết định**, không phải triển khai xác minh mật mã hoặc tích hợp framework đầy đủ. Với cả hai, Resource Server phải có chính sách tránh rò trạng thái tài nguyên ngoài quyền và cơ chế lỗi nhất quán.

### 14.3. Với Spring Security

Spring Security OAuth2 Resource Server hỗ trợ lựa chọn **JWT decoder** hoặc **opaque token introspection**. Với JWT, cấu hình issuer/JWKS không đồng nghĩa audience luôn được kiểm đúng yêu cầu ứng dụng: cần kiểm validator/config thực tế. Với opaque token, cấu hình introspection endpoint và Resource Server credentials, sau đó ánh xạ metadata thành principal/authority một cách đáng tin cậy.

Dù dùng cấu hình nào, annotation scope như `hasAuthority('SCOPE_orders:read')` vẫn **chưa đủ** để bảo đảm người dùng được xem đơn 42. Kiểm ownership và tenant tại service/repository.

## 15. Bài thực hành

### Bài 1 — Phân loại token

| Token mô tả | Định dạng/mục đích | Bên kiểm tra phù hợp |
|---|---|---|
| `header.payload.signature`, `aud=orders-api`, dùng gọi GET /orders | JWT access token *nếu* đã được xác minh đúng | Orders Resource Server |
| Chuỗi ngẫu nhiên 256 bit, gửi đến GET /orders | Opaque reference access token *nếu* được AS cấp cho API | Orders Resource Server thông qua lookup/introspection |
| Chuỗi ngẫu nhiên, dùng xin access token mới | Opaque refresh token | Authorization Server/token endpoint |
| JWT có `aud=shop-web` và claims xác thực OIDC | ID token | OIDC Client `shop-web` |
| JWT có cấu trúc rõ nhưng từ issuer lạ | Chưa đáng tin | API từ chối nếu issuer không được cấu hình |

Chú ý: không xác định loại token **chỉ bằng hình dạng chuỗi**. Phải biết mục đích phát hành và trust contract.

### Bài 2 — Chọn cách xác minh

Dự án có hai hệ thống:

1. **API A** đọc báo cáo hàng nghìn request mỗi giây, cho phép quyền thay đổi có độ trễ nhỏ theo TTL access token. Đề xuất: JWT ngắn hạn, chữ ký bất đối xứng, audience và scope rõ, kiểm resource policy; thêm trạng thái nếu có yêu cầu đặc biệt.
2. **API B** thực hiện thay đổi thông tin ngân hàng, yêu cầu thu hồi quyền gần như ngay lập tức. Đề xuất: opaque + introspection/lookup trạng thái hoặc JWT + online state check, TTL/cache theo rủi ro, thêm step-up/transaction authorization khi cần.

Không được kết luận “A buộc phải JWT, B buộc phải opaque”. Đây là các hướng chọn **theo yêu cầu vận hành**.

### Bài 3 — Sửa thiết kế nguy hiểm

Một nhóm đề xuất sinh token như sau:

~~~text
token = base64(userId + ":" + timestamp)
database[token] = scope + expiry
~~~

**Vấn đề:** nội dung token đoán được; Base64 không tạo entropy, kẻ tấn công có thể suy hoặc brute-force. Sửa thành `base64url(CSPRNG(32 bytes))`, lưu hash/HMAC làm khóa lookup, gắn metadata/expiry/client/audience, kiểm quyền và rate limit.

Một nhóm khác cho API nhận mọi JWT mà thư viện decode được và dùng `scope` luôn. **Vấn đề:** decode không phải verify; phải ràng buộc issuer, thuật toán/khóa, chữ ký, audience, thời gian, token profile và sau đó kiểm quyền.

### Bài 4 — Ma trận kiểm thử âm tính

- JWT sai chữ ký, sai issuer, sai audience, hết hạn, `nbf` tương lai, `alg` không cho phép, `kid` lạ hoặc URL khóa giả.
- JWT ID token đưa vào access-token endpoint: từ chối.
- JWT đúng scope nhưng không có quyền trên đơn thuộc user/tenant khác: từ chối.
- Opaque token được sinh bằng RNG kém: kiểm thử/đánh giá chất lượng sinh, không dùng đoán được.
- Opaque token đã revoke/expired: introspection trả inactive và API từ chối.
- Opaque token active nhưng scope/audience không khớp API: từ chối.
- Introspection chậm/mất kết nối: hành vi fail closed đúng chính sách.
- JWT access token sau logout còn `exp`: kiểm rằng quyết định thu hồi **đúng cam kết kiến trúc**, không dựa vào giả định.
- Token lộ qua log rồi bị phát lại: kiểm giới hạn TTL/scope, sender binding nếu triển khai và cách phát hiện bất thường.
- Key rotation JWT: API chấp nhận đúng khóa mới, ngừng chấp nhận khóa đã bị rút theo chính sách.

## 16. Checklist triển khai

- [ ] Đã phân biệt **định dạng token** với **mục đích** (access, refresh, ID).
- [ ] Nếu dùng JWT: xác minh chữ ký, issuer, audience, exp/nbf, thuật toán, khóa, loại token và policy.
- [ ] Không tin claims của JWT chỉ vì decode được; không nhận `alg=none` tùy ý hay URL khóa do token chỉ định.
- [ ] Nếu dùng reference token: sinh bằng CSPRNG có entropy đủ lớn; không dùng timestamp/ID dễ đoán.
- [ ] Có kho token/lookup hash được bảo vệ, expiry, status, revoke và kiểm quyền introspection.
- [ ] Không đặt bí mật nhạy cảm trong JWT JWS payload đọc được.
- [ ] Không cho ID token/refresh token gọi Resource Server; không cho token sai audience đi qua.
- [ ] API kiểm scope và quyền tài nguyên/tenant riêng, dù token hợp lệ.
- [ ] Có chiến lược TTL, logout, refresh rotation, revoke và cache phù hợp yêu cầu hiệu lực.
- [ ] Token được lưu và truyền an toàn, không vào URL/log; có biện pháp giảm đánh cắp/phát lại.
- [ ] Có kiểm thử âm tính cho token giả, sai loại, sai issuer/audience, token hết hạn, revoked và thiếu quyền.
- [ ] Xác định hành vi an toàn khi khóa/JWKS hoặc AS introspection không sẵn sàng.

**Ghi nhớ:** JWT là **định dạng có cấu trúc**, thường cho API tự xác minh chữ ký và claims; random reference token là **bí mật khó đoán** mà server tra thành metadata. Opaque là khái niệm rộng hơn random. Cả hai có thể là access token; chúng đều phải được phát hành, xác minh và cấp quyền đúng, đồng thời phải bảo vệ vòng đời trước rò rỉ, thu hồi trễ và phát lại.

### Tài liệu chuẩn tham khảo

- **RFC 7519** — JSON Web Token (JWT).
- **RFC 7515** — JSON Web Signature (JWS).
- **RFC 7516** — JSON Web Encryption (JWE).
- **RFC 7517** — JSON Web Key (JWK), dùng với tập khóa JWKS.
- **RFC 8725** — JSON Web Token Best Current Practices.
- **RFC 9068** — JWT Profile for OAuth 2.0 Access Tokens.
- **RFC 6749** — OAuth 2.0 Authorization Framework (access/refresh token).
- **RFC 6750** — OAuth 2.0 Bearer Token Usage.
- **RFC 7662** — OAuth 2.0 Token Introspection.
- **RFC 7009** — OAuth 2.0 Token Revocation.
- **RFC 9449** — OAuth 2.0 Demonstrating Proof of Possession (DPoP).
- **RFC 9700** — Best Current Practice for OAuth 2.0 Security.
- **OpenID Connect Core 1.0** — ID token và các quy tắc xác minh.
