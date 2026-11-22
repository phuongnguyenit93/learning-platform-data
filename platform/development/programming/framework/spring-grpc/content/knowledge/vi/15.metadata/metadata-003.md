# Authorization metadata

Trong hệ thống microservice sử dụng **Spring gRPC**, client thường phải chứng minh danh tính hoặc quyền truy cập trước khi server xử lý lời gọi. Dữ liệu như access token được truyền qua **request metadata**, phổ biến nhất là header `authorization` mang giá trị `Bearer <access-token>`. Cơ chế này dùng hạ tầng metadata của `grpc-java`, không cần thêm token vào mọi message Protocol Buffers.

Tên “authorization metadata” dễ gây nhầm lẫn: **metadata chỉ chuyên chở thông tin xác thực hoặc ủy quyền**. Bản thân sự hiện diện của một header không chứng minh người gọi có quyền. Server phải xác thực thông tin trước, rồi kiểm tra quyền đối với phương thức và tài nguyên cụ thể.

Sau bài học, bạn có thể:

- Phân biệt authentication (xác thực) và authorization (phân quyền) trong một lời gọi gRPC.
- Biết cách dùng ASCII metadata `authorization` cho bearer token, và trường hợp nào cần cơ chế credential khác.
- Gắn thông tin xác thực ở client bằng `CallCredentials` hoặc interceptor.
- Kiểm tra metadata trong server interceptor, chuyển danh tính đã xác thực qua `io.grpc.Context` và thực hiện phân quyền tại đúng nơi.
- Trả về `UNAUTHENTICATED` hoặc `PERMISSION_DENIED` đúng tình huống; kiểm thử và bảo vệ token khi dùng Spring gRPC, TLS, streaming và lời gọi liên dịch vụ.

## 1. Authentication và authorization trong gRPC

Hai bước có mục đích khác nhau:

| Bước | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Authentication** (xác thực) | Ai đang gọi? Có bằng chứng danh tính hợp lệ không? | Xác minh chữ ký, thời hạn, issuer, audience của JWT; hoặc introspection token mờ (opaque token) |
| **Authorization** (phân quyền) | Danh tính đã được xác thực có được thực hiện thao tác này trên tài nguyên này không? | Người dùng A chỉ được đọc đơn hàng của mình; dịch vụ kho mới được cập nhật tồn |

Trong kiến trúc dùng access token:

```text
Client                          gRPC Server                         Service
  |                                  |                                  |
  | -- request metadata -----------> |                                  |
  |    authorization: Bearer ...     |                                  |
  |    x-request-id: req-42          |                                  |
  |                                  |-- Xác minh token --------------> |
  |                                  |   (server interceptor)           |
  |                                  |-- Gắn danh tính đã xác thực ----> |
  |                                  |                                  |-- Kiểm tra quyền
  |                                  |                                  |   với phương thức/tài nguyên
  | <----------- response/status --- | <--------------------------------|
```

Luồng thành công:

1. Client lấy access token từ cơ chế đăng nhập hoặc định danh dịch vụ đã được thiết lập.
2. Client đưa token vào `authorization` khi bắt đầu RPC.
3. Server interceptor nhận request metadata, xác minh token và tạo ngữ cảnh danh tính đáng tin cậy.
4. Service (hoặc policy layer) kiểm tra quyền sử dụng phương thức và tài nguyên.
5. Server trả dữ liệu nếu được phép; nếu thất bại, trả gRPC status phù hợp.

**Ví dụ:** Token của người dùng `user-17` còn hiệu lực và có quyền `orders:read`. Token được xác thực thành công, nhưng nếu `user-17` yêu cầu đơn hàng của `user-22`, server vẫn phải từ chối nếu chính sách yêu cầu chủ sở hữu. Một token hợp lệ không đồng nghĩa mọi thao tác đều hợp lệ.

## 2. Header `authorization` là metadata kiểu gì?

`authorization` là **ASCII metadata key**: giá trị của nó được biểu diễn bằng chuỗi, ví dụ:

```text
authorization: Bearer eyJhbGciOi...
```

Trong `grpc-java`:

