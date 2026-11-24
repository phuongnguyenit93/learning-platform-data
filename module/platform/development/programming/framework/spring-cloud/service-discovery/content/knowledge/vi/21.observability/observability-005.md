# Theo dõi nhịp báo sống, kiểm tra sức khỏe và dữ liệu quá hạn

Trong Spring Cloud Service Discovery, registry giúp consumer tìm instance theo service ID. Tuy nhiên, một bản ghi trong registry không tự chứng minh instance vẫn đang chạy hoặc có thể phục vụ request. Instance có thể đã dừng nhưng bản ghi vẫn còn; instance có thể đã phục hồi nhưng consumer vẫn giữ cache cũ; hoặc heartbeat vẫn đến đều trong khi endpoint nghiệp vụ đã lỗi.

Để quan sát discovery đáng tin cậy, cần theo dõi riêng ba tín hiệu: nhịp báo sống (heartbeat/lease), kết quả kiểm tra sức khỏe (health check) và độ mới của dữ liệu registry/cache. Bài này trình bày cách đọc các tín hiệu đó với Eureka và Consul, cách đo độ trễ cập nhật, xây dựng cảnh báo và điều tra bản ghi quá hạn.

## 1. Phân biệt heartbeat, health check và registry freshness

Ba khái niệm này trả lời các câu hỏi khác nhau:

| Tín hiệu | Câu hỏi | Cơ chế điển hình |
|---|---|---|
| Heartbeat / lease renewal | Registry có còn nhận được tín hiệu từ instance không? | Eureka client gửi heartbeat; Consul TTL check nhận heartbeat |
| Health check | Instance có đáp ứng tiêu chí sức khỏe đã cấu hình không? | Consul Agent gọi HTTP/TCP/script check; Actuator health indicator |
| Registry freshness | Consumer đang nhìn thấy dữ liệu được cập nhật gần đây đến đâu? | Registry response cache, client fetch cache, LoadBalancer cache |

Ví dụ, JVM có thể vẫn gửi heartbeat đến Eureka nhưng database đã mất kết nối và ứng dụng không còn sẵn sàng xử lý request. Khi đó heartbeat vẫn tốt nhưng health có thể xấu.

Ngược lại, ứng dụng đã phục hồi và endpoint health trả UP, nhưng Consul Agent chưa chạy lần kiểm tra tiếp theo hoặc consumer chưa refresh cache. Registry/client vẫn có thể hiển thị trạng thái cũ trong một khoảng thời gian.

Vì vậy, không dùng một tín hiệu duy nhất để kết luận service khỏe. Cần kết hợp heartbeat, health, registration state, thời điểm cập nhật và khả năng gọi thực tế từ consumer.

## 2. Heartbeat và lease trong Eureka

Eureka Client đăng ký instance với Eureka Server rồi gửi heartbeat định kỳ để gia hạn lease. Các giá trị mặc định thường dùng:

| Thuộc tính | Giá trị mặc định thường gặp | Vai trò |
|---|---:|---|
| eureka.instance.lease-renewal-interval-in-seconds | 30 giây | Chu kỳ client gửi heartbeat |
| eureka.instance.lease-expiration-duration-in-seconds | 90 giây | Thời gian server chờ heartbeat trước khi lease hết hạn |
| eureka.client.registry-fetch-interval-seconds | 30 giây | Chu kỳ client tải registry |
| eureka.server.response-cache-update-interval-ms | 30000 ms | Chu kỳ cập nhật response cache của server |

Giá trị thực tế phụ thuộc phiên bản và cấu hình của ứng dụng. Khi điều tra, hãy kiểm tra cấu hình hiệu lực ở cả client và server, không chỉ đọc file YAML trong repository.

Ví dụ cấu hình client:

    eureka:
      instance:
        lease-renewal-interval-in-seconds: 30
        lease-expiration-duration-in-seconds: 90
      client:
        registry-fetch-interval-seconds: 30

Heartbeat trả lời việc server còn nhận được tín hiệu từ client. Nó không thay thế health check của ứng dụng. Nếu cần trạng thái sức khỏe Spring Boot được phản ánh vào Eureka, có thể bật health check integration:

    eureka:
      client:
        healthcheck:
          enabled: true

