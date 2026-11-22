# Kiểm tra iss, aud, sub và các claims bắt buộc

## 1. Claims chỉ có ý nghĩa tin cậy sau khi xác minh mật mã

Payload của JWT thường chứa một tập **claims**: các tuyên bố về bên phát hành, chủ thể, đối tượng nhận, thời gian, quyền hoặc ngữ cảnh của token. Những tên thường gặp gồm **iss**, **sub**, **aud**, **exp**, **nbf**, **iat** và **jti**.

Claims là dữ liệu JSON. Trước khi chữ ký JWS hoặc cơ chế bảo vệ JWE được xác minh thành công, người gửi có thể tự tạo hoặc sửa các giá trị này. Vì vậy, việc đọc được claim iss không chứng minh token đến từ issuer đó; claim sub không chứng minh người dùng đó đã đăng nhập; claim aud không chứng minh token được cấp cho API đang nhận nó.

Quy trình đúng gồm hai lớp:

- **Xác minh mật mã:** xác minh chữ ký/MAC hoặc giải mã xác thực theo chính sách tin cậy.
- **Xác minh claims:** kiểm tra issuer, audience, subject, thời gian, kiểu dữ liệu, sự hiện diện của claims bắt buộc và các ràng buộc riêng của token profile.

Chỉ khi cả hai lớp đạt, hệ thống mới tạo ngữ cảnh danh tính/claims đã xác minh để bước phân quyền sử dụng. Chữ ký hợp lệ không thay thế kiểm tra claims; claims có vẻ hợp lý cũng không thay thế chữ ký.

Nội dung này thuộc module Security - JSON Web Token (JWT), áp dụng chung cho mọi ngôn ngữ và nền tảng, không phụ thuộc Java hoặc Spring Security.

## 2. Registered claims và claims theo profile

RFC 7519 định nghĩa các tên claim đã đăng ký (registered claim names). Một số claim quan trọng:

| Claim | Ý nghĩa | Kiểu dữ liệu theo JWT |
| --- | --- | --- |
| **iss** | Issuer: bên phát hành token | StringOrURI |
| **sub** | Subject: chủ thể mà token nói tới | StringOrURI |
| **aud** | Audience: đối tượng nhận token | Một StringOrURI hoặc mảng StringOrURI |
| **exp** | Expiration Time: thời điểm token hết hạn | NumericDate |
| **nbf** | Not Before: thời điểm token bắt đầu có hiệu lực | NumericDate |
| **iat** | Issued At: thời điểm token được phát hành | NumericDate |
| **jti** | JWT ID: định danh token | Chuỗi phân biệt token |

Một điểm dễ nhầm: RFC 7519 định nghĩa các claim trên nhưng không yêu cầu tất cả phải xuất hiện trong mọi JWT. Issuer, subject, audience, thời gian hoặc định danh token có thể là tùy chọn ở cấp JWT tổng quát. **Token profile và hợp đồng ứng dụng** mới quy định claim nào bắt buộc, kiểu dữ liệu, cách diễn giải và điều kiện chấp nhận.

Ví dụ:

- Một access token theo RFC 9068 có tập claims bắt buộc riêng, bao gồm iss, exp, aud, sub, client_id, iat và jti.
- Một OpenID Connect ID token có quy tắc riêng về iss, sub, aud, exp, iat và các điều kiện như nonce theo luồng xác thực.
- Một JWT nội bộ có thể yêu cầu tenant_id, service_id hoặc claims nghiệp vụ riêng theo hợp đồng của các dịch vụ.

Không lấy một danh sách claims duy nhất rồi áp dụng cho mọi loại JWT. Cần chọn profile trước, sau đó kiểm tra đúng hợp đồng của profile đó.

## 3. Xác minh issuer (iss)

Claim **iss** xác định bên phát hành token. Nó là một trong những ranh giới tin cậy quan trọng nhất khi hệ thống có nhiều authorization server hoặc nhiều tổ chức phát hành token.

