# Metadata instance và giới hạn diễn giải theo implementation

## 1. Metadata của instance dùng để làm gì?

Service discovery trả về các instance mà consumer có thể gọi. Ngoài service ID, host, port và URI, một instance có thể mang metadata: các cặp key/value mô tả phiên bản triển khai, zone, nhóm canary, trọng số cân bằng tải hoặc thông tin phục vụ chính sách lựa chọn instance.

Ví dụ, hai instance của `catalog-service` có thể cùng nhận request nhưng chạy hai phiên bản khác nhau:

| Instance | Host | Metadata |
| --- | --- | --- |
| `catalog-a` | `catalog-a.internal` | `version=v1`, `zone=zone-a`, `weight=80` |
| `catalog-b` | `catalog-b.internal` | `version=v2`, `zone=zone-b`, `weight=20` |

Consumer có thể dùng thông tin này để quan sát rollout, ưu tiên instance gần vùng mạng hoặc phân phối tải theo trọng số. Tuy nhiên, metadata chỉ là dữ liệu mô tả cho consumer. Ý nghĩa của một key phụ thuộc vào thành phần đọc nó. Registry có thể lưu và trả metadata mà không tự thay đổi cách định tuyến.

Bài thuộc chương **DiscoveryClient** của mô-đun **SPRING_CLOUD_CORE**. Mô-đun tập trung vào Spring Cloud Commons, Context, cấu hình bên ngoài, discovery, service registry, giao tiếp dịch vụ và kiểm thử, vận hành các abstraction chung.

Sau bài học, người học có thể:

- Giải thích hợp đồng metadata của `ServiceInstance`.
- Phân biệt metadata chung của Spring Cloud Commons với dữ liệu riêng của Eureka, Consul và Kubernetes.
- Nhận diện các key mà Spring Cloud LoadBalancer có diễn giải sẵn.
- Hiểu vì sao cùng một key có thể không có tác dụng nếu consumer không bật đúng supplier hoặc integration.
- Thiết kế schema metadata có namespace, kiểu dữ liệu và quy tắc tương thích.
- Xử lý metadata thiếu, sai định dạng, cũ hoặc không đáng tin cậy.
- Kiểm thử metadata ở provider, registry và consumer.

## 2. Hợp đồng chung của ServiceInstance

Spring Cloud Commons định nghĩa `ServiceInstance` như một abstraction mô tả instance trong hệ thống discovery. Một trong các phương thức của abstraction là:

```java
@Nullable
Map<String, String> getMetadata();
```

Hợp đồng này cho biết metadata là một map key/value, trong đó cả key và value đều là chuỗi. Phương thức được đánh dấu có thể trả về `null`; consumer không nên giả định map luôn tồn tại hoặc luôn có phần tử.

Một `ServiceInstance` thường cung cấp các thông tin:

| Thành phần | Ý nghĩa |
| --- | --- |
| `getServiceId()` | Tên logic của dịch vụ. |
| `getInstanceId()` | Mã nhận diện một registration cụ thể; tùy implementation có thể không có. |
| `getHost()` / `getPort()` | Địa chỉ và cổng consumer dùng để kết nối. |
| `getUri()` | URI gốc của instance. |
| `isSecure()` | Instance được công bố để truy cập bằng HTTPS hay không. |
| `getMetadata()` | Map metadata mà discovery implementation cung cấp cho consumer. |

Điểm quan trọng là Commons chuẩn hóa **hình dạng dữ liệu**, không chuẩn hóa toàn bộ ý nghĩa nghiệp vụ của các key. `ServiceInstance` không định nghĩa rằng `version`, `zone`, `weight`, `team` hoặc `tenant` phải có mặt. Nó cũng không quy định một registry cụ thể phải ánh xạ mọi trường dữ liệu native vào metadata theo cùng cách.

Vì vậy, cần tách ba lớp:

1. **Metadata gốc:** labels, annotations, tags hoặc metadata map được khai báo ở registry/platform.
2. **Metadata projection:** các cặp key/value mà discovery provider chuyển thành `ServiceInstance.getMetadata()`.
3. **Metadata interpretation:** consumer, LoadBalancer hoặc custom code đọc key và áp dụng một hành vi cụ thể.

