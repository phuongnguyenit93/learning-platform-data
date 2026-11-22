# Phân phối khóa ký ổn định và đồng bộ thời gian hệ thống

Khi triển khai Spring Authorization Server trên nhiều instance, mọi instance phải phát hành JWT có thể được xác minh bằng cùng một bộ khóa công khai và cùng một định danh issuer. Đồng thời, máy chủ cấp token và các Resource Server phải có đồng hồ hệ thống đủ chính xác để diễn giải thống nhất các mốc thời gian trong token. Hai yêu cầu này quyết định trực tiếp việc xác thực có ổn định sau khi scale, restart, rolling update hoặc chuyển vùng triển khai hay không.

Bài học trình bày cách quản lý khóa ký bất biến qua các replica, công bố và xoay vòng khóa bằng JWK Set, đồng bộ thời gian bằng NTP/chrony, cấu hình Spring Authorization Server và Spring Security, cùng các bước kiểm tra trước khi đưa cụm vào vận hành.

## 1. Bối cảnh và mục tiêu

Giả sử Authorization Server có ba replica sau một load balancer. Client lấy access token từ endpoint token; API phía sau được bảo vệ bởi Spring Security Resource Server. Access token có thể là JWT ký bằng khóa bất đối xứng. Resource Server tải public key từ JWKS endpoint của Authorization Server để xác minh chữ ký.

Một triển khai đúng cần giữ các bất biến sau:

1. Các replica của cùng một Authorization Server dùng cùng issuer URL chuẩn và cùng bộ khóa ký được quản lý tập trung.
2. Mọi replica công bố cùng một JWKS có thể xác minh token do bất kỳ replica nào phát hành.
3. Mỗi khóa có một kid ổn định, duy nhất trong bộ khóa và được ghi vào protected header của JWT.
4. Private key chỉ được dùng cho việc ký tại Authorization Server hoặc dịch vụ ký được ủy quyền; Resource Server chỉ cần public key.
5. Đồng hồ của các node chạy Authorization Server và Resource Server được đồng bộ với nguồn thời gian tin cậy.
6. Cấu hình clock skew của bộ xác thực token nhỏ, có chủ đích và phù hợp với sai lệch thời gian đo được.

Sơ đồ triển khai điển hình:

~~~mermaid
flowchart TB
    C[Client] --> LB[Load balancer]
    LB --> A1[Authorization Server replica 1]
    LB --> A2[Authorization Server replica 2]
    LB --> A3[Authorization Server replica 3]
    K[Key store / KMS / HSM] --> A1
    K --> A2
    K --> A3
    A1 --> J[JWKS endpoint]
    A2 --> J
    A3 --> J
    J --> R[Resource Servers]
    N[NTP sources] --> T[chronyd / time service]
    T --> A1
    T --> A2
    T --> A3
    T --> R
~~~

Khóa ký và thời gian là hai loại trạng thái hạ tầng khác nhau. Khóa xác định liệu chữ ký có thể được xác minh hay không; thời gian xác định liệu token đang nằm trong cửa sổ hiệu lực hay không. Một cụm có khóa đồng nhất nhưng đồng hồ lệch vẫn có thể từ chối token hợp lệ. Một cụm có đồng hồ chính xác nhưng từng replica dùng khóa riêng vẫn có thể tạo ra lỗi chữ ký ngẫu nhiên theo node được load balancer chọn.

## 2. Vì sao khóa ký phải ổn định giữa các replica

### 2.1. Lỗi khi sinh khóa mới mỗi lần khởi động

Ví dụ hướng dẫn tối giản của Spring Authorization Server tạo RSA key pair trong lúc ứng dụng khởi động, sau đó đưa khóa vào JWKSource. Cách này thuận tiện để chạy thử trên máy cá nhân. Trong production nhiều replica, nếu mỗi tiến trình tự sinh khóa riêng, các node sẽ có các cặp public/private key khác nhau dù cùng công bố một issuer.

Tình huống lỗi thường gặp:

- Replica A ký token bằng khóa A.
- Replica B ký token bằng khóa B.
- JWKS endpoint đi qua load balancer có lúc trả bộ public key A, có lúc trả bộ public key B.
- Resource Server có thể cache bộ khóa A rồi nhận token được ký bằng khóa B. Nếu bộ khóa trong cache chưa có B, chữ ký bị từ chối.
- Sau khi pod restart, khóa mới được sinh ra. Token còn hạn được phát hành trước lần restart có thể không còn xác minh được.

Đây là lỗi phụ thuộc vào routing và cache, nên có thể chỉ xuất hiện theo từng request hoặc sau một lần deploy. Việc tăng số replica làm xác suất gặp lỗi tăng lên.

### 2.2. Nguồn khóa dùng chung

Tạo khóa trong một quy trình provisioning có kiểm soát, sau đó lưu và cấp phát khóa cho các replica qua một cơ chế quản lý bí mật phù hợp, chẳng hạn:

- HSM hoặc dịch vụ KMS có kiểm soát quyền ký.
- Secret manager của nền tảng triển khai, với phiên bản bí mật được quản lý và phân quyền theo workload.
- Kho khóa được mã hóa, có kiểm soát truy cập, audit và quy trình backup/restore rõ ràng.

Mỗi replica phải đọc cùng phiên bản khóa đang hoạt động và cùng metadata của khóa. Nếu private key được nạp vào tiến trình, chỉ cấp quyền đọc cho service account của Authorization Server. Không đưa private key vào Git, container image, ConfigMap, log, endpoint JWKS hoặc artifact build. Không dùng mật khẩu dễ đoán để sinh khóa đối xứng.

Với hệ thống dùng khóa bất đối xứng, Authorization Server giữ quyền ký bằng private key; Resource Server chỉ tải public key để xác minh. Đây là mô hình phù hợp khi nhiều API cần xác minh token mà không được phép tự phát hành token. Chọn thuật toán chữ ký theo chính sách mật mã của tổ chức, khả năng tương thích của client và thư viện. Tất cả bên phát hành và xác minh phải thống nhất thuật toán được cho phép; không tin thuật toán do token đầu vào tự khai báo.

Nếu KMS/HSM không cho xuất private key, không thể giả định rằng có thể dựng một RSA JWK chứa private key rồi đưa thẳng vào ImmutableJWKSet. Tùy nhà cung cấp, tích hợp có thể dùng Java Cryptography Architecture provider/PKCS#11 để biểu diễn khóa dưới dạng PrivateKey handle, hoặc triển khai một JwtEncoder gọi dịch vụ ký từ xa. Sau đó cấu hình JwtGenerator/OAuth2TokenGenerator của Spring Authorization Server dùng encoder đó. Đây là phần tích hợp phụ thuộc nhà cung cấp; JWKSource tự nó không biến một HTTP KMS API thành bộ ký từ xa.

### 2.3. JWK, JWK Set và kid

JWK là biểu diễn JSON của một khóa mật mã. JWK Set là một JSON object có trường keys, chứa danh sách JWK. Với khóa RSA dùng để xác minh chữ ký, public JWK thường chứa các thông tin như:

~~~json
{
  "kty": "RSA",
  "use": "sig",
  "alg": "RS256",
  "kid": "as-signing-2026-01",
  "n": "base64url-modulus",
  "e": "AQAB"
}
~~~

Đây là ví dụ minh họa cấu trúc, không phải khóa có thể sử dụng. Public JWK không được chứa các tham số private như d, p, q, dp, dq, qi; với khóa đối xứng, không được công bố trường k.

kid là định danh khóa. JWT ký bằng một khóa thường mang kid tương ứng trong protected header. Resource Server dùng giá trị này để tìm đúng JWK trong tập khóa. Khi xoay vòng, mỗi khóa cần kid riêng; không tái sử dụng kid cho một cặp khóa mới. RFC 7517 mô tả rõ mục đích tra cứu khóa và việc dùng kid trong quá trình key rollover.

JWKS endpoint chỉ công bố public key. Resource Server cần lấy được public key hiện tại và những public key cũ còn cần thiết để xác minh token chưa hết hạn. Private key không cần và không được phân phối cho Resource Server.

## 3. Cấu hình Spring Authorization Server với nguồn khóa ổn định

### 3.1. JWKSource và JWK Set endpoint