Đặt thuộc tính này trong application.yml hoặc cấu hình ứng dụng tương ứng để trạng thái health được khởi tạo cùng ApplicationContext. Hành vi chi tiết phụ thuộc phiên bản Spring Cloud Netflix và HealthCheckHandler đang sử dụng.

## 3. Self-preservation ảnh hưởng việc phát hiện dữ liệu cũ

Eureka có cơ chế self-preservation nhằm tránh xóa hàng loạt instance khi server nhận ít heartbeat hơn dự kiến. Thiếu heartbeat có thể do nhiều instance thật sự chết, nhưng cũng có thể do network partition, tải cao hoặc server tạm thời không nhận được heartbeat.

Khi self-preservation kích hoạt, Eureka có thể tạm dừng eviction. Vì vậy, instance đã ngừng hoạt động vẫn có thể tồn tại trong registry lâu hơn lease expiration dự kiến.

Một số thuộc tính liên quan:

    eureka:
      server:
        enable-self-preservation: true
        renewal-percent-threshold: 0.85
        expected-client-renewal-interval-seconds: 30

Không nên coi instance còn trong Eureka là bằng chứng instance đang sống nếu server đang self-preservation. Hãy theo dõi trạng thái self-preservation, số heartbeat nhận được so với số dự kiến và log eviction.

Không tắt self-preservation chỉ để làm dashboard xóa instance nhanh hơn. Trong môi trường production, cơ chế này bảo vệ registry khi có sự cố mạng diện rộng. Nếu thử nghiệm thay đổi chu kỳ heartbeat, phải đồng bộ expected-client-renewal-interval-seconds ở server và đo ảnh hưởng trước khi triển khai.

## 4. Health check trong Consul

Consul Agent quản lý các health check gắn với service. Với HTTP check, agent chủ động gọi endpoint theo interval đã khai báo. Một cấu hình Spring Cloud Consul thường dùng Actuator:

    management:
      endpoints:
        web:
          exposure:
            include: health,info
      endpoint:
        health:
          show-details: never

    spring:
      application:
        name: inventory-service
      cloud:
        consul:
          discovery:
            register: true
            register-health-check: true
            health-check-path: /actuator/health
            health-check-interval: 10s
            health-check-timeout: 3s
            query-passing: true

Consul HTTP check thường diễn giải mã phản hồi như sau:

| HTTP response | Trạng thái Consul |
|---|---|
| 2xx | passing |
| 429 | warning |
| Mã khác, lỗi kết nối hoặc timeout | critical |

Consul Agent thực hiện request từ vị trí mạng của agent. Endpoint có thể hoạt động khi gọi từ máy host nhưng thất bại khi agent ở container hoặc subnet khác. Vì vậy, hãy kiểm tra từ đúng network namespace của Consul Agent.

Thuộc tính query-passing=true yêu cầu Spring Cloud Consul chỉ lấy các instance có check passing trong truy vấn health service. Nếu không bật, danh sách discovery có thể bao gồm các trạng thái khác passing tùy API và cách truy vấn.

## 5. TTL check và heartbeat chủ động trong Consul

Ngoài HTTP/TCP/script check, Consul hỗ trợ TTL check. Với TTL, ứng dụng hoặc thành phần tích hợp chủ động gửi heartbeat tới Consul Agent để gia hạn trạng thái check.

Spring Cloud Consul có thể bật heartbeat TTL:

    spring:
      cloud:
        consul:
          discovery:
            heartbeat:
              enabled: true
              ttl: 30s

Với TTL check, ứng dụng phải cập nhật trạng thái đúng hạn. Nếu agent không nhận được heartbeat trước khi TTL hết, check chuyển sang critical. TTL không giống HTTP health-check-timeout:

- TTL là thời hạn mà Consul chờ heartbeat tiếp theo.
- health-check-timeout là thời gian tối đa chờ một lần gọi HTTP check.
- health-check-interval là khoảng cách giữa các lần agent chủ động gọi endpoint.

