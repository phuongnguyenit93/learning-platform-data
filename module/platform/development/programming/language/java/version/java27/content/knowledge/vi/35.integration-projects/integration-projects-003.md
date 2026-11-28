# Tạo HTTP client tổng hợp dữ liệu bằng virtual thread và ScopedValue

## 1. Mục tiêu dự án tích hợp

Xây một ứng dụng Java 27 đọc dữ liệu từ **nhiều HTTP endpoints**, thực hiện các request đồng thời bằng **virtual threads**, giữ một **correlation ID** cho từng yêu cầu tổng hợp bằng **ScopedValue**, kiểm soát timeout/kích thước phản hồi rồi gộp các kết quả hợp lệ thành một bảng tổng.

Ví dụ nghiệp vụ: một ứng dụng quản lý tồn kho cần tổng hợp số lượng của từng sản phẩm từ hai kho. Mỗi kho cung cấp một HTTP endpoint. Ứng dụng cần đưa ra kết quả cuối cùng ngay cả khi một nguồn thứ ba đang lỗi.

Những nội dung tích hợp:

- **java.net.http.HttpClient**: gửi HTTP request, xử lý status và response body.
- **Executors.newVirtualThreadPerTaskExecutor()**: một virtual thread cho mỗi tác vụ I/O.
- **ScopedValue**: cung cấp ngữ cảnh bất biến theo phạm vi thực thi, không cần truyền qua mọi tầng gọi.
- **Future**: chờ kết quả, phân biệt thành công/thất bại và xử lý timeout.
- **Records và collections**: mô tả immutable input/result, tổng hợp bằng **Map.merge**.
- **InputStream + CharsetDecoder**: giới hạn số byte trước khi giải mã và parse dữ liệu.
- **HttpServer** của **jdk.httpserver**: server thử nghiệm chạy ở **127.0.0.1** để bài có thể chạy offline.

Bài thuộc chương **Thực hành tích hợp**, trong module **Java 27 và các kiến thức liên quan**. Chỉ sử dụng API hiện hành. **Virtual threads** là tính năng ổn định từ Java 21; **ScopedValue** là API ổn định từ Java 25. Không dùng các API legacy hoặc cần preview trong dự án chính.

## 2. Kết quả mong muốn

Ứng dụng thử nghiệm tạo ba endpoints nội bộ:

| Nguồn | HTTP status | Response body | Kết quả |
|---|---:|---|---|
| **north** | 200 | **book=12**, **pen=4** | Chấp nhận |
| **south** | 200 | **book=5**, **pen=3** | Chấp nhận |
| **unstable** | 503 | Thông báo bảo trì | Ghi nhận nguồn lỗi, không cộng vào tổng |

Tổng hợp hai nguồn thành công:

~~~text
book=17
pen=7
~~~

Mỗi outbound request gửi header **X-Request-Id: demo-253** lấy từ ScopedValue của chính task. Nếu thiếu header, mock server của bài sẽ trả lỗi để giúp nhận diện việc truyền context sai.

Chính sách xử lý lỗi của phiên bản demo là **partial success có ghi nhận nguồn lỗi**. Đây là một lựa chọn nghiệp vụ minh họa; các hệ thống như thanh toán hoặc quyết toán có thể cần **fail-fast/fail-closed**, không được tự ý bỏ qua một nguồn.

## 3. Sơ đồ kiến trúc

~~~mermaid
flowchart TD
    A["Main / request entry"] --> B["Bind ScopedValue<RequestContext>"]
    B --> C["Aggregator"]
    C --> D["ExecutorService: virtual thread / task"]
    D --> E["Task north: rebind RequestContext"]
    D --> F["Task south: rebind RequestContext"]
    D --> G["Task unstable: rebind RequestContext"]
    E --> H["HttpClient.send + bounded response"]
    F --> H
    G --> H
    H --> I["Validate HTTP status + parse text"]
    I --> J["SourceResult: success or error"]
    J --> K["Await all with deadline"]
    K --> L["Merge results + report failures"]
~~~

**Quy tắc sở hữu dữ liệu:** các task chỉ tạo kết quả riêng, không đồng thời sửa một **HashMap** dùng chung. Sau khi các Futures được thu thập, **thread tổng hợp** gộp kết quả theo một thứ tự ổn định.

**Quy tắc sở hữu vòng đời:** executor được đóng ở cuối phạm vi, HttpClient dùng chung cho các request trong một đợt tổng hợp, và mọi response InputStream phải được đóng.

## 4. Ranh giới phạm vi và các giả định

Để người học chạy hoàn toàn offline, các HTTP endpoints được tạo bằng **com.sun.net.httpserver.HttpServer**, một **JDK-specific API được tài liệu hóa trong module jdk.httpserver**. Nó phù hợp cho demo, thử nghiệm và công cụ nhỏ; **không được coi là production-ready API gateway**.

Dữ liệu của demo dùng định dạng cực nhỏ:

~~~text
product=quantity
product=quantity
~~~

Ví dụ:

~~~text
book=12
pen=4
~~~

Đây **không phải JSON**. Java SE không cung cấp một JSON parser phổ quát trong module chuẩn để sử dụng trực tiếp cho phần này. Khi tích hợp với API JSON thực, chọn một thư viện JSON được bảo trì, định nghĩa DTO/schema và cấu hình giới hạn kích thước, độ sâu, số phần tử; không dùng **split** để parse JSON.

Giới hạn của demo:

- Nguồn được **hardcode** dưới **127.0.0.1**, không nhận URL tùy ý từ người dùng.
- Tối đa 3 nguồn; dữ liệu đầu vào đơn giản, ít dòng.
- Mỗi response có giới hạn byte, request có timeout và cả đợt tổng hợp có deadline.
- Không có database, auth, TLS hoặc hệ thống metrics bên ngoài.
- Mọi thao tác mạng diễn ra trên loopback của máy chạy.

Những giới hạn này có chủ đích để tập trung vào mô hình HTTP client + virtual threads + ScopedValue; phần mở rộng production được trình bày ở cuối bài.

## 5. Virtual thread là gì và được dùng khi nào?

**Virtual thread** là một Java Thread nhẹ, được JVM quản lý để có thể phục vụ nhiều công việc chờ I/O với chi phí thấp hơn việc tạo cùng số lượng platform threads.

Ví dụ:

~~~java
Thread.startVirtualThread(() -> {
    System.out.println("Running in a virtual thread");
});
~~~

Với nhiều tác vụ cần kết quả, dùng **ExecutorService** sẽ thuận tiện hơn:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<Integer> result = executor.submit(() -> 40 + 2);
    System.out.println(result.get()); // 42
}
~~~

**Không dùng virtual threads để tăng tốc phép tính CPU-bound một cách thần kỳ.** Chúng đặc biệt hữu ích khi có nhiều tác vụ I/O chờ response. CPU vẫn chịu giới hạn của các cores và tài nguyên hệ điều hành.

**Không pool virtual threads theo kiểu giữ một nhóm cố định để tái sử dụng.** Factory **newVirtualThreadPerTaskExecutor()** tạo virtual thread mới cho mỗi task, không giới hạn sẵn số task và không tự thực hiện backpressure. Phải đặt quota/concurrency ở nơi phù hợp, đặc biệt trước API downstream có connection limit.

## 6. HttpClient: một đối tượng dùng chung cho nhiều request

Java hỗ trợ **java.net.http.HttpClient** với cách gửi đồng bộ hoặc bất đồng bộ:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

try (HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build()) {

    HttpRequest request = HttpRequest.newBuilder(
            URI.create("https://example.com/"))
        .timeout(Duration.ofSeconds(3))
        .GET()
        .build();

    // Chỉ chạy khi môi trường được phép truy cập Internet:
    // HttpResponse<String> response = client.send(
    //     request, HttpResponse.BodyHandlers.ofString()
    // );
}
~~~

**HttpClient** là đối tượng immutable sau khi build, có thể tái sử dụng cho nhiều request và quản lý connection pools. Tạo client mới cho mỗi item thường làm mất lợi ích tái sử dụng kết nối.

**send(...)** chặn thread gọi cho đến khi có response theo BodyHandler tương ứng, nhưng khi thực thi trong virtual thread có thể phù hợp với mô hình đồng thời chờ I/O.

Hai kiểu timeout khác nhau:

- **connectTimeout**: áp dụng vào quá trình thiết lập kết nối trong những tình huống mà HttpClient cần mở kết nối mới.
- **HttpRequest.Builder.timeout**: thời gian yêu cầu theo hợp đồng HttpClient; không có nghĩa remote server chắc chắn đã dừng tác vụ ngay khi client hết hạn.

Khi có redirect, đích sau redirect có thể khác host/port ban đầu. Demo chọn **Redirect.NEVER** để giữ endpoint kiểm soát được.

## 7. Vì sao chọn send thay vì sendAsync cho dự án này?

