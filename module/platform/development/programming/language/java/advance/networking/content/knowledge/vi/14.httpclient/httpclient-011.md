# Chính sách chuyển hướng NEVER, NORMAL, ALWAYS và chuỗi phản hồi trước

## 1. Bài toán và mục tiêu

Khi một Java application gửi HTTP request, server có thể trả về status `301 Moved Permanently`, `302 Found`, `303 See Other`, `307 Temporary Redirect` hoặc `308 Permanent Redirect` cùng header `Location` để hướng client tới một URI khác. Ứng dụng phải quyết định **có tự gửi request mới tới URI đó không**, theo **chính sách nào**, và **ghi nhận những phản hồi trung gian ra sao**.

Từ Java 11, package `java.net.http` cung cấp `HttpClient` với enum `HttpClient.Redirect` và phương thức `HttpResponse.previousResponse()`. Ba policy được hỗ trợ trong Java 17 là:

- **`NEVER`:** không tự theo redirect. Ứng dụng nhận response 3xx để tự quyết định.
- **`NORMAL`:** tự theo redirect hợp lệ, **ngoại trừ HTTPS → HTTP** để ngăn downgrade từ kết nối bảo vệ TLS xuống plaintext.
- **`ALWAYS`:** tự theo redirect hợp lệ kể cả **HTTPS → HTTP**; cần đánh giá rủi ro bảo mật và ngữ cảnh ứng dụng.

Một redirect không xóa sạch mọi dấu vết request trước: response cuối cùng có thể truy ngược những **intermediate responses** qua `previousResponse()`. Tuy nhiên các response trung gian **không giữ lại body** như response cuối: `body() == null` với response lấy từ `previousResponse()`.

Sau bài học, bạn cần:
1. Nêu được default redirect policy của `HttpClient` Java 17 và khi nào chọn từng policy.
2. Phân biệt `3xx` trả trực tiếp với `2xx` sau nhiều lần tự chuyển hướng.
3. Đọc đúng `response.uri()`, `response.request().uri()`, `response.statusCode()` và chuỗi `previousResponse()`.
4. Hiểu ảnh hưởng status `301/302/303/307/308` lên **HTTP method** và **request body**.
5. Biết giải quyết `Location` tương đối và không nhầm `Location` với URI đã được request.
6. Tránh HTTPS downgrade, redirect tới host không tin cậy, SSRF, lộ thông tin và vòng lặp redirect.
7. Biên dịch/chạy ví dụ **Java 17+ trên loopback** để kiểm chứng các trường hợp, không cần Internet.

## 2. Redirect là phản hồi HTTP, không phải lỗi kết nối TCP

Một cuộc trao đổi HTTP điển hình:

```http
GET /old-path HTTP/1.1
Host: example.com

HTTP/1.1 302 Found
Location: /new-path
Content-Type: text/plain

Resource moved
```

Response `302` ở trên **vẫn là phản hồi HTTP hợp lệ**. Nó đề nghị client gửi **một request mới** tới `/new-path`. Redirect không phải TCP retry ở tầng transport, và cũng không bảo đảm request tiếp theo sẽ thành công.

Nếu client tự theo redirect, quá trình có thể là:

```text
GET https://example.com/old-path
  ↓
302 Location: /new-path
  ↓
GET https://example.com/new-path
  ↓
200 OK (body của tài nguyên)

Ứng dụng nhận HttpResponse cuối:
  statusCode() = 200
  uri() = https://example.com/new-path
  previousResponse() -> response 302 của /old-path
```

Nếu policy không tự theo:
- `statusCode()` có thể là `302`.
- `uri()` là URI của request đã tạo phản hồi `302`, tức `/old-path`.
- `headers().firstValue("Location")` có thể chứa `/new-path`.
- `previousResponse()` thường rỗng vì **không có intermediate response do việc follow redirect** trong lần gửi này.
- Body của response `302` đang được trả trực tiếp cho caller **có thể đọc được** bằng `BodyHandler` đã chọn.

**Quan trọng:** gọi `send()` thành công không đồng nghĩa nhận status `200`. Status 3xx, 4xx, 5xx là nội dung phản hồi HTTP; API không mặc định biến tất cả thành `IOException`.

## 3. Ba chính sách Redirect trong Java 17

| Policy | Có tự follow redirect hợp lệ? | HTTPS → HTTP? | Khi nào dùng |
| --- | --- | --- | --- |
| `HttpClient.Redirect.NEVER` | Không | Không tự theo | API client cần validate đích, lấy 3xx nguyên bản, crawler, security-sensitive |
| `HttpClient.Redirect.NORMAL` | Có | **Không** | Client theo redirect thông thường nhưng chặn downgrade TLS |
| `HttpClient.Redirect.ALWAYS` | Có | **Có thể** | Chỉ trong trường hợp được kiểm soát, đã hiểu rõ an toàn của đích |

`NORMAL` khác `ALWAYS` ở đúng điểm trọng tâm của enum: **redirect từ URL HTTPS sang URL HTTP**. Các policy không buộc một response 304, 300 hoặc 3xx thiếu/không hợp lệ `Location` phải dẫn tới network request mới. Quy tắc cụ thể của implementation, status code, redirect-limit và security settings vẫn quyết định một redirect có thực hiện được hay không.

### Bảng hướng chuyển scheme

| Từ URL | Đến URL | NEVER | NORMAL | ALWAYS |
| --- | --- | --- | --- | --- |
| `http://a` | `http://b` | Không follow | Có thể follow | Có thể follow |
| `http://a` | `https://b` | Không follow | Có thể follow | Có thể follow |
| `https://a` | `https://b` | Không follow | Có thể follow | Có thể follow |
| `https://a` | `http://b` | Không follow | **Chặn** | Có thể follow |

Các ô “có thể follow” giả định server trả **redirect response hợp lệ** và không có rào cản riêng như đích URI không hợp lệ, giới hạn redirect hoặc I/O failure. Đó không phải cam kết chắc chắn mọi request thành công.

Một lưu ý quan trọng: **`NORMAL` chỉ chặn HTTPS → HTTP; nó không kiểm soát toàn bộ đích redirect**. Nó vẫn có thể theo `Location` sang host, IP hoặc port khác. Với URI do người dùng/remote server không đáng tin quyết định, cần thêm allowlist và chính sách ứng dụng.

## 4. Mặc định của HttpClient là NEVER

Theo tài liệu Java SE 17:
- `HttpClient.newHttpClient()` tương đương `HttpClient.newBuilder().build()` với các giá trị mặc định.
- Nếu builder **không gọi** `followRedirects(...)`, mặc định là **`HttpClient.Redirect.NEVER`**.
- `client.followRedirects()` trả policy đã cấu hình.

Ví dụ:

```java
HttpClient client = HttpClient.newHttpClient();
System.out.println(client.followRedirects()); // NEVER
```

Đây là mảnh code với import `java.net.http.HttpClient`, chạy trong một phương thức thích hợp. Không suy ra Java sẽ tự follow giống trình duyệt khi code không có `followRedirects`. Với `HttpClient` gốc, response 302 vẫn được trả trực tiếp nếu không có xử lý nào khác.

Cách chỉ định tường minh:

```java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
```

`HttpClient` sau khi build là object **immutable về cấu hình**. Không có `client.setFollowRedirects(...)` để đổi policy cho chính instance đó; cần tạo client khác nếu cần policy khác. Một client có thể tái sử dụng cho nhiều request và chia sẻ connection resources của chính nó.

## 5. NEVER: nhận 3xx để tự quyết định

