# Kiểm tra metadata contract

Trong Spring gRPC, protobuf định nghĩa request/response body, còn gRPC metadata mang thông tin điều khiển đi kèm RPC như correlation ID, tenant context, authentication credential, tracing context và thông tin bổ sung ở response/trailers. Metadata không có schema proto riêng, nên tên key, kiểu giá trị hoặc thời điểm gửi có thể thay đổi mà compile vẫn thành công.

Metadata contract test bảo vệ những key/value mà client và server đã thống nhất: key đúng tên và kiểu, metadata bắt buộc phải có, giá trị được kiểm tra đúng, duplicate có semantics rõ ràng, response headers/trailers được gửi đúng thời điểm và dữ liệu nhạy cảm không bị lộ. Bài này tập trung vào kiểm thử metadata ở ranh giới transport của Spring gRPC.

## 1. Metadata nằm ở đâu trong một RPC?

Một RPC có ba vùng metadata chính:

| Vùng | Hướng | Thời điểm | API thường dùng |
| --- | --- | --- | --- |
| Request headers | Client → Server | Khi bắt đầu call, trước message đầu tiên | ClientCall.start và server interceptor |
| Initial response headers | Server → Client | Trước response message đầu tiên | ServerCall.sendHeaders; client listener onHeaders |
| Trailers | Server → Client | Khi call kết thúc, cùng status cuối | ServerCall.close; client listener onClose |

Request metadata thường mang correlation ID, tenant ID, credential hoặc trace context. Initial response headers có thể mang server version hoặc request ID để client đối chiếu log. Trailers phù hợp với thông tin kết thúc call như error reason hoặc quota metadata nếu đó là một phần contract.

Metadata khác protobuf message:

- Metadata thuộc transport và có thể được interceptor xử lý trước khi service nhận request body.
- Protobuf message là dữ liệu nghiệp vụ có schema, field number, type và compatibility rules.
- Không chuyển các field nghiệp vụ như product_id, quantity hoặc nội dung payload sang metadata chỉ để interceptor đọc.

## 2. Quy tắc đặt metadata key và kiểu giá trị

gRPC metadata key dùng tên ASCII chữ thường, thường theo dạng x-request-id, x-tenant-id hoặc authorization. Key dành cho binary value phải kết thúc bằng -bin. Không tự tạo key bắt đầu bằng grpc-; prefix đó dành cho protocol/runtime.

Trong gRPC Java, kiểu marshaller của key xác định cách encode/decode value:

```java
static final Metadata.Key<String> REQUEST_ID =
        Metadata.Key.of("x-request-id", Metadata.ASCII_STRING_MARSHALLER);

static final Metadata.Key<String> TENANT_ID =
        Metadata.Key.of("x-tenant-id", Metadata.ASCII_STRING_MARSHALLER);

static final Metadata.Key<byte[]> SIGNATURE =
        Metadata.Key.of(
                "x-payload-signature-bin",
                Metadata.BINARY_BYTE_MARSHALLER);

static final Metadata.Key<String> WARNING =
        Metadata.Key.of("x-warning", Metadata.ASCII_STRING_MARSHALLER);
static final Metadata.Key<String> SERVER_VERSION =
        Metadata.Key.of("x-server-version", Metadata.ASCII_STRING_MARSHALLER);
static final Metadata.Key<String> SERVICE_REGION =
        Metadata.Key.of("x-service-region", Metadata.ASCII_STRING_MARSHALLER);
```

ASCII metadata dùng ASCII_STRING_MARSHALLER; không giả định marshaller này chấp nhận Unicode tùy ý. Binary metadata dùng BINARY_BYTE_MARSHALLER; gRPC runtime xử lý biểu diễn wire, không cần tự base64 value trước khi put.

Metadata thường có giới hạn kích thước ở client, server hoặc proxy. Chỉ đưa giá trị ngắn cần thiết cho transport; dữ liệu lớn, danh sách dài hoặc object nghiệp vụ nên nằm trong protobuf body hay một resource được tham chiếu.

## 3. Xác định cardinality và semantics của từng key

Một metadata key có thể xuất hiện nhiều lần. Contract cần nói rõ key là đơn trị hay đa trị:

| Key | Cardinality gợi ý | Semantics |
| --- | --- | --- |
| x-request-id | Một giá trị | ID duy nhất cho một RPC |
| x-tenant-id | Một giá trị | Tenant context đã xác thực |
| authorization | Một giá trị | Credential theo security contract |
| x-feature-flag-bin | Có thể nhiều giá trị nếu được định nghĩa | Binary option; cần quy tắc thứ tự/duplicate |
| x-warning | Có thể nhiều giá trị | Các warning độc lập |

