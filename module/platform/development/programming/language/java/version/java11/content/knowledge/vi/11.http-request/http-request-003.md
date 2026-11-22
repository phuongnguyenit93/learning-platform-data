# GET, POST, PUT, DELETE và phương thức HTTP tùy biến với Java 11+

## 1. Từ `HttpRequest` đến HTTP method

Từ **Java 11**, package `java.net.http` cung cấp HTTP Client API chuẩn gồm `HttpClient`, `HttpRequest` và `HttpResponse`. Khi một ứng dụng cần gọi REST API, phương thức HTTP (**HTTP method**) cho server biết kiểu thao tác mà client yêu cầu, ví dụ lấy dữ liệu, tạo bản ghi, thay thế tài nguyên hoặc xóa tài nguyên.

`HttpRequest` được tạo bằng **builder**. Các phương thức `GET()`, `POST(BodyPublisher)`, `PUT(BodyPublisher)` và `DELETE()` là những cách thiết lập HTTP method thuận tiện. Với phương thức không có hàm tiện ích tương ứng, dùng `method(String, BodyPublisher)`, ví dụ `method("PATCH", ...)` hoặc `method("OPTIONS", BodyPublishers.noBody())`.

Một request gồm các thành phần khác nhau:

- **URI**: địa chỉ tài nguyên, gồm scheme/host/path và có thể có query, ví dụ `https://api.example.com/items/42?view=full`.
- **Method**: `GET`, `POST`, `PUT`, `DELETE`, `PATCH` hoặc token HTTP hợp lệ khác.
- **Headers**: metadata như `Accept`, `Content-Type`, `Authorization`.
- **Request body** (nếu có): các byte được cung cấp qua `HttpRequest.BodyPublisher`.

`HttpRequest.newBuilder(uri).GET().build()` **chỉ tạo đối tượng request**; nó chưa thực hiện kết nối mạng. Muốn thật sự gửi cần gọi `HttpClient.send(...)` hoặc `sendAsync(...)`. Sau khi `build()`, đối tượng `HttpRequest` là immutable; có thể xây các request khác qua builder.

## 2. Những phương thức dựng request cần nhớ

| HTTP method | API của `HttpRequest.Builder` | Request body | Ý nghĩa thường gặp theo hợp đồng HTTP |
| --- | --- | --- | --- |
| `GET` | `.GET()`, cũng là method mặc định | Thường không có | Truy xuất biểu diễn của tài nguyên; dữ liệu lọc/tìm kiếm thường ở URI query. |
| `POST` | `.POST(BodyPublishers.ofString(...))` | Cấp `BodyPublisher`; có thể dùng `noBody()` | Gửi dữ liệu cho tài nguyên xử lý; thường tạo mới hoặc thực hiện hành động. |
| `PUT` | `.PUT(BodyPublishers.ofString(...))` | Cấp `BodyPublisher` | Tạo/thay thế trạng thái của tài nguyên đích theo hợp đồng API. |
| `DELETE` | `.DELETE()` | Không truyền body bằng cách tiện ích này | Yêu cầu xóa liên kết/tài nguyên đích. |
| `PATCH` | `.method("PATCH", publisher)` | Theo hợp đồng API, thường có patch document | Thay đổi một phần tài nguyên; `PATCH` là HTTP method tiêu chuẩn nhưng builder Java 11 không có hàm `PATCH()` riêng. |
| `OPTIONS` | `.method("OPTIONS", BodyPublishers.noBody())` | Ví dụ này là body rỗng | Hỏi server về tùy chọn giao tiếp của tài nguyên; phản hồi tùy máy chủ. |

**Điểm khác biệt quan trọng:** `GET()` và `DELETE()` không yêu cầu một `BodyPublisher`, còn `POST(...)` và `PUT(...)` yêu cầu đối số `BodyPublisher`. Nếu muốn gửi `POST` hoặc `PUT` mà không có payload, vẫn truyền `HttpRequest.BodyPublishers.noBody()`. Cách dùng `method(String, BodyPublisher)` xác định **cả tên method lẫn publisher**.