```java
import io.grpc.Metadata;

Metadata.Key<String> AUTHORIZATION =
    Metadata.Key.of(
        "authorization",
        Metadata.ASCII_STRING_MARSHALLER
    );

Metadata headers = new Metadata();
headers.put(AUTHORIZATION, "Bearer " + accessToken);
```

Ở đây `accessToken` là giá trị **đã được client lấy theo luồng bảo mật của ứng dụng**. Không đưa token thật vào mã nguồn, file mẫu, git, URL, query string hay log. Chuỗi trên chỉ minh họa cách ghép header.

Một số quy tắc quan trọng:

| Quy tắc | Ý nghĩa thực tế |
| --- | --- |
| Key là `authorization`, viết chữ thường | Tương thích quy tắc đặt tên HTTP/2 header |
| Value mang `Bearer ` rồi đến token | Server cần parse và xác minh theo cơ chế đã thỏa thuận |
| Không thêm hậu tố `-bin` cho bearer token | Bearer token thông thường là chuỗi ASCII, không phải raw binary metadata |
| Không tự đặt key bắt đầu bằng `grpc-` | Tiền tố này dành cho metadata của giao thức |
| Header thuộc **RPC**, không phải message Protobuf | Streaming RPC không yêu cầu lặp token trên từng message |
| Header do client gửi không đáng tin cậy mặc định | Server phải kiểm tra giá trị và danh tính trước khi cấp quyền |

Bearer là một *authentication scheme*. Server nên kiểm tra scheme không phân biệt hoa/thường theo quy tắc HTTP authentication, đồng thời bác bỏ nội dung sai định dạng hoặc rỗng. Ứng dụng cần có chính sách rõ ràng nếu nhận nhiều value `authorization` cho cùng một RPC; tránh tùy tiện chọn một trong số đó.

### Khi nào cần binary metadata?

Một số hệ thống truyền dữ liệu chứng minh danh tính dạng byte tùy chỉnh, chẳng hạn bằng chứng nhị phân ngắn đã được hai đầu định nghĩa. Khi đó, key của nó **phải** kết thúc bằng `-bin` và có thể sử dụng `Metadata.BINARY_BYTE_MARSHALLER`. Nhưng việc đổi từ ASCII sang binary **không tự tăng độ bảo mật**: thư viện vẫn vận chuyển metadata qua header/trailer, và mã hóa Base64 trên đường truyền chỉ là biểu diễn byte.

Với bearer access token theo quy ước HTTP, dùng `authorization` kiểu ASCII. Đừng tự mã hóa token thành Base64 rồi gửi dưới key `-bin` chỉ để “an toàn hơn”.

## 3. Metadata và cơ chế bảo mật ở tầng vận chuyển

Access token kiểu bearer có đặc điểm: **ai sở hữu token hợp lệ có thể thử sử dụng quyền mà token đại diện**. Bởi vậy việc bảo vệ đường truyền và môi trường xử lý là thiết yếu.

- **TLS:** dùng kênh TLS cho RPC qua mạng. TLS bảo vệ metadata và message trên các chặng kết nối mà TLS bao phủ; trong mô hình có proxy kết thúc TLS, cần xem xét tiếp đường truyền từ proxy đến service.
- **mTLS:** xác thực hai chiều danh tính các đầu kết nối, thường dùng giữa các service. mTLS và token người dùng giải quyết những câu hỏi khác nhau và có thể phối hợp; không mặc định mTLS chứng minh người dùng cuối có quyền đọc đơn hàng.
- **Token audience và phạm vi:** chỉ chấp nhận token được phát hành cho đúng API/dịch vụ, còn hiệu lực và có quyền phù hợp.
- **Log và giám sát:** không ghi `authorization` hoặc token vào log, trace attribute, thông điệp lỗi hay metric label. Có thể ghi request ID hoặc định danh đã được chuẩn hóa và cho phép.
- **Proxy/gateway:** xác định rõ thành phần nào xác thực, thành phần nào có thể thêm hoặc loại bỏ header, và liệu server phía sau còn phải xác minh dữ liệu hay nhận một định danh đã chứng thực từ proxy tin cậy.

