# BodyPublisher, BodyHandler và BodySubscriber nằm ở đâu trong trao đổi

## 1. Nhìn toàn bộ vòng đời HTTP từ phía Java HttpClient

Khi dùng `java.net.http.HttpClient` (có từ Java 11), một HTTP exchange có **hai chiều body riêng biệt**:

- **Request body** đi **từ client tới server**.
- **Response body** đi **từ server trở lại client**.

Ba giao diện dễ nhầm nằm ở **những điểm khác nhau**:

1. **`HttpRequest.BodyPublisher`**: **đầu ra request**. Cung cấp dãy byte mà `HttpClient` gửi đi trong request.
2. **`HttpResponse.BodyHandler<T>`**: **bộ chọn cách xử lý response**. Được gọi khi HTTP **status và headers** của response đã có nhưng **trước khi response body được nhận**. Nó **trả về** một `BodySubscriber<T>` phù hợp.
3. **`HttpResponse.BodySubscriber<T>`**: **đầu vào response**. Nhận các byte response thực tế, tiêu thụ chúng theo cơ chế `Flow` và tạo giá trị body kiểu `T` (ví dụ `String`, `byte[]`, `Path` hoặc kiểu streaming).

~~~text
                       CHIỀU REQUEST
Ứng dụng client
    |
    | Tạo HttpRequest + POST(BodyPublisher)
    v
HttpRequest.BodyPublisher -- Flow.Publisher<ByteBuffer> --> HttpClient
                                                           |
                                                           v
                                                    HTTP request bytes
                                                           |
                                                           v
                                                       HTTP server
                                                           |
                              server xử lý request, tạo status/headers/body
                                                           |
                                                           v
                                                    HTTP response bytes
                                                           |
     CHIỀU RESPONSE                                       |
                                                           v
HttpClient có status + headers ----> BodyHandler<T>.apply(ResponseInfo)
                                               |
                                               | chọn/trả về BodySubscriber<T>
                                               v
                                     BodySubscriber<T>
                              Flow.Subscriber<List<ByteBuffer>>
                                               |
                              nhận các byte của response body
                                               |
                                               v
                                  CompletionStage<T> getBody()
                                               |
                                               v
                                 HttpResponse<T>.body()
~~~

**Không được đảo chiều:** `BodyPublisher` nói về **request gửi đi**, còn `BodyHandler` và `BodySubscriber` nói về **response nhận về**. `BodyHandler` không thực hiện việc upload request, và `BodySubscriber` không phải nơi chọn header hay status của request.

Đây là **pipeline phía client**. Trên server, API `com.sun.net.httpserver.HttpHandler`/`HttpExchange` là cơ chế **khác**; không phải một `HttpResponse.BodyHandler`. Hai chương trình chạy ở phần dưới tạo server loopback chỉ làm môi trường thử cho client.

## 2. Phân biệt tên gần giống: ba interface và ba lớp factory

| Tên API | Vai trò | Đầu vào/đầu ra điển hình |
| --- | --- | --- |
| `HttpRequest.BodyPublisher` | Cấp byte để **gửi request** | Implement `Flow.Publisher<ByteBuffer>`; có `contentLength()` |
| `HttpRequest.BodyPublishers` | **Factory** tạo BodyPublisher | `ofString`, `ofByteArray`, `ofFile`, `ofInputStream`, `noBody`, `fromPublisher` |
| `HttpResponse.BodyHandler<T>` | Chọn cách xử lý response theo **metadata** | `ResponseInfo -> BodySubscriber<T>` |
| `HttpResponse.BodyHandlers` | **Factory** tạo BodyHandler | `ofString`, `ofByteArray`, `ofFile`, `discarding`, `ofInputStream`, `ofPublisher` |
| `HttpResponse.BodySubscriber<T>` | Tiêu thụ response bytes và hoàn thiện `T` | Implement `Flow.Subscriber<List<ByteBuffer>>`, có `getBody()` |
| `HttpResponse.BodySubscribers` | **Factory** tạo BodySubscriber cho BodyHandler | `ofString`, `ofByteArray`, `ofFile`, `discarding`, `mapping`, `fromSubscriber` |

Vì Java có các factory rất giống tên, hãy nhìn **tiền tố**:

- `HttpRequest.BodyPublishers.ofString("...")`: **mã hóa String thành body gửi đi**.
- `HttpResponse.BodyHandlers.ofString(UTF_8)`: **trả về BodyHandler chọn cách nhận response thành String**.
- `HttpResponse.BodySubscribers.ofString(UTF_8)`: **BodySubscriber thực sự gom và giải mã byte response**. Thông thường `BodyHandlers.ofString(...)` tạo subscriber này giúp ta.

Hai chữ **Publisher** và **Subscriber** trong bài cùng dùng thuật ngữ Reactive Streams (`java.util.concurrent.Flow`), nhưng dữ liệu đi **ngược chiều**. `BodyHandler` là lớp điều phối nằm **giữa việc nhận headers và việc tiêu thụ response body**, không phải một publisher.

## 3. BodyPublisher: nguồn byte cho HTTP request

Một request POST thường được xây dựng như sau:

~~~java
HttpRequest.BodyPublisher publisher =
        HttpRequest.BodyPublishers.ofString(
                "Xin chào", StandardCharsets.UTF_8);

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.org/api"))
        .header("Content-Type", "text/plain; charset=utf-8")
        .POST(publisher)
        .build();
~~~

*Đoạn minh họa cần imports và endpoint thật để chạy; bản chạy độc lập ở phần 7 không dùng Internet.*

