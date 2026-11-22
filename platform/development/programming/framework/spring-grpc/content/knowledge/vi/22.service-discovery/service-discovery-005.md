# Cập nhật danh sách endpoint

Trong service discovery, danh sách endpoint của một gRPC service thay đổi theo vòng đời instance: Pod mới xuất hiện, instance cũ bị drain, địa chỉ IP đổi hoặc registry đánh dấu endpoint không còn phục vụ. Client cần nhận những thay đổi đó mà không phải tạo lại channel cho từng lần cập nhật.

Với grpc-java, **NameResolver công bố snapshot endpoint mới cho channel** bằng `ResolutionResult`. Load balancer nhận snapshot, cập nhật subchannel và quyết định endpoint nào được dùng cho RPC tiếp theo. Resolver chịu trách nhiệm theo dõi nguồn discovery và phát dữ liệu mới; nó không tự quản lý kết nối hoặc phân phối từng request.

## 1. Endpoint list là snapshot của trạng thái discovery

Một endpoint thường gồm địa chỉ host/port và có thể kèm attributes như zone hoặc thông tin định tuyến không nhạy cảm. Resolver chuyển chúng thành `EquivalentAddressGroup` rồi đưa vào `ResolutionResult`.

Ví dụ registry trả về:

```text
Snapshot revision 41:
  orders-1 -> 10.20.1.11:8443
  orders-2 -> 10.20.1.12:8443

Snapshot revision 42:
  orders-2 -> 10.20.1.12:8443
  orders-3 -> 10.20.1.13:8443
```

Ở revision 42, endpoint `orders-1` đã bị loại và `orders-3` được thêm. `orders-2` vẫn tồn tại. Resolver nên phát **toàn bộ snapshot hiện tại**, không chỉ gửi phần thay đổi, để channel có thể tính trạng thái endpoint mới nhất một cách nhất quán.

| Thay đổi trong registry | Hành động của resolver |
| --- | --- |
| Thêm instance | Đưa endpoint mới vào snapshot |
| Xóa instance | Loại endpoint khỏi snapshot tiếp theo |
| Host/port thay đổi | Thay endpoint cũ bằng địa chỉ mới |
| Attributes thay đổi | Phát snapshot với attributes mới |
| Endpoint không còn ready | Loại khỏi tập endpoint được phép nhận traffic hoặc đánh dấu theo policy |
| Không còn endpoint hợp lệ | Báo trạng thái discovery không có endpoint theo policy; không giữ danh sách cũ vô hạn |

Endpoint cần có định danh ổn định, chẳng hạn `instanceId`, để phân biệt một instance với instance khác khi địa chỉ thay đổi. Không dùng riêng index trong danh sách vì thứ tự DNS/registry có thể thay đổi giữa hai lần đọc.

## 2. Ai nhận và áp dụng endpoint update?

Luồng cập nhật có ba phần:

```text
Service registry / DNS watch
          |
          | snapshot revision 42
          v
Custom NameResolver
          |
          | listener.onResult(ResolutionResult)
          v
gRPC ManagedChannel
          |
          v
LoadBalancer
    |             |
    v             v
Subchannel A    Subchannel B
    |             |
    +---- RPC pick / connection lifecycle
```

- Registry hoặc DNS là nguồn dữ liệu về endpoint.
- Resolver phát kết quả phân giải mới cho channel.
- Load balancer so sánh kết quả mới với trạng thái hiện tại, tạo hoặc loại subchannel và chọn kết nối theo policy.

Resolver không nên tự mở socket tới từng endpoint, tự round-robin từng RPC hoặc đóng subchannel của load balancer. Các thao tác đó thuộc trách nhiệm channel/load balancer.

## 3. Phát snapshot mới bằng NameResolver.Listener2

Khi resolver nhận được danh sách endpoint mới, nó chuyển dữ liệu thành `EquivalentAddressGroup` và gọi `listener.onResult(...)`. Mỗi lần gọi mang snapshot đầy đủ:

```java
import io.grpc.EquivalentAddressGroup;
import io.grpc.NameResolver;
import java.net.InetSocketAddress;
import java.util.ArrayList;
import java.util.List;

void publishSnapshot(
        NameResolver.Listener2 listener,
        List<InetSocketAddress> endpoints) {

    List<EquivalentAddressGroup> groups = new ArrayList<>();
    for (InetSocketAddress endpoint : endpoints) {
        groups.add(new EquivalentAddressGroup(endpoint));
    }

    NameResolver.ResolutionResult result =
        NameResolver.ResolutionResult.newBuilder()
            .setAddresses(groups)
            .build();

    listener.onResult(result);
}
```

