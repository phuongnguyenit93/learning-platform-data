# Danh sách bên phát hành, đối tượng nhận và loại token hợp lệ

> **Module:** SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)  
> **Chương:** Hợp đồng token  
> **Phạm vi:** Kiến thức bảo mật JWT dùng chung cho hệ thống và giao thức, không phụ thuộc Java, Spring hoặc bất kỳ framework cụ thể nào.

Một dịch vụ có thể kiểm tra thành công chữ ký của JSON Web Token (JWT) nhưng vẫn **không được phép chấp nhận** token đó. Ví dụ: cùng một hệ thống định danh phát hành cả ID token cho ứng dụng đăng nhập và access token cho API. Hai token có thể có chữ ký hợp lệ, cùng nhận diện một người dùng nhưng dành cho **những bên tiếp nhận và mục đích khác nhau**. Cho phép chúng thay thế nhau dẫn đến lỗi xác thực hoặc cấp quyền.

Vì vậy, mỗi bên kiểm tra token cần có **danh sách cho phép (allowlist) rõ ràng** về:

1. **Issuer (bên phát hành):** Ai được phép ký/phát hành token mà dịch vụ tin cậy?
2. **Audience (bên nhận dự kiến):** Token phải được phát hành cho đúng ứng dụng hoặc tài nguyên nào?
3. **Token type / token profile (loại và hồ sơ token):** Dịch vụ chấp nhận loại JWT nào cho đúng chức năng?

**Quy tắc nền tảng:** Một token chỉ hợp lệ tại điểm tiếp nhận khi **tổ hợp issuer + audience + loại token** được hợp đồng của điểm đó cho phép, đồng thời đáp ứng kiểm tra mật mã, thời gian, quyền và các ràng buộc nghiệp vụ khác. Không nên kiểm tra từng trường một cách rời rạc rồi mặc định mọi tổ hợp của chúng đều hợp lệ.

## 1. Phân biệt ba danh sách

| Danh sách | Nguồn biểu diễn trong JWT | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|---|
| Issuer cho phép | Claim chuẩn **iss** | Token do nguồn tin cậy nào phát hành? | https://id.example.com |
| Audience cho phép | Claim chuẩn **aud** | Token được phát hành cho ứng dụng/API nào? | https://api.orders.example.com |
| Loại token cho phép | **typ** của JOSE header; hồ sơ chuẩn hoặc claim riêng theo hợp đồng | Token phục vụ đăng nhập, gọi API hay một quy trình khác? | **at+jwt**, **token_use: access** |

