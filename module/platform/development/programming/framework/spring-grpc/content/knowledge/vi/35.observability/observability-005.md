# Message count trong streaming

Một streaming RPC có thể trao đổi hàng trăm hoặc hàng triệu message trong suốt vòng đời của một call. Đếm số RPC chỉ cho biết có bao nhiêu stream được mở; nó không cho biết mỗi stream đang gửi bao nhiêu dữ liệu, chiều nào bị nghẽn hoặc message flow có đột ngột dừng hay không. Message count bổ sung góc nhìn về lưu lượng ở cấp message để vận hành và tối ưu dịch vụ gRPC.

**Message count trong streaming** là số message request/response được quan sát ở các ranh giới client và server trong một streaming RPC. Bài thuộc chương **Observability** của mô-đun **SPRING_GRPC**: phát triển dịch vụ gRPC trong hệ sinh thái Spring bằng hợp đồng Protocol Buffers, sinh mã Java và triển khai client/server cho unary hoặc streaming RPC; người học xử lý metadata, deadline, status, interceptor, TLS, kiểm thử tích hợp và giám sát hiệu năng, độ tin cậy. Trọng tâm là đếm message theo chiều gửi/nhận, phân biệt message count với RPC count và byte throughput, rồi dùng metrics để phát hiện luồng dữ liệu bất thường.

## 1. Message count khác RPC count

Một RPC là một lần gọi method của service. Một message là một đơn vị request hoặc response được trao đổi trong call. Quan hệ giữa hai đại lượng phụ thuộc loại RPC:

| Loại RPC | Message request | Message response | Số RPC |
| --- | ---: | ---: | ---: |
| Unary | 1 | 1 | 1 |
| Client streaming | Nhiều | 1 | 1 |
| Server streaming | 1 | Nhiều | 1 |
| Bidirectional streaming | Nhiều | Nhiều | 1 |

Ví dụ một bidirectional stream trao đổi 500 request message và 480 response message vẫn là một RPC. Nếu chỉ nhìn RPC count, hệ thống có vẻ chỉ xử lý một call; message count cho thấy khối lượng trao đổi thực tế.

Trong bài này, message count tập trung vào ba loại streaming RPC. Unary có đúng một request và một response theo contract nên có thể theo dõi bằng RPC metrics; nếu muốn thống kê message cho mọi loại method, cần ghi rõ cách tách rpc_type để không làm sai cách diễn giải.

## 2. Định nghĩa rõ ranh giới được đếm

Một message có thể được quan sát tại nhiều điểm trong vòng đời:

- Client gọi ClientCall.sendMessage: message request được trao cho client call để gửi.
- Server nhận ServerCall.Listener.onMessage: request message đã được transport giải mã và chuyển tới server call listener.
- Server gọi ServerCall.sendMessage: response message được trao cho server call để gửi.
- Client nhận ClientCall.Listener.onMessage: response message đã được transport giải mã và chuyển tới client listener.

Các điểm này tạo ra bốn metric khác nhau:

| Metric | Ranh giới quan sát | Diễn giải |
| --- | --- | --- |
| Client messages sent | Client gọi sendMessage cho request | Số request message được client call chấp nhận để gửi. |
| Server messages received | Server listener nhận onMessage | Số request message tới server listener. |
| Server messages sent | Server gọi sendMessage cho response | Số response message được server call chấp nhận để gửi. |
| Client messages received | Client listener nhận onMessage | Số response message tới client listener. |

Không giả định bốn con số luôn bằng nhau. Client có thể gửi message rồi bị hủy trước khi tất cả message tới server. Server có thể gửi message nhưng client mất kết nối trước khi nhận. Một message được đếm tại send boundary không phải bằng chứng rằng peer đã nhận hoặc ứng dụng peer đã xử lý message.

Nếu cần biết message đã được xử lý bền vững, ứng dụng phải có acknowledgement ở protocol hoặc business layer. Metrics ở transport boundary không thể thay thế acknowledgement.

## 3. Vì sao cần tách inbound và outbound?

Với bidirectional streaming, hai phía có thể gửi message độc lập. Nếu chỉ có một counter chung, khó xác định chiều nào ngừng hoạt động:

