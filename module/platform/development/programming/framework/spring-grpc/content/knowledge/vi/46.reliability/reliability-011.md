# Runbook cho UNAVAILABLE tăng đột biến

Runbook này hướng dẫn xử lý sự cố khi tỷ lệ gRPC status UNAVAILABLE tăng bất thường trong hệ thống Spring gRPC. UNAVAILABLE là canonical status code 14, thường biểu thị RPC không thể hoàn tất do service hoặc transport tạm thời không sẵn sàng. Tuy nhiên, status này không tự chứng minh server đã chết: nó có thể do server chủ động trả về, client không kết nối được, load balancer chọn endpoint lỗi, DNS/TLS/HTTP2 gặp vấn đề hoặc dependency phía server không sẵn sàng.

Mục tiêu trong sự cố là xác định phạm vi ảnh hưởng, phân biệt lỗi ứng dụng với lỗi kết nối, khôi phục khả năng phục vụ mà không tạo retry storm, rồi xác minh tỷ lệ lỗi và latency đã trở về mức bình thường. Hãy dùng method name, status, endpoint, thời điểm và trace/request ID để khoanh vùng; không ghi token hoặc payload nhạy cảm vào log.

## 1. Nhận diện và xác nhận sự cố

Kích hoạt runbook khi một hoặc nhiều tín hiệu vượt ngưỡng đã định nghĩa:
- Tỷ lệ RPC kết thúc bằng UNAVAILABLE tăng nhanh so với baseline.
- Số request thành công giảm trong khi traffic đầu vào vẫn ổn định.
- Client ghi nhận nhiều lỗi kết nối, channel chuyển sang TRANSIENT_FAILURE hoặc RPC timeout.
- Nhiều service consumer cùng báo lỗi tới một provider hoặc một vùng triển khai.
- Alert về pod restart, readiness failure, endpoint count giảm, DNS hoặc load balancer đồng thời xuất hiện.

Trước khi xử lý, xác nhận đây là tăng tỷ lệ chứ không chỉ tăng số tuyệt đối do traffic tăng. So sánh theo method, service, client application, zone/cluster, server instance và phiên bản release.

Bảng dữ liệu tối thiểu cần thu thập:

| Tín hiệu | Câu hỏi |
| --- | --- |
| Request rate | Traffic có tăng đột biến hoặc dồn vào một consumer không? |
| Error rate theo status | UNAVAILABLE tăng riêng hay mọi status cùng tăng? |
| Method | Một RPC hay toàn bộ method của service bị ảnh hưởng? |
| Client/service version | Lỗi bắt đầu sau rollout client hoặc server nào? |
| Endpoint/zone | Chỉ một pod, node, zone hay toàn bộ provider? |
| Latency và deadline | UNAVAILABLE tăng cùng DEADLINE_EXCEEDED hay xuất hiện ngay khi connect? |
| Server health | Pod ready, restart, CPU, memory, GC và queue có bất thường? |
| Dependency | Database, HTTP service, broker hoặc DNS phụ thuộc có lỗi? |

Không gộp UNAVAILABLE với DEADLINE_EXCEEDED. UNAVAILABLE thường chỉ ra service/transport không thể phục vụ call; DEADLINE_EXCEEDED cho biết ngân sách thời gian của call đã hết. Hai lỗi có thể cùng xuất hiện khi hệ thống quá tải, nhưng cần phân tích riêng.

## 2. Phân biệt status do server trả và lỗi do transport

UNAVAILABLE có thể xuất hiện từ hai đường chính:

1. **Server trả status UNAVAILABLE:** handler hoặc exception mapper chủ động đóng RPC với Status.UNAVAILABLE, ví dụ dependency tạm thời không sẵn sàng hoặc service đang từ chối traffic.
2. **Client/runtime tạo status UNAVAILABLE:** client không thiết lập hoặc duy trì được RPC do connection refused, endpoint không reachable, connection reset, proxy/HTTP2 failure hoặc server biến mất giữa call.

Bắt status ở client:

~~~java
try {
    return orderStub.getOrder(request);
} catch (StatusRuntimeException error) {
    Status status = Status.fromThrowable(error);

    if (status.getCode() == Status.Code.UNAVAILABLE) {
        metrics.incrementUnavailable("GetOrder");
        log.warn("gRPC call unavailable: method={}, description={}",
                "GetOrder", status.getDescription());
    }

    throw error;
}
~~~

Đây là ví dụ phân loại ở client. Trong hệ thống thực, tránh log mỗi exception ở mức ERROR với stack trace đầy đủ khi tỷ lệ lỗi rất cao; việc đó có thể tạo log storm. Dùng counter, sampling và log tổng hợp theo cửa sổ thời gian. Description không phải mã nguyên nhân ổn định; cần đối chiếu client transport log, server log và telemetry của hạ tầng.

