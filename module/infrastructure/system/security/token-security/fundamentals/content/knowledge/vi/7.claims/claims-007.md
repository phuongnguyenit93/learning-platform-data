# Scope claim

Trong OAuth 2.0, **scope** là cách mô tả phạm vi truy cập mà một client yêu cầu và được Authorization Server (AS) cho phép. Khi access token mang thông tin đó, **scope claim** giúp Resource Server (API) biết token được cấp những quyền thao tác nào theo hợp đồng của hệ thống. Ví dụ, token có `orders:read` có thể được dùng để yêu cầu đọc đơn hàng, trong khi `orders:write` là một phạm vi khác cần được cấp riêng nếu API quy định như vậy.

Bài học thuộc chương **Claims** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Trọng tâm là cách hiểu đúng scope trong mô hình tin cậy của JWT, opaque token, access token và refresh token; cách AS phát hành, API kiểm tra, giới hạn audience, thời gian, quyền dữ liệu và xử lý khi token bị thu hồi hoặc đánh cắp.

**Thông điệp chính:** scope claim chỉ là **một đầu vào** của quyết định phân quyền. API chỉ nên dùng nó **sau khi token đã được xác minh**, và chỉ cho phép thao tác khi người dùng hoặc client thực sự có quyền trên tài nguyên đích.

## 1. Scope là gì, scope claim là gì?

Ba cách nói thường xuất hiện ở những bước khác nhau:

| Khái niệm | Xuất hiện ở đâu? | Ý nghĩa |
|---|---|---|
| **Requested scope** | Client gửi `scope` trong authorization request hoặc token request | Những quyền client **muốn xin**; chưa phải quyền đã được cấp |
| **Granted scope** | AS quyết định sau khi kiểm tra client, grant, consent và policy | Những quyền **thực tế được chấp thuận** cho grant/token |
| **Scope claim** | Trong access token JWT hoặc kết quả introspection có thể có thuộc tính `scope` | Cách Resource Server nhận biết phạm vi quyền đã cấp để kiểm tra request |

Ví dụ:

~~~text
Client yêu cầu:     orders:read orders:write
AS chỉ chấp thuận:  orders:read
API cần đọc đơn:    orders:read       -> có thể qua bước kiểm tra scope
API cần xóa đơn:    orders:delete     -> thiếu scope, từ chối
~~~

Ngay cả khi client đã gửi `orders:write`, AS không có nghĩa vụ cấp scope đó. Client và API phải dựa trên **quyền thực sự được cấp**, không phải quyền xuất hiện trong request ban đầu.

**Scope không phải credential.** Chuỗi `orders:read` tự nó không chứng minh người gửi đã đăng nhập hay được phép truy cập. Nó chỉ có giá trị bảo mật khi được gắn với token/trạng thái tin cậy, có issuer và audience phù hợp, còn hiệu lực và được API đối chiếu với chính sách.

## 2. Mô hình tin cậy của scope claim

~~~mermaid
flowchart LR
    U["User / người có thẩm quyền"]
    C["Client: orders-web"]
    AS["Authorization Server"]
    API["Resource Server: Orders API"]
    DB[("Đơn hàng + ACL/tenant policy")]

    C -->|"Xin orders:read orders:write"| AS
    U -->|"Xác thực / consent khi cần"| AS
    AS -->|"Xét client, grant, policy"| AS
    AS -->|"Cấp access token: orders:read"| C
    C -->|"GET /orders/123 + access token"| API
    API -->|"Xác minh token, scope"| API
    API -->|"Kiểm tra chủ đơn hàng"| DB
    DB -->|"Dữ liệu được phép"| API
~~~

Mỗi bên trả lời một câu hỏi khác nhau:

1. **Client:** cần quyền gì để thực hiện chức năng này?
2. **User, admin hoặc chính sách:** có cho client sử dụng phạm vi yêu cầu không?
3. **Authorization Server:** client, grant, người có thẩm quyền và chính sách có cho phép cấp scope này tại thời điểm phát hành không?
4. **Resource Server:** access token có hợp lệ, dành cho API này và đủ scope cần thiết không?
5. **Tầng phân quyền dữ liệu:** subject/client này có quyền trên **đơn hàng cụ thể** hay không?

Lỗi phổ biến là bỏ bước 5. Một access token hợp lệ với scope `orders:read` không tự cấp quyền xem tất cả đơn hàng của mọi người dùng hoặc mọi tenant.

## 3. Cú pháp scope theo OAuth 2.0

Trong OAuth 2.0, giá trị `scope` chuẩn được biểu diễn bằng một **chuỗi các scope token phân tách bởi dấu cách ASCII** (`SP`). Mỗi scope token là một chuỗi ký tự không chứa khoảng trắng; tên cụ thể do AS và API định nghĩa.

Ví dụ:

~~~text
orders:read
orders:read orders:write
profile email
https://api.example.test/orders.read
~~~

Các điểm cần nhớ:

