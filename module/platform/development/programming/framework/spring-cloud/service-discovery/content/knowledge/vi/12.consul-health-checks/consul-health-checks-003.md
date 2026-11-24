# Địa chỉ mà Consul agent truy cập khác địa chỉ bên gọi sử dụng

Khi Consul kiểm tra sức khỏe một dịch vụ, **Consul agent là bên chủ động gọi endpoint health check**. Khi consumer tìm dịch vụ trong catalog, consumer lại kết nối đến **địa chỉ và cổng được đăng ký cho service**. Hai luồng này có thể đi qua những mạng khác nhau, vì vậy địa chỉ health check và địa chỉ mà consumer sử dụng không nhất thiết giống nhau.

Ví dụ, ứng dụng tồn kho chạy trong container ở cổng 8080. Consul agent cùng Docker network gọi được container bằng tên DNS nội bộ:

~~~text
http://inventory-api:8080/actuator/health
~~~

Consumer ở ngoài máy Docker lại truy cập ứng dụng qua địa chỉ host đã publish:

~~~text
http://203.0.113.10:18080
~~~

Nếu đăng ký nhầm địa chỉ nội bộ làm địa chỉ service cho consumer, health check vẫn có thể PASS nhưng consumer không kết nối được. Ngược lại, địa chỉ service có thể truy cập được từ consumer trong khi Consul agent không gọi được endpoint health check. Muốn chẩn đoán đúng, cần xác định ai là bên gọi, gọi từ network namespace nào và đang dùng trường địa chỉ nào.

## 1. Ba góc nhìn địa chỉ cần phân biệt

Trong môi trường Consul, thường có ít nhất ba loại địa chỉ khác nhau:

| Loại địa chỉ | Ai sử dụng? | Mục đích |
|---|---|---|
| Địa chỉ của Consul agent | Các Consul agent khác hoặc ứng dụng kết nối API/DNS của agent | Giao tiếp cluster, nhận request vào agent và cung cấp API/DNS |
| Địa chỉ health check | Chính Consul agent đang quản lý check | Gọi HTTP/TCP/gRPC endpoint hoặc chạy check tại môi trường agent |
| Địa chỉ service được đăng ký | Consumer tra cứu service trong catalog | Kết nối đến ứng dụng thực tế |

Cần phân biệt thêm hai trường địa chỉ của agent:

- **bind address** là địa chỉ agent dùng để lắng nghe/giao tiếp trên mạng cluster.
- **advertise address** là địa chỉ agent công bố để các agent khác liên hệ với nó.
- **client address** là địa chỉ agent lắng nghe các giao diện client như HTTP API, DNS hoặc gRPC theo cấu hình.

Các địa chỉ này mô tả chính Consul agent. Chúng không tự động trở thành địa chỉ của ứng dụng mà agent quản lý. Địa chỉ service được công bố nằm trong service registration, thường gồm trường Address và Port.

## 2. Luồng health check và luồng request của consumer

Với HTTP health check, Consul agent định kỳ gửi request đến URL được khai báo trong check. Agent nhận response, đánh giá trạng thái và cập nhật health status của service trong catalog.

Consumer thực hiện luồng khác:

1. Consumer truy vấn Consul DNS hoặc HTTP API để tìm service.
2. Consul trả về các service instance phù hợp cùng địa chỉ và port đã đăng ký.
3. Consumer chọn một instance theo chính sách của ứng dụng hoặc load balancer.
4. Consumer mở kết nối đến địa chỉ và port của instance đó.

Sơ đồ sau minh họa hai đường đi độc lập:

~~~mermaid
flowchart LR
    subgraph DockerNet["Docker network nội bộ"]
        Agent["Consul agent"]
        App["inventory-api:8080"]
        Agent -->|"HTTP health check"| App
    end
    Catalog["Consul catalog"]
    Agent -->|"Registration và health status"| Catalog
    Consumer["Consumer ở mạng bên ngoài"]
    Catalog -->|"Service address: 203.0.113.10:18080"| Consumer
    Consumer -->|"HTTP request"| Host["Docker host :18080"]
    Host -->|"Port mapping 18080 → 8080"| App
