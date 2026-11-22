# Lựa chọn HTTP version theo client hoặc request trong Java 11+

## 1. HTTP version là gì và tại sao phải chọn?

Khi một ứng dụng Java gọi API qua HTTP, giao thức truyền tải có thể là **HTTP/1.1** hoặc **HTTP/2**. Hai phiên bản cùng biểu diễn các khái niệm request/response quen thuộc như method, URI, headers và body, nhưng cách trao đổi trên kết nối khác nhau. HTTP/2 hỗ trợ multiplexing nhiều luồng trên cùng kết nối và nén header; HTTP/1.1 thường được dùng rộng rãi bởi máy chủ hoặc hạ tầng trung gian chưa hỗ trợ HTTP/2.

Từ **Java 11**, API chuẩn `java.net.http` cho phép cấu hình **phiên bản HTTP ưu tiên** theo hai cấp:

1. **Mức client:** `HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1)` hoặc `HTTP_2`. Đây là cấu hình mặc định cho những request sử dụng client ấy.
2. **Mức request:** `HttpRequest.newBuilder(uri).version(HttpClient.Version.HTTP_2)`. Đây là yêu cầu ưu tiên riêng của một request và được ưu tiên hơn cấu hình mặc định của client khi xác định phiên bản *được yêu cầu*.

Điểm phải nhớ: **ưu tiên không đồng nghĩa bảo đảm**. Phiên bản HTTP thực tế phụ thuộc khả năng máy chủ, thương lượng kết nối TLS/ALPN hoặc upgrade, proxy và các ràng buộc triển khai. Sau khi gửi request, kiểm tra **`response.version()`** để biết phiên bản đã được dùng cho phản hồi.

Bài này tập trung vào API Java 11 vẫn có giá trị hiện nay. Ở Java 11, enum `HttpClient.Version` hỗ trợ `HTTP_1_1` và `HTTP_2`. Trên JDK mới hơn, danh sách phiên bản có thể được mở rộng; ví dụ **HTTP/3 được bổ sung vào API JDK 26**, nhưng hằng `HTTP_3` **không có trên Java 11/17/21**. Không dùng hằng này trong mã muốn biên dịch trên Java 11.

## 2. Ba chỗ thường gặp từ khóa `version()`

| API | Kiểu trả về | Ý nghĩa chính xác |
| --- | --- | --- |
| `HttpClient.Builder.version(HttpClient.Version)` | `HttpClient.Builder` | Chọn phiên bản HTTP **ưu tiên mặc định** cho client đang tạo. |
| `HttpClient.version()` | `HttpClient.Version` | Đọc **mức ưu tiên đã cấu hình** của client; không phải bằng chứng kết nối thực tế đã dùng phiên bản này. |
| `HttpRequest.Builder.version(HttpClient.Version)` | `HttpRequest.Builder` | Đặt **mức ưu tiên riêng** cho request. |
| `HttpRequest.version()` | `Optional<HttpClient.Version>` | Đọc mức ưu tiên **đặt trực tiếp trên request**, hoặc `Optional.empty()` nếu không đặt. |
| `HttpResponse.version()` | `HttpClient.Version` | Đọc phiên bản HTTP **thực tế** của phản hồi sau khi request được gửi. |

Tên giống nhau nhưng ý nghĩa khác nhau: `client.version()` phản ánh cấu hình **ưu tiên**, `request.version()` phản ánh **override nếu có**, còn `response.version()` phản ánh **kết quả đã xảy ra**.

`HttpRequest.version()` là `Optional` vì request có thể hoàn toàn không gọi `builder.version(...)`. Khi đó, request kế thừa mức ưu tiên của client **tại thời điểm gửi**; không phải Java tự điền phiên bản của client vào đối tượng `HttpRequest` khi gọi `build()`.

## 3. Thứ tự ưu tiên giữa client và request

Giả sử ứng dụng có hai client:

```java
HttpClient h1Client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_1_1)
        .build();

HttpClient h2Client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
```

Các request có thể được tạo theo ba kiểu:

```java
HttpRequest inherited = HttpRequest.newBuilder(uri).GET().build();

HttpRequest requestH2 = HttpRequest.newBuilder(uri)
        .version(HttpClient.Version.HTTP_2)
        .GET()
        .build();

HttpRequest requestH1 = HttpRequest.newBuilder(uri)
        .version(HttpClient.Version.HTTP_1_1)
        .GET()
        .build();
```

Đây là **đoạn minh họa** trong phạm vi có các import và biến `uri` phù hợp, không phải chương trình Java độc lập.

