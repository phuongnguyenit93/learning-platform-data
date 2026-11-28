# Header injection

## 1. Khi dữ liệu trở thành cấu trúc của header

Một API xuất báo cáo nhận tên file từ người dùng rồi đưa tên đó vào response header. Một dịch vụ khác nhận metadata từ đối tác rồi chuyển thành header khi gọi upstream. Trong cả hai trường hợp, dữ liệu ứng dụng đã đi tới một ranh giới giao thức.

**Header injection** là lỗi cho phép dữ liệu không đáng tin cậy làm thay đổi header ngoài phạm vi mà ứng dụng dự định: tạo field mới, sửa cấu trúc field hiện có hoặc tác động tới cách thành phần nhận diễn giải thông điệp.

Trong HTTP/1.1, một nguyên nhân điển hình là để ký tự kết thúc dòng đi vào giá trị header mà không được xử lý an toàn. Tuy nhiên, chủ đề này không chỉ là tìm chuỗi `%0d%0a`. Cần kiểm soát tên field, giá trị, tham số con, số lần xuất hiện, quyền đặt header và cách các thành phần chuyển đổi giao thức.

Trong thiết kế yêu cầu bảo mật, mục tiêu là giữ được bất biến:

> Dữ liệu từ client, đối tác hoặc kho lưu trữ không được tạo cấu trúc header hay quyền điều khiển giao thức ngoài contract đã được server cho phép.

Một header hợp lệ về cú pháp cũng không mặc nhiên đáng tin về nguồn gốc. Vì vậy cần phân biệt **an toàn cấu trúc** và **quyền quyết định nội dung header**.

## 2. Cơ chế CR/LF injection trong HTTP/1.1

Hai ký tự thường được nhắc tới:

| Ký tự | Tên | Biểu diễn thường gặp |
|---|---|---|
| CR | Carriage return | `\r`, byte `0x0D`, percent-encoding `%0D` |
| LF | Line feed | `\n`, byte `0x0A`, percent-encoding `%0A` |

Trong biểu diễn HTTP/1.1 dạng dòng, mỗi field được ghi theo cấu trúc tương tự:

~~~text
Field-Name: field-value<CR><LF>
~~~

Dòng trống kết thúc phần header. Nếu một giá trị không đáng tin được ghép trực tiếp vào biểu diễn này, ký tự điều khiển có thể bị hiểu là ranh giới giao thức.

Ví dụ không an toàn trong một bộ ghi HTTP tự viết:

~~~java
writer.write("X-Report-Label: " + requestedLabel + "\r\n");
~~~

Nếu giá trị sau các bước decode của ứng dụng là:

~~~text
monthly<CR><LF>X-Demo: injected
~~~

Một parser dễ bị ảnh hưởng có thể nhìn thấy:

~~~http
X-Report-Label: monthly
X-Demo: injected
~~~

`<CR>` và `<LF>` trong minh họa là ký hiệu mô tả, không phải những ký tự văn bản mà HTTP parser tự động biến thành newline. Mức độ khai thác phụ thuộc thành phần ghi, parser và các lớp trung gian.

