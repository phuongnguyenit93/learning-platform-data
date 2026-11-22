# `thenApply`, `thenAccept` và `thenCompose` trong HTTP bất đồng bộ (Java 11+)

## 1. Bài toán và mục tiêu

Từ Java 11, module `java.net.http` cung cấp `HttpClient.sendAsync(...)` để gửi HTTP request mà không chặn thread của caller trong lúc đợi response:

```java
CompletableFuture<HttpResponse<String>> responseFuture =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
```

`sendAsync` trả **`CompletableFuture<HttpResponse<String>>`**. Khi request được xử lý và body hoàn tất theo `BodyHandler` đã chọn, future hoàn thành thành công với `HttpResponse<String>` hoặc hoàn thành **exceptionally** nếu gặp lỗi truyền tải, hủy, timeout hay lỗi xử lý khác.

Trong ứng dụng, ta thường cần nối những bước tiếp theo mà không phải đợi ngay bằng `join()`. Ba phương thức trọng tâm là:

- **`thenApply`:** nhận một kết quả `T`, chuyển thành giá trị mới `U`. Ví dụ: `HttpResponse<String>` → `String` → `Integer`.
- **`thenAccept`:** nhận giá trị `T` để sử dụng (in/log/gọi hàm xử lý), **không trả giá trị**; stage mới có kiểu `Void`.
- **`thenCompose`:** nhận `T`, tạo ra **một CompletionStage<U> khác**, sau đó **nối phẳng** kết quả thành một stage duy nhất. Ví dụ: lấy ID từ response A rồi gửi tiếp request B sử dụng ID đó.

Ba phương thức của `CompletableFuture` đã có trước Java 11, còn HTTP Client chuẩn có từ **Java 11 (JEP 321)**. Cả `sendAsync` và ba phương thức này **đều là API đang được hỗ trợ trong các JDK hiện đại**, không phải cách làm legacy.

## 2. So sánh kiểu dữ liệu và ý nghĩa

| Phương thức | Đầu vào callback | Callback trả về | Kiểu từ `CompletableFuture<T>` | Phù hợp |
| --- | --- | --- | --- | --- |
| `thenApply(fn)` | `T` | `U` | `CompletableFuture<U>` | Parse/chuyển dữ liệu |
| `thenAccept(action)` | `T` | `void` | `CompletableFuture<Void>` | Tiêu thụ/log/lưu kết quả |
| `thenCompose(fn)` | `T` | `CompletionStage<U>` | `CompletableFuture<U>` | Chạy tác vụ mới phụ thuộc tác vụ trước |
| `thenRun(action)` (đối chiếu) | Không nhận giá trị T | `void` | `CompletableFuture<Void>` | Chạy bước sau thành công, không cần dữ liệu trước |

Chữ ký khái niệm theo interface `CompletionStage<T>`:

```java
<U> CompletionStage<U> thenApply(
        Function<? super T, ? extends U> fn);

CompletionStage<Void> thenAccept(
        Consumer<? super T> action);

<U> CompletionStage<U> thenCompose(
        Function<? super T, ? extends CompletionStage<U>> fn);
```

Trên một đối tượng được khai báo kiểu `CompletableFuture<T>`, các phương thức tương ứng trả `CompletableFuture<U>` hoặc `CompletableFuture<Void>`. Nếu chỉ giữ tham chiếu kiểu interface `CompletionStage<T>`, compile-time return type là `CompletionStage<...>`.

Ba loại hàm được sử dụng:

- `Function<T,U>`: tính kết quả từ đầu vào, **trả `U`**.
- `Consumer<T>`: nhận và sử dụng giá trị, **không trả kết quả**.
- `Function<T,CompletionStage<U>>`: tạo **một việc bất đồng bộ tiếp theo**; cần ghép completion của việc mới.

Không đồng nhất khái niệm “đã đăng ký callback” với “callback đã chạy xong”: mỗi continuation tạo ra một **stage** có trạng thái hoàn thành riêng.

## 3. `thenApply` — chuyển một response thành dữ liệu ứng dụng

Giả sử endpoint trả HTTP 200 và body `"7"`. Ta cần một `Integer 7`:

```java
CompletableFuture<Integer> idFuture =
        client.sendAsync(idRequest,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
              .thenApply(response ->
                      Integer.parseInt(response.body().trim()));
```

Đây là đoạn **minh họa**, cần có `client`, `idRequest` và các import. Ví dụ hoàn chỉnh ở mục 7.

Diễn biến kiểu:

```text
sendAsync:  CompletableFuture<HttpResponse<String>>
thenApply:  CompletableFuture<Integer>
join():     Integer 7 (nếu đã hoàn tất bình thường)
```

`thenApply` dùng callback `Function`. Khi stage trước thành công với một `HttpResponse<String>`, callback lấy text và parse ra số. Kết quả `Integer` được dùng để hoàn thành stage mới.

Điều cần nhớ:

1. `thenApply` **chỉ chạy nếu stage nguồn hoàn thành bình thường**. Lỗi của stage trước được truyền sang stage phụ thuộc, không tự động chuyển thành một giá trị thường.
2. Nếu code trong callback ném lỗi, chẳng hạn `Integer.parseInt("oops")`, **stage mới hoàn thành exceptionally**.
3. `thenApply` không tự chạy trên thread mới; callback có thể chạy trên thread hoàn tất stage trước hoặc caller khi stage đã hoàn thành. Thảo luận ở mục 8.
4. `thenApply(HttpResponse::body)` làm stage cuối có kiểu của **body**, không còn tự chứa status và headers như `HttpResponse`. Nếu phải kiểm tra status, hãy thực hiện trước khi bỏ metadata.
5. `BodyHandlers.ofString(UTF_8)` chỉ chuyển bytes thành String. `thenApply` cũng không tự parse JSON hay validate dữ liệu: logic phải do ứng dụng hoặc thư viện chuyên dụng cung cấp.

### Kiểm tra status trước khi parse

```java
CompletableFuture<Integer> idFuture = client
        .sendAsync(idRequest,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
        .thenApply(response -> {
            if (response.statusCode() != 200) {
                throw new IllegalStateException(
                        "Unexpected HTTP status: " + response.statusCode());
            }
            return Integer.parseInt(response.body().trim());
        });
```

Đoạn này minh họa việc chủ động chuyển một response không đúng contract thành lỗi Java. **HTTP 404/503 tự thân không bắt buộc khiến `sendAsync` hoàn thành exceptionally**, vì vẫn có thể nhận được một phản hồi HTTP hợp lệ.

## 4. `thenAccept` — làm việc với kết quả nhưng không giữ giá trị trả về

Khi đã có ID:

```java
CompletableFuture<Void> done =
        idFuture.thenAccept(id -> System.out.println("ID: " + id));
```

- Callback là một `Consumer<Integer>`, **không tạo `Integer` mới**.
- Stage phụ thuộc có kiểu `CompletableFuture<Void>`. Nếu hoàn thành bình thường, `done.join()` trả `null`; điều đó **không có nghĩa tác vụ thất bại**.
- Stage `done` mô tả rằng hành động tiêu thụ đã hoàn tất, vì vậy có thể dùng `join()` hoặc một continuation khác để biết công việc đã kết thúc.
- Nếu action ném exception, `done` hoàn thành exceptionally.

**Điểm dễ sai:** Không dùng `thenAccept` để tính toán kết quả cần truyền cho bước sau. Ví dụ:

```java
CompletableFuture<String> raw = CompletableFuture.completedFuture("  Java  ");

CompletableFuture<String> cleaned = raw.thenApply(String::trim);
CompletableFuture<Void> printed = cleaned.thenAccept(System.out::println);
```

`cleaned` có giá trị `"Java"`; `printed` chỉ biểu diễn sự kiện đã in xong, không chứa chuỗi nữa. Nếu cần chuỗi ở một nhánh sau, giữ `cleaned` (hoặc dùng `thenApply` khác).