Nếu key chỉ được phép xuất hiện một lần, server nên từ chối duplicate hoặc định nghĩa rõ giá trị nào được dùng. Không dựa vào tình cờ của thứ tự duplicate. Nếu key đa trị, đọc bằng Metadata.getAll(key) và kiểm tra tập hợp/thứ tự theo contract thay vì chỉ gọi Metadata.get(key).

Ví dụ đọc repeated metadata:

```java
Iterable<String> warnings = headers.getAll(WARNING);
List<String> received = warnings == null
        ? List.of()
        : StreamSupport.stream(warnings.spliterator(), false).toList();

assertEquals(List.of("stale-cache", "partial-result"), received);
```

Không dùng cùng một key lúc thì ASCII string, lúc thì binary bytes. Key và marshaller là một phần contract; thay đổi suffix -bin hoặc kiểu value có thể làm client/server không đọc được metadata.

Với key đơn trị như request ID, test nên xác minh số lượng value đúng một thay vì chỉ đọc một value bất kỳ:

```java
Iterable<String> requestIds = headers.getAll(REQUEST_ID);
List<String> values = requestIds == null
        ? List.of()
        : StreamSupport.stream(requestIds.spliterator(), false).toList();
assertEquals(1, values.size());
assertFalse(values.get(0).isBlank());
```

## 4. Gắn request metadata từ client interceptor

Client interceptor là nơi phù hợp để thêm metadata xuyên suốt như request ID hoặc trace context:

```java
public final class RequestIdClientInterceptor implements ClientInterceptor {
    private final Supplier<String> requestIds;

    public RequestIdClientInterceptor(Supplier<String> requestIds) {
        this.requestIds = requestIds;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {
        ClientCall<ReqT, RespT> delegate = next.newCall(method, callOptions);
        return new ForwardingClientCall.SimpleForwardingClientCall<>(delegate) {
            @Override
            public void start(Listener<RespT> listener, Metadata headers) {
                if (headers.get(REQUEST_ID) == null) {
                    headers.put(REQUEST_ID, requestIds.get());
                }
                super.start(listener, headers);
            }
        };
    }
}
```

Interceptor có thể được dùng chung cho nhiều RPC; vì vậy không lưu request ID hiện tại vào field mutable. Sinh ID trong start hoặc nhận giá trị call-scoped từ Context. Nếu caller đã cung cấp request ID, giữ giá trị đó theo policy đã công bố; nếu interceptor luôn ghi đè, phải ghi rõ đây là hành vi contract.

Với authentication, ưu tiên CallCredentials hoặc integration bảo mật của framework để cấp credential theo call và hỗ trợ refresh bất đồng bộ. Không hard-code bearer token vào singleton interceptor và không ghi authorization metadata vào log.

## 5. Xác minh request metadata tại server

Server interceptor nhìn thấy request metadata trước khi handler nhận message:

```java
public final class RequestMetadataInterceptor implements ServerInterceptor {
    static final Context.Key<String> REQUEST_ID_CONTEXT =
            Context.key("request-id");

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {
        String requestId = headers.get(REQUEST_ID);
        String tenantId = headers.get(TENANT_ID);

        if (requestId == null || requestId.isBlank()) {
            call.close(Status.INVALID_ARGUMENT.withDescription(
                    "x-request-id is required"), new Metadata());
            return new ServerCall.Listener<>() {};
        }
        if (tenantId == null || tenantId.isBlank()) {
            call.close(Status.INVALID_ARGUMENT.withDescription(
                    "x-tenant-id is required"), new Metadata());
            return new ServerCall.Listener<>() {};
        }

        Context context = Context.current().withValue(REQUEST_ID_CONTEXT, requestId);
        return Contexts.interceptCall(context, call, headers, next);
    }
}
```

Đây là ví dụ contract yêu cầu hai metadata key. Trong ứng dụng thật, tenant ID phải được ràng buộc với principal đã xác thực; không tin tenant ID do client tự gửi nếu chưa kiểm tra quyền truy cập. Metadata thiếu/sai được trả status theo contract, còn thông tin chi tiết nội bộ chỉ ghi trong server log có kiểm soát.

## 6. Kiểm tra initial response headers và trailers

Server gửi initial headers qua ServerCall.sendHeaders(headers) trước response message đầu tiên. Trailers được gửi khi đóng call bằng ServerCall.close(status, trailers). Client low-level listener nhận chúng qua onHeaders và onClose.

