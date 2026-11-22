# Trạng thái HTTP, header và dữ liệu phản hồi với Java 17

## 1. Một phản hồi HTTP gồm những gì?

Khi ứng dụng Java gửi request đến máy chủ web, máy chủ trả về một **HTTP response**. Response cho biết kết quả xử lý request, cung cấp metadata và có thể mang dữ liệu mà ứng dụng cần sử dụng.

Một response HTTP thường có ba phần:

~~~text
HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 46
Cache-Control: no-store

{"id":42,"status":"PAID","active":true}
~~~

| Phần | Vai trò | Ví dụ |
|---|---|---|
| Status code | Cho biết kết quả xử lý request. | `200`, `404`, `503` |
| Headers | Mô tả response, nội dung, cache, xác thực, chuyển hướng... | `Content-Type`, `ETag`, `Location` |
| Body | Dữ liệu phản hồi nếu status và phương thức cho phép có nội dung. | JSON, HTML, ảnh, tệp hoặc văn bản |

Với HTTP/2, định dạng trên dây không còn là status line văn bản giống HTTP/1.1; giao thức dùng pseudo-header như `:status` và truyền header/body theo frame. Tuy nhiên, ở cấp ứng dụng, bạn vẫn làm việc với status code, headers và body. Java 17 HttpClient cung cấp API thống nhất cho các phiên bản HTTP mà nó hỗ trợ.

Trong Java 17, nên dùng `java.net.http.HttpClient`, được chuẩn hóa từ Java 11, để gửi request và đọc response. `HttpResponse<T>` chứa status code, headers, body và metadata liên quan.

## 2. Status code: phân loại kết quả xử lý

HTTP status code là số nguyên ba chữ số. Chữ số đầu tiên xác định nhóm kết quả:

| Nhóm | Ý nghĩa | Cách hiểu |
|---|---|---|
| `1xx` | Informational | Thông tin về tiến trình giao thức; thường không phải response cuối cùng mà ứng dụng xử lý. |
| `2xx` | Success | Request được tiếp nhận và xử lý thành công theo ngữ nghĩa của status cụ thể. |
| `3xx` | Redirection | Client cần hoặc có thể thực hiện hành động liên quan đến tài nguyên khác hoặc cache. |
| `4xx` | Client error | Request có vấn đề, không được phép hoặc không thể xử lý theo trạng thái tài nguyên hiện tại. |
| `5xx` | Server error | Máy chủ hoặc gateway gặp lỗi khi cố xử lý request hợp lệ. |

Không nên chỉ kiểm tra status có bằng `200` hay không. Một request thành công có thể trả về `201`, `202` hoặc `204` tùy thao tác.

### 2.1. Các status thành công thường gặp

| Code | Tên | Ý nghĩa thực tế |
|---:|---|---|
| `200` | OK | Request thành công; thường có body chứa representation hoặc kết quả. |
| `201` | Created | Một tài nguyên mới đã được tạo. Header `Location` có thể chỉ URI của tài nguyên vừa tạo. |
| `202` | Accepted | Request đã được chấp nhận để xử lý, nhưng xử lý có thể chưa hoàn tất. Client không nên hiểu đây là kết quả nghiệp vụ cuối cùng. |
| `204` | No Content | Request thành công nhưng response không có body. Thường gặp ở thao tác cập nhật/xóa không cần trả representation. |
| `206` | Partial Content | Máy chủ trả một phần representation, thường do request dùng `Range`. |

Ví dụ, khi tạo đơn hàng, API có thể trả `201 Created` cùng `Location: /orders/42` và body mô tả đơn hàng. Khi yêu cầu xóa một tài nguyên, API có thể trả `204 No Content`.

**Đừng cố parse JSON khi response không có body.** Với `204`, hoặc response không có nội dung theo hợp đồng, ứng dụng nên xử lý status trước rồi mới phân tích body nếu thực sự có.

### 2.2. Các status chuyển hướng

| Code | Tên | Lưu ý |
|---:|---|---|
| `301` | Moved Permanently | URI tài nguyên đã được chuyển vĩnh viễn. |
| `302` | Found | Chuyển hướng tạm thời. |
| `303` | See Other | Client được hướng tới tài nguyên khác, thường truy cập bằng GET. |
| `307` | Temporary Redirect | Chuyển hướng tạm thời và giữ nguyên phương thức request. |
| `308` | Permanent Redirect | Chuyển hướng vĩnh viễn và giữ nguyên phương thức request. |
| `304` | Not Modified | Representation không thay đổi so với validator client gửi; client có thể dùng bản cache. Đây là status 3xx nhưng không phải chuyển hướng tới URI khác. |