Một key có mặt ở lớp thứ nhất chưa chắc xuất hiện ở lớp thứ hai. Một key xuất hiện trong `ServiceInstance` cũng chưa chắc có tác dụng nếu không có thành phần ở lớp thứ ba diễn giải nó.

## 3. Metadata không có nghĩa chung cho mọi implementation

Mỗi discovery provider có mô hình dữ liệu và quy tắc ánh xạ riêng. Không nên lấy cấu hình của một provider rồi áp dụng nguyên xi cho provider khác.

| Provider | Nguồn metadata thường gặp | Cách đưa vào `ServiceInstance` | Điểm cần lưu ý |
| --- | --- | --- | --- |
| Eureka | `eureka.instance.metadata-map` | Metadata map trong Eureka instance registration được trả cho client. | Nhiều key chỉ là dữ liệu tùy chỉnh; client phải biết cách diễn giải. |
| Consul | Service `meta`, cấu hình `metadata` và `management-metadata` | Spring Cloud Consul ánh xạ service metadata vào map của `ServiceInstance`. | Consul tags không còn là cách được hỗ trợ để điền map metadata của `ServiceInstance` ở phiên bản hiện hành. |
| Kubernetes | Service labels, annotations và một số thông tin port/namespace | Spring Cloud Kubernetes có thể đưa các trường được bật vào metadata map. | Prefix, cờ bật/tắt và implementation client quyết định key nào xuất hiện. |
| SimpleDiscoveryClient | Metadata khai báo trong cấu hình instance | Được tạo từ danh sách instance cấu hình tĩnh. | Không có registry server tự cập nhật dữ liệu; thay đổi phụ thuộc cấu hình ứng dụng. |

Do đó, nếu ứng dụng chuyển từ Eureka sang Consul hoặc Kubernetes, cần kiểm tra lại mapping và consumer contract. Việc tên key giống nhau không chứng minh dữ liệu có cùng nguồn gốc, phạm vi hoặc thời điểm cập nhật.

## 4. Eureka: metadata map và ý nghĩa phụ thuộc consumer

Với Spring Cloud Netflix Eureka, có thể khai báo metadata cho instance qua `eureka.instance.metadata-map`.

Ví dụ:

```yaml
eureka:
  instance:
    metadata-map:
      zone: zone-a
      weight: "80"
      hint: canary
      API_VERSION: "2"
      com.example.owner: catalog-team
```

Metadata được đăng ký cùng instance và có thể được các Eureka client khác đọc. Theo tài liệu Spring Cloud Netflix, phần lớn metadata bổ sung không làm thay đổi hành vi client nếu client không được lập trình để hiểu ý nghĩa của key đó. Có một số trường hợp Spring Cloud đã định nghĩa semantics riêng, chẳng hạn zone cho lựa chọn instance.

Ví dụ, `com.example.owner` chỉ là dữ liệu mô tả. Nó không tự tạo quyền sở hữu, không gửi cảnh báo tới team và không thay đổi routing. Ứng dụng muốn sử dụng nó phải tự đọc và định nghĩa hành vi.

### 4.1. Zone trong Eureka

Một trường hợp có semantics tích hợp là key `zone`. Spring Cloud Netflix có thể dùng `eureka.instance.metadata-map.zone` để cung cấp zone của instance cho Spring Cloud LoadBalancer. `ZonePreferenceServiceInstanceListSupplier` đọc key `zone` trong metadata để lọc các instance cùng zone với client khi supplier này được cấu hình.

Ví dụ:

```yaml
eureka:
  instance:
    metadata-map:
      zone: zone-a
```

Metadata zone phải khớp với quy ước zone của hạ tầng. `zone-a`, `Zone-A` và `zone_a` là các chuỗi khác nhau nếu consumer so sánh chính xác. Cần thống nhất cách viết và tránh để hostname hoặc region tự động bị hiểu nhầm là zone.

### 4.2. Không phải mọi Eureka metadata đều là cấu hình hành vi

- `zone` có thể được Spring Cloud Netflix/LoadBalancer hiểu khi integration phù hợp được bật.
- `weight` được Spring Cloud LoadBalancer đọc khi sử dụng weighted supplier.
- `hint` được hint-based supplier đọc khi supplier này được cấu hình.
- `API_VERSION` được API-version supplier đọc khi tính năng API version-based load balancing được bật.
- `com.example.owner` không có hành vi chung được Spring Cloud tự động áp dụng.

