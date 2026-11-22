# Resolver và load balancer

Trong Spring gRPC, service discovery và phân phối RPC là hai bước liên tiếp nhưng có trách nhiệm khác nhau. **Name resolver tìm các địa chỉ hiện có của một service; load balancer dùng danh sách đó để quản lý kết nối và chọn endpoint cho từng RPC.** Tách bạch hai phần giúp chẩn đoán đúng lỗi DNS/registry, lỗi kết nối và lỗi phân phối tải.

Ví dụ client gọi target logic `dns:///orders.default.svc.cluster.local:8443`. Resolver phân giải tên này thành một hoặc nhiều endpoint. Load balancer nhận kết quả, tạo hoặc cập nhật subchannel tới các endpoint và chọn subchannel phù hợp khi stub thực hiện RPC. Ứng dụng vẫn dùng một `ManagedChannel` và stub ổn định trong khi danh sách endpoint thay đổi.

## 1. Hai trách nhiệm trong một luồng

```text
Client target URI
      |
      v
NameResolverRegistry -> NameResolver
      |
      | ResolutionResult: endpoint list + attributes/service config
      v
ManagedChannel
      |
      v
LoadBalancer
      |
      +---- create/update/remove Subchannels
      |
      v
Picker chọn Subchannel cho mỗi RPC
      |
      v
HTTP/2 transport -> gRPC server instance
```

| Thành phần | Câu hỏi nó trả lời | Trách nhiệm |
| --- | --- | --- |
| Target URI | Client muốn gọi service logic nào? | Chọn scheme và service name |
| Name resolver | Service hiện có địa chỉ nào? | Tra cứu DNS/registry và phát kết quả phân giải |
| Load balancer | RPC tiếp theo đi qua kết nối nào? | Quản lý subchannel, trạng thái kết nối và picker |
| Subchannel | Kết nối tới một nhóm địa chỉ ra sao? | Thiết lập/reconnect transport tới endpoint |
| Picker | Call hiện tại được gửi đi hay phải chờ/báo lỗi? | Chọn subchannel sẵn sàng hoặc trả quyết định tương ứng |

Resolver không tự round-robin từng RPC. Load balancer không tự biết toàn bộ instance trong registry nếu resolver không cung cấp địa chỉ. Mỗi thành phần dựa trên hợp đồng của thành phần trước.

## 2. Name resolver: từ target tới endpoint list

Khi channel được tạo bằng `ManagedChannelBuilder.forTarget(...)`, gRPC phân tích target URI và chọn `NameResolverProvider` theo scheme. Provider tạo `NameResolver`, sau đó resolver tra cứu nguồn discovery.

Ví dụ target:

```text
dns:///orders.default.svc.cluster.local:8443
catalog:///orders
```

`dns` là scheme DNS tiêu chuẩn; `catalog` là ví dụ scheme tùy chỉnh và chỉ hoạt động khi provider tương ứng được đăng ký. Resolver không cần biết client sẽ dùng `pick_first` hay `round_robin`; nó chỉ công bố endpoint hợp lệ.

Kết quả phân giải thường gồm:

- Danh sách `EquivalentAddressGroup`, mỗi group chứa một hoặc nhiều địa chỉ tương đương.
- `Attributes` gắn với group hoặc kết quả, ví dụ zone/region nếu policy cần.
- Service config nếu resolver có nguồn cấu hình và channel cho phép sử dụng.

Ví dụ phát kết quả:

```java
List<EquivalentAddressGroup> groups = new ArrayList<>();
for (InetSocketAddress address : resolvedAddresses) {
    groups.add(new EquivalentAddressGroup(address));
}

NameResolver.ResolutionResult result =
    NameResolver.ResolutionResult.newBuilder()
        .setAddresses(groups)
        .build();

listener.onResult(result);
```

Đây là phần cốt lõi của một resolver đơn giản. Resolver thực tế còn phải validate địa chỉ, quản lý refresh/watch, xử lý lỗi và phát snapshot mới trong `SynchronizationContext`. Mỗi `onResult(...)` nên mang danh sách endpoint đầy đủ hiện còn hợp lệ để channel có thể cập nhật trạng thái nhất quán.

