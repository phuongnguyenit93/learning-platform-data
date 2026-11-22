# HttpResponse.previousResponse() và chuỗi chuyển hướng — Cấu hình HTTP trong Java 11+

> **Mục tiêu:** Hiểu cách Java HTTP Client theo dõi các **phản hồi trung gian** khi tự động chuyển hướng HTTP (redirect), đọc chuỗi `HttpResponse.previousResponse()` từ phản hồi cuối trở về các bước trước đó, và chọn chính sách `HttpClient.Redirect` an toàn. Các API minh họa xuất hiện trong **Java 11** và vẫn còn được hỗ trợ trên JDK hiện đại.

## 1. Sau bài này bạn làm được gì?

1. Phân biệt **request ban đầu**, phản hồi `3xx` trung gian và **phản hồi cuối**.
2. Giải thích kiểu trả về `Optional<HttpResponse<T>>` của `previousResponse()` và khi nào nó rỗng.
3. Cấu hình `Redirect.NEVER`, `Redirect.NORMAL`, `Redirect.ALWAYS` đúng mục đích; biết **mặc định Java 11 là `NEVER`**.
4. Duyệt đúng thứ tự chuỗi response, phân biệt `response.uri()`, `response.request().uri()` và `Location`.
5. Hiểu tại sao `body()` của response lấy **qua `previousResponse()`** là **`null`**, dù response cuối có thể có `String` hoặc `byte[]`.
6. Chạy một chương trình kiểm thử cục bộ có chuỗi `302 → 301 → 200` để nhìn thấy kết quả thực.
7. Hiểu khác biệt giữa `302` (POST có thể chuyển GET) và `307` (giữ method và body) với một chương trình thử thứ hai.
8. Biết khi nào phải **tự kiểm tra đích redirect** để tránh SSRF, rò rỉ credential, HTTPS downgrade, vòng lặp hoặc chuỗi quá dài.
9. Thiết kế xử lý lỗi, timeout và kiểm thử tương thích Java 11 mà không dựa vào API lỗi thời.

## 2. Redirect, phản hồi trung gian và phản hồi cuối

Máy chủ có thể trả một trạng thái thuộc nhóm `3xx` và header `Location` để cho biết tài nguyên cần truy cập tại một URI khác. Ví dụ:

~~~text
GET /start HTTP/1.1
             |
             v
HTTP/1.1 302 Found
Location: /middle
             |
             v
GET /middle HTTP/1.1
             |
             v
HTTP/1.1 301 Moved Permanently
Location: /final
             |
             v
GET /final HTTP/1.1
             |
             v
HTTP/1.1 200 OK
body: finished
~~~

Ở đây có ba lần giao tiếp HTTP:

- **Lần 1:** `/start` trả `302` và đề nghị chuyển tới `/middle`.
- **Lần 2:** `/middle` trả `301` và đề nghị chuyển tiếp tới `/final`.
- **Lần 3:** `/final` trả `200` với body `finished`.

Nếu client **được cấu hình tự theo redirect**, lời gọi `send(...)` có thể trả trực tiếp response cuối cùng là `200`. Những response trung gian không biến mất: có thể truy cập chúng qua `previousResponse()`.

Nếu client **không theo redirect**, lời gọi `send(...)` trả response `302` đầu tiên. Khi ấy `previousResponse()` thường rỗng vì client không thực hiện một request tiếp theo từ redirect đó.

### Dạng dữ liệu của chuỗi previousResponse

~~~text
result:       200 /final, body = "finished"
    |
    | previousResponse()
    v
intermediate: 301 /middle, body = null
    |
    | previousResponse()
    v
intermediate: 302 /start, body = null
    |
    | previousResponse()
    v
Optional.empty()
~~~

**Hướng truy xuất là từ cuối về đầu**, chứ không phải từ `/start` đến `/final`. Muốn hiển thị theo thứ tự thời gian, bạn phải thu thập các node rồi đảo danh sách.

**Lưu ý quan trọng:** Theo Javadoc Java 11, intermediate response có thể xuất hiện do **redirection hoặc authentication**. Vì vậy tên `previousResponse` không có nghĩa tất cả node trước đó đều phải là `3xx`. Muốn gọi một node là “redirect hop” thì kiểm `statusCode()` và header/chính sách liên quan.

## 3. Cấu hình chính sách chuyển hướng của HttpClient

Java 11 dùng enum `HttpClient.Redirect`, cấu hình khi tạo client:

~~~java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .connectTimeout(Duration.ofSeconds(3))
        .build();
~~~

Đây là **đoạn mã minh họa trong method**; cần import `HttpClient` và `Duration`. Một client sau khi tạo có cấu hình cố định; bạn có thể dùng lại cho nhiều request. Chính sách redirect đặt **ở client**, không phải trên từng `HttpRequest.Builder`.

### Ba chính sách còn dùng được trên JDK hiện đại

| Chính sách | Ý nghĩa | Ứng dụng điển hình |
| --- | --- | --- |
| `HttpClient.Redirect.NEVER` | **Không tự động** chuyển tới Location | Cần xét/kiểm tra từng đích hoặc muốn tự xử lý 3xx |
| `HttpClient.Redirect.NORMAL` | Theo redirect thông thường **trừ hướng HTTPS → HTTP** | Request đến nguồn đáng tin, muốn tránh tự hạ cấp TLS |
| `HttpClient.Redirect.ALWAYS` | Cho phép tự động theo redirect, gồm cả trường hợp có thể hạ cấp HTTPS → HTTP | Chỉ cân nhắc khi có chính sách bảo mật cụ thể; không phải lựa chọn an toàn mặc định |

**Mặc định:** `HttpClient.newHttpClient()` tương đương một client có các thiết lập mặc định, bao gồm `Redirect.NEVER`. Tương tự, `HttpClient.newBuilder().build()` mặc định `NEVER` nếu không gọi `followRedirects`. Muốn tự theo redirect, phải cấu hình rõ ràng.

Bạn có thể đọc lại chính sách:

~~~java
System.out.println(client.followRedirects());
~~~

Đối với một client cấu hình `NORMAL`, dòng này in `NORMAL`; với client mặc định, in `NEVER`.

### Vì sao NORMAL không đồng nghĩa “an toàn tuyệt đối”?

