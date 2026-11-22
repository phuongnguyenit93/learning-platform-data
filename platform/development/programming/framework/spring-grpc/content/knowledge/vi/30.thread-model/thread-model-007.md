# Callback thread trong async stub

Generated asynchronous stub của gRPC Java trả kết quả qua các callback của `StreamObserver`. Những callback này không chạy trên thread đã gọi stub theo một cam kết cố định; gRPC dispatch chúng qua executor dành cho application callback. Vì vậy, `onNext`, `onError` và `onCompleted` phải thực hiện nhanh, không chặn thread và không giả định thread identity.

Trong Spring gRPC, stub và channel thường được chia sẻ giữa nhiều request. Callback của nhiều RPC có thể chạy đồng thời, nên state dùng chung cần concurrency control. Nếu callback cần truy vấn database, gọi dịch vụ blocking hoặc xử lý CPU nặng, hãy chuyển phần việc đó sang executor ứng dụng có giới hạn.

## 1. Async stub gọi callback ở đâu?

```java
stub.getProduct(request, new StreamObserver<>() {
    @Override
    public void onNext(Product response) {
        handleResponse(response);
    }

    @Override
    public void onError(Throwable error) {
        handleFailure(error);
    }

    @Override
    public void onCompleted() {
        handleCompletion();
    }
});
```

Lời gọi trên khởi chạy RPC rồi trả quyền điều khiển cho caller. Khi response hoặc lỗi đến, gRPC gọi observer trên executor dành cho application callback. Nếu không cấu hình executor riêng, gRPC sử dụng executor mặc định do runtime quản lý.

Không nên dựa vào giả định callback luôn chạy trên thread gọi stub, mọi RPC dùng chung một thread, callback có thread name cố định hoặc callback hoàn tất trước khi method gọi stub trả về. Với một RPC, callback tuân theo lifecycle của call; nhiều RPC khác nhau có thể được xử lý đồng thời trên các thread khác nhau.

## 2. Phân biệt transport thread và callback executor

| Thành phần | Vai trò | Cách sử dụng |
| --- | --- | --- |
| Transport/event-loop thread | Xử lý I/O và sự kiện transport | Không chạy logic blocking hoặc nghiệp vụ nặng |
| gRPC callback executor | Dispatch callback cho application | Callback ngắn, không chặn, không giữ lock lâu |
| Application executor | Chạy nghiệp vụ, I/O blocking hoặc CPU work theo giới hạn | Có queue/concurrency policy và lifecycle riêng |

Với gRPC Java, channel builder có thể nhận executor cho application callback. Server builder cũng có cơ chế executor cho callback phía server. Nếu không cấu hình, gRPC chọn executor mặc định. Không nên gọi mọi callback thread là Netty event-loop thread; loại transport và cấu hình executor quyết định chi tiết thực thi.

Đặc biệt, `directExecutor()` yêu cầu gRPC chạy callback trực tiếp thay vì dispatch qua executor riêng. Callback khi đó có thể chạy ngay trên thread đang thực hiện thao tác gRPC hoặc thread dispatch hiện tại; một callback blocking có thể giữ luôn thread đó và ảnh hưởng transport/call khác. Chỉ dùng direct executor khi callback rất ngắn, đã hiểu rõ call path và có kiểm thử tải phù hợp.

Một callback nên làm việc ngắn như kiểm tra status, hoàn tất future, cập nhật state per-call hoặc đưa task sang application executor. Truy vấn database đồng bộ, gọi HTTP blocking, chờ lock lâu hoặc chạy thuật toán CPU nặng trong callback có thể làm cạn callback pool và khiến RPC khác chậm theo.

## 3. Cấu hình callback executor cho channel

Có thể cung cấp executor riêng khi tạo channel:

```java
Executor callbackExecutor = grpcCallbackExecutor;

ManagedChannel channel = ManagedChannelBuilder
        .forAddress("catalog.internal", 9090)
        .useTransportSecurity()
        .executor(callbackExecutor)
        .build();

CatalogServiceGrpc.CatalogServiceStub stub =
        CatalogServiceGrpc.newStub(channel);
```

Trong ví dụ, `grpcCallbackExecutor` là executor do ứng dụng quản lý và inject vào cấu hình client. Với Spring, có thể khai báo executor bằng bean và cấu hình thread name, concurrency limit, queue capacity, metrics cùng shutdown lifecycle theo quy ước của ứng dụng.

