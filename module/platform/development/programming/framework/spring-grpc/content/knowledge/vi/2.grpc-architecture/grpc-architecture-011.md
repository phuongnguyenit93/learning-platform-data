# Một cuộc gọi qua proxy hoặc gateway

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả đường đi của một gRPC RPC từ Spring client, qua proxy/gateway, tới backend và quay lại.
- Phân biệt proxy L4 chuyển tiếp TCP với proxy L7 hiểu HTTP/2 và định tuyến theo gRPC method.
- Nhận biết các yêu cầu của gRPC trên HTTP/2: pseudo-header, path, content type, message frame và trailers.
- Giải thích TLS passthrough, TLS termination và re-encryption giữa gateway với backend.
- Cấu hình một tuyến gRPC cơ bản qua Envoy và kết nối từ Spring client.
- Phối hợp deadline, timeout, streaming, metadata, health, retry và graceful draining qua nhiều hop.
- Chẩn đoán lỗi phát sinh tại gateway thay vì nhầm chúng với lỗi nghiệp vụ của server.

## 1. Đường đi end-to-end của một gRPC call

Trong hệ sinh thái **SPRING_GRPC**, Spring client gọi service bằng generated stub. Ở môi trường triển khai, client thường không kết nối trực tiếp tới một instance; lời gọi đi qua reverse proxy, ingress, API gateway hoặc service mesh trước khi đến gRPC server.

~~~mermaid
sequenceDiagram
    participant App as Spring client
    participant Proxy as Proxy / Gateway
    participant Server as Spring gRPC server
    App->>Proxy: HTTP/2 + gRPC request
    Note over App,Proxy: TLS có thể kết thúc tại gateway
    Proxy->>Server: HTTP/2 upstream + gRPC request
    Server-->>Proxy: Response DATA + trailers
    Proxy-->>App: Response DATA + trailers
    Note over App,Server: grpc-status kết thúc RPC
~~~

Một proxy có thể thực hiện một số việc trên đường đi:

- Chọn backend theo hostname/authority, gRPC service và method.
- Cân bằng tải, kiểm tra health và loại endpoint không sẵn sàng.
- Kết thúc TLS, xác thực ở edge hoặc thiết lập TLS mới tới backend.
- Áp chính sách timeout, giới hạn kết nối/stream và điều tiết tải.
- Ghi access log, trace và metrics cho từng RPC.
- Áp dụng chính sách mạng hoặc xác thực tập trung.

Cần xác định rõ proxy đang hoạt động ở **L4** hay **L7**, có hiểu gRPC hay chỉ chuyển tiếp byte TCP, và HTTP/2 được dùng trên từng chặng như thế nào. Những lựa chọn đó quyết định gateway có thể định tuyến theo method, đọc status hay chuyển tiếp trailers hay không.

## 2. gRPC request trên HTTP/2 có cấu trúc gì?

Một gRPC method thường được truyền bằng HTTP/2 POST. Ví dụ:

~~~text
:method: POST
:scheme: https
:authority: orders.example.com
:path: /demo.orders.v1.OrderService/GetOrder
content-type: application/grpc
te: trailers
grpc-timeout: 800m
x-request-id: req-7f3a
~~~

Các trường quan trọng:

| Thành phần | Vai trò |
| --- | --- |
| **:authority** | Host/service authority của request; liên quan định tuyến và TLS identity |
| **:path** | Đường dẫn đầy đủ của RPC: /package.Service/Method |
| **content-type** | Thường là application/grpc hoặc biến thể được hỗ trợ |
| **te: trailers** | Báo phía nhận rằng caller hỗ trợ trailers |
| **grpc-timeout** | Ngân sách thời gian còn lại nếu client đặt deadline |
| **custom metadata** | Request ID, trace context hoặc thông tin ứng dụng được phép truyền |

Body không phải JSON thông thường. Mỗi gRPC message có prefix 5 byte gồm cờ nén và độ dài message, sau đó là bytes đã serialize theo protobuf. Với streaming RPC, HTTP/2 DATA có thể mang nhiều gRPC message theo thứ tự.