Đoạn code minh họa phần chuyển đổi. Resolver thực tế cần validate host/port trước khi tạo `InetSocketAddress`, loại endpoint trùng theo identity, giữ attributes cần thiết và bảo đảm callback chạy trong `SynchronizationContext` của gRPC.

Không gửi delta kiểu “thêm endpoint X” hoặc “xóa endpoint Y” như thể listener là một event bus. `onResult(...)` thay thế kết quả phân giải hiện tại bằng một kết quả mới; vì vậy snapshot phải chứa tất cả endpoint còn hợp lệ.

## 4. Theo dõi thay đổi: watch hoặc polling

Có hai cách phổ biến để biết registry thay đổi:

| Cách | Cơ chế | Ưu điểm | Điểm cần quản lý |
| --- | --- | --- | --- |
| Watch/subscribe | Registry đẩy event hoặc stream thay đổi | Độ trễ cập nhật thấp, giảm polling | Reconnect, event ordering, resync sau mất kết nối |
| Polling | Resolver truy vấn snapshot theo chu kỳ | Đơn giản, dễ phục hồi bằng lần đọc tiếp theo | Tần suất truy vấn, độ trễ phát hiện, jitter và tải registry |

Với watch, không nên chỉ áp dụng từng event mãi mãi. Sau khi mất kết nối hoặc phát hiện revision bị nhảy, resolver nên tải lại snapshot đầy đủ để đồng bộ. Với polling, nên có timeout, backoff khi lỗi và jitter để nhiều client không cùng truy vấn registry vào một thời điểm.

Một chiến lược kết hợp là dùng watch để cập nhật nhanh và định kỳ resync snapshot để sửa sai lệch. Cần giới hạn số watcher theo channel/service và đóng subscription khi resolver shutdown.

## 5. Cập nhật nguyên tử và bỏ kết quả cũ

Lookup bất đồng bộ có thể hoàn tất sai thứ tự. Ví dụ lần đọc revision 42 chậm hơn lần đọc revision 43; nếu resolver phát revision 42 sau revision 43, channel có thể quay lại endpoint cũ.

Nên gắn mỗi snapshot một revision hoặc sequence tăng đơn điệu:

```java
import java.util.concurrent.atomic.AtomicLong;
import io.grpc.SynchronizationContext;

final class EndpointUpdateGate {
    private final AtomicLong latestRevision = new AtomicLong(-1);
    private final SynchronizationContext syncContext;

    EndpointUpdateGate(SynchronizationContext syncContext) {
        this.syncContext = syncContext;
    }

    void accept(long revision, Runnable publish) {
        syncContext.execute(() -> {
            long current = latestRevision.get();
            if (revision <= current) {
                return; // Bỏ snapshot cũ hoặc lặp.
            }
            latestRevision.set(revision);
            publish.run();
        });
    }
}
```

Đây là khung minh họa; trong resolver thật, `publish` phải phát snapshot đã validate qua listener và cùng một synchronization context. Nếu registry không có revision, có thể dùng generation counter cục bộ để bỏ kết quả lookup cũ do resolver tự khởi tạo. Generation counter chỉ sắp thứ tự các yêu cầu của client; nó không thay thế revision có thẩm quyền của registry khi nhiều nguồn ghi cùng lúc.

Không cập nhật một collection dùng chung theo kiểu xóa hết rồi thêm từng endpoint trong khi callback khác có thể đọc. Hãy tạo snapshot immutable mới, validate đầy đủ, rồi công bố một lần. Channel sẽ thấy trạng thái trước hoặc sau cập nhật, không thấy danh sách ở giữa quá trình.

## 6. Xử lý add, remove và thay đổi địa chỉ

Resolver có thể so sánh snapshot mới với snapshot trước để đo thay đổi, log số lượng hoặc phát metric:

| Endpoint | Snapshot cũ | Snapshot mới | Diễn giải |
| --- | --- | --- | --- |
| `orders-1` | `10.20.1.11:8443` | Không có | Bị loại khỏi discovery |
| `orders-2` | `10.20.1.12:8443` | `10.20.1.12:8443` | Không đổi |
| `orders-3` | Không có | `10.20.1.13:8443` | Endpoint mới |
| `orders-4` | `10.20.1.14:8443` | `10.20.1.24:8443` | Địa chỉ thay đổi |

Identity nên dựa vào `instanceId` hoặc khóa do registry cung cấp. Khi host/port thay đổi, resolver phát endpoint mới cho cùng identity; load balancer có thể phải tạo subchannel mới và loại subchannel cũ.

