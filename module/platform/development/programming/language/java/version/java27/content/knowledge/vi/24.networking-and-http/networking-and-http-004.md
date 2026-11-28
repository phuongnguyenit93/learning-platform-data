# HTTP đồng bộ, bất đồng bộ và xử lý response body

Trong Java 27, **java.net.http.HttpClient** là API chuẩn để gửi yêu cầu HTTP và nhận phản hồi bằng Java thuần. API hỗ trợ cả hai cách thực thi:

- **Đồng bộ** (*synchronous*): **client.send(...)** chờ cho đến khi có phản hồi theo quy tắc của body handler.
- **Bất đồng bộ** (*asynchronous*): **client.sendAsync(...)** trả ngay một **CompletableFuture<HttpResponse<T>>**, cho phép ghép nhiều thao tác mà không cần chặn luồng gọi ngay tại thời điểm gửi.

Một phần quan trọng không kém là **response body**: tùy loại dữ liệu và kích thước, ta có thể đọc dưới dạng **String**, **byte[]**, **Path**, **InputStream**, **Stream<String>** hoặc luồng phát dữ liệu theo **Flow.Publisher**.

Bài học thuộc chương **Mạng và HTTP** trong mô-đun Java 27, sử dụng API còn hiệu lực trong JDK 27, không dựa vào những hướng dẫn HTTP cũ bằng các API không còn là lựa chọn mặc định cho ứng dụng mới. Nội dung cũng chỉ rõ **HTTP status**, **ngoại lệ mạng**, **timeout**, **cancellation**, **bộ mã ký tự**, **giới hạn bộ nhớ** và vòng đời kết nối.

## 1. Nhìn tổng thể một lần gọi HTTP

Một lần gọi thông thường gồm:

1. Tạo và cấu hình **HttpClient**.
2. Tạo **HttpRequest**, chọn URI, method, headers, body và timeout.
3. Chọn **HttpResponse.BodyHandler<T>** để định dạng body nhận về.
4. Gửi bằng **send** hoặc **sendAsync**.
5. Đọc **statusCode()**, **headers()**, **uri()** và **body()**.
6. Diễn giải kết quả theo hợp đồng API, xử lý lỗi và giải phóng tài nguyên.

~~~mermaid
flowchart TD
    A["HttpClient dùng lại giữa nhiều yêu cầu"]
    B["HttpRequest: URI, method, headers, timeout"]
    C{"Cách gửi?"}
    D["send(...) — đồng bộ"]
    E["sendAsync(...) — CompletableFuture"]
    F["BodyHandler chọn cách tiêu thụ response body"]
    G["HttpResponse<T>: status, headers, body"]
    H["Kiểm tra HTTP status và dữ liệu"]
    I["Đóng stream / hoàn tất subscription nếu cần"]
    A --> B --> C
    C -->|send| D --> F
    C -->|sendAsync| E --> F
    F --> G --> H --> I
~~~

Trong ví dụ:

~~~java
HttpResponse<String> response =
    client.send(request, HttpResponse.BodyHandlers.ofString());
~~~

**String** trong **HttpResponse<String>** không có nghĩa giao thức HTTP chỉ gửi chuỗi. Nó nói rằng **BodyHandler** đã chuyển các byte của HTTP response thành **String** theo quy tắc mã ký tự.

Nếu dùng **BodyHandlers.ofByteArray()**, kiểu trả về là **HttpResponse<byte[]>**. Nếu dùng **ofFile(path)**, kiểu là **HttpResponse<Path>**.

## 2. Tạo HttpClient đúng cách trong Java 27

Các import thường dùng:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
~~~

Tạo một client với timeout kết nối và chính sách redirect:

~~~java
HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(5))
    .followRedirects(HttpClient.Redirect.NORMAL)
    .build();
~~~

Hoặc dùng cấu hình mặc định:

~~~java
HttpClient client = HttpClient.newHttpClient();
~~~

**HttpClient** sau khi tạo là một đối tượng có cấu hình cố định, được thiết kế để **dùng lại cho nhiều yêu cầu**; nó có thể quản lý và tái sử dụng các kết nối bên dưới. Không nên tạo một HttpClient mới cho mỗi request nếu ứng dụng cần throughput và connection reuse tốt.

### 2.1. Vòng đời client

Từ Java 21, **HttpClient** triển khai **AutoCloseable**; điều này vẫn đúng trong Java 27. Với ứng dụng CLI có vòng đời ngắn:

~~~java
try (HttpClient client = HttpClient.newHttpClient()) {
    // Thực hiện các request và hoàn tất các phản hồi.
}
~~~

Ở ứng dụng server, có thể tạo client tại lúc khởi tạo ứng dụng, dùng chung qua nhiều service và đóng nó ở giai đoạn shutdown.

**Không nhầm**: đóng HttpClient không đồng nghĩa với việc một streaming response chưa được đọc sẽ tự hoàn thành tức khắc. Nếu **InputStream**, **Stream<String>** hoặc Publisher của response chưa được tiêu thụ/đóng/hủy đúng cách, shutdown có thể bị kéo dài.

### 2.2. Phiên bản giao thức

Java 27 có thể hỗ trợ **HTTP/1.1, HTTP/2 và HTTP/3** thông qua HttpClient mặc định. Phiên bản được sử dụng thực tế còn phụ thuộc máy chủ và quá trình đàm phán kết nối.

~~~java
HttpClient client = HttpClient.newBuilder()
    .version(HttpClient.Version.HTTP_2)
    .build();
~~~

Đây là lựa chọn phiên bản **ưu tiên/yêu cầu theo API**, không bảo đảm mọi request cuối cùng đều dùng HTTP/2. Hãy đọc **response.version()** để biết phiên bản đã sử dụng.

Khi không có lý do rõ ràng, nên để client quyết định theo cấu hình và khả năng hỗ trợ của endpoint thay vì ép phiên bản một cách tùy tiện.

## 3. Tạo HttpRequest

Một GET request:

~~~java
HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("https://example.com/"))
    .header("Accept", "text/html")
    .timeout(Duration.ofSeconds(10))
    .GET()
    .build();
~~~

Phương thức **GET()** có thể được viết rõ ràng. Nếu không chọn method, **HttpRequest.Builder** mặc định là GET.

Tùy mục đích, có thể dùng:

~~~java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
    .timeout(Duration.ofSeconds(10))
    .header("Accept", "application/json")
    .build();
~~~

**HttpRequest** đã build là đối tượng bất biến về cấu hình yêu cầu. Có thể dùng lại request khi phù hợp, nhưng cần lưu ý tính lặp lại của request body nếu có **BodyPublisher** cung cấp nội dung theo luồng.

### 3.1. Những thành phần cần phân biệt

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| URI | **https://example.com/api/items** | Đích HTTP |
| Method | **GET**, **POST**, **PUT**, **DELETE** | Hành động theo hợp đồng HTTP |
| Request header | **Accept: application/json** | Kiểu phản hồi client muốn nhận |
| Request body | JSON UTF-8 hoặc file | Dữ liệu client gửi |
| Request timeout | **timeout(Duration.ofSeconds(10))** | Giới hạn thời gian thực hiện request theo API |
| Response body handler | **ofString()**, **ofFile(...)** | Cách xử lý dữ liệu trả về |

