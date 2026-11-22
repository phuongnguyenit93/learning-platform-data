# Header hoặc trace context bị mất

Trong gRPC, thông tin thường được gọi là “header” được truyền dưới dạng **metadata** của RPC. Metadata đi theo từng lời gọi qua HTTP/2; nó không tự động trở thành header của Servlet request và cũng không tự động được chuyển tiếp khi service gọi sang một service khác. Trace context là một trường hợp đặc biệt: các giá trị như W3C **traceparent**, **tracestate** và **baggage** cũng được truyền qua metadata, thường nhờ bộ instrumentation của OpenTelemetry.

Khi header hoặc trace context biến mất, cần xác định chính xác nó mất ở chặng nào: lúc client tạo RPC, lúc server nhận RPC, khi ứng dụng chuyển sang luồng xử lý bất đồng bộ, hay khi service tạo một RPC tiếp theo. Kiểm tra từng ranh giới sẽ giúp tìm đúng interceptor hoặc context đang thiếu.

## 1. Nhận diện loại dữ liệu đang bị mất

Trước khi sửa, hãy phân biệt ba loại dữ liệu sau:

| Dữ liệu | Nơi lưu và cách truyền | Câu hỏi cần kiểm tra |
|---|---|---|
| Request metadata tùy chỉnh, ví dụ **x-request-id** hoặc **x-tenant-id** | **io.grpc.Metadata**, gửi cùng một RPC | Client có gắn metadata vào lời gọi không? Server có đọc đúng key không? |
| gRPC Context của ứng dụng | **io.grpc.Context**, gắn với quá trình xử lý RPC | Interceptor có đưa giá trị vào Context không? Context có còn hiện diện trong callback hoặc executor không? |
| Trace context | Context của OpenTelemetry, được inject/extract qua metadata như **traceparent** | Instrumentation có chạy ở cả client và server không? Span hiện tại có được truyền qua ranh giới bất đồng bộ không? |

Ba cơ chế này liên quan nhưng không đồng nhất. **io.grpc.Context** không phải **io.opentelemetry.context.Context**. Việc lưu **requestId** trong gRPC Context không tự tạo hoặc truyền trace context của OpenTelemetry.

Một số dấu hiệu thường gặp:

- Server nhận request nhưng **headers.get(...)** trả về **null**: kiểm tra metadata outbound, key và đăng ký client interceptor.
- Server đọc được metadata nhưng service gọi downstream không gửi tiếp: kiểm tra bước chuyển giá trị từ inbound metadata sang context và interceptor của channel outbound.
- Log của hai service có cùng request ID nhưng trace bị tách: kiểm tra OpenTelemetry extraction/injection và việc giữ OTel Context qua executor.
- **traceparent** có mặt ở server nhưng trace không xuất hiện trên giao diện quan sát: kiểm tra sampling, exporter và backend trước khi kết luận propagation bị lỗi.

## 2. Khoanh vùng theo từng chặng RPC

Với luồng A gọi B rồi B gọi C, hãy kiểm tra lần lượt bốn điểm:

1. **A trước khi gửi:** metadata đã được thêm vào **ClientCall** chưa?
2. **B khi nhận:** **ServerInterceptor** có nhìn thấy metadata không?
3. **B trong lúc xử lý:** giá trị đã được đưa vào context phù hợp và còn tồn tại trong callback hoặc tác vụ bất đồng bộ chưa?
4. **B trước khi gọi C:** interceptor của channel outbound có đọc được context và inject metadata vào RPC mới không?

Ghi lại một giá trị kiểm tra an toàn, chẳng hạn **x-request-id**, ở mỗi điểm. Với tracing, đối chiếu **traceId** và **spanId**: cùng một trace thường giữ nguyên **traceId**, trong khi mỗi service hoặc operation tạo span riêng với **spanId** khác nhau.

Nếu metadata có ở A nhưng mất trước B, tập trung vào client interceptor, channel đang được dùng và proxy trên đường truyền. Nếu B nhận được nhưng C không nhận, tập trung vào việc chuyển tiếp trong B. Nếu chỉ mất sau khi chuyển sang luồng bất đồng bộ, kiểm tra cơ chế truyền context của executor hoặc framework đang sử dụng.

## 3. Kiểm tra metadata key và marshaller

Tên metadata key phải viết thường. Giá trị văn bản dùng **Metadata.ASCII_STRING_MARSHALLER**; dữ liệu nhị phân dùng key có hậu tố **-bin** cùng binary marshaller.

~~~java
public final class GrpcMetadataKeys {
    private GrpcMetadataKeys() {}