**Tác dụng phụ cần kiểm soát:** `thenAccept` thích hợp log/notify hoặc ghi dữ liệu khi contract yêu cầu, nhưng nếu gọi database/blocking HTTP/file I/O trực tiếp trong callback thông thường thì có thể giữ thread hoàn tất I/O. Với thao tác chậm, dùng `thenAcceptAsync(..., executor)` hoặc tác vụ bất đồng bộ có vòng đời/giới hạn rõ ràng.

`thenAccept` chỉ chạy khi stage trước hoàn thành thành công. Khi muốn quan sát cả lỗi và thành công, `whenComplete` hoặc `handle` phù hợp hơn.

## 5. `thenCompose` — nối request B sau response A

Giả sử API có hai bước:

1. `GET /id` cho body `"7"`.
2. Chỉ sau khi biết ID `7` mới được `GET /users/7` để lấy tên `"Lan"`.

Sử dụng `thenCompose`:

```java
CompletableFuture<String> userName =
        client.sendAsync(idRequest,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
              .thenApply(response ->
                      Integer.parseInt(response.body().trim()))
              .thenCompose(id -> {
                  HttpRequest detail = HttpRequest.newBuilder(
                          URI.create(base + "/users/" + id))
                          .GET().build();
                  return client.sendAsync(
                          detail,
                          HttpResponse.BodyHandlers.ofString(
                                  StandardCharsets.UTF_8));
              })
              .thenApply(response -> response.body().trim());
```

Đây là **mã minh họa**: cần `idRequest`, `client`, `base`, các import, và endpoint thực tế. Ví dụ hoàn chỉnh chạy trên loopback ở mục 7.

Dòng dữ liệu:

```text
GET /id
  -> CompletableFuture<HttpResponse<String>>
  -> thenApply: String "7" thành Integer 7
  -> CompletableFuture<Integer>
  -> thenCompose: dùng 7 khởi tạo GET /users/7
  -> CompletableFuture<HttpResponse<String>>
  -> thenApply: lấy tên "Lan"
  -> CompletableFuture<String>
```

**`thenCompose` tự nó không gọi mạng**: callback trong ví dụ gọi `client.sendAsync(...)` để khởi động request tiếp theo. `thenCompose` bảo đảm stage kết quả phản ánh completion của stage mà callback trả về. Callback **không chặn** để đợi request B; nó tạo future B rồi trả ngay.

### 5.1. Tránh future lồng nhau

Sai khi mục tiêu là chờ kết quả cuối của request B:

```java
CompletableFuture<CompletableFuture<HttpResponse<String>>> nested =
        idFuture.thenApply(id ->
                client.sendAsync(
                        HttpRequest.newBuilder(
                                URI.create(base + "/users/" + id))
                                .GET().build(),
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8)));
```

`thenApply` nhận một `Function<Integer, CompletableFuture<HttpResponse<String>>>` nên result là **`CompletableFuture<CompletableFuture<HttpResponse<String>>>`**. Outer future hoàn thành khi **future B được tạo ra**, không đợi response của B. `nested.join()` trả **một future**, không trả HTTP response.

Đúng:

```java
CompletableFuture<HttpResponse<String>> flat =
        idFuture.thenCompose(id ->
                client.sendAsync(
                        HttpRequest.newBuilder(
                                URI.create(base + "/users/" + id))
                                .GET().build(),
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8)));
```

Bây giờ `flat` là future duy nhất đại diện cho kết quả cuối của request B. `thenCompose` có vai trò gần `flatMap` trên Stream/Optional, còn `thenApply` gần `map`.

### 5.2. Stage trước thất bại thì sao?

Nếu `idFuture` hoàn thành exceptionally, lambda trong `thenCompose` **không được chạy**, tức request B **không được khởi động bởi lambda đó**. Stage sau cũng hoàn thành lỗi theo quy tắc `CompletionStage`. Nếu muốn fallback ID rồi thử bước tiếp theo, phải xử lý lỗi có chủ đích (`exceptionally` hoặc `handle`) **trước** bước `thenCompose`, và chỉ làm thế khi nghiệp vụ cho phép.

`thenCompose` cũng không đảm bảo request B thành công: nếu response B fail do mạng, timeout hay callback của stage B ném lỗi, stage phẳng phản ánh thất bại đó. Vì vậy phải đặt xử lý lỗi thích hợp **ở cuối pipeline** hoặc tại các ranh giới có ngữ nghĩa riêng.