**Accept** và **Content-Type** không phải một:

- **Accept** thể hiện loại nội dung mong muốn nhận trong response.
- **Content-Type** của request thể hiện loại nội dung đang gửi lên server.

Nếu URI, header hay payload đến từ người dùng, phải xác thực theo hợp đồng và chính sách bảo mật trước khi tạo request.

## 4. Gửi HTTP đồng bộ bằng send

**send(HttpRequest, BodyHandler<T>)** chặn thread gọi trong lúc trao đổi HTTP cần thiết để phản hồi được trả về. Tùy body handler, dữ liệu body có thể đã được đọc hết hoặc vẫn đang chờ được tiêu thụ.

Ví dụ hoàn chỉnh, lưu trong **SyncHttpDemo.java**:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class SyncHttpDemo {

    public static void main(String[] args) throws Exception {
        URI uri = URI.create(
            args.length > 0 ? args[0] : "https://example.com/"
        );

        HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(10))
            .header("Accept", "text/html")
            .GET()
            .build();

        try (HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build()) {

            HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
            );

            System.out.println("Status: " + response.statusCode());
            System.out.println("URI: " + response.uri());
            System.out.println("HTTP: " + response.version());

            String body = response.body();
            System.out.println("Characters: " + body.length());
        }
    }
}
~~~

Chạy với JDK 27:

~~~bash
javac SyncHttpDemo.java
java SyncHttpDemo
~~~

Ví dụ cần **kết nối Internet**. Status và độ dài nội dung phụ thuộc phản hồi tại thời điểm chạy, vì vậy không gán một kết quả số cố định.

### 4.1. send có thể ném những lỗi nào?

Một số lỗi quan trọng:

- **IOException**: lỗi truyền nhận, kết nối, timeout hoặc xử lý HTTP ở mức I/O.
- **InterruptedException**: thread gửi bị ngắt trong lúc chờ.
- **IllegalArgumentException**: một request không đáp ứng các điều kiện hợp lệ mà API quy định.

Khi method của bạn có **throws IOException, InterruptedException**, có thể để người gọi xử lý. Khi bắt **InterruptedException**, không bỏ qua tín hiệu interrupt. Nếu chuyển sang một unchecked exception tại ranh giới không thể truyền tiếp, hãy khôi phục cờ ngắt:

~~~java
try {
    client.send(request, HttpResponse.BodyHandlers.discarding());
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException(
        "Tác vụ gửi HTTP bị ngắt", interrupted
    );
} catch (java.io.IOException failure) {
    throw new IllegalStateException(
        "Gửi HTTP thất bại", failure
    );
}
~~~

Việc Java có thể yêu cầu hủy exchange khi thread bị interrupt **không bảo đảm** server chưa từng nhận hoặc xử lý request. Cần nhớ điều này khi gửi POST/PUT có tác dụng phụ.

## 5. HTTP status không phải IOException

Một hiểu nhầm phổ biến: **client.send(...) sẽ ném ngoại lệ mỗi khi status là 404 hoặc 500**.

Không đúng. Nếu HTTP exchange thành công về mặt giao thức, **HttpResponse** có thể trả:

~~~java
int status = response.statusCode();
~~~

Dù status là **200**, **404**, **429** hoặc **500**. Lỗi HTTP theo hợp đồng server cần do **ứng dụng** phân loại.

~~~java
HttpResponse<String> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofString()
);

if (response.statusCode() >= 200
        && response.statusCode() < 300) {
    System.out.println("Thành công: " + response.body());
} else {
    System.err.println(
        "HTTP status không thành công: " + response.statusCode()
    );
}
~~~

| Nhóm status | Ý nghĩa tổng quát | Gợi ý xử lý |
|---|---|---|
| **2xx** | Request được xử lý thành công theo ngữ nghĩa HTTP | Đọc response body theo hợp đồng |
| **3xx** | Redirect hoặc thông tin điều hướng | Theo redirect policy và xác thực đích |
| **4xx** | Lỗi phía request/client, ví dụ 400/401/403/404/429 | Không giả định retry sẽ thành công; xét từng status |
| **5xx** | Server/gateway có lỗi, ví dụ 500/502/503 | Có thể retry khi hợp đồng và tính idempotent cho phép |

**Không nên** chỉ kiểm tra status **== 200** nếu API cũng hợp lệ với **201 Created**, **202 Accepted** hoặc **204 No Content**. Đồng thời, **2xx** không đồng nghĩa response luôn chứa body JSON.

### 5.1. Cẩn thận khi ghi log response body lỗi

Response lỗi có thể chứa dữ liệu cá nhân, token, thông tin nội bộ hoặc nội dung rất lớn. Không ghi toàn bộ body vào log mặc định.

Một cách tiếp cận tốt hơn:

~~~java
System.err.println(
    "HTTP request failed, status=" + response.statusCode()
        + ", endpoint=" + response.uri().getHost()
);
~~~

Ở production, thêm correlation ID nếu có nhưng phải bảo vệ dữ liệu nhạy cảm, và giới hạn khối lượng log.

## 6. Gửi HTTP bất đồng bộ bằng sendAsync

**sendAsync** trả về một **CompletableFuture<HttpResponse<T>>** mà không buộc thread gọi chờ kết quả ngay tại dòng gửi.

~~~java
CompletableFuture<HttpResponse<String>> future =
    client.sendAsync(
        request,
        HttpResponse.BodyHandlers.ofString()
    );
~~~

Trong khi request đang được xử lý, ứng dụng có thể thực hiện các công việc khác hoặc tạo thêm những request độc lập.

Sau đó:

~~~java
CompletableFuture<String> textFuture =
    future.thenApply(HttpResponse::body);
~~~

**thenApply** ở đây tạo một stage lấy body từ phản hồi; không có thêm request HTTP mới.

### 6.1. Ví dụ bất đồng bộ chạy được

