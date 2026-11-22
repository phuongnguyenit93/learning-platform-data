# Load balancing qua proxy

## 1. Proxy đứng giữa client và nhiều backend

Trong **SPRING_GRPC**, client gọi service bằng gRPC Java, stub được sinh từ hợp đồng Protocol Buffers và thường chạy trong ứng dụng Spring. Khi đặt một proxy ở giữa, client kết nối đến một địa chỉ ổn định của proxy; proxy tiếp nhận kết nối hoặc từng RPC rồi chọn server instance phía sau.

~~~text
Spring gRPC client
       |
       | HTTP/2 + gRPC
       v
  Proxy / Envoy
       |
       +----> Orders instance A
       +----> Orders instance B
       +----> Orders instance C
~~~

Proxy có thể thực hiện load balancing, health checking, retry, timeout, TLS termination, routing theo metadata và quan sát traffic. Client không cần biết địa chỉ từng replica nếu proxy chịu trách nhiệm discovery và lựa chọn backend.

Hai bước chọn backend có thể cùng tồn tại:

1. Client-side load balancing chọn một proxy endpoint nếu có nhiều proxy.
2. Proxy-side load balancing chọn server instance phía sau.

Phải xác định rõ mỗi lớp đang cân bằng tải ở đâu để tránh cấu hình trùng lặp hoặc tạo retry lồng nhau.

## 2. Phân biệt L4 proxy và L7 gRPC-aware proxy

Khác biệt quan trọng nhất là proxy xử lý ở tầng kết nối TCP hay tầng giao thức HTTP/2/gRPC:

| Đặc điểm | L4 TCP proxy | L7 gRPC-aware proxy |
|---|---|---|
| Nhìn thấy | Kết nối TCP và địa chỉ mạng | HTTP/2 stream, `:path`, headers/metadata, trailers |
| Đơn vị chọn backend thường gặp | Kết nối TCP | Từng HTTP/2 stream/RPC |
| Đọc method gRPC | Không | Có |
| Route theo metadata | Không thể nếu chỉ TCP passthrough | Có thể nếu proxy được cấu hình |
| TLS passthrough | Có thể chuyển tiếp byte mã hóa | Muốn đọc RPC phải kết thúc TLS tại proxy |
| Hành vi với HTTP/2 multiplex | Nhiều RPC trên cùng connection thường đi cùng backend | Có thể route các stream khác nhau đến backend khác nhau |

gRPC multiplex nhiều RPC trên một HTTP/2 connection. Vì vậy, L4 proxy chọn backend khi thiết lập TCP connection; mọi stream trên connection đó thường cùng đi đến backend đã chọn. Nếu một client giữ một channel lâu dài, nhiều RPC có thể tập trung vào một backend dù proxy dùng thuật toán round robin cho **kết nối**.

L7 proxy hiểu HTTP/2 và có thể chọn backend theo từng RPC. Ví dụ, cùng một kết nối client-proxy có thể gửi `GetOrder` đến A và `WatchOrder` đến B nếu route/policy cho phép. Đây là lý do cần phân biệt load balancing theo connection với load balancing theo RPC.

## 3. Đường đi của một RPC qua L7 proxy

Một gRPC-aware proxy thường kết thúc HTTP/2 connection phía client, phân tích request headers, chọn upstream cluster/endpoint rồi tạo hoặc dùng lại HTTP/2 connection đến backend:

~~~mermaid
sequenceDiagram
    participant C as Spring gRPC client
    participant P as L7 proxy
    participant L as Upstream load balancer
    participant B as Backend instance
    C->>P: HTTP/2 stream /orders.v1.OrdersService/GetOrder
    P->>P: Đọc authority, path, metadata
    P->>L: Chọn endpoint trong cluster orders
    L->>B: Chuyển tiếp stream qua HTTP/2
    B-->>P: Message + gRPC trailers
    P-->>C: Message + grpc-status
~~~

