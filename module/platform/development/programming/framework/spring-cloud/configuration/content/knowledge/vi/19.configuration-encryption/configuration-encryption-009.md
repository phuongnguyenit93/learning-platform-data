# Giữ khóa giải mã ngoài repository và kiểm soát endpoint mật mã

Spring Cloud Config có thể lưu giá trị cấu hình nhạy cảm trong Git dưới dạng ciphertext với tiền tố `{cipher}`. Khi Config Server đọc repository, server dùng khóa mật mã được cấu hình riêng để giải mã giá trị trước khi trả Environment cho Config Client. Cách làm này giúp tránh lưu password hoặc token ở dạng rõ trong repository, nhưng chỉ an toàn khi khóa giải mã được quản lý tách biệt và các endpoint `/encrypt`, `/decrypt` được bảo vệ đúng mức.

Khóa giải mã không được commit cùng repository cấu hình, đóng gói vào JAR hoặc đưa vào image container. Người có quyền đọc Git chỉ nên nhìn thấy ciphertext; quyền truy cập khóa và endpoint giải mã cần được cấp riêng cho Config Server và nhóm vận hành có nhiệm vụ phù hợp. Khi ciphertext được giải mã để gửi đến client, kết nối Config Server–Client vẫn phải dùng TLS và client phải được bảo vệ như một workload có quyền nhận secret.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích cách `{cipher}` được xử lý trong Config Server.
- Phân biệt khóa đối xứng và keystore bất đối xứng.
- Đặt khóa giải mã ngoài Git repository và artifact triển khai.
- Cấu hình khóa bằng secret store, biến môi trường hoặc file được mount an toàn.
- Bảo vệ endpoint `POST /encrypt` và `POST /decrypt` bằng xác thực, phân quyền và TLS.
- Phân biệt mã hóa dữ liệu lưu trữ với bảo vệ dữ liệu trên đường truyền.
- Xây dựng quy trình xoay vòng khóa, kiểm tra lỗi giải mã và thu hồi quyền truy cập.

## 1. Mô hình mã hóa cấu hình của Spring Cloud Config

Giả sử repository cấu hình cần lưu password database. Thay vì commit password dạng rõ, người vận hành gửi giá trị đến endpoint mã hóa của Config Server. Server trả ciphertext; ciphertext được lưu trong YAML hoặc properties với tiền tố `{cipher}`.

Khi Config Client yêu cầu cấu hình, Config Server đọc ciphertext, giải mã bằng khóa riêng của server và trả giá trị đã giải mã trong Environment response. Client nhận giá trị cấu hình cần dùng mà không cần biết khóa giải mã của Config Server.

```mermaid
flowchart TD
    A[Secret plaintext] --> B[POST /encrypt]
    B --> C[Config Server dùng key material]
    C --> D[Ciphertext]
    D --> E[Git config repository với {cipher}]
    E --> F[Config Server đọc repository]
    F --> G[Giải mã bằng khóa được cấp ngoài Git]
    G --> H[Environment response qua TLS]
    H --> I[Config Client]
```

Các ranh giới cần giữ rõ:

| Thành phần | Chứa gì | Ai cần quyền |
|---|---|---|
| Git repository | Ciphertext và cấu hình không nhạy cảm | Nhóm quản lý cấu hình theo quyền repository. |
| Khóa hoặc private key | Vật liệu giải mã | Chỉ Config Server và quy trình vận hành được ủy quyền. |
| `/encrypt` | Nhận plaintext và trả ciphertext | Nhóm/pipeline được phép mã hóa cấu hình. |
| `/decrypt` | Nhận ciphertext và trả plaintext | Quyền rất hạn chế; chỉ công cụ vận hành được phê duyệt khi thực sự cần. |
| Config Client | Giá trị đã giải mã cần cho ứng dụng | Chỉ workload có nhu cầu sử dụng secret. |

Mã hóa `{cipher}` bảo vệ giá trị khi lưu trong repository. Sau khi Config Server giải mã, secret vẫn cần được bảo vệ trong response, bộ nhớ, log, trace, heap dump và các hệ thống quan sát.

## 2. Chuẩn bị dependency và Config Server

