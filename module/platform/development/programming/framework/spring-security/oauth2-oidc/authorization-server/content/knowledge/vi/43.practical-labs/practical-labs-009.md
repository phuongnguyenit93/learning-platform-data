# Triển khai đa instance sau proxy với issuer và session ổn định

Khi Spring Authorization Server chạy trên nhiều instance phía sau reverse proxy hoặc load balancer, mọi instance phải cùng đại diện cho một Authorization Server duy nhất. Client nhìn thấy một issuer, một domain HTTPS và một bộ endpoint công khai; các node phía sau xử lý request thay nhau mà không làm thay đổi danh tính máy chủ, mất phiên đăng nhập hoặc phát hành token không thể xác minh.

Bài thực hành xây dựng một triển khai gồm reverse proxy kết thúc TLS, hai instance Spring Authorization Server, PostgreSQL dùng chung cho client/authorization/consent, Redis dùng chung cho HTTP session và một bộ khóa ký ổn định. Mục tiêu là chứng minh người dùng có thể bắt đầu đăng nhập ở node A rồi tiếp tục ở node B, authorization code được cấp ở node này có thể đổi ở node kia, metadata luôn công bố cùng issuer và token từ bất kỳ node nào đều được xác minh bằng cùng JWKS.

Các nguyên tắc xuyên suốt:

- Issuer là định danh công khai cố định, không phụ thuộc node hoặc header tùy ý của request.
- Proxy biên xóa hoặc ghi đè forwarded headers do client gửi và chỉ backend nhận traffic từ proxy tin cậy.
- Mọi node dùng chung kho client, authorization, consent và signing key set.
- Nếu cần duy trì phiên đăng nhập qua nhiều node, HTTP session phải được chia sẻ hoặc có một chính sách reauthentication được chấp nhận rõ ràng.
- Load balancer chỉ gửi traffic đến node đã sẵn sàng; rollout và key rotation phải giữ tương thích trong thời gian chuyển tiếp.

## 1. Mục tiêu và topology triển khai

Kịch bản lab dùng domain auth.example.test, hai node ứng dụng và hai dependency dùng chung. Tên miền .test dành cho môi trường thử nghiệm; khi triển khai thật, thay bằng domain đã được kiểm soát.

~~~text
                     Browser / OAuth2 Clients
                               |
                               | HTTPS auth.example.test
                               v
                    +----------------------+
                    | Reverse Proxy / LB   |
                    | TLS + host allowlist |
                    | forwarded header     |
                    | normalization        |
                    +----------------------+
                         |            |
                  private HTTP   private HTTP
                         |            |
                         v            v
                +----------------+ +----------------+
                | Auth Server A  | | Auth Server B  |
                | same issuer    | | same issuer    |
                | same config    | | same key set   |
                +----------------+ +----------------+
                         |            |
              +----------+------------+-----------+
              |                                  |
              v                                  v
       +--------------+                  +---------------+
       | PostgreSQL   |                  | Redis         |
       | client       |                  | shared HTTP   |
       | authorization|                  | sessions      |
       | consent      |                  |               |
       +--------------+                  +---------------+
              |
              v
       Backup / monitoring

       KMS / HSM / Key Manager supplies the same active
       signing key set to both Authorization Server nodes.
~~~

| Thành phần | Trách nhiệm | Điều kiện HA |
|---|---|---|
| Reverse proxy/load balancer | TLS, host allowlist, routing, header normalization, health check | Có health check, drain node và chỉ tin upstream đã xác định |
| Authorization Server A/B | OAuth/OIDC endpoints, đăng nhập, consent, phát hành token | Cùng issuer, config, client policy, key set và dependency |
| PostgreSQL | RegisteredClient, OAuth2Authorization, consent | Có backup, failover, migration tương thích và giới hạn connection |
| Redis | HTTP session dùng chung nếu bật Spring Session | Có persistence/failover theo yêu cầu, ACL, TLS nội bộ và TTL |
| KMS/HSM/key manager | Private signing key và key lifecycle | Hai node có quyền sử dụng cùng key version; thao tác được audit |
| Resource Server/client | Xác minh access token/ID Token | Tin cùng issuer và lấy JWKS từ endpoint công khai ổn định |

Đừng gộp các loại state thành một khái niệm. PostgreSQL giữ trạng thái OAuth như authorization code, access token metadata, refresh token và consent. Redis giữ HTTP session như SecurityContext, trạng thái đăng nhập và dữ liệu web cần tiếp tục qua request. Signing key giữ tính liên tục của chữ ký JWT. Mỗi loại có vòng đời, quyền truy cập và cơ chế phục hồi riêng.

## 2. Issuer phải ổn định trên mọi node

Issuer là định danh của Authorization Server. Giá trị này xuất hiện trong metadata và claim iss của token. Với một hệ thống có domain công khai cố định, tất cả instance phải dùng cùng một giá trị tuyệt đối, bao gồm scheme, host và path nếu có.

Cấu hình tường minh:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.test")
            .build();
}
~~~

Không cấu hình issuer bằng địa chỉ nội bộ như http://auth-server-a:9000, localhost, hostname của container hoặc địa chỉ riêng của node. Không suy issuer từ Host, Forwarded hay X-Forwarded-Host chưa được xác thực.