Cả **send** và **sendAsync** đều là API còn được hỗ trợ. Có hai cách xây fan-out:

| Cách | Cách phối hợp | Phù hợp khi |
|---|---|---|
| **send + virtual threads** | Mỗi virtual thread chờ kết quả riêng, Future để join | Luồng điều khiển tuần tự, dễ xử lý try/catch |
| **sendAsync + CompletableFuture** | Kết hợp các giai đoạn bất đồng bộ | Cần composition không chặn tại tầng ứng dụng |
| **StructuredTaskScope** | Structured concurrency, quản lý quan hệ cha–con | API vẫn là **preview trong Java 27** |

Vì mục tiêu là thực hành virtual threads và ScopedValue **không bật preview**, dự án chính dùng **send + virtual-thread-per-task executor**.

Không nên đặt một số request I/O đồng thời rất lớn vào một executor rồi mong network và upstream services luôn chịu tải. Virtual threads giảm chi phí thread chờ, **không tăng số connection của database hoặc quota của remote API**.

## 8. ScopedValue: context bất biến trong phạm vi thực thi

**ScopedValue<T>** giúp truyền ngữ cảnh từ phương thức gọi đến những phương thức sâu bên trong mà không phải thêm tham số ở mọi tầng.

~~~java
public class ScopedValueIntro {
    private static final ScopedValue<String> REQUEST_ID =
        ScopedValue.newInstance();

    static void operation() {
        System.out.println(REQUEST_ID.get());
    }

    public static void main(String[] args) {
        ScopedValue.where(REQUEST_ID, "req-42")
            .run(ScopedValueIntro::operation);

        System.out.println(REQUEST_ID.isBound()); // false
    }
}
~~~

Binding chỉ tồn tại trong phạm vi thực thi của **run(...)** hoặc **call(...)**. Khi phương thức kết thúc, ngay cả khi có exception, binding cũ được khôi phục.

**ScopedValue là một key**, và dữ liệu gắn với key nên là **immutable** hoặc phải được đồng bộ đúng cách nếu chia sẻ. Đây là lựa chọn phù hợp cho **request ID, tenant context đã được xác thực, thông tin trace không nhạy cảm hoặc các giá trị cấu hình chỉ đọc trong một request**.

Không sử dụng ScopedValue như một nơi lưu state mutable toàn cục. Không đưa mật khẩu, access token hoặc dữ liệu nhạy cảm vào context chỉ để tiện logging.

## 9. Rebinding và context riêng cho từng yêu cầu

Có thể bind lồng nhau:

~~~java
private static final ScopedValue<String> REQUEST_ID =
    ScopedValue.newInstance();

ScopedValue.where(REQUEST_ID, "outer").run(() -> {
    System.out.println(REQUEST_ID.get()); // outer

    ScopedValue.where(REQUEST_ID, "inner").run(() -> {
        System.out.println(REQUEST_ID.get()); // inner
    });

    System.out.println(REQUEST_ID.get()); // outer
});

System.out.println(REQUEST_ID.isBound()); // false
~~~

Nó khác **ThreadLocal.set(...)** ở chỗ binding có phạm vi lexical/dynamic rõ ràng và tự hồi phục sau lời gọi. Tuy nhiên, **mã phải có reference đến ScopedValue key** mới có thể đọc binding.

Trong dự án, một record **RequestContext(String requestId)** được tạo ở entry point và sẽ được truyền tới những task con bằng cơ chế chủ động.

## 10. Bẫy quan trọng: ExecutorService không tự kế thừa ScopedValue binding

**ScopedValue binding là per-thread**. Nếu một thread đang bound REQUEST_CONTEXT và submit một task qua **ExecutorService**, task được tạo có thể chạy ở thread khác **không có binding đó**.

Đừng viết như sau:

~~~java
// Sai nếu giả định executor tự truyền ScopedValue:
ScopedValue.where(CONTEXT, context).run(() -> {
    executor.submit(() -> {
        // CONTEXT.get() có thể ném NoSuchElementException.
        use(CONTEXT.get());
    });
});
~~~

Phương án dùng với **virtual-thread-per-task executor**:

~~~java
RequestContext captured = CONTEXT.get();

Future<Result> future = executor.submit(() ->
    ScopedValue.where(CONTEXT, captured)
        .call(() -> performRemoteCall())
);
~~~

**Phải lấy context ở thread đã có binding**, rồi **bind lại trong chính task**. Không dùng một static mutable field như **currentContext = ...** để truyền dữ liệu giữa requests: nhiều request đồng thời sẽ ghi đè lẫn nhau.

**StructuredTaskScope** có cơ chế kế thừa ScopedValue bindings cho những subtasks được tạo qua **fork**, nhưng đó là API **preview trong Java 27**. Không tự giả định mô hình inheritance ấy cũng áp dụng cho mọi executor hoặc ThreadFactory.

## 11. Mô hình dữ liệu bất biến cho tổng hợp

Ứng dụng dùng các records:

~~~java
record RequestContext(String requestId) {}

record Endpoint(String name, URI uri) {}

record SourceResult(
    String source,
    Map<String, Integer> counts,
    String errorCode
) {
    SourceResult {
        counts = Map.copyOf(counts);
    }

    boolean succeeded() {
        return errorCode == null;
    }
}
~~~

Mục đích:

- **RequestContext** lưu correlation ID, không lưu state nghiệp vụ thay đổi.
- **Endpoint** xác định một nguồn đã được ứng dụng cấu hình.
- **SourceResult** chứa bản sao không cho sửa của dữ liệu từng nguồn cùng mã lỗi ổn định.
- **Không cho task tự cập nhật tổng dùng chung**; mỗi task chỉ trả một result.

Trong file thực hành, các records được khai báo **static nested** trong class demo để có thể biên dịch bằng một tệp.

## 12. Giao thức mock và giới hạn dữ liệu

Mỗi upstream thành công trả **Content-Type: text/plain; charset=utf-8** với payload kiểu:

~~~text
book=12
pen=4
~~~

Validator yêu cầu:

- Tối đa **4.096 byte** cho mỗi response.
- Tối đa **16 dòng dữ liệu** không rỗng.
- Key theo biểu thức **[a-z][a-z0-9-]{0,15}**.
- Quantity là số thập phân không âm, không quá **100.000**.
- Không chấp nhận key trùng trong cùng nguồn.
- Phải có ít nhất một dòng dữ liệu hợp lệ.
- Byte body phải là **UTF-8 hợp lệ**, không âm thầm thay byte lỗi bằng ký tự replacement.

Đây là hợp đồng **cụ thể của demo**, không phải parser cho mọi text format hoặc giao thức CSV chuẩn.

**Nếu dữ liệu của API thật là JSON**, dùng JSON parser được duy trì và validation DTO/schema. Không cố đổi code **split("=")** của demo để phân tích JSON hay HTML.

## 13. Nhận response theo stream và giới hạn byte trước khi decode

**BodyHandlers.ofString()** thuận tiện khi response nhỏ và đáng tin; để giới hạn response byte ngay trong demo, dùng **BodyHandlers.ofInputStream()**:

~~~java
HttpResponse<InputStream> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofInputStream()
);

try (InputStream stream = response.body()) {
    byte[] bytes = stream.readNBytes(MAX_RESPONSE_BYTES + 1);

    if (bytes.length > MAX_RESPONSE_BYTES) {
        throw new IllegalArgumentException("Response too large");
    }

    // Decode và parse bytes sau bước kiểm soát byte.
}
~~~

Đọc thêm **một byte** giúp phân biệt body đúng giới hạn với body còn dữ liệu vượt giới hạn. Với một payload tối đa 4 KiB, giữ 4.097 byte trong RAM là có thể chấp nhận được.

**Vẫn cần timeout mạng và giới hạn concurrency**: một server gửi dữ liệu quá chậm có thể giữ task đang chờ, dù tổng byte nhỏ.

Response InputStream phải được **đọc hết hoặc đóng** để giải phóng tài nguyên liên quan. Không để stream mở khi response có HTTP status lỗi hoặc khi parser từ chối dữ liệu.

## 14. Không nhầm ba loại timeout

Dự án có ba thời hạn:

| Cấp | Ví dụ | Ý nghĩa |
|---|---|---|
| **connect timeout** | 2 giây | Giới hạn thiết lập kết nối theo HttpClient |
| **request timeout** | 3 giây | Giới hạn từng HTTP request |
| **aggregation deadline** | 4 giây | Toàn bộ đợt chờ kết quả từ các Futures |

**Quan trọng:** Nếu gọi **future.get(4, SECONDS)** nối tiếp trên N futures, thời gian chờ tổng cộng có thể gần **N × 4 giây**. Trong demo sẽ tính **một deadline chung** dựa trên **System.nanoTime()**, rồi mỗi lần chờ sử dụng thời lượng còn lại.