~~~

Agent kiểm tra container qua tên DNS nội bộ và cổng 8080. Consumer nhận địa chỉ host cùng cổng publish 18080. Hai địa chỉ khác nhau nhưng cùng dẫn đến một ứng dụng.

Một service có thể có trạng thái health là passing trong khi địa chỉ service không thể truy cập từ một số consumer. Health status chỉ phản ánh kết quả kiểm tra từ góc nhìn của check đã cấu hình; nó không chứng minh mọi mạng consumer đều có route đến service address.

## 3. Service Address và địa chỉ trong HTTP check

Service registration có thể khai báo địa chỉ mà consumer phải sử dụng:

~~~json
{
  "service": {
    "name": "inventory-service",
    "id": "inventory-node-a",
    "address": "203.0.113.10",
    "port": 18080,
    "checks": [
      {
        "http": "http://inventory-api:8080/actuator/health",
        "method": "GET",
        "interval": "10s",
        "timeout": "2s"
      }
    ]
  }
}
~~~

Trong ví dụ:

- service name là inventory-service.
- service ID inventory-node-a định danh registration cụ thể.
- Address 203.0.113.10 và Port 18080 là endpoint được công bố cho consumer.
- HTTP check gọi inventory-api:8080/actuator/health từ môi trường Consul agent.
- Agent thực hiện check định kỳ và cập nhật trạng thái của service.

Địa chỉ 203.0.113.10 là địa chỉ ví dụ dành cho tài liệu; thay bằng địa chỉ host hoặc DNS thực tế mà consumer có thể truy cập. Tên inventory-api phải phân giải được từ Consul agent và cổng 8080 phải được mở trên Docker network.

Nếu không chỉ định service address, Consul có thể sử dụng địa chỉ node làm địa chỉ service theo quy tắc đăng ký. Khi ứng dụng chạy sau NAT, port mapping hoặc proxy, nên khai báo rõ Address và Port để tránh công bố nhầm địa chỉ node/container không thể truy cập từ phía caller.

Trường HTTP trong health check không thay thế Address và Port của service. Check URL cho biết agent cần gọi đâu để xác nhận sức khỏe; service address cho biết consumer cần kết nối đến đâu để sử dụng dịch vụ.

## 4. Ví dụ agent chạy trên cùng máy với ứng dụng

Nếu Consul agent và ứng dụng chạy trực tiếp trên cùng máy, agent có thể kiểm tra qua loopback:

~~~json
{
  "service": {
    "name": "inventory-service",
    "id": "inventory-local-8080",
    "address": "192.0.2.25",
    "port": 8080,
    "check": {
      "http": "http://127.0.0.1:8080/actuator/health",
      "interval": "10s",
      "timeout": "2s"
    }
  }
}
~~~

Ở đây, 127.0.0.1 là địa chỉ loopback mà agent gọi trên chính máy đang chạy. Consumer ở máy khác sử dụng 192.0.2.25:8080. Hai địa chỉ khác nhau nhưng cùng tới một tiến trình nếu firewall và routing cho phép.

Không đăng ký 127.0.0.1 làm service address nếu consumer chạy ở máy khác. Với consumer, 127.0.0.1 luôn có nghĩa là chính máy của consumer, không phải máy chạy provider.

Nếu agent chạy trên máy khác với ứng dụng, loopback của agent sẽ trỏ về máy agent. Khi đó check phải dùng hostname hoặc IP mà agent thực sự có thể truy cập, ví dụ địa chỉ private của máy ứng dụng.

## 5. Ví dụ ứng dụng trong Docker sau NAT/port mapping

Giả sử môi trường gồm:

- Consul agent chạy trong container consul-agent.
- Ứng dụng inventory chạy trong container inventory-api, lắng nghe cổng 8080.
- Hai container cùng nằm trong network discovery.
- Docker host publish cổng 18080 và chuyển tiếp đến cổng 8080 của inventory-api.
- Consumer nằm ngoài Docker network và truy cập host qua địa chỉ 203.0.113.10.

