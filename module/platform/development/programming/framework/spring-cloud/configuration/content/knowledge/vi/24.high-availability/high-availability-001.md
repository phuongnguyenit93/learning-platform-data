# Chạy nhiều Config Server cùng nguồn cấu hình

Config Server là thành phần trung tâm cung cấp Environment cho các ứng dụng Spring Boot. Nếu chỉ chạy một instance, lỗi tiến trình, máy chủ, mạng hoặc kết nối backend có thể khiến nhiều Config Client không thể khởi động hay làm mới cấu hình. Có thể tăng tính sẵn sàng bằng cách chạy nhiều Config Server instance cùng phục vụ một nguồn cấu hình và đặt chúng sau load balancer hoặc service discovery.

Các instance phải có cấu hình vận hành tương đương: cùng backend, repository/ref, search paths, chính sách giải mã, bảo mật và broker nếu dùng Spring Cloud Bus. Với Git backend, mỗi Config Server thường giữ bản clone/cache cục bộ riêng, vì vậy cùng trỏ tới một remote repository chưa đủ để bảo đảm mọi request tức thời trả cùng commit. Cần quản lý label bất biến, theo dõi trạng thái từng replica và kiểm tra kết quả trực tiếp trước khi đưa node vào pool.

## 1. Kiến trúc nhiều Config Server

Mô hình cơ bản có nhiều Config Server instance nằm sau một địa chỉ ổn định:

~~~mermaid
flowchart TD
    C1[Config Client A] --> LB[Load Balancer / config.internal]
    C2[Config Client B] --> LB
    C3[Config Client C] --> LB
    LB --> S1[Config Server replica 1]
    LB --> S2[Config Server replica 2]
    LB --> S3[Config Server replica 3]
    S1 --> R[(Shared configuration backend)]
    S2 --> R
    S3 --> R
~~~

Mỗi replica nhận request HTTP từ load balancer, đọc cùng nguồn cấu hình và trả Environment. Khi một replica ngừng hoạt động, load balancer loại node đó khỏi pool và chuyển request sang các node khỏe còn lại.

Các thành phần:

| Thành phần | Trách nhiệm |
|---|---|
| Config Client | Yêu cầu cấu hình theo application, profile và label |
| Load balancer | Phân phối request tới Config Server replica đang sẵn sàng |
| Config Server replicas | Cung cấp cùng API và cùng chính sách đọc cấu hình |
| Configuration backend | Nguồn dữ liệu chung như Git, JDBC, Vault hoặc filesystem được chia sẻ |
| Health/readiness checks | Phát hiện instance không thể phục vụ request an toàn |
| Spring Cloud Bus (nếu dùng) | Phân phối sự kiện refresh đến các ứng dụng tham gia |

Config Server API chủ yếu xử lý request đọc nên thường không cần session affinity. Tuy nhiên, cần bảo đảm TLS, authentication và routing hoạt động nhất quán trên mọi node.

## 2. Chạy nhiều replica với cùng Git repository

Với Git backend, mỗi Config Server clone repository về filesystem của chính instance. Các replica có thể dùng cùng URI remote nhưng clone/cache độc lập:

~~~yaml
server:
  port: 8888

spring:
  application:
    name: config-server
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          default-label: main
          clone-on-start: true
          search-paths:
            - services
            - shared
~~~

Đưa cấu hình tương đương vào mọi Config Server replica. Mỗi instance cần:

- Truy cập được cùng Git remote qua DNS, firewall và TLS.
- Có credential đọc repository hợp lệ.
- Dùng cùng default label và search paths.
- Có đủ quyền ghi vào thư mục clone cục bộ của chính nó.
- Có dung lượng filesystem và quyền sở hữu thư mục phù hợp.
- Có chính sách cập nhật clone/cache tương thích với yêu cầu nhất quán.

`clone-on-start: true` giúp phát hiện sớm lỗi clone trong quá trình khởi động. Nó không có nghĩa mọi replica sẽ luôn giữ cùng commit sau đó; từng node vẫn có thể cập nhật clone vào các thời điểm khác nhau theo cơ chế refresh của Git backend.

