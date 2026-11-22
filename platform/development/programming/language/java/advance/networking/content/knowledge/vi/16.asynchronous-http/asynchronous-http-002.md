# thenApply, thenCompose và ghép các bước phụ thuộc

## Mục tiêu bài học

Trong Java 17+, `HttpClient.sendAsync(...)` trả về một `CompletableFuture<HttpResponse<T>>`. Thay vì chặn thread để lấy kết quả HTTP rồi mới thực hiện công việc tiếp theo, ta có thể **ghép các bước phụ thuộc** thành một pipeline bất đồng bộ. Hai phép biến đổi xuất hiện liên tục trong thực tế là **`thenApply`** (biến đổi một giá trị đã sẵn sàng) và **`thenCompose`** (dùng kết quả trước để **khởi tạo và đợi** một tác vụ bất đồng bộ khác).

Sau bài này, bạn có thể:

- Giải thích `CompletableFuture<T>` / `CompletionStage<T>` và sự khác nhau giữa **đăng ký một bước** với **chặn để chờ kết quả**.
- Dùng `thenApply(Function<T,U>)` để biến đổi `HttpResponse<String>` thành body, parse ID, áp quy tắc dữ liệu hoặc dựng kết quả hiển thị.
- Dùng `thenCompose(Function<T,CompletionStage<U>>)` để nối một HTTP request thứ hai **chỉ khi** response thứ nhất có dữ liệu cần thiết.
- Phân biệt `CompletableFuture<U>` với `CompletableFuture<CompletableFuture<U>>` và lý do `thenApply` có thể tạo **future lồng nhau**.
- Phân biệt **chuỗi phụ thuộc tuần tự** với **những request độc lập chạy song song**; biết khi nào nên dùng `thenCombine` hoặc `allOf`.
- Xử lý HTTP status, lỗi network, lỗi parse, exception lan truyền, fallback và logging đúng điểm; không mặc định 4xx/5xx khiến `sendAsync` hoàn tất exceptionally.
- Hiểu `thenApplyAsync`/`thenComposeAsync`, executor, nguy cơ block callback thread, cách dùng timeout và giới hạn của cancellation.
- Chạy **hai ví dụ Java 17+** độc lập: một ví dụ HTTP loopback thực và một ví dụ thuần `CompletableFuture` minh họa khác biệt kiểu dữ liệu.

**Phạm vi:** HTTP bất đồng bộ với `java.net.http.HttpClient` và `java.util.concurrent.CompletableFuture` trong Java 17; ví dụ không truy cập Internet. Bài nói về **quan hệ phụ thuộc giữa các bước**; không xem `thenCompose` là lệnh chạy song song hoặc mặc nhiên thay thế xử lý timeout/resource cleanup.

## 1. Vì sao cần pipeline bất đồng bộ?

Giả sử muốn lấy tên của một tài nguyên mà client chỉ biết tên người dùng:

1. `GET /users/alice` trả về ID tài nguyên, chẳng hạn `42`.
2. Phải có ID ấy mới gọi `GET /items/42`.
3. Khi nhận tên tài nguyên, chuyển sang định dạng hiển thị (ví dụ chữ hoa).

Đây là **hai request có quan hệ phụ thuộc**: request thứ hai không thể có URI đầy đủ trước khi request đầu tiên trả ID. Cách đồng bộ có thể dùng `client.send(...)` hai lần, nhưng thread thực hiện sẽ **chờ I/O** ở từng lời gọi.

Cách ghép các bước:

~~~text
sendAsync(GET /users/alice)
          │
          ▼
CompletableFuture<HttpResponse<String>>
          │ thenApply: kiểm tra HTTP status, lấy body
          ▼
CompletableFuture<String>     ───── "42"
          │ thenApply: Integer.parseInt
          ▼
CompletableFuture<Integer>    ───── 42
          │ thenCompose: dùng 42 tạo GET /items/42 + sendAsync
          ▼
CompletableFuture<String>     ───── "Java NIO"
          │ thenApply: toUpperCase
          ▼
CompletableFuture<String>     ───── "JAVA NIO"
          │
          ▼
Chỉ join()/get() ở ranh giới cần kết quả
~~~

**Không chờ trong từng callback:** `sendAsync` khởi tạo HTTP exchange và trả một future. Gọi `thenApply`/`thenCompose` **gắn** hành động vào đồ thị xử lý; bình thường người gọi không phải đợi request kết thúc để dựng tiếp pipeline. Khi HTTP exchange đã hoàn tất, các dependent stages được kích hoạt theo hợp đồng.

`CompletableFuture` là cả một `Future` (có thể đợi kết quả) lẫn một `CompletionStage` (có thể ghép việc tiếp theo). Do đó, nếu chỉ nghĩ nó như `Future.get()`, bạn sẽ bỏ lỡ khả năng biểu diễn luồng xử lý dữ liệu không chặn ở các đoạn trung gian.

**Lưu ý:** không phải callback nào cũng chạy trên một thread riêng; các method không có hậu tố `Async` không hứa tạo worker mới. Chi tiết thực thi luồng sẽ được giải thích ở phần executor.

## 2. `thenApply`: biến đổi giá trị T thành U

Chữ ký Java 17:

~~~java
<U> CompletableFuture<U> thenApply(
    Function<? super T, ? extends U> function);
~~~

Điều kiện: stage trước **hoàn tất bình thường**. Khi đó hàm nhận **giá trị T** của stage trước, tính toán một **giá trị U** và stage mới hoàn tất bằng U.

Sơ đồ kiểu dữ liệu:

~~~text
CompletableFuture<T>
     .thenApply(T -> U)
                │
                ▼
        CompletableFuture<U>
~~~

Ví dụ sau là snippet Java 17 (cần import `java.util.concurrent.CompletableFuture`):

~~~java
CompletableFuture<String> text =
    CompletableFuture.completedFuture("42");

CompletableFuture<Integer> id = text.thenApply(Integer::parseInt);
CompletableFuture<String> label =
    id.thenApply(number -> "Item ID: " + number);

// id.join()    == 42
// label.join() == "Item ID: 42"
~~~

Ta có thể nối nhiều `thenApply` để **parse**, **validate**, **map** và **format**. `thenApply` phù hợp nhất cho những thao tác **đã có đủ dữ liệu** và trả về một giá trị thường, không cần một tác vụ bất đồng bộ khác.

Với HTTP:

~~~java
CompletableFuture<String> bodyStage = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString())
    .thenApply(response -> {
        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                "HTTP " + response.statusCode());
        }
        return response.body();
    });
~~~

Đoạn trên giả định `client` là `HttpClient`, `request` là `HttpRequest` đã build và import `java.net.http.*`, `java.util.concurrent.*`. `sendAsync` trả `CompletableFuture<HttpResponse<String>>`, `thenApply` lấy response và biến thành `CompletableFuture<String>`.

