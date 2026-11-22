# Giới hạn số connection

gRPC chạy trên HTTP/2, vì vậy một kết nối TCP có thể mang nhiều RPC đồng thời dưới dạng các HTTP/2 stream. Điều này làm cho giới hạn connection và giới hạn số RPC đang chạy trở thành hai bài toán khác nhau. Một server có thể có ít connection nhưng vẫn phải xử lý hàng nghìn stream; ngược lại, nhiều client tạo nhiều connection nhàn rỗi vẫn có thể tiêu tốn file descriptor, bộ nhớ, TLS state và tài nguyên transport.

**Giới hạn số connection** là kiểm soát số kết nối mạng đồng thời được chấp nhận hoặc duy trì ở một ranh giới cụ thể, đồng thời đặt giới hạn phù hợp cho số RPC/stream chạy trên mỗi kết nối. Bài thuộc chương **Resource limits** của mô-đun **SPRING_GRPC**: phát triển dịch vụ gRPC trong hệ sinh thái Spring bằng hợp đồng Protocol Buffers, sinh mã Java và triển khai client/server cho unary hoặc streaming RPC; người học xử lý metadata, deadline, status, interceptor, TLS, kiểm thử tích hợp và giám sát hiệu năng, độ tin cậy. Trọng tâm là phân biệt TCP connection với HTTP/2 stream, chọn đúng lớp thực thi giới hạn, tái sử dụng client channel và đo capacity để tránh cạn file descriptor hoặc quá tải server.

## 1. Connection và RPC stream không phải một đơn vị

Một gRPC channel là abstraction phía client để gọi service. Channel quản lý kết nối và có thể dùng load balancing để tạo nhiều subchannel/transport. Trên mỗi HTTP/2 connection, client và server có thể multiplex nhiều RPC stream.

| Khái niệm | Ý nghĩa | Giới hạn kiểm soát điều gì? |
| --- | --- | --- |
| TCP connection | Kết nối mạng giữa client/proxy và server. | Số socket, file descriptor, TLS state, buffer và transport. |
| HTTP/2 stream | Một luồng logic trong connection, thường tương ứng một RPC. | Số RPC đồng thời trên một connection. |
| Logical RPC | Một lần ứng dụng gọi method gRPC. | Tải nghiệp vụ và concurrency của method. |
| ManagedChannel | Client abstraction quản lý việc gọi và transport. | Vòng đời, resolver, load balancing và kết nối phía client. |

Một TCP connection có thể phục vụ nhiều RPC cùng lúc. Do đó, giới hạn số connection không tự động giới hạn tổng số RPC; giới hạn số stream trên mỗi connection cũng không tự động giới hạn tổng số connection.

Ví dụ: 100 client connection, mỗi connection được phép chạy 50 stream đồng thời, có thể tạo tối đa 5.000 RPC đang hoạt động ở ranh giới đó. Muốn giới hạn tổng tải, cần thêm global concurrency limit hoặc capacity control ở tầng ứng dụng.

## 2. Xác định ranh giới cần giới hạn

Trước khi chọn cấu hình, xác định connection nào đang được đếm:

- Client đến load balancer: số TCP connection mà edge nhận từ client.
- Load balancer đến gRPC server: số upstream connection do proxy mở tới backend.
- Connection trực tiếp đến server: số transport mà gRPC server đang duy trì.
- Outbound từ service A đến service B: số connection do client channel/subchannel của A tạo ra.

Các con số này không nhất thiết bằng nhau. Một proxy có thể nhận hàng nghìn downstream connections nhưng chỉ mở một pool upstream connection tới mỗi backend. Nếu dashboard chỉ hiển thị connection ở server, nó không phản ánh toàn bộ socket phía client hoặc edge.

Nên đặt tên metric theo ranh giới, ví dụ downstream_active_connections, upstream_active_connections hoặc grpc_server_active_transports. Tránh một metric chung tên connections nếu không rõ nó đếm socket ở đâu.

