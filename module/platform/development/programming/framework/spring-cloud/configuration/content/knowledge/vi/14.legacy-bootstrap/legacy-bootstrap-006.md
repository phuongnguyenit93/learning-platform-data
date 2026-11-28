# Vòng phụ thuộc giữa Config Server, Discovery Server và ứng dụng

Trong kiến trúc Spring Cloud dùng cơ chế bootstrap truyền thống, ứng dụng có thể tìm Config Server thông qua service discovery thay vì gọi một URL cố định. Cách này hữu ích khi địa chỉ Config Server thay đổi hoặc có nhiều instance, nhưng nó tạo thêm một phụ thuộc ở giai đoạn khởi động: Config Client phải liên hệ Discovery Server trước khi lấy được cấu hình tập trung.

Nếu chính Discovery Server cũng cần Config Server để khởi động, trong khi Config Server lại cần Discovery Server để đăng ký hoặc tìm dịch vụ, hệ thống có thể rơi vào vòng phụ thuộc. Không thành phần nào có đủ thông tin để bắt đầu trước, hoặc một thành phần khởi động được nhưng không thể trở nên sẵn sàng.

Bài học này phân tích quan hệ khởi động giữa Config Server, Discovery Server và các ứng dụng trong mô hình legacy bootstrap. Bạn sẽ nhận diện điểm tạo vòng, phân biệt phụ thuộc khởi động với đăng ký dịch vụ sau khởi động, thiết kế cấu hình nền tối thiểu cho các thành phần hạ tầng và tổ chức thứ tự triển khai để phá vòng một cách có chủ đích.

Sau bài học, bạn có thể:

- Mô tả cách Config Client dùng DiscoveryClient để tìm Config Server trong bootstrap context.
- Giải thích chuỗi phụ thuộc giữa Discovery Server, Config Server và ứng dụng.
- Nhận diện vòng phụ thuộc khi một thành phần hạ tầng cần chính dịch vụ mà nó phải khởi tạo.
- Phân biệt cấu hình bootstrap cục bộ với cấu hình nghiệp vụ lấy từ xa.
- Thiết kế thứ tự khởi động và readiness cho Discovery Server, Config Server và client.
- Chọn giữa discovery-first lookup và địa chỉ Config Server tĩnh cho từng thành phần.
- Chẩn đoán lỗi khởi động, đăng ký muộn và lookup không tìm thấy Config Server.

## 1. Ba thành phần và trách nhiệm của chúng

Một hệ thống thường có ba vai trò:

**Discovery Server** duy trì registry chứa thông tin các dịch vụ đã đăng ký, chẳng hạn service ID, hostname, port, trạng thái và metadata của instance. Ví dụ phổ biến là Eureka Server hoặc một dịch vụ registry tương đương.

**Config Server** đọc cấu hình từ Git hoặc backend khác, sau đó cung cấp qua HTTP cho Config Client. Nó có thể tự đăng ký vào Discovery Server để các client tìm được bằng service ID như <code>configserver</code>.

**Ứng dụng Config Client** là dịch vụ Spring Boot cần lấy cấu hình tập trung khi khởi động. Trong chế độ discovery-first, client hỏi Discovery Server để tìm địa chỉ Config Server rồi mới gửi request lấy cấu hình.

Sơ đồ quan hệ thông thường:

~~~mermaid
flowchart TD
    D["Discovery Server"] -->|"Registry / service lookup"| C["Config Server"]
    C -->|"Đăng ký service ID configserver"| D
    A["Ứng dụng Config Client"] -->|"Tìm service ID configserver"| D
    A -->|"Lấy application / profile / label"| C
    C --> G["Git hoặc config backend"]
~~~

Mũi tên giữa Config Server và Discovery Server trong sơ đồ thể hiện việc Config Server đăng ký hoặc tương tác với registry. Mũi tên từ ứng dụng tới Discovery Server thể hiện bước tìm vị trí Config Server. Sau đó client mới gọi Config Server để lấy property source.

Hai bước của client là độc lập:

1. Tìm địa chỉ server bằng discovery.
2. Lấy nội dung cấu hình bằng Config Client.

Nếu bước thứ nhất thất bại, client chưa thể gửi request cấu hình tới Config Server. Nếu bước thứ hai thất bại, client đã tìm được server nhưng server không thể cung cấp cấu hình do lỗi Git, xác thực, label hoặc backend.

