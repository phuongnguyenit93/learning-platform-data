# Kiểm thử interceptor thành công và lỗi

Interceptor nằm trên đường đi của mỗi RPC nên một lỗi nhỏ có thể ảnh hưởng đồng thời nhiều service hoặc client. Kiểm thử cần chứng minh cả hai nhánh: request hợp lệ đi tiếp tới handler với đúng metadata/context; request không hợp lệ bị chặn bằng gRPC status phù hợp và không chạy nghiệp vụ.

Trong Spring gRPC, cần kiểm tra interceptor ở ba cấp: logic của interceptor, hành vi qua gRPC channel/server và việc Spring thực sự gắn interceptor vào đúng phạm vi. Bài này tập trung vào cách kiểm thử thành công, lỗi xác thực/phân quyền, status, metadata, thứ tự, concurrency và giới hạn của in-process test.

## 1. Xác định hợp đồng cần kiểm thử

Trước khi viết test, xác định rõ interceptor chịu trách nhiệm gì và điều gì phải đúng khi call thành công hoặc thất bại:

| Tình huống | Hành vi mong đợi |
| --- | --- |
| Credential hợp lệ | Interceptor xác thực, gắn principal vào gRPC `Context` và gọi `next.startCall(...)` |
| Thiếu credential | Đóng call với `UNAUTHENTICATED`; handler không được chạy |
| Credential sai/hết hạn | Đóng call với `UNAUTHENTICATED`; không tiết lộ chi tiết bí mật |
| Principal hợp lệ nhưng thiếu quyền | Trả `PERMISSION_DENIED`; handler không được chạy |
| Metadata sai định dạng | Trả lỗi client phù hợp, thường `INVALID_ARGUMENT` nếu đó là lỗi dữ liệu đầu vào |
| Lỗi dependency xác thực | Ánh xạ sang status đã quy định; không để exception tùy tiện rò ra wire |
| Call thành công | Response đúng; metrics/tracing/audit được ghi đúng một lần |
| Streaming call | Context và cleanup được giữ đúng trong suốt vòng đời stream |

Không nên chỉ assert rằng interceptor được gọi. Một test có giá trị phải xác minh kết quả quan sát được: status, response, metadata/context mà handler nhận, side effect được phép và việc handler không chạy khi request bị từ chối.

## 2. Chia test theo tầng

Một chiến lược cân bằng thường có ba tầng:

1. **Unit test policy:** kiểm tra logic xác thực, phân quyền, parse metadata và ánh xạ exception bằng fake/mock dependency.
2. **In-process gRPC test:** dựng server và channel trong cùng process để xác minh interceptor được gắn đúng, call đi qua chain, status và Context được truyền chính xác.
3. **Transport integration test:** dùng TCP/TLS thật khi cần kiểm tra certificate, HTTP/2, proxy, network, metadata qua gateway hoặc cấu hình channel do môi trường tạo.

Unit test chạy nhanh và chỉ rõ nhánh logic. In-process test xác minh hành vi gRPC mà không cần mở port mạng. Transport test chậm hơn nhưng cần thiết cho các vấn đề mà in-process transport không mô phỏng, đặc biệt TLS và proxy.

Không dùng mock để thay toàn bộ gRPC pipeline rồi kết luận interceptor hoạt động đúng. Ngược lại, cũng không cần khởi động cả hệ thống production chỉ để kiểm tra một nhánh `UNAUTHENTICATED`.

## 3. Kiểm thử server interceptor bằng in-process server

Ví dụ dưới đây dùng API key để minh họa. Interceptor xác thực key, đưa principal vào `Context` và từ chối call nếu key thiếu hoặc không hợp lệ:

```java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.Map;

final class ApiKeyInterceptor implements ServerInterceptor {
    static final Metadata.Key<String> API_KEY =
        Metadata.Key.of("x-api-key", Metadata.ASCII_STRING_MARSHALLER);
    static final Context.Key<String> CALLER = Context.key("caller");

    private final Map<String, String> principalsByKey;

    ApiKeyInterceptor(Map<String, String> principalsByKey) {
        this.principalsByKey = Map.copyOf(principalsByKey);
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String principal = principalsByKey.get(headers.get(API_KEY));
        if (principal == null) {
            call.close(
                Status.UNAUTHENTICATED.withDescription("Invalid credentials"),
                new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        Context context =
            Context.current().withValue(CALLER, principal);
        return Contexts.interceptCall(context, call, headers, next);
    }
}
```

Trong production, thay map minh họa bằng một `Authenticator` được inject. Không ghi API key vào log hoặc đưa key vào response error. Nếu authentication service ném exception, interceptor cần bắt và ánh xạ exception đã biết sang status; lỗi không mong đợi cần được ghi nhận an toàn và chuyển thành `INTERNAL` hoặc status theo error policy của ứng dụng.

Một service test có thể đọc principal từ Context để chứng minh interceptor đã truyền danh tính:

```java
final class OrdersTestService
        extends OrderServiceGrpc.OrderServiceImplBase {

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> observer) {
        String caller = ApiKeyInterceptor.CALLER.get();
        GetOrderResponse response = GetOrderResponse.newBuilder()
            .setOrderId(request.getOrderId())
            .setStatus("served-for-" + caller)
            .build();
        observer.onNext(response);
        observer.onCompleted();
    }
}
```

Service này chỉ dành cho test. Trong ứng dụng thật, handler dùng principal đã xác thực để áp dụng authorization nghiệp vụ, không ghép danh tính vào response.

## 4. Kiểm thử thành công, thiếu key và key sai

