# Bảo vệ metadata và nguồn danh sách bản sao

Spring Cloud LoadBalancer chọn nơi gửi request dựa trên các `ServiceInstance` mà chuỗi `ServiceInstanceListSupplier` cung cấp. Một instance thường mang **service ID**, **host**, **port**, trạng thái **secure** và `metadata` như zone, version hoặc weight. Những dữ liệu này trông giống cấu hình vận hành, nhưng thực chất chúng có thể ảnh hưởng đến **đích mạng nhận request**, **độ ưu tiên định tuyến** và **khả năng truyền thông tin nhạy cảm**.

Nếu nguồn danh sách bị sửa trái phép, một caller có thể được dẫn tới instance giả mạo hoặc bị chuyển khỏi vùng triển khai mong muốn. Nếu metadata bị thao túng, thuật toán trọng số hoặc chính sách zone/version có thể đưa lưu lượng đến đích không phù hợp. Đây là lý do **bảo mật giao tiếp** không chỉ bao gồm TLS và token; nó còn bao gồm **tính toàn vẹn, quyền thay đổi và nguồn gốc của thông tin dùng để chọn instance**.

Bài học thuộc chương **Bảo mật giao tiếp** của module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Mục tiêu là bảo vệ đầu vào của Spring Cloud LoadBalancer khi chọn `ServiceInstance` theo service ID, phối hợp discovery, health check và routing policy, đồng thời vận dụng vào RestClient, WebClient và OpenFeign. Chúng ta sẽ xây dựng mô hình mối đe dọa, các lớp phòng vệ, một ví dụ lọc instance và kịch bản kiểm thử.

> **Giới hạn bảo đảm:** metadata trong `ServiceInstance` không mặc nhiên được Spring Cloud LoadBalancer ký số hay xác thực nguồn gốc. Việc bảo vệ phải bắt đầu từ **registry/configuration source**, tiếp tục qua **supplier chain**, và được củng cố tại **transport, network egress và authorization của dịch vụ đích**.

## 1. Danh sách instance là dữ liệu điều khiển định tuyến

Giả sử `order-service` gọi:

~~~java
catalogRestClient.get()
    .uri("http://catalog-service/api/items/42")
    .retrieve()
    .body(String.class);
~~~

Một supplier cung cấp dữ liệu logic:

~~~text
serviceId = catalog-service

A: instanceId=catalog-a
   host=10.0.1.11, port=8443, secure=true
   metadata={zone=zone-a, version=v1, weight=80}

B: instanceId=catalog-b
   host=10.0.2.12, port=8443, secure=true
   metadata={zone=zone-b, version=v1, weight=20}
~~~

Các trường có thể có nguồn khác nhau: service registry, Kubernetes API, Consul, Eureka, cấu hình `SimpleDiscoveryClient` hoặc supplier tùy biến. Metadata được biểu diễn dưới dạng `Map<String, String>`; cách một thuật toán/supplier diễn giải map đó phụ thuộc vào cấu hình đang sử dụng.

| Trường | Ảnh hưởng có thể có | Rủi ro khi không tin cậy |
|---|---|---|
| `serviceId` | Ghép request logic với danh sách đích | Đăng ký nhầm/giả mạo dịch vụ |
| `host` | Xác định địa chỉ kết nối | Chuyển request sang máy không được phép |
| `port` | Xác định cổng dịch vụ | Truy cập cổng quản trị hoặc endpoint nội bộ khác |
| `isSecure()` / scheme | Ảnh hưởng đến URL và vận chuyển TLS theo integration | Hạ cấp kết nối hoặc lỗi xác minh danh tính |
| `instanceId` | Quan sát và phân biệt các bản sao | Giả mạo ID, gây nhầm log/metric |
| `zone` / region | Có thể dùng bởi zone-aware policy | Dẫn request ra sai vùng dữ liệu |
| `version` / canary | Có thể dùng bởi chính sách định tuyến tùy biến | Đưa traffic tới bản thử nghiệm trái phép |
| `weight` | Có thể ảnh hưởng chọn đích khi bật weighted supplier | Tập trung traffic vào instance do đối tượng xấu kiểm soát |
| Metadata tùy biến khác | Routing hint, tagging, feature flag | Injection, lộ secret, bùng nổ metric cardinality |

**Phân biệt dữ liệu và quyền quyết định:** một trường `metadata["weight"]` chỉ có tác động nếu supplier/chính sách thực sự đọc nó. Nhưng khi đã dùng làm tín hiệu điều khiển, trường đó phải được xem là **cấu hình có quyền cao**, không phải chuỗi tùy ý do instance tự công bố.

## 2. Ranh giới tin cậy từ registry đến HTTP request

~~~mermaid
flowchart LR
    A["Control plane / người được quyền đăng ký"] --> R["Registry / Kubernetes API / cấu hình"]
    R --> D["DiscoveryClient"]
    D --> S["ServiceInstanceListSupplier"]
    S --> C["Cache / health / route filters"]
    C --> LB["Spring Cloud LoadBalancer"]
    LB --> H["RestClient / WebClient / Feign"]
    H --> I["Instance đích đã chọn"]

    U["Nguồn bị chiếm quyền / cấu hình giả"] -. "chỉnh host, port, metadata" .-> R
    M["Metadata từ nguồn kém tin cậy"] -. "poisoning" .-> S
~~~

Một kiến trúc cần xác định rõ ba câu hỏi:

1. **Ai có quyền tạo, sửa, xóa instance?** Quyền ghi vào registry/config source không thể trao rộng chỉ vì đó là “thông tin discovery”.
2. **Ai xác thực nguồn dữ liệu?** DiscoveryClient nhận dữ liệu qua kết nối nào, với credentials và permission gì?
3. **Ai có quyền dùng dữ liệu đó để kết nối?** Caller có kiểm tra đích, TLS identity và giới hạn egress hay hoàn toàn tin vào host/port lấy từ registry?

