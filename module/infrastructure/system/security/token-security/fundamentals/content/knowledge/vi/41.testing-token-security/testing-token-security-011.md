# Test malformed claim

Một access token có thể được ký đúng nhưng vẫn chứa claim sai kiểu, thiếu trường bắt buộc, giá trị không hợp lệ hoặc mâu thuẫn với chính sách của API. Ví dụ `exp` là chuỗi thay vì NumericDate, `aud` trỏ tới service khác, `scope` là mảng không đúng profile, hoặc claim tenant không khớp với tài nguyên. Nếu resource server chỉ kiểm tra chữ ký rồi tin mọi claim, token có thể được chấp nhận sai mục đích.

Bài **Test malformed claim** thuộc chương **Testing token security** của mô-đun **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung gắn với mô hình tin cậy và vòng đời token: phân biệt JWT, opaque token, access token, refresh token; hiểu cách phát hành và xác minh claims, scope, audience, lưu trữ, thu hồi và phòng chống token bị đánh cắp hoặc phát lại trong OAuth 2.0/OIDC.

Sau bài này, bạn có thể:

- Phân biệt token sai cấu trúc, token sai chữ ký và token có claim sai ngữ nghĩa.
- Tạo bộ test âm tính cho registered claims và custom claims.
- Kiểm tra kiểu dữ liệu, trường bắt buộc, giới hạn thời gian, audience, scope và tenant binding.
- Kiểm thử JWT bằng chữ ký hợp lệ để cô lập lỗi claim khỏi lỗi chữ ký.
- Kiểm tra phản hồi introspection của opaque token và cách resource server xử lý dữ liệu thiếu/sai kiểu.
- Phân biệt lỗi xác thực token (thường là 401) với token hợp lệ nhưng thiếu quyền (thường là 403).
- Bảo đảm parser, cache và middleware không biến claim lỗi thành quyền mặc định.

## 1. “Malformed claim” là gì?

**Claim** là một thành phần dữ liệu trong payload JWT, hoặc thuộc tính do Authorization Server (AS) cung cấp khi introspection một opaque token. Claim có thể là registered claim như `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti`, hoặc custom claim như `tenant_id`, `roles`, `client_id`, `cnf`.

Một claim bị xem là malformed khi không đáp ứng cú pháp, kiểu dữ liệu, điều kiện giá trị hoặc hợp đồng bảo mật mà token profile/resource server yêu cầu.

| Nhóm lỗi | Ví dụ | Vì sao phải từ chối? |
|---|---|---|
| **Thiếu claim bắt buộc** | Không có `iss` hoặc `exp` trong profile yêu cầu | Không đủ dữ liệu để xác định nguồn hoặc thời hạn |
| **Sai kiểu dữ liệu** | `exp: "1795509000"` thay vì JSON number | Validator có thể hiểu sai hoặc bỏ qua kiểm tra thời gian |
| **Sai hình dạng** | `aud: {"api":"orders"}` thay vì string/array string | Không thể xác định recipient theo profile |
| **Giá trị không hợp lệ** | `iss: ""`, `aud: []`, `scope: "   "` | Không biểu đạt được trust context hoặc quyền hợp lệ |
| **Ngoài giới hạn** | `exp` quá xa trong tương lai, `scope` quá dài | Có thể phá policy hoặc gây DoS |
| **Sai ngữ nghĩa** | `aud` không chứa API hiện tại | Token không dành cho resource server |
| **Mâu thuẫn giữa claims** | `tenant_id=tenant-a` nhưng resource thuộc tenant-b | Có nguy cơ cross-tenant access |
| **Dữ liệu mơ hồ** | JSON có key `aud` lặp lại | Parser khác nhau có thể chọn giá trị khác nhau |
| **Claim bị giả mạo** | Client gửi `X-Role: admin` rồi middleware dùng làm claim | Dữ liệu không đến từ issuer tin cậy |

