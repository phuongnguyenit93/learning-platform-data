# Target URI và resolver

Trong Spring gRPC, client thường gọi một **tên dịch vụ logic** thay vì gắn cứng vào IP của một instance. Tên logic đó được đặt trong target URI của channel. **Name resolver** đọc URI, tìm các endpoint hiện có và thông báo danh sách địa chỉ cho gRPC channel. Nhờ vậy, khi instance thay đổi, client có thể tiếp tục gọi dịch vụ qua cùng một target.

Target URI và resolver là hai phần khác nhau: URI mô tả *dịch vụ cần tìm*, còn resolver quyết định *tìm dịch vụ đó ở đâu*. Hiểu rõ quan hệ này giúp cấu hình DNS, Kubernetes Service, registry nội bộ hoặc resolver tùy chỉnh đúng cách trong ứng dụng Spring gRPC.

## 1. Target URI là gì?

Target là chuỗi định danh đầu vào cho một gRPC channel. Với API `ManagedChannelBuilder.forTarget(...)`, target thường được phân tích như một URI để chọn resolver provider phù hợp.

Dạng URI tổng quát:

```text
scheme://authority/path?query
```

Ý nghĩa từng phần:

| Thành phần | Vai trò |
| --- | --- |
| `scheme` | Chọn loại resolver, ví dụ `dns` hoặc scheme do ứng dụng đăng ký |
| `authority` | Thông tin authority dành cho resolver; ý nghĩa cụ thể phụ thuộc scheme |
| `path` | Tên dịch vụ hoặc target mà resolver cần phân giải |
| `query` | Tham số tùy chọn do resolver cụ thể định nghĩa |

Ví dụ DNS target thường dùng:

```text
dns:///orders.internal.example:8443
dns:///orders.default.svc.cluster.local:8443
```

Ở dạng `dns:///...`, scheme là `dns`, authority để trống và path chứa hostname cùng port cần phân giải. Ba dấu gạch chéo là có chủ ý: chúng tạo URI có authority rỗng và path bắt đầu bằng dấu gạch chéo.

Không nên tự cắt chuỗi target bằng `split(":")` hoặc xem mọi phần sau `://` đều là hostname. IPv6, authority và path có quy tắc URI riêng; resolver chịu trách nhiệm phân tích target theo scheme của nó.

## 2. Scheme chọn resolver nào?

`NameResolverRegistry` của grpc-java quản lý các `NameResolverProvider` đã đăng ký. Khi channel nhận target URI, registry tìm provider có scheme tương ứng và yêu cầu provider tạo resolver.

Ví dụ:

| Target | Resolver được chọn | Mục đích |
| --- | --- | --- |
| `dns:///orders.example.net:8443` | DNS resolver | Phân giải tên DNS thành địa chỉ mạng |
| `dns:///orders.default.svc.cluster.local:8443` | DNS resolver | Phân giải tên Kubernetes Service qua DNS cluster |
| `catalog:///orders` | Resolver tùy chỉnh có scheme `catalog` | Tra cứu service registry hoặc catalog nội bộ |

`catalog` chỉ là ví dụ về scheme ứng dụng; nó hoạt động khi ứng dụng đã đăng ký provider tương ứng. Một target có scheme không được đăng ký sẽ không được resolver mặc định tự hiểu.

Nên khai báo scheme tường minh trong target. Nếu target không có scheme, gRPC phải áp dụng default scheme của registry; default có thể phụ thuộc các provider đang có trong runtime. Dựa vào default ngầm định có thể khiến hành vi khác nhau giữa môi trường local, test và production.

## 3. DNS target và địa chỉ trực tiếp

Khi cần service discovery, hãy phân biệt `forTarget(...)` với `forAddress(...)`:

```java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

// Target logic: DNS resolver tìm địa chỉ cho service name.
ManagedChannel discoveredChannel =
    ManagedChannelBuilder
        .forTarget("dns:///orders.default.svc.cluster.local:8443")
        .useTransportSecurity()
        .build();

// Địa chỉ cụ thể: kết nối tới host/port đã biết.
ManagedChannel directChannel =
    ManagedChannelBuilder
        .forAddress("10.20.1.15", 8443)
        .useTransportSecurity()
        .build();
```