Một registry có TLS nhưng mọi workload đều có quyền sửa entry của service khác vẫn có nguy cơ **đăng ký instance giả**. Một registry phân quyền tốt nhưng HTTP client tắt certificate verification vẫn có nguy cơ **gửi request tới đích giả mạo**. Bảo mật cần nhiều lớp độc lập.

## 3. Mô hình mối đe dọa cho discovery và metadata

| Mối đe dọa | Điểm bị lợi dụng | Hậu quả | Lớp phòng vệ chính |
|---|---|---|---|
| Đăng ký instance giả | Quyền ghi registry quá rộng | Caller gửi request đến attacker-controlled host | ACL/RBAC, registry authentication, egress policy |
| Sửa host/port | Dữ liệu địa chỉ từ discovery/config | SSRF vào mạng nội bộ hoặc cổng quản trị | Kiểm soát nguồn, allowlist đích, network policy |
| Giả mạo zone | Metadata routing | Đi sai vùng, vi phạm data residency | Trusted metadata authority, zone policy |
| Đẩy weight cực lớn | Weighted routing policy | Hút phần lớn request về một instance | Giới hạn và xác thực weight |
| Thay secure flag/scheme | ServiceInstance transport fields | Downgrade HTTP hoặc TLS identity mismatch | Bắt buộc HTTPS/mTLS theo policy và xác minh cert |
| Thêm instance ở môi trường khác | Thiếu namespace/environment isolation | Prod gọi nhầm staging | Registry isolation, environment-specific identity |
| Poison cache | Dữ liệu xấu được cache | Đích giả tiếp tục được chọn sau khi registry sửa | TTL/revocation, cache invalidation, kiểm tra trước routing |
| Giả mạo health | Health endpoint không tin cậy | Instance độc hại vẫn được coi healthy | Health trên kênh tin cậy, auth/network policy |
| Metadata chứa bí mật | Đưa token/credential vào map | Lộ qua discovery API, log hoặc metric | Không đưa secret vào metadata, secret manager |
| Metadata payload bất thường | Parser/formatter tùy biến | Lỗi parser, log injection, memory/cardinality | Bounds, schema, encoding, safe logging |

Đây là những **kịch bản rủi ro**, không phải tuyên bố mặc định mọi discovery implementation đều dễ bị khai thác. Độ phơi nhiễm phụ thuộc topology, permission, transport, khả năng đọc/ghi registry và chính sách của ứng dụng.

### Vì sao đây còn là rủi ro SSRF?

Server-Side Request Forgery (SSRF) thường được nhắc khi ứng dụng nhận một URL từ người dùng rồi tự gọi URL đó. Với client-side load balancing, **URL đích cũng có thể bị ảnh hưởng gián tiếp bởi một nguồn dữ liệu ngoài vùng tin cậy**.

Ví dụ registry bị thay đổi từ `catalog-b:8443` sang một địa chỉ quản trị nội bộ hoặc một IP link-local đặc biệt. Nếu caller tin tưởng hoàn toàn danh sách, nó có thể gửi request và Authorization header tới một đích không được cấp phép.

Điểm quan trọng là **metadata hoặc registry record trở thành đầu vào điều khiển địa chỉ mạng**, dù người dùng ngoài không trực tiếp truyền tham số `url` vào API.

## 4. Không coi metadata là bằng chứng danh tính

Một record giả có thể tự khai báo:

~~~text
serviceId=catalog-service
metadata={
  environment=production,
  zone=zone-a,
  trusted=true,
  weight=100
}
~~~

Trường `trusted=true` **không làm record trở nên đáng tin**. Nếu attacker có quyền sửa metadata, họ cũng có thể sửa cờ tự nhận là “trusted”. Tương tự, một trường `zone=zone-a` không chứng minh instance thực sự chạy trong zone-a.

**Danh tính đáng tin** phải đến từ nguồn được xác thực và kiểm soát quyền, ví dụ:

- Service account/workload identity được nền tảng xác nhận.
- Certificate identity được xác minh qua TLS/mTLS với CA và policy phù hợp.
- Quyền đọc/ghi registry phân theo namespace, service, role và môi trường.
- Admission policy hoặc quy trình triển khai quản trị labels/annotations.
- Quy tắc độc lập để giới hạn service ID và endpoint mà caller được phép kết nối.

Metadata có thể dùng để **gợi ý định tuyến**, nhưng không được sử dụng như **cơ chế xác thực hoặc phân quyền duy nhất**. Một quyết định bảo mật phải dựa trên identity/permissions được kiểm chứng, không dựa trên label tự khai.

## 5. Bảo vệ nơi sinh và lưu danh sách ServiceInstance

### Registry có quyền đọc và quyền ghi tách biệt

Trong Eureka, Consul, Kubernetes hoặc một registry nội bộ, cần kiểm soát độc lập:

- Ai được **đăng ký** hoặc **hủy đăng ký** instance?
- Ai được **sửa metadata** như zone/weight/version?
- Ai được **đọc danh sách** của dịch vụ nào?
- Một workload bị chiếm quyền có thể sửa record của workload khác không?
- Có **audit log** cho thao tác thay đổi control plane không?
- Registry có được truy cập qua kết nối xác thực và mã hóa không?

Một caller thường chỉ cần **đọc discovery** để chọn instance. Nếu workload chỉ cần discovery thì không nên cấp quyền ghi toàn bộ registry. Với cơ chế tự đăng ký, quyền ghi phải được giới hạn ở danh tính/instance mà workload sở hữu.

### Ví dụ Role đọc trong Kubernetes

Một manifest minh họa cho namespace `apps`:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: catalog-discovery-reader
  namespace: apps
