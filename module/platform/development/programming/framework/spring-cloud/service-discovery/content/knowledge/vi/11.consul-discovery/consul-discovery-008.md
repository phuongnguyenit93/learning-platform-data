# Phân biệt Consul Catalog API, Health API và DNS

Consul cung cấp nhiều cách để tìm một service đã đăng ký, nhưng các cách này trả lời những câu hỏi khác nhau. **Catalog API** cho biết service và instance nào đã được đăng ký. **Health API** bổ sung trạng thái các health check để xác định instance nào đang passing, warning hoặc critical. **DNS interface** biến thông tin service thành bản ghi A hoặc SRV để ứng dụng có thể phân giải tên mà không cần gọi HTTP API trực tiếp.

Chọn sai giao diện có thể khiến consumer nhận cả instance không khỏe, không lấy được port hoặc hiểu nhầm rằng service đã biến mất. Bài này phân biệt dữ liệu, endpoint, cách lọc và giới hạn của từng giao diện; đồng thời giải thích Spring Cloud Consul sử dụng HTTP API như thế nào.

## 1. Ba giao diện, ba mục đích

Giả sử Consul đang lưu ba instance của `inventory-service`:

| Instance | Endpoint | Health |
|---|---|---|
| inventory-a | 10.0.1.11:8081 | passing |
| inventory-b | 10.0.1.12:8081 | warning |
| inventory-c | 10.0.1.13:8081 | critical |

Ba giao diện có thể đưa ra góc nhìn khác nhau về cùng dữ liệu:

| Giao diện | Câu hỏi chính | Dữ liệu trả về | Lọc health |
|---|---|---|---|
| Catalog API | Đã đăng ký service/instance nào? | Service name, node, address, port, tags, metadata | Không tự lọc theo health check |
| Health API | Instance và các check của service đang ở trạng thái nào? | Node, Service, Checks, trạng thái check | Có thể yêu cầu chỉ trả instance passing |
| DNS | Tên service phân giải thành địa chỉ nào? | Bản ghi A hoặc SRV | Lọc theo cấu hình DNS, có thể khác Health API |

Không nên xem ba giao diện là ba cách gọi tương đương. Catalog là góc nhìn về registration; Health là góc nhìn về trạng thái; DNS là giao diện phân giải tên và địa chỉ cho client.

## 2. Catalog API: tra cứu dữ liệu đăng ký

Catalog là sổ đăng ký trung tâm của Consul. Nó theo dõi node, service, địa chỉ, port, tag, metadata và các thông tin mà Consul cần cho discovery và service mesh.

Các endpoint thường dùng:

| Endpoint | Mục đích |
|---|---|
| `GET /v1/catalog/services` | Liệt kê service name và các tag đã đăng ký trong datacenter |
| `GET /v1/catalog/service/:service_name` | Liệt kê node và registration cung cấp một service |
| `GET /v1/catalog/node/:node_name` | Xem thông tin node và service đăng ký trên node |
| `GET /v1/catalog/nodes` | Liệt kê node trong catalog |

### 2.1. Liệt kê service

Ví dụ:

~~~bash
curl http://127.0.0.1:8500/v1/catalog/services
~~~

Response minh họa:

~~~json
{
  "consul": [],
  "inventory-service": ["v1", "warehouse"],
  "order-service": ["v2"]
}
~~~

Mỗi key là service name; giá trị là danh sách tag của service. Endpoint này phù hợp để kiểm tra service nào đã được công bố, nhưng không cho biết instance nào đang khỏe.

### 2.2. Liệt kê instance đã đăng ký

Ví dụ:

~~~bash
curl http://127.0.0.1:8500/v1/catalog/service/inventory-service
~~~

Response rút gọn minh họa:

~~~json
[
  {
    "Node": "node-a",
    "Address": "10.0.1.11",
    "ServiceID": "inventory-a",
    "ServiceName": "inventory-service",
    "ServiceAddress": "10.0.1.11",
    "ServicePort": 8081,
    "ServiceTags": ["v1"],
    "ServiceMeta": {
      "zone": "zone-a"
    }
  },
  {
    "Node": "node-b",
    "Address": "10.0.1.12",
    "ServiceID": "inventory-b",
    "ServiceName": "inventory-service",
    "ServiceAddress": "10.0.1.12",
    "ServicePort": 8081,
    "ServiceTags": ["warehouse"],
    "ServiceMeta": {
      "zone": "zone-b"
    }
  }
]
~~~

