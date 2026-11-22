# URI template và xây dựng URI an toàn

Trong chương **Thiết kế URI** của module **INTEGRATION_API_REST**, một URI cần diễn đạt đúng resource và giữ được ý nghĩa đó khi dữ liệu thực tế chứa dấu cách, tiếng Việt hoặc ký tự đặc biệt. URI template mô tả cấu trúc liên kết, còn quá trình xây dựng URI biến cấu trúc ấy thành một địa chỉ dùng được trong request, response hoặc tài liệu API.

Bài học tập trung vào việc xây dựng URI theo hợp đồng rõ ràng, mã hóa giá trị theo đúng vị trí và kiểm soát nguồn dữ liệu đầu vào. Ví dụ sử dụng Java/Spring, nhưng các nguyên tắc cũng áp dụng cho công nghệ khác. Những kỹ năng này hỗ trợ trực tiếp việc tạo liên kết phân trang, trả header `Location`, mô tả OpenAPI và kiểm thử API.

Sau bài này, bạn có thể:

- Phân biệt URI template với URI đã mở rộng và với mẫu route của framework.
- Đưa dữ liệu vào đúng path segment hoặc query parameter.
- Tránh nối chuỗi làm thay đổi cấu trúc URI, mã hóa hai lần và giải mã hai lần.
- Xây dựng URI trong Spring từ template cố định và giá trị chưa mã hóa.
- Nhận diện giới hạn của encoding đối với phân quyền, chuyển hướng, proxy và SSRF.

## 1. Từ cấu trúc resource đến URI template

Giả sử hệ thống quản lý tài liệu theo tenant:

```text
Một tài liệu:
https://api.example.com/v1/tenants/acme/documents/550e8400-e29b-41d4-a716-446655440000

Tìm tài liệu trong một tenant:
https://api.example.com/v1/tenants/acme/documents?q=java&page=0&size=20
```

Các phần cố định thể hiện cấu trúc resource. Các phần thay đổi là định danh tenant, định danh tài liệu và điều kiện truy vấn. Có thể mô tả cấu trúc tài liệu bằng template:

```text
https://api.example.com/v1/tenants/{tenantId}/documents/{documentId}
```

Với các biến:

```text
tenantId   = acme
documentId = 550e8400-e29b-41d4-a716-446655440000
```

Sau khi mở rộng, ta nhận được URI cụ thể. Template chứa dấu `{` và `}` chưa thay thế không phải địa chỉ cuối cùng để đưa thẳng cho HTTP client.

Template là hợp đồng về **vị trí của dữ liệu**, không chỉ là cách tránh viết lặp chuỗi. Nếu `tenantId` đại diện cho một segment thì dữ liệu của biến này không được tự ý tạo thêm segment hoặc query parameter.

### 1.1. Nhận biết các thành phần URI

```text
https://api.example.com:443/v1/documents/123?q=java%20spring#summary
```

| Thành phần | Giá trị trong ví dụ |
|---|---|
| Scheme | `https` |
| Authority | `api.example.com:443`, gồm host và port |
| Path | `/v1/documents/123` |
| Query | `q=java%20spring` |
| Fragment | `summary` |

Fragment không được gửi trong request-target của HTTP. Địa chỉ `/documents#draft` không yêu cầu server tìm resource có path `/documents#draft`; phần `#draft` có ý nghĩa ở phía client. Nếu dấu `#` là dữ liệu của một giá trị, nó phải được mã hóa thành `%23` khi xây dựng URI.

Đối với REST API, hãy xác định rõ biến nào thuộc path, biến nào thuộc query và thành phần nào do server quản lý. Không dùng một chuỗi dữ liệu duy nhất để vừa biểu diễn tenant, vừa chọn host, vừa thêm query.

## 2. Ba khái niệm thường bị nhầm

### 2.1. URI template theo RFC 6570

RFC 6570 mô tả ngôn ngữ template với nhiều phép mở rộng. Một số dạng thường gặp:

| Biểu thức | Ý nghĩa | Ví dụ mở rộng |
|---|---|---|
| `{id}` | Mở rộng đơn giản | `id = a/b` tạo `a%2Fb` |
| `{+path}` | Mở rộng cho phép giữ lại ký tự reserved | `path = reports/2026` tạo `reports/2026` |
| `{/id}` | Mở rộng path, thêm dấu `/` | `id = abc` tạo `/abc` |
| `{?q,page}` | Mở rộng các biến query đã được cung cấp | `q = java spring`, `page = 2` tạo `?q=java%20spring&page=2` |
| `{&sort}` | Nối thêm biến query sau query có sẵn | `sort = title` tạo `&sort=title` |
| `{/segments*}` | Mở rộng danh sách thành các segment riêng | `segments = [reports, 2026]` tạo `/reports/2026` |

Đây là các phép mở rộng RFC 6570, không phải cú pháp được mọi thư viện hỗ trợ. Dấu `*` ở ví dụ cuối là toán tử mở rộng danh sách, không phải wildcard nhận mọi đường dẫn.

