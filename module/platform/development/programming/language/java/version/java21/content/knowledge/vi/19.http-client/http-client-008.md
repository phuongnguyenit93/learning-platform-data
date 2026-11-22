# Đóng client đúng thứ tự khi ứng dụng graceful shutdown

Khi ứng dụng dừng có trật tự, HttpClient cần tiếp tục sống trong lúc các request đang xử lý còn có thể gọi dịch vụ bên ngoài. Chỉ nên bắt đầu shutdown client sau khi ứng dụng đã ngừng nhận công việc mới và các request handler không còn gửi request đi.

Từ Java 21, HttpClient triển khai AutoCloseable và cung cấp shutdown(), shutdownNow(), awaitTermination(Duration), isTerminated() cùng close(). Các API này cho phép ứng dụng điều khiển việc ngừng nhận request, chờ request cũ hoàn tất và xử lý trường hợp vượt quá thời gian shutdown dự kiến.

## 1. Graceful shutdown cần phối hợp toàn ứng dụng

HttpClient.shutdown() chỉ quản lý vòng đời của chính client. Nó không tự dừng HTTP server đầu vào, không ngăn controller hoặc worker tạo thêm công việc ở tầng ứng dụng, và không chờ các request handler của ứng dụng kết thúc.

Một trình tự shutdown an toàn thường gồm:

1. **Ngừng nhận công việc mới:** đánh dấu instance không còn nhận traffic, ngừng nhận kết nối hoặc request mới ở ingress/load balancer/server.
2. **Drain request đang xử lý:** cho handler hiện tại hoàn tất. Trong giai đoạn này, handler vẫn có thể cần HttpClient để gọi dịch vụ khác.
3. **Ngừng tạo outbound request:** xác nhận không còn thành phần nào có thể submit request mới qua client.
4. **Bắt đầu shutdown HttpClient:** gọi shutdown() để client ngừng nhận request mới và cho các request đã submit tiếp tục.
5. **Chờ trong ngân sách thời gian:** gọi awaitTermination(Duration) để chờ các hoạt động của client hoàn tất.
6. **Xử lý khi hết hạn:** nếu client chưa kết thúc, gọi shutdownNow() như một yêu cầu dừng khẩn cấp rồi chờ thêm trong một khoảng thời gian giới hạn.
7. **Ghi nhận kết quả:** nếu client vẫn chưa terminated, ghi log/metric và để cơ chế điều phối shutdown cấp ứng dụng quyết định bước tiếp theo.

Điểm quan trọng là không đóng client ngay khi bắt đầu dừng ingress. Những handler đang drain có thể vẫn cần client để hoàn thành nghiệp vụ. Ngược lại, nếu đóng client trước khi ngừng tạo outbound request, các lời gọi mới có thể thất bại trong khi request handler vẫn đang chạy.

## 2. Phân biệt shutdown() và close()

Các phương thức vòng đời của HttpClient có mục đích khác nhau:

| Phương thức | Hành vi | Có chờ không? |
|---|---|---|
| shutdown() | Bắt đầu orderly shutdown; các request đã submit qua send() hoặc sendAsync() được phép hoàn tất; không nhận request mới | Không |
| awaitTermination(duration) | Chờ các hoạt động cần thiết để hoàn tất request sau shutdown | Có, tối đa theo duration |
| shutdownNow() | Thử bắt đầu immediate shutdown; implementation có thể thử interrupt các hoạt động đang chạy | Không |
| isTerminated() | Kiểm tra mọi hoạt động đã hoàn tất sau khi shutdown | Không |
| close() | Bắt đầu orderly shutdown và chờ client terminated | Có, không nhận timeout do caller truyền vào |

shutdown() phù hợp khi ứng dụng cần tự kiểm soát ngân sách thời gian và quyết định lúc nào chuyển sang bước dừng khẩn cấp. close() phù hợp khi chủ sở hữu muốn đóng client và chờ tất cả hoạt động kết thúc mà không cần tự viết vòng chờ.

Không nên coi shutdown() là dấu hiệu client đã đóng xong. Sau lời gọi này, request cũ có thể vẫn đang chạy. Chỉ khi isTerminated() trả về true mới biết mọi hoạt động đã hoàn tất sau shutdown.

isTerminated() không trả về true trước khi shutdown() hoặc shutdownNow() được gọi. Sau khi client đã shutdown, lời gọi send() mới sẽ thất bại; sendAsync() mới sẽ hoàn tất exceptional. Vì vậy, ứng dụng phải ngăn việc submit request mới trước khi bắt đầu shutdown.

