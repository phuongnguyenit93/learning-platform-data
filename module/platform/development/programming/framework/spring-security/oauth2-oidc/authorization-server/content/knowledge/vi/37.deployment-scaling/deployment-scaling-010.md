# Health check, readiness, graceful shutdown và rolling deployment

Một OAuth 2.0 / OpenID Connect Authorization Server là điểm tin cậy trung tâm: nó xác thực người dùng, kiểm tra client, ghi nhận consent, cấp authorization code và token, đồng thời công bố metadata cùng khóa công khai để các bên khác xác minh token. Khi chạy nhiều replica hoặc triển khai phiên bản mới, hệ thống phải tiếp tục xử lý các luồng đang diễn ra và bảo đảm mọi replica có cùng trạng thái bảo mật.

Trong module **Spring Security OAuth2/OIDC Authorization Server**, phần triển khai và mở rộng bao gồm việc thiết kế health check, readiness, graceful shutdown và rolling deployment. Các cơ chế này phối hợp với Spring Boot Actuator, Spring Security, nơi lưu trữ authorization, nguồn khóa ký và nền tảng điều phối như Kubernetes. Mục tiêu là để hệ thống chỉ nhận traffic khi đã sẵn sàng, rút một instance khỏi traffic có kiểm soát và thay phiên bản mà không làm hỏng luồng OAuth/OIDC.

## 1. Vì sao Authorization Server cần quy trình triển khai có kiểm soát?

Một ứng dụng web thông thường có thể chỉ cần kiểm tra tiến trình còn chạy và trả HTTP. Authorization Server có thêm trạng thái và tài nguyên bảo mật cần được đồng bộ giữa các instance.

| Thành phần | Vai trò trong Authorization Server | Rủi ro khi triển khai nhiều replica |
|---|---|---|
| **RegisteredClientRepository** | Đọc cấu hình client, redirect URI, grant type, scope và chính sách token | Replica dùng dữ liệu client khác nhau có thể chấp nhận hoặc từ chối cùng một request khác nhau |
| **OAuth2AuthorizationService** | Lưu authorization code, access token, refresh token và trạng thái authorization | Authorization code được tạo ở replica này nhưng không được replica khác tìm thấy; refresh token hoặc revoke không nhất quán |
| **OAuth2AuthorizationConsentService** | Lưu consent của người dùng cho client và scope | Người dùng bị hỏi consent lặp lại hoặc các replica áp dụng trạng thái consent khác nhau |
| Nguồn khóa ký (**JWKSource**) | Ký JWT và công bố JWKS để resource server xác minh | Token do replica A ký có thể không được replica B hoặc resource server xác minh |
| HTTP session | Giữ phiên đăng nhập và một phần trạng thái tương tác với người dùng | Request tiếp theo sang replica khác có thể mất phiên hoặc buộc người dùng đăng nhập lại |
| Cấu hình issuer và endpoint | Công bố địa chỉ Authorization Server trong OIDC Discovery và token | Replica có thể phát token với issuer hoặc metadata không nhất quán |
| Database, cache, KMS hoặc dịch vụ cấu hình | Cung cấp dữ liệu và tài nguyên để xử lý luồng ủy quyền | Một instance có thể khởi động thành công nhưng chưa đủ khả năng cấp token |

Vì vậy, trạng thái “process đang chạy” chưa đủ để kết luận một replica có thể nhận request. Cần phân biệt tiến trình khỏe, ứng dụng đã khởi động xong và ứng dụng có thể phục vụ traffic.

## 2. Phân biệt liveness, readiness và startup probe

Ba loại probe giải quyết ba câu hỏi khác nhau. Cấu hình sai có thể khiến Kubernetes liên tục khởi động lại ứng dụng khi database gặp sự cố, hoặc đưa một replica chưa có khóa ký vào Service.