Các status chuyển hướng thường đi kèm header `Location`, ngoại trừ `304` có ngữ nghĩa cache riêng. Chính sách tự động theo redirect được cấu hình trên `HttpClient`; không nên mặc định mọi redirect đều an toàn hoặc phù hợp.

### 2.3. Các status lỗi phía client

| Code | Tên | Tình huống thường gặp |
|---:|---|---|
| `400` | Bad Request | Cú pháp request hoặc dữ liệu gửi lên không hợp lệ. |
| `401` | Unauthorized | Thiếu hoặc không có thông tin xác thực hợp lệ; response thường kèm `WWW-Authenticate`. |
| `403` | Forbidden | Máy chủ hiểu request nhưng từ chối thực hiện do quyền truy cập hoặc chính sách. |
| `404` | Not Found | Không tìm thấy tài nguyên được yêu cầu, hoặc máy chủ không muốn tiết lộ sự tồn tại của nó. |
| `405` | Method Not Allowed | Phương thức HTTP không được hỗ trợ cho tài nguyên; có thể có header `Allow`. |
| `409` | Conflict | Request xung đột với trạng thái hiện tại của tài nguyên, ví dụ cập nhật phiên bản cũ. |
| `412` | Precondition Failed | Điều kiện trong header như `If-Match` không được thỏa mãn. |
| `415` | Unsupported Media Type | Máy chủ không hỗ trợ định dạng body được gửi lên. |
| `422` | Unprocessable Content | Nội dung có cú pháp hợp lệ nhưng không thể xử lý theo quy tắc nghiệp vụ. |
| `429` | Too Many Requests | Client gửi quá nhiều request trong một khoảng thời gian; có thể kèm `Retry-After`. |

`401` và `403` không đồng nghĩa: `401` liên quan đến xác thực (*authentication*), còn `403` là từ chối quyền thực hiện (*authorization/policy*). Tuy nhiên, ứng dụng không nên suy luận quá nhiều chi tiết nội bộ chỉ từ status.

### 2.4. Các status lỗi phía máy chủ

| Code | Tên | Ý nghĩa |
|---:|---|---|
| `500` | Internal Server Error | Lỗi nội bộ không được xử lý thành response nghiệp vụ cụ thể. |
| `501` | Not Implemented | Máy chủ không hỗ trợ chức năng cần thiết để xử lý request. |
| `502` | Bad Gateway | Gateway/proxy nhận response không hợp lệ từ upstream. |
| `503` | Service Unavailable | Máy chủ tạm thời không sẵn sàng, có thể do bảo trì hoặc quá tải. |
| `504` | Gateway Timeout | Gateway/proxy không nhận được response kịp thời từ upstream. |

Các status `5xx` không chứng minh thao tác nghiệp vụ chắc chắn chưa xảy ra. Máy chủ có thể đã ghi dữ liệu thành công nhưng kết nối bị đứt trước khi response tới client. Với thao tác ghi, retry mù quáng có thể tạo bản ghi trùng. Hãy thiết kế idempotency key hoặc cơ chế kiểm tra trạng thái theo hợp đồng API khi cần.

## 3. HTTP headers: metadata của request và response

Header là các trường metadata đi kèm thông điệp HTTP. Header có thể mô tả kiểu nội dung, cách cache, thông tin xác thực, điều kiện request, chuyển hướng hoặc giới hạn truy cập.

### 3.1. Header trong request

| Header | Mục đích | Ví dụ |
|---|---|---|
| `Accept` | Các media type client có thể nhận. | `application/json` |
| `Content-Type` | Kiểu dữ liệu của request body. | `application/json; charset=UTF-8` |
| `Authorization` | Thông tin xác thực theo cơ chế đã thỏa thuận. | `Bearer ...` |
| `User-Agent` | Nhận diện ứng dụng client. | Tên ứng dụng và phiên bản |
| `If-None-Match` | Điều kiện cache dựa trên ETag. | `"v17"` |
| `If-Match` | Điều kiện cập nhật dựa trên ETag hiện tại. | `"v17"` |
| `Range` | Yêu cầu một phần representation. | `bytes=0-999` |

`Accept` và `Content-Type` thường bị nhầm:

- `Accept` trả lời: "Client muốn **nhận** loại nội dung nào?"
- `Content-Type` trả lời: "Body hiện tại **được biểu diễn** bằng loại nội dung nào?"

