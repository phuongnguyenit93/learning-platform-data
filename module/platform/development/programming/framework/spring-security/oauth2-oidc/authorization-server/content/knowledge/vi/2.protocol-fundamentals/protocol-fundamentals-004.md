# Scope, Claim, Audience, Resource và Subject trong OAuth 2.0 / OpenID Connect

## 1. Mục tiêu và bối cảnh

Trong hệ thống dùng **Spring Security** và **Spring Authorization Server**, năm khái niệm **scope**, **claim**, **audience**, **resource** và **subject** xuất hiện cùng nhau ở lúc client xin token, Authorization Server phát hành token và Resource Server kiểm tra token. Chúng trả lời những câu hỏi khác nhau:

| Khái niệm | Câu hỏi chính | Ví dụ trong hệ thống quản lý đơn hàng |
| --- | --- | --- |
| **Scope** | Client đã được cấp **phạm vi quyền** nào? | <code>orders.read</code> |
| **Claim** | Token hoặc nguồn định danh đang **khẳng định thông tin** gì? | <code>sub</code>, <code>iss</code>, <code>aud</code>, <code>email</code> |
| **Audience** | Token **dành cho bên nhận** nào? | <code>https://orders.api.example.com</code> |
| **Resource** | Client muốn truy cập **tài nguyên/API** nào? | Orders API, hoặc một đơn hàng cụ thể |
| **Subject** | Token nói về **chủ thể** nào? | <code>user-42</code>, hoặc client dịch vụ |

Sau bài học, bạn cần có thể đọc một yêu cầu OAuth 2.0/OIDC và JWT, phân biệt năm khái niệm, quyết định nơi kiểm tra từng thông tin, cấu hình ví dụ đơn giản với Spring Authorization Server và Spring Security Resource Server, đồng thời nhận ra các lỗi phân quyền thường gặp.

**Ngữ cảnh xuyên suốt:** Người dùng Alice đăng nhập vào ứng dụng <code>orders-web</code>; ứng dụng gọi Orders API để đọc đơn hàng. Authorization Server phát hành access token. Orders API chỉ chấp nhận token có đúng nguồn phát hành, audience thích hợp và scope <code>orders.read</code>; API tiếp tục kiểm tra Alice có quyền xem đơn hàng đang yêu cầu hay không.

~~~mermaid
sequenceDiagram
    participant U as Alice (Subject)
    participant C as orders-web (Client)
    participant AS as Authorization Server
    participant API as Orders API (Resource Server)
    U->>C: Yêu cầu xem đơn hàng
    C->>AS: Authorization Code + PKCE; scope=openid orders.read
    AS->>U: Xác thực, áp dụng consent/chính sách
    AS-->>C: Authorization code
    C->>AS: Đổi code lấy token với code_verifier
    AS-->>C: Access token (sub, aud, scope...)
    C->>API: GET /api/orders/123 + Bearer access token
    API->>API: Kiểm tra chữ ký, iss, thời hạn, aud, scope
    API->>API: Kiểm tra Alice có quyền với order 123
    API-->>C: Dữ liệu hoặc lỗi 401/403
~~~

Điểm cần nhớ từ đầu: **scope là quyền được cấp, audience giới hạn nơi sử dụng token, subject xác định chủ thể, claim biểu diễn thông tin, resource là đích tài nguyên/API**. Trong JWT, <code>aud</code>, <code>sub</code> và đôi khi cả <code>scope</code> đều được lưu dưới dạng *claims*; đây là những góc nhìn khác nhau, không phải năm loại trường tách biệt.

## 2. Scope: phạm vi được cấp cho client

### 2.1. Scope trong OAuth 2.0

Theo OAuth 2.0, <code>scope</code> là danh sách các chuỗi biểu diễn **phạm vi truy cập** mà client yêu cầu và Authorization Server có thể cấp. Chuỗi scope có ý nghĩa do hệ thống định nghĩa. Ví dụ:

| Scope | Ý nghĩa do hệ thống quy định |
| --- | --- |
| <code>orders.read</code> | Đọc dữ liệu đơn hàng được phép xem |
| <code>orders.write</code> | Thực hiện thao tác sửa đơn hàng được phép sửa |
| <code>inventory.read</code> | Đọc tồn kho |
| <code>openid</code> | Yêu cầu một luồng xác thực **OpenID Connect** |
| <code>profile</code> / <code>email</code> | Các OIDC scope gợi ý nhóm thông tin định danh có thể cung cấp |

Trong request, nhiều scope được phân cách bằng **dấu cách** và khi truyền qua form/URL phải được encode thích hợp, ví dụ <code>scope=openid%20profile%20orders.read</code>. Tên như <code>orders.read</code> không phải hằng số mà Spring tự hiểu: đội phát triển phải thống nhất ý nghĩa, đăng ký scope được phép và thực thi chính sách tại API.

Phân biệt ba thời điểm:

1. **Requested scopes:** Client gửi các quyền mong muốn, ví dụ <code>orders.read orders.write</code>.
2. **Authorized/granted scopes:** Authorization Server áp dụng đăng ký client, người dùng, consent và chính sách; có thể chỉ cấp <code>orders.read</code>.
3. **Enforced scopes:** Resource Server kiểm tra scope **thực sự có trong token hoặc kết quả introspection**, sau đó áp dụng quyền nghiệp vụ.

Không được mặc định mọi scope đã yêu cầu đều được cấp. Việc người dùng đồng ý cũng không thay thế chính sách của API.

### 2.2. Scope khác role, permission và quyền trên một đối tượng

Scope thường thể hiện quyền **đã ủy quyền cho một client/token**; role như <code>ROLE_ADMIN</code> mô tả vai trò trong ứng dụng; permission là cách hệ thống diễn giải quyền cụ thể. Có thể ánh xạ giữa chúng, nhưng không nên xem là cùng một thứ.

Ví dụ, token có <code>orders.read</code> chỉ chứng tỏ client có thể yêu cầu thao tác đọc đơn hàng. Nếu Alice gọi <code>GET /api/orders/123</code>, API còn phải kiểm tra đơn hàng 123 có thuộc tổ chức của Alice hoặc Alice được chia sẻ hay không. Nếu bỏ bước này, hệ thống dễ mắc lỗi **Broken Object Level Authorization (BOLA/IDOR)**.

Với Spring Security Resource Server, JWT có claim <code>scope</code> hoặc <code>scp</code> phù hợp thường được chuyển thành authority dạng <code>SCOPE_orders.read</code>. Authority này giúp kiểm tra ở mức endpoint, còn quy tắc sở hữu dữ liệu nên kiểm tra ở service/domain.

### 2.3. Scope OIDC không đồng nghĩa claim chắc chắn có mặt

<code>openid</code> biến yêu cầu xác thực thành yêu cầu OIDC và cho phép client nhận **ID Token** theo luồng phù hợp. <code>profile</code> và <code>email</code> liên quan đến nhóm thông tin định danh, nhưng dữ liệu được phát hành thực tế còn tùy người dùng, cấu hình, consent và chính sách nhà cung cấp. Không suy luận rằng chỉ cần xin <code>email</code> thì mọi access token luôn có claim <code>email</code>.

## 3. Claim: thông tin được phát biểu về token hoặc chủ thể

**Claim** là cặp tên–giá trị biểu diễn một phát biểu, chẳng hạn <code>"sub": "user-42"</code>. JWT gồm header, payload chứa claims và chữ ký (đối với JWT có ký); claims không mặc nhiên là dữ liệu đáng tin chỉ vì đọc được từ chuỗi JWT. Bên nhận phải kiểm tra chữ ký và toàn bộ điều kiện chấp nhận token.