`InProcessServerBuilder` và `InProcessChannelBuilder` cho phép dựng server/channel mà không cần TCP port. Test sau kiểm tra cả nhánh thành công và nhánh bị từ chối:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import io.grpc.*;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.ServerServiceDefinition;
import java.io.IOException;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ApiKeyInterceptorTest {
    private Server server;
    private ManagedChannel channel;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        ServerServiceDefinition service =
            ServerInterceptors.intercept(
                new OrdersTestService().bindService(),
                new ApiKeyInterceptor(Map.of("test-key", "alice")));

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(service)
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow().awaitTermination(5, TimeUnit.SECONDS);
        }
        if (server != null) {
            server.shutdownNow().awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    @Test
    void validKeyReachesHandlerWithAuthenticatedContext() {
        GetOrderResponse response = stubWithKey("test-key").getOrder(
            GetOrderRequest.newBuilder().setOrderId("ORD-1").build());

        assertEquals("served-for-alice", response.getStatus());
    }

    @Test
    void missingKeyIsRejectedBeforeHandler() {
        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> OrderServiceGrpc.newBlockingStub(channel).getOrder(
                GetOrderRequest.newBuilder().setOrderId("ORD-1").build()));

        assertEquals(Status.Code.UNAUTHENTICATED,
            error.getStatus().getCode());
    }

    @Test
    void invalidKeyIsRejected() {
        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stubWithKey("wrong-key").getOrder(
                GetOrderRequest.newBuilder().setOrderId("ORD-1").build()));

        assertEquals(Status.Code.UNAUTHENTICATED,
            error.getStatus().getCode());
    }

    private OrderServiceGrpc.OrderServiceBlockingStub stubWithKey(
            String apiKey) {
        ClientInterceptor addKey = new ClientInterceptor() {
            @Override
            public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
                    MethodDescriptor<ReqT, RespT> method,
                    CallOptions callOptions,
                    Channel next) {
                return new ForwardingClientCall
                        .SimpleForwardingClientCall<ReqT, RespT>(
                            next.newCall(method, callOptions)) {
                    @Override
                    public void start(
                            Listener<RespT> listener,
                            Metadata headers) {
                        headers.put(ApiKeyInterceptor.API_KEY, apiKey);
                        super.start(listener, headers);
                    }
                };
            }
        };

        Channel wrapped = ClientInterceptors.intercept(channel, addKey);
        return OrderServiceGrpc.newBlockingStub(wrapped);
    }
}
```

Đoạn test giả định generated types `OrderServiceGrpc`, `GetOrderRequest` và `GetOrderResponse` đã được sinh từ proto của ứng dụng. `grpc-inprocess` và JUnit 5 cần có trong test dependencies. Test dùng `directExecutor()` để đơn giản hóa việc thực thi; nếu interceptor phụ thuộc scheduler hoặc callback bất đồng bộ, hãy thêm test với executor phù hợp.

Ba test trên xác minh:

- Key hợp lệ đi qua interceptor và handler đọc được principal trong Context.
- Thiếu key bị từ chối với `UNAUTHENTICATED`.
- Key sai cũng bị từ chối trước khi handler thực hiện nghiệp vụ.

Nên bổ sung `AtomicInteger` trong test service để assert handler không được gọi ở hai nhánh lỗi. Chỉ assert status có thể bỏ sót trường hợp interceptor đã gọi handler trước khi đóng call.

## 5. Kiểm thử authorization và status mapping

Authentication và authorization là hai quyết định riêng. Caller có thể được xác thực thành công nhưng không có quyền thực hiện một method.

| Điều kiện | Status thường dùng | Assertion nên có |
| --- | --- | --- |
| Thiếu credential | `UNAUTHENTICATED` | Handler không chạy |
| Credential sai/hết hạn | `UNAUTHENTICATED` | Không lộ lý do nội bộ hoặc token |
| Principal hợp lệ, thiếu role/scope | `PERMISSION_DENIED` | Authentication thành công nhưng policy từ chối |
| Metadata bắt buộc sai định dạng | `INVALID_ARGUMENT` | Error description ổn định, không chứa dữ liệu nhạy cảm |
| Dependency auth tạm unavailable | Thường `UNAVAILABLE` theo contract | Không biến lỗi hạ tầng thành lỗi credential |
| Lỗi không mong đợi | `INTERNAL` hoặc mapping chung đã quy định | Log có correlation ID, response không lộ stack trace |

Test authorization nên tạo ít nhất hai principal: một có quyền và một không có quyền. Gọi cùng method bằng cả hai principal; kiểm tra người có quyền thành công, người không có quyền nhận `PERMISSION_DENIED` và service handler không chạy cho call bị từ chối.

Không assert toàn bộ error description nếu nội dung có thể thay đổi hoặc chứa thông tin nội bộ. Ưu tiên status code, metadata error đã công bố và các side effect quan trọng.

## 6. Kiểm thử client interceptor và metadata

Client interceptor có thể thêm trace context, tenant header hoặc credential. Test cần xác minh header được gửi tới đúng server và không rò sang call khác.

Một test đơn giản có thể cho server test ghi nhận giá trị header vào `AtomicReference`, sau đó gọi stub qua channel đã bọc client interceptor và assert giá trị nhận được. Nên có cả hai stub: một stub dùng channel wrapper và một stub dùng channel gốc. Chỉ stub dùng wrapper mới được nhận metadata riêng.

Các trường hợp nên kiểm tra:

- Header được thêm đúng một lần.
- Header có sẵn từ caller được xử lý theo quy tắc merge/override đã chọn.
- Metadata nhạy cảm không xuất hiện trong log.
- Tenant/user của call trước không rò sang call sau.
- Credential refresh lấy giá trị mới ở call tiếp theo.
- Client interceptor không sửa shared `Metadata` object dùng đồng thời giữa nhiều call.

Đối với binary metadata, dùng key với marshaller phù hợp thay vì `ASCII_STRING_MARSHALLER`. Test cả tên key, kiểu dữ liệu và giới hạn kích thước header nếu ứng dụng có contract cụ thể.

## 7. Kiểm thử thứ tự và composition

Khi nhiều interceptor được ghép, test cần xác minh thứ tự thực tế mà ứng dụng yêu cầu:

- Authentication phải tạo principal trước khi authorization đọc principal.
- Trace context phải có sẵn khi metrics/audit ghi nhận call.
- Interceptor xử lý lỗi phải ghi nhận đúng status cuối.
- Interceptor service-specific chỉ chạy trên service được bọc.
- Interceptor global không bị đăng ký thêm lần nữa ở service scope nếu không chủ đích.

Không chỉ assert thứ tự khai báo trong configuration. Gắn các interceptor test ghi lại sự kiện `before` và `after` vào một list/thread-safe recorder, gọi RPC rồi so sánh trace sự kiện với contract mong đợi. Thứ tự wrapper/callback có thể phụ thuộc cách ghép interceptor và phiên bản grpc-java; test nên khóa hành vi thực tế của dự án.

Một test hữu ích có thể chạy hai service trên cùng server: service A được bọc authorization riêng, service B chỉ có global tracing. Gọi cả hai và xác minh interceptor riêng chỉ chạy với A.

## 8. Exception, cancellation, streaming và concurrency

Interceptor cần được kiểm thử ngoài đường unary thành công:

- **Exception trong authentication:** exception đã biết được map sang status; exception không mong đợi không làm lộ stack trace.
- **Client cancellation:** cleanup metrics/context/tài nguyên được thực hiện; không ghi call như thành công.
- **Deadline exceeded:** interceptor ghi nhận kết quả `DEADLINE_EXCEEDED` và không giữ tài nguyên sau khi call kết thúc.
- **Server streaming:** context cần tồn tại trong các callback xử lý message; cleanup chạy khi complete/error/cancel.
- **Client streaming/bidi streaming:** không giả định request kết thúc ngay sau `interceptCall`; kiểm tra listener lifecycle và callback.
- **Concurrent calls:** nhiều RPC đồng thời không chia sẻ principal, tenant, trace ID hoặc mutable request state.

Với streaming, test gửi nhiều message, kết thúc stream bình thường, sau đó test cancellation và lỗi giữa stream. Kiểm tra cleanup chỉ chạy một lần. Với concurrency, tạo nhiều call có principal/tenant khác nhau và xác minh response/audit của mỗi call gắn đúng identity.

Interceptor singleton trong Spring thường được nhiều thread dùng đồng thời. Test concurrency giúp phát hiện field mutable lưu request state, `Metadata` dùng chung hoặc cache không thread-safe.

## 9. Kiểm thử wiring trong Spring

Một interceptor bean tồn tại trong ApplicationContext không chứng minh nó đã được gắn vào server/channel. Integration test Spring cần xác minh:

1. Context tạo đúng interceptor bean và inject đúng dependency.
2. Server customizer hoặc extension point của Spring gRPC starter thực sự đăng ký interceptor.
3. Service-specific wrapper được áp dụng đúng service.
4. Client channel/stub do starter tạo nhận đúng client interceptor.
5. Không có interceptor trùng do vừa auto-configure vừa đăng ký thủ công.
6. Context shutdown đóng server/channel và tài nguyên mà interceptor sử dụng.

Có thể dùng `@SpringBootTest` với port động hoặc test slice/context phù hợp. Gọi RPC thật qua bean stub để kiểm tra hành vi; chỉ lấy bean bằng `ApplicationContext.getBean(...)` là chưa đủ.

API cấu hình của starter có thể khác theo phiên bản. Test nên chạy trên đúng cấu hình mà ứng dụng production sử dụng, thay vì dựng một `ServerBuilder` độc lập rồi suy ra starter đã wiring đúng.

## 10. Khi nào cần transport test thật?

In-process test rất phù hợp để kiểm tra interceptor chain, status, Context và metadata trong gRPC call. Nó không kiểm tra đầy đủ:

- TLS handshake, certificate chain, SAN và client certificate.
- HTTP/2 qua ingress, gateway hoặc service mesh.
- Header bị proxy loại bỏ hoặc chuẩn hóa.
- DNS, socket timeout và network interruption.
- Kích thước header/flow control trên transport thật.

Với interceptor tham gia authentication hoặc metadata qua proxy, cần ít nhất một integration test dùng TCP/TLS thật trong môi trường test. Test certificate mismatch phải thất bại; không sửa test bằng cách tắt hostname verification hoặc chuyển plaintext.

## 11. Ma trận kiểm thử đề xuất

| Nhóm | Ca kiểm thử cốt lõi | Điều kiện PASS |
| --- | --- | --- |
| Server success | Credential hợp lệ, handler trả response | Response đúng và principal đúng |
| Server failure | Thiếu/sai credential | `UNAUTHENTICATED`, handler không chạy |
| Authorization | Principal thiếu quyền | `PERMISSION_DENIED`, không có side effect |
| Error mapping | Auth dependency timeout/exception | Status theo contract, không lộ nội bộ |
| Client metadata | Client interceptor thêm header | Server nhận đúng header |
| Scope | Global và service-specific | Chỉ service/method đúng phạm vi được áp dụng |
| Composition | Nhiều interceptor | Thứ tự và số lần chạy đúng |
| Context | Nhiều principal đồng thời | Không rò identity giữa các call |
| Streaming | Complete, error, cancellation | Listener và cleanup đúng lifecycle |
| Spring wiring | Stub/server do Spring quản lý | Interceptor thực sự tham gia RPC |
| Transport | TLS/proxy/network | Hành vi phù hợp cấu hình thực |
| Lifecycle | Context/server/channel shutdown | Không còn scheduler, watch hoặc tài nguyên bị rò |

Không cần mọi test đều khởi động cả hệ thống. Chọn tầng test nhỏ nhất có thể chứng minh hợp đồng, rồi thêm một số integration test cho ranh giới Spring và transport.

## 12. Bài tập vận dụng

`OrderService` dùng server interceptor để xác thực API key, đặt principal vào gRPC `Context` và kiểm tra quyền `orders:cancel` cho method `CancelOrder`. Client interceptor thêm trace ID và tenant ID. Gần đây có lỗi: request thiếu key vẫn tạo audit record như đã xử lý thành công; tenant của hai request đồng thời đôi khi bị lẫn.

**Yêu cầu:**

1. Viết unit test cho authenticator: key hợp lệ, key sai, key hết hạn và dependency auth unavailable.
2. Viết in-process integration test chứng minh request hợp lệ nhận principal đúng trong Context.
3. Kiểm tra request thiếu/sai key trả `UNAUTHENTICATED` và không gọi handler hoặc ghi audit thành công.
4. Kiểm tra principal hợp lệ nhưng thiếu quyền `orders:cancel` trả `PERMISSION_DENIED`.
5. Kiểm tra client interceptor gửi trace/tenant metadata và tenant không rò giữa hai call đồng thời.
6. Kiểm tra thứ tự authentication → authorization → audit/metrics và xác nhận interceptor không chạy trùng.
7. Thêm test streaming cancellation và Spring wiring; dùng transport TLS thật cho phần certificate/proxy nếu ứng dụng có các ranh giới đó.

**Câu hỏi tự kiểm tra:**

- Vì sao test interceptor cần assert cả status và việc handler có được gọi hay không?
- `UNAUTHENTICATED` khác `PERMISSION_DENIED` thế nào?
- In-process test xác minh được gì và không xác minh được gì?
- Làm thế nào chứng minh principal đã được truyền qua gRPC `Context`?
- Vì sao client interceptor phải tạo metadata riêng cho từng call?
- Test nào phát hiện interceptor bị đăng ký trùng?
- Streaming cancellation ảnh hưởng cleanup và metrics ra sao?
- Vì sao Spring integration test phải gọi RPC qua stub do Spring quản lý?

**Ghi nhớ:** Kiểm thử interceptor phải bao phủ cả đường thành công lẫn đường từ chối, kiểm tra status, metadata, Context, handler side effect và thứ tự thực thi. Dùng unit test cho policy, in-process test cho gRPC chain, Spring integration test cho wiring và transport test cho TLS/proxy/network. Với interceptor singleton, luôn kiểm tra concurrency và streaming lifecycle để ngăn rò dữ liệu giữa các call.