**Cancel không đồng nghĩa remote server đã rollback**. **Future.cancel(true)** yêu cầu hủy task/interrupt theo cơ chế executor; **HttpClient.send** khi bị interrupt sẽ cố hủy HTTP exchange, nhưng tác vụ phía server có thể đã xử lý một phần.

Với hoạt động có side effect như thanh toán hoặc tạo đơn, phải có idempotency key, transaction và hợp đồng retry riêng. Demo chỉ đọc (GET) dữ liệu để tổng hợp.

## 15. Chính sách partial result và lỗi

Một request trả **HTTP 503** không thể coi như dữ liệu rỗng hợp lệ. Nó được biểu diễn thành **SourceResult với errorCode khác null**.

Các mã lỗi minh họa:

| Mã | Khi nào |
|---|---|
| **http_503** | HTTP upstream trả 503 |
| **transport_error** | IOException trong HTTP request/body |
| **invalid_payload** | Dữ liệu không đúng schema, UTF-8 lỗi hoặc vượt hạn mức |
| **deadline_exceeded** | Future chưa có kết quả trong deadline chung |
| **task_failed** | Task thất bại bằng exception chưa được xử lý |
| **cancelled** | Task bị hủy |

Kết quả tổng hợp lưu **cả danh sách nguồn thành công và nguồn thất bại**. Không biến lỗi thành số 0 mà không nêu rõ, vì **không có dữ liệu khác dữ liệu có số lượng bằng 0**.

Ứng dụng thật cần quyết định rõ partial results có thể đưa vào báo cáo như thế nào: đánh dấu **incomplete**, từ chối nếu nguồn quan trọng lỗi, hoặc giữ lại snapshot gần nhất theo hợp đồng đã được phê duyệt.

## 16. Demo hoàn chỉnh: một file Java 27, chạy offline

Tạo tệp **AggregatingHttpClientDemo.java** với nội dung sau. Chương trình tự chạy ba mock upstreams trên loopback, gọi chúng đồng thời, dùng ScopedValue truyền request ID và đóng mọi tài nguyên sau khi in báo cáo.

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class AggregatingHttpClientDemo {
    private static final int MAX_BODY_BYTES = 4096;
    private static final int MAX_LINES = 16;
    private static final ScopedValue<RequestContext> CONTEXT =
        ScopedValue.newInstance();

    record RequestContext(String requestId) {}

    record Endpoint(String name, URI uri) {}

    record SourceResult(
            String source,
            Map<String, Integer> counts,
            String errorCode) {

        SourceResult {
            counts = Map.copyOf(counts);
        }

        boolean succeeded() {
            return errorCode == null;
        }

        static SourceResult failed(String source, String code) {
            return new SourceResult(source, Map.of(), code);
        }
    }

    static String decodeUtf8Strict(byte[] bytes)
            throws CharacterCodingException {

        return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
    }

    static Map<String, Integer> parseCounts(String payload) {
        Map<String, Integer> values = new TreeMap<>();
        int rows = 0;

        for (String line : payload.split("\\R", -1)) {
            if (line.isEmpty()) {
                continue;
            }

            if (++rows > MAX_LINES || line.length() > 64) {
                throw new IllegalArgumentException("Too many/long rows");
            }

            String[] pair = line.split("=", -1);

            if (pair.length != 2
                    || !pair[0].matches("[a-z][a-z0-9-]{0,15}")
                    || !pair[1].matches("(?:0|[1-9][0-9]{0,5})")) {
                throw new IllegalArgumentException("Invalid row");
            }

            int quantity = Integer.parseInt(pair[1]);

            if (quantity > 100_000
                    || values.putIfAbsent(pair[0], quantity) != null) {
                throw new IllegalArgumentException("Invalid quantity/key");
            }
        }

        if (values.isEmpty()) {
            throw new IllegalArgumentException("Empty dataset");
        }

        return Map.copyOf(values);
    }

    static SourceResult fetch(HttpClient client, Endpoint endpoint)
            throws InterruptedException {

        String requestId = CONTEXT.get().requestId();

        HttpRequest request = HttpRequest.newBuilder(endpoint.uri())
            .timeout(Duration.ofSeconds(3))
            .header("X-Request-Id", requestId)
            .GET()
            .build();

        try {
            HttpResponse<InputStream> response = client.send(
                request, HttpResponse.BodyHandlers.ofInputStream()
            );

            try (InputStream stream = response.body()) {
                if (response.statusCode() != 200) {
                    return SourceResult.failed(
                        endpoint.name(), "http_" + response.statusCode()
                    );
                }

                byte[] bytes = stream.readNBytes(MAX_BODY_BYTES + 1);

                if (bytes.length > MAX_BODY_BYTES) {
                    return SourceResult.failed(
                        endpoint.name(), "invalid_payload"
                    );
                }

                String payload = decodeUtf8Strict(bytes);
                Map<String, Integer> counts = parseCounts(payload);

                return new SourceResult(endpoint.name(), counts, null);
            }
        } catch (CharacterCodingException | IllegalArgumentException ex) {
            return SourceResult.failed(endpoint.name(), "invalid_payload");
        } catch (IOException ex) {
            return SourceResult.failed(endpoint.name(), "transport_error");
        }
    }

    static List<SourceResult> aggregate(
            HttpClient client, List<Endpoint> endpoints)
            throws InterruptedException {

        RequestContext captured = CONTEXT.get();
        List<Future<SourceResult>> futures = new ArrayList<>();

        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {

            for (Endpoint endpoint : endpoints) {
                futures.add(executor.submit(() -> {
                    return ScopedValue.where(CONTEXT, captured).call(
                        () -> fetch(client, endpoint)
                    );
                }));
            }

            // Một hạn chót chung, không cộng dồn timeout từng Future.
            long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(4);

            List<SourceResult> results = new ArrayList<>();

            for (int index = 0; index < endpoints.size(); index++) {
                Endpoint endpoint = endpoints.get(index);
                Future<SourceResult> future = futures.get(index);
                long remaining = deadline - System.nanoTime();

                try {
                    if (remaining <= 0 && !future.isDone()) {
                        throw new TimeoutException("Aggregation deadline");
                    }

                    results.add(future.get(
                        Math.max(remaining, 0L), TimeUnit.NANOSECONDS
                    ));
                } catch (TimeoutException ex) {
                    future.cancel(true);
                    results.add(SourceResult.failed(
                        endpoint.name(), "deadline_exceeded"
                    ));
                } catch (ExecutionException ex) {
                    results.add(SourceResult.failed(
                        endpoint.name(), "task_failed"
                    ));
                } catch (CancellationException ex) {
                    results.add(SourceResult.failed(
                        endpoint.name(), "cancelled"
                    ));
                }
            }

            return List.copyOf(results);
        } catch (InterruptedException ex) {
            futures.forEach(future -> future.cancel(true));
            Thread.currentThread().interrupt();
            throw ex;
        }
    }

    static Map<String, Integer> mergeSuccessful(
            List<SourceResult> results) {

        Map<String, Integer> totals = new TreeMap<>();

        for (SourceResult result : results) {
            if (!result.succeeded()) {
                continue;
            }

            result.counts().forEach(
                (key, count) ->
                    totals.merge(key, count, Math::addExact)
            );
        }

        return Collections.unmodifiableMap(totals);
    }

    static void sendMock(
            HttpExchange exchange, int status, String body)
            throws IOException {

        try (exchange) {
            String requestId =
                exchange.getRequestHeaders().getFirst("X-Request-Id");

            if (!"demo-253".equals(requestId)) {
                status = 400;
                body = "missing request context";
            }

            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8"
            );
            exchange.sendResponseHeaders(status, bytes.length);

            try (OutputStream output = exchange.getResponseBody()) {
                output.write(bytes);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0
        );

        server.createContext(
            "/north", exchange ->
                sendMock(exchange, 200, "book=12\npen=4\n")
        );

        server.createContext(
            "/south", exchange ->
                sendMock(exchange, 200, "book=5\npen=3\n")
        );

        server.createContext(
            "/unstable", exchange ->
                sendMock(exchange, 503, "maintenance")
        );

        try (ExecutorService serverExecutor =
                Executors.newVirtualThreadPerTaskExecutor()) {

            server.setExecutor(serverExecutor);
            server.start();

            int port = server.getAddress().getPort();
            String origin = "http://127.0.0.1:" + port;

            List<Endpoint> endpoints = List.of(
                new Endpoint("north", URI.create(origin + "/north")),
                new Endpoint("south", URI.create(origin + "/south")),
                new Endpoint("unstable", URI.create(origin + "/unstable"))
            );

            try (HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build()) {

                RequestContext requestContext =
                    new RequestContext("demo-253");

                List<SourceResult> results = ScopedValue
                    .where(CONTEXT, requestContext)
                    .call(() -> aggregate(client, endpoints));

                int successCount = 0;

                for (SourceResult result : results) {
                    if (result.succeeded()) {
                        successCount++;
                        System.out.println(result.source() + ": OK");
                    } else {
                        System.out.println(
                            result.source() + ": " + result.errorCode()
                        );
                    }
                }

                Map<String, Integer> totals =
                    mergeSuccessful(results);

                totals.forEach((key, value) ->
                    System.out.println(key + "=" + value)
                );

                System.out.println(
                    "successful=" + successCount
                    + " failed=" + (results.size() - successCount)
                );
            } finally {
                server.stop(0);
            }
        }
    }
}
~~~

