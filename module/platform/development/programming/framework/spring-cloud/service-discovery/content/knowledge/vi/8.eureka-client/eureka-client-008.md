# Đồng bộ trạng thái Actuator với Eureka healthcheck

Một ứng dụng Spring Boot có thể vẫn gửi heartbeat đều đặn đến Eureka dù một dependency quan trọng đã lỗi. Nếu Eureka chỉ dựa vào heartbeat, registry có thể tiếp tục công bố instance ở trạng thái UP và consumer vẫn chọn instance đó để gửi request.

Spring Cloud Netflix Eureka Client có thể đồng bộ trạng thái sức khỏe của ứng dụng với trạng thái instance trong Eureka. Khi bật tích hợp này, Eureka Client sử dụng health handler của Spring Boot Actuator để tổng hợp các health contributor trong application context, chuyển kết quả sang trạng thái mà Eureka hiểu và gửi trạng thái đó cùng quá trình cập nhật instance.

Cơ chế này giúp registry phản ánh tốt hơn khả năng phục vụ của ứng dụng. Để cấu hình đúng, cần phân biệt heartbeat với health check, hiểu cách Actuator tổng hợp trạng thái, đặt property đúng nơi, kiểm soát các HealthIndicator được tham gia và xác minh kết quả từ góc nhìn consumer.

## 1. Vì sao cần đồng bộ Actuator với Eureka?

Eureka dùng heartbeat để biết một client còn duy trì registration hay không. Heartbeat thành công chứng minh client vẫn liên lạc được với Eureka Server; nó không tự chứng minh rằng API của ứng dụng có thể xử lý nghiệp vụ.

Ví dụ, `order-service` có thể đang chạy và gửi heartbeat đều đặn, nhưng kết nối đến database đã hỏng. Nếu Eureka vẫn công bố instance là UP, `payment-service` hoặc consumer khác có thể tiếp tục gửi request đến một instance không thể hoàn thành công việc.

Spring Boot Actuator cung cấp các health indicator để đánh giá ứng dụng và các dependency. Spring Cloud Netflix có thể dùng kết quả đó để cập nhật trạng thái instance trong Eureka.

| Cơ chế | Kiểm tra điều gì? | Kết quả được dùng để |
|---|---|---|
| Eureka heartbeat | Client còn gửi tín hiệu gia hạn lease hay không | Duy trì hoặc hết hạn registration |
| Actuator HealthIndicator | Ứng dụng và các thành phần được kiểm tra có khỏe không | Tính trạng thái sức khỏe tổng thể |
| Eureka health handler | Chuyển trạng thái Actuator sang trạng thái instance của Eureka | Cập nhật trạng thái công bố trong registry |
| Discovery client của consumer | Instance nào đang được công bố và phù hợp để sử dụng | Cung cấp danh sách instance cho việc gọi dịch vụ |

Hai cơ chế heartbeat và health check bổ sung cho nhau. Một ứng dụng có thể gửi heartbeat thành công nhưng health status là DOWN. Ngược lại, một health indicator cục bộ có thể báo UP nhưng client không liên lạc được với Eureka; trong trường hợp đó registry vẫn có thể hết lease sau một khoảng thời gian.

## 2. Phân biệt health endpoint và Eureka health handler

Có hai khái niệm dễ bị nhầm:

**Actuator health endpoint** là HTTP endpoint, thường được truy cập qua đường dẫn `/actuator/health` trong cấu hình Spring Boot mặc định hiện nay. Endpoint này cho operator, hệ thống giám sát hoặc probe được phép biết trạng thái sức khỏe của ứng dụng.

**EurekaHealthCheckHandler** là thành phần phía Eureka Client đọc các health contributor trong application context, tổng hợp trạng thái và chuyển nó thành trạng thái instance của Eureka. Handler được Eureka Client gọi trong quá trình cập nhật thông tin instance.

Điều đó có nghĩa:

- Eureka Server không mặc định gọi HTTP đến `/actuator/health` của từng instance để kiểm tra sức khỏe.
- Eureka Client thực hiện việc tổng hợp health ở phía ứng dụng rồi gửi trạng thái cùng thông tin registration/heartbeat.
- Việc công khai endpoint `/actuator/health` hữu ích cho quan sát và probe, nhưng riêng endpoint này không tự bật đồng bộ trạng thái với Eureka.
- Trường `eureka.instance.healthCheckUrlPath` công bố URL health trong metadata của instance. Trường URL metadata này khác với property bật health handler phía client.

~~~mermaid
flowchart TD
    subgraph APP["Ứng dụng Spring Boot"]
        H1["Database HealthIndicator"]
        H2["Custom HealthIndicator"]
        H3["Các HealthContributor khác"]
        AGG["StatusAggregator"]
        EH["EurekaHealthCheckHandler"]
        EP["HTTP /actuator/health"]
        H1 --> AGG
        H2 --> AGG
        H3 --> AGG
        AGG --> EH
        H1 --> EP
        H2 --> EP
        H3 --> EP
    end

    EH -->|"InstanceStatus"| EC["Eureka Client"]
    EC -->|"Heartbeat / instance update"| ES[("Eureka Server")]
    ES -->|"Registry data"| CON["Consumer"]
~~~

Sơ đồ cho thấy endpoint HTTP và health handler cùng dựa trên health contributor, nhưng có vai trò khác nhau. Không nên hiểu rằng Eureka Server phải gọi endpoint HTTP thì trạng thái mới được đồng bộ.

## 3. Dependency cần có

Ứng dụng provider cần Eureka Client và Spring Boot Actuator. Ví dụ Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Version của các dependency Spring Cloud nên được quản lý bởi Spring Cloud BOM tương thích với Spring Boot của dự án. Không tự ghim một version Eureka Client riêng nếu BOM đã quản lý artifact đó.

Nếu chỉ thêm Eureka Client, ứng dụng có thể đăng ký và gửi heartbeat. Để sử dụng các health indicator của Spring Boot, cần có Actuator và các indicator phù hợp với mục tiêu kiểm tra.

## 4. Bật đồng bộ health status trong application.yml

Ví dụ cấu hình cơ bản:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8082

eureka:
  client:
    serviceUrl:
      defaultZone: http://localhost:8761/eureka/
    healthcheck:
      enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
~~~

Property quan trọng là:

~~~yaml
eureka:
  client:
    healthcheck:
      enabled: true
~~~

Property này bật health check handler tích hợp của Eureka Client. Trong các release train, giá trị mặc định của property có thể khác nhau; tài liệu cấu hình của Spring Cloud Netflix 4.3.3 liệt kê mặc định là `true`. Khai báo rõ property giúp ý định cấu hình dễ đọc và tránh phụ thuộc vào mặc định của phiên bản.

**Đặt property này trong `application.yml` hoặc cấu hình application tương đương. Không đặt nó trong `bootstrap.yml`.** Tài liệu Spring Cloud Netflix cảnh báo việc đặt property ở bootstrap configuration có thể gây side effect, trong đó instance đăng ký với trạng thái UNKNOWN.

Nếu dùng profile, có thể đặt property trong file application profile tương ứng, ví dụ `application-prod.yml`, miễn là nó được nạp trong application configuration đúng thời điểm.

## 5. Actuator tổng hợp trạng thái như thế nào?

Spring Boot biểu diễn kết quả của mỗi health contributor bằng một `Status`. Một số trạng thái thường gặp:

| Actuator Status | Ý nghĩa |
|---|---|
| `UP` | Thành phần được kiểm tra đang hoạt động |
| `DOWN` | Thành phần không đáp ứng |
| `OUT_OF_SERVICE` | Thành phần đang chủ động không phục vụ |
| `UNKNOWN` | Không xác định được tình trạng |