Nếu server log cho thấy handler nhận request và trả UNAVAILABLE có chủ đích, điều tra status mapping và dependency. Nếu không có dấu vết request ở server, ưu tiên kiểm tra DNS, endpoint discovery, network, TLS, proxy và listener. Tuy nhiên, thiếu log server không phải bằng chứng tuyệt đối vì log có thể mất hoặc request có thể bị chặn trước interceptor.

## 3. Xác định phạm vi ảnh hưởng

Bắt đầu bằng cách so sánh các chiều sau:

- **Một method:** kiểm tra logic hoặc dependency riêng của method đó.
- **Mọi method trên một service:** kiểm tra listener, service registration, instance health và shared dependency.
- **Nhiều provider cùng lúc:** kiểm tra network, DNS, service mesh, node, load balancer hoặc hạ tầng chung.
- **Một client version:** kiểm tra cấu hình channel, resolver, credentials, retry policy và rollout client.
- **Một zone/region:** kiểm tra endpoint health, routing, firewall, certificate và network path của vùng đó.
- **Một vài instance:** kiểm tra pod/node cụ thể, readiness, resource pressure và connection distribution.

Dùng tỷ lệ lỗi theo method và endpoint thay vì chỉ xem tổng status. Nếu một backend nhận phần lớn traffic và lỗi nhiều hơn, có thể load balancing không loại endpoint lỗi hoặc health signal chưa phản ánh khả năng xử lý RPC.

Một ma trận đơn giản giúp khoanh vùng:

| Quan sát | Hướng ưu tiên |
| --- | --- |
| Chỉ một method, một service | Handler, status mapping hoặc dependency riêng |
| Tất cả method trên một instance | Instance, listener, resource hoặc deployment |
| Tất cả instance của một provider | Rollout, config, shared dependency hoặc service registration |
| Nhiều provider qua cùng gateway | Gateway, mesh, DNS, network hoặc certificate |
| Chỉ một consumer | Client channel, credentials, resolver hoặc traffic pattern |
| Chỉ một zone | Routing, endpoint health, network và capacity theo zone |

## 4. Kiểm tra client channel và name resolution

gRPC Java ManagedChannel quản lý kết nối và chọn subchannel theo resolver/load balancing policy. Quan sát trạng thái channel có thể giúp xác định call đang kết nối hay liên tục thất bại:

- IDLE: channel chưa cần kết nối hoặc đã trở về idle.
- CONNECTING: đang thiết lập kết nối.
- READY: có kết nối sẵn sàng theo view của channel.
- TRANSIENT_FAILURE: kết nối hiện không dùng được; runtime có thể tiếp tục backoff/reconnect.
- SHUTDOWN: channel đã đóng và không thể nhận call mới.

Channel state không thay thế health check của service. READY không chứng minh mọi method hoặc dependency đều khỏe; TRANSIENT_FAILURE cũng có thể chỉ là một subchannel trong một channel có nhiều endpoint.

Các điểm cần kiểm tra ở client:
- Target URI có đúng scheme/authority và DNS name không?
- Resolver có trả về địa chỉ endpoint hiện hành không?
- Load balancing policy có được cấu hình đúng cho target không?
- Channel có bị shutdown sớm hoặc tạo lại liên tục không?
- Client có tạo channel mới cho từng request gây connection churn không?
- TLS authority, trust roots và certificate SAN có khớp hostname không?
- Call credentials có hết hạn hoặc refresh thất bại không?
- Deadline có quá ngắn so với thời gian kết nối và tải thực tế không?

Không tạo ManagedChannel mới cho mỗi RPC. Tái sử dụng channel theo lifecycle ứng dụng và tạo stub theo call options. Channel churn làm tăng handshake, DNS lookup và áp lực lên server.

Nếu dùng DNS resolver, kiểm tra phân giải từ đúng runtime/container của client. Một truy vấn DNS từ laptop không chứng minh pod production phân giải cùng kết quả. Kiểm tra TTL, cache, search domain và thay đổi endpoint sau rollout.

## 5. Kiểm tra DNS, load balancer và HTTP/2 path

UNAVAILABLE trên nhiều method hoặc nhiều client thường yêu cầu kiểm tra network path:

1. DNS có phân giải đúng service name và trả về endpoint đang ready không?
2. Kubernetes Service/EndpointSlice hoặc service registry có endpoint healthy không?
3. Load balancer có gửi traffic tới pod đã terminating hoặc chưa ready không?
4. Proxy/service mesh có hỗ trợ HTTP/2 end-to-end hoặc cấu hình gRPC upstream đúng không?
5. Firewall, NetworkPolicy, security group hoặc routing table có thay đổi không?
6. Có connection reset, GOAWAY, RST_STREAM hoặc idle timeout bất thường không?
7. Gateway có giới hạn connection/stream hoặc rate limit mới được áp dụng không?

Ví dụ lệnh Kubernetes để xem service và endpoint:

~~~bash
kubectl get svc -n <namespace>
kubectl get endpointslices -n <namespace> -l kubernetes.io/service-name=<service>
kubectl get pods -n <namespace> -o wide
kubectl describe svc <service> -n <namespace>
~~~

Dùng grpcurl để xác minh từ một môi trường có network path tương tự client:

~~~bash
grpcurl -vv -plaintext \
  -import-path src/main/proto \
  -proto shop/order/v1/order_service.proto \
  -d '{"orderId":"order-123"}' \
  <grpc-host>:<grpc-port> \
  shop.order.v1.OrderService/GetOrder
~~~

Ví dụ dùng plaintext và proto source để minh họa; trong môi trường TLS, bỏ -plaintext và cấu hình CA/client certificate theo đúng security policy. Không đưa bearer token hoặc secret trực tiếp vào shell history. Nếu grpcurl báo không kết nối được, ghi nhận lỗi resolver/transport và so sánh từ pod consumer, pod cùng namespace và một điểm kiểm tra khác.

Nếu một gateway nằm giữa client và server, thử kiểm tra cả đường trực tiếp tới service trong môi trường được phép. So sánh kết quả giúp xác định lỗi thuộc gateway hay provider. Không bypass security boundary trong production để “test nhanh”.

## 6. Kiểm tra Spring gRPC server và instance health

Trên provider, kiểm tra:

- Pod/container có running và ready không?
- Application context có khởi động hoàn tất không?
- gRPC listener có bind đúng port/address không?
- Service bean có được đăng ký và method có trả UNAVAILABLE do logic ứng dụng không?
- Có pod restart, OOMKilled, liveness failure hoặc rollout liên tục không?
- CPU throttling, heap pressure, GC pause, thread pool/worker queue hoặc file descriptor có tăng?
- Connection count, concurrent streams và inbound message size có vượt giới hạn?
- Graceful shutdown có drain traffic trước khi pod bị terminate không?

Lệnh kiểm tra mẫu:

~~~bash
kubectl get pods -n <namespace> -l app=<provider>
kubectl describe pod <pod> -n <namespace>
kubectl logs <pod> -n <namespace> --since=15m
kubectl get events -n <namespace> --sort-by=.lastTimestamp
~~~

Đối chiếu thời điểm lỗi với deployment, config change, secret/certificate rotation và node event. Nếu chỉ các pod mới lỗi, so sánh image digest, environment variables, mounted secrets, service port và readiness behavior giữa pod mới/cũ.

Readiness cần phản ánh khả năng nhận traffic của gRPC server. Một HTTP health endpoint xanh không nhất thiết chứng minh gRPC listener đã bind hoặc dependency thiết yếu đã sẵn sàng. Nếu dùng gRPC Health Checking Protocol, kiểm tra health status của service tương ứng và cách load balancer/clients sử dụng health signal đó.

## 7. Kiểm tra overload và dependency phía server

Một server có thể trả UNAVAILABLE khi không còn khả năng nhận hoặc xử lý thêm công việc. Tìm các dấu hiệu:

- CPU cao kéo dài hoặc throttling.
- Heap gần giới hạn, GC pause dài, allocation rate tăng.
- Worker/executor queue đầy, thread starvation hoặc connection pool cạn.
- Database connection timeout, pool exhaustion hoặc lock contention.
- HTTP downstream trả 5xx, timeout hoặc connection refused.
- Message broker, cache hoặc service discovery mất kết nối.
- Inbound message/metadata vượt giới hạn hoặc quá nhiều concurrent streams.

Phân biệt status UNAVAILABLE từ provider với status do client transport bằng cách đối chiếu server metrics và logs theo method. Nếu handler bắt đầu chạy rồi exception mapper trả UNAVAILABLE, tìm dependency/exception cụ thể. Nếu server không nhận call, quay lại network/endpoint path.

Không tăng thread pool hoặc connection pool một cách mù quáng. Tăng concurrency khi database đã quá tải có thể làm queue dài hơn và khuếch đại sự cố. Xác định bottleneck trước, sau đó điều chỉnh concurrency, pool size hoặc rate limit trong giới hạn tài nguyên thực tế.