| Claim | Chức năng thường gặp | Lưu ý bảo mật |
| --- | --- | --- |
| <code>iss</code> | Issuer: bên phát hành | Đối chiếu issuer tin cậy đã cấu hình |
| <code>sub</code> | Subject: định danh chủ thể | Không mặc định là email, tên đăng nhập hoặc user ID toàn cục |
| <code>aud</code> | Audience: bên nhận dự kiến | Phải phù hợp với ứng dụng/API đang kiểm tra |
| <code>exp</code>, <code>nbf</code>, <code>iat</code> | Hết hạn, chưa có hiệu lực, thời điểm phát hành | Kiểm tra thời gian hợp lệ, có độ lệch đồng hồ hợp lý |
| <code>jti</code> | Định danh token | Hữu ích cho theo dõi/chống phát lại tùy thiết kế; tự nó không bảo đảm thu hồi |
| <code>scope</code> | Scope được cấp khi AS biểu diễn vào token | Không đồng nghĩa role hoặc quyền sở hữu từng đối tượng |
| <code>email</code>, <code>email_verified</code> | Thông tin định danh OIDC | Chỉ sử dụng sau xác thực nguồn, kiểm tra ngữ cảnh và tính phù hợp |
| <code>tenant_id</code> | Claim tùy biến trong hệ thống đa tenant | Kiểm tra chéo với quyền truy cập dữ liệu, không tin dữ liệu client tự gửi |

Claims được chia thành **registered claims** trong tiêu chuẩn JWT, **public claims** theo tên đã được xác định và **private/custom claims** do các bên thỏa thuận. Với OIDC, có tập **standard claims** cho thông tin End-User, chẳng hạn <code>name</code>, <code>preferred_username</code> và <code>email</code>. Không phải claim nào cũng bắt buộc trong mọi token.

### 3.1. Đừng nhầm claim trong ID Token với claim trong access token

| Đặc tính | ID Token (OIDC) | Access token (OAuth 2.0) |
| --- | --- | --- |
| Mục đích | Client xác minh sự kiện xác thực và danh tính End-User | Client trình cho Resource Server để truy cập API |
| Bên nhận chính | OIDC Client; <code>aud</code> phải bao gồm <code>client_id</code> | Resource Server/API; audience phụ thuộc định dạng, cấu hình và profile |
| <code>sub</code> | Định danh End-User theo issuer | Chủ thể token theo grant/profile, có thể là End-User hoặc client |
| Scope | Không phải trường bắt buộc của ID Token | Thường xuất hiện trong nội dung JWT access token hoặc kết quả introspection |
| Cách sử dụng | Xây dựng phiên đăng nhập ở client | Gửi dưới dạng <code>Authorization: Bearer ...</code> đến API |

**Không dùng ID Token làm access token để gọi API.** Một ID Token có chữ ký hợp lệ vẫn có audience là client, không phải Orders API. Hơn nữa, access token có thể là chuỗi opaque; phía client không được phụ thuộc vào việc tự giải mã payload.

Một ví dụ *payload rút gọn* của JWT access token (bỏ các claim thời gian và header để tập trung vào khái niệm):

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": ["https://orders.api.example.com"],
  "scope": "orders.read",
  "client_id": "orders-web"
}
~~~

Ví dụ *payload rút gọn* của ID Token được phát hành cho cùng phiên đăng nhập:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "orders-web",
  "email": "alice@example.com",
  "email_verified": true
}
~~~

Hai payload trên chỉ để giải thích **cách đặt audience và subject**; token thật phải có thêm các claim bắt buộc theo chuẩn/profile, ví dụ <code>exp</code>, <code>iat</code> trong ID Token, và phải được kiểm tra đầy đủ. <code>email</code> chỉ là một trường hợp có thể được phát hành khi chính sách cho phép.

### 3.2. Độ tin cậy và tối thiểu hóa dữ liệu

Một JWT có chữ ký hợp lệ cho biết payload được bên sở hữu khóa ký xác nhận và chưa bị sửa trái phép; nó **không tự động** chứng minh nội dung đáp ứng mọi chính sách ứng dụng. Resource Server vẫn phải đánh giá issuer, audience, thời hạn, loại token, scope và quyền nghiệp vụ. Payload JWT được mã hóa Base64URL, **không được mã hóa bí mật** theo mặc định, nên tránh đưa mật khẩu, dữ liệu nhạy cảm hoặc thông tin cá nhân không cần thiết vào access token.