Không phải mọi claim không được API sử dụng đều là malformed. Một JWT có thể chứa custom claim lạ mà profile cho phép. Cần phân biệt **claim không biết/không dùng** với **claim bắt buộc nhưng sai hoặc vi phạm policy**. Với dữ liệu ảnh hưởng xác thực và phân quyền, không được tự đặt giá trị mặc định có lợi khi claim thiếu hoặc sai kiểu.

## 2. Tách ba lớp kiểm tra token

Một bộ test tốt phải phân biệt lỗi cấu trúc, lỗi mật mã và lỗi claim:

1. **Token/serialization:** header hoặc payload không phải Base64URL hợp lệ, số phần không đúng, JSON hỏng, payload không phải object JSON hoặc chữ ký thiếu.
2. **Cryptographic validation:** chữ ký sai, khóa không tin cậy, thuật toán ngoài allowlist, `kid` không thuộc JWKS của issuer hoặc token bị sửa sau khi ký.
3. **Claims and authorization:** token có chữ ký hợp lệ nhưng `iss`, `aud`, `exp`, `nbf`, `scope`, `sub`, `client_id`, tenant hoặc claim nghiệp vụ không đáp ứng profile/policy.

Ví dụ cần phân biệt:

| Fixture | Chữ ký | Claim | Mục tiêu kiểm thử |
|---|---|---|---|
| JWT bị sửa một byte sau khi ký | Sai | Có thể vẫn đúng cú pháp | Kiểm tra chữ ký |
| JWT ký bằng test key tin cậy, `aud=other-api` | Đúng | Sai audience | Kiểm tra audience validator |
| JWT ký đúng, `exp` là string | Đúng | Sai kiểu NumericDate | Kiểm tra strict claim parser |
| Payload không phải JSON nhưng JWS signature đúng với payload bytes | Đúng | Không parse được | Kiểm tra parser/serialization |
| JWT đúng claims và chữ ký nhưng thiếu `orders:write` | Đúng | Token hợp lệ, quyền thiếu | Kiểm tra authorization (403) |

**Để test malformed claim, hãy tạo token bằng test key được validator tin cậy và ký payload có claim sai.** Nếu chỉ sửa payload sau khi ký, chữ ký sẽ hỏng; test đó chỉ chứng minh signature validation, chưa chứng minh claim validator từ chối dữ liệu sai.

Với test claim parser độc lập, có thể đưa trực tiếp object claims vào validator unit test. Nhưng cần thêm integration test đi qua decoder thật để chứng minh token có chữ ký hợp lệ nhưng claim sai vẫn bị chặn.

## 3. Các claim cần kiểm thử

Kiểu và tính bắt buộc phụ thuộc token profile, chẳng hạn JWT access token theo RFC 9068, hợp đồng AS và policy API. Bảng dưới mô tả các kiểm tra thường cần cho resource server.

| Claim | Kiểu/điều kiện thường dùng | Test malformed tiêu biểu |
|---|---|---|
| `iss` | String, khớp chính xác issuer tin cậy | Thiếu, null, number, empty, issuer gần giống |
| `sub` | String theo profile, định danh chủ thể | Thiếu nếu profile bắt buộc, null, object, empty |
| `aud` | String hoặc array các string theo JWT; phải chứa audience API | Number, object, array rỗng, phần tử không phải string, sai API |
| `exp` | NumericDate dạng JSON number; thời điểm hết hạn | String, boolean, null, object, NaN/Infinity không hợp lệ, quá hạn |
| `nbf` | NumericDate nếu có; không dùng trước mốc này | String, object, tương lai quá xa |
| `iat` | NumericDate theo profile; thời điểm phát hành | String, boolean, tương lai bất hợp lý |
| `jti` | String định danh token khi profile/policy yêu cầu | Object, array, empty hoặc trùng trong cơ chế chống replay |
| `client_id` | String theo access-token profile/hợp đồng AS | Thiếu, number, empty, client không được phép |
| `scope` | Thường là string gồm các scope phân tách bằng khoảng trắng theo profile | Array/object, chuỗi quá dài, phần tử sai cú pháp, whitespace bất thường |
| `tenant_id` | Custom claim; thường là string canonical theo hợp đồng | Thiếu, null, array, tenant không được phép hoặc mismatch |
| `cnf` | Object theo sender-constrained token profile | Sai cấu trúc key/certificate thumbprint, thiếu thành phần bắt buộc |