### 3.1. So khớp chính xác với issuer đã tin cậy

Bên nhận cần có danh sách issuer được phép từ cấu hình tin cậy. Sau khi xác minh chữ ký hoặc bảo vệ mật mã, claim iss phải khớp chính xác với issuer mà policy đã chọn.

Không nên:

- Chấp nhận issuer chỉ vì URL có cùng domain hoặc cùng tiền tố.
- Tự bỏ dấu slash cuối, đổi chữ hoa/thường, bỏ cổng hoặc chuẩn hóa URL theo suy đoán.
- Dùng issuer chưa xác minh để tự tạo JWKS URL hoặc tự động đăng ký issuer mới.
- Chỉ kiểm tra rằng iss tồn tại mà không kiểm tra nó có thuộc danh sách tin cậy của endpoint hay không.

Theo mô hình JWT, StringOrURI được so sánh theo cách phân biệt chữ hoa/chữ thường và không áp dụng canonicalization URL tùy tiện. Vì vậy, nếu policy đăng ký một issuer cụ thể, bên nhận phải áp dụng đúng quy tắc so khớp của profile thay vì tự biến các giá trị gần giống thành một.

Ví dụ, policy tin cậy issuer:

~~~text
https://identity.example.org/
~~~

Các giá trị sau không tự động tương đương:

~~~text
https://identity.example.org
https://IDENTITY.example.org/
https://identity.example.org:443/
https://identity.example.org/tenant-a
~~~

Chỉ chấp nhận giá trị được đăng ký theo hợp đồng. Không tự suy ra rằng khác biệt về slash, host casing, port hoặc path là không quan trọng.

### 3.2. Hệ thống nhiều issuer

Nếu endpoint chấp nhận nhiều issuer, cần ánh xạ từng issuer được phép tới policy và nguồn khóa riêng. Có thể dùng iss chưa xác minh như **gợi ý tra cứu** trong registry cố định, nhưng:

1. Chỉ tìm trong danh sách issuer đã được đăng ký cho endpoint/tenant/client context hiện tại.
2. Không dùng giá trị đó để truy cập URL tùy ý hoặc tự discovery issuer mới.
3. Chọn đúng JWKS/kho khóa gắn với issuer được tra cứu.
4. Xác minh chữ ký bằng khóa trong đúng kho khóa.
5. Sau khi xác minh, so khớp lại claim iss với issuer trong policy.

Không tra kid trên một kho khóa toàn cục chỉ vì các issuer cùng sử dụng tên kid. Cache khóa phải gắn với issuer và nguồn JWKS.

### 3.3. Issuer là ai trong một hệ thống tin cậy?

Issuer là thực thể chịu trách nhiệm phát hành token theo hợp đồng. Trong OAuth/OIDC, issuer thường là authorization server hoặc OpenID Provider. Trong hệ thống nội bộ, issuer có thể là một dịch vụ phát hành token đã được đăng ký.

Không nhầm issuer với:

- **Client:** ứng dụng yêu cầu hoặc nhận token.
- **Subject:** chủ thể được token nói tới.
- **Audience:** resource server hoặc bên nhận token.
- **Tenant:** vùng dữ liệu/khách hàng mà token có thể bị ràng buộc.

Các vai trò này có thể liên quan nhưng không thể thay thế nhau.

## 4. Xác minh audience (aud)

Claim **aud** chỉ ra đối tượng nhận mà token được phát hành cho. Với access token, audience thường đại diện cho resource server hoặc tài nguyên được phép tiêu thụ token.

### 4.1. Kiểm tra đúng audience của dịch vụ nhận

Mỗi API cần biết audience định danh chính nó. Sau khi xác minh mật mã, token phải có audience phù hợp với resource server đang nhận request.

Claim aud có thể là:

- Một chuỗi StringOrURI.
- Một mảng các chuỗi StringOrURI.

