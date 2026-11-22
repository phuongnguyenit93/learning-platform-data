# Ghép nhiều yêu cầu bất đồng bộ có giới hạn đồng thời (Java 11+)

## 1. Bài toán và mục tiêu

Giả sử ứng dụng cần lấy dữ liệu của 8 tài nguyên qua HTTP. Từng yêu cầu độc lập, có thời gian phản hồi khác nhau. Nếu khởi động tất cả cùng lúc, ứng dụng có thể gây quá tải dịch vụ đích, vượt hạn mức kết nối hoặc làm tăng số tác vụ đang chờ. Nếu gửi tuần tự, tổng thời gian lại quá dài.

Ta muốn **cho tối đa 3 yêu cầu đang được xử lý cùng lúc (in-flight)**, nhưng ngay khi một yêu cầu hoàn tất thì khởi động yêu cầu kế tiếp; cuối cùng ghép kết quả **đúng thứ tự đầu vào**. Một lỗi mạng hay HTTP 503 của một tài nguyên cần được xử lý rõ ràng, không làm mất kết quả các tài nguyên khác.

Đây là bài toán *bounded concurrency* (giới hạn đồng thời), khác với *rate limiting* (giới hạn số yêu cầu trong một giây). Giới hạn 3 yêu cầu đồng thời **không tự động** bảo đảm tối đa 3 yêu cầu/giây.

**Kiến thức sử dụng:** `java.net.http.HttpClient` và `sendAsync` (có từ Java 11), `CompletableFuture`, `thenCompose`, `handle`, `allOf`, các kiểu atomic của `java.util.concurrent`. Đây là các API hiện hành, không cần thư viện bất đồng bộ cũ hay cú pháp đã lỗi thời.

## 2. Ghép bất đồng bộ và giới hạn đồng thời là hai việc khác nhau

- **`thenCompose`:** dùng khi bước B phụ thuộc kết quả bước A; B trả về một `CompletableFuture`, và `thenCompose` nối chúng thành một luồng bất đồng bộ, tránh `CompletableFuture<CompletableFuture<T>>`.
- **`thenCombine`:** ghép kết quả của hai `CompletableFuture` độc lập khi cả hai hoàn thành. Tự nó không giới hạn số tác vụ đã khởi chạy.
- **`CompletableFuture.allOf`:** tạo điểm đợi để biết tất cả các future đã hoàn tất; nó **không tự khởi chạy hay giới hạn** request. Nếu tạo 1.000 lời gọi `sendAsync` trước rồi đưa vào `allOf`, 1.000 lời gọi vẫn đã được khởi tạo.
- **Giới hạn đồng thời:** phải đặt **ngay tại điểm bắt đầu request**. Ta quản lý `K` “làn” (slot/worker logic). Mỗi làn khởi chạy tối đa một `sendAsync`; khi future đó hoàn tất, làn lấy đầu việc tiếp theo.

Không nên chỉ đặt `Executors.newFixedThreadPool(3)` cho callback rồi cho rằng HTTP sẽ có tối đa 3 request in-flight: giới hạn số thread callback không đồng nghĩa với giới hạn số request mạng đã gửi.

## 3. Thuật toán “cửa sổ trượt” tối đa K yêu cầu

1. Chép danh sách URI đầu vào để giữ thứ tự cố định. Kiểm tra `K >= 1`.
2. Khởi động `min(K, N)` làn. Mỗi làn lấy chỉ số kế tiếp bằng `AtomicInteger.getAndIncrement()`, nên không làn nào lấy trùng công việc.
3. Làn tạo `HttpRequest` rồi gọi `HttpClient.sendAsync(...)`. Nó **không** gọi `get()` hay `join()` trong khi đợi mạng.
4. `handle` ghi kết quả của vị trí vừa xong, kể cả khi request lỗi, rồi `thenCompose` nối sang đầu việc kế tiếp của chính làn đó.
5. Sau khi mọi làn kết thúc, `allOf` hoàn tất. Đọc các kết quả theo chỉ số ban đầu để ghép thành danh sách có thứ tự.