Chọn TTL có biên dự phòng so với chu kỳ heartbeat, tính cả scheduler delay, JVM pause và network jitter. Nếu TTL quá ngắn, một lần GC pause hoặc mạng chậm có thể làm instance khỏe chuyển critical.

TTL heartbeat chỉ xác nhận thành phần gửi heartbeat vẫn có thể giao tiếp với agent. Nếu heartbeat được gửi bởi một scheduler độc lập với phần xử lý request, nó có thể tiếp tục chạy dù API nghiệp vụ đã lỗi. Muốn kiểm tra khả năng phục vụ, cần health check phản ánh đúng dependency và trạng thái ứng dụng.

## 6. Health indicator và readiness của Spring Boot

Spring Boot Actuator tổng hợp các HealthIndicator để tạo trạng thái health. Một số indicator kiểm tra datasource, disk space hoặc dependency tích hợp; ứng dụng cũng có thể tạo indicator riêng.

Các endpoint thường dùng:

    /actuator/health
    /actuator/health/liveness
    /actuator/health/readiness

Liveness cho biết tiến trình có thể tiếp tục chạy hay cần restart. Readiness cho biết ứng dụng có nên nhận traffic mới không. Hai tín hiệu không nên bị gộp:

- Database tạm thời lỗi có thể khiến readiness DOWN nếu database thiết yếu cho request.
- Liveness thường không nên phụ thuộc mọi dịch vụ bên ngoài, tránh restart dây chuyền khi dependency có sự cố.
- Khi bắt đầu drain có kế hoạch, readiness có thể chuyển REFUSING_TRAFFIC trong khi liveness vẫn CORRECT.

Health endpoint cần nhẹ và có timeout hữu hạn. Không nên gọi một chuỗi nhiều service hoặc chạy truy vấn nặng trong mỗi lần Consul Agent kiểm tra; điều đó có thể tạo thêm tải và làm chính health check gây ra sự cố.

Giữ show-details ở mức phù hợp và không expose thông tin kết nối, secret hoặc dữ liệu nhạy cảm ra mạng công khai.

## 7. Bản ghi quá hạn và những dạng stale data

Dữ liệu quá hạn không chỉ có nghĩa một instance đã chết nhưng vẫn còn trong registry. Có nhiều dạng khác nhau:

| Dạng stale data | Ví dụ | Nguyên nhân thường gặp |
|---|---|---|
| Stale registration | Instance đã dừng nhưng bản ghi vẫn còn | Shutdown không deregister, lease chưa hết hạn, self-preservation |
| Stale health status | Ứng dụng đã hồi phục nhưng check vẫn critical | Chưa tới lần check tiếp theo, agent lỗi hoặc endpoint vẫn bị chặn |
| Stale client cache | Registry đã cập nhật nhưng consumer vẫn thấy instance cũ | Registry fetch interval hoặc client cache |
| Stale load-balancer cache | Discovery client đã có dữ liệu mới nhưng request vẫn chọn instance cũ | Cache/list supplier của LoadBalancer |
| Orphan catalog record | Catalog còn service nhưng agent/workload nguồn đã mất | Node chết, agent không còn đồng bộ, deregister thất bại |
| Duplicate registration | Một service có nhiều instance ID cũ và mới | Instance ID thay đổi, deployment chồng lấn hoặc deregister thiếu |

Cần xác định stale data nằm ở lớp nào trước khi xóa bản ghi. Nếu chỉ xóa Catalog nhưng agent hoặc orchestrator vẫn sở hữu registration, service có thể xuất hiện lại. Nếu registry đã đúng nhưng consumer cache chưa refresh, xóa registration thêm lần nữa không giải quyết nguyên nhân.

## 8. Theo dõi độ mới của dữ liệu qua từng lớp

Một luồng discovery có nhiều lớp cập nhật:

    Service instance
       |
       | heartbeat / health check
       v
    Consul Agent hoặc Eureka Server
       |
       | catalog / registry update
       v
    Registry response cache
       |
       | client fetch / discovery query
       v
    DiscoveryClient cache
       |
       | supplier/cache refresh
       v
    Spring Cloud LoadBalancer
       |
       v
    Request của consumer