## 2. Discovery-first lookup trong legacy bootstrap

Trong cơ chế bootstrap truyền thống, Spring Cloud tạo bootstrap context trước application context chính. Config Client có thể dùng DiscoveryClient trong giai đoạn này để tìm Config Server.

Các thuộc tính thường gặp trong <code>bootstrap.yml</code> của ứng dụng client:

~~~yaml
spring:
  application:
    name: orders-service
  cloud:
    config:
      discovery:
        enabled: true
        service-id: configserver
      fail-fast: true

eureka:
  client:
    service-url:
      defaultZone: http://discovery-server:8761/eureka/
~~~

Ý nghĩa:

- <code>spring.application.name</code> là tên dịch vụ cần lấy cấu hình.
- <code>spring.cloud.config.discovery.enabled=true</code> bật discovery-first lookup cho Config Server.
- <code>spring.cloud.config.discovery.service-id</code> là service ID mà client tìm trong registry; mặc định phổ biến là <code>configserver</code>.
- <code>eureka.client.service-url.defaultZone</code> cho Eureka client biết địa chỉ Discovery Server.
- <code>spring.cloud.config.fail-fast=true</code> yêu cầu quá trình bootstrap thất bại nếu không lấy được cấu hình từ xa.

Client cần có cả Config Client và discovery client phù hợp, ví dụ Spring Cloud Config Client cùng Eureka Client khi dùng Eureka. Bootstrap context cũng phải được bật theo phiên bản Spring Cloud của dự án, thường bằng starter bootstrap ở những phiên bản không bật mặc định.

Sau khi DiscoveryClient tìm được instance có service ID <code>configserver</code>, Config Client dùng địa chỉ instance đó để gọi endpoint cấu hình. Request vẫn được xác định bằng application, profile và label, chẳng hạn:

~~~http
GET /orders-service/prod/release-2026.11
~~~

Discovery Server chỉ giúp tìm vị trí Config Server. Nó không lưu property source và không thay thế Git backend.

### Địa chỉ cố định và discovery-first

Nếu không bật discovery-first, client có thể dùng URL cố định:

~~~yaml
spring:
  cloud:
    config:
      uri: http://config-server:8888
      fail-fast: true
~~~

Với địa chỉ tĩnh, client không cần truy vấn Discovery Server để tìm Config Server. Đổi lại, địa chỉ hoặc DNS của Config Server phải được biết trước và duy trì ổn định.

Trong discovery-first, client cần địa chỉ Discovery Server trước; Config Server được tìm bằng service ID. Cách này linh hoạt khi instance thay đổi nhưng làm tăng một phụ thuộc ở giai đoạn bootstrap.

## 3. Phụ thuộc khởi động khác với phụ thuộc lúc vận hành

Không phải mọi quan hệ giữa các dịch vụ đều tạo vòng khởi động. Cần xác định một thành phần có cần dịch vụ khác **trước khi nó có thể khởi động**, hay chỉ cần dịch vụ đó sau khi tiến trình đã chạy.

Ví dụ:

- Config Server có thể cần Discovery Server để đăng ký instance. Nếu registry chưa sẵn sàng, đăng ký có thể thất bại hoặc được thử lại tùy discovery client và cấu hình.
- Config Client dùng discovery-first cần registry trả lời lookup trước khi có thể tìm Config Server.
- Discovery Server có thể chạy độc lập bằng cấu hình cục bộ và không cần Config Server.
- Discovery Server có thể được thiết kế để lấy cấu hình từ Config Server. Khi đó nó có một phụ thuộc khởi động tới Config Server.

Một quan hệ đăng ký dịch vụ sau khi tiến trình đã khởi động không nhất thiết chặn tiến trình. Ngược lại, nếu bootstrap bắt buộc phải gọi một dịch vụ khác để lấy thuộc tính cần thiết trước khi tạo application context, đó là phụ thuộc khởi động thực sự.

Cần kiểm tra log và readiness của từng thành phần để xác định điểm chờ. Đừng chỉ nhìn sơ đồ kiến trúc rồi kết luận hai dịch vụ có vòng phụ thuộc.

## 4. Vòng phụ thuộc hình thành như thế nào?

