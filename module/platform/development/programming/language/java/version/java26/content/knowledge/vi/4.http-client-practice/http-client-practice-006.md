# Vòng đời HttpClient và kết thúc các yêu cầu còn chạy

Java 26 cung cấp API quản lý vòng đời `HttpClient` để ứng dụng có thể ngừng nhận request mới, đợi request đã gửi hoàn tất hoặc yêu cầu hủy các thao tác đang chạy. Các phương thức `close()`, `shutdown()`, `shutdownNow()`, `awaitTermination(Duration)` và `isTerminated()` được đưa vào API từ Java 21; chúng vẫn là API ổn định và dùng được trên Java 26. Vì vậy, khi viết ví dụ Java 26, cần ghi đúng mốc phiên bản và không bật preview cho các phương thức này.

Một `HttpClient` thường quản lý pool kết nối riêng và tái sử dụng kết nối cho nhiều request. Nên tạo client theo vòng đời của ứng dụng hoặc thành phần sở hữu nó, dùng lại cho nhiều request, rồi đóng client khi thành phần đó dừng. Tạo client mới cho từng request thường làm mất lợi ích tái sử dụng kết nối.

## 1. Các trạng thái trong vòng đời HttpClient

Có thể nhìn vòng đời của client theo ba giai đoạn:

1. **Đang hoạt động:** client chấp nhận các lời gọi `send()` và `sendAsync()`.
2. **Đang shutdown:** ứng dụng đã yêu cầu dừng. Client từ chối request mới, còn các request đã gửi được tiếp tục xử lý theo chính sách shutdown.
3. **Đã terminated:** tất cả thao tác cần thiết để hoàn tất các request đã gửi trước đó đều kết thúc.

Các phương thức điều khiển trạng thái:

| Phương thức | Tác dụng | Có chờ request kết thúc không? |
|---|---|---|
| `shutdown()` | Bắt đầu dừng có trật tự; từ chối request mới và cho request đã gửi chạy đến khi hoàn tất. | Không |
| `awaitTermination(Duration)` | Chờ tối đa khoảng thời gian chỉ định sau khi đã shutdown. | Có |
| `isTerminated()` | Kiểm tra mọi thao tác đã hoàn tất sau shutdown hay chưa. | Không |
| `shutdownNow()` | Yêu cầu dừng tức thời và thử hủy các thao tác đang chạy. | Không đảm bảo |
| `close()` | Bắt đầu shutdown có trật tự và đợi client terminated. | Có, chờ cho đến khi kết thúc |

`shutdown()` và `close()` đều ngăn request mới, nhưng khác nhau ở việc chờ. `shutdown()` trả về ngay sau khi khởi tạo quá trình dừng. `close()` đợi các thao tác đang chạy hoàn tất. `shutdownNow()` là yêu cầu dừng khẩn cấp theo cơ chế best effort, không phải cam kết rằng mọi request sẽ bị thu hồi ngay lập tức.

## 2. Dùng try-with-resources để đóng client đúng lúc

Từ Java 21, `HttpClient` triển khai `AutoCloseable` nên có thể quản lý bằng try-with-resources. Khi rời khỏi khối `try`, Java gọi `close()` tự động.

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.concurrent.CompletableFuture;

