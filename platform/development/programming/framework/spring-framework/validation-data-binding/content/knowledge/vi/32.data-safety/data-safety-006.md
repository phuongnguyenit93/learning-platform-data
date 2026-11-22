# Giới hạn độ lớn đầu vào và chi phí biểu thức chính quy trong Spring Framework

Một API có thể kiểm tra `@NotBlank`, `@Size`, `@Pattern` rất đúng về mặt nghiệp vụ nhưng vẫn bị quá tải nếu nó **nhận một request quá lớn**, **tạo object graph không cần thiết** hoặc **chạy regex có độ phức tạp xấu trên dữ liệu không đáng tin**. Ba vấn đề này khác nhau và phải được giải quyết ở nhiều lớp:

1. **Độ lớn dữ liệu truyền qua HTTP:** số byte của body, header, URL, số form parameters, số multipart parts và số lượng request đồng thời.
2. **Độ lớn object sau khi decode/binding:** chiều dài `String`, kích thước `List`/`Map`, độ sâu JSON, nested property path và lượng bộ nhớ dùng để tạo DTO.
3. **Chi phí kiểm tra dữ liệu:** regex backtracking, số phép so khớp, số lần compile pattern, logic custom validator và các truy vấn I/O trong validation.

Trong **Spring Framework**, Bean Validation là tuyến bảo vệ **ngữ nghĩa sau khi dữ liệu đã được đọc/giải mã**, không phải một giới hạn byte toàn cục của HTTP server. Đặc biệt, `@Size(max = 128)` giúp phát hiện chuỗi dài quá 128 đơn vị độ dài Java, nhưng **không ngăn** server, JSON decoder hoặc application framework đã phải tiếp nhận dữ liệu trước khi validator chạy.

Bài Knowledge này thuộc nhóm **An toàn dữ liệu** của module **Spring Framework — validation-data-binding**. Nội dung trình bày mô hình đe dọa, các tầng giới hạn request, `@Size`, `@Pattern` và ReDoS, điểm mở rộng Spring MVC, thiết kế regex an toàn, ví dụ **Java 17+ / Spring Boot 3.5.x / Spring Framework 6.2.x**, kiểm thử, quan sát và những lỗi cấu hình phổ biến.

## 1. Mô hình đe dọa: dữ liệu nhỏ vẫn có thể tốn CPU

Xét một dịch vụ tạo nhãn tài nguyên:

~~~http
POST /api/labels HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{"label":"invoice_2026-11"}
~~~

Bài toán hợp lệ: label dài từ 1 đến 128, chỉ cho chữ cái ASCII, chữ số, dấu gạch dưới và gạch nối. Một thiết kế thiếu bảo vệ có thể mắc nhiều lỗi:

- Cho phép body JSON hàng chục MB trước khi kiểm tra `@Size(max=128)`.
- Chấp nhận một field `label` nhỏ nhưng đồng thời có hàng trăm ngàn phần tử trong field `tags`; deserializer phải cấp phát nhiều object.
- Dùng một regex có **nested repetition** như `(a+)+$`; khi input gần khớp nhưng thất bại ở cuối, Java regex engine có thể thử rất nhiều cách phân chia cùng đoạn `a...a`.
- Compile regex mới cho mỗi request thay vì tái sử dụng một `Pattern` immutable.
- Thực hiện phép match nhiều lần trong logging, DTO validation, service policy và persistence.
- Dùng `Matcher.find()` tìm toàn input khi thực tế yêu cầu match **toàn bộ** giá trị.
- Cố “cứu” một regex nguy hiểm bằng timeout HTTP, dù CPU có thể tiếp tục bị tiêu thụ trong regex engine.

**ReDoS (Regular Expression Denial of Service)** là kiểu từ chối dịch vụ dựa vào chi phí thực thi regex. Nó không yêu cầu client gửi input quá lớn: một biểu thức thiếu an toàn có thể tiêu tốn CPU với chuỗi tương đối ngắn, đặc biệt khi có các nhánh backtracking chồng nhau.

### Một biểu thức minh họa cần tránh

~~~regex
(a+)+$
~~~

Đây là **phản ví dụ**, không sử dụng nó để validate input thực tế. Nếu chuỗi chứa nhiều ký tự `a` rồi kết thúc bằng `!`, engine backtracking có thể xét nhiều cách phân đoạn `a` trước khi kết luận không match. Không chạy benchmark với input tăng vô hạn trên hệ thống thật; việc tự stress-test regex nguy hiểm trong web server đang phục vụ request cũng có thể gây gián đoạn.

Thay vì cố sửa bằng cách tăng timeout, hãy **loại bỏ cấu trúc mơ hồ**. Với định dạng nhãn cụ thể ở trên, có thể dùng một character class rõ ràng và độ dài hữu hạn:

~~~regex
\A[A-Za-z0-9_-]{1,128}\z
~~~

Không có nested ambiguous alternatives, không có backreference, có giới hạn số ký tự. `\A` và `\z` là anchor đầu/cuối **toàn bộ input** trong Java regex; không nhầm `\z` với `\Z` khi dữ liệu có newline cuối.

## 2. Giới hạn nào bảo vệ tài nguyên nào?

| Lớp | Đại lượng phải giới hạn | Công cụ/điểm kiểm soát | Nếu chỉ dùng `@Size` thì sao? |
|---|---|---|---|
| Reverse proxy / API gateway | Body bytes, URL/header size, tốc độ gửi, concurrency | Ingress, proxy body cap, rate limit | Request lớn có thể đã tới ứng dụng |
| Servlet container | Request line/headers, số parameters, form body, multipart parts | Cấu hình Tomcat/Jetty/Undertow | Container vẫn phân tích nhiều dữ liệu |
| HTTP multipart | File bytes và tổng multipart bytes | `spring.servlet.multipart.*` | File upload không bị giới hạn bởi `@Size` của DTO |
| JSON decoder | Chuỗi JSON, độ sâu nesting, số phần tử, số bytes | Jackson stream constraints, giới hạn ingress/body | JSON có thể được tạo thành graph lớn trước validation |
| Spring WebDataBinder | Nested object/collection growth, property allowlist | `setAutoGrowCollectionLimit`, `setAllowedFields` | Form indices có thể làm binder grow nếu policy cho phép |
| DTO constraint | Chiều dài chuỗi, số phần tử, miền giá trị | `@Size`, `@NotBlank`, `@Max`, custom constraint | Có kiểm tra hậu decode, nhưng không thay giới hạn transport |
| Regex engine | Số trạng thái/backtracking, scan length | Regex đơn giản, pre-gate, finite quantifier | `@Pattern` nguy hiểm vẫn có thể đốt CPU |
| Service/domain | Truy vấn, batch size, số object xử lý | Limit nghiệp vụ, pagination, budget, concurrency | Validator DTO không kiểm soát DB hoặc downstream |
| Observability | Số lỗi 400/413, request duration, CPU/timeouts | Metrics, traces, alerts có giới hạn cardinality | Không thấy được tấn công hoặc lỗi cấu hình |

**Thứ tự quan trọng:** chặn bytes càng sớm càng tốt; giới hạn parser/binder trước khi tạo cấu trúc quá lớn; kiểm tra giá trị có giới hạn trước regex phức tạp; sau cùng mới làm nghiệp vụ tốn kém. Trong một hệ thống production, các tầng này nên bổ sung nhau thay vì phụ thuộc một annotation duy nhất.

## 3. Độ dài String, số byte, code point và ký tự người dùng nhìn thấy

Một yêu cầu “tối đa 128 ký tự” có thể có ít nhất bốn nghĩa:

1. **Byte UTF-8** trên dây truyền: liên quan bandwidth, proxy, storage bytes.
2. **UTF-16 code units** của Java: `String.length()`.
3. **Unicode code points**: `String.codePointCount(0, value.length())`.
4. **Grapheme clusters**: những cụm glyph người dùng nhìn thấy; có thể gồm nhiều code points.

