# Ghép nhiều lời gọi I/O bằng CompletableFuture và executor riêng

Đây là bài thực hành trong nhóm **Thực hành**: kết hợp các lời gọi I/O độc lập, quản lý executor và tổng hợp kết quả bằng các API hiện hành của Java.

## 1. Bài toán: gọi nhiều dịch vụ độc lập rồi tổng hợp kết quả

Một màn hình tổng quan có thể cần ba nguồn dữ liệu: hồ sơ người dùng, danh sách đơn hàng và cấu hình tính năng. Nếu lần lượt gọi từng dịch vụ và đợi xong mới gọi dịch vụ tiếp theo, tổng thời gian chờ gần bằng tổng thời gian của cả ba lời gọi.

Nếu các lời gọi độc lập, có thể **khởi chạy tất cả trước, sau đó ghép các kết quả**. Đây là mô hình fan-out/fan-in:

~~~text
                    Request tổng hợp
                           |
               +-----------+-----------+
               |           |           |
               v           v           v
            Profile      Orders       Flags
             I/O           I/O         I/O
               |           |           |
               +-----------+-----------+
                           |
                           v
                   Tổng hợp Dashboard
                           |
                           v
                       Response
~~~

**CompletableFuture** biểu diễn kết quả sẽ hoàn tất trong tương lai và cho phép nối các bước xử lý khi kết quả sẵn sàng. **Executor riêng** xác định nơi chạy những tác vụ bất đồng bộ/dependent task cần được điều phối, giúp ứng dụng kiểm soát tài nguyên và tránh vô tình đưa workload vào common pool mặc định.

Bài tập trung vào cách gọi nhiều I/O độc lập, đặt timeout, ghép kết quả, xử lý lỗi, giới hạn tải và quản lý lifecycle. Các API được chọn còn được hỗ trợ trong Java hiện hành.

## 2. Xác định dependency trước khi ghép future

Không phải mọi lời gọi đều có thể chạy song song. Trước tiên, vẽ dependency giữa chúng:

| Tình huống | Cách ghép |
| --- | --- |
| Lấy profile, orders và flags độc lập | Khởi chạy cả ba rồi dùng **allOf** |
| Lấy profile, sau đó dùng profile ID để gọi detail | Dùng **thenCompose** |
| Hai nguồn độc lập, sau đó kết hợp hai giá trị | Dùng **thenCombine** |
| Chỉ cần kết quả đầu tiên hoàn tất | Cân nhắc **anyOf** hoặc **applyToEither** |
| Một nguồn tùy chọn có thể thiếu | Xử lý lỗi riêng bằng **handle** hoặc **exceptionally** trước khi tổng hợp |

Ví dụ phụ thuộc:

~~~text
GET /profile
      |
      v
đọc profile.id
      |
      v
GET /profile/{id}/preferences
~~~

Lời gọi thứ hai cần kết quả của lời gọi thứ nhất nên không thể bắt đầu trước khi có ID. Dùng thenCompose để nối hai stage mà không tạo CompletableFuture lồng nhau.

Ngược lại, nếu orders không phụ thuộc profile, hãy bắt đầu hai request ngay khi có đủ input. **Chỉ song song hóa phần thật sự độc lập**; việc chạy đồng thời các bước có dependency sẽ dẫn đến dữ liệu thiếu hoặc logic sai.

## 3. Phân biệt CompletableFuture, HttpClient và Executor

Ba thành phần có vai trò khác nhau:

- **CompletableFuture<T>:** biểu diễn kết quả bất đồng bộ kiểu T, hỗ trợ thenApply, thenCompose, allOf, handle và các stage khác.
- **HttpClient:** gửi HTTP request đồng bộ bằng send hoặc bất đồng bộ bằng sendAsync. sendAsync trả về CompletableFuture của HttpResponse.
- **Executor:** điều phối các tác vụ chạy bất đồng bộ; executor có thể là pool riêng, executor do ứng dụng quản lý hoặc executor được truyền trực tiếp cho một stage.

**CompletableFuture có từ Java 8 (Since 1.8).** Các API thenApplyAsync, thenComposeAsync, allOf và supplyAsync với Executor đều có trong Java 8.

**java.net.http.HttpClient có từ Java 11.** Vì vậy, chương trình HTTP hoàn chỉnh ở bài này chạy trên Java 17+. Nếu ứng dụng vẫn chạy Java 8, vẫn có thể dùng CompletableFuture với một client/DAO tương thích Java 8 và đưa các lời gọi blocking vào executor riêng. Phần cuối có chương trình Java 8 kiểm chứng chính mẫu fan-out/fan-in bằng file I/O.

## 4. Vì sao không để mọi async task chạy trên common pool?

Theo hợp đồng của CompletableFuture, các phương thức async **không truyền Executor** thường dùng ForkJoinPool.commonPool(). Ví dụ:

~~~java
CompletableFuture.supplyAsync(() -> loadProfile());
~~~

Và:

~~~java
future.thenApplyAsync(this::parseResponse);
~~~

Cả hai ví dụ trên không chỉ định executor. Chúng có thể chia sẻ common pool với những công việc không liên quan khác trong cùng JVM.

Với ứng dụng gọi nhiều dịch vụ I/O, nên xác định rõ:

~~~java
ExecutorService ioExecutor = Executors.newFixedThreadPool(8);
ExecutorService cpuExecutor = Executors.newFixedThreadPool(2);
~~~

- **ioExecutor:** dành cho các tác vụ I/O blocking hoặc executor được cấu hình cho HttpClient.
- **cpuExecutor:** dành cho parse/transform CPU-intensive nếu việc xử lý response đáng kể.
- **Không dùng chung một pool nhỏ cho mọi việc** nếu có nguy cơ các task chờ lẫn nhau hoặc chiếm hết worker.

Với HttpClient, cấu hình executor qua HttpClient.Builder.executor(...). Javadoc mô tả executor này được dùng cho asynchronous và dependent tasks. Nó không phải lời hứa rằng mọi thao tác socket đều chạy trực tiếp trên thread của pool, cũng không phải giới hạn số request đang bay tới server.

## 5. Tái sử dụng một HttpClient theo lifecycle

HttpClient là đối tượng immutable sau khi được tạo và được thiết kế để gửi nhiều request. Một client thường quản lý connection pool riêng để tái sử dụng kết nối.

**Không tạo HttpClient mới cho từng request.** Việc đó có thể làm mất lợi ích tái sử dụng connection và tăng chi phí thiết lập kết nối.

Tạo một client dùng chung cho service/component:

~~~java
HttpClient client = HttpClient.newBuilder()
        .executor(ioExecutor)
        .connectTimeout(Duration.ofSeconds(2))
        .build();
~~~