**iss** và **aud** là hai claim đã được định nghĩa trong [RFC 7519](https://www.rfc-editor.org/rfc/rfc7519). **typ** là tham số header trong JOSE/JWT để mô tả kiểu đối tượng. Một số hồ sơ chuẩn, chẳng hạn [RFC 9068](https://www.rfc-editor.org/rfc/rfc9068) dành cho OAuth 2.0 JWT access token, định nghĩa quy tắc cụ thể cho **typ** và các claim. Những trường như **token_use**, **purpose** hoặc **token_kind** là **quy ước riêng của hệ thống**, không phải claim bắt buộc áp dụng cho tất cả JWT.

### 1.1. Issuer không phải audience

- **iss** là định danh của thực thể phát hành, chẳng hạn máy chủ định danh **https://id.example.com**.
- **aud** là định danh bên mà token hướng đến, chẳng hạn API đơn hàng **https://api.orders.example.com**.
- **sub** cho biết token nói về người dùng/thực thể nào, không thay thế **aud**.

Một issuer có thể phát hành token cho nhiều API. API đơn hàng chỉ nên nhận token có **aud** phù hợp với chính nó, ngay cả khi API kho vận cũng tin issuer đó.

### 1.2. Loại token không phải quyền hạn

- **Loại token** trả lời: đây là access token, ID token, token khôi phục hay dạng được hợp đồng cho phép?
- **scope / permissions** trả lời: trong mục đích được phép ấy, người hoặc ứng dụng được thực hiện hành động nào?
- **Quyền đối với đối tượng cụ thể** trả lời: có được đọc đơn hàng số 123 của khách hàng A hay không?

Scope **orders:read** không đủ nếu token có sai audience hoặc sai loại. Ngược lại, đúng audience và loại token cũng chưa đủ nếu thiếu scope hoặc quyền trên tài nguyên đích.

## 2. Thiết kế danh sách issuer được tin cậy

### 2.1. Định danh và nguồn khóa phải gắn với nhau

Bên nhận nên lưu một danh sách issuer cụ thể theo môi trường, chẳng hạn:

| Môi trường | Issuer dự kiến | Nguồn khóa công khai được cấu hình tin cậy |
|---|---|---|
| Production | https://id.example.com | https://id.example.com/.well-known/jwks.json |
| Staging | https://id.staging.example.com | https://id.staging.example.com/.well-known/jwks.json |

Các URL trong bài chỉ là ví dụ minh họa, không phải địa chỉ dịch vụ thực tế. Thông tin nguồn khóa phải đến từ **cấu hình tin cậy hoặc cơ chế discovery đã được thiết lập tin cậy**; không được tự ý tải khóa tại một địa chỉ bất kỳ do token chưa xác thực khai báo.

Một bản ghi issuer nên xác định tối thiểu:

| Thuộc tính | Ý nghĩa |
|---|---|
| **issuer_id** | Chuỗi **iss** chính xác được chấp nhận |
| **key_source** | Nguồn khóa hoặc bộ khóa được ủy quyền cho issuer |
| **accepted_algorithms** | Các thuật toán chữ ký được cho phép với issuer/khóa |
| **supported_profiles** | Các loại token mà issuer có thể phát hành và bên nhận dự kiến xử lý |
| **environment** | Ranh giới môi trường, ví dụ production hoặc staging |
| **rotation_policy** | Cách cập nhật khóa và xử lý token còn hạn khi luân chuyển |

Lưu ý bảo mật:

- So sánh **iss** bằng quy tắc khớp chính xác đã thỏa thuận, không dùng tìm chuỗi con hay khớp tiền tố. Hai định danh khác nhau ở đường dẫn, dấu gạch chéo cuối hoặc tên miền phụ không mặc nhiên tương đương.
- Khóa dùng để kiểm tra chữ ký phải thuộc **đúng issuer**. Nếu nhiều issuer cùng dùng giá trị **kid**, không được coi **kid** là định danh khóa duy nhất trên toàn hệ thống.
- Hạn chế thuật toán theo cấu hình; không chấp nhận thuật toán chỉ vì **alg** trong header yêu cầu. Tránh chấp nhận **alg: none** ở điểm tiếp nhận yêu cầu token có chữ ký hoặc nhầm lẫn giữa thuật toán đối xứng và bất đối xứng.
- Nếu có nhiều issuer, lấy **iss** hoặc **kid** chưa xác minh làm *gợi ý chọn ứng viên trong allowlist* có thể chấp nhận được, nhưng chỉ coi các giá trị là đáng tin sau khi xác minh chữ ký và đối chiếu hợp đồng.
- Không tự động tin các tham số như **jku**, **x5u** hay URL tương tự do token cung cấp để quyết định nơi tải khóa.

### 2.2. Nhiều issuer không có nghĩa là tin mọi token của họ

Một dịch vụ có thể tiếp nhận token từ hai nhà cung cấp danh tính, nhưng không nhất thiết cho phép mọi loại token hoặc mọi audience từ cả hai. Hợp đồng nên mô tả **từng tổ hợp được phép**:

| Điểm tiếp nhận | Issuer được phép | Audience bắt buộc | Loại được phép |
|---|---|---|---|
| API đơn hàng | https://id.example.com | https://api.orders.example.com | JWT access token theo hồ sơ của API |
| API đối tác | https://partner-id.example.org | https://api.partner.example.com | JWT access token theo hồ sơ tích hợp đối tác |

Không suy ra từ việc API đối tác tin **partner-id.example.org** rằng API đơn hàng cũng tự động tin issuer này. Nếu nhiều issuer có cùng một **sub**, định danh người dùng thường phải được xác định trong **ngữ cảnh issuer**, chẳng hạn cặp (**iss**, **sub**), để tránh gộp nhầm hai chủ thể.

## 3. Thiết kế danh sách audience được phép

### 3.1. Audience là định danh bên nhận, không phải tên người dùng

Theo RFC 7519, **aud** có thể là một chuỗi hoặc mảng chuỗi. Ví dụ payload:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-42",
  "aud": "https://api.orders.example.com"
}
~~~

