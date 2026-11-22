# OAuth2AuthorizationConsentService và vòng đời consent

## 1. Consent là gì và vì sao Authorization Server cần lưu?

Trong hệ thống **OAuth 2.0/OpenID Connect (OIDC) Authorization Server** xây dựng bằng **Spring Security** và **Spring Authorization Server** trên Spring Boot, **consent** (sự chấp thuận ủy quyền) là quyết định của người dùng cho phép một **client** thực hiện những phạm vi truy cập nhất định thay mặt họ, trong giới hạn chính sách của hệ thống.

Ví dụ: Alice đăng nhập vào Authorization Server, ứng dụng <code>orders-web</code> yêu cầu scope <code>orders.read</code> và <code>orders.write</code>. Trên màn hình consent, Alice chỉ đồng ý <code>orders.read</code>. Server phải ghi nhớ lựa chọn hợp lệ của Alice cho đúng client, đồng thời bảo đảm token tiếp theo không được chứa quyền <code>orders.write</code> chỉ vì client đã yêu cầu.

<code>OAuth2AuthorizationConsentService</code> là **hợp đồng lưu trữ và truy xuất quyết định consent** của Spring Authorization Server. Nó phối hợp với mô hình <code>OAuth2AuthorizationConsent</code> và quy trình authorization, thay vì tự mình xác thực người dùng hay phát hành token.

Sau bài này, bạn có thể:

1. Phân biệt **authentication**, **authorization**, **consent** và token issuance.
2. Hiểu dữ liệu được lưu trong <code>OAuth2AuthorizationConsent</code>, khóa định danh và ba thao tác của <code>OAuth2AuthorizationConsentService</code>.
3. Mô tả vòng đời consent từ request lần đầu, cấp phép từng scope, sử dụng lại, mở rộng quyền, thu hồi đến cấp lại.
4. Cấu hình service dạng in-memory/JDBC trong Spring Boot; biết đâu là phần phục vụ demo và đâu là yêu cầu production.
5. Thiết kế màn hình consent và thao tác thu hồi an toàn, tránh giả mạo sự đồng ý.
6. Kiểm thử consent riêng biệt với quy trình thu hồi access token/refresh token.

### 1.1. Consent trả lời câu hỏi nào?

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Authentication** | Ai đang đăng nhập? | Người dùng Alice đã xác thực. |
| **Client registration** | Ứng dụng được đăng ký yêu cầu những quyền nào? | <code>orders-web</code> được đăng ký <code>orders.read</code>, <code>orders.write</code>. |
| **Consent** | Alice đã chấp thuận những quyền nào cho client đó? | Alice đồng ý <code>orders.read</code>. |
| **Authorization policy** | Chính sách hiện tại có cho phép yêu cầu này không? | Tài khoản Alice có bị hạn chế hoặc bị khóa không? |
| **Token issuance** | Server thực sự cấp token với quyền gì, cho ai và khi nào? | Access token chỉ có <code>orders.read</code>, audience Orders API. |
| **Resource authorization** | Alice có được truy cập bản ghi cụ thể không? | Alice được đọc đơn hàng 123 nhưng không được đọc đơn hàng của Bob. |

Consent **không phải** một loại đăng nhập, không chứng minh người dùng có quyền sở hữu mọi đối tượng, và cũng không thay thế chính sách kiểm soát scope của Authorization Server hoặc Resource Server.

## 2. Vị trí của ConsentService trong kiến trúc

~~~mermaid
flowchart LR
    U["End-User: Alice"] --> B["Authorization endpoint / consent UI"]
    C["OAuth Client: orders-web"] --> B
    B --> P["Authorization Code request processing"]
    P --> RC["RegisteredClientRepository"]
    P <--> CS["OAuth2AuthorizationConsentService"]
    CS <--> DB["Consent storage"]
    P <--> AS["OAuth2AuthorizationService"]
    P --> T["Token issuance"]
    T --> API["Resource Server"]
~~~

Những mô hình/chức năng chính:

| Thành phần | Nội dung và trách nhiệm |
| --- | --- |
| <code>RegisteredClient</code> | Định nghĩa client, phương thức xác thực, grant, redirect URI, scope có thể xin và <code>ClientSettings</code>. |
| <code>OAuth2AuthorizationConsent</code> | Bản ghi consent của **một principal cho một registered client**, gồm các authority đã được chấp thuận. |
| <code>OAuth2AuthorizationConsentService</code> | Giao diện truy xuất, lưu và xóa bản ghi consent. |
| <code>OAuth2Authorization</code> | Trạng thái một authorization/grant cùng các token, metadata và thông tin liên quan. |
| <code>OAuth2AuthorizationService</code> | Lưu, tìm, cập nhật trạng thái authorization/token; tách biệt với việc lưu consent. |
| <code>OAuth2AuthorizationServerConfigurer</code> | Gắn các filter/provider xử lý endpoint OAuth 2.0/OIDC; phối hợp kiểm tra client, người dùng và consent. |

Điểm quan trọng nhất: **bản ghi consent được dùng để ghi nhớ quyết định chấp thuận**, còn <code>OAuth2AuthorizationService</code> là nơi lưu trạng thái những authorization/token đã phát hành. Hai kho có thể cùng sử dụng database nhưng **không được coi là một bảng dữ liệu hay một nghiệp vụ thu hồi duy nhất**.

## 3. Mô hình <code>OAuth2AuthorizationConsent</code>

### 3.1. Ba phần dữ liệu cốt lõi

Mô hình <code>OAuth2AuthorizationConsent</code> lưu:

1. <code>registeredClientId</code>: **ID nội bộ của <code>RegisteredClient</code>**, được lấy qua <code>registeredClient.getId()</code>. Nó khác với <code>registeredClient.getClientId()</code> dùng trong request OAuth.
2. <code>principalName</code>: tên principal mà Spring Authorization Server dùng để định danh người dùng/chủ thể đã consent.
3. <code>authorities</code>: tập <code>GrantedAuthority</code> được chấp thuận cho tổ hợp client–principal.

Ví dụ biểu diễn một bản ghi:

~~~text
registeredClientId = "client-record-8f3c"
principalName      = "user-42"
authorities        = {"SCOPE_orders.read", "SCOPE_profile"}
~~~

<code>OAuth2AuthorizationConsent</code> **không** giữ toàn bộ access token, refresh token, phiên đăng nhập hoặc mật khẩu người dùng. Nó cũng không phải bảng ghi từng lần người dùng nhấn nút trong mọi request; thông thường nó đại diện cho **trạng thái consent hiện tại** của một cặp client–principal.

### 3.2. Vì sao authorities lại có dạng <code>SCOPE_...</code>?

Spring Security biểu diễn quyền dưới dạng <code>GrantedAuthority</code>. Trong consent model, các scope chấp thuận thường được ánh xạ thành authority có prefix <code>SCOPE_</code>:

~~~java
OAuth2AuthorizationConsent consent = OAuth2AuthorizationConsent
    .withId(registeredClient.getId(), principalName)
    .authority(new SimpleGrantedAuthority("SCOPE_orders.read"))
    .authority(new SimpleGrantedAuthority("SCOPE_profile"))
    .build();
~~~

Đây là minh họa **cách cấu trúc bản ghi**, không phải lời khuyên tự gọi <code>save()</code> để cấp quyền cho người dùng mà không qua quy trình consent. Mọi authority được ghi phải đến từ quyết định người dùng/chính sách đã kiểm tra ở phía server.

Phân biệt ba thứ:

| Dữ liệu | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Scope client yêu cầu | <code>orders.read orders.write</code> | Mong muốn trong authorization request. |
| Scope client đã đăng ký | <code>orders.read</code>, <code>orders.write</code> | Giới hạn trên do <code>RegisteredClient</code> cho phép. |
| Consent authority đã lưu | <code>SCOPE_orders.read</code> | Quyền người dùng đã chấp thuận trong ngữ cảnh client đó. |

Một <code>GrantedAuthority</code> trong consent **không nhất thiết là một role của người dùng** như <code>ROLE_ADMIN</code>. Không lấy các role đang có trong <code>Authentication.getAuthorities()</code> rồi ghi nguyên vào consent; cần đúng loại authority mà quy trình cấp quyền mong đợi.

### 3.3. Khóa cặp client–principal

Khi lấy bản ghi, API sử dụng hai tham số:

~~~java
OAuth2AuthorizationConsent existing =
    consentService.findById(registeredClient.getId(), principalName);
~~~

Điều này có các hệ quả quan trọng:

- Alice đã consent cho <code>orders-web</code> **không đồng nghĩa** Alice đã consent cho <code>billing-web</code>.
- Alice đã consent cho <code>orders-web</code> **không đồng nghĩa** Bob cũng được coi là đã consent.
- Truyền <code>clientId</code> thay vì <code>registeredClient.getId()</code> có thể khiến lookup sai, dẫn đến hỏi consent lại hoặc xóa nhầm bản ghi khi định danh trùng nhau.
- Trong hệ thống đa tenant, <code>principalName</code> phải có quy tắc định danh đủ ổn định và không va chạm giữa tenant/người dùng; với schema mặc định, tenant thường **không** là một cột khóa riêng.

Không lấy <code>principalName</code> từ tham số query mà người dùng tự gửi trong thao tác xem/xóa consent. Phải suy từ phiên xác thực đáng tin cậy và kiểm tra phân quyền thao tác.

## 4. API của <code>OAuth2AuthorizationConsentService</code>

Giao diện chính có ba thao tác:

~~~java
public interface OAuth2AuthorizationConsentService {
    void save(OAuth2AuthorizationConsent authorizationConsent);
    void remove(OAuth2AuthorizationConsent authorizationConsent);
    OAuth2AuthorizationConsent findById(
        String registeredClientId, String principalName);
}
~~~

| Phương thức | Ý nghĩa | Tình huống thường gặp |
| --- | --- | --- |
| <code>findById(clientRecordId, principalName)</code> | Tra cứu consent của một cặp client–principal; không có thì trả <code>null</code>. | Trước khi quyết định có cần hiển thị consent hay không. |
| <code>save(consent)</code> | Lưu trạng thái consent (tạo mới hoặc cập nhật theo implementation). | Người dùng hoàn thành bước chấp thuận hợp lệ. |
| <code>remove(consent)</code> | Xóa bản ghi consent. | Người dùng rút lại sự chấp thuận đã lưu hoặc chính sách yêu cầu xóa. |

Với implementation mặc định, việc tìm kiếm được tối ưu cho **một cặp khóa cụ thể**. Giao diện này **không có phương thức chuẩn <code>findAllByPrincipalName()</code>**. Nếu xây màn hình “Các ứng dụng đã kết nối”, bạn cần thiết kế tầng truy vấn bổ sung phù hợp, hoặc repository riêng, để liệt kê consent của người dùng.

### 4.1. Đọc và diễn giải scope đã chấp thuận

Ví dụ trong một service sử dụng các đối tượng **đã được tin cậy** từ backend:

~~~java
public Set<String> findConsentedScopes(
        RegisteredClient registeredClient,
        String authenticatedPrincipalName,
        OAuth2AuthorizationConsentService consentService) {

    OAuth2AuthorizationConsent consent = consentService.findById(
        registeredClient.getId(), authenticatedPrincipalName);

    if (consent == null) {
        return Set.of();
    }

    return consent.getAuthorities().stream()
        .map(GrantedAuthority::getAuthority)
        .filter(authority -> authority.startsWith("SCOPE_"))
        .map(authority -> authority.substring("SCOPE_".length()))
        .collect(Collectors.toUnmodifiableSet());
}
~~~

Đoạn mã trả về **scope đã lưu theo định dạng authority**, chưa thực hiện đối chiếu với scope được phép **hiện tại**, trạng thái tài khoản, chính sách tổ chức hay yêu cầu OAuth hiện thời. Khi ra quyết định phát hành token, server phải giới hạn quyền theo **tất cả** điều kiện tương ứng. Không dùng một kết quả <code>findById()</code> riêng lẻ để bỏ qua các kiểm tra đó.

### 4.2. Xóa bản ghi consent

~~~java
OAuth2AuthorizationConsent existing =
    consentService.findById(
        registeredClient.getId(), authenticatedPrincipalName);

if (existing != null) {
    consentService.remove(existing);
}
~~~

Đây là thao tác ở **tầng service sau khi đã xác thực và xác minh chủ sở hữu**. Nó không nên được đưa trực tiếp lên endpoint kiểu <code>DELETE /consents?principalName=alice</code> mà tin tưởng dữ liệu client cung cấp.

Đặc biệt, **xóa consent không tự đồng nghĩa vô hiệu hóa mọi access token/refresh token đã phát hành**. Phần 8 phân tích kỹ hậu quả và cách thiết kế chức năng “Ngắt kết nối ứng dụng”.

## 5. Vòng đời consent trong Authorization Code Flow

Trong một luồng Authorization Code + PKCE, consent là một **bước quyết định** sau khi server đã có đủ ngữ cảnh người dùng, client và authorization request. Nó có thể không cần hiển thị lại nếu quyền đã được chấp thuận trước đó hoặc chính sách client/server không yêu cầu.

~~~mermaid
flowchart TD
    A["Client yêu cầu /oauth2/authorize với scopes"] --> B{"Client / redirect URI / grant / scope hợp lệ?"}
    B -- Không --> X["Từ chối theo giao thức"]
    B -- Có --> C{"End-User đã xác thực?"}
    C -- Không --> LOGIN["Đăng nhập người dùng"] --> C
    C -- Có --> D["Đọc consent theo registeredClientId + principalName"]
    D --> E{"Consent mới hoặc bổ sung có cần thiết?"}
    E -- Không --> F["Tiếp tục authorization theo chính sách"]
    E -- Có --> G["Hiển thị ứng dụng và phạm vi yêu cầu"]
    G --> H{"Người dùng chấp thuận?"}
    H -- Không --> DENY["Không cấp các quyền bị từ chối; xử lý error theo flow"]
    H -- Có --> I["Xác minh và lưu consent hợp lệ"]
    I --> F
    F --> CODE["Authorization code / token theo grant"]
~~~

Điều kiện “có cần consent hay không” phụ thuộc <code>ClientSettings.requireAuthorizationConsent</code>, request, consent đã lưu, scope liên quan và cấu hình/version cụ thể. Sơ đồ thể hiện logic khái niệm; không nên diễn giải nó như thứ tự thực thi chính xác của từng filter/provider ở mọi phiên bản.

### 5.1. Lần đầu cấp quyền

Giả sử:

~~~text
Client: orders-web
Requested scopes: openid orders.read
Registered scopes: openid orders.read orders.write
Principal: user-42
Previous consent: không có
requireAuthorizationConsent: true
~~~

Khi người dùng đã đăng nhập, Authorization Server kiểm tra quy trình có cần consent hay không. Nếu cần, màn hình mô tả <code>orders-web</code> muốn đọc đơn hàng. Khi Alice xác nhận, service lưu phần quyền được chấp thuận phù hợp. Sau khi các điều kiện khác hoàn tất, server mới trả authorization code và cho phép client đổi code lấy token theo giao thức.

**Consent là điều kiện đầu vào, không phải lệnh phát token ngay lập tức.** Việc có record trong database không cho client được bỏ qua kiểm tra redirect URI, authentication, authorization code hay PKCE.

### 5.2. Quay lại với cùng phạm vi đã chấp thuận

Ở lần cấp quyền tiếp theo của cùng client và principal, server tìm consent cũ. Nếu phạm vi yêu cầu đã được bao phủ và chính sách cho phép tái sử dụng, người dùng có thể **không phải duyệt lại consent**.

Không suy rằng “đã có consent thì người dùng mãi mãi không thấy màn hình consent”: server có thể yêu cầu consent mới theo chính sách, giao thức, yêu cầu OIDC phù hợp hoặc khi bản ghi bị thu hồi. Việc tái xác thực người dùng cũng là một quyết định khác với tái sử dụng consent.

### 5.3. Client xin thêm scope

Ban đầu Alice đã đồng ý:

~~~text
{"SCOPE_orders.read"}
~~~

Sau một lần nâng cấp, client yêu cầu:

~~~text
orders.read orders.write
~~~

Nếu client được đăng ký <code>orders.write</code> và người dùng/chính sách có thể cấp quyền này, Authorization Server cần kiểm tra phần quyền **chưa từng được chấp thuận**. Nó không được coi consent cũ cho <code>orders.read</code> là sự đồng ý mặc nhiên với <code>orders.write</code>.

Một triển khai có thể hiển thị những scope mới, hoặc tổng hợp phạm vi yêu cầu để người dùng hiểu rõ. Nếu Alice không đồng ý quyền mới, server phải xử lý kết quả theo chính sách và đặc tả giao thức; **không tự ý thêm scope chưa được đồng ý vào consent**.

