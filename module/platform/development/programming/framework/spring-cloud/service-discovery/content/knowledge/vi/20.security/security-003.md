# Bảo vệ Eureka bằng Spring Security và HTTP Basic

Eureka Server lưu danh sách service instance và cung cấp HTTP API để client đăng ký, gửi heartbeat, cập nhật trạng thái và tra cứu registry. Nếu các endpoint này mở cho mọi kết nối, một hệ thống hoặc người dùng không được phép có thể đọc topology nội bộ, đăng ký instance giả, thay đổi trạng thái hoặc làm sai lệch registry.

Spring Security có thể bảo vệ Eureka Server bằng HTTP Basic. Eureka Client hỗ trợ tự gửi thông tin Basic Auth khi URL server chứa username và password. Cách triển khai cần xử lý đúng ba phần: xác thực request, CSRF cho các API đăng ký của Eureka và mã hóa đường truyền bằng HTTPS.

## 1. Mô hình bảo vệ Eureka

Một triển khai Eureka có hai vai trò chính:

- **Eureka Server:** nhận đăng ký, heartbeat, cập nhật trạng thái và trả danh sách instance.
- **Eureka Client:** gọi API server để đăng ký instance và tải registry.

Khi bật Spring Security trên Eureka Server, request phải được xác thực trước khi truy cập dashboard hoặc API. Với HTTP Basic, client gửi header Authorization chứa cặp username/password đã mã hóa Base64. Server kiểm tra credentials thông qua UserDetailsService hoặc AuthenticationProvider.

