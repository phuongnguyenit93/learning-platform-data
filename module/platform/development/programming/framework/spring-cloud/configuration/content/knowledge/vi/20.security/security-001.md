# Ranh giới tin cậy giữa client, Config Server, kho Git và broker

Spring Cloud Config phân phối cấu hình qua nhiều thành phần và nhiều kết nối. Một Config Client gọi Config Server để lấy cấu hình; Config Server đọc dữ liệu từ Git hoặc backend khác; Spring Cloud Bus dùng broker để gửi thông báo refresh đến nhiều instance. Người vận hành và pipeline triển khai cũng có thể thay đổi cấu hình hoặc phát lệnh quản trị.

Mỗi kết nối là một ranh giới tin cậy riêng. Việc một thành phần đã xác thực với thành phần kế tiếp không có nghĩa nó được phép đọc mọi cấu hình, ghi mọi repository hoặc phát mọi sự kiện. Bảo mật cần kiểm soát cả danh tính, quyền truy cập, dữ liệu truyền đi, bí mật lưu trữ và hoạt động quản trị trên từng hop.

Bài học này tập trung vào bốn ranh giới chính: **Config Client ↔ Config Server**, **Config Server ↔ Git**, **ứng dụng ↔ broker**, và **operator/pipeline ↔ API quản trị**. Bạn sẽ thiết kế danh tính riêng cho từng kết nối, giới hạn quyền đọc theo ứng dụng, bảo vệ secrets và kiểm tra các tình huống khi một thành phần bị xâm nhập.

Sau bài học, bạn có thể:

- Vẽ luồng dữ liệu và xác định ranh giới tin cậy trong hệ thống Spring Cloud Config.
- Phân biệt authentication với authorization ở từng kết nối.
- Giới hạn Config Client chỉ đọc cấu hình thuộc ứng dụng và môi trường được cấp quyền.
- Cấp quyền read-only cho Config Server khi truy cập Git và xác minh danh tính máy chủ Git.
- Bảo vệ kết nối và quyền publish/consume của Spring Cloud Bus broker.
- Tách quyền quản trị refresh khỏi quyền đọc cấu hình thông thường.
- Quản lý encryption key, credentials, audit log và quy trình thu hồi khi có sự cố.

## 1. Nhìn hệ thống theo các ranh giới tin cậy

Một hệ thống điển hình có các thành phần:

- **Config Client:** ứng dụng Spring Boot cần đọc cấu hình.
- **Config Server:** API trung tâm trả Environment cho client.
- **Git provider:** nơi lưu file cấu hình và lịch sử thay đổi.
- **Message broker:** RabbitMQ hoặc Kafka, dùng để chuyển sự kiện Spring Cloud Bus.
- **Operator/pipeline:** danh tính con người hoặc hệ thống triển khai có quyền phát hành cấu hình, gọi refresh và vận hành dịch vụ.
- **Secret manager/identity provider:** nơi cấp credentials, access token và khóa mã hóa.

~~~mermaid
flowchart LR
    O["Operator / CI pipeline"] -->|"TLS + quyền quản trị"| S["Config Server API"]
    C["Config Client"] -->|"TLS + danh tính riêng"| S
    S -->|"HTTPS token hoặc SSH deploy key"| G["Git provider"]
    C -->|"TLS + ACL publish/consume"| B[("RabbitMQ / Kafka")]
    S -->|"TLS + ACL nếu dùng Bus"| B
    V["Secret manager / Identity provider"] -->|"Cấp credential runtime"| C
    V -->|"Cấp Git credential và key"| S
    O -->|"Audit / release approval"| G
~~~

Trong triển khai thực tế, Config Server có thể không trực tiếp tham gia Spring Cloud Bus nếu kiến trúc không yêu cầu. Sơ đồ chỉ thể hiện các kết nối có thể tồn tại; mỗi dịch vụ chỉ nên có những quyền cần cho vai trò của nó.