Các tính năng mã hóa/giải mã của Spring Cloud Config dựa trên thư viện Spring Security RSA. Kiểm tra dependency graph của Config Server và bổ sung dependency tương thích nếu phiên bản đang dùng chưa có sẵn qua các dependency hiện tại. Để Spring Cloud BOM quản lý phiên bản tương thích thay vì tự chọn một phiên bản ngẫu nhiên.

Ví dụ Maven:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-rsa</artifactId>
</dependency>
```

Config Server cũng cần dependency `spring-cloud-config-server` và được bật bằng `@EnableConfigServer`. Các ví dụ trong bài giả định ứng dụng đã được cấu hình Config Server và có backend repository hoạt động.

Chỉ bật cơ chế mã hóa khi quy trình cấp, lưu, backup và xoay vòng khóa đã được xác định. Một endpoint `/encrypt` hoạt động không chứng minh khóa được bảo vệ đúng cách.

## 3. Dùng khóa đối xứng bên ngoài repository

Với khóa đối xứng, cùng một secret key được dùng để mã hóa và giải mã. Config Server nhận khóa qua thuộc tính `encrypt.key`:

```yaml
encrypt:
  key: ${CONFIG_ENCRYPT_KEY}
```

Biến `CONFIG_ENCRYPT_KEY` phải được cấp từ secret manager hoặc nền tảng triển khai. Không đặt giá trị thật trực tiếp trong `application.yml` được commit, repository cấu hình Git, Dockerfile, image container hoặc script dùng chung.

Có thể dùng biến môi trường `ENCRYPT_KEY` theo quy tắc relaxed binding của Spring Boot để cấp thuộc tính `encrypt.key`. Ví dụ khai báo ở trên dùng tên `CONFIG_ENCRYPT_KEY` làm placeholder rõ nghĩa; nền tảng phải cấp biến này trước khi Config Server khởi động.

### Ưu điểm và giới hạn

| Đặc điểm | Khóa đối xứng |
|---|---|
| Cách dùng | Một khóa dùng cho cả mã hóa và giải mã. |
| Triển khai | Đơn giản, phù hợp môi trường nhỏ hoặc pipeline được kiểm soát. |
| Phân phối khóa | Bất kỳ nơi nào có khóa đều có khả năng giải mã và thường cũng có thể mã hóa. |
| Rủi ro | Khóa bị lộ làm ảnh hưởng toàn bộ ciphertext được bảo vệ bằng khóa đó. |
| Xoay vòng | Cần mã hóa lại ciphertext bằng khóa mới và phối hợp thời điểm chuyển khóa. |

Không dùng cùng một khóa đối xứng cho nhiều môi trường nếu các môi trường cần ranh giới bảo mật riêng. Tách khóa local, test, staging và production giúp giới hạn tác động khi một môi trường bị xâm nhập.

## 4. Dùng keystore bất đối xứng

Với cơ chế bất đối xứng, bên mã hóa sử dụng public key, còn Config Server giữ private key để giải mã. Public key có thể được phân phối cho pipeline hoặc nhóm tạo ciphertext; private key phải được giữ kín tại phía server.

Config Server có thể đọc key pair từ keystore. Ví dụ dùng một keystore PKCS12 được mount từ secret volume:

```yaml
encrypt:
  key-store:
    location: file:/run/secrets/config-server-keystore.p12
    password: ${CONFIG_ENCRYPT_KEYSTORE_PASSWORD}
    alias: config-server
    secret: ${CONFIG_ENCRYPT_PRIVATE_KEY_PASSWORD}