Ví dụ một emoji phổ biến:

~~~java
String emoji = "😀";
int units = emoji.length();                     // 2
int points = emoji.codePointCount(0, units);   // 1
int bytes = emoji.getBytes(
    java.nio.charset.StandardCharsets.UTF_8).length; // 4
~~~

Đoạn trên là Java snippet, không cần Spring. Vì UTF-16 biểu diễn emoji bằng surrogate pair, `String.length()` là **2**, số Unicode code points là **1**, và UTF-8 cần **4 bytes**.

Một dấu tiếng Việt có thể được biểu diễn bằng precomposed code point hoặc kết hợp base letter + combining mark; số code points/Java length không nhất thiết trùng số glyph người đọc thấy. Nếu business requirement thực sự tính *grapheme clusters*, hãy định nghĩa và kiểm thử cách đếm bằng thư viện/cơ chế Unicode phù hợp. Đừng tự tuyên bố `@Size(max=128)` là giới hạn 128 graphemes.

### `@Size` tính độ dài theo loại dữ liệu

Jakarta Bean Validation `@Size` áp dụng cho các kiểu được hỗ trợ, như:

- `CharSequence`: kích thước/độ dài theo cách provider triển khai cho chuỗi (với Hibernate Validator trên `String`, dựa trên Java length).
- `Collection`: số phần tử.
- `Map`: số entries.
- Array: số elements.

Không dùng `@Size` cho một `int` để giới hạn giá trị số; với số nguyên dùng `@Min`/`@Max`, với BigDecimal dùng `@DecimalMin`/`@DecimalMax` hoặc rule nghiệp vụ khác.

**Không nhầm:** `@Size(max=128)` trên `String` **không giới hạn 128 UTF-8 bytes**. Với nhãn chỉ chấp nhận ASCII, một ký tự hợp lệ = một byte UTF-8, nhưng khi cho Unicode tự do thì các đại lượng khác nhau rõ rệt.

## 4. Spring MVC và điểm áp giới hạn đầu vào

Trong Spring MVC Servlet, một request JSON cơ bản đi qua:

~~~text
Client
  |
  v
Ingress / proxy (giới hạn bytes và tốc độ)
  |
  v
Servlet container: request line, headers, body
  |
  +-- form URL-encoded: container parameter parsing
  +-- multipart: multipart resolver/servlet parts
  |
  v
DispatcherServlet
  |
  v
HandlerMethodArgumentResolver
  |
  +-- @RequestBody: HttpMessageConverter/Jackson
  |       +-- parse JSON -> DTO
  |
  +-- @ModelAttribute: WebDataBinder
  |       +-- form/query parameter binding
  |
  v
@Valid / @Validated (nếu kích hoạt)
  |
  +-- @Size / @Pattern / custom validators
  |
  v
Controller/service
~~~

Đối với `@RequestBody`, **Jackson/`HttpMessageConverter` đọc JSON trước khi Bean Validation đánh giá DTO**. Nếu JSON rất lớn, `@Size` đến quá muộn để bảo vệ băng thông/decoder.

Đối với `@ModelAttribute`, `WebDataBinder` có thể tạo nested objects và collections theo request parameters. `DataBinder.setAutoGrowCollectionLimit(...)` cùng `setAllowedFields(...)` hỗ trợ giới hạn khối lượng công việc và quyền property binding.

**Đừng nhầm MVC với WebFlux**: WebFlux dùng `HttpMessageReader`/reactive codecs, có `maxInMemorySize` liên quan buffering nhưng semantics và điểm cấu hình không giống Servlet MVC. Với bài thực hành, ta chọn rõ Spring MVC và embedded Tomcat.

## 5. Cấu hình Spring Boot 3.5: các giới hạn có thật và phạm vi của chúng

Ví dụ trong `src/main/resources/application.properties`:

~~~properties
# HTTP request headers: không phải body cap.
server.max-http-request-header-size=8KB

# Embedded Tomcat: giới hạn kích thước FORM POST.
server.tomcat.max-http-form-post-size=16KB

# Số GET/POST parameters mà Tomcat tự parse.
server.tomcat.max-parameter-count=128

# Multipart: giới hạn từng file và tổng request multipart.
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=4MB
~~~

Các properties trên tồn tại trong Spring Boot 3.5, nhưng **mỗi property có phạm vi riêng**:

- `server.max-http-request-header-size` giới hạn **headers**, không phải JSON body.
- `server.tomcat.max-http-form-post-size` là giới hạn **form content** khi Tomcat xử lý HTTP POST form; **không được quảng bá như JSON request-body limit phổ quát**.
- `server.tomcat.max-parameter-count` giới hạn số parameters mà Tomcat tự parse (query và POST form theo container), không giới hạn các phần tử trong JSON array.
- `spring.servlet.multipart.max-file-size` giới hạn **mỗi file** trong multipart upload.
- `spring.servlet.multipart.max-request-size` giới hạn **tổng multipart request**.
- Các giá trị ví dụ 8KB/16KB/128/2MB/4MB là **chính sách của demo**, không phải mức mặc định hay con số phù hợp cho mọi hệ thống.

Nếu ứng dụng chạy Jetty, Undertow hoặc Tomcat standalone/proxy khác, phải dùng các tùy chọn đúng server. Ví dụ `server.tomcat.*` chỉ có nghĩa với embedded Tomcat.

### Giới hạn JSON body cần đặt ở đâu?

Với JSON API, hãy đặt **max request body bytes** tại ingress/proxy/API gateway hoặc một lớp **streaming byte-counting thực sự** trước JSON decoder. Ví dụ triển khai reverse proxy **NGINX**:

~~~nginx
server {
    listen 8088;

    # Giới hạn byte body của request đi qua server này.
    client_max_body_size 8k;

    location / {
        proxy_pass http://127.0.0.1:8080;
    }
}
~~~

Đây là **một cấu hình NGINX minh họa**, không phải file của dự án Spring Boot demo. Nếu chạy NGINX thực tế, cần thêm cấu hình production như TLS, logging, upstream health checks và headers theo môi trường. Request có body vượt limit thường được proxy từ chối với **HTTP 413 Content Too Large/Payload Too Large**, có thể **không đi vào controller và `@ControllerAdvice` của Spring**.

**Quan trọng:** các phép thử `MockMvc` chạy trực tiếp trong Spring test context, **không đi qua NGINX**. Muốn chứng minh body-byte cap của proxy, phải có **integration/system test đi qua ingress thật**, không chỉ `MockMvc`.

### Có nên chỉ kiểm tra Content-Length?

Không. `Content-Length` có thể không hiện diện (chunked transfer encoding hoặc HTTP/2 framing khác), có thể không đại diện chính xác cho lượng dữ liệu sau một số lớp xử lý, và không thay giới hạn stream đọc thực tế. Một check `request.getContentLengthLong() > limit` chỉ là **fast reject có điều kiện**, không phải enforcement đầy đủ. Giới hạn an toàn phải đếm bytes được đọc hoặc được server/gateway áp ngay trên luồng request.

## 6. JSON decoder: chiều dài chuỗi, độ sâu và số phần tử

Một JSON object có field `label` ngắn vẫn có thể quá lớn nếu chứa:

~~~json
{
  "label": "OK",
  "items": [
    {"nested": {"value": "x"}}
  ]
}
~~~

Đây chỉ là JSON nhỏ minh họa cấu trúc; rủi ro xuất hiện khi array hoặc nested graph lớn bất thường. Giới hạn cần đánh giá:

- **Document bytes**: toàn bộ input JSON.
- **String token length**: kích thước từng string token.
- **Nesting depth**: độ sâu object/array để tránh đệ quy/tốn stack.
- **Number token length**: số có quá nhiều chữ số.
- **Collection item count**: số phần tử sau decode, cần contract và giới hạn riêng.
- **Object property count**: số keys trên object/map nếu schema linh hoạt.
- **Duplicate keys, unknown properties**: quyết định reject hay bỏ qua theo security policy.