Một server interceptor có thể bổ sung metadata ở hai điểm:

```java
ServerCall<ReqT, RespT> forwarding =
        new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
            @Override
            public void close(Status status, Metadata trailers) {
                trailers.put(SERVICE_REGION, "ap-southeast");
                super.close(status, trailers);
            }
        };

ServerCall.Listener<ReqT> listener = next.startCall(forwarding, headers);
Metadata initialHeaders = new Metadata();
initialHeaders.put(SERVER_VERSION, "catalog-v2");
forwarding.sendHeaders(initialHeaders);
return listener;
```

Trong ví dụ, server version nằm ở initial headers và region nằm ở trailers. Chỉ thêm metadata vào đúng thời điểm; không gọi sendHeaders nhiều lần và không sửa trailers sau khi close đã được gọi.

Generated StreamObserver API không trực tiếp đưa response headers/trailers cho caller. Nếu client cần kiểm tra chúng, dùng ClientInterceptor bọc ClientCall.Listener hoặc một API client hỗ trợ metadata rõ ràng.

## 7. Client interceptor thu metadata để contract test

Client interceptor có thể ghi nhận initial headers và trailers vào holder riêng của test:

```java
final class MetadataCaptureInterceptor implements ClientInterceptor {
    final AtomicReference<Metadata> responseHeaders = new AtomicReference<>();
    final AtomicReference<Metadata> responseTrailers = new AtomicReference<>();

    private static Metadata copy(Metadata source) {
        Metadata target = new Metadata();
        target.merge(source);
        return target;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {
        ClientCall<ReqT, RespT> delegate = next.newCall(method, callOptions);
        return new ForwardingClientCall.SimpleForwardingClientCall<>(delegate) {
            @Override
            public void start(Listener<RespT> listener, Metadata headers) {
                super.start(
                        new ForwardingClientCallListener.SimpleForwardingClientCallListener<>(listener) {
                            @Override
                            public void onHeaders(Metadata received) {
                                responseHeaders.set(copy(received));
                                super.onHeaders(received);
                            }

                            @Override
                            public void onClose(Status status, Metadata trailers) {
                                responseTrailers.set(copy(trailers));
                                super.onClose(status, trailers);
                            }
                        },
                        headers);
            }
        };
    }
}
```

Metadata được copy vì object nhận từ callback không nên bị giữ rồi dùng chung ngoài lifecycle của call. Mỗi test nên có capture holder riêng; không chia sẻ một AtomicReference giữa nhiều RPC song song nếu không định danh kết quả theo call.

## 8. Provider contract test cho request, headers và trailers

Một in-process test có thể xác minh request metadata bắt buộc, initial response headers và trailers:

```java
@Test
void metadataContractIsPreservedAcrossRpc() {
    MetadataCaptureInterceptor capture = new MetadataCaptureInterceptor();
    ManagedChannel testChannel = InProcessChannelBuilder
            .forName(serverName)
            .intercept(MetadataUtils.newAttachHeadersInterceptor(requestHeaders))
            .intercept(capture)
            .build();

    CatalogServiceGrpc.CatalogServiceBlockingStub testStub =
            CatalogServiceGrpc.newBlockingStub(testChannel)
                    .withDeadlineAfter(2, TimeUnit.SECONDS);

    Product response = testStub.getProduct(
            GetProductRequest.newBuilder().setProductId("P-100").build());

    assertEquals("P-100", response.getProductId());
    assertEquals("req-123", serverCapture.requestId.get());
    assertEquals("tenant-7", serverCapture.tenantId.get());
    assertEquals("req-123", capture.responseHeaders.get().get(REQUEST_ID));
    assertEquals("catalog-v2", capture.responseHeaders.get().get(SERVER_VERSION));
    assertEquals("ap-southeast", capture.responseTrailers.get().get(SERVICE_REGION));
    testChannel.shutdownNow();
}
```

Đây là khung test minh họa; serverName, requestHeaders, serverCapture và interceptor phía server được tạo trong fixture. requestHeaders chứa REQUEST_ID=req-123 và TENANT_ID=tenant-7. serverCapture là holder test-local ghi nhận hai giá trị mà server interceptor nhận được. Nếu dùng MetadataUtils.newAttachHeadersInterceptor, cần bảo đảm request metadata có đúng key/type. Có thể dùng custom client interceptor ở mục 4 để kiểm tra request metadata được tạo động.

Test riêng trường hợp metadata thiếu hoặc sai:

```java
StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> stubWithoutTenant.getProduct(request));
assertEquals(Status.Code.INVALID_ARGUMENT, error.getStatus().getCode());
```

