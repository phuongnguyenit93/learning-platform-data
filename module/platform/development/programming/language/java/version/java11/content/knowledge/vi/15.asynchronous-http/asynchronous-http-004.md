# Executor của HttpClient và ngữ cảnh chạy các bước tiếp theo trong Java 11+

## 1. Bài toán: request bất đồng bộ và đoạn xử lý sau response chạy ở đâu?

Từ **Java 11**, `java.net.http.HttpClient` có thể gửi HTTP request bất đồng bộ bằng `sendAsync(...)`. Phương thức trả ngay một `CompletableFuture<HttpResponse<T>>`, nhờ đó ta có thể khai báo các bước tiếp theo như phân tích JSON, chuyển đổi dữ liệu, cập nhật trạng thái hoặc ghi log.

Hai câu hỏi phải tách biệt:

1. **Ai thực hiện các tác vụ bất đồng bộ phục vụ HTTP client?** Có thể cấu hình `Executor` cho `HttpClient` qua `HttpClient.newBuilder().executor(executor)`.
2. **Bước xử lý ứng dụng sau khi future hoàn thành chạy trên thread nào?** Điều này phụ thuộc cách gắn các `CompletableFuture`/`CompletionStage` stage: `thenApply(...)`, `thenApplyAsync(...)`, `thenApplyAsync(..., executor)`, v.v.

**Quy tắc quan trọng:** đặt `executor(...)` khi xây `HttpClient` **không có nghĩa** mọi lambda `thenApply`, `thenAccept` hay callback sau đó được bảo đảm chạy trên executor ấy. Khi cần kiểm soát nơi thực thi bước nghiệp vụ, hãy dùng các phương thức `*Async(..., executor)` với một executor ứng dụng được chỉ định rõ.

Các quy tắc này vẫn có giá trị với những JDK hiện đại. Bài học sử dụng API tương thích **Java 11 trở lên**, không dựa vào framework hay hành vi thread mang tính ngẫu nhiên.

## 2. `HttpClient.Builder.executor(...)` thực sự cấu hình điều gì?

API cốt lõi:

```java
ExecutorService httpExecutor = Executors.newFixedThreadPool(4);

HttpClient client = HttpClient.newBuilder()
        .executor(httpExecutor)
        .build();
```

Đây là **đoạn minh họa** trong một phạm vi có import `HttpClient`, `ExecutorService` và `Executors`; sau khi dùng xong, ứng dụng phải quản lý vòng đời `httpExecutor`.

Theo hợp đồng `HttpClient.Builder.executor(Executor)`, executor này được dùng cho **các tác vụ bất đồng bộ và phụ thuộc** của HTTP client. Nó có thể phục vụ các công việc nội bộ, phản hồi hoặc các tác vụ liên quan đến giao tiếp HTTP. Tuy nhiên, không được suy ra rằng **toàn bộ** I/O hay mọi callback của ứng dụng nhất định chạy trên những thread của executor này: một số tác vụ có thể chạy trên thread gọi API, thread nội bộ khác hoặc tuân theo chính sách riêng của `CompletableFuture`.

Nếu không gọi `builder.executor(...)`, client vẫn có **executor mặc định do implementation quản lý**. Không phải tự cấu hình executor thì `sendAsync()` mới hoạt động.

Có thể kiểm tra cấu hình đã cấp qua:

```java
Optional<Executor> configured = client.executor();
```

- Nếu đã truyền executor vào builder, `client.executor()` chứa executor đã cấu hình.
- Nếu không cấu hình thủ công, `client.executor()` trả `Optional.empty()`, **không có nghĩa client không có executor thực tế**; implementation vẫn có thể dùng executor mặc định không được trả ra qua API.
- `HttpClient` là đối tượng **immutable sau `build()`** và thường được tái sử dụng cho nhiều request.