OIDC còn hỗ trợ tham số yêu cầu <code>claims</code> để client nêu những claim muốn nhận. Đó là cơ chế **yêu cầu thông tin định danh**, khác với tham số <code>scope</code> yêu cầu phạm vi truy cập. Yêu cầu claim không đồng nghĩa AS bắt buộc cung cấp nó trong mọi hoàn cảnh.

## 4. Audience: token được gửi đến đúng bên nhận

**Audience** là một hoặc nhiều bên mà token được dự định dành cho. Trong JWT, claim <code>aud</code> có thể có dạng chuỗi hoặc mảng chuỗi theo RFC 7519. Bên nhận JWT phải xác định token có dành cho mình trước khi sử dụng.

Trong ví dụ:

- <code>aud = orders-web</code> trên **ID Token**: OIDC Client <code>orders-web</code> là bên nhận.
- <code>aud = https://orders.api.example.com</code> trên **access token**: Orders API là bên nhận theo quy ước của hệ thống.
- Billing API với audience <code>https://billing.api.example.com</code> phải từ chối access token chỉ dành cho Orders API, kể cả khi JWT có chữ ký đúng và issuer tin cậy.

Các tiêu chuẩn không quy định mọi OAuth 2.0 access token bắt buộc là JWT chứa <code>aud</code>. Nhưng khi chọn **JWT access token profile RFC 9068**, audience là một phần thiết kế bắt buộc và Resource Server cần xác minh. Với token opaque, Resource Server thường dùng **token introspection** hoặc cơ chế máy chủ tương đương để nhận thông tin được cấp, sau đó áp dụng hạn chế audience/resource tương ứng.

Tại sao kiểm tra audience quan trọng? Giả sử hai API cùng tin cậy một Authorization Server. Nếu chỉ kiểm tra chữ ký và <code>iss</code>, Billing API có thể chấp nhận nhầm token được phát hành cho Orders API. Đó là lỗi **token substitution / confused deputy**: một token hợp lệ nhưng được dùng sai đích.

**Audience và scope là hai điều kiện độc lập.** Token có scope <code>orders.read</code> nhưng audience là Billing API không được dùng ở Orders API; token đúng audience nhưng thiếu <code>orders.read</code> cũng không được phép đọc đơn hàng.

## 5. Resource: tài nguyên được bảo vệ và tham số <code>resource</code>

Từ *resource* có ít nhất ba cách dùng tùy ngữ cảnh:

1. **Protected resource:** dữ liệu hoặc thao tác cần bảo vệ, ví dụ đơn hàng số 123.
2. **Resource Server:** dịch vụ lưu trữ/cung cấp protected resource, ví dụ Orders API.
3. **Resource indicator:** một định danh URI trong OAuth 2.0 để client nói token sẽ được dùng ở resource nào, theo **RFC 8707**.

Không nên lấy path dữ liệu cụ thể như <code>/api/orders/123</code> làm audience cho từng token nếu thiết kế đang dùng audience ở cấp API. Khi đó resource indicator ổn định có thể là <code>https://orders.api.example.com</code>, còn quyền với đơn hàng 123 là phép kiểm tra nghiệp vụ.

### 5.1. Phân biệt tham số <code>resource</code> và claim <code>aud</code>

| | <code>resource</code> | <code>aud</code> |
| --- | --- | --- |
| Xuất hiện ở đâu? | Trong yêu cầu authorization/token theo RFC 8707, khi AS hỗ trợ | Trong JWT do AS phát hành |
| Ai nêu giá trị? | Client yêu cầu đích tài nguyên | Authorization Server xác định nội dung token |
| Ý nghĩa | “Tôi cần token cho API này” | “Token này dành cho bên nhận này” |
| Có thể tin ngay? | Không; AS phải xác minh client có quyền yêu cầu resource đó | Resource Server chỉ tin sau khi token được xác thực đầy đủ |

Ví dụ client muốn access token cho Orders API:

~~~http
GET /oauth2/authorize?response_type=code&client_id=orders-web
    &redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback
    &scope=openid%20orders.read
    &resource=https%3A%2F%2Forders.api.example.com
    &state=opaque-state
    &code_challenge=base64url-challenge
    &code_challenge_method=S256
~~~