```

Ý nghĩa các thuộc tính:

| Thuộc tính | Ý nghĩa |
|---|---|
| `location` | Đường dẫn hoặc resource URL đến keystore. |
| `password` | Mật khẩu mở keystore. |
| `alias` | Alias của key pair cần sử dụng. |
| `secret` | Mật khẩu bảo vệ private key entry. |

Đường dẫn `file:/run/secrets/...` là ví dụ về file được mount vào container. Quyền filesystem nên giới hạn để chỉ user chạy Config Server đọc được. Không đặt keystore trong Git repository, thư mục static được phục vụ qua HTTP hoặc image dùng chung cho nhiều ứng dụng.

Keystore bất đối xứng giúp tách quyền tạo ciphertext khỏi quyền giải mã: pipeline có thể chỉ cần public key, trong khi private key ở Config Server. Tuy nhiên, nếu dùng endpoint `/encrypt` trên chính Config Server, caller vẫn cần quyền gọi endpoint đó; mô hình public-key riêng cho pipeline cần được thiết kế và kiểm thử theo công cụ mã hóa được sử dụng.

## 5. Cấp khóa từ secret store hoặc nền tảng triển khai

Có một số cách cấp key material cho Config Server:

| Cách cấp | Phù hợp khi | Kiểm soát cần có |
|---|---|---|
| Secret manager/Vault | Tổ chức đã có hệ thống quản lý secret tập trung | Workload identity, policy đọc secret, audit và rotation. |
| File secret được mount | Nền tảng container/orchestrator hỗ trợ secret volume | Quyền file tối thiểu, không mount vào container không liên quan. |
| Environment variable | Cấu hình triển khai đơn giản hoặc tích hợp nền tảng hiện có | Không in environment, hạn chế quyền inspect process/container và dùng secret injection an toàn. |
| HSM/KMS qua tích hợp riêng | Có yêu cầu quản lý khóa phần cứng hoặc dịch vụ khóa tập trung | Dùng provider/integration đã được hỗ trợ và xác minh key lifecycle. |

Spring Cloud Config không tự động biến một chuỗi `encrypt.key` thành khóa nằm trong HSM/KMS. Nếu cần HSM/KMS, phải có tích hợp mật mã tương thích hoặc một dịch vụ quản lý khóa chuyên dụng; không chỉ khai báo một URL KMS vào `encrypt.key`.

Với environment variable, tránh in `env`, `printenv`, dump toàn bộ cấu hình hoặc bật debug log chứa giá trị secret. Với file mount, kiểm tra quyền đọc và backup. Với secret manager, cấp quyền theo workload identity và ghi nhận lần truy cập trong audit log.

## 6. Mã hóa một giá trị qua endpoint /encrypt

Config Server cung cấp endpoint mã hóa nhận plaintext qua HTTP POST. Ví dụ minh họa với giá trị giả:

```bash
curl --fail-with-body -X POST \
  -H "Content-Type: text/plain" \
  --data-binary 'example-password-for-demo' \
  https://config.example.internal/encrypt
```

Response là ciphertext. Khi đưa vào repository, thêm tiền tố `{cipher}` trước ciphertext:

```yaml
spring:
  datasource:
    password: "{cipher}AQB-example-ciphertext"
```

Ciphertext trong ví dụ là chuỗi minh họa, không dùng được để giải mã. Khi mã hóa secret thật, không đặt plaintext trực tiếp vào shell history hoặc log pipeline. Dùng input được cấp an toàn từ secret manager, stdin hoặc một bước xử lý bảo mật của pipeline.

Endpoint mã hóa chỉ tạo ciphertext. Nó không tự commit giá trị vào Git, không tự cập nhật Config Server repository và không tự refresh client. Người vận hành cần đưa ciphertext vào đúng file cấu hình, review thay đổi và phát hành theo quy trình quản lý cấu hình.

## 7. Giải mã qua endpoint /decrypt

Endpoint `POST /decrypt` nhận ciphertext và trả plaintext. Đây là endpoint đặc biệt nhạy cảm vì người gọi có thể lấy được giá trị gốc nếu có ciphertext hợp lệ và server có khóa.

Ví dụ minh họa:

```bash
curl --fail-with-body -X POST \
  -H "Content-Type: text/plain" \
  --data-binary 'AQB-example-ciphertext' \
  https://config.example.internal/decrypt
