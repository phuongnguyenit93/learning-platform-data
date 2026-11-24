# Consent service trong OAuth 2.0 Authorization Server

## 1. Consent service giải quyết vấn đề gì?

Khi người dùng đăng nhập vào một ứng dụng bằng OAuth 2.0/OpenID Connect (OIDC), có thể xuất hiện một màn hình hỏi: **“Bạn có đồng ý cho ứng dụng này xem hồ sơ và đọc danh sách tài liệu của bạn không?”**. Quyết định chấp thuận hoặc từ chối những quyền mà client yêu cầu chính là **authorization consent**.

Trong một **Authorization Server**, consent service là thành phần **tra cứu, ghi nhận và xóa sự chấp thuận** của người dùng dành cho một client theo tập quyền/phạm vi đã được cấp. Nó giúp Authorization Server biết người dùng đã đồng ý điều gì ở các lần cấp quyền trước, từ đó quyết định có cần hỏi lại và có thể tiếp tục luồng ủy quyền trong phạm vi nào.

Bài này thuộc chương **Authorization server** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Kiến thức kết nối với mô hình tin cậy và vòng đời token bảo mật: Authorization Server cấp access token/refresh token; Resource Server xác thực JWT hoặc opaque access token, kiểm tra claims, scope và audience; consent service quản lý lựa chọn của người dùng nhưng **không thay thế** xác thực client, kiểm tra quyền, kiểm soát thời hạn token hay cơ chế thu hồi khi credential bị đánh cắp hoặc phát lại.

**Bối cảnh triển khai:** các đoạn mã Java minh họa Spring Authorization Server trên Spring Security 6 và Spring Boot 3, với Authorization Code + PKCE. Một số extension point và chính sách hiển thị consent phụ thuộc phiên bản và tùy chỉnh của Authorization Server; luôn đối chiếu với dependency thực tế khi đưa vào dự án.

### Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt đăng nhập, client authorization, consent và token issuance.
2. Mô tả điểm consent service tham gia luồng Authorization Code/OIDC.
3. Hiểu bản ghi `OAuth2AuthorizationConsent`, khóa nhận dạng và các `GrantedAuthority` được lưu.
4. Sử dụng `OAuth2AuthorizationConsentService`, `InMemoryOAuth2AuthorizationConsentService` và `JdbcOAuth2AuthorizationConsentService` đúng phạm vi.
5. Thiết kế màn hình consent và API lưu quyết định có chống CSRF, chống tăng quyền và gắn với yêu cầu ủy quyền thực tế.
6. Giải thích xóa consent khác với thu hồi access token/refresh token đang tồn tại như thế nào.
7. Kiểm thử các trường hợp đồng ý một phần, bổ sung scope, từ chối, thu hồi và nhiều client/người dùng.

## 2. Phân biệt bốn quyết định thường bị nhầm lẫn

Hãy xét một người dùng muốn cho ứng dụng `photo-editor` được đọc và chỉnh sửa ảnh lưu tại `photos-api`.

| Khái niệm | Câu hỏi cần trả lời | Thành phần chịu trách nhiệm |
|---|---|---|
| **Authentication** | Người đang thao tác là ai? Đã đăng nhập hợp lệ chưa? | Cơ chế đăng nhập/IdP của Authorization Server. |
| **Client validation** | `photo-editor` có được đăng ký, dùng đúng redirect URI, grant type, PKCE và các scope cho phép không? | Registered client repository và chính sách Authorization Server. |
| **Consent** | Chủ tài khoản có chấp thuận cho client nhận quyền đọc/chỉnh sửa theo yêu cầu này không? | Consent workflow và consent service. |
| **Authorization tại API** | Access token này có hợp lệ, đúng audience/scope và được phép tác động lên ảnh cụ thể không? | Resource Server và business authorization. |

Người dùng **đăng nhập thành công** không có nghĩa họ đã đồng ý cho mọi client dùng dữ liệu. Người dùng **đồng ý** cũng không có nghĩa client được phép xin scope ngoài cấu hình, token được phát hành vĩnh viễn, hoặc Resource Server bỏ qua phân quyền theo đối tượng.

Consent là một **quyết định ủy quyền giữa người dùng và client**, không phải một dạng access token.

### Ví dụ dễ hiểu

Client được đăng ký với scopes `photos.read` và `photos.write`. Trong một request, client chỉ xin `photos.read`.

- Nếu người dùng đồng ý `photos.read`, consent ghi nhận quyền đó.
- Consent không tự động cho `photos.write` chỉ vì client được đăng ký hỗ trợ scope này.
- Khi client xin thêm `photos.write` sau đó, chính sách Authorization Server có thể yêu cầu consent bổ sung.
- Dù đã đồng ý `photos.read`, `photos-api` vẫn phải kiểm access token và quyền truy cập vào album/ảnh cụ thể.

Vì vậy, cần tách rõ **scope được đăng ký**, **scope được yêu cầu**, **scope được consent** và **scope thực sự được cấp trong token**. Bốn tập giá trị này có thể khác nhau.

## 3. Consent nằm ở đâu trong Authorization Code flow?

