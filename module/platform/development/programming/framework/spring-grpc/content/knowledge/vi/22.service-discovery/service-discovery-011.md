# Fallback khi discovery không sẵn sàng

Service discovery có thể tạm thời không truy cập được vì DNS lỗi, registry quá tải, control plane mất kết nối hoặc watch stream bị gián đoạn. Khi đó gRPC client cần một chính sách rõ ràng để tiếp tục dùng endpoint đã biết, chuyển sang nguồn discovery dự phòng hoặc dừng an toàn.

Trong Spring gRPC, fallback phải nằm đúng ở lớp gặp sự cố. **Resolver xử lý việc tìm endpoint; load balancer chọn kết nối; retry policy xử lý lần gọi RPC thất bại.** Một lỗi DNS không giống một kết nối TCP thất bại, và cả hai đều khác lỗi nghiệp vụ từ server. Bài này tập trung vào fallback của discovery, giới hạn dữ liệu cũ và cách bảo đảm fallback không làm client gọi nhầm service.

## 1. Xác định discovery không sẵn sàng

Discovery unavailable là trạng thái client không thể lấy hoặc làm mới danh sách endpoint từ nguồn discovery trong thời gian cần thiết. Những nguyên nhân thường gặp:

- DNS resolver timeout, SERVFAIL hoặc không truy cập được DNS server.
- Service registry tạm unavailable hoặc trả lỗi 5xx.
- Watch/subscribe bị ngắt và chưa thể reconnect.
- Network policy, proxy hoặc firewall chặn đường tới registry.
- Registry authentication hết hạn hoặc quyền truy cập bị thu hồi.
- Target URI sai, service name không tồn tại hoặc cấu hình sai.

Không phải mọi lỗi đều nên kích hoạt cùng một fallback:

| Lỗi | Phân loại | Hướng xử lý |
| --- | --- | --- |
| Registry timeout, connection reset, 5xx | Có thể tạm thời | Retry có giới hạn; dùng last-known-good nếu còn hợp lệ |
| DNS SERVFAIL hoặc timeout | Có thể tạm thời | Thử lại theo backoff; dùng nguồn dự phòng đã cấu hình |
| DNS NXDOMAIN | Có thể là sai tên hoặc record chưa được publish | Xác minh target; chỉ dùng fallback nếu đây là tình huống dự kiến |
| Target URI sai cấu trúc | Lỗi cấu hình | Fail fast; không thử endpoint tùy tiện |
| Registry 401/403 | Lỗi xác thực/phân quyền | Fail closed và sửa credentials/quyền; không che lỗi bằng fallback |
| TLS certificate/hostname mismatch | Lỗi bảo mật hoặc cấu hình | Dừng kết nối; không chuyển plaintext hoặc bỏ xác minh |
| Endpoint connection refused | Lỗi transport tới backend | Load balancer/reconnect hoặc discovery cập nhật endpoint; không coi đó tự động là lỗi registry |
| RPC trả `UNAVAILABLE` | Lỗi ở tầng call, transport hoặc server | Phân tích status và nguồn phát sinh; áp dụng RPC retry nếu an toàn |

Phân loại đúng lỗi giúp tránh trường hợp một cấu hình sai bị che giấu nhiều ngày bởi endpoint cache.

## 2. Các chiến lược fallback

Không có một chiến lược phù hợp cho mọi hệ thống. Chọn dựa trên SLA, mức độ nhạy cảm của dữ liệu và độ tin cậy của nguồn thay thế:

| Chiến lược | Cách hoạt động | Rủi ro/chú ý |
| --- | --- | --- |
| Last-known-good snapshot | Dùng snapshot endpoint gần nhất đã phân giải thành công trong một khoảng tuổi tối đa | Endpoint cũ có thể đã chết, bị thu hồi hoặc IP được tái sử dụng |
| Static/bootstrap endpoint | Dùng địa chỉ dự phòng được cấu hình rõ ràng | Có thể tạo điểm lỗi đơn hoặc đi tới môi trường sai |
| Alternate discovery source | Chuyển từ registry chính sang DNS/registry dự phòng | Hai nguồn có thể khác dữ liệu, revision hoặc trạng thái readiness |
| Stable gateway/proxy | Kết nối tới một endpoint ổn định; gateway chịu trách nhiệm tìm backend | Gateway trở thành dependency quan trọng và cần HA |
| Fail closed | Không có dữ liệu discovery hợp lệ thì không gửi RPC | Giảm availability nhưng tránh gọi nhầm hoặc vi phạm policy |