Đặc biệt, `{+path}` chủ động cho phép ký tự reserved giữ vai trò cấu trúc. Không thay `{id}` bằng `{+id}` chỉ để làm cho dấu `/` trong dữ liệu “chạy được”. Việc đó có thể biến một định danh thành nhiều segment hoặc thay đổi những thành phần khác của URI.

### 2.2. Template dùng bởi URI builder của framework

Spring thường dùng placeholder đơn giản như:

```text
/v1/tenants/{tenantId}/documents/{documentId}
```

Builder thay các placeholder bằng biến được cung cấp. Không mặc định rằng cùng builder đó hiểu đầy đủ các toán tử RFC 6570 như `{?q,page}` hoặc `{/segments*}`.

Với `UriComponentsBuilder` trong bài này, query parameter được khai báo qua `queryParam(...)`, còn các giá trị động được truyền khi mở rộng placeholder.

### 2.3. Mẫu route dùng để nhận request

Một controller cũng có thể khai báo:

```java
@GetMapping("/v1/tenants/{tenantId}/documents/{documentId}")
```

Đây là mẫu để framework khớp request đến với handler. Một số framework còn có cú pháp ràng buộc hoặc wildcard riêng cho route.

Mẫu route và template tạo liên kết có thể trông giống nhau nhưng phục vụ hai chiều khác nhau:

```text
Request đến -> route matching -> binding -> validation -> authorization

Dữ liệu resource -> template + builder -> URI -> response/client request
```

Một route khớp được không chứng minh URI đầu ra đã được mã hóa đúng. Ngược lại, URI đúng cú pháp không chứng minh người gọi có quyền truy cập resource.

## 3. Đặt ranh giới giữa cấu trúc và dữ liệu

Xét cách viết sau:

```java
// Không dùng để xây URI từ dữ liệu không được kiểm soát.
String url = "/v1/documents?q=" + query + "&page=" + page;
```

Nếu `query` là:

```text
java&size=1000
```

Kết quả với `page = 0` sẽ là:

```text
/v1/documents?q=java&size=1000&page=0
```

Dữ liệu dự kiến thuộc giá trị `q` đã tạo thêm tham số `size`. Đây là thay đổi cấu trúc request, dù chuỗi kết quả vẫn có thể là URI hợp lệ.

Tình huống tương tự xảy ra với path:

```java
String url = "/v1/documents/" + documentId;
```

Nếu `documentId` chứa `/`, `?` hoặc `#`, phép nối chuỗi có thể tạo thêm segment, bắt đầu query hoặc bắt đầu fragment.

Cách tiếp cận đúng có ba lớp:

1. **Cấu trúc cố định:** code hoặc cấu hình tin cậy quyết định scheme, host, path template và tên tham số.
2. **Validation theo hợp đồng:** kiểm tra tenant ID, UUID, giới hạn phân trang và độ dài truy vấn.
3. **Encoding theo thành phần:** builder đưa mỗi giá trị vào đúng vị trí trong URI.

Validation và encoding giải quyết các vấn đề khác nhau. Validation trả lời “giá trị này có được phép trong API không?”. Encoding trả lời “biểu diễn giá trị này trong URI như thế nào để giữ nguyên ranh giới cấu trúc?”.

Ví dụ, `A&B` có thể là truy vấn hợp lệ và cần được giữ nguyên về mặt dữ liệu. Không nên xóa dấu `&` chỉ để tránh viết builder. Ngược lại, nếu hợp đồng quy định `documentId` là UUID thì giá trị `A&B` phải bị từ chối vì sai kiểu, dù hoàn toàn có thể mã hóa nó.

## 4. Percent-encoding: mã hóa giá trị theo đúng vị trí

Percent-encoding biểu diễn byte bằng `%` theo sau bởi hai chữ số thập lục phân. Với văn bản Unicode, thông thường cần chuyển ký tự thành byte UTF-8 trước khi biểu diễn các byte đó.

Nhóm ký tự unreserved gồm:

```text
A-Z a-z 0-9 - . _ ~
```

Các ký tự thuộc nhóm này có thể xuất hiện trực tiếp trong giá trị URI. Nhiều ký tự khác có vai trò ngăn cách tùy thành phần, ví dụ `/`, `?`, `#`, `&`, `=`, `+` và `;`.

Một số cách biểu diễn khi mã hóa chặt giá trị biến:

| Dữ liệu gốc | Dạng mã hóa | Lưu ý |
|---|---|---|
| Dấu cách | `%20` | Thường dùng trong URI do builder tạo |
| `&` | `%26` | Giữ nó trong giá trị thay vì tạo tham số query mới |
| `+` | `%2B` | Phân biệt dấu cộng thật với quy ước dấu cách của form |
| `/` | `%2F` | Giữ `/` như dữ liệu khi tạo URI; chưa bảo đảm server chấp nhận trong path |
| `?` | `%3F` | Không mở query mới |
| `#` | `%23` | Không mở fragment |
| `%` | `%25` | Biểu diễn dấu phần trăm gốc |
| `Đ` | `%C4%90` | Hai byte UTF-8 của ký tự `Đ` |

“Reserved” không có nghĩa là ký tự ấy bị cấm ở mọi nơi. Ví dụ `/` là dấu phân tách trong path và có thể được phép trong query. Tuy vậy, mã hóa chặt dữ liệu biến thường giúp bảo đảm giá trị không được diễn giải thành cấu trúc ngoài ý muốn.