Một vòng thường xuất hiện khi Discovery Server và Config Server cùng cần nhau ở giai đoạn bootstrap.

### Trường hợp A: Discovery Server tìm Config Server bằng chính Discovery Server

Giả sử Discovery Server được cấu hình như một Config Client và dùng discovery-first:

1. Discovery Server bắt đầu bootstrap.
2. Nó cần lấy cấu hình từ Config Server.
3. Để tìm Config Server, nó gọi Discovery Server.
4. Nhưng tiến trình Discovery Server hiện tại chưa khởi động xong và chưa thể cung cấp registry.
5. Bootstrap không hoàn tất, nên Discovery Server không sẵn sàng.
6. Config Server hoặc các client khác cũng không tìm được Discovery Server.

Đây là vòng tự tham chiếu rõ ràng: registry phải chạy để tìm Config Server, nhưng registry lại cần lookup để có thể chạy.

### Trường hợp B: Config Server cần Discovery Server để tìm nguồn cấu hình khởi động

Nếu Config Server được cấu hình như một Config Client, dùng discovery-first để tìm một Config Server khác nhằm lấy cấu hình backend, đồng thời Discovery Server cũng cần Config Server đầu tiên để lấy cấu hình, hai thành phần có thể chờ nhau.

Ví dụ:

~~~mermaid
flowchart TD
    D["Discovery Server khởi động"] -->|"Cần cấu hình từ xa"| C["Config Server"]
    C -->|"Cần registry để tìm dependency hoặc đăng ký trước khi sẵn sàng"| D
    D --> X["Không thể hoàn tất bootstrap"]
    C --> Y["Không thể hoàn tất bootstrap"]
~~~

Một Config Server không nên cần chính dịch vụ discovery mà nó phải đăng ký vào để tìm chính nó hoặc tìm một nguồn cấu hình phụ thuộc ngược lại. Hãy tách cấu hình nền tảng của Config Server khỏi cấu hình mà nó phân phối cho các ứng dụng.

### Trường hợp C: ứng dụng bắt đầu trước hạ tầng

Ứng dụng dùng discovery-first có thể khởi động trước khi Discovery Server và Config Server sẵn sàng:

1. Client bootstrap và hỏi Discovery Server.
2. Registry chưa có endpoint hoặc chưa có instance <code>configserver</code>.
3. Client không tìm được Config Server.
4. Với fail-fast, ứng dụng dừng khởi động.

Đây là lỗi thứ tự triển khai hoặc readiness, không nhất thiết là vòng phụ thuộc giữa hai thành phần hạ tầng. Nếu retry có giới hạn được cấu hình, client có thể thử lại trong lúc hạ tầng hoàn tất khởi động.

## 5. Vì sao bootstrap context làm vòng phụ thuộc khó xử lý?

Bootstrap tồn tại để lấy cấu hình từ xa trước khi application context chính được tạo. Vì thế, các thuộc tính cần thiết để kết nối Config Server phải có sẵn trong bootstrap context hoặc trong nguồn cấu hình được đọc sớm.

Một chuỗi phụ thuộc có thể xảy ra:

~~~text
Bootstrap của ứng dụng
    -> DiscoveryClient cần địa chỉ Discovery Server
        -> Discovery Server cần cấu hình để khởi động
            -> Config Client trong Discovery Server cần Config Server
                -> Discovery-first lookup cần Discovery Server
~~~

Nếu mọi địa chỉ, credential và thông tin cần thiết đều nằm trong Config Server, không còn nguồn gốc độc lập để khởi động hạ tầng.

Cách thiết kế an toàn là tạo một **bootstrap root**: một tập hợp cấu hình nhỏ có sẵn trước khi gọi Config Server. Nó thường gồm:

- Địa chỉ Discovery Server hoặc Config Server gốc.
- Cổng và hostname cần để tiến trình lắng nghe.
- Cấu hình kết nối tối thiểu của registry.
- Danh tính và truststore cần để kết nối.
- Cấu hình Git backend và secret cần thiết cho Config Server.
- Các tùy chọn để không phụ thuộc vào dịch vụ mà chính tiến trình đang khởi tạo.

