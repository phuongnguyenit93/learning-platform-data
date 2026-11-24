# Test token hợp lệ và không hợp lệ

## 1. Mục tiêu của việc kiểm thử token

Một hệ thống xác thực và phân quyền an toàn phải nhận đúng token được phát hành cho nó, từ chối token sai hoặc đã mất hiệu lực, đồng thời chỉ cho phép người dùng và dịch vụ thực hiện hành động nằm trong quyền được cấp. Vì vậy, kiểm thử token cần bao phủ cả **tính hợp lệ của token** lẫn **quyền mà token thể hiện**.

Một JWT có thể giải mã được nhưng chữ ký sai. Một JWT có chữ ký đúng vẫn có thể được phát hành cho API khác, đã hết hạn hoặc đến từ issuer không được tin cậy. Một opaque token không thể được xác minh bằng cách đọc payload; resource server phải kiểm tra trạng thái qua cơ chế introspection hoặc kho token đáng tin cậy. Một access token hợp lệ cũng không đảm bảo chủ thể có quyền xóa mọi tài nguyên.

Bài học này hướng dẫn xây dựng bộ kiểm thử cho JWT và opaque token trong OAuth 2.0/OIDC, từ kiểm thử đơn vị đến kiểm thử tích hợp và kiểm thử bảo mật. Sau bài học, người học có thể:

- Phân loại token hợp lệ, không hợp lệ, hết hạn, bị thu hồi và không phù hợp với API.
- Kiểm tra chữ ký, thuật toán, issuer, audience, thời hạn và các claim theo profile của hệ thống.
- Kiểm tra opaque token qua introspection, bao gồm trạng thái active, scope, audience và lỗi kết nối.
- Phân biệt lỗi xác thực token với lỗi thiếu quyền để kiểm tra phản hồi HTTP chính xác.
- Kiểm thử refresh token, thu hồi, rotation, replay và các tình huống sử dụng sai loại token.
- Thiết kế dữ liệu kiểm thử tái lập được mà không dùng token, khóa bí mật hay dữ liệu người dùng thật.

## 2. Xác định hợp đồng bảo mật trước khi viết test

Trước khi tạo test case, cần xác định API đang chấp nhận loại token nào và điều kiện nào làm token hợp lệ. Những điều kiện này phải lấy từ cấu hình và security profile của hệ thống. Không nên suy ra toàn bộ chính sách chỉ từ một ví dụ JWT.

Một hợp đồng kiểm tra thường có các nội dung:

| Nhóm | Câu hỏi cần xác định |
| --- | --- |
| Token type | API nhận access token JWT, opaque token hay cả hai? Có từ chối ID token và refresh token không? |
| Issuer | Những issuer nào được tin cậy? So khớp `iss` chính xác ra sao? |
| Audience | Token phải được cấp cho API hoặc resource nào? |
| Signature | Thuật toán nào được cho phép? Khóa lấy từ nguồn JWKS nào? |
| Time | `exp`, `nbf`, `iat` được kiểm tra thế nào? Clock skew tối đa bao nhiêu? |
| Claims | Claim nào bắt buộc, kiểu dữ liệu và giá trị hợp lệ là gì? |
| Authorization | Scope, role, tenant và quyền trên từng tài nguyên được ánh xạ thế nào? |
| Revocation | Hệ thống kiểm tra thu hồi bằng introspection, denylist, session hay cơ chế khác? |
| Sender constraint | Token có ràng buộc với certificate hoặc DPoP key không? |
| Error contract | Trường hợp nào trả `401`, trường hợp nào trả `403`, có Bearer challenge ra sao? |

Ví dụ, một API đơn hàng có thể quy định access token phải có issuer `https://identity.example.test`, audience `orders-api`, scope `orders.read` hoặc `orders.write`, và thời gian hiệu lực hợp lệ. Đây chỉ là ví dụ về hợp đồng; tên issuer, audience và scope thực tế phải lấy từ cấu hình của ứng dụng.

**Phải tách hai quyết định:**

