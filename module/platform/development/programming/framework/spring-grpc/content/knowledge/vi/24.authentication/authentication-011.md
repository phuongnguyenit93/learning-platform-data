# Kiểm thử request thiếu credential

Trong gRPC, credential thường được gửi qua request metadata, ví dụ key `authorization` chứa Bearer token. Khi client gọi một RPC được bảo vệ mà không gửi credential, server phải từ chối request ở bước authentication và trả **`UNAUTHENTICATED` (16)**. Bài kiểm thử cần xác nhận cả status trả về lẫn việc business handler không được thực thi.

Trong **SPRING_GRPC**, authentication thường được đặt tại server interceptor hoặc cơ chế bảo mật tích hợp của starter. Kiểm thử request thiếu credential giúp phát hiện các lỗi như interceptor chưa được đăng ký, một service vô tình bỏ qua interceptor, hoặc handler vẫn chạy khi không có principal. Bài này tập trung vào request không có credential; credential sai, hết hạn và caller thiếu quyền là những trường hợp riêng cần test bổ sung để bảo đảm ranh giới authentication/authorization rõ ràng.

## 1. Kỳ vọng bảo mật khi thiếu credential

Một RPC được bảo vệ phải có quyết định authentication trước khi business logic chạy:

1. Client gửi request metadata.
2. Server interceptor đọc credential từ metadata.
3. Nếu credential không tồn tại hoặc rỗng, interceptor kết thúc call với `UNAUTHENTICATED`.
4. Server không gọi tiếp interceptor/application handler phía sau.
5. Client nhận status và có thể yêu cầu đăng nhập hoặc cấp credential theo flow của ứng dụng.

Với Bearer token, metadata thường có dạng:

```text
authorization: Bearer <access-token>
```

Tên metadata key được chuẩn hóa thành chữ thường. Giá trị token là dữ liệu nhạy cảm; không ghi token vào log, assertion message, exception description hoặc test report.

## 2. Phân biệt thiếu credential với lỗi bảo mật khác

Không nên gom mọi lỗi bảo mật vào một status:

| Tình huống | Status thường phù hợp | Ý nghĩa |
| --- | --- | --- |
| Không gửi metadata `authorization` | `UNAUTHENTICATED` | Server không nhận được danh tính để xác minh |
| Header có giá trị rỗng hoặc không có Bearer credential theo contract | `UNAUTHENTICATED` | Không có credential dùng được |
| Token sai chữ ký, malformed hoặc hết hạn | `UNAUTHENTICATED` | Credential được gửi nhưng không xác thực được |
| Token hợp lệ nhưng thiếu scope/role | `PERMISSION_DENIED` | Identity đã xác minh, caller không có quyền |
| Token hợp lệ và đủ quyền | `OK` nếu operation thành công | Authentication và authorization đều đạt |

Test thiếu credential phải chứng minh đúng status `UNAUTHENTICATED`. Nếu test chỉ kiểm tra một exception bất kỳ hoặc chỉ xác nhận response không có dữ liệu, nó chưa chứng minh server thực hiện authentication đúng.

## 3. Đặt kiểm tra credential trước business handler

Trong gRPC Java, `ServerInterceptor` có thể đọc metadata trước khi chuyển call đến handler. Nếu thiếu credential, interceptor gọi `close` và không gọi `next.startCall`.

Ví dụ interceptor tối giản:

```java
public final class RequireBearerCredentialInterceptor
        implements ServerInterceptor {

    private static final Metadata.Key<String> AUTHORIZATION =
        Metadata.Key.of(
            "authorization",
            Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String authorization = headers.get(AUTHORIZATION);
        if (authorization == null || authorization.isBlank()) {
            call.close(
                Status.UNAUTHENTICATED
                    .withDescription("Thiếu credential xác thực"),
                new Metadata());
            return new ServerCall.Listener<>() {};
        }

        return next.startCall(call, headers);
    }
}
```

Đây là ví dụ kiểm tra sự hiện diện của header để minh họa test. Trong ứng dụng thực tế, chỉ kiểm tra header khác rỗng là chưa đủ: interceptor hoặc authentication provider phải xác minh định dạng Bearer, chữ ký, issuer, audience, thời hạn và các claim cần thiết. Không chuyển chuỗi token chưa xác minh thành principal.

Điểm quan trọng đối với bài test là nhánh thiếu credential đóng call trước `next.startCall`. Nếu interceptor gọi `next.startCall` rồi mới xác thực, business handler hoặc interceptor phía sau có thể đã chạy.

## 4. Tạo service giả để phát hiện handler có bị gọi hay không

