# Tránh làm tăng tải vì quá nhiều bên gọi kiểm tra sức khỏe

Một service chạy nhiều bản sao thường được nhiều ứng dụng khác gọi đến. Trong Spring Cloud LoadBalancer, mỗi ứng dụng caller có thể có `ServiceInstanceListSupplier` riêng và chủ động kiểm tra sức khỏe của các instance đích. Khi số lượng caller tăng, số request kiểm tra sức khỏe (*health-check probe*) cũng có thể tăng theo, kể cả khi lưu lượng nghiệp vụ chưa tăng tương ứng.

Vấn đề ở đây không chỉ là một probe tốn bao nhiêu tài nguyên. Vấn đề là **nhiều caller độc lập cùng kiểm tra một tập replica**, có thể ở cùng một tần suất hoặc thậm chí cùng thời điểm. Nếu không thiết kế cẩn thận, chính cơ chế định tuyến nhằm tránh instance không khỏe lại tạo thêm tải, làm gia tăng timeout và khiến hệ thống khó phục hồi.

Bài học thuộc chương **Sức khỏe bản sao** của module `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING`. Mục tiêu của module là nắm vững cân bằng tải phía client theo service ID, discovery, health check và chính sách định tuyến; đồng thời thực hành với `RestClient`, `WebClient`, OpenFeign, retry/timeout và quan sát lỗi. Bài này tập trung vào cách **giữ health check hữu ích nhưng không để health-check traffic trở thành nguồn gây quá tải**.

Sau bài học, bạn có thể:

- Giải thích vì sao health check thực hiện tại từng caller có nguy cơ khuếch đại lượng request.
- Ước tính tải probe theo số lượng caller, instance và chu kỳ kiểm tra.
- Phân biệt health check của Spring Cloud LoadBalancer với kiểm tra từ registry và nền tảng triển khai.
- Chọn một cơ chế kiểm tra sức khỏe phù hợp, giảm các lần kiểm tra trùng lặp.
- Cấu hình chu kỳ kiểm tra, endpoint và supplier chain theo khả năng của phiên bản Spring Cloud đang dùng.
- Đánh giá tải tăng đột biến, lỗi health-check hàng loạt và tác động tới retry/timeout.
- Thiết kế phép đo để kiểm chứng hiệu quả trước và sau khi tối ưu.

## 1. Health check phía client diễn ra như thế nào?

Giả sử `order-service` gọi `inventory-service` bằng địa chỉ logic:

~~~http
GET http://inventory-service/api/items/42
~~~

Spring Cloud LoadBalancer chọn một `ServiceInstance` từ danh sách được cung cấp bởi `ServiceInstanceListSupplier`. Khi cấu hình thêm cơ chế health check phía client, một supplier phù hợp, chẳng hạn `HealthCheckServiceInstanceListSupplier`, có thể kiểm tra endpoint sức khỏe của từng bản sao và chỉ cung cấp những instance đáp ứng chính sách.

Ví dụ có ba bản sao:

~~~text
inventory-service
  ├─ inv-a: 10.0.1.11:8080
  ├─ inv-b: 10.0.1.12:8080
  └─ inv-c: 10.0.1.13:8080
~~~

Một caller có thể gọi endpoint health của cả ba replica:

~~~mermaid
flowchart LR
    A["order-service caller"] --> LB["ServiceInstanceListSupplier"]
    LB --> HA["GET inv-a /actuator/health"]
    LB --> HB["GET inv-b /actuator/health"]
    LB --> HC["GET inv-c /actuator/health"]
    HA --> F["Danh sách instance khỏe"]
    HB --> F
    HC --> F
    F --> L["Spring Cloud LoadBalancer"]
    L --> R["Request nghiệp vụ tới instance được chọn"]
~~~

Các probe giúp phát hiện instance có endpoint không đáp ứng hoặc báo trạng thái không chấp nhận được. Tuy nhiên, với client-side health check, **mỗi tiến trình caller có thể thực hiện kiểm tra riêng**, thay vì cùng đọc một kết quả kiểm tra tập trung. Khi `order-service` có 200 replica, không thể giả định toàn bộ 200 replica dùng chung đúng một vòng probe.

Cũng cần phân biệt:

- **Tra cứu service instance**: lấy danh sách host/port từ discovery.
- **Health check**: đánh giá instance trong danh sách có đủ khỏe để trở thành ứng viên không.
- **Load balancing**: chọn một instance từ tập ứng viên.
- **HTTP request nghiệp vụ**: thực hiện công việc thật trên instance được chọn.

Đọc dữ liệu discovery nhanh hơn không có nghĩa số health probe tự động giảm. Ngược lại, health check dày hơn không làm registry trở nên cập nhật nhanh hơn nếu nguồn discovery vẫn chậm phản ánh thay đổi.

## 2. Khuếch đại tải khi số caller tăng

Giả sử có:

- `C` tiến trình caller, mỗi tiến trình có health-check supplier cho cùng một service.
- `I` instance đích được từng caller kiểm tra.
- `T` giây là khoảng thời gian giữa các vòng kiểm tra.
- Mỗi vòng kiểm tra mỗi instance một lần, không tính retry hoặc phát sinh do refresh.

Ta có thể ước tính **tốc độ probe trung bình toàn hệ thống**:

\[
R_{\text{probe}} \approx \frac{C \times I}{T}
\]

Đây là mô hình ước lượng để thiết kế năng lực, không phải cam kết rằng một implementation luôn gửi đúng một request trên mỗi instance ở mọi vòng. Cách supplier làm mới danh sách, thời điểm khởi tạo, cấu hình kiểm tra lặp và hành vi xử lý lỗi đều có thể làm tải thực tế khác đi.

### Ví dụ quy mô vừa

Giả sử có 240 caller, mỗi caller quan sát 8 instance, chu kỳ health check 10 giây:

\[
R_{\text{probe}} \approx \frac{240 \times 8}{10}=192
\]

Khoảng **192 probe/giây** được tạo ra trên toàn tập instance, chưa tính health check của ingress, registry, Kubernetes hoặc monitoring.

Nếu tăng chu kỳ lên 60 giây trong một môi trường cho phép:

\[
R_{\text{probe}} \approx \frac{240 \times 8}{60}=32
\]

Tốc độ probe trung bình giảm từ khoảng 192 xuống 32 request/giây, tức **giảm khoảng 6 lần**. Nhưng thời gian phát hiện một instance hỏng nhờ cơ chế polling này có thể dài hơn. Vì thế, tăng interval không phải giải pháp duy nhất: cần chọn nguồn health đáng tin cậy và hiểu khả năng chịu lỗi trong khoảng chuyển tiếp.

### Quy mô lớn hơn

| Số caller | Instance được probe/caller | Chu kỳ | Probe/giây ước tính |
|---:|---:|---:|---:|
| 20 | 4 | 30 giây | 2,7 |
| 100 | 10 | 30 giây | 33,3 |
| 240 | 8 | 10 giây | 192 |
| 240 | 8 | 60 giây | 32 |
| 1.000 | 20 | 10 giây | 2.000 |

Với nhiều service đích, hãy cộng tải ước tính theo từng cặp caller–service ID. Trên một instance đích, tốc độ probe trung bình đến từ nhóm 240 caller với interval 10 giây có thể xấp xỉ `240/10 = 24` request/giây, giả sử mọi caller đều kiểm tra instance đó.

Những con số này không bao gồm sự gia tăng do retry, thay đổi danh sách, các health checker khác hoặc việc nhiều caller đồng bộ lịch.

## 3. Tải trung bình khác với tải tăng đột biến

Phép tính ở trên lấy trung bình theo thời gian. Nó không cho biết các probe đến dàn đều hay dồn thành từng đợt.

Ví dụ, một đợt triển khai khởi động 200 caller gần như đồng thời. Nếu tất cả bắt đầu vòng health check đầu tiên ngay sau một khoảng `initial-delay` giống nhau, nhiều caller có thể gửi request đến cùng một instance trong một khoảng rất ngắn:

~~~mermaid
sequenceDiagram
    participant A as Caller A
    participant B as Caller B
    participant C as Caller C
    participant I as Inventory instance
    Note over A,C: Nhiều caller khởi động cùng đợt
    A->>I: GET /actuator/health
    B->>I: GET /actuator/health
    C->>I: GET /actuator/health
    I-->>A: 200
    I-->>B: 200
    I-->>C: 200
~~~

Ở quy mô hàng trăm caller, một endpoint đơn giản cũng có thể chịu đỉnh kết nối đáng kể. Khi health endpoint gọi các dependency đắt tiền, hiệu ứng còn mạnh hơn: nhiều probe từ caller có thể đồng thời đánh vào database, message broker hoặc hệ thống xác thực.

**Điều cần phân biệt:** tăng interval làm giảm *tốc độ trung bình*, nhưng không tự bảo đảm tránh được các đợt probe dồn cùng thời điểm.

Để giảm tính đồng bộ:

- Tránh khởi động tất cả caller hoặc refresh toàn bộ health checker cùng một thời điểm khi có thể.
- Nếu cần lập lịch tùy chỉnh, cân nhắc jitter để phân tán thời điểm probe.
- Giới hạn số lượng probe đồng thời tại nơi thực hiện hoặc nhận probe khi hệ thống có cơ chế hỗ trợ.
- Không tự giả định Spring Cloud LoadBalancer có sẵn một nút cấu hình jitter cho mọi phiên bản; chỉ dùng giải pháp mà version và implementation thực sự cung cấp.
- Đo request/giây ở độ phân giải đủ nhỏ để thấy đỉnh, thay vì chỉ xem trung bình 1 phút.

