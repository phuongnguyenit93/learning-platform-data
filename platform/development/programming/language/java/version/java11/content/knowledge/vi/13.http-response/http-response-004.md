# Xử lý status nghiệp vụ thay vì chỉ dựa vào lỗi I/O (Java 11)

Khi dùng `java.net.http.HttpClient` của **Java 11**, một lời gọi HTTP có thể **được gửi và nhận thành công ở tầng mạng** nhưng server trả `404`, `409`, `429` hoặc `503`. Tương tự, server có thể trả **`200 OK`** trong khi body ghi rằng giao dịch bị từ chối, đơn hàng chưa được phê duyệt hoặc một công việc chỉ đang chờ xử lý. Bắt riêng `IOException` **không đủ** để quyết định nghiệp vụ thành công hay thất bại.

Nguyên tắc của bài:

> **Lỗi I/O**, **HTTP status** và **trạng thái nghiệp vụ trong response body** là ba tín hiệu khác nhau. Đọc, kiểm tra và ánh xạ mỗi tín hiệu theo hợp đồng API trước khi trả kết quả cho ứng dụng.

Chủ đề nằm trong nhóm **HTTP Response** của Java 11. Các API được dùng trong bài vẫn có giá trị với JDK được bảo trì hiện nay. Có thể sử dụng JDK LTS còn được cập nhật và biên dịch bằng `javac --release 11` khi compiler còn hỗ trợ mức Java 11. Bài không dựa vào cơ chế lỗi thời hoặc những cú pháp Java mới hơn Java 11.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt lỗi kết nối/đọc phản hồi với một phản hồi HTTP có mã status cụ thể.
2. Dùng `HttpResponse.statusCode()` để kiểm tra hợp đồng endpoint, không đoán từ `try/catch`.
3. Hiểu vì sao `BodyHandlers.ofString()` **không tự diễn giải** `4xx/5xx`.
4. Phân biệt ba trạng thái: **HTTP thành công**, **nghiệp vụ hoàn tất** và **tác vụ chỉ được tiếp nhận để xử lý tiếp**.
5. Xây API gateway ánh xạ status HTTP và payload thành kiểu kết quả nghiệp vụ rõ ràng.
6. Phân loại `IOException`, `InterruptedException`, lỗi HTTP, lỗi schema và trạng thái nghiệp vụ bị từ chối.
7. Viết test các tình huống `200`, `202`, `404`, `409`, `503` và lỗi mạng mà không kết nối Internet.
8. Đặt retry, timeout, logging và giới hạn response body đúng tầng, không che lỗi nghiêm trọng bằng giá trị mặc định.

## 2. Ba lớp kết quả của một lần gọi API

Giả sử ứng dụng hỏi trạng thái đơn hàng từ một API đối tác.

| Tầng | Điều được trả lời | Ví dụ | Ý nghĩa với ứng dụng |
| --- | --- | --- | --- |
| **Transport/I/O** | Có gửi request và nhận response về hay không? | `IOException` do kết nối thất bại | Chưa đủ dữ liệu khẳng định trạng thái nghiệp vụ |
| **HTTP protocol/status** | Server nói gì về request theo HTTP? | `200 OK`, `404 Not Found`, `503 Service Unavailable` | Cần diễn giải theo endpoint |
| **Business outcome** | Đơn hàng đã được duyệt, từ chối hay đang chờ? | `APPROVED`, `DECLINED`, `PENDING` trong payload thành công | Kết quả thực sự mà use case cần |

Ví dụ các tình huống riêng biệt:

```text
Tình huống A: Kết nối bị lỗi
    -> IOException
    -> Không có HttpResponse để đọc statusCode()

Tình huống B: Có HTTP response 503
    -> Không nhất thiết có IOException
    -> response.statusCode() == 503
    -> Gateway phân loại "dịch vụ đối tác chưa sẵn sàng"

Tình huống C: HTTP 200, body "DECLINED|insufficient_stock"
    -> HTTP request đã xử lý và phản hồi hợp lệ
    -> Business outcome: đơn hàng bị từ chối

Tình huống D: HTTP 202 Accepted
    -> Server đã tiếp nhận request
    -> Chưa đồng nghĩa công việc đã hoàn tất
```

**Hai chữ “success” không phải một:** thành công khi **trao đổi HTTP** không kéo theo thành công của **use case**. Đây là một trong những lỗi logic hay gặp nhất ở các client tích hợp payment, order, booking và workflow.

### Không suy luận nghiệp vụ từ status nếu chưa xem hợp đồng

Một API có thể mã hóa từ chối nghiệp vụ là `409 Conflict` hoặc `422 Unprocessable Content`, trong khi API khác dùng `200` với field `success=false` hoặc `status="REJECTED"`. Không có quy tắc chung bắt mọi đối tác dùng cùng một cách. Gateway phải biết **hợp đồng endpoint** và ánh xạ rõ ràng.

## 3. Java 11 `HttpClient` thực sự trả gì?

Phần lõi của giao tiếp đồng bộ:

```java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));

int httpStatus = response.statusCode();
String responseBody = response.body();
```

Đây là **đoạn mã bên trong một phương thức** đã có `HttpClient client`, `HttpRequest request`, imports `HttpResponse` và `StandardCharsets`, đồng thời xử lý `IOException`/`InterruptedException`. Nó không phải chương trình độc lập.

Trong Java 11:

- `HttpClient.send(request, bodyHandler)` có thể **ném `IOException`** nếu có lỗi gửi/nhận I/O.
- `send` cũng có thể **ném `InterruptedException`** khi thread bị ngắt trong lúc chờ.
- Nếu server gửi response `404`/`409`/`503` và quá trình HTTP hoàn tất bình thường, lời gọi **có thể trả `HttpResponse`**; đó không tự động là `IOException`.
- `HttpResponse.statusCode()` trả về mã HTTP dưới dạng `int`.
- `HttpResponse.body()` trả kiểu `T` tùy `BodyHandler<T>`, ví dụ `String`, `byte[]`, `InputStream` hoặc `Void`.
- Các `BodyHandlers` chuẩn **không kiểm tra HTTP status để từ chối body**. Chẳng hạn `BodyHandlers.ofString(UTF_8)` sẽ nhận nội dung như một `String` kể cả khi server trả `400` hoặc `500`.

