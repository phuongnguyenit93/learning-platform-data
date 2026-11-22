# Phối hợp load balancing với cơ chế khám phá service

## 1. Discovery tìm instance, load balancer chọn instance

Trong **SPRING_GRPC**, client gọi service bằng gRPC Java và các stub được sinh từ hợp đồng Protocol Buffers. Khi service chạy trên nhiều instance, client cần biết instance nào đang tồn tại và instance nào có thể nhận traffic. **Service discovery** cung cấp danh sách instance; **load balancing** chọn một instance trong danh sách đó cho từng RPC mới.

Hai trách nhiệm này nối tiếp nhau:

- **Service discovery:** tìm và cập nhật địa chỉ của các instance thuộc một service logic.
- **Name resolver:** chuyển kết quả discovery thành endpoint mà gRPC channel hiểu.
- **Load balancing policy:** dùng endpoint và trạng thái subchannel để chọn backend cho RPC.
- **Subchannel/transport:** thiết lập và duy trì kết nối đến backend đã chọn.

Ví dụ service `orders` có ba replica:

~~~text
Service registry / control plane
  orders -> [A, B, C]
              |
              v
        gRPC NameResolver
              |
              v
      ManagedChannel + policy
         /       |       \
    subchannel A B       C
        |       |        |
      server A server B server C
~~~

Registry không tự quyết định RPC tiếp theo đến A hay B. Nó cung cấp danh sách instance. Resolver đưa danh sách vào channel; picker của load balancer mới chọn subchannel.

## 2. Luồng từ đăng ký instance đến RPC

Một vòng đời điển hình có các bước:

1. Instance khởi động và tạo gRPC server.
2. Instance hoàn tất khởi tạo dependency bắt buộc và chuyển sang trạng thái sẵn sàng.
3. Instance đăng ký service name, host, port và metadata cần thiết vào registry.
4. Client resolver nhận danh sách endpoint từ registry hoặc DNS.
5. Resolver gửi danh sách mới đến `ManagedChannel`.
6. Load balancing policy tạo/cập nhật subchannel và chọn backend cho RPC mới.
7. Khi instance dừng hoặc không còn sẵn sàng, registry/resolver cập nhật danh sách để policy ngừng chọn instance đó.

~~~mermaid
sequenceDiagram
    participant S as Server instance
    participant R as Service registry
    participant N as NameResolver
    participant C as ManagedChannel
    participant P as Load balancer
    S->>S: Khởi tạo service và dependency
    S->>R: Register khi đã ready
    N->>R: Watch/query service endpoints
    R-->>N: Danh sách instance
    N-->>C: ResolutionResult
    C->>P: Cập nhật endpoint/subchannel
    Note over P: Picker chọn backend cho RPC mới
    S->>R: Deregister khi drain/shutdown
    R-->>N: Danh sách endpoint mới
    N-->>C: ResolutionResult cập nhật
    C->>P: Loại endpoint khỏi lựa chọn mới
~~~

Đăng ký quá sớm có thể khiến client gửi RPC đến instance đã mở port nhưng chưa tải xong cấu hình hoặc chưa kết nối được database. Deregister quá muộn có thể khiến client tiếp tục chọn instance đang dừng. Thời điểm register/deregister phải gắn với readiness và graceful shutdown.

## 3. Các kiểu service discovery thường gặp

| Cơ chế | Nguồn endpoint | Cách client nhận cập nhật |
|---|---|---|
| DNS | Bản ghi A/AAAA hoặc record của service | DNS resolver refresh theo cơ chế và cache của runtime |
| Registry như Consul/Eureka | Danh sách instance được đăng ký | Poll, watch hoặc adapter của registry |
| Kubernetes Service | ClusterIP hoặc pod IP tùy loại Service | DNS, API/control plane hoặc proxy của cluster |
| xDS/control plane | Endpoint và cấu hình routing do control plane phân phối | Giao thức xDS, thường qua ADS/EDS và service config liên quan |
| Static resolver | Danh sách cấu hình cố định | Chỉ thay đổi khi cấu hình/channel được cập nhật |

