# Tài liệu hóa hợp đồng giữa bên phát hành và các bên xác minh

> **Module:** SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)  
> **Chương:** Hợp đồng token  
> **Phạm vi:** Cách thiết kế, viết, quản lý và kiểm chứng hợp đồng JWT giữa issuer và từng bên nhận/xác minh; áp dụng ở mức giao thức và hệ thống, không phụ thuộc Java, Spring hay framework cụ thể.

Một hệ thống có thể phát hành JWT cho nhiều API, ứng dụng và dịch vụ. Nếu mỗi bên tự suy đoán claim nào bắt buộc, audience nào được chấp nhận, thuật toán nào được dùng hoặc token hết hạn được xử lý ra sao, các bên có thể hiểu cùng một token theo những cách khác nhau. Sai khác này tạo ra lỗi xác thực, cấp quyền quá mức, gián đoạn khi luân chuyển khóa hoặc khó điều tra khi có sự cố.

**Hợp đồng token (token contract)** là tài liệu đặc tả thỏa thuận giữa bên phát hành và từng bên xác minh. Tài liệu mô tả token được phát hành cho mục đích nào, ai được nhận, cấu trúc và cơ chế bảo vệ ra sao, claim nào phải có, cách kiểm tra, các trường hợp từ chối và quy trình thay đổi. Đây là nguồn tham chiếu chung để triển khai, kiểm thử, vận hành và phối hợp giữa các bên.

JWT không định nghĩa một mẫu hợp đồng nghiệp vụ duy nhất áp dụng cho mọi tổ chức. RFC 7519 định nghĩa định dạng và registered claims; các profile như RFC 9068 hoặc OpenID Connect đặt thêm quy tắc cho trường hợp cụ thể. Phần còn lại phải được các bên thống nhất thành hợp đồng rõ ràng.

## 1. Mục tiêu và phạm vi của tài liệu hợp đồng

### 1.1. Vì sao cần tài liệu hóa?

Hợp đồng cần giúp mọi bên trả lời nhất quán:

- **Issuer phát hành gì?** Loại token, profile, định dạng, thuật toán và khóa nào được dùng?
- **Token dành cho ai?** Audience và danh sách bên xác minh hợp lệ là gì?
- **Token nói về ai?** Subject, client, actor và các định danh khác có ý nghĩa thế nào?
- **Claim nào bắt buộc?** Kiểu dữ liệu, miền giá trị, giới hạn và quan hệ giữa các claim?
- **Verifier phải kiểm tra gì?** Chữ ký, issuer, audience, token type, thời hạn, quyền và trạng thái?
- **Khi nào phải từ chối?** Token sai, thiếu thông tin, hết hạn, bị thu hồi hoặc dùng sai mục đích?
- **Thay đổi được thực hiện ra sao?** Ai phê duyệt, triển khai trước/sau, tương thích và ngừng phiên bản cũ?

Tài liệu hóa giúp giảm phụ thuộc vào trao đổi miệng, mã nguồn của một bên hoặc hành vi mặc định của thư viện. Nó cũng tạo căn cứ để đánh giá một thay đổi có làm rộng phạm vi tin cậy hay phá vỡ tương thích hay không.

### 1.2. Một hợp đồng phải có ranh giới rõ

Một hợp đồng nên gắn với **một mục đích và một tập bên nhận xác định**. Nếu hai API có audience, quyền hoặc yêu cầu xác minh khác nhau, hãy mô tả thành các profile/contract riêng, kể cả khi cùng issuer và dùng chung thuật toán.

Ví dụ:

| Contract ID | Issuer | Bên nhận | Mục đích |
|---|---|---|---|
| orders-access-v1 | Authorization Server A | Orders API | Đọc/tạo đơn hàng |
| inventory-access-v1 | Authorization Server A | Inventory API | Đọc tồn kho |
| storefront-id-v1 | OpenID Provider A | Storefront OIDC client | Xác minh kết quả đăng nhập |
| account-recovery-v1 | Recovery issuer | Recovery endpoint | Hoàn tất yêu cầu khôi phục |

Không gộp các hợp đồng này thành “JWT chung” chỉ vì cấu trúc có header và payload tương tự nhau. ID token, access token và token nghiệp vụ không được thay thế cho nhau.

### 1.3. Phạm vi tài liệu và phần ngoài phạm vi

Tài liệu hợp đồng nên nêu rõ:

- Những hệ thống, môi trường và endpoint áp dụng.
- Những token profile được hỗ trợ.
- Các luồng phát hành, truyền, xác minh, gia hạn và thu hồi liên quan.
- Các phụ thuộc như JWKS, discovery metadata, introspection hoặc kho trạng thái.
- Những phần không áp dụng, ví dụ refresh token opaque không được resource server xác minh như JWT.

Một tài liệu chỉ mô tả payload mẫu mà không nêu bên nhận và hành vi xác minh chưa đủ để làm hợp đồng.