Vì vậy, cấu trúc:

```java
try {
    HttpResponse<String> response =
            client.send(request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

    // CHƯA thể kết luận thành công nghiệp vụ ở đây.
} catch (IOException ex) {
    // Đây là lỗi I/O, không phải nơi xử lý mọi HTTP 4xx/5xx.
}
```

chỉ minh họa **bước transport**. Phải kiểm tra response sau khi nhận. Đoạn mã này cũng cần `InterruptedException` được xử lý hoặc khai báo; nó **không phải chương trình độc lập**.

### HTTP 200 chưa chắc payload hợp lệ

Ngay cả khi response trả `200`, body có thể rỗng, sai JSON, thiếu field bắt buộc, sai kiểu, chứa mã nghiệp vụ không nhận diện hoặc không khớp ID đã yêu cầu. Đây là **lỗi hợp đồng/dữ liệu**, không nên gộp nhầm với sự kiện server không tìm thấy resource hoặc với lỗi mạng.

## 4. Chính sách diễn giải HTTP status

Mỗi API gateway nên định nghĩa **bảng quyết định theo endpoint** thay vì dùng chung một quy tắc cứng cho toàn bộ HTTP Client.

| Status / sự kiện | HTTP nói gì? | Hướng xử lý có thể phù hợp |
| --- | --- | --- |
| `200 OK` | HTTP request thành công và có thể có representation | Decode, validate payload; **kiểm tra business status** |
| `201 Created` | Tài nguyên đã được tạo | Đọc `Location`, ID hoặc body theo hợp đồng; không ép mọi response thành `200` |
| `202 Accepted` | Yêu cầu đã được tiếp nhận, xử lý có thể chưa xong | Trả **PENDING/ACCEPTED**, hoặc theo dõi trạng thái bằng job ID |
| `204 No Content` | Thành công, response không có content | Đừng parse JSON rỗng; map sang kết quả theo hợp đồng |
| `304 Not Modified` | Kết quả điều kiện/cache | Cần logic caching; không coi như một entity mới |
| `400 Bad Request` | Request sai cú pháp/giá trị theo API | Lỗi validation/integration |
| `401 Unauthorized` | Cần xác thực hợp lệ | Lỗi authorization/authentication; tránh lộ token |
| `403 Forbidden` | Không được phép thực hiện | Báo lỗi quyền; không retry mù |
| `404 Not Found` | Tài nguyên không được tìm thấy | Có thể trả `NOT_FOUND` nếu endpoint quy định; nơi khác có thể là lỗi |
| `409 Conflict` | Xung đột với trạng thái server | Có thể chuyển thành trạng thái nghiệp vụ `CONFLICT` nếu contract quy định |
| `422 Unprocessable Content` | Server hiểu request nhưng không xử lý được theo ngữ nghĩa | Có thể chứa lỗi validation nghiệp vụ theo schema |
| `429 Too Many Requests` | Vượt giới hạn tốc độ | Áp quota, `Retry-After` và backoff có ngân sách |
| `500/502/503/504` | Lỗi phía server/gateway | Báo remote-service failure; retry chọn lọc khi an toàn |
| `IOException` | Lỗi I/O hoặc kết nối, có thể chưa nhận response | Phân loại **TRANSPORT_FAILURE**, không tự bịa HTTP status |
| `InterruptedException` | Thread chờ bị ngắt | Bảo toàn interrupt flag và chuyển cho caller xử lý |
| Body sai định dạng trong `200` | HTTP thành công nhưng dữ liệu sai hợp đồng | Báo **BAD_PAYLOAD/CONTRACT_FAILURE**, không trả kết quả giả |

Một số endpoint có hợp đồng riêng: ví dụ `404` khi tra cứu tài khoản có thể nghĩa “không tồn tại”, nhưng `404` từ API cấp phép cấu hình sai lại là lỗi hệ thống. Khi cần dựa trên `statusCode()`, hãy ghi **điều kiện phù hợp cho endpoint cụ thể**, không kết luận từ status code một cách máy móc.

## 5. Thiết kế ranh giới: HTTP → gateway → domain

Tách trách nhiệm giúp code test được mà không cần gọi mạng:

```text
OrderService (nghiệp vụ)
     |
     v
OrderGateway.find(orderId)
     |
     |-- HttpTransport.get(uri)
     |       |-- HttpClient.send(...)      (gửi HTTP thật)
     |       '-- RawHttpResponse(status, body)
     |
     |-- HTTP status policy               (200, 202, 404, 503 ...)
     |
     |-- Payload decoder/validator        ("APPROVED|paid", JSON ...)
     |
     '-- BusinessResult(Decision, detail)
     |
     v
OrderService biết APPROVED / DECLINED / PENDING / NOT_FOUND
```

**Các ranh giới quan trọng:**

1. **Transport** hiểu `HttpRequest`, `HttpResponse`, timeout, charset, I/O exception, nhưng không cần biết `orderStatus` hay ý nghĩa `DECLINED`.
2. **Gateway** hiểu hợp đồng endpoint và cả HTTP status lẫn schema body.
3. **Mapper/decoder** biến body thành kiểu dữ liệu đã xác thực, không thực hiện HTTP call.
4. **Application service** xử lý kết quả nghiệp vụ; không đọc chuỗi HTTP status ở khắp codebase.

Với ứng dụng nhỏ, gateway và mapper có thể cùng một class; không cần tạo quá nhiều tầng không cần thiết. Giá trị chính là **đặt quy tắc status ở một nơi xác định**, không trộn vào code màn hình hoặc handler nghiệp vụ.

## 6. Chương trình Java 11 hoàn chỉnh: HTTP 200 có thể bị từ chối nghiệp vụ

Ví dụ dưới đây mô phỏng API đơn hàng. Nó dùng response text đơn giản `APPROVED|paid`, `DECLINED|insufficient_stock` hoặc `PENDING|manual_review` để không phải cài một thư viện JSON ngoài Java SE. **Đây là giao thức minh họa**, không phải lời khuyên parse payload thật bằng dấu `|`. Với JSON thực tế, dùng JSON decoder chuẩn còn được bảo trì và kiểm tra schema.

