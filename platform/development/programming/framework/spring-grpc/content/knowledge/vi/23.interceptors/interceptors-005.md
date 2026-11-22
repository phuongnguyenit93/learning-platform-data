# Đo metric theo RPC method

Khi theo dõi một Spring gRPC service, tổng số request hoặc CPU toàn ứng dụng chưa đủ để biết method nào đang chậm, lỗi tăng ở đâu hay kiểu RPC nào chiếm nhiều thời gian. Cần đo theo **RPC method**, ghi nhận status và duration tại cùng một điểm trong vòng đời call. Server interceptor là vị trí phù hợp vì nó nhìn thấy full method name và thời điểm call kết thúc, kể cả khi service trả lỗi.

Bài này tập trung vào metric theo method bằng Micrometer: chọn nhãn có cardinality hữu hạn, đo thời gian bằng đồng hồ đơn điệu, ghi nhận đúng một lần khi call kết thúc và phân biệt unary với streaming. Metric phía client có ý nghĩa khác server metric; không gộp hai loại số đo thành một đại lượng.

## 1. Chọn metric và định danh RPC

Mỗi RPC có full method name theo dạng:

```text
shop.catalog.v1.CatalogService/GetProduct
```

Lấy tên này từ descriptor:

```java
String method = call.getMethodDescriptor().getFullMethodName();
```

Full method name gồm protobuf package, service và method. Nó phân biệt được các method trùng tên ở service hoặc API version khác nhau. Không lấy tên từ class implementation hay tự ghép package Java vì các tên đó không phải định danh RPC trên wire.

Một metric hữu ích cho server thường cần các chiều sau:

| Nhãn | Giá trị ví dụ | Vì sao hữu ích |
| --- | --- | --- |
| method | shop.catalog.v1.CatalogService/GetProduct | So sánh tải và latency giữa các RPC |
| rpc_type | unary, server_streaming, client_streaming, bidi_streaming | Phân biệt thời gian call theo kiểu trao đổi |
| status | OK, NOT_FOUND, UNAVAILABLE | Theo dõi lỗi và tỷ lệ thành công |

Các nhãn này có tập giá trị hữu hạn do schema/service định nghĩa. Không thêm request_id, user_id, product_id, token, địa chỉ IP tùy ý hoặc exception message làm tag. Mỗi giá trị mới có thể tạo một time series mới; với hàng triệu request, cardinality sẽ làm tăng bộ nhớ và chi phí của hệ thống metrics.

## 2. Đo số liệu nào ở server?

Server interceptor có thể đo khoảng thời gian từ lúc server nhận call đến lúc call kết thúc ở phía server:

- **Call count:** số RPC đã kết thúc. Micrometer Timer đã có bộ đếm count, nên thường không cần tạo một Counter trùng mục đích.
- **Call duration:** thời gian từ lúc interceptor bắt đầu đến lúc server kết thúc call.
- **Status distribution:** số call theo gRPC status như OK, INVALID_ARGUMENT, UNAUTHENTICATED hoặc INTERNAL.
- **RPC type:** unary và các loại streaming cần được phân nhóm vì ý nghĩa duration khác nhau.

Đo duration bằng System.nanoTime():

```java
long startedAt = System.nanoTime();
// Khi call kết thúc:
long elapsedNanos = System.nanoTime() - startedAt;
```

nanoTime() là đồng hồ đơn điệu phù hợp để tính khoảng thời gian. currentTimeMillis() là thời gian lịch, có thể bị điều chỉnh, nên không phù hợp để tính latency.

Server call duration không hoàn toàn là thời gian chạy business method. Nó có thể bao gồm khởi tạo handler, xử lý, thời gian chờ message của client và toàn bộ thời gian stream còn mở. Vì vậy, tên metric và dashboard phải phản ánh đúng phạm vi đo.

## 3. Ghi Timer theo full method name

Micrometer Timer ghi nhận số lần, tổng duration và các thống kê phân phối khi histogram/percentile được cấu hình. Hàm ghi metric có thể nhận method, loại RPC, status và elapsed nanoseconds:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;