**Bất biến:** ban đầu chỉ có nhiều nhất `K` request đang chạy. Mỗi làn chỉ gửi request tiếp theo sau khi future của request trước đã hoàn thành. Bởi vậy tại mọi thời điểm số request in-flight không thể vượt `K`. Khi một request chậm, các làn khác vẫn có thể tiếp tục; khác với cách gom thành các đợt K phần tử rồi đợi hết cả đợt (*batch barrier*), vốn có thể để các slot trống.

## 4. Ví dụ chạy được: 8 HTTP request, tối đa 3 đang chạy

Ví dụ dùng HTTP server cục bộ của JDK chỉ để mô phỏng API, không phụ thuộc Internet. Lớp `BoundedAsyncHttpDemo` chứa cả client và server kiểm thử. Server trả `200` với dữ liệu bình thường, riêng mục số 5 trả `503`. Client ghi kết quả theo thứ tự 1 đến 8 dù thứ tự hoàn thành có thể khác nhau.

Lưu toàn bộ mã sau vào **`BoundedAsyncHttpDemo.java`**:

```java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReferenceArray;

public class BoundedAsyncHttpDemo {
    static final class Outcome {
        final int status;
        final String body;

        Outcome(int status, String body) {
            this.status = status;
            this.body = body;
        }
    }

    static final class Batch {
        final List<Outcome> outcomes;
        final int peakInFlight;

        Batch(List<Outcome> outcomes, int peakInFlight) {
            this.outcomes = outcomes;
            this.peakInFlight = peakInFlight;
        }
    }

    static CompletableFuture<Batch> fetchBounded(
            HttpClient client, List<URI> urls, int limit) {
        if (limit < 1) {
            throw new IllegalArgumentException("limit must be >= 1");
        }
        List<URI> inputs = List.copyOf(urls);
        for (URI uri : inputs) {
            String scheme = uri.getScheme();
            if (!"http".equalsIgnoreCase(scheme)
                    && !"https".equalsIgnoreCase(scheme)) {
                throw new IllegalArgumentException("Only HTTP(S) is supported: " + uri);
            }
        }
        AtomicInteger next = new AtomicInteger();
        AtomicInteger inFlight = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();
        AtomicReferenceArray<Outcome> results = new AtomicReferenceArray<>(inputs.size());

        CompletableFuture<?>[] lanes = new CompletableFuture[Math.min(limit, inputs.size())];
        for (int i = 0; i < lanes.length; i++) {
            lanes[i] = runLane(client, inputs, next, inFlight, peak, results);
        }
        return CompletableFuture.allOf(lanes).thenApply(ignored -> {
            List<Outcome> ordered = new ArrayList<>();
            for (int i = 0; i < inputs.size(); i++) {
                ordered.add(results.get(i));
            }
            return new Batch(ordered, peak.get());
        });
    }

    private static CompletableFuture<Void> runLane(
            HttpClient client, List<URI> urls, AtomicInteger next,
            AtomicInteger inFlight, AtomicInteger peak,
            AtomicReferenceArray<Outcome> results) {
        int index = next.getAndIncrement();
        if (index >= urls.size()) {
            return CompletableFuture.completedFuture(null);
        }
        HttpRequest request = HttpRequest.newBuilder(urls.get(index))
                .timeout(Duration.ofSeconds(3)).GET().build();

        int now = inFlight.incrementAndGet();
        peak.accumulateAndGet(now, Math::max);
        return client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .handle((response, error) -> {
                    inFlight.decrementAndGet();
                    if (error == null) {
                        results.set(index, new Outcome(response.statusCode(), response.body()));
                    } else {
                        Throwable cause = error;
                        while (cause instanceof CompletionException && cause.getCause() != null) {
                            cause = cause.getCause();
                        }
                        results.set(index, new Outcome(-1, cause.getClass().getSimpleName()));
                    }
                    return (Void) null;
                })
                .thenCompose(ignored -> runLane(client, urls, next, inFlight, peak, results));
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService serverWorkers = Executors.newFixedThreadPool(8);
        server.setExecutor(serverWorkers);
        server.createContext("/item/", exchange -> {
            try {
                int id = Integer.parseInt(
                        exchange.getRequestURI().getPath().substring("/item/".length()));
                try {
                    Thread.sleep(80);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
                int status = id == 5 ? 503 : 200;
                String body = id == 5 ? "busy" : "ok-" + id;
                byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(status, bytes.length);
                try (OutputStream output = exchange.getResponseBody()) {
                    output.write(bytes);
                }
            } finally {
                exchange.close();
            }
        });
        server.start();
        try {
            int port = server.getAddress().getPort();
            List<URI> urls = new ArrayList<>();
            for (int id = 1; id <= 8; id++) {
                urls.add(URI.create("http://127.0.0.1:" + port + "/item/" + id));
            }
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2)).build();
            Batch batch = fetchBounded(client, urls, 3).join();
            for (int i = 0; i < batch.outcomes.size(); i++) {
                Outcome outcome = batch.outcomes.get(i);
                System.out.println((i + 1) + ": HTTP " + outcome.status + ", " + outcome.body);
            }
            System.out.println("Peak <= 3: " + (batch.peakInFlight <= 3));
        } finally {
            server.stop(0);
            serverWorkers.shutdownNow();
        }
    }
}
```