| Probe | Câu hỏi | Khi thất bại | Kiểm tra phù hợp |
|---|---|---|---|
| Liveness | Process còn hoạt động và có thể tiếp tục xử lý không? | Nền tảng khởi động lại container | Trạng thái tiến trình, khả năng phục vụ nội bộ, lỗi khiến ứng dụng không thể tự phục hồi |
| Readiness | Instance có thể nhận request nghiệp vụ ngay lúc này không? | Nền tảng ngừng gửi traffic mới đến instance | Trạng thái sẵn sàng của Spring, database cần thiết, nguồn khóa ký và cấu hình bắt buộc |
| Startup | Ứng dụng đã hoàn tất khởi động chưa? | Nền tảng tiếp tục chờ hoặc khởi động lại nếu vượt thời hạn | Thời gian nạp cấu hình, khởi tạo Spring context, kết nối tài nguyên ban đầu và migration được kiểm soát |

### 2.1. Liveness: xác định ứng dụng có thể tự tiếp tục hoạt động

Liveness nên phản ánh khả năng tiến trình tiếp tục chạy. Ví dụ, ứng dụng bị deadlock, một thành phần nền tảng thiết yếu không thể tiến triển hoặc HTTP server không còn phục vụ request thì liveness có thể chuyển sang **DOWN**.

Không nên đưa mọi phụ thuộc bên ngoài vào liveness. Nếu database tạm thời mất kết nối, việc đánh dấu liveness **DOWN** sẽ khiến Kubernetes restart tất cả replica. Các instance mới vẫn không thể kết nối database, tạo ra vòng lặp restart và làm tình trạng quá tải nặng hơn. Một lỗi phụ thuộc có thể khiến instance chưa sẵn sàng, nhưng restart process không nhất thiết khắc phục được lỗi đó.

### 2.2. Readiness: xác định instance có thể nhận traffic

Readiness phải phản ánh các điều kiện thực sự cần để xử lý request. Với Authorization Server, các điều kiện thường gồm:

- Spring ApplicationContext đã khởi tạo và ứng dụng đã hoàn tất bước chuẩn bị ban đầu.
- Database có thể truy cập nếu client, authorization hoặc consent được lưu tại đó.
- **RegisteredClientRepository**, **OAuth2AuthorizationService** và **OAuth2AuthorizationConsentService** đã được cấu hình đúng và dùng kho dữ liệu dùng chung.
- Có khóa ký hợp lệ nếu instance cần phát JWT.
- Cấu hình issuer, redirect URI, endpoint và các secret bắt buộc đã được nạp.
- Session store có thể truy cập nếu hệ thống dùng session tập trung để duy trì đăng nhập.

Không phải mọi dịch vụ tích hợp đều cần nằm trong readiness. Chỉ đưa vào nhóm này những phụ thuộc mà khi mất chúng, instance thực sự không thể thực hiện vai trò được giao. Ví dụ, một hệ thống có thể vẫn phục vụ JWKS và discovery khi một nhà cung cấp đăng nhập liên kết bị gián đoạn; trong trường hợp đó, việc đưa nhà cung cấp ấy vào readiness có thể loại instance khỏi traffic rộng hơn mức cần thiết.

Health indicator phải phản ánh tình trạng thật và trả kết quả nhanh. Tránh thực hiện một luồng đăng nhập hoặc cấp token đầy đủ mỗi vài giây chỉ để kiểm tra sức khỏe.

### 2.3. Startup probe: dành thời gian cho quá trình khởi động

Một replica mới có thể cần thời gian để tạo Spring context, đọc secret, khởi tạo connection pool hoặc nạp khóa từ KMS. Nếu liveness bắt đầu quá sớm, Kubernetes có thể restart ứng dụng trước khi nó có cơ hội khởi động xong.

Startup probe tạo khoảng thời gian khởi động riêng. Khi startup probe chưa thành công, Kubernetes chưa dùng liveness và readiness để đánh giá container. Sau khi startup probe thành công, hai probe còn lại tiếp tục điều khiển vòng đời instance.

## 3. Cấu hình health endpoint bằng Spring Boot Actuator

