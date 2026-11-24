# Chi phí truy vấn toàn bộ danh mục và giới hạn phạm vi khám phá

Service registry lưu thông tin về nhiều service và instance để consumer có thể tìm đích gọi theo tên logic. Khi hệ thống phát triển, số service, replica, namespace và vùng triển khai tăng lên. Việc đọc toàn bộ catalog có thể tạo chi phí đáng kể về network, CPU, memory, thời gian đồng bộ và quyền truy cập. Một ứng dụng chỉ cần gọi `inventory-service` nhưng lại duyệt mọi service để tìm tên cần dùng là một dấu hiệu thiết kế chưa tốt.

Trong Spring Cloud, cần phân biệt truy vấn danh sách service bằng `DiscoveryClient.getServices()` với truy vấn instance của một service bằng `DiscoveryClient.getInstances(serviceId)`. Giới hạn phạm vi lookup giúp ứng dụng chỉ xử lý dữ liệu cần thiết. Tuy nhiên, chi phí nền của từng registry khác nhau: Eureka client thường đồng bộ một registry snapshot về cache cục bộ, trong khi Consul, ZooKeeper và Kubernetes có thể hỗ trợ truy vấn theo service hoặc phạm vi namespace tùy cách tích hợp.

## 1. Catalog, service và instance

Một catalog có thể chứa nhiều service ID. Mỗi service ID lại có thể có một hoặc nhiều instance:

```text
Catalog
  inventory-service
    inventory-1
    inventory-2
    inventory-3
  order-service
    order-1
    order-2
  payment-service
    payment-1
  notification-service
    notification-1
    notification-2
```

Các khái niệm:

- **Catalog:** tập hợp service mà registry biết trong phạm vi cluster, partition, namespace hoặc root path.
- **Service ID:** tên logic consumer dùng để tra cứu, ví dụ `inventory-service`.
- **Instance:** một bản chạy cụ thể của service, có host, port, URI và metadata.
- **Discovery scope:** phạm vi dữ liệu mà client được phép hoặc được cấu hình để khám phá, ví dụ một service ID, một namespace hoặc toàn bộ catalog.

Nếu một catalog có `S` service và tổng cộng `I` instance, thao tác enumerate toàn bộ catalog có thể phải xử lý dữ liệu tỷ lệ với `S + I`. Nếu consumer chỉ cần service `x` có `I_x` instance, truy vấn theo service có thể giới hạn phần dữ liệu ứng dụng phải xử lý xuống gần `I_x`. Đây là mô hình chi phí khái quát; chi phí thực tế còn phụ thuộc registry, cache, transport, filter và cách provider lưu dữ liệu.

## 2. Hai API DiscoveryClient có phạm vi khác nhau

Spring Cloud Commons cung cấp abstraction `DiscoveryClient`:

```java
public interface DiscoveryClient {
    String description();

    List<ServiceInstance> getInstances(String serviceId);

    List<String> getServices();

    default int getOrder() {
        return 0;
    }
}
```

Hai phương thức quan trọng:

| Phương thức | Kết quả | Khi nên dùng |
|---|---|---|
| `getInstances("inventory-service")` | Các instance của một service ID | Consumer cần gọi một service cụ thể |
| `getServices()` | Danh sách service ID mà client khám phá được | Công cụ quản trị, dashboard hoặc chức năng thật sự cần liệt kê |

Ví dụ consumer cần gọi tồn kho:

```java
List<ServiceInstance> instances =
    discoveryClient.getInstances("inventory-service");
```

Đây là truy vấn đúng phạm vi. Không cần gọi `getServices()` rồi lặp qua tất cả service để tìm `inventory-service`.

Anti-pattern:

```java
for (String serviceId : discoveryClient.getServices()) {
    if ("inventory-service".equals(serviceId)) {
        return discoveryClient.getInstances(serviceId);
    }
}
```

Đoạn code trên thực hiện một bước enumerate không cần thiết. Khi catalog lớn, việc gọi `getServices()` có thể buộc client duyệt hoặc materialize danh sách service trước khi lấy đúng instance.

