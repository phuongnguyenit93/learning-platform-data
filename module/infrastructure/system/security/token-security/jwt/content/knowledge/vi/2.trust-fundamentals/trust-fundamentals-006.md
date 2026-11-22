# Nguồn danh tính, bên phát hành đáng tin cậy và đối tượng nhận

Một JWT chỉ có giá trị bảo mật khi bên nhận hiểu rõ **ai phát hành token**, **token đại diện cho chủ thể nào** và **token được phát hành cho ai sử dụng**. Ba câu hỏi này thường được biểu diễn bằng các khái niệm issuer, subject và audience. Nếu hệ thống xác minh chữ ký nhưng không kiểm tra đúng issuer hoặc audience, token hợp lệ trong một ngữ cảnh vẫn có thể bị sử dụng sai ở ngữ cảnh khác.

Bài học thuộc chương **Nền tảng tin cậy** của module **Security – JSON Web Token (JWT)**. Nội dung áp dụng cho Identity Provider, OAuth Authorization Server, ứng dụng, API và hệ thống phân tán nói chung; không phụ thuộc ngôn ngữ lập trình hoặc framework.

## 1. Ba vai trò cần phân biệt

Trong một luồng xác thực và truy cập API, nhiều bên có thể tham gia. Tên gọi gần nhau nhưng vai trò không giống nhau:

| Vai trò | Ý nghĩa | Câu hỏi tương ứng |
| --- | --- | --- |
| **Identity Provider (IdP)** | Hệ thống xác thực người dùng hoặc cung cấp thông tin về danh tính | Người dùng đã được xác thực bằng cách nào? |
| **Authorization Server** | Hệ thống cấp token và quyết định quyền/ủy quyền theo giao thức | Client được cấp token nào, cho tài nguyên nào và phạm vi nào? |
| **Issuer** | Bên phát hành một token cụ thể; được nhận diện trong JWT qua claim **iss** | Bên nào chịu trách nhiệm phát hành các claims này? |
| **Subject** | Thực thể mà token nói tới; thường là người dùng hoặc workload, được nhận diện bằng **sub** | Token đang đại diện cho ai/cái gì? |
| **Client** | Ứng dụng xin token hoặc sử dụng token để truy cập tài nguyên | Ứng dụng nào đang yêu cầu quyền? |
| **Resource Server / API** | Bên nhận access token và bảo vệ tài nguyên | Token này có dành cho API này và request có được phép không? |
| **Audience** | Tập người nhận dự kiến của token; được biểu diễn bằng claim **aud** | Token được phát hành để bên nào chấp nhận? |

Một tổ chức có thể dùng cùng một sản phẩm cho vai trò IdP và Authorization Server. Tuy nhiên, khi xác minh token, resource server vẫn phải kiểm tra đúng **issuer của token**, đúng hồ sơ token và đúng audience; không suy ra độ tin cậy chỉ từ tên sản phẩm hoặc việc hai hệ thống thuộc cùng công ty.

## 2. Issuer, subject và audience trong JWT

JWT có thể chứa nhiều claims. Ba claim dưới đây là nền tảng để xác định nguồn phát hành, chủ thể và người nhận.

### 2.1. iss — Issuer: ai phát hành?

Claim **iss** (*issuer*) xác định bên phát hành JWT. Theo RFC 7519, giá trị là một chuỗi phân biệt chữ hoa/chữ thường; trong các hệ thống OAuth/OIDC, giá trị thường là định danh dạng URI của authorization server hoặc issuer.

Ví dụ:

~~~json
{
  "iss": "https://identity.example.org"
}
~~~

Resource server phải so khớp **iss** với issuer mà nó đã cấu hình tin cậy. Không chỉ kiểm tra rằng claim này có mặt, không dùng phép so khớp lỏng như kiểm tra chuỗi con, và không tự động tin bất kỳ issuer nào token tự khai báo.

Ví dụ, nếu API chỉ chấp nhận **https://identity.example.org**, các giá trị sau không mặc nhiên tương đương:

- **https://identity.example.org/**
- **https://identity.example.org.evil.example**
- **http://identity.example.org**
- **https://identity.example.org/tenant-b**