Tuy `HttpClient.Builder.executor` có chữ “dependent tasks” trong Javadoc, tài liệu package `java.net.http` làm rõ rằng **dependent stages do lập trình viên gắn vào future mà không chỉ định executor tường minh** tuân theo quy tắc thực thi của `CompletableFuture` hoặc của thread đang đăng ký stage khi future đã hoàn thành. Vì vậy không nên lấy cấu hình client làm cam kết về thread thực thi business logic.

## 3. Bảng so sánh các bước tiếp theo của `CompletableFuture`

Giả sử:

```java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
```

Đây là đoạn minh họa, cần `client` và `request` được tạo trước. Có các lựa chọn:

| Cách viết | Thread/executor chạy bước phụ thuộc | Điều cần lưu ý |
| --- | --- | --- |
| `future.thenApply(response -> ...)` | Có thể chạy trên thread hoàn thành future hoặc thread gắn stage nếu future đã hoàn thành | **Không bảo đảm** thread HTTP, main hay một pool cụ thể. |
| `future.thenAccept(response -> ...)` | Quy tắc tương tự stage không có hậu tố `Async` | Không nên chạy tác vụ blocking hoặc CPU nặng mà không hiểu tác động tới thread kích hoạt. |
| `future.thenApplyAsync(response -> ...)` | Executor mặc định của `CompletableFuture`; thường `ForkJoinPool.commonPool()` | **Không phải** chỉ thị dùng client executor. Các chi tiết có thể khác theo default executor/subclass hoặc môi trường. |
| `future.thenApplyAsync(response -> ..., appExecutor)` | **`appExecutor` được truyền trực tiếp** | Lựa chọn rõ ràng khi muốn điều phối bước xử lý nghiệp vụ tới một pool cụ thể. |
| `future.thenComposeAsync(response -> otherFuture, appExecutor)` | Bước gọi lambda được lên lịch bằng `appExecutor`, rồi nối với future khác | Phù hợp bước sau **cũng bất đồng bộ**; không đợi đồng bộ bằng `join()` bên trong lambda. |
| `future.whenCompleteAsync((value, error) -> ..., appExecutor)` | Callback quan sát hoàn tất được lên lịch bằng `appExecutor` | Thường dùng logging/cleanup; exception của chuỗi vẫn cần được xử lý. |
| `future.handleAsync((value, error) -> ..., appExecutor)` | Bước kết hợp giá trị/lỗi được lên lịch bằng `appExecutor` | Có thể biến đổi lỗi thành kết quả dự phòng nếu logic ứng dụng chủ động chọn. |

**`thenApply`** là đồng bộ *theo cách kích hoạt callback*, không phải “chặn thread gọi cho tới khi HTTP xong”. Nó đăng ký một hành động phụ thuộc và thường trả về ngay một future khác. Khi future nguồn được hoàn thành, callback có thể chạy trực tiếp trên thread làm nó hoàn thành. Ngược lại, khi future nguồn **đã** hoàn thành trước lúc đăng ký, callback không-`Async` có thể chạy ngay trên thread đang gọi `thenApply`.

**`thenApplyAsync` không truyền executor** thường dùng common pool (theo chính sách của `CompletableFuture`). Nếu chương trình cần một thread pool xác định, **luôn dùng overload có tham số `Executor`**, không kiểm tra tên thread ở thời điểm thử nghiệm rồi giả định đó là hợp đồng API.

## 4. Ví dụ Java hoàn chỉnh: executor HTTP riêng, bước nghiệp vụ riêng

Ví dụ sau tạo HTTP server cục bộ bằng module `jdk.httpserver`, nên **không cần Internet** hay API bên ngoài. Nó cấu hình:

- `httpPool`: executor được gắn vào `HttpClient`. Đây là pool phục vụ các tác vụ do HTTP client triển khai. Chương trình không phụ thuộc việc callback cụ thể nào chạy trên pool này.
- `appPool`: executor **một thread có tên cố định `app-stage`**, chỉ định rõ cho `thenApplyAsync(..., appPool)`. Vì thế tên thread của bước nghiệp vụ trong output được kiểm soát.
- `TRACE_ID`: một `ThreadLocal<String>` minh họa “ngữ cảnh request” (trace ID). Chương trình **chụp giá trị** trên thread khởi tạo request rồi **cài đặt và dọn dẹp** giá trị ấy trong lambda chạy bất đồng bộ.

