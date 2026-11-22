# Kiểm thử và tối ưu HTTP status, timeout, redirect và lỗi kết nối (Java 11+)

## 1. Mục tiêu và phạm vi

Khi lập trình HTTP với Java, nhiều lỗi xuất phát từ việc **đánh đồng mã trạng thái HTTP với lỗi mạng**, **nhầm connect timeout với request timeout**, hoặc **không nhận ra redirect có thể đổi phương thức POST thành GET**. Một chương trình gọi API hoạt động ổn ở môi trường test nhưng thất bại trong production thường có thể do kết nối bị từ chối, DNS/TLS, server trả 503, response chậm, redirect sang host khác hoặc retry không có giới hạn.

Bài học dưới ngữ cảnh **Kiểm thử và tối ưu** sử dụng module **`java.net.http`**, public API chính thức của Java 11 trở lên (JEP 321), để giải quyết bốn nhóm:

1. **HTTP status:** `200`/`204`, `3xx`, `4xx` và `5xx`; khi nào nhận `HttpResponse`, khi nào cần xử lý lỗi nghiệp vụ hoặc retry.
2. **Timeout:** `HttpClient.Builder.connectTimeout(Duration)` và `HttpRequest.Builder.timeout(Duration)`, kiểu exception và những trường hợp connection reuse.
3. **Redirect:** `HttpClient.Redirect.NEVER`, `NORMAL`, `ALWAYS`; `302`, `303`, `307`/`308`, thay đổi HTTP method, redirect history và rủi ro mất thông tin nhạy cảm.
4. **Lỗi kết nối:** `ConnectException`, `HttpConnectTimeoutException`, `UnknownHostException`, `SSLHandshakeException`, `IOException`, `InterruptedException`; sự khác biệt giữa `send` và `sendAsync`, cách test và tối ưu an toàn.

Bài có một **chương trình Java 11 hoàn chỉnh**, tự chạy một HTTP server trên loopback, kiểm tra 14 kết quả xác định và không cần Internet. Các tình huống cần môi trường đặc biệt (DNS thật, TLS certificate, TCP blackhole, proxy) được trình bày **như tình huống kiểm thử tích hợp**, không giả tạo stdout chắc chắn.

**Special Note:** Chỉ sử dụng kiến thức và API **vẫn còn áp dụng ở JDK hiện nay**. Cần phân biệt tính năng có từ Java 11 với API xuất hiện trên những JDK mới. Ví dụ này **không gọi `HttpClient.close()` hoặc `shutdown()`** vì các phương thức quản lý lifecycle đó được bổ sung sau Java 11; nó dùng public `java.net.http` của Java 11 và `jdk.httpserver` trong fixture kiểm thử.

## 2. Nắm đúng ranh giới: HTTP response khác transport failure

Luồng xử lý thường gặp:

```text
Java HttpClient
   |
   +-- kết nối/DNS/TCP/TLS thành công
   |       |
   |       +-- server gửi HTTP response
   |               |
   |               +-- 2xx: nhận HttpResponse, xử lý thành công
   |               +-- 3xx: nhận hoặc follow redirect theo policy
   |               +-- 4xx: nhận HttpResponse, xử lý lỗi client/nghiệp vụ
   |               +-- 5xx: nhận HttpResponse, xử lý lỗi server/backoff
   |
   +-- không thiết lập/duy trì HTTP exchange
           |
           +-- connect refused / DNS / TLS / I/O
           +-- connect timeout / request timeout
           +-- send(): IOException/InterruptedException
           +-- sendAsync(): CompletableFuture completed exceptionally
```

**Điểm quan trọng nhất:** `404 Not Found`, `429 Too Many Requests` hoặc `503 Service Unavailable` **không mặc nhiên làm `HttpClient.send(...)` ném IOException**. Server đã gửi một response hợp lệ, bạn vẫn nhận `HttpResponse<T>` để đọc `statusCode()`, headers và body.

`IOException` là nhóm lỗi **giao tiếp/đọc-ghi/transport**; lỗi code 4xx/5xx cần **tự quyết định nghiệp vụ** dựa trên `statusCode()`.

### 2.1. Ví dụ phân nhánh đúng

```java
HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());

int status = response.statusCode();
if (status >= 200 && status < 300) {
    // Thành công HTTP; tiếp tục kiểm tra nội dung/contract ứng dụng.
} else if (status == 404) {
    // Resource không tồn tại hoặc không được nhìn thấy.
} else if (status == 429) {
    // Rate limited; cân nhắc Retry-After và retry policy.
} else if (status >= 500) {
    // Lỗi server; không tự động retry mọi request.
} else {
    // Xử lý các status còn lại theo API contract.
}
```

Đây là **snippet**: cần biến `HttpClient client`, `HttpRequest request`, imports và xử lý `IOException/InterruptedException`. Chương trình đầy đủ ở mục 9 có một server cục bộ để chứng minh hành vi này.

Không nên đặt toàn bộ code trong `catch (IOException)` rồi giả định nó bắt được 404/503.

### 2.2. Bảng các status có ý nghĩa trong kiểm thử

| Status | Ý nghĩa thường gặp | Hành động ứng dụng |
| --- | --- | --- |
| `200 OK` | Thành công, có thể có body | Parse/validate payload theo contract |
| `201 Created` | Tạo resource thành công | Xem `Location`/body nếu API yêu cầu |
| `202 Accepted` | Đã tiếp nhận, xử lý có thể chưa hoàn tất | Poll/callback theo giao thức của server |
| `204 No Content` | Thành công nhưng không có body | Không parse JSON body rỗng |
| `301 Moved Permanently` / `302 Found` | Chuyển địa chỉ | Xem policy redirect và method semantics |
| `303 See Other` | Chuyển sang resource khác, thường dùng GET | Kiểm tra method sau redirect |
| `307 Temporary Redirect` | Redirect giữ nguyên HTTP method/body theo chuẩn | Chỉ follow nếu body có thể gửi lại an toàn |
| `308 Permanent Redirect` | Redirect lâu dài, giữ method/body theo chuẩn | Cẩn trọng replay POST/PUT |
| `400 Bad Request` | Request không hợp lệ | Sửa input/schema, thường không retry y hệt |
| `401 Unauthorized` | Chưa có/không hợp lệ thông tin xác thực | Luồng refresh/auth theo chính sách |
| `403 Forbidden` | Không đủ quyền | Không lặp retry vô ích |
| `404 Not Found` | Không tìm thấy/không cho biết resource | Theo nghiệp vụ: absent, fail hoặc fallback |
| `408 Request Timeout` | Server báo không chờ được request | Có thể retry theo idempotency policy |
| `409 Conflict` | Xung đột trạng thái | Reconcile thay vì retry vô điều kiện |
| `412 Precondition Failed` | Điều kiện `If-Match`/etag không thỏa | Refresh state và giải quyết conflict |
| `422 Unprocessable Content` | Dữ liệu hợp lệ về cú pháp nhưng không xử lý được | Sửa dữ liệu trước khi gọi lại |
| `429 Too Many Requests` | Bị giới hạn tốc độ | Đọc `Retry-After` nếu có, bounded backoff |
| `500 Internal Server Error` | Lỗi server chung | Phân tích ngữ nghĩa/idempotency trước retry |
| `502 Bad Gateway` | Gateway gặp upstream lỗi | Có thể retry với budget và backoff |
| `503 Service Unavailable` | Tạm thời quá tải/maintenance | Có thể retry có giới hạn, tôn trọng Retry-After |
| `504 Gateway Timeout` | Gateway không nhận upstream đúng hạn | Cân nhắc retry và double-processing risk |