- **Dấu cách phân tách các scope**, không dùng dấu phẩy hoặc dấu chấm phẩy theo mặc định.
- **Scope token có phân biệt chữ hoa/chữ thường** theo OAuth: `orders:read` khác `Orders:Read` nếu hợp đồng hệ thống không định nghĩa cơ chế khác.
- **Thứ tự các scope không mang nghĩa phân cấp**; `orders:read orders:write` và `orders:write orders:read` thường biểu diễn cùng tập quyền.
- **Không tự giả định quyền kế thừa:** `orders:admin` không tự đồng nghĩa mọi scope khác, `orders:write` không tự bao gồm `orders:read`.
- **Không mặc định scope là URL:** dấu hai chấm, dấu gạch hoặc URL có thể là một phần tên scope nếu AS/API hỗ trợ; ý nghĩa phải được định nghĩa trong tài liệu của hệ thống.

Theo cú pháp RFC 6749, scope token thuộc tập ký tự ASCII được cho phép; ký tự dấu cách được dùng làm dấu phân cách, còn dấu nháy kép và dấu gạch chéo ngược không thuộc tập scope-token. Hệ thống nên dùng tên scope rõ ràng, ổn định, không gây nhập nhằng và kiểm tra đúng cú pháp/token profile.

### Scope là string hay array?

Với **JWT access token profile RFC 9068**, claim `scope`, nếu có, là một **chuỗi** các scope phân tách bằng khoảng trắng:

~~~json
{
  "scope": "orders:read orders:export"
}
~~~

Một số nhà cung cấp định danh dùng trường riêng như `scp`, có thể biểu diễn bằng chuỗi hoặc mảng theo hợp đồng của họ:

~~~json
{
  "scp": ["orders:read", "orders:export"]
}
~~~

Ví dụ `scp` ở trên chỉ minh họa **profile do nhà cung cấp quyết định**; không phải cấu trúc thay thế mặc định của claim `scope` trong RFC 9068. Resource Server phải biết mình đang chấp nhận định dạng nào. Không nên tự động coi mọi claim tên gần giống `scope`, `scp`, `roles` hay `permissions` đều tương đương.

### Thiếu scope claim thì sao?

Không phải mọi access token đều bắt buộc có cùng cấu trúc claims. Với API mà endpoint yêu cầu scope cụ thể, **không có thông tin phạm vi quyền tin cậy tương ứng thì không đủ điều kiện cho phép**. API có thể nhận quyền từ kết quả introspection, token profile hoặc nguồn policy đáng tin cậy khác; không được tự mặc định `admin` hay `read-all` khi claim vắng mặt.

Trong authorization/token request, nếu client không đưa `scope`, AS có thể áp dụng phạm vi mặc định hoặc từ chối theo chính sách OAuth. Điều đó khác với việc Resource Server tự đoán quyền cho token không có scope.

## 4. Scope khác claim, role, permission và audience

**Claim** là thuộc tính được biểu diễn trong token hoặc kết quả xác minh, ví dụ `iss`, `sub`, `aud`, `exp`, `scope`. **Scope là một claim có ngữ nghĩa quyền cụ thể** khi token profile quy định như vậy.

| Thành phần | Trả lời câu hỏi nào? | Ví dụ | Không được nhầm với |
|---|---|---|---|
| `scope` | Token được cấp **những phạm vi thao tác** nào? | `orders:read` | Quyền sở hữu mọi đơn hàng |
| `iss` | Ai phát hành token? | `https://auth.example.test` | Khẳng định issuer đáng tin nếu chưa xác minh |
| `aud` | Token dành cho **API/người nhận** nào? | `https://orders-api.example.test` | Client ID hoặc tên scope |
| `sub` | Subject theo hợp đồng issuer/profile là ai? | `user-42` | Bằng chứng đủ để sửa dữ liệu của người khác |
| `client_id` / `azp` | Ứng dụng được cấp hoặc bên được ủy quyền, tùy profile | `orders-web` | Danh tính user |
| `roles` / `permissions` | Thông tin vai trò/quyền riêng theo hệ thống | `manager`, `order:approve` | Scope OAuth chuẩn chung |
| **ACL/ABAC/ReBAC** | Subject/client được làm gì với **object cụ thể**? | User 42 sở hữu order 123 | Quyền tự suy ra chỉ từ scope |
| **Consent/grant** | Chủ thể có thẩm quyền đã chấp thuận gì cho client? | Đồng ý `orders:read` | Chữ ký hoặc trạng thái hiệu lực của token |

**Audience khác scope:** access token dành cho Billing API không nên được Orders API chấp nhận chỉ vì cũng có chuỗi `orders:read`. API phải kiểm tra `aud` trước khi dùng scope claim.

**Role khác scope:** một user có vai trò `ADMIN` trong tổ chức có thể vẫn sử dụng access token chỉ được cấp `orders:read`. Nếu endpoint yêu cầu `orders:write`, **quyền nền của user không tự mở rộng token**. Chiều ngược lại cũng đúng: scope `orders:read` không thể vượt qua một quy tắc tenant hoặc ACL cấm user xem đơn hàng đó.

