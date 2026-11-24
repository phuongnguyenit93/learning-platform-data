# DiscoveryClientHealthIndicator và health tổng hợp của khám phá

## 1. Vì sao cần health cho Service Discovery?

Một ứng dụng có thể vẫn trả lời HTTP và xử lý một số request trong khi không thể truy vấn registry. Ví dụ, Eureka Server tạm thời không truy cập được, Kubernetes API từ chối request do thiếu RBAC, hoặc client discovery gặp lỗi khi đọc danh sách service. Nếu chỉ kiểm tra tiến trình và web server, hệ thống giám sát có thể kết luận ứng dụng hoàn toàn khỏe mạnh dù chức năng khám phá dịch vụ đang suy giảm.

Spring Cloud Commons cung cấp **DiscoveryClientHealthIndicator** để đưa tình trạng của DiscoveryClient vào hệ thống health của Spring Boot Actuator. Health indicator này giúp quan sát khả năng gọi API discovery ở phía ứng dụng.

Trong module Spring Cloud Service Discovery, cần nhìn health theo nhiều lớp:

- Ứng dụng có còn chạy và phục vụ HTTP hay không.
- DiscoveryClient có truy vấn được thông tin registry hay không.
- Các provider discovery cụ thể như Eureka, Consul hoặc Kubernetes có đang hoạt động hay không.
- Các service mà nghiệp vụ bắt buộc cần có instance phù hợp hay không.
- Những instance được tìm thấy có thực sự khỏe và xử lý request thành công hay không.

Các câu hỏi trên liên quan nhưng không thể thay thế cho nhau. DiscoveryClientHealthIndicator chủ yếu kiểm tra lớp DiscoveryClient; nó không tự gửi request nghiệp vụ đến mọi instance để xác nhận sức khỏe của từng service.

## 2. DiscoveryClientHealthIndicator kiểm tra điều gì?

DiscoveryClient là abstraction của Spring Cloud để lấy danh sách service và các instance tương ứng. Một số thao tác thường dùng:

- **getServices():** lấy danh sách service ID mà client hiện biết.
- **getInstances(serviceId):** lấy danh sách instance của một service ID.
- **description():** mô tả implementation discovery đang được sử dụng.

Theo cấu hình mặc định phổ biến, DiscoveryClientHealthIndicator gọi getServices() để lấy danh sách service và dùng kết quả này làm phép kiểm tra. Nếu thao tác hoàn tất bình thường, indicator báo UP và có thể đính kèm danh sách service; nếu truy vấn ném exception, indicator báo DOWN cùng thông tin lỗi. Ở một số phiên bản mới, có thể đặt use-services-query=false để thay truy vấn danh sách bằng DiscoveryClient.probe(), một phép kiểm tra nhẹ hơn. Ý nghĩa probe phụ thuộc implementation; hãy xem tài liệu provider nếu cần xác nhận kết nối trực tiếp đến registry.

Điều này cho biết thao tác kiểm tra qua DiscoveryClient đã hoàn tất tại thời điểm đó; nó không nhất thiết chứng minh có một network round-trip mới đến registry. Chẳng hạn, Eureka Client thường đọc danh sách service từ registry cache cục bộ. Vì vậy, health UP có thể cùng tồn tại với tình trạng Eureka Server tạm thời không truy cập được, miễn là client vẫn trả dữ liệu cache. Với provider khác, getServices hoặc probe có thể có cách kiểm tra khác nhau.

Kết quả không đồng nghĩa:

- Tất cả service ID bắt buộc đều có trong registry.
- Mọi instance trong danh sách đều có trạng thái UP.
- Mọi instance đều có thể kết nối qua mạng.
- Các endpoint nghiệp vụ của instance đều phản hồi đúng.
- Registry đã đồng bộ tức thời giữa mọi node hoặc client.

Một danh sách service rỗng không nhất thiết là lỗi kết nối. Trong môi trường mới khởi động, namespace rỗng hoặc hệ thống không có service nào được đăng ký, DiscoveryClient vẫn có thể truy vấn thành công. Nếu nghiệp vụ yêu cầu một service cụ thể phải tồn tại, cần thêm kiểm tra riêng cho service đó.

Ở một số release train, indicator còn theo dõi việc DiscoveryClient đã được khởi tạo hay chưa. Trước khi client hoàn tất giai đoạn khởi tạo hoặc phát event đăng ký tương ứng, health có thể là UNKNOWN với mô tả client chưa initialized. Hãy phân biệt trạng thái khởi tạo này với DOWN do truy vấn provider thất bại.