Chỉ assert status là chưa đủ để chứng minh request bị chặn trước business logic. Một service giả có thể dùng `AtomicBoolean` để ghi nhận handler có được gọi hay không:

```java
public final class GreetingService
        extends GreeterGrpc.GreeterImplBase {

    private final AtomicBoolean handlerInvoked;

    public GreetingService(AtomicBoolean handlerInvoked) {
        this.handlerInvoked = handlerInvoked;
    }

    @Override
    public void sayHello(
            HelloRequest request,
            StreamObserver<HelloReply> responseObserver) {
        handlerInvoked.set(true);
        responseObserver.onNext(
            HelloReply.newBuilder()
                .setMessage("Hello " + request.getName())
                .build());
        responseObserver.onCompleted();
    }
}
```

Các lớp `GreeterGrpc`, `HelloRequest` và `HelloReply` là ví dụ được sinh từ Protobuf service. Trong module thực tế, thay chúng bằng generated service và request/response của ứng dụng. Service giả không cần truy cập database hoặc dependency bên ngoài.

## 5. In-process integration test với JUnit 5

In-process transport cho phép dựng gRPC server và client trong cùng JVM. Test vẫn đi qua gRPC dispatch và interceptor, nhưng không cần mở TCP port hoặc phụ thuộc vào một server đang chạy bên ngoài.

Ví dụ JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.ServerInterceptors;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class MissingCredentialGrpcTest {

    private Server server;
    private ManagedChannel channel;
    private GreeterGrpc.GreeterBlockingStub stub;
    private AtomicBoolean handlerInvoked;

    @BeforeEach
    void setUp() throws IOException {
        handlerInvoked = new AtomicBoolean(false);
        String serverName = InProcessServerBuilder.generateName();

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(ServerInterceptors.intercept(
                new GreetingService(handlerInvoked),
                new RequireBearerCredentialInterceptor()))
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();

        stub = GreeterGrpc.newBlockingStub(channel);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow();
            channel.awaitTermination(5, TimeUnit.SECONDS);
        }
        if (server != null) {
            server.shutdownNow();
            server.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    @Test
    void requestWithoutAuthorizationMetadataIsRejected() {
        HelloRequest request = HelloRequest.newBuilder()
            .setName("Lan")
            .build();

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.sayHello(request));

        assertEquals(
            Status.Code.UNAUTHENTICATED,
            error.getStatus().getCode());
        assertFalse(handlerInvoked.get());
    }
}
```

Stub trong test không được gắn metadata interceptor hoặc `CallCredentials`, vì mục tiêu là gửi request không có credential. Nếu test fixture dùng chung một channel đã cấu hình credential mặc định, test có thể vô tình gửi token và không còn kiểm tra đúng tình huống thiếu credential.

### 5.1. Test đang chứng minh điều gì?

Hai assertion quan trọng:

- `Status.Code.UNAUTHENTICATED`: server trả đúng status cho request không có credential.
- `handlerInvoked == false`: interceptor đã chặn request trước khi business handler chạy.

Nếu status đúng nhưng handler vẫn được gọi, có thể implementation đã thực hiện side effect trước khi từ chối hoặc test đang quan sát sai handler. Với operation ghi dữ liệu, cần bổ sung assertion rằng repository/mock downstream không bị gọi và không có record/event nào được tạo.

## 6. Đăng ký interceptor trong Spring gRPC

Test in-process ở trên đăng ký interceptor trực tiếp với service. Ứng dụng Spring thường đăng ký interceptor qua annotation, bean hoặc cơ chế cấu hình do starter cung cấp. Tên annotation và thứ tự interceptor phụ thuộc thư viện Spring gRPC cụ thể.

Khi kiểm thử Spring application, cần xác minh:

- Interceptor được Spring phát hiện và gắn vào đúng gRPC server.
- Mọi service cần bảo vệ đều đi qua authentication interceptor.
- Không có endpoint nhạy cảm nào được đăng ký song song mà bỏ qua lớp bảo vệ.
- Authentication chạy trước interceptor/application component cần principal.
- Request thiếu credential bị chặn trước khi handler thực thi.

Một unit test cho interceptor không chứng minh Spring đã đăng ký interceptor. Vì vậy nên có ít nhất một integration test khởi động application context và gọi RPC qua channel mà ứng dụng thực sự cung cấp.

## 7. Integration test qua Spring application context

Một integration test ở cấp ứng dụng có thể dùng `@SpringBootTest` để khởi động server, lấy port/channel theo cấu hình test rồi gọi RPC không có metadata. Cấu trúc minh họa:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ProtectedGrpcApplicationTest {

    @Test
    void protectedMethodRejectsCallWithoutCredential(
            @Autowired GreeterGrpc.GreeterBlockingStub unauthenticatedStub) {

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> unauthenticatedStub.sayHello(
                HelloRequest.newBuilder().setName("Lan").build()));

        assertEquals(
            Status.Code.UNAUTHENTICATED,
            error.getStatus().getCode());
    }
}
```

