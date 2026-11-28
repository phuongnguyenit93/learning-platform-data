# Correlation ID xuyên qua nhiều lớp proxy

## 1. Bài toán: một request, nhiều điểm quan sát

Trong hệ thống mạng hiện đại, một yêu cầu HTTP có thể đi qua CDN, WAF, load balancer, reverse proxy, ingress controller, API gateway, service mesh rồi mới tới ứng dụng. Mỗi thành phần thường tạo access log riêng và có thể tự sinh một mã định danh cho request. Khi người dùng báo lỗi 504, việc tìm các dòng log thuộc **cùng một luồng xử lý** trở nên khó khăn nếu mỗi lớp sử dụng mã khác nhau.

**Correlation ID** là mã dùng để liên kết các sự kiện, bản ghi log và thao tác phát sinh từ cùng một request hoặc cùng một chuỗi công việc đã được xác định phạm vi. Ví dụ, mọi lớp cùng ghi:

~~~text
correlation_id=6f9c3a128ef24cfca6a92fdbe30571ab
~~~

Kỹ sư vận hành có thể tìm mã này ở edge proxy, ingress, gateway và các dịch vụ phía sau để biết request dừng ở đâu, lớp nào trả lỗi, upstream nào bị chậm và có retry hay không. Đây là một kỹ thuật cơ bản trong **giám sát mạng và telemetry**, hỗ trợ phân tích lưu lượng, phát hiện bất thường, điều tra sự cố bảo mật và xác định nguyên nhân lỗi xuyên nhiều lớp phòng vệ.

Sau bài này, người học cần phân biệt correlation ID với trace ID, thiết lập chính sách cấp phát và truyền mã qua các proxy, gắn mã vào log ứng dụng, kiểm tra tính liên tục của mã và xử lý đúng các ranh giới tin cậy.

## 2. Phân biệt các mã định danh thường gặp

| Mã | Phạm vi thường dùng | Có giữ nguyên qua nhiều hop không? | Mục đích |
| --- | --- | --- | --- |
| **Correlation ID / X-Request-ID** | Một request hoặc giao dịch được quy ước | Có, trong phạm vi đã chọn | Tìm tất cả log có liên quan |
| **Trace ID** | Một distributed trace | Có, xuyên các span thuộc trace | Nối các span và xem đường đi, độ trễ |
| **Span ID** | Một thao tác/span | Không; mỗi span có ID riêng | Phân biệt từng bước trong trace |
| **Proxy request ID** | Một request do một proxy nhìn thấy | Chưa chắc; có proxy tự sinh ID mới | Tra cứu log nội bộ của proxy |
| **Business/Workflow ID** | Đơn hàng, job hoặc workflow dài hạn | Có thể tồn tại qua nhiều request | Liên kết vòng đời nghiệp vụ |
| **Connection ID / địa chỉ IP** | Kết nối mạng hoặc điểm cuối | Không ổn định giữa các proxy | Chẩn đoán kết nối, định tuyến |

**X-Request-ID** là tên header phổ biến để mang correlation ID, nhưng không có chuẩn duy nhất bắt buộc mọi proxy phải tự động truyền header này. Ngược lại, **traceparent** và **tracestate** thuộc chuẩn W3C Trace Context, phục vụ distributed tracing. Một hệ thống có thể sử dụng cả hai, miễn là mô tả rõ vai trò của từng mã.

Đặc biệt, một client connection có thể chứa nhiều HTTP/2 stream, proxy có thể mở kết nối mới đến upstream, và NAT thay đổi địa chỉ quan sát được. Vì vậy, IP, port hoặc TCP connection không thể thay thế correlation ID.

## 3. Đường đi của một request qua nhiều proxy

Giả sử hệ thống tiếp nhận yêu cầu tạo đơn hàng:

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Client
    participant E as CDN / WAF / Edge
    participant I as Ingress proxy
    participant G as API Gateway
    participant A as Order Service
    participant B as Payment Service
    U->>E: POST /orders
    Note over E: Cấp correlation ID C
    E->>I: X-Request-ID: C
    I->>G: X-Request-ID: C
    G->>A: X-Request-ID: C
    A->>B: X-Request-ID: C
    B-->>A: Kết quả thanh toán
    A-->>G: Kết quả tạo đơn
    G-->>I: HTTP 201
    I-->>E: HTTP 201
    E-->>U: HTTP 201, X-Request-ID: C
