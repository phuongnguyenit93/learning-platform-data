# DiscoveryClient trong mô hình Spring Cloud Commons

## 1. DiscoveryClient giải quyết bài toán gì?

Một ứng dụng Spring Cloud có thể cần tìm địa chỉ của dịch vụ khác mà không hard-code danh sách Pod. Spring Cloud Commons đưa ra abstraction DiscoveryClient để lớp gọi dịch vụ hỏi:

~~~text
“Service có tên inventory-service hiện có những instance nào?”
~~~

Lớp sử dụng không nhất thiết biết backend discovery là Kubernetes, Eureka, Consul hay một hệ thống khác. Backend cụ thể cung cấp implementation phù hợp, còn ứng dụng làm việc với khái niệm ServiceInstance.

Trong môi trường Kubernetes, implementation có thể lấy dữ liệu từ Service, EndpointSlice hoặc resource liên quan rồi chuyển thành danh sách instance. Tuy nhiên, DiscoveryClient không phải Kubernetes API server và cũng không thay thế Service. Nó là lớp abstraction ở phía ứng dụng:

~~~text
Ứng dụng Spring
    |
    v
Spring Cloud Commons DiscoveryClient
    |
    v
Kubernetes discovery integration
    |
    v
Kubernetes client -> Service/EndpointSlice/API server
~~~

Nếu ứng dụng chỉ gọi một Service cố định qua DNS, DiscoveryClient có thể không cần thiết. Nếu ứng dụng cần danh sách instance, metadata, lựa chọn động hoặc tích hợp Spring Cloud LoadBalancer, abstraction này có giá trị rõ hơn.

Bài học thuộc phần **Khám phá dịch vụ** của module **Spring Cloud Kubernetes**. Mục tiêu là hiểu vai trò của DiscoveryClient, cách implementation Kubernetes cung cấp ServiceInstance và các điều kiện cần kiểm tra trước khi dùng discovery trong ứng dụng Spring.

## 2. Spring Cloud Commons tạo ranh giới giữa caller và backend

Lớp gọi không nên phụ thuộc trực tiếp vào model của Kubernetes nếu nhu cầu chỉ là tìm instance. Nó có thể dùng abstraction chung:

~~~java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

import java.util.List;

class InventoryLocator {

    private final DiscoveryClient discoveryClient;