## 4. Phân biệt các nguồn thông tin sức khỏe

Không phải mọi quyết định “instance khỏe hay không” đều cần được kiểm tra lại bởi từng caller. Một hệ thống có thể đã sở hữu thông tin health từ nhiều lớp:

| Lớp | Ai thực hiện | Mục tiêu chính | Cần lưu ý |
|---|---|---|---|
| **Liveness probe** | Nền tảng vận hành, ví dụ Kubernetes | Quyết định khi nào nên khởi động lại container | Không đồng nghĩa sẵn sàng nhận traffic. |
| **Readiness probe** | Nền tảng vận hành | Quyết định instance có nên nằm trong tập endpoint phục vụ traffic | Có thể được phản ánh vào danh sách instance qua discovery adapter. |
| **Registry health/status** | Eureka, Consul hoặc cơ chế tương ứng | Đăng ký và công bố trạng thái service | Độ mới phụ thuộc heartbeat, lease, watch hoặc refresh. |
| **LoadBalancer health-check supplier** | Từng ứng dụng caller sử dụng supplier này | Bổ sung kiểm tra khả dụng của instance trước khi chọn | Có nguy cơ nhân số probe theo số caller. |
| **Timeout/circuit breaker** | Caller trên request nghiệp vụ | Hạn chế chờ lâu và phản ứng với lỗi gọi thật | Không thay thế hoàn toàn health hoặc discovery. |

Mỗi lớp có mục đích riêng. Ví dụ Kubernetes readiness có thể loại Pod khỏi endpoint được dùng cho traffic. Nếu discovery client của caller đã nhận danh sách chỉ gồm các endpoint ready, thêm một vòng HTTP health check từ mỗi caller có thể chỉ cung cấp ít giá trị tăng thêm trong khi tạo nhiều request phụ.

Ngược lại, nếu registry chỉ biết instance “đã đăng ký” nhưng không bảo đảm endpoint ứng dụng hoạt động, một cơ chế health check bổ sung có thể hữu ích.

**Câu hỏi thiết kế đầu tiên không phải “đặt interval bao nhiêu?” mà là “chúng ta đã có tín hiệu sức khỏe đáng tin cậy ở đâu?”**

## 5. Chọn một cơ chế kiểm tra chính, tránh lặp không cần thiết

Không có một phương án đúng cho mọi hệ thống. Hãy xem xét các trường hợp điển hình.

### Trường hợp A: Kubernetes và discovery đã chỉ cung cấp endpoint ready

Nếu client dùng một discovery adapter trả về danh sách endpoint đã qua readiness filtering và danh sách được cập nhật đủ nhanh, một lựa chọn hợp lý là để nền tảng xử lý readiness và **không bật thêm per-caller health-check supplier** trừ khi đã xác định rõ nhu cầu.

Ưu điểm: không nhân thêm HTTP probe từ mọi caller. Đổi lại, chất lượng lựa chọn phụ thuộc tín hiệu readiness, tốc độ cập nhật discovery và chính sách vận hành.

### Trường hợp B: Eureka hoặc Consul đã theo dõi health

Khi registry thực hiện kiểm tra hoặc nhận trạng thái phù hợp rồi cung cấp danh sách instance khả dụng, có thể dựa vào tín hiệu đó làm nguồn chính. Xác minh registry thực sự lọc hoặc đánh dấu trạng thái theo cách discovery client của ứng dụng hiểu được.

Không nên giả định “có Eureka” đồng nghĩa mọi lỗi ứng dụng được phát hiện tức thì. Heartbeat, lease expiration và registry refresh vẫn có độ trễ. Tùy yêu cầu phát hiện lỗi, có thể cần bổ sung timeout, retry có kiểm soát hoặc một health checker ở một phạm vi hẹp hơn.

### Trường hợp C: Discovery chỉ cung cấp địa chỉ, không có tín hiệu health đáng tin cậy

Trong một số môi trường dùng danh sách tĩnh hoặc discovery không kiểm tra khả dụng, health-check supplier phía caller có thể giảm lựa chọn instance chết. Khi ấy nên:

1. Giới hạn chu kỳ kiểm tra ở mức đáp ứng mục tiêu phát hiện lỗi.
2. Dùng health endpoint nhẹ, rõ nghĩa và dễ truy cập.
3. Cân nhắc số caller đang thực hiện probe.
4. Đo tỷ lệ lỗi do stale instance trước và sau khi bật cơ chế.
5. Kiểm tra hành vi khi danh sách healthy trở nên rỗng.

Một supplier phía caller **không phải là bộ kiểm tra sức khỏe dùng chung toàn hệ thống**. Để giảm probe thực sự ở quy mô lớn, có thể cần chuyển việc kiểm tra sang nguồn chia sẻ như registry hoặc nền tảng, nếu nguồn đó phù hợp.

## 6. Cấu hình HealthCheckServiceInstanceListSupplier