Chương trình cũng có một adapter `JdkHttpTransport` dùng `java.net.http.HttpClient` thật, nhưng `main` **inject fake transport** để toàn bộ ví dụ chạy offline và cho stdout xác định.

Tạo file **`BusinessStatusDemo.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class BusinessStatusDemo {

    enum Decision {
        APPROVED, DECLINED, PENDING, NOT_FOUND
    }

    static final class BusinessResult {
        final Decision decision;
        final String detail;

        BusinessResult(Decision decision, String detail) {
            this.decision = decision;
            this.detail = detail;
        }
    }

    // Response ở tầng HTTP, chưa phải kết quả nghiệp vụ.
    static final class RawHttpResponse {
        final int statusCode;
        final String body;

        RawHttpResponse(int statusCode, String body) {
            this.statusCode = statusCode;
            this.body = body;
        }
    }

    interface HttpTransport {
        RawHttpResponse get(URI uri)
                throws IOException, InterruptedException;
    }

    // Adapter thật: trả status và body, không tự kết luận đơn hàng.
    static final class JdkHttpTransport implements HttpTransport {
        private final HttpClient client;

        JdkHttpTransport(HttpClient client) {
            this.client = Objects.requireNonNull(client, "client");
        }

        @Override
        public RawHttpResponse get(URI uri)
                throws IOException, InterruptedException {
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(3))
                    .header("Accept", "text/plain")
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            return new RawHttpResponse(
                    response.statusCode(), response.body());
        }
    }

    // Fake transport: không kết nối mạng, tạo được nhiều nhánh test.
    static final class FakeHttpTransport implements HttpTransport {
        private final Map<String, RawHttpResponse> responses =
                new HashMap<>();

        FakeHttpTransport reply(
                String path, int httpStatus, String body) {
            responses.put(path,
                    new RawHttpResponse(httpStatus, body));
            return this;
        }

        @Override
        public RawHttpResponse get(URI uri) throws IOException {
            if ("/orders/6".equals(uri.getPath())) {
                throw new IOException("Simulated network outage");
            }

            RawHttpResponse response =
                    responses.get(uri.getPath());

            if (response == null) {
                throw new IOException("Missing fake response");
            }
            return response;
        }
    }

    static final class TransportFailure
            extends RuntimeException {
        TransportFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class RemoteHttpStatus
            extends RuntimeException {
        final int statusCode;

        RemoteHttpStatus(int statusCode) {
            super("Unexpected remote HTTP status: " + statusCode);
            this.statusCode = statusCode;
        }
    }

    static final class BadPayload extends RuntimeException {
        BadPayload(String message) {
            super(message);
        }
    }

    // Gateway: diễn giải cả HTTP status và business status.
    static final class OrderGateway {
        private final HttpTransport transport;
        private final URI baseUri;

        OrderGateway(HttpTransport transport, URI baseUri) {
            this.transport = Objects.requireNonNull(
                    transport, "transport");
            this.baseUri = Objects.requireNonNull(
                    baseUri, "baseUri");
        }

        BusinessResult find(int orderId) {
            if (orderId <= 0) {
                throw new IllegalArgumentException(
                        "orderId must be positive");
            }

            RawHttpResponse response;
            try {
                URI uri = baseUri.resolve("orders/" + orderId);
                response = transport.get(uri);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new TransportFailure(
                        "Request interrupted", ex);
            } catch (IOException ex) {
                throw new TransportFailure(
                        "I/O failure", ex);
            }

            if (response.statusCode == 404) {
                return new BusinessResult(
                        Decision.NOT_FOUND, "missing");
            }
            if (response.statusCode == 202) {
                return new BusinessResult(
                        Decision.PENDING, "accepted");
            }
            if (response.statusCode != 200) {
                throw new RemoteHttpStatus(
                        response.statusCode);
            }

            return parseBusinessStatus(response.body);
        }

        private BusinessResult parseBusinessStatus(String body) {
            if (body == null) {
                throw new BadPayload("Missing response body");
            }

            int separator = body.indexOf('|');
            if (separator <= 0
                    || separator == body.length() - 1
                    || body.indexOf('|', separator + 1) >= 0) {
                throw new BadPayload("Malformed response body");
            }

            String code = body.substring(0, separator).strip();
            String detail = body.substring(separator + 1).strip();
            if (detail.isEmpty()) {
                throw new BadPayload("Missing detail");
            }

            switch (code) {
                case "APPROVED":
                    return new BusinessResult(
                            Decision.APPROVED, detail);
                case "DECLINED":
                    return new BusinessResult(
                            Decision.DECLINED, detail);
                case "PENDING":
                    return new BusinessResult(
                            Decision.PENDING, detail);
                default:
                    throw new BadPayload(
                            "Unsupported business status: " + code);
            }
        }
    }

    private static String describe(OrderGateway gateway, int id) {
        try {
            BusinessResult result = gateway.find(id);
            return id + ": " + result.decision
                    + " / " + result.detail;
        } catch (RemoteHttpStatus ex) {
            return id + ": HTTP_ERROR / " + ex.statusCode;
        } catch (TransportFailure ex) {
            return id + ": TRANSPORT_ERROR / " + ex.getMessage();
        } catch (BadPayload ex) {
            return id + ": BAD_PAYLOAD / " + ex.getMessage();
        }
    }

    public static void main(String[] args) {
        FakeHttpTransport fake = new FakeHttpTransport()
                .reply("/orders/1", 200, "APPROVED|paid")
                .reply("/orders/2", 200,
                        "DECLINED|insufficient_stock")
                .reply("/orders/3", 200,
                        "PENDING|manual_review")
                .reply("/orders/4", 404, "not found")
                .reply("/orders/5", 503, "service unavailable")
                .reply("/orders/7", 200, "UNKNOWN|unexpected")
                .reply("/orders/8", 202, "")
                .reply("/orders/9", 409, "conflict");

        OrderGateway gateway = new OrderGateway(
                fake, URI.create("https://api.example.invalid/"));

        for (int id = 1; id <= 9; id++) {
            System.out.println(describe(gateway, id));
        }
    }
}
```

### Lệnh chạy

Dùng JDK hiện hành còn được cập nhật, có `javac` hỗ trợ `--release 11`:

```sh
javac --release 11 -encoding UTF-8 BusinessStatusDemo.java
java BusinessStatusDemo
```

