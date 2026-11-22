# Môi trường local và production discovery

Service discovery phải hoạt động nhất quán từ máy lập trình tới môi trường production, dù nguồn endpoint và yêu cầu bảo mật giữa các môi trường có thể khác nhau. Trong Spring gRPC, client nên gọi một **target logic** được cấu hình theo môi trường; gRPC channel dùng resolver để tìm endpoint, sau đó load balancer quản lý kết nối và chọn backend.

Ở local, endpoint thường cố định và dễ quan sát: một process trên máy phát triển, Docker Compose service hoặc test server. Ở production, địa chỉ có thể thay đổi theo Pod, zone, rollout hoặc registry lease. Mục tiêu là giữ cách gọi service ổn định trong ứng dụng, đồng thời cấu hình rõ target, TLS, readiness và cơ chế cập nhật endpoint cho từng môi trường.

## 1. Tách target khỏi mã nguồn

Không hard-code hostname, IP hoặc port production trong client. Đưa target vào cấu hình ngoài ứng dụng để mỗi profile chọn đúng nguồn discovery:

| Môi trường | Target minh họa | Ý nghĩa |
| --- | --- | --- |
| Local, server chạy trên máy lập trình | `dns:///localhost:9090` | DNS resolver phân giải loopback và kết nối cổng local |
| Docker Compose, client và server là hai container | `dns:///orders:9090` | Dùng tên service trong mạng Compose |
| Kubernetes ClusterIP Service | `dns:///orders.default.svc.cluster.local:8443` | DNS phân giải tên Service thành virtual IP |
| Kubernetes headless Service | `dns:///orders-headless.default.svc.cluster.local:8443` | DNS có thể trả các Pod endpoint để client-side discovery |
| Registry riêng | `catalog:///orders` | Dùng custom resolver đã đăng ký scheme `catalog` |

`dns:///` chọn DNS resolver; hostname và port là target cần phân giải. Scheme `catalog` chỉ hoạt động khi ứng dụng đã đăng ký `NameResolverProvider` tương ứng. Không đưa token hoặc mật khẩu vào target URI vì target có thể xuất hiện trong log và diagnostics.

Một lỗi local thường gặp là dùng `localhost` giữa hai container. Trong container, `localhost` trỏ về chính container đó. Nếu client và server là hai container riêng, dùng DNS service name trên cùng network, ví dụ `orders:9090`. Nếu client chạy trên host và server publish port ra host, `localhost:<published-port>` mới là địa chỉ phù hợp.

## 2. Cấu hình theo Spring profile

Có thể giữ một property cho target và thay giá trị bằng profile hoặc biến môi trường:

```yaml
# application-local.yml
clients:
  orders:
    target: dns:///localhost:9090

---
# application-prod.yml
clients:
  orders:
    target: dns:///orders.default.svc.cluster.local:8443
```

Khi deploy, kích hoạt profile và inject cấu hình từ environment/config management. Không để giá trị production làm fallback ngầm cho local hoặc ngược lại. Nếu target bắt buộc mà bị thiếu, ứng dụng nên fail fast lúc khởi tạo channel thay vì đợi RPC đầu tiên mới phát hiện.

Ví dụ channel đọc target từ Spring configuration:

```java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;

@Configuration
class OrdersGrpcChannelConfiguration {

    @Bean(destroyMethod = "shutdown")
    @Profile("local")
    ManagedChannel localOrdersChannel(Environment environment) {
        String target =
            environment.getRequiredProperty("clients.orders.target");
        return ManagedChannelBuilder
            .forTarget(target)
            .usePlaintext()
            .build();
    }

    @Bean(destroyMethod = "shutdown")
    @Profile("prod")
    ManagedChannel productionOrdersChannel(Environment environment) {
        String target =
            environment.getRequiredProperty("clients.orders.target");
        return ManagedChannelBuilder
            .forTarget(target)
            .useTransportSecurity()
            .build();
    }
}
```

Ví dụ dùng hai profile tách biệt để chế độ plaintext chỉ được tạo trong local và production dùng TLS. Nếu dự án có nhiều profile như `staging`, `test` hoặc `devcontainer`, hãy định nghĩa rõ profile nào dùng transport nào; không dựa vào một boolean có default plaintext.

Đây là cấu hình grpc-java trực tiếp. Nếu Spring gRPC starter của dự án tự quản lý channel, hãy khai báo target và transport qua property/extension point của đúng phiên bản starter, rồi inject stub do starter cung cấp. Không tạo thêm channel thủ công cho từng RPC; `ManagedChannel` là tài nguyên dài hạn và cần được đóng khi Spring context shutdown.