**Mã trạng thái chỉ mô tả kết quả của HTTP exchange**, không khẳng định business operation thành công/thất bại hoàn toàn. Ví dụ server đã nhận và ghi một đơn hàng rồi đường trả lời bị ngắt; retry POST mà không có idempotency key có thể tạo đơn hàng trùng.

### 2.3. 204 và 404 với BodyHandler

Nếu dùng `HttpResponse.BodyHandlers.ofString()`:

- `200` kèm text body: trả String tương ứng.
- `204`: response thành công, body thường là chuỗi rỗng. **Đừng bắt JSON parser đọc một String rỗng thành JSON object**.
- `404`/`503`: body cũng có thể chứa thông tin lỗi (JSON hoặc text). Phải đọc/validate riêng theo status, không bỏ qua.
- Nếu dùng `BodyHandlers.discarding()`, bạn có thể có `HttpResponse<Void>` và không giữ body; thích hợp khi chỉ cần metadata/status.

Đừng in toàn bộ body lỗi vào log production. Nó có thể lớn, chứa dữ liệu nhạy cảm hoặc dữ liệu không tin cậy; giới hạn kích thước, loại bỏ secrets và xác định encoding theo API contract.

## 3. Cấu hình HttpClient và HttpRequest cho Java 11

Một cấu hình HTTP client thường dùng:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NORMAL)
        .version(HttpClient.Version.HTTP_2)
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/v1/items"))
        .timeout(Duration.ofSeconds(8))
        .header("Accept", "application/json")
        .GET()
        .build();

HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());
```

Đây là **snippet minh họa**: `api.example.com` là URL mẫu, không yêu cầu bạn truy cập. Cần imports `java.net.URI`, `java.net.http.*`, `java.time.Duration` và exception handling.

### 3.1. Một client dùng lại cho nhiều requests

`HttpClient` đã `build()` là immutable về cấu hình và quản lý connection pools, protocol negotiation cùng tài nguyên dùng chung. Tạo một client mới cho **mỗi request** thường làm giảm khả năng reuse connection, tăng chi phí DNS/TCP/TLS.

**Khuyến nghị:** tái sử dụng một client theo vòng đời service hoặc một nhóm cấu hình rõ ràng; mỗi request tự có URI, timeout và headers riêng. Không dùng cùng một `HttpRequest.Builder` mutable ở nhiều threads nếu không kiểm soát đồng bộ; có thể build các `HttpRequest` độc lập.

**Khác phiên bản:** Java 11 `HttpClient` **không implement `AutoCloseable`**. Các API shutdown/close xuất hiện trên JDK mới, không dùng trong source `--release 11`. Khi chạy Java 11, quản lý vòng đời executor do bạn tự cung cấp riêng nếu có, và tránh tạo client vô hạn.

### 3.2. HTTP/2 là preference, không phải bảo đảm

`version(HttpClient.Version.HTTP_2)` đặt phiên bản ưu tiên, không ép mọi server phải dùng HTTP/2. Với server không hỗ trợ hoặc dùng HTTP/1.1, client có thể sử dụng HTTP/1.1 theo negotiation. `response.version()` cho biết phiên bản thực tế.

Trong test loopback ở mục 9, ta chọn `HTTP_1_1` để tương thích với `com.sun.net.httpserver.HttpServer`, một server fixture tối giản.

## 4. Connect timeout và request timeout

Hai loại timeout áp dụng ở **hai tầng khác nhau**:

| Thuộc tính | Cấu hình | Ý nghĩa |
| --- | --- | --- |
| Connect timeout | `HttpClient.newBuilder().connectTimeout(Duration)` | Thời gian cho **thiết lập một kết nối mới** |
| Request timeout | `HttpRequest.newBuilder().timeout(Duration)` | Thời hạn phản hồi cho một request theo hợp đồng của HttpClient |
| Application deadline | Do ứng dụng tự quản lý | Có thể bao gồm retry, backoff, parse và downstream operations |
| Server-side timeout | Config server, proxy, LB, gateway | Độc lập với client timeout; có thể tạo HTTP 408/504 |

### 4.1. `connectTimeout` chỉ có tác dụng khi cần kết nối mới

Ví dụ:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();
```

Nếu client cần mở TCP connection mới nhưng không thể thiết lập trong khoảng đã định, `send(...)` có thể ném `HttpConnectTimeoutException`; `sendAsync(...)` hoàn tất future với nguyên nhân tương ứng.

**Quan trọng:** khi một request **tái sử dụng connection có sẵn**, connect timeout **không còn là giới hạn hữu ích** cho thời gian server phản hồi. Vì vậy không nên chỉ cấu hình connect timeout rồi nghĩ mọi request sẽ tự giới hạn.

### 4.2. `HttpRequest.Builder.timeout` giới hạn request

```java
HttpRequest req = HttpRequest.newBuilder(
        URI.create("https://api.example.com/report"))
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();
```

Nếu không nhận response theo timeout, `send(...)` ném `HttpTimeoutException`; với `sendAsync(...)`, future hoàn tất exceptionally và cause có thể là `HttpTimeoutException`.

Không tự hiểu đây là “chỉ timeout khi đọc body” hoặc “chắc chắn giới hạn toàn bộ nghiệp vụ từ lúc click đến lúc ghi database”. JDK API định nghĩa giới hạn quá trình nhận HTTP response; một application deadline phải cộng cả queueing, retry delays, parsing và xử lý tiếp. Với `BodyHandlers.ofInputStream()`, application nhận stream rồi có thể tự đọc lâu sau khi phương thức `send` trả về; cần thiết kế lifecycle/timeout của stream phù hợp.

### 4.3. Hai timeout có mối quan hệ thế nào?

