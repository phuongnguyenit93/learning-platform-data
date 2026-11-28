# So sánh độ trễ, thông lượng và hành vi khi mất kết nối

## 1. Mục tiêu và phạm vi

Bài thực hành này xây dựng một phép đo có thể lặp lại cho `java.net.http.HttpClient` trên JDK 26 trở lên, tập trung vào ba câu hỏi:

1. Một request mất bao lâu từ lúc gửi đến khi đọc xong response?
2. Khi tăng số request đồng thời, client hoàn thành được bao nhiêu request mỗi giây và độ trễ đuôi thay đổi thế nào?
3. Client phản ứng ra sao khi server chậm, kết nối bị ngắt, timeout xảy ra hoặc server trả mã lỗi HTTP?

HTTP/3 được đưa vào HttpClient tích hợp trong JDK từ Java 26 qua JEP 517. Trong JDK 27, API HTTP/3 vẫn là API chính thức. Bài dùng các API ổn định: `HttpClient`, `HttpRequest`, `HttpResponse`, `CompletableFuture` và `HttpOption.H3_DISCOVERY`. Không cần bật preview hoặc thêm module incubator.

Mọi phép đo cần chạy trên endpoint thử nghiệm mà bạn kiểm soát. Không dùng benchmark để tạo tải lớn lên dịch vụ bên ngoài hoặc production khi chưa có giới hạn tải được phê duyệt.

## 2. Những yếu tố cần phân biệt trước khi đo

### 2.1. Độ trễ, thông lượng và độ trễ đuôi

| Chỉ số | Ý nghĩa | Cách đọc |
|---|---|---|
| Latency | Thời gian của một request từ lúc bắt đầu đến khi nhận và xử lý xong response body theo BodyHandler đang dùng. | Đơn vị ms. |
| p50 | 50% request hoàn thành trong hoặc dưới giá trị này. | Đại diện mức điển hình. |
| p95 | 95% request hoàn thành trong hoặc dưới giá trị này. | Cho thấy nhóm request chậm. |
| p99 | 99% request hoàn thành trong hoặc dưới giá trị này. | Quan trọng với trải nghiệm tail latency. |
| Throughput | Số request hoàn thành trong một đơn vị thời gian. | Request/second (req/s). |
| Goodput | Lượng dữ liệu hữu ích được chuyển trong một đơn vị thời gian. | Byte/s hoặc MiB/s; phải biết kích thước body. |
| Error rate | Tỷ lệ request không tạo ra kết quả nghiệp vụ thành công. | Cần tách lỗi HTTP và lỗi truyền tải. |

Một phép đo chỉ có thời gian trung bình là chưa đủ. Ví dụ, hai cấu hình cùng đạt 500 req/s nhưng cấu hình A có p99 là 120 ms, cấu hình B có p99 là 2.000 ms. Cấu hình B có thể gây timeout ở người dùng dù throughput tổng thể có vẻ tốt.

Phân biệt các nhóm kết quả:

- **HTTP response:** server đã trả về response. Mã 404, 429 hoặc 503 vẫn là response hợp lệ ở tầng HTTP; chúng không tự động biến thành exception của `HttpClient`.
- **Transport failure:** không nhận được response do DNS, kết nối, TLS, reset, timeout, lỗi giao thức hoặc sự cố mạng.
- **Application failure:** response thành công ở tầng HTTP nhưng nội dung hoặc kết quả nghiệp vụ không đạt yêu cầu.

### 2.2. HTTP/1.1, HTTP/2 và HTTP/3 có đặc điểm khác nhau

| Giao thức | Đặc điểm ảnh hưởng đến phép đo | Điều cần kiểm chứng |
|---|---|---|
| HTTP/1.1 | Kết nối keep-alive có thể được tái sử dụng; song song thường cần nhiều kết nối TCP. | Số kết nối, thời gian bắt tay và khả năng tái sử dụng. |
| HTTP/2 | Nhiều stream có thể dùng chung một kết nối TCP; giảm số lần thiết lập kết nối khi có nhiều request. Mất gói TCP có thể ảnh hưởng việc truyền dữ liệu trên toàn kết nối. | ALPN/upgrade có thành công không, giới hạn stream và tình trạng TCP. |
| HTTP/3 | Nhiều stream chạy trên QUIC/UDP; cơ chế mất gói được xử lý theo stream ở tầng QUIC. TLS 1.3 tích hợp với quá trình bắt tay QUIC. | Server có QUIC, mạng cho phép UDP, giao thức thực tế và thời gian thiết lập kết nối. |