Spring Authorization Server cấu hình JWK Set endpoint khi ứng dụng đăng ký bean JWKSource<SecurityContext>. Trong cấu hình mặc định, endpoint thường có đường dẫn /oauth2/jwks; hãy kiểm tra endpoint thực tế theo cấu hình của ứng dụng và metadata được công bố.

Ví dụ dưới đây minh họa điểm tích hợp với một bộ nạp khóa do ứng dụng triển khai. SigningKeyLoader là interface nội bộ của ví dụ, không phải API có sẵn của Spring. Phần triển khai của nó phải đọc phiên bản khóa đã được provision từ key store/KMS/HSM và trả về JWK Set dùng để ký.

~~~java
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SigningKeyConfiguration {

    @Bean
    JWKSource<SecurityContext> jwkSource(SigningKeyLoader signingKeyLoader) {
        // Bộ khóa phải được nạp từ nguồn lưu trữ dùng chung, có kiểm soát.
        // Key set có khóa private đang hoạt động và public key cần giữ
        // để xác minh các JWT đã phát hành trước đó.
        JWKSet signingJwkSet = signingKeyLoader.loadJwkSet();

        return new ImmutableJWKSet<>(signingJwkSet);
    }
}
~~~

Hợp đồng tối thiểu của adapter do ứng dụng định nghĩa có thể như sau:

~~~java
import com.nimbusds.jose.jwk.JWKSet;

public interface SigningKeyLoader {

    JWKSet loadJwkSet();
}
~~~

ImmutableJWKSet phù hợp khi ứng dụng nạp một snapshot khóa lúc khởi động. Nếu cần cập nhật khóa trong lúc tiến trình đang chạy, cần có cơ chế refresh hoặc một JWKSource động đọc phiên bản khóa hiện hành. Không nên thay file khóa trên một node rồi giả định mọi replica và cache đã nhận phiên bản mới.

Có thể khai báo issuer công khai cố định để tất cả replica công bố cùng một định danh:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .build();
}
~~~

Issuer phải là URL chuẩn mà client và Resource Server tin cậy. Không để issuer thay đổi theo hostname nội bộ, địa chỉ pod, cổng ngẫu nhiên hoặc request host không đáng tin cậy. Khi chạy sau reverse proxy/load balancer, cấu hình forwarded headers và public base URL đúng để metadata và endpoint không vô tình trả URL nội bộ.

Trong cấu hình mặc định, OAuth2AuthorizationServerConfiguration có thể cung cấp SecurityFilterChain và các endpoint giao thức. Bean JWKSource<SecurityContext> là điều kiện để JWK Set endpoint được cấu hình. Nếu dùng OpenID Connect UserInfo hoặc một số endpoint cần giải mã JWT, đăng ký JwtDecoder theo tiện ích của Spring Authorization Server:

~~~java
import com.nimbusds.jose.proc.SecurityContext;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;
import com.nimbusds.jose.jwk.source.JWKSource;

@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

Không sao chép nguyên ví dụ sinh RSA key ngẫu nhiên trong phương thức khởi động của tài liệu Getting Started sang production nhiều replica. Trong production, phần sinh khóa thuộc quy trình provisioning riêng; bean ứng dụng chỉ nạp hoặc sử dụng khóa đã được quản lý.

### 3.2. Resource Server tải public key

Khi Authorization Server công bố metadata chuẩn và JWKS endpoint, Spring Boot Resource Server có thể tự khám phá public key thông qua issuer URI:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com
~~~

issuer-uri phải khớp chính xác với claim iss trong JWT. Spring Security dùng metadata của Authorization Server để tìm JWKS URI, lấy public key và xác minh chữ ký; cấu hình mặc định cũng kiểm tra issuer và các claim thời gian exp, nbf.

Nếu Resource Server cần khởi động độc lập với trạng thái sẵn sàng của Authorization Server, có thể khai báo thêm JWKS URI:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com
          jwk-set-uri: https://auth.example.com/oauth2/jwks
~~~

Cách này bỏ bước gọi metadata để tìm JWKS URI trong quá trình khởi động, nhưng vẫn giữ issuer-uri để kiểm tra claim iss. JWKS URI phải là địa chỉ HTTPS đã được cấu hình tin cậy; không lấy URI tùy ý từ header jku hoặc x5u của token.

