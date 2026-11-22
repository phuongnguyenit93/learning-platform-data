# 2.7. Client Credentials Grant và danh tính của ứng dụng

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Giải thích khi nào nên sử dụng **OAuth 2.0 Client Credentials Grant** cho giao tiếp giữa các ứng dụng hoặc dịch vụ.
- Phân biệt **xác thực client**, **ủy quyền truy cập API** và **xác thực người dùng cuối**.
- Mô tả quy trình lấy access token trực tiếp từ token endpoint mà không có trình duyệt, authorization code hay phiên đăng nhập người dùng.
- Hiểu “danh tính ứng dụng” được biểu diễn và kiểm tra ở đâu, cũng như giới hạn khi diễn giải claim trong access token.
- Cấu hình Spring Boot và sử dụng `OAuth2AuthorizedClientManager` để lấy, tái sử dụng access token khi một tác vụ backend gọi API khác.
- Nhận diện các yêu cầu bảo mật khi lưu client credential, giới hạn phạm vi quyền và quản lý vòng đời token.

## 1. Bối cảnh: dịch vụ cần quyền truy cập nhưng không có người dùng đăng nhập

Giả sử một hệ thống có hai dịch vụ:

- **Order Scheduler:** cứ vài phút tổng hợp các đơn hàng cần vận chuyển.
- **Inventory API:** cung cấp thông tin tồn kho và chỉ trả dữ liệu cho những ứng dụng được phép.

Order Scheduler chạy như một tác vụ nền. Không có người dùng nào mở trình duyệt hoặc bấm nút “Đăng nhập” tại thời điểm tác vụ bắt đầu. Tuy vậy, Inventory API vẫn cần biết **ứng dụng gọi đến đã được cấp quyền hay chưa**.

Nếu dùng tài khoản người dùng giả và mật khẩu để đăng nhập, hệ thống sẽ trộn lẫn danh tính của ứng dụng với danh tính con người. Nếu để API mở hoàn toàn, bất kỳ ai biết địa chỉ endpoint cũng có thể gửi request.

OAuth 2.0 cung cấp một cơ chế phù hợp hơn: **Client Credentials Grant**. Ứng dụng đăng ký với Authorization Server, chứng minh danh tính client, được cấp **access token**, rồi sử dụng access token để gọi API.

> Điểm cốt lõi: với Client Credentials Grant, **client hoạt động nhân danh chính nó** hoặc theo một thỏa thuận ủy quyền đã được thiết lập với Authorization Server; không có bước người dùng cuối trực tiếp đăng nhập để ủy quyền trong luồng này.

## 2. Client Credentials Grant là gì?

**Client Credentials Grant** là một grant type của OAuth 2.0, được mô tả trong RFC 6749, mục 4.4. Client có thể dùng thông tin xác thực của chính mình để yêu cầu access token tại Authorization Server.

Grant này dành cho client có khả năng xác thực với Authorization Server và bảo vệ thông tin xác thực cần thiết, thường là **confidential client** chạy ở backend hoặc môi trường máy chủ có quản lý bí mật.

### 2.1. Các thành phần tham gia

| Thành phần | Vai trò trong ví dụ |
|---|---|
| **OAuth 2.0 Client** | Order Scheduler: chương trình muốn gọi Inventory API |
| **Authorization Server (AS)** | Xác thực client, xác định quyền được cấp và phát hành access token |
| **Resource Server (RS)** | Inventory API: nhận access token và quyết định cho phép thao tác nào |
| **Resource Owner** | Chủ thể hoặc tổ chức sở hữu quyền đối với tài nguyên; việc ủy quyền được thiết lập trước theo chính sách thay vì qua màn hình đồng ý của người dùng trong luồng này |

Trong nhiều hệ thống, Authorization Server và Resource Server là hai sản phẩm hoặc dịch vụ khác nhau. Client phải tin cậy và cấu hình đúng Authorization Server cấp token cho API đích.

### 2.2. Những bước không có trong luồng

Client Credentials Grant **không cần**:

- Trang đăng nhập tương tác với người dùng cuối.
- Chuyển hướng browser đến authorization endpoint.
- Authorization code và redirect URI.
- `state`, `nonce` hoặc PKCE phục vụ các luồng tương tác tương ứng.
- OIDC ID token để xác thực một End-User.

Không có authorization code không có nghĩa là bỏ qua bảo mật. Client vẫn phải chứng minh danh tính với Authorization Server, còn Resource Server vẫn phải kiểm tra access token và quyền truy cập.

### 2.3. Sơ đồ luồng

