# Phân biệt bộ đệm khám phá, bộ đệm cân bằng tải và kết nối HTTP

Khi một consumer gọi service bằng tên logic như `inventory-service`, Spring Cloud phải tìm instance, chọn endpoint rồi gửi request qua HTTP client. Trên đường đi có thể xuất hiện ba cơ chế giữ dữ liệu hoặc tài nguyên: **bộ đệm discovery**, **bộ đệm của LoadBalancer** và **pool kết nối HTTP**.

Ba cơ chế này thường bị gọi chung là cache, nhưng chúng lưu những thứ khác nhau. Discovery cache giữ góc nhìn về registry; LoadBalancer cache giữ danh sách `ServiceInstance` dùng để lựa chọn; HTTP connection pool giữ các kết nối mạng đã mở để tái sử dụng. Mỗi cơ chế có vòng đời, thời hạn và cách xử lý lỗi riêng.

Hiểu đúng ba lớp giúp trả lời những câu hỏi vận hành quan trọng: Vì sao registry đã xóa instance nhưng consumer vẫn gọi đến nó? Vì sao tăng thời gian cache không làm giảm số lần TCP handshake? Vì sao đóng connection pool không làm mới danh sách instance? Bài này lần theo một request qua cả ba lớp và hướng dẫn cấu hình, quan sát, xử lý dữ liệu cũ.

## 1. Ba lớp nằm ở những vị trí khác nhau

Giả sử `order-service` cần gọi `inventory-service`, hiện có hai instance:

| Instance | Endpoint |
|---|---|
| inventory-a | `10.0.1.11:8081` |
| inventory-b | `10.0.1.12:8081` |

Consumer gọi URL logic:

~~~text
http://inventory-service/api/items
~~~

Trước khi gửi request, hệ thống phải biết những instance nào đang được công bố và chọn một instance. Sau khi chọn, HTTP client cần có kết nối đến host và port đó.

~~~mermaid
flowchart TD
    REG[("Service Registry")] --> DC["DiscoveryClient"]
    DC -->|"Registry snapshot / discovery cache"| SUP["ServiceInstanceListSupplier"]
    SUP -->|"LoadBalancer cache (nếu bật)"| LB["Spring Cloud LoadBalancer"]
    REQ["Request đến inventory-service"] --> LB
    LB -->|"Chọn host:port"| HTTP["HTTP client"]
    HTTP -->|"Acquire hoặc mở connection"| POOL[("HTTP connection pool")]
    POOL --> NET["TCP / TLS connection"]
    NET --> PROVIDER["inventory-service instance"]
~~~

| Lớp | Lưu gì? | Khóa hoặc phạm vi thường gặp | Mục đích |
|---|---|---|---|
| Discovery cache | Dữ liệu registry hoặc snapshot các service instance | Phụ thuộc implementation registry | Giảm truy vấn registry và cung cấp góc nhìn local |
| LoadBalancer cache | Danh sách `ServiceInstance` do supplier cung cấp | Service ID / client | Giảm việc lấy lại danh sách instance khi chọn đích |
| HTTP connection pool | Kết nối TCP/TLS đã mở và có thể tái sử dụng | Remote host, port hoặc HTTP route | Giảm chi phí tạo kết nối mới |

Một số hệ thống có cả ba lớp; một số chỉ có hai. `DiscoveryClient` là abstraction, không bắt buộc mọi implementation phải dùng cùng một kiểu cache. Tương tự, HTTP client có thể dùng pool hoặc tạo kết nối theo cách khác tùy thư viện và cấu hình.

## 2. Discovery cache: góc nhìn local về registry

Discovery cache giữ thông tin service và instance mà discovery client đã nhận từ registry. Nó trả lời câu hỏi: **Consumer hiện đang nhìn thấy những instance nào?**

Ví dụ với Eureka, Eureka Client tải registry từ Eureka Server rồi giữ dữ liệu local. Client cập nhật snapshot định kỳ bằng delta và có thể lấy lại toàn bộ registry khi cần đồng bộ. Property `eureka.client.registry-fetch-interval-seconds` điều khiển chu kỳ fetch; tài liệu Spring Cloud Netflix hiện hành công bố mặc định là 30 giây.

Cấu hình minh họa:

~~~yaml
eureka:
  client:
    fetch-registry: true
    registry-fetch-interval-seconds: 30
    filter-only-up-instances: true