## 3. Local discovery: chọn đúng topology

Local không phải lúc nào cũng là một process trên máy:

| Cách chạy | Target phù hợp | Điều cần xác minh |
| --- | --- | --- |
| Client và server cùng máy, hai process | `dns:///localhost:9090` | Server bind đúng port; firewall local không chặn |
| Client trên host, server trong container có port publish | `dns:///localhost:19090` | Host port ánh xạ tới container port `9090` |
| Client và server trong Docker Compose | `dns:///orders:9090` | Hai container cùng network; service name và port đúng |
| Client test gọi server in-process | In-process channel/server test transport | Không cần DNS hoặc socket; chỉ kiểm tra logic gRPC |
| Nhiều instance local | DNS/service registry giả hoặc custom resolver test | Resolver trả đủ endpoint; policy LB được cấu hình |

Với một server local cố định, `forAddress("localhost", 9090)` cũng có thể phù hợp. Khi muốn kiểm thử chính target/resolver mà production sử dụng, dùng `forTarget("dns:///localhost:9090")` để đi qua DNS resolver.

Local registry giả nên tái tạo contract của production ở mức cần thiết: service name, instance ID, host/port, readiness và cập nhật endpoint. Không cần mô phỏng toàn bộ hạ tầng production, nhưng cần kiểm tra client xử lý được endpoint thêm/xóa và registry unavailable.

## 4. Production discovery trong Kubernetes

Trong Kubernetes, DNS Service cung cấp tên ổn định trong khi Pod IP thay đổi. Hai topology thường gặp có tác động khác nhau tới load balancing:

| Service | DNS thường trả về | Nơi phân phối kết nối |
| --- | --- | --- |
| ClusterIP | Một virtual IP ổn định | Kubernetes service dataplane chọn backend khi thiết lập kết nối |
| Headless (`clusterIP: None`) | Danh sách Pod IP đủ điều kiện theo cấu hình Service | gRPC client có thể tạo nhiều subchannel và áp dụng client-side load balancing |

Với ClusterIP, một gRPC channel thường duy trì một kết nối HTTP/2 lâu dài tới một backend được chọn ở tầng mạng. Nhiều RPC multiplex trên cùng kết nối có thể tập trung vào backend đó; không nên kỳ vọng ClusterIP tự phân phối từng RPC của một channel.

Với headless Service, DNS có thể trả nhiều Pod IP. Resolver đưa danh sách đó tới load balancer; policy như `round_robin` có thể phân phối RPC mới qua các subchannel `READY` nếu policy được hỗ trợ và cấu hình đúng. Khi chọn topology, cân nhắc readiness, certificate identity, DNS caching và khả năng client kết nối trực tiếp tới Pod.

Target production không được trỏ tới Pod IP cố định. Dùng service DNS hoặc custom resolver để theo dõi endpoint. Với nhiều namespace/cluster, dùng FQDN rõ ràng để tránh phụ thuộc DNS search path của Pod.

## 5. Production discovery qua registry riêng

Một số nền tảng dùng Consul, Eureka hoặc registry nội bộ thay cho DNS thuần. Trong trường hợp đó:

1. Server đăng ký service name, instance ID, endpoint, zone và trạng thái readiness sau khi sẵn sàng.
2. Lease/heartbeat giữ registration còn hiệu lực; deregistration loại instance khi shutdown bình thường.
3. Custom `NameResolverProvider` nhận target scheme, ví dụ `catalog:///orders`.
4. `NameResolver` tra cứu/watch registry và phát snapshot `ResolutionResult`.
5. Load balancer cập nhật subchannel và picker cho RPC mới.

Không đăng ký song song vào nhiều registry nếu chưa xác định rõ registry nào là nguồn sự thật. Nếu nền tảng đã cung cấp Spring integration chính thức cho Consul/Eureka, ưu tiên dùng integration đó thay vì tự tạo heartbeat và registration trùng lặp.

Registry là nguồn dữ liệu discovery, không phải ranh giới bảo mật. Client vẫn cần TLS/mTLS, xác minh certificate và authentication cho RPC. Chỉ công bố endpoint client có thể truy cập; không đưa registry credentials vào service metadata.

## 6. TLS và authority phải khớp target logic

