# HttpClient triển khai AutoCloseable trong Java 21

Từ Java 21, java.net.http.HttpClient triển khai AutoCloseable và có thể được quản lý bằng try-with-resources. Khi đóng client, JDK khởi tạo quá trình shutdown có trật tự: các request đã gửi được phép hoàn tất, client ngừng nhận request mới và close() chờ các hoạt động nền kết thúc.

Thay đổi này giúp ứng dụng quản lý vòng đời tài nguyên mà HttpClient sử dụng, chẳng hạn connection pool và các hoạt động xử lý request. Để tận dụng đúng API, cần hiểu khi nào nên đóng client, close() chờ điều gì và vì sao response body dạng stream cũng phải được đọc hoặc đóng.

## 1. Điểm mới của HttpClient trong Java 21

HttpClient được đưa vào Java từ JDK 11. Tuy nhiên, khả năng quản lý vòng đời bằng AutoCloseable là thay đổi của Java 21. Từ phiên bản này, lớp HttpClient triển khai AutoCloseable và bổ sung các phương thức shutdown, shutdownNow, awaitTermination, isTerminated cùng close.

| API | Vai trò |
|---|---|
| AutoCloseable | Cho phép dùng HttpClient trong try-with-resources |
| close() | Khởi tạo shutdown có trật tự và chờ các hoạt động đã gửi hoàn tất |
| shutdown() | Ngừng nhận request mới và cho request đã gửi tiếp tục hoàn tất; không chờ |
| shutdownNow() | Cố gắng khởi tạo shutdown tức thời, có thể thử ngắt các hoạt động đang chạy |
| awaitTermination(Duration) | Chờ client kết thúc trong khoảng thời gian chỉ định |
| isTerminated() | Kiểm tra mọi hoạt động đã hoàn tất sau khi shutdown hay chưa |

Các phương thức quản lý vòng đời này có từ Java 21. Vì vậy, mã nguồn cần biên dịch với JDK 21 trở lên mới có thể gọi chúng. Không thể dùng close() trên HttpClient của JDK 11 đến JDK 20.

## 2. Vì sao cần đóng HttpClient?

Một HttpClient có thể quản lý connection pool riêng và tái sử dụng kết nối giữa nhiều request. Client đã được cấu hình là immutable và có thể gửi nhiều request. Tạo một client mới cho mỗi thao tác thường làm mất cơ hội tái sử dụng kết nối giữa các lần gọi.

Khi ứng dụng không còn cần client, đóng nó giúp thu hồi sớm tài nguyên mà client đang quản lý, thay vì chỉ chờ garbage collector thu hồi đối tượng. Việc đóng client cũng xác định rõ thời điểm ứng dụng ngừng gửi request qua client đó.

Do đó:

- Tái sử dụng một HttpClient cho nhiều request có cùng cấu hình và cùng phạm vi vòng đời.
- Đóng client tại nơi sở hữu vòng đời của nó, chẳng hạn khi một tác vụ ngắn hạn kết thúc hoặc khi ứng dụng dừng.
- Không tạo rồi đóng một client riêng cho từng request nếu mục tiêu là tái sử dụng connection pool.
- Không tiếp tục gửi request qua client sau khi bắt đầu shutdown.

## 3. Dùng try-with-resources để đóng client

Ví dụ sau tạo một client, gửi request đồng bộ và tự động đóng client khi ra khỏi block:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class HttpClientLifecycle {
    public static void main(String[] args)
            throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com"))
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
            System.out.println(response.body());
        }
    }
}
~~~

Trong ví dụ:

1. HttpRequest mô tả URI, timeout, header và HTTP method.
2. HttpClient.Builder cấu hình connect timeout trước khi tạo client.
3. send() gửi request đồng bộ và trả về khi response được nhận, với body được xử lý theo BodyHandler đã chọn.
4. Khi block try kết thúc, Java gọi client.close() tự động.

