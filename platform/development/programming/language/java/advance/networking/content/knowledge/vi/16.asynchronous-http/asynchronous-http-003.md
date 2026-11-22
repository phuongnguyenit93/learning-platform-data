# Phối hợp nhiều yêu cầu độc lập bằng allOf mà vẫn giữ kết quả từng yêu cầu

## 1. Bài toán và ý tưởng fan-out / fan-in

Một Java service cần gọi ba HTTP endpoint độc lập: lấy cấu hình, lấy hồ sơ, lấy trạng thái đơn hàng. Nếu lần lượt gọi `HttpClient.send(...)` hoặc gọi `sendAsync(...).join()` ngay từng lần, ứng dụng sẽ chờ một request xong rồi mới bắt đầu request sau. Trong trường hợp các request **không phụ thuộc dữ liệu lẫn nhau**, ta có thể bắt đầu tất cả trước rồi mới chờ nhóm hoàn tất.

Mô hình gồm ba bước:

1. **Fan-out:** khởi phát nhiều request bằng `HttpClient.sendAsync(...)`, lưu **mỗi `CompletableFuture<HttpResponse<T>>`** dưới đúng tên hoặc ID request.
2. **Barrier:** tạo `CompletableFuture.allOf(...)` để biết **khi nào tất cả future đầu vào hoàn tất**.
3. **Fan-in:** đọc từng future đã giữ theo ID, lấy status/body hoặc lỗi rồi tổng hợp một kết quả có cấu trúc.

~~~text
                      fan-out
client ---> sendAsync(A) ---> futureA ----\
       \-> sendAsync(B) ---> futureB -----+--> allOf(A,B,C) -- barrier
       \-> sendAsync(C) ---> futureC ----/          |
                                                   v
                                   fan-in: đọc A, B, C theo ID ban đầu
                                                   |
                                                   v
                                        List/Map<requestId, Outcome>
~~~

**Điểm cốt lõi: `allOf` không giữ các response thay bạn.** Nó chỉ đồng bộ hóa thời điểm hoàn tất. Từng request cần future riêng và danh tính riêng. Nếu một request thất bại, dữ liệu của các request thành công **không tự biến mất**, nhưng phải xử lý lỗi đúng để không vô tình bỏ qua chúng.

Bài sử dụng Java 17+ và `java.net.http.HttpClient`. Hai chương trình chạy đầy đủ tạo server HTTP ngay trên `127.0.0.1` bằng `com.sun.net.httpserver.HttpServer`, không phụ thuộc Internet hay tài khoản dịch vụ.

## 2. Kiểu dữ liệu của sendAsync và allOf khác nhau thế nào?

| Phương thức | Kiểu trả về | Vai trò |
| --- | --- | --- |
| `client.sendAsync(request, bodyHandler)` | `CompletableFuture<HttpResponse<T>>` | Mang response của **một** HTTP request |
| `response.statusCode()` | `int` | Status HTTP, kể cả 4xx/5xx |
| `response.body()` | `T` | Body theo `BodyHandler<T>` đã chọn |
| `CompletableFuture.allOf(f1,f2,...)` | `CompletableFuture<Void>` | Hoàn tất khi **mọi future đầu vào hoàn tất** |
| `future.join()` | `T` nếu thành công; có thể ném `CompletionException` | Đọc kết quả một future |
| `future.get()` | `T` nếu thành công; ném checked exception khi lỗi | Đọc/đợi kết quả một future |
| `future.handle((value,error)->...)` | `CompletableFuture<U>` | Chuẩn hóa **cả nhánh thành công và nhánh lỗi** |
| `future.thenApply(value->...)` | `CompletableFuture<U>` | Biến đổi giá trị khi upstream thành công |

Trường hợp `HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)`, mỗi future từ `sendAsync` có dạng `CompletableFuture<HttpResponse<String>>`. Response chứa status, headers và String body đã được body handler xử lý. Với body handler **streaming** như `ofInputStream()`, future có thể hoàn tất khi stream sẵn sàng dù ứng dụng còn phải đọc/đóng stream đó sau.

Chữ ký quan trọng của API:

~~~java
public static CompletableFuture<Void> allOf(
        CompletableFuture<?>... cfs)
~~~

*Đây là chữ ký minh họa của `CompletableFuture.allOf` trong JDK, không phải phương thức cần tự cài đặt.*

`Void` ở đây có nghĩa: barrier **không trả List của các kết quả con**. Khi `allOf` thành công, `join()` của barrier có giá trị `null`; các kết quả phải lấy từ từng `f1/f2/...`. Nếu muốn một `CompletableFuture<List<T>>`, phải **tự tạo giai đoạn tổng hợp** từ future con sau barrier.

## 3. Sai lầm hay gặp: join quá sớm khiến chương trình tuần tự

Ví dụ **không nên viết** nếu A, B và C độc lập:

~~~java
HttpResponse<String> a =
        client.sendAsync(requestA, HttpResponse.BodyHandlers.ofString()).join();
HttpResponse<String> b =
        client.sendAsync(requestB, HttpResponse.BodyHandlers.ofString()).join();
HttpResponse<String> c =
        client.sendAsync(requestC, HttpResponse.BodyHandlers.ofString()).join();
~~~

*Đoạn minh họa trong class đã có `client` và ba request, không phải chương trình chạy độc lập.*

Mặc dù tên API là `sendAsync`, ở dòng đầu thread caller đợi A hoàn tất **trước khi gọi `sendAsync` cho B**. Thời gian chờ có thể gần tổng thời gian ba request.

Khởi phát trước, chờ sau:

~~~java
CompletableFuture<HttpResponse<String>> fa =
        client.sendAsync(requestA, HttpResponse.BodyHandlers.ofString());
CompletableFuture<HttpResponse<String>> fb =
        client.sendAsync(requestB, HttpResponse.BodyHandlers.ofString());
CompletableFuture<HttpResponse<String>> fc =
        client.sendAsync(requestC, HttpResponse.BodyHandlers.ofString());

CompletableFuture<Void> all = CompletableFuture.allOf(fa, fb, fc);
all.join();

HttpResponse<String> a = fa.join();
HttpResponse<String> b = fb.join();
HttpResponse<String> c = fc.join();
~~~

*Đoạn minh họa chỉ phù hợp nhánh **mọi request thành công**. Khi bất kỳ future đầu vào nào exceptional, `all.join()` có thể ném exception; cách giữ kết quả tốt và lỗi được trình bày phía dưới.*

Vì `fa`, `fb` và `fc` được tạo trước `all.join()`, các yêu cầu **có thể đang thực thi đồng thời**, chịu giới hạn HTTP client, connection pool và server. `allOf` **không khởi tạo request mới, không tạo response và không tự làm network I/O**; các hoạt động đó đã được kích hoạt bởi `sendAsync`.

## 4. allOf có thực sự đợi mọi future không? Trạng thái lỗi ra sao?

Theo Javadoc `CompletableFuture`:

- `allOf` hoàn tất khi **tất cả** future đầu vào hoàn tất.
- Nếu một hoặc nhiều future đầu vào **exceptionally completed**, future của `allOf` **cũng exceptionally completed**.
- `allOf` **không tự trả kết quả** từ các future đầu vào.
- `CompletableFuture.allOf()` không có phần tử trả về future đã hoàn tất bình thường với giá trị `null`.
- Nếu mảng hoặc bất kỳ phần tử future nào là `null`, `allOf` ném `NullPointerException`.

Ví dụ:

~~~text
A: completed normally -> HttpResponse A
B: completed exceptionally -> IOException B
C: completed normally -> HttpResponse C

allOf(A,B,C): completed exceptionally khi nhóm hoàn tất
A: vẫn giữ response A
B: vẫn giữ exception B
C: vẫn giữ response C
~~~

**Không suy ra `allOf` là fail-fast và hủy tất cả future con khi một future lỗi.** Những request khác có thể tiếp tục chạy và hoàn tất. Khi nhiều request lỗi, không dựa vào loại lỗi do barrier ném để biết **đầy đủ mọi lỗi**; phải kiểm tra từng future hoặc outcome.

Một câu lệnh sai kiểu:

~~~java
// Cố ý không biên dịch: allOf trả CompletableFuture<Void>, không phải List.
CompletableFuture<List<HttpResponse<String>>> results =
        CompletableFuture.allOf(fa, fb, fc);
~~~

Muốn biến barrier thành future mang danh sách, khi đã biết mọi future con thành công:

~~~java
CompletableFuture<List<HttpResponse<String>>> combined =
        CompletableFuture.allOf(fa, fb, fc)
                .thenApply(ignored -> List.of(
                        fa.join(), fb.join(), fc.join()));
~~~

*Hai đoạn trên là minh họa riêng: đoạn đầu **cố ý sai kiểu**, đoạn thứ hai yêu cầu những biến `fa/fb/fc` đã được khởi tạo và xử lý lỗi tổng thể.*

`thenApply` sẽ **không chạy** nếu barrier hoàn tất exceptionally. Đây là hành vi phù hợp cho yêu cầu **all-or-nothing**, nhưng chưa đủ cho ứng dụng muốn **giữ lại mọi kết quả thành công khi một request hỏng**.

## 5. Giữ quan hệ định danh request và future

Khi ba request hoàn tất theo thứ tự `C,A,B`, ta không được gán response C cho request A chỉ vì C về trước. Một số phương pháp:

