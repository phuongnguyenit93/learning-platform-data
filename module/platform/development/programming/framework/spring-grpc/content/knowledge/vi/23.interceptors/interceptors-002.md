# Ghi log method name và latency

Khi một RPC chậm hoặc trả lỗi, câu hỏi đầu tiên của người vận hành thường là: **method nào được gọi, kết thúc với status gì và mất bao lâu?** Ghi log trong từng service method dễ bị thiếu, không đồng nhất và khó bao phủ các call bị từ chối trước khi vào handler. Interceptor cho phép đo thời gian tại ranh giới gRPC, nơi có thể quan sát tên method và vòng đời call một cách nhất quán.

Trong **Spring gRPC**, có thể dùng server interceptor để đo thời gian xử lý phía server và client interceptor để đo thời gian mà ứng dụng client thực sự chờ. Hai số đo trả lời hai câu hỏi khác nhau. Bài này tập trung vào cách lấy full method name, chọn đúng điểm bắt đầu/kết thúc, ghi log có cấu trúc và xử lý riêng RPC streaming.

## 1. Ghi full method name thay vì chỉ tên hàm Java

Từ `ServerCall` hoặc `MethodDescriptor`, lấy:

```java
String methodName = call.getMethodDescriptor().getFullMethodName();
```

Với service Catalog, giá trị có dạng:

```text
shop.catalog.v1.CatalogService/GetProduct
```

Full method name chứa protobuf package, service và method. Nó hữu ích hơn tên method Java như `getProduct`, vì nhiều service có thể cùng có method tên `GetProduct`. Đây cũng là định danh phù hợp để phân nhóm log/metrics khi API có nhiều package version.

Không tự ghép tên từ class Java hoặc tên bean Spring. Nếu đổi protobuf package hoặc service, full method name trên wire thay đổi; interceptor sẽ tự ghi đúng định danh mà gRPC đang xử lý.

## 2. Đo latency bằng đồng hồ đơn điệu

Latency là khoảng thời gian giữa hai thời điểm. Dùng `System.nanoTime()` để đo duration:

```java
long startedAt = System.nanoTime();
// ... khi call kết thúc
long elapsedNanos = System.nanoTime() - startedAt;
double latencyMs = elapsedNanos / 1_000_000.0;
```

`nanoTime()` là đồng hồ đơn điệu, phù hợp đo thời lượng vì không bị điều chỉnh theo giờ hệ thống. `currentTimeMillis()` phù hợp ghi timestamp lịch, nhưng không nên dùng để tính elapsed time.

Trước khi viết interceptor, cần định nghĩa rõ latency đang đo:

| Phạm vi | Bắt đầu | Kết thúc | Ý nghĩa |
| --- | --- | --- | --- |
| Server-side call duration | Server nhận call trong interceptor | Server đóng call hoặc nhận cancellation | Thời gian call tồn tại phía server, gồm xử lý và thời gian stream mở |
| Client-observed latency | Client bắt đầu call | Client nhận callback `onClose` | Thời gian client chờ toàn bộ RPC, gồm transport, server và response |
| Handler execution time | Trước khi gọi application/service method | Sau khi logic handler hoàn tất | Thời gian thực thi một đoạn xử lý; không bao gồm toàn bộ vòng đời transport |

Không gọi tất cả các số đo này là “thời gian xử lý server”. Client-observed latency còn có network và queueing; server-side call duration có thể bao gồm thời gian chờ client gửi message hoặc đọc stream.

## 3. Server interceptor ghi method, status và latency

Ở server, bắt đầu đo trong `interceptCall`. Kết thúc thường được ghi khi `ServerCall.close` được gọi; nếu client hủy call, listener nhận `onCancel`. Dùng `AtomicBoolean` để bảo đảm một RPC chỉ ghi một bản ghi dù có nhiều callback kết thúc.