Có thể kết hợp các chiến lược theo thứ tự, ví dụ registry chính → snapshot gần nhất còn mới → gateway dự phòng. Thứ tự và điều kiện chuyển đổi phải được cấu hình rõ, không nên suy ra từ exception message.

## 3. Last-known-good snapshot có giới hạn tuổi

Resolver có thể giữ snapshot cuối cùng đã phân giải thành công. Khi lần lookup mới thất bại, snapshot đó chỉ được dùng nếu vẫn nằm trong giới hạn tuổi `maxStale`.

Ví dụ:

```text
T=00s  Registry trả revision 120: A, B, C
       Resolver lưu last-known-good snapshot

T=10s  Registry timeout
       Snapshot age = 10s; maxStale = 60s
       -> Có thể tiếp tục dùng A, B, C

T=70s  Registry vẫn unavailable
       Snapshot age > maxStale
       -> Ngừng dùng snapshot cũ; báo discovery unavailable
```

Snapshot phải lưu ít nhất:

- Danh sách endpoint đã validate.
- Revision/version từ registry nếu nguồn có cung cấp.
- Thời điểm lookup thành công.
- Service identity và môi trường mà snapshot thuộc về.
- Attributes cần thiết cho load balancing, nếu có.

Không chia sẻ snapshot giữa hai service name, tenant, region hoặc môi trường chỉ vì chúng có cùng port. Snapshot `orders` ở staging không được dùng làm fallback cho `orders` ở production.

`maxStale` là giới hạn chính sách, không phải TTL của registry. Nó cần ngắn hơn khoảng thời gian mà endpoint cũ có thể bị tái sử dụng hoặc trở nên không an toàn. Nếu registry trả lease expiry hoặc endpoint validity, không giữ endpoint vượt quá thời hạn đó.

## 4. Ví dụ lưu và kiểm tra last-known-good

Một store nhỏ có thể giữ snapshot immutable trong bộ nhớ tiến trình:

```java
import java.net.InetSocketAddress;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

record EndpointSnapshot(
    String serviceName,
    String environment,
    long revision,
    List<InetSocketAddress> addresses,
    Instant fetchedAt) {

    EndpointSnapshot {
        addresses = List.copyOf(addresses);
    }
}

final class LastKnownGoodStore {
    private final AtomicReference<EndpointSnapshot> current =
        new AtomicReference<>();

    void update(EndpointSnapshot snapshot) {
        current.set(snapshot);
    }

    Optional<EndpointSnapshot> getUsable(
            String serviceName,
            String environment,
            Instant now,
            Duration maxStale) {
        EndpointSnapshot snapshot = current.get();
        if (snapshot == null
                || !snapshot.serviceName().equals(serviceName)
                || !snapshot.environment().equals(environment)
                || snapshot.addresses().isEmpty()) {
            return Optional.empty();
        }

        Duration age = Duration.between(snapshot.fetchedAt(), now);
        if (age.isNegative() || age.compareTo(maxStale) > 0) {
            return Optional.empty();
        }
        return Optional.of(snapshot);
    }
}
```

Đây là thành phần minh họa, chưa phải resolver hoàn chỉnh. Khi cập nhật snapshot thực tế, cần validate từng host/port, kiểm tra revision không lùi, xác minh service/environment identity và công bố snapshot nguyên tử. Dùng `Instant` để lưu mốc thời gian quan sát; nếu cần đo elapsed time chính xác trong cùng process, có thể dùng monotonic clock cho bộ đếm nội bộ.

Snapshot trong bộ nhớ mất khi process restart. Persist snapshot ra đĩa chỉ nên làm khi có nhu cầu rõ ràng; dữ liệu persisted cần có version, service/environment identity, thời hạn, integrity protection và phải được kiểm tra lại trước khi sử dụng. Không nạp cache của một deployment hoặc environment khác.