API đơn hàng chỉ chấp nhận nếu **aud** chứa chính xác định danh đã cấu hình cho API đó. API kho vận phải từ chối JWT này dù dùng chung issuer và bộ khóa công khai.

Trường hợp nhiều audience:

~~~json
{
  "aud": [
    "https://api.orders.example.com",
    "https://api.reports.example.com"
  ]
}
~~~

Cả hai API **có thể** được chỉ định là bên nhận, nhưng mỗi API phải tự kiểm tra **aud** của mình, loại token và quyền tương ứng. Việc cấp token cho nhiều API làm tăng phạm vi có thể sử dụng khi token bị lộ; nên chọn audience hẹp khi khả thi và thực sự cần thiết.

### 3.2. Quy tắc cho từng ứng dụng và API

| Điểm tiếp nhận | Audience mong đợi | Token nên nhận | Token cần từ chối |
|---|---|---|---|
| Ứng dụng web OIDC | **client_id** của ứng dụng, ví dụ **storefront-web** | ID token dành cho client theo OIDC | ID token cấp cho client khác; access token dùng như ID token |
| API đơn hàng | https://api.orders.example.com | Access token dành cho API đơn hàng | ID token của ứng dụng web; access token của API khác |
| API kho vận | https://api.inventory.example.com | Access token dành cho API kho vận | Access token dành riêng cho API đơn hàng |
| Dịch vụ xác minh email | Định danh endpoint/dịch vụ xác minh theo hợp đồng | Token xác minh email đúng mục đích | Access token hoặc reset token đưa nhầm vào |

Với **OIDC ID token**, client thường phải kiểm tra **aud** khớp **client_id** của chính mình và thực hiện các kiểm tra OIDC khác khi áp dụng như **azp**, **nonce**, chữ ký và thời hạn. Với API tài nguyên, audience thường là định danh của chính API/tài nguyên. Hai ngữ cảnh này không có cùng danh sách audience.

### 3.3. Những cách so khớp sai

Tránh các quy tắc như sau:

~~~text
SAI: aud chứa chuỗi "orders"                 -> chấp nhận
SAI: aud bắt đầu bằng "https://api."         -> chấp nhận
SAI: issuer hợp lệ nên bỏ qua aud            -> chấp nhận
SAI: client_id hợp lệ nên thay thế kiểm tra aud
~~~

Quy tắc đúng về mặt ý nghĩa:

~~~text
ĐÚNG: aud là chuỗi khớp định danh được phép của bên nhận
HOẶC: aud là mảng chứa chính xác định danh đó
VÀ: tổ hợp issuer + audience + token type được hợp đồng chấp nhận
~~~

Nếu hợp đồng yêu cầu một audience duy nhất hoặc cấm token đa audience, cần kiểm tra thêm điều kiện ấy. Việc **aud** là mảng không tự động cho phép phát hành một token để dùng chung tùy ý giữa các hệ thống.

## 4. Thiết kế danh sách loại token hợp lệ

JWT là một **định dạng mang claim**; không phải mọi JWT đều có thể dùng cho cùng mục đích. Việc dùng chung cấu trúc JSON và cùng thuật toán ký không biến những loại token khác nhau thành tương đương.