## 3. Chọn nơi thực thi hard connection cap

Giới hạn cứng số TCP connection thường phù hợp nhất ở lớp nhận kết nối:

| Lớp | Cách kiểm soát | Phù hợp khi |
| --- | --- | --- |
| L4 load balancer / network proxy | Đặt giới hạn concurrent connections theo listener, cluster hoặc nguồn kết nối. | Cần chặn socket trước khi chúng tiêu thụ tài nguyên sâu trong ứng dụng. |
| API gateway / L7 proxy | Giới hạn downstream connections và upstream connection pool; có thể trả lỗi HTTP/gRPC phù hợp. | Cần policy theo route, identity hoặc tenant đã xác thực. |
| Network policy / firewall | Giới hạn nguồn, subnet hoặc số kết nối theo hạ tầng hỗ trợ. | Cần bảo vệ biên mạng và giới hạn nguồn không mong muốn. |
| gRPC server | Theo dõi transport, giới hạn RPC concurrency trên mỗi connection và giới hạn công việc trong ứng dụng. | Cần kiểm soát tài nguyên bên trong tiến trình. |
| Client application | Tái sử dụng channel và quản lý số channel/subchannel. | Cần tránh tạo quá nhiều outbound connection. |

Nếu yêu cầu là “không cho server có quá N TCP connections đồng thời”, cần một cơ chế admission control thực sự tại listener/proxy hoặc transport implementation hỗ trợ việc từ chối connection. Một ServerInterceptor chạy ở cấp RPC đã quá muộn để làm hard TCP connection cap vì nó chỉ được gọi khi một RPC stream bắt đầu.

Không nhầm TCP listen backlog với số connection đang mở. Backlog giới hạn số kết nối đang chờ được accept/hoàn tất bắt tay theo hành vi hệ điều hành; nó không phải giới hạn tổng socket đã established.

## 4. HTTP/2 multiplexing và giới hạn concurrent calls

gRPC Java có cấu hình giới hạn số call đồng thời trên một connection qua ServerBuilder/NettyServerBuilder ở các phiên bản hỗ trợ:

~~~java
NettyServerBuilder serverBuilder =
        NettyServerBuilder.forPort(9090)
                .maxConcurrentCallsPerConnection(64);
~~~

Giá trị 64 là ví dụ, không phải ngưỡng mặc định phù hợp cho mọi service. Cấu hình này giới hạn số RPC đồng thời trên từng connection. Khi đạt ngưỡng, HTTP/2/gRPC transport sẽ điều tiết hoặc không nhận thêm stream mới theo cơ chế của implementation.

Đây không phải hard cap số TCP connection. Client có thể mở thêm connection khác và tạo thêm stream ở connection mới. Vì vậy:

- Dùng maxConcurrentCallsPerConnection để giới hạn stream concurrency trên từng transport.
- Dùng global application concurrency limit để giới hạn tổng RPC đang xử lý.
- Dùng edge connection cap để giới hạn số socket được chấp nhận.

Các lớp này bổ sung cho nhau, không thay thế nhau.

## 5. Theo dõi số transport đang hoạt động ở server

gRPC Java cung cấp ServerTransportFilter để quan sát lifecycle của transport. Với Netty HTTP/2 server, mỗi transport thường tương ứng một connection; filter có thể tăng bộ đếm khi transport sẵn sàng và giảm khi transport kết thúc.

~~~java
import io.grpc.Attributes;
import io.grpc.ServerTransportFilter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.concurrent.atomic.AtomicLong;