public class HttpClientLifecycle {
    public static void main(String[] args) {
        HttpRequest firstRequest = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/"))
                .GET()
                .build();

        HttpRequest secondRequest = HttpRequest.newBuilder()
                .uri(URI.create("https://openjdk.org/"))
                .GET()
                .build();

        try (HttpClient client = HttpClient.newHttpClient()) {
            CompletableFuture<HttpResponse<String>> first =
                    client.sendAsync(
                            firstRequest,
                            HttpResponse.BodyHandlers.ofString()
                    );

            CompletableFuture<HttpResponse<String>> second =
                    client.sendAsync(
                            secondRequest,
                            HttpResponse.BodyHandlers.ofString()
                    );

            CompletableFuture.allOf(first, second).join();

            System.out.println(first.join().statusCode());
            System.out.println(second.join().statusCode());
        }
    }
}
```

Hai request được gửi bất đồng bộ trên cùng một client. `CompletableFuture.allOf(...).join()` đợi cả hai future hoàn tất; sau đó khối try kết thúc và client được đóng. Với `BodyHandlers.ofString()`, response body được đọc thành chuỗi trước khi future hoàn tất.

Ngay cả khi có exception trong khối `try`, try-with-resources vẫn gọi `close()`. Việc đóng client sẽ chờ những request đã được gửi trước khi shutdown hoàn tất. Vì vậy, nếu request có thể treo lâu hoặc body stream chưa được tiêu thụ, quá trình thoát khỏi khối try cũng có thể chờ lâu.

`close()` không nhận tham số timeout. Nếu thread gọi `close()` bị interrupt trong lúc chờ, implementation mặc định của JDK có thể gọi `shutdownNow()`, sau đó vẫn tiếp tục chờ các thao tác đang thực thi kết thúc và khôi phục interrupt status trước khi trả về. Do đó, không nên coi `close()` là cơ chế dừng có giới hạn thời gian; dùng `shutdown()` kết hợp `awaitTermination(Duration)` nếu cần tự kiểm soát thời hạn chờ.

Dùng cách này khi một thành phần có phạm vi sở hữu client rõ ràng, chẳng hạn một tác vụ batch, một tiến trình CLI hoặc một thành phần ứng dụng có vòng đời đóng/mở xác định.

## 3. Shutdown có trật tự và chờ với thời hạn

Khi ứng dụng cần kiểm soát thời gian chờ, có thể gọi `shutdown()` rồi `awaitTermination(Duration)`. Phương thức `awaitTermination()` trả về:

- `true` nếu client đã terminated trong thời gian chờ.
- `false` nếu thời hạn chờ kết thúc trước khi client terminated.

Ví dụ sau cho client tối đa 30 giây để hoàn tất request đã gửi. Nếu hết thời gian, ứng dụng thử shutdown khẩn cấp rồi chờ thêm 5 giây:

```java
import java.net.http.HttpClient;
import java.time.Duration;