Lưu ý: abstraction chỉ mô tả API. Nó không bảo đảm mọi implementation có cùng chi phí. Một provider có thể trả danh sách từ cache local; provider khác có thể truy vấn API hoặc đọc cây znode. Cần xem xét cơ chế của registry đang sử dụng.

## 3. Các nguồn chi phí khi đọc toàn bộ catalog

Việc enumerate catalog có thể tạo chi phí ở nhiều tầng:

| Tầng | Chi phí có thể phát sinh |
|---|---|
| Registry server | Xử lý request rộng, đọc nhiều record, lọc và serialize dữ liệu |
| Network | Truyền payload lớn giữa registry và client |
| Client parser | Deserialize JSON, protobuf hoặc dữ liệu znode |
| Heap/memory | Giữ danh sách service và instance trong cache hoặc object graph |
| CPU | Lặp, sort, filter, tạo object và tính toán metadata |
| Refresh/watch | Đồng bộ snapshot hoặc xử lý nhiều event khi catalog thay đổi |
| Observability | Log/metric cardinality tăng nếu gắn nhãn theo mọi service hoặc instance |
| Security | Client có thể đọc nhiều thông tin hơn phạm vi nghiệp vụ cần thiết |

Một request liệt kê catalog có vẻ nhẹ khi hệ thống chỉ có vài service. Nhưng nếu có hàng nghìn service, nhiều replica, nhiều consumer và dashboard polling liên tục, tải tổng cộng có thể tăng đáng kể.

Cần phân biệt chi phí của một lần gọi API với chi phí nền của registry client. Ví dụ Eureka client có thể tải toàn bộ registry về cache theo chu kỳ; gọi `getInstances(serviceId)` giúp consumer chỉ xử lý instance cần dùng, nhưng không nhất thiết loại bỏ chi phí fetch toàn registry ở tầng Eureka client.

## 4. Vì sao không nên enumerate trong mỗi request?

Không nên truy vấn toàn bộ catalog trong đường xử lý HTTP nghiệp vụ:

```java
@GetMapping("/items/{id}")
public ItemResponse getItem(@PathVariable String id) {
    List<String> services = discoveryClient.getServices();

    // Tìm inventory-service trong toàn bộ danh sách
    // rồi mới gọi service đích.
    return inventoryClient.getItem(id);
}
```

Danh sách service không cần được tải lại cho từng request. Service ID là dependency đã biết của ứng dụng, nên có thể khai báo tĩnh trong Feign client hoặc cấu hình. Việc enumerate mỗi lần request sẽ làm tăng CPU, allocation và latency mà không tăng giá trị cho nghiệp vụ.

Nên dùng client theo service ID:

```java
@FeignClient(name = "inventory-service")
public interface InventoryClient {

    @GetMapping("/api/items/{id}")
    ItemResponse getItem(@PathVariable("id") String id);
}
```

Khi dùng OpenFeign cùng Spring Cloud LoadBalancer và discovery integration, LoadBalancer yêu cầu danh sách instance của đúng service ID. Consumer không cần tự duyệt catalog để tìm đích.

## 5. Eureka: fetch registry rộng và cache phía client

Eureka client thường tải registry snapshot từ Eureka Server về cache cục bộ. Các lần tra cứu instance sau đó có thể đọc từ cache thay vì gửi một request catalog mới cho mỗi lần gọi.

Cấu hình consumer phổ biến:

```yaml
eureka:
  client:
    fetch-registry: true
    registry-fetch-interval-seconds: 30
```

`fetch-registry` cho biết Eureka client có tải registry để phục vụ discovery hay không. `registry-fetch-interval-seconds` điều chỉnh chu kỳ fetch theo phiên bản và cấu hình client.

Điểm cần hiểu:

- Eureka client thường nhận registry snapshot rộng thay vì chỉ tải một service ID theo từng lời gọi `getInstances`.
- `DiscoveryClient.getInstances(serviceId)` thường lọc từ registry cache cục bộ.
- Giảm tần suất fetch có thể giảm tải network/CPU nhưng làm dữ liệu phía client cũ lâu hơn.
- Tắt `fetch-registry` sẽ làm client không tải registry để lookup; đây không phải cách giới hạn catalog còn một service.
- Không nên giả định Eureka có một property chung để chỉ fetch đúng một service ID nếu integration/version không hỗ trợ cơ chế đó.

Ví dụ, nếu consumer chỉ cần `inventory-service`, code vẫn nên gọi `getInstances("inventory-service")` hoặc dùng Feign service name. Điều đó giảm công việc enumerate ở tầng ứng dụng dù Eureka client vẫn có thể duy trì cache registry rộng.

### Khi nào cần cân nhắc Eureka fetch?

- Registry có số lượng instance rất lớn.
- Nhiều consumer cùng tải snapshot đầy đủ.
- Payload fetch lớn hoặc thời gian deserialize tăng.
- Heap sử dụng cho registry cache chiếm tỷ lệ đáng kể.
- Refresh tạo network burst hoặc CPU spike.

Có thể điều chỉnh chu kỳ fetch sau khi đo đạc. Không tăng interval chỉ để giảm tải nếu ứng dụng cần nhận biết instance mới hoặc instance bị loại nhanh. Phải đánh giá đồng thời tải và độ trễ cập nhật.

## 6. Consul: truy vấn theo service và filter

Consul cung cấp API có thể truy vấn health của một service cụ thể, ví dụ:

```http
GET /v1/health/service/inventory-service
```

Nếu chỉ cần các instance passing, có thể dùng query parameter `passing=true`:

```bash
curl "http://consul.internal:8500/v1/health/service/inventory-service?passing=true"
```

Truy vấn service cụ thể thường phù hợp hơn API catalog-wide:

```http
GET /v1/catalog/services
```

API catalog services liệt kê nhiều service trong catalog. Chỉ dùng khi thực sự cần khám phá danh sách service, ví dụ trang quản trị hoặc công cụ inventory.

Consul còn có filter theo tag, namespace, partition hoặc các điều kiện query tùy phiên bản và cấu hình. Các filter giúp giảm kết quả trả về, nhưng không thay thế authorization. ACL token vẫn cần giới hạn service/namespace mà client được đọc.

Trong Spring Cloud Consul, hãy dùng `DiscoveryClient.getInstances(serviceId)` cho lookup theo service. Các tùy chọn như chỉ lấy instance passing, watch hay cache phụ thuộc phiên bản Spring Cloud Consul; kiểm tra property và hành vi thực tế trước khi dựa vào chúng trong production.

## 7. ZooKeeper: đọc nhánh service cần thiết

Spring Cloud Zookeeper Discovery thường tổ chức registration dưới một root path. Có thể hình dung:

```text
/services
  /inventory-service
    /inventory-1
    /inventory-2
  /order-service
    /order-1
  /payment-service
    /payment-1
```

Nếu consumer cần `inventory-service`, discovery integration có thể đọc các child node của nhánh:

```text
/services/inventory-service
```

Thao tác đọc nhánh service cụ thể có phạm vi hẹp hơn việc liệt kê toàn bộ children dưới `/services` rồi đọc tiếp mọi instance.

Tuy nhiên, không nên tự thao tác znode nội bộ nếu Spring Cloud Zookeeper/Curator đã quản lý registration. Hãy dùng DiscoveryClient hoặc API được hỗ trợ. Cấu trúc znode, serialization, watcher và cache có thể khác theo phiên bản.

ACL ZooKeeper cũng có thể giới hạn quyền đọc theo path. Điều này giúp tách phạm vi discovery: consumer tồn kho chỉ cần đọc nhánh service liên quan, trong khi operator mới có quyền đọc toàn root nếu nhiệm vụ yêu cầu.

## 8. Kubernetes: giới hạn namespace và resource

Trong Kubernetes, Service và EndpointSlice được phân vùng theo namespace. Một ứng dụng thường chỉ cần khám phá service trong một hoặc vài namespace nhất định.