Lưu thành **AsyncHttpDemo.java**:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class AsyncHttpDemo {

    public static void main(String[] args) {
        URI uri = URI.create(
            args.length > 0 ? args[0] : "https://example.com/"
        );

        HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();

        try (HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build()) {

            CompletableFuture<String> bodyFuture = client
                .sendAsync(
                    request,
                    HttpResponse.BodyHandlers.ofString()
                )
                .thenApply(response -> {
                    int status = response.statusCode();

                    if (status < 200 || status >= 300) {
                        throw new IllegalStateException(
                            "HTTP status: " + status
                        );
                    }

                    return response.body();
                });

            System.out.println("Request đã được gửi bất đồng bộ.");

            try {
                String body = bodyFuture.join();
                System.out.println(
                    "Đã nhận " + body.length() + " ký tự."
                );
            } catch (CompletionException failure) {
                System.err.println(
                    "Lỗi bất đồng bộ: " + failure.getCause()
                );
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac AsyncHttpDemo.java
java AsyncHttpDemo
~~~

Ví dụ có điểm **join()** để chương trình CLI không thoát trước khi nhận kết quả. Điều này **không có nghĩa sendAsync là đồng bộ**: quá trình gửi đã được bắt đầu bất đồng bộ, còn **join** được dùng tại ranh giới nơi chương trình cần đợi kết quả.

### 6.2. join và get khác nhau

| Method | Khi hoàn tất bình thường | Khi thất bại |
|---|---|---|
| **future.join()** | Trả giá trị | Có thể ném **CompletionException** dạng unchecked |
| **future.get()** | Trả giá trị | Ném **ExecutionException** dạng checked; có thể bị ngắt |
| **future.get(timeout, unit)** | Trả giá trị trong thời hạn chờ | Có thể ném **TimeoutException** nếu chờ quá lâu |
| **future.cancel(true)** | Thử hủy tác vụ đang chờ/chạy | Cancellation không bảo đảm request chưa đến server |

Với **CompletionException** hoặc **ExecutionException**, nguyên nhân thường được truy xuất bằng **getCause()**. Khi tạo lỗi tầng ứng dụng, hãy bảo toàn cause thay vì chỉ sao chép message.

## 7. Kết hợp nhiều request bất đồng bộ

Giả sử cần lấy nội dung từ hai endpoint **độc lập**. Gửi chúng đồng thời có thể giảm tổng thời gian chờ so với gửi tuần tự, nếu server và network có đủ khả năng phục vụ.

~~~java
HttpRequest first = HttpRequest.newBuilder(
        URI.create("https://example.com/"))
    .timeout(Duration.ofSeconds(10))
    .build();

HttpRequest second = HttpRequest.newBuilder(
        URI.create("https://www.example.org/"))
    .timeout(Duration.ofSeconds(10))
    .build();

CompletableFuture<HttpResponse<String>> f1 =
    client.sendAsync(first, HttpResponse.BodyHandlers.ofString());

CompletableFuture<HttpResponse<String>> f2 =
    client.sendAsync(second, HttpResponse.BodyHandlers.ofString());

CompletableFuture<Void> all =
    CompletableFuture.allOf(f1, f2);

all.join();

HttpResponse<String> r1 = f1.join();
HttpResponse<String> r2 = f2.join();

System.out.println(r1.statusCode());
System.out.println(r2.statusCode());
~~~

Đoạn ví dụ cần các import **java.net.URI**, **java.net.http.*** và **java.util.concurrent.CompletableFuture** cùng một **HttpClient** đang mở.

Lưu ý:

1. Cả hai lời gọi **sendAsync** đều được khởi động trước khi **join**.
2. **allOf** chờ tất cả future hoàn tất; nếu một future thất bại, future tổng hợp hoàn thành theo trạng thái thất bại và **join** ném ngoại lệ.
3. **allOf** không tự quyết định request nào được retry hoặc hủy.
4. Cần kiểm tra **statusCode()** của từng phản hồi, vì 404/500 không tự khiến future thất bại.
5. Không tạo vô hạn các request bất đồng bộ mà không giới hạn concurrency.

### 7.1. thenApply, thenCompose và thenCombine

| API | Ý nghĩa | Ví dụ sử dụng |
|---|---|---|
| **thenApply(fn)** | Biến đổi kết quả ngay khi stage hoàn tất | Lấy **response.body()** hoặc kiểm tra status |
| **thenCompose(fn)** | Nối stage mới trả về **CompletionStage** | Lấy token, sau đó gọi endpoint cần token |
| **thenCombine(other, fn)** | Kết hợp hai stage độc lập khi đều xong | Hợp nhất hai response |
| **allOf(...)** | Chờ nhiều future | Đồng bộ kết thúc một nhóm request |
| **exceptionally(fn)** | Phục hồi khi stage thất bại | Áp dụng fallback có kiểm soát |
| **whenComplete((value,error) -> ...)** | Quan sát kết quả hoặc lỗi | Ghi metric hoặc log, không mặc định đổi kết quả |

**thenApply** không mặc định bảo đảm chạy trên một executor riêng. Callback có thể chạy trên thread hoàn thành stage hoặc thread thực thi một phương thức liên quan đến stage. Nếu callback xử lý CPU dài, hãy tách sang executor phù hợp bằng **thenApplyAsync(fn, executor)**.

## 8. So sánh send và sendAsync

| Tiêu chí | **send** | **sendAsync** |
|---|---|---|
| Kiểu trả về | **HttpResponse<T>** | **CompletableFuture<HttpResponse<T>>** |
| Thread gọi | Chặn tại lời gọi gửi | Trả về trước khi request hoàn tất |
| Cấu trúc code | Tuần tự, dễ theo dõi | Ghép các completion stages |
| Lỗi I/O | **IOException**, **InterruptedException** | Future hoàn thành thất bại, thường quan sát qua **CompletionException**/**ExecutionException** |
| Phù hợp | CLI, xử lý tuần tự, virtual-thread-per-task | Nhiều lời gọi độc lập hoặc pipeline async |
| Xử lý body | Cùng hệ **BodyHandler<T>** | Cùng hệ **BodyHandler<T>** |
| Giới hạn tài nguyên | Vẫn cần timeout, concurrency limit | Vẫn cần timeout, concurrency limit |
| Hiệu năng một lời gọi | Không tự kém hơn về network | Không tự khiến server phản hồi nhanh hơn |

### 8.1. Kết hợp send với virtual threads

Trong Java 27, **virtual threads** đã là tính năng chính thức và giúp mô hình **thread-per-task** làm việc hiệu quả với nhiều thao tác blocking I/O. Vì vậy, bạn không bắt buộc phải đổi mọi lời gọi **send** thành **sendAsync** để có khả năng xử lý đồng thời tốt.

~~~java
try (var executor =
        java.util.concurrent.Executors
            .newVirtualThreadPerTaskExecutor()) {

    var future = executor.submit(
        () -> client.send(
            request,
            HttpResponse.BodyHandlers.ofString()
        )
    );

    HttpResponse<String> response = future.get();
    System.out.println(response.statusCode());
}
~~~

Đoạn code giả định **client** và **request** đã được tạo và client còn mở cho đến khi task kết thúc.

Lựa chọn:

- **send + virtual threads** khi muốn mỗi tác vụ có luồng code tuần tự, dễ đọc, dễ debug.
- **sendAsync + CompletableFuture** khi cần phối hợp pipeline async hoặc đã dùng kiến trúc bất đồng bộ.
- Với framework reactive/event loop đang hoạt động tốt, không tự ý trộn thêm cách xử lý blocking nếu chưa hiểu nguyên lý chạy của framework.

## 9. Response body là byte trước khi trở thành dữ liệu Java

HTTP response mang status, headers và các byte body. **BodyHandler<T>** quy định cách chuyển phần body này thành kiểu Java mong muốn.

~~~java
HttpResponse<byte[]> bytesResponse = client.send(
    request,
    HttpResponse.BodyHandlers.ofByteArray()
);

HttpResponse<String> textResponse = client.send(
    request,
    HttpResponse.BodyHandlers.ofString()
);
~~~

Hai lời gọi trên là **hai request riêng**, nếu thực thi như ví dụ. Chúng không tự chia sẻ cùng body của một response.

Cấu trúc:

~~~text
HTTP response: status + headers + body bytes
                           |
                           v
                BodyHandler<T> nhận ResponseInfo
                           |
                           v
                BodySubscriber<T> tiêu thụ bytes
                           |
                           v
                 HttpResponse<T>.body()
~~~

Với handler tích hợp sẵn, Java thực hiện phần lớn việc nhận và ghép byte. Với trường hợp chuyên biệt, có thể tạo **BodyHandler** và **BodySubscriber** riêng.

## 10. Bảng lựa chọn BodyHandlers

| Body handler | Kiểu **T** | Phù hợp với | Cần lưu ý |
|---|---|---|---|
| **ofString()** | **String** | JSON/text nhỏ hoặc vừa | Chọn charset theo Content-Type, dự phòng UTF-8 |
| **ofString(Charset)** | **String** | Endpoint có charset được xác định theo hợp đồng | Bỏ qua charset khai báo ở response để dùng charset chỉ định |
| **ofByteArray()** | **byte[]** | Dữ liệu nhị phân nhỏ hoặc nội dung cần xử lý ở RAM | Toàn bộ body nằm trong bộ nhớ |
| **ofFile(Path)** | **Path** | Tải dữ liệu vào tệp | Phải kiểm tra status và xử lý tệp lỗi/đích |
| **ofInputStream()** | **InputStream** | Đọc tuần tự body lớn | **Phải đọc hết hoặc đóng stream** |
| **ofLines()** | **Stream<String>** | Dữ liệu văn bản theo dòng | **Phải tiêu thụ hoặc đóng stream** |
| **ofPublisher()** | **Flow.Publisher<List<ByteBuffer>>** | Kết nối pipeline reactive/streaming | Một subscriber và tuân thủ backpressure/cancel |
| **discarding()** | **Void** | Không cần nội dung body | Vẫn nhận/loại bỏ body theo handler |
| **replacing(value)** | Kiểu của **value** | Trả giá trị thay thế sau khi bỏ body | Không dùng để bỏ qua việc phân loại HTTP status |
| **limiting(handler, maxBytes)** | Kiểu của handler bên trong | Giới hạn số byte cho nội dung ngoài hệ thống | Nếu vượt ngưỡng, body exchange thất bại |

Trên Java 27, **BodyHandlers.limiting(...)** là một lựa chọn hữu ích khi đọc JSON/text từ nguồn chưa đáng tin cậy. Cần đặt giới hạn phù hợp với hợp đồng API; ngưỡng quá nhỏ có thể làm phản hồi hợp lệ thất bại.

**Điểm cốt lõi:** BodyHandlers tích hợp sẵn **không tự chọn thành công/thất bại dựa trên status code**. Chúng vẫn nhận body khi status 404, 429 hoặc 500, trừ khi bạn tự viết handler có quy tắc riêng.

## 11. Đọc văn bản và charset: ofString

Ví dụ đơn giản:

~~~java
HttpResponse<String> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofString()
);

String text = response.body();
~~~

**ofString()** dựa vào thông tin **charset** trong header **Content-Type** để giải mã. Nếu header không chỉ định charset hoặc charset không được hỗ trợ, API dùng **UTF-8**.

Khi hợp đồng API quy định rõ UTF-8, có thể chỉ định trực tiếp:

~~~java
import java.nio.charset.StandardCharsets;

HttpResponse<String> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
);
~~~

Lúc này, response được giải mã theo UTF-8 do chương trình chọn, bất kể charset được khai báo trong header.

### 11.1. Không tự biến byte[] thành String với charset ngầm định

Cách có rủi ro:

~~~java
byte[] bytes = response.body();
String text = new String(bytes); // Charset mặc định của môi trường
~~~

Nếu biết dữ liệu là UTF-8:

~~~java
String text = new String(bytes, StandardCharsets.UTF_8);
~~~

Thực tế, nếu đã muốn String thì dùng **BodyHandlers.ofString(StandardCharsets.UTF_8)** sẽ rõ ràng hơn.

### 11.2. Content-Type và Content-Encoding khác nhau

- **Content-Type** cho biết kiểu media và có thể kèm charset, ví dụ **text/plain; charset=UTF-8**.
- **Content-Encoding** mô tả dạng biểu diễn được mã hóa/nén trên đường truyền, ví dụ **gzip**.

Chọn charset **không** có nghĩa bạn tự động đã xử lý mọi content encoding. Đừng yêu cầu một content encoding mà client/pipeline của bạn chưa có chính sách giải mã tương ứng. Nếu endpoint trả dữ liệu nén, hãy xác minh cơ chế hỗ trợ của client và hợp đồng HTTP trước khi áp dụng bước xử lý body.

## 12. Đọc dữ liệu nhị phân: ofByteArray

Với phản hồi nhị phân nhỏ:

~~~java
HttpResponse<byte[]> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofByteArray()
);

int status = response.statusCode();
byte[] payload = response.body();

System.out.println("Status: " + status);
System.out.println("Bytes: " + payload.length);
~~~

Cách này phù hợp nếu body được giới hạn và ứng dụng cần dữ liệu trong RAM.

**Không nên** sử dụng **ofByteArray()** cho tải xuống hàng trăm MB hoặc phản hồi có thể lớn vô hạn. Bản thân một mảng byte có giới hạn của JVM, và nhiều request đồng thời có thể gây áp lực bộ nhớ rất lớn.

### 12.1. Giới hạn body bằng limiting (Java 27)

~~~java
import java.net.http.HttpResponse;

long maxBytes = 1024L * 1024L; // 1 MiB

HttpResponse.BodyHandler<byte[]> handler =
    HttpResponse.BodyHandlers.limiting(
        HttpResponse.BodyHandlers.ofByteArray(),
        maxBytes
    );

HttpResponse<byte[]> response = client.send(request, handler);
~~~

Nếu số byte body được nhận vượt **maxBytes**, subscriber bên trong nhận lỗi **IOException** và upstream subscription bị hủy theo hợp đồng API. Với async, lỗi thường được chuyển thành future hoàn thành thất bại.

Đây là giới hạn lượng body được cấp phát/nhận theo handler, không phải phương án thay thế cho chính sách:

- Giới hạn số request đồng thời.
- Timeout kết nối/request.
- Giới hạn băng thông hoặc quota ứng dụng.
- Kiểm tra content type trước khi parse.

**Content-Length** hữu ích để tham khảo nhưng có thể thiếu hoặc không mô tả mọi tình huống truyền dữ liệu. Không dựa **chỉ** vào header này để bảo vệ bộ nhớ.

## 13. Ghi response body trực tiếp xuống tệp: ofFile

Để tải một tệp:

~~~java
import java.nio.file.Path;
import java.net.http.HttpResponse;

Path destination = Path.of("download.bin");

HttpResponse<Path> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofFile(destination)
);

System.out.println("Status: " + response.statusCode());
System.out.println("Saved to: " + response.body());
~~~

Với **ofFile**, khi **HttpResponse<Path>** được trả về bình thường, body đã được ghi xong vào tệp. Đường dẫn trong **response.body()** chỉ vị trí tệp.

**Lưu ý về tệp đã tồn tại:** **ofFile(path)** mặc định tương đương mở file với tùy chọn **CREATE, WRITE**, không ngầm thêm **TRUNCATE_EXISTING**. Nếu ghi đè vào một file cũ dài hơn body mới, nội dung còn thừa ở cuối file có thể gây sai dữ liệu. Hãy dùng một tệp mới/rỗng (như ví dụ tệp tạm bên dưới), hoặc chỉ định rõ những **OpenOption** thích hợp khi hợp đồng cho phép ghi đè.

**Cẩn thận:** Handler tải xuống ghi body theo phản hồi, không chỉ ghi khi HTTP 2xx. Nếu server trả **404** với trang lỗi HTML, file đích có thể chứa **trang lỗi** thay vì nội dung mong muốn.

### 13.1. Tải an toàn vào tệp tạm rồi chuyển tới đích

Một cách rõ ràng là tải vào tệp tạm:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

static Path downloadChecked(
        HttpClient client,
        HttpRequest request,
        Path target
) throws IOException, InterruptedException {

    Path absoluteTarget = target.toAbsolutePath();
    Path parent = absoluteTarget.getParent();

    Path temporary = Files.createTempFile(
        parent, "http-download-", ".part"
    );

    boolean accepted = false;

    try {
        HttpResponse<Path> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofFile(temporary)
        );

        if (response.statusCode() != 200) {
            throw new IOException(
                "Tải xuống thất bại, HTTP " + response.statusCode()
            );
        }

        Files.move(
            temporary,
            absoluteTarget,
            StandardCopyOption.REPLACE_EXISTING
        );

        accepted = true;
        return absoluteTarget;
    } finally {
        if (!accepted) {
            Files.deleteIfExists(temporary);
        }
    }
}
~~~

Trong ví dụ này:

1. Thư mục cha của **target** cần tồn tại và cho phép tạo tệp.
2. Body được ghi vào tệp tạm, không ghi thẳng vào file đích.
3. Chỉ khi status **200** theo hợp đồng download này mới chuyển tệp vào đích.
4. Nếu thao tác thất bại, **finally** cố gắng xóa tệp tạm.
5. **Files.move** như trên không bảo đảm thao tác thay thế **atomic**; nếu cần atomic move, hãy kiểm tra hỗ trợ của filesystem và thiết kế recovery thích hợp.

Chỉ số **200** là quy tắc riêng của ví dụ tải file toàn phần. Với endpoint hỗ trợ **206 Partial Content**, resume, ETag hoặc checksum, cần một giao thức xử lý đầy đủ hơn. Không được tự ghép một phần nội dung vào file đầy đủ khi chưa xác minh range và tính toàn vẹn.

### 13.2. Không tin filename do server đưa ra

**BodyHandlers.ofFileDownload(directory)** có thể lấy tên file từ header **Content-Disposition**. Khi tải dữ liệu ngoài hệ thống, không dùng tên file từ header hoặc user input như một đường dẫn đáng tin cậy mà không có kiểm soát.

Để quản lý tên file và quyền ghi chặt chẽ, nhiều ứng dụng chọn **ofFile(targetPath)** với đích do ứng dụng tạo và kiểm tra trước.

## 14. Streaming với ofInputStream

**ofInputStream()** là lựa chọn khi ứng dụng cần tiêu thụ body theo luồng thay vì giữ toàn bộ trong RAM.

~~~java
import java.io.InputStream;

HttpResponse<InputStream> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofInputStream()
);

try (InputStream stream = response.body()) {
    byte[] prefix = stream.readNBytes(64);
    System.out.println("Bytes read: " + prefix.length);
}
~~~

### 14.1. Vì sao response có thể về sớm?

Với **ofInputStream**, Java có thể trả **HttpResponse<InputStream>** sau khi nhận xong headers dù body chưa đến hết. Khi đọc **stream.read()**, chương trình có thể tiếp tục chờ dữ liệu mạng.

Do đó:

- Hoàn thành **send** hoặc **sendAsync** với handler này **không nhất thiết** đồng nghĩa body đã đọc xong.
- Trách nhiệm xử lý body vẫn thuộc ứng dụng sau khi có response.
- Nếu không muốn tiếp tục đọc, **đóng stream** để cho phép giải phóng tài nguyên.
- Đóng sớm có thể khiến kết nối bên dưới không được tái sử dụng.

### 14.2. Copy body xuống OutputStream

Ví dụ sử dụng streaming để ghi nội dung ra file:

~~~java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

HttpResponse<InputStream> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofInputStream()
);

try (InputStream input = response.body()) {
    if (response.statusCode() != 200) {
        throw new IOException(
            "HTTP status không hợp lệ: " + response.statusCode()
        );
    }

    try (OutputStream output =
            Files.newOutputStream(Path.of("download.bin"))) {
        input.transferTo(output);
    }
}
~~~

Đoạn code cần import **java.io.IOException** và các biến **client**, **request** tương ứng. Trong chương trình thật, bổ sung giới hạn dung lượng và ghi file tạm, vì **transferTo** không tự bảo đảm giới hạn số byte.

### 14.3. Không bỏ quên stream

Cách rủi ro:

~~~java
HttpResponse<InputStream> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofInputStream()
);

// Không đọc, không đóng response.body(): có thể giữ tài nguyên HTTP.
~~~

Cách đúng là dùng **try-with-resources** hoặc đảm bảo luồng được tiêu thụ tới EOF. Một client có thể bị kẹt khi shutdown nếu các streaming exchanges còn mở mà không được hoàn tất/hủy.

## 15. Xử lý văn bản theo dòng với ofLines

Với response dạng văn bản dài, mỗi dòng là một bản ghi hoặc message, có thể dùng:

~~~java
HttpResponse<java.util.stream.Stream<String>> response =
    client.send(
        request,
        HttpResponse.BodyHandlers.ofLines()
    );

try (var lines = response.body()) {
    lines.forEach(System.out::println);
}
~~~

**ofLines** trả về **Stream<String>**. Stream này có thể tiêu thụ từng dòng khi dữ liệu đến; nó không nhất thiết đã đọc hết body ngay lúc phản hồi được trả về.

Nếu chỉ lấy một vài dòng:

~~~java
try (var lines = response.body()) {
    lines.limit(10).forEach(System.out::println);
}
~~~

Đóng stream vẫn cần thiết sau khi dừng sớm. Nếu **limit(10)** không bao giờ nhận đủ mười dòng và nguồn giữ kết nối mở, việc tiêu thụ vẫn có thể chờ; hãy thiết lập timeout/cancellation theo hợp đồng dòng dữ liệu.

### 15.1. Những điều ofLines không làm

- Không tự parse mỗi dòng thành JSON object.
- Không tự giải quyết quy tắc giao thức như **Server-Sent Events (SSE)**.
- Không tự kết nối lại khi server ngắt luồng.
- Không tự giới hạn tổng số dòng hay kích thước từng dòng theo hợp đồng nghiệp vụ.

Với **NDJSON** (*newline-delimited JSON*), có thể parse từng dòng bằng thư viện JSON thích hợp. Phải xử lý dòng lỗi và giới hạn kích thước dữ liệu do bên ngoài cung cấp.

## 16. Response body dạng Publisher và backpressure

API:

~~~java
HttpResponse<
    java.util.concurrent.Flow.Publisher<
        java.util.List<java.nio.ByteBuffer>
    >
> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofPublisher()
);
~~~

**BodyHandlers.ofPublisher()** biến body thành một **Flow.Publisher<List<ByteBuffer>>** để một subscriber tiêu thụ theo mô hình reactive streams.

Các điểm quan trọng:

1. Publisher được trả về **khi headers đã đến**, không nhất thiết sau khi body hoàn tất.
2. Publisher của một response được thiết kế cho **một subscriber**.
3. Subscriber cần gọi **Subscription.request(n)** để yêu cầu dữ liệu theo nhu cầu (*backpressure*).
4. Nếu không tiếp tục tiêu thụ, phải **cancel** subscription phù hợp.
5. Không nên tự xây dựng một subscriber phức tạp chỉ để đọc response nhỏ thành String.

Nếu ứng dụng chưa dùng **Flow.Subscriber**, **ofInputStream** hoặc **ofFile** thường là điểm khởi đầu đơn giản hơn cho streaming.

### 16.1. BodyHandler và BodySubscriber khác nhau

- **BodyHandler<T>** được gọi khi response headers đến, nhận **ResponseInfo** (status, headers, version) và chọn cách xử lý body.
- **BodySubscriber<T>** là thành phần nhận các byte của body và hoàn tất kết quả kiểu **T**.

Có thể xây một handler riêng khi cách xử lý phụ thuộc status:

~~~java
import java.nio.charset.StandardCharsets;
import java.net.http.HttpResponse;

HttpResponse.BodyHandler<String> handler = responseInfo -> {
    if (responseInfo.statusCode() == 204) {
        return HttpResponse.BodySubscribers.replacing("");
    }

    return HttpResponse.BodySubscribers.ofString(
        StandardCharsets.UTF_8
    );
};
~~~

Dù body handler biết **status**, ứng dụng vẫn nên kiểm tra **response.statusCode()** để xác định logic thành công/thất bại. **replacing("")** chủ động bỏ body theo nhánh đã chọn.

## 17. Gửi JSON qua POST: request body khác response body

Để gửi một JSON payload, dùng **HttpRequest.BodyPublishers.ofString(...)**:

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

String json = """
    {"sku":"P-01","quantity":2}
    """;

HttpRequest post = HttpRequest.newBuilder(
        URI.create("https://example.com/api/orders"))
    .header("Content-Type", "application/json; charset=UTF-8")
    .header("Accept", "application/json")
    .timeout(Duration.ofSeconds(10))
    .POST(HttpRequest.BodyPublishers.ofString(
        json, StandardCharsets.UTF_8
    ))
    .build();
~~~

Sau đó:

~~~java
HttpResponse<String> response = client.send(
    post,
    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
);
~~~

**BodyPublishers** và **BodyHandlers** làm hai việc ngược nhau:

| Nhóm | Luồng dữ liệu | Ví dụ |
|---|---|---|
| **HttpRequest.BodyPublishers** | Dữ liệu Java → byte gửi đi | **ofString**, **ofByteArray**, **ofFile**, **noBody** |
| **HttpResponse.BodyHandlers** | Byte nhận về → dữ liệu Java | **ofString**, **ofByteArray**, **ofFile**, **ofInputStream** |

**BodyPublishers.ofString** không tự tạo JSON từ object Java. Nếu cần chuyển một **record** thành JSON, hãy serialize bằng thư viện JSON phù hợp trước, sau đó gửi chuỗi JSON đã tạo.

### 17.1. POST không mặc nhiên an toàn để retry

Một lệnh POST tạo đơn hàng có thể đã thành công trên server ngay trước khi kết nối bị ngắt. Nếu tự động retry không có quy tắc, bạn có thể tạo hai đơn hàng.

Khi hệ thống cần retry một thao tác có tác dụng phụ, hãy thiết kế **idempotency key**, hợp đồng retry và cách nhận biết kết quả phía server. Không coi mọi **IOException**, timeout hoặc status 5xx là tín hiệu an toàn để gửi lại cùng một request.

## 18. Timeout và huỷ yêu cầu

Hai loại timeout thường thấy:

~~~java
HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(3))
    .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/"))
    .timeout(Duration.ofSeconds(10))
    .build();
~~~

| Timeout | Phạm vi áp dụng | Điều không bảo đảm |
|---|---|---|
| **connectTimeout** | Giới hạn thời gian thiết lập kết nối mới | Không phải thời hạn toàn bộ workflow |
| **HttpRequest.Builder.timeout** | Thời gian tối đa cho HTTP request theo hợp đồng API | Không tự áp giới hạn thời gian cho mọi công việc xử lý body sau khi đã có streaming response |
| **Future.get(timeout)** | Thời gian thread gọi chờ kết quả future | Không tự hủy request |
| **CompletableFuture.orTimeout(...)** | Hoàn tất future với lỗi nếu đến hạn | Không phải đảm bảo huỷ mọi thao tác I/O bên dưới |
| **cancel(true)** với future từ sendAsync | Yêu cầu hủy exchange theo kiểu best effort | Không bảo đảm request chưa được gửi/thi hành phía server |

### 18.1. Lỗi timeout

Java có các ngoại lệ trong nhóm:

- **java.net.http.HttpTimeoutException** cho những tình huống HTTP request vượt thời hạn.
- **java.net.http.HttpConnectTimeoutException** dành cho timeout kết nối; nó là lớp con của **HttpTimeoutException**.

~~~java
try {
    client.send(
        request,
        HttpResponse.BodyHandlers.discarding()
    );
} catch (java.net.http.HttpConnectTimeoutException failure) {
    System.err.println("Timeout khi thiết lập kết nối");
} catch (java.net.http.HttpTimeoutException failure) {
    System.err.println("HTTP request timeout");
} catch (java.io.IOException failure) {
    System.err.println("Lỗi I/O: " + failure.getMessage());
}
~~~

Đoạn code cần xử lý hoặc khai báo **InterruptedException** riêng. Thứ tự catch quan trọng: **HttpConnectTimeoutException** phải đứng trước lớp cha **HttpTimeoutException**.

### 18.2. Cancellation với async

~~~java
CompletableFuture<HttpResponse<String>> future =
    client.sendAsync(
        request,
        HttpResponse.BodyHandlers.ofString()
    );

// Khi ứng dụng chủ động quyết định hủy:
boolean cancelled = future.cancel(true);
~~~

Mặc dù **future.cancel(true)** có thể khởi động hủy HTTP exchange trên HttpClient mặc định, hành động này là **best effort**. Tác vụ phía server có thể đã nhận request và việc giải phóng tài nguyên ở client có thể đến sau.

Với nhiều future phụ thuộc nhau, hãy xác định rõ tác vụ nào cần hủy và tác vụ nào vẫn được phép chạy. Không giả định hủy một future tổng hợp tự động hủy mọi request con.

## 19. Redirects, TLS và an toàn HTTP

### 19.1. Redirect

~~~java
HttpClient client = HttpClient.newBuilder()
    .followRedirects(HttpClient.Redirect.NORMAL)
    .build();
~~~

Các chính sách gồm **NEVER**, **ALWAYS** và **NORMAL**. Chính sách mặc định là **NEVER**. **NORMAL** theo redirect theo quy tắc riêng của API nhưng không tự động chuyển từ **HTTPS** xuống **HTTP**.

Một redirect có thể thay đổi đích request. Nếu server trả 3xx, không nhất thiết response cuối là cùng URI với request ban đầu. Có thể kiểm tra:

~~~java
System.out.println(response.uri());
System.out.println(response.previousResponse().isPresent());
~~~

**response.uri()** cho biết URI thực tế của response; **previousResponse()** có thể cung cấp phản hồi trung gian khi có redirect.

### 19.2. Ưu tiên HTTPS

Với dữ liệu nhạy cảm, sử dụng **https://** và cơ chế kiểm tra TLS của Java. Không tắt kiểm tra chứng chỉ hoặc hostname verification chỉ để “cho chạy được”.

### 19.3. Chống SSRF khi URI do người dùng chỉ định

Nếu ứng dụng server nhận một URL từ bên ngoài rồi gọi HttpClient, có thể phát sinh **server-side request forgery (SSRF)**: kẻ tấn công yêu cầu server truy cập tài nguyên nội bộ mà họ không có quyền.

Cần áp dụng chính sách rõ:

- Chỉ cho phép scheme và hostname/port được chấp thuận.
- Không cho phép tự động truy cập tài nguyên nội bộ, loopback, metadata service nếu không có mục đích đã xác thực.
- Kiểm tra từng đích sau redirect, không chỉ URI ban đầu.
- Xem xét DNS resolution/rebinding và kiểm soát truy cập ở tầng mạng.
- Đặt timeout, giới hạn body và concurrency.

Các ví dụ dùng **https://example.com/** nhằm minh họa API, không phải lời khuyên cho phép người dùng tuỳ ý nhập URL vào một dịch vụ tải hộ.

### 19.4. HTTP headers và dữ liệu nhạy cảm

Không ghi trực tiếp header **Authorization**, cookie, token hay toàn bộ request/response vào log. Khi cần debug, chỉ giữ những trường được cho phép và xóa/mask giá trị nhạy cảm.

## 20. Thiết kế service HTTP có thể kiểm thử

Một lớp phục vụ nghiệp vụ nên nhận **HttpClient** qua constructor thay vì tự tạo client mới bên trong mỗi method.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Objects;

public final class ProductApiClient {
    private final HttpClient client;
    private final URI endpoint;

    public ProductApiClient(HttpClient client, URI endpoint) {
        this.client = Objects.requireNonNull(client);
        this.endpoint = Objects.requireNonNull(endpoint);
    }

    public String getProducts() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(endpoint)
            .timeout(Duration.ofSeconds(10))
            .header("Accept", "application/json")
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString(
                java.nio.charset.StandardCharsets.UTF_8
            )
        );

        int status = response.statusCode();

        if (status < 200 || status >= 300) {
            throw new IllegalStateException(
                "Product API returned status " + status
            );
        }

        return response.body();
    }
}
~~~

Đoạn code là một class có thể lưu thành **ProductApiClient.java**, dùng API ổn định. Ở ứng dụng thực:

- Chỉ chấp nhận URI hợp đồng đã xác thực.
- Thêm giới hạn body trước khi parse JSON.
- Không dùng **throws Exception** ở public API nếu có thể biểu đạt cụ thể các failure modes.
- Có thể dùng một adapter interface hoặc mock HTTP server cục bộ trong kiểm thử tích hợp.
- Dùng cùng HttpClient cho nhiều thao tác, quản lý lifecycle ở nơi cấu hình ứng dụng.

### 20.1. Phân chia kiểm thử

| Loại kiểm thử | Điều nên xác minh |
|---|---|
| Unit test logic phân loại status | 2xx được chấp nhận, 4xx/5xx được xử lý đúng |
| Integration test với HTTP server giả lập | URI, method, headers, request body, timeout và response body |
| Test charset | UTF-8 và charset khác theo hợp đồng |
| Test response lớn | Giới hạn body và streaming không giữ toàn bộ byte trong RAM |
| Test cancellation | Tác vụ bị hủy/timeout được xử lý theo chính sách |
| Test streaming resource | InputStream/Stream luôn được đóng hoặc tiêu thụ |
| Test redirects | Không đi ra ngoài allowlist |
| Test async | Các request độc lập thực sự khởi động trước khi chờ; lỗi future được báo cáo |

Nếu muốn không phụ thuộc mạng thật trong CI, dùng một HTTP test server tại **loopback** hoặc một adapter giả lập được phép. JDK có module **jdk.httpserver** cung cấp **HttpServer** cho những kịch bản HTTP đơn giản; ứng dụng cũng có thể dùng thư viện test server phù hợp với framework. Việc test qua mạng Internet công cộng thường thiếu ổn định, khó tái tạo kết quả.

## 21. Khi nào chọn body handler nào?

~~~mermaid
flowchart TD
    A["Cần xử lý HTTP response"]
    B{"Có cần nội dung body?"}
    C["BodyHandlers.discarding()"]
    D{"Body là văn bản nhỏ?"}
    E["ofString(...) + giới hạn bytes"]
    F{"Cần byte[] trong RAM?"}
    G["ofByteArray() + giới hạn"]
    H{"Ghi thẳng ra tệp?"}
    I["ofFile(path) + kiểm tra status"]
    J{"Cần đọc dần từng byte/dòng?"}
    K["ofInputStream() hoặc ofLines()"]
    L["ofPublisher() nếu pipeline Flow cần"]
    A --> B
    B -->|Không| C
    B -->|Có| D
    D -->|Có| E
    D -->|Không| F
    F -->|Có| G
    F -->|Không| H
    H -->|Có| I
    H -->|Không| J
    J -->|Có| K
    J -->|Dữ liệu reactive| L
~~~

Đây là sơ đồ chọn điểm bắt đầu. Bạn vẫn phải xét response status, timeout, dung lượng, định dạng nội dung và việc giải phóng tài nguyên.

## 22. Những lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Hậu quả | Cách xử lý |
|---|---|---|
| Cho rằng status **404** sẽ ném **IOException** | Không xử lý logic thất bại | Kiểm tra **response.statusCode()** |
| Gọi **sendAsync** rồi **join** ngay từng request trong vòng lặp | Dễ biến thao tác thành tuần tự | Khởi động các future độc lập trước khi chờ |
| Dùng **thenApply(HttpResponse::body)** mà quên kiểm tra status | Coi HTML trang lỗi là dữ liệu hợp lệ | Kiểm tra status trước khi trả body |
| Chọn **ofByteArray/ofString** cho body không giới hạn | Tốn bộ nhớ, nguy cơ OOME | Dùng **limiting**, streaming hoặc ghi tệp |
| Không đóng **ofInputStream/ofLines** | Giữ tài nguyên, có thể làm kẹt shutdown | try-with-resources, đọc hết hoặc đóng |
| Ghi **ofFile** trực tiếp vào file quan trọng | Lưu trang lỗi 404 hoặc nội dung chưa được xác thực | Ghi tệp tạm, kiểm tra status rồi chuyển |
| Nhầm **BodyPublishers** và **BodyHandlers** | Dùng sai chiều dữ liệu | Publishers gửi request; Handlers nhận response |
| Dùng charset ngầm định | Văn bản sai ký tự | Dùng UTF-8 hoặc charset theo hợp đồng |
| Coi **get(timeout)** tự hủy HTTP request | Exchange có thể vẫn chạy | Thiết kế cancellation riêng |
| Coi **cancel(true)** bảo đảm server chưa xử lý POST | Retry có thể nhân đôi thao tác | Dùng idempotency policy |
| Tạo HttpClient mới cho mỗi HTTP request | Khó tận dụng kết nối và tài nguyên | Tái sử dụng client |
| Bỏ qua request timeout khi dùng virtual thread | Task vẫn có thể chờ lâu | Đặt timeout và chính sách hủy |
| Cho rằng cấu hình HTTP/2 bảo đảm mọi response dùng HTTP/2 | Phiên bản còn phụ thuộc negotiation | Kiểm tra **response.version()** |
| Cho người dùng cung cấp URI tùy ý | Có rủi ro SSRF | Allowlist, kiểm tra redirect và network |
| Dùng **Content-Length** làm bảo vệ duy nhất | Header có thể thiếu hoặc không đáng tin | Giới hạn số byte được tiêu thụ thực tế |
| Ghi token hoặc Authorization vào log | Rò rỉ thông tin bí mật | Mask hoặc không log |
| Dùng streaming handler rồi đóng client trước khi dùng body | Request có thể chưa hoàn tất | Quản lý lifetime của body và client rõ ràng |

## 23. Bài thực hành

Xây dựng một **HttpDownloader** có hai method:

~~~java
String fetchText(URI uri) throws Exception;

Path download(URI uri, Path destination) throws Exception;
~~~

Yêu cầu:

1. Dùng một **HttpClient** được truyền qua constructor.
2. Mỗi request có timeout; chỉ chấp nhận **HTTPS** và host trong allowlist.
3. **fetchText** dùng **BodyHandlers.limiting(BodyHandlers.ofString(UTF_8), maxBytes)** và chấp nhận status 2xx phù hợp hợp đồng.
4. **download** tải vào file tạm, chỉ chuyển file tới destination sau khi kiểm tra status và dữ liệu.
5. Viết method **fetchBothAsync(URI a, URI b)** bằng hai lời gọi **sendAsync**, sau đó dùng **thenCombine** hoặc **allOf**.
6. Nếu một request thất bại, giữ nguyên nguyên nhân của **CompletionException/ExecutionException** trong lỗi cấp ứng dụng.
7. Kiểm tra cả trường hợp response là 204 hoặc không có body.
8. Viết test mô phỏng response chậm, response lớn quá giới hạn, 404/500 và redirect ra ngoài allowlist.
9. Nếu sử dụng **ofInputStream**, bảo đảm đóng stream cả khi status không hợp lệ.
10. Ghi kết quả và phân tích khi nào **send + virtual threads** đơn giản hơn **sendAsync + CompletableFuture**.

### Câu hỏi tự kiểm tra

1. Khác biệt giữa **HttpResponse<String>** và **HttpResponse<InputStream>** là gì?
2. Vì sao **sendAsync** không bảo đảm mỗi HTTP request nhanh hơn?
3. Nếu server trả 500 với body JSON, **ofString()** có tự ném IOException không?
4. Khi nào **response.body()** có thể được trả về trước khi nội dung đã nhận hết?
5. Vì sao body từ **ofInputStream** phải được đọc hết hoặc đóng?
6. **Future.get(timeout)** và **HttpRequest.timeout** khác phạm vi nào?
7. Vì sao không nên ghi một response tải xuống vào file chính trước khi kiểm tra status?
8. Cần thêm cơ chế gì ngoài virtual threads để tránh quá tải server phụ trợ?
9. **BodyHandlers.limiting** có thay thế được giới hạn thời gian và số request không?
10. Nếu muốn xử lý một response dạng NDJSON nhiều triệu dòng, bạn sẽ chọn body handler nào?

## 24. Ghi nhớ

- **HttpClient** là API HTTP chuẩn hiện hành của Java 27, có thể dùng lại cho nhiều yêu cầu và quản lý vòng đời bằng **AutoCloseable**.
- **send** gửi đồng bộ; **sendAsync** trả **CompletableFuture** để phối hợp các yêu cầu bất đồng bộ.
- Cả hai dùng **HttpRequest** và **BodyHandler<T>** giống nhau; khác nhau chủ yếu ở cơ chế chờ.
- **HttpResponse<T>** lưu status, headers, URI, phiên bản giao thức và body kiểu **T**.
- HTTP **4xx/5xx không tự sinh IOException**; cần kiểm tra **statusCode()** theo hợp đồng API.
- **ofString** phù hợp văn bản có giới hạn, **ofByteArray** cho binary nhỏ, **ofFile** cho download, **ofInputStream/ofLines** cho streaming.
- Với **ofInputStream**, **ofLines** và **ofPublisher**, phải thực hiện trách nhiệm tiêu thụ/đóng/hủy body; response có thể xuất hiện trước khi toàn bộ body đến.
- **BodyHandlers.limiting(...)** của Java 27 giúp giới hạn số byte nhận, không thay thế timeout hoặc backpressure.
- **BodyPublishers** tạo request body; **BodyHandlers** tiêu thụ response body.
- Đặt timeout cho kết nối và request; cancellation của async là best effort, không bảo đảm server chưa xử lý.
- Dùng **send + virtual threads** cho code đồng bộ dễ đọc với nhiều tác vụ I/O; dùng **sendAsync** nếu kiến trúc cần ghép các stage bất đồng bộ.
- Giới hạn mức đồng thời, độ lớn response, redirect, URI được phép; tránh rò rỉ header chứa bí mật.
- Kiểm thử bằng server giả lập để kiểm soát status, headers, body, timeout, redirect và tình huống streaming.

## Tài liệu tham khảo

- [Java SE 27 API — HttpClient](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 27 API — HttpClient.Builder](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [Java SE 27 API — HttpRequest](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpRequest.html)
- [Java SE 27 API — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html)
- [Java SE 27 API — HttpResponse](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpResponse.html)
- [Java SE 27 API — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [Java SE 27 API — HttpResponse.BodySubscribers](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html)
- [Java SE 27 API — CompletableFuture](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 27 API — Flow](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Flow.html)
- [Java SE 27 API — HttpTimeoutException](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpTimeoutException.html)
- [Oracle Java SE 27 — Networking and HTTP Client](https://docs.oracle.com/en/java/javase/27/core/java-networking.html)
