# Biến đổi địa chỉ WSDL sau reverse proxy và cấu hình đường dẫn bên ngoài

Một dịch vụ SOAP có thể hoạt động bình thường bên trong mạng nội bộ nhưng khiến đối tác không gọi được khi triển khai sau **reverse proxy**, **API gateway** hoặc **load balancer**. Triệu chứng điển hình: đối tác tải WSDL từ địa chỉ HTTPS công khai, nhưng phần `soap:address` trong WSDL vẫn trỏ đến `http://localhost:8080/ws` hoặc `http://soap-app:8080/ws`. Client sinh mã từ WSDL sau đó gửi request đến địa chỉ nội bộ, dẫn đến lỗi DNS, kết nối hoặc TLS.

Bài học thuộc chương **Đọc và công bố WSDL** của module **SPRING_WEB_SERVICES**, tập trung vào cách định danh URL mà client thực sự nhìn thấy, cơ chế biến đổi địa chỉ khi Spring Web Services (Spring-WS) công bố WSDL và những tình huống cần cấu hình reverse proxy. Kiến thức này gắn trực tiếp với quy trình **SOAP contract-first**: XSD/WSDL là hợp đồng tích hợp, JAXB dùng để ánh xạ payload, endpoint và SOAP client thực thi hợp đồng, còn SOAP Fault, interceptor, XML security, WS-Security và chứng chỉ cần hoạt động chính xác trên tuyến mạng bên ngoài.

## 1. Ba địa chỉ khác nhau phải được phân biệt

Giả sử Spring-WS chạy trong container ở cổng 8080 và được công bố qua proxy TLS:

| Vai trò | Ví dụ URL | Ý nghĩa |
| --- | --- | --- |
| **WSDL nội bộ** | `http://soap-app:8080/ws/orders.wsdl` | Ứng dụng có thể phục vụ tài liệu tại địa chỉ phía backend |
| **WSDL công khai** | `https://api.example.org/gateway/ws/orders.wsdl` | URL mà hệ thống đối tác được phép truy cập để đọc hợp đồng |
| **SOAP endpoint công khai** | `https://api.example.org/gateway/ws` | URL mà client gửi SOAP request theo `soap:address` |

WSDL là **tài liệu mô tả dịch vụ**; SOAP endpoint là **đích gửi thông điệp**. Trong ví dụ, hai URL công khai chỉ khác phần `/orders.wsdl` ở cuối, nhưng không nên suy ra quy tắc ghép chuỗi này cho mọi hệ thống: WSDL có thể được lưu ở địa chỉ khác với endpoint thực tế.

Đoạn WSDL 1.1 quan trọng đối với client SOAP/HTTP:

~~~xml
<wsdl:service name="OrdersService"
              xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
              xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/">
  <wsdl:port name="OrdersSoap11Port" binding="tns:OrdersSoap11Binding">
    <soap:address location="https://api.example.org/gateway/ws"/>
  </wsdl:port>
</wsdl:service>
~~~

Đoạn trên là **trích đoạn minh họa**, giả định `tns` và binding đã được khai báo ở phần khác của tài liệu. `soap:address/@location` cho biết đích gọi của port; nó không phải URL để tải chính WSDL.

### Những giá trị dễ bị nhầm với URL dịch vụ

| Giá trị | Có nên tự động sửa thành host công khai? | Vì sao? |
| --- | --- | --- |
| `soap:address location` | **Có thể cần** | Đây là địa chỉ client gửi SOAP message |
| URL tải `orders.wsdl` | **Phải định tuyến công khai được** | Client cần tải WSDL và các tài liệu phụ thuộc |
| `schemaLocation` của XSD/WSDL import | **Cần truy cập được khi resolve** | Client code generation và schema validator cần schema |
| `targetNamespace` của XSD/WSDL | **Không** | Đây là định danh QName của hợp đồng, không phải địa chỉ mạng |
| `soapAction` trong SOAP 1.1 binding | **Không tự suy ra từ URL endpoint** | Là giá trị action do hợp đồng/binding xác định |
| `wsdl:portType`, `wsdl:message` và `wsdl:binding` | **Không** | Mô tả giao diện/đóng gói, không phải tuyến proxy |

**Lưu ý:** URI namespace có thể trông giống `https://...` nhưng vẫn chỉ là **định danh logic**. Không đổi namespace từ `http://example.org/orders/v1` sang `https://api.example.org/gateway/ws` để sửa một URL công bố sai. Hành động đó thay đổi QName và có thể phá vỡ hợp đồng JAXB, WSDL và endpoint mapping.

## 2. Vì sao reverse proxy làm WSDL công bố địa chỉ sai?

Một reverse proxy thường làm ba việc:

1. **Kết thúc TLS:** client kết nối `https://api.example.org`, proxy chuyển request tới backend bằng HTTP trong mạng riêng.
2. **Chuyển host/port:** bên ngoài dùng `api.example.org:443`, bên trong dùng `soap-app:8080`.
3. **Thêm hoặc bỏ prefix đường dẫn:** bên ngoài có `/gateway/ws`, bên trong handler được mount ở `/ws`.

~~~mermaid
flowchart LR
    C["SOAP client<br/>https://api.example.org/gateway/ws"] -->|"HTTPS GET WSDL<br/>hoặc POST SOAP"| P["Reverse proxy<br/>TLS + path mapping"]
    P -->|"HTTP /ws/*"| S["Spring-WS<br/>soap-app:8080"]
    S -->|"WSDL với soap:address"| P
    P -->|"WSDL được công bố"| C
~~~

Nếu ứng dụng chỉ thấy request backend `http://soap-app:8080/ws/orders.wsdl`, nó có thể dựng đường dẫn WSDL hoặc `soap:address` với scheme/host/port nội bộ. Tuy nhiên, client không có quyền truy cập `soap-app`, và TLS phía công khai có thể yêu cầu tên miền khác.

**Hai phép biến đổi phải khớp nhau:**

- **Proxy chuyển request vào:** `/gateway/ws/...` → `/ws/...`.
- **WSDL trả ra địa chỉ client dùng được:** `http://soap-app:8080/ws` → `https://api.example.org/gateway/ws`.

Chỉ cấu hình proxy chuyển tiếp thành công **không tự bảo đảm** WSDL chứa địa chỉ SOAP công khai chính xác. Ngược lại, đổi `soap:address` trong WSDL không tạo route tương ứng tại proxy.

## 3. Cơ chế công bố WSDL của Spring-WS

Với cấu hình Spring-WS thông dụng, `MessageDispatcherServlet` công bố các bean `WsdlDefinition`, chẳng hạn `DefaultWsdl11Definition`, dưới tên `<bean-name>.wsdl` theo mapping của servlet. Ví dụ bean tên `orders` và servlet mapping `/ws/*` thường cho URL `/ws/orders.wsdl`.

Trong **Spring Boot** hoặc ứng dụng Servlet cấu hình bằng Java, một cấu hình minh họa:

~~~java
import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.transport.http.MessageDispatcherServlet;
import org.springframework.ws.wsdl.wsdl11.DefaultWsdl11Definition;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@EnableWs
@Configuration
public class OrdersSoapConfig {

    @Bean
    public ServletRegistrationBean<MessageDispatcherServlet> soapServlet(
            ApplicationContext context) {
        MessageDispatcherServlet servlet = new MessageDispatcherServlet();
        servlet.setApplicationContext(context);
        servlet.setTransformWsdlLocations(true);
        return new ServletRegistrationBean<>(servlet, "/ws/*");
    }

    @Bean
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(
                new ClassPathResource("xsd/orders.xsd"));
    }

    @Bean(name = "orders")
    public DefaultWsdl11Definition ordersWsdl(XsdSchema ordersSchema) {
        DefaultWsdl11Definition wsdl = new DefaultWsdl11Definition();
        wsdl.setPortTypeName("OrdersPort");
        wsdl.setLocationUri("/ws");
        wsdl.setTargetNamespace("urn:example:orders:service:v1");
        wsdl.setSchema(ordersSchema);
        return wsdl;
    }
}
~~~

Giả định `orders.xsd` định nghĩa các phần tử request/response theo quy ước mà `DefaultWsdl11Definition` sử dụng để tạo operation. Mã trên **không phải ứng dụng hoàn chỉnh**: còn thiếu endpoint, lớp JAXB, nghiệp vụ, dependency và cấu hình bảo mật. Nếu Spring Boot của dự án **đã tự đăng ký servlet SOAP**, cần thống nhất một cơ chế đăng ký và đường dẫn để tránh hai servlet/mapping chồng nhau.

Hai điểm cần chú ý:

- `setLocationUri("/ws")` định nghĩa **địa chỉ dịch vụ** trong WSDL được tạo, theo đường dẫn nhìn từ ứng dụng backend; đây không phải URL của file `orders.wsdl`.
- `setTransformWsdlLocations(true)` yêu cầu `MessageDispatcherServlet` **biến đổi các service location trong WSDL khi phục vụ tài liệu theo request đến**. Cơ chế này giúp công bố host/scheme/port của request hiệu dụng, nhưng để dựng **prefix bên ngoài**, ứng dụng còn phải hiểu thông tin proxy chuyển tiếp hoặc được cấu hình địa chỉ công khai thích hợp.

