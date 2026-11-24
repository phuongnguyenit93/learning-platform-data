# Thiết lập Spring Boot Actuator cho các thí nghiệm khám phá

Trong các thí nghiệm Spring Cloud Service Discovery, ứng dụng cần cung cấp tín hiệu rõ ràng về trạng thái hoạt động để registry hoặc thành phần điều phối có thể đánh giá instance. Spring Boot Actuator cung cấp các endpoint vận hành, trong đó endpoint health thường được dùng để kiểm tra ứng dụng còn sẵn sàng phục vụ hay không. Khi kết hợp với Consul, Eureka hoặc discovery client khác, Actuator giúp quan sát trạng thái service và kiểm tra cách trạng thái đó ảnh hưởng đến quá trình khám phá instance.

Actuator không thay thế DiscoveryClient, ServiceRegistry hay registry server. Nó cung cấp thông tin sức khỏe và vận hành; cơ chế discovery hoặc health check của registry quyết định cách sử dụng thông tin đó.

## 1. Spring Boot Actuator là gì?

Spring Boot Actuator bổ sung các endpoint để quan sát và quản lý ứng dụng đang chạy. Các endpoint có thể cung cấp thông tin như:

- **health:** trạng thái tổng thể và trạng thái của các health indicator.
- **info:** thông tin ứng dụng do cấu hình hoặc các InfoContributor cung cấp.
- **metrics:** số liệu đo lường do Micrometer và các thành phần tích hợp cung cấp.
- **env, configprops, beans, loggers:** thông tin cấu hình và runtime phục vụ chẩn đoán.

Không phải endpoint nào cũng được công khai qua HTTP theo mặc định. Trong cấu hình mặc định, health là endpoint web được expose; các endpoint khác cần được expose rõ ràng. Đây là cơ chế bảo vệ quan trọng vì nhiều endpoint có thể tiết lộ cấu hình, thông tin nội bộ hoặc dữ liệu nhạy cảm.

Trong phạm vi service discovery, endpoint thường cần kiểm tra đầu tiên là:

    GET /actuator/health

Nếu ứng dụng đang hoạt động bình thường và các health indicator liên quan đều đạt, endpoint thường trả trạng thái UP cùng HTTP 200. Khi trạng thái sức khỏe không đạt, endpoint có thể trả HTTP 503. Mã HTTP cụ thể còn phụ thuộc status mapping và cấu hình health endpoint.

## 2. Thêm dependency Actuator

Actuator được đóng gói trong starter spring-boot-starter-actuator. Dự án nên dùng Spring Boot dependency management hoặc Spring Boot parent/plugin để quản lý phiên bản starter đồng bộ với phiên bản Spring Boot đang sử dụng.

**Maven**

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

**Gradle**

    dependencies {
        implementation 'org.springframework.boot:spring-boot-starter-actuator'
    }

Ứng dụng web thường đã có spring-boot-starter-web hoặc một web stack tương ứng. Starter Actuator cung cấp các endpoint và infrastructure health; web stack cung cấp khả năng truy cập endpoint qua HTTP.

Với ứng dụng thử nghiệm discovery, dependency discovery được thêm riêng theo registry đang dùng. Ví dụ:

- Consul: spring-cloud-starter-consul-discovery.
- Eureka client: spring-cloud-starter-netflix-eureka-client.

Cần dùng Spring Cloud release train tương thích với phiên bản Spring Boot của dự án. Việc thêm Actuator không tự đăng ký service vào Consul hoặc Eureka; ứng dụng vẫn cần dependency và cấu hình discovery tương ứng.

## 3. Cấu hình endpoint health và info

Spring Boot mặc định dùng base path /actuator cho các endpoint web. Vì vậy health endpoint mặc định là /actuator/health.

Có thể khai báo rõ các endpoint cần dùng trong file application.yml:

    spring:
      application:
        name: discovery-lab-service

    server:
      port: 8080

    management:
      endpoints:
        web:
          base-path: /actuator
          exposure:
            include: health,info
      endpoint:
        health:
          show-details: never
          probes:
            enabled: true
      info:
        env:
          enabled: true

    info:
      app:
        name: discovery-lab-service
        purpose: service-discovery-lab

Ý nghĩa các cấu hình:

| Thuộc tính | Tác dụng |
|---|---|
| spring.application.name | Tên logic của ứng dụng; thường được dùng làm service ID khi đăng ký discovery |
| server.port | Cổng HTTP chính của ứng dụng |
| management.endpoints.web.base-path | Prefix của các endpoint Actuator; mặc định là /actuator |
| management.endpoints.web.exposure.include | Danh sách endpoint được expose qua HTTP |
| management.endpoint.health.show-details | Điều khiển việc hiển thị chi tiết sức khỏe; never tránh công khai chi tiết |
| management.endpoint.health.probes.enabled | Bật health group cho liveness và readiness |
| management.info.env.enabled | Bật InfoContributor đọc các thuộc tính info.* từ Environment |

