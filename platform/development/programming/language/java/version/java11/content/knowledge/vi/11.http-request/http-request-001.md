# `HttpRequest.Builder` và quy trình tạo yêu cầu HTTP trong Java 11+

## 1. Khái niệm và mục tiêu

Từ **Java 11**, Java cung cấp HTTP Client API chuẩn trong module `java.net.http` (JEP 321). Thành phần **`HttpRequest.Builder`** dùng để cấu hình một yêu cầu HTTP trước khi đóng gói thành đối tượng `HttpRequest`:

```java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
        .GET()
        .build();
```

Đoạn trên **chỉ tạo yêu cầu**, chưa kết nối tới máy chủ. Để gửi đi, sử dụng **`HttpClient.send(...)`** hoặc **`HttpClient.sendAsync(...)`** sau đó.

Phân biệt ba trách nhiệm:

- **`HttpRequest.Builder`:** đối tượng **có thể thay đổi** để đặt URI, method, headers, body, timeout và một số lựa chọn khác. Các phương thức cấu hình trả về chính builder, nên có thể *method chaining*.
- **`HttpRequest`:** yêu cầu đã `build()`, **bất biến** về cấu hình. Có thể dùng làm đầu vào cho những lần gửi thích hợp.
- **`HttpClient`:** bộ máy thực thi kết nối, gửi yêu cầu, nhận phản hồi và chia sẻ tài nguyên. Nó có **`HttpClient.Builder` riêng**, không phải cùng loại với `HttpRequest.Builder`.

`HttpRequest.Builder` là API được hỗ trợ trong các JDK hiện đại, không phải API legacy. Bài này trình bày những phương thức **sẵn có từ Java 11** và còn áp dụng hiện nay.

## 2. Quy trình tạo một yêu cầu: từ URI đến `build()`

Một luồng làm việc điển hình:

1. **Chuẩn bị URI:** địa chỉ mục tiêu hợp lệ, thường dùng `https://...`.
2. **Tạo builder:** `HttpRequest.newBuilder(uri)` hoặc `HttpRequest.newBuilder().uri(uri)`.
3. **Cấu hình:** đặt HTTP method, request headers, request body nếu có, request timeout và các lựa chọn tùy nhu cầu.
4. **Gọi `build()`:** chốt cấu hình thành một `HttpRequest` mới.
5. **Gửi khi cần:** truyền `HttpRequest` cho `HttpClient.send` hoặc `sendAsync` và xử lý `HttpResponse`.

Ví dụ GET:

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.time.Duration;

HttpRequest get = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/api/items"))
        .timeout(Duration.ofSeconds(8))
        .header("Accept", "application/json")
        .GET()
        .build();
```

Đây là **đoạn minh họa** đặt trong phương thức/class có các import đã chỉ định, không phải một tệp Java độc lập. `GET()` có thể bỏ vì **GET là method mặc định** khi chưa chỉ định phương thức khác:

```java
HttpRequest alsoGet = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
        .build();
```

Để kiểm tra không gửi nhầm dữ liệu: `get.method()` trả `"GET"`, `get.uri()` là URI đã đặt; request chưa được gửi chỉ vì `build()` đã chạy.

## 3. Các phương thức của `HttpRequest.Builder` cần biết

| Nhóm | Phương thức Java 11 | Tác dụng |
| --- | --- | --- |
| Điểm đích | `uri(URI)` | Đặt hoặc thay địa chỉ của yêu cầu |
| Header | `header(name, value)` | **Thêm** một giá trị header, không xóa các giá trị cùng tên có sẵn |
| Header | `headers(name1, value1, name2, value2, ...)` | Thêm nhiều cặp tên–giá trị; số đối số phải chẵn |
| Header | `setHeader(name, value)` | **Thay thế toàn bộ giá trị cũ** của header cùng tên bằng giá trị mới |
| Method | `GET()`, `DELETE()` | Đặt GET hoặc DELETE; các cách gọi này không cung cấp request body |
| Method và body | `POST(BodyPublisher)`, `PUT(BodyPublisher)` | Đặt POST/PUT và body publisher |
| Method tùy chỉnh | `method(String, BodyPublisher)` | Đặt method và body publisher, ví dụ một method được ứng dụng/giao thức cho phép |
| Thời gian | `timeout(Duration)` | Đặt timeout dành cho yêu cầu |
| Giao thức | `version(HttpClient.Version)` | Đặt **phiên bản HTTP mong muốn**, không bảo đảm phiên bản thực tế |
| Trước khi gửi body | `expectContinue(boolean)` | Yêu cầu xử lý cơ chế `100 Continue` trước khi gửi body nếu phù hợp |
| Kết thúc cấu hình | `build()` | Trả về **một `HttpRequest` mới**, không thực hiện kết nối |
| Tạo bản sao | `copy()` | Tạo **builder mới** có trạng thái cấu hình giống builder hiện tại, có thể sửa độc lập |

Một chuỗi cấu hình thường có dạng:

```java
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/api/items"))
        .header("Accept", "application/json")
        .timeout(Duration.ofSeconds(8))
        .GET()
        .build();
