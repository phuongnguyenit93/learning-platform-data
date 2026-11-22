# Xử lý phản hồi thiếu trường, sai kiểu hoặc trạng thái không hợp lệ

Trong **Spring Security OAuth 2.0 / OIDC Resource Server**, khi API nhận access token theo cơ chế *opaque token*, ứng dụng thường gọi **OAuth 2.0 Token Introspection** tại Authorization Server (AS) để biết token còn hoạt động không và nhận những thuộc tính được phép sử dụng cho authentication/authorization. Giao thức này được mô tả trong **RFC 7662**.

Một JSON response “nhìn có vẻ đúng” chưa đủ an toàn. Trên thực tế có thể gặp những tình huống:

- Endpoint trả HTTP `200 OK` nhưng **không có trường `active`**.
- `active` có giá trị `"true"` (string), `1` (number), `null` hoặc `[]` thay vì JSON boolean.
- `active=true` nhưng metadata bắt buộc **theo hợp đồng API** bị thiếu, ví dụ `aud`, `sub` hoặc `iss`.
- `scope` được gửi dưới dạng array hoặc object dù profile của issuer quy định chuỗi.
- `exp`, `iat` hoặc `nbf` là string thay vì NumericDate; hoặc `exp` đã ở quá khứ nhưng response vẫn bảo active.
- AS trả `active=false` cùng nhiều metadata nhạy cảm.
- Phản hồi là HTML/JSON lỗi, JSON bị cắt, có key lặp, hoặc HTTP `401`/`503` chứ không phải kết quả introspection hợp lệ.
- Sau khi nâng cấp AS, kiểu dữ liệu của `aud` hoặc `scp` thay đổi mà client Resource Server không cập nhật.

Nếu code xử lý theo kiểu “thấy key thì cast; thiếu thì tự cấp giá trị mặc định; parse lỗi thì coi là active”, hệ thống có thể gặp **ClassCastException/500**, cấp nhầm quyền, hoặc bỏ qua một yêu cầu bắt buộc khi xác thực token.

Bài học hướng tới cách **xử lý response một cách có hợp đồng, không nâng quyền ngoài ý muốn và fail closed**. Chúng ta sẽ phân biệt *ràng buộc tối thiểu của RFC 7662* với *ràng buộc chặt hơn của orders-api*, xem hoạt động của `OpaqueTokenIntrospector`, xây dựng lớp kiểm tra metadata, và thiết kế kiểm thử cho lỗi cấu trúc, kiểu dữ liệu, trạng thái token và lỗi upstream.

> **Quan trọng:** Ngoài `active`, phần lớn metadata trong RFC 7662 là **tùy chọn**. Một Resource Server được phép yêu cầu thêm trường dựa trên hợp đồng tích hợp **của riêng mình**, nhưng không nên gọi một response thiếu `sub`/`aud`/`exp` là “vi phạm RFC 7662” một cách chung chung. Nó có thể hợp chuẩn giao thức nhưng **không đủ điều kiện** để API này chấp nhận.

Ví dụ xuyên suốt:

- **Issuer tin cậy**: `https://auth.example.test/realms/orders`.
- **Introspection endpoint**: `https://auth.example.test/oauth2/introspect`.
- **Resource Server**: `orders-api`.
- **Introspection client**: `orders-api-introspector`.
- **OAuth client xin token**: `web-portal`.
- **Scope**: `orders:read`, `orders:write`.
- **Subject**: `alice-123`, tenant `tenant-a`.

Các tên miền, token, ID và credential bên dưới chỉ là ví dụ minh họa.

---

## 1. Ranh giới tin cậy: một response introspection được dùng để làm gì?

Một request thông thường:

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer opaque-access-token-example
```

Resource Server gửi token cho AS:

```http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <encoded-introspection-client-credentials>

token=opaque-access-token-example&token_type_hint=access_token
```

Sau khi xác thực introspection client và xác định trạng thái token, AS có thể trả:

```json
{
  "active": true,
  "scope": "orders:read orders:write",
  "client_id": "web-portal",
  "sub": "alice-123",
  "iss": "https://auth.example.test/realms/orders",
  "aud": ["orders-api"],
  "exp": 1890003600
}
```

Resource Server dùng response này để xác định:

1. **Authentication:** token có được AS xác nhận đang hoạt động không?
2. **Token contract:** dữ liệu nào có kiểu và ý nghĩa phù hợp cho API hiện tại? Token có thuộc issuer/resource được phép không?
3. **Authority mapping:** scopes/roles nào được phép ánh xạ thành quyền Spring Security?
4. **Business authorization:** principal có quyền đọc đơn `42` của đúng user/tenant không?

```mermaid
flowchart TD
    A["Bearer token trong HTTP request"] --> B["OpaqueTokenIntrospector"]
    B --> C["HTTPS POST đến introspection endpoint tin cậy"]
    C --> D{"Transport & response hợp lệ?"}
    D -->|Không| E["Từ chối, ghi nhận lỗi tích hợp"]
    D -->|Có| F{"active là boolean?"}
    F -->|Không| E
    F -->|false| G["Token inactive → authentication thất bại"]
    F -->|true| H["Validate schema + hợp đồng issuer/resource"]
    H --> I{"Metadata phù hợp?"}
    I -->|Không| E
    I -->|Có| J["Tạo principal và authorities có kiểm soát"]
    J --> K["Kiểm tra scope / role của route"]
    K --> L["Kiểm tra owner / tenant / nghiệp vụ"]
    L --> M["Cho phép hoặc từ chối"]