**connectTimeout** giới hạn thời gian thiết lập kết nối mới. Nó không thay thế timeout cho toàn bộ request/response.

HttpClient.Builder.executor nhận Executor dùng cho các tác vụ bất đồng bộ và dependent tasks. Truyền executor do ứng dụng sở hữu giúp xác định rõ nơi thực hiện các tác vụ đó.

Với Java 11–20, HttpClient chưa implement AutoCloseable; phải quản lý executor bên ngoài và đợi các request hoàn tất trước khi shutdown executor. Từ Java 21, HttpClient implement AutoCloseable và có close()/shutdown()/awaitTermination() để đóng client theo lifecycle. Không đóng client khi vẫn còn request đang cần hoàn tất.

## 6. Khởi chạy request bất đồng bộ bằng sendAsync

Một HTTP request cơ bản:

~~~java
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.test/profile"))
        .timeout(Duration.ofSeconds(4))
        .header("Accept", "application/json")
        .GET()
        .build();
~~~

Gửi bất đồng bộ:

~~~java
CompletableFuture<HttpResponse<String>> responseFuture =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
~~~

sendAsync trả về ngay một CompletableFuture; khi response sẵn sàng, future hoàn tất. Ứng dụng có thể kết hợp nó với các future khác mà không cần block thread điều phối tại thời điểm gửi.

**Đừng gọi get() sau từng sendAsync** rồi mới gửi request kế tiếp. Cách đó lại biến fan-out thành tuần tự:

~~~java
// Không nên: đợi request đầu xong mới gửi request sau.
HttpResponse<String> profile =
        client.sendAsync(profileRequest, handler).join();
HttpResponse<String> orders =
        client.sendAsync(ordersRequest, handler).join();
~~~

Hãy tạo cả ba future trước:

~~~java
CompletableFuture<HttpResponse<String>> profile =
        client.sendAsync(profileRequest, handler);
CompletableFuture<HttpResponse<String>> orders =
        client.sendAsync(ordersRequest, handler);
CompletableFuture<HttpResponse<String>> flags =
        client.sendAsync(flagsRequest, handler);
~~~

Đến đây, các request độc lập đã được khởi chạy. Chỉ chờ kết quả tại điểm fan-in hoặc ở boundary đồng bộ của ứng dụng.

## 7. Ghép các request bằng allOf

**CompletableFuture.allOf(...)** tạo một future hoàn tất khi tất cả future truyền vào hoàn tất:

~~~java
CompletableFuture<Void> all =
        CompletableFuture.allOf(profile, orders, flags);
~~~

allOf trả về CompletableFuture<Void>, **không trả về List kết quả**. Sau khi all hoàn tất bình thường, đọc từng future:

~~~java
CompletableFuture<Dashboard> dashboard =
        CompletableFuture.allOf(profile, orders, flags)
                .thenApplyAsync(ignored ->
                        new Dashboard(
                                profile.join(),
                                orders.join(),
                                flags.join()),
                        cpuExecutor);
~~~

Trong ví dụ này, các join chạy sau khi allOf đã hoàn tất bình thường nên không phải chờ I/O lần nữa. Nếu một future thất bại, allOf cũng hoàn tất exceptional; callback thenApplyAsync không chạy như một bước thành công.

**Không dùng allOf rồi giả định nó tự thu thập kết quả.** Nếu muốn một list, tự tạo list từ các future sau khi allOf hoàn tất hoặc dùng một cấu trúc kết quả có kiểu rõ ràng.

## 8. Chọn đúng method trong CompletionStage

| Method | Khi nào dùng |
| --- | --- |
| **thenApply / thenApplyAsync** | Biến đổi một kết quả T thành U |
| **thenCompose / thenComposeAsync** | Hàm tiếp theo cũng trả CompletionStage; nối stage phụ thuộc |
| **thenCombine / thenCombineAsync** | Ghép kết quả của hai stage độc lập |
| **allOf** | Chờ nhiều future hoàn tất |
| **anyOf** | Hoàn tất khi một future bất kỳ hoàn tất |
| **thenAccept** | Nhận kết quả nhưng không tạo giá trị trả về |
| **thenRun** | Chạy hành động không cần nhận kết quả trước |
| **handle / handleAsync** | Xử lý cả kết quả lẫn exception |
| **whenComplete / whenCompleteAsync** | Quan sát kết quả/lỗi, thường dùng logging/metrics mà giữ nguyên trạng thái hoàn tất |

**thenApply** không tự biến một lời gọi blocking thành async. Nó chỉ nối phép biến đổi sau khi stage trước hoàn tất.

**thenApplyAsync** điều phối callback trên executor mặc định hoặc executor được truyền vào. Nếu callback parse JSON lớn, transform nhiều dữ liệu hoặc chạy logic CPU-intensive, truyền cpuExecutor tách biệt.

**thenCompose** phù hợp với lời gọi phụ thuộc:

~~~java
CompletableFuture<Preferences> preferences =
        fetchProfile()
                .thenCompose(profile ->
                        fetchPreferences(profile.id()));
~~~

Nếu dùng thenApply ở đây, kết quả sẽ là CompletableFuture<CompletableFuture<Preferences>>; thenCompose làm phẳng stage lồng nhau.

## 9. Luôn chỉ định executor cho callback async quan trọng

Các callback non-async như thenApply có thể chạy trên thread hoàn tất future trước đó hoặc thread gọi completion. Vì vậy, callback phải ngắn và không block.

Các callback async không truyền Executor dùng default async executor, thường là ForkJoinPool.commonPool():

~~~java
responseFuture.thenApplyAsync(this::parseJson);
~~~

Để kiểm soát rõ:

~~~java
responseFuture.thenApplyAsync(this::parseJson, cpuExecutor);
~~~

Với HttpClient, executor được truyền vào builder phục vụ async/dependent tasks của client. Tuy nhiên, callback ứng dụng có thể chỉ định một executor khác cho parse hoặc aggregate.

**Không gọi blocking database/network trong callback chạy trên common pool** nếu có thể tránh. Nếu buộc phải gọi API blocking, chuyển nó sang executor chuyên dụng với giới hạn worker/queue rõ ràng.

## 10. Phân biệt timeout kết nối, timeout request và deadline tổng

Có ba mức timeout thường cần:

1. **Connect timeout:** giới hạn thời gian thiết lập kết nối mới.
2. **Request timeout:** giới hạn thời gian thực hiện một HTTP request/response.
3. **Overall deadline:** giới hạn thời gian toàn bộ fan-out/fan-in được phép tiêu tốn.

Ví dụ HttpClient:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .executor(ioExecutor)
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(4))
        .GET()
        .build();
~~~

Nếu một request không nhận được response trong khoảng request timeout, sendAsync hoàn tất exceptional với HttpTimeoutException.

Để đặt deadline cho aggregate, có thể chờ có giới hạn:

~~~java
Dashboard result = dashboardFuture.get(6, TimeUnit.SECONDS);
~~~

Đây là cách tương thích Java 8. Từ Java 9, CompletableFuture có **orTimeout** và **completeOnTimeout**; chúng không thuộc Java 8.

**Timeout ở thread gọi get() không tự động dừng các request con.** Nếu deadline tổng hết hạn, ứng dụng cần áp dụng policy cancel/cleanup cho các future còn chạy.

## 11. HTTP status 4xx/5xx không tự động làm future thất bại

sendAsync có thể hoàn tất bình thường với HttpResponse ngay cả khi server trả HTTP 404, 429 hoặc 503. Đây là response HTTP hợp lệ ở tầng transport.

Do đó, phải kiểm tra status:

~~~java
static String requireSuccess(HttpResponse<String> response) {
    int status = response.statusCode();
    if (status < 200 || status >= 300) {
        throw new CompletionException(
                new IllegalStateException("HTTP status " + status));
    }
    return response.body();
}
~~~

Nối bước kiểm tra:

~~~java
CompletableFuture<String> body =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .thenApplyAsync(
                        MyClient::requireSuccess,
                        parseExecutor);
~~~

Nếu muốn trả 404 như một kết quả nghiệp vụ (ví dụ profile chưa tồn tại), hãy mô hình hóa nó bằng kiểu kết quả rõ ràng thay vì biến mọi status thành exception.

**Tách transport error và business outcome:**

- DNS/connect/timeout/IO failure: request không lấy được response như mong đợi.
- HTTP 4xx/5xx: server đã trả response, nhưng status không thuộc nhóm success theo policy.
- Domain result như "không tìm thấy": có thể là trạng thái hợp lệ tùy API.

## 12. allOf và lỗi: required dependency khác optional dependency

Nếu cả ba nguồn đều bắt buộc, để lỗi truyền ra ngoài:

~~~java
CompletableFuture<Dashboard> required =
        CompletableFuture.allOf(profile, orders, flags)
                .thenApply(ignored ->
                        new Dashboard(
                                profile.join(),
                                orders.join(),
                                flags.join()));
~~~

Nếu một stage thất bại, aggregate sẽ exceptional. Không được trả một Dashboard thiếu dữ liệu rồi coi như thành công nếu nghiệp vụ yêu cầu đủ ba nguồn.

Nếu flags chỉ là nguồn tùy chọn, xử lý lỗi ngay ở stage đó:

~~~java
CompletableFuture<Optional<String>> optionalFlags =
        fetchFlags()
                .handleAsync((value, error) -> {
                    if (error == null) {
                        return Optional.of(value);
                    }
                    logOptionalFailure(error);
                    return Optional.empty();
                }, parseExecutor);
~~~

Sau đó ghép profile/orders bắt buộc với optionalFlags. Kiểu Optional phân biệt rõ "không có giá trị" với chuỗi rỗng.

**Không dùng exceptionally(error -> null) một cách vô thức.** Null có thể biến lỗi hạ tầng thành dữ liệu hợp lệ giả và khiến lỗi chỉ xuất hiện ở bước sau.

## 13. Thu thập kết quả từng phần khi có nguồn tùy chọn

Nếu cần hiển thị dữ liệu còn lại dù một nguồn tùy chọn lỗi, tạo một kiểu kết quả có cả value và error:

~~~java
final class Outcome<T> {
    final T value;
    final Throwable error;

    Outcome(T value, Throwable error) {
        this.value = value;
        this.error = error;
    }

    boolean succeeded() {
        return error == null;
    }
}
~~~

Tạo outcome:

~~~java
CompletableFuture<Outcome<String>> flags =
        fetchFlags().handle((value, error) ->
                new Outcome<String>(
                        value,
                        error == null ? null : unwrap(error)));
~~~

Khi tất cả outcome hoàn tất, aggregate có thể quyết định hiển thị cảnh báo, bỏ phần flags hoặc dùng fallback đã được nghiệp vụ phê duyệt.

**Giữ lại thông tin lỗi để quan sát.** Một fallback hợp lệ nên có metric/log cho biết nguồn nào đang lỗi và trong bao lâu; đừng che lỗi vĩnh viễn bằng một giá trị mặc định.

Với nguồn bắt buộc, không chuyển exception thành Outcome success trừ khi tầng nghiệp vụ đã có một policy rõ ràng để xử lý kết quả thiếu.

## 14. whenComplete, handle và exceptionally khác nhau

- **whenComplete:** quan sát kết quả/error; thường dùng metrics hoặc logging; stage trả về vẫn giữ kết quả/lỗi ban đầu, trừ khi callback tự ném lỗi.
- **handle:** luôn nhận cả value và error, rồi tạo kết quả mới. Dùng khi thật sự cần chuyển đổi cả hai trường hợp.
- **exceptionally:** chỉ chạy khi stage thất bại và có thể cung cấp fallback value.
- **exceptionallyCompose:** có từ Java 12, dùng khi recovery cần trả một stage khác; không dùng nếu target Java 8.

Ví dụ logging:

~~~java
CompletableFuture<String> observed =
        requestFuture.whenComplete((value, error) -> {
            if (error != null) {
                recordFailure(unwrap(error));
            }
        });
~~~

Nếu recordFailure có thể block hoặc ghi log chậm, cân nhắc callback async với executor riêng. Không để một callback metrics chậm chiếm thread hoàn tất response.

**Đừng log token, header Authorization, dữ liệu cá nhân hoặc toàn bộ response nhạy cảm.** Log correlation ID, endpoint category, status, duration và loại lỗi đủ để chẩn đoán.

## 15. Cancellation là best effort, không phải rollback

Nếu deadline tổng hết hạn hoặc một dependency bắt buộc thất bại, có thể yêu cầu hủy các request còn lại:

~~~java
profile.cancel(true);
orders.cancel(true);
flags.cancel(true);
~~~

Với CompletableFuture nói chung, cancel được biểu diễn như exceptional completion; nó không có quyền điều khiển trực tiếp mọi computation phía sau.

Với future do HttpClient.sendAsync trả về, implementation JDK có thể cố gắng hủy HTTP exchange khi gọi cancel(true), nhưng **không bảo đảm server chưa nhận hoặc chưa xử lý request**. Tài nguyên cũng có thể được giải phóng bất đồng bộ.

Vì vậy:

- Không coi cancel là rollback giao dịch phía server.
- Không retry POST/payment/create chỉ vì caller đã timeout.
- Dùng idempotency key hoặc operation ID khi nghiệp vụ cần retry an toàn.
- Phân biệt "caller không còn chờ" với "remote side effect đã dừng".
- Đặt timeout ở cả client và service/dependency nếu có thể.