Local có thể dùng plaintext khi server chỉ bind trong môi trường phát triển được kiểm soát. Production cần xác thực server bằng TLS và trust chain phù hợp; dùng mTLS nếu kiến trúc yêu cầu xác thực hai chiều.

Nếu target là `orders.default.svc.cluster.local`, certificate server cần có SAN phù hợp với danh tính mà client xác minh. DNS phân giải hostname thành IP không thay đổi danh tính TLS. Không tắt hostname verification hoặc chuyển production sang plaintext để khắc phục certificate mismatch.

Khi proxy hoặc service mesh kết thúc TLS, xác định rõ từng chặng:

- Client → gateway/sidecar: protocol, TLS identity và trust.
- Gateway/sidecar → gRPC server: HTTP/2, TLS/mTLS hoặc plaintext nội bộ theo policy.
- Authority mà client dùng để xác minh server: phải khớp certificate SAN hoặc authority override được cấu hình có chủ đích.

Không nhầm URI authority của resolver với TLS authority. Thay hostname target để né lỗi certificate có thể làm sai discovery và định tuyến.

## 7. Readiness, endpoint update và rollout

Production discovery cần loại endpoint không sẵn sàng và đưa endpoint mới vào pool theo một trình tự có kiểm soát:

1. Instance mới khởi động, bind gRPC port và kiểm tra dependency bắt buộc.
2. Readiness hoặc gRPC Health chuyển sang `SERVING`.
3. Registry/EndpointSlice công bố instance.
4. Resolver nhận snapshot mới; load balancer tạo subchannel và kết nối.
5. Khi shutdown, instance chuyển `NOT_SERVING`/`DRAINING`, được loại khỏi discovery và ngừng nhận RPC mới.
6. RPC in-flight hoàn tất trong grace period; server mới shutdown.

Resolver và client có thể nhận update chậm do DNS TTL, registry watch, cache hoặc kết nối HTTP/2 còn mở. Vì vậy readiness failure không đồng nghĩa mọi client lập tức ngừng gửi request. Cần đặt termination grace period, connection draining và retry policy phù hợp.

Local nên có test cho các chuyển trạng thái này bằng registry giả hoặc nhiều server test. Production cần quan sát propagation delay và kiểm tra rollout thực tế, không chỉ xác nhận registry đã xóa record.

## 8. Failover và hành vi khi discovery lỗi

Discovery có thể tạm thời không truy cập được trong lúc service vẫn đang chạy. Hành vi client cần được xác định:

| Tình huống | Hành vi nên thiết kế |
| --- | --- |
| DNS/registry lookup thất bại lúc khởi động | Báo lỗi rõ ràng; retry có backoff theo policy, không tạo vòng lặp nóng |
| Registry lỗi sau khi đã có endpoint hợp lệ | Quyết định có giữ snapshot gần nhất trong grace period hay chuyển sang lỗi; giới hạn tuổi dữ liệu stale |
| Không còn endpoint ready | Channel chờ/reconnect hoặc trả `UNAVAILABLE` theo policy và deadline |
| Một subchannel lỗi nhưng endpoint khác `READY` | Load balancer tiếp tục chọn endpoint sẵn sàng |
| Endpoint mới xuất hiện | Resolver phát snapshot mới; channel cập nhật subchannel |
| Một RPC trả `UNAVAILABLE` | Xử lý theo retry policy, deadline và tính idempotent; không mặc định mọi lỗi đều do discovery |

Không retry vô hạn. Retry RPC phải tôn trọng deadline và status được phép retry; operation không idempotent cần cơ chế bảo vệ để tránh thực hiện trùng. Giữ stale endpoint quá lâu có thể gửi traffic tới instance đã bị thu hồi; bỏ toàn bộ endpoint ngay khi registry chập chờn cũng có thể làm giảm availability. Chọn grace period theo SLA và đo thực tế.

## 9. Cấu hình và kiểm thử parity giữa local và production

Mục tiêu của local/test là xác minh cùng một contract discovery, không nhất thiết phải chạy nguyên hạ tầng production. Dùng cấu hình tường minh và kiểm thử các khác biệt có ảnh hưởng:

| Hạng mục | Local/test | Production |
| --- | --- | --- |
| Target | localhost, Compose service hoặc test resolver | Service FQDN hoặc registry scheme |
| Transport | Plaintext chỉ trong môi trường cô lập; test TLS nếu cần | TLS/mTLS theo policy |
| Discovery source | DNS local, fake registry, test resolver | Cluster DNS, service registry hoặc control plane |
| Endpoint count | Một hoặc vài server test | Nhiều instance/zone |
| Health | Health service giả lập trạng thái | Readiness, health Watch và registry health |
| Failure | Tắt server, đổi port, giả lập lookup lỗi | Pod rollout, zone failure, registry outage |
| Lifecycle | Đóng context/channel trong test | Graceful drain, termination grace period |