## 5. Tích hợp fallback tại NameResolver

Khi lookup thành công, resolver lưu snapshot và phát `ResolutionResult`. Khi lookup lỗi, resolver thử lấy snapshot còn mới; nếu không có snapshot hợp lệ thì báo lỗi qua listener.

Luồng khái quát:

```text
NameResolver refresh
       |
       v
Primary discovery lookup
       |
   +---+--------------------+
   | success                | failure
   v                        v
Validate full snapshot   Classify error
   |                        |
   v                        v
Save last-known-good    Is fallback allowed?
   |                        |
   v                   +----+-----+
Publish result         | yes      | no
                       v          v
                Snapshot fresh?  listener.onError
                       |
                 +-----+------+
                 | yes        | no
                 v            v
          Publish fallback   Try alternate source
                              or fail closed
```

Ví dụ phần xử lý kết quả:

```java
void onLookupFailure(
        Throwable cause,
        NameResolver.Listener2 listener,
        LastKnownGoodStore store,
        String serviceName,
        String environment,
        Duration maxStale) {

    Optional<EndpointSnapshot> fallback =
        store.getUsable(
            serviceName, environment, Instant.now(), maxStale);

    if (fallback.isPresent()) {
        EndpointSnapshot snapshot = fallback.get();
        publishSnapshot(listener, snapshot.addresses());
        recordFallbackUse(snapshot.revision(), cause);
        return;
    }

    listener.onError(
        io.grpc.Status.UNAVAILABLE
            .withDescription("Service discovery is unavailable")
            .withCause(cause));
}
```

`publishSnapshot(...)` ở đây là hàm chuyển địa chỉ thành `EquivalentAddressGroup` và gọi `listener.onResult(...)` như trong một resolver thông thường. Callback phải chạy trong `SynchronizationContext` của gRPC. Ví dụ bỏ qua phần triển khai registry client, revision gate, metric và backoff để tập trung vào quyết định fallback.

Không gọi `listener.onError(...)` rồi đồng thời phát một snapshot fallback cho cùng một lần xử lý mà không có thứ tự/policy rõ ràng. Hãy chọn một kết quả cho mỗi quyết định: publish snapshot hợp lệ hoặc báo resolution error. Nếu dùng alternate source, chỉ publish sau khi nguồn đó trả snapshot đã validate.

## 6. Static endpoint và alternate discovery

Static endpoint phù hợp cho môi trường local, bootstrap hoặc một gateway ổn định. Ví dụ cấu hình:

```yaml
clients:
  orders:
    discovery:
      primary-target: catalog:///orders
      fallback:
        mode: last-known-good
        max-stale: 45s
        static-target: ""
```

Trong cấu hình này, `static-target` để trống vì mode đang dùng last-known-good. Nếu chọn static fallback, địa chỉ phải được khai báo tường minh theo environment và phải dùng TLS/authority phù hợp. Không tự động fallback về `localhost`, `127.0.0.1` hoặc một IP hard-code không được kiểm soát.

Alternate discovery source hữu ích khi có hai control plane độc lập. Ví dụ registry chính đặt trong cluster, còn DNS/gateway dự phòng ở vùng khác. Trước khi chuyển nguồn, xác minh:

- Cùng service identity và API contract.
- Endpoint thuộc đúng environment, tenant và region.
- Cùng yêu cầu TLS/authentication.
- Health/readiness và version tương thích.
- Có cơ chế tránh split-brain hoặc snapshot revision cũ hơn nguồn chính.

Hai nguồn discovery dùng chung DNS, network, credentials hoặc control plane có thể cùng hỏng. Fallback chỉ tăng availability khi failure domain của nguồn dự phòng thực sự độc lập.

## 7. Khi nào phải fail closed?

Fallback không phải lúc nào cũng an toàn. Fail closed khi không thể xác minh endpoint vẫn thuộc đúng service hoặc policy bảo mật không còn được đáp ứng:

- Target sai cấu trúc hoặc service identity không khớp.
- Registry trả 401/403 do credentials hoặc quyền không hợp lệ.
- Certificate hết hạn, sai SAN hoặc trust chain không hợp lệ.
- Snapshot cũ vượt `maxStale` hoặc lease đã hết hạn.
- Endpoint thuộc environment/tenant/region khác.
- Fallback có thể bỏ qua yêu cầu residency, authorization hoặc routing.

Không chuyển sang plaintext, bỏ certificate verification hoặc gọi một service name gần giống để “cứu” request. Với hệ thống xử lý dữ liệu nhạy cảm hoặc thao tác ghi, fail closed có thể là lựa chọn đúng dù làm giảm availability.

## 8. Fallback discovery khác RPC retry và failover

Ba cơ chế này giải quyết ba vấn đề khác nhau:

| Cơ chế | Kích hoạt khi | Nơi xử lý |
| --- | --- | --- |
| Discovery fallback | Không lấy được endpoint list mới từ DNS/registry | Resolver/configuration |
| Load balancing failover | Một subchannel không kết nối được hoặc không còn đủ điều kiện pick | Load balancer |
| RPC retry | Một call thất bại với status được phép retry và còn deadline/budget | gRPC retry policy hoặc application |

Discovery fallback không tự chạy lại RPC đã thất bại. Load balancer chuyển sang subchannel khác không đồng nghĩa một RPC đã gửi được thực hiện lại. RPC retry cần xem xét:

- Deadline còn lại và retry budget.
- Status code được phép retry.
- Operation có idempotent không.
- Server có thể đã thực hiện request trước khi response bị mất hay không.
- Backoff và giới hạn số lần retry.

Không retry vô hạn khi registry hoặc toàn bộ backend đang unavailable; điều đó có thể khuếch đại sự cố.

## 9. Cấu hình Spring theo môi trường

Fallback mode nên được khai báo rõ ràng và có thể quan sát:

```yaml
# application-local.yml
clients:
  orders:
    discovery:
      primary-target: dns:///localhost:9090
      fallback:
        mode: none

---
# application-prod.yml
clients:
  orders:
    discovery:
      primary-target: dns:///orders.default.svc.cluster.local:8443
      fallback:
        mode: last-known-good
        max-stale: 45s
```

Local thường không cần fallback discovery vì endpoint đã cố định và lỗi cần hiển thị ngay. Production có thể dùng last-known-good với giới hạn tuổi nếu SLA cho phép. Các giá trị chỉ là ví dụ; chọn `max-stale` theo lease, rollout time, endpoint reuse và SLA thực tế.

Nếu starter Spring gRPC quản lý channel, cấu hình target và resolver theo extension point của phiên bản starter. Nếu tự tạo `ManagedChannel`, giữ channel dài hạn, inject vào stub và đóng khi Spring context shutdown. Không tạo một channel mới cho mỗi lần fallback; resolver có thể phát snapshot mới trên channel đang hoạt động.

## 10. Quan sát fallback và tránh che giấu sự cố

Fallback làm hệ thống tiếp tục phục vụ nhưng có thể che khuất việc registry đang hỏng. Cần đo và cảnh báo:

- Số lần discovery lookup thất bại theo nguyên nhân.
- Số lần dùng last-known-good, static hoặc alternate source.
- Tuổi snapshot tại thời điểm fallback.
- Số endpoint và revision của snapshot đang dùng.
- Thời gian ở fallback mode và số lần liên tiếp lookup thất bại.
- Số lần snapshot vượt `maxStale` và chuyển fail closed.
- RPC status/latency trong lúc fallback so với lúc discovery bình thường.

Log nên ghi service name, environment, fallback mode, snapshot revision/age và error category. Không log token, credentials hoặc toàn bộ registry response. Không đưa IP/instance ID không giới hạn vào metric labels.

Đặt cảnh báo khi fallback được kích hoạt, snapshot gần hết hạn hoặc alternate source được dùng. Một hệ thống fallback hoạt động lâu dài mà không cảnh báo có thể biến sự cố tạm thời thành cấu hình sai kéo dài.

## 11. Kiểm thử fallback

Kiểm thử cần xác minh cả quyết định chọn fallback và giới hạn không sử dụng dữ liệu sai:

| Ca kiểm thử | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Primary discovery thành công | Registry trả snapshot mới | Resolver lưu và publish snapshot chính |
| Registry timeout, cache còn mới | Last-known-good age nhỏ hơn `maxStale` | Resolver publish snapshot cũ và ghi nhận fallback |
| Cache vừa hết hạn | Age bằng/vượt giới hạn theo policy | Không dùng snapshot cũ |
| Chưa có snapshot | Discovery lỗi ngay lần đầu | Fail closed hoặc dùng bootstrap đã cấu hình |
| Sai service/environment | Cache thuộc service hoặc profile khác | Từ chối fallback |
| Revision lùi | Nguồn dự phòng trả snapshot cũ hơn | Không ghi đè snapshot mới hơn nếu policy không cho phép |
| Registry 401/403 | Credentials sai | Báo lỗi bảo mật; không che bằng fallback không được phép |
| TLS SAN mismatch | Certificate không khớp target | Kết nối thất bại; không chuyển plaintext |
| Alternate source unavailable | Cả hai nguồn cùng lỗi | Fail closed sau retry budget |
| Discovery phục hồi | Registry chính trả snapshot mới | Resolver trở lại primary và thay snapshot fallback |
| Channel shutdown | Watch/retry đang chạy | Dừng tác vụ và bỏ callback muộn |
| RPC không idempotent | Call lỗi sau khi server có thể đã xử lý | Không retry mù gây thực hiện trùng |

Integration test nên chạy gRPC server test tại endpoint trong snapshot. Sau khi primary registry bị làm cho unavailable, xác minh client vẫn gọi được server trong khoảng `maxStale`; sau khi vượt giới hạn, xác minh resolver không tiếp tục dùng endpoint cũ. Khôi phục registry và xác minh resolver chuyển lại snapshot primary.

## 12. Bài tập vận dụng

Client Spring gRPC dùng custom target `catalog:///orders`. Registry chính thỉnh thoảng timeout trong lúc rollout; một số client có snapshot endpoint gần nhất, client mới khởi động thì chưa có snapshot.

**Yêu cầu:**

1. Phân loại lỗi registry timeout, target sai, 401/403 và TLS mismatch; xác định lỗi nào cho phép fallback.
2. Thiết kế last-known-good snapshot gồm service identity, environment, revision, endpoint list và thời điểm thành công.
3. Chọn `maxStale` dựa trên lease/endpoint lifecycle và xác định hành vi khi cache hết hạn.
4. Định nghĩa bootstrap/static hoặc alternate source cho client mới chưa có snapshot, hoặc chọn fail closed nếu không có nguồn an toàn.
5. Tích hợp fallback trong `NameResolver`, phát snapshot đầy đủ và xử lý callback trong `SynchronizationContext`.
6. Phân biệt discovery fallback với load balancer failover và RPC retry; đặt deadline, retry budget và điều kiện idempotency.
7. Viết test cho registry outage, cache hết hạn, sai environment, TLS mismatch, recovery và channel shutdown.

**Câu hỏi tự kiểm tra:**

- Discovery unavailable khác endpoint transport failure ở điểm nào?
- Last-known-good snapshot cần những metadata nào để tránh dùng nhầm service?
- Vì sao snapshot cũ phải có `maxStale`?
- Khi nào static endpoint là fallback hợp lý?
- Vì sao 401/403 hoặc TLS mismatch thường phải fail closed?
- Discovery fallback có tự retry RPC đã thất bại không?
- Vì sao fallback source cần failure domain độc lập?
- Làm thế nào biết hệ thống đang phục vụ bằng snapshot cũ?

**Ghi nhớ:** Fallback khi discovery không sẵn sàng cần có nguồn thay thế, điều kiện kích hoạt và giới hạn tuổi rõ ràng. Last-known-good chỉ được dùng cho đúng service/environment và trong `maxStale`; static hoặc alternate source phải giữ nguyên contract, TLS và routing policy. Lỗi cấu hình/bảo mật cần fail closed. Trong Spring gRPC, xử lý fallback tại resolver, phân biệt nó với load balancer failover và RPC retry, đồng thời đo thời gian và tần suất sử dụng fallback.