Jackson Core cung cấp **`StreamReadConstraints`** để cấu hình một số parser limits như maximum string length, number length và nesting depth. Khi tích hợp Jackson với Spring Boot, cần đảm bảo cấu hình áp vào **`ObjectMapper/JsonFactory` thực sự được `MappingJackson2HttpMessageConverter` dùng**. Một `new ObjectMapper()` tạo riêng trong service không tự thay mapper của MVC.

**Không dùng một parser limit để chứng minh đã giới hạn tất cả array elements hay HTTP bytes.** Mỗi Jackson constraint có mục tiêu khác nhau; số items trong collection và toàn request body có thể cần limit ở tầng khác.

### Độ lớn sau decode có thể khác byte trên dây

JSON có escape sequences, metadata và nested structure. Dữ liệu sau decode có thể chiếm nhiều bộ nhớ hơn kích thước nén hoặc wire representation; đặc biệt nếu request bị nén hoặc chứa cấu trúc nhiều objects. Khi có request decompression, kiểm tra cả giới hạn **trước** và **sau** giải nén để giảm rủi ro decompression bomb.

Không bao giờ đặt toàn bộ trust vào số bytes của request do client tự khai báo.

## 7. WebDataBinder và collection growth

Với form/query binding:

~~~http
POST /orders HTTP/1.1
Content-Type: application/x-www-form-urlencoded

items[0].code=A&items[500].code=B
~~~

nếu binder cho phép auto-grow collection và model có cấu trúc phù hợp, một index lớn có thể khiến framework phải cấp phát nhiều phần tử/trạng thái để bind. Spring `DataBinder` có:

~~~java
binder.setAutoGrowCollectionLimit(64);
binder.setAllowedFields("customer", "items[*].code");
~~~

Đây là **snippet trong `@InitBinder`**, không phải một handler hoàn chỉnh. `setAutoGrowCollectionLimit(64)` giới hạn mức tăng tự động của collection trong binding, nhưng **không** thay thế giới hạn toàn bộ HTTP body, số form parameters hoặc số collection elements mà code nghiệp vụ tự thêm.

Một ví dụ controller-scoped:

~~~java
@InitBinder("orderForm")
void configureOrderBinder(WebDataBinder binder) {
    binder.setAutoGrowCollectionLimit(64);
    binder.setAllowedFields("customer", "items[*].code");
}
~~~

Cần imports `@InitBinder` và `WebDataBinder` khi dùng; chỉ áp dụng cho attribute tên `orderForm`. Mọi allowed-field pattern phải được kiểm tra theo chính sách Spring binder thực tế; đừng cấp quyền setter cho toàn bộ entity khi chỉ muốn vài trường.

### Vì sao không bind trực tiếp JPA entity?

Một object có nhiều writable fields như `role`, `price`, `ownerId` hoặc `admin` có thể bị **mass assignment** khi client gửi những property names không xuất hiện trong UI. Dùng DTO dành riêng cho request và allowlist rõ, ưu tiên constructor binding/declarative binding phù hợp. Giới hạn kích thước là **một lớp** của bảo vệ dữ liệu, không thay thế kiểm soát những fields được phép bind.

### Validation list với `@Size`

~~~java
public record OrderRequest(
    @Size(max = 64)
    List<@Valid OrderItem> items) {
}
~~~

Đây là snippet cần định nghĩa `OrderItem` và Jakarta imports. `@Size(max=64)` kiểm tra số phần tử sau khi collection đã được tạo; nó **không tự giới hạn parser hay request body** trước khi decode. Với endpoint có collections lớn, nên đặt quota trên body bytes/streaming parser và yêu cầu nghiệp vụ một cách rõ ràng.

## 8. Regex Java: vì sao backtracking trở thành chi phí lớn?

`java.util.regex.Pattern` là regex engine có khả năng backtracking. Nó hỗ trợ capturing groups, lookarounds, backreferences, greedy/lazy/possessive quantifiers và atomic groups. Sự linh hoạt này làm một số biểu thức có thể có thời gian thực thi rất lớn trên input được chọn đặc biệt.

### Một mẫu lồng lượng tử nguy hiểm

~~~regex
(a+)+$
~~~

Có hai lần lượng tử lồng nhau: `a+` ở bên trong và `(...)+` bên ngoài. Khi input là nhiều `a` rồi một ký tự không hợp lệ ở cuối, engine có thể thử rất nhiều cách chia cùng dãy ký tự thành các nhóm trước khi từ chối.

Đây là **mẫu để phân tích cấu trúc**, không đưa vào demo benchmark hoặc validator thực. Một test hiệu năng trên regex này với input dài có thể chiếm CPU mà không cung cấp kết quả ổn định giữa JDK/máy.

### Các mẫu khác cần review kỹ

- Nested quantifiers: `(x+)+`, `(x*)*`.
- Các alternatives có vùng match chồng nhau dưới quantifier: ví dụ những nhánh cùng nhận chuỗi `a` lặp lại.
- Pattern có nhiều `.*`/`.+` và backreferences làm số tổ hợp tăng.
- Regex sử dụng `find()` cho một chuỗi dài, trong khi không cần substring search.
- Regex được người dùng cung cấp hoặc được ghép động từ dữ liệu request mà không quote/lọc đúng.

**Không phải mọi `.*` đều nguy hiểm, và không phải mọi regex có lookahead đều ReDoS.** Rủi ro nằm ở tổ hợp của pattern, loại input, vị trí thất bại, engine và việc có thể kiểm soát độ dài/khối lượng công việc. Review cần tập trung vào đường match xấu nhất chứ không chỉ đọc số lượng ký tự trong regex.

### Lazy quantifiers không tự giải quyết ReDoS

Đổi `+` thành `+?` (reluctant/lazy) thay đổi thứ tự thử nhánh, **không đảm bảo** loại bỏ exponential backtracking. Đánh giá ngữ nghĩa và độ phức tạp chứ đừng áp một mẹo cú pháp máy móc.

### Possessive và atomic grouping

Java hỗ trợ:

~~~regex
a++
(?>a+)
~~~

`a++` là **possessive quantifier**, còn `(?>...)` là **atomic group**. Chúng hạn chế backtracking vào phần đã match, có thể giảm rủi ro với những pattern phù hợp. Nhưng chúng cũng có thể **thay đổi ngôn ngữ được chấp nhận**, vì engine không trả lại ký tự cho những phần regex phía sau.

**Ví dụ minh họa khác biệt:**

~~~regex
a+a
a++a
~~~

Với input `aa`, `a+a` có thể match bằng cách cho `a+` nhận một ký tự rồi ký tự `a` cuối nhận ký tự còn lại. `a++a` không match vì `a++` sở hữu toàn bộ các ký tự `a` mà không trả lại. Đừng “chữa” mọi regex bằng dấu `+` mà không chạy lại semantic tests.

### Ưu tiên validate theo cấu trúc đơn giản

Nếu yêu cầu chỉ là nhãn ASCII có một character class và độ dài giới hạn:

~~~regex
\A[A-Za-z0-9_-]{1,128}\z
~~~

Đây là cách rõ hơn nhiều so với cố dùng email/URL/ID regex khổng lồ có hàng loạt nhánh chồng nhau. Với email/URL, ưu tiên library/parser đã được bảo trì, validation cơ bản và rule nghiệp vụ, không tự sao chép một pattern RFC phức tạp từ nguồn không rõ độ an toàn.

## 9. `Pattern` và `Matcher`: API và vòng đời

Cấu trúc dùng `java.util.regex`:

~~~java
private static final Pattern SAFE_LABEL =
    Pattern.compile("\\A[A-Za-z0-9_-]{1,128}\\z");

boolean valid = SAFE_LABEL.matcher(input).matches();
~~~

