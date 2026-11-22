# Version negotiation qua metadata

## 1. Mục tiêu

Một ứng dụng Spring gRPC có thể gọi nhiều phiên bản server trong thời gian rolling deployment. Client cũng có thể được phát hành độc lập và hỗ trợ nhiều mức contract. Nếu các client vẫn gọi cùng một RPC path, metadata có thể mang thông tin phiên bản hoặc capability để server chọn hành vi phù hợp cho từng RPC.

**Version negotiation qua metadata** là quá trình client gửi phiên bản API mà nó muốn sử dụng trong metadata của một lời gọi gRPC; server kiểm tra khả năng hỗ trợ, chọn phiên bản phù hợp và có thể phản hồi phiên bản đã chọn. Cơ chế này hữu ích khi cùng một RPC path và message shape có thể phục vụ nhiều semantics tương thích.

Sau bài học, bạn có thể:

- Phân biệt API version, client build version và RPC method version.
- Gửi version/capability qua metadata của từng RPC.
- Kiểm tra và chọn phiên bản ở server bằng `ServerInterceptor`.
- Dùng `Context` để chuyển phiên bản đã chọn tới handler.
- Trả phiên bản được chọn hoặc danh sách phiên bản hỗ trợ trong response metadata/trailers.
- Giữ default tương thích cho caller cũ không gửi version.
- Nhận biết khi nào metadata negotiation không đủ và cần service/package version riêng.
- Kiểm thử negotiation, rollout và trường hợp client/server không có phiên bản chung.

## 2. Metadata nằm ở đâu trong một RPC?

gRPC truyền metadata cùng phần headers/trailers của HTTP/2 stream. Metadata là dữ liệu điều khiển đi kèm một RPC, chẳng hạn request ID, authentication credentials hoặc thông tin phiên bản. Nó không phải field trong Protobuf message.

Ví dụ một client gửi:

```text
x-api-version: v2
x-client-version: 4.8.1
x-request-id: 7c1...
```

Ba giá trị có ý nghĩa khác nhau:

| Metadata | Ý nghĩa | Có dùng để chọn contract không? |
|---|---|---|
| `x-api-version` | Phiên bản API client yêu cầu cho RPC | Có |
| `x-client-version` | Phiên bản build của ứng dụng/client | Không tự động; chủ yếu phục vụ quan sát |
| `x-request-id` | Correlation ID của một request | Không |

Không suy ra API version từ `x-client-version`. Một bản client có thể hỗ trợ nhiều API version; ngược lại, nhiều bản client khác nhau có thể cùng dùng một API version.

Metadata key phải dùng chữ thường. Giá trị ASCII dùng `Metadata.ASCII_STRING_MARSHALLER`; key nhị phân có hậu tố `-bin` và dùng marshaller nhị phân. Không tự đặt key bắt đầu bằng `grpc-`, vì tiền tố đó dành cho giao thức gRPC. Giữ metadata nhỏ, không dùng để truyền payload hoặc danh sách capability lớn.

Metadata thuộc từng RPC stream, không thuộc toàn bộ `ManagedChannel`. Nhiều RPC với version khác nhau có thể multiplex qua cùng một channel và cùng HTTP/2 connection.

## 3. Chọn chiến lược negotiation

Trước khi viết interceptor, xác định chính xác server và client sẽ thương lượng điều gì.

### Yêu cầu một version cụ thể

Đây là chiến lược đơn giản nhất:

```text
x-api-version: v2
```

Server chấp nhận `v2` nếu có implementation tương ứng; nếu không, server trả lỗi rõ ràng. Cách này phù hợp khi client đã biết chính xác contract version mà nó cần.

### Gửi danh sách version client hỗ trợ

Một client có thể gửi danh sách theo thứ tự ưu tiên:

```text
x-api-versions: v2,v1
```

Server chọn phiên bản đầu tiên trong danh sách mà nó hỗ trợ và trả về `x-api-selected-version`. Hai phía phải thống nhất quy tắc phân tích, thứ tự ưu tiên, định dạng version và cách xử lý giá trị không hợp lệ.