~~~mermaid
sequenceDiagram
    autonumber
    participant Job as Order Scheduler (OAuth Client)
    participant AS as Authorization Server
    participant API as Inventory API (Resource Server)
    Job->>AS: POST /oauth2/token, grant_type=client_credentials<br/>+ xác thực client, scope yêu cầu
    AS->>AS: Xác thực client và kiểm tra quyền đã cấp
    AS-->>Job: access_token, token_type, expires_in
    Job->>API: GET /api/inventory<br/>Authorization: Bearer access_token
    API->>API: Kiểm tra token và chính sách phân quyền
    API-->>Job: Dữ liệu tồn kho được phép truy cập
    Note over Job,AS: Khi token hết hạn, client yêu cầu token mới theo chính sách
~~~

Luồng đi qua hai mối quan hệ tin cậy khác nhau:

1. **Client → Authorization Server:** “Tôi là ứng dụng nào? Tôi có được phép nhận token với quyền này không?”
2. **Client → Resource Server:** “Access token này có hợp lệ và đủ quyền để thực hiện thao tác đang yêu cầu không?”

Một client đã xác thực thành công tại token endpoint **chưa chắc** được cấp mọi scope. Một access token đã được cấp **chưa chắc** dùng được tại mọi Resource Server.

## 3. Yêu cầu token qua HTTP

### 3.1. Đăng ký client trước khi gọi

Thông thường quản trị viên hoặc quy trình cấp phát của Authorization Server sẽ đăng ký một client:

| Thuộc tính | Ví dụ | Ý nghĩa |
|---|---|---|
| Client ID | `order-scheduler` | Định danh công khai của OAuth client |
| Client authentication | `client_secret_basic` | Cách client chứng minh danh tính tại token endpoint |
| Client credential | Bí mật lưu trong secret manager | Thông tin bí mật chỉ backend và AS được phép biết |
| Allowed grant | `client_credentials` | Grant type được AS chấp nhận cho client |
| Allowed scope | `inventory.read` | Quyền tối đa có thể được cấp theo cấu hình |
| Target resource/audience | Inventory API (nếu AS hỗ trợ cấu hình này) | Giới hạn nơi access token được chấp nhận |

**Client ID không phải là secret.** Biết một client ID không đủ để tự nhận access token khi client authentication được cấu hình đúng.

### 3.2. Request chuẩn

Client gửi yêu cầu đến token endpoint bằng HTTP POST với body `application/x-www-form-urlencoded`.

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <encoded-client-credentials>

grant_type=client_credentials&scope=inventory.read
~~~

Trong ví dụ:

- `grant_type=client_credentials` chỉ định loại grant.
- `scope=inventory.read` yêu cầu quyền đọc tồn kho; đây là trường **tùy chọn** ở mức giao thức và các giá trị được hỗ trợ phụ thuộc Authorization Server.
- Header `Authorization: Basic ...` là cách xác thực client bằng `client_secret_basic`; dữ liệu được mã hóa theo quy tắc HTTP Basic, **không phải cơ chế mã hóa bảo mật thay thế TLS**.
- Token endpoint **phải sử dụng TLS/HTTPS** trong triển khai thực tế.

Một số AS hỗ trợ các hình thức xác thực client khác như `private_key_jwt` hoặc mutual TLS; khi đó request sẽ khác ví dụ trên. Grant type và cách client authentication là **hai lựa chọn riêng biệt**.

### 3.3. Response thành công

Authorization Server có thể trả về:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<opaque-or-jwt-access-token>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "inventory.read"
}
~~~

Các trường chính:

| Trường | Ý nghĩa |
|---|---|
| `access_token` | Giá trị client mang đến Resource Server để xin quyền truy cập |
| `token_type` | Loại token, thường là `Bearer` |
| `expires_in` | Thời gian hiệu lực tính bằng giây từ lúc phát hành, khi AS cung cấp |
| `scope` | Phạm vi thực tế được cấp; có thể bị thu hẹp so với yêu cầu |

Dữ liệu trên chỉ để minh họa. Access token có thể là **JWT** hoặc **opaque token**. Không có quy tắc chung bắt buộc access token là JWT hoặc luôn có cùng tập claim.

Theo RFC 6749, trong Client Credentials Grant, **refresh token thường không được phát hành và chuẩn khuyến nghị không kèm refresh token**. Khi access token hết hạn, client thường xác thực lại với Authorization Server để lấy token mới.

Đừng viết code phụ thuộc vào việc luôn nhận refresh token. Cũng không cần phát minh quy trình “làm mới” access token bằng cách thay đổi thời hạn ở phía client.

### 3.4. Dùng token để gọi API

~~~http
GET /api/inventory HTTP/1.1
Host: inventory.example.com
Authorization: Bearer <access_token>
~~~