~~~

Ý nghĩa:

- `fetch-registry`: client có lấy registry để khám phá service hay không.
- `registry-fetch-interval-seconds`: chu kỳ client làm mới dữ liệu registry.
- `filter-only-up-instances`: lọc kết quả chỉ còn instance có status UP khi lấy danh sách ứng dụng.

Đặt chu kỳ fetch nhỏ hơn có thể giúp client nhận thay đổi sớm hơn, nhưng tăng số lần trao đổi với Eureka Server. Đặt quá lớn làm tăng khoảng thời gian consumer có thể nhìn thấy dữ liệu cũ sau khi provider thay đổi trạng thái hoặc deregister.

### 2.1. Không phải DiscoveryClient nào cũng cache giống Eureka

Spring Cloud Commons định nghĩa `DiscoveryClient` để truy vấn service và instance. Abstraction này không áp đặt một cơ chế cache chung cho mọi registry.

Ví dụ:

- Eureka Client duy trì local registry và làm mới theo chu kỳ.
- Một implementation khác có thể truy vấn HTTP API khi supplier yêu cầu danh sách.
- Một integration có thể sử dụng cache riêng, watch hoặc snapshot tùy backend.

Vì vậy, trước khi điều chỉnh cache, cần biết implementation cụ thể. Không nên áp dụng property của Eureka cho Consul hoặc ZooKeeper chỉ vì cả ba đều triển khai `DiscoveryClient`.

### 2.2. Discovery cache không phải danh sách instance đã được LoadBalancer chọn

Discovery cache có thể chứa những instance mà registry công bố. LoadBalancer còn có thể lọc theo zone, health, metadata, hint hoặc chính sách khác trước khi chọn instance.

Ví dụ, registry có ba instance nhưng chính sách zone chỉ giữ hai instance cùng vùng. Discovery cache vẫn có thể chứa cả ba; danh sách đầu vào của LoadBalancer chỉ còn hai.

Do đó, kết quả `DiscoveryClient.getInstances()` và danh sách cuối cùng mà LoadBalancer sử dụng không nhất thiết giống hệt nhau.

## 3. LoadBalancer cache: danh sách instance dùng để chọn đích

Spring Cloud LoadBalancer sử dụng `ServiceInstanceListSupplier` để lấy danh sách instance. Supplier thường đọc dữ liệu qua `DiscoveryClient`; một lớp cache có thể giữ danh sách trả về để tránh truy vấn lại ở mỗi lần chọn.

Cache này trả lời câu hỏi: **LoadBalancer đang có danh sách ứng viên nào để chọn cho service ID này?**

Spring Cloud LoadBalancer cung cấp `CachingServiceInstanceListSupplier` và cấu hình cache mặc định. Theo tài liệu Spring Cloud Commons hiện hành:

| Property | Giá trị mặc định |
|---|---:|
| `spring.cloud.loadbalancer.cache.enabled` | `true` |
| `spring.cloud.loadbalancer.cache.ttl` | `35s` |
| `spring.cloud.loadbalancer.cache.capacity` | `256` |

Nếu Caffeine có trên classpath, LoadBalancer dùng cache dựa trên Caffeine. Nếu không, starter LoadBalancer cung cấp cache mặc định. Giá trị thực tế cần kiểm tra theo release train của dự án.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 15s
        capacity: 256
~~~

TTL ở đây là thời gian một entry danh sách instance được giữ sau khi ghi vào cache. Nó không phải thời gian sống của service instance và cũng không phải thời gian giữ kết nối HTTP.

### 3.1. Tránh cache hai lần với Eureka

Tài liệu Spring Cloud LoadBalancer lưu ý: nếu `DiscoveryClient` đã cache dữ liệu, ví dụ `EurekaDiscoveryClient`, cần cân nhắc tắt cache của LoadBalancer để tránh double caching.

Ví dụ:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

Đây không phải cấu hình bắt buộc cho mọi registry. Nếu discovery implementation không cache danh sách instance, LoadBalancer cache có thể giúp giảm số lần truy vấn và được khuyến nghị trong production theo tài liệu Spring Cloud.