    InventoryLocator(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    List<ServiceInstance> instances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
~~~

Mã trên chỉ minh họa ý tưởng. Tên service ID, bean và cách inject phụ thuộc ứng dụng. Caller không tự biết EndpointSlice hay namespace nếu backend đã chuyển đổi dữ liệu thành ServiceInstance.

Thông tin thường có trong ServiceInstance:

- Service ID.
- Host hoặc địa chỉ instance.
- Port.
- Scheme hoặc cờ secure.
- Metadata tùy backend.
- URI được xây dựng từ các thành phần trên.

Backend có thể trả danh sách rỗng nếu service ID không tồn tại, namespace không đúng, endpoint chưa ready, filter loại bỏ instance, cache chưa đồng bộ hoặc client không có quyền đọc API. Danh sách rỗng không tự cho biết nguyên nhân.

Abstraction giúp thay backend dễ hơn, nhưng không làm mất các khác biệt vận hành. Kubernetes vẫn có readiness, namespace, RBAC, watch, cache và độ trễ hội tụ. Caller cần xử lý không có instance và lỗi gọi dịch vụ.

## 3. Blocking và reactive discovery

Spring Cloud Commons có đường tích hợp blocking và trong một số stack có reactive DiscoveryClient. Cần chọn path phù hợp với ứng dụng:

| Mô hình ứng dụng | Điều cần kiểm tra |
|---|---|
| Spring MVC/blocking | DiscoveryClient blocking và HTTP client blocking |
| Spring WebFlux/reactive | Reactive discovery path và HTTP client reactive |
| Ứng dụng có cả hai | Bean candidate, adapter và cách LoadBalancer chọn supplier |
| Chỉ gọi DNS | Có thể không cần discovery abstraction |

Không gọi blocking discovery trên event loop của ứng dụng reactive nếu implementation thực hiện I/O hoặc chờ API. Ngược lại, không thêm reactive abstraction chỉ vì một dependency khác có mặt.

Tên bean và property có thể thay đổi theo phiên bản. Kiểm tra type, auto-configuration và log startup thay vì đoán một tên bean cố định. Nếu có nhiều implementation, cần xác định implementation nào được chọn và vì sao.

Một discovery call có thể đọc cache thay vì gọi API ở mỗi lần:

~~~text
Caller -> DiscoveryClient -> cache
                         |
                         '-- watch/list Kubernetes khi cần refresh
~~~

Điều này tốt cho tải API nhưng khiến dữ liệu có độ trễ. Caller không nên coi danh sách instance là trạng thái nhất quán tức thời.

## 4. DiscoveryClient và Kubernetes Service

Kubernetes Service cung cấp tên và điểm truy cập ổn định. DiscoveryClient có thể cung cấp thông tin chi tiết hơn tùy integration:

~~~text
Service/DNS
  -> gọi một tên ổn định
  -> Kubernetes chọn backend

DiscoveryClient
  -> lấy danh sách ServiceInstance
  -> ứng dụng hoặc LoadBalancer chọn instance
~~~

So sánh:

| Nhu cầu | Service/DNS | DiscoveryClient |
|---|---|---|
| Gọi Service đã biết tên | Phù hợp, đơn giản | Có thể dư thừa |
| Không cần đọc API từ Pod | Thường đạt được | Thường cần integration API |
| Cần danh sách instance | Không trực tiếp cung cấp cho caller | Phù hợp hơn |
| Cần metadata instance | Hạn chế | Có thể hỗ trợ tùy backend |
| Client-side load balancing | Không phải vai trò chính | Cung cấp nguồn instance |
| Phạm vi namespace | DNS đầy đủ hoặc cấu hình | Discovery scope và RBAC |

Nếu Order chỉ gọi inventory-service trong namespace shop, URL DNS đầy đủ có thể đủ:

~~~text
http://inventory-service.shop.svc.cluster.local:8080
~~~

Nếu Order cần chọn instance theo metadata hoặc dùng Spring Cloud LoadBalancer, DiscoveryClient có thể hợp lý. Đừng bật discovery chỉ để lấy lại địa chỉ ClusterIP mà DNS đã cung cấp.

## 5. Kubernetes implementation biến resource thành ServiceInstance

Một integration Kubernetes có thể đi qua các bước:

1. Nhận service ID và namespace scope.
2. Đọc Service, EndpointSlice hoặc resource được cấu hình.
3. Lọc resource theo selector, label, readiness và port.
4. Chuyển backend thành ServiceInstance.
5. Lưu cache và theo dõi thay đổi.
6. Trả danh sách cho caller hoặc LoadBalancer.

Sơ đồ:

~~~text
Service ID
    |
    v
Kubernetes discovery integration
    |
    +-- namespace filter
    +-- Service/EndpointSlice query
    +-- ready/port/filter rules
    '-- cache/watch
    |
    v
List<ServiceInstance>
~~~

Các chi tiết resource và filter phụ thuộc release train, client implementation và property. Không giả định implementation luôn đọc Pod trực tiếp. Có dòng dựa vào Service/EndpointSlice, có mode hoặc tính năng cần metadata Pod.

Khi điều tra, xác định:

- Resource nào được đọc.
- API group nào được gọi.
- Namespace nào được quét.
- Verb nào cần: get, list, watch.
- Endpoint chưa ready có bị loại không.
- Port nào được chọn.
- Host trong ServiceInstance là ClusterIP, Pod IP hay hostname.
- Metadata nào được chuyển cho caller.

Nếu host là ClusterIP, LoadBalancer phía ứng dụng không nhất thiết đang chọn Pod. Nếu host là Pod IP, ứng dụng tham gia client-side load balancing và phải chịu cache, readiness, connection pool và retry.

## 6. Service ID và namespace

DiscoveryClient thường nhận service ID dạng chuỗi. Khi nhiều namespace có cùng Service name, chuỗi đơn giản có thể không đủ để phân biệt.

Ví dụ:

~~~text
shop/inventory-service
billing/inventory-service
~~~

Một integration có thể dùng namespace property riêng, metadata hoặc quy ước service ID; không có quy tắc chung rằng mọi implementation tự hiểu dấu gạch chéo. Hãy kiểm tra cách backend tạo và lọc ServiceInstance.

Các chiến lược:

1. Mỗi môi trường chỉ dùng một namespace scope.
2. Dùng tên Service khác nhau giữa namespace.
3. Đưa namespace vào cấu hình đích.
4. Dùng metadata hoặc service ID qualified nếu integration hỗ trợ.
5. Dùng DNS đầy đủ cho lời gọi namespace đã biết.

Không trộn nhiều instance cùng service ID nếu caller không có cách chọn đúng tenant. Một danh sách hợp lệ về mặt kỹ thuật vẫn có thể gây định tuyến sai về mặt nghiệp vụ.

Namespace hiện tại cũng không tự quyết định discovery scope. Client có thể chỉ đọc namespace hiện tại, đọc namespace cấu hình hoặc đọc nhiều namespace nếu RBAC cho phép.

## 7. DiscoveryClient và Spring Cloud LoadBalancer

Spring Cloud LoadBalancer thường dùng nguồn ServiceInstance để chọn một instance:

~~~text
Service ID
    -> DiscoveryClient/service instance supplier
    -> Spring Cloud LoadBalancer
    -> selected ServiceInstance
    -> HTTP client
~~~

LoadBalancer không tự tạo danh sách instance. Nếu không có discovery hoặc supplier phù hợp, nó không thể chọn đích.

Cần xác định lớp nào chịu trách nhiệm:

| Thành phần | Trách nhiệm |
|---|---|
| Kubernetes Service | Điểm truy cập, selector và routing nền tảng |
| DiscoveryClient | Lấy danh sách instance theo service ID |
| ServiceInstance supplier | Cung cấp danh sách cho LoadBalancer |
| LoadBalancer | Chọn một instance |
| HTTP client | Kết nối, timeout, retry và xử lý response |

Nếu DiscoveryClient trả host là ClusterIP, Kubernetes có thể tiếp tục cân bằng ở phía Service. Nếu trả Pod address, LoadBalancer chọn instance trực tiếp. Hai kiểu này có hành vi khác nhau khi Pod readiness đổi.

Những vấn đề cần kiểm tra:

- Service ID trong request có khớp service ID discovery không?
- Danh sách có rỗng hoặc stale không?
- Connection pool có giữ backend cũ không?
- Retry có lặp thao tác nghiệp vụ không?
- Port và scheme của ServiceInstance có đúng không?
- Metadata namespace có bị mất khi chuyển qua supplier không?

Không bật nhiều lớp load balancing mà không biết mỗi lớp chọn đích nào.

## 8. Cấu hình và bật discovery

Tên property phụ thuộc phiên bản Spring Cloud Kubernetes. Về mặt khái niệm, ứng dụng cần phân biệt:

~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        enabled: true
~~~

Đây là ví dụ minh họa, cần đối chiếu property metadata của release train. Một số ứng dụng còn cần cấu hình namespace, label selector, service filters hoặc cách đọc endpoint.

Khi bật discovery, kiểm tra:

- Starter discovery đã có đúng họ Kubernetes client chưa?
- Auto-configuration có match không?
- Bean DiscoveryClient đã được tạo chưa?
- Property discovery có bị profile hoặc environment override không?
- Client đang chạy trong cluster hay ngoài cluster?
- ServiceAccount có quyền đọc resource không?

Không dùng một starter tổng hợp nếu ứng dụng chỉ cần DNS. Mỗi capability bổ sung có thể kéo dependency, client connection, RBAC và log vận hành.

## 9. RBAC cho DiscoveryClient

Nếu integration đọc Service và EndpointSlice, Role cần đúng API group và verb:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: order-discovery-reader
  namespace: shop
rules:
  - apiGroups: [""]
    resources: ["services"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
~~~

Binding với ServiceAccount của Pod:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: order-discovery-reader
  namespace: shop
subjects:
  - kind: ServiceAccount
    name: order-runtime
    namespace: shop
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: order-discovery-reader
~~~

Đây là ví dụ phạm vi tối thiểu có thể cần, không phải danh sách đảm bảo cho mọi integration. Client cụ thể có thể đọc Endpoints thay vì EndpointSlice, hoặc cần resource khác cho metadata.

Nếu discovery nhiều namespace, lặp binding theo namespace hoặc dùng ClusterRole với RoleBinding namespaced. Tránh ClusterRoleBinding toàn cluster trừ khi yêu cầu thật sự là cluster-wide.

Lỗi thường gặp:

| Lỗi | Hậu quả |
|---|---|
| ServiceAccount không được gắn vào Pod | Pod dùng default hoặc danh tính khác |
| Binding ở sai namespace | Pod có token nhưng resource namespace không được cấp |
| Sai API group | EndpointSlice bị từ chối |
| Thiếu list/watch | Cache hoặc watch không khởi động |
| Đọc namespace khác Role scope | Discovery rỗng hoặc 403 |
| Cấp cluster-admin | Hoạt động nhưng vượt nhu cầu |

Một ServiceAccount token hợp lệ không chứng minh DiscoveryClient có quyền đọc.

## 10. Cache, watch và độ trễ

DiscoveryClient thường cần cache để tránh gọi API theo từng request nghiệp vụ. Cache được cập nhật bằng list/watch hoặc cơ chế refresh của integration.

Một chuỗi thay đổi có thể là:

~~~text
Pod readiness thay đổi
    -> EndpointSlice/controller cập nhật
    -> discovery watch nhận event
    -> cache cập nhật
    -> ServiceInstance list mới
    -> LoadBalancer dùng dữ liệu mới
~~~

Mỗi bước có độ trễ. Trong lúc hội tụ:

- Pod mới ready chưa xuất hiện ở mọi cache.
- Pod terminating có thể còn connection cũ.
- Watch có thể bị đóng và phải resync.
- API server trả resource version cũ.
- Nhiều replica có cache khác thời điểm.

Không dùng cache discovery làm nguồn sự thật cho giao dịch không thể sai. HTTP client vẫn cần timeout và xử lý lỗi. Retry phải cân nhắc idempotency.

Các tín hiệu nên quan sát:

- Thời điểm sync gần nhất.
- Số instance trong cache theo service ID.
- Số lỗi watch/reconnect.
- Độ tuổi cache.
- Namespace đang bị lỗi.
- Tỉ lệ request không có instance.

Không log token, Secret hoặc toàn bộ payload resource chỉ để debug cache.

## 11. Discovery không thay thế health probe

Kubernetes readiness và DiscoveryClient có liên quan nhưng không đồng nhất:

- Readiness ảnh hưởng việc endpoint được công bố là sẵn sàng.
- DiscoveryClient đọc dữ liệu đã công bố và có cache/filter riêng.
- LoadBalancer chọn từ danh sách mà nó nhận được.
- Connection pool có thể giữ connection qua thời điểm readiness đổi.

Nếu request tới Pod không sẵn sàng, kiểm tra cả:

1. Readiness probe có phản ánh đúng điều kiện phục vụ không?
2. EndpointSlice có ready false hoặc terminating không?
3. Discovery cache đã refresh chưa?
4. Connection pool có dùng connection cũ không?
5. ServiceInstance host là ClusterIP hay Pod address?

Không gắn lỗi API discovery vào liveness một cách máy móc. API server tạm thời không sẵn sàng không nhất thiết có nghĩa ứng dụng phải bị restart.

## 12. Xử lý không có instance

Caller phải có chính sách khi DiscoveryClient trả danh sách rỗng:

~~~java
List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");

if (instances.isEmpty()) {
    // timeout/fallback/error theo chính sách nghiệp vụ
}
~~~

Không spin loop vô hạn để chờ instance. Không retry nhanh khi API server đang lỗi. Cần tách:

- Service không tồn tại.
- Service tồn tại nhưng không có endpoint ready.
- Discovery filter loại hết endpoint.
- Client không có quyền.
- Cache chưa đồng bộ.
- API server hoặc mạng tạm thời lỗi.

Phản ứng có thể là trả lỗi rõ ràng, dùng fallback an toàn, chờ có giới hạn hoặc chuyển sang queue. Không dùng fallback DNS nếu hostname chưa được xác định đúng và thao tác không an toàn.

Với load balancing, empty supplier thường dẫn tới lỗi không tìm được instance. Health và metric nên phân biệt lỗi “no instance” với lỗi response từ một instance đã được chọn.

## 13. Các nhầm lẫn thường gặp

### “DiscoveryClient là Kubernetes Service”

Service là tài nguyên nền tảng; DiscoveryClient là abstraction phía Spring để lấy ServiceInstance.

### “Có DiscoveryClient thì không cần DNS”

DiscoveryClient có thể đọc Service/endpoint, nhưng Service vẫn là nguồn định danh Kubernetes trong nhiều thiết kế. Gọi DNS cố định có thể đơn giản hơn.

### “LoadBalancer tự khám phá Pod”

LoadBalancer cần ServiceInstance supplier. DiscoveryClient hoặc nguồn khác cung cấp danh sách.

### “Danh sách instance luôn mới nhất”

Cache, watch và network có độ trễ. Phải xử lý stale data và connection cũ.

### “Một service ID đủ cho mọi namespace”

Nếu nhiều namespace có cùng tên, cần scope hoặc quy ước định danh để tránh chọn nhầm.

### “403 chứng minh Service không tồn tại”

403 thường là lỗi authorization. Service có thể tồn tại nhưng ServiceAccount không được đọc.

### “Cấp quyền đọc toàn cluster là cách nhanh nhất”

Quyền rộng làm tăng dữ liệu lộ, tải API và blast radius. Hãy giới hạn namespace và resource.

## 14. Checklist triển khai DiscoveryClient

- Ứng dụng có cần danh sách instance hay DNS đã đủ?
- Starter discovery có đúng release train và họ client không?
- Auto-configuration và bean DiscoveryClient đã được xác nhận chưa?
- Service ID và namespace scope có rõ ràng không?
- Hai namespace có thể có cùng service name không?
- ServiceInstance host là ClusterIP, Pod IP hay hostname?
- Role có đúng Service/EndpointSlice hoặc resource integration thực sự đọc không?
- RoleBinding gắn đúng ServiceAccount của Pod chưa?
- Multi-namespace có binding riêng hoặc scope phù hợp chưa?
- Cache/watch/reconnect và độ trễ có được quan sát không?
- LoadBalancer đang chọn instance nào và retry ra sao?
- Empty instance list được xử lý với timeout/fallback nào?
- Readiness, endpoint terminating và connection pool có được tính đến không?
- Lỗi DNS, API, 401, 403, cache và backend có được phân loại riêng không?
- Có tránh log Secret, token và toàn bộ Kubernetes resource không?

DiscoveryClient trong Spring Cloud Commons giúp ứng dụng làm việc với abstraction ServiceInstance thay vì gắn chặt vào một backend discovery. Với Spring Cloud Kubernetes, abstraction này có thể nối tới Service và EndpointSlice, nhưng vẫn chịu các quy tắc namespace, RBAC, readiness, cache và network của Kubernetes. Chọn DiscoveryClient khi cần discovery động; dùng Service/DNS khi một điểm truy cập ổn định đã đáp ứng nhu cầu.