Không nên áp dụng máy móc mọi cột “thường dùng” cho mọi loại token. Ví dụ ID token OIDC và access token có profile, audience và mục đích khác nhau. Resource server phải xác định rõ **chỉ nhận access token phù hợp**, không nhận ID token chỉ vì nó là JWT có chữ ký hợp lệ.

### 3.1. Issuer

Issuer phải thuộc danh sách trust configuration của resource server. Các test nên bao gồm:

- Claim bị thiếu, null, number, array hoặc chuỗi rỗng.
- Issuer đúng và issuer khác.
- Chuỗi gần giống nhưng khác host, scheme, port, path hoặc dấu slash cuối.
- Issuer có Unicode/confusable hoặc encoding bất thường nếu hệ thống có nguy cơ canonicalization khác nhau.
- Token từ issuer A nhưng validator vô tình dùng JWKS của issuer B.

So sánh issuer theo quy tắc của token profile/hệ thống; không tự lower-case, bỏ path hoặc chuẩn hóa URL tùy tiện để “làm cho khớp”. Không tải khóa từ URL tùy ý do token cung cấp.

### 3.2. Audience

Audience có thể là một string hoặc danh sách string theo JWT. API phải xác minh audience của chính nó bằng phép so khớp phần tử chính xác:

```json
{
  "aud": ["orders-api", "reports-api"]
}
```

Nếu request đến `orders-api`, token trên có thể đạt audience check nếu các kiểm tra khác đều hợp lệ. Các test âm tính:

```text
{"aud": "other-api"}
{"aud": []}
{"aud": ["orders-api-evil"]}
{"aud": ["orders-api", 42]}
{"aud": {"name": "orders-api"}}
{"aud": null}
```

Không kiểm tra bằng `contains("orders-api")` trên một chuỗi JSON chưa parse; `orders-api-evil` không phải `orders-api`. Không coi `aud` bị thiếu là audience mặc định của gateway.

### 3.3. Thời gian: exp, nbf, iat

JWT NumericDate là số giây từ Unix epoch theo quy định JWT. Với profile yêu cầu các claim thời gian:

- `exp` phải là kiểu số được parser/profile chấp nhận; từ chối string, boolean, null hoặc object.
- `nbf` không được ở tương lai vượt giới hạn policy.
- `iat` không nên vượt quá thời gian hiện tại ngoài clock skew cho phép; có thể kiểm tra tuổi tối đa của token.
- Kiểm tra biên `now == exp`, `now == nbf`, token vừa hết hạn và sai lệch đồng hồ.
- Giới hạn thời gian sống tối đa để tránh token có hiệu lực quá lâu do lỗi AS hoặc cấu hình.

Ví dụ test:

```text
{"exp": "1795509000"}
{"exp": true}
{"exp": null}
{"exp": {"seconds": 1795509000}}
{"nbf": "1795500000"}
{"iat": 999999999999999999999999}
```

Không tự ép chuỗi thành số để chấp nhận token nếu profile yêu cầu JSON number. Không cho `exp` thiếu biến token thành vô hạn. Leeway/clock skew phải nhỏ, được cấu hình rõ và áp dụng nhất quán; không dùng cache để kéo dài token quá hạn.

### 3.4. Scope

Với JWT access token theo profile RFC 9068, `scope` thường được biểu diễn dưới dạng string. Test cần xác minh:

- Kiểu dữ liệu đúng theo profile; nếu là string, parse thành tập scope theo delimiter quy định.
- Không có scope rỗng hoặc scope chỉ gồm whitespace nếu policy yêu cầu scope.
- So khớp phần tử chính xác, không dùng substring.
- Không tự nâng quyền khi scope thiếu, null, array hoặc sai định dạng.
- Scope được kiểm tra theo HTTP method + route/action; `orders:read` không cho phép `POST /orders`.
- Scope không thay thế tenant, owner hoặc business authorization.

