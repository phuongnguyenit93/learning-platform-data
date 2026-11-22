# Thiết lập iss, sub, aud, iat, exp, nbf, jti và scope

## 1. Mục tiêu và bối cảnh

Trong chương **Token và claims** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, bài học này tập trung vào cách thiết kế các claim quan trọng trong JWT do OAuth 2.0/OpenID Connect Authorization Server phát hành. Đây là một phần của việc **thiết kế, cấu hình, bảo mật, kiểm thử và vận hành Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot**.

Một JWT Access Token có thể được ký hợp lệ nhưng vẫn không phù hợp để gọi một API cụ thể. Ví dụ token được phát hành bởi issuer tin cậy, còn hạn, nhưng có audience dành cho Billing API trong khi request đang tới Orders API. Nếu Orders API chỉ kiểm tra chữ ký và thời hạn, token có thể bị chấp nhận sai mục tiêu. Tương tự, một token có scope rộng hơn quyền đã cấp có thể tạo ra rủi ro leo thang đặc quyền.

Các claim được học trong bài:

- **iss**: issuer đã phát hành token.
- **sub**: subject mà token đại diện.
- **aud**: audience hoặc bên nhận token.
- **iat**: thời điểm token được phát hành.
- **exp**: thời điểm token hết hạn.
- **nbf**: thời điểm token bắt đầu có hiệu lực, nếu được sử dụng.
- **jti**: định danh của token.
- **scope**: các quyền được cấp cho Access Token.

Sau bài này, bạn có thể giải thích ý nghĩa từng claim, phân biệt claim của Access Token với ID Token, cấu hình chúng qua **OAuth2TokenCustomizer<JwtEncodingContext>**, xác minh ở Resource Server và kiểm thử token thực tế thay vì chỉ kiểm tra cấu hình.

## 2. JWT claims và ranh giới giữa Access Token với opaque token

JWT là một định dạng token có thể mang claims trong payload được mã hóa Base64URL rồi ký. Với **self-contained JWT Access Token**, Resource Server có thể xác minh chữ ký và kiểm tra claims mà không cần hỏi Authorization Server ở mỗi request, nếu kiến trúc chấp nhận mô hình xác minh offline.

Với **opaque Access Token**, client chỉ nhận một chuỗi không mang payload JWT để tự đọc. Resource Server thường xác minh token qua introspection hoặc cơ chế tra cứu trạng thái. Các claim nội bộ vẫn có thể tồn tại trong authorization store, nhưng không nhất thiết xuất hiện trong một JWT mà Resource Server tự giải mã.

| Đặc điểm | JWT Access Token | Opaque Access Token |
| --- | --- | --- |
| Nội dung | Có header và payload claims được mã hóa Base64URL, sau đó ký | Chuỗi không công khai cấu trúc claims |
| Kiểm tra | Chữ ký, issuer, audience, thời gian, scope và policy | Introspection hoặc cơ chế xác minh trạng thái |
| Claims | Có thể quan sát trong payload; **không được coi là bí mật** | Không thể tự đọc payload từ token |
| Thu hồi | Có giới hạn nếu Resource Server chỉ xác minh JWT offline | Có thể phản ánh trạng thái qua introspection, tùy cache/policy |
| Tùy chỉnh trong Spring | OAuth2TokenCustomizer<JwtEncodingContext> cho JWT | Dùng cơ chế claims/context phù hợp với opaque token và phiên bản |

**Bài này tập trung vào JWT Access Token.** Không được mặc định rằng việc thêm claim vào JwtEncodingContext cũng làm opaque token có cùng payload hoặc thay đổi ID Token theo cách giống Access Token.

## 3. Bảng tổng quan các claim

| Claim | Ý nghĩa | Dạng dữ liệu JWT | Kiểm tra chính |
| --- | --- | --- | --- |
| iss | Issuer | String | Phải khớp issuer được Resource Server tin cậy |
| sub | Subject | String | Phải đại diện đúng user/workload theo hợp đồng |
| aud | Audience | String hoặc mảng String | Phải chứa định danh Resource Server đang nhận token |
| iat | Issued At | NumericDate | Không được nằm quá xa trong tương lai; hỗ trợ đánh giá tuổi token |
| exp | Expiration Time | NumericDate | Token không còn hợp lệ tại hoặc sau thời điểm hết hạn |
| nbf | Not Before | NumericDate, tùy chọn | Token không hợp lệ trước thời điểm này |
| jti | JWT ID | String | Định danh token; cần state store nếu dùng cho revocation/deduplication |
| scope | Quyền OAuth2 được cấp | Thường là chuỗi scope phân cách bằng dấu cách theo JWT Access Token Profile | Chỉ cấp quyền đã được phê duyệt; API kiểm tra quyền phù hợp |