Nếu cần hủy toàn bộ fan-out khi một request bắt buộc lỗi, đăng ký policy rõ ràng bằng whenComplete và cancel các future còn lại. Nếu muốn partial result, đừng hủy các nguồn còn lại quá sớm.

## 16. Không chặn executor bằng get/join lồng nhau

Lỗi dễ gặp:

~~~java
CompletableFuture<Result> result =
        CompletableFuture.supplyAsync(() -> {
            // Không tốt: block một worker trong lúc chờ task khác.
            return anotherFuture.join();
        }, smallExecutor);
~~~

Nếu task đang chờ được submit vào chính pool nhỏ đó, toàn bộ worker có thể bị block và task cần thiết không có cơ hội chạy. Đây là một dạng thread starvation/deadlock.

Ưu tiên nối stage:

~~~java
CompletableFuture<Result> result =
        firstFuture.thenCompose(this::loadNextAsync);
~~~

**join sau allOf** trong bước aggregate là một trường hợp khác: khi allOf đã hoàn tất bình thường, các future con đã hoàn tất nên join không còn phải chờ I/O. Dù vậy, có thể giữ code gọn bằng cách đọc các giá trị trong callback đó.

Boundary đồng bộ ở main/request thread có thể dùng get(timeout), nhưng không nên block một worker của executor đang phải thực hiện chính future mà nó chờ.

## 17. Executor riêng và queue có giới hạn

Một ví dụ ThreadPoolExecutor cho tác vụ async/dependent:

~~~java
ThreadPoolExecutor ioExecutor = new ThreadPoolExecutor(
        8,
        8,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<Runnable>(128),
        threadFactory,
        new ThreadPoolExecutor.AbortPolicy());
~~~

Các thông số cần quyết định theo workload:

- **Core/max workers:** số task có thể được executor thực thi đồng thời.
- **Queue capacity:** số task có thể chờ trước khi hệ thống bão hòa.
- **ThreadFactory:** tên thread, daemon policy và context cần thiết.
- **RejectedExecutionHandler:** ứng xử khi queue đầy hoặc executor đã shutdown.

**newFixedThreadPool(n)** dùng số worker cố định nhưng shared queue không giới hạn dung lượng. Nếu submit nhanh hơn tốc độ xử lý, queue có thể tăng và tiêu thụ heap.

Bounded queue giúp giới hạn backlog. AbortPolicy ném RejectedExecutionException để caller nhận biết hệ thống không nhận thêm task. CallerRunsPolicy có thể tạo backpressure bằng cách cho thread submit chạy task; chỉ chọn nếu việc làm chậm caller là an toàn.

**Executor queue không đồng nghĩa giới hạn số HTTP request đang in-flight.** HttpClient có transport/connection management riêng. Nếu API ngoài chỉ cho phép tối đa N request đồng thời, hãy giới hạn ở boundary dependency bằng Semaphore, rate limiter hoặc bulkhead phù hợp.

## 18. Semaphore giới hạn số lời gọi tới dependency

Một ví dụ admission control không block thread chờ permit:

~~~java
Semaphore permits = new Semaphore(20);

if (!permits.tryAcquire()) {
    throw new RejectedExecutionException(
            "downstream concurrency limit reached");
}

CompletableFuture<HttpResponse<String>> response;
try {
    response = client.sendAsync(
            request,
            HttpResponse.BodyHandlers.ofString());
} catch (RuntimeException failure) {
    permits.release();
    throw failure;
}

response.whenComplete((value, error) -> permits.release());
~~~

Đoạn này là snippet cần client, request và Semaphore được tạo trong scope quản lý. Permit được giữ đến khi future response hoàn tất và được giải phóng trong cả trường hợp thành công/lỗi.

Nếu dùng streaming body handler, cần xác định thời điểm body thực sự được đọc/đóng trước khi giải phóng permit; future có thể hoàn tất khi stream đã được trao cho caller nhưng caller vẫn còn đọc body.

Giới hạn concurrency phải theo quota/connection/downstream capacity. Không đặt 20 chỉ vì ví dụ dùng 20; đo và cấu hình theo dependency thực tế.

## 19. Giữ mỗi request độc lập và tránh shared mutable state

Nhiều callback có thể chạy trên nhiều thread. Không sửa chung một ArrayList/HashMap hoặc object mutable không thread-safe từ các stage.

Ưu tiên:

- Truyền immutable request context qua tham số/stage.
- Mỗi request dùng dữ liệu riêng.
- Tổng hợp kết quả ở một stage cuối.
- Dùng concurrent collection/atomic primitive chỉ khi thật sự cần shared state.
- Không chia sẻ JDBC Connection đang được dùng đồng thời; lấy connection riêng từ DataSource/pool cho mỗi tác vụ và đóng đúng lifecycle.

**Đừng dựa vào ThreadLocal như thể mọi stage sẽ chạy cùng một thread.** Async continuation có thể chạy trên executor khác. Với tracing/security context, dùng cơ chế context propagation của framework hoặc truyền context tường minh; không sao chép secret vào log.

## 20. BodyHandler và kích thước response

Ví dụ trong bài dùng:

~~~java
HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
~~~

Cách này tiện khi response body vừa phải và cần xử lý như String. Body được đọc vào bộ nhớ; nhiều response lớn cùng lúc có thể làm heap tăng mạnh.

Với body lớn:

- Dùng BodyHandlers.ofFile để ghi response ra file.
- Dùng BodyHandlers.ofInputStream khi muốn tự quản lý streaming; luôn đóng stream.
- Dùng custom BodySubscriber nếu cần flow control/stream processing cụ thể.
- Đặt giới hạn kích thước response theo nghiệp vụ.
- Không giữ tất cả response body trong memory chỉ để chờ allOf nếu có thể xử lý/ghi từng phần an toàn.

Nếu dùng BodyHandlers.ofInputStream, phải đóng hoặc đọc stream đến hết để request/body resource hoàn tất. Không bỏ quên stream khi future đã trả response.

## 21. Retry và backoff khi nhiều dịch vụ cùng lỗi

Nếu nhiều dependency timeout cùng lúc, retry đồng loạt có thể tạo thêm một đợt tải lớn vào hệ thống đang quá tải.

Retry nên có:

- Số lần tối đa nhỏ và được cấu hình.
- Exponential backoff và jitter.
- Tổng deadline không vượt SLA của request cha.
- Phân loại lỗi retryable/non-retryable.
- Idempotency key cho operation có side effect.
- Circuit breaker/rate limit nếu dependency suy giảm kéo dài.
- Metric cho retry count và retry success.

Không dùng Thread.sleep trong callback trên I/O executor để chờ backoff. Dùng scheduler/delayed execution hoặc resilience library đã được kiểm chứng. CompletableFuture.delayedExecutor và orTimeout có từ Java 9; target Java 8 cần ScheduledExecutorService hoặc thư viện tương thích.

