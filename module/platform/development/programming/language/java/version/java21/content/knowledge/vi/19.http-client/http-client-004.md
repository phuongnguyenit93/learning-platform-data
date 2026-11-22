# shutdown, shutdownNow, awaitTermination và isTerminated

Từ Java 21, `java.net.http.HttpClient` có các phương thức quản lý vòng đời gồm `shutdown()`, `shutdownNow()`, `awaitTermination(Duration)`, `isTerminated()` và `close()`. Các API này cho phép ứng dụng chủ động ngừng nhận request mới, chờ những exchange đã gửi hoàn tất hoặc yêu cầu dừng sớm khi cần kết thúc ứng dụng.

Trong phạm vi `JAVA_VERSION_JAVA21` (Java 21), cần quản lý vòng đời `HttpClient` ở cấp thành phần hoặc ứng dụng. Một client thường được tái sử dụng cho nhiều request để chia sẻ cấu hình và kết nối. Vì vậy, không gọi shutdown sau mỗi request; chỉ đóng client khi thành phần sở hữu nó kết thúc hoạt động.

## Vì sao HttpClient cần lifecycle API?

`HttpClient` có thể quản lý tài nguyên và công việc nền để thực hiện HTTP exchange, bao gồm xử lý request bất đồng bộ, quản lý kết nối và các tác vụ nội bộ. Trước Java 21, API công khai tập trung vào cấu hình client và gửi request; Java 21 bổ sung các thao tác vòng đời để ứng dụng có thể chủ động kết thúc việc sử dụng client.

Các trường hợp thường cần shutdown client:

- Ứng dụng đang tắt và không muốn nhận thêm request mới.
- Một service hoặc component bị tháo khỏi hệ thống, cần chờ các HTTP exchange đã bắt đầu hoàn tất.
- Một tác vụ triển khai hoặc bảo trì cần giới hạn thời gian chờ client dừng.
- Ứng dụng cần yêu cầu dừng sớm các exchange còn hoạt động khi đã hết thời gian graceful shutdown.

`HttpClient` được thiết kế để dùng lại cho nhiều request. Tạo một client mới cho từng request làm mất lợi ích tái sử dụng cấu hình và kết nối, đồng thời khiến ứng dụng phải quản lý nhiều vòng đời client hơn mức cần thiết.

## Phân biệt bốn phương thức chính

| Phương thức | Ý nghĩa | Có chờ đến khi kết thúc không? |
| --- | --- | --- |
| `shutdown()` | Bắt đầu shutdown có trật tự; request đã được gửi có cơ hội hoàn tất, request mới không được chấp nhận | Không; phương thức khởi tạo quá trình shutdown |
| `shutdownNow()` | Yêu cầu dừng ngay việc xử lý, gồm cố gắng dừng exchange đang hoạt động và ngừng xử lý công việc đang chờ | Không bảo đảm mọi exchange đang chạy dừng ngay |
| `awaitTermination(Duration)` | Chờ tối đa thời lượng chỉ định để client kết thúc sau khi đã shutdown | Có, trong giới hạn thời gian |
| `isTerminated()` | Kiểm tra client đã hoàn tất shutdown và mọi hoạt động liên quan đã kết thúc hay chưa | Không; chỉ kiểm tra trạng thái hiện tại |

`shutdown()` phù hợp cho đường tắt ứng dụng bình thường. `shutdownNow()` là biện pháp mạnh hơn khi cần kết thúc nhanh, nhưng vẫn là yêu cầu best-effort đối với các hoạt động đang thực thi. `awaitTermination()` dùng để chờ có giới hạn; `isTerminated()` dùng để quan sát trạng thái.

## shutdown: ngừng nhận request mới và cho request đã gửi hoàn tất

`shutdown()` bắt đầu quá trình shutdown có trật tự. Những request đã được gửi tới client trước khi shutdown được phép hoàn tất, còn request mới sẽ không được chấp nhận. Phương thức này không chờ tất cả exchange kết thúc; ứng dụng có thể tiếp tục bằng `awaitTermination()`.

Ví dụ, một thành phần gửi request bất đồng bộ và sau đó bắt đầu đóng client:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

public class GracefulHttpShutdown {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/health"))
                .GET()
                .build();

        CompletableFuture<HttpResponse<String>> response =
                client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

        response.whenComplete((result, error) -> {
            if (error != null) {
                System.err.println("HTTP exchange failed: " + error);
            } else {
                System.out.println("HTTP status: " + result.statusCode());
            }
        });

        // Không gửi request mới sau điểm này.
        client.shutdown();