### 4.1. Không mã hóa nguyên URI như một giá trị

Nếu mã hóa toàn bộ chuỗi:

```text
https://api.example.com/v1/documents?q=java
```

như một giá trị đơn, bạn có thể mã hóa cả `:`, `/`, `?` và `=` vốn đang tạo cấu trúc URI. Kết quả không còn là địa chỉ có cấu trúc mong muốn.

Trình tự hợp lý là tạo cấu trúc bằng builder và đưa dữ liệu vào từng placeholder hoặc parameter. Không xây một chuỗi bằng phép nối rồi tìm một lệnh “encode tất cả” để sửa lại.

### 4.2. `URLEncoder` không phải bộ mã hóa path segment tổng quát

`java.net.URLEncoder` phục vụ định dạng `application/x-www-form-urlencoded`. Trong quy ước này, dấu cách thường được biểu diễn bằng `+`.

```java
String encoded = URLEncoder.encode(
        "java spring", StandardCharsets.UTF_8);
// java+spring
```

Nếu dùng trực tiếp chuỗi đó làm path segment, dấu `+` không tự mang ý nghĩa dấu cách như trong bộ giải mã form. Bạn có thể tạo ra định danh khác với dữ liệu ban đầu.

Khi hợp đồng yêu cầu form encoding, dùng công cụ dành cho form. Khi xây URI, dùng API có nhận biết các thành phần URI và cơ chế mở rộng biến phù hợp. Đừng coi mọi hàm có chữ `encode` là tương đương nhau.

### 4.3. Chỉ mã hóa một lần tại ranh giới đã xác định

Giả sử giá trị tìm kiếm thực sự là `A/B`:

```text
Giá trị gốc:       A/B
Mã hóa một lần:    A%2FB
Mã hóa lần nữa:    A%252FB
```

`%25` là dấu `%` đã được mã hóa. Sau một lần giải mã, `A%252FB` trở thành chuỗi `A%2FB`, chưa phải `A/B`.

Quy ước dễ duy trì là:

> Tầng nghiệp vụ truyền giá trị chưa percent-encode. Một tầng xây URI chịu trách nhiệm mã hóa đúng một lần.

Cần phân biệt hai trường hợp:

- Đầu vào là dữ liệu gốc `A/B`: builder cần tạo `A%2FB` khi mã hóa chặt biến.
- Đầu vào thực sự gồm năm ký tự `A%2FB`: builder tạo `A%252FB` là đúng để giữ nguyên dấu `%` trong dữ liệu.

Không tự đoán chuỗi “có vẻ đã encode” để bỏ qua encoding. Nếu cần nhận URI đã mã hóa từ bên ngoài, hãy thiết kế hợp đồng và luồng xử lý riêng, thay vì trộn nó với các giá trị gốc.

## 5. Xây dựng URI với Java/Spring

Ví dụ dưới đây dùng Java 17 trở lên và `UriComponentsBuilder` của Spring Web. API giả định:

- Tenant ID dài từ 1 đến 64 ký tự, chỉ gồm chữ ASCII, chữ số, `_`, `-`; ký tự đầu là chữ hoặc số.
- Document ID là UUID.
- Truy vấn tìm kiếm không rỗng và tối đa 200 Unicode code point.
- `page` bắt đầu từ `0`; `size` nằm trong khoảng `1..100`.
- Public origin do hệ thống quản lý là `https://api.example.com`.

Đây là lựa chọn hợp đồng của ví dụ, không phải quy định bắt buộc cho mọi REST API.

```java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.regex.Pattern;

import org.springframework.web.util.UriComponentsBuilder;

public final class DocumentUris {

    private static final String PUBLIC_ORIGIN =
            "https://api.example.com";

    private static final Pattern TENANT_ID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9_-]{0,63}");

    public URI document(String tenantId, UUID documentId) {
        String tenant = requireTenantId(tenantId);
        Objects.requireNonNull(documentId, "documentId");

        return UriComponentsBuilder
                .fromUriString(PUBLIC_ORIGIN)
                .path("/v1/tenants/{tenantId}/documents/{documentId}")
                .encode(StandardCharsets.UTF_8)
                .buildAndExpand(Map.of(
                        "tenantId", tenant,
                        "documentId", documentId.toString()))
                .toUri();
    }

    public URI search(
            String tenantId, String query, int page, int size) {

        String tenant = requireTenantId(tenantId);
        String checkedQuery = requireQuery(query);
        requirePagination(page, size);

        return UriComponentsBuilder
                .fromUriString(PUBLIC_ORIGIN)
                .path("/v1/tenants/{tenantId}/documents")
                .queryParam("q", "{query}")
                .queryParam("page", page)
                .queryParam("size", size)
                .encode(StandardCharsets.UTF_8)
                .buildAndExpand(Map.of(
                        "tenantId", tenant,
                        "query", checkedQuery))
                .toUri();
    }

    private static String requireTenantId(String value) {
        if (value == null || !TENANT_ID.matcher(value).matches()) {
            throw new IllegalArgumentException("Invalid tenantId");
        }
        return value;
    }

    private static String requireQuery(String value) {
        Objects.requireNonNull(value, "query");
        int length = value.codePointCount(0, value.length());
        if (value.isBlank() || length > 200) {
            throw new IllegalArgumentException("Invalid query");
        }
        return value;
    }

    private static void requirePagination(int page, int size) {
        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException("Invalid pagination");
        }
    }
}
```