- Client gửi tăng nhưng server nhận thấp: có thể call bị ngắt, flow control hoặc transport đang gặp vấn đề.
- Server gửi tăng nhưng client nhận thấp: response có thể chưa tới peer hoặc client đang chậm đọc.
- Client nhận nhiều hơn server gửi trong một cửa sổ ngắn: số liệu có thể lệch do scrape timing, nhiều instance hoặc metric được thu ở các ranh giới khác nhau.
- Message count ổn định nhưng bytes tăng: kích thước message trung bình đang tăng.

Vì vậy, đặt metric name tách theo chiều và phía quan sát. Tránh một metric messages_total không nói rõ đó là gửi hay nhận, client hay server.

## 4. Metric cơ bản cho streaming

Một bộ metric có thể dùng:

~~~text
grpc.client.stream.messages.sent
  type: Counter
  tags: service, method, rpc_type

grpc.client.stream.messages.received
  type: Counter
  tags: service, method, rpc_type

grpc.server.stream.messages.sent
  type: Counter
  tags: service, method, rpc_type

grpc.server.stream.messages.received
  type: Counter
  tags: service, method, rpc_type
~~~

Counter phù hợp vì số message tích lũy chỉ tăng. Backend metrics tính rate để biểu diễn message/second trong một cửa sổ thời gian. Nếu cần số message của từng stream, không đưa stream ID vào label; dùng trace hoặc log có sampling để điều tra từng call.

service nên là full Protobuf service name, method là tên method, còn rpc_type là một trong ba giá trị hữu hạn client_streaming, server_streaming, bidi_streaming. Các label này ổn định theo API và hỗ trợ tổng hợp theo method.

## 5. Đếm message ở server bằng ServerInterceptor

ServerInterceptor có thể quan sát request message khi listener nhận onMessage và response message khi ServerCall gửi sendMessage. Cách này không yêu cầu sửa từng implementation của service:

~~~java
import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.Locale;

public final class StreamMessageCountServerInterceptor
        implements ServerInterceptor {

    private final MeterRegistry registry;

    public StreamMessageCountServerInterceptor(
            MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        MethodDescriptor<ReqT, RespT> descriptor =
                call.getMethodDescriptor();
        MethodDescriptor.MethodType type = descriptor.getType();

        if (type == MethodDescriptor.MethodType.UNARY) {
            return next.startCall(call, headers);
        }

        String fullMethod = descriptor.getFullMethodName();
        int separator = fullMethod.lastIndexOf('/');
        String service = separator < 0
                ? "unknown"
                : fullMethod.substring(0, separator);
        String method = separator < 0
                ? fullMethod
                : fullMethod.substring(separator + 1);
        String rpcType = type.name().toLowerCase(Locale.ROOT);

        Counter received = Counter.builder(
                        "grpc.server.stream.messages.received")
                .description("Streaming request messages nhận ở server listener")
                .tags(
                        "service", service,
                        "method", method,
                        "rpc_type", rpcType)
                .register(registry);

        Counter sent = Counter.builder(
                        "grpc.server.stream.messages.sent")
                .description("Streaming response messages gửi từ server call")
                .tags(
                        "service", service,
                        "method", method,
                        "rpc_type", rpcType)
                .register(registry);

        ServerCall<ReqT, RespT> monitoredCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
                    @Override
                    public void sendMessage(RespT message) {
                        super.sendMessage(message);
                        sent.increment();
                    }
                };

        ServerCall.Listener<ReqT> listener =
                next.startCall(monitoredCall, headers);

        return new ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onMessage(ReqT message) {
                received.increment();
                super.onMessage(message);
            }
        };
    }
}
~~~

Interceptor bỏ qua unary method để metric chỉ phản ánh streaming. Counter được lấy một lần cho mỗi call, còn increment được gọi ở mỗi message. MeterRegistry tái sử dụng meter có cùng tên và tags, vì vậy các call cùng service/method/rpc_type đóng góp vào cùng một time series.