Khi xác định cần kiểm tra health phía client, có thể tạo supplier chain dùng `HealthCheckServiceInstanceListSupplier` thông qua builder của Spring Cloud LoadBalancer.

Ví dụ cấu hình riêng cho `inventory-service`:

~~~java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class InventoryHealthLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier serviceInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withHealthChecks()
                .build(context);
    }
}
~~~

Đăng ký cấu hình cho đúng service ID:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
    name = "inventory-service",
    configuration = InventoryHealthLoadBalancerConfiguration.class
)
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Cấu hình `InventoryHealthLoadBalancerConfiguration` nên nằm ngoài phạm vi component scan thông thường hoặc được loại khỏi scan. Nó được tham chiếu bởi `@LoadBalancerClient` để dùng trong LoadBalancer context của service ID tương ứng. Tránh để bean supplier riêng cho `inventory-service` trở thành bean áp dụng toàn cục.

Các phương thức builder và hình thức kiểm tra cụ thể còn tùy phiên bản Spring Cloud, discovery client và các dependency reactive/blocking phù hợp. Ví dụ nhằm minh họa cấu trúc: **source discovery → health-check decorator → tập ứng viên**. Không nên khai báo nhiều bean `ServiceInstanceListSupplier` cùng cạnh tranh trong một LoadBalancer context.

## 7. Điều chỉnh chu kỳ, độ trễ khởi đầu và health path

Spring Cloud LoadBalancer cung cấp nhóm cấu hình health check; với các phiên bản hỗ trợ, cấu hình minh họa như sau:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        initial-delay: 10s
        interval: 45s
        path:
          inventory-service: /actuator/health/readiness
~~~

Ý nghĩa:

- `initial-delay`: trì hoãn vòng kiểm tra đầu sau khi health-check supplier bắt đầu hoạt động.
- `interval`: khoảng thời gian giữa các vòng kiểm tra theo cơ chế của supplier.
- `path.inventory-service`: health path dành riêng cho service ID đích, thay vì dùng một path mặc định cho mọi service.

Đây là **giá trị minh họa**, không phải cấu hình tối ưu cho mọi hệ thống. Thuộc tính có hiệu lực khi health-check supplier thực sự được tạo và được phiên bản Spring Cloud tương ứng hỗ trợ; chỉ khai báo property không đồng nghĩa tự bật health check ở mọi ứng dụng.

Với Spring Boot Actuator, có thể bật health probes trong ứng dụng **đích** khi môi trường yêu cầu:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Một số lưu ý thực tế:

- `/actuator/health/readiness` phải tồn tại và truy cập được từ **caller** hoặc thành phần thực hiện probe.
- Nếu Actuator chạy ở management port tách biệt, hãy xác minh cơ chế health-check đang dùng có thực sự gọi đúng host và port; chỉ đổi `path` chưa chắc đủ.
- Nếu health endpoint yêu cầu xác thực, phải tính tới khả năng supplier gửi thông tin xác thực phù hợp; không mở một endpoint quản trị nhạy cảm ra Internet chỉ để health check chạy được.
- Khi dùng context path hoặc cấu hình endpoint khác, hãy kiểm tra URL kết quả thực tế.
- Path và các thuộc tính liên quan có thể khác giữa các dòng Spring Cloud; đối chiếu tài liệu của phiên bản đang triển khai trước khi sử dụng nguyên mẫu.

### Chọn interval theo yêu cầu phát hiện lỗi

Nếu health checker là nguồn phát hiện instance chết duy nhất, interval càng dài thì nguy cơ tiếp tục chọn instance lỗi càng kéo dài. Nếu registry đã có readiness signal cập nhật nhanh, poll thêm mỗi vài giây ở mọi caller có thể không mang lại giá trị tương xứng.

Hãy xác định một **mục tiêu phát hiện lỗi** trước, rồi lựa chọn interval và các chính sách bổ trợ, thay vì mặc định “càng nhanh càng tốt”.

## 8. Health endpoint phải rẻ và có ý nghĩa

Endpoint health có thể là nguyên nhân tạo tải lớn nhất nếu mỗi lần kiểm tra lại thực hiện truy vấn tốn kém.

Ví dụ một health endpoint bị thiết kế quá nặng có thể:

- Gọi database bằng truy vấn toàn bảng hoặc truy vấn không giới hạn.
- Gọi đồng thời nhiều downstream service để “đo sức khỏe của tất cả”.
- Mở kết nối mới tới broker hoặc database cho mỗi probe.
- Thực hiện yêu cầu ghi dữ liệu để kiểm tra khả năng tạo giao dịch.
- Gọi HTTP tới một hệ thống xác thực bên ngoài cho mọi lần kiểm tra.
- Tạo log lớn hoặc tính toán phức tạp mà không cần thiết.