Không nên để nhiều Config Server ghi vào cùng một thư mục clone cục bộ dùng chung qua filesystem mạng nếu chưa có thiết kế khóa và đồng bộ được hỗ trợ. Mô hình thông thường là mỗi replica có working copy riêng và cùng fetch từ một remote Git repository.

## 3. Giữ kết quả nhất quán giữa các replica

Hai replica cùng URI vẫn có thể trả kết quả khác nhau trong một khoảng thời gian nếu local clone của chúng đang ở các commit khác nhau. Ví dụ node A đã fetch commit mới nhưng node B vẫn đang phục vụ commit trước.

Để giảm rủi ro:

1. Dùng Git tag hoặc commit SHA bất biến cho các bản phát hành cần tái lập.
2. Tránh để production phụ thuộc vào branch di chuyển liên tục nếu yêu cầu mọi instance cùng trả một cấu hình tại cùng thời điểm.
3. Khi phát hành label mới, kiểm tra tất cả Config Server replica đã đọc được ref đó.
4. So sánh `version` trong Environment response giữa các node.
5. Chỉ chuyển client hoặc load balancer sang label mới sau khi backend sẵn sàng trên toàn pool.
6. Ghi lại label/commit được sử dụng để hỗ trợ rollback và điều tra.

Ví dụ gọi cùng endpoint trực tiếp tới từng replica:

~~~bash
curl --fail "https://config-1.internal:8888/orders-service/prod/release-2026.11"
curl --fail "https://config-2.internal:8888/orders-service/prod/release-2026.11"
curl --fail "https://config-3.internal:8888/orders-service/prod/release-2026.11"
~~~

So sánh các trường `name`, `profiles`, `label`, `version` và các key quan trọng trong `propertySources`. Nếu `version` khác nhau, chưa nên xem pool là đồng nhất cho label đó.

Nếu sử dụng branch label như `main`, các replica có thể fetch ở thời điểm khác nhau. Trong trường hợp này cần xác định rõ độ trễ chấp nhận được, cơ chế refresh repository và cách rollout; không giả định load balancer tự đồng bộ Git clone.

## 4. Dùng chung backend không phải lúc nào cũng là dùng chung cache

Mỗi backend có đặc tính khác nhau:

| Backend | Cách các replica chia sẻ dữ liệu | Điểm cần kiểm soát |
|---|---|---|
| Git | Cùng remote repository, mỗi replica có clone riêng | Fetch/refresh timing, label, commit và credentials |
| JDBC | Cùng database hoặc cụm database phục vụ cùng dữ liệu | Read consistency, schema, quyền SELECT và replica lag |
| Vault | Cùng Vault cluster, mỗi replica xác thực bằng identity phù hợp | Policy, auth method, token/lease và secret path |
| Native filesystem | Cùng nội dung được mount hoặc triển khai đồng bộ tới mọi node | Đồng bộ file, atomic deployment và quyền đọc |

Với JDBC, nếu dùng read replicas của database, cần xem độ trễ replication. Một Config Server có thể đọc dữ liệu mới trong khi node khác đọc từ replica chưa đồng bộ. Với Vault, các node cần cùng policy và khả năng truy cập secret path; không chia sẻ token quản trị rộng rãi chỉ để làm đơn giản cấu hình.

Với native filesystem, không nên để mỗi container có một thư mục cấu hình local khác nhau mà vẫn coi chúng là cùng nguồn. Nếu mount volume chung, cần bảo đảm cách cập nhật file atomic và mọi node nhìn thấy cùng phiên bản.

## 5. Cấu hình client gọi địa chỉ ổn định

Config Client nên gọi một địa chỉ logic ổn định của load balancer thay vì gắn cứng vào một Config Server instance:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    active: prod
  config:
    import: "configserver:https://config.internal"
  cloud:
    config:
      label: release-2026.11
~~~

`config.internal` trỏ tới load balancer hoặc ingress phân phối request tới các replica. Khi một node bị loại khỏi pool, client tiếp tục dùng cùng URL và không cần biết topology nội bộ đã thay đổi.