Metadata không phải một cơ chế mã hóa đầu cuối độc lập. Đừng xem “có `authorization`” hoặc “token nằm trong metadata nhị phân” là đủ để bảo vệ lời gọi.

## 4. Client: gắn token bằng interceptor

Để minh họa thao tác `Metadata` đơn giản, client có thể gắn một bộ header vào stub bằng `MetadataUtils.newAttachHeadersInterceptor(...)`:

```java
import io.grpc.Channel;
import io.grpc.Metadata;
import io.grpc.stub.MetadataUtils;
import java.util.concurrent.TimeUnit;

// Truyền token từ cơ chế quản lý credentials của ứng dụng.
String token = tokenProvider.getAccessToken();

Metadata.Key<String> authorizationKey =
    Metadata.Key.of("authorization", Metadata.ASCII_STRING_MARSHALLER);

Metadata fixedHeaders = new Metadata();
fixedHeaders.put(authorizationKey, "Bearer " + token);

OrderServiceGrpc.OrderServiceBlockingStub stub =
    OrderServiceGrpc.newBlockingStub(channel)
        .withInterceptors(
            MetadataUtils.newAttachHeadersInterceptor(fixedHeaders))
        .withDeadlineAfter(3, TimeUnit.SECONDS);

// stub.getOrder(...) sẽ gửi authorization trong request headers.
```

`OrderServiceGrpc`, `channel` và `tokenProvider` giả định đã tồn tại trong ứng dụng; tên dịch vụ và phương thức RPC tùy hợp đồng `.proto`. `withDeadlineAfter(...)` thiết lập deadline bằng API gRPC, không tự thêm `grpc-timeout`.

Cách gắn header cố định hữu ích cho ví dụ tối thiểu, kiểm thử hoặc token có vòng đời được quản lý tại thời điểm tạo stub. **Hạn chế:** nếu token hết hạn mà stub/interceptor vẫn sử dụng value cũ, RPC tiếp theo có thể bị từ chối. Cần chuẩn bị cơ chế cập nhật hoặc tạo credentials theo từng lần gọi cho môi trường thực tế.

## 5. Client: dùng `CallCredentials` khi token thay đổi

`io.grpc.CallCredentials` cho phép client cung cấp metadata xác thực vào thời điểm gRPC áp dụng credentials cho call. Nó phù hợp khi token được cấp động hoặc có khả năng xoay vòng. Đây là một cách tách việc lấy token ra khỏi logic xử lý message của stub.

Ví dụ một lớp credentials nhận `Supplier<String>` để lấy token hiện hành. Việc lấy token có thể cần I/O; `appExecutor` được gRPC cung cấp cho công việc liên quan credentials, tránh chặn luồng vận chuyển:

```java
import io.grpc.CallCredentials;
import io.grpc.Metadata;
import io.grpc.Status;
import java.util.concurrent.Executor;
import java.util.function.Supplier;

public final class BearerCallCredentials extends CallCredentials {
    private static final Metadata.Key<String> AUTHORIZATION =
        Metadata.Key.of("authorization", Metadata.ASCII_STRING_MARSHALLER);

    private final Supplier<String> tokenSupplier;

    public BearerCallCredentials(Supplier<String> tokenSupplier) {
        this.tokenSupplier = tokenSupplier;
    }

    @Override
    public void applyRequestMetadata(
            RequestInfo requestInfo,
            Executor appExecutor,
            MetadataApplier applier) {
        try {
            appExecutor.execute(() -> {
                try {
                    String token = tokenSupplier.get();
                    if (token == null || token.isBlank()) {
                        applier.fail(
                            Status.UNAUTHENTICATED.withDescription(
                                "Access token unavailable"));
                        return;
                    }

                    Metadata metadata = new Metadata();
                    metadata.put(AUTHORIZATION, "Bearer " + token);
                    applier.apply(metadata);
                } catch (Exception ex) {
                    // Không đính kèm token hoặc nội dung bí mật vào lỗi.
                    applier.fail(
                        Status.UNAUTHENTICATED.withDescription(
                            "Unable to obtain access token"));
                }
            });
        } catch (RuntimeException ex) {
            applier.fail(
                Status.UNAUTHENTICATED.withDescription(
                    "Credential execution unavailable"));
        }
    }

    @Override
    public void thisUsesUnstableApi() {
        // Phương thức tương thích với các phiên bản grpc-java yêu cầu nó.
    }
}
```