Không có kết luận chung rằng HTTP/3 luôn nhanh hơn HTTP/2 hoặc HTTP/1.1. Mạng LAN, WAN, RTT, mất gói, kích thước response, số request đồng thời, khả năng server và việc kết nối đã được làm nóng đều có thể làm thay đổi kết quả.

### 2.3. Tái sử dụng HttpClient là điều kiện quan trọng

Một `HttpClient` thường quản lý pool kết nối riêng và tái sử dụng các kết nối khi phù hợp. Pool giữa các instance thường không được chia sẻ. Nếu tạo client mới cho từng request, bạn thường mất lợi ích tái sử dụng kết nối và phép đo sẽ phản ánh chi phí tạo kết nối nhiều hơn hành vi steady-state.

Do đó:

- Tạo một client cho mỗi cấu hình giao thức.
- Dùng lại client đó cho nhiều request và nhiều luồng.
- Không tạo một client mới trong vòng lặp gửi request.
- Đo riêng request đầu tiên và giai đoạn steady-state sau warm-up.

## 3. Thiết kế phép đo công bằng

Chọn một endpoint HTTPS thử nghiệm có thể phục vụ cùng nội dung qua các giao thức cần so sánh. Với HTTP/3, server phải nhận QUIC tại đúng host và port của URI nếu dùng chế độ kiểm tra nghiêm ngặt.

Giữ các yếu tố sau giống nhau giữa các lượt đo:

- Cùng máy client, server, DNS, route mạng và proxy policy.
- Cùng URI, method, headers, authentication và kích thước request/response.
- Cùng chính sách timeout, redirect và xử lý body.
- Cùng số request, concurrency và thời gian warm-up.
- Không chạy benchmark khác đồng thời trên cùng máy hoặc server.
- Chạy nhiều lượt và luân phiên thứ tự giao thức để giảm ảnh hưởng của tải nền.

Nên tách hai loại phép đo:

**Cold/first-request:** tạo client mới và đo request đầu tiên. Kết quả bao gồm DNS lookup nếu chưa có cache, thiết lập kết nối, TLS/QUIC handshake, thương lượng giao thức và thời gian server xử lý.

**Warm/steady-state:** giữ nguyên client, gửi warm-up, sau đó đo một tập request có concurrency cố định. Kết quả phản ánh tốt hơn chi phí request khi kết nối có thể được tái sử dụng.

Không trộn hai loại kết quả vào cùng một percentile. Request đầu tiên có thể chậm hơn đáng kể vì chưa có kết nối được tái sử dụng.

### 3.1. Chọn phiên bản giao thức và xác minh phiên bản thực tế

`HttpClient.Builder.version(...)` và `HttpRequest.Builder.version(...)` đặt phiên bản ưu tiên. Chúng không phải bằng chứng rằng response đã dùng đúng phiên bản đó. Luôn kiểm tra `HttpResponse.version()`.

Đối với HTTP/3, JDK không chọn HTTP/3 mặc định. Khi muốn đo HTTP/3 thuần, dùng `HTTP_3_URI_ONLY` để chỉ thử QUIC tại authority trong URI. Cách này không dùng Alternative Services và sẽ thất bại nếu server không nghe HTTP/3 tại đúng host/port. Nếu dùng `ANY`, JDK có thể thiết lập cả QUIC và TLS/TCP rồi sử dụng kết nối thành công trước; response có thể là HTTP/1.1, HTTP/2 hoặc HTTP/3.

Implementation HttpClient tích hợp trong JDK không sử dụng HTTP/3 khi proxy được chọn cho URI. Nếu cần so sánh trực tiếp HTTP/3, phải kiểm thử trên đường mạng trực tiếp được cho phép và ghi lại route đó. Không so sánh một lượt HTTP/1.1 qua proxy với một lượt HTTP/3 đi trực tiếp rồi kết luận khác biệt chỉ do giao thức.

## 4. Mã benchmark tối thiểu

Ví dụ sau chạy trên JDK 26/27. Chương trình:

- Nhận URI HTTPS, số request và concurrency từ command line.
- Tạo một HttpClient cho mỗi giao thức và tái sử dụng client.
- Đo request đầu tiên riêng, sau đó warm-up.
- Giới hạn số request đang chạy bằng Semaphore.
- Thu thập latency của các response, mã HTTP, lỗi truyền tải và phiên bản giao thức thực tế.
- Tính p50/p95/p99 và throughput.

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpOption;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.LongAdder;