Đảm bảo load balancer:

- Chỉ chuyển request tới node đã sẵn sàng.
- Dùng HTTPS và kiểm tra chứng chỉ đúng hostname.
- Có timeout hợp lý cho request đọc cấu hình.
- Không retry vô hạn khi backend đang lỗi.
- Không cache response của endpoint Environment theo cách làm client nhận cấu hình cũ ngoài dự kiến.
- Hỗ trợ kết nối từ mọi mạng chạy Config Client.

Nếu dùng discovery-first lookup thay cho địa chỉ load balancer, client cần service discovery và service ID của Config Server được cấu hình thống nhất. Đây là một lựa chọn triển khai khác; không nên đồng thời cấu hình nhiều cơ chế định tuyến mà chưa xác định rõ thứ tự và hành vi failover của phiên bản Spring Cloud đang dùng.

## 6. Load balancing và failover

Load balancer có thể hoạt động ở tầng hạ tầng (L4/L7), ingress hoặc gateway. Với Config Server, điều quan trọng là health check phải loại node không thể cung cấp cấu hình đúng, chứ không chỉ node bị tắt process.

Các quyết định cần xác định:

- **Health check path:** endpoint kiểm tra trạng thái ứng dụng, thường dựa trên Actuator health.
- **Readiness:** node đã khởi tạo backend và có thể phục vụ request.
- **Liveness:** process còn sống và không bị treo nghiêm trọng.
- **Connection draining:** khi triển khai hoặc dừng node, ngừng nhận request mới và cho request đang chạy hoàn tất.
- **Timeout/retry:** giới hạn thời gian kết nối và số lần retry ở load balancer/client.
- **Capacity:** còn đủ replica khỏe để chịu tải khi một node hoặc một zone gặp sự cố.

Ví dụ bật health probes trong Spring Boot:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
~~~

Các endpoint readiness và liveness thường có dạng `/actuator/health/readiness` và `/actuator/health/liveness` khi health probes được bật. Cấu hình cụ thể phụ thuộc phiên bản Spring Boot và nền tảng triển khai.

Không dùng liveness để kiểm tra mọi phụ thuộc từ xa. Nếu Git hoặc database tạm thời không truy cập được, restart liên tục tất cả Config Server có thể làm sự cố nặng hơn. Readiness có thể xét khả năng phục vụ backend theo chính sách; liveness nên tập trung vào tình trạng process.

## 7. Kiểm tra backend trong readiness

Một Config Server process có thể trả health UP nhưng không thể đọc repository hoặc database cần thiết. Với môi trường production, cần quyết định health/readiness phản ánh những điều kiện nào:

- Kết nối Git remote và ref cần thiết có thể được đọc.
- Database query cần thiết thành công và trả dữ liệu hợp lệ.
- Vault có thể được truy cập bằng identity của server.
- Các file cấu hình trên filesystem đã được mount.
- Keystore và khóa giải mã cần thiết đã sẵn sàng.

Spring Cloud Config có health indicator cho repository trong các cấu hình được hỗ trợ. Có thể cấu hình kiểm tra repository và label cụ thể theo phiên bản; nếu health mặc định chưa phản ánh đúng yêu cầu, bổ sung readiness check ở tầng triển khai hoặc custom health indicator.

Không đánh dấu node ready chỉ vì HTTP `/actuator/health` trả 200 nếu backend bắt buộc đang lỗi. Ngược lại, cũng không nên làm readiness phụ thuộc vào mọi dịch vụ không liên quan đến việc đọc cấu hình.

## 8. Đồng bộ cấu hình vận hành giữa các Config Server

Ngoài backend URI, các replica cần cùng chính sách:

| Nhóm | Cần đồng nhất |
|---|---|
| Server runtime | Spring Boot/Spring Cloud compatible versions, active profiles và port/context path |
| Repository | Git URI, default label, search paths, clone behavior hoặc database schema |
| Security | Authentication, authorization, TLS, CORS và trusted proxy settings |
| Encryption | Keystore/alias hoặc encrypt.key tương thích trên mọi node |
| Bus | Binder, broker, destination và quyền publish/consume |
| Actuator | Endpoint exposure, health checks và management port |
| Deployment | Resource limits, filesystem permissions, environment variables và secret mounts |