`BodyPublisher` kế thừa `Flow.Publisher<ByteBuffer>`. Khi gửi request có body, **`HttpClient` đăng ký một `Flow.Subscriber<ByteBuffer>` nội bộ** lên publisher đó; publisher cung cấp các `ByteBuffer` theo nhu cầu để client đóng gói gửi lên HTTP. Ứng dụng thường **không tự gọi `subscribe`** với các publisher có sẵn.

Kích thước request body được mô tả qua `publisher.contentLength()`:

- **`> 0`**: số byte đã biết.
- **`== 0`**: body rỗng; client có thể không cần subscribe.
- **`< 0`**: độ dài chưa biết trước; client chọn framing truyền phù hợp HTTP version/transport. Không nên tự giả định luôn có header `Content-Length`.

`contentLength()` là **số byte**, không phải `String.length()`. Ví dụ `"Xin chào"` trong UTF-8 có byte đa kích thước; nếu muốn limit upload, kiểm tra số **byte đã mã hóa**, không chỉ đếm ký tự.

Một `BodyPublisher` tùy biến cần chú ý:

- `contentLength()` phải **ổn định** qua các lần gọi.
- Có thể bị `HttpClient` subscribe **lại** khi cần gửi lại request vì redirect/authentication hoặc tình huống nội bộ. Một publisher có dữ liệu chỉ đọc được một lần sẽ có vấn đề nếu không có chính sách retry/replay.
- Sau khi phát một `ByteBuffer` cho HttpClient, publisher **không được tiếp tục truy cập/chỉnh buffer đó**; phải tuân thủ ownership và `Flow` protocol.
- Dùng `Flow.Subscription.request(n)` để điều tiết nhu cầu phát dữ liệu. Publisher tùy biến phải xử lý cancel, lỗi và kết thúc đúng, không bắn dữ liệu không giới hạn.

### Các lựa chọn nguồn request phổ biến

| Factory | Dữ liệu gửi đi | Khi nào dùng |
| --- | --- | --- |
| `BodyPublishers.noBody()` | Không có body | GET hoặc yêu cầu không cần payload |
| `BodyPublishers.ofString(text, UTF_8)` | Byte UTF-8 của text | POST JSON/text nhỏ, đã có trong bộ nhớ |
| `BodyPublishers.ofByteArray(bytes)` | Dữ liệu nhị phân trong mảng | Payload nhị phân nhỏ/vừa |
| `BodyPublishers.ofFile(path)` | Đọc file để gửi | Upload file, tránh tự load toàn bộ vào String |
| `BodyPublishers.ofInputStream(supplier)` | Lấy `InputStream` từ `Supplier` khi cần | Stream dữ liệu, supplier cần tạo stream phù hợp cho từng lượt gửi |
| `BodyPublishers.fromPublisher(flowPublisher)` | Lấy `ByteBuffer` từ Flow publisher | Kết nối với pipeline streaming tùy biến |

**Cần phân biệt:** `BodyPublishers.ofFile(path)` **đọc file nguồn để gửi**, còn `BodyHandlers.ofFile(path)` **ghi response nhận được vào file đích**. Tên `ofFile` giống nhau nhưng hướng dữ liệu trái ngược.

Header `Content-Type` không tự được tạo chỉ vì dùng `ofString`; hãy đặt kiểu nội dung, charset và protocol theo yêu cầu server. BodyPublisher **không chịu trách nhiệm** quyết định status response hay biến response thành String.

## 4. BodyHandler: có status và headers, nhưng chưa có body

Trên đường response, sau khi HTTP client nhận thông tin status/headers, nó gọi:

~~~java
HttpResponse.BodyHandler<String> handler = info -> {
    int status = info.statusCode();
    HttpHeaders headers = info.headers();
    // Dựa vào metadata chọn subscriber; chưa thể đọc response body ở đây.
    return HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8);
};
~~~

*Ví dụ minh họa với `HttpHeaders`, `HttpResponse` và `StandardCharsets` đã import; chưa phải chương trình độc lập.*

Hàm `BodyHandler<T>.apply(HttpResponse.ResponseInfo info)` được gọi **sau khi status và headers khả dụng**, **trước khi nhận response body**. Tại thời điểm này, handler có thể xét:

- `info.statusCode()`, ví dụ 200, 204, 404.
- `info.headers()`, ví dụ `Content-Type`, `Content-Length` (nếu có).
- `info.version()`, HTTP protocol version được dùng.

Nó chọn **một `BodySubscriber<T>`** để HTTP client giao tiếp với body stream sau đó. `BodyHandler` không nhận `byte[]` của payload và không nên cố parse body trong `apply`.

Ví dụ điều phối theo status:

~~~java
HttpResponse.BodyHandler<String> handler = info ->
        info.statusCode() == 204
                ? HttpResponse.BodySubscribers.replacing("")
                : HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8);
~~~

*Đoạn minh họa: trường hợp 204 trả String rỗng và body subscriber kiểu `String`; trong hệ thống thật cần xử lý status/Content-Type theo contract.*

`BodySubscribers.replacing("")` bỏ dữ liệu response body và trả về một giá trị String cố định. Hai nhánh đều phải phù hợp kiểu generic `T == String`. Nếu muốn trả `byte[]`/`Path` thay vì String, phải thay đổi cả `BodyHandler<T>` và `HttpResponse<T>` cho nhất quán.

Factory `BodyHandlers.ofString(UTF_8)` là một handler có sẵn, thường không cần xem status. **HTTP 404/500 không tự ném exception chỉ vì status khác 2xx.** `send` có thể trả một `HttpResponse<T>` với `statusCode()==404` và body lỗi, rồi ứng dụng quyết định xử lý. Nếu body handler/IO gặp lỗi thì đó là một loại thất bại riêng.