| Loại hoặc hồ sơ | Bên tiếp nhận phù hợp | Tiêu chí phân biệt | Ghi chú |
|---|---|---|---|
| **OAuth 2.0 JWT access token** | Resource server/API đích | Hồ sơ RFC 9068 dùng **typ: at+jwt** hoặc **application/at+jwt**, cùng **aud**, **iss**, **client_id**, **scope** và các trường theo hồ sơ | API phải xác minh đúng hồ sơ, không chỉ thấy **scope** |
| **OpenID Connect ID token** | OIDC relying party/client | Claim theo OIDC, **aud** thường là client ID; **nonce** và **azp** khi quy tắc yêu cầu | Không dùng làm access token của API |
| **Token khôi phục mật khẩu dưới dạng JWT** | Dịch vụ xử lý khôi phục đã chỉ định | Audience của dịch vụ khôi phục, mục đích riêng như **purpose: password_reset**, trạng thái yêu cầu | Cần giới hạn thời gian, chống phát lại; đây là thiết kế riêng, không phải loại JWT chuẩn bắt buộc |
| **Token xác minh email dưới dạng JWT** | Điểm xác minh email | Audience, mục đích, email/giao dịch gắn với lần xác minh | Thường cần vô hiệu hóa sau khi dùng |
| **Service-to-service JWT access token** | API đích | Audience của API, loại access token, danh tính client/dịch vụ và quyền được cấp | Không tự động cho quyền của người dùng cuối |

**Refresh token không nhất thiết là JWT**: trong OAuth, nó có thể là một chuỗi opaque. Refresh token được chuyển đến authorization server theo giao thức tương ứng, không phải dùng trực tiếp để gọi resource API. Nếu một hệ thống chọn JWT cho refresh token thì vẫn phải xây dựng hợp đồng tiếp nhận và chống phát lại/thu hồi riêng.

### 4.1. Ý nghĩa của header **typ**

Header JWT:

~~~json
{
  "alg": "RS256",
  "kid": "key-2026-01",
  "typ": "at+jwt"
}
~~~

Ví dụ trên diễn tả JWT access token phù hợp phần **typ** của hồ sơ RFC 9068. Trong những hồ sơ khác, **typ** có thể có giá trị khác, mang tính tùy chọn hoặc sử dụng quy tắc định danh riêng. Giá trị **typ: JWT** chỉ cho biết kiểu tổng quát và **không phân biệt đầy đủ** access token với ID token hoặc các JWT nghiệp vụ.

Do đó, bên nhận phải kiểm tra **typ** theo hồ sơ token mà mình hỗ trợ; nếu hồ sơ có claim mục đích riêng như **token_use** hoặc **purpose**, phải kiểm tra tiếp claim đó **sau khi token được xác minh**. Không sử dụng riêng một trường trong header chưa xác minh làm căn cứ cấp quyền.

### 4.2. Danh sách cho phép nên xuất phát từ chức năng của điểm tiếp nhận

Ví dụ một hệ thống có ba điểm tiếp nhận:

~~~text
orders-api:
    nhận: JWT access token dành cho orders-api
    từ chối: ID token, reset token, access token của inventory-api

oidc-web-client:
    nhận: OIDC ID token dành cho chính client
    từ chối: ID token của client khác; access token dùng thay ID token

account-recovery:
    nhận: token khôi phục do hợp đồng recovery định nghĩa
    từ chối: ID token, access token, token xác minh email
~~~

**Mặc định từ chối** các loại không có trong danh sách. Đừng triển khai một bộ kiểm tra chung chỉ xác minh chữ ký rồi chia sẻ kết quả “đã xác thực” cho mọi loại điểm tiếp nhận: mỗi điểm phải áp dụng hồ sơ của nó.

## 5. Lập sổ đăng ký hợp đồng cho từng điểm tiếp nhận