Không phải mọi cơ chế đều tự tích hợp vào gRPC Java. DNS resolver có sẵn xử lý DNS target. Với Consul, Eureka hoặc registry riêng, ứng dụng thường cần custom `NameResolverProvider`, adapter tương thích hoặc dùng xDS integration. Spring Cloud `DiscoveryClient` có thể cung cấp danh sách instance cho adapter, nhưng tự nó không biến một `ManagedChannel` bất kỳ thành client gRPC có discovery.

## 4. Gắn registry với gRPC NameResolver

gRPC Java dùng `NameResolver` để chuyển target thành các địa chỉ transport. Với registry riêng, có thể triển khai `NameResolverProvider` cho một scheme, ví dụ `consul`, rồi tạo target:

~~~java
ManagedChannel channel = ManagedChannelBuilder
        .forTarget("consul:///orders")
        .defaultLoadBalancingPolicy("round_robin")
        .useTransportSecurity()
        .build();
~~~

Target `consul:///orders` chỉ hoạt động khi ứng dụng đã đăng ký custom provider xử lý scheme `consul`. Nó không phải scheme có sẵn trong mọi gRPC Java runtime.

Trong resolver, danh sách instance được chuyển thành `EquivalentAddressGroup`. Phần cốt lõi của việc công bố kết quả có dạng:

~~~java
import io.grpc.Attributes;
import io.grpc.EquivalentAddressGroup;
import io.grpc.NameResolver;

import java.util.List;

void publishEndpoints(
        NameResolver.Listener2 listener,
        List<EquivalentAddressGroup> addresses) {

    NameResolver.ResolutionResult result =
            NameResolver.ResolutionResult.newBuilder()
                    .setAddresses(addresses)
                    .setAttributes(Attributes.EMPTY)
                    .build();

    listener.onResult(result);
}
~~~

Đây là phần minh họa của custom resolver; việc tạo `InetSocketAddress`, ánh xạ metadata và quản lý listener thuộc implementation cụ thể. Resolver phải gửi cập nhật khi registry thay đổi, không chỉ đọc registry một lần lúc tạo channel.

Nếu registry không có endpoint hợp lệ, resolver cần biểu diễn trạng thái rỗng hoặc báo lỗi resolution theo hợp đồng của implementation. Không âm thầm giữ endpoint đã bị thu hồi vô thời hạn nếu việc đó có thể gửi traffic đến instance không còn an toàn. Nếu dùng last-known-good endpoint để chịu lỗi registry, phải có TTL, giới hạn thời gian và metrics rõ ràng.

## 5. Tích hợp Spring DiscoveryClient

Với ứng dụng dùng Spring Cloud, `DiscoveryClient` có thể trả danh sách instance theo service ID:

~~~java
List<ServiceInstance> instances =
        discoveryClient.getInstances("orders");
~~~

Một adapter custom có thể:

1. Nhận `ServiceInstance` từ discovery client.
2. Lấy host/port và các metadata được cho phép.
3. Kiểm tra trạng thái hoặc thuộc tính readiness theo nguồn discovery.
4. Chuyển mỗi instance thành `EquivalentAddressGroup`.
5. Gửi `ResolutionResult` đến listener của gRPC.

`getInstances("orders")` chỉ là truy vấn danh sách tại thời điểm gọi. Để channel cập nhật khi topology đổi, adapter cần cơ chế refresh: registry watch/event nếu có, hoặc polling có chu kỳ và backoff. Không gọi `getInstances` cho mỗi RPC; việc đó tạo tải không cần thiết lên registry và làm tăng latency.

Trong Spring, custom resolver/provider và `ManagedChannel` có thể được quản lý như bean. Tuy nhiên, cách đăng ký provider và lifecycle bean cần khớp với starter Spring gRPC/Spring Cloud cụ thể của dự án. Không có một property chuẩn chung cho mọi starter để tự nối mọi registry vào mọi gRPC channel.

## 6. Resolver và load balancing policy phối hợp ra sao?

Resolver cung cấp danh sách endpoint. Policy quyết định cách sử dụng danh sách:

| Discovery trả về | Policy | Kết quả |
|---|---|---|
| Một endpoint | `pick_first` | RPC mới dùng endpoint duy nhất khi ready |
| Nhiều endpoint | `pick_first` | Ưu tiên một subchannel hoạt động; thử endpoint khác khi cần |
| Nhiều endpoint | `round_robin` | Phân phối RPC mới qua các subchannel `READY` |
| Nhiều endpoint có thuộc tính locality/weight | Policy hỗ trợ thuộc tính đó | Có thể ưu tiên vùng hoặc trọng số nếu provider/control plane hỗ trợ |
| Danh sách rỗng | Bất kỳ policy nào | Không có backend để chọn; RPC có thể chờ hoặc thất bại theo deadline |

Ví dụ service config có thể đặt policy:

~~~json
{
  "loadBalancingConfig": [
    {
      "round_robin": {}
    }
  ]
}
~~~

Service config có thể được resolver cung cấp cùng kết quả resolution hoặc được đặt làm cấu hình mặc định của channel. Cấu hình từ resolver có thể được ưu tiên hơn cấu hình mặc định. Policy provider phải có trong runtime; chỉ ghi tên `round_robin` vào JSON không cài đặt provider đó.

Một registry có thể trả metadata như zone, region hoặc weight. Các metadata này chỉ ảnh hưởng lựa chọn nếu resolver ánh xạ chúng thành attributes mà policy tương ứng hiểu, hoặc control plane chuyển chúng thành cấu hình policy. `round_robin` cơ bản không tự cân bằng theo CPU, latency hay weight tùy ý.

## 7. Client-side discovery và server-side load balancing

Không phải hệ thống nào cũng để gRPC client nhìn thấy từng replica:

| Mô hình | Địa chỉ client nhìn thấy | Nơi chọn backend |
|---|---|---|
| Client-side discovery | Nhiều endpoint riêng | gRPC resolver và load balancing policy |
| Server-side/network LB | Một VIP hoặc hostname của proxy | Network load balancer |
| Sidecar/service mesh | Địa chỉ local proxy hoặc endpoint do xDS cung cấp | Sidecar/proxy hoặc gRPC xDS client |
| Kubernetes ClusterIP | Thường là một virtual IP | Lớp mạng/service proxy của Kubernetes |
| Kubernetes headless Service | Có thể là nhiều pod IP | Client có thể chọn từng pod nếu resolver nhận được danh sách |

Tránh vô tình xếp nhiều lớp load balancing mà không hiểu tác động. Ví dụ client chỉ thấy một ClusterIP thì `round_robin` phía client không thể phân phối trực tiếp qua các pod phía sau IP đó. Ngược lại, nếu client dùng headless Service và `round_robin`, mỗi RPC có thể được gửi trực tiếp đến một pod.

Với service mesh, xác định rõ gRPC client kết nối đến sidecar hay trực tiếp đến endpoint. Proxy có thể đã thực hiện retry, outlier detection, locality hoặc routing; cấu hình thêm ở client có thể tạo retry lồng nhau hoặc phân phối tải khó dự đoán.

## 8. Readiness, health và trạng thái đăng ký

Registry có thể chứa instance đang khởi động hoặc instance đã mất khả năng phục vụ nếu health signal cập nhật chậm. Cần thống nhất cách xác định một instance được phép công bố:

- **Liveness:** tiến trình còn sống; thường phục vụ quyết định restart.
- **Readiness:** instance đã sẵn sàng nhận traffic mới.
- **gRPC health:** service cụ thể đang `SERVING` hay `NOT_SERVING`.
- **Connectivity:** subchannel đã kết nối và ở trạng thái `READY`.

Các tín hiệu này không thay thế nhau. `READY` chỉ phản ánh transport; registry có endpoint cũng không chứng minh service đang `SERVING`.

Một cách phối hợp:

1. Khởi động server và dependency.
2. Chỉ đăng ký instance sau khi readiness đạt.
3. Cập nhật health nếu dependency bắt buộc mất khả năng phục vụ.
4. Khi shutdown, đặt `NOT_SERVING` hoặc readiness false trước khi deregister.
5. Chờ propagation và drain RPC đang chạy trước khi đóng server.

Nếu client dùng gRPC client-side health checking, service phải expose health service và client phải cấu hình theo dõi đúng tên service. Nếu registry đã loại endpoint theo readiness, client có thể không còn nhìn thấy endpoint đó; tránh tạo hai nguồn health mâu thuẫn.

## 9. Cập nhật endpoint, cache và stale discovery

