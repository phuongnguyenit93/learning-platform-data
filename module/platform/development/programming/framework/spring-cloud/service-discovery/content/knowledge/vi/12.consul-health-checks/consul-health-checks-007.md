# Hủy đăng ký instance lỗi kéo dài và xử lý bản ghi còn sót

Trong hệ thống microservice, một instance có thể ngừng hoạt động đột ngột vì máy chủ bị tắt, container bị xóa, tiến trình bị kill hoặc máy chủ ứng dụng mất kết nối. Nếu quá trình kết thúc không kịp gửi lệnh deregister, bản ghi service có thể vẫn còn trong Consul Catalog. Health check giúp Consul nhận ra instance không còn khỏe; thuộc tính health-check-critical-timeout cho phép tự động hủy đăng ký service nếu check ở trạng thái critical quá lâu.

Cơ chế này giúp dọn các đăng ký lỗi kéo dài, nhưng không thay thế việc kết thúc vòng đời ứng dụng đúng cách. Cần phân biệt hủy đăng ký ở local agent với xóa bản ghi trực tiếp khỏi catalog, đồng thời xác định thành phần nào đang sở hữu và có thể đăng ký lại service.

## 1. Vì sao xuất hiện bản ghi service còn sót?

Spring Cloud Consul đăng ký service với Consul Agent. Agent giữ thông tin service và health check tại node, sau đó đồng bộ trạng thái lên Consul Catalog để các consumer tra cứu.

Với cấu hình mặc định, Spring Cloud Consul tạo HTTP health check gọi endpoint /actuator/health khoảng mỗi 10 giây. Khi check thất bại, Consul đánh dấu instance là critical. Bản ghi vẫn có thể tồn tại trong catalog dù instance không còn phục vụ request.

Một số tình huống thường gặp:

- Tiến trình JVM bị kill -9 hoặc container bị xóa trước khi Spring chạy shutdown hook.
- Máy chủ chứa ứng dụng bị mất điện hoặc bị terminate.
- Mạng bị phân vùng khiến Consul Agent không thể gọi health endpoint.
- Consul Agent vẫn còn nhưng ứng dụng đã ngừng hoạt động.
- Service được đăng ký bằng file cấu hình hoặc API, nhưng file hay registration vẫn tồn tại sau khi ứng dụng bị gỡ.
- Một bộ điều phối như Nomad hoặc Kubernetes vẫn quản lý workload và tiếp tục đăng ký lại service.
- Người vận hành xóa service khỏi catalog nhưng local agent vẫn giữ registration và đồng bộ nó trở lại.

Một bản ghi critical không đồng nghĩa service đã bị xóa. Critical là trạng thái sức khỏe; deregister là thao tác loại bỏ registration cùng các check gắn với service.

## 2. Phân biệt health check, critical timeout và deregister

Ba tham số sau có vai trò khác nhau:

| Thuộc tính | Mục đích | Ví dụ |
|---|---|---|
| health-check-interval | Khoảng cách giữa các lần Consul kiểm tra endpoint | 10s |
| health-check-timeout | Thời gian tối đa chờ một lần gọi health endpoint | 3s |
| health-check-critical-timeout | Thời gian service được phép ở trạng thái critical trước khi tự động deregister | 30m |

Không nhầm health-check-timeout với health-check-critical-timeout. Một HTTP request có thể timeout sau 3 giây, nhưng service chỉ bị tự động hủy đăng ký nếu trạng thái check tiếp tục critical đủ 30 phút theo cấu hình.

Health check trả lời câu hỏi instance có khỏe hay không. Critical timeout trả lời câu hỏi cần giữ registration lỗi trong bao lâu trước khi xóa. Khoảng thời gian này cần đủ dài để chịu được sự cố có thể phục hồi, chẳng hạn khởi động lại ứng dụng, nâng cấp ngắn hoặc gián đoạn mạng tạm thời.