Khi có hai cache nối tiếp, một thay đổi có thể phải chờ discovery client cập nhật snapshot rồi chờ LoadBalancer cache hết hạn hoặc được làm mới. Độ trễ thực tế phụ thuộc thời điểm thay đổi, chu kỳ fetch, cách cache được lấp đầy và cơ chế refresh; không nên cộng máy móc hai TTL để suy ra một con số chắc chắn.

### 3.2. Thứ tự supplier và filter

LoadBalancer có thể kết hợp nhiều supplier:

- Supplier lấy danh sách từ DiscoveryClient.
- Cache supplier lưu danh sách nhận được.
- Zone preference supplier lọc instance theo zone.
- Health check supplier hoặc filter khác loại instance không phù hợp.
- Request-based supplier áp dụng hint hoặc thuộc tính của request.

Khi tự xây dựng supplier chain, tài liệu Spring Cloud khuyến nghị đặt `CachingServiceInstanceListSupplier` ngay sau supplier lấy instance qua mạng, ví dụ `DiscoveryClientServiceInstanceListSupplier`, và trước các supplier lọc khác. Đặt cache sai vị trí có thể khiến dữ liệu đã lọc bị giữ lại và ảnh hưởng kết quả của request tiếp theo.

### 3.3. Cache không phải thuật toán cân bằng tải

Cache chỉ giữ danh sách ứng viên. Thuật toán như round-robin hoặc random mới quyết định chọn instance nào.

Một danh sách được cache không có nghĩa mọi request sẽ đi đến cùng một instance. Ngược lại, đổi thuật toán LoadBalancer không tự làm mới registry cache.

## 4. HTTP connection pool: tái sử dụng kết nối mạng

Sau khi LoadBalancer chọn `10.0.1.11:8081`, HTTP client cần kết nối đến endpoint đó. Tạo kết nối mới thường bao gồm DNS resolution (nếu dùng hostname), TCP handshake và TLS handshake nếu là HTTPS.

HTTP connection pool giữ các kết nối persistent đã mở để request sau có thể tái sử dụng. Nó trả lời câu hỏi: **Có kết nối phù hợp đến endpoint này để gửi request ngay không?**

Pool thường quản lý:

- Kết nối đang được sử dụng.
- Kết nối rảnh có thể tái sử dụng.
- Số kết nối tối đa trên một route hoặc host.
- Thời gian chờ lấy connection từ pool.
- Thời gian idle và tuổi thọ tối đa của connection.
- Kết nối stale do server hoặc intermediary đã đóng.

Pool không lưu danh sách service instance. Nó không biết `inventory-service` có bao nhiêu instance trong registry; nó chỉ quản lý kết nối đến các remote endpoint mà HTTP client đã sử dụng.

### 4.1. Connection pool có vòng đời riêng

Một kết nối có thể được tái sử dụng cho nhiều request đến cùng route khi giao thức và cấu hình cho phép. Sau khi request hoàn tất, connection có thể trở về trạng thái idle trong pool.

Kết nối sẽ bị loại bỏ khi:

- Vượt quá TTL hoặc max lifetime.
- Idle lâu hơn thời hạn cho phép.
- Server hoặc proxy đóng kết nối.
- Client phát hiện connection không còn hợp lệ.
- Ứng dụng đóng HTTP client hoặc connection manager.

Với HTTP/1.1, connection thường được tái sử dụng cho các request tuần tự; HTTP/2 có thể multiplex nhiều stream trên một connection. Chi tiết phụ thuộc giao thức, server và HTTP client.

### 4.2. Ví dụ pool với Reactor Netty

`WebClient` thường dùng Reactor Netty trong ứng dụng WebFlux. Có thể cấu hình `ConnectionProvider` riêng:

~~~java
import java.time.Duration;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

ConnectionProvider provider =
        ConnectionProvider.builder("inventory-pool")
                .maxConnections(100)
                .maxIdleTime(Duration.ofSeconds(20))
                .maxLifeTime(Duration.ofMinutes(5))
                .pendingAcquireTimeout(Duration.ofSeconds(2))
                .build();

HttpClient httpClient = HttpClient.create(provider)
        .responseTimeout(Duration.ofSeconds(3));

WebClient webClient = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
~~~

Các giới hạn trong ví dụ chỉ để minh họa; cần điều chỉnh theo concurrency, timeout phía server, tải và năng lực của provider.

