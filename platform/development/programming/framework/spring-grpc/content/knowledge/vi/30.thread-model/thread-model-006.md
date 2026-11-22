# Thread safety của generated stub

Trong ứng dụng Spring gRPC, nhiều request có thể gọi cùng một backend đồng thời. Nếu mỗi request tự tạo channel và stub, ứng dụng tốn tài nguyên kết nối, khó quản lý lifecycle và tạo thêm chi phí khởi tạo. Với gRPC Java, generated stub là đối tượng bất biến và có thể được chia sẻ giữa nhiều thread. Một stub dùng chung phục vụ được nhiều RPC đồng thời; mỗi lần gọi tạo một call riêng với trạng thái riêng.

Điều đó không có nghĩa mọi đối tượng xung quanh stub đều an toàn khi dùng đồng thời. Cần phân biệt stub, channel, CallOptions, StreamObserver, protobuf builder, interceptor và executor. Bài này tập trung vào phạm vi thread safety của generated stub và cách tổ chức client trong Spring gRPC.

## 1. Generated stub bất biến và dùng chung được

Từ một service protobuf, gRPC Java sinh các kiểu stub phổ biến:

| Stub | Cách gọi | Kết quả |
| --- | --- | --- |
| CatalogServiceBlockingStub | Gọi method đồng bộ | Trả response hoặc ném StatusRuntimeException |
| CatalogServiceStub | Gọi method bất đồng bộ | Nhận kết quả qua StreamObserver |
| CatalogServiceFutureStub | Gọi theo future | Trả future đại diện kết quả RPC |

Generated stub được xây dựng trên AbstractStub và giữ channel cùng CallOptions. Cấu hình của stub là bất biến; các phương thức withDeadlineAfter, withWaitForReady hoặc withCompression trả về một stub mới với call options mới, không sửa stub ban đầu.

Do đó, một stub có thể được inject vào singleton service và được nhiều request thread gọi đồng thời:

```java
@Service
public class CatalogClient {
    private final CatalogServiceGrpc.CatalogServiceBlockingStub stub;

    public CatalogClient(
            CatalogServiceGrpc.CatalogServiceBlockingStub stub) {
        this.stub = stub;
    }

    public Product getProduct(String productId) {
        GetProductRequest request = GetProductRequest.newBuilder()
                .setProductId(productId)
                .build();
        return stub.getProduct(request);
    }
}
```

Không cần tạo một bản stub mới cho mỗi thread hoặc đồng bộ hóa toàn bộ lời gọi chỉ để bảo vệ stub. Mỗi RPC độc lập có call state riêng do gRPC runtime quản lý.

## 2. Channel cũng được thiết kế để tái sử dụng

Stub không tự mở một TCP connection riêng cho mỗi method. Nó gọi qua Channel; trong ứng dụng client thông thường, channel cụ thể là ManagedChannel. Channel gRPC Java được thiết kế để dùng đồng thời và tái sử dụng cho nhiều RPC.

Một cấu hình Spring có thể tạo channel và stub ở phạm vi application:

```java
@Configuration
public class CatalogGrpcClientConfiguration {
    @Bean(destroyMethod = "shutdown")
    ManagedChannel catalogChannel() {
        return ManagedChannelBuilder
                .forAddress("catalog.internal", 9090)
                .useTransportSecurity()
                .build();
    }

    @Bean
    CatalogServiceGrpc.CatalogServiceBlockingStub catalogBlockingStub(
            ManagedChannel catalogChannel) {
        return CatalogServiceGrpc.newBlockingStub(catalogChannel);
    }

    @Bean
    CatalogServiceGrpc.CatalogServiceStub catalogAsyncStub(
            ManagedChannel catalogChannel) {
        return CatalogServiceGrpc.newStub(catalogChannel);
    }
}
```

Ví dụ minh họa một channel được chia sẻ bởi blocking stub và async stub. Trong dự án thật, cấu hình TLS, load balancing, name resolver, interceptors và shutdown hook cần theo môi trường triển khai.

Các nguyên tắc lifecycle:

- Tạo channel ở phạm vi ứng dụng hoặc client component, không tạo mới cho từng request.
- Dùng channel cho nhiều stub nếu chúng cùng đích và cùng cấu hình transport.
- Không gọi shutdown() sau mỗi RPC; channel còn được các request khác dùng.
- Đóng channel khi ứng dụng dừng hoặc khi client component thực sự hết vòng đời.
- Nếu cần cấu hình transport khác nhau, tạo channel riêng theo từng đích/chính sách và quản lý lifecycle độc lập.

Stub không có lifecycle shutdown riêng; channel là tài nguyên cần được đóng.

## 3. Tạo stub mới khi cần CallOptions riêng cho một RPC

Vì stub bất biến, cấu hình deadline cho một call bằng cách tạo stub dẫn xuất:

```java
public Product getProduct(String productId) {
    GetProductRequest request = GetProductRequest.newBuilder()
            .setProductId(productId)
            .build();

    CatalogServiceGrpc.CatalogServiceBlockingStub callStub =
            baseStub.withDeadlineAfter(700, TimeUnit.MILLISECONDS);

    return callStub.getProduct(request);
}
```

baseStub vẫn giữ nguyên deadline/call options ban đầu. callStub chỉ áp dụng cấu hình riêng cho lời gọi này. Cách làm phù hợp khi các use case có ngân sách thời gian khác nhau.

Tránh ghi đè một field stub dùng chung cho từng request:

```java
// Không nên: field dùng chung bị thay đổi theo từng request.
this.stub = this.stub.withDeadlineAfter(timeout, TimeUnit.MILLISECONDS);
return this.stub.getProduct(request);
```

Dù mỗi stub được tạo ra là bất biến, việc gán lại field singleton tạo mutable shared state. Hai request đồng thời có thể ghi đè cấu hình của nhau. Hãy giữ base stub final và lưu stub dẫn xuất trong biến cục bộ của call.

CallOptions cũng bất biến; các phương thức with... tạo một cấu hình mới. Deadline là per-call policy, không phải trạng thái nên thay đổi trên stub dùng chung.

## 4. Thread safety không đồng nghĩa blocking stub luôn phù hợp

Blocking stub có thể được gọi an toàn từ nhiều thread, nhưng mỗi lời gọi giữ thread của caller cho tới khi RPC hoàn tất hoặc thất bại. Thread safety chỉ nói việc chia sẻ object không gây race; nó không bảo đảm khả năng mở rộng khi có nhiều request chờ mạng.

| Tình huống | Lựa chọn thường phù hợp |
| --- | --- |
| Luồng xử lý đồng bộ trên worker thread có giới hạn | Blocking stub với deadline rõ ràng |
| Ứng dụng cần xử lý callback/asynchronous | Async stub |
| Kết hợp pipeline future | Future stub |
| Event loop hoặc callback thread cần không blocking | Async/future API; không gọi blocking stub trực tiếp |

Không gọi blocking stub trên Netty event loop, gRPC transport callback thread hoặc executor có số thread quá nhỏ cho lượng call chờ. Một RPC bị chậm có thể chiếm thread và làm các tác vụ khác bị đói tài nguyên. Dùng executor có giới hạn, deadline và giới hạn concurrency.

## 5. Mỗi RPC cần observer và state riêng

Generated async stub có thể được gọi đồng thời, nhưng StreamObserver được truyền vào một call là đối tượng gắn với call đó. Không dùng một observer mutable duy nhất cho nhiều RPC độc lập:

```java
public void getProductAsync(
        String productId,
        Consumer<Product> onSuccess,
        Consumer<Throwable> onFailure) {

    GetProductRequest request = GetProductRequest.newBuilder()
            .setProductId(productId)
            .build();

    asyncStub.getProduct(request, new StreamObserver<>() {
        @Override
        public void onNext(Product response) {
            onSuccess.accept(response);
        }

        @Override
        public void onError(Throwable error) {
            onFailure.accept(error);
        }

        @Override
        public void onCompleted() {
            // Unary call đã kết thúc.
        }
    });
}
```

Mỗi lần gọi tạo observer mới, nên callback và kết quả không bị trộn giữa các request. Nếu observer cập nhật state dùng chung trong ứng dụng, state đó vẫn cần đồng bộ hóa hoặc thiết kế theo concurrency model phù hợp.