sendMessage được đếm sau khi gọi super.sendMessage. Điều này có nghĩa call API đã nhận thao tác gửi mà không ném lỗi đồng bộ; nó không chứng minh bytes đã được ghi lên socket hoặc client đã nhận message. onMessage biểu thị message đã tới listener server. Nếu ứng dụng cần đo message đã xử lý xong, đặt metric riêng ở tầng handler sau khi xử lý hoàn tất.

## 6. Đếm message ở client bằng ClientInterceptor

ClientInterceptor quan sát request message qua ClientCall.sendMessage và response message qua ClientCall.Listener.onMessage:

~~~java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.ForwardingClientCallListener;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.Locale;

public final class StreamMessageCountClientInterceptor
        implements ClientInterceptor {

    private final MeterRegistry registry;

    public StreamMessageCountClientInterceptor(
            MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        MethodDescriptor.MethodType type = method.getType();
        if (type == MethodDescriptor.MethodType.UNARY) {
            return next.newCall(method, callOptions);
        }

        String fullMethod = method.getFullMethodName();
        int separator = fullMethod.lastIndexOf('/');
        String service = separator < 0
                ? "unknown"
                : fullMethod.substring(0, separator);
        String methodName = separator < 0
                ? fullMethod
                : fullMethod.substring(separator + 1);
        String rpcType = type.name().toLowerCase(Locale.ROOT);

        Counter sent = Counter.builder(
                        "grpc.client.stream.messages.sent")
                .tags(
                        "service", service,
                        "method", methodName,
                        "rpc_type", rpcType)
                .register(registry);

        Counter received = Counter.builder(
                        "grpc.client.stream.messages.received")
                .tags(
                        "service", service,
                        "method", methodName,
                        "rpc_type", rpcType)
                .register(registry);

        return new ForwardingClientCall
                .SimpleForwardingClientCall<>(
                        next.newCall(method, callOptions)) {
            @Override
            public void sendMessage(ReqT message) {
                super.sendMessage(message);
                sent.increment();
            }

            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {
                Listener<RespT> monitored =
                        new ForwardingClientCallListener
                                .SimpleForwardingClientCallListener<>(
                                        responseListener) {
                            @Override
                            public void onMessage(RespT message) {
                                received.increment();
                                super.onMessage(message);
                            }
                        };
                super.start(monitored, headers);
            }
        };
    }
}
~~~

Gắn interceptor vào channel qua ManagedChannelBuilder.intercept hoặc extension point tương ứng của Spring gRPC starter. Ở server, đăng ký ServerInterceptor qua server builder hoặc extension point mà starter quản lý. Không tạo channel/server riêng chỉ để cài metrics nếu starter đã sở hữu lifecycle đó.

Client sendMessage đo message request được call chấp nhận để gửi; client listener onMessage đo response message tới listener. Các metric này không phải acknowledgement nghiệp vụ và không bảo đảm peer đã commit dữ liệu.

## 7. Chọn đúng vị trí đo trong ứng dụng

Có ba lớp thường được quan sát:

| Lớp | Điểm đo | Câu hỏi |
| --- | --- | --- |
| gRPC call API | sendMessage/onMessage ở interceptor | Bao nhiêu message đi qua call boundary? |
| Business handler | Khi handler bắt đầu/kết thúc xử lý message | Bao nhiêu message được xử lý thành công? |
| Application protocol | Khi gửi/nhận acknowledgement hoặc commit | Bao nhiêu message đã được xác nhận bền vững? |

Một message có thể được nhận ở server nhưng xử lý thất bại. Vì vậy messages.received không đồng nghĩa messages.processed. Nếu cần theo dõi xử lý nghiệp vụ, thêm messages.processed và messages.processing.errors tại tầng service, với semantics riêng.

Tương tự, messages.sent không chứng minh client đã nhận. Nếu cần đo delivery/acknowledgement, thiết kế acknowledgement trong Protobuf contract hoặc protocol của ứng dụng. Không cố suy ra delivery từ counter ở phía gửi.

## 8. Message count, byte count và throughput

Message count đo số đơn vị message, còn byte count đo lượng dữ liệu. Hai đại lượng có thể biến động độc lập:

- 1.000 message nhỏ có thể tiêu thụ ít băng thông hơn 10 message chứa payload lớn.
- Compression làm số byte trên wire khác kích thước message trước nén.
- Protobuf serialization có overhead khác nhau theo schema và giá trị field.
- TLS/HTTP2 framing tạo thêm bytes ngoài payload Protobuf.

Nếu cần quan sát byte throughput, tạo metric riêng như bytes sent/received ở ranh giới có semantics rõ ràng. Đừng đặt tên message count thành throughput nếu chưa đo bytes/second. Nếu chỉ đo kích thước serialized message, ghi rõ đó là payload size trước hay sau compression; không gọi nó là wire bytes.

## 9. Đọc message rate và số message trung bình trên mỗi RPC

Counter có thể chuyển thành message rate theo thời gian. Nếu exporter là Prometheus và metric được chuẩn hóa thành grpc_server_stream_messages_received_total, có thể truy vấn:

~~~promql
# Request messages mỗi giây server nhận, theo service/method.
sum by (service, method, rpc_type) (
  rate(grpc_server_stream_messages_received_total[5m])
)
~~~

Response message rate server gửi:

~~~promql
sum by (service, method, rpc_type) (
  rate(grpc_server_stream_messages_sent_total[5m])
)
~~~

Tổng message nhận trong một giờ:

~~~promql
sum by (service, method, rpc_type) (
  increase(grpc_server_stream_messages_received_total[1h])
)
~~~

Nếu có RPC completed counter cùng labels, có thể ước lượng số message trung bình trên mỗi call trong một cửa sổ:

~~~promql
sum by (service, method, rpc_type) (
  rate(grpc_server_stream_messages_received_total[5m])
)
/
sum by (service, method, rpc_type) (
  rate(grpc_server_calls_total[5m])
)
~~~

Query giả định RPC completed counter được export thành grpc_server_calls_total và có label rpc_type giống message counter. Nếu counter hiện tại chỉ có service/method/status, hãy bổ sung rpc_type hoặc dùng một metric RPC counter tương thích cho streaming trước khi tính tỷ lệ. Phải dùng đúng tên sau khi exporter chuẩn hóa và bảo đảm mẫu số đếm cùng loại streaming RPC, cùng direction và cùng ranh giới. Nếu mẫu số gồm cả unary hoặc client/server metrics trộn lẫn, tỷ lệ sẽ sai. Khi không có call counter phù hợp, không suy ra số message trung bình trên mỗi stream từ một mẫu số không tương thích.

## 10. Quan sát message flow cùng backpressure

Message rate thấp không tự động có nghĩa service lỗi. Client có thể không có dữ liệu để gửi, server có thể chờ event hoặc flow control có thể đang điều tiết tốc độ. Kết hợp message count với các tín hiệu:

- Active stream count và stream duration.
- Thời gian giữa các message (inter-message gap).
- Client/server readiness và callback onReady.
- Số lần producer bị pause/resume do flow control.
- Queue depth và thời gian chờ xử lý message.
- Deadline, cancellation và terminal status.

onReady không phải message event. Nó cho biết call có thể tiếp tục gửi mà không vượt quá ngưỡng buffering/flow control của gRPC. Không tăng message counter khi callback onReady được gọi.

Với bidirectional streaming, theo dõi hai chiều riêng. Nếu server nhận message nhanh hơn xử lý, queue có thể tăng dù inbound message rate bình thường. Nếu client gửi quá nhanh, cần dùng flow control/backpressure để điều tiết; counter chỉ giúp nhận diện tốc độ, không tự giới hạn tải.

## 11. Cardinality và hiệu năng instrumentation

Message counter tăng rất thường xuyên, nên instrumentation cần nhẹ:

- Lấy Counter một lần khi bắt đầu call, không tra MeterRegistry lại cho từng message.
- Chỉ dùng tags có tập giá trị hữu hạn: service, method, rpc_type và có thể direction nếu dùng chung metric.
- Không đưa stream ID, request ID, user ID, tenant ID, trace ID hoặc message sequence number vào labels.
- Tránh log từng message ở mức INFO; dùng sampled tracing hoặc debug log có kiểm soát khi cần điều tra.
- Nếu cần đo theo instance/zone, đánh giá cardinality budget trước khi thêm dimension.