- **Danh sách đồng thứ tự:** giữ `List<String> names` và `List<CompletableFuture<HttpResponse<String>>> futures`, rồi đọc cả hai theo cùng index.
- **Object có tên:** tạo `record NamedFuture(String id, CompletableFuture<HttpResponse<String>> future)` để đặt identifier và future vào cùng một object.
- **Map theo ID:** dùng `Map<String, CompletableFuture<...>>` nếu lookup theo key tiện hơn. Nếu quan tâm thứ tự in, chọn `LinkedHashMap` hoặc tự sắp xếp theo yêu cầu; không phó mặc cho thứ tự hoàn tất.

Hai mệnh đề này khác nhau:

~~~text
Start order:     profile -> orders -> settings
Completion order: settings -> profile -> orders

Output theo input order: profile -> orders -> settings
Identity của mỗi future: không đổi trong suốt exchange
~~~

Không nên để callback của nhiều future tùy tiện `add` vào cùng một `ArrayList` không được đồng bộ: có thể xảy ra race, mất dữ liệu hoặc thứ tự không ổn định. Lưu future riêng rồi tổng hợp sau barrier giúp kết quả dễ kiểm chứng hơn.

## 6. Ví dụ chạy độc lập Java 17+: allOf ba HTTP request thành công

Chương trình mở HTTP server tại loopback với ba endpoint `/alpha`, `/beta`, `/gamma`. Server dùng pool ba thread để có khả năng xử lý đồng thời. Client khởi phát cả ba `sendAsync` trong `stream().map(...)`, sau đó `allOf`, rồi mới đọc response theo thứ tự `names`.

Tạo file `HttpAllOfResultsDemo.java`:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class HttpAllOfResultsDemo {
    private static void reply(HttpExchange exchange, String text)
            throws IOException {
        try {
            byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            exchange.getResponseBody().write(bytes);
        } finally {
            exchange.close();
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService handlers = Executors.newFixedThreadPool(3);
        server.setExecutor(handlers);
        server.createContext("/alpha", e -> reply(e, "ALPHA"));
        server.createContext("/beta", e -> reply(e, "BETA"));
        server.createContext("/gamma", e -> reply(e, "GAMMA"));
        server.start();
        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3)).build();
            String base = "http://127.0.0.1:" + server.getAddress().getPort();
            List<String> names = List.of("alpha", "beta", "gamma");

            List<CompletableFuture<HttpResponse<String>>> requests =
                    names.stream().map(name -> {
                        HttpRequest request = HttpRequest.newBuilder()
                                .uri(URI.create(base + "/" + name))
                                .timeout(Duration.ofSeconds(5))
                                .GET().build();
                        return client.sendAsync(request,
                                HttpResponse.BodyHandlers.ofString(
                                        StandardCharsets.UTF_8));
                    }).toList();

            CompletableFuture<Void> all = CompletableFuture.allOf(
                    requests.toArray(CompletableFuture<?>[]::new));
            all.get(8, TimeUnit.SECONDS);

            for (int i = 0; i < names.size(); i++) {
                HttpResponse<String> response = requests.get(i).join();
                System.out.println(names.get(i) + ": HTTP "
                        + response.statusCode() + " " + response.body());
            }
            System.out.println("result count: " + requests.size());
        } finally {
            server.stop(0);
            handlers.shutdownNow();
        }
    }
}
~~~

Chạy với JDK 17 hoặc mới hơn:

~~~bash
javac HttpAllOfResultsDemo.java
java HttpAllOfResultsDemo
~~~

Stdout:

~~~text
alpha: HTTP 200 ALPHA
beta: HTTP 200 BETA
gamma: HTTP 200 GAMMA
result count: 3
~~~

### Những dòng cần hiểu

1. `HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0)` tạo server **cùng máy**, port `0` để hệ điều hành tự cấp. Ví dụ không yêu cầu truy cập mạng ngoài.
2. `names.stream().map(...)` gọi `sendAsync` ba lần **trước khi chờ**. Mỗi future chứa response của endpoint tương ứng.
3. `requests.toArray(CompletableFuture<?>[]::new)` cung cấp mảng cho varargs của `allOf` và biên dịch được trên Java 17.
4. `all.get(8, TimeUnit.SECONDS)` là **hạn chờ của thread gọi** để có barrier. Nếu nhóm bình thường thì tiếp tục. Nếu timeout hoặc lỗi, phương thức có thể ném checked exception; demo không phải mẫu production cho failure.
5. Sau khi barrier hoàn tất thành công, `requests.get(i).join()` đọc `HttpResponse<String>` đã sẵn sàng; `statusCode()` và `body()` được truy cập riêng cho từng request.
6. Thứ tự in là `alpha, beta, gamma` **do danh sách names**, không phải do kết nối HTTP thực thi tuần tự.
7. `server.stop(0)` và `handlers.shutdownNow()` dọn server demo. Một server dài hạn cần graceful lifecycle thích hợp hơn.