Biên dịch bằng JDK 11 trở lên (mã đã được kiểm tra với tùy chọn đích Java 11):

```bash
javac --release 11 BoundedAsyncHttpDemo.java
java BoundedAsyncHttpDemo
```

Kết quả mẫu (8 dòng dữ liệu có thứ tự cố định; server chạy trên cổng ngẫu nhiên nhưng cổng không được in ra):

```text
1: HTTP 200, ok-1
2: HTTP 200, ok-2
3: HTTP 200, ok-3
4: HTTP 200, ok-4
5: HTTP 503, busy
6: HTTP 200, ok-6
7: HTTP 200, ok-7
8: HTTP 200, ok-8
Peak <= 3: true
```

`Thread.sleep(80)` chỉ nằm trong **server giả lập** để tạo độ trễ. Client dùng `sendAsync` và không ngủ, không chặn thread khi chờ một request. `join()` chỉ xuất hiện một lần ở ranh giới `main`, khi chương trình thử nghiệm cần in kết quả cuối.

## 5. Tại sao cách ghép này đúng?

- **Đúng giới hạn:** có đúng `min(K, N)` làn ban đầu; mỗi làn có tối đa một future HTTP đang chờ. `inFlight` tăng ngay trước `sendAsync` và giảm trong `handle` khi future hoàn thành; `peak` đo đỉnh số lời gọi chưa xử lý xong.
- **Không mất hoặc lặp đầu việc:** `AtomicInteger` cấp phát mỗi chỉ số một lần. Khi hết chỉ số, làn trả về `completedFuture(null)`.
- **Kết quả đúng thứ tự:** từng `Outcome` được ghi vào ô `results[index]`; chỉ sau `allOf` mới đọc từ 0 tới N−1. Vì vậy thời gian hoàn thành không quyết định thứ tự trả về.
- **Lỗi từng request:** `handle` biến lỗi hoàn thành bất thường của future HTTP thành `Outcome(-1, tên_lỗi)` và tiếp tục lấy việc mới. Trong khi đó HTTP 503 vẫn là **phản hồi HTTP hợp lệ ở tầng giao thức** với `statusCode() == 503`, không tự biến thành exception. Ứng dụng phải tự xác định status nào là thành công.
- **Danh sách rỗng:** tạo 0 làn; `allOf` với mảng rỗng hoàn thành ngay và trả danh sách rỗng. `limit < 1` bị từ chối sớm.

**Độ phức tạp:** tối đa `K` request HTTP in-flight; bộ nhớ lưu input/result là `O(N)`. Ví dụ dùng chuỗi future được nối tiếp cho từng làn, phù hợp tập công việc hữu hạn. Với luồng hàng triệu mục hoặc các future liên tục hoàn tất đồng bộ, nên dùng bộ lập lịch dạng vòng lặp/hàng đợi giới hạn và điều phối callback trên executor được quản lý để tránh chuỗi phụ thuộc quá dài hoặc đệ quy sâu.

## 6. Áp dụng vào dịch vụ thật