public class HttpClientBenchmark {
    private static HttpRequest request(
            URI uri, HttpClient.Version preferredVersion) {

        var builder = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(10))
                .GET();

        if (preferredVersion == HttpClient.Version.HTTP_3) {
            builder.setOption(
                    HttpOption.H3_DISCOVERY,
                    HttpOption.Http3DiscoveryMode.HTTP_3_URI_ONLY
            );
        }

        return builder.build();
    }

    private static Throwable unwrap(Throwable error) {
        Throwable cause = error;
        while (cause instanceof java.util.concurrent.CompletionException
                && cause.getCause() != null) {
            cause = cause.getCause();
        }
        return cause;
    }

    private static double percentileMs(long[] sorted, double percentile) {
        if (sorted.length == 0) {
            return Double.NaN;
        }

        int index = (int) Math.ceil(percentile * sorted.length) - 1;
        index = Math.max(0, Math.min(index, sorted.length - 1));
        return sorted[index] / 1_000_000.0;
    }

    private static void measure(
            HttpClient client,
            URI uri,
            int requestCount,
            int concurrency) throws InterruptedException {

        if (requestCount <= 0 || concurrency <= 0) {
            throw new IllegalArgumentException(
                    "requestCount and concurrency must be positive"
            );
        }

        var slots = new Semaphore(concurrency);
        var responseLatencies = new ConcurrentLinkedQueue<Long>();
        var actualVersions =
                new ConcurrentHashMap<HttpClient.Version, LongAdder>();
        var failureTypes = new ConcurrentHashMap<String, LongAdder>();

        var successful = new LongAdder();
        var non2xx = new LongAdder();
        var transportFailures = new LongAdder();

        List<CompletableFuture<Void>> tasks =
                new ArrayList<>(requestCount);

        long wallStart = System.nanoTime();

        for (int i = 0; i < requestCount; i++) {
            slots.acquire();

            long requestStart = System.nanoTime();
            HttpRequest request = request(uri, client.version());

            CompletableFuture<Void> task = client
                    .sendAsync(request, HttpResponse.BodyHandlers.discarding())
                    .handle((response, error) -> {
                        try {
                            if (error != null) {
                                transportFailures.increment();
                                Throwable cause = unwrap(error);
                                String type = cause.getClass().getSimpleName();
                                failureTypes.computeIfAbsent(
                                        type, ignored -> new LongAdder()
                                ).increment();
                            } else {
                                responseLatencies.add(
                                        System.nanoTime() - requestStart
                                );

                                actualVersions.computeIfAbsent(
                                        response.version(),
                                        ignored -> new LongAdder()
                                ).increment();

                                int status = response.statusCode();
                                if (status >= 200 && status < 300) {
                                    successful.increment();
                                } else {
                                    non2xx.increment();
                                }
                            }
                        } finally {
                            slots.release();
                        }
                        return null;
                    });

            tasks.add(task);
        }

        CompletableFuture.allOf(
                tasks.toArray(CompletableFuture[]::new)
        ).join();

        double elapsedSeconds =
                (System.nanoTime() - wallStart) / 1_000_000_000.0;

        long[] sorted = responseLatencies.stream()
                .mapToLong(Long::longValue)
                .sorted()
                .toArray();

        Map<HttpClient.Version, Long> protocolCounts =
                new EnumMap<>(HttpClient.Version.class);
        actualVersions.forEach(
                (version, count) -> protocolCounts.put(version, count.sum())
        );

        long responseCount = successful.sum() + non2xx.sum();

        System.out.printf(
                Locale.ROOT,
                "%npreferred=%s attempts=%d responses=%d 2xx=%d "
                + "non2xx=%d transportFailures=%d%n"
                + "attempts/s=%.1f successful/s=%.1f "
                + "p50=%.2fms p95=%.2fms p99=%.2fms%n"
                + "actualProtocols=%s failureTypes=%s%n",
                client.version(),
                requestCount,
                responseCount,
                successful.sum(),
                non2xx.sum(),
                transportFailures.sum(),
                requestCount / elapsedSeconds,
                successful.sum() / elapsedSeconds,
                percentileMs(sorted, 0.50),
                percentileMs(sorted, 0.95),
                percentileMs(sorted, 0.99),
                protocolCounts,
                failureTypes.entrySet().stream().collect(
                        java.util.stream.Collectors.toMap(
                                Map.Entry::getKey,
                                entry -> entry.getValue().sum()
                        )
                )
        );
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            throw new IllegalArgumentException(
                    "Usage: java HttpClientBenchmark "
                    + "<https-uri> [requests] [concurrency]"
            );
        }

        URI uri = URI.create(args[0]);
        int requestCount = args.length > 1
                ? Integer.parseInt(args[1]) : 1000;
        int concurrency = args.length > 2
                ? Integer.parseInt(args[2]) : 32;

        for (HttpClient.Version version : List.of(
                HttpClient.Version.HTTP_1_1,
                HttpClient.Version.HTTP_2,
                HttpClient.Version.HTTP_3)) {

            try (HttpClient client = HttpClient.newBuilder()
                    .version(version)
                    .connectTimeout(Duration.ofSeconds(3))
                    // Direct route for a controlled HTTP/3 test.
                    // Remove this only when testing the configured proxy path.
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .build()) {

                long firstStart = System.nanoTime();
                HttpResponse<Void> first = client.send(
                        request(uri, version),
                        HttpResponse.BodyHandlers.discarding()
                );
                double firstMs =
                        (System.nanoTime() - firstStart) / 1_000_000.0;

                System.out.printf(
                        Locale.ROOT,
                        "%nfirst preferred=%s actual=%s status=%d time=%.2fms%n",
                        version, first.version(), first.statusCode(), firstMs
                );

                // Warm-up: the same client and connection pool are reused.
                for (int i = 0; i < 30; i++) {
                    client.send(
                            request(uri, version),
                            HttpResponse.BodyHandlers.discarding()
                    );
                }

                measure(client, uri, requestCount, concurrency);
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw error;
            } catch (Exception error) {
                System.err.printf(
                        "%npreferred=%s unavailable: %s: %s%n",
                        version,
                        error.getClass().getSimpleName(),
                        error.getMessage()
                );
            }
        }
    }
}
```

Biên dịch và chạy:

```text
javac HttpClientBenchmark.java
java HttpClientBenchmark https://your-controlled-origin.example/benchmark 1000 32
```

Chương trình dùng `NO_PROXY` để tạo phép đo trực tiếp có thể kiểm soát. Chỉ chạy như vậy khi chính sách mạng cho phép truy cập trực tiếp. Nếu cần đo qua proxy, bỏ cấu hình này và ghi nhận rằng lượt HTTP/3 trong HttpClient JDK không thể được dùng qua proxy.

### 4.1. Đọc kết quả benchmark

Giả sử output có dạng:

```text
preferred=HTTP_2 attempts=1000 responses=998 2xx=990 non2xx=8 transportFailures=2
attempts/s=420.0 successful/s=415.8 p50=42.10ms p95=95.40ms p99=180.20ms
actualProtocols={HTTP_2=998} failureTypes={HttpTimeoutException=2}
```

Đây chỉ là ví dụ minh họa cách đọc, không phải kết quả benchmark tham chiếu.

- `preferred` là giao thức được yêu cầu.
- `actualProtocols` cho biết response thực tế được nhận qua giao thức nào.
- `attempts/s` tính cả request có lỗi truyền tải.
- `successful/s` chỉ tính response 2xx.
- p50/p95/p99 được tính trên các response nhận được, gồm cả mã HTTP không phải 2xx; lỗi không có response được đếm riêng.
- `non2xx` là response HTTP không nằm trong khoảng 200–299. Cần đọc status cụ thể ở hệ thống quan sát server nếu muốn phân biệt 3xx, 4xx và 5xx.

Nếu `preferred=HTTP_3` nhưng `actualProtocols` có HTTP/2 hoặc HTTP/1.1, kiểm tra lại cách tạo request và discovery mode. Mã mẫu dùng `HTTP_3_URI_ONLY`, nên thông thường sẽ thất bại thay vì fallback khi không thể tạo HTTP/3. Nếu bạn đổi sang `ANY`, response có thể dùng giao thức khác và phải được báo cáo đúng theo `response.version()`.

## 5. Đọc đúng latency và throughput

### 5.1. Đo request đầu tiên riêng

Request đầu tiên có thể gồm:

- DNS resolution.
- Thiết lập TCP hoặc QUIC.
- TLS handshake hoặc QUIC/TLS handshake.
- Thương lượng ALPN và phiên bản HTTP.
- Xử lý request tại server.
- Truyền toàn bộ response body theo BodyHandler.

Đoạn mã dùng `System.nanoTime()` để đo khoảng thời gian. Đây là đồng hồ đơn điệu phù hợp để đo elapsed time; không dùng `System.currentTimeMillis()` để benchmark latency ngắn.

### 5.2. Đo steady-state

Sau warm-up, một kết nối có thể được tái sử dụng. Điều này loại bỏ phần lớn chi phí tạo kết nối khỏi nhiều request tiếp theo. Với HTTP/2 và HTTP/3, nhiều request có thể chạy đồng thời trên các stream của một kết nối. Với HTTP/1.1, client thường cần nhiều kết nối hơn để đạt cùng concurrency.

Đừng chỉ tăng concurrency cho đến khi throughput cao nhất. Khi concurrency vượt khả năng server hoặc client, hàng đợi tăng và p95/p99 thường xấu đi. Hãy chạy một dải concurrency, ví dụ 1, 4, 8, 16, 32, 64, rồi tìm điểm cân bằng giữa throughput, tail latency và error rate.

### 5.3. Đo payload lớn

Mã benchmark dùng `BodyHandlers.discarding()` để không giữ response body trong bộ nhớ. Nó phù hợp khi mục tiêu là đo thời gian hoàn tất request với một response cố định. Nếu muốn đo goodput dữ liệu, phải biết số byte đã truyền và dùng payload có kích thước xác định.

Với body lớn:

- `BodyHandlers.ofByteArray()` giữ toàn bộ body trong một mảng byte; không phù hợp với payload rất lớn nếu bộ nhớ bị giới hạn.
- `BodyHandlers.ofFile(path)` ghi body ra file.
- `BodyHandlers.ofInputStream()` cho phép đọc theo luồng; phải đóng stream bằng try-with-resources.
- BodyPublisher/BodySubscriber tùy chỉnh cho phép điều khiển luồng dữ liệu và backpressure.

Không bỏ dở response stream. Nếu dùng streaming handler, phải đọc đến hết, đóng hoặc hủy stream/subscription. Nếu không, request có thể chưa hoàn tất và tài nguyên liên quan đến kết nối/client có thể không được giải phóng đúng lúc.

## 6. Thực hành kiểm thử khi mất kết nối

Tạo một staging endpoint hoặc mock server mà nhóm kiểm thử kiểm soát. Chuẩn bị các hành vi sau và chạy từng kịch bản với HTTP/1.1, HTTP/2 và HTTP/3 nếu endpoint hỗ trợ:

| Kịch bản | Hành vi server/mạng | Quan sát ở client |
|---|---|---|
| Phản hồi bình thường | Trả 200 cùng payload cố định. | Latency, throughput, giao thức thực tế. |
| Chậm trước headers | Chờ lâu hơn request timeout rồi mới gửi headers. | `HttpTimeoutException` hoặc lỗi timeout tương ứng. |
| Chậm trong body | Gửi headers sớm, sau đó truyền body theo từng đoạn với khoảng nghỉ. | Thời gian hoàn tất body và request timeout của JDK. |
| Trả 503 | Server gửi HTTP 503 bình thường. | Nhận được HttpResponse; không coi 503 là IOException. |
| Ngắt TCP sau khi nhận request | Server đóng/reset kết nối trước khi trả response. | IOException hoặc retry kết nối theo implementation; kết quả nghiệp vụ có thể chưa rõ. |
| Chặn UDP | Firewall staging chặn UDP đến endpoint QUIC. | HTTP/3 strict có thể timeout hoặc lỗi kết nối; HTTP/1.1 và HTTP/2 qua TCP vẫn có thể hoạt động. |
| DNS không phân giải | Dùng hostname staging không tồn tại hoặc DNS test có kiểm soát. | UnknownHostException hoặc lỗi phân giải tên trong cause chain. |
| Hết hạn kết nối | Dùng địa chỉ test không phản hồi hoặc firewall drop gói SYN. | HttpConnectTimeoutException nếu timeout thiết lập kết nối hết hạn. |

Không giả định mọi tình huống mất mạng đều tạo cùng một exception. Kết quả phụ thuộc thời điểm lỗi, protocol, retry nội bộ, proxy, timeout và việc server đã nhận hoặc xử lý request hay chưa.

### 6.1. Phân biệt connect timeout và request timeout

Hai timeout giải quyết hai giai đoạn khác nhau:

| Cấu hình | Phạm vi | Khi hết hạn |
|---|---|---|
| `HttpClient.Builder.connectTimeout(Duration)` | Thời gian thiết lập một kết nối mới; implementation JDK bao gồm TLS handshake. | `HttpConnectTimeoutException`. Không có tác dụng nếu request tái sử dụng kết nối đã có. |
| `HttpRequest.Builder.timeout(Duration)` | Thời gian thực hiện request. Trong implementation JDK, bộ đếm dừng khi response body subscriber hoàn tất. | `HttpTimeoutException`. |

Ví dụ cấu hình cả hai:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://staging.example.com/slow"))
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();
```

