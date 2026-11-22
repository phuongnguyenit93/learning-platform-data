# Chọn BodyHandler theo status và header thay vì mặc định nhận mọi body trong Java HttpClient

## 1. Vấn đề: không phải HTTP response body nào cũng nên tải vào bộ nhớ

Khi gọi Java `HttpClient`, cách viết phổ biến nhất là:

~~~java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
~~~

Nó thuận tiện cho những response nhỏ và đáng tin. Nhưng nếu server trả **404 kèm một trang HTML rất dài**, **200 kèm file nhị phân lớn**, **204 không có nội dung**, hoặc **200 với `Content-Type` không đúng định dạng ứng dụng cần**, thì có nên mặc định gom tất cả byte vào một `String`?

**Không.** Java 17 cung cấp `HttpResponse.BodyHandler<T>` để ứng dụng **chọn cách nhận body dựa trên status code và response headers ngay sau khi header đến, trước khi đọc body**. Đây là điểm đặc biệt giúp tách **quyết định có nhận/chuyển đổi/ghi file/loại bỏ body hay không** khỏi công việc thực sự tiêu thụ các byte.

~~~text
HttpClient gửi HttpRequest
              |
              v
HTTP response: status + headers đã nhận
              |
              v
BodyHandler<T>.apply(ResponseInfo info)
   |                |                      |
   | 200 + text     | 404/204/304          | 200 + binary
   v                v                      v
BodySubscriber      BodySubscriber         BodySubscriber
.ofString(UTF_8)    .replacing(...)        .ofFile(...) / .ofInputStream()
   |                |                      |
   v                v                      v
String/typed T      không giữ body         file/stream/typed T
              \       |                    /
               \      |                   /
                v     v                  v
                 HttpResponse<T>
~~~

Tức là `BodyHandler` là **bộ chọn chiến lược**, còn `BodySubscriber` mới là **người tiêu thụ bytes từ luồng HTTP**. BodyHandler không phải nơi đã có body để parse JSON, không nên gọi database hay chờ tác vụ nặng.

Bài này thuộc **Java Advance - networking → Nội dung HTTP**, tập trung vào đề bài **“Chọn BodyHandler theo status và header thay vì mặc định nhận mọi body”**, không đi sâu vào viết HTTP parser hay tự xây HTTP stack.

## 2. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt `HttpResponse.BodyHandler<T>`, `HttpResponse.ResponseInfo`, `HttpResponse.BodySubscriber<T>` và `HttpResponse<T>`.
2. Biết **thời điểm** callback `BodyHandler.apply()` nhận status, headers, version và vì sao chưa đọc body.
3. Chọn bỏ qua body bằng `BodySubscribers.replacing(value)` hoặc `discarding()` thay vì vô điều kiện `BodyHandlers.ofString()` / `ofByteArray()`.
4. Kiểm tra `statusCode()`, `Content-Type`, `Content-Length`, trạng thái không có content và quy tắc HTTP trước khi chọn `BodySubscriber`.
5. Dùng `BodySubscribers.mapping()` để các nhánh khác nhau vẫn trả **cùng kiểu Java `T`**, tránh lỗi generic.
6. Dùng `BodySubscribers.ofString(UTF_8)` cho **nội dung văn bản nhỏ được chấp nhận**, `ofFile` cho download có kiểm soát, và `ofInputStream` cho việc xử lý streaming.
7. Hiểu `Content-Length` là **metadata do peer cung cấp**, có thể thiếu hoặc sai; nó **không phải giới hạn bytes thực tế**.
8. Phân biệt “discard body” với “không nhận byte từ mạng”, cùng hậu quả cho connection reuse và streaming resource lifecycle.
9. Chạy hai chương trình Java 17+ hoàn chỉnh: lọc text theo status/type/length và chỉ lưu file từ response hợp lệ.
10. Thiết kế test cho status lỗi, media type lạ, thiếu length, payload lớn, response không có body, timeout, retry, redirect và security.

## 3. API cốt lõi: BodyHandler được gọi lúc nào?

Các kiểu chính của module `java.net.http`:

~~~java
HttpResponse.BodyHandler<T> handler;
HttpResponse.ResponseInfo info;
HttpResponse.BodySubscriber<T> subscriber;
HttpResponse<T> response;
~~~

Đây là các **khai báo khái niệm**, không phải một chương trình chạy độc lập. Trong code thật, `BodyHandler<T>` là một **functional interface**:

~~~java
@FunctionalInterface
public interface BodyHandler<T> {
    BodySubscriber<T> apply(ResponseInfo responseInfo);
}
~~~

Chữ ký trên là mô tả rút gọn để học, không cần tự khai báo lại interface có sẵn của JDK. `apply` nhận một `ResponseInfo` và **trả** một `BodySubscriber<T>`; Java HttpClient sau đó dùng subscriber để xử lý body. `ResponseInfo` có:

| Phương thức | Giá trị | Khi nào dùng |
| --- | --- | --- |
| `info.statusCode()` | `int`, ví dụ `200`, `204`, `404` | Ưu tiên kiểm tra status trước; chọn có nên giữ error body hay không |
| `info.headers()` | `HttpHeaders` | Xem `Content-Type`, `Content-Length`, `Content-Disposition`... |
| `info.version()` | `HttpClient.Version` | Phiên bản HTTP thực tế của response |
| `info.headers().firstValue("Content-Type")` | `Optional<String>` | Chỉ là header value, có thể thiếu |
| `info.headers().firstValueAsLong("Content-Length")` | `OptionalLong` | Có thể empty; **có thể ném NumberFormatException** nếu không parse được |

**Quan trọng:** `apply(info)` chạy **sau khi status line/response headers đã sẵn sàng, nhưng trước khi body bytes được đọc/tiêu thụ bởi subscriber**. Vì vậy có thể đưa ra chính sách sớm mà không phải cấp phát `byte[]` khổng lồ rồi mới xem status.

Một custom handler đơn giản:

~~~java
HttpResponse.BodyHandler<String> handler = info -> {
    if (info.statusCode() != 200) {
        return HttpResponse.BodySubscribers.replacing("");
    }
    return HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8);
};
~~~

Đây là **mảnh mã** trong method có import `java.net.http.HttpResponse` và `java.nio.charset.StandardCharsets`. Với status 200, body được đọc thành `String`. Với status khác 200, JDK **tiêu thụ và bỏ body** rồi trả một `String` rỗng do chính bạn chọn; nó **không tự phát sinh HTTP exception**.

### 3.1. BodyHandler và BodySubscriber không phải cùng một thứ

- `BodyHandler<T>` nhận **metadata**, chọn cách xử lý body và **tạo một BodySubscriber<T> cho exchange**.
- `BodySubscriber<T>` nhận **những danh sách `ByteBuffer` của body** theo `Flow.Subscriber<List<ByteBuffer>>`, trả `CompletionStage<T>` từ `getBody()`.
- `BodyHandlers.ofString()` là **handler sẵn có** và sẽ dùng subscriber tương ứng.
- `BodySubscribers.ofString(UTF_8)` là **subscriber sẵn có** để custom handler trả về.
- `HttpResponse<T>.body()` là **kết quả kiểu T**, tùy subscriber; có thể là String, Path, InputStream, Void hoặc kiểu domain được ánh xạ.
- `HttpResponse.statusCode()` là metadata sau khi response nhận về, **không** thay quyết định đã thực hiện trong handler.

Trong handler tùy chỉnh, thường **trả `BodySubscribers.*`**, không phải `BodyHandlers.*`. Hai nhóm factory khác nhau về kiểu; nhầm lẫn này gây lỗi compile phổ biến.

### 3.2. BodyHandler quyết định trước body, không phải sau body

