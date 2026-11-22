# Interceptor cho unary và streaming

gRPC Java dùng cùng cơ chế interceptor cho cả unary RPC và streaming RPC. Điểm khác nhau nằm ở **số message và vòng đời call**: unary thường có một request và một response; streaming có thể trao đổi nhiều message trước khi call kết thúc. Vì vậy, interceptor cần được thiết kế theo từng RPC, đồng thời quan sát đúng các callback message, trạng thái kết thúc và cơ chế flow control.

Trong Spring gRPC, endpoint được framework đăng ký nhưng các interceptor vẫn bọc `ClientCall`/`ServerCall` và listener của gRPC Java. Bài này tập trung vào cách một interceptor xử lý cả bốn loại RPC, cách phân biệt call-level với message-level, và các lưu ý về cancellation, deadline, backpressure và kiểm thử.

## 1. Bốn loại RPC và điểm quan sát

Protocol Buffers định nghĩa kiểu RPC qua chữ ký method:

```proto
service CatalogService {
  // Một request, một response.
  rpc GetProduct(GetProductRequest) returns (Product);

  // Một request, nhiều response.
  rpc WatchProduct(WatchProductRequest) returns (stream ProductEvent);

  // Nhiều request, một response.
  rpc ImportProducts(stream ImportProductRequest)
      returns (ImportSummary);

  // Nhiều request, nhiều response.
  rpc SyncProducts(stream SyncProductRequest)
      returns (stream SyncProductEvent);
}
```

| RPC type | Client gửi | Server gửi | Điểm quan sát chính |
| --- | --- | --- | --- |
| Unary | Một request | Một response | Một lần gửi/nhận message và một lần kết thúc |
| Server streaming | Một request | Nhiều response | Server `sendMessage` nhiều lần; client listener nhận nhiều `onMessage` |
| Client streaming | Nhiều request | Một response | Server listener nhận nhiều `onMessage`; client gọi `sendMessage` nhiều lần rồi half-close |
| Bidirectional streaming | Nhiều request | Nhiều response | Hai chiều có thể trao đổi nhiều message độc lập cho tới khi call kết thúc |

Có thể đọc loại RPC từ descriptor:

```java
MethodDescriptor.MethodType rpcType =
        call.getMethodDescriptor().getType();
String fullMethodName =
        call.getMethodDescriptor().getFullMethodName();
```

`interceptCall` chỉ được gọi một lần cho mỗi RPC, không phải một lần cho từng message. Muốn quan sát message, interceptor phải bọc `ServerCall.Listener`, `ServerCall`, `ClientCall` hoặc `ClientCall.Listener` tùy hướng dữ liệu.

## 2. Vòng đời call và vòng đời message

Phía server:

```text
interceptCall
  -> next.startCall
      -> Listener.onMessage (0..n)
      -> Listener.onHalfClose
      -> ServerCall.sendMessage (0..n)
      -> ServerCall.close(status, trailers)
  -> Listener.onCancel nếu client hủy call
```

Phía client:

```text
interceptCall
  -> ClientCall.start(listener, headers)
  -> ClientCall.sendMessage (0..n)
  -> ClientCall.halfClose
  -> Listener.onHeaders
  -> Listener.onMessage (0..n)
  -> Listener.onClose(status, trailers)
```

Các callback không có nghĩa giống nhau:

- `onMessage` là một message đã được chuyển tới listener của phía nhận.
- `onHalfClose` phía server cho biết client đã ngừng gửi request message; với client streaming hoặc bidi, server vẫn có thể tiếp tục xử lý và gửi response.
- `ServerCall.close` đóng RPC từ phía server, mang status cuối cùng và trailers.
- `ClientCall.Listener.onClose` là kết quả cuối mà client quan sát.
- `onCancel` báo server biết call đã bị client hủy hoặc transport kết thúc theo hướng cancellation.

Không dùng `onHalfClose` làm thời điểm kết thúc toàn bộ call. Với client streaming, đó thường là thời điểm server có thể xử lý tổng hợp các request đã nhận; server còn phải gửi response cuối và đóng call.

## 3. Server interceptor đếm message cho mọi RPC type

Server interceptor có thể bọc cả `ServerCall` lẫn listener:

- `ServerCall.Listener.onMessage` đếm request message nhận từ client.
- `ServerCall.sendMessage` đếm response message server gửi.
- `ServerCall.close` ghi status cuối; `onCancel` ghi nhận cancellation nếu call chưa đóng.

Ví dụ dưới đây ghi một log tổng hợp cho mỗi call:

```java
package com.myshop.grpc.observability;

import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class ServerStreamMetricsInterceptor
        implements ServerInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(ServerStreamMetricsInterceptor.class);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String method = call.getMethodDescriptor().getFullMethodName();
        String rpcType = call.getMethodDescriptor()
                .getType().name().toLowerCase(Locale.ROOT);
        AtomicLong inbound = new AtomicLong();
        AtomicLong outbound = new AtomicLong();
        AtomicBoolean recorded = new AtomicBoolean();

        Consumer<Status> finish = status -> {
            if (recorded.compareAndSet(false, true)) {
                log.info(
                        "grpc.server.call method={} rpc_type={} inbound_messages={} outbound_messages={} status={}",
                        method, rpcType, inbound.get(), outbound.get(),
                        status.getCode());
            }
        };

        ServerCall<ReqT, RespT> wrappedCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
                    @Override
                    public void sendMessage(RespT message) {
                        outbound.incrementAndGet();
                        super.sendMessage(message);
                    }

                    @Override
                    public void close(Status status, Metadata trailers) {
                        finish.accept(status);
                        super.close(status, trailers);
                    }
                };

        final ServerCall.Listener<ReqT> listener;
        try {
            listener = next.startCall(wrappedCall, headers);
        } catch (RuntimeException ex) {
            finish.accept(Status.fromThrowable(ex));
            throw ex;
        }

        return new ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onMessage(ReqT message) {
                inbound.incrementAndGet();
                super.onMessage(message);
            }

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

Các bộ đếm được tạo bên trong `interceptCall`, vì vậy mỗi RPC có state riêng. Không đặt `AtomicLong` dùng chung trong field của interceptor singleton: nhiều call đồng thời sẽ trộn số message.

`outbound_messages` ở ví dụ là số lần server gọi `sendMessage`, còn `inbound_messages` là số callback `onMessage` đã chuyển tới listener. Đây là số lượng ở ranh giới API, không phải bằng chứng message đã được ứng dụng client xử lý thành công hoặc đã được ghi bền vững.

## 4. Client interceptor quan sát message hai chiều

Ở client, chiều gửi đi qua `ClientCall.sendMessage`; chiều nhận đi qua `ClientCall.Listener.onMessage`. `onClose` ghi status cuối:

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
import java.util.Locale;
import java.util.concurrent.atomic.AtomicLong;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class ClientStreamMetricsInterceptor
        implements ClientInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(ClientStreamMetricsInterceptor.class);

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        String fullMethodName = method.getFullMethodName();
        String rpcType = method.getType().name().toLowerCase(Locale.ROOT);
        AtomicLong outbound = new AtomicLong();
        AtomicLong inbound = new AtomicLong();

        ClientCall<ReqT, RespT> delegate =
                next.newCall(method, callOptions);

        return new ForwardingClientCall.SimpleForwardingClientCall<>(delegate) {
            @Override
            public void sendMessage(ReqT message) {
                outbound.incrementAndGet();
                super.sendMessage(message);
            }

            @Override
            public void start(Listener<RespT> listener, Metadata headers) {
                Listener<RespT> wrappedListener =
                        new ForwardingClientCallListener
                                .SimpleForwardingClientCallListener<>(listener) {
                            @Override
                            public void onMessage(RespT message) {
                                inbound.incrementAndGet();
                                super.onMessage(message);
                            }

                            @Override
                            public void onClose(Status status, Metadata trailers) {
                                log.info(
                                        "grpc.client.call method={} rpc_type={} outbound_messages={} inbound_messages={} status={}",
                                        fullMethodName, rpcType, outbound.get(),
                                        inbound.get(), status.getCode());
                                super.onClose(status, trailers);
                            }
                        };
                super.start(wrappedListener, headers);
            }
        };
    }
}
```