```

Không dùng endpoint này như một công cụ tra cứu chung cho mọi developer. Nếu cần kiểm tra, nên dùng một quy trình break-glass có phê duyệt, ghi nhận người gọi và giới hạn thời gian/quyền truy cập. Trong vận hành thường ngày, Config Server giải mã tự động khi tạo Environment cho client nên không cần người dùng gọi `/decrypt` thủ công.

## 8. Đặt endpoint mã hóa trong vùng quản trị

Endpoint `/encrypt` và đặc biệt `/decrypt` không nên được expose công khai. Cần áp dụng đồng thời:

- HTTPS/TLS từ caller đến Config Server.
- Xác thực người gọi bằng OAuth2/JWT, mTLS hoặc cơ chế doanh nghiệp phù hợp.
- Phân quyền riêng cho mã hóa và giải mã; không cấp quyền decrypt cho pipeline chỉ cần encrypt.
- Network policy hoặc management gateway giới hạn nguồn truy cập.
- Rate limit và audit log cho các thao tác nhạy cảm.
- Không ghi request body hoặc response plaintext vào access log, trace hay error log.
- Không bật CORS rộng hoặc để endpoint truy cập trực tiếp từ trình duyệt người dùng.

Ví dụ quy tắc phân quyền Spring Security 6 cho hai endpoint:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CryptoEndpointSecurity {

    @Bean
    SecurityFilterChain configServerSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.POST, "/encrypt")
                    .hasAuthority("SCOPE_config:encrypt")
                .requestMatchers(HttpMethod.POST, "/decrypt")
                    .hasAuthority("SCOPE_config:decrypt")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .csrf(csrf -> csrf.ignoringRequestMatchers("/encrypt", "/decrypt"))
            .build();
    }
}
```

Ví dụ minh họa việc phân quyền theo scope; ứng dụng phải cấu hình issuer/JWK hoặc JWT decoder và các security chain khác. Chain này dùng bearer token stateless được gửi tường minh trong Authorization header, vì vậy chỉ loại trừ hai endpoint mật mã khỏi CSRF protection. Chỉ áp dụng khi không dùng cookie/session tự động. Nếu trình duyệt gửi credential bằng cookie, giữ CSRF protection và yêu cầu CSRF token. Không tắt CSRF toàn ứng dụng.

Nếu tổ chức không cần endpoint decrypt trực tiếp, có thể chặn quyền truy cập endpoint này ở security layer hoặc gateway. Hãy kiểm tra các endpoint thực sự được đăng ký trong phiên bản Spring Cloud Config đang chạy.

## 9. Config Server giải mã `{cipher}` trước khi trả client

Ví dụ repository cấu hình:

```yaml
spring:
  datasource:
    username: catalog_app
    password: "{cipher}AQB-example-ciphertext"
```

Khi Config Client yêu cầu Environment, Config Server nhận diện tiền tố `{cipher}`, dùng key material của server để giải mã và trả giá trị đã giải mã trong property source cho client. Config Client thông thường không cần giữ khóa giải mã của Config Server.

Điều này tạo ra một ranh giới rõ: Git chỉ chứa ciphertext, Config Server có quyền giải mã, còn Config Client nhận secret cần cho workload. Vì client nhận giá trị rõ, phải bảo vệ đường truyền bằng TLS và hạn chế quyền truy cập response theo danh tính ứng dụng.

Nếu server không có khóa phù hợp hoặc ciphertext không hợp lệ, quá trình giải mã có thể thất bại. Khi đó, không được giả định giá trị trả về là plaintext hợp lệ. Kiểm tra log Config Server, key version, định dạng ciphertext và response Environment; tránh in nội dung nhạy cảm trong log để chẩn đoán.

## 10. Không nhầm mã hóa với TLS hoặc masking

Các cơ chế dưới đây giải quyết những rủi ro khác nhau:

| Cơ chế | Bảo vệ điều gì | Không giải quyết điều gì |
|---|---|---|
| `{cipher}` trong Git | Giá trị cấu hình khi lưu trong repository | Không bảo vệ plaintext sau khi Config Server giải mã. |
| HTTPS/TLS | Dữ liệu khi truyền giữa caller, Config Server và Config Client | Không bảo vệ secret đã lưu ở dạng rõ trong Git hoặc log. |
| Secret masking trong CI | Giảm khả năng lộ giá trị trong log pipeline | Không mã hóa dữ liệu trong Git hoặc broker. |
| Actuator sanitization | Hạn chế hiển thị giá trị qua endpoint chẩn đoán | Không thay thế phân quyền và bảo vệ key material. |
| Git access control | Giới hạn ai đọc/ghi repository | Không thay thế mã hóa và quản lý khóa. |

Một cấu hình an toàn cần phối hợp các lớp trên. Ciphertext có thể được đọc bởi nhiều người có quyền Git, nhưng chỉ Config Server được phép giải mã; response đã giải mã chỉ được gửi qua TLS đến client hợp lệ.

## 11. Xử lý lỗi mã hóa và giải mã