```

**Không nhất thiết phải gọi mọi phương thức.** Lựa chọn URI, headers, method, body phụ thuộc hợp đồng HTTP API. Những giá trị mặc định hoặc tùy chọn khác của `HttpClient` có thể áp dụng khi builder không thiết lập.

## 4. HTTP method và request body

### 4.1. GET: phương thức mặc định

```java
HttpRequest get = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
        .GET()
        .build();
```

Theo cấu hình mặc định, GET không có body publisher. Trong chương trình minh họa ở mục 6, `get.bodyPublisher().isPresent()` cho kết quả `false`.

### 4.2. POST/PUT: thêm `BodyPublisher`

Đối với một API nhận JSON:

```java
HttpRequest post = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
        .header("Content-Type", "application/json; charset=utf-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                "{\"id\":7}", java.nio.charset.StandardCharsets.UTF_8))
        .build();
```

**Giải thích:**

- `POST(...)` vừa chọn method `POST`, vừa gắn **`HttpRequest.BodyPublisher`** có nhiệm vụ phát các byte của request body khi gửi.
- `BodyPublishers.ofString(text, UTF_8)` chuyển chuỗi thành byte UTF-8; bản overload chỉ nhận `String` cũng mặc định UTF-8 từ Java 11.
- `Content-Type` mô tả kiểu dữ liệu gửi cho server; **đừng mặc định rằng `ofString` sẽ tự đặt `Content-Type: application/json`**. Đặt header theo contract của API.
- `Accept: application/json`, nếu có, thể hiện kiểu nội dung phản hồi client mong muốn; nó **không thay thế** `Content-Type` mô tả body gửi đi.
- Byte body gửi thực tế chỉ xuất hiện khi `HttpClient` bắt đầu gửi yêu cầu; tạo `BodyPublisher` và gọi `build()` không đồng nghĩa đã gửi.

Một PUT tương tự:

```java
HttpRequest put = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items/7"))
        .header("Content-Type", "text/plain; charset=utf-8")
        .PUT(HttpRequest.BodyPublishers.ofString("updated"))
        .build();
```

### 4.3. DELETE và method tùy chỉnh

```java
HttpRequest delete = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items/7"))
        .DELETE()
        .build();

// Minh họa khi giao thức yêu cầu method khác và KHÔNG có body:
HttpRequest custom = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
        .method("PATCH", HttpRequest.BodyPublishers.noBody())
        .build();
```

Đoạn ví dụ `PATCH` **không có nghĩa server nào cũng hỗ trợ PATCH**, cũng không có nghĩa PATCH thường nên không có body. Muốn gửi JSON bằng PATCH theo API của bạn, chọn body publisher phù hợp (chẳng hạn `ofString(json, UTF_8)`). Một số method bị implementation hạn chế; không được giả định mọi chuỗi là method HTTP hợp lệ.

### 4.4. Các BodyPublisher thường dùng

| Cách tạo | Khi nào dùng |
| --- | --- |
| `BodyPublishers.noBody()` | Không gửi request body, thường đi với `method(...)` |
| `BodyPublishers.ofString(text, UTF_8)` | Body là văn bản, JSON hoặc XML đã xác định charset |
| `BodyPublishers.ofByteArray(bytes)` | Đã có body nhị phân trong `byte[]` |
| `BodyPublishers.ofFile(path)` | Muốn gửi nội dung một file; cần xử lý ngoại lệ/file access theo API |
| `BodyPublishers.ofInputStream(supplier)` | Muốn tạo stream khi cần gửi; supplier cần cung cấp stream phù hợp ở mỗi lần thử gửi lại |

**Cảnh báo về gửi lại:** đối tượng `HttpRequest` có thể được dùng để gửi nhiều lần, nhưng **body publisher phải hỗ trợ phát lại dữ liệu** cho mỗi lần subscribe nếu có retry/redirect. Nguồn đọc một lần hoặc dữ liệu đang thay đổi có thể khiến gửi lại không thành công hay không tạo cùng body. Kiểm tra khả năng tái sử dụng của nguồn dữ liệu, không chỉ tính bất biến của request.

## 5. Header: `header`, `headers` và `setHeader`

Ba phương thức này dễ bị nhầm:

```java
HttpRequest req = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
        .header("X-Trace", "first")
        .header("X-Trace", "second")
        .build();

