# Tách danh sách dịch vụ theo profile và môi trường

Trong môi trường phát triển, kiểm thử và production, cùng một microservice thường có các địa chỉ instance khác nhau. Ví dụ, inventory-service có thể chạy trên localhost khi lập trình, dùng DNS service name trong Docker Compose khi tích hợp và dùng hostname nội bộ khi triển khai production. Nếu ghi các địa chỉ này trực tiếp trong mã nguồn, mỗi lần chuyển môi trường ứng dụng lại phải thay đổi hoặc đóng gói lại.

Spring Cloud SimpleDiscoveryClient cho phép khai báo service ID và danh sách URI bằng cấu hình. Spring Boot Profiles chọn tập cấu hình tương ứng với môi trường đang chạy. Nhờ đó, cùng một ứng dụng có thể tra cứu service theo tên logic nhưng nhận được địa chỉ phù hợp với profile hiện tại.

## 1. SimpleDiscoveryClient và cấu hình tĩnh

Spring Cloud cung cấp abstraction DiscoveryClient để tra cứu service ID thành danh sách ServiceInstance. Khi không có implementation DiscoveryClient gắn với registry server trên classpath, Spring Cloud có thể sử dụng SimpleDiscoveryClient. Implementation này đọc thông tin instance từ cấu hình ứng dụng.

Prefix cấu hình là:

    spring.cloud.discovery.client.simple.instances

Mỗi service ID có một danh sách instance được đánh chỉ số từ 0. Mỗi phần tử khai báo URI của instance:

    spring:
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: http://localhost:8081
                  - uri: http://localhost:8082
                payment-service:
                  - uri: http://localhost:8091

Trong ví dụ, inventory-service có hai instance và payment-service có một instance. Khi ứng dụng gọi DiscoveryClient.getInstances("inventory-service"), SimpleDiscoveryClient trả về hai ServiceInstance có URI tương ứng.

Cấu hình tĩnh không đăng ký instance lên Eureka hoặc Consul. Nó cũng không tự phát hiện instance mới, không thực hiện health check định kỳ và không tự cập nhật khi một địa chỉ ngừng hoạt động. Nhóm vận hành phải duy trì danh sách URI và triển khai lại hoặc nạp lại cấu hình theo cơ chế của ứng dụng khi danh sách thay đổi.

**Lưu ý về dependency:** SimpleDiscoveryClient được dùng khi không có DiscoveryClient dựa trên service registry trong classpath. Nếu ứng dụng đã thêm Consul Discovery hoặc Eureka Client, implementation tương ứng có thể được sử dụng thay cho SimpleDiscoveryClient. Khi muốn thực hành discovery tĩnh độc lập, hãy kiểm tra dependency discovery đang có trong ứng dụng; không giả định rằng chỉ cần thêm cấu hình simple.instances là sẽ ghi đè Consul hoặc Eureka.

## 2. Spring Profiles giúp tách cấu hình môi trường

Spring Profiles cho phép nạp một phần cấu hình chỉ khi profile tương ứng được kích hoạt. Spring Boot hỗ trợ file cấu hình theo quy ước:

- application.yml: cấu hình chung cho mọi môi trường.
- application-local.yml: cấu hình cho máy lập trình.
- application-test.yml: cấu hình cho môi trường kiểm thử.
- application-docker.yml: cấu hình khi các service chạy trong Docker network.
- application-prod.yml: cấu hình production.

Spring Boot nạp application.yml và file profile đang hoạt động. Các giá trị trong file profile-specific có độ ưu tiên cao hơn giá trị tương ứng trong file chung. Nếu nhiều profile cùng hoạt động, profile được xử lý sau có thể ghi đè giá trị của profile trước.

Có thể tổ chức thư mục cấu hình như sau:

    src/main/resources/
      application.yml
      application-local.yml
      application-test.yml
      application-docker.yml
      application-prod.yml