Catalog API cho phép xem các endpoint đã đăng ký và metadata của chúng. Nó không mặc định loại instance chỉ vì health check đang warning hoặc critical. Vì thế, nếu dùng catalog service list để chọn endpoint gọi request, consumer phải tự truy vấn và xử lý health đúng cách.

### 2.3. Catalog API không phải Health API

Một instance xuất hiện trong Catalog chứng minh rằng registration đang tồn tại trong catalog. Nó không chứng minh endpoint đang sẵn sàng nhận traffic.

Consul tách `/catalog` và `/health` có chủ đích: một số triển khai muốn tra cứu registration mà không bật hoặc không phụ thuộc vào health checking. Health API mới là giao diện truy vấn các thông tin liên quan đến check.

Catalog cũng có endpoint ghi dữ liệu như `/v1/catalog/register` và `/v1/catalog/deregister`. Đây là cơ chế cấp thấp. Tài liệu Consul khuyến nghị thường nên dùng Agent API để đăng ký service và health check vì agent quản lý anti-entropy và đồng bộ với catalog. Đặc biệt, việc ghi một check entry qua Catalog không tự thiết lập một HTTP, TCP hoặc TTL probe để kiểm tra node; cấu hình check thực tế phải được tạo qua agent hoặc cấu hình agent.

## 3. Health API: tra cứu instance kèm health check

Health API trả về dữ liệu registration cùng các check liên quan. Endpoint quan trọng nhất khi tìm instance của một service là:

~~~text
GET /v1/health/service/:service
~~~

Ví dụ:

~~~bash
curl http://127.0.0.1:8500/v1/health/service/inventory-service
~~~

Response thường gồm ba phần:

- `Node`: thông tin node đang chạy instance.
- `Service`: thông tin service registration như ID, name, address, port, tags và metadata.
- `Checks`: các check ở cấp node hoặc service gắn với kết quả truy vấn.

Ví dụ response rút gọn:

~~~json
[
  {
    "Node": {
      "Node": "node-a",
      "Address": "10.0.1.11"
    },
    "Service": {
      "ID": "inventory-a",
      "Service": "inventory-service",
      "Address": "10.0.1.11",
      "Port": 8081,
      "Tags": ["v1"]
    },
    "Checks": [
      {
        "CheckID": "service:inventory-a",
        "Name": "Inventory HTTP check",
        "Status": "passing"
      }
    ]
  }
]
~~~

Khác với Catalog API, Health API cho phép consumer biết vì sao một instance được xem là khỏe hoặc không khỏe.

### 3.1. Tham số passing

Mặc định, endpoint `/v1/health/service/:service` không chỉ lọc các instance passing. Có thể thêm query parameter `passing`:

~~~bash
curl "http://127.0.0.1:8500/v1/health/service/inventory-service?passing"
~~~

Khi `passing` là true, Consul chỉ trả các node có tất cả health check ở trạng thái `passing`. Một instance có check `warning` hoặc `critical` sẽ không được trả về trong kết quả này.

| Giá trị query | Hành vi |
|---|---|
| Không truyền `passing` hoặc `passing=false` | Trả các instance phù hợp với query, kèm checks và trạng thái của chúng |
| `passing=true` | Chỉ trả các node mà tất cả checks đều passing |

Đây là khác biệt quan trọng khi viết consumer. Nếu yêu cầu là chỉ gửi request đến instance đã vượt qua mọi check, hãy dùng `passing=true` hoặc áp dụng quy tắc lọc tương đương ở client.

### 3.2. Những endpoint Health API hữu ích khác

| Endpoint | Dùng để |
|---|---|
| `GET /v1/health/checks/:service` | Xem các check gắn với một service |
| `GET /v1/health/node/:node` | Xem các check của một node |
| `GET /v1/health/state/:state` | Liệt kê check theo trạng thái như passing, warning hoặc critical |
| `GET /v1/health/service/:service` | Lấy instance của service cùng checks |

Khi một instance không xuất hiện trong truy vấn `passing=true`, hãy gọi endpoint không lọc hoặc `/v1/health/checks/:service` để tìm check nào đang warning hoặc critical. Đừng kết luận instance đã bị deregister chỉ từ một kết quả passing rỗng.