## 5. BodySubscriber: nhận thật sự response bytes qua Flow

`HttpResponse.BodySubscriber<T>` kế thừa **`Flow.Subscriber<List<ByteBuffer>>`** và có thêm:

~~~java
CompletionStage<T> bodyStage = subscriber.getBody();
~~~

*Đoạn minh họa với `subscriber` đã có; `getBody()` không phải thao tác đọc của ứng dụng trực tiếp từ socket.*

HTTP client cung cấp các **danh sách `ByteBuffer`** chứa byte response. Các sự kiện chuẩn `Flow`:

1. `onSubscribe(Flow.Subscription subscription)`: nhận subscription, gọi `subscription.request(n)` để yêu cầu thêm **n item**.
2. `onNext(List<ByteBuffer> buffers)`: nhận **một item là một danh sách** ByteBuffer; xử lý mọi buffer trong danh sách theo đúng thứ tự.
3. `onComplete()`: luồng body đã phát hết bình thường.
4. `onError(Throwable error)`: luồng body thất bại; không coi body chưa đủ là thành công.

**Dễ sai:** ở response, item được yêu cầu bởi `request(n)` là **`List<ByteBuffer>`**, không phải `n` byte. Kích thước các list/ByteBuffer và số lần `onNext` **không được cam kết** trùng từng lần `write` bên server, từng TCP packet hoặc từng dòng text.

`BodySubscriber.getBody()` trả về một **`CompletionStage<T>`**. Với các subscriber gom toàn body như `ofString` hay `ofByteArray`, stage thường chỉ hoàn tất sau khi toàn bộ body đã được nhận/chuyển đổi. Với subscriber kiểu **streaming**, ví dụ `ofInputStream` hoặc `ofPublisher`, stage có thể hoàn tất **sớm**, khi đối tượng stream/publisher đã sẵn sàng, còn byte response thực tế sẽ được ứng dụng tiêu thụ tiếp.

Đây là lý do **“`HttpResponse<T>` đã có” không luôn có nghĩa “mọi response bytes đã được dùng xong”**. Nó phụ thuộc vào `T` và loại subscriber/handler chọn.

## 6. Timeline: ai chạy lúc nào, và send khác sendAsync ra sao?

Với một request POST và response String:

~~~text
T0  newBuilder().POST(BodyPublishers.ofString(...)).build()
    -> mới tạo cấu hình request, CHƯA gửi lên mạng.

T1  HttpClient.send(request, BodyHandlers.ofString(UTF_8))
    -> bắt đầu HTTP exchange.

T2  HttpClient subscribe BodyPublisher của request
    -> ByteBuffer request được phát/ghi theo Flow và transport.

T3  Server nhận request, xử lý và trả status + headers.

T4  BodyHandler được invoke với ResponseInfo
    -> chọn BodySubscriber<String> theo metadata.

T5  HttpClient giao response body qua onSubscribe/onNext/... cho subscriber
    -> subscriber xử lý byte, quản lý backpressure.

T6  BodySubscriber.getBody() hoàn tất với String (với ofString sau toàn body)
    -> HttpResponse<String>.body() là String kết quả.
~~~

Các mốc có thể **chồng lấn**, không nhất thiết tuần tự cứng giữa việc gửi request và nhận response: một server có thể từ chối request sớm và trả response trước khi toàn bộ request body được upload, tùy HTTP protocol và chính sách. Timeline chỉ minh họa quan hệ API.

**`send` so với `sendAsync`:**

- `client.send(request, handler)`: lời gọi **chặn thread caller** cho tới khi có `HttpResponse<T>` theo semantics của body handler, hoặc lỗi/gián đoạn.
- `client.sendAsync(request, handler)`: trả **`CompletableFuture<HttpResponse<T>>`** để caller tiếp tục việc khác. `thenApply`/`thenAccept`/`exceptionally` xử lý khi future được hoàn tất.
- `future.join()` hoặc `future.get()` có thể **chặn** khi kết quả chưa sẵn sàng, dù request được gửi qua API async.
- `HttpResponse<String>` từ `BodyHandlers.ofString` thường đồng nghĩa **body String đã gom xong**, nhưng `BodyHandlers.ofInputStream` có thể trả response khi stream vừa khả dụng và ứng dụng vẫn phải đọc/đóng stream.
- `CompletableFuture` completion từ HTTP client là **trạng thái xử lý exchange theo body handler**, không phải xác nhận nghiệp vụ được server commit thành công.

## 7. Ví dụ Java 17+ hoàn chỉnh: BodyPublisher gửi request, BodyHandler chọn subscriber