Không giữ endpoint đã bị registry thu hồi chỉ vì nó từng hoạt động. Nếu cần stale cache để chịu lỗi registry, phải có giới hạn tuổi, lý do và policy rõ ràng. Endpoint stale có thể gửi request tới instance đã chết hoặc đã được tái sử dụng cho workload khác.

## 7. Empty result và lỗi discovery

Không có endpoint hợp lệ là một trạng thái cần xử lý có chủ đích:

- Nếu registry trả snapshot rỗng hợp lệ, resolver có thể phát kết quả rỗng nếu load balancer/policy của phiên bản hỗ trợ và ứng dụng muốn channel chuyển sang trạng thái không có endpoint; hoặc báo `UNAVAILABLE` theo contract discovery.
- Nếu registry request thất bại tạm thời, gọi `listener.onError(Status.UNAVAILABLE...)` và thực hiện retry/backoff theo policy.
- Nếu target sai cấu trúc hoặc service key không hợp lệ, báo lỗi cấu hình sớm; không retry vô hạn.
- Nếu snapshot mới không hợp lệ, không công bố một phần snapshot. Giữ trạng thái hợp lệ trước đó chỉ trong khoảng grace period đã định nghĩa, hoặc báo lỗi theo policy.

Không có một lựa chọn duy nhất cho mọi registry. Quan trọng là phân biệt “không có instance”, “không truy cập được registry” và “target cấu hình sai”. Metrics và log cần thể hiện đúng category mà không ghi credential hay toàn bộ response registry.

## 8. Load balancer cập nhật subchannel ra sao?

Khi nhận `ResolutionResult` mới, load balancer sử dụng danh sách `EquivalentAddressGroup` để cập nhật subchannel:

- Endpoint mới có thể tạo subchannel mới và bắt đầu kết nối.
- Endpoint không còn trong snapshot có thể bị loại khỏi tập được chọn cho RPC mới.
- Endpoint còn tồn tại có thể giữ subchannel hiện tại nếu identity/address tương ứng.
- Endpoint đổi địa chỉ có thể cần subchannel mới.

Việc xóa endpoint khỏi snapshot không đồng nghĩa mọi RPC đang chạy trên kết nối đó lập tức bị hủy. RPC in-flight có thể hoàn tất theo connection lifecycle; server có thể tiếp tục drain. Retry hoặc chuyển sang endpoint khác phụ thuộc retry policy, status và tính idempotent của RPC.

Đây là lý do cần phối hợp discovery update với graceful deregistration:

1. Instance chuyển sang `DRAINING` hoặc không còn được publish là ready.
2. Registry phát snapshot loại instance khỏi endpoint list.
3. Resolver chuyển snapshot mới tới channel.
4. Load balancer ngừng chọn endpoint đó cho RPC mới và cập nhật subchannel.
5. Server chờ RPC đang chạy hoàn tất trong grace period rồi shutdown.

Resolver chỉ công bố membership/attributes. Nó không tự bảo đảm instance đã ngừng nhận traffic ở mọi client ngay tức thì; có propagation delay, cache và kết nối đang mở.

## 9. Tích hợp cập nhật endpoint trong Spring gRPC

Trong Spring, channel thường là bean sống lâu và được nhiều stub/call dùng chung. Khi resolver phát snapshot mới, channel tự cập nhật theo cơ chế grpc-java; ứng dụng không nên tạo lại channel cho mỗi lần registry đổi endpoint.

Ví dụ cấu hình channel với custom target:

```java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrdersClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel ordersChannel() {
        return ManagedChannelBuilder
            .forTarget("catalog:///orders")
            .useTransportSecurity()
            .build();
    }
}
```

Provider cho scheme `catalog` và resolver theo dõi registry phải được đăng ký trước khi channel phân giải target. Nếu starter Spring gRPC quản lý channel, cấu hình target và resolver theo extension point của phiên bản starter; giữ một channel dài hạn và để resolver cập nhật kết quả.

Không thay target URI bằng IP mới mỗi lần có event. Làm như vậy buộc ứng dụng tự quản lý việc tạo/đóng channel, stub và call đang chạy, dễ gây rò tài nguyên hoặc gián đoạn request.

## 10. Quan sát và kiểm thử endpoint update

Nên theo dõi các chỉ số giúp xác định resolver có cập nhật đúng và nhanh hay không:

- Số endpoint trong snapshot hiện tại.
- Thời gian từ registry revision/event đến lúc resolver publish.
- Số lần add/remove/change endpoint.
- Số lần refresh, lookup failure và reconnect watch.
- Tuổi snapshot hiện tại và thời điểm thành công gần nhất.
- Số subchannel đang kết nối hoặc ở trạng thái lỗi nếu load balancer cung cấp telemetry.

