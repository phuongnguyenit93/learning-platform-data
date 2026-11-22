# TTL của service record

Trong service discovery, một service record thường đại diện cho một instance cùng địa chỉ mà client có thể gọi. Nếu process crash, mất mạng hoặc không thể chủ động deregister, record có thể tiếp tục xuất hiện trong registry và khiến resolver trả về endpoint đã chết. **Time To Live (TTL)** giới hạn thời gian record được xem là còn hiệu lực nếu không được gia hạn.

Với Spring gRPC, TTL cần được phối hợp với registration, heartbeat/lease renewal, readiness và graceful shutdown. TTL là cơ chế dọn record bị bỏ quên; nó không thay thế health checking và không bảo đảm client lập tức ngừng dùng endpoint khi record hết hạn.

## 1. TTL biểu thị điều gì?

TTL là khoảng thời gian registry cho phép một registration tồn tại kể từ lần register hoặc renew hợp lệ gần nhất. Nếu không nhận được lần gia hạn trước thời điểm hết hạn, registry đánh dấu record hết hiệu lực và loại nó khỏi kết quả discovery theo semantics của registry.

Ví dụ một record có TTL 30 giây:

```text
T=0s       Register(instance-A, TTL=30s)
T=10s      Renew(instance-A)  -> expiry được đẩy về sau
T=20s      Renew(instance-A)  -> expiry được đẩy về sau
T=30s      Không có renew mới -> record vẫn còn hiệu lực nếu lần renew
                                gần nhất đã đặt expiry sau thời điểm này

Process crash sau lần renew cuối:
            Không còn heartbeat
            |
            v
            TTL hết hạn -> registry loại record
```

TTL thường được quản lý theo thời gian của registry server, không phải bằng cách client tự xóa record khi đồng hồ local chạm một mốc. Client gửi yêu cầu renew; registry xác nhận và cập nhật thời điểm hết hạn theo quy tắc của implementation.

Không nên hiểu TTL là thời gian sống của một RPC, thời gian timeout kết nối hoặc thời gian cache DNS. Đây là thời hạn hiệu lực của registration/health lease trong discovery system.

## 2. TTL, heartbeat và health là các khái niệm khác nhau

| Cơ chế | Câu hỏi được trả lời | Khi nào trạng thái thay đổi? |
| --- | --- | --- |
| TTL/lease | Registry còn coi registration là hợp lệ không? | Hết hạn nếu không renew đúng hạn |
| Heartbeat/renewal | Instance còn liên lạc được với registry để gia hạn không? | Mỗi lần renew thành công hoặc thất bại |
| Readiness | Instance có thể nhận request nghiệp vụ lúc này không? | Khi ứng dụng/dependency đổi trạng thái |
| gRPC Health `Watch` | Service báo `SERVING` hay `NOT_SERVING`? | Khi health status được cập nhật |
| Transport connectivity | Client có kết nối được tới endpoint không? | Khi subchannel kết nối, mất kết nối hoặc reconnect |

Một heartbeat thành công chỉ chứng minh tiến trình có thể gia hạn record; nó không chứng minh database, queue hoặc logic nghiệp vụ đang khỏe. Ngược lại, một service có thể vẫn xử lý request tốt nhưng tạm thời không liên lạc được với registry. Khi lease hết hạn, discovery có thể loại instance dù ứng dụng vẫn chạy.

Thiết kế nên xác định nguồn sự thật cho từng trạng thái. Ví dụ readiness điều khiển việc có nhận traffic hay không; TTL xử lý trường hợp instance không còn renew được registration; gRPC Health cho phép client hoặc hạ tầng theo dõi trạng thái phục vụ.

## 3. Chọn TTL và chu kỳ renewal

Giả sử TTL là 30 giây, một cấu hình ban đầu có thể renew khoảng mỗi 10 giây. Quy tắc `TTL / 3` là điểm khởi đầu phổ biến để có dư địa cho một vài lần lỗi, không phải giá trị bắt buộc.

Khi chọn TTL và chu kỳ heartbeat, cần tính:

- Thời gian mạng tới registry và timeout của request.
- JVM pause, GC pause, CPU starvation và scheduler delay.
- Tải registry khi có nhiều instance renew cùng lúc.
- Số lần retry có thể xảy ra trước khi TTL hết hạn.
- SLA phát hiện instance chết và thời gian chấp nhận endpoint stale.
- Độ trễ cập nhật từ registry qua resolver tới client.

| TTL | Renewal interval minh họa | Đặc điểm |
| --- | --- | --- |
| 15 giây | 5 giây | Phát hiện mất heartbeat nhanh hơn nhưng nhạy với pause/mạng chậm |
| 30 giây | 10 giây | Cân bằng ban đầu cho nhiều hệ thống |
| 60 giây | 20 giây | Có thêm dư địa nhưng record chết có thể tồn tại lâu hơn |

Đây là ví dụ để so sánh, không phải khuyến nghị cứng cho mọi registry. TTL quá ngắn làm instance khỏe bị loại nhầm khi có pause hoặc registry quá tải. TTL quá dài khiến record của process chết tồn tại lâu, kéo dài thời gian client có thể nhận endpoint stale.

Không đặt renewal interval sát TTL. Cần có safety margin đủ lớn để timeout và retry hoàn tất trước expiry. Với nhiều instance, thêm jitter để tránh tất cả heartbeat dồn vào cùng một thời điểm sau khi rollout.

## 4. Renewal phải có timeout và retry có giới hạn

Mỗi lần renew cần hoàn tất trong một thời hạn hữu hạn. Nếu call tới registry treo vô hạn, scheduler có thể ngừng renew và các instance khác cũng có thể bị ảnh hưởng nếu dùng chung executor.

Một chính sách renewal thực tế nên:

1. Gửi renew trước thời điểm hết hạn với safety margin.
2. Đặt timeout ngắn hơn khoảng thời gian còn lại của lease.
3. Khi lỗi tạm thời, retry với exponential backoff và jitter.
4. Giới hạn số lần retry để không tạo request storm.
5. Theo dõi lần renew thành công gần nhất và thời gian còn lại ước tính.
6. Nếu không thể xác nhận lease còn hiệu lực trước ngưỡng an toàn, đánh dấu instance không ready và ngừng nhận traffic mới theo policy.

Không phải mọi lỗi renew đều có cùng ý nghĩa:

| Kết quả | Diễn giải | Hành động |
| --- | --- | --- |
| Thành công | Registry xác nhận lease được gia hạn | Cập nhật thời điểm renew thành công |
| Timeout/network error | Không biết registry đã nhận renew hay chưa | Retry có giới hạn; kiểm tra lease state nếu API hỗ trợ |
| Unauthorized/forbidden | Credentials hoặc quyền registration có vấn đề | Báo lỗi cấu hình/bảo mật; không retry dày đặc |
| Lease/instance không tồn tại | Record đã hết hạn hoặc ID không còn sở hữu lease | Re-register theo quy trình có kiểm tra readiness |
| Registry unavailable | Control plane tạm thời không truy cập được | Backoff, cảnh báo và bảo vệ traffic khi lease gần hết |

Timeout không luôn đồng nghĩa renew thất bại: request có thể đã tới registry nhưng response bị mất. API registry nên hỗ trợ renew idempotent theo lease/instance identity hoặc cung cấp cách xác nhận trạng thái để client xử lý kết quả không chắc chắn.

## 5. Gắn TTL với registration trong Spring

Ứng dụng nên giữ service name, instance ID và lease identity riêng. Registry adapter che giấu API cụ thể của Consul, Eureka hoặc hệ thống nội bộ:

```java
import java.time.Duration;

public record ServiceInstance(
    String serviceName,
    String instanceId,
    String host,
    int port,
    Duration leaseTtl) {}

public interface ServiceLeaseRegistry {
    Lease register(ServiceInstance instance, Duration ttl);

    Lease renew(Lease lease, Duration ttl);

    void deregister(Lease lease);

    record Lease(
        String serviceName,
        String instanceId,
        String leaseId) {}
}
```

Ví dụ lifecycle coordinator dưới đây minh họa việc đăng ký sau readiness, renew định kỳ và deregister khi shutdown. Registry client phải đặt timeout hữu hạn cho mỗi lời gọi:

```java
import java.time.Duration;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public final class GrpcLeaseLifecycle {
    private static final Logger log =
        LoggerFactory.getLogger(GrpcLeaseLifecycle.class);

    private final ServiceLeaseRegistry registry;
    private final ServiceInstance instance;
    private final ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();
    private final AtomicBoolean stopping = new AtomicBoolean();

    private volatile ServiceLeaseRegistry.Lease lease;
    private ScheduledFuture<?> renewal;

    public GrpcLeaseLifecycle(
            ServiceLeaseRegistry registry,
            ServiceInstance instance) {
        this.registry = registry;
        this.instance = instance;
    }

    @EventListener(ApplicationReadyEvent.class)
    public synchronized void startAfterReadiness() {
        if (lease != null || stopping.get()) {
            return;
        }

        Duration ttl = instance.leaseTtl();
        lease = registry.register(instance, ttl);

        long intervalSeconds = Math.max(1, ttl.toSeconds() / 3);
        renewal = scheduler.scheduleWithFixedDelay(
            this::renewSafely,
            intervalSeconds,
            intervalSeconds,
            TimeUnit.SECONDS);
    }

    private synchronized void renewSafely() {
        ServiceLeaseRegistry.Lease current = lease;
        if (current == null || stopping.get()) {
            return;
        }

        try {
            lease = registry.renew(current, instance.leaseTtl());
        } catch (RuntimeException ex) {
            log.warn(
                "service_lease_renew_failed service={} instance={} error={}",
                instance.serviceName(),
                instance.instanceId(),
                ex.getClass().getSimpleName());
            // Production code cần theo dõi safety margin,
            // retry/backoff và chuyển readiness khi lease không còn chắc chắn.
        }
    }

    @EventListener(ContextClosedEvent.class)
    public synchronized void stopAndDeregister() {
        if (!stopping.compareAndSet(false, true)) {
            return;
        }
        if (renewal != null) {
            renewal.cancel(false);
        }
        ServiceLeaseRegistry.Lease current = lease;
        if (current != null) {
            try {
                registry.deregister(current);
            } catch (RuntimeException ex) {
                // TTL là lớp dọn dẹp dự phòng nếu deregistration thất bại.
                log.warn(
                    "service_lease_deregister_failed service={} instance={} error={}",
                    instance.serviceName(),
                    instance.instanceId(),
                    ex.getClass().getSimpleName());
            }
        }
        scheduler.shutdownNow();
    }
}
```

Đây là khung tích hợp tổng quát, không phải adapter hoàn chỉnh cho một registry cụ thể. Trong production, bổ sung timeout, backoff có jitter, xử lý lease hết hạn, trạng thái readiness khi renewal không còn chắc chắn và bảo đảm thứ tự shutdown. Nếu `ApplicationReadyEvent` xảy ra trước khi gRPC server thực sự sẵn sàng trong starter đang dùng, hãy thay bằng server-started/readiness hook phù hợp.

Không chạy tác vụ registry không giới hạn trên thread xử lý RPC. Scheduler nên dành riêng cho lease renewal hoặc dùng scheduler do ứng dụng quản lý với giới hạn tài nguyên rõ ràng. Không tạo một scheduler mới cho từng heartbeat.

## 6. Điều gì xảy ra khi TTL hết hạn?

Khi lease hết hạn, registry có thể loại record khỏi lookup/watch result. Resolver nhận snapshot mới và công bố endpoint list mới; load balancer cập nhật subchannel. Tuy nhiên, quá trình này có độ trễ:

1. Registry xác định record hết hạn.
2. Registry cập nhật dữ liệu discovery hoặc phát event.
3. Resolver nhận thay đổi hoặc thực hiện lần lookup tiếp theo.
4. Resolver phát `ResolutionResult` mới.
5. Load balancer cập nhật pool và ngừng chọn endpoint đã bị loại cho RPC mới.
6. Kết nối hiện hữu và RPC in-flight được xử lý theo connection lifecycle/graceful drain.

TTL hết hạn không lập tức đóng TCP/HTTP2 connection tại tất cả client. Client có thể giữ subchannel cũ trong một khoảng thời gian, đặc biệt khi resolver refresh chậm hoặc proxy/cache có propagation delay.