~~~text
Header đến: 200 | Content-Type: application/json | Content-Length: 12
                           |
                           v
                  BodyHandler quyết định
                           |
                           v
                 Bytes body bắt đầu tới
                           |
                           v
              BodySubscriber consume / map
                           |
                           v
                 HttpResponse<T>.body()
~~~

Vì vậy handler không thể xem nội dung JSON đã parse để quyết định “có nên tải JSON không”. Nó chỉ biết thông tin **trên status và headers**. Nếu quyết định phải dựa trên dữ liệu thực tế, thực hiện **validation khi tiêu thụ** hoặc chọn một streaming subscriber có giới hạn.

## 4. Vì sao ofString/ofByteArray mặc định có thể không phù hợp?

Các handler tiện lợi:

~~~java
HttpResponse.BodyHandlers.ofString();
HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8);
HttpResponse.BodyHandlers.ofByteArray();
HttpResponse.BodyHandlers.discarding();
HttpResponse.BodyHandlers.ofFile(file);
HttpResponse.BodyHandlers.ofInputStream();
~~~

Đây là **danh sách biểu thức** (biến `file` cần có trước, import liên quan). `BodyHandlers` được JDK ghi chú rõ: các implementation có sẵn thường **không kiểm tra status code**, nghĩa là **body được chấp nhận theo chiến lược đã chọn**, kể cả response 404 hoặc 500. Do vậy:

- `ofString()`: tích lũy bytes rồi tạo String; nếu dùng trên endpoint không giới hạn payload, có nguy cơ chiếm nhiều heap.
- `ofByteArray()`: giữ toàn bộ body thành `byte[]`; nguy cơ tương tự.
- `ofFile(path)`: ghi response body ra disk; **không tự bỏ qua file HTML lỗi 404** và có thể vô tình ghi trang lỗi dưới tên `report.pdf` nếu không check.
- `ofInputStream()`: cho caller đọc luồng; **phải đọc đến EOF hoặc close stream** để giải phóng exchange đúng hợp đồng.
- `discarding()`: không giữ nội dung nhưng **vẫn xử lý/drain incoming body**; không phải “client tuyệt đối không nhận byte nào”.
- `replacing(value)`: bỏ incoming bytes và dùng **giá trị T cho sẵn**, rất hợp cho nhánh skip trong custom policy.

**Mục tiêu** không phải “mọi 4xx/5xx đều phải bỏ body”. Một API có thể trả error JSON hữu ích theo RFC 9457 Problem Details; ta chỉ cần **chọn có kiểm soát**: nếu muốn đọc lỗi, dùng chiến lược giữ một phần lỗi nhỏ và có giới hạn, chứ không mặc định giữ toàn bộ.

## 5. Bảng ra quyết định theo status và headers

| Status và header | Lựa chọn có thể hợp lý | Lý do / lưu ý |
| --- | --- | --- |
| `200 OK`, `Content-Type: application/json`, body nhỏ, đủ tin cậy | `ofString(UTF_8)` rồi validate JSON | Chỉ dùng khi có giới hạn bytes thật sự |
| `200 OK`, `text/plain`, kích thước nhỏ | `ofString(UTF_8)` | Chỉ là text nếu response đúng semantics/charset |
| `200 OK`, `application/octet-stream` cần tải | `ofFile(controlledPath)` | Disk path do **ứng dụng** quyết định, có quota và cleanup |
| `200 OK`, binary/unknown length nhưng được phép đọc dần | `ofInputStream()` hoặc subscriber streaming | Đọc theo byte budget, phải close/cancel |
| `201 Created` có JSON hợp lệ | Có thể nhận một body nhỏ | Không gắn cứng mọi thành công bằng `status == 200` |
| `202 Accepted` có metadata/job URI | Có thể nhận JSON nhỏ | Ý nghĩa `202` khác hoàn thành nghiệp vụ |
| `204 No Content` | `replacing(NO_BODY)` / `discarding()` | Không có content theo HTTP semantics |
| `304 Not Modified` | `replacing(NO_BODY)` / `discarding()` | Dùng metadata/cache đã có, không đợi body mới |
| Response cho `HEAD` | Không đọc body, vẫn xem headers | `HEAD` không có response content dù metadata có thể giống GET |
| `3xx` khi không tự follow redirect | Bỏ hoặc xử lý nội dung trung gian có kiểm soát | Kiểm tra `Location`, chính sách redirect |
| `400`–`499` | Có thể bỏ hoặc giữ error body **có hạn mức** | Status mới là căn cứ; lỗi API có khi trả JSON hữu ích |
| `500`–`599` | Bỏ hoặc lấy trích đoạn lỗi nhỏ | Tránh ghi trang lỗi lớn ra file download |
| `206 Partial Content` | Xử lý đặc biệt khi bạn **đã yêu cầu Range** | Kiểm tra `Content-Range` và lắp ghép đúng vị trí |
| Thiếu `Content-Length` | Có thể stream với hard cap, hoặc fail-closed | Header có thể thiếu ở transfer chunked/HTTP2 |
| `Content-Length` rất lớn | Từ chối lưu vào memory/file không hạn mức | Header là hint, không phải hard cap |
| `Content-Type` sai/không mong muốn | Bỏ, báo lỗi hoặc fallback phù hợp | Content-Type là dữ liệu nhận được; vẫn phải kiểm tra content thực |

**Chú ý HTTP semantics:** response 204/304 hoặc HEAD không có content cần tiêu thụ như GET bình thường. Trạng thái 1xx thường là informational trước final response; trong flow HttpClient thông thường, đừng nhầm `100 Continue` với một response content cuối cần parse thành JSON. `205 Reset Content` cũng có yêu cầu không tạo content theo chuẩn; nếu chính sách áp dụng cho mọi “no-content”, cân nhắc cả 205.

### 5.1. Kiểm tra status trước khi kiểm tra content type

Một trang lỗi 404 có thể được server trả kèm `Content-Type: application/json`. Nếu bạn chỉ nhìn Content-Type rồi parse JSON thành đối tượng business success, logic có thể sai. Kiểm tra status trước:

~~~java
if (info.statusCode() < 200 || info.statusCode() >= 300) {
    return HttpResponse.BodySubscribers.replacing(
            new Choice("SKIP_STATUS", ""));
}
~~~

Đây là **mảnh code** trong lambda `BodyHandler<Choice>`, `Choice` là record trong ví dụ phần 8. Policy này bỏ mọi non-2xx, bao gồm error body; với sản phẩm cần error details, xây **nhánh lỗi riêng** có giới hạn body. Không phải tất cả response 2xx đều có content: 204/205 phải xét riêng.

### 5.2. Header Content-Type cần hiểu media type và parameter

Ví dụ:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Type: application/json
Content-Type: application/problem+json
Content-Type: application/octet-stream
~~~

Nếu chính sách nhận văn bản:

- So sánh media type **không phân biệt chữ hoa/thường**, loại tham số `; charset=...` trước khi so sánh.
- `application/problem+json` có cấu trúc kiểu JSON nhưng semantics khác `application/json` thông thường: nên có policy xử lý lỗi riêng.
- Header có thể thiếu hoặc bị khai báo sai; **không** dùng text type làm bằng chứng dữ liệu an toàn/đã xác thực.
- Charset thực tế phải phù hợp contract API. JSON trao đổi trên web thường dùng UTF-8; text/plain có thể có charset được khai báo. Chọn một charset cứng trong demo vì server chính mình tạo, không áp dụng mù cho mọi site.
- Với file tải xuống, Content-Type không phải antivirus, checksum hay lời bảo đảm file format. Luôn validate bytes nếu nghiệp vụ đòi hỏi.

**Tại sao tách media type?** `"text/plain; charset=UTF-8".equals("text/plain")` là false, nhưng hai header cùng media type. Có thể lấy phần trước `;`, trim và lower-case theo `Locale.ROOT` cho demo. Parser production cần xử lý field values hợp lệ và trường hợp malformed/duplicate theo HTTP stack.