// req.headers().allValues("X-Trace") là ["first", "second"].
```

Mỗi lần gọi `header(...)` **thêm một giá trị**, do đó một header có thể có nhiều giá trị.

```java
HttpRequest req2 = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
        .header("X-Trace", "first")
        .header("X-Trace", "second")
        .setHeader("X-Trace", "final")
        .build();

// req2.headers().allValues("X-Trace") là ["final"].
```

`setHeader(...)` **xóa các giá trị cùng tên trước đó trên builder** và thay bằng giá trị mới. Việc tra tên header không phân biệt chữ hoa–chữ thường theo quy tắc HTTP; có thể tra `allValues("x-trace")` dù lúc ghi là `"X-Trace"`.

Thêm nhiều cặp cùng lúc:

```java
HttpRequest req3 = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
        .headers("Accept", "application/json",
                 "X-Env", "dev")
        .build();
```

`headers(String... headers)` yêu cầu dãy tham số **tên, giá trị, tên, giá trị...**. Truyền số chuỗi lẻ gây `IllegalArgumentException`.

**Không phải header nào cũng được đặt thủ công.** Tên hoặc giá trị không hợp lệ, hoặc header do client tự quản lý (điển hình `Content-Length`), có thể bị từ chối bằng `IllegalArgumentException`. Authentication, cookie, redirect cũng có các chính sách cấu hình phía `HttpClient`; đừng nhét trực tiếp mọi loại thông tin vào request header rồi kỳ vọng client chấp nhận hoặc xử lý đúng.

## 6. Ví dụ Java 11 hoàn chỉnh, không cần kết nối Internet

Ví dụ này xây GET, rồi tái sử dụng builder thành POST và dùng `copy()` để tạo PUT. Chỉ **kiểm tra metadata request** nên đầu ra ổn định và không phụ thuộc máy chủ.

Tạo tệp **`RequestBuilderDemo.java`**:

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class RequestBuilderDemo {
    public static void main(String[] args) {
        URI endpoint = URI.create("https://example.com/api/items");
        HttpRequest.Builder builder = HttpRequest.newBuilder(endpoint)
                .timeout(Duration.ofSeconds(8))
                .header("Accept", "application/json")
                .header("X-Trace", "first")
                .header("X-Trace", "second");

        HttpRequest get = builder.build();
        System.out.println("GET method: " + get.method());
        System.out.println("GET path: " + get.uri().getPath());
        System.out.println("GET traces: " + get.headers().allValues("x-trace"));
        System.out.println("GET timeout seconds: "
                + get.timeout().orElseThrow().getSeconds());
        System.out.println("GET has body: " + get.bodyPublisher().isPresent());

        builder.setHeader("X-Trace", "final");
        builder.setHeader("Content-Type", "application/json; charset=utf-8");
        builder.POST(HttpRequest.BodyPublishers.ofString(
                "{\"id\":7}", StandardCharsets.UTF_8));
        HttpRequest post = builder.build();

        System.out.println("POST method: " + post.method());
        System.out.println("POST traces: " + post.headers().allValues("X-Trace"));
        System.out.println("POST body length: "
                + post.bodyPublisher().orElseThrow().contentLength());
        System.out.println("GET unchanged: " + get.method()
                + " " + get.headers().allValues("X-Trace"));

        HttpRequest put = builder.copy()
                .uri(URI.create("https://example.com/api/items/7"))
                .PUT(HttpRequest.BodyPublishers.ofString(
                        "updated", StandardCharsets.UTF_8))
                .build();
        System.out.println("COPY method and path: "
                + put.method() + " " + put.uri().getPath());

        HttpRequest sourceAgain = builder.build();
        System.out.println("SOURCE method and path: "
                + sourceAgain.method() + " " + sourceAgain.uri().getPath());

        try {
            HttpRequest.newBuilder().build();
            System.out.println("missing URI: unexpected");
        } catch (IllegalStateException expected) {
            System.out.println("missing URI: IllegalStateException");
        }

        try {
            HttpRequest.newBuilder(endpoint).timeout(Duration.ZERO);
            System.out.println("zero timeout: unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("zero timeout: IllegalArgumentException");
        }
    }
}
```