Ứng dụng có thể có nhiều HealthIndicator: database, disk space, broker, custom dependency hoặc thành phần nghiệp vụ. `StatusAggregator` tổng hợp các kết quả này thành một trạng thái chung.

Ví dụ:

| Database | Message broker | Trạng thái tổng hợp có thể gặp |
|---|---|---|
| UP | UP | UP |
| DOWN | UP | DOWN |
| UP | DOWN | DOWN |
| UP | OUT_OF_SERVICE | Phụ thuộc thứ tự ưu tiên status và cấu hình aggregator |

StatusAggregator dùng thứ tự ưu tiên để quyết định trạng thái tổng hợp khi có nhiều kết quả. Nếu ứng dụng bổ sung status tùy chỉnh, cần cấu hình thứ tự ưu tiên và mapping phù hợp; không nên giả định mọi status tự động được Eureka hiểu.

### 5.1. EurekaHealthCheckHandler làm gì?

Khi được bật, Spring Cloud Netflix tạo `EurekaHealthCheckHandler`. Handler thu thập các `HealthContributor` và `ReactiveHealthContributor` trong application context, tổng hợp trạng thái rồi ánh xạ sang `InstanceInfo.InstanceStatus` của Eureka.

Ở mức khái niệm:

1. Đọc các health contributor đã được đăng ký.
2. Thực hiện health check của từng contributor.
3. Thu thập các status trả về.
4. Dùng StatusAggregator để tính status tổng thể.
5. Ánh xạ status tổng thể sang trạng thái instance Eureka.
6. Cung cấp trạng thái cho Eureka Client khi client làm mới thông tin instance.

Implementation cũng tránh đưa Eureka health indicator của chính discovery vào vòng tổng hợp theo cách gây vòng lặp sức khỏe. Nếu health check của Eureka lại phụ thuộc vào trạng thái Eureka do chính nó công bố, ứng dụng có thể rơi vào vòng lặp tự tham chiếu.

### 5.2. Ánh xạ sang trạng thái Eureka

Eureka có vocabulary trạng thái instance riêng như `UP`, `DOWN`, `STARTING`, `OUT_OF_SERVICE` và `UNKNOWN`.

Ánh xạ mặc định phụ thuộc phiên bản Spring Cloud Netflix và cấu hình mapping của release train. Ví dụ, các implementation phổ biến ánh xạ `UP` sang `UP`, `DOWN` sang `DOWN` và `UNKNOWN` sang `UNKNOWN`; `OUT_OF_SERVICE` có thể được chuyển thành trạng thái không nhận traffic như `DOWN` tùy implementation. Status tùy chỉnh không có mapping có thể trở thành `UNKNOWN`.

Vì vậy, hãy kiểm tra implementation và tài liệu đúng phiên bản đang sử dụng trước khi dựa vào một mapping cụ thể. Đừng giả định `OUT_OF_SERVICE` của Actuator luôn được giữ nguyên thành `OUT_OF_SERVICE` trong Eureka.

## 6. Tạo HealthIndicator cho dependency quan trọng

Actuator có sẵn một số health indicator khi dependency tương ứng xuất hiện trên classpath. Ứng dụng cũng có thể tạo `HealthIndicator` riêng để kiểm tra một điều kiện nghiệp vụ hoặc dependency đặc thù.

Ví dụ:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component
public class InventoryDependencyHealthIndicator
        implements HealthIndicator {

    @Override
    public Health health() {
        boolean available = checkInventoryDependency();

        if (available) {
            return Health.up().build();
        }

        return Health.down()
                .withDetail("dependency", "inventory")
                .build();
    }

    private boolean checkInventoryDependency() {
        // Thay bằng phép kiểm tra thực tế có timeout phù hợp.
        return true;
    }
}
~~~