`forTarget(...)` đưa target qua cơ chế name resolution. `forAddress(...)` phù hợp khi ứng dụng đã biết địa chỉ socket cụ thể và không cần phân giải tên dịch vụ theo cách đó. Một địa chỉ trực tiếp thường hữu ích cho test hoặc endpoint cố định; nó làm giảm khả năng thích ứng khi instance thay đổi.

Trong production, DNS target có thể trỏ tới một tên service ổn định. Resolver lấy các địa chỉ hiện hành; load balancing policy của channel quyết định cách sử dụng chúng. DNS discovery không tự bảo đảm request được phân phối đều tới từng instance.

Ví dụ trên dùng TLS. Chỉ dùng `usePlaintext()` trong môi trường phát triển/test được kiểm soát; không chuyển sang plaintext chỉ để xử lý lỗi DNS hoặc resolver.

## 4. Resolver làm gì trong vòng đời channel?

Resolver không trực tiếp xử lý RPC message. Nó cung cấp danh sách địa chỉ cho channel:

1. Channel nhận target URI và chọn resolver provider theo scheme.
2. Provider tạo `NameResolver` với target và các tham số của channel.
3. Channel khởi động resolver; resolver tra cứu nguồn discovery như DNS hoặc service registry.
4. Resolver phát `ResolutionResult` chứa một hoặc nhiều địa chỉ (`EquivalentAddressGroup`) cùng attributes/service config nếu có.
5. Load balancer nhận danh sách endpoint, tạo hoặc cập nhật subchannel và chọn đường kết nối cho RPC.
6. Khi endpoint thay đổi hoặc cần làm mới, resolver phát kết quả mới; channel và load balancer cập nhật kết nối.

Vòng đời khái quát:

```text
forTarget(target URI)
       |
       v
NameResolverRegistry
       |
       v
NameResolverProvider theo scheme
       |
       v
NameResolver.start(listener)
       |
       v
Tra cứu DNS / service registry
       |
       v
ResolutionResult: endpoint list + attributes
       |
       v
LoadBalancer -> Subchannels -> RPC
       |
       +---- refresh / endpoint update ----> Resolver
```

Resolver thường có các điểm vòng đời chính:

- `start(listener)`: bắt đầu phân giải và gửi kết quả qua listener.
- `refresh()`: yêu cầu làm mới khi channel cần cập nhật.
- `shutdown()`: dừng resolver và giải phóng tài nguyên.
- `getServiceAuthority()`: cung cấp service authority mà resolver đại diện.

Việc tra cứu thường bất đồng bộ. Không thực hiện DNS, gọi registry hoặc chờ mạng đồng bộ ngay trên thread xử lý RPC. Resolver cần quản lý executor, timeout, retry/backoff và hủy tác vụ khi shutdown.

## 5. Resolver và load balancer không phải một

Đây là ranh giới kiến trúc quan trọng:

| Thành phần | Trả lời câu hỏi | Ví dụ trách nhiệm |
| --- | --- | --- |
| Target URI | Client muốn gọi dịch vụ logic nào? | `dns:///orders.internal:8443` |
| Name resolver | Dịch vụ đó hiện có những endpoint nào? | `10.0.1.8:8443`, `10.0.1.9:8443` |
| Load balancer | Chọn endpoint nào cho RPC/subchannel? | `pick_first`, `round_robin` nếu policy được hỗ trợ/cấu hình |
| Channel/transport | Thiết lập và quản lý kết nối tới endpoint | HTTP/2, TLS, reconnect, call lifecycle |

Resolver trả về endpoint; nó không nhất thiết chọn một endpoint cho từng request. Load balancer sử dụng kết quả phân giải để quyết định cách chọn kết nối. Ví dụ, resolver có thể trả ba địa chỉ; policy `round_robin` có thể phân phối các RPC lần lượt qua các subchannel sẵn sàng, trong khi `pick_first` thường chọn một subchannel phù hợp trước.

Nếu chỉ có một endpoint trong kết quả phân giải, resolver vẫn đang làm discovery; load balancer chỉ có ít lựa chọn hơn. Nếu registry trả endpoint không khỏe mạnh, cần health filtering hoặc discovery policy phù hợp; không giả định resolver tự biết trạng thái ứng dụng nếu nguồn dữ liệu không cung cấp.

## 6. Tích hợp target URI trong Spring gRPC

Trong ứng dụng Spring, channel hoặc client stub có thể được quản lý bởi cấu hình/bean của Spring gRPC. Dù channel được tạo thủ công hay do starter quản lý, target vẫn có cùng ý nghĩa: nó xác định scheme và tên logic mà resolver cần phân giải.