## 6. Nếu hai request độc lập: `thenCombine` thay vì `thenCompose`

`thenCompose` dành cho **quan hệ phụ thuộc**: cần kết quả A để tạo yêu cầu B. Nếu A/B độc lập, có thể khởi động cả hai không cần chờ nhau:

```java
CompletableFuture<String> a = client
        .sendAsync(requestA, HttpResponse.BodyHandlers.ofString())
        .thenApply(HttpResponse::body);

CompletableFuture<String> b = client
        .sendAsync(requestB, HttpResponse.BodyHandlers.ofString())
        .thenApply(HttpResponse::body);

CompletableFuture<String> merged =
        a.thenCombine(b, (left, right) -> left + " | " + right);
```

Đây là đoạn **minh họa** cần `client`, `requestA`, `requestB`. Hai `sendAsync` được gọi độc lập, có thể chạy đồng thời. `thenCombine` kết hợp khi cả hai hoàn thành bình thường; còn `CompletableFuture.allOf(...)` có thể dùng để đợi nhiều stage nhưng **không tự gom danh sách kết quả có kiểu**.

Bảng lựa chọn nhanh:

| Mục tiêu | API |
| --- | --- |
| `HttpResponse<String> → String` | `thenApply(HttpResponse::body)` |
| `String → Integer` | `thenApply(Integer::parseInt)` |
| `Integer → log` | `thenAccept(System.out::println)` |
| `ID → khởi động một GET khác dựa vào ID` | `thenCompose(id -> sendAsync(...))` |
| Hai GET độc lập rồi ghép body | `thenCombine(...)` |
| Bước không cần nhận giá trị stage trước | `thenRun(...)` |

## 7. Ví dụ Java 11 đầy đủ: ba phương thức, HTTP lỗi và lỗi parse

Chương trình sử dụng HTTP server nhỏ trong module `jdk.httpserver` để trả kết quả **trên 127.0.0.1, cổng tự chọn**. Không cần Internet và không gọi API bên ngoài.

Endpoints:

- `/id` → HTTP 200, body `"7"`.
- `/users/7` → HTTP 200, body `"Lan"`.
- `/error` → HTTP 503, body `"unavailable"`.
- `/bad` → HTTP 200, body `"oops"`.

Tạo tệp **`AsyncStagesDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class AsyncStagesDemo {
    static void respond(HttpExchange exchange, int status, String message)
            throws IOException {
        byte[] data = message.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders()
                .set("Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(status, data.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(data);
        } finally {
            exchange.close();
        }
    }

    static HttpRequest request(String url) {
        return HttpRequest.newBuilder(URI.create(url))
                .timeout(Duration.ofSeconds(5)).GET().build();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/id", ex -> respond(ex, 200, "7"));
        server.createContext("/users/7", ex -> respond(ex, 200, "Lan"));
        server.createContext("/error", ex -> respond(ex, 503, "unavailable"));
        server.createContext("/bad", ex -> respond(ex, 200, "oops"));
        server.start();
        try {
            String base = "http://127.0.0.1:" + server.getAddress().getPort();
            HttpClient client = HttpClient.newHttpClient();

            CompletableFuture<Integer> idFuture =
                    client.sendAsync(request(base + "/id"),
                            HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
                            .thenApply(response ->
                                    Integer.parseInt(response.body().trim()));
            System.out.println("thenApply id: " + idFuture.join());

            CompletableFuture<Void> accepted = idFuture.thenAccept(
                    id -> System.out.println("thenAccept consumed: " + id));
            System.out.println("thenAccept result null: " + (accepted.join() == null));

            CompletableFuture<String> nameFuture =
                    client.sendAsync(request(base + "/id"),
                                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
                            .thenApply(response ->
                                    Integer.parseInt(response.body().trim()))
                            .thenCompose(id ->
                                    client.sendAsync(request(base + "/users/" + id),
                                            HttpResponse.BodyHandlers.ofString(
                                                    StandardCharsets.UTF_8)))
                            .thenApply(response -> response.body().trim());
            System.out.println("thenCompose name: " + nameFuture.join());

            CompletableFuture<Integer> errorStatus =
                    client.sendAsync(request(base + "/error"),
                                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
                            .thenApply(HttpResponse::statusCode);
            System.out.println("HTTP status without guard: " + errorStatus.join());

            CompletableFuture<String> guarded =
                    client.sendAsync(request(base + "/error"),
                                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
                            .thenApply(response -> {
                                if (response.statusCode() >= 400) {
                                    throw new IllegalStateException(
                                            "HTTP " + response.statusCode());
                                }
                                return response.body();
                            })
                            .exceptionally(error -> "fallback");
            System.out.println("guarded HTTP status: " + guarded.join());

            CompletableFuture<Integer> parseBad =
                    client.sendAsync(request(base + "/bad"),
                                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
                            .thenApply(response ->
                                    Integer.parseInt(response.body().trim()));
            try {
                parseBad.join();
            } catch (CompletionException error) {
                Throwable cause = error;
                while (cause.getCause() != null) cause = cause.getCause();
                System.out.println("parse failure: " + cause.getClass().getSimpleName());
            }
        } finally {
            server.stop(0);
        }
    }
}
```