Client-side `outbound_messages` đếm lần ứng dụng gọi `sendMessage`; `inbound_messages` đếm message nhận tại listener. Với streaming, client có thể gửi nhiều message rồi gọi `halfClose` để báo đã gửi xong nhưng vẫn chờ response. Không coi `halfClose` là kết thúc RPC; status cuối chỉ có ở `onClose`.

## 5. Unary interceptor vẫn hữu ích

Với unary RPC, các wrapper message vẫn hoạt động nhưng số lượng thông thường là một request và một response. Interceptor chung có thể:

- Ghi method, status và duration cho mọi loại RPC.
- Gắn correlation ID hoặc trace metadata.
- Áp dụng authentication chung.
- Đếm request/response message mà không cần logic riêng cho unary.

Tuy nhiên, không nên ép mọi metric vào cùng một ý nghĩa. `message_count` của unary thường là 1/1, trong khi streaming có thể là hàng nghìn message. Nếu dashboard cần so sánh, hãy giữ nhãn `rpc_type` hoặc tách metric theo mục đích.

## 6. Flow control và backpressure: interceptor không được phá

Streaming RPC có thể truyền lượng message lớn. gRPC cung cấp flow control để bên gửi không đẩy dữ liệu nhanh hơn khả năng bên nhận xử lý. Interceptor quan sát message cần giữ nguyên cơ chế này:

- Không gọi thêm `request(n)` hoặc tăng demand thay cho ứng dụng.
- Không tự gọi `sendMessage` lần nữa, giữ bản sao message hoặc buffer vô hạn.
- Không trì hoãn callback `onMessage` bằng I/O blocking.
- Không thay đổi hành vi `isReady()`, `onReady()` hoặc `setOnReadyHandler` nếu không có lý do rõ ràng.
- Nếu cần buffering, đặt giới hạn bộ nhớ, chính sách overflow và cách hủy stream.

Với server streaming, ứng dụng nên tôn trọng trạng thái ready trước khi phát tiếp dữ liệu lớn. Với client streaming/bidi, client cần điều phối việc gửi theo demand và readiness thay vì gửi vô hạn trong một vòng lặp đồng bộ.

Interceptor chỉ đếm message như ví dụ trên không cần thay đổi demand hoặc buffer. Đó là lựa chọn an toàn hơn cho cross-cutting concern.

## 7. Cancellation, deadline và status

Một stream có thể kết thúc bình thường, lỗi, bị client hủy hoặc hết deadline:

| Tình huống | Server thường quan sát | Client thường quan sát |
| --- | --- | --- |
| Hoàn tất bình thường | `close(OK)` | `onClose(OK)` |
| Server trả lỗi nghiệp vụ | Status tương ứng khi close | Cùng status được truyền về client |
| Client chủ động cancel | `onCancel` | `onClose(CANCELLED)` |
| Deadline hết hạn | Server thường thấy call bị cancel | Client thường thấy `DEADLINE_EXCEEDED` |

Status ở hai phía có thể khác nhau khi deadline/cancellation xảy ra vì client biết deadline của chính call, còn server có thể chỉ thấy transport đã hủy. Không suy diễn nguyên nhân chính xác chỉ từ server `onCancel`.

Mọi state per-call cần được giải phóng khi kết thúc. Không giữ reference tới message, listener hoặc context trong collection toàn cục sau `close`/`onClose`. Nếu interceptor ghi metric/log ở cả `close` và `onCancel`, dùng cờ atomic để tránh ghi hai lần.

## 8. Đăng ký interceptor trong Spring gRPC

Core gRPC Java cho phép gắn interceptor vào server và channel:

```java
Server server = ServerBuilder.forPort(9090)
        .intercept(new ServerStreamMetricsInterceptor())
        .addService(catalogService)
        .build();

ManagedChannel channel = ManagedChannelBuilder
        .forAddress("catalog.internal", 9090)
        .useTransportSecurity()
        .intercept(new ClientStreamMetricsInterceptor())
        .build();
```

Trong Spring gRPC, server/channel thường do framework auto-configure. Đăng ký interceptor qua extension point mà phiên bản Spring gRPC của dự án hỗ trợ; chỉ khai báo class thành bean không tự bảo đảm nó được gắn vào mọi server/channel. Xác minh bằng integration test gọi đủ unary và streaming method.