`NORMAL` chỉ định không tự chuyển từ HTTPS sang HTTP. Nó **không** thay thế kiểm tra host, port, DNS, địa chỉ mạng nội bộ, quyền gửi dữ liệu hoặc quy tắc chia sẻ credential. Một HTTPS redirect sang **HTTPS host khác** có thể vẫn làm ứng dụng đi đến đích không mong muốn nếu tin tưởng URL bên ngoài một cách mù quáng.

`ALWAYS` không có nghĩa client bỏ qua mọi quy định của giao thức; nó chỉ biểu thị lựa chọn redirect trong API. Đối với request chứa token, cookie hay dữ liệu nhạy cảm, tuyệt đối không xem `ALWAYS` là tùy chọn “nhanh, tiện và không rủi ro”.

### Cấu hình không cần tự viết vòng lặp gửi lại

~~~java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/start"))
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
~~~

**Mã minh họa**, không phải chương trình hoàn chỉnh; cần import, xử lý ngoại lệ và endpoint thực. Nếu server cho phép redirect phù hợp, client tự xử lý các bước trung gian và có thể trả response cuối; nhưng **không** có cam kết rằng `example.com` thực sự cung cấp những path trên.

## 4. API previousResponse(): Optional chứa gì?

Chữ ký Java 11:

~~~java
Optional<HttpResponse<T>> previousResponse();
~~~

`T` là kiểu body của `HttpResponse<T>`, quyết định bởi `BodyHandler<T>` lúc gửi request. Phương thức trả:

- **`Optional.empty()`** nếu không có intermediate response nào được nhận trong lịch sử response này.
- **`Optional.of(previous)`** nếu có một intermediate response trực tiếp đứng trước node hiện tại.
- Mỗi `previous` lại có `previousResponse()` của riêng nó, tạo thành chuỗi liên kết.
- Các node trung gian có thể liên quan redirect hoặc authentication, không nhất thiết chỉ các status `301`/`302`.

Ví dụ đọc một bước:

~~~java
Optional<HttpResponse<String>> previous =
        response.previousResponse();

if (previous.isPresent()) {
    HttpResponse<String> hop = previous.get();
    System.out.println(hop.statusCode());
    System.out.println(hop.uri());
}
~~~

Đây là **đoạn minh họa trong một method** với `response` kiểu `HttpResponse<String>`. Cần import `Optional`. Không gọi `previous.get()` khi `isPresent() == false`; điều đó làm ném `NoSuchElementException`.

### 4.1. Body của intermediate response là null

Javadoc Java 11 của `HttpResponse.body()` nêu rõ: **nếu response này được trả bởi `previousResponse()`, `body()` trả `null`**.

~~~java
HttpResponse<String> hop = response
        .previousResponse()
        .orElseThrow();

System.out.println(hop.body() == null);  // true
~~~

Đoạn code minh họa với điều kiện chuỗi có intermediate response. Nó **không** có nghĩa server không gửi body trong một phản hồi redirect; điều đó chỉ nói `HttpResponse` trung gian không giữ body cho bạn truy cập.

Đừng nhầm:

- `body() == null` ở **intermediate response** do `previousResponse`: hành vi API.
- `body() == null` của response cuối dùng `BodyHandlers.discarding()`: do bạn chọn kiểu `Void` và bỏ body.
- Body rỗng `""` của response cuối dùng `BodyHandlers.ofString()`: một `String` dài 0, **không giống null**.
- Response cuối nhận `204 No Content`: không có body theo ngữ nghĩa HTTP; handler quyết định kiểu giá trị nhận được.

### 4.2. Những metadata vẫn đọc được từ intermediate response

| Thuộc tính | Ý nghĩa trên một node |
| --- | --- |
| `statusCode()` | Status của **chính response đó**: có thể `301`, `302`, `401`... |
| `uri()` | URI **đã nhận response** ở bước đó |
| `request()` | `HttpRequest` tương ứng với bước đó, có thể **khác request ban đầu** |
| `headers()` | Các response headers của chính bước đó, có thể gồm `Location` |
| `version()` | Phiên bản HTTP thực tế của bước đó |
| `previousResponse()` | Optional chứa node còn trước nữa |
| `body()` | **null** nếu node được lấy từ `previousResponse()` |

**Ví dụ:** Với chuỗi `/start → /middle → /final`, response cuối có `uri().getPath() == "/final"`, node `previous1` có `uri().getPath() == "/middle"` và node `previous2` có `uri().getPath() == "/start"`.

### 4.3. Phân biệt response.uri(), request().uri() và Location

- `response.uri()` là URI **đã nhận response tại node đang xét**.
- `response.request().uri()` là URI request tương ứng, có thể thay đổi do redirect so với object request khởi tạo ở đầu.
- `response.headers().firstValue("Location")` là **giá trị header do server cung cấp**. Nó có thể là đường dẫn tương đối, URL tuyệt đối hoặc không có; không tự có nghĩa client đã theo URL đó.
- `request.uri()` của request khởi tạo vẫn thể hiện đích ban đầu; **đừng dùng nó thay cho URI cuối** sau khi client tự theo redirect.

Một Location tương đối như `/middle` có thể được diễn giải thành đích kế tiếp dựa trên URI tại bước response, ví dụ:

~~~java
URI next = currentResponse.uri().resolve(
        currentResponse.headers()
                .firstValue("Location")
                .orElseThrow());
~~~

**Mã minh họa**, không tự gửi tiếp request. Cần kiểm giá trị Location, scheme, host, port và chính sách ứng dụng trước khi thực sự truy cập; `URI.resolve` chỉ thực hiện giải quyết URI, **không** làm validation bảo mật. Nếu Location thiếu, `orElseThrow()` ném exception.

## 5. Chương trình chạy được: chuỗi 302 → 301 → 200

Chương trình này dùng server HTTP **trên loopback** (`127.0.0.1`), cổng do hệ điều hành chọn. Không cần Internet, DNS hay tài khoản nào. Nó kiểm hai client:

1. Client **mặc định `NEVER`** nhận `302` tại `/start` và không đi tiếp.
2. Client `NORMAL` tự theo `/start → /middle → /final`, trả `200`, rồi duyệt chuỗi `previousResponse()`.

Tạo tệp **`RedirectChainDemo.java`**:

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

public class RedirectChainDemo {

    private static void redirect(
            HttpExchange exchange, int status, String location)
            throws IOException {

        exchange.getResponseHeaders().set("Location", location);
        exchange.sendResponseHeaders(status, -1);
        exchange.close();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/start",
                exchange -> redirect(exchange, 302, "/middle"));
        server.createContext("/middle",
                exchange -> redirect(exchange, 301, "/final"));