        if (client.awaitTermination(Duration.ofSeconds(10))) {
            System.out.println("HTTP client đã kết thúc");
        } else {
            System.out.println("Client vẫn còn hoạt động sau thời hạn chờ");
        }
    }
}
```

Request được gửi trước `shutdown()`, vì vậy nó thuộc nhóm hoạt động đã được submit và được phép hoàn tất. `awaitTermination()` chờ client kết thúc trong tối đa 10 giây. Ví dụ minh họa vòng đời; trong ứng dụng thật, nên đăng ký xử lý kết quả của `CompletableFuture` ngay khi gửi request, đồng thời xử lý lỗi hoặc cancellation thay vì phụ thuộc vào một callback được đăng ký sau khi client đã kết thúc.

Sau khi shutdown bắt đầu, không dùng client để gửi request mới. Hãy đảm bảo tầng nhận request của ứng dụng đã ngừng tạo công việc mới trước khi gọi shutdown, tránh cuộc đua giữa request mới và quá trình đóng client.

## shutdownNow: yêu cầu dừng sớm

`shutdownNow()` yêu cầu client dừng việc xử lý ngay khi có thể. Client cố gắng dừng các exchange đang hoạt động và ngừng xử lý các exchange đang chờ. Đây là yêu cầu best-effort; phương thức không đảm bảo mọi thao tác mạng hoặc xử lý ở phía server bị chấm dứt tức thời.

Ví dụ, ứng dụng đã hết thời gian graceful shutdown và cần yêu cầu dừng sớm:

```java
client.shutdown();

if (!client.awaitTermination(Duration.ofSeconds(10))) {
    client.shutdownNow();
}
```

Không nên gọi `shutdownNow()` ngay khi bắt đầu đóng ứng dụng nếu vẫn còn request cần hoàn tất, chẳng hạn thao tác ghi dữ liệu hoặc gửi callback cuối cùng. Hãy xác định request nào có thể bị hủy, request nào cần hoàn tất và hậu quả nghiệp vụ nếu client dừng giữa chừng.

`shutdownNow()` cũng không thể thu hồi một request mà server đã nhận và thực hiện xong. Việc client hủy exchange ở phía local không đồng nghĩa server rollback side effect. Với request có tác động như thanh toán hoặc tạo đơn hàng, cần thiết kế idempotency key, trạng thái xử lý và cơ chế đối soát phù hợp.

## awaitTermination(Duration): chờ với thời hạn rõ ràng

`awaitTermination(Duration)` chặn thread gọi cho đến khi một trong các điều kiện xảy ra:

- Client đã kết thúc sau yêu cầu shutdown.
- Hết thời lượng chờ được truyền vào.
- Thread đang chờ bị interrupt.

Phương thức trả về `true` nếu client đã terminated, `false` nếu hết thời gian chờ trước khi client kết thúc và ném `InterruptedException` nếu thread gọi bị interrupt.

```java
import java.net.http.HttpClient;
import java.time.Duration;

static boolean waitForClient(HttpClient client) {
    try {
        return client.awaitTermination(Duration.ofSeconds(15));
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return false;
    }
}
```

Đoạn code trên giả định `shutdown()` hoặc `shutdownNow()` đã được gọi trước đó. Nếu thread chờ bị interrupt, khôi phục interrupt status để tầng gọi cao hơn vẫn nhận biết yêu cầu dừng. Tùy chính sách ứng dụng, tầng gọi có thể tiếp tục yêu cầu `shutdownNow()` hoặc ghi nhận quá trình shutdown bị gián đoạn.

Thời hạn chờ nên phù hợp với ngân sách tắt ứng dụng. Không dùng một thời gian chờ vô hạn trong hook shutdown hoặc luồng điều phối nếu nền tảng triển khai yêu cầu tiến trình phải dừng trong một khoảng thời gian xác định.

## isTerminated: kiểm tra client đã kết thúc hoàn toàn

`isTerminated()` trả về `true` khi client đã được shutdown và tất cả hoạt động liên quan đã kết thúc. Phương thức không chờ và không khởi tạo shutdown.

```java
import java.net.http.HttpClient;
import java.time.Duration;