Lưu tệp **`HttpExecutorContextDemo.java`**:

```java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class HttpExecutorContextDemo {
    private static final ThreadLocal<String> TRACE_ID =
            new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/ping", exchange -> {
            byte[] payload = "pong".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, payload.length);
            try (OutputStream output = exchange.getResponseBody()) {
                output.write(payload);
            }
        });

        ExecutorService httpPool = Executors.newFixedThreadPool(
                2, task -> new Thread(task, "http-worker"));

        ExecutorService appPool = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "app-stage"));

        server.start();

        try {
            int port = server.getAddress().getPort();

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .executor(httpPool)
                    .build();

            HttpRequest request = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:"
                            + port + "/ping"))
                    .GET()
                    .build();

            TRACE_ID.set("trace-42");
            String capturedTrace = TRACE_ID.get();

            CompletableFuture<String> result =
                    client.sendAsync(
                            request,
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8))
                    .thenApplyAsync(response -> {
                        TRACE_ID.set(capturedTrace);
                        try {
                            if (response.statusCode() != 200) {
                                throw new IllegalStateException(
                                        "Unexpected HTTP status");
                            }
                            return "status=" + response.statusCode()
                                    + ",body=" + response.body()
                                    + ",stageThread="
                                    + Thread.currentThread().getName()
                                    + ",context=" + TRACE_ID.get();
                        } finally {
                            TRACE_ID.remove();
                        }
                    }, appPool);

            TRACE_ID.remove();

            System.out.println("clientExecutorConfigured=" +
                    client.executor().isPresent());
            System.out.println(result.join());
        } finally {
            appPool.shutdown();
            httpPool.shutdown();
            server.stop(0);
        }
    }
}
```

Biên dịch và chạy với **JDK 17+** (mã tương thích Java 11), trong môi trường cho phép dùng cổng loopback:

```bash
javac --add-modules jdk.httpserver HttpExecutorContextDemo.java
java --add-modules jdk.httpserver HttpExecutorContextDemo
```

**Stdout chính xác khi HTTP loopback hoạt động bình thường:**

```text
clientExecutorConfigured=true
status=200,body=pong,stageThread=app-stage,context=trace-42
```

Giải thích theo trình tự:

1. Server trả `200` và body `pong`. Cổng `0` để hệ điều hành chọn một cổng trống; ứng dụng không in cổng đó nên output ổn định.
2. `HttpClient.Builder.executor(httpPool)` cấu hình executor của client. `client.executor().isPresent()` là `true` vì executor đã được đặt tường minh.
3. `sendAsync(...)` lập lịch quá trình gửi và trả `CompletableFuture<HttpResponse<String>>`; `BodyHandlers.ofString` tạo kết quả body kiểu `String` khi đủ dữ liệu.
4. `thenApplyAsync(..., appPool)` bảo đảm **lambda ứng dụng** được đưa tới `appPool`. `newSingleThreadExecutor` tạo thread đặt tên `app-stage`, nên `stageThread=app-stage`.
5. `TRACE_ID` được đặt là `trace-42` trên thread tạo request, rồi copy sang biến `capturedTrace`. Lambda bất đồng bộ tự `set` giá trị vào `ThreadLocal` của thread nó đang chạy, sử dụng nó và `remove` trong `finally` để không làm rò ngữ cảnh sang công việc kế tiếp của pool.
6. `result.join()` **chặn thread gọi `join`** cho đến khi cả HTTP request lẫn bước `thenApplyAsync` hoàn thành hoặc thất bại. `sendAsync` không tự chặn; chính `join` trong ví dụ console phục vụ mục đích đợi kết quả để in đúng thứ tự.
7. Sau khi kết quả xong, `finally` shutdown hai executor do ứng dụng tạo và dừng HTTP server minh họa.