Chỉ cấu hình callback executor khi đã có lý do vận hành rõ ràng. Executor quá nhỏ khiến callback xếp hàng; executor quá lớn làm tăng context switching và áp lực bộ nhớ. Queue không giới hạn có thể biến quá tải thành độ trễ tăng liên tục. Theo dõi active threads, queue depth, task rejection và callback duration để điều chỉnh.

Nếu dùng executor riêng cho channel, xác định rõ ai sở hữu nó. Ứng dụng thường phải shutdown executor do mình tạo sau khi channel ngừng nhận call và callback còn lại đã được xử lý. Không shutdown executor dùng chung khi một client bean đơn lẻ kết thúc nếu các channel khác còn sử dụng.

## 4. Callback phải ngắn và không blocking

Ví dụ không nên làm:

```java
stub.getProduct(request, new StreamObserver<>() {
    @Override
    public void onNext(Product response) {
        // Không nên: callback bị giữ trong lúc chờ database.
        inventoryRepository.loadByProductId(response.getId());
        updateSearchIndex(response);
    }

    @Override
    public void onError(Throwable error) {
        log.error("RPC failed", error);
    }

    @Override
    public void onCompleted() {
    }
});
```

Nếu database hoặc search index chậm, callback executor bị chiếm trong suốt thời gian chờ. Khi nhiều RPC hoàn tất cùng lúc, các callback khác phải chờ thread rảnh.

Callback nên chuyển dữ liệu sang application executor:

```java
stub.getProduct(request, new StreamObserver<>() {
    @Override
    public void onNext(Product response) {
        applicationExecutor.execute(() -> {
            inventoryRepository.loadByProductId(response.getId());
            updateSearchIndex(response);
        });
    }

    @Override
    public void onError(Throwable error) {
        handleRpcFailure(error);
    }

    @Override
    public void onCompleted() {
        markRpcCompleted();
    }
});
```

Đây là phác thảo cho trường hợp unary. Trong production, cần xác định task có thể bị từ chối khi executor quá tải hay không, xử lý rejection, giới hạn queue và giữ thứ tự nếu các bước phụ thuộc nhau. Không chuyển một stream lớn vào queue không giới hạn; cần backpressure hoặc giới hạn số message đang chờ xử lý.

Nếu application executor từ chối task, hãy xử lý lỗi tại callback theo policy của use case. Đừng để exception từ lời gọi submit thoát ra ngoài callback một cách vô tình; cũng đừng âm thầm bỏ mất message.

## 5. Dùng future để tách callback khỏi xử lý tiếp theo

Với unary RPC, có thể hoàn tất một CompletableFuture trong callback rồi dùng async continuation trên application executor:

```java
public CompletableFuture<ProductView> getProductAsync(String productId) {
    GetProductRequest request = GetProductRequest.newBuilder()
            .setProductId(productId)
            .build();

    CompletableFuture<Product> response = new CompletableFuture<>();

    stub.getProduct(request, new StreamObserver<>() {
        @Override
        public void onNext(Product value) {
            response.complete(value);
        }

        @Override
        public void onError(Throwable error) {
            response.completeExceptionally(error);
        }

        @Override
        public void onCompleted() {
            // Unary response đã được chuyển vào future qua onNext.
        }
    });

    return response.thenApplyAsync(
            this::toView,
            applicationExecutor);
}
```

Callback chỉ hoàn tất future; mapping chạy trên application executor. Nếu mapping có thể lỗi, future kết quả sẽ hoàn tất exceptional và caller có thể xử lý bằng `exceptionally` hoặc `handle`. Với unary RPC, thông thường có tối đa một `onNext` trước `onCompleted`; với streaming, cần mô hình hóa nhiều message thay vì dùng một future đơn cho toàn bộ dữ liệu.

Không dùng `thenApply` nếu mapping có thể blocking và bạn không muốn chạy nó ngay trên thread hoàn tất future. Dùng `thenApplyAsync` với executor được chọn rõ ràng để giữ callback thread nhẹ.

## 6. Giữ gRPC Context khi chuyển sang executor khác

gRPC Context mang dữ liệu theo call như deadline, cancellation và thông tin được interceptor gắn vào. Context hiện hành trong callback không tự động được truyền qua mọi executor tùy chỉnh. Khi cần giữ context, chụp context ở callback và bọc task:

```java
@Override
public void onNext(Product response) {
    io.grpc.Context captured = io.grpc.Context.current();
    applicationExecutor.execute(captured.wrap(() -> {
        processProduct(response);
    }));
}
```

`Context.wrap` thiết lập context đã chụp trong lúc task chạy rồi khôi phục context trước đó sau khi task kết thúc. Cách này hữu ích khi `processProduct` cần đọc correlation ID hoặc deadline từ gRPC Context.

Không lưu context vào field mutable của singleton service. Mỗi callback/RPC phải giữ context riêng. Nếu công việc tiếp tục sau khi RPC đã kết thúc, context và deadline ban đầu có thể không còn phù hợp; hãy truyền dữ liệu cần thiết thành input rõ ràng và xác định timeout mới cho công việc nền.

OpenTelemetry Context là một context riêng. Nếu ứng dụng dùng tracing và chuyển sang executor tùy chỉnh, cần propagate OpenTelemetry Context bằng wrapper/executor instrumentation tương ứng; gRPC Context không tự động thay thế việc đó.

## 7. Streaming callback và thứ tự message

Với server streaming, `onNext` có thể được gọi nhiều lần trước terminal callback. Với client streaming hoặc bidi, ứng dụng còn gửi request qua `StreamObserver` được trả về từ stub. Cần phân biệt:

- Observer nhận response: gRPC gọi `onNext`, `onError` hoặc `onCompleted`.
- Request observer gửi message: ứng dụng gọi `onNext` và cuối cùng gọi `onCompleted` hoặc `onError`.

Đừng giả định callback của các RPC khác nhau có chung thứ tự toàn cục. Với cùng một stream, xử lý message phải giữ đúng thứ tự nghiệp vụ nếu thứ tự có ý nghĩa. Nếu submit từng message sang một pool nhiều thread, các task có thể hoàn tất sai thứ tự; dùng một executor tuần tự theo stream hoặc đánh số sequence và xử lý reorder có giới hạn.

Không để callback `onNext` đưa mọi message vào một queue không giới hạn. Khi producer nhanh hơn consumer, bộ nhớ tăng cho tới khi process gặp áp lực. Cần giới hạn số message đang chờ, điều phối demand/flow control khi API hỗ trợ và hủy stream nếu ứng dụng không thể tiếp tục an toàn.

## 8. Deadline, cancellation và lỗi trong callback

Async call kết thúc qua một terminal callback:

| Kết quả | Callback phía client | Việc cần làm |
| --- | --- | --- |
| Thành công | `onCompleted` sau response message | Giải phóng state per-call |
| Server trả lỗi | `onError` | Phân loại gRPC status, không retry mù quáng |
| Deadline hết hạn | Thường đi qua `onError` với `DEADLINE_EXCEEDED` | Dừng xử lý phụ thuộc call, ghi nhận timeout |
| Call bị hủy | Thường đi qua `onError` với `CANCELLED` | Ngừng công việc không còn cần thiết |

Không chờ đồng bộ callback bằng `CountDownLatch.await()` trên callback thread; điều đó có thể làm cạn executor hoặc gây deadlock nếu callback cần chính executor đó để hoàn tất.

Callback implementation không nên ném exception ra ngoài. Bắt lỗi phát sinh trong code callback, chuyển sang future/error handler của ứng dụng và bảo đảm không phát terminal signal lần hai. `onError` và `onCompleted` là terminal; sau đó không xử lý thêm message như thể call vẫn hoạt động.

Khi deadline/cancellation xảy ra, task đã được chuyển sang application executor có thể vẫn đang chạy. Nếu task không còn cần thiết, dùng cancellation token hoặc cờ per-call để dừng công việc; đừng giả định hủy RPC tự động dừng mọi tác vụ Java mà ứng dụng đã submit.

## 9. Quản lý executor trong Spring và kiểm thử

Trong Spring, callback executor và application executor có thể là hai bean riêng:

```java
@Configuration
public class GrpcExecutionConfiguration {

    @Bean(destroyMethod = "shutdown")
    ExecutorService grpcCallbackExecutor() {
        return Executors.newFixedThreadPool(8);
    }

    @Bean(destroyMethod = "shutdown")
    ExecutorService grpcApplicationExecutor() {
        return Executors.newFixedThreadPool(12);
    }
}
```