**Vì sao kiểm tra status?** Nhận `HttpResponse` với HTTP `404` hoặc `500` thường **không phải** lỗi thực thi network. Future có thể hoàn tất bình thường với `statusCode() == 404`; application phải diễn giải status và quyết định có ném lỗi/đi vào fallback hay không.

### `thenApply` không có nghĩa là bất đồng bộ hơn

`thenApply` mô tả **điều kiện thực hiện** (khi stage trước bình thường) và **biến đổi giá trị**, không tự cam kết callback sẽ chạy trên một executor khác. Nếu trong callback bạn gọi `Thread.sleep`, `Future.get`, `client.send` đồng bộ hoặc CPU task dài, bạn có nguy cơ làm chậm thread chạy phần completion đó.

Dùng `thenApply` cho xử lý nhanh/không chặn. Với công việc CPU nặng cần chủ động offload sang executor; dùng `thenApplyAsync(fn, executor)` nếu policy yêu cầu một pool riêng.

## 3. `thenCompose`: trả về một stage tiếp theo rồi làm phẳng

Chữ ký Java 17:

~~~java
<U> CompletableFuture<U> thenCompose(
    Function<? super T, ? extends CompletionStage<U>> function);
~~~

Mapper nhận **T**, nhưng **trả về `CompletionStage<U>`**, không phải một U đã có sẵn. Stage được trả từ `thenCompose` sẽ hoàn tất cùng **giá trị/lỗi** của stage mới do mapper trả về (khi các điều kiện completion tương ứng được thỏa mãn).

Sơ đồ kiểu:

~~~text
CompletableFuture<T>
    .thenCompose(T -> CompletionStage<U>)
                │
                ▼
        CompletableFuture<U>
~~~

Ví dụ:

~~~java
CompletableFuture<Integer> userId =
    CompletableFuture.completedFuture(42);

CompletableFuture<String> title = userId.thenCompose(
    id -> CompletableFuture.supplyAsync(
        () -> "Title for " + id));

// title có kiểu CompletableFuture<String>, không phải nested future.
~~~

Đây là snippet minh họa, cần import `java.util.concurrent.CompletableFuture`; `supplyAsync` chỉ mô phỏng một công việc bất đồng bộ, không tự gọi HTTP. Trong bài này, tác vụ thực của mapper thường là `client.sendAsync(nextRequest, handler)`.

**Quan hệ thời gian:** `thenCompose` không khởi tạo request thứ hai trước khi stage trước hoàn tất bình thường và mapper thực thi. Nó giúp thể hiện dependency rõ ràng và tránh phải chờ `join()` trong callback.

### Ghép hai HTTP request phụ thuộc

~~~java
CompletableFuture<Integer> idFuture = client.sendAsync(
        lookupRequest, HttpResponse.BodyHandlers.ofString())
    .thenApply(response -> {
        if (response.statusCode() != 200) {
            throw new IllegalStateException("Lookup failed");
        }
        return Integer.parseInt(response.body());
    });

CompletableFuture<String> titleFuture = idFuture.thenCompose(
    id -> {
        HttpRequest second = HttpRequest.newBuilder(
                trustedBase.resolve("/items/" + id))
            .GET().build();
        return client.sendAsync(
                second, HttpResponse.BodyHandlers.ofString())
            .thenApply(response -> {
                if (response.statusCode() != 200) {
                    throw new IllegalStateException("Item failed");
                }
                return response.body();
            });
    });
~~~

Đây là **snippet**, cần khai báo trước `client`, `lookupRequest`, `trustedBase` và import `java.net.http.*`, `java.util.concurrent.*`. Chương trình đầy đủ ở phần sau có thể biên dịch/chạy độc lập.

Ở ví dụ:
- `idFuture` bình thường với `42` → mapper `thenCompose` xây URI `/items/42` và **khởi tạo request thứ hai**.
- Request thứ hai có thể mất thời gian I/O nhưng **không** làm thread gọi `thenCompose` phải chờ `client.send` đồng bộ.
- Nếu request thứ nhất lỗi (network, HTTP status được mapper chuyển thành exception, parse sai), mapper không chạy và request thứ hai **không được khởi tạo bởi nhánh này**.
- Nếu request thứ hai gặp lỗi, `titleFuture` hoàn tất exceptionally theo dependency; không tự chuyển lỗi thành chuỗi rỗng.

**Không dùng dữ liệu chưa tin cậy làm URL tùy ý:** nếu server thứ nhất trả một URL bất kỳ rồi code gọi `URI.create(value)` để fetch ngay, có nguy cơ SSRF/đổi trust boundary. Bài demo chỉ parse một ID số và dựng path dưới **cùng trusted loopback base**. Trong hệ thống thật cần validate ID, path encoding, host/redirect policy và credential scope.

## 4. Bẫy future lồng nhau với `thenApply`

Một lỗi có thể biên dịch nhưng tạo kiểu không mong muốn:

~~~java
CompletableFuture<Integer> id =
    CompletableFuture.completedFuture(42);

// mapper trả về CompletableFuture<String>:
CompletableFuture<CompletableFuture<String>> nested =
    id.thenApply(n -> CompletableFuture.completedFuture(
        "item-" + n));
~~~

Kết quả của `thenApply` chính là **U**, mà trong trường hợp này U lại là `CompletableFuture<String>`. Vậy kiểu bên ngoài là `CompletableFuture<CompletableFuture<String>>`. `nested.join()` chỉ cho một **future bên trong**, chưa phải `String`.

Sửa đúng:

~~~java
CompletableFuture<String> flat =
    id.thenCompose(n -> CompletableFuture.completedFuture(
        "item-" + n));
~~~

`flat.join()` đã là `String` vì `thenCompose` làm phẳng một tầng stage. Tương tự với HTTP:

~~~java
// Không sai về cú pháp nhưng có nested future:
CompletableFuture<CompletableFuture<HttpResponse<String>>> nested =
    id.thenApply(n -> client.sendAsync(
        requestFor(n), HttpResponse.BodyHandlers.ofString()));

// Có một future đại diện trực tiếp kết quả request thứ hai:
CompletableFuture<HttpResponse<String>> flat =
    id.thenCompose(n -> client.sendAsync(
        requestFor(n), HttpResponse.BodyHandlers.ofString()));
~~~

Hai snippet HTTP giả định `client` và hàm `requestFor(int)` đã khai báo; dùng để **so sánh chữ ký**, không phải chương trình độc lập. Trong pipeline thật, kiểu `flat` giúp gắn tiếp `thenApply(HttpResponse::body)`, `exceptionally` và timeout dễ hơn.

**Không “sửa” bằng cách `thenApply(n -> client.sendAsync(...).join())`**. Cách đó chặn thread thực thi callback tới khi HTTP thứ hai xong, làm mất lợi ích bất đồng bộ của pipeline. Dùng `thenCompose` để trả stage thay vì chờ stage.