Đặc biệt, việc biến đổi WSDL diễn ra **khi cung cấp tài liệu**, không có nghĩa Spring-WS đã đổi mapping servlet từ `/ws/*` sang `/gateway/ws/*`, và cũng không tự tạo reverse proxy.

### Khi nào WSDL được tạo động, khi nào là WSDL tĩnh?

`DefaultWsdl11Definition` là cách tạo WSDL 1.1 từ XSD và cấu hình Java; phù hợp khi mô hình dịch vụ đơn giản và muốn dùng XSD làm nguồn cho payload. Ở những tích hợp yêu cầu WSDL đã được phê duyệt, operation/binding/fault/security policy cụ thể, có thể **công bố WSDL tĩnh** qua `SimpleWsdl11Definition` hoặc cơ chế tương ứng.

Đừng giả định mọi cách phục vụ WSDL đều hỗ trợ biến đổi URL giống nhau. Việc biến đổi `soap:address` phụ thuộc **WSDL có được phục vụ qua adapter/servlet đã cấu hình hay không**. Nếu file WSDL được đặt ở một static resource server, object storage hoặc một gateway riêng, cờ của `MessageDispatcherServlet` **không tác động đến tài liệu mà servlet đó không phục vụ**.

## 4. Chuyển thông tin địa chỉ công khai qua forwarded headers

Request từ reverse proxy cần mang đủ thông tin để ứng dụng nhận ra **địa chỉ bên ngoài**. Các header thường gặp:

| Header | Ví dụ | Mục đích |
| --- | --- | --- |
| `Forwarded` (chuẩn RFC 7239) | `proto=https;host=api.example.org` | Mô tả scheme và host từ proxy tin cậy |
| `X-Forwarded-Proto` | `https` | Scheme công khai |
| `X-Forwarded-Host` | `api.example.org` | Host công khai |
| `X-Forwarded-Port` | `443` | Port công khai nếu cần |
| `X-Forwarded-Prefix` | `/gateway` | Phần prefix bên ngoài bị proxy tách khỏi URL backend |

`X-Forwarded-Prefix` là quy ước triển khai phổ biến, **không phải trường chuẩn trong RFC 7239**. Cần kiểm tra proxy và framework có hỗ trợ nó, và xem chính xác ứng dụng nhận `contextPath`/`requestURI` hiệu dụng thế nào.

Trong Spring Boot hỗ trợ cấu hình forwarded headers, một lựa chọn là:

~~~yaml
# application.yml
server:
  forward-headers-strategy: framework
~~~

Chiến lược `framework` dùng cơ chế xử lý forwarded headers ở tầng Spring Servlet/Web, thường qua `ForwardedHeaderFilter` trong ứng dụng Servlet. Trong ứng dụng Spring thuần không dùng auto-configuration này, có thể **đăng ký `ForwardedHeaderFilter` trước servlet** theo cấu hình phù hợp.

Không đồng thời bật nhiều cơ chế xử lý forwarded headers một cách tùy tiện, vì có thể gây dựng URL sai hoặc cộng prefix hai lần. Chế độ `native` dựa vào servlet container (ví dụ Tomcat) có thể xử lý scheme/host/port, nhưng mức hỗ trợ `X-Forwarded-Prefix` phụ thuộc container và cấu hình. Nếu cần prefix URL, hãy **thử trên đúng phiên bản Spring Boot, Spring Framework và container triển khai**.

### Cấu hình minh họa với Nginx

Giả định Nginx là **edge proxy trực tiếp nhận HTTPS công khai**, ứng dụng Spring-WS chạy ở `soap-app:8080`. Mục tiêu là bỏ `/gateway/` ở ngoài nhưng giữ phần `/ws/` tương ứng ở backend:

~~~nginx
server {
    listen 443 ssl;
    server_name api.example.org;

    # Cấu hình ssl_certificate / ssl_certificate_key
    # và các chính sách TLS nằm trong cấu hình triển khai thực tế.

    location /gateway/ {
        proxy_pass http://soap-app:8080/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-Prefix /gateway;
    }
}
~~~

Với cặp `location /gateway/` và `proxy_pass .../`, request `/gateway/ws/orders.wsdl` được chuyển thành `/ws/orders.wsdl` ở backend. Tương tự, request POST `/gateway/ws` cần được chuyển tới `/ws`. Kiểm tra hành vi **trailing slash**, query string và route thực tế khi triển khai; cách khai báo `proxy_pass` có hoặc không có dấu `/` cuối làm thay đổi cách Nginx xử lý URI.

Trong cấu hình này `$scheme` bằng `https` và `$server_port` bằng `443` vì Nginx nhận TLS trực tiếp. Nếu có nhiều tầng proxy, tầng bên trong có thể thấy `http` hoặc port khác; khi đó phải thống nhất **nguồn thông tin công khai từ edge tin cậy**, không sao chép vô điều kiện header do client gửi.