rules:
  - apiGroups: [""]
    resources: ["services", "endpoints"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
~~~

Manifest trên **chỉ định nghĩa Role**, chưa gán quyền cho service account. Khi triển khai thật, cần RoleBinding phù hợp và phải kiểm tra Spring Cloud Kubernetes discovery implementation đang dùng cần resources nào (có thể khác theo phiên bản/cách chạy). Chỉ cấp tối thiểu những API thực sự được dùng; không sao chép thêm `create`, `update`, `patch`, `delete` nếu caller không cần.

Lưu ý nếu hệ thống có thể đọc nhiều namespace, quyền `list/watch` trên diện rộng làm tăng bề mặt phơi nhiễm dữ liệu. Tách namespace/service account và giới hạn phạm vi cần thiết.

### Cấu hình tĩnh cũng cần bảo vệ

Khi dùng `SimpleDiscoveryClient`:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: https://catalog-a.internal.example:8443
              - uri: https://catalog-b.internal.example:8443
~~~

Danh sách nằm trong YAML, nhưng YAML có thể đến từ Git, Config Server, ConfigMap, environment variable hoặc pipeline triển khai. Vì vậy phải bảo vệ **repository, quyền merge, CI/CD, secret store và cấu hình runtime**; danh sách “tĩnh” không đương nhiên an toàn nếu mọi nhân viên hoặc workload đều có quyền thay đổi.

## 6. Mã hóa và xác thực đường tới discovery source

Một discovery client có thể gọi registry qua mạng hoặc đọc từ API của nền tảng. Yêu cầu căn bản:

1. **TLS hợp lệ** khi dùng giao thức qua mạng; không tắt hostname verification hoặc tin mọi certificate.
2. **Xác thực danh tính caller** bằng credential, client certificate hoặc service account token phù hợp.
3. **Ủy quyền theo phạm vi nhỏ nhất** ở API registry.
4. **Quản lý secrets** bằng cơ chế được hỗ trợ, không hardcode token vào YAML public, URL query hay `ServiceInstance.getMetadata()`.
5. **Bảo vệ tính mới và vòng đời cache** để các thay đổi thu hồi quyền được áp dụng kịp thời.
6. **Audit thay đổi** instance và metadata, đặc biệt host/port/scheme và routing hints.

TLS bảo vệ đường truyền đến **nguồn dữ liệu**, không tự chứng minh rằng **mọi record nằm trong nguồn** đều do đúng service sở hữu. Cần phân quyền ghi và cơ chế xác thực workload.

### Tách ba kênh bảo mật

| Kênh | Mục tiêu | Không bảo đảm thay thế điều gì? |
|---|---|---|
| Caller → registry | Nhận danh sách có nguồn gốc xác thực | Không bảo đảm instance đích còn sống |
| Caller → instance | Bảo vệ request, credentials và response | Không kiểm soát ai được ghi registry |
| Instance → registry / control plane | Chỉ workload hợp lệ đăng ký hoặc đổi metadata | Không thay thế authorization nghiệp vụ của endpoint |

Nếu một kênh bị bỏ trống, chỉ mã hóa kênh còn lại không đủ để bảo vệ hệ thống.

## 7. Host, port, scheme và TLS identity là dữ liệu nhạy cảm về điều khiển

Giả sử service ID logic là `catalog-service`, nhưng instance được chọn trả:

~~~text
host = 192.0.2.50
port = 8080
secure = false
metadata = {zone=trusted-zone}
~~~

Một client không nên mặc nhiên tin đích này chỉ vì metadata nói `trusted-zone`. Trong production, chính sách có thể yêu cầu:

- **Service ID** phải khớp downstream mà caller được phép gọi.
- Endpoint phải thuộc **vùng mạng/vùng triển khai được duyệt**.
- **Port** nằm trong danh sách cổng dịch vụ hợp lệ.
- **TLS** phải bật với CA/chứng chỉ và identity phù hợp.
- Không cho gửi Authorization headers sang bất kỳ host do người dùng hoặc registry chưa xác thực quyết định.
- Không gọi loopback, link-local, metadata service, admin ports hoặc địa chỉ không mong muốn do dữ liệu bên ngoài chỉ định.

`ServiceInstance.isSecure()` và scheme từ `getUri()` là **thuộc tính dữ liệu**, không phải chứng cứ một phiên TLS đã xác thực thành công. TLS phải được **thực thi và xác minh ở HTTP transport thực tế**.

### Lưu ý về certificate name và load balancing

Sau khi LoadBalancer chọn instance A/B, HTTP connector có thể kết nối tới hostname hoặc IP thực của instance. Chứng chỉ TLS cần khớp **danh tính host/service được connector thực sự xác minh** theo cơ chế TLS/SNI/sidecar/proxy của hệ thống. Nếu certificate chỉ có SAN cho tên logic `catalog-service` nhưng transport trực tiếp kết nối và xác minh hostname `catalog-a.internal.example`, có thể xảy ra lỗi hostname mismatch.

Không “sửa” lỗi đó bằng `trustAll` hoặc tắt hostname verification. Hãy thiết kế certificate SAN, service DNS, sidecar/mTLS hoặc cấu hình SNI phù hợp với đường đi thật và xác minh bằng integration test.

## 8. Metadata định tuyến: whitelist và giới hạn giá trị

Những trường thường được dùng trong routing:

| Metadata | Cách dùng hợp lý | Giới hạn bảo vệ |
|---|---|---|
| `zone` | Ưu tiên instance gần caller | Chỉ nhận zone được nền tảng kiểm soát |
| `region` | Data locality | Kiểm tra data residency và authorization độc lập |
| `version` | Canary/blue-green | Version từ rollout controller được ủy quyền |
| `weight` | Phân phối lưu lượng có trọng số | Giá trị số trong khoảng được phép, không chấp nhận vô hạn |
| `protocol` | Chọn HTTP/TLS policy | Không cho metadata tự hạ cấp bảo mật |
| `tenant` | Có thể là hint ở kiến trúc chuyên biệt | Không dùng làm bằng chứng phân quyền tenant |

Một hàm kiểm tra dữ liệu đơn giản có thể giới hạn weight trước khi đưa vào thuật toán tùy biến:

~~~java
import java.util.Set;

final class RoutingMetadataPolicy {

    private static final Set<String> ALLOWED_ZONES =
        Set.of("zone-a", "zone-b");

    static boolean acceptable(String zone, String rawWeight) {
        if (zone == null || !ALLOWED_ZONES.contains(zone)) {
            return false;
        }

        try {
            int weight = Integer.parseInt(rawWeight);
            return weight >= 1 && weight <= 100;
        } catch (NumberFormatException ex) {
            return false;
        }
    }
}
~~~

Hàm trên **chỉ kiểm tra cấu trúc giá trị**, không xác thực ai đã cung cấp `zone`/`weight`. Kể cả giá trị hợp lệ, nếu attacker được quyền sửa registry họ vẫn có thể chọn `weight=100`. Vì vậy cần kết hợp **nguồn đáng tin, quyền sửa có giới hạn và chính sách định tuyến độc lập**.

Không đưa raw metadata vào log hay nhãn metric nếu không có giới hạn độ dài, encoding và cardinality. Một giá trị version tùy ý dài hàng nghìn ký tự có thể làm log khó đọc, tăng chi phí quan sát hoặc gây lỗi ở bộ xử lý tự viết.

## 9. Health check không thay thế xác minh danh tính

Health check trả HTTP `200` chỉ cho biết **endpoint phản hồi đúng điều kiện probe**, không chứng minh endpoint thuộc đúng dịch vụ.

Một instance giả mạo có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"UP"}
~~~