Phản hồi thường có initial headers, một hoặc nhiều DATA message và trailing HEADERS. Trong trailers có **grpc-status**; mã 0 là OK. HTTP status 200 không bảo đảm RPC thành công.

~~~text
Response:
  HEADERS: :status=200, content-type=application/grpc
  DATA:    [gRPC message prefix][protobuf response]
  HEADERS (trailers, END_STREAM):
           grpc-status: 0
~~~

Proxy L7 cần xử lý đúng HTTP/2 và gRPC framing, đồng thời giữ nguyên semantics của trailers. Nếu proxy chỉ nhìn HTTP status hoặc loại bỏ trailers, client có thể mất status thực của RPC.

## 3. Proxy L4 và gateway L7 khác nhau thế nào?

| Đặc điểm | L4 proxy / TCP load balancer | L7 proxy hiểu gRPC |
| --- | --- | --- |
| Tầng hoạt động | TCP/transport | HTTP/2 và HTTP semantics |
| Định tuyến theo gRPC method | Không | Có thể, dựa trên :path |
| Đọc custom metadata | Không hiểu nội dung HTTP/2 | Có thể đọc/allowlist metadata |
| Quan sát grpc-status/trailers | Không phân tích được khi chỉ passthrough | Có thể ghi nhận nếu hỗ trợ gRPC |
| TLS termination | Có thể passthrough hoặc terminate theo cấu hình | Thường terminate để xử lý HTTP/2; có thể mã hóa lại upstream |
| Phù hợp | Chuyển tiếp kết nối, giữ end-to-end TLS | Routing, policy, auth, observability ở tầng RPC |

L4 proxy có thể phân phối TCP connection giữa các backend, nhưng gRPC thường multiplex nhiều RPC trên một HTTP/2 connection dài hạn. Vì vậy, một connection được chọn tới backend A có thể mang nhiều RPC tới A trong suốt thời gian sống của connection. L4 load balancing không đồng nghĩa cân bằng từng RPC.

L7 proxy có thể định tuyến theo hostname và path, nhưng phải hỗ trợ HTTP/2 ở phía client và upstream. Một gateway chỉ hỗ trợ HTTP/1.1 cho upstream sẽ không tự động trở thành proxy gRPC chuẩn chỉ vì nhận được HTTP request.

**gRPC-Web là trường hợp riêng.** Trình duyệt thường không mở native gRPC HTTP/2 theo cách client Java thực hiện; nó dùng gRPC-Web và cần proxy/translator hỗ trợ chuyển đổi. Không nhầm gRPC-Web với việc chuyển native gRPC sang HTTP/1.1 một cách trong suốt.

## 4. Hai chặng HTTP/2 và cách định tuyến

Khi L7 gateway terminate kết nối phía client, thường có hai chặng độc lập:

~~~text
Spring client
  -- HTTP/2 over TLS -->
Gateway / Envoy
  -- HTTP/2 over TLS hoặc h2c -->
Spring gRPC server
~~~

Gateway đọc authority và path, sau đó chọn cluster/backend. Ví dụ route theo service prefix:

~~~text
/demo.orders.v1.OrderService/
    -> cluster: orders_grpc
        -> orders-1.internal:8443
        -> orders-2.internal:8443
~~~

Nên route theo **service/method đã công bố**, không dùng wildcard rộng hơn mức cần thiết. Cấu hình phải giữ đúng authority và TLS server name phù hợp với certificate upstream. Nếu gateway thay authority để định tuyến nội bộ, cần xác định riêng giá trị dùng cho routing và giá trị dùng xác minh danh tính TLS.

Với native gRPC, upstream cluster phải thương lượng HTTP/2. Một proxy có thể terminate TLS ở listener rồi tạo TLS connection mới tới backend; cũng có thể dùng upstream cleartext HTTP/2 (h2c) trong mạng nội bộ được kiểm soát. Lựa chọn h2c cần được giới hạn trong network trust boundary và không nên mặc định dùng cho lưu lượng qua mạng không tin cậy.

## 5. Ví dụ cấu hình Envoy cho tuyến gRPC

Đoạn cấu hình rút gọn dưới đây minh họa listener HTTP/2, route theo service path và upstream cluster bật HTTP/2. Đây là phần khung định tuyến; production cần bổ sung listener TLS/certificate, access log, health check, limits và policy triển khai.