Vì vậy cần đo **thời gian từ lần renew cuối đến lúc endpoint không còn được pick**, thay vì chỉ đo thời gian registry xóa record.

## 7. TTL khác nhau giữa các discovery system

Không phải registry nào cũng biểu diễn TTL theo cùng một API:

| Hệ thống | Cách quản lý thường gặp | Lưu ý |
| --- | --- | --- |
| Consul | Service registration có thể gắn TTL check; agent/client phải cập nhật trạng thái check trước expiry | TTL check là health check có thời hạn; cần hiểu agent ownership và behavior khi check hết hạn |
| Eureka | Client gửi heartbeat định kỳ; server dùng lease/renewal và eviction policy | Các ngưỡng renewal/eviction có semantics riêng, không nhất thiết tương đương một TTL tùy ý trên mỗi record |
| Kubernetes | Service/EndpointSlice được control plane cập nhật theo Pod, readiness và endpoint lifecycle | Thường không có application-managed TTL heartbeat cho từng Service record |
| Registry nội bộ | Lease/TTL theo contract do nền tảng định nghĩa | Phải quy định expiry, renewal, ownership, idempotency và stale behavior |

Nếu dùng Consul/Eureka starter hoặc integration chính thức, ưu tiên cấu hình và lifecycle do integration quản lý. Tránh thêm một heartbeat thủ công song song làm hai cơ chế registration xung đột.

Trong Kubernetes, readiness và EndpointSlice thường là cơ chế chính để quản lý endpoint. Không thêm custom TTL registration chỉ vì service discovery có khái niệm TTL; chỉ dùng nếu kiến trúc có registry riêng và contract rõ ràng.

## 8. TTL, stale record và graceful shutdown

TTL chủ yếu xử lý trường hợp instance biến mất mà không deregister được, chẳng hạn process crash hoặc node mất kết nối. Khi shutdown bình thường, nên deregister chủ động:

1. Chuyển readiness hoặc gRPC Health sang `NOT_SERVING`/`DRAINING`.
2. Ngừng nhận RPC mới theo cơ chế server/lifecycle.
3. Deregister hoặc cập nhật record để resolver không chọn instance nữa.
4. Cho RPC in-flight hoàn tất trong grace period.
5. Shutdown server và tài nguyên.

Nếu deregister thất bại, TTL dọn record sau expiry. TTL không thay thế drain vì record có thể vẫn còn hiệu lực trong thời gian chờ hết hạn.

Khi renewal mất kết nối kéo dài, ứng dụng nên có ngưỡng an toàn: nếu không thể xác nhận lease còn hiệu lực, tự chuyển readiness sang không phục vụ hoặc ngừng công bố trạng thái `SERVING`. Khi registry phục hồi, re-register cần xác minh instance vẫn ready và sử dụng identity/lease mới nếu lease cũ đã hết.

## 9. Quan sát TTL và cảnh báo

Các metric hữu ích:

- Số registration đang active theo service.
- Số lần register, renew, renew failure và deregister.
- Thời gian renew latency và tỷ lệ timeout.
- Thời gian kể từ lần renew thành công gần nhất.
- Số lease còn gần expiry hoặc đã hết hạn.
- Số lần re-register sau lease loss.
- Thời gian propagation từ expiry tới resolver/LB cập nhật endpoint.
- Số endpoint stale còn được client chọn nếu có telemetry.

Log nên ghi service name, instance ID đã được kiểm soát, operation, outcome và error category. Không log registry token, credentials hoặc toàn bộ response chứa thông tin nhạy cảm. Tránh dùng instance ID làm metric label không giới hạn nếu số lượng Pod thay đổi liên tục.

Đặt cảnh báo khi renew failure kéo dài, tỷ lệ lease gần expiry tăng, registry latency cao hoặc nhiều instance cùng mất lease. Một đợt mất lease đồng thời có thể là sự cố registry/network chứ không phải tất cả application instance cùng chết.

## 10. Kiểm thử TTL và lease lifecycle

