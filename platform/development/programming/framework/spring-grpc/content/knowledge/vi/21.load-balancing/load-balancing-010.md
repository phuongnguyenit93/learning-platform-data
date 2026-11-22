# Cân bằng giữa region hoặc zone

Một dịch vụ gRPC có thể chạy trên nhiều zone trong cùng một region hoặc trên nhiều region địa lý. Phân phối request giữa các địa điểm này ảnh hưởng trực tiếp tới độ trễ, khả năng chịu lỗi, chi phí truyền dữ liệu và tính nhất quán của dữ liệu. Một chính sách chỉ chia đều request cho mọi endpoint có thể khiến request đi qua region xa dù trong zone gần vẫn còn năng lực.

**Cân bằng giữa region hoặc zone** là chọn nơi xử lý RPC theo locality (vị trí triển khai), trạng thái endpoint, năng lực và mục tiêu độ sẵn sàng. Bài thuộc chương **Load balancing** của mô-đun **SPRING_GRPC**: phát triển dịch vụ gRPC trong hệ sinh thái Spring bằng hợp đồng Protocol Buffers, sinh mã Java và triển khai client/server cho unary hoặc streaming RPC; người học xử lý metadata, deadline, status, interceptor, TLS, kiểm thử tích hợp và giám sát hiệu năng, độ tin cậy. Trọng tâm ở đây là thiết kế locality-aware routing giữa zone và region cho gRPC client.

## 1. Region, zone và locality

- **Region** là một khu vực địa lý có hạ tầng riêng, thường có độ trễ mạng tới region khác cao hơn so với giao tiếp nội vùng. Ví dụ: Southeast Asia hoặc East Asia.
- **Zone** là một miền triển khai độc lập trong một region, thường tương ứng với một availability zone của cloud provider. Các zone cùng region thường có kết nối độ trễ thấp, nhưng vẫn có thể gặp sự cố độc lập.
- **Locality** là nhãn vị trí mà hệ thống cân bằng tải dùng để nhóm endpoint. Một locality thường được mô tả bởi region, zone và có thể thêm sub-zone.

Ví dụ một dịch vụ Inventory có endpoint tại ba zone của region A và hai zone của region B:

~~~text
Region A
  zone-a: inventory-a1, inventory-a2
  zone-b: inventory-b1, inventory-b2
  zone-c: inventory-c1

Region B
  zone-a: inventory-rb-a1, inventory-rb-a2
  zone-b: inventory-rb-b1
~~~

Client ở zone A/zone-a thường nên ưu tiên endpoint gần đó để giảm latency và traffic liên vùng. Nếu locality đó mất khả năng phục vụ hoặc quá tải, client có thể chuyển sang zone khác cùng region. Region khác là lớp dự phòng tiếp theo, tùy mục tiêu RTO, RPO và chi phí.

Không nên đồng nhất locality với hostname hoặc IP. Endpoint có thể thay đổi khi autoscaling, rolling deployment hoặc failover; locality là thuộc tính hạ tầng do service discovery/control plane cung cấp.

## 2. Vì sao round-robin đơn thuần chưa đủ?

Client-side load balancing của gRPC chọn subchannel/endpoint cho từng RPC. Với chính sách round-robin, các endpoint đang ở trạng thái READY được chọn luân phiên. Điều này hữu ích khi mọi endpoint có chi phí và vị trí tương đương.

Nhưng round-robin trên danh sách endpoint phẳng không tự hiểu endpoint nào ở cùng zone hoặc region với client. Nếu resolver trả về endpoint của nhiều region, client có thể phân phối request sang region xa ngay cả khi endpoint gần vẫn khỏe.