Nếu dùng nhiều domain hoặc tenant, ánh xạ từng host đã được proxy xác thực sang issuer nằm trong allowlist. Không cho phép một client tự gửi Host tùy ý rồi khiến Authorization Server phát token mang issuer do client chọn.

### Kiểm tra issuer và metadata

Gọi metadata qua domain công khai:

~~~bash
curl -fsS https://auth.example.test/.well-known/openid-configuration
~~~

Đối chiếu ít nhất:

- issuer đúng chính xác https://auth.example.test.
- authorization_endpoint, token_endpoint, jwks_uri dùng HTTPS và domain công khai.
- Các endpoint không chứa hostname nội bộ, port backend hoặc path lặp.
- Hai node trả metadata giống nhau về issuer và endpoint.
- Claim iss của ID Token và JWT access token khớp issuer đã công bố theo profile của hệ thống.

Nếu OIDC không được bật, kiểm tra OAuth Authorization Server Metadata endpoint tương ứng. Không dùng endpoint discovery của OIDC để kết luận một tính năng OIDC đã được bật nếu cấu hình không hỗ trợ.

Một smoke test hữu ích là gọi domain công khai nhiều lần và xác minh response không thay đổi theo node được load balancer chọn. Có thể thêm header tạm trong môi trường test để nhận diện node phục vụ, nhưng không đưa thông tin hạ tầng nhạy cảm vào response production.

## 3. Thiết lập ranh giới tin cậy ở reverse proxy

Khi proxy kết thúc TLS, kết nối từ proxy đến Spring Authorization Server có thể là HTTP nội bộ. Ứng dụng cần biết request gốc của client dùng HTTPS, nhưng chỉ được tin thông tin đó khi request thực sự đi qua proxy được phép.

Proxy biên phải:

1. Chỉ nhận host/domain đã được cấu hình.
2. Xóa forwarded headers mà client gửi đến.
3. Tạo lại scheme, host, port và địa chỉ nguồn theo kết nối mà proxy quan sát được.
4. Chỉ chuyển traffic đến backend qua mạng riêng.
5. Không để backend có đường truy cập trực tiếp từ Internet hoặc từ mạng không tin cậy.

Ví dụ Nginx khi Nginx nhận kết nối trực tiếp từ client:

~~~nginx
upstream authorization_servers {
    least_conn;
    server auth-server-a:9000 max_fails=3 fail_timeout=10s;
    server auth-server-b:9000 max_fails=3 fail_timeout=10s;
    keepalive 32;
}

server {
    listen 443 ssl;
    server_name auth.example.test;

    # TLS certificate and private key are configured here.

    location / {
        proxy_pass http://authorization_servers;
        proxy_http_version 1.1;

        # This virtual host is restricted to the canonical public host.
        proxy_set_header Host auth.example.test;

        # Discard values supplied by the external client.
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Host auth.example.test;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;

        # This example assumes Nginx sees the client connection directly.
        proxy_set_header X-Forwarded-For $remote_addr;

        proxy_set_header Connection "";
    }
}
~~~

Ví dụ này giả định Nginx là proxy biên trực tiếp. Nếu có CDN hoặc load balancer đứng trước Nginx, $remote_addr có thể là địa chỉ của hop phía trước. Chỉ cấu hình real IP khi đã giới hạn chính xác CIDR của upstream tin cậy và xác minh header do upstream đó tạo. Không dùng X-Forwarded-For do Internet gửi đến làm IP client đáng tin.

Không gửi đồng thời Forwarded và X-Forwarded-* với các giá trị mâu thuẫn. Chọn một quy ước và áp dụng nhất quán. Với nhiều proxy, xác định rõ hop nào xóa header, hop nào ghi lại, và node ứng dụng nhận request từ dải mạng nào.

### Giới hạn đường truy cập backend

Firewall, security group hoặc network policy cần bảo đảm:

- Chỉ proxy/load balancer được phép gọi cổng HTTP của Authorization Server.
- PostgreSQL chỉ nhận kết nối từ các service subnet cần thiết.
- Redis chỉ nhận kết nối từ các instance ứng dụng và thành phần quản trị được phép.
- Cổng actuator/management không được public.
- Không có ingress rule phụ cho phép truy cập backend trực tiếp để debug trong production.

Nếu backend bị gọi trực tiếp, attacker có thể tự gửi X-Forwarded-Proto: https và X-Forwarded-Host: auth.example.test. Việc ứng dụng bật xử lý forwarded headers không xác thực được nguồn gửi header; mạng phải bảo vệ ranh giới đó.

## 4. Cấu hình Spring xử lý forwarded headers

Với Spring Boot Servlet application, có thể chọn cơ chế framework để Spring diễn giải forwarded headers:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Cơ chế framework dùng khả năng của Spring Framework, thường thông qua ForwardedHeaderFilter, để các thành phần phía sau nhìn thấy scheme, host, port và request URI theo góc nhìn bên ngoài.

Các lựa chọn thường gặp của Spring Boot:

| Giá trị | Hành vi |
|---|---|
| none | Không bật xử lý forwarded headers tự động |
| framework | Dùng cơ chế xử lý của Spring Framework |
| native | Dùng cơ chế của web server/container, nếu runtime hỗ trợ |