Module `jdk.httpserver` chỉ phục vụ HTTP server kiểm thử; ứng dụng HTTP client bình thường không cần module đó. Nếu môi trường cấm mở socket loopback, chương trình có thể thất bại vì chính sách môi trường; khi đó không thể kỳ vọng stdout như trường hợp thành công.

**Lưu ý:** Việc ví dụ dùng `ThreadLocal` **không** có nghĩa HTTP client sẽ tự truyền context từ thread gọi `sendAsync` sang thread xử lý. Việc truyền ở đây là **do mã ứng dụng thực hiện chủ động** thông qua biến `capturedTrace` và `TRACE_ID.set(...)` trong `thenApplyAsync`.

## 5. “Ngữ cảnh xử lý bước tiếp theo” gồm những gì?

Tùy hệ thống, “context” có thể là:

- **Trace ID / correlation ID** để liên kết log request HTTP với các bước parse, validate, lưu dữ liệu.
- **MDC logging context** được logger lưu theo thread.
- **Locale hoặc thông tin cấu hình theo request**.
- **Thông tin xác thực đã được kiểm tra hợp lệ và giới hạn tối thiểu** cần cho nghiệp vụ; tránh lưu secrets trong thread-local lâu hơn cần thiết.
- **Transactional context** hoặc resource context do framework quản lý, cần chuyển tiếp theo cơ chế chính thức của framework; không tự giả định một transaction từ thread A có thể mang nguyên sang thread B.

Một `ThreadLocal` bình thường gắn giá trị với **thread cụ thể**, không phải với `CompletableFuture`. Khi một bước chuyển sang executor khác, giá trị `ThreadLocal` từ thread trước **không tự động xuất hiện**. Tương tự, callback có thể chạy trên một thread pool tái sử dụng, nơi còn giá trị **cũ** do một tác vụ khác quên dọn dẹp. Đó là lý do không được dựa vào “thử thấy ThreadLocal vẫn có” để kết luận cơ chế propagation an toàn.

Mẫu xử lý khuyến nghị:

1. **Chụp context bất biến** khi bắt đầu chuỗi bất đồng bộ (ví dụ `String traceId = ...`, hoặc một object immutable chỉ chứa dữ liệu cần thiết).
2. **Chỉ định executor cho stage** khi thread affinity hoặc chính sách tài nguyên là yêu cầu.
3. **Cài đặt context trong stage**, gọi logic nghiệp vụ, rồi **khôi phục hoặc xóa** context trong `finally`.
4. Nếu thread có thể đang chứa context khác và cần lồng ghép callback, lưu giá trị cũ trước khi set rồi khôi phục nó sau cùng, thay vì luôn `remove()`.
5. Với framework logging/tracing, dùng API propagation chính thức của framework nếu có; đừng tự bọc chỉ một stage mà quên các nhánh lỗi và những stage kế tiếp.

Với ứng dụng nhỏ, **truyền context như một tham số rõ ràng** thường còn dễ kiểm thử hơn dùng `ThreadLocal`:

```java
String traceId = "trace-42";
future.thenApplyAsync(response ->
        parseResponse(response, traceId), appPool);
```

`parseResponse(...)` là phương thức ứng dụng tự định nghĩa, không có sẵn trong JDK; đây là **đoạn minh họa**, không phải chương trình chạy độc lập. Cách truyền tham số tránh dựa vào thread mà code chạy.

**Không dùng `InheritableThreadLocal` như giải pháp mặc định** để “sửa” context cho thread pool. Pool có thể đã tạo thread trước, tái sử dụng thread cho request khác và không tạo thread con cho từng tác vụ. Context cần được capture và apply theo từng công việc, hoặc dùng cơ chế framework phù hợp.

## 6. Ví dụ xử lý lỗi mà không mất kiểm soát executor