## 5. Scope trong luồng OAuth 2.0 Authorization Code + PKCE

Giả sử client `orders-web` xin đọc và xuất đơn hàng. AS hỗ trợ Authorization Code + PKCE; OIDC có thể được dùng nếu ứng dụng còn cần đăng nhập user.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant C as Client
    participant AS as Authorization Server
    participant API as Orders API

    C->>AS: /authorize?scope=orders:read orders:export + state + PKCE
    AS->>U: Xác thực / xin consent nếu cần
    AS->>AS: Kiểm tra grant và phạm vi được phép
    AS-->>C: Callback authorization code + state
    C->>C: Kiểm tra state
    C->>AS: /token: code + code_verifier
    AS->>AS: Xác minh code, PKCE, client và policy
    AS-->>C: Access token với scope được cấp
    C->>API: GET /orders/123 + Bearer token
    API->>API: Xác minh token + scope + quyền dữ liệu
    API-->>C: Dữ liệu được phép
~~~

### 5.1. Client gửi phạm vi muốn xin

Ví dụ authorization request đã giản lược:

~~~http
GET /authorize?response_type=code&client_id=orders-web&redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback&scope=orders%3Aread%20orders%3Aexport&state=<STATE>&code_challenge=<S256_CHALLENGE>&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
~~~

`scope=orders%3Aread%20orders%3Aexport` khi URL decode là `orders:read orders:export`. Dấu `%20` ở đây thuộc **URL percent-encoding**, không phải bản thân scope có ký tự phần trăm trong tên.

Phạm vi client yêu cầu là đầu vào để AS xét duyệt. AS vẫn phải xác minh client, callback đã đăng ký, code challenge, trạng thái user, grant, consent và chính sách của resource. **Không có cơ chế nào cho phép client tự cấp scope bằng cách thêm chữ vào URL.**

### 5.2. AS quyết định cấp ít hơn phạm vi đã xin

Giả sử user chỉ đồng ý đọc đơn hàng, chưa đồng ý xuất dữ liệu. AS có thể giới hạn grant còn `orders:read`. Sau khi client đổi authorization code hợp lệ tại token endpoint, response minh họa:

~~~json
{
  "access_token": "<ACCESS_TOKEN>",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders:read"
}
~~~

Trong OAuth 2.0, **khi scope được cấp khác scope đã yêu cầu**, AS phải trả tham số `scope` trong token response để cho client biết phạm vi thực tế. Khi scope không thay đổi, token response có thể không lặp lại `scope` theo quy tắc giao thức; client vẫn phải dựa trên hợp đồng và bằng chứng cấp quyền tin cậy, không suy diễn từ payload chưa xác minh.

Client không được thực thi chức năng xuất dữ liệu chỉ vì trước đó từng xin `orders:export`. Nếu cần quyền bổ sung, client phải thực hiện quy trình xin cấp quyền thích hợp theo AS.

### 5.3. API đối chiếu scope thực tế

Client gọi:

~~~http
GET /orders/123 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer <ACCESS_TOKEN>
~~~

API phải xác minh token trước, sau đó kiểm tra `orders:read` và kiểm tra chủ sở hữu đơn hàng `123`. Khi client gọi `POST /orders/export`, nếu endpoint yêu cầu `orders:export` thì token chỉ có `orders:read` phải bị từ chối.

**Phạm vi được cấp trong token có thể được đọc sau khi xác minh JWT hoặc lấy từ introspection.** API không dùng giá trị `scope` do client gửi trong query/body của chính request nghiệp vụ làm nguồn phân quyền.

## 6. Scope claim trong JWT access token

Một JWT access token đã được **ký** (JWS) có thể chứa payload như sau:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": "https://orders-api.example.test",
  "client_id": "orders-web",
  "scope": "orders:read orders:export",
  "iat": 1800000000,
  "nbf": 1800000000,
  "exp": 1800000600,
  "jti": "at-1001"
}
~~~

Đây là **payload minh họa**, không phải JWT hoàn chỉnh có chữ ký hợp lệ. Các timestamp là Unix seconds để minh họa. Token thật còn phải có protected header, chữ ký và các thuộc tính đúng profile.

- `scope` là phạm vi được cấp cho **token này**, không phải toàn bộ quyền nền của `user-42`.
- `aud` giới hạn token dành cho Orders API. Một API khác phải từ chối token nếu không thuộc audience thích hợp.
- `client_id` cho biết client theo profile; `sub` cho biết subject theo ngữ cảnh issuer. Hai claim phục vụ vai trò khác nhau.
- `exp` và `nbf` giới hạn thời gian hợp lệ; scope không cho phép API bỏ qua thời gian hết hạn.
- `jti` nếu có là định danh JWT, có thể giúp theo dõi/chặn token; bản thân nó không chứng minh token chưa bị thu hồi.