Cách tổ chức này giúp mỗi môi trường có danh sách instance riêng mà không phải thay đổi mã Java.

## 3. Đặt cấu hình chung trong application.yml

File chung nên chứa những thuộc tính không phụ thuộc môi trường, chẳng hạn tên ứng dụng và các cấu hình discovery dùng chung:

    spring:
      application:
        name: order-service

Không nên đặt một danh sách URI chỉ phù hợp với máy lập trình trong application.yml nếu file này được đóng gói và dùng ở nhiều môi trường. Nếu cấu hình chung chứa endpoint localhost, một profile bị thiếu hoặc không được kích hoạt có thể khiến ứng dụng production gọi nhầm về chính container của nó.

Có thể để danh sách instance hoàn toàn trong từng file profile-specific để tránh phải ghi đè danh sách mặc định.

## 4. Cấu hình danh sách instance cho local

Ví dụ application-local.yml:

    spring:
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: http://localhost:8081
                  - uri: http://localhost:8082
                payment-service:
                  - uri: http://localhost:8091

Khi chạy local, ứng dụng có thể tra cứu hai instance inventory-service và một instance payment-service. Các port này chỉ là ví dụ; chúng phải khớp với port thực tế mà các service đang lắng nghe trên máy phát triển.

Nếu một service chỉ có một instance, vẫn khai báo danh sách với một phần tử:

    spring:
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: http://localhost:8081

## 5. Cấu hình danh sách instance cho test và Docker

Trong integration test, service có thể chạy trên hostname hoặc port do test environment cấp. Ví dụ application-test.yml:

    spring:
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: http://inventory-test.internal:18081
                payment-service:
                  - uri: http://payment-test.internal:18091

Nếu ứng dụng chạy cùng các service trong Docker Compose network, nên dùng tên service làm hostname nội bộ thay vì localhost. Ví dụ application-docker.yml:

    spring:
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: http://inventory-service:8080
                  - uri: http://inventory-service-canary:8080
                payment-service:
                  - uri: http://payment-service:8080

Trong Docker, localhost bên trong container trỏ về chính container đó. Nếu order-service gọi localhost:8080, request sẽ đi tới order-service chứ không phải container inventory-service. DNS service name chỉ phân giải được khi các container nằm trong network phù hợp và service đích được khai báo đúng.

## 6. Cấu hình danh sách instance cho production

Ví dụ application-prod.yml:

    spring:
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: https://inventory-a.internal:8443
                  - uri: https://inventory-b.internal:8443
                payment-service:
                  - uri: https://payment.internal:9443

Trong production, chỉ khai báo hostname và port đã được phê duyệt, có thể phân giải và truy cập từ mạng của ứng dụng gọi. Nếu endpoint dùng HTTPS, chứng chỉ và trust store của ứng dụng phải được cấu hình đúng.

Không đưa username, password, access token hoặc API key vào URI. Hãy dùng secret manager hoặc cơ chế quản lý secret của nền tảng để cung cấp thông tin xác thực riêng.

Cấu hình tĩnh chỉ phù hợp khi danh sách instance tương đối ổn định và có quy trình cập nhật rõ ràng. Nếu production thường xuyên scale, thay thế hoặc tạo instance tự động, registry động hoặc service discovery của nền tảng triển khai thường phù hợp hơn.

## 7. Kích hoạt profile khi chạy ứng dụng

Có nhiều cách kích hoạt profile. Chọn một cách phù hợp với môi trường triển khai.

**Command line**

    java -jar order-service.jar --spring.profiles.active=local

**Environment variable trên Linux**

    SPRING_PROFILES_ACTIVE=test java -jar order-service.jar

**JVM system property**

    java -Dspring.profiles.active=docker -jar order-service.jar

**Docker Compose**

    services:
      order-service:
        image: example/order-service
        environment:
          SPRING_PROFILES_ACTIVE: docker
        networks:
          - backend

