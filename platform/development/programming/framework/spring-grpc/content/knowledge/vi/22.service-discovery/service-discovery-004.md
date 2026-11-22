# Đăng ký service trong discovery system

Một gRPC service chỉ có thể được client tìm thấy nếu hệ thống discovery biết **service nào đang chạy, gọi tới địa chỉ nào và instance còn sẵn sàng hay không**. Quá trình đưa thông tin đó vào registry được gọi là service registration. Trong Spring gRPC, registration thường gắn với vòng đời của gRPC server: đăng ký sau khi server sẵn sàng nhận traffic, duy trì trạng thái trong lúc chạy và loại instance khỏi discovery khi nó dừng hoặc bắt đầu drain.

Registration bổ sung cho resolver: registry lưu thông tin instance; resolver đọc thông tin đó và cung cấp endpoint cho gRPC channel. Bài này tập trung vào dữ liệu đăng ký, lease/heartbeat, readiness, graceful deregistration và tích hợp vòng đời Spring.

## 1. Service registration giải quyết việc gì?

Một service có thể chạy nhiều instance trên các máy hoặc Pod khác nhau. Client cần một tên logic ổn định như `orders`, trong khi IP và port của từng instance có thể thay đổi. Service registry lưu các bản ghi instance để resolver có thể tìm chúng.

```text
gRPC server instance A ─┐
gRPC server instance B ─┼── register / renew / deregister ──> Service registry
gRPC server instance C ─┘                                      |
                                                               | lookup
                                                               v
                                                        Name resolver
                                                               |
                                                               v
                                                        gRPC client channel
```

Ba thao tác cốt lõi:

- **Register:** công bố instance và endpoint của nó.
- **Renew/heartbeat:** chứng minh instance vẫn đang hoạt động và giữ registration còn hiệu lực.
- **Deregister:** chủ động loại instance khỏi danh sách có thể nhận request khi nó dừng hoặc bắt đầu drain.

Registry thường lưu nhiều instance cùng `serviceName`. Mỗi instance phải có `instanceId` riêng để một tiến trình chỉ cập nhật hoặc xóa đúng bản ghi của nó.

## 2. Thiết kế registration record

Một registration record nên đủ để client kết nối và áp dụng policy, nhưng không chứa bí mật:

| Trường | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `serviceName` | `orders` | Tên logic mà client tra cứu |
| `instanceId` | `orders-pod-7f9c` | Định danh duy nhất của instance |
| `host` | `10.20.1.17` hoặc DNS name | Địa chỉ client có thể truy cập |
| `port` | `8443` | Cổng gRPC đang lắng nghe |
| `protocol` | `grpc` | Loại endpoint |
| `version` | `2.3.1` | Phiên bản phục vụ routing/diagnostics nếu cần |
| `zone` | `ap-southeast-1a` | Vị trí để áp dụng locality policy |
| `health/readiness` | `SERVING` | Instance có được nhận traffic không |
| `leaseTtl` | `30s` | Thời hạn registration nếu không được gia hạn |
| `metadata` | `team=checkout` | Thuộc tính không nhạy cảm đã được định nghĩa |

`host` phải là địa chỉ **client thực sự truy cập được**, không phải mặc định bind address như `0.0.0.0`, `127.0.0.1` hoặc hostname chỉ phân giải được bên trong container. Nếu service đứng sau gateway, có thể đăng ký địa chỉ gateway; nếu resolver kết nối trực tiếp tới Pod, phải công bố endpoint của Pod theo network policy.

`instanceId` cần duy nhất trong phạm vi registry và ổn định trong vòng đời một tiến trình. Không dùng chung một ID cho nhiều replica vì khi một replica deregister có thể xóa nhầm bản ghi của replica khác. Không đưa token, password, private key hoặc dữ liệu cá nhân vào metadata của registration.

Ví dụ bản ghi dạng JSON:

```json
{
  "serviceName": "orders",
  "instanceId": "orders-pod-7f9c",
  "host": "10.20.1.17",
  "port": 8443,
  "protocol": "grpc",
  "version": "2.3.1",
  "zone": "ap-southeast-1a",
  "status": "SERVING",
  "leaseTtlSeconds": 30,
  "metadata": {
    "team": "checkout"
  }
}
```

Schema thực tế phụ thuộc Consul, Eureka, Kubernetes hoặc registry riêng. Hãy thống nhất trường nào là bắt buộc, trường nào chỉ là hint và cách resolver diễn giải chúng.

## 3. Đăng ký đúng thời điểm: readiness trước registration

Không nên công bố instance ngay khi process vừa khởi động nếu gRPC server chưa bind port, service dependency chưa sẵn sàng hoặc cấu hình TLS chưa hoàn tất. Nếu resolver trả endpoint quá sớm, client có thể gửi request vào instance chưa thể xử lý.

Một trình tự khởi động an toàn:

1. Spring khởi tạo cấu hình, credentials và các dependency cần thiết.
2. gRPC server bind cổng và đăng ký các service implementation.
3. Kiểm tra readiness: server đang lắng nghe, dependency bắt buộc đã sẵn sàng và instance có thể nhận loại traffic cần thiết.
4. Register instance với trạng thái `SERVING` hoặc trạng thái tương đương trong registry.
5. Bắt đầu gia hạn lease/heartbeat.

Nếu Spring gRPC starter phát sự kiện server-started/readiness riêng, hãy dùng hook đó. `ApplicationReadyEvent` của Spring Boot là một lựa chọn khi gRPC server đã được khởi động trước thời điểm ứng dụng báo ready. Với server có lifecycle bất đồng bộ hoặc starter có thứ tự khởi động riêng, phải xác nhận điều kiện này thay vì mặc định.

Registration và health checking có quan hệ nhưng không đồng nghĩa. Registry có thể biết instance tồn tại trong khi health check cho biết nó chưa phục vụ. Nếu registry hỗ trợ health check chủ động, cấu hình endpoint/probe an toàn và dùng trạng thái đó để lọc instance. Nếu dùng heartbeat, heartbeat chỉ chứng minh tiến trình còn gia hạn được lease; nó không nhất thiết chứng minh mọi dependency nghiệp vụ đều khỏe.

## 4. Lease và heartbeat

Nếu instance crash hoặc mất mạng, nó không thể gửi deregistration. Vì vậy registry thường hỗ trợ lease/TTL: bản ghi hết hạn nếu không được gia hạn trong khoảng thời gian quy định.

Ví dụ TTL là 30 giây và heartbeat chạy khoảng mỗi 10 giây:

```text
Register ── renew ── renew ── renew ── renew
   |         |        |        |        |
   +---------+--------+--------+--------+----> lease remains valid

Process crash:
Register ── renew ── X
                    |
                    +---- TTL expires ----> registry removes instance
```

Chu kỳ heartbeat thường được chọn ngắn hơn TTL với biên an toàn; ví dụ `TTL / 3` là điểm bắt đầu, không phải quy tắc bắt buộc. Cần tính đến thời gian mạng, pause của JVM, tải scheduler và thời gian registry xử lý.

Khi renewal thất bại:

- Ghi log category và metric của lỗi registry, không ghi credentials.
- Retry có giới hạn và backoff có jitter để tránh tạo bão request.
- Theo dõi thời điểm lease có thể hết hạn.
- Nếu lease đã hết, phải đăng ký lại theo chính sách và xác nhận instance còn ready.
- Không tiếp tục tự nhận mình đang discoverable khi registry đã loại bản ghi.

TTL quá ngắn làm instance biến mất khi có pause hoặc registry chậm; TTL quá dài khiến instance chết còn tồn tại lâu trong registry. Chọn TTL dựa trên SLA phát hiện lỗi và đặc tính môi trường.

## 5. Tích hợp registration với vòng đời Spring

Có thể đóng gói registry bằng một interface để phần lifecycle không phụ thuộc SDK của Consul, Eureka hoặc registry riêng:

```java
import java.time.Duration;

public interface ServiceRegistry {
    void register(ServiceInstance instance);

    void renewLease(
        String serviceName,
        String instanceId,
        Duration ttl);

    void deregister(String serviceName, String instanceId);
}
```

Ví dụ record cho instance:

```java
import java.time.Duration;
import java.util.Map;

public record ServiceInstance(
    String serviceName,
    String instanceId,
    String host,
    int port,
    String protocol,
    String version,
    Duration leaseTtl,
    Map<String, String> metadata) {
}
```

Một bean Spring Boot có thể đăng ký sau khi ứng dụng ready, gia hạn lease định kỳ và deregister khi context đóng:

```java
import java.util.concurrent.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public final class GrpcServiceRegistration {
    private static final Logger log =
        LoggerFactory.getLogger(GrpcServiceRegistration.class);

    private final ServiceRegistry registry;
    private final ServiceInstance instance;
    private final ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor(r -> {
            Thread thread = new Thread(r, "grpc-service-lease");
            thread.setDaemon(true);
            return thread;
        });

    private volatile boolean registered;
    private ScheduledFuture<?> renewalTask;

    public GrpcServiceRegistration(
            ServiceRegistry registry,
            ServiceInstance instance) {
        this.registry = registry;
        this.instance = instance;
    }

    @EventListener(ApplicationReadyEvent.class)
    public synchronized void onApplicationReady() {
        if (registered) {
            return;
        }

        // Chỉ chạy khi gRPC server đã sẵn sàng nhận traffic.
        registry.register(instance);
        registered = true;

        long ttlSeconds = instance.leaseTtl().toSeconds();
        long intervalSeconds = Math.max(1, ttlSeconds / 3);
        renewalTask = scheduler.scheduleAtFixedRate(
            this::renewSafely,
            intervalSeconds,
            intervalSeconds,
            TimeUnit.SECONDS);
    }

    private void renewSafely() {
        if (!registered) {
            return;
        }
        try {
            registry.renewLease(
                instance.serviceName(),
                instance.instanceId(),
                instance.leaseTtl());
        } catch (RuntimeException ex) {
            // Không log token, request headers hoặc toàn bộ registry response.
            log.warn(
                "grpc_service_lease_renewal_failed service={} instance={} error={}",
                instance.serviceName(),
                instance.instanceId(),
                ex.getClass().getSimpleName());
        }
    }

    @EventListener(ContextClosedEvent.class)
    public synchronized void onContextClosed() {
        if (renewalTask != null) {
            renewalTask.cancel(false);
        }
        if (registered) {
            try {
                registry.deregister(
                    instance.serviceName(),
                    instance.instanceId());
            } catch (RuntimeException ex) {
                // TTL là lớp dọn dẹp dự phòng nếu deregistration thất bại.
                log.warn(
                    "grpc_service_deregistration_failed service={} instance={} error={}",
                    instance.serviceName(),
                    instance.instanceId(),
                    ex.getClass().getSimpleName());
            } finally {
                registered = false;
            }
        }
        scheduler.shutdownNow();
    }
}
```

Đây là ví dụ tích hợp tổng quát; `ServiceRegistry` và `ServiceInstance` cần được cung cấp bằng bean phù hợp. Các lời gọi registry phải có timeout hữu hạn. Nếu starter gRPC khởi động server sau `ApplicationReadyEvent`, hãy thay event hook bằng server-started hook hoặc lifecycle phase bảo đảm registration chỉ diễn ra sau khi listener đã mở.

Khi ứng dụng đóng, `ContextClosedEvent` được phát trước giai đoạn hủy bean; tuy nhiên, thứ tự dừng các thành phần server còn phụ thuộc starter và lifecycle configuration. Hãy bảo đảm deregistration xảy ra trước khi server ngừng nhận kết nối. Với hệ thống cần drain có kiểm soát, dùng lifecycle coordinator để điều phối thứ tự rõ ràng.