Proxy phải hỗ trợ gRPC/HTTP/2 đúng cách. Nó cần giữ ngữ nghĩa của stream, flow control, headers và trailers chứa `grpc-status`/`grpc-message`. Nếu proxy hạ upstream hoặc downstream về HTTP/1.1 không tương thích, RPC có thể lỗi dù TCP connection vẫn mở.

Đường dẫn method gRPC thường có dạng `/package.Service/Method`, ví dụ `/orders.v1.OrdersService/GetOrder`. L7 proxy có thể route theo path, authority, metadata hoặc kết hợp các điều kiện đó.

## 4. Ví dụ proxy cluster với Envoy

Envoy có thể làm L7 proxy cho gRPC. Phần cluster upstream cần khai báo endpoint và bật HTTP/2 cho kết nối đến backend. Ví dụ fragment cấu hình:

~~~yaml
clusters:
  - name: orders
    type: STRICT_DNS
    connect_timeout: 1s
    lb_policy: ROUND_ROBIN
    load_assignment:
      cluster_name: orders
      endpoints:
        - lb_endpoints:
            - endpoint:
                address:
                  socket_address:
                    address: orders-a.internal
                    port_value: 9090
            - endpoint:
                address:
                  socket_address:
                    address: orders-b.internal
                    port_value: 9090
            - endpoint:
                address:
                  socket_address:
                    address: orders-c.internal
                    port_value: 9090
    typed_extension_protocol_options:
      envoy.extensions.upstreams.http.v3.HttpProtocolOptions:
        "@type": type.googleapis.com/envoy.extensions.upstreams.http.v3.HttpProtocolOptions
        explicit_http_config:
          http2_protocol_options: {}
~~~

Đây là fragment minh họa cluster, chưa phải file Envoy hoàn chỉnh. Listener, HTTP connection manager và route cần được cấu hình để nhận HTTP/2/gRPC ở phía client và chuyển tiếp đến cluster `orders`. `STRICT_DNS` yêu cầu Envoy phân giải các hostname upstream; trong môi trường khác có thể dùng endpoint từ EDS/xDS hoặc cơ chế discovery phù hợp.

`ROUND_ROBIN` phân phối lựa chọn upstream trong số endpoint đủ điều kiện. Nếu cần weighted cluster, locality, outlier detection hoặc consistent hashing, phải cấu hình extension/policy tương ứng và xác minh khả năng của phiên bản Envoy đang chạy.

## 5. Spring client chỉ cần kết nối đến proxy endpoint

Khi proxy công bố một hostname ổn định, Spring client có thể tạo channel đến địa chỉ đó:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersGrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel ordersChannel() {
        return ManagedChannelBuilder
                .forTarget("dns:///orders-proxy.internal:443")
                .useTransportSecurity()
                .build();
    }
}
~~~

Stub được tạo từ channel dùng chung:

~~~java
import com.example.orders.rpc.OrdersGrpc;
import io.grpc.ManagedChannel;
import org.springframework.stereotype.Component;

@Component
public class OrdersClient {
    private final OrdersGrpc.OrdersBlockingStub stub;

    public OrdersClient(ManagedChannel ordersChannel) {
        this.stub = OrdersGrpc.newBlockingStub(ordersChannel);
    }
}
~~~

Client không cần khai báo IP của A, B và C nếu proxy quản lý upstream discovery. Nếu có nhiều proxy endpoint, channel có thể dùng resolver và policy riêng để chọn proxy; sau đó proxy tiếp tục chọn backend. Không tạo channel mới cho mỗi RPC.

Trong service mesh sidecar, địa chỉ target có thể là local proxy port. Cần xác định traffic được sidecar bắt theo iptables/transparent proxy hay client kết nối trực tiếp đến listener của sidecar; hai mô hình có cấu hình TLS và authority khác nhau.

## 6. Proxy và TLS: passthrough, termination, re-encryption