Đây là ví dụ cấu trúc. Trong ứng dụng thực tế, phương thức kiểm tra cần gọi dependency thật, đặt timeout rõ ràng và tránh tạo tải quá lớn. Không nên trả `UP` cố định như phần placeholder trên khi đưa vào production.

Khi health indicator báo DOWN, handler có thể tổng hợp thành trạng thái không sẵn sàng và Eureka Client sẽ công bố trạng thái đó. Consumer dùng Eureka sẽ tránh chọn instance không ở trạng thái UP nếu bộ lọc chỉ lấy instance UP được bật.

### 6.1. Chọn dependency nào được tính vào health tổng thể

Không phải mọi dependency đều phải quyết định khả năng nhận traffic. Hãy phân loại:

- Dependency bắt buộc để xử lý request chính, ví dụ database mà nghiệp vụ không thể hoạt động nếu thiếu.
- Dependency có thể suy giảm chức năng nhưng service vẫn phục vụ một phần.
- Dependency chỉ phục vụ monitoring, analytics hoặc tác vụ nền không ảnh hưởng request chính.

Nếu một dependency tùy chọn trả DOWN nhưng service vẫn có thể phục vụ nghiệp vụ, đưa indicator đó vào aggregate health có thể khiến Eureka loại instance quá sớm. Ngược lại, nếu bỏ qua dependency thiết yếu, Eureka có thể tiếp tục công bố instance không thể xử lý request.

HealthIndicator nên thể hiện khả năng phục vụ mà consumer cần, không chỉ phản ánh mọi lỗi kỹ thuật xuất hiện trong tiến trình.

## 7. Phân biệt liveness và readiness

Hai khái niệm này hữu ích khi ứng dụng chạy trong container hoặc Kubernetes:

- **Liveness:** tiến trình còn sống và có thể tiếp tục chạy không?
- **Readiness:** ứng dụng đã sẵn sàng nhận request nghiệp vụ chưa?

Một tiến trình có thể liveness UP nhưng readiness chưa đạt vì đang khởi tạo cache hoặc chờ kết nối database. Trong giai đoạn đó, không nên đưa instance vào nhận traffic chỉ vì JVM vẫn hoạt động.

Spring Boot hỗ trợ health group cho liveness và readiness ở các phiên bản phù hợp. Có thể bật probe endpoint bằng cấu hình:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Cấu hình này hữu ích cho probe của nền tảng triển khai, nhưng không tự đảm bảo Eureka chỉ dùng đúng readiness group. EurekaHealthCheckHandler tổng hợp các health contributor trong application context theo implementation của nó. Hãy xác minh các contributor và status aggregator đang tham gia để tránh việc liveness, readiness hoặc một indicator phụ làm thay đổi trạng thái Eureka ngoài ý muốn.

Một chính sách thường dùng:

- Instance chưa sẵn sàng: không công bố là UP cho traffic.
- Instance đã sẵn sàng: health tổng thể đạt và Eureka công bố UP.
- Instance đang drain: chuyển sang trạng thái không nhận traffic mới theo cơ chế được hỗ trợ, sau đó hoàn tất request đang xử lý.
- Instance lỗi: health tổng thể chuyển trạng thái không sẵn sàng và consumer ngừng chọn instance sau khi dữ liệu cập nhật.

## 8. Thời điểm trạng thái được truyền đến Eureka

Eureka Client vẫn gửi heartbeat để gia hạn lease. Khi health handler được đăng ký, client tính trạng thái ứng dụng trong quá trình refresh instance information và truyền thay đổi tới Eureka Server qua cơ chế cập nhật registration/heartbeat.

Điều này có nghĩa trạng thái trên dashboard Eureka không nhất thiết đổi cùng thời điểm với response của `/actuator/health`.

Có thể có độ trễ do:

- Chu kỳ heartbeat và làm mới instance information.
- Chu kỳ replication/update thông tin instance.
- Kết nối giữa Eureka Client và Eureka Server.
- Cache và chu kỳ cập nhật registry phía consumer.
- Thời gian chạy của các HealthIndicator.