Số lượng method được server hỗ trợ do **hợp đồng API/server quyết định**. Việc builder tạo được một request `PATCH` không chứng minh endpoint hiểu `PATCH`. Nếu server không hỗ trợ một method cho tài nguyên, có thể trả `405 Method Not Allowed`; nếu không nhận diện/triển khai method, có thể trả `501 Not Implemented`.

## 3. Chương trình Java 11+ hoàn chỉnh: dựng sáu loại request

Chương trình dưới đây có thể biên dịch và chạy **không cần Internet**. Nó chỉ tạo các `HttpRequest` và in cấu hình; không gọi `send` nên không phụ thuộc dữ liệu hay trạng thái của server. Lưu thành **`HttpRequestMethodsDemo.java`**:

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.net.http.HttpRequest.BodyPublishers;
import java.nio.charset.StandardCharsets;

public class HttpRequestMethodsDemo {
    public static void main(String[] args) {
        URI items = URI.create("https://api.example.com/items");
        URI item = URI.create("https://api.example.com/items/42");

        HttpRequest get = HttpRequest.newBuilder(items)
                .GET()
                .build();

        HttpRequest post = HttpRequest.newBuilder(items)
                .header("Content-Type", "application/json; charset=UTF-8")
                .POST(BodyPublishers.ofString(
                        "{\"name\":\"Lan\"}", StandardCharsets.UTF_8))
                .build();

        HttpRequest put = HttpRequest.newBuilder(item)
                .header("Content-Type", "application/json; charset=UTF-8")
                .PUT(BodyPublishers.ofString(
                        "{\"name\":\"Minh\"}", StandardCharsets.UTF_8))
                .build();

        HttpRequest delete = HttpRequest.newBuilder(item)
                .DELETE()
                .build();

        HttpRequest patch = HttpRequest.newBuilder(item)
                .header("Content-Type", "application/json; charset=UTF-8")
                .method("PATCH", BodyPublishers.ofString(
                        "{\"active\":true}", StandardCharsets.UTF_8))
                .build();

        HttpRequest options = HttpRequest.newBuilder(items)
                .method("OPTIONS", BodyPublishers.noBody())
                .build();

        describe("GET", get);
        describe("POST", post);
        describe("PUT", put);
        describe("DELETE", delete);
        describe("PATCH", patch);
        describe("OPTIONS", options);
    }