Một chuỗi JWS thông thường có ba phần `header.payload.signature`. **Base64url decode phần payload chỉ giúp đọc JSON, không xác minh chữ ký.** Đổi `scope` thành `orders:admin` rồi encode lại làm chữ ký cũ không hợp lệ. Resource Server phải xác minh chữ ký với khóa, issuer và thuật toán đã được cấu hình tin cậy.

### Quy trình Resource Server phải thực hiện

1. Nhận access token từ kênh được hỗ trợ (thường là header `Authorization: Bearer` trên HTTPS).
2. Kiểm tra cấu trúc/loại token, giới hạn độ dài/kích thước và thuật toán được phép; không tin các claim đã decode.
3. Xác minh chữ ký bằng khóa đáng tin cậy cho issuer; không tải JWKS từ URL tùy ý trong header token.
4. Kiểm tra chính xác `iss`, `aud`, `exp`, `nbf` nếu có và các claim bắt buộc theo token profile. Có thể dùng độ lệch đồng hồ nhỏ được cấu hình.
5. Xác định **scope claim đã được xác minh** theo đúng profile, ví dụ `scope` dạng string trong RFC 9068.
6. Kiểm tra tập scope của token có chứa **chính xác** scope endpoint yêu cầu; không tự mở rộng hoặc thay đổi chữ hoa/chữ thường.
7. Kiểm tra subject/client/tenant và quyền trên **bản ghi** hoặc thao tác thực tế.
8. Áp dụng thêm trạng thái thu hồi, ràng buộc khóa hoặc policy khác nếu hệ thống yêu cầu.

**Chỉ kiểm tra scope mà bỏ `aud` là lỗi token confusion.** **Chỉ kiểm tra scope mà bỏ object-level authorization là lỗi phân quyền kiểu BOLA/IDOR.** Cả hai có thể dẫn tới truy cập trái phép dù token mang chữ ký hợp lệ.

## 7. Scope trong opaque token và introspection

**Opaque access token** không cho Resource Server tự biết claims từ chuỗi token. API thường dùng **token introspection** hoặc tra trạng thái tương ứng do AS tin cậy cung cấp.

Yêu cầu introspection minh họa:

~~~http
POST /introspect HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <AUTHENTICATED_RESOURCE_SERVER_CREDENTIALS>

token=<OPAQUE_ACCESS_TOKEN>&token_type_hint=access_token
~~~

Phản hồi ví dụ khi token hoạt động:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "client_id": "orders-web",
  "aud": "https://orders-api.example.test",
  "scope": "orders:read",
  "exp": 1800000600
}
~~~

`scope` trong introspection response là dữ liệu đáng tin **khi** response đến từ AS đúng, qua kết nối và cơ chế xác thực được bảo vệ. API vẫn phải kiểm tra `active: true`, audience, scope và chính sách tài nguyên. Đối với `active: false`, API phải từ chối; không dùng bất kỳ claim khác để “cứu” token không hoạt động.

**Cần để ý cache:** cache introspection quá lâu có thể khiến API tiếp tục coi scope/trạng thái cũ là hợp lệ sau khi grant hoặc token bị thu hồi. Cache TTL cần được giới hạn theo `exp` và yêu cầu thu hồi. Không giả định introspection luôn trả đủ mọi claim của JWT; trường được trả phụ thuộc AS, quyền client introspection và hợp đồng.

## 8. Dùng scope trong Java: so khớp chính xác

Với `scope` dạng chuỗi cách nhau bằng dấu cách, Resource Server nên chuyển thành **tập scope đã được xác minh** và so khớp chính xác, thay vì tìm chuỗi con.

Ví dụ Java 11+ dưới đây chỉ xử lý **scope claim đã đến từ thành phần xác minh token đáng tin**. Nó **không** xác minh JWT/opaque token và không được dùng trực tiếp trên payload tự decode.

~~~java
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;

public final class ScopePolicy {
    private ScopePolicy() {}

    // Chỉ gọi sau khi JWT verifier/introspection đã xác minh token.
    public static Set<String> parseVerifiedScope(String scopeClaim) {
        if (scopeClaim == null || scopeClaim.isBlank()) {
            return Collections.emptySet();
        }

        Set<String> scopes = new HashSet<>();

        // OAuth scope là các token phân tách bằng dấu cách ASCII.
        for (String item : scopeClaim.split(" ")) {
            if (!item.isEmpty()) {
                scopes.add(item);
            }
        }

        return Collections.unmodifiableSet(scopes);
    }

    public static boolean hasAllRequired(
            Set<String> verifiedScopes,
            Set<String> requiredScopes
    ) {
        return verifiedScopes.containsAll(requiredScopes);
    }
}
~~~

Cách sử dụng:

~~~java
Set<String> granted = ScopePolicy.parseVerifiedScope(
        "orders:read orders:export"
);

boolean mayRead = ScopePolicy.hasAllRequired(
        granted, Set.of("orders:read")
); // true

