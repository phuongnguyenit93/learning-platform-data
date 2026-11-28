# send đồng bộ và sendAsync với CompletableFuture

`java.net.http.HttpClient` cung cấp hai cách gửi request: `send()` đồng bộ và `sendAsync()` bất đồng bộ. Cả hai dùng chung `HttpRequest`, `HttpResponse` và `BodyHandler`; điểm khác nhau chính là cách chương trình chờ kết quả và kết nối các bước xử lý tiếp theo.

API `HttpClient` được chuẩn hóa từ Java 11 và vẫn là API HTTP client hiện hành trong JDK 26. Khi viết mã mới, ưu tiên `java.net.http.HttpClient` thay cho các cách gọi HTTP cũ. Hãy tái sử dụng một `HttpClient` cho nhiều request vì mỗi client thường quản lý connection pool riêng; tạo client mới liên tục sẽ làm giảm khả năng tái sử dụng kết nối.

## 1. Chuẩn bị HttpClient và HttpRequest

`HttpClient` được tạo bằng builder. Client sau khi build là immutable và có thể dùng đồng thời cho nhiều request. Mỗi request xác định URI, method, header, body publisher và timeout nếu cần.

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.time.Duration;

public class HttpClientSetup {
    public static void main(String[] args) {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.com/products"))
                .timeout(Duration.ofSeconds(15))
                .header("Accept", "application/json")
                .GET()
                .build();
    }
}
```

Trong ví dụ:

- `connectTimeout` giới hạn thời gian thiết lập kết nối.
- `HttpRequest.Builder.timeout` giới hạn thời gian chờ response của request.
- `followRedirects` xác định chính sách xử lý redirect.
- `Accept` thông báo kiểu dữ liệu ứng dụng muốn nhận.

`HttpClient` có thể được chia sẻ giữa nhiều service hoặc request. `HttpRequest` là đối tượng bất biến sau khi build; có thể gửi lại khi ngữ cảnh nghiệp vụ cho phép và `BodyPublisher` của request hỗ trợ việc subscribe lại.

## 2. Gửi request đồng bộ bằng `send()`

`send(request, bodyHandler)` chặn luồng gọi cho đến khi request được gửi và response được xử lý theo `BodyHandler`. Phương thức trả về trực tiếp `HttpResponse<T>`.

Ví dụ đọc response dưới dạng chuỗi:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class SyncHttpExample {
    public static void main(String[] args)
            throws IOException, InterruptedException {

        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.com/products"))
                .timeout(Duration.ofSeconds(15))
                .header("Accept", "application/json")
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );

        System.out.println("Status: " + response.statusCode());
        System.out.println("Version: " + response.version());
        System.out.println("Body: " + response.body());
    }
}
```

`send()` khai báo hai checked exception chính:

- `IOException`: lỗi I/O trong quá trình gửi hoặc nhận response, hoặc client đã shutdown.
- `InterruptedException`: luồng đang chờ bị interrupt.

Khi bị interrupt, built-in `HttpClient` cố gắng hủy HTTP exchange, nhưng không bảo đảm request chưa được gửi hoặc server chưa bắt đầu xử lý.

Nếu tầng gọi cần xử lý interrupt, hãy giữ lại trạng thái interrupt sau khi bắt exception:

```java
try {
    return client.send(request, HttpResponse.BodyHandlers.ofString());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("HTTP request was interrupted", e);
}
```

Chỉ dùng `send()` khi việc chờ kết quả là phù hợp với luồng hiện tại, ví dụ trong tác vụ nền đồng bộ hoặc command-line tool. Tránh gọi `send()` trên UI thread hoặc event loop cần tiếp tục xử lý công việc khác.

## 3. Chọn `BodyHandler` phù hợp

Mỗi lần gọi `send()` hoặc `sendAsync()` đều phải truyền một `HttpResponse.BodyHandler<T>`. `BodyHandler` quyết định cách tiêu thụ response body và cũng quyết định kiểu `T` của `HttpResponse<T>`.