Luồng đăng ký:

    Eureka Client
         |
         | HTTPS + Authorization: Basic ...
         v
    Spring Security Filter Chain
         |
         | authenticate + authorize
         v
    Eureka REST API (/eureka/**)
         |
         v
    Eureka Registry

HTTP Basic chỉ xác thực danh tính. Nó không tự mã hóa dữ liệu trên mạng, không thay thế TLS, không tự phân quyền chi tiết giữa các service và không bảo vệ mọi kênh nội bộ của một cụm Eureka.

## 2. Thêm dependency cho Eureka Server

Ứng dụng server cần Eureka Server starter và Spring Security starter.

**Maven**

    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-netflix-eureka-server</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
    </dependencies>

**Gradle**

    dependencies {
        implementation 'org.springframework.cloud:spring-cloud-starter-netflix-eureka-server'
        implementation 'org.springframework.boot:spring-boot-starter-security'
    }

Dùng Spring Cloud BOM tương thích với phiên bản Spring Boot để quản lý version. Không tự chọn một version Eureka Server hoặc Spring Security riêng lẻ nếu dự án đã quản lý chúng bằng dependency management.

Ứng dụng Eureka Server có thể bắt đầu như sau:

    @SpringBootApplication
    @EnableEurekaServer
    public class EurekaServerApplication {

        public static void main(String[] args) {
            SpringApplication.run(EurekaServerApplication.class, args);
        }
    }

Chỉ cần thêm Spring Security vào classpath, Spring Boot đã tự bảo vệ ứng dụng web theo cấu hình mặc định. Tuy nhiên, nên khai báo SecurityFilterChain rõ ràng để kiểm soát endpoint được phép truy cập và cách xử lý CSRF của Eureka.

## 3. Cấu hình SecurityFilterChain cho Eureka

Eureka Client gọi các REST API dưới /eureka/** bằng những HTTP method như POST, PUT và DELETE. Spring Security bật CSRF protection cho các method thay đổi trạng thái. Client Eureka thông thường không lấy hoặc gửi CSRF token, nên nếu giữ mặc định, các request đăng ký và heartbeat có thể bị từ chối với HTTP 403.

Spring Cloud Netflix khuyến nghị bỏ kiểm tra CSRF riêng cho /eureka/**, đồng thời vẫn yêu cầu authentication. Không tắt CSRF cho toàn bộ ứng dụng chỉ để Eureka Client hoạt động.

Ví dụ dùng Spring Security 6 trở lên:

    import org.springframework.context.annotation.Bean;
    import org.springframework.context.annotation.Configuration;
    import org.springframework.security.config.Customizer;
    import org.springframework.security.config.annotation.web.builders.HttpSecurity;
    import org.springframework.security.config.http.SessionCreationPolicy;
    import org.springframework.security.web.SecurityFilterChain;

    @Configuration
    public class EurekaSecurityConfiguration {

        @Bean
        SecurityFilterChain eurekaSecurityFilterChain(HttpSecurity http)
                throws Exception {

            http
                .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers(
                        "/actuator/health",
                        "/actuator/health/**"
                    ).permitAll()
                    .anyRequest().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
                )
                .csrf(csrf -> csrf
                    .ignoringRequestMatchers("/eureka/**")
                );

            return http.build();
        }
    }

Giải thích:

- /actuator/health và các health group được cho phép nếu nền tảng cần kiểm tra tình trạng server mà không gửi credentials. Nếu không cần truy cập health công khai, hãy yêu cầu authentication cho các endpoint này.
- anyRequest().authenticated() yêu cầu đăng nhập cho dashboard, API và các endpoint còn lại.
- httpBasic(...) bật cơ chế HTTP Basic.
- STATELESS tránh phụ thuộc vào HTTP session cho luồng xác thực máy-máy.
- ignoringRequestMatchers("/eureka/**") chỉ bỏ CSRF cho API Eureka. Request vẫn phải qua authentication và authorization.

Nếu ứng dụng đổi context path hoặc prefix của Eureka API, matcher CSRF phải khớp đường dẫn thực tế. Không mở rộng matcher sang /** nếu chỉ cần cho Eureka Client đăng ký.

## 4. Cấu hình tài khoản cho môi trường thử nghiệm

Với một Eureka Server nhỏ, Spring Boot cho phép cấu hình một user in-memory bằng các thuộc tính:

    spring:
      security:
        user:
          name: ${EUREKA_USERNAME}
          password: ${EUREKA_PASSWORD}
          roles:
            - EUREKA_CLIENT

Trong ví dụ này, username và password được lấy từ environment variable thay vì ghi trực tiếp vào repository. SecurityFilterChain ở phần trước chỉ yêu cầu authenticated; nếu muốn kiểm tra role, có thể đổi quy tắc thành:

    .requestMatchers("/eureka/**").hasRole("EUREKA_CLIENT")
    .anyRequest().authenticated()

Khi dùng hasRole("EUREKA_CLIENT"), user phải có authority ROLE_EUREKA_CLIENT. Thuộc tính roles: EUREKA_CLIENT của Spring Boot tự thêm tiền tố ROLE_.

Cấu hình một user là cách bắt đầu thuận tiện cho demo hoặc một môi trường nhỏ. Spring Boot mặc định tạo một user in-memory và sinh password ngẫu nhiên khi không cấu hình credentials; password đó chỉ dành cho phát triển và được ghi trong log khởi động. Không dùng password ngẫu nhiên này như một cơ chế quản lý danh tính production.

## 5. Phân quyền cho nhiều client và người vận hành

Khi có nhiều service, dùng chung một tài khoản cho tất cả client khiến việc thu hồi và truy vết khó hơn. Có thể cấp user riêng cho từng service hoặc nhóm service thông qua UserDetailsService, LDAP, database hoặc hệ thống danh tính nội bộ.

Một ví dụ minh họa với hai user in-memory:

    @Bean
    UserDetailsService eurekaUsers(PasswordEncoder encoder) {
        UserDetails inventoryClient = User.withUsername("inventory-client")
                .password(encoder.encode(
                        System.getenv("INVENTORY_EUREKA_PASSWORD")
                ))
                .roles("EUREKA_CLIENT")
                .build();

        UserDetails operator = User.withUsername("eureka-operator")
                .password(encoder.encode(
                        System.getenv("EUREKA_OPERATOR_PASSWORD")
                ))
                .roles("EUREKA_CLIENT", "EUREKA_OPERATOR")
                .build();

        return new InMemoryUserDetailsManager(
                inventoryClient,
                operator
        );
    }

Khai báo PasswordEncoder:

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

Cần thêm các import tương ứng:

    import org.springframework.security.core.userdetails.UserDetails;
    import org.springframework.security.core.userdetails.UserDetailsService;
    import org.springframework.security.core.userdetails.User;
    import org.springframework.security.provisioning.InMemoryUserDetailsManager;
    import org.springframework.security.crypto.password.PasswordEncoder;
    import org.springframework.security.crypto.factory.PasswordEncoderFactories;

Đây là ví dụ để minh họa phân biệt danh tính. InMemoryUserDetailsManager lưu user trong bộ nhớ tiến trình và phù hợp cho demo hoặc môi trường nhỏ; khi server restart, danh sách user được tạo lại từ cấu hình. Production nên dùng kho danh tính được quản lý, lưu password dạng hash bằng PasswordEncoder và có quy trình cấp, thu hồi, luân chuyển credentials.

Nếu cần giới hạn dashboard cho operator trong khi cho client chỉ gọi API, hãy tách rule theo path và role. Kiểm tra các static resource và endpoint mà giao diện Eureka cần trước khi áp dụng rule chặt hơn.

Ví dụ rule tách API và dashboard khi đã có hai role ở trên:

    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/actuator/health", "/actuator/health/**").permitAll()
        .requestMatchers("/eureka/**").hasRole("EUREKA_CLIENT")
        .anyRequest().hasRole("EUREKA_OPERATOR")
    )

Trong cấu hình này, inventory-client chỉ gọi được Eureka API; eureka-operator có cả EUREKA_CLIENT và EUREKA_OPERATOR nên có thể dùng API lẫn dashboard. Khi tự khai báo UserDetailsService, Spring Boot không còn dùng user mặc định từ spring.security.user.* làm nguồn danh tính; các user phải được tạo trong UserDetailsService hoặc kho xác thực mà ứng dụng tích hợp.

## 6. Cấu hình Eureka Client gửi HTTP Basic

Spring Cloud Netflix tự thêm HTTP Basic authentication vào Eureka Client nếu URL trong eureka.client.serviceUrl.defaultZone chứa credentials theo dạng user-info.

Ví dụ:

    eureka:
      client:
        serviceUrl:
          defaultZone: https://${EUREKA_USERNAME}:${EUREKA_PASSWORD}@eureka.internal:8761/eureka/

Client sẽ gửi thông tin Basic Auth khi gọi Eureka Server. Không cần tự viết filter hoặc interceptor cho trường hợp HTTP Basic đơn giản này.

defaultZone phải giữ nguyên chữ Z viết hoa vì serviceUrl là một Map và khóa Map này phân biệt chữ hoa, chữ thường. Dạng default-zone không phải khóa fallback chuẩn của Eureka.

Khi password có ký tự đặc biệt trong URL, cần percent-encode phần user-info theo quy tắc URI. Các ký tự như @, :, /, ? hoặc # có thể làm URL bị phân tích sai nếu không được encode. Không encode toàn bộ URL; chỉ encode username/password theo đúng thành phần URI.

Không đặt credentials trực tiếp trong application.yml đã commit. Dùng secret manager, Kubernetes Secret, Docker secret hoặc biến môi trường được quản lý bởi nền tảng. Hạn chế quyền đọc environment và không log URL có chứa user-info.

## 7. Cấu hình Eureka Server và Client hoàn chỉnh

Ví dụ cấu hình standalone Eureka Server:

    server:
      port: 8761

    spring:
      application:
        name: eureka-server
      security:
        user:
          name: ${EUREKA_USERNAME}
          password: ${EUREKA_PASSWORD}
          roles:
            - EUREKA_CLIENT

    eureka:
      client:
        register-with-eureka: false
        fetch-registry: false

Kết hợp cấu hình này với @EnableEurekaServer và SecurityFilterChain ở phần trước. register-with-eureka: false và fetch-registry: false là cấu hình thường dùng cho server chạy độc lập; với cụm peer-aware, cấu hình client-side và peer URL cần được thiết lập riêng.

Ví dụ cấu hình cho một service client:

    spring:
      application:
        name: inventory-service

    eureka:
      client:
        register-with-eureka: true
        fetch-registry: true
        serviceUrl:
          defaultZone: https://${EUREKA_USERNAME}:${EUREKA_PASSWORD}@eureka.internal:8761/eureka/

Khi khởi động, inventory-service dùng credentials để đăng ký và tải registry. Nếu credentials sai, server trả HTTP 401 và client không thể hoàn tất các thao tác đăng ký hoặc fetch.

## 8. HTTP Basic phải đi cùng HTTPS

HTTP Basic gửi cặp username/password trong header Authorization dưới dạng Base64. Base64 chỉ là mã hóa biểu diễn, không phải mã hóa bảo mật. Người có thể nghe lén traffic không mã hóa có thể khôi phục credentials.

Vì vậy, không dùng HTTP Basic qua HTTP thuần trên mạng không tin cậy. Bật HTTPS trên Eureka Server hoặc kết thúc TLS tại một reverse proxy/gateway đáng tin cậy, đồng thời bảo vệ đường truyền nội bộ từ proxy tới server.

Ví dụ dùng PKCS12 keystore với Spring Boot:

    server:
      port: 8761
      ssl:
        key-store: file:/etc/eureka/tls/eureka-server.p12
        key-store-type: PKCS12
        key-store-password: ${EUREKA_KEYSTORE_PASSWORD}
        key-alias: eureka-server

Client phải tin cậy certificate của server. Nếu certificate được cấp bởi CA nội bộ, cấu hình trust store phù hợp cho JVM hoặc Eureka Client. Không tắt certificate validation để khắc phục nhanh lỗi TLS.

Nếu Eureka Server yêu cầu client certificate, đó là mutual TLS. Spring Cloud Netflix có các thuộc tính eureka.client.tls.* để cấu hình key store và trust store ở client. mTLS bổ sung xác thực ở tầng TLS; nó khác với HTTP Basic và có thể được dùng kết hợp với Basic Auth.

## 9. Bảo vệ dashboard và Actuator

Eureka Server cung cấp dashboard và HTTP API dưới /eureka/*. Khi dùng rule anyRequest().authenticated(), cả dashboard cũng yêu cầu Basic Auth.

Actuator là bề mặt quản trị riêng. Chỉ expose các endpoint thực sự cần:

    management:
      endpoints:
        web:
          exposure:
            include: health,info
      endpoint:
        health:
          show-details: never

Nếu health endpoint được cho phép không cần authentication trong SecurityFilterChain, hãy giữ thông tin health ở mức không nhạy cảm. Không expose env, configprops, beans, mappings hoặc các endpoint quản trị rộng ra mạng công khai chỉ để tiện kiểm tra.

Endpoint dashboard và registry có thể tiết lộ tên service, hostname, IP, port, zone và metadata nội bộ. Xem dữ liệu registry là thông tin vận hành nhạy cảm và giới hạn quyền truy cập phù hợp.

## 10. Kiểm tra authentication bằng curl

Có thể xác minh server yêu cầu credentials bằng cách gọi registry API không có thông tin đăng nhập:

    curl -i https://eureka.internal:8761/eureka/apps

Nếu server được bảo vệ đúng, request không có credentials thường nhận HTTP 401 Unauthorized và header WWW-Authenticate: Basic.

Gọi lại với credentials:

    curl -i \
      --user "$EUREKA_USERNAME:$EUREKA_PASSWORD" \
      -H "Accept: application/json" \
      https://eureka.internal:8761/eureka/apps

Nếu credentials đúng và endpoint hoạt động, server trả HTTP 200 cùng nội dung registry. Một registry rỗng vẫn có thể trả 200; điều này không có nghĩa đã có instance đăng ký.

Thử password sai:

    curl -i \
      --user "$EUREKA_USERNAME:wrong-password" \
      -H "Accept: application/json" \
      https://eureka.internal:8761/eureka/apps

Kết quả mong đợi là 401. Không đưa password thật vào command history hoặc tài liệu chia sẻ. Trong môi trường cần kiểm thử tự động, lấy credentials từ secret store của pipeline và tránh in biến ra log.

## 11. Xác minh client đăng ký và gửi heartbeat

Sau khi xác nhận server chấp nhận Basic Auth, khởi động một Eureka Client với URL có credentials.

Kiểm tra:

1. Log client cho thấy đã đăng ký instance thành công.
2. Eureka Dashboard hiển thị đúng application name và instance ID.
3. Client tiếp tục gửi heartbeat mà không nhận 401 hoặc 403.
4. Consumer khác có thể fetch registry bằng credentials hợp lệ.
5. Request không có credentials bị từ chối.
6. Request tới endpoint health được xử lý theo rule đã cấu hình.

Không chỉ kiểm tra dashboard bằng trình duyệt. Browser có thể giữ thông tin xác thực trong phiên, trong khi client service vẫn dùng credentials khác hoặc URL cấu hình sai.

## 12. Giới hạn của HTTP Basic trong Eureka

HTTP Basic là cách đơn giản cho xác thực máy-máy nhưng có một số giới hạn:

- Credentials thường được nhúng trong URL Eureka Client; cần bảo vệ cấu hình và log.
- Cấu hình defaultZone thông thường chỉ tiện cho một bộ credentials dùng chung.
- Eureka có giới hạn với nhiều URL server dùng các bộ Basic Auth khác nhau: không hỗ trợ credentials riêng cho từng server trong danh sách, và chỉ bộ credentials đầu tiên được tìm thấy được sử dụng.
- Basic Auth không tự cấp danh tính riêng cho từng instance nếu mọi client dùng chung một user.
- Basic Auth không tự mã hóa traffic; HTTPS vẫn bắt buộc trên mạng không tin cậy.
- Basic Auth không thay thế phân quyền theo role hoặc network policy.

Nếu cần cách xác thực phức tạp hơn, Spring Cloud Netflix cho phép tạo DiscoveryClientOptionalArgs và thêm ClientFilter để tùy chỉnh request từ client tới server. Hãy cân nhắc cơ chế xác thực phù hợp với hạ tầng thay vì mở rộng thủ công khi HTTP Basic đã đáp ứng yêu cầu.

## 13. Lưu ý đặc biệt khi chạy Eureka cluster

Bảo vệ client request bằng Spring Security không đồng nghĩa mọi request giữa các Eureka Server peer cũng được bảo vệ bằng cùng filter chain.

Spring Cloud Netflix lưu ý các request replication giữa Eureka Server, ví dụ /eureka/peerreplication/..., là request nội bộ và không đi qua Spring Security filter tiêu chuẩn. Vì vậy, cấu hình SecurityFilterChain ở trên không tự bảo vệ peer replication.

Khi triển khai nhiều Eureka Server:

- Giới hạn peer communication trong network nội bộ.
- Dùng firewall hoặc security group chỉ cho phép peer hợp lệ.
- Cân nhắc TLS/mTLS cho đường truyền giữa các peer.
- Nếu cần thêm authentication header cho replication, cấu hình ReplicationClientAdditionalFilters theo hướng dẫn Spring Cloud Netflix.
- Kiểm thử registration từ client và replication giữa peer như hai luồng riêng.
- Không giả định Basic Auth của client URL tự động bảo vệ peer replication.

Nếu một peer không thể replicate, các server có thể có registry state khác nhau. Hãy theo dõi peer replication và kiểm tra cấu hình mạng, TLS cùng custom filter riêng.

## 14. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Client nhận 401 | Username/password sai hoặc thiếu | Kiểm tra secret ở server và URL defaultZone của client |
| Client nhận 403 khi đăng ký | CSRF vẫn chặn POST/PUT hoặc user thiếu quyền | Kiểm tra matcher /eureka/** và authorization rule |
| Dashboard hỏi đăng nhập liên tục | Credentials sai, user không tồn tại hoặc proxy không chuyển Authorization header | Gọi trực tiếp API bằng curl và kiểm tra proxy |
| GET registry thành công nhưng đăng ký thất bại | CSRF matcher chưa áp dụng đúng API path hoặc method bị chặn | Kiểm tra request POST/PUT và security log |
| Client không gửi Basic Auth | URL không chứa user-info hợp lệ hoặc cấu hình service URL sai | Kiểm tra defaultZone, placeholder và log client |
| Password chứa ký tự @ hoặc : làm URL lỗi | User-info chưa percent-encode | Encode riêng username/password |
| TLS handshake thất bại | Client không tin cậy certificate hoặc hostname không khớp | Kiểm tra trust store, CA và SAN |
| Một peer không nhận replication | Peer replication không đi qua Spring Security filter chuẩn | Kiểm tra network, TLS và ReplicationClientAdditionalFilters |
| Actuator health trả 401 | Security rule không permit health endpoint hoặc matcher sai | Kiểm tra endpoint thực tế và policy |
| Credentials xuất hiện trong log | URL chứa user-info bị ghi lại | Che URL, tắt log nhạy cảm và luân chuyển secret nếu đã lộ |

Khi chẩn đoán, phân biệt:

- 401 Unauthorized: chưa xác thực được credentials.
- 403 Forbidden: đã xác thực nhưng không có quyền, hoặc request bị CSRF từ chối.
- 404 Not Found: sai context path hoặc URL Eureka.
- SSLHandshakeException: lỗi TLS/certificate, không phải lỗi Basic Auth.

Không tắt CSRF toàn ứng dụng để xử lý 403 của Eureka. Hãy xác minh request có nằm trong /eureka/** và matcher đã được áp dụng đúng.

## 15. Quản lý credentials và vận hành an toàn

Một số nguyên tắc cần áp dụng:

- Tạo credentials riêng cho Eureka Client hoặc nhóm client khi hệ thống cần khả năng thu hồi độc lập.
- Dùng secret manager hoặc secret của nền tảng để cấp username/password.
- Không commit credentials, không đưa vào image layer và không in chúng trong log.
- Luân chuyển password theo quy trình có kiểm soát; cập nhật client và server để tránh gián đoạn đăng ký.
- Dùng password encoder phù hợp khi tự quản lý UserDetailsService.
- Giới hạn quyền đọc registry và dashboard theo vai trò.
- Bảo vệ Actuator, reverse proxy và đường truyền nội bộ.
- Theo dõi số lần authentication failure, nguồn request và thay đổi registration bất thường.
- Dùng HTTPS và xác minh certificate ở cả client lẫn server.
- Khi có Eureka peer, bảo vệ peer replication riêng với luồng client authentication.

Basic Auth phù hợp cho thiết lập đơn giản hoặc mạng nội bộ được kiểm soát. Nếu yêu cầu có danh tính workload riêng, token ngắn hạn, phân quyền chi tiết hoặc audit theo service, hãy đánh giá cơ chế xác thực mạnh hơn thay vì dùng một password dùng chung lâu dài.

## 16. Quy trình triển khai theo từng bước

Có thể triển khai theo thứ tự sau để dễ kiểm tra:

1. Thêm Eureka Server starter và Spring Security starter.
2. Tạo Eureka Server bằng @EnableEurekaServer.
3. Cấu hình HTTPS và certificate trước khi truyền credentials.
4. Khai báo user hoặc UserDetailsService.
5. Tạo SecurityFilterChain yêu cầu authentication cho dashboard và API.
6. Bỏ CSRF riêng cho /eureka/**, giữ các rule CSRF khác.
7. Expose health endpoint tối thiểu và bảo vệ các Actuator endpoint còn lại.
8. Dùng curl xác nhận không credentials nhận 401 và credentials đúng nhận 200.
9. Cấu hình Eureka Client defaultZone với credentials từ secret.
10. Khởi động client và xác minh đăng ký, heartbeat, fetch registry.
11. Nếu chạy cluster, kiểm thử peer replication và bảo vệ đường truyền peer riêng.
12. Kiểm tra log, audit và quy trình rotate credentials trước khi đưa vào production.

Thực hiện từng bước trên môi trường test trước. Khi đổi password, có thể triển khai theo giai đoạn: thêm credential mới ở server, cập nhật client, xác minh client hoạt động rồi thu hồi credential cũ nếu kho user hỗ trợ song song hai credential.

## 17. Kết luận

Spring Security bảo vệ Eureka Server bằng cách yêu cầu xác thực cho dashboard và HTTP API. HTTP Basic có thể được bật bằng SecurityFilterChain; cần bỏ CSRF riêng cho /eureka/** vì Eureka Client không gửi CSRF token khi đăng ký và cập nhật instance. Ở phía client, Spring Cloud Netflix tự gửi Basic credentials khi URL eureka.client.serviceUrl.defaultZone chứa username và password.

Cấu hình này chỉ hoàn chỉnh khi đi cùng HTTPS, quản lý secret, phân quyền và kiểm tra hoạt động thực tế. Với Eureka cluster, peer replication là luồng riêng không đi qua Spring Security filter tiêu chuẩn nên phải bảo vệ bổ sung. Hãy xác minh cả API authentication, client registration, heartbeat, dashboard và peer replication trước khi triển khai rộng.

## Tài liệu tham khảo

- [Spring Cloud Netflix — Securing the Eureka Server](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Netflix — Authenticating with the Eureka Server](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Boot — Spring Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [Spring Boot — Configure SSL for Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [RFC 7617 — The Basic HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617.html)