        server.createContext("/final", exchange -> {
            try {
                byte[] bytes = "finished".getBytes(
                        StandardCharsets.UTF_8);

                exchange.sendResponseHeaders(200, bytes.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(bytes);
                }
            } finally {
                exchange.close();
            }
        });

        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            HttpRequest request = HttpRequest.newBuilder(
                    URI.create(base + "/start"))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            // Không cấu hình redirect => mặc định NEVER.
            HttpClient noFollow = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();

            HttpResponse<String> direct = noFollow.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            System.out.println(
                    "default.policy=" + noFollow.followRedirects());
            System.out.println(
                    "direct.status=" + direct.statusCode());
            System.out.println(
                    "direct.uri=" + direct.uri().getPath());
            System.out.println(
                    "direct.location=" + direct.headers()
                            .firstValue("Location")
                            .orElse("(none)"));
            System.out.println(
                    "direct.hasPrevious="
                            + direct.previousResponse().isPresent());

            // NORMAL cho phép các chuyển hướng http -> http
            // của fixture cục bộ này.
            HttpClient follow = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .followRedirects(HttpClient.Redirect.NORMAL)
                    .build();

            HttpResponse<String> result = follow.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            System.out.println(
                    "final.status=" + result.statusCode());
            System.out.println(
                    "final.uri=" + result.uri().getPath());
            System.out.println(
                    "final.request="
                            + result.request().uri().getPath());
            System.out.println(
                    "final.body=" + result.body());

            // Duyệt ngược: từ response cuối về các hop trước.
            HttpResponse<String> node = result;
            int hop = 0;

            while (node.previousResponse().isPresent()) {
                node = node.previousResponse().get();
                hop++;

                System.out.println(
                        "previous" + hop
                                + "=" + node.statusCode()
                                + ":" + node.uri().getPath()
                                + ":bodyIsNull="
                                + (node.body() == null));
            }

            System.out.println("previous.count=" + hop);
        } finally {
            server.stop(0);
        }
    }
}
~~~

### Cách chạy

Dùng JDK đầy đủ có module `jdk.httpserver`:

~~~bash
javac --add-modules jdk.httpserver RedirectChainDemo.java
java --add-modules jdk.httpserver RedirectChainDemo
~~~

Mã client thuộc module Java SE `java.net.http`; `com.sun.net.httpserver.HttpServer` thuộc module JDK `jdk.httpserver` và **chỉ dùng để dựng server thử nghiệm**. Chương trình tương thích Java 11 và các JDK mới hỗ trợ các module này.

**Stdout đã được kiểm bằng chạy thực tế trên JDK:**

~~~text
default.policy=NEVER
direct.status=302
direct.uri=/start
direct.location=/middle
direct.hasPrevious=false
final.status=200
final.uri=/final
final.request=/final
final.body=finished
previous1=301:/middle:bodyIsNull=true
previous2=302:/start:bodyIsNull=true
previous.count=2
~~~

### Phân tích tại sao output đúng

1. `noFollow.followRedirects()` trả `NEVER` vì client không có `followRedirects(...)`. `direct` nhận ngay response `302` với header `Location: /middle` và `previousResponse()` rỗng.
2. Request đầu tiên có URI `/start`. Client `follow` được đặt `NORMAL` nên tự xử lý `302` sang `/middle` rồi `301` sang `/final`.
3. `result.statusCode() == 200` và `result.body() == "finished"` vì response cuối của server ở `/final` chứa byte UTF-8 đó.
4. `result.uri().getPath()` và `result.request().uri().getPath()` đều là `/final` trong trường hợp này. Không lấy chúng làm URI ban đầu.
5. `previousResponse()` của `200` trả node **gần nhất** là `301 /middle`; đọc thêm `previousResponse()` của node đó mới đến `302 /start`.
6. Các node trung gian được đọc qua `previousResponse()` có `body() == null` **theo hợp đồng API**, nên hai dòng `bodyIsNull=true` không phản ánh rằng chúng đã có hoặc không có body trên dây.
7. Có **hai** intermediate response nên `previous.count=2`. Không đếm `200` cuối là một “previous” hop.
8. Chỉ in **path**, không in port động, nên stdout có thể lặp lại chính xác dù máy chọn cổng khác nhau.

**Bài học thực hành:** nếu bạn chỉ đọc `result.statusCode()`, bạn sẽ thấy `200` và bỏ lỡ việc request đã đi qua `302`, `301`. `previousResponse()` giúp ghi nhận đường đi đó nhưng không lưu body trung gian.

## 6. Duyệt chuỗi theo hướng ngược và hướng thời gian

### 6.1. Duyệt ngược từ phản hồi cuối

Vì mỗi node chỉ chứa `Optional` của node ngay trước, có thể duyệt:

~~~java
HttpResponse<String> node = response;
while (node.previousResponse().isPresent()) {
    node = node.previousResponse().get();
    System.out.println(node.statusCode() + " " + node.uri());
}
~~~

**Đoạn mã minh họa**, với `response` đã có. Với chuỗi demo, output sẽ lần lượt là `301 /middle` rồi `302 /start` (nếu chỉ xét phần path).

Hoặc tránh lặp lời gọi `previousResponse()`:

~~~java
Optional<HttpResponse<String>> previous =
        response.previousResponse();

while (previous.isPresent()) {
    HttpResponse<String> node = previous.get();
    System.out.println(node.statusCode());
    previous = node.previousResponse();
}
~~~

Đoạn trên cần import `java.util.Optional`. Nó tránh gọi `Optional.get()` khi Optional rỗng.

### 6.2. Hiển thị lại theo thứ tự redirect đã diễn ra

Nếu cần báo cáo `302 /start → 301 /middle → 200 /final`, thu thập nodes và đảo danh sách:

~~~java
List<HttpResponse<String>> history = new ArrayList<>();
HttpResponse<String> current = response;

history.add(current);
while (current.previousResponse().isPresent()) {
    current = current.previousResponse().get();
    history.add(current);
}

Collections.reverse(history);

for (HttpResponse<String> item : history) {
    System.out.println(
            item.statusCode() + " " + item.uri().getPath());
}
~~~

Đây là **đoạn minh họa trong một method**, cần import `List`, `ArrayList`, `Collections`; `response` có từ một lời gọi `send`/`sendAsync` hoàn tất. Với demo ba bước, ý nghĩa output:

~~~text
302 /start
301 /middle
200 /final
~~~

