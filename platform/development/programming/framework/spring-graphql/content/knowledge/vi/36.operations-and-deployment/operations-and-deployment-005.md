# Giới hạn request body

GraphQL HTTP endpoint nhận request từ client trước khi parse operation và thực thi resolver. Với POST, nội dung thường là một JSON object chứa query, operationName, variables và extensions. Nếu không giới hạn kích thước body, client có thể gửi payload quá lớn làm tăng bộ nhớ, CPU, thời gian parse và áp lực lên các service phía sau.

Trong Spring for GraphQL, giới hạn request body là một phần của vận hành HTTP. Cần đặt giới hạn ở ingress/reverse proxy hoặc HTTP server, sau đó bổ sung kiểm tra phù hợp ở ứng dụng. Cấu hình codec của WebFlux có thể giới hạn lượng dữ liệu được buffer khi decode; filter kiểm tra Content-Length có thể từ chối sớm request có độ dài đã khai báo quá lớn. Mỗi cơ chế có phạm vi riêng và không nên nhầm lẫn chúng với nhau.

Giới hạn body cũng không thay thế việc kiểm soát độ phức tạp GraphQL. Một query ngắn có thể tạo hàng nghìn resolver hoặc truy vấn database; ngược lại, variables lớn có thể tạo body lớn dù query document rất đơn giản. API cần bảo vệ cả kích thước HTTP payload lẫn chi phí thực thi GraphQL.

## 1. Request body của GraphQL HTTP gồm những gì?

Một POST request theo dạng JSON thường có cấu trúc:

~~~http
POST /graphql HTTP/1.1
Content-Type: application/json

{
  "query": "query Product($id: ID!) { product(id: $id) { id name } }",
  "operationName": "Product",
  "variables": {
    "id": "p-100"
  },
  "extensions": {}
}
~~~

Body size tính trên toàn bộ nội dung JSON được truyền, không chỉ riêng query string. Variables có thể chứa danh sách input lớn, chuỗi dài hoặc object lồng nhau. Extensions cũng có thể chứa metadata cho persisted query hoặc các giao thức mở rộng.

Các phần cần cân nhắc:

| Thành phần | Nội dung | Rủi ro khi quá lớn |
| --- | --- | --- |
| query | GraphQL document | Parse và validation tốn CPU, document có thể chứa nhiều field/alias |
| operationName | Tên operation được chọn | Thường nhỏ, nhưng vẫn nằm trong body |
| variables | Giá trị arguments/input | Có thể chứa danh sách lớn, chuỗi dài hoặc JSON lồng sâu |
| extensions | Metadata mở rộng | Có thể tăng payload nếu client gửi dữ liệu tùy ý |

Không lấy số ký tự của query làm giới hạn request body. HTTP body được đo bằng byte; UTF-8 characters có thể chiếm nhiều byte. Server/proxy cần áp dụng giới hạn byte trên payload thực tế.

## 2. Phân biệt body size, query size và query cost

Đây là ba giới hạn khác nhau:

| Giới hạn | Kiểm soát | Ví dụ |
| --- | --- | --- |
| HTTP request body size | Số byte POST body | Tối đa 1 MiB JSON |
| GraphQL document size | Độ dài query document | Tối đa 64 KiB query text |
| Query depth/complexity | Khối lượng công việc GraphQL có thể tạo ra | Giới hạn depth hoặc cost score |

Một request có thể vượt body limit vì variables chứa hàng chục nghìn phần tử, dù query chỉ có vài field. Một request khác có body nhỏ nhưng query lồng sâu, alias nhiều lần hoặc gọi field đắt lặp lại.

Do đó, không thể chỉ tăng body limit để sửa lỗi query phức tạp, cũng không thể chỉ dùng depth limit để ngăn payload JSON khổng lồ. Mỗi giới hạn cần có mục tiêu riêng.

## 3. Đặt giới hạn ở reverse proxy hoặc ingress

Reverse proxy là nơi phù hợp để chặn request quá lớn trước khi dữ liệu đến ứng dụng. Nó có thể áp dụng giới hạn cho cả request có Content-Length và request truyền theo chunked encoding.