Các exception trong ví dụ chỉ thể hiện việc từ chối dữ liệu sai hợp đồng. Khi dùng trong API, tầng HTTP cần ánh xạ lỗi validation đầu vào thành response lỗi thống nhất, thường là `400 Bad Request`; không để chúng vô tình trở thành lỗi `500`.

### 5.1. Tại sao đặt `encode()` trước khi mở rộng biến?

Trong cách dùng của ví dụ, lời gọi `encode(...)` trên builder trước `buildAndExpand(...)` yêu cầu mã hóa template và mã hóa chặt các giá trị biến khi mở rộng. Nhờ đó, dữ liệu như `&` hoặc `+` không được giữ lại như ký tự reserved có khả năng thay đổi cách hiểu query.

Luồng xử lý là:

```text
Template cố định + giá trị gốc
        |
        v
Builder nhận biết path và query
        |
        v
encode() cấu hình mã hóa khi build/mở rộng
        |
        v
buildAndExpand(...) thay biến và mã hóa giá trị
        |
        v
URI hoàn chỉnh
```

Không tráo thứ tự một cách tùy tiện. Mã hóa các component sau khi đã mở rộng có thể giữ lại những ký tự reserved hợp lệ trong component; hành vi đó không luôn tương đương với mã hóa chặt dữ liệu biến trước khi chúng trở thành một phần của URI.

Cũng không dùng `build(true)` như một tùy chọn “an toàn hơn”. Tham số đó khai báo các component đã được mã hóa; nó không có nghĩa là hãy mã hóa mọi dữ liệu đầu vào.

### 5.2. Kết quả với ký tự đặc biệt

```java
DocumentUris uris = new DocumentUris();

URI searchUri = uris.search(
        "acme",
        "A&B + C/Đ",
        0,
        20);

System.out.println(searchUri.toASCIIString());
```

Kết quả mong đợi:

```text
https://api.example.com/v1/tenants/acme/documents?q=A%26B%20%2B%20C%2F%C4%90&page=0&size=20
```

Dấu `&` bên trong `q` trở thành `%26`, còn các dấu `&` do builder đặt giữa `q`, `page` và `size` vẫn là dấu phân cách. Dấu cộng trong dữ liệu trở thành `%2B`, giúp phân biệt với quy ước dấu cách của các bộ giải mã form.

`toASCIIString()` biểu diễn một URI dưới dạng ASCII. Nó không thay thế các bước validation, xây cấu trúc hoặc mã hóa giá trị của builder.

### 5.3. Dùng kiểu `URI` ở ranh giới HTTP

Khi tầng xây liên kết đã tạo được `URI`, nên truyền đối tượng ấy vào overload nhận `URI` của HTTP client hoặc response API khi có hỗ trợ.

```java
URI location = uris.document(tenantId, documentId);

return ResponseEntity.created(location).body(responseBody);
```

Đoạn trên minh họa phần return trong handler tạo tài liệu thành công. Các biến `tenantId`, `documentId` và `responseBody` là dữ liệu đã có sau thao tác tạo resource.

`Location` phải trỏ đến resource vừa tạo theo chính sách public URL của hệ thống. Đừng tạo lại header bằng cách nối chuỗi ID vào URL hoặc truyền URI đã mã hóa qua một API khác lại coi nó là template cần mã hóa tiếp.

## 6. Một path segment có dấu `/` không phải lúc nào cũng dùng được

Về mặt xây URI, dấu `/` thuộc dữ liệu biến có thể được biểu diễn bằng `%2F`. Tuy nhiên, cả chuỗi xử lý request còn có reverse proxy, firewall, servlet container và router. Các thành phần này có thể từ chối encoded slash hoặc xử lý khác nhau.

Ví dụ:

```text
ID nghiệp vụ:  sales/2026
URI tạo ra:    /v1/documents/sales%2F2026
```

Không thể kết luận URI trên sẽ được nhận thành đúng một `documentId` ở mọi môi trường triển khai. Cũng không nên đổi biến thành phép mở rộng cho phép giữ `/` để vượt qua giới hạn, vì lúc đó path đã đổi cấu trúc.

Một số lựa chọn thiết kế:

- Dùng ID ổn định không chứa ký tự phân cách, ví dụ UUID, và lưu tên nghiệp vụ trong thuộc tính resource.
- Nếu `/` thể hiện quan hệ phân cấp thật sự, mô hình hóa quan hệ đó bằng các segment cố định của API.
- Nếu cần tra cứu bằng mã nghiệp vụ chứa `/`, cân nhắc endpoint tìm kiếm với query parameter có hợp đồng rõ ràng.
- Chỉ hỗ trợ encoded slash trong path khi đã xác định hành vi của toàn bộ hạ tầng và có kiểm thử tích hợp tương ứng.