Issuer được so khớp theo định danh chính xác mà giao thức/hồ sơ đã quy định. Không tự chuẩn hóa URL, bỏ dấu **/**, đổi chữ hoa/thường hoặc thay scheme trước khi so sánh nếu hợp đồng issuer không quy định điều đó.

### 2.2. sub — Subject: token nói về ai?

Claim **sub** (*subject*) xác định chủ thể mà token đại diện. Chủ thể có thể là:

- Người dùng cuối, ví dụ **user-42**.
- Ứng dụng hoặc workload, ví dụ **billing-worker**.
- Một thực thể khác theo mô hình danh tính của issuer.

Ví dụ:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user-42"
}
~~~

Không nên giả định **sub** là định danh toàn cục duy nhất giữa mọi issuer. Hai issuer khác nhau có thể cùng phát hành **sub = "user-42"** cho hai thực thể hoàn toàn khác nhau. Khi lưu liên kết danh tính, nên dùng cặp **(iss, sub)** làm khóa nhận diện theo issuer, trừ khi hệ thống có một quy tắc định danh toàn cục được xác định rõ.

Trong OpenID Connect, subject identifier có thể là public hoặc pairwise. Pairwise subject giúp cùng một người dùng có định danh khác nhau ở các client/sector để giảm khả năng liên kết hoạt động giữa các ứng dụng. Vì vậy, không nên so sánh **sub** từ hai client khác nhau rồi kết luận đó chắc chắn là cùng một người.

Với token đại diện cho workload hoặc client, **sub** có thể biểu diễn chính ứng dụng thay vì một người dùng cuối. Không được suy ra “có người dùng đã đăng nhập” chỉ vì token có **sub**.

### 2.3. aud — Audience: token dành cho ai?

Claim **aud** (*audience*) chỉ ra người nhận dự kiến của token. Theo RFC 7519, **aud** có thể là một chuỗi hoặc một mảng chuỗi. Các giá trị audience là định danh phân biệt chữ hoa/chữ thường.

Ví dụ token dành cho billing API:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user-42",
  "aud": "https://billing-api.example.org",
  "scope": "invoice:read"
}
~~~

Billing API phải kiểm tra audience có bao gồm định danh của chính nó theo hợp đồng token hay không. Một token được ký đúng nhưng chỉ dành cho payment API không được billing API chấp nhận.

Nếu **aud** là mảng:

~~~json
{
  "aud": [
    "https://billing-api.example.org",
    "https://reporting-api.example.org"
  ]
}
~~~

thì mỗi resource server phải xác minh chính nó nằm trong tập audience được phép và token được cấp cho đúng mục đích. Không nên mở rộng audience chỉ để tiện dùng chung một token cho nhiều API.

**Audience không phải scope.** Audience trả lời token được gửi tới API nào; scope/permission trả lời client hoặc chủ thể được phép thực hiện thao tác nào. Token có **aud** đúng nhưng thiếu **invoice:read** vẫn phải bị từ chối khi gọi chức năng đọc hóa đơn.

### 2.4. Bảng phân biệt nhanh

| Claim | Ý nghĩa | Ví dụ | Kiểm tra bởi |
| --- | --- | --- | --- |
| **iss** | Bên phát hành token | https://identity.example.org | Resource server / client theo hồ sơ token |
| **sub** | Chủ thể được token đại diện | user-42 | Ứng dụng cần thiết lập ngữ cảnh chủ thể |
| **aud** | Người nhận dự kiến | https://billing-api.example.org | Resource server nhận token |
| **client_id** | Ứng dụng OAuth đã yêu cầu token trong một số hồ sơ | web-portal | Resource server/chính sách cần nhận diện client |
| **azp** | Authorized party trong OpenID Connect, thường là client được token phát hành cho | web-portal | OIDC client khi xác minh ID token |
| **scope** | Phạm vi quyền được cấp | invoice:read | Resource server khi quyết định quyền |

Các claim như **client_id**, **azp** và **scope** phụ thuộc hồ sơ token/giao thức. Không giả định mọi JWT đều có chúng hoặc mọi issuer dùng cùng một quy ước.

## 3. Vì sao phải tin issuer trước khi tin claims?

Payload JWT thường có thể đọc được mà không cần khóa. Kẻ tấn công có thể tự tạo một JSON chứa **iss**, **sub**, **aud**, **role** và các claim khác rồi mã hóa Base64url thành chuỗi giống JWT. Việc dữ liệu có cú pháp JWT không chứng minh nội dung được phát hành bởi một bên đáng tin.

Đối với JWS, chữ ký hợp lệ cho biết phần dữ liệu được ký không bị sửa sau khi ký và có thể gắn với bên phát hành khi khóa xác minh được ràng buộc đúng với issuer. Vì vậy, hệ thống cần thiết lập **chuỗi tin cậy của issuer và khóa**, sau đó mới sử dụng claims.

### 3.1. Chuỗi tin cậy ở mức khái niệm

~~~mermaid
flowchart TD
    A["Cấu hình issuer được phép"] --> B["Metadata/discovery từ nguồn tin cậy"]
    B --> C["JWKS gắn với issuer"]
    C --> D["Chọn public key phù hợp"]
    E["JWT nhận được"] --> F["Đọc header chưa tin cậy để chọn ứng viên"]
    D --> G["Xác minh chữ ký bằng thuật toán được phép"]
    F --> G
    G --> H{"Chữ ký hợp lệ?"}
    H -- "Không" --> X["Từ chối"]
    H -- "Có" --> I["Kiểm tra iss, aud, thời hạn và loại token"]
    I --> J{"Claims hợp lệ?"}
    J -- "Không" --> X
    J -- "Có" --> K["Thiết lập ngữ cảnh chủ thể và đánh giá quyền"]
~~~

Metadata và JWKS chỉ đáng tin khi được lấy từ nguồn đã gắn với issuer mà hệ thống cấu hình chấp nhận. Việc một token tự chứa URL khóa không biến URL đó thành nguồn tin cậy.

### 3.2. Cấu hình issuer đáng tin

Resource server nên có một tập issuer được phép theo môi trường và use case:

~~~yaml
allowed_issuers:
  - https://identity.example.org
  - https://partner-id.example.net
~~~

Đây là ví dụ cấu hình minh họa. Trong hệ thống nhiều tenant, danh sách issuer có thể được quản lý theo tenant hoặc theo vùng dữ liệu, nhưng việc thêm issuer phải qua quy trình quản trị và xác minh nguồn.

Các nguyên tắc:

1. Chỉ tin issuer đã được cấu hình/đăng ký theo quy trình kiểm soát.
2. Dùng định danh issuer chính xác theo metadata hoặc hợp đồng đã thiết lập.
3. Lấy khóa xác minh từ JWKS URI gắn với issuer đó qua metadata đáng tin hoặc cấu hình cố định.
4. Xác minh TLS và nguồn phân phối metadata/JWKS; xử lý cache và luân chuyển khóa có kế hoạch.
5. Không cho phép token tự chọn issuer mới, host mới hoặc URL tải khóa bất kỳ.

Nếu hệ thống phục vụ nhiều tổ chức, không được lấy **iss** tùy ý từ request rồi tải discovery document từ Internet. Cách làm này có thể tạo SSRF, đưa khóa của kẻ tấn công vào luồng xác minh hoặc làm hệ thống tin issuer ngoài dự kiến. Hãy tra cứu issuer trong registry/allowlist nội bộ hoặc dùng tenant đã được xác thực để chọn cấu hình.

### 3.3. OIDC Discovery và JWKS

OpenID Connect Discovery cho phép client lấy metadata của OpenID Provider từ một issuer đã biết. Metadata có thể công bố **issuer**, **authorization_endpoint**, **token_endpoint**, **userinfo_endpoint**, **jwks_uri** và các khả năng hỗ trợ.

JWKS URI trả về tập khóa dưới dạng JSON Web Key Set. Client hoặc resource server dùng các khóa công khai phù hợp để xác minh chữ ký token.

Quy trình thiết lập:

1. Ứng dụng biết trước issuer được phép, ví dụ **https://identity.example.org**.
2. Lấy metadata discovery từ địa chỉ được xác định theo quy tắc của giao thức và xác minh issuer trong metadata khớp chính xác issuer dự kiến.
3. Đọc **jwks_uri** từ metadata đáng tin cậy và lấy JWKS qua kết nối an toàn.
4. Cache JWKS theo chính sách HTTP/cache và xử lý **kid** chưa biết bằng cách làm mới có kiểm soát.
5. Khi xác minh token, chỉ chọn khóa từ tập JWKS đã gắn với issuer đó.

Không coi Discovery là cách “tìm issuer bất kỳ do người dùng nhập rồi tin ngay”. Discovery là bước bootstrap metadata cho một issuer mà ứng dụng đã quyết định tin.

### 3.4. kid là gợi ý chọn khóa, không phải bằng chứng tin cậy

Header JWS có thể chứa:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026-01",
  "typ": "JWT"
}
~~~

**kid** (*Key ID*) giúp chọn một khóa trong JWKS đã được tin cậy. Nó không chứng minh khóa thuộc issuer, không tự xác thực chữ ký và không cho phép tải khóa từ một URL tùy ý.

Khi **kid** không tìm thấy:

- Có thể làm mới JWKS từ nguồn issuer đã cấu hình, có giới hạn tần suất và timeout.
- Nếu vẫn không tìm được khóa hợp lệ, từ chối token.
- Không thử tải khóa từ URL do token chưa xác minh tự cung cấp.
- Không bỏ qua xác minh chữ ký chỉ vì JWKS tạm thời không truy cập được.

Các header như **jku** hoặc **x5u** có thể chứa tham chiếu tới tài nguyên khóa/chứng chỉ trong một số dạng JOSE. Không tự động theo các URL này từ token không tin cậy. Nếu hệ thống có hỗ trợ, nguồn và cách sử dụng phải bị giới hạn bởi chính sách tin cậy đã cấu hình.

## 4. Audience bảo vệ API khỏi token bị dùng sai nơi

Audience là ranh giới giữa token và resource server. Cùng một issuer có thể phát hành nhiều loại token cho nhiều API. Tin issuer không có nghĩa mọi token của issuer đều được mọi API chấp nhận.

### 4.1. Một issuer, nhiều audience

Ví dụ một authorization server phát hành token cho:

- Billing API: **https://billing-api.example.org**
- Payment API: **https://payment-api.example.org**
- Reporting API: **https://reporting-api.example.org**

Một token dành cho Billing API:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user-42",
  "aud": "https://billing-api.example.org",
  "scope": "invoice:read",
  "exp": 2000000000
}
~~~

Nếu token này được gửi tới Payment API, Payment API phải từ chối vì audience không phù hợp, ngay cả khi:

- Chữ ký được xác minh thành công.
- Issuer nằm trong allowlist.
- Token chưa hết hạn.
- **sub** là người dùng hợp lệ.

Mỗi điều kiện bảo vệ một khía cạnh riêng. Chấp nhận issuer không thay thế kiểm tra audience; audience đúng không thay thế kiểm tra scope hoặc quyền trên tài nguyên.

### 4.2. Audience và scope kết hợp với nhau

Giả sử một token có:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user-42",
  "aud": "https://billing-api.example.org",
  "scope": "invoice:read",
  "exp": 2000000000
}
~~~

Token có thể được chấp nhận ở Billing API nhưng chỉ có scope đọc hóa đơn. Các trường hợp sau vẫn phải bị từ chối:

- Gọi Payment API: sai audience.
- Gọi Billing API để sửa hóa đơn: thiếu scope **invoice:write**.
- Đọc hóa đơn thuộc tenant khác: không đủ quyền trên tài nguyên, dù scope đọc đúng.
- Dùng token sau **exp**: hết hạn.

Audience xác định **nơi token được dùng**; scope và chính sách tài nguyên xác định **việc gì được phép làm**.

### 4.3. Một token nhiều audience có nên dùng?

JWT cho phép **aud** là mảng, và một số hệ thống có lý do hợp lệ để phát hành token cho nhiều resource server. Tuy nhiên, nhiều audience làm tăng số nơi có thể chấp nhận cùng một credential. Nếu một API bị xâm nhập hoặc token bị lộ, phạm vi sử dụng có thể rộng hơn.

Ưu tiên cấp token cho một resource server hoặc một nhóm người nhận có cùng ranh giới tin cậy và mục đích. Chỉ dùng nhiều audience khi:

- Hợp đồng token quy định rõ tất cả người nhận.
- Mỗi resource server kiểm tra chính nó có trong audience.
- Các quyền và dữ liệu được chia sẻ có chủ đích.
- Có đánh giá tác động khi một bên nhận bị xâm nhập.

Không dùng audience wildcard hoặc giá trị chung như **all-services** để bỏ qua thiết kế quyền giữa các service.

## 5. Phân biệt ID token và access token theo audience

Trong OpenID Connect, ID token là token dành cho client để truyền thông tin về lần xác thực. Access token là credential để truy cập resource server. Hai token có thể được phát hành bởi cùng issuer và cùng chứa **sub**, nhưng có audience và mục đích khác nhau.

| Tiêu chí | ID token | Access token |
| --- | --- | --- |
| Đối tượng nhận | OIDC client có **client_id** tương ứng | Resource server/API được chỉ định |
| Mục đích | Xác nhận thông tin xác thực và chủ thể cho client | Truy cập API theo quyền được cấp |
| Audience | Thường là **client_id** của ứng dụng | Định danh resource server hoặc người nhận theo hồ sơ |
| Kiểm tra chính | Issuer, audience, chữ ký, thời hạn, nonce và các yêu cầu OIDC khác | Issuer, audience, chữ ký/introspection, thời hạn, loại token, scope và quyền |
| Dùng để gọi API? | Không dùng thay access token | Có, tại API đúng audience |

### 5.1. azp trong ID token

Trong OpenID Connect, **azp** (*authorized party*) xác định bên được ID token phát hành thay mặt trong một số trường hợp. Khi ID token có nhiều giá trị audience, client cần áp dụng quy tắc OIDC về **azp**; nếu **azp** hiện diện, client phải xác minh nó phù hợp với **client_id** của mình.

**azp** không phải claim thay thế **aud**, cũng không phải claim phân quyền API. Không dùng **azp** của ID token như cách xác minh audience của access token trừ khi hồ sơ token cụ thể quy định rõ.

### 5.2. Ví dụ token substitution

Giả sử frontend nhận ID token:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user-42",
  "aud": "web-client-123",
  "exp": 2000000000
}
~~~

Frontend gửi ID token này tới Billing API. Nếu Billing API chỉ kiểm tra chữ ký và **sub**, nó có thể nhầm ID token là access token. Cách xử lý đúng là Billing API chỉ chấp nhận access token theo hồ sơ đã cấu hình, với audience dành cho Billing API và các claims quyền phù hợp.

Đây là lý do resource server cần phân biệt rõ **loại token**, không chỉ kiểm tra token được ký bởi một issuer quen thuộc.

## 6. Nguồn danh tính trong hệ thống nhiều tenant và nhiều issuer

Một hệ thống SaaS có thể hỗ trợ nhiều tổ chức đăng nhập qua các IdP khác nhau. Mỗi tenant có thể có issuer, chính sách, tập khóa và định dạng subject riêng.

### 6.1. Không nhận diện người dùng chỉ bằng sub

Ví dụ:

| Issuer | Subject | Danh tính theo hệ thống |
| --- | --- | --- |
| https://idp-a.example.org | employee-17 | Nhân viên của tổ chức A |
| https://idp-b.example.net | employee-17 | Nhân viên của tổ chức B |

Hai **sub** giống nhau nhưng thuộc hai issuer khác nhau. Nếu ứng dụng chỉ lưu **sub=employee-17**, có thể liên kết nhầm tài khoản hoặc cấp quyền chéo tenant.

Nên định danh chủ thể theo cặp issuer/subject hoặc một ánh xạ nội bộ đã được xác minh:

~~~text
external_identity = (issuer, subject)
internal_account = lookup_verified_mapping(external_identity)
~~~

Không tự động tạo liên kết tài khoản chỉ vì email, tên hiển thị hoặc **sub** trùng nhau. Nếu cần account linking, phải có quy trình xác minh quyền kiểm soát cả hai danh tính và chính sách chống chiếm đoạt tài khoản.

### 6.2. Chọn issuer theo tenant một cách an toàn

Một số hệ thống chọn issuer dựa trên tenant hoặc domain đăng nhập. Cần đảm bảo:

- Tenant đã được xác định từ nguồn đáng tin và người dùng có quyền vào tenant đó.
- Issuer được lấy từ registry tenant đã quản trị, không phải URL tùy ý do client gửi.
- Sau khi chọn issuer, token phải có **iss** khớp chính xác issuer được chọn.
- Khóa xác minh, audience, thuật toán và loại token được cấu hình riêng hoặc kế thừa theo chính sách rõ ràng.
- Không cho một tenant sử dụng token của tenant khác chỉ vì cả hai issuer cùng thuộc một hệ thống.

### 6.3. Subject có thể là người dùng hoặc workload

Trong OAuth Client Credentials, token có thể đại diện cho client/workload. Một service gọi API khác không nhất thiết có người dùng cuối. API nhận phải hiểu **sub**, **client_id**, actor/delegation và scope theo hồ sơ token.

Không giả định mọi **sub** là user ID trong cơ sở dữ liệu. Nếu API cần biết request được thực hiện bởi workload nào và thay mặt người dùng nào, phải dùng claims/extension được định nghĩa rõ, kiểm tra issuer và bảo đảm nguồn phát hành có quyền đưa ra các khẳng định đó.

## 7. Quy trình xác minh issuer và audience tại Resource Server

Một quy trình xác minh JWT có thể được tổ chức theo các bước sau:

1. **Xác định loại token được endpoint chấp nhận.** Ví dụ endpoint yêu cầu OAuth access token theo RFC 9068 hoặc một hồ sơ nội bộ đã định nghĩa.
2. **Chọn cấu hình issuer tin cậy.** Dựa trên route, tenant đã xác thực hoặc registry; không tin URL issuer bất kỳ từ token.
3. **Đọc header ở chế độ chưa tin cậy.** Chỉ dùng metadata cần thiết như **kid** để tìm khóa ứng viên trong JWKS đã gắn với issuer.
4. **Xác minh chữ ký/MAC.** Chỉ chấp nhận thuật toán được allowlist và khóa đúng loại/mục đích; nếu không xác minh được thì từ chối.
5. **Xác minh iss.** Giá trị phải khớp chính xác issuer được chấp nhận.
6. **Xác minh aud.** Token phải dành cho resource server hiện tại theo hợp đồng.
7. **Xác minh thời gian và loại token.** Kiểm tra **exp**, **nbf** nếu có, giới hạn tuổi token theo chính sách và **typ**/profile phù hợp.
8. **Kiểm tra claims và quyền.** Scope, client, subject, tenant, actor và các thuộc tính cần thiết phải hợp lệ.
9. **Đánh giá quyền trên tài nguyên.** Kiểm tra hành động, quyền sở hữu, trạng thái dữ liệu và ngữ cảnh.
10. **Thiết lập ngữ cảnh bảo mật.** Chỉ chuyển subject/claims sang phần nghiệp vụ sau khi các bước xác minh bắt buộc hoàn tất.