    private static void describe(String label, HttpRequest request) {
        String contentType = request.headers()
                .firstValue("Content-Type")
                .orElse("(none)");

        System.out.println(label + " -> " + request.method()
                + " " + request.uri().getPath()
                + " | Content-Type: " + contentType);
    }
}
```

Chạy bằng **JDK 17+**, đồng thời mã nguồn vẫn tương thích Java 11:

```bash
javac HttpRequestMethodsDemo.java
java HttpRequestMethodsDemo
```

**Stdout chính xác:**

```text
GET -> GET /items | Content-Type: (none)
POST -> POST /items | Content-Type: application/json; charset=UTF-8
PUT -> PUT /items/42 | Content-Type: application/json; charset=UTF-8
DELETE -> DELETE /items/42 | Content-Type: (none)
PATCH -> PATCH /items/42 | Content-Type: application/json; charset=UTF-8
OPTIONS -> OPTIONS /items | Content-Type: (none)
```

Giải thích:

1. `GET` dùng `GET()` và không cung cấp payload. Trong Java HTTP client, `GET` cũng là method mặc định của một builder mới, nhưng gọi `GET()` tường minh giúp người đọc dễ hiểu.
2. `POST` tới `/items` mang JSON `{"name":"Lan"}`; `PUT` tới `/items/42` mang JSON `{"name":"Minh"}`. Chuỗi được biến thành byte UTF-8 bằng `BodyPublishers.ofString(..., StandardCharsets.UTF_8)`.
3. `DELETE` gọi `DELETE()`, không khai báo request body trong ví dụ.
4. `PATCH` dùng `method("PATCH", publisher)` vì builder Java 11 không cung cấp hàm `PATCH()` tiện ích. `OPTIONS` dùng `noBody()` vì ví dụ không cần dữ liệu gửi lên.
5. Chương trình chỉ đọc `request.method()`, `request.uri().getPath()` và header đã đặt. Các chuỗi in ra **không phải** phản hồi từ một server; chúng phản ánh cấu hình request được xây trong bộ nhớ.

## 4. `BodyPublisher` và `Content-Type` là hai việc khác nhau

Phương thức `POST(...)`, `PUT(...)`, `method(..., ...)` nhận một đối tượng `HttpRequest.BodyPublisher`. Publisher chịu trách nhiệm **cung cấp byte của phần request body** khi client thực sự gửi request.

Những cách có giá trị sử dụng hiện nay gồm:

| Publisher | Đầu vào | Khi nên dùng |
| --- | --- | --- |
| `BodyPublishers.noBody()` | Không có payload | Method cần publisher theo chữ ký nhưng request không có body. |
| `BodyPublishers.ofString(text, StandardCharsets.UTF_8)` | `String` và charset rõ ràng | Gửi JSON, text hoặc dữ liệu text đã được định dạng. |
| `BodyPublishers.ofByteArray(bytes)` | `byte[]` | Gửi dữ liệu nhị phân đã có trong bộ nhớ. |
| `BodyPublishers.ofFile(path)` | `Path` đến file | Gửi nội dung file qua publisher; cần xử lý lỗi có thể phát sinh khi thiết lập/đọc file. |
| `BodyPublishers.ofInputStream(supplier)` | Hàm cung cấp `InputStream` mới | Đọc nội dung từ stream; phải thiết kế supplier phù hợp nếu request cần phát lại body. |

**Không đồng nhất body với header.** `BodyPublishers.ofString(json, UTF_8)` chuyển chuỗi sang byte; nó không tự hiểu rằng payload là JSON. Nên đặt header phù hợp:

```java
.header("Content-Type", "application/json; charset=UTF-8")
.POST(BodyPublishers.ofString(json, StandardCharsets.UTF_8))
```

Đây là **đoạn mã minh họa bên trong chuỗi builder**, với biến `json` do ứng dụng định nghĩa; nó không phải chương trình độc lập. `Content-Type` mô tả **định dạng dữ liệu đang gửi**, còn `Accept` mô tả **kiểu biểu diễn phản hồi mong muốn**:

```java
.header("Accept", "application/json")
.header("Content-Type", "application/json; charset=UTF-8")
```

Không nên tự thiết lập các header bị HTTP client hạn chế hoặc các header framing như `Content-Length` trừ khi thật sự hiểu API. Content length thường được suy ra từ publisher khi biết được độ dài. Với dữ liệu nhị phân, chọn `Content-Type` thích hợp theo hợp đồng server.

### URI query không phải request body

Đối với truy vấn GET, các tham số như trang và từ khóa thường được mã hóa trong URI:

```java
URI uri = URI.create(
        "https://api.example.com/items?page=2&size=10");
HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
```

Đây là đoạn minh họa, cần import `URI` và `HttpRequest`. Khi URI được xây động, **mã hóa các giá trị query** bằng API phù hợp và charset rõ ràng; không nối trực tiếp chuỗi do người dùng nhập nếu có ký tự đặc biệt. Tránh đặt mật khẩu, token hay dữ liệu nhạy cảm trong query vì URL có thể xuất hiện trong log/lịch sử.

Việc có body trên `GET` không phải cách truyền dữ liệu phổ biến hoặc có ngữ nghĩa được chấp nhận rộng rãi; các lớp trung gian và server có thể không xử lý như mong đợi. Ưu tiên query hoặc endpoint được API mô tả rõ.

## 5. Khi cần method khác: `method(String, BodyPublisher)`

`HttpRequest.Builder.method(String, BodyPublisher)` cho phép đặt **method token hợp lệ** và body publisher. Ví dụ:

```java
HttpRequest patch = HttpRequest.newBuilder(
        URI.create("https://api.example.com/items/42"))
    .header("Content-Type", "application/json")
    .method("PATCH", BodyPublishers.ofString(
            "{\"active\":false}", StandardCharsets.UTF_8))
    .build();

