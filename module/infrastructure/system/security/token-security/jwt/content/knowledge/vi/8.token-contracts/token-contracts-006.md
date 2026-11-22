# Quy tắc từ chối claims hoặc tham số không được hỗ trợ

> **Module:** SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)  
> **Chương:** Hợp đồng token  
> **Phạm vi:** Quy tắc xử lý dữ liệu và tính năng JWT ở mức giao thức/hệ thống, không phụ thuộc Java, Spring hay framework cụ thể.

Một hệ thống nhận JWT có thể gặp claim hoặc tham số JOSE mà nó chưa từng thấy. Ví dụ, issuer thêm claim **tenant_region**, một JWT có header **crit** yêu cầu extension mới, hoặc token dùng kiểu serialization mà API chưa hỗ trợ. Nếu bên nhận tùy tiện bỏ qua mọi trường lạ, nó có thể vô tình bỏ qua điều kiện bảo mật. Nếu từ chối mọi trường lạ, hệ thống lại dễ hỏng khi issuer bổ sung metadata không ảnh hưởng đến bên nhận.

Hợp đồng token phải phân biệt rõ:

- **Claim không được nhận diện:** một thuộc tính trong payload mà bên nhận chưa hiểu.
- **Claim đã biết nhưng không hợp lệ:** thiếu, sai kiểu, sai miền giá trị hoặc mâu thuẫn với hợp đồng.
- **JOSE header parameter không được nhận diện:** tham số trong protected/unprotected header mà implementation chưa hỗ trợ.
- **Tính năng hoặc định dạng không được hỗ trợ:** thuật toán, serialization, compression, nested JWT hay extension mà bên nhận không triển khai.
- **Tham số critical:** một extension được đánh dấu là bắt buộc phải hiểu và xử lý.

Các trường hợp này không có cùng cách xử lý. Quy tắc an toàn là **chỉ bỏ qua dữ liệu thật sự không ảnh hưởng đến quyết định bảo mật và được phép bỏ qua theo chuẩn/hợp đồng; từ chối khi không thể thực hiện đầy đủ semantics mà token yêu cầu**.

## 1. Phân biệt claim lạ, claim sai và tính năng không hỗ trợ

### 1.1. Claim không được nhận diện

Payload JWT là một Claims Set. Theo RFC 7519, khi recipient gặp claim không hiểu, recipient phải **từ chối JWT hoặc bỏ qua claim đó**. Recipient **không được sử dụng claim không hiểu để đưa ra quyết định**.

Ví dụ:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-42",
  "aud": "https://api.orders.example.com",
  "exp": 1794800600,
  "tenant_region": "ap-southeast"
}
~~~

Nếu API đơn hàng không dùng **tenant_region**, hợp đồng cho phép bỏ qua claim này và mọi claim bắt buộc khác đều hợp lệ, API có thể tiếp tục xử lý. Nhưng API không được tự suy ra quyền truy cập theo khu vực từ một claim mà nó không hiểu.

Ngược lại, nếu claim lạ được issuer thêm với ý nghĩa “chỉ cho phép truy cập khi thiết bị đã được quản lý”, bên nhận cũ không hiểu điều kiện đó. Nếu issuer kỳ vọng điều kiện mới được thực thi, cần thay đổi token profile/hợp đồng và cơ chế tương thích; không thể chỉ thêm claim rồi giả định mọi recipient sẽ áp dụng.

### 1.2. Claim đã biết nhưng không hợp lệ

Claim đã biết nhưng sai hợp đồng phải bị từ chối, không được xem như metadata tùy chọn:

| Trường hợp | Ví dụ | Cách xử lý |
|---|---|---|
| Claim bắt buộc bị thiếu | Profile yêu cầu **exp**, token không có exp | Từ chối |
| Sai kiểu JSON | **exp** là chuỗi thay vì NumericDate | Từ chối |
| Sai miền giá trị | **token_use** chỉ cho phép **access**, token có **admin** | Từ chối |
| Giá trị rỗng/ngoài giới hạn | **sub** rỗng hoặc **jti** quá dài | Từ chối theo schema |
| Mâu thuẫn với hợp đồng | **aud** không chứa API nhận token | Từ chối |
| Giá trị enum mới nhưng không được hỗ trợ | Claim **assurance_level** có giá trị mà policy chưa biết | Từ chối nếu claim tham gia quyết định bảo mật |