Gắn vào stub bằng `withCallCredentials(...)`:

```java
OrderServiceGrpc.OrderServiceBlockingStub authenticatedStub =
    OrderServiceGrpc.newBlockingStub(channel)
        .withCallCredentials(
            new BearerCallCredentials(tokenProvider::getAccessToken));
```

**Giới hạn của ví dụ:** `tokenProvider` đại diện cho thành phần cấp/làm mới token do ứng dụng tự triển khai. Trong thực tế, nó cần quản lý hết hạn, đồng bộ làm mới và tránh làm nghẽn khi nhiều RPC bắt đầu cùng lúc. Đừng tạo một request đăng nhập mới cho mọi lần gọi chỉ vì dùng `CallCredentials`. Nếu môi trường dùng thư viện credentials chính thức của hệ thống định danh, ưu tiên adapter có sẵn và kiểm tra tương thích với phiên bản `grpc-java`.

Với Spring gRPC, stub/channel thường được tạo hoặc cấu hình thông qua Spring. Cách gắn credentials vào stub vẫn là API của `grpc-java`; hãy áp dụng tại điểm khởi tạo/cấu hình client tương ứng với phiên bản Spring gRPC đang sử dụng. Nếu credentials phụ thuộc danh tính từng người dùng, tránh gắn token người A vào singleton stub rồi dùng chung cho người B.

## 6. Server: xác thực token trong `ServerInterceptor`

Ở server, một `ServerInterceptor` có thể đọc `authorization` trước khi thực thi dịch vụ. Ví dụ sau xử lý ba vấn đề thường gặp: thiếu header, nhiều header cùng tên và token không hợp lệ. Để tránh phụ thuộc nhà cung cấp JWT cụ thể, logic xác minh thật được tách qua `TokenVerifier`.

```java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.Iterator;

public final class AccessTokenServerInterceptor implements ServerInterceptor {
    private static final Metadata.Key<String> AUTHORIZATION =
        Metadata.Key.of("authorization", Metadata.ASCII_STRING_MARSHALLER);

    public static final Context.Key<String> SUBJECT =
        Context.key("authenticated-subject");

    private final TokenVerifier verifier;

    public AccessTokenServerInterceptor(TokenVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        Iterable<String> values = headers.getAll(AUTHORIZATION);
        if (values == null) {
            return reject(call);
        }
        Iterator<String> it = values.iterator();
        if (!it.hasNext()) {
            return reject(call);
        }
        String value = it.next();
        if (it.hasNext()) { // Không chấp nhận nhiều credential cạnh tranh.
            return reject(call);
        }

        if (value == null || !value.regionMatches(
                true, 0, "Bearer ", 0, 7)) {
            return reject(call);
        }
        String token = value.substring(7);
        if (token.isBlank() || token.length() > 4096) {
            return reject(call);
        }

        try {
            String subject = verifier.verify(token);
            if (subject == null || subject.isBlank()) {
                return reject(call);
            }

            Context authenticatedContext =
                Context.current().withValue(SUBJECT, subject);
            return Contexts.interceptCall(
                authenticatedContext, call, headers, next);
        } catch (InvalidTokenException ex) {
            return reject(call);
        }
    }

    private static <ReqT, RespT> ServerCall.Listener<ReqT> reject(
            ServerCall<ReqT, RespT> call) {
        call.close(
            Status.UNAUTHENTICATED.withDescription(
                "Missing or invalid credentials"),
            new Metadata());
        return new ServerCall.Listener<ReqT>() {};
    }

    public interface TokenVerifier {
        String verify(String token) throws InvalidTokenException;
    }

    public static final class InvalidTokenException extends Exception {
        public InvalidTokenException(String message) {
            super(message);
        }
    }
}
```

Trong ví dụ này:

- `AUTHORIZATION` có kiểu `String` nên dùng ASCII marshaller.
- `getAll` giúp phát hiện header lặp, thay vì chỉ đọc giá trị cuối bằng `get`.
- `TokenVerifier` phải xác thực token bằng thư viện hoặc thành phần bảo mật đáng tin cậy. Không so sánh token với chuỗi cố định trong ứng dụng thực tế.
- `Contexts.interceptCall(...)` chuyển `subject` đã xác thực vào `io.grpc.Context` của lời gọi để xử lý tiếp.
- Mã `4096` là **giới hạn ứng dụng minh họa**, không phải giới hạn cố định của gRPC.
- Thông điệp lỗi trả cho client được giữ chung chung, không tiết lộ token, danh tính tìm thấy, chi tiết chữ ký hay nguyên nhân xác thực nội bộ.

### `TokenVerifier` phải kiểm tra những gì?

Với **JWT**, verifier thường cần xác minh chữ ký bằng khóa được tin cậy, thuật toán được cho phép, `issuer`, `audience`, `exp`/`nbf` và các điều kiện khác theo chính sách. Không chỉ Base64-decode payload JWT rồi tin vào các claim. Khóa xác minh và việc đổi khóa phải có quy trình an toàn. Với **opaque token**, cần phương án introspection hoặc truy vấn trạng thái token với hệ thống phát hành được tin cậy, kèm quản lý timeout và lỗi mạng.

Đối với sự cố hạ tầng xác minh (ví dụ không liên lạc được introspection service), ứng dụng cần chính sách **fail closed** và mã lỗi phù hợp cho lỗi phụ thuộc, thường như `UNAVAILABLE`; không mặc định mọi sự cố backend là token giả mạo. Ví dụ interceptor ở trên chỉ minh họa đường đi của token bị xác định là không hợp lệ, còn chính sách xử lý lỗi hạ tầng phải được bổ sung theo môi trường.

## 7. Chuyển danh tính qua `Context` và phân quyền

Khi xác thực thành công, server biết được `subject`. Nhưng **quyền đối với tài nguyên** còn phụ thuộc phương thức, role/scope, tenant và dữ liệu cụ thể.

Trong implementation của RPC, có thể đọc:

```java
String subject = AccessTokenServerInterceptor.SUBJECT.get();
```

Sau đó policy layer kiểm tra, ví dụ logic minh họa:

```java
// Đoạn minh họa bên trong getOrder(request, responseObserver).
String subject = AccessTokenServerInterceptor.SUBJECT.get();
if (subject == null) {
    responseObserver.onError(
        Status.UNAUTHENTICATED
            .withDescription("Authentication required")
            .asRuntimeException());
    return;
}

if (!orderAccessPolicy.canRead(subject, request.getOrderId())) {
    responseObserver.onError(
        Status.PERMISSION_DENIED
            .withDescription("Access denied")
            .asRuntimeException());
    return;
}

// Đã qua xác thực và phân quyền: tiếp tục lấy dữ liệu và onNext/onCompleted.
```

`orderAccessPolicy` là một thành phần phân quyền của ứng dụng, cần được hiện thực và kiểm thử riêng. Chính sách có thể kết hợp scope, vai trò và **quyền sở hữu tài nguyên**. Quyền `orders:read` không tự động cho phép xem tất cả đơn hàng. Không dùng `x-user-id`, `x-role` hoặc `x-tenant-id` do client tự khai làm nguồn quyền đáng tin cậy; nếu các giá trị đó được sử dụng, phải có một thành phần tin cậy chứng thực và ánh xạ chúng sang principal trước.

`io.grpc.Context` giúp gắn ngữ cảnh theo lời gọi. Nếu code tự chuyển công việc sang executor/luồng khác, cần truyền context qua cơ chế của gRPC; nếu không, `SUBJECT.get()` có thể không còn giá trị mong đợi. Trong ứng dụng có Spring Security, `Context` của gRPC và `SecurityContextHolder` là hai cơ chế khác nhau. Chỉ sử dụng annotation hoặc policy theo Spring Security khi đã có tích hợp chuyển danh tính và context phù hợp; không mặc định một interceptor tự động kích hoạt toàn bộ Spring method security.

