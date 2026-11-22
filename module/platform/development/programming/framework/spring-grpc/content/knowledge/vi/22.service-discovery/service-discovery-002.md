# DNS resolver cho gRPC

DNS resolver giúp gRPC client tìm địa chỉ mạng của một dịch vụ từ tên DNS thay vì gắn cứng IP của một instance. Trong Spring gRPC, client đặt tên logic vào target URI, chẳng hạn `dns:///orders.default.svc.cluster.local:8443`; resolver tra cứu DNS và cung cấp các địa chỉ cho channel. Khi địa chỉ thay đổi, channel có thể nhận kết quả phân giải mới mà ứng dụng vẫn dùng cùng stub.

DNS resolver chỉ giải quyết bước **tên dịch vụ → địa chỉ endpoint**. Nó không tự xác thực server, kiểm tra sức khỏe ứng dụng hay quyết định phân phối request giữa các instance. Những nhiệm vụ đó liên quan đến TLS, health checking và load balancing.

## 1. DNS resolver hoạt động như thế nào?

Với target dùng scheme `dns`, gRPC chọn DNS `NameResolverProvider` được đăng ký trong runtime. Resolver lấy hostname từ target, tra cứu địa chỉ DNS và gửi kết quả về channel dưới dạng danh sách `EquivalentAddressGroup`.

Luồng cơ bản:

```text
Spring gRPC client
       |
       | target: dns:///orders.default.svc.cluster.local:8443
       v
ManagedChannel
       |
       v
NameResolverRegistry
       |
       v
DNS NameResolver
       |
       | tra cứu A / AAAA
       v
Danh sách địa chỉ IP:port
       |
       v
LoadBalancer và Subchannels
       |
       v
HTTP/2 connection tới service instance
```

Ở bước DNS, resolver có thể nhận nhiều địa chỉ cho cùng hostname. Nó chuyển các địa chỉ đó cho channel; load balancer dùng kết quả để tạo hoặc cập nhật subchannel. Resolver không trực tiếp chọn một instance cho từng RPC.

DNS resolver tiêu chuẩn của grpc-java thường dùng phân giải hostname qua hạ tầng DNS của JVM/nền tảng. Chi tiết truy vấn, cache và refresh có thể phụ thuộc phiên bản grpc-java, runtime và môi trường triển khai.

## 2. Cấu trúc DNS target

Target phổ biến có dạng:

```text
dns:///hostname:port
```

Ví dụ:

```text
dns:///orders.internal.example:8443
dns:///inventory.default.svc.cluster.local:9090
dns:///payments.prod.svc.cluster.local:443
```

Trong `dns:///...`, scheme là `dns`; authority để trống; hostname và port nằm trong path. Ba dấu gạch chéo là cú pháp có chủ đích, không phải dấu thừa.

| Thành phần | Ý nghĩa |
| --- | --- |
| `dns` | Chọn DNS resolver |
| Authority rỗng | Resolver không nhận authority riêng trong dạng target này |
| Hostname | Tên DNS cần phân giải |
| Port | Cổng gRPC mà client sẽ kết nối |

Không tự phân tích target bằng `split(":")`. Cách đó dễ sai với IPv6 và URI có authority/path. Hãy để gRPC resolver xử lý target theo cú pháp URI.

Với IPv6 literal, cú pháp địa chỉ cần dấu ngoặc vuông, ví dụ `[2001:db8::10]:8443`; tuy nhiên, nếu mục tiêu là discovery động, dùng hostname DNS thường dễ quản lý hơn.

## 3. DNS A và AAAA records

DNS thường trả về:

- **A record:** ánh xạ hostname sang địa chỉ IPv4.
- **AAAA record:** ánh xạ hostname sang địa chỉ IPv6.

Một hostname có thể trả một hoặc nhiều địa chỉ. Resolver cung cấp các địa chỉ mà DNS lookup trả về cho channel. Kết quả cụ thể phụ thuộc DNS server, cấu hình mạng, JVM và môi trường client.

Ví dụ một service có hai địa chỉ:

```text
orders.internal.example
    A     10.20.1.11
    A     10.20.1.12
    AAAA  2001:db8:20::11
```

Nếu channel nhận nhiều địa chỉ, load balancing policy quyết định cách sử dụng chúng. Một policy kiểu `pick_first` thường chọn một subchannel sẵn sàng; `round_robin` có thể phân phối RPC qua các subchannel sẵn sàng. Việc policy nào được chọn phụ thuộc cấu hình và provider có trong runtime.

**Nhiều DNS record không đồng nghĩa request chắc chắn được chia đều.** Hãy kiểm tra cả danh sách địa chỉ mà resolver phát ra và load balancing policy thực tế.