### 7.1. Pseudocode trung lập ngôn ngữ

~~~text
function accept_access_token(token, request, trusted_config):
    issuer_config = select_config_from_trusted_context(request, trusted_config)
    if issuer_config is missing:
        reject

    untrusted_header = parse_header_without_trusting_it(token)
    candidate_key = issuer_config.jwks.find(untrusted_header.kid)
    if candidate_key is missing:
        refresh_trusted_jwks_with_limits()
        candidate_key = issuer_config.jwks.find(untrusted_header.kid)

    if candidate_key is missing:
        reject
    if untrusted_header.alg not in issuer_config.allowed_algorithms:
        reject
    if not verify_signature(token, candidate_key):
        reject

    claims = read_verified_claims(token)
    if claims.iss != issuer_config.issuer:
        reject
    if request.resource_id not in claims.aud:
        reject
    if token_type_or_profile_is_wrong(token, claims):
        reject
    if token_is_expired_or_not_yet_valid(claims):
        reject
    if not claims_allow_requested_action(claims, request):
        reject
    if not resource_policy_allows(claims.sub, request.resource):
        reject

    accept_with_verified_security_context(claims)
~~~

Đây là pseudocode để mô tả thứ tự và ranh giới tin cậy, không phải thư viện xác minh hoàn chỉnh. Trong triển khai thực tế, cần tuân thủ profile token, xử lý **aud** đúng kiểu chuỗi/mảng, kiểm tra các claim bắt buộc, thuật toán, khóa, lỗi parse, thời gian và chính sách thu hồi.