Với GET không có body, thường đặt `Accept`. Với POST gửi JSON, đặt `Content-Type: application/json` và có thể đồng thời đặt `Accept: application/json`.

### 3.2. Header trong response

| Header | Mục đích |
|---|---|
| `Content-Type` | Media type và có thể cả charset của body. |
| `Content-Length` | Kích thước body theo byte nếu được cung cấp. |
| `Content-Encoding` | Mã hóa nội dung như gzip nếu có. |
| `Cache-Control` | Chỉ thị cache. |
| `ETag` | Validator định danh phiên bản representation. |
| `Last-Modified` | Thời điểm representation được sửa lần cuối. |
| `Location` | URI liên quan tới tài nguyên được tạo hoặc đích chuyển hướng. |
| `Retry-After` | Thời điểm hoặc khoảng thời gian client nên chờ trước khi thử lại. |
| `WWW-Authenticate` | Thử thách xác thực trong response `401`. |
| `Allow` | Các phương thức được tài nguyên hỗ trợ, thường thấy với `405`. |
| `Vary` | Những request header ảnh hưởng đến việc chọn representation/cache. |
| `Set-Cookie` | Chỉ thị đặt cookie ở client. |

Header là metadata, không phải dữ liệu nghiệp vụ thay thế body. Ví dụ `ETag` có thể giúp client xác định representation có đổi hay không, nhưng không chứa toàn bộ nội dung tài nguyên.

### 3.3. Tên header không phân biệt chữ hoa/chữ thường

Theo HTTP, tên header không phân biệt chữ hoa/chữ thường. Các tên `Content-Type`, `content-type` và `CONTENT-TYPE` là cùng một header. Giá trị của header lại tuân theo ngữ nghĩa riêng của từng trường; không được tự động coi mọi giá trị đều không phân biệt hoa thường.

Một header có thể xuất hiện nhiều lần hoặc chứa nhiều giá trị. Ví dụ `Set-Cookie` thường có nhiều trường riêng biệt; không nên gộp tùy tiện thành một chuỗi phân cách bằng dấu phẩy. Khi đọc headers, hãy dùng API trả về danh sách giá trị.

## 4. Đọc status và headers bằng Java 17 HttpClient

Java 17 cung cấp các kiểu chính:

- `HttpClient`: cấu hình và gửi request; nên tái sử dụng một client cho nhiều request.
- `HttpRequest`: URI, phương thức, headers, timeout và body publisher của request.
- `HttpResponse<T>`: status, headers, body và metadata của response.
- `HttpHeaders`: tập header không sửa được mà response trả về.
- `BodyHandlers`: chọn cách nhận và chuyển body thành kiểu dữ liệu mong muốn.

### 4.1. Gửi GET và đọc response

Ví dụ sau dùng một API công khai giả định trả JSON UTF-8 tại URI được cấu hình:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class ReadHttpResponse {
    private ReadHttpResponse() {
    }

    public static void main(String[] args) {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/api/orders/42"))
                .timeout(Duration.ofSeconds(10))
                .header("Accept", "application/json")
                .GET()
                .build();

        try {
            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            int status = response.statusCode();
            System.out.println("Status: " + status);
            System.out.println("HTTP version: " + response.version());
            System.out.println("Final URI: " + response.uri());

            String contentType = response.headers()
                    .firstValue("Content-Type")
                    .orElse("(not provided)");
            System.out.println("Content-Type: " + contentType);

            if (status >= 200 && status < 300) {
                System.out.println("Response body:");
                System.out.println(response.body());
            } else {
                System.out.println("Request was not successful.");
                System.out.println("Error body:");
                System.out.println(response.body());
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "HTTP request was interrupted", exception);
        } catch (IOException exception) {
            throw new IllegalStateException(
                    "Could not complete HTTP request", exception);
        }
    }
}
~~~

Đổi URI ví dụ thành endpoint của dịch vụ bạn được phép gọi. Điểm cần chú ý:

1. `HttpClient` được tạo trước và có thể tái sử dụng cho nhiều request.
2. `connectTimeout` giới hạn thời gian thiết lập kết nối.
3. `HttpRequest.Builder.timeout` giới hạn thời gian chờ response cho request.
4. `header("Accept", "application/json")` khai báo media type client mong muốn nhận.
5. `BodyHandlers.ofString(StandardCharsets.UTF_8)` chuyển body thành chuỗi bằng charset được chỉ định.
6. `statusCode()` trả status dạng số nguyên; ứng dụng tự quyết định status nào là thành công theo hợp đồng endpoint.
7. `firstValue("Content-Type")` lấy giá trị đầu tiên nếu có; `orElse` cung cấp giá trị thay thế khi header vắng mặt.