Không nên suy luận rằng cứ đặt key trong Eureka metadata map là LoadBalancer sẽ tự dùng key đó. Consumer cần đúng implementation và đúng cấu hình supplier.

## 5. Consul: service metadata, management metadata và tags

Consul có trường `meta` cho service. Spring Cloud Consul ánh xạ dữ liệu này vào `ServiceInstance.getMetadata()`. Có thể khai báo metadata trong `spring.cloud.consul.discovery.metadata`; với service quản trị riêng có thể dùng `management-metadata`.

Ví dụ:

```yaml
spring:
  cloud:
    consul:
      discovery:
        metadata:
          zone: zone-a
          weight: "80"
          release-track: stable
          com.example.owner: catalog-team
        management-metadata:
          endpoint-group: operations
```

Spring Cloud Consul hiện hành cũng tạo một số metadata tự động:

| Key | Nguồn tạo | Ý nghĩa |
| --- | --- | --- |
| `group` | `spring.cloud.consul.discovery.instance-group` | Nhóm instance nếu được cấu hình. |
| `secure` | Scheme đăng ký là `https` hay không | Giá trị thể hiện instance được công bố secure. |
| `zone` (tên key có thể cấu hình) | `spring.cloud.consul.discovery.instance-zone` | Zone của instance nếu được cấu hình. |

Tên key zone mặc định là `zone`, có thể thay bằng `spring.cloud.consul.discovery.default-zone-metadata-name`. Không nên tự tạo key trùng với metadata do provider sinh ra nếu chưa xác định quy tắc ưu tiên và ý nghĩa.

### 5.1. Phân biệt metadata và tags

Các phiên bản Spring Cloud Consul cũ từng phân tích tags theo dạng `key=value` để mô phỏng metadata. Cách ánh xạ cũ này không còn được hỗ trợ để điền `ServiceInstance.getMetadata()` ở phiên bản hiện hành. Hãy dùng map `spring.cloud.consul.discovery.metadata` cho metadata.

Tags vẫn có thể được sử dụng như một khái niệm riêng trong Consul và trong các cơ chế lọc/tag của provider. Nhưng không nên giả định tag `zone=zone-a` sẽ tự xuất hiện trong `ServiceInstance.getMetadata()` trên các phiên bản hiện hành.

Khi nâng cấp Spring Cloud Consul, hãy kiểm tra nơi ứng dụng đang khai báo metadata. Một cấu hình từng dựa vào tags để truyền dữ liệu sang consumer có thể cần chuyển sang `metadata` map.

## 6. Kubernetes: labels, annotations và metadata projection

Kubernetes có labels và annotations trên các resource như Service hoặc Pod. Spring Cloud Kubernetes Discovery Client có thể chuyển một số dữ liệu này vào `ServiceInstance.getMetadata()`.

Các thuộc tính điều khiển projection thường gặp:

| Thuộc tính | Tác dụng |
| --- | --- |
| `spring.cloud.kubernetes.discovery.metadata.add-labels` | Đưa labels của Service vào metadata. |
| `spring.cloud.kubernetes.discovery.metadata.add-annotations` | Đưa annotations của Service vào metadata. |
| `spring.cloud.kubernetes.discovery.metadata.add-ports` | Đưa thông tin port được đặt tên vào metadata. |
| `spring.cloud.kubernetes.discovery.metadata.labels-prefix` | Thêm prefix cho key từ labels. |
| `spring.cloud.kubernetes.discovery.metadata.annotations-prefix` | Thêm prefix cho key từ annotations. |
| `spring.cloud.kubernetes.discovery.metadata.ports-prefix` | Thêm prefix cho key port; mặc định là `port.`. |
| `spring.cloud.kubernetes.discovery.metadata.add-pod-labels` | Cho phép thêm labels của Pod nếu implementation hỗ trợ. |
| `spring.cloud.kubernetes.discovery.metadata.add-pod-annotations` | Cho phép thêm annotations của Pod nếu implementation hỗ trợ. |

