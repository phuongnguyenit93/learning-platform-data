# Kiểm tra hợp đồng claims, thuật toán và chính sách clock skew

## 1. Vì sao Resource Server cần một JWT contract rõ ràng?

Trong chương **Tích hợp ứng dụng** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, chúng ta học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot.

Authorization Server và Resource Server có thể được triển khai, nâng cấp và vận hành độc lập. Authorization Server phát hành access token; Resource Server nhận token và quyết định có chấp nhận nó cho API hiện tại hay không. Hai bên cần thống nhất một **hợp đồng token**: claim nào phải có, claim nào có thể vắng mặt, kiểu dữ liệu, ý nghĩa, thuật toán ký, key identifier, token type và cách xử lý timestamp.

Nếu hợp đồng chỉ được hiểu ngầm trong code, thay đổi nhỏ ở một phía có thể làm hỏng tích hợp ở phía còn lại. Ví dụ:

- Authorization Server đổi audience từ một URI sang danh sách URI nhưng Resource Server chỉ đọc string.
- Một grant Client Credentials đặt subject là user ID trong khi Resource Server hiểu đó là service account.
- Authorization Server chuyển từ RS256 sang ES256 nhưng Resource Server chỉ cho phép RS256.
- Hai node lệch đồng hồ khiến token bị coi là chưa có hiệu lực hoặc đã hết hạn.
- Resource Server nhận ID Token hoặc JWT dùng cho mục đích khác rồi coi nó là access token.

Một JWT được ký đúng chưa đủ để chứng minh token phù hợp với API. Resource Server cần kiểm tra cấu trúc, issuer, audience, thời gian, token type, thuật toán, key và claim nghiệp vụ theo hợp đồng.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Xây dựng JWT access token contract giữa Authorization Server và Resource Server.
- Phân biệt claim bắt buộc, tùy chọn và claim riêng của ứng dụng.
- Hiểu semantics của iss, sub, aud, exp, iat, nbf, jti, client_id, scope và tenant_id.
- Áp dụng JWT Access Token Profile theo RFC 9068 khi hai phía cần tuân thủ profile này.
- Giới hạn thuật toán JWS và kiểm tra tính tương thích giữa thuật toán với JWK.
- Cấu hình JwtTimestampValidator và clock skew trong Spring Security 6.5.
- Bổ sung validator cho claim bắt buộc, token lifetime và claim nghiệp vụ.
- Quản lý thay đổi contract và thuật toán theo giai đoạn tương thích.
- Kiểm thử chữ ký, claims, key rotation, timestamp boundary và sai lệch đồng hồ.

## 2. JWT contract gồm những gì?

Một JWT contract nên mô tả ít nhất bốn nhóm:

| Nhóm | Nội dung cần thống nhất | Ví dụ |
| --- | --- | --- |
| JOSE header | Loại token, thuật toán, key identifier và header được phép. | typ, alg, kid. |
| Registered claims | Issuer, subject, audience, thời điểm và token identifier. | iss, sub, aud, exp, iat, nbf, jti. |
| Authorization claims | Quyền mà Resource Server dùng để quyết định truy cập. | scope, roles, groups, entitlements. |
| Application claims | Thuộc tính riêng của miền nghiệp vụ. | tenant_id, account_id, contract_version. |

Contract cần ghi rõ claim có bắt buộc hay không, kiểu dữ liệu, nguồn dữ liệu đáng tin cậy, semantics theo grant type, resource server nào được nhận token, thuật toán và loại key được chấp nhận, khoảng thời gian token được coi là hợp lệ và cách triển khai thay đổi có tương thích ngược.

Không coi một ví dụ payload trong tài liệu là contract hoàn chỉnh. Contract phải định nghĩa cả trường hợp thiếu claim, claim sai kiểu, nhiều audience, client credentials, user delegation và token cũ trong giai đoạn nâng cấp.

## 3. Phân biệt JWT thông thường và JWT Access Token Profile

JWT là định dạng token tổng quát. Cùng định dạng có thể được dùng cho OIDC ID Token, OAuth access token, client assertion, logout token hoặc token nội bộ. Các loại token có thể chứa claim trùng tên nhưng ý nghĩa và người nhận khác nhau.

| Loại token | Mục đích | Người tiêu thụ |
| --- | --- | --- |
| OIDC ID Token | Chứng minh kết quả authentication cho OIDC client. | Relying Party/OIDC client. |
| OAuth JWT Access Token | Cho phép truy cập một resource server. | Resource Server được nêu trong audience. |
| JWT Client Assertion | Xác thực OAuth client tại Token Endpoint. | Authorization Server. |
| JWT Logout Token | Truyền sự kiện logout OIDC. | OIDC client/Relying Party. |
| JWT nội bộ | Mang dữ liệu cho một workflow riêng. | Thành phần được chỉ định trong contract nội bộ. |

### 3.1. Tránh cross-JWT confusion

Một ID Token có thể có chữ ký hợp lệ và được ký bởi cùng issuer với access token. Điều đó không làm nó trở thành access token. Nếu Resource Server chỉ kiểm tra chữ ký và iss, token có thể bị dùng sai mục đích.

Hãy phân biệt các loại JWT bằng một tổ hợp phù hợp:

- Token type trong header typ.
- Audience khác nhau cho từng resource/use case.
- Issuer hoặc signing key riêng khi kiến trúc cần.
- Bộ claim bắt buộc và semantics riêng.
- Validator chỉ chấp nhận đúng profile của endpoint.

RFC 8725 khuyến nghị dùng explicit typing và các quy tắc validation tách biệt để ngăn một loại JWT bị dùng trong context khác. RFC 9068 định nghĩa profile dành riêng cho JWT access token với typ là at+jwt hoặc application/at+jwt.

## 4. Các claim cốt lõi và semantics

### 4.1. Bảng claim