Đây là snippet trong class có biến `input`, cần `import java.util.regex.Pattern;`.

Những điểm chính:

- **`Pattern` đã compile là immutable**, có thể dùng chung giữa requests/threads.
- **`Matcher` mutable, không thread-safe**, tạo mới từ `pattern.matcher(value)` cho mỗi phép match.
- `Matcher.matches()` yêu cầu **toàn bộ input** khớp regex, phù hợp kiểm tra định dạng của một field.
- `Matcher.find()` chỉ cần tìm **một đoạn con** khớp, không phù hợp nếu rule muốn kiểm tra toàn bộ giá trị.
- `String.matches(regex)` compile pattern mới theo đường triển khai API, không nên dùng lặp lại ở hot path nếu regex cố định và throughput cao.
- Trong Java string literal, regex `\A` phải ghi thành `"\\A"` vì Java dùng backslash làm ký tự escape. Cùng nguyên tắc áp dụng cho `\z`, `\d`, `\s`, v.v.

### Trình tự kiểm tra tối ưu cho một field

~~~java
boolean acceptable(String value) {
    if (value == null || value.isEmpty()) {
        return false;
    }
    if (value.length() > 128) {
        return false; // Trả trước khi gọi regex.
    }
    return SAFE_LABEL.matcher(value).matches();
}
~~~

Đây là snippet trong một class có `SAFE_LABEL`. Việc kiểm tra `length` trước khi match giúp đảm bảo **phép match này** chỉ nhận chuỗi có độ dài tối đa 128 đơn vị Java UTF-16.

**Nhưng** đoạn này chỉ chạy khi ứng dụng **đã có String**. Nó không giới hạn JSON bytes hoặc tài nguyên đã được dùng để decode. Và nếu DTO cũng có `@Pattern` trong Bean Validation, các constraint annotations **không được cam kết chạy theo thứ tự khai báo**, nên đừng nói `@Size` chắc chắn chạy trước `@Pattern`. Nếu pattern nguy hiểm, phải sửa pattern hoặc thiết kế validation group sequence/explicit ordered validation thật sự, không trông chờ `@Size` đứng ở dòng trên.

### Có timeout trực tiếp cho `java.util.regex.Pattern` không?

Trong Java 17, `Pattern`/`Matcher` không có một API **time budget per match** tích hợp để bảo đảm regex luôn kết thúc sau N mili-giây. Chạy match trong `Future` rồi gọi `future.cancel(true)` không phải lớp bảo vệ đủ tin cậy nếu regex đang bận CPU và không phản hồi interruption đúng như mong muốn. Thread bị chiếm vẫn có thể tiếp tục làm hệ thống cạn tài nguyên.

Chiến lược ưu tiên:

1. **Viết lại pattern với chi phí có thể dự đoán**.
2. **Giới hạn input trước khi thực hiện match**.
3. **Giới hạn concurrency/rate** ở boundary.
4. **Đánh giá alternative regex engines** có bảo đảm tuyến tính khi cần (ví dụ RE2/J) và đối chiếu những tính năng regex được hỗ trợ; đây là thay đổi engine/API có chủ đích, không phải drop-in replacement cho mọi Java regex.
5. Quan sát CPU p95/p99, số request bị từ chối và thời gian validation.

Đừng quảng cáo HTTP timeout hoặc cancellation như một giải pháp hoàn chỉnh cho ReDoS.

## 10. Jakarta Bean Validation: `@NotBlank`, `@Size`, `@Pattern`

Một DTO Spring Boot 3 dùng:

~~~java
public record LabelInput(
    @NotBlank
    @Size(max = 128)
    @Pattern(regexp = "\\A[A-Za-z0-9_-]{1,128}\\z")
    String label
) {
}
~~~

Đây là snippet Java được hoàn thiện trong phần runnable. Ý nghĩa:

- `@NotBlank`: label không được null, rỗng hoặc chỉ gồm whitespace.
- `@Size(max=128)`: chiều dài của string không vượt mức đã định.
- `@Pattern`: định dạng chỉ nhận ASCII letters, digits, underscore, hyphen; lượng tử cũng tự giới hạn 1..128.
- `@Valid @RequestBody LabelInput` trên controller yêu cầu framework validate DTO sau khi JSON decoding thành công.

**Một object có thể vi phạm nhiều constraints**: ví dụ `label=""` vi phạm `@NotBlank` và `@Pattern`. Nếu error response hiển thị một danh sách field names đã loại trùng, điều đó không có nghĩa có đúng một constraint violation. Phần thực hành cố ý map names distinct để API minh họa đơn giản.

### `@Size` và `@Pattern` có chạy theo thứ tự không?

Không nên dựa vào thứ tự khai báo annotations trong source file. Nếu một expensive validator chạy trên input lớn, thêm `@Size` ở cùng field **không tạo ra ordering guarantee**.

Có hai chiến lược:

- **An toàn ngay từ pattern:** dùng bounded, simple expression như ví dụ, để kể cả `@Pattern` chạy trước `@Size` thì chi phí vẫn có kiểm soát.
- **Validation hai giai đoạn:** có explicit length guard trước phần expensive check, hoặc thiết kế **validation group sequence** để group kích thước chạy trước group định dạng, có tests xác nhận. Group sequence làm phức tạp contract và không thay thế network-level body cap.

Trong dự án thật, nếu có nhiều form dùng cùng một check phức tạp, đặt phép kiểm tra vào service/validator đã được audit, không sao chép một regex khó kiểm soát vào nhiều `@Pattern` annotations.

## 11. Chương trình Spring Boot 3.5 / Java 17+ hoàn chỉnh

Ta tạo một REST endpoint:

- `POST /api/labels` nhận JSON `{"label":"invoice_2026"}`.
- Label hợp lệ từ **1 đến 128 UTF-16 units**, chỉ ASCII letter, digit, underscore, hyphen.
- Dữ liệu hợp lệ trả HTTP **201 Created**.
- DTO sai constraint trả HTTP **400 Bad Request** kèm danh sách tên fields, không lộ rejected values.
- Service policy gọi length gate **trước** regex trong phép kiểm tra riêng.
- HTTP body byte cap **không** được giải quyết chỉ bởi Java/DTO; phần 5 chỉ cách cấu hình ingress.

Các file ở package `com.example.inputsafety`, dùng Spring Boot **3.5.x** và Java **17+**. Project có thể tạo từ Spring Initializr: Spring Web, Validation.

### 11.1. Dependencies Gradle

Trong `build.gradle` đã có Spring Boot plugin/version management tương thích:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Starter Web ở đây là Servlet Spring MVC (embedded Tomcat thông thường), không phải WebFlux. Starter Validation đưa Jakarta provider vào classpath. Starter Test cung cấp JUnit 5 và MockMvc.

Không chạy các class import Spring bằng `javac` thuần chỉ với JDK; cần các dependencies nêu trên và Gradle wrapper của project Boot hợp lệ.

### 11.2. `InputSafetyApplication.java`

`src/main/java/com/example/inputsafety/InputSafetyApplication.java`:

~~~java
package com.example.inputsafety;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InputSafetyApplication {

    public static void main(String[] args) {
        SpringApplication.run(InputSafetyApplication.class, args);
    }
}
~~~

### 11.3. `LabelInput.java`

`src/main/java/com/example/inputsafety/LabelInput.java`:

~~~java
package com.example.inputsafety;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record LabelInput(
    @NotBlank
    @Size(max = 128)
    @Pattern(regexp = "\\A[A-Za-z0-9_-]{1,128}\\z")
    String label
) {
}
~~~

Đây là immutable request DTO; không bind trực tiếp domain/entity object. `@Pattern` đã được thiết kế đơn giản và bounded **ngay cả khi annotation validators chạy theo thứ tự không xác định**.

### 11.4. `LabelPolicy.java`

`src/main/java/com/example/inputsafety/LabelPolicy.java`:

~~~java
package com.example.inputsafety;

import java.util.regex.Pattern;

public final class LabelPolicy {

    static final int MAX_LABEL_UNITS = 128;

    private static final Pattern LABEL_PATTERN =
        Pattern.compile("\\A[A-Za-z0-9_-]{1,128}\\z");

    private LabelPolicy() {
    }

    public static boolean acceptable(String label) {
        if (label == null || label.isEmpty()) {
            return false;
        }
        if (label.length() > MAX_LABEL_UNITS) {
            // Bảo đảm regex của method này không thấy String dài.
            return false;
        }
        return LABEL_PATTERN.matcher(label).matches();
    }
}
~~~

Phương thức này cố ý **không trả lại input đã lỗi**. `String.length()` kiểm tra UTF-16 units, rồi một regex đơn giản xác nhận characters. `Pattern` là static final và an toàn dùng chung; mỗi `matcher(...)` tạo một Matcher riêng.

**Có phải kiểm tra trùng với annotation?** Có, **có chủ đích để dạy boundary**: annotation thể hiện declarative contract trên DTO; policy minh họa *explicit pre-match guard* cho một phép match được ứng dụng chủ động thực hiện. Trong một production codebase, cân nhắc tránh chạy regex hai lần bằng cách chọn một nguồn quy tắc và các tests bảo đảm security/performance. Việc có guard trong policy **không** làm annotation `@Pattern` trước đó chạy theo thứ tự dự kiến.

### 11.5. `LabelController.java`

`src/main/java/com/example/inputsafety/LabelController.java`:

~~~java
package com.example.inputsafety;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/labels")
public class LabelController {

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<LabelReply> create(
            @Valid @RequestBody LabelInput input) {

        if (!LabelPolicy.acceptable(input.label())) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid label");
        }

        return ResponseEntity.status(HttpStatus.CREATED)
            .body(new LabelReply(
                input.label(), input.label().length()));
    }

    public record LabelReply(
        String label,
        int utf16Units
    ) {
    }
}
~~~

Nếu input sai `@Valid`, Spring MVC thường tạo `MethodArgumentNotValidException` trước khi gọi handler; advice phía dưới map nó thành response 400. Nếu controller tự từ chối bởi `LabelPolicy` thì `ResponseStatusException` cũng dẫn tới 400, nhưng body mặc định của đường đó **không bắt buộc trùng** response tùy chỉnh cho Bean Validation. Với các constraints hiện tại, policy chỉ là lớp xác nhận lặp lại; định dạng hợp lệ đều đi đến 201.

### 11.6. `LabelValidationAdvice.java`

`src/main/java/com/example/inputsafety/LabelValidationAdvice.java`:

~~~java
package com.example.inputsafety;

import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class LabelValidationAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<InvalidLabelReply> invalidInput(
            MethodArgumentNotValidException ex) {

        List<String> fields = ex.getBindingResult()
            .getFieldErrors()
            .stream()
            .map(FieldError::getField)
            .distinct()
            .sorted()
            .toList();

        return ResponseEntity.badRequest()
            .body(new InvalidLabelReply(
                "INVALID_LABEL", fields));
    }

    public record InvalidLabelReply(
        String code,
        List<String> fields
    ) {
    }
}
~~~

Response chỉ lộ field names và mã lỗi ổn định; không serialize `BindingResult`, `FieldError.getRejectedValue()` hoặc client input. Nếu product cần nhiều constraint messages, bổ sung trường `issues[]` theo contract riêng với `MessageSource` để dịch, tránh làm mất thông tin bằng cách `distinct()` ở mức field.

**Không cần** `ResponseEntityExceptionHandler` cho demo đơn giản này. Nếu production advice **đã extends ResponseEntityExceptionHandler**, nên override `handleMethodArgumentNotValid(...)` thay vì khai báo thêm `@ExceptionHandler(MethodArgumentNotValidException.class)` trùng map trong subclass.

### 11.7. `application.properties`

`src/main/resources/application.properties`:

~~~properties
# Chỉ giới hạn headers, FORM POST và multipart theo phạm vi.
server.max-http-request-header-size=8KB
server.tomcat.max-http-form-post-size=16KB
server.tomcat.max-parameter-count=128
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=4MB
~~~

**Đây chưa phải global JSON-body cap**. Khi đưa endpoint ra Internet, cần thêm proxy/gateway body limit hoặc một tầng enforce streaming bytes trước JSON decoder; không coi một ví dụ `@Size` đã giải quyết payload DoS.

### 11.8. Chạy và curl

Từ project root có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu ứng dụng dùng port mặc định 8080, input hợp lệ:

~~~bash
curl -i -X POST "http://localhost:8080/api/labels" \
  -H "Content-Type: application/json" \
  -d '{"label":"invoice_2026-11"}'
~~~

Kỳ vọng HTTP **201 Created**:

~~~json
{
  "label": "invoice_2026-11",
  "utf16Units": 15
}
~~~

Đếm ký tự chuỗi `invoice_2026-11`: `invoice` có 7, dấu gạch dưới 1, `2026` có 4, gạch nối 1, `11` có 2 → tổng **15** UTF-16 units.

Input dài quá 128:

~~~bash
python -c "import json; print(json.dumps({'label':'a'*129}))" \
  | curl -i -X POST "http://localhost:8080/api/labels" \
      -H "Content-Type: application/json" --data-binary @-
~~~

Đây là lệnh shell minh họa có Python sẵn trên máy. Nó tạo 129 chữ `a`; cả `@Size(max=128)` và `@Pattern` có thể báo lỗi. Kỳ vọng HTTP **400**, body do advice tạo:

~~~json
{
  "code": "INVALID_LABEL",
  "fields": ["label"]
}
~~~

Khi request có `{"label":"hello!"}`, ký tự `!` không hợp lệ và HTTP 400. Khi `label=""`, `@NotBlank`/`@Pattern` không đạt; response vẫn liệt kê field `label` một lần vì code advice dùng `distinct()`.

**Nếu client gửi body 100 MB:** `@Valid`/`@Size` có thể từ chối sau khi body đã đến Spring MVC, nhưng đó **không chứng minh** network/parser đã tránh sử dụng tài nguyên. Hãy thử cap ở proxy qua một test riêng, không tạo input khổng lồ trên server production.

## 12. Kiểm thử JUnit 5 và MockMvc

Để kiểm tra *input contract*, dùng integration tests qua Spring MVC. Để kiểm tra *thứ tự guard trước regex*, gọi riêng `LabelPolicy.acceptable` với một chuỗi dài nhưng không benchmark regex nguy hiểm.

### 12.1. `LabelPolicyTest.java`

`src/test/java/com/example/inputsafety/LabelPolicyTest.java`:

~~~java
package com.example.inputsafety;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LabelPolicyTest {

    @Test
    void acceptsBoundariesWithAllowedAscii() {
        assertTrue(LabelPolicy.acceptable("a"));
        assertTrue(LabelPolicy.acceptable("a".repeat(128)));
    }

    @Test
    void rejectsTooLongBeforeCallingMatcher() {
        assertFalse(LabelPolicy.acceptable(
            "a".repeat(10_000)));
    }

    @Test
    void rejectsDisallowedCharacters() {
        assertFalse(LabelPolicy.acceptable("a!"));
        assertFalse(LabelPolicy.acceptable("a b"));
        assertFalse(LabelPolicy.acceptable("😀"));
    }

    @Test
    void utf16UnitsDifferFromBytesAndCodePoints() {
        String emoji = "😀";
        assertEquals(2, emoji.length());
        assertEquals(1, emoji.codePointCount(
            0, emoji.length()));
        assertEquals(4, emoji.getBytes(
            StandardCharsets.UTF_8).length);
    }
}
~~~