Không nên lấy một lần gọi `/actuator/health` làm bằng chứng rằng mọi consumer đã nhận trạng thái mới. Hãy kiểm tra trạng thái trên Eureka Server và danh sách instance từ phía consumer.

## 9. URL health trong metadata của Eureka

Eureka instance có các thuộc tính URL như status page và health check URL. Các URL này được công bố trong metadata để hệ thống khác hoặc công cụ vận hành có thể tham khảo.

Ví dụ cấu hình đường dẫn:

~~~yaml
eureka:
  instance:
    statusPageUrlPath: /actuator/info
    healthCheckUrlPath: /actuator/health
~~~

Đường dẫn thực tế phải khớp với cấu hình Actuator của ứng dụng. Nếu đổi management base path, servlet path, context path hoặc chạy sau proxy, hãy cập nhật URL được công bố sao cho consumer và công cụ vận hành truy cập đúng endpoint.

Cần nhớ:

- `eureka.client.healthcheck.enabled` bật cơ chế health handler phía client.
- `eureka.instance.healthCheckUrlPath` cấu hình URL health được công bố trong instance metadata.
- Hai property có mục đích khác nhau.
- URL health trong metadata không có nghĩa Eureka Server mặc định chủ động polling endpoint đó.

Nếu Actuator dùng cổng management riêng, cần kiểm tra cả port và scheme được công bố. Một URL metadata sai có thể gây lỗi cho hệ thống giám sát hoặc consumer sử dụng URL đó, dù health handler nội bộ vẫn hoạt động.

## 10. Kiểm tra kết quả đồng bộ

Sau khi bật cấu hình, cần kiểm tra ba góc nhìn:

1. **Actuator:** ứng dụng trả health status nào?
2. **Eureka Server:** instance đang được công bố ở trạng thái nào?
3. **Consumer:** discovery client có còn trả instance đó trong danh sách được sử dụng hay không?

Ví dụ gọi endpoint Actuator:

~~~bash
curl http://localhost:8082/actuator/health
~~~

Nếu ứng dụng có security, cần gửi thông tin xác thực phù hợp. Không nên mở endpoint health chi tiết ra mạng công cộng chỉ để tiện kiểm tra.

Có thể quan sát Eureka dashboard tại địa chỉ server, thường là:

~~~text
http://localhost:8761/
~~~

Hoặc truy vấn registry qua API Eureka phù hợp với phiên bản server.

### 10.1. Kịch bản kiểm thử

| Kịch bản | Actuator mong đợi | Eureka mong đợi | Consumer mong đợi |
|---|---|---|---|
| Tất cả dependency khỏe | UP | UP | Có thể chọn instance |
| Dependency bắt buộc lỗi | DOWN hoặc status không sẵn sàng | Không còn UP | Không chọn instance nếu chỉ lọc UP |
| Dependency phục hồi | UP | Trở lại UP sau khi cập nhật | Instance xuất hiện lại sau refresh |
| Ứng dụng đang drain | Status theo chính sách drain | Trạng thái không nhận traffic mới | Ngừng chọn instance sau khi cập nhật |
| Eureka Server mất kết nối | Actuator vẫn có thể UP | Registry chưa nhận thay đổi mới | Consumer có thể thấy dữ liệu cũ trong thời gian chuyển tiếp |