```java
package com.myshop.grpc.observability;

import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class RpcLoggingServerInterceptor implements ServerInterceptor {
    private static final Logger log =
            LoggerFactory.getLogger(RpcLoggingServerInterceptor.class);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String method = call.getMethodDescriptor().getFullMethodName();
        long startedAt = System.nanoTime();
        AtomicBoolean recorded = new AtomicBoolean();

        java.util.function.Consumer<Status> record = status -> {
            if (recorded.compareAndSet(false, true)) {
                long elapsedNanos = System.nanoTime() - startedAt;
                double latencyMs = elapsedNanos / 1_000_000.0;
                log.info(
                        "grpc.server.call method={} status={} latency_ms={}",
                        method, status.getCode(), latencyMs);
            }
        };

        ServerCall<ReqT, RespT> monitoredCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
                    @Override
                    public void close(Status status, Metadata trailers) {
                        record.accept(status);
                        super.close(status, trailers);
                    }
                };

        final ServerCall.Listener<ReqT> listener;
        try {
            listener = next.startCall(monitoredCall, headers);
        } catch (RuntimeException ex) {
            record.accept(Status.fromThrowable(ex));
            throw ex;
        }

        return new ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onCancel() {
                try {
                    super.onCancel();
                } finally {
                    record.accept(Status.CANCELLED);
                }
            }
        };
    }
}
```

Các điểm cần chú ý:

- `getFullMethodName()` cung cấp method name đầy đủ mà không phải tự ghép chuỗi.
- Bắt đầu thời gian trước `next.startCall`, do đó phép đo bao gồm phần khởi tạo handler.
- `close(Status, Metadata)` cho biết status mà server kết thúc call.
- `onCancel()` ghi nhận trường hợp client hủy call mà server chưa gửi response kết thúc.
- `AtomicBoolean` tránh log hai lần nếu cancellation và close cùng xuất hiện.
- `finally` bảo đảm việc ghi nhận vẫn xảy ra khi delegate close hoặc callback kết thúc có lỗi.

Ví dụ ghi `CANCELLED` khi nhận `onCancel`; nếu hệ thống cần phân biệt cancellation do deadline với người dùng chủ động hủy, hãy bổ sung thông tin deadline/cause từ gRPC Context và kiểm thử theo phiên bản gRPC Java đang dùng. Không suy đoán nguyên nhân chỉ từ callback này.

## 4. Client interceptor đo thời gian client thực sự chờ

Client interceptor đo từ lúc call được start đến khi nhận `onClose`. Cách này hữu ích để so sánh trải nghiệm client với thời gian phía server:

```java
package com.myshop.grpc.observability;

import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.ForwardingClientCallListener;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.grpc.Status;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class RpcLoggingClientInterceptor implements ClientInterceptor {
    private static final Logger log =
            LoggerFactory.getLogger(RpcLoggingClientInterceptor.class);

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        String methodName = method.getFullMethodName();
        ClientCall<ReqT, RespT> delegate = next.newCall(method, callOptions);

        return new ForwardingClientCall.SimpleForwardingClientCall<>(delegate) {
            @Override
            public void start(Listener<RespT> listener, Metadata headers) {
                long startedAt = System.nanoTime();
                Listener<RespT> monitoredListener =
                        new ForwardingClientCallListener
                                .SimpleForwardingClientCallListener<>(listener) {
                            @Override
                            public void onClose(Status status, Metadata trailers) {
                                double latencyMs =
                                        (System.nanoTime() - startedAt) / 1_000_000.0;
                                try {
                                    super.onClose(status, trailers);
                                } finally {
                                    log.info(
                                            "grpc.client.call method={} status={} latency_ms={}",
                                            methodName, status.getCode(), latencyMs);
                                }
                            }
                        };
                super.start(monitoredListener, headers);
            }
        };
    }
}
```

Client đo tới `onClose`, vì vậy call bị hủy hoặc deadline hết hạn vẫn có callback kết thúc và status tương ứng. Đừng đo ở `interceptCall` rồi kết thúc ngay khi `start` trả về: `start` chỉ khởi động RPC, không có nghĩa response đã về.

Client và server có thể ghi cùng full method name nhưng duration khác nhau. Đó là điều bình thường:

- Client duration bao gồm thời gian truyền request/response, network và chờ phía server.
- Server duration bắt đầu khi server nhận call, không bao gồm thời gian request đi từ client tới server.
- Chênh lệch không tự động là network latency chính xác vì hai phía có thể có queueing, buffering và thời điểm đo khác nhau.

## 5. Unary và streaming có ý nghĩa latency khác nhau

Với unary RPC, một call thường có một request và một response. Đo từ lúc bắt đầu tới `onClose` là độ trễ toàn bộ thao tác mà client quan sát.