### 3.3. Health check ở cấp node và service

Một instance có thể chịu ảnh hưởng từ nhiều check:

- Check ở cấp node đánh giá tình trạng của máy hoặc agent. Nếu node critical, các service trên node đó cũng có thể bị xem là không khỏe.
- Check ở cấp service đánh giá riêng endpoint hoặc tiến trình cung cấp service.
- Một service có nhiều check; điều kiện `passing=true` yêu cầu tất cả checks liên quan phải passing.

Vì vậy, một HTTP check của ứng dụng trả passing chưa chắc đủ nếu node có check critical khác. Khi chẩn đoán, cần đọc toàn bộ `Checks` trong response thay vì chỉ nhìn một check service.

## 4. DNS interface: phân giải service thành địa chỉ

Consul DNS cho phép ứng dụng truy vấn service bằng tên miền mà không cần gọi HTTP API hoặc tích hợp trực tiếp Consul SDK.

Mặc định, Consul DNS sử dụng domain `consul` và thường lắng nghe trên port `8600` của agent. Ví dụ tên service:

~~~text
inventory-service.service.consul
~~~

Để client sử dụng được tên này, DNS resolver của máy hoặc môi trường phải chuyển tiếp truy vấn domain `.consul` đến Consul agent phù hợp. Không phải mọi máy đều tự động biết cách phân giải tên `.consul`.

### 4.1. Bản ghi A

Truy vấn A lấy địa chỉ IPv4 của các instance được DNS trả về:

~~~bash
dig @127.0.0.1 -p 8600 inventory-service.service.consul A
~~~

Response rút gọn:

~~~text
inventory-service.service.consul. 0 IN A 10.0.1.11
inventory-service.service.consul. 0 IN A 10.0.1.12
~~~

Bản ghi A cung cấp địa chỉ IP, không cung cấp port của service. Ứng dụng phải biết port theo cấu hình hoặc dùng một cơ chế khác để lấy port.

### 4.2. Bản ghi SRV

SRV record cung cấp hostname đích và port đã đăng ký:

~~~bash
dig @127.0.0.1 -p 8600 inventory-service.service.consul SRV
~~~

Response minh họa:

~~~text
inventory-service.service.consul. 0 IN SRV 1 1 8081 node-a.node.dc1.consul.
inventory-service.service.consul. 0 IN SRV 1 1 8081 node-b.node.dc1.consul.
~~~

SRV phù hợp khi client cần biết cả địa chỉ đích và port. Tuy nhiên, thư viện resolver của ứng dụng phải hỗ trợ truy vấn SRV; nhiều HTTP client thông thường chỉ phân giải A/AAAA cho hostname và không tự tiêu thụ SRV record.

### 4.3. Truy vấn theo tag

Có thể dùng tag trong tên truy vấn để giới hạn nhóm service, ví dụ:

~~~bash
dig @127.0.0.1 -p 8600 v1.inventory-service.service.consul SRV
~~~

Cách này hữu ích khi cùng một service name có nhiều tag như `v1`, `v2`, `blue` hoặc `warehouse`. Tag phải được đăng ký đúng và tên truy vấn tuân theo cú pháp DNS của Consul.

DNS cũng hỗ trợ truy vấn node, datacenter và prepared query theo cú pháp riêng. Với các yêu cầu lọc phức tạp hoặc cần dữ liệu metadata chi tiết, Health API hoặc prepared query thường phù hợp hơn.

## 5. Health filtering của DNS khác Health API

Không nên mặc định DNS và Health API có cùng chính sách lọc.

Health API có query parameter `passing=true` để chỉ lấy node có tất cả checks passing. DNS có cấu hình `only_passing` ở agent:

| Giao diện | Cấu hình lọc | Hành vi |
|---|---|---|
| Health API | Query `?passing` | Chỉ trả instance có tất cả checks passing |
| Consul DNS | `dns_config.only_passing = false` (mặc định) | Loại node có check critical; node warning vẫn có thể xuất hiện |
| Consul DNS | `dns_config.only_passing = true` | Chỉ trả node có checks passing; loại cả warning và critical |

Ví dụ cấu hình agent:

~~~hcl
dns_config {
  only_passing = true
}
~~~

Nếu DNS giữ mặc định `only_passing=false`, một instance warning có thể vẫn được phân giải. Nếu ứng dụng yêu cầu chỉ gọi instance hoàn toàn passing, cần bật cấu hình này hoặc dùng Health API với `passing=true`.