Ở ví dụ trên, ứng dụng expose health và info. Endpoint metrics, env, configprops, beans không được expose chỉ vì Actuator đã có mặt. Chỉ thêm endpoint khi có nhu cầu cụ thể và đã thiết lập quyền truy cập phù hợp.

Nếu không cần endpoint info, có thể bỏ info khỏi exposure.include và không khai báo nhóm info.*. Với thí nghiệm service discovery, endpoint health thường là phần bắt buộc; info hữu ích để nhận biết instance và phiên bản ứng dụng khi quan sát registry.

## 4. Phân biệt health, liveness và readiness

/actuator/health biểu diễn trạng thái tổng thể được tổng hợp từ các health indicator. Trong môi trường phân tán, chỉ một trạng thái tổng thể đôi khi chưa đủ để trả lời hai câu hỏi khác nhau:

- **Liveness:** tiến trình ứng dụng còn sống và có thể tiếp tục chạy không?
- **Readiness:** ứng dụng đã sẵn sàng nhận request từ service khác chưa?

Spring Boot cung cấp các health group cho hai trạng thái này. Khi bật:

    management:
      endpoint:
        health:
          probes:
            enabled: true

các endpoint sau có thể được sử dụng:

    /actuator/health/liveness
    /actuator/health/readiness

Liveness giúp nền tảng chạy ứng dụng phát hiện tiến trình bị kẹt hoặc không còn hoạt động đúng. Readiness phản ánh khả năng nhận traffic; ví dụ ứng dụng có thể chưa sẵn sàng trong giai đoạn khởi tạo hoặc khi một dependency bắt buộc chưa kết nối được.

| Tín hiệu | Câu hỏi cần trả lời | Cách sử dụng thường gặp |
|---|---|---|
| health | Trạng thái sức khỏe tổng thể hiện tại là gì? | Quan sát ứng dụng, health check của registry |
| liveness | Có cần khởi động lại tiến trình không? | Liveness probe của nền tảng |
| readiness | Có nên gửi request mới tới instance này không? | Readiness probe, kiểm soát nhận traffic |

Không nên đưa mọi dependency bên ngoài vào liveness. Nếu database tạm thời mất kết nối và liveness cũng chuyển sang DOWN, nền tảng có thể liên tục khởi động lại một tiến trình vốn vẫn khỏe, khiến sự cố lan rộng. Dependency bắt buộc để phục vụ request thường phù hợp hơn với readiness hoặc health group được thiết kế riêng.

Với các thí nghiệm discovery, có thể gọi cả ba endpoint để quan sát sự khác nhau. Nếu dùng readiness làm tiêu chí cho health check registry, hãy xác nhận registry được cấu hình gọi đúng path và mã HTTP phản ánh chính sách sẵn sàng mà hệ thống mong muốn.

## 5. Health indicator và trạng thái ứng dụng

Actuator tổng hợp kết quả từ các HealthIndicator. Spring Boot có sẵn một số indicator cho những dependency được hỗ trợ trên classpath, chẳng hạn datasource hoặc một số thành phần tích hợp. Ứng dụng cũng có thể định nghĩa indicator riêng cho dependency hoặc điều kiện nghiệp vụ cần theo dõi.

Ví dụ một custom health indicator đơn giản:

    import org.springframework.boot.actuate.health.Health;
    import org.springframework.boot.actuate.health.HealthIndicator;
    import org.springframework.stereotype.Component;

    @Component
    public class CatalogDependencyHealthIndicator implements HealthIndicator {

        @Override
        public Health health() {
            boolean reachable = checkCatalogDependency();

            if (reachable) {
                return Health.up().build();
            }

            return Health.down()
                    .withDetail("dependency", "catalog")
                    .build();
        }

        private boolean checkCatalogDependency() {
            // Thay bằng phép kiểm tra có timeout tới dependency thực tế.
            return true;
        }
    }

Đoạn mã trên minh họa cấu trúc; trong ứng dụng thực tế, checkCatalogDependency() cần kiểm tra dependency thật và có timeout hữu hạn. Không nên thực hiện truy vấn nặng hoặc gọi nhiều dịch vụ theo chuỗi ở mỗi lần health check. Endpoint health có thể bị gọi định kỳ bởi Consul hoặc nền tảng triển khai, vì vậy indicator chậm sẽ tạo thêm tải và có thể khiến instance bị đánh dấu không khỏe do chính việc kiểm tra.

Cần quyết định indicator thuộc nhóm nào. Dependency thiết yếu để nhận request có thể ảnh hưởng readiness. Một dependency tùy chọn hoặc chức năng phụ có thể chỉ nên xuất hiện trong health tổng thể hoặc metric riêng, tránh loại bỏ instance khỏi discovery khi chức năng chính vẫn hoạt động.