- `connectTimeout=2s`, `request.timeout=5s`: một kết nối mới quá chậm có thể gây connect timeout; nếu kết nối kịp nhưng server trả lời chậm thì request timeout có thể xảy ra.
- `connectTimeout=10s`, `request.timeout=1s`: thời hạn request nhỏ hơn có thể là nguyên nhân kết thúc request trước. Không dựa vào một trật tự exception tuyệt đối khi nhiều đồng hồ cạnh tranh.
- Không cấu hình request timeout trên request có thể khiến một HTTP exchange chờ rất lâu. Java 11 docs mô tả không đặt timeout tương đương không giới hạn thời gian cho request theo thuộc tính đó.
- Giá trị `Duration` phải **dương**, không dùng `Duration.ZERO` để biểu thị “chờ mãi”.

### 4.4. Phân biệt exception subtype

`HttpConnectTimeoutException` **extends `HttpTimeoutException`**, và `HttpTimeoutException` extends `IOException`. Vì thế khi catch nên đặt subclass trước superclass:

```java
try {
    HttpResponse<String> response =
            client.send(request, HttpResponse.BodyHandlers.ofString());
    // Xử lý statusCode ở đây.
} catch (HttpConnectTimeoutException e) {
    // Kết nối mới quá thời gian được phép.
} catch (HttpTimeoutException e) {
    // Request quá thời gian được phép.
} catch (IOException e) {
    // Transport/I/O khác.
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Hủy hoặc chuyển trạng thái công việc hiện tại phù hợp.
}
```

Đây là snippet cần imports; không dùng `catch (HttpTimeoutException)` trước `HttpConnectTimeoutException`, nếu không nhánh subclass sẽ không thể đến được.

### 4.5. Timeout không bảo đảm server chưa thực hiện thao tác

Khi client timeout, request có thể **đã được gửi**, server có thể **vẫn đang xử lý** hoặc đã commit database. Điều này quan trọng nhất với POST/PUT/DELETE có side effects.

Không suy luận `HttpTimeoutException` đồng nghĩa “server chưa nhận gì”. Muốn retry an toàn cần xác định **idempotency** hoặc dùng API-side idempotency key/operation ID và trạng thái đối soát.

## 5. Redirect: NEVER, NORMAL, ALWAYS

`HttpClient.Redirect` cung cấp ba policy từ Java 11:

| Policy | Hành vi | Lưu ý |
| --- | --- | --- |
| `NEVER` | **Không tự follow** redirect | Là **default** của HttpClient trong Java 11; nhận response 3xx để xử lý |
| `NORMAL` | Follow redirect trừ trường hợp **HTTPS → HTTP** | Chặn hạ cấp HTTPS sang HTTP, thường hợp lý hơn ALWAYS |
| `ALWAYS` | Follow redirect theo cơ chế HttpClient, kể cả **HTTPS → HTTP** | Có rủi ro an toàn nếu lộ dữ liệu khi downgrade |

Ví dụ:

```java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
```

**Nếu không gọi `followRedirects(...)`, mặc định `NEVER`.** Khi nhận `302`, `HttpResponse.statusCode()` có thể là `302` và `headers().firstValue("Location")` chứa đích chuyển hướng.

### 5.1. Method và body có thể đổi khi redirect

| Status | Cách redirect thường áp dụng | Điểm cần test |
| --- | --- | --- |
| `301` / `302` | Trong JDK HttpClient, một POST theo các status này có thể được **chuyển sang GET** theo implementation note Java 11 | Không mặc định POST body tiếp tục được gửi |
| `303` | Sau POST, client dùng GET để truy cập resource kết quả | Không mong chờ POST được giữ |
| `307` | Giữ HTTP method và body theo semantics | Bảo đảm body publisher có thể gửi lại |
| `308` | Giữ HTTP method và body theo semantics | Chỉ follow cross-origin theo policy tin cậy |

**Ví dụ đã kiểm thử:** POST tới `/redirect307` cho response body `POST` từ endpoint đích; POST tới `/redirect303` cho response body `GET`.

### 5.2. Redirect history và final URI

Khi tự follow, response trả về thường là **response cuối cùng**:

```java
HttpResponse<String> response =
        client.send(req, HttpResponse.BodyHandlers.ofString());

int finalStatus = response.statusCode();
URI finalUri = response.uri();

boolean had302 = response.previousResponse()
        .map(previous -> previous.statusCode() == 302)
        .orElse(false);
```

`previousResponse()` trả `Optional` để truy xuất redirect chain nếu có. Có thể theo nhiều bước bằng cách lặp qua `previousResponse()`, nhưng tránh logging toàn bộ headers có credentials. `response.uri()` là URI response thực tế; kiểm tra khi endpoint cuối cần thuộc allowlist.

### 5.3. Những rủi ro an toàn khi tự follow

- **HTTPS → HTTP downgrade:** tránh `ALWAYS` nếu dữ liệu nhạy cảm; `NORMAL` không follow hướng này.
- **Cross-origin redirect:** `Location` có thể dẫn tới host do attacker kiểm soát; không gửi credential/cookie/token tới đích không tin cậy. Mặc dù client có chính sách xử lý một số headers, ứng dụng vẫn phải quản lý credentials và host allowlist.
- **Redirect vòng lặp:** cần có giới hạn hop; client có cơ chế giới hạn riêng nhưng ứng dụng không nên giả định vô hạn redirect hợp lệ.
- **Replay body:** POST/PUT có body streaming có thể không dễ gửi lại. Một `BodyPublisher` không tái phát được có thể làm redirect/retry thất bại.
- **Method conversion:** tự động theo `302` từ POST có thể đổi thành GET, khiến hành vi server không như mong đợi.
- **SSRF:** không xây proxy/crawler nhận URL từ người dùng rồi follow redirect tới localhost/private/internal metadata endpoints mà không xác thực toàn bộ chuỗi đích.

Nếu môi trường đòi kiểm soát nghiêm ngặt, dùng `NEVER`, tự đọc `Location`, xác thực scheme/host/port/path, chặn mạng riêng hoặc sử dụng một HTTP layer có redirect policy được kiểm soát.

## 6. Phân biệt lỗi kết nối với HTTP error status

### 6.1. Bảng lỗi thường gặp

| Loại | Ví dụ exception/status | Tình huống |
| --- | --- | --- |
| HTTP error | `404` / `429` / `503` | Server đã trả HTTP response; không tự ném IOException |
| TCP connect refused | `java.net.ConnectException` | Không có listener trên host:port hoặc firewall chủ động từ chối |
| TCP connect timeout | `HttpConnectTimeoutException` | Kết nối mới không hình thành kịp |
| Request timeout | `HttpTimeoutException` | HTTP response không nhận được trong thời hạn |
| DNS failure | `UnknownHostException` hoặc I/O cause tương ứng | Host không phân giải được |
| TLS handshake | `SSLHandshakeException` | Certificate, trust chain, protocol/cipher mismatch |
| Remote peer reset / I/O | `IOException` và subclass, có thể wrapped | Kết nối đóng đột ngột khi truyền dữ liệu |
| Application thread interrupted | `InterruptedException` với `send()` | Hủy/đánh thức thread đang chờ |
| Async failure | `CompletableFuture` completed exceptionally | Cause là transport/timeout/TLS hoặc lỗi khác |
| Body parsing | JSON parser exception do ứng dụng | HTTP exchange có thể thành công nhưng payload không hợp lệ |