Ví dụ khi tạo channel bằng grpc-java:

```java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderGrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel orderChannel() {
        return ManagedChannelBuilder
            .forTarget("dns:///orders.default.svc.cluster.local:8443")
            .useTransportSecurity()
            .build();
    }
}
```

Đây là ví dụ quản lý channel bằng Spring bean ở tầng grpc-java. Nếu starter Spring gRPC của dự án đã tự quản lý channel lifecycle, hãy khai báo target tại cơ chế cấu hình client mà phiên bản đó hỗ trợ và inject channel/stub tương ứng; không tạo thêm channel mới cho từng RPC.

Các điểm cần kiểm tra trong cấu hình ứng dụng:

- Target có scheme đúng với resolver provider đang có không?
- DNS name/registry key có đúng namespace, domain và port không?
- Channel có dùng TLS và trust material phù hợp với endpoint không?
- Resolver có được đăng ký trước khi channel được tạo không?
- Channel được đóng khi Spring context shutdown không?
- Load balancing policy có hỗ trợ và phù hợp với danh sách endpoint không?

Không đồng nhất URI authority với TLS authority. Resolver authority là phần của target URI và được resolver diễn giải. TLS/HTTP/2 authority là danh tính dịch vụ dùng khi thiết lập kết nối. Nếu cần override authority, hãy dùng API/cấu hình TLS authority được hỗ trợ và bảo đảm chứng thư máy chủ hợp lệ; không sửa hostname trong target chỉ để bỏ qua lỗi xác minh chứng thư.

## 7. Khi nào cần resolver tùy chỉnh?

DNS resolver phù hợp khi tên dịch vụ được DNS cung cấp. Một resolver tùy chỉnh có ích khi endpoint đến từ:

- Service registry nội bộ có API riêng.
- Control plane hoặc catalog của nền tảng.
- Cấu hình động theo tenant/region/environment.
- Nguồn discovery cần trả thêm attributes hoặc service config.

Resolver tùy chỉnh thường gồm hai phần:

1. **`NameResolverProvider`:** đăng ký scheme, nhận target URI và tạo resolver phù hợp.
2. **`NameResolver`:** phân tích service key, tra cứu endpoint, chuyển kết quả thành `ResolutionResult`, nhận refresh và shutdown đúng vòng đời.

Luồng xử lý minh họa:

```text
Target: catalog:///orders?region=ap-southeast
       |
       v
CatalogNameResolverProvider
       |
       v
CatalogNameResolver("orders", "ap-southeast")
       |
       v
Registry client (timeout + authentication)
       |
       v
EquivalentAddressGroup list
       |
       v
ResolutionResult -> gRPC channel
```

Đây là URI minh họa; query parameter chỉ có ý nghĩa nếu resolver `catalog` định nghĩa và validate chúng. Không đưa token registry vào URI vì target có thể xuất hiện trong log, exception hoặc diagnostics.

Khi triển khai custom resolver, cần:

- Validate scheme, authority, path và query; từ chối target sai thay vì âm thầm phân giải nhầm service.
- Dùng registry client có timeout, TLS và authentication riêng.
- Gửi kết quả mới qua listener khi endpoint thay đổi.
- Báo lỗi bằng status thích hợp; phân biệt registry tạm thời unavailable với target sai cấu trúc.
- Có retry/backoff có giới hạn và không tạo vòng lặp tra cứu dày đặc.
- Dừng watcher, scheduler và executor trong `shutdown()`.
- Không giữ endpoint cũ vô thời hạn khi đã hết hiệu lực; định nghĩa rõ chính sách stale result.

## 8. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `UNAVAILABLE` ngay khi tạo/gọi channel | Không tìm thấy provider cho scheme hoặc resolver không phân giải được target | Kiểm tra scheme, target URI và resolver registry |
| DNS trả NXDOMAIN | Sai service name, namespace hoặc domain | Tra cứu DNS từ đúng môi trường chạy client |
| DNS có địa chỉ nhưng kết nối thất bại | Port sai, firewall, endpoint chưa listen hoặc TLS mismatch | Kiểm tra endpoint, network path và chứng thư |
| Channel luôn gọi một instance | Resolver chỉ trả một endpoint hoặc LB policy không như mong muốn | Quan sát resolution result và policy thực tế |
| Endpoint mới không được dùng | Resolver không refresh hoặc registry watcher không phát cập nhật | Kiểm tra refresh lifecycle và listener callback |
| Hoạt động local nhưng lỗi trong Kubernetes | Khác DNS search domain, namespace hoặc network policy | Kiểm tra target FQDN và DNS từ pod/client runtime |
| TLS hostname mismatch | Authority/SAN của certificate không khớp danh tính server | Kiểm tra certificate SAN và authority; không tắt TLS verification |
| Custom resolver leak thread | Không dừng executor/watcher khi channel shutdown | Kiểm tra `shutdown()` và lifecycle bean |