| Cách chọn | Hành vi | Hạn chế |
| --- | --- | --- |
| pick-first | Chọn endpoint khả dụng đầu tiên theo danh sách resolver. | Không phân phối đều; kết quả phụ thuộc thứ tự và khả năng kết nối. |
| round-robin | Luân phiên giữa các endpoint READY. | Không mặc nhiên ưu tiên zone gần hoặc nhận biết chi phí liên region. |
| Locality-aware | Chọn locality theo ưu tiên/trọng số, rồi chọn endpoint trong locality. | Cần discovery/control plane cung cấp metadata locality và policy phù hợp. |
| Proxy/service mesh routing | Proxy hoặc mesh áp dụng locality, health và failover policy. | Cần cấu hình, vận hành và quan sát thêm một tầng hạ tầng. |

Với gRPC, HTTP/2 multiplex nhiều RPC trên một channel. Nếu chỉ dùng một TCP connection qua L4 load balancer, nhiều RPC có thể cùng đi tới một backend do connection affinity. Client-side load balancing hoặc L7 proxy hiểu gRPC RPC-level routing sẽ phân phối ở mức call phù hợp hơn. Một streaming RPC vẫn gắn với backend đã nhận stream cho tới khi stream kết thúc; load balancer không chuyển từng message của cùng stream sang backend khác.

## 3. Mô hình locality-aware routing

Một chính sách locality-aware thường thực hiện hai bước:

1. Chọn locality theo ưu tiên hoặc trọng số, dựa trên vị trí client, sức khỏe và năng lực của locality.
2. Chọn endpoint trong locality được chọn bằng một policy phù hợp như round-robin.

Ví dụ chính sách có ba lớp:

| Ưu tiên | Locality | Mục đích |
| --- | --- | --- |
| Primary | Zone hiện tại | Giảm latency và traffic liên zone. |
| Secondary | Các zone khác trong cùng region | Tiếp tục phục vụ khi zone hiện tại lỗi hoặc thiếu năng lực. |
| Tertiary | Region dự phòng | Duy trì dịch vụ khi region chính gặp sự cố hoặc không đủ capacity. |

Thứ tự này là một lựa chọn kiến trúc, không phải quy tắc áp dụng cho mọi hệ thống. Nếu zone hiện tại quá tải, policy có thể phân phối một phần traffic sang zone khác trước khi endpoint bị đánh dấu unhealthy. Nếu dữ liệu chỉ có ở một region, ưu tiên region gần client có thể làm tăng độ trễ đồng bộ hoặc gây lỗi nghiệp vụ. Quyết định locality phải phù hợp với nơi dữ liệu được đọc/ghi và yêu cầu nhất quán.

### Locality preference và locality weight

- **Preference/priority** xác định locality nào được thử trước và locality nào đóng vai trò failover.
- **Weight** quyết định tỷ lệ traffic tương đối giữa các locality đang được phép nhận request.
- **Endpoint weight** có thể phân phối tải giữa các endpoint trong cùng locality nếu control plane hỗ trợ.

Ví dụ minh họa: locality zone-a nhận 70%, zone-b nhận 20%, zone-c nhận 10% traffic trong cùng region. Đây là tỷ lệ tương đối trong tập locality đủ điều kiện, không phải cam kết mỗi giây sẽ có chính xác số request tương ứng. Với request volume nhỏ, quan sát ngắn hạn có thể lệch tỷ lệ.

Không cấu hình weight chỉ dựa trên số lượng endpoint. Một zone có ít máy hơn vẫn có thể có capacity lớn hơn; ngược lại, locality có nhiều endpoint nhưng đang bị giới hạn CPU, database connection hoặc quota có thể không nên nhận tỷ lệ cao.

## 4. Chọn cơ chế triển khai trong hệ sinh thái gRPC

Có ba vị trí phổ biến để thực hiện cân bằng tải:

**Client-side gRPC load balancing.** Name resolver trả danh sách endpoint cho gRPC channel; load-balancing policy chọn subchannel cho mỗi RPC. Đây là lựa chọn phù hợp khi ứng dụng Java cần kiểm soát channel và có discovery metadata đáng tin cậy.