Chọn một cơ chế phù hợp với runtime. Không vừa bật xử lý native ở container vừa đăng ký thêm một ForwardedHeaderFilter làm cùng công việc nếu điều đó khiến header bị diễn giải hai lần. Nếu Boot đã đăng ký filter theo cấu hình framework, không tạo filter trùng.

Đối với một ứng dụng không dùng Spring Boot auto-configuration, có thể đăng ký ForwardedHeaderFilter thủ công. Filter phải chạy trước các thành phần cần đọc request scheme, host, port hoặc URI, bao gồm Spring Security filter chain. Kiểm tra thứ tự filter thực tế của ứng dụng.

### Cấu hình ứng dụng minh họa

~~~yaml
server:
  port: 9000
  forward-headers-strategy: framework
  shutdown: graceful

spring:
  datasource:
    url: jdbc:postgresql://postgres:5432/authorization
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 3000
  session:
    timeout: 30m
    redis:
      namespace: auth-server:sessions
  data:
    redis:
      host: redis
      port: 6379

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
~~~

Database username/password và Redis credential được inject từ secret manager hoặc môi trường runtime. Pool size và timeout trong ví dụ chỉ là giá trị khởi đầu; tính toán theo tổng số instance và giới hạn connection của database. Không public actuator endpoints ngoài những endpoint đã được kiểm soát.

Cookie phiên cần được cấu hình cho HTTPS và domain công khai. Ví dụ thuộc tính cần xem xét:

~~~yaml
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

SameSite phải phù hợp với cách client thực hiện redirect và response mode. Lax thường phù hợp với top-level navigation GET, nhưng luồng dùng cross-site POST hoặc form_post có thể cần chính sách khác. Không đổi sang None nếu chưa bật Secure và chưa đánh giá CSRF. Kiểm thử trên browser thật với callback và consent flow của hệ thống.

## 5. Chia sẻ OAuth persistence giữa các node

Mọi node phải dùng chung nguồn dữ liệu cho client, authorization và consent. Với JDBC, các service phổ biến là:

- JdbcRegisteredClientRepository
- JdbcOAuth2AuthorizationService
- JdbcOAuth2AuthorizationConsentService

Cấu hình minh họa:

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(
        JdbcTemplate jdbcTemplate) {
    return new JdbcRegisteredClientRepository(jdbcTemplate);
}

@Bean
OAuth2AuthorizationService authorizationService(
        JdbcTemplate jdbcTemplate,
        RegisteredClientRepository registeredClients) {
    return new JdbcOAuth2AuthorizationService(
            jdbcTemplate, registeredClients);
}

@Bean
OAuth2AuthorizationConsentService authorizationConsentService(
        JdbcTemplate jdbcTemplate,
        RegisteredClientRepository registeredClients) {
    return new JdbcOAuth2AuthorizationConsentService(
            jdbcTemplate, registeredClients);
}
~~~

Hai node cần cùng trỏ đến database/schema đã được migration tương thích. Không dùng một InMemoryOAuth2AuthorizationService riêng cho từng instance trong triển khai cần HA. Nếu authorization chỉ tồn tại trong memory node A, token request đi đến node B sẽ không tìm thấy code hoặc authorization.

### Phân biệt OAuth state và HTTP session

| Dữ liệu | Nơi lưu phù hợp | Lý do |
|---|---|---|
| RegisteredClient | Database dùng chung | Mọi node phải áp dụng cùng client policy |
| Authorization code và OAuth2Authorization | Database dùng chung | Code tạo ở node A phải được đổi ở node B |
| Consent | Database dùng chung | Người dùng không phải chấp thuận lại chỉ vì request đổi node |
| HTTP session/SecurityContext | Shared session store nếu cần tiếp tục login qua node | Browser có thể gửi request kế tiếp đến node khác |
| Signing private key | KMS/HSM/key manager dùng chung hoặc key material được đồng bộ an toàn | Token do node nào ký cũng cần được xác minh |
| Cache | Cache phân tán hoặc cache local có TTL/invalidation phù hợp | Không được làm dữ liệu bảo mật cũ tiếp tục được tin ngoài chính sách |

OAuth persistence và HTTP session giải quyết hai vấn đề khác nhau. Chỉ dùng PostgreSQL cho authorization không tự động chia sẻ phiên đăng nhập. Chỉ dùng Redis cho session cũng không làm authorization code được lưu bền vững.

### Migration và transaction

- Quản lý schema bằng Flyway/Liquibase hoặc quy trình migration có version.
- Cài đặt đúng schema tương ứng với phiên bản Spring Authorization Server đang sử dụng.
- Chạy migration một lần theo deployment job có kiểm soát; không để nhiều node đồng thời chạy migration phá hủy.
- Kiểm thử từ database trống và từ schema của release trước.
- Dùng transaction và isolation phù hợp cho việc tạo/cập nhật authorization.
- Kiểm thử hai request đồng thời đổi cùng một authorization code; chỉ một request được thành công theo semantics của grant.
- Không giả định test @Transactional bao phủ request đến server chạy ở thread khác trên cổng thật.