## 3. Health indicator được đưa vào Actuator như thế nào?

Spring Boot Actuator cung cấp các endpoint và cơ chế tổng hợp health contributor. Khi các dependency cần thiết có mặt và auto-configuration được bật, Spring Cloud có thể đăng ký health indicator cho DiscoveryClient.

Một cấu hình thường dùng:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: when-authorized

spring:
  cloud:
    discovery:
      client:
        health-indicator:
          enabled: true
          include-description: false
          use-services-query: true
        composite-indicator:
          enabled: true
~~~

Ý nghĩa:

| Thuộc tính | Tác dụng |
|---|---|
| spring.cloud.discovery.client.health-indicator.enabled | Bật hoặc tắt health indicator discovery do Spring Cloud cung cấp |
| spring.cloud.discovery.client.health-indicator.include-description | Cho phép đưa mô tả của DiscoveryClient vào chi tiết health |
| spring.cloud.discovery.client.health-indicator.use-services-query | Dùng getServices() để kiểm tra; nếu false, dùng probe() nhẹ hơn ở các phiên bản hỗ trợ |
| spring.cloud.discovery.client.composite-indicator.enabled | Bật hoặc tắt composite health contributor của discovery |
| spring.cloud.discovery.enabled | Bật các health indicator discovery do Spring Cloud cấu hình |
| management.endpoint.health.show-details | Kiểm soát khi nào response health hiển thị chi tiết |
| management.endpoints.web.exposure.include | Quyết định endpoint Actuator nào được mở qua HTTP |

Trong các cấu hình hiện hành phổ biến, health indicator và composite indicator được bật mặc định; include-description thường mặc định false, còn use-services-query mặc định true. Thuộc tính use-services-query không có ở mọi release train cũ. Hãy đối chiếu tài liệu của phiên bản Spring Cloud đang dùng nếu ứng dụng không thấy property hoặc muốn thay đổi hành vi.

Với registry có rất nhiều service, có thể giảm chi phí mỗi lần health check bằng cách dùng probe thay vì lấy toàn bộ danh sách:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          use-services-query: false
~~~

Chỉ dùng tùy chọn này khi DiscoveryClient implementation có hỗ trợ probe phù hợp. Probe nhẹ hơn không cung cấp danh sách service trong health detail; mục tiêu của nó là kiểm tra khả năng hoạt động của client với chi phí thấp hơn.

Tắt health indicator không đồng nghĩa tắt service discovery. Ứng dụng vẫn có thể sử dụng DiscoveryClient để tra cứu service; chỉ phần health contributor tương ứng không còn tham gia endpoint health.

### 3.1. Truy vấn endpoint health

Khi endpoint health được expose và có quyền truy cập, có thể gọi:

~~~bash
curl -i http://localhost:8080/actuator/health
~~~

Response có cấu trúc khái quát:

~~~json
{
  "status": "UP",
  "components": {
    "discoveryComposite": {
      "status": "UP"
    },
    "diskSpace": {
      "status": "UP"
    },
    "ping": {
      "status": "UP"
    }
  }
}
~~~

Đây là ví dụ minh họa. Tên component, cấu trúc chi tiết và việc có component tổng hợp hay không phụ thuộc các bean health được đăng ký trong ứng dụng. Hãy đọc tên thực tế trong response thay vì giả định mọi phiên bản đều có một key cố định.

Nếu cấu hình chỉ cho phép người dùng đã xác thực xem chi tiết, request không có quyền có thể chỉ nhận status tổng hợp. Đây là hành vi bảo mật có chủ đích.

## 4. Phân biệt health của discovery với health của service instance

Một trong những nhầm lẫn phổ biến là coi DiscoveryClientHealthIndicator như phép kiểm tra toàn bộ service được tìm thấy. Hai loại kiểm tra có mục đích khác nhau:

| Kiểm tra | Phạm vi | Ví dụ kết quả |
|---|---|---|
| DiscoveryClientHealthIndicator | Khả năng truy vấn discovery client | Có thể lấy danh sách service từ registry |
| Kiểm tra service bắt buộc | Một hoặc một số service ID do nghiệp vụ chọn | payment-service có ít nhất một instance |
| Health của instance | Một endpoint hoặc cơ chế health của instance đích | Instance trả lời health check thành công |
| Health nghiệp vụ | Khả năng hoàn thành một luồng nghiệp vụ | Có thể tạo báo giá hoặc xác nhận đơn hàng |