~~~yaml
static_resources:
  listeners:
    - name: grpc_listener
      address:
        socket_address:
          address: 0.0.0.0
          port_value: 8443
      filter_chains:
        - filters:
            - name: envoy.filters.network.http_connection_manager
              typed_config:
                "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
                stat_prefix: grpc_ingress
                codec_type: AUTO
                route_config:
                  name: grpc_routes
                  virtual_hosts:
                    - name: orders
                      domains: ["orders.example.com"]
                      routes:
                        - match:
                            prefix: "/demo.orders.v1.OrderService/"
                          route:
                            cluster: orders_grpc
                            timeout: 0s
                http_filters:
                  - name: envoy.filters.http.router
                    typed_config:
                      "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router

  clusters:
    - name: orders_grpc
      type: STRICT_DNS
      connect_timeout: 1s
      load_assignment:
        cluster_name: orders_grpc
        endpoints:
          - lb_endpoints:
              - endpoint:
                  address:
                    socket_address:
                      address: orders.internal
                      port_value: 8443
      typed_extension_protocol_options:
        envoy.extensions.upstreams.http.v3.HttpProtocolOptions:
          "@type": type.googleapis.com/envoy.extensions.upstreams.http.v3.HttpProtocolOptions
          explicit_http_config:
            http2_protocol_options: {}
~~~

Trong ví dụ, **timeout: 0s** tắt route timeout tổng của Envoy cho tuyến này; nó không có nghĩa ứng dụng nên bỏ deadline. Client vẫn cần đặt **gRPC deadline** theo từng RPC, và gateway/server cần giới hạn tài nguyên, thời lượng stream hoặc idle theo chính sách riêng. Với streaming, không đặt một timeout ngắn áp dụng chung khiến stream hợp lệ bị cắt giữa chừng.

**codec_type: AUTO** cho phép HTTP connection manager nhận diện protocol được thương lượng; cấu hình TLS listener thực tế cần ALPN h2 để native gRPC qua TLS. Upstream **http2_protocol_options** bảo đảm Envoy dùng HTTP/2 tới backend. Hãy xác minh cú pháp với phiên bản Envoy đang triển khai vì API cấu hình có thể thay đổi theo version.

## 6. Kết nối từ Spring client qua gateway

Spring client chỉ cần target của gateway nếu gateway là điểm vào ổn định. Ví dụ grpc-java:

~~~java
package dev.example.orders.client;

import dev.example.orders.v1.OrderServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderGrpcClientConfig {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel orderChannel() {
        return ManagedChannelBuilder
                .forTarget("dns:///orders.example.com:8443")
                .useTransportSecurity()
                .build();
    }

    @Bean
    OrderServiceGrpc.OrderServiceBlockingStub orderStub(
            ManagedChannel orderChannel) {
        return OrderServiceGrpc.newBlockingStub(orderChannel);
    }
}
~~~

Service dùng stub được inject và đặt deadline cho từng RPC:

~~~java
GetOrderResponse response = orderStub
        .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
        .getOrder(
                GetOrderRequest.newBuilder()
                        .setOrderId("order-42")
                        .build());
~~~

Trong production, Channel phải tin cậy certificate của gateway và xác minh hostname/authority đúng với certificate. Nếu gateway dùng mTLS tới backend, phần certificate upstream được cấu hình ở gateway; client không tự động xác thực trực tiếp backend sau khi TLS đã kết thúc tại gateway.

Không tạo Channel cho từng request. Reuse Channel giúp giữ resolver/transport ổn định, giảm handshake và tận dụng HTTP/2 multiplexing.

## 7. TLS passthrough, termination và re-encryption

Có ba mô hình thường gặp:

~~~text
A. TLS passthrough
Client == TLS end-to-end == Gateway L4 == TLS == Server

B. TLS termination
Client == TLS ==> Gateway -- h2c/internal network --> Server

C. TLS termination + re-encryption
Client == TLS ==> Gateway == TLS/mTLS ==> Server
~~~