Các claim iss, sub, aud, exp, nbf, iat và jti là **registered claims** trong RFC 7519. RFC 7519 định nghĩa ý nghĩa và kiểu dữ liệu, nhưng không bắt buộc mọi JWT đều phải có tất cả claim trong mọi use case. Khi phát hành JWT Access Token theo **RFC 9068**, các claim iss, exp, aud, sub, client_id, iat và jti là thành phần bắt buộc của profile. Scope là claim OAuth2 của Access Token, không phải registered claim cốt lõi của JWT.

**Không nên chỉ nhìn tên claim.** Resource Server cần xác minh cả nguồn phát hành, chữ ký, thời hạn, audience, loại token và quyền; một JWT có đủ tám trường nhưng sai audience vẫn phải bị từ chối.

## 4. iss — Issuer của token

Iss xác định **Authorization Server nào đã phát hành token**. Giá trị thường là URI công khai, ổn định, ví dụ:

~~~text
https://auth.example.com
~~~

Issuer được cấu hình trong AuthorizationServerSettings. Với Spring Authorization Server:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Configuration(proxyBeanMethods = false)
class AuthorizationServerSettingsConfiguration {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .issuer("https://auth.example.com")
                .build();
    }
}
~~~

JWT generator của Spring Authorization Server sử dụng issuer context để đưa issuer vào token. Trong cấu hình chuẩn, nên để framework tạo claim này từ AuthorizationServerSettings; chỉ override trong customizer khi có lý do rõ ràng và bảo đảm giá trị thống nhất với metadata discovery, JWKS và cấu hình Resource Server.

### 4.1. Những lỗi thường gặp với issuer

- Token dùng https://auth.example.com, nhưng Resource Server cấu hình tin https://auth-staging.example.com.
- Reverse proxy công bố hostname khác với issuer được ký trong JWT.
- Dev và production dùng chung issuer nhưng lại dùng key hoặc registry không tách biệt.
- Một Resource Server chấp nhận issuer bất kỳ lấy từ token thay vì dùng cấu hình tin cậy.
- Issuer bị thay đổi sau khi phát hành token nhưng client/API chưa được cập nhật.

Issuer là một **định danh chính xác**, không nên so sánh bằng chuỗi con hoặc wildcard hostname. Khi đổi issuer, cần xem đó là thay đổi trust boundary: metadata, JWKS, token đang còn hạn, Resource Server và các client liên quan đều cần kế hoạch chuyển đổi.

## 5. sub — Subject mà token đại diện

Sub xác định chủ thể gắn với token, thường là người dùng đã xác thực. Ví dụ:

~~~json
{
  "sub": "user-8f2a91"
}
~~~

Sub cần ổn định theo hợp đồng định danh mà Resource Server sử dụng. Không nên dùng email hoặc username có thể thay đổi làm định danh lâu dài nếu hệ thống cần liên kết quyền, audit hoặc dữ liệu theo vòng đời tài khoản.

Trong Spring Authorization Server, subject mặc định thường lấy từ principal của context khi tạo JWT. Cần xác minh Authentication nào đang được dùng trong từng grant:

- **Authorization Code:** thường đại diện người dùng đã đăng nhập.
- **Client Credentials:** token đại diện workload/client; không nên giả định có end-user.
- **Token Exchange:** subject cần phản ánh token nguồn và chính sách impersonation/delegation; không được tự gán subject theo tham số không đáng tin.

### 5.1. Bảo vệ quyền riêng tư của subject

Không đưa các dữ liệu sau vào sub nếu không có lý do nghiệp vụ và đánh giá riêng:

- Email, số điện thoại hoặc địa chỉ.
- Mã nhân sự hoặc định danh nhạy cảm dùng trên nhiều hệ thống.
- Tên đầy đủ hoặc thông tin cá nhân có thể nhận diện trực tiếp.

Có thể sử dụng định danh nội bộ khó đoán hoặc pairwise subject identifier theo từng client/resource domain khi cần giảm khả năng liên kết người dùng giữa các hệ thống. Quan trọng là Resource Server phải có cách ánh xạ định danh này tới dữ liệu nghiệp vụ được phép.

**Không nhầm sub với client_id.** Sub nói token đại diện ai; client_id nói ứng dụng nào đã yêu cầu token. Trong JWT Access Token Profile, hai thông tin này có vai trò riêng.

## 6. aud — Audience của token

Aud cho biết **token được phát hành cho bên nhận nào**. Với Access Token, audience thường là định danh của Resource Server/API, ví dụ:

~~~json
{
  "aud": ["orders-api"]
}
~~~

Một token dành cho orders-api không được chấp nhận ở billing-api chỉ vì cả hai cùng tin một issuer. Resource Server phải kiểm tra audience của token có chứa định danh của chính nó hay không.

### 6.1. Access Token và ID Token có audience khác nhau

| Loại token | Audience thường đại diện | Bên kiểm tra |
| --- | --- | --- |
| JWT Access Token | Resource Server/API nhận quyền truy cập | Resource Server |
| OIDC ID Token | OIDC Client đã yêu cầu đăng nhập | OIDC Client |