Nếu cùng một issuer phát hành token cho nhiều API, Resource Server cần xác minh cả aud để token chỉ được chấp nhận tại đúng API đích. Có thể dùng thuộc tính audiences của Spring Boot hoặc thêm OAuth2TokenValidator tùy yêu cầu. Kiểm tra chữ ký thành công không thay thế kiểm tra issuer, audience, thời hạn và quyền truy cập.

### 3.3. Kiểm tra cấu hình trước khi scale

Trước khi tăng replica, kiểm tra trực tiếp JWKS endpoint qua đường dẫn công khai và từng replica nếu có thể truy cập nội bộ:

~~~bash
curl -fsS https://auth.example.com/oauth2/jwks
~~~

So sánh các thuộc tính kid, kty, alg và public key material giữa các phản hồi. Có thể so sánh thumbprint của JWK để tránh phụ thuộc thứ tự phần tử JSON. Đảm bảo response chỉ chứa public key.

Một quy trình kiểm tra thực tế:

1. Gọi JWKS endpoint qua load balancer nhiều lần và qua từng replica.
2. Xác nhận mọi phản hồi có cùng tập kid và public key tương ứng.
3. Yêu cầu token nhiều lần để các replica khác nhau phát hành token.
4. Đọc protected header của từng JWT và xác nhận kid nằm trong JWKS.
5. Dùng Resource Server hoặc công cụ kiểm thử độc lập để xác minh chữ ký của token từ từng replica.
6. Restart một replica rồi lặp lại kiểm tra. kid và public key không được tự đổi chỉ vì tiến trình khởi động lại.

Trong production, theo dõi số lần xác minh JWT thất bại theo nguyên nhân. Phân biệt lỗi chữ ký, không tìm thấy kid, issuer sai, audience sai và token hết hạn. Không ghi access token hoặc private key vào log để chẩn đoán.

## 4. Xoay vòng khóa ký an toàn

Xoay khóa định kỳ giới hạn thời gian sử dụng của một khóa và giảm tác động khi khóa cần được thay thế. Tuy nhiên, xóa public key cũ quá sớm sẽ làm các token còn hạn bị từ chối. Vì vậy cần một khoảng thời gian chồng lấp giữa khóa cũ và khóa mới.

### 4.1. Quy trình xoay khóa có kế hoạch

Giả sử khóa hiện tại có kid=as-signing-2026-01, khóa mới có kid=as-signing-2026-07.

~~~mermaid
sequenceDiagram
    participant K as Key store
    participant A as Authorization Server replicas
    participant R as Resource Servers
    K->>K: Tạo khóa mới và kid mới
    K->>A: Cấp khóa mới cho bộ phát hành
    A->>R: JWKS công bố public key cũ và mới
    R->>R: Tải/cache public key mới
    A->>A: Chuyển tất cả replica sang ký bằng kid mới
    A->>R: JWT mới mang kid mới
    R->>R: Xác minh JWT bằng public key mới
    Note over A,R: Giữ public key cũ trong thời gian token cũ còn hiệu lực
    K->>A: Gỡ quyền ký bằng private key cũ
    A->>R: JWKS bỏ public key cũ sau thời gian chồng lấp
~~~

Thứ tự thực hiện:

1. **Tạo khóa mới:** tạo key pair trong KMS/HSM hoặc quy trình quản lý khóa; gán kid mới và ghi lại fingerprint, thuật toán, thời điểm tạo, phiên bản key.
2. **Phân phối public key trước:** cập nhật JWKS để chứa public key mới cùng public key cũ. Chờ mọi replica phục vụ JWKS và các cache liên quan có thể nhìn thấy khóa mới.
3. **Chuyển phát hành:** chuyển các replica sang dùng private key mới. Trong rolling update, có thể tạm thời tồn tại token ký bởi cả khóa cũ và mới; JWKS phải công bố cả hai trong giai đoạn này.
4. **Theo dõi:** xác nhận token mới mang kid mới và được mọi Resource Server xác minh thành công.
5. **Kết thúc khóa cũ:** ngừng dùng private key cũ để ký. Giữ public key cũ đến khi mọi JWT được ký bằng khóa đó đã hết hạn và hết khoảng clock skew, cache TTL cùng thời gian lan truyền cấu hình.
6. **Thu hồi:** sau thời gian chồng lấp, loại public key cũ khỏi JWKS và lưu hồ sơ khóa theo chính sách kiểm toán/khôi phục.