Không so sánh chuỗi version tùy ý theo thứ tự từ điển. Nếu dùng range hoặc semantic version, phải định nghĩa grammar và thuật toán chọn rõ ràng. Với contract RPC, các major version tường minh như `v1`, `v2` thường dễ vận hành hơn.

### Thương lượng capability

Nếu chỉ có một số tính năng độc lập cần bật, client có thể gửi capability:

```text
x-api-capabilities: pagination,sort-v2
```

Server xác nhận capability hỗ trợ và phản hồi tập đã chọn. Cách này tránh tạo quá nhiều major version cho các tính năng nhỏ, nhưng số tổ hợp có thể tăng nhanh. Chỉ dùng khi capability có semantics độc lập, có thể kiểm thử và có quy tắc tương thích rõ.

Trong bài này, ví dụ dùng yêu cầu version chính xác `x-api-version` để giữ thuật toán đơn giản.

## 4. Quy tắc tương thích cho caller cũ

Một client cũ có thể không gửi metadata version vì trước đây API chưa yêu cầu. Nếu server mới bắt buộc header ngay khi deploy, caller cũ sẽ thất bại dù Protobuf request vẫn hợp lệ.

Hãy quy định default tường minh:

| Request metadata | Server xử lý |
|---|---|
| Không có `x-api-version` | Chọn semantics legacy, ví dụ `v1` |
| `x-api-version: v1` | Chọn `v1` |
| `x-api-version: v2` | Chọn `v2` nếu server hỗ trợ |
| Version rỗng hoặc không hợp lệ | Trả `INVALID_ARGUMENT` |
| Version đúng định dạng nhưng server không hỗ trợ | Trả lỗi negotiation, kèm danh sách version hỗ trợ |

Default cho metadata bị thiếu là một phần behavioral contract. Không tự đổi default từ `v1` sang `v2` khi caller chưa opt-in. Nếu cần đổi default, phải migration caller có kế hoạch hoặc dùng service version riêng.

## 5. Gửi version từ Spring gRPC client

Tạo metadata key với tên chữ thường và ASCII marshaller:

```java
private static final Metadata.Key<String> API_VERSION =
        Metadata.Key.of(
                "x-api-version",
                Metadata.ASCII_STRING_MARSHALLER);
```

Một gateway có thể gắn version vào từng call:

```java
@Component
public class CatalogGateway {
    private final CatalogServiceGrpc.CatalogServiceBlockingStub baseStub;

    public CatalogGateway(
            @Qualifier("catalogChannel") ManagedChannel channel) {
        this.baseStub = CatalogServiceGrpc.newBlockingStub(channel);
    }

    public SearchResponse searchV2(SearchRequest request) {
        Metadata headers = new Metadata();
        headers.put(API_VERSION, "v2");

        var versionedStub = baseStub.withInterceptors(
                MetadataUtils.newAttachHeadersInterceptor(headers));

        return versionedStub
                .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
                .search(request);
    }
}
```

Ví dụ dùng `MetadataUtils.newAttachHeadersInterceptor` của gRPC Java. API tiện ích có thể khác hoặc được đánh dấu deprecated tùy phiên bản dependency; khi đó dùng `ClientInterceptor` tương đương của dự án. Metadata phải được tạo cho đúng phạm vi call/version và không bị sửa đồng thời bởi nhiều thread.

Generated stub là immutable; các lệnh `withInterceptors` và `withDeadlineAfter` tạo stub dẫn xuất. Không cần tạo `ManagedChannel` riêng chỉ vì muốn gửi `v1` hay `v2`. Channel vẫn được tái sử dụng nếu target và transport/security configuration giống nhau.

Không đặt bearer token hoặc dữ liệu bí mật vào `x-api-version`. Authentication nên dùng call credentials hoặc cơ chế metadata bảo mật riêng; version do client gửi chỉ là thông tin yêu cầu, không phải bằng chứng về quyền truy cập.

## 6. Kiểm tra và chọn version ở server

`ServerInterceptor` có thể đọc metadata trước khi request tới handler. Ví dụ dưới đây:

- Chọn `v1` khi caller không gửi version.
- Chấp nhận `v1` và `v2`.
- Từ chối version không hỗ trợ trước khi chạy handler.
- Đặt version đã chọn vào gRPC `Context`.
- Thêm version đã chọn vào response headers.