Không biến claim sai kiểu thành claim bị bỏ qua. Ví dụ, nếu **exp** sai kiểu, recipient không thể coi như “token không có exp” rồi tiếp tục; đó là vi phạm hợp đồng thời gian.

### 1.3. Tính năng hoặc định dạng không được hỗ trợ

Một token có thể yêu cầu cách xử lý mà recipient không triển khai:

- Thuật toán **alg** hoặc cặp JWE **alg + enc** không nằm trong allowlist.
- JOSE header extension được đánh dấu critical nhưng recipient không hiểu.
- JWS/JWE JSON Serialization trong khi điểm tiếp nhận chỉ hỗ trợ Compact Serialization.
- Detached payload hoặc unencoded payload khi recipient không hỗ trợ.
- Nested JWT khi hợp đồng không cho phép hoặc recipient không biết thứ tự lớp bảo vệ.
- JWE compression hoặc một content encryption method không được hỗ trợ.

Nếu không thực hiện được đầy đủ semantics của định dạng, recipient phải từ chối. Không được tự bỏ qua bước mã hóa, xác minh chữ ký hoặc extension bắt buộc.

## 2. Chính sách với claim không được nhận diện

### 2.1. Khi nào có thể bỏ qua?

Có thể bỏ qua claim không được nhận diện khi đồng thời thỏa mãn:

1. Claim không thuộc tập claim bắt buộc của token profile/hợp đồng.
2. Claim không tham gia xác thực issuer, audience, thời hạn, loại token, quyền hoặc ràng buộc bảo mật khác tại recipient.
3. Chuẩn/profile áp dụng cho phép bỏ qua claim đó.
4. Việc bỏ qua không làm recipient thực hiện một hành động khác với ý định bảo mật của issuer.

Ví dụ: issuer thêm **preferred_language** để giao diện hiển thị ngôn ngữ; API đơn hàng không dùng claim này trong quyết định truy cập. Nếu hợp đồng cho phép claim mở rộng, API có thể bỏ qua.

### 2.2. Khi nào phải từ chối?

Từ chối JWT nếu:

- Claim lạ nằm trong tập bắt buộc mà recipient phải hiểu.
- Hợp đồng yêu cầu allowlist tên claim và token chứa claim ngoài danh sách.
- Claim lạ là một phần của profile/extension bắt buộc để xác định semantics token.
- Claim đã biết nhưng sai kiểu, sai định dạng hoặc ngoài miền giá trị.
- Không thể xác định việc bỏ qua claim có làm thay đổi quyết định bảo mật hay không.

Đối với claim quyết định quyền, tenant, danh tính, mức xác thực hoặc ràng buộc thiết bị, không nên dùng chế độ “bỏ qua nếu không hiểu”. Cần định nghĩa rõ schema và phiên bản.

### 2.3. Không được sử dụng claim không hiểu để cấp quyền

Giả sử token chứa:

~~~json
{
  "sub": "user-42",
  "permissions": ["orders:read"],
  "emergency_admin": true
}
~~~

Nếu API không biết **emergency_admin** có ý nghĩa gì, nó không được tự diễn giải claim này như quyền quản trị hoặc dùng nó để bỏ qua kiểm tra quyền. Nếu claim không thuộc hợp đồng, hãy bỏ qua theo chính sách hoặc từ chối token; mọi quyết định cấp quyền phải dựa trên claim và policy đã định nghĩa.

### 2.4. Claim lạ và phiên bản hợp đồng

Khi thêm claim mới, issuer và recipient nên thống nhất:

- Claim mới là tùy chọn hay bắt buộc?
- Recipient cũ có thể bỏ qua không?
- Claim mới có ảnh hưởng đến quyền hoặc điều kiện chấp nhận không?
- Token profile/version nào yêu cầu claim mới?
- Cách triển khai chuyển tiếp và thời điểm loại bỏ recipient cũ?