| Mô hình | Gateway nhìn thấy gì? | Khi phù hợp |
| --- | --- | --- |
| **Passthrough** | Không giải mã HTTP/2/gRPC payload | Muốn TLS end-to-end và chỉ cần chuyển tiếp TCP/SNI |
| **Termination** | HTTP/2 headers, path và metadata sau khi giải mã | Cần L7 routing, auth, policy hoặc observability tại edge |
| **Re-encryption** | Đọc request ở gateway; mã hóa lại chặng upstream | Cần L7 features và bảo vệ traffic nội bộ bằng TLS/mTLS |

Với passthrough, gateway không thể định tuyến theo gRPC method hoặc đọc grpc-status vì TLS payload vẫn được mã hóa. Với termination, gateway trở thành một trust boundary: phải bảo vệ private key, giới hạn quyền đọc metadata và ghi log, đồng thời xác minh certificate upstream nếu có re-encryption.

TLS termination không có nghĩa backend tự động được tin cậy. Nếu gateway gọi backend bằng h2c, bảo vệ mạng nội bộ, network policy và quyền truy cập backend vẫn cần được thiết kế rõ ràng. Với hệ thống yêu cầu xác thực workload giữa các service, mTLS upstream là lựa chọn thường dùng.

## 8. Deadline, timeout và streaming qua gateway

Một RPC đi qua nhiều hop:

~~~text
Client deadline: 1200 ms
   |
   +-- Gateway routing/queue/connect: 100 ms
   |
   +-- Upstream server xử lý: 850 ms
   |
   +-- Response qua gateway về client: 100 ms
       Tổng ví dụ: 1050 ms
~~~

Deadline của client là ngân sách tổng. Gateway có thể áp route timeout, upstream connect timeout, idle timeout hoặc max stream duration; đây là các giới hạn khác nhau và phải phối hợp với deadline gRPC.

- **Client deadline**: giới hạn caller chờ kết quả của RPC.
- **Gateway route timeout**: giới hạn thời gian route/request ở proxy; cấu hình mặc định có thể không phù hợp với streaming.
- **Connect timeout**: giới hạn thời gian thiết lập upstream connection.
- **Idle timeout**: giới hạn khoảng thời gian stream không có hoạt động.
- **Max stream duration**: giới hạn tổng thời gian một stream tồn tại, nếu được cấu hình.

Không đặt gateway timeout ngắn hơn mọi deadline client một cách vô tình; client có thể nhận lỗi do proxy trước khi server hoàn tất. Ngược lại, route không giới hạn cũng không nên đồng nghĩa tài nguyên vô hạn: cần kiểm soát concurrent streams, idle streams và thời lượng tối đa theo use case.

Với server-streaming hoặc bidirectional streaming, proxy phải giữ stream mở và chuyển tiếp DATA/trailers đúng thứ tự. Một timeout/idle policy được thiết kế cho REST request ngắn có thể cắt gRPC stream hợp lệ. Nếu stream dài cần heartbeat, phải phối hợp keepalive/ping policy của client, server và proxy; HTTP/2 PING không thay thế message nghiệp vụ hoặc deadline.

## 9. Metadata, trailers và status qua gateway

Gateway L7 có thể đọc hoặc thêm metadata, nhưng nên dùng allowlist cho các key cần thiết:

- Cho phép trace context và request ID đã được chuẩn hóa.
- Chỉ chuyển authorization metadata tới backend khi kiến trúc yêu cầu và đã kiểm soát ranh giới tin cậy.
- Không ghi token, cookie hoặc dữ liệu cá nhân vào access log.
- Không tự ghi đè các trường reserved như **grpc-status**, **grpc-message**, **grpc-timeout**.
- Giữ nguyên custom trailers cần thiết nếu gateway/policy hỗ trợ; kiểm thử đường lỗi lẫn đường thành công.

Khi server trả HTTP/2 trailers với **grpc-status: 5** (NOT_FOUND), gateway cần chuyển status đó tới client. Nếu gateway chuyển thành HTTP 404 nhưng không tạo phản hồi gRPC hợp lệ, native gRPC client có thể báo **UNKNOWN** hoặc lỗi protocol thay vì NOT_FOUND.