Thêm Spring Boot Actuator vào ứng dụng để cung cấp endpoint health. Chỉ công bố những endpoint thực sự cần cho vận hành.

Ví dụ **application.properties**:

~~~properties
management.endpoints.web.exposure.include=health,info

# Bật health group cho liveness và readiness.
management.endpoint.health.probes.enabled=true

# Không trả chi tiết về dependency hoặc exception cho request health công khai.
management.endpoint.health.show-details=never
management.endpoint.health.show-components=never

# Readiness gồm trạng thái Spring, database và health indicator khóa ký.
# Chỉ dùng db khi database là dependency bắt buộc của request nghiệp vụ.
management.endpoint.health.group.readiness.include=readinessState,db,signingKeys

# Dừng nhận request mới và chờ request đang xử lý hoàn tất khi shutdown.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Khi bật health probes, Spring Boot cung cấp hai nhóm:

- **/actuator/health/liveness**
- **/actuator/health/readiness**

Nhóm readiness mặc định phản ánh **ReadinessState**; ví dụ trên bổ sung health contributor **db** và **signingKeys**. Chỉ khai báo **signingKeys** khi ứng dụng đã có bean health indicator tương ứng. Nếu không dùng database hoặc một dependency không bắt buộc, điều chỉnh danh sách **include** theo kiến trúc thực tế. Không thêm các contributor chỉ vì chúng tồn tại.

Từ Spring Boot 3.2, có thể cấu hình thêm:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

Cấu hình này tạo thêm **/livez** và **/readyz** trên cổng HTTP chính của ứng dụng. Nó hữu ích khi management endpoint chạy ở một cổng riêng: probe đi qua cổng chính sẽ kiểm tra được khả năng phục vụ của HTTP server nghiệp vụ, thay vì chỉ chứng minh cổng quản trị vẫn hoạt động.

Nếu dùng management port riêng, cần xác định rõ Kubernetes probe sẽ gọi cổng nào và bảo vệ cổng quản trị bằng network policy hoặc cơ chế truy cập nội bộ. Một management port vẫn trả health thành công trong khi cổng HTTP chính đã lỗi sẽ tạo tín hiệu readiness sai.

### 3.1. Tạo health indicator cho nguồn khóa ký

Spring Boot có health contributor cho một số tài nguyên phổ biến, chẳng hạn **DataSource**. Với tài nguyên riêng của Authorization Server, có thể tạo **HealthIndicator** để kiểm tra nguồn khóa ký.

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("signingKeys")
public class SigningKeysHealthIndicator implements HealthIndicator {

    private final SigningKeyRegistry signingKeyRegistry;

    public SigningKeysHealthIndicator(SigningKeyRegistry signingKeyRegistry) {
        this.signingKeyRegistry = signingKeyRegistry;
    }

    @Override
    public Health health() {
        if (signingKeyRegistry.hasUsableSigningKey()) {
            return Health.up().build();
        }

        return Health.down()
                .withDetail("reason", "No active signing key")
                .build();
    }
}
~~~

**SigningKeyRegistry** trong ví dụ là abstraction của ứng dụng, chịu trách nhiệm xác định có khóa ký đang hoạt động và còn hợp lệ hay không. Phần kiểm tra nên dùng trạng thái đã nạp hoặc một thao tác nhẹ. Nếu khóa nằm trong KMS, không nên tạo một request tốn kém đến KMS cho mỗi lần Kubernetes gọi probe; có thể kiểm tra trạng thái kết nối theo chu kỳ và cập nhật trạng thái nội bộ.

Health endpoint chỉ trả thông tin vận hành cần thiết. Không đưa private key, secret, access token, refresh token, thông tin kết nối database hoặc exception chứa dữ liệu nhạy cảm vào response.

### 3.2. Bảo vệ endpoint Actuator

Kubernetes cần truy cập health endpoint, nhưng các endpoint quản trị khác không nên trở thành API công khai. Có thể tách một **SecurityFilterChain** cho Actuator và đặt nó trước các filter chain nghiệp vụ.