Quy tắc lựa chọn **phiên bản được yêu cầu**:

| Client dùng để gửi | Request | Mức ưu tiên hiệu lực |
| --- | --- | --- |
| `h1Client` (ưu tiên `HTTP_1_1`) | `inherited` (không override) | `HTTP_1_1` từ client |
| `h1Client` (ưu tiên `HTTP_1_1`) | `requestH2` (override `HTTP_2`) | `HTTP_2` từ request |
| `h2Client` (ưu tiên `HTTP_2`) | `inherited` (không override) | `HTTP_2` từ client |
| `h2Client` (ưu tiên `HTTP_2`) | `requestH1` (override `HTTP_1_1`) | `HTTP_1_1` từ request |

Với request `r` và client `c`, có thể diễn tả mức ưu tiên hiệu lực bằng:

```java
HttpClient.Version preferred = r.version().orElse(c.version());
```

Biểu thức này **chỉ tính mức ưu tiên cấu hình**; nó không hỏi server và không phải kết quả thương lượng mạng. Một phép gán như `HTTP_2` có thể dẫn đến phản hồi thực tế dùng `HTTP_1_1` nếu môi trường không thiết lập được HTTP/2.

## 4. Ví dụ Java hoàn chỉnh, chạy được mà không cần Internet

Tạo tệp **`HttpVersionPreferenceDemo.java`**:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpClient.Version;

public class HttpVersionPreferenceDemo {
    public static void main(String[] args) {
        URI endpoint = URI.create("https://example.com/api/items");

        HttpClient h1Client = HttpClient.newBuilder()
                .version(Version.HTTP_1_1)
                .build();

        HttpClient h2Client = HttpClient.newBuilder()
                .version(Version.HTTP_2)
                .build();

        HttpClient defaultClient = HttpClient.newHttpClient();

        HttpRequest inherited = HttpRequest.newBuilder(endpoint)
                .GET()
                .build();

        HttpRequest forceH2Preference = HttpRequest.newBuilder(endpoint)
                .version(Version.HTTP_2)
                .GET()
                .build();

        HttpRequest forceH1Preference = HttpRequest.newBuilder(endpoint)
                .version(Version.HTTP_1_1)
                .GET()
                .build();

        System.out.println("h1Client=" + h1Client.version());
        System.out.println("h2Client=" + h2Client.version());
        System.out.println("defaultClient=" + defaultClient.version());

        System.out.println("inherited.request.version=" +
                inherited.version().map(Version::name).orElse("empty"));
        System.out.println("inherited.withH1=" +
                effectivePreference(h1Client, inherited));
        System.out.println("inherited.withH2=" +
                effectivePreference(h2Client, inherited));

        System.out.println("overrideH2.request.version=" +
                forceH2Preference.version().orElseThrow());
        System.out.println("overrideH2.withH1Client=" +
                effectivePreference(h1Client, forceH2Preference));

        System.out.println("overrideH1.withH2Client=" +
                effectivePreference(h2Client, forceH1Preference));

        System.out.println("request.method=" + inherited.method());
        System.out.println("request.path=" + inherited.uri().getPath());
    }

    private static Version effectivePreference(
            HttpClient client, HttpRequest request) {
        return request.version().orElse(client.version());
    }
}
```

Biên dịch và chạy bằng **JDK 17+** (mã cũng tương thích Java 11):

```bash
javac HttpVersionPreferenceDemo.java
java HttpVersionPreferenceDemo
```

**Stdout chính xác:**

```text
h1Client=HTTP_1_1
h2Client=HTTP_2
defaultClient=HTTP_2
inherited.request.version=empty
inherited.withH1=HTTP_1_1
inherited.withH2=HTTP_2
overrideH2.request.version=HTTP_2
overrideH2.withH1Client=HTTP_2
overrideH1.withH2Client=HTTP_1_1
request.method=GET
request.path=/api/items
```

Giải thích kết quả:

1. `h1Client.version()` trả `HTTP_1_1`, `h2Client.version()` trả `HTTP_2`. `HttpClient.newHttpClient()` trên Java 11 trở lên có mức ưu tiên mặc định **HTTP/2**, nên `defaultClient.version()` trả `HTTP_2`.
2. `inherited.version()` là `Optional.empty()` bởi builder không gọi `version(...)`. Giá trị `empty` trong chương trình chỉ là chuỗi hiển thị thay cho `Optional.empty()`.
3. Cùng đối tượng `inherited` có mức ưu tiên hiệu lực khác nhau khi được gửi bởi hai client khác nhau; **request không tự khóa phiên bản** khi builder không đặt override.
4. Với `forceH2Preference`, request ghi đè mức ưu tiên `HTTP_1_1` của `h1Client` thành `HTTP_2`.
5. Với `forceH1Preference`, request ghi đè mức ưu tiên `HTTP_2` của `h2Client` thành `HTTP_1_1`.
6. Chương trình **không gọi `send` hoặc `sendAsync`**, nên không có kết nối mạng; các dòng trên chỉ nói về cấu hình, không chứng minh giao thức thực tế được sử dụng.

`effectivePreference` là phương thức tự viết trong ví dụ để mô tả quy tắc kế thừa/override, **không phải** API sẵn có của JDK. Không đồng nhất kết quả của hàm này với `HttpResponse.version()`.

## 5. Phiên bản HTTP thực tế: kiểm tra `HttpResponse.version()`

Khi thật sự gửi request, Java HTTP client có thể thương lượng được phiên bản ưu tiên hoặc sử dụng phiên bản khác tùy điều kiện. Vì vậy, sau khi có `HttpResponse`, hãy đọc:

```java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString());