Nếu claim mới thay đổi semantics bảo mật, nên tạo phiên bản contract/profile mới hoặc một loại token mới có thể phân biệt rõ. Không âm thầm thay đổi ý nghĩa của claim cũ hoặc dựa vào một claim mới mà các recipient cũ không biết.

## 3. JOSE header parameters: tham số lạ và critical

### 3.1. Header parameter không critical

JOSE header có thể chứa các tham số chuẩn hoặc extension. Theo quy tắc JOSE, tham số header không được implementation nhận diện có thể được bỏ qua **trừ khi nó được liệt kê trong critical header parameter list**. Tuy nhiên, token profile hoặc hợp đồng có thể đặt chính sách chặt hơn và từ chối tham số ngoài danh sách cho phép.

Ví dụ header:

~~~json
{
  "alg": "RS256",
  "kid": "signing-2026-01",
  "x-display-hint": "compact"
}
~~~

Nếu **x-display-hint** là metadata không ảnh hưởng đến bảo vệ token và không nằm trong **crit**, implementation có thể bỏ qua theo quy tắc/profile. Recipient không được tự gán ý nghĩa bảo mật cho nó.

### 3.2. Header parameter được đánh dấu critical

Tham số **crit** liệt kê các header parameter mà recipient bắt buộc phải hiểu và xử lý. Nếu recipient không hiểu một parameter được liệt kê, nó phải từ chối đối tượng JOSE.

Ví dụ:

~~~json
{
  "alg": "RS256",
  "kid": "signing-2026-01",
  "crit": ["example-policy"],
  "example-policy": "strict-v2"
}
~~~

Nếu recipient không hỗ trợ **example-policy**, phải từ chối. Không được bỏ qua **crit** rồi tiếp tục xác minh chữ ký như thể extension không tồn tại.

Một critical header parameter hợp lệ cần được xử lý đúng:

- **crit** phải là mảng tên parameter theo cú pháp JOSE.
- Mỗi tên được liệt kê phải thực sự có mặt trong JOSE Header thích hợp.
- Recipient phải hiểu và triển khai semantics của từng parameter được liệt kê.
- Nếu một parameter critical không được hỗ trợ hoặc có cấu trúc sai, từ chối.
- Không đánh dấu một parameter là critical chỉ để tăng độ nghiêm trọng; nó phải thực sự thay đổi cách diễn giải hoặc xử lý đối tượng.

### 3.3. Bảng xử lý các header thường gặp

| Header parameter | Vai trò | Nếu không được hỗ trợ hoặc không hợp lệ |
|---|---|---|
| **alg** | Thuật toán JWS/JWE | Từ chối nếu thiếu, không nhận diện hoặc ngoài allowlist |
| **enc** | Thuật toán mã hóa nội dung JWE | Từ chối nếu JWE dùng enc không được hỗ trợ |
| **typ** | Kiểu đối tượng/token profile | Từ chối nếu không khớp loại token mà điểm tiếp nhận chấp nhận |
| **cty** | Content type, có thể biểu thị nested JWT | Từ chối nếu profile yêu cầu semantics mà recipient không hỗ trợ |
| **kid** | Gợi ý định danh khóa | Từ chối nếu không tìm được khóa phù hợp trong nguồn tin cậy sau quy trình refresh có giới hạn |
| **crit** | Danh sách extension critical | Từ chối nếu sai cấu trúc hoặc có extension không hiểu |
| **b64** | Điều khiển mã hóa Base64url payload trong JWS extension tương ứng | Nếu không hỗ trợ giá trị/semantics yêu cầu, từ chối; extension này phải được xử lý theo quy tắc critical |
| **zip** | Compression trong JWE | Từ chối nếu không hỗ trợ hoặc profile không cho phép; cần giới hạn giải nén |
| **jku / x5u** | URI tham chiếu nguồn khóa/chứng thư | Không tự động truy cập URI tùy ý; từ chối nếu profile yêu cầu dùng nhưng không có nguồn tin cậy |
| **x5c** | Chuỗi chứng thư X.509 | Chỉ xử lý nếu profile hỗ trợ và có quy tắc xác minh chuỗi tin cậy; không tin chỉ vì được đính kèm |
| **epk** | Ephemeral public key trong một số JWE key agreement | Từ chối nếu thuật toán/profile yêu cầu nhưng recipient không hỗ trợ |