`connectTimeout` không thay thế request timeout. Một kết nối đã được tái sử dụng có thể không cần thiết lập lại, nhưng request vẫn có thể treo khi server xử lý hoặc truyền response. Nếu không đặt request timeout, thời hạn mặc định có hiệu lực như một khoảng thời gian vô hạn.

### 6.2. Xử lý lỗi với send và sendAsync

Với `send`, lời gọi đồng bộ có thể ném `IOException` hoặc `InterruptedException`. `HttpTimeoutException` và `HttpConnectTimeoutException` thuộc nhánh `IOException`.

```java
try {
    HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString()
    );

    if (response.statusCode() >= 200
            && response.statusCode() < 300) {
        System.out.println(response.body());
    } else {
        System.err.println("HTTP status: " + response.statusCode());
    }
} catch (java.net.http.HttpConnectTimeoutException e) {
    System.err.println("Hết thời gian thiết lập kết nối: " + e.getMessage());
} catch (java.net.http.HttpTimeoutException e) {
    System.err.println("Request hết thời gian: " + e.getMessage());
} catch (java.io.IOException e) {
    System.err.println("Lỗi truyền tải: " + e.getMessage());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw e;
}
```

Với `sendAsync`, lỗi thường xuất hiện dưới dạng exceptional completion của `CompletableFuture`. Cần mở cause chain để phân loại nguyên nhân:

```java
client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .whenComplete((response, error) -> {
            if (error != null) {
                Throwable cause = error;
                while (cause.getCause() != null
                        && (cause instanceof java.util.concurrent.CompletionException
                            || cause instanceof java.util.concurrent.ExecutionException)) {
                    cause = cause.getCause();
                }

                if (cause instanceof java.net.http.HttpConnectTimeoutException) {
                    System.err.println("Connect timeout");
                } else if (cause instanceof java.net.http.HttpTimeoutException) {
                    System.err.println("Request timeout");
                } else if (cause instanceof java.io.IOException) {
                    System.err.println("I/O failure: " + cause);
                } else {
                    System.err.println("Unexpected failure: " + cause);
                }
                return;
            }

            if (response.statusCode() >= 200
                    && response.statusCode() < 300) {
                System.out.println("OK via " + response.version());
            } else {
                System.err.println("HTTP error: " + response.statusCode());
            }
        });
```

Không chỉ ghi `error.getMessage()`. Hãy ghi exception type, cause, host, method, giao thức thực tế nếu có response, timeout cấu hình và correlation ID. Không ghi access token, cookie hoặc nội dung nhạy cảm vào log.

## 7. Retry, interruption và cancellation

### 7.1. Không retry mọi lỗi giống nhau

Retry là một quyết định nghiệp vụ. Một kết nối bị ngắt sau khi client gửi POST có thể khiến client không biết server đã xử lý dữ liệu hay chưa. Nếu gửi lại POST, giao dịch có thể bị thực hiện hai lần.