final class RpcMethodMetrics {
    private final MeterRegistry registry;

    RpcMethodMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    void record(
            String method,
            String rpcType,
            String status,
            long elapsedNanos) {

        Timer.builder("grpc.server.call")
                .description("Duration of a server-side gRPC call")
                .tag("method", method)
                .tag("rpc_type", rpcType)
                .tag("status", status)
                .register(registry)
                .record(elapsedNanos, TimeUnit.NANOSECONDS);
    }
}
```

Registry trả lại meter đã đăng ký cho cùng tên và cùng tập tag, nên các call tiếp theo tiếp tục cập nhật cùng Timer. Timer.count() là số call được ghi; Timer.totalTime(...) là tổng thời gian. Muốn xem p50/p95/p99, cần bật histogram hoặc percentile phù hợp với backend metrics; không mặc định rằng mọi registry đều xuất percentile.

Có thể bật histogram bằng cấu hình Micrometer hoặc publishPercentileHistogram() cho Timer nếu backend và ngân sách series cho phép. Histogram giúp tính percentile ở hệ thống tổng hợp như Prometheus; cân nhắc số bucket và số tổ hợp tag trước khi bật rộng.

## 4. Server interceptor ghi metric đúng một lần

Một RPC có thể kết thúc qua ServerCall.close, bị client hủy qua onCancel, hoặc lỗi ngay khi bắt đầu handler. Dùng AtomicBoolean để bảo đảm một call chỉ được ghi một lần dù nhiều callback kết thúc xuất hiện:

```java
package com.myshop.grpc.metrics;