**Không retry HTTP 400/validation error một cách máy móc.** Không retry một lệnh ghi tiền/đặt hàng nếu chưa có idempotency contract.

## 22. Lifecycle: ai sở hữu client và executor?

Một service nên có lifecycle rõ ràng:

1. Tạo HttpClient một lần cho phạm vi service/application.
2. Tạo hoặc nhận executor được quản lý bởi application/container.
3. Mỗi request tạo các CompletableFuture mới, không tạo pool mới.
4. Khi shutdown, ngừng nhận request mới.
5. Đợi/cancel các request đang chạy theo policy.
6. Đóng body stream nếu có.
7. Đóng HttpClient trên Java 21+; trên Java 11–20, đợi request hoàn tất và quản lý executor được cung cấp.
8. Shutdown executor mà service sở hữu và await termination.

**Không shutdown executor ngay sau khi submit request.** Client vẫn có thể cần executor để chạy callback hoặc hoàn tất future.

Không shutdown executor được inject từ framework hoặc chia sẻ với component khác; chỉ owner mới chịu trách nhiệm đóng resource.

## 23. Java 21+: virtual threads là một lựa chọn cho blocking I/O

Java 21+ có virtual threads, phù hợp cho nhiều tác vụ dành phần lớn thời gian chờ I/O. Có thể viết blocking code theo thread-per-task:

~~~java
try (ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor()) {
    Future<Profile> profile =
            executor.submit(() -> loadProfileBlocking(id));
    Future<List<Order>> orders =
            executor.submit(() -> loadOrdersBlocking(id));

    Profile p = profile.get();
    List<Order> o = orders.get();
}
~~~

Virtual threads giúp tăng khả năng scale concurrency cho blocking I/O; **không làm CPU code chạy nhanh hơn** và không làm downstream tăng quota/connection. Không pool virtual threads như platform thread pool; mỗi task có thể có virtual thread riêng, còn giới hạn dependency dùng Semaphore/connection pool.

Nếu ứng dụng đã dùng HttpClient.sendAsync và CompletionStage, tiếp tục async pipeline là hợp lý. Tránh trộn một framework async với blocking code tùy tiện. Nếu blocking code đơn giản hơn và runtime Java 21+, virtual threads có thể là phương án dễ đọc hơn.

## 24. Chương trình Java 17+ hoàn chỉnh: fan-out HTTP, fan-in, lỗi và timeout

Chương trình dưới đây tạo HTTP server cục bộ trong cùng JVM, nên không cần Internet hoặc API key. Ba endpoint profile/orders/flags chờ nhau cùng được gọi, giúp xác minh các request được khởi chạy chồng lấp.

Chương trình dùng:

- **HttpClient.sendAsync** để gửi ba request độc lập.
- **ThreadPoolExecutor** riêng cho tác vụ async/dependent của HttpClient, queue giới hạn 32.
- **parseExecutor** riêng cho kiểm tra status và tổng hợp response.
- **CompletableFuture.allOf** để fan-in.
- Timeout từng request, kiểm tra HTTP 503 và fallback cho nguồn tùy chọn.
- Shutdown/await cho executor và local server.