public final class ActiveTransportFilter
        extends ServerTransportFilter {

    private final AtomicLong activeTransports = new AtomicLong();

    public ActiveTransportFilter(MeterRegistry registry) {
        Gauge.builder(
                        "grpc.server.active.transports",
                        activeTransports,
                        AtomicLong::get)
                .description("Số gRPC server transports đang hoạt động")
                .register(registry);
    }

    @Override
    public Attributes transportReady(Attributes transportAttrs) {
        activeTransports.incrementAndGet();
        return transportAttrs;
    }

    @Override
    public void transportTerminated(Attributes transportAttrs) {
        activeTransports.updateAndGet(value -> Math.max(0, value - 1));
    }
}
~~~

Đăng ký filter vào server builder:

~~~java
NettyServerBuilder serverBuilder = NettyServerBuilder.forPort(9090)
        .addTransportFilter(new ActiveTransportFilter(meterRegistry));
~~~

Trong ứng dụng Spring, gắn filter vào server builder do Spring gRPC starter quản lý qua extension point của phiên bản đang dùng. Không khởi tạo một server độc lập chỉ để gắn filter.

ServerTransportFilter là điểm quan sát lifecycle, không phải API từ chối transport. Đoạn code trên chỉ tạo gauge; nó không giới hạn số connection. Nếu cần hard cap, thực thi ở proxy/listener có admission control hoặc dùng transport implementation có hỗ trợ rõ ràng.

## 6. Giới hạn RPC concurrency toàn server

Giới hạn per-connection không đủ nếu nhiều connection cùng mở stream. Có thể áp dụng admission control ở tầng RPC để giới hạn tổng số handler đang chạy. Một cách là dùng semaphore trong ServerInterceptor; khi hết permit, trả RESOURCE_EXHAUSTED và không gọi service handler:

~~~java
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicBoolean;

public final class RpcAdmissionInterceptor
        implements ServerInterceptor {

    private final Semaphore permits = new Semaphore(500);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        if (!permits.tryAcquire()) {
            call.close(
                    Status.RESOURCE_EXHAUSTED
                            .withDescription("Server RPC capacity reached"),
                    new Metadata());
            return new ServerCall.Listener<>() {};
        }

        AtomicBoolean released = new AtomicBoolean();
        Runnable release = () -> {
            if (released.compareAndSet(false, true)) {
                permits.release();
            }
        };

        ServerCall<ReqT, RespT> monitored =
                new io.grpc.ForwardingServerCall
                        .SimpleForwardingServerCall<>(call) {
                    @Override
                    public void close(Status status, Metadata trailers) {
                        try {
                            super.close(status, trailers);
                        } finally {
                            release.run();
                        }
                    }
                };

        ServerCall.Listener<ReqT> listener;
        try {
            listener = next.startCall(monitored, headers);
        } catch (RuntimeException failure) {
            release.run();
            throw failure;
        }

        return new io.grpc.ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onComplete() {
                try {
                    super.onComplete();
                } finally {
                    release.run();
                }
            }

            @Override
            public void onCancel() {
                try {
                    super.onCancel();
                } finally {
                    release.run();
                }
            }
        };
    }
}
~~~

Ví dụ này giới hạn số RPC đã được nhận vào handler, không giới hạn TCP connections. Cần kiểm tra mọi terminal path và exception khi gọi next.startCall để permit không bị rò; trong production, nên bọc cả lỗi đồng bộ lúc khởi tạo listener và dùng một lifecycle guard thống nhất. Với streaming RPC, permit được giữ trong toàn bộ thời gian stream, vì stream vẫn chiếm tài nguyên cho tới khi close/cancel.

Giới hạn global cũng nên được phân loại theo method hoặc nhóm workload nếu một method streaming dài có thể chiếm hết permit của unary RPC quan trọng. Có thể dùng semaphore riêng theo service/method, weighted admission hoặc queue có giới hạn.

## 7. Quản lý connection phía client bằng ManagedChannel

Một lỗi phổ biến là tạo ManagedChannel mới cho từng request. Mỗi channel có lifecycle, resolver, load balancing state và transport riêng; tạo quá nhiều channel có thể làm tăng TCP connection, TLS handshake, thread và file descriptor.