Ví dụ Nginx:

~~~nginx
server {
    listen 443 ssl;

    location /graphql {
        client_max_body_size 1m;
        proxy_pass http://spring-graphql-app;
    }
}
~~~

Directive client_max_body_size quy định kích thước tối đa của client request body. Khi vượt giới hạn, Nginx trả HTTP 413 Request Entity Too Large và không chuyển request đó đến upstream.

1 MiB chỉ là giá trị minh họa. Hãy chọn mức phù hợp với payload hợp lệ lớn nhất của ứng dụng, ví dụ mutation nhập nhiều dòng hàng hoặc batch update. Đặt giới hạn quá thấp có thể chặn use case hợp lệ; đặt quá cao làm giảm hiệu quả bảo vệ.

Với Nginx Ingress Controller, có thể cấu hình annotation ở Ingress:

~~~yaml
metadata:
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "1m"
~~~

Tên annotation phụ thuộc ingress controller. Nếu dùng Traefik, Envoy, cloud load balancer hoặc API gateway, hãy cấu hình giới hạn body tương ứng của sản phẩm đó. Không giả định annotation của Nginx Ingress áp dụng cho mọi controller.

## 4. HTTP 413 và các status liên quan

HTTP 413 biểu thị request content lớn hơn giới hạn mà server hoặc proxy chấp nhận. Client nên xử lý status này ở tầng HTTP vì request có thể bị từ chối trước khi GraphQL execution bắt đầu.

| Status | Ý nghĩa | Ví dụ nguyên nhân |
| --- | --- | --- |
| 413 Content Too Large | Request body vượt giới hạn | JSON POST body lớn hơn proxy/server cap |
| 400 Bad Request | Request không hợp lệ | JSON malformed hoặc framing không đúng |
| 415 Unsupported Media Type | Content-Type không được hỗ trợ | Gửi body dạng text/plain thay vì media type được endpoint hỗ trợ |
| 414 URI Too Long | Request URI quá dài | GET query document hoặc variables mã hóa vào URL vượt giới hạn URI |
| 431 Request Header Fields Too Large | Header quá lớn | Cookie hoặc header vượt giới hạn |

Không xử lý HTTP 413 bằng DataFetcherExceptionResolver hoặc @GraphQlExceptionHandler. Những cơ chế đó hoạt động trong GraphQL execution; request bị proxy/container từ chối có thể chưa đến GraphQL engine.

Client nên phân biệt HTTP transport error với GraphQL errors nằm trong response body. Không giả định mọi lỗi đều có JSON shape chứa errors.

## 5. Giới hạn ở ứng dụng Spring MVC

Với Spring MVC/Servlet, có thể thêm filter kiểm tra Content-Length để từ chối sớm POST đến GraphQL endpoint:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

@Component
public class GraphQlContentLengthFilter extends OncePerRequestFilter {

    private static final long MAX_BODY_BYTES = 1_048_576L;
    private static final String GRAPHQL_PATH = "/graphql";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        boolean graphQlPost =
            "POST".equalsIgnoreCase(request.getMethod())
                && GRAPHQL_PATH.equals(request.getServletPath());

        long contentLength = request.getContentLengthLong();

        if (graphQlPost && contentLength > MAX_BODY_BYTES) {
            response.sendError(
                HttpServletResponse.SC_REQUEST_ENTITY_TOO_LARGE,
                "GraphQL request body is too large");
            return;
        }

        filterChain.doFilter(request, response);
    }
}
~~~

Filter này là chốt kiểm tra sớm khi request có Content-Length. Nếu Content-Length lớn hơn giới hạn, ứng dụng trả 413 trước khi GraphQL parse body.

Đây không phải giới hạn luồng hoàn chỉnh: getContentLengthLong() có thể trả -1 khi độ dài không được khai báo, chẳng hạn request dùng chunked transfer encoding. Filter trên sẽ cho request đó đi tiếp. Vì vậy, vẫn cần giới hạn body thực tế ở reverse proxy hoặc HTTP server. Nếu ứng dụng được phép nhận traffic trực tiếp không qua proxy, cần thêm giới hạn đọc stream có đếm byte hoặc cấu hình giới hạn native của container đang sử dụng.