1. **Dùng lại một `HttpClient`** cho nhiều request; không tạo client mới cho mỗi URI. Thay server giả lập bằng endpoint thực, truyền header xác thực khi cần, và chỉ gửi đến URI đáng tin cậy.
2. **Tách timeout:** `connectTimeout` là thời gian thiết lập kết nối; `HttpRequest.timeout` là hạn chờ request. Tùy yêu cầu nghiệp vụ, thêm deadline tổng cho cả lô. `join()` của lô sẽ đợi mọi làn kết thúc.
3. **Chọn chính sách lỗi:** ví dụ giữ cả HTTP 503 trong kết quả để không mất các mục thành công. Khi cần fail-fast, có thể hoàn thành future tổng theo lỗi đầu tiên và chủ động quản lý/cancel các future con; chỉ `cancel` future tổng **không đảm bảo** mọi HTTP request đang chạy tự dừng.
4. **Đặt giới hạn theo hệ thống thực:** thử với `K=1`, `K=3`, `K=5`; đo latency p95, số lỗi/timeout, HTTP 429 và tải của dịch vụ. Nếu API có quota theo giây, kết hợp bộ giới hạn tốc độ riêng. Nhiều instance ứng dụng cần quota chung nếu giới hạn ở phía dịch vụ đích tính toàn hệ thống.
5. **Retry có kiểm soát:** chỉ retry lỗi phù hợp (chẳng hạn timeout tạm thời, 429 hoặc 503 khi chính sách API cho phép), dùng exponential backoff kèm jitter, tôn trọng `Retry-After` và giới hạn số lần thử. Mỗi lần retry phải **chiếm lại một slot**; tránh tạo request retry vượt `K`. Với POST/ghi dữ liệu, cân nhắc tính idempotent trước khi retry.
6. **Khi cần kết quả ngay khi có:** ví dụ hiện tại cố ý ghép thành danh sách sau `allOf`. Nếu cần streaming kết quả đến người dùng, đẩy mỗi `Outcome` tới consumer ngay trong callback nhưng vẫn duy trì giới hạn in-flight và đồng bộ hóa consumer nếu cần.

## 7. Lỗi thường gặp và cách kiểm chứng

| Lỗi | Hậu quả | Cách đúng |
|---|---|---|
| Gọi `sendAsync` cho toàn bộ danh sách rồi mới `allOf` | Không có giới hạn in-flight | Cấp K làn; bắt đầu việc kế tiếp khi làn hoàn thành |
| Chia danh sách thành từng đợt K rồi đợi cả đợt | Một request chậm làm các slot khác đứng rỗi | Dùng cửa sổ trượt như `runLane` |
| Gọi `Semaphore.acquire()` hoặc `join()` ngay trong callback bất đồng bộ | Có thể giữ/chặn thread xử lý callback | Dùng `thenCompose` và bộ lập lịch không chặn |
| Tưởng HTTP 429/500 sẽ luôn đi vào nhánh exception | Bỏ sót lỗi nghiệp vụ từ status code | Kiểm tra `response.statusCode()` |
| `thenApply` trả về một future khác | Sinh `CompletableFuture<CompletableFuture<T>>` | Dùng `thenCompose` cho bước phụ thuộc bất đồng bộ |
| Ghi kết quả theo thứ tự callback hoàn thành | Kết quả bị đảo so với input | Lưu theo chỉ số và chỉ ghép khi đã xong |
| Chỉ tăng kích thước thread pool để giới hạn HTTP | Số request đã gửi vẫn có thể vượt dự kiến | Đặt quota tại chỗ khởi động request |

**Bài tự kiểm tra:** đổi giới hạn thành 1, 2, 5, 8 rồi kiểm tra `peakInFlight <= limit`; tăng số URL nhưng giữ `limit=3`; sửa server trả 503 ở nhiều mục và xác nhận kết quả còn đủ N mục, đúng vị trí. Thử lỗi mạng thực (server dừng giữa chừng) và quan sát `status=-1` cho request bị lỗi.

**Ranh giới cần nhớ:** giải pháp thực hành này quản lý số future HTTP đồng thời trong **một lần gọi hàm, một tiến trình**. Một hệ thống có nhiều request handler hoặc nhiều instance phải chia sẻ bộ giới hạn phù hợp nếu cần một trần toàn cục. Để xử lý tải rất lớn, bổ sung hàng đợi có giới hạn/bộ phát theo nhu cầu (backpressure), quan sát metric và quản lý hủy tác vụ rõ ràng.