Đây là ví dụ đơn giản để minh họa ownership. Cấu hình production cần cân nhắc pool có giới hạn queue, chính sách overload, metrics và shutdown có timeout; không sao chép kích thước thread cố định nếu chưa đo tải. Nếu Spring gRPC hoặc auto-configuration đã quản lý callback executor, hãy dùng đúng extension point và tránh tạo pool trùng lặp.

Kiểm thử nên bao gồm:

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| Unary thành công | Callback nhận response rồi terminal completion |
| RPC lỗi | `onError` nhận status và không gọi completion lần hai |
| Callback thread | Code không phụ thuộc thread identity cố định |
| Callback chậm | Application executor xử lý phần blocking, callback pool không bị giữ lâu |
| Executor quá tải | Rejection được xử lý, không âm thầm mất message |
| Context propagation | Correlation/deadline cần thiết có mặt trong task đã bọc |
| Streaming | Thứ tự message được giữ và queue có giới hạn |
| Deadline/cancel | Task phụ thuộc call được dừng hoặc đánh dấu hủy |
| Shutdown | Channel ngừng nhận call, callback được drain theo policy và executor được đóng đúng thứ tự |

Có thể dùng in-process channel/server và executor kiểm soát được trong test. Để xác minh thread dispatch, ghi thread name trong test/log chẩn đoán; không assert một tên thread cố định như contract của gRPC.

## 10. Checklist callback thread

- [ ] Không giả định callback chạy trên thread gọi stub hoặc một thread có tên cố định.
- [ ] Phân biệt transport thread, gRPC callback executor và application executor.
- [ ] Callback ngắn, không thực hiện blocking I/O hoặc chờ lock lâu.
- [ ] Công việc nặng được chuyển sang executor ứng dụng có giới hạn.
- [ ] Xử lý task rejection và không bỏ message âm thầm.
- [ ] Giữ thứ tự xử lý khi streaming yêu cầu thứ tự.
- [ ] Propagate gRPC Context và OpenTelemetry Context riêng khi chuyển executor.
- [ ] Xử lý `onError`/`onCompleted` như terminal callback.
- [ ] Không chờ callback đồng bộ trên callback thread.
- [ ] Task nền có cancellation policy riêng khi RPC deadline/cancel.
- [ ] Executor và channel có ownership/lifecycle rõ trong Spring.
- [ ] Có test success, failure, overload, streaming, context và shutdown.

**Tự kiểm tra**

**Câu 1.** Callback của async stub có luôn chạy trên thread gọi stub không?

*Đáp án:* Không. gRPC dispatch callback qua application callback executor; executor mặc định hoặc executor cấu hình quyết định thread thực thi. Code không nên dựa vào thread identity.

**Câu 2.** Vì sao không nên truy vấn database blocking ngay trong `onNext`?

*Đáp án:* Callback executor bị chiếm trong lúc chờ I/O, làm callback của các RPC khác phải chờ. Chuyển công việc blocking sang application executor có giới hạn.

**Câu 3.** Hai executor callback và application khác nhau ở đâu?

*Đáp án:* Callback executor chạy listener/observer do gRPC dispatch; application executor chạy công việc nghiệp vụ mà callback chuyển tiếp, như I/O blocking hoặc CPU work.

**Câu 4.** Vì sao cần bọc gRPC Context khi submit task?

*Đáp án:* Context không tự động đi qua mọi executor tùy chỉnh. Bọc task giúp giữ deadline, correlation hoặc dữ liệu call-scoped trong lúc task chạy.

**Câu 5.** Khi deadline hết hạn, tác vụ đã submit sang application executor có tự dừng không?

*Đáp án:* Không nhất thiết. RPC bị hủy không tự động dừng mọi tác vụ Java đã submit; ứng dụng cần cancellation token/cờ per-call và kiểm tra trước hoặc trong quá trình xử lý.

Callback thread trong async stub là một phần quan trọng của mô hình đồng thời: callback phải nhẹ, không phụ thuộc thread identity và không giữ tài nguyên chờ lâu. Tách callback executor khỏi application work, propagate context có chủ đích, giới hạn queue cho streaming và xử lý cancellation rõ ràng sẽ giúp Spring gRPC duy trì độ trễ ổn định khi nhiều RPC chạy đồng thời.