Các lỗi thường gặp:

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `/encrypt` trả lỗi | Thiếu key material, thiếu dependency hoặc endpoint bị security chặn | Kiểm tra dependency, key injection và quyền `config:encrypt`. |
| `/decrypt` trả lỗi | Ciphertext sai, dùng sai khóa hoặc private key/alias không khớp | Kiểm tra key version, alias và định dạng ciphertext trong môi trường bảo mật. |
| Client nhận giá trị không dùng được | Server không giải mã thành công hoặc property chưa có tiền tố đúng | Kiểm tra Environment response và log server, không ghi plaintext. |
| Server khởi động nhưng không đọc được keystore | Sai đường dẫn, quyền file hoặc mật khẩu keystore/private key | Kiểm tra mount, file permission và secret injection. |
| Một số Config Server replica giải mã được, số khác không | Các replica đang dùng key version khác nhau | So sánh key version/alias đã triển khai và rollout đồng bộ. |
| Secret mới bị lộ trong log | HTTP body, exception hoặc debug logging ghi plaintext | Tắt body logging, mask dữ liệu và kiểm soát tracing. |

Trong môi trường nhiều Config Server replica, tất cả instance phục vụ cùng ciphertext phải có key material tương thích. Nếu một replica dùng key cũ và replica khác dùng key mới, cùng một request có thể thành công hoặc thất bại tùy instance nhận request.

## 12. Xoay vòng khóa mã hóa

Khóa mã hóa cần có vòng đời: tạo, cấp, sử dụng, backup, xoay vòng và thu hồi. Không nên giữ một khóa cố định vô thời hạn hoặc thay khóa đột ngột mà chưa mã hóa lại ciphertext.

Với một Config Server chỉ cấu hình một khóa hoạt động, kế hoạch xoay vòng cần phối hợp ciphertext và key deployment. Nếu không có cơ chế dual-key đã kiểm thử, hãy thực hiện trong cửa sổ bảo trì để client không yêu cầu cấu hình trong lúc server và repository đang chuyển đổi:

1. Xác định phạm vi ciphertext đang được mã hóa bằng khóa cũ; lập danh sách property và repository liên quan.
2. Tạo khóa mới trong secret manager hoặc tạo key pair mới trong quy trình được kiểm soát.
3. Dùng quy trình bảo mật để giải mã giá trị cũ và mã hóa lại bằng khóa mới. Không lưu plaintext vào file tạm không bảo vệ hoặc log.
4. Commit ciphertext mới vào một revision/label riêng đã được review; giữ nguyên revision cũ để rollback theo chính sách.
5. Tạm dừng các lần refresh/client bootstrap và chuyển Config Server vào cửa sổ bảo trì nếu server chỉ hỗ trợ một khóa hoạt động.
6. Cập nhật key material của tất cả Config Server replica, xác nhận cùng key version và kiểm tra giải mã ciphertext mới.
7. Chuyển client sang revision chứa ciphertext mới, khôi phục traffic và xác minh Environment response trước khi kết thúc bảo trì.
8. Thu hồi khóa cũ sau khi xác nhận không còn revision hoặc backup cần được giải mã bằng khóa đó, theo chính sách lưu trữ của tổ chức.

Nếu cần phục vụ đồng thời ciphertext cũ và mới trong quá trình chuyển đổi mà không có cửa sổ bảo trì, phải có thiết kế hỗ trợ nhiều khóa hoặc một lớp giải mã tương thích đã được kiểm thử. Không giả định cấu hình một `encrypt.key` hoặc một keystore alias tự động hỗ trợ key ring nhiều phiên bản. Trong rollout thông thường, server mới dùng khóa mới có thể không giải mã được ciphertext cũ, vì vậy không để các request tiếp tục đi vào server đang chuyển khóa khi repository vẫn phục vụ ciphertext cũ.

Với keystore bất đối xứng, có thể phân phối public key mới cho bên mã hóa trước, nhưng Config Server vẫn phải giữ private key tương ứng với ciphertext đang phục vụ. Lập kế hoạch để server không nhận ciphertext mới trước khi đã có private key phù hợp.

## 13. Backup và thu hồi key material

Backup keystore hoặc symmetric key cũng nhạy cảm như bản đang dùng. Nếu backup được lưu ở cùng nơi với Git repository hoặc cùng quyền truy cập với ciphertext, kẻ tấn công có thể lấy cả dữ liệu lẫn khóa.