## 2. Các bên tham gia và trách nhiệm

### 2.1. Xác định đúng vai trò

| Vai trò | Trách nhiệm chính |
|---|---|
| **Issuer** | Xác thực yêu cầu cấp token, chọn profile/audience, tạo claim, ký hoặc mã hóa, công bố khóa và quản lý vòng đời |
| **Verifier / recipient** | Chỉ nhận token thuộc contract của mình, xác minh mật mã và claim, kiểm tra quyền/trạng thái, từ chối an toàn |
| **Client / caller** | Yêu cầu token theo grant được phép, gửi token đúng resource và bảo vệ token trong quá trình sử dụng |
| **Resource owner / subject** | Người dùng hoặc thực thể được đại diện trong mô hình cấp quyền |
| **Contract owner** | Điều phối tài liệu, phiên bản, thay đổi và xử lý bất đồng |
| **Security / platform owner** | Phê duyệt chính sách mật mã, nguồn khóa, thời hạn, giám sát và xử lý sự cố |

Một tổ chức có thể đảm nhiệm nhiều vai trò, nhưng trách nhiệm vẫn phải được phân định. Client gửi token không có quyền tự tuyên bố token hợp lệ; issuer phát hành token cũng không thay verifier quyết định quyền trên từng tài nguyên.

### 2.2. Trách nhiệm của issuer

Issuer phải:

1. Chỉ phát hành token theo profile và grant đã được phê duyệt.
2. Đặt **iss**, **aud**, token type và các claim theo đúng hợp đồng.
3. Không cấp scope/quyền vượt quá yêu cầu và policy đã được xác minh.
4. Dùng thuật toán, khóa và định dạng nằm trong allowlist đã thỏa thuận.
5. Đặt thời hạn, thời điểm bắt đầu và các ràng buộc replay phù hợp.
6. Công bố và luân chuyển khóa theo kế hoạch; thông báo sự cố ảnh hưởng verifier.
7. Cung cấp ví dụ token giả lập, tài liệu claim và bộ test tương thích.
8. Thông báo thay đổi có ảnh hưởng trước khi phát hành token theo semantics mới.

Issuer không được kỳ vọng verifier tự đoán ý nghĩa của claim riêng hoặc tự tải khóa từ URL tùy ý trong token.

### 2.3. Trách nhiệm của verifier

Verifier phải:

1. Chỉ tin issuer và nguồn khóa được cấu hình tin cậy.
2. Chọn đúng contract theo endpoint/mục đích, không dựa hoàn toàn vào header hoặc payload chưa xác minh.
3. Kiểm tra thuật toán, chữ ký/giải mã, issuer, audience và token profile.
4. Kiểm tra claim bắt buộc, kiểu dữ liệu, miền giá trị, thời gian và giới hạn kích thước.
5. Kiểm tra scope, quyền trên tài nguyên và trạng thái khi contract yêu cầu.
6. Từ chối token không hỗ trợ hoặc không thể xác minh đầy đủ.
7. Không ghi bearer token, private key hoặc secret vào log.
8. Báo issuer/contract owner khi phát hiện sai khác, token bất thường hoặc lỗi tương thích.

Verifier không nên “nới” chính sách để khắc phục sự cố phát hành mà không có phê duyệt và thay đổi hợp đồng có kiểm soát.

### 2.4. Ma trận trách nhiệm thay đổi

| Hoạt động | Issuer | Verifier | Contract owner / Security |
|---|---|---|---|
| Đề xuất claim mới | Đề xuất | Đánh giá khả năng hỗ trợ | Điều phối |
| Thay đổi audience | Đề xuất và cấu hình phát hành | Xác nhận bên nhận | Phê duyệt ranh giới tin cậy |
| Thay thuật toán/khóa | Triển khai phát hành và công bố khóa | Cập nhật xác minh | Phê duyệt chính sách mật mã |
| Thay thời hạn | Đặt giá trị phát hành | Cập nhật kiểm tra/cache | Đánh giá rủi ro và vận hành |
| Thay token profile | Định nghĩa/phát hành profile | Triển khai validator tương ứng | Quản lý phiên bản |
| Thu hồi khẩn cấp | Phát tín hiệu/thu hồi khóa hoặc token | Cập nhật trạng thái và từ chối | Điều phối sự cố |

## 3. Cấu trúc chuẩn của một tài liệu hợp đồng

Tài liệu cần đủ chi tiết để một nhóm khác có thể triển khai verifier mà không phải suy đoán. Có thể tổ chức theo các phần sau.

### 3.1. Thông tin định danh và quản trị

| Trường | Nội dung |
|---|---|
| Contract ID | Mã duy nhất, ổn định |
| Contract name | Tên dễ đọc |
| Version | Phiên bản hợp đồng |
| Status | Draft, Review, Active, Deprecated hoặc Retired |
| Purpose | Mục đích sử dụng token |
| Owner | Nhóm chịu trách nhiệm nội dung |
| Issuer | Tên và định danh issuer |
| Verifiers | Danh sách API/client/endpoint được phép nhận |
| Environments | Development, staging, production hoặc môi trường khác |
| Effective date | Thời điểm hợp đồng có hiệu lực |
| Review date | Thời điểm xem xét lại |
| References | RFC, profile, chính sách và tài liệu liên quan |