Proxy cần một mô hình TLS rõ ràng:

| Mô hình | Client → proxy | Proxy → backend | Proxy đọc được RPC? |
|---|---|---|---|
| TCP/TLS passthrough | TLS end-to-end qua proxy | Cùng TLS stream đến server | Không đọc được path/metadata gRPC |
| TLS termination | Client TLS kết thúc tại proxy | Có thể plaintext trong mạng tin cậy | Có, proxy xử lý HTTP/2/gRPC |
| TLS termination + re-encryption | TLS kết thúc tại proxy | Proxy tạo TLS mới đến backend | Có, đồng thời mã hóa lại upstream |

Nếu cần route theo method hoặc metadata, proxy phải nhìn thấy HTTP/2 headers, do đó TLS thường phải kết thúc tại proxy. Với re-encryption, proxy phải xác minh certificate của backend và dùng SNI/authority đúng. Không tắt certificate validation để giải quyết lỗi kết nối.

Trong môi trường production, cân nhắc mTLS ở cả hai chặng:

- Client xác thực proxy.
- Proxy xác thực backend.
- Backend có thể xác thực danh tính workload của proxy nếu mô hình bảo mật yêu cầu.

gRPC yêu cầu HTTP/2. Với TLS, ALPN cần thương lượng `h2`; proxy không được hạ giao thức upstream/downstream sang HTTP/1.1 cho gRPC native.

## 7. Health checking và loại backend lỗi

Proxy thường có thể kết hợp health checking chủ động và outlier detection thụ động:

- **Active health check:** proxy định kỳ gọi health endpoint/RPC để xác định backend có phục vụ được không.
- **Passive outlier detection:** proxy quan sát lỗi hoặc latency của traffic thật và tạm ejection backend bất thường.
- **Endpoint discovery:** registry/xDS cập nhật instance được công bố.
- **Load balancing:** picker chọn trong tập endpoint hiện còn đủ điều kiện.

Health checking cần phản ánh khả năng phục vụ nghiệp vụ. TCP connect thành công không chứng minh database hoặc dependency bắt buộc đang khỏe. Với gRPC, có thể dùng `grpc.health.v1.Health/Check` hoặc cơ chế health tương thích mà proxy hỗ trợ.

Không nên cấu hình active check quá dày hoặc gọi dependency nặng ở mỗi lần kiểm tra. Khi backend flapping giữa healthy/unhealthy, dùng ngưỡng, khoảng ổn định và ejection duration phù hợp để tránh liên tục đưa backend vào/ra khỏi pool.

## 8. Retry, deadline và timeout ở proxy

Proxy có thể áp dụng retry cho request đủ điều kiện, nhưng cần phối hợp với retry ở gRPC client và tầng ứng dụng. Nếu cả ba tầng đều retry nhiều lần, một logical RPC có thể tạo ra số attempt lớn hơn dự kiến.

Ví dụ ngân sách thời gian:

~~~text
Client deadline: 3 giây
  Proxy route timeout: tối đa 2.5 giây
    Attempt upstream A: 0.8 giây
    Backoff: 0.2 giây
    Attempt upstream B: phần thời gian còn lại
~~~

Các nguyên tắc:

- Deadline của client phải bao trùm tổng thời gian ở proxy và backend.
- Per-try timeout phải nhỏ hơn ngân sách còn lại của logical RPC.
- Proxy phải xử lý đúng `grpc-timeout` và status/trailers.
- Chỉ retry status và method có thể retry an toàn.
- Với side effect, dùng idempotency key để tránh thực hiện trùng.
- Chọn một tầng điều phối retry chính hoặc tính rõ giới hạn attempt tổng giữa các tầng.

`UNAVAILABLE` không luôn có nghĩa backend đã chết; backend đang kết nối tốt vẫn có thể trả status này vì dependency nội bộ. Retry không tự loại backend khỏi pool. Muốn ejection cần health/outlier/discovery policy.

