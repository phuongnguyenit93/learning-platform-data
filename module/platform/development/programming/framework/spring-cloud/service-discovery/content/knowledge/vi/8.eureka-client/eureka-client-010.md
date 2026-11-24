# Các tùy chọn kết nối HTTP của Eureka Client theo phiên bản

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt HTTP transport mà Eureka Client dùng để gọi Eureka Server với HTTP client dùng để gọi các microservice khác.
- Nhận biết thay đổi lựa chọn transport giữa các thế hệ Spring Cloud Netflix.
- Cấu hình RestTemplate, RestClient, WebClient hoặc Jersey theo phiên bản đang dùng.
- Đặt connect timeout, connection-request timeout và socket/read timeout đúng namespace property.
- Cấu hình proxy, TLS, xác thực và tùy biến HTTP request factory.
- Xác minh transport thực tế mà ứng dụng đã khởi tạo và xử lý lỗi kết nối thường gặp.

## 1. Eureka Client dùng HTTP ở đâu?

Eureka Client giao tiếp với Eureka Server qua HTTP để thực hiện các thao tác như đăng ký instance, gửi heartbeat, cập nhật metadata và tải registry. Phần HTTP này là transport nội bộ của Eureka Client.

Transport này khác với HTTP client mà code nghiệp vụ dùng để gọi order-service, inventory-service hoặc một API bên ngoài. Ví dụ, ứng dụng có thể dùng WebClient để gọi API nghiệp vụ nhưng Eureka Client vẫn dùng RestTemplate hoặc RestClient để trao đổi với registry. Việc bật eureka.client.webclient.enabled chỉ chọn transport cho Eureka Client; nó không tự chuyển mọi HTTP call trong ứng dụng sang WebClient.

Các transport có thể gặp trong những phiên bản Spring Cloud Netflix:

- **JerseyClient:** transport gắn với các thế hệ Netflix Eureka cũ.
- **RestTemplate:** transport đồng bộ dựa trên Spring Web.
- **RestClient:** HTTP client đồng bộ mới hơn của Spring Framework.
- **WebClient:** HTTP client của Spring WebFlux, hỗ trợ mô hình reactive.

Transport được chọn phụ thuộc vào phiên bản Spring Cloud Netflix, dependency có trên classpath và các cờ cấu hình. Vì vậy, không nên sao chép một property từ bài viết của phiên bản khác mà chưa kiểm tra release train của dự án.

## 2. Khác biệt lựa chọn HTTP client theo phiên bản

Bảng sau tóm tắt hành vi được mô tả trong tài liệu Spring Cloud Netflix chính thức. Đây là cách lựa chọn theo từng nhánh phiên bản; dependency thực tế trên classpath vẫn có thể làm thay đổi điều kiện auto-configuration.

| Nhánh Spring Cloud Netflix | Transport thường được chọn | Tùy chọn đáng chú ý |
| --- | --- | --- |
| 2.2.x (Hoxton) | Jersey là mặc định trong tài liệu của nhánh này. | Có thể loại Jersey khỏi dependency để Spring Cloud cấu hình RestTemplate. |
| 3.0.x | RestTemplate là mặc định theo tài liệu 3.0.3. | Jersey có thể được thêm như lựa chọn thay thế. |
| 4.1.x | RestTemplate là mặc định. | WebClient có thể được chọn bằng eureka.client.webclient.enabled=true; Jersey là lựa chọn bổ sung nếu thêm dependency. |
| 4.2.x – 4.3.x | RestTemplate vẫn là mặc định. | Có thể bật RestClient bằng eureka.client.restclient.enabled=true hoặc chọn WebClient bằng eureka.client.webclient.enabled=true. |
| 5.0.x – 5.1.x | RestClient là mặc định được tài liệu hiện hành mô tả. | WebClient được chọn khi có module cần thiết và bật eureka.client.webclient.enabled=true; Jersey vẫn có thể được dùng nếu thêm dependency. RestTemplate không còn nằm trong danh sách transport của tài liệu 5.x. |