- `maxConnections`: số connection tối đa mà pool quản lý theo phạm vi pool/remote host theo implementation.
- `maxIdleTime`: thời gian một connection có thể nằm idle.
- `maxLifeTime`: tuổi thọ tối đa của connection.
- `pendingAcquireTimeout`: thời gian chờ lấy connection khi pool chưa cấp được.
- `responseTimeout`: thời gian chờ response theo cấu hình Reactor Netty.

Đây là các thông số của connection pool và HTTP transport. Chúng không điều khiển discovery refresh hoặc LoadBalancer cache.

### 4.3. Ví dụ pool với Apache HttpClient 5

Với HTTP client blocking, Apache HttpClient 5 cung cấp `PoolingHttpClientConnectionManager`. Pool có thể giới hạn tổng số connection và số connection trên từng route:

~~~java
PoolingHttpClientConnectionManager connectionManager =
        PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(200)
                .setMaxConnPerRoute(50)
                .build();
~~~

Connection manager cũng hỗ trợ TTL, idle timeout, eviction và kiểm tra connection sau thời gian idle. Khi dùng `RestClient` hoặc `RestTemplate`, pool phụ thuộc request factory và HTTP client được cấu hình bên dưới; bản thân hai abstraction này không định nghĩa một pool chung cho mọi implementation.

## 5. TTL của ba lớp không có cùng ý nghĩa

Cả LoadBalancer cache và HTTP connection pool đều có thể có thuộc tính tên TTL hoặc lifetime, nhưng đối tượng được giữ hoàn toàn khác nhau.

| Thời hạn | Đối tượng | Khi hết hạn |
|---|---|---|
| Registry fetch interval | Snapshot registry phía discovery client | Discovery client thực hiện lần fetch/refresh tiếp theo |
| LoadBalancer cache TTL | Danh sách `ServiceInstance` | Cache entry hết hạn; supplier lấy danh sách mới khi cần |
| Connection max lifetime | TCP/TLS connection | Pool loại connection và tạo connection mới khi request cần |
| Connection max idle time | Connection rảnh | Pool đóng connection đã idle quá lâu |
| Pool acquire timeout | Thời gian chờ mượn connection | Request lỗi nếu không lấy được connection đúng hạn |

Không dùng `spring.cloud.loadbalancer.cache.ttl` để xử lý connection stale. Không giảm `maxIdleTime` để ép Eureka cập nhật danh sách instance. Không tăng `registry-fetch-interval-seconds` để giải quyết pool cạn connection.

## 6. Luồng của một request qua ba lớp

Khi `order-service` gọi `inventory-service`, trình tự tổng quát:

1. HTTP client nhận logical URL chứa service ID.
2. LoadBalancer yêu cầu danh sách instance từ `ServiceInstanceListSupplier`.
3. Supplier lấy dữ liệu từ DiscoveryClient; tùy cấu hình, danh sách có thể đến từ discovery cache hoặc LoadBalancer cache.
4. LoadBalancer chọn một `ServiceInstance`.
5. HTTP client tạo route đến host/port đã chọn.
6. HTTP client mượn connection phù hợp từ pool hoặc tạo connection mới.
7. Request được gửi đến provider và response được trả về.
8. Connection có thể được trả lại pool để tái sử dụng nếu vẫn hợp lệ.

~~~mermaid
sequenceDiagram
    participant O as order-service
    participant LB as LoadBalancer
    participant C as Discovery / LB cache
    participant D as DiscoveryClient
    participant P as HTTP connection pool
    participant I as inventory instance

    O->>LB: Call inventory-service
    LB->>C: Get ServiceInstance list
    alt Cache hit
        C-->>LB: Cached instances
    else Cache miss
        C->>D: Query service instances
        D-->>C: Registry view
        C-->>LB: Instance list
    end
    LB->>LB: Select instance A
    LB->>P: Acquire connection to A
    alt Reusable connection
        P-->>LB: Existing connection
    else No reusable connection
        P->>I: TCP/TLS connect
        I-->>P: Connection established
    end
    LB->>I: HTTP request
    I-->>O: HTTP response
    Note over P,I: Connection may return to pool
~~~

Một HTTP request có thể tạo connection mới hoặc tái sử dụng connection cũ. Một connection có thể phục vụ nhiều request đến cùng route. Hai việc này độc lập với việc danh sách instance có được fetch mới từ registry hay không.

## 7. Khi instance bị xóa, từng lớp phản ứng thế nào?

