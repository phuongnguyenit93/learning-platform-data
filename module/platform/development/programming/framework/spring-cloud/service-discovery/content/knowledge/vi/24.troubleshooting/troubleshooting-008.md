# Consul báo critical do sai đường dẫn, cổng hoặc quyền health check

Consul có thể đăng ký một service thành công nhưng vẫn đánh dấu instance ở trạng thái critical. Hai việc này khác nhau: registration tạo bản ghi service trong catalog, còn health check định kỳ đánh giá instance có đáp ứng điều kiện hoạt động hay không. Khi check HTTP gọi sai path, sai port, không truy cập được địa chỉ hoặc bị endpoint từ chối vì quyền, Consul vẫn giữ bản ghi nhưng health status chuyển sang critical.

Bài này tập trung vào service dùng HTTP health check, đặc biệt khi ứng dụng Spring Boot/Spring Cloud Consul chạy trong Docker Compose hoặc Kubernetes. Cần kiểm tra từ chính nơi Consul Agent thực hiện check, sau đó mới sửa cấu hình registration hoặc bảo mật.

## Phân biệt service registration và health check

Consul Agent nhận cấu hình service, đăng ký service cùng check vào agent/catalog, rồi thực hiện check theo chu kỳ. Với HTTP check, agent gửi request tới URL đã cấu hình. Kết quả thường được hiểu như sau:

| Kết quả check | Trạng thái thường thấy | Ý nghĩa |
|---|---|---|
| HTTP trả mã 2xx | passing | Endpoint health phản hồi thành công |
| HTTP trả mã ngoài 2xx | critical | Endpoint không đáp ứng điều kiện passing |
| Không phân giải được hostname | critical | DNS hoặc network namespace không nhìn thấy địa chỉ |
| Connection refused / timeout | critical | Sai cổng, process chưa lắng nghe hoặc network bị chặn |
| HTTP 401/403 | critical | Check không có credential hoặc không đủ quyền |
| TLS handshake/certificate lỗi | critical | Scheme, CA, hostname hoặc certificate không hợp lệ |

Đăng ký service thành công không đồng nghĩa health check passing. Ngược lại, một check có thể tồn tại nhưng service registration đã bị hủy hoặc không còn được agent quản lý. Khi điều tra, xem cả service record lẫn check record.

Luồng xử lý cơ bản:

    Consul Agent nhận service definition
        -> Đăng ký service và check
        -> Agent chạy HTTP health check theo interval
        -> Kiểm tra DNS, TCP, TLS và HTTP
        -> 2xx: passing; lỗi: critical
        -> Health API lọc instance passing
        -> Sửa URL, port, network hoặc quyền rồi kiểm tra lại

Consul không tự sửa path hoặc mở cổng cho ứng dụng. Check sẽ tiếp tục critical cho đến khi lần kiểm tra tiếp theo thành công hoặc cấu hình được cập nhật.

## Runbook chẩn đoán theo thứ tự

1. Xác định đúng service ID và check ID đang critical.
2. Đọc nguyên nhân và output của check từ Agent API hoặc Consul UI.
3. Lấy URL check thực tế: scheme, hostname/IP, port, path, method và headers.
4. Gửi cùng request từ network namespace của Consul Agent.
5. So sánh URL check với server port, context path và management/Actuator port của ứng dụng.
6. Kiểm tra TLS, redirect, authentication, ACL và network policy.
7. Sửa đúng một nguyên nhân, chờ interval kế tiếp và xác nhận check chuyển passing.
8. Kiểm tra lại Health API với và không có bộ lọc passing=1.

Không kết luận từ một lệnh curl chạy trên máy phát triển. Consul Agent là thành phần gửi check; địa chỉ chỉ có thể truy cập từ laptop nhưng không truy cập được từ container/pod của agent vẫn sẽ critical.

## 1. Đọc check ID, trạng thái và output