### Nhánh 2.2.x: Jersey mặc định

Ở nhánh Hoxton/2.2.x, tài liệu Spring Cloud Netflix mô tả Jersey là HTTP client mặc định. Nếu muốn tránh dependency Jersey, có thể loại các artifact Jersey khỏi starter Eureka Client để Spring Cloud tự cấu hình transport dựa trên RestTemplate.

Ví dụ Maven loại Jersey:

~~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    <exclusions>
        <exclusion>
            <groupId>com.sun.jersey</groupId>
            <artifactId>jersey-client</artifactId>
        </exclusion>
        <exclusion>
            <groupId>com.sun.jersey</groupId>
            <artifactId>jersey-core</artifactId>
        </exclusion>
        <exclusion>
            <groupId>com.sun.jersey.contribs</groupId>
            <artifactId>jersey-apache-client4</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~~

Đây là cấu hình dành cho dự án dùng nhánh cũ. Không áp dụng máy móc các exclusion này cho mọi nhánh mới; hãy xem dependency tree của chính phiên bản đang dùng.

### Nhánh 3.0.x – 4.1.x: RestTemplate mặc định

Tài liệu 3.0.3 mô tả RestTemplate là mặc định và Jersey là lựa chọn thay thế khi thêm dependency. Tài liệu 4.1.x tiếp tục dùng RestTemplate mặc định, đồng thời mô tả cách chọn WebClient bằng spring-boot-starter-webflux và cờ sau:

~~~~yaml
eureka:
  client:
    webclient:
      enabled: true
~~~~

Khi ứng dụng có cả Spring Web và WebFlux, cờ này giúp Spring Cloud chọn WebClient cho phần giao tiếp Eureka. Nếu không bật, RestTemplate vẫn là lựa chọn mặc định theo tài liệu nhánh này.

### Nhánh 4.2.x – 4.3.x: bổ sung RestClient

Nhánh 4.2.x và 4.3.x hỗ trợ thêm RestClient, nhưng RestTemplate vẫn là lựa chọn mặc định nếu không bật transport khác.

Để chọn RestClient, cần có Spring Web trên classpath và đặt:

~~~~yaml
eureka:
  client:
    restclient:
      enabled: true
~~~~

Để chọn WebClient, thêm Spring WebFlux và đặt:

~~~~yaml
eureka:
  client:
    webclient:
      enabled: true
~~~~

Theo thứ tự lựa chọn được tài liệu mô tả, khi có cả Spring Web và WebFlux, webclient.enabled=true chọn WebClient. Nếu điều kiện đó không thỏa mãn nhưng restclient.enabled=true, RestClient được chọn. Nếu không có cờ tương ứng, RestTemplate được chọn.

Nếu dependency Jersey có mặt và được bật, hãy kiểm tra điều kiện auto-configuration và log lựa chọn transport. Khi muốn dùng Spring HTTP client, có thể đặt rõ eureka.client.jersey.enabled=false để tránh Jersey được chọn ngoài dự kiến.

### Nhánh 5.x: RestClient mặc định

Trong tài liệu Spring Cloud Netflix 5.0.x và 5.1.x, Eureka Client dùng RestClient, WebClient hoặc Jersey. RestTemplate không còn được liệt kê trong danh sách transport của nhánh này.

Với Spring Boot 4, dependency được tách thành các module. Nếu chỉ dùng RestClient, thêm:

~~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-restclient")
}
~~~~

Nếu muốn dùng WebClient, thêm module:

~~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-webclient")
}
~~~~

Khi cả hai module có mặt, bật cờ sau để chọn WebClient; nếu không, RestClient là lựa chọn mặc định được tài liệu mô tả:

~~~~yaml
eureka:
  client:
    webclient:
      enabled: true
~~~~