Ví dụ: DiscoveryClient trả danh sách service thành công nên health của discovery là UP. Tuy nhiên, payment-service chưa được triển khai nên getInstances(payment-service) trả danh sách rỗng. Hai kết quả không mâu thuẫn: registry có thể truy vấn được nhưng service nghiệp vụ đang thiếu instance.

Ngược lại, registry tạm thời không truy cập được nhưng ứng dụng có thể vẫn xử lý request bằng dữ liệu đã cache hoặc không cần gọi service khác. Việc chuyển toàn bộ ứng dụng sang DOWN cần dựa trên mức độ phụ thuộc thực tế, không nên tự động suy ra chỉ từ một lỗi discovery.

## 5. Health tổng hợp khi có nhiều DiscoveryClient

Một ứng dụng có thể có nhiều implementation DiscoveryClient trên classpath, chẳng hạn Eureka cùng một provider khác, hoặc một client chính và một client dự phòng. Các provider có thể cung cấp bean triển khai DiscoveryHealthIndicator; Spring Cloud Commons có thể gom các bean này vào DiscoveryCompositeHealthContributor để quan sát trạng thái health của từng provider.

Khi dùng health tổng hợp:

- Composite health contributor dựa trên các bean triển khai DiscoveryHealthIndicator đã đăng ký trong context.
- DiscoveryClientHealthIndicator là health indicator tổng quát dựa trên DiscoveryClient hiện được chọn.
- Kết quả từng provider có thể xuất hiện dưới dạng chi tiết con.
- Một trạng thái tổng hợp được tạo từ các trạng thái thành phần theo quy tắc của health aggregation.
- Một provider lỗi có thể làm trạng thái tổng hợp xấu đi, tùy cách composite indicator và status aggregator được cấu hình.

Có thể tắt riêng composite contributor bằng spring.cloud.discovery.client.composite-indicator.enabled=false. Thuộc tính này không đồng nghĩa tắt DiscoveryClientHealthIndicator tổng quát; hai cơ chế có property điều khiển riêng. Composite contributor thu thập các bean DiscoveryHealthIndicator đã đăng ký; tùy phiên bản và provider, tập bean này có thể gồm indicator tổng quát và các indicator do provider cung cấp. DiscoveryClientHealthIndicator là indicator tổng quát dựa trên DiscoveryClient hiện được chọn.

Không nên nhầm **CompositeDiscoveryClient** với composite health indicator. CompositeDiscoveryClient là abstraction kết hợp hoặc điều phối việc tra cứu giữa nhiều DiscoveryClient. Composite health indicator tổng hợp trạng thái health của các thành phần discovery. Một ứng dụng có thể có một cơ chế mà không nhất thiết có cùng cách cấu hình cho cơ chế còn lại.

### 5.1. Khi nào cần health tổng hợp?

Health tổng hợp hữu ích khi:

- Ứng dụng thực sự sử dụng nhiều discovery provider.
- Đội vận hành cần biết provider nào đang lỗi.
- Một provider chính và provider dự phòng có vai trò riêng cần quan sát độc lập.
- Cần phát hiện tình trạng một provider không thể truy vấn dù provider khác vẫn hoạt động.

Nếu chỉ có một DiscoveryClient, health indicator đơn thường đã đủ. Không nên thêm nhiều provider chỉ để tạo một health response phức tạp.

### 5.2. Thứ tự tra cứu không phải thứ tự health

Khi có nhiều DiscoveryClient, thứ tự ưu tiên trong lookup và trạng thái health là hai vấn đề khác nhau. Một provider có thể được ưu tiên cho getInstances, trong khi một provider khác vẫn được kiểm tra và báo lỗi trong health tổng hợp.

Vì vậy, khi health tổng hợp báo DOWN, hãy xem chi tiết từng component và xác định provider nào ảnh hưởng đến luồng request thực tế. Không kết luận ứng dụng không thể tìm dịch vụ chỉ từ status tổng hợp nếu ứng dụng còn provider khác có thể đáp ứng.

## 6. Quy tắc tổng hợp status của Spring Boot

Spring Boot Actuator thu thập trạng thái từ các HealthIndicator và HealthContributor, sau đó tổng hợp thành status của endpoint hoặc health group.

Các status thường gặp:

| Status | Ý nghĩa |
|---|---|
| UP | Thành phần được đánh giá đang hoạt động |
| DOWN | Thành phần gặp lỗi nghiêm trọng theo indicator |
| OUT_OF_SERVICE | Thành phần tạm thời không phục vụ |
| UNKNOWN | Không xác định được trạng thái |

