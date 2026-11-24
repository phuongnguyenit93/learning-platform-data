# Tác động của metadata lớn và thay đổi instance liên tục

Trong Spring Cloud Service Discovery, registry không chỉ lưu tên service và địa chỉ instance. Nó còn lưu metadata để consumer, load balancer hoặc thành phần vận hành phân loại instance theo zone, version, role hay capability. Metadata hữu ích khi nhỏ và ổn định. Khi metadata quá lớn hoặc thay đổi liên tục, registry phải lưu, serialize, truyền và cập nhật nhiều dữ liệu hơn; consumer cũng phải nhận và xử lý các bản cập nhật thường xuyên.

Một vấn đề khác là instance churn: instance được tạo, đăng ký, thay thế và hủy đăng ký với tần suất cao. Churn làm tăng số lần ghi vào registry, health check, heartbeat, replication và refresh cache. Khi metadata lớn kết hợp churn cao, tải có thể tăng nhanh và làm dữ liệu discovery chậm cập nhật.

Bài này tập trung vào Eureka và Consul trong Spring Cloud, cách thiết kế metadata, cách nhận biết churn, các chỉ số hiệu năng và cách kiểm thử trước khi triển khai.

## 1. Metadata trong service discovery dùng để làm gì?

Metadata là các thuộc tính bổ sung gắn với một service instance. Consumer có thể dùng chúng để phân biệt instance theo môi trường, zone, phiên bản hoặc nhóm chức năng.

Ví dụ metadata phù hợp:

- zone: zone-a
- version: 2.4.1
- role: read
- protocol: v2
- capability: inventory-search

Metadata thường là các cặp key-value dạng chuỗi. Nó không nên trở thành nơi lưu trạng thái nghiệp vụ, dữ liệu lớn, log, danh sách user, token hoặc thông tin thay đổi theo từng request.

Ví dụ, consumer có thể chọn instance ở cùng zone hoặc chỉ gọi instance hỗ trợ protocol v2. Những quyết định này nên dựa trên một tập key nhỏ, có ý nghĩa và thay đổi theo vòng đời triển khai.

## 2. Metadata trong Eureka và Consul

Hai registry đều hỗ trợ metadata, nhưng cấu trúc và cách consumer sử dụng có khác nhau.

**Eureka**

Eureka lưu metadata tùy chỉnh trong metadata map của InstanceInfo. Với Spring Cloud Netflix, có thể cấu hình qua eureka.instance.metadata-map:

    eureka:
      instance:
        metadata-map:
          zone: zone-a
          version: 2.4.1
          role: read
          protocol: v2

Metadata được gửi cùng thông tin instance. Eureka Client nhận registry và có thể đọc metadata qua ServiceInstance hoặc Eureka-specific API. Metadata map phù hợp với các thuộc tính nhỏ, ổn định theo instance.

**Consul**

Spring Cloud Consul hỗ trợ metadata và tags khi đăng ký service:

    spring:
      cloud:
        consul:
          discovery:
            metadata:
              zone: zone-a
              version: 2.4.1
              role: read
            tags:
              - api
              - protocol-v2

Metadata là các cặp key-value gắn với service instance. Tags là nhãn để phân loại và hỗ trợ truy vấn/lọc theo khả năng của Consul và Spring Cloud Consul.

Không nên nhầm metadata với health check. Metadata mô tả instance; health check báo trạng thái kiểm tra của instance. Một instance có version=2.4.1 vẫn có thể critical nếu endpoint health thất bại.

## 3. Metadata lớn làm tăng chi phí ở đâu?

Khi metadata tăng, chi phí không chỉ nằm ở dung lượng lưu trữ. Dữ liệu còn phải đi qua nhiều bước:

1. Ứng dụng tạo thông tin registration và metadata.
2. Client serialize dữ liệu để gửi tới registry.
3. Registry xác thực, lưu và có thể replicate thay đổi.
4. Registry tạo response cho truy vấn service.
5. Consumer nhận response, deserialize và cập nhật registry cache.
6. DiscoveryClient hoặc LoadBalancer sử dụng danh sách instance và metadata.

Metadata càng lớn, payload đăng ký và payload trả về càng lớn. Việc serialize/deserialize cũng tốn CPU và cấp phát object. Khi nhiều consumer tải registry, cùng một metadata có thể được truyền tới nhiều nơi.

Một số tác động cần quan sát:

- Tăng kích thước request đăng ký hoặc cập nhật instance.
- Tăng response size khi consumer tải registry.
- Tăng CPU cho serialize, deserialize, nén và xử lý JSON.
- Tăng heap usage và allocation ở registry server lẫn consumer.
- Tăng network bandwidth giữa client, registry và peer.
- Tăng thời gian cập nhật cache khi có nhiều metadata cần xử lý.
- Tăng chi phí log hoặc trace nếu metadata bị sao chép vào mọi sự kiện.

Mức tác động phụ thuộc số instance, số consumer, kích thước metadata, tần suất cập nhật, cách registry truyền delta/full registry và cấu hình cache. Không có một giới hạn kích thước chung phù hợp cho mọi phiên bản và mọi provider; cần đo với topology thực tế.

## 4. Ước lượng payload registry

Có thể ước lượng sơ bộ phần metadata của một lần tải toàn bộ registry bằng:

    Metadata payload xấp xỉ
      = số instance x kích thước metadata trung bình mỗi instance

Ví dụ có 1.000 instance, mỗi instance mang khoảng 1 KB metadata:

    1.000 x 1 KB = khoảng 1 MB metadata thô

Nếu 100 consumer đều tải một bản registry đầy đủ mỗi 30 giây, lượng metadata thô được phân phối trung bình có thể xấp xỉ:

    1 MB x 100 / 30 giây = khoảng 3,3 MB/giây

Đây chỉ là phép ước lượng để thấy tác động nhân theo số consumer. Payload thực tế còn có thông tin instance, JSON/XML framing, HTTP header, compression và protocol overhead. Eureka thường sử dụng delta fetch để chỉ truyền thay đổi khi phù hợp; Consul query có thể trả về dữ liệu theo endpoint và filter. Không nên dùng con số trên như dự báo bandwidth chính xác.

Nếu metadata tăng từ 1 KB lên 8 KB trên cùng 1.000 instance, phần metadata trong một full registry response tăng xấp xỉ tám lần. Vì thế, một vài trường lớn lặp lại trên mọi instance có thể tạo tải đáng kể hơn nhiều so với một cấu hình chỉ có vài instance.

## 5. Metadata thay đổi liên tục tạo ra registry churn

Metadata có thể được cập nhật khi instance được đăng ký hoặc cập nhật registration. Nếu ứng dụng liên tục thay đổi metadata như current-load, request-count, timestamp mỗi giây hoặc danh sách tác vụ, mỗi thay đổi có thể tạo thêm cập nhật registry và lan truyền tới consumer.

Registry không phải hệ thống telemetry thời gian thực. Các thông tin thay đổi nhanh nên được đưa vào metrics, tracing, log hoặc một hệ thống trạng thái chuyên dụng. Registry nên giữ những thuộc tính mô tả instance đủ ổn định để định tuyến hoặc phân loại.

Ví dụ không nên dùng:

    metadata:
      current-request-count: 1837
      cpu-percent: 78.4
      last-request-time: 2026-11-24T10:22:31Z
      recent-user-ids: user-1,user-2,user-3

Những trường này thay đổi liên tục, tạo churn, có thể làm lộ thông tin và không phải dữ liệu phù hợp cho discovery.

Nên dùng:

    metadata:
      zone: zone-a
      version: 2.4.1
      role: read
      protocol: v2

Các thuộc tính này thay đổi khi instance được triển khai phiên bản mới hoặc chuyển nhóm vận hành, chứ không thay đổi theo từng request.

## 6. Instance churn là gì?

Instance churn là tốc độ instance xuất hiện và biến mất khỏi registry. Churn có thể đến từ:

- Autoscaling tăng/giảm replica liên tục.
- Container hoặc Pod crash rồi được tạo lại.
- Readiness/health check dao động khiến instance liên tục bị đưa vào và ra khỏi pool.
- Deployment thay thế nhiều instance trong thời gian ngắn.
- Instance ID không ổn định hoặc bị tạo mới sau mỗi lần restart.
- Network partition làm client mất kết nối rồi đăng ký lại.
- Job ngắn hạn đăng ký service như một instance dài hạn dù vòng đời chỉ vài giây.

Churn không giống heartbeat. Một instance ổn định có thể gửi heartbeat thường xuyên nhưng không tạo registration churn. Ngược lại, một hệ thống có heartbeat bình thường vẫn có thể churn cao nếu liên tục đăng ký và hủy đăng ký các instance mới.

## 7. Vì sao churn làm registry tốn tài nguyên?