Nếu policy yêu cầu audience là https://api.example.org/invoices, bên nhận chỉ chấp nhận khi giá trị đó khớp chính xác với aud hoặc là một phần tử của mảng aud. Không dùng kiểm tra substring, tiền tố, hậu tố hoặc so khớp domain chung.

Ví dụ:

~~~json
{
  "iss": "https://identity.example.org/",
  "aud": [
    "https://api.example.org/invoices",
    "https://api.example.org/reports"
  ]
}
~~~

Token trên có thể được dùng tại API hóa đơn hoặc API báo cáo nếu các policy tương ứng cho phép và mọi kiểm tra khác đều đạt. Nó không mặc nhiên được dùng tại API hồ sơ.

### 4.2. Không bỏ qua audience khi chữ ký đúng

Một issuer có thể cấp token cho nhiều resource server. Nếu API A chỉ xác minh chữ ký và issuer mà bỏ qua aud, token dành cho API B có thể bị chấp nhận ở API A.

Đây là lỗi **audience confusion**. Để ngăn lỗi:

- Mỗi resource server xác định audience riêng.
- Policy ghi rõ audience bắt buộc.
- Token có aud thiếu, sai kiểu hoặc không chứa audience mong đợi phải bị từ chối.
- Không chấp nhận tất cả audience của issuer chỉ vì cùng nguồn phát hành.
- Không dùng audience của client OIDC thay cho audience của API.

### 4.3. Nhiều audience và authorized party

Một JWT có thể có nhiều audience nếu token được cấp cho nhiều bên nhận theo profile. Tuy nhiên, nhiều audience làm tăng yêu cầu phân tích ai là bên được ủy quyền sử dụng token trong ngữ cảnh hiện tại.

Trong OpenID Connect, claim **azp** (authorized party) có quy tắc riêng để xác định client được ủy quyền khi áp dụng, đặc biệt khi ID token có nhiều audience. Không áp dụng azp như một claim bắt buộc phổ quát cho mọi JWT; chỉ kiểm tra theo OIDC profile.

Với access token theo profile OAuth, hãy tuân thủ đúng RFC 9068 và hợp đồng resource server. Không tự suy diễn azp, client_id hoặc aud thay thế lẫn nhau.

## 5. Xác minh subject (sub)

Claim **sub** xác định chủ thể mà token nói tới trong phạm vi issuer. Subject có thể là người dùng cuối, client, tài khoản dịch vụ hoặc một thực thể khác tùy loại token và profile.

### 5.1. Không mặc định sub luôn là người dùng

Trong luồng đăng nhập người dùng, sub thường định danh người dùng. Trong luồng client credentials hoặc giao tiếp service-to-service, sub có thể định danh client hoặc workload. Ứng dụng cần hiểu ý nghĩa sub theo issuer và token profile.

Không được:

- Mặc định mọi sub đều là username hoặc email.
- Dùng email làm định danh ổn định nếu issuer không cam kết điều đó.
- Tự chuyển đổi chữ hoa/thường hoặc chuẩn hóa sub.
- Cho rằng hai token có cùng sub từ hai issuer khác nhau nói về cùng một chủ thể.

### 5.2. Định danh subject nên gắn với issuer

Trong hệ thống nhiều issuer, cùng một chuỗi sub có thể được cấp bởi các issuer khác nhau. Vì vậy, khóa định danh nội bộ thường cần kết hợp **iss + sub** hoặc một ánh xạ danh tính đã được xác minh.

Ví dụ:

| iss | sub | Ý nghĩa |
| --- | --- | --- |
| https://identity-a.example/ | user-123 | Chủ thể user-123 trong miền issuer A |
| https://identity-b.example/ | user-123 | Chủ thể user-123 trong miền issuer B |

Không nên coi hai hàng là cùng một người chỉ vì sub giống nhau. Cần quy trình liên kết danh tính riêng nếu nghiệp vụ yêu cầu hợp nhất hai danh tính.