Thời gian giữ public key cũ tối thiểu phải bao phủ:

- Thời hạn tối đa của access token, ID token và các JWT khác được ký bằng khóa cũ.
- Clock skew mà Resource Server chấp nhận.
- Thời gian cache JWKS và chu kỳ refresh của Resource Server.
- Thời gian triển khai để tất cả replica và gateway nhận cấu hình mới.

Không có một con số cố định phù hợp với mọi hệ thống. Hãy tính từ cấu hình token thực tế, cache thực tế và thời gian rollout đo được. Nếu Resource Server cache JWKS lâu hơn dự kiến, việc xóa khóa cũ khỏi endpoint không đồng nghĩa tất cả cache đã quên khóa đó; ngược lại, một cache chưa có khóa mới có thể từ chối token mới trong giai đoạn chuyển đổi.

### 4.2. Khi khóa bị lộ

Khi có bằng chứng private key bị lộ, quy trình khẩn cấp khác với xoay khóa định kỳ:

1. Tạo khóa thay thế trong nguồn tin cậy và chuyển tất cả replica sang khóa mới.
2. Loại public key bị xâm phạm khỏi JWKS nhanh nhất có thể để Resource Server ngừng tin token ký bằng khóa đó.
3. Xác định token, client, authorization và hệ thống có thể bị ảnh hưởng; thu hồi authorization/refresh token liên quan theo khả năng của hệ thống.
4. Làm mới cache JWKS ở gateway và Resource Server theo cơ chế vận hành đã định.
5. Kiểm tra log/audit, xác định phạm vi lộ lọt và lưu bằng chứng sự cố.

Việc bỏ public key cũ sẽ khiến token hợp lệ trước đó nhưng được ký bằng khóa bị thu hồi không còn xác minh được. Đây là đánh đổi có chủ đích khi cần chặn khóa bị xâm phạm; thông báo và phối hợp với các API phụ thuộc cần nằm trong runbook sự cố.

## 5. Đồng bộ thời gian cho Authorization Server và Resource Server

### 5.1. JWT dùng thời gian UTC

RFC 7519 định nghĩa NumericDate là số giây kể từ 1970-01-01T00:00:00Z UTC, bỏ qua leap second. Các claim thời gian quan trọng gồm:

| Claim | Ý nghĩa | Cách diễn giải |
|---|---|---|
| iat | Issued At | Thời điểm token được phát hành; có thể dùng để đánh giá tuổi token |
| nbf | Not Before | Token không được chấp nhận trước mốc này |
| exp | Expiration Time | Token không được chấp nhận từ mốc này trở đi |

Với exp, thời điểm hiện tại phải nhỏ hơn thời điểm hết hạn. Với nbf, thời điểm hiện tại phải bằng hoặc sau mốc bắt đầu hiệu lực. RFC cho phép một khoảng dung sai nhỏ để bù sai lệch đồng hồ. Không nên biến khoảng dung sai này thành nhiều phút hoặc nhiều giờ để che giấu hạ tầng thời gian không ổn định.

iat cho biết thời điểm phát hành và có thể hỗ trợ kiểm tra tuổi token. Không nên tự coi iat là nbf: hai claim có ngữ nghĩa khác nhau. Nếu nghiệp vụ cần giới hạn tuổi token, hãy thiết kế validator riêng theo yêu cầu và tương thích với quy tắc JWT.

Đặt timezone của máy chủ thành UTC giúp log, lịch vận hành và điều tra sự cố nhất quán, nhưng thay đổi timezone không đồng bộ đồng hồ. NTP điều chỉnh đồng hồ hệ thống; UTC là cách biểu diễn thời gian chuẩn.

### 5.2. Hậu quả khi đồng hồ lệch

Ví dụ Authorization Server phát hành token với nbf=10:00:00Z, exp=10:05:00Z.