Nếu DNS/registry không phân giải được target, resolver báo lỗi qua listener. Không nên tự chọn một địa chỉ giả hoặc nhúng thuật toán retry RPC vào resolver; retry tra cứu và retry một RPC là hai chính sách khác nhau.

## 3. Load balancer: từ endpoint list tới RPC pick

Load balancer nhận các địa chỉ từ resolver qua API nội bộ của gRPC, tạo hoặc cập nhật `Subchannel` và theo dõi trạng thái kết nối. Sau đó nó cung cấp một picker để channel hỏi mỗi khi có RPC mới.

Các công việc chính:

1. Nhận `ResolvedAddresses` mới.
2. So sánh endpoint hiện tại với snapshot mới.
3. Tạo subchannel cho endpoint mới và bắt đầu kết nối.
4. Giữ subchannel còn hợp lệ; loại hoặc shutdown subchannel không còn trong snapshot theo policy.
5. Theo dõi connectivity state của từng subchannel.
6. Cập nhật picker để chọn subchannel phù hợp cho RPC mới.

Connectivity state thường gặp:

| State | Ý nghĩa với load balancer |
| --- | --- |
| `IDLE` | Subchannel chưa có hoạt động kết nối |
| `CONNECTING` | Đang thiết lập kết nối |
| `READY` | Transport sẵn sàng nhận RPC |
| `TRANSIENT_FAILURE` | Kết nối tạm thời thất bại; có thể thử reconnect |
| `SHUTDOWN` | Subchannel đã đóng |

Picker có thể trả về một subchannel sẵn sàng, yêu cầu channel chờ khi chưa có kết nối, hoặc trả lỗi theo trạng thái/policy. Vì thế, “resolver trả về ba địa chỉ” không có nghĩa cả ba đã `READY` hoặc request lập tức được chia đều.

## 4. Các policy phổ biến

Resolver cung cấp endpoint; policy quyết định cách sử dụng. Hai policy thường gặp:

| Policy | Cách chọn | Phù hợp khi |
| --- | --- | --- |
| `pick_first` | Thử các địa chỉ và dùng subchannel sẵn sàng đầu tiên theo thứ tự resolver; chuyển sang địa chỉ khác khi cần | Muốn một kết nối đang hoạt động ổn định, discovery thường trả một endpoint hoặc có proxy/service VIP |
| `round_robin` | Phân phối RPC qua các subchannel đang `READY` | Muốn client-side phân phối tải khi resolver trả nhiều endpoint độc lập |

Ví dụ, resolver trả ba Pod IP. Với `pick_first`, channel thường dùng một subchannel sẵn sàng và không luân phiên từng call qua cả ba. Với `round_robin`, picker có thể phân phối các RPC mới qua những subchannel `READY`.

Không phải mọi policy đều có mặt trong mọi runtime. Policy phải được đăng ký/có trong phiên bản grpc-java đang dùng và được chọn qua service config hoặc cơ chế cấu hình channel. Một policy không được hỗ trợ có thể khiến channel fallback hoặc báo lỗi tùy phiên bản/cấu hình; hãy quan sát policy thực tế thay vì chỉ dựa vào JSON đã khai báo.

Service config minh họa cho round robin:

```json
{
  "loadBalancingConfig": [
    {
      "round_robin": {}
    }
  ]
}
```

Đây là nội dung service config; cần cung cấp nó cho channel theo cơ chế grpc-java/starter của dự án và xác nhận resolver/channel chấp nhận service config. Đừng giả định chỉ đặt JSON ở một file bất kỳ thì channel tự động đọc.

## 5. Tích hợp với Spring gRPC

Trong ứng dụng Spring, channel nên được quản lý dài hạn và tái sử dụng bởi các stub. Target xác định resolver; service config hoặc cấu hình channel xác định load balancing policy.

Ví dụ tạo channel với DNS target:

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
            .forTarget("dns:///orders.default.svc.cluster.local:8443")
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

`OrdersGrpc` là tên minh họa cho generated stub. Nếu starter Spring gRPC quản lý channel/client, khai báo target và load balancing/service config bằng extension point của đúng phiên bản starter; không tạo thêm channel thủ công cho mỗi RPC.

Các điểm cần kiểm tra:

- Target có scheme đúng với resolver provider không?
- Resolver có trả nhiều endpoint như mong đợi không?
- Load balancing policy đã được đăng ký và thực sự được chọn chưa?
- TLS authority/certificate có hợp lệ cho service name không?
- Channel có được đóng khi Spring context shutdown không?

Không dùng IP cố định trong cấu hình channel nếu mục tiêu là discovery động. Cũng không tạo channel mới mỗi khi endpoint list đổi; resolver và load balancer được thiết kế để cập nhật trên channel đang sống.

## 6. Endpoint update ảnh hưởng load balancer thế nào?

Giả sử resolver phát snapshot mới:

```text
Snapshot cũ: A, B
Snapshot mới: B, C

A -> bị loại khỏi membership
B -> tiếp tục tồn tại
C -> endpoint mới, cần subchannel
```

Load balancer xử lý thay đổi:

- Tạo subchannel cho C và kết nối tới endpoint mới.
- Giữ subchannel B nếu địa chỉ/identity còn phù hợp.
- Ngừng chọn A cho RPC mới và shutdown subchannel khi policy/lifecycle cho phép.
- Cập nhật picker theo trạng thái READY của B và C.

Nếu C đang `CONNECTING`, picker có thể tiếp tục chọn B thay vì gửi RPC vào kết nối chưa sẵn sàng. Nếu không còn subchannel `READY`, channel có thể chờ, reconnect hoặc trả lỗi theo policy và deadline của call.

Loại endpoint khỏi snapshot không nhất thiết hủy RPC đang chạy trên A. RPC in-flight và connection draining cần được xử lý riêng; không dựa vào việc resolver phát snapshot mới để giả định mọi call cũ tự chuyển sang B hoặc C.

## 7. Health checking khác connectivity và load balancing

Subchannel `READY` chỉ cho biết transport đã kết nối. Nó không chứng minh service nghiệp vụ đang khỏe. Một server có thể giữ HTTP/2 connection nhưng database pool đã cạn.

Các tín hiệu cần phân biệt:

- **Resolver membership:** endpoint có còn được nguồn discovery công bố không?
- **Connectivity:** subchannel có kết nối transport sẵn sàng không?
- **gRPC health:** service báo `SERVING` hay `NOT_SERVING`?
- **Readiness:** instance có muốn và có thể nhận traffic mới không?

Nếu bật client-side gRPC health checking và policy hỗ trợ, trạng thái `NOT_SERVING` có thể khiến backend không được picker chọn cho RPC mới dù transport vẫn `READY`. Nếu không bật health checking, chỉ đăng ký health service ở server không tự động thay đổi lựa chọn của client.

Có thể lọc endpoint `NOT_SERVING` ngay tại nguồn discovery/resolver, hoặc dùng health Watch ở client. Chọn một quy tắc rõ ràng và kiểm thử propagation; tránh để registry, resolver và health Watch giữ các trạng thái mâu thuẫn trong thời gian dài.

## 8. Những lỗi thường gặp khi resolver và load balancer phối hợp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| DNS phân giải nhiều IP nhưng traffic chỉ tới một IP | Policy là `pick_first`, hoặc chỉ một subchannel `READY` | Xem service config, policy thực tế và connectivity state |
| Resolver trả endpoint nhưng RPC `UNAVAILABLE` | Địa chỉ/port sai, TLS mismatch hoặc mọi subchannel chưa `READY` | Kiểm tra endpoint, transport, TLS và picker state |
| Endpoint mới không được dùng | Resolver chưa refresh hoặc LB chưa nhận snapshot mới | Theo dõi revision, thời điểm `onResult` và subchannel creation |
| Endpoint đã xóa vẫn nhận call | Snapshot cũ/cache, propagation delay hoặc RPC in-flight | Kiểm tra resolver snapshot, picker và connection draining |
| Round robin không hoạt động | Policy không được hỗ trợ/chọn, resolver chỉ trả một địa chỉ hoặc chỉ một subchannel ready | Kiểm tra provider, service config và endpoint list |
| Channel không phục hồi sau lỗi tạm thời | Resolver không refresh hoặc subchannel reconnect bị ảnh hưởng bởi cấu hình | Quan sát resolver error, connectivity state và backoff |
| Instance khỏe nhưng bị loại | Readiness/health signal sai hoặc filter quá nhạy | So sánh registry state, health Watch và application readiness |