Chương trình không phụ thuộc thư viện ngoài. Nó dùng **HttpServer** để mô phỏng upstream; ứng dụng HTTP client **vẫn** sử dụng API Java SE **java.net.http.HttpClient**.

**Lưu ý quan trọng về mã nguồn:** **ScopedValue** là API đã hoàn thiện trong Java 27, nên không cần **--enable-preview** cho ví dụ này. **StructuredTaskScope** không được import hoặc sử dụng.

## 17. Biên dịch và chạy trên JDK 27

Từ thư mục chứa **AggregatingHttpClientDemo.java**:

~~~bash
javac --add-modules jdk.httpserver AggregatingHttpClientDemo.java
java --add-modules jdk.httpserver AggregatingHttpClientDemo
~~~

Nếu chạy trong module JPMS có tên, module descriptor sẽ cần:

~~~java
module demo.aggregation {
    requires java.net.http;
    requires jdk.httpserver;
}
~~~

Code của class demo khi đó phải đặt vào package và cấu trúc module tương ứng; hai lệnh ngắn phía trên dành cho **một file classpath demo**, không phải named-module project.

Kết quả mong đợi:

~~~text
north: OK
south: OK
unstable: http_503
book=17
pen=7
successful=2 failed=1
~~~

**Thứ tự hiển thị được cố ý giữ theo danh sách endpoints**, không phải thứ tự các response hoàn tất. Port được hệ điều hành tự chọn từ port 0 và không cần biết trước. Dù không kết nối Internet, chương trình vẫn thực hiện các HTTP requests thật qua loopback.

## 18. Mổ xẻ luồng chạy của demo

1. **Main** tạo HttpServer trên **127.0.0.1:0** và đăng ký ba đường dẫn.
2. Server mở listener, hệ điều hành cấp một port khả dụng.
3. Main tạo một HttpClient dùng chung với connect timeout và không follow redirect.
4. Main bind **CONTEXT** với **RequestContext("demo-253")** trong **ScopedValue.where(...).call(...)**.
5. **aggregate** đọc context đã bind, tạo virtual-thread-per-task executor.
6. Mỗi task chạy **ScopedValue.where(CONTEXT, captured).call(...)** để tự bind context.
7. **fetch** lấy request ID từ ScopedValue, thêm vào HTTP header rồi gửi request.
8. Mock server kiểm tra header; không có context thì trả HTTP 400.
9. Client đọc body có giới hạn, kiểm tra status, giải mã UTF-8 và parse số liệu.
10. **aggregate** chờ các Futures trong cùng deadline, trả SourceResult của từng nguồn.
11. **mergeSuccessful** cộng số lượng của các nguồn thành công theo key.
12. Các **try-with-resources** và finally đóng request bodies, HttpClient, executor và HttpServer.

~~~mermaid
sequenceDiagram
    participant M as Main
    participant A as Aggregator
    participant V1 as Virtual thread north
    participant V2 as Virtual thread south
    participant V3 as Virtual thread unstable
    participant S as Mock HTTP server
    M->>A: ScopedValue bound; aggregate()
    A->>V1: submit + rebind
    A->>V2: submit + rebind
    A->>V3: submit + rebind
    par Requests đồng thời
        V1->>S: GET /north + X-Request-Id
        V2->>S: GET /south + X-Request-Id
        V3->>S: GET /unstable + X-Request-Id
    end
    S-->>V1: 200 + counts
    S-->>V2: 200 + counts
    S-->>V3: 503
    V1-->>A: SourceResult OK
    V2-->>A: SourceResult OK
    V3-->>A: SourceResult failed
    A-->>M: Results in endpoint order
    M->>M: Merge only successful counts
~~~

## 19. Tại sao không dùng một Map mutable chung?

Một cách thiết kế dễ gặp lỗi:

~~~java
// Anti-pattern: Map thường không được đồng bộ.
Map<String, Integer> totals = new HashMap<>();

// Nhiều tasks cùng thực hiện:
totals.merge("book", quantity, Integer::sum);
~~~

**HashMap** không hỗ trợ concurrent writes an toàn. Dù đổi sang **ConcurrentHashMap**, bài toán còn có thứ tự merge, khả năng thất bại giữa chừng, kiểm tra overflow và thống nhất snapshot khi trả response.

Demo chọn cách đơn giản hơn:

- Task chỉ đọc cấu hình và ghi dữ liệu **cục bộ của nó**.
- Mỗi task trả về một **SourceResult bất biến**.
- Thread tổng hợp gộp **sau khi thu kết quả**, bằng **TreeMap** để có thứ tự xuất ổn định.
- **Math.addExact** phát hiện tràn số thay vì im lặng wraparound.

Nếu giá trị tổng có thể vượt int, hãy thiết kế sang **long** hoặc **BigInteger** theo hợp đồng dữ liệu; không bỏ kiểm tra overflow vì nghĩ số thực tế sẽ luôn nhỏ.

## 20. Dữ liệu context có phải luôn được kế thừa?

Không. **ScopedValue có hai mô hình khác nhau cần nhớ**:

| Cơ chế | ScopedValue binding sang task mới |
|---|---|
| Gọi phương thức bình thường trong cùng thread | Có, trong phạm vi bind |
| Bind lồng nhau cùng thread | Có, binding trong cùng lớp scope ưu tiên |
| **ExecutorService.submit(...)** | **Không tự động** kế thừa |
| **Thread.startVirtualThread(...)** thông thường | **Không tự động** kế thừa từ caller |
| **StructuredTaskScope.fork(...)** | Có, theo cơ chế kế thừa scoped bindings có cấu trúc (**preview API Java 27**) |
| Task rebind bằng **ScopedValue.where(...).call(...)** | Có, trong thời gian thực thi task |

Đây là khác biệt rất quan trọng với những hệ thống nhiều tác vụ không có quan hệ cha–con rõ ràng. Việc dùng virtual thread **không** tự động làm context từ thread đang submit hiện diện trong task.

**Không dùng ThreadLocal làm bản sao ngầm của ScopedValue**. Nếu cần mang context qua executor, hãy capture một record immutable rồi bind lại có kiểm soát.

## 21. ScopedValue không phải bằng chứng xác thực hay quyền truy cập

Header **X-Request-Id** của ví dụ chỉ dùng để **liên hệ log/các thao tác cùng một request**, không đại diện cho principal đã được xác thực. Client bên ngoài có thể giả mạo header nếu server tin nó vô điều kiện.

Trong một gateway/API thực tế:

1. Xác thực request ở ingress bằng cơ chế phù hợp.
2. Xác định principal/tenant **từ kết quả xác thực phía server**, không từ body hay một header tùy ý.
3. Tạo một context bất biến chứa thông tin **thực sự cần chia sẻ**.
4. Bind context trong phạm vi xử lý request và, khi dùng ExecutorService, rebind trong từng task.
5. Ở outbound HTTP, chỉ chuyển những metadata được phép đến dependency; không tự đưa toàn bộ context hoặc token sang mọi nguồn.
6. Thực thi authorization ở tầng truy cập dữ liệu; **ScopedValue không thay thế kiểm tra quyền**.

Ví dụ về một context được tạo từ nguồn đáng tin cậy, dùng trong thiết kế lớn hơn:

~~~java
record RequestContext(
    String requestId,
    String tenantId
) {}

// authenticatedTenantId phải lấy từ cơ chế xác thực server,
// không lấy trực tiếp từ request parameter.
~~~

**Không lưu object mutable chứa session hoặc dữ liệu nhạy cảm vào ScopedValue rồi để nhiều task thay đổi nó đồng thời**. Dùng immutable records hoặc thiết kế đồng bộ có kiểm soát khi thật sự phải chia sẻ mutable state.

## 22. Hạn mức đồng thời và backpressure

**newVirtualThreadPerTaskExecutor** không phải một semaphore hoặc một thread pool giới hạn sẵn lượng I/O. Tạo nhiều virtual threads rẻ hơn platform threads, nhưng downstream vẫn bị giới hạn bởi connections, CPU, memory, rate limit và số request có thể xử lý.

Một hệ thống nhận đầu vào **hàng nghìn endpoints** mà tạo task cho tất cả ngay lập tức có thể khiến:

- Quá nhiều kết nối TCP/TLS.
- Vượt hạn mức API của đối tác.
- Tăng bộ nhớ và số lượng response streams.
- Thời gian queue hoặc retry chồng chất.
- Xuất hiện nghẽn tại DNS, proxy, file descriptors hoặc downstream service.

Ví dụ dùng **Semaphore** để hạn chế số HTTP calls đang chạy:

~~~java
import java.util.concurrent.Semaphore;

Semaphore outboundPermits = new Semaphore(8);

// Bên trong callable của mỗi virtual thread:
outboundPermits.acquire();

try {
    // Gọi fetch(client, endpoint) ở đây.
    // Chỉ tối đa 8 task được vào phần gọi HTTP đồng thời.
} finally {
    outboundPermits.release();
}
~~~

Đây là snippet minh họa vị trí kiểm soát. Trong ứng dụng thật, **Semaphore cần được chia sẻ ở phạm vi phù hợp** (ví dụ mỗi upstream/tenant hoặc toàn service), thay vì tạo semaphore mới trong mỗi request rồi tưởng đã giới hạn tổng số connections.

Semaphore chặn **số tác vụ đang ở vùng gọi HTTP**, nhưng không tự giới hạn số task đã submit. Cần giới hạn thêm **số endpoint cho mỗi batch, số request đang chờ và tổng concurrency ingress**.

## 23. Deadline chung trong demo là best effort, không phải hard real-time

Đoạn code:

~~~java
long deadline = System.nanoTime()
    + TimeUnit.SECONDS.toNanos(4);
~~~

và:

~~~java
long remaining = deadline - System.nanoTime();
future.get(Math.max(remaining, 0L), TimeUnit.NANOSECONDS);
~~~

giúp **không nhân timeout riêng lẻ lên số nguồn** khi chờ Futures. **System.nanoTime()** phù hợp để đo khoảng thời gian đã trôi qua, khác với **Instant.now()** vốn dùng thời gian đồng hồ thực.

Nhưng phải hiểu các giới hạn:

- Deadline được tính **sau khi submit các tác vụ**, do đó không bao gồm phần thời gian trước khi bắt đầu tính deadline.
- **Future.cancel(true)** là yêu cầu ngắt/hủy, không bảo đảm mọi tác vụ dừng ngay.
- **ExecutorService.close()** đợi các tác vụ hoàn tất theo hợp đồng của executor; nếu task không hợp tác dừng, toàn bộ method vẫn có thể kéo dài quá bốn giây.
- Với **BodyHandlers.ofInputStream**, **HttpClient.send** có thể hoàn tất khi headers đã đến, rồi **InputStream.readNBytes** tiếp tục chờ body. Không được coi **HttpRequest.timeout** là hard deadline bảo đảm toàn bộ quá trình xử lý stream đã hoàn tất trong mọi hoàn cảnh.
- Khi response body được đọc theo stream, cần phương án hủy/đóng stream và watchdog nếu hệ thống yêu cầu SLA nghiêm ngặt.

**Vì vậy số 4 giây trong bài là deadline của pha chờ kết quả bằng Future, không phải chứng minh kết thúc request theo thời gian thực cứng.** Trong production, cần thiết kế **end-to-end request budget, cancellation, network read/idle timeout và resource cleanup** phù hợp với HTTP client, proxy và server framework đang dùng.

## 24. Xử lý InterruptedException đúng cách

**InterruptedException** biểu thị yêu cầu ngắt một thread đang chờ; không nên nuốt lỗi rồi tiếp tục chờ vô hạn.

Trong một hàm cho phép ném lại:

~~~java
try {
    return future.get();
} catch (InterruptedException interrupted) {
    future.cancel(true);
    Thread.currentThread().interrupt();
    throw interrupted;
}
~~~

**Không viết**:

~~~java
try {
    return future.get();
} catch (InterruptedException ignored) {
    return fallback; // Nuốt tín hiệu ngắt, có thể làm shutdown khó khăn.
}
~~~

Nếu caller đã khai báo **throws InterruptedException**, có thể để nó truyền đi và quản lý cleanup tại boundary. Việc gọi **Thread.currentThread().interrupt()** khi bắt và ném lại là cách bảo toàn tín hiệu cho caller, nhưng cần hiểu semantics của thư viện đang dùng.

**Ngắt thread không giống rollback giao dịch ở server khác.** Với POST/PUT có side effect, cancellation có thể đến sau khi phía server đã ghi thành công. Cần idempotency token và hợp đồng xác nhận trạng thái.

## 25. HTTP 200 không đủ chứng minh dữ liệu dùng được

Trong demo, chỉ nhận HTTP status 200 nhưng còn kiểm tra:

- Có đọc được response body không?
- Body có vượt **4.096 bytes** không?
- UTF-8 có hợp lệ không?
- Nội dung có đúng grammar của demo không?
- Số dòng, độ dài key, quantity và khóa trùng có vi phạm không?
- Khi tổng hợp, phép cộng có vượt miền số không?

~~~text
HTTP 200
   ↓
Body bounded?
   ↓
UTF-8 valid?
   ↓
Schema/grammar valid?
   ↓
Business constraints valid?
   ↓
SourceResult.success
~~~

Một nguồn trả status 200 cùng dữ liệu bị hỏng phải được coi là **invalid_payload**, không được lặng lẽ trả tổng 0. Ngược lại, một nguồn HTTP 503 phải được biểu diễn như lỗi của nguồn đó chứ không phải tập dữ liệu trống.

Nếu sản phẩm cho phép empty dataset hợp lệ, hãy **đổi hợp đồng parser** để phân biệt tình huống không có mặt hàng với tình huống response không chứa dữ liệu do lỗi.

## 26. Giới hạn response theo cả bytes, rows và giá trị số

Mỗi loại hạn mức bảo vệ một rủi ro:

| Giới hạn | Mục đích |
|---|---|
| **MAX_BODY_BYTES = 4096** | Chặn response body lớn gây áp lực RAM |
| **MAX_LINES = 16** | Giới hạn số records cần parse |
| **line.length() <= 64** | Chặn một record quá dài |
| **key length <= 16** | Đảm bảo mã sản phẩm theo hợp đồng |
| **quantity <= 100000** | Bảo vệ miền nghiệp vụ |
| **Math.addExact** | Phát hiện tràn khi gộp nhiều nguồn |
| **request timeout/deadline** | Giảm thời gian chờ, không thay hard I/O cap |
| **concurrency/rate limit** | Bảo vệ tài nguyên ngoài kích thước payload |

Giới hạn byte **không** tự bảo vệ dữ liệu giải nén nở lớn. Nếu dùng gzip, ZIP hoặc parser JSON, cần thêm giới hạn kích thước sau giải nén, nesting depth, số phần tử và CPU/time budget.

Với API dùng JSON, số object properties, độ sâu array và khả năng tự tham chiếu trong object mapper đều cần chính sách; không chỉ dựa vào **Content-Length** từ HTTP header.

## 27. Khi chuyển sang HTTPS và API thật

Demo dùng **http://127.0.0.1** vì chỉ chạy trên loopback. Trong production, các upstream thường phải sử dụng **HTTPS** với kiểm tra chứng chỉ và hostname hợp lệ.

Ví dụ một endpoint cấu hình sẵn:

~~~java
URI endpoint = URI.create(
    "https://inventory-api.example.com/v1/stock"
);

HttpRequest request = HttpRequest.newBuilder(endpoint)
    .timeout(Duration.ofSeconds(5))
    .header("Accept", "application/json")
    .GET()
    .build();
~~~

**inventory-api.example.com** ở đây chỉ mang tính minh họa, không phải dịch vụ cần truy cập. Khi tích hợp thật:

- Không tắt TLS certificate/hostname validation để giải quyết lỗi cấu hình.
- Không đưa access token vào query string hoặc log nguyên header xác thực.
- Chỉ gửi token tới đúng upstream được ủy quyền.
- Kiểm tra request/response schema, giới hạn body, rate limit và retry.
- Dùng HttpClient tái sử dụng theo lifecycle ứng dụng thay vì tạo mới mỗi request.
- Tách cấu hình timeout/host/port khỏi mã nghiệp vụ theo chính sách deployment.

**HTTP success không đồng nghĩa dữ liệu cuối cùng đầy đủ hoặc nhất quán giữa các hệ thống**. Nếu số tồn kho thay đổi liên tục, kết quả lấy từ hai kho có thể ở hai thời điểm khác nhau; nên bổ sung snapshot version/timestamp hoặc hợp đồng đồng bộ nếu nghiệp vụ yêu cầu.

## 28. Chống SSRF khi endpoints có thể bị điều khiển

Nếu mở rộng ứng dụng để nhận URI từ người dùng, nó có thể trở thành **SSRF proxy** và bị dùng để truy cập mạng nội bộ, metadata services hoặc những đích không được phép.