## 9. Server streaming và timeout của proxy

Một server streaming RPC là một HTTP/2 stream kéo dài qua proxy. Proxy phải giữ stream và flow control trong suốt thời gian hoạt động:

~~~text
Client
  -> Proxy
      -> Backend A
      <- event 1
      <- event 2
      <- event 3
  <- Proxy
<- Client
~~~

Các timeout HTTP thông thường có thể không phù hợp với stream dài. Cần xem xét:

- **Idle timeout:** khoảng thời gian không có dữ liệu trước khi proxy đóng stream.
- **Maximum stream duration:** giới hạn tổng tuổi stream nếu có.
- **Connection drain:** cách proxy xử lý HTTP/2 connection khi upstream hoặc proxy shutdown.
- **Flow control/buffer:** giới hạn bộ nhớ khi consumer đọc chậm.
- **Keepalive:** cơ chế phát hiện connection chết, phải phối hợp giữa client, proxy và server.

Đừng vô hiệu hóa mọi timeout một cách mặc định. Chọn idle timeout phù hợp với nhịp event, đồng thời dùng deadline hoặc giới hạn tuổi stream ở tầng nghiệp vụ. Nếu backend bị ejection hoặc dừng giữa stream, proxy không thể chuyển phần còn lại của cùng RPC sang backend khác; client cần reconnect/resume bằng cursor hoặc sequence.

## 10. Routing theo method, metadata và phiên bản

L7 proxy có thể route theo path gRPC, authority hoặc metadata. Ví dụ:

- `/orders.v1.OrdersService/GetOrder` đến cluster ổn định.
- `/orders.v1.OrdersService/WatchOrder` đến cluster có năng lực stream.
- Metadata `x-tenant-tier` chọn nhóm backend theo tier.
- Metadata `x-canary: true` route một nhóm request đến phiên bản thử nghiệm.

Metadata chỉ có tác dụng khi proxy được cấu hình đọc trường đó. Một gRPC client tự gửi `x-routing-key` không tự tạo sticky routing. Proxy cần policy hash/affinity hoặc route cụ thể.

Không dùng access token, email hoặc dữ liệu nhạy cảm làm khóa định tuyến. Proxy cũng không thay thế authorization: backend vẫn cần xác thực caller và kiểm tra quyền. Nếu proxy sửa/xóa metadata, phải thống nhất hợp đồng giữa gateway, client và backend.

## 11. Graceful shutdown và cập nhật upstream pool

Khi backend sắp dừng, proxy cần ngừng gửi RPC mới đến endpoint đó nhưng vẫn cho RPC hiện tại thời gian hoàn tất:

1. Backend báo readiness false hoặc deregister khỏi registry.
2. Proxy nhận cập nhật endpoint/health và loại backend khỏi lựa chọn RPC mới.
3. Backend/proxy drain connection và stream đang hoạt động theo grace period.
4. RPC còn lại được hoàn tất hoặc kết thúc theo status đã định nghĩa.
5. Client reconnect/resume stream nếu hợp đồng hỗ trợ.

Deregister khỏi registry không nhất thiết đóng ngay các HTTP/2 connection đã tồn tại. Proxy có thể cần chủ động drain upstream connection. Tương tự, restart proxy có thể ảnh hưởng nhiều stream dù backend vẫn khỏe; triển khai nhiều proxy replica và drain có kiểm soát để giảm gián đoạn.

## 12. Kiểm thử proxy load balancing

Một test chỉ gọi một backend qua proxy không chứng minh proxy phân phối tải. Cần nhiều backend có instance ID, proxy thật hoặc môi trường tương đương và quan sát lựa chọn:

| Kịch bản | Điều cần xác minh |
|---|---|
| Nhiều backend healthy | RPC mới được phân phối theo policy đã cấu hình |
| Một backend unhealthy | RPC mới không được gửi đến backend đã bị loại |
| L4 proxy với một HTTP/2 connection | Nhiều RPC multiplex có thể cùng đến một backend |
| L7 proxy với nhiều stream | Các RPC có thể được route độc lập theo policy |
| TLS termination/re-encryption | ALPN `h2`, certificate và authority được xác minh ở cả hai chặng |
| Metadata routing | Chỉ metadata được cho phép mới ảnh hưởng route |
| Proxy retry | Số attempt không vượt ngân sách và không lặp side effect |
| Deadline ngắn | Proxy không giữ RPC lâu hơn deadline client |
| Stream dài | Idle timeout/flow control không cắt stream hợp lệ |
| Backend drain | RPC mới chuyển đi; RPC đang chạy được xử lý theo grace period |
| Proxy restart | Client reconnect và stream resume nếu cần |

Nên kiểm tra cả gRPC trailers/status, không chỉ HTTP status hoặc TCP connection. In-process gRPC test không mô phỏng đầy đủ proxy HTTP/2, TLS, routing và timeout; các hành vi đó cần integration test với Envoy hoặc proxy thực tế của hệ thống.

## 13. Quan sát và chẩn đoán

Để tìm lỗi, cần quan sát riêng từng chặng:

- Số kết nối client-proxy và proxy-backend.
- RPC theo method, route, cluster và upstream instance.
- Latency ở proxy, thời gian upstream và thời gian chờ queue.
- HTTP status cùng `grpc-status` trong trailers.
- Số backend healthy/ejected và thời điểm thay đổi.
- Retry attempt, timeout, reset và connection drain.
- Số stream đang mở, tuổi stream và idle timeout.
- Lỗi TLS/ALPN theo chặng client-proxy hoặc proxy-backend.

Nếu mọi RPC đi vào một backend, kiểm tra proxy đang hoạt động L4 hay L7, HTTP/2 upstream có được bật không và policy đang phân phối theo connection hay stream. Nếu RPC nhận `UNAVAILABLE`, đối chiếu gRPC trailers với log proxy/backend để biết lỗi phát sinh ở đâu.

## 14. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Nghĩ L4 round robin phân phối từng RPC | Nhiều stream trên một connection cùng đến một backend | Dùng L7 gRPC-aware proxy nếu cần route theo RPC |
| Proxy upstream dùng HTTP/1.1 | gRPC native lỗi hoặc không giữ đúng semantics | Bật HTTP/2 upstream và ALPN `h2` |
| TLS passthrough nhưng mong route theo metadata | Proxy không đọc được headers mã hóa | Dùng TLS termination/re-encryption có kiểm soát |
| Timeout proxy ngắn hơn nhịp stream | Stream hợp lệ bị đóng giữa chừng | Cấu hình idle/max duration theo hợp đồng stream |
| Client và proxy cùng retry không giới hạn | Khuếch đại tải, vượt deadline | Phối hợp ngân sách retry toàn tuyến |
| Chỉ kiểm tra TCP health | Backend lỗi dependency vẫn nhận RPC | Dùng gRPC health/readiness phù hợp |
| Route theo metadata do caller tự khai báo | Có thể bị giả mạo để né quota hoặc đổi backend | Xác thực, chuẩn hóa và giới hạn metadata routing |
| Drain backend mà không drain connection | RPC/stream đang chạy bị reset đột ngột | Graceful drain và cơ chế resume |

**Ghi nhớ:** Proxy có thể cân bằng tải ở tầng TCP hoặc tầng HTTP/2/gRPC. L4 thường chọn backend theo connection nên các RPC multiplex có thể cùng đến một instance; L7 hiểu từng stream và có thể route theo method/metadata. Spring client kết nối đến proxy endpoint bằng một channel dùng chung, còn proxy quản lý upstream discovery, health và policy. Phải giữ HTTP/2, TLS authority, gRPC trailers, deadline và timeout stream đúng; retry, drain và resume cần được phối hợp trên toàn tuyến.