**Chạy bằng JDK 11 trở lên.** `jdk.httpserver` dùng cho server kiểm thử; `HttpClient` thuộc module chuẩn `java.net.http`:

```bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 AsyncStagesDemo.java
java --add-modules jdk.httpserver AsyncStagesDemo
```

**Đầu ra chính xác đã kiểm thử:**

```text
thenApply id: 7
thenAccept consumed: 7
thenAccept result null: true
thenCompose name: Lan
HTTP status without guard: 503
guarded HTTP status: fallback
parse failure: NumberFormatException
```

**Phân tích:**

1. `idFuture` dùng `thenApply` để chuyển body `"7"` thành `Integer 7`.
2. `accepted` dùng `thenAccept` để in `7`; `join() == null` phản ánh hoàn tất bình thường của `CompletableFuture<Void>`.
3. `nameFuture` dùng `thenCompose` để đợi response đầu có ID rồi tạo request `/users/7`, trả `String` cuối là `"Lan"`.
4. Request tới `/error` vẫn trả `HttpResponse` với `statusCode()==503`; Java không tự ném lỗi chỉ vì HTTP status 503.
5. `guarded` chủ động ném `IllegalStateException` khi gặp status >= 400, sau đó `exceptionally` cung cấp giá trị dự phòng `"fallback"`.
6. `parseBad` bị `NumberFormatException` trong `thenApply`; `join()` ném `CompletionException`, ví dụ lần theo `getCause()` để in nguyên nhân gốc.
7. Các lệnh `join()` được dùng **trong chương trình thử nghiệm** để các dòng stdout có thứ tự xác định; thực tế không nên gọi ngay `join()` sau mỗi `sendAsync` nếu muốn duy trì lợi ích bất đồng bộ.

Module `jdk.httpserver` chỉ là công cụ mô phỏng endpoint trên máy, không bắt buộc với hệ thống production dùng `HttpClient`. Server được dừng trong `finally`.

## 8. Thread, `Async` và executor

Các phương thức `thenApply`, `thenAccept`, `thenCompose` không có hậu tố `Async` **không cam kết callback chạy trên thread mới**. Theo hợp đồng `CompletableFuture`, continuation có thể được chạy bởi **thread hoàn tất stage nguồn**, hoặc thread khác có thao tác completion, bao gồm caller khi đăng ký continuation cho stage đã hoàn tất.

Các biến thể:

- `thenApplyAsync(fn)`, `thenAcceptAsync(action)`, `thenComposeAsync(fn)`: lập lịch hành động qua cơ chế executor mặc định của `CompletableFuture`.
- `thenApplyAsync(fn, executor)` và các biến thể tương ứng: **chọn executor tường minh**, thường phù hợp khi parse CPU-intensive hoặc muốn cô lập tác vụ khác.
- Theo Javadoc Java 11, `CompletableFuture` thông thường dùng `ForkJoinPool.commonPool()` cho async methods không chỉ định executor, với một số ngoại lệ về parallelism hoặc subclass. **Đừng mặc định đây là executor của `HttpClient`**, và đừng giả định mọi callback chạy trên một thread cụ thể.