Trong tài liệu Spring Cloud Kubernetes hiện hành, `add-labels`, `add-annotations` và `add-ports` mặc định được bật; việc đưa pod labels và pod annotations vào metadata mặc định tắt. Cần đối chiếu đúng phiên bản và Kubernetes client implementation vì khả năng hỗ trợ có thể khác.

Ví dụ:

```yaml
spring:
  cloud:
    kubernetes:
      discovery:
        metadata:
          add-labels: true
          add-annotations: true
          labels-prefix: "label."
          annotations-prefix: "annotation."
          add-pod-labels: false
          add-pod-annotations: false
```

Service manifest:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog
  labels:
    app: catalog
    release-track: canary
  annotations:
    com.example.owner: catalog-team
spec:
  selector:
    app: catalog
  ports:
    - name: http
      port: 80
      targetPort: 8080
```

Với prefix như ví dụ, consumer có thể nhìn thấy các key `label.app`, `label.release-track` hoặc `annotation.com.example.owner`. Nếu không đặt prefix, tên key có thể trùng với key do provider hoặc ứng dụng tự định nghĩa. Prefix giúp phân biệt nguồn và giảm nguy cơ xung đột.

Spring Cloud Kubernetes còn có thể bổ sung các key như `k8s_namespace`, `type` và metadata về ports. Cách tạo `ServiceInstance` có thể chứa thêm thông tin theo phiên bản và loại discovery client. Không nên giả định mọi key này có mặt trong tất cả implementation.

## 7. Những key mà Spring Cloud LoadBalancer có thể diễn giải

Spring Cloud LoadBalancer có một số supplier biết cách đọc metadata. Đây là ví dụ rõ nhất cho thấy ý nghĩa của metadata đến từ consumer implementation.

| Key metadata | Supplier / tính năng | Hành vi |
| --- | --- | --- |
| `weight` | `WeightedServiceInstanceListSupplier` | Đọc và phân tích trọng số; nếu key không có, mặc định trọng số là `1`. |
| `zone` | `ZonePreferenceServiceInstanceListSupplier` | Lọc instance theo zone mong muốn; nếu zone không có hoặc không tìm được instance cùng zone, supplier trả lại danh sách gốc. |
| `hint` | `HintBasedServiceInstanceListSupplier` | Lọc instance có hint khớp request hint; nếu không tìm thấy instance khớp, supplier trả lại danh sách được delegate cung cấp. |
| `API_VERSION` | Blocking/Reactive API version supplier | Tìm instance có metadata version khớp với version của request hoặc default version. |

Các key trên không tự có tác dụng chỉ vì xuất hiện trong registry:

- Weighted supplier phải được cấu hình trong chuỗi `ServiceInstanceListSupplier`.
- Zone preference cần supplier tương ứng. Eureka có integration tự cung cấp zone cho LoadBalancer; với discovery client khác, có thể cần đặt `spring.cloud.loadbalancer.zone`.
- Hint-based supplier phải được bật; request cần có hint từ header hoặc property theo cấu hình.
- API version-based supplier phải được bật và request phải cung cấp version theo header, query parameter, path segment hoặc media type parameter đã cấu hình.

Với các cấu hình dựng sẵn, có thể chọn `weighted`, `zone-preference` hoặc `api-version` qua `spring.cloud.loadbalancer.configurations` cho client tương ứng. Hint-based supplier có thể được ghép trong custom supplier chain bằng `withHints()`:

```yaml
spring:
  cloud:
    loadbalancer:
      configurations: weighted
```

```java
@Bean
ServiceInstanceListSupplier serviceInstanceListSupplier(
        ConfigurableApplicationContext context) {
    return ServiceInstanceListSupplier.builder()
            .withDiscoveryClient()
            .withCaching()
            .withHints()
            .build(context);
}
```

### 7.1. Weighted load balancing

Khi bật weighted supplier, metadata key `weight` được đọc như một số. Ví dụ:

```yaml
eureka:
  instance:
    metadata-map:
      weight: "80"
```

Giá trị `80` không có nghĩa rằng instance tự nhận 80% traffic trong mọi cấu hình. Nó chỉ được dùng khi LoadBalancer đang chạy weighted supplier. Nếu ứng dụng dùng round-robin supplier mặc định, key `weight` không tự thay đổi thuật toán.

### 7.2. Zone preference

Metadata:

```yaml
eureka:
  instance:
    metadata-map:
      zone: zone-a