### Luồng request khi các tầng được cấu hình đúng

~~~mermaid
sequenceDiagram
    participant Client as SOAP client
    participant Proxy as Reverse proxy
    participant App as Spring-WS
    Client->>Proxy: GET https://api.example.org/gateway/ws/orders.wsdl
    Proxy->>App: GET /ws/orders.wsdl + forwarded headers tin cậy
    App-->>Proxy: WSDL được biến đổi service location
    Proxy-->>Client: WSDL chứa soap:address URL công khai
    Client->>Proxy: POST https://api.example.org/gateway/ws (SOAP)
    Proxy->>App: POST /ws (SOAP)
    App-->>Client: SOAP response / SOAP Fault qua proxy
~~~

Trong sơ đồ, trường hợp transform đã xử lý đúng cả scheme/host và prefix là **kết quả mong muốn cần xác minh**, không phải lời bảo đảm chỉ dựa vào tên một property. Nếu WSDL xuất ra thiếu `/gateway` hoặc có hai lần `/gateway`, hãy kiểm tra lại request URI hiệu dụng sau khi xử lý forwarded headers và quy tắc rewrite của proxy.

## 5. Cấu hình đường dẫn bên ngoài khi proxy thay đổi prefix

Đây thường là phần khó nhất vì nhiều giá trị “path” cùng tồn tại:

| Cấu hình/giá trị | Ví dụ | Tác dụng |
| --- | --- | --- |
| Context path của ứng dụng | `/` (mặc định) | Base path mà Servlet container sử dụng |
| Servlet mapping Spring-WS | `/ws/*` | Điểm vào bên backend |
| `DefaultWsdl11Definition.locationUri` | `/ws` | Địa chỉ SOAP dịch vụ được mô tả ban đầu |
| Prefix do proxy thêm | `/gateway` | Phần đường dẫn công khai không tồn tại trực tiếp trên backend |
| Đường dẫn WSDL công khai | `/gateway/ws/orders.wsdl` | Nơi client tải WSDL |
| Đường dẫn SOAP công khai | `/gateway/ws` | Nơi client POST SOAP |

Có hai cách tổ chức phổ biến:

**Cách A — Proxy thêm một prefix, backend giữ nguyên mapping.** Như ví dụ Nginx, backend vẫn sử dụng `/ws/*`. Forwarded prefix cần được xử lý đúng khi Spring dựng địa chỉ công khai. Ưu điểm là mã ứng dụng không cần biết tên gateway riêng của từng môi trường; nhưng phải test kỹ khi nhiều ingress/proxy chồng tầng.

**Cách B — Ứng dụng công bố địa chỉ bên ngoài cố định theo môi trường.** Nếu dịch vụ chỉ có một hostname/endpoint được phê duyệt, có thể cấu hình WSDL/service address hoặc tài liệu WSDL tĩnh với URL cụ thể `https://api.example.org/gateway/ws`. Cách này giảm phụ thuộc vào biến đổi động, nhưng yêu cầu quản lý cấu hình riêng giữa dev, staging, production và bảo đảm không còn một cơ chế rewrite khác ghi đè URL cố định.

**Không chỉ thay `server.servlet.context-path` bằng `/gateway` khi proxy đã bỏ prefix.** Nếu backend đồng thời có context path `/gateway` nhưng Nginx lại chuyển `/gateway/ws` thành `/ws`, servlet có thể trả 404. Ngược lại, nếu cả proxy và backend cùng giữ `/gateway`, WSDL có thể chứa prefix lặp. Cần chọn **một quy tắc nhất quán** cho route công khai, route nội bộ và location trong WSDL.

### Nếu Spring-WS không nhận được X-Forwarded-Prefix

Không có một cách sửa đường dẫn áp dụng chung cho mọi proxy. Hãy lần lượt xác minh:

1. Proxy thực sự gửi `X-Forwarded-Prefix: /gateway` đến ứng dụng, và đã **ghi đè** các bản header không đáng tin cậy từ client.
2. Cơ chế xử lý forwarded headers của Spring/Servlet container đã bật và có hiệu lực **trước** khi WSDL được xây dựng.
3. `locationUri` của `DefaultWsdl11Definition` mô tả đúng backend endpoint, không nhập nhằng giữa đường dẫn SOAP và tên file WSDL.
4. Không có thêm ingress, API gateway, servlet context path hoặc rewrite rule đang thêm/bỏ prefix lần thứ hai.
5. Nếu môi trường không hỗ trợ biến đổi đúng như yêu cầu, chuyển sang **công bố WSDL đã được điều chỉnh địa chỉ theo môi trường** và kiểm tra kết quả bằng client thật.

