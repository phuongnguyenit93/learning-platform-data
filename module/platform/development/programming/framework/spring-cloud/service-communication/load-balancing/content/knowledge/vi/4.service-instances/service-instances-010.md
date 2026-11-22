# Khi DNS hoặc hạ tầng đã cung cấp cân bằng tải

Một dịch vụ có thể được truy cập qua một địa chỉ ổn định do DNS, Kubernetes Service, reverse proxy hoặc load balancer của hạ tầng cung cấp. Trong trường hợp đó, caller gửi request đến endpoint chung; thành phần hạ tầng chọn một backend khỏe mạnh để xử lý. Ứng dụng không nhất thiết phải tự lấy danh sách từng replica và chọn instance bằng Spring Cloud LoadBalancer.

Spring Cloud LoadBalancer giải quyết một lớp vấn đề khác: lựa chọn một `ServiceInstance` từ danh sách instance mà Spring Cloud discovery cung cấp. Nếu danh sách đó đã được gom thành một địa chỉ ảo duy nhất, việc thêm một lớp chọn instance trong ứng dụng có thể không mang lại lợi ích. Cần xác định rõ ai chịu trách nhiệm chọn backend, health check, failover và quan sát request trước khi cấu hình client.

## 1. Phân biệt DNS, địa chỉ ảo và Spring Cloud LoadBalancer

Các cơ chế sau đều có thể giúp caller không phải biết địa chỉ của từng replica, nhưng chúng hoạt động ở những lớp khác nhau.

| Cơ chế | Caller nhìn thấy | Thành phần chọn backend | Phạm vi lựa chọn thường gặp |
|---|---|---|---|
| DNS trỏ đến một địa chỉ ảo (VIP) | Một hostname hoặc IP ổn định | Load balancer phía sau VIP | Các backend thuộc pool của VIP |
| DNS trả về nhiều địa chỉ | Một hostname có nhiều bản ghi A/AAAA | Resolver và HTTP client chọn địa chỉ khi phân giải/kết nối; hành vi tùy nền tảng | Các IP được DNS trả về |
| Kubernetes Service kiểu ClusterIP | Tên DNS của Service và một ClusterIP | Data plane của cluster chuyển kết nối đến endpoint | Các Pod endpoint của Service |
| Reverse proxy / gateway / cloud load balancer | Một hostname hoặc endpoint gateway | Proxy hoặc load balancer | Backend pool, route, zone hoặc region được cấu hình |
| Spring Cloud LoadBalancer | Service ID và danh sách `ServiceInstance` | Client trong ứng dụng | Các instance được `ServiceInstanceListSupplier` cung cấp |

DNS về bản chất phân giải tên thành địa chỉ. Một bản ghi DNS trỏ đến VIP không tự chọn Pod hay máy chủ phía sau VIP; việc đó do load balancer nhận traffic tại VIP đảm nhiệm.

DNS cũng có thể trả nhiều địa chỉ IP để phân phối lưu lượng. Tuy nhiên, DNS round robin không mặc nhiên là health-aware load balancing. Kết quả phân giải có thể được cache bởi JVM, hệ điều hành hoặc thư viện HTTP; connection pool và HTTP keep-alive còn có thể giữ kết nối đến một địa chỉ trong nhiều request. Vì vậy, không nên mặc định mỗi HTTP request sẽ được phân phối sang một IP khác.

Spring Cloud LoadBalancer hoạt động sau khi có danh sách ứng viên `ServiceInstance`. Nếu ứng dụng discovery trả về nhiều instance, nó có thể áp dụng chiến lược chọn như Round Robin. Nếu discovery chỉ trả về một instance đại diện cho VIP, LoadBalancer chỉ nhìn thấy một ứng viên; lựa chọn backend thật vẫn do hạ tầng thực hiện.

## 2. Luồng request khi hạ tầng đã cân bằng tải

Ví dụ, caller truy cập `https://inventory.internal`. DNS phân giải hostname này đến địa chỉ của load balancer. Load balancer kiểm tra trạng thái các backend và chuyển request đến một inventory replica.