Đối với tên tệp hoặc tiêu đề người dùng đặt, đừng mặc định chúng là định danh path tốt. Tên hiển thị có thể thay đổi, trùng lặp hoặc chứa ký tự mà hạ tầng xử lý không thống nhất.

## 7. Dot segment, Unicode và ranh giới giải mã

### 7.1. Encoding không loại bỏ `.` và `..`

Dấu `.` là ký tự unreserved. Vì vậy, mã hóa chặt một biến không tự biến `..` thành định danh an toàn. Chuỗi `..` có thể mang ý nghĩa đi lên một cấp trong một số bước xử lý path.

Các đầu vào cần xem xét gồm:

```text
..
%2e%2e
%252e%252e
```

Ý nghĩa thực tế phụ thuộc việc component nào giải mã hoặc chuẩn hóa, và thực hiện bao nhiêu lần. Không mặc định thêm một lớp encoding sẽ giải quyết path traversal.

Trong ví dụ `DocumentUris`, hợp đồng tenant ID không cho phép dấu `.`, còn document ID là UUID. Việc giới hạn kiểu định danh giúp tránh đưa chuỗi đường dẫn tùy ý vào path.

Nếu resource đại diện cho tệp, đừng ghép trực tiếp biến từ URI vào đường dẫn filesystem. Nên ánh xạ ID sang bản ghi hoặc đối tượng lưu trữ đã xác định. Khi buộc phải xử lý đường dẫn tệp, cần kiểm soát riêng thư mục gốc, đường dẫn sau chuẩn hóa và tác động của symbolic link; URI builder không thực hiện các việc đó.

### 7.2. Không giải mã lặp lại dữ liệu đã được framework binding

Trong cấu hình thông thường, Spring đã chuyển query parameter từ biểu diễn truyền trên HTTP thành giá trị phục vụ binding. Ví dụ:

```text
Trên request:      q=A%26B%20%2B%20C
Giá trị ứng dụng:  A&B + C
```

Không gọi thêm `URLDecoder.decode(...)` chỉ vì thấy dấu `%` hoặc `+` trong giá trị ứng dụng. Dấu `+` thật có thể bị đổi thành dấu cách; chuỗi `%252F` có thể tiếp tục bị biến đổi qua nhiều lớp.

Với path variable, đặc biệt là encoded separator, cần xác nhận cách container/router đang cấu hình. Không suy từ việc query đã được binding rằng mọi trường hợp mã hóa path đều có cùng hành vi.

Hợp đồng nội bộ nên ghi rõ:

```text
HTTP representation -> một ranh giới parse/decode xác định
                    -> validation dữ liệu đã binding
                    -> xử lý nghiệp vụ
```

### 7.3. Unicode cần chính sách nghiệp vụ riêng

Hai chuỗi Unicode có thể nhìn giống nhau nhưng có biểu diễn code point khác nhau. Percent-encoding không tự đồng nhất các biểu diễn đó và cũng không xác định quy tắc phân biệt chữ hoa/chữ thường của định danh.

Nếu API cho phép slug Unicode, hãy quyết định chính sách chuẩn hóa, so sánh và xử lý xung đột ngay khi tạo resource. Áp dụng cùng chính sách khi lưu và tra cứu. Không tự bỏ dấu tiếng Việt hoặc chuyển chữ thường trong lúc tạo URI nếu hợp đồng chưa quy định.

## 8. Query parameter: optional, lặp và giá trị opaque

### 8.1. Phân biệt vắng mặt và chuỗi rỗng

Ba request sau có thể có ý nghĩa khác nhau:

```text
/documents
/documents?q=
/documents?q=java
```

API cần quy định tham số bị thiếu có nghĩa là không lọc, dùng mặc định hay báo lỗi; `q=` có được chấp nhận hay không. Builder không tự quyết định quy tắc nghiệp vụ này.

Trong `DocumentUris.search(...)`, truy vấn rỗng bị từ chối theo hợp đồng. Nếu muốn hỗ trợ liệt kê không có điều kiện tìm kiếm, có thể tạo phương thức xây URI khác bỏ hẳn `q` khi không được cung cấp. Không đưa chuỗi `"null"` vào query để biểu diễn sự vắng mặt.

### 8.2. Một tên tham số có nhiều giá trị

Nếu hợp đồng dùng query parameter lặp:

```text
/documents?tag=java&tag=spring
```

hãy tạo từng giá trị qua builder. Chẳng hạn, phần xây query có thể dùng:

```java
.queryParam("tag", "{firstTag}", "{secondTag}")
.encode(StandardCharsets.UTF_8)
.buildAndExpand(Map.of(
        "firstTag", "java",
        "secondTag", "spring"))
```

Đây là chuỗi lời gọi tiếp sau phần khởi tạo builder và path. Với giá trị thực tế có dấu `&`, dấu phẩy hoặc Unicode, cơ chế placeholder vẫn giữ chúng trong đúng giá trị.

Không tự ghép danh sách thành `java,spring` nếu API chưa quy định phân tách bằng dấu phẩy. Hợp đồng phải nêu rõ cách biểu diễn danh sách và hành vi đối với giá trị lặp, nhất là khi proxy và backend có thể chọn giá trị khác nhau cho một tham số được lặp ngoài dự kiến.