Spring Cloud Kubernetes có các tùy chọn giới hạn namespace discovery theo phiên bản, ví dụ:

```yaml
spring:
  cloud:
    kubernetes:
      discovery:
        all-namespaces: false
        namespaces:
          - shop
          - fulfillment
```

Ý nghĩa là giới hạn phạm vi khám phá vào các namespace được cấu hình, nếu phiên bản integration đang dùng hỗ trợ các thuộc tính này. Hãy kiểm tra tài liệu release train trước khi áp dụng; property name và hành vi có thể thay đổi theo phiên bản.

Kubernetes RBAC nên chỉ cấp quyền list/watch/get các resource cần thiết trong namespace được phép. Tùy chế độ discovery, client có thể cần quyền đọc Services, Endpoints hoặc EndpointSlices, và đôi khi Pod metadata. Không cấp quyền cluster-wide chỉ vì ứng dụng cần gọi một service trong namespace `shop`.

Nếu chỉ cần gọi service nội bộ Kubernetes, DNS Service thường đủ:

```text
http://inventory-service.shop.svc.cluster.local
```

Không nhất thiết phải liệt kê mọi Service qua Kubernetes API để gọi một service có tên đã biết. Spring Cloud Kubernetes Discovery hữu ích khi ứng dụng cần abstraction DiscoveryClient, metadata hoặc client-side load balancing; còn DNS và ClusterIP đã cung cấp discovery ở lớp nền tảng cho lời gọi thông thường.

## 9. Giới hạn phạm vi theo service, namespace và tenant

Có nhiều cách giới hạn scope, tùy registry:

| Phạm vi | Ví dụ | Mục đích |
|---|---|---|
| Service ID | Chỉ truy vấn `inventory-service` | Consumer chỉ cần một dependency |
| Allowlist | `inventory-service`, `pricing-service` | Ứng dụng chỉ biết các dependency đã được phê duyệt |
| Namespace | `shop`, `fulfillment` | Giới hạn theo domain hoặc môi trường |
| Consul namespace/partition | Một namespace/partition được cấp | Phân tách catalog theo tổ chức |
| ZooKeeper root/path | `/services/shop` | Tách cây registration theo domain |
| Kubernetes namespace/RBAC | Chỉ list/watch resource trong namespace được phép | Giới hạn cả dữ liệu nhìn thấy lẫn quyền API |

Scope nên phản ánh ranh giới nghiệp vụ và bảo mật. Không nên dùng một consumer credential có quyền đọc toàn bộ registry nếu consumer chỉ cần hai service.

Allowlist ở tầng ứng dụng giúp tránh truy vấn ngoài dự kiến. Namespace hoặc ACL ở tầng registry/platform còn giúp giảm dữ liệu có thể nhìn thấy và giới hạn tác động khi credential bị lộ. Kết hợp cả hai lớp thường an toàn hơn.

## 10. Cache, refresh và độ mới của dữ liệu

Cache giúp giảm truy vấn lặp, nhưng dữ liệu discovery có thể cũ khi instance thay đổi.

Các tầng cache có thể tồn tại:

- Registry server cache hoặc response cache.
- Client registry cache, ví dụ Eureka client registry snapshot.
- Discovery integration cache hoặc watch state.
- Spring Cloud LoadBalancer cache của danh sách instance.
- DNS cache trong JVM, OS hoặc resolver.
- Cache do ứng dụng tự tạo.

Không nên tự thêm cache nhiều lớp mà không hiểu TTL và invalidation. Nếu TTL quá dài, consumer có thể tiếp tục gọi instance đã bị gỡ. Nếu TTL quá ngắn, registry bị truy vấn thường xuyên và tải tăng.

Một nguyên tắc thực tế:

1. Xác định cache nào đã có trong provider/client.
2. Đo tần suất instance thay đổi và yêu cầu thời gian hội tụ.
3. Chọn TTL/refresh interval phù hợp với yêu cầu đó.
4. Dùng watch/event nếu provider hỗ trợ và integration triển khai đúng.
5. Xử lý trường hợp cache miss hoặc registry tạm thời không truy cập được.
6. Không gọi enumerate toàn catalog để ép cache refresh trên mỗi request.

Cache không phải nguồn dữ liệu có thẩm quyền. Registry mới là nơi quản lý registration; cache chỉ là bản sao phục vụ tra cứu nhanh.

## 11. Tổ chức dependency rõ ràng thay vì khám phá mọi service

Ứng dụng nên biết trước các service mà nó cần gọi. Ví dụ:

```yaml
app:
  dependencies:
    inventory-service: true
    pricing-service: true
    payment-service: false
```

Đây là ví dụ cấu hình nghiệp vụ minh họa; không phải property chuẩn của Spring Cloud. Mục đích là thể hiện dependency allowlist ở tầng ứng dụng.

Có thể khai báo client rõ ràng:

```java
@FeignClient(name = "inventory-service")
public interface InventoryClient {
    // ...
}

@FeignClient(name = "pricing-service")
public interface PricingClient {
    // ...
}
```

Cách này giúp:

- Biết trước dependency nào là bắt buộc.
- Kiểm tra readiness của đúng service quan trọng nếu nghiệp vụ cần.
- Gắn timeout, retry và circuit breaker theo từng client.
- Giới hạn quyền đọc registry.
- Tránh service discovery trở thành cơ chế service directory tùy ý cho mọi chức năng.

Nếu cần dashboard liệt kê catalog, nên xây một chức năng quản trị riêng, có cache, phân trang/filter nếu API hỗ trợ, quyền truy cập rõ ràng và polling interval hợp lý. Không đặt tác vụ đó trong request path của nghiệp vụ.

## 12. Bảo mật khi giới hạn discovery

Giới hạn truy vấn cũng là một biện pháp giảm bề mặt thông tin. Tên service, topology, host, port và metadata có thể tiết lộ cấu trúc hệ thống.

Các biện pháp nên áp dụng:

- Dùng ACL/token để consumer chỉ đọc service/namespace cần thiết.
- Dùng Kubernetes RBAC giới hạn namespace và resource.
- Dùng ZooKeeper ACL giới hạn root/path.
- Không cấp quyền catalog-wide cho ứng dụng không cần liệt kê.
- Không đưa token, password hoặc dữ liệu nhạy cảm vào metadata.
- Tách credential provider, consumer và operator.
- Audit các truy vấn catalog-wide bất thường.
- Bảo vệ endpoint dashboard/admin vì chúng thường có quyền quan sát rộng.

Giới hạn scope ở client không thay thế authorization ở server. Một ứng dụng có thể được lập trình chỉ gọi một service nhưng token vẫn có quyền đọc toàn catalog. Khi credential bị lộ, phạm vi quyền rộng vẫn làm tăng thiệt hại.

## 13. Đo chi phí và kiểm chứng giới hạn scope

Trước và sau khi thay đổi, cần đo các chỉ số phù hợp:

| Chỉ số | Điều cần quan sát |
|---|---|
| Catalog response size | Kích thước payload khi fetch toàn bộ |
| Discovery lookup latency | Thời gian getInstances(serviceId) |
| Registry API request rate | Số request tới registry theo client |
| Client heap | Memory dùng cho registry snapshot và instance objects |
| CPU/GC | Chi phí parse, filter và refresh |
| Cache hit/miss | Tỷ lệ lookup dùng dữ liệu cache |
| Refresh lag | Độ trễ từ registration change tới consumer |
| Empty instance result | Tần suất lookup không có instance |
| Registry error rate | Timeout, 401/403, 5xx hoặc lỗi session |

Có thể dùng Micrometer, application metrics, registry metrics và profiler để thu thập. Tránh gắn label metric bằng mọi instance ID hoặc URL vì cardinality cao có thể làm hệ thống monitoring quá tải. Dùng service ID hoặc nhóm service có kiểm soát, và giữ số label ở mức giới hạn.