`sendAsync` hoàn thành **exceptionally** khi có lỗi như kết nối thất bại, timeout, hủy hoặc lỗi xảy ra trong xử lý response. Các stage phụ thuộc thành công như `thenApply` không chạy bình thường nếu stage trước thất bại.

Mẫu dùng executor riêng để quan sát cả giá trị lẫn lỗi:

```java
CompletableFuture<Void> tracked =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString())
              .whenCompleteAsync((response, error) -> {
                  if (error != null) {
                      logFailure(error); // Hàm ứng dụng tự viết.
                      return;
                  }
                  logSuccess(response.statusCode());
              }, appPool);
```

Đây là đoạn minh họa trong ngữ cảnh có `client`, `request`, `appPool` và hai hàm logging tự định nghĩa; không phải chương trình độc lập. `whenCompleteAsync` là một **callback quan sát kết quả/lỗi** và không tự chuyển lỗi thành thành công. Nếu muốn áp dụng giá trị dự phòng, cân nhắc `handleAsync(...)` hoặc `exceptionally(...)` với logic rõ ràng.

Ví dụ:

```java
CompletableFuture<String> result =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString())
              .thenApplyAsync(response -> response.body(), appPool)
              .exceptionally(error -> "fallback");
```

Đoạn này chỉ minh họa cơ chế. `exceptionally` không có tham số `Executor` ở overload trên; không nên giả định đoạn xử lý fallback chạy trên `appPool`. Nếu thật sự cần thực thi xử lý lỗi trên một executor riêng, có thể chọn `handleAsync(..., appPool)` hoặc stage `*Async` phù hợp. Không tùy tiện “nuốt” mọi lỗi mạng thành dữ liệu giả trong nghiệp vụ quan trọng.

**`join()` và `get()`:** `join()` chờ rồi ném `CompletionException` nếu future thất bại; `get()` dùng `ExecutionException` và có thể `InterruptedException`. Chúng hữu ích ở biên đồng bộ của CLI/test, nhưng gọi `join()` trong một stage chạy trên pool nhỏ có thể chặn thread cần thiết để một future khác hoàn thành, dẫn tới nghẽn/starvation. Với chuỗi bất đồng bộ, ưu tiên `thenCompose` / `thenComposeAsync` hơn là đợi future bằng `join()` bên trong callback.

## 7. Cấu hình executor và quản lý tài nguyên trong thực tế

### 7.1. Tách công việc I/O và nghiệp vụ khi cần

Một ví dụ ứng dụng có thể tạo hai pool:

```java
ExecutorService httpPool = Executors.newFixedThreadPool(4);
ExecutorService businessPool = Executors.newFixedThreadPool(8);

HttpClient client = HttpClient.newBuilder()
        .executor(httpPool)
        .build();

client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .thenApplyAsync(response -> transform(response.body()),
                businessPool);
```

Đây là đoạn minh họa cần khai báo `request` và phương thức `transform`. Việc tách pool **không phải yêu cầu bắt buộc** cho mọi dự án; nó giúp kiểm soát tải khi các stage ứng dụng tiêu tốn CPU hoặc có thao tác blocking.

Không nên đặt một HTTP client lên pool quá nhỏ rồi dùng chính pool ấy cho các callback chặn lâu, đặc biệt khi phải gửi nhiều request đồng thời. Điều này có thể gây trễ, starvation hoặc deadlock nếu task giữ thread trong lúc chờ công việc được lên lịch vào cùng pool. Quyết định số thread, giới hạn queue và policy từ chối task dựa trên phép đo thực tế; không có kích thước cố định tối ưu cho mọi tải.

### 7.2. Ai sở hữu `ExecutorService`?

Khi ứng dụng tự tạo executor và truyền cho `HttpClient.Builder.executor(...)`, **ứng dụng quản lý vòng đời của executor đó**. Không gọi `shutdown()` ngay sau `sendAsync(...)` vì công việc HTTP và các stage có thể chưa hoàn tất. Dùng một điểm kết thúc rõ ràng khi không còn request cần chạy, đợi các future cần thiết, rồi shutdown theo chính sách ứng dụng.