~~~java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(0)
SecurityFilterChain actuatorSecurityFilterChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher(EndpointRequest.toAnyEndpoint())
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(EndpointRequest.to("health")).permitAll()
            .anyRequest().hasRole("OPS")
        )
        .httpBasic(Customizer.withDefaults());

    return http.build();
}
~~~

Ví dụ cho phép health endpoint để kubelet gọi probe và yêu cầu quyền vận hành đối với endpoint Actuator khác. Tài khoản vận hành phải được cấu hình trong hệ thống xác thực phù hợp; cổng quản trị cũng nên được giới hạn ở mạng nội bộ. Việc cho phép truy cập health không đồng nghĩa cho phép truy cập các endpoint quản trị khác.

Nếu ứng dụng có nhiều **SecurityFilterChain**, hãy kiểm tra thứ tự và matcher của từng chain. Chain dành cho Authorization Server không được bắt request Actuator trước chain quản trị. Cũng cần kiểm tra đường dẫn health group thực tế sau khi thay đổi **management.endpoints.web.base-path**.

## 4. Các phụ thuộc cần đồng nhất giữa các replica

Health check chỉ phát hiện một phần vấn đề. Để rolling deployment an toàn, các replica phải dùng trạng thái và cấu hình tương thích.

### 4.1. Dùng kho lưu trữ dùng chung cho client, authorization và consent

Trong môi trường nhiều replica, dữ liệu sau cần được lưu tại kho dùng chung:

- Client đăng ký trong **RegisteredClientRepository**.
- Authorization trong **OAuth2AuthorizationService**, bao gồm trạng thái authorization code, access token và refresh token.
- Consent trong **OAuth2AuthorizationConsentService**.

Nếu mỗi replica dùng implementation in-memory, request authorize có thể được xử lý ở replica A nhưng request token tiếp theo đến replica B không tìm thấy authorization code. Refresh token, revoke hoặc consent cũng có thể có kết quả khác nhau tùy instance nhận request.

Với database dùng chung, mọi replica đọc và ghi trên cùng nguồn dữ liệu. Cần cấu hình connection pool hợp lý, timeout, retry có giới hạn và cơ chế xử lý khi database failover. Không retry vô hạn request ghi dữ liệu.

Cache client hoặc authorization có thể giúp giảm tải, nhưng phải có quy tắc invalidation, thời gian sống và xử lý revoke rõ ràng. Một cache cục bộ không được làm cho client đã bị vô hiệu hóa hoặc token đã bị thu hồi tiếp tục được chấp nhận quá thời hạn chính sách.

### 4.2. Giữ issuer ổn định

Issuer là định danh công khai của Authorization Server. Giá trị này phải giống nhau giữa mọi replica và khớp với địa chỉ công khai mà client và resource server sử dụng.

Có thể khai báo rõ issuer bằng **AuthorizationServerSettings**:

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

Không tạo issuer từ hostname, IP nội bộ hoặc tên pod. Khi đặt sau reverse proxy hoặc ingress, cần cấu hình xử lý forwarded headers đúng cách để ứng dụng hiểu scheme và host công khai. OIDC Discovery và claim **iss** trong token phải nhất quán giữa các replica.

### 4.3. Dùng nguồn khóa ký nhất quán và xoay khóa có thời gian chuyển tiếp

Mọi replica cần truy cập cùng một bộ khóa hoặc cùng một dịch vụ quản lý khóa. Có thể dùng secret store được bảo vệ, KMS hoặc hệ thống quản lý khóa phù hợp. Không tạo khóa ký ngẫu nhiên riêng khi mỗi pod khởi động: token được replica A ký có thể không xác minh được khi public key do replica B công bố.

Khi xoay khóa:

1. Tạo khóa mới với **kid** duy nhất và đưa public key mới vào JWKS.
2. Chờ các bên tiêu thụ JWKS có thời gian tải khóa mới.
3. Chuyển hoạt động ký sang khóa mới.
4. Giữ public key cũ trong JWKS ít nhất đến khi token được ký bằng khóa cũ hết hạn, cộng thêm clock skew và khoảng thời gian cache JWKS.
5. Chỉ gỡ khóa cũ khi không còn token hợp lệ nào cần xác minh bằng khóa đó.

Không công bố private key trong JWKS. Kiểm tra readiness nên xác nhận instance có thể dùng khóa ký đang hoạt động; nó cũng nên phát hiện trường hợp khóa đã hết hạn hoặc cấu hình thuật toán không phù hợp.

### 4.4. Chia sẻ session khi luồng đăng nhập cần session

Authorization endpoint thường tương tác với phiên đăng nhập của người dùng. Nếu session chỉ nằm trong bộ nhớ của một pod, request tiếp theo chuyển sang pod khác có thể mất phiên. Có thể dùng Spring Session với Redis hoặc JDBC để chia sẻ session giữa các replica.

Sticky session có thể giảm số lần request đổi pod, nhưng không thay thế session store dùng chung: pod vẫn có thể bị restart, scale down hoặc mất kết nối. Nếu chấp nhận người dùng phải đăng nhập lại khi pod kết thúc, cần hiểu đó là hành vi sản phẩm đã chọn và kiểm thử luồng authorize tương ứng.

## 5. Graceful shutdown trong Spring Boot

Khi một pod được thay thế, ứng dụng cần có thời gian hoàn tất request đang xử lý. Nếu process kết thúc ngay, response token hoặc redirect có thể bị ngắt giữa chừng.

Với Spring Boot có hỗ trợ graceful shutdown, cấu hình:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Khi nhận tín hiệu shutdown, web server ngừng nhận kết nối hoặc request mới theo cơ chế của server và chờ các request đang xử lý hoàn tất trong khoảng thời gian cấu hình. Sau thời hạn đó, quá trình shutdown tiếp tục.

Trình tự kết thúc một pod trong môi trường Kubernetes thường gồm:

1. Pod được đánh dấu đang terminate và ngừng được chọn làm endpoint phục vụ traffic mới.
2. **preStop** hook, nếu có, được thực thi.
3. Container nhận **SIGTERM**.
4. Spring Boot thực hiện graceful shutdown và chờ request đang chạy.
5. Nếu hết **terminationGracePeriodSeconds**, Kubernetes có thể gửi tín hiệu kết thúc cưỡng bức.

Thời gian chờ của Spring cần ngắn hơn **terminationGracePeriodSeconds**, để còn khoảng dự phòng cho hook và thao tác dọn dẹp của nền tảng. Ví dụ, nếu Spring chờ 30 giây, có thể đặt thời gian terminate của pod là 60 giây. Cần điều chỉnh theo thời gian xử lý request và quy trình thực tế.

Các endpoint **/oauth2/authorize**, **/oauth2/token**, **/oauth2/jwks** và OIDC Discovery có đặc điểm khác nhau. Request token thường cần trả kết quả nhanh; authorization endpoint có thể gắn với đăng nhập và redirect. Không nên giả định mọi client sẽ retry an toàn khi request bị ngắt. Authorization code là dữ liệu dùng một lần; retry request token mù quáng có thể nhận lỗi vì code đã được tiêu thụ hoặc trạng thái đã thay đổi.

Graceful shutdown cũng không thay thế việc lưu trạng thái authorization bền vững. Request có thể kết thúc đúng cách nhưng nếu authorization chỉ nằm trong bộ nhớ pod, trạng thái vẫn mất khi pod bị xóa.

## 6. Rolling deployment với Kubernetes

Rolling deployment thay từng nhóm pod bằng phiên bản mới. Kubernetes chỉ nên đưa pod mới vào Service sau khi readiness thành công; pod cũ được loại khỏi traffic khi bắt đầu terminate.

### 6.1. Cấu hình Deployment

