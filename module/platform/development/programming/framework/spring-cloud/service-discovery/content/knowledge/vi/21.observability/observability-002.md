# Giảm chi phí getServices trong kiểm tra sức khỏe bằng probe

Spring Cloud có health indicator cho DiscoveryClient để Actuator phản ánh trạng thái của thành phần service discovery. Cách kiểm tra truyền thống có thể gọi getServices() và lấy danh sách tất cả service name trong registry. Khi registry lớn, thao tác này có thể tốn thời gian, tạo object và gây tải lặp lại mỗi lần health endpoint được thăm dò.

Nếu mục tiêu chỉ là xác nhận discovery client còn giao tiếp được với registry, việc liệt kê toàn bộ service name là không cần thiết. Spring Cloud Commons cung cấp phương thức probe() trên DiscoveryClient để health indicator có thể thực hiện phép kiểm tra nhẹ hơn. Có thể chọn chế độ này bằng cấu hình use-services-query=false, nhưng cần hiểu cách triển khai probe() của discovery client đang dùng: implementation mặc định có thể ủy quyền về getServices(), nên chỉ đổi property chưa chắc đã giảm chi phí.

Bài này giải thích cách health indicator hoạt động, khi nào nên dùng probe, cách triển khai phép kiểm tra nhẹ, cách quan sát hiệu quả và những giới hạn cần giữ rõ trong thiết kế.

## 1. Vì sao getServices() có thể trở thành chi phí đáng kể?

DiscoveryClient có hai thao tác thường được dùng ở các mục đích khác nhau:

- getInstances(serviceId) lấy các instance của một service cụ thể để consumer định tuyến request.
- getServices() liệt kê các service name mà registry biết.

Một health check chỉ muốn xác nhận kết nối discovery đang hoạt động, nhưng getServices() có thể phải lấy hoặc tổng hợp toàn bộ danh sách service. Tùy implementation, thao tác này có thể bao gồm:

1. Gọi API của registry hoặc đọc dữ liệu từ client cache.
2. Lấy danh sách application/service đã đăng ký.
3. Chuyển đổi response thành collection các service name.
4. Tổng hợp dữ liệu từ nhiều discovery client nếu dùng CompositeDiscoveryClient.
5. Cấp phát object và xử lý dữ liệu trước khi trả về health indicator.

Với registry có nhiều service, nhiều namespace hoặc nhiều nhóm ứng dụng, danh sách có thể lớn. Nếu health endpoint bị gọi liên tục bởi orchestrator, monitoring system và dashboard, chi phí này lặp lại thường xuyên.

Ví dụ, nếu một probe bị gọi mỗi 5 giây từ 20 instance ứng dụng, một health indicator có thể được kích hoạt hàng trăm lần mỗi phút. Nếu mỗi lần đều liệt kê toàn bộ service name qua mạng, phần kiểm tra sức khỏe có thể tạo tải đáng kể lên registry.

Không phải implementation nào cũng có chi phí như vậy. Một số client đã cache danh sách service hoặc getServices() chỉ đọc bộ nhớ cục bộ. Hãy đo latency, số lần gọi backend và allocation của implementation thực tế trước khi kết luận đây là bottleneck.

## 2. Health indicator của DiscoveryClient kiểm tra điều gì?

Spring Cloud Commons tích hợp DiscoveryClient với Spring Boot Actuator. DiscoveryClientHealthIndicator tham gia health aggregation để cho biết discovery client có hoạt động theo phép kiểm tra mà nó sử dụng hay không.

Ở chế độ dùng services query, health indicator gọi getServices() và có thể đưa danh sách service vào health details. Đây là một phép kiểm tra hữu ích khi cần xác minh client có thể đọc danh sách service, nhưng nó làm nhiều việc hơn một phép kiểm tra kết nối đơn giản.

Ở chế độ probe, health indicator gọi phương thức probe() của DiscoveryClient. Mục tiêu là cho implementation một điểm mở rộng để thực hiện thao tác kiểm tra rẻ hơn, không cần liệt kê toàn bộ service.

Cần phân biệt:

| Phép kiểm tra | Câu hỏi được trả lời | Phạm vi |
|---|---|---|
| getServices() | Client có lấy được danh sách service name không? | Truy vấn hoặc tổng hợp danh sách service |
| probe() | Discovery client có thực hiện được phép kiểm tra khả năng hoạt động không? | Do implementation định nghĩa |
| getInstances(serviceId) | Registry có trả instance cho một service cụ thể không? | Một service |
| Business health | Ứng dụng có xử lý được nghiệp vụ không? | Ứng dụng và dependency nghiệp vụ |