Luồng phổ biến là ứng dụng web hoặc mobile dùng Authorization Code + PKCE. Người dùng tương tác với Authorization Server qua trình duyệt; Authorization Server xác thực và có thể hiển thị màn hình consent trước khi phát authorization code.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as Client application
    participant B as Trình duyệt
    participant AS as Authorization Server
    participant CS as Consent service
    participant RS as Resource Server

    U->>C: Muốn kết nối tài khoản
    C-->>B: Điều hướng tới /oauth2/authorize<br/>client_id, redirect_uri, scope, state, PKCE
    B->>AS: Authorization request
    AS->>AS: Kiểm client, redirect_uri, scopes, PKCE
    alt Người dùng chưa đăng nhập
        AS-->>B: Yêu cầu đăng nhập
        U->>B: Đăng nhập
        B->>AS: Quay lại authorization request
    end
    AS->>CS: findById(registeredClientId, principalName)
    CS-->>AS: Các quyền đã consent hoặc null
    alt Cần consent
        AS-->>B: Trang hiển thị scopes cần quyết định
        U->>B: Chấp thuận hoặc từ chối
        B->>AS: Gửi lựa chọn kèm state và CSRF protection
        AS->>AS: Xác minh quyết định thuộc request hợp lệ
        opt Người dùng chấp thuận
            AS->>CS: save(consent cập nhật)
        end
    end
    alt Yêu cầu được phê duyệt
        AS-->>B: Redirect tới client với code và state
        B->>C: Gửi code
        C->>AS: /oauth2/token + code_verifier
        AS-->>C: Access token và token khác nếu phù hợp
        C->>RS: Gọi API bằng access token
        RS-->>C: Kiểm token, audience, scope, quyền đối tượng
    else Người dùng từ chối
        AS-->>B: Authorization error, thường access_denied
    end
~~~

**Các điểm mấu chốt trong luồng:**

- Consent được thực hiện trong **authorization interaction**, thường trước khi authorization code được phát hành. Nó không diễn ra trong Resource Server mỗi lần nhận API request.
- Consent service **không tự phát authorization code hoặc access token**. Authorization Server sử dụng kết quả consent trong toàn bộ pipeline cấp quyền.
- Client phải tự kiểm tra `state` ở authorization response để ràng buộc response với phiên yêu cầu của mình. PKCE bảo vệ bước đổi code, còn redirect URI phải khớp cấu hình được phép.
- Các chi tiết xử lý nếu người dùng đồng ý một phần hoặc từ chối phụ thuộc chính sách Authorization Server và semantics scope của client. Không được tự cấp scope mà người dùng chưa chấp thuận nếu chính sách yêu cầu consent.

## 4. Mô hình dữ liệu: OAuth2AuthorizationConsent

Trong Spring Authorization Server, abstraction trung tâm là `OAuth2AuthorizationConsent`. Một consent liên kết **một registered client** với **một principal** và tập authorities đã được chấp thuận.

~~~text
OAuth2AuthorizationConsent
├── registeredClientId : ID nội bộ của RegisteredClient
├── principalName      : định danh principal tại Authorization Server
└── authorities        : tập GrantedAuthority được lưu
                          ví dụ:
                          SCOPE_photos.read
                          SCOPE_photos.write
~~~

**Khóa định danh** thường là cặp `(registeredClientId, principalName)`.

Cần phân biệt:

- `registeredClientId` là ID nội bộ của bản ghi `RegisteredClient`, không nhất thiết bằng chuỗi OAuth `client_id` công khai.
- `principalName` là tên principal mà Authorization Server đang dùng; khi hệ thống có nhiều issuer, tenant hoặc identity provider, phải thiết kế để tên này phân biệt đúng chủ thể, tránh trùng tài khoản.
- `authorities` lưu `GrantedAuthority` đã consent. Trong trường hợp scope thông dụng, giá trị thường được biểu diễn dưới dạng `SCOPE_photos.read`. Các dạng authority khác có thể xuất hiện khi ứng dụng tùy biến; phải xác định semantics trước khi đọc/ghi.

Một bản ghi consent **không phải** thông tin đăng nhập, mật khẩu, khóa ký JWT, access token, refresh token hay trạng thái introspection. Cũng không có nghĩa tất cả các authority đã lưu đều được phát trong mọi token tiếp theo. Authorization Server vẫn phải áp dụng scope request, client registration, chính sách user và token issuance.

### Consent đã có không phải là quyền toàn cục

Giả sử:

~~~text
User: user-123
Client: photo-editor (registeredClientId = rc-photo-9)
Đã consent: [SCOPE_photos.read]

Request mới: scope=photos.read photos.write
~~~

`photos.read` có thể đã được chấp thuận trước đó, nhưng `photos.write` là scope mới cần quyết định theo chính sách. Không được suy rằng người dùng đã đồng ý mọi scope của `photo-editor` vì đã từng bấm “Đồng ý” một lần.

Nếu người dùng A đã đồng ý, quyền đó cũng không được áp dụng cho người dùng B. Nếu client X được chấp thuận, quyền đó không chuyển sang client Y.