Đây là ví dụ **giao thức**; các dòng xuống hàng chỉ để dễ đọc. Giá trị <code>state</code> và <code>code_challenge</code> là minh họa, phải được sinh đúng và kiểm tra đúng trong triển khai thật.

**Lưu ý Spring Authorization Server:** Không mặc định rằng chỉ cần client gửi <code>resource</code> thì framework sẽ tự xử lý RFC 8707 và tạo <code>aud</code> theo resource yêu cầu. Khi cần resource indicator, hãy xác nhận mức hỗ trợ trong phiên bản đang dùng và bổ sung kiểm tra yêu cầu, danh sách resource được cấp phép, lưu ngữ cảnh ủy quyền và logic phát hành token thích hợp. Không sao chép trực tiếp URI do client gửi vào <code>aud</code> nếu chưa xác minh.

Một kiến trúc có nhiều API thường nên phát hành **token giới hạn theo audience** riêng cho từng API. Nếu token có nhiều audience, mỗi API có thể vô tình tiếp nhận quyền rộng hơn dự kiến; chỉ làm vậy sau khi đánh giá mô hình tin cậy và quyền truy cập cụ thể.

## 6. Subject: token nói về ai hoặc thực thể nào?

**Subject** thường được biểu diễn bởi claim <code>sub</code>, một định danh **duy nhất trong phạm vi issuer** theo quy tắc của nhà phát hành. Có thể dùng khóa ghép <code>(iss, sub)</code> khi liên kết người dùng giữa nhiều hệ thống; không giả định <code>sub</code> là ID toàn cục. Trong OIDC, <code>sub</code> là định danh End-User, có thể theo kiểu *public* hoặc *pairwise* tùy cấu hình nhà cung cấp.

Không nhầm bốn vai:

| Vai | Trong ví dụ | Ý nghĩa |
| --- | --- | --- |
| Resource Owner / End-User | Alice | Người mà việc truy cập dữ liệu được ủy quyền/xác thực |
| Client | <code>orders-web</code> | Ứng dụng yêu cầu token và gọi API |
| Subject | <code>user-42</code> | Chủ thể được claim <code>sub</code> định danh |
| Resource Server | Orders API | Dịch vụ kiểm tra token, thực thi quyền trên tài nguyên |

Với **Authorization Code + PKCE**, access token có thể biểu thị chủ thể là người dùng Alice; API có thể dùng subject để tìm quyền của Alice. Nhưng với **Client Credentials**, thường **không có End-User**: token biểu thị client/service. Trong JWT access token profile RFC 9068, khi không có resource owner, <code>sub</code> đại diện cho client. Không viết logic “mọi <code>sub</code> đều là user ID” cho mọi grant type.

Nếu hệ thống có một service gọi API thay mặt người dùng, cần thiết kế rõ token đại diện cho người dùng, client hay actor trung gian. Các cơ chế token exchange/delegation có thể biểu diễn thêm actor, nhưng không tự suy từ mỗi <code>sub</code>.

**Không dùng email để thay thế subject**: email có thể đổi, trùng trong phạm vi dữ liệu không mong muốn hoặc chưa được xác minh. Kiểm tra quyền dựa trên định danh ổn định cùng issuer/tenant khi phù hợp.

## 7. Ghép năm khái niệm trong một giao dịch

Giả sử AS phát hành access token cho <code>orders-web</code> sau khi Alice đăng nhập:

~~~text
Client          = orders-web
Subject         = (https://auth.example.com, user-42)
Requested scope = openid orders.read
Granted scope   = orders.read (+ openid trong ngữ cảnh OIDC)
Resource        = https://orders.api.example.com
Access token aud= https://orders.api.example.com
Access token sub= user-42
~~~

Để xử lý <code>GET /api/orders/123</code>, Orders API đi qua nhiều lớp quyết định:

~~~mermaid
flowchart TD
    A["Nhận Bearer access token"] --> B{"Chữ ký / định dạng / issuer / thời hạn hợp lệ?"}
    B -- Không --> U["401 Unauthorized"]
    B -- Có --> C{"Audience chứa Orders API?"}
    C -- Không --> U
    C -- Có --> D{"Có scope orders.read?"}
    D -- Không --> F["403 Forbidden"]
    D -- Có --> E{"Subject được phép xem order 123?"}
    E -- Không --> F
    E -- Có --> G["200 OK: trả dữ liệu được phép"]
~~~

Sơ đồ là **mô hình kiểm tra an toàn**; mã HTTP thực tế phụ thuộc cách API biểu diễn lỗi xác thực, chính sách và việc che giấu tài nguyên. Trong Spring Security mặc định, token không hợp lệ thường trả 401, còn người dùng đã xác thực nhưng thiếu authority thường trả 403.

Một lỗi thường gặp là kiểm tra <code>scope</code> ngay trên client rồi cho phép gọi API. Quyết định bảo mật phải được thực hiện lại **ở phía Resource Server**; dữ liệu client hiển thị chỉ cải thiện trải nghiệm người dùng.

## 8. Áp dụng trong Spring Authorization Server và Spring Security

Các đoạn mã sau minh họa cấu hình **JWT access token cho một API cố định**. Chúng giả định dự án Spring Boot đã thiết lập Authorization Server, client repository, khóa ký JWT/JWK và OIDC theo tài liệu tương ứng. Ví dụ tập trung vào năm khái niệm của bài; các package/import được lược bỏ.

### 8.1. Định nghĩa scope có thể yêu cầu

Đăng ký client với những scope được phép (đoạn trích của quá trình tạo <code>RegisteredClient</code>):

~~~java
RegisteredClient ordersClient = RegisteredClient.withId(clientInternalId)
    .clientId("orders-web")
    .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .redirectUri("https://app.example.com/callback")
    .scope(OidcScopes.OPENID)
    .scope("orders.read")
    .clientSettings(ClientSettings.builder()
        .requireProofKey(true)
        .requireAuthorizationConsent(true)
        .build())
    .build();
~~~

Client này được phép yêu cầu <code>openid</code> và <code>orders.read</code>, không phải mọi scope do client tự nhập. Đây là ví dụ **public client dùng Authorization Code + PKCE**; với BFF/confidential client hãy chọn phương thức xác thực client tương ứng và bảo vệ secret/khóa. Cần cấu hình chính sách phát hành/grant và các thành phần OIDC khác của Authorization Server trước khi chạy luồng hoàn chỉnh.

### 8.2. Gắn audience có kiểm soát vào JWT access token

Với bài toán đơn giản **một client dành cho một API**, có thể ánh xạ client đã đăng ký sang audience cố định bằng <code>OAuth2TokenCustomizer&lt;JwtEncodingContext&gt;</code>:

~~~java
@Configuration
class AccessTokenAudienceConfiguration {
    private static final String ORDERS_API =
        "https://orders.api.example.com";

    @Bean
    OAuth2TokenCustomizer<JwtEncodingContext> accessTokenAudience() {
        return context -> {
            // Không sửa aud của ID Token hoặc loại token khác.
            if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
                return;
            }

            // Chỉ ánh xạ client được phép đến resource đã cấu hình.
            if ("orders-web".equals(context.getRegisteredClient().getClientId())) {
                context.getClaims().audience(List.of(ORDERS_API));
            }
        };
    }
}
~~~

Điều kiện ánh xạ này là một **ví dụ cấu hình cố định**, không phải một trình xử lý RFC 8707 hoàn chỉnh. Trong sản phẩm thực tế, phải thiết kế bảng quyền **client ↔ resource ↔ scope**, xác minh resource client yêu cầu, xử lý việc giảm scope và từ chối yêu cầu không phù hợp trước khi phát hành token. Nếu client có thể truy cập nhiều API, không suy audience đơn giản từ một scope hoặc sao chép nguyên văn tham số <code>resource</code> chưa kiểm tra. Tránh thêm các claim tùy biến nhạy cảm trừ khi Resource Server thật sự cần.

Spring Authorization Server có thể phát hành access token dạng **self-contained (JWT)** hoặc **reference/opaque** tùy <code>TokenSettings</code>. <code>JwtEncodingContext</code> dùng khi phát hành JWT; nếu dùng token opaque, cần cơ chế claims/introspection tương ứng (ví dụ customizer dành cho opaque token), không trông đợi đoạn mã trên chạy trên token không phải JWT.