Nếu response `gamma` hoàn tất trước `alpha`, kết quả vẫn gắn đúng tên vì `i` là chỉ số yêu cầu lúc tạo, không phải thứ tự kết thúc.

## 7. Vì sao chỉ bắt lỗi allOf là chưa đủ cho best-effort?

Giả sử một request gặp lỗi mạng `IOException`. `allOf` có thể hoàn tất exceptionally, nên:

~~~java
CompletableFuture.allOf(fa, fb, fc).join(); // Có thể throw.
System.out.println(fa.join().body());       // Có thể không chạy đến đây.
~~~

*Đoạn trên là ví dụ lỗi logic trong ứng dụng chưa bắt exception.*

**Các kết quả thành công của fa/fc vẫn tồn tại**, chỉ là luồng điều khiển đã rời khỏi đoạn code dự định đọc chúng.

Hai cách bảo toàn kết quả:

- **Cách A:** catch `CompletionException` từ `allOf`, sau đó kiểm tra từng future con vì barrier đã hoàn tất; xử lý riêng future thành công, future exceptional và future cancelled. Hữu ích khi phải giữ nguyên future và nguyên nhân của từng request.
- **Cách B (thường dễ tổng hợp):** đặt `handle` trên **từng request** để chuyển nó thành future `Outcome` không ném lỗi vì lỗi request. Sau đó gọi `allOf` trên các `Outcome` futures, lấy tất cả trạng thái theo nhãn.

**Lưu ý quan trọng:** `allOf` chỉ hoàn tất bình thường nếu mọi future **được đưa vào nó** đều hoàn tất bình thường. `handle` có thể biến lỗi request thành một giá trị `Outcome.failure`, nhưng nếu chính code trong `handle` ném lỗi thì future mới vẫn exceptional. Handler cần ngắn, ít rủi ro và không biến lỗi thành thành công giả.

## 8. handle, thenApply, exceptionally và whenComplete khác nhau

| Phương thức | Nhánh thành công | Nhánh lỗi | Tình huống sử dụng |
| --- | --- | --- | --- |
| `thenApply(value -> result)` | Chuyển giá trị `T` sang `U` | Không chạy function; lỗi được truyền sang stage tiếp | Parse JSON, kiểm tra status, map DTO |
| `handle((value,error) -> outcome)` | Có `value`, `error == null` | Có `error`; trả Outcome thất bại | **Thu cả thành công và lỗi** |
| `exceptionally(error -> fallback)` | Giữ nguyên giá trị cũ | Cho phép fallback cùng kiểu dữ liệu | Cấp mặc định, nhưng cần tránh che lỗi |
| `whenComplete((value,error) -> ...)` | Ghi log/metrics | Ghi log/metrics, không tự chữa lỗi | Observability/cleanup |
| `thenCompose(value -> futureB)` | Khởi phát operation phụ thuộc kết quả A | Không chạy function nếu A lỗi | Chuỗi request A → B |
| `thenCombine(other, (a,b) -> combined)` | Tạo value từ hai future | Nếu dependency lỗi thì không tạo value | Kết hợp hai kết quả |
| `anyOf(...)` | Hoàn tất khi một future xong | Cũng có thể kết thúc lỗi | Chờ kết quả sớm, **không chờ đủ** |

Với `handle`:

~~~java
CompletableFuture<Outcome> safe =
        httpFuture.handle((response, error) -> {
            if (error != null) {
                return Outcome.failed(requestId, error);
            }
            return Outcome.ok(
                    requestId, response.statusCode(), response.body());
        });
~~~

*Đây là **giả mã minh họa**: `Outcome.ok/failed`, `httpFuture` và `requestId` do ứng dụng tự định nghĩa. Chương trình đầy đủ ở phần 9 triển khai record cụ thể.*

Không dùng `exceptionally(error -> "")` cho mọi lỗi nếu String rỗng có thể là response thành công thực. Nên lưu rõ request ID, success/status và lỗi. `whenComplete` phù hợp logging nhưng không tự biến một future exceptional thành bình thường. Nếu một callback nặng chạy trên thread completion, nó có thể trì hoãn các request khác; cân nhắc `thenApplyAsync`/bounded executor cho xử lý CPU lớn.

## 9. Ví dụ Java 17+: allOf vẫn giữ hai kết quả khi request thứ ba lỗi

Trong ví dụ thứ hai:

- `/first` trả `HTTP 200` và `FIRST`.
- `/unavailable` trả `HTTP 503` và `BUSY`.
- `/third` trả `HTTP 200` và `THIRD`.

**HTTP 503 tự nó không phải exception Java.** Vì ví dụ muốn minh họa lỗi nghiệp vụ sau khi HTTP response về, code **chủ động** ném `IllegalStateException("HTTP 503")` trong `thenApply` nếu status khác 200. Sau đó `handle` chuyển mỗi request thành một `Outcome(name, success, detail)`, dù request thành công hay thất bại.