Không giữ request ID, response, exception hoặc callback của một RPC trong field mutable của singleton client. Hãy giữ state ở biến cục bộ hoặc đối tượng operation riêng.

## 6. StreamObserver không tự động thread-safe

Với client streaming hoặc bidirectional streaming, async stub trả về một StreamObserver<Request> để ứng dụng gửi nhiều message:

```java
StreamObserver<ImportProductRequest> requestStream =
        asyncStub.importProducts(new StreamObserver<ImportSummary>() {
            @Override
            public void onNext(ImportSummary summary) {
                handleSummary(summary);
            }

            @Override
            public void onError(Throwable error) {
                handleFailure(error);
            }

            @Override
            public void onCompleted() {
                handleCompleted();
            }
        });

requestStream.onNext(firstBatch);
requestStream.onNext(secondBatch);
requestStream.onCompleted();
```

StreamObserver không được bảo đảm thread-safe. Nếu nhiều producer thread cùng gọi onNext, onError hoặc onCompleted trên một observer, ứng dụng phải serialize các lời gọi. Có thể dùng một executor tuần tự hoặc một hàng đợi có giới hạn để làm single writer.

Quy tắc:

- Không gọi onNext từ nhiều thread trên cùng request observer.
- Chỉ gửi onCompleted hoặc onError một lần; đây là terminal signal.
- Không gửi thêm message sau terminal signal.
- Không chia sẻ request observer của một stream cho stream khác.
- Nếu cần đồng bộ bằng lock, giữ vùng lock ngắn và không thực hiện I/O blocking bên trong.

Tương tự, server-side StreamObserver cần được dùng theo quy tắc tuần tự hóa của ứng dụng. Stub thread-safe không làm observer hoặc state trong callback trở nên thread-safe.

## 7. Protobuf message và Builder có đặc tính khác nhau

Generated protobuf message sau khi build() là immutable, nên có thể chia sẻ để đọc từ nhiều thread. Builder là đối tượng mutable; không chia sẻ một builder giữa các thread nếu không có đồng bộ.

```java
GetProductRequest request = GetProductRequest.newBuilder()
        .setProductId("P-100")
        .build(); // Message đã build có thể được chia sẻ để đọc.

GetProductRequest.Builder builder = GetProductRequest.newBuilder();
builder.setProductId("P-200"); // Builder mutable, chỉ dùng trong phạm vi sở hữu.
GetProductRequest anotherRequest = builder.build();
```

Một cách an toàn là tạo builder bên trong method hoặc operation, build message rồi truyền message immutable cho stub. Không tái sử dụng builder singleton để tạo request cho nhiều call đồng thời.

## 8. Interceptor và CallCredentials cũng phải chịu tải đồng thời

Stub dùng chung kéo theo channel-level interceptor và credential provider có thể được gọi từ nhiều RPC cùng lúc. Vì vậy:

- Interceptor nên stateless hoặc chỉ giữ dependency immutable/thread-safe.
- Tạo counter, timestamp, listener wrapper và state riêng trong interceptCall.
- Không lưu request-specific metadata vào field của interceptor.
- Credential provider phải xử lý refresh token và cache theo cách thread-safe.
- Không block lâu trong interceptor khi lấy credential; cân nhắc CallCredentials và cơ chế async phù hợp.
- Dùng gRPC Context cho dữ liệu gắn với call; khi chuyển executor tùy chỉnh, propagate context tường minh.

Ví dụ một interceptor an toàn nên lấy dữ liệu per-call vào biến cục bộ:

```java
@Override
public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
        MethodDescriptor<ReqT, RespT> method,
        CallOptions callOptions,
        Channel next) {
    long startedAt = System.nanoTime();
    String methodName = method.getFullMethodName();
    ClientCall<ReqT, RespT> delegate = next.newCall(method, callOptions);
    return wrap(delegate, methodName, startedAt);
}
```

startedAt và methodName thuộc call đang tạo, không được lưu vào field để RPC sau ghi đè.

## 9. Kiểm thử việc chia sẻ stub