Tên artifact ở nhánh 5.x khác với spring-boot-starter-web và spring-boot-starter-webflux thường thấy trong các dự án Spring Boot 3.x. Hãy kiểm tra dependency management của Spring Boot và Spring Cloud release train đang dùng trước khi thêm module.

## 3. Chọn transport và dependency đúng cách

Trước khi thay đổi transport, hãy kiểm tra phiên bản Spring Boot và Spring Cloud Netflix được quản lý bởi BOM. Không nâng riêng spring-cloud-starter-netflix-eureka-client hoặc tự gán phiên bản Spring Web để ép một transport mới vào dự án.

Một quy trình an toàn:

1. Xác định Spring Cloud release train và phiên bản Spring Cloud Netflix thực tế.
2. Xem dependency tree để biết Jersey, Spring Web, WebFlux, RestClient hoặc WebClient có trên classpath hay không.
3. Đối chiếu bảng lựa chọn transport của nhánh phiên bản.
4. Chỉ thêm module cần thiết và đặt cờ lựa chọn rõ ràng nếu có nhiều transport.
5. Khởi động ứng dụng và kiểm tra log cho biết Eureka HTTP Client đã dùng transport nào.
6. Kiểm thử đăng ký, heartbeat, fetch registry và kết nối khi Eureka Server tạm thời không sẵn sàng.

Không nên thêm WebFlux chỉ để sử dụng WebClient cho Eureka nếu ứng dụng không cần hệ sinh thái reactive. Tương tự, không giữ Jersey chỉ vì dependency cũ còn được kéo vào transitively mà không có lý do tương thích.

## 4. Cấu hình URL và danh sách Eureka Server

Địa chỉ Eureka Server được cấu hình bằng eureka.client.service-url. Khóa defaultZone là tên map key có phân biệt chữ hoa/chữ thường; giữ nguyên camel case:

~~~~yaml
eureka:
  client:
    service-url:
      defaultZone: https://eureka-a.internal:8761/eureka/,https://eureka-b.internal:8761/eureka/
~~~~

Có thể khai báo nhiều URL để client có các endpoint Eureka thay thế. Hãy bảo đảm mọi URL có scheme, hostname, port và context path đúng với môi trường. Với môi trường production, dùng HTTPS nếu hạ tầng yêu cầu bảo vệ lưu lượng.

defaultZone xác định nơi client kết nối; nó không chọn RestTemplate, RestClient hay WebClient. Hai nhóm cấu hình có nhiệm vụ khác nhau.

## 5. Timeout: đặt đúng property theo transport và phiên bản

Timeout quyết định ứng dụng chờ bao lâu khi thiết lập kết nối và đọc phản hồi từ Eureka Server. Một cấu hình quá dài có thể khiến startup hoặc tác vụ nền bị treo lâu khi mạng lỗi. Cấu hình quá ngắn có thể tạo lỗi giả khi mạng có độ trễ cao.

Ba loại timeout thường gặp:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| connect-timeout | Thời gian tối đa để thiết lập kết nối TCP tới Eureka Server. |
| connect-request-timeout | Thời gian chờ lấy một kết nối từ connection pool hoặc chờ yêu cầu cấp kết nối. |
| socket-timeout | Thời gian chờ dữ liệu phản hồi sau khi kết nối đã được thiết lập; thường được hiểu như read timeout. |

Tài liệu Spring Cloud Netflix mô tả giá trị mặc định của các timeout HTTP này là 180.000 ms (3 phút) ở các transport Spring được đề cập. Nên đặt giá trị rõ ràng theo ngân sách thời gian của ứng dụng và đặc điểm mạng thay vì dựa vào mặc định dài.

### 4.1.x: RestTemplate timeout

Với nhánh 4.1.x, dùng eureka.client.rest-template-timeout. Tất cả giá trị tính bằng millisecond:

~~~~yaml
eureka:
  client:
    rest-template-timeout:
      connect-timeout: 5000
      connect-request-timeout: 8000
      socket-timeout: 10000
~~~~

Nhóm property này cấu hình transport RestTemplate. Không dùng nó để kỳ vọng điều khiển WebClient hoặc một transport Jersey khác.

### 4.2.x – 4.3.x: RestTemplate và RestClient timeout

Các nhánh 4.2.x–4.3.x có hai nhóm cấu hình riêng. Nếu dùng RestTemplate:

~~~~yaml
eureka:
  client:
    rest-template-timeout:
      connect-timeout: 5000
      connect-request-timeout: 8000
      socket-timeout: 10000
~~~~

Nếu dùng RestClient:

~~~~yaml
eureka:
  client:
    restclient:
      timeout:
        connect-timeout: 5000
        connect-request-timeout: 8000
        socket-timeout: 10000
~~~~

Cả hai nhóm đều dùng millisecond. Chọn đúng nhóm theo transport thực tế. Cấu hình rest-template-timeout không thay thế cấu hình restclient.timeout và ngược lại.

### 5.x: timeout dùng namespace eureka.client.timeout

Với tài liệu 5.1.x, nhóm property timeout được công bố dưới eureka.client.timeout:

~~~~yaml
eureka:
  client:
    timeout:
      connect-timeout: 5000
      connect-request-timeout: 8000
      socket-timeout: 10000
~~~~

Các giá trị tính bằng millisecond. Đừng sao chép nguyên rest-template-timeout hoặc restclient.timeout từ dự án 4.x sang 5.x mà không đối chiếu configuration properties của phiên bản đích.

### Lựa chọn giá trị timeout

Các giá trị 5/8/10 giây trong ví dụ chỉ là điểm bắt đầu minh họa, không phải chuẩn áp dụng cho mọi hệ thống. Khi đặt timeout:

- Connect timeout nên ngắn hơn deadline tổng của thao tác đăng ký hoặc fetch registry.
- Connection-request timeout cần tính đến giới hạn pool và số request đồng thời.
- Socket timeout cần đủ cho phản hồi registry lớn, nhất là khi client tải toàn bộ registry.
- Tổng timeout cần phù hợp với retry/backoff để một lỗi mạng không kéo dài vô hạn tác vụ nền.
- Kiểm thử cả lúc registry khỏe, tải cao, mạng chậm và registry không thể truy cập.

## 6. Connection pool và kết nối nhàn rỗi

Eureka Client thường tái sử dụng kết nối HTTP để gửi heartbeat và truy vấn registry. Pool giúp giảm chi phí tạo kết nối mới, nhưng cần giới hạn hợp lý theo số request đồng thời và số Eureka Server.

Một số thuộc tính legacy trong configuration properties có thể xuất hiện ở nhiều nhánh:

| Property | Ý nghĩa | Đơn vị |
| --- | --- | --- |
| eureka.client.eureka-connection-idle-timeout-seconds | Thời gian kết nối nhàn rỗi trước khi có thể đóng. | Giây |
| eureka.client.eureka-server-total-connections | Giới hạn tổng kết nối đến các Eureka Server. | Số kết nối |
| eureka.client.eureka-server-total-connections-per-host | Giới hạn kết nối đến một Eureka Server host. | Số kết nối |
| eureka.client.eureka-server-connect-timeout-seconds | Connect timeout của nhóm transport legacy. | Giây |
| eureka.client.eureka-server-read-timeout-seconds | Read timeout của nhóm transport legacy. | Giây |

Các property legacy này không nên được xem là cấu hình thay thế cho timeout namespace của RestTemplate/RestClient ở mọi phiên bản. Khả năng áp dụng phụ thuộc transport và implementation đang được auto-configure. Khi chuyển sang RestClient hoặc WebClient, hãy kiểm tra configuration properties và tài liệu đúng phiên bản; không giả định các giới hạn pool cũ tự động điều khiển pool mới.