Ví dụ dùng UTF-8 vì giả định API trả JSON UTF-8. Nếu endpoint dùng charset khác, hãy xác định charset theo hợp đồng và metadata hợp lệ của response trước khi giải mã. `ofString(UTF_8)` không tự động biến body bất kỳ thành object JSON.

### 4.2. Đọc nhiều giá trị của cùng một header

`HttpHeaders` cung cấp:

- `firstValue(name)`: `Optional<String>` chứa giá trị đầu tiên.
- `allValues(name)`: danh sách tất cả giá trị của header.
- `map()`: map tên header tới danh sách giá trị.

~~~java
HttpHeaders headers = response.headers();

headers.firstValue("Content-Type")
        .ifPresent(value -> System.out.println("Type: " + value));

List<String> cookies = headers.allValues("Set-Cookie");
cookies.forEach(cookie -> System.out.println("Cookie: " + cookie));

headers.map().forEach((name, values) ->
        System.out.println(name + " = " + values));
~~~

Tên header được xử lý không phân biệt chữ hoa/chữ thường. Map và danh sách trong `HttpHeaders` là dữ liệu chỉ đọc theo API; không thể dùng chúng để sửa response đã nhận.

Đặc biệt, `Set-Cookie` có thể có nhiều giá trị và mỗi cookie cần được xử lý theo quy tắc riêng. Không gộp danh sách thành một chuỗi duy nhất bằng dấu phẩy rồi tự parse theo cách chung.

## 5. Đọc response body theo loại dữ liệu

Body có thể là JSON, HTML, văn bản, ảnh, PDF, tệp nén hoặc dữ liệu nhị phân. Chọn body handler phù hợp giúp tránh đọc sai dữ liệu hoặc tiêu thụ bộ nhớ không cần thiết.

| Body handler | Kiểu body | Khi phù hợp |
|---|---|---|
| `BodyHandlers.ofString(charset)` | `String` | JSON, HTML hoặc văn bản có kích thước vừa phải. |
| `BodyHandlers.ofByteArray()` | `byte[]` | Dữ liệu nhị phân nhỏ hoặc cần xử lý bằng thư viện khác. |
| `BodyHandlers.ofFile(path)` | `Path` | Tải nội dung trực tiếp xuống tệp. |
| `BodyHandlers.ofInputStream()` | `InputStream` | Muốn tự đọc theo luồng và kiểm soát việc đóng stream. |
| `BodyHandlers.discarding()` | `Void` | Chỉ cần status/headers, không cần giữ body. |

### 5.1. Body dạng văn bản

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

String body = response.body();
~~~

Chỉ nên dùng cách này khi body có kích thước hợp lý. Một response lớn sẽ được đưa vào bộ nhớ như một chuỗi hoàn chỉnh.

### 5.2. Body dạng byte

~~~java
HttpResponse<byte[]> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofByteArray());

byte[] bytes = response.body();
~~~

Dùng khi nhận ảnh hoặc dữ liệu nhị phân. Không chuyển byte tùy ý thành `String` rồi giả định nội dung là UTF-8; hãy dựa vào media type và định dạng tệp.

### 5.3. Tải trực tiếp xuống tệp

~~~java
Path destination = Path.of("download.bin");

HttpResponse<Path> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofFile(destination));

System.out.println("Saved to: " + response.body());
System.out.println("Status: " + response.statusCode());
~~~

`ofFile` ghi body vào tệp khi response được nhận. Trong ứng dụng thật, hãy kiểm tra status và chính sách lưu trữ trước khi coi tệp là một bản tải thành công; cần chọn đường dẫn tạm và di chuyển sang vị trí chính thức sau khi xác nhận nếu dữ liệu có giá trị.

### 5.4. Body dạng stream

~~~java
HttpResponse<InputStream> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofInputStream());

try (InputStream input = response.body()) {
    byte[] buffer = new byte[8192];
    int bytesRead;
    while ((bytesRead = input.read(buffer)) != -1) {
        // Xử lý từng khối dữ liệu.
    }
}
~~~

Khi dùng `ofInputStream`, ứng dụng phải đóng `InputStream`. Đọc theo luồng hữu ích cho dữ liệu lớn nhưng cần quản lý tài nguyên, timeout và lỗi đọc body cẩn thận. Đừng quên body có thể vẫn là nội dung lỗi của status `4xx` hoặc `5xx`.
## 6. Status code và body phải được đọc cùng nhau