| Claim | Kiểu dữ liệu | Ý nghĩa | Quy tắc xác minh |
| --- | --- | --- | --- |
| iss | String/URI | Authorization Server phát hành token. | Phải khớp chính xác issuer được tin cậy. |
| sub | String | Subject mà token đại diện. | Phải có semantics rõ theo grant; không mặc định luôn là user. |
| aud | String hoặc array string | Resource server/người nhận được phép sử dụng token. | Phải chứa identifier của API hiện tại. |
| exp | NumericDate | Thời điểm token hết hạn. | Phải tồn tại theo contract và chưa hết hạn, có xét clock skew nhỏ. |
| iat | NumericDate | Thời điểm token được phát hành. | Kiểm tra tồn tại, không ở tương lai quá mức cho phép và tuổi token nếu policy yêu cầu. |
| nbf | NumericDate | Thời điểm token bắt đầu có hiệu lực. | Nếu có, không được nằm ngoài khoảng thời gian cho phép. |
| jti | String | ID duy nhất của token. | Phải có nếu contract yêu cầu; dùng để audit/denylist/replay detection khi cần. |
| client_id | String | OAuth client đã xin token. | Phân biệt client identity với subject. |
| scope | String | Các scope được cấp, thường phân tách bằng dấu cách. | Chỉ chứa scope được duyệt cho audience. |
| tenant_id | String | Tenant mà token thuộc về, nếu ứng dụng có multi-tenancy. | Phải khớp issuer/tenant mapping đáng tin cậy. |

RFC 9068 quy định các claim bắt buộc của profile JWT access token gồm iss, exp, aud, sub, client_id, iat và jti. nbf không nằm trong danh sách bắt buộc chung của profile, nhưng nếu được phát hành thì Resource Server phải xử lý đúng semantics của nó.

### 4.2. iss phải khớp chính xác

iss xác định Authorization Server. So sánh theo giá trị issuer đầy đủ, bao gồm scheme, host, port và path nếu có. Không tự bỏ path hoặc trailing slash để tạo phép so khớp gần đúng.

Trong mô hình đa tenant, issuer thường còn xác định miền danh tính. Hai token có cùng sub nhưng iss khác nhau không mặc nhiên đại diện cho cùng một principal.

### 4.3. sub không phải lúc nào cũng là user ID

Với Authorization Code Grant hoặc grant đại diện resource owner, sub thường là subject identifier của user. Với Client Credentials Grant, không có resource owner; sub có thể là định danh của client application hoặc service principal theo contract.

Resource Server không nên ép mọi sub vào bảng user. Nếu cần định danh principal duy nhất qua nhiều issuer, dùng cặp (iss, sub) hoặc một mapping tin cậy.

### 4.4. aud phải xác định resource cụ thể

Audience trả lời câu hỏi: token được phát hành cho API nào? Một token có thể được ký đúng và chưa hết hạn nhưng vẫn phải bị từ chối nếu aud không chứa API hiện tại.

Nếu token phục vụ nhiều resource, contract phải định nghĩa scope nào có ý nghĩa với từng audience. Tránh phát một token có nhiều audience và một tập scope mơ hồ không thể gắn với resource cụ thể.

### 4.5. client_id và sub trả lời hai câu hỏi khác nhau

client_id xác định ứng dụng OAuth đã xin token. sub xác định subject mà token đại diện. Trong grant có user delegation, hai giá trị thường khác nhau. Trong Client Credentials, chúng có thể cùng chỉ một service identity theo policy, nhưng không nên mặc định hai claim luôn bằng nhau.

### 4.6. scope phải có semantics rõ

OAuth scope thường được biểu diễn thành một string với các giá trị phân tách bằng dấu cách:

```json
{
  "scope": "orders.read orders.write"
}
```

Một số hệ thống dùng claim scp dạng array. Đây là lựa chọn contract riêng, không tự suy luận rằng scope và scp luôn tương đương. Nếu Resource Server hỗ trợ cả hai, phải định nghĩa thứ tự ưu tiên và cách xử lý khi cả hai cùng xuất hiện nhưng khác nhau.

## 5. Claim bắt buộc, tùy chọn và claim riêng

### 5.1. Required claims

Required claim là claim thiếu thì token không thể đáp ứng contract của API. Ví dụ một API có thể yêu cầu:

- iss: xác định nguồn phát hành.
- aud: xác định API nhận token.
- sub: xác định subject.
- exp: giới hạn thời gian sử dụng.
- client_id: xác định client.
- iat: thời điểm phát hành.
- jti: token identifier.
- scope: nếu API contract yêu cầu scope claim phải luôn có.
- tenant_id: nếu mọi request của API bắt buộc nằm trong một tenant.

Không đánh dấu mọi claim là bắt buộc chỉ vì một ví dụ token hiện tại có claim đó. Ví dụ auth_time, acr và amr có thể chỉ xuất hiện khi grant có resource owner authentication và policy cần thông tin về mức độ xác thực.

### 5.2. Optional claims

Optional claim có thể vắng mặt. Resource Server phải có hành vi rõ khi claim vắng mặt: không dùng claim đó trong policy, áp dụng giá trị mặc định đã định nghĩa hoặc từ chối một chức năng cụ thể cần claim đó.

Không chuyển một claim optional thành quyền mặc định cao hơn khi claim bị thiếu.

### 5.3. Private claims

Claim riêng của ứng dụng nên có tên collision-resistant, đặc biệt nếu token được nhiều tổ chức hoặc sản phẩm tiêu thụ. Có thể dùng URI namespace:

```json
{
  "https://example.com/claims/contract_version": "1",
  "https://example.com/claims/tenant_id": "tenant-a"
}
```

Không đặt custom claim trùng tên với registered claim hoặc một claim chuẩn nhưng mang ý nghĩa khác. Kiểu dữ liệu phải ổn định: tenant_id là string, roles là array string, permissions là tập quyền đã được định nghĩa.

### 5.4. Không đưa dữ liệu nhạy cảm vào JWT

JWT JWS chỉ được ký, không mặc định được mã hóa. Client và người giữ token có thể decode payload. Chỉ đưa claim cần thiết cho Resource Server; tránh password, secret, số định danh nhạy cảm, dữ liệu hồ sơ lớn hoặc thông tin không cần thiết cho authorization.

## 6. Thiết kế contract theo grant type

Không phải mọi grant đều có cùng subject semantics. Hãy định nghĩa token profile theo grant và resource.

| Grant | Subject (sub) | Client (client_id) | Claim có thể cần |
| --- | --- | --- | --- |
| Authorization Code | User/resource owner đã xác thực. | Ứng dụng client. | auth_time, acr, amr khi policy cần. |
| Client Credentials | Service principal/client identity. | Service client. | tenant_id, workload identity, resource audience. |
| Device Authorization | User đã hoàn thành xác nhận trên thiết bị khác. | Device client. | User subject và scope đã consent. |
| Token Exchange | Subject/actor theo delegation được chấp thuận. | Client thực hiện exchange. | act, may_act, audience và scope theo profile hỗ trợ. |
| Custom Grant | Subject do grant đã xác minh xác định. | Client đã authenticate. | Grant identifier hoặc tenant claim nếu policy cho phép. |