import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.Locale;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class RpcMethodMetricsInterceptor implements ServerInterceptor {
    private static final Logger log =
            LoggerFactory.getLogger(RpcMethodMetricsInterceptor.class);

    private final MeterRegistry registry;

    public RpcMethodMetricsInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String method = call.getMethodDescriptor().getFullMethodName();
        String rpcType = call.getMethodDescriptor()
                .getType().name().toLowerCase(Locale.ROOT);
        long startedAt = System.nanoTime();
        AtomicBoolean recorded = new AtomicBoolean();

        Consumer<Status> finish = status -> {
            if (!recorded.compareAndSet(false, true)) {
                return;
            }
            long elapsedNanos = Math.max(0L, System.nanoTime() - startedAt);
            try {
                Timer.builder("grpc.server.call")
                        .description("Duration of a server-side gRPC call")
                        .tag("method", method)
                        .tag("rpc_type", rpcType)
                        .tag("status", status.getCode().name())
                        .register(registry)
                        .record(elapsedNanos, TimeUnit.NANOSECONDS);
            } catch (RuntimeException metricsFailure) {
                // Metrics không được làm thay đổi kết quả RPC.
                log.warn("Unable to record gRPC metric for method={}",
                        method, metricsFailure);
            }
        };

        ServerCall<ReqT, RespT> monitoredCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
                    @Override
                    public void close(Status status, Metadata trailers) {
                        finish.accept(status);
                        super.close(status, trailers);
                    }
                };

        final ServerCall.Listener<ReqT> listener;
        try {
            listener = next.startCall(monitoredCall, headers);
        } catch (RuntimeException ex) {
            finish.accept(Status.fromThrowable(ex));
            throw ex;
        }

        return new ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onCancel() {
                try {
                    super.onCancel();
                } finally {
                    finish.accept(Status.CANCELLED);
                }
            }
        };
    }
}
```

Đoạn code minh họa các quyết định chính:

- Lấy getFullMethodName() và loại RPC từ MethodDescriptor.
- Bắt đầu đo khi server interceptor nhận call.
- Ghi Timer ở close để lấy status cuối cùng phía server.
- Ghi CANCELLED nếu listener nhận cancellation mà chưa có kết thúc khác.
- Dùng AtomicBoolean để tránh đếm hai lần khi close và onCancel cùng xuất hiện.
- Bắt lỗi ghi metrics để sự cố registry không làm hỏng RPC đang xử lý.

Nếu next.startCall ném exception đồng bộ, interceptor ghi status suy ra từ exception rồi ném lại để cơ chế xử lý lỗi của gRPC tiếp tục hoạt động. Với lỗi xảy ra sau khi handler đã trả listener, status cần được ghi khi server đóng call.

## 5. Đặt interceptor đúng vị trí trong chain

Nếu authentication interceptor từ chối call trước khi metrics interceptor nhìn thấy nó, request bị từ chối có thể không được ghi vào metric này. Muốn đo cả call thành công và call bị từ chối, metrics interceptor cần bao quanh các interceptor có thể short-circuit call.

Thứ tự chain thực tế phụ thuộc cách đăng ký và framework version. Hãy xác minh bằng integration test, không suy đoán chỉ từ thứ tự các dòng cấu hình. Nếu cần tách số liệu, có thể có metric riêng cho request bị chặn ở gateway/authentication layer.

Trong Spring gRPC, server thường được auto-configure. Đăng ký interceptor qua extension point mà phiên bản Spring gRPC của dự án hỗ trợ; khai báo một class thành bean không tự bảo đảm nó đã được gắn vào server. Kiểm thử bằng RPC thực và xác nhận Timer được cập nhật.

## 6. Đọc metric và phân tích latency

Với metric grpc.server.call, các dashboard thường cần:

| Chỉ số | Câu hỏi vận hành |
| --- | --- |
| Count theo method/status | Method nào có tải cao hoặc lỗi tăng? |
| Error rate theo method | Method nào có tỷ lệ status khác OK tăng? |
| p50 | Mức latency điển hình của call |
| p95/p99 | Nhóm call chậm ở đuôi phân phối |
| Tổng duration và call rate | Backend đang tiêu tốn thời gian xử lý ở method nào? |

Nếu dùng Prometheus registry và histogram, truy vấn p95 có thể có dạng:

```promql
histogram_quantile(
  0.95,
  sum by (le, method) (
    rate(grpc_server_call_seconds_bucket[5m])
  )
)
```

Tên metric xuất Prometheus phụ thuộc naming convention của registry và cấu hình ứng dụng; kiểm tra endpoint scrape thực tế trước khi dùng truy vấn. Không so sánh p95 của các method có semantics khác nhau mà không xem xét loại RPC và phân phối traffic.

## 7. Unary và streaming cần được phân tích riêng

Với unary RPC, một call có một request và một response; server call duration thường gần với thời gian xử lý toàn bộ request ở phía server.

Với streaming RPC, duration tại close phản ánh **tuổi thọ toàn call/stream**:

| RPC type | Timer tại close phản ánh | Metric bổ sung có thể cần |
| --- | --- | --- |
| Unary | Thời gian xử lý call | Queue time hoặc handler duration nếu cần phân rã |
| Server streaming | Thời gian stream mở đến khi hoàn tất/hủy | Time to first message, message count, inter-message interval |
| Client streaming | Thời gian nhận stream và tạo response cuối | Số request message, thời điểm client half-close |
| Bidirectional streaming | Tuổi thọ phiên trao đổi hai chiều | Message count hai chiều, idle duration, message latency |

Không gộp stream kéo dài hàng phút với unary request vào một dashboard latency mà không phân loại. Nếu cần metric từng message, bọc listener và đo onMessage/onNext theo một định nghĩa riêng; không gọi stream lifetime là message latency.

## 8. Server metric và client metric không giống nhau

Server metric bắt đầu khi server nhận call. Client metric thường bắt đầu khi client start call và kết thúc ở callback onClose. Client-observed latency bao gồm thời gian truyền request/response, queueing và xử lý ở server; server metric không bao gồm toàn bộ thời gian request đi từ client tới server.

Nếu instrument cả hai phía, dùng tên metric khác nhau, ví dụ grpc.server.call và grpc.client.call, đồng thời giữ cùng method label để so sánh. Không lấy hiệu hai số đo rồi khẳng định đó là network latency chính xác; hai phía có điểm bắt đầu/kết thúc và buffering khác nhau.

## 9. Kiểm thử metric theo method

Dùng SimpleMeterRegistry hoặc registry test để xác minh metric được ghi đúng. Các assertion cốt lõi:

```java
Timer timer = registry.find("grpc.server.call")
        .tag("method", "shop.catalog.v1.CatalogService/GetProduct")
        .tag("rpc_type", "unary")
        .tag("status", "OK")
        .timer();