Đường dẫn /graphql là ví dụ. Nếu ứng dụng đổi spring.graphql.path, filter phải dùng cùng endpoint path thực tế. Khi có context path hoặc servlet path riêng, kiểm tra getServletPath() phù hợp hơn so sánh toàn bộ request URI.

Không đọc toàn bộ request body trong filter chỉ để đếm byte rồi chuyển tiếp. Đọc stream có thể tiêu thụ body trước khi GraphQL handler nhận được, hoặc buộc ứng dụng buffer thêm một bản sao lớn.

## 6. Vì sao Content-Length không đủ?

Content-Length là kích thước body mà client khai báo trong HTTP headers. Nó hữu ích để từ chối sớm, nhưng không phải cơ chế duy nhất để giới hạn dữ liệu thực sự được nhận.

Các trường hợp cần lưu ý:

- Request có Content-Length lớn hơn cap: có thể từ chối ngay.
- Request có Content-Length nhỏ nhưng nội dung truyền không khớp: HTTP server xử lý framing/protocol error.
- Request dùng chunked transfer encoding: Content-Length có thể không có.
- Request đi qua proxy: proxy có thể buffer hoặc stream body theo cấu hình riêng.
- Request nén: kích thước truyền và kích thước sau giải nén có thể khác nhau nếu hệ thống hỗ trợ decompression.

Muốn có hard limit, tầng nhận dữ liệu phải đếm byte thực tế khi đọc stream hoặc dùng server/proxy có giới hạn body được hỗ trợ. Một filter chỉ nhìn Content-Length không bảo đảm giới hạn với chunked body.

ContentCachingRequestWrapper cũng không phải body-size limiter. Wrapper này phục vụ cache nội dung request đã được đọc, thường cho logging/auditing; nó không tự từ chối khi số byte vượt một ngưỡng.

## 7. Cấu hình codec cho Spring WebFlux

Trong ứng dụng WebFlux, request body được decode thông qua HTTP message codecs. Spring Boot cung cấp cấu hình max in-memory size:

~~~yaml
spring:
  codec:
    max-in-memory-size: 1MB
~~~

Giá trị này giới hạn lượng dữ liệu codec được phép buffer trong các tình huống cần aggregate nội dung. Nó hữu ích khi GraphQL JSON request được decode thành một object trong bộ nhớ và body lớn hơn ngưỡng sẽ làm quá trình decode thất bại.

Đây là giới hạn ở codec/buffering layer, không nên xem nó là thay thế hoàn toàn cho giới hạn body tại ingress hoặc HTTP server. Hành vi cụ thể phụ thuộc decoder, cách body được consume và phiên bản Spring Framework. Hãy kiểm tra với đúng stack WebFlux đang chạy.

Thuộc tính spring.codec.max-in-memory-size cũng có thể ảnh hưởng các codec được cấu hình trong ứng dụng, bao gồm một số client codec. Khi BFF vừa nhận GraphQL request vừa dùng WebClient/GraphQlClient tải payload lớn, cần cân nhắc ảnh hưởng chung và cấu hình riêng codec nếu cần.

## 8. Servlet container và các thuộc tính dễ nhầm

Không có một thuộc tính Spring Boot duy nhất có ý nghĩa giống nhau cho mọi servlet container và mọi loại request body. Một số thuộc tính của Tomcat thường bị nhầm là giới hạn JSON body:

| Thuộc tính Tomcat | Phạm vi chính | Không nên hiểu là |
| --- | --- | --- |
| maxPostSize | Giới hạn dữ liệu POST được Tomcat parse thành parameters cho các content type/form parsing liên quan | Hard cap chung cho mọi application/json body |
| maxSwallowSize | Lượng body Tomcat tiếp tục đọc/bỏ qua sau khi request bị từ chối hoặc xử lý kết thúc sớm | Kích thước tối đa của request được chấp nhận |
| maxHttpRequestHeaderSize | Kích thước request headers | Kích thước JSON body |