**xDS control plane.** xDS cung cấp cấu hình cluster, endpoint và locality cho client/proxy. Với gRPC Java có tích hợp xDS, client có thể nhận endpoint theo locality và áp dụng policy do control plane phân phối. Cách này phù hợp khi tổ chức đã có control plane quản lý nhiều service, region và zone. Cần kiểm tra phiên bản grpc-java, xDS resolver/load-balancer và các policy được hỗ trợ trong phiên bản triển khai.

**Proxy hoặc service mesh.** Client kết nối tới sidecar/gateway; proxy thực hiện routing, health handling và locality policy. Cách này tập trung chính sách ở hạ tầng, nhưng thêm một hop mạng và yêu cầu quan sát cả application lẫn proxy.

Trong ứng dụng Spring, channel thường được tạo và quản lý như bean hoặc qua thư viện tích hợp gRPC client. Dù chọn cơ chế nào, hãy quản lý channel theo vòng đời ứng dụng, tái sử dụng channel cho nhiều RPC và đóng channel khi ứng dụng dừng. Không tạo channel mới cho mỗi request để đổi locality.

## 5. Cấu hình round-robin khi endpoint đã được resolver chọn đúng

Nếu mục tiêu chỉ là phân phối giữa nhiều endpoint đã được giới hạn trong cùng locality, gRPC Java có thể dùng round-robin. Ví dụ dưới đây minh họa default service config cho một target DNS:

~~~java
Map<String, ?> serviceConfig = Map.of(
        "loadBalancingConfig",
        List.of(Map.of("round_robin", Map.of()))
);

ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///inventory.internal:8443")
        .defaultServiceConfig(serviceConfig)
        .build();
~~~

Đoạn này giả định resolver trả về nhiều địa chỉ backend thuộc cùng locality và policy round-robin có trong registry của runtime. Nó **không tự tạo locality awareness**: DNS resolver cần trả đúng tập endpoint, hoặc một discovery layer khác phải giới hạn/nhóm endpoint trước khi policy chọn. DNS thông thường không bảo đảm cung cấp region/zone metadata đủ để gRPC chọn locality.

Trong Spring, đặt channel trong bean có lifecycle rõ ràng và inject stub/channel vào client adapter. Ví dụ:

~~~java
@Configuration
class InventoryGrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel inventoryChannel() {
        Map<String, ?> serviceConfig = Map.of(
                "loadBalancingConfig",
                List.of(Map.of("round_robin", Map.of()))
        );

        return ManagedChannelBuilder
                .forTarget("dns:///inventory.internal:8443")
                .defaultServiceConfig(serviceConfig)
                .build();
    }
}
~~~

Đây chỉ là ví dụ channel thuần gRPC Java. Cấu hình TLS, authority, resolver, retry và integration property phụ thuộc cách dự án Spring tạo channel; không nên đồng thời tạo một channel thủ công nếu starter đã quản lý channel cho cùng client.

## 6. Locality-aware balancing với xDS

Khi cần chọn giữa zone hoặc region, endpoint discovery phải cung cấp locality metadata. Với xDS, control plane có thể phân nhóm endpoint theo locality và phân phối weight/priority. gRPC Java client dùng xDS resolver và load-balancer tương ứng để áp dụng cấu hình nhận được.

Mô hình dữ liệu logic có thể hình dung như sau:

~~~yaml
service: inventory
localities:
  - region: region-a
    zone: zone-a
    priority: 0
    weight: 70
    endpoints:
      - address: inventory-a1:8443
      - address: inventory-a2:8443
  - region: region-a
    zone: zone-b
    priority: 0
    weight: 30
    endpoints:
      - address: inventory-b1:8443
  - region: region-b
    zone: zone-a
    priority: 1
    weight: 100
    endpoints:
      - address: inventory-rb-a1:8443
~~~

Đây là mô hình minh họa để giải thích locality/priority/weight, không phải một file xDS resource hoàn chỉnh có thể nạp trực tiếp. Cấu trúc resource thực tế do xDS API và control plane version quyết định. Trong triển khai, phải xác minh:

- Client nhận đúng locality của endpoint và locality của client được xác định theo nguồn đáng tin cậy.
- Policy có hành vi ưu tiên/failover đúng như mong muốn.
- Endpoint health được cập nhật; endpoint không READY không tiếp tục nhận RPC mới.
- Thay đổi endpoint/weight được áp dụng mà không làm gián đoạn channel đang hoạt động.
- Chính sách TLS, authority và identity vẫn đúng khi RPC đi qua region khác.

Không tự suy locality từ IP public hoặc hostname nếu hạ tầng không bảo đảm ánh xạ đó ổn định. Dùng metadata từ control plane, deployment platform hoặc resolver có contract rõ ràng.

## 7. Failover giữa zone và region

Failover là chuyển traffic khi locality hiện tại không thể hoặc không nên nhận thêm request. Cần xác định điều kiện chuyển và điều kiện quay lại:

1. **Endpoint unhealthy:** loại endpoint khỏi tập nhận RPC mới.
2. **Zone suy giảm:** giảm weight hoặc chuyển traffic sang zone khác trong cùng region.
3. **Region suy giảm:** kích hoạt locality/priority dự phòng ở region khác.
4. **Recovery:** chỉ tăng traffic về locality cũ sau khi health và capacity ổn định.

Tránh failover chỉ dựa trên một lỗi đơn lẻ của một RPC. Một request có thể lỗi do dữ liệu đầu vào, quyền truy cập hoặc lỗi nghiệp vụ; các lỗi này không chứng minh cả zone bị hỏng. Dùng health check, outlier detection hoặc tín hiệu tổng hợp từ nhiều endpoint để tránh chuyển traffic quá sớm.

Failover nhiều region cần cân nhắc:

- **RTO:** thời gian cần để chuyển traffic và khôi phục phục vụ.
- **RPO:** mức dữ liệu có thể mất khi chuyển region, đặc biệt với ghi dữ liệu bất đồng bộ.
- **Capacity dự phòng:** region còn lại có đủ năng lực nhận thêm traffic không.
- **Dependency locality:** database, cache, broker và dịch vụ phụ trợ có sẵn tại region đích không.
- **Chi phí:** cross-region traffic, replication và vận hành thường đắt hơn nội vùng.

Chuyển traffic sang region khác khi database chưa sẵn sàng có thể biến sự cố latency thành lỗi dữ liệu. Failover phải được thiết kế theo cả application tier lẫn data tier.

## 8. Kết hợp locality với health, retry và deadline

Locality-aware balancing không thay thế health checking, deadline hoặc retry:

| Cơ chế | Vai trò |
| --- | --- |
| Health checking | Xác định endpoint/service có đủ điều kiện nhận RPC mới hay không. |
| Locality policy | Chọn zone/region ưu tiên trong tập endpoint đủ điều kiện. |
| Deadline | Giới hạn thời gian toàn bộ RPC, kể cả khi phải chọn locality khác. |
| Retry | Thử lại RPC khi lỗi thuộc nhóm retryable và operation an toàn. |
| Outlier detection | Phát hiện endpoint có tỷ lệ lỗi/latency bất thường và tạm loại khỏi traffic theo policy. |

Retry không nên làm mất deadline tổng. Nếu request đã dùng 700 ms trong ngân sách 1 giây, lần thử ở region khác chỉ còn phần ngân sách còn lại. Không cấp lại timeout đầy đủ cho mỗi retry.

Khi client retry, endpoint mới có thể thuộc locality khác. Với RPC đọc idempotent, điều này thường dễ chấp nhận hơn. Với RPC ghi, cần idempotency key và trạng thái operation; endpoint ở region khác phải có thể nhận diện cùng một ý định nghiệp vụ hoặc chuyển tới nơi sở hữu dữ liệu.

Không retry tất cả lỗi UNAVAILABLE vô hạn. Dùng backoff có jitter, giới hạn số attempt và deadline tổng. Tránh retry đồng thời ở nhiều tầng client, proxy và service vì có thể khuếch đại tải khi một region đang suy giảm.