Resource Server kiểm tra token bằng cơ chế được cấu hình: ví dụ kiểm tra chữ ký, issuer, audience và thời gian hiệu lực đối với JWT; hoặc introspection qua Authorization Server đối với token opaque. Sau khi xác định token hợp lệ, API vẫn cần kiểm tra scope/authority và quy tắc nghiệp vụ của endpoint.

Nếu token chỉ được cấp `inventory.read` thì không thể mặc nhiên cho phép thao tác cập nhật `inventory.write`.

## 4. “Danh tính ứng dụng” thực sự là gì?

Đây là điểm dễ gây hiểu nhầm nhất khi học Client Credentials Grant.

### 4.1. Client authentication xác nhận ứng dụng tại token endpoint

Khi Order Scheduler gửi yêu cầu token, Authorization Server cần xác minh client theo phương thức đã đăng ký, ví dụ kiểm tra client secret, chữ ký client assertion hoặc chứng chỉ.

Nếu thành công, AS biết yêu cầu đến từ client được định danh bởi client registration đã xác thực. Đây là **danh tính của OAuth client**, không phải danh tính người dùng cuối.

Mối quan hệ này có thể được mô tả như sau:

~~~text
client_id = order-scheduler
          |
          | xác thực client tại token endpoint
          v
Authorization Server
          |
          | cấp access token theo chính sách
          v
Inventory API nhận được token dành cho API
~~~

Có ba dữ kiện cần phân biệt:

1. **`client_id`:** định danh đăng ký của client với Authorization Server.
2. **Client credential:** bằng chứng client dùng để xác thực mình với Authorization Server.
3. **Access token:** bằng chứng ủy quyền mà Resource Server có thể kiểm tra, có thể chứa các claim liên quan đến client theo quy tắc phát hành của AS.

Không nên coi một chuỗi `client_id` tự khai trong HTTP request là bằng chứng đáng tin cậy. Resource Server phải dựa vào token hợp lệ và các claim/chính sách đã được kiểm tra.

### 4.2. Quyền của ứng dụng không phải quyền của một nhân viên

Ví dụ một access token được cấp cho Order Scheduler có quyền:

~~~text
inventory.read
shipment.create
~~~

Điều này có nghĩa AS cho phép **ứng dụng** thực hiện các thao tác đó trong phạm vi chính sách hiện hành. Nó **không nói rằng “nhân viên A đã chấp thuận đơn hàng 123”**.

Nếu nghiệp vụ cần kiểm tra người dùng nào đang thao tác, ví dụ chỉ chủ đơn mới được sửa đơn hàng, Client Credentials Grant đơn lẻ không mang theo ngữ cảnh xác thực và ủy quyền người dùng thích hợp. Khi đó nên chọn kiến trúc cho phép truyền ngữ cảnh người dùng hợp lệ, chẳng hạn Authorization Code cho ứng dụng có người dùng hoặc cơ chế token exchange/on-behalf-of được hệ thống hỗ trợ.

### 4.3. Nhận diện client từ claim trong access token

Một Authorization Server có thể phát hành JWT access token chứa dữ liệu minh họa như:

~~~json
{
  "iss": "https://auth.example.com",
  "aud": "inventory-api",
  "client_id": "order-scheduler",
  "scope": "inventory.read",
  "iat": 1760000000,
  "exp": 1760000300
}
~~~

Đây là **một khả năng triển khai**, không phải payload mà mọi OAuth 2.0 Server bắt buộc phải dùng. Đặc biệt:

- `client_id` có thể xuất hiện như claim, hoặc được biểu diễn bằng tên claim khác tùy chuẩn hồ sơ token và sản phẩm.
- `sub` nếu có có thể biểu diễn một service account, chính client hoặc chủ thể khác tùy chính sách issuer. Không suy luận rằng `sub` luôn là ID người dùng thực.
- `aud` thể hiện audience của token khi được cấp theo định dạng có hỗ trợ; Resource Server cần bảo đảm token thực sự được phát hành cho mình.
- `scope` thể hiện các quyền được cấp trong token, nhưng cách biến scope thành quyền thao tác phụ thuộc Resource Server.
- Với **opaque token**, Resource Server không thể tự đọc các claim theo kiểu giải mã JWT; nó phải dùng cơ chế xác minh thích hợp, ví dụ introspection.

Việc token được ký hợp lệ không đủ nếu issuer, audience hoặc quyền không phù hợp. Cũng không thể bảo đảm “ứng dụng nào gọi API” chỉ bằng cách tin một header tùy ý `X-Client-Id`.

### 4.4. OAuth client, service account và workload identity

Các khái niệm này liên quan nhưng không đồng nhất:

| Khái niệm | Giải thích |
|---|---|
| **OAuth client** | Thực thể đã đăng ký với AS để xin token, có `client_id` và phương thức xác thực |
| **Service account** | Tài khoản phi con người do một hệ thống quản lý danh tính tạo, có thể được ánh xạ với OAuth client |
| **Workload identity** | Danh tính của tiến trình/dịch vụ đang chạy, ví dụ theo nền tảng cloud hoặc cơ chế federation |
| **End-User identity** | Danh tính người dùng cuối đăng nhập tương tác, thường xử lý qua OIDC khi ứng dụng là RP |

Một hệ thống có thể dùng danh tính workload để xác thực OAuth client mà không lưu client secret dài hạn. Tuy nhiên, cách ánh xạ giữa những khái niệm trên là tính năng của Authorization Server/nền tảng, không phải bảo đảm tự động của `client_credentials`.

## 5. Client Credentials Grant khác Authorization Code và OIDC thế nào?

| Tiêu chí | Client Credentials | Authorization Code + OIDC |
|---|---|---|
| Chủ thể hoạt động | Ứng dụng/client | Người dùng cuối đăng nhập qua ứng dụng |
| Tương tác browser | Không | Thường có redirect browser trong web login |
| Authorization endpoint | Không dùng trong luồng này | Có |
| Token endpoint | Có | Có, để đổi authorization code lấy token |
| `redirect_uri` / code | Không | Có |
| `state` / `nonce` / PKCE | Không thuộc Client Credentials Grant | Dùng tùy cơ chế và yêu cầu của luồng tương ứng |
| Access token | Có | Thường có |
| OIDC ID token | Không phát hành như kết quả chuẩn của grant này | Có trong luồng OIDC |
| Câu hỏi giải quyết | “Ứng dụng có quyền gọi API nào?” | “Người dùng là ai?” và/hoặc “Ứng dụng được người dùng ủy quyền làm gì?” |
| Trường hợp điển hình | Job nền, máy chủ gọi máy chủ, automation | Web login, ứng dụng cần quyền truy cập tài nguyên của người dùng |

**OIDC không phải một dạng “Client Credentials nâng cao”.** OIDC bổ sung lớp xác thực End-User cho các luồng phù hợp. Không có End-User trong Client Credentials Grant, nên không có lý do mặc định yêu cầu scope `openid` hoặc kỳ vọng `id_token`.

Dù một Spring Boot application có tên “OIDC Client”, nó vẫn có thể đăng ký thêm một OAuth client riêng với grant `client_credentials` để giao tiếp máy chủ tới máy chủ.

## 6. Cấu hình Spring Boot OAuth 2.0 Client Credentials

Giả sử Order Scheduler chạy bằng Spring Boot, gọi Inventory API qua Authorization Server của doanh nghiệp. Ví dụ tập trung vào **Servlet/Spring Boot backend** hoặc tác vụ nền, không cần trang đăng nhập của người dùng.

### 6.1. Thêm dependency

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Starter này cung cấp các thành phần cấu hình client registration, quản lý authorized client và tương tác với token endpoint. Nó không tự biến ứng dụng thành một Resource Server.

### 6.2. Khai báo client registration

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-service:
            provider: internal-as
            client-id: ${INVENTORY_CLIENT_ID}
            client-secret: ${INVENTORY_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
        provider:
          internal-as:
            token-uri: https://auth.example.com/oauth2/token
~~~

Các trường quan trọng:

| Cấu hình | Vai trò |
|---|---|
| `registration.inventory-service` | Tên đăng ký để code Java chọn client |
| `provider: internal-as` | Liên kết registration với cấu hình Authorization Server |
| `client-id` và `client-secret` | Xác định và xác thực client với AS |
| `client-authentication-method` | Phương thức xác thực, ở đây là HTTP Basic |
| `authorization-grant-type` | Bắt buộc chọn `client_credentials` cho ví dụ |
| `scope` | Quyền client đề nghị AS cấp |
| `token-uri` | Endpoint để client trực tiếp xin access token |

Không khai báo `redirect-uri` hoặc `authorization-uri` vì luồng này không chuyển hướng người dùng. Với OAuth server không cung cấp OIDC discovery, cấu hình trực tiếp `token-uri` là đủ cho ví dụ Client Credentials.

Các biến môi trường `INVENTORY_CLIENT_ID` và `INVENTORY_CLIENT_SECRET` được cấp ở môi trường chạy; không đưa giá trị bí mật thật vào Git, ví dụ README, hoặc log. Tên miền `example.com` chỉ dùng làm địa chỉ minh họa.

### 6.3. Tạo `OAuth2AuthorizedClientManager` cho tác vụ nền

Trong Spring Security, thành phần `OAuth2AuthorizedClientManager` quản lý quá trình xin token và tái ủy quyền theo `ClientRegistration`.

Đối với tác vụ không chạy trong một HTTP request của người dùng, `AuthorizedClientServiceOAuth2AuthorizedClientManager` là lựa chọn phù hợp vì sử dụng `OAuth2AuthorizedClientService` để lưu/truy xuất authorized client.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class MachineToMachineOAuthConfig {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClientService) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        var manager =
                new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                        registrations,
                        authorizedClientService
                );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Code trên giả định dự án Spring Boot đã cấu hình OAuth 2.0 Client và có bean `OAuth2AuthorizedClientService` tương ứng. Trong cấu hình thông dụng, Spring Boot/Spring Security cung cấp implementation mặc định; với yêu cầu lưu trạng thái giữa nhiều instance hoặc sau khi khởi động lại, kiến trúc có thể cần một implementation phù hợp hơn.