BodyHandlers.ofString() đọc body thành String trước khi response được trả về. Vì vậy, ví dụ không giữ một InputStream mở sau khi ra khỏi block.

close() không khai báo ném checked exception. Tuy nhiên, send() có thể ném IOException hoặc InterruptedException, nên phương thức gọi vẫn cần xử lý hoặc khai báo các ngoại lệ đó.

## 4. close() thực hiện shutdown có trật tự

Khi gọi close(), client bắt đầu một quá trình orderly shutdown:

- Các request đã được gửi bằng send() hoặc sendAsync() được phép chạy đến khi hoàn tất.
- Client không nhận request mới sau khi shutdown bắt đầu.
- close() chờ các hoạt động cần thiết cho những request đã gửi kết thúc.
- Khi mọi hoạt động đã hoàn tất, client ở trạng thái terminated.

Vì close() chờ hoàn tất, lời gọi này có thể mất thời gian nếu request còn đang chờ mạng hoặc response body chưa được tiêu thụ hết. Đây là hành vi có chủ đích để tài nguyên được giải phóng sau khi các hoạt động của client hoàn tất.

Không nên gọi close() ngay sau khi gửi một request bất đồng bộ mà chưa hiểu rằng close() sẽ chờ request đó. Nếu cần quản lý shutdown riêng, có thể dùng shutdown() và awaitTermination().

## 5. Phân biệt shutdown, shutdownNow, awaitTermination và close

| Phương thức | Có ngừng nhận request mới? | Có chờ request cũ hoàn tất? | Cách dùng |
|---|---|---|---|
| shutdown() | Có | Không | Bắt đầu shutdown có trật tự |
| awaitTermination(duration) | Không tự khởi tạo shutdown | Có, tối đa duration | Chờ sau khi đã shutdown |
| shutdownNow() | Có | Không chờ; cố gắng yêu cầu dừng ngay | Trường hợp cần thử dừng khẩn cấp |
| close() | Có | Có, chờ đến khi client terminated | Đóng client, thường qua try-with-resources |

Ví dụ điều khiển shutdown có thời hạn:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

client.shutdown();

if (!client.awaitTermination(Duration.ofSeconds(20))) {
    client.shutdownNow();

    if (!client.awaitTermination(Duration.ofSeconds(5))) {
        throw new TimeoutException("HttpClient has not terminated");
    }
}
~~~

Ví dụ này giả định client đã được tạo và các ngoại lệ InterruptedException được xử lý ở tầng gọi. shutdown() chỉ bắt đầu quá trình đóng và trả về ngay; awaitTermination() mới là phương thức chờ. Nếu hết thời gian, shutdownNow() thử khởi tạo shutdown tức thời.

shutdownNow() không bảo đảm mọi request đang chạy sẽ dừng ngay. Hành vi của hoạt động đang chạy khi bị interrupt không được bảo đảm; một số hoạt động có thể tiếp tục hoặc không thông báo hoàn tất theo cách ứng dụng mong đợi. Không dùng phương thức này thay cho shutdown có trật tự trong luồng xử lý bình thường.

isTerminated() chỉ trả về true khi mọi hoạt động đã hoàn tất sau shutdown hoặc shutdownNow. Trước khi một trong hai phương thức shutdown được gọi, isTerminated() không trả về true.

## 6. Gửi request bất đồng bộ trước khi đóng client

sendAsync() trả về CompletableFuture ngay sau khi khởi tạo việc gửi request. Request vẫn thuộc vòng đời của HttpClient. Khi đóng client, các request đã được submit trước thời điểm shutdown được phép hoàn tất:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

public class AsyncHttpClientLifecycle {
    public static void main(String[] args) {
        try (HttpClient client = HttpClient.newHttpClient()) {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create("https://example.com"))
                    .timeout(Duration.ofSeconds(10))
                    .GET()
                    .build();

            CompletableFuture<HttpResponse<String>> future =
                    client.sendAsync(
                            request,
                            HttpResponse.BodyHandlers.ofString()
                    );

            future.thenApply(HttpResponse::statusCode)
                    .thenAccept(System.out::println)
                    .join();
        }
    }
}
~~~