### 5.3. Kiểm tra sub

Nếu profile yêu cầu sub:

- Claim phải hiện diện.
- Giá trị phải có kiểu StringOrURI theo JWT và đáp ứng giới hạn/profile cụ thể.
- Không chấp nhận null, object, array hoặc chuỗi rỗng nếu hợp đồng không cho phép.
- Nếu ứng dụng dùng sub để truy cập bản ghi, phải kiểm tra chủ thể tồn tại và có trạng thái phù hợp trong miền issuer tương ứng.

Không biến việc sub hợp lệ về cú pháp thành quyết định quyền truy cập. Subject xác định ai/đối tượng nào được token nói tới; authorization quyết định chủ thể đó có thể làm gì.

## 6. Xác minh claims thời gian

Các claim thời gian thường ảnh hưởng trực tiếp tới khả năng chấp nhận token:

| Claim | Điều kiện thường áp dụng | Lưu ý |
| --- | --- | --- |
| **exp** | Token phải được dùng trước thời điểm hết hạn | Tại now >= exp, token hết hiệu lực theo quy tắc không có leeway |
| **nbf** | Token chỉ được dùng từ thời điểm nbf trở đi | Tại now < nbf, token chưa có hiệu lực |
| **iat** | Thời điểm phát hành phải hợp lý; có thể dùng để giới hạn tuổi token | iat tự nó không làm token hết hạn |

Các giá trị này dùng kiểu **NumericDate**: số giây kể từ Unix epoch theo RFC 7519, có thể chứa phần lẻ. Không diễn giải chúng thành mili giây hoặc tự chuyển chuỗi thành số.

Ví dụ policy có thể yêu cầu:

~~~yaml
timeValidation:
  requireExp: true
  requireIat: true
  maxTokenAgeSeconds: 900
  clockSkewSeconds: 60
~~~

Đây là policy minh họa. RFC 7519 không bắt buộc mọi JWT phải có exp, nbf hoặc iat; profile/ứng dụng xác định claim nào phải có.

### 6.1. Kiểm tra exp và nbf

Không có sai số đồng hồ:

- Từ chối nếu **now >= exp**.
- Từ chối nếu **now < nbf**.

Nếu policy cho phép clock skew, chỉ nới lỏng ranh giới trong một khoảng nhỏ, thống nhất và được cấu hình rõ. Không dùng leeway lớn để biến token hết hạn lâu thành token hợp lệ hoặc chấp nhận token chưa tới thời điểm sử dụng.

### 6.2. Kiểm tra iat và tuổi tối đa

iat là thời điểm token được phát hành. Có thể kiểm tra:

- iat không nằm quá xa trong tương lai so với đồng hồ tin cậy.
- now - iat không vượt giới hạn tuổi token nếu policy có quy định.
- exp không đứng trước iat nếu profile yêu cầu quan hệ thời gian hợp lý.
- Thời lượng exp - iat không vượt giới hạn sống tối đa nếu hệ thống quy định.

Không coi iat là bằng chứng token còn hiệu lực. Một token có iat cũ và exp rất xa vẫn cần bị từ chối nếu vượt maxTokenAgeSeconds.

## 7. Xác minh các claims bắt buộc theo profile

### 7.1. Phân biệt claim chuẩn với claim bắt buộc

Một claim có thể được RFC định nghĩa nhưng vẫn tùy chọn ở cấp JWT tổng quát. Ví dụ, RFC 7519 định nghĩa iss, sub, aud, exp, nbf, iat và jti nhưng không yêu cầu tất cả xuất hiện trong mọi token.

Policy cần mô tả rõ:

| Thuộc tính policy | Câu hỏi |
| --- | --- |
| Required | Claim nào bắt buộc phải có? |
| Type | Giá trị phải là string, number, array hay object? |
| Format | Có giới hạn độ dài, định dạng hoặc miền giá trị không? |
| Semantics | Claim có ý nghĩa gì trong profile này? |
| Relationship | Có quan hệ giữa các claim không, ví dụ exp > iat? |
| Context binding | Claim phải khớp endpoint, tenant, client hoặc tài nguyên nào? |
| Unknown claims | Claim mở rộng không biết có được bỏ qua hay phải từ chối theo profile? |

Không nên chỉ kiểm tra claim có tồn tại. Một claim tồn tại nhưng sai kiểu, sai miền giá trị hoặc không phù hợp ngữ cảnh vẫn phải bị từ chối.

### 7.2. Ví dụ access token theo RFC 9068

RFC 9068 định nghĩa JWT Profile for OAuth 2.0 Access Tokens. Profile này yêu cầu các claims như:

- **iss:** issuer của authorization server.
- **exp:** thời điểm hết hạn.
- **aud:** resource server hoặc tài nguyên nhận.
- **sub:** subject của token.
- **client_id:** client đã yêu cầu token.
- **iat:** thời điểm phát hành.
- **jti:** định danh token.

Profile còn quy định typ là at+jwt trong JOSE header và các điều kiện xác minh access token khác. Resource server phải thực hiện đúng profile này, không suy ra rằng mọi JWT có các claims trên đều là access token.

### 7.3. Ví dụ OpenID Connect ID token

OpenID Connect Core quy định ID token có các claims cốt lõi như iss, sub, aud, exp và iat, cùng các điều kiện bổ sung theo authentication flow. Ví dụ, nếu request có nonce thì client phải xác minh nonce trong ID token; khi có nhiều audience, cần áp dụng quy tắc azp theo OIDC.

Đây là profile riêng của ID token. Resource server không lấy danh sách claims OIDC rồi áp dụng thay cho access-token validation.

### 7.4. Claims riêng của ứng dụng

Ứng dụng có thể định nghĩa claims mở rộng như tenant_id, roles, permissions, department hoặc service_id. Cần tài liệu hóa:

- Ai được phép phát hành claim.
- Kiểu dữ liệu và schema.
- Phạm vi áp dụng.
- Cách xử lý khi claim thiếu hoặc có giá trị lạ.
- Claim có thể được dùng cho authorization hay chỉ để hiển thị/tham khảo.

Không tin một claim quyền tùy biến chỉ vì nó có tên như admin, role hoặc permissions. Chỉ dùng nó khi issuer, token profile và chính sách phân quyền đã định nghĩa rõ ý nghĩa, phạm vi và vòng đời.

## 8. Kiểm tra kiểu dữ liệu và cấu trúc claims

Claims Set là một JSON object. Sau khi xác minh mật mã, parser vẫn cần kiểm tra schema:

| Claim | Kiểu thường yêu cầu | Lỗi cần từ chối |
| --- | --- | --- |
| iss | StringOrURI | null, number, object hoặc array |
| sub | StringOrURI | null, object, array hoặc kiểu ngoài hợp đồng |
| aud | StringOrURI hoặc array StringOrURI | object, number hoặc mảng chứa phần tử không phải chuỗi |
| exp, nbf, iat | NumericDate/JSON number | chuỗi số, boolean, object, giá trị tràn hoặc không hợp lệ |
| jti | Chuỗi | object/array hoặc chuỗi vượt giới hạn profile |
| scope theo profile OAuth | Chuỗi theo quy tắc profile | array/object nếu profile yêu cầu chuỗi |
| roles/permissions tùy biến | Theo schema đã định nghĩa | Sai kiểu, giá trị ngoài danh sách hoặc cấu trúc quá lớn |

Ví dụ payload sai kiểu:

~~~json
{
  "iss": 123,
  "sub": {"user": "u-1"},
  "aud": ["https://api.example.org/invoices", 42],
  "exp": "1893456000"
}
~~~