### 8.3. Cursor và mã opaque vẫn cần encoding

Cursor là dữ liệu mà client không cần hiểu cấu trúc bên trong. Nó có thể chứa `+`, `/` hoặc `=` nếu được tạo bằng một số dạng Base64.

```text
Cursor gốc: abc+/==
```

Không nối thẳng cursor sau `?cursor=`. Truyền nó như một giá trị query để builder mã hóa. Base64url giúp giảm ký tự bất tiện, nhưng không thay thế hợp đồng kiểm tra cursor và không biến cursor thành dữ liệu đáng tin cậy.

Nếu cursor ảnh hưởng đến phạm vi tenant, thứ tự hoặc vị trí đọc dữ liệu, server vẫn cần xác minh tính hợp lệ và gắn nó với ngữ cảnh truy vấn phù hợp. Encoding không chứng minh cursor do server phát hành.

## 9. Liên kết phân trang và hợp đồng resource

Giả sử response trang đầu có các điều kiện:

```text
tenantId = acme
q        = java spring
page     = 0
size     = 20
```

Nếu còn dữ liệu, liên kết tiếp theo cần giữ nguyên tenant và truy vấn, chỉ đổi trang:

```text
https://api.example.com/v1/tenants/acme/documents?q=java%20spring&page=1&size=20
```

Một số quy tắc hữu ích:

- Dùng cùng tầng xây URI cho `self`, `next` và `previous`.
- Lấy các giá trị đã parse và validation theo hợp đồng, sau đó xây URI mới.
- Chỉ giữ các tham số có trong hợp đồng, không sao chép toàn bộ raw query string từ request.
- Không phát hành `next` khi không còn trang tiếp theo; không tạo trang âm cho `previous`.
- Nếu có `sort`, chỉ chấp nhận tên trường và hướng sắp xếp đã cho phép.

Thứ tự query parameter thường không được API coi là thứ tự nghiệp vụ, nhưng hai chuỗi URI khác nhau có thể tạo cache key khác nhau ở một số tầng. Dùng thứ tự xuất ổn định giúp liên kết nhất quán, hỗ trợ kiểm thử và giảm biến thể không cần thiết. Nếu ký request hoặc canonicalize URI, phải có quy tắc riêng về thứ tự, encoding và tham số lặp; đừng suy ra quy tắc chữ ký chỉ từ URI builder.

Không đưa access token, mật khẩu hoặc dữ liệu nhạy cảm không cần thiết vào URI. URI có thể xuất hiện trong log, lịch sử và công cụ giám sát dù request được truyền qua HTTPS.

## 10. Scheme, host và nguồn tạo liên kết

### 10.1. Ưu tiên public origin được quản lý

Ví dụ trong bài dùng origin cố định:

```text
https://api.example.com
```

Trong triển khai thật, origin có thể đến từ cấu hình môi trường. Cấu hình cần được kiểm tra khi khởi động: scheme, host, port và base path có đúng hợp đồng triển khai hay không.

Nếu dịch vụ được public dưới tiền tố `/catalog`, tầng xây URI cần giữ tiền tố đó đúng một lần. Không để mỗi handler tự ghép lại public base URL theo cách riêng.

Một số API chọn trả liên kết tương đối, ví dụ:

```text
/v1/tenants/acme/documents/550e8400-e29b-41d4-a716-446655440000
```

Liên kết tương đối giảm phụ thuộc vào host khi phù hợp với client và hợp đồng API. Nếu dùng liên kết tuyệt đối, host và scheme phải phản ánh đúng địa chỉ public đã kiểm soát.

### 10.2. Không tin mù quáng `Host` và forwarded header

Khi đứng sau reverse proxy, ứng dụng có thể thấy địa chỉ nội bộ. Header như `Forwarded` hoặc `X-Forwarded-*` giúp truyền thông tin public origin, nhưng chỉ đáng tin khi do proxy tin cậy thiết lập và được xử lý theo cấu hình đúng.

Nếu lấy trực tiếp `Host` hoặc `X-Forwarded-Host` do client tùy ý gửi để tạo `Location`, liên kết API có thể trỏ đến host ngoài ý muốn. Đây là lỗi chọn nguồn cho authority.

Giải pháp cần nằm ở cấu hình public origin hoặc chuỗi proxy tin cậy. Builder chỉ ghép các thành phần được cấp cho nó, không biết host nào thuộc hệ thống của bạn.

## 11. URI hợp lệ không đồng nghĩa với đích đến được phép

### 11.1. `URI.create()` chỉ giải quyết việc phân tích cú pháp

```java
URI target = URI.create(userProvidedValue);
```

Việc tạo được đối tượng `URI` không chứng minh rằng:

- URI là tuyệt đối hoặc dùng HTTPS.
- Host thuộc miền đã cho phép.
- Đích đến không phải dịch vụ nội bộ.
- Người dùng được phép chuyển hướng tới địa chỉ đó.
- Server được phép gửi request tới đó.