### 5.3. Content-Length là byte count, nhưng không đáng tin làm rào chắn cứng

`Content-Length` là **số octets** của body theo quy tắc HTTP, không phải độ dài `String.length()`. `HttpHeaders.firstValueAsLong("Content-Length")` trả `OptionalLong` nếu có giá trị parse được, **empty nếu vắng** và **có thể ném `NumberFormatException`** nếu giá trị không parse được.

~~~java
OptionalLong length;
try {
    length = info.headers().firstValueAsLong("Content-Length");
} catch (NumberFormatException invalid) {
    return HttpResponse.BodySubscribers.replacing(
            new Choice("SKIP_LENGTH", ""));
}
if (length.isEmpty() || length.getAsLong() > 64) {
    return HttpResponse.BodySubscribers.replacing(
            new Choice("SKIP_LENGTH", ""));
}
~~~

Đây là **mảnh code** trong handler ví dụ. Dù kiểm tra `<= 64` và đủ tin rằng server theo hợp đồng, vẫn có nhiều giới hạn:

1. `Content-Length` **không luôn xuất hiện**, ví dụ response HTTP/1.1 chunked hoặc stream.
2. Header **có thể sai** nếu peer hoặc intermediary không đáng tin, hoặc request bị lỗi framing.
3. `Content-Encoding: gzip` có thể làm kích thước dữ liệu sau giải mã **khác** số byte truyền trên wire; cần giới hạn sau giải mã nếu dùng decompression.
4. `Content-Length` không ngăn `ofString()` hoặc `ofFile()` lưu nhiều bytes hơn nếu nguồn gửi không tuân thủ và stack cho phép; chỉ dựa header **không phải cơ chế chống memory/disk exhaustion**.
5. Cần giới hạn **thực tế khi đọc**: bộ đếm byte, timeout, max decoded size, disk quota, Flow cancellation, hoặc proxy/server enforcing.

Vì thế các demo dùng **local server được kiểm soát**. Production nên áp dụng **hard cap ở subscriber/stream**, và dùng Content-Length làm bước **lọc sớm**.

## 6. Generic type T: cùng một BodyHandler phải trả BodySubscriber<T>

Phương thức `client.send(request, bodyHandler)` có chữ ký theo generic body type:

~~~java
<T> HttpResponse<T> send(
        HttpRequest request,
        HttpResponse.BodyHandler<T> responseBodyHandler)
        throws IOException, InterruptedException;
~~~

Đây là dạng chữ ký minh họa API (không phải lời gọi thực thi). Nếu handler có kiểu `BodyHandler<String>`, mọi nhánh phải trả `BodySubscriber<String>`, không được một nhánh trả `BodySubscriber<Void>` và nhánh khác trả `BodySubscriber<Path>` rồi hy vọng compiler tự làm union type.

**Sai kiểu:**

~~~java
// SAI: lambda khai báo BodyHandler<String>,
// nhưng nhánh 404 trả BodySubscriber<Void>.
HttpResponse.BodyHandler<String> wrong = info ->
        info.statusCode() == 404
                ? HttpResponse.BodySubscribers.discarding()
                : HttpResponse.BodySubscribers.ofString(
                        StandardCharsets.UTF_8);
~~~

Đây là ví dụ **cố ý không compile** để minh họa generic mismatch, không phải chương trình Java chạy được.

**Đúng bằng cách dùng `replacing`:**

~~~java
HttpResponse.BodyHandler<String> correct = info ->
        info.statusCode() == 404
                ? HttpResponse.BodySubscribers.replacing("")
                : HttpResponse.BodySubscribers.ofString(
                        StandardCharsets.UTF_8);
~~~

Đây là mảnh code Java 17; import `HttpResponse` và `StandardCharsets`. `replacing("")` là `BodySubscriber<String>`, đồng nhất với `ofString(...)`. Nếu cần phân biệt “bị bỏ” và “body rỗng hợp lệ”, hãy dùng một **record/kiểu kết quả** chứa `decision` thay vì trả `""` rồi đoán ý nghĩa.

### 6.1. Dùng mapping để trả kiểu domain rõ ràng

~~~java
record Choice(String decision, String text) {}

HttpResponse.BodySubscriber<Choice> kept =
        HttpResponse.BodySubscribers.mapping(
                HttpResponse.BodySubscribers.ofString(
                        StandardCharsets.UTF_8),
                text -> new Choice("ACCEPT_TEXT", text));

HttpResponse.BodySubscriber<Choice> dropped =
        HttpResponse.BodySubscribers.replacing(
                new Choice("SKIP_STATUS", ""));
~~~

Đây là các mảnh code nằm trong class/method, không standalone. Cả hai nhánh trả **BodySubscriber<Choice>**. `mapping` cho phép chuyển String thành Choice **sau khi body đã được subscriber upstream xử lý**.

**Chú ý performance:** tài liệu JDK nói mapping function chạy bằng **executor của HttpClient**. Không đặt parsing DB/blocking I/O lâu trong mapper; nếu muốn stream JSON/file lớn, tách sang cơ chế parsing bất đồng bộ/streaming riêng và giữ executor responsive.

## 7. Chiến lược cụ thể: loại bỏ, nhận text, ghi file hay streaming?

| Factory trong custom handler | Kiểu body trả về | Điều kiện điển hình | Rủi ro/cleanup |
| --- | --- | --- | --- |
| `BodySubscribers.replacing(value)` | Tùy giá trị `T` | Bỏ response không được chấp nhận, vẫn trả result rõ ràng | Vẫn drain incoming bytes; không chặn lưu lượng mạng |
| `BodySubscribers.discarding()` | `Void` | Chỉ cần status/headers, không cần body | Generic `Void`, response body null |
| `BodySubscribers.ofString(UTF_8)` | `String` | Text nhỏ sau khi validate status/type/size | Tích lũy toàn bộ body vào heap, cần hard cap |
| `BodySubscribers.ofByteArray()` | `byte[]` | Payload binary nhỏ có giới hạn | Heap tăng theo body thực nhận |
| `BodySubscribers.ofFile(path)` | `Path` | Download được phép, path app kiểm soát | Disk quota, symlink, path ownership, partial file cleanup |
| `BodySubscribers.ofInputStream()` | `InputStream` | Đọc streaming/cấp giới hạn khi không có Content-Length | Phải đọc tới EOF hoặc `close()` |
| `BodySubscribers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | Pipeline reactive/backpressure | Subscribe đúng một lần, tiêu thụ/cancel có kiểm soát |
| `BodySubscribers.mapping(upstream, fn)` | `U` | Đổi String/Path/Void thành kết quả thống nhất | Mapper có thể chạy trên client executor |
| `BodySubscribers.fromSubscriber(...)` | Tùy `T` | Cần Flow subscriber do app kiểm soát | Phải thực hiện đúng Flow protocol và cancellation |

**Quan trọng:** `replacing`/`discarding` giúp ứng dụng **không giữ toàn bộ body vào String/byte[]/file**, chứ **không** bảo đảm server không gửi body hoặc không tiêu hao bandwidth. JDK thường phải consume/drain body để tuân thủ framing và có thể giữ connection tái sử dụng. Nếu muốn abort vì response quá lớn/không đáng tin, cần cancellation/close ở cấp streaming/subscriber theo policy; hành vi connection reuse có thể bị ảnh hưởng.

## 8. Chương trình chạy độc lập #1: lọc theo status, Content-Type và Content-Length

### 8.1. Chính sách của chương trình

Một HTTP server cục bộ tạo bảy tình huống có thể tái hiện:

- `/ok`: 200 + `text/plain` + 5 byte → **ACCEPT_TEXT**.
- `/json`: 200 + `application/json` + 11 byte → **ACCEPT_TEXT**.
- `/error`: 404 + text → **SKIP_STATUS** (dù body tồn tại).
- `/binary`: 200 + `application/octet-stream` → **SKIP_TYPE**.
- `/large`: 200 + text 100 byte → **SKIP_LENGTH**, vì giới hạn demo là 64 byte.
- `/empty`: 204 No Content → **NO_BODY**.
- `/unknown`: 200 + text chunked không có Content-Length → **SKIP_LENGTH** (policy fail-closed của demo).

Mã **không tải toàn bộ response bị từ chối vào heap**, vì dùng `BodySubscribers.replacing(...)`. Với text đã chấp nhận, dùng `BodySubscribers.ofString(UTF_8)` qua `mapping(...)`. Đây là một **filter bằng metadata**, không phải bộ hạn mức tuyệt đối chống payload độc hại: nếu server khai báo Content-Length nhỏ nhưng gửi body thực lớn, cần streaming subscriber kiểm soát bytes như phần 10.

Tạo tệp **`SelectiveBodyHandlerDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Locale;
import java.util.OptionalLong;