Với server streaming, client có thể nhận nhiều message trong một khoảng thời gian dài. `onClose` chỉ xảy ra khi stream kết thúc, vì vậy duration là **tuổi thọ toàn stream**, không phải thời gian trả message đầu tiên hay latency của từng message.

| Loại RPC | Đo tại `onClose` | Số đo bổ sung có thể cần |
| --- | --- | --- |
| Unary | End-to-end call latency | Server handler duration |
| Server streaming | Tổng thời gian stream mở | Time to first message, message count, inter-message interval |
| Client streaming | Thời gian từ khi mở call đến khi response cuối kết thúc | Thời gian nhận request stream, số message, thời điểm client half-close |
| Bidirectional streaming | Tuổi thọ toàn phiên trao đổi | Message count hai chiều, thời gian message đầu/cuối, thời gian idle |

Không ghi một metric tên `rpc_latency` rồi gộp cả unary và stream dài hàng giờ. Dùng tên/nhãn mô tả đúng ý nghĩa, hoặc tách metric theo RPC type. Nếu cần đo latency từng message, bọc `ClientCall.Listener.onMessage` hoặc `ServerCall.Listener.onMessage` và định nghĩa rõ thời điểm bắt đầu/kết thúc cho từng message.

## 6. Log có cấu trúc, status và dữ liệu nhạy cảm

Một log record hữu ích thường gồm:

| Trường | Ví dụ | Lưu ý |
| --- | --- | --- |
| `method` | `shop.catalog.v1.CatalogService/GetProduct` | Nhãn có tập giá trị hữu hạn theo API |
| `status` | `OK`, `NOT_FOUND`, `UNAVAILABLE` | Dùng gRPC status code, không chỉ ghi chuỗi lỗi |
| `latency_ms` | `18.42` | Duration được tính từ `nanoTime()` |
| `side` | `server`, `client` | Phân biệt điểm đo |
| `request_id` | ID correlation nếu có | Có thể đưa vào log có kiểm soát; không dùng làm metric label |

Ví dụ log tham số hóa:

```text
grpc.server.call method=shop.catalog.v1.CatalogService/GetProduct status=OK latency_ms=18.42
```

Không ghi toàn bộ request/response, authorization header, token, dữ liệu cá nhân hoặc metadata tùy ý. Nếu cần correlation, lấy request ID đã được kiểm soát và áp dụng chính sách che/giới hạn retention của hệ thống. Với call thất bại, status code thường đủ để phân nhóm; description có thể chứa dữ liệu do caller gửi nên không tự động log.

Log mỗi RPC ở mức INFO có thể tạo lượng lớn dữ liệu. Trong production, cân nhắc:

- Ghi tất cả call vào metrics histogram; chỉ log lỗi và call vượt ngưỡng latency.
- Sample các call thành công theo tỷ lệ có kiểm soát.
- Đặt ngưỡng slow-call theo từng nhóm method thay vì một ngưỡng cho toàn hệ thống.
- Giữ log structured và parameterized, tránh nối chuỗi hoặc serialize payload.

## 7. Kết hợp log với metrics latency

Log giúp điều tra từng call; metrics giúp nhìn phân phối và xu hướng. Với Micrometer, có thể ghi duration vào `Timer` với tag có cardinality thấp:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;

void recordLatency(
        MeterRegistry registry,
        String method,
        String status,
        long elapsedNanos) {
    Timer.builder("grpc.server.call")
            .description("Server-side gRPC call duration")
            .tag("method", method)
            .tag("status", status)
            .register(registry)
            .record(elapsedNanos, TimeUnit.NANOSECONDS);
}
```

Timer có thể cung cấp count, total time và histogram/percentile tùy cấu hình registry. Không tạo tag từ request ID, user ID, product ID hoặc exception message: mỗi giá trị mới có thể tạo một time series mới, làm tăng bộ nhớ và chi phí monitoring.

Nên theo dõi p50/p95/p99 cùng request count và error rate. Trung bình thấp không có nghĩa hệ thống khỏe nếu một nhóm nhỏ call có latency rất cao. Với streaming, tách metric stream lifetime khỏi unary latency và cân nhắc metric message-level riêng.

## 8. Đăng ký interceptor và kiểm thử

Core gRPC Java cho phép gắn interceptor vào server builder:

```java
Server server = ServerBuilder.forPort(9090)
        .intercept(new RpcLoggingServerInterceptor())
        .addService(new CatalogGrpcEndpoint(catalogService))
        .build();