## 8. Kiểm soát retry storm và giữ an toàn cho operation

UNAVAILABLE thường có thể là lỗi tạm thời, nhưng retry không phải lúc nào cũng an toàn. Retry policy phải giới hạn số lần thử, có exponential backoff, jitter và tổng deadline budget. Nếu mọi client retry cùng thời điểm, provider vừa phục hồi có thể bị dồn thêm tải.

Nguyên tắc:
- Chỉ retry method/operation được xác định là retry-safe hoặc idempotent.
- Giữ nguyên idempotency key qua các lần retry của cùng một ý định nghiệp vụ.
- Giới hạn max attempts và tổng thời gian retry theo deadline.
- Dùng exponential backoff có jitter; không retry vòng lặp tức thời.
- Giới hạn số call đồng thời và queue ở client.
- Tránh cấu hình retry ở nhiều tầng cùng lúc nếu không tính tổng số attempts.
- Không retry PERMISSION_DENIED, INVALID_ARGUMENT hoặc lỗi không thể tự hết.
- Với streaming RPC, xác định rõ resume cursor và duplicate handling trước khi reconnect.

Ví dụ policy service config có thể giới hạn retry cho method idempotent:

~~~json
{
  "methodConfig": [{
    "name": [{
      "service": "shop.order.v1.OrderService",
      "method": "GetOrder"
    }],
    "retryPolicy": {
      "maxAttempts": 3,
      "initialBackoff": "0.2s",
      "maxBackoff": "2s",
      "backoffMultiplier": 2,
      "retryableStatusCodes": ["UNAVAILABLE"]
    }
  }]
}
~~~

Đây là cấu trúc minh họa cho gRPC service config; cách đưa service config vào ManagedChannel phụ thuộc resolver và client configuration của ứng dụng. Không bật policy này cho CreateOrder nếu server chưa bảo đảm idempotency. Retry policy không thay thế deadline, bulkhead, rate limit hoặc circuit breaker.

Nếu provider đang quá tải, tạm giảm retry attempts hoặc tắt retry cho method gây tải; giới hạn ingress/concurrency và khôi phục capacity trước khi tăng traffic lại. Không dùng wait-for-ready hoặc retry vô hạn như cách che một service đang mất khả năng phục vụ.

## 9. Biện pháp giảm thiểu theo nguyên nhân

Chọn mitigation theo bằng chứng:

| Nguyên nhân đã xác nhận | Mitigation ưu tiên | Điều cần tránh |
| --- | --- | --- |
| Rollout mới gây lỗi trên mọi pod mới | Pause rollout hoặc rollback phiên bản đã biết tốt | Restart toàn bộ fleet khi chưa xác định |
| Một vài pod unhealthy | Loại pod khỏi traffic, khôi phục readiness hoặc thay pod | Đưa pod chưa ready trở lại load balancer |
| Capacity provider thiếu | Scale có kiểm soát, giảm ingress/concurrency, bảo vệ dependency | Tăng concurrency vô hạn |
| DNS/service discovery sai | Khôi phục record/registry và xác minh cache/TTL | Thay target đồng loạt mà không kiểm tra |
| Gateway/proxy lỗi HTTP/2 | Rollback config gateway hoặc sửa upstream protocol/timeout | Bỏ qua gateway/security controls trong production |
| Certificate/TLS lỗi | Khôi phục certificate chain, SAN, trust bundle hoặc rotation config | Tắt TLS verification |
| Dependency lỗi | Fail fast với status phù hợp, circuit break, khôi phục dependency | Retry dồn dập tới dependency đang chết |
| Retry storm | Giảm attempts, tăng backoff/jitter, rate limit | Tăng retry để “bù” lỗi |
| Client config sai | Rollback config hoặc phát hành client fix có kiểm soát | Tạo channel mới cho mỗi request |

Nếu rollback, kiểm tra cả compatibility của schema, database migration và dữ liệu đã ghi bởi phiên bản mới. Nếu scale out, xác minh dependency có đủ capacity để phục vụ thêm instance. Mỗi mitigation phải có người chịu trách nhiệm, thời điểm, tín hiệu kỳ vọng và điều kiện rollback mitigation.

## 10. Xác minh phục hồi và đóng sự cố

Sau khi áp dụng mitigation, không chỉ kiểm tra pod đang Running. Xác minh từ consumer path thực tế:

1. Request success rate phục hồi theo service/method.
2. Tỷ lệ UNAVAILABLE giảm về baseline trong một cửa sổ đủ dài.
3. DEADLINE_EXCEEDED và latency p95/p99 không tăng bất thường.
4. Endpoint count và readiness ổn định; không còn pod restart hoặc connection churn.
5. Client channel reconnect ổn định, không còn TRANSIENT_FAILURE kéo dài.
6. Dependency pool/queue, CPU, memory và GC trở về ngưỡng vận hành.
7. Retry attempts trên mỗi logical request trở về mức bình thường.
8. Synthetic RPC hoặc canary từ các zone quan trọng thành công.
9. Không có side effect trùng do client retry trong thời gian sự cố.

Chỉ đóng incident khi lỗi đã ổn định qua cửa sổ quan sát phù hợp và các consumer chính xác nhận phục hồi. Ghi lại thời điểm bắt đầu/kết thúc, phạm vi ảnh hưởng, root cause đã xác nhận hoặc còn giả thuyết, mitigation, version/config thay đổi và hành động phòng ngừa.

## 11. Bằng chứng cần giữ cho post-incident review

Thu thập:
- Error rate và request rate theo method/status/client version/zone.
- Client-side description, channel state và transport error đã redact.
- Server log theo request ID/trace ID và exception mapping.
- Pod restart, deployment event, readiness, resource và endpoint history.
- DNS resolution, load balancer/proxy logs và TLS certificate timeline.
- Dependency latency/error rate, pool usage và queue depth.
- Retry attempts, deadline distribution và số logical request so với physical attempts.

Không lưu token, authorization header, private key, payload cá nhân hoặc secret vào incident note. Nếu chưa xác định được nguyên nhân, ghi rõ giả thuyết và bằng chứng thiếu; không kết luận “server down” chỉ từ status UNAVAILABLE.

## 12. Checklist vận hành

- [ ] Xác nhận UNAVAILABLE tăng theo tỷ lệ, method và phạm vi.
- [ ] Phân biệt server-returned status với client/transport failure.
- [ ] So sánh theo client version, provider version, pod và zone.
- [ ] Kiểm tra channel state, DNS resolver và endpoint selection.
- [ ] Kiểm tra load balancer, proxy, HTTP/2, firewall và TLS.
- [ ] Kiểm tra Spring gRPC listener, readiness, restart và service registration.
- [ ] Kiểm tra CPU, memory, GC, queue, thread/connection pool và dependencies.
- [ ] Giới hạn retry bằng attempts, backoff, jitter và deadline budget.
- [ ] Bảo vệ operation không idempotent bằng idempotency key trước retry.
- [ ] Áp dụng mitigation theo bằng chứng và có điều kiện rollback.
- [ ] Xác minh success rate, latency, retry rate và dependency health phục hồi.
- [ ] Lưu evidence đã redact và ghi rõ root cause/unknowns.

**Tự kiểm tra**

**Câu 1.** UNAVAILABLE có luôn nghĩa là server process đã dừng không?

*Đáp án:* Không. Server có thể chủ động trả UNAVAILABLE; client runtime cũng có thể tạo status này khi connection, endpoint, proxy hoặc HTTP/2 transport không dùng được.

**Câu 2.** Vì sao phải tách UNAVAILABLE khỏi DEADLINE_EXCEEDED?

*Đáp án:* UNAVAILABLE mô tả khả năng phục vụ/kết nối không sẵn sàng; DEADLINE_EXCEEDED cho biết call vượt thời gian cho phép. Chúng có thể cùng tăng nhưng cần chẩn đoán khác nhau.

**Câu 3.** Khi nào được retry UNAVAILABLE?

*Đáp án:* Khi operation retry-safe hoặc idempotent, còn deadline budget, retry được giới hạn và có backoff/jitter. Với operation ghi, giữ idempotency key qua các lần retry.

**Câu 4.** Vì sao không nên tăng retry attempts khi provider quá tải?

*Đáp án:* Retry tạo thêm physical requests trên cùng logical traffic, làm queue và dependency quá tải nặng hơn. Cần giảm ingress/concurrency, khôi phục capacity và kiểm soát retry storm.

**Câu 5.** Khi nào incident có thể đóng?

*Đáp án:* Khi success rate và UNAVAILABLE trở về baseline qua cửa sổ quan sát đủ dài, latency/retry/dependency health ổn định và consumer path thực tế đã được xác minh.

Runbook UNAVAILABLE hiệu quả bắt đầu bằng việc xác định status đến từ server hay transport, rồi khoanh vùng theo method, client, endpoint và zone. Khôi phục endpoint/server/dependency theo bằng chứng, kiểm soát retry để tránh khuếch đại tải và chỉ đóng incident sau khi consumer path cùng các chỉ số độ tin cậy đã ổn định.
