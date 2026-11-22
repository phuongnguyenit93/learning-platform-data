# Tùy chỉnh accessTokenRequestConverter và AuthenticationProvider

## 1. Mục tiêu của bài và bối cảnh

Trong **Spring Security OAuth2/OIDC Authorization Server** triển khai bằng **Spring Boot** và **Spring Authorization Server**, **Token Endpoint** là điểm tiếp nhận yêu cầu đổi authorization grant lấy access token. Các grant như <code>authorization_code</code>, <code>refresh_token</code> và <code>client_credentials</code> đều đi qua endpoint này, nhưng có cách kiểm tra tham số, xác thực client, điều kiện cấp quyền và trạng thái token khác nhau.

Spring Authorization Server cung cấp các **extension point** để ứng dụng tùy chỉnh cách đọc yêu cầu và cách xử lý grant mà không phải viết lại toàn bộ endpoint:

- <code>accessTokenRequestConverter(...)</code>: thêm một <code>AuthenticationConverter</code> chuyển HTTP request thành đối tượng authentication đại diện cho một grant.
- <code>authenticationProvider(...)</code>: thêm một <code>AuthenticationProvider</code> xác minh grant, thực hiện chính sách cấp token và trả kết quả xác thực.
- <code>accessTokenRequestConverters(...)</code> và <code>authenticationProviders(...)</code>: truy cập **danh sách các thành phần mặc định và được bổ sung** để điều chỉnh một cách có chủ đích.

Đây là điểm mở rộng rất mạnh, đồng thời nhạy cảm về bảo mật: một converter quá rộng có thể chiếm request của grant chuẩn; một provider bỏ qua xác thực client hoặc scope có thể cấp token ngoài quyền đăng ký; một validator mới thay thế hoàn toàn validator mặc định có thể vô tình nới lỏng các kiểm tra quan trọng.

Sau bài này, bạn có thể:

1. Hiểu pipeline **HTTP → converter → AuthenticationManager/provider → token generator → authorization store → token response**.
2. Phân biệt các phương thức thêm converter/provider với các phương thức tùy chỉnh danh sách mặc định.
3. Tự thiết kế một **extension authorization grant** có URI riêng và token class riêng.
4. Viết converter kiểm tra tham số, từ chối dữ liệu không hợp lệ và nhường request không thuộc grant của mình.
5. Viết provider kiểm tra client, grant được đăng ký, credential nghiệp vụ, scope và khả năng sử dụng một lần trước khi phát token.
6. Dùng <code>OAuth2TokenGenerator</code> và <code>OAuth2AuthorizationService</code> theo đúng ranh giới trách nhiệm.
7. Bổ sung rule cho một provider **mặc định** mà vẫn giữ validator nền tảng.
8. Xây dựng integration test chứng minh các grant chuẩn còn hoạt động và extension grant không gây leo thang quyền.

**Ví dụ xuyên suốt:** Authorization Server ở <code>https://auth.example.com</code> phục vụ confidential client <code>reports-worker</code>. Ngoài Client Credentials, hệ thống thử nghiệm muốn cấp access token thông qua **one-time ticket do một thành phần nội bộ đáng tin cậy phát hành**, được ràng buộc trước với một registered client và tập scope hạn chế. Grant minh họa mang URI <code>urn:example:oauth:grant-type:one-time-ticket</code> và **không phải một grant chuẩn IETF**. Trong sản phẩm thực, ưu tiên grant chuẩn như Token Exchange (RFC 8693) khi phù hợp thay vì tự thiết kế giao thức mới.

**Phạm vi phiên bản:** Các ví dụ về Java DSL dùng API Spring Authorization Server **1.5.x** với <code>OAuth2AuthorizationServerConfigurer.authorizationServer()</code> và <code>HttpSecurity.with(...)</code>. Một số bản Spring Security mới tích hợp Authorization Server trong package khác; cần đối chiếu API của đúng version. Các lớp nghiệp vụ ví dụ (như <code>OneTimeTicketService</code>) là hợp đồng do ứng dụng tự xây, không phải API có sẵn của Spring.

## 2. Token Endpoint thực sự xử lý những thành phần nào?

### 2.1. Luồng từ request tới response

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant CF as OAuth2ClientAuthenticationFilter
    participant TF as OAuth2TokenEndpointFilter
    participant CV as AuthenticationConverter
    participant AM as AuthenticationManager
    participant P as AuthenticationProvider
    participant S as Authorization/Token services
    C->>CF: POST /oauth2/token + client authentication + grant parameters
    CF->>CF: Xác thực client theo RegisteredClient
    CF->>TF: Cho phép request tiếp tục nếu phù hợp
    TF->>CV: convert(HttpServletRequest)
    CV-->>TF: OAuth2AuthorizationGrantAuthenticationToken
    TF->>AM: authenticate(grantToken)
    AM->>P: Chọn provider có supports(grantToken)
    P->>S: Xác minh grant, client, scope và trạng thái
    S-->>P: Kết quả hợp lệ
    P->>S: Sinh token và lưu OAuth2Authorization
    P-->>AM: OAuth2AccessTokenAuthenticationToken
    AM-->>TF: Authentication thành công
    TF-->>C: JSON access_token hoặc OAuth error
~~~

Sơ đồ biểu diễn luồng thông thường, không phải sơ đồ chính xác từng vị trí filter ở mọi cấu hình. Điểm quan trọng là **client authentication** và **authorization grant authentication** là hai trách nhiệm khác nhau. Trong pipeline mặc định, <code>OAuth2ClientAuthenticationFilter</code> xác thực OAuth client; <code>OAuth2TokenEndpointFilter</code> và provider grant tiếp tục xử lý yêu cầu token.

### 2.2. Ba điểm mở rộng tương ứng ba giai đoạn

| Giai đoạn | API thường dùng | Nhiệm vụ | Không nên làm |
| --- | --- | --- | --- |
| **Trước xử lý** | <code>AuthenticationConverter</code> | Đọc và kiểm tra hình dạng HTTP request; tạo authentication request phù hợp. | Tự phát access token, tin client ID chưa xác thực, gọi database nặng khi chưa cần. |
| **Xử lý chính** | <code>AuthenticationProvider</code> | Xác minh client/grant/policy, truy xuất trạng thái, sinh/lưu token và trả authentication. | Bỏ qua scope, cấp token khi client chưa xác thực, chấp nhận ticket/code đã dùng. |
| **Sau xử lý** | <code>AuthenticationSuccessHandler</code> / <code>AuthenticationFailureHandler</code> | Tạo HTTP response thành công/lỗi phù hợp giao thức. | Thực hiện logic cấp quyền ở handler chỉ vì dễ ghi JSON. |

Trong Spring Authorization Server 1.5.x, Token Endpoint mặc định hỗ trợ những grant phổ biến, gồm Authorization Code, Refresh Token, Client Credentials, Device Code và Token Exchange (mức hỗ trợ phụ thuộc version). Một số bản cũ không có đủ converter/provider mặc định kể trên, vì vậy khi thay đổi version cần kiểm tra lại.

### 2.3. Không nhầm ba loại Authentication

| Đối tượng | Đại diện cho | Ví dụ |
| --- | --- | --- |
| <code>OAuth2ClientAuthenticationToken</code> | Client đã hoặc đang được xác thực. | <code>reports-worker</code> dùng <code>client_secret_basic</code>. |
| <code>OAuth2AuthorizationGrantAuthenticationToken</code> | Một **yêu cầu sử dụng grant** tại token endpoint. | <code>authorization_code</code>, <code>refresh_token</code> hoặc custom ticket. |
| <code>OAuth2AccessTokenAuthenticationToken</code> | **Kết quả thành công** của xử lý grant; chứa access token và thông tin liên quan. | Provider tạo token, filter xuất response JSON. |

