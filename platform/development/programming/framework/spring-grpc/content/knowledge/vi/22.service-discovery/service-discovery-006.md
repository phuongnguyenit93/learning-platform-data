# Endpoint không khỏe và loại khỏi pool

Trong service discovery, một endpoint có thể vẫn tồn tại trong registry nhưng không còn đủ điều kiện nhận RPC: ứng dụng chưa sẵn sàng, dependency quan trọng bị lỗi, instance đang shutdown hoặc health check báo `NOT_SERVING`. Nếu client tiếp tục chọn endpoint đó, request sẽ thất bại dù các instance khác vẫn hoạt động.

Với Spring gRPC, cần phối hợp ba lớp: **health/readiness xác định endpoint có thể phục vụ hay không; resolver công bố membership; load balancer quyết định endpoint nào được chọn cho RPC**. Loại endpoint không khỏe khỏi pool phải có tín hiệu rõ ràng, thời gian phục hồi và cơ chế tránh loại nhầm do một lỗi mạng thoáng qua.

## 1. Phân biệt các trạng thái thường bị nhầm

“Endpoint không khỏe” không chỉ có một nghĩa. Các tín hiệu sau đại diện cho những khía cạnh khác nhau:

| Tín hiệu | Nó cho biết điều gì? | Có nên loại endpoint khỏi traffic nghiệp vụ? |
| --- | --- | --- |
| Readiness `NOT_READY` | Instance chưa sẵn sàng hoặc không còn muốn nhận request mới | Có; không công bố như endpoint phục vụ |
| gRPC Health `NOT_SERVING` | Health service báo service được hỏi chưa phục vụ | Có, nếu client/LB dùng health checking hoặc discovery tiêu thụ trạng thái này |
| Transport `TRANSIENT_FAILURE` | Kết nối tới endpoint hiện thất bại | Load balancer thường tạm ngừng chọn subchannel đó và thử kết nối lại; không nhất thiết xóa registration |
| Lease/heartbeat hết hạn | Instance không gia hạn được registration | Registry loại bản ghi theo TTL; đây là tín hiệu liveness/control plane |
| RPC trả `UNAVAILABLE` | Một call không thể hoàn tất do service hoặc hạ tầng tạm thời không khả dụng | Không tự động eject chỉ từ một lỗi; cần policy và ngưỡng |
| Liveness thất bại | Process cần được khởi động lại theo cơ chế quản lý | Thường để orchestrator restart; không đồng nghĩa readiness |

Readiness và liveness có mục đích khác nhau. Một process vẫn sống nhưng dependency bắt buộc mất kết nối có thể cần báo `NOT_SERVING`; liveness vẫn thành công để tránh restart liên tục. Ngược lại, lỗi liveness kéo dài có thể yêu cầu restart process.

## 2. Các lớp quyết định endpoint có được chọn hay không

Endpoint có thể bị loại khỏi pool ở nhiều lớp:

1. **Application health:** service biết trạng thái dependency và khả năng xử lý request.
2. **Platform readiness:** Kubernetes hoặc registry đánh dấu instance không còn ready.
3. **Name resolver:** phát snapshot chỉ chứa endpoint được phép nhận traffic.
4. **Client-side health checking:** gRPC health Watch cập nhật trạng thái serving của backend; load balancer có thể ngừng pick endpoint đó.
5. **Load balancer connectivity:** subchannel ở trạng thái lỗi kết nối sẽ không được chọn cho call mới theo policy.

Sơ đồ:

```text
Application / dependency health
             |
             v
   Readiness or gRPC Health
             |
       +-----+------------------+
       |                        |
       v                        v
Kubernetes / Registry     Client health Watch
       |                        |
       v                        v
NameResolver snapshot      LoadBalancer health state
       |                        |
       +-----------+------------+
                   v
           Endpoint pick pool
                   |
          healthy endpoint only
```

Không phải mọi hệ thống đều dùng đủ các lớp. Cần xác định rõ nguồn nào là nguồn sự thật cho readiness, nguồn nào cập nhật resolver và client có bật health checking hay không. Nếu chỉ ghi `NOT_SERVING` trong ứng dụng nhưng resolver/LB không đọc trạng thái đó, traffic vẫn có thể được gửi tới endpoint.