Kiểm thử concurrency nên xác minh nhiều call dùng chung một stub vẫn nhận đúng response và status:

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| Nhiều unary RPC đồng thời qua một stub | Mỗi call nhận đúng response của request tương ứng |
| Hai deadline khác nhau | Deadline của call này không làm thay đổi call kia |
| Blocking và async stub dùng chung channel | Channel xử lý đồng thời, không bị đóng giữa chừng |
| Hai streaming call | Observer và message count không bị trộn |
| Nhiều producer gửi vào một stream | Các message được serialize theo thứ tự ứng dụng quy định |
| Interceptor dùng chung | Không có request-specific mutable state bị chia sẻ |
| Ứng dụng shutdown | Channel được đóng một lần sau khi ngừng nhận call mới |

Có thể dùng in-process server/channel cho test gRPC và stress test có giới hạn thread. Khi test Spring, inject cùng bean stub vào nhiều task song song để xác minh wiring và lifecycle thực tế. Không dùng test chỉ tạo nhiều stub mới vì như vậy chưa kiểm tra trường hợp chia sẻ cùng một stub.

## 10. Checklist sử dụng generated stub an toàn

- [ ] Dùng lại generated stub bất biến giữa các thread.
- [ ] Dùng lại ManagedChannel thread-safe cho nhiều RPC cùng đích.
- [ ] Quản lý shutdown channel ở application lifecycle, không ở từng request.
- [ ] Dùng withDeadlineAfter để tạo stub dẫn xuất cục bộ cho call cần timeout riêng.
- [ ] Không gán lại field stub singleton theo từng request.
- [ ] Chọn blocking, async hoặc future stub theo mô hình thread của ứng dụng.
- [ ] Tạo observer và state riêng cho từng RPC.
- [ ] Serialize các thao tác trên cùng StreamObserver khi có nhiều producer thread.
- [ ] Không chia sẻ protobuf Builder mutable giữa các thread; chia sẻ message đã build để đọc.
- [ ] Bảo đảm interceptor và credential provider an toàn khi được gọi đồng thời.
- [ ] Propagate gRPC Context qua executor tùy chỉnh.
- [ ] Có concurrency test cho unary, streaming, deadline và shutdown.

**Tự kiểm tra**

**Câu 1.** Có thể inject một generated blocking stub vào Spring singleton service và gọi từ nhiều request thread không?

*Đáp án:* Có. Generated stub bất biến và được thiết kế để chia sẻ đồng thời. Mỗi lần gọi tạo RPC call riêng; vẫn cần deadline và mô hình executor phù hợp.

**Câu 2.** withDeadlineAfter có sửa deadline của stub gốc không?

*Đáp án:* Không. Nó trả về một stub mới với CallOptions mới; stub gốc không đổi. Giữ stub dẫn xuất trong biến cục bộ của call.

**Câu 3.** Vì sao không nên tạo ManagedChannel cho mỗi request?

*Đáp án:* Channel là tài nguyên transport có thể tái sử dụng đồng thời. Tạo liên tục làm tăng kết nối, thread và chi phí khởi tạo; channel nên được quản lý theo lifecycle của ứng dụng/client.

**Câu 4.** Có thể cho nhiều thread cùng gọi onNext trên một request StreamObserver không?

*Đáp án:* Không nên giả định observer thread-safe. Phải serialize các lời gọi trên cùng observer bằng một writer tuần tự hoặc cơ chế đồng bộ phù hợp.

**Câu 5.** Protobuf message và Builder khác nhau thế nào về chia sẻ giữa thread?

*Đáp án:* Message đã build là immutable và có thể chia sẻ để đọc; Builder mutable nên không chia sẻ đồng thời nếu không đồng bộ.

Generated stub thread-safe giúp một client Spring gRPC dùng chung stub và channel cho nhiều request mà không phải khóa toàn bộ lời gọi. Hãy giữ cấu hình stub bất biến, tạo CallOptions riêng theo từng call, quản lý observer/stream state theo đúng concurrency contract và đóng channel theo application lifecycle; khi đó tính đồng thời của client rõ ràng và dễ kiểm thử.