### 7.2. Lưu ý khi hệ thống hỗ trợ nhiều issuer

Nếu token có thể đến từ nhiều issuer:

- Chọn issuer bằng cấu hình đã đăng ký, tenant đã xác thực hoặc cơ chế định tuyến tin cậy.
- Nếu đọc **iss** chưa xác minh để tra cứu cấu hình, chỉ dùng nó như **gợi ý tra cứu trong allowlist**, sau đó phải xác minh chữ ký và so khớp **iss** chính xác.
- Không tạo discovery request hoặc JWKS fetch tới host tùy ý dựa trên **iss**, **jku** hoặc **x5u** chưa tin cậy.
- Không dùng chung cache JWKS giữa các issuer nếu không gắn namespace/nguồn rõ ràng.
- Không cho cùng một **kid** ở hai issuer khiến khóa bị nhầm lẫn; **kid** chỉ có ý nghĩa trong tập khóa của issuer tương ứng.
- Áp dụng cùng một hồ sơ token rõ ràng cho mọi issuer hoặc cấu hình riêng theo từng issuer; không hạ tiêu chuẩn kiểm tra cho một issuer vì tiện tích hợp.

## 8. Các kiểu tấn công liên quan issuer và audience

### 8.1. Issuer confusion

API chấp nhận token từ nhiều issuer nhưng chỉ kiểm tra chữ ký bằng một tập khóa dùng chung hoặc không kiểm tra **iss**. Kẻ tấn công có thể đưa token do issuer khác phát hành, vốn hợp lệ ở hệ thống khác, vào API.