static void waitUntilTerminated(HttpClient client) throws InterruptedException {
    client.shutdown();

    while (!client.isTerminated()) {
        if (!client.awaitTermination(Duration.ofSeconds(1))) {
            System.out.println("Đang chờ các HTTP exchange hoàn tất...");
        }
    }

    System.out.println("Client đã terminated");
}
```

Trong ứng dụng thực tế, thường nên dùng một lần `awaitTermination()` với deadline tổng thể thay vì lặp vô hạn. `isTerminated()` phù hợp để kiểm tra trạng thái trong health/diagnostic hoặc sau khi đã chờ.

`isTerminated()` chỉ có ý nghĩa kết thúc sau một yêu cầu shutdown. Một client đang hoạt động bình thường không được xem là terminated chỉ vì tạm thời không có request nào.

## Quy trình graceful shutdown có deadline

Một trình tự thường dùng khi ứng dụng dừng:

1. Ngừng nhận công việc mới ở tầng server hoặc component gọi HTTP.
2. Gọi `client.shutdown()` để ngừng nhận request mới và cho exchange đã gửi cơ hội hoàn tất.
3. Gọi `awaitTermination(gracePeriod)` để chờ trong thời hạn graceful shutdown.
4. Nếu hết thời hạn mà client chưa terminated, gọi `client.shutdownNow()` để yêu cầu dừng sớm.
5. Có thể chờ thêm một khoảng ngắn bằng `awaitTermination(forcePeriod)` và ghi nhận nếu client vẫn chưa kết thúc.
6. Kiểm tra `isTerminated()` để xác nhận trạng thái cuối cùng.

Ví dụ đóng client với hai khoảng thời gian:

```java
import java.net.http.HttpClient;
import java.time.Duration;

static void stopClient(HttpClient client) {
    client.shutdown();

    try {
        if (!client.awaitTermination(Duration.ofSeconds(20))) {
            client.shutdownNow();

            if (!client.awaitTermination(Duration.ofSeconds(5))) {
                System.err.println("HttpClient chưa terminated sau shutdownNow");
            }
        }
    } catch (InterruptedException e) {
        client.shutdownNow();
        Thread.currentThread().interrupt();
    }

    if (client.isTerminated()) {
        System.out.println("HttpClient đã dừng hoàn toàn");
    }
}
```

Hàm này minh họa chính sách: chờ 20 giây để hoàn tất bình thường, sau đó yêu cầu dừng ngay và chờ thêm tối đa 5 giây. Nếu thread điều phối bị interrupt, nó yêu cầu `shutdownNow()` và khôi phục interrupt status. Ứng dụng cần quyết định cách báo lỗi hoặc tiếp tục shutdown nếu client vẫn chưa terminated sau thời hạn cuối.

## close và try-with-resources

Trong Java 21, `HttpClient` triển khai `AutoCloseable`. Có thể dùng `close()` hoặc try-with-resources khi phạm vi sở hữu client có ranh giới rõ ràng. `close()` thực hiện shutdown có trật tự và chờ các hoạt động hoàn tất; do đó, việc đóng client có thể chặn thread gọi.

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class ShortLivedClient {
    static void run() throws Exception {
        try (HttpClient client = HttpClient.newHttpClient()) {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create("https://example.com/"))
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(
                    request, HttpResponse.BodyHandlers.ofString());

            System.out.println(response.statusCode());
        }
    }
}
```

Ví dụ này phù hợp khi client chỉ được dùng trong phạm vi tác vụ và request hoàn tất trước khi thoát block. Với client dùng chung trong toàn ứng dụng, không đặt nó trong try-with-resources của từng request; hãy để thành phần sở hữu client đóng nó khi thành phần đó dừng.

Nếu cần kiểm soát deadline shutdown rõ ràng hoặc muốn xử lý riêng trường hợp graceful shutdown không hoàn tất, gọi `shutdown()`, `awaitTermination()` và `shutdownNow()` tường minh sẽ phù hợp hơn việc chỉ dựa vào `close()`.

## Phân biệt HttpClient lifecycle với ExecutorService lifecycle

Tên các phương thức của `HttpClient` khá giống `ExecutorService`, nhưng hai API quản lý hai loại tài nguyên khác nhau:

| Nội dung | `HttpClient` | `ExecutorService` |
| --- | --- | --- |
| Đối tượng được quản lý | HTTP client và các exchange do client quản lý | Executor và các task được submit |
| `shutdown()` | Ngừng nhận request mới, cho request đã gửi cơ hội hoàn tất | Ngừng nhận task mới, cho task đã submit tiếp tục |
| `shutdownNow()` | Yêu cầu dừng exchange đang chạy và ngừng xử lý exchange đang chờ | Cố gắng interrupt task đang chạy và trả về task chưa bắt đầu |
| `awaitTermination()` | Chờ client kết thúc | Chờ executor kết thúc |
| `isTerminated()` | Kiểm tra toàn bộ hoạt động của client đã kết thúc | Kiểm tra executor và các task đã kết thúc |

Không áp dụng giả định về kiểu trả về hoặc danh sách task của `ExecutorService.shutdownNow()` cho `HttpClient.shutdownNow()`. Hãy đọc đúng API của đối tượng đang quản lý. `HttpClient.shutdownNow()` là phương thức vòng đời của client, không phải cách lấy danh sách các `Runnable` đang chờ trong executor.