Không nên đợi TTL thực tế dài hàng chục giây trong mọi unit test. Dùng fake clock hoặc registry test có thể điều khiển thời gian; integration test xác minh semantics thật của registry:

| Ca kiểm thử | Thiết lập | Kết quả cần xác minh |
| --- | --- | --- |
| Register ban đầu | Instance ready, đăng ký TTL | Registry trả lease/record có expiry |
| Renew thành công | Gia hạn trước expiry | Lease được kéo dài |
| Không renew | Dừng heartbeat | Record hết hạn và bị loại khỏi discovery |
| Renew timeout | Giả lập response chậm/mất | Retry có giới hạn; xử lý kết quả không chắc chắn |
| Registry unavailable | Chặn kết nối registry | Có metric/cảnh báo; readiness xử lý theo safety margin |
| Lease đã mất | Renew bằng lease ID không còn hợp lệ | Re-register theo policy, không giả định lease cũ còn sống |
| Heartbeat jitter | Nhiều instance khởi động cùng lúc | Request renewal không dồn thành một đợt |
| Graceful shutdown | Đóng Spring context | Dừng renew và deregister đúng instance |
| Deregister thất bại | Registry không phản hồi khi shutdown | TTL cuối cùng dọn record |
| Stale endpoint | Resolver nhận record hết hạn | Snapshot mới loại endpoint; RPC mới không pick endpoint sau propagation |
| Rolling deployment | Instance mới ready trước khi instance cũ drain | Capacity được duy trì trong rollout |

Unit test dùng fake `ServiceLeaseRegistry` để xác minh register/renew/deregister và retry policy. Integration test dùng registry phù hợp để xác nhận expiry thật, sau đó gọi qua resolver/channel và kiểm tra endpoint không còn được chọn. Test cần đo cả registry expiry lẫn thời điểm client pool cập nhật vì hai thời điểm không giống nhau.

## 11. Bài tập vận dụng

`OrderService` đăng ký ba instance vào registry nội bộ với TTL 30 giây. Khi một Pod bị kill đột ngột, record của Pod đó vẫn xuất hiện và một số client tiếp tục nhận `UNAVAILABLE`.

**Yêu cầu:**

1. Giải thích vì sao record còn tồn tại sau khi process crash và TTL giải quyết tình huống đó thế nào.
2. Chọn renewal interval, timeout, retry/backoff và jitter phù hợp với TTL 30 giây; nêu safety margin.
3. Thiết kế lease identity theo `serviceName` và `instanceId`, tránh một replica xóa registration của replica khác.
4. Xử lý renewal timeout không rõ kết quả và trường hợp lease đã hết hạn.
5. Phối hợp readiness, gRPC Health, deregistration và graceful drain khi shutdown bình thường.
6. Viết test cho expiry, registry outage, heartbeat đồng loạt, stale endpoint và resolver propagation.
7. So sánh semantics TTL của registry đang dùng với Kubernetes EndpointSlice/readiness.

**Câu hỏi tự kiểm tra:**

- TTL bắt đầu hoặc được gia hạn theo xác nhận của thành phần nào?
- Vì sao heartbeat thành công không chứng minh service nghiệp vụ khỏe?
- Tại sao renewal interval không nên sát expiry?
- Timeout khi renew có chắc chắn nghĩa là registry chưa nhận request không?
- Khi lease hết hạn, vì sao client có thể vẫn còn subchannel cũ?
- TTL khác readiness và gRPC Health Watch như thế nào?
- Vì sao graceful deregistration vẫn cần dù registry có TTL?
- Khi nào cần re-register thay vì tiếp tục renew lease cũ?

**Ghi nhớ:** TTL giới hạn thời gian service record còn hiệu lực nếu instance không gia hạn lease. Chọn TTL và renewal cadence có safety margin, timeout, retry/backoff và jitter; theo dõi lease loss để không tiếp tục nhận traffic khi registration không còn chắc chắn. TTL dọn record bị bỏ quên, còn readiness/health và graceful deregistration điều khiển khả năng phục vụ. Trong Spring gRPC, gắn lease renewal với lifecycle server và kiểm thử cả expiry tại registry lẫn thời điểm resolver/load balancer ngừng chọn endpoint.