```

**Không có nhánh “parse response lỗi thì tự cho qua”.** Khi không thể xác định token đáng tin, request không được thực thi nghiệp vụ bảo vệ.

### 1.1. HTTP 200 không phải là “token hợp lệ”

Cần phân biệt **introspection request đã được HTTP server xử lý** và **access token thực sự active**:

| Introspection HTTP response | Ý nghĩa | Hành vi API |
|---|---|---|
| `200` + `{"active":true}` | Request xử lý thành công; AS báo token active. | Tiếp tục kiểm tra metadata, scope và object policy. |
| `200` + `{"active":false}` | Request xử lý thành công; token inactive/không được phép introspect. | Từ chối authentication. |
| `200` + `{}` | Thiếu trường bắt buộc. | Xem response không hợp lệ, không cấp quyền. |
| `200` + `{"active":"true"}` | `active` sai kiểu. | Xem response không hợp lệ, không ép chuỗi thành true. |
| `401` từ AS | Introspection client không xác thực đúng hoặc không được cho phép, tùy AS. | Xử lý lỗi tích hợp; không suy ra token inactive. |
| `403` từ AS | Introspection requester không có quyền endpoint/resource. | Xử lý lỗi ủy quyền với AS; fail closed. |
| `429`, `5xx`, timeout | AS/quota/network lỗi. | Không xác minh token; retry giới hạn hoặc xử lý sự cố. |
| `302` redirect bất thường | Có thể endpoint thay đổi hoặc cấu hình sai. | Không gửi credential sang host khác thiếu kiểm chứng. |

Trong trường hợp `active=false`, AS nên hạn chế các metadata bổ sung để không tiết lộ thông tin về token. Dù endpoint vô tình trả thêm metadata, Resource Server **không được tạo principal hoặc authority từ response inactive**.

### 1.2. Token không phải thứ duy nhất cần xác minh

Ngay cả khi `active=true`, API có thể phải chứng minh:

- Introspection endpoint thuộc **Authorization Server tin cậy**, kết nối TLS hợp lệ.
- Token được phát hành bởi issuer được chấp nhận, hoặc AS có cơ chế ràng buộc tương đương.
- Token dành cho **`orders-api`**, không phải `payments-api`.
- Token là **access token** phù hợp, không phải refresh token.
- Metadata mà policy cần có đúng schema.
- Token chưa hết hạn/không bị chặn theo chính sách.
- Scope, role và resource ownership đủ để thực hiện thao tác.

RFC 7662 không tự quyết định toàn bộ chính sách của API. Đó là lý do cần tách **protocol validation** khỏi **application token contract**.

---

## 2. Những gì RFC 7662 thực sự quy định

RFC 7662 yêu cầu response là **JSON object** có trường `active` là **boolean**. Các trường `scope`, `client_id`, `username`, `token_type`, `exp`, `iat`, `nbf`, `sub`, `aud`, `iss` và `jti` là metadata được định nghĩa nhưng **không bắt buộc có mặt trong mọi response**.

### 2.1. `active` là mốc rẽ nhánh đầu tiên

Hai response cơ bản:

```json
{"active": true}
```

```json
{"active": false}
```

Theo RFC, `active=false` thường phản ánh token đã hết hạn, bị thu hồi, không tồn tại, hoặc introspection requester không có quyền truy cập metadata token đó. AS có thể che giấu nguyên nhân cụ thể bằng cùng một kết quả.

**`active=true` không có nghĩa token có quyền gọi mọi API.** Trạng thái này chỉ là một phần điều kiện xác thực; route còn phải đòi đủ quyền.

Ví dụ **sai kiểu**:

```json
{"active": "true"}
```

```json
{"active": 1}
```

```json
{"active": null}
```

```json
{"active": []}
```

Không chuyển các trường hợp này sang `true` bằng `Boolean.parseBoolean(...)`, so sánh số `1` hoặc coi mọi giá trị “truthy” đều active. Một serializer/issuer sai schema có thể xuất hiện, nhưng **Resource Server không nên tự sửa giao thức bằng ép kiểu nguy hiểm**.

### 2.2. Active có thể hợp chuẩn dù thiếu các trường khác

```json
{
  "active": true
}
```

Theo **cấu trúc RFC 7662**, response này không nhất thiết là sai: `scope`, `aud`, `sub` và `exp` đều tùy chọn. Nhưng đối với `orders-api`, nếu chính sách đòi `aud` và `sub` để xác minh resource và subject, response đó **không đủ dữ liệu để cấp quyền**.

Có ít nhất hai mức đánh giá:

| Mức | Câu hỏi | Ví dụ |
|---|---|---|
| **RFC/schema cơ sở** | JSON object có `active` là boolean không? | `{"active":true}` đạt điều kiện cơ bản. |
| **Hợp đồng tích hợp của API** | Có đủ trường/kiểu để khẳng định đúng issuer/resource/subject và tạo authorities không? | Không có `aud` trong hệ không có resource binding khác → từ chối. |

Đừng gắn nhãn “RFC không hợp lệ” cho mọi lỗi policy. Logging/phân loại sự cố nên phân biệt **malformed protocol response** với **insufficient token metadata for this resource**.

### 2.3. Trường `scope` và `token_type`

Ví dụ:

```json
{
  "active": true,
  "scope": "orders:read orders:write",
  "token_type": "Bearer"
}
```

- `scope`, nếu có theo RFC 7662, là **chuỗi scope values phân cách bằng dấu cách**.
- `token_type` là chuỗi, có thể cho biết loại token như `Bearer`.
- Không tự thêm `orders:read` nếu `scope` vắng mặt.
- Không suy ra refresh token có thể dùng làm API Bearer access token chỉ vì `token_type_hint=access_token` trong request. Hint là dữ liệu gợi ý tìm kiếm, không phải bằng chứng loại token.
- Một số issuer dùng `scp`, `permissions` hoặc cấu trúc role riêng; đó là **hợp đồng bổ sung**, không có nghĩa `scope` được phép đổi kiểu ngẫu nhiên theo từng request.

---

## 3. Chính sách schema cho từng metadata

Bảng phân biệt **kiểu dữ liệu theo RFC** và **hành vi an toàn** khi thiếu/sai kiểu. Những quyết định như “bắt buộc aud” là ví dụ **profile của orders-api**, không phải quy tắc bắt buộc của RFC 7662.

| Trường | Kiểu / ý nghĩa | Nếu thiếu | Nếu sai kiểu |
|---|---|---|---|
| **`active`** | JSON boolean, **bắt buộc**. | Response giao thức không hợp lệ, fail closed. | Không ép kiểu; response không hợp lệ. |
| **`scope`** | Chuỗi scope token cách nhau bằng dấu cách. | Không tạo scope authority từ claim này; route cần scope sẽ từ chối. | Từ chối response theo profile chuẩn hoặc dùng mapper vendor-specific đã thỏa thuận, không tự cast. |
| **`client_id`** | String — OAuth client gắn với token. | Có thể chấp nhận nếu API không yêu cầu; nếu client allowlist bắt buộc, từ chối. | Từ chối/không sử dụng; không tạo client identity từ object/number. |
| **`username`** | String — tên user thân thiện. | Thường không ảnh hưởng authentication. | Không dùng làm chủ sở hữu/role; có thể từ chối theo contract. |
| **`token_type`** | String, ví dụ `Bearer`. | Quyết định theo profile; không tự xem mọi token đều là Bearer. | Từ chối nếu profile yêu cầu token type rõ. |
| **`exp`** | NumericDate (JSON number, giây từ epoch). | RFC cho phép thiếu; API có thể đòi để kiểm soát tuổi token/cache. | Không parse tùy tiện `"1890003600"` thành số nếu contract quy định number. |
| **`iat`** | NumericDate. | Thường tùy chọn. | Không sử dụng dữ liệu sai kiểu cho audit/thời gian. |
| **`nbf`** | NumericDate. | Thường tùy chọn. | Không coi chuỗi bất kỳ là mốc thời gian. |
| **`sub`** | String — subject token. | Nếu policy cần user/owner, phải từ chối hoặc tra nguồn tin cậy theo contract. | Không gọi `toString()` trên map/list để chế ra user ID. |
| **`aud`** | String hoặc mảng string. | Nếu AS không bảo đảm ràng buộc resource theo cách khác, từ chối. | Từ chối object/number/mảng chứa kiểu khác string. |
| **`iss`** | String — issuer. | Nếu policy cần xác minh issuer, từ chối hoặc dựa vào ràng buộc provider đã được bảo đảm rõ. | Không suy diễn issuer từ token chưa xác minh. |
| **`jti`** | String — token ID. | Thường không ảnh hưởng xác thực. | Không dùng cho cache/audit nếu sai schema. |
| **`roles` / `permissions`** | Vendor-defined. | Không tự cấp quyền. | Theo schema riêng; không chuyển mọi dữ liệu thành `ROLE_ADMIN`. |
| **`tenant_id`** | Vendor-defined. | Nếu tenant bắt buộc, từ chối/không cấp quyền trên dữ liệu tenant. | Không dùng object/list tự ép thành tenant. |

### 3.1. Một API cần chọn hợp đồng trước

Giả sử `orders-api` thống nhất với đội Identity:

- Endpoint chỉ phát metadata dùng được cho **access token** dành cho `orders-api`.
- `active` bắt buộc boolean (RFC 7662).
- Đối với token được chấp nhận, `iss`, `aud`, `sub` và `exp` là các trường **bắt buộc theo orders-api**.
- `iss` phải đúng `https://auth.example.test/realms/orders`.
- `aud` phải chứa `orders-api`.
- `exp` phải là NumericDate và nằm trong tương lai.
- `scope` nếu có là string theo RFC 7662, chuỗi rỗng nghĩa là không cấp scope.
- `client_id` nếu có phải là string; endpoint nhạy cảm có thể yêu cầu client allowlist.
- `tenant_id` nếu có phải là string; với route tenant-specific phải có tenant context hợp lệ.
- Các claim không biết trước **không được dùng tự động để cấp authority**.

Đây là một **hợp đồng nghiêm ngặt hơn giao thức cơ sở**. Nó giúp Resource Server phân biệt “AS đang nói token active” với “AS đã cung cấp đủ bằng chứng cho đúng API này”.

### 3.2. Khi nào không nên đòi `sub`?

Với Client Credentials, `sub` có thể là service identity hoặc có thể vắng mặt tùy issuer. Nếu API được thiết kế cho workload, contract có thể định nghĩa `client_id` làm chủ thể chính cùng quyền client-specific và audience, thay vì đòi user `sub`.

Không nên áp một schema user token cho mọi grant. Phân tách các **profile được phép** theo issuer/grant/client/token type và bảo đảm lựa chọn profile không phụ thuộc vào một trường do caller tự gửi.

### 3.3. Khi nào `aud` có thể vắng mặt?

RFC 7662 không bắt buộc `aud`. Một AS có thể ràng buộc introspection client với một resource và **chỉ trả active metadata cho token được phép sử dụng ở resource đó**. Nếu hợp đồng này được AS thực thi và đã kiểm thử, Resource Server có thể dựa vào ràng buộc đó thay vì bắt buộc một claim `aud`.

Nếu AS trả `active=true` cho token của nhiều resource nhưng không có `aud`, API sẽ khó tự xác nhận token dành cho mình. Trong trường hợp đó không nên im lặng bỏ qua kiểm tra audience. Đây là rủi ro **confused deputy / token substitution**.

---

## 4. Thứ tự xử lý quyết định tính an toàn

Một thứ tự rõ ràng giúp tránh đọc trường quyền trước khi biết token đang active.

```text
1. Xác minh response đến từ introspection endpoint tin cậy qua HTTPS.
2. Kiểm tra HTTP status và cấu trúc JSON object.
3. Kiểm tra active tồn tại và là JSON boolean.
4. Nếu active=false: từ chối token; bỏ qua mọi metadata khác.
5. Nếu active=true: kiểm tra schema và token contract.
6. Xác định đúng issuer, audience/resource, token type và thời hạn nếu contract yêu cầu.
7. Chuẩn hóa các metadata đã xác minh thành principal/authorities.
8. Áp dụng HTTP/method authorization.
9. Áp dụng ownership, tenant và business authorization.
```

**Không gọi `get("scope").asText()` trước khi kiểm tra `active`**. Một JSON number/object hoặc response inactive có thể bị ép thành chuỗi hoặc đọc sai. Chỉ chuyển dữ liệu có schema được chấp nhận.

### 4.1. Trường hợp `active=false` có metadata khác

Response:

```json
{
  "active": false,
  "sub": "alice-123",
  "scope": "orders:read",
  "exp": 1890003600
}
```

Dù các field trông đầy đủ, **token vẫn inactive**. Không có chuyện “scope đúng nên bỏ qua active false”.

RFC 7662 khuyến cáo AS không tiết lộ thông tin bổ sung về token inactive. Nếu AS trả metadata cùng `active=false`, Resource Server phải **không sử dụng chúng để xác thực, cấp quyền hay ghi PII không cần thiết**. Hãy ghi nhận sự cố provider ở mức mã lỗi/schema, không đưa toàn bộ response vào application log.

### 4.2. Trường hợp `active=true` nhưng `exp` đã quá khứ

```json
{
  "active": true,
  "sub": "alice-123",
  "aud": ["orders-api"],
  "iss": "https://auth.example.test/realms/orders",
  "exp": 1700000000
}
```

Nếu theo thời điểm hiện tại và chính sách của API, `exp` đã qua, có sự bất nhất giữa `active=true` và metadata thời hạn. Trong contract đòi `exp`, Resource Server phải **từ chối** thay vì coi `active=true` là override vô điều kiện.