Thử cả chiều DOWN và phục hồi UP. Một số lỗi cấu hình chỉ xuất hiện khi health status thay đổi lần đầu hoặc khi instance phục hồi.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Actuator DOWN nhưng Eureka vẫn UP | Health handler chưa bật hoặc không được đăng ký | Kiểm tra `eureka.client.healthcheck.enabled` và dependency Actuator |
| Eureka đăng ký trạng thái UNKNOWN khi khởi động | Property healthcheck đặt trong bootstrap configuration hoặc cấu hình chưa sẵn sàng | Đặt property trong application configuration |
| Eureka luôn DOWN dù endpoint health là UP | Một HealthIndicator khác vẫn DOWN hoặc aggregator chọn status nghiêm trọng hơn | Kiểm tra từng contributor và StatusAggregator |
| Eureka DOWN nhưng một API vẫn trả thành công | Health policy tính cả dependency không thiết yếu | Phân loại lại indicator theo khả năng phục vụ nghiệp vụ |
| Consumer vẫn gọi instance lỗi | Consumer dùng cache cũ hoặc chưa lọc chỉ instance UP | Kiểm tra refresh, cache và `eureka.client.filter-only-up-instances` |
| Consumer không thấy instance sau khi phục hồi | Status chưa được replicate hoặc client chưa refresh registry | Kiểm tra heartbeat, update interval và registry fetch |
| URL health metadata trả 404 | Context path hoặc Actuator base path không khớp | Cập nhật `healthCheckUrlPath` và kiểm tra management port |
| Health status tùy chỉnh thành UNKNOWN | Status chưa có mapping sang Eureka InstanceStatus | Cấu hình mapping theo phiên bản hoặc viết HealthCheckHandler riêng |

### 11.1. Kiểm tra HealthIndicator gây DOWN

Actuator thường tổng hợp nhiều indicator. Chỉ nhìn trạng thái tổng thể không cho biết contributor nào đang làm ứng dụng DOWN.

Trong môi trường phát triển, có thể bật chi tiết health có kiểm soát để xem từng component. Trong production, chỉ mở chi tiết cho người vận hành được xác thực và tránh tiết lộ hostname, thông tin kết nối, tên database hoặc dữ liệu nhạy cảm.

### 11.2. Kiểm tra bộ lọc phía consumer

Trong cấu hình Eureka Client, `eureka.client.filter-only-up-instances` điều khiển việc lọc danh sách instance chỉ còn trạng thái UP. Tài liệu cấu hình của các release hiện hành đặt mặc định là true. Nếu ứng dụng thay đổi property này, consumer có thể nhận cả instance ở trạng thái khác UP; hãy cân nhắc kỹ trước khi thay đổi.

Đồng bộ status ở provider chỉ có ý nghĩa khi consumer thực sự sử dụng trạng thái đó trong discovery và lựa chọn instance.

## 12. Tùy biến HealthCheckHandler

Nếu cần logic phức tạp hơn cách tổng hợp mặc định của Actuator, có thể triển khai `com.netflix.appinfo.HealthCheckHandler` riêng.

Handler nhận trạng thái hiện tại và trả về `InstanceInfo.InstanceStatus` mà Eureka Client sẽ sử dụng. Ví dụ, ứng dụng có thể đưa một quy tắc nghiệp vụ vào quyết định trạng thái, hoặc ánh xạ custom status theo chính sách riêng.

Khi tùy biến:

- Chỉ trả về trạng thái phù hợp với vocabulary Eureka.
- Không thực hiện phép gọi mạng dài hoặc không giới hạn trong mỗi lần health check.
- Tránh phụ thuộc vòng lặp vào Eureka health indicator hoặc discovery client của chính ứng dụng.
- Xác định rõ trạng thái trong giai đoạn startup và shutdown.
- Kiểm thử trường hợp exception; lỗi khi tính health có thể khiến client công bố trạng thái không mong muốn.
- Ghi log và metric khi handler trả về trạng thái không như dự kiến.

Nếu chỉ cần kiểm tra database hoặc broker, một HealthIndicator phù hợp thường đơn giản hơn việc viết handler riêng. Chỉ tùy biến HealthCheckHandler khi chính sách tổng hợp hoặc mapping mặc định không đáp ứng được yêu cầu.

## 13. Bảo mật và hiệu năng

Health endpoint có thể tiết lộ thông tin về dependency và cấu trúc nội bộ. Hãy chỉ expose endpoint cần thiết, giới hạn quyền truy cập và không đặt `show-details: always` cho mọi người dùng.