**Stdout xác định của chương trình:**

```text
1: APPROVED / paid
2: DECLINED / insufficient_stock
3: PENDING / manual_review
4: NOT_FOUND / missing
5: HTTP_ERROR / 503
6: TRANSPORT_ERROR / I/O failure
7: BAD_PAYLOAD / Unsupported business status: UNKNOWN
8: PENDING / accepted
9: HTTP_ERROR / 409
```

`main` không thực hiện bất kỳ kết nối HTTP thật nào. Dữ liệu được lấy qua `FakeHttpTransport` và URI có domain `.invalid`, được dùng làm tên minh họa. Vì vậy, demo không phụ thuộc tài khoản, API đối tác, DNS hoặc Internet.

### Giải thích 9 trường hợp

| ID | Giả lập response/sự kiện | Kết quả nghiệp vụ hoặc lỗi | Vì sao? |
| --- | --- | --- | --- |
| 1 | HTTP `200`, `APPROVED|paid` | `APPROVED` | Cả HTTP contract và business payload hợp lệ |
| 2 | HTTP `200`, `DECLINED|insufficient_stock` | `DECLINED` | **HTTP 200 nhưng nghiệp vụ từ chối** |
| 3 | HTTP `200`, `PENDING|manual_review` | `PENDING` | Đang chờ kiểm tra, chưa hoàn tất |
| 4 | HTTP `404` | `NOT_FOUND` | Hợp đồng tra cứu ví dụ quy định 404 nghĩa là không tìm thấy |
| 5 | HTTP `503` | `HTTP_ERROR / 503` | Đã có response HTTP nhưng server chưa phục vụ |
| 6 | `IOException` giả lập | `TRANSPORT_ERROR` | Không nhận được response hợp lệ để đọc status |
| 7 | HTTP `200`, mã `UNKNOWN` | `BAD_PAYLOAD` | Dữ liệu vi phạm hợp đồng các mã nghiệp vụ được nhận |
| 8 | HTTP `202` | `PENDING` | Server mới tiếp nhận yêu cầu |
| 9 | HTTP `409` | `HTTP_ERROR / 409` | Gateway mẫu chưa có quy tắc chuyển `409` thành một business result |

Ba đường đi **2, 5 và 6** là trọng tâm: không thể dùng một `catch(IOException)` duy nhất để phân biệt nghiệp vụ từ chối, HTTP lỗi và mất kết nối.

### Những nguyên tắc code đáng chú ý

**`JdkHttpTransport`** làm HTTP thực tế: tạo request, áp timeout, nhận response string và status. Nó **không biết** một chuỗi `DECLINED` có nghĩa gì.

**`OrderGateway`** biết hợp đồng cụ thể: `404` → `NOT_FOUND`, `202` → `PENDING`, `200` → decode business status, còn status khác → `RemoteHttpStatus`. Với API khác, các quy tắc phải thay theo tài liệu đối tác.

**`parseBusinessStatus`** là mapper thuần dữ liệu. Nó kiểm tra dấu phân cách, giá trị không rỗng và mã `APPROVED/DECLINED/PENDING`. Mã lạ gây `BadPayload` thay vì âm thầm gán thành `APPROVED`.

**`TransportFailure`** bọc `IOException` và `InterruptedException`, nhưng lưu **cause**. Khi bắt interruption, code khôi phục interrupt flag bằng `Thread.currentThread().interrupt()`.

**`describe`** chỉ chuyển các kết quả thành dòng minh họa. Trong ứng dụng thực, UI hoặc service nên nhận các kiểu kết quả và ngoại lệ đã phân loại, không tự parse chuỗi log.

## 7. Thay fake bằng `HttpClient` thật

Sau khi có HTTP server thực được phép truy cập, có thể tạo client và inject adapter:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

HttpTransport transport = new JdkHttpTransport(client);

OrderGateway gateway = new OrderGateway(
        transport, URI.create("https://partner.example/"));