**Phòng tránh:** gắn khóa với issuer cụ thể, xác minh **iss** chính xác, tách cấu hình và cache theo issuer, không tin khóa chỉ dựa trên **kid**.

### 8.2. Audience confusion / token substitution

Một access token dành cho API A bị gửi sang API B. Nếu B chỉ kiểm tra issuer và chữ ký, B có thể chấp nhận token vốn không dành cho mình.

**Phòng tránh:** mỗi resource server xác minh **aud** có chứa chính nó; dùng audience hẹp và token theo mục đích.

### 8.3. ID token bị dùng như access token

ID token được ký đúng bởi IdP nhưng dành cho client, không phải API. Resource server bỏ qua loại token và **typ**/claims cần thiết rồi chấp nhận vì thấy chữ ký hợp lệ.

**Phòng tránh:** phân biệt token theo profile và các quy tắc cụ thể; ID token phải được client xác minh theo OIDC, access token phải được resource server xác minh theo hồ sơ access token.

### 8.4. Confused deputy

Một service có quyền rộng nhận token hợp lệ nhưng không kiểm tra audience hoặc chủ thể/actor đúng ngữ cảnh. Service bị lừa sử dụng quyền của chính nó để truy cập tài nguyên mà bên gọi không được phép.

**Phòng tránh:** ràng buộc token với audience, scope và client/actor; kiểm tra delegation; không biến khẳng định của caller thành quyền của service.