## 6. Graceful deregistration và connection draining

Deregister không tự đóng những kết nối mà client đã tạo. Một số channel có thể vẫn giữ subchannel hoặc endpoint cũ trong thời gian resolver refresh và load balancer cập nhật.

Trình tự shutdown nên được thiết kế:

1. Đánh dấu instance `DRAINING` hoặc không còn ready để registry/resolver ngừng chọn nó.
2. Ngừng nhận RPC mới theo cơ chế server/starter hỗ trợ.
3. Cho RPC đang chạy hoàn tất trong khoảng grace period.
4. Đóng gRPC server và giải phóng tài nguyên.
5. Nếu deregistration không thực hiện được, lease TTL giúp registry dọn bản ghi sau thời hạn.

Thời gian drain phải hữu hạn. Khi hết grace period, hủy các call còn lại theo chính sách và ghi nhận số call bị gián đoạn. Không giữ instance ở trạng thái `SERVING` trong khi server đã dừng nhận request.

Đối với rolling deployment, cần để instance mới ready và đăng ký trước khi loại instance cũ nếu muốn duy trì capacity. Cấu hình readiness, registry propagation, resolver refresh và termination grace period phải phối hợp với nhau.

## 7. Registry nào chịu trách nhiệm đăng ký?

Không phải mọi nền tảng đều cần ứng dụng tự gọi registry API:

| Nền tảng | Cách registration thường dùng | Điều cần chú ý |
| --- | --- | --- |
| Consul | Agent/API đăng ký service và health check, có thể dùng TTL check | ID duy nhất, TTL renewal, deregistration |
| Eureka | Client integration đăng ký instance và gửi heartbeat | Lease/renewal và eviction theo cấu hình |
| Kubernetes | Khai báo `Service`, `Deployment` labels và readiness; control plane quản lý EndpointSlice | Thường không cần application tự đăng ký từng Pod qua registry API |
| Registry nội bộ | SDK/API riêng hoặc adapter của ứng dụng | Contract, auth, timeout, retry và lifecycle phải được định nghĩa |

Trong Kubernetes, một `Service` chọn Pod bằng label selector; EndpointSlice được control plane cập nhật theo Pod/Service readiness. Với gRPC client dùng DNS, tên Service là endpoint ổn định. Nếu cần client-side discovery từng Pod, headless Service có thể công bố Pod addresses theo cấu hình. Không triển khai thêm registration client vào registry riêng nếu Kubernetes Service đã đáp ứng yêu cầu, trừ khi kiến trúc có lý do rõ ràng.

Với Consul/Eureka starter, ưu tiên integration chính thức của phiên bản đang dùng để tránh tự tạo một registration song song. Chỉ viết adapter thủ công khi cần kiểm soát lifecycle hoặc schema mà integration sẵn có không đáp ứng.

## 8. Bảo mật và tính đúng đắn của registration

Registry là nguồn dữ liệu ảnh hưởng trực tiếp nơi client gửi traffic. Một bản ghi giả hoặc endpoint bị chiếm quyền có thể chuyển request tới server không đáng tin.

- Xác thực service khi ghi registry; dùng TLS/mTLS nếu nền tảng hỗ trợ.
- Giới hạn quyền: instance chỉ được đăng ký hoặc xóa đúng service/instance mà nó sở hữu.
- Kiểm tra host, port, protocol, service name và metadata trước khi publish.
- Không công bố endpoint quản trị hoặc port nội bộ không dành cho client.
- Không đưa credentials, token hoặc private key vào registration metadata.
- Ràng buộc certificate SAN/TLS authority với tên dịch vụ mà client sử dụng.
- Dùng instance ID duy nhất và thao tác deregister có tính idempotent.
- Hạn chế quyền đọc registry nếu metadata có thông tin topology nhạy cảm.

Đừng coi trạng thái `SERVING` do instance tự khai là bằng chứng độc lập rằng server khỏe. Có thể kết hợp active health check từ registry, gRPC health service hoặc readiness probe của nền tảng.