Chương trình đầu không cần Internet: nó chạy một `HttpServer` trên **127.0.0.1`** trong cùng JVM, rồi gửi POST `PING` từ Java `HttpClient`. Server đọc request body và gửi lại `ACK:PING`. Phía client:

- `HttpRequest.BodyPublishers.ofString("PING", UTF_8)` tạo body nguồn, `contentLength() == 4` byte.
- `BodyHandler<String>` đọc `ResponseInfo.statusCode()` trước khi response body được nhận; trả `BodySubscribers.ofString(UTF_8)`.
- `client.send(...)` trả `HttpResponse<String>`; `response.body()` là kết quả subscriber.

Tạo file `HttpBodyPipelineDemo.java`:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class HttpBodyPipelineDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        AtomicReference<String> requestAtServer = new AtomicReference<>();
        server.createContext("/echo", exchange -> {
            try {
                String received = new String(
                        exchange.getRequestBody().readAllBytes(),
                        StandardCharsets.UTF_8);
                requestAtServer.set(exchange.getRequestMethod() + " " + received);
                byte[] reply = ("ACK:" + received).getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=utf-8");
                exchange.sendResponseHeaders(200, reply.length);
                exchange.getResponseBody().write(reply);
            } finally {
                exchange.close();
            }
        });
        server.start();
        try {
            HttpRequest.BodyPublisher publisher =
                    HttpRequest.BodyPublishers.ofString(
                            "PING", StandardCharsets.UTF_8);
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create("http://127.0.0.1:"
                            + server.getAddress().getPort() + "/echo"))
                    .header("Content-Type", "text/plain; charset=utf-8")
                    .POST(publisher)
                    .build();

            AtomicInteger statusAtHeaders = new AtomicInteger(-1);
            HttpResponse.BodyHandler<String> handler = info -> {
                statusAtHeaders.set(info.statusCode());
                return HttpResponse.BodySubscribers.ofString(
                        StandardCharsets.UTF_8);
            };
            HttpResponse<String> response = HttpClient.newHttpClient()
                    .send(request, handler);
            System.out.println("publisher bytes: " + publisher.contentLength());
            System.out.println("server received: " + requestAtServer.get());
            System.out.println("handler saw status: " + statusAtHeaders.get());
            System.out.println("response status: " + response.statusCode());
            System.out.println("response body: " + response.body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Chạy (JDK 17 hoặc mới hơn):

~~~bash
javac HttpBodyPipelineDemo.java
java HttpBodyPipelineDemo
~~~

Kết quả khi loopback hoạt động bình thường:

~~~text
publisher bytes: 4
server received: POST PING
handler saw status: 200
response status: 200
response body: ACK:PING
~~~

### Từng phần của output đến từ đâu?

- `publisher bytes: 4` đến từ `BodyPublisher.contentLength()`: length của **request body** đã mã hóa, không phải độ dài response.
- `server received: POST PING` là **server fixture** đọc `HttpExchange.getRequestBody()`, giúp chứng minh request thực sự đã được gửi.
- `handler saw status: 200` là giá trị `ResponseInfo.statusCode()` mà **`BodyHandler.apply`** thấy ở giai đoạn headers. Handler không tự nhận body; nó trả subscriber.
- `response status: 200` là metadata trên `HttpResponse<String>` sau `send`.
- `response body: ACK:PING` là kết quả **`BodySubscriber<String>`** xử lý response body. `HttpClient` nội bộ gọi Flow callbacks, nên ví dụ không cần tự implement `Flow.Subscriber`.

Không nhầm `server.createContext("/echo", exchange -> ...)` với `HttpResponse.BodyHandler`: hàm server fixture phục vụ **HTTP request đến server**, còn `BodyHandler` phía client xử lý **cách nhận response**.

## 8. Ví dụ Java 17+ hoàn chỉnh: custom BodySubscriber, demand và sendAsync

Ví dụ thứ hai cố ý tạo một `Flow.Subscriber<List<ByteBuffer>>` để thấy `BodySubscriber` hoạt động ra sao. `HttpResponse.BodySubscribers.fromSubscriber(...)` chuyển subscriber do ứng dụng viết thành `BodySubscriber<String>` bằng một hàm `finisher`.

Server gửi chuỗi `STREAM:ONE-TWO` trong hai lệnh `write`. Trên client, **không giả định** đó sẽ là đúng hai `onNext`: tầng HTTP/TCP có thể gom/tách dữ liệu tùy cách triển khai.

Tạo file `HttpBodyFlowDemo.java`:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Flow;
import java.util.concurrent.atomic.AtomicReference;

public class HttpBodyFlowDemo {
    static final class CopyingSubscriber
            implements Flow.Subscriber<List<ByteBuffer>> {
        private final ByteArrayOutputStream collected = new ByteArrayOutputStream();
        private Flow.Subscription subscription;
        private int onNextCalls;
        private boolean finished;

        @Override
        public void onSubscribe(Flow.Subscription s) {
            subscription = s;
            s.request(1);
        }

        @Override
        public void onNext(List<ByteBuffer> buffers) {
            for (ByteBuffer buffer : buffers) {
                byte[] chunk = new byte[buffer.remaining()];
                buffer.get(chunk);
                collected.write(chunk, 0, chunk.length);
            }
            onNextCalls++;
            subscription.request(1);
        }

        @Override
        public void onError(Throwable error) {
            System.err.println("response body failed: " + error.getClass().getName());
        }

        @Override
        public void onComplete() {
            finished = true;
        }

        String result() {
            return new String(collected.toByteArray(), StandardCharsets.UTF_8);
        }

        boolean receivedData() {
            return onNextCalls > 0;
        }

        boolean completed() {
            return finished;
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/stream", exchange -> {
            try {
                byte[] message = "STREAM:ONE-TWO".getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=utf-8");
                exchange.sendResponseHeaders(200, 0);
                exchange.getResponseBody().write(message, 0, 7);
                exchange.getResponseBody().write(message, 7, message.length - 7);
            } finally {
                exchange.close();
            }
        });
        server.start();
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create("http://127.0.0.1:"
                            + server.getAddress().getPort() + "/stream"))
                    .GET().build();
            AtomicReference<CopyingSubscriber> observed = new AtomicReference<>();
            HttpResponse.BodyHandler<String> handler = info -> {
                CopyingSubscriber collector = new CopyingSubscriber();
                observed.set(collector);
                return HttpResponse.BodySubscribers.fromSubscriber(
                        collector, CopyingSubscriber::result);
            };

            CompletableFuture<HttpResponse<String>> future =
                    HttpClient.newHttpClient().sendAsync(request, handler);
            HttpResponse<String> response = future.join();
            System.out.println("status: " + response.statusCode());
            System.out.println("onNext called: " + observed.get().receivedData());
            System.out.println("onComplete called: " + observed.get().completed());
            System.out.println("subscriber body: " + response.body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Chạy:

~~~bash
javac HttpBodyFlowDemo.java
java HttpBodyFlowDemo
~~~

Kết quả:

~~~text
status: 200
onNext called: true
onComplete called: true
subscriber body: STREAM:ONE-TWO
~~~

### Giải thích Flow trong ví dụ

1. `HttpResponse.BodyHandler<String>` được gọi khi headers sẵn sàng. Nó tạo một `CopyingSubscriber` mới **cho response này**, rồi dùng `BodySubscribers.fromSubscriber(collector, CopyingSubscriber::result)`.
2. `onSubscribe` được gọi với `Flow.Subscription`; `request(1)` cho phép HTTP client phát **một item List<ByteBuffer>**.
3. `onNext` duyệt **mọi ByteBuffer trong List**, copy đúng số byte `remaining()` vào bộ đệm; gọi `request(1)` để cho phép item tiếp theo. Không xem mỗi item là đúng một frame HTTP, một lần server write hoặc một ký tự.
4. `onComplete` đánh dấu luồng response body đã hết. Adapter `fromSubscriber` áp dụng `finisher` sau khi onComplete, chuyển các byte đã gom thành `String` UTF-8.
5. `CompletableFuture<HttpResponse<String>>` được trả ngay bởi `sendAsync`; `join()` trong **demo** đợi để in output ổn định. Trong ứng dụng bất đồng bộ thật, có thể gắn `thenApply`/`thenAccept` và xử lý exception mà không chặn thread gọi.
6. Vì body type là `String` tích lũy toàn bộ body, ví dụ chỉ phù hợp response nhỏ/đã kiểm soát. Nếu body lớn, hãy dùng subscriber streaming/ghi file và hạn mức dữ liệu.

**Lưu ý:** `onNextCalls` có thể bằng 1, 2 hoặc con số khác. Output chỉ in `onNext called: true`, **không in một số chunk cố định**. `request(1)` điều tiết theo **số lần phát List<ByteBuffer>**, không phải theo byte hay số phần tử trong List.

## 9. Những ranh giới kiểu dữ liệu cần nhớ

~~~text
Request:
  String/byte[]/Path
      -> BodyPublisher extends Flow.Publisher<ByteBuffer>
      -> HttpClient nhận từng ByteBuffer để gửi request.

Response:
  HTTP status + headers
      -> BodyHandler<T>.apply(ResponseInfo)
      -> BodySubscriber<T> extends Flow.Subscriber<List<ByteBuffer>>
      -> getBody(): CompletionStage<T>
      -> HttpResponse<T>.body() có kiểu T.
~~~

So sánh hai nhánh `Flow`:

| Phía | `Flow` type | Ai giữ vai trò subscriber? | Điều nó chuyển? |
| --- | --- | --- | --- |
| **Gửi request** | `Flow.Publisher<ByteBuffer>` | `HttpClient` là subscriber nội bộ | Các buffer body outbound |
| **Nhận response** | `Flow.Subscriber<List<ByteBuffer>>` | `BodySubscriber<T>` do `BodyHandler` chọn | Các list buffer body inbound |
| **Nhận response streaming qua ofPublisher** | `Flow.Publisher<List<ByteBuffer>>` là **body kiểu trả về** | Ứng dụng đăng ký subscriber vào publisher sau khi nhận response | Các list buffer inbound được chuyển tiếp |

Vì `BodySubscriber` nhận **List<ByteBuffer>**, code tự viết cần duyệt hai lớp: mỗi `onNext` có thể có một hoặc nhiều buffer. Nếu decode UTF-8, một ký tự đa byte có thể trải qua nhiều buffer; **không tự decode riêng lẻ từng chunk** bằng `new String(chunk)` rồi nối vì có thể cắt giữa ký tự. Dùng decoder streaming giữ trạng thái hoặc gom/copy byte đúng thứ tự rồi decode khi đủ, như ví dụ dành cho response nhỏ.

Trong Java Flow, terminal signals `onComplete` và `onError` kết thúc subscription; không gọi `request` sau khi đã hủy một subscription để “đọc lại” phần body bị mất. Nếu ứng dụng không muốn nhận tiếp, `subscription.cancel()` là thao tác hủy; nó có hệ quả đối với kết nối HTTP có thể tái sử dụng.

## 10. BodyHandler có thể chọn các chiến lược nhận khác nhau

Không phải response nào cũng nên gom vào String:

| BodyHandler factory | Kiểu body `T` | Đặc điểm |
| --- | --- | --- |
| `BodyHandlers.ofString(UTF_8)` | `String` | Gom body rồi decode; tiện JSON/text nhỏ, cần kiểm soát kích thước |
| `BodyHandlers.ofByteArray()` | `byte[]` | Gom dữ liệu nhị phân; có thể chiếm nhiều RAM |
| `BodyHandlers.ofFile(path)` | `Path` | Ghi byte response vào file; dùng cho download và quản lý đường dẫn/quyền truy cập |
| `BodyHandlers.discarding()` | `Void` | Đọc/bỏ dữ liệu, không tạo body nội dung |
| `BodyHandlers.ofInputStream()` | `InputStream` | Trả stream để ứng dụng đọc dần; **phải đọc hết/đóng** |
| `BodyHandlers.ofLines()` | `Stream<String>` | Đọc từng dòng text; quản lý/đóng stream đúng |
| `BodyHandlers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | Chuyển body thành Flow publisher để ứng dụng tự subscribe/điều tiết |
| Custom `BodyHandler<T>` | Tùy thiết kế | Chọn `BodySubscriber` theo `statusCode/headers`, ví dụ bỏ body khi 204 |