**Không nên viết logic dựa hoàn toàn vào chuỗi `getMessage()`** của exception như `"Connection refused"`: nội dung thường khác theo OS, JDK, TLS provider hoặc locale. Phân loại theo type/cause và ghi log đủ context.

### 6.2. ConnectException không giống connect timeout

- **ConnectException:** TCP connection bị từ chối hoặc một số lỗi connect khác; có thể xảy ra gần như tức thì.
- **HttpConnectTimeoutException:** hết thời gian chờ thiết lập connection mới; có thể do network filtering/packet loss hoặc đường mạng không phản hồi.
- **HttpTimeoutException:** thời hạn request, không nhất thiết xảy ra ở TCP connection phase.

Đoạn test trong mục 9 tạo một `HttpServer` ở loopback, dừng server rồi dùng một HttpClient mới gọi lại cổng vừa đóng. Nó quan sát được **`ConnectException`**; không cố giả lập TCP blackhole để ép `HttpConnectTimeoutException` vì môi trường mạng thật thường không cho phép test deterministic mà không có quyền cấu hình firewall.

### 6.3. DNS và TLS là những nhánh cần test có kiểm soát

- **DNS:** dùng một test resolver/fake network layer hoặc môi trường integration chuyên biệt. Không đoán rằng mọi tên miền giả đều sinh đúng `UnknownHostException`: proxy, DNS search domain và network config có thể thay đổi.
- **TLS:** thử với certificate thiếu trust chain, hostname mismatch, expired cert hay TLS version mismatch trong một local TLS fixture được cấu hình chủ động. Không “sửa” bằng cách tắt certificate validation trong production.
- **Proxy:** phân biệt lỗi kết nối tới proxy và lỗi upstream, kiểm tra status `407 Proxy Authentication Required` khi phù hợp.
- **Service discovery:** xác định tên host/port, IPv4/IPv6, container namespace, DNS TTL và connection reuse. Một app chạy thành công trên laptop không bảo đảm địa chỉ giống nhau trong Kubernetes.

### 6.4. IOException từ body reading và status hợp lệ

Ngay cả khi đã nhận status line và headers, việc **đọc body** vẫn có thể thất bại vì network reset hoặc dữ liệu không đủ. Với `BodyHandlers.ofString()`, việc đọc body được thực hiện như một phần việc nhận response. Với `BodyHandlers.ofInputStream()` hoặc cách streaming khác, lỗi có thể xảy ra khi **ứng dụng đang đọc stream** sau thời điểm `send()` trả về.

Phải đóng InputStream/close resources khi dùng streaming; không giữ reference tới response body vô hạn. Đọc body JSON rất lớn bằng `ofString()` có thể gây memory pressure, nên lựa chọn streaming/size limits với dữ liệu lớn hoặc không tin cậy.

## 7. send() đồng bộ và sendAsync() bất đồng bộ

### 7.1. send(): exceptions trực tiếp

```java
try {
    HttpResponse<String> r =
            client.send(request, HttpResponse.BodyHandlers.ofString());
    System.out.println("status=" + r.statusCode());
} catch (HttpTimeoutException e) {
    // Timeout.
} catch (IOException e) {
    // Lỗi network/I/O.
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Không nuốt tín hiệu interruption.
}
```

**`InterruptedException`** báo thread bị interrupt trong khi chờ. Nên tái đặt interrupt flag bằng `Thread.currentThread().interrupt()` khi handler không ném tiếp, rồi kết thúc/hủy công việc phù hợp. Việc interrupt/cancel không chứng minh server chưa nhận request.

### 7.2. sendAsync(): trả về CompletableFuture

```java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

future.thenAccept(r -> {
    // HTTP 404/503 cũng vào đây nếu response đã đến hợp lệ.
    System.out.println(r.statusCode());
}).exceptionally(error -> {
    // Lỗi I/O/timeout hoặc lỗi xử lý future.
    System.err.println(error.getClass().getSimpleName());
    return null;
});
```

Đây là **snippet** cần imports, biến `client/request`, và quản lý vòng đời future. Nếu gọi `future.join()` khi future exceptional, Java thường ném `CompletionException` với `getCause()` là exception gốc. Nếu dùng `future.get()`, lỗi thường được bọc trong `ExecutionException`; cách xử lý cần xem `getCause()` và không mất interruption.

**Kết luận:** `sendAsync()` không phải “tự throw IOException khi gọi” theo nghĩa đồng bộ. Phần lớn lỗi từ HTTP exchange đi vào **exceptionally completed future**.

### 7.3. Vì sao retry khi future fail vẫn có thể gây duplicate?

Một future exceptional có thể đến **sau khi server đã thực hiện side effect**. Network reset, timeout hoặc client cancellation chỉ nói rằng **client không nhận kết quả thành công**, không nói chắc server chưa xử lý.

Đối với POST thanh toán/đơn hàng, nếu API hỗ trợ, sử dụng **idempotency key** (giữ nguyên key qua retries) hoặc operation ID và đối soát trạng thái. Với GET/HEAD (không side effects theo contract) retry thường an toàn hơn, nhưng vẫn cần giới hạn để tránh tạo request storm.

## 8. Chiến lược retry và tối ưu thực tế

### 8.1. Không retry theo một quy tắc “5xx là retry hết”

Một policy tốt phải xét:

1. **Loại operation:** GET/HEAD hay write request; body có replay được không?
2. **Loại lỗi:** 503/502/504/429/408 thường là **ứng viên retry**, nhưng không bảo đảm retry luôn đúng; 400/401/403/404 đa số không nên retry y hệt.
3. **Server guidance:** `Retry-After`, rate-limit headers, circuit breaker.
4. **Retry budget:** tổng số attempts, deadline, backoff, jitter, concurrency limits.
5. **Idempotency:** xử lý request trùng không gây side effects ngoài dự kiến.
6. **Observability:** log/metrics nguyên nhân và số attempts, không log credentials.

### 8.2. Phân loại status để quyết định, không throw mọi lỗi giống nhau

```java
static boolean retryCandidate(int status) {
    return status == 408 || status == 429
            || status == 502 || status == 503 || status == 504;
}
```

Đây là **hàm minh họa**, chưa phải retry policy hoàn chỉnh. Ngay cả khi `retryCandidate(503)` true, **chỉ retry** nếu method/body/idempotency/deadline cho phép. Những status khác, kể cả `500` hoặc `409`, có thể cần cách xử lý riêng theo contract API.

### 8.3. Backoff, jitter và Retry-After