Đoạn minh họa:

```java
ExecutorService parsingPool = Executors.newFixedThreadPool(2);
try {
    CompletableFuture<Integer> parsed = client
            .sendAsync(request, HttpResponse.BodyHandlers.ofString(
                    StandardCharsets.UTF_8))
            .thenApplyAsync(
                    response -> Integer.parseInt(response.body().trim()),
                    parsingPool);

    Integer value = parsed.join();
} finally {
    parsingPool.shutdown();
}
```

Đoạn này cần các import `ExecutorService`, `Executors`, `CompletableFuture`, `HttpResponse`, `StandardCharsets` và biến `client`/`request`; **không chạy độc lập**. Trong ứng dụng thực tế, nên quản lý executor dùng chung theo vòng đời hệ thống, thay vì tạo một pool cho từng HTTP call.

**Không phải mọi callback đều cần `Async`.** Nếu chỉ lấy `HttpResponse::body` hay kiểm tra một trường đơn giản, `thenApply` thường đủ. Nếu callback phải chờ database hoặc I/O blocking, không block thread hoàn tất HTTP lâu; dùng tác vụ bất đồng bộ hoặc executor phù hợp.

Bất đồng bộ cũng **không đồng nghĩa luôn chạy song song**: với `thenCompose`, request B **phụ thuộc** vào A nên chỉ được tạo khi A có kết quả. Hai request độc lập mới có thể chạy đồng thời nếu cùng được khởi động sớm.

## 9. Xử lý lỗi và điều kiện hoàn tất

### 9.1. Phân biệt HTTP status với lỗi CompletableFuture

| Loại | Ví dụ | Outcome điển hình |
| --- | --- | --- |
| HTTP status lỗi nghiệp vụ | `404`, `503` | Vẫn có thể có `HttpResponse` hợp lệ; future hoàn thành bình thường |
| Lỗi mạng/thời gian | DNS, kết nối, TLS, timeout | `sendAsync` có thể hoàn thành exceptionally |
| Lỗi mapper/action | `Integer.parseInt("oops")` | Stage `thenApply` và các continuation success-only phía sau thất bại |
| Hủy bỏ | `cancel(...)` | Future có thể hoàn thành với `CancellationException`; không phải rollback server |

`thenApply`, `thenAccept`, `thenCompose` **chỉ chạy callback khi upstream hoàn thành bình thường**. Nếu một bước fail và không được recover, các stage phụ thuộc success-only không chạy callback của chúng.

### 9.2. `exceptionally`, `handle` và `whenComplete`

```java
CompletableFuture<String> output = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .thenApply(response -> {
            if (response.statusCode() >= 400) {
                throw new IllegalStateException("HTTP " + response.statusCode());
            }
            return response.body();
        })
        .exceptionally(error -> "fallback");
```

Ở đây `exceptionally` **chỉ chạy khi có lỗi** và cung cấp kết quả `String` thay thế. Nếu response thành công, stage giữ body gốc.

Khác biệt:

- **`exceptionally(Function<Throwable,T>)`:** trả fallback **cùng kiểu T** khi lỗi.
- **`handle(BiFunction<T,Throwable,U>)`:** chạy với **thành công hoặc lỗi**, trả kết quả kiểu U tùy logic.
- **`whenComplete(BiConsumer<T,Throwable>)`:** dùng để quan sát/log cả hai trạng thái; về cơ bản **giữ nguyên kết quả/lỗi** khi callback không ném lỗi, không phải cách chính để đổi giá trị.

Với future kiểu `CompletableFuture<Integer>`, callback của `exceptionally` phải trả `Integer`, không thể tự trả `String` nếu chưa đổi kiểu pipeline. **Vị trí đặt bước recovery quyết định loại giá trị được phép trả.**

### 9.3. `join()`, `get()`, timeout và cancellation