Đây là khác biệt quan trọng. Không áp dụng audience của ID Token (client ID) như thể đó là audience của Access Token. Cũng không dùng ID Token để gọi API thay Access Token.

### 6.2. Không lấy audience tùy ý từ request

Client có thể gửi resource hoặc audience trong những flow hỗ trợ resource indicator/token exchange, nhưng **giá trị đó là yêu cầu**, không phải quyết định cuối cùng. Authorization Server phải xác minh client, subject, scope và resource policy trước khi đặt audience vào token.

Ví dụ policy nội bộ:

| Client | Audience được phép |
| --- | --- |
| orders-bff | orders-api |
| billing-bff | billing-api |
| reporting-service | reports-api |

Không dùng quy tắc lấy audience từ request rồi ký token. Với một client gọi nhiều API, nên có mapping server-side đã được duyệt giữa client, grant, resource và scope.

### 6.3. Cấu hình audience trong JwtEncodingContext

Ví dụ dưới đây tùy chỉnh audience của **Access Token JWT** theo mapping tĩnh phía server:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Configuration(proxyBeanMethods = false)
class AccessTokenAudienceConfiguration {

    @Bean
    OAuth2TokenCustomizer<JwtEncodingContext> accessTokenAudienceCustomizer() {
        return context -> {
            if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
                return;
            }

            String clientId = context.getRegisteredClient().getClientId();
            List<String> audiences = switch (clientId) {
                case "orders-bff" -> List.of("orders-api");
                case "billing-bff" -> List.of("billing-api");
                default -> throw new IllegalStateException(
                        "No approved audience mapping for client");
            };

            context.getClaims().audience(audiences);
        };
    }
}
~~~

Đây là **ví dụ minh họa mapping**; production có thể dùng policy repository nhưng phải giữ nguyên nguyên tắc allowlist. Nếu một client được phép gọi nhiều API, chỉ thêm audience khi authorization và resource policy cho phép. Không dùng client_id làm audience thay cho API một cách máy móc.

**Lưu ý về mặc định:** bộ claim mặc định được tạo bởi JWT generator có thể phụ thuộc phiên bản và ngữ cảnh token. Hãy giải mã một Access Token test để xác nhận aud thực tế, sau đó cấu hình rõ audience mà Resource Server yêu cầu. Không suy đoán chỉ từ tên client hoặc từ một ví dụ tài liệu khác phiên bản.

## 7. iat — Thời điểm phát hành

Iat (Issued At) biểu diễn thời điểm token được tạo, dùng kiểu **NumericDate** theo RFC 7519. Khi serialize JWT, NumericDate là số giây tính từ Unix epoch (có thể có phần thập phân); thư viện thường xử lý chuyển đổi từ Instant.

Ví dụ payload:

~~~json
{
  "iat": 1794823200
}
~~~

Iat giúp:

- Xác định tuổi của token.
- Hỗ trợ kiểm tra token được tạo quá xa trong tương lai.
- Phục vụ điều tra, correlation và chính sách thu hồi theo thời điểm.
- Hỗ trợ phân tích thời gian phát hành so với thời gian sự cố.

Không nên dùng iat như bằng chứng duy nhất rằng token hợp lệ. Kẻ tấn công có thể tự tạo payload với iat hợp lý nhưng không có chữ ký hợp lệ; Resource Server vẫn phải xác minh chữ ký và issuer.

## 8. exp — Thời điểm hết hạn

Exp (Expiration Time) xác định thời điểm token **không còn được chấp nhận**. Theo RFC 7519, token không được chấp nhận tại hoặc sau thời điểm hết hạn, có thể có một khoảng clock skew nhỏ được policy cho phép để xử lý chênh lệch đồng hồ.

Ví dụ:

~~~json
{
  "iat": 1794823200,
  "exp": 1794823800
}
~~~

Token có khoảng sống danh nghĩa 600 giây. Thời hạn thực tế cần được đặt theo rủi ro, loại client, scope, audience và yêu cầu vận hành.

### 8.1. Cấu hình Access Token TTL

Spring Authorization Server cấu hình thời hạn Access Token trong TokenSettings của RegisteredClient:

~~~java
import java.time.Duration;

import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(10))
        .build();
~~~

TTL được JWT generator sử dụng để tạo exp tương ứng khi phát hành token. **Không nhầm** accessTokenTimeToLive với thời hạn Authorization Code, Refresh Token hoặc Device Code; chúng là các chính sách riêng.

### 8.2. Quan hệ giữa iat và exp

Với một token mới phát hành:

~~~text
iat = thời điểm phát hành
exp = iat + accessTokenTimeToLive
exp > iat
~~~