Không lấy sub từ request parameter chưa xác minh. Authorization Server phải xác định subject từ authentication hoặc grant record đáng tin cậy.

### 6.1. Scope phải phù hợp audience

Nếu token có audience orders-api, scope orders.read phải có ý nghĩa trên Orders API. Không đưa scope billing.write vào cùng token nếu không có một policy rõ ràng gắn nó với resource khác.

Resource Server chỉ cấp quyền dựa trên scope đã được ký và được contract chấp nhận. Nó vẫn phải kiểm tra quyền trên từng bản ghi, tenant và quan hệ nghiệp vụ.

## 7. Ví dụ JWT access token contract

Ví dụ sau mô tả một token theo profile nội bộ của API Orders. Đây không tự động tuyên bố token tuân thủ RFC 9068; để tuyên bố tuân thủ profile đó, cần đáp ứng đầy đủ header và validation rules tương ứng.

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-8f31",
  "aud": ["https://orders-api.example.com"],
  "exp": 1794852300,
  "iat": 1794851700,
  "nbf": 1794851680,
  "jti": "9d5d1a5e-6f5a-4b6d-9e77-14d1ef4f52b1",
  "client_id": "storefront-web",
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-a",
  "https://example.com/claims/contract_version": "1"
}
```

Contract minh họa:

- Issuer là https://auth.example.com.
- API Orders là audience bắt buộc.
- sub là subject đã xác minh.
- Token có hiệu lực trong khoảng từ nbf đến exp, có áp dụng clock skew nhỏ.
- jti duy nhất trong phạm vi token issuer.
- Client ID là ứng dụng đã xin token.
- Scope có định dạng OAuth space-delimited.
- Tenant ID phải khớp tenant context do hệ thống tin cậy xác định.
- Contract version là string "1", không phải number.

Resource Server phải từ chối token thiếu claim bắt buộc, sai kiểu dữ liệu, sai issuer/audience hoặc vượt quá khoảng thời gian hợp lệ.

## 8. Chuẩn hóa bằng RFC 9068

RFC 9068 định nghĩa JWT Profile for OAuth 2.0 Access Tokens để Authorization Server và Resource Server khác implementation có thể thống nhất cấu trúc và quy tắc xác minh.

Các điểm quan trọng của profile:

- JWT access token phải được ký; thuật toán none không được chấp nhận.
- Header typ phải là at+jwt hoặc application/at+jwt.
- Các claim bắt buộc gồm iss, exp, aud, sub, client_id, iat, jti.
- Resource Server phải kiểm tra issuer chính xác, audience chứa resource identifier của chính nó và chữ ký bằng key của Authorization Server.
- Scope trong token phải có ý nghĩa đối với resource được nêu trong audience.
- Có thể cho phép một khoảng leeway nhỏ để xử lý clock skew.

RFC 9068 là một profile cụ thể. Nếu hệ thống hiện có dùng typ JWT và một bộ claim riêng, không được chỉ đổi validator ở Resource Server sang RFC 9068 mà không thay đổi Authorization Server và kiểm thử tương thích.

### 8.1. Phân biệt JWT và at+jwt

typ JWT chỉ cho biết token là JWT ở mức tổng quát. typ at+jwt chỉ rõ token là OAuth JWT access token theo RFC 9068.

Spring Security 6.5 có JwtTypeValidator.jwt() để chấp nhận JWT hoặc không có typ theo cấu hình validator mặc định. Khi áp dụng RFC 9068, decoder phải chuyển việc kiểm tra type sang JwtValidators.createAtJwtValidator(), thay vì để validator tổng quát từ chối at+jwt.

### 8.2. Cấu hình RFC 9068 trên Resource Server

Ví dụ sau dùng API của Spring Security 6.5:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration(proxyBeanMethods = false)
public class Rfc9068JwtDecoderConfig {

    private static final String ISSUER =
            "https://auth.example.com";
    private static final String AUDIENCE =
            "https://orders-api.example.com";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(ISSUER)
                        .jwsAlgorithm(SignatureAlgorithm.RS256)
                        .validateTypes(false)
                        .build();

        decoder.setJwtValidator(
                JwtValidators.createAtJwtValidator()
                        .issuer(ISSUER)
                        .audience(AUDIENCE)
                        .build());

        return decoder;
    }
}
```

createAtJwtValidator() kiểm tra RFC 9068 profile, bao gồm typ và các claim bắt buộc. Nếu API chỉ chấp nhận token từ một client cụ thể, có thể thêm clientId("orders-service-client"). Nếu API phục vụ nhiều client, không pin một client ID duy nhất; hãy giữ validator kiểm tra sự hiện diện và kiểu dữ liệu của client_id theo contract.

Ví dụ này dùng clock skew mặc định của validator profile. Nếu cần một chính sách clock skew khác, hãy xác định rõ cách thay thế timestamp validator và kiểm thử lại toàn bộ required claim validation; không bỏ profile validator để chỉ giữ một kiểm tra thời gian.

## 9. Contract versioning và thay đổi tương thích

JWT access token thường có tuổi thọ ngắn, nhưng trong một khoảng thời gian Resource Server có thể nhận token được phát hành bởi nhiều phiên bản Authorization Server. Vì vậy, thay đổi contract cần có giai đoạn tương thích.

### 9.1. Thay đổi thường tương thích ngược

- Thêm optional claim mới mà Resource Server cũ bỏ qua.
- Thêm một scope mới nhưng không cấp nó cho client cũ.
- Thêm metadata không ảnh hưởng semantics của claim hiện tại.
- Tăng version tài liệu contract nhưng giữ nguyên schema và behavior.

### 9.2. Thay đổi có thể phá vỡ tích hợp

- Đổi kiểu claim từ string sang array.
- Đổi scope thành scp mà không hỗ trợ song song.
- Đổi semantics của sub.
- Thay đổi iss hoặc audience identifier.
- Bỏ claim bắt buộc.
- Đổi typ từ JWT sang at+jwt mà Resource Server chưa được cập nhật.
- Đổi thuật toán ký mà decoder chưa allowlist thuật toán mới.
- Giảm clock skew hoặc TTL khiến token đang được phát hành bị từ chối.