public class SelectiveBodyHandlerDemo {
    record Choice(String decision, String text) {}

    static HttpResponse.BodyHandler<Choice> selectBody() {
        return info -> {
            int status = info.statusCode();
            if (status == 204 || status == 304) {
                return HttpResponse.BodySubscribers.replacing(
                        new Choice("NO_BODY", ""));
            }
            if (status < 200 || status >= 300) {
                return HttpResponse.BodySubscribers.replacing(
                        new Choice("SKIP_STATUS", ""));
            }

            String type = info.headers().firstValue("Content-Type")
                    .orElse("").split(";", 2)[0]
                    .trim().toLowerCase(Locale.ROOT);
            if (!type.equals("text/plain") &&
                !type.equals("application/json")) {
                return HttpResponse.BodySubscribers.replacing(
                        new Choice("SKIP_TYPE", ""));
            }

            OptionalLong length;
            try {
                length = info.headers().firstValueAsLong("Content-Length");
            } catch (NumberFormatException invalid) {
                return HttpResponse.BodySubscribers.replacing(
                        new Choice("SKIP_LENGTH", ""));
            }
            if (length.isEmpty() || length.getAsLong() < 0 ||
                    length.getAsLong() > 64) {
                return HttpResponse.BodySubscribers.replacing(
                        new Choice("SKIP_LENGTH", ""));
            }

            return HttpResponse.BodySubscribers.mapping(
                    HttpResponse.BodySubscribers.ofString(
                            StandardCharsets.UTF_8),
                    text -> new Choice("ACCEPT_TEXT", text));
        };
    }

    static void reply(HttpExchange exchange, int status,
                      String type, String text) throws IOException {
        try (exchange) {
            if (type != null) {
                exchange.getResponseHeaders().set("Content-Type", type);
            }
            if (status == 204) {
                exchange.sendResponseHeaders(status, -1);
                return;
            }
            byte[] payload = text.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(status, payload.length);
            exchange.getResponseBody().write(payload);
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/ok", e ->
                reply(e, 200, "text/plain; charset=UTF-8", "hello"));
        server.createContext("/json", e ->
                reply(e, 200, "application/json", "{\"ok\":true}"));
        server.createContext("/error", e ->
                reply(e, 404, "text/plain", "not allowed"));
        server.createContext("/binary", e ->
                reply(e, 200, "application/octet-stream", "BYTE"));
        server.createContext("/large", e ->
                reply(e, 200, "text/plain", "x".repeat(100)));
        server.createContext("/empty", e ->
                reply(e, 204, null, ""));
        server.createContext("/unknown", e -> {
            try (e) {
                e.getResponseHeaders().set("Content-Type", "text/plain");
                e.sendResponseHeaders(200, 0); // chunked: no Content-Length
                e.getResponseBody().write("chunk".getBytes(
                        StandardCharsets.UTF_8));
            }
        });
        server.start();
        try {
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            for (String path : new String[]{
                    "/ok", "/json", "/error", "/binary",
                    "/large", "/empty", "/unknown"}) {
                URI uri = URI.create("http://127.0.0.1:" +
                        server.getAddress().getPort() + path);
                HttpRequest request = HttpRequest.newBuilder(uri)
                        .timeout(Duration.ofSeconds(5))
                        .GET().build();
                HttpResponse<Choice> response = client.send(
                        request, selectBody());
                System.out.println(path + " -> " + response.statusCode()
                        + " | " + response.body().decision()
                        + " | " + response.body().text());
            }
        } finally {
            server.stop(0);
        }
    }
}
~~~

Biên dịch với API mục tiêu **Java 17** và chạy:

~~~bash
javac --release 17 -encoding UTF-8 --add-modules jdk.httpserver SelectiveBodyHandlerDemo.java
java --add-modules jdk.httpserver SelectiveBodyHandlerDemo
~~~

**Stdout đã được kiểm chứng bằng OpenJDK 24 với `javac --release 17`:**

~~~text
/ok -> 200 | ACCEPT_TEXT | hello
/json -> 200 | ACCEPT_TEXT | {"ok":true}
/error -> 404 | SKIP_STATUS | 
/binary -> 200 | SKIP_TYPE | 
/large -> 200 | SKIP_LENGTH | 
/empty -> 204 | NO_BODY | 
/unknown -> 200 | SKIP_LENGTH | 
~~~

Dấu cách ở cuối các dòng skip là do `System.out.println(... + " | " + response.body().text())` và `text=""`; đó **không** phải một body thực nhận được lưu trong Choice.

### 8.2. Phân tích flow từng request

**Trường hợp `/ok`:**

1. `ResponseInfo.statusCode() == 200`, không bị skip do status.
2. `Content-Type: text/plain; charset=UTF-8` được tách media type còn `text/plain`.
3. `Content-Length: 5` nằm trong `0..64`.
4. Handler trả `BodySubscribers.mapping(ofString(UTF_8), ...)`.
5. Body bytes được decode thành `"hello"`, ánh xạ thành `Choice("ACCEPT_TEXT", "hello")`.

**Trường hợp `/error`:**

1. Handler thấy `404` trước khi phải nhận body vào String.
2. Trả `BodySubscribers.replacing(new Choice("SKIP_STATUS",""))`.
3. Response vẫn có `statusCode()==404` để tầng ứng dụng xử lý.
4. Error payload server gửi vẫn được JDK **discard/consume**, nhưng ứng dụng không giữ body trong Choice/heap.

**Trường hợp `/binary`:** status 200 nhưng Content-Type không thuộc allowlist; không gọi `ofString` để tạo chuỗi vô nghĩa từ binary.

**Trường hợp `/large`:** header thông báo 100 byte nên handler bỏ sớm. **Không có hard cap thực tế** từ đoạn này; nó chỉ dựa trên header của local server.

**Trường hợp `/empty`:** status 204 không mang content; handler trả Choice `NO_BODY` mà không cố decode String.

**Trường hợp `/unknown`:** Java HttpServer gửi HTTP/1.1 chunked khi `sendResponseHeaders(200, 0)`, không có Content-Length; chính sách demo quyết định **bỏ** thay vì tự động lưu payload không biết trước độ dài. Ứng dụng thực có thể chọn streaming với limit thay vì bỏ mọi body không có header độ dài.

### 8.3. Vì sao cần kiểu Choice?

Nếu trả String rỗng khi bỏ body, caller khó phân biệt:

- Response 200 có body thật sự bằng chuỗi rỗng.
- Response 204 không có body theo semantics.
- Response 404 bị bỏ.
- Response 200 binary bị từ chối.
- Response 200 body dài bị policy từ chối.