Nếu registry đã bị đầu độc, `HealthCheckServiceInstanceListSupplier` có thể coi endpoint giả là khỏe, tùy cấu hình probe. Vì vậy:

- **Kiểm tra nguồn danh sách** trước khi coi một instance là ứng viên.
- Dùng **TLS/mTLS identity** cho kết nối tới instance.
- Hạn chế network access tới health endpoint nếu có thể.
- Kiểm soát response/policy từ health check: nó là tín hiệu **availability**, không phải **authentication**.
- Không thực hiện fallback từ “không có instance đáng tin” sang “mọi instance” chỉ để giữ tỷ lệ thành công.

Một số health supplier có chính sách dự phòng khi không có instance healthy; cơ chế đó phục vụ availability. **Danh sách bị policy bảo mật từ chối phải fail closed**, không được lẫn với fallback của health check.

## 10. Cache và nguy cơ giữ dữ liệu định tuyến đã bị thu hồi

Caching instance lists giúp giảm áp lực lên registry nhưng tạo khoảng trễ giữa việc xóa record và việc client ngừng sử dụng nó.

~~~mermaid
sequenceDiagram
    participant Admin as Control plane
    participant Reg as Registry
    participant Cache as Instance list cache
    participant LB as LoadBalancer
    participant Net as Network egress control

    Reg-->>Cache: Cache [A, B]
    Admin->>Reg: Thu hồi B vì không còn tin cậy
    Reg-->>Admin: Đã xóa B
    LB->>Cache: Lấy danh sách trước khi TTL hết
    Cache-->>LB: [A, B] (stale)
    LB->>Net: Thử kết nối tới B
    Net--xLB: Policy chặn B nếu đã thu hồi ở mạng
    Note over Cache: Cache sẽ cập nhật theo lifecycle đã cấu hình
~~~

**TTL của instance cache không phải thời hạn thu hồi quyền truy cập chắc chắn**. Nó còn chịu tác động của nhiều tầng cache/discovery, cơ chế push/watch, polling và cách supplier xếp thứ tự.

Nếu phải thu hồi khẩn cấp một instance vì bị chiếm quyền, nên dùng **biện pháp độc lập với cache** như network egress policy, revoke certificate/identity hoặc đóng quyền tại backend. Cũng cần cơ chế làm mới/invalidate danh sách để client ngừng thử chọn đích cũ.

Không sửa thời gian cache một cách cảm tính mà bỏ qua toàn bộ đường truyền và quyền truy cập. Cache TTL quá thấp có thể làm quá tải registry; TTL quá cao có thể kéo dài việc chọn instance đã thay đổi.

## 11. Đặt kiểm tra ở đâu trong supplier chain?

Một chuỗi logic thường có:

~~~text
Discovery source
    → service instance list
    → [zone / version / health / caching theo cấu hình]
    → LoadBalancer chọn đích
    → HTTP client kết nối
~~~

Thứ tự cụ thể phụ thuộc `ServiceInstanceListSupplier` builder và các lớp đang bật; không có một thứ tự phổ quát cho mọi ứng dụng.

Các điểm kiểm soát bảo mật nên được phân lớp:

1. **Control plane/registry:** chặn đăng ký dữ liệu trái phép, mạnh nhất để bảo vệ nguồn.
2. **Supplier/filter:** loại instance không đáp ứng danh tính/phạm vi/quy tắc endpoint trước khi chọn.
3. **Ngay tại biên gửi request / network:** chặn kết nối ra ngoài tập đích được phép, kể cả khi cache hoặc supplier sai.
4. **TLS + authorization ở backend:** từ chối caller không có danh tính/quyền phù hợp.

Nếu bộ lọc bảo mật nằm trước một cache có thể chứa dữ liệu được phép từ thời điểm cũ, phải hiểu việc **thu hồi** có được phản ánh kịp không. Khi cần bảo đảm nghiêm ngặt, kiểm tra phải được áp dụng lại ở điểm quyết định cuối hoặc có network policy độc lập.

**Fail closed:** nếu không có instance đạt yêu cầu, trả danh sách rỗng/không chọn đích và để caller xử lý lỗi rõ ràng. Không “cứ thử một host bất kỳ” khi dữ liệu thiếu bằng chứng tin cậy.

## 12. Ví dụ thực hành: chỉ cho LoadBalancer chọn instance được phép

Lab dùng `SimpleDiscoveryClient` để mô phỏng một danh sách có **hai instance hợp lệ** và **một instance ngoài danh sách**. Các địa chỉ đều là `localhost`, không dùng IP/host ngoài môi trường thử nghiệm.

| Instance | Cổng | Vai trò |
|---|---:|---|
| `catalog-a` | 18081 | Hợp lệ |
| `catalog-b` | 18082 | Hợp lệ |
| `catalog-extra` | 18083 | Giả lập record bị thêm trái phép |