Trên **Java 11**, `HttpClient` chưa có phương thức quản lý vòng đời kiểu `close()` dành cho `try-with-resources`; thiết kế thường tạo một client dùng lại. Trên các JDK mới hơn đã có API quản lý vòng đời HTTP client, nhưng **đóng client và đóng executor tự cấp là hai trách nhiệm riêng**; không lấy việc đóng một trong hai làm bảo đảm ngầm cho mọi tài nguyên của cái còn lại.

Nếu executor được chia sẻ với module khác thì không tự shutdown tùy tiện sau một HTTP call; bên **sở hữu executor** quyết định thời điểm đóng. Nếu application server/framework cung cấp managed executor, dùng cơ chế quản lý của framework thay vì tạo/shutdown thread pool ngẫu hứng.

### 7.3. Executor mặc định là một cơ chế hoạt động, không phải “không có executor”

`HttpClient.newHttpClient().executor()` có thể trả `Optional.empty()`. Điều này chỉ phản ánh **không có executor cấu hình tường minh**; default implementation vẫn có thể dùng các thread phục vụ HTTP. Không lấy `isEmpty()` để kết luận `sendAsync` chạy trên main thread.

`HttpClient.Builder.executor(null)` không phải cách hợp lệ để quay lại mặc định: một tham số `null` là không hợp lệ. Để sử dụng executor mặc định, **không gọi phương thức `executor(...)`**.

### 7.4. `sendAsync()` không làm mọi thao tác đằng sau tự động non-blocking

`sendAsync(...)` trả về future mà không đợi HTTP response theo cách của `send(...)`. Nhưng nếu ứng dụng tự đưa vào `BodyPublisher`, `BodySubscriber` hoặc callback có thao tác I/O blocking thì những đoạn code đó vẫn có thể chặn thread thực thi. Việc chọn `Executor` không biến một hàm blocking thành non-blocking.

Khi cần tiếp tục một quy trình I/O bất đồng bộ khác, ưu tiên compose future:

```java
CompletableFuture<Result> result =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
              .thenComposeAsync(response ->
                      saveAsync(response.body()), appPool);
```

Đây là **mã minh họa** với `Result` là kiểu dữ liệu ứng dụng và `saveAsync` là hàm tự định nghĩa trả `CompletionStage<Result>`. Không phải chương trình đầy đủ. `thenComposeAsync` tránh tạo `CompletableFuture<CompletableFuture<Result>>` và không cần gọi `join()` trong lambda.

## 8. Các tình huống sai phổ biến

| Hiểu lầm / lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Đặt `HttpClient.Builder.executor(pool)` rồi cho rằng `thenApply(...)` luôn chạy ở `pool` | Callback không-`Async` chạy theo cơ chế hoàn thành của `CompletableFuture`. | Nếu cần thread affinity, dùng `thenApplyAsync(..., pool)`. |
| Dùng `thenApplyAsync(fn)` rồi cho rằng chắc chắn sử dụng executor của HTTP client | Không truyền executor nên dùng default executor theo chính sách của future, thường common pool. | Dùng `thenApplyAsync(fn, appExecutor)`. |
| Truyền `ThreadLocal` qua các callback bằng cách chỉ `set` trên thread gốc | ThreadLocal gắn với thread, không đi theo future. | Capture rồi restore trong callback hoặc truyền context như tham số. |
| Quên `remove` context trong pool | Task sau có thể đọc nhầm trace ID của request trước. | Dọn/khôi phục ngữ cảnh trong `finally`. |
| Sử dụng `InheritableThreadLocal` để “truyền” context vào mọi thread pool | Thread trong pool thường tái sử dụng, không phải thread con mới mỗi lần. | Dùng context propagation theo từng task. |
| Nghĩ `client.executor().isEmpty()` là `sendAsync` không có thread | Client vẫn có thể có default executor nội bộ. | Không nhầm cấu hình nhìn thấy với implementation. |
| `shutdown()` pool ngay sau khi gọi `sendAsync` | Công việc chưa hoàn tất, có thể bị từ chối hoặc gián đoạn. | Đợi mọi request/stage cần thiết kết thúc rồi mới shutdown. |
| Chạy parsing nặng/DB blocking trong `thenApply` trực tiếp | Có thể chặn thread hoàn thành hoặc thread gắn stage. | Dùng executor thích hợp, hoặc API asynchronous cho bước I/O tiếp theo. |
| Gọi `join()` trong callback của pool chỉ có một thread | Có nguy cơ nghẽn nếu future được chờ cũng cần pool ấy. | Compose futures, không đợi đồng bộ bên trong. |
| Chỉ gắn `thenAccept` nhưng bỏ quên future được trả về | Lỗi trong bước xử lý phụ thuộc có thể không được quan sát. | Giữ future cuối chuỗi và xử lý hoàn tất/lỗi. |