Một **token contract registry** (sổ đăng ký hợp đồng token) mô tả tập tổ hợp được phép. Nó có thể là tài liệu thiết kế hoặc cấu hình được kiểm soát phiên bản; không nhất thiết phải có một dịch vụ đăng ký riêng.

### 5.1. Bảng hợp đồng mẫu

| Contract ID | Điểm tiếp nhận | Issuer chính xác | Audience chính xác | Token profile |
|---|---|---|---|---|
| **orders-access-v1** | Orders API | https://id.example.com | https://api.orders.example.com | RFC 9068 access token, **typ: at+jwt** |
| **inventory-access-v1** | Inventory API | https://id.example.com | https://api.inventory.example.com | RFC 9068 access token, **typ: at+jwt** |
| **web-id-v1** | Storefront OIDC client | https://id.example.com | **storefront-web** | OIDC ID token |
| **recovery-reset-v1** | Account recovery endpoint | https://id.example.com | https://account.example.com/recovery | JWT theo hợp đồng **password_reset** |
| **partner-reports-v1** | Partner Reports API | https://partner-id.example.org | https://api.partner.example.com/reports | JWT access token theo hợp đồng đối tác |

Bảng cho phép hai contract cùng issuer nhưng **khác audience hoặc loại token**. Nó cũng cho phép một điểm tiếp nhận có nhiều hợp đồng khi chủ đích hỗ trợ nhiều issuer/hồ sơ; khi đó từng bộ điều kiện của **một hợp đồng** phải thỏa mãn trọn vẹn.

### 5.2. Mẫu cấu hình minh họa

~~~yaml
# Ví dụ KHÁI NIỆM; không phải cấu hình của một thư viện cụ thể.
contracts:
  orders-access-v1:
    receiver: orders-api
    issuer: "https://id.example.com"
    allowed_signature_algorithms: ["RS256"]
    trusted_jwks: "https://id.example.com/.well-known/jwks.json"
    audience: "https://api.orders.example.com"
    token_profile: "oauth2-jwt-access-rfc9068"
    accepted_typ: ["at+jwt", "application/at+jwt"]
    authorization:
      required_scope_for_read: "orders:read"
      resource_policy: "caller_can_read_requested_order"

  recovery-reset-v1:
    receiver: account-recovery
    issuer: "https://id.example.com"
    allowed_signature_algorithms: ["RS256"]
    trusted_jwks: "https://id.example.com/.well-known/jwks.json"
    audience: "https://account.example.com/recovery"
    token_profile: "application-password-reset-jwt"
    required_purpose: "password_reset"
    replay_policy: "single_use"
~~~

Với hợp đồng access token theo RFC 9068, danh sách **accepted_typ** minh họa hai dạng đã được hồ sơ chấp nhận. Hợp đồng recovery là **quy ước ứng dụng**: cần định nghĩa rõ cách phân biệt token, claim bắt buộc, cách xử lý **jti** và trạng thái yêu cầu khôi phục; không suy ra từ RFC 9068.

**Tránh nhầm lẫn danh sách độc lập với danh sách tổ hợp:** Nếu lưu riêng 3 issuer, 5 audience và 4 token type rồi kiểm tra từng trường có nằm trong một danh sách tổng hay không, hệ thống có thể vô tình cho phép \(3 \times 5 \times 4\) tổ hợp, trong khi chỉ một số tổ hợp là hợp lệ. Sổ đăng ký phải gắn chúng theo **contract ID/điểm tiếp nhận**, không lấy tích Descartes tùy ý.

### 5.3. Những thuộc tính nên có ngoài bộ ba chính