- `join()` **có thể block** nếu stage chưa xong; khi lỗi thường ném `CompletionException` (unchecked) với cause; khi bị hủy có thể ném `CancellationException`.
- `get()` cũng block, nhưng ném `ExecutionException` (checked) hoặc `InterruptedException`; `get(timeout, unit)` còn có thể ném `TimeoutException`.
- `HttpRequest.Builder.timeout(Duration)` xác lập timeout của **request HTTP**. `CompletableFuture.orTimeout(...)` hoặc `get(timeout, unit)` là cách khác để quản lý giới hạn thời gian của **future/chờ kết quả**; không đồng nhất ngữ nghĩa của chúng.
- Hủy future/HTTP request không đảm bảo server chưa nhận request. Không xem `cancel()` là rollback một thao tác ghi dữ liệu từ xa; với retry cần chính sách idempotency phù hợp.
- Trong ứng dụng bất đồng bộ, ưu tiên tiếp nối bằng stage; dùng `join()` tại ranh giới phù hợp như entry point, test hoặc khi buộc phải đồng bộ, **không block trong completion callback hay UI thread**.

## 10. Lỗi thường gặp

| Lỗi/hiểu nhầm | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Tưởng `thenApply` chạy thread mới | Non-async continuation có thể chạy tại thread hoàn tất/caller | Không suy luận thread; dùng `thenApplyAsync(..., executor)` khi cần |
| Dùng `thenAccept` để tạo giá trị cho bước sau | `Consumer` trả `void`; stage mới là `Void` | Dùng `thenApply`, giữ stage kết quả T |
| Dùng `thenApply(id -> sendAsync(...))` | Tạo `CompletableFuture<CompletableFuture<...>>` | Dùng `thenCompose` để nối phẳng |
| Dùng `thenCompose` với callback trả giá trị thường | Cần trả `CompletionStage<U>` | Dùng `thenApply` |
| Tưởng HTTP 503 luôn làm `sendAsync` fail | HTTP status khác lỗi transport | Kiểm tra `response.statusCode()` và tự quyết định |
| Tưởng `thenAccept` chạy kể cả khi upstream fail | Success-only callback sẽ bị bỏ qua | Dùng `whenComplete`/`handle` hoặc recovery |
| `join()` ngay sau từng `sendAsync` | Đang đợi đồng bộ từng tác vụ | Khởi tạo future sớm, nối continuation, chỉ join khi cần |
| `thenApplyAsync` bị nhầm là luôn dùng executor HttpClient | Executor mặc định thuộc CompletableFuture | Cấp `Executor` tường minh khi quan trọng |
| Hai request độc lập nối qua `thenCompose` | Tạo phụ thuộc không cần thiết | Dùng `thenCombine`/`allOf` |
| Mapper ném `NumberFormatException` | Body sai định dạng | Validate status/content trước khi parse, xử lý exception |
| `exceptionally` trả giá trị sai kiểu | Fallback phải phù hợp với T của stage hiện tại | Đặt recovery sau bước chuyển kiểu thích hợp |
| `cancel()` được coi là undo request | Hủy là best-effort | Thiết kế retry/idempotency theo contract |
| Callback ghi mutable state không đồng bộ | Nhiều thread có thể chạy continuation | Dùng immutable values, đồng bộ hoặc cấu trúc thread-safe |

## 11. Best practices khi dùng Java 11+