Thử nghiệm thực tế có giá trị hơn suy luận rằng cờ `transformWsdlLocations=true` sẽ tự giải quyết tất cả các kiểu reverse proxy.

## 6. WSDL location khác schemaLocation: phải kiểm tra cả dependency

Một WSDL có `soap:address` công khai đúng vẫn có thể **không dùng được để sinh client** nếu các XSD phụ thuộc không truy cập được. Ví dụ đoạn trong WSDL:

~~~xml
<wsdl:types
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:schema targetNamespace="urn:example:orders:service:v1">
    <xs:import namespace="urn:example:orders:data:v1"
               schemaLocation="orders.xsd"/>
  </xs:schema>
</wsdl:types>
~~~

Nếu tài liệu được tải từ `https://api.example.org/gateway/ws/orders.wsdl`, tham chiếu tương đối `orders.xsd` sẽ được giải dựa trên URL gốc thành `https://api.example.org/gateway/ws/orders.xsd`. **Địa chỉ đó thực sự phải tồn tại**, hoặc WSDL phải được thiết kế theo cách phân giải dependency khác phù hợp với client.

Với `xs:include` và `xs:import` nằm trong các XSD phụ thuộc, client tiếp tục cần resolve những đường dẫn đó. Tình huống thường gặp:

- WSDL công khai chứa `schemaLocation="http://soap-app:8080/ws/common.xsd"`: client ngoài mạng không tải được XSD.
- WSDL trỏ đúng `orders.xsd`, nhưng XSD đó include `types/common.xsd` và gateway không chuyển tiếp `/gateway/ws/types/common.xsd`.
- Proxy rewrite host/scheme đúng nhưng làm rơi path prefix ở một URL import.
- WSDL/XSD được nén, cached hoặc phục vụ qua CDN với URL base khác, khiến các đường dẫn tương đối resolve sai.

Phải phân biệt:

- **`soap:address`**: URL để gửi SOAP request; cơ chế `transformWsdlLocations` hướng đến địa chỉ service này.
- **`schemaLocation`**: gợi ý vị trí để công cụ đọc XSD. Nó không nhất thiết được sửa bởi cùng một tùy chọn; cần xem cách WSDL/schema được xuất và cơ chế transform schema locations mà phiên bản Spring-WS hỗ trợ.
- **`targetNamespace`**: định danh hợp đồng; tuyệt đối không đổi chỉ để sửa lỗi tải schema.

Trong một số phiên bản Spring-WS có cơ chế hỗ trợ biến đổi **schema locations** riêng. Hãy kiểm tra API và hành vi của chính phiên bản đang dùng trước khi bật cơ chế đó; dù cấu hình nào, vẫn phải xác nhận mọi URL import/include bằng client bên ngoài. Một giải pháp có thể dự đoán hơn là **công bố trọn bộ WSDL/XSD đã được kiểm tra**, cho phép client tải từ cùng một đường dẫn public hoặc resolver/catalog được thống nhất.

## 7. Kiểm tra bằng request thực, không chỉ nhìn vào cấu hình

Với ví dụ công khai, trước tiên tải WSDL **qua chính hostname bên ngoài**, không chỉ gọi backend:

~~~bash
curl --fail --silent --show-error \
  https://api.example.org/gateway/ws/orders.wsdl \
  -o orders.wsdl
~~~

Sau đó mở XML hoặc parse bằng công cụ XML để kiểm tra:

~~~xml
<!-- Kết quả mong muốn trong WSDL được công bố bên ngoài -->
<soap:address location="https://api.example.org/gateway/ws"/>
~~~

Đừng chỉ kiểm tra trạng thái HTTP 200. Một response có thể là trang HTML đăng nhập của gateway, redirect loop, trang 404 được reverse proxy trả theo dạng 200 hoặc WSDL chứa URL nội bộ.

### Checklist cho một WSDL có thể tiêu thụ

1. **GET WSDL:** tải được qua HTTPS public, content là XML/WSDL đúng, không chuyển hướng về địa chỉ nội bộ.
2. **Service location:** mỗi `soap:address/@location` của port dự kiến trỏ đến địa chỉ bên ngoài mà đối tác có quyền truy cập, gồm đúng scheme, hostname, port và prefix.
3. **Schema dependency:** mọi XSD `schemaLocation`, WSDL import và include có thể resolve; không lộ `localhost`, tên container hay cổng mạng riêng.
4. **SOAP POST:** gửi request thực đến địa chỉ ghi trong `soap:address`, đi qua proxy và được `MessageDispatcherServlet` nhận đúng mapping.
5. **SOAP binding:** request gửi đúng SOAP 1.1/1.2 và `Content-Type`/`SOAPAction` theo binding, không bị gateway tự chuyển thành REST/JSON.
6. **TLS:** hostname khớp chứng chỉ công khai, chuỗi tin cậy hợp lệ và chính sách mTLS (nếu có) được áp dụng đúng tầng.
7. **Fault:** lỗi SOAP trả về đúng Envelope/Fault theo contract, không bị proxy thay thế bằng HTML error page khi ứng dụng đã gửi Fault hợp lệ.
8. **Tương thích:** công cụ đối tác (Java, .NET, ESB…) sinh client từ **WSDL công khai** được và gọi operation thực tế thành công.