### 9.3. Quy trình nâng cấp contract

1. Ghi lại contract hiện tại và các consumer đang sử dụng.
2. Thêm khả năng đọc claim/algorithm mới vào Resource Server trước.
3. Triển khai Authorization Server phát hành token theo contract mới hoặc giai đoạn chuyển tiếp.
4. Quan sát tỷ lệ token cũ/mới và lỗi validation.
5. Chờ token cũ hết hạn cộng clock skew và khoảng đệm vận hành.
6. Loại bỏ validator/algorithm cũ khi không còn token hợp lệ cần hỗ trợ.

Không giữ thuật toán yếu hoặc claim cũ vô thời hạn chỉ để tránh thay đổi. Giai đoạn tương thích phải có thời điểm kết thúc và tiêu chí quan sát rõ ràng.

## 10. Chọn thuật toán chữ ký

### 10.1. Thuật toán là policy của ứng dụng

Header alg do token mang tới không phải quyết định mà Resource Server được phép tin. Resource Server phải cấu hình trước danh sách thuật toán được chấp nhận; thư viện chỉ thực hiện xác minh bằng thuật toán trong danh sách đó.

Spring Security 6.5 NimbusJwtDecoder mặc định chỉ tin RS256. Có thể cấu hình rõ qua Spring Boot:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com
          jws-algorithms: RS256
```

Hoặc cấu hình trực tiếp bằng builder:

```java
NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withIssuerLocation("https://auth.example.com")
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();
```

Không chấp nhận none. Không tự động cho phép mọi thuật toán chỉ vì JWK Set response hoặc token header có khai báo thuật toán đó.

### 10.2. So sánh một số nhóm thuật toán

| Nhóm | Ví dụ | Đặc điểm | Lưu ý |
| --- | --- | --- | --- |
| RSA PKCS#1 v1.5 | RS256, RS384, RS512 | Phổ biến, tương thích rộng, dùng private/public key. | RS256 là mặc định được Spring Security 6.5 tin cậy. |
| RSA-PSS | PS256, PS384, PS512 | Dùng RSA với padding PSS. | Hai bên phải hỗ trợ cùng thuật toán và key phù hợp. |
| ECDSA | ES256, ES384, ES512 | Chữ ký gọn hơn với elliptic curve. | Phải khớp curve và thuật toán. |
| HMAC | HS256, HS384, HS512 | Cùng secret để ký và xác minh. | Resource Server phải giữ secret có khả năng ký; không công bố secret trong JWKS. |

Với Authorization Server và nhiều Resource Server độc lập, chữ ký bất đối xứng thường phù hợp hơn: Authorization Server giữ private key, Resource Server chỉ cần public key. Nếu Resource Server có shared HMAC secret, một Resource Server bị xâm nhập có thể tạo token giả mà các thành phần khác chấp nhận.

### 10.3. Không dùng thuật toán yếu hoặc tự chọn từ token

RFC 8725 yêu cầu ứng dụng xác minh thuật toán, giới hạn tập thuật toán được hỗ trợ và ràng buộc mỗi key với thuật toán tương ứng. Không:

- Chấp nhận alg none.
- Dùng cùng key với nhiều thuật toán không tương thích.
- Cho token tự quyết định key URL hoặc key material.
- Hạ cấp thuật toán khi chữ ký không xác minh được.
- Dùng HMAC secret như thể nó là public key.

## 11. Tương thích giữa JWS algorithm và JWK

Thuật toán ký phải tương thích với loại key:

| JWS algorithm | JWK kty | Key parameter cần phù hợp |
| --- | --- | --- |
| RS256 | RSA | RSA public modulus/exponent và private key tương ứng ở Authorization Server. |
| PS256 | RSA | RSA key được dùng với RSA-PSS. |
| ES256 | EC | Curve P-256. |
| ES384 | EC | Curve P-384. |
| ES512 | EC | Curve P-521. |

JWK có thể chứa kid, kty, use, key_ops, alg và các tham số key. kid phải xác định key duy nhất trong key set đang công bố. Nếu JWK khai báo alg, giá trị phải phù hợp thuật toán token ký.

Resource Server phải chọn public key từ JWKS được cấu hình/khám phá qua issuer tin cậy. Không dùng jku, x5u hoặc một URL do JWT header chỉ định để tự tải key.

### 11.1. Cấu hình nhiều thuật toán trong giai đoạn chuyển đổi

Spring Security cho phép cấu hình nhiều thuật toán bằng cách gọi jwsAlgorithm nhiều lần:

```java
NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withIssuerLocation("https://auth.example.com")
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .jwsAlgorithm(SignatureAlgorithm.PS256)
                .build();
```

Chỉ cho phép đồng thời nhiều thuật toán khi có kế hoạch chuyển đổi cụ thể. Theo dõi token thực tế đang được phát hành; sau khi không còn token hợp lệ dùng thuật toán cũ, bỏ thuật toán đó khỏi allowlist.

### 11.2. kid không thay thế algorithm validation

kid chỉ giúp tìm key. Nó không chứng minh token đáng tin cậy. Decoder vẫn phải kiểm tra chữ ký, thuật toán, issuer và audience. Nếu kid không tồn tại hoặc key không tương thích thuật toán, từ chối token.

## 12. Đồng bộ thuật toán ở Authorization Server

Authorization Server phải phát hành JWT bằng thuật toán mà Resource Server chấp nhận. Khi dùng Spring Authorization Server, JwtGenerator dùng JwtEncoder và JWK phù hợp để ký token.

Contract vận hành cần ghi rõ thuật toán đang dùng, loại key và curve/size phù hợp, kid của signing key hiện tại, JWK Set URI công bố public key, thời điểm bắt đầu/kết thúc chuyển đổi thuật toán và khoảng thời gian giữ key cũ để xác minh token chưa hết hạn.

Không rotate signing algorithm chỉ bằng cách thay cấu hình ở Authorization Server. Resource Server phải được cập nhật allowlist trước khi token mới được phát hành.

### 12.1. Đặt token type và custom claim tại Authorization Server

Spring Authorization Server cho phép tùy biến header và claims của JWT qua OAuth2TokenCustomizer<JwtEncodingContext>. Nếu hệ thống áp dụng RFC 9068, có thể đặt type at+jwt cho access token và bổ sung claim contract theo namespace:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Configuration(proxyBeanMethods = false)
public class JwtContractCustomizerConfig {

    @Bean
    OAuth2TokenCustomizer<JwtEncodingContext> jwtContractCustomizer() {
        return context -> {
            if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
                context.getJwsHeader().type("at+jwt");
                context.getClaims().claim(
                        "https://example.com/claims/contract_version", "1");
            }
        };
    }
}
```