Đây là cấu trúc minh họa, không phải một bean stub có sẵn trong mọi Spring gRPC starter. Test fixture của dự án cần tạo channel/stub tới server test và inject hoặc cung cấp stub đó. Điều cần giữ là channel trong test không tự đính kèm credential.

Nếu ứng dụng dùng random port, test nên lấy port được server test công bố thay vì hard-code port dùng chung. Đóng channel/server trong lifecycle để tránh rò rỉ thread và port giữa các test.

## 8. Test matrix cho request thiếu hoặc không dùng được credential

Một test case tập trung vào header vắng mặt nên nằm trong một nhóm negative authentication tests:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Không gửi metadata `authorization` | `UNAUTHENTICATED`; handler không chạy |
| Gửi header rỗng | `UNAUTHENTICATED`; handler không chạy |
| Gửi giá trị không theo Bearer scheme | `UNAUTHENTICATED`; handler không chạy |
| Bearer token malformed | `UNAUTHENTICATED`; handler không chạy |
| Bearer token sai chữ ký/issuer/audience | `UNAUTHENTICATED`; handler không chạy |
| Token hết hạn | `UNAUTHENTICATED`; handler không chạy |
| Token hợp lệ nhưng thiếu scope | `PERMISSION_DENIED` |
| Token hợp lệ và đủ quyền | Handler chạy; status theo kết quả nghiệp vụ |

Không gộp tất cả test này vào một test duy nhất. Khi mỗi nguyên nhân có test riêng, failure sẽ chỉ ra chính xác lớp xác thực hoặc phân quyền đang sai.

## 9. Kiểm tra request không gửi metadata

Trong gRPC Java, metadata được gắn vào call bằng interceptor hoặc `CallCredentials`. Để chắc chắn test không gửi credential:

- Tạo stub từ channel không có client-side metadata interceptor.
- Không dùng `CallCredentials` trong test thiếu credential.
- Không tái sử dụng stub đã được cấu hình Bearer token từ test khác.
- Nếu dùng shared test fixture, tạo channel riêng cho nhóm unauthenticated.
- Có thể ghi nhận phía server rằng authorization key không tồn tại, nhưng không log giá trị credential.

Một test có thể kiểm tra header rỗng riêng, nhưng không nên xem header rỗng là tương đương mọi malformed credential. Contract cần quy định parser xử lý scheme, whitespace và nhiều giá trị metadata thế nào.

## 10. Assertion status và thông tin lỗi

Client blocking stub thường ném `StatusRuntimeException` khi RPC kết thúc với status không phải `OK`. Test nên assert mã status trước:

```java
StatusRuntimeException error = assertThrows(
    StatusRuntimeException.class,
    () -> stub.sayHello(request));

assertEquals(Status.Code.UNAUTHENTICATED, error.getStatus().getCode());
```

Không nên chỉ assert message như “Thiếu credential xác thực”, vì message có thể thay đổi ngôn ngữ hoặc cách diễn đạt mà không làm thay đổi contract. Nếu API có rich error details, có thể assert detail type/reason ổn định, nhưng không nên yêu cầu server gửi token, claim nhạy cảm hoặc thông tin xác minh nội bộ.

Thông báo trả client nên ngắn và tổng quát, ví dụ “Yêu cầu cần credential hợp lệ”. Server log có thể ghi method, reason code, trace ID và kết quả authentication mà không ghi raw token.

## 11. Không để test tạo lỗ hổng bảo mật

Test fixture cần tuân thủ cùng nguyên tắc bảo vệ credential như production:

- Không commit access token thật, private key hoặc secret của môi trường.
- Dùng token giả hoặc signing key chỉ dành cho test.
- Không in metadata đầy đủ khi assertion thất bại.
- Không đưa token vào tên test, test display name hoặc CI artifact.
- Không tắt authentication toàn cục chỉ để test business handler thuận tiện.
- Nếu có test bypass interceptor, giới hạn bypass trong fixture riêng và không dùng cấu hình đó để chạy production.