Không dùng tên file hoặc tên nhóm thay cho Contract ID. Contract ID phải được tham chiếu trong cấu hình, kiểm thử, log và yêu cầu thay đổi.

### 3.2. Mô tả mục đích và luồng sử dụng

Mô tả ngắn:

- Token giải quyết nhu cầu nào.
- Ai yêu cầu token và theo grant/profile nào.
- Token được gửi tới đâu.
- Verifier sử dụng kết quả xác minh để thực hiện quyết định gì.
- Những trường hợp không được dùng token.

Nên có sơ đồ luồng issuer → client → verifier, kèm điểm xác minh và nơi kiểm tra quyền/trạng thái. Sơ đồ cần thể hiện ranh giới tin cậy, không chỉ đường đi mạng.

### 3.3. Định nghĩa token profile

Ghi rõ:

- Chuẩn/profile nền tảng, ví dụ RFC 9068 hoặc OpenID Connect Core.
- Loại đối tượng: JWS, JWE, nested JWT hay dạng khác.
- Serialization được phép: Compact hoặc JSON Serialization.
- Header **typ**, **cty**, **crit** và extension liên quan.
- Token có phải bearer token hay sender-constrained token không.
- Các điều kiện profile bổ sung do ứng dụng quy định.

Nếu có claim riêng như **token_use** hoặc **purpose**, phải ghi rõ đây là quy ước ứng dụng, không trình bày như claim bắt buộc của RFC 7519.

## 4. Tài liệu hóa issuer, audience và danh sách verifier

### 4.1. Issuer và nguồn khóa

Mô tả tối thiểu:

| Thuộc tính | Nội dung cần ghi |
|---|---|
| Issuer identifier | Giá trị **iss** chính xác |
| Discovery metadata | URI discovery đã được cấu hình tin cậy, nếu dùng |
| JWKS URI | Nguồn khóa công khai được ủy quyền |
| Trust establishment | Cách verifier xác định nguồn metadata/JWKS đáng tin |
| Allowed algorithms | Danh sách thuật toán được phép |
| Key constraints | Loại khóa, use, key_ops, kích thước/đường cong |
| Rotation policy | Cách công bố khóa mới, overlap và gỡ khóa cũ |
| Emergency procedure | Cách xử lý khi khóa bị lộ hoặc cần thu hồi khẩn cấp |

Không ghi private key hoặc secret vào tài liệu. Chỉ ghi tham chiếu an toàn tới nơi quản lý khóa và người/nhóm có quyền truy cập.

### 4.2. Audience và bên nhận

Mỗi verifier cần có định danh audience chính xác:

| Verifier | Audience yêu cầu | Token profile | Có chấp nhận audience khác? |
|---|---|---|---|
| Orders API | https://api.orders.example.com | Orders access v1 | Chỉ khi contract liệt kê rõ |
| Inventory API | https://api.inventory.example.com | Inventory access v1 | Chỉ khi contract liệt kê rõ |
| Storefront OIDC client | storefront-web | OIDC ID token | Theo OIDC client registration |

Các giá trị là ví dụ. Verifier phải so khớp audience theo contract; không dùng tiền tố, chuỗi con hoặc wildcard rộng trừ khi profile có quy tắc được định nghĩa và đánh giá rõ.

Nếu một token có nhiều audience, ghi rõ:

- Vì sao cần nhiều audience.
- Verifier nào được liệt kê.
- Quyền nào được phép dùng tại từng verifier.
- Có yêu cầu token riêng cho từng resource không.
- Hậu quả nếu token bị lộ tại một trong các resource.

Không dùng một audience chung cho mọi API chỉ để giảm số lượng cấu hình nếu điều đó làm mở rộng phạm vi token.

### 4.3. Bảng ma trận issuer–verifier

Đây là bảng quan trọng để tránh việc hai bên hiểu khác nhau:

| Contract ID | Issuer được tin | Verifier | Audience | Token type | Trạng thái |
|---|---|---|---|---|---|
| orders-access-v1 | https://id.example.com | Orders API | https://api.orders.example.com | RFC 9068 access token | Active |
| inventory-access-v1 | https://id.example.com | Inventory API | https://api.inventory.example.com | RFC 9068 access token | Active |
| storefront-id-v1 | https://id.example.com | Storefront client | storefront-web | OIDC ID token | Active |
| partner-report-v1 | https://partner-id.example.org | Partner Reports API | https://api.partner.example.com/reports | Partner access profile | Review |

Một verifier chỉ được nhận các dòng contract được gán cho nó. Việc cùng issuer xuất hiện trong nhiều dòng không khiến mọi verifier tự động tin mọi audience hoặc token type của issuer đó.