## 6. Tích hợp Actuator với service discovery

Actuator chỉ cung cấp endpoint. Registry cần được cấu hình để sử dụng endpoint đó.

### Consul

Spring Cloud Consul thường đăng ký HTTP health check trỏ tới /actuator/health. Có thể khai báo rõ cấu hình để thí nghiệm dễ quan sát:

    spring:
      cloud:
        consul:
          host: localhost
          port: 8500
          discovery:
            register: true
            register-health-check: true
            health-check-path: /actuator/health
            health-check-interval: 10s

Consul Agent phải truy cập được địa chỉ và path này từ vị trí mạng của agent. Nếu đổi base path, context path hoặc cổng quản lý, cần cập nhật URL health check tương ứng. Chỉ bật register-health-check không bảo đảm check sẽ passing nếu endpoint chưa được expose hoặc không thể truy cập.

### Eureka

Eureka client có thể sử dụng trạng thái sức khỏe của ứng dụng thông qua health check integration của Spring Cloud Netflix Eureka. Khi muốn client truyền trạng thái health của ứng dụng tới Eureka, cấu hình:

    eureka:
      client:
        healthcheck:
          enabled: true

Đặt cấu hình này trong application.yml hoặc cấu hình ứng dụng tương đương để trạng thái health được khởi tạo đúng trong application context. Hành vi cụ thể còn phụ thuộc phiên bản Spring Cloud Netflix và cách ứng dụng tích hợp Actuator.

### Phân biệt trách nhiệm

| Thành phần | Trách nhiệm |
|---|---|
| Spring Boot Actuator | Cung cấp endpoint health và thông tin vận hành |
| HealthIndicator | Đánh giá một thành phần hoặc dependency |
| Consul Agent / Eureka client integration | Đọc hoặc truyền tín hiệu sức khỏe tới registry |
| DiscoveryClient | Tra cứu danh sách instance theo service ID |
| LoadBalancer | Chọn instance phù hợp để gửi request |

Khi thử nghiệm, cần xác minh từng lớp riêng. Endpoint Actuator trả UP chưa chứng minh instance đã được đăng ký; instance đã đăng ký cũng chưa chứng minh client chỉ nhận các instance khỏe.

## 7. Cổng quản lý và đường dẫn endpoint

Mặc định, Actuator sử dụng cùng cổng với ứng dụng. Có thể cấu hình management server chạy trên cổng riêng:

    server:
      port: 8080

    management:
      server:
        port: 8081
      endpoints:
        web:
          exposure:
            include: health,info

Khi cấu hình như trên, request nghiệp vụ chạy qua cổng 8080, còn endpoint quản lý chạy qua cổng 8081. Cách tách cổng giúp kiểm soát mạng và quyền truy cập tốt hơn, nhưng health check của registry phải gọi đúng cổng quản lý. Nếu Consul Agent vẫn gọi cổng service 8080 với path /actuator/health, check có thể thất bại vì endpoint thực tế đang ở 8081.

Trong các thí nghiệm đầu tiên, nên giữ Actuator trên cùng cổng để giảm số biến cấu hình. Chỉ tách management port khi bài thực hành cần khảo sát riêng về mạng quản lý, firewall hoặc chính sách bảo mật.

Các thuộc tính liên quan cần nhận biết:

- management.server.port: cổng management server.
- management.server.address: địa chỉ bind của management server.
- management.endpoints.web.base-path: prefix endpoint HTTP.
- management.endpoints.web.path-mapping: ánh xạ tên endpoint sang path khác.

Nếu thay đổi một trong các thuộc tính trên, hãy kiểm tra lại URL đầy đủ từ chính máy hoặc container sẽ thực hiện health check.

## 8. Bảo vệ endpoint Actuator

Expose endpoint và cấp quyền truy cập endpoint là hai việc khác nhau. management.endpoints.web.exposure.include quyết định endpoint nào có thể được gọi qua HTTP; Spring Security hoặc cấu hình mạng quyết định ai được phép gọi.

Một số nguyên tắc cơ bản:

1. Chỉ expose endpoint cần thiết. Với bài thực hành discovery, thường chỉ cần health và có thể thêm info.
2. Không expose rộng env, configprops, beans, heapdump hoặc shutdown trên mạng công khai.
3. Giữ management.endpoint.health.show-details ở never hoặc chỉ hiển thị khi người gọi đã được xác thực.
4. Giới hạn management port bằng firewall, network policy hoặc mạng nội bộ.
5. Nếu endpoint yêu cầu xác thực, cấu hình health check của registry phải gửi thông tin xác thực phù hợp; không nhúng secret thật vào repository.
6. Không trả password, token, connection string hoặc dữ liệu cá nhân trong custom health details.