```

Đoạn này **không phải chương trình độc lập**: các interface/class `HttpTransport`, `JdkHttpTransport` và `OrderGateway` nằm trong chương trình ở phần 6. Thay URI minh họa bằng endpoint thực, xác nhận policy TLS/auth, body schema, timeout và hợp đồng HTTP của đối tác.

Khi thay transport, **gateway và domain không phải viết lại logic mạng**. Chỉ cần bảo đảm format body mà mapper nhận đúng với API thật. Trong sản phẩm thực tế, payload thường là JSON và cần JSON parser/schema phù hợp, không dùng `|` để phân tích dữ liệu tùy ý.

### Vì sao tách `RawHttpResponse` khỏi domain?

Một `HttpResponse<String>` chứa nhiều chi tiết HTTP như status, headers, request, URI và protocol version. Nếu service trực tiếp phụ thuộc `HttpResponse`, mọi nơi sẽ phải hiểu status code. `RawHttpResponse` trong ví dụ là loại dữ liệu trung gian cố ý nhỏ, đủ để gateway làm việc; `BusinessResult` mới là kiểu phù hợp với use case.

Nếu cần retry theo `Retry-After` hoặc lưu correlation ID, transport có thể chuyển **một tập headers được chọn** vào `RawHttpResponse`. Không truyền toàn bộ request/response nhạy cảm sâu vào domain một cách mặc định.

## 8. Dữ liệu JSON thực tế: hai lớp status thường tồn tại cùng lúc

Nhiều API trả JSON dạng:

```json
{
  "success": false,
  "code": "PAYMENT_DECLINED",
  "message": "Card rejected",
  "requestId": "req-123"
}
```

Payload trên có thể đi cùng HTTP `200`, `400` hoặc `422`, tùy hợp đồng. Khi thiết kế gateway, cần:

1. Xác định **status HTTP được chấp nhận** cho từng endpoint.
2. Kiểm tra `Content-Type` và cách mã hóa được quy định, thường là JSON UTF-8.
3. Decode JSON bằng thư viện parser hiện được bảo trì và kiểm tra schema (đúng kiểu `boolean`, `String`, field bắt buộc).
4. Diễn giải `success`/`code`/`status` thành enum hoặc kiểu kết quả nghiệp vụ.
5. Phân biệt **lỗi validation nghiệp vụ** với **lỗi contract** nếu dữ liệu trả về sai định dạng.
6. Không đưa nguyên message từ đối tác cho end user nếu chứa thông tin nhạy cảm hoặc chưa được duyệt nội dung.

`HttpClient` của Java 11 **không tự ánh xạ JSON sang domain object** chỉ vì dùng `BodyHandlers.ofString()`. Đoạn ví dụ `String body = response.body()` mới là bước giải mã bytes thành text; parse JSON và validate diễn ra sau đó.

### Ví dụ schema/policy

| HTTP status | JSON business fields | Gateway trả về |
| --- | --- | --- |
| `200` | `success=true` + entity hợp lệ | `APPROVED` hoặc domain entity |
| `200` | `success=false, code=PAYMENT_DECLINED` | `DECLINED`, **không** ném `IOException` |
| `200` | Thiếu `success` hoặc sai kiểu dữ liệu | `BAD_PAYLOAD / CONTRACT_FAILURE` |
| `202` | `jobId` và `status=QUEUED` | `PENDING` kèm job ID nếu hợp đồng quy định |
| `400` / `422` | Danh sách lỗi validation hợp lệ | Validation result có cấu trúc; không parse như entity thành công |
| `409` | `code=VERSION_CONFLICT` | Business conflict nếu hợp đồng quy định rõ |
| `503` | Response lỗi máy chủ | Remote service error; cân nhắc retry an toàn |

**Chú ý:** Ví dụ này không quy định một tiêu chuẩn chung cho mọi API. Nếu đối tác trả `success=false` trên HTTP `200`, phải dựa vào hợp đồng chứ không phỏng đoán.

### Khi nào response `200` nhưng vẫn cần báo lỗi?

Hai loại sự cố khác nhau:

- `200 + DECLINED` là một **kết quả nghiệp vụ có thể hoàn toàn hợp lệ**. Nó không nhất thiết là lỗi phần mềm.
- `200 + body sai JSON/schema` là **lỗi hợp đồng/dữ liệu**. Không thể tin tưởng để tiếp tục xử lý bình thường.

Một gateway tốt giúp service phân biệt hai loại mà không kiểm tra chuỗi ở nhiều nơi.

## 9. Phân biệt exception transport, HTTP và nghiệp vụ

Thiết kế exception/result nên làm rõ ai có thể xử lý trường hợp đó.

| Loại | Ví dụ | Phương án xử lý |
| --- | --- | --- |
| **Transport failure** | DNS lỗi, không kết nối được, lỗi đọc body | Báo dịch vụ tạm không sẵn sàng, log cause, retry có điều kiện |
| **Interruption/cancellation** | Thread bị ngắt trong `send` | Giữ interrupt flag, dừng/đưa lên caller theo yêu cầu |
| **Remote HTTP status** | `503`, `429`, `401`, `409` | Phân nhánh theo status + endpoint contract |
| **Business rejection** | `DECLINED`, `OUT_OF_STOCK`, `LIMIT_EXCEEDED` | Kết quả nghiệp vụ bình thường có thể hiển thị/giải thích |
| **Business pending** | `202 Accepted`, `status=PENDING` | Trả trạng thái chờ hoặc theo dõi job |
| **Contract/payload failure** | JSON sai, schema thiếu, mã lạ, ID mismatch | Báo lỗi tích hợp; không đoán dữ liệu |
| **Application input validation** | ID không dương, cấu hình URL không hợp lệ | Từ chối đầu vào trước khi gọi mạng |

Không cần mọi dự án phải tạo bảy subclass exception. Có thể dùng sealed outcome trong phiên bản Java mới, nhưng vì bài nhắm Java 11, ví dụ chỉ dùng **enum, lớp bình thường và exception** (tương thích `--release 11`). Điều quan trọng là **không trộn tất cả trạng thái vào cùng một `boolean success`** hoặc che mọi lỗi bằng `Optional.empty()`.

### Không nên bắt `Exception` rồi trả “thành công”

Phản ví dụ:

```java
try {
    return callPartner();
} catch (Exception ex) {
    return new OrderResult(true);
}
```

Đây chỉ là **phản ví dụ trong một phương thức**, không phải code được khuyến nghị. Nếu network timeout hoặc JSON sai mà phương thức trả `true`, ứng dụng sẽ hiểu sai trạng thái giao dịch. Trong các hệ thống có side effect hoặc tiền, sự nhầm lẫn này có thể gây lỗi nghiêm trọng.

Một default an toàn hơn là **phản ánh trạng thái chưa biết** và chuyển lỗi tới ranh giới xử lý phù hợp; không tự khẳng định giao dịch thất bại hay thành công nếu server có thể đã xử lý nhưng response thất lạc.

## 10. Kỹ thuật kiểm tra status và body đúng thứ tự

Cách làm minh họa trong API gateway:

```text
1. Gửi request.
2. Nếu không có response vì lỗi I/O:
      -> TRANSPORT_FAILURE
3. Nếu có response:
      -> Đọc statusCode().
4. Dựa trên hợp đồng:
      -> 200: decode body thành DTO, validate, map business result.
      -> 202: PENDING/ACCEPTED nếu endpoint cho phép.
      -> 204: không parse body thành entity; map theo contract.
      -> 404: NOT_FOUND hoặc ERROR tùy use case.
      -> 409/422: xem error payload có schema hợp lệ không.
      -> 429/503: phân loại remote failure, áp policy retry.
      -> status không được định nghĩa: ERROR/UNEXPECTED_STATUS.