RFC 9110 xác định CR, LF và NUL trong field value là không hợp lệ và nguy hiểm; ở phía nhận, RFC cho phép từ chối hoặc thay chúng bằng SP trước khi xử lý tiếp. Với dữ liệu ứng dụng sắp đưa vào header, bài này chọn chính sách **từ chối input không hợp lệ**, thay vì âm thầm sửa giá trị. [RFC 9110, mục 5.5](https://www.rfc-editor.org/rfc/rfc9110.html#section-5.5)

Không được chỉ kiểm tra cặp `\r\n`. Một CR đứng riêng, LF đứng riêng hoặc NUL cũng cần được xét; các parser có thể phản ứng khác nhau với chúng.

### Header injection và response splitting

Thêm được một field ngoài dự định là header injection. Nếu dữ liệu còn làm phá vỡ ranh giới header/body hoặc tạo thông điệp phản hồi khác trong chuỗi xử lý, có thể dẫn tới **HTTP response splitting**.

OWASP mô tả response splitting như tình huống dữ liệu không đáng tin được đưa vào response header và nền tảng bên dưới cho phép ký tự điều khiển gây thay đổi cấu trúc phản hồi. Vì thế, cần kiểm chứng stack thực tế, không suy luận rằng một đoạn code bất cẩn luôn khai thác được trên mọi container. [OWASP HTTP Response Splitting](https://community.owasp.org/attacks/HTTP_Response_Splitting)

Không cần tái hiện việc tạo nhiều response để công nhận một yêu cầu chống header injection. Chỉ việc client tạo được header ngoài phạm vi cho phép đã là vi phạm contract cần xử lý.

## 3. Phân biệt những rủi ro liên quan

| Tình huống | Vấn đề chính | Vì sao cần phân biệt |
|---|---|---|
| CR/LF trong giá trị tạo thêm field | Header injection về cấu trúc | Cần validation và API ghi header đúng |
| Client gửi `X-Internal-Role: admin` | Header giả mạo về độ tin cậy | Không cần newline vẫn có thể nguy hiểm nếu backend tin client |
| Client điều khiển `Host` dùng để tạo link | Host header poisoning hoặc lỗi xây URL | Cần nguồn origin đáng tin, không chỉ lọc CR/LF |
| Redirect tới URL ngoài mong muốn | Open redirect | Một `Location` một dòng vẫn có thể sai chính sách |
| Cookie value tác động thuộc tính cookie | Injection ở grammar của cookie | Cần API/cấu trúc cookie và chính sách thuộc tính |
| Các proxy hiểu framing request khác nhau | Request smuggling | Có liên quan parser và header, nhưng không đồng nhất với phản xạ CR/LF |
| Input tạo dòng log giả | Log injection | Cần xử lý theo định dạng log riêng |
| Dữ liệu đi vào header thư điện tử | Email header injection | MIME/email có grammar và cơ chế folding khác HTTP |

Một yêu cầu bảo mật tốt có thể liên kết các rủi ro này nhưng không dùng một biện pháp để tuyên bố đã giải quyết tất cả.

Ví dụ cấm CR/LF không ngăn client gửi một `X-Tenant-ID` hoàn toàn hợp lệ về cú pháp. Nếu backend dùng nó để quyết định tenant mà không xác minh nguồn, vấn đề vẫn còn.

## 4. Xác định source, sink và owner

Các nguồn có thể gồm query parameter, JSON, path parameter, header đến từ client, file import, cấu hình đối tác và giá trị đã lưu trong database.

Các sink cần kiểm soát:

| Sink | Dữ liệu có thể đi vào | Quyết định cần có |
|---|---|---|
| Response header tùy biến | Request ID, label, metadata | Tên cố định, grammar và độ dài value |
| `Content-Disposition` | Tên file tải xuống | API tham số phù hợp, chính sách filename |
| `Location` | Đích chuyển hướng | Kiểm tra URI và quyền chọn đích |
| `Set-Cookie` | Value và thuộc tính cookie | Value theo grammar; thuộc tính do server quản lý |
| HTTP client gọi upstream | Metadata và credential | Mapping tên header, quyền forwarding và binding đích |
| Gateway/proxy | Header định tuyến hoặc danh tính | Nguồn tin cậy và chính sách overwrite/remove |
| Job nền | Metadata đã lưu từ trước | Kiểm tra tại lúc tạo header, không tin mặc định dữ liệu đã lưu |
| Mail composer | Subject, địa chỉ và tên hiển thị | API email riêng; không ghép raw header |

Mô hình luồng dữ liệu:

~~~mermaid
flowchart LR
    A[Client, đối tác, dữ liệu đã lưu] --> B[Parse và decode theo contract]
    B --> C[Validation theo từng field]
    C --> D[Kiểm tra quyền đặt hoặc forward header]
    D --> E[API header có cấu trúc]
    E --> F[Server hoặc HTTP client]
    F --> G[Proxy và bên nhận cuối]
~~~

Owner cần được chỉ rõ:

- Ứng dụng quyết định field nghiệp vụ nào được dùng làm header.
- HTTP server/client chịu trách nhiệm serialize giao thức và áp dụng kiểm tra thư viện.
- Gateway quản lý các header do hạ tầng sở hữu.
- Nhóm vận hành xác nhận chuỗi proxy, protocol và hạn mức đang triển khai.

Không nên dùng hợp đồng mơ hồ như “framework sẽ lọc” mà không xác định điểm nào từ chối, trường hợp nào bị sửa và hành vi khi lỗi.

## 5. Kiểm tra đúng biểu diễn, đúng thời điểm

Một request có thể mang dữ liệu ở dạng percent-encoded hoặc JSON escape. Chỉ tìm chuỗi ký tự `%0d%0a` trên raw request chưa chứng minh rằng giá trị cuối cùng an toàn.

Ví dụ:

~~~text
Query parameter:
label=monthly%0D%0AX-Demo%3Ainjected

Sau decoder phù hợp của framework:
monthly<CR><LF>X-Demo:injected
~~~

Với JSON:

~~~json
{
  "label": "monthly\r\nX-Demo: injected"
}
~~~

JSON parser tạo CR/LF trong chuỗi kết quả. Dữ liệu cần được kiểm tra trước khi sử dụng tại sink, dù raw JSON chứa các ký tự backslash-escape thay vì CR/LF trực tiếp.

Ngược lại:

~~~json
{
  "label": "%0D%0A"
}
~~~

JSON không tự yêu cầu percent-decoding chuỗi này. Nếu contract coi đây là văn bản literal, không được decode thêm chỉ vì nó trông giống URI encoding. Nếu một trường chỉ cho phép identifier ASCII, ký tự `%` có thể bị từ chối theo grammar mà không cần một decoder mới.

### Double decoding

Một biến thể như `%250D%250A` có thể trở thành `%0D%0A` sau một lần percent-decoding, rồi CR/LF sau lần thứ hai. Yêu cầu phải xác định ai decode lớp nào và cấm việc giải mã lại cùng lớp ngoài contract.

Quy trình nên là:

1. Giới hạn tài nguyên trước khi parse hoặc decode.
2. Parse/decode đúng lớp giao thức đã công bố.
3. Áp dụng grammar của dữ liệu sắp đi vào header.
4. Tạo header bằng API của framework.
5. Không biến đổi value theo cách có thể tạo delimiter sau bước kiểm tra.

Không dùng “decode đến khi không đổi” làm thuật toán chống injection.

### Ký tự khác newline

Một profile identifier ASCII có thể từ chối toàn bộ ký tự điều khiển, whitespace và ký tự ngoài alphabet cho phép. Đây là chính sách ứng dụng chặt hơn grammar HTTP tổng quát.

Không được suy ra mọi ký tự xuống dòng Unicode đều là delimiter HTTP giống CR/LF. Nếu một thư viện có thể chuyển đổi chúng, cần xét bước chuyển đổi đó; nếu không, áp dụng quy tắc của trường thay vì khẳng định mọi biểu diễn Unicode có cùng cơ chế khai thác.

## 6. Ba lớp kiểm soát khi tạo header

### 6.1. Quyền chọn tên field

Không cung cấp một bản đồ request mà client có thể biến trực tiếp thành mọi response header:

~~~java
// Thiếu kiểm soát quyền đặt tên và nội dung header.
for (var entry : requestedHeaders.entrySet()) {
    response.setHeader(entry.getKey(), entry.getValue());
}
~~~

Một API như vậy có thể cho phép sửa header bảo mật, cache hoặc cookie ngay cả khi không có CR/LF.

Nếu nghiệp vụ cần tùy chọn hữu hạn, dùng mapping từ option sang tên field cố định do server sở hữu. So sánh tên HTTP field phải phù hợp tính không phân biệt hoa thường; không để `x-tenant-id` và `X-Tenant-ID` vượt qua hai nhánh policy khác nhau.

### 6.2. Grammar và độ dài value

Mỗi field cần profile riêng. Ví dụ:

| Header minh họa | Profile |
|---|---|
| `X-Correlation-ID` | 1–64 ký tự ASCII chữ/số, dấu chấm, gạch dưới, gạch ngang; ký tự đầu chữ/số |
| `X-Report-Version` | Giá trị do server tạo từ phiên bản có kiểu |
| `Content-Disposition` | Disposition và parameter được dựng theo grammar riêng |
| `Location` | URI-reference phù hợp chính sách redirect |
| `Authorization` gọi đối tác | Credential của workload, không lấy từ client tùy ý |

Một hàm chỉ kiểm tra “không có CR/LF” là lớp nền hữu ích, nhưng không thay thế grammar cho `Location`, cookie hoặc một parameter trong `Content-Disposition`.

Giới hạn cần xét cả value, số field và tổng kích thước header sau serialization. Nếu có Unicode encoding cho parameter, độ dài sau encoding có thể lớn hơn chuỗi đầu vào.

### 6.3. API tạo header

Dùng API header của server hoặc HTTP client thay vì viết raw dòng giao thức vào socket. Nhưng vẫn cần validation nghiệp vụ và kiểm soát tên header.

Không bật hoặc tạo một đường fallback bỏ qua kiểm tra của thư viện khi gặp lỗi. Việc builder từ chối value là tín hiệu để xử lý input hoặc cấu hình, không phải lý do chuyển sang ghi raw bytes.

## 7. Ví dụ Java với correlation ID

Giả sử hệ thống cho phép client cung cấp correlation ID phục vụ truy vết. ID này không dùng để xác thực, phân quyền hay làm khóa idempotency của nghiệp vụ.

Profile minh họa:

- Vắng field: server tạo ID mới.
- Có field: chỉ một giá trị, đúng alphabet và tối đa 64 ký tự.
- Có nhiều giá trị hoặc value không hợp lệ: từ chối theo contract.
- Header trả về có tên cố định.
- Sau khi tạo kiểu hợp lệ, không decode hoặc trim thêm.

~~~java
import java.util.List;
import java.util.Objects;
import java.util.UUID;
import java.util.regex.Pattern;

public record CorrelationId(String value) {
    private static final Pattern ALLOWED =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");

    public CorrelationId {
        if (value == null
                || value.length() > 64
                || !ALLOWED.matcher(value).matches()) {
            throw new IllegalArgumentException("Invalid correlation ID");
        }
    }

    public static CorrelationId fromExternal(List<String> values) {
        Objects.requireNonNull(values, "values");

        if (values.isEmpty()) {
            return new CorrelationId(UUID.randomUUID().toString());
        }

        if (values.size() != 1) {
            throw new IllegalArgumentException(
                    "Multiple correlation IDs are not accepted");
        }

        return new CorrelationId(values.get(0));
    }
}
~~~

Adapter đọc danh sách value từ API header của framework, áp dụng contract rồi chuyển đối tượng hợp lệ vào luồng xử lý.

Ghi response bằng API Servlet, trước khi response được commit:

~~~java
CorrelationId correlationId = CorrelationId.fromExternal(incomingValues);
response.setHeader("X-Correlation-ID", correlationId.value());
~~~

Jakarta Servlet cung cấp các API như `setHeader`, `addHeader` và API cookie. Chọn API phù hợp với semantics của field; cách container kiểm tra và xử lý lỗi vẫn cần được xác minh trên cấu hình triển khai. [Jakarta HttpServletResponse](https://jakarta.ee/specifications/servlet/6.1/apidocs/jakarta.servlet/jakarta/servlet/http/HttpServletResponse.html)

Khi gọi upstream bằng Java HTTP Client:

~~~java
import java.net.URI;
import java.net.http.HttpRequest;

HttpRequest upstreamRequest = HttpRequest.newBuilder()
        .uri(URI.create("https://reports.example.invalid/internal/status"))
        .header("X-Correlation-ID", correlationId.value())
        .GET()
        .build();
~~~

URI trong ví dụ là địa chỉ minh họa. Đích thật phải lấy từ cấu hình hoặc registry có kiểm soát, không phải mặc định tin URL client gửi.

`HttpRequest.Builder` kiểm tra tên/value và có thể hạn chế một số header; `header` thêm giá trị còn `setHeader` thay các giá trị đã đặt cho tên tương ứng. Lớp API này bổ sung bảo vệ giao thức, không thay cho policy forwarding của ứng dụng. [Java HttpRequest.Builder](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)

Nếu proxy trước ứng dụng gộp các value bằng dấu phẩy, profile correlation ID trên sẽ từ chối dấu phẩy. Tuy nhiên, cần kiểm chứng cách mỗi hop đọc header trùng; gọi một API chỉ lấy giá trị đầu có thể che mất thông tin về các giá trị khác.

## 8. Content-Disposition: tên file là parameter, không phải raw header

Chức năng tải báo cáo thường tạo header dạng:

~~~http
Content-Disposition: attachment; filename="report.csv"
~~~

Một tên file do người dùng đặt không chỉ có nguy cơ chứa CR/LF. Dấu nháy, dấu chấm phẩy hoặc cách encode không phù hợp cũng có thể làm thay đổi cách parser hiểu parameter.

Cách nối trực tiếp cần tránh:

~~~java
String contentDisposition =
        "attachment; filename=\"" + requestedFileName + "\"";

response.setHeader("Content-Disposition", contentDisposition);
~~~

Việc container có thể từ chối CR/LF không chứng minh rằng mọi vấn đề về parameter và tên file đã được giải quyết.

### Phương án đơn giản: tên tải xuống do server tạo

Nếu nghiệp vụ không cần tùy ý đặt tên tải xuống, có thể tạo từ ID có kiểu và phần mở rộng cố định:

~~~java
long reportId = authorizedReport.id();
if (reportId <= 0) {
    throw new IllegalStateException("Invalid report metadata");
}

String downloadName = "report-" + reportId + ".csv";

response.setContentType("text/csv; charset=UTF-8");
response.setHeader(
        "Content-Disposition",
        "attachment; filename=\"" + downloadName + "\""
);
~~~

`authorizedReport` trong ví dụ phải là tài nguyên đã được kiểm tra quyền. Số ID dương chỉ giúp bảo đảm grammar của tên được tạo, không tự chứng minh người gọi có quyền tải báo cáo.

### Khi cần tên Unicode

Nếu phải giữ tên tiếng Việt hoặc tên do người dùng cung cấp, yêu cầu cần bao gồm:

- Profile filename: độ dài, ký tự điều khiển bị từ chối, separator/path và các tên không được phép.
- Builder hoặc encoder dành riêng cho parameter header, có phiên bản được hỗ trợ.
- Cách tạo ASCII fallback nếu cần.
- Chính sách dùng `filename*` và charset tương ứng.
- Hành vi với value chứa quote, backslash, semicolon và percent.
- Giới hạn kích thước sau encoding.

Ví dụ biểu diễn theo cơ chế parameter mở rộng:

~~~http
Content-Disposition: attachment; filename="report.csv"; filename*=UTF-8''b%C3%A1o-c%C3%A1o.csv
~~~

RFC 6266 quy định `Content-Disposition` và filename parameter; RFC 8187 mô tả biểu diễn charset/language cho các parameter HTTP phù hợp. Không dùng HTML escaping hoặc form URL-encoding như một cách thay thế tổng quát cho grammar này. [RFC 6266](https://www.rfc-editor.org/rfc/rfc6266.html), [RFC 8187](https://www.rfc-editor.org/rfc/rfc8187.html)

Encode toàn bộ chuỗi header sẽ làm mất cấu trúc cần thiết. Chỉ encode thành phần theo đúng grammar, sau khi value đã đáp ứng policy. Một chuỗi điều khiển không nên được âm thầm chấp nhận chỉ vì có thể biến thành percent-encoding trong một parameter.

Tên tải xuống và đường dẫn file phía server cũng là hai dữ liệu khác nhau. Không dùng filename do client gửi trực tiếp làm đường dẫn mở file.

## 9. Location: một dòng hợp lệ chưa đủ an toàn

`Location` chứa đích chuyển hướng. Hai yêu cầu độc lập là:

1. Value không phá cấu trúc header.
2. Đích chuyển hướng thuộc phạm vi được phép.

Chỉ cấm CR/LF vẫn cho phép một URL bên ngoài nếu ứng dụng phản xạ raw `next` vào `Location`. Đây là vấn đề open redirect, dù không tạo field mới.

Với các đích hữu hạn, mapping thường rõ ràng hơn việc chấp nhận mọi URI:

~~~text
option "reports" -> /app/reports
option "home"    -> /app
~~~

Server có thể đặt một đích cố định đã được chọn:

~~~java
response.setStatus(HttpServletResponse.SC_SEE_OTHER);
response.setHeader("Location", "/app/reports");
~~~

Nếu phải nhận URI động, cần parser và policy cho scheme, origin, userinfo, dạng tương đối và các trường hợp đặc biệt. Kiểm tra “bắt đầu bằng dấu slash” không đủ vì một URI-reference dạng `//host/path` có ý nghĩa khác đường dẫn cục bộ mong muốn.

Khi tạo URL tuyệt đối cho email, OAuth hoặc phục hồi tài khoản, public origin nên lấy từ cấu hình đáng tin hoặc cơ chế proxy trust đã xác định. Không tự tin `Host` hoặc `X-Forwarded-Host` do client gửi chỉ vì chúng không chứa newline.

## 10. Cookie và các header do server sở hữu

### Cookie

`Set-Cookie` có grammar riêng cho value và các thuộc tính. Một dấu chấm phẩy có thể có ý nghĩa ở cấp thuộc tính, không chỉ là văn bản bình thường trong mọi vị trí.

Yêu cầu nên quy định:

- Dùng API cookie hoặc builder phù hợp.
- Tên cookie và các thuộc tính bảo mật thuộc quyền quản lý của server.
- Value đáp ứng grammar và encoding đã chọn.
- `Domain`, `Path`, `Secure`, `HttpOnly` và `SameSite` không lấy trực tiếp từ input tùy ý.
- Mỗi cookie được phát theo semantics của API, không tự nối mọi `Set-Cookie` thành một list ngăn bằng dấu phẩy.

`Set-Cookie` là trường hợp đặc biệt khi xử lý nhiều field cùng tên; không áp dụng quy tắc gộp list một cách máy móc. [RFC 9110, mục 5.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-5.3)

Việc một cookie API có thể tạo cấu trúc đúng không đồng nghĩa dữ liệu nhạy cảm nào cũng được phép đưa vào cookie. Phạm vi phiên, tính toàn vẹn và vòng đời cookie vẫn cần thiết kế riêng.

### Header bảo mật và cache

Các header như `Content-Security-Policy`, `Access-Control-Allow-Origin` hoặc `Cache-Control` có ngữ nghĩa điều khiển quan trọng. Client không được tùy ý thay đổi chúng qua một trường metadata.

Ví dụ phản xạ mọi `Origin` một dòng sang `Access-Control-Allow-Origin` không trở nên an toàn chỉ nhờ chặn CR/LF. Cần chính sách CORS riêng.

Tương tự, một header cache hợp lệ nhưng do bên không có quyền quyết định có thể làm phản hồi nhạy cảm bị lưu hoặc chia sẻ sai. Ownership phải nêu rõ ứng dụng, gateway hay CDN là nơi sở hữu giá trị cuối cùng.

## 11. Outbound header và ranh giới tin cậy qua proxy

Một service thường nhận request rồi gọi service khác. Không nên chuyển tiếp nguyên xi toàn bộ header đầu vào:

~~~java
// Không có policy forwarding và có thể chuyển tiếp quyền không phù hợp.
incomingHeaders.forEach((name, values) -> {
    for (String value : values) {
        outboundBuilder.header(name, value);
    }
});
~~~

Ngay cả khi HTTP client chặn ký tự không hợp lệ, việc này có thể chuyển nhầm credential, header định tuyến hoặc danh tính do client tự khai.

Một policy forwarding cần xác định:

| Nhóm field | Chính sách minh họa |
|---|---|
| Correlation metadata | Chỉ forward field đã cho phép, theo profile |
| `Authorization` | Cấp credential của đúng workload/đích; không mặc định forward token client |
| `Cookie` | Không chuyển sang upstream khác phạm vi theo thói quen |
| Header tenant/role nội bộ | Tạo từ ngữ cảnh đã xác thực, không tin bản client gửi |
| `Host` và thông tin authority | Để HTTP client xác lập từ đích có kiểm soát |
| Field framing hoặc connection-specific | Do giao thức và tầng HTTP quản lý |
| Field mở rộng không biết | Không forward nếu contract không cho phép |

### Header danh tính nội bộ

Giả sử gateway thêm `X-Internal-Tenant`. Muốn backend tin nó, cần đủ các điều kiện:

- Request từ bên ngoài không thể tự đi thẳng vào đường backend tin cậy.
- Gateway loại bỏ hoặc ghi đè bản do client cung cấp.
- Kênh giữa các thành phần được xác thực phù hợp.
- Backend chỉ tin header khi request đến từ nguồn được phép.
- Các tác vụ nội bộ đi đường khác có contract rõ ràng.

Header đúng cú pháp và tên bắt đầu bằng `X-Internal-` không phải bằng chứng về danh tính.

### Forwarded headers

`Forwarded` và nhóm `X-Forwarded-*` cần trust policy theo cấu trúc proxy thực tế. Không tin tự động toàn bộ chuỗi do client gửi. Việc suy ra IP, scheme hoặc host cần chỉ rõ hop nào được phép cung cấp phần thông tin nào.

Nếu thông tin này tham gia audit, giới hạn IP hoặc xây URL bảo mật, yêu cầu tin cậy phải được kiểm chứng xuyên suốt chuỗi proxy.

## 12. Duplicate headers và chuyển đổi HTTP/1.1–HTTP/2

Một field có nhiều value có thể hợp lệ hoặc không, tùy định nghĩa field. Không dùng một quy tắc “lấy đầu”, “lấy cuối” hoặc “nối bằng dấu phẩy” cho mọi trường.

Với singleton do ứng dụng định nghĩa như correlation ID trong ví dụ, có thể chọn từ chối nhiều value. Với field cho phép list, cần parser list đúng grammar. Với header framing, parser giao thức và các proxy phải thực thi quy tắc tương ứng; không tự viết bộ parser HTTP bằng vài thao tác trên chuỗi.

### Obsolete line folding

Cách gấp dòng cũ trong HTTP/1.x có thể làm các thành phần diễn giải khác nhau. RFC 9112 không cho sender tạo obs-fold trong thông điệp thông thường ngoài ngoại lệ được quy định. Ứng dụng nên phát field một dòng bằng API phù hợp; ingress có thể chọn policy từ chối dạng gấp dòng không được hỗ trợ. [RFC 9112, mục 5.2](https://www.rfc-editor.org/rfc/rfc9112.html#section-5.2)

Không dùng việc một parser “chịu lỗi tốt” làm cơ sở để chấp nhận dữ liệu mà parser phía sau có thể hiểu khác.

### HTTP/2 không dùng header dạng dòng giống HTTP/1.1

HTTP/2 biểu diễn field bằng cơ chế của protocol, không phải ghép chuỗi CRLF như ví dụ HTTP/1.1. Tuy nhiên, nó vẫn có yêu cầu về tính hợp lệ của field và có thể đi qua gateway chuyển sang HTTP/1.1. [RFC 9113, mục 8.2.1](https://www.rfc-editor.org/rfc/rfc9113.html#section-8.2.1)

Vì vậy, “client đang dùng HTTP/2” không đủ để kết luận toàn chuỗi không có rủi ro header injection. Cần xét:

- Protocol ở từng hop.
- Cách chuyển đổi và kiểm tra field.
- Field nào được tạo sau bước kiểm tra đầu tiên.
- Hành vi với dữ liệu không hợp lệ và field trùng.

Không phải mọi khác biệt parser đều tự tạo được một khai thác. Yêu cầu cần gắn với cấu hình thực tế và bằng chứng hành vi ở các hop liên quan.

## 13. Dữ liệu đã lưu, email và đường đi ít gặp

### Header được tạo từ dữ liệu đã lưu

Tên file hoặc label được lưu hợp lệ trong database có thể chứa ký tự không phù hợp để đưa vào header. Một lần kiểm tra khi tạo bản ghi không thay thế validation của ngữ cảnh sử dụng về sau.

Ví dụ:

~~~text
Tên báo cáo được nhập
    -> lưu dưới dạng văn bản
    -> job xuất báo cáo đọc lại
    -> dùng tên làm Content-Disposition
~~~

Job phải áp dụng profile filename/header tại sink. Không thể coi tất cả văn bản đã lưu đều là một field value HTTP hợp lệ.

### Email header injection

Email có header, address list, encoded-word và folding theo chuẩn riêng. Nếu ứng dụng ghép raw subject hoặc địa chỉ người nhận vào một chuỗi thông điệp, dữ liệu có thể tác động tới cấu trúc ngoài dự định.

Yêu cầu nên tách riêng:

- Parse địa chỉ và giới hạn người nhận theo nghiệp vụ.
- Dùng API mail/MIME có cấu trúc.
- Không nhận raw block header từ một input subject thông thường.
- Phân biệt địa chỉ nhận thực tế, tên hiển thị và các trường được phép.
- Không tự dùng cùng hàm escape cho HTTP header và email header.

Phần này là ranh giới liên quan để tránh áp dụng sai biện pháp; policy HTTP trong bài không phải đặc tả đầy đủ cho hệ thống email.

### Đường lỗi và retry

Response lỗi, redirect sau đăng nhập, tên file trong export và header của một request retry thường bị bỏ sót. Mỗi nhánh tạo header cần cùng quy tắc kiểm soát; một helper an toàn ở đường thành công không bảo vệ đoạn nối chuỗi trong error handler.

## 14. Bộ yêu cầu bảo mật mẫu

Giả sử nền tảng có API tải báo cáo, correlation ID và lời gọi tới report service. Có thể chuyển mục tiêu thành các yêu cầu sau:

| ID | Yêu cầu | Bằng chứng nghiệm thu dự kiến |
|---|---|---|
| HDR-01 | Không có dữ liệu không đáng tin được ghi thành raw field line | Rà soát sink, writer và các đường serialize thủ công |
| HDR-02 | Tên header nghiệp vụ lấy từ hằng hoặc mapping được server quản lý | Kiểm tra option ngoài mapping và tên khác hoa thường |
| HDR-03 | Value đáp ứng profile sau các bước parse/decode theo contract | Ca CR, LF, NUL, JSON escape và encoded input |
| HDR-04 | Không có decoder về sau có thể biến value đã kiểm tra thành delimiter | Theo dõi cùng dữ liệu qua adapter, service, client và proxy |
| HDR-05 | `X-Correlation-ID` tuân profile 1–64 ký tự và policy nhiều value | Ca thiếu, hợp lệ, quá dài và trùng |
| HDR-06 | Filename tải xuống được server tạo hoặc dùng builder/encoder parameter đúng grammar | Ca quote, semicolon, Unicode và ký tự điều khiển |
| HDR-07 | Đích `Location` được kiểm soát độc lập với tính hợp lệ header | Ca đích ngoài phạm vi và URI-reference đặc biệt |
| HDR-08 | Outbound request chỉ mang header được policy forwarding cho phép | Upstream kiểm chứng không nhận field/credential ngoài contract |
| HDR-09 | Header danh tính nội bộ không do client quyết định | Ca client tự gửi field nội bộ và truy cập qua các đường mạng được xét |
| HDR-10 | Header trùng và protocol conversion có hành vi nhất quán theo contract | Kiểm tra qua chuỗi ingress–gateway–service có thật |
| HDR-11 | Input không hợp lệ không đi vào response lỗi hoặc log dưới dạng raw nguy hiểm | Kiểm tra error path và dữ liệu quan sát |
| HDR-12 | Kích thước value và tổng header có giới hạn tương thích các hop | Ca vượt hạn trước và sau encoding |

Giới hạn ví dụ 64 ký tự cho correlation ID chỉ thuộc contract minh họa. Hạn mức cho header khác và tổng header phải được chọn theo chức năng, server, proxy và HTTP client triển khai.

Một yêu cầu hoàn chỉnh có thể viết:

> Khi nhận correlation ID từ client, adapter phải áp dụng policy nhiều value và grammar trước khi sử dụng. Chỉ tên field cố định được trả về hoặc forward. Input bị từ chối không được xuất hiện trong bất kỳ header nào của response lỗi. Qua chuỗi proxy được hỗ trợ, client không tạo được field ngoài contract hoặc thay giá trị header do server sở hữu.

Các bằng chứng trong bảng là kế hoạch nghiệm thu, không phải tuyên bố đã chạy kiểm thử cho một hệ thống cụ thể.

## 15. Ma trận trường hợp kiểm chứng

Môi trường kiểm chứng nên dùng dữ liệu giả và một upstream do nhóm kiểm soát. Không cần gửi credential thật hoặc thử làm nhiễm cache chung của người dùng.

| Nhóm | Input hoặc sự kiện | Kết quả mong đợi |
|---|---|---|
| Hợp lệ | Correlation ID `req-123.ab` | Một value đúng contract, không đổi nội dung |
| Vắng field | Không có correlation ID | Server tạo ID mới đúng profile |
| CR/LF | Value sau parse chứa CR hoặc LF | Từ chối trước khi tạo header từ value |
| NUL | Value chứa `\u0000` sau JSON parse | Từ chối theo profile |
| Cặp bị tách | CR riêng hoặc LF riêng | Không chỉ chặn trường hợp có cả CRLF |
| Percent encoding | Query value giải mã thành CRLF | Bị từ chối trên biểu diễn đã decode |
| Encoding kép | Value chỉ thành CRLF nếu decode thêm | Không có decoder ngoài contract; value ngoài grammar bị từ chối |
| JSON literal | Văn bản `%0D` trong một trường không decode percent | Không tự chuyển thành CR |
| Nhiều value | Hai correlation ID | Từ chối theo policy singleton của ứng dụng |
| Khác hoa thường | Tên field khác case | Không vượt policy ownership |
| Filename | Quote, semicolon, Unicode | Từ chối hoặc biểu diễn parameter đúng contract, không tạo field mới |
| Redirect | Đích một dòng nhưng ngoài phạm vi | Bị chặn theo redirect policy |
| Header nội bộ | Client gửi tenant/role tự khai | Không được tin như danh tính đã xác thực |
| Dữ liệu đã lưu | Job đọc lại label chứa newline | Không đưa raw label vào header |
| Protocol | HTTP/2 ở một hop, HTTP/1.1 ở hop khác | Header vẫn đúng contract ở bên nhận cuối |
| Lỗi | Builder từ chối value | Không có fallback ghi raw; response lỗi không phản xạ input |

### Ca kiểm chứng qua response

**Given:** một endpoint có field ứng dụng được dùng để tạo header theo contract.

**When:** field sau parse chứa CR/LF và một tên field đánh dấu vô hại như `X-Demo`.

**Then:** input bị từ chối; client không nhận `X-Demo` do input tạo ra, không có body hoặc response phụ ngoài dự định, và các header do server sở hữu giữ đúng policy.

Nếu client library đã từ chối ngay việc tạo request, kết quả đó chỉ chứng minh khả năng kiểm tra của client library. Nó chưa kiểm chứng server. Có thể dùng request hợp lệ chứa JSON escape hoặc query encoding để đi qua đúng đường parse cần xét, trong phạm vi môi trường được phép.

### Ca kiểm chứng outbound

**Given:** service gọi một upstream kiểm chứng do nhóm kiểm soát.

**When:** client gửi header không nằm trong allowlist hoặc metadata không hợp lệ.

**Then:** upstream không nhận header ngoài contract; credential dành cho client không bị chuyển nhầm; dữ liệu sai không được “sửa” rồi âm thầm forward.

### Ca kiểm chứng parser thực tế

Khi kiểm tra header ở phía nhận, cần quan sát danh sách field và số value theo giao thức, không chỉ tìm substring trong một bản dump đã được công cụ format lại.

Với cache hoặc gateway, cần phân biệt dữ liệu của từng request kiểm chứng và bảo đảm không ảnh hưởng lưu lượng dùng chung. Đối với framing/protocol, harness và phạm vi kiểm tra phải được chuẩn bị riêng; không biến một ca unit của validator thành kết luận về toàn bộ hạ tầng.

## 16. Hành vi khi từ chối và thông tin quan sát

Input mới từ client không hợp lệ có thể trả mã lỗi ứng dụng phù hợp, chẳng hạn 400 theo contract. Nhưng metadata hỏng được đọc từ database là tình huống khác; không tự quy lỗi client hiện tại nếu nguyên nhân là dữ liệu nội bộ.

Yêu cầu nên nêu:

- Kiểm tra trước khi commit response hoặc gửi request upstream.
- Không phát một phần header nguy hiểm rồi mới báo lỗi.
- Không đưa input bị từ chối vào chính header lỗi.
- Không phản xạ raw value vào thông báo hoặc log không có escaping.
- Phân loại nguồn và owner để xử lý dữ liệu đã lưu không hợp lệ.
- Không bắt exception rồi gọi API khác bỏ kiểm tra.

Một sự kiện quan sát có thể chứa:

~~~json
{
  "eventType": "header_value_rejected",
  "fieldPolicy": "correlation-id-v1",
  "source": "client",
  "reason": "INVALID_CHARACTER",
  "requestId": "server-generated-event-id",
  "action": "REJECTED"
}
~~~

Request ID của sự kiện không nên lấy từ chính value đang bị từ chối. Không cần ghi toàn bộ payload, cookie, token hay header Authorization để chứng minh rằng có input sai.

Chỉ số có thể theo dõi số lần reject theo field policy, lỗi serializer và lỗi upstream liên quan header. Tránh dùng raw input làm nhãn metric vì có thể chứa bí mật và tạo số lượng nhãn không kiểm soát.

Một lần reject không tự chứng minh có tấn công chủ đích. Có thể là lỗi client, import hoặc cấu hình; dữ liệu quan sát cần hỗ trợ phân loại mà không làm phát sinh một sink injection mới.

## 17. Những cách sửa không đủ

| Cách sửa | Giới hạn hoặc sai sót |
|---|---|
| Chỉ cấm raw `%0d%0a` | Bỏ sót biểu diễn sau decode và các lớp encoding khác |
| Chỉ tìm đúng cặp `\r\n` | Có thể bỏ CR, LF hoặc NUL riêng |
| Xóa newline rồi dùng tiếp | Âm thầm thay đổi dữ liệu, che lỗi và không giải quyết grammar khác |
| HTML-escape header value | Sai ngữ cảnh |
| URL-encode toàn bộ header | Có thể phá cấu trúc và không đúng grammar field |
| Tin mọi setter đều kiểm tra mọi policy | Serializer không quyết định quyền đặt header |
| Tắt kiểm tra restricted header | Có thể phá giả định an toàn của HTTP client |
| Chặn newline nhưng forward tất cả field | Vẫn chuyển nhầm quyền hoặc credential |
| Dùng HTTP/2 nên bỏ kiểm tra | Bỏ qua field validity và các hop chuyển đổi |
| Chỉ test helper validator | Không bao phủ proxy, error path và job nền |
| Cấm mọi Unicode ở mọi vị trí | Có thể làm mất chức năng hợp lệ thay vì dùng encoding parameter phù hợp |
| Gộp mọi header trùng bằng dấu phẩy | Không phù hợp mọi field, đặc biệt cookie |

## 18. Bài tập thiết kế yêu cầu

Một API tạo file export nhận tên hiển thị báo cáo, đích điều hướng sau hoàn tất và correlation ID. Service còn gọi một upstream với metadata của tenant.

Hãy xác định:

1. Trường nào cần ở body và có thực sự cần đưa lên header không?
2. Những tên header nào do server quản lý?
3. Grammar, giới hạn và policy nhiều value của từng field là gì?
4. Ai decode input, và có thành phần nào decode lần nữa không?
5. Filename Unicode được biểu diễn thế nào mà không tạo cấu trúc ngoài dự định?
6. Đích redirect có được kiểm soát dù hoàn toàn không có CR/LF không?
7. Tenant header outbound lấy từ nguồn nào và upstream tin nó theo cơ chế nào?
8. Bằng chứng nào xác nhận hành vi qua đúng proxy, HTTP server và HTTP client đang triển khai?

Một đặc tả header injection đủ rõ phải nối được nguồn dữ liệu, quyền đặt field, grammar và bên nhận cuối. Khi ứng dụng giữ dữ liệu trong đúng thành phần đã định nghĩa, còn cấu trúc và các header có quyền lực thuộc quyền quản lý của server, yêu cầu phòng vệ mới có thể được triển khai và kiểm chứng nhất quán.