~~~mermaid
flowchart LR
    A["Caller service"] -->|"https://inventory.internal"| B["DNS"]
    B -->|"VIP / endpoint ổn định"| C["Infrastructure Load Balancer"]
    C -->|"chọn backend khỏe mạnh"| D["inventory replica 1"]
    C -->|"hoặc"| E["inventory replica 2"]
    C -->|"hoặc"| F["inventory replica 3"]
~~~

Trong luồng này, caller chỉ cần biết hostname ổn định. Caller không cần truy vấn registry để lấy từng replica và không cần tự chọn một IP trong pool. Hạ tầng quản lý pool backend, health probe và chuyển hướng traffic theo chính sách đã cấu hình.

Một ví dụ khác là Kubernetes Service kiểu ClusterIP:

~~~mermaid
flowchart LR
    A["Caller Pod"] -->|"http://inventory-service"| B["Kubernetes DNS"]
    B -->|"ClusterIP của Service"| C["Service virtual IP / data plane"]
    C --> D["inventory Pod 1"]
    C --> E["inventory Pod 2"]
    C --> F["inventory Pod 3"]
~~~

Trong cluster, tên Service thường phân giải thành ClusterIP. Data plane của cluster chọn endpoint Pod cho kết nối. Tùy cách triển khai mạng và giao thức, việc chọn thường diễn ra ở cấp kết nối; nhiều request HTTP dùng chung một kết nối keep-alive có thể tiếp tục đến cùng một Pod. Điều đó không có nghĩa Service không cân bằng tải: nó có thể phân phối các kết nối mới đến nhiều endpoint.

Với Kubernetes headless Service, DNS có thể trả về địa chỉ Pod thay vì một ClusterIP. Đây là mô hình khác: caller hoặc thư viện resolver cần xử lý danh sách địa chỉ và cập nhật DNS theo TTL. Không nên coi headless Service tương đương một VIP có health-aware load balancing.

## 3. Khi nào không cần Spring Cloud LoadBalancer ở caller?

Không cần tích hợp client-side load balancing khi caller đã có một endpoint ổn định và hạ tầng chịu trách nhiệm phân phối đến replica. Các trường hợp thường gặp:

- Dịch vụ đích được công bố qua một VIP hoặc hostname của load balancer.
- Caller chạy trong Kubernetes và gọi một Service ClusterIP bằng DNS của Service.
- Caller gọi qua API gateway hoặc reverse proxy đã quản lý backend pool.
- Nền tảng cloud cung cấp endpoint ổn định và tự kiểm tra sức khỏe các target.

Khi đó, HTTP client có thể gọi URL thông thường. Ví dụ cấu hình caller:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service

clients:
  inventory:
    base-url: https://inventory.internal
~~~

Tạo `RestClient` thông thường:

~~~java
@Configuration
public class InventoryHttpConfiguration {

    @Bean
    RestClient inventoryRestClient(Environment environment) {
        String baseUrl = environment.getRequiredProperty(
                "clients.inventory.base-url"
        );

        return RestClient.builder()
                .baseUrl(baseUrl)
                .build();
    }
}
~~~

Sử dụng client trong service:

~~~java
@Service
public class InventoryClient {

    private final RestClient restClient;

    public InventoryClient(RestClient inventoryRestClient) {
        this.restClient = inventoryRestClient;
    }

    public InventoryResponse getInventory(String sku) {
        return restClient.get()
                .uri("/api/inventory/{sku}", sku)
                .retrieve()
                .body(InventoryResponse.class);
    }
}
~~~

Ở đây không đánh dấu builder bằng `@LoadBalanced`. `RestClient` gửi request đến hostname đã cấu hình; DNS và hạ tầng mạng chịu trách nhiệm phân giải và phân phối traffic. Không cần thêm danh sách IP replica vào code.

Với WebClient, cũng dùng builder thông thường:

~~~java
@Bean
WebClient inventoryWebClient(Environment environment) {
    String baseUrl = environment.getRequiredProperty(
            "clients.inventory.base-url"
    );

    return WebClient.builder()
            .baseUrl(baseUrl)
            .build();
}
~~~

WebClient vẫn có thể hoạt động reactive/non-blocking. Việc dùng hay không dùng Spring Cloud LoadBalancer là quyết định về cách chọn đích, độc lập với cách ứng dụng chờ I/O.

Với Spring Cloud OpenFeign, có thể khai báo URL cụ thể:

~~~java
@FeignClient(
        name = "inventory-service",
        url = "https://inventory.internal"
)
public interface InventoryFeignClient {

    @GetMapping("/api/inventory/{sku}")
    InventoryResponse getInventory(@PathVariable("sku") String sku);
}
~~~

Khi cung cấp `url`, Feign gọi endpoint đó trực tiếp thay vì nhờ Spring Cloud LoadBalancer chọn một `ServiceInstance` theo service ID. Nếu bỏ `url` và chỉ khai báo tên client, tích hợp load balancing/discovery có thể được dùng để tìm instance, tùy cấu hình và dependency của ứng dụng.

## 4. Tránh cấu hình hai lớp cùng chọn một pool replica

Giả sử DNS đã đưa `inventory.internal` đến một VIP, và VIP đó chọn một trong ba replica. Nếu caller lại khai báo `inventory.internal` như một service ID trong Spring Cloud LoadBalancer, cần hiểu chính xác danh sách `ServiceInstance` mà discovery cung cấp.

Nếu danh sách chỉ có một instance đại diện cho VIP:

~~~text
Spring Cloud LoadBalancer
        |
        | chỉ có 1 ServiceInstance
        v
https://inventory.internal
        |
        v
Infrastructure Load Balancer
        |
        +---- inventory-1
        +---- inventory-2
        +---- inventory-3
~~~

Spring Cloud LoadBalancer không phân phối giữa ba replica. Nó chỉ chọn VIP duy nhất; load balancer phía hạ tầng mới chọn backend. Trong trường hợp này, cấu hình client thông thường thường dễ hiểu và ít thành phần hơn.

Nếu cả Spring Cloud LoadBalancer và hạ tầng cùng chọn trực tiếp từ một nhóm replica, kiến trúc có thể có hai tầng quyết định:

~~~mermaid
flowchart LR
    A["Caller"] --> B["Spring Cloud LoadBalancer"]
    B -->|"chọn instance / zone"| C["Gateway hoặc VIP"]
    C --> D["Infrastructure Load Balancer"]
    D --> E["Backend replicas"]
~~~

Hai tầng không nhất thiết sai. Ví dụ, tầng ứng dụng chọn một region hoặc gateway phù hợp, còn load balancer trong region phân phối đến các replica cục bộ. Nhưng mỗi tầng cần một mục đích riêng và một tập ứng viên rõ ràng.

Tránh cấu hình trùng lặp khiến cả hai tầng cùng quản lý một backend pool mà không có lý do. Khi đó có thể khó xác định tầng nào đang loại instance lỗi, retry đang diễn ra ở đâu, request đã được gửi đến backend nào và vì sao tải bị lệch.

## 5. Phân biệt service ID với hostname do DNS quản lý

Tên `inventory-service` có thể xuất hiện ở nhiều nơi nhưng không tự động có cùng ý nghĩa:

- Trong Spring Cloud LoadBalancer, đó có thể là service ID dùng để tra cứu danh sách `ServiceInstance`.
- Trong Kubernetes, đó có thể là DNS name của Service, ví dụ `inventory-service.default.svc.cluster.local`.
- Trong DNS doanh nghiệp, đó có thể là hostname trỏ đến VIP hoặc reverse proxy.

Nếu dùng Spring Cloud LoadBalancer, URI dạng `http://inventory-service` được client load-balanced xử lý như tên logic cần phân giải qua Spring Cloud. Cơ chế này cần một nguồn cung cấp instance cho service ID đó.

Nếu muốn gọi DNS hoặc VIP trực tiếp, hãy cấu hình hostname thật và dùng HTTP client thông thường, ví dụ `https://inventory.internal`. Đừng gắn `@LoadBalanced` vào builder chỉ vì hostname có tên giống service ID. Annotation đó thay đổi cách URI được phân giải và yêu cầu cấu hình discovery/load-balancer tương ứng.

Một cách đặt tên rõ ràng giúp giảm nhầm lẫn:

| Ý nghĩa | Ví dụ |
|---|---|
| Service ID trong Spring Cloud | `inventory-service` |
| DNS name của Kubernetes Service | `inventory-service.default.svc.cluster.local` |
| Hostname của load balancer nội bộ | `inventory.internal` |
| Địa chỉ vật lý của replica | `10.20.1.14:8080` |