Các tests không chạy regex `(a+)+$` hoặc so thời gian tuyệt đối, vì wall-clock benchmark dễ thất thường theo JDK/CPU/load. `"a".repeat(10_000)` chỉ kiểm chứng một lời gọi `acceptable` phải trả false vì length guard; nó không gây stress bằng regex xấu.

### 12.2. `LabelControllerTest.java`

`src/test/java/com/example/inputsafety/LabelControllerTest.java`:

~~~java
package com.example.inputsafety;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LabelControllerTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private ObjectMapper mapper;

    private String json(String label) throws Exception {
        return mapper.writeValueAsString(
            new LabelInput(label));
    }

    @Test
    void validAsciiLabelReturns201() throws Exception {
        mvc.perform(post("/api/labels")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json("invoice_2026-11")))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.label")
                .value("invoice_2026-11"))
            .andExpect(jsonPath("$.utf16Units")
                .value(15));
    }

    @Test
    void exactly128UnitsIsValid() throws Exception {
        mvc.perform(post("/api/labels")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json("a".repeat(128))))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.utf16Units")
                .value(128));
    }

    @Test
    void oneOverLimitIsRejected() throws Exception {
        mvc.perform(post("/api/labels")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json("a".repeat(129))))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("INVALID_LABEL"))
            .andExpect(jsonPath("$.fields[0]")
                .value("label"));
    }

    @Test
    void invalidCharacterIsRejected() throws Exception {
        mvc.perform(post("/api/labels")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json("hello!")))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fields[0]")
                .value("label"));
    }

    @Test
    void blankLabelIsRejected() throws Exception {
        mvc.perform(post("/api/labels")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json("")))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fields[0]")
                .value("label"));
    }

    @Test
    void missingLabelIsRejected() throws Exception {
        mvc.perform(post("/api/labels")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json(null)))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fields[0]")
                .value("label"));
    }

    @Test
    void unicodeNotAllowedByAsciiPolicy() throws Exception {
        mvc.perform(post("/api/labels")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json("😀")))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fields[0]")
                .value("label"));
    }

    @Test
    void malformedJsonGetsClientError() throws Exception {
        mvc.perform(post("/api/labels")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Trong cấu hình Spring Boot 3.5 + Web/Validation/Test starters, **12 test methods** (4 unit + 8 MVC) kỳ vọng pass. Đây là kết quả lý thuyết từ code mẫu; chưa khẳng định Gradle đã chạy. Một `ObjectMapper` do Boot cung cấp giúp test tạo JSON an toàn thay vì ghép chuỗi và tự escape input.

**MockMvc không kiểm chứng proxy cap hoặc network bandwidth.** Nó đi qua Spring MVC controller/validation nhưng không gửi payload qua NGINX như ví dụ ở phần 5. Cần một test E2E có proxy thật để khẳng định HTTP 413 cho body vượt giới hạn byte.

### Thử lỗi 413 ở tầng ingress

Khi dùng NGINX `client_max_body_size 8k` trong môi trường test, gửi một body JSON vừa vượt 8 KiB, quan sát HTTP status từ proxy và logs upstream. Đừng kết luận mọi response quá giới hạn đều sẽ đi qua `@RestControllerAdvice`; proxy có thể trả response trực tiếp và controller không được gọi.

Khi triển khai production, kiểm tra giới hạn trên **tổng payload thực tế**, cả trường hợp `Transfer-Encoding: chunked` khi phù hợp, và xác nhận health/rate policies không bị bypass bằng endpoint khác.

## 13. Thiết kế regex an toàn theo bài toán cụ thể

### Nhãn ASCII

Yêu cầu: 1..128 ký tự từ alphabet đơn giản:

~~~regex
\A[A-Za-z0-9_-]{1,128}\z
~~~

Ưu điểm: rõ ràng, bounded, không backreference, không nested ambiguous repetition.

### Mã gồm đúng 8 chữ số ASCII

~~~regex
\A[0-9]{8}\z
~~~

Nếu dùng `\d` trong Java regex, semantics Unicode phụ thuộc flags và pattern configuration. Khi business rule chỉ chấp nhận ASCII digits, viết `[0-9]` rõ hơn.

### Định dạng 3 chữ cái viết hoa và 4 chữ số

~~~regex
\A[A-Z]{3}-[0-9]{4}\z
~~~

Ví dụ hợp lệ `ABC-1234`; ví dụ không hợp lệ `AB-1234`. Không cần `.*` hoặc alternation.

### Slug chữ thường với các nhóm cách nhau bằng gạch nối

Có thể dùng:

~~~regex
\A[a-z0-9]+(?:-[a-z0-9]+)*\z
~~~

Pattern này diễn đạt slug có các token chữ/số, giữa chúng tối đa một `-`; nên giới hạn độ dài input trước khi áp dụng nếu traffic không tin cậy. Khi quan sát pattern có nested quantifier, cần review các character sets có overlap và hành vi thất bại, không suy ra an toàn chỉ vì nhìn gọn.

Một lựa chọn còn dễ audit hơn là **parser thủ công tuyến tính**: kiểm tra length, duyệt từng ký tự, cho phép ASCII alphanumeric và `-` khi không ở đầu/cuối hoặc liên tiếp. Với grammar đơn giản, code vòng lặp O(n) thường dễ chứng minh chi phí hơn một regex phức tạp.

### Email, URL và định dạng quốc tế

Không lấy một “regex RFC đầy đủ” nhiều trang từ Internet rồi dùng làm `@Pattern` cho email/URL trong API public. Ưu tiên `@Email` của Jakarta Validation (với những giới hạn của nó) và kiểm tra domain nghiệp vụ, hoặc parser URI/URL/IDN phù hợp. Luôn giới hạn độ dài trước bước tốn kém và không coi email/URL parse thành công là đã xác thực quyền sở hữu hay chống SSRF.

## 14. Tách chính sách an toàn khỏi thông báo lỗi

Một API tốt không đưa cho client thông tin nhạy cảm về engine, regex pattern nội bộ hay object graph:

| Nguyên nhân | Trạng thái phù hợp thường gặp | Nội dung công khai nên có |
|---|---|---|
| Field quá dài sau decode, schema không hợp lệ | HTTP 400 | `INVALID_FIELD_LENGTH`, field name, max length |
| Regex-format mismatch trên field | HTTP 400 | `INVALID_FIELD_FORMAT`, hướng dẫn định dạng |
| Request body vượt ingress byte limit | HTTP 413 | `PAYLOAD_TOO_LARGE` hoặc generic |
| Multipart file vượt limit | HTTP 413 hoặc response tương ứng cấu hình | Max file/request size; không lộ temp path |
| JSON malformed | HTTP 400 | `MALFORMED_JSON` |
| Missing/unsupported content type | HTTP 400/415 tùy lỗi | Content type được hỗ trợ |
| Rate limit vượt quota | HTTP 429 | Thông tin retry nếu contract cho phép |
| Lỗi server hoặc validator code bug | HTTP 500 | Thông điệp chung; log nội bộ riêng |

**Đừng hard-code mọi lỗi thành HTTP 400**. Request vượt byte limit khác một field sai quy tắc. Trong Spring MVC, `MethodArgumentNotValidException` thường phản ánh DTO violations, còn JSON parsing có thể tạo `HttpMessageNotReadableException` và multipart có thể tạo `MaxUploadSizeExceededException`. Proxy body cap thường chặn trước khi Spring thấy request.

### Có cần in rejected value vào log không?

Không mặc định. Một request quá dài có thể làm log tăng rất nhanh và chứa tokens/PII. Ghi **error code, route template, length band** hoặc số bytes theo bucket, không ghi toàn bộ field. Với ReDoS, ghi thời lượng validation/CPU metrics và correlation ID thay vì raw payload.

### Tránh leak pattern nội bộ

Nếu ứng dụng dùng regex để kiểm tra mã giao dịch, trả một câu như “Mã phải có 8 chữ số” thay vì trả nguyên regex phức tạp trong response. Regex có thể là implementation detail và một phản hồi quá kỹ thuật không giúp người dùng sửa input tốt hơn.

## 15. Rate limiting và time budgets bổ sung, không thay thế regex review

Một attacker có thể dùng nhiều requests nhỏ để chiếm tài nguyên. Ngoài size cap:

- **Per-client rate limit** và global quotas ở gateway.
- **Connection/read timeout** để giảm slow-client abuse; semantics tùy server.
- **Thread pool / concurrency bounds** và backpressure khi upstream quá tải.
- **Timeout cho downstream I/O** như database/network, nhưng không coi chúng là regex CPU timeout.
- **Circuit breaker** cho dependency failures, không dùng thay input validation.
- **Giới hạn số phần tử batch** và thời gian xử lý business logic.
- **Metrics p95/p99** cho parsing, validation và toàn request; cảnh báo tăng bất thường.

Một regex rất xấu vẫn có thể làm một request đơn lẻ chiếm một thread CPU lâu. Rate limit giảm khả năng khuếch đại nhưng không sửa độ phức tạp của pattern. Nên **giảm chi phí một request xuống mức có thể dự đoán**, sau đó mới dùng quotas để bảo vệ tổng hệ thống.

## 16. Nếu ứng dụng cho người dùng nhập regex tùy ý

Đây là trường hợp rủi ro cao hơn việc dùng một regex cố định do developer viết. Đừng đưa chuỗi người dùng vào:

~~~java
Pattern compiled = Pattern.compile(userPattern);
boolean match = compiled.matcher(userText).find();
~~~

Đây là **phản ví dụ**, vì pattern và input đều không tin cậy. Cấu hình đơn thuần `@Size(max=128)` trên `userPattern` không bảo đảm an toàn: một biểu thức ngắn vẫn có thể gây ReDoS.

Các lựa chọn:

1. **Không hỗ trợ regex tự do** nếu sản phẩm chỉ cần prefix/suffix/exact/wildcard đơn giản; chuyển yêu cầu thành parser an toàn.
2. Nếu bắt buộc có regex, cân nhắc engine có **bảo đảm tuyến tính** và giới hạn tập cú pháp; document rõ việc thiếu backreferences/lookarounds hoặc các tính năng khác.
3. Áp giới hạn chiều dài cả **pattern** lẫn **input**; giới hạn số phép thử, số searches và rate.
4. Kiểm tra quy tắc nghiệp vụ/tài nguyên trước khi compile/chạy.
5. Phân tách vùng thực thi, time/memory budget với cơ chế hủy tác vụ đáng tin và giới hạn concurrency nếu cho phép tính toán phức tạp.
6. Không dùng `Pattern.quote(...)` để “sửa” một regex do người dùng thật sự muốn nhập; `Pattern.quote` chuyển nội dung thành **literal text**, là giải pháp đúng khi muốn tìm chuỗi literal, nhưng thay đổi semantic của chức năng regex.

### Literal search thì dùng gì?

Nếu cần tìm chuỗi do client cung cấp nhưng **không cần cú pháp regex**, dùng `String.contains(...)`/`indexOf(...)` hoặc:

~~~java
Pattern safeLiteral =
    Pattern.compile(Pattern.quote(userText));
~~~

Đây là snippet cần imports và biến `userText`. `Pattern.quote` bảo đảm các ký tự như `(`, `*`, `+`, `[` được xem là literal thay vì thành regex operators. Với bài toán tìm literal đơn giản, `String.contains` thường dễ hiểu, không cần regex engine.

## 17. Unicode, normalisation và kiểm tra trước/sau chuẩn hóa

Nếu ứng dụng cho Unicode labels, cần quyết định:

- Có cho emoji, combining marks, nhiều scripts và các ký tự điều khiển không?
- Độ dài dựa trên bytes, UTF-16 units, Unicode code points hay grapheme clusters?
- Có chuẩn hóa NFC/NFKC không? Chuẩn hóa có thể thay đổi biểu diễn chuỗi, và đôi khi cả độ dài/tập ký tự.
- Có cần case folding theo locale hoặc invariant hay không?
- Có cho ký tự nhìn giống nhau nhưng khác code point (homoglyph/confusable) không?

**Đừng validate một representation rồi lưu representation khác mà không kiểm tra lại.** Nếu hệ thống chuẩn hóa Unicode trước lưu, cần xác định thứ tự: giới hạn bytes trước decode → decode an toàn → normalize với budget → giới hạn length và định dạng trên chuỗi chuẩn hóa → lưu.

Một mã định danh liên quan authorization/signature còn cần canonicalization nhất quán giữa các thành phần. Regex đúng cú pháp không tự giải quyết homoglyph spoofing hoặc path traversal.

## 18. So sánh Spring MVC và WebFlux ở mức tài nguyên

| Vấn đề | Spring MVC Servlet | Spring WebFlux |
|---|---|---|
| Body decoder | `HttpMessageConverter`/Jackson | `HttpMessageReader`/codecs |
| Backpressure/reactive type | Thường DTO trực tiếp, Servlet I/O | `Mono<T>`/`Flux<T>` theo resolver |
| Annotation validation | `@Valid`/`@Validated` sau binding/decoding | `@Valid`/`@Validated` với resolver reactive |
| Multipart cap | Servlet multipart config và server/proxy | Codec/multipart server settings riêng |
| Buffered data limit | Parser/server/proxy; không có một Boot property chung mọi JSON | Codec `maxInMemorySize` có vai trò riêng |
| Regex CPU risk | Java `Pattern` vẫn backtracking | Cũng vậy: reactive wrapper không làm regex tự thành non-blocking |
| Big request cap | Cần ingress/proxy hoặc byte-counting thật | Cần ingress/proxy và reactor/codec limits |
| Blocking custom validator | Chiếm Servlet worker thread | Có thể chặn event-loop, càng cần tránh |

WebFlux không tự giải quyết ReDoS. `Mono<Dto>` hoặc `Flux<Dto>` là cơ chế dữ liệu bất đồng bộ; một `ConstraintValidator.isValid(...)` gọi regex backtracking vẫn có thể đốt CPU trong thread đang chạy nó.

## 19. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| Body JSON 20MB vẫn tới controller dù đã đặt `@Size(max=128)` | `@Size` chạy sau JSON decoder | Giới hạn bytes ở ingress và parser; dùng DTO constraint như lớp sau |
| `server.tomcat.max-http-form-post-size=16KB` không chặn JSON | Đây là giới hạn form POST, không phải JSON body cap phổ quát | Dùng proxy/streaming body byte cap |
| 128 emoji được xem dài hơn 128 “ký tự” | Java UTF-16 units khác code points/glyphs | Định nghĩa độ dài sản phẩm và kiểm thử Unicode |
| Một field có `@Size` nhưng regex vẫn chậm | Constraint order không được bảo đảm | Viết regex an toàn, ordered validation hoặc explicit gate |
| Regex thất bại rất chậm trên input gần hợp lệ | Nested/ambiguous quantifiers | Audit và rewrite pattern, kiểm tra worst-case |
| Đổi `+` thành `+?` không cải thiện | Lazy vẫn có backtracking | Đơn giản hóa grammar, dùng possessive/atomic có test semantics |
| Gắn `++` làm input đúng bị reject | Possessive không trả lại ký tự | Kiểm tra equivalence bằng unit tests |
| `Matcher.find()` chấp nhận chuỗi chứa nội dung cấm | Chỉ match một substring | Dùng `matches()` và policy full-string |
| Patterns được compile mỗi request | Repeated compilation | Dùng static final `Pattern` cho regex cố định |
| Chia sẻ một `Matcher` qua threads gây lỗi | Matcher là stateful | Tạo matcher mới cho mỗi input |
| `Future.cancel(true)` không giải phóng CPU ngay | Không có match-timeout contract bảo đảm | Không dựa vào cancel; viết lại pattern/giới hạn CPU |
| File upload vượt giới hạn nhưng advice không chạy | Multipart parsing/container/proxy từ chối trước handler | Test end-to-end, map exception phù hợp nơi nhận được |
| Form có `items[99999]` và xử lý tốn memory | Collection auto-growth/binding policy | Giới hạn autoGrow, allowedFields, parameter count |
| JSON nesting quá sâu | Parser/object graph chưa có nesting limit | Dùng Jackson StreamReadConstraints và giới hạn bytes |
| Validation custom gọi database cho mỗi field | I/O đồng bộ trong validator | Tách validation cấu trúc và policy/service checks |
| Test MockMvc PASS nhưng ingress vẫn nhận body lớn | MockMvc bypass reverse proxy | Thêm E2E traffic qua ingress thực |
| Response 400 lộ input dài/token | Serialize `FieldError` hoặc log body | DTO error tối giản, log size buckets |
| Có HTTP 429 nhưng một request vẫn chiếm CPU lâu | Rate limit không sửa regex complexity | Chỉnh pattern, giới hạn input/CPU |
| Byte cap được kiểm tra chỉ bằng Content-Length | Chunked/streaming có thể không có Content-Length | Enforce actual bytes trên stream/proxy |

### Quy trình debug thực tế

1. Ghi rõ web stack: MVC/Servlet hay WebFlux.
2. Xác định loại input: JSON, form, multipart, query, header, file.
3. Đọc giới hạn **bytes** ở proxy/container trước khi kiểm tra annotations.
4. Kiểm tra parser limits: string token, nesting depth, số items/parameters.
5. Xác nhận Bean Validation provider đang hoạt động.
6. Đo độ dài theo đúng đơn vị (bytes/UTF-16/code points).
7. Đọc regex, tìm nested ambiguity/backreferences/scan semantics.
8. Xác minh `Pattern` được tái sử dụng, `Matcher` không bị chia sẻ.
9. Thử 0/1/max/max+1 và input gần hợp lệ nhưng thất bại, **không chạy benchmark nguy hiểm trong prod**.
10. Kiểm tra status: 400 cho field invalid, 413 cho body bytes vượt cap, 429 cho quota.
11. Đo thời gian parser/validator và CPU, theo dõi p95/p99, tỷ lệ rejects.
12. Xác nhận E2E ingress cap, vì unit/MockMvc test không đi qua proxy.

## 20. Câu hỏi tự luyện

**1. `@Size(max=128)` có chặn request body JSON dài 5 MB trước khi Spring đọc không?**

Không. Nó kiểm tra DTO/field sau decode/binding; cần byte cap ở ingress/parser.

**2. Giới hạn `server.tomcat.max-http-form-post-size` có nghĩa là mọi JSON body đều bị cap cùng kích thước không?**

Không. Đây là form POST content cap của Tomcat, không phải JSON body cap phổ quát.

**3. Với `String emoji="😀"`, `emoji.length()` và byte UTF-8 là bao nhiêu?**

`length()==2` UTF-16 code units; UTF-8 thường 4 bytes; số code points là 1.

**4. Vì sao `@Size` đứng trước `@Pattern` trong source không đảm bảo regex chạy sau?**

Jakarta Bean Validation không cam kết thứ tự thực thi các constraints chỉ dựa vào thứ tự annotation.

**5. `(a+)+$` có vấn đề gì?**

Nested ambiguous repetition có thể tạo nhiều nhánh backtracking trên input gần khớp nhưng thất bại ở cuối.

**6. Cách xử lý trước tiên là gì nếu một regex có chi phí xấu?**

Viết lại regex/grammar để giảm ambiguity, giới hạn input và test semantics, không chỉ tăng timeout.

**7. `Pattern` hay `Matcher` có thể chia sẻ giữa các requests?**

`Pattern` compile cố định có thể chia sẻ an toàn. `Matcher` mutable không thread-safe, tạo mới cho từng match.

**8. Khi cần kiểm tra toàn bộ label, `matches()` hay `find()` phù hợp?**

`matches()`. `find()` phù hợp khi thật sự chỉ muốn tìm một đoạn con.

**9. `setAutoGrowCollectionLimit(64)` có giới hạn cả JSON array decoder không?**

Không. Đó là policy cho auto-growth trong data binding, không phải một giới hạn JSON array phổ quát.

**10. Vì sao body cap ở proxy cần integration test riêng?**

Vì `MockMvc` không đi qua proxy; nó không chứng minh HTTP 413 được áp trước ứng dụng.

**11. `Future.cancel(true)` có phải regex timeout đáng tin cậy trong Java 17 không?**

Không. Không nên coi cancellation/interruption là bảo đảm CPU của regex sẽ dừng theo deadline.

**12. Nếu client chỉ muốn tìm chuỗi literal do họ cung cấp, có cần regex tùy ý không?**

Không. Dùng `String.contains`/`indexOf` hoặc `Pattern.quote` để tránh biến ký tự input thành regex syntax.

## 21. Checklist vận hành và review security

- [ ] Định nghĩa max byte size cho từng endpoint tại ingress/proxy.
- [ ] Định nghĩa header/request-line size, parameter count, form cap và multipart limits.
- [ ] Có parser limits cho JSON strings, numbers, nesting depth và collection sizes khi cần.
- [ ] Giới hạn WebDataBinder auto-grow và property allowlist với form binding.
- [ ] Dùng DTO chuyên biệt, không bind trực tiếp entity nhạy cảm.
- [ ] Xác định đơn vị `@Size`: UTF-16 length hay product-specific Unicode semantics.
- [ ] Không kỳ vọng `@Size` chạy trước `@Pattern` nếu chưa áp ordering rõ.
- [ ] Audit regex cho nested quantifier, overlapping alternatives, backreferences, unanchored scans.
- [ ] Với regex cố định, dùng bounded character class và full-string match khi phù hợp.
- [ ] Compile `Pattern` một lần, tạo `Matcher` riêng cho mỗi request.
- [ ] Không coi `Future.cancel`/HTTP timeout là biện pháp chắc chắn chống ReDoS.
- [ ] Có strategy riêng khi client được phép nhập regex, không dùng Java Pattern tùy ý mặc định.
- [ ] Không serialize rejected values, tokens hoặc stack traces trong lỗi validation.
- [ ] Trả status phù hợp: 400 (field/schema), 413 (byte cap), 429 (quota), 500 (server).
- [ ] Kiểm thử boundaries 0/1/max/max+1, Unicode, field invalid, malformed JSON.
- [ ] Kiểm tra request transport cap qua ingress thật chứ không chỉ MockMvc.
- [ ] Theo dõi latency, CPU, reject rates, rate limits và hoạt động dưới tải.
- [ ] Rà soát lại các limits/patterns khi thay đổi schema, server, JDK hoặc Spring Boot.

**Ghi nhớ:** Bảo vệ input phải có **nhiều tầng**. `@Size` kiểm tra độ dài sau binding, `@Pattern` kiểm tra định dạng nhưng có thể gây **ReDoS** nếu thiết kế regex xấu; cả hai không thay cho giới hạn **HTTP bytes/JSON parser/binder growth**. Với Spring Boot 3.5, dùng đúng properties theo phạm vi (form, multipart, headers), đặt JSON byte limit ở ingress/streaming layer và giữ regex đơn giản, bounded, có kiểm thử.

## Tài liệu tham khảo chính thức

- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework — Jakarta Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Boot 3.5 — Spring MVC / Multipart](https://docs.spring.io/spring-boot/3.5/how-to/spring-mvc.html)
- [Java 17 — Pattern Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
- [Java 17 — Matcher Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Matcher.html)
- [OWASP — Regular Expression Denial of Service](https://owasp.org/www-community/attacks/Regular_expression_Denial_of_Service_-_ReDoS)
- [Jackson Core — StreamReadConstraints Javadoc](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/latest/com/fasterxml/jackson/core/StreamReadConstraints.html)