## 3. Trình tự ở cấp ứng dụng

Ví dụ sau mô tả thứ tự giữa ingress, executor xử lý request và HttpClient. stopAcceptingRequests() là thao tác thuộc server/framework của ứng dụng:

~~~java
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

final class ApplicationLifecycle {
    private final ExecutorService requestHandlers;
    private final HttpClient httpClient;

    ApplicationLifecycle(
            ExecutorService requestHandlers,
            HttpClient httpClient
    ) {
        this.requestHandlers = requestHandlers;
        this.httpClient = httpClient;
    }

    void stop() throws InterruptedException {
        stopAcceptingRequests();

        requestHandlers.shutdown();
        if (!requestHandlers.awaitTermination(20, TimeUnit.SECONDS)) {
            requestHandlers.shutdownNow();
            if (!requestHandlers.awaitTermination(5, TimeUnit.SECONDS)) {
                // Handler vẫn có thể đang dùng HttpClient.
                // Chưa đóng client ở bước này.
                reportHandlersStillRunning();
                throw new IllegalStateException(
                        "Request handlers remain active; HttpClient is still open"
                );
            }
        }

        shutdownHttpClient(httpClient);
    }

    private void stopAcceptingRequests() {
        // Gọi API dừng ingress hoặc server của ứng dụng.
    }

    private void reportHandlersStillRunning() {
        // Ghi log/metric và để lifecycle coordinator xử lý tiếp.
    }

    private void shutdownHttpClient(HttpClient client)
            throws InterruptedException {
        client.shutdown();
        if (!client.awaitTermination(Duration.ofSeconds(20))) {
            client.shutdownNow();
            if (!client.awaitTermination(Duration.ofSeconds(5))) {
                reportHttpClientStillRunning();
            }
        }
    }

    private void reportHttpClientStillRunning() {
        // Ghi nhận client chưa kết thúc trong ngân sách thời gian.
    }
}
~~~

Ví dụ minh họa cách phối hợp, không phải một server hoàn chỉnh. Trong ứng dụng thật, cần nối stopAcceptingRequests() với lifecycle API của web server hoặc framework. Nếu handler không kết thúc sau khi đã yêu cầu dừng, không được giả định rằng chúng sẽ không còn gọi client; chủ sở hữu phải có chính sách rõ ràng cho những tác vụ còn sống trước khi đóng client.

Thời gian chờ trong ví dụ chỉ là giá trị minh họa. Hãy đặt ngân sách phù hợp với thời gian graceful shutdown mà nền tảng triển khai, container orchestrator hoặc hệ thống quản lý service cho phép.

Ngân sách tổng phải bao gồm thời gian dừng ingress, drain handler và drain HttpClient. Nếu mỗi giai đoạn dùng toàn bộ timeout tối đa của riêng nó, tổng thời gian shutdown có thể vượt deadline mà nền tảng cấp cho tiến trình.

## 4. Shutdown HttpClient trong một ngân sách thời gian

Một helper nhỏ có thể thể hiện rõ hai giai đoạn: orderly shutdown và yêu cầu dừng khẩn cấp nếu hết hạn:

~~~java
import java.net.http.HttpClient;
import java.time.Duration;

static boolean stopHttpClient(
        HttpClient client,
        Duration gracefulTimeout,
        Duration forcedTimeout
) throws InterruptedException {
    client.shutdown();

    if (client.awaitTermination(gracefulTimeout)) {
        return true;
    }

    client.shutdownNow();
    return client.awaitTermination(forcedTimeout);
}
~~~

Giá trị trả về:

- true: client đã terminated trong thời gian chờ.
- false: client vẫn chưa terminated khi hết cả thời gian chờ graceful và thời gian chờ sau shutdownNow().

awaitTermination() trả về false khi duration hết trước khi client kết thúc. Duration bằng hoặc nhỏ hơn zero chỉ kiểm tra trạng thái hiện tại mà không chờ.

shutdownNow() là best-effort. API không bảo đảm các hoạt động đang chạy sẽ kết thúc, cũng không bảo đảm code đang chờ các hoạt động đó sẽ luôn được thông báo. Vì vậy, giá trị false sau lần chờ cuối phải được xem là trạng thái chưa dừng xong, không được báo cáo thành shutdown thành công.

## 5. Xử lý interruption trong lúc shutdown