Danh sách này không thay thế JOSE/JWA registry. Cách xử lý cụ thể phụ thuộc loại đối tượng, vị trí protected/unprotected header và profile. Điểm quan trọng là **không biến tham số bắt buộc của thuật toán thành metadata có thể bỏ qua**.

### 3.4. Phân biệt bỏ qua parameter với bỏ qua semantics

Một parameter không critical có thể được bỏ qua khi chuẩn cho phép và nó không làm thay đổi cách recipient phải bảo vệ hoặc diễn giải token. Nhưng nếu parameter cho biết cách xác minh, cách mã hóa, cách giải nén hoặc cách xử lý claim, recipient không được bỏ qua semantics đó.

Ví dụ:

- Không hiểu một hint hiển thị không bảo mật: có thể bỏ qua nếu profile cho phép.
- Không hiểu **crit** extension yêu cầu kiểm tra thiết bị: phải từ chối.
- Không hỗ trợ **alg**: phải từ chối.
- Không hỗ trợ **enc** của JWE: phải từ chối.
- Không hỗ trợ **b64=false** hoặc detached payload theo extension: phải từ chối thay vì tự parse theo Compact JWS thông thường.

## 4. Từ chối thuật toán, khóa và nguồn dữ liệu không được hỗ trợ

### 4.1. Thuật toán không được hỗ trợ

Recipient phải dùng allowlist cấu hình sẵn. Không chọn thuật toán chỉ dựa trên giá trị **alg** do token cung cấp.

| Tình huống | Xử lý |
|---|---|
| **alg** không xuất hiện trong allowlist | Từ chối |
| **alg** thiếu trong dạng JWS/JWE yêu cầu nó | Từ chối |
| Token dùng **none** tại điểm tiếp nhận yêu cầu chữ ký/MAC | Từ chối |
| JWE dùng **alg** hoặc **enc** không hỗ trợ | Từ chối |
| Thuật toán được hỗ trợ nhưng không tương thích với loại khóa | Từ chối |
| Xác minh thất bại với thuật toán đã chọn | Từ chối; không thử thuật toán khác |

Không fallback từ RS256 sang HS256, từ JWE sang JWS hoặc từ xác minh chữ ký sang bỏ qua chữ ký. Fallback như vậy biến lỗi cấu hình hoặc token không hợp lệ thành cơ hội hạ cấp bảo mật.

### 4.2. Khóa không được hỗ trợ hoặc không tìm thấy

Các trường hợp sau phải được xử lý an toàn:

- **kid** không tìm thấy trong JWKS tin cậy: có thể refresh JWKS theo chính sách giới hạn; nếu vẫn không có, từ chối.
- Khóa có **kty**, **alg**, **use** hoặc **key_ops** không phù hợp: từ chối.
- Khóa đã bị thu hồi hoặc bị đánh dấu xâm phạm: từ chối, kể cả token chưa hết hạn.
- Nguồn JWKS không khả dụng: áp dụng chính sách sẵn có/cache đã được xác định; không tự chuyển sang URL do token chỉ định.
- Có nhiều khóa trùng định danh hoặc dữ liệu khóa mâu thuẫn: từ chối hoặc xử lý theo quy tắc xung đột đã định nghĩa; không chọn ngẫu nhiên.

### 4.3. URL và chứng thư do token cung cấp

Các header như **jku**, **x5u** hoặc **x5c** có thể liên quan đến phân phối khóa/chứng thư. Chúng không tự tạo ra niềm tin.

- Không tải **jku/x5u** từ URL tùy ý trong token chưa xác minh; có thể tạo SSRF hoặc khiến hệ thống tin khóa do kẻ tấn công kiểm soát.
- Nếu profile cho phép tham chiếu khóa, chỉ dùng nguồn đã gắn với issuer/contract và áp dụng kiểm soát mạng, redirect, DNS và cache.
- Không coi **x5c** đính kèm là chứng thư đáng tin chỉ vì chuỗi chứng thư có thể parse; phải xác minh chain, mục đích, thời hạn và trust anchor theo chính sách.
- Không tự chuyển sang nguồn khóa dự phòng không nằm trong allowlist khi nguồn chính gặp lỗi.