Không đặt exp quá xa chỉ để giảm số lần client refresh. Access Token sống lâu làm tăng rủi ro khai thác nếu token bị đánh cắp. Nếu client cần duy trì phiên lâu hơn, hãy xem xét Refresh Token theo chính sách grant/client phù hợp thay vì kéo dài Access Token thiếu kiểm soát.

### 8.3. Clock skew và đồng bộ thời gian

Các node Authorization Server và Resource Server cần đồng bộ thời gian. Nếu clock lệch lớn, token vừa phát hành có thể bị coi là chưa hợp lệ hoặc đã hết hạn. Chỉ cho phép clock skew nhỏ theo policy; không mở rộng sai lệch hàng phút/hàng giờ để che lỗi NTP.

## 9. nbf — Thời điểm bắt đầu có hiệu lực

Nbf (Not Before) là claim tùy chọn. Nếu được đặt, token không được chấp nhận **trước** thời điểm này. Ví dụ:

~~~json
{
  "nbf": 1794823200,
  "exp": 1794826800
}
~~~

Nbf có thể hữu ích khi token được tạo trước thời điểm một quyền bắt đầu có hiệu lực, hoặc khi hệ thống có một lịch phát hành cụ thể. Với Access Token thông thường, thường không cần thêm nbf nếu token có hiệu lực ngay tại thời điểm phát hành.

### 9.1. Khi nào nên đặt nbf?

- Token được phát hành trước thời điểm bắt đầu một phiên làm việc đã lên lịch.
- Một luồng nghiệp vụ yêu cầu thời điểm kích hoạt cụ thể.
- Hệ thống có chính sách rõ ràng về hiệu lực trong tương lai và Resource Server xử lý đồng hồ nhất quán.

Không dùng nbf để thay thế exp, không đặt nbf sau exp, và không tùy tiện đặt nbf trong tương lai để “tạo độ trễ an toàn”. Nếu client nhận token trước nbf, API sẽ từ chối token cho đến khi đạt thời điểm này.

### 9.2. Ví dụ thêm nbf có chủ đích

Nếu nghiệp vụ thực sự cần, có thể thêm nbf trong customizer cho Access Token:

~~~java
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Configuration(proxyBeanMethods = false)
class NotBeforeClaimConfiguration {

    @Bean
    OAuth2TokenCustomizer<JwtEncodingContext> notBeforeCustomizer(Clock tokenClock) {
        return context -> {
            if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
                context.getClaims().notBefore(tokenClock.instant());
            }
        };
    }
}
~~~

Bean Clock cần được cung cấp bởi ứng dụng, ví dụ Clock.systemUTC(). Trong ứng dụng thật, chỉ đặt nbf nếu có yêu cầu; nếu chỉ muốn token có hiệu lực ngay, không cần thêm claim này. Nếu có nhiều OAuth2TokenCustomizer<JwtEncodingContext>, cần hợp nhất chúng có chủ đích để tránh bean customizer ghi đè hoặc thay thế logic của nhau.

## 10. jti — Định danh duy nhất của token

Jti (JWT ID) là định danh của một JWT cụ thể. Ví dụ:

~~~json
{
  "jti": "6f6c7d18-4baf-4e93-92a4-8e71d54b1d3c"
}
~~~

Hai token khác nhau nên có jti khác nhau, kể cả khi cùng sub, aud, scope và thời hạn gần nhau. Jti hữu ích cho:

- Liên kết token với sự kiện audit.
- Danh sách denylist/revocation nếu hệ thống có lưu trạng thái.
- Phân tích token bị lộ hoặc sử dụng bất thường.
- Phát hiện trùng lặp trong các quy trình cần định danh token.

**Jti không tự tạo ra cơ chế chống replay.** Nếu Resource Server chỉ kiểm tra chữ ký và thời hạn, nó không tự biết một jti đã được dùng trước đó hay đã bị thu hồi. Muốn chặn một token cụ thể, cần state store, introspection, denylist hoặc cơ chế khác được kiểm tra ở mỗi request theo mức độ yêu cầu.

JWT generator mặc định của Spring Authorization Server thường tạo jti cho JWT. Không cần tự ghi đè nếu không có yêu cầu cụ thể. Nếu custom generator tạo jti, phải dùng nguồn ngẫu nhiên an toàn và tránh tái sử dụng giá trị.

## 11. scope — Quyền được cấp trong Access Token

Scope biểu diễn các quyền OAuth2 được cấp cho token. Ví dụ:

~~~json
{
  "scope": "orders.read profile"
}
~~~

Scope phải phản ánh **quyền đã được Authorization Server chấp thuận**, không phải toàn bộ scope client gửi trong authorization request. Khi người dùng chỉ đồng ý orders.read, không được phát token có thêm orders.write.

Theo JWT Access Token Profile RFC 9068, nếu claim scope được đưa vào JWT Access Token thì nó có dạng **chuỗi các scope phân cách bằng dấu cách**. Một số converter/framework có thể chấp nhận collection trong các ngữ cảnh khác; khi áp dụng profile JWT Access Token, hãy xác nhận dạng serialize đúng với hợp đồng của Resource Server.