Không chỉnh maxSwallowSize để mong chặn GraphQL JSON body. Không dựa vào maxPostSize như giới hạn body chung nếu endpoint nhận application/json. Hãy kiểm tra tài liệu đúng phiên bản container và dùng proxy/body limiter thực sự.

Nếu dùng Jetty hoặc Undertow, cấu hình native có thể khác về tên và semantics. Đọc tài liệu server tương ứng, xác minh nó áp dụng cho raw request content hay chỉ form/multipart parsing, và test cả Content-Length lẫn chunked transfer.

## 9. Giới hạn query document riêng

Body size cap giới hạn tổng JSON bytes, nhưng một query document có thể cần ngưỡng riêng:

~~~graphql
query LargeDocument {
    product1: product(id: "p-1") { id name }
    product2: product(id: "p-2") { id name }
    product3: product(id: "p-3") { id name }
}
~~~

Một document có thể lặp nhiều alias hoặc field selection. Body có thể vẫn nhỏ hơn giới hạn nhưng tạo ra nhiều resolver invocation.

Các biện pháp:

- Giới hạn độ dài query document theo byte hoặc ký tự sau khi decode.
- Giới hạn số operation/alias nếu policy cần.
- Dùng query depth limit.
- Dùng query complexity/cost analysis để ước lượng công việc.
- Cân nhắc persisted queries hoặc allowlist cho client production.

Độ dài query và complexity là hai chỉ số khác nhau. Không dùng giới hạn query length làm thay thế complexity analysis.

## 10. Giới hạn variables và input collection

Variables thường là phần lớn nhất của GraphQL POST body. Ví dụ mutation import có thể nhận danh sách hàng nghìn item:

~~~graphql
mutation ImportProducts($items: [ImportProductInput!]!) {
    importProducts(items: $items) {
        acceptedCount
        rejectedCount
    }
}
~~~

Body cap giới hạn tổng payload, nhưng application vẫn nên validate:

- Số phần tử tối đa trong từng input list.
- Độ dài tối đa của string.
- Độ sâu và số field của input object.
- Kích thước từng blob/text field nếu có.
- Tổng số item mà một mutation được phép xử lý.

Không chỉ dựa vào giới hạn byte. Một payload nhỏ có thể chứa hàng nghìn phần tử ngắn; ngược lại một trường mô tả dài có thể làm body lớn dù số phần tử ít.

Với import rất lớn, cân nhắc API upload riêng hoặc quy trình asynchronous job: client tải file qua object storage, sau đó mutation GraphQL nhận file/job reference đã được xác thực. Không buộc một GraphQL request giữ hàng chục MB dữ liệu trong bộ nhớ nếu use case có thể xử lý theo luồng.

## 11. GET request có giới hạn khác POST

GraphQL HTTP có thể hỗ trợ GET cho query operations tùy cấu hình/transport. Với GET, query và variables thường được mã hóa vào URL query parameters, nên giới hạn quan trọng là URI/request-target size và request headers, không phải POST body.

Một URL quá dài có thể bị từ chối bằng HTTP 414 hoặc bị browser/proxy/server từ chối theo giới hạn riêng. Giới hạn URI có thể thấp hơn body limit rất nhiều.

Mutation không nên được gửi bằng GET. Client cần dùng POST cho mutation và các request có variables lớn. Với GET, không cố chuyển một JSON payload lớn thành URL chỉ để tránh body cap.

Persisted query có thể giảm kích thước query document truyền trong request bằng cách gửi hash/identifier, nhưng variables vẫn nằm trong request và vẫn phải tuân theo body limit.

## 12. Multipart upload và request body

GraphQL specification cốt lõi không định nghĩa file upload bằng multipart/form-data. Nếu ứng dụng cài thêm GraphQL multipart request convention hoặc endpoint upload riêng, cần áp dụng chính sách riêng:

- Giới hạn tổng request size.
- Giới hạn kích thước từng file.
- Giới hạn số file và số part.
- Giới hạn metadata và field text.
- Kiểm tra loại nội dung thực tế, không chỉ tin filename/Content-Type.
- Lưu file theo streaming vào storage thay vì buffer toàn bộ trong heap.
- Quét hoặc kiểm tra file theo yêu cầu nghiệp vụ.