Probe không mặc nhiên kiểm tra mọi service, mọi instance hoặc database của ứng dụng. Nó chỉ kiểm tra điều mà implementation thiết kế cho probe.

## 3. Chuyển health indicator sang chế độ probe

Trong Spring Cloud Commons có thể cấu hình health indicator không dùng services query:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          use-services-query: false
~~~

Khi property này là false, DiscoveryClientHealthIndicator sử dụng DiscoveryClient.probe() thay vì lấy danh sách qua getServices().

Giá trị mặc định của use-services-query là true trong Spring Cloud Commons hiện hành. Vì vậy, nếu không khai báo property, health indicator sẽ dùng getServices(). Giá trị mặc định của include-description là false; chỉ bật khi cần đưa mô tả implementation vào health result.

Có thể giữ mô tả health indicator nếu cần:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          use-services-query: false
          include-description: true
~~~

Tên property và hành vi phụ thuộc phiên bản Spring Cloud Commons đang dùng. Hãy kiểm tra dependency management/BOM của dự án và xác nhận property được bind trong phiên bản đó. Nếu dự án dùng release train cũ chưa hỗ trợ cấu hình này, cần nâng cấp tương thích hoặc tự xây dựng health indicator phù hợp; không giả định property lạ sẽ tự có tác dụng.

Cấu hình này chỉ đổi cách health indicator kiểm tra. Nó không thay đổi cách consumer tra cứu instance, không thay đổi service registration và không thay thế health check của từng provider.

## 4. Điểm quan trọng: probe mặc định có thể vẫn gọi getServices()

DiscoveryClient có phương thức probe() với implementation mặc định có thể gọi getServices(). Điều này giúp các implementation cũ vẫn có hành vi kiểm tra tương thích, nhưng cũng có nghĩa là:

**Đặt use-services-query=false không tự động làm phép kiểm tra rẻ hơn nếu DiscoveryClient đang dùng không override probe().**

Luồng cần hiểu:

~~~mermaid
flowchart TD
    A["Actuator health request"] --> B["DiscoveryClientHealthIndicator"]
    B --> C{"use-services-query"}
    C -->|"true"| D["getServices()"]
    C -->|"false"| E["probe()"]
    E --> F{"Implementation override probe()?"}
    F -->|"Không"| D
    F -->|"Có"| G["Phép kiểm tra nhẹ do client cung cấp"]
    D --> H["Health result"]
    G --> H
~~~

Trước khi bật chế độ probe, hãy xác định implementation đang được inject:

- Eureka DiscoveryClient.
- Consul DiscoveryClient.
- ZooKeeper DiscoveryClient.
- SimpleDiscoveryClient.
- CompositeDiscoveryClient hoặc discovery client tùy chỉnh.

Không nên suy luận từ tên registry rằng probe đã được tối ưu. Kiểm tra mã nguồn hoặc tài liệu đúng phiên bản, hoặc đo xem probe có tiếp tục gọi getServices() hay không. Nếu bean được inject là CompositeDiscoveryClient và composite không override probe(), probe mặc định sẽ gọi getServices() trên composite; do đó danh sách từ các delegate vẫn có thể được tổng hợp.

### Ví dụ về hành vi của client tích hợp sẵn

Ở source hiện hành của Spring Cloud Netflix, EurekaDiscoveryClient triển khai getServices() nhưng không override probe(). Vì vậy, khi health indicator gọi probe(), implementation mặc định của interface vẫn gọi getServices(); property use-services-query=false không tự loại bỏ thao tác liệt kê này đối với Eureka client đó.

Ngược lại, ConsulDiscoveryClient của Spring Cloud Consul override probe() và gọi thao tác lấy trạng thái leader của Consul. Đây là phép kiểm tra nhẹ hơn việc liệt kê toàn bộ service. Hành vi này phụ thuộc phiên bản thư viện; hãy đối chiếu source của release train đang triển khai trước khi dựa vào kết luận.

## 5. Thiết kế một probe nhẹ và có ý nghĩa

Một probe tốt cần đáp ứng ba điều:

1. Kiểm tra đúng khả năng cần biết, thường là client còn giao tiếp được với registry hoặc backend discovery.
2. Có chi phí thấp và thời gian phản hồi giới hạn.
3. Trả lỗi khi thao tác kiểm tra thực sự thất bại, không trả thành công giả tạo.

Ví dụ về phần override trong một DiscoveryClient tùy chỉnh:

~~~java
@Override
public void probe() {
    registryHealthProbe.checkConnectivity();
}
~~~

registryHealthProbe là abstraction do ứng dụng định nghĩa, không phải API có sẵn của Spring Cloud. Nó có thể gọi một thao tác nhẹ mà registry client hỗ trợ, chẳng hạn kiểm tra trạng thái kết nối hoặc một request đọc metadata nhỏ. Nếu thao tác thất bại, phương thức cần ném exception để health indicator ghi nhận trạng thái không khỏe.

Một interface ứng dụng minh họa:

~~~java
public interface RegistryHealthProbe {
    void checkConnectivity();
}
~~~

Implementation cần tránh gọi lại getServices() bên trong checkConnectivity(), nếu mục tiêu là loại bỏ chi phí liệt kê service. Không nên tạo một probe chỉ trả về bình thường mà không kiểm tra gì, vì như vậy health indicator sẽ luôn UP ngay cả khi registry không thể truy cập.

Nếu registry client đã có connection state đáng tin cậy, probe có thể kiểm tra state đó. Nếu state chỉ phản ánh kết nối TCP nhưng request registry có thể thất bại do xác thực hoặc quyền truy cập, hãy cân nhắc một thao tác đọc nhẹ có timeout để kiểm tra cả đường truy cập cần thiết.

## 6. Phân biệt probe kết nối và kiểm tra service cụ thể

Một probe ở cấp DiscoveryClient thường kiểm tra khả năng hoạt động của discovery backend, không chứng minh một service cụ thể có instance khỏe.

Ví dụ:

- Probe Eureka thành công cho biết discovery client thực hiện được phép kiểm tra đã thiết kế với Eureka.
- Điều đó không chứng minh inventory-service có instance.
- Nó cũng không chứng minh từng instance của inventory-service trả HTTP 200.
- Nó không chứng minh database hoặc dịch vụ nghiệp vụ của provider đang khỏe.

Nếu cần kiểm tra service cụ thể, có thể gọi getInstances(serviceId) hoặc một health check riêng cho service đó. Tuy nhiên, không nên đưa danh sách hoặc toàn bộ instance của mọi service vào probe tổng quát nếu điều đó tái tạo chi phí cũ.

Một cách phân lớp:

| Thành phần | Nên kiểm tra | Ví dụ |
|---|---|---|
| Discovery client | Kết nối/khả năng đọc metadata discovery | Probe nhẹ |
| Service cần thiết cho ứng dụng | Có instance phù hợp hay không | getInstances cho serviceId cụ thể |
| Provider instance | Có nhận và xử lý request hay không | HTTP readiness/health endpoint |
| Ứng dụng consumer | Có đủ dependency để nhận request hay không | Readiness group |

Không biến health check của consumer thành một chuỗi gọi nghiệp vụ qua tất cả downstream service. Điều đó có thể tạo health-check storm và khiến sự cố của một dependency lan truyền thành việc restart hàng loạt ứng dụng.

## 7. Ví dụ tùy chỉnh DiscoveryClient

Đoạn mã sau minh họa ý tưởng một discovery client tự quản lý. Các phương thức truy vấn và đăng ký được rút gọn để tập trung vào probe:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

public class InventoryRegistryDiscoveryClient implements DiscoveryClient {

    private final RegistryApi registryApi;
    private final RegistryHealthProbe healthProbe;

    public InventoryRegistryDiscoveryClient(
            RegistryApi registryApi,
            RegistryHealthProbe healthProbe) {
        this.registryApi = registryApi;
        this.healthProbe = healthProbe;
    }

    @Override
    public String description() {
        return "Inventory registry discovery client";
    }

    @Override
    public List<ServiceInstance> getInstances(String serviceId) {
        return registryApi.findInstances(serviceId);
    }

    @Override
    public List<String> getServices() {
        return registryApi.listServiceNames();
    }

    @Override
    public void probe() {
        healthProbe.checkConnectivity();
    }
}
~~~