`Retry-After` có thể biểu diễn số giây chờ hoặc HTTP-date. Ứng dụng nên:

- Ưu tiên thời hạn server công bố nếu hợp lệ và nằm trong ngân sách.
- Áp dụng exponential backoff có jitter và **max delay** để tránh đồng loạt retry.
- Có max attempts (ví dụ 2–3 đối với endpoint thích hợp) và **overall deadline**.
- Có circuit breaker hoặc rate limit outbound nếu sự cố kéo dài.
- Không ngủ `Thread.sleep` trực tiếp trên event loop hoặc executor bận; dùng scheduler phù hợp với kiến trúc async.

Ví dụ:

```text
Attempt 1: response 503 + Retry-After: 2
Wait (nếu deadline còn đủ) >= 2s theo policy.
Attempt 2: GET idempotent, cùng correlation ID.
Nếu vẫn fail: trả kết quả có phân loại, không retry vô hạn.
```

**Đây là tình huống minh họa**, không phải output từ chương trình chính. Retry-After không phải lệnh bắt buộc vượt mọi deadline. Nếu còn 100ms trong budget, không chờ 2s rồi gọi lại một request đã hết hạn nghiệp vụ.

### 8.4. Tái sử dụng connection và quản lý thời gian

Để tối ưu:

- Tái sử dụng `HttpClient` thay vì tạo mỗi lần.
- Đặt connect timeout, request timeout và application-level deadline hợp lý, đo p95/p99 chứ không chọn tùy tiện.
- Chọn `BodyHandler` phù hợp kích thước và loại body.
- Đóng stream khi dùng streaming, tránh rò rỉ connection.
- Không follow redirects không tin cậy hoặc quá nhiều hops.
- Giới hạn concurrency và retry budget để tránh tự nhân tải lên server đang lỗi.
- Bật metrics latency, status, exception class, redirect count và destination host/endpoint template, nhưng **không log access tokens**.
- Cẩn thận executor dùng cho `sendAsync`/continuations; không block các thread dành cho I/O với parsing nặng hoặc `sleep` tùy tiện.

## 9. Chương trình Java 11 hoàn chỉnh: 14 trường hợp kiểm thử HTTP

Bài lab tạo một HTTP server **chỉ nghe loopback `127.0.0.1`** và chọn một cổng ngẫu nhiên. Không cần Internet, không truy cập API bên ngoài và không ghi file production.

Nó kiểm thử:

- Trả `200` + body; `404` + body; `503`; `204` với body rỗng.
- Mặc định `Redirect.NEVER` giữ nguyên status `302`.
- `Redirect.NORMAL` follow `302` tới `200 OK` và kiểm tra `previousResponse()`.
- `307` giữ phương thức POST; `303` đổi POST thành GET.
- Request timeout đồng bộ `HttpTimeoutException`; HTTP `404` async vẫn hoàn tất bình thường; timeout async bị bọc trong `CompletionException`.
- Dừng server, dùng HttpClient mới để kiểm chứng `ConnectException`.
- Dọn server executor qua `finally`.