Trong môi trường có firewall hoặc NAT đóng kết nối nhàn rỗi, thời gian idle của pool cần tương thích với timeout của hạ tầng. Nếu firewall xóa trạng thái kết nối trước khi client nhận biết, client có thể gặp lỗi trên một kết nối đã bị đóng ở giữa đường. Theo dõi log reset/closed connection và thử tải lại registry để xác định nguyên nhân.

## 7. Proxy, TLS và xác thực HTTP

### HTTP proxy

Nếu Eureka Server chỉ truy cập được thông qua proxy, có thể cấu hình các thuộc tính proxy được hỗ trợ:

~~~~yaml
eureka:
  client:
    proxy-host: proxy.internal
    proxy-port: 8080
    proxy-user-name: eureka-client
    # proxy-password lấy từ secret store hoặc biến môi trường
~~~~

Không ghi password thật vào file cấu hình được commit. Hãy xác nhận proxy cho phép kết nối đến toàn bộ peer URL và không chặn các đường dẫn API Eureka.

### TLS và mutual TLS

Khi Eureka Server yêu cầu client certificate, bật TLS và cấu hình keystore/truststore:

~~~~yaml
eureka:
  client:
    tls:
      enabled: true
      key-store: /run/secrets/eureka-client.p12
      key-store-type: PKCS12
      key-store-password: LOAD_FROM_SECRET_STORE
      key-password: LOAD_FROM_SECRET_STORE
      trust-store: /run/secrets/eureka-trust.p12
      trust-store-type: PKCS12
      trust-store-password: LOAD_FROM_SECRET_STORE
~~~~

Nếu không khai báo truststore, tài liệu Spring Cloud Netflix mô tả JVM default truststore sẽ được sử dụng. Kiểu keystore và truststore mặc định được mô tả là PKCS12. Quản lý mật khẩu bằng secret store; không commit giá trị thật.

TLS bảo vệ đường truyền. Với mutual TLS, client trình chứng thư để server xác thực danh tính kết nối. Chứng thư, hostname và trust chain phải phù hợp với cấu hình của Eureka Server.

### HTTP Basic Authentication

Tài liệu Eureka hỗ trợ Basic Authentication khi URL defaultZone chứa thông tin user/password. Tuy nhiên, credential trong URL có thể xuất hiện trong log, cấu hình đã render hoặc công cụ quan sát. Hãy dùng secret injection và bảo vệ cấu hình truy cập.

Eureka có giới hạn về credential riêng cho từng server URL: tài liệu Spring Cloud Netflix lưu ý chỉ bộ credential đầu tiên được tìm thấy được sử dụng. Nếu cần xác thực phức tạp hơn, có thể tùy biến các filter của Eureka Client qua DiscoveryClientOptionalArgs và ClientFilter, theo API mà nhánh phiên bản hỗ trợ.

## 8. Tùy biến HTTP request factory

Với RestTemplate/RestClient ở các nhánh hỗ trợ, có thể tùy biến ClientHttpRequestFactory thông qua bean EurekaClientHttpRequestFactorySupplier. Điều này hữu ích khi cần điều chỉnh Apache HttpClient 5, connection pool hoặc request configuration theo chính sách hạ tầng.

Ví dụ Spring Cloud Netflix 4.2.x/4.3.x và tài liệu hiện hành minh họa hook tùy biến Apache HttpClient 5:

~~~~java
@Configuration
public class EurekaHttpConfiguration {

    @Bean
    EurekaClientHttpRequestFactorySupplier.RequestConfigCustomizer
            requestConfigCustomizer() {
        return builder -> builder.setProtocolUpgradeEnabled(false);
    }
}
~~~~

Đây là ví dụ tùy biến RequestConfig; nó không phải cấu hình bắt buộc cho mọi ứng dụng. Chỉ thêm customizer khi có yêu cầu cụ thể và kiểm tra API class trong phiên bản đang dùng.

