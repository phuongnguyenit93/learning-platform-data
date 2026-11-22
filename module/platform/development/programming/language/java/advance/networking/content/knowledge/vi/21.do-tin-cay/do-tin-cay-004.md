# Tính lũy đẳng, mã yêu cầu và kết quả chưa xác định sau mất kết nối

## 1. Bài toán độ tin cậy: client mất response sau khi server đã commit

Client gửi một lệnh tạo giao dịch, server thực hiện thành công rồi trả response. Nhưng nếu kết nối đứt **sau commit và trước khi response đến client**, client chỉ thấy `IOException`/timeout mà **không biết nghiệp vụ đã hoàn tất hay chưa**. Việc retry bừa có thể tạo giao dịch trùng. Đây là bài toán **unknown outcome**, khác hẳn một yêu cầu chắc chắn đã bị server từ chối.

~~~text
CLIENT                                     SERVER
 POST amount=100, key=op-42 --------------> xử lý và commit receipt=R-1
                          X <------------- response bị mất
 Client: UNKNOWN                            Server: COMPLETED
 POST amount=100, key=op-42 --------------> nhận ra key, trả cached R-1
 201 receipt=R-1 <------------------------ không tạo effect lần 2
~~~

Có ít nhất ba khả năng cùng dẫn tới lỗi mạng ở client: request chưa đến server; request đã đến và còn xử lý/rollback; hoặc request đã **được commit** nhưng response mất. **Không thể phân biệt ba khả năng chỉ bằng exception ở phía client.** Hệ thống phải có cách truy vấn operation hoặc retry theo cùng mã logic để khôi phục kết quả.

Mục tiêu bài: hiểu tính lũy đẳng, phân biệt request ID với idempotency key, thiết kế cơ chế chống trùng ở server, xử lý tình huống kết quả chưa xác định, biết rõ giới hạn “exactly once”, và xem hai ví dụ Java 17+ chạy trên HTTP loopback không cần Internet.

## 2. Tính lũy đẳng (idempotency) thực sự nghĩa là gì?

Một thao tác **lũy đẳng** khi lặp lại thao tác đó nhiều lần vẫn có **hiệu ứng nghiệp vụ được yêu cầu** như chỉ thực hiện một lần:

~~~text
effect(op, op, op) == effect(op)
~~~

Ví dụ cùng một lệnh “đặt trạng thái người dùng thành ACTIVE” có thể lũy đẳng: cuối cùng vẫn ACTIVE. Gọi POST “tạo giao dịch mới” ba lần không mặc định lũy đẳng: có thể tạo ba giao dịch. Tuy nhiên POST có contract `Idempotency-Key` được server thực thi đúng thì có thể cho phép **gửi lại cùng một logical operation nhiều lần mà chỉ tạo một tác động nghiệp vụ**.

**Lũy đẳng không có nghĩa response của hai lần phải giống từng byte.** Một lệnh DELETE xóa item có thể trả 204 lần đầu, 404 lần sau, nhưng desired effect “item không tồn tại” vẫn như nhau. Access logs/metrics có thể ghi nhiều lần dù hiệu ứng nghiệp vụ lũy đẳng.

| Thuật ngữ | Định nghĩa | Độ bảo đảm |
| --- | --- | --- |
| **Idempotency** | Lặp cùng logical operation có cùng hiệu ứng dự định | Cần server/operation contract |
| **At-most-once effect** | Mỗi operation xảy ra tối đa một lần | Có thể chưa xảy ra; vẫn phải phân biệt UNKNOWN |
| **At-least-once delivery** | Retry để cố gắng giao yêu cầu ít nhất một lần | Có thể chạy side effect nhiều lần nếu thiếu dedup |
| **Exactly-once end-to-end** | Một tác động xảy ra đúng một lần qua mọi process/network/downstream | Không tự đạt bằng header hay local map |

Không nên tự tuyên bố “exactly once” khi chỉ kiểm tra request đã từng xuất hiện trong `HashMap`. Điều cần định nghĩa là **ranh giới của tác động thật**, phạm vi transaction, crash window, retry và retention.

## 3. HTTP method có idempotent mặc định không?