Điểm đáng chú ý:

- `clientCredentials()` chỉ kích hoạt provider xử lý grant tương ứng.
- Manager sử dụng client registration để biết client ID, cách xác thực, token URI và scope.
- Authorized client chứa access token cùng thông tin đăng ký và ngữ cảnh principal; manager có thể tái sử dụng token còn hiệu lực rồi xin token mới khi cần.
- Việc có manager không tạo phiên đăng nhập người dùng. Không cần `oauth2Login()` để chạy job nền với `client_credentials`.

### 6.4. Lấy token và gọi Inventory API

Ví dụ sử dụng `RestClient` của Spring Framework 6.1+:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryGateway {

    private static final String REGISTRATION_ID = "inventory-service";
    private static final String WORKER_PRINCIPAL = "order-scheduler-worker";

    private final OAuth2AuthorizedClientManager clientManager;
    private final RestClient inventoryApi;

    public InventoryGateway(
            OAuth2AuthorizedClientManager clientManager,
            RestClient.Builder restClientBuilder) {

        this.clientManager = clientManager;
        this.inventoryApi = restClientBuilder
                .baseUrl("https://inventory.example.com")
                .build();
    }

    public String fetchInventory() {
        OAuth2AuthorizeRequest authorizationRequest =
                OAuth2AuthorizeRequest
                        .withClientRegistrationId(REGISTRATION_ID)
                        .principal(WORKER_PRINCIPAL)
                        .build();

        OAuth2AuthorizedClient authorizedClient =
                clientManager.authorize(authorizationRequest);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                    "No OAuth2 authorized client for inventory-service"
            );
        }

        String accessToken =
                authorizedClient.getAccessToken().getTokenValue();

        return inventoryApi.get()
                .uri("/api/inventory")
                .headers(headers -> headers.setBearerAuth(accessToken))
                .retrieve()
                .body(String.class);
    }
}
~~~

Giải thích luồng code:

1. `REGISTRATION_ID` trỏ tới `spring.security.oauth2.client.registration.inventory-service`.
2. `principal("order-scheduler-worker")` là **khóa định danh ổn định trong ngữ cảnh quản lý authorized client/token**. Nó **không tạo ra một người dùng đăng nhập** và không tự trở thành claim danh tính của token.
3. `clientManager.authorize(...)` tìm authorized client thích hợp, xin access token khi cần rồi trả về token để sử dụng.
4. `RestClient` gắn token vào header `Authorization: Bearer ...` khi gọi Inventory API.
5. Inventory API chịu trách nhiệm xác minh token và áp quyền `inventory.read` hoặc chính sách tương đương.

Ví dụ trả về chuỗi JSON để ngắn gọn. Trong ứng dụng thật nên định nghĩa kiểu response (DTO), xử lý lỗi mạng, timeout và các trường hợp token/quyền không hợp lệ.

**Vì sao dùng principal cố định?** Trong service-to-service grant, tên principal này là một phần khóa lưu token của authorized client. Dùng tên ngẫu nhiên mỗi lần gọi có thể gây nhiều lần xin token không cần thiết. Nếu ứng dụng có nhiều client registrations hoặc ngữ cảnh ủy quyền, cần chọn khóa tách biệt, ổn định và phù hợp với cách quản lý token.

### 6.5. Khi nào cấu hình `oauth2Client()` và `oauth2Login()`?

Trong web application dùng Spring Security Filter Chain, `oauth2Client()` bật các tích hợp OAuth 2.0 Client thích hợp cho môi trường servlet. `oauth2Login()` phục vụ đăng nhập người dùng qua redirect và có thể dẫn đến OIDC authentication.

Đối với một tác vụ nền chỉ cần `OAuth2AuthorizedClientManager` như ví dụ, **không cần bật đăng nhập OIDC**. Cách lấy token được điều phối bởi manager và client registration, không phụ thuộc vào browser hay cookie phiên đăng nhập.