Chọn `NEVER` khi ứng dụng:
- Cần hiển thị hoặc log đúng response ban đầu từ origin.
- Đang xây API gateway/proxy/crawler với policy redirect riêng.
- Phải kiểm tra **scheme, host, port, resolved address, path** trước khi gửi request tới đích mới.
- Cần giữ chính xác method/body hoặc kiểm tra auth/cookie trên từng hop.
- Không muốn server từ xa quyết định tự động nơi client kết nối tiếp theo.

```java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/old"))
        .GET().build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());

System.out.println(response.statusCode());
System.out.println(response.headers().firstValue("Location"));
```

Đây là **mảnh code**; cần imports `java.net.URI`, `java.net.http.*` và `throws IOException, InterruptedException` hoặc xử lý ngoại lệ. Chương trình cần Internet và endpoint demo phù hợp, nên **không khẳng định stdout cố định**.

Nếu gặp `302`, đoạn code hiển thị `302` và `Optional<String>` từ `Location`. Không có tự động request tới location; caller phải chọn có gửi thêm request hay không.

**Không nhầm:** policy `NEVER` không cấm chương trình **tự viết code** redirect sau đó. Nó chỉ tắt tính năng **automatic** follow trong `HttpClient`.

## 6. NORMAL: tự theo redirect nhưng tránh hạ từ HTTPS xuống HTTP

`NORMAL` là lựa chọn tiện lợi cho nhiều ứng dụng muốn tự theo các redirect thông thường:

```java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .connectTimeout(Duration.ofSeconds(5))
        .build();
```

Đây là mảnh code, cần import `java.net.http.HttpClient` và `java.time.Duration`. Các request vẫn nên đặt `HttpRequest.timeout(...)` theo nhu cầu.

Các ví dụ logic:
- `http://a.example/old` → `https://a.example/new`: được policy NORMAL cho phép.
- `https://a.example/old` → `https://b.example/new`: được NORMAL cho phép **về hướng scheme**, nhưng vẫn cần đánh giá cross-host.
- `https://a.example/old` → `http://a.example/new`: **NORMAL từ chối tự follow downgrade**. Ứng dụng sẽ thấy intermediate 3xx nếu không có follow khả thi, tùy các bước trước.

Vì sao chặn downgrade? Nếu đã kết nối HTTPS với certificate validation đúng, request tiếp theo qua HTTP sẽ gửi dữ liệu **không được TLS bảo vệ**; cookies/header/body có thể lộ trên mạng, tùy request được gửi ra. Dùng `NORMAL` tránh một kiểu downgrade tự động.

**Điều NORMAL không giải quyết:**
- Không xác nhận redirect target thuộc một danh sách host được phép.
- Không giới hạn redirect sang IP private, loopback, cloud metadata hoặc internal services.
- Không tự chứng minh `Authorization`/`Cookie`/custom headers được xử lý theo policy bảo mật của ứng dụng.
- Không ngăn server tạo redirect loop mãi về mặt logic; implementation có retry/redirect limit nhưng ứng dụng phải coi giới hạn là một failure mode.
- Không bảo đảm idempotency của request có body.

## 7. ALWAYS: theo redirect kể cả HTTPS sang HTTP

`ALWAYS` cho phép tự follow nhiều đường redirect hơn `NORMAL`; riêng chuyển **HTTPS → HTTP** là điểm khiến policy này cần cân nhắc an toàn:

```java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.ALWAYS)
        .build();
```

Ví dụ:

```text
GET https://shop.example/checkout
  ↓
302 Location: http://shop.example/checkout
  ↓ (ALWAYS có thể cho follow)
GET http://shop.example/checkout
```

Chỉ cần người dùng/ứng dụng tưởng rằng toàn bộ hành trình là HTTPS nhưng thực tế request được gửi sang HTTP, dữ liệu có thể đi qua mạng không mã hóa. Việc đã nhìn thấy TLS certificate hợp lệ ở hop đầu không bảo vệ hop sau. Không dựa vào tên `ALWAYS` để kết luận “redirect an toàn trong mọi trường hợp”.

Khi nào cân nhắc `ALWAYS`? Thường chỉ khi:
- Môi trường kiểm soát hoàn toàn, redirect đích không mang dữ liệu nhạy cảm.
- Protocol/application cho phép downgrade một cách có chủ ý.
- Có network segmentation và chính sách bảo mật rõ ràng.
- Các URI và việc chuyển header/method/body đã được thẩm định.

Với API chứa token, session, thông tin cá nhân hoặc giao dịch quan trọng, **`NEVER` kèm redirect thủ công có kiểm tra** hoặc `NORMAL` cộng với kiểm soát origin thường phù hợp hơn `ALWAYS`. Dùng `ALWAYS` đơn thuần cho mục đích “ít bị lỗi hơn” là một đánh đổi bảo mật không đáng có.

## 8. Location có thể là đường dẫn tương đối

Server có thể trả:

```http
HTTP/1.1 302 Found
Location: ../v2/items?page=2
```

Đây là **URI-reference tương đối**, không phải absolute URL. Với một request tới `https://api.example.com/v1/items/42`, Java `URI.resolve(...)` có thể giải quyết relative reference theo base URI; kết quả cụ thể phụ thuộc cấu trúc path và quy tắc RFC 3986.

Mảnh code minh họa:

```java
URI source = URI.create("https://api.example.com/v1/items/42");
URI target = source.resolve("../v2/items?page=2");
System.out.println(target);
```

Nếu chạy, target là `https://api.example.com/v1/v2/items?page=2` theo quy tắc relative path resolution của URI. Đây chỉ là việc **resolve cú pháp**, không phải xác minh target an toàn.

Phân biệt:
- `Location: /new` → absolute path cùng origin (nếu base là URL HTTP/HTTPS thông thường).
- `Location: https://other.example/new` → absolute URI tới host khác.
- `Location: ../new` → relative path theo vị trí base.
- `Location: //other.example/new` → network-path reference, thừa hưởng scheme nhưng **đổi host**.
- `Location` thiếu, sai cú pháp hoặc scheme không hỗ trợ → đừng cố follow mù.

Khi redirect tự động, `HttpClient` xử lý URI của redirect theo implementation. Khi làm manual redirect, dùng `URI.resolve(...)` đúng base của **response hiện tại**, rồi validate absolute URI sau resolve. Không nối chuỗi URL bằng toán tử `+` hoặc tin rằng location bắt đầu bằng `/` nên tự nhiên an toàn.

## 9. HttpResponse sau khi client đã tự chuyển hướng

Một chuỗi giả định:

```text
GET /start
   │
   └── 302 Location: /middle
          │
          └── 307 Location: /final
                 │
                 └── 200 OK + body "OK-final"
```

Nếu client follow tự động và hoàn tất:
- `response.statusCode() == 200`.
- `response.uri()` là URI đã tạo **response cuối cùng**, ví dụ `.../final`.
- `response.request().uri()` là URI của **request ứng với response cuối**, không nhất thiết là initiating request được đưa vào `send(...)`.
- `response.headers()` là header của response cuối, không phải tập header gộp của các hop.
- `response.body()` là body của **response cuối** theo `BodyHandler<T>` đã chọn.
- `response.previousResponse()` có thể chứa response của hop trước, ví dụ 307.
- Gọi tiếp `previousResponse()` trên response 307 có thể có response 302, v.v.

Một bảng xem dữ liệu sau khi follow hai lần:

| Đối tượng | `statusCode()` | `uri().getPath()` | `body()` |
| --- | ---: | --- | --- |
| Response chính caller nhận | `200` | `/final` | `"OK-final"` |
| `response.previousResponse().get()` | `307` | `/middle` | **`null`** |
| `response.previousResponse().get().previousResponse().get()` | `302` | `/start` | **`null`** |