### 8.5. Issuer discovery tùy ý và SSRF

API đọc **iss** từ JWT chưa xác minh rồi gọi **/.well-known/openid-configuration** hoặc JWKS ở host đó. Kẻ tấn công đặt issuer trỏ tới server do mình kiểm soát hoặc địa chỉ nội bộ, khiến API tải khóa tùy ý hoặc tạo SSRF.

**Phòng tránh:** registry issuer được phép, chặn host/private IP không phù hợp, không thực hiện network fetch tùy ý theo token, cache metadata theo cấu hình và xác minh issuer trong metadata.

### 8.6. Key confusion và thuật toán không phù hợp

API chọn khóa/thuật toán theo header chưa tin cậy mà không ràng buộc loại khóa và allowlist. Ví dụ, hệ thống nhầm khóa công khai RSA thành secret HMAC hoặc cho phép thuật toán không an toàn.

**Phòng tránh:** allowlist thuật toán, kiểm tra loại khóa và mục đích (**use**, **key_ops**, **alg** khi có), tách cấu hình JWS/JWE và làm theo RFC 8725.

## 9. Tình huống thực tế

### Tình huống A — Token đúng issuer nhưng sai audience

Identity Provider ký token cho Reporting API. Người dùng gửi token đó tới Billing API. Billing API xác minh chữ ký thành công và nhận ra issuer quen thuộc, nhưng phải từ chối vì **aud** không bao gồm Billing API.