Chẩn đoán theo thứ tự: parse target → chọn provider → resolver result → load balancer/subchannel → kết nối transport → TLS → RPC status. Cách này tách lỗi discovery khỏi lỗi kết nối và lỗi xử lý nghiệp vụ.

## 9. Kiểm thử target URI và resolver

Nên có unit test cho URI/parser và resolver, cùng integration test cho channel thực sự sử dụng kết quả phân giải.

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Target DNS hợp lệ | Chọn DNS resolver và phân giải hostname/port |
| Scheme không đăng ký | Thất bại rõ ràng; không âm thầm dùng resolver khác |
| URI sai cấu trúc | Bị từ chối với lỗi target có thể chẩn đoán |
| Target thiếu port | Hành vi theo default port đã định nghĩa; không đoán ngầm trong ứng dụng |
| Resolver trả nhiều endpoint | Resolution result chứa đúng danh sách địa chỉ |
| Registry unavailable | Resolver báo lỗi, áp dụng retry/backoff có giới hạn |
| Endpoint thay đổi | Resolver phát kết quả mới và channel cập nhật subchannel |
| Channel shutdown | Resolver dừng watcher/executor và không phát kết quả mới |
| TLS authority không khớp | Kết nối thất bại; không bypass xác minh chứng thư |
| Spring context shutdown | Channel được đóng và tài nguyên được giải phóng |

Với custom resolver, dùng registry giả trong test để kiểm soát endpoint và cập nhật. Integration test nên xác minh RPC thực sự tới endpoint mong đợi sau lần phân giải đầu và sau khi danh sách endpoint thay đổi. Test DNS production-like cần chạy từ môi trường có cùng DNS/network policy; một unit test parse URI không chứng minh DNS trong cluster hoạt động.

## 10. Bài tập vận dụng

`OrderService` có nhiều instance trong Kubernetes. Client Spring gRPC hiện cấu hình trực tiếp IP của một pod, nên khi pod được thay thế, lời gọi có thể thất bại.

**Yêu cầu:**

1. Chuyển client sang target logic dạng `dns:///orders.default.svc.cluster.local:8443`.
2. Giải thích scheme, authority và path của target URI; xác minh DNS name từ môi trường chạy client.
3. Phân biệt việc resolver trả endpoint với load balancer chọn subchannel.
4. Bảo đảm channel dùng TLS với certificate identity phù hợp và được Spring quản lý lifecycle.
5. Thiết kế test cho DNS failure, endpoint update, TLS hostname mismatch và channel shutdown.
6. Nếu DNS không đáp ứng nhu cầu discovery, phác thảo custom scheme và vòng đời `NameResolverProvider`/`NameResolver` cho registry nội bộ.

**Câu hỏi tự kiểm tra:**

- Target URI mô tả dịch vụ logic hay một message RPC?
- Scheme trong URI quyết định thành phần nào?
- Vì sao `forTarget(...)` phù hợp với discovery hơn địa chỉ IP cố định?
- Resolver khác load balancer ở nhiệm vụ nào?
- `dns:///host:port` có ý nghĩa gì với authority và path?
- Vì sao target URI authority không nên bị nhầm với TLS authority?
- Custom resolver cần dừng những tài nguyên nào khi channel shutdown?

**Ghi nhớ:** Target URI chọn resolver và chỉ ra dịch vụ logic cần tìm; resolver biến target thành danh sách endpoint; load balancer dùng danh sách đó để chọn kết nối cho RPC. Trong Spring gRPC, hãy dùng scheme tường minh, quản lý channel theo lifecycle ứng dụng, kiểm tra DNS/registry và TLS trên môi trường thực, đồng thời kiểm thử cả cập nhật endpoint lẫn shutdown.