## 3. Cơ chế DeregisterCriticalServiceAfter của Consul

Consul hỗ trợ trường DeregisterCriticalServiceAfter trong cấu hình health check gắn với service. Khi check ở trạng thái critical lâu hơn khoảng thời gian đã cấu hình, Consul tự động deregister service và toàn bộ các check liên quan tới service đó.

Spring Cloud Consul cung cấp thuộc tính:

    spring:
      cloud:
        consul:
          discovery:
            health-check-critical-timeout: 30m

Thuộc tính này được ánh xạ sang DeregisterCriticalServiceAfter của Consul. Giá trị không được đặt mặc định trong Spring Cloud Consul; nếu bỏ trống, ứng dụng không yêu cầu Consul tự động deregister theo critical timeout thông qua thuộc tính này.

Một số điểm quan trọng của Consul:

- Tính năng DeregisterCriticalServiceAfter có từ Consul 0.7 trở lên; cần xác nhận phiên bản Consul đang chạy hỗ trợ trường này.
- Timeout tối thiểu là 1 phút.
- Tác vụ dọn service critical chạy theo chu kỳ 30 giây, nên thời điểm deregister thực tế có thể muộn hơn timeout đã đặt một chút.
- Service và các health check gắn với service bị xóa khỏi đăng ký; node Consul không tự động bị xóa chỉ vì một service bị deregister.
- Timeout nên dài hơn đáng kể so với mọi khoảng gián đoạn có thể phục hồi của service.

Ví dụ đặt 30 phút nghĩa là Consul giữ service trong catalog khi check critical trong thời gian đó. Nếu check trở lại passing trước khi hết thời gian, điều kiện tự động deregister không còn được đáp ứng.

## 4. Cấu hình Spring Cloud Consul

Ví dụ cấu hình service Spring Boot dùng Actuator:

    spring:
      application:
        name: inventory-service
      cloud:
        consul:
          host: consul-agent.internal
          port: 8500
          discovery:
            enabled: true
            register: true
            register-health-check: true
            health-check-path: /actuator/health
            health-check-interval: 10s
            health-check-timeout: 3s
            health-check-critical-timeout: 30m

Trong ví dụ:

- Service được đăng ký với tên inventory-service.
- Consul Agent gọi /actuator/health mỗi 10 giây.
- Mỗi lần gọi health endpoint có giới hạn chờ 3 giây.
- Nếu health check tiếp tục critical đủ thời gian cấu hình, Consul tự động deregister service và các check gắn với service.

Cần bảo đảm endpoint health thực sự được expose, có thể truy cập từ Consul Agent và trả HTTP status phù hợp. Nếu endpoint trả 401, 403, 404 hoặc 503 vì cấu hình sai, Consul có thể đánh dấu service critical dù tiến trình JVM vẫn chạy.

Health check phải được gắn với service. Nếu đăng ký một node-level check độc lập, check đó không đại diện cho một service cụ thể và không thể dùng nó như cơ chế tự động dọn registration của service theo cách mong muốn.

## 5. Chọn critical timeout như thế nào?

Không nên chọn timeout chỉ dựa trên mong muốn xóa bản ghi nhanh. Cần xác định khoảng gián đoạn tối đa mà hệ thống muốn cho phép trước khi coi instance là không thể phục hồi.

Ví dụ một số mốc minh họa:

| Loại service | Timeout minh họa | Lý do |
|---|---:|---|
| Worker ngắn hạn, dễ tạo lại | 5–10 phút | Có thể dọn nhanh khi job hoặc container đã kết thúc |
| API nội bộ thông thường | 15–30 phút | Cho phép restart, deploy và gián đoạn mạng ngắn |
| Service trạng thái quan trọng | 30–60 phút hoặc theo chính sách riêng | Tránh xóa đăng ký trong sự cố kéo dài nhưng có khả năng phục hồi |