Tương tự, lỗi phát sinh ngay tại gateway có thể không có response protobuf từ backend. Gateway phải trả một phản hồi gRPC hợp lệ với status/trailers nếu muốn native gRPC client nhận được mã lỗi có nghĩa. Hãy kiểm tra behavior cụ thể của gateway/version đang dùng, đặc biệt cho lỗi upstream reset, route timeout và connection failure.

## 10. Retry và health routing tại gateway

Gateway có thể có retry policy cho một số lỗi upstream, nhưng retry ở proxy có cùng rủi ro nghiệp vụ như retry ở client. Nếu backend đã commit một thao tác ghi trước khi connection reset, proxy retry có thể tạo tác dụng phụ lặp lại.

- Chỉ retry method có semantics an toàn hoặc có idempotency key.
- Giới hạn số attempt và tổng thời gian retry trong deadline.
- Dùng backoff/jitter phù hợp để tránh retry storm.
- Không retry một streaming RPC đã gửi/nhận một phần message như thể đó là unary request mới.
- Ghi nhận số attempt và backend cuối cùng để điều tra.

Health check của gateway cũng khác connectivity của gRPC client. Gateway cần biết endpoint nào được phép nhận traffic; có thể dùng health endpoint, gRPC health protocol hoặc cơ chế discovery phù hợp. Một TCP port mở chưa chứng minh ứng dụng đang SERVING.

Khi deploy phiên bản mới, gateway và backend cần **connection draining**. Backend nên ngừng nhận RPC mới, cho RPC đang chạy hoàn tất trong giới hạn, sau đó đóng connection. Với HTTP/2, GOAWAY có thể giúp báo peer không mở stream mới trên connection; client/gateway vẫn cần xử lý RPC đang hoạt động và reconnect theo policy.

## 11. Quan sát và chẩn đoán theo từng hop

Một request qua gateway có thể thất bại ở client, gateway, upstream connection hoặc server handler. Cần liên kết logs/traces bằng request ID hoặc trace context và đo theo từng chặng:

| Dấu hiệu | Nơi kiểm tra đầu tiên |
| --- | --- |
| Client không kết nối được gateway | DNS, TCP, TLS, ALPN h2, certificate/authority |
| Gateway trả lỗi trước khi có upstream | Route match, authority, listener/filter, auth policy |
| Gateway không kết nối được backend | Cluster endpoint, upstream TLS/HTTP2, connect timeout |
| Client nhận UNKNOWN thay vì status nghiệp vụ | Gateway có chuyển trailers và grpc-status đúng không |
| Unary RPC timeout | Client deadline, route timeout, upstream latency |
| Streaming RPC bị ngắt sau thời gian cố định | Idle timeout, max stream duration, proxy drain |
| Metadata mất ở backend | Header allowlist, normalization, proxy policy |
| Tải dồn vào một backend | L4 connection balancing, HTTP/2 reuse, L7 LB policy |
| Lỗi chỉ xảy ra sau deploy | GOAWAY, connection draining, endpoint discovery và version compatibility |

Metrics hữu ích gồm request count theo full method name, status code, upstream cluster, latency từng hop, active streams, connection errors, retries và timeout. Tránh dùng request ID, user ID hoặc token làm metric labels vì cardinality và rủi ro lộ dữ liệu.

## 12. Kiểm thử một call qua gateway

Kiểm thử cần đi qua đúng đường mạng triển khai, không chỉ gọi trực tiếp handler:

1. **Routing:** gọi method hợp lệ và xác minh đúng cluster/backend nhận request; thử path/authority sai.
2. **HTTP/2:** xác nhận ALPN h2 ở listener TLS và HTTP/2 upstream tới server.
3. **TLS:** thử certificate hợp lệ, hostname sai, trust chain sai và mTLS upstream nếu dùng.
4. **Trailers:** tạo một RPC trả NOT_FOUND/INVALID_ARGUMENT và xác minh client nhận đúng grpc-status cùng custom trailer được phép.
5. **Deadline:** đặt deadline ngắn hơn thời gian xử lý; xác định hop nào kết thúc RPC và status client quan sát.
6. **Streaming:** gửi nhiều message trong thời gian dài; kiểm tra idle timeout, flow control và trailers cuối stream.
7. **Failure/draining:** dừng backend hoặc deploy phiên bản mới; quan sát upstream reset, GOAWAY, reconnect và RPC đang chạy.
8. **Security/logging:** xác minh authorization được chuyển đúng phạm vi và token không xuất hiện trong access log.