spring.servlet.multipart.max-file-size và spring.servlet.multipart.max-request-size áp dụng cho multipart handling của Servlet. Chúng không phải giới hạn chung cho application/json GraphQL POST. Nếu dùng WebFlux multipart, cần cấu hình multipart reader/server tương ứng.

Không bật upload extension chỉ vì body limit đã được nâng cao. File upload có threat model và tài nguyên khác JSON request thông thường.

## 13. Request compression và kích thước sau giải nén

Nếu server/proxy hỗ trợ request Content-Encoding như gzip, cần xác định giới hạn được áp dụng trước hay sau giải nén. Payload nén nhỏ có thể mở rộng thành dữ liệu lớn trong bộ nhớ.

Chính sách nên xem xét:

- Giới hạn bytes trên wire tại ingress.
- Giới hạn decoded/decompressed bytes nếu có decompression.
- Giới hạn thời gian giải nén và đọc body.
- Tắt request compression nếu không cần.
- Test payload nén có tỷ lệ mở rộng lớn.

Không mặc định rằng client_max_body_size hoặc Content-Length cap sau proxy sẽ bảo vệ bộ nhớ sau giải nén. Điều này phụ thuộc nơi và cách decompression được thực hiện.

## 14. Chọn giới hạn phù hợp

Không có một giá trị body size phù hợp với mọi GraphQL API. Hãy đo payload hợp lệ thực tế và chọn ngưỡng có headroom hợp lý:

1. Thu thập kích thước request body ở môi trường thử nghiệm hoặc telemetry đã được mask.
2. Xác định use case hợp lệ lớn nhất, gồm variables và extensions.
3. Chọn ngưỡng tối đa có dư địa vừa đủ.
4. Đặt default nhỏ hơn nếu client thông thường chỉ gửi request nhỏ.
5. Giới hạn riêng cho mutation/bulk operation nếu chúng có nhu cầu khác.
6. Đặt giới hạn đồng bộ giữa ingress, server và app.
7. Theo dõi tỷ lệ request gần ngưỡng và số lượng HTTP 413.

Ví dụ một API chỉ phục vụ query thông thường có thể bắt đầu thử nghiệm với 1 MiB. API có mutation nhập batch có thể cần mức khác hoặc một endpoint import riêng. Các con số này là điểm khởi đầu để đo, không phải chuẩn mặc định cho mọi hệ thống.

## 15. Đồng bộ giới hạn giữa các tầng

Giả sử ingress giới hạn 1 MiB, WebFlux codec giới hạn 512 KiB và app filter cho phép 2 MiB. Request 700 KiB có thể bị codec từ chối dù ingress cho qua. Request 1.5 MiB bị ingress chặn trước khi đến app. Ba tầng đang có contract khác nhau, làm việc chẩn đoán khó hơn.

Hãy lập bảng cấu hình:

| Tầng | Giới hạn ví dụ | Vai trò |
| --- | --- | --- |
| CDN/API gateway | 1 MiB | Chặn payload lớn ở edge |
| Ingress/reverse proxy | 1 MiB | Chặn trước upstream |
| HTTP server/codec | 1 MiB hoặc ngưỡng phù hợp | Giới hạn nhận/decode/buffer |
| App validation | 1 MiB và input-specific limits | Kiểm tra bổ sung theo endpoint/use case |

Giới hạn ở các tầng cần tương thích. Nếu tầng trong có giới hạn thấp hơn tầng ngoài, request có thể đi qua mạng rồi mới bị từ chối. Nếu tầng ngoài cho phép lớn hơn tầng trong, client nhận lỗi từ app/codec thay vì edge. Điều đó có thể chấp nhận, nhưng cần chủ động và có quan sát.

## 16. Xử lý lỗi body quá lớn

Body bị từ chối trước GraphQL execution thường trả HTTP 413. Response body có thể do proxy hoặc HTTP server tạo ra và không nhất thiết tuân theo GraphQL error format.

Client nên:

- Kiểm tra HTTP status trước khi parse GraphQL response.
- Hiển thị thông báo payload quá lớn hoặc đề nghị chia nhỏ batch.
- Không retry nguyên request không thay đổi vì retry sẽ tiếp tục vượt giới hạn.
- Giữ error handling cho GraphQL errors riêng với transport errors.

Nếu app filter tự trả 413, có thể cấu hình error response thống nhất ở gateway hoặc filter. Nhưng không cần giả lập GraphQL response nếu request chưa được GraphQL engine xử lý; HTTP status là tín hiệu chuẩn.

Không trả nội dung body đã bị từ chối trong error message hoặc log. Chỉ log endpoint, content length, request ID và metadata an toàn.

## 17. Quan sát request size mà không lộ dữ liệu

Nên theo dõi:

- Số request POST đến GraphQL endpoint.
- Histogram kích thước body theo byte.
- Số request bị từ chối 413 theo tầng.
- Số lỗi decode/codec buffer limit.
- Query document size và variables size nếu có instrumentation an toàn.
- Tỷ lệ request gần ngưỡng.
- Latency parse/validation/execution.

Không log raw GraphQL body hoặc variables mặc định. Variables có thể chứa email, địa chỉ, token, dữ liệu cá nhân hoặc thông tin nghiệp vụ nhạy cảm. Nếu cần debug, dùng sampled logging có mask, giới hạn kích thước và thời gian lưu ngắn.

Gắn request ID/correlation ID để đối chiếu log proxy và ứng dụng. Một request bị Nginx trả 413 có thể không xuất hiện trong application log; cần xem metrics/access log ở tầng ingress.

## 18. Kiểm thử request body limit

Test phải kiểm tra hành vi ở đúng tầng cấu hình:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| POST body nhỏ hơn limit | Request đến GraphQL execution |
| POST body đúng limit | Được chấp nhận nếu server/proxy dùng điều kiện inclusive |
| POST body vượt limit | HTTP 413 |
| Content-Length lớn hơn limit | Bị từ chối sớm |
| Chunked body vượt limit | Bị giới hạn bởi proxy/server stream cap |
| JSON malformed nhưng nhỏ | HTTP 400 hoặc error theo transport contract |
| Content-Type không hỗ trợ | HTTP 415 |
| GET URI quá dài | HTTP 414 hoặc status theo server/proxy |
| Variables list quá nhiều dù body còn nhỏ | Application validation từ chối |
| Query sâu nhưng body nhỏ | Depth/complexity policy từ chối |

Khi test app filter, cần có test cho request không có Content-Length để chứng minh filter không được xem là hard cap. Khi test ingress, gửi request qua ingress thật hoặc môi trường tích hợp tương đương; MockMvc không kiểm tra được Nginx limit.

## 19. Ví dụ kiểm thử filter bằng MockMvc

Filter Content-Length có thể được kiểm thử ở servlet layer:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class GraphQlContentLengthFilterTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsDeclaredBodyLargerThanLimit() throws Exception {
        byte[] body = new byte[1_048_577];

        mockMvc.perform(post("/graphql")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isPayloadTooLarge());
    }
}
~~~

Test này kiểm tra filter từ chối request có Content-Length lớn hơn 1 MiB. MockMvc thường tạo request với content length đã biết; nó không mô phỏng đầy đủ chunked transfer hoặc reverse proxy. Cần integration test qua HTTP server/ingress để kiểm tra hard limit.

Nếu endpoint path khác /graphql hoặc ứng dụng chạy dưới context path, điều chỉnh test và filter theo cấu hình thật. Không giả định filter chỉ được đăng ký cho một servlet mapping nếu cấu hình ứng dụng có nhiều dispatcher.