```java
package dev.example.catalog.server;

import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.ForwardingServerCall;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.Set;

public final class ApiVersionInterceptor implements ServerInterceptor {
    static final Context.Key<String> API_VERSION_CONTEXT =
            Context.key("api-version");

    private static final Metadata.Key<String> REQUESTED_VERSION =
            Metadata.Key.of(
                    "x-api-version",
                    Metadata.ASCII_STRING_MARSHALLER);

    private static final Metadata.Key<String> SELECTED_VERSION =
            Metadata.Key.of(
                    "x-api-selected-version",
                    Metadata.ASCII_STRING_MARSHALLER);

    private static final Metadata.Key<String> SUPPORTED_VERSIONS =
            Metadata.Key.of(
                    "x-api-supported-versions",
                    Metadata.ASCII_STRING_MARSHALLER);

    private static final Set<String> SUPPORTED = Set.of("v1", "v2");
    private static final String LEGACY_DEFAULT = "v1";

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata requestHeaders,
            ServerCallHandler<ReqT, RespT> next) {

        String requested = requestHeaders.get(REQUESTED_VERSION);
        String selected = requested == null
                ? LEGACY_DEFAULT
                : requested;

        if (!selected.matches("v[1-9][0-9]*")) {
            call.close(
                    Status.INVALID_ARGUMENT.withDescription(
                            "API version must use the vN format"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        if (!SUPPORTED.contains(selected)) {
            Metadata trailers = new Metadata();
            trailers.put(SUPPORTED_VERSIONS, "v1,v2");
            call.close(
                    Status.FAILED_PRECONDITION.withDescription(
                            "Requested API version is not supported"),
                    trailers);
            return new ServerCall.Listener<ReqT>() {};
        }

        ServerCall<ReqT, RespT> forwardingCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
                    @Override
                    public void sendHeaders(Metadata responseHeaders) {
                        responseHeaders.put(SELECTED_VERSION, selected);
                        super.sendHeaders(responseHeaders);
                    }
                };

        Context context = Context.current()
                .withValue(API_VERSION_CONTEXT, selected);
        return Contexts.interceptCall(
                context, forwardingCall, requestHeaders, next);
    }
}
```

Đây là interceptor minh họa cho một service có tập version cố định. Trong production, giới hạn interceptor vào đúng service/method cần negotiation và lấy danh sách hỗ trợ từ cấu hình có kiểm soát. Nếu một service chỉ hỗ trợ `v1`, không khai báo `v2` trong tập hỗ trợ.

`FAILED_PRECONDITION` diễn tả rằng server không thể thực hiện call với version được yêu cầu trong cấu hình hiện tại. Có thể dùng status khác nếu API đã công bố quy ước riêng; điều quan trọng là giữ mapping ổn định. `UNIMPLEMENTED` thường phù hợp khi full method path không có handler, còn negotiation thất bại trên một method đã tồn tại là tình huống khác.

Đăng ký interceptor qua cơ chế global/server interceptor của Spring gRPC starter đang dùng. Tên annotation hoặc cấu hình đăng ký khác nhau theo starter và phiên bản; không tự tạo thêm gRPC server nếu framework đã sở hữu server.

## 7. Đưa version đã chọn vào handler

Handler đọc version từ `Context` để chọn policy:

```java
@Override
public void search(
        SearchRequest request,
        StreamObserver<SearchResponse> observer) {
    String apiVersion =
            ApiVersionInterceptor.API_VERSION_CONTEXT.get();

    try {
        SearchResponse response;
        if ("v1".equals(apiVersion)) {
            response = searchService.searchLegacy(request);
        } else if ("v2".equals(apiVersion)) {
            response = searchService.searchV2(request);
        } else {
            observer.onError(Status.INTERNAL
                    .withDescription("API version context is missing")
                    .asRuntimeException());
            return;
        }

        observer.onNext(response);
        observer.onCompleted();
    } catch (IllegalArgumentException ex) {
        observer.onError(Status.INVALID_ARGUMENT
                .withDescription("invalid search request")
                .asRuntimeException());
    }
}
```