Tài liệu cũng nêu rằng nếu có bean builder phù hợp trên ApplicationContext, Eureka Client có thể sử dụng builder đó để tạo HTTP client nền. Vì vậy, khi ứng dụng đồng thời khai báo builder thường và builder có @LoadBalanced, cần kiểm tra bean nào được inject vào transport Eureka. Không để interceptor hoặc cấu hình load balancing dành cho request nghiệp vụ vô tình được áp dụng vào request gọi registry.

Với WebClient, hãy cấu hình WebClient.Builder hoặc connector tương ứng theo API của Spring WebFlux và phiên bản Spring Boot. Các property timeout của RestTemplate/RestClient không tự động áp dụng cho WebClient.

## 9. Kiểm tra transport thực tế khi ứng dụng khởi động

Đừng chỉ dựa vào YAML để kết luận transport nào đang hoạt động. Auto-configuration còn phụ thuộc dependency và điều kiện bean.

Các bước kiểm tra:

1. Xem phiên bản spring-cloud-starter-netflix-eureka-client đã resolve từ BOM.
2. Xem dependency tree để xác nhận có Jersey, Spring Web, WebFlux hoặc module RestClient/WebClient.
3. Kiểm tra các cờ eureka.client.jersey.enabled, eureka.client.restclient.enabled và eureka.client.webclient.enabled nếu nhánh phiên bản hỗ trợ.
4. Đọc log startup tìm thông báo transport, ví dụ Eureka HTTP Client sử dụng RestTemplate, RestClient, WebClient hoặc Jersey.
5. Nếu chưa rõ, chạy ứng dụng với debug auto-configuration hoặc kiểm tra điều kiện tạo bean bằng công cụ phù hợp.
6. Xác nhận client đăng ký được, gửi heartbeat và fetch registry sau khi transport đã khởi tạo.

Có thể dùng một cấu hình thử nghiệm tách biệt cho từng transport, nhưng không nên bật nhiều cờ cùng lúc rồi đoán kết quả. Mỗi lần thử chỉ thay đổi một lựa chọn, giữ nguyên URL và môi trường server để so sánh.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| ClassNotFoundException hoặc thiếu class HTTP client | Thiếu module tương ứng hoặc dùng artifact của sai thế hệ Spring Boot. | Kiểm tra dependency tree và tên artifact theo nhánh 4.x/5.x. |
| Ứng dụng vẫn dùng RestTemplate dù đã thêm WebClient | Chưa bật eureka.client.webclient.enabled, hoặc WebFlux không có trên classpath. | Kiểm tra property và module WebFlux/WebClient. |
| 4.2/4.3 không chuyển sang RestClient | Chưa bật eureka.client.restclient.enabled hoặc thiếu Spring Web. | Kiểm tra cờ và dependency đã resolve. |
| Jersey vẫn được chọn ngoài dự kiến | Jersey có trên classpath và cờ Jersey vẫn bật. | Kiểm tra dependency tree; đặt eureka.client.jersey.enabled=false nếu muốn dùng Spring HTTP client. |
| Timeout property không có tác dụng | Dùng sai namespace của phiên bản hoặc đang cấu hình nhầm transport. | Đối chiếu 4.1, 4.2/4.3 và 5.x; kiểm tra transport thực tế. |
| Lỗi connect timeout | Sai hostname/port, DNS, firewall, proxy hoặc server chưa chạy. | Kiểm tra phân giải tên và kết nối TCP từ chính môi trường ứng dụng. |
| Lỗi socket/read timeout | Server phản hồi chậm, registry response lớn hoặc mạng không ổn định. | Đo thời gian phản hồi, xem log server và điều chỉnh timeout có kiểm soát. |
| Lỗi SSL handshake | Truststore thiếu CA, chứng thư hết hạn, hostname không khớp hoặc client certificate sai. | Kiểm tra certificate chain, SAN, thời hạn và cấu hình TLS hai phía. |
| HTTP 401/403 | Sai credential hoặc chính sách xác thực/CSRF trên server. | Kiểm tra cấu hình bảo mật và quyền của client. |
| Kết nối thường xuyên bị đóng khi nhàn rỗi | Firewall/NAT đóng connection trước pool timeout. | Đồng bộ idle timeout và theo dõi connection reset. |
| Client đăng ký được nhưng fetch registry lỗi | Transport có thể gửi được một số request nhưng bị chặn ở endpoint hoặc payload khác. | Kiểm tra quyền truy cập, proxy route, log fetch và response từ Eureka Server. |