Status tổng hợp phụ thuộc StatusAggregator và thứ tự ưu tiên status. Với cấu hình mặc định phổ biến, DOWN và OUT_OF_SERVICE được xem là trạng thái không khỏe và có thể làm endpoint health trả HTTP 503; UP thường trả HTTP 200. Nếu ứng dụng tùy chỉnh status order hoặc HTTP mapping, kết quả có thể khác.

Ví dụ cấu hình thứ tự status:

~~~yaml
management:
  endpoint:
    health:
      status:
        order: down,out-of-service,unknown,up
~~~

Không nên thay đổi thứ tự chỉ để dashboard hiển thị màu xanh. Status phải phản ánh đúng mức độ ảnh hưởng đến khả năng phục vụ. Nếu một provider phụ không thiết yếu bị lỗi, có thể cần một health group riêng hoặc một chính sách tổng hợp phù hợp thay vì hạ trạng thái toàn bộ ứng dụng.

## 7. Đưa discovery vào health group nào?

Actuator có thể công bố health tổng thể và các health group riêng như readiness hoặc liveness. Không nên tự động đưa mọi health indicator vào mọi group.

Ví dụ một cấu hình readiness group:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,requiredServices
~~~

requiredServices là tên bean của HealthIndicator tùy chỉnh ở phần tiếp theo. Khi muốn đưa indicator auto-configured vào group, hãy xác nhận ID thực tế trong response Actuator của phiên bản đang chạy trước khi khai báo include.

Chỉ đưa discovery vào readiness khi khả năng truy vấn registry là điều kiện bắt buộc để instance nhận request. Ví dụ, request đến service này luôn cần tra cứu một service khác theo thời gian thực và không có cache hoặc fallback an toàn.

Nếu ứng dụng có thể tiếp tục phục vụ bằng dữ liệu đã cache, hoặc một số request không cần discovery, việc để registry gián đoạn làm Pod NotReady có thể loại bỏ quá nhiều capacity. Khi đó nên quan sát discovery ở health tổng thể hoặc một group riêng, trong khi readiness chỉ kiểm tra điều kiện thực sự cần thiết để nhận traffic.

Không đưa discovery network check vào liveness chỉ vì muốn tự khởi động lại khi registry lỗi. Nếu Eureka hoặc Kubernetes API gặp sự cố diện rộng, tất cả ứng dụng có thể restart đồng loạt và làm tình trạng nặng hơn. Liveness nên tập trung vào khả năng tiến trình tự phục hồi, còn readiness phản ánh khả năng nhận traffic.

## 8. Tùy chỉnh kiểm tra service bắt buộc

Nếu nghiệp vụ yêu cầu một số service phải có ít nhất một instance, hãy viết HealthIndicator riêng. Ví dụ sau kiểm tra hai service ID bắt buộc:

~~~java
import java.util.Map;
import java.util.LinkedHashMap;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component("requiredServices")
public class RequiredServicesHealthIndicator implements HealthIndicator {

    private final DiscoveryClient discoveryClient;