Ví dụ `orders:read-extra` không được tính là `orders:read`; `orders:read orders:write` có hai phần tử quyền riêng.

### 3.5. Custom claims

Custom claims cần schema và trust contract rõ ràng:

| Claim | Kiểm tra gợi ý |
|---|---|
| `tenant_id` | String canonical, tenant đang hoạt động, khớp tenant của resource |
| `tenant_ids` | Array string theo schema, giới hạn số lượng, mọi tenant đều thuộc tập được cấp |
| `roles` | Kiểu đúng theo profile, role được issuer tin cậy cấp, không lấy từ header |
| `client_id` | String và đúng client được policy cho phép |
| `act` | Cấu trúc actor đúng profile delegation, xác minh nguồn và quan hệ subject/actor |
| `cnf` | Cấu trúc proof-of-possession đúng mTLS/DPoP profile |

Không biến claim không tồn tại thành role mặc định `admin`, tenant mặc định từ header, hoặc scope mặc định có quyền ghi. Nếu custom claim không bắt buộc thì có thể bỏ qua; nếu bắt buộc để ra quyết định an ninh, thiếu/sai kiểu phải bị từ chối.

## 4. Kiểm thử JSON parser và claim ambiguity

JWT payload thường là JSON. Ngoài kiểm tra schema, cần kiểm thử parser:

- JSON không hợp lệ: thiếu dấu ngoặc, dấu phẩy thừa, string không đóng, escape sai.
- Payload là array, number, string hoặc `null` thay vì JSON object khi profile yêu cầu object.
- Duplicate member name, ví dụ hai trường `aud` với giá trị khác nhau.
- Nested object/array sai cấu trúc.
- Number cực lớn, số âm hoặc giá trị gây overflow khi chuyển kiểu.
- Unicode, ký tự null, ký tự điều khiển và tên claim tương tự nhưng khác ký tự.
- Header/payload có encoding bất thường hoặc token vượt giới hạn kích thước.

Với JSON member trùng tên, parser có thể có hành vi khác nhau nếu không được cấu hình chặt. Hãy đặt policy rõ (ưu tiên từ chối duplicate member) và kiểm thử decoder, gateway và backend không diễn giải token theo hai cách khác nhau. Không để một lớp lấy giá trị đầu tiên còn lớp khác lấy giá trị cuối cùng.

Ví dụ payload malformed:

```text
{"iss":"https://id.example.com","aud":"orders-api",}
{"iss":"https://id.example.com","aud":"orders-api"
{"iss":"https://id.example.com","aud":["orders-api"],"aud":["admin-api"]}
["iss","https://id.example.com"]
null
```

Các payload này phải bị parser/validator từ chối trước khi claims được dùng để cấp quyền. Nếu test tạo JWS ký trên raw payload bytes, chữ ký vẫn có thể hợp lệ về mặt mật mã; điều đó không làm JSON malformed trở thành dữ liệu claim hợp lệ.

## 5. Thiết kế test fixture đúng mục tiêu

### 5.1. Một token hợp lệ làm baseline

Tạo fixture chuẩn từ test AS/key pair:

```json
{
  "iss": "https://id.example.test",
  "sub": "user-42",
  "aud": ["orders-api"],
  "client_id": "web-bff",
  "scope": "orders:read",
  "iat": 1795507200,
  "exp": 1795507500,
  "jti": "test-token-001"
}
```

Đây là payload minh họa; fixture thực tế phải được ký bằng khóa test mà decoder tin cậy. Lưu private key test trong test resources, không dùng khóa production. Baseline phải đi qua toàn bộ decoder/validator và được chấp nhận trong test môi trường.

### 5.2. Biến đổi từng claim một

Để xác định lỗi nào được bắt, thay đổi **một yếu tố mỗi test**:

```text
validClaims -> sign(testKey) -> decoder -> validator -> endpoint

test_wrong_audience:
  claims = validClaims with aud = ["billing-api"]
  sign(testKey)
  expect token rejected

test_string_exp:
  claims = validClaims with exp = "1795507500"
  sign(testKey)
  expect token rejected
```