Ví dụ dưới đây minh họa Deployment có ba replica, startup probe, readiness probe, liveness probe và thời gian graceful termination.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: authorization-server
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  minReadySeconds: 10
  progressDeadlineSeconds: 600
  selector:
    matchLabels:
      app: authorization-server
  template:
    metadata:
      labels:
        app: authorization-server
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: authorization-server
          image: registry.example.com/authorization-server:1.8.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 36
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
~~~

**maxSurge: 1** cho phép tạo thêm một pod trong lúc cập nhật. **maxUnavailable: 0** yêu cầu Kubernetes duy trì số replica sẵn sàng theo cấu hình trong quá trình rollout; cluster cần đủ tài nguyên để chạy pod mới. Nếu không đủ CPU, memory hoặc quota, rollout có thể bị kẹt vì pod mới không thể được tạo hoặc không thể trở nên ready.

**minReadySeconds** yêu cầu pod duy trì trạng thái ready trong một khoảng thời gian trước khi được tính là available. **progressDeadlineSeconds** giới hạn thời gian rollout được phép không tiến triển. Những giá trị này cần phù hợp với thời gian khởi động và khả năng phục hồi của ứng dụng.

Ví dụ dùng **/actuator/health/...**. Nếu đã bật **management.endpoint.health.probes.add-additional-paths=true** trên phiên bản Spring Boot hỗ trợ, có thể dùng **/livez** và **/readyz** trên cổng HTTP chính. Nếu Actuator dùng cổng riêng, thay **port** trong probe theo cấu hình thực tế và kiểm tra riêng khả năng phục vụ của cổng nghiệp vụ.

### 6.2. Luồng thay thế một replica

~~~mermaid
sequenceDiagram
    participant K as Kubernetes
    participant S as Service
    participant N as Pod mới
    participant O as Pod cũ

    K->>N: Tạo container phiên bản mới
    N-->>K: Startup probe thành công
    N-->>K: Readiness vẫn DOWN khi đang chuẩn bị
    Note over N: Nạp cấu hình, kiểm tra database và khóa ký
    N-->>K: Readiness UP
    K->>S: Thêm Pod mới vào endpoint phục vụ
    K->>O: Bắt đầu terminate Pod cũ
    Note over O: Pod cũ ngừng nhận traffic mới
    K->>O: Gửi SIGTERM
    O->>O: Graceful shutdown, chờ request đang chạy
    O-->>K: Process kết thúc
~~~

Khi pod mới chưa ready, Service tiếp tục chuyển traffic đến các pod đang sẵn sàng. Sau khi pod mới vượt qua readiness, nó được thêm vào endpoint phục vụ. Pod cũ sau đó được terminate và Spring Boot có thời gian drain request.

Đối với Authorization Server, quá trình này chỉ an toàn nếu các phiên bản cùng tương thích với database schema, client configuration, session store và khóa ký. Nếu phiên bản mới ghi dữ liệu mà phiên bản cũ không đọc được, rollout có thể gây lỗi ngay cả khi tất cả probe đều xanh.

## 7. Giữ tương thích dữ liệu và cấu hình khi rollout

Rolling deployment thường tạo ra giai đoạn hai phiên bản cùng chạy. Hãy thiết kế thay đổi theo hướng tương thích ngược và tiến.

### 7.1. Migration database theo kiểu expand-contract

Một quy trình an toàn thường có các bước:

1. **Expand:** thêm cột, bảng hoặc index mới theo cách phiên bản cũ vẫn hoạt động.
2. **Deploy tương thích:** phát hành ứng dụng có thể đọc/ghi theo schema mở rộng và vẫn xử lý dữ liệu cũ.
3. **Migrate dữ liệu:** chuyển đổi dữ liệu nếu cần, có kiểm tra tiến độ và khả năng tiếp tục.
4. **Contract:** chỉ xóa cột hoặc cấu trúc cũ sau khi mọi replica cũ đã ngừng chạy và không còn consumer nào phụ thuộc.