1. **Authentication:** token có được tin cậy và đại diện cho một chủ thể hợp lệ trong ngữ cảnh API này không?
2. **Authorization:** chủ thể đó có được phép gọi endpoint và thao tác trên tài nguyên cụ thể không?

Một token hợp lệ nhưng thiếu scope thường là lỗi phân quyền. Token sai chữ ký hoặc hết hạn là lỗi xác thực. Test phải phân biệt hai nhóm này để phát hiện trường hợp hệ thống vô tình cấp quyền hoặc trả mã lỗi sai.

## 3. Phân biệt các loại token cần kiểm thử

| Loại token | Mục đích | Cách kiểm tra tại API |
| --- | --- | --- |
| JWT access token | Mang các claim phục vụ xác thực/phân quyền | Xác minh chữ ký, profile, issuer, audience, thời hạn, trạng thái và quyền |
| Opaque access token | Chuỗi tham chiếu đến trạng thái token do AS quản lý | Introspection hoặc tra cứu kho token tin cậy; không tự giải mã chuỗi |
| Refresh token | Dùng tại authorization server để xin access token mới theo refresh grant | Kiểm tra tại token endpoint; resource API thông thường phải từ chối |
| OIDC ID token | Chứng thực kết quả đăng nhập cho OIDC client | Kiểm tra theo OIDC client và audience của client; không dùng thay access token để gọi API |
| Token đã exchange | Access token mới cho resource/actor/ngữ cảnh đích | Kiểm tra như access token theo issuer, audience, scope, actor và ràng buộc của profile |

Không được mặc định token là JWT chỉ vì nó có ba phần phân tách bằng dấu chấm. Không được mặc định token là access token chỉ vì nó có thể giải mã. `token_type=Bearer` mô tả cách trình bày token trong giao thức OAuth; nó không nói token bắt buộc là JWT hay opaque.

## 4. Chuẩn bị dữ liệu kiểm thử an toàn và có thể tái lập

### 4.1. Tạo token test bằng khóa riêng cho môi trường test

Đối với JWT, hãy dùng thư viện JWT/JWS đáng tin cậy để ký token bằng **khóa test riêng**, không tự viết thuật toán mã hóa và không sao chép private key production vào test. Có thể tạo cặp khóa tạm cho từng test suite hoặc dùng fixture khóa test được quản lý trong môi trường CI.

Một test token factory nên cho phép thay đổi có chủ đích từng thuộc tính:

- `iss`: issuer được tin cậy hoặc issuer giả.
- `sub`: subject hợp lệ hoặc subject không tồn tại theo fixture.
- `aud`: đúng API hoặc một API khác.
- `exp`, `nbf`, `iat`: thời điểm trước, tại và sau mốc kiểm thử.
- `scope` / `roles`: đủ quyền, thiếu quyền hoặc có quyền không được hỗ trợ.
- `kid` và khóa ký: khóa hiện hành, khóa cũ còn được chấp nhận, khóa không biết.
- `typ`: loại token theo profile mà API yêu cầu.
- Claim tenant, client hoặc actor theo mô hình của ứng dụng.

Chỉ thay đổi một yếu tố trong từng test âm cơ bản. Ví dụ, khi kiểm tra audience sai, chữ ký, issuer và thời gian vẫn phải hợp lệ. Nhờ vậy, test chứng minh đúng nguyên nhân bị từ chối, tránh trường hợp token bị loại bởi một lỗi khác trước khi tới nhánh cần kiểm tra.

### 4.2. Dùng thời gian cố định

Không phụ thuộc đồng hồ thật trong test. Inject `Clock` hoặc cơ chế thời gian tương đương vào thành phần xác minh để có thể kiểm tra chính xác:

- Token hết hạn một giây trước thời điểm hiện tại.
- Token còn hiệu lực đúng tại ranh giới `exp`, theo quy tắc so sánh của thư viện/profile.
- Token có `nbf` ở tương lai.
- Token có `iat` trong tương lai khi profile của ứng dụng cấm trường hợp đó.
- Clock skew nằm trong giới hạn và vượt giới hạn.