`Contexts.interceptCall` gắn context cho listener và callback của RPC. Nếu ứng dụng tự chuyển công việc sang executor, phải bảo đảm context được truyền sang tác vụ bất đồng bộ theo cơ chế gRPC/Context phù hợp; không giữ version trong một field mutable của singleton service.

Quan trọng: cách dispatch trên chỉ phù hợp khi cả hai semantics có thể dùng chung method path và request/response shape tương thích. Nếu `v2` cần Protobuf message khác cấu trúc, hãy tạo service/package version riêng hoặc method mới. Metadata không làm server cũ hiểu field mà schema của nó không có, cũng không đổi full method path.

## 8. Trả version đã chọn cho client

Server có thể phản hồi:

```text
x-api-selected-version: v2
```

Header này cho client biết server thực sự áp dụng version nào. Đây là thông tin hữu ích khi client gửi danh sách version ưu tiên hoặc khi server có default cho caller cũ.

Nếu negotiation bị từ chối, server có thể trả trailer:

```text
x-api-supported-versions: v1,v2
```

Client có thể đọc trailer từ `StatusRuntimeException`:

```java
try {
    return versionedStub.search(request);
} catch (StatusRuntimeException ex) {
    Metadata trailers = Status.trailersFromThrowable(ex);
    String supported = trailers == null
            ? null
            : trailers.get(SUPPORTED_VERSIONS);

    log.warn("API negotiation failed: status={}, supported={}",
            ex.getStatus().getCode(), supported);
    throw ex;
}
```

Để đọc `x-api-selected-version` trong response headers của call thành công, client có thể dùng một `ClientInterceptor` bọc `ClientCall.Listener.onHeaders`. Không dựa vào trailer lỗi để xác định version của một call thành công.

Client không nên tự động downgrade với mọi lỗi. Chỉ cân nhắc chọn version khác khi status và supported-version metadata cho thấy negotiation thất bại, version thay thế được hỗ trợ và semantics của fallback phù hợp.

## 9. Negotiation qua metadata khác gì version hóa service?

| Tiêu chí | Metadata negotiation | Versioned service/package |
|---|---|---|
| RPC path | Giữ nguyên path | Path khác theo package/service |
| Protobuf request/response | Phải dùng chung shape tương thích hoặc envelope có chủ đích | Có thể có message riêng từng version |
| Chọn semantics | Dựa trên metadata từng RPC | Được xác định bởi method path |
| Client cũ không gửi version | Server cần default legacy | Client gọi path v1 rõ ràng |
| Khả năng quan sát | Cần ghi nhận version đã chọn | Có thể phân biệt ngay từ full method name |
| Phù hợp | Thay đổi semantics/capability có thể thương lượng trên cùng contract | Breaking schema hoặc semantics lớn |

Nếu v1 và v2 có request/response khác nhau, versioned service thường rõ ràng và an toàn hơn. Ví dụ `/catalog.v1.CatalogService/Search` và `/catalog.v2.CatalogService/Search` đã mang version trong method path; thêm `x-api-version` có thể trở thành tín hiệu dư thừa hoặc gây mâu thuẫn.

Metadata negotiation cũng không phải content negotiation tự động như HTTP framework. gRPC không tự chọn version chỉ vì client gửi một header; ứng dụng phải kiểm tra, quyết định, dispatch và phản hồi.

## 10. Negotiation với capability hoặc version range

Khi client hỗ trợ nhiều version, có thể dùng một danh sách ưu tiên thay vì gửi một version duy nhất. Thuật toán nên được quy định cụ thể:

1. Client gửi `x-api-versions: v2,v1` theo thứ tự ưu tiên.
2. Server kiểm tra danh sách có đúng định dạng và không chứa giá trị lặp bất thường.
3. Server chọn version đầu tiên mà service/method hiện tại hỗ trợ.
4. Server đưa version đã chọn vào `Context` và response header.
5. Nếu không có version chung, trả `FAILED_PRECONDITION` cùng danh sách hỗ trợ.