Bootstrap root có thể nằm trong <code>application.yml</code> cục bộ, <code>bootstrap.yml</code>, biến môi trường, tham số khởi chạy hoặc secret mount của nền tảng. Chỉ giữ các giá trị cần thiết để hạ tầng tự khởi động; cấu hình nghiệp vụ và mặc định dùng chung vẫn có thể lấy từ Config Server sau đó.

## 6. Cách phá vòng: để Discovery Server khởi động độc lập

Với hệ thống mà Discovery Server là gốc của service discovery, một cách triển khai phổ biến là không bắt Discovery Server phụ thuộc vào Config Server khi bootstrap.

Discovery Server có thể dùng cấu hình cục bộ tối thiểu:

~~~yaml
# application.yml của Discovery Server
server:
  port: 8761

spring:
  application:
    name: discovery-server

eureka:
  client:
    register-with-eureka: false
    fetch-registry: false
    service-url:
      defaultZone: http://localhost:8761/eureka/
~~~

Lớp ứng dụng bật Eureka Server:

~~~java
@SpringBootApplication
@EnableEurekaServer
public class DiscoveryServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiscoveryServerApplication.class, args);
    }
}
~~~

Với một registry server độc lập, không cần đăng ký chính nó như một Eureka client và không cần fetch registry. Trong cụm nhiều node Eureka peer-aware, cấu hình peer replication sẽ khác; các node cần biết địa chỉ peer tĩnh hoặc từ hạ tầng để hình thành cluster. Không áp dụng cấu hình standalone này một cách máy móc cho cụm nhiều node.

Sau khi Discovery Server khởi động và readiness thành công, Config Server mới kết nối và đăng ký với registry. Các ứng dụng có thể dùng discovery-first để tìm Config Server.

Cách này phá vòng bằng cách bảo đảm Discovery Server không cần tìm Config Server để có thể cung cấp dịch vụ discovery.

## 7. Cấu hình nền cho Config Server

Config Server cần khởi động được ngay cả khi Discovery Server chưa sẵn sàng. Các thông tin thiết yếu để đọc Git backend nên được cấp qua cấu hình cục bộ hoặc biến môi trường.

Ví dụ:

~~~yaml
# application.yml của Config Server
server:
  port: 8888

spring:
  application:
    name: configserver
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          default-label: main

eureka:
  client:
    service-url:
      defaultZone: http://discovery-server:8761/eureka/
~~~

Lớp ứng dụng bật Config Server:

~~~java
@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
~~~

Các điểm cần chú ý:

- <code>spring.application.name: configserver</code> tạo service ID mà client sẽ tìm theo quy ước đã chọn.
- Git URI và credential cần có sẵn để Config Server đọc repository.
- Discovery Server URL phải được cung cấp tĩnh trong cấu hình nền của Config Server.
- Config Server không dùng discovery-first để tìm chính nó.
- Nếu Discovery Server chưa sẵn sàng, cần xác định việc đăng ký sẽ retry, chờ readiness hay được điều phối bằng thứ tự triển khai.
- Config Server phải có health/readiness thể hiện khả năng đọc backend cấu hình, không chỉ trạng thái tiến trình.

Nếu Git repository private, cấp credential bằng secret manager hoặc biến môi trường của tiến trình Config Server. Không đưa token vào Git repository cấu hình mà Config Server đang đọc.

## 8. Cấu hình ứng dụng dùng discovery-first

Khi Discovery Server và Config Server đã sẵn sàng, các ứng dụng nghiệp vụ có thể dùng discovery-first lookup trong <code>bootstrap.yml</code>:

~~~yaml
spring:
  application:
    name: orders-service
  cloud:
    config:
      discovery:
        enabled: true
        service-id: configserver
      fail-fast: true
      label: release-2026.11

eureka:
  client:
    service-url:
      defaultZone: http://discovery-server:8761/eureka/
~~~

Ứng dụng cần các dependency phù hợp với phiên bản Spring Cloud, ví dụ:

~~~groovy
dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-config")
    implementation("org.springframework.cloud:spring-cloud-starter-netflix-eureka-client")
    implementation("org.springframework.cloud:spring-cloud-starter-bootstrap")
}
~~~