Bắt đầu bằng Consul UI: mở service, chọn instance và xem phần health checks. Ghi lại check ID, trạng thái, lần cập nhật gần nhất và thông báo output. Output thường cho biết lỗi thuộc DNS, kết nối, HTTP status, TLS hay timeout.

Có thể truy vấn các check mà agent cục bộ đang quản lý:

    curl -s http://127.0.0.1:8500/v1/agent/checks

Hoặc xem các service agent đang quản lý:

    curl -s http://127.0.0.1:8500/v1/agent/services

Các API /v1/agent/* trả trạng thái local của agent. Nếu đang gọi Consul Server từ máy khác, cần chắc chắn bạn đang xem đúng agent đã đăng ký instance đó.

Với ACL bật, request tới API cần token có quyền phù hợp. Không đưa token vào command line hoặc shell history khi chia sẻ log; ưu tiên biến môi trường/secret store và che token trong output.

## 2. Kiểm tra sai đường dẫn HTTP

Health check phải gọi đúng endpoint đang được ứng dụng expose. Với Spring Boot Actuator, path mặc định thường là /actuator/health, nhưng có thể thay đổi bởi:

- management.endpoints.web.base-path đổi prefix Actuator.
- management.endpoints.web.path-mapping đổi path của endpoint health.
- server.servlet.context-path thêm context path cho ứng dụng servlet.
- management.server.port đặt management endpoint trên cổng riêng.
- Gateway hoặc reverse proxy thêm/bỏ prefix, nhưng Consul Agent thường gọi thẳng service address chứ không đi qua Gateway.

Ví dụ ứng dụng dùng context path /inventory và Actuator base path /manage, endpoint có thể là /inventory/manage/health thay vì /actuator/health. Nếu management server dùng port 9091, URL phải dùng port đó.

Ví dụ cấu hình Spring Boot:

    server:
      port: 8080

    management:
      server:
        port: 9091
      endpoints:
        web:
          base-path: /manage
          exposure:
            include: health,info

Trong cấu hình trên, health endpoint của management server thường có dạng http://<host>:9091/manage/health. Nếu ứng dụng còn cấu hình context path riêng cho management server hoặc không tách management port, URL sẽ khác. Không tự động ghép server.servlet.context-path vào URL khi management server chạy riêng; hãy xác nhận path thực tế bằng log mapping hoặc gọi trực tiếp từ cùng môi trường.

### Chọn endpoint health phù hợp

Với Spring Boot có thể dùng /actuator/health hoặc endpoint readiness nếu ứng dụng bật health probes, ví dụ /actuator/health/readiness. Readiness phù hợp khi muốn Consul chỉ coi instance sẵn sàng nhận traffic sau khi ứng dụng khởi tạo xong và dependency thiết yếu đã sẵn sàng.

Không nên dùng liveness làm điều kiện duy nhất để nhận traffic nếu liveness chỉ xác nhận process còn sống. Cũng không nên đưa các dependency không thiết yếu vào readiness khiến service bị loại khỏi registry chỉ vì một thành phần phụ tạm thời lỗi.

Đảm bảo endpoint được expose qua HTTP. Chỉ tạo bean Actuator hoặc thêm dependency chưa đủ nếu endpoint không được expose hoặc management server chỉ bind vào loopback.

## 3. Kiểm tra cổng service và cổng health check

Một lỗi phổ biến là đăng ký service ở cổng 8080 nhưng health endpoint chạy trên cổng management 9091. Nếu check dùng cổng 8080, request có thể tới nhầm ứng dụng hoặc nhận 404. Nếu service đăng ký port 9091 trong khi API nghiệp vụ lắng nghe 8080, consumer lại gọi sai cổng.

Phân biệt ba giá trị:

| Giá trị | Dùng cho | Ví dụ |
|---|---|---|
| Service port | Port consumer dùng để gọi API service | 8080 |
| Health check port | Port Consul Agent dùng để gọi endpoint check | 9091 |
| Published host port | Port trên host được ánh xạ tới container | 18080 hoặc 19091 |

Health check URL có thể chỉ rõ port riêng, độc lập với service port trong catalog. Ví dụ service lắng nghe API ở 8080 nhưng management health ở 9091:

    service {
      name = "inventory-service"
      id   = "inventory-node-1"
      address = "inventory-service"
      port = 8080

      check {
        id       = "inventory-http-health"
        name     = "Inventory readiness"
        http     = "http://inventory-service:9091/actuator/health/readiness"
        method   = "GET"
        interval = "10s"
        timeout  = "2s"
      }
    }

Đây là service definition minh họa cho Consul Agent. Hostname inventory-service chỉ hợp lệ nếu Consul Agent phân giải được tên đó từ network của nó. Nếu agent chạy ở một container riêng không cùng network, cần dùng địa chỉ mà agent truy cập được.

### Không nhầm host port với container port

Trong Docker Compose, nếu khai báo 18080:8080, container khác trên cùng network thường gọi inventory-service:8080, không phải inventory-service:18080. Host port 18080 dành cho client đi qua Docker host.

Nếu Consul Agent chạy trên host, nó có thể cần gọi localhost:18080. Nếu Consul Agent chạy trong container cùng network với ứng dụng, nó nên gọi service DNS và container port. Nếu agent ở container khác network, cần kết nối network phù hợp hoặc advertised address có thể định tuyến.

## 4. Kiểm tra địa chỉ và network từ góc nhìn Consul Agent

Consul Agent là nơi thực hiện HTTP check. Từ chính agent, kiểm tra:

- DNS hostname có phân giải được không?
- IP và port có route tới được không?
- Process có lắng nghe trên interface có thể truy cập từ agent không?
- Network policy, firewall hoặc security group có chặn traffic không?
- Agent và service có cùng network namespace hoặc network bridge phù hợp không?

Ví dụ với Docker Compose, nếu container Consul tên consul-agent và service tên inventory-service, cần bảo đảm cả hai cùng tham gia một network:

    services:
      consul-agent:
        image: hashicorp/consul:1.20
        networks:
          - backend

      inventory-service:
        image: example/inventory-service:1.0
        networks:
          - backend
        expose:
          - "8080"
          - "9091"

    networks:
      backend:

expose không phải firewall rule và không thay thế network membership. Điều quan trọng là Consul Agent có thể kết nối tới cổng đang lắng nghe của ứng dụng.

Kiểm tra từ container agent (nếu image có curl và công cụ DNS):

    docker compose exec consul-agent sh
    getent hosts inventory-service
    curl -v --connect-timeout 2 http://inventory-service:9091/actuator/health/readiness

Nếu image Consul không có curl, dùng một debug container gắn vào đúng network để kiểm tra đường đi; cần giữ nguyên góc nhìn DNS/network của agent. Kiểm tra từ laptop hoặc container của ứng dụng không thay thế được bước này.

Với Kubernetes, Consul Agent có thể chạy dạng sidecar/DaemonSet hoặc một topology khác. Chạy lệnh kiểm tra từ đúng pod/container agent; xác định check đang dùng Pod IP, Service DNS hay localhost. localhost trong container độc lập trỏ về chính container đó; trong sidecar cùng pod network namespace, localhost có thể truy cập cổng của container ứng dụng trong cùng pod.

### Kiểm tra bind address

Ứng dụng bind vào 127.0.0.1 chỉ nhận kết nối loopback. Nếu Consul Agent ở container/pod khác, request tới IP container sẽ thất bại dù curl localhost bên trong ứng dụng thành công.

Với service cần nhận kết nối từ network, để Spring Boot lắng nghe trên interface phù hợp, thường là 0.0.0.0 trong container. Sau đó quảng bá địa chỉ service có thể truy cập từ consumer và check URL có thể truy cập từ agent. Không đăng ký localhost làm service address khi consumer nằm ở nơi khác.

## 5. Kiểm tra HTTP status, method và timeout

Consul HTTP check thường coi response 2xx là passing. Các response 3xx, 4xx hoặc 5xx không đáp ứng điều kiện passing sẽ làm check critical; redirect có thể hoạt động khác tùy cấu hình follow redirect và giới hạn redirect. Để chẩn đoán dễ dàng, trỏ check thẳng vào endpoint health cuối cùng thay vì endpoint redirect.

Kiểm tra:

- Method phải phù hợp với endpoint, thông thường dùng GET cho Actuator health.
- URL không được trỏ vào endpoint nghiệp vụ yêu cầu tham số hoặc body.
- Endpoint không trả 401/403 do Spring Security.
- Endpoint không trả 404 do sai base path hoặc endpoint chưa expose.
- Endpoint không trả 503 khi readiness chưa đạt hoặc dependency cần thiết chưa sẵn sàng.
- Timeout check đủ cho response bình thường nhưng không quá dài để che giấu service treo.

Ví dụ cấu hình check với timeout và interval:

    check {
      id       = "inventory-readiness"
      name     = "Inventory readiness"
      http     = "http://inventory-service:9091/actuator/health/readiness"
      method   = "GET"
      interval = "15s"
      timeout  = "3s"
    }

Interval 15 giây và timeout 3 giây chỉ là giá trị minh họa. Chọn dựa trên startup time, p95/p99 của endpoint health và yêu cầu phát hiện lỗi. Timeout quá ngắn tạo false critical khi tải cao; timeout quá dài làm chậm phát hiện lỗi thật.

## 6. Kiểm tra authentication, Spring Security và Consul ACL

Một health endpoint có thể trả 401 Unauthorized hoặc 403 Forbidden nếu Spring Security bảo vệ Actuator. Consul Agent không tự đăng nhập bằng session của người dùng. Cần chọn chính sách rõ ràng:

1. Chỉ expose một endpoint readiness tối giản trong mạng nội bộ và cho phép agent truy cập endpoint đó.
2. Hoặc cấu hình HTTP check gửi header xác thực phù hợp, đồng thời quản lý secret bằng secret store và giới hạn quyền đọc.

Ví dụ Spring Security cho phép riêng readiness endpoint; matcher thực tế phải khớp path và context path của ứng dụng:

    http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/actuator/health/readiness").permitAll()
        .requestMatchers("/actuator/**").hasRole("OPS")
        .anyRequest().authenticated()
    );

Chỉ cho phép endpoint health tối giản, không mở toàn bộ /actuator/**. Kiểm tra management.endpoints.web.exposure.include đã expose endpoint tương ứng và management server không bị giới hạn vào interface mà agent không truy cập được.

### Gửi header cho HTTP check

Consul HTTP check hỗ trợ khai báo header gửi cùng request. Nếu endpoint yêu cầu token, cấu hình header theo cú pháp của service definition/Consul version đang dùng. Ví dụ HCL minh họa:

    check {
      id       = "inventory-authenticated-health"
      name     = "Inventory authenticated readiness"
      http     = "http://inventory-service:9091/actuator/health/readiness"
      method   = "GET"
      interval = "15s"
      timeout  = "3s"
      header = {
        Authorization = ["Bearer HEALTH_CHECK_TOKEN"]
      }
    }

Cấu trúc header trong HCL là map từ tên header tới danh sách giá trị; khi gửi qua JSON API, dùng cấu trúc tương ứng của API. Kiểm tra schema của phiên bản Consul đang triển khai trước khi áp dụng. Không lưu token trực tiếp trong file cấu hình commit vào Git. Ưu tiên template/secret injection, quyền file chặt chẽ và xoay vòng credential.

### Phân biệt Consul ACL và quyền HTTP endpoint của ứng dụng

Có hai lớp quyền độc lập:

- Consul ACL: kiểm soát ai được gọi Consul Agent/Server API, đăng ký service, đọc catalog hoặc sửa cấu hình registry.
- HTTP health endpoint auth: kiểm soát Consul Agent có được gọi endpoint /actuator/health/... của ứng dụng hay không.

Token có quyền service:write để đăng ký service không tự động là credential hợp lệ để gọi endpoint Actuator của ứng dụng. Ngược lại, bearer token của ứng dụng không cấp quyền đọc/ghi Consul catalog.

Với ACL bật, xác nhận agent/service registration dùng token có quyền ghi service phù hợp theo policy của Consul; consumer cần quyền đọc service/node phù hợp để tra cứu. Nếu agent check một endpoint có authentication riêng, cung cấp header/token dành riêng cho check đó. Không dùng master/management token cho mọi workload.

## 7. Kiểm tra TLS và HTTPS health check

Nếu URL check dùng https://, Consul Agent phải tin cậy CA cấp certificate và hostname trong URL phải khớp SAN của certificate. Các lỗi thường gặp:

- Dùng https:// trong khi ứng dụng chỉ lắng nghe HTTP.
- Dùng hostname không có trong certificate SAN.
- Agent thiếu CA nội bộ hoặc trust bundle.
- Certificate hết hạn hoặc chain không đầy đủ.
- Cấu hình skip verify khiến check pass nhưng bỏ qua xác minh danh tính server.

Ví dụ check HTTPS:

    check {
      id       = "inventory-https-health"
      name     = "Inventory HTTPS readiness"
      http     = "https://inventory.internal:9443/actuator/health/readiness"
      method   = "GET"
      interval = "15s"
      timeout  = "3s"
      tls_skip_verify = false
    }

Đảm bảo Consul Agent được cấu hình CA/trust store phù hợp. Chỉ dùng bỏ xác minh TLS tạm thời để chẩn đoán trong môi trường cô lập; không để tls_skip_verify = true làm cấu hình production lâu dài.

## 8. Cấu hình Spring Cloud Consul Discovery

Khi dùng Spring Cloud Consul, client có thể tự đăng ký service và tạo HTTP health check dựa trên cấu hình discovery. Ví dụ:

    spring:
      application:
        name: inventory-service
      cloud:
        consul:
          host: consul-agent
          port: 8500
          discovery:
            enabled: true
            register: true
            service-name: inventory-service
            health-check-path: /actuator/health/readiness
            health-check-interval: 15s

Property health-check-path là đường dẫn tương đối được Spring Cloud Consul dùng để tạo check URL. Host, port và advertised address của instance phải phù hợp với nơi Consul Agent gọi check. Nếu ứng dụng dùng management port riêng, cấu hình thêm health-check URL/port theo property được hỗ trợ bởi release train đang dùng hoặc khai báo check riêng bằng Consul service definition.

Các property Spring Cloud Consul có thể thay đổi theo phiên bản. Kiểm tra spring-configuration-metadata.json và reference đúng release train, đặc biệt khi dùng management.server.port, HTTPS, health check header hoặc custom address.

Không nhầm spring.cloud.consul.port (cổng Consul Agent API mà client kết nối) với cổng HTTP của ứng dụng được đăng ký. Hai cổng này phục vụ hai luồng khác nhau.

## 9. Service definition mẫu với Consul Agent

Khi cần kiểm soát check URL độc lập với cấu hình ứng dụng, có thể đăng ký service bằng file definition:

    service {
      name = "inventory-service"
      id   = "inventory-node-1"
      address = "inventory-service"
      port = 8080
      tags = ["api", "internal"]

      check {
        id       = "inventory-readiness"
        name     = "Inventory readiness"
        http     = "http://inventory-service:9091/actuator/health/readiness"
        method   = "GET"
        interval = "15s"
        timeout  = "3s"
      }
    }

Trong ví dụ, consumer gọi service port 8080, còn Consul Agent gọi readiness endpoint ở port 9091. Địa chỉ inventory-service phải phân giải được từ agent. Nếu service chạy trên host, dùng địa chỉ/port host mà agent truy cập được; nếu chạy trong cùng Compose network, dùng service DNS và container port.

Không đăng ký cùng một service từ cả Spring Cloud Consul và file service definition mà không có kế hoạch quản lý ID rõ ràng. Hai cơ chế có thể tạo hai service/check record khác nhau hoặc ghi đè theo ID; xác định một chủ sở hữu registration cho mỗi instance.

## 10. Kiểm tra bằng Consul API và CLI

### Agent API

Xem service và check tại agent cục bộ:

    curl -s http://127.0.0.1:8500/v1/agent/services
    curl -s http://127.0.0.1:8500/v1/agent/checks

### Health API

Xem mọi instance của service:

    curl -s http://consul-server:8500/v1/health/service/inventory-service

Chỉ lấy instance passing:

    curl -s "http://consul-server:8500/v1/health/service/inventory-service?passing=1"

Nếu service có trong kết quả không lọc nhưng biến mất khi thêm passing=1, hãy xem trạng thái từng check để biết check nào critical. Health API là góc nhìn catalog/health; Agent API giúp tìm check output ở node cụ thể.

### Consul CLI

    consul catalog services
    consul health checks inventory-service
    consul members

Các lệnh cần chạy trong môi trường có Consul CLI và endpoint/token phù hợp. Khi có nhiều datacenter/namespace/partition, xác nhận đang truy vấn đúng phạm vi.

## 11. Phân biệt HTTP check với TCP và TTL check

Chọn loại check theo điều muốn xác nhận:

| Loại check | Xác nhận điều gì? | Giới hạn |
|---|---|---|
| HTTP | Endpoint HTTP trả status mong muốn | Có thể critical do path, auth, TLS hoặc ứng dụng trả lỗi |
| TCP | Có thể mở kết nối tới host/port | Không chứng minh API hoặc dependency bên trong đang khỏe |
| TTL | Agent nhận heartbeat/pass trước TTL | Cần ứng dụng hoặc tiến trình phụ gửi cập nhật đúng hạn |
| Script | Lệnh kiểm tra tùy chỉnh chạy thành công | Cần quản lý quyền thực thi và rủi ro chạy script trên agent |

Không đổi HTTP check thành TCP check chỉ để dashboard chuyển xanh nếu mục tiêu là xác nhận readiness của API. TCP check có thể passing trong khi endpoint trả 500. Ngược lại, HTTP check có thể critical do endpoint bảo vệ bằng auth dù process vẫn khỏe; khi đó sửa quyền/headers là đúng hơn đổi loại check.

## 12. Deregister sau khi critical kéo dài

Consul hỗ trợ cấu hình tự hủy đăng ký service sau khi check critical liên tục trong một khoảng thời gian, thường dùng deregister_critical_service_after trong service check. Ví dụ:

    check {
      id                               = "inventory-readiness"
      name                             = "Inventory readiness"
      http                             = "http://inventory-service:9091/actuator/health/readiness"
      interval                         = "15s"
      timeout                          = "3s"
      deregister_critical_service_after = "5m"
    }

Chỉ dùng tính năng này khi muốn xóa service bị critical kéo dài khỏi catalog. Nó không sửa nguyên nhân check và không thay thế cơ chế restart/recovery của ứng dụng. Chọn thời gian đủ lớn để tránh deregister nhầm khi có sự cố mạng ngắn; xác minh service có tự đăng ký lại sau khi process phục hồi.

## 13. Bảng triệu chứng và cách xử lý

| Output/triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| 404 Not Found | Sai path, context path hoặc Actuator base path | Gọi đúng endpoint thực tế; kiểm tra management mapping |
| 401 Unauthorized | Health endpoint yêu cầu authentication | Cho phép endpoint readiness nội bộ hoặc cấu hình header/token cho check |
| 403 Forbidden | Spring Security, proxy hoặc policy từ chối | Kiểm tra matcher/role/ACL và request headers |
| connection refused | Sai port hoặc process chưa lắng nghe | Đối chiếu service port và health port; kiểm tra bind address |
| i/o timeout | Firewall/network policy, endpoint chậm hoặc timeout quá ngắn | Thử từ agent, kiểm tra route và đo latency; điều chỉnh timeout hợp lý |
| no such host | Agent không phân giải được hostname | Kiểm tra network membership, DNS và service alias |
| TLS/certificate error | CA, SAN, expiry hoặc scheme sai | Cài CA đúng, dùng hostname khớp cert và kiểm tra chain |
| Check pass trong container app nhưng critical ở Consul | Test từ sai network namespace | Chạy cùng request từ Consul Agent hoặc debug container cùng network |
| Catalog có service nhưng passing=1 không có | Check critical hoặc warning tùy filter | Đọc từng check output và sửa nguyên nhân |
| Critical kéo dài rồi service biến mất | Cấu hình deregister critical timeout | Kiểm tra deregister_critical_service_after và registration lifecycle |

## 14. Ví dụ quy trình khôi phục thực tế

Giả sử Consul UI báo inventory-service critical với output HTTP GET tới http://inventory-service:9091/actuator/health/readiness trả 404.

1. Mở Agent API để xác nhận check ID và URL mà agent thực hiện.
2. Chạy curl -i từ container Consul Agent tới đúng URL.
3. Gọi thử /actuator/health và /actuator/health/readiness để xác định endpoint nào đang được expose.
4. Kiểm tra management.endpoints.web.exposure.include có health, health probes có được bật và context/base path có bị thay đổi không.
5. Cập nhật health-check-path hoặc service definition tới path đúng.
6. Chờ ít nhất một health-check interval, sau đó đọc lại Agent API và Health API.
7. Xác nhận instance xuất hiện trong truy vấn passing=1 và consumer gọi đúng advertised service address.

Ví dụ khác: output là 401. Khi đó path và port có thể đúng; vấn đề nằm ở Spring Security. Cho phép riêng readiness endpoint trong mạng backend hoặc thêm header check được quản lý bằng secret. Sau khi sửa, xác nhận check pass và các endpoint quản trị khác vẫn được bảo vệ.

Không xóa service rồi đăng ký lại như bước đầu tiên. Nếu check definition sai, đăng ký lại cùng cấu hình sẽ tạo lại trạng thái critical và làm mất dấu vết chẩn đoán hữu ích.

## Checklist triển khai

1. Ghi lại service ID, check ID, URL và output critical từ đúng Consul Agent.
2. Kiểm tra path theo context path, Actuator base path và management port.
3. Phân biệt service port, health-check port và published host port.
4. Gọi đúng URL từ network namespace của Consul Agent.
5. Bảo đảm ứng dụng bind trên interface agent có thể truy cập và DNS phân giải được.
6. Xác nhận method, status 2xx, timeout và redirect behavior.
7. Kiểm tra Spring Security và HTTP header nếu endpoint yêu cầu authentication.
8. Phân biệt Consul ACL token với credential của endpoint ứng dụng.
9. Với HTTPS, kiểm tra CA, certificate SAN và TLS chain; không bỏ verify lâu dài.
10. Chỉ có một cơ chế quản lý registration cho mỗi instance hoặc phối hợp ID rõ ràng.
11. Chọn interval, timeout và critical deregistration delay phù hợp với SLO.
12. Xác nhận check passing và instance xuất hiện trong Health API với passing=1.

## Kết luận

Consul báo critical thường có nghĩa Agent không hoàn thành health check theo cấu hình, dù service có thể đã được đăng ký. Hãy đọc check output và kiểm tra đúng URL từ chính network của Agent; đối chiếu path, context path, service/management port, DNS, bind address, HTTP status, TLS và quyền endpoint. Tách riêng Consul ACL khỏi authentication của ứng dụng, sau đó xác minh lại bằng Agent API và Health API. Khi check chuyển passing và instance xuất hiện trong truy vấn passing=1, mới kết luận đường health check đã được khôi phục.