- Nếu đồng hồ Resource Server chạy nhanh 90 giây, token có thể bị coi là hết hạn sớm.
- Nếu đồng hồ Resource Server chạy chậm 90 giây, token có thể được chấp nhận sau thời điểm exp theo thời gian thực; clock skew cấu hình thêm có thể kéo dài khoảng này.
- Nếu đồng hồ Authorization Server chạy chậm, token mới có thể mang iat/nbf nằm trong quá khứ so với thời gian thực; khi chạy nhanh, token có thể chưa đến nbf theo đồng hồ của Resource Server.
- Sai lệch thời gian còn làm log giữa các service khó đối chiếu, ảnh hưởng audit, chứng thư TLS, lịch refresh và tác vụ hết hạn.

Clock skew là biện pháp dung sai ở lớp xác minh token. Nó không sửa đồng hồ hệ điều hành và không thay thế NTP.

### 5.3. Đồng bộ bằng NTP và chrony

Trên Linux, chronyd đồng bộ đồng hồ hệ thống với một hoặc nhiều nguồn NTP. Tài liệu chrony khuyến nghị tối thiểu ba nguồn thời gian để tăng khả năng nhận diện nguồn sai và duy trì độ tin cậy. Trong mạng nội bộ, có thể dùng các NTP server do tổ chức quản lý; các node nên tuân theo cùng chính sách nguồn thời gian.

Ví dụ cấu hình minh họa trong /etc/chrony/chrony.conf:

~~~conf
server ntp1.example.net iburst
server ntp2.example.net iburst
server ntp3.example.net iburst

driftfile /var/lib/chrony/drift
makestep 1 3
rtcsync
~~~

Ý nghĩa:

- server khai báo nguồn NTP; có thể dùng pool nếu tên DNS trả về nhiều máy chủ.
- iburst tăng tốc đồng bộ ban đầu.
- driftfile lưu ước lượng sai số tần số đồng hồ để chrony khởi động ổn định hơn.
- makestep 1 3 cho phép điều chỉnh nhảy đồng hồ khi sai lệch vượt ngưỡng trong ba lần cập nhật đầu. Điều chỉnh nhảy thời gian có thể tác động tới tiến trình đang chạy, nên cấu hình ngưỡng và thời điểm áp dụng phù hợp với chính sách vận hành.
- rtcsync giúp đồng hồ phần cứng RTC được cập nhật từ đồng hồ hệ thống trên nền tảng hỗ trợ.

Dùng các lệnh sau để kiểm tra trạng thái:

~~~bash
# Trạng thái đồng bộ của hệ điều hành
timedatectl status

# Độ lệch giữa system clock và nguồn thời gian được chọn
chronyc tracking

# Danh sách nguồn, nguồn đang được chọn và khả năng truy cập
chronyc sources -v

# Thống kê chất lượng các nguồn thời gian
chronyc sourcestats
~~~

Trong kết quả chronyc sources -v, dấu * thường chỉ nguồn đang được chọn; dấu + chỉ nguồn được kết hợp. Theo dõi các trường như Reach, LastRx, Last sample, offset và root dispersion. Nếu Reach bằng 0, máy không nhận được phản hồi hợp lệ từ nguồn tương ứng; kiểm tra DNS, firewall và UDP port 123.

Trên Windows Server, dùng Windows Time Service và kiểm tra bằng:

~~~powershell
w32tm /query /status
w32tm /query /source
~~~

Không cấu hình nhiều dịch vụ cùng điều khiển system clock trên một host nếu chưa có thiết kế rõ ràng. Hãy để một dịch vụ đồng bộ thời gian được chọn và giám sát.

### 5.4. Node, container và Kubernetes

Trong triển khai container thông thường, container sử dụng đồng hồ realtime của kernel trên node host. Vì vậy, đồng bộ thời gian cần được cấu hình và giám sát ở cấp máy chủ/worker node. Không nên chỉ cài một NTP client trong image ứng dụng rồi cho rằng mọi pod đã được đồng bộ.

Các bước kiểm tra:

1. Xác nhận tất cả worker node dùng cùng nhóm NTP nguồn tin cậy.
2. Theo dõi clock offset và trạng thái đồng bộ của từng node.
3. Đảm bảo node mới được đồng bộ trước khi nhận workload phát hành hoặc xác minh JWT.
4. Kiểm tra lại sau khi VM resume, node reboot, thay đổi mạng hoặc mất kết nối NTP.
5. Đặt cảnh báo khi nguồn thời gian mất liên lạc hoặc offset vượt ngưỡng vận hành.