Các `BodyHandlers` có sẵn **không tự từ chối HTTP 4xx/5xx**. Nếu API coi status ngoài 2xx là lỗi nghiệp vụ, sau khi nhận response hãy kiểm tra `response.statusCode()` hoặc chọn subscriber hợp lý từ `BodyHandler.apply`. Việc chọn `discarding()` sẽ bỏ body lỗi, khiến mất chi tiết thông báo server; đôi khi cần giữ body lỗi nhỏ có giới hạn để chẩn đoán.

**`ofInputStream`/`ofLines`/`ofPublisher` có vòng đời khác `ofString`.** `HttpResponse<T>` có thể được trả về trước khi ứng dụng đã tiêu thụ toàn bộ body; nếu ứng dụng giữ stream mà không đọc/đóng, tài nguyên HTTP connection có thể bị chiếm. Với streaming publisher, nếu chưa subscribe hoặc subscriber không request thêm item, response body không thể tự hoàn tất theo cách ứng dụng mong đợi.

Để tải response lớn, cân nhắc `ofFile`, `ofInputStream` hoặc streaming, kiểm tra kích thước khi nhận và xử lý hủy/cleanup. `BodyHandlers.ofString` rất tiện nhưng không nên dùng vô điều kiện với payload có thể quá lớn hoặc từ nguồn không tin cậy.