Đoạn code chỉ nên được bật khi Resource Server đã được cấu hình để chấp nhận RFC 9068. Nếu ứng dụng đã có OAuth2TokenCustomizer<JwtEncodingContext>, hãy hợp nhất logic vào customizer hiện tại; không tạo nhiều bean cùng generic type một cách vô tình. Claims tenant, role hoặc permission phải lấy từ nguồn tin cậy của server, không copy trực tiếp request parameter.

## 13. Clock skew là gì?

Các máy trong hệ thống phân tán có thể không có cùng thời gian chính xác. Authorization Server có thể phát token lúc 12:00:00, nhưng đồng hồ Resource Server chạy nhanh hơn 20 giây. Khi token có nbf bằng thời điểm phát hành, Resource Server có thể nghĩ token chưa có hiệu lực.

Ngược lại, nếu Resource Server chạy chậm hơn, nó có thể tiếp tục chấp nhận token sau thời điểm exp thật.

Clock skew là khoảng dung sai nhỏ mà Resource Server cho phép để xử lý sai lệch đồng hồ giữa các hệ thống.

Spring Security dùng JwtTimestampValidator để kiểm tra cửa sổ hiệu lực của token:

- nbf: token không được sử dụng trước thời điểm bắt đầu hiệu lực.
- exp: token không được sử dụng từ thời điểm hết hạn trở đi.

Trong Spring Security 6.5, clock skew mặc định là 60 giây.

### 13.1. Khoảng hiệu lực khi có skew

Với clock skew S, thời điểm hiện tại được chấp nhận trong một khoảng có thể hình dung:

```text
nbf - S <= now < exp + S
```

Đây là cách diễn giải policy leeway. Nó có nghĩa token có thể được chấp nhận sớm hơn nbf một lượng nhỏ và muộn hơn exp một lượng nhỏ.

Clock skew không sửa timestamp trong token, không kéo dài exp mà Authorization Server đã phát hành và không thay thế việc đồng bộ đồng hồ. Nó chỉ thay đổi cách Resource Server đánh giá ranh giới thời gian.

### 13.2. Chọn skew nhỏ

Một giá trị như 30 hoặc 60 giây thường đủ cho môi trường có NTP/chrony hoạt động ổn định. RFC 9068 cho phép leeway nhỏ, thường không quá vài phút, để xử lý clock skew.

Không đặt skew quá lớn để che một hệ thống có đồng hồ sai. Skew càng lớn thì cửa sổ sử dụng token ngoài thời gian danh nghĩa càng rộng, đặc biệt ở ranh giới hết hạn.

## 14. Cấu hình clock skew bằng JwtTimestampValidator

Spring Security 6.5 cung cấp constructor nhận Duration:

```java
import java.time.Duration;

import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

JwtTimestampValidator timestampValidator =
        new JwtTimestampValidator(Duration.ofSeconds(45));
```

Ví dụ Resource Server dùng issuer, audience, type và timestamp validator riêng:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.JwtTypeValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration(proxyBeanMethods = false)
public class ResourceServerJwtContractConfig {

    private static final String ISSUER = "https://auth.example.com";
    private static final String AUDIENCE = "https://orders-api.example.com";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(ISSUER)
                        .jwsAlgorithm(SignatureAlgorithm.RS256)
                        .build();

        OAuth2TokenValidator<Jwt> validators =
                new DelegatingOAuth2TokenValidator<>(
                        new JwtTimestampValidator(Duration.ofSeconds(45)),
                        new JwtIssuerValidator(ISSUER),
                        JwtTypeValidator.jwt(),
                        audienceValidator(),
                        requiredClaimsValidator());

        decoder.setJwtValidator(validators);
        return decoder;
    }

    private OAuth2TokenValidator<Jwt> audienceValidator() {
        return jwt -> jwt.getAudience() != null &&
                jwt.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error("invalid_token", "Invalid audience", null));
    }

    private OAuth2TokenValidator<Jwt> requiredClaimsValidator() {
        return jwt -> {
            boolean valid = jwt.getIssuer() != null
                    && jwt.getSubject() != null
                    && !jwt.getSubject().isBlank()
                    && jwt.getAudience() != null
                    && !jwt.getAudience().isEmpty()
                    && jwt.getExpiresAt() != null
                    && jwt.getIssuedAt() != null
                    && jwt.getId() != null
                    && !jwt.getId().isBlank()
                    && jwt.getClaimAsString("client_id") != null
                    && !jwt.getClaimAsString("client_id").isBlank();

            return valid
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                    "invalid_token", "Required claim is missing", null));
        };
    }
}
```

Ví dụ này cố ý liệt kê validator tường minh để đặt clock skew 45 giây. Khi tự xây validator chain, phải giữ đủ các kiểm tra cần thiết cho profile đang dùng. JwtTypeValidator.jwt() phù hợp với token type JWT hoặc không có typ; nếu contract dùng RFC 9068 at+jwt, hãy dùng JwtValidators.createAtJwtValidator() như phần 8.

Nếu contract nội bộ yêu cầu header typ phải hiện diện và có đúng giá trị JWT, thay JwtTypeValidator.jwt() bằng new JwtTypeValidator("JWT"). Validator jwt() cho phép header typ vắng mặt; lựa chọn strict cần khớp với cách Authorization Server thực sự phát hành token.

Nếu dùng JwtValidators.createDefaultWithIssuer(ISSUER), Spring Security đã cung cấp validator chuẩn gồm issuer, timestamp và token type với skew mặc định 60 giây. Khi cần đổi skew, không chỉ thêm một validator khác rồi nghĩ rằng validator mặc định đã bị thay thế; hãy tạo chain rõ ràng như ví dụ và kiểm tra không bỏ sót validator.

## 15. Dùng Clock cố định để kiểm thử thời gian

JwtTimestampValidator hỗ trợ setClock(Clock) để test mà không phụ thuộc thời gian thực của máy:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-16T12:00:00Z"),
        ZoneOffset.UTC);

JwtTimestampValidator validator =
        new JwtTimestampValidator(Duration.ofSeconds(30));
validator.setClock(fixedClock);
```