Theo JWT, `exp` là thời điểm sau đó token không được chấp nhận; `nbf` là thời điểm trước đó token chưa được chấp nhận. `iat` cho biết thời điểm phát hành, nhưng việc bắt buộc có mặt và giới hạn tuổi token thường thuộc profile hoặc chính sách ứng dụng. Nếu cho phép clock skew, cần kiểm tra cả trong và ngoài ngưỡng đã công bố.

### 4.3. Fixture cho opaque token

Opaque token test nên được tạo trong authorization server giả lập hoặc kho token test. Chuẩn bị các bản ghi có trạng thái:

- `active=true`, đúng subject, audience và scope.
- `active=false` do hết hạn hoặc bị thu hồi.
- Token không tồn tại.
- Token thuộc client hoặc resource khác.
- Introspection timeout, lỗi xác thực client hoặc trả phản hồi sai schema.

Không cố decode opaque token để lấy claim. API phải dựa vào kết quả introspection đã xác thực và xử lý lỗi theo chính sách fail-closed khi không thể xác minh token.

### 4.4. Không để lộ bí mật trong test

Không dùng access token, refresh token, cookie phiên hoặc private key thật trong mã nguồn, log CI, ảnh chụp màn hình hay báo cáo lỗi. Token test vẫn là dữ liệu nhạy cảm trong phạm vi test: nên dùng giá trị giả, giới hạn quyền truy cập artifact, rút ngắn thời gian lưu và che token trong log. Không ghi toàn bộ `Authorization` header khi test thất bại.

## 5. Bộ test JWT: chữ ký và claim

### 5.1. Chữ ký và thuật toán

| Test case | Dữ liệu tạo ra | Kết quả mong đợi |
| --- | --- | --- |
| Chữ ký hợp lệ | JWT được ký bằng private key tương ứng với public key tin cậy | Chấp nhận nếu mọi điều kiện khác đạt |
| Sai chữ ký | Thay payload hoặc ký bằng khóa khác | Từ chối |
| Chữ ký bị cắt/malformed | Segment hoặc encoding không hợp lệ | Từ chối an toàn |
| Thuật toán không được cho phép | Header khai thuật toán ngoài allowlist | Từ chối |
| `alg=none` | Token không có chữ ký nhưng khai báo không dùng thuật toán | Từ chối với access token yêu cầu chữ ký |
| Sai loại khóa | Dùng khóa đối xứng trong khi profile chỉ cho phép khóa bất đối xứng, hoặc ngược lại | Từ chối |
| `kid` không tồn tại | Header trỏ đến key ID không có trong JWKS tin cậy | Từ chối |
| Key rotation | Token ký bằng khóa cũ trong thời gian overlap được cấu hình | Chấp nhận trong thời gian cho phép; từ chối sau khi khóa bị loại theo policy |

Verifier phải có **allowlist thuật toán** do cấu hình tin cậy quyết định; không để header `alg` của token tự chọn thuật toán. Tránh lỗi algorithm confusion, ví dụ nhầm public key RSA thành secret HMAC. Không tin URL `jku` hoặc `x5u` tùy ý do token cung cấp để tải khóa. Chỉ lấy khóa từ JWKS endpoint hoặc trust configuration đã đăng ký.

Khi kiểm thử rotation, cần kiểm tra cả cache JWKS: khóa mới được nhận sau refresh, khóa cũ chỉ được giữ trong khoảng overlap cần thiết, và lỗi tải JWKS không khiến hệ thống chấp nhận token không xác minh được. Cần có test cho `kid` trùng hoặc cấu hình khóa mơ hồ nếu hệ thống có khả năng gặp trường hợp đó.

### 5.2. Issuer, audience và thời gian