Ngoài status, xác minh handler nghiệp vụ không được gọi nếu request metadata bắt buộc không hợp lệ. Với Spring integration test, khởi động application context để xác minh interceptor thực sự được đăng ký trên server.

## 9. Security, privacy và compatibility của metadata

Metadata thường đi qua nhiều thành phần trung gian như proxy, gateway, tracing agent và log interceptor. Vì vậy:

- Không log authorization, cookie, token, chữ ký hoặc metadata chứa dữ liệu nhạy cảm.
- Không dùng metadata thay cho cơ chế xác thực; xác minh credential và principal ở security boundary.
- Không tin x-tenant-id nếu chưa kiểm tra tenant thuộc quyền của principal.
- Không đưa thông tin cá nhân hoặc payload lớn vào headers/trailers.
- Dùng allowlist key được ghi log; redact value nhạy cảm.
- Đặt giới hạn kích thước và số lượng value; kiểm tra behavior khi vượt giới hạn.

Metadata key là contract cần versioning như field proto. Đổi key x-request-id thành request-id có thể làm client cũ mất correlation. Khi đổi key, có thể hỗ trợ song song key cũ/mới trong thời gian chuyển tiếp, xác định precedence nếu cả hai cùng xuất hiện và bỏ key cũ sau khi consumer đã nâng cấp.

Không dùng reserved HTTP/2/gRPC protocol headers hoặc key bắt đầu bằng grpc-. Tránh giả định mọi proxy giữ nguyên metadata tùy ý; integration test qua gateway/proxy cần xác minh các key thực sự được forward.

## 10. Checklist metadata contract

- [ ] Request headers, initial response headers và trailers được phân biệt rõ.
- [ ] Mỗi key có tên lowercase, type marshaller và suffix -bin phù hợp.
- [ ] Cardinality đơn trị/đa trị và duplicate behavior được định nghĩa.
- [ ] Metadata bắt buộc được validate trước khi chạy use case.
- [ ] Client interceptor thêm metadata call-scoped, không lưu state request vào field mutable.
- [ ] Tenant/identity metadata được ràng buộc với principal đã xác thực.
- [ ] Response headers được gửi trước message đầu tiên; trailers chỉ gửi khi close.
- [ ] Test capture headers/trailers qua ClientCall.Listener và copy Metadata.
- [ ] Test status khi metadata thiếu/sai và xác minh không có side effect.
- [ ] Không log credential hoặc metadata nhạy cảm.
- [ ] Có giới hạn size/count và test qua gateway/proxy khi có.
- [ ] Đổi metadata key có compatibility/deprecation plan.

**Tự kiểm tra**

**Câu 1.** Metadata khác protobuf request body ở điểm nào?

*Đáp án:* Metadata là thông tin transport đi kèm call và có thể được interceptor đọc trước khi service xử lý message. Protobuf body chứa dữ liệu nghiệp vụ có schema và field compatibility riêng.

**Câu 2.** Khi nào metadata key phải kết thúc bằng -bin?

*Đáp án:* Khi value là binary bytes và dùng BINARY_BYTE_MARSHALLER. Với ASCII string dùng ASCII_STRING_MARSHALLER; không tự base64 bytes trước khi đưa vào binary metadata.

**Câu 3.** Initial response headers và trailers khác nhau thế nào?

*Đáp án:* Initial headers được gửi trước response message đầu tiên; trailers được gửi cùng lúc server đóng RPC với status cuối. Client nhận chúng ở onHeaders và onClose.

**Câu 4.** Vì sao không nên chỉ dùng headers.get(key) cho metadata có thể lặp?

*Đáp án:* Một key có thể có nhiều value. Contract đa trị cần đọc bằng getAll(key) và kiểm tra cardinality/thứ tự; nếu chỉ đơn trị thì phải validate duplicate.

**Câu 5.** Có nên tin tenant ID do client gửi trong metadata không?

*Đáp án:* Không nếu chưa ràng buộc với principal đã xác thực. Metadata chỉ là input từ client; server phải kiểm tra caller có quyền hoạt động trong tenant đó.

Kiểm tra metadata contract bảo vệ những thông tin đi cùng RPC ở cả ba thời điểm: request headers, initial response headers và trailers. Định nghĩa rõ key/type/cardinality, validate tại interceptor, kiểm tra qua generated stub và ClientCall listener, đồng thời bảo vệ credential/tenant context. Nhờ đó client và server Spring gRPC giữ được correlation, security context và semantics của metadata qua các lần nâng cấp.