Khi hàng trăm caller cùng probe, những thao tác này bị nhân lên và có thể gây **hiệu ứng dây chuyền**: chính request health làm dependency chậm, khiến health trả lỗi, rồi nhiều client loại thêm instance khỏi tập ứng viên.

### Readiness nên phản ánh khả năng phục vụ

Không nên cực đoan theo hướng endpoint “luôn trả 200” để rẻ. Nếu một dependency thực sự thiết yếu, trạng thái readiness cần phản ánh việc ứng dụng có thể phục vụ yêu cầu một cách an toàn.

Giải pháp là **chọn tín hiệu hiệu quả**:

- Dùng trạng thái readiness đã được ứng dụng duy trì và cập nhật trong vòng đời, thay vì thực hiện nhiều thao tác tốn kém trên mỗi HTTP GET.
- Dùng health indicator có timeout hợp lý và giới hạn số dependency được kiểm tra trực tiếp.
- Nếu cần kiểm tra sâu và tốn thời gian, cân nhắc chạy riêng theo lịch rồi công bố trạng thái gần nhất, với yêu cầu về độ mới được xác định rõ.
- Đừng để liveness và readiness sử dụng những dependency không phù hợp như nhau: một downstream chậm không nhất thiết là lý do restart toàn bộ tiến trình.

Health endpoint nên **không có side effect**, phản hồi ngắn gọn và tránh trả thông tin bí mật. Bảo vệ endpoint bằng network policy hoặc chính sách truy cập nội bộ thích hợp.

## 9. Phối hợp với cache và discovery refresh

Health-check supplier thường nhận danh sách instance từ một nguồn discovery hoặc từ một supplier khác. Nếu discovery snapshot đã cũ, health check có thể liên tục probe một instance mà registry thực tế đã gỡ.

Ngược lại, nếu một instance mới chưa xuất hiện trong snapshot của caller, health checker cũng không thể kiểm tra nó.

~~~text
Registry / discovery adapter
          |
          v
Danh sách ServiceInstance tại caller
          |
          v
HealthCheckServiceInstanceListSupplier
          |
          v
Các instance đang được coi là healthy
          |
          v
LoadBalancer chọn đích
~~~

Đừng nhầm hai loại “mới”:

1. **Discovery freshness:** caller nhìn thấy danh sách instance cập nhật đến mức nào.
2. **Health freshness:** trạng thái healthy của các instance hiện có được kiểm tra gần đây đến mức nào.

Tăng tần suất health check không tự cải thiện discovery freshness. Tăng tần suất registry refresh không tự bảo đảm endpoint luôn hoạt động.

Trong supplier chain, cache và health-check decorator cần được bố trí phù hợp với hướng dẫn và semantics của phiên bản sử dụng; không tự động bật cả hai lớp chỉ vì chúng tồn tại. Đặc biệt, khi discovery client đã duy trì registry snapshot, việc cache thêm ở LoadBalancer có thể kéo dài thời gian sử dụng instance cũ.

Nếu đã có health check tại registry hoặc nền tảng, việc tắt health check phía caller có thể giảm tải tốt hơn nhiều so với chỉ kéo dài interval.

## 10. Khởi động hàng loạt, autoscaling và jitter

Khi nhiều replica caller được tạo trong cùng một lần autoscale hoặc rolling deployment, chúng thường có thời điểm khởi động gần nhau. Nếu tất cả khởi tạo health-check supplier cùng lúc với một `initial-delay` giống nhau, thời điểm probe đầu có thể trùng nhau.

Một số chiến lược giảm đỉnh:

| Chiến lược | Lợi ích | Đánh đổi / lưu ý |
|---|---|---|
| Stagger rollout caller | Giảm số tiến trình bắt đầu probe đồng thời | Deploy/autoscale có thể kéo dài hơn |
| Initial delay phù hợp | Tránh probe ngay trong giai đoạn context chưa sẵn sàng | Chỉ trì hoãn vòng đầu; không tự tạo jitter |
| Jitter trong scheduler tùy chỉnh | Làm lệch pha các vòng probe | Cần implementation hoặc cấu hình thực sự hỗ trợ |
| Giới hạn concurrency | Tránh dồn quá nhiều kết nối tới health endpoint | Probe bị chờ, kết quả health có thể cập nhật muộn |
| Dựa vào health signal của registry | Giảm kiểm tra HTTP lặp tại mỗi caller | Phụ thuộc độ mới và độ tin cậy của registry |
| Interval dài hơn | Giảm tải trung bình | Có thể tăng thời gian phát hiện instance lỗi |

Không nên giả định rằng `initial-delay` là jitter. Nếu mọi caller đều có cùng độ trễ khởi đầu sau một đợt khởi động đồng loạt, các vòng kiểm tra vẫn có thể đồng bộ.

Ngoài ra, không nên tự động thêm retry cho từng probe chỉ để “chắc chắn”. Khi health endpoint đang quá tải, nhiều retry đồng thời có thể khiến đợt tải tăng mạnh hơn.