Với bảng authorization lớn, theo dõi index, lock, query latency và connection pool. Nếu dùng read replica, không đọc trạng thái authorization vừa ghi từ replica có replication lag trong bước token exchange hoặc consent; đường đọc cần consistency phù hợp.

## 6. Chia sẻ HTTP session giữa các instance

Đăng nhập và consent là các tương tác web có trạng thái. Trình duyệt gửi cookie session đến domain Authorization Server; load balancer có thể định tuyến request đầu đến node A và request tiếp theo đến node B. Nếu mỗi node chỉ giữ session trong bộ nhớ riêng, node B không thấy SecurityContext hoặc trạng thái web cần tiếp tục.

Có ba chiến lược:

| Chiến lược | Cách hoạt động | Giới hạn |
|---|---|---|
| Session local + sticky session | LB cố gắng giữ browser ở cùng node | Node hỏng hoặc rebalance có thể làm mất session; không phải shared session HA |
| Shared session bằng Spring Session Redis | Mọi node đọc/ghi session từ Redis | Cần vận hành Redis, bảo vệ credential, serialization và failover |
| Không giữ session lâu dài | Yêu cầu xác thực lại khi đổi node/mất session | Trải nghiệm kém hơn; chỉ phù hợp khi chính sách chấp nhận |

Trong lab này dùng Spring Session Redis. Thêm dependency tương ứng với Spring Boot version của dự án, ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.session</groupId>
    <artifactId>spring-session-data-redis</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
~~~

Tên artifact và cơ chế auto-configuration phụ thuộc phiên bản Spring Boot đang dùng; xác minh dependency management của dự án. Khi Spring Session Redis được cấu hình, các node dùng cùng Redis endpoint và cùng namespace để chia sẻ session.

Ví dụ cấu hình Redis:

~~~yaml
spring:
  session:
    store-type: redis
    timeout: 30m
    redis:
      namespace: auth-server:sessions
  data:
    redis:
      host: redis.internal
      port: 6379
~~~

Trong production, bật TLS/ACL hoặc cơ chế xác thực mà Redis platform hỗ trợ; không mở Redis ra Internet. Cấu hình timeout theo session policy và bảo đảm TTL của session được cập nhật đúng. Nếu ứng dụng dùng Spring Boot auto-configuration, tránh đồng thời bật một cấu hình EnableRedisHttpSession khác nếu nó tạo ra hai nguồn cấu hình session.

### Session serialization và rolling deployment

Shared session có thể chứa object được serialize. Khi rolling deploy, node mới phải có khả năng đọc session do node cũ ghi. Vì vậy:

- Giữ tương thích class và serialVersionUID trong thời gian rollout.
- Tránh lưu object tùy biến không cần thiết hoặc class thay đổi thường xuyên vào session.
- Ưu tiên dữ liệu session nhỏ, ổn định và có thể tái tạo.
- Đánh giá serializer và format được hỗ trợ bởi phiên bản Spring Session.
- Kiểm thử node mới đọc session được tạo bởi node cũ trước khi tăng traffic.
- Có kế hoạch xử lý session cũ nếu thay đổi không tương thích, bao gồm chấp nhận người dùng đăng nhập lại nếu cần.

Redis là dependency vận hành quan trọng khi dùng shared session. Theo dõi availability, latency, connection exhaustion, memory, eviction và replication/failover. Không cấu hình eviction policy có thể xóa session đang hoạt động ngoài dự kiến.

## 7. Đồng bộ signing key và JWKS

Mọi node phải dùng cùng bộ signing key đang hoạt động. Nếu node A ký token bằng key A nhưng node B công bố JWKS không có public key A, client hoặc resource server có thể xác minh token thất bại tùy node mà metadata/JWKS request đi tới.

Không tạo key pair ngẫu nhiên mới mỗi lần ứng dụng khởi động. Dùng KMS, HSM, keystore được bảo vệ hoặc một key provider có thể cung cấp cùng key set cho tất cả node. Private key không được log hoặc đưa vào image/repository.

Mỗi key có kid duy nhất. Trong cùng giai đoạn triển khai, mọi node phải:

- Nhận cùng key set và cùng active signing key.
- Công bố JWKS tương thích.
- Ký token mới với key được chọn theo rollout/key policy.
- Giữ public key cũ đủ lâu để xác minh token còn hiệu lực.
- Không xóa key cũ trước khi hết token lifetime, cache window và overlap cần thiết.

### Quy trình rotation trong cluster

1. Tạo key mới trong KMS/HSM.
2. Cấp quyền sử dụng key mới cho tất cả node.
3. Công bố public key mới trong JWKS trên mọi node.
4. Chờ client/resource server refresh JWKS hoặc hết cache TTL phù hợp.
5. Chuyển các node sang ký bằng key mới theo một thay đổi nhất quán.
6. Kiểm tra token do từng node phát hành đều xác minh được.
7. Giữ key cũ cho đến khi token cũ hết hiệu lực và overlap kết thúc.
8. Gỡ public key cũ theo kế hoạch và lưu audit record.

Không triển khai node A dùng key mới trong khi node B vẫn công bố JWKS cũ nếu load balancer có thể phục vụ JWKS từ node B. Một lựa chọn là mọi node cùng công bố cả key cũ và mới trước khi bất kỳ node nào chuyển sang ký bằng key mới.