```

Phía consumer cần biết zone mong muốn, ví dụ thông qua cấu hình `spring.cloud.loadbalancer.zone`, hoặc qua integration Eureka tương ứng. Zone preference không bảo đảm tuyệt đối rằng mọi request luôn ở cùng zone: nếu không có instance cùng zone, supplier có thể trả danh sách gốc để hệ thống vẫn có khả năng phục vụ.

### 7.3. Hint-based routing

Metadata:

```yaml
eureka:
  instance:
    metadata-map:
      hint: canary
```

Hint-based supplier có thể đọc header mặc định `X-SC-LB-Hint` hoặc hint được cấu hình theo service. Khi có request hint `canary`, supplier tìm instance có metadata `hint=canary`. Nếu không có instance khớp, hành vi mặc định là trả lại danh sách từ delegate thay vì trả danh sách rỗng.

Không dùng hint như một cơ chế phân quyền hoặc cô lập dữ liệu. Nó là tín hiệu lựa chọn instance, không phải ranh giới bảo mật.

### 7.4. API version-based routing

Spring Cloud LoadBalancer có supplier cho API version. Khi tính năng được bật, request mang version và supplier tìm metadata key `API_VERSION` có giá trị khớp.

Ví dụ:

```yaml
eureka:
  instance:
    metadata-map:
      API_VERSION: "2"
```

Nếu không tìm thấy instance có version phù hợp, mặc định danh sách trả về có thể rỗng. Có thể cấu hình `spring.cloud.load-balancer.clients.<serviceId>.api-version.fallbackToAvailableInstances=true` cho service tương ứng nếu chính sách cho phép fallback sang instance bất kỳ. Chỉ bật fallback khi các phiên bản API thực sự tương thích; nếu không, fallback có thể tạo lỗi runtime khó phát hiện.

## 8. Metadata tùy chỉnh: tự định nghĩa contract

Ứng dụng có thể cần key riêng như:

```text
com.example.owner=catalog-team
com.example.release-track=canary
com.example.routing-policy=low-latency
com.example.capability=bulk-read
```

Vì metadata map chỉ chứa chuỗi, ứng dụng phải tự quy định:

- Tên key và namespace sở hữu key.
- Kiểu dữ liệu logic: boolean, integer, enum, version hoặc chuỗi.
- Đơn vị đo nếu là số, chẳng hạn milliseconds hay requests/second.
- Giá trị hợp lệ và giá trị mặc định khi key thiếu.
- Hành vi khi key sai định dạng hoặc không được hỗ trợ.
- Phiên bản schema metadata và quy tắc tương thích khi rollout.

Không dùng key chung như `mode`, `team` hoặc `version` nếu nhiều hệ thống có thể hiểu khác nhau. Có thể dùng namespace như `com.example.*` cho metadata riêng. Với key được Spring Cloud LoadBalancer định nghĩa như `zone`, `weight`, `hint`, `API_VERSION`, phải giữ đúng tên mà supplier yêu cầu.

### 8.1. Quy ước giá trị

Ví dụ schema:

| Key | Kiểu logic | Ví dụ | Khi thiếu |
| --- | --- | --- | --- |
| `com.example.release-track` | Enum | `stable`, `canary` | `stable` |
| `com.example.max-payload-bytes` | Số nguyên | `1048576` | Không giới hạn hoặc từ chối tùy chính sách |
| `com.example.supports-bulk-read` | Boolean | `true`, `false` | `false` |
| `com.example.config-schema` | Version | `1` | Dùng schema legacy đã định nghĩa |

Không dùng giá trị mơ hồ như `yes`, `on`, `enabled` lẫn lộn nếu consumer chỉ chấp nhận `true`/`false`. Không dùng số không có đơn vị cho timeout hoặc kích thước nếu nhiều nhóm có thể diễn giải khác nhau.

### 8.2. Consumer phải parse an toàn

Vì `getMetadata()` có thể trả `null`, và giá trị có thể sai định dạng, hãy xử lý phòng thủ:

```java
Map<String, String> metadata = instance.getMetadata();
String rawWeight = metadata == null ? null : metadata.get("weight");