| Trường hợp | Hướng xử lý |
|---|---|
| DNS hoặc connect failure trước khi request được gửi | Có thể retry có giới hạn sau khi kiểm tra nguyên nhân và deadline. |
| Timeout sau khi gửi request | Kết quả có thể chưa rõ; chỉ retry nếu thao tác an toàn hoặc có idempotency key. |
| HTTP 429 | Tôn trọng `Retry-After` nếu có, giới hạn số lần thử và tổng thời gian chờ. |
| HTTP 500, 502, 503, 504 | Có thể là lỗi tạm thời; quyết định retry dựa trên method, nghiệp vụ và chính sách server. |
| HTTP 400, 401, 403, 404 hoặc lỗi validation | Thường cần sửa request hoặc quyền truy cập, không retry mù quáng. |
| TLS certificate/hostname failure | Sửa cấu hình tin cậy hoặc chứng chỉ; không retry liên tục. |

Nếu cần retry ở tầng ứng dụng:

- Chỉ retry các thao tác idempotent hoặc các thao tác được server bảo vệ bằng idempotency key.
- Dùng exponential backoff có jitter; đặt số lần thử tối đa và deadline tổng.
- Không giữ request trong hàng đợi vô hạn.
- Tôn trọng `Retry-After` của server.
- Ghi lại attempt number, nguyên nhân retry và kết quả cuối cùng.