Nếu cùng ứng dụng có cả trang web đăng nhập OIDC và job nền, hãy dùng **hai registration khác nhau khi khác grant, quyền hoặc danh tính ứng dụng**, chẳng hạn:

- `employee-login`: Authorization Code + OIDC cho nhân viên.
- `inventory-service`: Client Credentials cho job nền.

Thiết kế này giúp tránh dùng nhầm access token của người dùng cho công việc hệ thống, hoặc dùng token của ứng dụng cho hành động cần kiểm tra quyền của từng người.

## 7. Quản lý vòng đời access token

### 7.1. Không xin token mới trước mọi API call nếu vẫn còn hiệu lực

Token endpoint có giới hạn và độ trễ. Một worker chạy 1.000 lần/phút mà xin token cho từng request sẽ gây tải không cần thiết. `OAuth2AuthorizedClientManager` kết hợp `OAuth2AuthorizedClientService` giúp lưu và tái sử dụng authorized client theo registration/principal.

Một client manager thông thường theo dõi thời điểm hết hạn để quyết định khi nào cần xin token mới. Cần chú ý token có thể bị thu hồi sớm hoặc bị Resource Server từ chối do thay đổi quyền, cho dù thời gian hết hạn chưa tới.

Trong hệ thống nhiều instance, việc mỗi instance có token cache riêng đôi khi chấp nhận được. Nếu cần chia sẻ trạng thái hoặc hạn chế lượng request tại token endpoint, phải thiết kế thêm tầng lưu token, đồng bộ và xử lý đồng thời phù hợp, không lưu token ở nơi không có kiểm soát truy cập.

### 7.2. Khi nào xin token mới?

- Khi chưa có authorized client/access token phù hợp.
- Khi access token sắp hết hạn hoặc đã hết hạn theo tiêu chí của manager.
- Khi token bị thu hồi hoặc Resource Server trả lỗi cho thấy token hiện tại không còn hợp lệ, theo chiến lược xử lý lỗi đã thiết kế.

Thông thường Client Credentials Grant sẽ **lặp lại yêu cầu `grant_type=client_credentials`** để nhận token mới, không thực hiện một luồng refresh token giống như grant dành cho người dùng.

Không nên tự viết vòng lặp vô hạn khi nhận HTTP 401/403. Nếu lỗi do credential sai, scope không được cấp hoặc audience không đúng, xin lại cùng một token không giải quyết nguyên nhân.

### 7.3. Phân biệt lỗi từ Authorization Server và Resource Server

| Giai đoạn | Dấu hiệu thường gặp | Hướng xử lý |
|---|---|---|
| Xin token | `invalid_client` | Kiểm tra client ID, secret, phương thức xác thực, trạng thái client |
| Xin token | `unauthorized_client` | Grant type hoặc thao tác chưa được cho phép cho client |
| Xin token | `invalid_scope` | Scope sai tên hoặc ngoài quyền client được cấp |
| Gọi API | HTTP 401 / `invalid_token` | Token thiếu, hết hạn, bị thu hồi, issuer/audience không phù hợp hoặc không được chấp nhận |
| Gọi API | HTTP 403 / `insufficient_scope` hoặc lỗi quyền nghiệp vụ | Token có thể hợp lệ nhưng thiếu quyền hoặc không đạt chính sách API |
| Gọi token/API | Timeout, 429, 5xx | Theo dõi, giới hạn retry, backoff và circuit breaker tùy môi trường |

Thông điệp lỗi và HTTP status thực tế phụ thuộc sản phẩm AS/RS và cách triển khai. Khi xử lý sự cố, cần phân biệt **token không xin được**, **token bị từ chối**, và **token hợp lệ nhưng không đủ quyền**.

## 8. Thiết kế bảo mật cho danh tính ứng dụng

### 8.1. Xác thực client bằng cách nào?

| Cách xác thực | Đặc điểm | Lưu ý |
|---|---|---|
| `client_secret_basic` | Gửi client secret qua HTTP Basic tới token endpoint | Phổ biến, dễ tích hợp; bảo vệ secret và bắt buộc HTTPS |
| `client_secret_post` | Đặt client ID/secret trong body token request | Chỉ dùng khi có lý do tương thích và được AS hỗ trợ; tránh log body |
| `private_key_jwt` | Client ký assertion bằng khóa riêng; AS xác minh bằng khóa công khai | Phù hợp khi có hạ tầng quản lý khóa, cần kiểm tra thời hạn/đối tượng của assertion |
| Mutual TLS client authentication | Client chứng minh danh tính bằng chứng chỉ TLS | Cần quản lý certificate và khả năng hỗ trợ của AS |
| Workload identity federation | Dùng bằng chứng danh tính từ nền tảng chạy để thiết lập quyền xin token | Cơ chế cụ thể tùy hệ thống và AS; giúp giảm phụ thuộc vào shared secret dài hạn khi được hỗ trợ |