## 5. OAuth2AuthorizationConsentService có giao diện nào?

Spring Authorization Server cung cấp giao diện `OAuth2AuthorizationConsentService` với ba hoạt động chính:

~~~java
public interface OAuth2AuthorizationConsentService {
    void save(OAuth2AuthorizationConsent authorizationConsent);
    void remove(OAuth2AuthorizationConsent authorizationConsent);
    OAuth2AuthorizationConsent findById(
        String registeredClientId,
        String principalName
    );
}
~~~

Đây là **hình thức rút gọn để minh họa contract**; mã nguồn thư viện thực tế có thể kèm chú thích nullability/Javadoc.

| Method | Vai trò | Điểm cần lưu ý |
|---|---|---|
| `findById` | Tra cứu consent theo ID registered client và principal. | Trả `null` nếu không tồn tại; cần nhất quán cách nhận dạng principal. |
| `save` | Tạo hoặc cập nhật quyền đã consent. | Chỉ gọi trong luồng/điểm nghiệp vụ đã kiểm chứng lựa chọn của người dùng. |
| `remove` | Xóa consent đã lưu. | Không mặc nhiên thu hồi mọi token đã phát hành trước đó. |

Consent service là **lớp lưu trữ/truy xuất quyết định**, không tự bảo đảm rằng request consent hợp lệ. Kiểm tra request, quyền được yêu cầu, client và người dùng phải được thực hiện bởi Authorization Server và logic xung quanh.

### Không nhầm các service trong Spring Authorization Server

| Thành phần | Dữ liệu quản lý |
|---|---|
| `RegisteredClientRepository` | Client đã đăng ký: `client_id`, redirect URI, grant type, scope và chính sách client. |
| `OAuth2AuthorizationConsentService` | Những authorities/scope người dùng đã consent cho client. |
| `OAuth2AuthorizationService` | Các authorization cùng trạng thái và token thuộc vòng đời cấp quyền. |
| `OAuth2TokenGenerator` và token customization | Tạo biểu diễn token và một số claims theo chính sách. |
| Resource Server | Kiểm tra access token trước khi cho gọi API. |

Ví dụ: xóa một bản ghi consent bằng `remove` không đồng nghĩa record trong `OAuth2AuthorizationService` hay refresh token của client tự biến mất.

## 6. Hai cách triển khai sẵn có: in-memory và JDBC

### 6.1. InMemoryOAuth2AuthorizationConsentService

~~~java
@Bean
OAuth2AuthorizationConsentService authorizationConsentService() {
    return new InMemoryOAuth2AuthorizationConsentService();
}
~~~

Mẫu này thuận tiện trong ví dụ, local development hoặc thử nghiệm. Dữ liệu nằm trong bộ nhớ tiến trình: khởi động lại có thể mất consent; nhiều instance Authorization Server cũng không tự chia sẻ trạng thái.

Với hệ thống production cần consent bền vững hoặc nhiều replica, chọn kho dữ liệu được chia sẻ và cơ chế vận hành phù hợp.

### 6.2. JdbcOAuth2AuthorizationConsentService

~~~java
@Bean
OAuth2AuthorizationConsentService authorizationConsentService(
        JdbcTemplate jdbcTemplate,
        RegisteredClientRepository registeredClientRepository) {
    return new JdbcOAuth2AuthorizationConsentService(
        jdbcTemplate, registeredClientRepository);
}
~~~

Cách này lưu consent vào database qua JDBC. Cần tạo **schema tương thích với đúng phiên bản Spring Authorization Server đang sử dụng**; việc chỉ khai báo bean không tự tạo bảng hoặc cấu hình migration.

Một sơ đồ mang tính khái niệm cho dữ liệu:

~~~text
oauth2_authorization_consent
---------------------------------------------
registered_client_id  (khóa chính thành phần)
principal_name        (khóa chính thành phần)
authorities           (các authorities được serialize)
---------------------------------------------
Unique(registered_client_id, principal_name)
~~~

Trong triển khai JDBC mặc định, mẫu bảng thường sử dụng những tên cột như trên; kiểu dữ liệu và định dạng authorities phải tuân theo schema/mapping đi kèm thư viện. Nếu dùng SQL/JPA triển khai riêng, đừng giả định có thể lưu JSON tùy ý rồi vẫn dùng JDBC mapper mặc định.

**Yêu cầu vận hành:**

- Đảm bảo database migration chạy trước khi Authorization Server phục vụ traffic.
- Quy định backup, retention, xóa dữ liệu theo yêu cầu quyền riêng tư, và quyền truy cập của tài khoản database.
- Với nhiều instance, dùng shared database và xử lý cập nhật đồng thời; tránh mất quyền mới cấp do hai request ghi đè.
- Cân nhắc audit event **ai cấp quyền cho client nào, scope nào, lúc nào**, nhưng giới hạn dữ liệu và thời gian lưu theo chính sách.
- Không log token, mật khẩu hoặc thông tin nhạy cảm vào audit consent; sử dụng ID/correlation ID có kiểm soát.

## 7. Cấu hình client yêu cầu consent