Mỗi lớp có thể giữ dữ liệu cũ trong một khoảng thời gian. Để đo freshness, cần ghi nhận các mốc:

- Thời điểm instance khởi động và đăng ký.
- Thời điểm heartbeat thành công gần nhất.
- Thời điểm health check gần nhất và trạng thái trả về.
- Thời điểm registry ghi nhận trạng thái mới.
- Thời điểm consumer lần đầu nhìn thấy thay đổi.
- Thời điểm request cuối cùng được gửi tới instance đã lỗi.

Có thể định nghĩa các chỉ số dẫn xuất:

- Heartbeat age: thời gian hiện tại trừ thời điểm heartbeat thành công gần nhất.
- Health-check age: thời gian hiện tại trừ thời điểm check gần nhất.
- Registry propagation delay: thời điểm consumer nhìn thấy thay đổi trừ thời điểm registry ghi nhận thay đổi.
- Stale selection count: số request được định tuyến tới instance đã được xác nhận không còn phục vụ.
- Orphan registration age: thời gian bản ghi không có owner/agent hợp lệ vẫn tồn tại.

Các chỉ số này giúp phân biệt phát hiện sự cố chậm với propagation chậm.

## 9. Metrics nên theo dõi

Có thể chia metrics thành bốn nhóm:

| Nhóm | Metrics gợi ý | Ý nghĩa |
|---|---|---|
| Heartbeat/lease | Heartbeat success, heartbeat failure, heartbeat age, lease expiry | Client còn duy trì registration không |
| Health | Check status theo passing/warning/critical, check duration, check failure count | Instance có đạt tiêu chí sức khỏe không |
| Discovery | Lookup count, lookup error, lookup latency, instance count trả về | Consumer tra cứu registry có thành công không |
| Freshness/routing | Registry propagation delay, cache age, request tới instance stale | Dữ liệu có đủ mới để định tuyến không |

Tên metric cụ thể phụ thuộc exporter và phiên bản. Các tên ở bảng là khái niệm cần instrument, không phải tên metric mặc định được bảo đảm có sẵn trong mọi phiên bản Spring Cloud.

Với Micrometer, có thể tạo metric tùy chỉnh cho số lần lookup và lỗi:

    import io.micrometer.core.instrument.MeterRegistry;
    import org.springframework.stereotype.Component;

    @Component
    public class DiscoveryMetrics {

        private final MeterRegistry registry;

        public DiscoveryMetrics(MeterRegistry registry) {
            this.registry = registry;
        }

        public void recordLookup(String provider, String serviceId) {
            registry.counter(
                    "discovery.lookup",
                    "provider", provider,
                    "service", serviceId
            ).increment();
        }

        public void recordLookupFailure(String provider, String serviceId) {
            registry.counter(
                    "discovery.lookup.failure",
                    "provider", provider,
                    "service", serviceId
            ).increment();
        }

        public void recordLookupLatency(
                String provider,
                String serviceId,
                Runnable lookup) {
            registry.timer(
                    "discovery.lookup.duration",
                    "provider", provider,
                    "service", serviceId
            ).record(lookup);
        }
    }

Đây là ví dụ instrument tại lớp gọi; cần tích hợp vào code path thực tế và tránh tạo metric chỉ khi có thao tác mà không ghi nhận kết quả. Có thể bổ sung Timer cho health-check duration và Gauge cho số instance theo service/status.

Không đưa instance ID, IP, request ID hoặc user ID có cardinality cao vào metric label nếu số lượng có thể tăng không giới hạn. Những giá trị chi tiết phù hợp hơn với log có cấu trúc hoặc trace attribute. Giữ label ở tập hữu hạn như provider, service, status và environment.

## 10. Logs và traces để điều tra stale registration

Metrics cho biết có vấn đề và mức độ ảnh hưởng; log và trace giúp tìm nguyên nhân.

Log nên có các trường:

- provider: eureka hoặc consul.
- service_id và instance_id.
- node hoặc datacenter nếu provider hỗ trợ.
- operation: register, heartbeat, health_check, lookup, status_change hoặc deregister.
- status_before và status_after.
- endpoint/host/port đã công bố, sau khi loại bỏ thông tin nhạy cảm.
- duration_ms, result và error_type.
- timestamp và trace/correlation ID nếu thao tác nằm trong request quản trị.

Ví dụ log có cấu trúc:

    {
      "event": "discovery_health_check",
      "provider": "consul",
      "service_id": "inventory-service",
      "instance_id": "inventory-1",
      "status": "critical",
      "duration_ms": 3000,
      "reason": "timeout"
    }

Không ghi ACL token, password, URI có credential hoặc health detail chứa dữ liệu nhạy cảm.

Tracing hữu ích khi muốn liên kết một request thất bại với instance đã chọn. Thêm service ID, instance ID và endpoint đã chọn vào span attribute có kiểm soát. Heartbeat định kỳ không nhất thiết tự có trace; nếu cần theo dõi, instrument riêng các thao tác quản trị hoặc client call và tránh tạo một trace cho mỗi heartbeat với tần suất quá lớn.

## 11. Dashboard quan sát discovery

Một dashboard vận hành nên trả lời được bốn câu hỏi:

1. Có bao nhiêu instance được đăng ký theo service?
2. Có bao nhiêu instance passing, warning, critical hoặc OUT_OF_SERVICE?
3. Heartbeat và health check gần nhất đã xảy ra khi nào?
4. Consumer đang nhận danh sách instance nào và request thực tế được gửi tới đâu?

Có thể bố trí các panel:

| Panel | Nội dung | Cảnh báo cần quan sát |
|---|---|---|
| Instance inventory | Số instance theo service và trạng thái | Số instance passing giảm đột ngột |
| Heartbeat age | Tuổi heartbeat/lease gần nhất | Tuổi vượt ngưỡng lease dự kiến |
| Health check | Trạng thái và thời gian phản hồi | Critical liên tục hoặc check duration tăng |
| Registry freshness | Thời điểm cập nhật registry và consumer cache | Propagation delay tăng |
| Discovery lookup | Tỷ lệ lỗi và latency | Lookup error tăng hoặc danh sách rỗng |
| Routing | Request theo instance và lỗi kết nối | Consumer vẫn gọi instance stale |

Dashboard nên cho phép lọc theo environment, provider, service ID và datacenter. Không trộn dữ liệu dev/test/prod trong cùng một panel mà không có nhãn môi trường rõ ràng.

## 12. Xây dựng cảnh báo có ý nghĩa

Cảnh báo cần phản ánh tác động dịch vụ thay vì chỉ báo một heartbeat trễ đơn lẻ.

Ví dụ chính sách:

- Heartbeat age cao: cảnh báo khi tuổi heartbeat vượt một tỷ lệ đáng kể của lease expiration và kéo dài qua nhiều lần đánh giá.
- Critical kéo dài: cảnh báo khi check critical liên tục quá khoảng thời gian phục hồi bình thường của service.
- Thiếu instance khỏe: cảnh báo khi số instance passing thấp hơn capacity tối thiểu của service.
- Discovery lookup lỗi: cảnh báo khi tỷ lệ lỗi hoặc latency vượt SLO.
- Stale routing: cảnh báo khi request tiếp tục tới instance đã bị xác nhận critical hoặc deregister.
- Orphan record: cảnh báo khi registration không có agent/workload owner trong thời gian dài.

Với Eureka, khi self-preservation hoạt động, cần cảnh báo riêng về trạng thái đó và so sánh heartbeat nhận được với số dự kiến. Không nên tạo cảnh báo xóa instance chỉ từ việc lease đã quá hạn nếu server đang chủ động bảo vệ registry.

Với Consul, theo dõi thời gian check ở critical và cấu hình DeregisterCriticalServiceAfter nếu muốn tự động dọn service lỗi kéo dài. Critical timeout là thời gian giữ registration trước khi deregister; nó không phải thời gian chờ của một lần HTTP health check.

## 13. Điều tra instance lỗi nhưng vẫn xuất hiện trong discovery