Giả sử `inventory-a` bị deregister khỏi registry.

| Lớp | Điều gì xảy ra? | Điều gì không tự xảy ra? |
|---|---|---|
| Registry / Discovery cache | Discovery client nhận thay đổi ở lần refresh hoặc theo cơ chế backend | Mọi consumer không nhất thiết cập nhật cùng thời điểm |
| LoadBalancer cache | Danh sách cũ có thể còn được dùng đến khi refresh hoặc hết TTL | Registry update không bảo đảm xóa ngay cache entry |
| HTTP connection pool | Connection đến `inventory-a` có thể còn idle cho đến khi hết hạn/được eviction | Pool không tự biết registration đã bị xóa |

Nếu discovery và LoadBalancer đã cập nhật danh sách, request mới sẽ không chọn `inventory-a` qua danh sách đó. Tuy vậy, connection cũ có thể còn nằm trong pool; nó chỉ là tài nguyên idle và không có nghĩa request mới chắc chắn tiếp tục dùng nó.

Nếu LoadBalancer cache còn chứa `inventory-a`, request mới vẫn có thể chọn endpoint cũ. Khi đó HTTP client có thể thử mượn connection còn sống hoặc gặp connection đã stale/đã bị server đóng.

### 7.1. Khi instance được thay thế tại cùng IP và port

Một trường hợp khó chẩn đoán là địa chỉ `10.0.1.11:8081` được dùng lại cho tiến trình mới.

Pool có thể còn connection TCP đã mở đến tiến trình cũ. Khi tiến trình cũ đóng, connection đó có thể bị đóng hoặc trở thành stale. Request đầu tiên sau một thời gian idle có thể gặp lỗi I/O dù discovery đã trả về endpoint có cùng host/port.

Cách xử lý nằm ở tầng connection: idle timeout, max lifetime, validation sau idle và retry có kiểm soát. Chỉ refresh discovery không đảm bảo connection cũ được đóng ngay.

## 8. Khi registry mất kết nối

Nếu consumer tạm thời không liên lạc được registry:

- Discovery cache có thể tiếp tục cung cấp snapshot cũ nếu implementation giữ dữ liệu local.
- LoadBalancer cache có thể còn danh sách instance đã lấy trước đó.
- HTTP pool vẫn có thể gửi request đến provider bằng connection đang có hoặc tạo connection mới nếu endpoint còn hợp lệ.

Điều này có thể giúp một số request tiếp tục hoạt động trong thời gian registry gián đoạn. Nhưng nó cũng tạo nguy cơ dùng instance đã chết hoặc bỏ lỡ instance mới.

Không nên giả định cache luôn được dùng khi refresh lỗi. Hành vi phụ thuộc discovery implementation, supplier, cache và lỗi phát sinh. Hãy kiểm tra log và metric của đúng client.

## 9. Khi HTTP connection pool cạn

Một pool có thể hết connection rảnh dù registry và LoadBalancer đều hoạt động bình thường.

Ví dụ:

- LoadBalancer chọn đúng `inventory-a`.
- Pool đã đạt `maxConnections`.
- Các connection hiện tại đều đang được request khác sử dụng.
- Request mới phải chờ trong pending acquire queue.
- Nếu chờ quá `pendingAcquireTimeout`, request lỗi trước khi kết nối tới provider.

Đây là lỗi tài nguyên transport, không phải lỗi discovery. Tăng TTL của LoadBalancer cache không làm pool có thêm connection. Cần xem concurrency, thời gian response, số connection đang leased, idle connection, pending acquire và giới hạn ở provider.

Không nên chỉ tăng `maxConnections` thật cao. Quá nhiều connection đồng thời có thể làm provider, load balancer mạng hoặc hệ điều hành quá tải.

## 10. Cấu hình tổng thể theo loại registry

### 10.1. Eureka

Eureka Client đã giữ local registry và refresh theo chu kỳ. Trong cấu hình ví dụ, có thể giữ cache discovery và tắt cache LoadBalancer để tránh double caching:

~~~yaml
eureka:
  client:
    fetch-registry: true
    registry-fetch-interval-seconds: 30

spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

Property `registry-fetch-interval-seconds` có mặc định 30 giây trong cấu hình Spring Cloud Netflix hiện hành. Hãy xác nhận phiên bản thực tế và chỉ thay đổi khi đã đo được trade-off giữa độ mới của registry và tải lên server.