Danh sách dependency chỉ là ví dụ cho một dự án dùng Eureka và legacy bootstrap. Quản lý phiên bản bằng Spring Cloud BOM tương thích với Spring Boot đang sử dụng. Ở các phiên bản cũ hơn, bootstrap có thể được bật theo cách khác; ở các phiên bản mới hơn, cần bật rõ nếu tiếp tục dùng cơ chế legacy.

Luồng khởi động của client:

1. Đọc cấu hình bootstrap cục bộ.
2. Khởi tạo DiscoveryClient với địa chỉ registry đã biết.
3. Tìm service ID <code>configserver</code>.
4. Chọn instance Config Server theo cơ chế discovery/load balancing của phiên bản.
5. Gọi Config Server với application, profile và label.
6. Nạp property source từ xa.
7. Khởi tạo application context chính và các bean.

Nếu lookup discovery thất bại, kiểm tra registry trước. Nếu lookup thành công nhưng request Config Server thất bại, kiểm tra Config Server, Git backend và bảo mật.

## 9. Thứ tự triển khai an toàn

Với mô hình Discovery Server là gốc, có thể triển khai theo trình tự:

~~~mermaid
flowchart TD
    A["1. Khởi động Discovery Server bằng cấu hình cục bộ"] --> B["2. Kiểm tra health và readiness của registry"]
    B --> C["3. Khởi động Config Server bằng bootstrap root tĩnh"]
    C --> D["4. Xác nhận Config Server đọc được Git"]
    D --> E["5. Xác nhận Config Server đã đăng ký trong registry"]
    E --> F["6. Khởi động ứng dụng Config Client"]
    F --> G["7. Client tìm configserver bằng discovery-first"]
    G --> H["8. Client nạp cấu hình và kiểm tra bean"]
~~~

Không chỉ kiểm tra process đã chạy. Cần xác nhận từng điều kiện sẵn sàng:

| Thành phần | Điều kiện sẵn sàng nên kiểm tra |
|---|---|
| Discovery Server | HTTP health thành công, registry endpoint phản hồi, có thể nhận đăng ký |
| Config Server | Endpoint cấu hình phản hồi, Git backend đọc được label kiểm tra |
| Đăng ký Config Server | Service ID và instance metadata xuất hiện trong registry |
| Ứng dụng client | Tìm được instance Config Server, lấy đúng application/profile/label và bind được thuộc tính bắt buộc |

Trong môi trường container hoặc orchestrator, khai báo startup/readiness probe theo điều kiện thực tế. Một container đang chạy không có nghĩa registry đã nhận đăng ký hoặc Config Server đã clone/fetch Git thành công.

## 10. Nếu Discovery Server cũng cần cấu hình tập trung thì sao?

Có thể một tổ chức muốn tất cả ứng dụng, kể cả Discovery Server, lấy cấu hình từ Git qua Config Server. Khi đó phải xác định một nguồn bootstrap độc lập cho Discovery Server.

Có hai hướng phổ biến.

### Hướng A: Discovery Server dùng bootstrap cục bộ

Discovery Server lấy các giá trị cần để chạy registry từ cấu hình cục bộ hoặc môi trường triển khai. Sau khi khởi động, nó có thể nhận cấu hình bổ sung cho các tính năng không thiết yếu, hoặc được quản lý như một thành phần hạ tầng có cấu hình riêng.

Đây là cách đơn giản và ít phụ thuộc nhất. Không phải mọi thuộc tính của Discovery Server đều cần đưa vào Config Server. Các giá trị làm cho registry có thể khởi động nên nằm trong bootstrap root.

### Hướng B: Discovery Server dùng URI Config Server tĩnh

Nếu Discovery Server cần cấu hình tập trung, nó có thể gọi Config Server bằng URL tĩnh được cung cấp từ bootstrap:

~~~yaml
# bootstrap.yml của Discovery Server
spring:
  application:
    name: discovery-server
  cloud:
    config:
      uri: http://config-server:8888
      fail-fast: true
      label: release-2026.11
~~~

Điều kiện quan trọng: Config Server phải khởi động độc lập mà không cần Discovery Server để tìm chính nó hoặc để lấy cấu hình nền thiết yếu. Config Server có thể được triển khai bằng cấu hình cục bộ, Git URI và credential được cấp từ môi trường.

Sau khi Discovery Server khởi động, Config Server có thể đăng ký với registry. Các ứng dụng nghiệp vụ chỉ dùng discovery-first sau khi registry đã sẵn sàng và có instance Config Server.