Chính sách lọc cần được kiểm tra ở chính agent đang trả lời truy vấn. Hai môi trường có cấu hình DNS khác nhau có thể trả tập địa chỉ khác nhau dù cùng nhìn vào một catalog.

## 6. So sánh dữ liệu và khả năng của ba giao diện

| Tiêu chí | Catalog API | Health API | DNS |
|---|---|---|---|
| Danh sách service | Có | Không phải mục đích chính | Truy vấn từng tên |
| Instance endpoint | Có | Có | Có địa chỉ qua A; có cả port qua SRV |
| Tags | Có | Có | Có thể truy vấn theo tag |
| Metadata đầy đủ | Có | Có trong service registration | Không trả metadata tùy ý như API |
| Health check chi tiết | Không | Có | Không |
| Lọc chỉ passing | Không phải bộ lọc health | Có `passing=true` | Có `only_passing` |
| Giao thức | HTTP API | HTTP API | DNS |
| Phụ thuộc SDK hoặc HTTP client | Có | Có | Cần DNS resolver |
| Hợp với ứng dụng legacy | Cần tích hợp API | Cần tích hợp API | Thường dễ dùng nếu ứng dụng đã dùng DNS |
| Kiểm tra/chẩn đoán | Xem registration | Xem trạng thái và lý do health | Kiểm tra tên có phân giải thành endpoint |

Cách chọn:

- Dùng Catalog API khi cần kiểm tra inventory, service name, tag, metadata hoặc registration.
- Dùng Health API khi ứng dụng cần quyết định dựa trên trạng thái check, cần lọc passing hoặc cần chẩn đoán vì sao instance không khỏe.
- Dùng DNS khi ứng dụng chỉ cần phân giải tên thành địa chỉ và có thể chấp nhận các giới hạn của DNS, resolver và cache.

## 7. Spring Cloud Consul sử dụng giao diện nào?

Spring Cloud Consul Service Discovery sử dụng **Consul HTTP API** cho đăng ký và discovery. Nó không mặc định dùng Consul DNS để triển khai `DiscoveryClient`.

Khi ứng dụng dùng `spring-cloud-starter-consul-discovery`:

1. Auto-configuration tạo Consul client và discovery integration.
2. Ứng dụng đăng ký service qua Consul theo cấu hình.
3. Spring Cloud Consul truy vấn API để tìm instance.
4. `ConsulDiscoveryClient` chuyển kết quả thành `ServiceInstance` của Spring Cloud Commons.
5. Spring Cloud LoadBalancer có thể dùng danh sách instance đó để chọn endpoint.

Do đó, khi debug Spring Cloud Consul, hãy kiểm tra HTTP API và cấu hình discovery client. Việc một tên service phân giải được qua DNS không chứng minh `DiscoveryClient` của ứng dụng đang trả cùng danh sách.

### 7.1. Property query-passing

Spring Cloud Consul có property:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        query-passing: true
~~~

Khi bật `query-passing`, Spring Cloud Consul thêm tham số `passing` vào truy vấn `/v1/health/service/:service`. Consul sẽ chỉ trả các instance mà tất cả health check đều passing.

Theo tài liệu property hiện hành, mặc định `spring.cloud.consul.discovery.query-passing` là `false`. Khi để mặc định, Spring Cloud Consul có thể nhận cả các instance warning hoặc critical trong kết quả Health API rồi trả cho ứng dụng tùy logic xử lý. Nếu yêu cầu chỉ dùng instance passing, hãy bật property này và kiểm thử hành vi của đúng release train.

Property này điều khiển truy vấn Health API của Spring Cloud Consul; nó không thay đổi cấu hình `only_passing` của DNS agent.

### 7.2. Cấu hình health check khi đăng ký

Spring Cloud Consul thường đăng ký HTTP health check trỏ đến `/actuator/health`. Một số thuộc tính có thể điều chỉnh:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        register-health-check: true
        health-check-path: /actuator/health
        health-check-interval: 15s
        query-passing: true
~~~

Tên property và các tùy chọn chi tiết cần đối chiếu với phiên bản Spring Cloud Consul đang dùng. Nếu ứng dụng có context path, servlet path hoặc management port riêng, health check path và địa chỉ phải khớp với endpoint thực tế.