### Thử cả hai luồng thành công và lỗi

Với một request ví dụ:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:data:v1">
  <soapenv:Body>
    <ord:GetOrderRequest>
      <ord:orderId>ORD-1024</ord:orderId>
    </ord:GetOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

SOAP client phải POST tới `https://api.example.org/gateway/ws` với header đúng hợp đồng. Để kiểm thử lỗi, cố ý gửi request sai schema hoặc thiếu xác thực: nếu ứng dụng sinh SOAP Fault thì proxy phải chuyển tiếp hợp lý. Không kỳ vọng mọi lỗi HTTP của proxy sẽ biến thành SOAP Fault: lỗi gateway (ví dụ 502 do backend chết) có thể là HTTP error **không chứa SOAP Envelope**.

### Kiểm thử nhiều góc nhìn mạng

| Nguồn gọi | Đích kiểm tra | Điều có thể phát hiện |
| --- | --- | --- |
| Máy phát triển | `http://localhost:8080/ws/orders.wsdl` | Backend servlet/WSDL hoạt động nhưng chưa nói lên trạng thái public |
| Container cùng mạng | `http://soap-app:8080/ws/orders.wsdl` | DNS/service nội bộ, mapping backend |
| Client ngoài mạng | `https://api.example.org/gateway/ws/orders.wsdl` | TLS, proxy headers, prefix và location công khai |
| Client SOAP độc lập | POST tới `soap:address` thực tế | Binding, SOAPAction, JAXB/schema, security và routing |

Nếu chỉ test qua `localhost`, bạn sẽ không phát hiện vấn đề mà đối tác thực sự gặp phải khi lấy WSDL bên ngoài.

## 8. Bảo mật forwarded headers và thông tin công bố

Các header `Forwarded` và `X-Forwarded-*` **không tự chứng minh** chúng được gửi bởi proxy đáng tin cậy. Nếu backend nhận trực tiếp header do Internet client tự đặt, người tấn công có thể cố khiến ứng dụng tạo WSDL chứa hostname do họ chọn.

Ví dụ rủi ro:

~~~http
GET /ws/orders.wsdl HTTP/1.1
Host: api.example.org
X-Forwarded-Host: attacker.example.net
X-Forwarded-Proto: https
~~~

Nếu backend tin header trên, WSDL có thể trả:

~~~xml
<soap:address location="https://attacker.example.net/gateway/ws"/>
~~~

Đây là một dạng **host/header poisoning**, có thể làm client sinh mã với endpoint sai hoặc khiến hệ thống lưu nhầm địa chỉ trong cache. Do đó:

- Chỉ cho phép backend nhận lưu lượng từ **reverse proxy tin cậy** (network policy/firewall/ingress ACL).
- Tại proxy biên, **loại bỏ hoặc ghi đè** forwarded headers do client tự gửi; chỉ chuyển thông tin canonical của host/proto/port/prefix đã kiểm soát.
- Giới hạn **allowed hosts** và thông tin địa chỉ public mà ứng dụng được phép công bố. Với hệ thống chỉ có một endpoint cố định, cân nhắc cấu hình địa chỉ public tĩnh thay vì tin mọi hostname từ request.
- Nếu có nhiều proxy, thống nhất proxy nào có quyền thiết lập header và cách xử lý danh sách nhiều giá trị; không lấy giá trị bất kỳ từ chuỗi do client điều khiển.
- Tránh cache WSDL biến đổi theo request host/proto ở một shared cache nếu cache không phân biệt chính xác host/path/headers; cân nhắc không cache hoặc dùng cache key và chính sách cụ thể.

### TLS/mTLS và WS-Security qua reverse proxy

Trong tích hợp doanh nghiệp, **TLS** bảo vệ đường truyền client–proxy; nếu proxy kết thúc TLS rồi chuyển HTTP vào backend, đây là **hai chặng kết nối khác nhau**. Đánh giá chính sách an toàn của chặng proxy–backend và việc chuyển tiếp danh tính client nếu hệ thống yêu cầu mTLS.