### 11.1. Phân biệt requested scopes và authorized scopes

| Tập scope | Nguồn | Ý nghĩa |
| --- | --- | --- |
| Requested scopes | Client yêu cầu | Mong muốn của client, chưa phải quyền đã cấp |
| Registered client scopes | RegisteredClient | Giới hạn scope client có thể yêu cầu |
| Authorized scopes | Authorization Server sau khi xét policy/consent | Quyền được chấp thuận cho authorization/token |
| Token scope claim | Claims của Access Token | Quyền Resource Server có thể dùng để authorize request |

Trong customizer, ưu tiên context.getAuthorizedScopes() thay vì tự parse scope từ raw HTTP request. Việc scope xuất hiện trong token không thay thế kiểm tra quyền trên tài nguyên cụ thể; API vẫn cần kiểm tra ownership, tenant, trạng thái dữ liệu và policy nghiệp vụ.

### 11.2. Scope không phải audience

- aud=orders-api: token dành cho Orders API.
- scope=orders.read: token cho phép hành động đọc đơn hàng theo policy.

Một token có orders.read nhưng audience là billing-api **không được dùng ở Orders API**. Ngược lại, audience đúng nhưng scope thiếu orders.read cũng phải bị từ chối.

## 12. Phân biệt claims của Access Token và ID Token

Một hệ thống OIDC có thể phát cả JWT Access Token và ID Token. Hai loại token có một số claim trùng tên nhưng ngữ nghĩa khác nhau.

| Claim | JWT Access Token | OIDC ID Token |
| --- | --- | --- |
| iss | Issuer của Authorization Server | Issuer của OpenID Provider |
| sub | Subject mà API/token policy cần nhận diện | Định danh end-user trong OIDC |
| aud | Resource Server/API nhận token | OIDC Client phải xác minh ID Token |
| iat | Thời điểm phát hành Access Token | Thời điểm phát hành ID Token |
| exp | Hạn dùng Access Token | Hạn dùng ID Token |
| nbf | Có thể có, tùy policy | Không phải claim luôn xuất hiện |
| jti | Định danh Access Token | Có thể có tùy generator/profile |
| scope | Quyền OAuth2 được cấp, theo profile | Không phải claim thay thế scope của Access Token |
| nonce | Không dùng như claim thay thế ở Access Token | Ràng buộc ID Token với OIDC request khi được yêu cầu |

**Không áp dụng một customizer chung thiếu điều kiện cho mọi token type.** Nếu customizer Access Token thay aud thành orders-api, không được vô tình làm ID Token có audience orders-api; ID Token phải có audience của client OIDC theo quy tắc OIDC.

## 13. Pipeline tạo JWT trong Spring Authorization Server

~~~mermaid
flowchart TD
    A["Token Endpoint / Authorization flow"] --> B["OAuth2TokenContext"]
    B --> C["JwtGenerator"]
    C --> D["Tạo claims chuẩn: iss, sub, aud, iat, exp, jti..."]
    D --> E["OAuth2TokenCustomizer<JwtEncodingContext>"]
    E --> F["JwsEncoder / JwtEncoder ký JWT"]
    F --> G["OAuth2AuthorizationService lưu authorization/token"]
    G --> H["Token response"]
~~~

Các claim chuẩn có thể được generator khởi tạo dựa trên AuthorizationServerContext, principal, RegisteredClient, authorized scopes và TokenSettings. Customizer cho phép **bổ sung hoặc thay đổi claims trước khi ký**. Việc một claim có giá trị mặc định cụ thể cần được xác nhận trên đúng phiên bản và loại token.

### 13.1. Điểm mở rộng OAuth2TokenCustomizer<JwtEncodingContext>

Ví dụ tối thiểu chỉ thêm claim cho Access Token:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Configuration(proxyBeanMethods = false)
class AccessTokenClaimsConfiguration {

    @Bean
    OAuth2TokenCustomizer<JwtEncodingContext> accessTokenCustomizer() {
        return context -> {
            if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
                return;
            }

            context.getClaims().claims(claims -> {
                claims.put("client_id", context.getRegisteredClient().getClientId());
                claims.put("scope", String.join(" ", context.getAuthorizedScopes()));
            });
        };
    }
}
~~~

Ví dụ trên:

- Chỉ áp dụng cho OAuth2TokenType.ACCESS_TOKEN, không sửa ID Token.
- Dùng getRegisteredClient() để lấy client đã được server xác định.
- Dùng getAuthorizedScopes() để lấy quyền đã được chấp thuận.
- Đưa scope thành chuỗi phân cách bằng dấu cách theo JWT Access Token Profile.
- Đưa client_id để phân biệt client yêu cầu token với subject.

Nếu phiên bản/generator đã tạo client_id hoặc scope đúng định dạng, không cần ghi đè chỉ để lặp lại. Hãy decode token test và kiểm tra hợp đồng của Resource Server trước khi thêm customizer.