Các mốc trên chỉ là ví dụ để thảo luận. Hãy căn cứ vào thời gian khởi động lại, lịch bảo trì, cơ chế autoscaling, mức độ quan trọng của service và quy trình khôi phục thực tế.

Timeout quá ngắn có thể xóa registration của instance đang phục hồi. Timeout quá dài khiến bản ghi critical tồn tại lâu, làm catalog khó quan sát và tăng nguy cơ consumer hoặc công cụ vận hành đọc nhầm dữ liệu cũ nếu không lọc health status.

## 6. Dùng health filtering trước khi deregister

Không nhất thiết phải chờ critical timeout để ngăn consumer chọn instance lỗi. Spring Cloud Consul có thuộc tính query-passing:

    spring:
      cloud:
        consul:
          discovery:
            query-passing: true

Khi bật query-passing, Spring Cloud Consul yêu cầu Consul chỉ trả các instance có check passing trong truy vấn health service. Instance critical sẽ không xuất hiện trong danh sách được consumer sử dụng, dù registration vẫn còn trong catalog.

Cần phân biệt:

| Trạng thái | Registration trong catalog | Kết quả discovery khi query-passing=true |
|---|---|---|
| passing | Còn | Được trả về |
| warning | Còn | Không được trả về |
| critical | Còn cho tới khi deregister hoặc phục hồi | Không được trả về |
| Đã deregister | Đã xóa | Không còn được trả về |

Health filtering giúp loại instance lỗi khỏi luồng gọi dịch vụ nhanh hơn. Critical timeout xử lý việc dọn registration sau khi trạng thái lỗi kéo dài. Hai cơ chế bổ sung cho nhau.

## 7. Hủy đăng ký bình thường khi ứng dụng dừng

Deregister tự động sau critical timeout là phương án dự phòng khi instance chết bất thường. Khi ứng dụng dừng có kiểm soát, Spring Cloud Consul nên gửi yêu cầu deregister trong quá trình shutdown.

Spring Cloud Consul có lifecycle auto-registration. Khi service được đăng ký bởi ứng dụng, lifecycle thực hiện đăng ký và hủy đăng ký theo vòng đời ứng dụng. Thuộc tính spring.cloud.consul.discovery.deregister điều khiển việc hủy đăng ký khi lifecycle dừng; cấu hình mặc định hiện hành cho phép thao tác này.

Ví dụ giữ lifecycle và deregister hoạt động:

    spring:
      cloud:
        consul:
          discovery:
            register: true
            deregister: true
            lifecycle:
              enabled: true

Dừng ứng dụng theo quy trình graceful shutdown để Spring có thời gian thực hiện callback và gửi yêu cầu tới Consul. Nếu container bị kill cưỡng bức, máy chủ bị tắt hoặc Consul Agent không thể truy cập, lệnh deregister có thể không tới được Consul. Critical timeout vẫn cần thiết như lớp bảo vệ dự phòng.

Không nên tắt deregister trong production nếu chưa có cơ chế thay thế để dọn đăng ký khi ứng dụng dừng bình thường.

## 8. Phân biệt local agent và Consul Catalog

Đây là điểm quan trọng nhất khi xử lý bản ghi còn sót.

Consul có hai góc nhìn:

- **Local Agent:** các service và check mà agent trên một node đang quản lý.
- **Catalog:** dữ liệu service và node được Consul cluster công bố cho toàn hệ thống.

Thông tin ở hai nơi có thể lệch nhau trong thời gian ngắn khi cluster chưa có leader hoặc đang đồng bộ. Agent có cơ chế anti-entropy để đồng bộ lại trong hầu hết trường hợp sau vài giây.

Các API kiểm tra:

    GET /v1/agent/services
    GET /v1/agent/checks
    GET /v1/catalog/services
    GET /v1/catalog/service/inventory-service

Nếu service còn trong /v1/agent/services, local agent vẫn quản lý registration đó. Nếu service chỉ còn trong catalog nhưng không có trên agent tương ứng, có thể đó là bản ghi cũ cần kiểm tra và xử lý ở catalog.