RFC 9110 `9.2.2 quy định safe methods (GET/HEAD, v.v.), PUT và DELETE có **idempotent semantics**; POST thì **không mặc nhiên**.

| Method | Semantics thông thường | Phán đoán retry |
| --- | --- | --- |
| `GET`/`HEAD` | Đọc/metadata, safe/idempotent | Có thể retry theo quota/timeout policy |
| `PUT` | Đặt/thay thế tài nguyên tại URI cụ thể | Cùng request có desired state giống nhau; response có thể khác |
| `DELETE` | Xóa tài nguyên đã chỉ định | Có thể idempotent dù lần sau 404 |
| `POST` | Xử lý theo resource, thường tạo tài nguyên/tác động mới | Cần định nghĩa idempotency riêng để retry an toàn |

RFC cũng cảnh báo không tự retry non-idempotent request nếu không biết semantics lũy đẳng hoặc không biết request đầu chưa được áp dụng. Trong thực tế có thể có retry ở client, proxy và các tầng trung gian; backend chống trùng vẫn cần thiết. Chuyển method POST sang PUT **không tự đảm bảo** một payment gateway ở hệ thống khác sẽ chỉ charge một lần.

## 4. Request ID, operation ID và idempotency key

Ba định danh hay bị gộp:

- **requestId/correlation ID**: phục vụ log, trace một HTTP attempt. Retry mới có thể có request ID mới.
- **operationId/Idempotency-Key**: định danh **một ý định nghiệp vụ**; mọi attempt retry cùng intent phải dùng **cùng key**.
- **resourceId/receiptId**: ID của tài nguyên hoặc kết quả do server tạo. Dùng để tra cứu/đối soát.

~~~text
Logical operation: chuyển 100 cho B
  Idempotency-Key: op-42
  Attempt 1: requestId=req-A -> mất response
  Attempt 2: requestId=req-B -> server trả receipt=R-1
  Kết quả nghiệp vụ: chỉ một operation R-1

Logical operation MỚI: chuyển thêm 100 cho B
  Idempotency-Key: op-43
  Kết quả nghiệp vụ: tạo receipt=R-2
~~~

Header `Idempotency-Key` **không tự được Java HttpClient hoặc mọi server diễn giải**. Nó chỉ có nghĩa nếu API contract định nghĩa key, scope, payload fingerprint, kết quả trả lại, retention và retry. Nếu dịch vụ dùng tên header/field khác, phải theo chính contract đó.

**Scope:** server nên ràng buộc key với tenant/principal và loại operation (method + endpoint hoặc resource), tránh hai người dùng cùng chuỗi key làm ảnh hưởng nhau. Trace ID riêng không thể thay thế idempotency key ổn định khi retry.

## 5. Thiết kế hợp đồng giữa client và server

Một ví dụ HTTP request:

~~~http
POST /transfers HTTP/1.1
Content-Type: application/json
Idempotency-Key: 7ce60a9a-4f18-452c-93ad-3f801ea39d4b

{"from":"A","to":"B","amount":100,"currency":"VND"}
~~~

*Đây là message HTTP minh họa, không phải ví dụ client chạy độc lập.*

Contract nên trả lời:

1. **Ai sinh key?** Client/orchestrator tạo key duy nhất cho logical operation, lưu trước khi gửi (dùng UUID ngẫu nhiên hoặc ID ổn định phù hợp).
2. **Cùng request nghĩa là gì?** Server so key + **fingerprint của payload có ảnh hưởng nghiệp vụ**. Cùng key khác amount/receiver -> conflict, không tạo operation mới.
3. **Server giữ kết quả gì?** Trạng thái, response status/body/resource ID và thời hạn lưu. Retry cùng key + fingerprint trả trạng thái/kết quả đã biết.
4. **Hai request cùng key đến đồng thời thì sao?** Phải atomically claim một owner, request sau chờ/nhận pending/replay; không chạy side effect trùng.
5. **Key hết hạn thì sao?** TTL/retention phải công bố rõ. Retry quá muộn không được mặc định an toàn nếu record đã bị dọn.
6. **Quyền truy cập?** Key phải ràng buộc principal/tenant; không trả receipt của người khác chỉ vì họ đoán đúng key.

Một status/receipt endpoint giúp client hỏi `GET /operations/{operationId}` thay vì đoán kết quả khi nhận `IOException`.

## 6. State machine nên có cho operation

~~~text
               new scoped key
 ABSENT ------------------------------> IN_PROGRESS
                                             |
                              apply effect + commit result
                                             v
                                         COMPLETED
                                             |
                     same key + same payload -> replay result

 In-progress duplicate -> wait/poll/pending, KHÔNG apply lần 2.
 Same key + other payload -> CONFLICT, KHÔNG apply effect khác.
 FAILED/UNKNOWN -> phân biệt lỗi đã rollback với tác động không chắc.
~~~

`IN_PROGRESS` **không luôn nghĩa “chưa gọi downstream”**. Nếu worker đã gửi yêu cầu tới payment gateway rồi crash, bản ghi pending có thể tương ứng một giao dịch đã charge. Không xóa pending và chạy lại thiếu đối soát.

Nếu toàn bộ effect nằm trong cùng một database, lưu effect + result trong một transaction có unique key sẽ mạnh hơn. Khi gọi external service, cần downstream idempotency key hoặc outbox/inbox + reconciliation; local state không đủ.

## 7. Sau disconnect, cách nghĩ nào là đúng?

~~~text
Kịch bản A:
 Client --X--> Server  (request không tới)
 Effect = 0

Kịch bản B:
 Client -----> Server (đang xử lý)
         <---X        Effect có thể chưa chắc chắn

Kịch bản C:
 Client -----> Server (commit R-1)
         <---X        Effect = 1 nhưng response mất
~~~

Các lỗi như `IOException`, EOF, connection reset, `HttpTimeoutException` có thể để lại trạng thái **UNKNOWN** nếu client đã/ có thể đã gửi request. Không dùng “network failed” làm bằng chứng “DB rolled back”. Ngay cả khi client cancel `CompletableFuture`, server có thể đã nhận và xử lý request.

**Chính sách UX:** trong các thao tác tài chính, hiển thị “Đang xác minh kết quả” và cung cấp tra cứu trạng thái. Đừng tự động mở giao dịch mới với idempotency key mới khi kết quả cũ chưa rõ.

## 8. Retry an toàn: cùng key, cùng payload, có deadline

Quy trình client:

~~~text
1. Tạo operationId một lần và lưu trước khi gửi.
2. Gửi request với operationId + payload đúng contract.
3. Nếu nhận kết quả COMMITTED: lưu receipt và dừng.
4. Nếu nhận PENDING: poll operationId, không tạo effect mới.
5. Nếu nhận CONFLICT: dừng, kiểm tra reuse key/payload.
6. Nếu I/O timeout/disconnect: đánh dấu UNKNOWN, tra cứu status.
7. Nếu contract cho phép: retry CÙNG key + CÙNG intent/payload.
8. Hạn chế số lần, deadline tổng, exponential backoff + jitter.
9. Nếu vượt TTL hoặc không thể đối soát: escalated UNKNOWN, không retry mù.
~~~

HTTP 429/503 hoặc `Retry-After` có thể gợi ý backoff, **nhưng không tự cấp phép retry một POST non-idempotent**. Phân biệt lỗi validation (400), authorization (401/403), fingerprint conflict (409), pending (202) và lỗi transport. Khi client/gateway/queue đều retry, các tầng phải giữ cùng logical key để chống trùng.

## 9. Java 17+: minh họa server commit rồi mất HTTP response

Bài thực hành đầu chạy một `HttpServer` trên `127.0.0.1` và `HttpClient` trong cùng JVM. Server dùng `ConcurrentHashMap.compute` lưu `Stored(payload, receipt)` với key đã scope, `AtomicInteger` đếm side effects. Nó cố ý **đóng exchange sau khi áp dụng effect nhưng trước khi gửi response headers lần đầu**. Client gặp `IOException` nên coi outcome chưa rõ. Khi retry, server tìm key cũ, trả receipt R-1 và không tăng effect.

**Quan trọng:** store ở đây **chỉ là bộ nhớ của một process**, hoàn toàn không phải durable database. `ConcurrentHashMap.compute` minh họa atomicity per-key trong JVM, **không** đảm bảo across nodes/restart, không làm payment gateway exactly-once. Server demo đọc body với `readAllBytes()` rồi mới kiểm size, không phù hợp production (cần giới hạn trong lúc stream).

Tạo file `UnknownOutcomeRetryDemo.java`:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class UnknownOutcomeRetryDemo {
    record Stored(String payload, String response) {}
    record Decision(int status, String response, boolean replayed,
                    boolean newlyApplied) {}

    private static final ConcurrentHashMap<String, Stored> STORE =
            new ConcurrentHashMap<>();
    private static final AtomicInteger EFFECTS = new AtomicInteger();
    private static final AtomicBoolean DROP_FIRST_RESPONSE = new AtomicBoolean(true);

    private static void respond(HttpExchange exchange, Decision decision)
            throws IOException {
        byte[] bytes = decision.response().getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.getResponseHeaders().set(
                "Idempotency-Replayed", Boolean.toString(decision.replayed()));
        exchange.sendResponseHeaders(decision.status(), bytes.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    private static void transfer(HttpExchange exchange) throws IOException {
        try {
            if (!"POST".equals(exchange.getRequestMethod())) {
                exchange.sendResponseHeaders(405, -1);
                return;
            }
            String key = exchange.getRequestHeaders()
                    .getFirst("Idempotency-Key");
            if (key == null || key.isBlank() || key.length() > 64) {
                exchange.sendResponseHeaders(400, -1);
                return;
            }
            byte[] body = exchange.getRequestBody().readAllBytes();
            if (body.length > 128) {
                exchange.sendResponseHeaders(413, -1);
                return;
            }
            String payload = new String(body, StandardCharsets.UTF_8);
            String scopedKey = "demo-user|POST|/transfers|" + key;
            AtomicReference<Decision> answer = new AtomicReference<>();
            STORE.compute(scopedKey, (ignored, previous) -> {
                if (previous != null) {
                    if (!previous.payload().equals(payload)) {
                        answer.set(new Decision(409,
                                "key reused with different payload", false, false));
                    } else {
                        answer.set(new Decision(201, previous.response(), true, false));
                    }
                    return previous;
                }
                int receiptNumber = EFFECTS.incrementAndGet();
                String receipt = "receipt=R-" + receiptNumber;
                answer.set(new Decision(201, receipt, false, true));
                return new Stored(payload, receipt);
            });
            Decision decision = answer.get();
            if (decision.newlyApplied()
                    && DROP_FIRST_RESPONSE.compareAndSet(true, false)) {
                // Simulate: server applied the effect, then the connection
                // disappeared before it could send HTTP response headers.
                return;
            }
            respond(exchange, decision);
        } finally {
            exchange.close();
        }
    }

    private static HttpRequest request(String endpoint, String key, String payload) {
        return HttpRequest.newBuilder(URI.create(endpoint))
                .timeout(Duration.ofSeconds(5))
                .header("Idempotency-Key", key)
                .header("Content-Type", "text/plain; charset=utf-8")
                .POST(HttpRequest.BodyPublishers.ofString(
                        payload, StandardCharsets.UTF_8))
                .build();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService pool = Executors.newFixedThreadPool(4);
        server.setExecutor(pool);
        server.createContext("/transfers", UnknownOutcomeRetryDemo::transfer);
        server.start();
        try {
            String endpoint = "http://127.0.0.1:"
                    + server.getAddress().getPort() + "/transfers";
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .version(HttpClient.Version.HTTP_1_1).build();
            HttpRequest first = request(endpoint, "op-42", "transfer=100");
            boolean unknownOutcome = false;
            try {
                client.send(first, HttpResponse.BodyHandlers.ofString());
            } catch (IOException expected) {
                unknownOutcome = true;
            }
            if (!unknownOutcome) {
                throw new AssertionError("expected an intentionally lost response");
            }
            System.out.println("first attempt: outcome unknown to client");

            HttpResponse<String> retry = client.send(
                    request(endpoint, "op-42", "transfer=100"),
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("same-key retry: " + retry.statusCode()
                    + " " + retry.body());
            System.out.println("replayed: " + retry.headers()
                    .firstValue("Idempotency-Replayed").orElse("missing"));
            System.out.println("effects after retry: " + EFFECTS.get());

            HttpResponse<String> mismatch = client.send(
                    request(endpoint, "op-42", "transfer=999"),
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("same key, other payload: " + mismatch.statusCode());
            System.out.println("effects after conflict: " + EFFECTS.get());

            HttpResponse<String> distinct = client.send(
                    request(endpoint, "op-43", "transfer=100"),
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("new-key request: " + distinct.statusCode()
                    + " " + distinct.body());
            System.out.println("final effects: " + EFFECTS.get());
        } finally {
            server.stop(0);
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac UnknownOutcomeRetryDemo.java
java UnknownOutcomeRetryDemo
~~~

Stdout chính xác:

~~~text
first attempt: outcome unknown to client
same-key retry: 201 receipt=R-1
replayed: true
effects after retry: 1
same key, other payload: 409
effects after conflict: 1
new-key request: 201 receipt=R-2
final effects: 2
~~~

## 10. Giải thích output của ví dụ mất response

**Lượt đầu:** `Idempotency-Key: op-42`, payload `transfer=100`. Server claim key `demo-user|POST|/transfers|op-42` và tạo `receipt=R-1`; sau đó code cố tình không gửi headers mà gọi `exchange.close()` trong `finally`. Vì client không nhận HTTP response, nó in `first attempt: outcome unknown to client`. Ở mã nguồn test ta biết effect đã xảy ra, nhưng ở client thật không được suy đoán điều ấy từ một lỗi I/O.

**Retry đúng:** cùng key `op-42` và payload y nguyên, server trả lại `201 receipt=R-1` cùng header demo `Idempotency-Replayed: true`. Counter `effects after retry: 1` chứng minh in-memory effect không lặp.

**Reuse sai:** cùng `op-42` nhưng `transfer=999` trả `409`, counter vẫn 1. Đừng “chữa” 409 bằng cách đổi key khi request cũ có khả năng đã được áp dụng; đây có thể gây duplicate/tác động ngoài ý định.

**Operation mới:** `op-43` với cùng số tiền là một logical operation **khác**, nên tạo `receipt=R-2`, counter 2. Cùng payload **không bắt buộc** cùng business operation: ID mới là phân biệt ý định mới với retry.

Header `Idempotency-Replayed` ở demo là **quy ước ứng dụng tự đặt**, không phải mọi API đều trả. HTTP 201 trong lần replay cũng là một policy; có hệ thống trả lại nguyên response, có hệ thống trả 200 cùng resource ID.

## 11. Duplicate đồng thời: lỗi race của containsKey + put

Một anti-pattern:

~~~java
if (!store.containsKey(key)) {
    externalCharge();              // Hai threads có thể cùng gọi.
    store.put(key, result);
}
~~~

*Đoạn trên là **giả mã cố tình sai**; biến `store`, `key`, `result` và `externalCharge` không phải chương trình độc lập.*

Hai threads có thể đều thấy “key chưa tồn tại” rồi cùng thực hiện charge. Sau cùng map chỉ còn **một record**, nhưng khách hàng đã bị charge **hai lần**. Trong một JVM, phép `ConcurrentHashMap.compute` có atomic remapping per-key, phù hợp để minh họa chống race **trong bộ nhớ**. Ở hệ thống nhiều pods, mỗi JVM có map riêng, nên vẫn phải có **unique constraint/atomic claim ở durable DB**.

Cũng không nên gọi external payment gateway **bên trong `compute`** rồi kết luận “an toàn”; mạng ngoài không nằm trong transaction của map và có thể commit rồi response mất.

## 12. Java 17+: tám yêu cầu trùng cùng lúc chỉ ghi một hiệu ứng

Chương trình `ConcurrentKeyDedupDemo` gửi **8 POST song song** bằng `HttpClient.sendAsync`, cùng `Idempotency-Key: batch-7` và payload `amount=42`. Server dùng `ConcurrentHashMap.compute` cho key cùng principal/endpoint, nên chỉ request đầu trong **JVM test** tạo stored record và tăng effect count; bảy request còn lại nhận cached result.

Code in **tổng số** thay vì dựa vào thứ tự request hoàn tất (không deterministic). Gửi thêm request cùng key nhưng payload khác để kiểm chứng conflict.

Tạo file `ConcurrentKeyDedupDemo.java`:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentKeyDedupDemo {
    record Stored(String payload, String response) {}

    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Stored> stored = new ConcurrentHashMap<>();
        AtomicInteger applied = new AtomicInteger();
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService handlers = Executors.newFixedThreadPool(8);
        server.setExecutor(handlers);
        server.createContext("/operations", exchange -> {
            try {
                byte[] bytes = exchange.getRequestBody().readAllBytes();
                String payload = new String(bytes, StandardCharsets.UTF_8);
                String key = exchange.getRequestHeaders()
                        .getFirst("Idempotency-Key");
                if (!"POST".equals(exchange.getRequestMethod())
                        || key == null || key.isBlank() || bytes.length > 128) {
                    exchange.sendResponseHeaders(400, -1);
                    return;
                }
                AtomicBoolean fresh = new AtomicBoolean();
                Stored record = stored.compute("demo-user|POST|/operations|" + key,
                        (ignored, previous) -> {
                            if (previous != null) return previous;
                            fresh.set(true);
                            int number = applied.incrementAndGet();
                            return new Stored(payload, "created=R-" + number);
                        });
                int status = record.payload().equals(payload) ? 201 : 409;
                String result = status == 201
                        ? record.response() : "different payload";
                exchange.getResponseHeaders().set(
                        "Idempotency-Replayed",
                        Boolean.toString(status == 201 && !fresh.get()));
                byte[] reply = result.getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(status, reply.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(reply);
                }
            } finally {
                exchange.close();
            }
        });
        server.start();

        try {
            String endpoint = "http://127.0.0.1:"
                    + server.getAddress().getPort() + "/operations";
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3)).build();
            HttpRequest request = HttpRequest.newBuilder(URI.create(endpoint))
                    .timeout(Duration.ofSeconds(8))
                    .header("Idempotency-Key", "batch-7")
                    .POST(HttpRequest.BodyPublishers.ofString("amount=42"))
                    .build();
            List<CompletableFuture<HttpResponse<String>>> futures =
                    java.util.stream.IntStream.range(0, 8)
                            .mapToObj(i -> client.sendAsync(
                                    request, HttpResponse.BodyHandlers.ofString(
                                            StandardCharsets.UTF_8)))
                            .toList();

            CompletableFuture.allOf(
                    futures.toArray(CompletableFuture<?>[]::new))
                    .get(15, TimeUnit.SECONDS);
            List<HttpResponse<String>> results =
                    futures.stream().map(CompletableFuture::join).toList();
            long successes = results.stream()
                    .filter(r -> r.statusCode() == 201).count();
            long replays = results.stream().filter(r ->
                    r.headers().firstValue("Idempotency-Replayed")
                            .orElse("false").equals("true")).count();
            System.out.println("successful responses: " + successes);
            System.out.println("replayed responses: " + replays);
            System.out.println("side effects: " + applied.get());
            System.out.println("stored keys: " + stored.size());

            HttpRequest conflict = HttpRequest.newBuilder(URI.create(endpoint))
                    .timeout(Duration.ofSeconds(5))
                    .header("Idempotency-Key", "batch-7")
                    .POST(HttpRequest.BodyPublishers.ofString("amount=999"))
                    .build();
            HttpResponse<String> mismatch = client.send(conflict,
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("same-key conflict status: "
                    + mismatch.statusCode());
            System.out.println("side effects after conflict: " + applied.get());
        } finally {
            server.stop(0);
            handlers.shutdownNow();
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ConcurrentKeyDedupDemo.java
java ConcurrentKeyDedupDemo
~~~

Stdout:

~~~text
successful responses: 8
replayed responses: 7
side effects: 1
stored keys: 1
same-key conflict status: 409
side effects after conflict: 1
~~~

`successful responses: 8` ở đây là số HTTP responses status 201, **không phải tám side effects**. `replayed responses: 7` là bảy lần đọc lại kết quả. `side effects: 1` mới là số lần code in-memory áp dụng logic tạo bản ghi. Nếu chạy test trên nhiều JVM/DB hoặc kill process, cần cơ chế bền vững khác — không được suy rộng kết quả unit demo thành bảo đảm production.

## 13. Bản ghi lũy đẳng nào phải bền vững?

Một schema tham khảo:

| Trường | Ví dụ | Vai trò |
| --- | --- | --- |
| `tenant_id` | tenant-A | Namespace và authorization |
| `operation_type` | POST:/transfers | Phân biệt loại nghiệp vụ |
| `idempotency_key` | op-42 | Logical operation |
| `request_fingerprint` | SHA-256 của payload canonical | Chống reuse key khác intent |
| `state` | IN_PROGRESS/COMPLETED | Theo dõi claim và recovery |
| `resource_id` | transfer-R-1 | Truy vấn giao dịch đã tạo |
| `http_status`, `response_body` | 201, receipt | Có thể replay kết quả |
| `created_at`, `expires_at` | timestamps | TTL/retention |
| `lease_version` | version/worker | Chống stale worker lấy lại pending |

Khóa duy nhất điển hình: `UNIQUE(tenant_id, operation_type, idempotency_key)`. Khi key đã có, phải kiểm fingerprint và status, chứ không tự bắt đầu effect thứ hai. Giữ key theo tenant tránh rò rỉ cached response của người dùng khác.

Nếu database cho phép effect và result record ở **cùng một transaction**, mục tiêu là **atomic commit**. Nếu business side effect nằm ở payment gateway khác, DB transaction nội bộ **không kéo theo** giao dịch tại gateway: cần downstream idempotency key, outbox/inbox, retries có giới hạn và reconciliation.

## 14. Giao dịch, unique constraint và crash window

Một flow giả mã:

~~~text
BEGIN TRANSACTION
  INSERT scoped idempotency key IF ABSENT (unique index)
  Nếu đã tồn tại:
    so fingerprint; khác -> conflict
    nếu COMPLETED -> trả saved result
    nếu IN_PROGRESS -> pending/wait/reconcile
  Nếu claim thành công:
    thực hiện business update trong cùng DB transaction
    lưu resource ID, status, body hoặc receipt
    chuyển state thành COMPLETED
COMMIT

Gửi HTTP response. Nếu response bị mất, record vẫn còn để replay.
~~~

Đây là **thuật toán khái niệm**, không phải SQL trực tiếp cho mọi RDBMS. Production phải xét isolation level, deadlock, unique constraint violation, transaction retries, crash recovery và các side effects bên ngoài DB.

Ví dụ rủi ro nghiêm trọng:

~~~text
1. Server gọi gateway CHARGE op-42
2. Gateway charge thành công
3. Server crash trước khi lưu COMPLETED
4. Client timeout, retry op-42
5. Server không biết gateway đã charge, có nguy cơ gọi lại
~~~

Để xử lý, phải có downstream operation ID/idempotency key được gateway chấp nhận và endpoint tra cứu/đối soát. Không tự xóa `IN_PROGRESS` vì một lease đã hết: worker có thể đã làm phần việc ngoại vi. Outbox/inbox hoặc saga có thể phù hợp tùy kiến trúc.

## 15. Canonical request fingerprint và conflict

Cùng key phải tương ứng cùng ý định: amount, currency, account, recipient, item ID hoặc các thuộc tính làm thay đổi tác động. Cần thống nhất cách fingerprint/canonicalization.

~~~json
{"amount":100,"currency":"VND"}
{"currency":"VND","amount":100}
~~~

Trong JSON, hai bản trên có thể là **cùng intent** khi canonicalize keys và dữ liệu phù hợp, dù byte order khác nhau. Ngược lại:

~~~json
{"amount":100,"currency":"VND"}
{"amount":999,"currency":"VND"}
~~~

Là **khác intent**, phải trả conflict nếu reuse key. Hash SHA-256 chỉ là phương tiện tạo fingerprint, không thay thế validation, authorization và normalization. Không nên đưa trace ID thay đổi mỗi retry vào fingerprint nghiệp vụ. Hãy version canonicalization khi cập nhật schema/API.

Demo dùng **so sánh String y nguyên** để code tập trung vào cơ chế dedup; nó không phải JSON canonicalizer và không xử lý Unicode normalization, JSON equivalent values, floating-point hay các tính chất tài chính phức tạp.

## 16. IN_PROGRESS, TTL và recovery đúng

**IN_PROGRESS** có thể có ba trạng thái thực tế: chưa gọi downstream, đã gọi và đang chờ, hoặc đã commit ở downstream nhưng server chưa nhận result. Hãy chỉ cho một worker giữ claim/lease ở một thời điểm, có fencing token hoặc unique constraint để ngăn stale worker tiếp tục ghi; kết hợp **reconcile external result** khi process restart.

**TTL không có mặc định chung của HTTP/JDK.** API có thể giữ cached result 24 giờ, bảy ngày hoặc lâu hơn tùy nhu cầu; thời hạn là một phần contract. Một key hết TTL nhưng client vẫn retry sau 48 giờ có thể được coi là operation mới và tạo trùng — nguy hiểm với thanh toán. Các business receipt/ledger cần lưu bền vững hơn cache response ngắn hạn.

Retention nên cân bằng storage quota và cửa sổ retry; quy định rõ hết hạn sẽ reject, chuyển UNKNOWN cần đối soát, hay cho key mới. Đừng âm thầm coi key vừa hết hạn là intent chưa từng xử lý.

## 17. Cách nhận biết response, HTTP error và transport error

| Client thấy | Có thể kết luận | Chính sách điển hình |
| --- | --- | --- |
| 201 + receipt hợp lệ | Có response nghiệp vụ về tạo resource | Lưu receipt, dừng retry |
| 200 + result replay | API trả lại kết quả theo contract | Cập nhật trạng thái hoàn tất |
| 202 + PENDING | Server đã tiếp nhận nhưng chưa có final result | Poll theo operationId |
| 409 + fingerprint mismatch | Key bị dùng cho intent khác | Dừng, cảnh báo, không đổi key tùy tiện |
| 429/503 | Server quá tải/từ chối tạm | Backoff nếu operation idempotent |
| TCP reset/EOF/read timeout | **Outcome có thể UNKNOWN** | Query status hoặc retry cùng key |
| Future cancellation | Client yêu cầu hủy, chưa bảo đảm rollback | Query/reconcile |
| Status endpoint 404 | Có thể chưa có record, đã expire hoặc replication lag | Xem retention/contract, không tự kết luận |
| HTTP 500/502/504 | Server có lỗi, không có bằng chứng effect chưa xảy ra | Không retry với key mới |
| Request 400/401/403 | Có lỗi input/auth, thường cần sửa cấu hình | Tránh retry vô điều kiện |

Không gộp HTTP status khác 2xx với Java `IOException`. `HttpClient.send` có thể trả `HttpResponse` chứa status 500 bình thường về mặt HTTP; future chỉ exceptional khi có lỗi I/O/processing. Không được suy luận việc server charge đã xảy ra hay chưa chỉ từ một error class.

## 18. Java HttpClient: request timeout và future cancellation

Đoạn minh họa client gửi POST có key ổn định:

~~~java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.org/transfers"))
        .timeout(Duration.ofSeconds(5))
        .header("Idempotency-Key", operationId)
        .POST(HttpRequest.BodyPublishers.ofString(payload))
        .build();

CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
future.whenComplete((response, error) -> {
    if (error != null) {
        // UNKNOWN: query operation status/retry theo contract, đừng kết luận failed.
        return;
    }
    // Kiểm tra status, resourceId/receipt và lưu trạng thái cuối.
});
~~~

*Đoạn minh họa trong class có `client`, `operationId`, `payload` và imports; không phải chương trình chạy độc lập.*

`sendAsync` trả `CompletableFuture<HttpResponse<T>>`; `join()` có thể ném `CompletionException` khi exceptional. `send` có thể ném `IOException`. `HttpRequest.Builder.timeout` hạn chế thời gian HTTP request, **không chứng minh** server đã rollback khi timeout.

`CompletableFuture.cancel(true)` trên HTTP future là yêu cầu hủy, **không bảo đảm request chưa đến/được xử lý bởi server**. Nếu server đã charge, đóng TCP hoặc reset HTTP/2 stream không tự đảo ngược charge. Với POST không-idempotent, không dùng cancel + resend key mới như một cơ chế retry.

## 19. Bảo mật, giới hạn tài nguyên và quan sát

- **Key có entropy đủ**, tránh dùng email, số tài khoản, access token hoặc PII trực tiếp làm key. Giới hạn độ dài/header size và số key mới mỗi tenant.
- **Scope theo principal/tenant + operation type** để cùng key của hai người không thể đọc/ghi kết quả lẫn nhau. Sau xác thực vẫn phải kiểm authorization với resource.
- **Không log payload nhạy cảm** hoặc toàn bộ cached response. Log operation ID dạng an toàn, trace ID của attempt, state transition, result code và duration.
- **Đọc request body có giới hạn từ đầu**. Hai demo cố ý dùng `readAllBytes()` cho body nhỏ giả lập, rồi mới kiểm size; đừng copy cách đó cho Internet-facing server. Dùng capped streaming read và reject khi vượt.
- **Giới hạn in-flight operations**, HTTP connections, timeouts và DB locks. Duplicate request trong `IN_PROGRESS` có thể chờ có giới hạn, trả pending/Retry-After hoặc status endpoint.
- **Không cache vô hạn mọi lỗi 5xx**; những loại error nào replay hoặc retry được phụ thuộc contract và transaction outcome. Luôn phân biệt lỗi validation trước side effect với lỗi sau khi có khả năng đã commit.
- **Giới hạn auto-retry qua nhiều tầng**: ứng dụng, SDK, gateway, queue. Chia sẻ logical key để retry không tạo lặp effect và dùng exponential backoff + jitter.
- **Audit ledger/receipt bền vững** tách khỏi cache TTL, nhất là thanh toán và giao dịch nhiều bước.

## 20. Test matrix cho tính lũy đẳng

| Fault injection | Cách test | Điều phải kiểm chứng |
| --- | --- | --- |
| Duplicate tuần tự | Gửi cùng key/payload hai lần | Một effect, response replay đúng |
| Duplicate đồng thời | Nhiều threads/clients cùng key | Atomic claim, không charge trùng |
| Cùng key khác payload | Reuse key với amount mới | Conflict, không thay đổi effect |
| Key mới với payload giống | Thực hiện ý định mới | Được phép effect mới theo contract |
| Mất response sau commit | Đóng kết nối sau effect | Client UNKNOWN, retry/poll khôi phục |
| Crash trước DB commit | Kill process giữa transaction | Không có COMPLETED giả |
| Crash sau commit trước HTTP response | Kill sau COMMIT | Retry trả stored result |
| External gateway đã charge | Làm mất downstream response | Reconcile bằng provider operation ID |
| IN_PROGRESS lâu | Worker crash, lease hết | Fencing, đối soát trước reclaim |
| Key hết TTL | Retry sau expiration | Không tạo duplicate trái policy |
| HTTP 429/503/timeout | Retry policy + jitter/deadline | Không storm, giữ cùng key |
| Wrong tenant/key collision | Hai principals dùng cùng chuỗi key | Không rò rỉ cached receipt |
| Restart/đa instance | Hai+ server nodes | DB/unique index đảm bảo claim |
| Partial body/client cancel | Ngắt trong lúc upload/đợi response | Không đoán commit chỉ từ lỗi I/O |

Hai chương trình Java trong bài chứng minh **in-memory** dedup và response loss khi một JVM còn sống. Không coi chúng là test durability cho DB/process crash, external gateway hay multi-node.

## 21. Những nhầm lẫn thường gặp

| Hiểu sai | Sự thật | Cách sửa |
| --- | --- | --- |
| “IOException nghĩa là giao dịch thất bại.” | Response có thể mất sau commit | Đánh dấu UNKNOWN, tra cứu |
| “HTTP 500 chứng minh chưa ghi gì.” | Có thể fail sau effect | Reconcile |
| “Retry POST với key mới là an toàn.” | Key mới là operation mới | Giữ key cũ cho retry |
| “Thêm Idempotency-Key tự đủ.” | Server phải thực thi contract | Key + fingerprint + durable dedup |
| “requestId luôn là key chống trùng.” | requestId theo HTTP attempt | Tách operationId |
| “PUT/DELETE phải trả cùng status.” | Lũy đẳng nói về desired effect | Kiểm trạng thái cuối |
| “POST mặc định idempotent.” | Không theo RFC 9110 | Quy định riêng |
| “containsKey rồi put là atomic.” | Có race giữa các threads | Atomic claim |
| “ConcurrentHashMap đủ cho cluster.” | Mỗi JVM có map riêng | DB transaction/unique index |
| “Unique key đảm bảo gateway không charge hai lần.” | External effect ngoài DB | Downstream idempotency + reconcile |
| “IN_PROGRESS nghĩa là chưa charge.” | Gateway có thể đã nhận lệnh | Kiểm tra pending |
| “Key hết TTL vẫn chống trùng.” | Record có thể mất | Retention/ledger |
| “Cancel future rollback server.” | Cancel chỉ là yêu cầu | Query trạng thái |
| “Mọi response 5xx đều retryable.” | Có thể đã commit, contract khác nhau | Phân loại |
| “Hash payload thay thế auth.” | Hash không có quyền truy cập | Scope principal + auth |
| “ReadAllBytes rồi check limit là đủ.” | Allocation đã xảy ra | Capped streaming read |
| “Một cached 201 nghĩa exactly-once end-to-end.” | Chưa giải quyết crash/downstream | Định nghĩa transaction boundary |

## 22. Câu hỏi tự kiểm tra

**1.** Client gửi POST rồi bị mất response. Có được thông báo người dùng “thất bại” và tạo operation ID mới ngay không?

*Đáp án:* Không. Client đang ở trạng thái UNKNOWN; server có thể đã commit. Phải tra cứu/trả lại cùng ID theo contract.

**2.** Cùng key `op-42` nhưng payload amount khác nhau nên làm gì?

*Đáp án:* Conflict, không apply effect thứ hai; không âm thầm đổi nội dung của operation cũ.

**3.** Vì sao `ConcurrentHashMap.compute` không chứng minh exactly-once trong hệ ba pods?

*Đáp án:* Mỗi pod có map riêng và mất map khi restart. Không có transaction với DB/downstream, nên vẫn có double effect.

**4.** `DELETE /items/7` lần một 204, lần hai 404 có thể idempotent không?

*Đáp án:* Có. Intended effect item không còn tồn tại là như nhau dù response khác.

**5.** `CompletableFuture.cancel(true)` có làm payment gateway đảo charge không?

*Đáp án:* Không. Hủy client không là rollback downstream.

**6.** Key hết TTL sau một ngày, client retry sau ba ngày có an toàn tuyệt đối không?

*Đáp án:* Không. Server có thể đã quên key; cần ledger/retention dài hơn hoặc đối soát.

**7.** Cùng key và payload bị gửi đồng thời trong lúc IN_PROGRESS, có nên tạo hai jobs không?

*Đáp án:* Không. Một owner xử lý, bản còn lại chờ/poll/pending/replay.

**8.** Trace ID và operation ID có cần giống nhau?

*Đáp án:* Không. Trace ID có thể khác mỗi HTTP attempt; operation ID phải ổn định qua retry của một logical intent.

## 23. Bài tập vận dụng

1. Chạy `UnknownOutcomeRetryDemo`, chỉ ra chỗ server đã ghi effect và cố ý đóng exchange trước headers. Giải thích vì sao client chỉ biết UNKNOWN dù chương trình test biết effect xảy ra.
2. Thay key của retry đầu từ `op-42` thành `op-999`; quan sát effect count tăng, nêu vì sao retry này nguy hiểm.
3. Giữ `op-42` nhưng đổi `transfer=100` thành `transfer=101`; kiểm tra HTTP 409 và effect vẫn 1.
4. Trong `ConcurrentKeyDedupDemo`, tăng 8 lên 16 request, theo dõi số `replayed responses` và `side effects`; không dựa vào thứ tự hoàn tất.
5. Cố tình dùng `containsKey` rồi `put` trong test có nhiều threads, quan sát race và giải thích tại sao phải thay bằng atomic claim.
6. Thiết kế record `Outcome(operationId,state,status,receipt,error)` để ứng dụng có UNKNOWN/PENDING/COMPLETED/FAILED thay vì boolean.
7. Thêm `GET /operations/{id}` cho local server (phải xác thực principal trong phiên bản thực) và viết client poll sau khi mất response.
8. Thiết kế schema SQL có `UNIQUE(tenant_id,operation_type,idempotency_key)`, giao dịch ghi effect + result cùng DB và kiểm thử conflict/concurrency/crash.
9. Mô phỏng gateway đã charge nhưng server crash trước COMPLETED; thiết kế downstream idempotency, outbox và reconciliation.
10. Viết retry policy cho 429/503/timeout với exponential backoff + jitter và max total deadline; giữ key và payload.
11. Thiết kế retention/TTL của cache kết quả khác với ledger bền vững, tránh retry sau expiry gây giao dịch trùng.
12. Kiểm thử hai tenant dùng cùng chuỗi key nhưng không được đọc/chồng kết quả của nhau.
13. Đổi fingerprint từ chuỗi thô thành JSON canonicalization + SHA-256; đảm bảo thay đổi thứ tự thuộc tính JSON không tạo conflict giả.
14. Viết fault-injection matrix trước/sau transaction commit, trước/sau HTTP response và trước/sau downstream call, phân biệt khả năng khôi phục.

## Tài liệu chuẩn

- [RFC 9110 `9.2.2 — HTTP Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110#section-9.2.2): semantics idempotency, PUT/DELETE/safe methods và retry khi communication failure.
- [`HttpClient` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `send`, `sendAsync`, IO failures và cancellation.
- [`HttpRequest` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): request header, timeout, body publisher.
- [`HttpResponse` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): status, headers, body.
- [`CompletableFuture` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): completion, cancel, whenComplete, allOf.
- [`ConcurrentHashMap` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): atomic per-key compute trong bộ nhớ.
- [`HttpServer` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): HTTP server loopback của demo.