Nếu có nhiều channel tới backend khác nhau, quyết định interceptor nào global và interceptor nào chỉ gắn vào một channel. Metrics có thể dùng chung, nhưng credential, tenant context và policy có thể khác nhau theo đích gọi.

## 9. Kiểm thử cả bốn RPC type

Một test unary đơn lẻ không đủ chứng minh interceptor đúng với streaming. Cần kiểm thử:

| Ca kiểm thử | Kết quả cần xác minh |
| --- | --- |
| Unary | Đếm một request/response và ghi status một lần |
| Server streaming | Một request, nhiều response; count outbound khớp số lần server gửi |
| Client streaming | Nhiều request, một response; `onHalfClose` không bị coi là kết thúc call |
| Bidirectional streaming | Count đúng cả hai chiều khi message xen kẽ |
| Stream bị cancel | Ghi cancellation một lần và giải phóng state |
| Deadline hết hạn | Client thấy `DEADLINE_EXCEEDED`; server xử lý cancellation an toàn |
| Flow control | Interceptor không thay đổi demand/readiness hoặc làm buffer tăng vô hạn |
| Nhiều call đồng thời | Bộ đếm từng call không bị trộn |
| Exception/close | Status gốc được giữ và không ghi trùng |

Có thể dùng in-process server/channel cho test gRPC thuần. Với Spring integration test, khởi động application context và thực hiện RPC qua cấu hình thật để xác nhận interceptor được đăng ký đúng. Dùng stream có nhiều message và stream bị hủy giữa chừng để kiểm tra lifecycle thực tế.

## 10. Checklist triển khai

- [ ] Dùng `MethodDescriptor.getType()` để phân loại unary/server streaming/client streaming/bidi streaming.
- [ ] `interceptCall` tạo state riêng cho từng RPC.
- [ ] Server đếm request ở listener `onMessage` và response ở `ServerCall.sendMessage`.
- [ ] Client đếm request ở `ClientCall.sendMessage` và response ở listener `onMessage`.
- [ ] `onHalfClose` chỉ được hiểu là client ngừng gửi message.
- [ ] Status cuối được ghi tại `ServerCall.close` hoặc client `onClose`.
- [ ] Cancellation/deadline được xử lý mà không ghi metric hai lần.
- [ ] Không can thiệp demand, readiness hoặc buffer nếu interceptor chỉ quan sát.
- [ ] Không giữ per-call state trong field dùng chung của interceptor singleton.
- [ ] Có test cho cả bốn RPC type, concurrency, cancellation và deadline.
- [ ] Xác minh đăng ký interceptor bằng Spring integration test.

**Tự kiểm tra**

**Câu 1.** `interceptCall` được gọi một lần cho mỗi message trong streaming RPC hay một lần cho cả call?

*Đáp án:* Một lần cho cả RPC. Muốn quan sát từng message phải bọc listener/call và xử lý các callback/send operation.

**Câu 2.** Ở server, callback nào đếm request message và method nào đếm response message?

*Đáp án:* `ServerCall.Listener.onMessage` đếm request nhận từ client; `ServerCall.sendMessage` đếm response server gửi.

**Câu 3.** Trong client streaming, `onHalfClose` có nghĩa RPC đã kết thúc chưa?

*Đáp án:* Chưa. Nó chỉ báo client đã gửi xong request stream; server vẫn có thể xử lý và gửi response cuối trước khi đóng call.

**Câu 4.** Vì sao interceptor đếm message không nên tự gọi `request(n)`?

*Đáp án:* `request(n)` điều khiển flow control/demand. Thay đổi nó có thể làm thay đổi backpressure và hành vi tiêu thụ stream của ứng dụng.

**Câu 5.** Vì sao bộ đếm phải nằm trong `interceptCall` thay vì field của interceptor?

*Đáp án:* Interceptor thường được dùng đồng thời cho nhiều RPC. State cục bộ trong mỗi lần `interceptCall` bảo đảm số message và status của từng call không bị trộn.

Interceptor cho unary và streaming dùng chung điểm mở rộng, nhưng phải tôn trọng khác biệt giữa call-level và message-level. Bọc đúng call/listener, giữ flow control nguyên vẹn, quản lý state riêng từng RPC và kiểm thử cả bốn kiểu trao đổi sẽ giúp interceptor hoạt động nhất quán trong Spring gRPC.