Không tạo một meter riêng cho mỗi stream. Mỗi tổ hợp label phải được tái sử dụng qua nhiều call để giữ số time series ổn định.

## 12. Kiểm thử message count

Dùng SimpleMeterRegistry và in-process gRPC server/channel để kiểm tra semantics của interceptor:

1. Client-streaming gửi N request message; xác minh client sent và server received tăng N.
2. Server-streaming gửi M response message; xác minh server sent và client received tăng M.
3. Bidirectional streaming trao đổi N request và M response; xác minh bốn counter đúng theo từng chiều.
4. Mở một stream và gửi nhiều message; xác minh RPC count vẫn là một trong khi message count tăng theo N/M.
5. Hủy stream giữa chừng; xác minh các message đã đi qua boundary vẫn được giữ trong counter, message chưa gửi không bị tính.
6. Làm server trả lỗi sau khi nhận một số request message; xác minh received count phản ánh message đã tới listener, không phải message dự kiến gửi.
7. Gọi unary method; xác minh interceptor streaming bỏ qua method đó.
8. Kiểm tra metric labels không chứa stream ID, request ID hoặc dữ liệu payload.

Với test message gửi, chờ terminal callback hoặc acknowledgement của test protocol trước khi đọc registry. Không dùng Thread.sleep để đoán message đã tới. Với kiểm thử TCP/TLS, bổ sung test peer disconnect và flow control vì in-process transport không mô phỏng đầy đủ network buffering hoặc proxy.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Message count bằng RPC count | Chỉ đếm call start/complete. | Đếm riêng sendMessage và onMessage. |
| Server sent bằng client received trong mọi thời điểm | Hiểu nhầm hai ranh giới là cùng một sự kiện. | Tách API send boundary và peer receive boundary. |
| Một stream nhiều message bị đếm thành nhiều RPC | Đếm mỗi onMessage như một call. | Giữ RPC counter và message counter riêng. |
| Client-streaming không có inbound message metric | Chỉ instrument response hoặc chỉ instrument server send. | Theo dõi request ở server onMessage và client sendMessage. |
| Server-streaming không có response receive metric | Chỉ instrument client sendMessage. | Đếm response ở client listener onMessage. |
| Message rate tăng nhưng bytes không tăng tương ứng | Kích thước message trung bình giảm. | Quan sát message count và byte count riêng. |
| Message received bị hiểu là business processed | Metric nằm ở transport boundary. | Thêm processed counter ở business handler. |
| Metrics backend tăng cardinality theo stream | Dùng stream ID hoặc sequence number làm tag. | Giữ labels hữu hạn; dùng trace/log cho từng stream. |
| Counter không tăng trong test | Interceptor chưa được đăng ký vào channel/server thực tế. | Xác minh starter wiring và gọi RPC qua đúng channel/server. |

## 14. Bài tập thực hành

1. Viết ServerInterceptor đếm request message nhận và response message gửi cho ba loại streaming RPC.
2. Viết ClientInterceptor đếm request message gửi và response message nhận; bỏ qua unary method.
3. Tạo client-streaming test gửi 100 message; xác minh client sent và server received theo đúng boundary.
4. Tạo server-streaming test trả 50 message; xác minh server sent và client received.
5. Tạo bidirectional stream với hai chiều có số message khác nhau; kiểm tra bốn counter độc lập.
6. Viết PromQL tính message/second và tổng message trong một giờ theo service/method.
7. Kết hợp message rate với active stream, inter-message gap và queue depth để nhận diện backpressure.
8. Kiểm tra cardinality và xác minh không có stream ID, request ID hoặc message payload trong labels.

Sau bài này, bạn cần phân biệt message count với RPC count, byte throughput và business processing count; đo inbound/outbound tại ranh giới phù hợp ở cả client lẫn server; và diễn giải chênh lệch giữa message được gửi với message tới peer. Khi kết hợp message rate với active stream, backpressure và queue metrics, đội vận hành có thể nhận biết luồng dữ liệu bất thường trong hệ thống Spring gRPC.