| Thuộc tính | Lý do cần thiết |
|---|---|
| **Điểm tiếp nhận và chủ sở hữu** | Rõ dịch vụ nào được quyền thực hiện kiểm tra và ai quản lý hợp đồng |
| **Thuật toán/nguồn khóa** | Tránh tin nhầm chữ ký hoặc khóa của issuer khác |
| **Thời gian hiệu lực** | Kiểm tra **exp**, **nbf**, **iat** theo hồ sơ và chính sách; giới hạn dung sai đồng hồ |
| **Scope và quyền tài nguyên** | Tránh token đúng loại nhưng được dùng quá quyền |
| **Tenant / môi trường** | Phân tách khách hàng, tổ chức và staging/production khi cần |
| **Cơ chế chống phát lại/thu hồi** | Quan trọng với token một lần, quy trình nhạy cảm hoặc token cần vô hiệu hóa sớm |
| **Quy tắc lỗi và giám sát** | Từ chối an toàn, ghi lý do có kiểm soát để phát hiện cấu hình sai/lạm dụng |
| **Quy trình thay đổi phiên bản** | Cho phép triển khai có kiểm soát khi thêm issuer, audience hoặc profile mới |

## 6. Luồng kiểm tra theo một hợp đồng cụ thể

~~~mermaid
flowchart TD
    A[Nhận token tại một điểm tiếp nhận] --> B[Chọn tập contract được cấu hình cho điểm này]
    B --> C[Phân tích cấu trúc chưa tin cậy]
    C --> D[Chọn issuer/khóa ứng viên từ tập đã tin cậy]
    D --> E{Chữ ký và thuật toán hợp lệ?}
    E -->|Không| R[Từ chối]
    E -->|Có| F{iss khớp issuer của contract?}
    F -->|Không| R
    F -->|Có| G{aud khớp bên nhận của cùng contract?}
    G -->|Không| R
    G -->|Có| H{Đúng loại và hồ sơ token?}
    H -->|Không| R
    H -->|Có| I{Thời hạn, quyền và ràng buộc khác hợp lệ?}
    I -->|Không| R
    I -->|Có| J[Cho phép thực hiện thao tác tương ứng]
~~~

Sơ đồ mô tả trình tự kiểm tra mang tính khái niệm; triển khai có thể sắp xếp các bước kiểm tra không tạo tác dụng phụ theo thư viện/giao thức, nhưng **không được sử dụng các claim chưa xác minh để cấp quyền**.

Pseudocode kiểm tra theo contract:

~~~text
validate(token, receiver, operation):
    contracts = trustedRegistry.forReceiver(receiver)
    reject nếu không có contract cho receiver

    header, claims = parseAsUntrusted(token)
    reject nếu định dạng hoặc kích thước không hợp lệ

    for contract in contracts:
        nếu header.alg không thuộc contract.allowedAlgorithms:
            continue
        keys = trustedKeysFor(contract.issuer, header.kid)
        nếu không xác minh được chữ ký bằng khóa/thuật toán hợp lệ:
            continue
        nếu claims.iss != contract.issuer:
            continue
        nếu claims.aud không chứa chính xác contract.audience:
            continue
        nếu không khớp contract.tokenProfile:
            continue
        nếu các claim thời gian và claim bắt buộc không hợp lệ:
            continue
        nếu scope, tenant, quyền tài nguyên hoặc ràng buộc quy trình không đạt:
            continue
        return ACCEPT

    return REJECT
~~~

Mỗi vòng lặp thử **đầy đủ một contract**; không lấy issuer khớp từ contract A rồi ghép audience khớp từ contract B và loại token khớp từ contract C.

### 6.1. Các điểm cần tránh khi triển khai