## 8. Cấu hình load balancer, cookie và graceful shutdown

Load balancer cần có health check riêng và chỉ đưa node vào rotation sau khi ứng dụng đã sẵn sàng. Health endpoint phải kiểm tra các dependency thiết yếu theo chính sách, nhưng tránh tạo vòng lặp restart toàn cluster khi một dependency dùng chung đang gặp sự cố.

Các nguyên tắc:

- Readiness xác định node có thể nhận traffic hay không.
- Liveness chỉ xác định process cần restart hay không.
- Khi deploy, drain node cũ trước khi dừng process.
- Cho request đang xử lý hoàn tất trong thời gian graceful shutdown.
- Không xóa session hoặc authorization dùng chung khi node dừng.
- Đặt timeout LB lớn hơn hoặc tương thích với request duration và shutdown grace period.
- Theo dõi tỷ lệ request phân phối đến từng node và node bị loại khỏi pool.

Sticky session có thể giúp giảm chuyển node nếu session vẫn local, nhưng không thay thế shared session trong thiết kế HA. Nếu chọn sticky session vì lý do tương thích tạm thời, ghi rõ hậu quả khi node hỏng và cách người dùng tiếp tục phiên.

### Cấu hình cookie

Cookie session phải được trả về từ domain công khai và được browser gửi theo đúng luồng. Kiểm tra:

- Secure được bật khi truy cập qua HTTPS.
- HttpOnly được bật để JavaScript không đọc cookie session.
- Domain và Path giới hạn phù hợp với Authorization Server.
- SameSite tương thích với redirect và response mode.
- Cookie không bị proxy ghi đè hoặc loại bỏ.
- Mọi node dùng cùng session cookie name và cấu hình signing/encryption nếu có.

Không dùng cookie domain rộng như .example.com nếu không cần chia sẻ cookie giữa subdomain. Việc chia sẻ cookie rộng làm tăng phạm vi ảnh hưởng nếu một subdomain bị xâm nhập.

## 9. Bảo đảm các node có cấu hình tương đương

Một cluster không chỉ cần cùng issuer và database. Mọi node phải chạy cấu hình tương thích:

| Hạng mục | Yêu cầu đồng nhất |
|---|---|
| Application release | Cùng phiên bản hoặc phiên bản tương thích trong rolling deployment |
| Issuer và endpoint settings | Cùng giá trị công khai |
| RegisteredClient policy | Đọc từ cùng nguồn dữ liệu hoặc cùng version |
| Security filter chains | Matcher, CSRF, login, consent và endpoint policy nhất quán |
| Signing key set | Cùng public key set và active key policy |
| Token settings/customizers | Claim, lifetime, audience và token format nhất quán |
| Database schema | Phiên bản tương thích với mọi node đang chạy |
| Session cookie | Name, Secure, HttpOnly, SameSite, Path và namespace nhất quán |
| Time | Đồng bộ NTP; sai lệch clock trong giới hạn cho phép |
| Trust store/TLS | Cùng CA và trust policy cần thiết |

Các giá trị bí mật không cần giống nhau nếu chúng là credential riêng của node, nhưng quyền truy cập và vai trò của chúng phải tương đương. Với signing key, các node phải dùng cùng key set hoặc cùng dịch vụ ký để token có thể được xác minh trên toàn cluster.

Clock skew có thể làm token bị xem là chưa có hiệu lực hoặc đã hết hạn. Đồng bộ thời gian cho node, database và hệ thống phụ thuộc. Không tăng clock skew allowance quá mức để che giấu NTP drift.

## 10. Triển khai và rollout nhiều instance

Một rollout an toàn cần tương thích ở cả database, session serialization, issuer và key set.

Quy trình tham khảo:

1. Build image một lần và dùng cùng artifact cho mọi node.
2. Xác minh config, secret reference, KMS permissions và network policy.
3. Chạy database migration tương thích ngược trước khi rollout nếu cần.
4. Đảm bảo key set mới đã được phân phối và JWKS có overlap.
5. Khởi động node mới, đợi readiness và gọi metadata/JWKS qua node đó.
6. Chạy smoke test login và token bằng client test.
7. Đưa node mới vào LB, sau đó drain một node cũ.
8. Kiểm tra session được đọc qua node mới và authorization được đọc/đổi từ node khác.
9. Theo dõi token error, login failure, DB pool, Redis latency và KMS error.
10. Hoàn tất rollout hoặc rollback theo tiêu chí đã định.

### Expand-and-contract cho schema

Nếu thay đổi database schema:

- Thêm cột/bảng mới theo cách code cũ vẫn chạy được.
- Deploy code có thể đọc/ghi schema tương thích trong giai đoạn chuyển tiếp.
- Backfill và xác minh dữ liệu.
- Chuyển toàn bộ traffic sang code mới.
- Chỉ loại bỏ schema cũ ở release sau khi không còn node cũ.

Không chạy migration phá hủy trong lúc node cũ vẫn cần schema đó. Migration phải có backup, thời gian lock dự kiến và kế hoạch rollback.

### Graceful shutdown