Nên tái sử dụng channel theo target và cấu hình kết nối:

~~~java
ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///inventory.internal:8443")
        .useTransportSecurity()
        .build();

InventoryGrpc.InventoryBlockingStub stub =
        InventoryGrpc.newBlockingStub(channel);

// Dùng lại channel/stub cho nhiều RPC trong vòng đời bean/service.

// Khi ứng dụng shutdown:
channel.shutdown();
if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
    channel.shutdownNow();
}
~~~

Trong Spring Boot, quản lý channel bằng bean có lifecycle rõ ràng và đóng channel khi application context dừng. Không tạo channel trong từng controller method hoặc từng message callback.

Một ManagedChannel không phải lúc nào cũng tương đương đúng một TCP connection: load balancing có thể tạo nhiều subchannel tới nhiều backend, và resolver/policy quyết định transport. gRPC Java không có một thuộc tính maxConnections chung áp dụng cho mọi ManagedChannelBuilder. Nếu cần giới hạn outbound socket nghiêm ngặt, quản lý số channel/target có chủ đích và cân nhắc egress proxy với connection pool cap.

## 8. Connection lifecycle: idle, age và keepalive

Connection lifecycle policy giúp thu hồi hoặc làm mới kết nối lâu không dùng, nhưng không phải hard concurrent connection cap:

- maxConnectionIdle: cho phép server đóng connection không có RPC hoạt động trong một khoảng thời gian.
- maxConnectionAge: giới hạn tuổi connection để dần xoay vòng transport.
- maxConnectionAgeGrace: khoảng thời gian cho RPC đang chạy hoàn tất trước khi connection bị đóng.
- Keepalive: kiểm tra transport còn sống; ping quá thường xuyên có thể tạo tải không cần thiết.
- Client idle/shutdown policy: giúp giải phóng channel không còn được dùng.

Các tùy chọn server có thể được cung cấp bởi ServerBuilder/NettyServerBuilder tùy phiên bản grpc-java. Ví dụ cấu hình phải được xác minh với version đang dùng:

~~~java
NettyServerBuilder.forPort(9090)
        .maxConnectionIdle(5, TimeUnit.MINUTES)
        .maxConnectionAge(30, TimeUnit.MINUTES)
        .maxConnectionAgeGrace(2, TimeUnit.MINUTES)
        .permitKeepAliveTime(1, TimeUnit.MINUTES)
        .permitKeepAliveWithoutCalls(false);
~~~

Idle/age policy có thể làm client reconnect và tạo connection mới. Khi rollout hoặc đặt age quá thấp, connection churn tăng, TLS handshake và load balancer activity cũng tăng. Theo dõi connection creation rate và reconnect rate cùng active connection count.

## 9. Đặt connection cap ở edge proxy

Nếu cần hard limit, cấu hình tại L4/L7 proxy hoặc load balancer đang accept connection. Chính sách cần xác định:

| Thuộc tính | Câu hỏi cần trả lời |
| --- | --- |
| Scope | Giới hạn theo listener, backend cluster, source IP hay identity? |
| Concurrent cap | Số connection established tối đa là bao nhiêu? |
| Pending cap | Có giới hạn số connection đang chờ accept/handshake không? |
| Overflow behavior | Từ chối/reset connection mới, queue có giới hạn hay trả lỗi ở L7? |
| Fairness | Một client có thể chiếm toàn bộ slot của các client khác không? |
| Recovery | Slot được giải phóng khi close, timeout hay health failure như thế nào? |

Với Envoy hoặc proxy tương đương, dùng connection limit/network filter hoặc upstream connection pool limits theo đúng phiên bản và loại listener. L4 proxy thường đóng/từ chối TCP connection; L7 gateway có thể trả status phù hợp nếu request đã được parse. Không giả định mọi connection limit filter đều có cùng semantics.