boolean mayDelete = ScopePolicy.hasAllRequired(
        granted, Set.of("orders:delete")
); // false
~~~

Hàm trên chỉ minh họa logic **exact set membership**. Trong hệ thống thật, thư viện hoặc lớp tích hợp còn phải kiểm tra kiểu claim là string theo token profile, định dạng scope được phép, issuer, audience, chữ ký/thời hạn/trạng thái và ánh xạ sang authority phù hợp. Không chấp nhận giá trị `scope` từ HTTP request do client tự nhập.

### Hai lỗi so khớp rất nguy hiểm

**Lỗi 1 — Dùng `contains` trên chuỗi chưa tách:**

~~~java
String scope = "orders:read-all";

// SAI: có thể trả true dù không có scope chính xác "orders:read".
boolean allowed = scope.contains("orders:read");
~~~

**Lỗi 2 — Biến scope thành hệ phân cấp tự đặt:**

~~~text
Token có:           orders:write
Endpoint yêu cầu:   orders:read
Giả định sai:       write luôn bao gồm read
Kết luận đúng:      chỉ được coi tương đương nếu hợp đồng
                    API định nghĩa và policy kiểm tra rõ ràng.
~~~

**Quy tắc:** so khớp giá trị chính xác theo hợp đồng. Nếu API có quyền tổng hợp như `orders:*` hoặc cấp admin bao gồm nhiều thao tác, hãy định nghĩa **chính sách ánh xạ riêng, có kiểm soát**; đừng tự triển khai wildcard theo tiền tố hoặc dựa vào tên scope để suy ra quyền.

### Điều kiện cần cho một endpoint

~~~text
GET /orders/123:
    valid token (issuer, audience, time, signature/status)
    AND exact scope "orders:read"
    AND tenant constraint
    AND user/client mayRead(order 123)

POST /orders/export:
    valid token
    AND exact scope "orders:export"
    AND policy permits exporting this data set
~~~

Một endpoint có thể yêu cầu **tất cả** các scope hoặc **một trong** nhiều scope; phép AND/OR phải được xác định rõ bằng policy. Không tự gán `containsAny` khi nghiệp vụ yêu cầu tất cả.

## 9. HTTP 401, 403 và `insufficient_scope`

OAuth 2.0 Bearer Token Usage quy định cách Resource Server thông báo một số lỗi token. Phân biệt hai nhóm:

| Tình huống | Phản hồi thường phù hợp | Ý nghĩa |
|---|---|---|
| Không có token hoặc token bị sai chữ ký/hết hạn/sai audience | `401 Unauthorized`; có thể kèm `WWW-Authenticate: Bearer` và lỗi phù hợp | API chưa có credential hợp lệ |
| Token hợp lệ nhưng thiếu scope endpoint bắt buộc | `403 Forbidden`, thường kèm `WWW-Authenticate: Bearer error="insufficient_scope"` khi áp dụng | Credential hợp lệ nhưng không đủ quyền thao tác |
| Token có scope nhưng subject không có quyền trên object | `403` hoặc `404` theo chính sách tránh lộ tài nguyên | Đây là lỗi quyền tài nguyên, không nên tự refresh |
| Introspection báo `active: false` | Xử lý như token không hợp lệ | Không dùng claims đã hết hiệu lực |

Ví dụ challenge cho thiếu scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders:export"
~~~

Thông tin `scope` trong challenge mô tả phạm vi cần thiết nếu API chọn công bố; không được tiết lộ chi tiết nhạy cảm quá mức về quyền hoặc tài nguyên. Client phải xử lý quyền thiếu bằng quy trình ủy quyền phù hợp, **không refresh vô hạn** với grant vẫn chỉ có `orders:read`.

Các ứng dụng có thể dùng response body riêng để hướng dẫn người dùng, nhưng không nên trả token, secret, hoặc thông tin nội bộ trong lỗi.

## 10. Scope trong OIDC: `openid`, `profile` và `offline_access`

OpenID Connect dùng tham số `scope` trong authorization request để yêu cầu **dịch vụ xác thực và nhóm thông tin**. Nó không có cùng ngữ nghĩa với mọi scope nghiệp vụ của API.

| Scope | Ý nghĩa thường gặp | Điều không nên suy ra |
|---|---|---|
| `openid` | Yêu cầu OpenID Connect và ID token theo luồng phù hợp | Token cấp quyền gọi mọi API |
| `profile` | Yêu cầu nhóm claims hồ sơ tiêu chuẩn qua cơ chế OIDC tương ứng | Quyền sửa hồ sơ người dùng |
| `email` | Yêu cầu thông tin liên quan email theo OIDC | Email luôn được xác minh hoặc được API tùy ý dùng làm khóa phân quyền |
| `offline_access` | Yêu cầu khả năng cấp refresh token theo OIDC/policy | Luôn được cấp refresh token hoặc phiên truy cập vĩnh viễn |
| `orders:read` | Scope nghiệp vụ do Orders API/AS định nghĩa | Scope chuẩn có sẵn trong OIDC |