Chẩn đoán theo chuỗi: target → resolver provider → endpoint snapshot → load balancing policy → subchannel state → picker result → transport/TLS → RPC status. Chuỗi này giúp xác định lỗi ở discovery hay ở việc sử dụng endpoint.

## 9. Kiểm thử resolver và load balancer

Nên kiểm thử riêng từng trách nhiệm và thêm integration test qua channel:

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| Target hợp lệ | Chọn đúng resolver provider theo scheme |
| Resolver trả một/nhiều endpoint | `ResolutionResult` chứa đúng address groups |
| Endpoint được thêm/xóa | Load balancer tạo/loại subchannel theo snapshot mới |
| `pick_first` với nhiều endpoint | Dùng subchannel sẵn sàng đầu tiên theo policy |
| `round_robin` với nhiều endpoint | RPC mới được phân phối qua các subchannel READY |
| Một endpoint `TRANSIENT_FAILURE` | Endpoint lỗi không được pick khi có endpoint READY khác |
| Tất cả endpoint chưa READY | Picker chờ hoặc báo lỗi theo trạng thái/deadline |
| Endpoint update khi có RPC in-flight | Call hiện tại và call mới tuân theo drain/update policy |
| Health `NOT_SERVING` | Backend không được chọn nếu client health checking được bật |
| Resolver/channel shutdown | Watch, subchannel và channel được giải phóng đúng lifecycle |

Dùng fake resolver hoặc registry giả để kiểm soát snapshot và thứ tự cập nhật. Dùng server test trên các port động để xác minh RPC thực sự tới backend nào. Với `round_robin`, gửi đủ số call sau khi mọi subchannel đã `READY`, rồi kiểm tra phân phối; không assert cân bằng tuyệt đối trong một mẫu nhỏ vì kết quả có thể chịu ảnh hưởng thời điểm kết nối và picker.

In-process transport hữu ích cho logic service/interceptor nhưng không kiểm tra DNS, TCP, TLS hoặc hành vi kết nối của subchannel thực. Các phần đó cần integration test với transport thật hoặc môi trường gần production.

## 10. Bài tập vận dụng

`OrderService` chạy ba instance trong Kubernetes. DNS trả ba Pod IP nhưng client hiện dùng `pick_first`, khiến phần lớn RPC tập trung vào một instance. Nhóm muốn phân phối tải ở phía client và loại backend không khỏe khỏi pool.

**Yêu cầu:**

1. Mô tả dữ liệu resolver cần phát cho channel và vì sao resolver không tự chọn backend cho từng RPC.
2. Cấu hình service config dùng `round_robin` nếu policy được hỗ trợ.
3. Xác minh ba subchannel đều đạt `READY` trước khi đánh giá phân phối.
4. Bổ sung health checking hoặc lọc readiness để endpoint `NOT_SERVING` không được chọn.
5. Khi một endpoint bị xóa, kiểm tra subchannel được cập nhật và RPC in-flight được drain đúng cách.
6. Viết integration test so sánh `pick_first` và `round_robin`, gồm một endpoint lỗi và một lần endpoint list thay đổi.

**Câu hỏi tự kiểm tra:**

- Resolver và load balancer khác nhau ở đầu vào, đầu ra và trách nhiệm nào?
- `ResolutionResult` mang dữ liệu gì?
- Vì sao nhiều endpoint trong resolver result không đảm bảo round robin?
- `READY` của subchannel có đồng nghĩa service `SERVING` không?
- Picker quyết định điều gì khi chưa có subchannel sẵn sàng?
- Khi endpoint bị xóa khỏi snapshot, RPC đang chạy có tự động chuyển sang endpoint khác không?
- Khi nào `pick_first` phù hợp hơn `round_robin`?
- Làm thế nào xác minh policy thực tế đang được channel sử dụng?

**Ghi nhớ:** Resolver biến target thành snapshot endpoint; load balancer biến snapshot thành subchannel và picker cho RPC. Resolver chịu trách nhiệm discovery và cập nhật membership; load balancer chịu trách nhiệm kết nối, trạng thái và lựa chọn endpoint. Trong Spring gRPC, giữ channel dài hạn, cấu hình policy được hỗ trợ, phân biệt connectivity với health và kiểm thử cả endpoint update lẫn RPC thực tế.