Một DNS name có thể chính là tên Service trong Kubernetes, nhưng đó vẫn là DNS/network endpoint. Nó không đồng nghĩa với việc Spring Cloud discovery đã trả về một danh sách `ServiceInstance` cho ứng dụng.

## 6. DNS round robin không giống health-aware load balancing

Một DNS zone có thể chứa nhiều bản ghi cho cùng hostname:

~~~dns
inventory.internal.  30  IN  A  10.20.1.14
inventory.internal.  30  IN  A  10.20.1.15
inventory.internal.  30  IN  A  10.20.1.16
~~~

Resolver có thể nhận nhiều địa chỉ cho một truy vấn. Thứ tự trả về hoặc cách client chọn địa chỉ phụ thuộc DNS server, resolver, cache và HTTP client. TTL 30 giây trong ví dụ là thời gian cache được khai báo, không bảo đảm mọi client sẽ hỏi DNS lại chính xác sau 30 giây.

DNS round robin đơn giản không nhất thiết biết backend nào đang lỗi. Nếu một địa chỉ vẫn được trả về sau khi server dừng, caller có thể tiếp tục kết nối thất bại cho đến khi bản ghi được cập nhật và cache hết hiệu lực. Một dịch vụ DNS có health check hoặc cơ chế routing nâng cao có thể làm tốt hơn, nhưng cần xác nhận chính sách thực tế của nhà cung cấp.

Load balancer chuyên dụng thường có thể kiểm tra sức khỏe backend, loại target lỗi khỏi pool, phục hồi target khi khỏe lại và áp dụng chính sách phân phối như least connections, weighted routing hoặc locality. Tuy vậy, khả năng cụ thể phụ thuộc loại load balancer và cấu hình.

Khi dùng DNS nhiều địa chỉ, cần quan sát:

- DNS trả về một hay nhiều địa chỉ và thứ tự thay đổi thế nào.
- JVM hoặc resolver có cache kết quả bao lâu.
- HTTP client mở kết nối mới thường xuyên hay tái sử dụng connection pool.
- Cơ chế health check có loại địa chỉ lỗi khỏi câu trả lời không.
- Ứng dụng phản ứng thế nào khi DNS thay đổi nhưng connection cũ vẫn còn.

Đừng kết luận DNS round robin đang phân phối request chỉ từ việc nhìn thấy nhiều bản ghi DNS. Hãy quan sát backend thực tế đã nhận request.

## 7. Health check và failover thuộc tầng nào?

Khi hạ tầng chịu trách nhiệm load balancing, cần biết health check được thực hiện ở đâu. Một load balancer có thể dùng TCP probe, HTTP health endpoint hoặc kiểm tra theo giao thức riêng. Nó có thể ngừng gửi kết nối mới đến backend không khỏe, nhưng request đang chạy có thể vẫn thất bại nếu backend dừng giữa chừng.

Trong Spring Cloud LoadBalancer, danh sách ứng viên thường đến từ `ServiceInstanceListSupplier`. Có thể kết hợp supplier để lọc instance theo health check hoặc metadata. Cơ chế này hữu ích khi ứng dụng trực tiếp chọn từ nhiều instance. Nếu discovery chỉ trả về một VIP và hạ tầng đã kiểm tra backend, health check ở tầng Spring không nhìn thấy trạng thái từng replica phía sau VIP.

Cần phân biệt:

| Tình huống | Health check cần quan sát |
|---|---|
| Spring Cloud LoadBalancer chọn trực tiếp nhiều replica | Từng `ServiceInstance` mà caller có thể chọn |
| Caller gọi một VIP | VIP/load balancer và trạng thái target phía sau nó |
| Caller gọi Kubernetes ClusterIP | Kubernetes Service endpoints và cơ chế readiness của Pod |
| Caller dùng DNS nhiều IP | DNS health policy, TTL/cache và khả năng kết nối đến từng IP |

Readiness của ứng dụng nên phản ánh khả năng nhận traffic nghiệp vụ. Liveness thường phục vụ quyết định khởi động lại tiến trình. Không nên dùng một health endpoint kiểm tra quá nhiều phụ thuộc bên ngoài đến mức backend khỏe bị đánh dấu lỗi dây chuyền khi một dependency tạm thời gián đoạn.