Một lỗi thường gặp là chỉ xem body như thể request luôn thành công. Trên thực tế, nhiều API trả JSON lỗi với status `400`, `401`, `404` hoặc `500`. Body có thể hữu ích để hiển thị thông báo hoặc ghi log có kiểm soát, nhưng status mới cho biết nhóm kết quả HTTP.

Ví dụ xử lý:

~~~java
static void handle(HttpResponse<String> response) {
    int status = response.statusCode();

    if (status >= 200 && status < 300) {
        System.out.println("Success: " + response.body());
    } else if (status >= 300 && status < 400) {
        System.out.println("Redirection");
        response.headers().firstValue("Location")
                .ifPresent(uri -> System.out.println("Location: " + uri));
    } else if (status >= 400 && status < 500) {
        System.out.println("Client-side response: " + status);
        System.out.println("Error details: " + response.body());
    } else if (status >= 500 && status < 600) {
        System.out.println("Server-side response: " + status);
    } else {
        System.out.println("Other HTTP status: " + status);
    }
}
~~~

Đoạn mã là khung phân loại. Trong ứng dụng thật, mỗi endpoint nên xác định các status mong đợi và cách ánh xạ body lỗi sang loại lỗi miền nghiệp vụ.

**Java HttpClient không tự ném IOException chỉ vì status là `404` hoặc `500`.** Khi máy chủ trả về response HTTP hợp lệ, `send` vẫn trả về `HttpResponse`; bạn phải đọc `statusCode()` để biết đó là thành công hay lỗi HTTP. `IOException` thường biểu thị lỗi giao tiếp, kết nối, TLS hoặc đọc/ghi dữ liệu, không phải đơn thuần là status lỗi.

### 6.1. Xử lý `204 No Content`

Không nên gọi JSON parser trên body rỗng:

~~~java
if (response.statusCode() == 204) {
    System.out.println("Operation completed without a response body.");
} else if (response.statusCode() >= 200
        && response.statusCode() < 300) {
    // Parse body theo Content-Type và hợp đồng API.
}
~~~

### 6.2. Xử lý `201 Created`

Khi tạo tài nguyên:

~~~java
if (response.statusCode() == 201) {
    URI createdResource = response.headers()
            .firstValue("Location")
            .map(request.uri()::resolve)
            .orElse(null);

    System.out.println("Created resource: " + createdResource);
}
~~~

Header `Location` có thể là URI tương đối; resolve nó dựa trên URI response/request theo hợp đồng API nếu cần. Không giả định header này luôn có mặt.

### 6.3. Xử lý `429 Too Many Requests`

Khi nhận `429`, xem `Retry-After` nếu máy chủ cung cấp:

~~~java
if (response.statusCode() == 429) {
    response.headers().firstValue("Retry-After")
            .ifPresent(value ->
                    System.out.println("Retry guidance: " + value));
}
~~~

Giá trị `Retry-After` có thể biểu diễn số giây cần chờ hoặc một ngày HTTP. Không nên luôn parse nó thành số nguyên. Khi triển khai retry, hãy tôn trọng giới hạn của máy chủ, dùng backoff có giới hạn và chỉ retry thao tác an toàn hoặc có cơ chế idempotency phù hợp.

## 7. Headers liên quan đến cache và điều kiện request

HTTP hỗ trợ cache để tránh tải lại representation không thay đổi. Hai validator thường gặp là `ETag` và `Last-Modified`.

### 7.1. `ETag` và `If-None-Match`

Máy chủ có thể trả:

~~~text
HTTP/1.1 200 OK
ETag: "order-v42"
Content-Type: application/json
~~~

Ở request sau, client gửi:

~~~text
If-None-Match: "order-v42"
~~~

Nếu representation vẫn không đổi, máy chủ có thể trả `304 Not Modified`. Client dùng bản representation đã cache thay vì tải lại body.

Trong Java:

~~~java
HttpRequest cachedRequest = HttpRequest.newBuilder(uri)
        .header("If-None-Match", "\"order-v42\"")
        .GET()
        .build();