`record Choice(String decision, String text)` làm quyết định trở nên **tường minh**, giúp log, xử lý fallback và test không nhập nhằng. Trong sản phẩm, có thể thay bằng `sealed interface Result permits Text, Skipped, Downloaded` hoặc record chứa enum Decision và metadata, miễn cùng generic `T`.

## 9. Chương trình chạy độc lập #2: chỉ ghi file khi status và headers đúng

Một sai lầm phổ biến:

~~~java
HttpResponse<Path> response = client.send(
        request, HttpResponse.BodyHandlers.ofFile(Path.of("report.pdf")));
~~~

Dù endpoint trả **404 trang lỗi HTML**, handler `ofFile` vẫn xử lý body theo chính sách ghi file. Có thể tạo file `report.pdf` chứa nội dung lỗi thay vì PDF thật. Nếu cần download có kiểm soát, chọn **ofFile chỉ trong nhánh chấp nhận**.

Ví dụ tiếp theo:

1. Một endpoint local `/asset` trả HTTP 200, `application/octet-stream` và đúng **8 bytes nhị phân**.
2. `/missing` trả HTTP 404 nhưng cũng gắn `application/octet-stream` → **không tạo file**.
3. `/text` trả HTTP 200 nhưng `text/plain` → **không tạo file**.
4. Handler dùng `BodySubscribers.replacing(new Outcome(..., null))` cho nhánh skip.
5. Nhánh chấp nhận dùng `BodySubscribers.ofFile(target, CREATE_NEW, WRITE)` rồi `mapping` về `Outcome`.
6. Mỗi request có **đường dẫn file đích do ứng dụng tạo trong private temporary directory**, không lấy tên file từ server.
7. Cuối chương trình xóa các file nó quản lý và thư mục tạm.

**Tệp: `SelectiveFileDownloadDemo.java`**

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.util.Locale;
import java.util.OptionalLong;

public class SelectiveFileDownloadDemo {
    record Outcome(String decision, Path file) {}

    static HttpResponse.BodyHandler<Outcome> forDownload(Path target) {
        return info -> {
            if (info.statusCode() != 200) {
                return HttpResponse.BodySubscribers.replacing(
                        new Outcome("SKIP_STATUS", null));
            }
            String mediaType = info.headers().firstValue("Content-Type")
                    .orElse("").split(";", 2)[0]
                    .trim().toLowerCase(Locale.ROOT);
            if (!mediaType.equals("application/octet-stream")) {
                return HttpResponse.BodySubscribers.replacing(
                        new Outcome("SKIP_TYPE", null));
            }
            OptionalLong size;
            try {
                size = info.headers().firstValueAsLong("Content-Length");
            } catch (NumberFormatException invalid) {
                return HttpResponse.BodySubscribers.replacing(
                        new Outcome("SKIP_LENGTH", null));
            }
            if (size.isEmpty() || size.getAsLong() < 0 ||
                    size.getAsLong() > 1_024) {
                return HttpResponse.BodySubscribers.replacing(
                        new Outcome("SKIP_LENGTH", null));
            }
            return HttpResponse.BodySubscribers.mapping(
                    HttpResponse.BodySubscribers.ofFile(target,
                            StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE),
                    file -> new Outcome("SAVED", file));
        };
    }