| Test case | Thay đổi so với token chuẩn | Kết quả mong đợi |
| --- | --- | --- |
| Issuer đúng | `iss` khớp chính xác issuer tin cậy | Qua bước issuer |
| Issuer giả | `iss` là domain hoặc tenant khác | Từ chối |
| Audience đúng | `aud` chứa đúng API hiện tại theo profile | Qua bước audience |
| Audience sai | `aud` chỉ tới API khác | Từ chối |
| Audience có nhiều giá trị | Có API hiện tại và một audience khác | Chấp nhận hoặc từ chối theo profile; không bỏ qua chính sách nhiều audience |
| Hết hạn | `exp` ở quá khứ | Từ chối |
| Chưa tới thời điểm sử dụng | `nbf` ở tương lai vượt clock skew | Từ chối |
| Phát hành trong tương lai | `iat` ở tương lai | Từ chối nếu profile/policy yêu cầu |
| Token quá cũ | `iat` quá xa hoặc tuổi token vượt giới hạn ứng dụng | Từ chối nếu có chính sách tuổi tối đa |

`iss` phải được so khớp theo định danh issuer đã cấu hình, không chỉ so hostname gần giống. `aud` có thể là chuỗi hoặc mảng theo JWT; verifier cần xử lý đúng kiểu dữ liệu và xác nhận API hiện tại nằm trong audience được chấp nhận. Không được coi token phát hành cho API A là hợp lệ tại API B chỉ vì cả hai cùng tin issuer.

### 5.3. Kiểu dữ liệu và claim bắt buộc

Bên cạnh giá trị, test cần kiểm tra cấu trúc claim:

- Thiếu `sub`, `iss`, `aud` hoặc claim bắt buộc theo access token profile.
- `exp`, `nbf`, `iat` có kiểu dữ liệu sai hoặc định dạng không hợp lệ.
- `scope` là chuỗi theo profile nhưng token lại chứa object/array không được hỗ trợ.
- Claim tenant, client hoặc actor bị thiếu, sai định dạng hoặc mâu thuẫn.
- JSON có claim trùng tên hoặc cấu trúc bất thường; parser phải có hành vi xác định, an toàn và nhất quán.
- Header `typ` không đúng nếu profile yêu cầu loại token cụ thể.

Không phải mọi claim đều bắt buộc trong mọi JWT. Ví dụ, `iat` có thể không bắt buộc theo JWT tổng quát, nhưng ứng dụng có thể yêu cầu nó theo profile. Test phải bám theo hợp đồng đã công bố. Nếu hệ thống dùng JWT access token theo RFC 9068, cần kiểm tra các yêu cầu của profile đó, bao gồm loại token và claim bắt buộc tương ứng.

## 6. Bộ test opaque token và introspection

Với opaque token, API thường gửi token tới introspection endpoint của authorization server theo RFC 7662. Kết quả có thể chứa `active`, `scope`, `client_id`, `username`, `sub`, `aud`, `iss`, `exp`, `iat` hoặc các thuộc tính mở rộng. Chỉ dùng những trường mà AS thực sự hỗ trợ và đã được xác minh theo hợp đồng tích hợp.

| Test case | Phản hồi introspection / tình huống | Kết quả mong đợi tại API |
| --- | --- | --- |
| Token active | `active=true`, issuer/audience/scope đúng | Chấp nhận nếu quyền endpoint đạt |
| Token inactive | `active=false` | Từ chối xác thực |
| Token không tồn tại | AS trả `active=false` | Từ chối |
| Sai audience | Active nhưng audience không dành cho API | Từ chối |
| Thiếu scope | Active, đúng audience nhưng scope không đủ | Từ chối thao tác theo authorization contract |
| Token hết hạn | Inactive hoặc `exp` không còn hợp lệ theo contract | Từ chối |
| Introspection timeout | Không nhận được kết quả xác minh | Fail closed; không cho phép truy cập |
| AS trả lỗi 5xx | Không thể xác minh trạng thái | Fail closed; trả lỗi hệ thống phù hợp, không coi token là active |
| Sai thông tin xác thực introspection client | AS từ chối client | Không truy cập; cảnh báo cấu hình |
| Cache kết quả cũ | Token vừa bị thu hồi nhưng cache còn active | Thu hồi có hiệu lực trong giới hạn SLA/cache policy đã thiết kế |