### 13.2. Đặt audience theo resource policy

Có thể kết hợp audience mapping ở mục 6 với customizer Access Token. Trong ứng dụng thực, nên đưa mapping vào một component/policy riêng thay vì để danh sách target tùy ý từ request:

~~~java
List<String> audience = resourceAudiencePolicy.resolve(
        context.getRegisteredClient(),
        context.getAuthorizedScopes());

if (audience.isEmpty()) {
    throw new IllegalStateException("No approved resource audience");
}

context.getClaims().audience(audience);
~~~

resourceAudiencePolicy là component nghiệp vụ do ứng dụng định nghĩa, không phải class mặc định của Spring Authorization Server. Nó phải từ chối client/scope không có mapping; không trả về một audience chung để “cho chạy được”.

### 13.3. Issuer, subject, thời gian và ID

Spring Authorization Server thường tạo iss, sub, iat, exp và jti trong JWT generator theo authorization context và TokenSettings. Không nên ghi lại các claim này một cách tùy tiện trong mọi customizer:

- **iss:** lấy từ issuer context/AuthorizationServerSettings, không tự lấy host từ request.
- **sub:** lấy từ principal hoặc subject mapping đáng tin; không dùng giá trị browser tự gửi.
- **iat:** thời điểm phát hành do generator/clock quyết định.
- **exp:** dựa trên TTL đã cấu hình cho loại token.
- **jti:** định danh duy nhất do generator tạo.

Chỉ override khi có một yêu cầu kiến trúc cụ thể, có kiểm soát đồng hồ, định danh và tương thích với các validator phía Resource Server.

## 14. Ví dụ cấu hình RegisteredClient và JWT Access Token

Một client web backend có thể được đăng ký như sau:

~~~java
import java.time.Duration;
import java.util.UUID;

import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

RegisteredClient ordersBff = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("orders-bff")
        .clientSecret(encodedClientSecret)
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://portal.example.com/login/oauth2/code/orders")
        .scope("orders.read")
        .scope("profile")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
        .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(10))
                .build())
        .build();
~~~

Đây là ví dụ đăng ký một client; encodedClientSecret phải là secret đã được mã hóa phù hợp, không phải raw secret trong source code. Với JDBC repository, RegisteredClient.id cần được tạo một lần và lưu ổn định qua các lần deploy.

RegisteredClient giới hạn client được yêu cầu scope nào và dùng grant nào. **Audience vẫn cần được quyết định bởi resource policy** và đưa vào Access Token theo customizer/generator phù hợp. Không vì client tên orders-bff mà tự động cấp mọi scope cho Orders API.

## 15. Xác minh claims tại Resource Server

Authorization Server phát hành token là một nửa của hợp đồng. Resource Server phải xác minh claims theo tài nguyên mà nó bảo vệ.

Với Orders API:

- iss phải khớp issuer tin cậy.
- Chữ ký phải hợp lệ theo JWK/algorithm được cấu hình.
- exp và nbf phải hợp lệ theo clock policy.
- aud phải chứa orders-api.
- scope phải chứa quyền phù hợp, ví dụ orders.read.
- sub/tenant phải phù hợp với authorization trên tài nguyên cụ thể.

Ví dụ validator audience trong Spring Security Resource Server:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoder;

@Configuration(proxyBeanMethods = false)
class OrdersJwtValidationConfiguration {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer = "https://auth.example.com";
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains("orders-api")) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(new OAuth2Error(
                    "invalid_token",
                    "Required audience is missing",
                    null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));
        return decoder;
    }
}
~~~

Đây là cấu hình Resource Server minh họa cho Spring Security 6.x; endpoint issuer/JWKS phải có thể truy cập từ môi trường triển khai và cần được cấu hình theo trust policy thật. Trong ứng dụng hoàn chỉnh, còn cần SecurityFilterChain bật oauth2ResourceServer(...jwt...), authorization rules và converter scope/authority phù hợp.

**Không chỉ xác minh audience ở Authorization Server.** Resource Server phải tự xác minh aud vì token có thể bị chuyển nhầm hoặc bị đánh cắp từ một hệ thống khác.

## 16. Kiểm thử JWT claims

Kiểm thử nên đọc **JWT đã ký được phát hành trong integration test**, không chỉ assert builder hoặc customizer được gọi.

### 16.1. Các kiểm tra cần có

| Claim | Ca kiểm thử | Kỳ vọng |
| --- | --- | --- |
| iss | Token từ issuer test | Khớp URI issuer đã cấu hình |
| sub | User đăng nhập | Đúng định danh subject theo policy, không lộ PII không cần thiết |
| aud | Token dành cho Orders API | Có orders-api; không chứa target ngoài allowlist |
| iat | Token mới | Có giá trị, không nằm quá xa trong tương lai |
| exp | Token mới với TTL 10 phút | Sau iat, phù hợp TTL đã cấu hình |
| nbf | Token có policy hiệu lực tương lai | Không được Resource Server chấp nhận trước thời điểm |
| jti | Hai lần phát hành token | Định danh khác nhau |
| scope | Authorization chỉ được orders.read | Không có orders.write; dạng serialize phù hợp profile |