`register-health-check` điều khiển việc đăng ký health check với Consul; `query-passing` điều khiển cách consumer truy vấn instance. Hai property có mục đích khác nhau.

## 8. Cache, TTL và dữ liệu cũ

Ba giao diện có hành vi cache khác nhau.

### 8.1. Catalog và Health API

Catalog và Health API hỗ trợ blocking query để client chờ dữ liệu thay đổi thay vì polling liên tục. Một số endpoint cũng hỗ trợ agent caching với background refresh. Consumer có thể dùng index và `X-Consul-Index` để tiếp tục truy vấn từ thay đổi mới nhất theo cơ chế blocking query.

Không nên gửi truy vấn liên tục với tần suất cao nếu có thể dùng blocking query hoặc cache phù hợp. Cần xử lý timeout và index theo tài liệu API.

### 8.2. DNS TTL

Mặc định, Consul DNS trả TTL bằng 0, nghĩa là không khuyến khích resolver cache câu trả lời. Có thể cấu hình TTL cho service lookup để giảm số truy vấn và tải lên Consul.

TTL dài giúp giảm query nhưng tăng nguy cơ client giữ địa chỉ cũ sau khi instance thay đổi. TTL ngắn giúp cập nhật nhanh hơn nhưng tăng số lần truy vấn.

Ngoài TTL dương, cần chú ý **negative caching**: một số hệ điều hành và DNS forwarder lưu kết quả không tìm thấy service. Khi service vừa được đăng ký lại, client vẫn có thể thấy lỗi không phân giải được cho đến khi negative cache hết hạn.

### 8.3. DNS không phải load balancer đầy đủ

Consul DNS có thể trả nhiều A hoặc SRV record và có thể xáo trộn thứ tự để phân phối lựa chọn. Tuy nhiên, DNS không kiểm soát request cụ thể:

- Resolver hoặc ứng dụng có thể chỉ chọn một địa chỉ.
- Client có thể cache kết quả và tái sử dụng connection.
- Một số thư viện không hỗ trợ SRV.
- DNS không cung cấp đầy đủ metadata hoặc health detail cho logic nghiệp vụ.
- Khi endpoint vừa lỗi, cache và thời gian refresh có thể khiến client tiếp tục dùng địa chỉ cũ.

Nếu cần chọn instance theo zone, metadata, tag, health hoặc chính sách retry phức tạp, dùng Health API qua discovery client và load balancer phù hợp hơn.

## 9. Bảo mật và quyền truy cập

Catalog API và Health API chịu sự kiểm soát của Consul ACL. Token phải có quyền đọc service và node phù hợp; nếu kết quả bị ACL lọc, response có thể thiếu một phần dữ liệu mà không nhất thiết biểu hiện như lỗi HTTP thông thường.

Một số nguyên tắc:

- Chỉ cấp quyền `service:read` và `node:read` theo nhu cầu thực tế.
- Bảo vệ token trong secret store hoặc cơ chế quản lý cấu hình an toàn.
- Không đưa token vào URL query string hoặc log.
- Giới hạn mạng truy cập HTTP API và DNS agent.
- Bảo vệ các endpoint đăng ký và deregistration để workload không được phép không thể giả mạo service.
- Không lưu credential hoặc secret trong service metadata hay tags.

DNS thường cung cấp ít thông tin hơn HTTP API, nhưng việc phân giải được tên nội bộ vẫn có thể làm lộ topology. Hãy giới hạn mạng có thể truy vấn DNS và thiết kế ACL phù hợp với môi trường.

## 10. Quy trình chọn API khi xử lý sự cố

Khi `inventory-service` không được consumer tìm thấy, hãy kiểm tra theo thứ tự:

1. **Catalog:** gọi `/v1/catalog/services` để xác nhận service name có tồn tại.
2. **Catalog instance:** gọi `/v1/catalog/service/inventory-service` để xem registration, host, port và metadata.
3. **Health:** gọi `/v1/health/service/inventory-service` để đọc các check của từng instance.
4. **Passing filter:** gọi thêm `?passing` để xác nhận có instance nào vượt qua tất cả check.
5. **DNS:** dùng `dig` truy vấn A và SRV đến Consul agent để kiểm tra góc nhìn DNS.
6. **Spring Cloud:** nếu consumer dùng DiscoveryClient, kiểm tra `query-passing`, endpoint Health API và danh sách `ServiceInstance` thực tế.
7. **Network:** thử kết nối từ chính mạng của consumer đến endpoint được trả về.