```

Ở client:

```java
ManagedChannel channel = ManagedChannelBuilder
        .forAddress("catalog.internal", 9090)
        .useTransportSecurity()
        .intercept(new RpcLoggingClientInterceptor())
        .build();
```

Trong Spring gRPC, server/channel thường do framework cấu hình. Đăng ký interceptor qua extension point mà đúng phiên bản Spring gRPC đang dùng hỗ trợ; việc khai báo class thành bean không tự chứng minh nó đã được gắn vào server hoặc channel. Hãy xác minh bằng integration test với RPC thực.

Các test quan trọng:

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| Unary trả `OK` | Log đúng full method name, status và latency không âm |
| Unary trả `NOT_FOUND`/`INVALID_ARGUMENT` | Status được ghi đúng, không mất do wrapper |
| Client cancel hoặc deadline | Client `onClose` và server `onCancel` được ghi nhận; không log trùng |
| Nhiều call đồng thời | Thời điểm bắt đầu và status không bị dùng chung giữa call |
| Server streaming | Duration chỉ được ghi khi stream kết thúc/hủy |
| Method cùng tên ở package khác nhau | Log phân biệt full method name |
| Metadata chứa token/PII | Log không ghi raw header hoặc payload |

Có thể dùng in-process server/channel để test interceptor nhanh. Với test Spring, khởi động cấu hình ứng dụng để kiểm tra interceptor thực sự được framework đăng ký.

## 9. Checklist triển khai

- [ ] Dùng `getFullMethodName()` để lấy method identity.
- [ ] Định nghĩa rõ server duration, client-observed latency hay handler execution time.
- [ ] Dùng `System.nanoTime()` cho phép đo duration.
- [ ] Ghi status cuối cùng và bảo đảm mỗi call chỉ ghi một lần.
- [ ] Bao phủ cancellation, lỗi khởi tạo call và callback kết thúc.
- [ ] Phân biệt unary latency với stream lifetime và message latency.
- [ ] Log có cấu trúc, không ghi payload, token hoặc metadata nhạy cảm.
- [ ] Không dùng request/user/resource ID làm metric label.
- [ ] Theo dõi percentile và error rate, không chỉ trung bình.
- [ ] Kiểm thử thứ tự wrapper, concurrency và interceptor registration trong Spring.

**Tự kiểm tra**

**Câu 1.** Vì sao nên dùng `getFullMethodName()` thay vì ghi `getProduct`?

*Đáp án:* Full method name bao gồm package, service và method nên phân biệt được các RPC trùng tên ở service/version khác nhau.

**Câu 2.** Vì sao `System.nanoTime()` phù hợp hơn `currentTimeMillis()` để đo latency?

*Đáp án:* `nanoTime()` là đồng hồ đơn điệu dùng để đo khoảng thời gian; thời gian lịch có thể bị điều chỉnh.

**Câu 3.** Đo từ client `start` đến `onClose` phản ánh điều gì?

*Đáp án:* Thời gian client quan sát toàn bộ call, gồm truyền dữ liệu, network, xử lý server và chờ response cuối.

**Câu 4.** Với server streaming, đo đến `onClose` có phải latency của message đầu tiên không?

*Đáp án:* Không. Nó là tuổi thọ toàn stream. Muốn đo time-to-first-message phải ghi thêm thời điểm nhận message đầu.

**Câu 5.** Vì sao không dùng request ID làm tag của Micrometer Timer?

*Đáp án:* Request ID có giá trị gần như duy nhất cho mỗi call, tạo cardinality rất cao và làm monitoring tốn bộ nhớ/tài nguyên. Chỉ dùng nó trong log có kiểm soát.

Ghi method name và latency ở interceptor giúp quan sát RPC nhất quán mà không phải sửa từng service method. Hãy chọn đúng điểm kết thúc, ghi status một lần, phân biệt thời gian phía client/server và xử lý streaming theo tuổi thọ của stream; log và metrics khi đó sẽ hữu ích cho cả điều tra lỗi lẫn theo dõi hiệu năng.