Ví dụ `application.yml` ở caller:

~~~yaml
server:
  port: 18090

spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
              - uri: http://localhost:18083
~~~

Trong lab, sử dụng HTTP để đơn giản hóa việc chạy cục bộ và tập trung vào **policy chọn instance**. **Production không được sao chép policy cho phép HTTP loopback này**: cần HTTPS/mTLS, trusted identity, egress restriction và endpoint policy phù hợp.

### 12.1. Tạo service thử nghiệm có thể phân biệt instance

Trên backend dùng Spring Boot Web MVC:

~~~java
package demo.catalog;

import java.util.Map;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CatalogWhoAmIController {

    private final String instanceId;

    CatalogWhoAmIController(Environment environment) {
        this.instanceId = environment.getProperty(
            "instance.id", "catalog-unknown");
    }

    @GetMapping("/api/whoami")
    Map<String, String> whoami() {
        return Map.of("instanceId", instanceId);
    }
}
~~~

Cần có `@SpringBootApplication` và dependency Spring Web trong ứng dụng backend. Giả sử đã đóng gói thành `catalog-service.jar`, chạy ba tiến trình riêng:

~~~bash
java -jar catalog-service.jar --server.port=18081 --instance.id=catalog-a
java -jar catalog-service.jar --server.port=18082 --instance.id=catalog-b
java -jar catalog-service.jar --server.port=18083 --instance.id=catalog-extra
~~~

Trước hết kiểm tra cả ba instance trả `200` cho `/api/whoami` khi gọi trực tiếp. Nếu chúng cùng trả response hợp lệ, health check đơn thuần sẽ không phân biệt được instance ngoài policy.

### 12.2. Gắn cấu hình supplier riêng cho service ID

Trong caller, đặt một cấu hình riêng cho `catalog-service`:

~~~java
package demo.caller;

import demo.lbconfig.CatalogSecurityLbConfig;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
    name = "catalog-service",
    configuration = CatalogSecurityLbConfig.class
)
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Lớp `CatalogSecurityLbConfig` nằm ngoài package tree được `@SpringBootApplication` component-scan mặc định để tránh vô tình đăng ký supplier chuyên biệt vào toàn bộ application context. `@LoadBalancerClient` nạp nó vào context LoadBalancer của đúng service ID.

### 12.3. Supplier lọc bằng allowlist cho lab

~~~java
package demo.lbconfig;

import java.util.List;
import java.util.Set;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;

@Configuration(proxyBeanMethods = false)
public class CatalogSecurityLbConfig {

    private static final String SERVICE_ID = "catalog-service";

    private static final Set<Integer> ALLOWED_LAB_PORTS =
        Set.of(18081, 18082);

    @Bean
    ServiceInstanceListSupplier allowedCatalogInstances(
            DiscoveryClient discoveryClient) {

        return new ServiceInstanceListSupplier() {
            @Override
            public String getServiceId() {
                return SERVICE_ID;
            }

            @Override
            public Flux<List<ServiceInstance>> get() {
                return Flux.defer(() -> {
                    List<ServiceInstance> allowed =
                        discoveryClient.getInstances(SERVICE_ID)
                            .stream()
                            .filter(CatalogSecurityLbConfig::isAllowedLab)
                            .toList();

                    return Flux.just(allowed);
                });
            }
        };
    }

    private static boolean isAllowedLab(ServiceInstance instance) {
        if (instance == null || instance.getUri() == null) {
            return false;
        }

        return SERVICE_ID.equals(instance.getServiceId())
            && "localhost".equalsIgnoreCase(instance.getHost())
            && ALLOWED_LAB_PORTS.contains(instance.getPort())
            && !instance.isSecure()
            && "http".equalsIgnoreCase(
                instance.getUri().getScheme());
    }
}
~~~

Đây là **chính sách kiểm tra cố định dành riêng cho lab**. Khi discovery trả ba bản sao, supplier chỉ đưa A/B vào danh sách. Khi không bản sao nào khớp, supplier trả **danh sách rỗng**, không quay lại danh sách gốc.

**Cảnh báo kỹ thuật quan trọng:**

- Ví dụ này **thay thế supplier mặc định** cho `catalog-service` và **không tự kết hợp caching, health check hoặc zone filter**. Khi chuyển sang production, phải thiết kế/decorate supplier chain phù hợp, giữ các chức năng hiện có và kiểm tra thứ tự xử lý.
- `DiscoveryClient.getInstances(...)` là API đồng bộ. Trong lab với `SimpleDiscoveryClient` in-memory nó trả ngay; với remote discovery có thể chặn thread. Trong pipeline reactive production, ưu tiên supplier/discovery phù hợp thay vì gọi nguồn blocking trên event-loop.
- Host/port allowlist cố định phù hợp để **chứng minh việc lọc**, không phù hợp cho autoscaling động. Production nên dựa trên **workload identity, policy control plane và network egress**; chỉ kiểm tra hậu tố DNS hoặc so chuỗi host không đủ chống DNS rebinding/đích giả.
- `getUri()` và `isSecure()` đều đọc từ `ServiceInstance` do nguồn cung cấp. Kiểm tra hai giá trị có nhất quán chỉ là validation cơ bản; nó **không xác thực nguồn gốc hoặc TLS peer**.
- Nếu security policy bị bỏ qua ở những HTTP clients khác, ví dụ một `RestClient.create()` tự tạo hoặc một proxy gọi URL trực tiếp, filter của LoadBalancer sẽ không bảo vệ những đường đi đó. Network egress policy là lớp kiểm soát độc lập cần có.

### 12.4. Tạo RestClient có LoadBalancer