Đặc biệt, nếu Config Server giải mã ciphertext trước khi trả về client, mọi replica phải có khả năng giải mã cùng các giá trị mà backend chứa. Nếu một node thiếu alias hoặc keystore version, request có thể thành công qua node này nhưng lỗi qua node khác, tạo ra lỗi ngẫu nhiên theo load balancing.

Với key rotation, triển khai key ring/keystore theo giai đoạn để tất cả node đều đọc được ciphertext đang hỗ trợ. Chỉ đổi alias mặc định hoặc thu hồi khóa cũ sau khi mọi replica đã có key material phù hợp và dữ liệu đã được chuyển đổi theo kế hoạch.

## 9. Kết hợp nhiều Config Server với Spring Cloud Bus

Trong hệ thống nhiều Config Server, Bus giúp phân phối sự kiện refresh đến các Config Client. Config Server replicas và các client cần tham gia cùng broker/destination theo cấu hình:

~~~yaml
spring:
  cloud:
    bus:
      destination: config-events
~~~

Ví dụ endpoint phát refresh trên Config Server:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,busrefresh
~~~

Gửi POST đến địa chỉ load balancer:

~~~bash
curl -i -X POST "https://config.internal/actuator/busrefresh"
~~~

Replica nhận request sẽ phát sự kiện qua broker. Các client nhận sự kiện tự gọi lại Config Server để lấy cấu hình. Broker và destination phải nhất quán giữa các thành phần tham gia; mỗi client cũng cần truy cập được địa chỉ Config Server ổn định.

Không nhầm lẫn ba việc:

1. Git/JDBC/Vault đã có dữ liệu mới.
2. Config Server replicas có thể đọc dữ liệu mới.
3. Config Clients đã nhận sự kiện và áp dụng cấu hình mới.

Bus chỉ hỗ trợ phân phối tín hiệu. Nó không bảo đảm mọi bean có thể cập nhật nóng hoặc mọi client đã hoàn tất refresh. Cần quan sát client và xác minh hành vi sau sự kiện.

## 10. Triển khai rolling update

Khi nâng cấp Config Server, nên thay node từng phần để luôn còn đủ capacity phục vụ client:

1. Chuẩn bị artifact và cấu hình phiên bản mới.
2. Kiểm tra tương thích Spring Boot/Spring Cloud, backend, encryption và Bus.
3. Khởi động một replica mới ngoài pool hoặc ở trạng thái chưa nhận traffic.
4. Kiểm tra health, readiness, repository response, label/version và giải mã property.
5. Đưa replica vào pool và theo dõi lỗi, latency, backend access.
6. Drain một replica cũ, chờ request đang xử lý hoàn tất rồi dừng node.
7. Lặp lại cho đến khi toàn bộ pool chạy phiên bản mới.
8. Kiểm tra lại kết quả qua load balancer và trực tiếp trên từng replica.

Không rollout tất cả Config Server cùng lúc nếu client phụ thuộc vào dịch vụ này để khởi động hoặc refresh. Giữ đủ capacity trong suốt quá trình và có thể rollback artifact/cấu hình nếu health hoặc response không đạt yêu cầu.

## 11. Kiểm thử failover

Kiểm thử HA phải chứng minh client vẫn lấy được cấu hình khi một replica lỗi. Một kịch bản staging:

1. Khởi động tối thiểu hai Config Server replica cùng backend.
2. Gọi endpoint Environment qua load balancer và xác nhận response hợp lệ.
3. Tạm dừng hoặc drain một replica.
4. Gọi lại endpoint nhiều lần qua load balancer.
5. Xác nhận request chỉ tới replica còn khỏe và vẫn trả cùng application/profile/label/version.
6. Khởi động lại node đã dừng và kiểm tra node đồng bộ lại backend trước khi vào pool.
7. Thử backend tạm thời không khả dụng để quan sát readiness và hành vi client.
8. Thử refresh event qua Bus nếu hệ thống sử dụng Bus.