Phần tử cuối là **response cuối**, còn các phần tử trước là intermediate responses. Khi cần phân tích auth/redirect, nên gắn nhãn từng node theo status và không mặc định mọi node trong lịch sử là redirect.

### 6.3. Giới hạn độ dài lịch sử trong việc hiển thị/log

Trong code hiển thị production, đừng giả định chuỗi lịch sử vô hạn hoặc có ít hơn một số cố định. Thư viện HTTP có cơ chế xử lý việc theo redirect, nhưng ngưỡng/hành vi thực tế có thể phụ thuộc bản JDK và cấu hình. Khi tạo logger, parser hoặc redirect thủ công, đặt giới hạn phù hợp:

~~~java
int maxHistoryToShow = 20; // Giới hạn trình bày, không phải hằng số JDK.
int count = 0;
HttpResponse<String> current = response;

while (current.previousResponse().isPresent()
        && count < maxHistoryToShow) {
    current = current.previousResponse().get();
    count++;
    // Ghi metadata đã được redaction, không log token nhạy cảm.
}
~~~

Đây là **mã minh họa**. `20` chỉ là cap do ứng dụng chọn cho việc log, **không phải số lần redirect tối đa được Java 11 bảo đảm**.

## 7. Header Location: URI tương đối, tuyệt đối và xử lý thủ công

Header `Location` có thể là:

- Đường dẫn tuyệt đối trên cùng host, ví dụ `/middle`.
- Đường dẫn tương đối, ví dụ `../next`.
- URI tuyệt đối, ví dụ `https://other.example/path`.
- Không có hoặc không hợp lệ, tùy phản hồi từ server.

Đừng nhầm `Location` với `response.uri()`: một cái là **đích được đề xuất**, một cái là **nguồn response thực tế**.

Nếu muốn **tự kiểm từng bước**, dùng client có `Redirect.NEVER` để ứng dụng tự kiểm status và Location:

~~~java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

HttpResponse<Void> response = client.send(
        request,
        HttpResponse.BodyHandlers.discarding());

int status = response.statusCode();

if (status == 301 || status == 302
        || status == 303 || status == 307 || status == 308) {
    String location = response.headers()
            .firstValue("Location")
            .orElseThrow(() -> new IllegalStateException(
                    "Redirect response without Location"));

    URI candidate = response.uri().resolve(location);

    // Kiểm tra candidate theo chính sách an toàn
    // (scheme, host, port, mạng đích, quyền, hop limit ...)
    // rồi mới quyết định có tạo request tiếp hay không.
}
~~~

**Mã minh họa, không phải chương trình độc lập.** `client`, `request`, `URI` và xử lý `IOException`/`InterruptedException` cần có trong scope; đoạn này chủ động **không gửi tiếp** cho đến khi có validation phù hợp.

### Vì sao không chỉ dựa vào Location rồi gọi lại send ngay?

1. **Location có thể chuyển sang host khác.** Nếu bạn tự copy `Authorization`, API key, cookie hoặc body nhạy cảm của request gốc sang host mới, có thể làm rò bí mật.
2. **Location có thể chuyển đến địa chỉ nội bộ/loopback.** Trong server-side app, redirect có thể mở đường cho SSRF nếu đích không được kiểm soát.
3. **HTTPS → HTTP là hạ cấp bảo mật.** `Redirect.NORMAL` tránh tự động theo hướng này; một vòng lặp tự viết phải thực thi chính sách tương ứng.
4. **Location có thể sai hoặc không tồn tại.** `URI.resolve`/`URI.create` có thể ném exception; ứng dụng cần xử lý và từ chối đúng cách.
5. **Số bước chuyển hướng cần được giới hạn.** Một server có thể tạo loop `/a → /b → /a` hoặc chuỗi rất dài. Không gọi vô hạn trong vòng lặp tự viết.
6. **HTTP method và body có thể thay đổi.** Không đơn giản gửi lại POST đến mọi đích bằng cách dùng cùng body publisher.

Nếu cần manual redirect, hãy thiết kế **một bộ điều phối redirect có chính sách rõ ràng**, có limit, deadline, validation và xử lý idempotency. Không dùng vòng lặp generic sao chép mọi header và body sang Location.

## 8. Redirect với POST: 301/302 khác 307/308

Phần này rất quan trọng khi request có side effect như tạo đơn hàng hoặc ghi dữ liệu.

Theo hành vi được ghi trong Javadoc Java 11 của `HttpClient.Redirect`:

- Với **`301` và `302`**, request `POST` khi tự động redirect sẽ **được chuyển thành `GET`**.
- Với **`307 Temporary Redirect` và `308 Permanent Redirect`**, ngữ nghĩa redirect là **giữ method** và body request; khi muốn gửi lại, BodyPublisher phải hỗ trợ việc phát lại phù hợp.
- Với **`303 See Other`**, client thường chuyển sang GET theo ngữ nghĩa xem tài nguyên khác, ngoại trừ những khác biệt theo phương thức/cách triển khai; không dùng 303 như quy tắc bảo toàn POST body.
- Vì vậy, **đừng suy luận từ URI cuối** rằng server đã nhận cùng phương thức và payload như request ban đầu.
- Khi có dữ liệu không thể phát lại (stream chỉ dùng một lần), việc redirect có thể thất bại hoặc không thực hiện như bạn kỳ vọng; cần thiết kế BodyPublisher có khả năng gửi lại khi hợp đồng yêu cầu.

### Kiểm chứng thực tế bằng một server phản chiếu method

Chương trình sau tạo `/redirect302` và `/redirect307`, cả hai chuyển tới `/reflect`. Endpoint `/reflect` trả chuỗi **method:số byte body** đã nhận.