## 20. Những lỗi cấu hình thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ kiểm tra Content-Length | Chunked request có thể đi qua filter | Dùng proxy/server stream cap |
| Dùng maxSwallowSize như request cap | Request body vẫn có thể được chấp nhận | Dùng giới hạn body thực sự |
| Dùng maxPostSize cho mọi JSON body | Hiểu sai phạm vi form parameter parsing | Kiểm tra container semantics và đặt proxy cap |
| Chỉ tăng max-in-memory-size | Payload lớn vẫn được buffer và tốn heap | Chọn ngưỡng vừa đủ và giới hạn tại ingress |
| Nhầm body size với query complexity | Query nhỏ nhưng rất đắt vẫn chạy | Thêm depth/cost controls |
| Nhầm multipart limit với JSON limit | GraphQL JSON không được bảo vệ như mong đợi | Cấu hình đúng media type và tầng |
| Không giới hạn variables | Input list/string lớn làm tăng memory/CPU | Validate size và item count |
| Không phân biệt GET và POST | Query URL quá dài hoặc body không được kiểm soát | URI limit cho GET, body limit cho POST |
| Trả GraphQL error cho mọi 413 | Sai tầng và client có thể parse nhầm | Xử lý HTTP status transport |
| Log toàn bộ body | Rò rỉ dữ liệu nhạy cảm và tăng log volume | Log size/request ID, mask nội dung |
| Các tầng có ngưỡng khác nhau không chủ đích | Lỗi khó chẩn đoán | Đồng bộ cấu hình và quan sát từng tầng |

## 21. Checklist triển khai

- Xác định endpoint GraphQL và các HTTP methods được bật.
- Xác định payload POST hợp lệ lớn nhất, gồm query, variables và extensions.
- Chọn max body size theo byte.
- Cấu hình ingress/reverse proxy để chặn cả Content-Length và chunked body.
- Kiểm tra giới hạn native của servlet container nếu app nhận traffic trực tiếp.
- Với WebFlux, cấu hình codec max-in-memory-size phù hợp và xác minh decoder behavior.
- Nếu dùng app filter, coi Content-Length check là early guard; không coi đó là hard cap cho chunked body.
- Đặt giới hạn riêng cho query document, variables list/string và query complexity.
- Xử lý GET URI size riêng; không gửi mutation qua GET.
- Nếu có multipart upload hoặc request compression, định nghĩa giới hạn riêng cho từng dạng.
- Trả HTTP 413 khi body vượt ngưỡng và hướng dẫn client chia nhỏ payload.
- Đo body-size histogram, 413 rate và codec failures mà không log raw variables.
- Kiểm thử ở cả application layer và ingress/server layer.

## 22. Nguyên tắc giới hạn request body cho Spring GraphQL

Giới hạn request body cần được áp dụng trước khi GraphQL parse và execute operation. Ưu tiên hard cap ở ingress/reverse proxy hoặc HTTP server để chặn payload thực tế, sau đó dùng codec hoặc app validation như lớp bảo vệ bổ sung. Trong Spring MVC, filter kiểm tra Content-Length giúp từ chối sớm request đã khai báo quá lớn; nó không tự chặn chunked body. Trong WebFlux, spring.codec.max-in-memory-size giới hạn buffering của codec và cần được xem đúng theo phạm vi của decoder.

Phân biệt HTTP body bytes với query document size, variables limits, GET URI size và query complexity. Dùng HTTP 413 cho payload quá lớn, không dựa vào GraphQL exception resolver cho request bị từ chối trước execution. Giữ giới hạn đồng bộ giữa gateway, proxy, server và ứng dụng; kiểm thử cả request có Content-Length và chunked transfer.

Không đặt một con số lớn chỉ để tránh lỗi client. Đo payload hợp lệ, giới hạn list/string theo use case, cân nhắc upload/import riêng cho dữ liệu lớn và quan sát request size mà không log dữ liệu nhạy cảm. Cách làm này bảo vệ bộ nhớ và năng lực xử lý của GraphQL endpoint mà vẫn giữ contract rõ ràng cho client.

## Tài liệu tham khảo

- [Spring Boot — Web Server Configuration](https://docs.spring.io/spring-boot/reference/howto/webserver.html)
- [Spring Boot — WebFlux Codec Configuration](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring for GraphQL — HTTP Transport](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Nginx — client_max_body_size](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size)
- [GraphQL over HTTP Specification](https://graphql.github.io/graphql-over-http/draft/)