**Grant type** `client_credentials` mô tả *vì sao client xin token*. **Client authentication method** mô tả *client chứng minh danh tính thế nào*. Không nhầm lẫn hai khái niệm này.

### 8.2. Nguyên tắc quyền tối thiểu

- Mỗi dịch vụ/tác vụ nên có client registration riêng khi trách nhiệm và quyền khác nhau.
- Chỉ cấp scope cần thiết, ví dụ `inventory.read` cho tác vụ chỉ xem tồn kho.
- Hạn chế audience/resource đích để token không dùng tùy tiện ở API khác.
- Dùng thời gian sống token phù hợp và cơ chế thu hồi/rotation theo chính sách.
- Resource Server kiểm tra issuer, audience, thời gian hiệu lực và quyền, không chỉ kiểm tra “token có tồn tại”.
- Áp quyền nghiệp vụ ở Resource Server. Ví dụ quyền `inventory.read` không mặc nhiên cho phép đọc mọi kho hoặc mọi tenant.

### 8.3. Bảo vệ client secret và access token

Client secret và access token đều là thông tin nhạy cảm, nhưng chúng có vai trò khác nhau. Nếu lộ client secret, kẻ tấn công có thể tự xin token mới cho đến khi credential bị thu hồi hoặc thay đổi. Nếu lộ bearer access token, bên khác có thể sử dụng token đó trong thời gian và phạm vi nó được chấp nhận.

Biện pháp thực tế:

1. Dùng secret manager hoặc cơ chế secret injection của môi trường triển khai.
2. Không commit credential vào repository, file cấu hình công khai hoặc Docker image.
3. Không ghi credential/token đầy đủ vào log, lỗi exception, trace, analytics hay response cho browser.
4. Chỉ gọi token endpoint/API qua HTTPS hợp lệ.
5. Định kỳ xoay vòng credential theo khả năng của AS và quy trình triển khai.
6. Giới hạn quyền truy cập secret cho đúng workload; tránh chia sẻ một client secret cho nhiều hệ thống độc lập.
7. Kiểm soát khả năng lộ access token trong memory dump, diagnostic hoặc hệ thống quan sát.

### 8.4. Bearer token không chứng minh chính xác tiến trình nào đang giữ nó

Với bearer token thông thường, Resource Server cho phép bất kỳ bên nào sở hữu token hợp lệ trong phạm vi được chấp nhận sử dụng token; nó không tự chứng minh rằng request hiện tại thật sự đến từ cùng tiến trình đã xin token. Vì vậy, khái niệm “danh tính của ứng dụng” ở Resource Server **có giới hạn bởi cơ chế xác thực token**.

Các cơ chế token ràng buộc với bên sở hữu khóa/chứng chỉ (sender-constrained token), nếu AS và RS cùng hỗ trợ, có thể giảm nguy cơ dùng lại token bị đánh cắp. Tuy nhiên, đây là thiết kế bổ sung, không tự xuất hiện chỉ vì dùng `client_credentials`.

## 9. Các tình huống chọn grant

### Tình huống A — Job tổng hợp dữ liệu đêm

Một tiến trình Spring Boot chạy theo lịch, lấy dữ liệu từ Reporting API. Không có người dùng đang đăng nhập. Client Credentials Grant là lựa chọn tự nhiên nếu AS và API cấp quyền trực tiếp cho ứng dụng.

**Danh tính có ý nghĩa:** tiến trình/reporting client.

### Tình huống B — Người dùng bấm “Xuất báo cáo cá nhân”

Web app cần tải dữ liệu thuộc quyền riêng của người dùng. Nếu API phải biết ai đã yêu cầu và đánh giá quyền của người đó, chỉ dùng token Client Credentials của web app sẽ làm mất ngữ cảnh người dùng.

**Cân nhắc:** Authorization Code có đăng nhập người dùng, token dành cho API, hoặc một cơ chế delegation/token exchange được thiết kế và hỗ trợ đúng cách.

### Tình huống C — API gọi API khác

Billing API nhận request từ frontend rồi gọi Tax API. Nếu lời gọi sang Tax API là thao tác hệ thống độc lập với người dùng, Billing API có thể dùng Client Credentials. Nếu Tax API phải phân quyền dựa trên người dùng đang yêu cầu, cần một cơ chế chuyển ngữ cảnh ủy quyền phù hợp.