**WS-Security** hoạt động ở tầng SOAP message: ký/mã hóa body/header, sử dụng token, timestamp hoặc chứng chỉ theo hợp đồng. Việc proxy đổi WSDL URL **không tự biến đổi chữ ký SOAP đã được tạo**, nhưng nếu proxy hoặc adapter sửa **SOAP Body/Header đã ký**, việc xác minh chữ ký có thể thất bại. Các interceptor dựa trên WSS4J trong Spring-WS vẫn cần chính sách và truststore phù hợp.

Thông điệp SOAP Fault, header `SOAPAction` và namespace của payload cũng phải được giữ nguyên theo hợp đồng, trừ khi gateway là một thành phần SOAP-aware được thiết kế chủ đích. Tránh giải pháp “sửa chuỗi SOAP XML trên proxy” để bù cho việc WSDL công bố sai địa chỉ.

## 9. Chẩn đoán các lỗi hay gặp

| Hiện tượng | Nguyên nhân có thể | Nơi cần kiểm tra |
| --- | --- | --- |
| Tải WSDL qua HTTPS được, nhưng `soap:address` là `http://soap-app:8080/ws` | WSDL transform chưa bật hoặc forwarded headers chưa được xử lý | `setTransformWsdlLocations`, strategy, request hiệu dụng |
| `soap:address` có host đúng nhưng thiếu `/gateway` | Prefix bị proxy bỏ mà framework không nhận biết | `X-Forwarded-Prefix`, filter/container và rewrite rule |
| `soap:address` có `/gateway/gateway/ws` | Cộng prefix ở cả proxy và ứng dụng/WSDL | Context path, `locationUri`, filter và ingress |
| WSDL có `https` nhưng port `8080` | Port công khai sai hoặc truyền headers không nhất quán | `Forwarded`, `X-Forwarded-Port`, TLS termination |
| WSDL trả đúng trên máy dev nhưng sai qua gateway | Chỉ test backend hoặc cấu hình môi trường lệch nhau | So sánh cùng một WSDL qua URL nội bộ/public |
| Client sinh mã lỗi “schema not found” | `schemaLocation` trỏ vào nội bộ hoặc URL import bị 404 | WSDL/XSD import graph, public routing |
| WSDL đúng nhưng SOAP POST 404 | Gateway route GET hoạt động, POST vào URL khác hoặc servlet mapping sai | `soap:address`, method/route/path, trailing slash |
| SOAP request đến được nhưng bị từ chối | Sai SOAP version, QName, JAXB, xác thực hoặc chữ ký | SOAP Envelope, interceptor, log server có kiểm soát |
| SOAP client báo lỗi TLS certificate | Hostname/trust chain/mTLS sai ở public endpoint | Chứng chỉ edge, SNI và client truststore |
| WSDL thay đổi ngẫu nhiên theo Host/header | Tin header từ client hoặc cache sai | Proxy header sanitization và caching |
| SOAP Fault biến thành trang HTML gateway | Proxy xử lý status/body thay ứng dụng | Cấu hình proxy error interception, timeout, body forwarding |

### Chẩn đoán theo thứ tự để tìm đúng tầng lỗi

~~~mermaid
flowchart TD
    A["GET WSDL qua URL công khai"] --> B{"Đọc được WSDL?"}
    B -->|Không| C["Sửa DNS, TLS, route GET, proxy"]
    B -->|Có| D{"soap:address đúng URL public?"}
    D -->|Không| E["Kiểm tra locationUri,<br/>transformWsdlLocations,<br/>forwarded headers/prefix"]
    D -->|Có| F{"Resolve được WSDL/XSD imports?"}
    F -->|Không| G["Sửa schemaLocation,<br/>đường dẫn publish, resolver"]
    F -->|Có| H{"SOAP POST đến endpoint hoạt động?"}
    H -->|Không| I["Kiểm tra route POST,<br/>mapping, SOAP binding"]
    H -->|Có| J["Kiểm tra QName, JAXB,<br/>Fault, WS-Security và nghiệp vụ"]
~~~

Sơ đồ giúp tránh sửa XSD/WSDL namespace hoặc code JAXB khi nguyên nhân thực sự là proxy rewrite và forwarded headers.

## 10. Chọn cách công bố địa chỉ cho từng kiểu môi trường

| Bối cảnh | Cách tiếp cận nên cân nhắc | Điểm phải kiểm tra |
| --- | --- | --- |
| Local development không qua proxy | WSDL/endpoint ở `localhost` và mapping `/ws/*` | Không dùng kết quả local để khẳng định public đã đúng |
| Một reverse proxy, một domain public | Biến đổi WSDL theo request + forwarded headers đã tin cậy | Scheme/host/port/prefix thực tế |
| Nhiều proxy/ngõ vào khác nhau | Quy ước forwarded headers nhất quán hoặc endpoint public cố định | Host allowlist, multi-hop headers, cache |
| Đối tác yêu cầu hợp đồng cố định, phát hành có kiểm soát | WSDL tĩnh/versioned với service address được quản lý theo môi trường | Artifact và URL công bố ổn định, imports đi cùng |
| Dịch vụ nhiều tenant/hostname | Có thể công bố WSDL động theo hostname được phép | Không tin hostname tùy ý, tránh cache nhầm tenant |
| WSDL nhiều import, XSD nhiều namespace | Công bố toàn bộ dependency qua public URL/resolver | Schema graph có thể đọc từ bên ngoài |