Giá trị profile phải khớp với hậu tố file cấu hình. SPRING_PROFILES_ACTIVE=docker khiến Spring Boot nạp application-docker.yml cùng application.yml.

Không nên để mặc định spring.profiles.active=prod trong file application.yml dùng chung. Nếu môi trường chạy quên đặt profile, ứng dụng có thể nạp nhầm cấu hình production trong máy phát triển hoặc ngược lại. Hãy xác định rõ profile tại lệnh khởi chạy, biến môi trường hoặc cấu hình triển khai.

## 8. Dùng nhiều profile cùng lúc

Spring Boot cho phép kích hoạt nhiều profile, phân tách bằng dấu phẩy:

    java -jar order-service.jar --spring.profiles.active=docker,observability

Trong đó docker cung cấp danh sách URI và observability có thể bật cấu hình log hoặc metric. Với cùng một thuộc tính được khai báo ở nhiều profile, quy tắc last-wins áp dụng: profile được xử lý sau có thể ghi đè giá trị của profile trước.

Có thể dùng profile group để gom các profile liên quan:

    spring:
      profiles:
        group:
          production:
            - prod
            - observability

Sau đó chỉ cần chạy:

    java -jar order-service.jar --spring.profiles.active=production

Spring Boot kích hoạt profile production và các profile thành viên. Các khai báo spring.profiles.group phải nằm trong tài liệu cấu hình không phụ thuộc profile, chẳng hạn application.yml; không đặt chúng trong application-prod.yml.

## 9. Multi-document YAML như một lựa chọn khác

Thay vì tạo nhiều file, có thể dùng nhiều tài liệu YAML trong cùng application.yml và kích hoạt từng tài liệu bằng spring.config.activate.on-profile:

    spring:
      application:
        name: order-service

    ---
    spring:
      config:
        activate:
          on-profile: local
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: http://localhost:8081
                  - uri: http://localhost:8082

    ---
    spring:
      config:
        activate:
          on-profile: docker
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: http://inventory-service:8080

    ---
    spring:
      config:
        activate:
          on-profile: prod
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: https://inventory-a.internal:8443
                  - uri: https://inventory-b.internal:8443

Chỉ tài liệu có biểu thức profile phù hợp mới được đưa vào Environment. Cách này tiện khi cấu hình ngắn và ít môi trường. Khi danh sách service dài hoặc từng môi trường có nhiều khác biệt, tách file application-{profile}.yml thường dễ bảo trì và review hơn.

## 10. Hiểu đúng precedence và cách merge cấu hình

Spring Boot cho phép nhiều nguồn cấu hình cùng cung cấp một thuộc tính. Profile-specific file ghi đè giá trị tương ứng trong file chung; command-line argument, environment variable và các nguồn có độ ưu tiên cao hơn cũng có thể thay đổi giá trị cuối cùng.

Với cấu hình SimpleDiscoveryClient, cần chú ý kiểu dữ liệu lồng nhau:

- instances là Map theo service ID.
- Giá trị của mỗi service ID là List các instance.
- Các key Map khác nhau có thể được bổ sung từ nhiều nguồn cấu hình.
- Nếu cùng một service ID có danh sách instance ở nhiều nguồn, danh sách có độ ưu tiên cao hơn thay thế toàn bộ danh sách trước đó; các phần tử không được tự nối thêm.

Ví dụ application.yml:

    spring:
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: http://inventory-default-1:8080
                  - uri: http://inventory-default-2:8080
                payment-service:
                  - uri: http://payment-default:8080

Ví dụ application-prod.yml:

    spring:
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: https://inventory-prod.internal:8443

Khi profile prod hoạt động, danh sách inventory-service chỉ chứa inventory-prod.internal:8443. Nó không tự giữ lại hai instance từ application.yml. payment-service vẫn có thể giữ giá trị chung vì đó là một key Map khác và không bị profile prod ghi đè.