## 9. Ảnh hưởng của stream và affinity

Unary RPC kết thúc sau một request/response nên mỗi lần gọi mới có thể được load balancer chọn endpoint theo policy hiện tại. Server-streaming, client-streaming và bidirectional-streaming có tuổi thọ dài hơn:

- Endpoint được chọn khi stream bắt đầu và thường giữ stream đó tới khi kết thúc.
- Nếu locality bị giảm weight sau khi stream đã mở, stream hiện tại không tự chuyển sang endpoint khác.
- Khi stream bị ngắt, client cần mở RPC mới; nếu cần tiếp tục dữ liệu, dùng sequence number, cursor hoặc resume token.
- Nếu nghiệp vụ cần session affinity, phải xác định rõ key và policy; không dựa vào việc tình cờ cùng một HTTP/2 connection.

Với stream dài, đặt giới hạn tuổi thọ hoặc cơ chế re-establish/resume có thể giúp rollout và failover. Nhưng việc ngắt stream định kỳ phải phù hợp với semantics ứng dụng và không làm mất message chưa được xác nhận.

## 10. Dữ liệu và tính nhất quán khi chọn region

Chọn endpoint gần nhất không phải lúc nào cũng đúng nếu dữ liệu có locality riêng. Ví dụ, một order được ghi ở region A nhưng client được định tuyến sang region B có thể đọc replica chưa nhận bản ghi mới.

Một số chiến lược:

- **Read local, write home:** đọc từ replica gần client; ghi về region sở hữu dữ liệu.
- **Regional ownership:** mỗi tenant/account/order có home region; request được định tuyến tới region sở hữu.
- **Active-active:** nhiều region cùng nhận ghi, cần conflict resolution hoặc cơ chế phân vùng dữ liệu rõ ràng.
- **Failover có kiểm soát:** region dự phòng chỉ nhận ghi sau khi quyền sở hữu/fencing token được chuyển an toàn.

Đừng dùng header do client tự gửi như region hoặc tenant để cấp quyền truy cập dữ liệu. Locality dùng cho routing cần đến từ nguồn tin cậy; authorization vẫn phải được kiểm tra độc lập ở service.

## 11. Kiểm thử locality và failover

Kiểm thử cần xác minh endpoint được chọn, phản ứng khi locality suy giảm và tác động tới RPC đang mở:

1. Tạo resolver/test control plane trả endpoint thuộc hai zone; xác minh traffic ưu tiên zone được cấu hình.
2. Thay đổi weight giữa zone-a và zone-b; gửi đủ nhiều RPC để kiểm tra phân phối thống kê thay vì khẳng định chuỗi luân phiên tuyệt đối.
3. Đánh dấu endpoint unhealthy; xác minh RPC mới không được chọn endpoint đó.
4. Làm toàn bộ zone primary unhealthy; xác minh client chuyển sang zone dự phòng trong giới hạn deadline.
5. Làm region primary không khả dụng; xác minh failover region và kiểm tra dependency/data readiness.
6. Mở một streaming RPC rồi thay đổi locality weight; xác minh stream hiện tại vẫn gắn với endpoint cũ và RPC mới tuân theo policy mới.
7. Kiểm tra TLS/authority và identity khi endpoint được chọn ở region khác.

Với client-side load balancing, có thể dùng fake NameResolver hoặc resolver test để điều khiển danh sách endpoint. Với xDS, dùng control plane test fixture hoặc môi trường tích hợp có khả năng cập nhật endpoint/locality. Kiểm thử qua TCP/TLS để xác minh hành vi transport và health thực tế; unit test policy không chứng minh được DNS, xDS hoặc proxy đã được cấu hình đúng.

## 12. Quan sát và vận hành

Theo dõi theo method và locality để hiểu traffic đang đi đâu:

- Số RPC, latency p50/p95/p99 và error rate theo region/zone.
- Tỷ lệ request local-zone, cross-zone và cross-region.
- Số lần failover, thời gian phát hiện locality unhealthy và thời gian phục hồi.
- Số endpoint READY/UNREADY và số subchannel đang kết nối.
- Retry count, deadline exceeded, queueing và connection churn.
- Chi phí egress liên zone/liên region và tải trên dependency dữ liệu.

Dùng nhãn region/zone có cardinality giới hạn. Tránh gắn request ID, user ID hoặc endpoint ephemeral vào metric label. Log/tracing có thể mang endpoint/locality đã chọn để điều tra một request cụ thể, nhưng cần tuân thủ chính sách bảo mật.

Một locality nhận ít traffic hơn dự kiến chưa chắc là lỗi: weight, health, client locality, số RPC và long-lived stream đều ảnh hưởng phân phối. So sánh số liệu trong khoảng đủ dài và kiểm tra trạng thái resolver/control plane trước khi thay đổi weight.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Round-robin gửi request sang region xa | Policy chỉ thấy danh sách endpoint phẳng, không biết locality. | Cung cấp locality metadata và dùng policy locality-aware. |
| DNS trả nhiều IP nhưng traffic vẫn dồn một backend | Resolver/policy/channel chưa tạo hoặc chọn nhiều subchannel như dự kiến. | Kiểm tra resolver result, LB policy và trạng thái READY. |
| L4 load balancer dồn nhiều RPC vào một server | HTTP/2 multiplex nhiều RPC trên cùng connection. | Dùng client-side gRPC LB hoặc L7 proxy hiểu RPC. |
| Failover liên tục giữa hai zone | Health signal nhiễu hoặc ngưỡng quá nhạy. | Dùng health window, hysteresis và recovery threshold. |
| Region dự phòng nhận traffic nhưng request lỗi dữ liệu | Replica lag hoặc data ownership chưa chuyển. | Thiết kế data locality, consistency và fencing. |
| Retry làm quá tải region còn khỏe | Nhiều tầng retry cùng lúc hoặc không giới hạn attempt. | Deadline tổng, backoff jitter và retry budget. |
| Stream không chuyển sang zone mới sau đổi weight | Stream hiện tại đã gắn với backend lúc mở. | Resume/reconnect bằng cursor hoặc token khi cần chuyển. |
| Tăng weight nhưng không thấy phân phối tương ứng | Endpoint chưa READY, ít RPC hoặc stream dài chiếm tải. | Kiểm tra health, sample size và tuổi thọ stream. |

## 14. Bài tập thực hành

1. Tạo gRPC client channel với round-robin và resolver trả nhiều endpoint trong cùng zone; xác minh phân phối giữa endpoint.
2. Mô hình hóa endpoint theo region/zone và mô tả vì sao round-robin phẳng không thể tự chọn locality gần client.
3. Dùng xDS hoặc resolver/control plane có locality metadata để ưu tiên zone hiện tại, sau đó failover sang zone khác.
4. Thay đổi weight giữa hai zone và đo tỷ lệ RPC, latency cùng cross-zone traffic.
5. Mô phỏng primary region mất kết nối; xác minh failover, deadline và trạng thái dữ liệu ở region dự phòng.
6. Mở server-streaming RPC qua thời điểm đổi locality; kiểm tra semantics stream hiện tại và thiết kế resume cho lần kết nối lại.
7. Thiết lập dashboard theo region/zone cho latency, error rate, failover, retry và số endpoint READY.

Sau bài này, bạn cần biết phân biệt round-robin endpoint với locality-aware routing, chọn cơ chế client-side/xDS/proxy phù hợp, đặt ưu tiên và weight giữa zone/region, đồng thời phối hợp health, deadline, retry và data locality. Cân bằng tải liên vùng hiệu quả phải giảm latency trong điều kiện bình thường, chuyển traffic có kiểm soát khi sự cố và giữ đúng semantics dữ liệu của dịch vụ Spring gRPC.