Trong Spring Authorization Server, `ClientSettings.requireAuthorizationConsent` thể hiện chính sách client có yêu cầu sự chấp thuận của người dùng khi đi qua authorization flow hay không.

Ví dụ tạo một confidential client từ cấu hình tin cậy:

~~~java
RegisteredClient photoClient = RegisteredClient
    .withId(UUID.randomUUID().toString())
    .clientId("photo-editor")
    .clientSecret(passwordEncoder.encode(secretFromSecretManager))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .redirectUri("https://photo.example.test/login/oauth2/code")
    .scope("photos.read")
    .scope("photos.write")
    .clientSettings(
        ClientSettings.builder()
            .requireAuthorizationConsent(true)
            .build())
    .build();
~~~

`passwordEncoder`, `secretFromSecretManager` là những giá trị được cung cấp từ cấu hình bảo mật của hệ thống; code trên minh họa cấu hình client, chưa bao gồm bean/service lưu client. Confidential client phải bảo vệ secret ở backend, không nhúng secret vào JavaScript/browser.

Với **public client** (SPA/native) không giữ được secret, dùng phương thức xác thực client phù hợp (ví dụ `ClientAuthenticationMethod.NONE`), cấu hình **Authorization Code + PKCE** đúng cách và áp dụng chính sách refresh token an toàn. Không dùng giả định rằng consent hoặc client ID là thay thế cho PKCE.

**`requireAuthorizationConsent(true)` không có nghĩa hiển thị consent screen ở mọi request, bất kể lịch sử**: quyết định hiển thị thực tế còn xét những scope đã consent, scope mới, yêu cầu OIDC liên quan và các chính sách tùy chỉnh. Với ứng dụng nội bộ first-party, có thể có chính sách không hiện màn hình consent; đó là quyết định về trust/user experience cần được phê duyệt rõ, không phải cơ chế tự tăng quyền.

### Quy tắc tối thiểu trước khi ghi consent

Authorization Server cần xác minh:

1. Principal đang đăng nhập và đủ điều kiện grant các quyền đang xét.
2. Client thực sự tồn tại, `client_id` hợp lệ, redirect URI/grant type/PKCE thỏa điều kiện.
3. Các scope client yêu cầu nằm trong tập scope mà client **được đăng ký**; loại bỏ hoặc từ chối scope không được cấp phép theo policy.
4. Mỗi scope trên form phải thuộc authorization request hiện tại, và giá trị người dùng chọn là một phần của request đó.
5. Yêu cầu xác nhận được ràng buộc với authorization interaction hiện tại; có chống CSRF và chống sửa dữ liệu form.
6. Consent đã lưu chỉ phản ánh những quyền người dùng **thực sự đồng ý**.

Không được quyết định cấp token dựa đơn thuần trên việc trình duyệt gửi `approved=true` hay tự gửi một danh sách scope chưa được kiểm tra.

## 8. Thiết kế màn hình consent có thể hiểu và an toàn

Một màn hình consent tốt phải cho người dùng biết **ứng dụng nào đang xin quyền gì**, trong ngữ cảnh tài khoản nào, và hệ quả của việc đồng ý.

Ví dụ thông điệp:

~~~text
Ứng dụng: Photo Editor
Đang yêu cầu truy cập tài khoản ảnh của bạn:

[✓] Đọc danh sách và nội dung ảnh          (photos.read)
[ ] Tạo, sửa và xóa ảnh                     (photos.write)

[Cho phép những quyền đã chọn]   [Từ chối]
~~~

Trên giao diện thật, nên dùng mô tả scope thân thiện, nhưng phạm vi quyền thực tế vẫn phải dựa vào mã scope chuẩn hóa ở Authorization Server, không dựa vào bản dịch UI.

### Thông tin nào được tin cậy?

- Tên/logo/client metadata nên lấy từ **registered client** đã kiểm soát và escape/sanitize khi hiển thị; không tin tên ứng dụng lấy trực tiếp từ query string tùy ý.
- Danh sách scope hiển thị đến từ authorization request đã được server kiểm tra với registered scopes.
- Identity đang đăng nhập lấy từ server-side authenticated principal; không lấy từ hidden field do client điền.
- `state` do client tạo giúp client đối chiếu authorization response; nó **không thay thế CSRF protection** cho form consent do Authorization Server xử lý.
- Form cần chống clickjacking, XSS, CSRF và ràng buộc quyết định với authorization request còn hiệu lực.
- Nội dung hiển thị chính xác quyền nguy hiểm: `write`, `delete`, `offline_access` hoặc quyền dữ liệu nhạy cảm cần được mô tả minh bạch.

Không nên đưa access token, refresh token, client secret, mã authorization code hoặc khóa ký vào URL của trang consent hay hidden input form.

### Đồng ý một phần và từ chối

Nếu hệ thống hỗ trợ **partial consent**, người dùng có thể chỉ đồng ý `photos.read` trong số các scope đang yêu cầu. Authorization Server phải bảo đảm consent và token cuối cùng phản ánh đúng tập đã được phê duyệt theo policy, đồng thời thông báo tập scope thực sự được cấp nếu cần. Một client có thể không sử dụng được chức năng nào đó nếu thiếu scope cần thiết.