Không đổi <code>OAuth2AccessTokenAuthenticationToken</code> thành <code>UsernamePasswordAuthenticationToken</code> để “đưa user vào hệ thống”, và không coi xác thực client thành công là quyền tự động nhận mọi scope.

## 3. API của OAuth2TokenEndpointConfigurer

Các phương thức tiêu biểu:

~~~java
authorizationServer.tokenEndpoint(tokenEndpoint -> tokenEndpoint
    .accessTokenRequestConverter(customConverter)
    .accessTokenRequestConverters(converters -> {
        // Có thể xem/chỉnh danh sách converter mặc định và đã thêm.
    })
    .authenticationProvider(customProvider)
    .authenticationProviders(providers -> {
        // Có thể xem/chỉnh danh sách provider mặc định và đã thêm.
    })
    .accessTokenResponseHandler(successHandler)
    .errorResponseHandler(errorHandler)
);
~~~

| Phương thức | Tác động | Dùng khi nào |
| --- | --- | --- |
| <code>accessTokenRequestConverter(converter)</code> | **Bổ sung** một converter để token endpoint nhận kiểu request riêng. | Có extension grant mới. |
| <code>accessTokenRequestConverters(consumer)</code> | Consumer có quyền truy cập danh sách converter, bao gồm default. | Cần quan sát, điều chỉnh vị trí hoặc thay một converter cụ thể. |
| <code>authenticationProvider(provider)</code> | **Bổ sung** provider xử lý authentication request mới. | Có extension grant mới, token class riêng. |
| <code>authenticationProviders(consumer)</code> | Consumer có quyền truy cập danh sách provider, bao gồm default. | Muốn cấu hình một provider mặc định hoặc điều chỉnh danh sách có kiểm soát. |
| <code>accessTokenResponseHandler(handler)</code> | Tùy chỉnh hành vi ghi response khi thành công. | Tích hợp response handling phù hợp, sau khi hiểu cấu trúc OAuth2. |
| <code>errorResponseHandler(handler)</code> | Tùy chỉnh xử lý lỗi token endpoint. | Chuẩn hóa logging/response mà không lộ credential hoặc làm sai mã lỗi giao thức. |

**Quy tắc quan trọng:** Các phương thức **số ít** thường được dùng để **thêm** thành phần; không nên hiểu chúng là lệnh thay thế toàn bộ cơ chế mặc định. Các phương thức **số nhiều** cho phép truy cập list hiện tại; sửa/xóa hoặc thay đổi thứ tự ở đó có thể làm thay đổi hành vi grant chuẩn. Muốn biết chính xác converter/provider nào đang hoạt động, kiểm tra tài liệu API/version và integration test.

### 3.1. Converter được chọn như thế nào?

Token Endpoint mặc định dùng một <code>DelegatingAuthenticationConverter</code> gồm nhiều converter. Từng converter nhận cùng request, theo thứ tự trong list; converter đầu tiên trả về một authentication khác <code>null</code> sẽ được sử dụng. Một converter dành cho extension grant phải:

1. Kiểm tra <code>grant_type</code> trước.
2. **Trả <code>null</code>** nếu request thuộc grant khác.
3. **Ném <code>OAuth2AuthenticationException</code>** nếu request đã được nhận diện là grant của mình nhưng tham số bắt buộc sai.
4. Trả đối tượng <code>OAuth2AuthorizationGrantAuthenticationToken</code> chuyên biệt nếu request hợp lệ về hình dạng.

Nếu converter trả <code>null</code> cả khi client dùng đúng custom grant nhưng thiếu ticket, lỗi có thể đi sai đường và hiện thành một lỗi unsupported grant không phản ánh dữ liệu đầu vào. Ngược lại, nếu converter luôn trả non-null kể cả <code>authorization_code</code>, nó có thể “nuốt” request chuẩn và làm hỏng toàn bộ Token Endpoint.

### 3.2. Provider được chọn như thế nào?

<code>AuthenticationManager</code>, thường có implementation kiểu <code>ProviderManager</code>, sử dụng <code>AuthenticationProvider.supports(Class&lt;?&gt;)</code> để xác định provider có thể xử lý authentication token hay không. Provider nên chỉ nhận **đúng class** mình hỗ trợ, rồi kiểm tra:

- OAuth client đã được xác thực, có <code>RegisteredClient</code> thật.
- Client được phép sử dụng loại grant đó.
- Credential hoặc bằng chứng grant hợp lệ theo policy.
- Scope, audience/resource, principal và trạng thái liên quan được kiểm tra.
- Token generation, persistence, replay protection và error mapping không làm mất các bất biến của OAuth2.

Đừng xây provider có <code>supports(Authentication.class)</code> hoặc một class quá tổng quát rồi tự chọn theo nhiều điều kiện trong <code>authenticate()</code>. Một provider quá rộng có thể chặn request của built-in provider.

## 4. Đọc HTTP request và lỗi OAuth ở Token Endpoint

Ví dụ client sử dụng Authorization Code:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <redacted-client-credential>
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=example-code&redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&code_verifier=example-verifier
~~~

Đây là request minh họa; giá trị code và PKCE verifier phải là dữ liệu thực được tạo đúng chuẩn. Token endpoint thường nhận form URL encoded qua HTTPS. Client phải gửi các trường phù hợp với grant và client authentication đã đăng ký. Không đưa token/code/secret vào query URL hoặc log raw body.

### 4.1. Các mã lỗi cần phân biệt

| Mã lỗi OAuth 2.0 | Ví dụ | Xử lý đúng ở converter/provider |
| --- | --- | --- |
| <code>invalid_request</code> | Thiếu ticket, hai tham số trùng nhau, form sai định dạng. | Converter hoặc validation ở token endpoint từ chối request. |
| <code>invalid_client</code> | Client chưa xác thực hoặc credential client sai. | Client authentication/provider từ chối; không thay bằng <code>invalid_grant</code> tùy ý. |
| <code>unauthorized_client</code> | Client tồn tại nhưng không được đăng ký grant này. | Provider kiểm tra danh sách grant của RegisteredClient. |
| <code>invalid_grant</code> | Code/ticket hết hạn, đã dùng, sai client hoặc bị thu hồi. | Provider từ chối bằng lỗi chung, tránh tiết lộ chi tiết credential. |
| <code>invalid_scope</code> | Scope vượt quá quyền đã đăng ký hoặc policy của grant. | Provider/validator từ chối phần quyền không hợp lệ. |
| <code>unsupported_grant_type</code> | Không có converter/provider nào hỗ trợ grant được gửi. | Token endpoint trả lỗi giao thức. |
| <code>server_error</code> | Token generator hoặc hệ thống lưu trữ lỗi. | Không phát token không lưu trạng thái cần thiết, ghi audit an toàn. |

Đừng trả HTTP 200 cùng JSON chứa chuỗi “error” tự thiết kế cho một yêu cầu thất bại. Dùng <code>OAuth2AuthenticationException</code> với <code>OAuth2Error</code> phù hợp để framework chuyển thành lỗi giao thức; không để stack trace, token hoặc chi tiết khóa ký xuất hiện ở response cho client.

## 5. Tình huống minh họa: custom grant bằng one-time ticket

Giả sử hệ thống nội bộ có một thành phần **Ticket Issuer** đáng tin cậy, có nhiệm vụ phát hành credential ngắn hạn, ngẫu nhiên và chỉ dùng một lần cho confidential client <code>reports-worker</code>. Sau khi client chứng minh danh tính ở token endpoint, nó có thể đổi ticket lấy access token giới hạn scope <code>reports.generate</code>.