Để tránh nhầm lẫn, nên khai báo đầy đủ toàn bộ instance của một service trong file profile khi service đó cần danh sách riêng cho môi trường. Không dựa vào việc một phần tử ở profile sẽ được thêm vào danh sách chung.

## 11. Profile mặc định và cấu hình kích hoạt sai

Nếu không có profile nào được kích hoạt rõ ràng, Spring Boot sử dụng profile mặc định tên default. Có thể khai báo application-default.yml để cung cấp cấu hình dành cho trường hợp này, nhưng với hệ thống có nhiều môi trường, nên chủ động đặt profile để tránh dùng nhầm danh sách URI.

Một số lỗi thường gặp:

- Đặt spring.profiles.active bên trong application-local.yml hoặc tài liệu YAML được kích hoạt bằng on-profile. Thuộc tính active chỉ được khai báo trong tài liệu không phụ thuộc profile.
- Gõ sai tên profile, ví dụ kích hoạt docker nhưng file là application-container.yml.
- Khai báo danh sách service trong application.yml trỏ tới localhost và quên ghi đè ở production.
- Kích hoạt đồng thời local và prod khiến một profile ghi đè URI của profile còn lại.
- Đặt danh sách profile trong command line nhưng quên rằng nó có thể thay thế giá trị active được khai báo ở nguồn cấu hình thấp hơn.
- Dùng spring.config.location trỏ tới file đơn lẻ rồi kỳ vọng Spring Boot tự tìm mọi biến thể profile-specific như khi dùng thư mục config location. Cần kiểm tra quy tắc Config Data của phiên bản đang sử dụng.

Hãy kiểm tra log khởi động để xác nhận các profile thực sự được kích hoạt. Không chỉ dựa vào tên file tồn tại trong JAR.

## 12. Kiểm tra DiscoveryClient nhận đúng danh sách

Có thể inject DiscoveryClient và in danh sách instance để xác nhận profile đang cung cấp đúng URI:

    import java.util.List;

    import org.springframework.cloud.client.ServiceInstance;
    import org.springframework.cloud.client.discovery.DiscoveryClient;
    import org.springframework.core.env.Environment;
    import org.springframework.stereotype.Component;

    @Component
    public class DiscoveryConfigurationCheck {

        private final DiscoveryClient discoveryClient;
        private final Environment environment;

        public DiscoveryConfigurationCheck(
                DiscoveryClient discoveryClient,
                Environment environment) {
            this.discoveryClient = discoveryClient;
            this.environment = environment;
        }

        public void logInventoryInstances() {
            String[] profiles = environment.getActiveProfiles();

            List<ServiceInstance> instances =
                    discoveryClient.getInstances("inventory-service");

            System.out.println("Active profiles: "
                    + String.join(",", profiles));

            for (ServiceInstance instance : instances) {
                System.out.println(
                        instance.getServiceId() + " -> " + instance.getUri()
                );
            }
        }
    }

Trong dự án thực tế, dùng logger thay cho System.out và tránh ghi thông tin nhạy cảm. Nếu danh sách rỗng, kiểm tra SimpleDiscoveryClient có thực sự được sử dụng hay không, service ID có khớp chính xác không và file profile đã được nạp chưa.

Có thể kiểm tra thêm bằng Actuator env hoặc configprops trong môi trường phát triển được bảo vệ. Không expose các endpoint này ra mạng công khai chỉ để chẩn đoán cấu hình.

## 13. Kết hợp DiscoveryClient và LoadBalancer

DiscoveryClient chỉ trả về danh sách ServiceInstance. Nếu ứng dụng cần gọi dịch vụ, có thể dùng Spring Cloud LoadBalancer để chọn instance từ danh sách đó.

Ví dụ với RestTemplate:

    @Configuration
    public class ClientConfiguration {

        @Bean
        @LoadBalanced
        RestTemplate restTemplate() {
            return new RestTemplate();
        }
    }