- Mã hóa backup bằng một khóa bảo vệ độc lập và lưu ở kho backup có ACL riêng.
- Giới hạn người có thể export private key hoặc secret đối xứng.
- Kiểm tra khả năng restore trong môi trường cô lập, không dùng secret production trên máy cá nhân.
- Ghi nhận key identifier/version, thời điểm tạo, mục đích và thời điểm thu hồi; không ghi giá trị khóa.
- Khi nghi ngờ khóa bị lộ, lập tức đánh giá phạm vi ciphertext, rotate key và thay các secret gốc nếu cần.
- Xóa hoặc thu hồi bản sao không còn được phép sử dụng theo chính sách lưu trữ và pháp lý của tổ chức.

Đối với private key, ưu tiên giữ quyền export ở mức thấp nhất. Nếu hạ tầng hỗ trợ HSM hoặc dịch vụ khóa chuyên dụng qua integration đã được kiểm chứng, cân nhắc dùng để hạn chế việc private key xuất hiện dưới dạng file thông thường.

## 14. Kiểm thử và vận hành an toàn

Trước khi triển khai, kiểm thử cả đường mã hóa, giải mã và phân quyền:

1. Xác nhận Config Server lấy được key material từ nguồn bên ngoài repository.
2. Gọi `/encrypt` với một giá trị thử không nhạy cảm và xác nhận response là ciphertext.
3. Đặt ciphertext với tiền tố `{cipher}` trong repository test.
4. Gọi Environment API và xác nhận server giải mã được giá trị mong đợi cho client được phép.
5. Xác nhận client không cần nhận key giải mã của Config Server.
6. Kiểm tra caller không có scope decrypt bị từ chối khi gọi `/decrypt`.
7. Kiểm tra endpoint không thể truy cập từ mạng công khai hoặc danh tính không được cấp quyền.
8. Xoay thử key trong môi trường test và xác nhận ciphertext cũ/mới được xử lý theo kế hoạch.
9. Kiểm tra log, trace, Actuator và pipeline không ghi plaintext hoặc key material.

Một bài test thành công với `/encrypt` không đủ chứng minh cấu hình production an toàn. Cần xác minh quyền đọc key, quyền gọi endpoint, TLS, behavior của Config Server khi giải mã thất bại và khả năng rollback.

## 15. Những điểm cần ghi nhớ

- Giá trị nhạy cảm trong Git được lưu dưới dạng `{cipher}...`; Config Server giải mã trước khi trả Environment cho client.
- Khóa đối xứng dùng cùng một key để mã hóa/giải mã; keystore bất đối xứng giữ private key ở Config Server.
- `encrypt.key`, mật khẩu keystore và private key phải được cấp ngoài repository và artifact triển khai.
- Secret store, file mount và environment injection là các cách cấp key; HSM/KMS cần integration tương thích, không tự động có chỉ nhờ khai báo URL.
- `/encrypt` nhận plaintext và trả ciphertext; `/decrypt` trả plaintext và cần quyền rất hạn chế.
- Bảo vệ endpoint bằng TLS, xác thực, phân quyền riêng, network restriction và audit; không log request/response nhạy cảm.
- Mã hóa khi lưu trong Git không thay thế TLS khi Config Server gửi giá trị đã giải mã đến client.
- Xoay vòng khóa cần mã hóa lại ciphertext và phối hợp key version giữa tất cả Config Server replica.
- Backup key material phải được bảo vệ độc lập; thu hồi khóa khi hết vòng đời hoặc nghi ngờ bị lộ.

Giữ khóa giải mã ngoài repository giúp tách quyền đọc cấu hình khỏi quyền giải mã secret. Khi kết hợp key management, endpoint security, TLS, audit và quy trình xoay vòng, Spring Cloud Config có thể phân phối cấu hình nhạy cảm mà vẫn giữ được ranh giới truy cập rõ ràng giữa Git, Config Server, Config Client và nhóm vận hành.

## Tài liệu tham khảo

- [Spring Cloud Config – Encryption and Decryption](https://docs.spring.io/spring-cloud-config/reference/server/encryption-and-decryption.html)
- [Spring Cloud Config – Security](https://docs.spring.io/spring-cloud-config/reference/server/security.html)
- [Spring Security RSA](https://github.com/spring-cloud/spring-security-rsa)