Bật graceful shutdown trong Spring Boot và cấu hình LB drain. Không để node dừng ngay khi đang xử lý token request hoặc consent submission. Nếu request đang xử lý không thể hoàn tất trước deadline, client có thể retry; nhưng authorization code/token semantics vẫn phải chống cấp token hai lần.

## 11. Kiểm thử tích hợp đa instance

Không đủ nếu chỉ gọi từng node độc lập và thấy HTTP 200. Cần kiểm tra state đi qua node khác.

### Kiểm thử metadata trên cả hai node

Gọi trực tiếp từng node từ mạng test nội bộ và gọi qua domain LB:

- issuer phải giống nhau.
- Authorization/token/JWKS endpoint phải dùng domain công khai.
- JWKS phải chứa cùng key set trong giai đoạn không rotation.
- Header Location không được lộ host nội bộ.
- Không node nào trả HTTP URL trong redirect khi request gốc là HTTPS.

### Kiểm thử login bắt đầu ở A, tiếp tục ở B

1. Gửi browser đến authorization endpoint và ép request đầu vào node A.
2. Node A tạo session và chuyển người dùng đến login/consent.
3. Gửi request tiếp theo đến node B với cùng cookie session.
4. Node B phải nhận được SecurityContext/session cần thiết.
5. Hoàn tất consent và redirect về đúng URI đã đăng ký.

Nếu test dùng sticky session, chủ động tắt affinity trong môi trường test hoặc gọi thẳng node B để xác minh shared session. Nếu kiến trúc chấp nhận mất session khi node hỏng, ghi rõ người dùng phải đăng nhập lại và kiểm tra hành vi đó an toàn.

### Kiểm thử code phát ở A, đổi ở B

1. Gửi authorization request qua node A.
2. Hoàn tất đăng nhập/consent và nhận authorization code.
3. Gửi token request qua node B.
4. Xác minh token được cấp và claim/issuer hợp lệ.
5. Gửi lại cùng code qua node A hoặc B.
6. Xác minh replay bị từ chối và không có token mới được cấp.

Đây là phép thử quan trọng chứng minh OAuth2AuthorizationService dùng chung. Chạy thêm hai request đổi cùng code đồng thời đến hai node để xác minh chỉ một request thắng theo semantics authorization code. Kiểm tra database transaction/locking của phiên bản và cấu hình đang dùng; không chỉ dựa vào kết quả test đơn luồng.

### Kiểm thử token và JWKS giữa các node

- Lấy token từ node A, xác minh bằng JWKS lấy qua load balancer.
- Lấy token từ node B, xác minh bằng cùng JWKS.
- Ép JWKS request đến từng node và xác minh cả hai public key set tương thích.
- Decode claim iss, aud, exp, scope và kid theo profile; xác minh chữ ký bằng thư viện tin cậy.
- Trong key rotation, kiểm tra token cũ và mới đều được xác minh trong overlap.

Không chỉ decode JWT rồi xem payload. Phải xác minh chữ ký, issuer, audience và thời hạn.

### Kiểm thử failover

| Thử nghiệm | Cách thực hiện | Kết quả mong đợi |
|---|---|---|
| Node A dừng | Drain và terminate A | LB chuyển traffic sang B; session vẫn hoạt động nếu Redis dùng chung |
| Node B dừng | Drain và terminate B | A tiếp tục phục vụ |
| Redis failover | Chuyển Redis primary hoặc mô phỏng gián đoạn | Session tiếp tục hoặc lỗi theo chính sách; không tạo trạng thái xác thực giả |
| PostgreSQL failover | Mô phỏng failover trong staging | Node phục hồi kết nối; request lỗi được xử lý an toàn |
| KMS tạm lỗi | Từ chối key operation trong test | Không phát token với key không xác định; alert được phát |
| Proxy header spoofing | Gửi Host/Forwarded/X-Forwarded giả | URL công khai và issuer vẫn đúng; backend không tin nguồn trực tiếp |
| Rolling deploy | Thay node từng bước | Session, schema và JWKS tương thích trong giai đoạn chuyển tiếp |

Không thực hiện failover hoặc kill node trên production nếu chưa có kế hoạch diễn tập và phạm vi được phê duyệt. Lab này dùng local/staging có dữ liệu giả.

## 12. Kiểm thử forwarded headers và host spoofing

Gửi request đến domain công khai cùng các header giả:

~~~bash
curl -i \
  -H 'Forwarded: host=attacker.example;proto=http' \
  -H 'X-Forwarded-Host: attacker.example' \
  -H 'X-Forwarded-Proto: http' \
  https://auth.example.test/.well-known/openid-configuration
~~~

Proxy biên phải xóa hoặc ghi đè các giá trị do client gửi. Metadata và redirect vẫn phải dùng issuer/domain hợp lệ. Nếu attacker.example hoặc http:// xuất hiện trong URL do server tạo, kiểm tra:

- Host allowlist ở ingress.
- Quy tắc xóa/ghi lại Forwarded và X-Forwarded-*.
- Backend network access.
- forward-headers-strategy.
- Filter order và việc đăng ký filter trùng.
- Cấu hình issuer tường minh.

Kiểm thử thêm đường truy cập trực tiếp đến backend từ một mạng không được phép. Request phải bị chặn ở firewall/security group/network policy. Đây là kiểm tra mạng; MockMvc không thể chứng minh điều đó.