Một số API có thể cache kết quả introspection để giảm độ trễ. Test cần đo thời gian token bị thu hồi có hiệu lực, không chỉ kiểm tra một lần gọi. TTL cache phải tương thích với yêu cầu bảo mật; không dùng cache active lâu hơn mức rủi ro hệ thống chấp nhận. Nếu AS không truy cập được, không được mặc định token hợp lệ dựa trên lần kiểm tra thất bại.

## 7. Test authorization và phản hồi HTTP

Một bộ test tốt phân biệt rõ lỗi token với lỗi quyền. Với Bearer token theo RFC 6750, các tình huống thường gặp:

| Tình huống | Phản hồi thường dùng | Ý nghĩa |
| --- | --- | --- |
| Không gửi credential | `401 Unauthorized` cùng `WWW-Authenticate: Bearer` | Chưa có thông tin xác thực |
| Token sai, hết hạn, bị thu hồi hoặc không hợp lệ | `401 Unauthorized`, `error="invalid_token"` | Không thể xác thực bằng token |
| Token hợp lệ nhưng thiếu scope cần thiết | `403 Forbidden`, `error="insufficient_scope"` khi phù hợp | Đã xác thực nhưng không đủ quyền |
| Token hợp lệ, đủ scope và resource policy cho phép | `2xx` theo endpoint | Được thực hiện thao tác |
| Token đủ scope nhưng truy cập bản ghi thuộc user/tenant khác | Từ chối theo chính sách dữ liệu, thường `403` hoặc `404` có chủ đích | Scope không thay thế kiểm tra quyền trên từng tài nguyên |

Cách trả lỗi cụ thể cần thống nhất với API contract và tránh tiết lộ thông tin nhạy cảm. Không nên trả `403` cho token sai chữ ký nếu hệ thống phân biệt xác thực và phân quyền theo chuẩn Bearer. Cũng không nên trả `200` với dữ liệu rỗng để che một lỗi xác thực mà client không thể phân biệt.