Nếu một nền tảng dùng time namespace hoặc cơ chế ảo hóa thời gian đặc biệt, kiểm tra hành vi thực tế của môi trường thay vì giả định mọi container đều nhìn cùng một clock.

## 6. Cấu hình clock skew trong Spring Security

Spring Security Resource Server sử dụng JwtTimestampValidator để kiểm tra cửa sổ hiệu lực dựa trên exp và nbf. Tài liệu hiện hành mô tả clock skew mặc định là 60 giây. Có thể đặt dung sai tường minh khi yêu cầu vận hành cần giá trị khác.

Ví dụ cấu hình servlet Resource Server dùng issuer discovery và dung sai 30 giây:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
JwtDecoder jwtDecoder() {
    String issuerUri = "https://auth.example.com";

    NimbusJwtDecoder decoder =
            (NimbusJwtDecoder) JwtDecoders.fromIssuerLocation(issuerUri);

    OAuth2TokenValidator<Jwt> validator =
            new DelegatingOAuth2TokenValidator<>(
                    new JwtIssuerValidator(issuerUri),
                    new JwtTimestampValidator(Duration.ofSeconds(30))
            );

    decoder.setJwtValidator(validator);
    return decoder;
}
~~~

Đây là cấu hình minh họa khi cần tự tạo JwtDecoder. Nếu đã dùng cấu hình Spring Boot với issuer-uri và không cần tùy chỉnh validator, có thể giữ auto-configuration. Khi tự khai báo JwtDecoder, cần bảo đảm validator vẫn kiểm tra đầy đủ issuer, thời gian, audience và các điều kiện riêng của ứng dụng; không vô tình thay toàn bộ validator mặc định bằng một validator chỉ kiểm tra thời gian.

Dung sai 30 giây trong ví dụ là giá trị minh họa, không phải khuyến nghị cố định. Chọn giá trị dựa trên số liệu offset thực tế giữa các node và yêu cầu bảo mật. Nếu phải tăng clock skew liên tục để request thành công, cần xử lý nguyên nhân đồng hồ lệch.

Có thể dùng JwtTimestampValidator#setClock để kiểm thử logic với một clock cố định, giúp test không phụ thuộc thời gian thật:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

JwtTimestampValidator validator =
        new JwtTimestampValidator(Duration.ofSeconds(30));

validator.setClock(
        Clock.fixed(
                Instant.parse("2026-11-16T10:00:00Z"),
                ZoneOffset.UTC
        )
);
~~~

Clock cố định chỉ dành cho test hoặc logic cần kiểm soát thời gian. Không đặt clock giả lập trong cấu hình production.

Với nghiệp vụ đo thời lượng trong cùng một tiến trình, chẳng hạn timeout hoặc thời gian xử lý request, dùng clock đơn điệu như System.nanoTime() thay cho phép trừ hai mốc Instant. Đồng hồ wall-clock có thể được NTP điều chỉnh; clock đơn điệu phù hợp hơn để đo khoảng thời gian trôi qua.

## 7. Giám sát và xử lý sự cố

### 7.1. Chỉ số cần theo dõi

| Nhóm | Chỉ số hoặc sự kiện | Ý nghĩa |
|---|---|---|
| Khóa ký | kid đang ký trên từng replica | Phát hiện node dùng nhầm phiên bản khóa |
| JWKS | Tập kid, fingerprint public key, thời điểm cập nhật | Phát hiện JWKS không đồng nhất hoặc cập nhật chậm |
| Xác minh JWT | Lỗi signature, unknown kid, issuer/audience mismatch | Phân biệt lỗi phân phối khóa với lỗi cấu hình token |
| Thời gian | Clock offset, root dispersion, nguồn NTP đang chọn | Phát hiện node mất đồng bộ |
| Nền tảng | Node reboot, VM resume, NTP source unreachable | Tìm nguyên nhân làm đồng hồ lệch |
| Token | Tỷ lệ lỗi expired và not-before | Phát hiện sự cố thời gian hoặc cấu hình TTL |