Ví dụ bảng diễn giải kết quả:

| Kết quả | Cách hiểu có thể có |
|---|---|
| Catalog không có service | Registration chưa tồn tại, sai datacenter/namespace hoặc ACL lọc kết quả |
| Catalog có instance, Health trả critical | Registration còn nhưng health check không đạt |
| Health API có instance, `passing` trả rỗng | Không có instance nào có tất cả check passing |
| Health API passing có instance nhưng DNS không trả | DNS policy, datacenter, domain hoặc agent khác góc nhìn |
| DNS trả địa chỉ nhưng HTTP request lỗi | Port, network, TLS hoặc ứng dụng có vấn đề |
| DNS phân giải được nhưng Spring DiscoveryClient không có instance | Spring Cloud Consul dùng HTTP API; kiểm tra `query-passing`, ACL và cấu hình client |

Đừng chỉ nhìn dashboard Consul. Hãy truy vấn cùng service name, datacenter và namespace từ đúng agent/consumer đang gặp sự cố để tránh so sánh hai góc nhìn khác nhau.

## 11. Ví dụ tổng hợp

Giả sử Consul có ba instance `inventory-service`:

- `inventory-a`: passing.
- `inventory-b`: warning.
- `inventory-c`: critical.

Các truy vấn có thể cho kết quả:

| Truy vấn | Kết quả minh họa |
|---|---|
| `GET /v1/catalog/service/inventory-service` | Có cả ba registration |
| `GET /v1/health/service/inventory-service` | Có cả ba registration kèm checks |
| `GET /v1/health/service/inventory-service?passing` | Chỉ có inventory-a |
| DNS với `only_passing=false` | Có thể trả inventory-a và inventory-b; loại inventory-c |
| DNS với `only_passing=true` | Chỉ trả inventory-a |
| Spring Cloud Consul `query-passing=false` | Không yêu cầu server lọc passing; ứng dụng có thể nhận cả warning/critical |
| Spring Cloud Consul `query-passing=true` | Yêu cầu Health API chỉ trả instance passing |

Ví dụ này cho thấy cùng một catalog có thể tạo ra tập kết quả khác nhau tùy giao diện và chính sách lọc. Vì thế, khi triển khai consumer, hãy chọn rõ mức độ health cần thiết thay vì mặc định mọi giao diện sẽ loại cùng một instance.

## 12. Ghi nhớ

- Catalog API trả dữ liệu registration; nó không tự lọc instance theo health check.
- Health API trả service instance cùng checks; `passing=true` chỉ trả node có tất cả checks passing.
- Consul DNS phân giải tên service thành A hoặc SRV record; SRV chứa port, A chỉ chứa địa chỉ IP.
- DNS có `only_passing`; mặc định false có thể vẫn trả instance warning, còn true chỉ giữ instance passing.
- Spring Cloud Consul dùng HTTP API cho registration và discovery, không mặc định dùng DNS.
- `spring.cloud.consul.discovery.query-passing` mặc định false; bật true để yêu cầu Health API lọc instance passing.
- DNS TTL mặc định bằng 0, nhưng resolver có thể negative-cache kết quả không tìm thấy.
- Khi debug, hãy đối chiếu Catalog, Health, DNS và kết quả DiscoveryClient từ cùng datacenter/namespace.

Catalog, Health và DNS là ba góc nhìn bổ sung cho service discovery của Consul. Hiểu dữ liệu và chính sách lọc của từng giao diện giúp consumer chọn đúng instance, đồng thời giúp người vận hành xác định lỗi nằm ở registration, health check, DNS resolver hay cấu hình Spring Cloud.

## Tài liệu tham khảo

- [Consul Catalog HTTP API](https://developer.hashicorp.com/consul/api-docs/catalog)
- [Consul Health HTTP API](https://developer.hashicorp.com/consul/api-docs/health)
- [Consul DNS overview](https://developer.hashicorp.com/consul/docs/discover/dns)
- [Consul DNS static queries](https://developer.hashicorp.com/consul/docs/discover/service/static)
- [Consul DNS configuration and TTL](https://developer.hashicorp.com/consul/docs/discover/dns/configure)
- [Spring Cloud Consul Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Consul configuration properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