Lưu ý rằng `exp` là **NumericDate theo giây** chứ không phải milliseconds. Chênh lệch đồng hồ (*clock skew*) cần được chính sách hóa rõ ràng. Các NumericDate có thể biểu diễn phần giây; đừng tùy tiện quy định “phải là integer” rồi cho rằng đó là quy tắc của toàn bộ RFC.

### 4.3. Trường hợp JSON có hai key `active`

Một payload nguy hiểm cho tính nhất quán của parser:

```json
{
  "active": false,
  "active": true
}
```

JSON object có key trùng có thể được các parser xử lý khác nhau (first wins/last wins/error). Với dữ liệu xác thực, nên dùng JSON parser có **duplicate field detection** hoặc chính sách từ chối rõ ràng, không để các lớp middleware và application hiểu token khác nhau.

Ở Jackson có thể bật `STRICT_DUPLICATE_DETECTION` tại parser của đường xử lý response. Nếu đang dùng introspector thư viện, cần xác minh parser/HTTP client mà phiên bản đó thực sự sử dụng; một validator chạy **sau** khi JSON đã thành map không thể khôi phục được thông tin rằng key đã bị lặp.

---

## 5. Khi dữ liệu sai kiểu: không ép kiểu để “lấy được quyền”

### 5.1. `active` sai kiểu

| Input | Vì sao không hợp lệ? | Cách xử lý |
|---|---|---|
| `{"active":true}` | Đúng kiểu. | Tiếp tục validate metadata. |
| `{"active":false}` | Đúng kiểu, token inactive. | Từ chối. |
| `{"active":"true"}` | String, không phải boolean. | Lỗi schema, fail closed. |
| `{"active":"false"}` | String, không phải boolean. | Lỗi schema, fail closed. |
| `{"active":1}` | Number, không phải boolean. | Lỗi schema, fail closed. |
| `{"active":null}` | Null, không phải boolean. | Lỗi schema, fail closed. |
| `{"active":[]}` | Array, không phải boolean. | Lỗi schema, fail closed. |
| `{}` | Thiếu trường bắt buộc. | Lỗi schema, fail closed. |
| `[]` | Root không phải JSON object. | Lỗi schema, fail closed. |

Không viết:

```java
// KHÔNG DÙNG: biến dữ liệu bất kỳ thành boolean.
boolean active = Boolean.parseBoolean(
    String.valueOf(response.get("active"))
);
```

Ví dụ trên biến string `"true"` thành true dù protocol quy định boolean. Nguy hiểm hơn, code khác có thể dùng quy ước truthy khiến `"false"` cũng được coi là true. Hãy dùng **kiểm tra kiểu chặt**.

### 5.2. `scope` sai kiểu

Hợp đồng chuẩn:

```json
{"active":true,"scope":"orders:read orders:write"}
```

Một phản hồi vendor-specific có thể dùng:

```json
{"active":true,"scope":["orders:read","orders:write"]}
```

Nhưng mảng không phải biểu diễn `scope` kiểu chuỗi trong RFC 7662. Nếu issuer thật sự có contract mảng, ứng dụng phải **chọn parser riêng cho profile đó**, không chấp nhận mọi kiểu dữ liệu bằng một lệnh `String.valueOf(...)`.

Đặc biệt:

```json
{
  "active": true,
  "scope": {
    "admin": true
  }
}
```

không được tạo authority `SCOPE_ADMIN` chỉ vì object có field `admin`. Nếu không có một hợp đồng được kiểm chứng, **không cấp thêm authority**. Với API yêu cầu schema nghiêm ngặt, từ chối response/token để phát hiện sai lệch từ AS.

### 5.3. `aud` sai kiểu và lẫn resource

Các dạng hay gặp:

```json
{"active":true,"aud":"orders-api"}
```

```json
{"active":true,"aud":["orders-api","reports-api"]}
```

Hai dạng string hoặc string array có thể hợp lệ. Ngược lại:

```json
{"active":true,"aud":[42,"orders-api"]}
```

```json
{"active":true,"aud":{"resource":"orders-api"}}
```

không nên được chấp nhận trong contract dùng audience string/array-string. Đừng gọi `String.valueOf(aud).contains("orders-api")` vì nó có thể khớp chuỗi nằm bên trong object không đáng tin. Cần so sánh **giá trị audience nguyên vẹn**:

```text
aud == "orders-api"
OR
aud là array of strings chứa đúng phần tử "orders-api"
```

`"orders-api-dev"` hoặc `"not-orders-api"` không được coi là trùng `"orders-api"`.

### 5.4. NumericDate sai đơn vị hoặc sai kiểu

`exp`, `iat`, `nbf` trong RFC 7662 là JSON number tính theo **giây từ Unix epoch**.

```json
{"active":true,"exp":1890003600}
```

Không tự coi những giá trị dưới đây là tương đương:

```json
{"active":true,"exp":"1890003600"}
```

```json
{"active":true,"exp":1890003600000}
```

Trường đầu là string sai kiểu nếu contract đòi number. Trường thứ hai là number nhưng giống Unix **milliseconds**, có thể làm token tưởng như sống trong hàng chục nghìn năm nếu bị diễn giải như giây. Ngoài kiểm tra kiểu, có thể đặt **giới hạn tuổi token tối đa theo policy** hoặc xác minh AS đang gửi đơn vị đúng. Không tự chia cho 1000 theo “độ lớn số” mà không có hợp đồng, vì như vậy che giấu lỗi provider.

### 5.5. Những trường custom cần validator riêng

Một số issuer trả:

```json
{
  "active": true,
  "tenant_id": "tenant-a",
  "roles": ["orders-viewer"],
  "permissions": ["orders:approve"]
}
```

Nếu policy yêu cầu `tenant_id` string, `roles` mảng string và `permissions` mảng string, hãy kiểm tra đúng từng phần tử. Không lấy object/map hoặc list chứa số, sau đó gọi `toString()` và ghép tiền tố `ROLE_` hay `PERM_`.

Nếu `roles` bị thiếu, token vẫn có thể active nhưng không có quyền role. Nếu API yêu cầu role này để truy cập endpoint, route/method security sẽ từ chối. Nếu role là điều kiện **bắt buộc để token thuộc profile hợp lệ**, cần validator profile từ chối sớm.

---

## 6. Hai lớp tùy chỉnh trong Spring Security

Trong Spring Security Servlet Resource Server dùng opaque token, điểm mở rộng chính là **`OpaqueTokenIntrospector`**:

```java
public interface OpaqueTokenIntrospector {
    OAuth2AuthenticatedPrincipal introspect(String token);
}
```

Một introspector chuẩn sẽ gọi endpoint và tạo `OAuth2AuthenticatedPrincipal` hoặc ném exception nếu token/response không được chấp nhận. Có **hai mức kiểm tra** khác nhau:

1. **Kiểm tra sau thư viện:** bọc introspector chuẩn, nhận principal đã được thư viện xác thực rồi bổ sung **hợp đồng ứng dụng** như audience, issuer, tenant hoặc quyền client.
2. **Kiểm tra JSON thô trước khi chuyển kiểu:** khi cần ép chính xác `active` là boolean, từ chối duplicate keys, kiểm tra `scope` ở wire format, phân loại response bất thường. Mức này cần quản lý HTTP client/parser của chính mình hoặc một extension tương đương **trước** khi response được parse thành map/principal.

**Không giả định wrapper sau `delegate.introspect(...)` có thể kiểm tra lại kiểu JSON ban đầu.** Thư viện có thể chuẩn hóa `exp` thành `Instant`, `scope` thành collection hoặc bỏ `active` khỏi principal; sau đó không còn biết AS đã gửi boolean hay string nếu parser trước đó đã ép kiểu.

### 6.1. Cấu hình opaque token cơ bản

`pom.xml` dưới Spring Boot BOM:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

`application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}

security:
  token-contract:
    issuer: https://auth.example.test/realms/orders
    audience: orders-api
```

`INTROSPECTION_CLIENT_SECRET` phải được cấp từ Secret Manager hoặc runtime injection an toàn. **Không hardcode secret** trong file cấu hình Git hoặc code Java.

`SecurityFilterChain`:

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OpaqueApiSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            // API stateless dùng Bearer header, không xác thực bằng cookie.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
```

Việc tắt CSRF chỉ phù hợp với trường hợp API không dùng cookie/session để xác thực; không sao chép máy móc cho ứng dụng web kết hợp session.

---

## 7. Cách 1: bọc introspector chuẩn để kiểm tra metadata theo hợp đồng

Nếu introspector đã xử lý HTTP, `active` và ánh xạ dữ liệu, Resource Server chỉ cần bắt buộc một số metadata. Đây thường là phương án đơn giản hơn tự triển khai toàn bộ giao thức.

Ví dụ lớp wrapper chỉ nhận token có:

- Issuer khớp chính xác.
- Audience chứa `orders-api`.
- Subject không rỗng.
- Scope metadata sau khi chuẩn hóa, nếu có, thuộc dạng string hoặc collection of strings.
- Không tự cấp default scope, role hay tenant.

### 7.1. Code minh họa `ContractCheckingOpaqueTokenIntrospector`

```java
package com.example.orders.security;