Tạo file `HttpAllOfOutcomesDemo.java`:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class HttpAllOfOutcomesDemo {
    record Outcome(String name, boolean success, String detail) {}

    private static void reply(HttpExchange exchange, int status, String text)
            throws IOException {
        try {
            byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(status, bytes.length);
            exchange.getResponseBody().write(bytes);
        } finally {
            exchange.close();
        }
    }

    private static CompletableFuture<Outcome> fetch(
            HttpClient client, String base, String name) {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(base + "/" + name))
                .timeout(Duration.ofSeconds(5))
                .GET().build();
        return client.sendAsync(request, HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8))
                .thenApply(response -> {
                    if (response.statusCode() != 200) {
                        throw new IllegalStateException(
                                "HTTP " + response.statusCode());
                    }
                    return response.body();
                })
                .handle((body, error) -> {
                    if (error != null) {
                        Throwable cause = error;
                        while (cause instanceof CompletionException
                                && cause.getCause() != null) {
                            cause = cause.getCause();
                        }
                        return new Outcome(name, false,
                                "ERROR " + cause.getMessage());
                    }
                    return new Outcome(name, true, "OK " + body);
                });
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService handlers = Executors.newFixedThreadPool(3);
        server.setExecutor(handlers);
        server.createContext("/first", e -> reply(e, 200, "FIRST"));
        server.createContext("/unavailable", e -> reply(e, 503, "BUSY"));
        server.createContext("/third", e -> reply(e, 200, "THIRD"));
        server.start();
        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3)).build();
            String base = "http://127.0.0.1:" + server.getAddress().getPort();
            List<String> names = List.of("first", "unavailable", "third");

            List<CompletableFuture<Outcome>> settled = names.stream()
                    .map(name -> fetch(client, base, name)).toList();
            CompletableFuture.allOf(
                    settled.toArray(CompletableFuture<?>[]::new))
                    .get(8, TimeUnit.SECONDS);

            List<Outcome> results = settled.stream()
                    .map(CompletableFuture::join).toList();
            for (Outcome result : results) {
                System.out.println(result.name() + ": " + result.detail());
            }
            long okCount = results.stream().filter(Outcome::success).count();
            System.out.println("success count: " + okCount);
        } finally {
            server.stop(0);
            handlers.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac HttpAllOfOutcomesDemo.java
java HttpAllOfOutcomesDemo
~~~

Stdout:

~~~text
first: OK FIRST
unavailable: ERROR HTTP 503
third: OK THIRD
success count: 2
~~~

### Giải thích vì sao hai kết quả thành công không bị mất

1. `names.stream()` gọi `fetch` cho cả ba tên **trước khi đợi barrier**.
2. `client.sendAsync(...)` trả response HTTP; `thenApply` kiểm tra `statusCode`. HTTP 503 được **chính ứng dụng** chuyển thành một lỗi của stage.
3. `handle` được chạy cả khi upstream bình thường lẫn exceptional. Nó tạo `Outcome` có nhãn `name` và trạng thái `success`, nên mỗi request có một giá trị kết quả.
4. Khi có `CompletionException` bọc lỗi, vòng `while` lấy cause gốc để ghi chi tiết dễ hiểu. Nếu HTTP client lỗi mạng thật, `handle` cũng sẽ nhận error và trả Outcome thất bại.
5. `allOf` được gọi **trên danh sách future đã `handle`**, nên trong demo chúng hoàn tất bình thường. Một lỗi nghiệp vụ không còn làm mất lối đi tới các Outcome còn lại.
6. Vòng `for` in theo thứ tự `names`. Con số `success count: 2` là kết quả **chính sách ứng dụng**: hai status 200, một status 503 bị nâng lên lỗi; không phải “mạng chỉ gửi được hai response”.

Demo lưu `Outcome.detail` để dễ in, chứ không giữ toàn bộ `HttpResponse` của nhánh 503 sau khi throw. Khi cần phân tích lỗi production, nên lưu riêng **status, body lỗi, cause và latency** thay vì chỉ một chuỗi.

## 10. Thiết kế Outcome đủ thông tin để giữ cả HTTP status và network error

Một kiểu `Outcome` production-friendly có thể chứa:

~~~text
Outcome(
    requestId,
    httpStatus = 200 / 503 / null nếu chưa từng nhận HTTP response,
    body = String hoặc null,
    error = Throwable hoặc null,
    duration = thời gian xử lý
)
~~~

Điểm quan trọng: lỗi **HTTP response 503** khác lỗi **TCP connect, DNS, TLS hoặc timeout**. Với `503`, server đã trả HTTP response nên thông tin status và body vẫn có ý nghĩa. Nếu không nhận được response, chỉ có exception/cause và metadata chờ.

Mẫu giữ nguyên status/body khi HTTP vẫn trả response:

~~~java
record Outcome(String id, Integer status, String body, Throwable error) {}

CompletableFuture<Outcome> future = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .handle((response, failure) -> {
            if (failure != null) {
                return new Outcome(requestId, null, null, failure);
            }
            return new Outcome(
                    requestId, response.statusCode(), response.body(), null);
        });
~~~

*Đây là đoạn minh họa trong class có `client`, `request` và `requestId`; không phải chương trình chạy độc lập. Cần giới hạn kích thước body và không vô tình log dữ liệu nhạy cảm.*

Cách này không biến HTTP 503 thành Java exception; nó biến status thành dữ liệu được giữ lại. Lớp nghiệp vụ phía sau mới quyết định `status >= 500` có nên retry hay hiển thị cảnh báo. Nếu client thực sự gặp lỗi `IOException`, `failure != null` và response không có.

**Đặt ID vào Outcome tại thời điểm tạo future**, không dựa vào thời điểm callback hoàn tất để gán ID. Đây là nguyên tắc quan trọng để giữ kết quả từng yêu cầu.

## 11. Phân biệt allOf với thenCompose, thenCombine và anyOf

| Bài toán | Công cụ nên cân nhắc | Ghi chú |
| --- | --- | --- |
| Nhiều request **độc lập**, đợi **đủ tất cả** | `allOf` + giữ futures | Fan-out/fan-in |
| Request B cần token/ID từ response A | `thenCompose` | Chuỗi phụ thuộc; không fan-out cùng lúc |
| Kết hợp kết quả **hai** future thành một giá trị | `thenCombine` | Hữu ích với hai dependencies |
| Chọn **một** future hoàn tất trước | `anyOf` | Không giữ đủ kết quả của cả nhóm |
| Một future lỗi cần giá trị thay thế | `exceptionally` hoặc `handle` | Đừng che lỗi bằng dữ liệu giả |
| Muốn ghi log trạng thái mỗi request | `whenComplete` | Quan sát, không tự phục hồi lỗi |
| Muốn danh sách Outcome cho cả thành công/lỗi | `handle` trên từng future + `allOf` | Phân loại kết quả theo request ID |

`allOf` không phải phương thức làm A/B/C chạy trên ba thread riêng theo lời gọi. HTTP client có cơ chế thực thi bất đồng bộ của nó. `allOf` chỉ biểu diễn **phụ thuộc vào việc tất cả future đầu vào đã hoàn tất**.

Nếu nghiệp vụ đòi **chỉ cần 2 trên 3 response thành công**, không nên coi `allOf` như quorum primitive: `allOf` đợi cả ba. Cần cơ chế riêng với điều kiện số kết quả đủ, timeout và chính sách cancel những request còn lại.

## 12. Timeout của từng request khác timeout của barrier

Các lớp timeout không đồng nghĩa:

| Cấu hình/thao tác | Giới hạn điều gì? | Có tự hủy mọi request con không? |
| --- | --- | --- |
| `HttpClient.Builder.connectTimeout(Duration)` | Thời gian thiết lập kết nối | Không |
| `HttpRequest.Builder.timeout(Duration)` | Thời hạn thực hiện HTTP request theo client | Không, chỉ request tương ứng |
| `all.get(8, TimeUnit.SECONDS)` | Thời gian thread caller **chờ barrier** | **Không** |
| `all.orTimeout(8, TimeUnit.SECONDS)` | Hoàn tất exceptionally chính **future barrier** nếu quá hạn | Không có bảo đảm hủy từng child |
| `child.cancel(true)` | Yêu cầu hủy future HTTP đang pending | HTTP client cố hủy exchange; không bảo đảm kịp ngăn server xử lý |

`CompletableFuture.get(timeout)` khi timeout ném `TimeoutException` mà **không mặc định hủy operation đang chờ**. `CompletableFuture.orTimeout` điều chỉnh trạng thái future được gọi; khi gọi trên barrier, nó không tự đặt lại timeout của mỗi HTTP request.

Khi cần tổng deadline thực sự, hãy xác định rõ: hết giờ thì **trả kết quả partial**, tiếp tục chạy nền để ghi log, hay yêu cầu hủy từng HTTP request? Nếu hủy, cũng không có bảo đảm server chưa nhận và xử lý request. Với POST tạo đơn hàng hoặc giao dịch, cần **idempotency key**, ACK nghiệp vụ và chính sách retry cẩn thận.

Trong hai demo, `all.get(8, TimeUnit.SECONDS)` chỉ làm test tránh chờ vô hạn. Bản production cần catch `TimeoutException`, xử lý `ExecutionException`/`InterruptedException`, cleanup future/socket và quyết định xử lý các kết quả đã nhận.

## 13. Giới hạn đồng thời và tài nguyên khi danh sách lớn

`allOf` không giới hạn số request. Nếu bạn viết `ids.stream().map(id -> sendAsync(...)).toList()` cho 20.000 ID, ứng dụng có thể khởi phát rất nhiều exchange ngay lập tức. Từ đó xuất hiện rủi ro:

- Hết connection/socket/file descriptor, cạn bandwidth hoặc đạt quota API.
- `BodyHandlers.ofString` gom quá nhiều response lớn vào RAM.
- Server bị dồn tải đột biến, trả HTTP 429/503 hoặc timeout.
- Callback `thenApply/handle` làm việc CPU nặng, ảnh hưởng thời gian completion.
- Dữ liệu lỗi hoặc body nhạy cảm bị log quá mức.

**Cách điều tiết:** chạy **batch có giới hạn** hoặc bounded concurrency có backpressure. Ví dụ chia danh sách theo nhóm N request, khởi phát một batch, dùng `allOf` để nhận outcomes, rồi mới khởi phát batch tiếp theo. N phải được chọn qua workload/benchmark và quota, không có số mặc định phù hợp mọi hệ thống.

Nếu dùng `Semaphore`, tránh thiết kế một task/thread bị chặn chỉ để chờ permit cho mỗi ID; điều phối bất đồng bộ hoặc dùng executor/hàng đợi có giới hạn sẽ quản tài nguyên tốt hơn. Cần giới hạn tổng số bytes nhận, số request đang pending và thời gian kết thúc, không chỉ số kết nối.

Không suy ra rằng output được in alpha/beta/gamma nghĩa là ba request HTTP thực sự chạy tuần tự. Để đo concurrency, dùng timestamps hoặc đo thời gian server phục vụ; code ví dụ cố ý in **theo input order** để kết quả ổn định.

## 14. Bảo toàn kết quả trước race và biến đổi dữ liệu

Một số quy tắc làm code fan-in dễ review:

1. **Một request = một ID ổn định + một future**. Không gán kết quả theo thứ tự thread hoàn tất.
2. **Không thay đổi collection đầu vào** sau khi tạo futures, hoặc dùng record gắn identity và future trong cùng object.
3. **Không dùng shared mutable `ArrayList` không đồng bộ** cho callback từ nhiều future. Tổng hợp theo future gốc sau barrier, hoặc chọn cấu trúc thread-safe.
4. **Phân loại thành công/lỗi rõ ràng:** HTTP 200, HTTP 503, IOException, timeout, cancel là những trạng thái khác nhau.
5. **Giới hạn body trước khi tích lũy quá lớn**. HTTP 200 không có nghĩa payload an toàn.
6. **Không chặn lâu trong callback completion**; dùng executor được quản lý cho xử lý nặng. Callback `handle` có thể chạy trên thread hoàn tất future, không chắc luôn là thread ứng dụng.
7. **Kiểm tra `isDone()` cẩn thận:** true bao gồm normal, exceptional và cancelled; không đồng nghĩa thành công. Dùng `isCompletedExceptionally()` và xử lý cause, hoặc chuẩn hóa bằng Outcome.
8. **Một Throwable không thay cho toàn bộ log per-request** nếu có nhiều lỗi. Giữ requestId, status, cause và latency cho từng việc.

## 15. Lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai? | Cách xử lý |
| --- | --- | --- |
| `sendAsync(A).join()` rồi mới tạo B | Vô tình gửi tuần tự | Tạo tất cả future trước khi chờ |
| Coi `allOf` trả List | Kết quả của barrier là `Void` | Giữ future con, tạo List riêng |
| Bỏ future con sau khi tạo allOf | Không thể truy cập từng result | Lưu future trong list/map/record |
| `all.join()` ném lỗi rồi bỏ qua hai kết quả tốt | Lỗi chặn luồng tổng hợp | `handle` mỗi future hoặc catch rồi duyệt |
| Tin rằng allOf tự cancel các request khác | Javadoc không bảo đảm như vậy | Cleanup/cancel theo chính sách |
| Gán request theo response hoàn tất trước | Sai identity | Gắn ID khi gửi |
| Đồng bộ hoá bằng ArrayList không bảo vệ | Race và sai dữ liệu | Aggregate sau barrier |
| Coi HTTP 503 là lỗi mạng bắt buộc | HTTP status vẫn là response | Kiểm tra status |
| `exceptionally(error -> "")` cho mọi lỗi | Mất phân biệt với response hợp lệ rỗng | Outcome chứa trạng thái rõ |
| `all.get(timeout)` mà không xử lý timeout child | Request có thể còn chạy | Timeouts/cancel per-request |
| Khởi phát hàng nghìn request không giới hạn | Quá tải mạng/RAM/server | Batch, bounded concurrency |
| Gom tất cả body lớn bằng ofString | Có thể hết RAM | Giới hạn byte, stream/ofFile |
| Retry toàn nhóm POST khi một response lỗi | Có thể lặp side effect | Idempotency/ACK theo nghiệp vụ |
| Coi `thenCombine` như `allOf` cho mọi N | thenCombine chỉ ghép cặp và cần typed aggregation | Chọn mô hình theo dependency |
| Coi `allOf()` rỗng sẽ chờ | Nó hoàn tất bình thường ngay | Xử lý tập input rỗng theo contract |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `CompletableFuture.allOf(fa,fb,fc)` trả kiểu gì và chứa response nào?

*Đáp án:* Trả `CompletableFuture<Void>`; bản thân nó không chứa response. Phải đọc `fa/fb/fc` sau khi barrier hoàn tất hoặc transform thành một future mang collection.

**Câu 2.** B trả về lỗi, A và C thành công. `all.join()` ném exception. Hai kết quả của A và C có mất không?

*Đáp án:* Không. Dữ liệu của A/C vẫn ở futures riêng. Ứng dụng phải catch và tổng hợp từng future hoặc dùng `handle` mỗi future thành Outcome trước `allOf`.

**Câu 3.** `sendAsync(A).join()` rồi `sendAsync(B).join()` có tận dụng sự độc lập của A/B không?

*Đáp án:* Không tốt. Thread caller đợi A xong trước khi B được khởi phát. Cần tạo futures cho cả hai trước.

**Câu 4.** HTTP response 503 có làm future `sendAsync` tự động exceptional không?

*Đáp án:* Không chỉ vì status 503. Response HTTP bình thường có thể có status 503. Ứng dụng phải tự kiểm tra status và quyết định coi đó là lỗi nghiệp vụ.

**Câu 5.** `all.get(3, SECONDS)` timeout có làm ba HTTP request chắc chắn dừng không?

*Đáp án:* Không. Đó là hạn chờ của caller; cần hủy child futures hoặc để chúng tiếp tục theo chính sách, và không giả định server chưa tạo side effect.

**Câu 6.** C hoàn tất trước A nhưng danh sách ban đầu A,B,C. In C dưới nhãn A vì nó về trước có đúng không?

*Đáp án:* Sai. Identity phải gắn từ lúc tạo request, còn thứ tự in phụ thuộc yêu cầu đầu ra. Kết quả không được gán dựa vào timing.

**Câu 7.** `Outcome.failure` giúp ích gì hơn `exceptionally(error -> "")`?

*Đáp án:* Nó giữ dấu hiệu lỗi rõ ràng cùng ID/cause. Chuỗi rỗng có thể là response thành công hợp lệ nên dùng làm fallback sẽ che sự cố.

## 17. Bài tập vận dụng

1. Chạy `HttpAllOfResultsDemo`, đánh dấu dòng **khởi phát** cả ba `sendAsync`, dòng **allOf barrier**, và dòng **đọc từng future**. Đổi thứ tự `names` và kiểm chứng output vẫn đúng ID.
2. Thêm `/delta` trả `DELTA`, thêm tên vào list và kiểm tra `result count` tăng từ 3 lên 4.
3. Chạy `HttpAllOfOutcomesDemo`, đổi `/unavailable` từ 503 thành 200; giải thích vì sao `success count` thành 3. Đổi lại 503.
4. Viết Outcome giàu thông tin gồm `requestId`, `httpStatus`, `body`, `error`. Gọi `handle` trực tiếp trên `sendAsync` để giữ cả body `BUSY` của HTTP 503.
5. Thêm một `CompletableFuture.failedFuture(new IOException("test error"))` **giả lập** vào một nhóm unit test (không coi đây là response HTTP thật), quan sát allOf raw exceptional và allOf các Outcome hoạt động khác nhau.
6. Gọi `CompletableFuture.allOf()` không đối số và tìm cách xử lý input list rỗng theo contract nghiệp vụ.
7. Thêm timeout per-request và timeout barrier rồi viết chính sách hủy, ghi nhận kết quả partial, retry và cleanup. Không giả định timeout barrier đã cancel child.
8. Chuyển 100 request thành từng batch giới hạn, đo in-flight count và số bytes body tích lũy; benchmark thay vì kết luận tốc độ từ thứ tự log.
9. Thiết kế dashboard best-effort: hiển thị success của A/C, HTTP 503 của B kèm body error, thời gian và nguyên nhân, thay vì bỏ cả màn hình.

## Tài liệu API chính thức

- [`CompletableFuture` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `allOf`, `join`, `get`, `handle`, `thenApply`, `thenCompose`, `thenCombine`, `orTimeout`.
- [`HttpClient` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html): `sendAsync`, cancel HTTP future và HTTP exchange.
- [`HttpRequest` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.html): request builder, URI và timeout.
- [`HttpResponse` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.html): status, headers, body và BodyHandlers.
- [`CompletionStage` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletionStage.html): xử lý nhánh thành công/lỗi, kết hợp các thao tác.
- [`HttpServer` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): local fixture cho hai chương trình demo.