Biên dịch, chạy bằng JDK 11 trở lên:

```bash
javac --release 11 -encoding UTF-8 RequestBuilderDemo.java
java RequestBuilderDemo
```

**Đầu ra chính xác đã kiểm chứng:**

```text
GET method: GET
GET path: /api/items
GET traces: [first, second]
GET timeout seconds: 8
GET has body: false
POST method: POST
POST traces: [final]
POST body length: 8
GET unchanged: GET [first, second]
COPY method and path: PUT /api/items/7
SOURCE method and path: POST /api/items
missing URI: IllegalStateException
zero timeout: IllegalArgumentException
```

Giải thích kết quả:

1. Builder ban đầu đã có URI, timeout 8 giây, các headers; chưa gọi method nên `build()` tạo **GET** không có body publisher.
2. `header("X-Trace", ...)` gọi hai lần nên GET giữ `[first, second]`; tra `"x-trace"` bằng chữ thường vẫn ra hai giá trị.
3. Khi gọi `setHeader("X-Trace", "final")` trên builder **sau khi đã build GET**, rồi đặt POST, request POST mới chỉ còn `[final]`. Request GET trước đó vẫn giữ `GET [first, second]` vì **HttpRequest đã build là bất biến**.
4. JSON `{"id":7}` có **8 byte UTF-8** trong ví dụ ASCII. `bodyPublisher().orElseThrow().contentLength()` trả về `8`; việc biết độ dài body không đồng nghĩa đã gửi body.
5. `copy()` tạo bản sao cấu hình hiện tại; đổi URI và method sang PUT trên bản sao không đổi builder gốc. Vì vậy builder gốc vẫn tạo được POST với URI `/api/items`.
6. `HttpRequest.newBuilder().build()` thiếu URI nên ném `IllegalStateException`.
7. `timeout(Duration.ZERO)` không hợp lệ và ném `IllegalArgumentException`; request timeout phải **dương**.

Không có bất kỳ HTTP network request nào được gửi trong chương trình này. Tất cả thông tin hiển thị đều đến từ các đối tượng `HttpRequest` được xây dựng trong bộ nhớ.

## 7. Tính chất quan trọng của Builder và Request

### 7.1. Builder có trạng thái và không thread-safe

Các phương thức như `header`, `setHeader`, `uri`, `POST`, `timeout` **thay đổi chính builder** và trả về chính đối tượng đó. Vì vậy:

```java
HttpRequest.Builder builder = HttpRequest.newBuilder(
        URI.create("https://example.com/"));
builder.header("X-App", "demo");
HttpRequest first = builder.build();

builder.setHeader("X-App", "another");
HttpRequest second = builder.build();
```

`first` vẫn có header `X-App: demo`; `second` có `X-App: another`.

**Đừng chia sẻ một builder đang bị nhiều thread sửa cùng lúc**: `HttpRequest.Builder` không được đồng bộ hóa. Tạo builder riêng cho mỗi yêu cầu, hoặc dùng `copy()` rồi sửa bản sao khi muốn tạo nhiều request tương tự.

### 7.2. `build()` không đóng builder

`build()` trả một `HttpRequest` mới mỗi lần, nhưng **không biến builder thành đối tượng bất biến** và không tự gửi request. Sau `build()` bạn vẫn có thể cấu hình tiếp builder rồi xây request khác. Nếu cần một request độc lập từ cấu hình hiện tại, `copy()` giúp tách những thay đổi cho request tiếp theo.

### 7.3. `URI` và dữ liệu query

`URI.create(...)` nhận chuỗi URI hợp lệ, ví dụ:

```java
URI uri = URI.create("https://example.com/search?q=java%2011");
```

Khoảng trắng trong query đã được percent-encode thành `%20`. Khi tham số chứa dữ liệu người dùng, **không ghép thẳng** chuỗi chưa encode vào URI. Cần encode **từng thành phần** query bằng công cụ thích hợp; `URLEncoder` được thiết kế theo quy tắc form encoding và không nên dùng bừa lên toàn bộ URL vì có thể làm hỏng `://`, `/` hoặc `?`.

Builder chỉ chấp nhận URI có scheme phù hợp với HTTP client (thông thường `http`, `https`); scheme không hỗ trợ gây `IllegalArgumentException`. URI cú pháp sai có thể bị `URI.create` từ chối trước khi tới builder. Ưu tiên `https` khi truyền dữ liệu nhạy cảm và kiểm tra điểm đích do người dùng cung cấp để tránh gửi request đến host không mong muốn.

## 8. Timeout, HTTP version và `Expect: 100-continue`

### 8.1. Timeout cho yêu cầu

```java
HttpRequest req = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
        .timeout(Duration.ofSeconds(8))
        .build();
```

`timeout(Duration)` là **timeout theo request**, không phải cùng khái niệm với `HttpClient.Builder.connectTimeout(Duration)` vốn áp dụng cho việc thiết lập kết nối. Theo Javadoc, khi phản hồi không đến trong thời gian đã định, `send` có thể ném `HttpTimeoutException`, còn `sendAsync` hoàn thành thất bại với ngoại lệ liên quan. Khi không đặt timeout cho request, API không áp giới hạn thời gian hữu hạn từ tùy chọn này; trong ứng dụng thực tế nên chọn timeout hợp lý.

`Duration.ZERO` hoặc khoảng âm bị từ chối bằng `IllegalArgumentException`.

### 8.2. HTTP version chỉ là giá trị mong muốn

```java
HttpRequest req = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
        .version(java.net.http.HttpClient.Version.HTTP_2)
        .build();
```

Đây là **phiên bản giao thức mong muốn**, không bảo đảm sẽ dùng HTTP/2: còn tùy server, TLS/ALPN, môi trường kết nối và cấu hình client. Nếu không đặt `version` ở request, lựa chọn mặc định của `HttpClient` được dùng. Sau khi gửi, hãy kiểm tra `HttpResponse.version()` để biết phiên bản thật sự.

### 8.3. `expectContinue(true)`

```java
HttpRequest req = HttpRequest.newBuilder(
        URI.create("https://example.com/upload"))
        .expectContinue(true)
        .POST(HttpRequest.BodyPublishers.ofString("payload"))
        .build();
```

Tùy chọn này thể hiện mong muốn server phản hồi sơ bộ (chẳng hạn `100 Continue` hoặc mã lỗi) trước khi client bắt đầu phát body. Nó **không xác nhận server luôn trả 100**, không thay thế xử lý response và không cần bật cho mọi POST. Mặc định là `false`.

## 9. Sau khi `build()`: gửi request bằng `HttpClient`

`HttpRequest.Builder` **không gửi dữ liệu**. Khi có request đã cấu hình, sử dụng `HttpClient`:

```java
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

HttpClient client = HttpClient.newHttpClient();

// Giả sử biến request là HttpRequest đã được build,
// và endpoint thực sự có thể truy cập.
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

System.out.println(response.statusCode());
System.out.println(response.body());
```

**Đây là đoạn minh họa, không phải chương trình độc lập**: cần khai báo `request`, đặt trong phương thức có xử lý `IOException` và `InterruptedException`, và cần server thật để nhận response. Không có một mã HTTP hay body phản hồi cố định nào được giả định.

Gửi bất đồng bộ:

```java
java.util.concurrent.CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
```

`sendAsync` trả về `CompletableFuture`; cần xử lý hoàn tất thành công hoặc thất bại một cách tường minh, ví dụ `whenComplete(...)` hoặc `handle(...)`. Không giả định thứ tự thời gian của callback hay nội dung phản hồi khi chưa thực hiện request.

Khác nhau:

| Giai đoạn | API | Có thực hiện network? |
| --- | --- | --- |
| Tạo và cấu hình | `HttpRequest.newBuilder(...).header(...).POST(...)` | Không |
| Đóng gói | `builder.build()` | Không |
| Gửi đồng bộ | `client.send(request, BodyHandler)` | Có, khi thực thi |
| Gửi bất đồng bộ | `client.sendAsync(request, BodyHandler)` | Có, theo cơ chế bất đồng bộ |

`HttpClient` nên được tái sử dụng hợp lý để tận dụng kết nối và tài nguyên. Đừng tạo client mới cho từng phần tử của một vòng lặp chỉ vì mỗi request có builder riêng.

## 10. Lỗi thường gặp, kiểm tra và khắc phục

| Hiện tượng / hiểu sai | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `build()` ném `IllegalStateException` | Builder chưa có URI | Dùng `newBuilder(uri)` hoặc `uri(uri)` trước `build` |
| `URI.create(...)` ném lỗi | URI không đúng cú pháp, ví dụ chứa khoảng trắng chưa encode | Tạo URI hợp lệ; encode riêng thành phần query/path theo mục đích |
| `uri(...)` từ chối scheme | Không phải scheme HTTP được hỗ trợ | Dùng `http://` hoặc `https://` hợp lệ |
| `header(...)` gây `IllegalArgumentException` | Tên/giá trị không hợp lệ hoặc header bị hạn chế | Chỉ truyền header đúng chuẩn, không cố ghi `Content-Length` thủ công |
| Dự kiến header cũ bị ghi đè nhưng vẫn thấy hai giá trị | Dùng `header` nhiều lần | Dùng `setHeader` để thay toàn bộ giá trị cũ |
| Dự kiến thêm header mới nhưng giá trị cũ biến mất | Dùng `setHeader` thay vì `header` | Chọn đúng phương thức theo số giá trị cần có |
| `headers(...)` báo lỗi | Số chuỗi không chẵn hoặc tên/giá trị sai | Truyền theo cặp `name, value` |
| `timeout(Duration.ZERO)` báo lỗi | Request timeout phải dương | Dùng `Duration.ofSeconds(...)` với giá trị dương |
| Gọi `build()` nhưng không thấy server nhận request | `build` không gửi HTTP | Gọi `client.send`/`sendAsync` trên request đã xây |
| POST có nội dung JSON nhưng server báo sai format | Chưa đặt `Content-Type` hoặc JSON không hợp lệ | Đặt header đúng contract và tạo body hợp lệ bằng serializer thích hợp |
| Chỉ định `HTTP_2` nhưng phản hồi là `HTTP_1_1` | `version` là ưu tiên, không bảo đảm | Kiểm tra `response.version()` và điều kiện hỗ trợ của server |
| Đổi builder rồi thấy request cũ khác với request mới | Builder mutable, request đã build immutable | Tạo builder mới hoặc `copy()` cho cấu hình độc lập |
| Nhiều thread tạo request lẫn cấu hình của nhau | Chia sẻ builder mà không đồng bộ hóa | Mỗi thread/request có builder riêng; không ghi chung đồng thời |
| Retry body từ stream thất bại | `BodyPublisher` không thể tái phát nguồn dữ liệu | Dùng publisher có khả năng tái tạo dữ liệu ở mỗi lần gửi |
| Thông tin bí mật xuất hiện trong log | In nguyên URI, Authorization hoặc cookie | Che/redact thông tin nhạy cảm; không log toàn bộ body/header trong production |

Về lỗi gửi: `HttpRequest` được tạo hợp lệ **không bảo đảm** request thành công qua mạng. Kết nối bị từ chối, DNS, timeout, TLS, HTTP status lỗi, body/charset và chính sách retry đều là phần của quy trình gửi/nhận — phải xử lý riêng. Phân biệt **lỗi cấu hình request** với **lỗi truyền tải/response**.

## 11. Best practices khi sử dụng trong dự án