## 13. Quan sát và cảnh báo trong cluster

Theo dõi theo node và toàn cluster:

- Request rate, latency, error rate theo endpoint.
- Login/consent success và failure.
- invalid_client, invalid_grant, token issuance và refresh failure.
- HikariCP active/idle/pending connections, timeout và query latency.
- Redis latency, connection, memory, eviction và failover.
- KMS request latency, error và permission denial.
- JVM memory, CPU, thread pool, GC và restart count.
- Load balancer healthy/unhealthy target, connection draining và phân phối traffic.
- Issuer/JWKS key version được node công bố.
- Clock drift và health probe failures.

Log cần có correlation ID, node ID, endpoint category và outcome. Không log access token, refresh token, authorization code, client secret, cookie, private key hoặc device/user code. Không đưa username hoặc token vào metric label vì cardinality và rủi ro riêng tư.

Một cảnh báo nên chỉ ra phạm vi: một node hay cả cluster, một dependency hay tất cả, login hay token endpoint. Điều đó giúp on-call khoanh vùng trước khi drain hoặc rollback.

## 14. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Bằng chứng cần xem | Hướng xử lý |
|---|---|---|---|
| Issuer khác nhau giữa các request | Issuer suy từ request hoặc node có config khác | Metadata từ từng node, config version | Cấu hình issuer tường minh và đồng bộ rollout |
| Redirect chứa HTTP hoặc hostname nội bộ | Proxy header sai hoặc không được xử lý | Location, forwarded headers, proxy log | Sửa proxy normalization và network boundary |
| Login bắt đầu ở A nhưng B yêu cầu đăng nhập lại | Session local hoặc Redis namespace/cookie khác | Cookie, session store, node logs | Bật shared session hoặc chấp nhận reauthentication có chủ đích |
| Token endpoint ở B trả invalid_grant sau code từ A | OAuth authorization lưu local hoặc DB khác nhau | Datasource, JDBC service, DB row | Dùng shared OAuth2AuthorizationService và cùng schema |
| JWT ký ở A không verify khi JWKS từ B | Key set không đồng nhất hoặc kid khác | JWT header, JWKS từ từng node, key inventory | Đồng bộ key set và triển khai rotation có overlap |
| Một số node trả metadata cũ | Config drift hoặc rollout dở dang | Release/config version theo node | Drain node lệch, hoàn tất rollout |
| Consent xuất hiện lặp lại | Consent persistence khác nhau hoặc không được chia sẻ | Consent service và database | Đồng bộ JDBC store, kiểm tra migration |
| Session mất sau deploy | Serialization không tương thích hoặc TTL/cookie đổi | Redis session metadata, release diff | Giữ tương thích serialization hoặc xử lý đăng nhập lại có kiểm soát |
| Token request timeout | DB pool, lock, Redis/KMS hoặc thread pool | Metrics, traces, DB/KMS logs | Khôi phục dependency, giảm tải và điều chỉnh sau khi xác định nguyên nhân |
| Code có thể đổi hai lần ở hai node | Race condition/transaction semantics sai | Concurrent test, DB isolation, authorization update | Sửa atomic consume/locking và bổ sung regression test |

### Quy trình triage

1. Xác định lỗi xảy ra ở login, consent, authorization endpoint, token endpoint hay JWKS.
2. Ghi correlation ID, timestamp, node ID và release/config version.
3. Gọi metadata/JWKS qua LB và từng node từ mạng test.
4. So sánh issuer, endpoint, active kid và key set.
5. Kiểm tra session cookie và Redis nếu lỗi xảy ra trong login/consent.
6. Kiểm tra PostgreSQL và OAuth2AuthorizationService nếu lỗi liên quan code/token/consent.
7. Kiểm tra forwarded headers và host allowlist nếu URL/redirect sai.
8. Drain node có config/key/schema lệch nếu có bằng chứng.
9. Chạy smoke test cross-node trước khi đưa node trở lại pool.
10. Ghi nguyên nhân gốc, tác động và regression test.

Không xóa session hoặc authorization hàng loạt để khắc phục lỗi node. Không thay issuer hoặc signing key chỉ để làm metadata của một node khớp tạm thời; thay đổi đó có thể làm client không xác minh được token đang còn hiệu lực.

## 15. Thực hành capstone

Dùng môi trường local hoặc staging cô lập, domain test và dữ liệu giả.

### Lab A — Dựng hai node

1. Chạy hai instance Spring Authorization Server từ cùng image.
2. Cấp cùng issuer https://auth.example.test.
3. Cấu hình cùng PostgreSQL và migration.
4. Cấu hình cùng key set qua key provider.
5. Kiểm tra từng node trả metadata cùng issuer và endpoint.

**Kết quả mong đợi:** hai node có cùng danh tính Authorization Server và có thể phát token dùng chung trust.

### Lab B — Đưa hai node sau proxy

1. Cấu hình Nginx/load balancer với domain test và TLS.
2. Xóa/ghi lại forwarded headers ở proxy biên.
3. Chặn truy cập trực tiếp đến backend.
4. Bật forward-headers-strategy framework hoặc cơ chế native đã chọn.
5. Gọi discovery qua domain và xác minh không lộ địa chỉ nội bộ.
6. Gửi header spoofing và xác minh response không bị ảnh hưởng.