Failover cũng có độ trễ. Load balancer cần phát hiện lỗi theo chu kỳ probe; DNS cần cập nhật bản ghi và chờ cache; client cần mở kết nối mới để sử dụng địa chỉ mới. Vì vậy, một backend vừa dừng có thể vẫn nhận request hoặc gây lỗi trong một khoảng thời gian.

## 8. Timeout, retry và connection pool khi có nhiều tầng

Khi request đi qua caller, gateway và load balancer, tổng thời gian xử lý gồm thời gian ở tất cả các tầng. Hãy đặt deadline cho toàn request và phân bổ ngân sách timeout hợp lý cho từng hop.

Ví dụ:

~~~text
Caller deadline: 2.5 giây
    |
    +-- Kết nối / chờ gateway: tối đa 2.0 giây
            |
            +-- Load balancer chọn backend
            +-- Backend xử lý: phần thời gian còn lại
~~~

Các giá trị trên chỉ minh họa cách chia ngân sách; hãy đo độ trễ thực tế và chọn timeout theo SLA của dịch vụ. Timeout kết nối và timeout đọc response có thể là hai cấu hình khác nhau của HTTP client.

Retry có thể xuất hiện ở nhiều tầng: HTTP client, Spring Cloud LoadBalancer, gateway hoặc load balancer hạ tầng. Nếu mỗi tầng đều retry nhiều lần, một request ban đầu có thể tạo ra nhiều lần gọi backend. Khi dịch vụ quá tải, retry đồng loạt còn làm tình trạng nặng hơn.

Một số nguyên tắc:

1. Chọn một tầng chính chịu trách nhiệm retry cho từng loại lỗi, hoặc ghi rõ cách phối hợp nếu cần nhiều tầng.
2. Giới hạn tổng số lần thử và tổng thời gian theo deadline của caller.
3. Dùng backoff và jitter để giảm việc nhiều client retry cùng lúc.
4. Chỉ retry thao tác an toàn khi lặp; thao tác ghi cần idempotency key hoặc cơ chế chống thực hiện trùng.
5. Phân biệt lỗi kết nối, timeout, HTTP status và lỗi nghiệp vụ trước khi quyết định retry.

Connection pool và keep-alive ảnh hưởng đến cách quan sát load balancing. Với load balancing ở tầng L4 hoặc Kubernetes Service, nhiều request trên một TCP connection có thể đi cùng một backend. Muốn kiểm tra phân phối ở cấp kết nối, hãy tạo đủ kết nối mới và quan sát log/metric backend. Với HTTP/2, một connection còn có thể multiplex nhiều stream, nên không nên kỳ vọng mỗi request stream được hạ tầng phân phối lại độc lập.

## 9. Tình huống nên phối hợp Spring Cloud và hạ tầng

Có những hệ thống cần nhiều tầng phân phối vì chúng giải quyết các phạm vi khác nhau. Ví dụ ứng dụng có thể chọn một region hoặc gateway theo tenant, sau đó load balancer trong region chọn replica.

~~~text
Order service
    |
    | Spring Cloud LoadBalancer chọn region
    v
Region gateway (region-a hoặc region-b)
    |
    | Infrastructure LB chọn backend khỏe mạnh
    v
Inventory replica trong region
~~~

Để thiết kế phối hợp rõ ràng:

- Mỗi tầng chỉ chọn trong tập ứng viên thuộc trách nhiệm của tầng đó.
- Tầng Spring có thể chọn gateway/region, còn tầng hạ tầng chọn replica trong region.
- Health check ở mỗi tầng phải kiểm tra đúng đối tượng mà tầng đó quản lý.
- Không để một tầng đánh dấu gateway khỏe chỉ vì VIP trả TCP accept nếu nghiệp vụ cần kiểm tra sâu hơn.
- Xác định retry và timeout theo toàn bộ đường đi.
- Gắn trace ID để nối log từ caller qua gateway đến backend.

Một trường hợp khác là caller muốn dùng service discovery để chọn một trong nhiều gateway nội bộ, còn gateway tự quản lý replicas. Khi đó danh sách `ServiceInstance` trong Spring Cloud nên chứa các gateway endpoint. Không nên đưa đồng thời từng Pod và gateway vào cùng một service ID nếu hai loại endpoint có semantics và chính sách routing khác nhau.