Nếu giới hạn theo source IP, lưu ý nhiều user có thể đi chung NAT IP. Nếu giới hạn theo authenticated identity, proxy phải xác thực identity trước khi áp dụng quota. Không dùng x-request-id hoặc metadata do caller tự khai báo làm danh tính tin cậy.

## 10. Backlog và file descriptor không thay thế admission control

Các giới hạn hệ điều hành vẫn quan trọng:

- Listen backlog điều tiết connection đang chờ accept; không giới hạn tổng established connections.
- File descriptor limit đặt trần tài nguyên socket/process có thể mở; chạm trần thường làm accept/connect thất bại.
- Ephemeral port và conntrack table có thể giới hạn outbound/network state.
- Memory/socket buffer và TLS session state tăng theo số connection.

Đừng dựa vào file descriptor exhaustion để bảo vệ server. Đây là hàng rào cuối cùng, không phải cơ chế từ chối có kiểm soát. Hãy đặt cap tại edge, giới hạn RPC concurrency trong ứng dụng và cấu hình OS đủ cao cho tải dự kiến cộng headroom.

## 11. Ước lượng capacity

Connection count phải dựa trên đo đạc của workload thực tế. Một mô hình đơn giản:

\[
\text{Total connection budget} =
\text{steady-state connections}
+ \text{rollout/reconnect headroom}
+ \text{failure headroom}
\]

Capacity planning cần tính:

- Số client instance và số target/backend mỗi client gọi.
- Số subchannel/connection mà load balancing policy có thể tạo.
- Số connection từ proxy tới mỗi backend.
- Số stream đồng thời trên mỗi connection.
- Memory, file descriptor, TLS handshake rate và socket buffer.
- Connection churn khi deploy, autoscale, DNS change hoặc failover.
- Headroom cho retry storm và reconnect đồng loạt.

Đừng chỉ nhân số client với một connection giả định. Đo active transports ở server và connection pool ở proxy trong load test. Connection ít nhưng stream concurrency lớn vẫn có thể làm CPU/worker pool quá tải; connection nhiều nhưng idle vẫn tiêu tốn tài nguyên.

## 12. Metrics và cảnh báo

Nên theo dõi connection và stream bằng các metric riêng:

| Metric | Ý nghĩa |
| --- | --- |
| grpc.server.active.transports | Transport/connection đang hoạt động tại server. |
| edge.downstream.active_connections | Connection client tới proxy. |
| edge.upstream.active_connections | Connection proxy tới backend. |
| connection.accepted/rejected rate | Tốc độ nhận và từ chối connection. |
| connection creation rate | Mức churn/reconnect. |
| grpc.server.active.calls | RPC/stream đang hoạt động. |
| grpc.server.calls.rejected | RPC bị từ chối do admission limit. |
| TLS handshake duration/errors | Chi phí và lỗi thiết lập TLS. |

Dashboard nên so sánh active connections với configured cap, đồng thời hiển thị active streams, rejected connections và connection creation rate. Alert khi connection usage duy trì gần cap, reject rate tăng hoặc connection churn bất thường; tránh cảnh báo chỉ vì một đỉnh ngắn trong lúc rollout có kế hoạch.

Metric labels nên giới hạn ở listener, cluster, service, method hoặc zone có tập giá trị được kiểm soát. Không gắn request ID, socket local port, ephemeral remote port hoặc connection ID làm label vì chúng tạo cardinality cao.

## 13. Kiểm thử connection limit

In-process gRPC transport hữu ích để kiểm thử interceptor/RPC logic nhưng không mô phỏng TCP socket thật. Kiểm thử hard connection cap cần chạy server qua TCP và, nếu policy nằm ở edge, gửi traffic qua đúng proxy/load balancer:

1. Mở số connection thấp hơn cap; xác minh tất cả được chấp nhận.
2. Mở thêm connection vượt cap; xác minh overflow behavior đúng policy (reject/reset/queue có giới hạn).
3. Đóng một connection; xác minh slot được giải phóng và connection mới được chấp nhận.
4. Giữ một connection nhưng mở nhiều RPC; xác minh maxConcurrentCallsPerConnection hoạt động theo cấu hình.
5. Mở nhiều connection cùng lúc; xác minh global RPC concurrency limit vẫn có hiệu lực.
6. Tạo nhiều ManagedChannel ở client test; quan sát số transport thực tế và xác minh channel reuse làm giảm connection churn.
7. Kiểm tra connection age/idle policy; xác minh stream đang chạy được drain theo grace period.
8. Mô phỏng rolling restart/reconnect; xác minh headroom và connection cap không làm toàn bộ client mất khả năng kết nối.
9. Đo active transport gauge và edge connection metrics; xác minh tăng/giảm đúng theo socket lifecycle.

Dùng latch/barrier để đồng bộ test và timeout hữu hạn. Không dựa vào sleep để đoán lúc connection đã được accept; quan sát metric, health endpoint hoặc trạng thái client channel. Với proxy, kiểm tra cả log/metric của proxy vì server có thể không nhìn thấy connection bị từ chối ở edge.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Nghĩ maxConcurrentCallsPerConnection là max TCP connections | Nhầm HTTP/2 stream với socket. | Dùng edge connection cap cho hard TCP limit. |
| Server có ít connection nhưng quá tải | Mỗi connection multiplex quá nhiều RPC. | Giới hạn stream/call concurrency và capacity handler. |
| Connection count tăng theo request rate | Tạo ManagedChannel cho mỗi RPC. | Tái sử dụng channel theo target/lifecycle. |
| ServerTransportFilter không chặn connection vượt ngưỡng | Filter chỉ quan sát transport lifecycle. | Thực thi admission ở proxy/listener hỗ trợ reject. |
| Backlog được xem là cap connection | Backlog chỉ điều tiết hàng chờ accept. | Dùng concurrent connection limit riêng. |
| File descriptor chạm trần | Dùng OS limit làm admission policy. | Đặt cap chủ động và tăng headroom OS phù hợp. |
| Deploy gây reconnect storm | Connection age quá ngắn hoặc rollout đồng loạt. | Điều chỉnh drain/grace, jitter reconnect và headroom. |
| IP quota chặn nhiều user hợp lệ | Nhiều caller chung NAT. | Áp dụng quota theo authenticated identity ở L7 khi phù hợp. |
| Dashboard connection count không khớp | Đếm ở các ranh giới khác nhau. | Đặt tên downstream/upstream/server transport rõ ràng. |

## 15. Bài tập thực hành

1. Vẽ đường đi của connection từ client qua load balancer/proxy tới gRPC server và xác định từng điểm đếm.
2. Cấu hình maxConcurrentCallsPerConnection và kiểm thử số stream trên một connection.
3. Viết ServerTransportFilter dùng Micrometer Gauge để theo dõi active transports.
4. Tái sử dụng ManagedChannel trong Spring bean và đóng channel đúng lifecycle.
5. Đặt hard connection cap ở proxy/L4 listener; kiểm thử hành vi khi vượt ngưỡng.
6. Kết hợp per-connection stream cap với global RPC admission limit.
7. Đo connection churn, TLS handshake, active streams và file descriptor trong load test.
8. Tạo dashboard phân biệt downstream connections, upstream connections, server transports và active RPCs.

Sau bài này, bạn cần phân biệt TCP connection với HTTP/2 stream, biết giới hạn per-connection RPC khác hard connection cap, và chọn đúng lớp thực thi policy. Kết hợp edge admission control, gRPC stream concurrency, channel reuse và metrics theo từng ranh giới giúp hệ thống Spring gRPC bảo vệ socket/file descriptor mà vẫn duy trì khả năng phục vụ ổn định.