## 9. Kiểm thử service registration

Kiểm thử cần xác minh không chỉ registry API được gọi mà còn endpoint có phản ánh đúng trạng thái gRPC server.

| Ca kiểm thử | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Khởi động thành công | Server đã bind và ready | Instance được register với host/port chính xác |
| Server chưa ready | Dependency bắt buộc chưa sẵn sàng | Instance chưa được công bố `SERVING` |
| Hai replica cùng service | Instance ID khác nhau | Registry giữ cả hai bản ghi |
| Heartbeat thành công | Lease còn hiệu lực | TTL được gia hạn |
| Heartbeat lỗi | Registry tạm unavailable | Có metric/log an toàn; retry có giới hạn |
| Lease hết hạn | Process mất khả năng renew | Registry loại instance theo TTL |
| Graceful shutdown | Đóng Spring context | Instance được deregister trước khi server dừng |
| Deregistration lỗi | Registry không phản hồi | Lease hết hạn làm lớp dọn dẹp dự phòng |
| Rolling deployment | Instance mới ready trước khi instance cũ drain | Không mất toàn bộ capacity |
| Host/TLS sai | Đăng ký hostname không khớp certificate hoặc địa chỉ không reachable | Validation/test phát hiện trước production |
| Kubernetes Service | Pod readiness thay đổi | EndpointSlice/DNS phản ánh trạng thái theo cấu hình cluster |

Unit test dùng fake `ServiceRegistry` để xác minh register/renew/deregister và tính idempotent. Integration test dùng registry test hoặc container phù hợp, sau đó tạo gRPC client qua resolver để gọi endpoint đã đăng ký. Kiểm tra thêm crash/TTL và rolling update trong môi trường gần production; mock registry không chứng minh propagation delay thực tế.

## 10. Bài tập vận dụng

`OrderService` chạy ba instance và đăng ký vào registry nội bộ. Client gRPC tra cứu service name `orders`, nhưng sau rollout đôi lúc vẫn gọi một instance đã dừng.

**Yêu cầu:**

1. Thiết kế registration record gồm service name, instance ID, host, gRPC port, protocol, version, zone, readiness và lease TTL.
2. Xác định thời điểm register sau khi gRPC server sẵn sàng; không công bố endpoint chưa listen.
3. Thiết kế heartbeat/lease renewal với timeout và backoff; giải thích registry xử lý instance crash như thế nào.
4. Xây dựng graceful deregistration, connection draining và rolling deployment để tránh nhận request mới trên instance cũ.
5. Tích hợp registration với lifecycle Spring; xác định hook khởi động và shutdown theo starter thực tế.
6. Viết test cho nhiều replica, lease expiry, registry outage, deregistration failure và resolver nhận endpoint mới.
7. Nếu chạy trên Kubernetes, so sánh việc dùng Service/EndpointSlice với tự đăng ký từng Pod vào registry riêng.

**Câu hỏi tự kiểm tra:**

- Registration record cần những trường nào để resolver tạo endpoint?
- Vì sao `serviceName` và `instanceId` phải là hai giá trị riêng?
- Heartbeat khác health check ở điểm nào?
- Vì sao chỉ đăng ký sau readiness?
- Deregister có lập tức xóa mọi subchannel ở client không?
- TTL giúp xử lý trường hợp process crash ra sao?
- Khi nào Kubernetes Service đã đủ và không cần custom registration client?
- Vì sao registry credentials không được đặt trong instance metadata?

**Ghi nhớ:** Service registration công bố một instance gRPC có thể được tìm thấy ở đâu và trong trạng thái nào. Đăng ký sau readiness, dùng instance ID riêng, gia hạn lease có giới hạn, deregister trước khi server dừng nhận traffic và để TTL dọn bản ghi khi process crash. Trong Spring gRPC, gắn registration với lifecycle server, bảo vệ registry bằng xác thực và kiểm thử cả startup, renewal, drain, shutdown lẫn endpoint propagation.