    static void reply(HttpExchange exchange, int status,
                      String contentType, byte[] bytes) throws IOException {
        try (exchange) {
            exchange.getResponseHeaders().set("Content-Type", contentType);
            exchange.sendResponseHeaders(status, bytes.length);
            exchange.getResponseBody().write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("http-download-");
        Path ok = directory.resolve("ok.bin");
        Path missing = directory.resolve("missing.bin");
        Path wrong = directory.resolve("wrong.bin");
        HttpServer server = null;
        try {
            server = HttpServer.create(
                    new InetSocketAddress(
                            InetAddress.getByName("127.0.0.1"), 0), 0);
            server.createContext("/asset", e -> reply(e, 200,
                    "application/octet-stream",
                    new byte[]{1,2,3,4,5,6,7,8}));
            server.createContext("/missing", e -> reply(e, 404,
                    "application/octet-stream", new byte[]{9,9,9}));
            server.createContext("/text", e -> reply(e, 200,
                    "text/plain", new byte[]{65,66}));
            server.start();

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3)).build();
            for (String path : new String[]{"/asset","/missing","/text"}) {
                Path destination = path.equals("/asset") ? ok :
                        path.equals("/missing") ? missing : wrong;
                URI uri = URI.create("http://127.0.0.1:" +
                        server.getAddress().getPort() + path);
                HttpRequest request = HttpRequest.newBuilder(uri)
                        .timeout(Duration.ofSeconds(5)).GET().build();
                HttpResponse<Outcome> response = client.send(
                        request, forDownload(destination));
                System.out.print(path + " -> " + response.statusCode() +
                        " | " + response.body().decision());
                if (response.body().file() != null) {
                    System.out.println(" | bytes=" +
                            Files.size(response.body().file()));
                } else {
                    System.out.println(" | file=" + Files.exists(destination));
                }
            }
        } finally {
            if (server != null) server.stop(0);
            Files.deleteIfExists(ok);
            Files.deleteIfExists(missing);
            Files.deleteIfExists(wrong);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Lệnh chạy Java 17+:

~~~bash
javac --release 17 -encoding UTF-8 --add-modules jdk.httpserver SelectiveFileDownloadDemo.java
java --add-modules jdk.httpserver SelectiveFileDownloadDemo
~~~

**Stdout đã kiểm chứng với OpenJDK 24 và `--release 17`:**

~~~text
/asset -> 200 | SAVED | bytes=8
/missing -> 404 | SKIP_STATUS | file=false
/text -> 200 | SKIP_TYPE | file=false
~~~

### 9.1. Vì sao không sinh file ở nhánh 404 hoặc sai type?

Handler được gọi **khi status và headers đã có**, nên ngay lúc đó nó quyết định trả `replacing` thay cho `ofFile`. Vì thế `BodySubscribers.ofFile(...)` **không được khởi tạo cho exchange bị từ chối** và ứng dụng không viết body lỗi xuống file đích.

Tính đúng đắn trong demo dựa trên việc:

- Endpoint local được kiểm soát, header length đúng với payload thật.
- File path được tạo trong thư mục tạm do chương trình tạo riêng.
- `CREATE_NEW` tránh ghi đè file đích đã có (nếu file tồn tại, thao tác download sẽ fail thay vì truncate file).
- File được dọn trong `finally` kể cả khi có exception.

**Không tuyên bố demo đã an toàn trước server độc hại.** Header `Content-Length <= 1024` chỉ là **bước lọc**, không phải quota disk cứng. Production còn cần giới hạn số byte **thực nhận**, verify checksum/magic bytes/charset theo file format, kiểm tra kích thước cuối, chống filename injection, path traversal, symlink, disk exhaustion và file partial khi lỗi giữa chừng.

### 9.2. Policy HTTP nên tùy loại tài nguyên

Một downloader chỉ nhận **200 OK** có thể đúng nếu muốn một response trọn vẹn. Nhưng ứng dụng tải file theo range có thể cần **206 Partial Content** và parse `Content-Range` để ghép phần file đúng offset. Nếu server trả 301/302/307/308, có thể cần follow redirect theo chính sách và kiểm tra **origin cuối**; không tự chuyển file từ bất kỳ origin mới sang vị trí tin cậy. Nếu server trả 304 từ conditional GET, cần dùng cache đã lưu thay vì ghi file rỗng đè file cũ.

Tức là **chọn theo status** phải xuất phát từ **hợp đồng endpoint**, không hard-code “chỉ 200 mới là đúng” cho mọi API.

## 10. Khi không biết Content-Length: dùng streaming và giới hạn bytes thực

Một body có thể không có `Content-Length` hợp lệ, nhưng vẫn là JSON/text cần thiết. Nếu không muốn bỏ như ví dụ #1, có thể chọn **`BodySubscribers.ofInputStream()`** thay vì `ofString()`, rồi đọc có giới hạn trong caller.

Mảnh code minh họa (đặt trong method có `client`, `request` đã tồn tại; cần `java.io.InputStream`, `java.io.IOException`, `java.net.http.*` và `StandardCharsets`):

~~~java
HttpResponse.BodyHandler<InputStream> streaming = info -> {
    boolean text200 = info.statusCode() == 200 &&
            info.headers().firstValue("Content-Type")
                    .orElse("").toLowerCase(Locale.ROOT)
                    .startsWith("text/plain");
    if (!text200) {
        return HttpResponse.BodySubscribers.replacing(
                InputStream.nullInputStream());
    }
    return HttpResponse.BodySubscribers.ofInputStream();
};

HttpResponse<InputStream> response =
        client.send(request, streaming);

final int maxBytes = 64 * 1024;
try (InputStream body = response.body()) {
    byte[] bounded = body.readNBytes(maxBytes + 1);
    if (bounded.length > maxBytes) {
        throw new IOException("Body exceeds configured byte limit");
    }
    String acceptedText =
            new String(bounded, StandardCharsets.UTF_8);
    // Parse/validate acceptedText only after enforcing the byte limit.
}
~~~

Đây là **mảnh code**, không phải chương trình độc lập. Cần import `java.util.Locale` nữa. `readNBytes(maxBytes + 1)` bảo đảm ứng dụng **không giữ nhiều hơn maxBytes + 1** trong mảng này, rồi phát hiện vượt hạn; `try-with-resources` đóng stream. Nhưng nó **không tự bảo vệ** trước slow server không kết thúc body, decompression bomb ở tầng khác hoặc mọi loại resource exhaustion. Cần request/stream deadline, giới hạn decoded bytes nếu giải nén, số connection và cách thức hủy khi quá hạn.

**Lifecycle cực kỳ quan trọng:** tài liệu JDK nói `BodySubscribers.ofInputStream()` cho response hoàn thành **ngay khi headers đã đọc**, trước khi toàn bộ body được xử lý. Caller phải **đọc hết đến EOF hoặc gọi `InputStream.close()`**, nếu không có thể giữ connection/resources lâu không cần thiết.

Với `BodySubscribers.ofPublisher()`, phải subscribe **một lần**, request đúng cách, drain đến `onComplete/onError` hoặc cancel khi không muốn đọc tiếp; không subscribe có thể gây leak. Một subscriber tự viết phải tuân thủ `Flow.Subscriber<List<ByteBuffer>>`, quản lý backpressure và cancellation. Không nên chuyển toàn bộ công việc blocking vào `BodySubscribers.mapping(...)`, vì mapper chạy trên executor của HttpClient và có thể starvation.

### 10.1. Lọc header + hard cap là hai lớp khác nhau

~~~text
LỚP 1 — HEADER DECISION:
  status hợp lệ?
  media type đúng?
  Content-Length <= chính sách (nếu có)?
     |
     v
LỚP 2 — BYTE ENFORCEMENT:
  stream/subscriber đếm bytes thực
  dừng/cancel khi > limit
  timeout & decoded-size bound
     |
     v
LỚP 3 — SEMANTIC VALIDATION:
  charset / JSON schema / checksum / file format
  auth / business policy / move staged file
~~~

Không có lý do gì coi header `Content-Length: 100` là **chứng chỉ** body chỉ dài 100 byte. Cũng không coi `Content-Type: application/json` là JSON đã parse hợp lệ. **Quy tắc an toàn là ra quyết định bằng headers, xác minh bằng bytes và schema.**

## 11. Các trường hợp HTTP không có body hoặc body không được mong đợi

### 11.1. HTTP 204, 205, 304 và HEAD

- `204 No Content`: response thành công nhưng **không có content**.
- `205 Reset Content`: báo client reset document/view và **không được tạo content** theo HTTP semantics.
- `304 Not Modified`: kết quả conditional request; dùng cached representation theo rules, **không** có response content mới.
- Response cho `HEAD`: không có body dù headers có thể mô tả representation nếu gửi GET; `Content-Length` trong HEAD response không được hiểu là “phải tải N byte”.

Một selector production có thể ưu tiên:

~~~java
boolean noContent = request.method().equals("HEAD") ||
        info.statusCode() == 204 ||
        info.statusCode() == 205 ||
        info.statusCode() == 304;
if (noContent) {
    return HttpResponse.BodySubscribers.replacing(
            new Choice("NO_BODY", ""));
}
~~~

Đây là **mảnh code** trong lambda có truy cập `request` đã định nghĩa bên ngoài và `Choice` đã khai báo. Trong generic library nhận nhiều requests, nên truyền context/method của request một cách rõ ràng; riêng `ResponseInfo` **không chứa method của request**. Một response 1xx mang semantics đặc biệt và thường không được xử lý như final response có body.

### 11.2. Error bodies có giá trị nhưng không nên gom vô hạn

Một API có thể trả lỗi theo `application/problem+json`, ví dụ:

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json
Content-Length: 47

{"type":"about:blank","title":"Invalid data"}
~~~

Đây là **minh họa format**; `Content-Length` hiển thị không nên được dùng làm kích thước xác nhận cho request gửi thật nếu không tự mã hóa và đếm bytes chính xác. Nếu implement server mẫu, hãy lấy `payload.getBytes(UTF_8).length` thay vì gõ length bằng mắt.

Chính sách hợp lý:

- Nếu status 4xx/5xx có error media type được cho phép, nhận **trích đoạn lỗi ngắn** với **hard byte cap**, không nhận vô hạn.
- Không ghi raw error body chứa token/cookie/PII ra log.
- Không mặc định throw `IOException` chỉ vì HTTP status 400/500; `HttpClient.send` có thể trả `HttpResponse` hợp lệ với status đó.
- Nếu không cần error body, dùng `replacing`/`discarding` để tiếp tục xử lý status.
- Khi response đã được trả qua `sendAsync`, xử lý phần lỗi và dữ liệu đầu ra trên executor/consumer thích hợp.

### 11.3. Content-Disposition không quyết định đường dẫn tin cậy

Khi tải attachment, server có thể gửi:

~~~text
Content-Disposition: attachment; filename="../../secrets.txt"
~~~

Đây là ví dụ **giá trị không đáng tin cậy**. Đừng đưa nguyên filename do HTTP header đề nghị vào `Path.resolve(...)` rồi mở file. Hãy:

1. Dùng thư mục do ứng dụng sở hữu, đúng permissions.
2. Chọn tên file do ứng dụng quyết định hoặc sanitize/whitelist cẩn thận.
3. Chống traversal, absolute paths và symlink.
4. Ghi staging file riêng với `CREATE_NEW`, hard size cap và checksum/format validation.
5. Sau khi hoàn tất, chuyển file tới vị trí cuối theo atomic move khi hệ thống hỗ trợ.
6. Dọn partial file khi download fail/cancel.

JDK có `BodyHandlers.ofFileDownload(directory, ...)`, nhưng nếu yêu cầu security nghiêm ngặt, cần hiểu cách xử lý filename và vẫn cần policy ứng dụng; dùng `ofFile(controlledPath)` thường giúp thể hiện ownership rõ ràng hơn trong bài học.

## 12. sendAsync cũng chọn body theo cùng nguyên tắc

`BodyHandler<T>` được truyền cho cả hai API:

~~~java
HttpResponse<Choice> result = client.send(
        request, selectBody());

CompletableFuture<HttpResponse<Choice>> future =
        client.sendAsync(request, selectBody());
~~~

Đây là **mảnh code trong class demo `SelectiveBodyHandlerDemo`**, cần `java.util.concurrent.CompletableFuture` và các biến `client`/`request`. Với `sendAsync`, `BodyHandler.apply(info)` vẫn quyết định theo status/headers trước khi body subscriber tiêu thụ bytes. Khác biệt là **caller không block chờ response theo cách `send`**, mà nhận `CompletableFuture`.

Không có nghĩa Java tự tạo giới hạn memory cho `BodySubscribers.ofString` chỉ vì dùng `sendAsync`. Nếu nhiều request đồng thời trả body lớn, `ofString` có thể tăng heap rất nhanh. Cần **admission control, concurrency limit, timeout và policy subscriber**, không chỉ chọn asynchronous API.

### 12.1. Tính bất biến và thread-safety

Một `BodyHandler<T>` có thể được dùng cho nhiều request; không nên lưu trạng thái mutable chung mà không đồng bộ. Cách viết lambda chỉ đọc `info` và trả subscriber mới thường đơn giản và ít rủi ro.

Đừng tái dùng **một BodySubscriber instance** cho nhiều HTTP exchanges. Subscriber có lifecycle/Flow subscription riêng; tạo subscriber mới trong mỗi lần `apply(info)`. Đường dẫn file cũng nên tách theo từng request, tránh hai downloads ghi cùng một path.

## 13. Redirect, partial response và cache: khi status quan trọng hơn loại body

### 13.1. 3xx và redirect policy

Java `HttpClient` có cấu hình `followRedirects(...)`. Khi redirect được tự động follow, final response có thể đến từ **URI khác** và headers/status khác. Một selector chọn subscriber theo response info của exchange đang xử lý; app nên quan sát `response.uri()`, `response.request()` và `response.previousResponse()` nếu cần audit redirect.

Nếu download từ URL ban đầu tin cậy nhưng redirect sang origin không tin cậy, không thể chỉ xét final `Content-Type` là đủ. Chính sách origin/scheme/authorization phải được kiểm soát. Đừng chuyển HTTP sang HTTPS hoặc ngược lại mà không theo quy tắc an toàn.

### 13.2. 206 Partial Content

Nếu request có `Range` để tải tiếp file, response `206 Partial Content` mang partial representation; **không** ghi đè toàn bộ file như một 200 bình thường. Cần kiểm tra `Content-Range`, ETag/validator và tổng độ dài/offset. Chọn `BodySubscriber` theo **status + request context + headers**.

### 13.3. 304 Not Modified

Một conditional request có thể nhận `304`. Trả empty body choice là đúng, nhưng app phải **kết hợp với cached representation** theo HTTP caching semantics nếu muốn hiển thị dữ liệu. `304` không nên bị đối xử như “body lỗi rỗng” hoặc “đè file cache thành rỗng”.

## 14. Tại sao “chọn subscriber” không phải hard stop trước khi download?

Có ba khái niệm dễ nhầm:

| Hành động | Ý nghĩa | Tác động |
| --- | --- | --- |
| `BodySubscribers.replacing(value)` | **Consume/discard** bytes, trả một value do app chọn | Không materialize body; vẫn có network traffic |
| `BodySubscribers.ofInputStream()` + close sớm | App có quyền đọc/cancel remainder khi không muốn body nữa | Có thể đóng connection, ảnh hưởng reuse |
| Custom `Flow.Subscriber` cancel subscription | Ngừng nhận thêm dữ liệu qua subscription theo Flow contract | Có thể hủy exchange/connection; phải xử lý trạng thái chính xác |

Không nên quảng bá `replacing` thành “ngăn server gửi body 10 GB”. Nếu server thật sự trả 10 GB thì hoạt động **drain/discard vẫn tiêu tốn băng thông/thời gian**, dù tiết kiệm heap/disk. Khi muốn cắt ngay vì body không đáng tin, dùng cancellation/close/size limit và chấp nhận trade-off connection reuse.

Ngược lại, **vứt response body bằng cách bỏ quên `InputStream` mà không đóng** là lỗi resource management: network exchange có thể giữ kết nối và pooled resources. Vì vậy phải đọc EOF hoặc close/cancel đúng cách.

## 15. Debugging: vì sao body không có hoặc bị skip?

| Triệu chứng | Khả năng | Cách kiểm tra |
| --- | --- | --- |
| Status 200 nhưng `Choice=SKIP_TYPE` | Content-Type không thuộc allowlist | Xem media type/charset; không tự sửa giả header |
| Status 200 nhưng `Choice=SKIP_LENGTH` | Content-Length thiếu/lớn/sai dạng | Xem transfer chunked và khả năng streaming có hard cap |
| Status 404 với body thực nhưng `Choice.text()==""` | Handler đã quyết định `replacing` | Xem `response.statusCode()` và decision, không hiểu là server gửi rỗng |
| 204 nhưng code chờ body bytes | Vi phạm kỳ vọng no-content | Xem status và cách dùng handler |
| File tải về có nội dung HTML lỗi | Dùng `ofFile` không check status/type | Dùng custom handler select theo metadata |
| `HttpResponse.body()` là null | Dùng `discarding()` (Void) | Dùng typed result/replacing nếu cần phân biệt |
| Memory tăng cao dù đã check Content-Length | Header không phải hard cap, concurrency cao | Dùng bounded subscriber/stream + concurrency limit |
| Download `ofFile` tạo file một phần rồi fail | Transport/cancel/timeout | Dọn staging file theo ownership |
| `send` nhận HTTP 500 nhưng không throw | HTTP error status vẫn là response | Kiểm tra status và branch nghiệp vụ |
| `InputStream` khiến connection pool bị giữ | Không đọc hết hoặc close | Try-with-resources/EOF |
| `sendAsync` callback bị nghẽn | Mapping/consumer làm việc nặng | Tách blocking tasks khỏi client executor |
| File có tên nguy hiểm | Tin `Content-Disposition` từ server | Dùng controlled path, sanitize và validate |

**Nguyên tắc logging:** log `request method`, URI đã loại query secrets, status, Content-Type, Content-Length (nếu có), decision, actual bytes và thời gian xử lý; **không** log raw error pages, cookies hay Authorization headers.

## 16. Bài tập có lời giải

### Bài 1 — Phân biệt handler và subscriber

`BodyHandler.apply(info)` nhận được byte[] của response chưa?

**Đáp án:** Chưa. Nó nhận **ResponseInfo** với status, headers, version trước khi body được nhận/tiêu thụ; nó phải trả `BodySubscriber<T>` để xử lý body.

### Bài 2 — Vì sao `BodyHandlers.ofString()` vẫn nhận body 404?

**Đáp án:** Handler dựng sẵn thường **không kiểm tra status code**; nó nhận body theo chiến lược `ofString`. Nếu muốn skip 404 phải viết `BodyHandler` tùy chỉnh trả `BodySubscribers.replacing(...)` hoặc `discarding()` ở nhánh đó.

### Bài 3 — Sai generic

Handler có kiểu `BodyHandler<String>` nhưng nhánh 404 trả `BodySubscribers.discarding()`. Có vấn đề gì?

**Đáp án:** `discarding()` trả `BodySubscriber<Void>`, không khớp `BodySubscriber<String>`. Dùng `replacing("")` hoặc đổi sang `BodyHandler<Choice>` và map các nhánh.

### Bài 4 — Header nhỏ nhưng body lớn

Server khai báo `Content-Length: 100`, nhưng phía ứng dụng có thể nhận vượt hạn do dữ liệu lỗi/khác biệt encoding. Kiểm tra `length <= 1024` đã bảo đảm không tốn quá 1024 byte bộ nhớ chưa?

**Đáp án:** Chưa. Header không phải hard cap; cần đếm **bytes thực tế** và dừng/cancel/close khi vượt hạn, cùng giới hạn decompressed size nếu có content encoding. Đừng tin giá trị header là bằng chứng đủ an toàn.

### Bài 5 — Thiếu Content-Length

Response 200, Content-Type text/plain nhưng không có Content-Length; có bắt buộc bỏ body không?

**Đáp án:** Không. Demo chọn **fail-closed** và bỏ; sản phẩm có thể chọn `ofInputStream()` và đọc tối đa N+1 bytes rồi close, hoặc custom Flow subscriber áp hard cap.

### Bài 6 — Không có body theo HTTP semantics

Server trả `204 No Content`. Có nên gọi `BodySubscribers.ofString` để parse JSON không?

**Đáp án:** Không. Không có content; trả result typed `NO_BODY`/replacing hoặc `discarding`.

### Bài 7 — 404 khi đang tải file

Download endpoint trả 404 với body HTML. Dùng `BodyHandlers.ofFile(destination)` có thể gây gì?

**Đáp án:** Có thể tạo file destination chứa HTML lỗi. Dùng custom handler kiểm tra status và media type **trước khi chọn `ofFile`**, ghi vào path do app kiểm soát và cleanup partial file nếu có lỗi.

### Bài 8 — Bytes vs Java chars

Một response UTF-8 chứa dấu tiếng Việt; muốn giới hạn 64 KiB, dùng `String.length()` sau decode có phải cách đúng không?

**Đáp án:** Không. Cần giới hạn **số bytes thực nhận** trước khi gom thành String. `String.length()` tính UTF-16 code units, không phải byte length trên wire.

### Bài 9 — Error JSON hữu ích

API trả `422 application/problem+json` kèm error details. Có nhất thiết bỏ response body không?

**Đáp án:** Không. Nếu ứng dụng cần error details, chọn subscriber lưu/trích xuất **bản lỗi có hạn mức**, validate schema và không log secret. Không mặc định giữ lỗi tùy độ dài.

### Bài 10 — InputStream lifecycle

Sau `BodySubscribers.ofInputStream()`, caller đọc 10 bytes đầu rồi bỏ đối tượng stream mà không close. Hậu quả?

**Đáp án:** Có thể giữ connection/resources của exchange; phải đọc hết đến EOF hoặc `close()` để giải phóng. Đóng sớm có thể làm underlying connection không được tái sử dụng.

### Bài 11 — Redirect

Tại sao cần quan sát `response.uri()`/`previousResponse()` khi download có redirect?

**Đáp án:** Final response có thể đến từ **origin khác** với policy/trust khác. Chỉ xét final status/Content-Type mà không kiểm soát redirect có thể tải từ nguồn không mong muốn.

### Bài 12 — Range download

Request `Range: bytes=1000-1999` nhận `206 Partial Content`. Có thể ghi đè file đầu từ byte 0 như xử lý 200 không?

**Đáp án:** Không. Cần xác minh `Content-Range` và ghi đúng offset; nếu không file hỏng. Status 206 cần một nhánh policy riêng.

### Bài 13 — Chỉ cần status/headers

Client muốn kiểm tra response status và ETag, không cần body. Nên chọn gì?

**Đáp án:** `BodyHandlers.discarding()` là lựa chọn sẵn có, hoặc dùng custom handler trả `BodySubscribers.replacing(...)` khi muốn value typed thể hiện quyết định. Nhớ rằng discard vẫn có thể tiêu thụ bytes qua mạng.

### Bài 14 — sendAsync và memory

Một ứng dụng chuyển từ `send` sang `sendAsync` nhưng vẫn dùng `BodyHandlers.ofByteArray()` cho 500 requests đồng thời, mỗi response 20 MB. Có tự hết nguy cơ OOM không?

**Đáp án:** Không. `sendAsync` chỉ thay cách chờ kết quả; mỗi response vẫn tích lũy bytes. Cần giới hạn concurrency, hard byte size, streaming và admission control.

## 17. Checklist code review trước khi deploy

- [ ] Tôi đã xác định status và media type **được phép nhận body** theo hợp đồng endpoint.
- [ ] Tôi biết `BodyHandler.apply(ResponseInfo)` chạy **trước** khi body được tiêu thụ.
- [ ] Mọi nhánh custom handler trả đúng `BodySubscriber<T>` theo generic thống nhất.
- [ ] Tôi chọn `replacing`/`discarding` cho response không cần body thay vì `ofString()` mặc định.
- [ ] Tôi phân biệt 204/205/304/HEAD và những response không có content.
- [ ] Tôi không chỉ chấp nhận status 200 nếu API hỗ trợ 201/202/206 hợp lệ.
- [ ] `Content-Type` được so theo media type/charset phù hợp, không dùng như bằng chứng dữ liệu an toàn.
- [ ] `Content-Length` được hiểu là **byte length**, optional/malformed và không phải rào chắn cứng.
- [ ] Với text/byte array, tôi có giới hạn **bytes thực nhận** và giới hạn decoded size.
- [ ] Với download, path được kiểm soát, staging/CREATE_NEW, quota/checksum và partial cleanup.
- [ ] Với `ofInputStream`, luôn đọc EOF hoặc close trong `try-with-resources`.
- [ ] Với `ofPublisher`, có một subscriber và lifecycle/cancellation rõ ràng.
- [ ] `mapping` không làm I/O/blocking lâu trên client executor.
- [ ] Tôi kiểm tra `statusCode()` và decision trước khi parse body hoặc triển khai side effect.
- [ ] Khi cần body lỗi có ích, có nhánh riêng với hard cap và không log secrets.
- [ ] Tôi có test 200 text, 200 binary, 204/304/HEAD, 404/500, oversized, no length, malformed headers.
- [ ] Tôi không nhầm discard với “không tốn network bandwidth”.
- [ ] Tôi đã kiểm soát redirect, content-encoding, Range/206, cache/304 và timeout theo nhu cầu.
- [ ] Tôi thử bằng JDK 17+ ở môi trường kiểm soát và không dựa vào Internet cho unit tests.

## 18. Tài liệu chính thức

- [Java SE 17 — HttpResponse.BodyHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandler.html): `apply(ResponseInfo)`, thời điểm có status/headers và tạo subscriber.
- [Java SE 17 — HttpResponse.ResponseInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.ResponseInfo.html): `statusCode()`, `headers()`, `version()`.
- [Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): các handler sẵn có và điểm quan trọng **không tự kiểm tra status code**.
- [Java SE 17 — HttpResponse.BodySubscribers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): `ofString`, `ofFile`, `ofInputStream`, `replacing`, `discarding`, `mapping`, Flow subscribers.
- [Java SE 17 — HttpResponse.BodySubscriber](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html): `Flow.Subscriber<List<ByteBuffer>>`, `getBody()`, completion và cancellation.
- [Java SE 17 — HttpHeaders](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpHeaders.html): `firstValue`, `firstValueAsLong`, case-insensitive names và NumberFormatException.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `send`, `sendAsync`, redirect/timeouts, HTTP versions.
- [Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): response status, headers, body, URI và previous response.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): server HTTP nhẹ dùng trong hai ví dụ loopback.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): status 204, 205, 206, 304, HEAD và response content semantics.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): Content-Length, transfer framing và message boundaries.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): `304 Not Modified` và cached representations.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): lỗi có representation `application/problem+json`.

**Kết luận:** `BodyHandlers.ofString()` dễ dùng nhưng **không tự quyết định có nên nhận body theo status hay media type**. Dùng **`BodyHandler<T>` tùy chỉnh** để xem `ResponseInfo` trước, rồi trả **`BodySubscriber<T>` phù hợp** — `replacing` khi bỏ, `ofString` cho text nhỏ, `ofFile` cho download đủ điều kiện, `ofInputStream` cho streaming. **Content-Length chỉ là bộ lọc sớm, không phải hard limit**, và discard không có nghĩa chặn mọi byte truyền qua mạng. Thiết kế tốt cần đúng cả **HTTP semantics, generic typing, resource cleanup, actual byte quotas và xử lý lỗi**.