### 8.3. Resource Server xác minh audience và scope

Orders API sử dụng Spring Security Resource Server để kiểm tra JWT. Ví dụ dưới đây chỉ chấp nhận issuer đáng tin, audience Orders API và authority <code>SCOPE_orders.read</code> tại endpoint đọc đơn hàng:

~~~java
@Configuration
@EnableWebSecurity
class OrdersResourceServerSecurity {
    private static final String ISSUER = "https://auth.example.com";
    private static final String ORDERS_AUDIENCE =
        "https://orders.api.example.com";

    @Bean
    SecurityFilterChain ordersSecurityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(ISSUER + "/oauth2/jwks")
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains(ORDERS_AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                        "Token is not intended for Orders API", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));
        return decoder;
    }
}
~~~

Giải thích từng chốt kiểm soát:

1. <code>withJwkSetUri</code> cung cấp nguồn khóa công khai để kiểm tra chữ ký; URL này phải thực sự thuộc Authorization Server tin cậy. Trong hệ thống thật cần kiểm soát thuật toán ký được cho phép và quy trình xoay khóa.
2. <code>createDefaultWithIssuer</code> kiểm tra issuer và các điều kiện thời gian mặc định, bao gồm token hết hạn.
3. Validator tự viết buộc <code>aud</code> chứa **đúng resource identifier** của Orders API.
4. Spring Security chuyển scope phù hợp thành authority có tiền tố <code>SCOPE_</code> theo cấu hình mặc định; rule trên kiểm tra <code>orders.read</code>.
5. Service xử lý đơn hàng vẫn phải kiểm tra <code>sub</code> (kèm issuer/tenant khi cần) có quyền với từng order. **Scope và audience không tự kiểm tra quyền sở hữu**.

Đây là cấu hình minh họa cho endpoint HTTP Servlet và JWT. Hệ thống cần xử lý riêng các phương thức/endpoint khác, CSRF/session tùy kiến trúc, xử lý lỗi và xác thực đúng loại access token mong đợi. Nếu áp dụng **RFC 9068** hãy kiểm tra đầy đủ cả yêu cầu profile liên quan, không chỉ hai claim <code>iss</code> và <code>aud</code>. Nếu dùng opaque token, thay cơ chế JWT decoder bằng introspection và chính sách audience thích hợp.

### 8.4. Không sửa <code>sub</code> tùy tiện

<code>sub</code> của ID Token phải phản ánh chính sách định danh End-User của OIDC issuer. Với access token, nguồn subject phụ thuộc grant và token profile. Trong token customizer, không gán <code>sub</code> theo <code>userId</code> do HTTP client cung cấp; nếu cần định danh đặc thù, thực hiện ánh xạ từ authentication đáng tin và mô hình subject đã được thiết kế, cùng kiểm thử tính nhất quán giữa các luồng grant.

## 9. Các trường hợp kiểm thử cần có

| Trường hợp | Đầu vào | Kết quả kỳ vọng |
| --- | --- | --- |
| Hợp lệ | JWT do AS tin cậy phát hành; đúng audience, chưa hết hạn, có <code>orders.read</code>; Alice được phép xem order | Cho phép |
| Sai audience | Token cho Billing API được gửi tới Orders API | Từ chối xác thực token, thường 401 |
| Thiếu scope | Đúng audience nhưng không có <code>orders.read</code> | Từ chối quyền đọc, thường 403 |
| Sai issuer/chữ ký | Token bị sửa hoặc phát hành từ issuer không tin cậy | 401 |
| Hết hạn | <code>exp</code> đã qua | 401 |
| Sai chủ sở hữu | Đúng audience và scope nhưng Alice không có quyền với order | 403 (hoặc chính sách che giấu phù hợp) |
| Dùng ID Token gọi API | <code>aud</code> chứa <code>orders-web</code> thay vì Orders API | Không chấp nhận như access token |
| Client Credentials | Token chủ thể là dịch vụ, không có End-User | Áp dụng chính sách service-to-service; không suy ra Alice |
| Xin resource không được phép | Client yêu cầu Billing API dù chỉ đăng ký Orders API | AS từ chối yêu cầu hoặc giảm quyền theo chính sách; không phát hành token sai audience |