Khi người dùng chọn **Từ chối**, Authorization Server thường trả authorization error như `access_denied` cho client qua redirect URI đã được kiểm tra. Không lưu thêm quyền mới vì người dùng đã từ chối, và không cấp code/token cho phạm vi bị từ chối.

Một số scope hoặc giao thức có yêu cầu bổ sung (đặc biệt OIDC); không triển khai việc bỏ chọn tùy tiện nếu chính sách hoặc đặc tả giao thức quy định xử lý khác.

## 9. Đọc và cập nhật consent bằng API Java

Ví dụ sau minh họa cách làm việc với consent service **sau khi** Authorization Server đã chứng thực người dùng, xác minh client/request và ghi nhận quyết định đồng ý hợp lệ:

~~~java
String registeredClientId = registeredClient.getId();
String principalName = authenticatedUser.getName();

// Đọc quyền trước đó, nếu có.
OAuth2AuthorizationConsent existing =
    consentService.findById(registeredClientId, principalName);

// Giữ các quyền cũ khi chính sách cho phép tích lũy consent.
OAuth2AuthorizationConsent.Builder builder =
    existing != null
        ? OAuth2AuthorizationConsent.from(existing)
        : OAuth2AuthorizationConsent.withId(
            registeredClientId, principalName);

// Đây phải là kết quả đã kiểm tra từ chính authorization request
// và quyết định của người dùng, không phải scope lấy thẳng từ input.
Set<String> approvedScopes = validatedUserApprovedScopes;

for (String scope : approvedScopes) {
    builder.authority(new SimpleGrantedAuthority("SCOPE_" + scope));
}

consentService.save(builder.build());
~~~

Các biến `registeredClient`, `authenticatedUser`, `consentService` và `validatedUserApprovedScopes` đại diện các đối tượng đã có từ pipeline đáng tin cậy. Không sao chép đoạn mã này vào một endpoint công khai cho phép client tự ghi consent; như vậy client có thể tự cấp quyền cho chính mình.

**Lưu ý về semantics:** code trên minh họa kiểu **cộng dồn scope được đồng ý**. Nó không phù hợp nếu thao tác người dùng là **gỡ bỏ** một quyền đã có, hoặc nếu consent chỉ có hiệu lực cho một lần sử dụng. Trong trường hợp đổi hoặc rút bớt quyền, phải xây dựng tập authorities mới theo policy, lưu đúng kết quả và đồng bộ xử lý các authorization/token hiện hữu khi cần.

### Ví dụ khi cần xóa bản ghi consent

~~~java
OAuth2AuthorizationConsent consent =
    consentService.findById(registeredClientId, principalName);

if (consent != null) {
    consentService.remove(consent);
}
~~~

Đây là việc **xóa dấu vết consent đã lưu cho cặp client/principal**. Nó không tự động gọi revoke endpoint, không chủ động hủy refresh token và không bảo đảm access token đã phát hành mất hiệu lực.

### Cạnh tranh ghi dữ liệu

Giả sử hai cửa sổ browser cùng lúc xin thêm các scope khác nhau. Nếu cả hai đọc cùng bản ghi cũ rồi mỗi bên lưu một bản ghi mới, cập nhật đến sau có thể làm mất scope mới được chấp thuận trước đó (**lost update**). Với nhiều instance hoặc traffic cao, cần transaction, optimistic locking hoặc cơ chế merge/serializable phù hợp với schema và policy. Khi loại bỏ quyền, merge thiếu kiểm soát còn có thể vô tình khôi phục quyền vừa bị rút.

Đây là lý do nên xem consent là dữ liệu phân quyền có ảnh hưởng bảo mật, cần kiểm soát tính nhất quán thay vì chỉ là cache giao diện.

## 10. OIDC: consent, scope và offline_access

OpenID Connect bổ sung lớp định danh lên OAuth 2.0. Khi client xin `openid`, authorization flow có thể cấp ID token để client biết kết quả xác thực người dùng; access token vẫn được dùng theo chính sách tài nguyên/API.

Một số scope thường gặp:

| Scope | Ý nghĩa minh họa | Điều cần phân biệt |
|---|---|---|
| `openid` | Yêu cầu xử lý theo OIDC. | Không đồng nghĩa cấp toàn bộ thuộc tính người dùng. |
| `profile` | Xin nhóm thông tin hồ sơ tiêu chuẩn khi được hỗ trợ và policy cho phép. | Không tự cho phép mọi thao tác API. |
| `email` | Xin thông tin email theo chính sách OP. | Không đồng nghĩa email đã được xác minh nếu thiếu claim/chính sách tương ứng. |
| `offline_access` | Xin khả năng truy cập khi người dùng không hiện diện, thường gắn với refresh token. | Có yêu cầu consent và điều kiện riêng theo OIDC/provider; không tự phát refresh token chỉ vì có chuỗi scope này. |
| `photos.read` | Scope API do hệ thống định nghĩa. | Resource Server vẫn phải kiểm audience và quyền từng đối tượng. |