Không chỉ kiểm tra HTTP 200. So sánh metadata `name`, `profiles`, `label`, `version`, property source names và một số key không nhạy cảm để phát hiện node trả cấu hình lệch.

## 12. Giám sát hệ thống nhiều replica

Theo dõi tối thiểu:

- Số replica đang ready và số lần node bị loại khỏi load balancer.
- HTTP request rate, latency, timeout và tỷ lệ lỗi theo status code.
- Lỗi kết nối backend, Git fetch/clone, JDBC query hoặc Vault authentication.
- Commit/version được trả bởi từng replica.
- Lỗi decrypt và tình trạng keystore/alias.
- Broker connection, event publish/consume và client refresh failures.
- CPU, memory, filesystem và connection pool.

Nên gắn log với instance ID để biết request được xử lý bởi replica nào. Tránh ghi secret hoặc toàn bộ Environment vào log. Khi cần so sánh các node, dùng metadata commit/label và property key không nhạy cảm.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách kiểm tra |
|---|---|---|
| Client thỉnh thoảng nhận cấu hình cũ | Git clone/cache của các replica chưa cùng commit | Gọi trực tiếp từng node, so sánh `version` và label |
| Một số request lỗi 5xx | Node chưa ready, backend lỗi hoặc credential khác nhau | Kiểm tra load balancer target health và log từng replica |
| Replica mới khởi động nhưng không clone được Git | Network, credential, TLS hoặc quyền filesystem sai | Kiểm tra remote từ node và clone-on-start logs |
| Node UP nhưng không đọc được repository | Health check chưa bao gồm backend readiness | Kiểm tra repository health và readiness policy |
| Decrypt lỗi ngẫu nhiên | Keystore/alias hoặc encrypt.key không đồng nhất | So sánh key material/alias trên từng replica |
| JDBC replica trả dữ liệu cũ | Database read replica có replication lag | Kiểm tra read consistency và database topology |
| Bus refresh chỉ tới một số client | Broker, destination, ACL hoặc consumer binding không đồng nhất | Kiểm tra connection và event consumption từng client |
| Rolling update làm client mất cấu hình | Drain hoặc dừng quá nhiều node cùng lúc | Kiểm tra capacity, readiness và deployment strategy |
| TLS lỗi sau khi thêm node | Certificate/SAN hoặc trust store không đồng nhất | Kiểm tra hostname, chain và secret mount trên node mới |

## 14. Checklist triển khai HA

- [ ] Có ít nhất hai Config Server replica ở failure domain phù hợp.
- [ ] Tất cả replica dùng cùng backend và quy ước application/profile/label.
- [ ] Git clone/cache độc lập, được kiểm tra đồng bộ theo commit/ref.
- [ ] Credential và quyền truy cập backend giống nhau về phạm vi cần thiết.
- [ ] Keystore/alias hoặc khóa mã hóa tương thích trên tất cả replica.
- [ ] Config Client gọi địa chỉ load balancer hoặc discovery endpoint ổn định.
- [ ] Load balancer chỉ gửi traffic tới node ready.
- [ ] Health/readiness có xét các dependency cần thiết để phục vụ cấu hình.
- [ ] Timeout, retry, connection draining và capacity được xác định.
- [ ] Bus destination/broker đồng nhất nếu dùng refresh events.
- [ ] Đã thử failover khi một replica dừng.
- [ ] Đã so sánh version và property sources trên từng replica.
- [ ] Có giám sát, audit và quy trình rolling update/rollback.

Chạy nhiều Config Server cùng một nguồn cấu hình giúp loại bỏ điểm lỗi đơn ở tầng cung cấp Environment. Độ sẵn sàng thực tế phụ thuộc vào cả load balancer, backend, key material, broker và khả năng đồng bộ phiên bản giữa các replica. Khi mỗi node chỉ nhận traffic sau khi sẵn sàng, client dùng một địa chỉ ổn định và đội vận hành kiểm tra version trên từng replica, hệ thống có thể chịu lỗi node mà vẫn cung cấp cấu hình nhất quán.