Ví dụ request kết hợp đăng nhập và quyền API:

~~~text
scope=openid profile orders:read
~~~

Client có thể nhận **ID token** để xác minh sự kiện xác thực user và **access token** để gọi Orders API, nhưng mỗi token có mục đích, audience và quy tắc xác minh riêng.

**Không đưa ID token trực tiếp cho Orders API để thay access token.** ID token thường có `aud` là **client ID**, không phải Orders API. Các scope OIDC trong authorization request cũng không tự động biến ID token thành token phân quyền API.

## 11. Scope trong client credentials và quyền được ủy quyền

Không phải access token nào cũng đại diện user đang thao tác.

| Tình huống | Chủ thể/quyền nền | Ví dụ scope | API cần lưu ý |
|---|---|---|---|
| **Authorization Code theo user** | Grant gắn với user và client | `orders:read` | Kiểm tra quyền user/client với đơn hàng |
| **Client Credentials** | Quyền của chính service/client | `inventory:sync` | Không bịa user chỉ từ token; phân quyền dựa trên service/tenant |
| **Token exchange/on-behalf-of** theo AS hỗ trợ | Quyền được chuyển tiếp/ràng buộc theo policy | `reports:generate` | Kiểm tra actor/subject/audience mới; không tự tăng quyền |
| **Refresh token grant** | Grant đã cấp và policy hiện tại | Scope không được vượt grant đã có | Không refresh để “tự xin thêm” quyền chưa được phê duyệt |

Ví dụ service `warehouse-job` dùng client credentials lấy token chỉ có `inventory:sync`. Một API đòi `orders:read` phải từ chối dù token có chữ ký hợp lệ từ cùng issuer.

Khi một API gọi API khác, **không chuyển nguyên access token sang service có audience khác**. Nếu cần quyền theo user cho downstream API, dùng cơ chế phát hành token mới theo resource hoặc token exchange được AS và hệ thống hỗ trợ, luôn giới hạn scope và subject/actor.

## 12. Thiết kế scope theo nguyên tắc least privilege

Scope tốt giúp AS cấp quyền chính xác và API dễ kiểm tra. Một số nguyên tắc thiết kế:

1. **Đặt tên theo tài nguyên và hành động** khi thích hợp: `orders:read`, `orders:create`, `orders:cancel`. Định nghĩa rõ mỗi quyền tác động đến gì.
2. **Tránh scope quá rộng** như `all` hay `admin` nếu client chỉ cần đọc đơn hàng. Scope cực rộng làm hậu quả lộ token lớn hơn.
3. **Chia quyền đọc và ghi**; tách thao tác nhạy cảm như xuất dữ liệu hàng loạt, thanh toán, xóa dữ liệu hoặc quản trị.
4. **Xin quyền khi cần** (incremental authorization) nếu hệ thống hỗ trợ; không đòi quyền ngay khi đăng nhập chỉ vì có thể cần trong tương lai.
5. **Phân biệt scope với quyền object:** `orders:read` là loại thao tác; quyền xem đơn hàng của tenant khác cần policy/ACL riêng.
6. **Định nghĩa scope theo audience/resource:** tránh để cùng một scope dễ bị hiểu theo hai nghĩa tại hai API.
7. **Có quy trình quản lý thay đổi:** không đổi ngữ nghĩa scope đang dùng một cách âm thầm; khi cần có thể version scope/API hoặc hỗ trợ chuyển đổi an toàn.
8. **Xác định quyền được tổng hợp rõ ràng:** nếu `orders:manage` bao gồm các thao tác khác, thể hiện trong policy thay vì chỉ dựa vào chuỗi.
9. **Có cơ chế thu hồi và giám sát:** token/grant bị lộ hoặc client bị đình chỉ cần được xử lý đúng thời gian chấp nhận được.

Scope không mô tả tốt mọi tình huống “chỉ được đọc tài liệu X, với số tiền Y, trước giờ Z”. Có thể dùng ràng buộc tài nguyên, policy và cơ chế **Rich Authorization Requests (RAR)** nếu AS hỗ trợ để mô tả quyền chi tiết hơn. Tuy nhiên, việc cấp và kiểm tra cuối cùng vẫn phải diễn ra tại thành phần đáng tin cậy.

## 13. Vòng đời scope khi token hết hạn, làm mới hoặc bị thu hồi

~~~mermaid
stateDiagram-v2
    [*] --> Requested: Client xin scope
    Requested --> Denied: AS / user / admin không cho phép
    Requested --> Granted: Scope được chấp thuận
    Granted --> Active: AS cấp access token
    Active --> Expired: Token đạt exp
    Active --> Revoked: Bị chặn/thu hồi
    Expired --> Active: Cấp token mới nếu grant vẫn hợp lệ
    Granted --> Revoked: Grant bị thu hồi
    Denied --> [*]
    Revoked --> [*]
~~~