## 3. Cung cấp gRPC Health service

gRPC định nghĩa Health Checking Protocol với service `grpc.health.v1.Health`. Client hoặc hạ tầng có thể hỏi trạng thái của một service cụ thể; phương thức `Watch` cho phép theo dõi thay đổi trạng thái liên tục.

Các trạng thái phổ biến:

- `SERVING`: service hiện có thể nhận request.
- `NOT_SERVING`: service không nên nhận request nghiệp vụ.
- `UNKNOWN`: trạng thái chưa được xác định.
- `SERVICE_UNKNOWN`: health server không biết service name được hỏi.

Trong Java, grpc-java cung cấp `HealthStatusManager` trong artifact `grpc-services`. Ví dụ:

```java
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.protobuf.services.HealthStatusManager;

public final class OrdersGrpcServer {
    public static void main(String[] args) throws Exception {
        HealthStatusManager health = new HealthStatusManager();

        Server server = ServerBuilder.forPort(8443)
            .addService(new OrdersService())
            .addService(health.getHealthService())
            .build()
            .start();

        // Chỉ báo SERVING sau khi server và dependency cần thiết đã ready.
        health.setStatus("orders.v1.OrderService", ServingStatus.SERVING);
        health.setStatus("", ServingStatus.SERVING);

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            health.setStatus(
                "orders.v1.OrderService", ServingStatus.NOT_SERVING);
            server.shutdown();
        }));

        server.awaitTermination();
    }
}
```

Đây là ví dụ grpc-java tối giản; trong Spring gRPC, đăng ký health service và cập nhật trạng thái qua bean/lifecycle component phù hợp với starter. Không tạo một health manager riêng cho mỗi request. Dùng cùng một trạng thái được quản lý theo vòng đời server.

Health service nên trả `SERVING` sau khi gRPC listener đã khởi động và các dependency bắt buộc cho service đã sẵn sàng. Nếu `OrderService` phụ thuộc database nhưng không thể xử lý bất kỳ request nào khi database mất kết nối, có thể chuyển service đó sang `NOT_SERVING`. Không nhất thiết đánh dấu toàn bộ process không khỏe nếu chỉ một service độc lập bị ảnh hưởng; health status có thể được đặt theo service name.

## 4. Client-side health checking và load balancer

Health service chỉ cung cấp trạng thái. Để client ngừng chọn backend `NOT_SERVING`, channel phải có health checking được hỗ trợ và cấu hình phù hợp. Trong gRPC, client-side health checking dùng `Health/Watch` cho service name đã cấu hình; load balancer sử dụng kết quả để quyết định backend có đủ điều kiện nhận RPC hay không.

Service config minh họa:

```json
{
  "healthCheckConfig": {
    "serviceName": "orders.v1.OrderService"
  }
}
```

Service config này cần được cung cấp cho channel theo cơ chế grpc-java đang dùng. Khả năng health checking và cách bật nó phụ thuộc phiên bản grpc-java, load balancing policy và cấu hình channel; hãy xác nhận policy đang chạy thực sự hỗ trợ client-side health checking. Không giả định chỉ đăng ký `HealthStatusManager` ở server là đủ để mọi client tự động ngừng gửi request.

Khi health Watch báo `NOT_SERVING`, client-side health checking có thể ngừng chọn backend đó cho RPC mới. Khi trạng thái trở lại `SERVING`, backend có thể được đưa lại vào pool theo hành vi của implementation. Health Watch là một stream riêng; cần theo dõi lỗi stream, reconnect và trạng thái chưa xác định theo policy.

Phân biệt health state với connectivity state:

- `READY`: subchannel có kết nối và có thể nhận call theo transport.
- `TRANSIENT_FAILURE`: kết nối hiện thất bại, channel có thể thử reconnect.
- Health `NOT_SERVING`: server có kết nối nhưng khai báo service chưa sẵn sàng.

Một endpoint có transport `READY` vẫn có thể không khỏe ở tầng ứng dụng. Ngược lại, một endpoint `TRANSIENT_FAILURE` có thể hồi phục sau reconnect mà không cần xóa khỏi registry.