Không dùng IP, instance ID hoặc hostname từng endpoint làm metric label không giới hạn; cardinality có thể tăng nhanh khi instance thay đổi. Có thể ghi các ID cần thiết vào log có kiểm soát, nhưng tránh credentials và thông tin nhạy cảm.

| Ca kiểm thử | Kịch bản | Kết quả cần xác minh |
| --- | --- | --- |
| Initial snapshot | Registry trả hai endpoint | Resolver publish đủ hai endpoint |
| Add endpoint | Registry thêm instance thứ ba | Snapshot mới chứa cả ba |
| Remove endpoint | Registry loại instance đã drain | Snapshot mới không còn instance đó |
| Address change | Host/port của instance đổi | Snapshot mới chứa địa chỉ mới |
| Out-of-order result | Revision 43 đến trước revision 42 | Revision 42 bị bỏ qua |
| Duplicate event | Cùng revision được phát hai lần | Không tạo update churn |
| Watch reconnect | Mất kết nối rồi reconnect | Resolver tải lại snapshot đầy đủ |
| Empty result | Không còn endpoint ready | Channel chuyển sang trạng thái theo policy đã định nghĩa |
| Registry unavailable | Lookup timeout hoặc lỗi | Báo lỗi, retry/backoff có giới hạn |
| Resolver shutdown | Channel đóng khi watch đang hoạt động | Subscription/executor được dừng, callback muộn bị bỏ qua |
| In-flight RPC | Endpoint bị remove khi call đang chạy | Hành vi drain/cancel đúng policy, không giả định mọi call tự retry |

Unit test dùng fake registry để phát snapshot có revision được kiểm soát. Integration test có thể khởi chạy hai gRPC server trên port động, cho resolver trả endpoint thứ nhất, sau đó cập nhật snapshot sang endpoint thứ hai và xác minh RPC mới được gửi tới endpoint mới. Thêm test cho RPC đang chạy trong lúc update để xác nhận behavior drain.

Test in-process hữu ích cho logic resolver nhưng không kiểm tra kết nối TCP/TLS thực. Khi cần xác minh TLS authority, proxy, DNS cache hoặc connection draining, chạy test với transport và hạ tầng tương ứng.

## 11. Bài tập vận dụng

`OrderService` chạy nhiều instance. Custom resolver hiện chỉ đọc registry một lần khi channel khởi tạo, vì vậy Pod mới không được client sử dụng và Pod cũ đôi khi vẫn nhận request sau khi bắt đầu shutdown.

**Yêu cầu:**

1. Thiết kế snapshot có revision và endpoint identity ổn định.
2. Bổ sung watch hoặc polling để nhận thay đổi từ registry.
3. Phát toàn bộ `ResolutionResult` mới sau khi validate; không gửi delta hoặc sửa collection dùng chung từng phần.
4. Bỏ snapshot cũ đến muộn, xử lý duplicate event và resync sau reconnect.
5. Phối hợp remove endpoint với `DRAINING`, load balancer subchannel update và server graceful shutdown.
6. Viết test cho add/remove/address change, empty result, registry outage, out-of-order revision và in-flight RPC.

**Câu hỏi tự kiểm tra:**

- Vì sao `onResult(...)` cần nhận snapshot đầy đủ?
- Resolver và load balancer chia trách nhiệm cập nhật endpoint thế nào?
- Vì sao revision giúp ngăn kết quả lookup cũ ghi đè trạng thái mới?
- Khi endpoint bị remove, điều gì xảy ra với RPC đang chạy?
- Vì sao watch cần resync snapshot sau reconnect?
- Khi nào nên báo `UNAVAILABLE` và khi nào xử lý empty result theo policy?
- Vì sao Spring gRPC nên giữ channel dài hạn thay vì tạo lại channel mỗi lần endpoint thay đổi?

**Ghi nhớ:** Cập nhật danh sách endpoint là quá trình phát snapshot discovery mới cho gRPC channel. Resolver theo dõi registry, validate và công bố toàn bộ `ResolutionResult`; load balancer cập nhật subchannel và lựa chọn endpoint cho RPC mới. Dùng revision để bỏ kết quả cũ, cập nhật snapshot nguyên tử, xử lý empty/error có policy và phối hợp deregistration với graceful draining. Trong Spring gRPC, giữ channel ổn định và kiểm thử cả endpoint update lẫn RPC đang chạy.