OIDC có các tham số như `prompt=consent` để client yêu cầu OP thu thập consent ngay cả khi có consent trước đó, theo những điều kiện của giao thức và triển khai. Không nên khẳng định mọi phiên bản/provider xử lý giống nhau: có thể cần kiểm tra hành vi tùy chỉnh và quy tắc của OP cụ thể.

**Consent và refresh token:** người dùng đồng ý cho quyền truy cập lâu dài không có nghĩa refresh token vô thời hạn hay không thể thu hồi. Authorization Server phải có chính sách TTL, rotation, phát hiện reuse và revocation riêng. Khi client dùng access token ở Resource Server, API xác thực token và scope tại thời điểm request, không đi hỏi lại màn hình consent mỗi lần.

## 11. Xóa consent khác thu hồi token ra sao?

Đây là khác biệt quan trọng nhất để hiểu vòng đời và biên giới tin cậy:

| Hành động | Tác động trực tiếp | Điều không tự được bảo đảm |
|---|---|---|
| `consentService.remove(consent)` | Xóa quyền đã đồng ý được lưu cho client/principal. | Không làm JWT access token đang còn hạn tự vô hiệu; không tự xóa refresh token. |
| Thu hồi authorization/refresh token | Chặn việc dùng credential tương ứng theo chính sách của Authorization Server. | JWT access token đã cấp có thể vẫn được Resource Server nhận nếu chỉ kiểm chữ ký/`exp` offline. |
| Thu hồi opaque token + introspection | Resource Server có thể thấy `active=false` khi introspect lại. | Cache introspection có thể tạo một khoảng trễ theo cấu hình. |
| Logout phiên đăng nhập OP | Kết thúc session đăng nhập tại Authorization Server/IdP theo phạm vi được chọn. | Không mặc nhiên hủy mọi token đã cấp cho mọi client. |
| Hết hạn access token | Token không còn hợp lệ sau `exp`, trừ clock skew/chính sách cho phép. | Refresh token còn hiệu lực có thể xin access token mới nếu chưa bị chặn. |

Ví dụ người dùng vào trang **Ứng dụng đã kết nối**, chọn “Ngắt kết nối Photo Editor”. Nếu mục tiêu sản phẩm là **ngăn ứng dụng truy cập tiếp**, chỉ xóa consent **không đủ**. Một quy trình phù hợp cần:

1. Xác định chính xác người dùng, client và phạm vi cần thu hồi; yêu cầu xác thực lại nếu thao tác nhạy cảm.
2. Xóa hoặc cập nhật consent cho phạm vi đã chọn.
3. Vô hiệu hóa những authorization/refresh token thích hợp; áp dụng chính sách với token family nếu dùng rotation.
4. Quyết định cách xử lý access token đã cấp: thu hồi tức thì qua kiểm tra trạng thái/introspection/denylist, hoặc chấp nhận khoảng còn hiệu lực ngắn với TTL định trước và thông báo đúng.
5. Đồng bộ các instance, cache, audit và khả năng cấp lại quyền; xác định hành vi khi client gửi authorization request mới.

**Không tồn tại một thao tác xóa consent phổ quát bảo đảm JWT đang phát hành sẽ mất hiệu lực ngay** nếu Resource Server chỉ xác minh chữ ký và các claims. Yêu cầu thu hồi phải được thiết kế xuyên suốt Authorization Server và Resource Server.

### Điều gì xảy ra khi người dùng kết nối lại?

Nếu consent đã xóa, một authorization request mới có thể cần hiển thị consent theo policy. Nhưng nếu refresh token cũ vẫn còn hiệu lực, client có thể tiếp tục gọi token endpoint mà không đưa người dùng qua trang consent. Đó là lý do **disconnect** thường cần thêm thu hồi token và authorization, không chỉ `remove` consent.

## 12. Rủi ro và biện pháp bảo vệ Consent service

### 12.1. Tự tăng scope qua form bị sửa

Attacker sửa hidden input từ `photos.read` thành `photos.write`. Nếu backend ghi ngay chuỗi scope do form gửi thì người dùng có thể bị gán quyền chưa hề xem/đồng ý.

**Biện pháp:** liên kết form với authorization request đã kiểm tra, chỉ nhận lựa chọn thuộc requested scopes và registered scopes, kiểm tra principal/client trên server; từ chối mọi giá trị ngoài phạm vi.

### 12.2. Consent bị áp dụng cho nhầm client hoặc nhầm người

Nếu code lưu consent theo tên ứng dụng hiển thị hoặc chuỗi email không ổn định, hai client/người dùng có thể bị lẫn quyền. Trong hệ thống multi-tenant, một `principalName` như `alice` có thể trùng giữa các tenant.

**Biện pháp:** dùng registered client ID nội bộ và principal ổn định, định nghĩa namespace theo issuer/tenant khi cần. Xây dựng khóa, truy vấn và policy xóa dữ liệu tương ứng; kiểm thử cách ly tenant.

### 12.3. Consent phishing và mạo danh giao diện