Ví dụ gọi API với token test:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <TEST_ACCESS_TOKEN>
Accept: application/json
```

Các test nên kiểm tra đồng thời status code, `WWW-Authenticate`, response body theo schema, không có dữ liệu nhạy cảm và không có side effect. Với request bị từ chối, xác nhận thao tác ghi dữ liệu không xảy ra.

**Kiểm thử scope và quyền tài nguyên:**

1. Token có `orders.read` gọi endpoint đọc đơn hàng → cho phép nếu subject có quyền trên đơn hàng đó.
2. Token chỉ có `orders.read` gọi endpoint xóa đơn → từ chối.
3. Token có `orders.write` nhưng truy cập đơn hàng thuộc tenant khác → từ chối.
4. Token có role quản trị ở tenant A nhưng request chọn tenant B → từ chối nếu không có quyền cross-tenant.
5. Token hợp lệ nhưng account/session đã bị khóa theo policy → từ chối nếu hệ thống yêu cầu kiểm tra trạng thái đó.
6. Token exchange có `act` hợp lệ nhưng actor không được phép thao tác trên resource cụ thể → từ chối.

## 8. Kiểm thử refresh token, thu hồi và replay

### 8.1. Refresh token

Refresh token phải được gửi tới token endpoint theo refresh grant và được xác minh theo chính sách của authorization server. Resource API thông thường không được nhận refresh token như access token.

Các ca kiểm thử cần có:

- Refresh token hợp lệ, chưa hết hạn, đúng client và phiên → cấp access token mới theo policy.
- Refresh token sai, hết hạn hoặc đã thu hồi → từ chối.
- Refresh token bị dùng bởi client khác → từ chối nếu token được ràng buộc client.
- Refresh token rotation: lần refresh đầu trả token mới và vô hiệu hóa token cũ theo policy.
- Reuse token cũ sau rotation: phát hiện và xử lý theo chính sách reuse detection, có thể thu hồi token family/phiên.
- Logout hoặc thu hồi consent/session: refresh token không tiếp tục cấp access token ngoài chính sách.
- API nhận refresh token trong `Authorization: Bearer` → từ chối vì sai token type/purpose.

Không phải hệ thống nào cũng dùng rotation hoặc reuse detection giống nhau. Test phải xác nhận hành vi đúng với thiết kế thực tế, bao gồm phản hồi lỗi và trạng thái phiên sau khi phát hiện reuse.

### 8.2. Revocation và thời gian lan truyền

Với opaque token, introspection thường là điểm kiểm tra trạng thái active. Với JWT tự xác minh tại resource server, việc thu hồi tức thời cần thêm cơ chế như denylist, session/version check hoặc chuyển sang introspection; chữ ký hợp lệ tự nó không cho biết token vừa bị thu hồi.

Test thu hồi cần xác định:

- Thời điểm AS nhận yêu cầu revoke.
- Resource server nhận biết trạng thái mới qua introspection/cache/denylist lúc nào.
- Access token và refresh token có hành vi thu hồi khác nhau ra sao.
- Khi cache hoặc kho thu hồi không sẵn sàng, hệ thống xử lý theo fail-closed policy nào.
- Token đã exchange có bị ảnh hưởng theo chính sách liên kết với phiên/subject nguồn không.

Không giả định revoke refresh token tự động làm mọi JWT access token đang phát hành mất hiệu lực ngay lập tức. Đây là hành vi cần được thiết kế và xác minh bằng test.

### 8.3. Replay và sender constraint

Với bearer token, bất kỳ bên nào có bản sao token đều có thể thử sử dụng token trong thời hạn hiệu lực. Test nên bao gồm việc gửi lại cùng token ở nhiều request, nhiều client và nhiều thiết bị để xác nhận hệ thống có kiểm soát phù hợp.

Nếu dùng DPoP hoặc mTLS sender-constrained token, kiểm tra:

- Thiếu proof hoặc certificate → từ chối.
- Proof ký bằng key/certificate khác → từ chối.
- Proof hết hạn hoặc sai method/URL theo cơ chế tương ứng → từ chối.
- Proof bị replay khi hệ thống có cơ chế phát hiện replay → từ chối.
- Token binding không khớp với proof/certificate → từ chối.

Không mặc định mọi access token đều one-time-use. Replay defense phụ thuộc loại token, cơ chế ràng buộc và thiết kế endpoint.

## 9. Ví dụ tổ chức test tự động

### 9.1. Ma trận test theo một biến thay đổi

Có thể định nghĩa một token chuẩn hợp lệ, sau đó tạo từng biến thể:

```text
validToken:
  signature: trusted-test-key
  issuer: trusted-issuer
  audience: orders-api
  expiration: future
  notBefore: past
  scope: orders.read
  subject: user-42

invalidVariants:
  - bad-signature
  - unknown-issuer
  - wrong-audience
  - expired
  - not-yet-valid
  - unsupported-algorithm
  - unknown-key-id
  - missing-required-claim
  - malformed-claim-type
  - revoked
  - wrong-token-type
```

Mỗi biến thể nên có một test riêng với kỳ vọng cụ thể. Có thể dùng parameterized test để giảm lặp, nhưng tên test phải cho biết lý do từ chối. Đừng gom tất cả trường hợp vào một test duy nhất chỉ kiểm tra rằng “token sai thì bị từ chối”.

### 9.2. Pseudocode Java với JUnit

Đoạn mã dưới đây minh họa cách tổ chức test. `TestTokenFactory`, `TokenVerifier` và các assertion là giao diện giả định của dự án; thay bằng thư viện và abstraction hiện có. Test factory phải ký JWT bằng khóa test và dùng clock cố định.

```java
class AccessTokenVerifierTest {
    private final Instant now = Instant.parse("2026-11-23T10:00:00Z");
    private final Clock clock = Clock.fixed(now, ZoneOffset.UTC);
    private final KeyPair testKeys = TestKeys.createRsaKeyPair();

    private final TokenVerifier verifier =
        new TokenVerifier(testKeys.getPublic(), clock, TRUSTED_ISSUER,
                          "orders-api");