HttpRequest options = HttpRequest.newBuilder(
        URI.create("https://api.example.com/items"))
    .method("OPTIONS", BodyPublishers.noBody())
    .build();
```

Các đoạn trên dùng lại import của chương trình hoàn chỉnh; không tự gửi request. **`PATCH` là method HTTP tiêu chuẩn**, còn “tùy biến” ở đây chỉ cách dùng API `method(...)` để chỉ định tên method mà builder không có hàm riêng.

Một số API riêng có thể định nghĩa HTTP method extension khác. Ví dụ tổng quát:

```java
HttpRequest extension = HttpRequest.newBuilder(uri)
        .method("REPORT", BodyPublishers.noBody())
        .build();
```

`uri` ở đây là một biến `URI` có sẵn. Chỉ dùng tên method như `REPORT` nếu giao thức/server thực sự hỗ trợ; Java cho phép thiết lập token nhưng **không bảo đảm** server hoặc proxy chấp nhận. Method name là token HTTP và **phân biệt chữ hoa/chữ thường** theo HTTP; nên dùng tên chuẩn viết hoa đúng như tài liệu API. Token không hợp lệ hoặc method bị implementation hạn chế có thể khiến builder ném `IllegalArgumentException`. Ví dụ một số implementation hạn chế `CONNECT`.

### DELETE có body không?

`DELETE()` là cách tiện ích tạo request DELETE **không có body**. Nếu một API **quy định rõ** rằng DELETE cần body, có thể dùng `method(...)`:

```java
HttpRequest deleteWithBody = HttpRequest.newBuilder(uri)
        .header("Content-Type", "application/json")
        .method("DELETE", BodyPublishers.ofString(
                "{\"reason\":\"duplicate\"}", StandardCharsets.UTF_8))
        .build();
```

Đoạn này không phải chương trình độc lập; `uri` là một `URI` có sẵn. Theo HTTP, body của DELETE **không có ngữ nghĩa chung được định nghĩa** và có thể bị một số server/proxy từ chối hoặc xử lý không nhất quán. Không thêm body vào DELETE trừ khi giao thức mà hai phía cùng dùng quy định và hỗ trợ nó.

Tương tự, nếu Java 11 cần tạo request `HEAD`, có thể dùng `method("HEAD", BodyPublishers.noBody())`. Tránh dùng hàm `HEAD()` khi mã phải biên dịch bằng JDK 11, vì hàm tiện ích đó chỉ được bổ sung ở các phiên bản JDK mới hơn.

## 6. Gửi request thật bằng `HttpClient`

Sau khi có `HttpRequest`, ứng dụng tạo/reuse `HttpClient`:

```java
HttpClient client = HttpClient.newHttpClient();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