~~~

Quy ước ở ví dụ này:

1. **Edge được tin cậy** tạo một mã C mới cho request từ Internet. Header do client tự gửi không được mặc nhiên xem là đáng tin.
2. Ingress và gateway **giữ nguyên C** trong khi chuyển tiếp, thay vì thay bằng request ID cục bộ của chính mình.
3. Ứng dụng ghi C trong log và đưa C vào những lời gọi downstream thuộc cùng request.
4. Mỗi hop vẫn ghi các dữ liệu riêng như thời gian xử lý, trạng thái upstream, địa chỉ upstream, route và số lần retry.
5. Edge có thể trả C về client để đội hỗ trợ tra cứu. Nếu yêu cầu bị WAF chặn trước khi tới ingress, chỉ các lớp đã xử lý request mới có log.

Một lớp proxy có quyền tạo **local_request_id** riêng để quản lý vòng đời request tại lớp đó. Khi ấy, cần log cả local ID lẫn correlation ID chung; không được âm thầm thay mã chung bằng local ID.

## 4. Hợp đồng propagation và ranh giới tin cậy

### 4.1. Quy ước một header nhất quán

Với hệ thống HTTP nội bộ, có thể chọn **X-Request-ID** làm header canonical:

~~~http
POST /orders HTTP/1.1
Host: api.example.com
X-Request-ID: 6f9c3a128ef24cfca6a92fdbe30571ab
~~~

Header HTTP không phân biệt chữ hoa/chữ thường theo tên. Khi HTTP/2 hoặc HTTP/3 biểu diễn tên header dạng chữ thường, **x-request-id** và **X-Request-ID** vẫn có cùng ý nghĩa. Tuy vậy, các sản phẩm proxy có thể dùng tên riêng, ví dụ header request ID do nhà cung cấp CDN tạo. Cần cấu hình ánh xạ rõ ràng tại biên thay vì giả định các tên đó tự động đồng nghĩa.

Một hợp đồng tối thiểu nên xác định: nơi sinh mã, tên header nội bộ, định dạng tối đa, cách xử lý header sai hoặc trùng lặp, proxy nào được phép tin tưởng mã đến, việc chuyển tiếp qua HTTP/gRPC, cách đặt field trong log và chính sách trả mã trong response.

### 4.2. Cấp phát ở điểm vào tin cậy đầu tiên

Một chính sách dễ kiểm soát cho traffic công khai là **tạo correlation ID mới tại edge do tổ chức quản lý** rồi ghi đè X-Request-ID từ Internet. Điều này ngăn client cố tình dùng chung một ID với request khác để làm nhiễu việc truy vết. Có thể sinh ID bằng UUID v4 hoặc 16 byte ngẫu nhiên đủ mạnh; giá trị nên ngắn, không chứa dữ liệu cá nhân và có xác suất trùng rất thấp.

Nếu business yêu cầu nhận mã đối soát do đối tác gửi, hãy giữ giá trị đó trong field riêng, ví dụ **external_correlation_id**, và quy định danh sách nguồn đáng tin trước khi có thể dùng làm mã chung. **Kiểm tra định dạng chỉ giúp giảm rủi ro dữ liệu bẩn, không chứng minh header đến từ nguồn tin cậy.**

Ở mỗi điểm biên, cần:

- Chỉ chấp nhận một giá trị hợp lệ, giới hạn độ dài và bộ ký tự; xử lý header lặp hoặc quá dài theo chính sách gateway.
- Ghi đè giá trị không tin cậy trước khi chuyển vào miền nội bộ; không đưa trực tiếp giá trị chưa kiểm tra vào log.
- Không dùng correlation ID làm token đăng nhập, bằng chứng sở hữu request hay quyền truy cập log.
- Không nhúng email, số điện thoại, access token, địa chỉ IP hoặc dữ liệu bí mật vào ID.

### 4.3. Truyền xuyên các lớp proxy