Bốn hop cần được kiểm soát độc lập:

| Kết nối | Danh tính cần xác minh | Quyền cần giới hạn |
|---|---|---|
| Config Client → Config Server | Workload identity của từng ứng dụng | Chỉ đọc application/profile/label được cấp |
| Config Server → Git | Service account hoặc deploy key của Config Server | Chỉ clone/fetch repository cần thiết |
| Config Client/Bus participant → broker | Broker principal của từng workload | Chỉ publish/consume destination cần thiết |
| Operator/pipeline → Config Server hoặc Bus endpoint | Người dùng hoặc service identity quản trị | Chỉ gọi API quản trị được phân công |

Không dùng một mật khẩu hoặc token chung cho tất cả các kết nối. Nếu một credential bị lộ, phạm vi ảnh hưởng phải được giới hạn trong một vai trò cụ thể.

## 2. Authentication và authorization giải quyết hai câu hỏi khác nhau

**Authentication** xác minh bên gọi là ai. **Authorization** quyết định danh tính đó được làm gì và trên tài nguyên nào.

Ví dụ, Config Server xác thực thành công một client bằng HTTP Basic hoặc JWT chỉ chứng minh request có danh tính hợp lệ. Nó chưa chứng minh client được phép đọc cấu hình của **payment-service**, **order-service** hoặc profile production.

Một chính sách chỉ yêu cầu người dùng đăng nhập:

~~~java
.authorizeHttpRequests(auth -> auth
    .anyRequest().authenticated()
)
~~~

có thể phù hợp với một API nội bộ đơn giản, nhưng chưa đủ khi repository chứa secrets riêng theo ứng dụng. Cần thêm authorization dựa trên danh tính và đường dẫn tài nguyên.

Các quyền nên được xác định cụ thể:

- Ứng dụng nào được đọc.
- Profile nào được đọc, ví dụ dev, staging hoặc prod.
- Label/revision nào được phép truy cập nếu có ranh giới phát hành.
- Danh tính nào được gọi endpoint quản trị.
- Danh tính nào được phép publish hoặc consume broker destination.

Không coi tên ứng dụng do client gửi trong URL là bằng chứng danh tính. Client có thể tự thay path segment nếu server không ràng buộc nó với principal đã xác thực.

## 3. Bảo vệ Config Client → Config Server