Nên có **integration test thực sự đi qua JWT decoder/validator** cho các trường hợp sai issuer, sai audience, sai chữ ký và thời hạn. Trong Spring Security Test, helper <code>jwt()</code> thường dựng Authentication mô phỏng và **bỏ qua** quá trình xác thực chữ ký/audience của decoder, vì vậy chỉ dùng nó để kiểm thử authorization rule, không dùng làm bằng chứng đã kiểm thử token validation.

## 10. Lỗi nhận thức và cách sửa

| Hiểu sai | Cách hiểu đúng |
| --- | --- |
| “Có scope là truy cập được mọi đối tượng.” | Scope chỉ là lớp quyền tổng quát; cần kiểm tra quyền trên từng tài nguyên. |
| “Token ký đúng thì API nào cũng nhận được.” | Mỗi API phải kiểm tra audience, issuer, thời hạn và điều kiện token thích hợp. |
| “<code>aud</code> là client ID trong mọi loại token.” | Với ID Token, audience gồm client ID; với access token cho API, audience thường là Resource Server. |
| “<code>resource</code> và <code>aud</code> luôn giống nhau.” | <code>resource</code> là yêu cầu/định danh đích; AS quyết định audience sau xác minh và ánh xạ. |
| “<code>sub</code> luôn là email/người dùng.” | Subject là định danh theo issuer và grant; client credentials có thể đại diện service. |
| “Scope <code>email</code> chắc chắn làm access token chứa email.” | Scope OIDC và việc phát hành claim phụ thuộc token, consent và chính sách. |
| “Giải mã JWT là đủ.” | Phải xác minh chữ ký, claim bắt buộc, issuer, audience, thời gian và quyền. |
| “ID Token dùng được cho Resource Server.” | ID Token dành cho OIDC Client; API cần access token được cấp cho chính API đó. |
| “Spring Authorization Server tự hiểu mọi <code>resource</code> request.” | Kiểm tra mức hỗ trợ phiên bản và tự triển khai các phần mở rộng còn thiếu. |

## 11. Bài tập áp dụng

Thiết kế hệ thống có <code>catalog-web</code>, Catalog API và Billing API cùng sử dụng một Authorization Server.

1. Đề xuất scope riêng cho quyền đọc sản phẩm và xem hóa đơn, đồng thời chọn resource identifier ổn định cho hai API.
2. Mô tả vì sao token có <code>catalog.read</code> với <code>aud=Catalog API</code> phải bị Billing API từ chối dù có cùng issuer.
3. Nêu khác biệt giữa <code>sub</code> của token Authorization Code khi một khách hàng đăng nhập và token Client Credentials khi một cron job chạy.
4. Viết chính sách cho trường hợp khách hàng A có scope <code>billing.read</code> nhưng cố đọc hóa đơn của khách hàng B.
5. Liệt kê những phép thử thực hiện tại Resource Server và những phép thử phải thực hiện tại Authorization Server khi hỗ trợ tham số <code>resource</code>.

Một thiết kế đạt yêu cầu phải có **kiểm tra riêng** cho quyền của client/token, nơi token được phép sử dụng và quyền của subject trên bản ghi dữ liệu.

## 12. Tài liệu đối chiếu

- [RFC 6749, §3.3 — Access Token Scope](https://www.rfc-editor.org/rfc/rfc6749#section-3.3): phạm vi truy cập trong OAuth 2.0.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc và các registered claims như <code>iss</code>, <code>sub</code>, <code>aud</code>.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): tham số <code>resource</code> và token giới hạn theo resource.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): yêu cầu profile của JWT access token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): cách Resource Server lấy metadata của token (nhất là opaque).
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, subject và standard claims.
- [Spring Authorization Server — Reference](https://docs.spring.io/spring-authorization-server/reference/): client registration, token customization và Authorization Server.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác minh JWT, JWT decoder, authorities và kiểm tra claims.