**Tệp `HttpFailureModesDemo.java`:**

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.ConnectException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class HttpFailureModesDemo {
    static void reply(HttpExchange ex, int status, String text) throws IOException {
        ex.getRequestBody().readAllBytes();
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type", "text/plain; charset=utf-8");
        if (status == 204) {
            ex.sendResponseHeaders(204, -1);
        } else {
            ex.sendResponseHeaders(status, data.length);
            try (var body = ex.getResponseBody()) {
                body.write(data);
            } catch (IOException clientDisconnected) {
                // Expected for deliberately timed-out /slow test.
            }
        }
        ex.close();
    }

    static void redirect(HttpExchange ex, int status, String location)
            throws IOException {
        ex.getRequestBody().readAllBytes();
        ex.getResponseHeaders().add("Location", location);
        ex.sendResponseHeaders(status, -1);
        ex.close();
    }

    static HttpRequest get(String base, String route) {
        return HttpRequest.newBuilder(URI.create(base + route))
                .GET().build();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService serverPool = Executors.newFixedThreadPool(4);
        server.setExecutor(serverPool);
        server.createContext("/ok", ex -> reply(ex, 200, "OK"));
        server.createContext("/missing", ex -> reply(ex, 404, "MISSING"));
        server.createContext("/unavailable", ex -> reply(ex, 503, "RETRY LATER"));
        server.createContext("/no-content", ex -> reply(ex, 204, ""));
        server.createContext("/redirect302", ex -> redirect(ex, 302, "/ok"));
        server.createContext("/redirect307", ex -> redirect(ex, 307, "/method"));
        server.createContext("/redirect303", ex -> redirect(ex, 303, "/method"));
        server.createContext("/method", ex -> reply(ex, 200, ex.getRequestMethod()));
        server.createContext("/slow", ex -> {
            try {
                Thread.sleep(500);
                reply(ex, 200, "LATE");
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                ex.close();
            }
        });
        server.start();
        String base = "http://127.0.0.1:" + server.getAddress().getPort();

        HttpClient noRedirect = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(2))
                .build();
        HttpClient follow = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .followRedirects(HttpClient.Redirect.NORMAL)
                .connectTimeout(Duration.ofSeconds(2))
                .build();
        try {
            var ok = noRedirect.send(
                    get(base, "/ok"), HttpResponse.BodyHandlers.ofString());
            System.out.println("200 body: " + ok.body());

            var missing = noRedirect.send(
                    get(base, "/missing"), HttpResponse.BodyHandlers.ofString());
            System.out.println("404 status: " + missing.statusCode());
            System.out.println("404 body: " + missing.body());

            var unavailable = noRedirect.send(
                    get(base, "/unavailable"), HttpResponse.BodyHandlers.ofString());
            System.out.println("503 status: " + unavailable.statusCode());

            var noContent = noRedirect.send(
                    get(base, "/no-content"), HttpResponse.BodyHandlers.ofString());
            System.out.println("204 body empty: " + noContent.body().isEmpty());

            var redirectRaw = noRedirect.send(
                    get(base, "/redirect302"), HttpResponse.BodyHandlers.ofString());
            System.out.println("default redirect status: "
                    + redirectRaw.statusCode());

            var redirectFollowed = follow.send(
                    get(base, "/redirect302"), HttpResponse.BodyHandlers.ofString());
            System.out.println("NORMAL redirect result: "
                    + redirectFollowed.statusCode() + " "
                    + redirectFollowed.body());
            System.out.println("redirect history 302: " +
                    redirectFollowed.previousResponse()
                        .map(r -> r.statusCode() == 302).orElse(false));

            HttpRequest post307 = HttpRequest.newBuilder(
                    URI.create(base + "/redirect307"))
                    .POST(HttpRequest.BodyPublishers.ofString("payload")).build();
            var response307 = follow.send(
                    post307, HttpResponse.BodyHandlers.ofString());
            System.out.println("307 preserves method: " + response307.body());

            HttpRequest post303 = HttpRequest.newBuilder(
                    URI.create(base + "/redirect303"))
                    .POST(HttpRequest.BodyPublishers.ofString("payload")).build();
            var response303 = follow.send(
                    post303, HttpResponse.BodyHandlers.ofString());
            System.out.println("303 changes method: " + response303.body());

            HttpRequest slow = HttpRequest.newBuilder(
                    URI.create(base + "/slow"))
                    .timeout(Duration.ofMillis(100))
                    .GET().build();
            try {
                follow.send(slow, HttpResponse.BodyHandlers.ofString());
                System.out.println("sync timeout: NOT THROWN");
            } catch (HttpTimeoutException expected) {
                System.out.println("sync timeout: "
                        + expected.getClass().getSimpleName());
            }

            var asyncStatus = follow.sendAsync(
                    get(base, "/missing"), HttpResponse.BodyHandlers.ofString())
                    .join();
            System.out.println("async 404 status: " + asyncStatus.statusCode());
            try {
                follow.sendAsync(
                        slow, HttpResponse.BodyHandlers.ofString()).join();
                System.out.println("async timeout: NOT THROWN");
            } catch (CompletionException expected) {
                System.out.println("async timeout cause: "
                        + expected.getCause().getClass().getSimpleName());
            }
        } finally {
            server.stop(0);
            serverPool.shutdownNow();
        }

        HttpClient newClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();
        try {
            newClient.send(
                    get(base, "/ok"), HttpResponse.BodyHandlers.ofString());
            System.out.println("connection refusal: NOT THROWN");
        } catch (ConnectException expected) {
            System.out.println("connection refusal: "
                    + expected.getClass().getSimpleName());
        }
    }
}
```

### 9.1. Biên dịch và chạy

Vì server fixture thuộc module `jdk.httpserver` của JDK, khai báo module này khi compile và run. `java.net.http` được dùng từ unnamed module theo classpath, không cần tạo `module-info.java` trong ví dụ.

Linux/macOS:

```bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 HttpFailureModesDemo.java
java --add-modules jdk.httpserver HttpFailureModesDemo
```

Windows PowerShell:

```powershell
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 .\HttpFailureModesDemo.java
java --add-modules jdk.httpserver -cp . HttpFailureModesDemo
```

Chương trình dùng `var` cho biến cục bộ, đã được Java hỗ trợ từ Java 10; nó **biên dịch hợp lệ với `--release 11`**.

**Output chính xác đã kiểm thử (14 dòng):**

```text
200 body: OK
404 status: 404
404 body: MISSING
503 status: 503
204 body empty: true
default redirect status: 302
NORMAL redirect result: 200 OK
redirect history 302: true
307 preserves method: POST
303 changes method: GET
sync timeout: HttpTimeoutException
async 404 status: 404
async timeout cause: HttpTimeoutException
connection refusal: ConnectException
```

Đã xác minh `javac --release 11` thành công, chương trình chạy với exit code 0 và in đúng 14 dòng trong môi trường test cục bộ. Kết quả liên quan connect refusal phụ thuộc cổng còn đóng ở thời điểm gọi; trong một môi trường mạng bị can thiệp đặc biệt, loại IOException có thể khác. Không nên hardcode mọi network failure vào `ConnectException`.

### 9.2. Tại sao timeout test đáng tin?

Endpoint `/slow` cố tình ngủ **500 ms**, trong khi `HttpRequest.timeout` là **100 ms**. Khoảng chênh đủ lớn để test thường ổn định hơn so với sleep 101 ms và timeout 100 ms. Tuy vậy OS scheduling và tải hệ thống vẫn có thể làm test chạy khác; hệ thống CI cần cho phép timeout/test failure được báo rõ, không lặng lẽ bỏ qua.

Server có thread pool riêng để các request khác không bị chặn bởi handler `/slow`. Khi client đã timeout, server có thể vẫn cố gửi response và gặp IOException do connection đã đóng. Trong fixture, lỗi write khi client disconnect được xử lý để không làm nhiễu bài test.

### 9.3. Vì sao test redirect phải kiểm tra method?

Một test chỉ assert final status `200` có thể bỏ sót lỗi nguy hiểm: request ban đầu là POST nhưng cuối cùng server nhận GET. Hai endpoint `/redirect307` và `/redirect303` trả lại tên method ở server đích, giúp test phát hiện rõ:

```text
POST -> 307 -> POST
POST -> 303 -> GET
```

Với API có side effects, cần kiểm tra cả body, headers và idempotency policy nếu theo redirect. Không cho client tự follow redirect tới một origin không kiểm soát chỉ vì status ban đầu là 302.

### 9.4. Vì sao 404/503 không nằm trong catch?

Test gọi `HttpClient.send(...)` và nhận object `HttpResponse` cho `404` lẫn `503`. Nếu chương trình có policy “non-2xx là lỗi”, nó phải **biến response thành kết quả nghiệp vụ hoặc exception của chính ứng dụng** ở lớp API client, không dựa vào `HttpClient` làm thay.

Async test nhận `404` qua `sendAsync(...).join()` bình thường, không có `CompletionException`. Ngược lại timeout async tạo một exceptional future và `join()` bọc nguyên nhân thành `CompletionException`.

### 9.5. Không dùng các output minh họa làm benchmark

Chương trình tạo HTTP server cùng JVM, có sleep và connection management; nó dùng để **kiểm tra semantics**, không phải benchmark throughput/latency production. Không lấy thời gian chạy chương trình hoặc số threads làm chỉ số tối ưu công nghệ. Với benchmark cần setup độc lập, warm-up, load generator, metrics, repeated runs và dữ liệu thống kê phù hợp.

## 10. Test matrix nên có trong một API client thực tế

| Case | Fixture / điều kiện | Assertion |
| --- | --- | --- |
| 200 + JSON hợp lệ | Server trả payload đúng schema | Parse thành công, headers/status hợp lệ |
| 204 | Không có response body | Không cố parse JSON rỗng |
| 404 | Resource không tồn tại | Trả kết quả absent hoặc mapped error đúng contract |
| 400/422 | Request không hợp lệ | Không retry y hệt vô hạn |
| 401 | Chưa có credentials | Luồng auth/refresh có giới hạn |
| 403 | Không có quyền | Fail với phân loại permission |
| 409/412 | Conflict hoặc precondition fail | Reconcile state, tôn trọng ETag/version |
| 429 | Rate-limited, Retry-After | Bounded backoff nếu idempotent |
| 500 | Server error | Không mặc định retry non-idempotent POST |
| 502/503/504 | Gateway/upstream không sẵn sàng | Retry candidate theo deadline/idempotency |
| 301/302 | Redirect có Location | Policy và method handling đúng |
| 303 sau POST | Server yêu cầu chuyển endpoint | Final method GET nếu follow theo contract |
| 307/308 sau POST | Temporary/permanent redirect | Method/body vẫn đúng nếu follow |
| Redirect HTTPS→HTTP | Downgrade destination | `NORMAL` không follow |
| Redirect tới host không tin cậy | Có Location sang domain khác | Không lộ secrets, kiểm tra allowlist |
| Slow response | Local handler chậm hơn request timeout | `HttpTimeoutException` |
| Connect blackhole | Network fixture có packet drop | `HttpConnectTimeoutException` nếu đúng connect phase |
| Connection refused | Không có listener ở cổng | `ConnectException` hoặc lỗi connect tương ứng |
| DNS failure | DNS fixture chuyên biệt | Phân loại nguyên nhân, không phụ thuộc text message |
| TLS invalid certificate | Local HTTPS fixture | `SSLHandshakeException` theo TLS flow |
| Body bị ngắt giữa chừng | Server close/reset | IOException từ exchange/stream, không hiểu là 2xx success hoàn chỉnh |
| Async 404 | Server trả 404 | Future successful với response status 404 |
| Async timeout | Delay > timeout | Future exceptional, unwrap cause |
| Interrupt sync send | Interrupt worker | `InterruptedException`, restore flag |
| Retry POST | Có/không idempotency key | Không tạo duplicate side effects |
| Retry budget exhausted | N lần lỗi, deadline hết | Dừng retry và propagate error có cấu trúc |

Một test suite cần tránh phụ thuộc Internet, đồng hồ thật hoặc API của bên thứ ba nếu không phải integration test. **Local HTTP fixture** kiểm soát hoàn toàn status/redirect/delay. DNS/TLS/blackhole có thể yêu cầu containerized integration environment và phải giữ tài nguyên/permissions rõ ràng.

## 11. Thiết kế kết quả ở tầng API client

Một thư viện gọi HTTP của ứng dụng nên phân tách ít nhất ba loại outcome:

```text
1) Success HTTP and business content
   - status, parsed payload, trace/correlation ID