Không xóa catalog trước khi xác định agent nào đang sở hữu service. Nếu agent vẫn giữ registration, nó có thể đồng bộ và đăng ký lại service sau khi catalog bị xóa.

## 9. Hủy service còn tồn tại trên local agent

Nếu service vẫn được đăng ký trên Consul Agent, hãy deregister qua đúng agent đã tạo registration.

Dùng CLI:

    consul services deregister -id inventory-service-8080

Hoặc dùng Agent HTTP API:

    curl --request PUT \
      http://127.0.0.1:8500/v1/agent/service/deregister/inventory-service-8080

Thay inventory-service-8080 bằng ServiceID thực tế. ServiceID là ID của instance trên agent, không nhất thiết bằng service name inventory-service.

Agent sẽ xóa service cùng các check liên quan và đồng bộ thay đổi lên Consul Catalog. API này chỉ xóa registration được quản lý bởi local agent đang nhận request.

Quyền ACL cần thiết cho thao tác agent service deregistration là service:write. Nếu dùng token, gửi token qua header X-Consul-Token và không ghi token thật vào tài liệu, shell history hoặc log.

## 10. Xử lý bản ghi chỉ còn trong Catalog

Nếu host hoặc Consul Agent đã mất hoàn toàn và registration không còn trên agent, có thể cần xóa bản ghi trực tiếp khỏi Consul Catalog.

Trước tiên, lấy thông tin node, datacenter và ServiceID:

    GET /v1/catalog/service/inventory-service

Một kết quả có thể chứa:

    {
      "Node": "worker-03",
      "Datacenter": "dc1",
      "ServiceName": "inventory-service",
      "ServiceID": "inventory-service-8080",
      "ServiceAddress": "10.0.2.15",
      "ServicePort": 8080
    }

Sau khi xác minh chính xác bản ghi cần xóa, gửi PUT tới Catalog API:

    curl --request PUT \
      --header "X-Consul-Token: $CONSUL_HTTP_TOKEN" \
      --header "Content-Type: application/json" \
      --data '{
        "Datacenter": "dc1",
        "Node": "worker-03",
        "ServiceID": "inventory-service-8080"
      }' \
      http://127.0.0.1:8500/v1/catalog/deregister

Catalog API cần node:write và service:write. Đây là API cấp thấp để sửa catalog trực tiếp; tài liệu HashiCorp khuyến nghị dùng Agent API khi local agent còn tồn tại vì agent API đơn giản hơn và có anti-entropy.

Không gửi payload chỉ có Node nếu mục tiêu là xóa một service. Khi chỉ có Node, Consul có thể xóa node cùng toàn bộ service và check của node đó. Muốn xóa một instance riêng lẻ, phải cung cấp đúng Datacenter, Node và ServiceID.

## 11. Xử lý service được quản lý bằng file cấu hình hoặc orchestrator

Một số service không được đăng ký trực tiếp bởi Spring Cloud mà được khai báo bằng file cấu hình của Consul Agent hoặc được một bộ điều phối quản lý.

**Service khai báo bằng file cấu hình Consul**

- Tìm đúng file định nghĩa service trong config directory của agent.
- Xóa hoặc chỉnh sửa định nghĩa service trong file.
- Chạy consul reload hoặc reload agent theo quy trình vận hành.
- Xác minh service không còn trong /v1/agent/services và Catalog.

Nếu chỉ gọi API deregister mà file cấu hình vẫn còn, agent có thể đăng ký lại service khi reload hoặc khởi động lại.

**Service do orchestrator quản lý**

Nếu Nomad, Kubernetes, một operator hoặc agent triển khai đang quản lý service, cần cập nhật workload hoặc cấu hình ở nguồn sở hữu. Nếu chỉ xóa bản ghi khỏi Consul, bộ điều phối có thể tạo lại registration khi workload còn tồn tại hoặc được reconcile.