assertNotNull(timer);
assertEquals(1L, timer.count());
assertTrue(timer.totalTime(TimeUnit.NANOSECONDS) >= 0L);
```

Đây là assertion sau khi test đã thực hiện một RPC thành công. Cần có thêm test cho:

- Method khác nhau tạo tag method khác nhau.
- NOT_FOUND, INVALID_ARGUMENT và UNAVAILABLE được ghi đúng status.
- Client cancellation chỉ ghi một lần.
- Unary và từng loại streaming có rpc_type đúng.
- Nhiều RPC đồng thời không chia sẻ thời điểm bắt đầu hoặc trạng thái ghi nhận.
- Authentication rejection được đo nếu chain được cấu hình để metrics interceptor quan sát call đó.
- Lỗi metrics không làm thay đổi response/status của RPC.

Test interceptor riêng có thể dùng in-process server/channel. Test Spring integration cần khởi động cấu hình server thực tế để xác minh interceptor được framework đăng ký.

## 10. Checklist triển khai

- [ ] Dùng full method name từ MethodDescriptor.
- [ ] Metric ghi method, RPC type và gRPC status bằng các tag hữu hạn.
- [ ] Dùng Timer để có count và duration; bật histogram/percentile theo nhu cầu.
- [ ] Đo duration bằng System.nanoTime().
- [ ] Ghi đúng một lần khi close, cancel hoặc lỗi khởi tạo.
- [ ] Metrics failure không làm hỏng RPC.
- [ ] Chain order cho phép đo các call bị authentication/policy từ chối nếu đó là yêu cầu.
- [ ] Không dùng request ID, user ID, resource ID, token hoặc exception message làm tag.
- [ ] Tách unary latency khỏi streaming lifetime và message latency.
- [ ] Tách server-side duration khỏi client-observed latency.
- [ ] Dashboard có request count, error rate và p50/p95/p99 theo method.
- [ ] Integration test xác minh metric thực sự được ghi trong Spring gRPC.

**Tự kiểm tra**

**Câu 1.** Vì sao nên dùng full method name làm tag method?

*Đáp án:* Nó phân biệt service, package version và method, tránh gộp các RPC trùng tên ngắn.

**Câu 2.** Micrometer Timer đã có thông tin nào mà thường không cần thêm Counter riêng?

*Đáp án:* Timer có count số lần ghi và tổng duration, ngoài các thống kê phân phối khi được cấu hình.

**Câu 3.** Vì sao không thêm request_id vào tag của Timer?

*Đáp án:* Request ID gần như duy nhất trên từng call, làm cardinality tăng không giới hạn và gây áp lực lên hệ thống metrics. Dùng ID trong log có kiểm soát.

**Câu 4.** Timer server streaming ghi tại close biểu diễn điều gì?

*Đáp án:* Tuổi thọ toàn stream từ lúc server nhận call đến lúc stream kết thúc hoặc bị hủy, không phải latency của một message.

**Câu 5.** Vì sao cần phân biệt server metric với client metric?

*Đáp án:* Client đo thời gian ứng dụng chờ, gồm network và xử lý server; server đo từ lúc nhận call tới khi server kết thúc. Hai metric có phạm vi khác nhau.

Đo metric theo RPC method giúp xác định chính xác method nào tạo tải, lỗi và latency cao. Dùng full method name cùng các tag hữu hạn, ghi Timer đúng một lần khi call kết thúc và phân loại riêng streaming; khi kết hợp dashboard percentile với integration test, số liệu sẽ hữu ích mà không làm metrics backend quá tải.