### 5.4. Người dùng từ chối

Việc bấm “Từ chối” không được tạo record cấp quyền mới. Với Authorization Code Flow, hệ thống thường trả lỗi giao thức phù hợp như <code>access_denied</code> về client theo các quy tắc redirect đã được xác minh.

Các chi tiết phải được kiểm tra kỹ:

- Không redirect đến một <code>redirect_uri</code> tùy ý chưa được kiểm tra.
- Không để lỗi giao thức chứa thông tin nhạy cảm.
- Không làm thay đổi bản ghi consent hiện có do một request bị từ chối, trừ khi sản phẩm có quy trình thu hồi **riêng và được xác thực**.
- Không phát token mang quyền chưa được duyệt.

### 5.5. Rút lại consent và cấp lại sau đó

Người dùng chọn “Ngắt kết nối” trong mục quản lý ứng dụng đã cấp quyền. Backend xác định đúng principal hiện đăng nhập, client cần thu hồi và record hiện tại; sau đó xóa consent hoặc sửa trạng thái theo mô hình lưu trữ. Lần authorization request tiếp theo có thể yêu cầu consent mới theo chính sách.

Những token đang còn hiệu lực cần được xử lý **riêng**. Nếu mục tiêu là ngắt quyền ngay lập tức, phải bổ sung cơ chế thu hồi/kiểm soát token, không dừng ở việc xóa hàng consent.

## 6. Consent khác authorization code, refresh token và đăng nhập

Để tránh lỗi thiết kế, cần tách ít nhất bốn vòng đời:

| Đối tượng | Tạo/khi nào | Lưu ở đâu | Khi nào hết hoặc bị xóa |
| --- | --- | --- | --- |
| Phiên đăng nhập của End-User | Khi xác thực người dùng | Security context/session hoặc hạ tầng tương ứng | Đăng xuất, hết hạn hoặc chính sách session |
| **Consent** | Khi người dùng chấp thuận phạm vi cho client | <code>OAuth2AuthorizationConsentService</code> | Rút lại consent, xóa client/người dùng hoặc chính sách lưu trữ |
| Authorization code | Sau authorization request được chấp thuận | <code>OAuth2AuthorizationService</code> | Hết hạn, sử dụng một lần hoặc bị vô hiệu |
| Access token / refresh token | Khi token endpoint phát hành | Metadata/trạng thái theo kiểu token và <code>OAuth2AuthorizationService</code> | Hết hạn, revocation và cơ chế kiểm soát token liên quan |

Một người dùng có thể:

- **Vẫn đăng nhập** nhưng đã thu hồi consent cho một client.
- **Đã đăng xuất** nhưng bản ghi consent vẫn còn, để không phải hỏi lại sau khi đăng nhập lần sau.
- **Vẫn có consent** nhưng refresh token đã hết hạn hoặc bị thu hồi.
- **Đã xóa consent** nhưng một JWT access token cũ vẫn hợp lệ cho đến khi hết hạn, nếu Resource Server chỉ kiểm tra chữ ký/thời gian mà không có cơ chế revoke.

Consent thường liên quan tới **End-User approval trong luồng có người dùng**, điển hình là Authorization Code. Với **Client Credentials**, client tự hoạt động dưới danh tính ứng dụng và không có End-User đứng trước màn hình consent; không thiết kế UI consent của người dùng như một bước mặc định cho grant này. Quyền client phải được kiểm soát qua đăng ký client, scope, policy và xác thực client.

Trong OIDC, <code>openid</code>, <code>profile</code>, <code>email</code> mô tả yêu cầu xác thực/thông tin định danh. Chúng có các quy tắc consent/claim riêng tùy cấu hình nhà cung cấp; **không mặc định mọi scope OIDC đều được lưu và hiển thị như scope API tùy biến**, và không khẳng định consent cho <code>email</code> bảo đảm ID Token luôn chứa claim <code>email</code>.

## 7. Cấu hình service bằng Spring Authorization Server

### 7.1. Bật yêu cầu consent trên RegisteredClient

<code>requireAuthorizationConsent(true)</code> là thiết lập trên **client**, không phải một thuộc tính toàn cục của <code>OAuth2AuthorizationConsentService</code>.

~~~java
RegisteredClient ordersWeb = RegisteredClient.withId("orders-web-record-001")
    .clientId("orders-web")
    .clientSecret(encodedSecret)
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
    .redirectUri("https://orders.example.com/login/oauth2/code/orders-web")
    .scope(OidcScopes.OPENID)
    .scope("orders.read")
    .scope("orders.write")
    .clientSettings(ClientSettings.builder()
        .requireAuthorizationConsent(true)
        .build())
    .build();
~~~

Ví dụ dùng **confidential server-side web client** với client secret đã mã hóa bằng <code>PasswordEncoder</code> phù hợp. Không đưa secret thô vào mã nguồn; nếu dùng public client phải cấu hình client authentication và PKCE phù hợp. <code>requireAuthorizationConsent</code> kích hoạt chính sách consent liên quan, **không có nghĩa mọi request chắc chắn hiển thị lại trang consent**.

### 7.2. Service dạng in-memory cho ví dụ và thử nghiệm

~~~java
@Bean
OAuth2AuthorizationConsentService authorizationConsentService() {
    return new InMemoryOAuth2AuthorizationConsentService();
}
~~~

Lựa chọn này dễ học, không yêu cầu database, nhưng có giới hạn:

- Restart sẽ làm mất bản ghi consent trong bộ nhớ.
- Nhiều instance độc lập có thể thấy các consent khác nhau.
- Không đáp ứng yêu cầu quản trị dữ liệu, backup, truy vấn/audit ở môi trường production.
- Không nên coi nó là nơi lưu trạng thái ủy quyền bền vững trong hệ thống thực.