Trong ví dụ, join() chờ pipeline CompletableFuture hoàn tất trước khi thoát khỏi block. Khi client.close() được gọi, request đã hoàn tất và client có thể kết thúc shutdown.

Nếu không chờ future, close() vẫn chờ những request đã gửi hoàn tất theo hợp đồng của client. Tuy nhiên, ứng dụng thường nên giữ và theo dõi CompletableFuture để xử lý kết quả, ngoại lệ hoặc hủy request theo logic nghiệp vụ.

## 7. Đóng response body dạng stream

Một request có thể được xem là chưa hoàn tất nếu response body vẫn đang được tiêu thụ. Điều này đặc biệt quan trọng với các BodyHandler trả về stream hoặc publisher.

Với BodyHandlers.ofInputStream(), response body là InputStream. Hãy đọc đến hết hoặc đóng stream:

~~~java
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;

try (HttpClient client = HttpClient.newHttpClient()) {
    HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://example.com/file"))
            .GET()
            .build();

    HttpResponse<InputStream> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofInputStream()
    );

    try (InputStream body = response.body()) {
        Files.copy(body, Path.of("download.bin"));
    }
}
~~~

Block try bên trong bảo đảm InputStream được đóng ngay cả khi thao tác ghi file gặp lỗi. Sau khi stream được tiêu thụ hoặc đóng, request có thể hoàn tất và client có thể hoàn tất orderly shutdown.

Các trường hợp khác cũng cần quản lý vòng đời body:

- BodyHandlers.ofLines() trả về Stream<String>; phải đóng stream sau khi sử dụng.
- BodyHandlers.ofPublisher() trả về Publisher; subscriber cần yêu cầu dữ liệu hoặc hủy subscription.
- BodySubscriber tùy chỉnh cần request dữ liệu cho đến khi hoàn tất hoặc hủy subscription khi không cần dữ liệu nữa.

Nếu bỏ quên stream hoặc subscription, client.close() có thể tiếp tục chờ vì request chưa hoàn tất. Đây là một nguyên nhân phổ biến khiến shutdown bị kéo dài.

## 8. Dùng một client dùng chung trong ứng dụng dài hạn

Không phải mọi HttpClient đều nên nằm trong một block try-with-resources ngắn. Với ứng dụng server hoặc service chạy lâu dài, một client thường được tạo ở lúc khởi động, dùng cho nhiều request và đóng khi thành phần sở hữu nó dừng.

Ví dụ mô tả một service sở hữu client:

~~~java
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.io.IOException;

final class RemoteService implements AutoCloseable {
    private final HttpClient client = HttpClient.newHttpClient();

    HttpResponse<String> call(HttpRequest request)
            throws IOException, InterruptedException {
        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );
    }

    @Override
    public void close() {
        client.close();
    }
}
~~~

Trong ứng dụng thực tế, framework hoặc application lifecycle manager có thể gọi close() của RemoteService khi dừng. Các component khác có thể dùng service này thay vì tự tạo một HttpClient cho mỗi request.

Quy tắc sở hữu rất quan trọng: component tạo hoặc quản lý client chịu trách nhiệm đóng nó. Một component chỉ mượn client dùng chung không nên tự đóng client sau mỗi lần gọi, vì việc đó có thể làm hỏng các request của component khác.

## 9. close() khi thread bị interrupt

close() không khai báo InterruptedException, nhưng thao tác chờ bên trong có thể bị interrupt. Theo hợp đồng Java 21, nếu thread bị interrupt trong lúc close() chờ:

1. close() có thể thử dừng các hoạt động bằng shutdownNow().
2. close() tiếp tục chờ cho đến khi các hoạt động đang thực thi hoàn tất.
3. Trước khi trả về, close() khôi phục interrupt status của thread.