## 5. Ví dụ độc lập A: kiểm chứng kiểu lồng nhau/làm phẳng

Lưu đầy đủ thành **`ApplyComposeTypesDemo.java`**:

~~~java
import java.util.concurrent.CompletableFuture;

public class ApplyComposeTypesDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> source =
            CompletableFuture.completedFuture(7);

        CompletableFuture<CompletableFuture<String>> nested =
            source.thenApply(n ->
                CompletableFuture.completedFuture("item-" + n));

        CompletableFuture<String> flat =
            source.thenCompose(n ->
                CompletableFuture.completedFuture("item-" + n));

        System.out.println("nested: " + nested.join().join());
        System.out.println("flat: " + flat.join());
    }
}
~~~

Biên dịch với Java 17+:

~~~bash
javac --release 17 -encoding UTF-8 ApplyComposeTypesDemo.java
java ApplyComposeTypesDemo
~~~

Stdout đã kiểm thử:

~~~text
nested: item-7
flat: item-7
~~~

Hai dòng giống nhau **về giá trị**, nhưng câu lệnh lấy giá trị khác nhau: `nested.join().join()` cần hai lần join vì hai tầng future, còn `flat.join()` chỉ cần một. Đây là minh họa thuần kiểu dữ liệu; hai future bên trong đã hoàn tất sẵn nên **không dùng nó để benchmark tốc độ bất đồng bộ**.

## 6. Ví dụ độc lập B: HTTP loopback với hai request phụ thuộc

Giờ áp dụng `thenApply` + `thenCompose` trong **một chương trình Java 17+ đầy đủ**, không phụ thuộc Internet.

Giao thức demo:
- `GET /users/alice` → HTTP `200`, body `42`.
- Dùng `42` tạo `GET /items/42` → HTTP `200`, body `Java NIO`.
- `thenApply` tiếp theo chuyển title thành `JAVA NIO`.
- `GET /missing` → HTTP `404`. Helper `bodyIfOk` sẽ ném `IllegalStateException` và `exceptionally` trả chuỗi `fallback`.

Máy chủ dùng `com.sun.net.httpserver.HttpServer` của module `jdk.httpserver`, bind **loopback `127.0.0.1`** với cổng động `0`; client dùng `java.net.http.HttpClient`. Cả hai nằm trong **cùng JVM**. Để output quyết định, chương trình **không in thứ tự chạy của threads**, chỉ in dữ liệu sau khi future kết thúc.