### 10.2. Registry không cache danh sách instance ở DiscoveryClient

Nếu discovery implementation không cache kết quả truy vấn, LoadBalancer cache có thể giảm số lần gọi discovery:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 20s
        capacity: 256
~~~

TTL 20 giây chỉ là giá trị ví dụ. Cần chọn theo tốc độ thay đổi instance và mức độ chấp nhận dữ liệu cũ của ứng dụng.

### 10.3. HTTP pool

Cấu hình pool nằm ở HTTP client, không nằm trong `spring.cloud.loadbalancer.cache`. Với Reactor Netty, cấu hình `ConnectionProvider`; với Apache HttpClient 5, cấu hình connection manager và request factory tương ứng.

Không có một bộ property chung của Spring Cloud để điều khiển tất cả các HTTP client. Hãy xác định ứng dụng đang dùng `WebClient`, `RestClient`, `RestTemplate`, OpenFeign và transport implementation nào trước khi thay đổi pool.

## 11. Quy tắc chọn thời hạn và giới hạn

Không nên chọn TTL hoặc pool size chỉ dựa trên giá trị mặc định. Hãy dựa trên yêu cầu vận hành:

| Câu hỏi | Tham số cần xem |
|---|---|
| Instance mới cần xuất hiện trong consumer sau bao lâu? | Registry fetch/refresh interval và cơ chế event của backend |
| Instance bị xóa có thể còn trong danh sách bao lâu? | Discovery cache và LoadBalancer cache TTL |
| Request có thể chờ lấy connection bao lâu? | Pool acquire timeout |
| Connection mới được phép mất bao lâu để kết nối? | Connect timeout |
| Connection idle bao lâu thì đóng? | Max idle time |
| Connection được tái sử dụng tối đa bao lâu? | Max lifetime / TTL |
| Request chờ response tối đa bao lâu? | Response/read timeout |
| Có bao nhiêu request đồng thời đến một provider? | Pool max connections, per-route limit và concurrency |

Độ trễ cập nhật endpoint có thể đến từ nhiều tầng. Khi tính mục tiêu thời gian loại instance lỗi, hãy đo toàn bộ đường từ lúc provider đổi trạng thái đến khi consumer ngừng chọn endpoint cũ.

## 12. Quan sát từng lớp

### Discovery cache

Theo dõi:

- Lần registry fetch thành công gần nhất.
- Số service và instance trong local registry.
- Số lần fetch delta/full và lỗi đồng bộ.
- Thời gian từ lúc registry thay đổi đến khi DiscoveryClient nhìn thấy.

### LoadBalancer cache

Theo dõi:

- Cache hit/miss.
- TTL và số entry.
- Danh sách instance sau các bước filter.
- Instance thực tế được chọn cho từng request.
- Thời gian supplier lấy danh sách và lỗi discovery.

### HTTP connection pool

Theo dõi:

- Connection đang leased, idle và pending.
- Số lần tạo connection mới.
- Acquire timeout, connect timeout và response timeout.
- Connection bị đóng do idle/lifetime hoặc stale validation.
- Latency của TCP/TLS handshake và request.

Nên gắn service ID, instance ID, host/port và trace ID vào log hoặc metric ở mức phù hợp. Không ghi token hoặc dữ liệu nhạy cảm.

## 13. Quy trình chẩn đoán theo dấu hiệu

| Hiện tượng | Lớp nên kiểm tra trước | Cách kiểm tra |
|---|---|---|
| Registry đã xóa instance nhưng consumer vẫn chọn nó | Discovery cache và LoadBalancer cache | Xem local registry, fetch interval, cache TTL và supplier list |
| `DiscoveryClient` đã thấy instance mới nhưng LoadBalancer chưa chọn | LoadBalancer cache/filter | Kiểm tra cache entry, supplier chain, zone/health filter |
| LoadBalancer đã chọn đúng instance nhưng connect timeout | HTTP client / network | Kiểm tra route, DNS, TCP connect, firewall và connect timeout |
| Pool acquire timeout | HTTP connection pool | Xem max connections, pending queue, request duration và connection đang leased |
| Request đầu tiên sau thời gian idle bị reset | HTTP connection pool | Kiểm tra idle timeout server/proxy, maxIdleTime và stale validation |
| Đóng pool nhưng vẫn gọi endpoint cũ | Discovery / LoadBalancer cache | Pool chỉ tạo connection mới; danh sách instance vẫn có thể cũ |
| Tăng LoadBalancer TTL nhưng số TCP handshake không giảm | HTTP connection pool | Kiểm tra pool reuse và phạm vi HTTP client |
| Request vẫn đi tới instance sau khi deregister | Danh sách ứng viên hoặc request đang chạy | Kiểm tra cache, thời điểm chọn endpoint và in-flight request |