`URI.normalize()` cũng không phải chính sách an toàn mạng hoặc phân quyền. Nó không xác minh quyền sở hữu host và không giải quyết toàn bộ khác biệt diễn giải URI giữa các tầng.

### 11.2. `resolve()` không giới hạn đích đến trong base URI

Ví dụ:

```java
URI base = URI.create("https://api.example.com/v1/");
URI target = base.resolve("//outside.example/documents");
```

Kết quả dùng host `outside.example`. URI tuyệt đối được truyền cho `resolve()` cũng có thể thay thế base.

Vì vậy, đừng nhận chuỗi tùy ý từ người dùng rồi gọi `base.resolve(input)` với giả định đích đến luôn nằm dưới `/v1/`. Nếu nghiệp vụ chỉ cần document ID thì hãy nhận document ID, validation nó và mở rộng template cố định.

Dấu `/` cuối base cũng có ý nghĩa khi giải quyết đường dẫn tương đối: base kết thúc bằng `/v1/` khác với base kết thúc bằng `/v1`. Khi cần cấu trúc cố định, builder với path template thường dễ kiểm soát hơn việc suy luận qua nhiều lần resolve.

### 11.3. Chuyển hướng và request phía server cần chính sách riêng

Nếu ứng dụng nhận `returnUrl`, nên giới hạn nó theo hợp đồng chuyển hướng, chẳng hạn đường dẫn nội bộ đã cho phép. Việc cho phép URI tuyệt đối đòi hỏi kiểm tra scheme, host và port bằng cấu trúc đã parse; không dùng kiểm tra tiền tố chuỗi như `startsWith("https://trusted.example")`.

Nếu server dùng URI do người dùng ảnh hưởng để gọi HTTP, nguy cơ còn gồm SSRF. Ngoài validation cú pháp và allowlist đích, cần kiểm soát redirect, kết quả phân giải DNS, địa chỉ mạng thực sự được kết nối và chính sách outbound. Host ban đầu được cho phép không bảo đảm mọi đích sau redirect cũng được phép.

Trong cả hai tình huống, percent-encoding không thay thế chính sách đích đến. Thiết kế an toàn hơn thường là nhận khóa nghiệp vụ rồi ánh xạ sang endpoint được cấu hình, thay vì cho client điều khiển toàn bộ URL.

## 12. Mô tả hợp đồng URI bằng OpenAPI

Trong OpenAPI, path template khai báo placeholder bằng tên trong dấu `{}`. Mỗi placeholder phải có khai báo path parameter tương ứng và path parameter phải là bắt buộc.

```yaml
openapi: 3.0.3
info:
  title: Tenant Document API
  version: 1.0.0
servers:
  - url: https://api.example.com
paths:
  /v1/tenants/{tenantId}/documents/{documentId}:
    get:
      summary: Đọc một tài liệu trong tenant
      parameters:
        - name: tenantId
          in: path
          required: true
          schema:
            type: string
            pattern: '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'
        - name: documentId
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Đọc tài liệu thành công
        '400':
          description: Định danh không đúng hợp đồng
        '404':
          description: Không tìm thấy tài liệu trong phạm vi truy cập
```

Đoạn đặc tả tối thiểu này minh họa hợp đồng path; API hoàn chỉnh còn cần response schema, error schema và mô tả xác thực/phân quyền phù hợp.

Đối với endpoint tìm kiếm, query parameter được khai báo riêng bằng `in: query`; không đưa chuỗi `?q={q}` vào khóa path. Với danh sách, cần mô tả cách serialize tương ứng như `style` và `explode`, để client generator và server thống nhất dạng `tag=java&tag=spring` hay dạng khác.

Không giả định path template của OpenAPI hỗ trợ mọi toán tử RFC 6570. Template trong tài liệu, builder tạo liên kết và route nhận request phải có cùng hợp đồng resource, nhưng cú pháp và mức hỗ trợ của chúng cần được xét riêng.

Schema như `format: uuid` mô tả hợp đồng. Việc framework hoặc validator có thực sự cưỡng chế kiểm tra nó cần được cấu hình và xác minh trong ứng dụng; tài liệu không tự thực thi validation.

## 13. Ma trận tình huống cần kiểm thử khi triển khai

Bảng dưới đây là các trường hợp để thiết kế kiểm thử cho tầng xây URI và cho đường đi qua hạ tầng. Nó không phải khẳng định rằng ví dụ đã được chạy trong mọi cấu hình Spring hoặc proxy.

| Tình huống | Kết quả cần kiểm tra |
|---|---|
| Tenant `acme`, document UUID hợp lệ | Path có đúng cấu trúc resource đã công bố |
| Tenant chứa `/`, `..` hoặc khoảng trắng | Bị từ chối theo hợp đồng tenant ID của ví dụ |
| `q = A&B` | URI có `q=A%26B`; không xuất hiện parameter `B` |
| `q = A+B` | URI có `q=A%2BB`; khi binding nhận lại dấu cộng thật |
| `q = java spring` | URI dùng `%20`; ứng dụng nhận đúng dấu cách |
| `q` có tiếng Việt | Byte UTF-8 được mã hóa và dữ liệu nhận lại đúng |
| `q = A%2FB` là dữ liệu gốc | URI chứa `A%252FB`; sau một lần giải mã vẫn là `A%2FB` |
| Cursor có `+`, `/`, `=` | Tất cả vẫn thuộc đúng một giá trị cursor |
| `page < 0`, `size = 0` hoặc `size > 100` | Bị từ chối trước khi tạo liên kết |
| Tham số query được lặp ngoài hợp đồng | Có chính sách từ chối hoặc diễn giải nhất quán |
| Dữ liệu có encoded slash trong path | Xác nhận hành vi của proxy, container và router nếu API hỗ trợ |
| Host hoặc forwarded header bị thay đổi | Liên kết đầu ra vẫn tuân theo nguồn origin được tin cậy |
| Trang cuối của tập kết quả | Không có liên kết `next` gây hiểu nhầm |