    public static final Metadata.Key<String> REQUEST_ID =
            Metadata.Key.of("x-request-id", Metadata.ASCII_STRING_MARSHALLER);
}
~~~

Những lỗi thường gặp:

- Dùng tên key khác nhau giữa nơi gửi và nơi nhận, ví dụ **x-request-id** so với **request-id**.
- Dùng ASCII marshaller cho dữ liệu nhị phân hoặc quên hậu tố **-bin** với key nhị phân.
- Đặt tên metadata ứng dụng bắt đầu bằng **grpc-**, vốn dành cho giao thức gRPC.
- Gắn metadata vào một đối tượng **Metadata** nhưng không truyền nó vào **ClientCall.start**.
- Tạo một **Metadata** mới trong interceptor rồi vô tình làm mất các giá trị đã được interceptor trước đó thêm vào.

Không nên dùng metadata để truyền payload lớn. Metadata có giới hạn kích thước ở các thành phần trên đường truyền; proxy hoặc server có thể từ chối request nếu metadata vượt giới hạn. Không ghi toàn bộ metadata vào log vì có thể chứa token, thông tin định danh hoặc dữ liệu nhạy cảm.

## 4. Gắn metadata ở client bằng ClientInterceptor

Một **ClientInterceptor** là điểm phù hợp để bổ sung metadata cho các RPC outbound. Ví dụ dưới đây đọc request ID từ gRPC Context tại thời điểm lời gọi bắt đầu:

~~~java
public final class RequestIdClientInterceptor implements ClientInterceptor {

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        return new ForwardingClientCall.SimpleForwardingClientCall<>(
                next.newCall(method, callOptions)) {

            @Override
            public void start(Listener<RespT> listener, Metadata headers) {
                String requestId = RequestContext.REQUEST_ID.get();

                if (requestId != null && !requestId.isBlank()) {
                    headers.put(GrpcMetadataKeys.REQUEST_ID, requestId);
                }

                super.start(listener, headers);
            }
        };
    }
}
~~~

Context key dùng chung trong ví dụ:

~~~java
public final class RequestContext {
    private RequestContext() {}

    public static final Context.Key<String> REQUEST_ID =
            Context.key("request-id");
}
~~~

Khi bắt đầu một luồng xử lý có request ID, đặt giá trị vào context trong phạm vi gọi stub:

~~~java
OrderReply reply = Context.current()
        .withValue(RequestContext.REQUEST_ID, requestId)
        .call(() -> blockingStub.getOrder(request));
~~~

**Context.call(...)** có thể ném **Exception**, vì vậy hãy xử lý theo chữ ký của phương thức gọi. Với asynchronous stub, hãy tạo RPC trong phạm vi context còn hiệu lực; interceptor cần đọc context khi **ClientCall** được khởi tạo và bắt đầu.

Trong ứng dụng Spring gRPC, ví dụ trên minh họa cơ chế của grpc-java. Cần bảo đảm interceptor thực sự được gắn vào channel mà stub đang sử dụng, thông qua điểm cấu hình hoặc cơ chế đăng ký interceptor của phiên bản Spring gRPC trong dự án. Chỉ khai báo một bean **ClientInterceptor** không đủ nếu channel factory không đăng ký hoặc không sử dụng bean đó. Nếu ứng dụng có nhiều channel, hãy kiểm tra đúng channel của RPC bị lỗi.

## 5. Đọc metadata ở server và đưa vào gRPC Context

Server interceptor nhận metadata đầu vào. Nếu service hoặc interceptor outbound cần dùng lại request ID, hãy đưa giá trị vào gRPC Context trước khi chuyển quyền xử lý cho handler:

~~~java
public final class RequestIdServerInterceptor implements ServerInterceptor {

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String requestId = headers.get(GrpcMetadataKeys.REQUEST_ID);
        Context context = Context.current();

        if (requestId != null) {
            context = context.withValue(RequestContext.REQUEST_ID, requestId);
        }

        return Contexts.interceptCall(context, call, headers, next);
    }
}
~~~

**Contexts.interceptCall(...)** giúp gắn context vào quá trình xử lý RPC, bao gồm các callback của listener. Nếu chỉ đọc metadata trong interceptor rồi lưu vào một biến cục bộ, các thành phần xử lý ở phía sau sẽ không tự động nhìn thấy biến đó.

Đăng ký **ServerInterceptor** trên gRPC server bằng cơ chế tích hợp mà ứng dụng đang dùng. Kiểm tra interceptor có được áp dụng cho đúng service hay được đăng ký toàn cục theo cấu hình của dự án. Một interceptor được khai báo nhưng không nằm trong chuỗi xử lý server sẽ không quan sát được request.