## 11. Timeout, retry và các vòng khuếch đại lỗi

Cần xem health-check traffic trong mối quan hệ với HTTP traffic nghiệp vụ.

Kịch bản nguy hiểm:

1. Một instance xử lý chậm vì quá tải.
2. Nhiều caller cùng gửi health probe vào instance đó.
3. Health probe cũng timeout hoặc trả trạng thái lỗi.
4. Các caller loại instance khỏi tập ứng viên.
5. Traffic nghiệp vụ tập trung sang những instance còn lại.
6. Các instance còn lại bị quá tải và bắt đầu trượt health check.

~~~mermaid
flowchart TD
    A["Instance A chậm"] --> B["Probe từ nhiều caller tăng độ trễ"]
    B --> C["Một số caller loại A"]
    C --> D["Traffic dồn sang B/C"]
    D --> E["B/C cũng quá tải"]
    E --> F["Health check của B/C thất bại"]
    F --> G["Tập ứng viên giảm thêm"]
    G --> D
~~~

Đây là vòng phản hồi xấu thường gặp khi health policy quá nhạy với dao động tạm thời.

Các biện pháp giảm nguy cơ gồm:

- Thiết kế endpoint health rẻ, ít phụ thuộc và có timeout rõ ràng.
- Không loại instance chỉ vì một tín hiệu tạm thời nếu hệ thống cần cơ chế chống dao động; khả năng giữ trạng thái, ngưỡng liên tiếp hoặc hysteresis phải được triển khai theo chính sách thực tế.
- Giới hạn retry và tránh retry dồn dập ở cả lớp probe và lớp HTTP nghiệp vụ.
- Phân biệt lỗi kết nối không thành công với lỗi nghiệp vụ trả `4xx`; không lấy mọi lỗi ứng dụng làm dấu hiệu toàn bộ instance đã chết.
- Ưu tiên cảnh báo và quan sát tải thay vì để mọi caller tự ra quyết định dựa trên một đo lường nhiễu.
- Bảo đảm timeout tổng thể không bị nhân lên vô hạn qua các tầng retry.

Spring Cloud LoadBalancer không tự động cung cấp đầy đủ các cơ chế như hysteresis, circuit breaker và retry budget chỉ bằng việc thêm `withHealthChecks()`. Nếu cần, phải thiết kế và cấu hình chúng ở thành phần phù hợp.

## 12. Khi nào nên tắt kiểm tra sức khỏe phía caller?

Có thể cân nhắc **không dùng per-caller health-check supplier** khi:

- Registry hoặc nền tảng đã cung cấp danh sách instance phản ánh readiness phù hợp.
- Discovery của caller cập nhật danh sách đủ nhanh so với mục tiêu khôi phục.
- Việc kiểm tra lại từng instance tại hàng trăm caller không cải thiện đáng kể tỷ lệ thành công.
- Phần lớn tải lên health endpoint đến từ những probe lặp lại.
- Hệ thống đã có timeout, retry có kiểm soát và cơ chế phản ứng với lỗi request thật.

Khi quyết định không bật health-check supplier, vẫn phải kiểm tra khả năng phục hồi thực tế. Một registry phản ánh trạng thái đúng nhưng cập nhật quá chậm có thể khiến nhiều request đi tới instance chết. Cách giải quyết có thể là cải thiện heartbeat/readiness/registry refresh, hoặc cân nhắc một cơ chế failover có giới hạn.

Nếu vẫn cần health check tại caller, nên tập trung vào **một nhóm service thật sự cần nó**, thay vì bật mặc định cho mọi service ID trong mọi ứng dụng.

## 13. Đo tải health check theo service và instance

Không thể đánh giá tối ưu nếu chỉ theo dõi tổng số request HTTP. Cần phân biệt request nghiệp vụ và request health.

Những phép đo nên có:

| Chỉ số | Ý nghĩa |
|---|---|
| `health_probe_requests_total` | Số probe thực hiện/nhận trong một khoảng thời gian |
| `health_probe_duration` | Độ trễ phản hồi probe |
| `health_probe_failures` | Probe timeout, lỗi kết nối hoặc báo không khỏe |
| `health_probe_in_flight` | Số probe đang xử lý đồng thời |
| `supplier_candidate_count` | Số instance được supplier cung cấp |
| `loadbalancer_no_instance` | Số lần không có instance khả dụng |
| HTTP `5xx`/timeout | Chất lượng giao tiếp nghiệp vụ thực tế |
| `readiness` transitions | Tần suất instance chuyển healthy/unhealthy |

Tên trên là **tên metric minh họa** để xây dựng dashboard; không có nghĩa mọi metric đều được Spring Cloud LoadBalancer hoặc Micrometer tự động cung cấp dưới tên đó. Hãy dùng các metric thực sự có từ Actuator/observation của ứng dụng, hoặc bổ sung instrumentation cần thiết.