System.out.println("requested=" +
        request.version().orElse(client.version()));
System.out.println("actual=" + response.version());
System.out.println("status=" + response.statusCode());
```

Đây là **đoạn mã minh họa**, cần import `java.net.http.HttpResponse`; các biến `client`, `request` được tạo từ trước, và phương thức chứa đoạn này phải xử lý hoặc khai báo `IOException` và `InterruptedException`. Nếu được chạy, đoạn mã **thật sự gửi HTTP request**; không có stdout cố định vì kết quả phụ thuộc endpoint và mạng.

Đối với việc quan sát một endpoint thật, có thể dùng một chương trình độc lập như sau (thay địa chỉ bằng API HTTPS bạn kiểm soát):

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class HttpVersionNetworkCheck {
    public static void main(String[] args)
            throws IOException, InterruptedException {
        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.com/"))
                .GET()
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

        System.out.println("preferred=" +
                request.version().orElse(client.version()));
        System.out.println("actual=" + response.version());
        System.out.println("status=" + response.statusCode());
    }
}
```

Nếu lưu riêng đoạn chương trình này thành **`HttpVersionNetworkCheck.java`**, lệnh biên dịch/chạy là:

```bash
javac HttpVersionNetworkCheck.java
java HttpVersionNetworkCheck
```

**Không có stdout chính xác cố định cho chương trình có mạng**. Nó có thể in `actual=HTTP_2`, `actual=HTTP_1_1` hoặc gặp lỗi kết nối/TLS/tên miền. Cả ba khả năng cần được phân biệt với chương trình minh họa cấu hình ở mục trước. `statusCode()` là mã HTTP (ví dụ `200`), **không** cho biết phiên bản giao thức. `HttpResponse.version()` mới là nơi đọc phiên bản được dùng.

Nếu sử dụng redirect hoặc authentication, kết quả trả về có thể gắn với request cuối cùng sau quá trình chuyển hướng. Khi điều tra, kiểm tra thêm `response.uri()`, `response.request()` và (khi có) `previousResponse()` để hiểu đường đi.

## 6. Tại sao yêu cầu HTTP/2 có thể nhận phản hồi HTTP/1.1?

`HttpClient.Version.HTTP_2` thể hiện **mong muốn sử dụng HTTP/2 khi có thể**, không phải chỉ thị bắt buộc “phải HTTP/2 hoặc thất bại”.

Những nguyên nhân phổ biến:

- **Server không hỗ trợ HTTP/2**, hoặc chỉ bật HTTP/1.1 trên endpoint được gọi.
- **Kết nối HTTPS/TLS:** HTTP/2 thông thường được thương lượng qua **ALPN** trong quá trình bắt tay TLS. Nếu không chọn được HTTP/2, giao tiếp có thể sử dụng HTTP/1.1.
- **Kết nối HTTP không mã hóa:** để dùng HTTP/2 trên kết nối cleartext, có thể cần cơ chế upgrade từ HTTP/1.1 (h2c); hỗ trợ thực tế phụ thuộc client và server. Không được mặc định mọi URI `http://` sẽ chuyển lên HTTP/2.
- **Proxy/gateway:** một proxy hoặc cấu hình mạng có thể khiến HTTP/2 không khả dụng, từ đó yêu cầu dùng HTTP/1.1.
- **Kết nối đang dùng và ràng buộc triển khai:** việc chọn protocol và tái sử dụng kết nối có thể phụ thuộc trạng thái client và máy chủ.