Khi consumer báo vẫn nhận instance không còn hoạt động, hãy điều tra theo thứ tự:

1. Xác định instance chính xác: lấy service ID, instance ID, host, port, node và datacenter từ kết quả consumer.
2. Kiểm tra registry: xem trạng thái hiện tại trên Eureka hoặc Consul, thời điểm cập nhật và health check.
3. Kiểm tra heartbeat: xác định heartbeat gần nhất và lease còn hiệu lực hay đã hết hạn.
4. Kiểm tra self-preservation: với Eureka, xác định server có tạm dừng eviction hay không.
5. Kiểm tra agent: với Consul, so sánh /v1/agent/services và /v1/agent/checks với Catalog.
6. Kiểm tra client cache: gọi discovery từ consumer và so sánh với registry server.
7. Kiểm tra LoadBalancer: xác định cache hoặc supplier nào còn giữ instance.
8. Kiểm tra đường mạng: gọi trực tiếp từ consumer tới host/port được công bố để phân biệt stale registry với route lỗi.
9. Xác định owner: kiểm tra ứng dụng, Consul Agent, file cấu hình hoặc orchestrator nào còn có thể đăng ký lại instance.
10. Chỉ dọn bản ghi sau khi xác nhận: dùng deregister đúng nguồn sở hữu và theo dõi để chắc chắn record không xuất hiện lại.

Với Consul, có thể dùng các API đọc:

    GET /v1/agent/services
    GET /v1/agent/checks
    GET /v1/catalog/service/inventory-service
    GET /v1/health/service/inventory-service?passing

So sánh local agent với catalog giúp phát hiện registration còn trên agent hay chỉ còn trong catalog. Nếu agent vẫn sở hữu registration, xóa catalog trực tiếp có thể khiến agent đồng bộ và tạo lại record.

## 14. Điều tra instance đã hồi phục nhưng vẫn bị loại

Trường hợp ngược lại cũng thường xảy ra: ứng dụng đã khỏe nhưng consumer không thấy instance.

Kiểm tra:

- Endpoint health đã trả HTTP 2xx hoặc trạng thái UP chưa?
- Consul Agent đã chạy lần check tiếp theo chưa?
- Nếu dùng TTL, ứng dụng đã gửi heartbeat pass tới agent chưa?
- Service có đang ở maintenance mode hoặc OUT_OF_SERVICE không?
- Eureka client đã gửi heartbeat/health status mới chưa?
- Consumer đã fetch registry mới chưa?
- query-passing có đang lọc instance vì một check khác vẫn warning/critical không?
- Cache của LoadBalancer đã được refresh chưa?

Không khôi phục traffic chỉ dựa vào việc process đã chạy. Cần xác nhận readiness, registry status và request thực tế trước khi cho instance trở lại pool.

## 15. Phân biệt dữ liệu cũ với truy vấn không lọc health

Một số trường hợp nhìn giống stale data nhưng nguyên nhân là truy vấn không yêu cầu lọc instance khỏe.

Với Spring Cloud Consul, query-passing mặc định là false. Khi không bật, kết quả có thể chứa service instance có health check warning hoặc critical tùy kiểu truy vấn. Nếu ứng dụng chỉ muốn dùng instance passing, hãy bật query-passing và kiểm tra endpoint Health API mà provider sử dụng.

Với Eureka, client có registry cache cục bộ. Instance có thể còn xuất hiện trong cache trước lần fetch tiếp theo. Ngoài ra, self-preservation có thể làm server giữ lease đã hết hạn trong sự cố mạng. Cần phân biệt server registry state với client cache state.

Do đó, khi nhìn thấy instance lỗi, hãy kiểm tra cả trạng thái check và cách truy vấn. Đừng kết luận registry stale chỉ từ một danh sách chưa lọc.

## 16. Thực hành quan sát heartbeat và dữ liệu quá hạn

Có thể thực hiện một thí nghiệm có kiểm soát với hai instance inventory-service:

1. Khởi động Eureka hoặc Consul và đăng ký hai instance.
2. Ghi lại service ID, instance ID, địa chỉ công bố và thời điểm đăng ký.
3. Quan sát heartbeat hoặc TTL renewal thành công.
4. Gọi health endpoint và ghi lại thời gian phản hồi.
5. Dừng một instance theo cách graceful; quan sát deregistration và thời gian consumer ngừng nhìn thấy instance.
6. Khởi động lại instance rồi ngắt mạng đột ngột để mô phỏng mất heartbeat.
7. Theo dõi lease expiration hoặc Consul check chuyển critical.
8. So sánh trạng thái registry với kết quả DiscoveryClient của consumer.
9. Đo thời gian từ lúc registry thay đổi tới lúc LoadBalancer ngừng chọn instance.
10. Khôi phục mạng và quan sát thời gian instance trở lại passing/UP.
11. Thử query-passing=false và true trong Consul để thấy khác biệt danh sách.
12. Với Eureka, quan sát self-preservation trong môi trường test cô lập và không áp dụng cấu hình thử nghiệm đó lên production.

Ghi timestamp cho mỗi sự kiện để tính heartbeat age, health-check age và propagation delay. Lặp lại thử nghiệm dưới tải và khi có GC pause để hiểu mức jitter thực tế.

## 17. Các nguyên tắc vận hành

- Theo dõi heartbeat và health như hai tín hiệu riêng.
- Đo độ mới của registry và cache ở phía consumer.
- Dùng health endpoint nhẹ, timeout hữu hạn và phản ánh đúng readiness.
- Với Consul, cân nhắc query-passing nếu consumer chỉ được phép nhận instance passing.
- Với Eureka, theo dõi self-preservation và không tắt cơ chế này chỉ để eviction nhanh hơn.
- Thiết kế TTL và lease có khoảng dự phòng cho network jitter và JVM pause.
- Dùng graceful shutdown để deregister khi dừng bình thường; dùng health/lease timeout làm lớp dự phòng cho sự cố bất thường.
- Không xóa catalog trước khi xác định agent hoặc orchestrator nào sở hữu registration.
- Giới hạn cardinality của metric label; đưa instance ID chi tiết vào log/trace.
- Bảo vệ Actuator, Consul API và Eureka management endpoint bằng authentication, ACL và network policy.
- Đặt cảnh báo theo tác động và thời gian kéo dài, tránh phản ứng với một lần check trễ đơn lẻ.

## 18. Kết luận

Heartbeat cho biết instance còn duy trì liên lạc với registry; health check cho biết instance có đáp ứng tiêu chí sức khỏe; registry freshness cho biết consumer đang nhìn thấy trạng thái được cập nhật đến đâu. Eureka dùng heartbeat/lease và có self-preservation; Consul dùng các check chủ động hoặc TTL heartbeat và có thể lọc kết quả bằng query-passing.

Để phát hiện dữ liệu quá hạn, hãy theo dõi thời điểm heartbeat gần nhất, trạng thái và tuổi health check, thời điểm registry cập nhật, cache ở consumer và request thực tế. Khi xử lý stale registration, xác định đúng lớp lưu dữ liệu và nguồn sở hữu trước khi deregister. Kết hợp metrics, log có cấu trúc, trace và kiểm thử mất kết nối sẽ giúp phân biệt instance thực sự lỗi với dữ liệu discovery chỉ đang chậm cập nhật.

## Tài liệu tham khảo

- [Spring Cloud Netflix — Eureka Client and Server](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Netflix — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Netflix Eureka — Understanding Client/Server Communication](https://github.com/Netflix/eureka/wiki/Understanding-eureka-client-server-communication)
- [Netflix Eureka — Server Self-Preservation Mode](https://github.com/Netflix/eureka/wiki/Server-Self-Preservation-Mode)
- [Spring Cloud Consul — Service Discovery and Health Checks](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Consul — Common Application Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [HashiCorp Consul — Health Check Configuration](https://developer.hashicorp.com/consul/docs/reference/service/health-check)
- [HashiCorp Consul — Health API](https://developer.hashicorp.com/consul/api-docs/health)
- [Spring Boot — Actuator Health](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Micrometer — Metrics](https://docs.micrometer.io/micrometer/reference/index.html)