Trên đường request đi vào, mỗi reverse proxy phải lấy **correlation ID canonical** từ phía upstream đáng tin cậy, ghi vào access log và truyền cùng giá trị cho hop tiếp theo. Trong đường response, việc trả mã về client cần được xử lý tại gateway/edge theo chính sách; không có bảo đảm client luôn nhận được response header khi kết nối bị hủy.

Cần kiểm tra cấu hình thực tế của CDN, WAF, proxy, ingress và mesh vì các lớp này có thể xóa header không được allowlist, đổi tên, ghi đè request ID hoặc không chuyển header khi retry. Header như **X-Forwarded-For**, **Forwarded** và **X-Real-IP** có tác dụng khác: mô tả nguồn kết nối/chuỗi proxy, không dùng để định danh một request.

## 5. Cấu hình NGINX ở hai vai trò khác nhau

Ví dụ sau minh họa một edge NGINX sở hữu việc cấp phát mã mới. Biến **$request_id** là ID do NGINX sinh cho request tại chính instance đó; vì thế chỉ dùng trực tiếp nó để cấp phát ở edge:

~~~nginx
http {
    log_format edge_json escape=json
        '{"time":"$time_iso8601",'
        '"correlation_id":"$request_id",'
        '"uri":"$request_uri",'
        '"status":$status,'
        '"upstream":"$upstream_addr",'
        '"upstream_status":"$upstream_status",'
        '"request_time":$request_time}';

    upstream trusted_ingress {
        server ingress.internal:8080;
    }

    server {
        listen 8080;
        access_log /var/log/nginx/edge-access.log edge_json;

        location / {
            # Ghi đè mọi X-Request-ID do client cung cấp.
            proxy_set_header X-Request-ID $request_id;
            proxy_set_header Host $host;
            proxy_pass http://trusted_ingress;

            # Tránh trùng header trả về từ upstream.
            proxy_hide_header X-Request-ID;
            add_header X-Request-ID $request_id always;
        }
    }
}
~~~

Ở **proxy nội bộ chỉ nhận traffic từ edge đáng tin cậy**, lấy header đã được cấp phát thay vì sinh lại. Nếu header vắng mặt, ví dụ cấu hình chuyển tiếp bị lỗi, proxy tạo ID dự phòng và phát tín hiệu cảnh báo vì đường propagation đã bị đứt:

~~~nginx
http {
    map $http_x_request_id $correlation_id {
        default $http_x_request_id;
        ""      $request_id;
    }

    log_format ingress_json escape=json
        '{"time":"$time_iso8601",'
        '"correlation_id":"$correlation_id",'
        '"status":$status,'
        '"upstream":"$upstream_addr",'
        '"upstream_status":"$upstream_status",'
        '"request_time":$request_time}';

    server {
        listen 8080;
        access_log /var/log/nginx/ingress-access.log ingress_json;

        location / {
            proxy_set_header X-Request-ID $correlation_id;
            proxy_pass http://api_gateway;
        }
    }
}
~~~

**Điều kiện áp dụng:** snippet nội bộ giả định đường đến ingress đã bị giới hạn ở lớp mạng và edge đã chuẩn hóa header. Cơ chế map chỉ xử lý trường hợp rỗng; nó không xác thực giá trị tùy ý từ một nguồn có thể bypass edge. Với nhiều ingress hoặc nguồn truy cập khác, phải xác minh trust boundary và lọc giá trị trước khi log/chuyển tiếp. Ví dụ cũng chỉ trình bày đường HTTP proxy; một hệ thống production cần bổ sung TLS, timeout, health check và cấu hình phù hợp hạ tầng thực tế.

Đừng dùng **$request_id** riêng của từng NGINX làm correlation ID chung trong mọi access log: như vậy mỗi hop sẽ hiển thị một ID khác nhau dù request vẫn đi qua đầy đủ.

## 6. Đưa correlation ID vào ứng dụng Java

Ở ứng dụng Spring Boot chạy phía sau trusted proxy, một servlet filter có thể lấy mã từ header, kiểm tra định dạng, lưu vào **SLF4J MDC** cho log và dọn sạch sau khi xử lý:

~~~java
import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class CorrelationIdFilter extends OncePerRequestFilter {
    private static final String HEADER = "X-Request-ID";
    private static final String MDC_KEY = "correlationId";
    private static final Pattern VALID_ID =
            Pattern.compile("[A-Za-z0-9_-]{16,64}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        String inbound = request.getHeader(HEADER);
        String correlationId =
                inbound != null && VALID_ID.matcher(inbound).matches()
                        ? inbound
                        : UUID.randomUUID().toString();

        request.setAttribute(MDC_KEY, correlationId);
        response.setHeader(HEADER, correlationId);
        MDC.put(MDC_KEY, correlationId);
        try {
            filterChain.doFilter(request, response);
        } finally {
            // Tránh rò MDC sang request khác dùng lại worker thread.
            MDC.remove(MDC_KEY);
        }
    }
}
~~~

Filter trên kiểm tra cú pháp và tạo fallback; **chỉ được tin tưởng header đầu vào nếu kết nối đến ứng dụng thực sự đi qua proxy đã xác thực/chuẩn hóa nó**. Nếu ứng dụng bị truy cập trực tiếp từ Internet, chính sách phải đổi sang tự tạo ID mới hoặc dùng biện pháp xác thực nguồn. Cần xử lý header trùng lặp ngay tại gateway thay vì dựa vào hành vi lấy header đầu tiên của servlet container.

Khi ứng dụng gọi service khác qua Spring **RestClient**, interceptor có thể tiếp tục gửi ID đang nằm trong MDC:

~~~java
import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class HttpClientConfig {
    @Bean
    RestClient restClient(RestClient.Builder builder) {
        return builder.requestInterceptor((request, body, execution) -> {
            String correlationId = MDC.get("correlationId");
            if (correlationId != null) {
                request.getHeaders().set("X-Request-ID", correlationId);
            }
            return execution.execute(request, body);
        }).build();
    }
}
~~~

Định dạng log cần xuất MDC key này thành một field có cấu trúc. Ví dụ, trong Logback có thể dùng pattern **%X{correlationId}**; đối với log JSON, nên ghi field **correlation_id** độc lập để công cụ tìm kiếm log lọc chính xác. **MDC không tự truyền qua thread pool, callback bất đồng bộ hay message queue**: các môi trường đó cần cơ chế truyền context phù hợp và dọn context sau khi xử lý. Với WebFlux/reactive, dùng Reactor Context và cơ chế tích hợp tracing thay cho giả định một request luôn chạy trong một thread.

## 7. Kết hợp với W3C Trace Context và OpenTelemetry

Distributed tracing cho phép biết request mất thời gian ở đâu. Với W3C Trace Context, một request có thể mang:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Trong ví dụ này, chuỗi 32 ký tự hex là **trace ID**, chuỗi 16 ký tự hex là **parent span ID**, còn hai ký tự cuối chứa **trace flags**. Các hop thuộc cùng trace thông thường giữ trace ID và tạo span ID mới khi sinh span; parent span ID trong header thay đổi theo quan hệ cha-con. **tracestate** có thể mang thông tin bổ sung của hệ thống tracing theo đúng đặc tả.

Điểm cần phân biệt:

- Correlation ID thường giữ nguyên qua proxy theo hợp đồng logging, ngay cả khi chưa triển khai tracing.
- Trace ID liên kết các span, có thể nối nhiều công đoạn; các span và sampling được tracing SDK điều phối.
- Không tùy tiện tự sửa chuỗi **traceparent** bằng phép thay text. Hãy dùng OpenTelemetry SDK, instrumentation và propagator tương thích W3C.
- Một **correlation_id** và **trace_id** có thể khác nhau; ghi **cả hai** vào log giúp truy vấn từ access log sang trace.
- Trace context từ nguồn công khai cũng chịu chính sách tin cậy và giới hạn dữ liệu. Không truyền dữ liệu cá nhân hoặc secret qua **baggage**.

Ví dụ log có cấu trúc từ ba lớp cùng xử lý một request:

~~~json
{"service":"edge","correlation_id":"6f9c3a128ef24cfca6a92fdbe30571ab","http_status":504,"upstream":"ingress:8080","duration_ms":30002}
{"service":"gateway","correlation_id":"6f9c3a128ef24cfca6a92fdbe30571ab","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","route":"POST /orders","http_status":504,"duration_ms":30000}
{"service":"order-service","correlation_id":"6f9c3a128ef24cfca6a92fdbe30571ab","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","operation":"charge-payment","duration_ms":29940,"error":"upstream_timeout"}
~~~