Không để mỗi pod tự chạy migration phá hủy cấu trúc dữ liệu khi các phiên bản đang chạy song song. Dùng quy trình migration có kiểm soát, khóa migration hoặc một bước triển khai riêng phù hợp với hệ thống.

### 7.2. Giữ cấu hình tương thích trong thời gian chuyển phiên bản

Các replica cần cùng hiểu những giá trị quan trọng như issuer, public endpoint, thuật toán ký, thời hạn token và cấu hình client. Khi đổi secret hoặc chứng thư, nên có khoảng thời gian chuyển tiếp để phiên bản cũ và mới cùng hoạt động.

Nếu thay đổi **kid**, khóa hoặc thuật toán ký, phối hợp thứ tự công bố JWKS và chuyển hoạt động ký. Nếu thay đổi cookie hoặc session serialization, bảo đảm phiên bản mới đọc được session do phiên bản cũ tạo trong suốt rollout.

### 7.3. Kiểm soát cache và trạng thái revoke

Cache cục bộ của từng pod có thể làm dữ liệu giữa các replica lệch nhau. Đặc biệt, việc vô hiệu hóa client, revoke token hoặc cập nhật consent cần có thời gian đồng bộ xác định. Nếu hệ thống dùng cache, hãy quy định TTL, invalidation và hành vi khi không nhận được sự kiện đồng bộ. Không để cache kéo dài thời gian chấp nhận một client hoặc token đã bị vô hiệu hóa vượt quá chính sách.

## 8. Kiểm tra rollout và theo dõi sau triển khai

Probe chỉ là tín hiệu tối thiểu để điều phối container. Vận hành Authorization Server còn cần theo dõi lỗi nghiệp vụ và khả năng tương tác với client, resource server.

Trước và sau rollout, kiểm tra các endpoint quan trọng:

~~~bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness

# OIDC Discovery, nếu đã bật OIDC.
curl -i https://auth.example.com/.well-known/openid-configuration

# JWK Set endpoint mặc định của Spring Authorization Server.
curl -i https://auth.example.com/oauth2/jwks
~~~

Trong môi trường Kubernetes:

~~~bash
kubectl rollout status deployment/authorization-server
kubectl get pods -l app=authorization-server -w
kubectl describe deployment authorization-server
~~~

Nếu rollout có vấn đề và cần quay lại phiên bản trước:

~~~bash
kubectl rollout undo deployment/authorization-server
~~~

Sau rollout, theo dõi tối thiểu:

- Tỷ lệ HTTP 5xx và độ trễ của **/oauth2/authorize**, **/oauth2/token**, discovery và JWKS.
- Tỷ lệ lỗi xác thực client, redirect URI, authorization code, refresh token và consent.
- Kết nối database, connection pool, timeout và lỗi ghi authorization.
- Trạng thái session store và số lần người dùng phải đăng nhập lại bất thường.
- Khả năng tải JWKS, số lượng **kid** được công bố và lỗi xác minh chữ ký ở resource server.
- Số replica ready, thời gian khởi động, số lần restart và số lần readiness chuyển trạng thái.
- Log shutdown để xác nhận request đang xử lý đã kết thúc trong thời hạn cho phép.

Có thể kiểm thử rollout trên môi trường staging bằng cách tạo authorization flow, đăng nhập, nhận authorization code, đổi code lấy token, dùng refresh token và xác minh JWT trong lúc thay replica. Kiểm tra cả trường hợp request đang chạy khi pod nhận **SIGTERM**. Với client thật, cần xác minh redirect URI và issuer trong discovery/token vẫn giữ nguyên sau khi thay phiên bản.

## 9. Các lỗi vận hành thường gặp