## 5. Tài liệu hóa header, thuật toán và khóa

### 5.1. Bảng header policy

| Thành phần | Giá trị/quy tắc được chấp nhận | Hành vi khi sai |
|---|---|---|
| **alg** | Allowlist JWS theo contract | Từ chối |
| **enc** | Allowlist JWE nếu có sử dụng | Từ chối nếu không hỗ trợ |
| **typ** | Token type/profile đã thống nhất | Từ chối nếu sai profile |
| **kid** | Định danh khóa trong JWKS của issuer | Tìm trong nguồn tin cậy; từ chối nếu không có khóa phù hợp |
| **crit** | Chỉ extension mà verifier hiểu và xử lý đầy đủ | Từ chối nếu extension critical không hỗ trợ |
| **cty** | Quy tắc nested/content type của profile | Từ chối nếu semantics không được hỗ trợ |
| **zip** | Chỉ khi profile cho phép và có giới hạn giải nén | Từ chối nếu không hỗ trợ |

Nếu contract chỉ nhận JWS Compact, phải ghi rõ JWE, JSON Serialization, detached payload hoặc nested JWT nằm ngoài phạm vi.

### 5.2. Bảng thuật toán và khóa

Ví dụ:

| Mục | Quy định |
|---|---|
| JWS algorithms | PS256 |
| Key type | RSA |
| Key use | sig |
| Key source | JWKS của issuer đã cấu hình |
| Minimum key requirements | Theo RFC JWA và chính sách mật mã tổ chức |
| HMAC | Không được chấp nhận trong contract này |
| Unsecured JWT | Từ chối |

Danh sách chỉ là ví dụ. Chọn thuật toán theo profile và chính sách mật mã đang áp dụng; không sao chép danh sách mẫu mà không đánh giá khả năng tương thích và vòng đời dữ liệu.

### 5.3. Quy trình xác minh khóa

Tài liệu cần mô tả:

1. Verifier xác định issuer theo cấu hình contract.
2. Nguồn JWKS được lấy từ metadata/URI đã tin cậy.
3. **kid** chỉ dùng chọn ứng viên trong bộ khóa của issuer đó.
4. Kiểm tra **kty**, **alg**, **use**, **key_ops**, kích thước hoặc đường cong.
5. Xác minh chữ ký theo đúng thuật toán được cấu hình.
6. Nếu **kid** chưa có, refresh JWKS có giới hạn; không tải URL tùy ý từ token.
7. Nếu khóa bị thu hồi/xâm phạm, áp dụng quy trình khẩn cấp.

### 5.4. Quản lý khóa và thời gian chuyển tiếp

Hợp đồng nên ghi:

- Ai chịu trách nhiệm tạo và bảo vệ private key/secret.
- Cách công bố public key mới trước khi bắt đầu ký.
- Khoảng overlap để verifier nhận cả khóa cũ và mới.
- Thời gian cache JWKS và giới hạn refresh.
- Điều kiện gỡ khóa cũ.
- Cách xử lý khi private key bị xâm phạm.

Không ghi secret thật, private key hoặc dữ liệu truy cập kho khóa vào ví dụ. Dùng giá trị giả lập và tham chiếu tới kho quản lý được kiểm soát.

## 6. Tài liệu hóa Claims Schema

### 6.1. Bảng claim chuẩn

Mỗi claim cần có tên, kiểu, tính bắt buộc, ý nghĩa và quy tắc xác minh:

| Claim | Kiểu | Bắt buộc? | Ý nghĩa và kiểm tra |
|---|---|---|---|
| **iss** | String | Có | Khớp chính xác issuer |
| **sub** | String | Theo profile | Subject theo issuer/grant |
| **aud** | String hoặc array string | Có theo profile | Chứa audience của verifier |
| **exp** | NumericDate | Theo profile | Chưa hết hạn; lifetime không vượt policy |
| **nbf** | NumericDate | Theo profile | Không sử dụng trước thời điểm |
| **iat** | NumericDate | Theo profile | Hợp lý và đủ mới |
| **jti** | String | Theo profile | JWT ID; dùng chống replay/thu hồi khi cần |
| **client_id** | String | Theo profile | OAuth client identity |
| **scope** | String theo profile OAuth | Theo profile | Quyền được cấp, kiểm tra theo thao tác |

Không trình bày tất cả registered claims là bắt buộc cho mọi JWT. Hãy ghi profile cụ thể, ví dụ RFC 9068 hoặc OIDC, và liệt kê đúng yêu cầu của profile đó.

### 6.2. Claim riêng

Với mỗi private/public claim do ứng dụng định nghĩa, ghi:

| Thuộc tính | Ví dụ |
|---|---|
| Claim name | https://claims.example.com/tenant_id |
| Data type | String |
| Required | Có trong Orders access profile |
| Allowed values | Tenant ID đã được issuer cấp |
| Maximum length | Theo schema của tổ chức |
| Security meaning | Xác định phạm vi tenant |
| Issuer responsibility | Chỉ phát hành sau khi xác thực tenant membership |
| Verifier responsibility | Kiểm tra tenant của tài nguyên và request |
| Unknown handling | Từ chối nếu contract yêu cầu allowlist claim |

Tên claim URI trong ví dụ là namespace, không phải URL bắt buộc phải truy cập. Claim tham gia quyết định bảo mật cần có schema chặt, nguồn dữ liệu tin cậy và quy tắc khi thiếu/sai.

### 6.3. Kiểu dữ liệu và giới hạn

Ghi rõ:

- Kiểu JSON chính xác; không tự chuyển string thành number/boolean.
- Độ dài tối thiểu/tối đa của chuỗi.
- Số phần tử tối đa trong array.
- Số lượng claim và độ sâu object/array.
- Miền giá trị, enum và quy tắc so khớp.
- Quy tắc duplicate member trong JSON.
- Kích thước tối đa của compact token, header, payload và ciphertext.

Các giới hạn cụ thể là quyết định của contract, không phải mặc định của RFC 7519. Chúng cần phù hợp với gateway, proxy, header/cookie và dịch vụ liên quan.

### 6.4. Claim không được nhận diện

Tài liệu phải nói rõ verifier xử lý claim lạ thế nào:

- Bỏ qua nếu chuẩn/profile cho phép và claim không tham gia quyết định bảo mật.
- Từ chối nếu claim thuộc allowlist bắt buộc, ảnh hưởng quyền hoặc cần thiết để diễn giải token.
- Không sử dụng claim không hiểu để cấp quyền.
- Không âm thầm bỏ qua claim đã biết nhưng sai kiểu hoặc sai miền giá trị.

Phân biệt claim lạ với JOSE header parameter được liệt kê trong **crit**. Verifier không hiểu critical extension phải từ chối đối tượng JOSE.

## 7. Tài liệu hóa thời hạn, trạng thái và quyền

### 7.1. Chính sách thời gian

| Mục | Quy định cần ghi |
|---|---|
| Required time claims | **exp**, **iat**, **nbf** theo profile |
| NumericDate | Số giây từ Unix epoch |
| Maximum lifetime | Thời hạn tối đa theo loại token |
| Maximum token age | Tuổi tối đa nếu cần freshness |
| Clock skew | Dung sai nhỏ và có căn cứ |
| Boundary semantics | Điều kiện đúng tại thời điểm **exp/nbf** |
| Clock source | Cơ chế đồng bộ và giám sát thời gian |

Không để issuer và verifier tự chọn leeway khác nhau mà không được ghi nhận. Dung sai lớn không thay thế việc đồng bộ đồng hồ.

### 7.2. Revocation và trạng thái

Hợp đồng cần nêu token có thể bị vô hiệu hóa trước **exp** hay không, cách kiểm tra và mức độ trễ chấp nhận được:

- Access token có lifetime ngắn và kiểm tra offline.
- Denylist theo **jti**.
- Token introspection.
- Session/grant version.
- Thu hồi khóa khi có sự cố.
- Trạng thái một lần dùng cho recovery, email verification hoặc transaction token.

Ghi rõ cache TTL, fail-open/fail-closed khi dependency không khả dụng và thời gian tối đa để trạng thái thu hồi có hiệu lực ở mọi verifier.

### 7.3. Authorization policy

Tài liệu phải phân biệt:

- Xác thực token: token có hợp lệ theo profile không?
- Quyền thao tác: token có scope/permission cần thiết không?
- Quyền trên tài nguyên: subject/client/actor có được truy cập đúng đối tượng không?
- Ràng buộc ngữ cảnh: tenant, môi trường, trạng thái giao dịch hoặc sender proof có khớp không?

Scope không thay thế kiểm tra quyền trên tài nguyên cụ thể. Với delegation, phải ghi cách đánh giá cả subject và actor.

## 8. Ví dụ hợp đồng hoàn chỉnh

Ví dụ dưới đây là một bản đặc tả khái niệm cho access token của Orders API. Các URI, client, thời hạn và thuật toán chỉ là dữ liệu giả lập:

~~~yaml
contract:
  id: orders-access-v1
  name: Orders API access token
  version: 1.0.0
  status: active
  purpose: access_orders_resource
  owner: identity-platform
  effective_date: "2026-11-16"

issuer:
  iss: "https://id.example.com"
  jwks_uri: "https://id.example.com/.well-known/jwks.json"
  trusted_algorithms:
    - PS256

verifier:
  name: orders-api
  audience: "https://api.orders.example.com"
  accepted_profile: oauth2-jwt-access-rfc9068
  serialization: jws-compact
  accepted_typ:
    - at+jwt
    - application/at+jwt