## 8. Phân biệt `UNAUTHENTICATED` và `PERMISSION_DENIED`

gRPC sử dụng `io.grpc.Status` để diễn đạt kết quả; thư viện vận chuyển status trong trailers khi kết thúc RPC. Hai mã liên quan quyền truy cập dễ bị dùng sai:

| Tình huống | Trạng thái gRPC gợi ý | Lý do |
| --- | --- | --- |
| Không gửi token nhưng phương thức yêu cầu xác thực | `UNAUTHENTICATED` | Chưa có bằng chứng danh tính |
| Token hết hạn, sai chữ ký, sai audience | `UNAUTHENTICATED` | Không xác thực được thông tin đăng nhập |
| Gửi hai header `authorization` trái chính sách | `UNAUTHENTICATED` | Credentials không được chấp nhận |
| Danh tính hợp lệ nhưng thiếu scope để ghi dữ liệu | `PERMISSION_DENIED` | Đã biết ai gọi, nhưng không có quyền |
| Người dùng hợp lệ truy cập tài nguyên không thuộc quyền | `PERMISSION_DENIED` hoặc `NOT_FOUND` theo chính sách che giấu tài nguyên | Cần chọn nhất quán để không làm lộ sự tồn tại của dữ liệu |
| Hệ thống xác minh token phụ thuộc dịch vụ khác đang ngừng hoạt động | `UNAVAILABLE` hoặc status vận hành phù hợp | Lỗi hạ tầng khác với token đã bị chứng minh không hợp lệ |

Trong một số API, server có thể trả `NOT_FOUND` thay vì `PERMISSION_DENIED` để không tiết lộ sự tồn tại của tài nguyên. Đây là một quyết định về bảo mật và trải nghiệm API, phải nhất quán với chính sách truy cập của hệ thống.

Không cố sửa `grpc-status` bằng `Metadata.put`. Hãy kết thúc call bằng `Status` hoặc `StatusRuntimeException`. Lỗi gửi về client nên tránh kèm thông tin nhạy cảm, kể cả trong custom response trailers.

## 9. Tích hợp với Spring gRPC

Spring gRPC vận hành trên nền `grpc-java`, nên các API `Metadata`, `ServerInterceptor`, `CallCredentials` và `Status` được sử dụng ở tầng tích hợp thích hợp.

Một luồng tổ chức điển hình:

1. **Client configuration:** cấu hình channel bảo mật, nơi lấy token và việc gắn `CallCredentials` vào stub được sử dụng.
2. **Server configuration:** đăng ký interceptor xác thực tại phạm vi service cần bảo vệ.
3. **Principal mapping:** sau khi xác thực, đưa thông tin danh tính tin cậy vào context được sử dụng trong xử lý RPC.
4. **Authorization policy:** phân quyền theo phương thức, scope và tài nguyên tại service hoặc tầng policy.
5. **Observability:** chỉ log request ID, mã gRPC status và thông tin không nhạy cảm cần thiết.

Ví dụ một bean tạo interceptor:

```java
import io.grpc.ServerInterceptor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RpcSecurityConfiguration {

    @Bean
    ServerInterceptor accessTokenServerInterceptor(
            AccessTokenServerInterceptor.TokenVerifier tokenVerifier) {
        return new AccessTokenServerInterceptor(tokenVerifier);
    }
}
```

Bean trên cho thấy cách cung cấp dependency của interceptor bằng Spring. **Việc tự động áp dụng bean interceptor cho server hoặc chọn thứ tự giữa các interceptor tùy phiên bản và cách cấu hình Spring gRPC/starter.** Cần đăng ký theo cơ chế tương ứng trong dự án, rồi kiểm thử một RPC thật để xác nhận interceptor chạy. Với nhiều cơ chế xác thực hoặc RPC công khai (health check, reflection theo chính sách), hãy định nghĩa rõ phạm vi bảo vệ; không vô tình để một endpoint nhạy cảm nằm ngoài chuỗi interceptor.

Không lẫn “Spring gRPC” với một starter bên thứ ba có annotation và cấu hình tương tự nhưng API khác. Giữ phần xác thực phụ thuộc tối thiểu vào chi tiết starter giúp dễ kiểm thử và nâng cấp.