## 5. Định dạng và serialization không được hỗ trợ

### 5.1. Compact và JSON Serialization

JWS/JWE có thể dùng Compact Serialization hoặc JSON Serialization theo chuẩn. Một điểm tiếp nhận có thể chỉ triển khai một dạng.

| Định dạng | Đặc điểm | Hành vi khi contract không hỗ trợ |
|---|---|---|
| JWS Compact | Ba phần phân tách bằng dấu chấm | Từ chối nếu điểm nhận chỉ cho dạng khác |
| JWE Compact | Năm phần phân tách bằng dấu chấm | Từ chối nếu không hỗ trợ JWE Compact |
| JWS JSON Serialization | Biểu diễn JSON, có thể hỗ trợ nhiều chữ ký | Từ chối nếu contract chỉ cho Compact |
| JWE JSON Serialization | Biểu diễn JSON, có thể có nhiều recipient | Từ chối nếu contract chỉ cho Compact |
| Detached/unencoded payload | Payload không nằm theo cách Compact thông thường hoặc không Base64url-encode theo extension | Từ chối nếu không hỗ trợ đầy đủ semantics |
| Nested JWT | Một JOSE object chứa JWT khác | Từ chối nếu không có profile/logic xác minh lớp lồng |

Không tự đoán định dạng từ một phần chuỗi rồi thử nhiều parser cho đến khi một parser chấp nhận. Contract cần khai báo serialization được phép và parser phải từ chối các dạng khác.

### 5.2. Detached payload và b64 extension

JWS có thể sử dụng extension **b64** để thay đổi cách biểu diễn payload; trường hợp payload không Base64url-encode được biểu thị qua giá trị **b64=false** và phải tuân thủ quy tắc critical header tương ứng. Một số cấu hình còn dùng detached payload.

Nếu recipient không hỗ trợ extension hoặc không có payload ngoài để xác minh, nó phải từ chối. Không diễn giải token như JWS Compact thông thường, vì dữ liệu ký và dữ liệu được xác minh có thể khác nhau.

### 5.3. Compression và giới hạn giải nén

JWE có thể mang tham số **zip** theo extension compression. Nếu recipient không hỗ trợ thuật toán nén được khai báo, phải từ chối. Nếu có hỗ trợ:

- Chỉ bật theo profile/hợp đồng cần thiết.
- Giới hạn kích thước plaintext sau giải nén và tỷ lệ nén.
- Giới hạn CPU, bộ nhớ và thời gian xử lý.
- Tránh giải nén trước khi hoàn tất các bước xác thực cần thiết theo quy trình JWE.
- Không để dữ liệu nén nhỏ tạo ra payload khổng lồ (decompression bomb).

Nếu hệ thống không cần compression, cách đơn giản là từ chối JWE có **zip** thay vì mở rộng bề mặt xử lý.

## 6. Nguyên tắc fail-closed và không fallback

### 6.1. Fail-closed có nghĩa gì trong hợp đồng token?

Fail-closed nghĩa là **khi không thể xác định token đáp ứng đầy đủ hợp đồng, không cấp quyền dựa trên token đó**. Ví dụ:

- Không hiểu critical header extension → từ chối.
- Không xác minh được chữ ký → từ chối.
- Không tìm được khóa tin cậy → từ chối.
- Không hiểu claim bắt buộc hoặc claim tham gia quyết định bảo mật → từ chối.
- Không hỗ trợ serialization/profile → từ chối.
- Không xác định được trạng thái thu hồi khi policy yêu cầu kiểm tra bắt buộc → xử lý theo fail-closed policy đã định, thường từ chối.

Fail-closed không có nghĩa mọi lỗi hệ thống đều phải làm sập toàn bộ dịch vụ. Có thể trả lỗi xác thực có kiểm soát, dùng cache tin cậy trong giới hạn đã thiết kế hoặc áp dụng cơ chế dự phòng riêng. Nhưng không được biến lỗi không hiểu token thành kết quả “hợp lệ”.

### 6.2. Không thử cách khác cho đến khi thành công

Không nên triển khai logic:

~~~text
try parse as JWS
if failed: try as JWE
if failed: try another algorithm
if failed: skip unknown header
if failed: accept claims that were understood
~~~

Cách làm này tạo nhiều đường xử lý khó kiểm soát và dễ dẫn đến algorithm confusion, parser differential hoặc bỏ qua điều kiện bảo mật.

Quy trình nên là:

~~~text
contract = select from trusted receiver configuration
format = require one of contract.accepted_formats
algorithm = require one of contract.allowed_algorithms
key = select only from contract.trusted_key_sources
profile = require contract.accepted_token_profile
critical_extensions = require all supported
verify/decrypt according to that exact contract
validate required claims and authorization
otherwise reject
~~~

Chọn contract từ cấu hình tin cậy của điểm tiếp nhận, không lấy contract tùy ý từ claim/header chưa xác minh.

### 6.3. Fail-open chỉ khi được thiết kế riêng

Một số hệ thống có thể cân nhắc chế độ dự phòng khi một dịch vụ trạng thái không khả dụng, chẳng hạn cache introspection. Nếu dùng, phải giới hạn:

- Dữ liệu cache đã được xác thực và còn trong TTL cho phép.
- Token vẫn chưa hết hạn theo thời gian hiện tại.
- Hành động được phép trong thời gian dự phòng được xác định trước.
- Có giới hạn thời gian, giám sát và kế hoạch phục hồi.

Không dùng fail-open để bỏ qua chữ ký, issuer, audience, token type, critical extension hoặc claim bắt buộc. Đây là các điều kiện cốt lõi của hợp đồng token.

## 7. Xử lý lỗi và phản hồi bên gọi

### 7.1. Phân biệt lỗi xác thực và lỗi quyền

| Kết quả | Ý nghĩa | Phản hồi khái niệm |
|---|---|---|
| Token sai chữ ký, hết hạn, sai issuer/audience/type, claim bắt buộc sai hoặc extension không hỗ trợ | Không có token hợp lệ cho điểm tiếp nhận | Từ chối xác thực; với OAuth Bearer có thể dùng **401** và lỗi **invalid_token** theo RFC 6750 |
| Token hợp lệ nhưng thiếu scope/quyền cho thao tác | Đã xác thực token nhưng không được phép thực hiện hành động | Từ chối quyền; với OAuth Bearer có thể dùng **403** và **insufficient_scope** khi phù hợp |
| Cú pháp yêu cầu gửi token sai hoặc thiếu cách truyền theo giao thức | Request không đáp ứng cách gửi thông tin xác thực | Trả lỗi request theo giao thức áp dụng |
| Dịch vụ xác minh trạng thái bắt buộc không khả dụng | Không thể hoàn tất kiểm tra theo policy | Áp dụng chính sách availability/fail-closed đã thiết kế |

Mã phản hồi cụ thể phụ thuộc giao thức và ngữ cảnh. Không nên dùng **403** cho mọi token sai hoặc **401** cho mọi trường hợp thiếu quyền.

### 7.2. Không tiết lộ chi tiết nhạy cảm

Phản hồi cho bên gọi nên đủ để biết cần gửi lại thông tin xác thực hợp lệ, nhưng không cần tiết lộ:

- Khóa nào đang được dùng hoặc **kid** nào được tin cậy.
- Chi tiết thuật toán nội bộ hoặc nguồn JWKS.
- Claim nào cho phép vượt qua policy.
- Nội dung payload hoặc token được gửi.
- Trạng thái tài khoản/tenant nhạy cảm vượt quá yêu cầu của giao thức.

Trong log nội bộ, có thể ghi mã nguyên nhân có kiểm soát như **unsupported_critical_header**, **algorithm_not_allowed**, **claim_schema_invalid** hoặc **token_profile_mismatch**. Không ghi toàn bộ bearer token, private key, secret hay dữ liệu nhạy cảm.

### 7.3. Quan sát và cảnh báo

Theo dõi các nhóm lỗi:

- Tỷ lệ claim lạ theo issuer/profile và thay đổi đột biến sau khi phát hành.
- Số token có critical extension không hỗ trợ.
- Thuật toán/serialization/type ngoài allowlist.
- **kid** không tìm thấy, JWKS refresh thất bại hoặc khóa không hợp lệ.
- Token có payload/header quá lớn, duplicate claim hoặc schema sai.
- Các lỗi từ chối theo phiên bản contract.