| BodyHandler | Kiểu body | Cách dùng phù hợp |
| --- | --- | --- |
| `BodyHandlers.ofString()` | `String` | JSON hoặc văn bản có kích thước vừa phải; body được đọc hết trước khi response được trả về |
| `BodyHandlers.ofByteArray()` | `byte[]` | Nội dung nhị phân nhỏ, cần xử lý trực tiếp trong bộ nhớ |
| `BodyHandlers.ofFile(path)` | `Path` | Tải file; khi response trả về, body đã được ghi xong vào file |
| `BodyHandlers.ofInputStream()` | `InputStream` | Đọc streaming; response có thể trả về khi mới nhận xong header, body vẫn đang đến |
| `BodyHandlers.ofLines()` | `Stream<String>` | Xử lý văn bản theo dòng; stream phải được đóng |
| `BodyHandlers.discarding()` | `Void` | Chỉ cần status/header và muốn bỏ response body |

`ofString()` sử dụng charset trong header `Content-Type`; nếu header không có charset hoặc charset không được hỗ trợ, UTF-8 được dùng. Với body lớn, không nên mặc định gom toàn bộ nội dung vào `String` hoặc `byte[]`; cân nhắc `ofFile()` hoặc streaming handler.

Ví dụ tải file:

```java
Path destination = Path.of("downloads", "report.pdf");

HttpResponse<Path> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofFile(destination)
);

System.out.println("Saved to: " + response.body());
```

Ví dụ đọc stream cần đóng tài nguyên:

```java
HttpResponse<InputStream> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofInputStream()
);

Path destination = Path.of("downloads", "report.pdf");
Files.createDirectories(destination.getParent());

try (InputStream body = response.body()) {
    Files.copy(body, destination, StandardCopyOption.REPLACE_EXISTING);
}
```

Đoạn mã cần các import `InputStream`, `Files`, `Path` và `StandardCopyOption` từ `java.io`/`java.nio.file`.

Với `ofInputStream()`, `ofLines()` hoặc `ofPublisher()`, response có thể được trả về trước khi body được tiêu thụ hết. Ứng dụng phải đọc stream đến cuối hoặc đóng/cancel nó để giải phóng tài nguyên và để HTTP exchange hoàn tất.

## 4. Gửi bất đồng bộ bằng `sendAsync()`

`sendAsync(request, bodyHandler)` trả về `CompletableFuture<HttpResponse<T>>`. Phương thức cung cấp future để chương trình đăng ký các bước tiếp theo và tiếp tục làm việc khác mà không cần chờ response ngay tại dòng gọi.

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