## 5. Loại endpoint qua registry hoặc resolver

Một cách khác là nguồn discovery lưu readiness/health state và resolver chỉ công bố endpoint đủ điều kiện. Ví dụ registry có snapshot:

```text
orders revision 81:
  orders-1  10.20.1.11:8443  SERVING
  orders-2  10.20.1.12:8443  NOT_SERVING
  orders-3  10.20.1.13:8443  SERVING

resolver result:
  10.20.1.11:8443
  10.20.1.13:8443
```

Resolver cần lọc theo một quy tắc rõ ràng, chẳng hạn chỉ công bố instance có trạng thái `SERVING` và lease còn hiệu lực. Khi instance chuyển `NOT_SERVING`, registry phát snapshot mới và resolver loại endpoint khỏi `ResolutionResult`.

Điểm quan trọng:

- Phát **snapshot đầy đủ** sau mỗi thay đổi, không gửi delta nếu API resolver đang dùng yêu cầu `ResolutionResult`.
- Dùng revision/generation để bỏ kết quả lookup cũ đến muộn.
- Không giữ endpoint đã bị loại vô thời hạn chỉ vì registry tạm thời lỗi.
- Phân biệt trạng thái `NOT_SERVING` với registry không truy cập được.
- Không tự probe từng endpoint trên thread callback của resolver; dùng health source hoặc worker bất đồng bộ có timeout.

Không nên đồng thời lọc endpoint ở quá nhiều lớp mà không có quy ước. Ví dụ registry xóa endpoint ngay, client health Watch vẫn còn stream, còn resolver cache lại snapshot cũ; việc phối hợp thứ tự và propagation delay phải được xác định.

## 6. Kubernetes readiness và gRPC health

Trong Kubernetes, readiness probe quyết định Pod có được xem là sẵn sàng nhận traffic qua Service hay không. Với gRPC, probe có thể kiểm tra health service của ứng dụng:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
spec:
  template:
    spec:
      containers:
        - name: orders
          ports:
            - name: grpc
              containerPort: 8443
          readinessProbe:
            grpc:
              port: 8443
              service: orders.v1.OrderService
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
```

Đây là manifest minh họa; cần điều chỉnh theo cấu hình cluster và cách server triển khai health endpoint. Kubernetes native gRPC probe có các giới hạn riêng, chẳng hạn không cấu hình TLS credentials hay authentication như một gRPC client ứng dụng thông thường. Nếu server chỉ nhận TLS hoặc yêu cầu xác thực, cần chọn probe mechanism phù hợp (ví dụ exec/custom probe hoặc endpoint health nội bộ được bảo vệ bằng network policy).

Khi readiness thất bại, Kubernetes cập nhật trạng thái endpoint của Service/EndpointSlice theo cơ chế control plane. Điều này không đóng ngay các kết nối HTTP/2 đã tồn tại ở client. Client có thể tiếp tục giữ subchannel tới địa chỉ cũ trong thời gian propagation hoặc connection draining.

Không dùng liveness probe để kiểm tra mọi dependency từ xa một cách quá nhạy. Nếu database chậm vài giây, restart hàng loạt Pod có thể làm sự cố nặng hơn. Readiness thường phù hợp hơn để tạm ngừng nhận traffic; liveness nên phát hiện process không thể tự phục hồi.

## 7. Passive ejection và tránh loại nhầm

Một số load balancer hoặc service mesh có passive health checking: quan sát lỗi RPC/kết nối để tạm thời eject endpoint. Cách này hữu ích khi không có health signal đáng tin, nhưng một lỗi đơn lẻ không đủ để kết luận instance hỏng.

Policy nên cân nhắc:

- Ngưỡng lỗi liên tiếp hoặc tỷ lệ lỗi trong cửa sổ thời gian.
- Loại lỗi: `UNAVAILABLE` do backend, lỗi mạng, `DEADLINE_EXCEEDED` do client timeout hay lỗi nghiệp vụ.
- Số request tối thiểu trước khi tính tỷ lệ.
- Thời gian eject tối đa và cooldown.
- Cơ chế thử lại có kiểm soát (half-open) trước khi đưa endpoint trở lại.
- Giới hạn tỷ lệ endpoint bị eject để tránh làm cạn capacity toàn cụm.

Không eject endpoint chỉ vì `INVALID_ARGUMENT`, `PERMISSION_DENIED` hoặc lỗi nghiệp vụ do request. Những status này thường phản ánh input/quyền của caller, không phải sức khỏe của backend. `UNAVAILABLE` có thể là dấu hiệu hạ tầng nhưng cũng cần phân tích nguồn phát sinh.

Ví dụ state machine:

```text
             consecutive failures / health NOT_SERVING
   SERVING ----------------------------------------------> EJECTED
      ^                                                       |
      |                                                       | cooldown
      | successful health check / probe                       v
   HALF_OPEN <-------------------------------------------- PROBING
      |
      +-- failures --> EJECTED
      |
      +-- enough successes --> SERVING