Khi dùng clock cố định, test có thể tạo token ở đúng ranh giới:

| Token timestamp | Thời điểm hiện tại | Kết quả với skew 30 giây |
| --- | --- | --- |
| nbf = now - 1 phút | now | Hợp lệ nếu các kiểm tra khác đạt. |
| nbf = now + 20 giây | now | Vẫn nằm trong leeway. |
| nbf = now + 45 giây | now | Bị từ chối. |
| exp = now - 20 giây | now | Vẫn nằm trong leeway hết hạn. |
| exp = now - 45 giây | now | Bị từ chối. |
| exp = now + 5 phút | now | Chưa hết hạn. |

Các test này giúp phát hiện nhầm lẫn giữa timestamp UTC, timezone và logic so sánh thời gian. NumericDate là số giây tính từ Unix epoch; không phát exp dưới dạng chuỗi ngày ISO-8601.

## 16. iat không giống exp và nbf

JwtTimestampValidator tập trung vào cửa sổ hiệu lực qua exp và nbf. Claim iat biểu thị thời điểm phát hành; chỉ có iat không tự giới hạn tuổi tối đa của token.

Nếu policy cần từ chối token có iat ở tương lai quá mức cho phép, giới hạn token không được cũ hơn 10 phút, bảo đảm exp sau iat hoặc giới hạn TTL tối đa là 15 phút, thì cần thêm validator riêng.