Khi kiểm tra tương tác giữa nhiều claim, tạo thêm test tổ hợp có chủ đích. Nếu thay đồng thời issuer, audience và expiry trong một test, kết quả chỉ cho biết token bị từ chối, không cho biết validator nào bắt lỗi.

### 5.3. Phân biệt unit test và integration test

| Loại test | Cách tạo input | Chứng minh điều gì? | Không chứng minh điều gì? |
|---|---|---|---|
| Claim validator unit test | Map/object claims trực tiếp | Logic schema, kiểu và policy claim | Decoder có xác minh chữ ký hay không |
| Authorization unit test | Principal/authorities giả lập | Scope/action mapping, 403 khi thiếu quyền | JWT raw có malformed hay không |
| Decoder integration test | JWT ký bằng test key, gọi decoder thật | Signature + parse + claim validator | Toàn bộ luồng HTTP/gateway |
| API integration test | Gửi Bearer JWT qua endpoint thật | Hành vi 401/403 và không có side effect | Toàn bộ production topology |
| Opaque introspection test | Mock/contract AS introspection response | Xử lý active, audience, scope, expiry và schema | JWT decoder |
| End-to-end security test | AS test thật + API + cache | Luồng phát hành, thu hồi, audience, scope và tích hợp | Mọi lỗi có thể xảy ra trong production |

Nếu dùng Spring Security test helper như `jwt()` để tạo `JwtAuthenticationToken`, helper thường dựng principal đã xác thực ở tầng test; nó **không đi qua** chữ ký/JWT decoder thật. Dùng nó cho authorization rule và viết integration test riêng để kiểm tra malformed claims qua decoder.

## 6. Test opaque token và introspection response

Opaque token không mang claims để resource server tự giải mã. API/gateway hỏi endpoint introspection của AS và nhận response. Vì vậy cần kiểm thử **cả token đầu vào lẫn schema response**:

```json
{
  "active": true,
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "exp": 1795507500,
  "client_id": "web-bff"
}
```

Các test âm tính:

| Response introspection | Kỳ vọng |
|---|---|
| `active: false` | Từ chối token |
| Thiếu `active` | Không tự coi là active |
| `active: "true"` | Từ chối sai kiểu boolean |
| `active: 1` | Từ chối nếu contract yêu cầu boolean |
| `aud` sai kiểu/thiếu audience API | Từ chối |
| `scope` sai kiểu hoặc thiếu scope cần thiết | Không cấp quyền |
| `exp` string/null/đã quá hạn | Từ chối theo schema/lifetime |
| `tenant_id` không khớp tài nguyên | Từ chối cross-tenant |
| Response không phải JSON hoặc bị cắt | Từ chối, không cache kết quả hợp lệ |
| AS timeout/5xx | Fail closed với request chưa có trạng thái tin cậy |

Introspection endpoint phải được gọi qua HTTPS và xác thực resource server theo cấu hình AS. Không chấp nhận response từ host do token hoặc client chỉ định. Không cache `active=true` nếu response malformed, thiếu claim thiết yếu hoặc AS có chỉ thị không cache. Cache hit không thay thế kiểm tra `exp`, audience, scope và quyền tài nguyên ở request hiện tại.

## 7. Ví dụ test trong Java/Spring Security

### 7.1. Authorization test cho scope

Ví dụ Servlet endpoint `GET /orders` yêu cầu authority `SCOPE_orders:read`. Spring Security test có thể dựng JWT principal để kiểm tra policy:

```java
@Test
void rejectsRequestWithoutReadScope() throws Exception {
    mockMvc.perform(get("/orders")
            .with(jwt().jwt(jwt -> jwt
                .claim("sub", "user-42")
                .claim("aud", List.of("orders-api"))
                .claim("scope", "orders:write"))))
        .andExpect(status().isForbidden());
}
```

Đoạn test này kiểm tra **authorization mapping** trong filter chain. Vì helper `jwt()` tạo authentication cho test, không dùng test này để tuyên bố decoder đã từ chối JWT có chữ ký sai hoặc `exp` sai kiểu.

### 7.2. Integration test qua decoder thật