DNS SRV records cũng không nên được mặc định là cơ chế discovery của mọi gRPC DNS resolver. Target `dns:///host:port` thông thường xác định hostname và port; nếu hệ thống dựa vào SRV hoặc một quy ước DNS đặc biệt, phải xác nhận resolver triển khai có hỗ trợ và được cấu hình cho hành vi đó.

## 4. Sử dụng DNS resolver trong Spring gRPC

Trong grpc-java, `ManagedChannelBuilder.forTarget(...)` cho phép channel nhận target URI và chọn resolver theo scheme. `forAddress(...)` phù hợp khi client đã biết địa chỉ host/port cụ thể.

```java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrdersGrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel ordersChannel() {
        return ManagedChannelBuilder
            .forTarget(
                "dns:///orders.default.svc.cluster.local:8443")
            .useTransportSecurity()
            .build();
    }

    @Bean
    OrdersGrpc.OrdersBlockingStub ordersStub(
            ManagedChannel ordersChannel) {
        return OrdersGrpc.newBlockingStub(ordersChannel);
    }
}
```

`OrdersGrpc` là tên minh họa cho stub được sinh từ Protobuf. Trong ứng dụng thật, dùng lớp generated tương ứng. Spring quản lý channel bean và gọi `shutdown()` khi context đóng; không tạo channel mới cho mỗi RPC vì channel là đối tượng dài hạn, có thể tái sử dụng cho nhiều call.

Nếu starter Spring gRPC đã tự quản lý channel/client, khai báo target tại cơ chế cấu hình mà phiên bản starter đang dùng hỗ trợ. Tránh vừa để starter tạo channel vừa tự tạo một channel song song cho cùng endpoint mà không có lý do.

So sánh:

```java
// DNS discovery: target là tên dịch vụ ổn định.
ManagedChannel byDns = ManagedChannelBuilder
    .forTarget("dns:///orders.internal.example:8443")
    .useTransportSecurity()
    .build();

// Direct address: client đã biết địa chỉ cụ thể.
ManagedChannel direct = ManagedChannelBuilder
    .forAddress("10.20.1.11", 8443)
    .useTransportSecurity()
    .build();
```

`forAddress(...)` không đem lại cùng hành vi discovery theo hostname như DNS target. Nếu địa chỉ instance thay đổi, ứng dụng dùng direct address phải tự cập nhật cấu hình hoặc tạo lại channel.

## 5. DNS resolver trong Kubernetes

Trong Kubernetes, DNS Service giúp client dùng tên ổn định thay cho Pod IP. Cần phân biệt **ClusterIP Service** và **headless Service** vì chúng tạo ra hành vi discovery khác nhau.

| Loại Service | DNS thường trả về | Ai phân phối traffic? |
| --- | --- | --- |
| ClusterIP | Một virtual IP ổn định của Service | Kubernetes service dataplane (ví dụ kube-proxy hoặc implementation tương đương) |
| Headless (`clusterIP: None`) | Địa chỉ các Pod endpoint phù hợp với cấu hình Service | Client gRPC/load balancer có thể chọn giữa các địa chỉ được phân giải |

Ví dụ DNS name nội bộ:

```text
orders.default.svc.cluster.local
```

Nếu client gọi ClusterIP Service, DNS resolver thường chỉ thấy virtual IP. Khi đó gRPC client-side load balancer không nhìn thấy từng Pod; việc phân phối kết nối do dataplane của Kubernetes đảm nhiệm.

Với headless Service, DNS có thể trả nhiều Pod IP. Channel có thể nhận danh sách endpoint và áp dụng policy như `round_robin` nếu policy đó được cấu hình và hỗ trợ. Điều này hữu ích khi muốn client gRPC quản lý lựa chọn endpoint, nhưng cần hiểu readiness, endpoint publication và cập nhật DNS trong cluster.

Ví dụ Service headless:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: orders
  namespace: default
spec:
  clusterIP: None
  selector:
    app: orders
  ports:
    - name: grpc
      port: 8443
      targetPort: 8443