Nguyên tắc là xóa registration tại nơi tạo và duy trì nó. Consul Catalog là bản ghi được đồng bộ từ các nguồn đó; sửa catalog thủ công không phải lúc nào cũng thay đổi trạng thái mong muốn của workload.

## 12. Vì sao service xuất hiện lại sau khi deregister?

Nếu service biến mất rồi xuất hiện trở lại, kiểm tra các nguyên nhân sau:

1. **Local agent vẫn giữ registration:** đã xóa catalog nhưng chưa xóa registration ở agent.
2. **Ứng dụng vẫn chạy:** Spring Cloud Consul hoặc một tiến trình khác tiếp tục đăng ký service.
3. **Config file vẫn tồn tại:** agent tải lại định nghĩa service khi reload hoặc restart.
4. **Orchestrator reconcile:** Nomad, Kubernetes hoặc operator tự đăng ký lại service theo trạng thái workload.
5. **Sai ServiceID:** thao tác xóa nhầm instance hoặc dùng service name thay vì ID cụ thể.
6. **Có nhiều agent:** service được đăng ký trên node khác nhưng chỉ một node được kiểm tra.
7. **Nhiều datacenter hoặc namespace:** truy vấn hoặc thao tác xóa đang nhắm tới sai phạm vi.

Khi điều tra, so sánh /v1/agent/services với /v1/catalog/service/{serviceName}, kiểm tra Node và Datacenter, sau đó tìm nguồn đang sở hữu registration. Không lặp lại thao tác xóa catalog nếu chưa xử lý nguyên nhân đăng ký lại.

## 13. Quy trình dọn bản ghi còn sót an toàn

Có thể áp dụng quy trình sau khi phát hiện instance critical kéo dài:

1. **Xác định instance:** lấy service name, ServiceID, Node, Datacenter, địa chỉ và port từ Consul Catalog.
2. **Xác nhận trạng thái:** kiểm tra health check ID, trạng thái critical, output và thời điểm cập nhật.
3. **Xác định chủ sở hữu:** kiểm tra local agent, file cấu hình, tiến trình Spring Boot và orchestrator.
4. **Ngăn đăng ký lại:** dừng workload hoặc cập nhật nguồn cấu hình nếu service không còn được sử dụng.
5. **Chọn đúng cách deregister:** dùng Agent API nếu local agent còn sở hữu registration; dùng Catalog API nếu chỉ còn bản ghi catalog và agent cũ không còn khả dụng.
6. **Xác minh:** kiểm tra agent services, agent checks, catalog service và truy vấn health service.
7. **Kiểm tra consumer:** xác nhận DiscoveryClient hoặc LoadBalancer không còn nhận instance cũ sau khi cache được cập nhật.
8. **Theo dõi:** quan sát catalog trong một khoảng thời gian để chắc chắn registration không xuất hiện trở lại.

Nếu service đã bị deregister tự động do critical timeout, vẫn nên xác minh source of truth và trạng thái agent. Việc service biến mất khỏi catalog không chứng minh tiến trình cũ đã được dừng hoặc workload không còn được bộ điều phối tạo lại.

## 14. Bảo mật và kiểm soát thao tác xóa

Deregister là thao tác thay đổi trạng thái hệ thống và có thể làm gián đoạn traffic. Cần áp dụng các biện pháp:

- Chỉ cấp service:write cho agent deregistration và node:write cùng service:write cho catalog deregistration khi thực sự cần.
- Dùng ACL token có phạm vi nhỏ, không dùng token quản trị toàn quyền cho script dọn service định kỳ.
- Ghi lại ServiceID, Node, Datacenter, người thực hiện, lý do và kết quả thao tác.
- Xác minh instance trước khi xóa; không dựa riêng vào tên service vì một service có thể có nhiều instance.
- Không xóa node nếu mục tiêu chỉ là một service instance.
- Bảo vệ Consul HTTP API bằng mạng quản trị, TLS và ACL.
- Kiểm tra namespace hoặc partition nếu dùng Consul Enterprise để tránh thao tác nhầm phạm vi.