**Kết quả mong đợi:** URL công khai luôn là HTTPS và host allowlist.

### Lab C — Chia sẻ session

1. Thêm Spring Session Redis dependency tương thích.
2. Cấu hình cùng Redis endpoint và namespace trên cả hai node.
3. Bắt đầu login ở A.
4. Gửi request tiếp theo với cùng browser cookie đến B.
5. Hoàn tất login/consent và xác minh session.
6. Drain A trong lúc session vẫn còn hiệu lực và tiếp tục request qua B.

**Kết quả mong đợi:** browser tiếp tục phiên qua node khác theo chính sách.

### Lab D — Chia sẻ OAuth authorization

1. Gửi authorization request đến A.
2. Nhận authorization code sau login/consent.
3. Gửi token request đến B.
4. Xác minh token và claim.
5. Thử replay code qua A.
6. Chạy hai token request đồng thời đến A và B với cùng code.

**Kết quả mong đợi:** code được lưu dùng chung và chỉ tiêu thụ một lần.

### Lab E — Đồng bộ key và failover

1. Lấy token từ A và B.
2. Xác minh token bằng JWKS qua LB và từng node.
3. Drain/terminate A rồi kiểm tra B tiếp tục phục vụ.
4. Thực hiện key rotation với overlap trong môi trường test.
5. Kiểm tra token cũ và mới trong thời gian overlap.

**Kết quả mong đợi:** failover không làm thay đổi issuer hoặc mất khả năng xác minh token.

### Lab F — Ghi runbook

Ghi lại topology, issuer, proxy rules, database, Redis, key provider, health check, rollout, rollback, cảnh báo và quy trình triage. Mỗi thao tác cần có owner, lệnh hoặc đường dẫn cấu hình, điều kiện trước và bước xác minh sau thao tác.

**Kết quả mong đợi:** một kỹ sư on-call có thể xác định node lỗi, drain node, kiểm tra session/OAuth state và khôi phục dịch vụ mà không cần đoán.

## 16. Checklist sẵn sàng production

- [ ] Tất cả node dùng cùng issuer công khai và endpoint settings.
- [ ] Issuer được cấu hình tường minh, không suy từ Host tùy ý.
- [ ] Proxy biên xóa/ghi lại forwarded headers và áp dụng host allowlist.
- [ ] Backend chỉ nhận traffic từ proxy tin cậy.
- [ ] Chỉ chọn một cơ chế xử lý forwarded headers.
- [ ] Tất cả node dùng chung RegisteredClient, OAuth2Authorization và consent store.
- [ ] HTTP session được chia sẻ nếu cần duy trì login/consent qua nhiều node.
- [ ] Session cookie có Secure/HttpOnly và SameSite phù hợp.
- [ ] Redis có ACL, network isolation, TTL và kế hoạch failover.
- [ ] Mọi node dùng cùng signing key set và JWKS tương thích.
- [ ] Key rotation có overlap; không xóa key cũ khi token còn hiệu lực.
- [ ] Database migration tương thích với rolling deployment.
- [ ] Load balancer có readiness, health check và graceful drain.
- [ ] Clock được đồng bộ.
- [ ] Cross-node login, consent và authorization code exchange đã được kiểm thử.
- [ ] Concurrent authorization code redemption chỉ thành công một lần.
- [ ] Token từ mọi node được xác minh bằng JWKS công khai.
- [ ] Forwarded header spoofing và backend direct access đã được kiểm thử.
- [ ] Metrics/logs/audit có correlation ID nhưng không chứa credential.
- [ ] Runbook failover, key rotation, rollback và incident triage đã được diễn tập.

Triển khai đa instance thành công khi các node là những bản sao tương thích của cùng một Authorization Server: cùng issuer, cùng chính sách client, cùng dữ liệu authorization, cùng key trust và cùng cách diễn giải request bên ngoài. Reverse proxy tạo ranh giới tin cậy, database giữ OAuth state, shared session giữ trạng thái đăng nhập và key manager duy trì chữ ký. Khi kiểm thử chéo node và failover đạt, hệ thống có thể mở rộng hoặc thay node mà không làm client nhìn thấy một Authorization Server khác.

## Tài liệu tham khảo

- Spring Authorization Server — Configuration Model: https://docs.spring.io/spring-authorization-server/reference/configuration-model.html
- Spring Authorization Server — Core Model: https://docs.spring.io/spring-authorization-server/reference/core-model-components.html
- Spring Boot — Forwarded Headers: https://docs.spring.io/spring-boot/reference/howto/webserver.html
- Spring Framework — ForwardedHeaderFilter: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
- Spring Session — Redis: https://docs.spring.io/spring-session/reference/guides/boot-redis.html
- RFC 7239 — Forwarded HTTP Extension: https://datatracker.ietf.org/doc/html/rfc7239
- RFC 8414 — OAuth 2.0 Authorization Server Metadata: https://datatracker.ietf.org/doc/html/rfc8414
- RFC 7517 — JSON Web Key (JWK): https://datatracker.ietf.org/doc/html/rfc7517