5. Chuyển kết quả đã phân loại cho application service.
```

Một số lỗi có thể xảy ra khi giải mã body hoặc đọc stream sau khi đã biết headers/status. Chúng vẫn thuộc **transport/body processing** nếu là `IOException`; còn JSON parse failure là **dữ liệu/hợp đồng**. Khi dùng streaming `BodyHandler`, thời điểm lỗi có thể khác với `BodyHandlers.ofString()` vốn nhận toàn bộ text trước khi trả kết quả.

### Tại sao không dùng quy tắc “status nhỏ hơn 400 tức là thành công”?

Quy tắc `statusCode() < 400` bỏ sót các khác biệt quan trọng:

- `202` mới **tiếp nhận** yêu cầu; job chưa chắc hoàn tất.
- `204` không có response content để map thành DTO.
- `304` liên quan cơ chế cache/conditional request.
- `200` có thể mang kết quả nghiệp vụ `DECLINED`.

Có thể bắt đầu bằng phân loại nhóm status (2xx/4xx/5xx), nhưng **bước cuối phải là hợp đồng endpoint**. Đừng dùng phép kiểm tra thô như lời khẳng định hoàn thành use case.

## 11. Xử lý bất đồng bộ `sendAsync` mà vẫn phân loại được status

Java 11 cũng hỗ trợ `HttpClient.sendAsync`, trả `CompletableFuture<HttpResponse<T>>`. Trong chế độ này, response chứa HTTP `503` vẫn có thể làm future hoàn tất **bình thường** với đối tượng `HttpResponse`; đó không mặc định là exceptional completion.

Đoạn mã minh họa trong **lớp adapter** đã có `HttpClient client`, `HttpRequest request` và `mapResponse(...)`:

```java
CompletableFuture<BusinessResult> resultFuture =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8))
              .thenApply(response -> mapResponse(
                      response.statusCode(), response.body()));
```

Đây là **snippet minh họa, chưa phải chương trình độc lập**; `mapResponse` là phương thức của adapter do ứng dụng viết để diễn giải status và payload; cần import `CompletableFuture` và các kiểu HTTP.

Phân biệt:

- HTTP `503` trả response → `thenApply` **vẫn chạy**, nếu upstream future hoàn tất bình thường.
- `mapResponse` có thể quyết định ném `RemoteHttpStatus` → future phía sau kết thúc exceptionally với lỗi nghiệp vụ/tích hợp này.
- Lỗi mạng khiến future của `sendAsync` hoàn tất exceptionally; `thenApply` sẽ **không chạy** với một response giả.
- `future.join()` trên future lỗi thường ném `CompletionException` bọc cause; cần phân loại **nguyên nhân**, không chỉ in tên lớp bọc.

Một pattern xử lý lỗi bất đồng bộ minh họa:

```java
resultFuture.whenComplete((result, failure) -> {
    if (failure != null) {
        // Ghi nhận lỗi đã được phân loại; tránh log token/body nhạy cảm.
        return;
    }
    // Dùng result.decision để xử lý use case.
});
```

Đoạn này cũng **không phải chương trình độc lập**. `whenComplete` là callback quan sát kết quả; nếu cần biến lỗi thành một kiểu kết quả, dùng `handle`/`exceptionally` có chủ đích và giữ thông tin cause.

### Chọn executor cho mapping

Mapping đơn giản có thể dùng `thenApply`; nếu decode JSON nặng hoặc có bước CPU tốn thời gian, dùng `thenApplyAsync(..., executor)` với executor có giới hạn thích hợp. Không chạy logic nghiệp vụ dài hoặc blocking operation không kiểm soát trên thread xử lý HTTP. Cũng không dựa vào future cancellation để khẳng định server chưa xử lý request.

## 12. Timeout, retry và idempotency: đừng biến lỗi I/O thành giao dịch trùng

Lỗi I/O sau khi gửi request **không chứng minh server chưa xử lý**. Ví dụ client POST thanh toán, server đã nhận lệnh và cập nhật dữ liệu nhưng kết nối đứt trước khi response về. Nếu client tự gửi lại vô điều kiện, có thể tạo hai giao dịch.

Chính sách retry cần xét ít nhất:

1. **Method và side effect:** GET thường idempotent; POST có thể không. Không chỉ dựa trên HTTP status để retry.
2. **Lỗi nào:** `IOException`, `429`, `503` hoặc các mã khác theo hợp đồng. `400`/`401` thường cần sửa request hoặc credential thay vì retry vô hạn.
3. **Có idempotency key hay không:** nếu endpoint hỗ trợ, dùng key ổn định khi retry cùng một tác vụ.
4. **Số lần thử và deadline:** giới hạn số retry, backoff, jitter, tổng timeout và số request đang chờ.
5. **Quota/throttle:** đọc `Retry-After` khi phù hợp và không làm quá tải đối tác.
6. **Theo dõi trạng thái:** với `202` hoặc response bị mất sau khi server có thể đã xử lý, tìm cơ chế query status/correlation ID thay vì gửi lại một thao tác có side effect.

Ví dụ với `HttpRequest` trên Java 11:

```java
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(5))
        .header("Accept", "application/json")
        .GET()
        .build();