import java.net.URI;
import java.net.URL;
import java.util.Collection;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class ContractCheckingOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String expectedIssuer;
    private final String expectedAudience;

    public ContractCheckingOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate,
            String expectedIssuer,
            String expectedAudience) {
        this.delegate = delegate;
        this.expectedIssuer = expectedIssuer;
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Delegate chịu trách nhiệm HTTP request, active và parse.
        // Nếu delegate từ chối token/response, exception đi lên.
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Object issuer = principal.getAttribute("iss");
        Object audience = principal.getAttribute("aud");
        Object subject = principal.getAttribute("sub");
        Object scope = principal.getAttribute("scope");

        if (!sameIssuer(issuer)
                || !containsExpectedAudience(audience)
                || !(subject instanceof String s) || s.isBlank()
                || !validNormalizedScopeType(scope)) {
            // Không log raw token hoặc response chứa dữ liệu nhạy cảm.
            throw new BadOpaqueTokenException(
                "Token does not satisfy orders-api contract");
        }

        return principal;
    }

    private boolean sameIssuer(Object value) {
        if (value instanceof String s) {
            return expectedIssuer.equals(s);
        }
        // Một số parser/phiên bản có thể biểu diễn URL bằng URI/URL.
        if (value instanceof URI uri) {
            return expectedIssuer.equals(uri.toString());
        }
        if (value instanceof URL url) {
            return expectedIssuer.equals(url.toString());
        }
        return false;
    }

    private boolean containsExpectedAudience(Object value) {
        if (value instanceof String audience) {
            return expectedAudience.equals(audience);
        }
        if (value instanceof Collection<?> audiences) {
            if (audiences.isEmpty()) {
                return false;
            }
            for (Object item : audiences) {
                if (!(item instanceof String s) || s.isBlank()) {
                    return false;
                }
            }
            return audiences.contains(expectedAudience);
        }
        return false;
    }

    private static boolean validNormalizedScopeType(Object value) {
        // Scope không bắt buộc ở mọi token. Route cần scope sẽ đòi
        // authority riêng; không tạo quyền mặc định.
        if (value == null) {
            return true;
        }
        if (value instanceof String) {
            return true;
        }
        if (value instanceof Collection<?> scopes) {
            return scopes.stream()
                .allMatch(s -> s instanceof String);
        }
        return false;
    }
}
```

**Điểm phải hiểu khi dùng wrapper này:**

- Lớp chỉ nhìn thấy **principal sau khi delegate đã xử lý**, không trực tiếp thấy JSON response thô.
- `scope` có thể đã được introspector chuyển từ chuỗi sang collection. Việc chấp nhận collection trong wrapper là chấp nhận **dạng nội bộ đã chuẩn hóa**, không tuyên bố AS được phép trả `scope` dạng array trên wire.
- Trường `iss` hoặc `aud` thiếu sẽ khiến wrapper từ chối vì **contract của `orders-api`**, mặc dù RFC 7662 cho phép chúng vắng mặt.
- Nếu token không có scope, wrapper có thể chấp nhận authentication nhưng route cần `SCOPE_orders:read` vẫn từ chối authorization. Nếu contract buộc mọi token phải có scope không rỗng, thêm yêu cầu đó **một cách tường minh**.
- Việc kiểm tra audience chỉ an toàn khi đối tượng `aud` do **introspector tin cậy** cung cấp và không bị client tự ghi đè vào principal.

### 7.2. Khởi tạo delegate và đăng ký bean

Ví dụ cho Spring Security 6.x hỗ trợ `NimbusOpaqueTokenIntrospector`:

```java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
public class OpaqueIntrospectionConfig {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
            String introspectionUri,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
            String clientId,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
            String clientSecret,
        @Value("${security.token-contract.issuer}")
            String issuer,
        @Value("${security.token-contract.audience}")
            String audience
    ) {
        OpaqueTokenIntrospector delegate =
            new NimbusOpaqueTokenIntrospector(
                introspectionUri, clientId, clientSecret);

        return new ContractCheckingOpaqueTokenIntrospector(
            delegate, issuer, audience);
    }
}
```

Tên implementation/builder có thể thay đổi hoặc bị deprecate tùy phiên bản Spring Security 6.x/7.x; `NimbusOpaqueTokenIntrospector` là API được dùng rộng rãi trong nhánh 6.x. Khi nâng version, kiểm tra API `SpringOpaqueTokenIntrospector` hoặc implementation tương ứng trong tài liệu của bản thư viện thực tế, tránh sao chép nhầm constructor.

**Không đăng ký thêm một bean `OpaqueTokenIntrospector` khác mà không có điều kiện**, vì application context có thể không biết bean nào được dùng. Đảm bảo filter chain thực tế trỏ đúng introspector đã bọc (auto-wiring thông qua bean hoặc DSL cấu hình rõ ràng).

### 7.3. Khi nào wrapper chưa đủ?

Wrapper không thể khẳng định những điều sau nếu delegate đã chuẩn hóa dữ liệu:

- JSON ban đầu có `"active":"true"` hay `"active":true`?
- `scope` ban đầu là string hay array?
- JSON có key `active` lặp?
- `exp` là số nguyên, số thập phân hay string mà delegate đã ép kiểu?
- Response content type có phải `application/json` hay HTTP converter đã đọc một loại khác?

Nếu **chính sách bắt buộc kiểm tra byte/JSON từ endpoint trước khi parser của thư viện diễn giải**, phải có lớp kiểm tra **tại ranh giới nhận HTTP response**, chứ không chỉ nhìn `OAuth2AuthenticatedPrincipal` sau khi tạo.

---

## 8. Cách 2: kiểm tra JSON response thô trước khi tạo principal

Khi một dự án cần xử lý nghiêm ngặt response sai kiểu, cách minh bạch nhất là sở hữu pipeline:

```text
RestOperations POST introspection
    ↓
HTTP status / TLS / content-type / response size
    ↓
JSON parser nghiêm ngặt (kiểm tra duplicate fields)
    ↓
active: boolean bắt buộc
    ↓
Nếu false → từ chối
    ↓
Các trường bắt buộc theo API contract
    ↓
Tạo OAuth2AuthenticatedPrincipal với attributes/authorities rõ ràng
```

Đây là ví dụ **mang tính giáo dục về custom introspection**, không có nghĩa mọi ứng dụng nên tự viết lại client RFC 7662. Nếu introspector chuẩn đã đáp ứng policy, ưu tiên **wrapper** ở phần trước. Khi tự viết HTTP/parser, bạn phải chịu trách nhiệm đầy đủ về client authentication, timeout, TLS, error handling, secret masking, parser limits, logging và cập nhật thư viện.

### 8.1. Ví dụ `StrictRfc7662Introspector`

Ví dụ giả định **client ID/secret của introspection client chỉ chứa ký tự ASCII an toàn** khi dùng Basic; với credential chứa ký tự đặc biệt, hãy kiểm tra yêu cầu encode OAuth client authentication của AS/RFC 6749 và ưu tiên dùng HTTP client/autenticator chuẩn đã hỗ trợ. Đoạn code tập trung vào **schema của JSON phản hồi**, không thay thế policy bảo mật transport.

```java
package com.example.orders.security;

import java.math.BigDecimal;
import java.net.URI;
import java.time.Clock;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestOperations;