Về cardinality, tránh dùng request ID làm metric label. Với service ID và instance ID có thể dùng nhãn có giới hạn theo mục tiêu quan sát, nhưng cần cân nhắc quy mô và vòng đời instance để không làm bùng nổ số chuỗi thời gian.

### Dự đoán trước và đối chiếu số đo

Giả sử có 240 caller, 8 instance, interval 10 giây:

~~~text
Ước tính trước: 240 × 8 / 10 = 192 probe/s
Sau đổi sang 60s: 240 × 8 / 60 = 32 probe/s
Mục tiêu: giảm khoảng 83% tải probe trung bình
~~~

Nếu đo được tải giảm ít hơn, có thể còn health check từ registry, Kubernetes, monitoring hoặc một supplier chain khác đang hoạt động. Nếu số probe vượt xa mô hình ước lượng, hãy tìm retry, nhiều context/caller, nhiều service ID hoặc các vòng refresh phụ.

**Không chỉ đo lượng probe.** Phải theo dõi đồng thời tỷ lệ request thành công, độ trễ phát hiện instance hỏng và độ trễ phục hồi khi instance trở lại.

## 14. Thực hành kiểm chứng trong môi trường local hoặc staging

Mục đích của thực hành là quan sát cơ chế khuếch đại và tác động của việc giảm probe, không dùng số liệu ví dụ làm cam kết cho production.

### Chuẩn bị

- Chạy hai hoặc ba replica `inventory-service`, mỗi replica có endpoint `/actuator/health/readiness` hoặc health path tương ứng.
- Chạy hai hoặc nhiều tiến trình caller `order-service` có `@LoadBalancerClient` và health-check supplier được cấu hình.
- Đảm bảo service discovery hoặc danh sách instance tĩnh chứa đủ host/port của các replica.
- Bật log hoặc metric ở health endpoint để đếm số probe đến mỗi instance.
- Nếu muốn tính cả request nghiệp vụ, dùng endpoint trả về `instanceId` để quan sát LoadBalancer chọn đích.

### Các bước

1. Cho mọi instance healthy, giữ cố định số caller và số replica.
2. Quan sát health request trong một cửa sổ đo đủ dài để thấy vài chu kỳ, ví dụ 5 phút.
3. Đối chiếu số probe thực tế với ước tính `C × I / T`.
4. Giữ nguyên số replica đích nhưng tăng số caller, ví dụ từ 2 lên 4; kiểm tra tải probe có xu hướng tăng hay không.
5. Giữ nguyên số caller, thay đổi interval trong staging; so sánh probe/giây, độ trễ và độ đỉnh.
6. Dừng một replica và quan sát thời gian từ lúc nó lỗi đến khi supplier không còn cung cấp nó.
7. Khôi phục replica rồi quan sát thời gian nó trở lại tập ứng viên.
8. Ghi lại tình huống danh sách trở nên rỗng và cách HTTP client xử lý.
9. Nếu nền tảng có readiness/registry health tin cậy, thử tắt health-check supplier phía caller và so sánh tổng probe cùng tỷ lệ lỗi nghiệp vụ.

Nếu dùng `SimpleDiscoveryClient` tĩnh, việc dừng instance **không tự xóa nó khỏi nguồn discovery**. Health-check supplier có thể đánh giá instance đó không khỏe, nhưng danh sách địa chỉ vẫn tồn tại trong cấu hình. Khi tắt per-caller health check, bạn cần một cơ chế khác để tránh chọn host đã chết.

### Bảng ghi nhận

| Kịch bản | Số caller | Chu kỳ | Probe/giây đo được | P95 health latency | Request nghiệp vụ lỗi |
|---|---:|---|---:|---|---|
| Trước tối ưu | 2 | 10s | Ghi sau thử nghiệm | Ghi sau thử nghiệm | Ghi sau thử nghiệm |
| Tăng caller | 4 | 10s | Ghi sau thử nghiệm | Ghi sau thử nghiệm | Ghi sau thử nghiệm |
| Giãn chu kỳ | 4 | 45s | Ghi sau thử nghiệm | Ghi sau thử nghiệm | Ghi sau thử nghiệm |
| Dựa vào registry readiness | 4 | Không bật per-caller check | Ghi sau thử nghiệm | Không áp dụng cho LB checker | Ghi sau thử nghiệm |

Bảng này chỉ là mẫu ghi dữ liệu; không có phép thử thực tế nào được ngầm khẳng định đã chạy.

## 15. Quy trình xử lý khi health endpoint bị gọi quá nhiều