Lưu đầy đủ thành file **`DependentHttpDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;

public class DependentHttpDemo {
    static void reply(HttpExchange ex, int status, String value)
            throws IOException {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type",
            "text/plain; charset=utf-8");
        ex.sendResponseHeaders(status, bytes.length);
        try (OutputStream output = ex.getResponseBody()) {
            output.write(bytes);
        }
    }

    static void handle(HttpExchange ex) throws IOException {
        try {
            String path = ex.getRequestURI().getRawPath();
            if (!"GET".equals(ex.getRequestMethod())) {
                reply(ex, 405, "only GET");
            } else if ("/users/alice".equals(path)) {
                reply(ex, 200, "42");
            } else if ("/items/42".equals(path)) {
                reply(ex, 200, "Java NIO");
            } else {
                reply(ex, 404, "missing");
            }
        } finally {
            ex.close();
        }
    }

    static String bodyIfOk(HttpResponse<String> response) {
        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                "HTTP " + response.statusCode());
        }
        return response.body();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
            new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/", DependentHttpDemo::handle);
        server.start();
        try {
            URI base = URI.create(
                "http://127.0.0.1:" + server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(2))
                .build();

            HttpRequest lookup = HttpRequest.newBuilder(
                    base.resolve("/users/alice"))
                .timeout(Duration.ofSeconds(3))
                .GET().build();

            CompletableFuture<Integer> idStage = client.sendAsync(
                    lookup, HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8))
                .thenApply(DependentHttpDemo::bodyIfOk)
                .thenApply(Integer::parseInt);

            CompletableFuture<String> titleStage = idStage.thenCompose(
                id -> {
                    HttpRequest request = HttpRequest.newBuilder(
                            base.resolve("/items/" + id))
                        .timeout(Duration.ofSeconds(3))
                        .GET().build();
                    return client.sendAsync(
                            request, HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8))
                        .thenApply(DependentHttpDemo::bodyIfOk);
                });

            CompletableFuture<String> formattedStage = titleStage.thenApply(
                title -> title.toUpperCase(Locale.ROOT));

            System.out.println("id: " + idStage.join());
            System.out.println("title: " + titleStage.join());
            System.out.println("formatted: " + formattedStage.join());

            HttpRequest missing = HttpRequest.newBuilder(
                    base.resolve("/missing"))
                .timeout(Duration.ofSeconds(3))
                .GET().build();
            CompletableFuture<String> fallback = client.sendAsync(
                    missing, HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8))
                .thenApply(DependentHttpDemo::bodyIfOk)
                .exceptionally(error -> "fallback");

            System.out.println("missing: " + fallback.join());
        } finally {
            server.stop(0);
        }
    }
}
~~~

### Biên dịch và chạy

Dùng JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 DependentHttpDemo.java
java DependentHttpDemo
~~~

Stdout đã được kiểm tra bằng biên dịch `--release 17` và chạy một HTTP server/client thực trên TCP loopback:

~~~text
id: 42
title: Java NIO
formatted: JAVA NIO
missing: fallback
~~~

**Vì sao không in port?** Server bind port `0` để OS chọn cổng còn trống; client lấy bằng `server.getAddress().getPort()`. Port thực tế thay đổi, nhưng kết quả pipeline được in không phụ thuộc số port.

### Phân tích chương trình theo từng bước

1. **`HttpServer`:** route `/users/alice` và `/items/42` trả payload `text/plain; charset=utf-8`. Route không biết trả 404, method khác trả 405. Đây là server minh họa; không có database, login hay JSON parser.
2. **`HttpClient`:** một client được tạo ngoài pipeline và dùng lại cho mọi request, có connect timeout và preferred HTTP/1.1. Không tạo một client mới trong mỗi callback.
3. **`idStage`:** `sendAsync` trả `CompletableFuture<HttpResponse<String>>`; `thenApply(bodyIfOk)` ném exception nếu response không phải 200; `thenApply(Integer::parseInt)` biến chuỗi `"42"` thành `int 42`.
4. **`titleStage`:** `idStage.thenCompose(id -> ...)` chỉ xây request `/items/42` sau khi có ID. Mapper trả về **future của `sendAsync` thứ hai**, đã được map tới `String`. `thenCompose` flatten thành `CompletableFuture<String>`.
5. **`formattedStage`:** `thenApply` là phép chuyển đổi thuần dữ liệu: `Java NIO` thành `JAVA NIO`, không phát thêm HTTP.
6. **`join()`:** chỉ được gọi **sau khi các stages đã được tạo** và tại ranh giới để in kết quả. Nó có thể block thread `main`; pipeline không dùng `join` trong các callbacks.
7. **`fallback`:** HTTP `404` vẫn có thể trả `HttpResponse` thành công ở tầng transport; `bodyIfOk` ném `IllegalStateException`, stage chuyển sang exceptional và `exceptionally` phục hồi chuỗi `fallback`.
8. **Resource cleanup:** `try/finally` dừng HTTP server sau khi cả hai chuỗi đã được đợi trong đường bình thường. Trong hệ thống thật cần quản lý cả những futures còn pending khi lỗi khiến main thoát sớm; demo không phải lifecycle manager production.

### Vì sao `idStage.join()` xuất hiện trước `titleStage.join()` mà vẫn bất đồng bộ?

Bởi `titleStage` và `formattedStage` **đã được khai báo/đăng ký trước** khi `join` xuất hiện. Khi request đầu tiên trả ID, HTTP request thứ hai được kích hoạt tự động theo dependency. `join` sau cùng chỉ để console demo chờ kết quả trước khi process kết thúc.

Nếu viết `idStage.join()` **giữa** bước lấy ID và tạo `titleStage`, người gọi sẽ đợi ở giữa và làm mất lợi ích ghép pipeline. Cách tốt hơn cho ứng dụng bất đồng bộ là return `CompletableFuture<String>` cho caller, chứ không phải `join` ngay trong service method.

## 7. Type-flow: theo dõi kiểu dữ liệu để tránh nhầm

Hãy ghi rõ kiểu của từng stage:

| Biểu thức | Kiểu trả về |
|---|---|
| `client.sendAsync(req, BodyHandlers.ofString())` | `CompletableFuture<HttpResponse<String>>` |
| `.thenApply(HttpResponse::body)` | `CompletableFuture<String>` |
| `.thenApply(Integer::parseInt)` | `CompletableFuture<Integer>` |
| `.thenApply(id -> client.sendAsync(...))` | `CompletableFuture<CompletableFuture<HttpResponse<String>>>` |
| `.thenCompose(id -> client.sendAsync(...))` | `CompletableFuture<HttpResponse<String>>` |
| `.thenCompose(id -> client.sendAsync(...).thenApply(HttpResponse::body))` | `CompletableFuture<String>` |
| `.thenApply(s -> s.toUpperCase(Locale.ROOT))` trên string stage | `CompletableFuture<String>` |
| `.thenAccept(System.out::println)` | `CompletableFuture<Void>` |
| `.thenRun(() -> metric.increment())` | `CompletableFuture<Void>` |

`thenApply` là phép **map** một giá trị; `thenCompose` tương tự phép **flatMap** với một nguồn dữ liệu bất đồng bộ. Đừng lựa chọn chỉ dựa trên “method nào nghe có vẻ async hơn”; hãy nhìn **kiểu hàm lambda trả về**.

Câu hỏi quyết định:

> Lambda của tôi trả về **U** đã có, hay trả về **CompletionStage<U>** mà tôi phải đợi?

- Trả U → `thenApply`.
- Trả `CompletionStage<U>` → `thenCompose`.
- Chỉ cần hành động phụ và không cần giá trị mới → `thenAccept` hoặc `thenRun`, nhưng phải quản lý tác dụng phụ và exception.
- Cần phối hợp **hai kết quả độc lập** → `thenCombine`/`allOf` (khác bài toán dependency tuần tự).

## 8. Ghép bước phụ thuộc không đồng nghĩa chạy song song

Hai request phụ thuộc:

~~~text
t0: GET /users/alice bắt đầu
t1: Response user hoàn tất, parse ID = 42
t2: GET /items/42 bắt đầu
t3: Response item hoàn tất, format title

        Request #1 ────────┐
                           └── Request #2 ─────────┐
                                                   └─ Format
~~~

Vì request thứ hai **phụ thuộc ID của request thứ nhất**, không thể có hai request đồng thời từ đầu mà vẫn đúng semantics.

Ngược lại, nếu cần tải `/settings` và `/profile` mà không phụ thuộc nhau, khởi tạo hai futures rồi dùng `thenCombine`:

~~~java
CompletableFuture<String> settings = client.sendAsync(
        settingsRequest, HttpResponse.BodyHandlers.ofString())
    .thenApply(HttpResponse::body);

CompletableFuture<String> profile = client.sendAsync(
        profileRequest, HttpResponse.BodyHandlers.ofString())
    .thenApply(HttpResponse::body);

CompletableFuture<String> combined = settings.thenCombine(
    profile, (a, b) -> "settings=" + a + ", profile=" + b);
~~~

Đây là snippet, cần `client`, `settingsRequest`, `profileRequest` và import `java.net.http.*` / `java.util.concurrent.*`. Hai `sendAsync` được khởi tạo **độc lập**, nên chúng **có thể overlap** trong quá trình HTTP, dù mức đồng thời thực phụ thuộc client/server/connection limits. `thenCombine` chạy sau khi **cả hai** hoàn tất bình thường.

`CompletableFuture.allOf(f1, f2, ...)` cũng chờ một nhóm future hoàn tất, nhưng **trả `CompletableFuture<Void>`**, không tự gom result list hay bảo đảm mọi tác vụ phải thành công. Khi cần lấy giá trị, truy cập futures thành phần sau `allOf` và quản lý exception/cancellation.

Nếu dữ liệu của request B cần kết quả A, **không dùng `allOf` để giả vờ song song**; hãy biểu diễn phụ thuộc bằng `thenCompose`.

## 9. Lỗi lan truyền giữa các bước

Một stage có thể kết thúc:
- **Normally:** có giá trị kết quả, kể cả `null` nếu API cho phép.
- **Exceptionally:** lỗi network, exception trong mapper, body subscriber, lỗi parse hoặc cancellation.
- **Cancelled:** future bị hủy theo semantics `CompletableFuture`; cancellation cũng được xem là dạng hoàn tất đặc biệt có exception.

Với chuỗi:

~~~text
HTTP 1 -> validate status -> parse ID -> HTTP 2 -> validate -> format
                │
                ├── lỗi HTTP status do app chuyển thành exception
                │
                └── lỗi parse / network
                         │
                         ▼
                Success-only steps tiếp theo bị bỏ qua
                         │
                         ▼
                    exceptionally / handle
~~~

**Quy tắc:** `thenApply` và `thenCompose` chỉ chạy callback khi stage trước **hoàn tất bình thường**. Nếu trước đó đã exceptionally completed, stage phụ thuộc thường cũng exceptional và mapper success không được gọi. Nếu lambda của mapper tự ném exception, **stage trả về** hoàn tất exceptionally.

### 9.1. HTTP status không mặc định là exception

Với `sendAsync(request, BodyHandlers.ofString())`:
- HTTP `200`: future hoàn tất bình thường với `HttpResponse`, như mong đợi.
- HTTP `404`: future **cũng có thể hoàn tất bình thường** với `HttpResponse` và `statusCode() == 404`.
- Lỗi kết nối/DNS/timeout I/O: future có thể hoàn tất exceptionally.

Vì vậy đoạn này dễ sai:

~~~java
client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
    .thenApply(HttpResponse::body)
    .exceptionally(error -> "not found");
~~~

Nếu server trả 404 **bình thường**, nhánh `exceptionally` **không nhất thiết chạy**. Đoạn trên sẽ đọc body 404 và xem như dữ liệu thành công. Cần kiểm tra status bằng mapper:

~~~java
client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
    .thenApply(response -> {
        if (response.statusCode() == 404) {
            throw new IllegalStateException("Not found");
        }
        if (response.statusCode() / 100 != 2) {
            throw new IllegalStateException(
                "HTTP " + response.statusCode());
        }
        return response.body();
    })
    .exceptionally(error -> "fallback");
~~~

Đây là snippet, cần `client` và `request`. Trong API thật nên dùng **exception type hoặc error model** để phân biệt status 404, 401, 429, 500, lỗi parse và transport. Fallback bừa cho mọi exception có thể che lỗi bảo mật hoặc khiến người dùng nhìn nhầm dữ liệu.

### 9.2. `exceptionally`, `handle` và `whenComplete`

| API | Khi nào chạy? | Có thể thay đổi giá trị cuối? | Thường dùng |
|---|---|---|---|
| `exceptionally(ex -> fallback)` | Khi stage phía trước exceptional | Có, trả **cùng kiểu T** để phục hồi | Fallback có chủ đích |
| `handle((value, error) -> result)` | Khi stage hoàn tất normally **hoặc** exceptionally | Có, có thể đổi thành kiểu U | Biến đổi tổng quát cả hai nhánh |
| `whenComplete((value, error) -> {...})` | Khi stage hoàn tất ở cả hai trạng thái | Bình thường giữ result/exception gốc; callback ném có thể ảnh hưởng | Logging/metrics/tracing |
| `thenApply(value ->...)` | Khi stage phía trước normally | Có, trả U | Biến đổi dữ liệu thành công |
| `thenCompose(value -> stage)` | Khi stage phía trước normally | Có, kết hợp với stage mới | Bước bất đồng bộ phụ thuộc |

Ví dụ:

~~~java
CompletableFuture<String> pipeline = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString())
    .thenApply(response -> {
        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                "HTTP " + response.statusCode());
        }
        return response.body();
    })
    .whenComplete((body, error) -> {
        if (error != null) {
            System.err.println("HTTP pipeline failed");
        }
    })
    .exceptionally(error -> "unavailable");
~~~

Snippet này dùng logging không chứa URI/token/response body. `whenComplete` ở đây là side effect quan sát, `exceptionally` là bước phục hồi; không cần đồng thời dùng cả hai nếu không có yêu cầu.

**Bẫy vị trí:** nếu đặt `exceptionally(error -> "42")` **trước** `thenCompose`, bước thứ hai có thể được kích hoạt với ID fallback dù request đầu lỗi. Nếu chỉ muốn fallback **sau khi cả pipeline thất bại**, gắn `exceptionally` ở cuối. Vị trí catch/recovery trong đồ thị là một phần semantics nghiệp vụ.

### 9.3. `join` và `get` khác nhau

- `future.join()` trả giá trị hoặc ném `CompletionException` (unchecked) cho exceptional completion; cancellation có thể ném `CancellationException`.
- `future.get()` trả giá trị hoặc ném `ExecutionException` (checked), `InterruptedException`; overload `get(timeout, unit)` còn có `TimeoutException`.
- `join` có thể **block thread gọi**, dù pipeline được khởi tạo nonblocking. Không gọi `join()` trong lambda để chờ HTTP tiếp theo — dùng `thenCompose`.
- Nếu xử lý lỗi, có thể cần lần theo `getCause()` thay vì hiển thị một chuỗi `CompletionException` không phân loại; không log nội dung nhạy cảm từ request/body.

## 10. Thread và hậu tố `Async`

Tên API dễ gây ngộ nhận: `thenCompose` không có hậu tố `Async` vẫn **ghép một tác vụ bất đồng bộ** nếu lambda trả `sendAsync`. `Async` trong tên method chủ yếu quy định **cách lập lịch callback** chứ không thay đổi ý nghĩa map/flatMap.

| Method | Nhiệm vụ | Chọn executor |
|---|---|---|
| `thenApply(fn)` | Map T → U, không bắt buộc offload | Callback có thể chạy trên thread hoàn tất stage hoặc caller khác theo quy tắc CF |
| `thenApplyAsync(fn)` | Map T → U với lịch chạy async | Default async execution facility của stage, thường ForkJoin common pool với `CompletableFuture` mặc định |
| `thenApplyAsync(fn, executor)` | Map T → U trên executor chỉ định | Ứng dụng quản lý executor và capacity |
| `thenCompose(fn)` | Flat-map T → CompletionStage<U> | Mapper có thể chạy inline trong lúc stage hoàn tất |
| `thenComposeAsync(fn)` | Flat-map với mapper được lên lịch async | Default async execution facility |
| `thenComposeAsync(fn, executor)` | Flat-map với mapper chạy trên executor chỉ định | Ứng dụng chọn pool; HTTP exchange vẫn do HttpClient quản lý |

**Không dựa vào tên thread/ID thread** của callback trong kiểm thử chức năng. Với non-async dependent stages, Java không cam kết luôn chạy trên một thread nhất định; callback có thể chạy trong thread hoàn tất stage hoặc thread khác tương tác với completion. Ngay cả khi `thenApplyAsync` dùng executor riêng, khi lambda trả về, hoàn tất tương ứng còn có lịch xử lý khác theo implementation.

### Khi nào cần executor riêng?

Các tác vụ như parse JSON nhỏ và chuyển đổi ID thường có thể dùng `thenApply` bình thường. Nếu bước parse/normalize thực sự nặng CPU, dùng pool CPU có giới hạn:

~~~java
ExecutorService cpu = Executors.newFixedThreadPool(2);
try {
    CompletableFuture<String> parsed =
        responseStage.thenApplyAsync(
            response -> expensiveParse(response.body()), cpu);
    String result = parsed.join();
    // Xử lý result trong ứng dụng.
} finally {
    cpu.shutdown();
}
~~~

Đây là **snippet** cần import `java.util.concurrent.*`, giả định `responseStage` là `CompletableFuture<HttpResponse<String>>` và `expensiveParse` đã được ứng dụng định nghĩa. Không đặt `cpu.shutdown()` trước khi những tác vụ cần CPU pool hoàn tất; tránh executor không giới hạn task queue dưới tải cao. Với production, quản lý cả active tasks, giới hạn queue, rejection và deadline.

Không dùng `thenApplyAsync` chỉ để “chuyển thành HTTP async”: `sendAsync` đã khởi tạo I/O bất đồng bộ. Thêm thread hop không cần thiết có thể tăng chi phí context switch và latency.

**Cẩn thận khi dùng default common pool:** tác vụ blocking dài trong common pool có thể làm chậm nhiều phần của ứng dụng. Không chạy `client.send(... )` hoặc `Thread.sleep` tùy ý trong callback common-pool; với HTTP dependent request dùng `thenCompose` và `sendAsync`.

## 11. Timeout theo từng request và timeout toàn pipeline

Trong ví dụ thực, mỗi request được cấu hình `HttpRequest.Builder.timeout(Duration.ofSeconds(3))`. Nếu có hai request phụ thuộc:

~~~text
Request #1: mất tối đa theo timeout riêng
                       │
                       ▼
Request #2: mất tối đa theo timeout riêng
                       │
                       ▼
Toàn pipeline: có thể lâu hơn một timeout đơn lẻ
~~~

**Không suy ra** “đặt timeout 3 giây cho từng request thì toàn chuỗi hoàn tất trước 3 giây”. Nếu request 1 mất gần 3 giây và request 2 mất gần 3 giây, tổng thời gian có thể lớn hơn 3 giây, chưa kể parse, queue, callback và scheduling.

### `orTimeout` và `completeOnTimeout` (Java 17)

~~~java
CompletableFuture<String> result =
    dependentPipeline.orTimeout(5, TimeUnit.SECONDS);
~~~

`orTimeout` hoàn tất future bằng `TimeoutException` khi thời gian yêu cầu qua mà future chưa xong; **nó trả lại chính CompletableFuture đó** (không tạo một future con biệt lập). `completeOnTimeout(fallback, timeout, unit)` cũng tác động lên chính future được gọi, nhưng hoàn tất bình thường bằng fallback nếu deadline đến trước.

**Rất quan trọng:** đánh dấu future timeout **không mặc nhiên là bằng chứng HTTP exchange đã dừng hoặc server chưa xử lý request**. Cần quản lý việc hủy và vòng đời network operation theo policy; cancellation trong `HttpClient` là best effort.

Nếu muốn một thời hạn **end-to-end** với nhiều requests, tính deadline chung từ `System.nanoTime()` và truyền ngân sách còn lại vào từng request khi phù hợp; sau đó kết hợp timeout của pipeline ở boundary. Hãy tính toán cả retry/backoff, không chỉ hai HTTP requests.

### Timeout vs cancel

- Request timeout: hạn chế thời gian response theo `HttpRequest.timeout`, có thể dẫn đến `HttpTimeoutException`.
- `CompletableFuture.orTimeout`: chuyển trạng thái tương lai của stage khi chưa xong.
- `future.cancel(true)`: yêu cầu cancel stage; trong `HttpClient` mặc định, các futures được hỗ trợ cancellation có thể cố hủy HTTP exchange. Không có bảo đảm thời điểm hủy được áp dụng; downstream có thể đã nhận request.
- Nếu một dependent future bị hủy, **không nên suy diễn** mọi stage upstream/downstream đều dừng ngay; phụ thuộc loại future, cấu trúc stage và implementation.

**Đừng dùng timeout làm cơ chế rollback giao dịch.** Nếu request thứ hai là POST tạo đơn hàng, hết thời gian đợi không chứng minh đơn hàng chưa được tạo.

## 12. Vấn đề resource và tính đúng đắn của HTTP body

`HttpResponse.BodyHandlers.ofString()` trong demo đưa body thành `String`. Khi stage hoàn tất bình thường, ứng dụng đã có chuỗi trả về để parse, không cần giữ một `InputStream` chưa đọc.

Với `BodyHandlers.ofInputStream()`, HTTP future có thể hoàn tất và trả `HttpResponse<InputStream>` **trước khi body được ứng dụng đọc hết**. Nếu bạn chỉ dùng `thenApply(HttpResponse::body)` để lấy stream rồi không đóng, connection/resource có thể bị giữ:

~~~java
CompletableFuture<HttpResponse<InputStream>> future =
    client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

future.thenAccept(response -> {
    try (InputStream stream = response.body()) {
        // Đọc theo giới hạn payload; hoặc đóng khi không còn cần.
    } catch (IOException error) {
        // Ghi log/khôi phục đúng ngữ cảnh ứng dụng.
    }
});
~~~

Đây là snippet cần import `java.io.*`, `java.net.http.*`, `java.util.concurrent.*`, giả định `client` và `request` đã có. **Nội dung đọc/parse thực tế chưa được viết** trong snippet vì phụ thuộc protocol; mục tiêu là cho thấy stream cần được đóng.

Nếu chain có thể hoàn tất exceptionally **sau khi đã tạo stream**, phải đảm bảo có người chịu trách nhiệm cleanup tương ứng. `BodyHandlers.ofLines()` có `Stream<String>` cần đóng khi không dùng; `ofPublisher()` cần subscriber yêu cầu dữ liệu/cancel đúng semantics.

**Trạng thái HTTP và dữ liệu chưa tin cậy:** body length, charset, JSON schema và URL từ response đều phải được validate. Một `thenApply(Integer::parseInt)` sẽ ném lỗi nếu body không phải số, điều đó không nên bị che bằng fallback mặc định `0` nếu request tiếp theo sẽ dùng ID ấy để cập nhật resource quan trọng.

## 13. Ghép callback đúng để không tạo các tác dụng phụ khó kiểm soát

### 13.1. Không tạo request trước khi có ID

Sai về dependency:

~~~java
// Không có ID từ request #1 nhưng đã muốn build request #2.
HttpRequest request2 = HttpRequest.newBuilder(
    URI.create("https://api.example.org/items/" + unknownId))
    .GET().build();
~~~

Đây là **code sai có chủ đích**, `unknownId` không tồn tại và không phải chương trình runnable. Trong bài thật, dựng URI thứ hai **bên trong mapper `thenCompose`**, sau khi ID đã parse/validate.

### 13.2. Đừng lẫn action phụ với biến đổi kết quả

`thenAccept` nhận giá trị nhưng trả `CompletableFuture<Void>`. Nếu sau đó bạn muốn tiếp tục dùng kết quả cho request phụ thuộc, đừng đặt `thenAccept(System.out::println)` vào giữa rồi cố lấy lại ID:

~~~java
CompletableFuture<Void> logged =
    idStage.thenAccept(id -> System.out.println(id));
// logged không mang Integer để thenCompose tạo request từ id.
~~~

Đây là snippet giả định `idStage` là `CompletableFuture<Integer>`. Nếu muốn quan sát mà giữ kết quả, dùng `whenComplete((id, error) -> ...)` (logging thích hợp) hoặc gắn một **nhánh** `thenAccept` riêng để không làm mất type của pipeline chính.

### 13.3. Không đếm request theo số callback

Một stage có thể có nhiều dependent branches. Nếu bạn gọi `idStage.thenCompose(...)` **hai lần** với hai lambda gửi HTTP, khi ID sẵn sàng cả hai lambda có thể khởi tạo **hai HTTP requests**. Một stage bất biến không có nghĩa downstream side effects chỉ xảy ra một lần trên toàn đồ thị.

Ví dụ:

~~~java
CompletableFuture<String> a =
    idStage.thenCompose(id -> sendDetails(id));

CompletableFuture<String> b =
    idStage.thenCompose(id -> sendDetails(id));
~~~

Đây là snippet **chỉ minh họa**; `sendDetails(int)` là hàm ứng dụng phải viết. Nếu muốn hai consumers chia sẻ **cùng kết quả request thứ hai**, tạo một `detailsStage` duy nhất rồi gắn nhiều dependent stages vào đó:

~~~java
CompletableFuture<String> detailsStage =
    idStage.thenCompose(id -> sendDetails(id));

CompletableFuture<Integer> lengthStage =
    detailsStage.thenApply(String::length);
CompletableFuture<String> upperStage =
    detailsStage.thenApply(String::toUpperCase);
~~~

Hai snippets cần `idStage` có sẵn; trường hợp production phải tính đến mã hóa Unicode/Locale khi uppercase. **Kiểm soát số HTTP exchanges** theo vị trí tạo `sendAsync`, không theo số `thenApply`.

### 13.4. Giới hạn side effects và trạng thái đồng thời

Với hệ thống thực:
- Không mutate `ArrayList` / `HashMap` không đồng bộ từ nhiều callbacks ở các threads khác nhau.
- Dùng immutable DTO khi có thể; nếu cần state chung, dùng concurrent collections, atomic operations hoặc owner-thread model.
- Giới hạn số requests in-flight; đừng tạo hàng nghìn chuỗi `thenCompose` khi người dùng gửi burst vô hạn.
- Ghi log có trace ID/correlation ID nhưng ẩn `Authorization`, cookie, token và dữ liệu nhạy cảm trong URL.
- Không làm parsing nặng ngay trong HTTP completion threads; tách CPU executor nếu có số liệu chứng minh cần.

## 14. Bảng quyết định nhanh cho API

| Bài toán | API gợi ý | Kết quả |
|---|---|---|
| Đổi `HttpResponse<String>` thành `String body` | `thenApply(HttpResponse::body)` | Future body |
| Parse body text thành ID | `thenApply(Integer::parseInt)` | Future ID |
| Có ID rồi mới phát HTTP khác | `thenCompose(id -> client.sendAsync(...))` | Future response mới, không lồng future |
| Map dữ liệu tốn CPU lớn trên pool riêng | `thenApplyAsync(fn, cpuExecutor)` | Future result trên executor chỉ định |
| Khởi tạo mapper async trên pool riêng | `thenComposeAsync(fn, executor)` | Future kết quả stage được trả |
| Hai request độc lập, cần cả hai | `thenCombine` | Future kết hợp kết quả |
| Chờ nhóm requests và tự gom results | `allOf` + đọc futures thành phần | Future báo nhóm đã hoàn tất |
| Chỉ log kết quả cuối, giữ type | `whenComplete` | Stage mới giữ result/exception gốc trong đường bình thường |
| Trả fallback cho lỗi đã phân loại | `exceptionally` hoặc `handle` | Future đã phục hồi |
| Ngừng đợi một pipeline sau hạn | `orTimeout` + cleanup/cancel policy | Future timeout, không bảo đảm HTTP đã rollback |
| Cần một giá trị tại boundary sync | `join`/`get` | Block caller; dùng có chủ đích |

Không có một phép ghép luôn đúng cho mọi request. **Hình dạng dependency** quyết định: map giá trị, flat-map một stage khác, hay combine nhiều stages độc lập.

## 15. Lỗi thường gặp và cách sửa

| Sai lầm | Vấn đề | Cách sửa |
|---|---|---|
| `thenApply` gọi `sendAsync` rồi tưởng result là `HttpResponse` | Tạo `CompletableFuture<CompletableFuture<HttpResponse>>` | Dùng `thenCompose` |
| Gọi `join` trong mapper trước request thứ hai | Block completion thread | Trả `CompletionStage` từ mapper |
| Xem `thenCompose` là tự chạy song song | Request thứ hai phụ thuộc stage trước | Phân biệt dependency với `thenCombine` |
| Cho rằng `thenApply` luôn chạy ở worker riêng | Method non-Async không bảo đảm thread | Callback nhanh; dùng `thenApplyAsync` khi cần |
| Dùng `thenApplyAsync` chỉ để biến `send` thành async | `client.send(...)` vẫn chặn worker | Dùng `client.sendAsync(...)` |
| Không kiểm tra `response.statusCode()` | 404/500 có thể vẫn là normal HTTP result | Validate status trước parse |
| Dùng `exceptionally` cho mọi lỗi để trả ID=0 | Che lỗi mạng/auth/parse, tạo request sai | Phân loại lỗi và fail closed khi cần |
| Đặt fallback giữa pipeline rồi vô tình phát request thứ hai | Success stages sau fallback lại chạy | Đặt recovery theo nghiệp vụ |
| Tưởng `join` không block vì source là future | `join` đợi cho tới completion | Chỉ join ở boundary thật sự cần |
| Gắn `thenAccept` giữa chain mà muốn tiếp tục dùng ID | Trả `CompletableFuture<Void>` | Dùng `thenApply` hoặc giữ `idStage` |
| Hai nhánh `thenCompose` cùng gọi HTTP rồi tưởng chỉ 1 request | Mỗi lambda có thể tạo exchange riêng | Chia sẻ một stage kết quả chung |
| Đọc response stream mà không close | Giữ network resource/connection | Try-with-resources / cancel |
| Đặt timeout 3s mỗi request rồi nghĩ toàn chain ≤3s | Tổng thời gian các request cộng dồn | Global deadline/budget + per-request timeout |
| `orTimeout` nghĩa là server chắc chưa xử lý POST | Timeout chỉ thay đổi trạng thái future | Idempotency/đối soát/cancellation |
| Lấy URL từ response rồi `sendAsync` ngay | Nguy cơ SSRF/credential leak | Whitelist host, validate path/redirect |
| Dùng common pool cho CPU blocking không giới hạn | Thread starvation, latency cao | Executor bounded, callback nhanh |
| Tạo HTTP client mới mỗi stage | Mất khả năng reuse tài nguyên | Reuse một `HttpClient` phù hợp |
| Không kiểm tra `Integer.parseInt` exception | Chuỗi không hợp lệ làm chain exceptional | Validate dữ liệu/exception policy |
| Cho rằng `allOf` trả về list responses | `allOf` trả `CompletableFuture<Void>` | Sau đó lấy từng future |
| Nuốt `CompletionException` khi debug | Mất nguyên nhân gốc | Phân loại nguyên nhân và log có kiểm soát |

## 16. Bài tập thực hành

1. Viết kiểu trả về của `client.sendAsync(req, BodyHandlers.ofString())`, sau đó nối `thenApply(HttpResponse::body)`. Kiểu của stage cuối là gì?
2. Nếu `CompletableFuture<Integer> id` gọi `id.thenApply(n -> client.sendAsync(requestFor(n), handler))`, kiểu kết quả là gì? Sửa thế nào để thành `CompletableFuture<HttpResponse<String>>`?
3. Trong pipeline `lookup → parse ID → fetch details`, đâu là phép `thenApply` và đâu là `thenCompose`?
4. Khi HTTP request đầu trả `404`, `sendAsync` có tự đưa exception vào future không? Khi nào mapper `thenCompose` sẽ bị bỏ qua?
5. Một parse `Integer.parseInt("oops")` ném lỗi. Request thứ hai trong `thenCompose` có được khởi tạo bởi nhánh ấy không?
6. Tại sao không nên viết `thenCompose(id -> client.sendAsync(...).join())`? Ngoài block, cú pháp đó còn không phù hợp chữ ký về kiểu trả về thế nào?
7. Hai request `/settings` và `/profile` độc lập. Nên dùng `thenCompose` hay `thenCombine` để ghép kết quả? Vì sao?
8. `thenApplyAsync(fn)` có bảo đảm callback chạy trên chính thread HTTP vừa complete stage không? `thenApply(fn)` có bảo đảm chạy thread riêng không?
9. Khi cần parsing CPU nặng, làm sao dùng executor riêng? Ai chịu trách nhiệm shutdown executor?
10. Vì sao `join` ở cuối console demo chấp nhận được, nhưng `join` trong callback HTTP thường là bẫy?
11. Nếu `exceptionally(error -> "42")` đặt ngay sau lookup, bước `thenCompose` tiếp theo sẽ làm gì khi lookup lỗi?
12. Một `BodyHandlers.ofInputStream()` trả response stream rồi pipeline không close. Tại sao đó là rò tài nguyên dù future đã hoàn tất?
13. Hai request mỗi cái có timeout 3 giây; toàn chain có bị giới hạn ở 3 giây không?
14. `CompletableFuture.orTimeout` có tự gửi “cancel request” tới server và rollback nghiệp vụ không?
15. Trong demo chạy thực, `/missing` trả HTTP code nào? Vì sao stdout lại là `missing: fallback`?
16. Phân biệt `thenAccept`, `whenComplete` và `thenApply` khi muốn vừa ghi log vừa giữ nguyên kết quả để tạo request phụ thuộc.
17. Một `idStage` có hai `thenCompose`, mỗi lambda gọi `sendAsync`. Có thể phát bao nhiêu HTTP request? Nếu chỉ muốn một, thiết kế lại thế nào?
18. Tại sao không được dùng URI tuyệt đối do response đầu trả về để gửi request thứ hai không kiểm tra?
19. `CompletableFuture.allOf(a,b)` trả kiểu gì và cách lấy dữ liệu từ `a`, `b` sau khi allOf hoàn tất?
20. Hãy thêm một bước `thenApply` cuối vào `titleStage` để trả `"Item: JAVA NIO"`. Tại sao bước này không cần request HTTP thứ ba?

**Gợi ý đáp án:**
(1) `CompletableFuture<HttpResponse<String>>` rồi `CompletableFuture<String>`; (2) nested future, sửa `thenCompose`; (3) parse/format dùng `thenApply`, HTTP phụ thuộc dùng `thenCompose`; (4) không mặc định, app phải throw khi status không chấp nhận; (5) không; (6) `join` trả giá trị thay vì `CompletionStage` và chặn thread; (7) `thenCombine` vì hai requests độc lập; (8) không, hai API có chính sách scheduling khác; (9) `thenApplyAsync(fn, cpuExecutor)`, ứng dụng quản lý pool; (10) boundary demo chủ ý đợi, callback không nên block; (11) bước hai có thể chạy với ID fallback; (12) stream đang giữ network delivery; (13) không; (14) không; (15) 404 được helper chuyển thành exception rồi `exceptionally` phục hồi; (16) `thenApply` map, `thenAccept` không giữ value, `whenComplete` quan sát; (17) có thể hai request, chia sẻ một `detailsStage`; (18) SSRF/credential scope; (19) `CompletableFuture<Void>`, lấy results từ futures thành phần; (20) chỉ xử lý chuỗi đã sẵn sàng.

## 17. Tổng kết

- **`thenApply` = map** giá trị `T → U` khi stage trước hoàn tất bình thường.
- **`thenCompose` = flatMap** giá trị `T → CompletionStage<U>`, tạo chuỗi async phụ thuộc mà không cần `join` giữa chặng; tránh nested future.
- **`HttpClient.sendAsync` + CompletableFuture** giúp viết workflow HTTP mà không chặn thread ở các bước trung gian, nhưng caller vẫn có thể block nếu cố `join`.
- **Kiểm tra HTTP status:** HTTP 4xx/5xx không mặc định khiến future exceptional; validation của ứng dụng phải rõ ràng.
- **Phân biệt dependency và parallelism:** chuỗi phụ thuộc dùng `thenCompose`, các requests độc lập dùng `thenCombine`/`allOf`.
- **Exception/callback placement quyết định semantics:** fallback đặt trước hay sau `thenCompose` có thể thay đổi việc request thứ hai có được phát hay không.
- **Async thread policy và tài nguyên:** không dùng callback nặng/blocking thiếu kiểm soát; xử lý executor, streaming bodies, timeout/cancellation và quyền truy cập URI hợp lệ.
- **Hai ví dụ Java 17 đã kiểm thử:** kiểu `nested` vs `flat`, và pipeline HTTP loopback với response thực, status 404/fallback.

### Tài liệu tham khảo

- [Oracle Java SE 17 — CompletableFuture: thenApply, thenCompose, completion policies, orTimeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Oracle Java SE 17 — CompletionStage và kiểu kết quả các phép ghép](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [Oracle Java SE 17 — HttpClient.sendAsync và cancellation](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [Oracle Java SE 17 — HttpRequest.Builder.timeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [Oracle Java SE 17 — HttpServer cho ví dụ loopback](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