**Không mặc định:** “Backend gọi backend” lúc nào cũng phải dùng Client Credentials; hãy xác định quyền đang thuộc ứng dụng hay thuộc người dùng.

### Tình huống D — Multi-tenant SaaS

Một client có quyền `orders.read` không đồng nghĩa có quyền đọc đơn hàng của mọi tenant. Nếu quyền bị giới hạn theo tenant, AS/RS cần cơ chế thể hiện và xác minh ràng buộc tenant; ứng dụng không được chỉ dựa vào scope chung rồi chấp nhận tenant ID tùy ý trong URL.

## 10. Sai lầm thường gặp

**“Có client ID là đủ để xin access token.”**  
Không. Client Credentials Grant yêu cầu client authentication theo cách mà AS chấp nhận. `client_id` chỉ là định danh, không phải bằng chứng sở hữu credential.

**“Client Credentials trả về ID token để biết ứng dụng là ai.”**  
Không. Kết quả chuẩn là access token dùng cho quyền truy cập tài nguyên. ID token thuộc chức năng OIDC xác thực người dùng cuối và không phải phần mặc định của Client Credentials Grant.

**“Trong JWT có `sub`, vậy `sub` chắc chắn là người dùng.”**  
Không. Ý nghĩa `sub` phụ thuộc định dạng token và issuer. Trong machine-to-machine flow, nó có thể là service account hoặc một chủ thể phi con người.

**“Access token là JWT hợp lệ thì gọi API nào cũng được.”**  
Không. API phải kiểm tra audience/resource, issuer, thời hạn và chính sách phân quyền. Token phát cho Inventory API không mặc nhiên dùng được cho Payment API.

**“Ứng dụng backend nên dùng token của tài khoản quản trị viên.”**  
Không nên biến tác vụ máy chủ thành hoạt động của người dùng giả. Hãy đăng ký danh tính ứng dụng phù hợp và chỉ cấp đúng quyền công việc cần.

**“Mỗi lần gọi API đều tự POST xin token mới.”**  
Không cần thiết. Manager có thể quản lý và tái sử dụng token còn hiệu lực; lặp lại token request không kiểm soát gây tải cho AS.

**“Đã gọi `oauth2Login()` thì Client Credentials tự chạy.”**  
Không. `oauth2Login()` xử lý đăng nhập tương tác. Machine-to-machine grant cần registration `client_credentials` và logic OAuth client/authorized client thích hợp.

## 11. Bài tập tư duy

Xét hệ thống gồm ba dịch vụ:

- **Invoice Worker** tạo hóa đơn định kỳ, dùng client ID `invoice-worker`.
- **Authorization Server** xác thực Invoice Worker và cấp token có scope `invoice.create`, audience hướng đến Invoice API.
- **Invoice API** bảo vệ endpoint `POST /invoices`.

**Câu 1: Ai là Resource Server?**  
Invoice API, vì nó nhận access token để quyết định cho phép tạo hóa đơn.

**Câu 2: Việc token có scope `invoice.create` chứng minh nhân viên nào đã tạo hóa đơn?**  
Không. Nó thể hiện quyền được cấp cho client trong machine-to-machine flow. Nếu cần ghi nhận người dùng, nghiệp vụ phải bổ sung mô hình danh tính người dùng và nguồn bằng chứng phù hợp.

**Câu 3: Worker chạy qua đêm, token hết hạn sau 5 phút. Có cần refresh token?**  
Không nhất thiết. Client có thể xác thực lại bằng grant `client_credentials` để lấy access token mới; Spring Security có thể điều phối việc này.

**Câu 4: Vì sao Invoice API không nên tin header `X-Client-Id: invoice-worker` do phía gọi tự gửi?**  
Vì bất kỳ client nào cũng có thể tự đặt header đó. API phải xác minh access token và claim/chính sách được cấp bởi Authorization Server tin cậy.

**Câu 5: Nếu Worker cần đồng thời gọi Payment API với quyền khác, nên làm gì?**  
Xác định scope/audience/registration và chính sách phù hợp của Payment API, có thể sử dụng một client registration riêng với quyền tối thiểu. Không giả định token của Invoice API cũng được Payment API chấp nhận.

## Ghi nhớ

**Client Credentials Grant** là cơ chế OAuth 2.0 để một ứng dụng backend xác thực danh tính client với Authorization Server và xin access token phục vụ truy cập API trong phạm vi được cấp. Không có đăng nhập người dùng cuối và không có ID token OIDC trong luồng chuẩn. Spring Security hỗ trợ cơ chế này thông qua `ClientRegistration`, `OAuth2AuthorizedClientManager` và provider `clientCredentials()`; ứng dụng vẫn phải bảo vệ credential, quản lý token và để Resource Server kiểm tra đầy đủ quyền truy cập.