public class AsyncHttpExample {
    public static void main(String[] args) {
        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.com/products"))
                .timeout(Duration.ofSeconds(15))
                .header("Accept", "application/json")
                .GET()
                .build();

        CompletableFuture<HttpResponse<String>> responseFuture =
                client.sendAsync(
                        request,
                        HttpResponse.BodyHandlers.ofString()
                );

        CompletableFuture<String> bodyFuture = responseFuture
                .thenApply(HttpResponse::body);

        CompletableFuture<Void> done = bodyFuture.thenAccept(System.out::println)
                .exceptionally(error -> {
                    System.err.println("Request failed: " + error);
                    return null;
                });

        // Điểm chờ ở cuối chương trình CLI để JVM không kết thúc trước callback.
        // Trong server hoặc ứng dụng có vòng đời riêng, trả/ghép stage thay vì block.
        done.join();
        client.close(); // Đóng client sau khi các request đã hoàn tất.
    }
}
```

`thenApply` biến đổi kết quả từ `HttpResponse<String>` thành `String`. `thenAccept` nhận kết quả để thực hiện một hành động và tạo stage có kết quả kiểu `Void`. `exceptionally` xử lý lỗi và trả về giá trị thay thế để hoàn tất stage tiếp theo. `done.join()` ở ví dụ chỉ dùng tại điểm kết thúc của chương trình CLI để chờ pipeline; không nên đặt kiểu chờ này trong callback hoặc event loop.

Không nên gọi `join()` hoặc `get()` ngay sau `sendAsync()` nếu mục tiêu là không chặn luồng hiện tại. Nếu gọi ngay, chương trình lại chờ future hoàn tất và mất lợi ích của việc nối xử lý bất đồng bộ.

## 5. Ghép các bước với CompletableFuture

`CompletableFuture` cho phép mô tả quan hệ phụ thuộc giữa các bước mà không phải lồng nhiều callback. Các method thường dùng:

| Method | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| `thenApply` | Biến đổi kết quả `T` thành `U` | Parse JSON, lấy body, ánh xạ DTO |
| `thenAccept` | Nhận kết quả và thực hiện hành động, trả stage `Void` | Ghi log, cập nhật kết quả, gửi thông báo nội bộ |
| `thenRun` | Chạy hành động không cần kết quả trước đó | Dọn trạng thái hoặc ghi nhận hoàn tất |
| `thenCompose` | Nối một stage mới được tạo từ kết quả stage trước | Request thứ hai phụ thuộc dữ liệu response thứ nhất |
| `thenCombine` | Kết hợp kết quả của hai stage độc lập khi cả hai hoàn tất bình thường | Ghép dữ liệu từ hai API |
| `allOf` | Hoàn tất khi tất cả future đầu vào hoàn tất | Chờ một nhóm request độc lập |
| `exceptionally` | Chuyển lỗi thành kết quả thay thế | Fallback khi request thất bại |
| `handle` | Xử lý cả kết quả lẫn lỗi | Chuẩn hóa kết quả thành một kiểu chung |
| `whenComplete` | Quan sát kết quả/lỗi mà không chủ đích thay đổi kết quả | Logging, metrics, tracing |

### Chuỗi tuần tự với `thenCompose`

Giả sử endpoint đầu tiên trả về một mã sản phẩm dạng số; request thứ hai cần mã đó để lấy chi tiết:

```java
CompletableFuture<HttpResponse<String>> detailFuture =
        client.sendAsync(
                HttpRequest.newBuilder()
                        .uri(URI.create("https://api.example.com/featured-id"))
                        .GET()
                        .build(),
                HttpResponse.BodyHandlers.ofString()
        )
        .thenApply(response -> {
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new IllegalStateException(
                        "Featured ID request failed: " + response.statusCode()
                );
            }
            return Integer.parseInt(response.body().trim());
        })
        .thenCompose(productId -> {
            HttpRequest detailRequest = HttpRequest.newBuilder()
                    .uri(URI.create(
                            "https://api.example.com/products/" + productId
                    ))
                    .GET()
                    .build();

            return client.sendAsync(
                    detailRequest,
                    HttpResponse.BodyHandlers.ofString()
            );
        });
```

`thenCompose` nhận `productId`, tạo request mới và trả về future của request đó. Kết quả cuối là `CompletableFuture<HttpResponse<String>>`, không phải `CompletableFuture<CompletableFuture<HttpResponse<String>>>`. Nếu dùng `thenApply` với hàm trả về future, bạn sẽ tạo kiểu future lồng nhau.

### Chạy song song các request độc lập

Khi hai API không phụ thuộc dữ liệu của nhau, khởi chạy cả hai trước rồi ghép kết quả:

```java
CompletableFuture<HttpResponse<String>> productsFuture =
        client.sendAsync(productsRequest, HttpResponse.BodyHandlers.ofString());

CompletableFuture<HttpResponse<String>> categoriesFuture =
        client.sendAsync(categoriesRequest, HttpResponse.BodyHandlers.ofString());

CompletableFuture<List<String>> resultFuture =
        productsFuture.thenCombine(categoriesFuture, (products, categories) -> {
            if (products.statusCode() < 200 || products.statusCode() >= 300
                    || categories.statusCode() < 200 || categories.statusCode() >= 300) {
                throw new IllegalStateException("An API returned an error status");
            }
            return List.of(products.body(), categories.body());
        });