awaitTermination(Duration) ném InterruptedException nếu thread chờ bị interrupt. Tầng lifecycle cần quyết định chính sách khi nhận interruption: chuyển sang dừng khẩn cấp, ghi nhận trạng thái dừng bị gián đoạn và giữ lại interrupt status khi trả quyền điều khiển cho tầng gọi.

Ví dụ:

~~~java
static boolean stopHttpClient(
        HttpClient client,
        Duration gracefulTimeout,
        Duration forcedTimeout
) throws InterruptedException {
    client.shutdown();

    try {
        if (client.awaitTermination(gracefulTimeout)) {
            return true;
        }

        client.shutdownNow();
        return client.awaitTermination(forcedTimeout);
    } catch (InterruptedException interrupted) {
        client.shutdownNow();
        Thread.currentThread().interrupt();
        throw interrupted;
    }
}
~~~

Đoạn mã chủ động gửi yêu cầu dừng khẩn cấp khi luồng điều phối bị interrupt, sau đó khôi phục interrupt status và truyền ngoại lệ lên tầng gọi. Nó không tiếp tục chờ sau interruption; lifecycle coordinator phía trên cần quyết định cách kết thúc quy trình.

close() có chính sách interruption khác: nếu bị interrupt trong lúc chờ, nó có thể gọi shutdownNow(), tiếp tục chờ cho đến khi các hoạt động đang thực thi hoàn tất và khôi phục interrupt status trước khi trả về. Vì vậy, close() có thể tiếp tục block sau khi đã bị interrupt. Nếu cần giới hạn thời gian chờ, hãy điều khiển bằng shutdown() và awaitTermination(Duration).

## 6. Đừng quên response body dạng stream

HttpClient chỉ xem một request là hoàn tất khi các hoạt động cần thiết cho request đã hoàn tất, bao gồm việc phân phối response body. Một response stream chưa được tiêu thụ hoặc đóng có thể khiến orderly shutdown bị treo chờ.

Các trường hợp cần quản lý:

- BodyHandlers.ofInputStream(): đọc stream đến hết hoặc đóng InputStream.
- BodyHandlers.ofLines(): đóng Stream<String> sau khi dùng.
- BodyHandlers.ofPublisher(): subscriber phải yêu cầu dữ liệu hoặc hủy subscription.
- BodySubscriber tùy chỉnh: tiếp tục request dữ liệu đến onComplete/onError, hoặc hủy subscription khi không cần nữa.

Ví dụ với InputStream:

~~~java
HttpResponse<InputStream> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofInputStream()
);

try (InputStream body = response.body()) {
    Files.copy(body, destination);
}
~~~

Nếu ứng dụng bỏ quên stream, publisher hoặc subscription, request có thể chưa hoàn tất. Khi đó awaitTermination() có thể hết hạn dù ingress đã dừng và không còn request handler mới.

## 7. Quản lý các request bất đồng bộ đang chạy

Với sendAsync(), nên giữ tham chiếu tới CompletableFuture hoặc một cấu trúc theo dõi request đang hoạt động. Việc này giúp lifecycle coordinator biết còn bao nhiêu outbound request, request nào đã hoàn tất và request nào cần hủy theo chính sách ứng dụng.

Ví dụ về việc theo dõi future:

~~~java
Set<CompletableFuture<?>> inFlight = ConcurrentHashMap.newKeySet();

CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

inFlight.add(future);
future.whenComplete((response, error) -> inFlight.remove(future));
~~~

Khi bắt đầu drain:

1. Ngừng tạo future mới.
2. Chờ các future hiện tại hoàn tất trong ngân sách thời gian.
3. Nếu deadline hết, hủy những request mà nghiệp vụ cho phép hủy.
4. Bắt đầu HttpClient.shutdown() và chờ client terminated.

Các future trả về bởi implementation JDK có thể hỗ trợ cancellation; cancel(true) cố gắng hủy HTTP exchange và giải phóng tài nguyên sớm. Tuy nhiên, cancellation là best-effort và tác động đến kết nối phụ thuộc HTTP version, trạng thái exchange và implementation. Không dùng việc gọi cancel() như bằng chứng rằng request đã kết thúc; vẫn cần theo dõi completion và trạng thái của client.

Đảm bảo mọi công việc nền được theo dõi. Nếu handler khởi chạy tác vụ detached hoặc callback có thể gửi thêm request sau khi handler đã kết thúc, việc chờ executor của handler không đủ để chứng minh rằng outbound request mới sẽ không còn được tạo.

## 8. Vì sao thứ tự shutdown quan trọng?