JSON này có thể parse thành công nhưng không đáp ứng kiểu dữ liệu của các claims. Bộ xác minh phải từ chối, không tự ép kiểu để tiếp tục.

Không nên dùng chuyển kiểu lỏng lẻo, ví dụ biến chuỗi "true" thành boolean, chuỗi số thành NumericDate hoặc object thành tên subject. Ép kiểu có thể khiến các thành phần khác nhau hiểu cùng token theo cách khác nhau.

## 9. Claim name collision và claims mở rộng

JWT có registered claims, public claim names và private claim names. Khi định nghĩa claims riêng:

- Tránh dùng tên trùng với registered claim có ý nghĩa khác.
- Dùng URI/namespace được kiểm soát nếu cần public claim name có khả năng tránh va chạm.
- Định nghĩa schema và semantics rõ ràng giữa issuer và bên nhận.
- Không để hai dịch vụ diễn giải cùng tên claim theo hai kiểu dữ liệu hoặc ý nghĩa khác nhau.
- Từ chối duplicate JSON member names để tránh parser khác nhau chọn giá trị đầu/cuối.

Một hệ thống có thể bỏ qua claims mở rộng không biết nếu profile cho phép, nhưng phải luôn xác minh các claim bắt buộc và các claim ảnh hưởng tới bảo mật. Nếu profile yêu cầu allowlist claim names, cần từ chối claim ngoài danh sách theo đúng hợp đồng.

## 10. Quan hệ giữa claims và quyết định phân quyền

Xác minh claims tạo ra một ngữ cảnh có căn cứ về issuer, subject, audience, thời gian và các thuộc tính của token. Đây là đầu vào cho authorization, không phải quyết định authorization hoàn chỉnh.

Ví dụ:

- Token có scope invoice:read không nhất thiết cho phép đọc mọi hóa đơn.
- Subject có tenant_id = tenant-blue không chứng minh request đang truy cập tài nguyên thuộc tenant đó.
- Claim role = admin chỉ có ý nghĩa nếu issuer và profile quy định role đó, và chính sách ứng dụng cho phép sử dụng nó.
- Token hợp lệ nhưng tài khoản đã bị khóa hoặc tài nguyên đã chuyển quyền sở hữu có thể vẫn bị từ chối theo dữ liệu hiện hành.

Luồng nên tách:

1. Xác minh chữ ký/giải mã xác thực.
2. Xác minh claims và token profile.
3. Tạo ValidatedTokenContext từ các giá trị đã xác minh.
4. Kiểm tra quyền trên hành động, tài nguyên, tenant và trạng thái nghiệp vụ.
5. Chấp nhận hoặc từ chối thao tác.

Không để code nghiệp vụ tự parse lại payload thô rồi dùng một claim khác với kết quả mà validator đã kiểm tra.

## 11. Ví dụ policy và kết quả kiểm tra

Giả sử API hóa đơn chỉ nhận access token theo RFC 9068:

~~~yaml
accessTokenValidation:
  issuer: https://identity.example.org/
  audience: https://api.example.org/invoices
  typ: at+jwt
  requiredClaims:
    - iss
    - exp
    - aud
    - sub
    - client_id
    - iat
    - jti
  maxTokenAgeSeconds: 900
  clockSkewSeconds: 60
~~~

Các giá trị là minh họa. Policy thực tế còn phải định nghĩa allowlist thuật toán, JWKS tin cậy, kiểu dữ liệu, scope và các điều kiện khác của RFC 9068.