**grpcurl** có thể hỗ trợ kiểm tra endpoint gRPC nếu server bật reflection hoặc caller cung cấp proto descriptor. Nhưng một lệnh grpcurl thành công không thay thế kiểm thử concurrency, streaming dài hạn, retry và connection draining.

## 13. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Chạy Spring gRPC server với method **GetOrder** và một Spring client gọi qua hostname gateway.
2. Cấu hình Envoy listener HTTP/2 và route theo prefix /demo.orders.v1.OrderService/ tới cluster backend.
3. Kiểm tra request path, authority và trailers bằng client gRPC; tạo một lỗi NOT_FOUND để xác nhận grpc-status được chuyển tiếp.
4. Cấu hình TLS termination ở gateway và TLS/mTLS tới backend; xác minh hostname/SAN và trust chain.
5. Thử client deadline 800 ms với backend xử lý chậm; quan sát route timeout và status ở client.
6. Mở server-streaming RPC, điều chỉnh idle/max stream policy và kiểm tra stream không bị cắt ngoài dự kiến.
7. Dừng một backend trong lúc có traffic; xác minh health routing, connection draining và retry chỉ áp dụng cho thao tác an toàn.
8. Tạo trace/log correlation giữa client, gateway và server; xác nhận token và dữ liệu nhạy cảm được redact.

### Câu hỏi tự kiểm tra

**1. L4 proxy có thể route theo gRPC method không?**  
Không nếu chỉ chuyển tiếp TCP. Định tuyến theo path cần proxy L7 hiểu HTTP/2 sau khi giải mã TLS.

**2. Vì sao L7 gateway phải hỗ trợ HTTP/2 upstream?**  
Native gRPC dùng HTTP/2 trên mỗi chặng. Nếu upstream chỉ là HTTP/1.1 thông thường, gRPC framing/trailers không được giữ đúng.

**3. TLS passthrough có cho gateway đọc metadata và grpc-status không?**  
Không. TLS payload vẫn được mã hóa; gateway chỉ chuyển tiếp transport/SNI theo cấu hình.

**4. TLS termination có bảo vệ chặng gateway tới backend không?**  
Không tự động. Cần TLS/mTLS upstream hoặc một network trust boundary được kiểm soát.

**5. Vì sao HTTP 200 không đảm bảo gRPC thành công?**  
RPC status nằm trong grpc-status ở trailers. Client phải nhận và xử lý trailers đúng.

**6. Có thể áp timeout REST ngắn cho mọi gRPC stream không?**  
Không. Streaming cần idle/max duration policy phù hợp; deadline của client và timeout của proxy phải được phối hợp.

**7. Gateway retry một RPC ghi có an toàn không?**  
Chỉ khi semantics method cho phép hoặc có idempotency bảo vệ. Connection reset không chứng minh backend chưa thực hiện thao tác.

**8. Khi nào cần kiểm thử qua gateway thật?**  
Khi cần xác minh routing, TLS/ALPN, upstream HTTP/2, trailers, streaming, timeout, retry và draining. In-process test không kiểm tra được các hành vi mạng này.

## Tổng kết

Một gRPC call qua proxy/gateway đi qua các hop HTTP/2 riêng biệt, với routing dựa trên authority/path, transport TLS và lifecycle của stream. L4 proxy chủ yếu chuyển tiếp connection; L7 gateway có thể hiểu gRPC method, metadata, status và trailers nhưng phải hỗ trợ HTTP/2 cả phía client lẫn upstream. Trong Spring gRPC, client thường tái sử dụng ManagedChannel trỏ tới gateway, đặt deadline theo RPC và xác minh TLS identity. Gateway cần giữ semantics của gRPC, phối hợp timeout/streaming/health/retry, bảo vệ metadata và hỗ trợ connection draining. Kiểm thử end-to-end qua gateway thật là cách xác nhận các hop hoạt động đúng.