**Bài học:** issuer đáng tin không có nghĩa mọi token từ issuer đều dành cho mọi API.

### Tình huống B — Hai tenant có cùng subject

Tenant A và tenant B cùng có **sub = "admin"**. Ứng dụng chỉ dùng **sub** làm khóa tài khoản nên có thể liên kết nhầm hai người dùng.

**Bài học:** định danh ngoài cần gắn với issuer, thường dùng (**iss**, **sub**) và ánh xạ tenant đã xác minh.

### Tình huống C — Tin jku do token gửi lên

Một token giả đặt **jku** tới JWKS do kẻ tấn công lưu trữ, rồi ký token bằng khóa riêng của mình. API tải JWKS đó và xác minh chữ ký thành công.

**Bài học:** chữ ký chỉ có ý nghĩa khi khóa xác minh đến từ nguồn đã tin; không để token quyết định nguồn khóa.

### Tình huống D — ID token được gửi tới API

Frontend gửi ID token có **aud = web-client-123** tới Payment API. Payment API chỉ kiểm tra **iss** và chữ ký rồi chấp nhận.

**Bài học:** API cần access token dành cho chính nó; kiểm tra issuer và chữ ký chưa đủ.

### Tình huống E — Một issuer phục vụ nhiều client

Issuer phát hành ID token có nhiều audience. Client bỏ qua quy tắc OIDC về **azp**, khiến token được phát hành cho authorized party khác bị sử dụng nhầm.

**Bài học:** client xác minh ID token theo đầy đủ OpenID Connect Core, bao gồm **aud**, **azp** khi áp dụng, **nonce** và các kiểm tra khác.

### Tình huống F — Tenant do client tự chọn issuer

Ứng dụng nhận tham số **issuer_url** từ query string và tải metadata/JWKS từ địa chỉ đó. Kẻ tấn công đưa URL tới máy chủ nội bộ, tạo SSRF.

**Bài học:** issuer phải được quản trị và chọn từ registry tin cậy; dữ liệu client chỉ là đầu vào cần xác thực.