Chính vì vậy, **không suy ra số hop từ status cuối**. Chỉ nhìn `200` không biết endpoint đã chuyển từ đâu và có từng đi qua host khác hay không. Khi cần audit, hãy thu thập chain của từng intermediate response.

## 10. previousResponse() là một linked chain, không phải một danh sách

Chữ ký trong Java 17:

```java
Optional<HttpResponse<T>> previousResponse()
```

Phương thức trả:
- `Optional.empty()` nếu **không có intermediate response trước đó**.
- `Optional<HttpResponse<T>>` chứa intermediate response gần nhất nếu có; bản thân nó lại có `previousResponse()`.
- Intermediate response có thể xuất hiện do **redirection hoặc authentication**, không chỉ redirect.

Vì vậy `previousResponse()` **không phải** một list `List<HttpResponse<?>>` và cũng không tự cho biết toàn bộ “lịch sử mọi request trong client”. Nó chỉ diễn tả các response trung gian liên quan đến **một HTTP exchange** vừa hoàn tất.

Một cách duyệt an toàn:

```java
Optional<HttpResponse<String>> cursor = response.previousResponse();
while (cursor.isPresent()) {
    HttpResponse<String> previous = cursor.get();
    System.out.println(previous.statusCode()
            + " " + previous.uri()
            + " Location=" + previous.headers()
                    .firstValue("Location").orElse("-"));
    cursor = previous.previousResponse();
}
```

Đây là mảnh code, biến `response` là `HttpResponse<String>` đã có. Vòng này đi **từ gần nhất về xa nhất**:
- Response cuối `200` không thuộc danh sách `previousResponse` mà đang nằm ở `response`.
- Hop gần nhất có thể là `307 /middle`.
- Hop xa hơn có thể là `302 /start`.
- Cuối chuỗi, `Optional.empty()` kết thúc vòng.

Đừng dùng `while (response.previousResponse().isPresent())` mà không cập nhật cursor; sẽ lặp vô hạn trên cùng đối tượng response.

## 11. Body của intermediate response bị bỏ, không lưu lại

Theo `HttpResponse.body()` Java 17: **nếu HttpResponse được trả từ `previousResponse()` thì `body()` trả `null`**. Điều này đúng ngay cả khi server đã gửi body thật ở response 302/307.

Vì sao? Automatic redirect cần xử lý body của các hop để tiếp tục trao đổi và không cung cấp nó cho ứng dụng dưới dạng body của response cuối. Metadata như `statusCode`, `headers`, `uri` và `request` vẫn hỗ trợ kiểm tra chain, nhưng **không thể dùng `previousResponse().get().body()` để lấy nguyên payload của redirect**.

Hai tình huống khác nhau:

```text
Redirect.NEVER:
  server 302 + body "redirect-body"
  caller nhận response 302 trực tiếp
  response.body() == "redirect-body"  (với BodyHandlers.ofString)

Redirect.NORMAL:
  server 302 + body "redirect-body", rồi 200 + body "OK-final"
  caller nhận response 200
  response.body() == "OK-final"
  response.previousResponse().get().body() == null
```

**Không nhầm `null` với chuỗi rỗng `""`.** `null` ở intermediate body là đặc tả của API; không nhất thiết server đã gửi body rỗng. Nếu việc audit bắt buộc phải giữ nội dung body của từng hop, tự follow với `NEVER` và `BodyHandler` phù hợp để thu thập trước khi quyết định request tiếp theo, có giới hạn size/timeout vì body remote có thể lớn.

## 12. Ví dụ Java 17+ chạy được: NEVER, NORMAL, ALWAYS và lịch sử 302 → 307 → 200

Chương trình sau tạo HTTP server cục bộ bằng `com.sun.net.httpserver.HttpServer` và dùng `java.net.http.HttpClient` gửi request trên **127.0.0.1**. Không cần Internet, DNS công cộng hoặc chứng chỉ TLS. Chương trình chứng minh:
- `NEVER` dừng tại `302`, giữ body redirect ban đầu, không có `previousResponse`.
- `NORMAL` và `ALWAYS` trên **đường HTTP → HTTP** đều theo hai lần redirect để nhận `200`.
- `previousResponse()` cho chuỗi `307 /middle` rồi `302 /start`, với body ở từng hop bằng `null`.
- `HttpResponse.request().uri()` là URI cuối cùng.
- Status 301/302/303/307/308 ảnh hưởng tới `POST` thế nào.

**Lưu ý:** local demo sử dụng **HTTP plaintext trên loopback** chỉ để test chuyển hướng; nó **không** minh họa việc gửi credential qua HTTP hoặc chứng minh HTTPS → HTTP policy bằng network thật. Sự khác biệt `NORMAL`/`ALWAYS` đối với downgrade được mô tả từ chính API contract ở mục 3, 6, 7.

Lưu đúng tên **`RedirectPolicyDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public class RedirectPolicyDemo {
    private static void reply(HttpExchange exchange, int code, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(code, bytes.length);
        try (var output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    private static void redirect(HttpExchange exchange, int code, String target)
            throws IOException {
        exchange.getResponseHeaders().add("Location", target);
        reply(exchange, code, "redirect-body");
    }

    private static String history(HttpResponse<String> response) {
        List<String> hops = new ArrayList<>();
        Optional<HttpResponse<String>> previous = response.previousResponse();
        while (previous.isPresent()) {
            HttpResponse<String> hop = previous.get();
            hops.add(hop.statusCode() + "@" + hop.uri().getPath()
                    + "(body=" + hop.body() + ")");
            previous = hop.previousResponse();
        }
        return hops.isEmpty() ? "-" : String.join(" <- ", hops);
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/start", e -> redirect(e, 302, "/middle"));
        server.createContext("/middle", e -> redirect(e, 307, "/final"));
        server.createContext("/final", e -> reply(e, 200, "OK-final"));
        for (int status : new int[]{301, 302, 303, 307, 308}) {
            int code = status;
            server.createContext("/post" + code,
                    e -> redirect(e, code, "/echo"));
        }
        server.createContext("/echo", e -> reply(e, 200,
                e.getRequestMethod() + ":" +
                new String(e.getRequestBody().readAllBytes(),
                        StandardCharsets.UTF_8)));
        server.start();

        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort());
            System.out.println("default=" +
                    HttpClient.newHttpClient().followRedirects());

            for (HttpClient.Redirect policy : HttpClient.Redirect.values()) {
                HttpClient client = HttpClient.newBuilder()
                        .followRedirects(policy)
                        .connectTimeout(Duration.ofSeconds(3))
                        .version(HttpClient.Version.HTTP_1_1)
                        .build();
                HttpRequest request = HttpRequest.newBuilder(
                        base.resolve("/start"))
                        .timeout(Duration.ofSeconds(5))
                        .GET().build();
                HttpResponse<String> response = client.send(
                        request, HttpResponse.BodyHandlers.ofString());
                System.out.println(policy + ": status=" + response.statusCode()
                        + " uri=" + response.uri().getPath()
                        + " request=" + response.request().uri().getPath()
                        + " body=" + response.body());
                System.out.println("  previous=" + history(response));
            }

            HttpClient client = HttpClient.newBuilder()
                    .followRedirects(HttpClient.Redirect.NORMAL)
                    .build();
            for (int status : new int[]{301, 302, 303, 307, 308}) {
                HttpRequest request = HttpRequest.newBuilder(
                        base.resolve("/post" + status))
                        .timeout(Duration.ofSeconds(5))
                        .POST(HttpRequest.BodyPublishers.ofString("payload"))
                        .build();
                HttpResponse<String> response = client.send(
                        request, HttpResponse.BodyHandlers.ofString());
                System.out.println("POST " + status + " -> "
                        + response.body() + " previous="
                        + response.previousResponse()
                                .map(HttpResponse::statusCode).orElse(-1));
            }
        } finally {
            server.stop(0);
        }
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac RedirectPolicyDemo.java
java RedirectPolicyDemo
```