Config Server hỗ trợ nhiều cơ chế bảo vệ, ví dụ HTTP Basic và OAuth2/JWT Bearer token thông qua Spring Security. Với HTTP Basic, có thể thêm Spring Security vào classpath và cấu hình user/password. Với nhiều client cần danh tính độc lập, OAuth2/JWT thường thuận tiện hơn để cấp token riêng cho từng workload. Xem [Spring Cloud Config — Security](https://docs.spring.io/spring-cloud-config/reference/server/security.html).

### HTTP Basic cho môi trường đơn giản

Ví dụ Config Server dùng một user trong môi trường thử nghiệm:

~~~yaml
spring:
  security:
    user:
      name: order-service
      password: ${CONFIG_SERVER_PASSWORD}
~~~

Client khai báo thông tin truy cập từ biến môi trường được nền tảng cấp:

~~~yaml
spring:
  config:
    import: "configserver:https://config.internal.example"
  cloud:
    config:
      username: order-service
      password: ${CONFIG_SERVER_PASSWORD}
~~~

Đây chỉ là minh họa cho cách truyền credentials. Trong production, nên có danh tính riêng cho mỗi ứng dụng hoặc workload, lưu password trong secret manager và giới hạn thời hạn/khả năng sử dụng. Tránh dùng một tài khoản chung cho tất cả client vì khi đó server khó phân biệt quyền của từng ứng dụng.

HTTP Basic phải được dùng qua TLS. Nếu truyền username/password qua HTTP không mã hóa, người quan sát được lưu lượng có thể lấy credential và giả mạo client.

### OAuth2/JWT cho nhiều client

Config Server có thể hoạt động như OAuth2 Resource Server. Ví dụ cấu hình xác minh JWT từ identity provider:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/issuer
~~~

Thêm dependency Resource Server tương ứng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Identity provider cấp access token cho workload. Config Server xác minh chữ ký, issuer, thời hạn và các claim theo cấu hình Resource Server. Authorization policy của ứng dụng cần tiếp tục kiểm tra claim hoặc principal để quyết định client được đọc tài nguyên nào.

Spring Cloud Config Client không tự động lấy OAuth2 token chỉ vì Config Server được cấu hình Resource Server. Client cần một cơ chế lấy token, chẳng hạn OAuth2 Client với client credentials, sau đó gắn Bearer token vào request Config Server. Xem [Spring Security — OAuth2](https://docs.spring.io/spring-security/reference/servlet/oauth2/).

## 4. Giới hạn quyền đọc theo application

Đây là một ranh giới rất quan trọng. Theo mặc định, một người dùng đã xác thực có thể yêu cầu cấu hình của bất kỳ application name nào nếu họ biết tên ứng dụng đó. Nếu repository chứa database password hoặc API token riêng theo dịch vụ, điều này có thể làm lộ secret giữa các service.

Spring Cloud Config hướng dẫn dùng custom **SecurityFilterChain** hoặc **RequestMatcher** để ràng buộc application trong URL với principal đã xác thực. Ví dụ sau minh họa HTTP Basic và giới hạn principal chỉ đọc ứng dụng có tên trùng với principal:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ConfigServerSecurity {

    @Bean
    SecurityFilterChain configSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            // Chỉ permit nếu Actuator thực sự sở hữu route health này.
            .requestMatchers("/actuator/health").permitAll()
            .requestMatchers("/actuator/**").hasRole("OPS")
            .requestMatchers("/encrypt", "/decrypt").hasRole("CONFIG_CRYPTO_ADMIN")
            .requestMatchers("/{application}/**").access((authentication, context) -> {
                String requestedApp = context.getVariables().get("application");
                String principal = authentication.get().getName();

                return new AuthorizationDecision(
                    principal.equals(requestedApp)
                );
            })
            .anyRequest().denyAll()
        );

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Ví dụ này minh họa một quy tắc đơn giản. Trong hệ thống dùng JWT, principal có thể là subject hoặc claim khác; hãy ánh xạ danh tính workload thành application ID đã đăng ký. Không lấy application ID từ request body hoặc header do client tự đặt làm nguồn tin cậy.

Nếu một client chỉ được đọc profile **dev** và không được đọc **prod**, authorization policy phải kiểm tra cả profile. Nếu quyền truy cập khác nhau theo label, hãy kiểm tra label tương ứng. Ràng buộc application đơn thuần chưa đủ cho mô hình phân quyền theo môi trường.

Khi triển khai policy, kiểm thử cả trường hợp từ chối:

- Client **order-service** yêu cầu **order-service/dev**: được phép nếu đã cấp quyền.
- Client **order-service** yêu cầu **payment-service/prod**: phải bị từ chối.
- Token hết hạn hoặc issuer sai: phải bị từ chối.
- Request thiếu application hoặc có path không hợp lệ: phải xử lý theo chính sách từ chối an toàn.

## 5. Bảo vệ TLS trên từng kết nối

TLS mã hóa lưu lượng và xác minh danh tính máy chủ thông qua certificate. TLS không tự quyết định người dùng được đọc application nào; authorization vẫn cần thực hiện ở tầng ứng dụng.

Có ít nhất ba kết nối cần xem xét:

| Kết nối | Kiểm soát TLS |
|---|---|
| Client → Config Server | HTTPS; xác minh certificate và hostname của Config Server |
| Config Server → Git | HTTPS với certificate validation hoặc SSH host key verification |
| Ứng dụng → broker | TLS/SASL_SSL hoặc cơ chế TLS và authentication tương ứng của broker |

Với Config Server, dùng cấu hình TLS của Spring Boot qua **server.ssl.*** hoặc đặt server phía sau reverse proxy/gateway có TLS được cấu hình đúng. Không để credentials và cấu hình đi qua mạng nội bộ dưới dạng plaintext chỉ vì mạng được gọi là private.

Với Git HTTPS, giữ kiểm tra certificate bật. Spring Cloud Config có thuộc tính **skipSslValidation**, mặc định là **false**. Không bật bỏ qua kiểm tra certificate để khắc phục tạm thời lỗi certificate; hãy cài đúng CA chain và hostname. Xem [Git Backend — SSL Certificate Validation](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html).

Với SSH, xác minh host key của Git server. Nếu dùng property-based SSH configuration, giữ **strictHostKeyChecking=true** và cung cấp host key hoặc file known_hosts đã xác minh. Tắt host key checking khiến Config Server chấp nhận máy chủ SSH bất kỳ trong handshake, mở ra nguy cơ kết nối đến máy chủ giả mạo.

## 6. Config Server → Git: danh tính riêng và quyền tối thiểu

Config Server cần credential để clone hoặc fetch repository riêng. Credential này thuộc về Config Server, không phải Config Client.

Với HTTPS, khai báo URI và credentials thành các thuộc tính riêng:

~~~yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          username: config-reader
          password: ${CONFIG_GIT_TOKEN}
          clone-on-start: true
~~~

Không nhúng token vào Git URL. URL có thể bị ghi vào log, exception, dashboard, process argument hoặc hệ thống giám sát. Tài liệu Git backend của Spring Cloud Config hướng dẫn đặt username và password riêng. Xem [Spring Cloud Config — Git Backend Authentication](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html).

Danh tính Git của Config Server nên:

- Chỉ có quyền đọc repository cần thiết.
- Không có quyền push, xóa branch hoặc quản trị thành viên.
- Dùng deploy token/deploy key riêng thay vì token cá nhân của lập trình viên.
- Có phạm vi repository rõ ràng và thời hạn/chu kỳ rotation.
- Được cấp từ secret manager hoặc secret mount khi chạy.

Nếu dùng SSH, private key chỉ được cấp cho Config Server. Public key được đăng ký trên Git provider với quyền read-only nếu provider hỗ trợ. Host key của Git server phải được xác minh riêng; private key xác thực client với Git, còn host key xác thực Git server với Config Server.

Không chia sẻ Git private key với các Config Client. Nếu client có Git credential, client có thể vượt qua kiến trúc phân phối tập trung và truy cập repository trực tiếp ngoài chính sách của Config Server.

## 7. Git repository cũng là một ranh giới tin cậy

File cấu hình có thể thay đổi endpoint, logging, timeout, feature flag, quyền truy cập và hành vi kết nối của ứng dụng. Người có quyền sửa repository cấu hình vì thế có thể tác động đến runtime của nhiều dịch vụ.

Bảo vệ Git repository bằng quy trình phát hành:

- Bảo vệ branch production; yêu cầu review trước khi merge.
- Giới hạn ai có quyền ghi và ai chỉ có quyền đọc.
- Dùng CI để kiểm tra YAML, schema và các quy tắc chính sách trước khi merge.
- Lưu lịch sử thay đổi và liên kết commit với ticket hoặc release.
- Tách quyền thay đổi cấu hình khỏi quyền deploy ứng dụng nếu cần separation of duties.
- Dùng label hoặc commit cụ thể cho rollout cần kiểm soát phiên bản.
- Theo dõi ai thay đổi file nào và thời điểm nào.

Không để Config Server dùng credential có quyền ghi repository chỉ vì việc dùng một token duy nhất tiện hơn. Nếu Config Server chỉ clone/fetch, quyền write là thừa.

Cũng cần bảo vệ quy trình build và CI. Một pipeline bị xâm nhập có thể đưa cấu hình độc hại vào branch được Config Server tin cậy. Hãy bảo vệ runner, secret CI, quyền merge và các bước phê duyệt.

## 8. Secrets: mã hóa khi lưu và giới hạn khi phân phối

Không commit password, private key, access token hoặc certificate private key dưới dạng plaintext trong Git. Có hai cách tiếp cận phổ biến:

1. Lưu secret trong secret manager như Vault hoặc secret store của nền tảng, rồi cấp cho workload đúng lúc chạy.
2. Dùng cơ chế mã hóa giá trị cấu hình của Spring Cloud Config nếu cần lưu ciphertext trong repository.

Với Spring Cloud Config, giá trị bắt đầu bằng **{cipher}** được giải mã ở Config Server trước khi gửi cho client qua HTTP. Mục tiêu là tránh để secret ở dạng plaintext trong Git hoặc storage. Sau khi giải mã, client vẫn nhận plaintext, vì vậy cần TLS và authorization đúng. Encryption at rest không thay thế kiểm soát quyền đọc. Xem [Spring Cloud Config — Encryption and Decryption](https://docs.spring.io/spring-cloud-config/reference/server/encryption-and-decryption.html).

Ví dụ repository có thể chứa ciphertext:

~~~yaml
spring:
  datasource:
    username: order_reader
    password: '{cipher}ENCRYPTED_VALUE_FROM_CONFIG_SERVER'
~~~

Khóa giải mã phải được giữ ngoài repository. Config Server hỗ trợ symmetric key hoặc asymmetric key pair. Có thể cấp symmetric key qua biến môi trường **ENCRYPT_KEY** hoặc dùng keystore theo cấu hình phù hợp. Không commit keystore password, private key hoặc encryption key vào cùng repository chứa ciphertext. Xem [Spring Cloud Config — Key Management](https://docs.spring.io/spring-cloud-config/reference/server/key-management.html).

Các endpoint **/encrypt** và **/decrypt** có thể xử lý dữ liệu bí mật. Chỉ expose và cho phép gọi bởi danh tính được ủy quyền. Không để người dùng Config Client thông thường có quyền gọi **/decrypt**.

Nếu cần mã hóa riêng theo ứng dụng/profile, phải thiết kế locator và key mapping tương ứng. Không mặc định một khóa dùng chung cho toàn bộ hệ thống là ranh giới cô lập secret giữa các ứng dụng.

## 9. Bảo vệ ứng dụng ↔ broker trong Spring Cloud Bus

Spring Cloud Bus dùng Spring Cloud Stream binder để giao tiếp với broker. Mỗi workload kết nối broker cần danh tính riêng và chỉ được cấp quyền cần thiết cho destination của nó.

Với Kafka, có thể bật TLS cùng SASL bằng **SASL_SSL**. Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          configuration:
            security.protocol: SASL_SSL
            sasl.mechanism: SCRAM-SHA-512
            sasl.jaas.config: ${KAFKA_SASL_JAAS_CONFIG}
~~~

Giá trị JAAS chứa credentials phải được cấp từ secret manager hoặc secret của nền tảng triển khai. Không ghi password trực tiếp trong file YAML được commit. Spring Cloud Stream Kafka binder cho phép cấu hình các thuộc tính bảo mật của Kafka client qua **spring.cloud.stream.kafka.binder.configuration**. Xem [Spring Cloud Stream — Kafka Security Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/security-config.html).

Với RabbitMQ, cấu hình TLS, username/password và quyền vhost/queue/exchange theo Rabbit binder và chính sách của broker. Không dùng một bộ credentials có quyền administrator cho mọi ứng dụng.

Broker ACL nên phân biệt:

- Producer nào được publish event lên destination.
- Consumer nào được subscribe destination.
- Workload nào được tạo topic/queue hoặc thay đổi cấu trúc broker.
- Operator nào có quyền quản trị broker.

Không cấp quyền tạo topic hoặc quản trị broker cho mọi Config Client nếu topic đã được provision bởi hạ tầng. Giới hạn quyền publish cũng quan trọng: một workload không được phép có thể phát refresh hoặc sự kiện quản trị đến phạm vi ngoài trách nhiệm của nó.

## 10. Bảo vệ endpoint quản trị và Actuator

Các endpoint của Spring Cloud Bus có thể ảnh hưởng đến nhiều instance:

| Endpoint | Tác động | Mức quyền cần cân nhắc |
|---|---|---|
| **/actuator/busrefresh** | Yêu cầu các instance refresh cấu hình | Quyền vận hành cấu hình |
| **/actuator/busenv** | Cập nhật một key/value trên nhiều instance | Quyền quản trị cấu hình rất hạn chế |
| **/actuator/busshutdown** | Yêu cầu ứng dụng dừng | Quyền vận hành đặc biệt |
| **/actuator/bustrace** | Hiển thị metadata event và instance | Quyền xem thông tin vận hành |

Chỉ expose endpoint thực sự cần dùng. Ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,busrefresh
~~~

Không dùng **include: "*"** trong production nếu chưa có policy rõ ràng cho từng endpoint. Spring Boot lưu ý rằng chỉ **health** được expose qua HTTP theo mặc định; các endpoint khác cần được bảo vệ bằng firewall hoặc Spring Security. Nếu ứng dụng tự khai báo **SecurityFilterChain**, cấu hình bảo mật Actuator tự động của Spring Boot sẽ nhường quyền kiểm soát cho cấu hình tùy chỉnh. Xem [Spring Boot — Actuator Endpoint Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).

Cần tách quyền đọc health khỏi quyền phát refresh. Ví dụ, hệ thống giám sát có thể đọc health nhưng không được gọi **busrefresh** hoặc **busshutdown**. Operator có quyền refresh không nhất thiết cần quyền đọc secret hoặc sửa Git repository.

Một lưu ý riêng với Config Server: nếu Actuator không nằm trong classpath, request đến **/actuator/** có thể bị route nhầm vào API cấu hình theo dạng **/{application}/{label}** và làm lộ thông tin. Cần thêm Actuator dependency khi dùng health endpoint, đồng thời cấu hình security để user health check không có quyền đọc Config Server API. Xem [Spring Cloud Config — Actuator and Security](https://docs.spring.io/spring-cloud-config/reference/server/actuator-and-security.html).

## 11. Mô hình quyền mẫu cho một hệ thống

Một bảng phân quyền giúp kiểm tra xem mỗi danh tính có đang nhận quá nhiều quyền hay không:

| Danh tính | Config Server API | Git repository | Broker | API quản trị |
|---|---|---|---|---|
| order-service | Đọc order-service/dev và prod theo policy | Không truy cập trực tiếp | Publish/consume Bus destination được cấp | Không |
| payment-service | Đọc payment-service/profile được cấp | Không truy cập trực tiếp | Publish/consume destination riêng | Không |
| Config Server | Không cần quyền client ngoài thiết kế | Read-only các repo cấu hình | Chỉ quyền Bus nếu kiến trúc cần | Health nội bộ |
| CI pipeline | Kiểm tra response/revision theo quyền | Ghi branch qua quy trình review | Không cần quyền broker thông thường | Có thể phát refresh sau release approval |
| Operator | Theo vai trò được cấp | Review/merge theo quyền | Không cần broker admin mặc định | Refresh hoặc xem trace theo role |
| Monitoring | Health/metrics cần thiết | Không | Metrics read-only nếu được cấp | Không được gọi busrefresh |

Bảng chỉ là ví dụ phân quyền. Quyền thực tế phải khớp topology, cách tách repository, profile và broker destination của hệ thống.

## 12. Các tình huống xâm phạm và phạm vi ảnh hưởng

| Sự cố | Rủi ro | Kiểm soát giúp giảm tác động |
|---|---|---|
| Credential của một Config Client bị lộ | Kẻ tấn công giả mạo client và có thể thử đọc cấu hình khác | Per-app authorization, token ngắn hạn, thu hồi credential |
| Config Server bị xâm nhập | Có thể đọc nhiều cấu hình và Git credential, giải mã secret | Cô lập mạng, quyền Git read-only, secret manager, audit và hardening server |
| Git token bị lộ | Kẻ tấn công đọc repository hoặc sửa cấu hình nếu token có quyền ghi | Read-only deploy identity, scope hẹp, branch protection và rotation |
| Git server giả mạo | Config Server có thể tải cấu hình từ nguồn không đáng tin | TLS certificate validation hoặc SSH host key verification |
| Broker credential bị lộ | Kẻ tấn công có thể publish/consume event trái phép | Broker TLS, ACL theo destination, credential riêng |
| Operator token bị lộ | Kẻ tấn công phát refresh hoặc thay đổi trạng thái nhiều instance | Role riêng, MFA/short-lived identity, audit và approval |
| Encryption key bị lộ | Ciphertext trong repository có thể giải mã | Tách key khỏi Git, hạn chế người đọc, rotation và incident response |

Mức độ ảnh hưởng phụ thuộc quyền của danh tính bị xâm phạm. Nếu mọi service dùng cùng một credential, một sự cố nhỏ có thể lan sang toàn hệ thống. Nếu mỗi hop có identity và scope riêng, có thể thu hồi một credential mà không phải thay toàn bộ credentials của hệ thống.

## 13. Audit, logging và rotation

Mọi thay đổi cấu hình production nên truy được về một người hoặc một workload cụ thể. Audit record nên có:

- Người hoặc service identity thực hiện.
- Application, profile, label và repository liên quan.
- Git commit hoặc revision.
- Event ID nếu phát Spring Cloud Bus event.
- Thời điểm request và kết quả.
- Phạm vi instance được tác động.
- Approval/ticket hoặc release identifier.

Không log Authorization header, access token, password, private key, encryption key hoặc toàn bộ response chứa secret. Với cấu hình nhạy cảm, log tên property và trạng thái thay đổi thay vì ghi giá trị plaintext.

Quy trình rotation nên theo từng loại credential:

1. Tạo credential mới với cùng phạm vi quyền tối thiểu.
2. Cấp credential mới vào secret manager.
3. Cập nhật workload và triển khai theo thứ tự để tránh gián đoạn.
4. Kiểm tra từng kết nối bằng credential mới.
5. Thu hồi credential cũ sau khi các instance đã chuyển đổi.
6. Ghi nhận thời điểm, owner và kết quả kiểm tra.

Nếu credential bị lộ, thu hồi ngay theo mức độ rủi ro, xác định nơi nó từng được sử dụng và kiểm tra log/audit. Chỉ thay token trong file hiện tại là chưa đủ nếu giá trị cũ còn trong Git history, build logs, image hoặc hệ thống quan sát.

## 14. Kiểm thử các ranh giới tin cậy

Bảo mật không nên chỉ được kiểm tra bằng một request hợp lệ. Hãy có các bài kiểm thử âm tính chứng minh hệ thống từ chối đúng người và đúng tài nguyên:

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Request Config Server không có credentials | 401 hoặc bị từ chối theo cơ chế xác thực |
| Client order-service yêu cầu payment-service | 403 hoặc bị từ chối theo policy |
| Client yêu cầu profile prod khi chỉ có quyền dev | Bị từ chối |
| JWT hết hạn hoặc issuer sai | Token bị từ chối |
| Config Server kết nối Git bằng token hết hạn | Không ghi nhận revision mới; nếu server còn local clone, phải nhận diện rõ dữ liệu đang phục vụ là revision đã cache |
| Git TLS certificate không tin cậy | Kết nối bị từ chối |
| SSH host key không khớp | Kết nối bị từ chối |
| Broker principal không có quyền publish | Publish bị từ chối |
| Monitoring gọi busrefresh | Bị từ chối |
| Operator có quyền refresh gọi busrefresh | Được phép và có audit record |
| User health check gọi Config Server API | Bị từ chối |

Kiểm thử cả luồng thành công và thất bại trong môi trường staging. Xác minh status code, log đã che dữ liệu nhạy cảm, audit record và broker ACL. Không dùng credential production trong test.

## 15. Checklist triển khai production

- Mỗi Config Client có workload identity riêng.
- Config Server xác thực và phân quyền theo application; profile/label được kiểm tra nếu có ranh giới môi trường.
- Client kết nối Config Server qua HTTPS và xác minh certificate.
- Config Server dùng Git service account/deploy key chỉ đọc.
- Git credential được cấp runtime và không nằm trong URI, Git hoặc image.
- Git HTTPS certificate validation và SSH host key verification được bật.
- Encryption key nằm ngoài repository; endpoint encrypt/decrypt được bảo vệ.
- Secret chỉ được phân phối đến client có quyền đọc.
- Broker dùng TLS và authentication; ACL giới hạn publish/consume destination.
- Bus và Actuator endpoints chỉ expose khi cần và có role phù hợp.
- Health check không có quyền đọc Config Server API hoặc secrets.
- Git changes có review, branch protection và audit.
- Có quy trình rotation, revoke và incident response.
- Có negative tests cho request sai application/profile, token hết hạn và quyền broker bị từ chối.

## 16. Tự kiểm tra

1. Authentication khác authorization như thế nào trong request Config Client đến Config Server?
2. Vì sao một client đã xác thực vẫn có thể đọc nhầm cấu hình của ứng dụng khác nếu không có per-application authorization?
3. Git token mà Config Server dùng khác gì với credential của Config Client?
4. Vì sao quyền read-only phù hợp với Config Server khi nó chỉ clone/fetch repository?
5. TLS bảo vệ điều gì và không thay thế cơ chế nào?
6. SSH private key và SSH host key xác minh hai phía nào của kết nối?
7. Vì sao không nên để mọi Config Client dùng chung một broker principal?
8. Endpoint busrefresh, busenv và busshutdown cần được phân quyền như thế nào?
9. Khi Config Server giải mã giá trị {cipher}, vì sao client vẫn cần TLS và authorization?
10. Nếu token của một client bị lộ, những lớp kiểm soát nào giúp ngăn client đọc secrets của service khác?

Hãy dựng một môi trường staging có Config Server, hai Config Client với danh tính riêng, Git repository riêng và broker. Cấu hình client thứ nhất chỉ được đọc cấu hình của chính nó; thử yêu cầu application thứ hai và xác nhận bị từ chối. Tiếp đó, dùng Git deploy identity read-only và kiểm tra Config Server không thể push. Bật TLS cho Config Server và broker, kiểm tra certificate validation. Cuối cùng, cấp quyền Bus refresh cho operator role, thử gọi endpoint từ monitoring identity và xác nhận bị từ chối. Ghi lại audit event và xác minh log không chứa credentials hoặc secret plaintext.

## Tài liệu tham khảo

- [Spring Cloud Config — Security](https://docs.spring.io/spring-cloud-config/reference/server/security.html)
- [Spring Cloud Config — Git Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html)
- [Spring Cloud Config — Encryption and Decryption](https://docs.spring.io/spring-cloud-config/reference/server/encryption-and-decryption.html)
- [Spring Cloud Config — Key Management](https://docs.spring.io/spring-cloud-config/reference/server/key-management.html)
- [Spring Cloud Config — Actuator and Security](https://docs.spring.io/spring-cloud-config/reference/server/actuator-and-security.html)
- [Spring Cloud Bus — Bus Endpoints](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/bus-endpoints.html)
- [Spring Cloud Stream — Kafka Security Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/security-config.html)
- [Spring Boot — Actuator Endpoint Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Security — OAuth2](https://docs.spring.io/spring-security/reference/servlet/oauth2/)