## 10. Token hết hạn, retry, deadline và streaming

### Vòng đời token

Access token thường có hạn sử dụng. Client nên có thành phần quản lý token có thể:

- Lấy token từ nguồn tin cậy và lưu an toàn theo chính sách ứng dụng.
- Làm mới khi cần, với kiểm soát số lượng yêu cầu refresh đồng thời.
- Phân biệt token của người dùng và token của chính dịch vụ.
- Xử lý phản hồi `UNAUTHENTICATED` theo quy trình xác thực phù hợp, tránh lặp vô hạn cùng token đã hết hạn.

Không lưu token dùng chung trong biến static toàn cục nếu ứng dụng phục vụ nhiều danh tính. Không để nhiều người dùng sử dụng chung một singleton stub có bearer token cố định của một người.

### Retry và deadline

gRPC có thể retry một số tình huống tùy cấu hình và tính chất RPC. Thông tin xác thực cần được áp dụng đúng cho mỗi attempt, và thao tác làm mới token phải có giới hạn. Không mặc định retry tất cả lời gọi `UNAUTHENTICATED` hoặc `PERMISSION_DENIED`; đây thường là lỗi cần sửa credentials/quyền, không phải lỗi tạm thời có thể thử lại ngay.

Client thiết lập deadline qua API `withDeadlineAfter(...)` hoặc `withDeadline(...)`. Nếu quá trình lấy token chậm, lời gọi cũng có thể hết deadline trước khi hoàn tất. Bảo đảm cơ chế lấy token có timeout phù hợp, không để queue xác thực vô hạn hoặc làm nghẽn gRPC executor.

### Streaming RPC

Với server streaming, client streaming và bidirectional streaming, authentication metadata được gửi khi **bắt đầu một RPC stream**. Không tự động có token mới trên từng message. Nếu token hết hạn trong một stream dài, chính sách server về thời hạn phiên, thu hồi token và thời lượng stream cần được thiết kế rõ. Không mặc định cập nhật `authorization` giữa chừng bằng một message.

### Gọi xuống service khác

Khi service A gọi service B, không nên tự động chuyển nguyên token của người dùng cho mọi downstream service. Token có thể bị ràng buộc `audience`, scope hoặc chính sách ủy quyền cụ thể. Tùy kiến trúc, A có thể dùng service identity, token exchange hoặc cơ chế on-behalf-of được hệ thống định danh hỗ trợ. B phải xác thực thông tin phù hợp với **chính B**.

## 11. Kiểm thử Authorization metadata

Nên kết hợp kiểm thử đơn vị cho verifier/policy và kiểm thử tích hợp bằng client/server gRPC thật. `InProcessServerBuilder` và `InProcessChannelBuilder` hữu ích để kiểm tra logic interceptor mà không mở cổng mạng; kiểm thử TLS, proxy, mTLS và hành vi giới hạn header cần môi trường kết nối tương ứng.

| Trường hợp | Dữ liệu đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| Không có header | Không gửi `authorization` | `UNAUTHENTICATED` |
| Sai scheme | `authorization: Basic ...` khi API chỉ hỗ trợ Bearer | `UNAUTHENTICATED` |
| Token rỗng hoặc sai định dạng | `authorization: Bearer ` | `UNAUTHENTICATED` |
| Trùng header | Hai value `authorization` | Bị từ chối theo chính sách minh họa |
| Token hết hạn | JWT quá `exp` | `UNAUTHENTICATED` |
| Token sai chữ ký hoặc sai audience | Credentials giả lập không hợp lệ | `UNAUTHENTICATED` |
| Token hợp lệ, thiếu scope | Danh tính hợp lệ gọi thao tác cấm | `PERMISSION_DENIED` |
| Token hợp lệ, đủ quyền | Danh tính và tài nguyên đúng chính sách | RPC thành công |
| Truy cập tài nguyên người khác | User A yêu cầu tài nguyên của user B | Bị từ chối hoặc che giấu theo policy |
| Hai người dùng dùng cùng client process | Stub/credentials tách theo danh tính | Không gửi nhầm token của người này cho người kia |
| Lỗi mạng đến verifier | Introspection service không phản hồi | Fail closed; status vận hành phù hợp, không cấp quyền |
| Log/trace | Header chứa token thử nghiệm | Không xuất hiện token trong log, trace, error trailers |
| Streaming | Token tại thời điểm bắt đầu stream | Interceptor xác thực khi RPC mở; phân quyền nhất quán theo chính sách |