1. **Tách bước rõ:** `sendAsync` cho I/O; `thenApply` cho parse/map; `thenCompose` để gọi HTTP phụ thuộc; `thenAccept` cho side effect cuối.
2. **Kiểm tra status trước khi parse** thành công. Đừng parse HTML error 503 như DTO JSON.
3. **Chọn charset rõ ràng**, ví dụ UTF-8. `String.length()` là số UTF-16 code units, không phải byte count.
4. **Hạn chế dữ liệu lớn:** `BodyHandlers.ofString()` gom toàn bộ text vào bộ nhớ; dùng handler phù hợp và quản lý tài nguyên với streaming.
5. **Tránh block completion thread** bằng I/O nặng. Với parse CPU-intensive chọn executor/async stage phù hợp.
6. **Không ép request độc lập thành chuỗi phụ thuộc.** Bắt đầu cùng lúc, ghép kết quả sau.
7. **Xử lý lỗi đầy đủ:** phân biệt HTTP status, timeout/IOException, parse exception; dùng `exceptionally`, `handle`, `whenComplete` theo mục đích.
8. **Tái sử dụng `HttpClient`** phù hợp, thay vì tạo client mới cho từng phần tử của vòng lặp.
9. **Không log secrets:** không in token, cookie, auth header hay dữ liệu cá nhân trong body.
10. **Giới hạn thời gian và cẩn trọng hủy/retry:** hủy không đảm bảo server ngừng xử lý.
11. **Không chia sẻ mutable state thiếu đồng bộ** giữa các callback.
12. **Tiếp tục dùng API hiện hành:** `CompletableFuture`/`CompletionStage` và `HttpClient.sendAsync` vẫn được hỗ trợ, và ví dụ `--release 11` đã được kiểm thử.

## 12. Tự kiểm tra

**Câu 1:** `sendAsync(...).thenApply(HttpResponse::body)` trả kiểu gì khi dùng `BodyHandlers.ofString(UTF_8)`?  
**Đáp án:** `CompletableFuture<String>`, không phải `CompletableFuture<HttpResponse<String>>`.

**Câu 2:** `thenAccept(System.out::println)` trả kiểu nào?  
**Đáp án:** `CompletableFuture<Void>`. Khi thành công, `join()` trả `null`.

**Câu 3:** Tại sao `thenApply(id -> client.sendAsync(...))` có thể gây vấn đề?  
**Đáp án:** Nó tạo future lồng nhau; `thenCompose` tạo stage phẳng để quan sát kết quả request B.

**Câu 4:** Server trả 503, `sendAsync` bắt buộc fail không?  
**Đáp án:** Không. Có thể nhận một `HttpResponse` hợp lệ; chính sách lỗi HTTP do ứng dụng quyết định.

**Câu 5:** Hai request không liên quan nhau nên dùng `thenCompose` không?  
**Đáp án:** Không cần. Có thể khởi động độc lập rồi dùng `thenCombine` hoặc `allOf`.

**Câu 6:** `thenApply` chạy ở main thread hay completion thread?  
**Đáp án:** Không có thread cố định được bảo đảm; nó có thể chạy trên thread hoàn tất hoặc caller. Dùng biến thể `Async` và executor khi cần điều khiển.

**Câu 7:** Nếu mapper parse ném exception, `thenAccept` ở sau có chạy không?  
**Đáp án:** Không, trừ khi đã có bước recovery đưa pipeline về trạng thái hoàn thành bình thường.

## 13. Tổng kết

- `thenApply(Function<T,U>)` **chuyển một giá trị T thành U**; dùng khi parse/chọn dữ liệu từ `HttpResponse`.
- `thenAccept(Consumer<T>)` **sử dụng T nhưng không tạo kết quả mới**; trả `CompletableFuture<Void>`.
- `thenCompose(Function<T,CompletionStage<U>>)` **nối một stage phụ thuộc** và tránh `CompletableFuture<CompletableFuture<U>>`.
- `sendAsync` không block caller để đợi HTTP, nhưng callback non-async không được đảm bảo chạy ở thread riêng. `thenApplyAsync(..., executor)` và các overload tương ứng dùng khi cần kiểm soát executor.
- HTTP status 4xx/5xx không mặc nhiên là exceptional completion. Tách lỗi network, status và lỗi parse; sử dụng recovery đúng chỗ.
- `join()` có thể block; chỉ dùng ở ranh giới phù hợp. Với request độc lập, dùng `thenCombine` thay vì nối `thenCompose`.

**Tài liệu chính thức còn áp dụng:** [Oracle Java 11 — HttpClient.sendAsync](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html); [Oracle Java 11 — CompletionStage](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletionStage.html); [Oracle Java 11 — CompletableFuture](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletableFuture.html); [Oracle Java 26 — CompletableFuture](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html); [JEP 321 — HTTP Client Standard](https://openjdk.org/jeps/321).