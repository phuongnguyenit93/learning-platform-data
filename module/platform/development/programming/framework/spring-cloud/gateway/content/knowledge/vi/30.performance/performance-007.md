# Giảm chi phí predicate và biểu thức chính quy

## 1. Tại sao route matching lại trở thành vấn đề hiệu năng?

Trong kiến trúc microservices, **Spring Cloud Gateway** là điểm vào của nhiều API: Gateway xem xét yêu cầu HTTP, chọn tuyến bằng **route predicate**, chạy **filter chain** để biến đổi đường dẫn/header, xác thực và giới hạn lưu lượng, rồi chuyển tiếp tới dịch vụ qua URI cố định hoặc service discovery. Khi xử lý nhiều request đồng thời, những thao tác nhỏ trong quá trình chọn tuyến cũng có thể tích lũy thành CPU time đáng kể.

Ví dụ hệ thống có vài trăm tuyến và một số tuyến dùng biểu thức chính quy để phân biệt `Host`, `Header` hoặc `Query`. Một cấu hình rất rộng:

~~~yaml
predicates:
  - Path=/**
  - Header=X-Partner-Code,^(.*a){3,}.*$
  - Query=search,.*(gold|silver|platinum).*
~~~

có thể khiến Gateway phải thực hiện nhiều lần kiểm tra các chuỗi client có quyền kiểm soát. Nếu regex cho phép **backtracking rất lớn** ở một đầu vào đặc biệt, một request nhỏ có thể tiêu tốn CPU quá mức (**Regular Expression Denial of Service, ReDoS**). Mặt khác, chỉ nhìn thấy regex không có nghĩa mọi regex đều chậm: tác động thực tế phụ thuộc pattern, input, số lần đánh giá và phiên bản Java/framework.

Bài **“Giảm chi phí predicate và biểu thức chính quy”** thuộc chương **Hiệu năng** của module **SPRING_CLOUD_GATEWAY**. Ta sẽ tối ưu **phần chọn route**, nhưng không phá vỡ tính đúng đắn của route, authorization, rate limiting, circuit breaker, retry, TLS hay observability.

Sau bài, bạn có thể:

1. Xây dựng mô hình chi phí từ **số route ứng viên × số predicate × độ phức tạp từng predicate**.
2. Phân biệt `Path`/`Host` patterns và regex Java trong `Header`/`Cookie`/`Query`.
3. Thay regex quá rộng bằng điều kiện hẹp, sự hiện diện của tham số hoặc so sánh chuỗi khi phù hợp.
4. Hiểu `Pattern.compile`, `Matcher` và các dạng regex dễ gây backtracking.
5. Viết custom `RoutePredicateFactory` có giới hạn input, không làm blocking I/O.
6. Đo p50/p95/p99, throughput, CPU, allocation và độ đúng của route trên nhiều trường hợp.
7. Triển khai tối ưu có canary, hồi quy và rollback để không vô tình mở đường truy cập không được phép.

> **Phạm vi:** Ví dụ chính dùng **Spring Cloud Gateway Server WebFlux** và Reactor Netty. Gateway Server Web MVC dùng WebMvc.fn/Servlet với các API predicate tương ứng nhưng **không dùng cùng `ServerWebExchange` hoặc cùng lớp factory WebFlux**. Các nguyên lý giảm regex/backtracking vẫn hữu ích cho cả hai stack.

## 2. Predicate chạy ở đâu trong luồng xử lý?

~~~mermaid
flowchart TD
    C["HTTP client"] --> M["Gateway Server WebFlux<br/>RoutePredicateHandlerMapping"]
    M --> R{"Xét các route runtime<br/>theo cấu hình/order"}
    R -->|"Route A không match"| N["Xét route ứng viên tiếp"]
    N --> R
    R -->|"Một route match"| F["Combined GlobalFilter + GatewayFilter"]
    F --> L["Routing / lb:// / HttpClient"]
    L --> B["Backend service"]
    R -->|"Không có route"| E["Không có Gateway route<br/>handler khác hoặc 404"]
    B --> O["Response"]
~~~

**Predicate quyết định có chọn route hay không. Filter chạy sau khi route được chọn.** Vì thế, nếu mục tiêu là từ chối thật nhanh những request không thuộc một tuyến, đặt một điều kiện nhận dạng đường dẫn ở **Path predicate** thường hợp lý hơn cố chuyển toàn bộ phân loại vào một filter chạy sau bước chọn route.

Theo tài liệu Spring Cloud Gateway Server WebFlux, các predicate của một route thường được kết hợp bằng logic **AND**. Nhiều giá trị trong một predicate như `Method=GET,HEAD` hoặc `Path=/orders/**,/products/**` thể hiện lựa chọn **OR** trong cùng factory.

### 2.1. Cost model để suy nghĩ, không phải công thức của Spring

Giả sử mỗi request làm các thao tác:

\[
T_{\mathrm{routing}}\approx T_{\mathrm{dispatch}}
  + \sum_{r\in C(q)}\sum_{p\in P_r(q)} T_p(q)
  +T_{\mathrm{bookkeeping}}
\]

Trong đó:

- `q`: một incoming request.
- `C(q)`: các route ứng viên runtime thực sự được đánh giá trước khi chọn được một route hoặc kết luận không khớp.
- `P_r(q)`: các predicate đã được gọi của route `r`.
- `T_p(q)`: chi phí của một predicate với dữ liệu request đó.

Đây là **mô hình trực giác**; nó không tuyên bố Gateway luôn quét tuyến tính toàn bộ mọi route ở mọi phiên bản hay mọi cách khai báo. Route cache, ordering, predicate composition, matching và JIT optimization đều có thể tác động thực tế. Cần đo trên **artifact và cấu hình đang chạy**.

Một ước lượng minh họa:

~~~text
100 route candidates × 3 predicates each × 5 μs average
= 1.500 μs = 1,5 ms
~~~

Đây **không phải số đo Spring Cloud Gateway**. Nó chỉ cho thấy một chi phí nhỏ bị nhân bởi số lượng lần kiểm tra có thể trở nên đáng kể. Ngược lại, khi backend mất 300 ms, tối ưu vài micro giây predicate có thể ít giá trị hơn tối ưu connection pooling hoặc timeout.

### 2.2. Rất nhiều request “không match” cũng tốn CPU

Nếu gateway có 300 routes, một request `GET /does-not-exist` có thể phải đi qua nhiều nhánh kiểm tra trước khi trả 404. Trong một cuộc quét path hoặc đợt traffic xấu, số request **không khớp bất kỳ route nào** có thể rất lớn.

Đừng chỉ benchmark request thành công tới backend: cần cả **hit**, **miss**, request bị route khác nhận, và input dài/khác thường.

### 2.3. Chi phí route matching khác chi phí filter và downstream

| Chi phí | Ví dụ | Có phải route predicate cost? |
| --- | --- | --- |
| So path/method/header/query | Match `Path=/api/orders/**` | Có |
| Regex đối với header client | `Header=X-Partner-Code,...` | Có |
| Đọc/caching body cho `ReadBody` | Decode JSON request | Có, và có thể đáng kể |
| Xác thực JWT trong Spring Security | Kiểm tra chữ ký/audience | Không mặc định là route predicate |
| `RequestRateLimiter` qua Redis | Quota key và Redis round trip | GatewayFilter, không phải predicate thông thường |
| Rewrite response body | Buffers/codec | Filter |
| TLS handshake, DNS, TCP connect | Reactor Netty / backend | Transport/downstream |
| Retry/circuit breaker | Nhiều attempts hoặc fallback | Filter/downstream |

Nếu một flame graph cho thấy phần lớn thời gian ở TLS, JSON parsing hoặc Redis, giảm regex trên các route ít dùng có thể **không cải thiện độ trễ end-to-end đáng kể**. Tối ưu phải dựa vào dữ liệu.

## 3. Nhận diện predicate nào thật sự cần regex

Các route predicate factories Server WebFlux không có cùng thuật toán nội bộ.

| Predicate | Dữ liệu xét | Ngôn ngữ mẫu chính | Khi nào nên chọn |
| --- | --- | --- | --- |
| `Method` | HTTP method | Danh sách method | Phân nhánh GET/POST/HEAD |
| `Path` | Request path | Spring path patterns / URI templates | Tách chức năng theo prefix/segment |
| `Host` | HTTP Host | Ant-style host patterns | Virtual host/subdomain |
| `Header` | Header name/value | Java regex cho value | Chỉ khi phải kiểm tra value |
| `Query` | Query parameter | Có thể chỉ yêu cầu **tồn tại**, hoặc regex | Phân nhánh presence/value |
| `Cookie` | Cookie name/value | Java regex cho value | Chỉ khi có lý do hợp lệ; không thay auth |
| `RemoteAddr` | Remote socket address | CIDR | Phân loại mạng theo địa chỉ đáng tin |
| `After/Before/Between` | Thời gian request | ZonedDateTime | Khung thời gian, không cần regex |
| `ReadBody` | Body decoded | Custom Java predicate | Chỉ khi không thể quyết định bằng metadata |

Tài liệu Spring Cloud Gateway mô tả `Host` là **Ant-style với dấu chấm làm separator**, còn `Path` là **Spring path pattern**, **không phải cùng cú pháp Java regex**. Ví dụ `/api/orders/{id}` là URI template pattern, không cần thử `.matches("...")` với URL.

### 3.1. Khi chỉ cần biết query tồn tại, bỏ regex

Không cần:

~~~yaml
# Rườm rà nếu chỉ cần query key tồn tại
- Query=download,.*
~~~

Thay bằng:

~~~yaml
# Kiểm tra tham số download có mặt
- Query=download
~~~

**Nhưng semantics không giống nhau trong mọi ca.** Dạng một tham số kiểm tra sự tồn tại của key; dạng regex có thể áp lên giá trị (kể cả chuỗi rỗng hoặc nhiều values tùy phiên bản). Chỉ thay khi **yêu cầu nghiệp vụ thực sự là presence**, và thêm test cho `?download`, `?download=`, duplicate keys.

### 3.2. Khi chỉ cần phân nhánh theo prefix, dùng Path

Không nên dựng một custom predicate chỉ để chạy:

~~~java
Pattern.compile("^/api/catalog/.*")
       .matcher(requestPath)
       .matches();
~~~

trên mọi request nếu Gateway đã hỗ trợ:

~~~yaml
predicates:
  - Path=/api/catalog/**
~~~

`Path` thể hiện ý định route rõ hơn và sử dụng cơ chế matching tích hợp của Spring. Không tuyên bố nó **luôn** nhanh hơn mọi regex ở mọi JVM; nhưng nó tránh việc tự thiết kế một biểu thức quá rộng, tái biên dịch không cần thiết và tự xử lý URL encoding.

### 3.3. Khi chỉ cần so method, tránh chuyển thành chuỗi/regex

~~~yaml
predicates:
  - Method=GET,HEAD
~~~

đơn giản hơn việc tạo `Header=X-HTTP-Method-Override,...` hoặc đọc request body để suy ra method. Nếu ứng dụng sử dụng method override, phải xử lý ở security/routing boundary theo contract — không tự tin client khai header đó.

### 3.4. Đừng dùng wildcard rộng để “giảm số predicate”

Ví dụ thay:

~~~yaml
predicates:
  - Path=/api/payments/**
  - Method=POST
~~~

bằng:

~~~yaml
predicates:
  - Path=/**
~~~

có thể khiến route match **nhanh hơn trong vài trường hợp** nhưng cũng cho phép nhiều request không mong muốn đi qua đến backend. Đó không phải tối ưu chấp nhận được: **độ đúng và bảo mật là điều kiện ràng buộc**, hiệu năng là mục tiêu sau.

## 4. Java regex: compile, match và bộ nhớ

Chi phí một regex gồm các giai đoạn khác nhau:

1. **Compile** chuỗi mẫu thành cấu trúc `Pattern`.
2. **Tạo Matcher** cho giá trị đầu vào.
3. **Match** input, có thể phải thử lại nhiều nhánh.
4. **Allocation và GC** do các object/string phát sinh.

Với Java `java.util.regex.Pattern`:

~~~java
// Tiện, nhưng biên dịch regex mỗi lần gọi:
boolean ok = Pattern.matches("^[A-Za-z0-9_-]{1,32}$", value);
~~~

Theo Javadoc, `Pattern.matches(regex, input)` tương đương `Pattern.compile(regex).matcher(input).matches()`. Với pattern lặp lại trong request hot path, việc **compile một lần và tái sử dụng** thường hợp lý hơn.

~~~java
import java.util.regex.Pattern;

private static final Pattern SAFE_PARTNER_CODE =
        Pattern.compile("[A-Za-z0-9_-]{1,32}");

boolean ok = value != null
        && value.length() <= 32
        && SAFE_PARTNER_CODE.matcher(value).matches();
~~~

### 4.1. Pattern chia sẻ được, Matcher không chia sẻ

| Đối tượng | Cách dùng an toàn |
| --- | --- |
| `Pattern` | Immutable/thread-safe; giữ trong `static final` hoặc object cấu hình |
| `Matcher` | Mỗi request/mỗi lần kiểm tra tạo riêng; **không thread-safe** |
| Input string | Giới hạn độ dài và charset theo contract |
| Mutable buffer/cache | Không dùng chung mà thiếu kiểm soát đồng thời |

**Sai:**

~~~java
// KHÔNG dùng một Matcher để chia sẻ giữa request threads.
private static final Matcher SHARED_MATCHER =
        SAFE_PARTNER_CODE.matcher("");

// SHARED_MATCHER.reset(clientValue).matches();
~~~

`Matcher` có state: index, nhóm capture và kết quả trước đó; chia sẻ nó tạo data race và có thể làm kết quả route không nhất quán. Trên WebFlux, nhiều requests có thể được phục vụ đồng thời trên các event-loop threads.

### 4.2. Không đổ lỗi built-in factory khi chưa profile

Khi khai báo một regex có **dấu phẩy trong lượng từ `{1,32}`**, hãy dùng cú pháp fully expanded để tránh dấu phẩy bị hiểu là dấu phân tách shortcut arguments:

~~~yaml
predicates:
  - name: Header
    args:
      header: X-Partner-Code
      regexp: '^[A-Za-z0-9_-]{1,32}$'
~~~

**Không suy rằng Gateway chắc chắn gọi `Pattern.compile` lại với mỗi request**. Việc built-in factory compile ở bước tạo route hay lúc match là **chi tiết implementation theo version**. Hãy dùng CPU profile/JFR/benchmark đúng release; nếu không thấy compilation hot path, tự thay bằng factory riêng chỉ để “cache regex” có thể tăng complexity mà không tạo lợi ích.

### 4.3. `matches()` và `find()` khác nhau

~~~java
Pattern p = Pattern.compile("partner");
p.matcher("partner").matches();       // true
p.matcher("x-partner-x").matches();   // false
p.matcher("x-partner-x").find();      // true
~~~

`matches()` kiểm tra **toàn bộ** input; `find()` tìm một đoạn con. Java regex còn có anchors `^` và `$`. Khi thay mẫu, phải kiểm tra cách factory đang dùng Matcher và giữ nguyên tập giá trị được chấp nhận. Việc thêm `.*` để “cho dễ match” thường làm regex rộng hơn và tăng cơ hội backtracking.

### 4.4. Độ dài input quyết định nhiều hơn vẻ ngoài pattern

Pattern đơn giản như `[a-z]+` có thể chạy nhanh với header 12 ký tự, nhưng việc xử lý header rất dài vẫn tốn CPU. Do đó:

- Giới hạn kích thước request line/headers/URI ở public ingress và HTTP server.
- Giới hạn riêng độ dài header/query/cookie trước khi match custom regex.
- Giới hạn số parameter values, repeated headers và cookie count.
- Không đoán tên một property `max-header-size` áp dụng cho mọi Spring Boot/Netty version; đối chiếu configuration metadata.
- Không “normalize” dữ liệu lạ rồi vô tình biến request đáng lẽ bị loại thành request được chấp nhận.

## 5. ReDoS và catastrophic backtracking

Java `Pattern` là backtracking regex engine. Một số pattern cho phép **nhiều cách phân chia cùng một chuỗi**, khiến engine thử rất nhiều nhánh trước khi thất bại.

Ví dụ nổi tiếng:

~~~regex
^(a+)+$
~~~

Với chuỗi ngắn toàn ký tự `a`, biểu thức có thể match. Nhưng khi có nhiều `a` rồi một ký tự cuối **không hợp lệ**, engine có thể thử rất nhiều cách chia chuỗi cho các vòng lặp lồng nhau. Đây là dạng rủi ro ReDoS do OWASP cảnh báo.

**Không chạy benchmark input dài không kiểm soát cho regex nguy hiểm trên Gateway production.** Mục tiêu bài này là **nhận diện và loại bỏ pattern**, không hướng dẫn gây tải hay tấn công một hệ thống.

### 5.1. Các dấu hiệu regex dễ gây bùng nổ chi phí

| Dấu hiệu | Ví dụ minh họa | Rủi ro |
| --- | --- | --- |
| Lặp nằm trong lặp | `(a+)+` | Nhiều cách chia các ký tự giống nhau |
| Alternation chồng lấn, rồi lặp | `(a|aa)+` | Nhiều cách phân nhóm |
| Dùng `.*` lặp nhiều lần | `.*foo.*bar.*` | Backtracking trên input dài, nhất là khi gần match |
| Optional bên trong repetition | `(a?)+` | Nhiều cách khớp với đoạn rỗng |
| Regex lấy từ cấu hình không review | Pattern do người vận hành dán | Có thể mở rộng match hoặc gây CPU spike |
| Regex lấy trực tiếp từ client | `Pattern.compile(queryParam)` | Client điều khiển cả công việc CPU và chính sách |

Không phải mọi pattern có `.*` đều là exponential, và không phải mọi alternation đều xấu. Nhưng các dấu hiệu trên nên được **review và benchmark với input gần-khớp/thất-bại**.

### 5.2. Đơn giản hóa bằng biểu thức tương đương

Nếu yêu cầu thật sự là **chỉ chấp nhận một hoặc nhiều ký tự `a`**, thay:

~~~regex
^(a+)+$
~~~

bằng:

~~~regex
^a+$
~~~

Hai pattern cùng mô tả chuỗi chỉ gồm một hoặc nhiều `a` ở bài toán này, nhưng mẫu đơn giản loại bỏ việc lặp lồng nhau. Đối với input thật, cũng cần kiểm thử newline, Unicode, case sensitivity và cách matcher được gọi.

Tương tự, nếu nghiệp vụ chỉ yêu cầu một mã ký tự ASCII trong 1–32 ký tự, ưu tiên:

~~~regex
^[A-Za-z0-9_-]{1,32}$
~~~

thay vì:

~~~regex
^.*[A-Za-z0-9_-].*$
~~~

**Nhưng hai pattern này không cùng semantics**: pattern thứ nhất áp cấu trúc/length chặt hơn. Chỉ áp khi **hợp đồng API quy định rõ** input như vậy, và kiểm thử dữ liệu hợp lệ hiện tại trước khi thay.

### 5.3. Anchor, character class và độ dài hữu hạn

Các chiến thuật nên xét theo thứ tự:

1. Có thể không dùng regex? Dùng `Method`, `Path`, `Host` hoặc so sánh string.
2. Nếu cần regex, có thể dùng **character class** thay alternation?
3. Có thể giới hạn độ dài bằng `{min,max}`?
4. Có thể anchor để không phải dò tìm substring?
5. Có thể loại bỏ group/capture không sử dụng?
6. Có thể giới hạn input ngoài regex trước khi chạy?
7. Có test cho input hợp lệ, sai, rỗng, dài và “gần đúng” không?

Đặc biệt, so sánh một enum hữu hạn như `partner`/`internal` thường không cần regex tùy biến:

~~~java
private static boolean allowedChannel(String value) {
    return "partner".equals(value) || "internal".equals(value);
}
~~~

Mã trên dễ review, không có backtracking; tuy nhiên với route cấu hình YAML, một regex cố định `^(partner|internal)$` vẫn có thể là lựa chọn đủ đơn giản. Không tạo custom factory chỉ vì một pattern nhỏ chưa được đo là bottleneck.

### 5.4. Possessive quantifier và atomic group: chỉ khi đã chứng minh tương đương

Java có các dạng:

~~~regex
a*+
a++
(?>a+)
~~~

Chúng có thể giảm backtracking vì **không trả lại các ký tự đã ăn** theo cách greedy thông thường. Nhưng điều này cũng có thể thay đổi tập input được match nếu phần sau cần những ký tự đó. Không thay mọi `*` thành `*+` theo thói quen rồi tự nhận tối ưu an toàn.

Ví dụ:

~~~regex
a+a
a++a
~~~

Hai biểu thức **không tương đương** với input `aa`: bản possessive không nhường lại ký tự `a` cho phần cuối. Hãy đặt **test đúng/sai** trước benchmark, hoặc chọn thuật toán so sánh chuỗi đơn giản khi nghiệp vụ cho phép.

### 5.5. Regex deadline: timeout của HTTP không phải timeout CPU regex

Timeout kết nối/response downstream chỉ giới hạn một số thao tác mạng, **không ngắt được Java regex đang chạy CPU** một cách đáng tin. Một thread event loop đang thực hiện backtracking lâu có thể không kịp xử lý timer/cancellation.

Các lớp bảo vệ hiệu quả hơn:

- **Không cho regex nguy hiểm vào route definitions** (code review, static analysis, validation).
- **Giới hạn input size** trước khi regex chạy.
- Dùng cấu trúc so sánh tuyến tính, matcher tối giản hoặc một engine có bảo đảm hiệu năng phù hợp khi thực sự cần.
- Có load test với crafted near-miss input trong môi trường cách ly và timeout cho toàn bộ test process.
- Dùng quota/WAF ở edge để giảm lượng input bất thường, nhưng **không lấy rate limit thay cho sửa regex**.

## 6. Bố trí predicate: điều kiện chọn lọc, ít tốn trước

Một route có:

~~~yaml
predicates:
  - Path=/api/catalog/**
  - Method=GET
  - Header=X-Partner-Code,^[A-Za-z0-9_-]{1,32}$
  - Query=mode,^(full|summary)$
~~~

được diễn giải là **tất cả điều kiện phải đúng**. Về mặt lý thuyết, nếu các phép kiểm tra được ghép bằng `Predicate.and(...)` theo thứ tự, Java sẽ **short-circuit** khi gặp false, giúp bỏ qua phép kiểm tra sau. Tuy nhiên, **đừng coi thứ tự các dòng YAML là cam kết tối ưu tương đương ở mọi release, route source hoặc custom predicate**; cần xác minh chính xác cách Gateway materialize route và đo bằng test/profile.

### 6.1. Xét chi phí và xác suất fail

Giả sử một request đến:

| Điều kiện | Chi phí giả định | Tỉ lệ loại request |
| --- | ---: | ---: |
| `Method=GET` | Rất thấp | 30% |
| `Path=/api/catalog/**` | Thấp | 90% |
| `Header=X-Partner-Code,regex` | Trung bình | 20% trong số request còn lại |
| Custom predicate gọi dịch vụ ngoài | Rất cao | Không nên nằm trong route hot path |

Nếu có short-circuit như dự kiến, thường nên **để điều kiện rẻ và phân loại mạnh** sớm. Nhưng “rẻ nhất” không luôn tối ưu: điều kiện rẻ nhưng gần như luôn true có thể tiết kiệm ít hơn một Path predicate hơi tốn hơn nhưng loại 99% traffic.

Để đơn giản hóa, ta muốn giảm **expected evaluation cost**:

\[
E[T]=c_1+p_1c_2+p_1p_2c_3+\cdots
\]

với `c_i` là chi phí predicate thứ `i`, `p_i` là xác suất pass có điều kiện để đi tới bước sau. Công thức này giả định **thứ tự và short-circuit xác định**, không là phép đo Gateway thực tế.

### 6.2. Không đổi semantics chỉ để loại bớt predicate

Khi tối ưu route:

- Giữ `Method` nếu API không cho phép POST.
- Giữ `Host` nếu phân chia virtual hosts, dù client có thể tự khai Host trong HTTP.
- Giữ `Header` nếu đúng contract routing; không nhầm với authentication.
- Giữ `Query` nếu backend behavior phụ thuộc mode.
- Không đổi `Path=/api/admin/**` thành `Path=/**` chỉ để giảm chi phí.
- Không xóa security filters và backend authorization để p99 đẹp hơn.

Mọi tối ưu phải có **regression matrix** chứng minh request được phép vẫn vào đúng backend, request không hợp lệ không trượt sang route khác.

### 6.3. Nhiều tuyến có cùng pattern rộng sẽ tốn lần kiểm tra

Ví dụ một tập route:

~~~yaml
- id: route-a
  order: 10
  predicates:
    - Path=/**
    - Header=X-Service,^catalog$
- id: route-b
  order: 20
  predicates:
    - Path=/**
    - Header=X-Service,^billing$
- id: route-c
  order: 30
  predicates:
    - Path=/**
    - Header=X-Service,^shipping$
~~~

Tất cả routes đều chấp nhận path rất rộng và phân loại bằng header. Một kiến trúc **chỉ phụ thuộc client-controlled header** còn có rủi ro bảo mật; nếu giao thức cho phép, có thể chia theo path chính:

~~~yaml
- id: route-a
  order: 10
  predicates:
    - Path=/api/catalog/**
- id: route-b
  order: 20
  predicates:
    - Path=/api/billing/**
- id: route-c
  order: 30
  predicates:
    - Path=/api/shipping/**
~~~

Đây là **thiết kế lại contract URL**, không phải phép thay thế hoàn toàn tương đương. Chỉ áp dụng khi khách hàng chấp nhận path mới, backend/security policies được cập nhật và có migration plan.

### 6.4. Route order có thể cải thiện đường phổ biến nhưng thay routing behavior

Gateway có `order` để chọn giữa nhiều routes cùng match, thường order nhỏ được xét ưu tiên hơn. Đưa route phổ biến lên trước **có thể** giảm lượng đánh giá với traffic thường gặp, nhưng cũng có thể **chiếm traffic** vốn phải vào route chuyên biệt hơn.

Ví dụ:

~~~text
Route A: Path=/api/**             order=0
Route B: Path=/api/admin/**       order=10
~~~

Request admin có thể khớp Route A trước và không bao giờ đến Route B. Tối ưu đúng trước hết phải bảo đảm **route admin được chọn** (ví dụ order B nhỏ hơn A hoặc predicates tách biệt), không chỉ tối thiểu hóa số lần evaluate.

Đo chi phí cả **hit**, **miss**, và **overlap**; giữ route ID markers/recorded backend calls trong test.

## 7. Lab cấu hình: thay regex lồng nhau bằng regex đơn giản

Ta có một service `catalog-backend` HTTP tại `127.0.0.1:9191`. Contract của ví dụ:

- Chỉ chấp nhận `GET /api/catalog/**`.
- Request phải có `X-Catalog-Key` chứa **một hoặc nhiều** ký tự ASCII trong tập chữ cái, số, dấu gạch dưới và gạch ngang.
- Query `mode` phải là `full` hoặc `summary`.
- Header response có `X-Matched-Route: catalog` để xác minh route đã chọn.

Đây là **routing marker**, không phải authentication. Trong production, key/tokens thực phải được xác minh theo policy riêng.

### 7.1. Baseline: cấu hình kém cần thay

~~~yaml
# Gateway Server WebFlux 5.x - ví dụ CẦN CẢI THIỆN
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog
              order: 0
              uri: http://127.0.0.1:9191
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                # Nested repetition: không nên giữ pattern này.
                - Header=X-Catalog-Key,^([A-Za-z0-9_-]+)+$
                - Query=mode,^(full|summary)$
              filters:
                - AddResponseHeader=X-Matched-Route,catalog
~~~

Trong mẫu xấu, phần `([A-Za-z0-9_-]+)+` lồng hai repetitions bao cùng tập ký tự. Khi input gần khớp rồi thất bại, engine có thể thử nhiều nhánh backtracking.

### 7.2. Optimized: cùng ngôn ngữ giá trị, ít nhánh hơn

~~~yaml
# Gateway Server WebFlux 5.x - route tương ứng đã cải thiện
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog
              order: 0
              uri: http://127.0.0.1:9191
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - Header=X-Catalog-Key,^[A-Za-z0-9_-]+$
                - Query=mode,^(full|summary)$
              filters:
                - AddResponseHeader=X-Matched-Route,catalog
~~~

Với giá trị header theo contract, hai regex đều chấp nhận **một hoặc nhiều ký tự trong cùng tập ASCII**. Bản sau không còn repetition lồng. Cả hai đều **chưa giới hạn độ dài tối đa**: cần giới hạn ở edge hoặc dùng custom predicate với limit nếu nghiệp vụ yêu cầu.

**Không chạy cả hai route cùng ID/path trong một Gateway.** Lab thay lần lượt nội dung cấu hình trên cùng deployment test, khởi động lại/reload theo quy trình và xác nhận route runtime. Một lần chạy chỉ có **một** định nghĩa route `catalog`.

### 7.3. Namespace WebFlux 4.2/4.3

Với Gateway Server WebFlux 4.2/4.3 dùng prefix khác:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog
          uri: http://127.0.0.1:9191
          predicates:
            - Path=/api/catalog/**
            - Method=GET
            - Header=X-Catalog-Key,^[A-Za-z0-9_-]+$
            - Query=mode,^(full|summary)$
          filters:
            - AddResponseHeader=X-Matched-Route,catalog
~~~

Đừng trộn prefix `spring.cloud.gateway.routes` của WebFlux 4.x với `spring.cloud.gateway.server.webflux.routes` của WebFlux 5.x. Starter mới thường là `spring-cloud-starter-gateway-server-webflux`, trong khi một số dự án 4.x cũ dùng `spring-cloud-starter-gateway`; chọn **Spring Boot/Spring Cloud BOM tương thích** và kiểm tra route runtime thực tế.

### 7.4. Thử input đúng, sai và near miss

~~~bash
# Match route: 200 nếu backend sẵn sàng
curl -i "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "X-Catalog-Key: partner_42"

# Header sai charset: không match route này
curl -i "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "X-Catalog-Key: partner!"

# Query sai: không match route này
curl -i "http://127.0.0.1:8080/api/catalog/items/42?mode=other" \
  -H "X-Catalog-Key: partner_42"

# Method sai: không match route này
curl -i -X POST "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "X-Catalog-Key: partner_42"
~~~

Với **chỉ một route** và không có handler khác, negative cases thường về 404 (không nhất thiết 400/403). Khi có fallback route, negative có thể **được route khác nhận**. Do đó kiểm tra **route marker + backend request count**, không chỉ status.

Lệnh trên dùng input ngắn. **Không gửi chuỗi lặp hàng nghìn ký tự đến regex baseline nguy hiểm**. Muốn đánh giá ReDoS, phân tích pattern trước; nếu buộc kiểm thử sức chịu tải, thực hiện trong process/cgroup cô lập với input cap, deadline và khả năng dừng process.

### 7.5. Bảng regression trước và sau

| Case | X-Catalog-Key | mode | Method | Kỳ vọng cả hai cấu hình |
| --- | --- | --- | --- | --- |
| R1 | `partner_42` | `full` | GET | Khớp |
| R2 | `ABC-9` | `summary` | GET | Khớp |
| R3 | `a` | `full` | GET | Khớp |
| R4 | chuỗi rỗng | `full` | GET | Không khớp |
| R5 | `partner!` | `full` | GET | Không khớp |
| R6 | `partner_42` | `other` | GET | Không khớp |
| R7 | `partner_42` | `full` | POST | Không khớp |
| R8 | thiếu header | `full` | GET | Không khớp |
| R9 | `partner_42` | thiếu | GET | Không khớp |
| R10 | `partner_42` | `full` | GET, path khác | Không khớp |

Nếu regex mới thay đổi kết quả ở một case mà contract không thay đổi, **chưa thể gọi tối ưu hoàn tất**, kể cả p99 giảm. Cần thêm test cho Unicode, newline, duplicated headers và URL encoding theo lớp proxy thực tế.

## 8. Khi nào nên tạo custom RoutePredicateFactory?

Đối với một phép so sánh header chính xác, biểu thức `^partner$` thường đã đơn giản. Tuy nhiên nếu nhiều routes đang dùng regex chỉ để kiểm tra một giá trị cố định và cần **policy về độ dài và header trùng**, có thể viết custom factory để làm rõ contract và hạn chế regex.

Spring Cloud Gateway Server WebFlux hướng dẫn tạo component kế thừa `AbstractRoutePredicateFactory<Config>` và override `apply(Config)`.

### 8.1. Ví dụ: BoundedChannelRoutePredicateFactory

`src/main/java/demo/gateway/predicate/BoundedChannelRoutePredicateFactory.java`:

~~~java
package demo.gateway.predicate;

import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.function.Predicate;

import org.springframework.cloud.gateway.handler.predicate.AbstractRoutePredicateFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;

@Component
public final class BoundedChannelRoutePredicateFactory
        extends AbstractRoutePredicateFactory<
            BoundedChannelRoutePredicateFactory.Config> {

    private static final Set<String> ALLOWED =
            Set.of("partner", "internal");
    private static final int MAX_LENGTH = 16;

    public BoundedChannelRoutePredicateFactory() {
        super(Config.class);
    }

    @Override
    public Predicate<ServerWebExchange> apply(Config config) {
        // Đọc và validate config MỘT LẦN khi dựng predicate.
        String expected = Objects.requireNonNull(
                config.getExpected(), "expected");

        if (!ALLOWED.contains(expected)) {
            throw new IllegalArgumentException(
                    "Unsupported channel: " + expected);
        }

        // Lambda chạy cho từng request: không blocking I/O.
        return exchange -> {
            List<String> values = exchange.getRequest()
                    .getHeaders().get("X-Channel");

            // Contract: phải đúng MỘT giá trị header.
            if (values == null || values.size() != 1) {
                return false;
            }

            String actual = values.get(0);
            return actual != null
                    && actual.length() <= MAX_LENGTH
                    && expected.equals(actual);
        };
    }

    public static final class Config {
        private String expected;

        public String getExpected() {
            return expected;
        }

        public void setExpected(String expected) {
            this.expected = expected;
        }
    }
}
~~~

**Giải thích cơ chế:**

1. Spring tạo factory bean qua `@Component`.
2. Khi materialize route, `apply(config)` kiểm tra expected nằm trong allowlist.
3. Predicate trên mỗi request chỉ đọc danh sách `X-Channel`, giới hạn số values và độ dài, rồi so sánh bằng `String.equals`.
4. Không chạy regex, không cấp phát Matcher, không gọi Redis/HTTP/DB ở đường chọn route.
5. Nếu config có value ngoài allowlist, factory báo lỗi thay vì âm thầm chấp nhận.

**Lưu ý đổi semantics:** Built-in `Header=X-Channel,^partner$` có thể đánh giá các giá trị header khác nhau theo implementation; custom factory trên chủ động **từ chối nhiều header values**. Đó là một **thay đổi policy có chủ đích**, không thể coi hai implementation tương đương nếu chưa test duplicated headers.

### 8.2. Dùng factory qua YAML

Trên Gateway Server WebFlux 5.x:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: partner-catalog
              uri: http://127.0.0.1:9191
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - name: BoundedChannel
                  args:
                    expected: partner
              filters:
                - AddResponseHeader=X-Matched-Route,partner-catalog
~~~

Tên `BoundedChannel` được suy từ class `BoundedChannelRoutePredicateFactory` theo naming convention của Gateway. Dùng dạng `name/args` vì factory mẫu không khai báo shortcut fields. Với 4.2/4.3, chuyển namespace routes về `spring.cloud.gateway.routes`.

**Chỉ dùng custom factory khi có nhu cầu đã chứng minh**: nếu bản built-in đã nhanh, correct và đủ bảo mật, việc thêm một lớp Java/factory có thể làm tăng chi phí bảo trì hơn là giảm CPU thực.

### 8.3. Unit test không phụ thuộc HTTP server

~~~java
package demo.gateway.predicate;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;

import static org.assertj.core.api.Assertions.assertThat;

class BoundedChannelPredicateTest {
    @Test
    void acceptsOnlyOneShortApprovedValue() {
        var factory = new BoundedChannelRoutePredicateFactory();
        var config =
                new BoundedChannelRoutePredicateFactory.Config();
        config.setExpected("partner");
        var predicate = factory.apply(config);

        var good = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/catalog/items/42")
                        .header("X-Channel", "partner"));

        var missing = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/catalog/items/42"));

        var wrong = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/catalog/items/42")
                        .header("X-Channel", "Partner"));

        var repeated = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/catalog/items/42")
                        .header("X-Channel", "partner", "internal"));

        assertThat(predicate.test(good)).isTrue();
        assertThat(predicate.test(missing)).isFalse();
        assertThat(predicate.test(wrong)).isFalse();
        assertThat(predicate.test(repeated)).isFalse();
    }
}
~~~

Unit test này kiểm tra logic custom predicate, **không chứng minh YAML đã bind**, thứ tự route hoặc backend request. Một HTTP integration test vẫn cần chạy Gateway trên random port và dùng MockWebServer/WireMock kiểm tra route ID/đích thực tế.

### 8.4. Nếu cần regex động trong custom factory

Chỉ nên nhận pattern từ **configuration source đáng tin**, review/static validation và giới hạn độ phức tạp. Nếu config yêu cầu biểu thức cố định đã được phê duyệt, compile tại `apply(config)`:

~~~java
final Pattern accepted = Pattern.compile(config.getRegexp());
return exchange -> {
    String header = exchange.getRequest()
            .getHeaders().getFirst("X-Approved-Code");
    return header != null
            && header.length() <= 32
            && accepted.matcher(header).matches();
};
~~~

Đây là **đoạn minh họa riêng**, không phải phần bổ sung nguyên trạng vào class `BoundedChannelRoutePredicateFactory` (class đó không có `getRegexp()`). Nó mô tả chỗ compile an toàn hơn so với mỗi lần request, **không làm regex nguy hiểm trở nên an toàn**: nếu pattern có catastrophic backtracking, compile một lần vẫn có thể treo CPU trong `Matcher.matches()`.

## 9. Benchmark có phương pháp: không tối ưu dựa vào cảm giác

Một tối ưu predicate cần được đánh giá từ **microbenchmark** đến **HTTP integration/load test**. Hai loại đo trả lời các câu hỏi khác nhau:

| Tầng | Mục đích | Hạn chế |
| --- | --- | --- |
| Pure Java benchmark | So `String.equals`, compiled `Pattern`, repeated `Pattern.compile` | Không đo route selection, Netty, GC toàn ứng dụng |
| Gateway HTTP benchmark | Đo request hit/miss qua Gateway + stub backend | Bao gồm HTTP parsing, client/server/network và JVM warm-up |
| Production-like load | Đo p99, CPU, throughput, memory với tỷ lệ routes và traffic thực | Có nhiều yếu tố nhiễu; khó gán riêng chi phí predicate |
| CPU profiling/JFR | Phát hiện regex/backtracking hoặc allocation trong hot path | Sampling overhead, cần giải thích đúng call stack |
| Regression/integration | Chứng minh cùng route/headers/backend được chọn | Không tự chứng minh nhanh hơn |

### 9.1. Microbenchmark bằng JMH

JMH giúp đo hot-path Java sau warm-up, tránh một số sai lầm phổ biến của tự dùng `System.nanoTime()` vài lần.

Ví dụ class trong **một benchmark module riêng**:

~~~java
package demo.benchmark;

import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 3)
@Measurement(iterations = 5)
@Fork(2)
public class ChannelMatchBenchmark {

    private static final Pattern CHANNEL_PATTERN =
            Pattern.compile("^partner$");

    @Param({"partner", "other", "partnerX"})
    public String value;

    @Benchmark
    public boolean stringEquals() {
        return "partner".equals(value);
    }

    @Benchmark
    public boolean precompiledRegex() {
        return CHANNEL_PATTERN.matcher(value).matches();
    }

    @Benchmark
    public boolean compileOnEveryCall() {
        return Pattern.matches("^partner$", value);
    }
}
~~~

Để chạy JMH, thêm `jmh-core` và annotation processor `jmh-generator-annprocess` theo phiên bản JMH tương thích, cấu hình benchmark plugin/harness riêng. Bài này **không chạy benchmark**, nên không đưa ra số nanoseconds đo được.

Các phương thức trên có cùng **logic mong muốn** với ba giá trị test: chỉ `partner` hợp lệ. Tuy nhiên kết quả benchmark không phải cam kết rằng built-in `HeaderRoutePredicateFactory` sẽ nhanh/chậm tương tự, vì factory có xử lý HTTP header và route composition riêng.

**Cảnh báo về JIT:** Với benchmark nhỏ, HotSpot có thể inline/constant-fold một số nhánh; dùng đủ parameter values, warm-up, multiple forks và kiểm tra profiler. Tránh chạy JMH chung lúc CPU của CI runner đang bị chia sẻ quá tải; so sánh trên cùng máy/cấu hình/GC/JDK.

### 9.2. Không cho regex nguy hiểm chạy stress vô hạn

Một sai lầm là dùng `^([A-Za-z0-9_-]+)+$` rồi thử chuỗi 10.000 ký tự gần khớp để “đo chênh lệch”. Nếu có ReDoS, một iteration có thể giữ CPU rất lâu và làm CI/hệ thống test bị treo.

Hãy:

- Kiểm tra bằng code review/static analysis trước.
- Chỉ dùng input ngắn có giới hạn nếu cần chứng minh regression.
- Dùng pattern mới an toàn để đo throughput với input dài hợp lệ.
- Kiểm thử stress liên quan ReDoS trong **môi trường cô lập có giới hạn tài nguyên**, deadline và khả năng dừng process, không trên public gateway.

### 9.3. HTTP load test: ba nhóm request bắt buộc

Một bài đo Gateway nên có:

| Nhóm | Request | Ý nghĩa |
| --- | --- | --- |
| **Hit** | `GET /api/catalog/items/42?mode=full`, header key hợp lệ | Route match + backend response |
| **Miss-path** | `GET /not-a-route?mode=full` | Chi phí route matching khi không match |
| **Miss-near-regex** | Đúng path/method/query nhưng header sai ngắn | Route candidate đi tới regex rồi miss |
| **Overlap** | Nhiều routes cùng có thể match | Route order và chi phí ứng viên |
| **Long-but-bounded** | Header dài trong giới hạn được phê duyệt | Allocation/CPU khi input gần giới hạn |

Benchmark chỉ request hit có thể che giấu vấn đề ở miss-path khi Internet bots scan URI, hoặc ở miss-near-regex khi client gửi giá trị không hợp lệ.

### 9.4. Cố định các yếu tố gây nhiễu

1. Cùng JVM/JDK patch, Spring Boot, Gateway BOM và OS/kernel.
2. Cùng cấu hình Netty event loops, connection pool, heap/direct memory và GC.
3. Cùng backend stub trả response nhanh, ổn định; không gọi Internet.
4. Cùng TLS mode (HTTP trong lab, TLS riêng ở production-like).
5. Cùng số routes, order, filters, retry/rate-limit/security policy.
6. Cùng concurrency/arrival-rate và tỷ lệ hit/miss/near-miss.
7. Warm-up đủ và thu **nhiều lần lặp**.
8. Không bật DEBUG wiretap/logging request ở một bên rồi tắt bên kia.
9. Không thay route predicates và backend/client pool cùng lúc nếu muốn suy ra nguyên nhân.
10. Chạy positive/negative routing tests trước và sau để bảo đảm benchmark **đo cùng chức năng**.

**Không so sánh trực tiếp p99 từ hai đợt load có traffic mix khác nhau.** Một route hẹp có thể trả 404 nhanh hơn vì không proxy nữa, nhưng đó là thay đổi semantics chứ không đơn thuần giảm CPU.

### 9.5. Những số đo cần giữ

| Metric | Vì sao quan trọng? | Điều cần cảnh giác |
| --- | --- | --- |
| Requests/sec và status theo class | Throughput và tỷ lệ kết quả mong muốn | 404 negative test không phải lỗi hệ thống |
| p50/p95/p99 HTTP latency | Tail latency dưới concurrency | p99 nhiễu nếu sample quá nhỏ |
| Gateway CPU usage / CPU seconds per request | Chi phí xử lý một request | CPU throttling/steal trong container |
| Allocations/s, GC pause | Regex/strings/matchers có tạo object quá nhiều? | Heap/GC khác gây kết quả lệch |
| Reactor Netty event-loop lag | Phát hiện predicate sync giữ thread lâu | Cùng workload mới so được |
| Downstream call count | Phát hiện route sai/retry vô tình | Một client request có thể retry nhiều lần |
| Route hit distribution | Kiểm tra route order/fallback | Route miss có thể không xuất hiện ở route metrics |
| Header/URI size rejected | Kiểm tra input cap | Không log raw input có secret |

Trên WebFlux, **predicate synchronous tốn CPU có thể làm nghẽn Netty event-loop**. Regex lâu không chỉ ảnh hưởng request đang xử lý mà còn trì hoãn các request khác chung event-loop. Không xem `subscribeOn(boundedElastic())` như “sửa mọi predicate”: route predicate thông thường là synchronous, và chuyển thread không tự giải quyết ReDoS hoặc bảo đảm bảo toàn route semantics.

## 10. Quan sát routing mà không tự tạo bottleneck mới

### 10.1. Gateway metrics không nhất thiết đo riêng thời gian predicate

Spring Cloud Gateway cung cấp metric như `spring.cloud.gateway.requests` thông qua Gateway metrics filter khi đã thêm Actuator và bật metrics theo release. Metric này tập trung vào requests **được route/filter chain xử lý**, thường có route ID, status, method, outcome.

Nhưng một request **không khớp bất kỳ route nào** có thể không đi qua Gateway metrics filter. Vì vậy **không dùng riêng metric này để kết luận tổng số requests Gateway nhận hoặc chi phí route predicate miss**.

Muốn quan sát toàn bộ:

- Netty HTTP server metrics hoặc một WebFilter/observation ở tầng nhận request thích hợp.
- Gateway route-level metrics cho request đã chọn route.
- Backend/stub metrics để phân biệt requests đã forward.
- JFR/CPU sampling cho stack `Pattern.matcher`, route predicates hoặc custom code.

### 10.2. Ví dụ bật metrics trên WebFlux Gateway 5.x

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          metrics:
            enabled: true

management:
  server:
    address: 127.0.0.1
    port: 9090
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus"
~~~

Ví dụ giả định có `spring-boot-starter-actuator`. Muốn có `/actuator/prometheus` cần thêm `micrometer-registry-prometheus`. Endpoint có thể yêu cầu authentication tùy Security config; **không expose management port này ra Internet**.

Bảng Config Props Gateway WebFlux 5.x liệt kê `spring.cloud.gateway.server.webflux.metrics.enabled`. Với Gateway 4.x, tên property/default có thể khác; phải đối chiếu config metadata và xác nhận metrics thực sự có dữ liệu.

### 10.3. Tránh high cardinality khi đo

**Không bật path tags chứa toàn bộ URI của người dùng** chỉ để đo predicate: hàng triệu giá trị `/items/{id}` có thể tạo nhiều time series. Tương tự, không gắn raw header values, session ID, token, user ID hoặc query string làm labels.

Ưu tiên labels giới hạn:

~~~text
routeId = catalog
method = GET
status = 200
outcome = SUCCESS
requestClass = hit | miss-path | miss-regex
~~~

`requestClass` là nhãn **tự thiết kế**, không phải mặc định Gateway. Nếu cần phân loại request miss, instrumentation nên ở lớp thích hợp trước routing, có sampling/limits. Không biến metrics thành raw request logging.

### 10.4. Dùng JFR/CPU profiler khi cần quy trách nhiệm

Khi p99 tăng nhưng backend stub phản hồi nhanh:

1. Đo Gateway process CPU/throttling.
2. Thu CPU profile có sampling trong **môi trường được cấp phép**.
3. Tìm stack liên quan `java.util.regex.Pattern`, `Matcher`, factory hoặc custom predicate.
4. Quan sát allocations của `Matcher`/strings/buffers.
5. So cùng workload và cùng JDK với baseline.
6. Xử lý pattern/input cap trước khi điều chỉnh số thread.

Không bật Netty wiretap body/header trong production để “đo hiệu năng” vì vừa có nguy cơ lộ cookie/token vừa làm sai kết quả benchmark. Logging từng predicate trong hot path cũng dễ trở thành overhead mới.

### 10.5. Instrument custom predicate có giới hạn

Nếu muốn đếm số lần custom predicate được gọi, có thể dùng Micrometer `Counter` đăng ký **một lần theo route ID/factory name**, không tạo meter với label riêng cho từng request.

~~~java
// Pseudocode - meter đã đăng ký trong component:
predicateEvaluations.increment();
return cheapCheck(exchange);
~~~

Đây chỉ là ý tưởng. **Không coi `Counter.increment()` miễn phí**: trong benchmark nóng, instrumentation dày cũng có thể thay đổi kết quả. Đo JFR sampling và baseline không instrumentation để đối chiếu.

## 11. Cấu hình route quy mô lớn: tránh nhân chi phí vô ích

### 11.1. Số route runtime không chỉ đến từ application.yml

Gateway có thể nhận definitions từ:

- Static YAML/properties.
- Java `RouteLocator` beans.
- Config Server hoặc repository động.
- Discovery locator (tự sinh routes từ service registry).

Vì vậy, chỉ đếm số entry trong `application.yml` không phản ánh đúng số route runtime. Một Gateway bật discovery có thể tạo thêm nhiều routes, trong khi mỗi replica có revision/cache khác.

Hãy ghi nhận **route count + route IDs/order + predicates thực tế** bằng công cụ quản trị được bảo vệ. Khi deploy nhiều replicas, kiểm tra từng instance nếu nghi có drift.

### 11.2. Tối ưu route topology thay vì rewrite regex bằng tay

Một số đề xuất kiến trúc:

| Hiện tượng | Cách tiếp cận | Lưu ý |
| --- | --- | --- |
| Nhiều routes dùng `Path=/**` và lọc bằng header regex | Chia path theo dịch vụ khi hợp đồng cho phép | Có thể thay public API contract; cần migration |
| Nhiều routes trùng predicate và URI | Hợp nhất nếu semantics thực sự giống nhau | Giữ filter/security/quota từng nhánh |
| Duplicate service-discovery routes | Kiểm tra discovery locator config, route ID generation | Không xóa routes cần thiết cho service |
| Nhiều regex parse cùng một header | Cân nhắc validate một lần ở edge hoặc custom logic có cache per-request | Không tạo cache global chứa credential |
| Route ưu tiên thấp nhưng match rất rộng | Tách fallback rõ ràng và đặt order đúng | Không cho fallback bypass auth |
| Traffic xấu phần lớn vào unknown paths | Edge WAF/ingress policy, rate limiting có căn cứ | Không thay thế sửa regex ReDoS |

Tập trung giảm **candidate evaluations** và **work per evaluation** mà vẫn bảo toàn semantics. Nếu business API contract yêu cầu một số routes phân loại bằng Header/Query, đừng buộc người dùng đổi URL chỉ vì một giả thuyết hiệu năng chưa đo.

### 11.3. Route cache không phải memoization kết quả cho từng request

Gateway Server WebFlux có route definition/runtime caching. Khi route definitions đã materialize, điều đó **không nghĩa** kết quả `matches(exchange)` của mọi incoming request được lưu toàn cục.

Không nên tự tạo map:

~~~java
// Ý tưởng SAI: user khác có thể dùng cùng path nhưng khác token/host.
Map<String, Boolean> matchedByPath = new HashMap<>();
~~~

Nếu route còn phụ thuộc Host, method, header, query, time, IP hoặc auth context, cache theo **path đơn độc** sẽ chọn sai route. Một cache key đầy đủ thì rất dễ high cardinality, chi phí bộ nhớ lớn và rủi ro lưu dữ liệu nhạy cảm; thường không phải tối ưu an toàn.

### 11.4. Dynamic route refresh không tự tăng tốc regex

`RefreshRoutesEvent` hay `POST /actuator/gateway/refresh` yêu cầu làm mới route cache từ nguồn hiện có, **không sửa một regex xấu** và không bảo đảm tất cả Gateway replicas lập tức dùng revision mới.

Nếu thay regex cũ bằng mới trong production:

1. Validate cấu hình và regex trước commit.
2. Commit nguồn route definitions có version/rollback.
3. Refresh mỗi Gateway replica theo cơ chế điều phối.
4. Xác minh route runtime đã chứa pattern revision mới.
5. Chạy positive/negative và canary traffic.
6. Theo dõi p99/CPU, lỗi mapping, backend destination.

Không lẫn “cache đã refresh” với “tối ưu đã có hiệu quả” trước khi đo workload thực tế.

## 12. Tối ưu predicate theo đúng ranh giới bảo mật

### 12.1. Header/Host không phải danh tính đã được xác minh

Ví dụ:

~~~yaml
predicates:
  - Host=admin.example.test
  - Header=X-Internal-User,^true$
~~~

không tự có nghĩa request đã được xác thực. Client có thể tự gửi Host/Header trong nhiều đường mạng. Vì vậy, **đừng xóa Spring Security**, backend authorization, mTLS hoặc allowlist mạng chỉ vì route match “rất nhanh”.

Routing predicate chọn đường đi; **authentication và authorization** đánh giá ai được quyền làm gì. Cần test các lớp riêng.

### 12.2. X-Forwarded-* và chi phí xử lý IP

`RemoteAddr` có thể kiểm tra CIDR theo remote socket address. Nếu Gateway sau ingress, remote peer thường là proxy; `XForwardedRemoteAddr`/custom resolver phải xét **chuỗi proxy đáng tin**, không mặc định tin giá trị XFF client tự gửi.

Khi tối ưu:

- Không thay `RemoteAddr` bằng string prefix của XFF vì “nhanh hơn”.
- Không chọn `trustAll` chỉ để bỏ xác minh proxy chain.
- Đo trong topology ingress thật và test header giả.
- Nếu IP allowlist là security boundary, đặt thêm kiểm soát ở network/edge, không chỉ một predicate.

### 12.3. Request body, cookie và payload nhạy cảm

`ReadBody` predicate có thể decode và cache body trước routing; đây là thao tác thường tốn hơn Method/Path. Nếu cần xác định API theo thông tin trong JWT/cookie/body:

- Cân nhắc đổi contract để metadata route không phụ thuộc nội dung body lớn.
- Giới hạn body size và content type.
- Bảo vệ dữ liệu nhạy cảm, tránh cache/log payload không cần thiết.
- Kiểm tra request body có thể đọc tiếp ở filter/backend sau predicate.
- Không coi regex trên cookie là session authentication.

Một predicate đọc JSON để chỉ tìm một `"type"` field có thể kéo theo decode toàn payload. Nếu phải làm vậy, cần chứng minh chi phí chấp nhận được và xử lý malformed/large bodies. Không sao chép cùng việc parse payload ở nhiều predicates.

### 12.4. Rate limiting và Retry có thể che giấu kết quả benchmark

Nếu request rate limiter chạy sau route match, nó vẫn có overhead Redis/key resolution trong các request được chọn. Retry có thể tạo **nhiều downstream attempts cho một incoming request**. Do đó:

- Trong benchmark tập trung predicate, dùng stub backend và loại bỏ hoặc cố định những bộ lọc không liên quan ở **cả hai cấu hình**.
- Trong load test production-like, giữ nguyên security/rate limiting/circuit breaker/retry và đo end-to-end.
- Không tắt limiter/auth trên production để thử “regex nhanh hơn” nếu làm vậy mở đường tấn công.
- Khi performance tăng, xem số downstream attempts có giảm do định tuyến sai/fail sớm hay không.

## 13. Kiểm thử hồi quy: nhanh hơn nhưng phải đúng route

### 13.1. Ba yêu cầu để gọi là tối ưu thành công

Một thay đổi predicate chỉ đạt khi:

1. **Correctness:** tập request hợp lệ/không hợp lệ được route xử lý đúng như hợp đồng đã phê duyệt.
2. **Safety:** không còn regex nguy hiểm hoặc input không giới hạn có thể làm CPU treo; không mở đường truy cập trái phép.
3. **Performance:** có bằng chứng CPU/allocation/tail latency cải thiện đủ ý nghĩa dưới workload đại diện.

**Không dùng HTTP 200 duy nhất để kết luận correctness**: request có thể match nhầm fallback route, backend khác hoặc controller local.

### 13.2. Ma trận test tương đương hai regex

Hai mẫu trong mục 7:

~~~regex
^([A-Za-z0-9_-]+)+$
^[A-Za-z0-9_-]+$
~~~

được dùng để chứng minh giảm repetition lồng trong cùng contract. Một tập test nhỏ, deterministic:

~~~java
package demo.gateway.predicate;

import java.util.List;
import java.util.regex.Pattern;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class RegexEquivalenceTest {

    private static final Pattern LEGACY =
            Pattern.compile("^([A-Za-z0-9_-]+)+$");
    private static final Pattern OPTIMIZED =
            Pattern.compile("^[A-Za-z0-9_-]+$");

    @Test
    void bothPatternsAgreeForSmallRepresentativeInputs() {
        List<String> inputs = List.of(
                "a", "abc", "A9_2", "CAT-007",
                "", "bad!", "hello world", "é", "Z?");

        for (String value : inputs) {
            boolean before = LEGACY.matcher(value).matches();
            boolean after = OPTIMIZED.matcher(value).matches();
            assertThat(after)
                    .as("Different decision for: " + value)
                    .isEqualTo(before);
        }
    }
}
~~~

Đây là **unit test nhỏ có giới hạn input**; nó không chứng minh tương đương cho mọi chuỗi có thể có theo hình thức toán học, và không được dùng để chạy input dài đối với regex legacy. Với mẫu đơn giản này, review cấu trúc regex là bằng chứng chính; test giúp bắt lỗi khi sửa syntax.

### 13.3. Test sau khi thay `Header` bằng custom factory

Custom `BoundedChannelRoutePredicateFactory` từ mục 8 có policy **reject duplicated headers** và giới hạn chiều dài. Viết bảng test rõ:

| Request header | Built-in `Header=X-Channel,^partner$` | Custom `BoundedChannel(expected=partner)` |
| --- | --- | --- |
| `X-Channel: partner` | Khớp theo contract | Khớp |
| `X-Channel: Partner` | Không khớp (case-sensitive) | Không khớp |
| Thiếu `X-Channel` | Không khớp | Không khớp |
| `X-Channel: partnerX` | Không khớp | Không khớp |
| Hai giá trị `partner` và `internal` | Phụ thuộc cách built-in xử lý multiple values | **Không khớp** có chủ đích |
| Giá trị dài hơn 16 | Tùy regex | Không khớp theo input cap |

Đừng ghi vào tài liệu vận hành rằng hai cách có “cùng semantics hoàn toàn” nếu duplicated headers và input cap khác. Việc giới hạn đầu vào phải được thống nhất với API client và backend.

### 13.4. Integration test qua HTTP Gateway thật

Dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` kết hợp `WebTestClient` và backend stub cổng ngẫu nhiên (ví dụ MockWebServer hoặc WireMock). Với request hợp lệ:

~~~java
client.get()
        .uri("/api/catalog/items/42?mode=full")
        .header("X-Catalog-Key", "partner_42")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
                "X-Matched-Route", "catalog");
~~~

Đây là **đoạn assertion tích hợp**, giả định `client` được bind đến Gateway HTTP server và backend stub đang trả 200. Trong test hoàn chỉnh cần xác nhận **backend received request** (method/path/headers, request count) và không có retry ngoài dự kiến.

Các negative cases như header `partner!`, thiếu `mode`, sai method/path phải:

- Không được chọn route `catalog` (không có marker tương ứng).
- Không gửi downstream request tới backend của route này **trong fixture chỉ có route này**.
- Nếu có fallback, xác nhận route fallback ID/đích thay vì ép mọi negative trả 404.

### 13.5. Property tests và boundary input

Một bộ test khá mạnh có thể sinh ngẫu nhiên **có seed cố định** các chuỗi ASCII độ dài 0–64 để đối chiếu trước/sau tối ưu. Phân loại:

~~~text
length=0
length=1
length=16
length=32
length=33
contains disallowed punctuation
contains spaces
contains Unicode
repeated headers
duplicate query values
different Host/method/path
~~~

**Chỉ dùng input ngắn/bounded với legacy regex nguy hiểm**. Với pattern an toàn mới, có thể kiểm tra dài hơn trong giới hạn mà Gateway cho phép để xác minh giới hạn input và error handling. Seed/report giúp tái hiện failure, không dựa vào một lần random không lưu seed.

### 13.6. Khi một test “nhanh hơn” vì bỏ filter

Nếu sau tối ưu:

~~~text
Trước: 200 OK + JWT authorized + backend request
Sau:   404 Not Found và không gọi backend
~~~

latency có thể giảm mạnh, nhưng kết quả **sai**. Tương tự, một route match wildcard đã bỏ `Method=POST` có thể trả 200 nhanh vì backend GET cache, trong khi API trước đây cần ghi dữ liệu.

Vì vậy benchmark cần tỷ lệ **functional success theo từng nhóm input**, không chỉ aggregate latency của tất cả responses.

## 14. Regex không chỉ ở predicate: phân biệt với RewritePath và filters

Các lớp sau cũng có thể dùng regex:

- `RewritePath` GatewayFilter biến đổi đường dẫn **sau khi route đã match**.
- `RewriteResponseHeader` biến đổi response header theo mẫu.
- Custom security/validation filters có thể chạy regex trên JWT claims, Host, path hoặc body.
- Servlet/WebFlux filters ở lớp khác cũng có thể kiểm tra input.

Nếu CPU profile hiển thị `Pattern.matcher` ở `RewritePath`, sửa predicate `Header` có thể không tạo cải thiện.

### 14.1. So sánh hai vị trí

~~~text
Incoming request
    ↓
Path/Header/Query RoutePredicateFactory  ← chọn route, cost thuộc matching
    ↓
GatewayFilter: RewritePath(regex)         ← sửa URI, cost thuộc filter
    ↓
NettyRoutingFilter → backend
~~~

Đừng biến một filter regex thành predicate khác chỉ để giảm CPU: chúng có **mục đích khác nhau**. Muốn bỏ một bước rewrite, có thể thay đổi contract public path/backend URI hoặc dùng `StripPrefix`/`SetPath` nếu tương đương. Việc này cần test URL encoding, path variables và route priority.

### 14.2. Khi nào StripPrefix có thể thay RewritePath?

Nếu yêu cầu chỉ bỏ một segment đầu:

~~~text
Client:  /api/orders/42
Backend: /orders/42
~~~

Một `StripPrefix=1` có thể đơn giản hơn regex:

~~~yaml
filters:
  - StripPrefix=1
~~~

Tuy nhiên, nếu rewrite phải đổi cấu trúc phức tạp, chuyển tên segment, giữ query hoặc thay suffix khác, `StripPrefix` không tương đương. **Test chính xác path backend nhận**, nhất là encoded slashes và repeated slashes.

Không khẳng định mọi built-in filter không dùng regex đều có latency tốt hơn trong mọi release: benchmark theo implementation và workload thật.

### 14.3. Regex của security filter vẫn phải được review

Đặc biệt nguy hiểm là các biểu thức regex do **người vận hành nhập qua control plane** để kiểm tra headers mà client có quyền điều khiển. Nếu API admin cho phép khai báo `Header=...` / `RewritePath=...` không qua validation, một mẫu xấu có thể bị đưa lên nhiều replicas cùng lúc.

Control plane nên có:

1. Schema và allowlist factory names/arguments.
2. Validation cú pháp regex, whitelist pattern constructs hoặc static ReDoS checks.
3. Input caps ở ingress và ở custom predicates.
4. Approval/audit + revision/rollback.
5. Test correctness trước khi phát route refresh.
6. Theo dõi CPU/event-loop sau rollout.

**Đừng cho public request tự cung cấp regex để compile trong Gateway**. Một route predicate lấy regex từ request trực tiếp vừa là nguy cơ ReDoS vừa khiến client tự điều khiển routing policy.

## 15. Xử lý sự cố hiệu năng predicate

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| CPU tăng khi request có header lạ | Regex trên header có nested repetition/backtracking | CPU profile, xem pattern, input cap |
| p99 tăng nhưng backend latency không đổi | Route scanning hoặc predicate/filter synchronous | JFR, Gateway hit/miss mix, event-loop lag |
| Gateway chậm nhiều khi trả 404 | Nhiều route candidates không match | Đo miss-path, đếm runtime routes, route order |
| Request GET thường nhanh, query hiếm chậm | `Query` regex hoặc duplicate parameter values | Test gần-match, query length/quantity |
| Sau thêm nhiều routes, CPU/request tăng | Số ứng viên/route predicate calls tăng | So route ID/count, topology, flame graph |
| Regex benchmark nhanh nhưng Gateway vẫn chậm | Nút nghẽn TLS/Redis/filter/Netty/GC | So microbenchmark và HTTP/JFR |
| Thay `^([A-Za-z]+)+$` thành `^[A-Za-z]+$` vẫn không cải thiện | Regex không phải hot path hoặc input luôn ngắn | Tìm bottleneck trước tối ưu tiếp |
| CPU không giảm khi chuyển sang custom predicate | Factory đã compile tối ưu; overhead ở nơi khác | Kiểm tra profiling thực và test correctness |
| Header dài bị 431/400 trước Gateway route | HTTP server/ingress từ chối vì size cap | Phân biệt HTTP parse reject và predicate miss |
| Gateway bắt đầu nhận route không mong muốn | Đổi regex/wildcard rộng, mất `Method`/`Host` | Routing regression matrix, backend markers |
| Route hợp lệ bị từ chối sau thêm length cap | API contract cũ cho input dài hơn | Xác minh max length, migration và client impact |
| Khi refresh routes, có node vẫn CPU cao | Replica chưa nhận regex revision mới | Applied route revision từng node, refresh logs |
| Benchmark 404 tăng nhanh bất thường | Test đang đo fast-fail thay vì route hit | Phân loại status và backend calls |
| Thông lượng giảm khi bật DEBUG | Log format/IO hoặc wiretap làm nghẽn | So logs profile, sampling, tắt raw request logs |
| Event-loop bị giữ lâu ở `Matcher.matches()` | Input gần-match gây backtracking | Rollback pattern, chặn input ở edge, review ReDoS |
| Memory tăng sau thêm `ReadBody` | Body decode/cache trong route matching | Payload cap, codec, concurrency, profiling |
| Metrics tăng số time series đột biến | Raw path/query/token làm label | Xóa high-cardinality tags, giới hạn labels |
| Host/RemoteAddr tối ưu nhưng auth bị bypass | Predicate bị dùng thay security policy | Tách Spring Security/authorization và route tests |

### 15.1. Runbook chẩn đoán có thứ tự

1. **Xác nhận route runtime**: route IDs, `order`, predicates, version; có route mới/dynamic discovery không?
2. **Xác nhận workload**: bao nhiêu hit, miss, near miss, malformed, input dài?
3. **Tách downstream**: dùng stub backend nhanh và kiểm tra số downstream calls.
4. **Đo server side CPU**: có saturation/throttling không?
5. **CPU profile**: phần trăm samples ở regex/predicate so với filter/transport?
6. **Kiểm tra regex**: có nested repetition/overlapping alternation, `.*` rộng hoặc pattern do user nhập?
7. **Kiểm tra input caps** ở ingress/Netty và trong custom predicate.
8. **Thực hiện thay đổi nhỏ nhất** có thể giữ semantics.
9. **Chạy regression + performance** với cùng test profile/arrival rate.
10. **Rollout có thể rollback** và giám sát p99, CPU, 4xx/5xx, route selection trong production-like.

Không bật unrestricted Gateway Actuator ra Internet để điều tra. Một management endpoint chỉ đọc và được bảo vệ là đủ để quan sát route inventory khi cần; quyền ghi/refresh phải qua control plane an toàn.

## 16. Thiết kế thử nghiệm A/B không tự đánh lừa mình

### 16.1. Phân nhóm traffic rõ ràng

| Nhóm | Tỷ trọng ví dụ | Điều kiện | Kết quả mong muốn |
| --- | ---: | --- | --- |
| H1 | 50% | Path + Method + Header + Query hợp lệ | Match route + backend 200 |
| M1 | 20% | Path ngoài route | Không match route |
| M2 | 15% | Đúng Path/Method nhưng Header sai ngắn | Không match |
| M3 | 10% | Đúng Path/Method/Header nhưng Query sai | Không match |
| B1 | 5% | Input hợp lệ gần độ dài giới hạn | Match đúng, độ trễ ổn định |

Đây là **mix giả định phục vụ thiết kế benchmark**, không phải tỉ lệ traffic của một hệ thống thật. Nếu log production cho thấy 90% requests là miss-path, hãy điều chỉnh test mix theo thực tế.

**Đầu ra cần ghi:** số lượng từng nhóm, response status, route marker, downstream calls, p95/p99, CPU/container throttling, allocations và phiên bản cấu hình. Không gộp tất cả status thành một trung bình không có phân nhóm.

### 16.2. Điều kiện thí nghiệm để so sánh công bằng

Một phương án:

~~~text
Build A: Gateway 5.x, legacy regex (chỉ traffic test nhỏ đã kiểm soát)
Build B: cùng binary/dependencies, optimized regex

Warm-up:
  cùng số requests, cùng arrival rate, backend trả cùng body

Measurement:
  cùng traffic mix, cùng số routes, cùng CPU/memory limits
  thu nhiều lần lặp, ghi confidence/variance nếu có

Correctness gate:
  cùng route ID / backend destination
  cùng allow/deny decisions
  cùng bảo mật CORS/CSRF/rate limit theo contract

Performance gate:
  so CPU/request, p95/p99, failed/timeout rates
~~~

Chỉ nên chạy A với pattern legacy nguy hiểm **trong môi trường cô lập và input ngắn đã review**, không đưa traffic crafted gần-match dài vào Gateway đang phục vụ người dùng. Nếu đã biết regex có ReDoS, **ưu tiên sửa ngay** theo quy trình kiểm soát thay đổi thay vì giữ lại cho một benchmark production.

### 16.3. Kết quả mẫu để báo cáo — không phải số liệu đã đo

| Trường | Baseline | Optimized | Đánh giá |
| --- | --- | --- | --- |
| Config revision | `v1` | `v2` | Xác nhận code/BOM giống nhau |
| Route count | Điền từ runtime | Điền từ runtime | Phải bằng nhau nếu chỉ đổi regex |
| CPU seconds / 1k requests | Đo | Đo | Giảm mới là tín hiệu tốt |
| p99 hit | Đo | Đo | Không tăng quá SLO |
| p99 miss | Đo | Đo | Có thể nhạy hơn với matching cost |
| Backend attempts | Đo | Đo | Không đổi ngoài dự định |
| Route match regression tests | PASS/FAIL | PASS/FAIL | Bắt buộc PASS |
| ReDoS/static analysis | Có cảnh báo? | Có cảnh báo? | Không deploy pattern nguy hiểm |

Đừng điền số liệu ước lượng như thể benchmark thật. Kết quả tốt ở laptop cũng **chưa xác nhận** kết quả tương đương trong container có CPU throttling, nhiều routes và TLS.

### 16.4. Khi không thấy cải thiện

Nếu CPU vẫn cao nhưng JFR không còn nhiều samples ở regex:

- Kiểm tra path matching và số routes thực sự được đánh giá.
- Kiểm tra codec/serialization, Netty HTTP client pooling, DNS/TLS.
- Kiểm tra limiter Redis và timeout/retry budget.
- Kiểm tra access logs, tracing exporters, metric tags.
- Kiểm tra allocation/GC và Netty direct memory.

Không tiếp tục “tối ưu regex” chỉ vì đó là mục tiêu ban đầu nếu dữ liệu cho thấy bottleneck đã chuyển sang nơi khác.

## 17. Checklist đưa predicate tối ưu lên production

- [ ] Đã xác định route matching thực sự là hot path bằng benchmark/profile, không suy từ cảm giác.
- [ ] Đã phân biệt chi phí predicate với GatewayFilter, Spring Security, Redis và transport.
- [ ] Số routes/runtime sources đã được kiểm tra, không chỉ đếm entry trong YAML.
- [ ] Các predicate kết hợp AND/OR đúng contract; route priority/overlap không thay đổi ngoài ý muốn.
- [ ] Ưu tiên `Method`/`Path`/`Host`/CIDR/Query presence khi đúng semantics, tránh regex tự chế.
- [ ] Các regex Java được review cho nested repetition, overlapping alternation, backreferences và backtracking.
- [ ] Input lengths/số headers/số query parameters có giới hạn tại edge/server và nơi cần thiết trong custom code.
- [ ] Không nhận regex tùy ý từ public request.
- [ ] Dùng `Pattern` compile sẵn khi có custom regex dùng lặp lại; không share `Matcher` giữa threads.
- [ ] Không tự tạo cache route match theo path đơn độc khi còn Host/Header/Method/Query/IP.
- [ ] Không gọi DB/Redis/HTTP/blocking I/O trong custom predicate synchronous.
- [ ] Không thay cấu trúc Gateway Server WebFlux bằng Web MVC classes hoặc ngược lại.
- [ ] Regex có dấu phẩy trong shortcut arguments dùng `name/args` để tránh binding sai.
- [ ] Cả trước/sau đổi regex đều vượt qua unit test, route integration test và security tests.
- [ ] Negative cases kiểm tra route **không** match/không forward khi fixture chỉ có một route.
- [ ] Có fallback/overlap thì khẳng định đúng **route ID và backend** được chọn, không chỉ status.
- [ ] Time/RemoteAddr/ReadBody predicates được kiểm tra với dữ liệu đại diện và trust boundaries.
- [ ] JMH chỉ dùng để so Java code; HTTP load test thực sự đo Gateway và backend stub.
- [ ] Có workload hit/miss/near-match, nhiều concurrency levels và latency distribution.
- [ ] Benchmark cùng JDK, hardware, route count, CPU/memory limits, TLS mode, instrumentation.
- [ ] Không công khai metrics với raw path/query/header/token hoặc bật wiretap ghi PII.
- [ ] Gateway Actuator dùng read-only management plane được bảo vệ.
- [ ] Dynamic route changes có validation, revision, refresh từng replica, canary và rollback.
- [ ] Có SLO về p95/p99, CPU per request, error rate và cảnh báo event-loop stalls.

## 18. Câu hỏi tự kiểm tra

**1. Vì sao `Path=/api/orders/**` thường phù hợp hơn custom regex `^/api/orders/.*`?**

Vì Path predicate là công cụ chuyên dụng của Gateway để match URL path, rõ nghĩa, xử lý URI template theo Spring và tránh tự viết/compile regex. Nhưng hiệu năng cuối vẫn cần đo trên đúng release.

**2. `Pattern.compile` một lần có ngăn ReDoS không?**

Không. Nó giảm chi phí **compile lặp lại** nhưng `Matcher.matches()` vẫn có thể backtrack rất lâu với một pattern nguy hiểm.

**3. Có được share `Pattern` và `Matcher` giữa nhiều requests không?**

`Pattern` immutable/thread-safe nên có thể share; `Matcher` có state, không thread-safe nên phải tạo riêng cho mỗi lần đánh giá.

**4. Vì sao bỏ `Method=POST` khỏi route có thể làm benchmark “nhanh hơn” nhưng không đạt?**

Vì request trước đây bị chặn có thể vào backend; đó là **thay đổi route semantics và có thể mở quyền sai**, không phải tối ưu tương đương.

**5. Nếu benchmark chỉ chạy request match route, nó bỏ sót gì?**

Nó bỏ sót chi phí ở requests không match, đặc biệt khi Gateway phải xem xét nhiều routes hoặc regex nhận input gần khớp rồi thất bại.

**6. Tại sao metric `spring.cloud.gateway.requests` không tự đủ để đo mọi predicate misses?**

Vì metrics filter thường chạy trong Gateway filter chain **sau route selection**; một request không có route có thể không đi qua nó. Cần thêm HTTP server observations và CPU profiling.

**7. `Host` predicate có dùng Java regex như `Header` không?**

Không cùng cú pháp: Host được tài liệu mô tả là Ant-style host pattern, còn Header/Query/Cookie có Java regex cho giá trị tương ứng.

**8. Vì sao `a++a` có thể không tương đương `a+a`?**

Possessive quantifier `++` không nhường lại ký tự để phần cuối của regex match; tối ưu kiểu đó có thể đổi ngôn ngữ được chấp nhận.

**9. Có nên thay `RequestRateLimiter` bằng một regex “chỉ cho phép client tốt” để nhanh hơn?**

Không. Regex predicate không có state/quota đáng tin và không xác thực danh tính. Rate limiting phải được thiết kế riêng, cùng với authentication và trust boundary.

**10. Với nhiều routes cùng match, vì sao đổi `order` để giảm CPU là rủi ro?**

Vì route rộng có thể được chọn trước route cụ thể, đổi backend/filter/security policy. Thứ tự phải được kiểm chứng qua route ID và downstream target.

## 19. Tài liệu chính thức và tham khảo

1. [Spring Cloud Gateway Server WebFlux 5.0 — Route Predicate Factories](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/request-predicates-factories.html): cách kết hợp AND, Path/Method/Host/Header/Query/Cookie/RemoteAddr/ReadBody.
2. [Spring Cloud Gateway Server WebFlux 4.2 — Route Predicate Factories](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/request-predicates-factories.html): đối chiếu behavior và prefix config WebFlux 4.x.
3. [Spring Cloud Gateway 5.0 — Developer Guide](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/developer-guide.html): cách viết `AbstractRoutePredicateFactory<Config>`.
4. [Spring Cloud Gateway 5.0 — Predicate/Filter Configuration](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/configuring-route-predicate-factories-and-filter-factories.html): cú pháp shortcut và full `name/args`.
5. [Spring Cloud Gateway 5.0 — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/5.0/configprops.html): namespaces/metrics/defaults theo version.
6. [Spring Cloud Gateway Server WebFlux — Global Filters and Metrics](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html): route-specific metrics và filter ordering.
7. [Java SE — Pattern API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/regex/Pattern.html): precompile, `Pattern.matches`, thread safety, quantifiers, atomic groups.
8. [Java SE — Matcher API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/regex/Matcher.html): mutable state, thread safety của Matcher.
9. [OWASP — Regular Expression Denial of Service](https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/07-Injection/28-Regular_Expression_Denial_of_Service/): rủi ro regex với exponential backtracking.
10. [OWASP — Denial of Service Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html): input size limits, CPU exhaustion và tránh catastrophic regex.
11. [JMH — OpenJDK Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/): phương pháp microbenchmark JVM.
12. [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): HTTP test có response assertions, phù hợp integration Gateway.

**Ghi nhớ:** Muốn giảm chi phí predicate của Spring Cloud Gateway, hãy **đo trước**, **giảm số route/predicate evaluations không cần thiết**, **ưu tiên phép kiểm tra chuyên biệt** và **tránh regex có backtracking nguy hiểm**. Với custom code, tái sử dụng `Pattern` nhưng tạo `Matcher` riêng; giới hạn input và không blocking trên WebFlux event loop. Một tối ưu chỉ thành công khi **route selection và security vẫn đúng**, đồng thời có bằng chứng cải thiện **CPU, allocation hoặc p95/p99** dưới workload đại diện.
