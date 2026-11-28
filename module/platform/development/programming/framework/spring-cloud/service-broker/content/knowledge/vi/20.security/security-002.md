# Xác thực nền tảng bằng HTTP Basic theo hợp đồng OSB và triển khai TLS

Service broker nhận request từ platform để cung cấp catalog, provision service instance, update, deprovision, tạo binding và theo dõi operation. Các request này có thể tạo tài nguyên, cấp credential hoặc xóa dữ liệu production. Vì vậy, broker phải xác thực platform trước khi xử lý API. Open Service Broker API (OSB API) định nghĩa cơ chế HTTP Basic Authentication cho platform gọi broker; TLS bảo vệ credential và dữ liệu trên đường truyền.

Trong mô hình này, platform là client của broker. Khi đăng ký broker, platform được cấu hình URL và thông tin xác thực do broker cấp. Platform gửi username/password trong header Authorization của các request OSB. Broker xác thực cặp credential, ánh xạ nó đến platform identity đã đăng ký và áp dụng quyền truy cập tương ứng. TLS xác thực server broker với platform và mã hóa kênh truyền; mutual TLS có thể được bổ sung nếu hạ tầng hỗ trợ.

HTTP Basic chỉ mã hóa username/password bằng Base64 để biểu diễn trong header; Base64 không phải mã hóa bảo mật. Vì vậy, Basic Authentication chỉ an toàn khi request đi qua HTTPS với chứng thư TLS được kiểm tra hợp lệ. Không được gửi credential broker qua HTTP thuần.

## 1. Vai trò xác thực trong kiến trúc Service Broker

Có nhiều loại credential trong một hệ thống broker và cần tách biệt chúng:

| Credential | Chủ thể sử dụng | Mục đích |
|---|---|---|
| OSB broker credentials | Platform gửi đến broker | Xác thực platform với broker |
| Provider credentials | Broker gửi đến Cloud API hoặc control plane | Cho broker tạo, cập nhật và thu hồi tài nguyên phía sau |
| Service binding credentials | Ứng dụng consumer | Cho ứng dụng kết nối database, queue hoặc service |
| TLS server private key | Broker hoặc TLS ingress | Chứng minh danh tính server broker |
| TLS client certificate (nếu dùng mTLS) | Platform | Bổ sung xác thực client ở tầng TLS |

Các loại credential này có vòng đời và phạm vi quyền khác nhau. Không dùng password của database binding làm Basic password cho platform. Không dùng provider API token làm OSB broker password. Không dùng private key TLS làm password HTTP Basic.

Luồng tin cậy cơ bản:

    Platform -- HTTPS + Basic --> TLS endpoint --> Service Broker
    Service Broker -- provider credentials riêng --> Provider API

TLS và HTTP Basic giải quyết hai phần bổ sung cho nhau: TLS bảo vệ kênh và xác thực server; Basic Authentication xác thực platform client ở tầng HTTP. Một kết nối HTTPS hợp lệ không tự chứng minh caller được phép thao tác trên service instance. Ngược lại, một cặp Basic credentials đúng không bảo vệ được password nếu gửi qua HTTP.

## 2. Hợp đồng HTTP Basic của OSB API

Khi platform đăng ký service broker, platform lưu thông tin xác thực broker và gửi chúng trong header Authorization của request đến broker. Dạng header:

    Authorization: Basic <base64(username:password)>

Giá trị sau từ khóa Basic là Base64 của chuỗi username, dấu hai chấm và password. Ví dụ minh họa:

    username = platform-a
    password = <secret>
    raw value = platform-a:<secret>
    header = Authorization: Basic <base64-encoded-value>

Không tự tạo Base64 bằng cách nối username/password trong log hoặc script rồi lưu kết quả như một secret mới. Base64 có thể giải mã trực tiếp về giá trị ban đầu.

Broker cần hỗ trợ xác thực Basic theo hợp đồng OSB API và kiểm tra credential trên mọi endpoint OSB được bảo vệ, bao gồm:

- GET catalog.
- PUT provision và PATCH update service instance.
- DELETE deprovision.
- PUT và DELETE service binding.
- GET retrieve service instance hoặc binding khi broker công bố capability tương ứng.
- GET last_operation cho các thao tác bất đồng bộ.