claims:
  required:
    iss: string
    sub: string
    aud: string_or_array_of_strings
    exp: numeric_date_seconds
    iat: numeric_date_seconds
    jti: string
    client_id: string
  optional:
    tenant_id: string
    scope: oauth_space_delimited_string
  unknown_claims: ignore_if_non_security_relevant
  duplicate_names: reject

time_policy:
  max_lifetime_seconds: 600
  max_token_age_seconds: 600
  clock_skew_seconds: 30
  reject_at_or_after_exp: true

authorization:
  read_order_scope: orders:read
  create_order_scope: orders:create
  resource_check: caller_may_access_requested_order

state:
  revocation_check: required_by_risk_policy
  cache_never_exceeds_exp: true

failure:
  invalid_token: reject
  insufficient_scope: reject
  unsupported_algorithm: reject
  unknown_critical_header: reject

operations:
  key_rotation: publish_before_use
  emergency_key_compromise: revoke_and_notify_all_verifiers
  contract_change_notice_days: 30
~~~

Đây là ví dụ minh họa cấu trúc tài liệu, **không phải schema chuẩn của RFC hoặc của một thư viện**. Các giá trị phải được hai bên thống nhất. Nếu dùng RFC 9068, cần đáp ứng đầy đủ mọi yêu cầu của profile; ví dụ trên không thay thế tiêu chuẩn.

### 8.1. Ví dụ payload minh họa

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-42",
  "aud": "https://api.orders.example.com",
  "client_id": "storefront-web",
  "iat": 1794800000,
  "exp": 1794800600,
  "jti": "at-example-7f19",
  "scope": "orders:read",
  "tenant_id": "tenant-42"
}
~~~

Payload chỉ minh họa claim và kiểu dữ liệu; nó không phải JWT đã ký. Không dùng token mẫu với secret hoặc dữ liệu người dùng thật. Bộ ví dụ phát hành nên được ký bằng khóa thử nghiệm riêng, không dùng private key production.

## 9. Ví dụ ma trận xác minh cho nhiều bên nhận

Một issuer có thể phục vụ nhiều verifier, nhưng từng verifier phải thực thi contract của mình:

| Điều kiện | Orders API | Inventory API | Storefront OIDC client |
|---|---|---|---|
| Issuer | Identity issuer A | Identity issuer A | OIDC provider A |
| Audience | Orders API URI | Inventory API URI | Storefront client ID |
| Token type | Access token profile | Access token profile | ID token |
| Required purpose | Gọi Orders API | Gọi Inventory API | Xác minh đăng nhập |
| Scope | orders:read / orders:create | inventory:read | Không dùng như scope API |
| Time policy | Access lifetime ngắn | Access lifetime ngắn | OIDC exp/iat và flow checks |
| State checks | Revocation theo policy | Revocation theo policy | Nonce/session theo OIDC |
| Từ chối token của bên khác | Inventory/ID token | Orders/ID token | Access token/ID token sai client |

Issuer không được phát hành một token audience chung rồi trông đợi mỗi verifier tự suy ra tài nguyên đích. Nếu cần nhiều audience, contract phải nêu rõ và từng verifier vẫn phải kiểm tra audience của chính mình.

## 10. Bộ kiểm thử tuân thủ hợp đồng

Tài liệu không hoàn chỉnh nếu chỉ có ví dụ token hợp lệ. Cần có bộ kiểm thử chứng minh issuer và verifier cùng hiểu contract.

### 10.1. Test case dương tính

- Token đúng issuer, audience, type, thuật toán và khóa.
- Claims bắt buộc có mặt, đúng kiểu và miền giá trị.
- Token còn hiệu lực theo thời gian và leeway.
- Scope/permission hợp lệ cho thao tác.
- Token có claim mở rộng tùy chọn được xử lý đúng.
- Key rotation trong giai đoạn overlap hoạt động theo kế hoạch.

### 10.2. Test case âm tính

| ID | Đầu vào | Kết quả |
|---|---|---|
| C01 | Sai chữ ký hoặc khóa không thuộc issuer | Từ chối |
| C02 | Issuer ngoài allowlist | Từ chối |
| C03 | Audience của verifier khác | Từ chối |
| C04 | ID token gửi tới resource API | Từ chối |
| C05 | Thuật toán ngoài allowlist hoặc none | Từ chối |
| C06 | Thiếu claim bắt buộc | Từ chối |
| C07 | Claim sai kiểu hoặc ngoài giới hạn | Từ chối |
| C08 | Token hết hạn hoặc chưa đến nbf | Từ chối theo time policy |
| C09 | Lifetime vượt giới hạn | Từ chối |
| C10 | Critical header extension không hỗ trợ | Từ chối |
| C11 | Serialization không được contract hỗ trợ | Từ chối |
| C12 | Token bị thu hồi hoặc jti đã dùng | Từ chối khi contract yêu cầu trạng thái |
| C13 | Scope hợp lệ nhưng không có quyền trên tài nguyên | Từ chối quyền |
| C14 | Key mới xuất hiện trước khi JWKS được cập nhật | Xử lý theo rotation procedure; không fallback nguồn khóa |
| C15 | Claim lạ không ảnh hưởng bảo mật và profile cho phép bỏ qua | Tiếp tục sau các kiểm tra còn lại |