public final class StrictRfc7662Introspector
        implements OpaqueTokenIntrospector {

    // RFC 6749 scope-token: visible ASCII trừ double quote và backslash.
    private static final Pattern SCOPE_TOKEN =
        Pattern.compile("[\\x21\\x23-\\x5B\\x5D-\\x7E]+");

    private final RestOperations http;
    private final ObjectMapper json;
    private final Clock clock;
    private final URI endpoint;
    private final String introspectionClientId;
    private final String introspectionClientSecret;
    private final String expectedIssuer;
    private final String expectedAudience;

    public StrictRfc7662Introspector(
            RestOperations http,
            ObjectMapper json,
            Clock clock,
            URI endpoint,
            String clientId,
            String clientSecret,
            String expectedIssuer,
            String expectedAudience) {
        this.http = http;
        this.json = json;
        this.clock = clock;
        this.endpoint = endpoint;
        this.introspectionClientId = clientId;
        this.introspectionClientSecret = clientSecret;
        this.expectedIssuer = expectedIssuer;
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        if (token == null || token.isBlank()) {
            throw new BadOpaqueTokenException("Invalid bearer token");
        }

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_FORM_URLENCODED);
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));

        // Demo: Basic Auth cho credentials test ASCII-safe.
        // Production: theo đúng auth method đã đăng ký với AS.
        headers.setBasicAuth(
            introspectionClientId, introspectionClientSecret);

        MultiValueMap<String, String> form =
            new LinkedMultiValueMap<>();
        form.add("token", token);
        form.add("token_type_hint", "access_token");

        ResponseEntity<String> response;
        try {
            response = http.exchange(
                endpoint,
                HttpMethod.POST,
                new HttpEntity<>(form, headers),
                String.class
            );
        } catch (RestClientException ex) {
            // Lỗi HTTP 401/403/429/5xx, DNS, timeout, TLS...
            // Không gắn token hoặc response body vào exception công khai.
            throw new OAuth2IntrospectionException(
                "Introspection endpoint unavailable or request rejected");
        }

        if (response.getStatusCode().value() != 200
                || response.getBody() == null) {
            throw invalidResponse();
        }

        JsonNode root;
        try {
            root = json.readTree(response.getBody());
        } catch (JsonProcessingException ex) {
            throw invalidResponse();
        }

        if (root == null || !root.isObject()) {
            throw invalidResponse();
        }

        JsonNode active = root.get("active");
        if (active == null || !active.isBoolean()) {
            throw invalidResponse();
        }

        if (!active.booleanValue()) {
            // Quan trọng: không đọc scope/sub dù response có gửi thêm.
            throw new BadOpaqueTokenException("Inactive token");
        }

        // Những trường bên dưới bắt buộc do contract orders-api,
        // KHÔNG phải vì mọi response RFC 7662 đều bắt buộc có chúng.
        String issuer = requiredString(root, "iss");
        String subject = requiredString(root, "sub");
        List<String> audiences = requiredAudience(root.get("aud"));

        if (!expectedIssuer.equals(issuer)
                || !audiences.contains(expectedAudience)) {
            throw new BadOpaqueTokenException(
                "Token not intended for this resource");
        }

        BigDecimal expiry = requiredNumericDate(root, "exp");
        BigDecimal now = BigDecimal.valueOf(
            clock.instant().getEpochSecond());
        if (expiry.compareTo(now) <= 0) {
            throw new BadOpaqueTokenException("Expired token");
        }

        // RFC 7662 cho phép nbf và iat vắng mặt.
        if (root.has("nbf")) {
            BigDecimal notBefore = requiredNumericDate(root, "nbf");
            if (notBefore.compareTo(now) > 0) {
                throw new BadOpaqueTokenException(
                    "Token not yet valid");
            }
        }
        if (root.has("iat")) {
            requiredNumericDate(root, "iat");
        }

        String scopesValue = optionalString(root, "scope");
        List<String> scopes = parseStandardScopes(scopesValue);

        // Các trường bổ sung phải đúng schema nếu được dùng.
        optionalString(root, "client_id");
        optionalString(root, "token_type");
        optionalString(root, "jti");

        Set<GrantedAuthority> authorities = new LinkedHashSet<>();
        for (String scope : scopes) {
            authorities.add(
                new SimpleGrantedAuthority("SCOPE_" + scope));
        }

        Map<String, Object> attributes = new LinkedHashMap<>();
        attributes.put("active", true);
        attributes.put("iss", issuer);
        attributes.put("sub", subject);
        attributes.put("aud", audiences);
        attributes.put("exp", expiry);
        attributes.put("scope", scopes);
        if (root.hasNonNull("client_id")) {
            attributes.put("client_id",
                root.get("client_id").textValue());
        }

        // Principal name là subject đã qua contract validation.
        return new DefaultOAuth2AuthenticatedPrincipal(
            subject, attributes, authorities);
    }

    private static String requiredString(
            JsonNode root, String field) {
        JsonNode value = root.get(field);
        if (value == null || !value.isTextual()
                || value.textValue().isBlank()) {
            throw invalidResponse();
        }
        return value.textValue();
    }

    private static String optionalString(
            JsonNode root, String field) {
        JsonNode value = root.get(field);
        if (value == null) {
            return null;
        }
        if (!value.isTextual()) {
            throw invalidResponse();
        }
        return value.textValue();
    }

    private static BigDecimal requiredNumericDate(
            JsonNode root, String field) {
        JsonNode value = root.get(field);
        if (value == null || !value.isNumber()) {
            throw invalidResponse();
        }
        return value.decimalValue();
    }

    private static List<String> requiredAudience(JsonNode value) {
        if (value == null) {
            throw invalidResponse();
        }
        if (value.isTextual() && !value.textValue().isBlank()) {
            return List.of(value.textValue());
        }
        if (value.isArray()) {
            List<String> audiences = new ArrayList<>();
            for (JsonNode entry : value) {
                if (!entry.isTextual()
                        || entry.textValue().isBlank()) {
                    throw invalidResponse();
                }
                audiences.add(entry.textValue());
            }
            if (!audiences.isEmpty()) {
                return audiences;
            }
        }
        throw invalidResponse();
    }

    private static List<String> parseStandardScopes(String scope) {
        if (scope == null || scope.isEmpty()) {
            return List.of();
        }

        List<String> result = new ArrayList<>();
        // Delimiter chuẩn là dấu cách ASCII, không phải comma.
        for (String item : scope.split(" ", -1)) {
            if (!SCOPE_TOKEN.matcher(item).matches()) {
                throw invalidResponse();
            }
            result.add(item);
        }
        return List.copyOf(result);
    }

    private static OAuth2IntrospectionException invalidResponse() {
        return new OAuth2IntrospectionException(
            "Invalid introspection response schema");
    }
}
```

**Phạm vi và giới hạn của ví dụ:**

1. Đoạn code thực sự nhìn thấy **JSON thô** và kiểm tra `active` đúng boolean trước khi tạo principal.
2. Mỗi response `active=false` bị từ chối **trước khi đọc metadata quyền**.
3. `iss`, `sub`, `aud` và `exp` được xem là **bắt buộc theo contract orders-api**. Nếu AS của bạn không bảo đảm những trường này, không copy code mà chưa thống nhất cách resource binding/subject được bảo đảm.
4. `scope` được yêu cầu đúng chuỗi RFC 7662; không tự nhận array/vendor extension. Nếu thiếu scope, principal không có `SCOPE_...`, nên route cần scope bị từ chối.
5. Mẫu kiểm tra `nbf` và `exp` không có allowance clock skew. Hệ thống production nên chọn chính sách lệch đồng hồ rõ ràng theo AS, không âm thầm thêm vài giờ.
6. `exp` được đưa vào principal dưới dạng `BigDecimal` do lớp custom này định nghĩa; introspector framework có thể dùng kiểu nội bộ khác như `Instant`. Code downstream **phải theo kiểu do implementation mình tạo**, không cast tùy tiện.
7. Client HTTP chưa có **connection pooling, total deadline, retry/backoff, response body size limits**, rate limiting và observability đầy đủ. Các yêu cầu này cần được bổ sung nếu dùng production.
8. ObjectMapper trong ví dụ phải được cấu hình **strict duplicate detection**, giới hạn độ sâu/kích thước đầu vào và không cho phép coercion sai kiểu theo yêu cầu security. Chỉ nhận `JsonNode` không tự bảo đảm phát hiện duplicate keys.
9. Ví dụ bắt `RestClientException` và trả lỗi tổng quát. Trong production cần phân loại 401/403 credential, 429/5xx, timeout và lỗi JSON **trong logs an toàn**, nhưng không đưa raw token/secret/body vào thông báo trả client.
10. Basic Auth ở đây giả định credential thích hợp. Với client ID/secret chứa ký tự đặc biệt theo OAuth 2.0, phải thực hiện đúng encoding/method của nhà phát hành; nên ưu tiên implementation authentication đã được kiểm chứng của thư viện thay vì tự tạo.
11. Ví dụ cho thấy nguyên tắc strict parsing; nó không thay thế test tích hợp và security review của code tự phát triển tại bước QA sau.

### 8.2. Khởi tạo HTTP client với timeout hữu hạn

Ví dụ đăng ký implementation custom ở môi trường sử dụng Spring Boot:

```java
package com.example.orders.security;

import java.net.URI;
import java.time.Clock;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.web.client.RestTemplate;

@Configuration
class StrictIntrospectionConfig {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
            String endpoint,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
            String clientId,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
            String clientSecret,
        @Value("${security.token-contract.issuer}")
            String issuer,
        @Value("${security.token-contract.audience}")
            String audience,
        ObjectMapper objectMapper
    ) {
        SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(1_500);
        factory.setReadTimeout(2_000);

        RestTemplate http = new RestTemplate(factory);

        return new StrictRfc7662Introspector(
            http,
            objectMapper,
            Clock.systemUTC(),
            URI.create(endpoint),
            clientId,
            clientSecret,
            issuer,
            audience
        );
    }
}
```

Giá trị timeout ở đây chỉ **minh họa**, không phải recommendation chung. Nếu API có SLO vài trăm milliseconds hoặc AS qua liên vùng, cần đo latency, số request đồng thời và timeout của gateway.

**Chọn một cách tùy chỉnh:** phần 7 và phần 8 là **hai phương án thay thế**. Không đưa cả `OpaqueIntrospectionConfig` và `StrictIntrospectionConfig` vào cùng context nếu chúng cùng khai báo bean `OpaqueTokenIntrospector`.

### 8.3. Nhận biết response bị parse sai trước khi gọi custom logic

Nếu ứng dụng dùng `RestTemplate` với converter tự động ánh xạ JSON thành `Map<String,Object>`, bước convert có thể đã thay đổi kiểu hoặc cách xử lý duplicate keys. Nếu yêu cầu giữ nguyên wire schema, cần lấy **raw response** và parse bằng cấu hình strict.

Ví dụ một đường test dùng Jackson để từ chối key lặp:

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper strictMapper = new ObjectMapper();
strictMapper.enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);

// Khi đọc JSON có hai key "active" trùng, mapper cần ném lỗi.
```

Cấu hình ObjectMapper toàn cục có thể ảnh hưởng endpoint JSON nghiệp vụ, nên cân nhắc **một mapper riêng cho introspection** để kiểm soát chính xác. Không tin rằng việc JSON object “trông đúng” sau parse chứng minh các key ban đầu là duy nhất.

---

## 9. Bảo vệ trước null, thiếu metadata và kiểu không mong đợi trong principal

Dù dùng introspector chuẩn hay custom, ứng dụng downstream cần tránh lỗi cast.

### 9.1. Đừng viết getter trực tiếp giả định mọi thuộc tính hiện diện

Ví dụ dễ lỗi:

```java
// KHÔNG DÙNG:
String tenantId =
    principal.<String>getAttribute("tenant_id").toUpperCase();

List<String> aud =
    (List<String>) principal.getAttribute("aud");
```

Vấn đề:

- `tenant_id` có thể thiếu → `NullPointerException`.
- `tenant_id` có thể sai kiểu → `ClassCastException`.
- `aud` có thể là string đơn hoặc collection, không phải `List<String>`.
- Nếu object trong collection không phải string, generic cast có thể không phát hiện sớm.
- Exception có thể tạo `500` không rõ nguyên nhân thay vì từ chối token theo policy.

### 9.2. Tạo context ứng dụng đã được chuẩn hóa

Một cách tiếp cận là chỉ chuyển data sau khi validate:

```java
package com.example.orders.security;

public record AuthenticatedActor(
    String issuer,
    String subject,
    String tenantId
) { }
```