Các test quan trọng:

- **Config test:** profile local và production chọn đúng target, transport; không có fallback localhost trong production.
- **Resolver test:** target được parse đúng, DNS/registry trả endpoint đúng, snapshot add/remove hoạt động.
- **Channel integration test:** generated stub gọi được server qua target đã cấu hình.
- **TLS test:** hostname/SAN đúng thì kết nối thành công; mismatch phải thất bại.
- **Load balancing test:** nhiều endpoint `READY` được dùng theo policy đã chọn.
- **Failure test:** DNS/registry unavailable, endpoint chết, không còn endpoint ready và reconnect.
- **Rollout test:** endpoint mới được thêm, endpoint cũ drain và RPC in-flight được xử lý đúng.

Một bài test local thành công với `localhost` không chứng minh FQDN production phân giải được hoặc certificate hợp lệ. Chạy smoke test từ đúng network namespace/Pod, dùng đúng DNS và trust material như client production.

## 10. Quan sát discovery trong từng môi trường

Nên có các metric/log thống nhất để so sánh local, staging và production:

- Target scheme và service name (không ghi query chứa dữ liệu nhạy cảm).
- Số endpoint trong resolver snapshot và thời điểm cập nhật gần nhất.
- Resolver lookup success/failure, refresh count và latency.
- Số subchannel theo connectivity state.
- Load balancing policy thực tế và số RPC theo backend nếu telemetry cho phép.
- Thời gian từ readiness/registry update tới khi endpoint không còn được pick.
- RPC status, deadline và retry count theo service/method.

Tránh dùng IP, Pod UID hoặc instance ID làm metric label không giới hạn. Log có thể chứa endpoint identity đã được kiểm soát để điều tra, nhưng không ghi token, credentials hoặc toàn bộ metadata.

## 11. Bài tập vận dụng

Một client Spring gRPC chạy ở local gọi `OrderService` bằng `localhost:9090`. Khi deploy lên Kubernetes, nhóm chỉ thay port thành `8443` nhưng client không kết nối được; sau rollout, một số request vẫn tới Pod cũ.

**Yêu cầu:**

1. Thiết kế `clients.orders.target` cho local, Docker Compose và Kubernetes.
2. Giải thích vì sao `localhost` trong container không phải địa chỉ của container khác.
3. Chọn ClusterIP hay headless Service dựa trên nơi cần thực hiện load balancing; nêu tác động của kết nối HTTP/2 lâu dài.
4. Cấu hình production TLS và certificate SAN khớp service DNS.
5. Xác định readiness, endpoint update, resolver refresh và graceful drain khi rollout.
6. Viết test để xác nhận production profile không dùng plaintext hoặc localhost, DNS target phân giải đúng và client ngừng chọn endpoint cũ sau propagation.
7. Đề xuất metric để phân biệt lỗi DNS/registry, lỗi transport/TLS và lỗi RPC.

**Câu hỏi tự kiểm tra:**

- Vì sao target nên nằm trong cấu hình profile thay vì mã nguồn?
- Khi nào dùng `forAddress(...)`, khi nào dùng `forTarget(...)`?
- Vì sao `localhost` có ý nghĩa khác nhau giữa host và container?
- ClusterIP và headless Service khác nhau thế nào với gRPC load balancing?
- DNS resolver có bảo đảm client nhận endpoint mới ngay khi Pod thay đổi không?
- Vì sao TLS certificate phải khớp hostname logic dù DNS đã trả IP?
- Khi registry lỗi, giữ snapshot cũ trong bao lâu là phù hợp?
- Làm thế nào bảo đảm local test phản ánh đủ hành vi discovery của production?

**Ghi nhớ:** Local và production có thể dùng nguồn discovery khác nhau nhưng nên giữ target, resolver và channel contract rõ ràng. Tách target/transport theo profile; dùng localhost chỉ đúng trong network namespace tương ứng; hiểu ClusterIP và headless Service; bảo vệ production bằng TLS, readiness, endpoint update và graceful drain. Kiểm thử từ đúng môi trường mạng và trust configuration để phát hiện khác biệt trước khi rollout.