Sơ đồ minh họa quá trình; **grant, access token và refresh token có vòng đời riêng**. Sau khi token hết hạn, scope trước đây vẫn có thể thuộc một grant còn hiệu lực, nên AS có thể cấp token mới theo chính sách. Ngược lại, user bị gỡ quyền hoặc thu hồi grant có thể khiến AS không tiếp tục cấp token, dù một JWT đã phát hành còn tồn tại vật lý trên thiết bị client.

Ba lưu ý thực tế:

- **Refresh không tự mở rộng scope:** refresh token không cho phép client tự nâng từ `orders:read` lên `orders:write`; việc cấp quyền mới cần grant/policy phù hợp.
- **Scope trong JWT đã ký thường không thay đổi tại chỗ:** thay đổi quyền user hoặc admin không tự sửa claims trong token đã phát hành. Nếu cần cập nhật ngay, API phải kết hợp kiểm tra trạng thái/quyền nguồn hoặc biện pháp thu hồi.
- **Cache ảnh hưởng thu hồi:** nếu API cache kết quả introspection, scope/trạng thái cũ có thể còn được dùng trong giới hạn TTL. Chọn TTL theo `exp` và mức độ cần thu hồi sớm.

Một access token có scope hợp lệ bị đánh cắp vẫn có thể được phát lại nếu là **bearer token**. Chữ ký ngăn sửa claim nhưng không ngăn kẻ giữ nguyên token gửi lại. Cần HTTPS, không log token, lưu trữ an toàn, TTL phù hợp, phát hiện bất thường và có thể **DPoP/mTLS** nếu hệ thống hỗ trợ sender-constrained token.

## 14. Các lỗ hổng thường gặp liên quan scope claim

| Anti-pattern | Ví dụ | Hậu quả và cách khắc phục |
|---|---|---|
| **Tin scope chưa xác minh** | Base64url decode JWT rồi đọc `scope` | Kẻ tấn công tự bịa scope. Phải xác minh token trước |
| **Substring matching** | `scope.contains("read")` | `orders:read-all`/`files:read` có thể bị hiểu sai; tách tập và so khớp chính xác |
| **Tự kế thừa tên scope** | `write` mặc nhiên đồng nghĩa `read` | Quyền vượt hợp đồng; phải có policy rõ |
| **Tin scope request ban đầu** | Client xin `orders:export`, chỉ được cấp `orders:read` | Gọi API vượt quyền; dùng granted scope |
| **Bỏ audience** | Token Billing API có `orders:read` được Orders API chấp nhận | Token confusion; kiểm tra `aud` |
| **Dùng ID token như access token** | API đọc `sub`/`scope` của ID token | Sai mục đích token; xác minh loại và audience |
| **Bỏ quyền object/tenant** | GET `/orders/999` chỉ kiểm tra `orders:read` | BOLA/IDOR; kiểm tra ACL, tenant và sở hữu |
| **Tự map mọi claim thành quyền** | `roles=ADMIN` hoặc `scp` được đọc không theo profile | Nâng quyền ngoài hợp đồng; chỉ nhận nguồn/kiểu đáng tin cậy |
| **Scope quá rộng** | `all:write` cấp cho app chỉ cần đọc | Token lộ gây thiệt hại lớn; least privilege |
| **Không xét thu hồi** | JWT còn `exp` dù user đã mất quyền | Quyền cũ còn dùng được; trạng thái/denylist/thời hạn ngắn theo policy |
| **Chia sẻ token sai API** | API A gửi token có `aud=A` sang API B | Lộ token hoặc dùng sai audience; cấp token cho API B theo chính sách |

## 15. Case study: quyền đọc, xuất và hủy đơn hàng

Hệ thống có ba endpoint:

| Endpoint | Scope tối thiểu | Kiểm tra dữ liệu bổ sung |
|---|---|---|
| `GET /orders/{id}` | `orders:read` | Subject được xem đơn hàng thuộc đúng tenant |
| `POST /orders/export` | `orders:export` | Chủ thể được xuất những bản ghi trong phạm vi được phép |
| `POST /orders/{id}/cancel` | `orders:cancel` | Trạng thái đơn cho phép hủy và chủ thể có quyền hủy |

AS cấp token cho `orders-web`:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": "https://orders-api.example.test",
  "scope": "orders:read orders:export",
  "exp": 1800000600
}
~~~

Giả sử token được **xác minh thành công**, còn hạn và hệ thống xác định `user-42` thuộc tenant `t-1`, chỉ được xem đơn `123` trong tenant này.

| Request | Kết quả | Giải thích |
|---|---|---|
| `GET /orders/123` | Có thể cho phép | Có `orders:read`, audience đúng, quyền trên object đúng |
| `POST /orders/export` của đơn thuộc tenant `t-1` | Có thể cho phép | Có `orders:export`, cần lọc dữ liệu theo quyền user |
| `POST /orders/123/cancel` | Từ chối | Token thiếu `orders:cancel` |
| `GET /orders/999` thuộc tenant khác | Từ chối | Scope đọc đủ nhưng policy tenant không cho phép |
| Gửi token trên tới `billing-api.example.test` | Từ chối | Audience của token dành cho Orders API |
| Gửi ID token OIDC thay token trên | Từ chối | ID token không phải access token dành cho API |
| Dùng token sau `exp` | Từ chối | Scope không gia hạn hiệu lực token |