Nếu tạo `HttpClient` bằng builder và cung cấp một executor do ứng dụng sở hữu, hãy quản lý vòng đời executor đó theo hợp đồng sở hữu riêng của ứng dụng. Không giả định shutdown `HttpClient` đồng nghĩa với việc ứng dụng đã đóng mọi executor hoặc tài nguyên khác do ứng dụng tự cung cấp.

## Xử lý request bất đồng bộ trong quá trình shutdown

`sendAsync()` trả về `CompletableFuture` đại diện cho kết quả của một exchange. Future này và trạng thái lifecycle của client có liên quan nhưng không đồng nhất:

- `CompletableFuture` cho biết kết quả của một request cụ thể.
- `HttpClient.awaitTermination()` chờ toàn bộ hoạt động do client quản lý kết thúc.
- `shutdown()` không tự động có nghĩa mọi future đã hoàn tất ngay tại thời điểm gọi.
- `shutdownNow()` có thể khiến exchange đang chạy bị dừng hoặc future hoàn tất bất thường; ứng dụng phải xử lý `CompletionException`, cancellation hoặc lỗi tương ứng.

Nên đăng ký xử lý kết quả ngay sau khi gọi `sendAsync()`:

Trong ví dụ dưới đây, `logger` là logger do ứng dụng cung cấp.

```java
CompletableFuture<HttpResponse<String>> future = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString());

future.whenComplete((response, error) -> {
    if (error != null) {
        logger.warn("HTTP exchange không hoàn tất bình thường", error);
        return;
    }

    logger.info("HTTP status: {}", response.statusCode());
});
```

Khi ứng dụng bắt đầu shutdown, các callback vẫn cần xử lý lỗi và cancellation an toàn. Không giả định callback luôn chạy thành công hoặc server đã hoàn tác request nếu client exchange bị hủy.

## Những lỗi thiết kế cần tránh

- **Shutdown client sau từng request:** làm mất khả năng tái sử dụng client và khiến các request tiếp theo không thể dùng client đó.
- **Gọi shutdownNow ngay lập tức:** có thể cắt ngang exchange quan trọng, gây trạng thái nghiệp vụ không rõ ràng.
- **Không đặt deadline cho awaitTermination:** có thể làm tiến trình dừng kéo dài ngoài ngân sách triển khai.
- **Nhầm isTerminated với không có request đang chạy:** client chưa shutdown vẫn chưa terminated.
- **Nhầm HttpClient với ExecutorService:** lifecycle API tương tự tên nhưng quản lý các đối tượng khác nhau.
- **Bỏ qua interruption:** nếu thread đang chờ awaitTermination bị interrupt, cần xử lý và khôi phục trạng thái theo chính sách của ứng dụng.
- **Cho rằng hủy HTTP exchange sẽ rollback phía server:** cancellation ở client không đảo ngược side effect đã xảy ra ở hệ thống từ xa.

## Quy trình áp dụng trong dự án Java 21

1. **Xác định chủ sở hữu HttpClient.** Client thuộc về toàn ứng dụng, một service hay một tác vụ có phạm vi ngắn?
2. **Tái sử dụng client trong suốt vòng đời sở hữu.** Không tạo và shutdown client cho từng request nếu có thể chia sẻ một client đã cấu hình.
3. **Ngừng phát sinh request mới.** Đóng cổng tiếp nhận hoặc dừng component gửi request trước khi gọi shutdown.
4. **Bắt đầu graceful shutdown.** Gọi `shutdown()` để request đã gửi có cơ hội hoàn tất.
5. **Chờ trong thời hạn.** Dùng `awaitTermination(Duration)` theo ngân sách shutdown của ứng dụng.
6. **Yêu cầu dừng sớm nếu cần.** Gọi `shutdownNow()` khi hết thời hạn graceful và chấp nhận rủi ro hủy exchange.
7. **Xác nhận trạng thái.** Dùng `isTerminated()` và log nếu client chưa kết thúc sau thời hạn cuối.
8. **Xử lý interruption và request async.** Khôi phục interrupt status khi phù hợp, đồng thời xử lý lỗi/cancellation của các `CompletableFuture`.
9. **Đóng theo vòng đời component.** Dùng `close()`/try-with-resources khi phạm vi sở hữu phù hợp; tránh đóng client dùng chung sau mỗi request.

Các lifecycle API của `HttpClient` trong Java 21 giúp ứng dụng kết thúc HTTP client có trật tự và có deadline. `shutdown()` cho request đã gửi cơ hội hoàn tất; `shutdownNow()` yêu cầu dừng sớm; `awaitTermination()` chờ trong thời gian xác định; `isTerminated()` xác nhận trạng thái cuối. Hãy gắn việc shutdown với vòng đời của component sở hữu client và xác định rõ cách xử lý request còn hoạt động khi ứng dụng dừng.