Phòng vệ cần kết hợp:

1. **Allowlist host và scheme** (thường chỉ HTTPS và upstreams được quản trị cấu hình).
2. Chỉ cho phép những **port** cần thiết.
3. Không tự động đi theo redirect tới host khác nếu chưa kiểm tra lại toàn bộ chính sách.
4. Xét tất cả địa chỉ **IPv4/IPv6** mà hostname có thể phân giải.
5. Kiểm soát **DNS rebinding/TOCTOU** giữa bước kiểm tra hostname và bước kết nối thực sự.
6. Dùng **egress gateway/proxy** hoặc transport thực thi IP destination policy khi cần độ an toàn cao.
7. Đặt timeout, concurrency, size limit và quota ở nhiều tầng.
8. Giữ TLS trust/hostname verification đúng chuẩn.

**Chỉ parse URI hoặc gọi InetAddress.getAllByName một lần không tạo ra bộ lọc SSRF hoàn chỉnh.** DNS có thể thay đổi trước khi kết nối, và proxy có thể tự resolve ở nơi khác.

Trong demo, endpoints được xây **chỉ từ localhost do code sở hữu**, vì vậy không có thao tác lấy URI tùy ý từ user.

## 29. Retry: chỉ khi có chính sách rõ

Một nguồn HTTP 503 có thể phục hồi nếu thử lại sau khoảng ngắn, nhưng retry sai cách sẽ làm tăng tải lên chính hệ thống đang gặp sự cố.

Các quy tắc:

- Chỉ retry khi lỗi **có khả năng tạm thời** và operation **idempotent** hoặc có idempotency guarantee.
- Đặt **số lần retry tối đa**, tổng thời gian và **jittered backoff**.
- Không retry vô hạn khi DNS, TLS, authorization hoặc schema liên tục sai.
- Tôn trọng response headers như **Retry-After** khi hợp đồng API yêu cầu.
- Mọi retry phải dùng chung **end-to-end deadline**, không tự tạo ngân sách mới vô hạn.
- Ghi metrics các lần retry để thấy lỗi thực sự của upstream.
- Cẩn trọng với retry kết hợp ở nhiều tầng (client, service mesh, load balancer).

~~~text
Fan-out 3 nguồn
  ↓
1 nguồn lỗi 503
  ↓
Retry có điều kiện, tối đa số lần định trước
  ↓
Vẫn phải nằm trong request budget
  ↓
Nguồn thành công hoặc lỗi được ghi rõ
~~~

**Demo cố ý không retry**: output phải ổn định và minh họa partial results. Khi thêm retry, cần kiểm thử cả trường hợp dịch vụ phục hồi, lỗi kéo dài và timeout giữa những lần backoff.

## 30. Partial success, nhất quán dữ liệu và chính sách sản phẩm

Có nhiều cách trả lời khi một upstream lỗi:

| Chiến lược | Hành vi | Khi có thể phù hợp |
|---|---|---|
| **All-or-nothing** | Một nguồn lỗi khiến toàn bộ tổng hợp thất bại | Quyết toán, thao tác đòi dữ liệu đầy đủ |
| **Partial results + status** | Trả dữ liệu từ nguồn thành công, kèm danh sách lỗi | Dashboard, tra cứu không quyết định giao dịch |
| **Fallback từ cache** | Dùng snapshot gần nhất và đánh dấu stale | Chỉ khi có SLA/TTL rõ |
| **Quorum** | Chấp nhận khi đủ số nguồn đồng thuận | Hệ thống có hợp đồng quorum |
| **Hedged requests** | Gửi thêm request nếu quá chậm | Chỉ khi đo lợi ích và kiểm soát tải |

Demo thuộc chiến lược thứ hai. Vì vậy, **successful=2 failed=1** là một phần thiết yếu của kết quả; **book=17** không có nghĩa số tồn kho tổng toàn hệ thống chắc chắn là 17.

Nếu xuất kết quả thành JSON API, nên có schema rõ như:

~~~json
{
  "complete": false,
  "totals": {
    "book": 17,
    "pen": 7
  },
  "sources": [
    {"source": "north", "status": "ok"},
    {"source": "south", "status": "ok"},
    {"source": "unstable", "status": "http_503"}
  ]
}
~~~

Payload JSON trên chỉ mô tả hợp đồng đề xuất; ứng dụng demo đang in ra console, chưa serialize JSON.

## 31. Quan sát độ trễ bằng System.nanoTime

Đo thời lượng một thao tác bằng đồng hồ đơn điệu:

~~~java
long started = System.nanoTime();

try {
    // Call aggregator hoặc fetch trong phạm vi muốn đo.
} finally {
    long elapsedNanos = System.nanoTime() - started;
    System.out.println(
        "elapsedMs=" + TimeUnit.NANOSECONDS.toMillis(elapsedNanos)
    );
}
~~~

**System.nanoTime** thích hợp để đo duration, **không** biểu diễn timestamp tuyệt đối. Khi cần thời gian log thực, dùng **Instant.now()** hoặc đồng hồ ứng dụng được cấu hình.

Các chỉ số gợi ý:

- Tổng số sources/request.
- Success/failed sources.
- Thời gian tổng hợp p50/p95/p99.
- Thời gian HTTP từng upstream.
- Số task đang chờ, active outbound requests.
- Tỷ lệ timeout/cancellation, số lần retry.
- Kích thước response theo upstream.
- Tỷ lệ invalid payload hoặc schema mismatch.

Không dùng raw **request ID** làm metric label/cardinality cao. Request ID thích hợp hơn cho structured logs/traces với chính sách quyền truy cập và retention.

## 32. Khác biệt wall-clock latency và CPU time

Virtual threads đặc biệt hữu ích cho tác vụ chờ I/O. Một task có thể tồn tại 300 ms nhưng chỉ sử dụng vài ms CPU.

~~~text
Virtual thread lifetime:
[CPU]----[network waiting]----[CPU]
          ^ phần lớn wall-clock time

CPU time ≠ elapsed latency
~~~

Khi điều tra:

- CPU cao → xem parsing, transformations, hot methods hoặc garbage collection.
- CPU thấp nhưng request chậm → xem I/O waiting, connection pool, DNS, TLS, upstream latency hoặc lock contention.
- Nhiều virtual threads → không tự là lỗi; phải xem **memory, sockets, downstream limits và backlog**.
- Nhiều platform threads bị chặn → có thể là dấu hiệu kiến trúc cần thay đổi, nhưng không mặc định mọi blocking là xấu.

Có thể dùng **JDK Flight Recorder** và **Java Mission Control** để kiểm tra HTTP, allocation, thread blocking và runtime events trong JVM; kết hợp với tracing và metrics phía upstream.

## 33. Không dựa vào lời khuyên lỗi thời về pinning

Virtual thread có các hành vi scheduling và blocking đã được cải tiến qua nhiều JDK. **Từ JDK 24, JEP 491 thay đổi cách virtual threads tương tác với monitor synchronization**, giảm những tình huống pinning từng xuất hiện với **synchronized**.

Vì vậy, không nên dạy rằng "**mọi lần virtual thread đi vào synchronized sẽ pin carrier thread**" như một quy tắc chung cho Java 27.

Tuy nhiên, vẫn cần kiểm tra:

- Blocking operations có tương thích virtual threads hay không.
- Native/foreign calls hoặc những trường hợp runtime đặc biệt còn gây pinning/blocking.
- CPU-bound workload có đang tiêu thụ carrier threads không.
- Thread-per-task có tạo tải downstream vượt quota không.

Tối ưu dựa trên **profiling/JFR và kết quả thực tế** thay vì tự đổi mọi synchronized block thành ReentrantLock không có dữ liệu đo.

## 34. Structured concurrency: hướng nâng cấp, nhưng vẫn là preview trong Java 27

Java 27 có **StructuredTaskScope** trong **java.util.concurrent**, nhưng API này vẫn mang nhãn **preview**, cần **--enable-preview** và có thể thay đổi trong các bản phát hành sau.

Ý tưởng:

~~~text
Parent task
  ├── child: north
  ├── child: south
  └── child: unstable

Parent chỉ hoàn tất khi subtasks được quản lý theo scope.
ScopedValue bindings có thể được kế thừa bởi scope.fork().
~~~

**Điểm mạnh theo mô hình cấu trúc:**

- Nhiệm vụ con gắn với vòng đời của scope.
- Cancellation và deadline có chính sách rõ theo joiner/configuration.
- ScopedValue binding được truyền cho subtasks do scope tạo.
- Giảm những task “mồ côi” chạy sau khi parent đã hoàn thành.