~~~mermaid
sequenceDiagram
    autonumber
    participant I as Trusted Ticket Issuer
    participant C as reports-worker
    participant AS as Authorization Server
    participant TS as OneTimeTicketService
    participant P as Custom AuthenticationProvider
    I-->>C: Cấp ticket qua kênh tin cậy, ràng buộc client + scope + TTL
    C->>AS: POST /oauth2/token + client auth + grant_type + ticket
    AS->>AS: OAuth2ClientAuthenticationFilter xác thực reports-worker
    AS->>P: Converter tạo OneTimeTicketAuthenticationToken
    P->>TS: Kiểm tra và consume ticket atomically với registeredClientId
    TS-->>P: Ticket hợp lệ, chưa dùng, scope được duyệt
    P->>AS: Sinh access token qua OAuth2TokenGenerator
    P->>AS: Lưu OAuth2Authorization
    AS-->>C: Access token với scope reports.generate
~~~

Đây là ví dụ **grant nội bộ**, không dùng thay thế OAuth 2.0 chuẩn ở môi trường không cần thiết. Không cấp ticket dựa đơn thuần trên một email, mã OTP dễ đoán hoặc tham số browser chưa xác thực. Ticket phải có entropy cao, ràng buộc client, TTL, một lần sử dụng, scope đã phê duyệt và quy tắc chống replay.

### 5.1. Tại sao chọn URI riêng?

Theo hướng dẫn Spring Authorization Server, một extension grant cần <code>grant_type</code> là **absolute URI duy nhất**. Trong bài dùng:

~~~text
urn:example:oauth:grant-type:one-time-ticket
~~~

Không sử dụng tên <code>authorization_code</code> hoặc <code>client_credentials</code> để định nghĩa lại ngữ nghĩa của grant chuẩn. Cũng không dùng URN thuộc namespace IETF một cách tùy tiện để ngụ ý grant tự tạo đã được chuẩn hóa.

### 5.2. HTTP request mẫu

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <redacted-reports-worker-credential>
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aexample%3Aoauth%3Agrant-type%3Aone-time-ticket&ticket=high-entropy-one-time-value
~~~

Với grant minh họa này:

- <code>ticket</code> là bắt buộc và chỉ có **một** giá trị.
- Không cho client tự thêm <code>scope</code> hoặc <code>resource</code> vào form để nâng quyền: tập quyền đã được Ticket Issuer quyết định và gắn với ticket.
- Client phải dùng phương thức client authentication đã đăng ký.
- Ticket được gửi qua HTTPS, không đưa lên query URL và không được log nguyên văn.
- Một ticket đã đổi thành công phải không thể dùng lại.

## 6. Định nghĩa AuthenticationToken chuyên biệt

<code>OAuth2AuthorizationGrantAuthenticationToken</code> là lớp cơ sở cho các authentication request thuộc OAuth authorization grant. Tạo subclass có dữ liệu riêng giúp provider chỉ xử lý đúng loại grant và tránh đọc request body lần thứ hai.

~~~java
public final class OneTimeTicketAuthenticationToken
        extends OAuth2AuthorizationGrantAuthenticationToken {

    public static final AuthorizationGrantType GRANT =
        new AuthorizationGrantType(
            "urn:example:oauth:grant-type:one-time-ticket");

    private final String ticket;

    public OneTimeTicketAuthenticationToken(
            String ticket, Authentication clientPrincipal) {
        super(GRANT, clientPrincipal, Map.of());
        this.ticket = ticket;
    }

    public String getTicket() {
        return ticket;
    }
}
~~~

Constructor truyền **client principal** vào lớp cơ sở; đó không phải danh tính End-User. Trong ví dụ này ticket chỉ cấp quyền cho workload/client, không biểu diễn đăng nhập của một người dùng cụ thể. Với grant đại diện cho End-User, nhà phát triển còn phải xác minh chủ thể, consent, mức xác thực và chính sách phù hợp; **không** tự lấy username từ một field form để biến thành principal được xác thực.

<code>ticket</code> là credential nhạy cảm dù được lưu trong object ngắn hạn. Không override <code>toString()</code> để in giá trị này, không đặt ticket vào event/log, và nên giới hạn vòng đời của object theo request. Nếu muốn hỗ trợ dọn credential, cân nhắc thiết kế kiểu dữ liệu cho phép xóa credential mà không ảnh hưởng kiểm tra cần thiết.

## 7. Viết AuthenticationConverter cho custom grant

Converter chỉ chuyển HTTP request thành một đối tượng mô tả **yêu cầu**. Nó chưa chứng minh ticket hợp lệ, cũng chưa cấp token.

~~~java
public final class OneTimeTicketAuthenticationConverter
        implements AuthenticationConverter {

    @Override
    public Authentication convert(HttpServletRequest request) {
        String grant = request.getParameter(
            OAuth2ParameterNames.GRANT_TYPE);

        // Nhường request của authorization_code, refresh_token,
        // client_credentials, device_code... cho converter khác.
        if (!OneTimeTicketAuthenticationToken.GRANT.getValue()
                .equals(grant)) {
            return null;
        }

        String[] grantValues = request.getParameterValues(
            OAuth2ParameterNames.GRANT_TYPE);
        if (grantValues == null || grantValues.length != 1) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_REQUEST);
        }

        String[] tickets = request.getParameterValues("ticket");
        if (tickets == null || tickets.length != 1
                || !StringUtils.hasText(tickets[0])) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_REQUEST);
        }

        // Grant này KHÔNG chấp nhận client tự quyết định scope/resource.
        if (request.getParameterMap().containsKey("scope")
                || request.getParameterMap().containsKey("resource")) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_REQUEST);
        }

        Authentication clientPrincipal =
            SecurityContextHolder.getContext().getAuthentication();

        return new OneTimeTicketAuthenticationToken(
            tickets[0], clientPrincipal);
    }
}
~~~

**Chi tiết đáng chú ý:**

1. Converter so chính xác <code>grant_type</code>. Không thuộc grant này thì trả <code>null</code>, cho phép converter mặc định khác xử lý.
2. <code>getParameterValues()</code> kiểm tra **số lần xuất hiện** của tham số. Nếu chỉ dùng <code>getParameter("ticket")</code>, một request có hai ticket có thể bị hiểu như một giá trị đầu tiên, làm validation không rõ ràng.
3. Nếu <code>grant_type</code> đúng nhưng thiếu ticket, ném <code>invalid_request</code>. Không dùng <code>return null</code> để che lỗi dữ liệu.
4. Không dựa vào client ID do browser gửi để tự đánh dấu client đã xác thực. <code>SecurityContextHolder</code> chỉ cung cấp kết quả client authentication ở chain phù hợp; provider **phải kiểm tra lại** loại và trạng thái principal.
5. Ví dụ không đưa <code>additionalParameters</code> tự do vào token. Nếu thực sự cần thêm tham số, phải kiểm tra cardinality, kiểu dữ liệu, độ dài và chỉ đưa dữ liệu đã chọn vào một map có kiểm soát.
6. <code>HttpServletRequest</code> ở đây là request của Token Endpoint. Không triển khai logic GET/query hoặc đọc raw JSON thay thế form URL encoded nếu giao thức yêu cầu POST form.

**Hạn chế của đoạn trích:** Converter tập trung kiểm tra shape của ticket grant. Các ràng buộc HTTP method, content type, kích thước payload, multipart, URL encoding và client authentication được cấu hình ở Token Endpoint/filter/hạ tầng; production nên kiểm thử tổng thể để bảo đảm request lạ không được parse thành grant hợp lệ.

## 8. Hợp đồng kiểm tra ticket một lần

Để phân tách nhiệm vụ, giả định ứng dụng cung cấp service sau:

~~~java
public interface OneTimeTicketService {
    /**
     * Kiểm tra và consume ticket theo registered client record ID.
     * Trả null khi không hợp lệ / đã dùng / hết hạn / sai client.
     * Việc kiểm tra + consume phải atomic ở storage chung.
     */
    ValidatedTicket validateAndConsume(
        String rawTicket, String registeredClientRecordId);
}

public record ValidatedTicket(
    String safeAuditId,
    Set<String> approvedScopes
) {}
~~~

**Quan trọng:** <code>OneTimeTicketService</code> và <code>ValidatedTicket</code> là **abstraction do ứng dụng tự viết**, không phải thư viện có sẵn. Một implementation production cần bảo đảm:

- Ticket được tạo bằng CSPRNG, đủ entropy, được giữ kín, giới hạn TTL và (nếu phù hợp) chỉ cấp qua kênh đáng tin.
- Lookup đúng ticket bằng giá trị được bảo vệ hoặc hash, không nhận dạng bằng các ký tự dễ đoán.
- Ticket **được ràng buộc với <code>RegisteredClient.getId()</code>**, không chỉ với client ID từ form.
- Mỗi ticket mang tập scope đã phê duyệt và phạm vi resource/audience cụ thể; không cho client tự chỉnh.
- Status chưa dùng/chưa hết hạn/không bị thu hồi được kiểm tra và chuyển sang consumed bằng **thao tác atomic** trên kho dùng chung.
- Một replay của ticket phải bị từ chối, kể cả hai request đến hai instance Authorization Server cùng lúc.
- Audit chỉ dùng mã định danh an toàn; không đưa raw ticket vào log, trace hoặc error response.

Nếu ticket đại diện cho sự ủy quyền của một End-User, service phải cung cấp **principal, tenant, consent và mức xác thực** được xác minh; ví dụ workload-only này cố ý không giả định có End-User.

**Độ nguyên tử giữa consume và lưu authorization:** Nếu ticket được đánh dấu consumed rồi token generator hoặc database lỗi, request có thể thất bại và ticket không dùng lại được. Đây là hành vi **fail closed** có thể chấp nhận về bảo mật nhưng cần thiết kế trải nghiệm tạo ticket mới. Nếu yêu cầu vừa consume ticket vừa lưu authorization trong một transaction, phải chọn backend/giao dịch hỗ trợ và kiểm thử rollback/race. Không âm thầm cho phép dùng lại ticket khi không biết lần trước đã cấp token thành công chưa.

## 9. Viết AuthenticationProvider cấp access token

Provider thực hiện **những kiểm tra bảo mật chính** rồi dùng cơ chế token generation và persistence của Spring Authorization Server. Trong ví dụ workload-only này, access token biểu diễn quyền của client; không phát refresh token và không suy ra một principal người dùng.

### 9.1. Skeleton provider có kiểm tra quan trọng

~~~java
public final class OneTimeTicketAuthenticationProvider
        implements AuthenticationProvider {

    private final OneTimeTicketService tickets;
    private final OAuth2AuthorizationService authorizations;
    private final OAuth2TokenGenerator<? extends OAuth2Token> tokenGenerator;

    public OneTimeTicketAuthenticationProvider(
            OneTimeTicketService tickets,
            OAuth2AuthorizationService authorizations,
            OAuth2TokenGenerator<? extends OAuth2Token> tokenGenerator) {
        this.tickets = Objects.requireNonNull(tickets);
        this.authorizations = Objects.requireNonNull(authorizations);
        this.tokenGenerator = Objects.requireNonNull(tokenGenerator);
    }

    @Override
    public Authentication authenticate(Authentication authentication)
            throws AuthenticationException {

        OneTimeTicketAuthenticationToken request =
            (OneTimeTicketAuthenticationToken) authentication;

        if (!(request.getPrincipal()
                instanceof OAuth2ClientAuthenticationToken client)
                || !client.isAuthenticated()
                || client.getRegisteredClient() == null) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_CLIENT);
        }

        RegisteredClient registeredClient = client.getRegisteredClient();
        if (!registeredClient.getAuthorizationGrantTypes()
                .contains(OneTimeTicketAuthenticationToken.GRANT)) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.UNAUTHORIZED_CLIENT);
        }

        // Service nghiệp vụ bắt buộc ràng buộc ticket với ID client,
        // kiểm tra TTL, policy, chống replay và consume atomically.
        ValidatedTicket verified = tickets.validateAndConsume(
            request.getTicket(), registeredClient.getId());
        if (verified == null) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_GRANT);
        }

        Set<String> scopes = Set.copyOf(verified.approvedScopes());
        if (scopes.isEmpty()
                || !registeredClient.getScopes().containsAll(scopes)) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_SCOPE);
        }

        OAuth2TokenContext tokenContext = DefaultOAuth2TokenContext
            .builder()
            .registeredClient(registeredClient)
            .principal(client)
            .authorizationServerContext(
                AuthorizationServerContextHolder.getContext())
            .authorizedScopes(scopes)
            .tokenType(OAuth2TokenType.ACCESS_TOKEN)
            .authorizationGrantType(
                OneTimeTicketAuthenticationToken.GRANT)
            .authorizationGrant(request)
            .build();

        OAuth2Token generated = tokenGenerator.generate(tokenContext);
        if (generated == null) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.SERVER_ERROR);
        }

        OAuth2AccessToken accessToken = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            generated.getTokenValue(),
            generated.getIssuedAt(),
            generated.getExpiresAt(),
            scopes
        );

        OAuth2Authorization.Builder authorizationBuilder =
            OAuth2Authorization.withRegisteredClient(registeredClient)
                .principalName(client.getName())
                .authorizationGrantType(
                    OneTimeTicketAuthenticationToken.GRANT)
                .authorizedScopes(scopes)
                .attribute("ticket_audit_id", verified.safeAuditId());

        if (generated instanceof ClaimAccessor claims) {
            authorizationBuilder.token(accessToken, metadata ->
                metadata.put(
                    OAuth2Authorization.Token.CLAIMS_METADATA_NAME,
                    claims.getClaims()));
        } else {
            authorizationBuilder.accessToken(accessToken);
        }

        authorizations.save(authorizationBuilder.build());

        return new OAuth2AccessTokenAuthenticationToken(
            registeredClient, client, accessToken);
    }

    @Override
    public boolean supports(Class<?> authentication) {
        return OneTimeTicketAuthenticationToken.class
            .isAssignableFrom(authentication);
    }
}
~~~

Các import được lược bỏ; lớp này sử dụng những API thường gặp trong Spring Authorization Server 1.5.x. Mã có **service nghiệp vụ giả định** và chưa cung cấp implementation lưu ticket, transaction, audit, OAuth error logging hoặc tests. Không được xem nó là một extension grant production-ready chỉ vì có thể biên dịch sau khi bổ sung bean.

### 9.2. Giải thích từng bước bắt buộc

| Bước | Tại sao cần |
| --- | --- |
| Kiểm tra <code>OAuth2ClientAuthenticationToken</code> | Không chấp nhận request chỉ có client ID do caller tự khai. |
| <code>client.isAuthenticated()</code> và RegisteredClient khác null | Phải có client đã được xác thực bởi cơ chế đã đăng ký. |
| <code>registeredClient.getAuthorizationGrantTypes().contains(GRANT)</code> | Không cho mọi client tùy ý dùng custom grant. |
| <code>validateAndConsume(ticket, registeredClient.getId())</code> | Bảo đảm ticket thật, đúng client, chưa dùng, chưa hết hạn và không replay. |
| <code>getScopes().containsAll(scopes)</code> | Scope từ ticket cũng không được vượt đăng ký hoặc chính sách client. |
| <code>DefaultOAuth2TokenContext</code> | Cung cấp client, principal, grant, scope và token type cho generator. |
| <code>OAuth2TokenGenerator.generate(...)</code> | Dùng cơ chế sinh token của AS thay vì tự tạo JWT không đồng nhất. |
| <code>OAuth2AuthorizationService.save(...)</code> | Lưu token và trạng thái authorization để kiểm tra/introspection/revocation khi cần. |
| <code>OAuth2AccessTokenAuthenticationToken</code> | Trả đúng kiểu kết quả để endpoint xuất access token response. |