Khi B gọi C, **RequestIdClientInterceptor** ở channel outbound có thể đọc **RequestContext.REQUEST_ID** và gửi lại key **x-request-id**. Đây là bước chuyển tiếp tường minh giữa hai RPC. gRPC không tự sao chép toàn bộ metadata từ RPC inbound sang RPC outbound.

Chỉ chuyển tiếp những key ứng dụng thực sự cần. Không chuyển tiếp nguyên trạng **authorization**, cookie hoặc metadata nội bộ sang một service khác nếu chưa xác định rõ ranh giới tin cậy và quyền truy cập.

## 6. Xử lý khi context biến mất trong tác vụ bất đồng bộ

gRPC Context có phạm vi gắn với luồng thực thi hiện tại. Khi ứng dụng chuyển công việc sang một executor tùy ý, **CompletableFuture** dùng common pool, **@Async**, hoặc scheduler của Reactor, context có thể không còn là context hiện tại trên luồng mới.

Một số cách xử lý:

- Với executor Java, dùng **Context.currentContextExecutor(executor)** hoặc **context.fixedContextExecutor(executor)** tại điểm gửi tác vụ, tùy theo ngữ nghĩa context mong muốn.
- Với một **Runnable** hoặc **Callable** cụ thể, dùng **Context.current().wrap(runnable)** hoặc **Context.current().wrap(callable)**.
- Với Reactor hoặc Spring asynchronous processing, dùng cơ chế context propagation tương thích với phiên bản framework và thư viện đang dùng; không giả định **ThreadLocal** được sao chép tự động.
- Với OpenTelemetry, bảo đảm OTel Context cũng được truyền qua ranh giới bất đồng bộ. Cơ chế truyền **io.grpc.Context** không thay thế cơ chế truyền **io.opentelemetry.context.Context**.

Ví dụ bọc một tác vụ với gRPC Context hiện tại:

~~~java
Context grpcContext = Context.current();

executor.execute(grpcContext.wrap(() -> {
    // Các thao tác trong tác vụ có thể đọc RequestContext.REQUEST_ID.
    downstreamStub.process(request);
}));
~~~

Nếu **downstreamStub** được gọi trong tác vụ này, interceptor outbound có thể đọc request ID từ gRPC Context. Khi lỗi chỉ xuất hiện dưới tải hoặc trong một nhánh asynchronous, hãy so sánh giá trị context ngay trước khi gửi tác vụ và bên trong tác vụ để xác định ranh giới làm mất context.

## 7. Kiểm tra trace context của OpenTelemetry

Với W3C Trace Context, các trường thường gặp là:

- **traceparent**: mang trace ID, parent span ID và cờ trace.
- **tracestate**: mang trạng thái vendor-specific nếu có.
- **baggage**: mang các thuộc tính được phép truyền giữa các service.

Nếu dùng OpenTelemetry instrumentation cho grpc-java, cần có instrumentation ở cả phía client và server. Phía client inject OTel Context hiện tại vào metadata outbound; phía server extract metadata inbound và khôi phục OTel Context trước khi tạo hoặc xử lý span. Kiểm tra instrumentation đã được gắn vào đúng channel và server đang chạy. Việc bật tracing ở một phía không bảo đảm context được truyền qua cả hai phía.

Nếu dự án dùng Spring Boot observability hoặc Micrometer Tracing kết hợp OpenTelemetry, hãy xác minh toàn bộ cấu hình bridge, propagator và instrumentation gRPC của phiên bản đang dùng. Không suy ra rằng tracing HTTP/Servlet tự động bao phủ gRPC server hoặc mọi **ManagedChannel**.

Không nên tự tạo **traceparent** bằng cách ghép chuỗi nếu OpenTelemetry đã quản lý propagation. Hai cơ chế inject/extract cùng hoạt động có thể ghi đè metadata, tạo span không liên kết hoặc khiến trace bị chia tách. Chọn một đường propagation thống nhất và kiểm tra thứ tự interceptor nếu ứng dụng có custom interceptor đọc OTel Context.

Phân biệt lỗi propagation với lỗi ghi nhận trace:

- Nếu **traceparent** không xuất hiện ở server, kiểm tra client instrumentation, metadata trên đường truyền và server extraction.
- Nếu server có trace context nhưng backend không hiển thị trace, kiểm tra sampling, exporter, collector và bộ lọc của backend.
- Nếu **traceId** thay đổi giữa hai service, kiểm tra extraction/injection hoặc việc tạo root span ngoài context hiện tại.
- Nếu **traceId** giữ nguyên nhưng quan hệ parent-child sai, kiểm tra span được tạo trước hay sau khi context được khôi phục và context có bị thay thế trong tác vụ bất đồng bộ không.