Các kết quả “có thể cho phép” nhấn mạnh scope chỉ là một điều kiện. API vẫn phải kiểm tra mọi điều kiện khác theo nghiệp vụ. Nếu server trả `403` hoặc `404` cho object không thuộc quyền user, phải tuân theo chính sách hạn chế lộ thông tin tài nguyên.

### Tự kiểm tra nhanh

**Câu 1.** Client yêu cầu `orders:read orders:delete`, AS chỉ cấp `orders:read`. Client có được xóa không? **Không.** Quyền xin không phải quyền được cấp.

**Câu 2.** Scope claim là `orders:read-all`. API yêu cầu chính xác `orders:read` và chỉ có kiểm tra chuỗi con. Có đúng không? **Không.** Cần so khớp từng scope token chính xác.

**Câu 3.** Token có scope `orders:read` nhưng `aud` là Billing API. Orders API nhận không? **Không.** Token sai audience.

**Câu 4.** Token đúng issuer, audience, chữ ký và scope đọc; đơn hàng thuộc user khác. Trả dữ liệu không? **Không.** Phải kiểm tra quyền trên tài nguyên.

**Câu 5.** JWT đã cấp có scope `orders:export`, quyền export của user vừa bị thu hồi. API tự xác minh JWT có thấy ngay không? **Không mặc định.** Cần cơ chế kiểm tra trạng thái/policy hoặc chờ token hết hạn theo thiết kế.

**Câu 6.** Scope `openid` chứng minh user được gọi mọi API? **Không.** Đây là scope OIDC; API cần access token có audience và scope nghiệp vụ phù hợp.

## 16. Checklist triển khai scope claim

1. **Thiết kế tên và ngữ nghĩa:** mỗi scope có quyền cụ thể, rõ thao tác, tài nguyên và API áp dụng.
2. **Chỉ cấp quyền được chấp thuận:** AS xét client, user/admin, grant, consent, audience và chính sách trước khi phát hành.
3. **Dùng granted scope:** không lấy scope đã xin trong request làm bằng chứng được phép.
4. **Nhận đúng token:** access token dành cho API; không dùng ID token để phân quyền API hoặc refresh token để gọi Resource Server.
5. **Xác minh trước khi đọc quyền:** issuer, audience, loại token/profile, signature hoặc introspection, thời hạn và trạng thái khi cần.
6. **Chuẩn hóa đúng hợp đồng:** `scope` dạng string phân tách dấu cách trong profile chuẩn; `scp`/`roles` chỉ khi provider định nghĩa rõ.
7. **So khớp chính xác:** so theo tập scope, có phân biệt chữ hoa/chữ thường; không dùng substring hoặc wildcard tự đặt.
8. **Kiểm tra quyền dữ liệu:** scope không thay thế ACL, tenant, subject/client policy hay kiểm tra quyền trên object.
9. **Xử lý lỗi phù hợp:** token không hợp lệ thường `401`; token hợp lệ nhưng thiếu scope thường `403`/`insufficient_scope`.
10. **Bảo vệ vòng đời:** token ngắn hạn, refresh theo grant, rotation/thu hồi đúng chính sách, bảo vệ bearer token và hạn chế cache trạng thái.
11. **Kiểm tra gọi downstream:** mỗi API chỉ nhận token đúng audience và scope của mình.
12. **Rà soát quyền định kỳ:** tránh scope quá rộng và cập nhật policy khi quyền tổ chức thay đổi.

**Điều cần ghi nhớ:** `scope` là một claim hoặc thuộc tính mô tả **phạm vi quyền đã được cấp cho token**, không phải lời hứa rằng client hay user được phép làm mọi điều có tên gần giống scope. Một quyết định phân quyền an toàn cần **token đã xác minh + audience đúng + scope phù hợp + chính sách user/client/tenant trên tài nguyên cụ thể**.

### Tài liệu chuẩn để tham khảo

- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749), đặc biệt Section 3.3 (Access Token Scope) và các quy tắc token response.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer authorization, `insufficient_scope` và xử lý lỗi.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): thuộc tính `active`, `scope` và kiểm tra opaque token.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): cách biểu diễn scope claim trong JWT access token.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo mật OAuth hiện đại.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): ràng buộc tài nguyên/audience.
- [RFC 9396 — OAuth 2.0 Rich Authorization Requests](https://www.rfc-editor.org/rfc/rfc9396): mô tả quyền có cấu trúc khi scope đơn giản chưa đủ.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): scope `openid`, `profile`, `email`, `offline_access` và phân biệt ID token với access token.