    public RequiredServicesHealthIndicator(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @Override
    public Health health() {
        Map<String, Integer> instanceCounts = new LinkedHashMap<>();
        instanceCounts.put("payment-service",
                discoveryClient.getInstances("payment-service").size());
        instanceCounts.put("inventory-service",
                discoveryClient.getInstances("inventory-service").size());

        boolean allAvailable = instanceCounts.values()
                .stream()
                .allMatch(count -> count > 0);

        if (allAvailable) {
            return Health.up()
                    .withDetail("instanceCounts", instanceCounts)
                    .build();
        }

        return Health.down()
                .withDetail("instanceCounts", instanceCounts)
                .withDetail("reason", "A required service has no discovered instance")
                .build();
    }
}
~~~

Đây là ví dụ kiểm tra sự tồn tại của instance trong discovery result, không gọi endpoint của từng instance. Nếu getInstances ném exception, Actuator sẽ nhận lỗi từ indicator; nếu danh sách rỗng, indicator tự trả DOWN vì service được đánh dấu là bắt buộc.

Không nên đưa danh sách service bắt buộc cố định vào code nếu mỗi môi trường có dependency khác nhau. Có thể đưa service ID vào cấu hình, nhưng cần xác thực cấu hình khi khởi động.

Nếu cần kiểm tra instance thực sự phục vụ được, hãy thiết kế health check chuyên biệt có timeout, concurrency limit và cache kết quả. Gọi health endpoint của mọi instance mỗi lần Actuator được scrape có thể tạo tải lớn và làm health endpoint chậm.

## 9. Tránh health check gây tải hoặc vòng phụ thuộc

Health endpoint có thể được Kubernetes, load balancer, monitoring system và người vận hành gọi thường xuyên. Nếu mỗi lần gọi health lại thực hiện nhiều truy vấn mạng, chính health check có thể trở thành nguồn tải mới.

Các nguyên tắc nên áp dụng:

- Dùng thao tác nhẹ như kiểm tra DiscoveryClient có thể truy vấn registry.
- Không quét sâu mọi service và mọi instance ở mỗi lần scrape nếu không cần.
- Đặt timeout rõ ràng cho thao tác có thể gọi mạng.
- Tránh retry dài trong luồng health request.
- Nếu cần kiểm tra sâu, chạy định kỳ ở background và health endpoint chỉ đọc kết quả gần nhất.
- Phân biệt lỗi tạm thời với lỗi kéo dài để tránh dao động UP/DOWN liên tục.
- Không để health endpoint phụ thuộc vòng tròn vào chính service đang được kiểm tra.

Ví dụ vòng phụ thuộc nguy hiểm: health check của service A gọi service B, health check của B lại gọi A. Khi cả hai khởi động, hai health check có thể chờ nhau hoặc tạo tải retry. Health indicator nên kiểm tra các dependency ở mức tối thiểu và có giới hạn.

## 10. Quan sát và chẩn đoán

Khi DiscoveryClientHealthIndicator báo DOWN, hãy kiểm tra theo thứ tự:

1. Đọc chi tiết health response và exception của component discovery.
2. Xác định provider thực tế là Eureka, Consul, Kubernetes hay implementation khác.
3. Kiểm tra kết nối đến registry hoặc Kubernetes API từ chính môi trường chạy ứng dụng.
4. Kiểm tra DNS, port, TLS, authentication và authorization.
5. Kiểm tra log provider client và thời điểm fetch/watch gần nhất.
6. Nếu health tổng hợp có nhiều component, xác định component nào DOWN và provider đó có nằm trên đường tra cứu thực tế không.
7. Nếu discovery health UP nhưng service bắt buộc thiếu instance, kiểm tra service ID, namespace, registration và selector tương ứng.
8. Nếu instance tồn tại nhưng request lỗi, kiểm tra host, port, network policy, health endpoint và load balancing.

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Discovery health DOWN | Lỗi truy vấn provider hoặc exception từ DiscoveryClient | Xem exception, endpoint registry, network và quyền |
| Discovery health UP nhưng service list rỗng | Registry chưa có service hoặc namespace/filter không đúng | Kiểm tra đăng ký, namespace và provider |
| Discovery health UP nhưng service bắt buộc không có instance | Service ID sai hoặc instance chưa đăng ký | Kiểm tra getInstances(serviceId), service name và registry |
| Composite health DOWN nhưng một provider vẫn hoạt động | Provider khác trong composite đang lỗi | Đọc status từng component và thứ tự lookup |
| Health endpoint chậm | Indicator thực hiện truy vấn nặng hoặc chờ mạng | Đo thời gian, timeout và số lần gọi |
| Pod NotReady khi registry lỗi | Discovery được đưa vào readiness group | Xem readiness policy và khả năng fallback |
| Ứng dụng restart liên tục khi registry lỗi | Liveness phụ thuộc vào discovery | Tách liveness khỏi registry availability |

## 11. Kiểm thử health indicator

Nên kiểm tra cả trường hợp provider hoạt động và lỗi:

1. Khi DiscoveryClient truy vấn thành công, xác nhận health component có status phù hợp.
2. Khi getServices trả danh sách rỗng nhưng không có exception, xác nhận ứng dụng diễn giải đúng trạng thái rỗng.
3. Khi provider ném exception, xác nhận indicator báo lỗi và không làm lộ thông tin nhạy cảm.
4. Khi có nhiều DiscoveryClient, xác nhận từng component được biểu diễn đúng trong health tổng hợp.
5. Khi một provider lỗi nhưng provider khác hoạt động, xác nhận status tổng thể phù hợp với chính sách vận hành.
6. Kiểm tra health group readiness và liveness không bao gồm nhầm contributor.
7. Đo latency của endpoint health khi monitoring scrape theo tần suất dự kiến.
8. Kiểm tra response khi người dùng không có quyền xem chi tiết health.

Có thể dùng mock DiscoveryClient trong unit test để mô phỏng danh sách service, danh sách instance rỗng và exception. Với integration test, dùng provider thử nghiệm hoặc môi trường test riêng để xác minh auto-configuration và bean name thực tế.

## 12. Các lỗi thiết kế thường gặp

### 12.1. Xem DiscoveryClient UP là mọi service đều khỏe

Indicator chỉ kiểm tra khả năng truy vấn discovery theo implementation. Muốn kiểm tra service ID cụ thể, cần kiểm tra instance riêng; muốn kiểm tra khả năng xử lý nghiệp vụ, cần health check ở tầng phù hợp.

### 12.2. Coi danh sách service rỗng là lỗi kết nối

Registry rỗng có thể là trạng thái hợp lệ. Phân biệt truy vấn thành công nhưng không có dữ liệu với truy vấn thất bại do mạng hoặc quyền.

### 12.3. Đưa discovery vào liveness

Registry lỗi không có nghĩa tiến trình Spring Boot cần restart. Liveness phụ thuộc discovery có thể gây restart storm trong sự cố diện rộng.

### 12.4. Đưa tất cả provider vào readiness

Nếu ứng dụng có provider dự phòng hoặc không dùng mọi provider cho mọi request, một provider phụ lỗi không nhất thiết phải loại Pod khỏi traffic. Readiness cần phản ánh yêu cầu phục vụ thực tế.

### 12.5. Health check quét toàn bộ instance

Gọi health endpoint của mọi instance trong mỗi lần scrape có thể tạo tải và vòng phụ thuộc. Dùng kiểm tra nông cho health tổng hợp; thiết kế kiểm tra sâu riêng với lịch chạy, timeout và giới hạn tải.

### 12.6. Mở chi tiết health cho mọi người

Health response có thể tiết lộ tên provider, service ID, exception, hostname hoặc topology nội bộ. Giới hạn show-details và bảo vệ endpoint theo quyền truy cập.

## 13. Quy trình cấu hình và vận hành

1. Xác định provider DiscoveryClient thực tế và phiên bản Spring Cloud.
2. Kiểm tra health indicator auto-configured có được bật hay không.
3. Cấu hình include-description và chính sách hiển thị chi tiết phù hợp.
4. Truy vấn Actuator health để ghi nhận component name và status thực tế.
5. Nếu có nhiều provider, kiểm tra health tổng hợp và phân biệt nó với thứ tự lookup.
6. Xác định service ID nào thật sự bắt buộc cho request của ứng dụng.
7. Chỉ tạo health indicator nghiệp vụ riêng khi cần kiểm tra các service ID hoặc instance cụ thể.
8. Quyết định discovery có thuộc readiness group hay không; tránh đưa nó vào liveness.
9. Đặt timeout và giới hạn tải cho các kiểm tra có truy cập mạng.
10. Kiểm thử tình huống provider lỗi, registry rỗng, thiếu instance, nhiều provider và health endpoint bị gọi thường xuyên.

## 14. Tài liệu tham khảo

- [Spring Cloud Commons - Common Abstractions và Health Indicators](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons - Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)

Hãy đối chiếu tài liệu theo release train mà dự án sử dụng; property và hành vi health indicator có thể thay đổi giữa các phiên bản.

## 15. Tổng kết

DiscoveryClientHealthIndicator đưa khả năng thực hiện phép kiểm tra qua DiscoveryClient vào Spring Boot Actuator. Với provider có registry cache cục bộ như Eureka, health UP không nhất thiết chứng minh registry server đang reachable ngay lúc đó. Indicator cũng không xác nhận tất cả service bắt buộc đều tồn tại hoặc mọi instance đều khỏe. Một danh sách service rỗng có thể là hợp lệ nếu truy vấn thành công và registry chưa có dữ liệu.

Khi ứng dụng có nhiều DiscoveryClient, health tổng hợp có thể cho biết trạng thái từng provider và status chung. Cần phân biệt health tổng hợp với CompositeDiscoveryClient dùng cho tra cứu. Spring Boot tiếp tục tổng hợp các HealthContributor theo StatusAggregator và health group được cấu hình. Chỉ đưa discovery vào readiness khi registry thực sự cần thiết để phục vụ request; không dùng lỗi registry làm điều kiện liveness. Với yêu cầu kiểm tra service cụ thể, hãy tạo indicator riêng có timeout và giới hạn tải, đồng thời bảo vệ chi tiết health khỏi người không có quyền.