| Tình huống | Kết quả | Lý do |
| --- | --- | --- |
| Chữ ký đúng, iss đúng, aud chứa API hóa đơn, claims bắt buộc hợp lệ | Tiếp tục kiểm tra quyền | Token vượt qua validation policy |
| iss đúng nhưng aud là API hồ sơ | Từ chối | Token dành cho resource server khác |
| aud đúng nhưng iss không được tin cậy | Từ chối | Sai issuer |
| iss/aud đúng nhưng sub thiếu | Từ chối theo RFC 9068 policy | Thiếu claim bắt buộc |
| sub là object thay vì chuỗi | Từ chối | Sai kiểu dữ liệu |
| exp là chuỗi số | Từ chối | NumericDate phải là JSON number |
| exp đã qua ngoài leeway | Từ chối | Token hết hạn |
| iat nằm xa trong tương lai | Từ chối | Thời điểm phát hành bất hợp lý |
| jti trùng trong luồng yêu cầu chống replay | Từ chối theo chính sách chống replay | Token/ assertion đã được sử dụng |
| Claims hợp lệ nhưng scope thiếu invoice:read | Từ chối thao tác | Token hợp lệ nhưng thiếu quyền |

## 12. Mã giả xác minh claims

Đoạn mã giả mô tả việc kiểm tra sau khi thư viện đã xác minh mật mã thành công:

~~~text
function validateVerifiedClaims(claims, header, policy, now):
    require claims is a JSON object
    require requiredClaimsArePresent(claims, policy.requiredClaims)
    require claims.iss is a valid StringOrURI
    require claims.iss exactly equals policy.trustedIssuer

    require claims.aud is a StringOrURI or array of StringOrURI
    require policy.expectedAudience is present in claims.aud

    require claims.sub is a valid StringOrURI when required by policy
    require claims.exp is a valid NumericDate when required by policy
    require claims.iat is a valid NumericDate when required by policy
    require claims.nbf is a valid NumericDate when present or required

    if claims.exp exists:
        require now < claims.exp + policy.clockSkew
    if claims.nbf exists:
        require now + policy.clockSkew >= claims.nbf
    if claims.iat exists:
        require claims.iat <= now + policy.clockSkew
        require now - claims.iat <= policy.maxTokenAge when configured

    require claimTypesMatchProfile(claims, policy)
    require profileSpecificRulesPass(claims, header, policy)
    require tenantAndClientBindingsPass(claims, policy)

    return ValidatedTokenContext(
        issuer = claims.iss,
        subject = claims.sub,
        audience = claims.aud,
        claims = claims,
        policyId = policy.id
    )
~~~

Trong mã giả, quy tắc thời gian có leeway được viết để minh họa; triển khai phải áp dụng một định nghĩa thống nhất cho exp/nbf/iat và kiểm thử ranh giới. Không dùng claims trước khi thư viện xác minh mật mã thành công.

## 13. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Chỉ kiểm tra chữ ký | Token đúng chữ ký nhưng sai issuer/audience vẫn được chấp nhận | Kiểm tra claims theo policy |
| So khớp iss bằng tiền tố hoặc domain | Chấp nhận issuer giả hoặc issuer khác | So khớp chính xác theo hợp đồng |
| Bỏ qua aud | Token dành cho API khác được dùng tại API hiện tại | Audience riêng cho resource server |
| Dùng sub đơn lẻ làm định danh toàn cục | Trùng subject giữa issuer | Kết hợp issuer + subject hoặc mapping đã xác minh |
| Mặc định sub là người dùng | Sai khi token đại diện client/workload | Diễn giải theo profile |
| Chỉ kiểm tra claim tồn tại | Sai kiểu hoặc giá trị vô nghĩa vẫn lọt | Kiểm tra schema và semantics |
| Ép kiểu chuỗi thành số/boolean | Các parser hiểu khác nhau | Từ chối sai kiểu |
| Coi mọi claim chuẩn là bắt buộc | Từ chối nhầm token hợp lệ ngoài profile đó | Chọn required claims theo profile |
| Coi iat là thời hạn hết hiệu lực | Token cũ hoặc tương lai được xử lý sai | Kiểm tra exp và max age riêng |
| Dùng claim role/scope trực tiếp để cấp quyền | Vượt ranh giới authorization | Kiểm tra quyền theo tài nguyên và chính sách |