Không nên parse danh sách bằng cách chọn chuỗi có số lớn nhất nếu chưa có quy tắc versioning chính thức. Với capability, server cần phản hồi tập capability được chấp nhận; client phải kiểm tra các capability bắt buộc của nó có nằm trong tập đó hay không.

Không nhồi một ma trận tính năng lớn vào metadata. Khi các capability phụ thuộc lẫn nhau hoặc thay đổi request/response shape, một Protobuf negotiation RPC hoặc versioned service có thể dễ kiểm thử hơn.

## 11. Metadata negotiation trong streaming RPC

Metadata được gửi khi RPC bắt đầu. Với client streaming, server streaming hoặc bidirectional streaming, version được chọn cho toàn bộ stream đó.

- Không đổi API version giữa các message trong cùng stream.
- Nếu client cần chuyển version, kết thúc/cancel stream cũ và mở RPC mới với metadata mới.
- Với stream sống lâu, phải tính đến thời gian hỗ trợ version và thời điểm server ngừng phục vụ version cũ.
- Nếu stream cần resume, cursor/resume token phải giữ semantics tương thích với version đã chọn.

Một stream có thể tồn tại lâu hơn thời gian rollout server. Không retire version khi còn stream hợp lệ đang chạy nếu việc đó làm gián đoạn contract đã cam kết; dùng drain policy và giới hạn thời gian rõ ràng.

## 12. Giới hạn, bảo mật và vận hành

Metadata phù hợp với thông tin điều khiển nhỏ, không phải nơi lưu payload:

- Giữ key ngắn, chữ thường và giá trị có giới hạn.
- Không truyền Protobuf JSON, danh sách dữ liệu lớn hoặc thông tin cá nhân trong version header.
- Không dùng prefix `grpc-` dành riêng cho giao thức.
- Tôn trọng giới hạn header/metadata của client, proxy và server.
- Tránh ghi toàn bộ metadata vào log vì có thể chứa token hoặc dữ liệu nhạy cảm.

Version do client gửi là input không đáng tin cậy. Server phải validate và chỉ chọn version đã triển khai. API version không thay thế authentication/authorization; không cấp quyền cao hơn chỉ vì caller yêu cầu `v2`.

Metrics nên ghi:

| Metric/dimension | Mục đích |
|---|---|
| Full method name | Biết RPC nào đang được gọi |
| Requested API version | Biết caller yêu cầu gì |
| Selected API version | Biết server thực sự áp dụng gì |
| Negotiation failure/status | Phát hiện client và server không có version chung |
| Client version | Khoanh vùng nhóm caller cần migration |
| Latency theo selected version | So sánh hiệu năng các semantics |

Version là dimension có cardinality thấp nếu tập giá trị được kiểm soát. Không dùng request ID, user ID hoặc giá trị metadata tùy ý làm metric label.

## 13. Rollout và kiểm thử

Thứ tự rollout an toàn:

1. Triển khai server hỗ trợ version mới nhưng vẫn giữ default legacy cho request không có metadata.
2. Xác nhận mọi replica sau load balancer đều hỗ trợ version mới.
3. Kiểm thử client cũ không gửi metadata và xác nhận vẫn nhận semantics cũ.
4. Bật client mới gửi version tường minh theo nhóm nhỏ.
5. Theo dõi requested/selected version, negotiation failure, status và latency.
6. Mở rộng rollout khi kết quả ổn định; giữ fallback có thời hạn nếu cần.
7. Chỉ ngừng version cũ sau khi caller và stream cũ đã migration, theo support policy.

Ma trận test tối thiểu:

| Client metadata | Server hỗ trợ | Kết quả mong đợi |
|---|---|---|
| Không có header | v1, v2 | Chọn default legacy v1 |
| `v1` | v1, v2 | Chọn v1 |
| `v2` | v1, v2 | Chọn v2 |
| `v3` | v1, v2 | `FAILED_PRECONDITION`, trả supported versions |
| Giá trị rỗng/không hợp lệ | v1, v2 | `INVALID_ARGUMENT` |
| `v2` | Chỉ v1 | Negotiation thất bại; không âm thầm giả vờ đã chạy v2 |

Kiểm thử bổ sung:

- Hai RPC đồng thời trên cùng channel yêu cầu hai version khác nhau; xác minh context không rò giữa call.
- Server phản hồi đúng `x-api-selected-version`.
- Caller cũ không gửi metadata vẫn hoạt động sau deploy.
- Version không hỗ trợ bị từ chối trước khi chạy nghiệp vụ.
- Streaming RPC giữ nguyên version từ đầu đến cuối.
- Client chỉ fallback khi negotiation status cho phép và fallback semantics đã được xác nhận.
- Interceptor được đăng ký đúng trong Spring gRPC server và không bị đăng ký trùng.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Caller cũ lỗi sau khi bật negotiation | Server bắt buộc header | Định nghĩa default legacy khi header absent |
| Client gửi v2 nhưng server xử lý v1 | Server cũ bỏ qua metadata không hiểu | Deploy server hỗ trợ trước hoặc capability routing |
| Version bị lẫn giữa hai request đồng thời | Lưu version vào field mutable singleton | Dùng gRPC `Context` theo call |
| Client nghĩ v2 đã được chọn nhưng server dùng default | Không trả/không kiểm tra selected version | Phản hồi và quan sát `x-api-selected-version` |
| Negotiation thất bại bị retry vô hạn | Không phân biệt lỗi version với lỗi tạm thời | Dùng status rõ ràng và fallback có điều kiện |
| Header quá lớn hoặc chứa dữ liệu nhạy cảm | Dùng metadata như payload/log context | Chỉ truyền version/capability ngắn |
| Dùng metadata để thay schema version | Nghĩ server tự hiểu message mới | Dùng service/package version khi shape không tương thích |
| API version bị dùng như quyền truy cập | Tin header do client tự khai báo | Xác thực principal và authorize độc lập |
| Stream đổi semantics giữa chừng | Cố cập nhật version sau khi RPC bắt đầu | Chọn version khi mở stream; mở RPC mới khi cần đổi |

## 15. Bài tập thực hành

**Tình huống:** Catalog có một RPC `Search` với request/response shape có thể giữ tương thích. Server mới hỗ trợ hai semantics: v1 sắp xếp theo relevance, v2 cho phép sort theo thời gian và filter category. Client cũ không gửi metadata; client mới muốn yêu cầu v2.

Hãy thực hiện:

1. Định nghĩa `x-api-version`, `x-api-selected-version` và `x-api-supported-versions` bằng metadata key ASCII.
2. Viết client gateway gửi `v2` theo từng RPC mà vẫn tái sử dụng channel.
3. Viết server interceptor chọn `v1` khi header absent, chấp nhận `v1`/`v2` và từ chối version khác.
4. Đưa selected version vào gRPC `Context`; handler dispatch tới policy v1 hoặc v2.
5. Trả selected version trong response headers và supported versions trong trailers khi negotiation thất bại.
6. Kiểm thử hai RPC đồng thời trên cùng channel với version khác nhau.
7. Kiểm thử caller cũ không có header và client mới gọi server chưa hỗ trợ v2.
8. Bổ sung metrics requested/selected version, status và latency; không ghi metadata nhạy cảm.
9. Xác định ranh giới: nếu v2 cần Protobuf message khác shape, chuyển sang versioned service/package thay vì dựa vào metadata.

**Tiêu chí hoàn thành:** version được chọn theo từng RPC, default legacy không phá caller cũ, server phản hồi version đã chọn, context không rò giữa các call, unsupported version có status rõ và giải pháp phù hợp khi schema không tương thích.

## 16. Ghi nhớ

Metadata negotiation cho phép client yêu cầu API version hoặc capability theo từng RPC mà vẫn dùng chung `ManagedChannel`. Client gửi version qua metadata; server interceptor validate, chọn version, đưa lựa chọn vào `Context` và có thể phản hồi bằng headers/trailers. Caller cũ không gửi header cần có default legacy rõ ràng. Version metadata là input do client kiểm soát, không phải authentication và không tự làm schema mới tương thích với server cũ. Dùng cơ chế này khi cùng RPC path/message shape có thể hỗ trợ nhiều semantics; nếu Protobuf contract hoặc method path khác nhau, versioned service/package thường rõ ràng hơn.