Ví dụ kiểm tra cách tạo key và phát hiện header lặp bằng JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.Metadata;
import java.util.Iterator;
import org.junit.jupiter.api.Test;

class AuthorizationMetadataTest {
    private static final Metadata.Key<String> AUTHORIZATION =
        Metadata.Key.of("authorization", Metadata.ASCII_STRING_MARSHALLER);

    @Test
    void detectsRepeatedAuthorizationValues() {
        Metadata headers = new Metadata();
        headers.put(AUTHORIZATION, "Bearer token-A");
        headers.put(AUTHORIZATION, "Bearer token-B");

        Iterator<String> values = headers.getAll(AUTHORIZATION).iterator();
        assertTrue(values.hasNext());
        assertEquals("Bearer token-A", values.next());
        assertTrue(values.hasNext());
        assertEquals("Bearer token-B", values.next());
        assertFalse(values.hasNext());
    }
}
```

Unit test trên chỉ chứng minh hành vi `Metadata` trong Java. Để xác minh interceptor thật sự từ chối header lặp, cần gọi RPC thông qua server có đăng ký interceptor và kiểm tra gRPC status. Không dùng các chuỗi `token-A`/`token-B` làm credentials thực.

## 12. Tình huống thực hành: bảo vệ RPC xem đơn hàng

Giả sử bạn xây dựng `OrderService.GetOrder` bằng Spring gRPC. Người dùng đăng nhập lấy được access token; chỉ chủ đơn hàng hoặc nhân viên có quyền phù hợp mới được xem nội dung.

**Yêu cầu:**

1. Client sử dụng TLS, nhận token từ `tokenProvider` và gắn vào request metadata `authorization`.
2. Server interceptor chỉ chấp nhận một bearer credential, kiểm tra định dạng và chuyển token cho verifier đáng tin cậy.
3. Verifier cung cấp danh tính đã xác thực. Nếu token sai/hết hạn, trả `UNAUTHENTICATED`.
4. Service kiểm tra quyền `orders:read`, tenant và quyền sở hữu của `order_id`. Nếu không có quyền, trả `PERMISSION_DENIED` hoặc `NOT_FOUND` theo chính sách.
5. Request/response Protobuf chỉ mang dữ liệu nghiệp vụ; log chỉ lưu request ID, trạng thái và trường không nhạy cảm.
6. Kiểm thử riêng token hết hạn, scope thiếu, truy cập chéo tenant, hai người dùng đồng thời và lời gọi streaming nếu API có hỗ trợ.

**Câu hỏi tự kiểm tra:**

- Vì sao một `authorization` header có mặt chưa chứng minh client được phép gọi `GetOrder`?
- Khi nào dùng `UNAUTHENTICATED`, khi nào dùng `PERMISSION_DENIED`?
- Vì sao cần xác minh `audience` và không chuyển nguyên token cho mọi downstream service?
- `CallCredentials` giúp giải quyết hạn chế nào của một interceptor gắn token cố định?
- Vì sao `io.grpc.Context` không mặc nhiên giống `SecurityContextHolder` của Spring Security?
- Token bearer trong binary metadata có an toàn hơn token ASCII không?

**Ghi nhớ:** `authorization` là một ASCII metadata header phổ biến để truyền bearer token của lời gọi gRPC. Client chịu trách nhiệm gửi credentials đúng và bảo vệ kênh truyền; server chịu trách nhiệm xác minh credentials, tạo danh tính tin cậy và thực thi phân quyền theo phương thức/tài nguyên. Trong Spring gRPC, `CallCredentials`, `ServerInterceptor`, `Context`, TLS và `Status` là các thành phần phối hợp để thực hiện luồng này một cách rõ ràng, kiểm thử được.