Cấu hình service registration có thể dùng:

~~~json
{
  "service": {
    "name": "inventory-service",
    "id": "inventory-api-1",
    "address": "203.0.113.10",
    "port": 18080,
    "checks": [
      {
        "http": "http://inventory-api:8080/actuator/health",
        "interval": "10s",
        "timeout": "2s"
      }
    ]
  }
}
~~~

Đường đi của hai loại request:

| Request | Nguồn | Đích | Port |
|---|---|---|---:|
| Health check | consul-agent | inventory-api trong Docker network | 8080 |
| Request nghiệp vụ | Consumer bên ngoài | Docker host 203.0.113.10 | 18080 |
| Port forwarding | Docker host | inventory-api | 8080 |

Cấu hình này chỉ đúng nếu:

1. Consul agent phân giải được tên inventory-api.
2. Consul agent và inventory-api cùng kết nối network discovery.
3. Ứng dụng lắng nghe trên interface có thể truy cập từ network container, thường là 0.0.0.0 bên trong container.
4. Docker host thực sự publish 18080 đến đúng container và port 8080.
5. Consumer có route đến 203.0.113.10 và firewall cho phép kết nối.

Nếu agent chạy trên host thay vì trong container, URL health check có thể là http://127.0.0.1:18080/actuator/health hoặc một địa chỉ host-local phù hợp. Chọn URL dựa trên nơi agent chạy và đường mạng mà agent có thể đi qua.

Không dùng localhost trong check URL một cách máy móc. Nếu Consul agent chạy trong container riêng, localhost là chính container agent; nó không trỏ đến container ứng dụng.

## 6. Khi agent và consumer ở nhiều mạng khác nhau

Một dịch vụ có thể được nhìn thấy từ nhiều vùng mạng:

- Mạng nội bộ container dùng DNS service name và port nội bộ.
- Mạng máy chủ dùng private IP hoặc DNS nội bộ.
- Mạng bên ngoài dùng địa chỉ public, ingress hoặc reverse proxy.

Không có một địa chỉ duy nhất luôn truy cập được từ mọi vùng mạng. Việc chọn service address phải dựa trên nhóm consumer thực tế.

Có một số cách triển khai:

| Mô hình | Địa chỉ service công bố | Khi phù hợp |
|---|---|---|
| Mạng nội bộ dùng chung | Private IP hoặc DNS nội bộ | Agent và tất cả consumer cùng có route |
| Container sau port mapping | Host IP/DNS và host port đã publish | Consumer ở ngoài Docker network |
| Ứng dụng sau reverse proxy | DNS của proxy và port proxy | Consumer chỉ được phép truy cập qua gateway |
| Nhiều vùng mạng tách biệt | Registration riêng cho từng network hoặc endpoint trung gian | Các nhóm consumer không thể truy cập cùng một địa chỉ |

Nếu cùng một service được consumer ở nhiều mạng khác nhau sử dụng, hãy xác định rõ network nào là nguồn truy cập được hỗ trợ. Có thể đăng ký các service entry riêng với service name hoặc tag/metadata thể hiện network/zone, rồi để consumer truy vấn đúng nhóm. Cần cấu hình bộ lọc hoặc chính sách định tuyến ở consumer; metadata đơn thuần không tự thay đổi địa chỉ được trả về.

Nếu không thể bảo đảm một service address có thể truy cập từ mọi consumer, hãy đưa một gateway hoặc load balancer vào giữa và công bố địa chỉ của gateway. Gateway chịu trách nhiệm chuyển tiếp đến các instance nội bộ.

## 7. Địa chỉ của Consul agent không phải địa chỉ của service

Consul agent có các cấu hình mạng riêng. Ví dụ cấu hình minh họa:

~~~hcl
bind_addr = "10.10.0.12"
advertise_addr = "10.10.0.12"
client_addr = "127.0.0.1"
~~~

Ý nghĩa:

- bind_addr xác định địa chỉ agent sử dụng cho giao tiếp cluster.
- advertise_addr là địa chỉ agent công bố cho các agent khác.
- client_addr xác định các địa chỉ agent lắng nghe các giao diện client như HTTP API và DNS theo cấu hình.

Các giá trị này không thay thế cho service.address trong registration. Nếu Consul agent chạy trong container, advertise address cần phù hợp với khả năng kết nối giữa các agent. Nếu consumer cần gọi ứng dụng, consumer vẫn phải dùng service address và port của ứng dụng hoặc endpoint trung gian đã công bố.

Một số nhầm lẫn thường gặp:

| Cấu hình bị nhầm | Hậu quả |
|---|---|
| Dùng advertise_addr làm service address | Consumer kết nối đến Consul agent thay vì ứng dụng |
| Dùng client_addr của agent làm địa chỉ provider | Request có thể đi vào API/DNS của agent, không đến ứng dụng |
| Dùng địa chỉ container nội bộ cho consumer ngoài mạng | Consumer không có route đến container IP |
| Dùng địa chỉ public trong health check nội bộ khi firewall chặn hairpin NAT | Agent không gọi được check dù ứng dụng vẫn truy cập được từ mạng nội bộ |
| Dùng localhost trong check khi agent ở container khác | Agent gọi nhầm chính container agent |

## 8. Chẩn đoán khi health check PASS nhưng consumer không gọi được

Trường hợp này thường có nghĩa agent đã kiểm tra thành công endpoint health, nhưng service address trả về cho consumer không dùng được từ network của consumer.

Kiểm tra lần lượt:

1. **Xem registration:** đọc service Address, Port, ID và các check trong Consul catalog hoặc Agent API.
2. **Xác định vị trí agent:** agent chạy trên host, container hay máy riêng? Xác định network namespace của agent.
3. **Thử URL health từ đúng nơi:** chạy curl từ chính host/container của agent đến check URL. Lệnh chạy từ laptop của người vận hành không chứng minh agent có cùng khả năng truy cập.
4. **Thử service address từ consumer:** từ máy hoặc container consumer, gọi đúng Address và Port Consul trả về.
5. **Kiểm tra NAT/proxy/firewall:** xác minh port mapping, route, security group, firewall và reverse proxy.
6. **Kiểm tra DNS:** tên host có phân giải giống nhau trong các network không? DNS nội bộ của Docker có thể không tồn tại với consumer ngoài Docker.
7. **Đối chiếu HTTP response:** health endpoint có thể trả 200 nhưng API nghiệp vụ, path, TLS hoặc xác thực ở địa chỉ consumer vẫn có lỗi.

Ví dụ kiểm tra từ môi trường của agent:

~~~bash
curl -i --max-time 3 http://inventory-api:8080/actuator/health
~~~

Ví dụ kiểm tra từ consumer bên ngoài:

~~~bash
curl -i --max-time 3 http://203.0.113.10:18080/api/inventory
~~~

Hai lệnh phải được chạy từ hai môi trường tương ứng. Nếu chỉ chạy cả hai từ cùng một máy, kết quả có thể không phản ánh đường đi mạng thực tế.

## 9. Chẩn đoán khi consumer gọi được nhưng health check CRITICAL

Tình huống ngược lại xảy ra khi consumer truy cập service address thành công nhưng agent không gọi được check URL. Một số nguyên nhân:

- Check URL dùng localhost nhưng agent nằm trong container hoặc máy khác.
- Check URL dùng hostname chỉ consumer phân giải được, không tồn tại trong DNS của agent.
- Firewall chỉ cho phép subnet consumer, không cho phép subnet của Consul agent.
- Ứng dụng chỉ bind vào loopback, không lắng nghe trên interface container/private network.
- Health endpoint yêu cầu header hoặc chứng thư mà check chưa cấu hình.
- Timeout quá ngắn hoặc endpoint phụ thuộc một dịch vụ đang chậm.
- Check dùng HTTPS nhưng chứng thư không được agent tin cậy hoặc hostname không khớp.