HttpResponse<String> response = client.send(
        cachedRequest,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

if (response.statusCode() == 304) {
    System.out.println("Use the cached representation.");
} else if (response.statusCode() == 200) {
    // Cập nhật cache bằng body và ETag mới.
}
~~~

Đây là ví dụ minh họa luồng validator; ứng dụng thực tế phải lưu representation và ETag từ cùng một cache entry, đồng thời tuân thủ `Cache-Control`, `Vary` và chính sách cache của tài nguyên.

### 7.2. `Last-Modified` và `If-Modified-Since`

`Last-Modified` cho biết thời điểm representation được sửa lần cuối. Client có thể gửi `If-Modified-Since` trong lần request tiếp theo. Máy chủ có thể trả `304` nếu không có thay đổi kể từ thời điểm đó.

ETag thường là validator mạnh hơn cho việc xác định phiên bản representation, còn Last-Modified có độ phân giải và ngữ nghĩa thời gian phụ thuộc máy chủ. Không nên tự kết luận hai validator luôn tương đương.

### 7.3. `Cache-Control` và `Vary`

- `Cache-Control: no-store` yêu cầu không lưu response vào cache theo chính sách tương ứng.
- `Cache-Control: max-age=60` cho biết freshness lifetime trong 60 giây theo ngữ nghĩa HTTP.
- `Vary: Accept-Language` cho biết representation có thể thay đổi theo request header `Accept-Language`; cache cần phân biệt các biến thể.

Client không nên tự cache mọi response chỉ vì có `200`. Cần tuân thủ chỉ thị cache, quyền riêng tư và chính sách dữ liệu của API.

## 8. Redirect, timeout và phiên bản HTTP trong HttpClient

### 8.1. Cấu hình redirect

`HttpClient` hỗ trợ:

| Chính sách | Hành vi |
|---|---|
| `Redirect.NEVER` | Không tự động theo redirect. |
| `Redirect.NORMAL` | Theo redirect thông thường, không theo chuyển hướng HTTPS xuống HTTP. |
| `Redirect.ALWAYS` | Theo mọi redirect theo chính sách client. |

Ví dụ:

~~~java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
~~~

Mặc định là không tự động theo redirect. Chọn chính sách theo yêu cầu bảo mật và endpoint. Khi redirect xảy ra, `response.uri()` cho URI cuối cùng; `previousResponse()` có thể cho response trước đó nếu có.

Redirect có thể thay đổi cách xử lý request tùy status và phương thức. Đặc biệt, `307` và `308` yêu cầu giữ nguyên phương thức; các status `301`/`302` có lịch sử xử lý khác nhau giữa client. Với request có body hoặc chứa thông tin xác thực, hãy xem xét kỹ redirect trước khi bật tự động.

### 8.2. Timeout kết nối và timeout request

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(4))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(12))
        .GET()
        .build();
~~~

- `connectTimeout` giới hạn thời gian thiết lập kết nối.
- `HttpRequest.timeout` giới hạn thời gian chờ response cho request.
- Timeout có thể phát sinh `HttpTimeoutException`, là một loại `IOException`.

Timeout không phải status code HTTP. Nếu request timeout trước khi client nhận response, có thể không có status hoặc headers để đọc.

### 8.3. Chọn phiên bản HTTP

`HttpClient.Builder.version` cho phép đặt phiên bản ưu tiên:

~~~java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
~~~

Client có thể thương lượng hoặc dùng phiên bản khác tùy server và môi trường. Sau khi nhận response, xem `response.version()` để biết phiên bản thực tế. Không nên giả định yêu cầu HTTP/2 luôn được đáp ứng.

## 9. POST JSON và đọc status/header/body