## 9. Câu hỏi tự kiểm tra

**Câu 1:** Cấu hình `client = HttpClient.newBuilder().executor(httpPool).build()` có bảo đảm `client.sendAsync(...).thenApply(fn)` chạy `fn` trên `httpPool` không?

**Đáp án:** **Không.** Stage không-`Async` theo chính sách hoàn thành `CompletableFuture`; có thể chạy trên thread hoàn thành hoặc thread gắn stage nếu future đã xong. Muốn ấn định executor, dùng `thenApplyAsync(fn, appPool)`.

**Câu 2:** `thenApplyAsync(fn)` không truyền executor khác gì `thenApplyAsync(fn, appPool)`?

**Đáp án:** Dạng thứ nhất dùng default executor của `CompletableFuture` (thông thường common pool); dạng thứ hai lên lịch `fn` qua `appPool` được chỉ định rõ.

**Câu 3:** Vì sao `client.executor().isEmpty()` không có nghĩa client thiếu khả năng chạy bất đồng bộ?

**Đáp án:** Nó chỉ nghĩa là **không có executor được set tường minh** trong builder; HTTP client có thể dùng default executor nội bộ.

**Câu 4:** `ThreadLocal` được set ở thread tạo request có tự có trong thread của `thenApplyAsync` không?

**Đáp án:** Không. Cần capture dữ liệu, áp dụng trong callback, dọn/khôi phục trong `finally`; hoặc truyền dữ liệu context qua tham số rõ ràng.

**Câu 5:** Có nên gọi `httpPool.shutdown()` ngay sau khi `sendAsync` trả future không?

**Đáp án:** Không. Khi future chưa hoàn tất, tác vụ HTTP còn có thể cần pool. Chỉ đóng khi không còn công việc liên quan và đã phối hợp vòng đời đúng.

**Câu 6:** Nếu bước sau trả về một future khác, dùng `thenApply` và `join` hay `thenComposeAsync`?

**Đáp án:** Thường dùng `thenComposeAsync(..., executor)` để nối hai giai đoạn bất đồng bộ mà không chặn thread, và điều khiển nơi thực thi lambda khi cần.

**Ghi nhớ:** `HttpClient.Builder.executor(...)` cấu hình executor cho các công việc async/dependent của **HTTP client**, nhưng không phải lời hứa rằng mọi `CompletableFuture` callback ứng dụng chạy trên cùng pool. `thenApply` có thể chạy ở thread hoàn thành/gắn stage; `thenApplyAsync` không truyền executor dùng mặc định của future; `thenApplyAsync(..., appExecutor)` mới điều khiển rõ **ngữ cảnh thực thi bước tiếp theo**. Context dạng `ThreadLocal` phải được truyền và dọn chủ động; executor do ứng dụng sở hữu chỉ shutdown sau khi công việc đã hoàn tất.

**Tài liệu API chính thức:** [Java SE 11 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html); [HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html); [package java.net.http](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/package-summary.html); [CompletableFuture](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletableFuture.html); [Java SE 25 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.Builder.html).