## 10. Cách kiểm chứng hạ tầng đang thực sự cân bằng tải

Đừng chỉ dựa vào cấu hình hoặc DNS record. Hãy kiểm chứng từ đầu đến cuối.

**Bước 1: kiểm tra DNS và endpoint.**

Trên PowerShell:

~~~powershell
Resolve-DnsName inventory.internal
~~~

Ghi lại bản ghi, địa chỉ trả về và TTL. Nếu hostname trỏ tới VIP, cần xác định load balancer nào đang nhận traffic tại địa chỉ đó.

**Bước 2: gửi nhiều request qua endpoint chung.**

~~~powershell
1..20 | ForEach-Object {
    Invoke-RestMethod https://inventory.internal/api/instance
}
~~~

Endpoint `/api/instance` trong ví dụ cần được dịch vụ cung cấp để trả về mã nhận diện replica. Nếu không muốn thêm thông tin replica vào response production, hãy dùng log hoặc trace ở backend để quan sát.

**Bước 3: kiểm tra phân phối tại backend.**

Đối chiếu số request từng replica nhận được, trạng thái target trong dashboard của load balancer và access log của gateway. Nếu tất cả request đi vào một replica, kiểm tra connection reuse, sticky session, chính sách phân phối và số kết nối thực tế trước khi kết luận cấu hình lỗi.

**Bước 4: thử một backend không khỏe.**

Dừng một replica hoặc làm cho readiness/health probe của nó thất bại trong môi trường kiểm thử. Quan sát thời gian load balancer loại replica khỏi pool, lỗi caller nhìn thấy và thời gian phục hồi khi replica khỏe lại.

**Bước 5: kiểm tra hành vi khi DNS thay đổi.**

Nếu đang dùng DNS nhiều địa chỉ, thay đổi một bản ghi trong môi trường thử nghiệm và quan sát thời gian client bắt đầu dùng địa chỉ mới. So sánh TTL DNS với cache JVM, connection pool và thời gian sống của kết nối.

Kết quả cần ghi nhận gồm hostname caller sử dụng, địa chỉ VIP hoặc gateway, backend thực tế, thời gian phản hồi, trạng thái HTTP và lỗi khi failover. Những dữ liệu này giúp phân biệt lỗi ở DNS, mạng, load balancer, HTTP client hay ứng dụng đích.

## 11. Checklist chọn đúng cơ chế

- [ ] Xác định caller đang gọi service ID Spring Cloud, DNS name, ClusterIP, VIP hay gateway URL.
- [ ] Xác định thành phần nào đang chọn backend replica.
- [ ] Nếu hạ tầng đã quản lý backend pool, dùng HTTP client thông thường với endpoint ổn định khi không cần Spring chọn gateway.
- [ ] Nếu Spring Cloud LoadBalancer chọn trực tiếp nhiều `ServiceInstance`, khai báo nguồn discovery và chính sách chọn rõ ràng.
- [ ] Không nhầm DNS round robin với health-aware load balancing.
- [ ] Kiểm tra TTL, cache DNS, connection pooling và keep-alive.
- [ ] Xác định health check ở đúng tầng và biết độ trễ failover.
- [ ] Đặt timeout theo deadline end-to-end và tránh retry trùng ở nhiều tầng.
- [ ] Nếu phối hợp nhiều tầng, phân chia rõ phạm vi lựa chọn: region/gateway ở một tầng, replica ở tầng khác.
- [ ] Dùng log, metric và trace để xác nhận backend thực sự nhận request.

Khi DNS hoặc hạ tầng đã cung cấp một endpoint ổn định và chịu trách nhiệm chọn replica, caller thường chỉ cần gọi endpoint đó bằng HTTP client thông thường. Spring Cloud LoadBalancer phát huy tác dụng khi ứng dụng cần chọn giữa nhiều `ServiceInstance` mà discovery cung cấp. Có thể kết hợp hai tầng nếu mỗi tầng có phạm vi lựa chọn rõ ràng, health check phù hợp và chính sách timeout/retry được phối hợp xuyên suốt request.