Để kiểm tra malformed claim, hãy ký fixture bằng private key test tương ứng với public key/JWKS mà decoder test tin cậy:

```java
@Test
void rejectsSignedJwtWithStringExpiration() throws Exception {
    String token = testJwtSigner.sign(Map.of(
        "iss", "https://id.example.test",
        "sub", "user-42",
        "aud", List.of("orders-api"),
        "client_id", "web-bff",
        "scope", "orders:read",
        "iat", 1795507200,
        "exp", "1795507500",
        "jti", "malformed-exp"
    ));

    mockMvc.perform(get("/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());
}
```

`testJwtSigner` là helper giả định của test suite, phải tạo JWS có chữ ký hợp lệ với test key và giữ nguyên kiểu claim trong payload. Nhiều builder JWT có thể tự chuyển đổi hoặc từ chối giá trị sai kiểu; khi đó cần tạo raw payload fixture và ký đúng bytes để test parser/validator thực sự.

Ví dụ test audience:

```java
@Test
void rejectsSignedJwtForDifferentAudience() throws Exception {
    String token = testJwtSigner.sign(validClaims()
        .with("aud", List.of("billing-api")));

    mockMvc.perform(get("/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());
}
```

Ví dụ trên cũng là pseudocode ở phần `validClaims()`/`with()`; API thực tế tùy test fixture builder. Điều quan trọng là JWT phải được ký bằng test key tin cậy, sau đó đi qua **decoder và audience validator thật**.

### 7.3. Kiểm tra không có side effect

Với request tạo đơn hoặc charge, không chỉ assert status:

```java
@Test
void malformedClaimMustNotCreateOrder() throws Exception {
    String token = signedTokenWithMalformedTenantClaim();

    mockMvc.perform(post("/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .contentType(MediaType.APPLICATION_JSON)
            .content(validOrderRequest()))
        .andExpect(status().isUnauthorized());

    verify(orderRepository, never()).save(any());
}
```

Đây là test minh họa: repository/service mock phải được cấu hình trong test context. Với hành động tài chính hoặc thay đổi dữ liệu, cần xác minh không có message, transaction, event hoặc external call nào được phát ra khi token/claim không hợp lệ.

## 8. Test malformed claim theo ma trận

Một bộ test nên có baseline token hợp lệ, sau đó lần lượt thay đổi từng claim:

| ID | Biến thể | Kỳ vọng tại API bảo vệ |
|---|---|---|
| C01 | Token chuẩn, issuer/audience/expiry/scope hợp lệ | 2xx nếu quyền tài nguyên đạt |
| C02 | Thiếu `iss` | 401 |
| C03 | `iss` là number hoặc empty | 401 |
| C04 | `iss` là issuer không tin cậy | 401 |
| C05 | Thiếu `aud` | 401 nếu profile yêu cầu |
| C06 | `aud` là object/number/null | 401 |
| C07 | `aud` không chứa API hiện tại | 401 |
| C08 | `aud` có phần tử không phải string | 401 |
| C09 | Thiếu `exp` trong profile bắt buộc | 401 |
| C10 | `exp` là string/boolean/object | 401 |
| C11 | `exp` đã qua hoặc sát biên theo leeway | 401 khi hết hạn |
| C12 | `nbf` là string hoặc nằm quá xa trong tương lai | 401 |
| C13 | `iat` sai kiểu hoặc vượt giới hạn tuổi token | 401 theo validator |
| C14 | `sub` sai kiểu/empty khi profile yêu cầu | 401 |
| C15 | `client_id` sai kiểu hoặc client bị cấm | 401/403 theo contract |
| C16 | `scope` là array/object thay vì string theo profile | 401 |
| C17 | Scope hợp lệ nhưng thiếu action cần thiết | 403 |
| C18 | Scope có chuỗi gần giống, không có exact member | 403 |
| C19 | `tenant_id` là array/null hoặc mismatch | 401/403 theo token contract, không trả dữ liệu |
| C20 | JSON payload có duplicate claim name | Từ chối theo parser policy nghiêm ngặt |
| C21 | Payload JSON malformed nhưng JWS bytes ký hợp lệ | 401 |
| C22 | Chữ ký bị sửa sau khi ký | 401 |
| C23 | `kid` không có trong JWKS tin cậy | 401; refresh JWKS có giới hạn nếu policy cho phép |
| C24 | `typ` không phải access-token type theo profile | 401 |
| C25 | Token đúng claim nhưng là ID token/refresh token | 401 |
| C26 | Introspection `active` sai kiểu hoặc thiếu | 401 |
| C27 | Introspection `active=true` nhưng thiếu audience/scope thiết yếu | Từ chối theo contract; không cấp quyền |
| C28 | AS timeout hoặc response bị cắt | 401/503 theo API contract, không fail open |