Cần quan sát `HttpResponse.version()` thay vì kết luận dựa trên `client.version()`. Nếu nghiệp vụ **bắt buộc** HTTP/2, có thể kiểm tra kết quả và từ chối khi giao thức thực tế khác; tuy nhiên việc phát hiện này xảy ra **sau** khi quá trình gửi đã diễn ra, nên không coi nó là cách ngăn request tới server. Nếu cần hợp đồng cứng chỉ HTTP/2, phải xem xét hỗ trợ và cấu hình ở cả client, proxy và server.

## 7. Nên chọn ở client hay từng request?

**Đặt ở client** khi đa số request có cùng nhu cầu về giao thức:

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
```

Một `HttpClient` thường được **tái sử dụng** cho nhiều request nhằm tận dụng tài nguyên và kết nối. Chọn tại client giúp tránh lặp cấu hình trên tất cả request. Khi không có yêu cầu đặc biệt, mức ưu tiên mặc định HTTP/2 thường hợp lý; không nhất thiết tự đặt lại giá trị vốn đã là mặc định.

**Đặt ở request** khi một endpoint hoặc một nhóm request có yêu cầu tương thích khác với phần còn lại:

```java
HttpRequest legacyEndpointRequest = HttpRequest.newBuilder(
        URI.create("https://api.example.com/compatibility"))
        .version(HttpClient.Version.HTTP_1_1)
        .GET()
        .build();
```

Đây là đoạn minh họa xây request, **không** tự gọi mạng. Dùng override khi biết hạ tầng đích yêu cầu HTTP/1.1 hoặc đang điều tra lỗi tương thích. Nếu nhiều request đều phải dùng HTTP/1.1 và cấu hình đi kèm cũng khác, có thể cân nhắc một client riêng với cấu hình phù hợp. Nhưng **không bắt buộc tạo một client mới chỉ để đổi version một request**.

Các kiểu lựa chọn này **không sửa được một request đã xây**; `HttpRequest` được build là immutable. Nếu muốn thay version của một request, tạo request khác với builder cấu hình phù hợp.

## 8. Những giới hạn quan trọng của API Java 11

### 8.1. Enum version có những giá trị nào?

Đối với mã cần biên dịch trên Java 11, hai giá trị `HttpClient.Version` liên quan là:

```java
HttpClient.Version.HTTP_1_1
HttpClient.Version.HTTP_2
```

Đừng viết một chuỗi tùy ý như `"HTTP/2"` để truyền vào `builder.version(...)`; phương thức yêu cầu **enum** `HttpClient.Version`, không nhận `String`. `HTTP_1_1` có dấu gạch dưới theo tên enum, còn cách viết chuẩn giao thức là “HTTP/1.1”.

**Cập nhật liên quan JDK hiện đại:** Trên JDK 26, enum có thêm `HTTP_3`, nhưng tính năng đó phụ thuộc phiên bản JDK và khả năng hỗ trợ kết nối. Nếu bài tập hay hệ thống đặt mục tiêu chạy trên **Java 11 hoặc Java 17**, không dùng `HTTP_3` trong mã nguồn vì nó không biên dịch được tại các mức API đó. Phần chọn client/request và kiểm tra response vẫn là nguyên tắc đúng.

### 8.2. Cấu hình request không phải HTTP header

Đoạn sau **không phải cách đổi HTTP version**:

```java
.header("X-HTTP-Version", "2")
```

Đây chỉ là một custom header. Nó không quyết định protocol mà HTTP client dùng khi kết nối. Một số header liên quan framing hoặc upgrade có thể bị implementation hạn chế; không tự thêm `Connection`, `Upgrade`, `HTTP2-Settings` để “ép” HTTP/2 nếu API đã cung cấp `version(...)`. Để chọn ưu tiên, dùng builder API; để biết thực tế, đọc response.

### 8.3. Đừng nhầm `HttpClient.version()` với `HttpResponse.version()`

Ví dụ logic:

```text
Client preference: HTTP_2
Request preference: (not set)
Response protocol: HTTP_1_1
```

Trường hợp này **có thể xảy ra**: client ưu tiên HTTP/2 nhưng trao đổi thực tế dùng HTTP/1.1 vì điều kiện kết nối. Nếu request đã gọi `version(HTTP_1_1)`, client vẫn có thể báo `client.version()==HTTP_2`; giá trị trong client không tự thay đổi theo từng request.

### 8.4. Không có cú pháp “cố định version” bằng `send()`

`HttpClient.send(...)` nhận `HttpRequest` và `BodyHandler`, không có tham số phiên bản giao thức. Thời điểm lựa chọn ưu tiên là khi tạo client/request. Việc **thương lượng protocol** được thực hiện khi trao đổi qua mạng.

Timeout của client/request (ví dụ `connectTimeout(Duration)` và `HttpRequest.Builder.timeout(Duration)`) là cấu hình về thời gian, không phải cơ chế chọn HTTP version. Không nên suy luận rằng timeout báo lỗi là do version không tương thích nếu chưa có quan sát mạng và lỗi cụ thể.

## 9. Các lỗi thường gặp và cách sửa

| Lỗi hoặc hiểu lầm | Giải thích và cách xử lý |
| --- | --- |
| Thấy `client.version()==HTTP_2` nên khẳng định kết nối là HTTP/2 | Giá trị đó là **ưu tiên cấu hình**. Sau khi gửi, đọc `response.version()`. |
| Thấy `request.version().isEmpty()` rồi tưởng request sai | `Optional.empty()` là bình thường: request **kế thừa ưu tiên của client**. |
| Nghĩ request luôn tuân theo version của client dù có override | `request.version(Version)` đặt mức ưu tiên riêng, được chọn trước client default khi xác định ưu tiên. |
| Chọn `HTTP_2` nhưng thực tế thấy `HTTP_1_1` | Có thể do server, TLS/ALPN, proxy hoặc hỗ trợ triển khai. Kiểm tra khả năng endpoint và `response.version()`. |
| Dùng `HTTP_3` khi biên dịch Java 11 | Enum Java 11 chưa có giá trị đó. Dùng `HTTP_1_1`/`HTTP_2` hoặc đổi yêu cầu phiên bản JDK theo dự án. |
| Tưởng `HttpRequest.Builder.version(...)` gửi request | Builder chỉ cấu hình và tạo request. `HttpClient.send`/`sendAsync` mới gửi. |
| Thêm một header “HTTP-Version” để ép protocol | Header ứng dụng không thay việc chọn giao thức kết nối. Dùng `version(...)` đúng cấp. |
| Tạo mới một `HttpClient` ở mọi lời gọi API | Thường lãng phí việc tái sử dụng kết nối/tài nguyên. Tái sử dụng client phù hợp và override ở request khi cần. |
| Tự cho rằng server hỗ trợ HTTP/2 vì URL bắt đầu bằng `https://` | HTTPS không tự bảo đảm HTTP/2. Cần thương lượng thành công. |