int weight = 1;
if (rawWeight != null) {
    try {
        int parsed = Integer.parseInt(rawWeight);
        if (parsed > 0 && parsed <= 100) {
            weight = parsed;
        }
    }
    catch (NumberFormatException ex) {
        // Ghi metric/log đã làm sạch; dùng chính sách fallback đã thống nhất.
    }
}
```

Đây là ví dụ cho custom consumer. Nếu dùng supplier có sẵn của Spring Cloud, hãy tuân thủ contract của supplier đó và kiểm thử cả giá trị sai định dạng. Không giả định mọi supplier có cùng fallback khi parse thất bại.

Không sửa trực tiếp map trả về từ `getMetadata()`. Hãy coi metadata là dữ liệu đầu vào chỉ đọc; nếu cần biến đổi, tạo map hoặc object riêng.

## 9. Giới hạn diễn giải và các rủi ro thiết kế

### 9.1. Metadata không phải schema chung

Một key `version` có thể là phiên bản ứng dụng, phiên bản API, phiên bản image hoặc phiên bản schema. Nếu không định nghĩa rõ, consumer có thể so sánh sai hoặc route request tới instance không tương thích.

Dùng key cụ thể như `API_VERSION` khi tích hợp với supplier có contract tương ứng; dùng namespace riêng cho metadata nội bộ.

### 9.2. Metadata không phải trạng thái health

Metadata `healthy=true` chỉ là một chuỗi do nguồn đăng ký cung cấp. Nó không chứng minh instance đang sống hoặc sẵn sàng nhận traffic. Hãy dùng health check và trạng thái của registry/discovery provider. Nếu cần một capability hoặc trạng thái vận hành đặc biệt, định nghĩa rõ nó khác với liveness/readiness.

### 9.3. Metadata không phải cơ chế bảo mật

Không lưu password, access token, private key, session ID hoặc dữ liệu cá nhân trong metadata. Registry thường cho phép nhiều client đọc thông tin đăng ký. Metadata cũng không phải nguồn đáng tin cậy để quyết định user có quyền truy cập tài nguyên hay không.

Nếu metadata được dùng để chọn tenant, role hoặc nhóm xử lý, consumer vẫn phải xác thực request và kiểm tra quyền bằng cơ chế bảo mật chuyên biệt. Không để client tự khai báo metadata rồi dùng nó làm căn cứ cấp quyền.

### 9.4. Metadata có thể thiếu hoặc không đồng nhất

Trong một cluster có thể tồn tại instance từ nhiều phiên bản ứng dụng. Một phiên bản cũ chưa phát key mới, trong khi consumer mới đã bắt đầu đọc key đó. Consumer phải có chính sách khi key vắng mặt và rollout cần giữ tương thích ngược.

Khi đổi schema metadata:

1. Triển khai consumer hiểu cả schema cũ và mới.
2. Bắt đầu đăng ký metadata mới.
3. Quan sát tỷ lệ instance đã có key mới.
4. Chỉ bỏ hỗ trợ schema cũ sau khi toàn bộ instance đã chuyển đổi.

### 9.5. Metadata có thể cũ do cache

Registry, discovery client và Spring Cloud LoadBalancer có thể có cache. Tài liệu Spring Cloud LoadBalancer hiện hành đặt TTL mặc định của cache là 35 giây nếu dùng cấu hình mặc định; discovery client cũng có thể có cache riêng. Vì vậy, thay đổi metadata tại registry chưa chắc xuất hiện ngay trong mọi consumer.

Nếu metadata ảnh hưởng routing, hãy xác định độ trễ chấp nhận được, cấu hình cache phù hợp và tránh cache hai lần không cần thiết. Khi cần kiểm tra, so sánh dữ liệu tại registry, kết quả `DiscoveryClient.getInstances()` và danh sách instance mà LoadBalancer thực sự sử dụng.

### 9.6. Metadata không thay thế thông tin kết nối chuẩn

Không lưu host, port hoặc secure flag thành metadata riêng nếu `ServiceInstance` đã có các trường chuẩn tương ứng. Không dùng metadata thay cho URI hoặc service ID. Các key tự đặt có thể bị bỏ qua bởi client hoặc gây xung đột với key do provider tạo.

## 10. Kiểm thử metadata theo từng lớp

Một bài test chỉ kiểm tra rằng YAML có key metadata chưa chứng minh consumer nhận và sử dụng đúng key đó. Cần kiểm tra cả chuỗi từ khai báo đến diễn giải.

| Lớp kiểm thử | Nội dung | Ví dụ assertion |
| --- | --- | --- |
| Provider configuration | Cấu hình được bind đúng vào metadata map của provider | Eureka/Consul/Kubernetes tạo registration có key và value mong muốn. |
| Registry integration | Metadata được lưu và trả về | Đọc instance từ registry, kiểm tra key có mặt và giá trị đúng. |
| Discovery projection | Provider ánh xạ metadata sang `ServiceInstance` | `getMetadata()` có key theo đúng prefix/format. |
| Consumer parsing | Xử lý key thiếu, null, sai định dạng và giá trị ngoài miền | Không ném lỗi không kiểm soát; fallback đúng contract. |
| LoadBalancer supplier | Supplier đọc đúng key khi được bật | Weighted/zone/hint/API-version chọn hoặc lọc đúng instance. |
| Compatibility | Instance cũ và mới cùng tồn tại | Consumer không lỗi khi instance cũ chưa có metadata mới. |
| Security | Metadata không chứa secret hoặc dữ liệu nhạy cảm | Kiểm tra registration payload và log. |
| Cache | Metadata mới xuất hiện sau thời gian cache phù hợp | Xác minh độ trễ cập nhật theo cấu hình cache. |

### 10.1. Unit test consumer

Dùng các `ServiceInstance` giả lập:

- Map metadata có đủ key hợp lệ.
- Map rỗng.
- Metadata là `null`.
- Giá trị `weight` không phải số.
- Giá trị `zone` không nằm trong danh sách zone được hỗ trợ.
- `API_VERSION` thiếu hoặc không tương thích.

Kiểm tra rằng consumer không biến dữ liệu không hợp lệ thành lỗi không kiểm soát hoặc lựa chọn instance ngoài chính sách.

### 10.2. Integration test provider

Với từng discovery implementation, khởi động provider test hoặc dùng registry test phù hợp:

- Đăng ký instance.
- Đọc registration từ registry.
- Gọi discovery client để lấy `ServiceInstance`.
- So sánh metadata map với contract đã định nghĩa.

Không chỉ test `Map` tự tạo trong unit test nếu mục tiêu là xác minh mapping của Eureka, Consul hoặc Kubernetes. Những mapping đó thuộc implementation của provider.

### 10.3. Test LoadBalancer

Nếu sử dụng metadata cho routing, kiểm tra supplier tương ứng đã thực sự được đăng ký:

- Weighted: xác nhận supplier có bật weighted selection và xử lý `weight`.
- Zone: xác nhận local zone và metadata `zone` khớp quy ước.
- Hint: xác nhận request hint được truyền và metadata `hint` được lọc.
- API version: xác nhận request version khớp metadata `API_VERSION`; kiểm tra cả trường hợp không tìm thấy version phù hợp.

Nếu test chỉ khởi tạo `RoundRobinLoadBalancer` mặc định, metadata `weight` sẽ không chứng minh weighted routing hoạt động.

## 11. Chẩn đoán sự cố

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Metadata có trong YAML nhưng không có trong `ServiceInstance` | Sai property name, provider không map nguồn đó hoặc cấu hình projection chưa bật | Kiểm tra registration tại registry rồi kiểm tra kết quả `getMetadata()`. |
| Consul tags không xuất hiện trong metadata map | Đang dựa vào cơ chế tags cũ | Chuyển sang `spring.cloud.consul.discovery.metadata`. |
| Kubernetes label không có prefix mong đợi | Prefix hoặc cờ `add-labels` khác cấu hình | Kiểm tra metadata projection và namespace key. |
| `weight` có mặt nhưng traffic vẫn round-robin | Weighted supplier chưa được bật | Kiểm tra `ServiceInstanceListSupplier` đang dùng. |
| Zone preference không lọc instance | Supplier chưa cấu hình, zone của client chưa có hoặc key sai | Kiểm tra `spring.cloud.loadbalancer.zone` và metadata key `zone`. |
| Hint không chọn được canary | Request không truyền hint hoặc instance không có key `hint` tương ứng | Kiểm tra header/property và supplier hint-based. |
| API version không tìm thấy instance | `API_VERSION` thiếu hoặc khác giá trị request | Kiểm tra version parser, metadata và fallback policy. |
| Consumer đọc metadata cũ sau cập nhật | Registry/discovery/load-balancer cache | Kiểm tra TTL và cache ở từng lớp. |
| Một key có giá trị khác giữa provider | Provider tạo metadata tự động hoặc dùng quy tắc prefix khác | Kiểm tra metadata gốc và projection riêng của implementation. |
| Metadata bị dùng nhầm như health hoặc quyền truy cập | Consumer gán semantics vượt quá contract | Tách health/authentication khỏi metadata tùy chỉnh. |

## 12. Hướng dẫn thiết kế

1. **Xem `ServiceInstance.getMetadata()` là map dữ liệu tùy chọn.** Xử lý trường hợp null, thiếu key và giá trị sai định dạng.
2. **Xác định provider trước khi viết cấu hình.** Eureka, Consul, Kubernetes và SimpleDiscoveryClient có cách ánh xạ khác nhau.
3. **Viết contract metadata cho consumer.** Ghi rõ key, kiểu logic, đơn vị, giá trị hợp lệ, default và phiên bản schema.
4. **Dùng key chuẩn khi tích hợp supplier có sẵn.** `weight`, `zone`, `hint` và `API_VERSION` có semantics cụ thể trong các tính năng tương ứng.
5. **Bật đúng LoadBalancer supplier.** Metadata không tự thay thuật toán cân bằng tải mặc định.
6. **Dùng namespace cho key riêng.** Tránh trùng key tự động sinh bởi provider hoặc key được Spring Cloud sử dụng.
7. **Giữ tương thích trong quá trình rollout.** Consumer phải xử lý instance cũ chưa có key mới.
8. **Không lưu secret và không cấp quyền từ metadata.** Dữ liệu discovery không thay thế hệ thống bảo mật.
9. **Xem xét cache và độ trễ cập nhật.** Đừng giả định thay metadata tại registry sẽ có hiệu lực tức thời trên mọi consumer.
10. **Kiểm thử xuyên suốt provider → registry → DiscoveryClient → consumer.** Unit test map đơn lẻ không xác minh mapping của implementation.

## 13. Câu hỏi tự kiểm tra

1. `ServiceInstance.getMetadata()` chuẩn hóa hình dạng dữ liệu nào và có giới hạn gì?
2. Vì sao metadata được lưu trong registry chưa chắc xuất hiện trong `ServiceInstance.getMetadata()`?
3. Tại sao Eureka metadata bổ sung thường không làm thay đổi hành vi client?
4. Spring Cloud Consul hiện hành ánh xạ service metadata như thế nào, và vì sao không nên tiếp tục dùng tags theo cách cũ?
5. Spring Cloud Kubernetes có thể lấy metadata từ những resource field nào?
6. Những điều kiện nào phải có để key `weight` thực sự ảnh hưởng Spring Cloud LoadBalancer?
7. `zone`, `hint` và `API_VERSION` được các supplier nào diễn giải?
8. Vì sao metadata `healthy=true` không thay thế health check?
9. Làm thế nào giữ tương thích khi instance cũ chưa đăng ký metadata key mới?
10. Hãy thiết kế một integration test kiểm tra metadata từ Eureka registration tới quyết định chọn instance của LoadBalancer.

## 14. Tài liệu tham khảo chính thức

- [Spring Cloud Commons — ServiceInstance API](https://docs.spring.io/spring-cloud-commons/docs/current/api/org/springframework/cloud/client/ServiceInstance.html)
- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud Netflix — Eureka Metadata for Instances and Clients](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Consul — Service Discovery and Metadata](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Kubernetes — Discovery Metadata Properties](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html)

Metadata contract, key mapping và semantics có thể thay đổi theo implementation và release train. Trước khi dùng metadata để điều khiển routing, hãy đối chiếu tài liệu của provider, Spring Cloud Commons và supplier thực sự chạy trong ứng dụng.