Ví dụ:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class IssuedAtPolicyValidator
        implements OAuth2TokenValidator<Jwt> {

    private final Clock clock;
    private final Duration allowedFutureSkew;
    private final Duration maxTokenAge;
    private final Duration maxTokenLifetime;

    public IssuedAtPolicyValidator(
            Clock clock,
            Duration allowedFutureSkew,
            Duration maxTokenAge,
            Duration maxTokenLifetime) {
        this.clock = clock;
        this.allowedFutureSkew = allowedFutureSkew;
        this.maxTokenAge = maxTokenAge;
        this.maxTokenLifetime = maxTokenLifetime;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        Instant issuedAt = jwt.getIssuedAt();
        Instant expiresAt = jwt.getExpiresAt();
        Instant now = this.clock.instant();

        if (issuedAt == null || expiresAt == null) {
            return failure();
        }
        if (issuedAt.isAfter(now.plus(this.allowedFutureSkew))) {
            return failure();
        }
        if (issuedAt.isBefore(now.minus(this.maxTokenAge)
                .minus(this.allowedFutureSkew))) {
            return failure();
        }
        if (!expiresAt.isAfter(issuedAt)) {
            return failure();
        }
        if (Duration.between(issuedAt, expiresAt)
                .compareTo(this.maxTokenLifetime) > 0) {
            return failure();
        }
        return OAuth2TokenValidatorResult.success();
    }

    private OAuth2TokenValidatorResult failure() {
        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                        "invalid_token",
                        "The token violates the issued-at policy",
                        null));
    }
}
```

Validator này là policy bổ sung của ứng dụng, không phải behavior mặc định của Spring Security. Hãy chọn maxTokenAge và maxTokenLifetime phù hợp TTL do Authorization Server phát hành. Nếu token hợp lệ có thể sống lâu hơn giới hạn này, Resource Server sẽ từ chối token dù exp vẫn còn trong tương lai.

Không dùng clock skew để cho phép iat tùy ý nằm trong tương lai. Leeway chỉ xử lý sai lệch đồng hồ nhỏ; token có thời điểm phát hành bất thường vẫn phải bị từ chối.

## 17. Đồng bộ đồng hồ trong môi trường phân tán

Clock skew là lớp dung sai cuối cùng, không phải giải pháp thay cho đồng bộ đồng hồ.

Các thực hành vận hành:

- Dùng NTP hoặc chrony trên máy chủ và container host.
- Đồng bộ UTC giữa Authorization Server, Resource Server, database và hệ thống audit.
- Theo dõi clock offset và cảnh báo khi vượt ngưỡng.
- Tránh tự thay đổi timezone của JVM để xử lý sai lệch thời gian.
- Không dùng thời gian client gửi lên làm cơ sở xác minh token.
- Giữ clock skew trong contract và cấu hình giống nhau giữa các Resource Server có cùng policy.

Nếu một node có offset 3 phút nhưng clock skew chỉ 45 giây, token bị từ chối là behavior đúng. Hãy sửa hạ tầng thời gian thay vì tăng skew lên 5 phút.

### 17.1. Clock skew ảnh hưởng gì tới revocation và TTL?

JWT tự chứa claims nên Resource Server thường không hỏi Authorization Server mỗi request. Nếu token đã bị thu hồi ở Authorization Server nhưng Resource Server không có introspection/denylist, token vẫn có thể được chấp nhận tới khi hết hạn theo validator và leeway.

Do đó, TTL ngắn giảm cửa sổ token bị lộ; clock skew lớn làm tăng cửa sổ chấp nhận quanh thời điểm hết hạn; key rotation không tự thu hồi token nếu key cũ vẫn còn trong JWKS. Nếu cần thu hồi tức thời, cân nhắc opaque token/introspection, denylist theo jti hoặc cơ chế stateful phù hợp.

## 18. Chính sách key rotation và algorithm migration

Thuật toán và key là một phần của contract. Khi thay key hoặc algorithm, Resource Server cần có khả năng xác minh token cũ và token mới trong giai đoạn chuyển tiếp.

Quy trình rotation key cùng thuật toán:

1. Tạo key mới với kid mới.
2. Công bố public key mới trong JWKS.
3. Cập nhật Resource Server nếu thuật toán mới chưa nằm trong allowlist.
4. Chuyển Authorization Server sang ký bằng private key mới.
5. Giữ public key cũ đủ lâu cho token cũ còn hiệu lực cộng clock skew và khoảng đệm.
6. Gỡ public key cũ sau khi không còn token hợp lệ sử dụng nó.

Quy trình đổi thuật toán, ví dụ RS256 sang PS256, cần phối hợp allowlist:

- Resource Server cho phép RS256 và PS256 trong giai đoạn ngắn.
- Authorization Server bắt đầu ký token mới bằng PS256.
- Theo dõi token RS256 còn tồn tại và thời điểm hết hạn.
- Sau khi hết giai đoạn overlap, bỏ RS256 khỏi allowlist.

Không giữ thuật toán cũ vĩnh viễn. Không tái sử dụng kid cho key material khác nhau trong cùng một issuer/key set.

## 19. Bảo mật claim contract

### 19.1. Không tin claim trước khi xác minh chữ ký

JWT payload có thể được đọc trước khi xác minh chữ ký, nhưng không được dùng để cấp quyền, chọn tenant, truy vấn database hoặc gọi URL. Chỉ sử dụng claims sau khi JwtDecoder xác minh thành công.

### 19.2. Không dùng claim URL tùy ý làm endpoint

Các claim như iss, jku, x5u, tenant_url hoặc resource_uri có thể bị lợi dụng nếu ứng dụng dùng chúng để gọi network endpoint mà không có allowlist. Metadata/JWKS URI phải đến từ cấu hình hoặc registry issuer tin cậy.

### 19.3. Không nâng quyền từ claim lạ

Không ánh xạ mọi string trong roles, groups hoặc permissions thành authority. Resource Server phải có allowlist hoặc mapping rõ. Claim có tên admin không tự biến principal thành administrator.

### 19.4. Claim phải có nguồn dữ liệu xác định

| Claim | Nguồn nên dùng |
| --- | --- |
| iss | AuthorizationServerSettings/issuer configuration. |
| sub | Authenticated principal hoặc grant đã xác minh. |
| aud | Resource parameter đã được policy phê duyệt hoặc mapping scope-to-resource. |
| client_id | RegisteredClient đã authenticate. |
| scope | Scope được duyệt sau khi áp dụng client/grant/consent policy. |
| tenant_id | Tenant context đã xác thực, không lấy trực tiếp từ header tùy ý. |
| roles/permissions | Authorization service hoặc entitlement store đáng tin cậy. |

## 20. Kiểm thử hợp đồng claims, thuật toán và clock skew

Kiểm thử nên có unit test cho validator, integration test với JWT được ký thật và test vận hành cho key rotation/clock.

| Nhóm | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| Required claim | Thiếu iss, sub, aud, exp, iat, jti hoặc client_id theo contract. | invalid_token. |
| Claim type | aud là object hoặc client_id là number. | Bị từ chối. |
| Issuer | iss khác một ký tự hoặc sai path. | Bị từ chối. |
| Audience | aud không chứa API identifier. | Bị từ chối. |
| Subject | Client Credentials token bị diễn giải thành user không tồn tại. | Policy từ chối hoặc dùng service principal đúng contract. |
| Scope | Scope không có trong contract hoặc không gắn với audience. | Không cấp quyền. |
| Tenant | tenant_id không khớp issuer/tenant mapping. | Bị từ chối. |
| Token type | ID Token hoặc JWT nội bộ được gửi vào API access token. | Bị từ chối do profile/type/audience. |
| Algorithm | alg là none hoặc thuật toán ngoài allowlist. | Bị từ chối. |
| Key compatibility | RSA token được xác minh bằng EC key hoặc kid không tồn tại. | Bị từ chối. |
| Signature | Payload/header bị sửa sau khi ký. | Bị từ chối. |
| nbf boundary | Nằm trong/ngoài clock skew. | Kết quả đúng theo policy. |
| exp boundary | Token vừa hết hạn nhưng còn trong leeway. | Chấp nhận trong leeway; từ chối sau leeway. |
| iat future | Issued-at vượt allowed future skew. | Bị từ chối. |
| Maximum age | Token cũ hơn maxTokenAge. | Bị từ chối nếu policy bật. |
| Maximum TTL | Khoảng exp - iat vượt giới hạn. | Bị từ chối nếu policy bật. |
| Key rotation | Token dùng key mới sau khi JWKS cập nhật. | Được xác minh. |
| Key overlap | Token cũ còn hạn và public key cũ còn trong JWKS. | Vẫn được xác minh. |
| Algorithm migration | RS256 và PS256 trong giai đoạn overlap. | Chỉ hai thuật toán đã allowlist được chấp nhận. |
| Contract migration | Token version cũ và mới trong giai đoạn tương thích. | Hành vi theo migration policy. |
| Clock drift | Resource Server lệch đồng hồ trong/ngoài ngưỡng. | Kết quả đúng theo clock skew. |
| Missing typ | Token không có typ khi contract yêu cầu explicit typing. | Bị từ chối. |

### 20.1. Unit test cho custom validator

Tạo Jwt test bằng Jwt.withTokenValue(...), đặt header và claims theo contract. Dùng Clock.fixed(...) để test thời gian chính xác. Kiểm tra cả trường hợp hợp lệ và từng claim thiếu/sai kiểu.

Unit test validator không chứng minh chữ ký được xác minh. Nó chỉ kiểm tra policy trên một đối tượng Jwt đã được dựng sẵn.

### 20.2. Integration test với chữ ký thật

Tạo RSA/EC key pair test và ký JWT thật. Cấu hình NimbusJwtDecoder với public key/JWKS test, sau đó gửi request tới endpoint được bảo vệ.

Thử thay payload, header alg, kid, issuer, audience, timestamp và token type. Những thay đổi không hợp lệ phải bị decoder từ chối trước khi authorization policy chạy.

### 20.3. Test clock skew với thời gian cố định

Với skew 30 giây, test các điểm:

- nbf sớm hơn hiện tại 1 giây.
- nbf muộn hơn hiện tại 29 giây.
- nbf muộn hơn hiện tại 31 giây.
- exp đã qua 29 giây.
- exp đã qua 31 giây.

Điều này xác minh boundary behavior và tránh test phụ thuộc tốc độ chạy của máy.

## 21. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Token có chữ ký hợp lệ nhưng bị từ chối | Issuer/audience/required claim không khớp. | Kiểm tra claims sau khi xác minh và so sánh với contract. |
| Invalid signature | Sai key, sai kid, sai algorithm hoặc token bị sửa. | Kiểm tra JWK, signing algorithm và token source. |
| Unsupported algorithm | Resource Server không allowlist thuật toán đang ký. | Cập nhật allowlist có kiểm soát trước khi đổi signing key. |
| Invalid typ | JWT và at+jwt không thống nhất. | Xác định profile và dùng đúng type validator. |
| Missing required claim | Authorization Server chưa phát claim theo contract. | Kiểm tra grant, token customizer và schema contract. |
| Token vừa phát đã bị not before | Đồng hồ Resource Server chạy nhanh hoặc nbf sai. | Kiểm tra NTP và timestamp phát hành. |
| Token hết hạn sớm | Đồng hồ Resource Server chạy nhanh hoặc skew quá nhỏ. | Kiểm tra clock offset và policy leeway. |
| Token vẫn dùng được sau exp | Clock skew rộng hơn dự kiến. | Giảm skew phù hợp và đánh giá TTL. |
| iat tương lai nhưng token vẫn được nhận | Validator mặc định không áp policy issued-at riêng. | Thêm IssuedAtPolicyValidator nếu contract yêu cầu. |
| Token mới lỗi sau rotation | Public key mới chưa được công bố hoặc thuật toán chưa được allowlist. | Publish JWKS trước, rồi chuyển signing key. |
| Token cũ lỗi ngay sau rotation | Public key cũ bị gỡ quá sớm. | Giữ key overlap đến hết token lifetime và skew. |
| Resource Server và Authorization Server hiểu claim khác nhau | Contract không có version hoặc semantics chưa được ghi rõ. | Chuẩn hóa contract, test consumer và triển khai migration có overlap. |

## 22. Bài tập thực hành và checklist

### Bài tập 1 — Viết JWT contract

Định nghĩa claim bắt buộc/tùy chọn cho API Orders. Ghi rõ kiểu dữ liệu, semantics, issuer, audience, subject, scope, tenant và token lifetime.

### Bài tập 2 — Thêm required claims validator

Tạo validator kiểm tra iss, sub, aud, exp, iat, jti và client_id. Gửi token thiếu từng claim và xác nhận đều bị từ chối.

### Bài tập 3 — Giới hạn thuật toán

Cấu hình Resource Server chỉ nhận RS256. Ký token bằng RS256, PS256 và none; xác nhận chỉ thuật toán được allowlist được chấp nhận.

### Bài tập 4 — Thay đổi clock skew

Cấu hình skew 45 giây và dùng Clock cố định. Kiểm thử nbf/exp ở ngay trong và ngoài ranh giới.

### Bài tập 5 — Kiểm tra iat và token lifetime

Thêm IssuedAtPolicyValidator, giới hạn token age 10 phút và TTL 15 phút. Kiểm tra token phát hành trong tương lai và token có TTL vượt giới hạn.

### Bài tập 6 — Áp dụng RFC 9068

Cấu hình Authorization Server phát typ at+jwt cho access token. Cấu hình Resource Server dùng JwtValidators.createAtJwtValidator(), rồi kiểm tra ID Token không thể dùng thay access token.

### Bài tập 7 — Algorithm/key migration

Cho Resource Server hỗ trợ RS256 và PS256 trong giai đoạn chuyển đổi. Chuyển Authorization Server sang PS256, giữ key cũ trong JWKS, sau đó gỡ RS256 khi token cũ hết hạn.

### Checklist hoàn thành

- [ ] Có tài liệu JWT contract giữa Authorization Server và Resource Server.
- [ ] Required/optional claims và kiểu dữ liệu được định nghĩa.
- [ ] Semantics của sub theo grant type rõ ràng.
- [ ] iss và aud được xác minh chính xác.
- [ ] client_id, scope, jti và claim tenant có nguồn tin cậy.
- [ ] Phân biệt JWT thông thường và RFC 9068 access token profile.
- [ ] Token type được kiểm tra phù hợp với contract.
- [ ] Thuật toán ký được allowlist.
- [ ] JWK tương thích thuật toán và có kid ổn định.
- [ ] Không chấp nhận none hoặc key URL từ token.
- [ ] Clock skew nhỏ và thống nhất giữa Resource Server.
- [ ] Có kiểm tra iat/max token age nếu policy yêu cầu.
- [ ] Đồng hồ hạ tầng được đồng bộ UTC.
- [ ] Key rotation/algorithm migration có giai đoạn overlap.
- [ ] Test claim thiếu/sai kiểu, chữ ký, thuật toán và timestamp boundary.
- [ ] Không log raw JWT hoặc dữ liệu nhạy cảm trong claims.

## 23. Tài liệu tham khảo

- [Spring Security 6.5 — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html) — trusted algorithms, custom validators, RFC 9068 validation và timestamp/clock skew.
- [Spring Security 6.5 API — JwtTimestampValidator](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/JwtTimestampValidator.html) — cấu hình Duration clock skew và Clock.
- [Spring Security 6.5 API — JwtValidators](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html) — default validators và RFC 9068 builder.
- [Spring Security 6.5 API — JwtTypeValidator](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/JwtTypeValidator.html) — xác minh header typ.
- [Spring Authorization Server 1.5.8 — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html) — OAuth2TokenCustomizer, JwtEncodingContext, JwtGenerator và token claims.
- [Spring Authorization Server 1.5.8 — How-to: Add authorities as custom claims in JWT access tokens](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-custom-claims-authorities.html) — tùy biến claim cho JWT access token.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html) — claim bắt buộc, typ at+jwt, audience và validation.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html) — algorithm verification, issuer/subject, audience và cross-JWT confusion.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519.html) — registered claims và NumericDate.
- [RFC 7518 — JSON Web Algorithms](https://www.rfc-editor.org/rfc/rfc7518.html) — thuật toán JWS/JWE và key compatibility.

**Kết luận:** JWT contract phải được định nghĩa chung giữa Authorization Server và Resource Server, gồm claim semantics, kiểu dữ liệu, token type, audience, thuật toán ký và thời gian hiệu lực. Spring Security 6.5 cung cấp validator cho issuer, type, timestamp, claim và RFC 9068; Resource Server cần cấu hình allowlist thuật toán và clock skew nhỏ phù hợp với hạ tầng. Khi thay claim, key hoặc thuật toán, hãy triển khai theo giai đoạn tương thích, kiểm thử token ở ranh giới thời gian và chỉ loại bỏ contract cũ sau khi token cũ không còn hợp lệ.