### 7.2. Retry nội bộ của JDK không thay thế chính sách ứng dụng

Module `java.net.http` của JDK liệt kê một số system properties của implementation tích hợp, trong đó `jdk.httpclient.disableRetryConnect` điều khiển retry kết nối và mặc định là `false`; `jdk.httpclient.enableAllMethodRetry` mặc định là `false` và điều khiển việc cho phép retry tự động các method không idempotent.

Đây là thuộc tính của implementation JDK, không phải API retry portable mà mọi implementation HttpClient đều phải hỗ trợ. Không dựa vào retry nội bộ để bảo đảm một lệnh nghiệp vụ chỉ được thực hiện một lần. Cũng không thay đổi các thuộc tính này như một cách chữa lỗi chung mà chưa kiểm thử phiên bản JDK, method và hành vi server.

### 7.3. Cancellation không bảo đảm server dừng xử lý

Với `send`, khi thread bị interrupt, implementation mặc định cố gắng hủy HTTP exchange và ném `InterruptedException`. Với `sendAsync`, ứng dụng có thể hủy future. Tuy nhiên, cancellation là best-effort: request có thể đã được gửi và server có thể đã bắt đầu xử lý. Không dùng cancellation làm bằng chứng rằng giao dịch đã bị rollback.

Khi hủy request, cần ghi nhận trạng thái nghiệp vụ là chưa xác định nếu chưa có xác nhận từ server. Với thao tác ghi dữ liệu, dùng idempotency key hoặc API tra cứu trạng thái để xác minh trước khi gửi lại.

## 8. Quan sát và chẩn đoán HttpClient

### 8.1. Ghi giao thức và thời gian ở tầng ứng dụng

Mỗi lần gọi nên ghi tối thiểu:

- Tên endpoint hoặc route đã chuẩn hóa, không ghi query chứa secret.
- HTTP method và mã trạng thái.
- `response.version()` nếu nhận được response.
- Thời gian request, timeout, số lần retry và concurrency.
- Số byte request/response nếu ứng dụng có thể đo chính xác.
- Exception type và cause khi thất bại.

Dùng `System.nanoTime()` để đo thời lượng trong tiến trình. Dùng tracing/metrics để liên kết thời gian client với thời gian xử lý ở server; chênh lệch có thể nằm ở DNS, kết nối, proxy, mạng, hàng đợi hoặc đọc body.

### 8.2. Bật log chẩn đoán có mục tiêu

Implementation JDK cung cấp logger `jdk.httpclient.HttpClient` qua Platform Logging API. Có thể bật log trong môi trường kiểm thử bằng system property:

```text
-Djdk.httpclient.HttpClient.log=errors,requests,ssl,trace,channel
```

Khi chẩn đoán HTTP/3/QUIC, JDK 27 liệt kê thêm các nhóm log `http3` và `quic`. Ví dụ:

```text
-Djdk.httpclient.HttpClient.log=errors,requests,http3,quic:control:retransmit
```

Log mức thấp có thể rất nhiều và có thể chứa thông tin request/headers tùy lựa chọn. Chỉ bật có thời hạn trong môi trường thử nghiệm; rà soát dữ liệu nhạy cảm trước khi lưu hoặc chia sẻ log.

### 8.3. Kiểm tra keep-alive

JDK 27 có các system properties cho thời gian giữ kết nối nhàn rỗi trong pool:

- `jdk.httpclient.keepalive.timeout`: mặc định 30 giây, áp dụng cho HTTP/1.1, HTTP/2 và HTTP/3.
- `jdk.httpclient.keepalive.timeout.h2`: thời gian riêng cho HTTP/2; nếu không đặt hoặc giá trị âm thì dùng giá trị chung.
- `jdk.httpclient.keepalive.timeout.h3`: thời gian riêng cho HTTP/3; nếu không đặt hoặc giá trị âm thì dùng giá trị HTTP/2.

Đây là cấu hình implementation của JDK. Thay đổi keep-alive có thể ảnh hưởng số lần bắt tay, số kết nối nhàn rỗi và tải lên server. Hãy đo với mô hình traffic thật trước khi điều chỉnh. Không đặt timeout bằng 0 với giả định rằng nó có nghĩa là giữ kết nối vô hạn; trong JDK, giá trị 0 khiến kết nối bị đóng khi trở thành idle.