Hãy sửa URL check hoặc cấu hình network/credential để agent có thể kiểm tra endpoint đúng cách. Không đánh dấu check là passing giả tạo để che lỗi kết nối. Nếu ứng dụng dùng TTL check thay cho HTTP check, cần phân biệt cơ chế: agent không chủ động gọi HTTP endpoint; tiến trình bên ngoài phải gửi cập nhật TTL định kỳ.

## 10. Health check HTTP và service address có thể dùng giao thức khác nhau

Health check và request nghiệp vụ có thể dùng giao thức hoặc endpoint khác nhau:

- Agent dùng HTTP nội bộ để kiểm tra /actuator/health.
- Consumer dùng HTTPS qua reverse proxy.
- Agent gọi TCP check đến cổng nội bộ.
- Consumer gọi API qua gateway có xác thực.

Điều này có thể hợp lệ nếu cả hai địa chỉ đều đại diện đúng cho cùng service và health check thực sự phản ánh khả năng phục vụ. Tuy nhiên, nếu health check chỉ kiểm tra tiến trình đang sống mà không kiểm tra dependency quan trọng, trạng thái passing có thể không phản ánh khả năng xử lý request nghiệp vụ.

Khi cấu hình HTTP check, có thể đặt method, interval, timeout và header theo khả năng của Consul phiên bản đang dùng. Nếu dùng TLS, bảo đảm agent tin cậy certificate. Tránh tắt xác minh TLS trong môi trường production chỉ để làm check chuyển sang passing.

Với health check có xác thực, không đặt secret trực tiếp vào file cấu hình được commit. Sử dụng cơ chế secret của môi trường và giới hạn quyền đọc cấu hình check. Endpoint health không nên trả về thông tin nội bộ hoặc dữ liệu nhạy cảm.

## 11. Service registration mẫu cho các kiểu mạng

### Agent trên cùng host

~~~json
{
  "service": {
    "name": "payment-service",
    "id": "payment-host-8080",
    "address": "192.0.2.50",
    "port": 8080,
    "check": {
      "http": "http://127.0.0.1:8080/actuator/health",
      "interval": "15s",
      "timeout": "3s"
    }
  }
}
~~~

Agent kiểm tra qua loopback; consumer dùng địa chỉ host 192.0.2.50:8080.

### Agent trong cùng Docker network

~~~json
{
  "service": {
    "name": "catalog-service",
    "id": "catalog-container-1",
    "address": "catalog-api",
    "port": 8080,
    "check": {
      "http": "http://catalog-api:8080/actuator/health",
      "interval": "10s",
      "timeout": "2s"
    }
  }
}
~~~

Cả agent và consumer cần phân giải được catalog-api và có route đến cổng 8080. Nếu consumer nằm ngoài Docker network, địa chỉ này không phù hợp; cần công bố endpoint host/proxy có thể truy cập từ consumer.

### Agent kiểm tra nội bộ, consumer qua reverse proxy

~~~json
{
  "service": {
    "name": "report-service",
    "id": "report-node-1",
    "address": "reports.example.internal",
    "port": 443,
    "checks": [
      {
        "http": "http://report-api:8080/actuator/health",
        "interval": "15s",
        "timeout": "3s"
      }
    ]
  }
}
~~~

Agent kiểm tra ứng dụng nội bộ qua Docker DNS. Consumer truy cập qua DNS và HTTPS của reverse proxy. Reverse proxy phải định tuyến đúng về report-api và xử lý TLS theo cấu hình.

Các địa chỉ trong ví dụ chỉ minh họa. Trước khi dùng, thay hostname, IP, port và path bằng thông tin của môi trường thực tế; kiểm tra khả năng truy cập từ cả agent và consumer.

## 12. Ảnh hưởng đến discovery và load balancing

Consul health status có thể được dùng để lọc instance khi consumer truy vấn các service passing. Ví dụ, client có thể yêu cầu chỉ trả về các instance đang passing. Tuy nhiên, lọc health không sửa được service address sai.

Có thể gặp hai trường hợp:

| Health check | Service address | Kết quả |
|---|---|---|
| Passing | Truy cập được từ consumer | Consumer có thể gọi instance |
| Passing | Không truy cập được từ consumer | Discovery trả instance nhưng request thất bại |
| Critical | Consumer vẫn truy cập được | Consumer truy vấn passing có thể bỏ qua instance |
| Critical | Không truy cập được | Instance vừa không khỏe theo check vừa không phục vụ được |

Load balancer nên sử dụng danh sách instance phù hợp với network của consumer. Nếu các consumer ở các network khác nhau, cần lọc theo zone/network hoặc trả về endpoint chung có thể truy cập. Đừng mặc định rằng mọi instance trong catalog đều có thể được mọi client gọi trực tiếp.

Ngay cả khi check passing, địa chỉ có thể trở nên lỗi thời sau khi container được tạo lại, IP thay đổi hoặc port mapping thay đổi. Hãy cập nhật registration khi endpoint đổi và theo dõi các service record cũ. Có thể cấu hình deregistration sau một khoảng thời gian ở trạng thái critical để dọn registration, nhưng khoảng thời gian phải phù hợp với chu kỳ check và hành vi triển khai.

## 13. Bảo mật và nguyên tắc vận hành

Địa chỉ service là dữ liệu định tuyến. Nếu registration công bố sai hoặc bị một workload không đáng tin sửa đổi, consumer có thể gửi request đến một host không mong muốn.

Một số nguyên tắc cần áp dụng:

- Giới hạn quyền đăng ký và cập nhật service trong Consul bằng ACL.
- Chỉ cho phép Consul agent và consumer truy cập các cổng cần thiết.
- Bảo vệ HTTP API và DNS interface của agent; không công khai client interface tùy tiện.
- Dùng TLS cho kết nối cần bảo vệ và xác minh certificate đúng cách.
- Không để metadata hoặc health endpoint chứa token, password hay dữ liệu nhạy cảm.
- Ghi nhận service ID, node, service address, port, check URL và trạng thái khi điều tra sự cố.
- Giữ cấu hình check và registration nhất quán với network thực tế sau mỗi lần triển khai.
- Khi thay đổi địa chỉ, xác minh cả agent check lẫn đường truy cập của consumer trước khi kết thúc rollout.

Không nên chỉ nhìn dashboard thấy màu xanh rồi kết luận dịch vụ sẵn sàng cho mọi caller. Cần xác minh đúng địa chỉ mà nhóm consumer sử dụng và đúng đường mạng mà request đi qua.

## 14. Quy trình thực hành

Thực hiện quy trình sau khi service health check chạy qua một địa chỉ nhưng consumer gọi qua địa chỉ khác:

1. Ghi lại địa chỉ và port của Consul agent, gồm bind/advertise/client nếu có liên quan.
2. Xác định vị trí chạy agent: host, container hay máy riêng.
3. Ghi lại URL check mà agent thực hiện và chạy thử từ đúng môi trường agent.
4. Ghi lại Service.Address và Service.Port trong registration.
5. Truy vấn service từ góc nhìn consumer để biết chính xác địa chỉ mà consumer nhận được.
6. Gọi thử địa chỉ đó từ consumer, không dùng kết quả test từ host khác thay thế.
7. Kiểm tra Docker DNS, port mapping, NAT, firewall, route và reverse proxy.
8. Sửa riêng check URL hoặc service address theo đúng vai trò của từng trường.
9. Chờ chu kỳ health check, xác minh trạng thái và gọi lại từ consumer.
10. Kiểm tra lại sau khi container hoặc agent khởi động lại để phát hiện địa chỉ cũ hoặc registration trùng.

Sau bài này, cần phân biệt rõ: **Consul agent gọi health check từ network của agent; consumer kết nối đến service address và port trong catalog; địa chỉ bind/advertise/client mô tả chính agent.** Chỉ khi cả hai đường đi đều đúng với mạng thực tế thì một service vừa được đánh giá khỏe, vừa có thể được consumer sử dụng.