Một phép thử đơn giản:

1. Ghi nhận số service và instance hiện tại.
2. Đo thời gian, payload và heap khi enumerate catalog.
3. Đo lookup theo một service ID cụ thể.
4. Lặp thử nghiệm với số lượng service/instance tăng.
5. So sánh request rate và refresh lag của registry.
6. Kiểm tra dữ liệu có còn đủ mới theo yêu cầu vận hành.

Không dùng benchmark local vài service để suy ra năng lực production. Tải thực tế phụ thuộc số client, số replica, tần suất thay đổi registry và cơ chế cache.

## 14. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Startup chậm khi discovery bật | Client đồng bộ catalog lớn hoặc registry phản hồi chậm | Đo fetch latency, payload, cache và phạm vi |
| CPU/heap tăng khi catalog lớn | Deserialize và giữ nhiều service/instance | Giảm enumerate, kiểm tra cache và scope provider |
| Registry nhận quá nhiều request | Dashboard hoặc ứng dụng polling toàn catalog thường xuyên | Tăng interval, cache kết quả, truy vấn theo service |
| Eureka consumer dùng nhiều heap | Registry snapshot client-side lớn | Đo snapshot, số instance, refresh interval và nhu cầu discovery |
| Consul query trả quá nhiều kết quả | Dùng catalog-wide endpoint thay vì health/service | Dùng API theo service và filter phù hợp |
| ZooKeeper đọc nhiều znode | Duyệt toàn root thay vì nhánh service | Dùng DiscoveryClient và giới hạn root/ACL |
| Kubernetes API load tăng | Discovery watch/list trên nhiều namespace | Giới hạn namespaces và RBAC |
| Consumer thấy instance cũ | Cache TTL/refresh hoặc watch propagation | Kiểm tra từng tầng cache và thời gian hội tụ |
| Không tìm thấy service sau khi giới hạn scope | Namespace/path/ACL allowlist thiếu service cần thiết | Đối chiếu service ID, namespace và quyền đọc |

Khi xử lý, hãy xác định chi phí nằm ở server registry, client sync, application enumeration hay LoadBalancer cache. Tăng timeout hoặc tắt discovery không giải quyết đúng nguyên nhân nếu ứng dụng chỉ đang đọc quá rộng.

## 15. Checklist thiết kế discovery scope

1. Consumer có thật sự cần danh sách toàn bộ service không?
2. Có thể dùng `getInstances(serviceId)` thay cho `getServices()` không?
3. Có dependency allowlist rõ ràng cho từng ứng dụng không?
4. Eureka client có cần fetch registry và chu kỳ fetch hiện tại có phù hợp không?
5. Consul có thể dùng API health/service hoặc filter thay catalog-wide query không?
6. ZooKeeper client có thể đọc nhánh service thay toàn bộ root không?
7. Kubernetes discovery có thể giới hạn namespace và RBAC không?
8. Cache hiện có ở những tầng nào và TTL là bao lâu?
9. Độ trễ hội tụ có đáp ứng yêu cầu rollout và failover không?
10. Credential có quyền đọc rộng hơn nhu cầu thực tế không?
11. Catalog-wide dashboard có cache và polling interval hợp lý không?
12. Metrics có tránh cardinality cao theo instance ID/URL không?
13. Đã đo payload, latency, heap, CPU và registry request rate ở quy mô dự kiến chưa?

Chi phí khám phá tăng khi client đọc và xử lý nhiều dữ liệu hơn nhu cầu thực tế. Dùng truy vấn theo service ID, giới hạn namespace/path, quyền ACL/RBAC, cache có TTL và dependency allowlist giúp giảm tải và thu hẹp thông tin được phép nhìn thấy. Tuy nhiên, cần hiểu giới hạn của từng provider: đặc biệt Eureka có thể vẫn đồng bộ registry snapshot rộng ở nền, dù ứng dụng chỉ lookup một service. Đo cả chi phí ở registry, client và request path trước khi điều chỉnh cấu hình.