Không chỉ bảo vệ các endpoint tạo hoặc xóa tài nguyên. Catalog và endpoint đọc cũng có thể tiết lộ service, plan, metadata, trạng thái hoặc thông tin binding. Cần áp dụng chính sách xác thực nhất quán cho toàn bộ OSB API.

Các endpoint quản trị nội bộ, actuator hoặc health check không mặc nhiên là endpoint OSB. Chúng cần chính sách truy cập riêng, giới hạn theo mạng và quyền vận hành. Không vô tình để endpoint quản trị công khai chỉ vì đã cấu hình Basic cho đường dẫn /v2/**.

### 2.1. Basic Authentication không phải mã hóa

Base64 chỉ chuyển dữ liệu sang dạng biểu diễn khác. Người có được header có thể giải mã để lấy username và password. Vì vậy:

- Chỉ chấp nhận Basic credentials trên HTTPS.
- Tắt HTTP listener công khai hoặc chặn HTTP ở ingress/firewall.
- Không dựa vào redirect từ HTTP sang HTTPS để bảo vệ credential; request HTTP đầu tiên đã có thể làm lộ header.
- Không ghi Authorization header vào application log, access log, tracing hoặc error report.
- Không đưa username/password vào query parameter hoặc request body.
- Không gửi Basic credentials đến hostname không được platform cấu hình là broker.

### 2.2. Credential gắn với platform registration

Mỗi platform registration nên có username hoặc credential identity riêng. Khi xác thực thành công, broker ánh xạ identity đó sang platform account hoặc installation tương ứng. Điều này giúp:

- Thu hồi quyền của một platform mà không ảnh hưởng platform khác.
- Xoay credential theo từng registration.
- Ghi audit biết request đến từ platform nào.
- Áp dụng rate limit và chính sách truy cập theo platform.
- Ngăn một credential dùng chung trở thành điểm xâm nhập cho toàn bộ broker.

Không lấy platform identity từ một field do caller tự gửi trong JSON rồi coi đó là danh tính đã xác thực. Identity phải được suy ra từ credential đã xác thực hoặc một cơ chế tin cậy bổ sung.

## 3. Xác thực và phân quyền là hai bước riêng

Xác thực trả lời câu hỏi caller là ai. Phân quyền xác định caller đó được phép làm gì và trên phạm vi nào.

Sau khi Basic credentials hợp lệ, broker nên tạo một principal nội bộ có thông tin như:

| Thuộc tính | Ví dụ | Mục đích |
|---|---|---|
| principal ID | broker-client-17 | Định danh client đã xác thực |
| platform ID | cf-prod-east | Phạm vi platform registration |
| username | cf-prod-east-broker | Tìm credential record |
| roles/authorities | OSB_PLATFORM | Quyền gọi OSB API |
| status | ACTIVE | Có cho phép tiếp tục sử dụng credential không |
| credential version | 4 | Theo dõi rotation và thu hồi |
| expires/rotated at | Thời điểm | Chính sách vòng đời credential |

Với mô hình nhiều platform, cần kiểm tra service instance hoặc binding thuộc platform scope của principal. Ví dụ platform A không thể truy xuất binding của platform B chỉ vì đoán được instance ID và binding ID.

Một kiểm tra quyền điển hình:

1. Xác thực username/password.
2. Lấy platform ID gắn với credential record.
3. Đọc service instance theo cặp platform ID và service instance ID.
4. Kiểm tra service, plan và trạng thái instance phù hợp với operation.
5. Chỉ sau đó mới gọi provider hoặc trả dữ liệu.

Không coi việc biết URL, instance ID, binding ID hoặc operation ID là bằng chứng có quyền truy cập. Các ID này là định danh tài nguyên, không phải bí mật xác thực.

## 4. TLS bảo vệ kênh platform đến broker

TLS cung cấp mã hóa, toàn vẹn dữ liệu và xác thực server thông qua chứng thư số. Khi platform kết nối đến broker bằng HTTPS, platform phải kiểm tra:

- Chứng thư còn hiệu lực và chưa hết hạn.
- Hostname trong URL khớp Subject Alternative Name (SAN) của certificate.
- Certificate chain dẫn đến CA được platform tin cậy.
- Chứng thư chưa bị thu hồi theo chính sách kiểm tra của môi trường.
- TLS protocol và cipher suite đáp ứng baseline bảo mật của tổ chức.

Nên dùng TLS 1.2 trở lên; ưu tiên TLS 1.3 khi cả platform và broker hỗ trợ. Tắt SSL cũ và TLS version không còn an toàn. Không dùng chứng thư tự ký nếu platform không được cấu hình tin cậy CA/certificate đó.

### 4.1. Server certificate và private key

Broker hoặc TLS ingress cần certificate có SAN phù hợp với hostname mà platform sử dụng. Private key phải được bảo vệ như secret có giá trị cao:

- Lưu trong secret manager, keystore hoặc cơ chế quản lý khóa của nền tảng.
- Hạn chế quyền đọc private key cho process cần thiết.
- Không commit private key hoặc keystore password vào Git.
- Không in private key, certificate chain có thông tin nhạy cảm hoặc keystore password vào log.
- Có lịch gia hạn và thay thế certificate trước khi hết hạn.
- Kiểm tra chain và hostname từ chính mạng mà platform dùng để gọi broker.

Ví dụ cấu hình Spring Boot với keystore được mount từ secret:

    server:
      port: 8443
      ssl:
        enabled: true
        key-store: file:/run/secrets/broker-keystore.p12
        key-store-type: PKCS12
        key-store-password: "<injected-keystore-secret>"
        key-alias: service-broker

Đây là cấu hình minh họa. Trong production, giá trị password phải được inject từ secret manager hoặc secret volume, không lưu nguyên văn trong application.yml. Nếu TLS được terminate ở ingress, cấu hình certificate nằm ở ingress; cần bảo vệ cả chặng ingress đến ứng dụng theo mô hình mạng của hệ thống.

### 4.2. Không hạ cấp xuống HTTP

Nếu certificate hết hạn, hostname sai hoặc CA không được tin cậy, cần sửa certificate/trust configuration. Không hướng dẫn platform tắt certificate validation hoặc dùng tùy chọn tương đương curl -k để làm cho kết nối hoạt động.

HTTP thuần không được phép chuyển tiếp Authorization header. Tốt nhất chỉ mở HTTPS listener ở public endpoint. Nếu cần HTTP giữa ingress và ứng dụng trong môi trường nội bộ, hãy giới hạn bằng network policy và cân nhắc TLS/mTLS trên internal hop; không để client bên ngoài truy cập trực tiếp listener đó.

## 5. TLS termination tại ingress hoặc reverse proxy

Nhiều triển khai đặt load balancer, ingress controller hoặc reverse proxy trước ứng dụng Spring:

    Platform -- HTTPS --> Ingress -- HTTPS hoặc private protected hop --> Spring Broker

Trong mô hình này, platform xác thực certificate của ingress. Ingress giải mã TLS rồi chuyển request đến ứng dụng. Broker cần biết request ban đầu đến qua HTTPS để áp dụng chính sách an toàn, nhưng không được tin bất kỳ header forwarded nào từ một client tùy ý.

Các nguyên tắc:

- Chỉ nhận traffic đến application port từ ingress/proxy được tin cậy.
- Chỉ proxy tin cậy mới được thêm hoặc ghi đè Forwarded/X-Forwarded-Proto.
- Loại bỏ forwarded headers do client bên ngoài tự gửi trước khi proxy ghi header của mình.
- Không dùng X-Forwarded-Proto từ Internet làm bằng chứng request đã dùng HTTPS.
- Cấu hình Spring forwarded-header handling đúng với topology; không bật chế độ trust-all nếu ứng dụng có thể nhận traffic trực tiếp.
- Nếu có thể, dùng TLS trên cả hai chặng và xác thực proxy/application bằng network identity hoặc mTLS.

Không nên redirect một request Basic từ HTTP sang HTTPS như biện pháp bảo vệ duy nhất. Client có thể đã gửi Authorization header qua HTTP trước khi nhận redirect. Hãy chặn request HTTP trước khi nó đến tầng xử lý Basic Authentication.

## 6. Mutual TLS như lớp bảo vệ bổ sung

HTTP Basic là cơ chế xác thực client ở tầng HTTP. Mutual TLS (mTLS) bổ sung xác thực client ở tầng TLS bằng certificate của platform. Khi mTLS được bật:

1. Broker trình server certificate cho platform.
2. Platform xác minh certificate của broker.
3. Broker yêu cầu client certificate.
4. Platform gửi certificate của mình.
5. Broker hoặc ingress xác minh chain, issuer, SAN và trạng thái certificate.
6. Sau khi TLS handshake thành công, HTTP Basic vẫn có thể được dùng để ánh xạ platform registration theo hợp đồng OSB.

mTLS hữu ích khi cần xác thực thiết bị/hệ thống ở tầng kết nối, nhưng làm tăng yêu cầu quản lý certificate, trust store, gia hạn và thu hồi. Không nên tự coi một certificate hợp lệ là quyền truy cập toàn bộ service instance; vẫn cần mapping identity và authorization.

Không phải mọi platform đều hỗ trợ mTLS cho Service Broker registration. Chỉ bật yêu cầu client certificate khi platform và ingress đã được cấu hình đồng bộ. Nếu không, platform sẽ không thể thiết lập kết nối ngay cả khi Basic credentials đúng.

## 7. Triển khai HTTP Basic bằng Spring Security

Spring Security có thể bảo vệ các route OSB bằng HTTP Basic. Với broker API stateless, mỗi request mang Authorization header; không cần tạo session trình duyệt.

Ví dụ cấu hình nền tảng:

    @Configuration
    @EnableWebSecurity
    public class BrokerSecurityConfiguration {

        @Bean
        SecurityFilterChain osbApiSecurity(HttpSecurity http) throws Exception {
            http
                .securityMatcher("/v2/**")
                .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(csrf -> csrf.disable());

            return http.build();
        }
    }

Ví dụ này giả định các endpoint OSB nằm dưới /v2/** và broker không dùng cookie/session để xác thực API. CSRF có thể tắt cho nhóm API stateless dùng Basic credentials trong Authorization header, nhưng không nên áp dụng cấu hình này cho trang quản trị dùng cookie session. Quản trị UI cần filter chain và chính sách CSRF riêng.

### 7.1. Nguồn lưu credential

Trong môi trường thực tế, không nên dùng user mặc định hoặc password sinh tự động của Spring Boot. Credential platform cần được quản lý theo registration và có thể tra cứu từ database bảo vệ hoặc secret store.

Một credential record có thể gồm:

    BrokerClientCredential
      username
      passwordHash
      platformId
      active
      credentialVersion
      createdAt
      expiresAt
      lastAuthenticatedAt

Password nên là secret ngẫu nhiên có entropy cao, được lưu dưới dạng hash có salt bằng password hashing function phù hợp như BCrypt, Argon2id hoặc scrypt. Không dùng SHA-256 đơn giản làm password hash vì đây là hàm quá nhanh đối với việc dò mật khẩu. Với secret machine-to-machine dài và ngẫu nhiên, lựa chọn thuật toán và tham số cần phù hợp với thư viện, chính sách vận hành và yêu cầu kiểm tra của tổ chức.

Spring Security có thể dùng UserDetailsService và PasswordEncoder để xác thực. Ví dụ minh họa:

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(12);
    }

    @Bean
    UserDetailsService brokerUsers(BrokerCredentialRepository repository) {
        return username -> repository.findActiveByUsername(username)
            .map(record -> User.withUsername(record.username())
                .password(record.passwordHash())
                .authorities("OSB_PLATFORM")
                .disabled(!record.active())
                .build())
            .orElseThrow(() ->
                new UsernameNotFoundException("Invalid credentials"));
    }

Đây là ví dụ cấu trúc. Trong production, cần xử lý trường hợp username không tồn tại sao cho không tạo khác biệt dễ khai thác qua thời gian phản hồi, dùng password encoder đúng cách và kiểm tra credential status/expiry. Nếu có nhiều platform, Authentication principal nên chứa platform ID đã được tra cứu từ credential record.

### 7.2. Không tự viết Basic parser nếu không cần

Spring Security đã xử lý cú pháp header, decode và tích hợp authentication manager. Tự viết filter giải mã Base64 và so sánh chuỗi password dễ gây lỗi:

- Chấp nhận header sai định dạng.
- So sánh secret bằng phép so sánh không an toàn.
- Bỏ qua password encoder.
- Không xử lý account disabled hoặc credential rotation.
- Log nhầm header hoặc thông tin đăng nhập.
- Tạo khác biệt response cho username tồn tại và không tồn tại.

Chỉ viết custom AuthenticationProvider khi cần tra cứu credential theo platform registration hoặc tích hợp secret manager. Vẫn nên để Spring Security quản lý filter chain và lifecycle authentication.

## 8. Cấu hình TLS trong Spring Boot và môi trường triển khai

Nếu Spring Boot trực tiếp terminate TLS, cấu hình server SSL và keystore trong secret mount. Nếu ingress terminate TLS, ứng dụng cần giới hạn network access và cấu hình forwarded headers theo proxy đáng tin cậy.

Ví dụ cấu hình dạng YAML:

    server:
      port: 8443
      ssl:
        enabled: true
        key-store: file:/run/secrets/broker-keystore.p12
        key-store-type: PKCS12
        key-store-password: "<injected-secret>"
        enabled-protocols:
          - TLSv1.3
          - TLSv1.2

Kiểm tra tên thuộc tính theo phiên bản Spring Boot đang sử dụng. Không phải mọi ingress hoặc runtime đều cần ứng dụng tự terminate TLS. Cần xác định một điểm kết thúc TLS rõ ràng và bảo vệ mọi hop tiếp theo.

Trong Kubernetes:

- Lưu TLS certificate/private key trong Kubernetes Secret hoặc tích hợp external secret manager.
- Giới hạn RBAC để chỉ ingress/controller hoặc broker pod cần thiết đọc secret.
- Dùng NetworkPolicy để chỉ ingress và thành phần quản trị tin cậy truy cập broker service.
- Không đưa Basic password vào ConfigMap; dùng Secret hoặc external secret.
- Không mount toàn bộ secret vào container nếu process chỉ cần một credential cụ thể.

Trong Cloud Foundry:

- Đăng ký broker bằng HTTPS URL và credential do broker cấp.
- Dùng cơ chế platform quản lý thông tin đăng nhập broker.
- Kiểm tra certificate chain từ network path của Cloud Controller/platform đến broker.
- Khi thay credential hoặc certificate, thực hiện theo quy trình registration và rotation được platform hỗ trợ.

## 9. Quản lý và xoay vòng Basic credentials

Credential broker có thể tồn tại lâu trong cấu hình platform. Nếu bị lộ, người khác có thể gọi API bằng quyền của platform registration đó. Cần có chính sách rotation định kỳ và khi có dấu hiệu compromise.

Quy trình rotation an toàn có thể gồm:

1. Tạo credential mới cho cùng platform registration hoặc tạo một credential version mới.
2. Lưu password mới vào secret manager và cập nhật cấu hình platform theo quy trình hỗ trợ.
3. Trong thời gian chuyển đổi, chỉ cho phép credential cũ và mới cùng hoạt động nếu hệ thống cần overlap; đặt thời hạn overlap ngắn và có audit.
4. Kiểm tra request mới đã xác thực bằng credential mới.
5. Thu hồi credential cũ.
6. Ghi nhận thời điểm, người thực hiện, platform registration và credential version.

Không xoay đồng loạt credential của mọi platform nếu chỉ một registration bị ảnh hưởng. Không gửi password mới qua email hoặc log. Không lưu password rõ để có thể hiển thị lại; chỉ hiển thị một lần khi tạo hoặc cung cấp qua secret manager.

Nếu phát hiện credential bị lộ:

- Vô hiệu hóa credential bị ảnh hưởng theo mức độ khẩn cấp.
- Cấp credential thay thế và cập nhật platform.
- Kiểm tra audit log để xác định request bất thường.
- Rà soát binding/instance operations được gọi trong khoảng thời gian nghi ngờ.
- Xoay các secret khác nếu có bằng chứng chúng bị lộ cùng lúc.

## 10. Phòng chống dò mật khẩu và lạm dụng API

OSB broker là API machine-to-machine, nhưng vẫn có thể bị dò credential hoặc gửi request quá mức. Các biện pháp phù hợp:

- Dùng username/password dài, ngẫu nhiên và riêng cho từng platform.
- Rate limit theo source network, platform identity hoặc credential identity.
- Theo dõi số lần xác thực thất bại và cảnh báo khi vượt ngưỡng.
- Áp dụng lockout hoặc cooldown thận trọng; tránh để attacker cố tình khóa credential hợp lệ bằng cách gửi sai password liên tục.
- Giới hạn kích thước request body, thời gian xử lý và số request đồng thời.
- Chỉ mở endpoint OSB trên network cần thiết.
- Cập nhật Spring Boot, Spring Security, TLS library và reverse proxy.
- Không bật debug logging cho security headers trong production.

Không chỉ dựa vào IP allowlist vì platform có thể chạy trên hạ tầng có IP thay đổi hoặc dùng NAT. Network restriction là lớp bổ sung; Basic Authentication và TLS vẫn cần được cấu hình đúng.

## 11. Xử lý response khi xác thực thất bại

Khi không có Authorization header, header sai định dạng hoặc credentials không hợp lệ, broker phải từ chối request trước khi gọi nghiệp vụ hoặc provider. Response thường dùng HTTP 401 Unauthorized; với HTTP Basic, có thể trả challenge:

    HTTP/1.1 401 Unauthorized
    WWW-Authenticate: Basic realm="service-broker"
    Content-Type: application/json

    {
      "error": "Unauthorized",
      "description": "Valid broker credentials are required."
    }

Nếu caller đã xác thực nhưng không có quyền trên platform scope hoặc tài nguyên, trả 403 Forbidden. Không trả 404 chỉ để che giấu quyền nếu điều đó làm sai hợp đồng hoặc gây khó hiểu cho platform; chính sách che giấu resource existence cần được áp dụng nhất quán và không được làm rò rỉ dữ liệu.

Response không được phân biệt chi tiết rằng username tồn tại nhưng password sai hay username không tồn tại. Description nên chung chung. Không đưa password, username nhạy cảm, hash, credential version hoặc thông tin xác thực provider vào response.

Authentication failure phải dừng trước các side effect. Một request có Basic credentials sai không được tạo operation, gọi provider, thay đổi binding hoặc cập nhật trạng thái service instance.

## 12. Bảo vệ log, trace và telemetry

Authorization là header nhạy cảm. Nhiều reverse proxy, access logger và tracing agent có thể ghi request headers theo mặc định. Cần rà soát toàn bộ đường đi của request:

- Tắt hoặc mask Authorization trong access log.
- Không log raw request headers ở exception handler.
- Không đưa username/password hoặc Base64 token vào trace attributes.
- Không ghi Basic credentials vào metric labels.
- Không lưu request dump trong hệ thống hỗ trợ nếu chưa loại bỏ secret.
- Hạn chế quyền truy cập log và áp dụng retention phù hợp.
- Ghi principal ID, platform ID và kết quả xác thực thay vì credential.

Log hữu ích có thể gồm:

    event=broker_authentication
    principal_id=broker-client-17
    platform_id=cf-prod-east
    result=SUCCESS
    request_id=req-82f1
    timestamp=2026-11-27T10:00:00Z

Không ghi header Authorization. Với thất bại, có thể ghi source network, kết quả generic và correlation ID; không ghi password hoặc header đã decode.

## 13. Kiểm thử HTTP Basic và TLS

Kiểm thử cần bao phủ cả authentication, authorization và transport security:

1. Request HTTPS có Basic credentials hợp lệ truy cập được catalog.
2. Request thiếu Authorization nhận 401 và Basic challenge phù hợp.
3. Username/password sai nhận 401 với message chung.
4. Credential bị disable hoặc hết hạn không thể gọi OSB API.
5. Credential của platform A không thể đọc hoặc thay đổi instance thuộc platform B.
6. Tất cả endpoint /v2/** đều yêu cầu authentication, bao gồm catalog và last_operation.
7. Request đã xác thực nhưng thiếu quyền nhận 403.
8. Request HTTP thuần bị chặn trước khi Authorization header đến ứng dụng.
9. Certificate hết hạn, sai hostname hoặc CA không tin cậy làm TLS handshake thất bại.
10. Certificate hợp lệ với SAN đúng kết nối thành công.
11. Nếu dùng mTLS, client certificate không tin cậy bị từ chối ở TLS handshake.
12. TLS protocol yếu bị vô hiệu hóa theo baseline môi trường.
13. Credential rotation cho phép chuyển đổi theo quy trình và credential cũ bị thu hồi đúng thời điểm.
14. Access log, application log và tracing không chứa Authorization header.
15. Authentication failure không tạo operation hoặc gọi provider.
16. Reverse proxy loại bỏ forwarded headers không tin cậy và chỉ ghi header từ proxy được cấu hình.

Ví dụ kiểm tra bằng curl:

    curl --cacert broker-ca.pem \
      --user platform-a \
      https://broker.example.com/v2/catalog

Khi không truyền password sau username, curl có thể yêu cầu nhập password tương tác. Không dùng tùy chọn bỏ qua certificate validation trong kiểm thử production. Với mTLS, có thể bổ sung client certificate và private key theo cấu hình platform:

    curl --cacert broker-ca.pem \
      --cert platform-client.crt \
      --key platform-client.key \
      --user platform-a \
      https://broker.example.com/v2/catalog

Không đặt password trực tiếp trong command line vì process list, shell history hoặc log có thể ghi lại giá trị. Dùng prompt, secret manager hoặc cơ chế credential injection của môi trường kiểm thử.

## 14. Lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng Basic qua HTTP | Username/password có thể bị đọc trên đường truyền | Chỉ cho phép HTTPS và chặn HTTP trước khi xử lý |
| Nghĩ Base64 là mã hóa | Credential bị lộ khi decode header | Coi Authorization là secret và bảo vệ bằng TLS |
| Chỉ bảo vệ endpoint mutation | Catalog hoặc last_operation có thể bị truy cập trái phép | Áp dụng auth cho toàn bộ OSB API |
| Dùng chung một credential cho mọi platform | Khó thu hồi và audit theo platform | Credential riêng cho từng registration |
| Dùng provider token làm broker password | Trộn hai trust boundary và phạm vi quyền | Quản lý credential riêng cho từng kết nối |
| Lưu password rõ trong database/config | Tăng nguy cơ lộ secret | Dùng password hash hoặc secret manager phù hợp |
| Log Authorization header | Lộ Basic credentials qua log/trace | Mask hoặc loại bỏ header ở mọi tầng |
| Chỉ xác thực mà không kiểm tra platform scope | Platform có thể truy cập tài nguyên của platform khác | Gắn principal với platform ID và kiểm tra ownership |
| Redirect HTTP sang HTTPS sau khi nhận request | Header có thể đã đi qua HTTP | Chặn HTTP tại ingress/listener |
| Tin mọi X-Forwarded-Proto | Client có thể giả mạo thông tin scheme | Chỉ tin forwarded headers từ proxy tin cậy |
| Bật mTLS khi platform chưa hỗ trợ | Platform không thể kết nối broker | Chỉ bật sau khi cấu hình đồng bộ hai phía |
| Không có quy trình rotation | Credential cũ tồn tại quá lâu | Xoay vòng, overlap ngắn và thu hồi có audit |

## 15. Checklist triển khai

Trước khi đưa broker vào sử dụng, xác nhận:

- Platform registration có URL HTTPS và credential riêng.
- Basic Authentication được bật cho tất cả endpoint OSB.
- Credential được lưu và so sánh bằng cơ chế an toàn.
- Principal sau xác thực được gắn với platform scope.
- Broker kiểm tra quyền trên service instance và binding trước khi thao tác.
- TLS certificate có SAN đúng, chain tin cậy và thời hạn hợp lệ.
- TLS protocol yếu bị vô hiệu hóa.
- HTTP thuần bị chặn, không chỉ redirect.
- TLS termination và forwarded-header trust được cấu hình đúng.
- Provider credentials và application binding credentials được quản lý tách biệt.
- Authorization header bị loại khỏi log, trace và metric.
- Có quy trình cấp mới, rotation, revoke và xử lý compromise.
- Có kiểm thử auth failure, TLS failure, cross-platform access và credential rotation.

## 16. Kết luận

Theo hợp đồng OSB, platform xác thực với service broker bằng HTTP Basic Authentication. Broker phải kiểm tra credentials trên toàn bộ API OSB, ánh xạ caller thành platform identity và kiểm tra quyền trên từng service instance/binding. Vì Basic chỉ dùng Base64 để biểu diễn username/password, toàn bộ request phải đi qua HTTPS với TLS certificate được xác minh đúng hostname và trust chain. Spring Security có thể bảo vệ các route /v2/** theo mô hình stateless; credential cần được quản lý riêng theo platform registration, lưu an toàn, xoay vòng và loại khỏi log. Mutual TLS có thể bổ sung xác thực client ở tầng kết nối khi platform hỗ trợ. Kết hợp đúng Basic Authentication, TLS và authorization theo platform scope giúp broker bảo vệ các thao tác provision, update, deprovision và binding trong môi trường Cloud Foundry hoặc Kubernetes.