Không log giá trị token, private key hoặc secret của KMS. Với lỗi xác minh, log loại lỗi, issuer đã cấu hình, kid đã được làm sạch và request correlation ID theo chính sách bảo mật.

### 7.2. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Lỗi chữ ký chỉ xuất hiện khi tải tăng | Replica ký bằng các khóa khác nhau | So sánh JWKS và kid theo từng replica |
| Token mới có kid nhưng Resource Server báo không tìm thấy khóa | JWKS/cache chưa cập nhật | Kiểm tra endpoint, cache TTL và cơ chế refresh |
| Token còn hạn nhưng báo expired | Đồng hồ Resource Server chạy nhanh hoặc exp sai | Kiểm tra chronyc tracking, exp và clock skew |
| Token mới báo chưa đến thời điểm hiệu lực | Đồng hồ phát hành/kiểm tra lệch hoặc nbf được đặt sai | So sánh UTC trên các node và claim nbf |
| Lỗi xuất hiện sau restart | Ứng dụng sinh khóa mới khi khởi động | Nạp khóa đã provision từ nguồn ổn định |
| Chỉ một API từ chối token | Audience hoặc cấu hình issuer của API không đúng | Kiểm tra iss, aud, metadata và validator |

### 7.3. Runbook kiểm tra sau deploy

Sau mỗi lần rollout Authorization Server hoặc thay đổi key set:

1. Kiểm tra các replica đã sẵn sàng và cùng dùng một issuer.
2. Lấy JWKS qua load balancer và từng replica; so sánh kid và public key fingerprint.
3. Phát hành token qua từng replica nếu có thể định tuyến riêng; xác nhận header kid.
4. Xác minh từng token bằng Resource Server đại diện cho các vùng triển khai.
5. Kiểm tra clock offset trên node của Authorization Server và Resource Server.
6. Xác nhận log không có đột biến lỗi signature, unknown kid, expired hoặc not-before.
7. Lưu phiên bản khóa, fingerprint, thời gian rollout và kết quả kiểm tra vào audit record.

Nếu deploy có thay đổi key, thực hiện thêm bước kiểm tra thời gian chồng lấp và khả năng xác minh token cũ trước khi gỡ public key cũ.

## 8. Checklist vận hành

- [ ] Tất cả replica dùng một issuer URL công khai, ổn định.
- [ ] Khóa ký được provision và lưu trong KMS/HSM/secret manager hoặc kho khóa có kiểm soát.
- [ ] Restart replica không sinh ra một khóa ký mới ngoài kế hoạch.
- [ ] Mỗi khóa có kid riêng và thuật toán được allow-list rõ ràng.
- [ ] JWK Set endpoint chỉ công bố public key.
- [ ] JWKS của mọi replica có cùng tập khóa cần thiết.
- [ ] Resource Server xác minh chữ ký, issuer, audience và thời gian.
- [ ] Quy trình xoay khóa công bố public key mới trước khi chuyển ký.
- [ ] Public key cũ được giữ đủ lâu cho token còn hạn và cache JWKS.
- [ ] Tất cả node dùng nguồn NTP tin cậy và có giám sát clock offset.
- [ ] Clock skew được đặt tường minh theo số liệu và giữ ở mức nhỏ.
- [ ] Runbook có bước xử lý khi private key bị lộ hoặc node mất đồng bộ thời gian.

## 9. Tài liệu tham khảo

1. [Spring Authorization Server — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html): cấu hình JWKSource, JwtDecoder và ví dụ khóa RSA.
2. [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): các endpoint mặc định và điều kiện đăng ký JWK Set endpoint.
3. [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer discovery, JWKS URI, xác minh JWT và tùy chỉnh validator.
4. [Spring Security API — JwtTimestampValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtTimestampValidator.html): cấu hình clock skew và clock dùng khi kiểm tra timestamp.
5. [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK Set, public/private key material và kid trong key rollover.
6. [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): NumericDate và các claim exp, nbf, iat.
7. [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh thuật toán, issuer, audience và xử lý các header/claim không đáng tin cậy.
8. [chrony — Frequently Asked Questions](https://chrony-project.org/faq.html): cấu hình NTP client, số lượng nguồn thời gian và chẩn đoán đồng bộ đồng hồ.