Mapper:

```java
package com.example.orders.security;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

public final class ActorMapper {
    private ActorMapper() { }

    public static AuthenticatedActor requireUserActor(
            OAuth2AuthenticatedPrincipal principal) {
        Object rawIssuer = principal.getAttribute("iss");
        Object rawSubject = principal.getAttribute("sub");
        Object rawTenant = principal.getAttribute("tenant_id");

        if (!(rawIssuer instanceof String issuer)
                || issuer.isBlank()
                || !(rawSubject instanceof String subject)
                || subject.isBlank()
                || !(rawTenant instanceof String tenant)
                || tenant.isBlank()) {
            throw new AccessDeniedException(
                "Authenticated principal lacks required user context");
        }

        return new AuthenticatedActor(issuer, subject, tenant);
    }
}
```

**Chú ý:** nếu introspector đã normalize `iss` thành URI/URL, mapper phải dùng dạng được contract thống nhất hoặc utility chuyển đổi đã kiểm soát. **Không dùng `String.valueOf(rawIssuer)` để tạo issuer tin cậy từ object tùy ý.**

`AuthenticatedActor` chỉ nên được tạo từ **principal đã xác thực** hoặc đường identity mapping nội bộ đáng tin, không tạo từ request JSON hoặc HTTP headers của client.

### 9.3. Thiếu metadata thuộc lớp authentication hay authorization?

Điều này phụ thuộc vai trò của metadata:

- Nếu `iss`/`aud`/**token type** là điều kiện để Resource Server xác định token có được chấp nhận ngay từ đầu, thiếu/sai thường nên được xử lý ở **authentication/token contract**.
- Nếu token active và profile hợp lệ nhưng không có scope để gọi endpoint đọc, đó là **authorization**: token không có `SCOPE_orders:read` nên route trả 403.
- Nếu token active, đủ scope nhưng không có tenant để quyết định quyền trên đơn, có thể từ chối tại application authorization; nếu tenant bắt buộc cho *mọi* token của profile, có thể từ chối sớm tại authentication.
- Nếu AS trả response sai JSON hoặc `active` sai kiểu, đó là **lỗi response/protocol integration**, không phải “user thiếu quyền” thông thường.

**Không có một HTTP status duy nhất cho mọi sai lệch schema**. Các exception handler thực tế của Spring Security có thể trả 401 hoặc báo lỗi upstream tùy cách triển khai; điều quan trọng là **không thực thi thao tác bảo vệ**. Nếu muốn phân biệt 401/403/503 cho client, phải làm rõ error contract, tránh làm lộ trạng thái token hoặc dữ liệu nội bộ.

---

## 10. Không tự tạo authority từ dữ liệu bất kỳ

Một response có thể chứa nhiều claim:

```json
{
  "active": true,
  "scope": "orders:read",
  "roles": ["ADMIN"],
  "permissions": ["orders:delete"],
  "tenant_id": "tenant-a"
}
```

Không nên biến mọi giá trị thành Spring authority vô điều kiện:

```java
// KHÔNG DÙNG:
for (Object value : response.values()) {
    authorities.add(
        new SimpleGrantedAuthority("ROLE_" + value));
}
```

Cần phân biệt:

- `scope` chuẩn → quyền kiểu `SCOPE_orders:read` khi parser xác nhận string và token profile đúng.
- `roles` → role riêng của issuer/resource, có schema và allowlist.
- `permissions` → quyền nghiệp vụ nếu API chấp nhận hợp đồng này.
- `tenant_id` → ngữ cảnh giới hạn dữ liệu, **không phải một role**.

Nếu có cả `scope` và `scp`/`roles`, không tự **union** mọi quyền. Một số claim có thể chỉ dành cho resource hoặc actor khác. Chỉ lấy nguồn đã được định nghĩa trong hợp đồng của issuer/tenant/audience tương ứng.

### 10.1. Kiểm tra permission value theo allowlist

Ví dụ hệ thống có hai quyền tùy biến:

```text
orders:approve
orders:export
```

Một mapper có thể ánh xạ chúng thành:

```text
PERM_orders:approve
PERM_orders:export
```

chỉ sau khi xác nhận claim `permissions` là array-string và issuer/profile cho phép. Nếu có chuỗi lạ `"superadmin"`, không tự cấp `ROLE_SUPERADMIN`. Có thể bỏ qua quyền lạ nếu contract quy định tính tương thích, hoặc từ chối toàn response nếu tính nhất quán là yêu cầu bắt buộc. Quyết định này phải **ổn định và có test**.

### 10.2. Đừng giải quyết lỗi response bằng cách hạ quyền route

Ví dụ khi response thiếu `scope`, API có thể thấy tăng `403` cho `GET /api/orders/**`. Cách sửa sai:

```java
// KHÔNG DÙNG: làm mọi token active được vào route.
.requestMatchers("/api/orders/**").authenticated()
```

Cách sửa đúng là **xác nhận AS đang phát hành scope gì**, response có đúng contract, converter có ánh xạ `SCOPE_...` hay không, và route thực sự yêu cầu quyền nào. Không hạ yêu cầu bảo mật để che một lỗi tích hợp.

---

## 11. Phân biệt lỗi AS, lỗi token và lỗi nghiệp vụ

Một hệ thống dễ vận hành cần phân loại thất bại để operator biết nên sửa credential, sửa schema hay yêu cầu user lấy token mới.

| Lớp lỗi | Ví dụ | Hành vi bảo mật | Hướng điều tra |
|---|---|---|---|
| **Inactive token** | `active=false` | Không tạo principal. | Token hết hạn, bị revoke hoặc AS không cho introspect. |
| **Protocol schema** | Thiếu `active`, `active="true"`, JSON lỗi. | Fail closed; không tự ép kiểu. | AS phiên bản mới, serializer, proxy, parsing. |
| **Token contract** | `active=true` nhưng thiếu `aud`/`iss`/`sub` mà API buộc có. | Không chấp nhận token theo profile. | Hợp đồng AS–API, issuer/resource binding. |
| **Metadata type** | `exp` là string, `aud` là object. | Không dùng dữ liệu sai kiểu. | JSON mapping/token profile. |
| **Credential integration** | AS trả HTTP 401/403. | Không cho request qua. | Introspection client secret, client auth method, permission. |
| **Upstream transient** | Timeout, `429`, `503`. | Fail closed; retry có giới hạn nếu phù hợp. | Network, TLS, quota, AS availability. |
| **Insufficient scope** | Token active, thiếu `orders:read`. | Route từ chối authorization. | Scope grant và converter. |
| **Object-level denial** | Token có scope nhưng order thuộc user khác. | Từ chối theo owner/tenant policy. | BOLA/IDOR, database/ACL, delegation. |

Không ghi toàn bộ response khi schema sai. Response introspection có thể chứa PII, scopes, clients và token IDs; raw token và introspection client secret tuyệt đối không được xuất vào log/traces.

---

## 12. Chặn lỗi mạng nhưng không đánh đồng chúng với `active=false`

Khi AS gặp sự cố, một số chương trình chuyển mọi exception thành “token inactive”:

```java
// KHÔNG DÙNG:
try {
    return delegate.introspect(token);
} catch (Exception e) {
    return anonymousPrincipalWithNoAuthorities();
}
```

Cách này có thể tạo principal ngoài ý muốn, che sự cố dependency và làm người quản trị mất khả năng phát hiện credential hết hạn. Thậm chí nếu principal không có authority, các route `authenticated()` vẫn có thể đi qua tùy implementation.

Một cách xử lý an toàn:

- **Token inactive**: thư viện ném một exception phù hợp, không tạo authentication.
- **HTTP 401/403 của AS**: khác nguyên nhân, operator kiểm tra client credentials và policy.
- **`429`/`503`/timeout**: có thể retry rất giới hạn, backoff/jitter và tổng deadline; khi không có kết quả vẫn từ chối.
- **Schema invalid**: không retry vô hạn vì response sai cấu trúc thường không tự sửa sau vài milliseconds.
- **Audience/issuer sai**: không thử introspection ở issuer khác theo input token để tìm nơi nào báo active.
- **Scope thiếu**: không “thử lại cho đến khi scope xuất hiện” nếu không có quá trình cập nhật grant rõ ràng.

### 12.1. Timeout và retry có giới hạn

Một request introspection đi qua network. Đặt:

- Connect timeout và read timeout hữu hạn.
- Tổng thời gian cho cả attempts nằm trong request budget.
- Max retries thấp cho lỗi thực sự transient.
- Exponential backoff + jitter, tôn trọng `Retry-After` khi hợp lý.
- Connection pool/concurrency limit để tránh nhân số request tới AS.
- Circuit breaker nếu AS outage kéo dài, nhưng **không có nhánh cấp quyền khi circuit open**.

Ví dụ policy đơn giản:

```text
if AS returned valid active=false:
    reject token, do not retry
else if AS returned invalid JSON/schema:
    fail closed, report integration error
else if AS timeout/503:
    retry at most N times within total deadline
    if no valid answer: fail closed
else if AS returned valid active=true:
    validate contract and route/object authorization
```

Trong môi trường tải cao, retry ở HTTP client, service mesh và gateway nếu cùng bật có thể tạo **retry storm**. Hãy đo request amplification và thống nhất một vị trí sở hữu retry budget.

### 12.2. Cached introspection result cũng có schema và vòng đời

Nếu application cache kết quả `active=true`:

- Chỉ cache sau khi response **được xác thực và schema hợp lệ**.
- Không cache response bị parse lỗi như một principal hợp lệ.
- TTL không vượt `exp` nếu token có trường này, và phải phản ánh yêu cầu thu hồi.
- Không dùng cache active vĩnh viễn để bỏ qua AS khi token đã bị revoke.
- Không chia sẻ metadata giữa issuer/resource mà không có namespace và trust model.
- Không dùng cached principal của token A cho token B vì cache key bị thiết kế sai.
- Không xem mạng lỗi là `active=false` hoặc `active=true` và cache trạng thái đó không có bằng chứng.

Thực tế **revocation delay** của hệ thống sẽ phụ thuộc việc API có cache introspection hay không, cache TTL và khả năng invalidation; không thể suy ra “opaque token luôn bị revoke tức thì” nếu chính API giữ kết quả cũ.

---

## 13. Kiểm thử phản hồi thiếu trường, sai kiểu và trạng thái bất thường

Một test suite đủ hữu ích phải gửi **JSON/HTTP response thực qua pipeline introspection**, không chỉ tạo principal mock rồi kiểm `hasAuthority`.

### 13.1. Ma trận positive và negative test

| Test case | JSON/HTTP mẫu | Kỳ vọng |
|---|---|---|
| Active hợp lệ, đủ contract | `{"active":true,"iss":"...","aud":["orders-api"],"sub":"alice","exp":...}` | Có thể tạo principal; quyền theo `scope`. |
| Inactive tối thiểu | `{"active":false}` | Từ chối token. |
| Inactive vẫn có scope | `{"active":false,"scope":"orders:read"}` | Vẫn từ chối; không dùng scope. |
| Thiếu `active` | `{"scope":"orders:read"}` | Lỗi schema, fail closed. |
| `active` string | `{"active":"true"}` | Lỗi schema, không ép kiểu. |
| `active` number | `{"active":1}` | Lỗi schema. |
| `active=null` | `{"active":null}` | Lỗi schema. |
| Root array | `[{"active":true}]` | Lỗi schema. |
| Body HTML | `<html>error</html>` | Lỗi content/parse, không cấp quyền. |
| JSON cắt cụt | `{"active":tru` | Parse failure, không cấp quyền. |
| Key `active` lặp | `{"active":false,"active":true}` | Parser strict phải từ chối. |
| Active đúng nhưng thiếu `aud` | `{"active":true,"sub":"alice"}` | Bị từ chối bởi orders-api contract nếu aud bắt buộc. |
| Audience sai | `{"active":true,"aud":["payments-api"]}` | Không nhận token của resource khác. |
| Audience sai kiểu | `{"active":true,"aud":{"name":"orders-api"}}` | Lỗi schema, không `toString().contains(...)`. |
| Scope vắng mặt | `{"active":true,...}` | Không cấp scope authority; route cần scope bị từ chối. |
| Scope là array | `{"active":true,"scope":["orders:read"]}` | Từ chối theo profile `scope` string của ví dụ. |
| Scope là object | `{"active":true,"scope":{"admin":true}}` | Không tạo authority. |
| `exp` dạng string | `{"active":true,"exp":"1890003600"}` | Từ chối nếu contract yêu cầu NumericDate number. |
| `exp` đã qua | `{"active":true,"exp":1700000000}` | Từ chối dù active=true. |
| `nbf` trong tương lai | `{"active":true,"nbf":<future-seconds>}` | Từ chối theo chính sách thời gian. |
| `sub` thiếu | `{"active":true,"aud":["orders-api"]}` | Nếu user profile bắt buộc subject: từ chối. |
| HTTP 401 của AS | Unauthorized | Lỗi introspection client, không cho token qua. |
| HTTP 429/503 | Rate limit / Service Unavailable | Retry giới hạn nếu có, sau đó fail closed. |
| HTTP 204 | Không body | Không thể coi token active. |
| HTTP 200 body `null` | JSON null | Lỗi schema. |
| Token active, không đủ scope | Có `scope="orders:write"` | `GET` cần read phải từ chối authorization. |
| Token active, đủ scope, sai owner | Alice dùng token đọc đơn Bob | Từ chối object authorization. |

Các `...` và `<future-seconds>` trong bảng là ký hiệu rút gọn, **không phải JSON test fixture hợp lệ**. Trong test thực hãy tạo các giá trị `iss`, `aud`, `sub`, `exp` đầy đủ và cố định thời gian bằng `Clock.fixed(...)` để các tests có thể lặp lại.

### 13.2. JUnit test trực tiếp parser và schema

Nên tách hàm/đối tượng validate JSON thô thành một thành phần có thể test độc lập. Ví dụ pseudocode:

```text
given HTTP 200, body {"active":"true"}:
    expect protocol/schema failure

given HTTP 200, body {"active":false,"scope":"orders:read"}:
    expect inactive-token rejection
    expect zero authorities

given HTTP 200, body active=true, aud=["payments-api"]:
    expect token-contract failure

given HTTP 200, body active=true, iss/orders-api/sub valid,
                      scope="orders:read", exp in future:
    expect principal with SCOPE_orders:read
```

Với Jackson, một unit test có thể kiểm tra tính năng từ chối duplicate keys:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class IntrospectionJsonStrictTest {

    @Test
    void duplicateActiveIsRejected() {
        ObjectMapper mapper = new ObjectMapper();
        mapper.enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);

        assertThrows(JsonProcessingException.class,
            () -> mapper.readTree(
                "{\"active\":false,\"active\":true}"));
    }
}
```

Đây là **kiểm tra parser**, không tự chứng minh HTTP client hoặc Spring filter chain sử dụng đúng mapper đó. Test tích hợp cần gửi JSON qua endpoint stub tới implementation thật.

### 13.3. Integration test bằng mock HTTP endpoint

Có thể dùng `MockRestServiceServer` khi custom introspector dùng `RestTemplate`, hoặc WireMock/MockWebServer khi cần HTTP server cục bộ.

Ví dụ với `MockRestServiceServer`:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.net.URI;
import java.time.Clock;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

class StrictIntrospectionHttpTest {

    @Test
    void stringActiveFailsClosed() {
        RestTemplate http = new RestTemplate();
        MockRestServiceServer server =
            MockRestServiceServer.bindTo(http).build();

        String endpoint = "https://auth.example.test/oauth2/introspect";
        server.expect(requestTo(endpoint))
            .andExpect(method(HttpMethod.POST))
            .andRespond(withSuccess(
                "{\"active\":\"true\"}", MediaType.APPLICATION_JSON));

        var introspector = new StrictRfc7662Introspector(
            http,
            new ObjectMapper(),
            Clock.systemUTC(),
            URI.create(endpoint),
            "test-client",
            "test-secret",
            "https://auth.example.test/realms/orders",
            "orders-api"
        );

        assertThrows(OAuth2IntrospectionException.class,
            () -> introspector.introspect("test-token"));

        server.verify();
    }
}
```

Test này dùng **secret giả và không gọi mạng thật**. Cần thêm assertions:

- HTTP method `POST`, content-type `application/x-www-form-urlencoded`.
- Body `token=...` được form-encode chính xác.
- `Authorization` header dùng đúng client authentication và không bị ghi vào output công khai.
- Trường `active` false → exception/denial theo policy.
- Các trường `iss`/`aud`/`sub`/`exp`/`scope` có đủ thì principal/authorities đúng.
- HTTP 401/429/503, timeout và JSON body lỗi đều không cho request vào business endpoint.
- Negative tests với `scope` object, `aud` number, `exp` string, duplicated active.
- Integration test với AS staging thật để phát hiện khác biệt serialization.

Nếu test dùng `ObjectMapper` mặc định mà production dùng mapper có duplicate detection, hãy tiêm đúng mapper production vào test. Không chỉ kiểm tra HTTP 200 của stub rồi bỏ qua việc `active` và contract có được thực thi hay không.

### 13.4. MockMvc `opaqueToken()` kiểm tra được điều gì?

`spring-security-test` hỗ trợ:

```java
mvc.perform(get("/api/orders/42")
    .with(opaqueToken().authorities(
        new SimpleGrantedAuthority("SCOPE_orders:read"))))
   .andExpect(status().isOk());
```

Điều kiện cần: controller/fixture và owner policy cho phép truy cập đơn `42`.

Nhưng `opaqueToken()` **giả lập principal đã xác thực**, không thực sự gửi request introspection đến AS. Vì vậy test này **không chứng minh** `active` được parse đúng kiểu, duplicate keys bị từ chối hoặc endpoint HTTP trả lỗi đúng cách. Để test schema cần dùng **HTTP stub + introspector thật** hoặc direct parser tests.

### 13.5. Test sự thay đổi hợp đồng giữa AS và API

Khi nâng version Authorization Server, nên so sánh token thử nghiệm của các grant:

| Token profile | Metadata có thể khác | Cần test |
|---|---|---|
| Authorization Code / user token | `sub`/`username`, `scope`, tenant. | User identity, owner, audience, expiry. |
| Client Credentials / service token | `client_id`, có thể không có user `sub`. | Workload profile riêng; không ép user schema. |
| Token exchange/delegation | Subject, actor/claim bổ sung, audience khác. | Không tự thừa hưởng mọi scope của token gốc. |
| Token dành cho API khác | `aud` không chứa `orders-api`. | Không chấp nhận token substitution. |
| Token bị revoke | `active=false` hoặc AS xử lý theo policy. | Không cache active quá lâu. |
| Token gần hết hạn | `exp` và clock skew. | Không làm token sống vượt chính sách. |

Hợp đồng nào thay đổi phải có **versioning/migration** rõ. Không tắt validator trong production chỉ vì AS đã đổi tên một trường.

---

## 14. Quan sát và audit lỗi schema mà không rò rỉ token

Một introspection response có thể chứa tên user, OAuth client ID, scopes, tenant, role, token identifier và những trường nhạy cảm khác. **Không log toàn bộ response** khi parse lỗi để “có dữ liệu debug”.

### 14.1. Các nhóm metric hữu ích

Ví dụ tên metric do ứng dụng tự định nghĩa:

| Metric / event | Ý nghĩa |
|---|---|
| `introspection_request_total{result=...}` | Phân biệt success, inactive, HTTP error, timeout, schema error. |
| `introspection_response_schema_error_total{field=...}` | Thiếu `active`, sai kiểu `scope`, sai `aud`... dùng **nhãn cố định**. |
| `introspection_dependency_failure_total{status=...}` | Lỗi 401/403/429/5xx hoặc TLS/network. |
| `opaque_authentication_failure_total{reason=...}` | Token không được chấp nhận; nguyên nhân mã hóa chuẩn. |
| `opaque_authorization_failure_total{reason=...}` | Thiếu scope, tenant/owner denial. |
| `introspection_duration_seconds` | p95/p99 của round-trip đến AS. |
| `introspection_cache_hit_total` | Nếu có cache; phải biết semantics và TTL. |

**Không dùng** token, `jti`, `sub` hoặc response body làm label metric; cardinality và quyền riêng tư đều có thể trở thành vấn đề. Với logs, dùng request correlation ID và tên lỗi cố định:

```text
event=introspection_response_rejected
reason=active_wrong_type
issuer_config_id=orders-auth
http_status=200
correlation_id=<request-id>
```

Không thêm raw token hoặc client secret vào bản ghi đó.

### 14.2. Fail closed nhưng vẫn phân loại được sự cố

Một cách thiết kế là lưu các lý do nội bộ an toàn:

```text
TOKEN_INACTIVE
INTROSPECTION_SCHEMA_INVALID
INTROSPECTION_REQUIRED_CLAIM_MISSING
INTROSPECTION_CLAIM_TYPE_INVALID
INTROSPECTION_AUDIENCE_MISMATCH
INTROSPECTION_ISSUER_MISMATCH
INTROSPECTION_EXPIRED_METADATA
INTROSPECTION_CLIENT_UNAUTHORIZED
INTROSPECTION_UPSTREAM_UNAVAILABLE
SCOPE_INSUFFICIENT
OBJECT_ACCESS_DENIED
```

Các lý do này dành cho logging/monitoring có kiểm soát. Response trả client không nên phơi bày chi tiết như “token thuộc Bob ở tenant B”, danh sách scopes nhạy cảm, client secret hay JSON body AS.

---

## 15. Runbook khi AS bắt đầu trả response sai schema

Giả sử ngay sau một bản nâng cấp Identity Provider, API tăng 401/5xx và log nội bộ cho thấy `INTROSPECTION_CLAIM_TYPE_INVALID`.

**Bước 1 — Phân loại trước khi thay đổi code.** Xác định token inactive hay response malformed, introspection client credential lỗi, hay chỉ đơn giản scope không đủ. Nhìn HTTP status từ AS và metric reason; không cần in raw token.

**Bước 2 — Kiểm tra hợp đồng đang áp dụng.** `active` có đúng boolean không? Trường nào thay kiểu? Ví dụ `aud` từ string sang string array có thể vẫn thuộc các dạng được RFC hỗ trợ; `scope` từ string sang object là thay đổi đáng kể. Phân biệt protocol rule với contract của API.

**Bước 3 — Kiểm chứng nguồn response.** Bảo đảm không bị trỏ sai realm/tenant, proxy biến đổi body, redirect sang endpoint khác hoặc kết nối TLS hỏng. Không đổi endpoint theo thông tin nằm trong token.

**Bước 4 — Giữ fail-closed.** Không thay `active="true"` thành true một cách im lặng, không bỏ audience/issuer check, không bật `permitAll()`. Nếu bug AS gây gián đoạn, ưu tiên rollback/fix AS hoặc triển khai migration đã được review.

**Bước 5 — Tái tạo bằng test.** Lưu một **fixture được biên tập loại PII/secret** với schema đại diện, tái tạo unit/integration test cho lỗi. Đừng commit một raw response có dữ liệu user/token production.

**Bước 6 — Thống nhất contract mới nếu chủ động thay đổi.** Nếu AS chính thức đổi `scp` thành array hoặc thêm trường tenant, cập nhật parser/profile có version, test grant user/service và audience khác.

**Bước 7 — Kiểm tra quyền thực tế.** Token active đủ quyền route không được truy cập dữ liệu của user/tenant khác. Test cả dữ liệu danh sách, export và bulk.

**Bước 8 — Kiểm tra cache.** Nếu cache introspection, phải biết instance nào còn response schema cũ. Hạn chế xóa cache đồng loạt khi AS đang outage vì có thể tăng tải. Với token bị revoke, cache invalidation phải đáp ứng chính sách.

**Bước 9 — Quan sát sau khôi phục.** Theo dõi error reasons, p95 introspection, 401/403, AS request rate và phân bố theo pod/region. Xác nhận không phát sinh authorities mới ngoài danh sách đã phê duyệt.

**Bước 10 — Cập nhật tài liệu.** Ghi rõ phiên bản AS, các trường bắt buộc theo API, kiểu dữ liệu, cách xử lý thiếu/sai, HTTP error mapping và quy trình rollback.

---

## 16. Checklist để thiết kế contract rõ ràng

| Câu hỏi | Quyết định cần có |
|---|---|
| Endpoint nào xác nhận token? | URL cố định, HTTPS, client auth, quyền introspection requester. |
| Dữ liệu nào bắt buộc theo RFC? | JSON object với `active` boolean. |
| Dữ liệu nào bắt buộc theo **API**? | Issuer, audience, subject, expiry, tenant hoặc client tùy profile. |
| Khi `active=false` xử lý thế nào? | Từ chối ngay, không dùng metadata bổ sung. |
| Khi thiếu `active` hoặc sai kiểu? | Schema failure, không ép kiểu, fail closed. |
| Khi thiếu `scope`? | Không tạo scope authority, route cần scope sẽ từ chối; có thể từ chối token nếu contract bắt buộc. |
| `aud` có thể là string hoặc array không? | Có theo RFC, nhưng parser phải kiểm tra đúng từng phần tử. |
| `exp`/`nbf` dùng đơn vị nào? | NumericDate giây; policy skew và tuổi tối đa. |
| Claims custom có được ánh xạ thành quyền không? | Chỉ với issuer/profile đã thỏa thuận và allowlist. |
| Lỗi schema và lỗi mạng có được retry không? | Phân loại riêng; retry hữu hạn chỉ cho transient upstream. |
| HTTP status client nhận là gì? | Mapping authentication/authorization/dependency đã thiết kế và test. |
| Cache introspection có gây chậm revoke không? | Có TTL/invalidate rõ ràng, không vượt expiry. |
| Có test từ chối token của API/tenant khác không? | Bắt buộc với môi trường đa resource/tenant. |
| Có test duplicate `active` và wrong-type không? | Tại raw parser nếu policy yêu cầu. |
| Log có lộ token/secret/PII không? | Đã mask và dùng reason code/metric labels cố định. |

## 17. Phân biệt ba kết quả cuối cùng

Từ góc nhìn client của `orders-api`, ba tình huống trông có thể gần giống nhau nhưng bản chất khác hẳn:

```text
(1) Introspection:
    HTTP 200 + {"active": false}
    → token không được chấp nhận
    → authentication failure (thường 401)

(2) Introspection:
    HTTP 200 + {"active": true, "scope": "orders:read", ...}
    → token hợp lệ theo contract
    → POST /api/orders đòi SCOPE_orders:write
    → authorization failure (thường 403)

(3) Introspection:
    HTTP 200 + {"active": "true"}
    → sai cấu trúc RFC 7662
    → integration/protocol error; không tạo principal
    → mã HTTP trả client phụ thuộc error handler;
      không được thực thi API bảo vệ
```

Và tình huống thứ tư:

```text
(4) Introspection:
    HTTP 200 + {"active": true, "scope": "orders:read", ...}
    → token đúng, scope đúng
    → Alice yêu cầu xem đơn của Bob
    → object-level authorization từ chối 403/404
```

Cả bốn tình huống đều có thể phát sinh trong một Resource Server duy nhất. **Một parser an toàn không thay thế scope policy; một scope policy đúng không thay thế quyền sở hữu tài nguyên.**

---

## 18. Tài liệu tham khảo kỹ thuật

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): request/response, `active`, metadata tùy chọn, client authentication và bảo mật endpoint.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): OAuth client authentication, `scope` và ngữ nghĩa access token.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): Bearer token và lỗi resource access.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519.html): `iss`, `aud`, `sub` và NumericDate.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): hợp đồng access token JWT để đối chiếu với introspection.
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259.html): JSON values, object member names và rủi ro duplicate members.
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): `OpaqueTokenIntrospector`, authorities và custom introspection.
- [Spring Security API — OpaqueTokenIntrospector](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html): giao diện và phương thức `introspect(...)`.
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): áp dụng scope/authority sau authentication.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): phân quyền trên đúng tài nguyên sau khi token được xác minh.

**Kết luận:** Khi tùy chỉnh introspection trong Spring Security, nên xử lý theo nguyên tắc **kiểm tra giao thức trước, kiểm tra hợp đồng issuer/resource sau, rồi mới tạo principal và authorities**. `active` phải là boolean thật; metadata tùy chọn chỉ trở thành bắt buộc khi chính sách API quy định; response thiếu/sai kiểu phải được từ chối hoặc không tạo quyền, tuyệt đối không được ép kiểu để biến dữ liệu mơ hồ thành authentication hợp lệ.