Khi gửi body, header `Content-Type` mô tả định dạng body request. Ví dụ sau gửi JSON UTF-8:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class CreateOrderRequest {
    private CreateOrderRequest() {
    }

    public static void main(String[] args) throws Exception {
        String json = """
                {
                  "customerId": "CUST-01",
                  "itemCode": "BOOK-17",
                  "quantity": 2
                }
                """;

        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/api/orders"))
                .timeout(Duration.ofSeconds(15))
                .header("Accept", "application/json")
                .header("Content-Type", "application/json; charset=UTF-8")
                .POST(HttpRequest.BodyPublishers.ofString(
                        json, StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

        System.out.println("Status: " + response.statusCode());
        response.headers().firstValue("Location")
                .ifPresent(value -> System.out.println("Location: " + value));

        if (response.statusCode() == 201) {
            System.out.println("Order created:");
            System.out.println(response.body());
        } else {
            System.out.println("API response:");
            System.out.println(response.body());
        }
    }
}
~~~

Endpoint trên chỉ là URI minh họa; hãy thay bằng API và payload theo hợp đồng dịch vụ thực tế. Ví dụ cho thấy request body và response body là hai chiều khác nhau:

- `BodyPublishers.ofString` tạo request body từ chuỗi.
- Header `Content-Type` mô tả body được gửi.
- `BodyHandlers.ofString` quyết định cách đọc response body.
- `Accept` thể hiện kiểu response client mong muốn.
- `statusCode()` và `headers()` vẫn phải được đọc riêng để quyết định kết quả.

Không ghép dữ liệu không tin cậy vào JSON bằng `String.formatted()` hoặc nối chuỗi nếu chưa escape đúng JSON. Trong ứng dụng thực tế, dùng JSON serializer để tạo request body.

## 10. Lỗi HTTP và lỗi giao tiếp là hai loại khác nhau

Khi gọi `client.send(request, handler)`, có thể gặp hai nhóm vấn đề:

| Nhóm | Ví dụ | Có `HttpResponse` không? |
|---|---|---|
| HTTP response hợp lệ nhưng status là lỗi | `400`, `401`, `404`, `429`, `500` | **Có.** Đọc status, headers và body lỗi. |
| Lỗi giao tiếp/transport | DNS, kết nối bị từ chối, TLS handshake, timeout, lỗi đọc body | Có thể **không có response hoàn chỉnh**; thường nhận exception. |
| Request bị interrupt | Thread bị ngắt khi đang chờ response | Ném `InterruptedException`; nên khôi phục cờ interrupt khi xử lý. |

Ví dụ:

~~~java
try {
    HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

    if (response.statusCode() >= 400) {
        // Đây vẫn là một HTTP response.
        System.err.println("HTTP error: " + response.statusCode());
        System.err.println(response.body());
    }
} catch (HttpTimeoutException exception) {
    System.err.println("Request timed out: " + exception.getMessage());
} catch (IOException exception) {
    System.err.println("Transport or body I/O error: "
            + exception.getMessage());
} catch (InterruptedException exception) {
    Thread.currentThread().interrupt();
    System.err.println("Request interrupted");
}
~~~

Không nên bắt mọi exception rồi trả về status giả như `500`. Khi không nhận được response, ứng dụng không biết máy chủ đã xử lý request tới đâu. Hãy biểu diễn lỗi giao tiếp riêng với lỗi HTTP và giữ thông tin nguyên nhân phục vụ retry/quan sát.

## 11. Bảo mật và độ tin cậy khi đọc response

### 11.1. Không tin cậy body chỉ vì status là `200`

Response có thể chứa dữ liệu sai định dạng, quá lớn, thiếu trường hoặc không đúng hợp đồng API. Hãy:

- Kiểm tra `Content-Type` trước khi parse theo một định dạng cụ thể.
- Xác thực cấu trúc và giá trị sau khi deserialize.
- Đặt giới hạn kích thước body phù hợp với ứng dụng.
- Xử lý dữ liệu không đầy đủ hoặc sai định dạng.
- Không hiển thị trực tiếp HTML hoặc nội dung không tin cậy trong giao diện mà bỏ qua escaping.

`Content-Length` có thể vắng mặt hoặc không phải cách duy nhất để biết kích thước body; không dùng nó làm biện pháp duy nhất để chống response quá lớn.

### 11.2. Không ghi log thông tin bí mật trong headers

Các header như `Authorization`, `Cookie` và `Set-Cookie` có thể chứa token hoặc thông tin phiên. Không ghi toàn bộ header map vào log ở môi trường production nếu chưa lọc dữ liệu nhạy cảm.

Tương tự, response body lỗi có thể chứa dữ liệu cá nhân, thông tin nội bộ hoặc chi tiết hệ thống. Hãy giới hạn nội dung log, che thông tin nhạy cảm và tránh phản chiếu thông báo lỗi thô cho người dùng cuối.

### 11.3. Xử lý redirect cẩn thận

Redirect sang host khác có thể làm thay đổi ranh giới tin cậy. Không chuyển tiếp credential hoặc header nhạy cảm một cách tùy tiện. Hãy giới hạn host đích, yêu cầu HTTPS khi phù hợp và kiểm tra chính sách của HttpClient.

### 11.4. Retry có điều kiện

Không phải request nào cũng nên retry:

- GET thường an toàn hơn để thử lại vì được thiết kế không làm thay đổi trạng thái máy chủ.
- PUT và DELETE có ngữ nghĩa idempotent theo HTTP, nhưng ứng dụng vẫn cần xét cách endpoint triển khai.
- POST thường không idempotent; retry có thể tạo nhiều tài nguyên nếu lần đầu đã được xử lý nhưng response bị mất.
- Với `429` hoặc `503`, xem `Retry-After`, dùng backoff có giới hạn và tránh tạo thêm tải khi dịch vụ đang quá tải.

Khi API hỗ trợ idempotency key, hãy dùng cùng key cho các lần retry của cùng một thao tác logic theo đúng hợp đồng dịch vụ.

## 12. Bài tập thực hành

### Bài tập 1 — Phân loại status

Cho các mã `200`, `201`, `202`, `204`, `301`, `304`, `400`, `401`, `403`, `404`, `409`, `429`, `500` và `503`. Hãy xếp chúng vào nhóm status và mô tả ứng dụng cần đọc header/body nào.

### Bài tập 2 — Đọc headers nhiều giá trị

Tạo request tới một endpoint thử nghiệm có thể trả nhiều header `Set-Cookie`. Dùng `allValues("Set-Cookie")` để in số lượng và từng giá trị. Đảm bảo không ghi token cookie thật vào log dùng chung.

### Bài tập 3 — Xử lý response không có body

Viết phương thức xử lý kết quả DELETE. Khi status là `204`, trả thông báo thành công mà không gọi JSON parser. Với status lỗi, ghi nhận status và body lỗi nếu có.

### Bài tập 4 — Validator cache

Giả lập một response `200` có `ETag`. Gửi request tiếp theo với `If-None-Match`. Mô tả cách xử lý `304` và lý do không parse body của response này như JSON mới.

### Bài tập 5 — Phân biệt lỗi transport

Gọi một URI không thể kết nối hoặc đặt timeout rất ngắn. Bắt `IOException`/`HttpTimeoutException` và so sánh với trường hợp máy chủ trả `404`. Giải thích tại sao `404` vẫn có `HttpResponse`.

### Bài tập 6 — Đọc Content-Type

Nhận một response có header `Content-Type`. In media type và charset nếu có. Thử với `application/json; charset=UTF-8` và một response không khai báo charset. Nêu cách chọn decoder theo hợp đồng API.

## 13. Quy trình đọc một response trong ứng dụng

Một quy trình xử lý có thể áp dụng cho nhiều endpoint:

1. Gửi request với `Accept` và `Content-Type` đúng mục đích.
2. Đặt timeout kết nối và timeout request phù hợp với SLA.
3. Nhận `HttpResponse` bằng body handler đúng loại dữ liệu.
4. Đọc `statusCode()` trước khi giả định body có dạng thành công.
5. Đọc các header liên quan: `Content-Type`, `Location`, `Retry-After`, `ETag` hoặc header nghiệp vụ đã thỏa thuận.
6. Phân biệt status thành công, chuyển hướng, lỗi client và lỗi server.
7. Chỉ parse body theo media type và hợp đồng của endpoint; xử lý riêng status không có body.
8. Tách lỗi HTTP khỏi lỗi transport và interruption.
9. Chỉ retry khi phương thức, idempotency và hướng dẫn của máy chủ cho phép.
10. Lọc dữ liệu nhạy cảm trước khi ghi log.

## 14. Các nguyên tắc cần ghi nhớ

- Response HTTP có status code, headers và có thể có body.
- Nhóm `2xx` biểu thị thành công, nhưng `200` không phải status thành công duy nhất; `201`, `202`, `204` và `206` có ngữ nghĩa riêng.
- `4xx` thường chỉ vấn đề phía request/quyền/trạng thái tài nguyên; `5xx` thường chỉ lỗi máy chủ hoặc gateway.
- `Accept` mô tả loại response client muốn nhận; `Content-Type` mô tả loại body của thông điệp hiện tại.
- Header name không phân biệt chữ hoa/chữ thường; một header có thể có nhiều giá trị.
- `HttpResponse.statusCode()` trả số status; `headers()` cho phép đọc metadata; `body()` có kiểu tùy body handler.
- `4xx`/`5xx` không tự động làm `HttpClient.send` ném exception. Đây vẫn là response hợp lệ.
- `IOException`/`HttpTimeoutException` và `InterruptedException` là các tình huống giao tiếp/thực thi khác với HTTP status.
- Chính sách redirect mặc định của HttpClient là không tự động theo; hãy cấu hình có chủ đích.
- `204` và `304` không cung cấp body representation mới để parse như JSON.
- Text/body không đáng tin cậy; cần giới hạn kích thước, xác thực dữ liệu và bảo vệ thông tin nhạy cảm.
- Retry phải xét idempotency và `Retry-After`; không retry mù quáng POST hoặc thao tác ghi.

### Tài liệu tham khảo

- [Java SE 17 API — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html).
- [Java SE 17 API — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html).
- [Java SE 17 API — HttpHeaders](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpHeaders.html).
- [Java SE 17 API — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html).
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110).
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111).