Danh sách instance thay đổi liên tục khi scale out, scale in, rolling deploy hoặc sự cố mạng. Resolver cần nhận và áp dụng cập nhật theo cơ chế phù hợp:

~~~mermaid
sequenceDiagram
    participant D as Discovery registry
    participant N as NameResolver
    participant C as ManagedChannel
    participant L as Load balancer
    D-->>N: [A, B]
    N-->>C: ResolutionResult [A, B]
    C->>L: Tạo/cập nhật subchannel
    Note over D: Instance C được thêm
    D-->>N: [A, B, C]
    N-->>C: ResolutionResult [A, B, C]
    C->>L: Thêm subchannel C
    Note over D: Instance A bắt đầu drain
    D-->>N: [B, C]
    N-->>C: ResolutionResult [B, C]
    C->>L: Loại endpoint khỏi lựa chọn mới
~~~

Các vấn đề cần kiểm soát:

- **TTL/cache:** client có thể tiếp tục thấy endpoint cũ sau khi registry đã thay đổi.
- **Watch bị ngắt:** resolver phải reconnect với backoff và không tạo hàng loạt watcher.
- **Update dồn dập:** coalesce/debounce thay đổi nhanh để tránh tạo/hủy subchannel liên tục.
- **Duplicate endpoint:** chuẩn hóa host/port và loại trùng trước khi công bố.
- **Empty result:** xác định rõ RPC sẽ fail-fast hay wait-for-ready trong deadline.
- **Stale last-known-good:** nếu giữ endpoint cũ khi registry lỗi, phải giới hạn tuổi và có chính sách an toàn.

Không tạo lại `ManagedChannel` mỗi lần registry thay đổi. Resolver gửi `ResolutionResult` mới để channel và policy điều chỉnh subchannel theo lifecycle hiện tại.

## 10. TLS và danh tính service khi địa chỉ thay đổi

Discovery có thể trả IP hoặc hostname khác nhau theo từng instance, nhưng client vẫn phải xác minh danh tính TLS. Ví dụ target là:

~~~text
consul:///orders
~~~

Registry có thể trả `10.60.0.11:9090`, nhưng certificate của backend cần hợp lệ với authority/hostname mà client sử dụng theo cấu hình gRPC. Không tự đổi TLS authority sang IP chỉ vì resolver nhận địa chỉ IP. Nếu các backend dùng certificate khác nhau hoặc nhiều SAN, trust và authority phải được thiết kế nhất quán cho toàn bộ tập endpoint.

Registry cũng là nguồn dữ liệu có ảnh hưởng đến nơi client gửi traffic. Chỉ tin registry/control plane đã xác thực, bảo vệ quyền ghi service registration và giới hạn metadata endpoint. Nếu attacker có thể đăng ký endpoint giả, client có thể bị chuyển hướng đến server không đáng tin cậy.

## 11. Retry, health và discovery cần một chính sách chung

Khi backend lỗi, ba cơ chế có vai trò khác nhau:

| Cơ chế | Trách nhiệm |
|---|---|
| Discovery/resolver | Cập nhật endpoint còn được công bố |
| Health/outlier detection | Đánh giá backend có nên nhận RPC mới |
| Load balancing | Chọn subchannel trong tập endpoint đủ điều kiện |
| Retry | Tạo attempt mới khi status và commitment cho phép |
| Application resume | Tạo RPC mới với cursor/checkpoint để tiếp tục stream |

Nếu resolver vẫn công bố backend A, health checker không loại A và policy `pick_first` vẫn chọn A, retry có thể tiếp tục đến A dù A trả `UNAVAILABLE` ở tầng ứng dụng. Cần quyết định cơ chế nào chịu trách nhiệm ejection và thời gian phục hồi.

Không cấu hình retry đồng thời ở gRPC client, service mesh và application loop mà không tính tổng số attempt. Retry lồng nhau có thể khuếch đại tải và vượt deadline. Với side effect cần idempotency key; với server stream đã commit cần cursor để resume.

## 12. Kiểm thử phối hợp discovery và load balancing

Một test chỉ tạo `ManagedChannel` và một server không chứng minh discovery động. Nên kiểm thử resolver, policy và vòng đời instance:

| Kịch bản | Điều cần xác minh |
|---|---|
| Registry trả A, B, C | Resolver công bố đủ endpoint |
| `round_robin`, các endpoint đều `READY` | RPC mới được phân phối qua nhiều instance |
| Registry thêm D | Resolver cập nhật và policy có thể dùng D sau khi subchannel ready |
| Registry gỡ A | RPC mới ngừng chọn A sau khi update được áp dụng |
| A chưa readiness | A không được công bố hoặc bị health policy loại |
| Watch/registry tạm mất kết nối | Resolver reconnect có backoff; không tạo watcher trùng |
| Registry trả endpoint trùng | Resolver chuẩn hóa và không tạo subchannel trùng |
| Registry trả danh sách rỗng | Hành vi fail-fast/wait-for-ready tuân theo deadline |
| TLS trên endpoint mới | Certificate và authority vẫn được xác minh |
| Rolling shutdown | Deregister/drain không cắt RPC đang chạy ngoài grace period |
| Service config thay đổi | Channel áp dụng policy mới theo hỗ trợ runtime |
| Retry sau khi endpoint lỗi | Attempt mới dùng tập backend đã cập nhật; không vượt giới hạn retry |

Có thể dùng fake registry và custom `NameResolverProvider` để kiểm thử deterministic. Với DNS, Kubernetes, Consul/Eureka hoặc xDS, cần integration test trong môi trường tương ứng vì TTL, cache, watcher, proxy và certificate không được mô phỏng đầy đủ bằng in-process transport.

## 13. Metrics và chẩn đoán

Theo dõi cả discovery và lựa chọn backend:

- Số instance registry trả về theo service.
- Số endpoint resolver công bố và thời điểm mỗi lần cập nhật.
- Độ trễ từ register/deregister đến khi client áp dụng.
- Số subchannel `READY`, `CONNECTING`, `TRANSIENT_FAILURE`.
- Số RPC theo backend, method và status code.
- Số endpoint stale, duplicate hoặc không đạt readiness.
- Thời gian reconnect watcher và số lần registry query lỗi.
- Tỷ lệ retry, deadline và stream reconnect theo backend.

Khi một instance không nhận RPC, kiểm tra lần lượt: registry có đăng ký nó không, resolver có nhận endpoint không, channel có áp dụng kết quả không, subchannel có `READY` không và policy có chọn endpoint đó không. Chỉ nhìn số replica trong Kubernetes hoặc số record trong registry là chưa đủ.

## 14. Những lỗi tích hợp thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Nghĩ Spring `DiscoveryClient` tự động tích hợp với mọi gRPC channel | Channel vẫn chỉ dùng resolver mặc định | Viết adapter/custom resolver hoặc dùng xDS integration phù hợp |
| Gọi registry trên mỗi RPC | Tăng latency và tải control plane | Watch/poll ở resolver theo lifecycle channel |
| Register instance trước readiness | Client gửi request đến instance chưa phục vụ được | Chỉ công bố sau readiness |
| Deregister sau khi server đã dừng | Client tiếp tục chọn endpoint cũ | Báo không ready/deregister trước graceful shutdown |
| Registry trả nhiều IP nhưng policy chỉ dùng một | Không tận dụng các replica như mong muốn | Chọn policy phù hợp và kiểm tra subchannel |
| Client và proxy cùng retry không giới hạn | Retry storm và vượt deadline | Chọn một chính sách retry có ngân sách tổng |
| Coi `READY` là `SERVING` | Backend có thể lỗi dependency nhưng vẫn nhận RPC | Kết hợp gRPC health/readiness |
| Tin metadata registry không xác thực | Có nguy cơ định tuyến đến endpoint giả | Bảo vệ registry/control plane và xác minh TLS |

**Ghi nhớ:** Service discovery tìm và cập nhật endpoint; gRPC `NameResolver` chuyển endpoint thành `EquivalentAddressGroup`; load balancing policy chọn subchannel cho RPC mới. Với Spring Cloud registry, cần adapter/custom resolver hoặc control plane phù hợp, vì `DiscoveryClient` không tự nối vào mọi `ManagedChannel`. Đồng bộ register/readiness/deregister, cập nhật resolver có kiểm soát, chọn đúng policy và giữ TLS authority đáng tin cậy để discovery và load balancing phối hợp ổn định.