Test thiếu credential không cần biết secret hợp lệ là gì. Nó chỉ cần gửi một request không có authorization metadata và xác minh server từ chối đúng cách.

## 12. TLS và phạm vi của in-process test

In-process transport kiểm tra gRPC dispatch và interceptor nhưng không kiểm tra TLS handshake, certificate validation hoặc mTLS. Vì vậy:

- Dùng in-process test để kiểm tra status và thứ tự interceptor.
- Dùng integration test với transport TLS để xác minh server certificate và client trust configuration.
- Nếu hệ thống yêu cầu mTLS, test riêng trường hợp thiếu client certificate ở transport handshake.
- Phân biệt client certificate ở tầng TLS với Bearer credential ở application metadata.

TLS bảo vệ kênh và xác minh server (hoặc client trong mTLS); nó không tự động thay thế mọi quy tắc authorization ở application layer. Một request có TLS hợp lệ vẫn có thể thiếu Bearer token theo contract của RPC.

## 13. Những lỗi kiểm thử thường gặp

| Sai lầm | Hậu quả | Cách làm tốt hơn |
| --- | --- | --- |
| Chỉ assert exception được ném | Không chứng minh đúng status | Assert `UNAUTHENTICATED` |
| Không kiểm tra handler | Request có thể đã chạy business logic | Dùng spy/flag và assert handler không được gọi |
| Stub tự đính kèm token mặc định | Test không còn là request thiếu credential | Dùng channel/stub không có metadata credentials |
| Chỉ unit test interceptor | Bỏ sót lỗi Spring registration | Thêm integration test qua application context |
| Dùng `PERMISSION_DENIED` cho credential vắng mặt | Trộn authentication với authorization | Trả `UNAUTHENTICATED` |
| Assert grpc-message chính xác | Test dễ vỡ khi message đổi | Assert status code và structured detail |
| Log toàn bộ request metadata | Có thể lộ token | Chỉ log key/reason an toàn, redact credential |
| Dùng in-process test để tuyên bố TLS đã đúng | Không hề kiểm tra handshake/certificate | Có test transport TLS/mTLS riêng |

## 14. Checklist hoàn tất test request thiếu credential

Trước khi coi authentication test đạt, hãy xác nhận:

1. **Đúng RPC được bảo vệ:** test gọi method cần authentication.
2. **Không có credential thật:** stub không gắn metadata interceptor hoặc `CallCredentials`.
3. **Server interceptor được đăng ký:** test đi qua đúng pipeline đang dùng.
4. **Status chính xác:** response là `UNAUTHENTICATED` (16).
5. **Handler không chạy:** không có business side effect hoặc downstream invocation.
6. **Authentication tách authorization:** token hợp lệ nhưng thiếu quyền được test riêng bằng `PERMISSION_DENIED`.
7. **Message an toàn:** không lộ token, claim, key hoặc chi tiết xác minh.
8. **Spring wiring được kiểm tra:** có integration test qua application context nếu ứng dụng đăng ký interceptor bằng Spring.
9. **Transport security được kiểm tra riêng:** in-process test không thay thế TLS/mTLS test.
10. **Test độc lập:** không phụ thuộc thứ tự chạy hoặc channel có credential từ test khác.

## 15. Ghi nhớ

Request gọi RPC được bảo vệ mà không gửi credential phải bị từ chối bằng `UNAUTHENTICATED` (16), trước khi business handler chạy. Một test tốt cần chứng minh đồng thời hai điều: status trả về chính xác và handler không được gọi. In-process gRPC test giúp xác minh dispatch/interceptor; integration test qua Spring application context xác minh cấu hình đăng ký thực tế. TLS/mTLS cần test riêng vì in-process transport không thực hiện handshake.

Trong Spring gRPC, hãy đặt authentication ở interceptor hoặc security integration được đăng ký nhất quán cho các service cần bảo vệ. Không nhầm credential thiếu/sai với caller đã xác thực nhưng thiếu quyền (`PERMISSION_DENIED`). Giữ token ngoài log/test output, assert status code thay vì phụ thuộc message và kiểm tra side effect bằng spy hoặc repository assertion. Những kiểm tra này bảo đảm request không xác thực không thể đi vào business logic.

### Tài liệu tham khảo

- [gRPC – Authentication](https://grpc.io/docs/guides/auth/)
- [gRPC Java – Interceptors](https://grpc.io/docs/languages/java/interceptors/)
- [gRPC – Status codes](https://grpc.io/docs/guides/status-codes/)
- [JUnit 5 – User guide](https://junit.org/junit5/docs/current/user-guide/)
- [Spring Security – Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/index.html)