Một trace không được lấy mẫu có thể không được export dù propagation vẫn hoạt động. Vì vậy, cần quan sát metadata/context tại điểm nhận trước khi kết luận rằng thiếu trace trên giao diện quan sát đồng nghĩa với thiếu header.

## 8. Kiểm tra proxy, gateway và giới hạn metadata

Nếu client gửi metadata đúng nhưng server không nhận được, thử gọi trực tiếp tới server trong môi trường kiểm thử để xác định proxy hoặc gateway có làm rơi metadata không. Kiểm tra cấu hình allowlist/denylist header, quy tắc chuyển tiếp HTTP/2, giới hạn kích thước request header và cách gateway xử lý gRPC trailers.

Các điểm cần lưu ý:

- Metadata ứng dụng được ánh xạ thành HTTP/2 headers hoặc trailers trên đường truyền. Proxy có thể áp dụng quy tắc lọc riêng.
- Không dùng key dành riêng cho gRPC hoặc key có định dạng không hợp lệ.
- Phân biệt initial metadata với trailing metadata. Dữ liệu được server gửi trong trailers sẽ không xuất hiện trong metadata đầu vào của request.
- Một số gateway cần cấu hình tường minh để chuyển tiếp metadata tùy chỉnh hoặc baggage.
- So sánh kết quả khi đi qua gateway và khi gọi trực tiếp, đồng thời giữ nguyên phiên bản client, server và request để phép thử có ý nghĩa.

## 9. Kiểm thử để ngăn lỗi quay lại

Một kiểm thử tích hợp nên xác minh cả chiều gửi, chiều nhận và chuyển tiếp:

1. Tạo gRPC server kiểm thử có **ServerInterceptor** ghi nhận **x-request-id**.
2. Tạo client channel có **ClientInterceptor** và gọi một RPC với request ID xác định.
3. Xác nhận server nhận đúng giá trị.
4. Trong handler của server, gọi một service downstream giả lập bằng channel có interceptor outbound.
5. Xác nhận downstream nhận cùng request ID.
6. Lặp lại phép thử khi handler chuyển công việc qua executor để xác minh context được truyền đúng.
7. Nếu kiểm thử tracing, xác nhận trace context được extract và span downstream thuộc cùng trace; không chỉ kiểm tra một chuỗi header có mặt.

Có thể dùng in-process gRPC server/channel để kiểm thử interceptor mà không cần mở cổng mạng. Tuy nhiên, kiểm thử in-process không bao phủ proxy, gateway hoặc giới hạn HTTP/2 metadata; cần một kiểm thử qua hạ tầng thật khi nghi ngờ lỗi nằm trên đường truyền.

Trong log chẩn đoán, chỉ ghi các trường đã được cho phép như RPC method, request ID đã làm sạch và trạng thái có/không có trace context. Tránh ghi token, payload, toàn bộ baggage hoặc toàn bộ đối tượng **Metadata**.

## 10. Checklist xử lý nhanh

- [ ] Xác định key bị mất là metadata ứng dụng, gRPC Context hay OTel Context.
- [ ] Xác nhận client gọi đúng channel có **ClientInterceptor**.
- [ ] Xác nhận interceptor thêm metadata vào chính **headers** được truyền tới **ClientCall.start**.
- [ ] Kiểm tra key viết thường, đúng tên và dùng đúng marshaller.
- [ ] Xác nhận server interceptor được đăng ký trên đúng server/service.
- [ ] Đưa dữ liệu cần dùng tiếp vào context phù hợp trước khi gọi handler.
- [ ] Kiểm tra context tại mọi ranh giới executor, **@Async**, **CompletableFuture** hoặc Reactor.
- [ ] Với RPC downstream, xác nhận outbound interceptor inject lại metadata cần thiết.
- [ ] Với tracing, kiểm tra OpenTelemetry instrumentation và propagator ở cả client lẫn server.
- [ ] Nếu chỉ lỗi qua gateway, kiểm tra quy tắc chuyển tiếp và giới hạn metadata.
- [ ] Phân biệt propagation thành công với sampling hoặc export thất bại.

Khi đã xác định được chặng làm mất dữ liệu, sửa đúng điểm đăng ký interceptor hoặc truyền context, rồi giữ lại kiểm thử tích hợp cho cả RPC trực tiếp và RPC downstream.