Hai tình huống sai thứ tự thường gặp:

| Thứ tự sai | Hậu quả có thể xảy ra | Cách tổ chức lại |
|---|---|---|
| Gọi HttpClient.shutdown() trước khi ngừng nhận request ứng dụng | Handler mới có thể gọi client sau khi client đã ngừng nhận request | Dừng ingress và ngăn tạo công việc mới trước |
| Đóng client trước khi handler đang chạy hoàn tất | Handler đang drain có thể mất khả năng gọi dịch vụ ngoài | Chờ handler hoàn tất hoặc được hủy và xác nhận không còn submit request |
| Chỉ gọi shutdown() rồi kết thúc tiến trình | Request cũ có thể chưa hoàn tất | Chờ awaitTermination() trong ngân sách thời gian |
| Gọi close() trong shutdown path có deadline nghiêm ngặt | close() có thể chờ lâu hơn ngân sách mong muốn | Dùng shutdown() và awaitTermination(Duration) |
| Quên đóng response stream | Request chưa hoàn tất và client có thể không terminated | Đọc hết, đóng hoặc hủy body/subscription |

Graceful shutdown là quy trình phối hợp giữa ingress, request handler, outbound request và tài nguyên. HttpClient chỉ kiểm soát phần outbound request do chính client quản lý.

## 9. HttpClient dùng chung và quyền sở hữu

Trong service chạy lâu dài, thường nên tái sử dụng một HttpClient cho nhiều request có cùng cấu hình. Component tạo hoặc sở hữu client chịu trách nhiệm đóng nó ở cuối vòng đời.

Các component chỉ mượn client không nên tự gọi shutdown() hoặc close() sau một request. Nếu một component đóng client dùng chung, các component khác có thể đang có request chưa hoàn tất hoặc cần gửi request mới.

Nên gom việc đóng client vào một lifecycle coordinator hoặc component sở hữu tài nguyên. Không dựa vào thứ tự chạy của nhiều shutdown hook độc lập để điều phối ingress, handler executor và HTTP client; hãy gọi chúng theo trình tự rõ ràng trong cùng quy trình dừng ứng dụng.

## 10. Khác biệt giữa implementation JDK và custom subclass

HttpClient là abstract class. Các instance tạo bằng HttpClient.newHttpClient() hoặc HttpClient.newBuilder().build() sử dụng implementation tích hợp của JDK, implementation này ghi đè các phương thức lifecycle để cung cấp hành vi best-effort.

Các default implementation ở lớp cơ sở không tự bảo đảm shutdown thực tế: ví dụ shutdown() mặc định không làm gì, shutdownNow() mặc định gọi shutdown(), awaitTermination() mặc định kiểm tra đối số rồi trả về true, còn isTerminated() mặc định trả về false. Nếu tự viết subclass, phải ghi đè các phương thức lifecycle để triển khai hợp đồng phù hợp.

Phần lớn ứng dụng nên dùng implementation do JDK cung cấp thay vì tự subclass HttpClient. Khi dựa vào khả năng giải phóng connection pool và các tài nguyên nền, hãy xác minh hành vi của implementation thực tế.

## 11. Checklist graceful shutdown

- [ ] Dừng nhận request mới ở ingress trước khi shutdown HTTP client.
- [ ] Ngăn tạo công việc mới và drain các request handler hiện có.
- [ ] Chỉ shutdown client khi handler không còn khả năng submit outbound request mới.
- [ ] Gọi HttpClient.shutdown() để bắt đầu orderly shutdown.
- [ ] Chờ bằng awaitTermination(Duration) theo ngân sách thời gian của ứng dụng.
- [ ] Nếu hết hạn, gọi shutdownNow() và chờ thêm trong một khoảng thời gian hữu hạn.
- [ ] Nếu vẫn chưa terminated, ghi nhận trạng thái và không báo shutdown thành công.
- [ ] Đóng/tiêu thụ response stream và quản lý publisher/subscriber.
- [ ] Theo dõi các CompletableFuture đang chạy và hủy có chọn lọc khi deadline yêu cầu.
- [ ] Giữ interrupt status và truyền interruption theo chính sách của lifecycle coordinator.
- [ ] Để đúng component sở hữu client chịu trách nhiệm đóng nó.

## Tài liệu tham khảo

- [Oracle Java SE 21 API — HttpClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle JDK 21 Release Notes — HttpClient lifecycle methods](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html)
- [Oracle Java SE 21 API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