~~~java
package demo.caller;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class ClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient catalogRestClient(
            @Qualifier("loadBalancedBuilder")
            RestClient.Builder builder) {

        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

Một endpoint kiểm chứng:

~~~java
package demo.caller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
class LabController {

    private final RestClient client;

    LabController(RestClient catalogRestClient) {
        this.client = catalogRestClient;
    }

    @GetMapping("/demo/whoami")
    String whoami() {
        return client.get()
            .uri("/api/whoami")
            .retrieve()
            .body(String.class);
    }
}
~~~

Khi gọi nhiều lần:

~~~bash
for i in $(seq 1 20); do
  curl -s http://localhost:18090/demo/whoami
  echo
done
~~~

Kỳ vọng khi cấu hình đã có hiệu lực: chỉ nhìn thấy `catalog-a` và `catalog-b`, **không thấy `catalog-extra`**. Đây là kết quả kiểm chứng chính sách đầu vào tại supplier cho lab; để kết luận bảo mật production cần thêm chứng cứ TLS identity, RBAC và network policy.

## 13. Nếu metadata bị sửa thì xử lý thế nào?

Trong production, metadata có thể được cập nhật mà host/port vẫn không đổi. Ví dụ một instance đổi `zone=zone-b` sang `zone=zone-a`, hoặc chuyển `weight` từ 10 lên 100.

Các biện pháp:

1. **Chỉ người/automation được cấp quyền** mới có thể thay đổi routing metadata.
2. **Validate schema**: key được hỗ trợ, giá trị hợp lệ, độ dài và kiểu dữ liệu.
3. **Giới hạn tác động**: weight không vượt ngưỡng, canary tỷ lệ nhỏ có approval; các quy tắc này không nên do cùng metadata tự quyết định.
4. **Tách authorization khỏi hint**: `tenant=abc` không chứng minh workload được quyền xử lý dữ liệu tenant abc.
5. **Quan sát thay đổi**: báo khi số lượng instance, zone distribution hoặc weight thay đổi bất thường.
6. **Thu hồi nhanh**: có cách vô hiệu hóa instance ngoài cache khi phát hiện bị xâm phạm.

Một ví dụ cấu hình tùy biến có thể chỉ cho phép `zone-a` và `zone-b`; mọi giá trị khác bị loại hoặc dẫn tới cảnh báo theo policy. Nhưng metadata có `zone-a` cũng không chứng minh instance thật sự nằm ở zone-a nếu nguồn bị xâm phạm.

### Trường hợp weight=0 hoặc rất lớn

Khi sử dụng weighted supplier hoặc thuật toán tùy chỉnh:

- Phải định nghĩa rõ `weight=0` nghĩa là gì, có được chấp nhận không.
- Không parse weight bằng số nguyên không có giới hạn rồi nhân/chia mà không kiểm tra overflow.
- Không cho một instance tự sửa weight của mình để chiếm toàn bộ lưu lượng nếu không có authority.
- Không tin giá trị weight do request headers của người dùng gửi lên, trừ khi đã có authorization và mapping rõ ràng.

Cách Spring Cloud LoadBalancer dùng metadata trọng số phụ thuộc phiên bản và supplier/chính sách được bật; **không phải mọi `ServiceInstance.metadata["weight"]` đều tự động làm đổi Round Robin**.

## 14. Bảo vệ Authorization header và token theo đích đã chọn

Một caller có thể gửi Bearer token hoặc thông tin xác thực service-to-service. Nếu danh sách instance bị thay đổi để chuyển request đến đích không tin cậy, token có nguy cơ bị lộ.

Nguyên tắc:

- **Không sao chép `Authorization` vô điều kiện** sang mọi downstream.
- Token cần có **audience và scope** đúng cho dịch vụ nhận, thời hạn ngắn và cơ chế rotation.
- Kiểm soát đường đi qua trusted proxy/sidecar và mTLS khi phù hợp.
- Chỉ attach token sau khi xác định service đích và policy cho phép, không dựa trên host do user input quyết định.
- Không đưa token vào URL, discovery metadata, log hoặc metrics.
- Backend phải **tự xác thực và phân quyền** thay vì tin rằng request tới được mình thì chắc chắn hợp lệ.

~~~mermaid
flowchart TD
    A["Caller muốn gọi catalog-service"] --> B["Xác định service ID theo API contract"]
    B --> C["Discovery từ nguồn có quyền truy cập"]
    C --> D["Policy lọc instance đáng tin"]
    D --> E{"Có đích được phép?"}
    E -->|Không| F["Fail closed / ghi nhận cảnh báo"]
    E -->|Có| G["TLS/mTLS identity verification + egress"]
    G --> H["Gửi credential đúng audience"]
    H --> I["Backend xác thực và authorize operation"]
~~~

Dùng OAuth2/OIDC hay service account token như thế nào tùy môi trường. Không có quy tắc “mọi request nội bộ đều dùng cùng token”; token propagation không đúng audience còn có thể tạo lỗi **confused deputy**, khi một service dùng quyền của chính nó để truy cập tài nguyên không được phép thay cho caller.

## 15. Đừng dùng metadata làm secret store

Không đưa các giá trị sau vào `ServiceInstance.getMetadata()`:

- Mật khẩu database hoặc Redis.
- API key, access token, refresh token.
- Private key hoặc client certificate.
- Session cookie, authorization header.
- Khóa mã hóa, webhook secret hoặc thông tin người dùng nhạy cảm.

Metadata thường được phân phối rộng hơn secret store: nhiều caller có thể đọc discovery để định tuyến, log có thể in toàn bộ metadata, và tooling vận hành có thể lưu snapshot của registry.

Nếu một service cần credentials, lấy từ secret manager hoặc identity provider dành riêng cho nó, với scope, rotation và audit. Metadata chỉ nên chứa **routing descriptors không nhạy cảm** và đã được kiểm soát quyền ghi.

## 16. Ghi log metadata an toàn và tránh metric cardinality

Khi debug, nhiều đội có xu hướng:

~~~java
// Không khuyến khích ghi toàn bộ metadata không kiểm soát:
log.info("Selected instance metadata: {}", instance.getMetadata());
~~~

Rủi ro:

- Metadata có thể chứa dữ liệu nhạy cảm do cấu hình sai.
- Chuỗi có newline/control characters có thể làm nhiễu log hoặc gây log injection.
- Giá trị động như request ID hoặc endpoint URL dài tạo cardinality lớn.
- Log có thể trở thành nguồn thứ cấp phát tán dữ liệu bị đánh cắp.

Thay vào đó, log các trường **đã được cho phép và chuẩn hóa**, ví dụ:

~~~java
String zone = instance.getMetadata().get("zone");
String safeZone =
    ("zone-a".equals(zone) || "zone-b".equals(zone))
        ? zone
        : "unknown";

log.info(
    "Selected serviceId={}, instanceId={}, zone={}",
    instance.getServiceId(),
    instance.getInstanceId(),
    safeZone
);
~~~

Ví dụ giả định đã có logger `log`. Trước khi dùng production, cũng cần xem `instanceId` có chứa dữ liệu bất thường không và giới hạn độ dài/ký tự phù hợp. Không tạo Prometheus label từ một giá trị `instanceId`/`version` tùy ý không kiểm soát.

## 17. Phát hiện registry poisoning và thay đổi bất thường

Các tín hiệu có ích:

| Metric / audit event | Dấu hiệu |
|---|---|
| Instance count theo service ID | Tăng/giảm bất thường |
| Số instance bị policy loại | Có record không đáp ứng trust rules |
| Thay đổi host/port/scheme | Endpoint có thể đã bị thay đổi trái phép |
| Zone/version/weight distribution | Routing metadata bị biến động lớn |
| Registry write/delete events | Ai sửa entry, vào lúc nào, từ pipeline nào |
| TLS handshake failures | Sai identity/certificate hoặc cấu hình |
| Network egress denies | Caller cố kết nối tới đích ngoài phạm vi cho phép |
| Service ID lookup failures | Đổi tên, thiếu permission hoặc nguồn discovery lỗi |
| Cache age/refresh failures | Dữ liệu cũ tồn tại lâu |
| Health state transitions | Flapping hoặc probe bị thao túng |
| Selected instance and actual peer | Đối chiếu quyết định routing với kết nối thực |

Không tự nhận rằng các metric này đều được Spring Cloud LoadBalancer phát ra mặc định. Nhiều tín hiệu cần lấy từ registry audit, Kubernetes audit logs, HTTP connector, network policy logs, application instrumentation hoặc tracing.

Khi một record bất thường xuất hiện, nên có quy trình cô lập: xác minh chủ sở hữu, thu hồi quyền ghi, loại entry khỏi nguồn, thu hồi credential/certificate liên quan, chặn egress nếu cần, invalidate cache và kiểm tra log các request đã đi tới đích đó.

## 18. Thứ tự ưu tiên khi có sự cố an ninh

Một quy trình ứng phó có thể là:

1. **Phân loại rủi ro:** metadata sai thuần vận hành hay địa chỉ chuyển traffic tới đích không được phép?
2. **Chặn đường truyền nguy hiểm:** network policy/egress deny, revoke mTLS identity hoặc key nếu có dấu hiệu bị chiếm quyền.
3. **Khóa quyền sửa nguồn:** thu hẹp RBAC/ACL, thu hồi token quản trị hoặc account bị lộ.
4. **Làm sạch registry/config:** xóa record hoặc khôi phục metadata được phê duyệt.
5. **Đồng bộ client:** refresh discovery/cache, xác minh tập instance sau supplier.
6. **Đối soát tác động:** kiểm tra traces/request logs xem request nào đã gửi tới đích bị nghi ngờ.
7. **Luân chuyển secrets:** nếu token có khả năng bị gửi tới đích không tin cậy, thực hiện rotation/revocation phù hợp.
8. **Bổ sung guardrails:** policy admission, audit, canary kiểm soát và test regression.

**Xóa record khỏi registry không có nghĩa mọi caller ngay lập tức ngừng kết nối**; còn cache, in-flight requests và connection pools. Vì vậy các biện pháp chặn ở network/identity quan trọng khi cần thu hồi khẩn cấp.

## 19. Kiểm thử bảo mật cho ServiceInstanceListSupplier

Một bộ test nên phân biệt **validation**, **authorization**, **transport identity** và **behavior khi mất ứng viên**.

| Tình huống | Kiểm tra | Kỳ vọng |
|---|---|---|
| Hai instance hợp lệ | Discovery trả A/B | Có thể chọn A/B |
| Thêm instance `catalog-extra` | Cổng 18083 không thuộc allowlist | Không thấy catalog-extra qua caller |
| Sửa port của A | A chuyển sang cổng ngoài policy | A bị lọc |
| Sửa service ID | Record không còn khớp `catalog-service` | Bị loại |
| Tất cả bản sao không hợp lệ | Supplier không còn ứng viên | **Fail closed**, không gửi request đến đích lạ |
| Metadata weight không hợp lệ | Parsing/validation | Reject/quarantine theo policy |
| Metadata zone giả | Registry cho phép ghi sai | Phát hiện bằng authority/policy, không chỉ schema |
| Registry credential thiếu quyền | Discovery không đọc được | Error được phân loại, không dùng fallback tùy ý |
| Registry có TLS nhưng sai cert | Handshake/xác minh danh tính | Từ chối kết nối |
| Instance trả health 200 nhưng identity sai | Health riêng vẫn pass | Transport/authentication từ chối |
| Cache còn record vừa bị thu hồi | TTL chưa hết | Egress policy vẫn chặn đích |
| Retry chuyển instance | Attempt chọn đích khác | Mọi attempt đều đi qua policy |
| RestClient/WebClient/Feign khác cấu hình | Một client bypass LoadBalancer | Test phát hiện và loại bỏ đường bypass |
| Request có Bearer token | Instance giả bị đăng ký | Token không được gửi tới đích ngoài phạm vi |
| Metadata có newline/secret | Logging/metrics | Sanitized, không lộ giá trị thô |

Trong lab phần 12, bạn có thể quan sát response body `instanceId`. Nếu cần kiểm chứng mạnh hơn, dùng integration test với stub server trên từng port và đếm số request thực sự tới `18083`; chỉ nhìn một vài response không phải bằng chứng tuyệt đối rằng đích ngoài policy chưa từng được chọn.

### Một phép thử phụ: khi allowlist rỗng

Thay `ALLOWED_LAB_PORTS` thành một set không chứa cổng nào trong môi trường test, rồi gọi qua caller. Mong đợi không có HTTP request tới cả ba backend. Kiểu lỗi/cách HTTP server caller phản hồi phụ thuộc client và error mapping, nên không hardcode một exception class duy nhất trong test nếu thư viện khác phiên bản.

**Không** thêm nhánh “nếu danh sách an toàn rỗng thì trả về danh sách chưa lọc”. Với trust policy, đó là việc mở lại đường đến các đích vừa bị coi là không đáng tin.

## 20. Những lỗi thiết kế thường gặp

1. **Tin `serviceId` hoặc `trusted=true` trong metadata như bằng chứng identity.**
2. **Cho mọi workload quyền ghi/xóa instance của service khác trong registry.**
3. **Tắt TLS hostname verification** vì certificate không khớp host thực được LoadBalancer chọn.
4. **Chỉ bật health check rồi coi mọi instance 200 là đáng tin.**
5. **Cho metadata từ request/header bên ngoài tự chọn zone, weight hoặc target host** mà không kiểm tra quyền.
6. **Nhét token/secret vào metadata** vì tiện đọc ở caller.
7. **Dùng allowlist host suffix không kiểm tra DNS, IP hoặc egress**, dễ bị đánh lừa bởi cấu hình bất thường.
8. **Chỉ lọc ở một supplier nhưng để HTTP client khác gọi trực tiếp**, bỏ qua policy.
9. **Cho fallback từ danh sách đã bị security reject sang toàn bộ instance gốc.**
10. **Coi TTL cache là biện pháp thu hồi quyền bảo mật đủ nhanh.**
11. **Không audit thay đổi registry/config map**, khiến khó truy nguyên routing hijack.
12. **Dùng weight/zone/version không giới hạn và không xác thực nguồn sửa.**
13. **Ghi mọi metadata vào log hoặc metrics**, gây rò thông tin/cardinality.
14. **Tưởng chứng chỉ TLS của discovery tự chứng minh danh tính mọi backend.**
15. **Sử dụng chung token quá quyền rộng** cho các downstream có mức tin cậy khác nhau.
16. **Cố định host/port allowlist của lab cho production autoscaling**, làm hỏng discovery và không chứng minh identity.
17. **Thêm security filter nhưng quên preserve caching/health chain**, khiến hành vi availability thay đổi ngoài dự kiến.
18. **Giảm kiểm tra khi không có instance phù hợp** chỉ để tránh lỗi không có server.
19. **Không theo dõi selectedInstance so với actual peer** khi điều tra lỗi chuyển hướng.
20. **Không phân biệt lỗi security policy với lỗi discovery/transport** trong observability.

## 21. Checklist triển khai an toàn

Trước khi đưa một client-side LoadBalancer vào production, hãy trả lời:

- Ai có thể **đăng ký/sửa/xóa** record của từng service ID?
- Có RBAC/ACL, audit log và quy trình phê duyệt metadata routing không?
- Discovery client có dùng **kênh xác thực và mã hóa** phù hợp không?
- Các **host/port/scheme** có được giới hạn bởi policy độc lập với metadata tự khai không?
- HTTP connector có **xác minh TLS peer identity** với SAN/SNI đúng tuyến kết nối không?
- Caller có **network egress policy** để không thể truy cập đích ngoài phạm vi không?
- `ServiceInstance` nào bị loại do policy, và điều gì xảy ra khi danh sách sau lọc rỗng?
- Có lỗ hổng bypass qua `RestClient.create()`, WebClient không `@LoadBalanced` hoặc Feign có `url` cố định không?
- Các trường `zone`, `weight`, `version` có nguồn và người sở hữu đáng tin không?
- Metadata có được validate type, range, length và logging safety không?
- Health check có được coi đúng là **availability**, không phải authentication, không?
- Caching và TTL có tương thích với nhu cầu thu hồi khẩn cấp không?
- Token có audience/scope đúng downstream và không bị forward vô điều kiện không?
- Backend có authorize operation độc lập với việc request đến được hay không?
- Có telemetry/audit để điều tra instance giả, stale cache, unauthorized writes và TLS failures không?
- Có test với instance không được phép, sai scheme, registry thiếu quyền và policy fail-closed không?
- Khi metadata đổi đột ngột, có cảnh báo và quy trình khôi phục/rollback không?

## 22. Kết luận

**Danh sách `ServiceInstance` và metadata định tuyến là dữ liệu điều khiển có ảnh hưởng bảo mật.** Một thay đổi trái phép ở **service registry, config source hoặc supplier chain** có thể dẫn request đến host/port sai, thao túng zone/weight và làm lộ credentials. Chỉ dùng HTTPS cho API nghiệp vụ hoặc chỉ bật health check **không đủ** để chứng minh nguồn danh sách đáng tin.

Trong Spring Cloud LoadBalancer, hãy bảo vệ từng ranh giới: **RBAC/ACL và audit ở nguồn discovery; validation/fail-closed ở supplier; egress restriction và TLS/mTLS identity ở transport; authorization ở service đích**. Với RestClient, WebClient và OpenFeign, cần nhất quán để mọi lời gọi theo service ID đi qua chính sách đã định, và vẫn có lớp bảo vệ mạng độc lập khi một client cấu hình sai.

Nguyên tắc vận hành là **kiểm soát ai được phép thay đổi metadata, hiểu chúng có thể tác động đến routing như thế nào, và chứng minh được đích đã chọn thực sự được ủy quyền**. Khi kết hợp những lớp đó với cache/health check, retry/timeout có giới hạn và observability, hệ thống có thể giao tiếp liên dịch vụ ổn định mà không biến metadata hoặc discovery thành một đường vòng vượt qua kiểm soát bảo mật.