Health check cũng có chi phí:

- Một indicator gọi database hoặc broker có thể tạo thêm tải.
- Một phép kiểm tra chậm có thể làm chậm quá trình tính status.
- Nếu quá nhiều indicator chạy đồng thời, heartbeat/update status có thể bị ảnh hưởng.
- Nếu health policy quá nhạy, lỗi tạm thời có thể làm instance bị loại khỏi traffic.
- Nếu health policy quá lỏng, instance hỏng vẫn có thể được công bố UP.

Nên dùng timeout cho các phép kiểm tra dependency, chọn đúng tập health indicator quan trọng và đặt threshold phù hợp. Health check phải phản ánh khả năng phục vụ chứ không trở thành một workload nặng hơn request nghiệp vụ.

## 14. Quy trình triển khai đề xuất

Khi áp dụng đồng bộ Actuator với Eureka trong một service:

1. Thêm Eureka Client và Spring Boot Actuator dependency tương thích.
2. Đặt service ID và địa chỉ Eureka Server.
3. Bật `eureka.client.healthcheck.enabled` trong application configuration.
4. Xác định health indicator nào thực sự quyết định khả năng phục vụ.
5. Kiểm tra StatusAggregator và mapping trạng thái của đúng release train.
6. Cấu hình Actuator endpoint và bảo vệ thông tin health chi tiết.
7. Đồng bộ URL health metadata nếu có consumer hoặc công cụ vận hành sử dụng URL đó.
8. Kiểm thử UP, DOWN, phục hồi và graceful shutdown.
9. Xác minh trạng thái ở Eureka Server và danh sách instance từ consumer.
10. Theo dõi thời gian propagation, lỗi health check và request thất bại sau triển khai.

Không chỉ kiểm thử endpoint Actuator. Điều cần xác nhận là trạng thái đã được Eureka nhận và consumer có hành vi định tuyến đúng.

## 15. Ghi nhớ

- Eureka heartbeat xác nhận client còn duy trì lease; nó không tự chứng minh ứng dụng khỏe về nghiệp vụ.
- `eureka.client.healthcheck.enabled` bật việc đồng bộ trạng thái Actuator qua health handler của Eureka Client.
- Đặt property trong `application.yml`, không đặt trong `bootstrap.yml`.
- EurekaHealthCheckHandler tổng hợp HealthContributor/HealthIndicator trong application context và ánh xạ kết quả sang InstanceStatus.
- Actuator `/actuator/health` là HTTP endpoint; Eureka Server không mặc định polling endpoint này để lấy trạng thái.
- `eureka.instance.healthCheckUrlPath` chỉ cấu hình URL health trong metadata và khác với property bật health handler.
- Mapping status có thể khác theo phiên bản; custom status cần được ánh xạ rõ ràng.
- Phải kiểm tra trạng thái ở Actuator, Eureka Server và consumer; cache và heartbeat có thể tạo độ trễ.
- Chọn health indicator theo khả năng phục vụ nghiệp vụ, bảo vệ endpoint và giới hạn chi phí health check.

Đồng bộ Actuator với Eureka giúp registry phản ánh tốt hơn trạng thái phục vụ của từng instance. Khi health policy, status mapping và thời điểm cập nhật được thiết kế rõ ràng, consumer có thể tránh gửi request đến instance đang không đủ điều kiện xử lý nghiệp vụ.

## Tài liệu tham khảo

- [Spring Cloud Netflix — Eureka's Health Checks](https://docs.spring.io/spring-cloud-netflix/reference/html/index.html)
- [Spring Cloud Netflix — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [EurekaHealthCheckHandler source](https://github.com/spring-cloud/spring-cloud-netflix/blob/main/spring-cloud-netflix-eureka-client/src/main/java/org/springframework/cloud/netflix/eureka/EurekaHealthCheckHandler.java)