Gọi dịch vụ bằng service ID:

    restTemplate.getForObject(
            "http://inventory-service/api/items/42",
            Item.class
    );

LoadBalancer sử dụng DiscoveryClient để lấy danh sách instance của inventory-service rồi chọn một instance theo chính sách đang cấu hình. Khi profile thay đổi, URI mà DiscoveryClient trả về cũng thay đổi theo cấu hình được nạp.

Cần nhớ SimpleDiscoveryClient không kiểm tra endpoint có thật sự hoạt động hay không. LoadBalancer có thể chọn một URI đã lỗi thời nếu cấu hình tĩnh chưa được cập nhật. Ứng dụng vẫn cần timeout, xử lý lỗi và quy trình cập nhật cấu hình khi địa chỉ thay đổi.

## 14. Quy trình kiểm thử tách biệt môi trường

Có thể kiểm tra cấu hình profile theo các bước:

1. Khởi động inventory-service trên hai port local đã khai báo trong application-local.yml.
2. Chạy order-service với profile local.
3. Gọi getInstances("inventory-service") và xác nhận danh sách chỉ chứa hai URI local.
4. Dừng các service local, khởi động bộ service trong Docker network.
5. Chạy order-service với profile docker.
6. Xác nhận danh sách trả về dùng DNS service name và port nội bộ Docker.
7. Chạy thử profile prod trong môi trường staging tương đương, xác minh hostname, TLS và network policy trước khi phát hành.
8. Khởi động lại order-service với từng profile để xác nhận không có URI của môi trường trước bị giữ lại.

Nên ghi lại profile hoạt động, service ID và URI được trả về trong mỗi lần kiểm thử. Dữ liệu này giúp phát hiện lỗi cấu hình nhầm môi trường trước khi request thực tế đi tới endpoint.

## 15. Khi nào nên dùng cấu hình tĩnh theo profile?

Cách làm này phù hợp khi:

- Số lượng service và instance nhỏ, ít thay đổi.
- Mỗi môi trường có danh sách endpoint đã biết trước.
- Địa chỉ được quản lý cùng cấu hình triển khai.
- Cần demo hoặc kiểm thử service discovery mà không dựng Eureka hay Consul.
- Có quy trình phát hành để cập nhật danh sách URI khi topology thay đổi.

Không nên dựa vào danh sách tĩnh khi ứng dụng tự động scale, instance thường xuyên được thay thế hoặc cần health check và đăng ký động. Trong những trường hợp đó, Eureka, Consul hoặc service discovery của nền tảng triển khai giúp duy trì registry phù hợp với topology đang chạy.

Tách profile không phải là cơ chế bảo mật mạng. Endpoint trong application-prod.yml vẫn phải được bảo vệ bằng TLS, firewall, network policy và xác thực ở tầng ứng dụng khi cần.

## 16. Kết luận

SimpleDiscoveryClient cho phép khai báo danh sách instance bằng spring.cloud.discovery.client.simple.instances. Spring Boot Profiles giúp chọn đúng danh sách URI cho local, test, Docker hoặc production mà không phải thay đổi mã nguồn. Hãy đặt cấu hình chung trong application.yml, đặt URI theo môi trường trong application-{profile}.yml và kích hoạt profile rõ ràng qua command line hoặc environment variable.

Khi ghi đè cấu hình, nhớ rằng danh sách instance của cùng một service bị thay thế toàn bộ, không được cộng dồn giữa các profile. Cuối cùng, xác minh profile đang hoạt động và kết quả getInstances() trước khi cho phép consumer gọi dịch vụ. Với topology thường xuyên thay đổi, nên chuyển sang registry động thay vì tiếp tục duy trì danh sách tĩnh thủ công.

## Tài liệu tham khảo

- [Spring Cloud Commons — SimpleDiscoveryClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Properties and Configuration](https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html)