Với quy trình tự động, nên có bước kiểm tra thời gian critical, nguồn đăng ký và trạng thái workload trước khi gọi API xóa. Không xóa hàng loạt chỉ dựa vào điều kiện service đang critical tại một thời điểm.

## 15. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Service critical nhưng không tự deregister | Chưa cấu hình health-check-critical-timeout hoặc Consul không hỗ trợ trường này | Kiểm tra cấu hình service check và phiên bản Consul |
| Đã quá timeout nhưng service vẫn còn | Consul reap theo chu kỳ 30 giây hoặc check chưa critical liên tục đủ thời gian | Kiểm tra trạng thái check và chờ thêm một chu kỳ dọn |
| Service bị xóa quá sớm | Critical timeout nhỏ hơn thời gian phục hồi thực tế | Tăng timeout và đánh giá health endpoint |
| Agent API trả Unknown service ID | Gọi sai agent hoặc dùng service name thay vì ServiceID | Kiểm tra /v1/agent/services trên đúng node |
| Catalog API xóa không thành công | Thiếu ACL, sai Node, Datacenter hoặc ServiceID | Kiểm tra payload và quyền node:write/service:write |
| Service xuất hiện lại | Agent, file cấu hình hoặc orchestrator vẫn đăng ký | Xóa tại nguồn sở hữu registration |
| Consumer vẫn thấy instance cũ | Cache discovery hoặc LoadBalancer chưa làm mới | Kiểm tra query-passing và chu kỳ refresh cache |
| Node vẫn còn sau khi service bị deregister | Service deregistration không xóa node | Chỉ xóa node khi node đã ngừng hoạt động và không còn service/check hợp lệ |

Khi Consul Agent và Catalog không đồng nhất, kiểm tra log agent và trạng thái leader/anti-entropy. Chênh lệch ngắn hạn có thể xảy ra trong quá trình đồng bộ; nếu kéo dài, cần kiểm tra ACL, kết nối agent-server và registration source.

## 16. Kết luận

Spring Cloud Consul hỗ trợ tự động deregister service lỗi kéo dài bằng thuộc tính health-check-critical-timeout, được ánh xạ sang DeregisterCriticalServiceAfter của Consul. Khi check gắn với service ở trạng thái critical quá thời gian cấu hình, Consul xóa service cùng các check liên quan. Tác vụ dọn chạy theo chu kỳ, vì vậy thời điểm xóa thực tế có thể muộn hơn timeout một chút.

Khi xử lý bản ghi còn sót, hãy xác định service đang nằm trên local agent hay chỉ còn trong catalog. Dùng Agent API để xóa registration mà agent đang quản lý; dùng Catalog API cho bản ghi mồ côi khi agent nguồn không còn tồn tại. Nếu service do file cấu hình hoặc orchestrator quản lý, phải cập nhật nguồn đăng ký để tránh service xuất hiện trở lại.

Kết hợp graceful shutdown, health check, critical timeout, query-passing và quy trình dọn catalog có kiểm soát giúp registry phản ánh chính xác các instance còn khả năng phục vụ.

## Tài liệu tham khảo

- [Spring Cloud Consul — Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Consul — Common Application Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [Consul — Health Check Configuration Reference](https://developer.hashicorp.com/consul/docs/reference/service/health-check)
- [Consul — Check Agent HTTP API](https://developer.hashicorp.com/consul/api-docs/agent/check)
- [Consul — Service Agent HTTP API](https://developer.hashicorp.com/consul/api-docs/agent/service)
- [Consul — Catalog HTTP API](https://developer.hashicorp.com/consul/api-docs/catalog)
- [Consul — Services Deregister Command](https://developer.hashicorp.com/consul/commands/services/deregister)