Mỗi lần instance được thêm hoặc xóa có thể kéo theo nhiều công việc:

- Registry nhận request register hoặc deregister.
- Registry cập nhật catalog/registry state.
- Thay đổi được replicate tới peer hoặc đồng bộ tới các agent.
- Health check được tạo, cập nhật hoặc xóa.
- Response cache và client cache cần phản ánh trạng thái mới.
- Consumer tải delta hoặc full registry và cập nhật danh sách instance.
- LoadBalancer phải chọn từ tập instance mới.
- Log, metric và event phát sinh thêm.

Khi nhiều instance thay đổi cùng lúc, registry có thể xử lý một đợt burst thay vì tải đều. Consumer cũng có thể nhận nhiều bản cập nhật liên tiếp trong khi cache chưa ổn định.

Nếu một instance mới được đăng ký rồi bị hủy sau vài giây, consumer có thể nhận nó trong registry nhưng chưa kịp dùng; sau đó lại nhận một bản cập nhật xóa instance. Với churn cao, phần lớn hoạt động discovery có thể dành cho những instance tồn tại quá ngắn.

## 8. Eureka: heartbeat, delta registry và churn

Eureka Client đăng ký instance và gửi heartbeat để gia hạn lease. Client cũng định kỳ tải registry; mặc định thường dùng delta để nhận thay đổi kể từ lần fetch trước. Nếu phát hiện dữ liệu delta không nhất quán, client có thể reconcile bằng cách tải registry đầy đủ.

Churn cao làm tăng số thay đổi registry được đưa vào delta. Nếu nhiều instance cùng được tạo hoặc xóa, response delta có thể lớn; client cần deserialize và cập nhật nhiều InstanceInfo. Khi metadata map lớn, phần dữ liệu đi kèm mỗi instance update cũng lớn hơn.

Một số thuộc tính thường gặp:

    eureka:
      instance:
        lease-renewal-interval-in-seconds: 30
        lease-expiration-duration-in-seconds: 90
      client:
        registry-fetch-interval-seconds: 30
        disable-delta: false

Không nên tắt delta chỉ để thử nghiệm đơn giản mà không đánh giá tải. Full registry fetch có thể truyền nhiều dữ liệu hơn, đặc biệt khi số instance và metadata lớn.

Eureka self-preservation cũng ảnh hưởng quan sát churn. Khi heartbeat thấp hơn ngưỡng dự kiến, server có thể tạm dừng eviction để tránh xóa hàng loạt instance do network partition. Vì vậy, số registration trong server có thể cao hơn số instance thực sự đang phục vụ.

Khi churn tăng, cần theo dõi heartbeat rate, registration/deregistration rate, delta fetch size, full fetch count, eviction và trạng thái self-preservation. Tên metric cụ thể tùy phiên bản và instrumentation; hãy xác định metric đang có thay vì giả định mọi tên đều được xuất sẵn.

## 9. Consul: service registration, checks và catalog churn

Consul Agent quản lý service registration và các health check của service. Thay đổi service hoặc metadata cần được agent đồng bộ với Consul Catalog. Khi instance churn cao, số lần đăng ký, hủy đăng ký và cập nhật trạng thái check tăng.

Health check interval quá ngắn làm agent tạo nhiều lần kiểm tra. Nếu endpoint dao động quanh ngưỡng timeout, trạng thái có thể liên tục chuyển passing và critical. Điều này không nhất thiết tạo registration mới mỗi lần, nhưng tạo health-state churn và làm truy vấn health thay đổi thường xuyên.

Cần phân biệt:

- Registration churn: service được thêm/xóa khỏi agent hoặc catalog.
- Health-state churn: check đổi passing, warning, critical.
- Metadata churn: metadata hoặc tags của service bị cập nhật.
- Consumer query churn: danh sách instance trả về thay đổi liên tục.

Có thể bật query-passing để consumer chỉ nhận instance passing:

    spring:
      cloud:
        consul:
          discovery:
            query-passing: true

Cấu hình này lọc kết quả discovery theo trạng thái health, nhưng không ngăn service registration hoặc health check phát sinh. Muốn giảm churn, cần xử lý nguyên nhân tạo/xóa instance hoặc làm health check ổn định hơn.

## 10. Giảm metadata mà không mất thông tin cần thiết

Hãy giữ metadata ở mức tối thiểu đủ cho định tuyến, lựa chọn hoặc vận hành:

- Chỉ giữ key có consumer thực sự sử dụng.
- Ưu tiên chuỗi ngắn và giá trị có kích thước giới hạn.
- Dùng version, zone, role hoặc capability thay vì mô tả dài.
- Không lặp lại cấu hình chung trên từng instance nếu có thể lấy từ config service hoặc deployment environment.
- Không lưu JSON lớn, danh sách endpoint phụ thuộc động, log hoặc dữ liệu nghiệp vụ trong metadata.
- Không lưu secret, token, password hoặc connection string.
- Không đưa timestamp, counter, CPU, memory hoặc request count thay đổi liên tục vào registry.
- Xóa key cũ khi consumer không còn dùng để tránh metadata tích lũy qua nhiều phiên bản.

Ví dụ metadata có kiểm soát:

    spring:
      cloud:
        consul:
          discovery:
            metadata:
              zone: zone-a
              version: 2.4.1
              role: read
              protocol: v2

Đối với Eureka:

    eureka:
      instance:
        metadata-map:
          zone: zone-a
          version: 2.4.1
          role: read
          protocol: v2

Hãy thống nhất tên key và ý nghĩa giữa producer và consumer. Nếu consumer lọc theo zone nhưng một nhóm instance dùng key availability-zone còn nhóm khác dùng zone, logic lọc có thể trả kết quả thiếu hoặc sai.

## 11. Giảm churn do autoscaling và deployment

Churn có thể giảm bằng cách điều chỉnh chính sách vòng đời instance:

1. **Autoscaling stabilization:** dùng stabilization window hoặc cooldown để tránh scale up/down liên tục khi metric dao động nhỏ.
2. **Readiness gate:** chỉ đưa instance vào traffic khi ứng dụng và dependency đã sẵn sàng.
3. **Graceful deregistration:** rút instance khỏi traffic và deregister trước khi dừng tiến trình.
4. **Health check có biên dự phòng:** timeout và interval phải chịu được jitter, GC pause và tải cao.
5. **Instance ID ổn định theo vòng đời:** mỗi instance cần ID duy nhất nhưng không tạo ID mới liên tục khi chỉ có thay đổi cấu hình nhỏ.
6. **Deployment theo batch:** rollout theo từng nhóm để tránh burst registration và health check.
7. **Giới hạn retry:** retry đăng ký hoặc kết nối phải có backoff và jitter để tránh thundering herd sau sự cố registry.
8. **Không đăng ký job ngắn hạn như service lâu dài:** dùng queue/job scheduler nếu workload không cần được consumer tìm như một endpoint.

Không nên giảm heartbeat interval hoặc health-check interval một cách máy móc để phản ứng nhanh hơn. Interval ngắn làm tăng traffic và có thể khiến hệ thống nhạy hơn với dao động tạm thời.

## 12. Cache và chi phí cập nhật ở consumer

Consumer có thể giữ registry trong cache để tránh gọi registry cho từng request. Spring Cloud LoadBalancer cũng có thể dùng ServiceInstanceListSupplier với cache tùy cấu hình. Cache giảm số truy vấn nhưng tạo độ trễ khi topology thay đổi.

Khi churn cao, cache liên tục bị làm mới hoặc nhận danh sách khác nhau. Nếu TTL quá dài, consumer có thể chọn instance đã bị xóa; nếu TTL quá ngắn, consumer tạo nhiều truy vấn hơn và tăng tải registry.

Cần đo:

- Cache hit/miss.
- Số lần refresh và thời gian refresh.
- Số instance trong mỗi response.
- Độ trễ từ lúc registry thay đổi tới lúc consumer nhìn thấy thay đổi.
- Số request thất bại do instance không còn tồn tại.
- Số lần LoadBalancer chọn instance có health/status không còn phù hợp.

Không mặc định rằng mọi DiscoveryClient đều cache giống nhau. Eureka có registry cache phía client; Consul query và Spring Cloud LoadBalancer có cơ chế riêng. Hãy kiểm tra implementation và version đang sử dụng trước khi điều chỉnh TTL hoặc refresh interval.

## 13. Đo churn và chi phí metadata

Một số chỉ số hữu ích:

| Chỉ số | Cách hiểu | Dùng để phát hiện |
|---|---|---|
| Registered instance count | Số instance hiện có theo service | Tăng/giảm bất thường |
| Registration rate | Số lần đăng ký mỗi giây/phút | Burst tạo instance |
| Deregistration rate | Số lần hủy đăng ký mỗi giây/phút | Crash loop hoặc scale-in liên tục |
| Instance turnover | Tỷ lệ instance bị thay thế trong một khoảng thời gian | Churn tổng thể |
| Metadata bytes per instance | Kích thước metadata trung bình và p95 | Payload lớn |
| Registry response bytes | Kích thước response registry/delta | Network và serialization cost |
| Registry update latency | Thời gian từ thay đổi tới lúc registry ghi nhận | Độ trễ ghi |
| Consumer propagation delay | Thời gian consumer nhìn thấy thay đổi | Cache/fetch delay |
| Health-state transition rate | Số lần passing/critical chuyển đổi | Health flapping |
| Lookup latency/error | Thời gian và lỗi khi consumer tra cứu | Ảnh hưởng discovery |

Tên metric ở đây là chỉ số cần instrument hoặc tổng hợp từ log/API; không phải tất cả đều là metric mặc định do Eureka, Consul hoặc Spring Cloud xuất ra.

Có thể tính churn rate đơn giản:

    churn rate
      = (số lần register + số lần deregister)
        / khoảng thời gian đo

Với một đợt thay thế instance, thường có ít nhất một lần đăng ký instance mới và một lần hủy đăng ký instance cũ. Vì vậy, số lần thay thế và số sự kiện registry không giống nhau.

## 14. Thiết kế benchmark metadata và churn

Nên tách thử nghiệm metadata size và churn rate để nhận biết yếu tố gây tải.

Một ma trận mẫu:

| Kịch bản | Số instance | Metadata trung bình | Churn |
|---|---:|---:|---:|
| Baseline | 100 | 256 B | Thấp |
| Metadata vừa | 100 | 2 KB | Thấp |
| Metadata lớn | 100 | 8 KB | Thấp |
| Churn vừa | 500 | 1 KB | 5% instance/phút |
| Churn cao | 500 | 1 KB | 20% instance/phút |
| Kết hợp | 500 | 8 KB | 20% instance/phút |

Các con số chỉ là cấu hình thí nghiệm minh họa. Cần điều chỉnh theo quy mô dự kiến và không coi 8 KB là giới hạn kỹ thuật của provider.

Với mỗi kịch bản:

1. Giữ cùng phiên bản registry, số consumer và network topology.
2. Đăng ký instance với metadata có kích thước xác định.
3. Đo kích thước request/response, CPU, heap, allocation và network.
4. Tạo churn theo tỷ lệ đã định, ghi lại register/deregister events.
5. Đo thời gian registry cập nhật và consumer nhìn thấy thay đổi.
6. Đo lookup p50/p95/p99, lỗi lookup và request tới instance đã bị loại.
7. Lặp lại đủ lâu để thấy ảnh hưởng GC và cache warm-up.
8. So sánh với baseline, sau đó thay đổi một yếu tố mỗi lần.

Đừng thay metadata size, churn rate, fetch interval và health-check interval cùng lúc trong lần thử đầu tiên. Nếu thay nhiều yếu tố đồng thời, sẽ khó xác định nguyên nhân của thay đổi hiệu năng.

## 15. Phân tích kết quả benchmark

Một số dấu hiệu và hướng diễn giải:

| Quan sát | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Registry CPU tăng theo metadata size | Serialize/deserialize và xử lý payload lớn | Giảm key/value, bỏ dữ liệu lặp |
| Network tăng mạnh khi số consumer tăng | Mỗi consumer nhận response registry lớn | Giảm metadata, đánh giá delta/cache |
| Consumer heap và GC tăng | Nhiều InstanceInfo/ServiceInstance và metadata object | Giảm payload, tránh tạo object phụ không cần thiết |
| Registration rate tăng đột biến | Autoscaling, restart loop hoặc deployment đồng loạt | Stabilization, rollout theo batch, backoff |
| Health status liên tục passing/critical | Endpoint chập chờn, timeout quá ngắn hoặc dependency không ổn định | Đo latency, chỉnh check và thiết kế readiness |
| Registry đúng nhưng consumer cập nhật chậm | Client fetch/cache hoặc LoadBalancer cache | Đo từng lớp và điều chỉnh có kiểm soát |
| Nhiều bản ghi instance cũ | Deregistration thất bại hoặc self-preservation | Kiểm tra owner, lease, agent và quy trình shutdown |

Nên đánh giá cả hiệu năng lẫn độ đúng của discovery. Một cấu hình nhanh nhưng thường xuyên trả instance không còn hoạt động không phải là tối ưu.