Với kiểm thử đơn vị, nên kiểm tra thành phần URI và giá trị mong đợi theo hợp đồng. Không cố định thứ tự lặp của map tùy ý nếu builder không cam kết thứ tự đó. Nếu API chủ động công bố biểu diễn URI ổn định, kiểm tra thêm chuỗi đầu ra đúng quy tắc đã chọn.

Với kiểm thử tích hợp, gửi request qua cùng loại proxy/container dự kiến triển khai để phát hiện khác biệt parse và decode. Phép kiểm thử chỉ tạo `URI` trong JVM chưa bao phủ đường đi của request đến controller.

Phân quyền cần kiểm thử riêng. Chẳng hạn, tài liệu có ID hợp lệ thuộc tenant khác vẫn phải bị ngăn truy cập, dù URI được tạo và giải mã hoàn toàn đúng.

## 14. Bài tập thực hành

### Bài tập 1: Tìm lỗi ranh giới dữ liệu

Xét đoạn mã:

```java
String uri = "/v1/tenants/" + tenantId
        + "/documents?q=" + query;
```

Với `tenantId = acme` và `query = java&size=500`, hãy giải thích vì sao query đã thay đổi cấu trúc request. Sau đó viết lại bằng template cố định, query placeholder và encoding khi mở rộng biến.

Kết quả cần đạt: phần dữ liệu `java&size=500` nằm trong một giá trị `q`, được biểu diễn là `java%26size%3D500` khi mã hóa chặt biến; không có parameter `size` mới do đầu vào tạo ra.

### Bài tập 2: Thiết kế hợp đồng định danh

Một hệ thống đang dùng tên tài liệu `Báo cáo/2026` làm `documentId` trong path. Hãy đề xuất hợp đồng thay thế sao cho tên hiển thị vẫn giữ nguyên và liên kết đến resource ổn định.

Một hướng giải quyết là cấp UUID cho resource, đưa UUID vào path và giữ tên tiếng Việt trong response body. Nếu cần tra cứu bằng tên, bổ sung tiêu chí tìm kiếm có query parameter được mã hóa đúng.

### Bài tập 3: Tạo liên kết trang tiếp theo

Từ `tenantId = acme`, `q = REST + HTTP`, `page = 2`, `size = 20`, tạo `next` khi còn dữ liệu. Xác định rõ API dùng số trang bắt đầu từ `0` hay `1`.

Theo hợp đồng của ví dụ, URI cần trỏ tới `page=3`, giữ nguyên `size=20` và biểu diễn truy vấn bằng `q=REST%20%2B%20HTTP`.

### Bài tập 4: Xác định trách nhiệm từng lớp

Một lập trình viên nói: “Đã dùng URI builder thì không cần kiểm tra tenant và host nữa”. Hãy chỉ ra ba kiểm tra vẫn còn cần thiết.

Gợi ý trả lời:

- Tenant ID phải đúng hợp đồng dữ liệu.
- Người gọi phải được phép truy cập tenant và tài liệu đích.
- Host, scheme và chính sách đích đến phải phù hợp với loại liên kết hoặc request mà hệ thống đang tạo.

## 15. Tự kiểm tra trước khi áp dụng

1. Template và tên parameter có do code hoặc cấu hình tin cậy quản lý không?
2. Mỗi biến có kiểu dữ liệu, giới hạn độ dài và miền giá trị rõ ràng không?
3. Giá trị đưa vào builder có còn là dữ liệu chưa percent-encode không?
4. Encoding có được thực hiện đúng một lần, theo vị trí path hoặc query không?
5. Dấu `+`, `%`, `/`, `&`, `#` và tiếng Việt có được giữ đúng nghĩa khi round-trip không?
6. Nguồn public origin và forwarded header có được kiểm soát không?
7. Liên kết phân trang có giữ đúng điều kiện và phạm vi tenant không?
8. Route, OpenAPI và tầng xây URI có thống nhất hợp đồng không?
9. Validation, phân quyền và chính sách gọi endpoint có được thực hiện ở các lớp tương ứng không?

Một URI template tốt giúp cấu trúc resource rõ ràng. Một tầng xây URI tốt giữ dữ liệu đúng vị trí trong cấu trúc đó. Khi kết hợp validation, encoding có chủ đích và kiểm soát origin, API có thể phát hành liên kết ổn định, dễ kiểm thử và phù hợp với hợp đồng đã công bố.