Không đưa raw ticket vào <code>OAuth2Authorization.attribute(...)</code>. Chỉ lưu audit ID đã được thiết kế không tiết lộ credential. Với JWT token generator, <code>ClaimAccessor</code> giúp giữ claims metadata trong authorization store theo mẫu của Spring; vẫn phải kiểm soát dữ liệu claims nhạy cảm.

### 9.3. Scope và subject của access token

Trong ví dụ client-only này:

- <code>principal(client)</code> nghĩa là principal của quá trình cấp token là client; không tự suy ra Alice/Bob.
- <code>scopes</code> lấy từ ticket đã được Ticket Issuer kiểm tra, sau đó giới hạn theo registered client.
- Nếu JWT có <code>sub</code>, phải xác minh ngữ nghĩa của <code>sub</code> theo generator/profile đang dùng; không tự thay bằng username từ form.
- <code>aud</code> của access token phải phục vụ Resource Server đã được cho phép, không dùng endpoint Token hoặc một resource URI do client tự nhập mà chưa kiểm tra.
- Nếu dùng token format reference/opaque, token generator và metadata phải tương thích với cơ chế introspection/revocation.

Vì custom grant này không có một authorization code hoặc consent của End-User, **không phát refresh token hoặc ID Token một cách mặc định**. Nếu bài toán yêu cầu refresh token, phải thiết kế và kiểm thử vòng đời/rotation/replay theo chính sách; nếu cần ID Token, đó là ngữ nghĩa OIDC End-User authentication khác.

### 9.4. Tương thích TokenSettings và generator

<code>OAuth2TokenGenerator</code> có thể là một <code>DelegatingOAuth2TokenGenerator</code> gồm <code>JwtGenerator</code>, <code>OAuth2AccessTokenGenerator</code> và các generator phù hợp. Nó dựa trên <code>OAuth2TokenContext</code>, <code>TokenSettings</code>, key/JWK và cấu hình format để quyết định token được phát hành. Provider phải xử lý trường hợp <code>generate(...)</code> trả <code>null</code> thay vì trả token rỗng.

Một điểm cần kiểm tra là token claim customization chỉ chạy cho đúng loại token/format. Ví dụ <code>OAuth2TokenCustomizer&lt;JwtEncodingContext&gt;</code> không đồng nghĩa mọi opaque token đều nhận cùng claim; Resource Server vẫn phải kiểm tra issuer, audience, thời hạn và các quyền thực tế.

## 10. Cấu hình converter/provider vào Token Endpoint

### 10.1. Cách thêm extension grant mà vẫn giữ các grant mặc định

~~~java
@Configuration
@EnableWebSecurity
class AuthorizationServerSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http,
            OneTimeTicketService ticketService,
            OAuth2AuthorizationService authorizationService,
            OAuth2TokenGenerator<?> tokenGenerator) throws Exception {

        OAuth2AuthorizationServerConfigurer as =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(as.getEndpointsMatcher())
            .with(as, server -> server
                .tokenEndpoint(tokenEndpoint -> tokenEndpoint
                    .accessTokenRequestConverter(
                        new OneTimeTicketAuthenticationConverter())
                    .authenticationProvider(
                        new OneTimeTicketAuthenticationProvider(
                            ticketService,
                            authorizationService,
                            tokenGenerator))))
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

        return http.build();
    }
}
~~~

Cấu hình này **thêm** converter và provider cho ticket grant. Những grant chuẩn như Authorization Code, Refresh Token và Client Credentials tiếp tục dùng converter/provider mặc định, trừ khi bạn thay đổi danh sách bằng API khác.

Ứng dụng thật còn cần <code>RegisteredClientRepository</code>, <code>OAuth2AuthorizationService</code>, token generator/JWK, client authentication và các bean nền tảng. Nếu triển khai Authorization Code/OIDC cho người dùng, còn cần chain web/login và các dịch vụ user authentication/consent tương ứng. Ví dụ không tắt CSRF toàn ứng dụng.

### 10.2. RegisteredClient phải cho phép custom grant

~~~java
RegisteredClient reportsWorker = RegisteredClient
    .withId("reports-worker-record-001")
    .clientId("reports-worker")
    .clientSecret(encodedClientSecret)
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        OneTimeTicketAuthenticationToken.GRANT)
    .scope("reports.generate")
    .tokenSettings(TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .build())
    .build();
~~~

<code>encodedClientSecret</code> là secret đã mã hóa phù hợp với <code>PasswordEncoder</code> và được cung cấp an toàn; không commit secret plaintext. Đây là **confidential client** nên sử dụng xác thực client thật. Nếu bỏ <code>authorizationGrantType(...)</code>, provider phải từ chối bằng <code>unauthorized_client</code> dù client đăng nhập đúng.

Không tự bật custom grant cho SPA/mobile public client chỉ vì nó có thể gửi ticket. Phải phân tích ranh giới tin cậy: ticket bearer bị lộ, public client không thể bảo vệ shared secret, yêu cầu bảo vệ tài nguyên và nguy cơ replay.

### 10.3. Những trường hợp ưu tiên dùng grant chuẩn

| Nhu cầu | Hướng tiếp cận nên xem xét |
| --- | --- |
| Người dùng đăng nhập và đồng ý cấp quyền | Authorization Code + PKCE/OIDC. |
| Máy chạy tác vụ dưới danh tính ứng dụng | Client Credentials, nếu quyền client là đủ. |
| Client đổi một token đã có lấy token cho audience khác theo policy | Token Exchange (RFC 8693), nếu framework/version hỗ trợ đúng yêu cầu. |
| Thiết bị không có trình duyệt phù hợp | Device Authorization Grant (RFC 8628). |
| Trình một JWT assertion được ký làm authorization grant | Các profile chuẩn thích hợp như RFC 7523, nếu thực sự phù hợp và đã được hỗ trợ/cấu hình. |
| One-time ticket nội bộ có ngữ nghĩa đặc thù | Chỉ cân nhắc custom grant sau khi có threat model, validation, storage, audit và test đầy đủ. |

Đừng xây một “password grant” tự viết để lách việc loại bỏ Resource Owner Password Credentials khỏi thực hành bảo mật hiện đại. Không nhận password/MFA code của End-User trong Token Endpoint custom mà không có một giao thức xác thực người dùng được thiết kế đầy đủ.

## 11. Tùy chỉnh AuthenticationProvider có sẵn mà không nới scope

Không phải mọi yêu cầu đều cần custom grant. Ví dụ: công ty muốn bổ sung một chính sách với **Client Credentials** để client <code>reports-worker</code> không được xin <code>reports.admin</code> dù scope này từng được đăng ký trong hệ thống cũ. Tốt nhất là sửa đăng ký/policy ở nguồn có thẩm quyền; nếu cần check runtime ở provider, hãy dùng extension point có sẵn.

Spring Authorization Server 1.5.x có <code>OAuth2ClientCredentialsAuthenticationProvider.setAuthenticationValidator(...)</code> và <code>OAuth2ClientCredentialsAuthenticationValidator.DEFAULT_SCOPE_VALIDATOR</code>. Khi thay validator, **phải giữ check mặc định rồi thêm điều kiện mới**:

~~~java
private static Consumer<List<AuthenticationProvider>>
        clientCredentialsPolicy() {

    return providers -> providers.forEach(provider -> {
        if (provider instanceof
                OAuth2ClientCredentialsAuthenticationProvider credentials) {

            credentials.setAuthenticationValidator(context -> {
                // BẮT BUỘC: bảo lưu validation scope mặc định.
                OAuth2ClientCredentialsAuthenticationValidator
                    .DEFAULT_SCOPE_VALIDATOR.accept(context);

                RegisteredClient registeredClient =
                    context.getRegisteredClient();

                Set<String> requestedScopes =
                    context.getAuthentication().getScopes();

                if ("reports-worker".equals(registeredClient.getClientId())
                        && requestedScopes.contains("reports.admin")) {
                    throw new OAuth2AuthenticationException(
                        OAuth2ErrorCodes.INVALID_SCOPE);
                }
            });
        }
    });
}
~~~

Gắn consumer đó:

~~~java
http.securityMatcher(as.getEndpointsMatcher())
    .with(as, server -> server.tokenEndpoint(tokenEndpoint ->
        tokenEndpoint.authenticationProviders(
            clientCredentialsPolicy())))
    .authorizeHttpRequests(authorize ->
        authorize.anyRequest().authenticated());
~~~

Ở đây <code>as</code> là <code>OAuth2AuthorizationServerConfigurer</code> đã được tạo trong cùng <code>SecurityFilterChain</code>. Đây là một **đoạn cấu hình nối tiếp**, không phải security chain đầy đủ độc lập.

**Điểm quan trọng:** <code>setAuthenticationValidator(...)</code> thay validator của provider; nếu chỉ đặt custom validator mà **không** gọi <code>DEFAULT_SCOPE_VALIDATOR</code>, bạn có thể vô tình mất kiểm tra tập scope nằm trong RegisteredClient. Trong một hệ thống thật, bổ sung thêm policy từ nguồn tin cậy (tenant, trạng thái client, entitlement) thay vì chỉ so một chuỗi hằng như ví dụ.

### 11.1. Khi nào dùng biến thể danh sách?

- <code>authenticationProviders(listConsumer)</code> hữu ích khi muốn tìm một provider mặc định theo **đúng class**, cấu hình validator/hook được hỗ trợ, hoặc thêm provider trước/sau một loại cụ thể.
- <code>accessTokenRequestConverters(listConsumer)</code> hữu ích khi cần truy cập converter mặc định và can thiệp có chủ đích vào thứ tự/behavior.
- Nếu chỉ thêm một grant mới, ưu tiên <code>authenticationProvider(...)</code> và <code>accessTokenRequestConverter(...)</code> thay vì tự tạo toàn bộ list để giảm rủi ro mất các grant chuẩn.
- Không loại bỏ provider <code>authorization_code</code> hoặc <code>refresh_token</code> mà không có kế hoạch thay thế và integration test: làm vậy có thể khiến request hợp lệ trả <code>unsupported_grant_type</code> hoặc lỗi khác.

**Phân biệt rõ:** <code>authenticationProviders(...)</code> của **Token Endpoint** khác <code>clientAuthentication(...)</code> của **Authorization Server**. Nếu mục tiêu là thay cách xác thực <code>client_secret_basic</code>, <code>private_key_jwt</code> hoặc mTLS, cần xem extension point **client authentication**, không dùng converter của authorization grant để bỏ qua client authentication.

## 12. Các bất biến bảo mật phải bảo toàn

Một custom converter/provider thành công phải giữ những bất biến sau:

~~~text
Client:
  Có Authentication thật và RegisteredClient hợp lệ
  Phương thức client authentication phù hợp với đăng ký

Grant:
  grant_type duy nhất, đúng định dạng và được client cho phép
  Credential/grant proof hợp lệ, chưa hết hạn, chưa dùng, đúng client
  Không replay hoặc dùng chéo issuer/tenant/resource theo policy

Token:
  grantedScopes ⊆ registeredClient.scopes ∩ grantAllowedScopes
  audience/resource được phép, không do form tự cấp
  token_type/expiry/format phù hợp với TokenSettings
  authorization state được lưu nhất quán
  Không đưa token/secret/code vào log

Response:
  Thành công trả OAuth2AccessTokenAuthenticationToken
  Thất bại trả lỗi OAuth2 thích hợp
  Không phát token khi persistence/policy validation thất bại
~~~

### 12.1. Client binding

Khi service xác minh ticket, phải dùng <code>registeredClient.getId()</code> đã được xác thực, không dùng <code>client_id</code> do request body tự khai mà chưa qua <code>OAuth2ClientAuthenticationFilter</code>. Cặp <code>registeredClientId</code> và <code>authorization</code> cần nhất quán trong token store.

Nếu hai client được đăng ký cùng scope, client B vẫn không được đổi ticket do client A sở hữu. Sự giống nhau về scope **không** tạo ra quyền chuyển credential giữa các client.

### 12.2. Grant evidence và replay

Custom ticket/code có thể là bearer credential: ai đánh cắp được có thể thử dùng trước chủ sở hữu. Nếu chỉ kiểm tra timestamp mà không đánh dấu đã sử dụng, một ticket còn hạn có thể bị đổi nhiều lần.

Thiết kế nên có:

1. Giá trị ngẫu nhiên đủ entropy và TTL ngắn.
2. Ràng buộc client, issuer, resource, tenant nếu cần.
3. Lưu trạng thái pending/consumed/revoked và sử dụng **atomic compare-and-set** hoặc transaction phù hợp.
4. Chỉ một request thắng khi hai instance cố consume cùng ticket.
5. Giám sát replay mà không lưu raw credential.
6. Xử lý lỗi DB theo chính sách **fail closed**, không phát token khi không xác minh được ticket.

Không dùng <code>synchronized</code> cục bộ trong một JVM làm cơ chế duy nhất khi hệ thống có nhiều Authorization Server instance.

### 12.3. Scope và audience

Scope được khai trong <code>RegisteredClient</code> chỉ là giới hạn đăng ký; ticket cũng phải có scope được policy duyệt. Không tự gán <code>registeredClient.getScopes()</code> toàn bộ vào token chỉ vì client được phép xin các scope đó.

Đối với access token JWT, <code>aud</code> phải phù hợp Resource Server, còn <code>iss</code> là issuer Authorization Server; không đặt mọi token chung một audience “*”. Nếu grant có dữ liệu <code>resource</code>, phải xác minh nó với chính sách/hợp đồng cấp ticket, tránh token substitution giữa API.

### 12.4. Refresh token, consent và End-User

Custom grant trong bài **không** có End-User và chỉ phát access token; không tự phát refresh token hay ID Token. Với extension grant cho người dùng, cần có bằng chứng xác thực/consent hợp lệ, kiểm tra user status và chính sách refresh/revoke riêng.

<code>OAuth2AuthorizationConsentService</code> lưu quyết định consent cho client và principal, không tự biến một ticket tùy ý thành quyền đăng nhập. <code>OAuth2AuthorizationService</code> lưu authorization/token đã phát hành; xóa consent đơn lẻ không tự vô hiệu hóa mọi JWT access token cũ.

### 12.5. Không đưa chính sách vào response handler để lách provider

<code>accessTokenResponseHandler(...)</code> dùng khi kết quả đã được xác thực. Nếu xử lý logic cấp quyền hoặc chọn scope ở đây, có nguy cơ authorization đã được lưu và token đã phát hành trước khi bạn quyết định từ chối. Các điều kiện an toàn cần nằm ở converter/provider/service trước khi token generation/response.

## 13. Kiểm thử converter và provider

### 13.1. Unit test converter

Converter phải nhường grant khác và báo lỗi khi grant của mình bị lỗi:

~~~java
@Test
void converterIgnoresOtherGrantTypes() {
    MockHttpServletRequest request =
        new MockHttpServletRequest("POST", "/oauth2/token");
    request.setParameter("grant_type", "client_credentials");

    Authentication result =
        new OneTimeTicketAuthenticationConverter().convert(request);

    assertThat(result).isNull();
}