```

Đây là manifest minh họa. FQDN và namespace phải khớp với cluster thực tế. Cấu hình `publishNotReadyAddresses`, readiness probe và endpoint lifecycle có thể ảnh hưởng các địa chỉ được DNS công bố; không giả định DNS record luôn tương đương với trạng thái ứng dụng khỏe mạnh.

## 6. Resolver refresh, DNS cache và endpoint thay đổi

DNS thay đổi không có nghĩa mọi channel lập tức nhìn thấy endpoint mới. Đường đi của cập nhật phụ thuộc nhiều lớp:

1. DNS record được cập nhật tại authoritative DNS hoặc Kubernetes DNS.
2. Recursive resolver/cache có thể tiếp tục trả kết quả cũ cho tới khi hết TTL hoặc cache policy cho phép làm mới.
3. JVM/platform DNS cache có thể giữ kết quả theo cấu hình runtime.
4. gRPC `NameResolver` cần thực hiện lần phân giải tiếp theo và gửi kết quả mới qua listener.
5. Load balancer cập nhật subchannel; kết nối cũ có thể còn tồn tại trong một khoảng thời gian.

Vì vậy, **TTL của DNS không đảm bảo thời điểm client chuyển sang endpoint mới**. Cần kiểm tra JVM DNS cache, resolver implementation/version, refresh behavior, DNS caching của cluster và lifecycle của kết nối.

`NameResolver` có các điểm vòng đời quan trọng:

- `start(listener)`: bắt đầu phân giải và gửi `ResolutionResult`.
- `refresh()`: yêu cầu phân giải lại khi channel cần cập nhật.
- `shutdown()`: dừng resolver và giải phóng tài nguyên.

Ứng dụng thông thường không cần tự gọi các API này khi dùng DNS resolver tiêu chuẩn. Chúng hữu ích khi tìm hiểu hành vi resolver hoặc triển khai resolver tùy chỉnh.

Không nên đặt DNS TTL quá thấp chỉ để ép discovery cập nhật nhanh. Việc đó có thể làm tăng truy vấn DNS và tải lên control plane. Hãy cân bằng tốc độ cập nhật, cache, thời gian sống của kết nối và khả năng phục hồi.

## 7. DNS discovery không thay thế health checking

DNS resolver cho biết hostname phân giải thành những địa chỉ nào. Điều đó không nhất thiết chứng minh gRPC server tại mỗi địa chỉ đang nhận request hoặc xử lý nghiệp vụ khỏe mạnh.

Phân biệt:

- **DNS resolution:** tìm địa chỉ từ tên.
- **Transport connectivity:** channel có thiết lập được kết nối tới địa chỉ không.
- **gRPC health checking:** service có báo trạng thái phục vụ theo health protocol hay không.
- **Application readiness:** instance đã sẵn sàng nhận loại traffic nghiệp vụ cụ thể chưa.

Một Pod có thể còn địa chỉ trong DNS trong lúc ứng dụng đang shutdown hoặc chưa sẵn sàng, tùy cấu hình và thời điểm cập nhật. Ngược lại, DNS có thể đã bỏ endpoint nhưng client còn cache địa chỉ cũ. Cần kết hợp readiness, graceful shutdown, connection draining và retry policy có giới hạn.

Không dùng `UNAVAILABLE` như bằng chứng duy nhất rằng DNS sai. Status này có thể xuất phát từ DNS, kết nối TCP, TLS, proxy, server shutdown hoặc lỗi hạ tầng khác.

## 8. TLS authority và tên DNS

DNS resolver chuyển hostname thành IP, nhưng TLS vẫn cần xác minh **danh tính dịch vụ**. Nếu client target là:

```text
dns:///orders.default.svc.cluster.local:8443
```

chứng thư server cần có danh tính phù hợp với hostname mà client dùng, thường thể hiện qua Subject Alternative Name (SAN). DNS lookup thành công không làm hostname mismatch trở nên hợp lệ.

Không chuyển sang plaintext hoặc tắt xác minh hostname để khắc phục lỗi chứng thư. Hãy cấp certificate có SAN phù hợp, cấu hình trust chain đúng và kiểm tra authority mà gRPC dùng cho TLS. URI authority của resolver và TLS authority là khái niệm riêng; không override TLS authority tùy tiện để né xác minh chứng thư.

## 9. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `UNAVAILABLE` ngay khi tạo/gọi channel | Không tìm thấy provider cho scheme hoặc resolver không phân giải được target | Kiểm tra scheme, target URI và resolver registry |
| DNS trả NXDOMAIN | Sai hostname, namespace hoặc search domain | Tra cứu từ đúng container/pod chạy client |
| DNS trả SERVFAIL/timeout | DNS server hoặc network path có vấn đề | Kiểm tra cluster DNS, resolver config và network policy |
| DNS có địa chỉ nhưng kết nối thất bại | Port sai, firewall, Pod chưa listen hoặc TLS mismatch | Kiểm tra endpoint, port, transport và certificate |
| Chỉ một instance nhận traffic | DNS chỉ trả một địa chỉ hoặc policy là `pick_first` | Quan sát resolution result và load balancer policy |
| Endpoint mới không được sử dụng | Cache, refresh hoặc subchannel cũ còn hoạt động | Kiểm tra TTL, JVM DNS cache, resolver refresh và connection state |
| Lỗi sau khi Pod thay thế | Client dùng IP cố định hoặc còn endpoint cũ | Dùng DNS target ổn định và kiểm thử cập nhật |
| TLS hostname mismatch | SAN không khớp target hostname | Kiểm tra certificate SAN và TLS authority |

Chẩn đoán theo thứ tự: **target URI → DNS lookup → resolver result → load balancer/subchannel → TCP/HTTP2 → TLS → gRPC status**. Thứ tự này giúp phân biệt lỗi discovery với lỗi transport và lỗi xử lý RPC.

## 10. Kiểm thử DNS resolver

Kiểm thử cần bao phủ URI, DNS, endpoint update, TLS và lifecycle của channel:

| Ca kiểm thử | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| DNS target hợp lệ | Dùng hostname có A/AAAA record | Resolver trả đúng địa chỉ và port |
| Target sai hostname | Dùng tên không tồn tại | Resolution/connectivity thất bại có thể chẩn đoán |
| Nhiều DNS records | Hostname trả nhiều địa chỉ | Resolver phát danh sách endpoint theo kết quả DNS |
| DNS record thay đổi | Thay địa chỉ trong test DNS có kiểm soát | Sau refresh/cache propagation, channel cập nhật endpoint |
| Headless Service | Gọi từ pod trong cùng cluster | DNS trả endpoint theo cấu hình Kubernetes |
| ClusterIP Service | Gọi qua virtual IP | Xác nhận dataplane Kubernetes phân phối traffic |
| TLS SAN không khớp | Dùng certificate sai hostname | TLS handshake thất bại; không bỏ xác minh |
| Resolver/channel shutdown | Đóng Spring context | Channel và tài nguyên liên quan được giải phóng |
| DNS tạm thời unavailable | Làm DNS test server không phản hồi | Client phục hồi theo retry/refresh policy đã định nghĩa |

Unit test có thể kiểm tra cách tạo target và cấu hình channel. Để kiểm thử resolver thay đổi địa chỉ, dùng DNS server test có thể điều khiển hoặc resolver test double; không dựa vào DNS công cộng vốn thay đổi ngoài kiểm soát. Với Kubernetes, chạy test từ cùng namespace/network policy như client thật. In-process gRPC test không kiểm tra DNS, HTTP/2 network path hay TLS.

## 11. Bài tập vận dụng

`OrderService` chạy nhiều Pod trong Kubernetes. Client Spring gRPC đang cấu hình trực tiếp IP của một Pod, nên khi Pod được thay thế, lời gọi có thể thất bại.

**Yêu cầu:**

1. Đổi target sang `dns:///orders.default.svc.cluster.local:8443` và giải thích các phần URI.
2. So sánh DNS của ClusterIP Service với headless Service; xác định nơi thực hiện load balancing trong từng trường hợp.
3. Kiểm tra DNS A/AAAA, cache và thời gian client nhận endpoint mới sau rollout.
4. Cấu hình load balancing policy phù hợp nếu DNS trả nhiều Pod IP; xác minh provider và service config được hỗ trợ.
5. Bảo đảm certificate SAN phù hợp hostname DNS và channel được Spring đóng khi context shutdown.
6. Viết test cho NXDOMAIN, nhiều địa chỉ, endpoint update, TLS hostname mismatch và DNS tạm thời unavailable.

**Câu hỏi tự kiểm tra:**

- DNS resolver nhận gì từ target URI và trả gì cho channel?
- Vì sao nhiều A/AAAA records không đảm bảo request được chia đều?
- ClusterIP và headless Service khác nhau thế nào với client-side load balancing?
- Vì sao DNS TTL không đồng nghĩa client chuyển endpoint đúng tại thời điểm TTL hết?
- DNS resolver có xác nhận service khỏe mạnh không?
- Vì sao TLS certificate phải khớp hostname target dù DNS đã phân giải thành IP?
- Khi nào nên dùng `forTarget(...)` thay cho `forAddress(...)`?

**Ghi nhớ:** DNS resolver biến hostname trong target URI thành danh sách địa chỉ cho gRPC channel. Load balancer mới quyết định cách dùng các endpoint; DNS không thay thế health checking, TLS hay readiness. Trong Spring gRPC, hãy dùng DNS target ổn định, hiểu rõ ClusterIP/headless Service, kiểm tra cache và refresh trong môi trường thực, đồng thời xác minh certificate theo hostname logic.