Từ đây có thể kết luận giả thuyết ban đầu là request đi qua edge và gateway đến order-service, rồi chờ thanh toán quá lâu. Muốn xác định chính xác nguyên nhân sâu hơn cần log hoặc span từ payment-service và kiểm tra timeout tương ứng; chỉ cùng ID chưa đủ chứng minh thành phần nào là nguyên nhân gốc.

## 8. Tình huống làm đứt hoặc làm rối correlation

| Tình huống | Biểu hiện khi tìm log | Cách xử lý |
| --- | --- | --- |
| Proxy tự sinh ID mới | Mỗi lớp có một mã khác nhau | Giữ header canonical; ghi riêng local ID |
| WAF/CDN chặn sớm | Không có log ở ứng dụng | Tra access/security log tại edge theo thời gian và ID tại edge |
| Proxy bỏ header | Mất ID sau một hop | Kiểm tra allowlist, request header forwarding, mapping và cấu hình ingress |
| Retry hoặc failover | Một ID xuất hiện nhiều lần tại một lớp | Ghi **attempt**, upstream, status, timestamp và span cho từng thử lại |
| HTTP/2 multiplexing | Nhiều request dùng chung kết nối | Liên kết theo request/stream context, không dựa vào connection |
| CDN cache hit | Edge có log, origin không có | Kiểm tra **cache_status** và phân biệt cache hit với lỗi propagation |
| Gọi service qua queue | Worker không nhận HTTP header | Gửi correlation ID trong message attributes/metadata |
| Callback tạo request mới | ID request ban đầu không còn hợp lý | Tạo ID cho request mới, liên kết bằng trace/workflow/causation ID |
| Client ngắt kết nối | Không nhận response header; có thể thấy 499 tại NGINX | Tra log edge theo thời điểm, route và ID đã cấp phát |
| Thread pool làm mất MDC | Log ứng dụng thiếu correlation_id | Truyền context qua executor/reactive context và dọn context đúng cách |

**Retry:** giữ ID của request logic gốc để điều tra xuyên suốt; bổ sung số lần thử và ID/span của từng attempt nếu cần phân biệt các lần gọi upstream. Không nên dùng cùng một correlation ID làm khóa duy nhất của từng bản ghi log.

**Bất đồng bộ:** khi HTTP request đặt một message vào queue, hãy ghi correlation ID vào metadata của message và copy sang log của consumer. Nếu một job chạy nhiều giờ và phát sinh nhiều request mới, hãy quy ước thêm **workflow_id** bền vững và **causation_id** chỉ thông điệp gây ra thông điệp kế tiếp; không ép mọi tác vụ về một request ID không còn đúng phạm vi.

**Các miền độc lập:** nếu gọi hệ thống bên thứ ba, không được giả định họ giữ X-Request-ID. Ghi mapping giữa mã nội bộ và mã phản hồi của nhà cung cấp trong log, kèm chính sách giới hạn dữ liệu chia sẻ.

## 9. Quy trình điều tra sự cố bằng correlation ID

Giả sử client nhận lỗi 504 với **X-Request-ID** là **6f9c3a128ef24cfca6a92fdbe30571ab**:

1. **Tìm tại edge:** lọc theo correlation_id, thời điểm, host và route. Đọc HTTP status, upstream address, request time, upstream response time, WAF action và cache status (nếu có).
2. **Tìm tại ingress/gateway:** kiểm tra cùng ID có xuất hiện không, request được route vào service nào, có retry/failover không và kết quả từng upstream.
3. **Tìm tại ứng dụng:** dùng correlation_id cùng trace_id để xem operation nào chậm hoặc lỗi; mở distributed trace để xem quan hệ các span.
4. **Đối chiếu timeline:** dùng timestamp với timezone rõ ràng và độ lệch đồng hồ giữa các node; xác định sự kiện trước/sau, timeout ở hop nào và điểm log cuối cùng.
5. **Khoanh vùng mất mã:** nếu edge có mã nhưng ingress không có, kiểm tra cấu hình giữa hai lớp trước; nếu gateway có mã nhưng service không có, kiểm tra client interceptor/mesh và các hop tiếp theo.