Vì vậy, không nên giả định close() sẽ trả về ngay khi thread bị interrupt. Nếu ứng dụng cần một quy trình shutdown có deadline hoặc chính sách dừng riêng, hãy dùng shutdown(), awaitTermination(Duration) và shutdownNow() theo trình tự phù hợp.

## 10. Lưu ý về implementation

HttpClient là abstract class. Các instance thông thường tạo bằng HttpClient.newHttpClient() hoặc HttpClient.newBuilder().build() dùng implementation có sẵn của JDK. Implementation này ghi đè close(), shutdown(), shutdownNow(), awaitTermination() và isTerminated() để quản lý vòng đời tài nguyên ở mức tốt nhất có thể.

Các default implementation trong lớp cơ sở có thể không thực hiện đầy đủ việc shutdown: ví dụ shutdown() mặc định không làm gì và awaitTermination() mặc định trả về true. Nếu tự xây dựng subclass của HttpClient, cần ghi đè các phương thức quản lý vòng đời để cung cấp hành vi phù hợp. Phần lớn ứng dụng không cần subclass HttpClient; nên dùng builder và implementation mặc định của JDK.

## 11. Các lỗi thường gặp

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Tạo một HttpClient mới cho từng request | Khó tái sử dụng connection pool giữa các request | Dùng lại client trong cùng phạm vi cấu hình và vòng đời |
| Đóng client ngay sau khi submit sendAsync() mà không hiểu shutdown | close() sẽ chờ request đã gửi; lời gọi có thể chặn | Theo dõi future và xác định rõ thời điểm đóng client |
| Quên đóng InputStream từ ofInputStream() | Request có thể chưa hoàn tất và shutdown bị kéo dài | Đọc hết hoặc dùng try-with-resources cho stream |
| Dùng shutdown() rồi giả định client đã kết thúc | shutdown() không chờ | Gọi awaitTermination() hoặc close() |
| Dùng shutdownNow() như một bảo đảm hủy mọi request | Không có bảo đảm mọi hoạt động đang chạy sẽ dừng | Thiết kế timeout, cancellation và xử lý kết quả riêng |
| Đóng client dùng chung sau từng lần gọi | Các component khác có thể không gửi được request tiếp | Để chủ sở hữu client quản lý việc đóng |

## 12. Checklist quản lý vòng đời HttpClient

- [ ] Dùng JDK 21 trở lên khi cần AutoCloseable và API shutdown của HttpClient.
- [ ] Xác định rõ component nào sở hữu và chịu trách nhiệm đóng client.
- [ ] Tái sử dụng client cho nhiều request có cùng cấu hình và vòng đời.
- [ ] Dùng try-with-resources cho client có phạm vi ngắn, hoặc đóng client ở giai đoạn ứng dụng dừng.
- [ ] Hiểu rằng close() chờ các request đã submit hoàn tất và từ chối request mới.
- [ ] Nếu dùng shutdown(), chờ bằng awaitTermination() khi cần xác nhận kết thúc.
- [ ] Chỉ dùng shutdownNow() khi chấp nhận hành vi dừng không được bảo đảm đối với hoạt động đang chạy.
- [ ] Đọc hết hoặc đóng response stream; quản lý subscription của publisher và custom subscriber.
- [ ] Kiểm tra request bất đồng bộ và CompletableFuture trước khi đóng client.

Việc HttpClient triển khai AutoCloseable trong Java 21 giúp quản lý tài nguyên rõ ràng hơn. Dùng try-with-resources cho client ngắn hạn, tái sử dụng client trong service dài hạn và luôn hoàn tất response body là ba nguyên tắc cốt lõi để shutdown diễn ra có trật tự.

## Tài liệu tham khảo

- [Oracle Java SE 21 API — HttpClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle JDK 21 Release Notes — HttpClient lifecycle methods](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html)
- [Oracle Java SE 21 API — AutoCloseable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AutoCloseable.html)