RegistryApi và RegistryHealthProbe là interface minh họa do ứng dụng định nghĩa. Trong hệ thống thực, không cần tự viết DiscoveryClient nếu Eureka, Consul hoặc ZooKeeper starter đã cung cấp implementation phù hợp. Chỉ tạo adapter tùy chỉnh khi có yêu cầu cụ thể và hiểu rõ cách Spring chọn bean DiscoveryClient.

Probe phải có timeout. Nếu request kiểm tra registry có thể treo lâu, Actuator endpoint cũng có thể bị chậm theo. Hãy đặt timeout nhỏ hơn ngân sách thời gian health check của orchestrator, nhưng đủ để chịu độ trễ mạng bình thường.

## 8. Khi dùng nhiều DiscoveryClient

Một ứng dụng có thể có nhiều DiscoveryClient, ví dụ một client cho registry chính và một client khác cho discovery phụ. Spring Cloud có thể tổng hợp chúng qua CompositeDiscoveryClient.

Khi đó cần xác định bean DiscoveryClient nào thực sự được inject vào DiscoveryClientHealthIndicator. Auto-configuration có thể tạo CompositeDiscoveryClient làm bean primary. CompositeDiscoveryClient tổng hợp danh sách service từ các delegate; nếu composite không override probe(), phương thức mặc định của interface sẽ gọi getServices() trên composite và vẫn thực hiện việc tổng hợp đó.

Việc một delegate tự override probe() không có nghĩa composite tự động gọi probe() của delegate. Muốn tránh liệt kê danh sách, composite cần có implementation probe phù hợp hoặc ứng dụng cần cấu hình đúng DiscoveryClient bean được health indicator sử dụng. Hãy kiểm tra source của đúng release train và đo lời gọi thực tế.

Một số điểm cần kiểm tra:

- Thứ tự của từng DiscoveryClient.
- CompositeDiscoveryClient đang được dùng thay cho implementation đơn lẻ hay không.
- Probe có được override ở delegate hay chỉ ở composite.
- Một backend discovery phụ bị lỗi có nên làm health tổng hợp DOWN không.
- Ứng dụng có thực sự cần mọi registry để phục vụ request hay chỉ một registry chính.

Không gộp trạng thái của các registry theo cách khiến một registry không được dùng làm ứng dụng mất readiness. Nếu nhiều backend đều bắt buộc, health tổng hợp nên phản ánh đúng điều kiện bắt buộc. Nếu backend phụ chỉ phục vụ một tính năng tùy chọn, nên hiển thị trạng thái riêng thay vì làm toàn bộ ứng dụng DOWN.

### Consul có một health indicator riêng

Khi Spring Cloud Consul được bật, ứng dụng có thể đồng thời có DiscoveryClientHealthIndicator và ConsulHealthIndicator. Hai indicator này có cấu hình khác nhau. ConsulHealthIndicator mặc định có thể đọc trạng thái leader và danh sách service; để bỏ phần truy vấn danh sách service, cấu hình:

~~~yaml
spring:
  cloud:
    consul:
      health-indicator:
        include-services-query: false
~~~

Property này chỉ điều khiển ConsulHealthIndicator. Nó không thay thế spring.cloud.discovery.client.health-indicator.use-services-query và không cấu hình DiscoveryClient.probe(). Khi điều tra health endpoint, xem contributor nào đang chiếm thời gian để chọn đúng property.

## 9. Tách discovery health khỏi liveness và readiness

Actuator health có thể được dùng bởi nhiều hệ thống: dashboard, Prometheus, load balancer, Kubernetes probe hoặc nền tảng triển khai. Không phải mọi health indicator đều nên điều khiển restart hoặc loại instance khỏi traffic.

- **Liveness** trả lời tiến trình có còn hoạt động và có thể tiếp tục chạy không.
- **Readiness** trả lời ứng dụng có sẵn sàng nhận request mới không.
- **Discovery health** phản ánh trạng thái của discovery client theo phép probe được cấu hình.
- **Business health** phản ánh dependency và khả năng thực hiện nghiệp vụ.

Nếu registry tạm thời mất kết nối nhưng ứng dụng vẫn xử lý được request đang có, không nhất thiết phải làm liveness DOWN. Restart liên tục trong lúc registry lỗi có thể làm tăng tải và kéo dài sự cố.