## 14. Kiểm thử claims và ranh giới profile

| Nhóm | Ca kiểm thử |
| --- | --- |
| Issuer | Issuer đúng, sai, gần giống, khác slash/port/case, issuer chưa đăng ký |
| Audience | Chuỗi đúng, mảng có audience đúng, audience API khác, thiếu aud, sai kiểu, phần tử không phải chuỗi |
| Subject | sub đúng, thiếu, rỗng, sai kiểu, trùng sub giữa hai issuer |
| Required claims | Thiếu từng claim bắt buộc, claim null, sai kiểu, claim ngoài profile |
| Thời gian | exp sát ranh giới, exp đã qua, nbf tương lai, iat tương lai, max age vượt ngưỡng |
| Profile | Access token đúng typ/aud, ID token gửi vào API, assertion gửi nhầm endpoint |
| Claims mở rộng | tenant mismatch, scope sai kiểu, role không biết, claim name collision |
| Mật mã | Claims đúng nhưng chữ ký sai; chữ ký đúng nhưng claims sai |
| Authorization | Token hợp lệ nhưng không có quyền với hành động/tài nguyên cụ thể |

Nên dùng đồng hồ cố định trong test để kiểm tra chính xác exp, nbf, iat và clock skew. Với multi-issuer, cần kiểm tra cùng một sub ở hai issuer không bị hợp nhất danh tính ngoài ý muốn.

## 15. Checklist triển khai

1. [ ] Chỉ kiểm tra claims sau khi JWS/JWE đã được xác minh mật mã thành công.
2. [ ] Policy xác định issuer được phép và iss phải khớp chính xác.
3. [ ] Audience được cấu hình riêng cho resource server; hỗ trợ đúng dạng chuỗi hoặc mảng.
4. [ ] Không dùng substring/domain-prefix để so khớp iss hoặc aud.
5. [ ] Subject được diễn giải theo profile; định danh nội bộ gắn với issuer khi cần.
6. [ ] Required claims được chọn theo token profile, không áp dụng một danh sách toàn cục.
7. [ ] Mỗi claim được kiểm tra kiểu dữ liệu, miền giá trị và quan hệ với claims khác.
8. [ ] exp, nbf, iat dùng NumericDate theo giây; clock skew nhỏ và max token age được kiểm tra nếu có.
9. [ ] OIDC ID token, OAuth access token và assertion có validator riêng.
10. [ ] Claims mở rộng có schema, namespace và semantics được tài liệu hóa.
11. [ ] Claims đã xác minh chỉ tạo ngữ cảnh; authorization vẫn kiểm tra hành động và tài nguyên.
12. [ ] Có negative tests cho issuer/audience mismatch, thiếu claims, sai kiểu và ranh giới thời gian.
13. [ ] Không log token hoặc claims nhạy cảm.

## 16. Tài liệu tiêu chuẩn liên quan

- **RFC 7519 — JSON Web Token (JWT):** registered claims, StringOrURI, NumericDate và JWT Claims Set.
- **RFC 8725 — JSON Web Token Best Current Practices:** xác minh issuer/audience và phòng nhầm lẫn giữa các loại JWT.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** claims bắt buộc, typ và quy tắc xác minh access token dạng JWT.
- **OpenID Connect Core 1.0:** ID token, iss, sub, aud, exp, iat, nonce và azp.
- **RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants:** claims và quy tắc cho JWT assertion.

**Nguyên tắc ghi nhớ:** iss trả lời ai phát hành, aud trả lời token dành cho ai, sub trả lời token nói tới chủ thể nào. Các claims thời gian và claims bắt buộc phải được kiểm tra theo đúng profile. Chỉ sau khi bằng chứng mật mã và toàn bộ claims validation thành công, hệ thống mới được tạo ngữ cảnh tin cậy để đưa vào bước phân quyền.