Nếu issuer bắt đầu gửi extension mới và recipient từ chối hàng loạt, cần phát hiện sớm qua telemetry để phối hợp cập nhật hợp đồng. Không giải quyết sự cố bằng cách tắt kiểm tra critical hoặc nới allowlist không đánh giá.

## 8. Quy trình mở rộng hợp đồng an toàn

Khi issuer muốn thêm claim, header parameter hoặc kiểu token:

1. **Xác định mục đích:** metadata mới hay semantics ảnh hưởng đến bảo mật?
2. **Chốt chuẩn:** claim/header parameter đã đăng ký hay extension riêng? Có cần đánh dấu critical?
3. **Định nghĩa schema:** kiểu dữ liệu, miền giá trị, tính bắt buộc, giới hạn và cách xử lý khi không hỗ trợ.
4. **Đánh giá recipient:** từng API/client có hiểu extension hay được phép bỏ qua?
5. **Phân phiên bản:** nếu thay đổi semantics bảo mật, dùng token profile/contract version mới hoặc loại token mới.
6. **Triển khai tương thích:** cập nhật recipient trước khi issuer phát hành extension bắt buộc; xác nhận cả hai phía đã sẵn sàng.
7. **Kiểm thử âm tính:** token thiếu extension, extension sai kiểu, extension không hỗ trợ và phiên bản cũ.
8. **Giám sát và loại bỏ:** theo dõi lỗi, có kế hoạch kết thúc hỗ trợ phiên bản cũ.

### 8.1. Ví dụ rollout một claim metadata tùy chọn

Issuer muốn thêm **preferred_language** chỉ phục vụ hiển thị:

- Contract hiện tại cho phép bỏ qua claim không liên quan.
- Issuer có thể bổ sung claim mà không thay đổi quyết định bảo mật.
- Recipient cũ bỏ qua; recipient mới có thể dùng cho hiển thị.
- Claim không được dùng để cấp quyền hoặc xác định tenant.

Đây là trường hợp mở rộng tương thích nếu profile và hợp đồng cho phép.

### 8.2. Ví dụ rollout một extension bắt buộc

Issuer muốn thêm extension **device_assurance** yêu cầu recipient chỉ chấp nhận token nếu thiết bị đạt một mức bảo đảm:

- Recipient cũ không hiểu extension nên không thể thực thi điều kiện.
- Issuer không được phát hành token yêu cầu extension critical tới recipient cũ.
- Triển khai hỗ trợ extension ở recipient trước; kiểm thử cách xử lý cả giá trị hợp lệ và không hợp lệ.
- Khi tất cả bên nhận đã hỗ trợ, issuer mới phát hành token có extension trong **crit**.
- Nếu recipient không hiểu hoặc extension thiếu/sai, recipient từ chối.

Không được gửi token với điều kiện bắt buộc rồi hy vọng recipient cũ sẽ bỏ qua an toàn.

## 9. Ma trận kiểm thử từ chối