public class HttpClientShutdown {
    static void stopClient(HttpClient client) {
        client.shutdown();

        try {
            boolean terminated =
                    client.awaitTermination(Duration.ofSeconds(30));

            if (!terminated) {
                client.shutdownNow();

                boolean stopped =
                        client.awaitTermination(Duration.ofSeconds(5));

                if (!stopped) {
                    System.err.println(
                            "HttpClient vẫn còn thao tác chưa kết thúc"
                    );
                }
            }
        } catch (InterruptedException e) {
            client.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

Trong ứng dụng thực tế, phương thức dừng cần được gọi bởi thành phần đang sở hữu client. Sau khi `shutdown()` được gọi, các lời gọi `send()` mới có thể thất bại bằng `IOException`; `sendAsync()` có thể trả về future hoàn tất bất thường với `IOException` do client đã shutdown.

Nếu `awaitTermination()` trả về `false`, điều đó chỉ cho biết client chưa hoàn tất trong khoảng thời gian đã cho. Gọi `shutdownNow()` là yêu cầu hủy best effort; kể cả lần chờ thứ hai vẫn trả về `false`, ứng dụng không được tự kết luận rằng các thao tác đã dừng. Hãy ghi log, theo dõi tác vụ còn lại và xử lý theo chính sách dừng của hệ thống.

## 4. shutdownNow không đảm bảo request chưa tới máy chủ

`shutdownNow()` yêu cầu implementation thử kết thúc các thao tác đang hoạt động. Tuy nhiên, API không đảm bảo request sẽ dừng ngay, hoặc mọi thao tác đang chạy sẽ kết thúc. Một request có thể đã được gửi tới máy chủ trước khi yêu cầu hủy được xử lý; máy chủ vẫn có thể tiếp tục thực thi request đó.

Điều này đặc biệt quan trọng với request có tác dụng phụ như tạo đơn hàng, ghi dữ liệu hoặc thanh toán. Hủy future hay shutdown client không tương đương với rollback giao dịch phía máy chủ. Nếu cần tính đúng đắn khi retry hoặc timeout, API nghiệp vụ cần có cơ chế idempotency, mã yêu cầu duy nhất hoặc thao tác tra cứu trạng thái.

Có hai mức hủy thường gặp:

**Hủy một request:** với future trả về từ `sendAsync()`, có thể gọi `cancel(true)`:

```java
var future = client.sendAsync(
        request,
        HttpResponse.BodyHandlers.ofString()
);

// Khi request không còn cần thiết:
boolean cancellationRequested = future.cancel(true);
System.out.println("Đã gửi yêu cầu hủy: " + cancellationRequested);
```

Với implementation mặc định của JDK, future có thể hủy được. `cancel(true)` thử hủy HTTP exchange để giải phóng tài nguyên sớm. Giá trị `true` cho biết future đã nhận trạng thái hủy; nó không chứng minh máy chủ chưa nhận hoặc chưa xử lý request.

**Dừng toàn bộ client:** gọi `shutdownNow()` khi thành phần sở hữu client cần dừng các thao tác của client. Việc này ảnh hưởng mọi request còn chạy trên client đó, do đó không nên dùng một client dùng chung cho nhiều thành phần độc lập rồi gọi shutdown khẩn cấp chỉ vì một request riêng lẻ bị chậm.

Nếu chỉ một request không còn cần thiết, ưu tiên hủy future của request đó. Nếu toàn bộ thành phần đang dừng, dùng shutdown ở cấp client.

## 5. Streaming response body có thể làm shutdown bị treo

Một request chưa chắc đã hoàn tất chỉ vì ứng dụng đã nhận được object `HttpResponse`. Mức độ đọc response body phụ thuộc `BodyHandler` và kiểu body mà ứng dụng chọn.

Với các handler gom toàn bộ dữ liệu như `BodyHandlers.ofString()` hoặc `BodyHandlers.ofByteArray()`, body được đọc vào bộ nhớ trước khi response được hoàn tất. Với handler streaming như `ofInputStream()` hoặc publisher, ứng dụng phải quản lý việc tiêu thụ body.

Ví dụ tải body dạng stream:

```java
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;

public class DownloadWithStreamingBody {
    public static void main(String[] args) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/archive.bin"))
                .GET()
                .build();

        try (HttpClient client = HttpClient.newHttpClient()) {
            HttpResponse<InputStream> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofInputStream()
            );

            try (InputStream body = response.body();
                 OutputStream output =
                         Files.newOutputStream(Path.of("archive.bin"))) {
                body.transferTo(output);
            }
        }
    }
}
```

Khối try của `InputStream` đảm bảo stream được đóng kể cả khi ghi file phát sinh lỗi. Đọc đến hết stream hoặc đóng stream khi không cần đọc tiếp để request được giải phóng. Nếu chỉ lấy `HttpResponse<InputStream>` rồi bỏ quên `response.body()`, request có thể vẫn mở và làm chậm shutdown.

Với `BodySubscriber` tùy chỉnh, subscriber phải yêu cầu dữ liệu tiếp tục cho đến khi nhận `onComplete()` hoặc `onError()`, hoặc hủy subscription. Một subscriber ngừng yêu cầu dữ liệu mà không hủy subscription có thể khiến response không hoàn tất.

Đây là nguyên nhân phổ biến khiến `close()` hoặc `awaitTermination()` chờ lâu dù ứng dụng tưởng rằng request đã trả response. Khi điều tra, kiểm tra cả future, stream, publisher và subscriber của từng request.

## 6. isTerminated và kiểm tra trạng thái

`isTerminated()` trả về `true` khi mọi thao tác đã hoàn tất sau một lần gọi `shutdown()` hoặc `shutdownNow()`. Phương thức này không chờ và có thể dùng để kiểm tra sau một lần chờ:

```java
client.shutdown();

try {
    if (client.awaitTermination(Duration.ofSeconds(10))) {
        System.out.println("Client đã dừng hoàn toàn");
    } else {
        System.out.println("Client chưa dừng trong thời hạn");
    }

    System.out.println("Terminated: " + client.isTerminated());
} catch (InterruptedException e) {
    client.shutdownNow();
    Thread.currentThread().interrupt();
}
```

`isTerminated()` không phải phép kiểm tra client còn mở hay không trước khi shutdown. Theo hợp đồng API, nó không thể trả về `true` nếu chưa gọi `shutdown()` hoặc `shutdownNow()` trước đó. `HttpClient` không cung cấp phương thức `isShutdown()` như `ExecutorService`; hãy quản lý trạng thái sở hữu client trong thành phần ứng dụng nếu cần biết thời điểm bắt đầu dừng.

## 7. Implementation mặc định và custom HttpClient

Các client tạo bằng `HttpClient.newHttpClient()` hoặc `HttpClient.newBuilder().build()` sử dụng implementation mặc định của JDK. Implementation này ghi đè các phương thức vòng đời để cung cấp hành vi shutdown thực tế.

Tuy nhiên, `HttpClient` là lớp abstract và các phương thức vòng đời có implementation mặc định trong lớp cơ sở. Một implementation tùy chỉnh có thể không ghi đè chúng: `shutdown()` mặc định không làm gì, `shutdownNow()` mặc định chỉ gọi `shutdown()`, `awaitTermination()` mặc định có thể trả về `true` và `isTerminated()` mặc định trả về `false`. Vì vậy, khi dùng implementation HTTP Client của bên thứ ba, phải kiểm tra hợp đồng vòng đời của implementation đó.

Đừng giả định mọi object có kiểu `HttpClient` đều có hành vi quản lý tài nguyên giống implementation tích hợp của JDK. Nếu ứng dụng dùng client từ provider riêng, hãy kiểm tra khả năng đóng, chính sách hủy request và cách quản lý response stream của provider.

## 8. Những thói quen nên áp dụng

- Tạo ít client có vòng đời rõ ràng và tái sử dụng chúng cho nhiều request; tránh tạo một client mới cho mỗi request.
- Với tác vụ có phạm vi ngắn, dùng try-with-resources để tự động gọi `close()`.
- Với service chạy lâu, đóng client khi thành phần sở hữu dừng; không đóng client dùng chung sau mỗi request.
- Dùng `shutdown()` khi muốn ngừng nhận request mới nhưng cho request cũ hoàn tất.
- Dùng `awaitTermination(Duration)` để giới hạn thời gian chờ và `isTerminated()` để kiểm tra kết quả.
- Chỉ dùng `shutdownNow()` khi cần yêu cầu dừng khẩn cấp; xử lý khả năng request đã tới máy chủ và vẫn đang được xử lý.
- Hủy future khi chỉ một request không còn cần thiết; không shutdown toàn client dùng chung vì một request riêng lẻ.
- Đọc hết hoặc đóng response stream; với custom subscriber, luôn yêu cầu dữ liệu đến trạng thái kết thúc hoặc hủy subscription.
- Không dựa vào garbage collector để quản lý thời điểm giải phóng client. Việc tài nguyên được thu hồi sau khi client không còn reachable còn phụ thuộc mọi request đã hoàn tất.
- Không dùng finalization hoặc API legacy để đóng client. Dùng `AutoCloseable.close()` và API vòng đời chính thức.

## Tài liệu tham chiếu

1. [Oracle Java SE 26 API – HttpClient](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html)
2. [Oracle Java SE 26 API – HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
3. [Oracle Java SE 26 API – HttpResponse.BodySubscribers](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html)
4. [Oracle Java SE 26 API – CompletableFuture](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
5. [JEP 321 – HTTP Client (Standard)](https://openjdk.org/jeps/321)