@Test
void converterRejectsDuplicateTickets() {
    MockHttpServletRequest request =
        new MockHttpServletRequest("POST", "/oauth2/token");
    request.setParameter(
        "grant_type",
        OneTimeTicketAuthenticationToken.GRANT.getValue());
    request.setParameter("ticket", "first", "second");

    assertThatThrownBy(() ->
        new OneTimeTicketAuthenticationConverter().convert(request))
        .isInstanceOf(OAuth2AuthenticationException.class);
}
~~~

Nên bổ sung test thiếu ticket, ticket blank, <code>grant_type</code> lặp, <code>scope</code>/<code>resource</code> không được hỗ trợ, độ dài và encoding bất thường. Unit test converter chỉ kiểm tra **cách đọc dữ liệu**, không chứng minh client đã được xác thực.

### 13.2. Unit test provider

Với <code>OneTimeTicketService</code> fake/mock và <code>OAuth2TokenGenerator</code> test, kiểm tra:

- Client principal không phải <code>OAuth2ClientAuthenticationToken</code> hoặc chưa authenticated ⇒ <code>invalid_client</code>.
- Client đã xác thực nhưng không đăng ký custom grant ⇒ <code>unauthorized_client</code>.
- Ticket không tồn tại/hết hạn/đã dùng/sai registered client ID ⇒ <code>invalid_grant</code>.
- Ticket cho phép scope ngoài RegisteredClient ⇒ <code>invalid_scope</code>.
- Token generator trả <code>null</code> ⇒ <code>server_error</code>, không phát access token.
- Ticket hợp lệ và scopes đúng ⇒ lưu <code>OAuth2Authorization</code> đúng client/grant/scopes, trả <code>OAuth2AccessTokenAuthenticationToken</code>.
- Khi hai request cạnh tranh cùng ticket ⇒ đúng một request thành công theo thiết kế service atomic.

Trong unit test, có thể fake <code>OAuth2ClientAuthenticationToken</code> đã authenticated để thử riêng provider. Nhưng **không dùng kiểu fake đó để kết luận client authentication qua HTTP đã được kiểm chứng**.

### 13.3. Integration test Token Endpoint

Ví dụ một kiểm thử HTTP với <code>MockMvc</code>, giả định đã có fixture confidential client, ticket hợp lệ và tất cả bean Authorization Server:

~~~java
@Test
void acceptsValidOneTimeTicket() throws Exception {
    String issuedTicket = ticketFixtures.issueFor(
        "reports-worker-record-001", Set.of("reports.generate"));

    mockMvc.perform(post("/oauth2/token")
            .with(httpBasic("reports-worker", "test-only-secret"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("grant_type",
                OneTimeTicketAuthenticationToken.GRANT.getValue())
            .param("ticket", issuedTicket))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.access_token").exists())
        .andExpect(jsonPath("$.token_type").value("Bearer"));
}
~~~

<code>ticketFixtures.issueFor(...)</code> là **test helper do dự án tự viết**, không phải API Spring. <code>test-only-secret</code> chỉ dùng với client test đã được đăng ký/encode đúng. Một test hoàn chỉnh còn đọc lại <code>OAuth2Authorization</code>, kiểm tra scope và token claims/audience, gọi Resource Server nếu cần, và xác nhận ticket chỉ dùng được một lần.

### 13.4. Ma trận integration test hồi quy

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Custom grant đúng, ticket hợp lệ, client đã xác thực | Access token được cấp với scope hợp lệ, lưu đúng authorization. |
| Custom grant thiếu ticket | <code>invalid_request</code>. |
| Custom grant có hai ticket | <code>invalid_request</code>. |
| Grant mới nhưng client không đăng ký grant | <code>unauthorized_client</code>. |
| Client bí mật sai hoặc thiếu xác thực | <code>invalid_client</code> hoặc phản hồi tương ứng của client authentication. |
| Ticket đã dùng hoặc hết hạn | <code>invalid_grant</code>; không phát token. |
| Ticket của client A được client B trình | Bị từ chối; không tạo authorization cho client B. |
| Ticket cấp scope vượt quyền client | <code>invalid_scope</code>; không cấp thêm quyền. |
| Client sửa form gửi scope/resource | Bị từ chối nếu custom grant không hỗ trợ; không thay phạm vi ticket. |
| Token generator lỗi | Không trả access token; xử lý <code>server_error</code>/hạ tầng an toàn. |
| Authorization DB lỗi | Không báo thành công khi trạng thái không được lưu theo thiết kế. |
| Hai request cùng ticket đến hai node | Chỉ một request có thể consume ticket; không phát hai lần trái chính sách. |
| <code>authorization_code</code> chuẩn với PKCE | Vẫn hoạt động, converter custom trả <code>null</code> cho grant khác. |
| <code>refresh_token</code> chuẩn | Vẫn kiểm tra đúng client, authorization, active state và scope. |
| <code>client_credentials</code> chuẩn | Vẫn kiểm tra scope mặc định và policy được bổ sung. |
| <code>device_code</code> nếu bật | Vẫn nhận pending/denied/success theo giao thức. |
| <code>token-exchange</code> nếu version hỗ trợ | Không bị converter/provider custom bắt nhầm. |
| Response chứa credential nhạy cảm trong log | Test/kiểm tra log xác nhận đã ẩn secret/ticket/token. |

Đừng chỉ test HTTP 200; cần xác nhận **token thật sự phản ánh đúng issuer, audience, scope, client và authorization**, đồng thời các trường hợp lỗi không phát token.

## 14. Lỗi thiết kế thường gặp và cách chẩn đoán

### Lỗi 1: Converter trả non-null cho mọi request

**Triệu chứng:** Authorization Code hoặc Refresh Token đột nhiên lỗi sau khi thêm custom grant.

**Nguyên nhân:** Converter không kiểm tra chính xác <code>grant_type</code> hoặc luôn tạo custom authentication token.

**Cách sửa:** Trả <code>null</code> ngay nếu grant khác; kiểm thử hồi quy các grant chuẩn.

### Lỗi 2: Converter trả null khi request custom sai

**Triệu chứng:** Client gửi đúng grant URI nhưng thiếu tham số <code>ticket</code>, endpoint trả lỗi không rõ hoặc không đến provider.

**Nguyên nhân:** Dùng <code>return null</code> thay vì <code>invalid_request</code>.

**Cách sửa:** Phân biệt “không phải grant của tôi” với “grant của tôi nhưng request sai”; ném <code>OAuth2AuthenticationException</code> thích hợp.

### Lỗi 3: Provider xác thực grant nhưng quên xác thực client

**Triệu chứng:** Client lạ có ticket có thể xin token.

**Nguyên nhân:** Tin client ID trong request hoặc bỏ qua <code>OAuth2ClientAuthenticationToken.isAuthenticated()</code>.

**Cách sửa:** Bắt buộc principal có RegisteredClient đã xác thực, kiểm tra phương thức client authentication ở tầng tương ứng và ràng buộc ticket theo ID client nội bộ.

### Lỗi 4: Không kiểm tra grant thuộc danh sách đăng ký

**Triệu chứng:** Mọi client đều dùng được grant mới.

**Nguyên nhân:** Provider không kiểm tra <code>RegisteredClient.getAuthorizationGrantTypes()</code>.

**Cách sửa:** Từ chối bằng <code>unauthorized_client</code> nếu chưa đăng ký grant; quản trị grant theo chính sách rõ ràng.

### Lỗi 5: Thay validator mặc định bằng validator quá đơn giản

**Triệu chứng:** Client Credentials xin scope ngoài đăng ký vẫn nhận token.

**Nguyên nhân:** Gọi <code>setAuthenticationValidator()</code> mà không giữ <code>DEFAULT_SCOPE_VALIDATOR</code>.

**Cách sửa:** Compose default validator và policy bổ sung; có test cho scope ngoài đăng ký.

### Lỗi 6: Phát token bằng cách tự ký JWT trong converter

**Triệu chứng:** Token thiếu issuer/audience chuẩn, không được lưu authorization, không thể introspect/revoke đúng hoặc có TTL khác client settings.

**Nguyên nhân:** Trộn đọc request với phát token và không dùng <code>OAuth2TokenGenerator</code>/<code>OAuth2AuthorizationService</code>.

**Cách sửa:** Converter chỉ parse, provider dùng token generator và lưu state theo hợp đồng.

### Lỗi 7: Tạo TicketService chỉ có kiểm tra rồi mới xóa

**Triệu chứng:** Hai request đồng thời đều đổi cùng ticket thành công.

**Nguyên nhân:** <code>if (ticket.active) ... ticket.active=false</code> không atomic giữa nhiều node.

**Cách sửa:** Dùng transaction/compare-and-set trên storage chung, kiểm thử race; không dựa vào lock một JVM.

### Lỗi 8: Cấu hình nhầm Token Endpoint với Client Authentication Endpoint

**Triệu chứng:** Tùy chỉnh grant converter nhưng <code>client_secret_jwt</code> hoặc mTLS không thay đổi.

**Nguyên nhân:** Cơ chế xác thực client được cấu hình qua <code>clientAuthentication(...)</code>, không phải <code>tokenEndpoint(...)</code>.

**Cách sửa:** Chọn đúng extension point theo trách nhiệm, không tắt client authentication để “giải quyết” lỗi.

### Lỗi 9: Không có một nguồn lưu authorization thống nhất

**Triệu chứng:** Token đổi thành công tại node A nhưng introspection/revocation ở node B không tìm thấy.

**Nguyên nhân:** In-memory service khác nhau giữa node hoặc database schema/transaction không phù hợp.

**Cách sửa:** Dùng repository chia sẻ, migration đúng version, kiểm tra concurrency và tính nhất quán token state.

## 15. Vận hành production và kiểm soát thay đổi

Trước khi triển khai một custom converter/provider, nhóm phát triển nên xác nhận:

| Hạng mục | Câu hỏi |
| --- | --- |
| Nhu cầu giao thức | Có thể giải quyết bằng Authorization Code/PKCE, Client Credentials, Device Grant hoặc Token Exchange chuẩn không? |
| Grant naming | URI duy nhất, không xung đột grant chuẩn hoặc client khác? |
| Client authentication | Client nào được phép dùng grant? Có bảo vệ credential và đăng ký method đúng không? |
| Input validation | Cardinality, content type, độ dài, encoding, tham số lạ, grant type đã được kiểm soát? |
| Grant evidence | Ticket/code có entropy, TTL, ràng buộc client/tenant/resource và one-time semantics? |
| Token policy | Scope, audience, TTL, format, claims và Resource Server được giới hạn đúng? |
| Persistence | Authorization/token được lưu trước khi báo thành công? Có transaction phù hợp? |
| Multi-instance | Ticket consume, token issuance, replay detection có atomic và cùng nguồn dữ liệu? |
| Error handling | OAuth errors đúng, không lộ ticket/secret/token hay stack trace? |
| Observability | Log mã lỗi, client ID, request ID và audit ID an toàn; không log credential raw? |
| Test | Unit converter/provider, integration HTTP, regression grant chuẩn và race trên DB thật? |
| Upgrade | API/configurer/default provider list được xác minh khi nâng Spring Boot/Security/Authorization Server? |

Ngoài test kỹ thuật, cần thực hiện **threat modeling** cho custom grant: ai phát hành ticket, ai có thể lấy ticket, có thể replay hoặc dùng chéo client không, thời gian hiệu lực và hậu quả khi Ticket Issuer bị chiếm đoạt. Với hệ thống có yêu cầu tuân thủ hoặc nhiều bên thứ ba, thường nên tránh custom grant không được chuẩn hóa.

## 16. Bài tập thực hành

Một công ty có các client: <code>billing-worker</code> chạy Client Credentials, <code>reports-worker</code> có quyền đổi one-time ticket, và <code>portal-web</code> dùng Authorization Code + PKCE. Hãy hoàn thành:

1. Vẽ luồng <code>OAuth2ClientAuthenticationFilter → OAuth2TokenEndpointFilter → converter → provider → token generator → authorization service</code>. Chỉ ra bước nào xác thực client, bước nào xác minh grant.
2. Đăng ký custom grant <code>urn:example:oauth:grant-type:one-time-ticket</code> cho **chỉ <code>reports-worker</code>**.
3. Viết converter từ chối request custom thiếu ticket, ticket trùng hai lần, thêm scope ngoài hợp đồng; nhường mọi grant khác bằng <code>null</code>.
4. Viết <code>OneTimeTicketAuthenticationToken</code> kế thừa <code>OAuth2AuthorizationGrantAuthenticationToken</code>; giải thích vì sao class cần riêng.
5. Thiết kế <code>OneTimeTicketService</code> dùng database để consume ticket một lần bằng thao tác atomic. Minh họa khi hai request chạy ở hai node.
6. Viết provider kiểm tra client đã xác thực, grant đã đăng ký, ticket đúng client/chưa hết hạn/chưa dùng, scope không vượt client và resource được phép.
7. Dùng <code>OAuth2TokenGenerator</code> cấp access token, lưu <code>OAuth2Authorization</code>, trả <code>OAuth2AccessTokenAuthenticationToken</code>. Không phát refresh/ID token trong ví dụ workload-only.
8. Bổ sung validator cho Client Credentials để chặn một scope nhạy cảm nhưng vẫn gọi <code>DEFAULT_SCOPE_VALIDATOR</code>.
9. Viết integration tests cho sai secret, ticket thuộc client khác, ticket đã dùng, concurrent request, token generator lỗi, scope leo thang và grant chuẩn vẫn hoạt động.
10. Nếu dự án nâng Spring Security lên API Authorization Server mới, liệt kê các class/package/configurer cần kiểm chứng lại trước khi triển khai.

**Tiêu chí đạt:** Converter chỉ **phân tích đúng request**, provider **xác minh đầy đủ và phát token theo policy**, customization **không phá grant mặc định**, và không thể dùng một ticket của client này để cấp token cho client khác.

## 17. Tài liệu đối chiếu

- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Token Endpoint, converter/provider mặc định và các extension point.
- [Spring Authorization Server — How-to Implement an Extension Authorization Grant Type](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-ext-grant-type.html): mẫu chính thức về custom grant, <code>AuthenticationConverter</code>, <code>AuthenticationProvider</code> và cấu hình.
- [Spring Authorization Server — OAuth2TokenEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2TokenEndpointConfigurer.html): chữ ký các phương thức <code>accessTokenRequestConverter(s)</code>, <code>authenticationProvider(s)</code>.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): <code>RegisteredClient</code>, <code>OAuth2Authorization</code>, <code>OAuth2AuthorizationService</code>.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): filter chain, client authentication và endpoint configurers.
- [Spring Authorization Server — OAuth2ClientCredentialsAuthenticationValidator API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2ClientCredentialsAuthenticationValidator.html): bảo toàn validation mặc định khi bổ sung policy.
- [Spring Security — OAuth2 Authorization Server Protocol Endpoints](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/protocol-endpoints.html): API trong các nhánh Spring Security tích hợp Authorization Server.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): token endpoint, grant validation, mã lỗi và client authentication.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo mật OAuth 2.0 hiện đại, giới hạn grant/credentials và refresh token.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): grant chuẩn để trao đổi token khi có nhu cầu phù hợp.