- **Không dùng JWT payload chưa xác minh** để thiết lập danh tính, mở quyền, chọn tenant hay quyết định hành động nghiệp vụ.
- **Không lấy khóa từ URL tùy ý do header cung cấp.** Chỉ dùng nguồn đã được ủy quyền cho issuer dự kiến, kiểm soát giao thức và quyền truy cập nguồn khóa.
- **Không chọn thuật toán dựa hoàn toàn vào header.** Ràng buộc thuật toán với khóa và contract; không cho phép hoán đổi các loại thuật toán để qua mặt xác minh.
- **Không chuyển tiếp token sang tài nguyên khác chỉ vì issuer giống nhau.** Nếu một dịch vụ cần gọi API B, phải dùng cơ chế cấp/trao đổi token phù hợp với audience B.
- **Không coi một JWT có chữ ký là được giữ bí mật nội dung.** Payload của JWT ký thông thường có thể đọc được sau khi Base64url decode. Nếu có yêu cầu bảo mật nội dung, cần giao thức mã hóa/phân phối phù hợp; nếu dùng JWE thì bên nhận phải giải mã/xác thực theo chính sách trước khi xét claim.
- **Không cho refresh token hoặc token nghiệp vụ khác đi qua validator access token** trừ khi đó là một hợp đồng mới được thiết kế rõ ràng, với các điều kiện kiểm tra độc lập.

## 7. Tình huống thực tế và ca kiểm thử

Giả sử hệ thống có:

- Issuer production **https://id.example.com**.
- Web client có **client_id = storefront-web**.
- Orders API có audience **https://api.orders.example.com**.
- Inventory API có audience **https://api.inventory.example.com**.
- Điểm khôi phục tài khoản có audience **https://account.example.com/recovery**.

Hệ thống ký access token bằng khóa phù hợp và có các loại token khác nhau. Kết quả mong đợi:

| Ca | Token được đưa vào | Bên tiếp nhận | Kết quả | Điều kiện quyết định |
|---|---|---|---|---|
| A | Access token đúng **iss**, **aud**, **typ**, thời hạn và scope | Orders API | **Có thể chấp nhận** | Còn phải kiểm tra quyền trên đơn hàng cụ thể |
| B | Access token cho Inventory API | Orders API | **Từ chối** | Audience sai |
| C | ID token của **storefront-web** | Orders API | **Từ chối** | Loại và audience không phù hợp |
| D | Access token cho Orders API | OIDC web client tại bước kiểm tra ID token | **Từ chối** | Access token không phải ID token |
| E | Token khôi phục mật khẩu ký hợp lệ | Orders API | **Từ chối** | Sai loại và bên nhận |
| F | Access token có đúng audience nhưng **iss** là issuer staging | Orders API production | **Từ chối** | Issuer ngoài allowlist production |
| G | Token đúng **iss/aud/typ**, nhưng thuật toán ngoài allowlist | Orders API | **Từ chối** | Chính sách xác minh chữ ký |
| H | Token đúng **iss/aud/typ**, thiếu **orders:create** | Endpoint tạo đơn hàng | **Từ chối** | Thiếu quyền thao tác |
| I | Token đúng mọi claim cần thiết nhưng đã hết hạn | Orders API | **Từ chối** | **exp** |
| J | Token có **aud** là mảng, chứa Orders API; hồ sơ cho phép multi-audience | Orders API | **Có thể chấp nhận** | Phải tiếp tục kiểm tra type/scope/quyền |
| K | Token có **aud** khớp bằng tiền tố nhưng không khớp chuỗi chính xác | Orders API | **Từ chối** | So khớp audience không an toàn |
| L | Token đúng issuer và audience từ contract A nhưng loại token chỉ được cho phép ở contract B | Orders API | **Từ chối** | Không ghép các điều kiện giữa hợp đồng |

### 7.1. Tình huống nhiều issuer và nhiều tenant

Một SaaS có thể cho phép khách hàng doanh nghiệp dùng các issuer khác nhau. Mỗi issuer mới phải được duyệt và gắn với đúng client, audience, tổ chức và chính sách kiểm tra. Không nên:

- Tự thêm issuer lấy từ trường **iss** của JWT người dùng gửi.
- Dùng một **sub** không kèm issuer để định danh chung mọi người dùng ở mọi tổ chức.
- Coi “issuer thuộc đối tác đáng tin” là đủ để quyền của đối tác có hiệu lực với mọi tenant hoặc mọi API.