### 10.3. Test vector và dữ liệu thử

Mỗi test vector nên ghi:

- Contract ID và phiên bản.
- Mục tiêu kiểm thử.
- Header/payload giả lập hoặc token thử nghiệm.
- Khóa công khai thử nghiệm và cách lấy khóa.
- Kết quả mong đợi.
- Mã lỗi dự kiến.
- Phiên bản issuer/verifier đã chạy.

Không đưa private key, secret production, bearer token đang hoạt động hoặc dữ liệu cá nhân thật vào repository/tài liệu. Nếu test cần chữ ký, dùng key pair riêng cho môi trường thử nghiệm và quản lý vòng đời test key rõ ràng.

### 10.4. Conformance giữa issuer và verifier

Hai bên nên chạy cùng bộ test:

1. Issuer phát hành token cho từng test case.
2. Verifier xác minh và trả kết quả.
3. Hai bên đối chiếu kết quả với contract.
4. Ghi nhận sai khác và nguyên nhân.
5. Chỉ xác nhận tương thích khi các ca bắt buộc đạt.

Có thể duy trì bộ test tự động hoặc công cụ kiểm tra độc lập, nhưng kết quả phải gắn với phiên bản contract và phiên bản triển khai.

## 11. Versioning và quản lý thay đổi

### 11.1. Khi nào cần phiên bản mới?

Thay đổi có thể chia thành:

| Loại thay đổi | Ví dụ | Ảnh hưởng |
|---|---|---|
| Tương thích, không đổi semantics | Bổ sung claim hiển thị tùy chọn mà verifier cũ được phép bỏ qua | Có thể cập nhật phiên bản minor/revision theo quy ước |
| Thay đổi có điều kiện | Thêm audience/verifier mới, thêm scope tùy chọn, thay cache policy | Cần đánh giá phạm vi tin cậy và cập nhật verifier liên quan |
| Phá vỡ tương thích | Đổi issuer/audience, đổi kiểu claim, bắt buộc claim mới, đổi token type hoặc thuật toán không tương thích | Cần phiên bản contract mới và rollout phối hợp |

Không có một quy tắc semver bắt buộc cho mọi token contract. Tổ chức nên định nghĩa quy ước rõ, ví dụ:

- **Major:** thay đổi semantics hoặc điều kiện bắt buộc khiến verifier cũ không còn tương thích.
- **Minor:** bổ sung tính năng tùy chọn mà verifier cũ có thể bỏ qua an toàn.
- **Patch/revision:** sửa mô tả, ví dụ hoặc lỗi chính tả không đổi semantics.

Nếu thay đổi ảnh hưởng ranh giới bảo mật, nên tạo contract/profile mới ngay cả khi mã phiên bản nội bộ có quy tắc khác.

### 11.2. Quy trình thay đổi

~~~mermaid
flowchart TD
    A[Đề xuất thay đổi contract] --> B[Phân tích mục đích và tác động]
    B --> C[Phân loại tương thích]
    C --> D[Issuer và verifier review]
    D --> E{Được phê duyệt?}
    E -->|Không| R[Điều chỉnh hoặc từ chối]
    E -->|Có| F[Cập nhật tài liệu và test vectors]
    F --> G[Triển khai verifier hỗ trợ trước nếu cần]
    G --> H[Issuer phát hành theo phiên bản mới]
    H --> I[Giám sát kết quả và lỗi tương thích]
    I --> J[Ngừng phiên bản cũ theo lịch]
~~~

Mọi thay đổi cần có:

1. Lý do và chủ sở hữu yêu cầu.
2. Contract/profile và verifier bị ảnh hưởng.
3. Phân tích rủi ro, tương thích và phương án rollback.
4. Phiên bản tài liệu, test vector và ngày hiệu lực.
5. Thời gian thông báo đủ để các bên triển khai.
6. Kế hoạch loại bỏ phiên bản cũ và xử lý token còn hạn.

### 11.3. Thứ tự triển khai

Với thay đổi yêu cầu verifier hiểu claim/extension mới, thường phải triển khai verifier hỗ trợ trước, sau đó issuer mới phát hành token yêu cầu tính năng đó. Nếu issuer phát hành trước, verifier cũ có thể từ chối hàng loạt hoặc tệ hơn là bỏ qua điều kiện bảo mật nếu được cấu hình sai.

Với thay đổi khóa ký thông thường, công bố public key mới trước khi bắt đầu ký bằng khóa mới; duy trì overlap có giới hạn; gỡ khóa cũ sau khi hết thời gian chuyển tiếp. Sự cố khóa bị xâm phạm cần quy trình thu hồi khẩn cấp riêng, không theo lịch rotation bình thường.