Đối với log JSON, truy vấn khái niệm có thể là:

~~~text
correlation_id = "6f9c3a128ef24cfca6a92fdbe30571ab"
  AND timestamp BETWEEN <start_time> AND <end_time>
ORDER BY timestamp ASC
~~~

Ngôn ngữ truy vấn thực tế phụ thuộc hệ thống lưu log. Cần bổ sung **service**, **environment**, **route**, **upstream**, **status**, **duration_ms**, **trace_id** và **attempt** để phân tích. Một correlation ID chỉ giúp nối bằng chứng; kết luận về nguyên nhân phải dựa thêm vào các tín hiệu mạng, log lỗi, metric và trace.

## 10. Kiểm thử propagation từ đầu đến cuối

Sau khi triển khai, có thể gửi request có header cố ý giả mạo vào endpoint thử nghiệm:

~~~bash
curl -i https://api.example.com/health \
  -H 'X-Request-ID: client-controlled-id'
~~~

Với chính sách edge tự cấp phát, response nên chứa X-Request-ID mới do edge tạo. Dùng giá trị đó tìm lại log và xác minh các tầng được đi qua ghi **đúng cùng một mã**. Lặp thử nghiệm cho HTTP/2 (nếu hỗ trợ), request lỗi 4xx/5xx, backend timeout, retry, WAF block, cache hit và luồng gọi service nối tiếp; các trường hợp dừng ở edge sẽ không có log downstream.

Checklist chấp nhận triển khai:

- Request từ Internet được cấp mã ở đúng trust boundary; header đầu vào sai, quá dài hoặc trùng được xử lý theo chính sách.
- Mã canonical tồn tại nhất quán trong các log và downstream request của cùng luồng; local proxy ID được giữ riêng khi cần.
- Access log cho biết route, upstream, response status, duration, retry/attempt để phân biệt nguyên nhân.
- Ứng dụng Java ghi correlation_id trong log, chuyển mã qua HTTP/gRPC/message metadata tương ứng và dọn context.
- Có liên kết tới trace_id nếu sử dụng OpenTelemetry; không tự sửa traceparent trong proxy hoặc ứng dụng.
- Kiểm thử lỗi và request bị chặn cho thấy rõ lớp nào xử lý request cuối cùng.

## 11. Yêu cầu bảo mật và vận hành telemetry

Correlation ID cần đủ ngẫu nhiên để tránh đụng độ và có thể được lộ cho client khi hỗ trợ xử lý sự cố, nhưng **không phải bí mật hay chứng thực**. Tuyệt đối không dùng ID để cho phép truy cập vào nội dung log hoặc dữ liệu đơn hàng. Nếu cho phép người dùng gửi ID để tra cứu, hệ thống hỗ trợ vẫn phải xác minh quyền truy cập dữ liệu theo cơ chế riêng.

Chuẩn hóa giá trị trước khi ghi log nhằm chống giả mạo bản ghi qua ký tự xuống dòng hoặc control characters; giới hạn độ dài để tránh tiêu hao tài nguyên. Trong hệ thống nhiều tenant, nên ghi thêm tenant identifier được cấp sau xác thực vào **field riêng có kiểm soát truy cập**, không ghép vào ID.

Không đưa **correlation_id** hoặc **trace_id** làm label cho mọi time series Prometheus vì số lượng giá trị gần như tăng theo mỗi request, gây **high cardinality**. Các mã này phù hợp hơn với structured logs và tracing; metric nên dùng nhãn có số giá trị hữu hạn như service, route chuẩn hóa, status class. Điều chỉnh retention, chỉ mục log, sampling và quyền truy vấn theo nhu cầu điều tra thực tế.

Một thiết kế tốt tạo được sợi dây liên kết đáng tin cậy từ edge qua từng proxy tới ứng dụng, đồng thời giữ đủ dữ liệu tại từng hop để biết request được định tuyến và xử lý ra sao. Chính sách cấp phát ở biên, propagation rõ ràng, logging nhất quán và trace context đúng chuẩn giúp công tác giám sát mạng chuyển từ việc dò từng file log sang điều tra một chuỗi sự kiện có thể kiểm chứng.