### 7.3. Service JDBC để lưu consent bền vững

Spring Authorization Server cung cấp <code>JdbcOAuth2AuthorizationConsentService</code>:

~~~java
@Bean
OAuth2AuthorizationConsentService authorizationConsentService(
        JdbcTemplate jdbcTemplate,
        RegisteredClientRepository registeredClientRepository) {

    return new JdbcOAuth2AuthorizationConsentService(
        jdbcTemplate, registeredClientRepository);
}
~~~

Với triển khai JDBC chuẩn, cần chuẩn bị schema được cung cấp/tương thích với **phiên bản Spring Authorization Server đang dùng**. Cấu trúc thường dựa trên bảng <code>oauth2_authorization_consent</code> có các cột:

| Cột | Vai trò |
| --- | --- |
| <code>registered_client_id</code> | Khóa bản ghi registered client. |
| <code>principal_name</code> | Principal đã chấp thuận. |
| <code>authorities</code> | Tập authority được serialize theo cơ chế lưu trữ. |

Cặp <code>(registered_client_id, principal_name)</code> thường là **khóa chính/khóa duy nhất**, nên mỗi cặp có một trạng thái consent hiện tại. Đừng tạo bảng và kiểu cột theo phỏng đoán; dùng DDL/schema đi kèm đúng phiên bản, migration được kiểm soát và kiểm thử với loại database thực tế.

**Không phải chỉ thay bean service là production-ready.** Authorization Server còn cần kho client, authorization/token, consent, cấu hình transaction, khóa ký và chính sách backup/migration nhất quán. Nếu có nhiều instance, chúng phải dùng chung trạng thái cần thiết và issuer/khóa phù hợp.

### 7.4. Khi dùng Spring Boot auto-configuration

Tùy phiên bản Spring Boot và các bean đã được khai báo, hệ thống có thể có các implementation mặc định. Khi ứng dụng **tự khai báo** <code>OAuth2AuthorizationConsentService</code>, auto-configuration tương ứng có thể không tạo bean mặc định do điều kiện <code>@ConditionalOnMissingBean</code> hoặc cơ chế tương tự.

Nên kiểm tra bean thực tế trong runtime khi chuyển từ demo sang JDBC. Đừng vừa mong framework tự cấp một service in-memory vừa tạo thêm service riêng và mặc định rằng tất cả endpoint đều dùng cùng kho. Các namespace Boot cho authorization server và OAuth2 Client/Resource Server không thay thế cho các service mô hình của Authorization Server.

## 8. Thu hồi consent có thu hồi access token không?

**Không thể coi <code>consentService.remove(consent)</code> là thao tác thu hồi tất cả token.** Consent và token nằm ở những vòng đời/tầng lưu trữ khác nhau.

### 8.1. Hai quyết định độc lập

Một thao tác “Ngắt kết nối ứng dụng” có thể có hai yêu cầu sản phẩm:

1. **Không sử dụng consent cũ cho authorization mới:** xóa/sửa consent; lần tới phải xem xét consent lại theo chính sách.
2. **Chặn quyền truy cập hiện có càng sớm càng tốt:** thu hồi authorization, refresh token và/hoặc access token theo thiết kế và khả năng của từng loại token.

Một JWT self-contained có thể vẫn được Resource Server chấp nhận nếu chữ ký, issuer, audience, <code>exp</code> và các điều kiện khác còn hợp lệ; xóa hàng consent trong database **không làm payload JWT cũ biến mất**.

| Loại token/cơ chế | Hệ quả khi xóa consent | Việc cần làm nếu yêu cầu ngắt quyền sớm |
| --- | --- | --- |
| JWT access token, xác minh offline | Token đã phát hành vẫn có thể hợp lệ tới <code>exp</code>. | Access token ngắn hạn; cơ chế denylist/revocation hoặc kiểm tra trạng thái tập trung khi cần. |
| Reference/opaque token có introspection | Xóa consent riêng lẻ không mặc nhiên thay đổi trạng thái token. | Thu hồi token/authorization tại nguồn dữ liệu introspection kiểm tra. |
| Refresh token | Không nên giả định bị xóa cùng consent. | Thu hồi refresh token và authorization liên quan theo chính sách. |
| Authorization request mới | Consent cũ không còn để tái sử dụng. | Áp dụng lại chính sách và yêu cầu consent khi phù hợp. |

RFC 7009 định nghĩa endpoint revocation theo token; nó không tự cung cấp thao tác phổ quát “xóa mọi token của người dùng cho một client”. Nếu cần tính năng ngắt kết nối toàn bộ, phải thiết kế truy vấn những authorization liên quan, giao dịch thu hồi, xử lý race với refresh token, audit và nhất quán nhiều instance.

### 8.2. Mẫu quy trình “Ngắt kết nối” an toàn

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant UI as Trang ứng dụng đã kết nối
    participant S as Backend quản lý consent
    participant CS as ConsentService
    participant AS as AuthorizationService / token controls
    U->>UI: Chọn ngắt kết nối orders-web
    UI->>S: POST /account/consents/revoke (+ CSRF)
    S->>S: Xác thực phiên, lấy principal, kiểm tra quyền thao tác
    S->>CS: findById(registeredClientId, principalName)
    S->>CS: remove(consent) nếu tồn tại
    S->>AS: Thu hồi token/authorization theo chính sách nếu cần
    S-->>UI: Trạng thái ngắt kết nối đã áp dụng
~~~