Trang consent bị nhúng iframe, nhãn client có HTML/script hoặc ứng dụng được hiển thị bằng metadata tự cung cấp chưa kiểm chứng có thể lừa người dùng chấp thuận scope quá rộng.

**Biện pháp:** bảo vệ XSS, output encoding, CSP, frame-ancestors/X-Frame-Options theo kiến trúc, xác thực và kiểm duyệt metadata client, mô tả scope rõ ràng và hiển thị domain/nhà phát triển đáng tin khi phù hợp.

### 12.4. Bỏ qua quyết định từ chối

Luồng tùy chỉnh ghi nhận `approved=false` nhưng vẫn tiếp tục phát code/token, hoặc giữ nguyên những scope vừa bị từ chối và cấp chúng trong request mới.

**Biện pháp:** từ chối là đường đi riêng: không lưu thêm scope, không phát credential cho phạm vi bị từ chối; kiểm tra tập quyền trước token issuance. Đảm bảo response authorization error trở về redirect URI được đăng ký và client kiểm `state`.

### 12.5. Kết hợp consent sai với token renewal

Khi người dùng rút consent, refresh token vẫn xin được access token mới; hoặc resource server vẫn chấp nhận JWT cũ. Consent service không giải quyết các kiểm soát này một mình.

**Biện pháp:** định nghĩa chính sách token issuance, invalidation, refresh rotation và introspection/denylist nhất quán; xem `scope`, `audience` và token lifetime như ràng buộc riêng.

### 12.6. Ghi nhận và giữ dữ liệu quá mức

Lưu toàn bộ authorization request, dữ liệu cá nhân nhạy cảm hoặc token cùng bản ghi consent mà không cần thiết làm tăng nguy cơ lộ thông tin.

**Biện pháp:** lưu tối thiểu client/principal/approved authorities và metadata audit cần thiết; mã hóa/vô hiệu hóa truy cập dữ liệu khi phù hợp; chính sách retention/xóa và log redaction. Consent có thể là dữ liệu liên quan cá nhân nên phải quản lý quyền truy cập và retention nghiêm túc.

## 13. Mô hình vận hành thực tế: consent, authorization và audit

Một thiết kế có thể chia trách nhiệm:

~~~mermaid
flowchart TD
    Browser[Browser / consent UI] --> Endpoint[Authorization endpoint]
    Endpoint --> Login[Authenticated principal]
    Endpoint --> ClientRepo[RegisteredClientRepository]
    Endpoint --> Consent[OAuth2AuthorizationConsentService]
    Consent --> DB[(Consent store)]
    Endpoint --> Authorization[OAuth2AuthorizationService]
    Authorization --> AuthDB[(Authorization + token store)]
    Endpoint --> TokenGen[Token generator]
    TokenGen --> Client[OAuth client]
    Client --> Resource[Resource Server]
    Resource --> Policy[Signature / Introspection / Audience / Scope / Ownership]
    Consent -.-> Audit[(Audit trail)]
    Authorization -.-> Audit
~~~

Đối với dữ liệu production, nên có:

- **Độ bền và tính nhất quán:** shared storage, transaction khi cập nhật và chiến lược chống ghi đè nếu có nhiều request.
- **Observability:** số lần yêu cầu consent, đồng ý/từ chối, scope mới, lỗi lưu/đọc, thời gian phản hồi; tránh ghi token hoặc dữ liệu riêng tư vào metrics labels.
- **Chính sách thay đổi:** khi scope bị bỏ khỏi client registration hoặc đổi ý nghĩa, cần cơ chế đánh giá lại các consent cũ, thay vì tiếp tục tin một authority với semantics mới.
- **Quản lý danh sách ứng dụng đã kết nối:** cho phép người dùng xem client, scope và lựa chọn ngắt kết nối có ý nghĩa thực tế.
- **Sao lưu/khôi phục:** phải hiểu tác động nếu consent store được khôi phục tại thời điểm khác với authorization/token store; phối hợp revocation và audit để tránh khôi phục quyền đã rút.

Đừng để Consent service tự gọi API Resource Server để “kiểm quyền” khi cấp access token. Authorization Server quyết định grant và token theo dữ liệu/quy tắc của mình; Resource Server áp dụng những policy bảo vệ tài nguyên cụ thể ở thời điểm request.

## 14. Kiểm thử Consent service và luồng authorization

Có thể kiểm thử từng lớp, nhưng test tốt phải làm rõ mình đang kiểm **persistence** hay **end-to-end authorization**.

### 14.1. Unit test contract lưu trữ

Ví dụ minh họa đơn giản:

~~~java
OAuth2AuthorizationConsentService service =
    new InMemoryOAuth2AuthorizationConsentService();

OAuth2AuthorizationConsent consent =
    OAuth2AuthorizationConsent.withId("registered-client-42", "user-123")
        .authority(new SimpleGrantedAuthority("SCOPE_photos.read"))
        .build();

service.save(consent);

OAuth2AuthorizationConsent saved =
    service.findById("registered-client-42", "user-123");

assertNotNull(saved);
assertTrue(saved.getAuthorities().contains(
    new SimpleGrantedAuthority("SCOPE_photos.read")));