~~~mermaid
flowchart TD
    A["Health endpoint có QPS/latency tăng cao"] --> B{"Probe đến từ đâu?"}
    B -- "Nhiều caller ứng dụng" --> C["Đếm caller × instance × interval"]
    B -- "Registry / platform / monitor" --> D["Kiểm tra từng health checker hiện có"]
    C --> E{"Per-caller check có bổ sung giá trị?"}
    E -- Không --> F["Dựa vào health signal chia sẻ nếu đủ tin cậy"]
    E -- Có --> G["Giảm tần suất, tránh đồng bộ, giới hạn chi phí"]
    D --> H["Loại bỏ kiểm tra trùng lặp không cần thiết"]
    F --> I["Đo lại tải và tỷ lệ lỗi"]
    G --> I
    H --> I
    I --> J{"Phát hiện lỗi và phục hồi còn đạt yêu cầu?"}
    J -- Không --> K["Điều chỉnh interval/discovery/timeout/health policy"]
    J -- Có --> L["Giữ cấu hình và giám sát"]
~~~

Các lỗi cấu hình thường gặp:

- Bật health-check supplier trên mọi caller trong khi registry đã có kết quả readiness tin cậy.
- Dùng interval quá ngắn so với nhu cầu phát hiện lỗi thực tế.
- Mọi caller khởi động đồng thời, dẫn tới các đợt probe cùng pha.
- Một health endpoint thực hiện truy vấn hoặc lời gọi downstream tốn kém cho mỗi probe.
- Bật cả health check của nền tảng và per-caller mà không tính tổng tải.
- Hiểu nhầm `initial-delay` là cơ chế jitter.
- Không có timeout hợp lý cho probe, khiến nhiều kết nối chờ lâu.
- Bật retry dồn dập khi health endpoint đang không đáp ứng.
- Đặt health path sai hoặc dùng management port không thể truy cập, khiến nhiều instance bị đánh dấu không khỏe dù ứng dụng vẫn hoạt động.
- Xem việc giảm số health probe là thành công mà không đo ảnh hưởng đến tỷ lệ lỗi nghiệp vụ.

## 16. Checklist trước khi triển khai ở quy mô lớn

| Câu hỏi kiểm tra | Điều cần có |
|---|---|
| Có bao nhiêu caller và replica đích? | Ước tính `C × I / T` theo từng service ID |
| Ai đang phát health probe? | Danh sách rõ ràng: platform, registry, LB caller, monitoring |
| Nguồn health chính có đủ đáng tin cậy? | Kiểm thử readiness và độ trễ cập nhật discovery |
| Có nhất thiết bật per-caller supplier? | Lý do cụ thể và lợi ích đo được |
| Endpoint health có nhẹ không? | Không tạo tải downstream lớn trên mỗi lần kiểm tra |
| Chu kỳ và initial delay hợp lý? | Giá trị phù hợp mục tiêu phát hiện lỗi và tải cho phép |
| Có nguy cơ đồng bộ lịch? | Đã đo QPS đỉnh và cân nhắc stagger/jitter |
| Supplier có gắn đúng service ID? | `@LoadBalancerClient` và phạm vi bean được kiểm chứng |
| Health path và management port đúng? | Caller truy cập được và có chính sách bảo mật phù hợp |
| Có retry/timeout và fallback rõ ràng? | Không tạo vòng khuếch đại lỗi hoặc retry vô hạn |
| Khi toàn bộ instance unhealthy? | Hành vi no-instance có thể dự đoán và được quan sát |
| Đã đo trước và sau tối ưu? | Probe QPS, P95, error rate, detection/recovery time |

## 17. Tổng kết

- Health-check supplier phía client có thể thực hiện probe từ **từng caller** đến **nhiều instance** của service đích. Tải trung bình có thể tăng xấp xỉ theo `số caller × số instance / chu kỳ`.
- Khi nhiều caller khởi động đồng thời, probe còn có thể **dồn thành đỉnh**; tăng interval không tự tạo jitter.
- Cần phân biệt health check của Spring Cloud LoadBalancer với readiness/liveness của nền tảng và tín hiệu từ discovery registry.
- Nếu registry hoặc nền tảng đã cung cấp health signal đủ tin cậy, **tránh bật lại một vòng per-caller health check không cần thiết**.
- Khi thực sự cần `HealthCheckServiceInstanceListSupplier`, hãy dùng endpoint nhẹ, interval phù hợp, phạm vi service đúng và đánh giá độ trễ phát hiện lỗi.
- Cache, health, timeout và retry giải quyết các vấn đề khác nhau; phối hợp không đúng có thể tạo nhiều request thừa hoặc vòng khuếch đại quá tải.
- Một tối ưu tốt phải giảm tải kiểm tra **mà không làm xấu đi khả năng phát hiện instance lỗi, phục hồi và tỷ lệ thành công của request nghiệp vụ**.

Khi cân nhắc toàn bộ hệ thống thay vì chỉ một caller, bạn sẽ biết lúc nào nên dựa vào health signal chia sẻ, lúc nào nên giữ kiểm tra sức khỏe phía client, và cách kiểm soát số lượng probe để Spring Cloud LoadBalancer định tuyến ổn định mà không tự tạo thêm áp lực lên các service đích.