Nếu ứng dụng cần discovery để tìm downstream service cho mọi request, mất discovery có thể khiến readiness DOWN. Nếu service address đã được cache và ứng dụng có thể tiếp tục phục vụ an toàn, chính sách readiness có thể khác. Quyết định phải dựa trên hành vi thực tế, không chỉ dựa vào tên health indicator.

Khi dùng Spring Boot Actuator readiness group, hãy xem tên contributor thực tế tại endpoint health và cấu hình group theo nhu cầu. Không mặc định rằng discovery health luôn phải nằm trong readiness hoặc liveness.

## 10. Theo dõi chi phí trước và sau khi bật probe

Để biết thay đổi có hiệu quả, cần đo cùng một tập điều kiện trước và sau.

Các chỉ số nên quan sát:

| Chỉ số | Trước tối ưu | Sau tối ưu |
|---|---|---|
| Số lần getServices() | Đếm mỗi lần health check | Kỳ vọng giảm hoặc không xuất hiện trong probe |
| Số lần probe() | Có thể chưa dùng | Tăng theo chu kỳ health check |
| Latency health indicator | Đo p50/p95/p99 | So sánh cùng tải |
| Request đến registry | Đếm request liệt kê service | Xác định probe có tạo request nhẹ hay không |
| CPU và allocation | Đo khi danh sách service lớn | Kiểm tra mức giảm |
| Error rate | Lỗi từ getServices() | Lỗi từ phép probe mới |

Không gắn toàn bộ service name làm metric label nếu số lượng service lớn hoặc thay đổi liên tục; điều đó tạo high-cardinality metrics. Có thể ghi tổng số service trong log hoặc gauge riêng khi cần quan sát.

Probe cũng cần được giới hạn tần suất theo chu kỳ health check. Không gọi probe ở mọi request nghiệp vụ. Nếu nhiều replica cùng probe một thời điểm, cân nhắc jitter hoặc cơ chế cache trạng thái ngắn hạn phù hợp để tránh dồn tải vào registry.

## 11. Kiểm thử để chắc chắn getServices() không còn bị gọi

Một test đơn giản có thể xác nhận health indicator đi theo probe thay vì services query. Tạo DiscoveryClient giả có bộ đếm:

~~~java
import java.util.List;
import java.util.Collections;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

public class CountingDiscoveryClient implements DiscoveryClient {

    private final AtomicInteger servicesCalls = new AtomicInteger();
    private final AtomicInteger probeCalls = new AtomicInteger();

    @Override
    public String description() {
        return "Counting discovery client";
    }

    @Override
    public List<ServiceInstance> getInstances(String serviceId) {
        return Collections.emptyList();
    }

    @Override
    public List<String> getServices() {
        servicesCalls.incrementAndGet();
        throw new UnsupportedOperationException("getServices must not be used by this probe test");
    }

    @Override
    public void probe() {
        probeCalls.incrementAndGet();
    }

    public int servicesCalls() {
        return servicesCalls.get();
    }

    public int probeCalls() {
        return probeCalls.get();
    }
}
~~~

Test tích hợp cần khởi tạo health indicator với cấu hình use-services-query=false, đưa indicator qua sự kiện đăng ký instance để nó rời trạng thái UNKNOWN ban đầu, rồi gọi health() và xác nhận probeCalls tăng còn servicesCalls bằng 0. Nếu đang kiểm tra implementation registry thật, bổ sung integration test hoặc đo request backend để xác nhận probe không gián tiếp gọi API liệt kê service.

Không chỉ test rằng endpoint trả UP. Một implementation probe luôn trả thành công có thể làm test xanh nhưng không kiểm tra kết nối nào. Cần thêm test khi registry probe thất bại để xác nhận health indicator chuyển trạng thái tương ứng.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Đặt use-services-query=false nhưng latency không giảm | probe() mặc định vẫn gọi getServices() | Kiểm tra implementation và override probe nếu có thể |
| Health indicator luôn UP dù registry mất kết nối | probe không thực hiện thao tác kiểm tra thực sự | Dùng phép kiểm tra backend có timeout và phát lỗi |
| Health endpoint chậm khi registry lớn | getServices() lấy toàn bộ danh sách | Đo backend call, chuyển sang probe nhẹ nếu phù hợp |
| Probe thất bại trong lúc registry vẫn phục vụ | Probe phụ thuộc một endpoint hoặc quyền không cần thiết | Chọn thao tác đại diện đúng khả năng ứng dụng cần |
| Composite client vẫn tốn chi phí | Composite kế thừa probe mặc định và gọi getServices() tổng hợp | Kiểm tra bean primary và override probe ở đúng composite |
| Readiness DOWN kéo theo restart liên tục | Dùng discovery health làm liveness không phù hợp | Tách liveness, readiness và discovery status |
| Metric tăng cardinality | Gắn service name động vào label | Dùng metric tổng hợp, log hoặc phân nhóm có giới hạn |
| Probe tạo tải lớn tương tự query cũ | Probe vẫn liệt kê service hoặc bị gọi quá thường xuyên | Đo số lần gọi và chi phí backend, thêm timeout/jitter hợp lý |