2) HTTP response but non-success status
   - status, safe error payload, retry hints

3) Transport/protocol failure
   - exception category, endpoint, latency,
     retryability (only after method/idempotency checks)
```

Không biến mọi lỗi thành `null` hoặc một generic `RuntimeException("HTTP failed")` vì sẽ mất thông tin. Cũng không để mọi caller bắt những class network exception ở mỗi tầng nếu một typed result/error abstraction phù hợp hơn.

### 11.1. Ví dụ exception khi muốn non-2xx trở thành lỗi ứng dụng

```java
int code = response.statusCode();
if (code < 200 || code >= 300) {
    throw new IllegalStateException(
            "Remote service returned HTTP " + code);
}
```

Đây là **snippet minh họa**, không phải hành vi mặc định của HttpClient và không phải chính sách phù hợp mọi API. Với `404` dùng làm “resource absent”, có thể trả Optional empty; với `409` có thể đưa người dùng tới luồng conflict resolution.

### 11.2. Không làm mất response diagnostics

Trong error mapping, có thể lưu:

- Status code thực.
- Endpoint template (không kèm credentials).
- Correlation/trace ID nếu server cung cấp.
- Retry-After nếu có, đã parse hợp lệ.
- Latency theo `System.nanoTime()` để đo elapsed time.
- Exception class và cause chain, nhưng loại bỏ token/PII.

Không log đầy đủ URL nếu query chứa secrets. Hạn chế logging body lỗi và headers nhạy cảm như `Authorization`, `Cookie`, `Set-Cookie`.

## 12. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Bắt IOException để xử lý HTTP 404 | Không vào catch, bỏ sót lỗi nghiệp vụ | Kiểm tra `response.statusCode()` |
| Coi HTTP 503 là connection failure | Retry policy/metrics bị sai | Phân loại HTTP response riêng |
| Coi HTTP 200 là business success chắc chắn | JSON payload có thể invalid/semantic error | Validate body/schema/contract |
| Parse JSON từ body 204 | Body rỗng, parser lỗi | Xử lý 204 riêng |
| Chỉ đặt connect timeout | Connection reuse làm timeout vô tác dụng | Đặt request timeout phù hợp |
| Chỉ đặt request timeout rồi coi là total SLA | Retry/backoff/parse nằm ngoài | Dùng overall deadline |
| Đặt timeout 0 hoặc âm | Builder ném exception | Dùng Duration dương |
| Bắt HttpTimeoutException trước HttpConnectTimeoutException | Nhánh subclass không chạy | Catch subtype trước |
| Không restore interrupt flag | Làm mất cancellation signal | `Thread.currentThread().interrupt()` |
| Coi timeout nghĩa server chưa xử lý | Retry POST có thể tạo duplicate | Idempotency key/reconciliation |
| Không unwrap CompletionException | Chỉ thấy wrapper, không phân loại timeout | Dùng `getCause()`, kiểm tra loại |
| Dùng CompletableFuture.join() trên event loop | Gây blocking và hạn chế concurrency | Async composition phù hợp |
| Tạo HttpClient cho mỗi request | Mất connection reuse, tăng TCP/TLS overhead | Tái sử dụng client |
| Cho redirect ALWAYS với credential | HTTPS→HTTP downgrade/cross-origin risk | NORMAL/NEVER + allowlist |
| POST follow 302 rồi giả định POST còn nguyên | Có thể chuyển sang GET | Test method hoặc tự handle redirect |
| 307 redirect với body publisher one-shot | Body có thể không gửi lại được | Chỉ follow nếu replay safe |
| Follow redirect vô hạn | Vòng redirect/latency | Policy với giới hạn hops |
| Retry mọi 5xx và 429 vô hạn | Retry storm, quá tải thêm | Backoff jitter, max attempts/deadline |
| Retry POST không idempotency | Giao dịch/đơn hàng trùng | Operation ID/idempotency key |
| Log toàn bộ error payload | Lộ PII/secret, log flooding | Mask/limit body, bounded logs |
| Dùng sleep sát timeout để assert | Test flaky vì scheduler | Chênh lệch delay/timeout rõ |
| Dùng server bên ngoài để test 404/503 | Test phụ thuộc mạng/DNS bên thứ ba | Local fixture |
| Tắt TLS validation cho nhanh | Kết nối không an toàn | Dùng certificate fixture đúng |
| Giả định Java 11 có `HttpClient.close()` | Compile error với `--release 11` | Không dùng API chỉ có từ JDK mới |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `HttpClient.send()` có ném `IOException` khi server trả `404`?  
**Đáp án:** Không, nếu server gửi response hợp lệ; nhận `HttpResponse` có `statusCode()==404`.

**Câu 2.** Connect timeout có còn áp dụng khi reuse connection?  
**Đáp án:** Không theo ý nghĩa thiết lập connection mới; cần request timeout để chặn trao đổi chậm.

**Câu 3.** `HttpConnectTimeoutException` có kế thừa `HttpTimeoutException`?  
**Đáp án:** Có, và cả hai thuộc nhánh `IOException`.

**Câu 4.** Mặc định HttpClient Java 11 tự follow redirect không?  
**Đáp án:** Không; policy mặc định `NEVER`.

**Câu 5.** `NORMAL` và `ALWAYS` khác nhau quan trọng nhất ở đâu?  
**Đáp án:** `NORMAL` không follow từ HTTPS sang HTTP; `ALWAYS` có thể follow downgrade.

**Câu 6.** Sau POST + 303, server đích nhận method gì trong ví dụ?  
**Đáp án:** `GET`.

**Câu 7.** Sau POST + 307, server đích nhận method gì?  
**Đáp án:** `POST` với body publisher có thể phát lại.

**Câu 8.** `sendAsync` gặp HTTP 503 có complete exceptionally mặc định không?  
**Đáp án:** Không, 503 vẫn là response; future có thể complete successfully với status 503.

**Câu 9.** `sendAsync(...).join()` gặp timeout sẽ ném gì?  
**Đáp án:** Thường `CompletionException`, cause là `HttpTimeoutException` hoặc subtype.

**Câu 10.** `ConnectException` có thể là timeout connect không?  
**Đáp án:** Connect refusal và connect timeout khác nhau; khi connection mới thực sự quá thời hạn, `HttpConnectTimeoutException` được dùng theo API.

**Câu 11.** Vì sao timeout của POST không đủ cơ sở retry an toàn?  
**Đáp án:** Server có thể đã commit operation dù client chưa nhận response; cần idempotency/reconciliation.

**Câu 12.** Vì sao bài lab không cố giả lập TLS handshake với chứng chỉ công khai?  
**Đáp án:** Cần fixture TLS/cert được kiểm soát; Internet/CA/network bên ngoài làm test không tái lập.

**Câu 13.** Java 11 có thể dùng `try (HttpClient c = ...)` vì client AutoCloseable không?  
**Đáp án:** Không. `HttpClient` Java 11 chưa có hợp đồng `AutoCloseable`; các lifecycle APIs được bổ sung sau.

**Câu 14.** Khi request 204, có nên luôn parse body thành object JSON không?  
**Đáp án:** Không; body rỗng theo ngữ nghĩa No Content.

**Câu 15.** Một retry policy tốt cần thêm gì ngoài HTTP status?  
**Đáp án:** HTTP method, idempotency, retry budget/deadline, Retry-After, backoff/jitter và an toàn dữ liệu.

## 14. Checklist trước khi đưa HTTP client vào production

- [ ] Chỉ dùng public `java.net.http` API Java 11+, không dựa vào các hàm close/shutdown chỉ có trên JDK mới.
- [ ] Có `connectTimeout` và `request.timeout` riêng với Duration dương.
- [ ] Có overall deadline bao trùm retry/backoff/parse.
- [ ] Phân biệt HTTP error response và IOException/timeout.
- [ ] Xử lý 204, 4xx, 429, 5xx theo contract nghiệp vụ.
- [ ] Phân biệt ConnectException, HttpConnectTimeoutException, HttpTimeoutException, TLS/DNS errors.
- [ ] Catch subclass trước superclass; restore interrupt flag sau InterruptedException.
- [ ] Async unwrap CompletionException/ExecutionException đúng cách.
- [ ] Tái sử dụng HttpClient; kiểm soát concurrency và tài nguyên streaming.
- [ ] Redirect policy rõ; kiểm tra downgrade/cross-origin/method/replay.
- [ ] Không retry non-idempotent POST khi thiếu idempotency protection.
- [ ] Có max attempts, exponential backoff, jitter, Retry-After và circuit-breaker khi phù hợp.
- [ ] Test 200, 204, 302, 303, 307, 404, 503, timeout và connect refusal bằng local fixture.
- [ ] Có integration environment riêng cho DNS/TLS/proxy/blackhole.
- [ ] Metrics latency, status, redirect counts, exception cause và retry attempts.
- [ ] Log không chứa Authorization tokens, cookies, secrets hoặc body nhạy cảm.
- [ ] Endpoint và redirect targets được validate/allowlist để tránh SSRF.
- [ ] Tài liệu API khớp Java 11 runtime và JDK mới nếu nâng phiên bản.

## 15. Kết luận và nguồn tài liệu chính thức

**Nguyên tắc tổng kết:**

- **HTTP 4xx/5xx vẫn là HttpResponse**, không mặc định là IOException.
- **Connect timeout** chỉ dành cho thiết lập connection mới; **request timeout** giới hạn một HTTP request, không phải toàn bộ workflow nghiệp vụ.
- **Redirect policy mặc định NEVER**; `NORMAL` không downgrade HTTPS→HTTP; `303` có thể đổi POST thành GET, `307` giữ method.
- **send()** ném IOException/InterruptedException trực tiếp; **sendAsync()** trả future và lỗi transport thường nằm trong cause của CompletionException/ExecutionException khi đợi.
- **Timeout không chứng minh server chưa xử lý side effects**; retry có giới hạn và phải gắn với idempotency.
- Dùng **local HTTP fixture** để kiểm thử deterministic status/redirect/timeout; dùng integration test chuyên biệt cho DNS/TLS/blackhole.
- Ví dụ `HttpFailureModesDemo` đã biên dịch với `--release 11` và chạy đúng **14 dòng stdout**, không cần Internet.

**Tài liệu được duy trì và còn áp dụng:**

1. [Oracle Java 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html).
2. [Oracle Java 11 — HttpClient.Builder / connectTimeout](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html).
3. [Oracle Java 11 — HttpClient.Redirect](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html).
4. [Oracle Java 11 — HttpRequest.Builder / timeout](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html).
5. [Oracle Java 11 — HttpResponse / previousResponse](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html).
6. [Oracle Java 11 — HttpTimeoutException](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpTimeoutException.html).
7. [Oracle Java 11 — HttpConnectTimeoutException](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html).
8. [Oracle Java 11 — BodyHandlers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html).
9. [OpenJDK JEP 321 — HTTP Client (Standard)](https://openjdk.org/jeps/321).
10. [Oracle Java 26 — HttpClient hiện hành](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html).
11. [IETF RFC 9110 — HTTP Semantics, status codes và redirect](https://www.rfc-editor.org/rfc/rfc9110).
12. [IETF RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111).

**Lưu ý tương thích:** Trong Java 11, `java.net.http` hỗ trợ HTTP/1.1 và HTTP/2. Nếu dùng tài liệu JDK mới có API version/lifecycle khác, kiểm tra `Since` của từng method thay vì cho rằng nó có trong Java 11.