**Vì sao demo chính không dùng StructuredTaskScope?** Bài cần một chương trình Java 27 **không phụ thuộc preview**, nên sử dụng ExecutorService và truyền context tường minh. Khi dự án quyết định bật preview theo chính sách sản phẩm, có thể viết lại phần fan-out bằng StructuredTaskScope theo **Javadoc đúng phiên bản JDK đang sử dụng**, không sao chép chữ ký từ các preview cũ vì API đã thay đổi qua các lần preview.

Không nhầm **ScopedValue ổn định** với **StructuredTaskScope preview**: chúng là hai API có trạng thái phát hành khác nhau.

## 35. Kiểm thử đơn vị phần parser và aggregator

Mã parser của demo là một điểm tốt để bắt đầu test không cần mạng.

Một số ca định hướng:

| Input | Kết quả |
|---|---|
| **book=12\\npen=4\\n** (xuống dòng thực) | Hai bản ghi |
| **book=0** | Chấp nhận số 0 |
| **book=100000** | Giá trị tối đa hợp lệ |
| **book=100001** | Từ chối |
| **book=-1** | Từ chối |
| **book=1\\nbook=2** | Từ chối key trùng |
| **book=999999999999** | Từ chối format/độ dài |
| **product with spaces=1** | Từ chối key |
| **payload rỗng** | Từ chối |
| **17 dòng** | Từ chối |
| **UTF-8 malformed bytes** | Decoder ném lỗi |

Ví dụ JUnit Jupiter với class parser từ demo:

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class AggregatingHttpClientDemoTest {
    @Test
    void parsesCounts() {
        var counts = AggregatingHttpClientDemo.parseCounts(
            "book=12\npen=4\n"
        );

        assertEquals(12, counts.get("book"));
        assertEquals(4, counts.get("pen"));
    }

    @Test
    void duplicateKeysAreRejected() {
        assertThrows(
            IllegalArgumentException.class,
            () -> AggregatingHttpClientDemo.parseCounts(
                "book=1\nbook=2\n"
            )
        );
    }

    @Test
    void emptyPayloadIsRejected() {
        assertThrows(
            IllegalArgumentException.class,
            () -> AggregatingHttpClientDemo.parseCounts("")
        );
    }
}
~~~

Test này là đoạn ví dụ bổ sung, cần dự án đã khai báo JUnit Jupiter tương thích. **Không chạy nó trong bước tạo tài liệu** và không đặt nó lẫn vào file demo chính.

Đối với số liệu nhiều nguồn, kiểm tra thêm **mergeSuccessful**, lỗi upstream không bị gộp và overflow bị phát hiện thay vì wraparound.

## 36. Kiểm thử tích hợp bằng mock server có kiểm soát

Các tình huống cần mở rộng mock HttpServer:

1. **200 + body hợp lệ**: aggregate đúng.
2. **503 hoặc 429**: lưu errorCode, không cộng dữ liệu lỗi.
3. **200 + body rỗng**: invalid_payload theo hợp đồng.
4. **200 + UTF-8 malformed**: invalid_payload.
5. **200 + hơn 4.096 bytes**: từ chối response quá lớn.
6. **200 + nhiều hơn 16 dòng**: từ chối.
7. **200 + khóa trùng**: từ chối.
8. **Server không trả headers đúng hạn**: request timeout.
9. **Server trả headers rồi body gửi rất chậm**: kiểm tra giới hạn read-body và hành vi cancellation.
10. **Redirect sang host khác**: với Redirect.NEVER, không đi theo.
11. **Nhiều requests đồng thời với request IDs khác nhau**: không lẫn context.
12. **Upstream trả dữ liệu làm tổng overflow**: hệ thống báo lỗi aggregate theo policy, không cho kết quả sai.

**Lưu ý về test timeout:** Không viết kiểm thử chỉ dựa trên **Thread.sleep(5)** rồi yêu cầu ranh giới thời gian chính xác trong mọi CI. Dùng latch/barrier, timeout đủ an toàn và một mock server có thể điều khiển lúc gửi headers/body để tái hiện các trạng thái.

Nếu test chạy dưới quyền CI bị hạn chế không cho bind loopback socket, phần tích hợp phải chạy trong môi trường được cấp quyền thích hợp; unit test parser vẫn có thể chạy offline mà không mở socket.

## 37. Cách kiểm tra ScopedValue có bị lẫn giữa các requests không

Tạo hai requests với hai IDs và chạy song song:

~~~text
Request A: req-A
  ├── source north  → X-Request-Id: req-A
  └── source south  → X-Request-Id: req-A

Request B: req-B
  ├── source north  → X-Request-Id: req-B
  └── source south  → X-Request-Id: req-B
~~~

Mock server cho test nên chấp nhận/echo header theo từng request thay vì hardcode **demo-253** như ví dụ chạy một lần, rồi kiểm tra:

- Mọi task thuộc A gửi **req-A**.
- Mọi task thuộc B gửi **req-B**.
- Không task nào của A nhận context B.
- Sau khi mỗi **ScopedValue.where(...).call(...)** hoàn tất, binding ở thread ngoài phạm vi được khôi phục.
- Nếu task quên bind, việc gọi **CONTEXT.get()** phải báo lỗi rõ thay vì silently dùng context của request trước.

Mô hình này quan trọng khi application server xử lý nhiều clients đồng thời. Một shared static String **CURRENT_REQUEST_ID** là cách sai vì nó có thể bị ghi đè.

## 38. Tài nguyên và shutdown khi request bị hủy

Những tài nguyên cần quản lý rõ:

| Tài nguyên | Vòng đời |
|---|---|
| **HttpServer** mock | start trước requests, stop trong finally |
| **ExecutorService** phục vụ server | đóng sau khi server dừng |
| **ExecutorService** phục vụ fan-out | đóng sau khi đã thu/hủy các Futures |
| **HttpClient** | tạo ở tầng ứng dụng hoặc demo, đóng khi shutdown |
| **Response InputStream** | đóng sau khi xử lý status/body dù thành công hay lỗi |
| **RequestContext** | chỉ còn tham chiếu trong phạm vi xử lý và task đang dùng |
| **Response bytes** | giới hạn kích thước, không giữ vô hạn |
| **Metrics/log** | giới hạn kích thước và loại dữ liệu được ghi |

**Trong một ứng dụng production**, không tạo/đóng HttpClient và executor ở từng request nếu lifecycle toàn service có thể quản lý chúng hiệu quả hơn. Demo dùng try-with-resources để minh họa vòng đời rõ và tránh để thread/process tiếp tục chạy sau khi chương trình kết thúc.

Nhớ rằng một task bị cancel chưa chắc đã giải phóng mọi tài nguyên ngay nếu code không hợp tác. Production cần **cancellation discipline, resource limits và monitoring**.

## 39. Lộ trình nâng cấp từ demo thành dịch vụ thực tế

Một phương án tổ chức code theo package:

~~~text
integration-service/
├── api/
│   ├── AggregationController.java
│   └── AggregationResponse.java
├── context/
│   └── RequestContext.java
├── upstream/
│   ├── UpstreamClient.java
│   ├── UpstreamEndpoint.java
│   └── UpstreamPolicy.java
├── aggregation/
│   ├── Aggregator.java
│   └── AggregateResult.java
├── observability/
│   └── MetricsAndTracing.java
└── test/
    ├── ParserContractTest.java
    ├── HttpClientIntegrationTest.java
    ├── ScopedValueIsolationTest.java
    └── TimeoutAndCancellationTest.java
~~~

Đây là **cấu trúc gợi ý**, không phải những file đã được tạo trong workspace.

Các bước:

1. Định nghĩa DTO/schema của upstream bằng parser chính thống (ví dụ JSON).
2. Cấu hình endpoints trong một danh sách do server sở hữu và có validation.
3. Tạo HttpClient dùng chung, cấu hình TLS/proxy/timeouts.
4. Chia request input validation khỏi authorization.
5. Bind ScopedValue context ở request entry, rebind ở task boundary.
6. Đặt giới hạn số upstream, concurrency, response size và rate limit.
7. Định nghĩa rõ retry, circuit breaking, partial results và fallback.
8. Thêm metrics/traces/correlation ID không lộ dữ liệu bí mật.
9. Kiểm thử tải, timeout, cancellation, malformed responses và source outages.
10. Đóng tài nguyên khi application shutdown và có runbook khi upstream chậm.

Một mô hình dễ bảo trì là **giữ policy tách khỏi kỹ thuật HTTP**: aggregator không nên tự cài đặt DNS validation hoặc TLS trust logic trong một lambda ngắn.