Cách này thay vòng phụ thuộc bằng một chuỗi có gốc rõ ràng:

~~~text
Config Server (địa chỉ tĩnh, cấu hình nền cục bộ)
    -> Discovery Server (bootstrap dùng URI tĩnh)
        -> Ứng dụng nghiệp vụ (discovery-first)
~~~

Nếu Config Server cũng phải lấy cấu hình bootstrap của chính nó từ một Config Server khác, hãy xác định rõ dịch vụ gốc đó và địa chỉ tĩnh của nó. Không để mọi Config Server đều cần discovery-first từ registry mà chúng cùng phải khởi tạo.

## 11. Vai trò của fail-fast, retry và readiness

<code>fail-fast</code> quyết định client có dừng khởi động khi không lấy được cấu hình từ xa hay không. Trong bootstrap legacy, ví dụ:

~~~yaml
spring:
  cloud:
    config:
      fail-fast: true
~~~

Khi Config Server là nguồn bắt buộc, fail-fast giúp tránh ứng dụng chạy với cấu hình mặc định không phù hợp. Nhưng nếu hạ tầng chưa sẵn sàng, mọi client có thể thất bại cùng lúc.

Retry có thể giúp vượt qua một khoảng trễ ngắn khi Discovery Server vừa khởi động hoặc Config Server chưa kịp đăng ký. Retry nên có giới hạn số lần, khoảng chờ tăng dần và tổng thời gian phù hợp với startup budget. Nó không sửa được vòng phụ thuộc thật sự: nếu A luôn chờ B và B luôn chờ A, thử lại nhiều lần chỉ lặp lại trạng thái chờ.

Readiness cần phản ánh khả năng phục vụ của thành phần:

- Discovery Server sẵn sàng khi registry có thể trả lời lookup và nhận đăng ký.
- Config Server sẵn sàng khi có thể trả cấu hình từ backend được yêu cầu.
- Ứng dụng sẵn sàng khi đã nạp cấu hình bắt buộc và khởi tạo các dependency chính.

Liveness chỉ trả lời tiến trình còn sống hay không. Không dùng liveness thay readiness để quyết định có thể khởi động client phụ thuộc hay chưa.

## 12. Nhiều instance và tính nhất quán của registry

Trong môi trường nhiều instance, có thể xảy ra các tình huống:

- Config Server đã chạy nhưng chưa đăng ký xong.
- Registry đã nhận service ID nhưng instance chưa healthy.
- Một client nhìn thấy instance cũ trong cache.
- Config Server replica có Git ref hoặc cache khác nhau.
- Một số client lookup được server nhưng server trả cấu hình từ label khác.

Cần kiểm tra:

1. Service ID mà Config Server đăng ký có khớp với <code>spring.cloud.config.discovery.service-id</code> của client không.
2. Hostname/IP và port mà registry công bố có thể truy cập từ mạng của client không.
3. Instance metadata, health status và zone/region có phù hợp không.
4. Các Config Server replica dùng cùng repository, credential, encryption key và label policy không.
5. Client có cache discovery hoặc retry theo cách làm chậm nhận biết instance mới không.

Không chỉ dựa vào việc một instance Config Server xuất hiện trên giao diện registry. Hãy thử lookup từ đúng mạng chạy ứng dụng và gọi endpoint cấu hình qua địa chỉ instance được trả về.

## 13. Chẩn đoán theo triệu chứng

| Triệu chứng | Vùng cần kiểm tra trước | Câu hỏi chẩn đoán |
|---|---|---|
| Discovery Server không khởi động | Bootstrap root của registry | Có Config Client trong bootstrap đang tìm Config Server qua chính registry này không? |
| Config Server chạy nhưng không xuất hiện trong registry | Đăng ký service | Eureka URL, network, service name và credential có đúng không? |
| Client không tìm thấy service ID configserver | Discovery lookup | Config Server đã đăng ký chưa, service ID có khớp không? |
| Client tìm thấy Config Server nhưng nhận 404 | Request cấu hình | Application, profile, label và property source có đúng không? |
| Client timeout trước khi gọi Config Server | Discovery Server hoặc network | Discovery endpoint có truy cập được từ bootstrap process không? |
| Config Server không đọc được Git | Git backend | URI, credential, DNS, TLS và label có hợp lệ không? |
| Hạ tầng khởi động được theo thứ tự thủ công nhưng fail khi triển khai đồng thời | Orchestration/readiness | Có phụ thuộc startup chưa được mô tả hoặc health check quá sớm không? |
| Một số instance khởi động được, số khác thất bại | Registry/cache/network | Instance metadata và khả năng truy cập có nhất quán không? |