Ví dụ cấu hình tối thiểu cho môi trường thực hành:

    management:
      endpoints:
        web:
          exposure:
            include: health,info
      endpoint:
        health:
          show-details: never

Khi Spring Security có mặt, cần bảo đảm các request từ health checker được cấp quyền truy cập đúng endpoint. Không nên tắt toàn bộ bảo mật chỉ để làm cho health check chuyển sang UP; hãy cấu hình rule hoặc credential dành riêng cho health checker.

## 9. Thực hành xác minh Actuator

Sau khi thêm dependency và cấu hình, khởi động ứng dụng rồi kiểm tra endpoint từ máy có thể truy cập tới ứng dụng.

**Kiểm tra trạng thái tổng thể**

    curl -i http://localhost:8080/actuator/health

Kết quả mong đợi khi ứng dụng khỏe thường có HTTP 200 và body tương tự:

    {
      "status": "UP"
    }

**Kiểm tra liveness và readiness**

    curl -i http://localhost:8080/actuator/health/liveness
    curl -i http://localhost:8080/actuator/health/readiness

Hai endpoint cần được bật bằng management.endpoint.health.probes.enabled. Nếu nhận 404, kiểm tra phiên bản Spring Boot, cấu hình probes và path endpoint.

**Kiểm tra thông tin ứng dụng**

    curl -i http://localhost:8080/actuator/info

Endpoint info chỉ hoạt động qua HTTP khi được expose và có contributor cung cấp dữ liệu. Nếu body rỗng, kiểm tra info.* và cấu hình management.info.env.enabled.

**Kiểm tra từ góc nhìn Consul Agent**

Nếu registry ở container khác, không chỉ gọi endpoint từ máy host. Hãy thử gọi từ chính network namespace hoặc container của Consul Agent tới địa chỉ mà agent sử dụng. Hostname localhost bên trong container chỉ trỏ về container đó, không trỏ tới máy host hay container service khác.

## 10. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| /actuator/health trả 404 | Thiếu Actuator, sai base path hoặc endpoint web chưa được expose | Kiểm tra dependency và management.endpoints.web.base-path |
| /actuator/info trả 404 | Chưa expose info | Thêm info vào management.endpoints.web.exposure.include |
| Health trả 503 | Một health indicator báo DOWN hoặc OUT_OF_SERVICE | Xem log và chi tiết health trong môi trường được bảo vệ |
| Health trả 401 hoặc 403 | Spring Security chặn health checker | Kiểm tra authorization rule và credential |
| Gọi được từ host nhưng registry check thất bại | Registry Agent không truy cập được host/port/path | Kiểm tra DNS, port mapping, firewall và network |
| Instance đăng ký nhưng bị đánh dấu không khỏe | Health check gọi sai endpoint hoặc ứng dụng chưa ready | Kiểm tra URL và trạng thái check ở registry |
| Readiness DOWN nhưng liveness UP | Ứng dụng còn sống nhưng chưa sẵn sàng phục vụ | Kiểm tra dependency bắt buộc và quá trình khởi tạo |
| Endpoint lộ nhiều chi tiết | Health detail hoặc endpoint exposure cấu hình quá rộng | Giới hạn exposure và show-details |

Một số bước chẩn đoán nên thực hiện theo thứ tự: xác nhận dependency, xác nhận path và cổng, gọi endpoint trực tiếp, kiểm tra quyền truy cập, rồi mới kiểm tra cấu hình registry. Cách này giúp phân biệt lỗi của Actuator với lỗi mạng hoặc lỗi tích hợp discovery.

## 11. Kết luận

Spring Boot Actuator cung cấp nền tảng quan sát sức khỏe cho các thí nghiệm Spring Cloud Service Discovery. Để bắt đầu, thêm spring-boot-starter-actuator, expose endpoint health, bật probes khi cần kiểm tra liveness/readiness và giữ thông tin chi tiết ở mức được bảo vệ. Sau đó cấu hình registry gọi đúng endpoint từ vị trí mạng mà registry thực sự sử dụng.

Khi thực hành, hãy quan sát riêng trạng thái của Actuator, trạng thái check trong registry và danh sách instance mà DiscoveryClient trả về. Ba kết quả này liên quan với nhau nhưng thuộc các trách nhiệm khác nhau; kiểm tra từng lớp sẽ giúp xác định chính xác vì sao một instance được hoặc không được chọn để phục vụ request.

## Tài liệu tham khảo

- [Spring Boot Reference — Actuator](https://docs.spring.io/spring-boot/reference/actuator/index.html)
- [Spring Boot Reference — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Reference — Health Information](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health)
- [Spring Cloud Consul — Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Netflix — Eureka Client](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)