## 11. Checklist chọn cấu hình

- [ ] Đã xác định phiên bản Spring Cloud Netflix và Spring Boot tương thích.
- [ ] Đã chọn transport theo đúng tài liệu của nhánh phiên bản.
- [ ] Dependency chỉ chứa các HTTP client cần thiết.
- [ ] Không có Jersey cũ trên classpath ngoài chủ đích.
- [ ] defaultZone trỏ đúng endpoint và giữ nguyên defaultZone camel case.
- [ ] Timeout dùng đúng namespace và đơn vị millisecond/second.
- [ ] Connection pool phù hợp với số peer và lưu lượng đăng ký/fetch.
- [ ] Proxy, TLS và authentication được cấu hình theo hạ tầng thực tế.
- [ ] Secret được lấy từ secret store, không commit vào repository.
- [ ] Log startup xác nhận đúng transport được chọn.
- [ ] Đã thử registration, heartbeat, registry fetch và tình huống mất kết nối.
- [ ] Đã xác minh cấu hình không ảnh hưởng nhầm đến HTTP client dùng cho request nghiệp vụ.

## Ghi nhớ

- HTTP transport của Eureka Client chỉ phục vụ giao tiếp với Eureka Server; nó không phải HTTP client chung của ứng dụng.
- 2.2.x dùng Jersey mặc định trong tài liệu cũ; 3.0.x–4.1.x mặc định RestTemplate; 4.2.x–4.3.x thêm lựa chọn RestClient; 5.x chuyển mặc định sang RestClient.
- eureka.client.webclient.enabled chọn WebClient cho giao tiếp Eureka khi dependency phù hợp có trên classpath.
- Timeout property thay đổi theo phiên bản: rest-template-timeout, restclient.timeout hoặc eureka.client.timeout.
- Các giá trị timeout trong nhóm Spring HTTP client dùng millisecond; các property legacy có hậu tố -seconds dùng giây.
- Proxy, TLS, xác thực và connection pool cần được kiểm tra cùng transport thực tế.
- Luôn xác nhận transport bằng dependency tree và log startup, không chỉ nhìn file YAML.

## Tài liệu tham khảo chính thức

- [Spring Cloud Netflix 2.2.8 – Eureka Client](https://docs.spring.io/spring-cloud-netflix/docs/2.2.8.RELEASE/reference/html/)
- [Spring Cloud Netflix 3.0.3 – Eureka Client](https://docs.spring.io/spring-cloud-netflix/docs/3.0.3/reference/html/)
- [Spring Cloud Netflix 4.1 – Features](https://docs.spring.io/spring-cloud-netflix/reference/4.1/spring-cloud-netflix.html)
- [Spring Cloud Netflix 4.2 – Features](https://docs.spring.io/spring-cloud-netflix/reference/4.2/spring-cloud-netflix.html)
- [Spring Cloud Netflix 4.3 – Features](https://docs.spring.io/spring-cloud-netflix/reference/4.3/spring-cloud-netflix.html)
- [Spring Cloud Netflix 5.1 – Features](https://docs.spring.io/spring-cloud-netflix/reference/5.1/spring-cloud-netflix.html)
- [Spring Cloud Netflix 5.1 – Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/5.1/configprops.html)