### Phân biệt ba lỗi thường bị gộp

**Không tìm thấy Discovery Server:** Config Client chưa thể tìm Config Server. Kiểm tra địa chỉ registry và network.

**Không tìm thấy Config Server trong registry:** Discovery Server hoạt động, nhưng Config Server chưa đăng ký hoặc đăng ký sai service ID. Kiểm tra trạng thái Config Server và registry.

**Config Server trả lỗi cấu hình:** client đã tới được server. Kiểm tra application/profile/label, xác thực client, Git backend và nội dung repository.

Phân biệt đúng ba lỗi này giúp không sửa Git khi vấn đề thực tế nằm ở registry hoặc startup order.

## 14. Những cách xử lý không giải quyết được vòng phụ thuộc

Một số thay đổi chỉ che triệu chứng:

- Tăng timeout nhưng không loại bỏ quan hệ A chờ B và B chờ A.
- Retry vô hạn khiến tiến trình treo lâu mà không có điểm phục hồi.
- Đặt optional cho mọi client khiến ứng dụng khởi động thiếu cấu hình bắt buộc.
- Đưa toàn bộ cấu hình vào Config Server trong khi Config Server cần chính các giá trị đó để khởi động.
- Cho Discovery Server dùng discovery-first để tìm Config Server trong khi nó là registry gốc.
- Chỉ kiểm tra process running mà không kiểm tra readiness và đăng ký dịch vụ.
- Dùng một URL Config Server tĩnh trong môi trường này và discovery-first trong môi trường khác nhưng không ghi lại chính sách.

Cách sửa bền vững là xác định thành phần gốc, cung cấp cấu hình nền độc lập cho nó và làm cho các phụ thuộc tiếp theo có thứ tự rõ ràng.

## 15. Checklist thiết kế và vận hành

- [ ] Đã vẽ dependency graph ở giai đoạn bootstrap, không chỉ sơ đồ request runtime.
- [ ] Discovery Server có thể khởi động từ cấu hình nền độc lập.
- [ ] Config Server có Git URI, credential, port và security bootstrap trước khi cần registry.
- [ ] Config Server không dùng discovery-first để tìm chính nó.
- [ ] Config Server đăng ký với đúng service ID mà client tìm kiếm.
- [ ] Client chỉ dùng discovery-first sau khi Discovery Server sẵn sàng.
- [ ] Địa chỉ Discovery Server được cấp tĩnh cho bootstrap context.
- [ ] Đã xác nhận starter bootstrap và discovery client tương thích với phiên bản Spring Cloud.
- [ ] Fail-fast và retry có giới hạn, phù hợp với startup budget.
- [ ] Readiness kiểm tra khả năng lookup, đăng ký và đọc cấu hình thực tế.
- [ ] Nhiều Config Server replica có repository, label và security configuration nhất quán.
- [ ] Không dùng optional hoặc fallback để che thiếu cấu hình bắt buộc.
- [ ] Đã thử nghiệm cold start, restart riêng từng thành phần và triển khai đồng thời.
- [ ] Log có request ID, service ID và trạng thái từng bước nhưng không tiết lộ credential.

Vòng phụ thuộc giữa Config Server, Discovery Server và ứng dụng thường xuất hiện khi mọi thành phần đều cần cấu hình hoặc discovery từ một dịch vụ chưa thể khởi động nếu thiếu chính nó. Trong legacy bootstrap, hãy giữ một bootstrap root độc lập cho các thành phần hạ tầng, khởi động registry trước khi client cần discovery-first và để Config Server có thể chạy bằng địa chỉ cùng cấu hình backend đã biết. Khi startup dependency, readiness và thứ tự triển khai được xác định rõ, các ứng dụng có thể tìm Config Server qua registry mà không làm hạ tầng mắc kẹt trong vòng chờ lẫn nhau.