int status = response.statusCode();
String responseBody = response.body();
```

Đoạn này là **minh họa đặt trong một phương thức có khai báo hoặc xử lý** `IOException` và `InterruptedException`, với biến `request` đã xây từ trước; cần import `java.net.http.HttpClient`, `java.net.http.HttpResponse` và `StandardCharsets`. Nó sẽ thực sự gửi network request nếu được thực thi. `HttpClient` thường nên được tái sử dụng cho nhiều request để tận dụng quản lý kết nối.

Nếu muốn bất đồng bộ, dùng:

```java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
```

Đây là đoạn minh họa, cần import `java.util.concurrent.CompletableFuture`. Kết quả đến qua `CompletableFuture`; ứng dụng có thể xử lý bằng `thenApply`, `thenAccept`, `handle`... và cần quản lý lỗi bất đồng bộ.

**Phân biệt lỗi kết nối với HTTP status:** `send(...)` trả về `HttpResponse` khi server phản hồi, kể cả mã `400`, `404` hoặc `500`; HTTP client không mặc nhiên chuyển mọi status 4xx/5xx thành exception. Ứng dụng phải kiểm tra `response.statusCode()` và xử lý theo hợp đồng API. `IOException` thường liên quan lỗi truyền nhận; `InterruptedException` có thể xuất hiện khi gửi đồng bộ bị ngắt.

Ví dụ xử lý minh họa:

```java
if (status >= 200 && status < 300) {
    // Xử lý phản hồi thành công theo hợp đồng API.
} else if (status == 404) {
    // Xử lý trường hợp tài nguyên không tìm thấy.
} else {
    // Xử lý trạng thái HTTP không mong đợi.
}
```

Không có stdout cố định cho ví dụ gửi thật: mã HTTP và response body phụ thuộc endpoint, quyền truy cập, kết nối, dữ liệu server và thời điểm gọi. Phần demo runnable phía trên cố tình **không gửi mạng** để kết quả có thể kiểm tra chính xác.

## 7. GET, POST, PUT, DELETE, PATCH khác nhau về ngữ nghĩa

| Method | “Safe” theo HTTP? | “Idempotent” theo HTTP? | Ý nghĩa thực tế |
| --- | --- | --- | --- |
| `GET` | Có | Có | Đọc tài nguyên; nhiều GET lặp lại không được nhằm tạo thay đổi trạng thái theo yêu cầu client. |
| `POST` | Không | Không được bảo đảm | Thường tạo hoặc xử lý dữ liệu; gửi lại có thể tạo tác động lặp. |
| `PUT` | Không | Có | Cùng yêu cầu thay thế trạng thái nhiều lần phải có tác động dự kiến như một lần. |
| `DELETE` | Không | Có | Xóa lặp lại vẫn nhằm cùng trạng thái xóa; response lần hai có thể khác lần đầu. |
| `PATCH` | Không | Không mặc định | Cập nhật một phần; có thể thiết kế idempotent nhưng không được giả định. |

“**Safe**” là ngữ nghĩa method về việc không yêu cầu tác động thay đổi trạng thái ngoài ý muốn; không có nghĩa luôn bảo mật hay ứng dụng chắc chắn không có log/counter. “**Idempotent**” là thuộc tính tác động dự kiến của nhiều request giống nhau lên server, **không phải** lời hứa rằng mọi lần đều trả cùng status hoặc response body.

Ví dụ, xóa một tài nguyên thành công có thể trả `204 No Content` ở lần đầu và `404 Not Found` ở lần sau, trong khi ý nghĩa idempotent của DELETE vẫn được giữ. Với `POST` tạo giao dịch hoặc đơn hàng, không nên tự động gửi lặp nếu chưa có cơ chế chống trùng lặp (ví dụ idempotency key theo hợp đồng API). Cần xét retry policy, timeout và lỗi mạng với hiểu biết về nghiệp vụ.

`PUT` thường hướng tới **thay thế** biểu diễn toàn bộ tài nguyên, còn `PATCH` diễn tả **thay đổi một phần**. Tuy nhiên, cách server kiểm tra payload, định dạng patch và kết quả cập nhật luôn phụ thuộc API cụ thể. Không suy ra “PUT chắc chắn thay mọi field” hay “PATCH luôn an toàn để retry” chỉ từ method.

## 8. Những lỗi thường gặp

**Lỗi 1 — quên body publisher của POST/PUT.** Không thể viết `.POST()` hay `.PUT()` không đối số. Nếu không cần body, dùng `.POST(BodyPublishers.noBody())` hoặc `.PUT(BodyPublishers.noBody())`.

**Lỗi 2 — muốn PATCH nhưng tìm `.PATCH()` trên Java 11.** Builder không có phương thức tiện ích đó. Dùng `.method("PATCH", publisher)`.

**Lỗi 3 — nghĩ `build()` gửi request.** `build()` chỉ tạo `HttpRequest`; muốn gọi server phải có `HttpClient.send` hoặc `sendAsync`.

**Lỗi 4 — gửi JSON nhưng bỏ Content-Type.** Publisher mã hóa chuỗi thành byte, không tự mô tả payload là JSON. Cần khai báo media type tương ứng, ví dụ `application/json; charset=UTF-8` nếu API chấp nhận.

**Lỗi 5 — đặt sai method/URI.** `GET /items` và `DELETE /items/42` là hai thao tác khác nhau. Dù path giống nhau, method khác sẽ dẫn đến route hoặc xử lý khác. Kiểm tra cả `request.method()` và `request.uri()`.

**Lỗi 6 — coi 404/500 như exception do Java tự ném.** HTTP status có thể được trả về bình thường trong `HttpResponse`; ứng dụng phải phân nhánh theo `statusCode()`.

**Lỗi 7 — tự retry POST/PATCH mà không hiểu tác động.** Network timeout không chứng minh server chưa xử lý request. Retry phải bám theo chính sách của API và cơ chế chống trùng lặp.

**Lỗi 8 — tự tạo tên method “bất kỳ” mà mong server hiểu.** Builder chỉ bảo đảm tạo request theo hợp đồng của thư viện; server/gateway có thể không hỗ trợ token đó. Method không hợp lệ hoặc bị hạn chế có thể bị từ chối ngay lúc dựng request.

**Lỗi 9 — nhầm header request với body.** `header("Authorization", "...")` là metadata để server xác thực, không phải request payload. Không đưa token vào URI hay log; chỉ dùng HTTPS cho dữ liệu nhạy cảm.

## 9. Câu hỏi tự kiểm tra

**Câu 1:** Vì sao `HttpRequest.newBuilder(uri).GET().build()` chưa gọi server?

**Đáp án:** `build()` chỉ đóng gói cấu hình thành `HttpRequest`. Cần gọi `HttpClient.send(...)` hoặc `sendAsync(...)`.

**Câu 2:** Đoạn nào tạo POST với body JSON trên Java 11?

**Đáp án:** `HttpRequest.newBuilder(uri).header("Content-Type", "application/json").POST(BodyPublishers.ofString(json, StandardCharsets.UTF_8)).build()`. `uri`/`json` là các biến đã có, và cần import tương ứng.

**Câu 3:** Muốn tạo PATCH và OPTIONS không có hàm tiện ích riêng thì làm sao?

**Đáp án:** `.method("PATCH", BodyPublishers.ofString(...))` cho PATCH có payload; `.method("OPTIONS", BodyPublishers.noBody())` cho OPTIONS không có payload.

**Câu 4:** `DELETE()` có tự đính kèm JSON payload không?

**Đáp án:** Không. Phương thức tiện ích `DELETE()` đặt method DELETE mà không cấp body. Chỉ dùng `method("DELETE", publisher)` khi giao thức đích quy định rõ body DELETE.

**Câu 5:** Server trả `404` khi gửi GET, có nhất thiết Java ném `IOException` không?

**Đáp án:** Không. `HttpClient.send(...)` có thể trả `HttpResponse` chứa `statusCode()==404`. Cần xử lý status ở tầng ứng dụng.

**Câu 6:** Cùng một DELETE gửi lại có nhất thiết trả về cùng HTTP status không?

**Đáp án:** Không. Idempotence mô tả tác động dự kiến lên trạng thái server, không buộc status/response phải giống nhau.

**Ghi nhớ:** Với Java 11+, dùng `GET()` cho GET, `POST(publisher)` cho POST, `PUT(publisher)` cho PUT, `DELETE()` cho DELETE không body, và `method("PATCH", publisher)` hay `method("OPTIONS", BodyPublishers.noBody())` khi cần method khác. `build()` chỉ tạo request; `HttpClient` mới gửi nó. Kiểm tra method, URI, headers, body và status theo hợp đồng HTTP/API.

**Tài liệu chuẩn:** [Java SE 11 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html); [Java SE 11 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html); [Java SE 25 — HttpRequest](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpRequest.html); [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110).
