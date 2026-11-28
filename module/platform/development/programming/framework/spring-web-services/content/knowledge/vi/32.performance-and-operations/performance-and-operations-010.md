# Reverse proxy, cân bằng tải và địa chỉ WSDL công bố bên ngoài

Trong môi trường production, dịch vụ SOAP thường chạy sau một hoặc nhiều lớp hạ tầng: load balancer, ingress controller, reverse proxy, API gateway, WAF và servlet container. Client nhìn thấy một địa chỉ HTTPS công khai, trong khi ứng dụng Spring-WS có thể chỉ lắng nghe HTTP trên một cổng nội bộ, với context path và servlet mapping khác. Nếu WSDL công bố sai địa chỉ, partner có thể tải được contract nhưng SOAP client lại gọi vào hostname nội bộ, sai scheme/port hoặc đường dẫn không tồn tại. Nếu proxy chuyển tiếp thiếu hoặc sai metadata, ứng dụng có thể dựng `soap:address` không đúng, tạo redirect sai, xác thực TLS/mTLS không như mong muốn hoặc ghi log sai nguồn request.

Bài **“Reverse proxy, cân bằng tải và địa chỉ WSDL công bố bên ngoài”** thuộc chương **Hiệu năng và vận hành** của module `SPRING_WEB_SERVICES`. Module tập trung phát triển dịch vụ SOAP contract-first với Spring Web Services, thiết kế XSD/WSDL, ánh xạ JAXB, endpoint và SOAP client; xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích trong hệ thống doanh nghiệp.

Mục tiêu là thiết kế đường đi của SOAP request qua proxy/load balancer, công bố đúng public endpoint trong WSDL, xử lý forwarded headers an toàn, cấu hình Spring-WS/Servlet mapping phù hợp và kiểm thử topology production. Các ví dụ dùng Spring-WS 4.x và Spring Boot 3.x trên Servlet stack; một số thuộc tính thay đổi theo phiên bản/framework/container. Hãy kiểm tra dependency và container thực tế trước khi áp dụng. Tên miền, hostname, port và đường dẫn là giả định.

`SPECIAL_NOTE` của bài được truyền rỗng.

## 1. Topology của một SOAP service production

Một hệ thống B2B điển hình có nhiều client bên ngoài cùng gọi một endpoint công khai. Load balancer phân phối connection đến các proxy hoặc application nodes; các thành phần phía trong chỉ biết địa chỉ mạng nội bộ.

~~~mermaid
flowchart LR
    A["Partner SOAP Client A"] --> P["Public DNS / WAF"]
    B["Partner SOAP Client B"] --> P
    P --> L["Load Balancer"]
    L --> R1["Reverse Proxy / Ingress 1"]
    L --> R2["Reverse Proxy / Ingress 2"]
    R1 --> N1["Spring-WS Node 1"]
    R1 --> N2["Spring-WS Node 2"]
    R2 --> N2
    R2 --> N3["Spring-WS Node 3"]
    N1 --> S["Shared application services"]
    N2 --> S
    N3 --> S
~~~

Ví dụ địa chỉ:

~~~text
Public endpoint:
  https://soap.example.com/integration/orders/v1

Internal proxy -> application:
  http://orders-soap.internal:8080/orders-soap/ws/*