| Lỗi cấu hình hoặc triển khai | Biểu hiện | Cách xử lý |
|---|---|---|
| Đưa database vào liveness | Toàn bộ pod restart khi database tạm thời mất kết nối | Chuyển database sang readiness nếu đó là dependency bắt buộc |
| Readiness chỉ kiểm tra process | Pod nhận traffic dù chưa nạp khóa ký hoặc chưa kết nối database | Bổ sung health indicator cho dependency thiết yếu |
| Mỗi pod tự tạo khóa ký | JWT từ một pod không xác minh được ở pod khác | Dùng nguồn khóa dùng chung và quy trình xoay khóa có overlap |
| Dùng repository in-memory trong nhiều replica | Authorization code, refresh token hoặc consent không nhất quán | Dùng implementation lưu trữ dùng chung, bền vững |
| Session chỉ nằm trong bộ nhớ pod | Người dùng mất phiên khi request chuyển sang pod khác | Dùng session store dùng chung hoặc chấp nhận rõ hành vi đăng nhập lại |
| Management port vẫn khỏe khi HTTP port lỗi | Probe xanh nhưng request nghiệp vụ không đến được ứng dụng | Dùng probe trên cổng chính hoặc bổ sung đường dẫn **/livez**, **/readyz** |
| Endpoint health bị SecurityFilterChain chặn | Kubernetes nhận 401/403 và đánh dấu pod không ready | Tách chain Actuator, cho phép health có kiểm soát |
| Graceful shutdown dài hơn thời gian terminate của pod | Pod bị kill cưỡng bức trước khi drain xong | Đồng bộ timeout Spring với **terminationGracePeriodSeconds** |
| Schema mới không tương thích phiên bản cũ | Lỗi đọc/ghi trong lúc hai phiên bản cùng chạy | Dùng migration expand-contract |
| Issuer phụ thuộc hostname nội bộ | Discovery và claim **iss** khác địa chỉ công khai | Cấu hình issuer ổn định và xử lý forwarded headers đúng |

## 10. Checklist trước khi đưa Authorization Server vào production

- [ ] Liveness, readiness và startup probe có mục đích riêng, ngưỡng và timeout phù hợp.
- [ ] Readiness phản ánh database, nguồn khóa ký và các dependency thực sự cần để xử lý request.
- [ ] Liveness không phụ thuộc vào database hoặc dịch vụ bên ngoài có thể gián đoạn độc lập.
- [ ] Health endpoint không tiết lộ secret, token, private key hoặc thông tin hạ tầng nhạy cảm.
- [ ] Endpoint Actuator được giới hạn truy cập; Kubernetes có thể gọi probe đúng cổng và đường dẫn.
- [ ] **RegisteredClientRepository**, **OAuth2AuthorizationService** và **OAuth2AuthorizationConsentService** dùng kho lưu trữ phù hợp với nhiều replica.
- [ ] Issuer, endpoint công khai, cấu hình client và nguồn khóa ký nhất quán giữa các pod.
- [ ] Session được chia sẻ hoặc hành vi mất phiên khi pod kết thúc đã được chấp nhận và kiểm thử.
- [ ] Spring Boot graceful shutdown có timeout nhỏ hơn thời gian terminate của pod.
- [ ] Rolling update có đủ tài nguyên cho **maxSurge** và duy trì số replica ready theo yêu cầu.
- [ ] Database migration và cấu hình tương thích trong giai đoạn hai phiên bản chạy đồng thời.
- [ ] Quy trình xoay khóa giữ public key cũ đủ lâu để xác minh token còn hiệu lực.
- [ ] Đã kiểm thử authorization code, token, refresh token, consent, discovery và JWKS trong lúc rollout.
- [ ] Có dashboard và cảnh báo cho lỗi token, độ trễ, database, session, restart và readiness.

Health check cho biết một instance có thể tiếp tục chạy hoặc nhận traffic hay không. Graceful shutdown giúp instance rời khỏi hệ thống có kiểm soát. Rolling deployment phối hợp các cơ chế đó để thay phiên bản từng bước. Với Spring Authorization Server, độ an toàn của quá trình còn phụ thuộc vào việc chia sẻ authorization state, session, issuer và khóa ký giữa các replica; những phần này cần được thiết kế cùng với probe và chiến lược triển khai ngay từ đầu.