1. **Xây request sát nơi có dữ liệu đầu vào:** lấy base URI tin cậy, tạo đường dẫn/query đã encode, xác định method và body từ contract API.
2. **Tách lớp chịu trách nhiệm:** hàm tạo `HttpRequest` không nhất thiết phải gọi network; lớp dùng `HttpClient` chịu trách nhiệm gửi, xử lý timeout, status và phản hồi. Điều này giúp unit test bằng cách kiểm tra `method()`, `uri()` và `headers()` mà không cần Internet.
3. **Chọn headers có mục đích:** `Accept` mô tả response mong muốn; `Content-Type` mô tả body bạn gửi. Đừng đặt `Content-Length` thủ công khi publisher/client tự quản lý.
4. **Ưu tiên HTTPS** và kiểm tra URI đầu vào; ứng dụng server gọi URL tùy ý do người dùng cung cấp cần có chính sách chống SSRF và danh sách đích được phép khi phù hợp.
5. **Không chia sẻ builder mutable giữa các thread.** Tái sử dụng `HttpClient` khác với tái sử dụng `HttpRequest.Builder`.
6. **Kiểm soát timeout và nguồn body.** Request có thể được gửi lại trong một số quy trình; với body file/stream, cần bảo đảm dữ liệu còn đọc được và không bị thay đổi ngoài ý muốn.
7. **Không in token và dữ liệu nhạy cảm:** nếu cần debug request, log có chọn lọc method, endpoint đã loại bỏ query nhạy cảm, thời gian và status; không log nguyên `Authorization`, cookie hoặc payload.
8. **Dùng Java 11+ API hiện hành:** phương thức `newBuilder`, `uri`, `header`, `setHeader`, `GET`, `POST`, `PUT`, `DELETE`, `method`, `timeout`, `version`, `expectContinue`, `copy` và `build` đều được hỗ trợ. Các API mới bổ sung ở những JDK về sau không cần thiết cho bài học này.

## 12. Bài tập tự kiểm tra

**Bài 1.** Cần gửi GET tới `https://example.com/api/items`, nhận JSON, timeout 10 giây. Hãy mô tả chuỗi gọi.  
**Đáp án:**

```java
HttpRequest req = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
        .header("Accept", "application/json")
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();
```

Đoạn này giả định đã import `HttpRequest`, `URI` và `Duration`.

**Bài 2.** `builder.header("X-Key", "a").header("X-Key", "b")` khác gì `builder.setHeader("X-Key", "b")`?  
**Đáp án:** hai lệnh `header` tạo hai giá trị `a` và `b` cho cùng tên; `setHeader` thay các giá trị cũ thành một giá trị `b`.

**Bài 3.** Lệnh `HttpRequest.newBuilder().build()` có gửi request không và lỗi gì?  
**Đáp án:** không gửi; thiếu URI nên `build` ném `IllegalStateException`.

**Bài 4.** Tạo GET từ builder, sau đó sửa builder thành POST: GET có thay đổi không?  
**Đáp án:** không. `HttpRequest` đã build là bất biến; builder vẫn có thể sửa cho request kế tiếp.

**Bài 5.** Tạo POST body JSON nhưng quên `Content-Type`. `BodyPublishers.ofString(json)` có tự khai báo JSON không?  
**Đáp án:** không. Nó biến String thành byte (mặc định UTF-8), còn header nội dung cần đặt đúng hợp đồng API.

**Bài 6.** `builder.version(HTTP_2)` có bảo đảm request dùng HTTP/2 không?  
**Đáp án:** không. Đây là phiên bản mong muốn; xem `HttpResponse.version()` để biết thực tế sau khi gửi.

## 13. Ghi nhớ

- **`HttpRequest.Builder`** là đối tượng cấu hình mutable; **`HttpRequest` sau `build()` bất biến**.
- Quy trình đúng: **URI → headers/method/body/timeout → `build()` → `HttpClient.send` hoặc `sendAsync`**.
- **GET mặc định**, POST/PUT cần `BodyPublisher` phù hợp; `header` **thêm** giá trị, `setHeader` **thay** các giá trị cũ cùng tên.
- `build()` **không gửi network**, chỉ tạo request mới. `copy()` cho phép tách các biến thể builder độc lập.
- `timeout` phải dương, `version` chỉ là đề xuất giao thức, `expectContinue` là lựa chọn theo yêu cầu giao tiếp.
- Kiểm tra URI và header hợp lệ, dùng HTTPS, đặt charset và `Content-Type` có chủ đích, quản lý retry và bí mật đúng cách.

**Tài liệu chính thức còn áp dụng:** [JEP 321 — HTTP Client (Standard)](https://openjdk.org/jeps/321); [Java 11 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html); [Java 11 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html); [Java 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html); [Java hiện hành — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html).