## 10. Checklist thiết kế và xác minh

### Thiết lập nguồn tin cậy

- [ ] Có danh sách issuer được phép và quy trình đăng ký/loại bỏ issuer.
- [ ] Issuer được chọn từ cấu hình/tenant đáng tin, không từ URL tùy ý trong token.
- [ ] Discovery metadata và JWKS được lấy từ nguồn gắn với issuer đã xác minh.
- [ ] TLS, cache, timeout và luân chuyển khóa được quản lý.
- [ ] **kid** chỉ dùng chọn khóa trong tập khóa đã tin; không tin URL tải khóa từ header chưa xác minh.

### Xác minh JWT

- [ ] Chỉ chấp nhận loại token/profile mà endpoint yêu cầu.
- [ ] Xác minh chữ ký/MAC bằng thuật toán allowlist và khóa đúng issuer.
- [ ] So khớp **iss** chính xác theo hợp đồng.
- [ ] Kiểm tra **aud** có chứa resource server hiện tại.
- [ ] Kiểm tra **exp**, **nbf** và giới hạn thời gian theo chính sách.
- [ ] Xác minh các claim bắt buộc, **typ** và quy tắc phân biệt ID/access token.
- [ ] Chỉ sử dụng **sub**, **scope**, **client_id**, **azp** sau khi token đã được xác minh theo đúng profile.

### Phân quyền và nhiều tenant

- [ ] Phân biệt audience với scope/permission.
- [ ] Kiểm tra quyền trên hành động và tài nguyên cụ thể.
- [ ] Gắn subject với issuer; không dùng **sub** đơn lẻ làm định danh toàn cục.
- [ ] Chọn issuer theo tenant từ registry tin cậy.
- [ ] Xác định rõ token đại diện user hay workload/client.
- [ ] Có chính sách delegation/actor khi service gọi thay người dùng.

## 11. Tự kiểm tra

| Câu hỏi | Đáp án |
| --- | --- |
| **iss** trả lời câu hỏi nào? | **Ai phát hành token?** |
| **sub** luôn là ID người dùng toàn cục duy nhất không? | **Không.** Subject được định nghĩa trong ngữ cảnh issuer; nên gắn với **iss**. |
| **aud** có giống **scope** không? | **Không.** **aud** xác định người nhận; scope xác định phạm vi quyền. |
| Token có chữ ký hợp lệ và issuer đúng có bắt buộc API phải chấp nhận không? | **Không.** Còn phải kiểm tra audience, thời hạn, loại token, claims và quyền. |
| **kid** có chứng minh khóa thuộc issuer không? | **Không.** Nó chỉ giúp chọn khóa trong nguồn khóa đã tin cậy. |
| API có nên tải JWKS từ URL tùy ý trong JWT không? | **Không.** Nguồn khóa phải được gắn với issuer tin cậy; tránh SSRF và key substitution. |
| ID token có thể dùng thay access token để gọi API không? | **Không.** Hai loại token có audience và mục đích khác nhau. |
| Hai issuer có thể phát hành cùng **sub** không? | **Có.** Vì vậy cần định danh bằng (**iss**, **sub**) hoặc ánh xạ đã xác minh. |
| Token có **aud** đúng có đồng nghĩa request được phép đọc mọi tài nguyên không? | **Không.** API vẫn phải kiểm tra scope, tenant, quyền sở hữu và chính sách tài nguyên. |

## 12. Ghi nhớ

- **Issuer (iss)** là bên phát hành token. Chỉ chấp nhận issuer đã được cấu hình tin cậy và so khớp chính xác.
- **Subject (sub)** là chủ thể token đại diện. Định danh này có ngữ cảnh issuer; không mặc định là user ID toàn cục.
- **Audience (aud)** là người nhận dự kiến. Mỗi resource server phải xác minh token dành cho chính nó.
- **Scope/permission** xác định thao tác được cấp; audience không thay thế phân quyền.
- **Khóa xác minh** phải đến từ nguồn đã gắn với issuer. Discovery, JWKS và **kid** hỗ trợ phân phối/chọn khóa nhưng không tự tạo niềm tin.
- **ID token và access token** có mục đích và audience khác nhau; resource server không dùng ID token thay access token.
- **Nhiều issuer/tenant** đòi hỏi registry, cache và ánh xạ danh tính được phân tách; tránh issuer confusion, audience confusion, token substitution và SSRF.

### Tiêu chuẩn và tài liệu tham khảo

- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7515 – JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 – JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 8414 – OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8707 – Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 – JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9700 – Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