Mã trạng thái cụ thể có thể khác theo API contract, nhưng phải giữ ranh giới: **token không được xác thực/không đáp ứng profile** không được xem là principal hợp lệ; **token hợp lệ nhưng thiếu quyền action** mới là trường hợp authorization từ chối. Không tiết lộ chi tiết nội bộ của claim nào sai cho client nếu điều đó làm lộ cấu trúc token hoặc policy.

## 9. Kiểm thử parser, decoder và middleware trong điều kiện biên

### 9.1. Duplicate claims và parser differential

Một payload có:

```json
{
  "aud": ["orders-api"],
  "aud": ["admin-api"]
}
```

có thể được xử lý khác nhau bởi thư viện JSON khác nhau. Test cần xác định decoder từ chối duplicate member hoặc có chính sách nhất quán theo tiêu chuẩn/profile. Quan trọng là gateway và backend không được dùng hai cách parse khác nhau khiến gateway cho qua nhưng backend tin audience khác (hoặc ngược lại).

### 9.2. Kích thước và tài nguyên

Test các trường hợp:

- JWT header/payload vượt giới hạn kích thước được cấu hình.
- Scope string hoặc mảng tenant quá dài.
- JSON nesting quá sâu, array có quá nhiều phần tử.
- NumericDate cực lớn, âm hoặc gây overflow.
- Nhiều claim lạ/claim gần giống được thêm để gây tải parser.
- Nhiều request cùng `kid` không tồn tại gây refresh JWKS liên tục.

Từ chối dữ liệu vượt giới hạn trước khi tiêu tốn tài nguyên không cần thiết. Không ghi toàn bộ payload vào log khi parser lỗi.

### 9.3. Claim normalization

Không tự ý chuẩn hóa claim an ninh theo kiểu:

- Lowercase issuer hoặc tenant ID nếu hệ thống coi chúng phân biệt.
- Trim scope rồi chấp nhận chuỗi rỗng hoặc delimiter lạ mà không theo profile.
- Convert string `"true"` thành boolean `true`.
- Convert string timestamp thành number.
- Thay claim thiếu bằng giá trị từ header/query.

Nếu hợp đồng yêu cầu canonicalization, phải định nghĩa một lần và dùng thống nhất ở AS, gateway, resource server và cache. Test cả input đã canonical và input khác biệt về encoding/case/Unicode.

### 9.4. Cache và thời điểm thu hồi

Khi validator đã từ chối claim malformed, không cache kết quả thành `ALLOW`. Với introspection, không cache response lỗi hoặc response thiếu trường thiết yếu. Với JWT, cache JWKS không thay thế kiểm tra claim theo từng request; cache validation result phải có key gắn với issuer, token fingerprint, audience/profile và expiry tuyệt đối.

Test:

- Token `exp` vừa qua nhưng JWKS cache còn hạn.
- Token opaque bị thu hồi sau khi cache `active=true`.
- Claim tenant/policy thay đổi nhưng cache key thiếu tenant/version.
- Decoder validator config thay đổi nhưng cache cũ chưa invalidated.
- Một token malformed được gửi lặp lại nhiều lần để đo parser/AS load và rate limit.

## 10. Quy trình xử lý lỗi và quan sát

Khi claim malformed:

1. Dừng xác thực trước khi tạo principal đáng tin.
2. Không gọi service nghiệp vụ, không phát event, không thực hiện side effect.
3. Trả lỗi phù hợp, thường 401 cho token không hợp lệ; 403 cho token hợp lệ nhưng thiếu quyền.
4. Ghi log có kiểm soát: route ID, issuer đã cấu hình, loại validator, mã lỗi nội bộ, correlation ID và kết quả; **không log bearer token hoặc toàn bộ claims nhạy cảm**.
5. Theo dõi số lượng lỗi theo nhóm (wrong issuer, wrong audience, invalid time, malformed JSON, missing scope) mà không đưa token/subject nhạy cảm vào metric label.
6. Cảnh báo khi tăng đột biến malformed token, unknown `kid`, invalid signature hoặc introspection failure; có thể là lỗi client, cấu hình sai hoặc hoạt động dò quét.

Ví dụ log an toàn:

```json
{
  "event": "access_token_rejected",
  "route": "orders-read",
  "reason_code": "INVALID_AUDIENCE",
  "issuer_config": "company-idp",
  "request_id": "req-8321",
  "decision": "deny"
}
```

Không ghi `Authorization`, token raw, refresh token, private key hoặc payload có PII. Nếu cần tương quan token, dùng fingerprint/HMAC nội bộ được quản lý như dữ liệu nhạy cảm và chỉ lưu khi thật sự cần.

## 11. Checklist cho test suite

- Có baseline token hợp lệ được ký bằng test key và được decoder tin cậy.
- Có test tách biệt token serialization, chữ ký, claims và authorization.
- Có negative test cho `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti`, `client_id`, `scope` và custom claims bắt buộc.
- Có test sai kiểu dữ liệu, null, empty, thiếu trường, giá trị quá lớn, duplicate claim và JSON malformed.
- Có test audience exact match, scope exact membership, tenant binding và resource ownership.
- Có test phân biệt access token với ID token/refresh token.
- Có integration test dùng chữ ký hợp lệ nhưng claim malformed; không chỉ dùng mock principal.
- Có opaque token introspection contract test với `active`, expiry, audience, scope và response sai schema.
- Có test 401/403 và xác minh không có side effect khi token không hợp lệ.
- Có test cache, JWKS rotation, revocation, timeout, parser limits và multi-instance consistency.
- Có redaction token trong log/trace/error và metric không chứa bí mật.
- Có regression test cho mọi malformed claim từng được phát hiện trong production.

### Bài tập suy luận

`orders-api` chỉ chấp nhận access token có issuer `https://id.example.test`, audience `orders-api`, `exp` là NumericDate còn hạn và scope `orders:read` khi gọi `GET /orders`.

Token A được ký đúng bởi test key tin cậy nhưng có:

```json
{
  "iss": "https://id.example.test",
  "sub": "user-42",
  "aud": ["orders-api"],
  "exp": "1795507500",
  "scope": "orders:read"
}
```

**Kết quả:** token phải bị từ chối vì `exp` là string, không phải NumericDate theo profile. Chữ ký hợp lệ không sửa được lỗi kiểu claim.

Token B có `exp` đúng kiểu và còn hạn, nhưng `aud=["billing-api"]`. **Kết quả:** từ chối vì token không dành cho `orders-api`.

Token C có issuer, audience và thời hạn hợp lệ nhưng chỉ có `scope=orders:write`. **Kết quả:** token được xác thực nhưng request đọc thiếu quyền, thường trả 403; không được cấp `orders:read` theo mặc định.

Token D có claim `tenant_id=tenant-north` nhưng order cần đọc thuộc `tenant-acme`. **Kết quả:** từ chối theo tenant/resource authorization, không trả dữ liệu chỉ vì scope đọc đúng.

**Nguyên tắc cốt lõi:** *chữ ký xác minh nguồn và tính toàn vẹn của token; claim validator xác minh dữ liệu đúng profile; authorization kiểm tra quyền action; backend kiểm tra quyền trên tài nguyên.* Bộ test malformed claim phải chứng minh từng lớp từ chối đúng, không chỉ chứng minh endpoint trả một mã lỗi.

### Tiêu chuẩn tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