Tạo tệp **`RedirectMethodDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpServer;

import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class RedirectMethodDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/redirect302", exchange -> {
            exchange.getResponseHeaders()
                    .set("Location", "/reflect");
            exchange.sendResponseHeaders(302, -1);
            exchange.close();
        });

        server.createContext("/redirect307", exchange -> {
            exchange.getResponseHeaders()
                    .set("Location", "/reflect");
            exchange.sendResponseHeaders(307, -1);
            exchange.close();
        });

        server.createContext("/reflect", exchange -> {
            try {
                // Input trong fixture chỉ do test sinh, dài 3 byte.
                byte[] received =
                        exchange.getRequestBody().readAllBytes();

                byte[] result = (
                        exchange.getRequestMethod()
                        + ":" + received.length
                ).getBytes(StandardCharsets.UTF_8);

                exchange.sendResponseHeaders(200, result.length);

                try (var out = exchange.getResponseBody()) {
                    out.write(result);
                }
            } finally {
                exchange.close();
            }
        });

        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .followRedirects(HttpClient.Redirect.NORMAL)
                    .build();

            for (int status : new int[] {302, 307}) {
                HttpRequest request = HttpRequest.newBuilder(
                        URI.create(base + "/redirect" + status))
                        .timeout(Duration.ofSeconds(5))
                        .POST(HttpRequest.BodyPublishers
                                .ofString("abc"))
                        .build();

                HttpResponse<String> response = client.send(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8));

                System.out.println(
                        "redirect" + status + ".final="
                        + response.body());

                System.out.println(
                        "redirect" + status + ".previous="
                        + response.previousResponse()
                                .orElseThrow()
                                .statusCode());
            }
        } finally {
            server.stop(0);
        }
    }
}
~~~

Chạy trên JDK 11+:

~~~bash
javac --add-modules jdk.httpserver RedirectMethodDemo.java
java --add-modules jdk.httpserver RedirectMethodDemo
~~~

**Stdout đã kiểm tra bằng chạy thực tế:**

~~~text
redirect302.final=GET:0
redirect302.previous=302
redirect307.final=POST:3
redirect307.previous=307
~~~

### Giải thích

- Với status `302`, `HttpClient.Redirect.NORMAL` tạo request chuyển tới `/reflect` theo method **GET**, không gửi ba byte body gốc. Server in `GET:0`.
- Với status `307`, method **POST** và body `abc` được giữ trong fixture này. Server in `POST:3`.
- Response cuối của cả hai request là status `200` từ `/reflect`. `previousResponse()` của nó là node trung gian chứa `302` hoặc `307` tương ứng.
- Phần code này **không khẳng định** mọi BodyPublisher stream đều có thể phát lại: nó dùng `BodyPublishers.ofString("abc")`, thích hợp cho ví dụ body nhỏ và có khả năng tái sử dụng.
- `exchange.getRequestBody().readAllBytes()` chỉ xuất hiện trong **server test cục bộ nhận body 3 byte tự tạo**. Server sản xuất nhận đầu vào không đáng tin phải giới hạn số byte, không đọc vô hạn vào RAM.
- Nếu nghiệp vụ là chuyển tiền hoặc đặt hàng, redirect POST có thể ảnh hưởng tính đúng đắn, quyền gửi dữ liệu và xử lý lặp. Kiểm tra hợp đồng server thay vì dựa vào mỗi status cuối.

## 9. previousResponse() với authentication và proxy

Javadoc `HttpResponse.previousResponse()` định nghĩa intermediate response có thể đến từ **redirect hoặc authentication**.

Ví dụ khái niệm:

~~~text
Request không có thông tin xác thực phù hợp
        |
        v
HTTP 401 Unauthorized (challenge)
        |
        v
Authenticator / cơ chế auth của client xử lý
        |
        v
Request có xác thực phù hợp
        |
        v
HTTP 200 OK
~~~

Đây là **sơ đồ tình huống**, không phải khẳng định rằng mọi 401 đều được client tự khôi phục. Tự xử lý authentication phụ thuộc `Authenticator`, cấu hình client, server, proxy và loại auth.

Những điều không nên giả định:

- Có `previousResponse()` nghĩa là **chắc chắn đã redirect**. Nó cũng có thể phản ánh authentication exchange.
- Không có `previousResponse()` nghĩa là **chưa bao giờ server gửi 3xx/401**. Ví dụ với `Redirect.NEVER`, response `302` trực tiếp có thể có `previousResponse()` rỗng.
- Mọi status `401`/`407` đều tự tạo thêm request. Điều đó tùy cơ chế auth và cấu hình thực tế.
- Từ một node intermediate có thể lấy lại **body lỗi/challenge** đầy đủ. Theo hợp đồng API, `body()` của node từ `previousResponse()` là `null`.
- Header `Location` của response intermediate có thể được log nguyên văn mà không kiểm tra. Redirect URL có thể chứa query nhạy cảm; cần redaction nếu ghi log.

Nếu mục tiêu chính là chẩn đoán HTTP authentication, hãy dùng các kiểm thử tích hợp với realm/credentials kiểm soát, tuyệt đối tránh đưa token thật vào log hoặc tài liệu bài học.

## 10. Kết quả send, sendAsync và thời điểm nhận chain

Dùng `HttpClient.send(...)`:

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));

Optional<HttpResponse<String>> previous =
        response.previousResponse();
~~~

Dùng `HttpClient.sendAsync(...)`:

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

CompletableFuture<Integer> previousCount = future.thenApply(r -> {
    int count = 0;
    while (r.previousResponse().isPresent()) {
        r = r.previousResponse().get();
        count++;
    }
    return count;
});
~~~

Hai đoạn trên là **minh họa trong method**, cần `client`, `request`, import và xử lý ngoại lệ phù hợp.

- Chính sách `followRedirects` đặt trên **cùng loại HttpClient** nên áp dụng cho cả `send` lẫn `sendAsync`.
- `send` trả response hoặc ngoại lệ sau khi chờ; `sendAsync` trả `CompletableFuture<HttpResponse<T>>`. Khi Future hoàn thành bình thường, bạn có thể duyệt `previousResponse()` như nhau.
- HTTP status `301`, `302` hoặc `404` không tự trở thành exception chỉ vì nó không phải 2xx. Nếu redirect bị chặn bởi policy, client có thể trả trực tiếp response 3xx; ứng dụng tự kiểm `statusCode()`.
- Nếu mạng hoặc xử lý response thất bại, `send` có thể ném `IOException`, `InterruptedException`; `sendAsync` có thể hoàn thành Future bất thường. **Không phải lúc nào cũng có response cuối để duyệt chain**.
- Với handler `ofString`/`ofByteArray`, body cuối được tích lũy trước khi Future hoàn thành bình thường. Với `ofInputStream`, Future có thể hoàn thành khi mới có headers, còn caller phải đọc/đóng stream của response **cuối**; body của intermediate vẫn là `null`.

### Không tự động biến status 404 sau redirect thành “thành công”

Giả sử:

~~~text
GET /old -> 301 Location: /new -> 404 Not Found
~~~

Khi client theo redirect, `response.statusCode() == 404` và `previousResponse()` có thể chứa `301`. Việc redirect xảy ra **không đảm bảo** đích cuối hợp lệ hoặc nghiệp vụ thành công. Kiểm cả status cuối và URI cuối.

## 11. Bảo mật khi tự theo chuyển hướng

Đây là nơi cấu hình redirect ảnh hưởng trực tiếp đến quyền truy cập dữ liệu.

### 11.1. Thay đổi origin là ranh giới tin cậy

Origin thường được phân biệt bởi scheme, hostname và port. Một redirect có thể đưa request từ:

~~~text
https://api.example.com/private
             |
             v
https://other.example/collect
~~~

Ngay cả khi vẫn là HTTPS, đích mới thuộc một bên khác hoặc một ranh giới trust khác.

- Không **tự động sao chép** `Authorization`, API key, cookie thủ công hay body nhạy cảm sang origin mới khi chưa kiểm chính sách.
- Dùng các khả năng quản lý auth/cookie của client theo contract, nhưng không coi implementation là cơ chế kiểm URL phía ứng dụng thay bạn.
- Khi request chứa bí mật, bạn có thể chọn `Redirect.NEVER` để kiểm status/Location và tự quyết định có cho follow không.
- Hạn chế ghi full redirect URL vào log khi có query param nhạy cảm.

### 11.2. HTTPS downgrade

~~~text
https://secure.example/path
             |
             v
http://insecure.example/path
~~~

`Redirect.NORMAL` của Java 11 **không** tự chuyển từ HTTPS sang HTTP. `Redirect.ALWAYS` cho phép chính sách redirect rộng hơn, bao gồm hướng chuyển này, nhưng **không** có nghĩa bạn nên bật nó trong ứng dụng mang dữ liệu nhạy cảm.

Không tắt TLS certificate validation chỉ để “redirect chạy được”. Với HTTPS, vẫn phải bảo đảm xác thực chứng chỉ/host phù hợp.

### 11.3. SSRF và mạng nội bộ

Trong web server/worker có khả năng gọi URL do người dùng đưa vào, redirect có thể là con đường để truy cập:

- `127.0.0.1` hoặc các địa chỉ loopback khác;
- địa chỉ mạng riêng hoặc service nội bộ;
- endpoint metadata của hạ tầng;
- những cổng không nằm trong phạm vi nghiệp vụ.

**Đừng chỉ kiểm URL ban đầu rồi cho phép auto redirect tới mọi nơi.** Việc giải quyết DNS, thay đổi địa chỉ theo thời gian và chuyển host khiến kiểm tra bằng chuỗi hostname đơn giản không đủ. Chính sách chống SSRF phải được thực thi ở tầng URL và ở **network egress boundary** phù hợp. Một số hệ thống cần khóa cả proxy, DNS, dải địa chỉ/cổng đích.

### 11.4. Vòng lặp và nhiều hop

Ví dụ:

~~~text
/a --302--> /b --302--> /a --302--> ...
~~~

Client có thể có cách giới hạn/chấm dứt redirect riêng theo implementation. **Không ghi cứng một số hop tối đa như một bảo đảm portable của Java 11** nếu API không tài liệu hóa. Nếu tự làm redirect, luôn có:

- Số hop tối đa (chính sách ứng dụng);
- Deadline tổng và timeout cho từng request;
- Kiểm URI đích hợp lệ;
- Chính sách thay đổi method và body;
- Kiểm nguồn/đích cho mỗi bước;
- Cơ chế xử lý loop hoặc URL lặp.

Đừng tạo vòng lặp `while(true)` theo Location mà không có điều kiện dừng.

### 11.5. POST và idempotency

Với request có side effect, timeout/redirect/cancellation **không chứng minh server chưa xử lý**. Nếu ứng dụng tạo đơn hàng, chuyển tiền hoặc ghi database, retry phải dựa trên hợp đồng idempotency phù hợp (ví dụ idempotency key hoặc endpoint có semantics an toàn). Một redirect làm thay đổi method như `302 POST → GET` càng cần được kiểm thử theo API thực tế.

## 12. Timeout, lỗi và xử lý response chuyển hướng

### 12.1. Timeout client và request

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();
~~~

**Đoạn minh họa** với `uri` đã tồn tại. `connectTimeout` chỉ giới hạn thời gian tạo kết nối mới; `request.timeout` quản lý hạn thời gian request theo API. Không có bảo đảm rằng mỗi hop được phép dùng trọn một timeout mới tách rời mà không tính vào deadline nghiệp vụ. Với hệ thống phức tạp, có thể thêm **deadline tổng** do ứng dụng quản lý.

### 12.2. Ngoại lệ không đồng nghĩa HTTP status

| Tình huống | Kết quả thường gặp | Điều cần làm |
| --- | --- | --- |
| Server trả 301/302 và client `NEVER` | `HttpResponse` với status 3xx | Đọc `Location` và quyết định thủ công |
| Server trả 301/302 và client `NORMAL` | Có thể theo redirect, trả response cuối | Kiểm URI/status cuối và history |
| Server trả 404 ở đích cuối | `HttpResponse` có status 404 | Xử lý lỗi nghiệp vụ, có thể xem previousResponse |
| DNS/TCP/TLS thất bại | `IOException` hoặc lớp con với `send` | Xử lý I/O, logging phù hợp |
| Bị request timeout | `HttpTimeoutException`/lớp con | Dừng/hủy theo chính sách; không tự kết luận server chưa xử lý |
| Thread chờ `send` bị ngắt | `InterruptedException` | Truyền lên hoặc khôi phục interrupt và thoát |
| `sendAsync` gặp lỗi | Future hoàn thành bất thường | `handle`/`exceptionally`/`whenComplete` hoặc truyền Future cho caller |
| Location xấu khi tự resolve | Exception URI hoặc lỗi validation ứng dụng | Từ chối redirect, không gửi sang đích tùy ý |

### 12.3. Nhìn status cuối trước khi phân tích chuỗi

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));

int code = response.statusCode();

if (code >= 200 && code < 300) {
    // Đánh giá body theo hợp đồng API.
} else if (code >= 300 && code < 400) {
    // Có thể là redirect chưa theo, hoặc 3xx khác.
    // Kiểm Location / chính sách ứng dụng.
} else {
    // 4xx, 5xx hoặc mã khác: xử lý theo API.
}
~~~

Đây là **đoạn mã minh họa**. Không tự coi “có previousResponse” là thành công, hoặc “không có previousResponse” là lỗi.

### 12.4. Body của response trung gian không dùng để debug nội dung

Nếu server trả trang HTML “Moved Permanently” ở bước `301`, nội dung HTML đó **không có trong `previous.body()`** vì API trả `null` ở intermediate node. Khi cần chẩn đoán thông điệp server trả trong một redirect, có thể gửi request bằng client `Redirect.NEVER` và chọn `BodyHandler` hợp lý cho **response trực tiếp**, với giới hạn byte và kiểm bảo mật.

Không cố dùng `previous.body().toString()`: điều này có thể gây `NullPointerException`.

## 13. Kiểm thử thiết kế theo ma trận

Bộ kiểm thử cần phân biệt **redirect policy**, **history shape** và **request semantics**.

| Ca test | Kỳ vọng |
| --- | --- |
| `NEVER`, response `302 Location: /next` | Nhận `302` trực tiếp; `previousResponse()` rỗng |
| `NORMAL`, `302 /start → 301 /middle → 200 /final` | Response cuối `200`, URI `/final`, hai node `301` rồi `302` khi duyệt ngược |
| Đúng một redirect | `previousResponse()` có một node; node đó `previousResponse()` rỗng |
| Không có redirect | `previousResponse()` rỗng |
| `Location` tương đối | URI kế tiếp được resolve đúng với URI bước hiện tại |
| `Location` tuyệt đối, host khác | Chính sách bảo mật/allowlist của ứng dụng xử lý |
| HTTPS → HTTP với `NORMAL` | Không tự theo downgrade |
| HTTP → HTTPS với `NORMAL` | Có thể được theo nếu hợp đồng/điều kiện cho phép |
| POST nhận `302` rồi đích phản chiếu method | Trong demo, đích nhận `GET`, không giữ payload |
| POST nhận `307` rồi đích phản chiếu method | Trong demo, đích nhận `POST` và 3 byte body |
| Đích cuối trả `404` | Response cuối status `404`; history vẫn có thể chứa hop redirect |
| Intermediate node được lấy qua `previousResponse()` | `body() == null`; status/headers/URI vẫn có |
| `sendAsync` với redirect | Future khi thành công có chain tương ứng |
| Redirect loop | Không treo vô hạn; kiểm giới hạn/deadline/cách chấm dứt theo client mục tiêu |
| 401/407 có xác thực | History có thể chứa intermediate authentication, không mặc nhiên là redirect |
| Thiếu `Location` hoặc Location sai | Không gửi tiếp mù quáng; xử lý theo API/chính sách |
| Vượt thời gian chờ / lỗi mạng | Không giả định có HttpResponse cuối để đọc previousResponse |

### 13.1. Test có assert, không chỉ in ra console

Đối với demo chính:

~~~java
if (direct.statusCode() != 302
        || direct.previousResponse().isPresent()) {
    throw new AssertionError("NEVER policy incorrect");
}

if (result.statusCode() != 200
        || !"/final".equals(result.uri().getPath())) {
    throw new AssertionError("Final redirect response incorrect");
}

HttpResponse<String> previous = result.previousResponse()
        .orElseThrow();

if (previous.statusCode() != 301
        || previous.body() != null) {
    throw new AssertionError("Intermediate response incorrect");
}
~~~

**Đoạn minh họa**, các biến `direct` và `result` là kết quả trong `RedirectChainDemo`. Có thể đặt assertion ngay sau các lời gọi để test tự phát hiện mismatch thay vì chỉ dựa vào việc đọc stdout.

### 13.2. Tại sao dùng server loopback?

- Không phụ thuộc Internet, DNS, proxy và website thật;
- Có thể xác định chính xác `Location`/status của mỗi bước;
- Không bị thay đổi do nhà cung cấp triển khai endpoint;
- Không đưa credential, token, URL riêng tư vào log;
- Có thể kiểm redirect loop, method và body trong fixture riêng.

Nếu dùng JUnit, có thể thay `System.out.println` bằng `assertEquals`, `assertTrue`, `assertFalse` và dựng/dọn server trong setup/teardown. JUnit là **thư viện test bên ngoài Java SE**, nên cần cấu hình dependency phù hợp; hai chương trình `RedirectChainDemo` và `RedirectMethodDemo` ở bài này **không cần JUnit**.

## 14. Những lỗi thường gặp

| Nhầm lẫn | Vì sao sai? | Cách đúng |
| --- | --- | --- |
| “Java HttpClient luôn tự theo redirect.” | Mặc định là `Redirect.NEVER` | Bật `NORMAL`/`ALWAYS` có chủ đích |
| “`previousResponse()` là một list.” | Nó trả `Optional<HttpResponse<T>>` | Duyệt liên kết lùi qua từng node |
| “`previousResponse()` trả redirect đầu tiên.” | Nó trả intermediate **gần nhất** | Duyệt ngược hoặc reverse danh sách |
| “Node trước luôn có `String` body như node cuối.” | API trả `null` cho node từ `previousResponse` | Đọc status/headers/URI, không dereference body |
| “Có history nghĩa là chắc chắn redirect.” | Authentication cũng tạo intermediate response | Kiểm status và ngữ cảnh |
| “`response.uri()` luôn là URI ban đầu.” | Auto redirect có thể đổi URI cuối | Phân biệt `request.uri()` gốc và `response.uri()` |
| “Header Location chính là URI đang được trả.” | Location đề xuất **URI kế tiếp** | Đọc `response.uri()` cho nguồn, resolve Location khi cần |
| “Mọi 3xx đều phải tự động theo.” | Có 3xx không phù hợp để follow hoặc bị policy chặn | Dựa trên API, status và policy |
| “`NORMAL` là an toàn với mọi URL.” | Nó chủ yếu tránh HTTPS → HTTP, không kiểm mọi SSRF | Kiểm host/port/egress và trust boundary |
| “`ALWAYS` là chế độ nên dùng mặc định.” | Cho phép chuyển hướng rộng hơn, có thể hạ cấp HTTPS | Chọn theo chính sách và rủi ro |
| “POST sang 302 luôn giữ POST.” | JDK HTTP Client chuyển POST→GET với 301/302 | Test method/body theo status |
| “POST sang 307 giống 302.” | 307 có ngữ nghĩa giữ method/body | Đảm bảo publisher có thể replay khi cần |
| “Đã theo redirect thì status cuối chắc chắn 200.” | Đích cuối có thể trả 404/500 | Kiểm `statusCode()` cuối |
| “`previous.body() == null` nghĩa là server không gửi body.” | Body trung gian không được giữ trong API | Không suy đoán raw wire bytes từ null |
| “Redirect loop có thể lặp vô hạn trong code tự viết.” | Không có hop limit là lỗi thiết kế | Thêm giới hạn, visited-set/deadline |
| “Có thể log mọi Location/Authorization.” | Dễ rò URL/token/query nhạy cảm | Redaction và giới hạn logging |
| “Một URI.parse thành công đủ để chống SSRF.” | Redirect/DNS/network có thể đổi đích thực tế | Áp chính sách ở nhiều tầng |
| “Client trả response thì network và nghiệp vụ đều thành công.” | HTTP 4xx/5xx vẫn là response hợp lệ | Xử lý status và errors riêng |

## 15. Checklist thực hành

- [ ] Biết rõ client đang dùng `NEVER`, `NORMAL` hay `ALWAYS`; không giả định default tự theo redirect.
- [ ] Đã phân biệt URI ban đầu, URI của response hiện tại và Location đề xuất cho bước sau.
- [ ] Code duyệt `previousResponse()` theo `Optional` an toàn; không gọi `get` khi rỗng.
- [ ] Khi cần thứ tự thời gian, duyệt lùi rồi đảo danh sách; không gán sai thứ tự hop.
- [ ] Không đọc body ở intermediate response, vì `body() == null` theo Javadoc.
- [ ] Có kiểm HTTP status cuối, kể cả khi đã đi qua các redirect.
- [ ] Có kiểm điều kiện policy nếu Location chuyển host/origin hoặc hạ cấp HTTPS.
- [ ] Không sao chép credential/body nhạy cảm sang host khác khi tự làm redirect.
- [ ] Với POST, đã xét sự thay đổi method do `301`/`302` và bảo toàn method theo `307`/`308`.
- [ ] Vòng lặp redirect tự viết có hop limit, deadline và xử lý Location thiếu/sai.
- [ ] Đã cấu hình connect timeout, request timeout và error handling.
- [ ] Test có case không redirect, một hop, nhiều hop, redirect bị chặn, POST, 404 cuối, lỗi mạng.
- [ ] Ví dụ và code không dùng API chỉ mới xuất hiện sau Java 11 nếu dự án còn target Java 11.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Tạo `HttpClient.newHttpClient()` rồi gửi GET tới `/start` trả `302 Location: /final`. `send` có tự đến `/final` không?

**Không.** Mặc định là `Redirect.NEVER`. Bạn nhận response `302` trực tiếp trừ khi cấu hình client để theo redirect.

**Câu 2.** Sau khi theo `302 → 301 → 200`, `response.previousResponse()` đầu tiên cho status nào?

**`301`.** Đó là response trung gian gần nhất với `200`. Gọi `previousResponse()` trên node `301` mới đến `302`.

**Câu 3.** `previousResponse().orElseThrow().body()` có thể chứa body HTML của redirect không?

**Không.** Javadoc `HttpResponse.body()` quy định node trả bởi `previousResponse()` có `body() == null`.

**Câu 4.** Nếu chuỗi redirect đến `/final` nhưng đích cuối trả `404`, có nên coi request thành công vì đã theo redirect?

**Không.** Redirect chỉ là quá trình đi qua các địa chỉ; cần kiểm status cuối và hợp đồng nghiệp vụ.

**Câu 5.** `Redirect.NORMAL` khác `ALWAYS` ở điểm quan trọng nào?

**`NORMAL` không tự theo redirect HTTPS → HTTP**. `ALWAYS` cho phép chính sách redirect rộng hơn; điều này có rủi ro lộ dữ liệu khi dùng với đích không đáng tin.

**Câu 6.** POST `"abc"` nhận `302` được client theo tự động, trong demo `/reflect` thấy phương thức và độ dài nào?

**`GET:0`.** Với `302`, Java HTTP Client chuyển POST thành GET cho request theo redirect của fixture.

**Câu 7.** Nếu POST `"abc"` nhận `307`, trong demo `/reflect` thấy gì?

**`POST:3`.** Method và body được bảo toàn trong fixture có thể phát lại body này.

**Câu 8.** Một node `previousResponse` có status `401`, chắc chắn là redirect?

**Không.** Nó có thể là một intermediate authentication exchange. Đừng nhầm tất cả node previous là 3xx.

**Câu 9.** `response.headers().firstValue("Location")` có URL tuyệt đối đến host khác. Có nên tự tạo request kế tiếp bằng toàn bộ header và token cũ?

**Không nên.** Kiểm chính sách origin, scheme, host/port, credential forwarding và SSRF trước. Với URL không đáng tin, cần kiểm network egress.

**Câu 10.** `sendAsync` và `send` có khác cách duyệt `previousResponse()` không?

**Không.** Khi đã có `HttpResponse<T>` hoàn thành bình thường, API history dùng giống nhau. Khác biệt là `sendAsync` trả `CompletableFuture` để nhận response sau.

## 17. Tài liệu tham khảo API chính thức

- [`HttpResponse` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html): `previousResponse()`, `uri()`, `request()`, `body()` và `statusCode()`; `body()` của intermediate response là `null`.
- [`HttpClient.Redirect` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html): `NEVER`, `NORMAL`, `ALWAYS`; lưu ý chuyển `POST` sang `GET` với `301`/`302`.
- [`HttpClient.Builder` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `followRedirects(...)`, `connectTimeout(...)` và cấu hình client.
- [`HttpClient` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): `send`, `sendAsync` và chính sách redirect mặc định.
- [`HttpRequest` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html): URI/method/body của request, kể cả request theo redirect.
- [`HttpResponse` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpResponse.html): API `previousResponse` và hợp đồng `body` vẫn có trên JDK hiện đại.
- [`HttpServer` — JDK 11](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): server loopback dùng trong các ví dụ tự kiểm thử.

**Tóm tắt:** `HttpResponse.previousResponse()` trả **một Optional chứa response trung gian gần nhất**, có thể lần ngược tiếp để dựng toàn bộ lịch sử. **Body của response trung gian là null** theo API; status, URI và headers vẫn đọc được. Java 11 **không tự theo redirect theo mặc định**; hãy chọn `NEVER`/`NORMAL`/`ALWAYS` đúng ý đồ, kiểm status cuối và đặc biệt lưu ý giới hạn chuyển hướng, bảo mật origin/TLS cùng sự thay đổi method của POST.