service.remove(consent);

assertNull(service.findById("registered-client-42", "user-123"));
~~~

Đây là logic minh họa có thể đưa vào test JUnit với imports và test fixture phù hợp. Nó chứng minh store hoạt động, **không chứng minh** form consent được kiểm CSRF hay authorization endpoint đã chặn scope giả mạo.

### 14.2. Bảng tình huống tích hợp cần có

| Trường hợp | Kỳ vọng |
|---|---|
| Lần đầu user U kết nối client C và xin `photos.read` | Khi policy yêu cầu, hiện consent; đồng ý thì lưu đúng authority. |
| Cùng U/C xin lại những scope đã được consent | Chính sách có thể cho phép bỏ qua màn hình consent; token chỉ cấp scope hợp lệ. |
| U/C xin thêm `photos.write` | Có quyết định cho scope mới; không mặc định cấp ngay nếu chưa consent. |
| User chọn chỉ `photos.read` | Không được cấp `photos.write` nếu hệ thống hỗ trợ partial consent. |
| User từ chối | Không cấp authorization code/token cho phạm vi bị từ chối; error được xử lý đúng. |
| Client gửi scope không có trong registration | Authorization Server từ chối hoặc giới hạn theo chính sách; tuyệt đối không thêm scope chỉ nhờ form. |
| Tấn công sửa `client_id`, `state` hoặc scope trong form | Không dùng quyết định của user cho request/client khác; chặn request không hợp lệ. |
| User U đã consent, user V cùng client chưa consent | V không kế thừa quyền của U. |
| Hai client có tên hiển thị giống nhau | Consent không bị dùng chéo giữa registered client ID khác nhau. |
| Hai request đồng thời thêm hoặc xóa quyền | Không mất update, không khôi phục quyền đã rút trái policy. |
| Restart Authorization Server dùng JDBC | Consent được khôi phục đúng từ shared DB. |
| Xóa consent nhưng giữ token cũ | Test chỉ ra token có thể còn hiệu lực; xác minh quy trình revocation bổ sung nếu yêu cầu disconnect. |
| OIDC `prompt=consent` hoặc `offline_access` | Luồng tuân theo chính sách của OP/phiên bản đang triển khai. |
| Multi-tenant hoặc multi-issuer | Principal và client được phân vùng, không rò consent qua tenant/issuer. |

### 14.3. Test hiệu lực bảo mật cuối cùng

Kịch bản cụ thể:

1. Đăng ký client chỉ cho `photos.read` và `photos.write`, yêu cầu consent.
2. Đăng nhập user-123, thực hiện Authorization Code + PKCE, chỉ chấp thuận `photos.read`.
3. Kiểm consent record bằng `findById` và kiểm token vừa nhận không có quyền `photos.write`.
4. Gọi `photos-api` để đọc ảnh hợp lệ; xác nhận Resource Server vẫn kiểm `audience`, `exp` và ownership.
5. Gửi request trái phép dùng scope `photos.write`; Resource Server phải từ chối.
6. Ngắt kết nối client: xóa consent và thực hiện revocation theo yêu cầu hệ thống.
7. Thử refresh token cũ và access token cũ; kết quả phải phù hợp **mức bảo đảm thu hồi** đã công bố.

Test tách rõ rằng **consent quyết định quyền được ủy quyền từ phía người dùng**, còn **token validation, token revocation và resource authorization** quyết định credential có còn sử dụng được khi gọi API hay không.

## 15. Câu hỏi tự luyện

1. Người dùng đã đăng nhập vào Authorization Server. Điều kiện nào cần có trước khi một client được cấp `photos.write`?
2. `OAuth2AuthorizationConsentService.findById` nhận hai tham số gì? Tại sao không chỉ lưu consent theo `client_id`?
3. Vì sao `OAuth2AuthorizationConsentService.remove` không tương đương với thu hồi access token JWT đang còn hạn?
4. Consent record lưu `SCOPE_photos.read` nhưng client yêu cầu `photos.read photos.write`. Làm sao quyết định quyền nào có thể cấp?
5. Lỗi gì xuất hiện nếu backend ghi scope do hidden form gửi mà không so sánh với authorization request đã xác minh?
6. Consent service khác `OAuth2AuthorizationService` và `RegisteredClientRepository` ra sao?
7. Vì sao `scope=offline_access` cần được xem xét cùng chính sách refresh token/rotation?
8. Nếu hai tab cùng sửa consent và một tab đang rút quyền, cần kiểm soát tình trạng cạnh tranh ghi như thế nào?

**Ghi nhớ:** Consent service lưu **lựa chọn đã chấp thuận của người dùng đối với một client và tập quyền cụ thể**. Authorization Server vẫn phải kiểm client, yêu cầu ủy quyền, scope được phép và chính sách cấp token. Resource Server vẫn phải kiểm access token cùng quyền truy cập tài nguyên; khi người dùng ngắt kết nối hoặc rút quyền, hệ thống phải xử lý **thu hồi token hiện có** theo chính sách riêng, ngoài việc cập nhật consent.