```

Đây là **snippet**, cần `uri` là `URI` hợp lệ và imports `HttpRequest`, `Duration`. Timeout được khai báo rõ, nhưng timeout **không tự quyết định** retry hay kết quả nghiệp vụ.

`HttpClient.Builder.connectTimeout` áp timeout thiết lập kết nối trong điều kiện cần mở kết nối mới; `HttpRequest.Builder.timeout` áp timeout cho request. Trong ứng dụng thực, cần xem thêm hạn xử lý toàn bộ use case, timeout proxy/server, giới hạn số kết nối, và thời gian chờ của future. Không có một con số mặc định phù hợp tất cả hệ thống.

## 13. Đọc error body đúng loại, không để body lớn phá hệ thống

Khi server trả `4xx/5xx`, body có thể là một JSON error object, HTML error page, văn bản, hoặc thậm chí rỗng. Không nên dùng mapper cho success entity để parse error body theo mặc định.

Ví dụ nếu body lỗi chứa:

```json
{
  "code": "RATE_LIMITED",
  "message": "Too many requests",
  "retryAfterSeconds": 15
}
```

thì gateway có thể diễn giải riêng một **ErrorDto** theo schema. Nhưng không tin tuyệt đối vào content từ server: message có thể thiếu, sai kiểu hoặc chứa dữ liệu không nên log/hiển thị nguyên văn. Cần dựa vào **status + schema + chính sách**.

### `BodyHandlers.ofString` không có sẵn giới hạn kích thước ứng dụng

`BodyHandlers.ofString(UTF_8)` thường tích lũy body thành `String`, nên có thể dùng đáng kể RAM với response lớn hoặc không tin cậy. Nếu API có khả năng trả dữ liệu lớn, cân nhắc `BodyHandlers.ofInputStream()` hoặc custom `BodyHandler`/`BodySubscriber` để đọc theo stream, áp giới hạn byte và đóng tài nguyên.

Không dùng `String.length()` để suy ra kích thước mạng: một ký tự Unicode có thể dùng nhiều byte UTF-8. Nếu giới hạn 1 MiB body, kiểm tra **số byte được đọc**. Với error body, có thể giới hạn phần lưu để log nhưng vẫn cần xử lý kết nối/stream theo chính sách của thư viện.

### Bảo mật thông tin trong lỗi

- Không log header `Authorization`, API key, cookie, access token hoặc thông tin thanh toán.
- Dùng request/correlation ID để hỗ trợ truy vết mà không ghi lại toàn bộ payload.
- Không hiển thị raw HTML error page từ đối tác trực tiếp cho người dùng.
- Đối với response lỗi, có thể log **status, endpoint đã làm sạch, duration, request ID, error category**, thay vì toàn bộ body.
- Nếu địa chỉ endpoint có thể được điều khiển từ bên ngoài, cần kiểm soát SSRF và redirect policy.

## 14. Tổ chức kiểu kết quả nghiệp vụ

Trong Java 11, một enum và class bất biến đủ để tạo result có ý nghĩa. Có thể chọn:

```java
enum Decision {
    APPROVED, DECLINED, PENDING, NOT_FOUND
}
```

Với use case đòi hỏi phân biệt nhiều trường hợp hơn, có thể dùng lớp kết quả chứa **loại trạng thái, dữ liệu, mã lỗi có cấu trúc, ID theo dõi và thời hạn**, nhưng chỉ giữ những trường cần thiết cho nghiệp vụ. Tùy domain:

- `APPROVED`: xử lý xong và hợp lệ.
- `DECLINED`: một quyết định nghiệp vụ đã xác nhận, không phải lỗi kỹ thuật.
- `PENDING`: cần tiếp tục theo dõi, không thể báo kết quả cuối.
- `NOT_FOUND`: không có đối tượng được tìm.
- `UNKNOWN`/**INDETERMINATE**: không biết kết quả do mất response hoặc contract failure — **không tự chuyển thành DECLINED**.

Một cách dễ gây nhầm là thiết kế duy nhất `boolean isSuccess()`. Khi cả `PENDING` và `DECLINED` tồn tại, một boolean không thể biểu diễn đủ thông tin cho retry, UX, metrics và các hành động tiếp theo.

### Có nên biến `404` thành `Optional.empty()`?

Chỉ khi endpoint đọc tài nguyên và domain thật sự hiểu “không tìm thấy” là một kết quả bình thường. Ở API xác minh trạng thái thanh toán, `404` có thể do transaction ID sai hoặc đồng bộ chưa xong; cần contract riêng. Không dùng `Optional.empty()` cho mọi `IOException`, `401`, `503` hoặc payload sai, vì sẽ che lỗi quan trọng.

## 15. Bộ test cần có

Ví dụ `BusinessStatusDemo` đã có 9 tình huống cố định. Trong dự án thật, mở rộng theo nhóm:

| Nhóm kiểm thử | Tình huống | Điều cần xác nhận |
| --- | --- | --- |
| Transport | DNS/network failure, socket timeout, connection reset | Chuyển thành `TRANSPORT_FAILURE`, giữ cause và metric |
| HTTP status | `200`, `201`, `202`, `204`, `404`, `409`, `429`, `503` | Mapping đúng contract endpoint |
| Payload thành công | JSON/schema hợp lệ, field null, sai kiểu, mã business lạ | Validator/mapper xác định kết quả hoặc contract failure |
| Kết quả nghiệp vụ | `APPROVED`, `DECLINED`, `PENDING` | Không nhầm HTTP 200 với “approved” |
| Lỗi error body | Empty body, HTML, JSON khác schema | Không parse như success entity, không lộ raw body |
| Interruption | Thread bị ngắt trong send | Bảo toàn tín hiệu và dừng hoặc propagate phù hợp |
| Retry | GET/POST, idempotency key, `429 Retry-After`, `503` | Chỉ retry khi an toàn, có giới hạn |
| Async | Future có response 503, future kết thúc exceptionally | `thenApply` và exceptional completion khác nhau |
| Contract | Đối tác đổi mã field/status | Test phát hiện drift sớm |
| Security | URL/token/header chứa bí mật | Đã loại bỏ dữ liệu nhạy cảm khỏi log |

**Chiến lược test:** unit test gateway bằng fake transport; unit test mapper thuần dữ liệu; integration test `JdkHttpTransport` với local/mock HTTP server; contract test với schema/fixture hoặc môi trường thử nghiệm được kiểm soát. Một fake transport **không chứng minh TLS, proxy, DNS hay HTTP/2 hoạt động**; đó là phạm vi của integration test.

## 16. Những lỗi phổ biến

**Lỗi 1 — Chỉ dùng `catch(IOException)` để nhận biết mọi thất bại.** `4xx/5xx` thường vẫn trả `HttpResponse`. Cần đọc `statusCode()`.

**Lỗi 2 — Coi `statusCode() == 200` là đơn hàng đã được duyệt.** `200` chỉ nói request xử lý thành công theo HTTP. Body có thể là `DECLINED` hoặc `PENDING`.

**Lỗi 3 — Parse tất cả body như success DTO.** Error body thường có schema khác. Chọn parser/mapping theo status và endpoint.

**Lỗi 4 — Coi `202 Accepted` là giao dịch xong.** Nó có thể chỉ cho biết đã xếp hàng xử lý. Cần chờ/kiểm tra trạng thái bằng job ID khi hợp đồng yêu cầu.

**Lỗi 5 — Dùng `Optional.empty()` cho cả network failure, 404, 503 và body lỗi.** Mất khả năng phân biệt not found với hệ thống gặp sự cố.

**Lỗi 6 — Tự retry POST sau timeout.** Server có thể đã xử lý yêu cầu. Kiểm soát idempotency và trạng thái trước khi gửi lại.

**Lỗi 7 — Quên `InterruptedException`.** Khi chuyển ngoại lệ, có thể cần gọi `Thread.currentThread().interrupt()` để không làm mất tín hiệu.

**Lỗi 8 — Xử lý `sendAsync` như `send`.** Future lỗi cần quan sát exceptional completion; HTTP status 503 có thể vẫn là normal completion với response.

**Lỗi 9 — Cho rằng `BodyHandlers.ofString()` có thể tự parse JSON hoặc từ chối `4xx`.** Nó chỉ tạo `String` từ bytes, không áp business policy.

**Lỗi 10 — Không kiểm tra enum/mã status nghiệp vụ lạ.** Đối tác có thể thêm status mới; không gán mặc định thành `APPROVED`.

**Lỗi 11 — Tưởng `204 No Content` luôn mang body thành công có thể parse.** Status này không có response content; xử lý theo hợp đồng.

**Lỗi 12 — Quên giới hạn kích thước response.** Body quá lớn có thể gây áp lực bộ nhớ. Với nguồn không tin cậy, phải xác lập budget.

**Lỗi 13 — Logging toàn bộ response lỗi.** Có thể lộ token/PII hoặc dữ liệu bảo mật. Ghi metadata cần thiết, redaction.

**Lỗi 14 — Viết business HTTP policy lặp lại trong mọi service.** Mỗi nơi xử lý khác nhau, khó bảo trì. Tập trung ở gateway và test theo contract.

## 17. Bài tập thực hành

### Bài 1 — Phân biệt tầng lỗi

Với các tình huống sau, xác định **transport**, **HTTP status** hay **business outcome**:

1. `HttpClient.send` ném `IOException`.
2. Response `503` với body “Service unavailable”.
3. Response `200` với body `DECLINED|insufficient_stock`.
4. Response `200` với body không parse được.
5. Response `202` với job ID.

Gợi ý: mỗi tình huống có thể cần xử lý khác nhau; **không** gom cả năm thành cùng một `false`.

### Bài 2 — Mở rộng `FakeHttpTransport`

Thêm các tình huống:

- `/orders/10` → HTTP `200`, body `APPROVED|`: phải báo `BAD_PAYLOAD` do thiếu detail.
- `/orders/11` → HTTP `204`, body rỗng: quyết định rõ hợp đồng; với gateway demo hiện tại, status không được chấp nhận nên báo `HTTP_ERROR`/unexpected status.
- `/orders/12` → HTTP `200`, body `"DECLINED|limit_exceeded"`: phải trả `DECLINED`, không ném `IOException`.
- `/orders/13` → HTTP `429`: báo trạng thái remote rate limit; nếu triển khai retry, cần chính sách backoff và giới hạn.

### Bài 3 — JSON thật và domain enum

Giả sử API trả:

```json
{
  "orderId": 7,
  "status": "DECLINED",
  "reason": "OUT_OF_STOCK"
}
```

Thiết kế DTO, JSON decoder và mapper từ `status` string sang enum nghiệp vụ. Kiểm tra `orderId` khớp request, status lạ, null và thiếu field. Không sửa tầng `JdkHttpTransport` để nó biết một trạng thái domain mới.

### Bài 4 — Tạo status policy cho một endpoint khác

Endpoint tìm khách hàng có `404` nghĩa là không tồn tại, `200` trả customer, `503` báo dịch vụ tạm ngừng. Thiết kế mapping sang `Optional<Customer>` hoặc loại kết quả tường minh. Vì sao không thể trả `Optional.empty()` cho `503`?

### Bài 5 — Xử lý async

Với `sendAsync`, mô tả sự khác nhau giữa:
- future hoàn tất bình thường với response `503`;
- future hoàn tất exceptionally do `IOException`;
- response `200` hợp lệ HTTP nhưng mapper ném `BadPayload`.

Chỉ ra vị trí `thenApply` và `whenComplete` được dùng, và cách lấy cause từ `CompletionException`.

### Bài 6 — Lập kế hoạch retry

Một lệnh tạo thanh toán dùng POST; client timeout trước khi nhận response. Đề xuất cơ chế idempotency key, query status, giới hạn retry, và cách giao diện hiển thị trạng thái **chưa xác định** mà không tự báo “thất bại” hay “thành công”.

### Checklist hoàn thành

- [ ] Biết `IOException` không đồng nghĩa mọi mã HTTP lỗi.
- [ ] Đọc và diễn giải `HttpResponse.statusCode()` theo hợp đồng endpoint.
- [ ] Không xem `200 OK` là bằng chứng business outcome đã được chấp thuận.
- [ ] Phân biệt `202 Accepted`/`204 No Content` với response entity hoàn chỉnh.
- [ ] Không dùng `BodyHandlers.ofString()` như JSON mapper.
- [ ] Chạy được `BusinessStatusDemo.java` trên JDK tương thích Java 11 và đối chiếu 9 dòng output.
- [ ] Có fake tests cho HTTP error, transport error, business reject, pending và bad payload.
- [ ] Hiểu việc khôi phục interrupt flag, async exceptional completion và retry idempotency.
- [ ] Không che lỗi mạng bằng `Optional.empty()` hoặc tự suy ra transaction đã thất bại.
- [ ] Áp timeout, giới hạn body, validate schema và log có redaction.

## 18. Tài liệu tham khảo chính thức

1. [Java SE 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): `send`, `sendAsync`, `IOException`, `InterruptedException` và kiểu response.
2. [Java SE 11 — HttpResponse](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html): `statusCode()`, `headers()`, `body()`.
3. [Java SE 11 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): các handler chuẩn, đặc biệt chú ý chúng **không kiểm tra HTTP status**.
4. [Java SE 11 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): URI, method, headers, request timeout.
5. [Java SE 11 — CompletableFuture](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletableFuture.html): xử lý các bước async và future hoàn tất lỗi.
6. [Java SE 25 — HttpClient](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.html): xác nhận những API HTTP tiêu chuẩn tiếp tục có trên JDK LTS hiện đại.

**Kết luận:** đừng để `catch(IOException)` quyết định trạng thái nghiệp vụ. Với Java 11 HTTP Client, hãy **phân biệt lỗi I/O với HTTP status**, sau đó **diễn giải payload theo hợp đồng API** để trả một business outcome tường minh. Có HTTP `200` không đồng nghĩa nghiệp vụ được duyệt; có HTTP `503` không đồng nghĩa client đã ném ngoại lệ; và một lần timeout không đủ để khẳng định server chưa thực hiện thao tác.