Nếu một API phục vụ nhiều tenant, cần thêm điều kiện xác định tenant của yêu cầu và quyền truy cập tài nguyên. **aud** thường phân biệt dịch vụ tiếp nhận, trong khi quyền dữ liệu từng tenant phải có chính sách kiểm tra riêng.

### 7.2. Thay đổi danh sách có kiểm soát

Khi thêm một issuer, audience hoặc loại token:

1. Xác định **lý do nghiệp vụ** và **điểm tiếp nhận** cần thay đổi.
2. Chốt định danh issuer, nguồn khóa, thuật toán, audience, token profile và ranh giới môi trường.
3. Thêm hoặc cập nhật **từng contract cụ thể**; đánh giá liệu thay đổi có vô tình làm rộng phạm vi tin cậy hay không.
4. Viết kiểm thử chấp nhận đúng token và **kiểm thử từ chối** các token sát ranh giới.
5. Phối hợp triển khai giữa bên phát hành và bên nhận; giám sát các lỗi audience/type/issuer sau phát hành.
6. Khi ngừng dùng issuer/khóa/loại token, có lộ trình loại bỏ cùng chính sách đối với token cũ còn thời hạn.

Không nên biến việc thêm loại token mới thành thao tác “tắt kiểm tra **aud**” hoặc “chấp nhận mọi **typ**”. Một ngoại lệ tương thích ngược phải được mô tả thành hợp đồng tách biệt, có giới hạn và kế hoạch kết thúc.

## 8. Checklist hoàn tất hợp đồng token

Trước khi đưa một điểm tiếp nhận JWT vào vận hành, cần trả lời **có** cho các câu sau:

- [ ] Đã liệt kê chính xác **issuer** nào được tin tại từng môi trường?
- [ ] Mỗi issuer có **nguồn khóa**, **thuật toán** và chính sách luân chuyển khóa phù hợp?
- [ ] Mỗi ứng dụng/API biết rõ **audience** chính xác của mình và kiểm tra cả dạng chuỗi lẫn mảng theo hợp đồng?
- [ ] Đã liệt kê **token profile/type** hợp lệ cho từng điểm tiếp nhận?
- [ ] Các loại token có quy tắc kiểm tra phân biệt; token không được hỗ trợ bị từ chối mặc định?
- [ ] Mỗi hợp đồng gắn **issuer + audience + token type**, không kiểm tra như ba allowlist tổng độc lập?
- [ ] Đã có kiểm tra thời hạn, scope, quyền trên đối tượng, tenant và trạng thái token khi cần?
- [ ] Đã kiểm thử ít nhất các ca sai issuer, sai audience, sai loại, sai thuật toán, hết hạn và thiếu quyền?
- [ ] Quy trình thay đổi hợp đồng, thêm issuer và thu hồi hỗ trợ môi trường được phân công rõ?
- [ ] Không dựa vào claim chưa xác minh hoặc nguồn khóa do bên gửi token tự chỉ định?

**Điểm cần nhớ:** Danh sách issuer cho biết **tin bên phát hành nào**; danh sách audience cho biết **bên nào được nhận token**; danh sách loại token cho biết **nhận token để làm việc gì**. Một token chỉ vượt qua hàng rào đầu vào khi **cả ba điều kiện cùng khớp trong một hợp đồng cụ thể**. Sau đó mới xét đầy đủ thời gian hiệu lực và quyền thực thi tác vụ.

### Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): Các claim **iss**, **aud**, **sub**, **exp**, **nbf**, **iat**, **jti**.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): Giới hạn thuật toán, xác minh issuer/audience, quy tắc rõ ràng cho từng loại JWT và ngăn nhầm lẫn token.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): Hồ sơ JWT access token và **typ: at+jwt**.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, quy tắc audience/client và các kiểm tra OIDC.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): Cách client chỉ định tài nguyên dự kiến để hỗ trợ access token có audience phù hợp.