Lưu tệp **CompletableFutureIoDemo.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public class CompletableFutureIoDemo {
    private static final AtomicInteger THREAD_ID = new AtomicInteger();

    private static ThreadFactory namedThreads(String prefix) {
        return task -> new Thread(task,
                prefix + "-" + THREAD_ID.incrementAndGet());
    }

    private static void respond(HttpExchange exchange, String body,
                                int status, CountDownLatch allArrived)
            throws IOException {
        if (allArrived != null) {
            allArrived.countDown();
            try {
                if (!allArrived.await(3, TimeUnit.SECONDS)) {
                    status = 503;
                    body = "fan-out did not reach all endpoints";
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IOException(
                        "server handler interrupted", interrupted);
            }
        }

        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static CompletableFuture<String> getText(
            HttpClient client, ExecutorService parseExecutor,
            URI uri, Duration requestTimeout) {
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(requestTimeout)
                .header("Accept", "text/plain")
                .GET()
                .build();

        return client.sendAsync(request, HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8))
                .thenApplyAsync(response -> {
                    int status = response.statusCode();
                    if (status < 200 || status >= 300) {
                        throw new CompletionException(new IOException(
                                "HTTP status " + status + " from " + uri));
                    }
                    return response.body();
                }, parseExecutor);
    }

    private static Throwable rootCause(Throwable error) {
        Throwable current = error;
        while ((current instanceof ExecutionException
                || current instanceof CompletionException)
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch allArrived = new CountDownLatch(3);
        ExecutorService serverExecutor = Executors.newFixedThreadPool(
                5, namedThreads("local-server"));
        ExecutorService parseExecutor = Executors.newFixedThreadPool(
                2, namedThreads("response-parse"));
        ThreadPoolExecutor httpExecutor = new ThreadPoolExecutor(
                4, 4, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<Runnable>(32),
                namedThreads("http-client"),
                new ThreadPoolExecutor.AbortPolicy());

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.setExecutor(serverExecutor);
        server.createContext("/profile",
                exchange -> respond(exchange, "profile=ada", 200, allArrived));
        server.createContext("/orders",
                exchange -> respond(exchange, "orders=3", 200, allArrived));
        server.createContext("/flags",
                exchange -> respond(exchange, "flags=beta", 200, allArrived));
        server.createContext("/unavailable",
                exchange -> respond(exchange, "temporarily unavailable",
                        503, null));
        server.createContext("/slow", exchange -> {
            try {
                Thread.sleep(800);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IOException(
                        "slow handler interrupted", interrupted);
            }
            respond(exchange, "slow response", 200, null);
        });
        server.start();

        try {
            int port = server.getAddress().getPort();
            URI base = URI.create("http://127.0.0.1:" + port);

            HttpClient client = HttpClient.newBuilder()
                    .executor(httpExecutor)
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();

            // Fan-out: start all independent requests before waiting for any.
            CompletableFuture<String> profile =
                    getText(client, parseExecutor, base.resolve("/profile"),
                            Duration.ofSeconds(4));
            CompletableFuture<String> orders =
                    getText(client, parseExecutor, base.resolve("/orders"),
                            Duration.ofSeconds(4));
            CompletableFuture<String> flags =
                    getText(client, parseExecutor, base.resolve("/flags"),
                            Duration.ofSeconds(4));

            // Fan-in: allOf signals completion; it does not collect the values.
            CompletableFuture<String> dashboard =
                    CompletableFuture.allOf(profile, orders, flags)
                            .thenApplyAsync(ignored ->
                                    profile.join() + " | " +
                                    orders.join() + " | " +
                                    flags.join(),
                                    parseExecutor);

            String result;
            try {
                result = dashboard.get(6, TimeUnit.SECONDS);
            } catch (ExecutionException | TimeoutException failure) {
                profile.cancel(true);
                orders.cancel(true);
                flags.cancel(true);
                throw failure;
            }

            System.out.println("dashboard: " + result);
            System.out.println("all three requests overlapped: " +
                    (allArrived.getCount() == 0));
            System.out.println("HTTP executor is dedicated: " +
                    client.executor().isPresent());
            System.out.println("HTTP executor queue capacity: " +
                    (httpExecutor.getQueue().remainingCapacity()
                            + httpExecutor.getQueue().size()));

            CompletableFuture<String> unavailable =
                    getText(client, parseExecutor,
                            base.resolve("/unavailable"),
                            Duration.ofSeconds(2));
            try {
                unavailable.get(3, TimeUnit.SECONDS);
                throw new AssertionError("HTTP 503 should fail the stage");
            } catch (ExecutionException expected) {
                System.out.println("non-2xx status rejected: " +
                        (rootCause(expected) instanceof IOException));
            }

            CompletableFuture<String> optional =
                    getText(client, parseExecutor,
                            base.resolve("/unavailable"),
                            Duration.ofSeconds(2))
                            .handleAsync((value, error) ->
                                    error == null ? value :
                                            "optional=unavailable",
                                    parseExecutor);
            System.out.println("optional failure fallback: " +
                    optional.get(3, TimeUnit.SECONDS));

            CompletableFuture<String> slow =
                    getText(client, parseExecutor, base.resolve("/slow"),
                            Duration.ofMillis(150));
            try {
                slow.get(3, TimeUnit.SECONDS);
                throw new AssertionError("request timeout should fail");
            } catch (ExecutionException expected) {
                System.out.println("request timeout observed: " +
                        (rootCause(expected) instanceof HttpTimeoutException));
            }
        } finally {
            server.stop(0);
            httpExecutor.shutdown();
            parseExecutor.shutdown();
            serverExecutor.shutdown();
            await(httpExecutor);
            await(parseExecutor);
            await(serverExecutor);
        }
        System.out.println("executors terminated: true");
    }

    private static void await(ExecutorService executor)
            throws InterruptedException {
        if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "executor did not terminate");
            }
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac --release 17 --add-modules jdk.httpserver CompletableFutureIoDemo.java
java --add-modules jdk.httpserver CompletableFutureIoDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
dashboard: profile=ada | orders=3 | flags=beta
all three requests overlapped: true
HTTP executor is dedicated: true
HTTP executor queue capacity: 32
non-2xx status rejected: true
optional failure fallback: optional=unavailable
request timeout observed: true
executors terminated: true
~~~

Ba endpoint chính dùng CountDownLatch: mỗi handler đợi đến khi cả ba request tới server. Dòng **all three requests overlapped: true** chứng minh chương trình đã khởi chạy ba request trước khi chờ kết quả.

Ví dụ này kiểm chứng fan-out/fan-in, status handling, timeout và executor lifecycle trong môi trường local. Nó không đo tốc độ mạng production và không khẳng định số worker/queue 4/32 là cấu hình tối ưu cho mọi hệ thống.

## 25. Ví dụ Java 8: CompletableFuture với executor riêng cho nhiều I/O

Java 8 chưa có java.net.http.HttpClient. Tuy nhiên, CompletableFuture.supplyAsync, allOf và ExecutorService đã có từ Java 8. Mẫu phù hợp là đưa các lời gọi blocking của client/DAO hiện có vào executor riêng.

Chương trình sau dùng ba file local để kiểm chứng API và cách ghép kết quả, hoàn toàn tương thích Java 8. Trong ứng dụng thật, hàm read có thể được thay bằng lời gọi JDBC hoặc HTTP client blocking đã cấu hình timeout.

Lưu tệp **CompletableFutureJava8FileDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class CompletableFutureJava8FileDemo {
    private static String read(Path path) {
        try {
            byte[] bytes = Files.readAllBytes(path);
            return new String(bytes, StandardCharsets.UTF_8);
        } catch (IOException failure) {
            throw new CompletionException(failure);
        }
    }

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("cf-io-demo");
        Path profile = directory.resolve("profile.txt");
        Path orders = directory.resolve("orders.txt");
        Path flags = directory.resolve("flags.txt");
        Files.write(profile,
                "profile=ada".getBytes(StandardCharsets.UTF_8));
        Files.write(orders,
                "orders=3".getBytes(StandardCharsets.UTF_8));
        Files.write(flags,
                "flags=beta".getBytes(StandardCharsets.UTF_8));

        ExecutorService ioExecutor = Executors.newFixedThreadPool(3);
        try {
            CompletableFuture<String> profileFuture =
                    CompletableFuture.supplyAsync(
                            () -> read(profile), ioExecutor);
            CompletableFuture<String> ordersFuture =
                    CompletableFuture.supplyAsync(
                            () -> read(orders), ioExecutor);
            CompletableFuture<String> flagsFuture =
                    CompletableFuture.supplyAsync(
                            () -> read(flags), ioExecutor);

            String combined = CompletableFuture.allOf(
                    profileFuture, ordersFuture, flagsFuture)
                    .thenApply(ignored ->
                            profileFuture.join() + " | " +
                            ordersFuture.join() + " | " +
                            flagsFuture.join())
                    .get(5, TimeUnit.SECONDS);

            System.out.println("Java 8 I/O result: " + combined);
            System.out.println("all futures complete: " +
                    (profileFuture.isDone() &&
                     ordersFuture.isDone() &&
                     flagsFuture.isDone()));
        } finally {
            ioExecutor.shutdown();
            if (!ioExecutor.awaitTermination(5, TimeUnit.SECONDS)) {
                ioExecutor.shutdownNow();
                if (!ioExecutor.awaitTermination(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "executor did not terminate");
                }
            }
            Files.deleteIfExists(profile);
            Files.deleteIfExists(orders);
            Files.deleteIfExists(flags);
            Files.deleteIfExists(directory);
        }
        System.out.println("Java 8 executor terminated: true");
    }
}
~~~

Biên dịch/chạy với JDK mới ở target Java 8:

~~~bash
javac --release 8 CompletableFutureJava8FileDemo.java
java CompletableFutureJava8FileDemo
~~~

Trên chính JDK 8, dùng javac/java trực tiếp vì tùy chọn --release được bổ sung ở JDK sau.

**Stdout đã kiểm chứng với javac --release 8:**

~~~text
Java 8 I/O result: profile=ada | orders=3 | flags=beta
all futures complete: true
Java 8 executor terminated: true
~~~

Khi thay file I/O bằng JDBC hoặc HTTP client blocking:

~~~java
CompletableFuture<User> user =
        CompletableFuture.supplyAsync(
                () -> userRepository.loadUser(userId),
                ioExecutor);

CompletableFuture<List<Order>> orders =
        CompletableFuture.supplyAsync(
                () -> orderRepository.loadOrders(userId),
                ioExecutor);
~~~

Đây là snippet cần repository và executor được cấu hình. Mỗi repository call phải quản lý connection/resource đúng cách; không chia sẻ một JDBC Connection đang được dùng đồng thời giữa nhiều future. Với HTTP client blocking, thiết lập connect/read timeout ở client đó trước khi đưa vào executor.

## 26. Java 8 và Java 11+ khác nhau ở đâu?

| Khả năng | Java 8 | Java 11+ |
| --- | --- | --- |
| CompletableFuture / CompletionStage | Có | Có |
| supplyAsync với Executor | Có | Có |
| allOf / anyOf | Có | Có |
| thenCompose / thenCombine / handle | Có | Có |
| HttpClient trong JDK | Chưa có | Có từ Java 11 |
| HttpClient.sendAsync | Chưa có | Có từ Java 11 |
| HttpRequest.timeout | Chưa có | Có từ Java 11 |
| CompletableFuture.orTimeout | Chưa có | Có từ Java 9 |
| HttpClient.close / AutoCloseable | Chưa có | Có từ Java 21 |

Nếu runtime là Java 8, chọn client/driver được hỗ trợ trên Java 8 và chạy blocking call trên executor riêng có giới hạn. Nếu runtime Java 11+, HttpClient.sendAsync cung cấp HTTP asynchronous API tích hợp JDK.

**Không biên dịch code HttpClient rồi kỳ vọng chạy trên Java 8.** Tách module/source set theo target JDK hoặc dùng abstraction transport để code orchestration không phụ thuộc vào một HTTP API cụ thể.

## 27. Context propagation, tracing và logging

Một request tổng hợp thường có correlation ID, trace/span, tenant ID và deadline. Khi tạo nhiều future, cần bảo đảm context đi theo các stage:

- Gắn trace context vào HTTP headers của từng request.
- Dùng context propagation do framework hỗ trợ khi callback chuyển thread.
- Truyền request-scoped data qua object immutable hoặc tham số.
- Ghi metric cho từng dependency và cho aggregate.
- Không phụ thuộc vào ThreadLocal nếu framework không bảo đảm context propagation.
- Không ghi token, cookie, secret hoặc payload nhạy cảm vào log.

Nên phân biệt metric theo endpoint/dependency: request count/status, request latency/timeout, retry/cancellation, queue depth/active workers, tổng thời gian fan-out/fan-in và số aggregate thành công/thất bại/partial result.

Một dashboard tổng thể có thể nhanh hơn nhưng vẫn che một dependency thường xuyên chậm. Ghi latency riêng từng future giúp biết nguồn nào chi phối tail latency.

## 28. Test đúng và test hiệu năng

**Correctness test:**

- Tất cả endpoint trả thành công.
- Một endpoint trả 404/503.
- Một endpoint timeout.
- Nguồn optional lỗi nhưng aggregate vẫn có fallback hợp lệ.
- Nhiều future hoàn tất theo thứ tự khác nhau.
- Response rỗng, body lớn hoặc JSON không hợp lệ.
- Cancellation xảy ra khi request đang chạy.
- Executor queue đầy hoặc executor đã shutdown.
- Tổng hợp không làm mất hoặc trộn dữ liệu giữa user/tenant.

**Test concurrency:** có thể dùng local HTTP server, barrier/latch hoặc stub để xác minh các lời gọi độc lập được khởi chạy chồng lấp. Không chỉ kiểm tra thời gian wall-clock của một lần chạy.

**Test hiệu năng:** so sánh tuần tự với fan-out/fan-in dưới cùng input, cùng server/dependency, cùng timeout và cùng tải. Đo p50/p95/p99, throughput, error rate, queue depth và memory. Một chương trình local chứng minh cơ chế hoạt động không phải benchmark production.

## 29. Các lỗi phổ biến khi ghép nhiều I/O

1. **Gọi get/join sau mỗi sendAsync.** Làm request chạy tuần tự.
2. **Dùng common pool cho mọi callback async.** Workload không liên quan có thể tranh chấp.
3. **Không truyền executor cho thenApplyAsync/thenComposeAsync quan trọng.** Callback rơi về default async executor.
4. **Tạo HttpClient mới cho từng request.** Mất lợi ích connection reuse.
5. **Tạo ExecutorService mới cho mỗi request.** Tăng thread và làm khó lifecycle.
6. **Shutdown executor ngay sau submit.** Các callback còn cần executor để hoàn tất.
7. **Dùng queue không giới hạn cho producer nhanh.** Backlog có thể làm heap tăng.
8. **Cho rằng bounded queue tự giới hạn HTTP in-flight.** Cần limiter/semaphore ở boundary downstream.
9. **Không đặt request timeout.** Một dependency treo có thể giữ aggregate rất lâu.
10. **Nhầm connectTimeout với request timeout.** Hai phạm vi khác nhau.
11. **Không kiểm tra statusCode.** HTTP 503 vẫn có thể là response hoàn tất bình thường.
12. **Nghĩ allOf trả list kết quả.** Nó chỉ trả CompletableFuture<Void>.
13. **Nghĩ allOf tự cancel sibling khi một future lỗi.** Cần policy cancel rõ ràng.
14. **Dùng exceptionally trả null cho mọi lỗi.** Che lỗi và tạo dữ liệu không rõ nghĩa.
15. **Block trong callback đang chạy trên I/O executor.** Làm nghẽn worker.
16. **Block chờ task con trên cùng pool nhỏ.** Có thể gây starvation/deadlock.
17. **Chia sẻ mutable collection giữa callbacks.** Có thể race hoặc sai dữ liệu.
18. **Không kiểm tra response size.** Nhiều body lớn cùng lúc gây heap pressure.
19. **Không đóng streaming response body.** Resource có thể bị giữ lại.
20. **Retry vô hạn hoặc không có jitter.** Làm dependency quá tải hơn.
21. **Coi cancel là remote operation đã dừng.** Server có thể đã xử lý request.
22. **Retry lệnh ghi không idempotent.** Có thể tạo side effect trùng.
23. **Dựa vào ThreadLocal qua nhiều async stage.** Context có thể mất hoặc trộn.
24. **Log toàn bộ request/response.** Có nguy cơ lộ credential hoặc dữ liệu nhạy cảm.
25. **Chỉ test happy path.** Lỗi một dependency có thể làm aggregate hỏng.
26. **Dùng CompletableFuture chỉ để bọc một method đơn giản.** Tăng độ phức tạp mà không có lợi ích.
27. **Không đo tail latency từng dependency.** Một nguồn chậm có thể chi phối cả dashboard.

## 30. Quy trình triển khai có thể lặp lại

1. Liệt kê các nguồn I/O và dependency giữa chúng.
2. Xác định nguồn bắt buộc và nguồn tùy chọn.
3. Tạo baseline tuần tự để xác nhận kết quả nghiệp vụ.
4. Chọn transport API đúng phiên bản JDK.
5. Tạo HttpClient tái sử dụng và executor được quản lý theo lifecycle.
6. Giới hạn queue, downstream concurrency, request timeout và overall deadline.
7. Khởi chạy các request độc lập trước khi chờ.
8. Dùng thenCompose cho dependency chain, allOf/thenCombine cho fan-in.
9. Kiểm tra HTTP status, parse response trên executor phù hợp.
10. Xử lý required/optional failure theo policy.
11. Định nghĩa cancellation, retry, idempotency và partial result.
12. Test happy path, timeout, 4xx/5xx, queue full và shutdown.
13. Đo latency từng dependency và latency aggregate dưới tải.
14. Chỉ tăng worker/queue khi metric chứng minh cấu hình hiện tại là bottleneck.

## 31. Checklist trước khi đưa vào production

**Dependency:** những request nào thực sự độc lập? Có bước nào cần kết quả của bước trước?

**Executor:** ai sở hữu executor? Có truyền rõ executor cho callback async? Worker/queue có giới hạn và rejection policy?

**Downstream:** connection pool, rate limit, quota và concurrency limit có được tôn trọng? Có Semaphore/bulkhead nếu cần?

**Timeout:** connect timeout, request timeout và overall deadline đã có? Timeout có kích hoạt cleanup/cancel đúng policy?

**Failure:** status 4xx/5xx được phân loại? Required/optional dependency khác nhau? Error cause có được quan sát?

**Cancellation/retry:** cancel có được hiểu là best effort? Side effect có idempotent? Retry có backoff/jitter/maximum attempts?

**Resources:** body stream được đóng? Client/executor được đóng theo owner? Không shutdown resource còn được future sử dụng?

**Thread safety:** context được truyền đúng? Không có shared mutable state hoặc JDBC Connection dùng đồng thời?

**Observability:** có latency từng endpoint, aggregate latency, queue/rejection, timeout/retry/cancel metrics?

**Testing:** có test partial failure, status error, timeout, concurrency, overload và shutdown?

## 32. Bài tập và đáp án

**1.** CompletableFuture có từ Java nào?  
**Đáp án:** Java 8.

**2.** JDK HttpClient có từ Java nào?  
**Đáp án:** Java 11.

**3.** sendAsync trả về kiểu gì?  
**Đáp án:** CompletableFuture<HttpResponse<T>>.

**4.** Vì sao tạo cả ba future trước khi gọi get?  
**Đáp án:** Để khởi chạy các request độc lập chồng lấp thay vì tuần tự.

**5.** allOf có trả về List kết quả không?  
**Đáp án:** Không; nó trả CompletableFuture<Void>. Đọc từng future sau khi allOf hoàn tất.

**6.** Khi nào dùng thenCompose?  
**Đáp án:** Khi bước sau phụ thuộc kết quả bước trước và bản thân bước sau trả một stage/future khác.

**7.** Async method không truyền Executor thường dùng pool nào?  
**Đáp án:** ForkJoinPool.commonPool.

**8.** thenApply có luôn chạy trên executor được cấu hình cho HttpClient không?  
**Đáp án:** Không; callback non-async có thể chạy trên thread hoàn tất stage trước hoặc caller thread.

**9.** HTTP 503 có làm sendAsync exceptional tự động không?  
**Đáp án:** Không nhất thiết; kiểm tra statusCode và áp dụng policy.

**10.** allOf có tự cancel các future còn lại khi một future lỗi không?  
**Đáp án:** Không; phải xây dựng policy cancel nếu cần.

**11.** CompletableFuture.cancel(true) có đảm bảo remote server ngừng xử lý không?  
**Đáp án:** Không; cancellation của HttpClient là best effort.

**12.** connectTimeout và HttpRequest.timeout khác nhau thế nào?  
**Đáp án:** Một cái giới hạn thiết lập kết nối, cái còn lại giới hạn request/response.

**13.** Vì sao không dùng queue không giới hạn?  
**Đáp án:** Backlog có thể tăng liên tục và tiêu thụ heap khi producer nhanh hơn consumer.

**14.** Bounded executor queue có giới hạn số HTTP request in-flight không?  
**Đáp án:** Không trực tiếp; dùng Semaphore/rate limiter nếu cần giới hạn downstream concurrency.

**15.** Có thể dùng HttpClient JDK trên Java 8 không?  
**Đáp án:** Không; HttpClient tích hợp JDK có từ Java 11. CompletableFuture vẫn có thể kết hợp blocking client tương thích Java 8.

## 33. Tài liệu Java hiện hành

- **CompletableFuture (Java SE 26):** allOf/anyOf, default executor, cancellation, completion policies và async methods: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- **CompletableFuture (Java SE 8):** API nền tảng tương thích Java 8: https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CompletableFuture.html
- **HttpClient (Java SE 26):** sendAsync, connection reuse, body handlers, cancellation và lifecycle: https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html
- **HttpClient.Builder (Java SE 26):** executor và connectTimeout: https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Builder.html
- **HttpRequest.Builder (Java SE 26):** request timeout: https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html
- **ExecutorService (Java SE 26):** submit, shutdown, awaitTermination và quản lý task: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html
- **ThreadPoolExecutor (Java SE 26):** worker bounds, bounded/unbounded queue và rejection policy: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- **Semaphore (Java SE 26):** giới hạn số tác vụ đồng thời: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Semaphore.html
- **Virtual Threads (Java SE 26):** blocking I/O, throughput và giới hạn CPU-bound: https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html

**Phiên bản và mức kiểm chứng:** chương trình HTTP dùng API HttpClient từ Java 11 và đã biên dịch/chạy bằng target Java 17. Chương trình Java 8 dùng CompletableFuture/ExecutorService với file I/O và đã biên dịch/chạy bằng javac --release 8. Các kết quả trong stdout là output thực tế của local test, không phải benchmark production. Executor size, queue capacity, timeout và concurrency limit trong ví dụ là cấu hình minh họa; cần đo và điều chỉnh theo downstream thật.

**Kết luận:** khởi chạy các lời gọi I/O độc lập bằng sendAsync hoặc supplyAsync với executor được chỉ định, sau đó ghép bằng allOf/thenCombine và nối dependency bằng thenCompose. Đặt timeout, giới hạn tải, phân loại lỗi và quản lý lifecycle ngay từ đầu để fan-out/fan-in có thể vận hành an toàn dưới tải thực tế.