Kết quả stdout đã kiểm tra bằng `javac --release 17` và thực thi:

```text
default=NEVER
NEVER: status=302 uri=/start request=/start body=redirect-body
  previous=-
ALWAYS: status=200 uri=/final request=/final body=OK-final
  previous=307@/middle(body=null) <- 302@/start(body=null)
NORMAL: status=200 uri=/final request=/final body=OK-final
  previous=307@/middle(body=null) <- 302@/start(body=null)
POST 301 -> GET: previous=301
POST 302 -> GET: previous=302
POST 303 -> GET: previous=303
POST 307 -> POST:payload previous=307
POST 308 -> POST:payload previous=308
```

### Đọc output

1. `default=NEVER` xác nhận không gọi `followRedirects` thì mặc định không follow.
2. `NEVER` giữ status 302 và body `redirect-body` của server vì response này được trả **trực tiếp**.
3. Trên đường thử chỉ có `http://127.0.0.1`, `NORMAL` và `ALWAYS` cho hành vi giống nhau: follow `302`, sau đó `307`, cuối cùng `200`.
4. `uri=/final` và `request=/final` cho thấy response cuối thuộc request sau redirect, không phải URI khởi đầu `/start`.
5. `previous=307@/middle... <- 302@/start...` là thứ tự **từ gần nhất về xa nhất**. Body của mỗi intermediate response bằng `null` dù server đã gửi nội dung `redirect-body`.
6. Với `POST`, 301/302/303 đổi thành `GET` trong implementation Java 17 đã thử; 307/308 giữ `POST` và gửi body `payload` đến `/echo`.
7. `server.stop(0)` dừng server cục bộ khi kết thúc. Port là port ngẫu nhiên do OS cấp, nhưng stdout chỉ in path/status để tránh phụ thuộc số cổng.

### Vì sao thứ tự ALWAYS trước NORMAL?

`HttpClient.Redirect.values()` trong Java 17 trả các enum theo thứ tự khai báo: `NEVER`, `ALWAYS`, `NORMAL`. Đây là thứ tự enum, **không phải xếp hạng khuyến nghị bảo mật**.

### Giới hạn của ví dụ

- Test bằng HTTP local nên **không phân biệt NORMAL và ALWAYS trên HTTPS downgrade**; bảng chính sách ở mục 3 là quy tắc chuẩn của API.
- `HttpServer` là server dành cho ví dụ/test, không đại diện cho server production.
- Không có authentication, cookies, proxy, redirects tới các host khác hoặc HTTPS certificate; những tình huống đó cần kiểm thử riêng, có kiểm soát.
- Dùng `HttpResponse.BodyHandlers.ofString()` cho body nhỏ. Với body lớn/untrusted, cần streaming, giới hạn kích thước, timeout.
- JDK/provider/network có thể làm một bài demo loopback lỗi nếu không được phép bind socket hoặc đang bị security policy đặc biệt chặn. Điều đó không thay đổi semantics của API.

## 13. HTTP method và request body khi redirect

Redirect ảnh hưởng tới không chỉ URI. **Request method** và **body** có thể đổi theo status code và implementation.

| Status | Ý nghĩa phổ biến | Khi Java 17 tự follow một POST trong ví dụ |
| --- | --- | --- |
| `301 Moved Permanently` | Tài nguyên chuyển lâu dài | **POST → GET**, không gửi lại body ban đầu |
| `302 Found` | Tạm chuyển (lịch sử có client đổi method) | **POST → GET**, không gửi lại body ban đầu |
| `303 See Other` | Chỉ tới tài nguyên khác để truy xuất kết quả | **POST → GET** |
| `307 Temporary Redirect` | Tạm chuyển, phải giữ method | **POST vẫn POST**, gửi lại body khi có thể |
| `308 Permanent Redirect` | Chuyển lâu dài, phải giữ method | **POST vẫn POST**, gửi lại body khi có thể |

Theo Java SE 17 `HttpClient.Redirect`, khi automatic redirect diễn ra, method **có thể được điều chỉnh** theo 30x status; riêng `301` và `302` làm **POST thành GET**. Phần `303/307/308` trong bảng được xác minh bằng code local, đồng thời phù hợp ý nghĩa HTTP semantics của các status đó.