## 11. Backpressure, cancel và tài nguyên mạng

`Flow.Subscription.request(n)` là tín hiệu **nhu cầu nhận thêm item**, không phải lệnh “đọc n byte từ socket” của ứng dụng. `HttpClient` điều phối nhu cầu để không giao dữ liệu cho subscriber vượt quá demand phù hợp Flow protocol.

**Ở chiều request:**

- Publisher nhận demand từ subscriber nội bộ của `HttpClient` và phát `ByteBuffer` tương ứng.
- Publisher phải tôn trọng `cancel` và phát `onComplete`/`onError` đúng vòng đời.
- Publisher từ file/stream cần quản lý nguồn dữ liệu khi gửi kết thúc/hủy/thất bại. `BodyPublishers.ofInputStream(supplier)` phải có khả năng tạo **InputStream phù hợp mỗi lượt đăng ký** nếu request được gửi lại.
- Nếu `contentLength()` khai báo sai số byte phát, exchange có thể thất bại; không giả định HTTP client tự sửa giúp một publisher tùy biến hỏng.

**Ở chiều response:**

- Subscriber gọi `request(n)` để nhận các **List<ByteBuffer>` tiếp theo, xử lý đúng byte `remaining()`.
- Nếu không muốn tiêu thụ hết, gọi `cancel()`; tài liệu Java cảnh báo việc hủy sớm có thể **đóng connection và không cho tái sử dụng**. Nếu muốn tận dụng keep-alive, chọn chiến lược đọc/bỏ tới cuối khi phù hợp về tài nguyên, timeout và bảo mật.
- Nếu subscriber tự chế bị mắc kẹt vì không bao giờ gọi `request`, response body có thể dừng mãi. Giữ một bộ đệm vô hạn cũng không phải backpressure: phải giới hạn RAM, byte, thời gian và số exchange đồng thời.
- `BodySubscriber.getBody()` phải trả được một `CompletionStage` ở mọi thời điểm; không viết implementation chặn trong `getBody()` khiến HTTP client đứng đợi.
- Sau `onComplete` hoặc `onError`, hoàn tất hoặc đánh dấu thất bại của body stage đúng cách. Dùng factory `BodySubscribers.fromSubscriber(...)` thường an toàn và gọn hơn tự implement toàn bộ protocol.

**Đừng dùng HTTP client BodySubscriber để thay thế mọi xử lý framing ở tầng ứng dụng.** BodySubscriber lo nhận byte response qua HTTP, còn JSON parser/NDJSON parser, limits và schema validation là tầng phía trên.

## 12. Content-Type, Content-Length và thực tế streaming

`Content-Type` và `Content-Length` là **header HTTP**, không phải bản thân body:

- `Content-Type: application/json; charset=utf-8` mô tả loại dữ liệu; `BodyPublishers.ofString`/`BodyHandlers.ofString` không đảm bảo tự kiểm tra JSON schema. Ứng dụng cần tự chọn charset/parse/validate.
- `BodyPublisher.contentLength()` là thông tin **request body** từ publisher, có thể biết hoặc không biết. Nếu unknown (`-1`), HTTP client có thể sử dụng transfer framing phù hợp; việc tự đặt `Content-Length` mâu thuẫn với publisher là không an toàn.
- `Content-Length` trên response có thể không xuất hiện (HTTP/2/framing, truyền chunked HTTP/1.1, hoặc các trường hợp khác). Không coi giá trị header là ranh giới duy nhất của dữ liệu đã được ứng dụng đọc.
- Response có thể dùng `Content-Encoding` như gzip theo cấu hình giao thức; **đừng giả định `BodyHandler` tự động giải nén mọi nội dung**. Xử lý encoding theo hợp đồng API/service thực tế, kiểm soát kích thước **sau giải nén** để tránh payload mở rộng bất thường.
- Một response có thể chứa header báo độ dài nhỏ nhưng body thực hoặc dữ liệu sau decode lớn; cần kiểm tra **số byte thực nhận và hạn mức tài nguyên** trong pipeline, không chỉ kiểm tra header.
- `HEAD`/`204 No Content`/`304 Not Modified` thường không có response body theo semantics HTTP; handler có thể dùng subscriber bỏ body/trả giá trị rỗng thích hợp, nhưng vẫn phải xử lý status/headers.

Nếu ứng dụng yêu cầu giới hạn response size, phải chọn subscriber/streaming consumer có kiểm soát số byte thực và hủy hoặc dừng khi vượt giới hạn; chỉ dùng `BodyHandlers.ofString` sau khi nhìn `Content-Length` không đủ để bảo vệ chắc chắn trước peer không tin cậy.

## 13. Lỗi HTTP, lỗi body và CompletableFuture: đừng trộn lẫn

| Loại sự kiện | Thường xuất hiện ở đâu? | Xử lý đúng |
| --- | --- | --- |
| Server trả `404`/`500` | `HttpResponse.statusCode()`, BodyHandler vẫn có thể được gọi | Là **HTTP status**, không tự tương đương exception Java |
| Không kết nối được/DNS/TLS fail | `send` ném `IOException` hoặc `sendAsync` complete exceptionally | Chưa chắc BodyHandler đã được gọi, vì có thể chưa có response headers |
| Timeout của request | `HttpTimeoutException` hoặc I/O error liên quan | Quản lý deadline/retry theo tính idempotent |
| `BodyPublisher` lỗi khi phát request | Exchange thất bại, lỗi xuất hiện qua `send`/future | Kiểm tra file/stream/publisher, không chỉ response |
| `BodyHandler.apply` ném lỗi | Không tạo được subscriber phù hợp | Sửa logic chọn subscriber; không parse response body ở đây |
| `BodySubscriber.onError` | Flow nhận body gặp lỗi | Không đưa body chưa đủ cho parser như thành công |
| `send` bị interrupt | `InterruptedException` | Khôi phục interrupt state hoặc xử lý policy, không nuốt lỗi |
| `sendAsync` thất bại | Future complete exceptionally, `join()` có thể ném `CompletionException` | Kiểm tra `getCause()`, timeout/cancellation và cleanup |
| Streaming body chưa được tiêu thụ hết | `HttpResponse<InputStream>` có thể đã được trả nhưng stream vẫn mở | Đọc/đóng/cancel phù hợp để giải phóng tài nguyên |

Một đoạn xử lý `sendAsync` thường có thể gắn:

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

future.thenApply(response -> {
    if (response.statusCode() / 100 != 2) {
        throw new IllegalStateException(
                "HTTP status " + response.statusCode());
    }
    return response.body();
}).thenAccept(body -> {
    // Parse/validate và xử lý body đã nhận.
}).exceptionally(error -> {
    // Log phase/cause, áp dụng retry và cleanup đúng chính sách.
    return null;
});
~~~

*Đây là **đoạn minh họa** trong class có `client`/`request` và imports; không phải chương trình độc lập.*

`thenApply`/`thenAccept` có thể chạy trên thread thực hiện completion hoặc thread caller tùy trạng thái Future; không block lâu trong callback. Xử lý lỗi status HTTP **sau** khi nhận response không làm thay đổi sự thật rằng `BodyHandler` đã được dùng để chọn cách tiêu thụ response body.

Với request không idempotent (ví dụ tạo đơn hàng), không retry mù quáng chỉ vì Future lỗi: server có thể đã nhận hoặc xử lý request dù response thất bại. Dùng token/idempotency key và contract nghiệp vụ rõ ràng.

## 14. Những nhầm lẫn phổ biến nhất

| Nhầm lẫn | Vì sao sai? | Cách nhớ |
| --- | --- | --- |
| “BodyPublisher nhận response.” | Publisher này thuộc `HttpRequest` | Publisher **gửi request** |
| “BodyHandler nhận từng byte body.” | Handler chỉ thấy `ResponseInfo` trước body | Handler **chọn subscriber** |
| “BodySubscriber tự quyết định response status.” | Status đã có trước khi subscriber được chọn | Subscriber **tiêu thụ response bytes** |
| “BodyHandlers.ofString và BodyPublishers.ofString tương đương.” | Một cái xử lý inbound, một cái tạo outbound | Kiểm tra tiền tố `HttpRequest`/`HttpResponse` |
| “onNext nhận một ByteBuffer.” | `BodySubscriber` nhận `List<ByteBuffer>` | Duyệt tất cả buffer của mỗi list |
| “request(1) nghĩa là một byte.” | Flow demand đếm item | Một item là một list buffer |
| “Hai write ở server = hai onNext ở client.” | HTTP/TCP không giữ ranh giới write | Không dựa vào chunk count |
| “sendAsync trả Future tức body đã xong.” | Future có thể chưa complete; streaming hoàn tất giai đoạn khác | Hiểu `CompletionStage<T>` và body type |
| “BodyHandler chỉ gọi khi HTTP 200.” | Handler được dùng để nhận response có status khác 2xx | Luôn kiểm tra `statusCode()` |
| “ofInputStream không cần close.” | Connection/resource có thể bị giữ | Đọc và đóng stream |
| “ofString phù hợp download gigabytes.” | Gom body trong RAM | Dùng streaming/ofFile và byte limits |
| “contentLength là số ký tự.” | Nó biểu thị byte | Đếm byte sau encoding |
| “Custom publisher có thể thay buffer ngay sau onNext.” | Vi phạm ownership | Tôn trọng Flow và buffer lifecycle |
| “Cancel subscriber không ảnh hưởng connection.” | Có thể đóng HTTP connection, giảm reuse | Quyết định consume/discard/cancel có ý thức |
| “HTTP 500 luôn làm send ném IOException.” | 500 là status HTTP hợp lệ | Phân loại transport vs HTTP status |
| “Dùng BodyHandler là đang viết server handler.” | Đây là client response handler | Server `HttpHandler` là API khác |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Trong `client.send(request, BodyHandlers.ofString())`, BodyPublisher ở đâu?

*Đáp án:* Nó được gắn **trong `request`**, ví dụ `POST(BodyPublishers.ofString("PING"))`. Tham số của `send` là **BodyHandler** cho **response**, không phải publisher request.

**Câu 2.** Khi nào `BodyHandler.apply(ResponseInfo)` được gọi?

*Đáp án:* Khi status và headers của response đã khả dụng, **trước khi body bytes được nhận**. Handler trả `BodySubscriber<T>` để tiếp tục xử lý body.

**Câu 3.** `BodySubscriber<T>` nhận loại dữ liệu gì trong `onNext`? `request(1)` nghĩa gì?

*Đáp án:* Nhận `List<ByteBuffer>` theo Flow; `request(1)` yêu cầu **một item là một list buffer**, không phải một byte hoặc một buffer đơn.

**Câu 4.** `BodyHandlers.ofInputStream()` đã trả `HttpResponse<InputStream>`. Body lớn đã được đọc hết chưa?

*Đáp án:* **Chưa chắc**. Stage trả body object kiểu InputStream có thể hoàn tất sớm, còn ứng dụng cần tự đọc/đóng stream để kết thúc việc tiêu thụ và giải phóng tài nguyên.

**Câu 5.** Server trả 404 với JSON error body. `BodyHandlers.ofString(UTF_8)` có tự throw `IOException` không?

*Đáp án:* Không phải chỉ vì status 404. Client vẫn có thể nhận `HttpResponse<String>`, phải kiểm tra `statusCode()` rồi xử lý body lỗi. Exception Java xảy ra nếu có lỗi kết nối/HTTP processing/body handling khác.

**Câu 6.** Vì sao một BodyPublisher tùy biến chỉ đọc được một lần có thể lỗi khi request được gửi lại?

*Đáp án:* `HttpClient` có thể subscribe lại khi cần resend. Publisher phải có khả năng phát lại dữ liệu nhất quán hoặc ứng dụng phải chọn chiến lược không retry request không replayable.

**Câu 7.** Vì sao không thể `new String(chunk)` cho từng ByteBuffer rồi nối khi response UTF-8 có tiếng Việt?

*Đáp án:* Một ký tự UTF-8 có nhiều byte và có thể bị tách ở ranh giới buffer; decode riêng từng mảnh có thể làm sai ký tự. Cần streaming decoder giữ trạng thái hoặc gom byte rồi decode đầy đủ.

## 16. Bài tập vận dụng

1. **Theo vết pipeline:** trong `HttpBodyPipelineDemo`, đánh dấu dòng tạo `BodyPublisher`, dòng gắn vào `POST(...)`, dòng `BodyHandler` chọn `BodySubscriber`, và dòng lấy `HttpResponse<String>.body()`. Giải thích vì sao `server.createContext` không phải client BodyHandler.
2. **Đổi kiểu body:** thay `BodySubscribers.ofString(UTF_8)` bằng `BodySubscribers.ofByteArray()`, sửa generic thành `HttpResponse<byte[]>` và decode `new String(response.body(), UTF_8)` sau khi nhận. Nêu điểm trade-off.
3. **Theo status:** sửa server trả `404` và một JSON lỗi nhỏ; thử `BodyHandlers.ofString` rồi in status + body. Viết custom handler dùng `BodySubscribers.replacing("")` cho `204` mà không làm mất metadata.
4. **Backpressure:** trong `HttpBodyFlowDemo`, thử `request(1)` mỗi `onNext` rồi so sánh với việc bỏ gọi request kế tiếp. Xem vì sao Future có thể không hoàn tất nếu flow vẫn cần demand.
5. **Ranh giới chunk:** đổi response thành chuỗi tiếng Việt dài; xem số lần `onNext` có thể thay đổi giữa các lượt và xác minh body cuối vẫn đúng nếu copy toàn bộ byte rồi decode một lần.
6. **Streaming lớn:** phác thảo `BodyHandlers.ofFile(path)` so với `ofString`, tính hạn mức download, xử lý lỗi/hủy/cleanup tệp tải dở.
7. **Kiến trúc client:** vẽ pipeline cho một POST JSON có xác thực, response 201 và response 422; xác định chính xác việc kiểm tra TLS, status HTTP, body type, JSON schema và ACK nghiệp vụ nằm ở lớp nào.
8. **Khả năng retry:** thiết kế `BodyPublisher` từ InputStream có supplier tạo luồng mới cho mỗi subscription, và giải thích cách đảm bảo cùng nội dung khi HTTP client cần resend, tránh retry thao tác nghiệp vụ không idempotent.

## Tài liệu Java chuẩn

- [`HttpRequest.BodyPublisher` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html): `Flow.Publisher<ByteBuffer>` và `contentLength()`.
- [`HttpRequest.BodyPublishers` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html): factory nguồn dữ liệu request.
- [`HttpResponse.BodyHandler<T>` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandler.html): được gọi sau headers, trước response body, chọn `BodySubscriber<T>`.
- [`HttpResponse.BodySubscriber<T>` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html): `Flow.Subscriber<List<ByteBuffer>>` và `getBody()`.
- [`HttpResponse.BodyHandlers` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): factory nhận response.
- [`HttpResponse.BodySubscribers` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): subscriber, mapping, `fromSubscriber` và streaming.
- [`HttpClient` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html): `send`, `sendAsync` và HTTP exchange.
- [`Flow` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html): reactive streams, demand, subscription và terminal signals.