## 13. Quy trình triển khai an toàn

Thực hiện theo thứ tự:

1. Ghi nhận Spring Boot và Spring Cloud release train đang dùng.
2. Xác nhận phiên bản Spring Cloud Commons hỗ trợ property use-services-query.
3. Xác định DiscoveryClient implementation thực tế được inject.
4. Kiểm tra probe() hiện tại có override hay đang gọi getServices().
5. Đo latency, số lần gọi backend và kích thước danh sách service ở chế độ hiện tại.
6. Cấu hình use-services-query=false trong môi trường thử nghiệm.
7. Nếu probe mặc định vẫn gọi getServices(), triển khai hoặc chọn implementation có probe nhẹ và có ý nghĩa.
8. Kiểm thử cả trường hợp registry hoạt động và registry lỗi.
9. So sánh p95/p99 latency, request backend, CPU và allocation.
10. Kiểm tra Actuator health, readiness và liveness để chắc chắn không đổi chính sách traffic ngoài ý muốn.
11. Triển khai theo từng nhóm instance và theo dõi lỗi trước khi mở rộng.

Nếu không thể override DiscoveryClient của thư viện đang dùng, có thể cân nhắc health indicator riêng hoặc adapter được hỗ trợ chính thức. Không tạo hai health indicator cùng kiểm tra một backend mà không kiểm soát thứ tự và trạng thái tổng hợp, vì điều đó có thể khiến Actuator vẫn chạy phép getServices() cũ.

## 14. Checklist hoàn tất

Trước khi coi việc tối ưu đã thành công, xác nhận:

1. Đã xác định rõ getServices() đang được gọi từ health indicator nào.
2. Property use-services-query=false được bind trong đúng phiên bản Spring Cloud Commons.
3. DiscoveryClient.probe() thực hiện phép kiểm tra nhẹ thật sự.
4. Probe không gọi lại getServices() một cách gián tiếp.
5. Probe có timeout và báo lỗi khi discovery backend không thể truy cập.
6. Business health và liveness không bị đánh đồng với discovery connectivity.
7. Health endpoint không liệt kê service names nếu không cần thiết.
8. CompositeDiscoveryClient và từng delegate đã được kiểm tra.
9. Đã đo số lần gọi, latency và tài nguyên trước/sau thay đổi.
10. Đã kiểm thử cả probe thành công và probe thất bại.

Điểm cốt lõi là: **getServices() trả về danh sách service, còn probe() nên kiểm tra khả năng hoạt động của discovery client với chi phí thấp.** Property use-services-query=false chỉ chuyển health indicator sang gọi probe; để thật sự giảm tải, implementation probe phải tránh liệt kê toàn bộ service và vẫn kiểm tra được điều kiện cần thiết.

## 15. Tài liệu tham khảo

- Spring Cloud Commons — Common Abstractions và DiscoveryClientHealthIndicator: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html
- Spring Cloud Commons — Configuration Properties: https://docs.spring.io/spring-cloud-commons/reference/configprops.html
- DiscoveryClient interface — mô tả default probe() và khả năng override: https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/DiscoveryClient.java
- EurekaDiscoveryClient — ví dụ implementation không override probe() trong source hiện hành: https://github.com/spring-cloud/spring-cloud-netflix/blob/main/spring-cloud-netflix-eureka-client/src/main/java/org/springframework/cloud/netflix/eureka/EurekaDiscoveryClient.java
- ConsulDiscoveryClient — ví dụ implementation override probe() để kiểm tra leader: https://github.com/spring-cloud/spring-cloud-consul/blob/main/spring-cloud-consul-discovery/src/main/java/org/springframework/cloud/consul/discovery/ConsulDiscoveryClient.java