Việc chọn WSDL động hay tĩnh phụ thuộc quản trị hợp đồng, hạ tầng và công cụ client. **Contract-first** có thể dùng cả hai: trọng tâm là **WSDL/XSD công bố có thể tiêu thụ độc lập**, dữ liệu và operation thống nhất với runtime.

## 11. Một kịch bản triển khai từ đầu đến cuối

Tóm lại trong ví dụ `OrdersService`, hãy đối chiếu năm thành phần sau:

1. **Backend:** Spring-WS phục vụ `/ws/orders.wsdl` và SOAP endpoint `/ws`.
2. **WSDL definition:** `DefaultWsdl11Definition` có `locationUri="/ws"`, schema và namespace hợp lệ.
3. **Servlet:** `MessageDispatcherServlet` có `transformWsdlLocations=true` để có thể biến đổi service location khi công bố.
4. **Proxy và forwarded headers:** HTTPS public `/gateway/ws/*` được chuyển đúng sang backend `/ws/*`; scheme, host, port và prefix bên ngoài đến được Spring theo cơ chế trusted.
5. **Xác minh từ client ngoài:** tải `https://api.example.org/gateway/ws/orders.wsdl`, thấy `soap:address location="https://api.example.org/gateway/ws"`, resolve mọi XSD, sinh SOAP client và gửi request thành công.

Nếu WSDL đã đúng mà SOAP client vẫn lỗi, **đừng sửa URL mù quáng**. Tiếp tục chẩn đoán SOAP binding, QName/XSD, JAXB, Fault, interceptor, WS-Security, chứng chỉ và logic nghiệp vụ theo từng lớp.

## 12. Bài thực hành tự kiểm tra

**Tình huống:** Một dịch vụ Spring-WS ban đầu hoạt động tại `http://orders:8080/ws/orders.wsdl` và được công bố qua gateway ở `https://services.example.com/ext/soap/orders.wsdl`. Gateway chuyển `/ext/soap/*` vào backend `/ws/*`. Sau khi triển khai, client tải được WSDL nhưng bên trong `soap:address` vẫn là `http://orders:8080/ws`.

1. Viết lại **URL WSDL công khai**, **URL SOAP endpoint công khai**, **URL SOAP backend** và chỉ ra chỗ không khớp của WSDL.
2. Đề xuất cấu hình `setTransformWsdlLocations` và forwarded headers; giải thích vì sao chỉ sửa `Host` có thể chưa đủ nếu vẫn thiếu `/ext/soap`.
3. Thiết kế quy tắc rewrite ở proxy sao cho GET `/ext/soap/orders.wsdl` và POST `/ext/soap` đều tới backend chính xác.
4. Nếu WSDL import `common.xsd`, dự đoán client sẽ cố tải schema từ URL nào khi import là **đường dẫn tương đối**. Cần công bố tài nguyên nào ở gateway?
5. Tạo một trường hợp sai với `X-Forwarded-Host: untrusted.example` và mô tả cách proxy/ứng dụng phải ngăn việc WSDL bị biến đổi theo header đó.
6. Giả sử client đã gửi đúng URL SOAP nhưng nhận lỗi xác minh chữ ký WS-Security, nêu vì sao đổi `soap:address` không phải lời giải và cần kiểm tra tầng nào.
7. Kiểm tra WSDL ở staging và production: liệt kê những giá trị nên khác nhau (scheme/host/path/port) và những định danh hợp đồng **không nên thay đổi ngẫu nhiên** (QName, target namespace, operation, binding).

**Kết luận:** Địa chỉ được công bố trong WSDL phải phản ánh **đường đi mà SOAP client thực sự truy cập được**, còn proxy phải đưa GET WSDL, GET XSD và POST SOAP tới đúng backend. Với Spring-WS, `transformWsdlLocations` kết hợp forwarded headers đáng tin cậy có thể giải quyết việc biến đổi service address; các trường hợp thêm/bỏ path prefix hoặc phát hành WSDL tĩnh cần kiểm tra riêng. Chỉ khi URL WSDL, `soap:address`, schema dependencies, SOAP binding và chính sách bảo mật cùng nhất quán thì hợp đồng contract-first mới thực sự sử dụng được trong môi trường doanh nghiệp.