## 9. Bài tập thực hành

Dùng cùng một staging endpoint và thực hiện lần lượt:

1. Chạy HTTP/1.1, HTTP/2 và HTTP/3 strict với 1.000 request, concurrency 1.
2. Lặp lại với concurrency 8, 32 và 64.
3. Chạy mỗi cấu hình ít nhất năm lượt, ghi lại p50, p95, p99, successful req/s, non-2xx, transport failures và giao thức thực tế.
4. So sánh request đầu tiên với steady-state sau warm-up.
5. Chạy lại với response body nhỏ và body lớn. Với body lớn, so sánh streaming ra file và đọc toàn bộ vào bộ nhớ.
6. Tạo endpoint chậm trước headers và endpoint truyền body chậm; kiểm tra request timeout.
7. Ngắt kết nối trong lúc request đang chạy; ghi lại exception và kiểm tra server có nhận request hay chưa.
8. Trả HTTP 503 và HTTP 429; xác minh client nhận được response và áp dụng chính sách retry đúng.
9. Chặn UDP trong staging rồi chạy HTTP/3 strict; ghi lại lỗi và xác minh HTTP/1.1/HTTP/2 qua TCP vẫn hoạt động.
10. Thử cancellation khi request đang xử lý; kiểm tra trạng thái dữ liệu phía server để chứng minh cancellation không tự động rollback nghiệp vụ.

Tạo bảng kết quả:

| Protocol được yêu cầu | Protocol thực tế | Concurrency | p50 (ms) | p95 (ms) | p99 (ms) | 2xx/s | Non-2xx | Transport failure |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| HTTP/1.1 | | 1 | | | | | | |
| HTTP/2 | | 1 | | | | | | |
| HTTP/3 | | 1 | | | | | | |
| HTTP/1.1 | | 32 | | | | | | |
| HTTP/2 | | 32 | | | | | | |
| HTTP/3 | | 32 | | | | | | |

Sau khi đo, trả lời:

- Giao thức nào có latency p50 thấp nhất? Giao thức nào có p99 ổn định nhất?
- Khi tăng concurrency, throughput tăng đến mức nào trước khi tail latency hoặc error rate tăng mạnh?
- Request đầu tiên khác steady-state ra sao? Chênh lệch có đến từ handshake hay warm-up của server/JIT không?
- Khi chặn UDP, HTTP/3 strict thất bại như thế nào? HTTP/2/HTTP/1.1 có tiếp tục hoạt động không?
- Khi server trả 503, client nhận response hay exception? Vì sao cần phân biệt hai loại lỗi?
- Khi request timeout sau khi gửi POST, có đủ thông tin để gửi lại an toàn không? Server có hỗ trợ idempotency key không?
- Kích thước response body và cách xử lý body ảnh hưởng latency, memory và goodput ra sao?

## 10. Kết luận khi chọn cấu hình

Chọn giao thức dựa trên số liệu của môi trường triển khai. HTTP/2 thường hữu ích khi nhiều request cần chia sẻ kết nối TCP; HTTP/3 có thể cải thiện hành vi trên mạng có mất gói hoặc RTT cao nhờ QUIC, nhưng phải kiểm tra khả năng UDP và server. HTTP/1.1 vẫn có thể là lựa chọn phù hợp cho endpoint, proxy hoặc hạ tầng chưa hỗ trợ giao thức mới.

Với JDK HttpClient, hãy tái sử dụng client, đặt timeout kết nối và timeout request theo ngân sách thời gian, tiêu thụ hoặc đóng response body, ghi nhận giao thức thực tế và thiết kế retry theo tính idempotent của nghiệp vụ. Không chọn giao thức chỉ từ một con số benchmark hoặc một lần chạy.

## Tài liệu tham khảo chính thức

- [JEP 517: HTTP/3 for the HTTP Client API](https://openjdk.org/jeps/517)
- [HttpClient — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.html)
- [HttpClient.Builder — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [HttpRequest.Builder — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [HttpResponse.BodyHandlers — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [HttpOption.Http3DiscoveryMode — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpOption.Http3DiscoveryMode.html)
- [java.net.http module summary and system properties — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/module-summary.html)
- [HttpTimeoutException — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpTimeoutException.html)
- [HttpConnectTimeoutException — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html)