Đây là **thiết kế nghiệp vụ** minh họa, không phải endpoint được Spring Authorization Server tạo sẵn. Giao diện quản lý consent phải được xây dựng và bảo vệ riêng. Thứ tự lưu/xóa/thu hồi token cần được phối hợp để tránh báo thành công một phần khi yêu cầu là ngắt kết nối toàn bộ.

### 8.3. Tình huống bất đồng bộ và race condition

Giả sử Alice vừa nhấn “Ngắt kết nối”, đồng thời <code>orders-web</code> đang đổi refresh token. Nếu triển khai chỉ xóa consent, request refresh có thể vẫn thành công. Nếu cả thao tác thu hồi token cũng được thiết kế, cần tính đến cạnh tranh ghi, tính nhất quán transaction, revoke lần hai và retry an toàn. Với nhiều database/hệ thống ngoài, khả năng atomic có thể bị giới hạn; xác định rõ trạng thái cuối cùng và cơ chế hòa giải, giám sát.

Đừng hứa “thu hồi có hiệu lực tức thời trên tất cả API” khi kiến trúc còn sử dụng JWT xác minh offline không kiểm tra trạng thái thu hồi.

## 9. Thiết kế màn hình consent an toàn, dễ hiểu

Spring Authorization Server cho phép tùy chỉnh UI/luồng consent theo các hook/configurer có trong phiên bản sử dụng. Màn hình consent là thành phần **đặc biệt nhạy cảm**: mọi nội dung và tham số được hiển thị hoặc gửi đi phải xuất phát từ dữ liệu đã kiểm tra.

### 9.1. Nội dung nên hiển thị

Màn hình có thể trình bày:

- **Tên ứng dụng đã đăng ký** và định danh client để người dùng biết mình đang cấp quyền cho ai. Tránh dùng trực tiếp tham số display name do client gửi trong request nếu chưa được xác minh.
- **Danh sách scope** và mô tả dễ hiểu: <code>orders.read</code> → “Xem đơn hàng bạn có quyền truy cập”; <code>orders.write</code> → “Tạo hoặc cập nhật đơn hàng trong phạm vi được phép”.
- Phân biệt quyền đã cấp trước đây với quyền **mới được yêu cầu**.
- Nút **Chấp thuận** và **Từ chối** rõ ràng, không tạo các checkbox đánh dấu sẵn theo cách gây hiểu nhầm.
- Thông tin cách rút lại quyền và cách xử lý quyền đã cấp.

Không mô tả <code>orders.read</code> thành “Xem tất cả đơn hàng trong hệ thống” nếu Resource Server còn kiểm tra quyền sở hữu và tenant. Mô tả scope phải phản ánh chính sách API thực tế.

### 9.2. Các kiểm soát bắt buộc về logic

**Tập quyền có thể chấp thuận** phải được suy từ:

~~~text
requested scopes
∩ scopes hợp lệ trong RegisteredClient
∩ quyền/chính sách hiện thời của principal
∩ giới hạn của authorization flow
~~~

Đây là mô hình khái niệm; chi tiết cấp quyền còn phụ thuộc cấu hình chuẩn OAuth2/OIDC. Nếu form gửi scope <code>admin</code> hoặc client ID khác với request gốc, server phải **từ chối** chứ không tin form.

Các lớp bảo vệ nên có:

1. Xác thực người dùng bằng phiên hợp lệ và liên kết response consent với **authorization request** đang chờ xử lý.
2. Bảo vệ **CSRF** cho request POST từ trình duyệt và xem xét clickjacking/XSS/HTML escaping.
3. Kiểm tra <code>state</code>, client, redirect URI và tính toàn vẹn của dữ liệu authorization theo cơ chế giao thức.
4. Không đưa access token, refresh token, client secret hoặc authorization code vào URL và HTML ngoài mục đích giao thức được thiết kế.
5. Lưu audit metadata thích hợp (ai, client nào, scope nào, thời điểm, nguồn quyết định) mà không log credential hoặc token nguyên văn.
6. Với endpoint quản lý consent, chủ thể thao tác phải được lấy từ authentication đáng tin; không cho người dùng chỉ định tùy ý <code>principalName</code>.

**Consent UI không phải nơi client tự cấp quyền cho mình**. Tất cả quyền từ form phải được server kiểm tra lại trước khi gọi service lưu trữ.

## 10. Multi-tenancy, thay đổi client và yêu cầu dữ liệu

### 10.1. Không để <code>principalName</code> va chạm giữa tenant

Một tổ chức đa tenant có thể có hai người dùng với tên <code>alice</code>, hoặc một người dùng được đổi email/username. Nếu dùng đúng string <code>alice</code> làm khóa principal ở mọi tenant trong cùng kho consent, có thể vô tình tái sử dụng bản ghi giữa các thực thể khác nhau.

Giải pháp phụ thuộc kiến trúc, chẳng hạn:

- Dùng ID người dùng **ổn định, không đổi** trong toàn bộ phạm vi issuer, có phân biệt tenant khi cần.
- Ánh xạ authenticated principal name theo quy tắc có kiểm soát; không lấy từ email có thể đổi hoặc dữ liệu request.
- Với nhiều issuer/tenant hoặc mô hình consent khác biệt, thiết kế namespace và schema tương ứng; không cố nhồi dữ liệu tenant vào một string thiếu quy tắc.

### 10.2. Đổi client ID hoặc scope đăng ký

<code>OAuth2AuthorizationConsent</code> tham chiếu **registered client record ID**, không phải client ID giao thức. Nếu xóa và tạo lại <code>RegisteredClient</code> bằng một record ID mới, consent cũ sẽ không tự liên kết với record mới, kể cả <code>clientId</code> OAuth hiển thị giống hệt.

Khi thay đổi client registration:

| Thay đổi | Cần kiểm tra |
| --- | --- |
| Thêm scope mới | Client phải được phép xin và consent mới cần được xử lý khi thích hợp. |
| Bỏ scope khỏi client | Không cấp token với scope đã bị bỏ chỉ vì consent cũ vẫn còn lưu. |
| Thay <code>registeredClient.getId()</code> | Quy hoạch migration/cleanup consent tham chiếu ID cũ. |
| Xóa client hoàn toàn | Xử lý consent mồ côi, authorization/token và dữ liệu audit theo chính sách. |
| Chuyển tenant hoặc thay principal identifier | Ngăn tái sử dụng consent không thuộc cùng chủ thể. |

Để minh bạch và dễ truy vết, không nên âm thầm “nâng” quyền consent cũ khi thay đổi nghĩa của scope. Ví dụ đổi <code>orders.read</code> từ “đọc đơn của tôi” sang “đọc đơn của cả tổ chức” là thay đổi chính sách và trải nghiệm người dùng, cần xem lại quyền, consent và thông tin đã công bố.

### 10.3. Retention và audit

Vì consent thể hiện mối quan hệ người dùng–ứng dụng, nó có thể là dữ liệu có yêu cầu bảo vệ riêng. Nên có chính sách giữ/xóa bản ghi khi tài khoản bị xóa, client ngừng hoạt động hoặc hợp đồng kết thúc. **Lịch sử consent** (audit trail) và **trạng thái consent hiện tại** là hai loại dữ liệu khác nhau: nếu cần chứng minh ai đã chấp thuận gì tại thời điểm nào, nên lưu audit có kiểm soát thay vì trông đợi bảng hiện trạng luôn chứa lịch sử.

## 11. Kiểm thử Service và toàn bộ vòng đời

### 11.1. Kiểm thử API bằng in-memory service

Ví dụ JUnit + AssertJ kiểm tra khóa cặp client–principal và thao tác lưu/xóa:

~~~java
@Test
void consentIsScopedByRegisteredClientAndPrincipal() {
    OAuth2AuthorizationConsentService service =
        new InMemoryOAuth2AuthorizationConsentService();

    OAuth2AuthorizationConsent aliceOrders =
        OAuth2AuthorizationConsent
            .withId("orders-client-record", "alice-id")
            .authority(new SimpleGrantedAuthority("SCOPE_orders.read"))
            .build();

    service.save(aliceOrders);

    assertThat(service.findById("orders-client-record", "alice-id"))
        .isNotNull();
    assertThat(service.findById("orders-client-record", "bob-id"))
        .isNull();
    assertThat(service.findById("billing-client-record", "alice-id"))
        .isNull();

    service.remove(aliceOrders);

    assertThat(service.findById("orders-client-record", "alice-id"))
        .isNull();
}
~~~

Phép thử này kiểm tra **hợp đồng storage**, chưa kiểm tra màn hình consent, grant validation hoặc revocation. Trong production, cần kiểm thử tương đương trên JDBC/database thực tế, gồm tạo/cập nhật/xóa, transaction và tình huống race khi nhiều request cùng cập nhật consent.

### 11.2. Ma trận integration test

| Tình huống | Kỳ vọng |
| --- | --- |
| Client A chưa có consent, yêu cầu scope hợp lệ | Hiển thị/áp dụng bước consent theo chính sách client/server. |
| Người dùng đồng ý một scope hợp lệ | Bản ghi consent phản ánh quyền chấp thuận; token sau đó không vượt quá scope được cấp. |
| Yêu cầu lại phạm vi đã đồng ý | Có thể tái sử dụng consent theo chính sách, không cấp thêm quyền. |
| Client xin thêm scope mới | Không tự chấp thuận quyền mới; xử lý consent theo flow. |
| Client xin scope chưa đăng ký | Từ chối yêu cầu theo giao thức, không lưu quyền mới. |
| Người dùng bấm “Từ chối” | Không tạo consent cho quyền bị từ chối; phản hồi lỗi phù hợp. |
| Bob yêu cầu cùng client | Không dùng bản ghi consent của Alice. |
| Alice yêu cầu client B | Không dùng bản ghi consent của client A. |
| POST consent giả mạo/CSRF | Không lưu consent; endpoint từ chối theo bảo vệ được thiết kế. |
| Thu hồi consent | Không còn bản ghi, lần authorization sau đánh giá consent lại. |
| Thu hồi consent khi JWT cũ chưa hết hạn | Kiểm chứng chính xác chiến lược token revocation đã chọn; không giả định JWT tự mất hiệu lực. |
| Restart Authorization Server dùng JDBC | Consent bền vững được đọc lại. |
| Hai instance dùng chung database | Quyết định consent nhất quán, không mất cập nhật khi concurrency. |
| Xóa client hoặc thay registeredClient ID | Dữ liệu consent mồ côi được xử lý theo chính sách. |

Ở mức HTTP, sử dụng <code>MockMvc</code> hoặc client giao thức thật để đi qua authentication, authorization endpoint, session, CSRF, consent submission, authorization code và token endpoint. Kiểm tra response giao thức và trạng thái thực trong <code>OAuth2AuthorizationConsentService</code>.

**Lưu ý về mocking:** Chỉ stub <code>consentService.findById()</code> trong một unit test không chứng minh request OAuth đã chọn đúng client, scope hoặc redirect URI. Tương tự, mock JWT authentication trong Resource Server thường bỏ qua kiểm tra JWT decoder; token validation cần integration test riêng.

### 11.3. Những bất biến nên kiểm tra

Một bộ kiểm thử tốt cần bảo đảm:

~~~text
Persisted consent scopes ⊆ Allowed scopes for this client and principal
Granted token scopes ⊆ Valid requested / authorized scopes
Consent(client A, user X) != Consent(client B, user X)
Consent(client A, user X) != Consent(client A, user Y)
Removing consent does not imply revocation of an already issued JWT
~~~

Ký hiệu <code>⊆</code> là “tập con hoặc bằng”. Những bất biến về quyền cần được đánh giá sau khi áp dụng chính sách và loại grant cụ thể; một số authority lưu cho OIDC có thể có ngữ nghĩa/biểu diễn khác scope API tùy phiên bản và cấu hình.

## 12. Sự cố thường gặp và cách xử lý

### Sự cố 1: Người dùng bị hỏi consent mỗi lần đăng nhập

Kiểm tra <code>OAuth2AuthorizationConsentService</code> có phải in-memory rồi bị reset không; client record ID hoặc <code>principalName</code> có thay đổi mỗi lần hay không; server có nhiều instance nhưng mỗi node lưu riêng hay không; scope mới thực sự được yêu cầu hay không; và chính sách có yêu cầu tái consent hay không.

Không tắt hẳn <code>requireAuthorizationConsent</code> chỉ để che lỗi dữ liệu. Cần xác định lý do hệ thống không tìm được consent cũ.

### Sự cố 2: Consent đã tồn tại nhưng token vẫn thiếu scope

Consent đã lưu **không bảo đảm** scope luôn được cấp. Kiểm tra requested scope thực tế, registered scopes, loại grant, chính sách Authorization Server, quyết định của người dùng ở request hiện tại và logic token customization. Không tự bổ sung scope trong JWT chỉ vì nó có trong bảng consent.

### Sự cố 3: Đã bấm ngắt kết nối nhưng API vẫn chấp nhận token

Đây có thể là hành vi dự kiến khi token JWT cũ còn hạn và Resource Server chỉ xác minh offline. Hãy đối chiếu yêu cầu sản phẩm, thời hạn token, cơ chế revoke/introspection/denylist và refresh token. Nếu sản phẩm hứa ngắt kết nối tức thời thì cần thiết kế revocation thật, không chỉ xóa consent.

### Sự cố 4: JDBC lưu lỗi hoặc đọc consent không nhất quán

Kiểm tra schema đúng phiên bản, connection pool, transaction, khóa chính tổ hợp, kiểu dữ liệu của cột <code>authorities</code>, quyền DB và khả năng chạy nhiều node. Nếu dùng mapper/serializer tùy biến, kiểm tra chiều đi và chiều về của dữ liệu authorities.

Không tự động “cho qua consent” khi database lỗi: lỗi lưu trữ không thể là lý do cấp thêm quyền. Xử lý lỗi có kiểm soát và phản hồi an toàn.

### Sự cố 5: Lộ hoặc trộn consent của người dùng khác

Kiểm tra principal key, tenant scoping, registered client record ID, truy vấn list/revoke tự viết, session ownership và dữ liệu mà frontend được phép gửi. Xem xét thu hồi các token đã cấp sai và rà soát audit theo quy trình ứng phó bảo mật.

## 13. Bài tập áp dụng

Thiết kế Authorization Server cho ba đối tượng:

- Client **reporting-web** dùng Authorization Code + PKCE, xin <code>openid</code>, <code>reports.read</code> và khi cần <code>reports.export</code>.
- Client **admin-portal** cùng issuer nhưng có <code>registeredClientId</code> riêng.
- Client **batch-job** dùng Client Credentials để thực hiện nhiệm vụ hệ thống.

Hãy hoàn thành các yêu cầu:

1. Đề xuất cấu trúc <code>RegisteredClient</code> và <code>ClientSettings.requireAuthorizationConsent</code> cho <code>reporting-web</code>. Giải thích client nào thực sự cần sự chấp thuận của End-User.
2. Alice lần đầu chỉ cấp <code>reports.read</code>. Mô tả record <code>OAuth2AuthorizationConsent</code> và lý do <code>reports.export</code> chưa được tự động cấp.
3. Khi client xin thêm <code>reports.export</code>, mô tả điều kiện cần kiểm tra trước khi thay đổi consent và phát token.
4. Xây dựng service JDBC và migration cho bảng consent, giải thích vì sao khóa nên dựa trên registered client record ID và principal ổn định.
5. Thiết kế chức năng “Ngắt kết nối reporting-web” có kiểm soát CSRF, principal ownership và yêu cầu thu hồi token theo chính sách.
6. Viết một unit test kiểm tra client/principal isolation, một integration test về phạm vi scope và một integration test về revocation khi access token là JWT.
7. Khi hệ thống triển khai ba instance và có hai tenant cùng dùng username <code>alice</code>, hãy chứng minh consent không bị dùng chéo.

Đáp án thiết kế cần giải thích rõ **consent lưu quyền gì, theo khóa nào, được hỏi lại khi nào, lưu ở đâu và khác revocation của token ra sao**.

## 14. Tài liệu đối chiếu

- [Spring Authorization Server — Core Model / <code>OAuth2AuthorizationConsent</code>](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): mô hình consent, service và các triển khai lưu trữ.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): cấu hình authorization endpoint, OIDC và Java DSL.
- [Spring Authorization Server — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html): đăng ký client, consent và các bean cần thiết.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): <code>GrantedAuthority</code>, <code>AuthorizationManager</code> và mô hình phân quyền.
- [RFC 6749, §4.1 — Authorization Code Grant](https://www.rfc-editor.org/rfc/rfc6749#section-4.1): luồng ủy quyền OAuth 2.0 và chấp thuận của resource owner.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): cơ chế thu hồi token, tách biệt với lưu consent.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): scope và sự chấp thuận trong OIDC.