```

Đây là mô hình policy, không phải state machine bắt buộc của grpc-java. Nếu load balancer hiện tại không hỗ trợ outlier detection, chức năng này có thể thuộc service mesh, proxy hoặc custom load balancer; không tự giả định `round_robin` tiêu chuẩn sẽ eject backend theo tỷ lệ lỗi ứng dụng.

## 8. Đưa endpoint trở lại pool

Loại endpoint chỉ là một nửa vòng đời. Nếu không có recovery path, một lỗi thoáng qua có thể khiến instance bị loại vĩnh viễn.

Quy trình re-admission nên xác định:

1. Nguồn health chuyển lại `SERVING` hoặc probe thành công.
2. Instance vẫn có lease/registration hợp lệ và địa chỉ truy cập được.
3. Resolver phát snapshot mới có endpoint đó.
4. Health checking/LB xác nhận backend có thể nhận call.
5. Endpoint được đưa trở lại pool; nếu hệ thống hỗ trợ, có thể tăng traffic dần.

Với passive ejection, dùng cooldown và một số probe thành công liên tiếp trước khi phục hồi. Với readiness, chỉ chuyển `READY` khi dependency bắt buộc đã ổn định. Tránh dao động liên tục giữa `SERVING` và `NOT_SERVING` bằng debounce/hysteresis phù hợp.

## 9. Graceful drain khi endpoint cần dừng

Khi triển khai phiên bản mới hoặc shutdown instance, trình tự thường là:

1. Chuyển health status sang `NOT_SERVING` hoặc readiness `false`.
2. Chờ health Watch/registry/EndpointSlice và resolver truyền trạng thái mới tới client.
3. Ngừng nhận RPC mới và bắt đầu drain.
4. Cho RPC đang chạy hoàn tất trong grace period.
5. Shutdown server; lease TTL là lớp dọn dẹp nếu deregistration thất bại.

Thứ tự cụ thể phụ thuộc hạ tầng. Nếu registry xóa endpoint trước khi health Watch báo `NOT_SERVING`, client có thể nhận hai tín hiệu không cùng thời điểm. Cần đặt grace period đủ cho propagation nhưng hữu hạn. Không kỳ vọng việc loại khỏi resolver snapshot lập tức hủy mọi RPC in-flight.

## 10. Quan sát và kiểm thử endpoint health

Nên theo dõi:

- Số endpoint theo trạng thái `SERVING`, `NOT_SERVING`, `UNKNOWN`.
- Số subchannel `READY` và `TRANSIENT_FAILURE`.
- Thời gian từ health/readiness đổi trạng thái đến khi endpoint ngừng được chọn.
- Số lần endpoint bị eject, thời gian eject và số lần re-admission.
- Tỷ lệ RPC lỗi theo endpoint và status code.
- Số health Watch đang mở, lỗi stream và lần reconnect.
- Thời gian drain và số RPC còn in-flight khi shutdown.

Không dùng instance ID hoặc IP làm metric label không giới hạn; cardinality có thể tăng nhanh khi Pod thay thế. Log có thể ghi endpoint ID đã được kiểm soát, nhưng không ghi credentials hoặc toàn bộ metadata.

| Ca kiểm thử | Thiết lập | Kết quả cần xác minh |
| --- | --- | --- |
| Ready ban đầu | Server và dependency đã sẵn sàng | Health trả `SERVING`; endpoint được công bố |
| Dependency mất | Giả lập database bắt buộc unavailable | Service chuyển `NOT_SERVING`; endpoint ngừng được chọn theo policy |
| Health Watch update | Chuyển `SERVING` sang `NOT_SERVING` | Client health checking nhận thay đổi |
| Transport failure thoáng qua | Ngắt kết nối rồi phục hồi | Subchannel reconnect; không xóa registration vĩnh viễn |
| Registry loại endpoint | Snapshot mới bỏ instance | Resolver publish snapshot mới; LB cập nhật subchannel |
| Passive error burst | Tạo lỗi vượt ngưỡng | Endpoint bị eject theo cooldown đã định nghĩa |
| Recovery | Health/probe thành công liên tiếp | Endpoint được đưa lại vào pool |
| False positive | Một RPC trả `INVALID_ARGUMENT` | Endpoint không bị eject |
| Graceful drain | Đặt `NOT_SERVING` rồi shutdown | RPC mới ngừng được chọn; RPC in-flight được xử lý theo grace period |
| Kubernetes readiness | Probe thất bại rồi phục hồi | EndpointSlice cập nhật và traffic trở lại theo propagation |

Integration test nên có ít nhất hai backend: backend A chuyển `NOT_SERVING`, backend B vẫn `SERVING`. Gửi RPC liên tục và xác minh call mới không còn tới A sau khi health/discovery update được áp dụng, trong khi B tiếp tục phục vụ. Sau đó đưa A về `SERVING` và xác minh nó được nhận traffic trở lại. Kiểm thử riêng RPC đang chạy lúc A bị loại để xác nhận chính sách drain.

## 11. Bài tập vận dụng

`OrderService` chạy ba instance. Một instance vẫn mở TCP/HTTP2 connection nhưng database pool của nó cạn, khiến request thất bại. Client hiện chỉ dựa vào trạng thái kết nối nên vẫn gửi call tới instance này.

**Yêu cầu:**

1. Bổ sung gRPC Health service và cập nhật `SERVING`/`NOT_SERVING` theo readiness của dependency bắt buộc.
2. Chọn một cơ chế để client ngừng pick endpoint không khỏe: client-side health checking hoặc resolver lọc registry readiness; giải thích giới hạn của cơ chế còn lại.
3. Phân biệt health failure với `TRANSIENT_FAILURE`, lease expiry và một RPC trả `UNAVAILABLE`.
4. Thiết kế threshold/cooldown nếu dùng passive ejection; không eject vì lỗi input như `INVALID_ARGUMENT`.
5. Xây dựng recovery path để endpoint trở lại pool sau khi dependency phục hồi.
6. Phối hợp readiness, registry update, health Watch và graceful drain khi rollout.
7. Viết integration test với hai backend để chứng minh traffic ngừng tới endpoint `NOT_SERVING` và quay lại khi endpoint `SERVING`.

**Câu hỏi tự kiểm tra:**

- Vì sao transport `READY` không đồng nghĩa service `SERVING`?
- Heartbeat/lease khác readiness và gRPC Health Watch ở điểm nào?
- Đăng ký health service có tự động khiến mọi client loại endpoint không khỏe không?
- Khi nào resolver nên lọc endpoint và khi nào client-side health checking phù hợp hơn?
- Vì sao một lỗi `UNAVAILABLE` đơn lẻ chưa đủ để eject backend?
- Readiness và liveness probe có mục tiêu khác nhau thế nào?
- Khi endpoint bị loại khỏi pool, RPC đang chạy được xử lý ra sao?
- Cần điều kiện gì để đưa endpoint trở lại pool an toàn?

**Ghi nhớ:** Endpoint không khỏe cần được nhận diện bằng readiness hoặc health signal phù hợp, sau đó truyền tới resolver/load balancer để ngừng chọn cho RPC mới. Phân biệt health state với transport connectivity và lease; dùng threshold/cooldown để tránh eject nhầm; có recovery path và graceful drain. Trong Spring gRPC, hãy kiểm thử toàn bộ đường đi từ trạng thái ứng dụng tới endpoint pick, không chỉ kiểm tra health endpoint trả về đúng giá trị.