Quy trình kiểm tra một request lỗi:

1. Ghi nhận service ID và endpoint mà LoadBalancer chọn.
2. Kiểm tra `DiscoveryClient` hiện đang trả danh sách nào.
3. Kiểm tra supplier và LoadBalancer cache có đang giữ danh sách khác không.
4. Kiểm tra HTTP client đã chọn connection có sẵn hay đang mở connection mới.
5. Đọc lỗi cụ thể: acquire timeout, connect timeout, TLS error, response timeout hay HTTP status.
6. Đối chiếu timestamp để xác định dữ liệu cũ xuất hiện ở tầng nào.

## 14. Kiểm thử thay đổi instance và connection

Một bộ kiểm thử hữu ích cần bao phủ cả ba lớp:

| Kịch bản | Kết quả cần xác minh |
|---|---|
| Thêm instance mới | Discovery client nhận instance; supplier/LoadBalancer nhìn thấy sau refresh |
| Deregister instance | Instance biến mất khỏi danh sách ứng viên sau thời gian hội tụ |
| Instance unhealthy | Health filter hoặc status filter loại instance theo chính sách |
| Registry tạm thời mất kết nối | Consumer xử lý snapshot cũ và refresh failure theo thiết kế |
| Provider restart cùng IP/port | Connection cũ được phát hiện/loại bỏ và connection mới được tạo |
| Pool đạt giới hạn | Request chờ hoặc timeout theo acquire policy |
| Server đóng connection idle | Client loại connection stale và tạo kết nối mới |
| HTTP client shutdown | Pool giải phóng tài nguyên, không còn connection rò rỉ |

Không nên chỉ kiểm tra số lượng instance trong dashboard. Hãy kiểm tra endpoint mà LoadBalancer thực sự chọn và connection mà HTTP client thực sự sử dụng.

## 15. Ghi nhớ

- Discovery cache giữ góc nhìn registry ở phía client; cơ chế và chu kỳ refresh phụ thuộc DiscoveryClient implementation.
- Eureka Client giữ local registry và có `eureka.client.registry-fetch-interval-seconds` để điều khiển chu kỳ fetch.
- LoadBalancer cache giữ danh sách `ServiceInstance` do supplier cung cấp; TTL mặc định hiện hành là 35 giây và capacity mặc định là 256.
- Nếu DiscoveryClient đã cache, như Eureka, cần cân nhắc tắt LoadBalancer cache để tránh double caching.
- HTTP connection pool giữ kết nối TCP/TLS đến endpoint, không giữ danh sách instance.
- `maxIdleTime`, `maxLifeTime`, `maxConnections`, acquire timeout và response timeout điều khiển các khía cạnh khác nhau của transport.
- Registry update không tự xóa LoadBalancer cache hoặc connection pool; mỗi lớp có cơ chế refresh/eviction riêng.
- Khi debug, ghi lại cả service ID, instance được chọn và lỗi transport để xác định đúng tầng gây ra dữ liệu cũ hoặc request thất bại.

Ba lớp cùng tham gia vào một lần gọi service nhưng giải quyết ba bài toán riêng. Discovery tìm ra instance, LoadBalancer chọn đích, còn HTTP client quản lý kết nối đến đích đó. Khi cấu hình và quan sát riêng từng lớp, hệ thống có thể cân bằng giữa độ mới của discovery, chi phí tra cứu và hiệu quả tái sử dụng kết nối.

## Tài liệu tham khảo

- [Spring Cloud Commons — Service Discovery abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons — Spring Cloud LoadBalancer and caching](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud Netflix — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Reactor Netty — HTTP Client connection pool and timeouts](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [Apache HttpComponents — Connection management](https://hc.apache.org/httpcomponents-client-5.6.x/connection-management.html)