## 10. Bài tập tự kiểm tra

**Câu 1:** Client được tạo với `HTTP_1_1`; request được tạo với `HTTP_2`. Phiên bản nào được **ưu tiên**?

**Đáp án:** `HTTP_2`, do request override ưu tiên của client. Kết quả **thực tế** vẫn phải đọc từ `HttpResponse.version()`.

**Câu 2:** `HttpRequest.newBuilder(uri).GET().build().version()` trả gì nếu builder chưa gọi `version(...)`?

**Đáp án:** `Optional.empty()`. Khi gửi, request sử dụng mức ưu tiên của `HttpClient` gửi nó.

**Câu 3:** Một client `HTTP_2` gửi request không có override, nhưng phản hồi dùng HTTP/1.1. Có mâu thuẫn không?

**Đáp án:** Không. HTTP/2 là mức ưu tiên; các ràng buộc máy chủ, kết nối, proxy có thể khiến HTTP/1.1 được dùng.

**Câu 4:** Có thể kiểm tra giao thức **thật** trước khi gửi request chỉ bằng `client.version()` không?

**Đáp án:** Không. Chỉ biết mức ưu tiên. Sau khi nhận phản hồi, dùng `response.version()` để biết giao thức được dùng.

**Câu 5:** Vì sao `request.version()` trả `Optional<HttpClient.Version>` trong khi `client.version()` trả trực tiếp `HttpClient.Version`?

**Đáp án:** Request có thể **không đặt override**, nên `Optional.empty()` biểu thị kế thừa từ client. Client luôn có mức ưu tiên, kể cả khi dùng mặc định.

**Ghi nhớ:** Trong Java 11+, **ưu tiên HTTP version ở request ghi đè ưu tiên client**, nếu request không đặt thì **kế thừa từ client**, và **`HttpResponse.version()` mới cho biết giao thức thực tế**. Java 11 dùng `HTTP_1_1` hoặc `HTTP_2`; không coi cấu hình là cam kết thương lượng thành công.

**Tài liệu API chính thức:** [Java SE 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html); [HttpClient.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html); [HttpRequest.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html); [HttpRequest](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html); [HttpResponse](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html); [Java SE 26 — HttpClient.Version](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Version.html).