    @Test
    void acceptsTokenWithTrustedSignatureIssuerAudienceAndTime() {
        String token = TestTokenFactory.jwt(testKeys.getPrivate())
            .issuer(TRUSTED_ISSUER)
            .subject("user-42")
            .audience("orders-api")
            .issuedAt(now.minusSeconds(30))
            .expiresAt(now.plusSeconds(300))
            .claim("scope", "orders.read")
            .sign();

        assertThat(verifier.verify(token)).isAuthenticated();
    }

    @Test
    void rejectsTokenForAnotherAudience() {
        String token = TestTokenFactory.jwt(testKeys.getPrivate())
            .issuer(TRUSTED_ISSUER)
            .subject("user-42")
            .audience("billing-api")
            .expiresAt(now.plusSeconds(300))
            .sign();

        assertThatThrownBy(() -> verifier.verify(token))
            .isInstanceOf(InvalidTokenException.class);
    }

    @Test
    void rejectsExpiredTokenEvenWhenSignatureIsValid() {
        String token = TestTokenFactory.jwt(testKeys.getPrivate())
            .issuer(TRUSTED_ISSUER)
            .subject("user-42")
            .audience("orders-api")
            .expiresAt(now.minusSeconds(1))
            .sign();

        assertThatThrownBy(() -> verifier.verify(token))
            .isInstanceOf(InvalidTokenException.class);
    }
}
```

Ví dụ nhấn mạnh ba nguyên tắc: dùng thời gian cố định, dùng khóa test và giữ các điều kiện khác hợp lệ khi kiểm tra một lỗi cụ thể. Không nên mock chính hàm xác minh chữ ký trong test tích hợp nhằm chứng minh verifier hoạt động; unit test có thể mock dependency bên ngoài, nhưng cần ít nhất một nhóm test thực sự xác minh JWT bằng khóa test.

### 9.3. Test tích hợp với resource server

Một test tích hợp có thể khởi động API với cấu hình security gần production nhưng dùng issuer/JWKS hoặc authorization server test. Gửi request HTTP và xác minh:

- Token hợp lệ, đủ scope → endpoint trả kết quả mong đợi.
- Token sai chữ ký, issuer hoặc audience → `401`.
- Token hết hạn hoặc bị thu hồi → bị từ chối theo contract.
- Token hợp lệ nhưng thiếu scope → `403` khi phù hợp.
- Request truy cập sai tenant/resource → bị chặn dù token có scope.
- Không có request bị từ chối nào làm thay đổi dữ liệu.
- Header và body lỗi không chứa token, secret, stack trace hay claim nhạy cảm.

Nếu dùng opaque token, test tích hợp cần có introspection server test hoặc mock HTTP server trả phản hồi theo kịch bản. Đồng thời kiểm tra xác thực client tới introspection endpoint và timeout, retry, cache theo cấu hình.

## 10. Các lỗi thiết kế mà test cần phát hiện

**Chỉ decode JWT mà không verify chữ ký.** Kẻ tấn công có thể sửa `sub`, `scope` hoặc `role`. Test sửa payload nhưng giữ chữ ký cũ phải bị từ chối.

**Chấp nhận `alg=none` hoặc thuật toán do token tự chọn.** Test header không chữ ký và thuật toán ngoài allowlist phải bị từ chối.

**Không kiểm tra audience.** Token của API khác bị dùng tại API hiện tại. Test audience sai phải thất bại dù chữ ký và issuer đúng.

**Chỉ kiểm tra scope ở gateway.** Service phía sau hoặc endpoint khác có thể bị gọi trực tiếp. Kiểm thử từng ranh giới tin cậy và xác nhận resource server tự thực thi policy cần thiết.

**Coi role/scope là quyền truy cập mọi bản ghi.** Người dùng có scope đọc đơn hàng vẫn có thể không được đọc đơn hàng của tenant khác. Test object-level authorization và tenant isolation.

**Fail-open khi introspection lỗi.** Không xác minh được trạng thái nhưng API vẫn trả dữ liệu. Test timeout/5xx phải chứng minh không truy cập được.

**Dùng ID token hoặc refresh token như access token.** Test sai token type tại resource API phải bị từ chối.

**Log token khi xác minh thất bại.** Test log capture để bảo đảm `Authorization` header và token không xuất hiện trong log, trace hoặc exception.

**Chỉ kiểm thử đường thành công.** Test âm, ranh giới thời gian, rotation, thu hồi và replay là phần bắt buộc của kiểm thử bảo mật token.

## 11. Checklist nghiệm thu bộ test

- [ ] Có token test chuẩn được ký bằng khóa riêng của môi trường test.
- [ ] Có test chữ ký sai, khóa không biết, thuật toán không được phép và key rotation.
- [ ] Có test issuer, audience, `exp`, `nbf`, `iat` và claim bắt buộc theo profile.
- [ ] Có test opaque token active/inactive, introspection timeout, 5xx và cache thu hồi.
- [ ] Có test phân biệt `401 invalid_token` với `403 insufficient_scope`.
- [ ] Có test scope, role, tenant và quyền truy cập từng resource.
- [ ] Có test từ chối ID token/refresh token tại resource API.
- [ ] Có test refresh rotation, reuse detection và revocation theo chính sách triển khai.
- [ ] Có test replay hoặc sender constraint nếu hệ thống hỗ trợ DPoP/mTLS.
- [ ] Có kiểm tra không phát sinh side effect khi request bị từ chối.
- [ ] Có kiểm tra log, trace và response không làm lộ token hoặc secret.
- [ ] Test có thể chạy lặp lại với clock và dữ liệu xác định, không phụ thuộc dịch vụ production.

## 12. Câu hỏi tự kiểm tra

**1. JWT có thể decode thành công nhưng vẫn phải bị từ chối trong trường hợp nào?**

Khi chữ ký sai, thuật toán không được phép, issuer không tin cậy, audience không dành cho API, token hết hạn/chưa tới thời điểm hiệu lực hoặc claim không đáp ứng profile.

**2. Token có chữ ký hợp lệ và audience đúng nhưng thiếu scope thì nên kiểm tra ở lớp nào?**

Xác thực token có thể thành công, sau đó authorization phải từ chối thao tác. Với Bearer token, trường hợp thiếu scope thường trả `403` và `insufficient_scope` theo contract phù hợp.

**3. Vì sao opaque token không thể kiểm thử bằng cách decode payload?**

Opaque token là định danh tham chiếu; nội dung và trạng thái được quản lý phía authorization server. Resource server cần introspection hoặc kho dữ liệu tin cậy để xác minh.

**4. API có nên chấp nhận refresh token trong Authorization header không?**

Thông thường không. Refresh token được dùng tại token endpoint theo refresh grant; resource API yêu cầu access token đúng audience và token type.

**5. Thu hồi refresh token có chắc chắn làm JWT access token đã phát hành mất hiệu lực ngay không?**

Không. JWT có thể tiếp tục được xác minh cục bộ đến khi hết hạn nếu không có cơ chế kiểm tra thu hồi/session bổ sung. Hành vi phải được xác định bằng thiết kế và test.

**6. Tại sao cần test token hợp lệ nhưng truy cập tài nguyên của tenant khác?**

Vì token hợp lệ và scope phù hợp không chứng minh chủ thể được phép truy cập mọi bản ghi. API vẫn phải kiểm tra quyền trên resource và ranh giới tenant.

## Tài liệu chuẩn tham khảo

- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và các claim registered như `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`.
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh thuật toán, issuer, audience và các rủi ro triển khai JWT.
- [RFC 9068 – JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT dành cho OAuth access token.
- [RFC 6750 – OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách gửi bearer token và lỗi `invalid_token`, `insufficient_scope`.
- [RFC 7662 – OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra trạng thái opaque/reference token.
- [RFC 7009 – OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): endpoint và ngữ nghĩa thu hồi token.
- [RFC 9700 – Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): khuyến nghị bảo mật OAuth 2.0 hiện đại.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ngữ nghĩa ID token và xác thực OIDC.