## 40. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| **NoSuchElementException** khi gọi ScopedValue.get | Task chưa bind context | Capture/rebind rõ ở task boundary |
| Header correlation ID bị trộn giữa requests | Dùng static mutable field/ThreadLocal sai lifecycle | Immutable context + ScopedValue scope |
| Chạy tuần tự dù dùng virtual threads | Submit rồi get ngay trong cùng loop | Submit hết trước, rồi mới collect futures |
| Tổng hợp chờ gần N × timeout | Mỗi Future.get dùng full timeout riêng | Một deadline chung, tính thời gian còn lại |
| Deadline hết nhưng process chưa dừng | Cancellation không hợp tác; executor.close đợi | Resource lifecycle, streaming-body timeouts |
| HTTP 200 nhưng parse lỗi | Không cùng hợp đồng dữ liệu | Validate UTF-8, schema, byte/count limits |
| Dữ liệu nguồn 503 bị cộng như 0 | Không phân biệt missing với empty | SourceResult có errorCode |
| Số lượng âm hoặc quá lớn | Parser thiếu range validation | Grammar và business constraints |
| Tổng bị âm bất ngờ | Integer overflow khi merge | Math.addExact/kiểu dữ liệu rộng hơn |
| Số connection tăng vọt | Executor tạo task không có backpressure | Fan-out cap, Semaphore/quota theo upstream |
| Đọc response body mãi chưa xong | Streaming không có hard read deadline | Close/cancel, I/O timeout, watchdog |
| Leak tài nguyên HTTP | Response stream không được đóng | try-with-resources |
| Redirect tới endpoint cấm | Auto-follow redirects | Redirect.NEVER hoặc revalidate từng hop |
| Thay HttpClient mỗi task | Không reuse connection pool | Shared HttpClient lifecycle |
| CPU cao dù virtual threads | Tác vụ parsing/CPU-bound hoặc workload tăng | Profiling và giới hạn CPU |
| SSRF khi nhận URL từ user | Thiếu destination policy | Allowlist và connection-time egress enforcement |
| Bật preview mới biên dịch | Dùng StructuredTaskScope preview | Bản demo dùng API ổn định, không cần preview |
| Kết quả khác nhau mỗi lần | Lấy theo thứ tự response completion | Giữ endpoint order hoặc sort theo key |

## 41. Bài tập thực hành

**Bài 1 — Thêm kho thứ tư.** Thêm endpoint **/central** trả **book=2**, **pen=1**, **pencil=9**. Kiểm tra tổng hợp thành **book=19**, **pen=8**, **pencil=9** và các source statuses.

**Bài 2 — Ngắt giữa chừng.** Tạo mock endpoint chưa trả headers trong vài giây; kiểm tra request timeout, Future cancellation và thời gian shutdown thực sự. Giải thích vì sao timeout trong Future không bảo đảm hard wall-clock deadline.

**Bài 3 — Response quá lớn.** Trả hơn 4.096 bytes từ mock; xác nhận **invalid_payload** và response stream được đóng.

**Bài 4 — Dữ liệu lỗi.** Trả một key trùng, quantity âm, quantity vượt 100.000 và malformed UTF-8; phân biệt từng loại lỗi trong test.

**Bài 5 — Correlation ID.** Cho hai requests với ID khác nhau chạy đồng thời, dùng mock server kiểm tra headers. Chứng minh ScopedValue binding không lẫn giữa các requests.

**Bài 6 — Hạn chế concurrency.** Giả sử 100 endpoints cần gọi nhưng upstream chỉ cho 10 concurrent requests. Thêm semaphore/bounded admission và đo số lời gọi thực đang chạy.

**Bài 7 — Chính sách partial results.** Thay đổi aggregator để với một nguồn bắt buộc bị lỗi, toàn bộ request trả trạng thái **incomplete** hoặc fail-closed theo hợp đồng; không chỉ nhìn tổng.

**Bài 8 — JSON.** Dùng một JSON parser được bảo trì trong dự án riêng, định nghĩa DTO có validation, parser nesting limits và max response bytes.

**Bài 9 — Retry có giới hạn.** Thêm retry cho GET trả 503 với tối đa 2 lần, exponential backoff và jitter; bảo đảm tổng thời gian không vượt request budget theo thiết kế.

**Bài 10 — Observability.** Ghi thời gian từng nguồn và tổng hợp, xuất metrics thành công/thất bại theo source name cố định, không dùng request ID làm metric label.

**Bài 11 — Bảo mật.** Thiết kế chính sách khi endpoint được cấu hình qua admin UI. Trình bày kiểm tra HTTPS, host/port allowlist, redirect, SSRF, DNS rebinding và TLS.

**Bài 12 — Chuyển sang structured concurrency.** Trong một nhánh thực nghiệm độc lập của dự án, xem API **StructuredTaskScope preview của chính JDK 27** và cách nó tự kế thừa ScopedValue bindings. So sánh lifecycle và error policies với ExecutorService; không lẫn build flags preview vào bản ứng dụng ổn định nếu chưa có quyết định hỗ trợ preview.

## 42. Checklist hoàn thành dự án Java 27

- [ ] Chạy được một HTTP client tổng hợp nhiều nguồn qua loopback.
- [ ] Có bản ghi kết quả/nguồn lỗi rõ ràng.
- [ ] Hiểu **virtual thread cho I/O**, không phải công cụ làm CPU vô hạn.
- [ ] Dùng **newVirtualThreadPerTaskExecutor** và quản lý vòng đời.
- [ ] Submit toàn bộ tác vụ trước khi collect kết quả.
- [ ] Có **ScopedValue<RequestContext>** và binding phạm vi ngắn.
- [ ] Với ExecutorService, capture context và **bind lại trong mỗi task**.
- [ ] Không giả định ScopedValue tự lan qua mọi virtual threads.
- [ ] Không dùng static mutable request context để lưu correlation ID.
- [ ] HttpClient dùng chung, có connect/request timeouts và redirect policy.
- [ ] Dùng **BodyHandlers.ofInputStream** khi cần bounded streaming.
- [ ] Response InputStream được đóng trong mọi nhánh thành công/lỗi.
- [ ] Giới hạn response bytes và kích thước dữ liệu sau parse.
- [ ] UTF-8 được decode theo chính sách lỗi rõ.
- [ ] Có schema/parser validation và không chấp nhận duplicate keys.
- [ ] Dữ liệu nguồn lỗi không bị cộng nhầm thành số 0.
- [ ] Có chính sách partial results/fail-closed theo nghiệp vụ.
- [ ] Tổng hợp kiểm tra overflow, đầu ra được sắp xếp ổn định.
- [ ] Có deadline chung, phân biệt timeout với cancellation best effort.
- [ ] Không xem Future.cancel là bảo đảm rollback upstream.
- [ ] Có giới hạn số nguồn và outbound concurrency.
- [ ] Có test 200, 4xx/5xx, slow server, oversized/malformed response.
- [ ] Có test ScopedValue isolation giữa requests khác nhau.
- [ ] Dùng HTTPS và egress/SSRF policy khi truy cập endpoint thật.
- [ ] Không log secrets/token và không dùng requestId làm metric label.
- [ ] Hiểu **StructuredTaskScope vẫn preview ở Java 27**, còn ScopedValue đã ổn định.
- [ ] Đã xác nhận giải pháp phù hợp với load/latency thực tế trước triển khai production.

**Kết luận:** Một HTTP aggregator hiệu quả trong Java 27 không chỉ là gửi nhiều request đồng thời. Nó phải **có nguồn dữ liệu đáng tin theo hợp đồng, context được truyền đúng, giới hạn tài nguyên, mô hình lỗi tường minh và vòng đời task có thể kiểm soát**. Virtual threads giúp diễn đạt việc chờ I/O theo mã tuần tự dễ đọc; ScopedValue giữ request context trong một phạm vi an toàn; còn HttpClient, Future, timeout và validation giúp liên kết chúng thành một dự án tích hợp có thể mở rộng dần.

## Tài liệu tham khảo

- [Java SE 27 — ScopedValue](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.html): binding, rebinding, per-thread semantics và structured inheritance.
- [Java SE 27 — HttpClient](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.html): cấu hình, send, lifecycle và connection reuse.
- [Java SE 27 — HttpRequest](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpRequest.html): URI, headers và per-request timeout.
- [Java SE 27 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): streaming response, lifecycle InputStream.
- [Java SE 27 — Executors](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executors.html): newVirtualThreadPerTaskExecutor.
- [Java SE 27 — Future](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Future.html): get, cancellation và timeout.
- [Java SE 27 — ExecutorService](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html): task lifecycle, close và shutdown.
- [Java SE 27 — StructuredTaskScope (preview)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): structured concurrency, fork/join và inheritance của ScopedValue.
- [Java SE 27 — HttpServer](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): mock loopback HTTP server.
- [Java SE 27 — CharsetDecoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CharsetDecoder.html): strict UTF-8 decoding.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): tính năng virtual threads ổn định từ JDK 21.
- [JEP 506 — Scoped Values](https://openjdk.org/jeps/506): ScopedValue được hoàn thiện ở JDK 25.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): cải thiện monitor blocking trong JDK hiện đại.
- [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): đích outbound, redirect và DNS rebinding.