Spring servlet:
  context path     = /orders-soap
  servlet mapping  = /ws/*
  request path     = /orders-soap/ws
~~~

Client phải sử dụng **public endpoint** đã được công bố và được partner cho phép. Ứng dụng có thể nhìn thấy `http://orders-soap.internal:8080/orders-soap/ws`, nhưng đây là địa chỉ nội bộ, không được đưa vào WSDL cho đối tác bên ngoài.

### 1.1. Vai trò của từng tầng

| Thành phần | Trách nhiệm | Không nên mặc định |
| --- | --- | --- |
| DNS | Phân giải hostname public tới địa chỉ frontend. | DNS hostname luôn giống hostname ở backend. |
| WAF / API gateway | Policy biên, allowlist, rate limit, request screening, đôi khi authentication. | Gateway parse/validate toàn bộ SOAP contract thay ứng dụng. |
| Load balancer | Chọn proxy/backend node, health checks, TLS termination hoặc passthrough. | Mỗi request cùng client luôn tới cùng node. |
| Reverse proxy / Ingress | Forward HTTP, rewrite path, thêm forwarded metadata, giới hạn payload/timeouts. | Proxy tự biết public WSDL address nếu không cấu hình. |
| Servlet container | Nhận request, tính context path/servlet path, quản lý connection. | Host/port mà Servlet thấy chính là public host/port. |
| Spring-WS | Dispatch SOAP message, endpoint mapping, marshalling, interceptors. | Spring-WS tự suy mọi thông tin proxy một cách chính xác. |
| Application service | Thực hiện use case và business rules. | Một request đã qua proxy luôn hợp lệ về nghiệp vụ. |

Điểm phải giữ xuyên suốt là **địa chỉ client sử dụng, địa chỉ proxy chuyển tiếp và địa chỉ ứng dụng bind** có thể khác nhau. Hãy quản trị chúng như các giá trị riêng biệt.

### 1.2. TLS termination ở đâu?

Có ba mô hình phổ biến:

**TLS termination tại load balancer/proxy**

~~~text
Partner -- HTTPS --> Load Balancer -- HTTP --> Spring-WS
~~~

Proxy giải mã TLS và chuyển HTTP vào mạng tin cậy. Đây là cách phổ biến, nhưng đường proxy-to-application cần được bảo vệ bằng network segmentation, private network hoặc TLS nội bộ theo threat model. Ứng dụng phải nhận biết public scheme/host từ forwarded metadata đáng tin cậy nếu cần dựng URL.

**TLS passthrough**

~~~text
Partner -- TLS passthrough --> TCP load balancer --> Spring-WS TLS
~~~

Load balancer chỉ phân phối TCP/TLS, backend tự terminate TLS. Ứng dụng thấy TLS connection thật, nhưng proxy tầng 4 không thể thêm HTTP forwarded headers vì chưa đọc được HTTP.

**TLS re-encryption**

~~~text
Partner -- HTTPS --> Proxy -- HTTPS --> Spring-WS
~~~

Proxy terminate TLS public rồi tạo TLS connection mới đến backend. Cần quản lý hai trust boundaries: chứng chỉ public phía partner và certificate/trust nội bộ giữa proxy với application. Nếu dùng mTLS nội bộ, ứng dụng xác minh identity của proxy hoặc workload theo policy.

Không có mô hình nào luôn đúng. Chọn theo yêu cầu bảo mật, compliance, network topology và khả năng vận hành certificate.

## 2. Public endpoint và internal endpoint

Một SOAP service có thể có các địa chỉ sau:

| Khái niệm | Ví dụ | Ai dùng? |
| --- | --- | --- |
| Public base URL | `https://soap.example.com/integration/orders` | Partner, client bên ngoài. |
| Public SOAP address | `https://soap.example.com/integration/orders/v1` | SOAP client gọi operation. |
| Public WSDL URL | `https://soap.example.com/integration/orders/v1/orders.wsdl` | Client tải contract. |
| Internal service address | `http://orders-soap:8080/orders-soap/ws` | Proxy/service mesh nội bộ. |
| Container bind address | `0.0.0.0:8080` | Network listener của process/container. |
| Health endpoint | `http://orders-soap:8080/actuator/health/readiness` | Orchestrator/load balancer nội bộ, nếu được bảo vệ. |

Public WSDL address phải phù hợp với DNS, TLS certificate, port, gateway route và partner firewall. Đừng publish địa chỉ service discovery hoặc container hostname.

### 2.1. WSDL có hai loại địa chỉ dễ bị nhầm

Ví dụ WSDL 1.1:

~~~xml
<wsdl:service name="OrdersService">
  <wsdl:port name="OrdersSoap11Port"
             binding="tns:OrdersSoap11Binding">
    <soap:address
      location="https://soap.example.com/integration/orders/v1"/>
  </wsdl:port>
</wsdl:service>
~~~

- URL mà partner tải WSDL là **contract retrieval location**.
- Giá trị `soap:address/@location` là **SOAP invocation endpoint**.

Hai URL có thể cùng host/path prefix nhưng không bắt buộc giống nhau. Client generator hoặc runtime thường đọc `soap:address` để tạo default service URL. Nếu trường này là hostname nội bộ, partner có thể generate stub thành công nhưng gọi thất bại ngoài mạng.

### 2.2. Public URL và servlet mapping phải khớp

Giả sử:

~~~text
Public URL:
  https://soap.example.com/integration/orders/v1

Proxy rewrite:
  /integration/orders/v1  -> /orders-soap/ws

Servlet context path:
  /orders-soap

MessageDispatcherServlet mapping:
  /ws/*
~~~

Ứng dụng nhận request tại servlet path do container tính; proxy đã thay prefix. Nếu WSDL generator tự dựng URL từ request mà forwarded metadata hoặc proxy configuration không đúng, nó có thể phát `soap:address` thành:

~~~text
http://orders-soap:8080/orders-soap/ws
~~~

Đây là một URL có thể truy cập từ cluster nhưng không phải địa chỉ public. Cần cấu hình public base URL rõ ràng hoặc xử lý forwarded headers đúng cách.

## 3. Reverse proxy headers: Host, scheme, port và forwarded path

Để backend biết public request ban đầu, proxy có thể chuyển metadata:

~~~http
Forwarded: proto=https;host=soap.example.com
X-Forwarded-Proto: https
X-Forwarded-Host: soap.example.com
X-Forwarded-Port: 443
X-Forwarded-Prefix: /integration
X-Forwarded-For: 198.51.100.25
~~~

`Forwarded` được chuẩn hóa trong RFC 7239; các `X-Forwarded-*` là quy ước phổ biến nhưng không cùng một chuẩn thống nhất. Proxy stack và framework có thể hỗ trợ một tập khác nhau.

### 3.1. Ý nghĩa từng header

| Header | Ý nghĩa | Cần chú ý |
| --- | --- | --- |
| `Forwarded` | Metadata chuẩn hóa gồm `for`, `by`, `host`, `proto`. | Có thể có nhiều phần tử/chuỗi proxy. Parse theo RFC, không tự split ngây thơ. |
| `X-Forwarded-For` | Danh sách địa chỉ client/proxy trước đó. | Chọn client IP phụ thuộc trust boundary và chuỗi proxy; không tin giá trị do internet gửi thẳng. |
| `X-Forwarded-Host` | Host public mà client gọi. | Phải giới hạn host hợp lệ để tránh Host header injection. |
| `X-Forwarded-Proto` | Scheme public (`http`/`https`). | Cần đúng khi TLS terminate tại proxy. |
| `X-Forwarded-Port` | Port public. | Có thể suy từ scheme/default port nhưng nên nhất quán. |
| `X-Forwarded-Prefix` | Prefix proxy đã thêm hoặc rewrite. | Không phải Servlet API header tiêu chuẩn ở mọi stack; framework integration phụ thuộc version. |

Proxy phải **ghi đè hoặc xóa các forwarded headers do client gửi vào**, rồi thêm giá trị do chính nó xác định. Nếu proxy chỉ nối chuỗi không kiểm soát, attacker có thể gửi `X-Forwarded-Host: evil.example` và làm backend dựng WSDL/redirect/link theo host giả.

### 3.2. Trust forwarded headers chỉ từ proxy được kiểm soát

Luồng an toàn:

1. Public edge nhận request.
2. Edge xóa các `Forwarded`/`X-Forwarded-*` không đáng tin từ inbound client.
3. Edge ghi lại metadata từ connection và routing thực tế.
4. Network policy giới hạn backend chỉ nhận traffic từ proxy/load balancer đã duyệt.
5. Backend chỉ xử lý forwarded metadata khi request thực sự đến từ trusted proxy.
6. Logging giữ được cả public request context và internal route theo policy.

**Không bật forwarded-header processing một cách mù quáng** nếu backend cũng truy cập trực tiếp được từ internet hoặc mạng không tin cậy. Nếu request trực tiếp có thể gửi header giả, backend có thể tin một host/scheme không do hạ tầng xác nhận.

### 3.3. Host header injection và WSDL poisoning

WSDL động đôi khi dựng `soap:address` từ host/scheme của inbound request. Nếu ứng dụng tin tùy tiện Host hoặc forwarded host, attacker có thể khiến WSDL trả:

~~~xml
<soap:address
  location="https://attacker.example/collect-soap"/>
~~~

Khi client tải WSDL từ một endpoint bị ảnh hưởng, client generator hoặc runtime có thể gửi request tới địa chỉ attacker. Đây là lý do public host cần allowlist và proxy phải chuẩn hóa metadata.

Các biện pháp:

- Dùng hostname public cấu hình tĩnh cho mỗi môi trường khi có thể.
- Nếu cần dynamic host, allowlist hostname và scheme; không chấp nhận host tùy ý.
- Proxy chỉ chuyển forwarded headers đã chuẩn hóa.
- Chặn backend access trực tiếp ngoài network boundary.
- Kiểm tra response WSDL trong test từ public hostname thực.
- Không log/echo header không tin cậy mà không encoding/normalization.

### 3.4. Forwarded path prefix và rewrite

Một số gateway thêm prefix public:

~~~text
External:
  /integration/orders/v1

Internal:
  /orders-soap/ws
~~~

`X-Forwarded-Prefix` có thể giúp framework biết prefix ngoài, nhưng không có nghĩa mọi component đều sử dụng nó để tạo URL. Spring Framework `ForwardedHeaderFilter`, container native support và Spring Boot forwarded-header strategy có hành vi/version-specific. Cũng cần xác minh proxy path rewrite thực tế, context path và servlet mapping.

**Đừng vừa rewrite path tại proxy vừa thêm prefix ở backend một cách không có kiểm thử**, vì có thể tạo URL lặp:

~~~text
/integration/integration/orders/v1
~~~

## 4. Công bố WSDL trong Spring-WS

Spring-WS có thể publish WSDL từ contract/schema resources bằng `DefaultWsdl11Definition` hoặc có thể phục vụ WSDL tĩnh đã được quản lý như artifact. Cách chọn ảnh hưởng trực tiếp đến `soap:address`.

### 4.1. DefaultWsdl11Definition và locationUri

Một cấu hình contract-first điển hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.wsdl.wsdl11.DefaultWsdl11Definition;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
public class OrdersWsdlConfig {

    @Bean
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(
            new ClassPathResource("contracts/orders-v1.xsd"));
    }

    @Bean(name = "orders")
    public DefaultWsdl11Definition ordersWsdl(XsdSchema ordersSchema) {
        DefaultWsdl11Definition definition =
            new DefaultWsdl11Definition();

        definition.setPortTypeName("OrdersPort");
        definition.setLocationUri(
            "https://soap.example.com/integration/orders/v1");
        definition.setTargetNamespace(
            "urn:example:orders:v1");
        definition.setSchema(ordersSchema);
        return definition;
    }
}
~~~

Trong Spring-WS, bean tên `orders` thường được publish qua `MessageDispatcherServlet` tại URL dạng `/ws/orders.wsdl` khi servlet được cấu hình xử lý WSDL. `setLocationUri` cung cấp location được dùng trong SOAP address của WSDL được tạo. Đây là ví dụ dùng **public address cố định** cho một môi trường; không copy hostname production vào development hoặc staging.

Ưu điểm của address tĩnh:

- Không phụ thuộc Host/Forwarded headers của từng request.
- Tránh WSDL thay đổi theo header do caller gửi.
- Dễ test checksum và contract artifact.
- Hạn chế host header injection khi WSDL được tải từ nhiều hostname.

Nhược điểm là cần quản lý property theo môi trường và cập nhật khi public endpoint thay đổi. Hãy externalize bằng configuration property/bean factory hoặc dùng một WSDL artifact theo môi trường; không hardcode cùng production URL ở mọi deployment.

### 4.2. Transform WSDL locations theo request

`MessageDispatcherServlet` có tùy chọn transform WSDL locations. Khi bật, Spring-WS có thể biến đổi location trong WSDL dựa trên request URL để WSDL phản ánh nơi nó được truy cập.

Ví dụ cấu hình servlet:

~~~java
import org.springframework.ws.transport.http.MessageDispatcherServlet;
import org.springframework.web.WebApplicationInitializer;

public class SoapWebApplicationInitializer
        implements WebApplicationInitializer {

    @Override
    public void onStartup(
            jakarta.servlet.ServletContext servletContext) {

        MessageDispatcherServlet servlet =
            new MessageDispatcherServlet();

        servlet.setTransformWsdlLocations(true);

        var registration = servletContext.addServlet(
            "messageDispatcher", servlet);
        registration.setLoadOnStartup(1);
        registration.addMapping("/ws/*");
    }
}
~~~

Ví dụ này minh họa servlet mapping trên Jakarta Servlet. Spring Boot auto-configuration có thể đăng ký servlet khác; **không tạo thêm một servlet thứ hai** nếu Boot đã đăng ký `MessageDispatcherServlet`. Kiểm tra cấu hình ứng dụng thực tế và chỉ bật transform tại đúng servlet đang publish WSDL.

Transform theo request có thể hữu ích khi cùng một deployment được truy cập qua nhiều hostname public hoặc môi trường proxy khác nhau. Nhưng **nó phụ thuộc request metadata mà backend nhận**. Nếu backend thấy scheme `http`, host `orders-soap:8080` và path nội bộ, transformed WSDL vẫn sai. Trước khi bật, hãy cấu hình proxy headers và kiểm thử response WSDL qua public route.

### 4.3. Address tĩnh hay transform động?

| Tiêu chí | `locationUri` tĩnh | Transform theo request |
| --- | --- | --- |
| Public host cố định | **Phù hợp.** | Có thể dùng nhưng cần cấu hình proxy đúng. |
| Nhiều public hosts/tenant domains | Cần config hoặc WSDL theo từng host. | Có thể tiện nếu từng host đã được allowlist và forwarded headers đáng tin. |
| Host header injection risk | Thấp hơn vì address không lấy từ request. | Cao hơn nếu request host/forwarded headers không được chuẩn hóa. |
| Contract artifact reproducible | Dễ giữ nội dung ổn định. | WSDL có thể khác theo host/request. |
| Multi-environment | Cần property theo môi trường. | Có thể suy public address theo inbound request. |
| Testing | Assert một address mong đợi. | Test mỗi public route/host/proxy path. |

Không có lựa chọn mặc định đúng cho mọi deployment. Với partner B2B cần một hostname ổn định, **địa chỉ tĩnh theo môi trường thường đơn giản và an toàn hơn**. Với nhiều domain aliases được quản trị, dynamic transform có thể phù hợp nếu host allowlist và forwarded headers được bảo vệ.

### 4.4. Không nhầm WSDL generation với WSDL publication

Spring-WS có thể tạo WSDL từ XSD và conventions, nhưng một số hệ thống contract-first cần **WSDL/XSD đã duyệt và bất biến**. Khi đó có thể phục vụ WSDL tĩnh hoặc quản lý contract artifact riêng. Dù chọn cách nào, hãy bảo đảm:

- WSDL `soap:address` trỏ đến public SOAP endpoint đúng.
- Tất cả XSD import/include được phân phối hoặc resolve đúng.
- WSDL lấy được từ public route dùng đúng SOAP 1.1/1.2 binding.
- Client không nhận URL nội bộ hoặc endpoint của môi trường khác.
- Thay đổi address không vô tình thay đổi schema/QName/policy.

## 5. Spring Boot và forwarded header strategy

Spring Boot hỗ trợ cấu hình forwarded headers thông qua `server.forward-headers-strategy` trong các phiên bản hiện đại. Các giá trị thường gặp:

| Giá trị | Ý nghĩa khái quát | Khi dùng |
| --- | --- | --- |
| `NONE` | Không áp dụng forwarded-header processing theo strategy của Boot. | Backend không cần public request metadata hoặc proxy đã xử lý theo cách khác. |
| `NATIVE` | Để embedded server/container xử lý forwarded metadata. | Container có hỗ trợ như Tomcat Remote IP Valve hoặc tương đương. |
| `FRAMEWORK` | Dùng Spring Framework forwarded-header support, thường thông qua `ForwardedHeaderFilter`. | Muốn chuẩn hóa request view ở framework layer. |

Tên/value support và chi tiết cấu hình cần đối chiếu **Spring Boot version cụ thể**. Chỉ chọn một cơ chế chủ đạo. Không vừa bật native container rewriting vừa thêm filter framework lần nữa nếu chưa hiểu thứ tự và kết quả; có thể bị rewrite hai lần hoặc tạo scheme/host sai.

### 5.1. Ví dụ cấu hình

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Đây là cấu hình minh họa cho một topology có proxy đáng tin cậy đã chuẩn hóa headers và backend không expose trực tiếp ra internet. `FRAMEWORK` **không tự xác thực proxy source** hoặc thay thế network ACL. Nếu backend nhận request trực tiếp từ untrusted sources, attacker có thể gửi forwarded headers giả.

Với một cấu hình production khác, có thể dùng:

~~~yaml
server:
  forward-headers-strategy: native
~~~

Chọn `NATIVE` khi container native support được cấu hình đúng, ví dụ Tomcat remote IP handling và trusted/internal proxy ranges. Các thuộc tính Tomcat cụ thể phụ thuộc Spring Boot/container version. Cần kiểm tra actual `server.tomcat.remoteip.*` options trên đúng version thay vì copy nguyên một cấu hình generic.

### 5.2. Tránh xử lý forwarded headers hai lần

Một lỗi thường gặp:

1. Embedded Tomcat đọc `X-Forwarded-Proto` và điều chỉnh request scheme.
2. `ForwardedHeaderFilter` lại đọc cùng headers.
3. Proxy prefix cũng được thêm một lần nữa.
4. WSDL/redirect sinh sai host/path hoặc log source IP sai.

Hãy kiểm tra một request qua endpoint diagnostics trong test (không public trên production), ghi nhận:

~~~text
request.getScheme()
request.isSecure()
request.getServerName()
request.getServerPort()
request.getContextPath()
request.getServletPath()
request.getPathInfo()
request.getRequestURI()
~~~

Đây là các giá trị **sau quá trình container/filter xử lý**, không phải nội dung thô của network packet. So sánh chúng với expected public/internal mapping của topology. Tạo test qua cả HTTP nội bộ và HTTPS public proxy để phát hiện double handling.

### 5.3. Trust proxy CIDR và direct access

Nếu dùng Tomcat native remote IP handling, phải cấu hình danh sách internal/trusted proxies phù hợp. Không đặt một dải quá rộng như toàn bộ RFC1918 nếu nhiều workload không tin cậy cùng mạng có thể kết nối backend. Tùy thiết lập, container có thể chỉ xem header từ proxy được trusted; hãy test request từ:

- Trusted reverse proxy.
- Load balancer đúng dải đã duyệt.
- Một pod/workload không được phép.
- Direct client gửi forged `X-Forwarded-Host`/`Proto`.
- Client gửi nhiều header forwarded mâu thuẫn.

Kết quả cần chứng minh backend chỉ sử dụng forwarded metadata từ trust boundary đã định. Network policy/firewall nên chặn direct access khi không cần thiết.

## 6. Proxy path rewrite và Spring-WS servlet mapping

Một request có thể đi qua nhiều path transformations:

~~~text
Partner path:
  /integration/orders/v1

Ingress rewrite:
  /internal/orders/v1

Servlet context:
  /orders-soap

MessageDispatcherServlet:
  /ws/*
~~~

Path public, path sau proxy, context path và servlet path là các khái niệm khác nhau. `getRequestURI()`, `getContextPath()`, `getServletPath()` và `getPathInfo()` không thay thế được cho nhau.

### 6.1. Quản lý servlet mapping rõ ràng

Với Spring-WS, `MessageDispatcherServlet` thường được map tới prefix như `/ws/*`. Endpoint methods dùng `@PayloadRoot` map QName của payload; servlet path quyết định request đi vào dispatcher, còn namespace/local part quyết định endpoint. Proxy path rewrite không tự thay đổi SOAP Body QName.

Kiểm tra tối thiểu:

- Servlet mapping có bao gồm public route sau rewrite?
- WSDL URL có nằm trong servlet mapping?
- WSDL `soap:address` có phải invocation URL client gọi?
- Endpoint v1/v2 có được phân biệt theo path/namespace/action đúng không?
- Trailing slash và encoded paths có behavior nhất quán?
- Proxy có strip prefix đúng một lần?
- Error/redirect path có bị sinh từ internal request URI?

### 6.2. Ví dụ NGINX location và proxy headers

Một cấu hình minh họa:

~~~nginx
server {
    listen 443 ssl;
    server_name soap.example.com;

    location /integration/orders/v1/ {
        proxy_pass http://orders_soap_backend/ws/;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        proxy_connect_timeout 5s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
~~~

Đây là **ví dụ minh họa**, chưa bao gồm TLS certificate directives, body limits, upstream health, WSDL route hoặc mọi rule cần cho production. Trong NGINX, dấu slash cuối ở `location` và `proxy_pass` ảnh hưởng cách URI được thay thế; hãy test chính xác mapping. Nếu muốn public path `/integration/orders/v1` chuyển thành `/ws`, kiểm tra kết quả URI backend bằng request thật.

`$proxy_add_x_forwarded_for` nối client address với chuỗi hiện có; chỉ dùng khi edge đã sanitize inbound headers hoặc topology đã định nghĩa chuỗi tin cậy. Nếu không, client có thể giả mạo phần đầu của chuỗi IP. Cần lựa chọn cách set/append theo vai trò edge và các proxy đứng trước.

### 6.3. Không forward tất cả header một cách mặc định

Proxy nên chuyển tiếp những header cần cho SOAP và policy đã duyệt. Đặc biệt:

- Giữ `Content-Type`, SOAP 1.1 `SOAPAction`, và các header SOAP/WS-Addressing cần thiết.
- Bảo toàn HTTP `Authorization` nếu authentication được xử lý ở application và policy cho phép.
- Nếu gateway terminate mTLS, không tin một `X-Client-Cert` do client tự gửi; gateway phải strip inbound value và set metadata có xác thực, còn backend chỉ trust gateway.
- Không forward `Connection`, hop-by-hop headers hoặc header không hợp lệ tùy tiện.
- Hỗ trợ MTOM attachments nếu contract dùng multipart; không ép mọi SOAP payload thành text XML.
- Không loại bỏ WS-Security SOAP Header; nó nằm trong Envelope body stream, không phải HTTP header.

## 7. Cân bằng tải nhiều Spring-WS nodes

SOAP request-response qua HTTP thường là một request độc lập: client gửi Envelope, server xử lý và trả Envelope. Nếu ứng dụng giữ trạng thái phiên trong bộ nhớ node, load balancer có thể đưa request tiếp theo tới node khác và làm mất state. Mục tiêu vận hành thường là **stateless application nodes**, hoặc dùng shared state khi có lý do cụ thể.

### 7.1. Stateless là lựa chọn tốt cho SOAP B2B

Một cluster ba node:

~~~text
                    Public Load Balancer
                     /       |       \
                   Node A  Node B  Node C
                     \       |       /
                     Shared dependencies
                       ├─ Database
                       ├─ Message broker
                       ├─ Shared cache (nếu cần)
                       └─ Centralized secrets/key service
~~~

Mỗi node nên có khả năng xử lý request hợp lệ mà không cần request trước đó đến đúng node đó. Tránh lưu trong memory:

- Conversation state cần thiết cho operation tiếp theo.
- Idempotency record hoặc duplicate request state.
- Authentication state duy nhất chỉ tồn tại ở node.
- File upload/MTOM temporary data cần được request khác đọc.
- Transaction workflow chưa được persist.

Nếu cần session hoặc multi-step state, hãy lưu tại shared store hoặc thiết kế protocol có correlation/persistence rõ. Sticky sessions có thể giảm xác suất request đổi node, nhưng không thay thế persistence và failover.

### 7.2. Sticky session có phải luôn cần?

| Mô hình | Khi phù hợp | Rủi ro |
| --- | --- | --- |
| Không sticky, stateless | SOAP B2B request-response, auth token/cert độc lập từng request. | Mỗi node cần cùng contract/config/security trust và shared dependencies. |
| Sticky theo cookie | Browser session hoặc stateful flow thực sự cần affinity. | Failover mất session, load imbalance và phụ thuộc cookie. |
| Consistent routing theo partner/tenant | Cần locality hoặc cache affinity. | Một partner lớn có thể dồn tải lên một node; routing key phải đáng tin. |
| Shared session/state store | State cần giữ qua nhiều node. | Thêm latency/availability dependency và phải quản lý TTL/consistency. |

SOAP client máy–máy thường không cần session affinity nếu mỗi request mang đủ identity/security metadata và backend không dựa vào state cục bộ. Nếu WSS4J dùng replay cache/nonce/timestamp validation, cần đảm bảo replay state chia sẻ hoặc được kiểm soát xuyên cluster; **mỗi node có replay cache riêng có thể không phát hiện cùng một message bị gửi tới node khác**.

### 7.3. Đồng bộ security configuration

Các nodes trong cùng service version cần đồng nhất:

- WSDL/XSD contract release và endpoint addresses.
- SOAP 1.1/1.2 binding, action mappings, interceptors.
- WS-Security trust anchors, accepted signer certificates và recipient private keys theo policy.
- TLS truststores/key material và proxy trust ranges.
- JWT issuer/audience/keys nếu dùng HTTP bearer auth.
- Clock synchronization cho WS-Security timestamp validation.
- Replay cache/nonce state nếu policy yêu cầu chống replay toàn cluster.

Khi rotation certificate hoặc deploy v2, rollout từng node có thể khiến cluster có lúc chỉ một phần node chấp nhận key/contract mới. Dùng rollout overlap có kiểm soát, hoặc giữ compatibility window. Metrics nên phân biệt version/node để phát hiện chỉ một backend node đang cấu hình sai.

## 8. Timeout, request size và MTOM qua proxy

SOAP payload có thể rất nhỏ hoặc rất lớn. Một request chỉ vài KB XML khác hoàn toàn operation có MTOM attachment hàng trăm MB. Mọi tầng phải có giới hạn nhất quán và timeout phù hợp.

### 8.1. Timeout phải được thiết kế theo cả pipeline

Một request có thể chịu các timeout:

~~~text
Partner client connection/read timeout
    ↓
Public load balancer idle/request timeout
    ↓
WAF/API gateway request timeout
    ↓
Reverse proxy connect/send/read timeout
    ↓
Servlet/container connection and async timeout
    ↓
Application/database/broker timeout
~~~

Nếu ứng dụng cần 45 giây nhưng proxy cắt request sau 30 giây, client thấy lỗi trước khi server hoàn tất. Nếu client timeout sau 20 giây trong khi server xử lý 40 giây, client có thể retry và tạo duplicate side effect.

Nguyên tắc:

- Đặt connect timeout riêng với response/read timeout.
- Timeout của tầng ngoài phải phù hợp với tầng trong; không để proxy trả lỗi quá sớm so với budget nghiệp vụ đã duyệt.
- Đặt upper bound tổng thời gian request, không chỉ tăng timeout vô hạn.
- Timeout database/broker/remote calls phải nằm trong overall request budget.
- Thiết kế idempotency/correlation trước khi retry operation có side effect.
- Quan sát p50/p95/p99 latency; không chỉ đo average.

### 8.2. Proxy buffering và streaming

Reverse proxy có thể buffer request body trước khi gửi đến backend. Buffering giúp kiểm soát connection và có thể bảo vệ backend, nhưng làm tăng bộ nhớ/disk usage và độ trễ khởi đầu đối với payload lớn. Streaming giảm buffer nhưng khiến backend nhận dữ liệu sớm hơn và cần xử lý backpressure/partial transfer đúng.

Với SOAP có MTOM, proxy phải hỗ trợ multipart MIME, boundary, content length/chunked transfer và giới hạn kích thước. Không giả định NGINX/gateway mặc định cho phép attachment lớn; kiểm tra các cấu hình như body size, buffering, temp path, disk capacity và timeout.

### 8.3. Giới hạn payload ở nhiều tầng

Ví dụ bảng policy:

| Tầng | Giới hạn minh họa | Lý do |
| --- | --- | --- |
| WAF/gateway | 20 MiB request body | Chặn payload quá lớn tại edge. |
| Reverse proxy | 20 MiB `client_max_body_size` | Tránh nhận body vượt policy. |
| Servlet/container | Request limits theo connector/container | Bảo vệ memory/thread/connection. |
| Spring-WS message factory | Max payload/in-memory attachment policy | Kiểm soát XML/attachment parsing. |
| Application | Giới hạn business-specific fields/files | Ngăn request hợp lệ về transport nhưng vô lý về nghiệp vụ. |

Các con số chỉ để minh họa. Hãy chọn giới hạn theo contract, MTOM usage, memory budget, concurrent requests và partner requirements. Nếu proxy cho 20 MiB nhưng application chỉ cho 5 MiB, hãy công bố error behavior rõ và tránh upload toàn bộ body rồi mới trả lỗi.

### 8.4. SOAP XML và attachment cần hai chính sách

**XML Envelope** cần giới hạn độ sâu/nút, chống XXE, external entities và XML bomb. **MTOM attachments** cần giới hạn kích thước, số lượng, content types, temporary storage và cleanup. Một payload Envelope nhỏ có thể tham chiếu attachment lớn, vì vậy chỉ giới hạn kích thước XML không đủ.

Nếu proxy/WAF cố parse toàn bộ body để tìm text patterns, cần xác minh nó không phá multipart boundary hoặc canonicalized/signed message. WS-Security signature validation phải diễn ra ở đúng SOAP layer với message bytes/infoset được framework xử lý, không tự chỉnh sửa body tại proxy.

### 8.5. Retry sau timeout phải an toàn

Ví dụ:

~~~text
Client gửi CreatePayment
Server ghi nhận payment, nhưng response bị proxy timeout
Client không biết transaction thành công hay chưa
Client retry cùng operation
~~~

Nếu không có idempotency key hoặc business uniqueness constraint, có thể tạo hai payment. Contract nên có client request ID/idempotency key theo semantics, server lưu kết quả và trả lại cùng kết quả cho lần retry phù hợp. Không dựa vào TCP connection hoặc SOAP MessageID đơn thuần để bảo đảm nghiệp vụ chỉ chạy một lần; WS-Addressing MessageID và idempotency semantics là hai cơ chế khác nhau.

## 9. Health checks, readiness và draining

Load balancer cần biết node có nên nhận traffic mới không. Một SOAP process có thể đang sống nhưng chưa sẵn sàng xử lý contract/security traffic.

### 9.1. Liveness và readiness khác nhau

- **Liveness:** process có hoạt động hay đang deadlock/treo đến mức cần restart?
- **Readiness:** node đã load config, contract, security material và dependencies cần thiết để nhận request chưa?
- **Startup probe:** cho phép ứng dụng khởi động lâu hơn mà không bị liveness probe restart liên tục.

Không đưa tất cả remote partner services vào liveness check; một dependency chập chờn có thể làm Kubernetes restart toàn bộ nodes. Readiness nên phản ánh các điều kiện thiết yếu để xử lý SOAP requests an toàn.

### 9.2. Readiness cho Spring-WS

Một node có thể chưa ready khi:

- Keystore/truststore chưa load hoặc certificate không đạt policy.
- WSDL/XSD contract artifacts chưa được load.
- JAXB marshaller/context chưa khởi tạo.
- Database/broker thiết yếu không truy cập được theo availability policy.
- Security configuration thiếu alias/key hoặc không truy xuất được HSM.
- Migration/deployment chưa hoàn tất.
- Node đang draining để shutdown.

Health indicator cần tránh thực hiện SOAP call nghiệp vụ thật hoặc in dữ liệu nhạy cảm. Không expose actuator health chi tiết cho internet; public health endpoint nếu cần chỉ nên lộ trạng thái tối thiểu.

### 9.3. Graceful shutdown và connection draining

Khi rolling deployment:

1. Đánh dấu node không còn ready để load balancer ngừng gửi request mới.
2. Cho các request đang xử lý có thời gian kết thúc trong grace period.
3. Đóng connection/worker threads theo lifecycle container.
4. Chỉ terminate khi đã drain hoặc hết deadline.
5. Theo dõi số request đang active và lỗi do shutdown.

SOAP request có thể kéo dài do partner gửi batch hoặc attachment lớn. Nếu kill node ngay khi deploy, client nhận connection reset và có thể retry. Phải đặt termination grace period tương thích với max request processing time và client retry strategy.

### 9.4. Health check endpoint không được lẫn với SOAP endpoint

Có thể tách:

~~~text
SOAP:
  /ws/orders.wsdl  (GET contract)
  /ws             (POST SOAP)

Operations:
  /actuator/health/liveness
  /actuator/health/readiness
  /actuator/metrics
~~~

Các đường Actuator phải được bảo vệ bởi network policy/authentication thích hợp. Không để WAF public expose chi tiết health/metrics, environment, build info hoặc certificate metadata ngoài ý muốn. Load balancer probe nên gọi đúng health path và dùng status/readiness semantics đã thống nhất.

## 10. Observability: theo dõi proxy, SOAP endpoint và từng node

Khi partner báo lỗi SOAP, câu hỏi đầu tiên thường là request có tới được application không, node nào xử lý, WSDL nào được partner dùng và lỗi xảy ra ở HTTP, Spring-WS hay business layer. Nếu chỉ ghi application exception mà không có request correlation xuyên các tầng, sẽ khó xác định proxy đã rewrite path hay backend đã trả SOAP Fault.

### 10.1. Correlation ID xuyên proxy và application

Có thể dùng một request ID do gateway tạo hoặc được application tạo khi ID inbound không đáng tin. Chính sách:

- Gateway tạo/ghi đè correlation ID theo format được kiểm tra.
- Proxy chuyển tiếp ID đó tới backend.
- Application đưa ID vào MDC/log context và response header nếu policy cho phép.
- Client có thể gửi business correlation ID riêng trong SOAP Header; không đồng nhất nó với HTTP request ID.
- Không dùng correlation ID làm authentication token hoặc idempotency key trừ khi contract định nghĩa riêng.

Một log mẫu:

~~~text
timestamp=2026-11-27T10:00:00+07:00
requestId=gw-8f123
partnerId=partner-a
contractVersion=v2
publicHost=soap.example.com
publicProto=https
backendNode=orders-soap-2
method=POST
servletPath=/ws
httpStatus=200
soapOperation=CreateOrder
durationMs=84
~~~

Đây là dữ liệu minh họa. Chỉ log metadata cần thiết và được phép; không log full SOAP Body, bearer token, WS-Security UsernameToken, certificate private material hoặc dữ liệu cá nhân.

### 10.2. Metrics cần theo dõi

| Metric | Nhãn hữu ích | Cảnh báo có thể phát hiện |
| --- | --- | --- |
| Request count | contract version, operation, partner, node, status | Traffic tăng bất thường hoặc node không nhận traffic. |
| HTTP status count | route, status, gateway/backend | 404/413/502/503/504 tăng. |
| SOAP Fault count | Fault code/category, operation, version | Validation/security/business lỗi tăng. |
| Latency p50/p95/p99 | operation, node, version | Timeout và tail latency. |
| Payload/attachment bytes | operation, partner, version | MTOM volume bất thường hoặc payload lớn. |
| Active requests/connections | node, listener | Thread/connection saturation. |
| Queue/database latency | dependency | Chậm downstream làm SOAP request kéo dài. |
| WSDL retrieval/version count | contract version, environment | Partner còn dùng contract cũ hoặc cache sai. |
| Certificate expiry/rotation status | alias purpose, partner | Sự cố sắp hết hạn/rotation. |
| Replay/duplicate detection | partner, version | Retries hoặc replay behavior bất thường. |

Cẩn thận với **cardinality**: không dùng mọi request ID, raw user ID hoặc full SOAPAction làm label Prometheus nếu tạo quá nhiều time series. Dùng log/traces cho giá trị phân biệt cao, metrics cho nhãn có tập giá trị giới hạn.

### 10.3. Phân biệt edge failure và application failure

| HTTP response | Có thể phát ra ở | Bằng chứng kiểm tra |
| --- | --- | --- |
| 400 / 415 | Gateway, proxy hoặc SOAP HTTP binding | Content-Type, SOAP 1.1/1.2, body limits. |
| 401 / 403 | WAF, gateway, Spring Security | AuthN/AuthZ, mTLS mapping, request ID và filter logs. |
| 404 | Ingress route, context path, servlet mapping | Public/backend URI, rewrite rules. |
| 413 | WAF/reverse proxy/container | Body size, MTOM limits, multipart handling. |
| 502 | Proxy không kết nối hoặc backend đóng connection | Upstream health, DNS, port, TLS internal. |
| 503 | Load balancer không có healthy node hoặc app unavailable | Readiness, deployment, capacity. |
| 504 | Gateway/proxy upstream timeout | Timeout budget, server duration, retry. |
| 500 SOAP Fault | Application/Spring-WS processing | Fault code/detail, endpoint exception mapping. |

Một HTTP status không đủ xác định tầng lỗi. Gắn request ID và so log ở gateway/proxy/backend theo cùng thời điểm.

### 10.4. Trace qua các tầng

~~~text
partner request
  └─ edge / gateway
      └─ load balancer / ingress
          └─ Spring servlet filter chain
              └─ Spring-WS message dispatch
                  └─ endpoint / WSS4J / JAXB
                      └─ application service
                          ├─ database
                          └─ downstream service
~~~

Không phải mọi load balancer đều phát OpenTelemetry span. Có thể chỉ có trace ở gateway và application. Bảo đảm `traceparent` và correlation headers được allowlist và sanitize; đừng tin trace ID do caller cung cấp như một định danh xác thực.

## 11. TLS, mTLS và certificate identity qua proxy

TLS termination có ảnh hưởng tới cách backend nhận diện peer và cách SOAP service xác thực partner.

### 11.1. Client certificate termination ở gateway

Nếu gateway terminate mTLS:

~~~text
Partner -- mTLS --> Gateway -- HTTP/TLS --> Spring-WS
~~~

Backend **không còn TLS peer certificate của partner** trên connection trực tiếp; nó chỉ thấy certificate của proxy nếu proxy-to-backend cũng dùng mTLS. Nếu cần chuyển partner identity vào backend, gateway phải:

- Validate client cert chain, validity, revocation và policy trước khi forward.
- Xóa mọi inbound header cùng tên do caller tự gửi.
- Ghi identity metadata theo một format đã thống nhất.
- Bảo vệ gateway-to-backend bằng authenticated channel và network controls.
- Backend chỉ tin metadata từ gateway đã được xác thực, không tin request trực tiếp.
- Ghi lại audit chain: partner identity đã được gateway xác minh và request ID.

Một header như `X-Client-Cert` hoặc `X-SSL-Client-DN` **không tự đáng tin** vì tên header. Trust phụ thuộc việc gateway strip/set, authenticated hop và access controls. Nếu backend cần tự xác minh mTLS peer, dùng TLS passthrough hoặc re-encryption với client certificate forwarding design được kiểm chứng; không nhầm chứng chỉ của gateway với chứng chỉ partner.

### 11.2. WSS4J message signature độc lập TLS peer

Một partner có thể ký SOAP Body bằng WS-Security certificate, trong khi gateway đồng thời terminate mTLS. Hai identity này có thể khác nhau và phục vụ hai mục đích:

- TLS client certificate chứng minh danh tính peer của transport connection.
- WS-Security signature chứng minh message được ký bởi private key tương ứng với certificate signer và các signed parts không bị thay đổi.

Không bỏ WSS4J signature validation chỉ vì gateway đã xác thực mTLS; ngược lại, không coi SOAP Signature là bằng chứng TLS connection được bảo vệ. Authorization có thể ràng buộc cả hai identity theo policy.

### 11.3. Preserve Host và SNI

TLS handshake dùng SNI để chọn certificate tại endpoint. Sau TLS termination, proxy cần chuyển đúng Host/authority đến backend theo route policy. Không để public host thay đổi bất ngờ giữa:

- DNS hostname partner kết nối.
- TLS certificate SAN.
- HTTP Host/`:authority`.
- Forwarded host backend dùng dựng WSDL.
- Hostname xuất hiện trong WSDL `soap:address`.

Khi có nhiều public domains, test từng hostname vì ingress có thể chọn certificate hoặc route khác nhau theo SNI/Host.

## 12. Kiểm thử topology public endpoint và WSDL

Unit test `DefaultWsdl11Definition` không chứng minh partner ngoài internet nhìn thấy đúng address. Cần test qua đường đi giống production.

### 12.1. Test WSDL từ public hostname

Tải WSDL qua public entry:

~~~bash
curl --fail --silent --show-error \
  'https://soap.example.com/integration/orders/v1/orders.wsdl' \
  -o orders-public.wsdl
~~~

Kiểm tra `soap:address`:

~~~bash
grep -n 'soap:address' orders-public.wsdl
~~~

Kỳ vọng: URL dùng `https://soap.example.com/...`, đúng public path, không có `orders-soap.internal`, `localhost`, IP private hoặc HTTP scheme ngoài ý muốn.

Với SOAP 1.2, WSDL có thể dùng namespace/address element tương ứng của SOAP 1.2 extension. Test cả mọi port/binding công bố; không chỉ grep một address rồi kết luận đủ.

### 12.2. Integration test matrix

| Trường hợp | Request path / topology | Kỳ vọng |
| --- | --- | --- |
| Public happy path | Partner → HTTPS LB → proxy → node | SOAP response đúng contract. |
| WSDL retrieval | Public GET WSDL | `soap:address` đúng public hostname/path/scheme. |
| Direct backend blocked | Caller ngoài mạng thử backend host/port | Không truy cập được. |
| Forged forwarded host | Client gửi `X-Forwarded-Host: attacker.example` | Edge strip/overwrite; WSDL không phản chiếu host giả. |
| Forged forwarded proto | Client gửi `X-Forwarded-Proto: http` | Edge chuẩn hóa theo TLS connection; backend thấy scheme đúng. |
| Path rewrite | Public prefix → internal servlet path | Dispatcher nhận request; WSDL vẫn công bố public URL. |
| SOAP 1.1 | `text/xml` + SOAPAction theo binding | Đúng SOAP 1.1 endpoint/binding. |
| SOAP 1.2 | `application/soap+xml` | Đúng SOAP 1.2 binding, không bị proxy 415. |
| MTOM | Multipart request theo contract | Boundary/attachment giữ nguyên, size policy đúng. |
| Large body | Body vượt limit | 413 hoặc lỗi contract đã công bố; node không OOM. |
| Long operation | Request trong timeout budget | Không bị LB/proxy cắt sớm. |
| Upstream node failure | Node bị unhealthy | LB dừng route node; các node còn lại xử lý. |
| Rolling deployment | Node draining | Request active được drain; request mới tới node ready. |
| WS-Security | Signature/timestamp theo policy | Không bị proxy chỉnh sửa signed SOAP parts. |
| mTLS | Client cert hợp lệ/sai | Gateway/backend xử lý trust policy đúng. |
| Response URL | Redirect/fault/error | Không chứa internal hostname/path. |

### 12.3. Test forged header từ ngoài proxy

Trong staging, gửi request với header giả:

~~~bash
curl --include \
  -H 'X-Forwarded-Host: attacker.example' \
  -H 'X-Forwarded-Proto: http' \
  'https://soap.example.com/integration/orders/v1/orders.wsdl'
~~~

Public endpoint vẫn phải phục vụ WSDL có address đúng `soap.example.com` và HTTPS. Chỉ chạy test này trên domain/environment được phép. Nếu WSDL đổi thành attacker host, proxy hoặc backend trust configuration chưa an toàn.

### 12.4. Test nhiều nodes và failover

Gửi một batch request qua public load balancer và quan sát node xử lý (qua log/trace nội bộ). Xác nhận:

- Tất cả nodes công bố cùng contract/address/policy.
- Không node nào có truststore hoặc WSDL cũ.
- Khi tắt một node, request mới chuyển sang healthy nodes.
- Request đang xử lý được drain theo policy.
- Retry không tạo duplicate business side effects.
- Replay protection và idempotency hoạt động xuyên cluster.

Không đưa hostname/identity backend ra response public để chỉ ra node xử lý. Dùng telemetry nội bộ hoặc response header debug chỉ có trong staging.

## 13. Troubleshooting reverse proxy và WSDL address

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| WSDL chứa `http://` dù public dùng HTTPS | TLS terminate ở proxy nhưng forwarded proto không được xử lý hoặc bị ghi đè. | Forwarded header, Boot strategy, container request scheme. |
| WSDL có hostname nội bộ | `locationUri` chưa cấu hình hoặc transform dùng request host nội bộ. | Inspect `soap:address`; kiểm tra public address và proxy metadata. |
| WSDL có port nội bộ 8080 | Backend dựng address từ server port nội bộ. | `X-Forwarded-Port`, forwarded strategy, tĩnh hóa locationUri. |
| WSDL path lặp prefix | Proxy rewrite và forwarded prefix cùng áp dụng hai lần. | Path trước/sau rewrite, context path, servlet mapping. |
| Partner tải WSDL được nhưng POST 404 | WSDL GET route khác SOAP POST route hoặc address sai. | Test `soap:address` và POST qua public path. |
| 502 Bad Gateway | Upstream DNS/port/TLS sai hoặc backend đóng connection. | Proxy upstream logs, health, network/DNS, internal TLS. |
| 503 Service Unavailable | Không còn healthy backend hoặc readiness false. | LB health checks, node startup, dependency readiness. |
| 504 Gateway Timeout | Proxy/LB timeout ngắn hơn thời gian xử lý. | Timeout budget ở từng tầng, p95/p99 và downstream calls. |
| 413 Request Entity Too Large | Body/MTOM vượt giới hạn ở gateway/proxy/container. | Body limit đồng bộ, attachment policy và WAF. |
| SOAP 1.1 hoạt động, SOAP 1.2 415 | Proxy/content-type rules hoặc binding chưa hỗ trợ. | `Content-Type`, SOAP 1.2 media type, WSDL binding. |
| WS-Security signature fail qua proxy | Proxy/WAF đã chỉnh sửa body/header hoặc MIME payload. | Message capture ở hai phía, compression/normalization, MTOM. |
| Client IP luôn là proxy IP | Remote address chưa được xử lý hoặc log đang dùng wrong field. | Trusted proxy config, `X-Forwarded-For` chain. |
| Client IP là giá trị attacker gửi | Backend tin forwarded header từ nguồn không trusted. | Edge strip/overwrite, backend ACL và direct access. |
| mTLS client cert backend thành gateway cert | TLS terminate tại gateway. | Xác định trust boundary; thiết kế identity forwarding có xác thực. |
| Mỗi lần tải WSDL nhận host khác | Dynamic transform tin Host header/forwarded host không chuẩn hóa. | Host allowlist, proxy sanitation, chọn locationUri tĩnh. |
| Một node trả WSDL khác node còn lại | Artifact/config drift giữa nodes. | Contract checksum, config version, rollout state. |
| Failover làm duplicate giao dịch | Client retry khi timeout/reset mà operation không idempotent. | Idempotency key, request ledger, retry contract. |

### 13.1. Quy trình điều tra có thứ tự

~~~text
1. Lấy WSDL từ public URL và lưu lại nguyên bản.
2. Đọc mọi soap:address/service port/binding, không chỉ một endpoint.
3. Gửi SOAP POST tới chính address trong WSDL.
4. Ghi lại public URL, proxy route, internal URI và backend node.
5. So forwarded host/proto/port/prefix với trusted proxy configuration.
6. Kiểm tra servlet context path, servlet path, pathInfo và request URI sau filters.
7. Xem response status/body để phân biệt gateway, HTTP Security và SOAP Fault.
8. So TLS/SNI/SAN, mTLS identity, WSS4J policy và signed message parts.
9. Đối chiếu timeout/size limits với operation latency và MTOM size.
10. Test lại qua failover và từ chối direct/forged-header access.
~~~

Không sửa đồng thời proxy rewrite, forwarded strategy, WSDL locationUri và servlet mapping trong một lần mà không có test phân tách. Thay từng lớp, lưu WSDL trước/sau, rồi kiểm tra client behavior.

## 14. Bài tập tình huống có đáp án gợi ý

### Tình huống A — WSDL công bố internal hostname

Partner tải được WSDL nhưng `soap:address` là `http://orders-soap:8080/ws`. Partner không resolve được hostname.

**Đáp án:** Đó là internal service address. Đặt public `locationUri` theo môi trường hoặc bật transform WSDL sau khi forwarded host/proto/path được cấu hình tin cậy. Test WSDL qua public route, không test trực tiếp node.

### Tình huống B — Public HTTPS nhưng WSDL sinh HTTP

Load balancer terminate TLS và forward HTTP vào Spring-WS. Ứng dụng nhìn request scheme là HTTP.

**Đáp án:** Cấu hình proxy set forwarded proto, chọn đúng Spring Boot forwarded-header strategy hoặc container native support, và chỉ tin proxy được phép. Kiểm tra `request.isSecure()`/`getScheme()` sau xử lý. Với một public host ổn định, `locationUri` tĩnh là phương án đơn giản.

### Tình huống C — Attacker thay X-Forwarded-Host

Backend mở port nội bộ cho cả proxy và một network không tin cậy. Caller gửi `X-Forwarded-Host: attacker.example`, WSDL trả address attacker.

**Đáp án:** Edge phải strip/overwrite inbound forwarded headers; chặn direct backend access bằng firewall/network policy; giới hạn trusted proxies. Nếu cần, cấu hình public hostname tĩnh hoặc allowlist host.

### Tình huống D — SOAP POST trả 404 sau rewrite

WSDL công bố `/integration/orders/v1`, proxy rewrite về `/orders-soap/ws`, nhưng servlet được map `/soap/*`.

**Đáp án:** Mapping không khớp. Đối chiếu path public, proxy rewrite, context path và servlet mapping. Sửa một phía theo topology được thiết kế, rồi test WSDL GET và SOAP POST cùng public URL.

### Tình huống E — Rolling deployment làm mất request

Load balancer gửi request tới node đang shutdown; client nhận reset, retry tạo đơn hàng hai lần.

**Đáp án:** Readiness phải rút node khỏi traffic trước khi shutdown; dùng connection/request draining và termination grace period phù hợp. Contract cần idempotency key hoặc uniqueness rule để retry không tạo duplicate.

### Tình huống F — WSS4J replay protection lệch giữa nodes

Node A và B có replay cache riêng. Attacker gửi lại SOAP message đã ký nhưng lần retry tới node khác.

**Đáp án:** Sticky session không phải biện pháp replay protection đáng tin. Dùng shared/distributed replay cache hoặc cơ chế đảm bảo replay detection xuyên cluster, đồng bộ clock và test cùng một message qua nhiều nodes.

### Tình huống G — MTOM bị 413 ở proxy

Envelope XML nhỏ nhưng attachment 30 MiB bị proxy từ chối với 413; application chưa nhận request.

**Đáp án:** Kiểm tra body-size limits ở WAF, load balancer, reverse proxy, container và Spring-WS message factory. Đồng bộ limit theo contract, kiểm tra multipart handling/temp storage và giữ giới hạn có bảo vệ tài nguyên.

### Tình huống H — mTLS ở gateway nhưng backend không thấy partner cert

Gateway terminate mTLS và mở kết nối HTTP nội bộ tới Spring-WS. Ứng dụng chỉ thấy gateway address.

**Đáp án:** Backend không còn peer certificate gốc của partner. Nếu cần identity, gateway phải validate cert và chuyển metadata đã sanitize qua authenticated hop; backend chỉ trust gateway. Không coi header client tự gửi là bằng chứng cert.

### Tình huống I — Proxy trả 504 nhưng server vẫn hoàn thành

Client retry sau 504 và tạo side effect lặp.

**Đáp án:** Điều chỉnh timeout budget theo latency thật và đặt proxy timeout phù hợp. Thiết kế idempotency để xử lý trường hợp response bị mất sau khi nghiệp vụ commit. Theo dõi server completion sau client timeout.

### Tình huống J — WSDL khác nhau giữa nodes

Node 1 công bố `/v1`, node 2 đã đổi `soap:address` thành `/v2`; load balancer khiến partner tải ngẫu nhiên hai contract address.

**Đáp án:** Đồng nhất contract artifact và config giữa nodes trong cùng pool. Đừng trộn deployment v1/v2 dưới một pool nếu chưa có routing/version boundary. Dùng checksum/health metadata nội bộ để phát hiện drift.

## 15. Checklist triển khai production

| Hạng mục | Điều kiện đạt |
| --- | --- |
| Public DNS/hostname | Partner resolve đúng hostname và TLS SAN khớp. |
| Public WSDL URL | Tải được qua route công khai và không lộ hostname nội bộ. |
| `soap:address` | Đúng scheme/host/port/path, client gọi đúng address đã công bố. |
| WSDL bindings | Mọi SOAP 1.1/1.2 port/binding có address hợp lệ. |
| XSD imports | Resolve đúng artifact, không phụ thuộc internal URL hoặc schema mutable. |
| TLS termination model | Rõ terminate, passthrough hay re-encryption; có trust boundary. |
| Forwarded headers | Edge strip/overwrite inbound values, thêm metadata đã xác minh. |
| Trusted proxy ranges | Backend chỉ tin proxy/load balancer được định danh. |
| Forwarded strategy | Chọn NONE/NATIVE/FRAMEWORK phù hợp version; không double processing. |
| Host allowlist | Không dựng WSDL/redirect từ untrusted Host header. |
| Path rewrite | Public prefix, proxy URI, context path và servlet mapping đã test. |
| SOAPAction/content type | SOAP 1.1/1.2 headers được giữ đúng binding. |
| MTOM/body limit | WAF, proxy, container và application có giới hạn thống nhất. |
| Timeout budget | Client/LB/proxy/app/dependency timeout phù hợp p95/p99 và idempotency. |
| Load balancing | Các nodes stateless hoặc shared state đúng; không cần sticky ngoài lý do rõ. |
| Replay protection | Cache/nonce/timestamp policy hoạt động xuyên cluster. |
| Security config | Truststore, key, WSS4J policy, JWT/mTLS config đồng nhất giữa nodes. |
| Health/readiness | LB chỉ route tới node sẵn sàng; Actuator được bảo vệ. |
| Graceful shutdown | Drain requests trước terminate; grace period phù hợp operation. |
| Observability | Request ID, partner/version/operation/node metrics và log an toàn. |
| Failover | Node failure không làm mất toàn bộ service; retry không duplicate. |
| Public integration tests | WSDL GET, SOAP POST, forged headers, TLS, MTOM và failover đã kiểm tra. |
| Change management | WSDL/config/proxy changes được review, rollout và rollback có kế hoạch. |

### 15.1. Runbook kiểm tra trước khi mở partner mới

1. Lấy WSDL từ public hostname đúng môi trường.
2. Kiểm tra tất cả `soap:address`, ports, bindings và XSD imports.
3. Generate client stub từ artifact đó trong môi trường partner-compatible.
4. Gọi một SOAP operation an toàn hoặc sandbox operation.
5. Kiểm tra request ID xuyên gateway, proxy và application.
6. Xác nhận partner certificate/authentication identity được map đúng.
7. Kiểm tra SOAP Fault khi gửi payload sai có kiểm soát.
8. Thử failover node và xác minh request retry/idempotency.
9. Lưu contract checksum, endpoint, certificate fingerprint và kết quả certification.
10. Chỉ mở production traffic sau khi partner owner và service owner xác nhận.

## 16. Tài liệu tham khảo và cách áp dụng

- **IETF — [RFC 7239: Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)**: chuẩn hóa thông tin proxy như `for`, `by`, `host`, `proto`.
- **Spring Boot — [How-to: Use Behind a Proxy Server](https://docs.spring.io/spring-boot/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server)**: forwarded headers, native/framework strategy và embedded server behavior.
- **Spring Framework — [ForwardedHeaderFilter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html)**: xử lý forwarded headers ở Servlet layer và lưu ý trust boundary.
- **Spring Web Services — [Reference Documentation 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/)**: `MessageDispatcherServlet`, WSDL publication và transform WSDL locations.
- **Spring Web Services — [DefaultWsdl11Definition API 4.1.x](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/wsdl/wsdl11/DefaultWsdl11Definition.html)**: WSDL definition, schema, target namespace và location URI.
- **NGINX — [Reverse Proxy Guide](https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/)**: `proxy_pass`, headers và upstream routing.
- **NGINX — [HTTP Core Module](https://nginx.org/en/docs/http/ngx_http_core_module.html)** và **[Proxy Module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)**: URI mapping, body limits, buffering, timeouts và proxy headers.
- **Kubernetes — [Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)**: startup, liveness, readiness semantics.
- **OpenTelemetry — [Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)**: truyền trace context giữa các service qua headers.

Tên thuộc tính Spring Boot, servlet/container integration và NGINX directives có thể thay đổi theo phiên bản. Hãy kiểm tra docs/Javadoc đúng version đang deploy, đặc biệt forwarded-header strategy và path rewriting. Ví dụ cấu hình ở bài là điểm khởi đầu cần kiểm chứng trong topology thật, không phải file production hoàn chỉnh.

### Ghi nhớ

- **Public SOAP address khác internal backend address.** WSDL phải công bố endpoint mà partner thực sự truy cập, không phải hostname/container port phía trong.
- `soap:address` có thể được đặt tĩnh bằng `DefaultWsdl11Definition.setLocationUri` hoặc transform theo request bằng `MessageDispatcherServlet.setTransformWsdlLocations(true)`. Dynamic transform chỉ an toàn khi forwarded host/proto/path đến từ proxy được tin cậy.
- **Forwarded headers là dữ liệu nhạy cảm về routing.** Edge phải strip/overwrite giá trị caller gửi; backend cần allowlist trusted proxy và chặn direct access không mong muốn.
- Chọn một cơ chế xử lý forwarded headers phù hợp (`NONE`, `NATIVE`, `FRAMEWORK` theo Spring Boot version); tránh xử lý hai lần và test scheme/host/port/path sau filter/container.
- Cân bằng tải hoạt động tốt nhất khi SOAP nodes stateless hoặc dùng shared state rõ ràng. Replay cache, security config, WSDL/XSD và certificate trust cần nhất quán trên cluster.
- Timeout, body-size và MTOM limits phải được thiết kế xuyên client, LB, proxy, servlet và application. Retry sau timeout cần idempotency để không lặp side effects.
- Readiness và graceful draining giúp deploy/failover không đưa request mới tới node chưa sẵn sàng hoặc đang shutdown.
- **Kiểm thử từ public route là bắt buộc:** tải WSDL, xác minh mọi `soap:address`, gửi SOAP POST, giả mạo forwarded headers, test SOAP 1.1/1.2, MTOM, mTLS và node failover.