### 16.2. Ví dụ kiểm tra claims sau khi decode

Giả sử test đã hoàn thành flow và nhận accessTokenValue từ Token Endpoint:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;

import static org.assertj.core.api.Assertions.assertThat;

class AccessTokenClaimsIntegrationTest {

    @Autowired
    JwtDecoder jwtDecoder;

    @Test
    void issuedAccessTokenContainsExpectedClaims() {
        String accessTokenValue = obtainAccessTokenFromTestFlow();
        Jwt jwt = jwtDecoder.decode(accessTokenValue);

        assertThat(jwt.getClaimAsString("iss"))
                .isEqualTo("https://auth.example.com");
        assertThat(jwt.getSubject()).isEqualTo("user-8f2a91");
        assertThat(jwt.getAudience()).containsExactly("orders-api");
        assertThat(jwt.getIssuedAt()).isNotNull();
        assertThat(jwt.getExpiresAt()).isAfter(jwt.getIssuedAt());
        assertThat(jwt.getId()).isNotBlank();
        assertThat(jwt.getClaimAsString("scope")).isEqualTo("orders.read");
        assertThat(jwt.getClaimAsString("client_id")).isEqualTo("orders-bff");
    }

    private String obtainAccessTokenFromTestFlow() {
        // Thực hiện Authorization Code + PKCE trong test fixture,
        // hoàn tất login/consent và đổi code tại Token Endpoint.
        throw new UnsupportedOperationException("Provide the project's test flow");
    }
}
~~~

obtainAccessTokenFromTestFlow() là placeholder mô tả phần fixture, không phải implementation chạy độc lập. Test thật phải phát token qua đúng Authorization Server và decoder phải xác minh chữ ký của issuer test.

### 16.3. Kiểm thử âm tính

- Token đúng issuer/chữ ký nhưng sai aud → Resource Server từ chối.
- Token hết hạn → từ chối.
- Token có nbf ở tương lai → từ chối trước thời điểm.
- Token có scope profile nhưng API yêu cầu orders.read → từ chối.
- Token có sub hợp lệ nhưng thuộc tenant khác → authorization nghiệp vụ từ chối.
- Token được ký bởi key không tin cậy hoặc issuer khác → từ chối.
- Hai JWT được phát hành độc lập có jti trùng bất thường → kiểm tra token generator và uniqueness.

**Test thành công decode JWT không chứng minh mọi API đã kiểm tra claims.** Cần integration test Resource Server với endpoint được bảo vệ để chứng minh audience và scope thực sự được thực thi.

## 17. Các lỗi thiết kế thường gặp

### 17.1. Có iss nhưng Resource Server không kiểm tra

JWT chứa issuer không tự làm issuer đáng tin. Resource Server phải dùng issuer đã cấu hình và xác minh chữ ký từ key tương ứng. Không lấy iss trong token rồi tự động tin issuer mới.

### 17.2. Dùng client_id làm aud cho mọi Access Token

Client_id định danh client; aud xác định bên nhận. Nếu Resource Server cần orders-api, token có audience chỉ là orders-bff có thể không phù hợp. Hãy định nghĩa mapping audience theo resource và kiểm tra tại API.

### 17.3. Dùng email làm sub

Email có thể thay đổi, tái sử dụng hoặc tiết lộ dữ liệu cá nhân. Dùng định danh subject ổn định theo policy; nếu cần email, đưa vào claim riêng chỉ khi Resource Server thật sự cần.

### 17.4. Tăng exp để giảm lỗi refresh

Access Token sống lâu làm tăng rủi ro khi bị đánh cắp. Đặt TTL dựa trên threat model và sử dụng Refresh Token theo điều kiện grant/client khi phù hợp.

### 17.5. Cho nbf quá xa trong tương lai

Client nhận token nhưng API từ chối vì token chưa có hiệu lực. Chỉ đặt nbf khi có yêu cầu thật; kiểm tra clock và thông báo lỗi đúng cách.

### 17.6. Cho rằng jti tự chống replay

Jti chỉ là định danh. Nếu không có cơ chế lưu trạng thái/denylist hoặc kiểm tra khác, Resource Server offline không biết token đã bị thu hồi.

### 17.7. Cấp scope từ request thô

Không đưa nguyên scope client yêu cầu vào token. Dùng authorizedScopes sau khi server xét grant, RegisteredClient, consent và policy.

### 17.8. Một customizer áp dụng cho cả Access Token và ID Token