## 12. Vận hành và giám sát hợp đồng

### 12.1. Chỉ số cần theo dõi

- Số token được phát hành theo Contract ID/profile.
- Tỷ lệ xác minh thành công và từ chối theo nguyên nhân.
- Sai issuer, audience, token type, thuật toán hoặc claim.
- Lỗi tải JWKS, unknown kid, thời gian cache và sự kiện rotation.
- Token hết hạn, chưa có hiệu lực, vượt max lifetime hoặc freshness.
- Lỗi introspection, denylist, replay hoặc trạng thái giao dịch.
- Các verifier đang dùng phiên bản contract cũ.

### 12.2. Log và bảo vệ dữ liệu

Log nên ghi contract ID, profile version, verifier, mã nguyên nhân và thời điểm xử lý cần thiết. Có thể ghi định danh subject/client đã được xác minh nếu chính sách riêng tư cho phép và có mục đích rõ ràng.

Không ghi:

- Toàn bộ bearer token hoặc refresh token.
- Private key, HMAC secret hoặc nội dung kho khóa.
- Payload chứa dữ liệu cá nhân/nhạy cảm không cần thiết.
- URL/claim chưa xác minh như thể chúng là nguồn tin cậy.

### 12.3. Xử lý sự cố

Hợp đồng cần chỉ rõ:

- Đầu mối liên hệ của issuer, verifier và security owner.
- Cách thông báo issuer/key bị xâm phạm.
- Cách thu hồi khóa/token hoặc vô hiệu hóa profile.
- Cách cập nhật JWKS/cache và trạng thái ở tất cả verifier.
- Cách đánh giá token đã phát hành trong khoảng thời gian rủi ro.
- Cách khôi phục dịch vụ và xác nhận contract hoạt động lại.

Nếu verifier không thể thực hiện một kiểm tra bắt buộc, phải xử lý theo fail-closed hoặc cơ chế dự phòng đã phê duyệt. Không bỏ qua chữ ký, audience, token type hoặc critical extension để duy trì availability.

## 13. Checklist nghiệm thu hợp đồng

**Định nghĩa và quản trị**

- [ ] Có Contract ID, version, owner, status và ngày hiệu lực.
- [ ] Mục đích, endpoint và phạm vi áp dụng được mô tả rõ.
- [ ] Issuer, verifier, client và các vai trò liên quan được phân định.
- [ ] Có tài liệu tham chiếu RFC/profile áp dụng.

**Issuer và verifier**

- [ ] Issuer, JWKS/discovery và trust establishment được định nghĩa.
- [ ] Mỗi verifier có audience chính xác và profile riêng.
- [ ] Ma trận issuer–verifier không có tổ hợp tin cậy ngoài ý muốn.
- [ ] Trách nhiệm phát hành, xác minh, thu hồi và thay đổi được phân công.

**Token và claim**

- [ ] JWS/JWE, serialization, typ, thuật toán và khóa được ghi rõ.
- [ ] Claim bắt buộc, tùy chọn, kiểu dữ liệu và miền giá trị có schema.
- [ ] Claim riêng có semantics, owner và unknown handling.
- [ ] Time policy, lifetime, freshness và clock skew được thống nhất.
- [ ] Authorization, revocation và replay policy được ghi rõ.

**Kiểm thử và vận hành**

- [ ] Có test case dương tính, âm tính và test vector an toàn.
- [ ] Issuer và mọi verifier liên quan đã chạy conformance tests.
- [ ] Có quy trình key rotation và emergency revocation.
- [ ] Có versioning, thông báo, rollout, rollback và sunset.
- [ ] Có logging/monitoring không làm lộ token hoặc secret.
- [ ] Có đầu mối liên hệ và quy trình xử lý sự cố.

**Điều cần nhớ:** Một hợp đồng JWT tốt là thỏa thuận có thể triển khai và kiểm chứng giữa issuer với từng verifier. Nó phải nói rõ **ai phát hành, ai nhận, token dùng làm gì, cấu trúc và khóa nào được chấp nhận, claim nào bắt buộc, cách xác minh/từ chối và cách thay đổi có kiểm soát**. Nếu một bên vẫn phải tự đoán, hợp đồng chưa đủ rõ.

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): Định dạng JWT, Claims Set và registered claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): Thực hành xác minh JWT, ràng buộc issuer/audience/algorithm và ngăn cross-JWT confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): Profile access token dành cho resource server.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token và quy tắc xác minh cho relying party.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): Cấu trúc JWS và chữ ký/MAC.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): Cấu trúc JWE và mã hóa.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS và tham số khóa.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): Thuật toán JOSE.
- [RFC 2119 — Key words for use in RFCs to Indicate Requirement Levels](https://www.rfc-editor.org/rfc/rfc2119) và [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174): Ý nghĩa các từ khóa yêu cầu như MUST, SHOULD và MAY khi viết đặc tả.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): Thu hồi token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): Kiểm tra trạng thái token.