## 16. Tình huống thực tế: autoscaling tạo burst instance

Giả sử một service có 100 instance. Khi tải tăng, autoscaler tăng lên 200 instance trong một phút. Nếu mỗi instance có metadata lớn và health check chạy ngay sau registration, registry nhận một burst gồm registration, health check và các lần cập nhật trạng thái.

Khi tải giảm, autoscaler scale-in quá nhanh và xóa 100 instance. Nếu consumer cache chưa kịp cập nhật, request có thể tiếp tục tới instance đang dừng. Nếu các instance mới lại được tạo do tải dao động, hệ thống có thể liên tục thêm/xóa record.

Cách xử lý:

- Dùng scale-out nhanh nhưng scale-in có stabilization window dài hơn.
- Đưa instance mới vào traffic sau khi readiness đạt.
- Drain instance cũ trước khi terminate.
- Giới hạn tốc độ rollout và số instance thay thế đồng thời.
- Giữ metadata nhỏ và ổn định để mỗi registration có payload nhẹ.
- Theo dõi registration/deregistration rate cùng consumer propagation delay.
- Dùng backoff có jitter cho retry sau khi registry hoặc network phục hồi.

## 17. Bảo mật và quyền riêng tư của metadata

Metadata thường được trả về cho consumer có quyền đọc registry. Vì vậy, mọi trường metadata nên được xem là dữ liệu có thể bị nhiều service nội bộ quan sát.

Không lưu:

- Password, API key, bearer token hoặc ACL token.
- Connection string có thông tin xác thực.
- Thông tin cá nhân hoặc định danh user.
- Nội dung request, log hoặc payload nghiệp vụ.
- Địa chỉ nội bộ nhạy cảm không cần thiết cho consumer.

Chỉ đưa các thuộc tính cần cho discovery và định tuyến. Dùng ACL của Consul hoặc cơ chế bảo vệ registry phù hợp, nhưng không coi việc bật ACL là lý do để đưa secret vào metadata.

## 18. Nguyên tắc vận hành

- Giữ metadata nhỏ, có schema và ý nghĩa ổn định.
- Dùng metrics/log/tracing cho dữ liệu thay đổi nhanh.
- Không dùng registry như message bus hoặc telemetry store.
- Đo kích thước metadata trung bình và p95 theo service.
- Theo dõi registration/deregistration rate và health-state transition rate.
- Dùng stabilization và rollout theo batch để tránh churn burst.
- Đặt health check có timeout và interval phù hợp với latency thực tế.
- Hiểu delta/full registry fetch của Eureka và cache/query behavior của Consul.
- Đo propagation delay tới consumer, không chỉ nhìn trạng thái trên dashboard registry.
- Kiểm tra deregistration, self-preservation và orphan record khi churn tăng.
- Không tối ưu tốc độ cập nhật bằng cách làm heartbeat/check quá dày nếu chưa đo tải.
- Không đưa secret hoặc dữ liệu cá nhân vào metadata.

## 19. Kết luận

Metadata lớn làm tăng payload đăng ký và truy vấn, chi phí serialize/deserialize, memory, network và cập nhật cache. Instance churn làm tăng registration/deregistration, health check, replication và các lần consumer phải cập nhật danh sách instance. Khi hai yếu tố xuất hiện cùng lúc, registry và consumer có thể chịu tải lớn trong khi dữ liệu discovery lại kém ổn định hơn.

Hãy giữ metadata nhỏ và ít thay đổi, chuyển dữ liệu động sang metrics hoặc hệ thống chuyên dụng, ổn định autoscaling và rollout, rồi đo registry response size, event rate, lookup latency và propagation delay bằng benchmark có kiểm soát. Mục tiêu là cân bằng chi phí cập nhật với độ mới và độ chính xác của dữ liệu discovery.

## Tài liệu tham khảo

- [Spring Cloud Netflix — Eureka Client and Server](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Netflix — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Netflix Eureka — Understanding Client/Server Communication](https://github.com/Netflix/eureka/wiki/Understanding-eureka-client-server-communication)
- [Spring Cloud Consul — Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Consul — Common Application Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [HashiCorp Consul — Service Registration](https://developer.hashicorp.com/consul/docs/register)
- [HashiCorp Consul — Catalog API](https://developer.hashicorp.com/consul/api-docs/catalog)
- [Spring Cloud LoadBalancer — Caching](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Micrometer — Metrics](https://docs.micrometer.io/micrometer/reference/index.html)