Luôn kiểm tra context.getTokenType() trước khi sửa claims. Audience của Access Token là Resource Server; audience của ID Token là OIDC Client. Nhầm hai loại có thể phá vỡ validation ở client/API.

### 17.9. Đưa bí mật vào claims

Không đưa password, client secret, refresh token, private key, code verifier hoặc dữ liệu nhạy cảm không cần thiết vào JWT. JWT payload thường chỉ được Base64URL encode, không được mã hóa mặc định; người nắm token có thể đọc claims.

## 18. Checklist triển khai

1. **Issuer:** iss khớp AuthorizationServerSettings và metadata công khai; Resource Server tin đúng issuer.
2. **Subject:** sub ổn định, có chính sách privacy, phân biệt user và client/workload.
3. **Audience:** aud chỉ ra Resource Server được phép nhận token; không lấy tùy ý từ request.
4. **Issued At:** iat phản ánh thời điểm phát hành, đồng hồ các node được đồng bộ.
5. **Expiration:** exp được tạo theo TokenSettings, TTL ngắn phù hợp và không bị customizer kéo dài vô tình.
6. **Not Before:** chỉ đặt nbf khi cần; nbf < exp và Resource Server kiểm tra.
7. **JWT ID:** jti duy nhất; nếu cần revoke/deduplicate phải có state store hoặc cơ chế kiểm tra thực tế.
8. **Scope:** chỉ dùng authorized scopes, serialize đúng profile và Resource Server enforce quyền.
9. **Token type:** customizer Access Token không làm sai ID Token hoặc opaque token.
10. **Resource Server:** xác minh chữ ký, issuer, audience, thời gian, scope và authorization nghiệp vụ.
11. **Privacy:** không đưa bí mật/PII không cần thiết vào claims; không log JWT thô.
12. **Tests:** kiểm thử claims của token đã ký, token sai audience/issuer/time/scope và hành vi API.

## 19. Bài tập và câu hỏi tự đánh giá

**Bài tập A — Phân biệt audience.** Một OIDC Client có ID orders-bff, Resource Server có ID orders-api. Hãy mô tả aud đúng cho Access Token và ID Token, giải thích vì sao không thể dùng một giá trị cho cả hai.

**Bài tập B — Thiết kế subject.** Người dùng đổi email nhưng vẫn giữ tài khoản. Chọn giá trị sub ổn định và giải thích rủi ro nếu dùng email.

**Bài tập C — TTL.** Access Token được phát hành lúc 10:00:00, accessTokenTimeToLive là 600 giây. Xác định iat và exp kỳ vọng; phân tích ảnh hưởng nếu một Resource Server lệch đồng hồ 5 phút.

**Bài tập D — Scope.** Client yêu cầu orders.read orders.write nhưng user chỉ được chấp thuận orders.read. Viết customizer dùng context.getAuthorizedScopes() và test rằng token không có orders.write.

**Bài tập E — Audience validator.** Viết Resource Server validator chỉ chấp nhận aud=orders-api, sau đó thử JWT có audience billing-api nhưng issuer và chữ ký hợp lệ.

**Bài tập F — jti và revocation.** Một JWT có jti duy nhất bị đánh cắp. Mô tả vì sao chỉ có jti không đủ thu hồi token và thiết kế một cách kiểm tra trạng thái phù hợp.

**Câu hỏi ôn tập:**

1. iss khác aud ở điểm nào?
2. Vì sao sub nên là định danh ổn định thay vì email?
3. aud của Access Token khác aud của ID Token ra sao?
4. iat, exp và nbf sử dụng kiểu dữ liệu nào trong JWT?
5. Token có nbf ở tương lai cần được Resource Server xử lý thế nào?
6. jti có tự động chống replay hay thu hồi JWT không?
7. Vì sao scope nên lấy từ authorized scopes thay vì requested scopes?
8. OAuth2TokenCustomizer<JwtEncodingContext> áp dụng cho opaque token không?
9. Vì sao cần guard OAuth2TokenType.ACCESS_TOKEN trước khi thay audience?
10. Nếu JWT có chữ ký hợp lệ nhưng audience sai, Resource Server phải làm gì?
11. Khi nâng cấp Spring Authorization Server, cần xác minh điều gì về claims mặc định?
12. Tại sao không được đưa client secret hoặc Refresh Token vào JWT claims?

## 20. Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0 — ID Token](https://openid.net/specs/openid-connect-core-1_0.html#IDToken)
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)

**Ghi nhớ:** iss trả lời **ai phát hành**, sub trả lời **token đại diện ai**, aud trả lời **ai được nhận**, iat/exp/nbf xác định **thời gian hiệu lực**, jti định danh **một token**, còn scope mô tả **quyền được cấp**. Authorization Server phải phát hành claims từ ngữ cảnh đã xác thực; Resource Server phải kiểm tra chúng theo đúng API. Một chữ ký JWT hợp lệ không thể thay thế kiểm tra issuer, audience, thời gian và quyền.