resultFuture.thenAccept(results -> {
    System.out.println("Products: " + results.get(0));
    System.out.println("Categories: " + results.get(1));
});
```

`thenCombine` phù hợp khi chỉ ghép hai kết quả. Với nhiều request, `allOf` trả về `CompletableFuture<Void>` hoàn tất khi tất cả future đã hoàn tất:

```java
CompletableFuture<Void> all = CompletableFuture.allOf(
        productsFuture,
        categoriesFuture
);

CompletableFuture<List<String>> allBodies = all.thenApply(ignored ->
        List.of(productsFuture.join().body(), categoriesFuture.join().body())
);
```

Trong ví dụ này, `join()` được gọi bên trong bước sau `allOf`, nên hai future đầu vào đã hoàn tất trước khi lấy kết quả. Nếu một future hoàn tất exceptional, `allOf` cũng hoàn tất exceptional và bước `thenApply` không chạy bình thường.

## 6. Xử lý HTTP status và lỗi bất đồng bộ

Không nhầm lẫn lỗi HTTP với lỗi truyền tải. Response có status `404`, `401` hoặc `500` vẫn là một `HttpResponse` hợp lệ; future thường hoàn tất bình thường. Ứng dụng phải tự kiểm tra `statusCode()` để quyết định response có được xem là thành công hay không.

```java
CompletableFuture<String> bodyFuture = client.sendAsync(
        request,
        HttpResponse.BodyHandlers.ofString()
).thenApply(response -> {
    if (response.statusCode() < 200 || response.statusCode() >= 300) {
        throw new IllegalStateException(
                "HTTP status: " + response.statusCode()
        );
    }
    return response.body();
}).exceptionally(error -> {
    Throwable cause = error.getCause() != null ? error.getCause() : error;
    System.err.println("Could not load response: " + cause.getMessage());
    return "";
});
```

Các lỗi thường gặp:

- `IOException`: lỗi mạng, lỗi đọc/ghi body hoặc client đã shutdown. Khi xử lý qua `CompletableFuture`, lỗi thường xuất hiện trong exceptional completion.
- `HttpTimeoutException`: request không nhận được response trong thời gian đã cấu hình.
- `HttpConnectTimeoutException`: không thiết lập được kết nối trong thời gian connect timeout.
- `CancellationException`: future đã bị hủy.
- `CompletionException`: wrapper thường gặp khi lấy kết quả exceptional bằng `join()` hoặc trong một số bước xử lý stage.

Có ba cách xử lý lỗi phổ biến:

```java
// Chỉ chuyển lỗi thành kết quả thay thế
future.exceptionally(error -> fallbackValue);

// Xử lý cả kết quả và lỗi, rồi tạo giá trị mới
future.handle((value, error) -> {
    if (error != null) {
        return fallbackValue;
    }
    return transform(value);
});

// Quan sát để ghi log/metrics; giữ nguyên kết quả hoặc lỗi của stage
future.whenComplete((value, error) -> {
    if (error != null) {
        logger.warn("HTTP operation failed", error);
    }
});
```

`exceptionally` và `handle` có thể khôi phục pipeline bằng cách trả về giá trị. `whenComplete` thích hợp cho side effect như logging; nếu callback của nó ném lỗi, stage được trả về cũng có thể hoàn tất exceptional.

## 7. Timeout, get/join và hủy request

### Timeout ở request và kết nối

Hai timeout có phạm vi khác nhau:

- `HttpClient.Builder.connectTimeout(Duration)`: giới hạn thời gian thiết lập kết nối.
- `HttpRequest.Builder.timeout(Duration)`: giới hạn thời gian chờ response của request.

Ví dụ:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/data"))
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();
```

Đặt timeout ở request là cách trực tiếp để giới hạn thời gian của HTTP exchange. Nếu không đặt request timeout, thời gian chờ response không có giới hạn do `HttpRequest` quy định.

### Lấy kết quả bằng `get()` hoặc `join()`

Hai method đều chặn luồng gọi cho đến khi future hoàn tất:

| Method | Exception khi future lỗi | Đặc điểm |
| --- | --- | --- |
| `get()` | `ExecutionException`, đồng thời có thể ném `InterruptedException` | Phù hợp khi cần xử lý checked exception hoặc chờ có timeout qua overload `get(timeout, unit)` |
| `join()` | `CompletionException` | Không khai báo checked exception, tiện ở ranh giới đồng bộ hoặc test |

Ví dụ:

```java
try {
    HttpResponse<String> response = responseFuture.get(
            12,
            TimeUnit.SECONDS
    );
    System.out.println(response.body());
} catch (ExecutionException e) {
    System.err.println("Request failed: " + e.getCause());
} catch (TimeoutException e) {
    System.err.println("Waiting for the future timed out");
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
}
```

`get(timeout, unit)` chỉ giới hạn thời gian chờ của lời gọi `get`; nó không tự cấu hình request timeout. Nếu hết thời gian chờ, `TimeoutException` được ném ra cho luồng gọi, còn future có thể vẫn đang chạy. Dùng request timeout nếu muốn giới hạn HTTP exchange.

Không gọi `get()` hoặc `join()` trong callback bất đồng bộ để chờ một future khác có thể phụ thuộc vào cùng executor; điều này có thể gây nghẽn hoặc deadlock. Hãy dùng `thenCompose`, `thenCombine` hoặc `allOf` để mô tả quan hệ phụ thuộc.

### Hủy future

```java
CompletableFuture<HttpResponse<String>> pending = client.sendAsync(
        request,
        HttpResponse.BodyHandlers.ofString()
);

// Khi nghiệp vụ không còn cần kết quả
boolean cancellationRequested = pending.cancel(true);
```

Với built-in `HttpClient` của JDK, future trả về có thể hủy và `cancel(true)` cố gắng hủy HTTP exchange để giải phóng tài nguyên. Tuy nhiên, không có bảo đảm chính xác khi việc hủy được áp dụng. Request có thể đã được gửi và server có thể đã bắt đầu xử lý trước khi client nhận lệnh hủy. Vì vậy, không dùng cancellation làm cơ chế đảm bảo một thao tác ghi phía server chưa xảy ra.

## 8. Executor và luồng chạy callback

`sendAsync()` không có nghĩa mỗi request luôn tạo một thread mới. Built-in `HttpClient` dùng executor của client hoặc executor nội bộ để thực hiện các tác vụ bất đồng bộ. Nếu không cấu hình executor, `client.executor()` có thể trả về `Optional.empty()` dù implementation vẫn có executor mặc định không được công khai.

Các callback không có hậu tố `Async`, như `thenApply` hoặc `thenAccept`, có thể chạy trên thread hoàn tất future hiện tại hoặc thread đăng ký callback nếu future đã hoàn tất trước đó. Các method có hậu tố `Async` cho phép chuyển callback sang cơ chế thực thi bất đồng bộ. Với xử lý CPU nặng hoặc công việc blocking, nên chỉ định executor riêng:

```java
ExecutorService cpuExecutor = Executors.newFixedThreadPool(4);

CompletableFuture<ParsedResult> parsedFuture = client.sendAsync(
        request,
        HttpResponse.BodyHandlers.ofString()
).thenApplyAsync(response -> parseResponse(response.body()), cpuExecutor);
```

`parseResponse` là hàm xử lý dữ liệu của ứng dụng. Quản lý vòng đời `cpuExecutor` và chỉ shutdown sau khi các stage dùng nó đã hoàn tất. Tránh thực hiện thao tác blocking dài trong callback không chỉ định executor vì có thể làm chậm các công việc khác.

## 9. Quản lý vòng đời HttpClient

`HttpClient` là immutable và được thiết kế để tái sử dụng. Hãy tạo client ở phạm vi ứng dụng hoặc service rồi dùng cho nhiều request, thay vì tạo một client cho mỗi lần gọi API.

Từ JDK 21, `HttpClient` triển khai `AutoCloseable`. Trên JDK 26, có thể đóng client khi service dừng:

```java
HttpClient client = HttpClient.newHttpClient();

// Gửi và xử lý các request trong thời gian service hoạt động.

client.close();
```

`close()` khởi tạo orderly shutdown: các request đã gửi được phép hoàn tất, client từ chối request mới và phương thức chờ các hoạt động kết thúc. Nếu dùng try-with-resources, hãy bảo đảm các request bất đồng bộ đã được chờ hoặc pipeline của chúng đã được thiết kế để hoàn tất trong phạm vi quản lý tài nguyên. Với streaming body, luôn đóng hoặc tiêu thụ stream; nếu để stream mở, request có thể chưa được xem là hoàn tất và shutdown có thể bị giữ lại.

## 10. Chọn send hay sendAsync

| Tình huống | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| Tác vụ nền đơn giản, cần response ngay để thực hiện bước kế tiếp | `send()` | Luồng gọi chờ trực tiếp, mã dễ đọc và xử lý exception rõ ràng |
| UI hoặc server event loop cần tiếp tục nhận công việc | `sendAsync()` | Không chặn luồng gọi trong lúc chờ mạng |
| Gọi nhiều API độc lập | `sendAsync()` kết hợp `thenCombine` hoặc `allOf` | Có thể khởi chạy request trước rồi ghép kết quả khi hoàn tất |
| Request sau phụ thuộc response trước | `sendAsync()` kết hợp `thenCompose` | Nối pipeline mà không cần block để lấy kết quả trung gian |
| Tải file lớn hoặc response streaming | Cả hai đều dùng được, chọn BodyHandler phù hợp | `ofFile` hoặc streaming handler tránh giữ toàn bộ body trong bộ nhớ |
| Bài test hoặc điểm biên đồng bộ cần kết quả | `send()` hoặc chờ future có chủ đích | Dễ xác định điểm chờ và xử lý lỗi |

Đừng chọn bất đồng bộ chỉ vì nghĩ nó luôn nhanh hơn. Nếu ứng dụng chỉ có một request và cần kết quả ngay, `send()` thường dễ hiểu hơn. `sendAsync()` phát huy lợi ích khi luồng gọi cần tiếp tục làm việc, nhiều request có thể chạy độc lập, hoặc các bước xử lý có thể được ghép thành pipeline.

## Ghi nhớ

- `send()` chặn luồng gọi và trả `HttpResponse<T>`; xử lý `IOException` và `InterruptedException`.
- `sendAsync()` trả `CompletableFuture<HttpResponse<T>>`; dùng CompletionStage methods để biến đổi, ghép hoặc xử lý lỗi.
- HTTP status 4xx/5xx vẫn là response bình thường; tự kiểm tra `statusCode()`.
- `BodyHandler` quyết định kiểu body và thời điểm response được coi là đã xử lý xong.
- Dùng `thenCompose` cho các bước phụ thuộc tuần tự; `thenCombine` hoặc `allOf` cho request độc lập.
- `get()` và `join()` đều block; tránh gọi chúng bên trong callback để chờ công việc khác.
- Cancellation là best-effort; không bảo đảm server chưa nhận hoặc chưa xử lý request.
- Tái sử dụng `HttpClient`, đóng stream khi dùng streaming handler và đóng client khi service kết thúc.

## Tài liệu tham khảo

- [HttpClient, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html) — `send`, `sendAsync`, executor, cancellation và vòng đời client.
- [HttpResponse.BodyHandlers, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html) — các cách xử lý body, streaming và file.
- [HttpRequest, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpRequest.html) — timeout và cấu hình request.
- [HttpResponse, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpResponse.html) — status, headers, body và phiên bản giao thức.
- [Package `java.net.http`, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/package-summary.html) — hành vi executor và các API HTTP client hiện hành.
- [CompletableFuture, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html) — composition, exception, cancellation, `get()` và `join()`.
- [CompletionStage, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletionStage.html) — hợp đồng các thao tác kết hợp stage.