Không kết luận rằng:
- `307`/**`308`** lúc nào cũng tự retry thành công. Body publisher có thể không hỗ trợ phát lại, I/O có thể lỗi, redirect limit có thể chặn.
- `301`/`302` luôn giữ body; với Java 17 POST đã đổi sang GET trong demo.
- Mọi method tùy biến đều có cùng behavior như POST; cần kiểm thử theo API và status cụ thể.
- Redirect một request có tác động nghiệp vụ luôn an toàn. Server có thể đã xử lý POST đầu trước khi redirect hoặc retry; application phải quản lý idempotency.

### Khi nào 307/308 hữu ích?

Nếu endpoint muốn đổi URL mà **không thay method**, 307/308 phù hợp hơn 302 cho nhiều thao tác API. Nhưng lưu ý retry/resend body:
- Với `BodyPublishers.ofString(...)`, dữ liệu có thể được phát lại thuận tiện.
- Với publisher một lần đọc từ input stream/network hoặc stateful source, phải kiểm tra publisher **có thể subscribe lại/phát lại** hay không.
- Không tự replay request lớn, upload nhạy cảm hoặc transaction có tác động nếu chưa định nghĩa rõ behavior và giới hạn.

**Khuyến nghị thực tế:** server cung cấp 307/308 khi muốn bảo toàn method rõ ràng; phía client kiểm tra URI, body replay policy và transaction semantics trước khi follow.

## 14. previousResponse() không đồng nghĩa “mọi request đã được gửi”

Có ít nhất bốn loại lịch sử khác nhau cần phân biệt:

1. **Initiating request:** object `HttpRequest` mà caller truyền vào `send(...)` hoặc `sendAsync(...)`. Nó vẫn tồn tại ở biến cục bộ do bạn giữ.
2. **Final response:** `HttpResponse<T>` mà caller nhận sau khi client xử lý redirect và authentication theo cấu hình.
3. **Intermediate responses:** chuỗi `previousResponse()` nếu có redirect/authentication trước khi final.
4. **Application trace/log:** danh sách do ứng dụng tự ghi cho mỗi user operation/correlation ID. Nó có thể bao gồm nhiều `send(...)` độc lập và retries ở tầng nghiệp vụ.

`previousResponse()` chỉ bao quát loại **3** trong phạm vi HTTP exchange đó. Nó **không**:
- Cho biết request trước đó của một `HttpClient` khi hoàn toàn không liên quan.
- Ghi lại mọi network packet, DNS resolution hay TCP retry.
- Cam kết bao gồm tất cả application retries nếu bạn tự gọi `send` nhiều lần.
- Chứa response body đầy đủ của redirect hops.
- Thay thế distributed tracing qua reverse proxy/CDN/backend.

Khi cần trace một chuỗi redirect, lưu initiating URI cùng với final URI, final status, number of intermediate hops, từng status/Location, response duration và correlation ID do ứng dụng định nghĩa. Không chỉ ghi final 200.

## 15. Lấy chuỗi theo thứ tự thời gian, không đảo lộn

Phương thức `previousResponse()` bắt đầu từ response **gần final nhất**. Với chain:

```text
/start (302) → /middle (307) → /final (200)
```

Duyệt `previousResponse` từ final sẽ cho:
1. `307 /middle`
2. `302 /start`

Nếu muốn log theo thứ tự request thực sự diễn ra, hãy thu thập rồi đảo list:

```java
List<HttpResponse<String>> intermediates = new ArrayList<>();
Optional<HttpResponse<String>> cursor = finalResponse.previousResponse();
while (cursor.isPresent()) {
    HttpResponse<String> hop = cursor.get();
    intermediates.add(hop);
    cursor = hop.previousResponse();
}
Collections.reverse(intermediates);

for (HttpResponse<String> hop : intermediates) {
    System.out.println(hop.statusCode() + " " + hop.uri());
}
System.out.println(finalResponse.statusCode()
        + " " + finalResponse.uri());
```

Đây là **mảnh code minh họa**, cần imports `java.util.ArrayList`, `java.util.Collections`, `java.util.List`, `java.util.Optional` và `java.net.http.HttpResponse`; `finalResponse` là kết quả `HttpResponse<String>` đã có.

Với ví dụ local, thứ tự log mong muốn là `302 /start`, `307 /middle`, `200 /final`. Nếu xuất hiện intermediate response do authentication, danh sách có thể có cả những status khác 3xx. Khi logging, hãy **không in Authorization, Set-Cookie, tokens hoặc query parameters nhạy cảm** một cách không kiểm soát.

## 16. request().uri(), uri() và Location có vai trò khác nhau

Các câu hỏi API:

| API | Trả về | Khi có redirect |
| --- | --- | --- |
| `initiatingRequest.uri()` | URI caller ban đầu gửi | Vẫn là URI gốc của object bạn giữ |
| `finalResponse.request().uri()` | URI của HttpRequest ứng với final response | Thường là URL sau các redirect |
| `finalResponse.uri()` | URI của response cuối | Là URI mà response cuối nhận được |
| `finalResponse.headers().firstValue("Location")` | Header Location của **final response** nếu có | Thường rỗng khi cuối là 200 |
| `finalResponse.previousResponse().get().uri()` | URI của intermediate response gần nhất | Ví dụ `/middle` |
| `hop.headers().firstValue("Location")` | Location mà một intermediate hop quảng bá | Ví dụ `/final` |

Một lỗi thường gặp:

```java
System.out.println(response.headers().firstValue("Location"));
```

với response cuối `200` sau redirect. Bạn sẽ không thấy Location của `302` vì `response.headers()` thuộc **response cuối**. Phải đi qua `previousResponse` để xem intermediate 3xx headers.

Một lỗi khác: dùng `response.request().uri()` làm “origin bắt đầu”. Nó có thể đã đổi sau automatic redirects. Nếu cần cả original và final, **giữ biến `HttpRequest original` khi gửi**.

## 17. Chuyển hướng qua HTTPS: policy và lớp bảo mật

Giả sử:
- URI ban đầu: `https://login.example.com/session`.
- Server trả: `302 Location: http://login.example.com/session`.

Theo enum Java 17:
- `NEVER`: trả response `302`; không gửi request tiếp theo.
- `NORMAL`: **không tự follow** vì HTTPS → HTTP.
- `ALWAYS`: cho phép automatic follow xuống HTTP nếu redirect hợp lệ và không có cản trở khác.

Tại sao cần quan tâm? HTTP plaintext không có tính bí mật/tính toàn vẹn/xác thực endpoint như HTTPS/TLS. Dữ liệu URL, query, headers hay body gửi sang endpoint HTTP có thể bị quan sát hoặc sửa đổi bởi tác nhân mạng, tùy điều kiện. Nguy cơ tăng nếu token, cookie, session hoặc thông tin cá nhân đi theo request mới.

**Tuyên bố quan trọng:** `ALWAYS` chỉ là chính sách auto-follow; nó **không** chứng minh client sẽ chắc chắn gửi lại mọi header, cookie và body theo cách nào. Quy tắc chuyển credential phụ thuộc implementation, request và authentication/cookie configuration. Không dựa vào giả định “Java sẽ tự tước toàn bộ secret”, cũng không assume Java gửi nguyên xi mọi secret. Với trường hợp nhạy cảm, phải kiểm thử và **đặt chính sách rõ**.

### Dùng NORMAL đã đủ để an toàn chưa?

Chưa. `NORMAL` có thể theo redirect `https://api.example.com` → `https://evil.example`, vẫn qua HTTPS nhưng **đích đổi host**. TLS của `evil.example` có thể hoàn toàn hợp lệ cho chính tên đó; vấn đề nằm ở **quyền ứng dụng được phép gửi dữ liệu tới host đó hay không**, không phải certificate sai.

Vì vậy với client tải dữ liệu từ URL do bên thứ ba kiểm soát, nên dùng `NEVER` và validate từng bước hoặc một wrapper có redirect policy chặt chẽ. Đừng xem TLS là thay thế allowlist.

## 18. Redirect, credentials và cross-origin

Redirect có thể thay đổi:
- **Scheme:** `http` / `https`.
- **Hostname/IP:** từ máy đang yêu cầu sang máy khác.
- **Port:** từ 443 sang 8443 hoặc cổng khác.
- **Path/query:** từ endpoint này sang endpoint khác, có thể thay ý nghĩa dữ liệu.
- **User identity/cookies/authentication scope:** khác nhau giữa origins và domains.

Một client có `Authorization: Bearer ...`, Cookie hoặc custom internal header cần quyết định rõ:
- Có được theo redirect sang host khác hay không?
- Khi đổi host/port, có được giữ Authorization hay phải loại bỏ/đổi credential?
- Có thể gửi cookie từ CookieHandler tới domain phù hợp theo cookie rules không?
- Có chấp nhận gửi body của POST sang endpoint không thuộc allowlist?
- Query string chứa secret có đang bị gửi sang Location do remote chọn không?

Không dựa vào một enum `Redirect.NORMAL` để xử lý hết. `NORMAL` **chỉ là chính sách redirect cơ bản** (đặc biệt chặn HTTPS → HTTP). Các chính sách credentials, host allowlist, redirect count, size limit và server behavior cần được ứng dụng hoặc HTTP framework quản trị riêng.

**Đừng log query secrets:** khi audit chain, có thể thay full URI bằng host/path đã sanitize hoặc correlation ID. HTTP client logs có thể vô tình tiết lộ token trong URL.

## 19. Open redirect và SSRF khi auto-follow

Một endpoint `https://api.example.com/lookup?id=42` có thể bị điều khiển để trả:

```http
HTTP/1.1 302 Found
Location: http://127.0.0.1:8080/admin
```

Nếu Java application chạy trong mạng nội bộ và dùng `ALWAYS` hoặc `NORMAL` từ **một URL HTTP ban đầu** (hoặc redirect hợp scheme khác cho phép), nó có thể bị dẫn tới dịch vụ nội bộ ngoài ý định. Đây là một hình thức **server-side request forgery (SSRF)** qua redirect.

Trường hợp đặc biệt: với **HTTPS → HTTP**, `NORMAL` sẽ chặn downgrade, nhưng attacker vẫn có thể đưa target kiểu `https://internal.example:8443/`. Vì vậy **chặn downgrade không đồng nghĩa chặn SSRF**.

Các lớp bảo vệ:
1. **Chấp nhận đầu vào giới hạn** (allowlist scheme, host, port, path, prefix nghiệp vụ).
2. **Kiểm tra từng Location sau khi `resolve`**, không chỉ request đầu tiên.
3. **Chặn IP private, loopback, link-local, metadata endpoints** khi ứng dụng chỉ được phép truy cập Internet công khai, theo yêu cầu mạng.
4. **Cân nhắc DNS rebinding/TOCTOU:** chỉ gọi `InetAddress.getAllByName(host)` rồi tạo request cho `HttpClient` sau đó không bảo đảm transport sẽ kết nối chính các IP đã kiểm tra. Cần egress policy/network firewall và phương pháp ràng buộc resolution/connection phù hợp với HTTP stack thực.
5. **Tắt tự redirect nếu không có kiểm soát từng hop:** `Redirect.NEVER` giúp ứng dụng kiểm tra target trước mọi request tiếp theo.
6. **Giới hạn số hop, tổng thời gian, tổng byte tải và request bodies**, tránh redirect loop/exhaustion.
7. **Không chuyển tiếp secrets sang origin không được phép**, dù target sử dụng HTTPS hợp lệ.

Một URL “được trả về từ server tin cậy” vẫn có thể chịu ảnh hưởng tham số của người dùng và lỗi open redirect. Với API lấy URL nhập từ user, redirect target cần được xem là **dữ liệu không đáng tin** cho tới khi validate.

## 20. Khi cần kiểm soát từng hop: cách làm manual redirect

`HttpClient.Redirect.NEVER` cho phép client quan sát từng 3xx rồi quyết định có tạo request mới. Luồng khái niệm:

```text
current = URI ban đầu
hops = 0

loop:
  validate current (scheme, host, port, path và egress policy)
  send one HttpRequest với HttpClient.Redirect.NEVER
  if response không phải redirect cần follow:
      return response
  read Location (phải có và hợp lệ)
  next = response.uri().resolve(Location)
  validate next + cross-origin credential/method policy
  hops++
  if hops > MAX_HOPS: reject
  current = next
```

Đây là **pseudocode**, không phải chương trình Java biên dịch trực tiếp. Một triển khai manual thực sự phải định nghĩa chi tiết:
- Status nào được follow (301/302/303/307/308).
- Khi nào đổi `POST` thành `GET`, khi nào giữ body, có thể replay publisher không.
- Header nào được sao chép, header nào phải bỏ khi cross-origin.
- CookieHandler/Authenticator/ProxySelector có tác động gì.
- Response body của từng 3xx được xử lý/đóng đúng cách, không tải vô hạn.
- Timeout per-hop và deadline cho toàn bộ chain.
- Limit số redirects và detected loops, chính sách protocol/scheme riêng.
- Cơ chế chống SSRF ngoài HTTP layer như egress ACL và DNS/connection binding.

**Đừng** đơn giản lấy `Location` rồi `HttpRequest.newBuilder(URI.create(location))` và copy toàn bộ headers/body từ original. Relative Location có thể sai base, credentials có thể rò rỉ, POST semantics có thể thay đổi và URI mới có thể nằm ngoài phạm vi được phép.

### Mảnh code resolve và phân tích target

```java
Optional<String> location =
        response.headers().firstValue("Location");
if (location.isPresent()) {
    URI target = response.uri().resolve(location.get());
    if (!"https".equalsIgnoreCase(target.getScheme())) {
        throw new IllegalArgumentException("HTTPS required");
    }
    if (!"api.example.com".equalsIgnoreCase(target.getHost())) {
        throw new IllegalArgumentException("Host not allowed");
    }
    // Cần kiểm tra port, DNS/IP, path, headers và các policy khác nữa.
}
```

Đây là **mảnh code**, không phải bộ chống SSRF hoàn chỉnh; biến `response` là `HttpResponse<?>`, imports `java.net.URI` và `java.util.Optional`. Không dùng một so sánh host đơn giản để thay thế tất cả kiểm soát network/credential; nó chỉ minh họa việc validate target **trước** khi tạo request mới.

## 21. Loop, nhiều redirects và giới hạn tài nguyên

Các redirect chain có thể:
- Hợp lệ: `/old` → `/new` → `/final`.
- Lặp: `/a` → `/b` → `/a`.
- Dài bất thường: hàng trăm hop do cấu hình sai.
- Chuyển qua nhiều host và port.
- Trả URI malformed/unsupported hoặc thiếu Location.
- Gặp timeout/failure giữa chừng.
- Đổi POST method/body trên một hop, gây kết quả khác kỳ vọng.

Java HTTP client implementation có cơ chế giới hạn redirect/retry; tài liệu Java 17 Networking có nhắc system property implementation-specific `jdk.httpclient.redirects.retrylimit` (một giá trị mặc định được ghi trong tài liệu đó), nhưng **đừng dùng số đó làm bảo đảm nghiệp vụ**. Giới hạn thực tế có thể chịu ảnh hưởng retry do lỗi khác và thay đổi theo phiên bản/provider. Trong ứng dụng nhạy cảm, tự đặt hop limit rõ ở layer policy khi điều khiển từng hop.

Một điều kiện bảo vệ tốt là:
- `MAX_HOPS` theo nghiệp vụ, ví dụ 5.
- Deadline tổng thể cho toàn bộ thao tác; timeout request không thay thế tuyệt đối cho all-hops operation deadline trong mọi cấu hình.
- Không lặp URI đã từng ghé thăm, có tính đến canonicalization/các trường hợp query khác.
- Giới hạn response body/intermediate payload.
- Cấm chuyển sang scheme/host/port ngoài allowlist.
- Khi request method/body không replayable, dừng và báo lỗi thay vì âm thầm thử lại.

**Không coi vòng lặp redirect là tình huống “HttpClient sẽ tự động chắc chắn trả một exception kiểu X”**. Nếu không thể follow, client có thể trả intermediate 3xx cuối, hoặc operation có thể lỗi vì I/O/timeout. Khi cần chính xác, hãy test behavior trên phiên bản triển khai sử dụng và xử lý cả 3xx lẫn exception.

## 22. GET, HEAD, POST và redirects trong ứng dụng thật

Một API client GET dữ liệu có thể chấp nhận `NORMAL` để xử lý các URL đã được chuyển đường dẫn, nếu redirect targets vẫn nằm trong phạm vi tin cậy. Nhưng các request mang side effects hoặc credentials cần nhiều điều kiện:

**GET:** 
- Thường safe/idempotent theo HTTP semantics, nhưng request vẫn có thể kèm token hoặc query nhạy cảm.
- Cross-host redirect có nguy cơ đưa credential/dữ liệu sang nơi khác.
- Nếu download là dữ liệu lớn, cần body size limit và streaming policy.

**HEAD:**
- Dùng để lấy metadata mà không cần body; một số server chuyển hướng tới đích và client có thể follow.
- Không dùng sự thành công của HEAD để suy ra GET luôn cùng semantics khi ứng dụng có logic riêng.

**POST:**
- Có thể đổi thành GET khi 301/302/303 trong Java 17.
- 307/308 dự kiến giữ method/body; phải đảm bảo payload có thể được gửi lại, giới hạn retry và chống tác động lặp.
- Không tự cho phép API “thanh toán” hoặc “tạo đơn” dùng redirect tự động tới endpoint bất kỳ.

**PUT/DELETE/PATCH/custom methods:**
- Phụ thuộc chuẩn HTTP, status code và behavior của client implementation.
- Không lấy kết quả test POST rồi suy ra mọi method sẽ xử lý y hệt.
- Nên có integration tests riêng cho request có side effects.

**Server-side design:** nếu server cần chỉ dẫn client đọc resource mới sau khi xử lý POST, `303 See Other` thường diễn đạt rõ việc chuyển sang GET. Nếu server cần chuyển endpoint nhưng giữ method/body, 307/308 là lựa chọn có chủ đích hơn 302.

## 23. send() và sendAsync(): redirect policy nằm trên client

Java `HttpClient` có synchronous và asynchronous APIs:
- `client.send(request, bodyHandler)` có thể block caller tới khi response hoàn thành theo BodyHandler và network conditions.
- `client.sendAsync(request, bodyHandler)` trả `CompletableFuture<HttpResponse<T>>`; xử lý response khi future hoàn tất.

**Cả hai dùng redirect policy của cùng instance `HttpClient`.** Khi automatic redirects hoàn tất, response final của sync hay async đều hỗ trợ `previousResponse()`.

Mảnh code async:

```java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();

CompletableFuture<HttpResponse<String>> future = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString());

future.thenAccept(response -> {
    System.out.println("Final status: " + response.statusCode());
    System.out.println("Final URI: " + response.uri());
    System.out.println("Has history: " + response.previousResponse().isPresent());
}).exceptionally(error -> {
    System.err.println("HTTP exchange failed: " + error.getMessage());
    return null;
});
```

Đây là **mảnh code**, biến `request` là `HttpRequest` phù hợp, imports `java.net.http.*` và `java.util.concurrent.CompletableFuture`. Với async, process cần giữ sống đủ lâu để future hoàn thành; code không nên chỉ đăng ký callback rồi thoát ứng dụng. Trong production cần quản lý cancellation, deadline, executor và log có giới hạn.

**Quan trọng:** `CompletableFuture` lỗi vì I/O/timeout/SSL không giống HTTP response status 3xx/4xx/5xx. Phải có nhánh xử lý response status **và** nhánh xử lý exceptional completion.

## 24. Kiểm thử theo ma trận thay vì dự đoán

| Trường hợp | Policy | Kỳ vọng chính |
| --- | --- | --- |
| HTTP 302 `/start → /final` | NEVER | Trả 302, không có automatic history, final body có thể là body của 302 |
| HTTP 302 `/start → /final` | NORMAL | Follow, nhận final status nếu network thành công |
| HTTP 302 `/start → /final` | ALWAYS | Follow, nhận final status nếu network thành công |
| HTTPS 302 → HTTP | NORMAL | **Không tự follow downgrade** |
| HTTPS 302 → HTTP | ALWAYS | Cho phép follow nếu redirect hợp lệ |
| HTTPS 302 → HTTPS cùng host | NORMAL | Có thể follow |
| HTTPS 302 → HTTPS host khác | NORMAL | Có thể follow; ứng dụng vẫn phải kiểm tra host |
| 302 → 307 → 200 | NORMAL | Final 200; history chứa 307 rồi 302 với body null |
| 301/302 POST → location | NORMAL/ALWAYS | Java 17 đổi POST thành GET trong demo |
| 303 POST → location | NORMAL/ALWAYS | Đổi sang GET trong demo |
| 307/308 POST → location | NORMAL/ALWAYS | Giữ POST/body trong demo; publisher phải replayable |
| 3xx thiếu Location | Bất kỳ | Không follow một location không có; ứng dụng xử lý 3xx |
| 302 Location tương đối | NORMAL/ALWAYS | Resolve từ response URI theo quy tắc URI |
| Redirect loop | NORMAL/ALWAYS | Không được cho phép vô hạn; kết quả phụ thuộc limits/implementation |
| Response 401 authentication challenge | Có authenticator | `previousResponse` có thể chứa intermediate auth response |
| Proxy/auth error, network timeout | Bất kỳ | Có thể exception, không suy ra luôn nhận final 2xx |

Hãy viết integration test local với:
- Ephemeral port `0`, bind loopback để tránh tác động mạng ngoài.
- Mỗi test độc lập: GET, POST, relative Location, cross-origin, no Location, loop.
- Kiểm tra **số lần endpoint bị gọi** và URI/method thực tế, không chỉ final status.
- Kiểm tra `previousResponse` từng hop, status và headers, đồng thời xác nhận `body() == null` cho intermediates.
- Với HTTPS downgrade, dùng test server HTTPS có certificate/test truststore hợp lệ, tuyệt đối không bật trust-all chỉ để test.
- Chạy tests trên JDK/runtime thật được triển khai; behavior có thể khác giữa thư viện/framework chứ không chỉ Java `HttpClient`.

## 25. Quan sát và xử lý lỗi khi redirect

Log hữu ích cho mỗi logical operation:
- **Request correlation ID** do ứng dụng tạo.
- **Initial URI** đã sanitize.
- **Final URI** sau khi nhận response, đã sanitize.
- **Final HTTP status code**.
- **Redirect policy** đang dùng.
- **Count và trạng thái từng intermediate response**.
- **Scheme/host thay đổi** (đặc biệt có downgrade/cross-origin).
- **Elapsed time, timeout/exception** và số lần retry ở application layer nếu có.
- **Method ban đầu và method cuối** nếu nghiệp vụ cần xác minh.
- **Số byte response** theo policy, không log body nhạy cảm.

Ví dụ một format log đã lược query secrets:

```text
operation=fetch-item
policy=NORMAL
initial=https://api.example.com/v1/item
final=https://api.example.com/v2/item
status=200
redirects=1
hops=301:https://api.example.com/v1/item
method=GET
result=success
```

Không logging `Authorization`, `Cookie`, bearer tokens, signed URLs hoặc raw PII. Với `previousResponse`, chỉ log status, host/path đã được lọc, loại redirect và lượng hop. Nếu URL mang thông tin nhạy cảm trong path, phải tiếp tục mask theo chính sách dữ liệu.

Có thể dùng Java HTTP client diagnostics của JDK trong môi trường kiểm soát, ví dụ system property `jdk.httpclient.HttpClient.log`, nhưng logging chi tiết cần được bảo vệ và tắt đúng lúc. Đừng xem debug logs là bằng chứng production phải luôn lưu toàn bộ URLs/headers.

## 26. Những lỗi thường gặp

1. **“Java HttpClient mặc định follow redirect như browser.”** Sai: mặc định `NEVER`.
2. **“NORMAL nghĩa là chỉ redirect trong cùng origin.”** Sai: NORMAL chặn HTTPS → HTTP, không phải cross-origin allowlist.
3. **“ALWAYS bảo đảm mọi 3xx được follow.”** Sai: còn status eligibility, `Location`, limits, method/body và I/O.
4. **“Final 200 nghĩa không có redirect.”** Sai: `previousResponse` có thể chứa các 3xx.
5. **“`response.headers().firstValue("Location")` lấy Location của 302 trước.”** Sai khi `response` là final 200; cần duyệt history.
6. **“`previousResponse` là một list.”** Sai: nó trả `Optional<HttpResponse<T>>` liên kết đệ quy.
7. **“Body của các previous responses vẫn giữ đầy đủ.”** Sai: `body() == null` cho response từ `previousResponse()`.
8. **“`response.uri()` luôn bằng URI caller truyền vào send.”** Sai khi auto-follow; nó là URI của response hiện tại/final.
9. **“`response.request().uri()` luôn là initiating URI.”** Sai: request tương ứng với response hiện tại có thể là redirected request.
10. **“302 luôn bảo toàn POST và body.”** Sai theo Java 17 implementation: POST → GET.
11. **“307/308 không cần cân nhắc replay body.”** Sai: body publisher phải đáp ứng khả năng gửi lại và nghiệp vụ cần idempotency.
12. **“Location tương đối chỉ cần `URI.create(location)`.”** Sai: phải resolve với base URI phù hợp.
13. **“Redirect HTTPS → HTTP không đáng lo vì hop đầu là HTTPS.”** Sai: hop HTTP sau không được TLS bảo vệ.
14. **“Dùng NORMAL ngăn mọi SSRF.”** Sai: vẫn có redirect tới HTTPS host/IP private hoặc từ HTTP tới HTTP nội bộ.
15. **“Khi nhận redirect loop Java sẽ luôn ném cùng một exception.”** Không có cam kết kết quả kiểu exception cụ thể cho mọi implementation/trạng thái; cần kiểm thử và xử lý cả 3xx lẫn failure.
16. **“Cứ copy Authorization/Cookie tới mọi redirect target.”** Sai: nguy cơ lộ credential khi đổi origin; cần policy rõ.
17. **“Timeout connect là đủ bao trùm cả chuỗi redirect.”** Sai: còn các thời hạn của request, response body, nhiều hops và ứng dụng.
18. **“previousResponse là lịch sử của mọi request đã gọi qua một client.”** Sai: chỉ intermediate chain của exchange hiện tại.
19. **“Body của redirect bị null chứng minh server không gửi body.”** Sai: API không lưu body intermediate cho caller trong automatic chain.
20. **“Chuyển sang HTTP plaintext là fallback an toàn khi TLS lỗi.”** Sai: đây là downgrade, không phải giải pháp cho chứng chỉ/SSL handshake sai.

## 27. Checklist chọn policy cho từng ứng dụng

**Chọn `NEVER` khi:**
- Request phục vụ từ URL do user/remote nhập và phải bảo vệ trước SSRF.
- Gửi credential hoặc payload nhạy cảm tới allowlisted origins.
- Muốn audit và quyết định rõ từng redirect hop.
- Cần giữ body của 3xx hoặc custom method/response handling.
- Đang phát triển crawler, proxy hoặc SDK cần redirect rules riêng.

**Chọn `NORMAL` khi:**
- Client muốn follow các redirect thường gặp một cách tiện lợi.
- Không cho phép HTTPS → HTTP downgrade.
- Danh sách nguồn/đích đã được tin hoặc có kiểm soát bổ sung.
- Có timeout, error handling và tests khi cross-host/method change.

**Chỉ cân nhắc `ALWAYS` khi:**
- Đã cho phép HTTPS → HTTP một cách rõ ràng, có căn cứ nghiệp vụ.
- Không có secrets/credential cần bảo vệ trên hop plaintext.
- Hạ tầng và target hosts được kiểm soát, có tests.
- Rủi ro redirect sang host/port khác đã được giới hạn.

**Với mọi policy:**
- Phân biệt initial URI, final URI và `previousResponse` chain.
- Phân biệt redirects với retries, auth challenges, SSL errors và HTTP non-2xx responses.
- Cẩn thận POST 301/302/303/307/308 và replay.
- Kiểm tra no Location/invalid Location, loop và hop limits.
- Log đã sanitize, không leak token qua headers/query.
- Nếu là network client có quyền rộng, ràng buộc egress/host/IP ở tầng transport/firewall thay vì chỉ nhìn chuỗi URL.

## 28. Bài tập tự kiểm tra

**Câu 1.** `HttpClient.newHttpClient()` gặp `302 Location: /new`. Có tự truy cập `/new` không?  
**Đáp án:** Không. Default `Redirect.NEVER` nên caller nhận response 302 trực tiếp.

**Câu 2.** `NORMAL` gặp redirect từ `https://a.example/old` sang `http://a.example/new`. Có follow không?  
**Đáp án:** Không tự follow downgrade HTTPS → HTTP; đây là khác biệt quan trọng so với ALWAYS.

**Câu 3.** `ALWAYS` gặp redirect từ `https://a.example` sang `http://a.example`. Nó có cho phép follow theo policy không?  
**Đáp án:** Có, nhưng còn status/Location/limits/I/O. Đây là lý do policy cần được sử dụng rất thận trọng với dữ liệu nhạy cảm.

**Câu 4.** Chuỗi `302 /start → 307 /middle → 200 /final` với `NORMAL`. `response.statusCode()` là bao nhiêu? `previousResponse().get().statusCode()` là bao nhiêu?  
**Đáp án:** Final 200; previous gần nhất 307. Previous của 307 là 302.

**Câu 5.** Vì sao `previousResponse().get().body()` có thể `null` dù server đã gửi body trong 302?  
**Đáp án:** `HttpResponse` Java 17 quy định body của response lấy từ `previousResponse()` là `null`; intermediate body không được cung cấp cho caller như final body.

**Câu 6.** `POST` gặp 302 trong Java 17 implementation đã kiểm chứng. Sau redirect, method nào được gửi?  
**Đáp án:** `GET`, không gửi lại body POST ban đầu trong ví dụ.

**Câu 7.** `POST` gặp 307, publisher có thể phát lại. Request tiếp theo dùng method nào?  
**Đáp án:** `POST`; 307 yêu cầu bảo toàn method/body semantics. Nhưng vẫn cần kiểm tra target và nghiệp vụ side effects.

**Câu 8.** Vì sao `response.request().uri()` không đáng tin để suy ra original URI?  
**Đáp án:** Nó là request tương ứng response hiện tại, có thể là request đã redirect; phải giữ original `HttpRequest` riêng.

**Câu 9.** `Location: //internal.example/admin` có phải relative path an toàn cùng host không?  
**Đáp án:** Không. Đó là network-path reference **thay hostname**, thừa hưởng scheme; cần validate host/IP và egress.

**Câu 10.** Có phải `NORMAL` ngăn mọi SSRF vì nó chặn HTTPS → HTTP?  
**Đáp án:** Không. NORMAL vẫn có thể theo HTTPS → HTTPS tới host/IP nội bộ; phải kiểm soát đích ở mọi hop.

**Câu 11.** `previousResponse()` có thể bao gồm phản hồi 401/authentication không?  
**Đáp án:** Có thể. JDK mô tả intermediate responses đến từ redirection **hoặc authentication**.

**Câu 12.** Muốn log chuỗi theo đúng thứ tự thời gian, trong khi `previousResponse` duyệt từ gần nhất về xa nhất, làm thế nào?  
**Đáp án:** Thu thập intermediate responses, đảo list, sau đó append final response; không đảo lẫn URI và status của từng hop.

## 29. Tài liệu đối chiếu chính thức

- Java SE 17 `HttpClient` — default Redirect.NEVER, cấu hình client, send/sendAsync: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Java SE 17 `HttpClient.Redirect` — NEVER/NORMAL/ALWAYS và method changes trên redirect: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html
- Java SE 17 `HttpClient.Builder` — `followRedirects`, `connectTimeout`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html
- Java SE 17 `HttpResponse` — `request()`, `uri()`, `previousResponse()`, `body()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html
- Java SE 17 `HttpRequest.Builder` — URI, timeout, method, headers, body publishers: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html
- Java SE 17 `URI` — `resolve` với URI-reference tương đối: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html
- Java SE 17 `HttpServer` — local HTTP test server: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- RFC 9110 — HTTP Semantics, status codes 301/302/303/307/308: https://www.rfc-editor.org/rfc/rfc9110
- RFC 9112 — HTTP/1.1 message syntax and parsing: https://www.rfc-editor.org/rfc/rfc9112
- OWASP Server-Side Request Forgery Prevention Cheat Sheet — kiểm tra redirect/egress/destination: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