| ID | Đầu vào | Điều kiện contract | Kết quả mong đợi |
|---|---|---|---|
| R1 | Token có claim metadata không được nhận diện | Claim không bắt buộc, profile cho phép bỏ qua, không dùng trong quyết định | Có thể tiếp tục sau các kiểm tra khác |
| R2 | Claim lạ tham gia quyết định quyền | Recipient không hỗ trợ claim | Từ chối |
| R3 | Claim bắt buộc bị thiếu | Contract yêu cầu | Từ chối |
| R4 | Claim đã biết sai kiểu | Schema quy định kiểu cụ thể | Từ chối |
| R5 | Claim enum có giá trị không hỗ trợ | Giá trị ngoài allowlist | Từ chối nếu claim có ý nghĩa bảo mật |
| R6 | Header parameter lạ không critical | Chuẩn/profile cho phép bỏ qua và không ảnh hưởng semantics | Có thể bỏ qua |
| R7 | Header parameter lạ nằm trong **crit** | Recipient không hỗ trợ | Từ chối |
| R8 | **crit** sai cấu trúc hoặc liệt kê parameter không có mặt | JOSE header không hợp lệ | Từ chối |
| R9 | **alg** ngoài allowlist | Contract chỉ cho thuật toán cụ thể | Từ chối |
| R10 | JWE **enc** không hỗ trợ | Contract chỉ cho enc đã định | Từ chối |
| R11 | **kid** không tìm thấy sau refresh JWKS có giới hạn | Không có khóa phù hợp | Từ chối |
| R12 | **jku** trỏ tới URL không tin cậy | Không có nguồn khóa được ủy quyền | Không truy cập URL; từ chối nếu không thể chọn khóa tin cậy |
| R13 | JWS JSON Serialization | Contract chỉ chấp nhận Compact | Từ chối |
| R14 | Detached/unencoded payload | Recipient không hỗ trợ extension | Từ chối |
| R15 | JWE có **zip** nhưng compression không hỗ trợ | Contract không cho zip | Từ chối |
| R16 | Nested JWT nhưng contract không cho nested | Chỉ chấp nhận một lớp JWS | Từ chối |
| R17 | Token có chữ ký hợp lệ nhưng profile không đúng | API chỉ nhận access token, token là ID token | Từ chối |
| R18 | Dịch vụ introspection bắt buộc không khả dụng | Policy yêu cầu trạng thái trực tuyến | Từ chối hoặc lỗi dịch vụ theo policy; không tự động chấp nhận |

## 10. Checklist chính sách từ chối

**Claims**

- [ ] Phân biệt claim lạ với claim đã biết nhưng sai schema.
- [ ] Chỉ bỏ qua claim lạ khi chuẩn/profile cho phép và claim không tham gia quyết định bảo mật.
- [ ] Không dùng claim không hiểu để cấp quyền hoặc thay đổi danh tính.
- [ ] Claim bắt buộc, claim có ý nghĩa bảo mật và giá trị enum không hỗ trợ được xử lý rõ ràng.
- [ ] Có phiên bản schema/contract khi semantics thay đổi.

**JOSE header và tính năng**

- [ ] **crit** được xử lý đầy đủ; extension critical không hỗ trợ bị từ chối.
- [ ] Header parameter không critical chỉ được bỏ qua khi chuẩn/profile cho phép.
- [ ] **alg**, **enc**, **typ**, **kid** và key source được kiểm tra theo contract.
- [ ] Không truy cập URL khóa tùy ý từ token.
- [ ] Serialization, detached payload, nested JWT, compression và extension chỉ được nhận khi đã hỗ trợ đầy đủ.

**Fail-closed và vận hành**

- [ ] Không fallback sang thuật toán, key source, serialization hoặc token profile khác.
- [ ] Lỗi xác thực được phân biệt với thiếu quyền.
- [ ] Phản hồi không tiết lộ chi tiết nội bộ; log không chứa token/secret.
- [ ] Có telemetry theo contract/profile và kiểm thử âm tính cho tính năng không hỗ trợ.
- [ ] Có quy trình rollout trước khi issuer phát hành claim/extension bắt buộc.

**Điều cần nhớ:** Claim lạ có thể được bỏ qua theo quy tắc JWT nếu nó không được dùng để ra quyết định và profile cho phép. Critical header, thuật toán, khóa, serialization hoặc semantics bắt buộc mà recipient không hỗ trợ thì phải bị từ chối. **Không hiểu một điều kiện bảo mật không bao giờ là lý do để tự bỏ qua điều kiện đó.**

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): Claims Set và cách xử lý claim không được nhận diện.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JOSE Header, **crit**, JWS serialization và unencoded payload extension.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): JWE Header, **crit**, **zip**, serialization và xác thực mã hóa.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS và tham số khóa.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): Thuật toán JOSE và các tham số liên quan.
- [RFC 7797 — JSON Web Signature (JWS) Unencoded Payload Option](https://www.rfc-editor.org/rfc/rfc7797): Tham số **b64** và quy tắc critical.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): Thực hành xác minh JWT, ràng buộc thuật toán/khóa và ngăn nhầm lẫn.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): Quy tắc profile access token.
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Phản hồi lỗi Bearer token.
