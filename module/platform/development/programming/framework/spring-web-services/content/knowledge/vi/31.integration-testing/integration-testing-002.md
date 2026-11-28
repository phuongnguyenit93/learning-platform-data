# Kiểm tra URL WSDL, XSD import và địa chỉ dịch vụ sau triển khai

## 1. Vì sao endpoint chạy được chưa chứng minh WSDL đã publish đúng?

Trong module **SPRING_WEB_SERVICES**, dịch vụ SOAP được xây dựng theo hướng contract-first: XSD định nghĩa cấu trúc dữ liệu, WSDL mô tả operations/messages/bindings/service ports, JAXB ánh xạ XML–Java và Spring-WS triển khai endpoint/client. Khi triển khai lên application server, container, reverse proxy hoặc ingress, URL public mà consumer cần dùng có thể khác URL nội bộ mà ứng dụng đang lắng nghe.

Một endpoint có thể trả SOAP response khi gọi trực tiếp trong cluster nhưng WSDL public vẫn chứa địa chỉ localhost, HTTP thay vì HTTPS, thiếu context path, sai host hoặc port. WSDL root có thể tải thành công nhưng một XSD được import bằng relative path lại trả 404. Một schema import có thể resolve trong môi trường dev nhưng thất bại sau khi deploy vì base URL, proxy rewrite hoặc resource packaging khác nhau.

Bài học tập trung vào ba kiểm tra gắn với nhau:

1. **WSDL publication URL:** consumer truy cập được WSDL qua địa chỉ công bố chính thức.
2. **XSD import/include closure:** toàn bộ schema dependencies được resolve và có nội dung đúng.
3. **Service endpoint address:** soap:address/wsa:Address trong contract trỏ tới địa chỉ thực sự có thể gọi sau triển khai.

Không dừng ở HTTP 200 của WSDL. Cần tải toàn bộ dependency graph, xác thực contract, đọc endpoint address và thực hiện một SOAP smoke test qua đúng đường mạng public.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt WSDL retrieval URL với SOAP service endpoint URL.
2. Phân tích WSDL service/port/binding và soap:address.
3. Phát hiện localhost, private host, sai scheme, port, context path và proxy prefix.
4. Resolve đầy đủ WSDL import, XSD import/include/redefine và relative locations.
5. Hiểu base URI và quy tắc resolve relative URL.
6. Cấu hình Spring-WS WSDL publication và xác minh URL sau deployment.
7. Kiểm tra ảnh hưởng của reverse proxy, ingress và forwarded headers.
8. Dùng XML catalog/offline artifacts khi build hoặc test không có network.
9. Xây deployment smoke tests cho WSDL, XSD và SOAP operations.
10. Chẩn đoán lỗi DNS, TLS, routing, content type, schema và environment drift.

## 2. Phân biệt ba loại URL

Một deployment có thể liên quan ít nhất ba địa chỉ khác nhau:

| URL | Vai trò | Ví dụ minh họa |
|---|---|---|
| WSDL retrieval URL | Tải contract XML | https://api.example.test/soap/orders.wsdl |
| XSD dependency URL | Tải schema được import/include | https://api.example.test/soap/schemas/orders.xsd |
| SOAP endpoint URL | Gửi SOAP POST | https://api.example.test/soap/orders |

Các URL có thể cùng host/path prefix nhưng không nhất thiết giống nhau. WSDL URL thường là địa chỉ GET để consumer lấy contract; SOAP endpoint là địa chỉ POST được khai báo trong service port/binding.

### 2.1. WSDL URL không nhất thiết là endpoint URL

Một consumer có thể tải WSDL từ:

~~~text
https://gateway.example.test/contracts/orders?wsdl
~~~

nhưng gửi SOAP tới:

~~~text
https://gateway.example.test/services/orders
~~~

Đây là mô hình hợp lệ nếu WSDL soap:address trỏ tới SOAP endpoint. Không cấu hình client gọi POST vào URL WSDL chỉ vì cả hai thuộc cùng service.

### 2.2. Endpoint URL trong WSDL

WSDL 1.1 có thể khai báo địa chỉ HTTP trong phần service port:

~~~xml
<wsdl:service name="OrdersService">
  <wsdl:port name="OrdersSoap11" binding="tns:OrdersSoap11Binding">
    <soap:address
        location="https://api.example.test/soap/orders"/>
  </wsdl:port>
</wsdl:service>
~~~

Với SOAP 1.2, binding có thể dùng soap12:address. Consumer generated từ WSDL thường lấy địa chỉ này làm default endpoint, dù nhiều client cho phép override bằng configuration.

### 2.3. URL public và URL nội bộ

Ví dụ deployment qua reverse proxy:

~~~text
Consumer
  -> https://partner.example.com/integration/soap/orders
  -> Reverse proxy / ingress
  -> http://orders-service:8080/soap/orders
  -> Spring-WS MessageDispatcherServlet
~~~

WSDL public cần đưa ra URL consumer có thể truy cập, trong khi upstream address là chi tiết nội bộ. Không để contract public vô tình lộ service DNS nội bộ hoặc hostname của container.

## 3. Đọc WSDL để xác định service address

WSDL 1.1 thường có các thành phần:

- types: schema definitions hoặc import XSD.
- message: dữ liệu input/output/fault.
- portType: abstract operations.
- binding: SOAP version, style/use, SOAPAction và wire protocol.
- service: một hoặc nhiều ports.
- port: binding cụ thể và endpoint address.

### 3.1. Một WSDL giản lược

~~~xml
<definitions
    xmlns="http://schemas.xmlsoap.org/wsdl/"
    xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
    xmlns:tns="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1">

  <service name="OrdersService">
    <port name="OrdersSoap11" binding="tns:OrdersSoap11Binding">
      <soap:address
          location="https://api.example.test/soap/orders"/>
    </port>
  </service>
</definitions>
~~~

Đây chỉ là fragment minh họa; một WSDL có thể có nhiều services/ports/bindings. Consumer phải chọn đúng port tương ứng SOAP version và policy được hỗ trợ.

### 3.2. Nhiều ports

Một service có thể publish SOAP 1.1 và SOAP 1.2 ports, hoặc nhiều endpoint addresses cho các bindings khác nhau. Smoke test không nên chỉ tìm phần tử đầu tiên mang local name address. Hãy chọn đúng QName:

- {http://schemas.xmlsoap.org/wsdl/soap/}address cho SOAP 1.1.
- {http://schemas.xmlsoap.org/wsdl/soap12/}address cho SOAP 1.2.

### 3.3. soap:address và WSDL retrieval location khác nhau

WSDL retrieval URL là URL tải tài liệu. soap:address location là endpoint nhận SOAP message. WSDL có thể được host ở contract registry/CDN nhưng endpoint nằm trên gateway khác.

### 3.4. Address phải phù hợp binding

Một port dùng SOAP 1.2 binding nhưng consumer gọi endpoint chỉ cấu hình SOAP 1.1 sẽ không tương thích chỉ vì URL giống nhau. Kiểm cả binding QName, address, SOAP version và HTTP Content-Type.

## 4. Spring-WS publish WSDL như thế nào?

Spring-WS thường publish WSDL thông qua servlet mapping và endpoint definitions. Trong cấu hình contract-first, ứng dụng có thể dùng DefaultWsdl11Definition và XsdSchema để expose WSDL từ XSD resources.

Ví dụ Java configuration giản lược:

~~~java
@Bean(name = "orders")
public DefaultWsdl11Definition ordersWsdl(XsdSchema ordersSchema) {
    DefaultWsdl11Definition definition =
        new DefaultWsdl11Definition();

    definition.setPortTypeName("OrdersPort");
    definition.setLocationUri("/soap/orders");
    definition.setTargetNamespace("urn:example:orders:v1");
    definition.setSchema(ordersSchema);

    return definition;
}

@Bean
public XsdSchema ordersSchema() {
    return new SimpleXsdSchema(
        new ClassPathResource("xsd/orders.xsd")
    );
}
~~~

Với servlet mapping phù hợp, resource có thể được publish tại URL WSDL theo convention của Spring-WS, ví dụ servlet path cộng tên bean và hậu tố WSDL. Convention phụ thuộc version/configuration; xác minh bằng HTTP request ở môi trường đã deploy, không suy từ tên bean.

### 4.1. locationUri là gì?

locationUri thường là URI path dùng để sinh soap:address trong generated/published WSDL. Nó không nhất thiết là URL đầy đủ có scheme/host. Trong deployment sau proxy, path phải khớp public routing và cách Spring-WS xây dựng service address.

### 4.2. DefaultWsdl11Definition và XSD schema

Generated WSDL có thể phụ thuộc cách Spring-WS suy operation/message từ schema element names và naming conventions. Khi đổi schema/bean settings, kiểm WSDL thực tế đã publish thay vì chỉ review cấu hình Java.

### 4.3. Static WSDL và generated WSDL

Có thể publish static WSDL file hoặc generated WSDL. Static artifact kiểm soát contract identity tốt nhưng cần update address/imports cho từng môi trường hoặc dùng policy/catalog/placeholder strategy. Generated WSDL linh hoạt hơn nhưng có thể phụ thuộc request context và proxy headers. Chọn cách quản lý rõ ràng, version hóa contract.

## 5. Context path, servlet mapping và application base path

Endpoint nội bộ có thể nằm tại:

~~~text
http://orders-service:8080/soap/orders
~~~

nhưng public path là:

~~~text
https://partner.example.com/platform/integration/soap/orders
~~~

Các yếu tố ảnh hưởng gồm:

- Servlet mapping của MessageDispatcherServlet.
- Application context path.
- Reverse proxy path prefix/rewrite.
- Ingress route.
- API gateway base path.
- Container port mapping.
- Deployment environment profile.

### 5.1. Servlet mapping

Nếu MessageDispatcherServlet map theo /soap/* thì endpoint URL sẽ khác khi app có context path /orders-app. Kiểm full path sau deploy, không chỉ servlet mapping riêng.

### 5.2. Proxy path rewrite

Proxy có thể nhận /integration/soap và forward /soap. Nếu WSDL phát sinh address dựa nội bộ hoặc forwarded path không được xử lý đúng, consumer sẽ thấy URL thiếu /integration hoặc chứa path nội bộ.

### 5.3. Trailing slash

URL kết thúc bằng slash và không có slash có thể được routing khác nhau tùy proxy/server. Relative imports cũng có thể resolve khác khi base URI là directory hay file URL. Chuẩn hóa convention và test đúng path production.

## 6. Reverse proxy, ingress và forwarded headers

Khi ứng dụng chạy sau TLS-terminating reverse proxy, app có thể chỉ thấy HTTP nội bộ trong khi caller dùng HTTPS public. Nếu WSDL được tạo từ request context, sai forwarded headers có thể sinh soap:address sai scheme/host/port.

Các forwarded metadata thường gặp:

- Forwarded: RFC 7239 standardized header.
- X-Forwarded-Proto: scheme bên ngoài.
- X-Forwarded-Host: host bên ngoài.
- X-Forwarded-Port: port bên ngoài.
- X-Forwarded-Prefix: prefix do một số proxy convention sử dụng.

Các header này chỉ đáng tin khi được proxy tin cậy xóa/ghi lại. Không cho client gửi tùy ý X-Forwarded-Host để quyết định URL công bố; nếu app tin header không kiểm soát, có thể tạo host injection hoặc link poisoning.

### 6.1. Kiểm tra proxy chain

Xác minh:

1. Proxy strip các forwarded headers do client gửi vào.
2. Proxy tự gắn giá trị dựa request đã nhận.
3. App chỉ trust proxy hop/addresses đã cấu hình.
4. Host/scheme/port/prefix được giữ đúng qua chain.
5. WSDL public không trả private host, internal port hoặc HTTP downgrade.

### 6.2. Không sửa URL bằng string replace tùy tiện

Thay hostname hoặc scheme trong WSDL sau khi generate có thể phá XML escaping, port selection, SOAP 1.2 address hoặc imported links. Nếu cần rewrite, dùng cấu hình/framework-aware strategy hoặc explicit public base URL.

### 6.3. Kiểm host injection

Gửi request với Host/X-Forwarded-Host giả từ môi trường test. WSDL không được publish address theo host tùy ý nếu request không qua trusted proxy. Không thực hiện test này trên production public service nếu chưa có test plan được duyệt.

## 7. WSDL import và XSD import/include: dependency closure

WSDL/XSD không nhất thiết là một file duy nhất. WSDL có thể import WSDL khác; WSDL types có thể import XSD; XSD có thể import, include hoặc redefine schemas khác.

Ví dụ WSDL:

~~~xml
<wsdl:definitions
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    targetNamespace="urn:example:orders:v1">

  <wsdl:types>
    <xs:schema>
      <xs:import
          namespace="urn:example:common:v1"
          schemaLocation="schemas/common.xsd"/>
      <xs:import
          namespace="urn:example:orders:v1"
          schemaLocation="schemas/orders.xsd"/>
    </xs:schema>
  </wsdl:types>
</wsdl:definitions>
~~~

### 7.1. import và include

- xs:import dùng để tham chiếu schema có target namespace khác (hoặc schema không namespace theo rules).
- xs:include kết hợp schema cùng target namespace hoặc schema chameleon theo XSD rules.
- xs:redefine có semantics nâng cao và có thể ảnh hưởng định nghĩa type/group.
- wsdl:import tham chiếu WSDL definitions khác, thường với namespace tương ứng.

Không thay import bằng include chỉ vì URL tải được; quan hệ namespace/schema composition phải hợp lệ.

### 7.2. Relative schemaLocation

Nếu WSDL được tải từ:

~~~text
https://api.example.test/contracts/orders.wsdl
~~~

và schemaLocation là:

~~~text
schemas/orders.xsd
~~~

thì URL tương đối được resolve dựa vào base URI của tài liệu chứa reference, thông thường thành:

~~~text
https://api.example.test/contracts/schemas/orders.xsd
~~~

Nếu WSDL được tải qua URL khác hoặc proxy rewrite path, resolved URL có thể thay đổi.

### 7.3. Query string và redirects

Khi WSDL URL có query string như ?wsdl hoặc redirect sang canonical URL, base URI dùng để resolve relative imports cần được xác minh theo URI thực tế sau redirect/parser behavior. Đừng tự giả định relative links sẽ resolve dựa trên SOAP endpoint URL.

### 7.4. Nested imports

orders.xsd có thể import common.xsd; common.xsd có thể import money.xsd. Phải tải/resolve đệ quy tới toàn bộ dependency closure, không chỉ một cấp.

## 8. Quy tắc resolve URI và lỗi thường gặp

Một vài dạng location:

| schemaLocation | Base URI | Kết quả tổng quát |
|---|---|---|
| schemas/orders.xsd | https://host/contracts/orders.wsdl | /contracts/schemas/orders.xsd |
| ../shared/common.xsd | https://host/contracts/orders.wsdl | /shared/common.xsd |
| /schemas/common.xsd | https://host/contracts/orders.wsdl | /schemas/common.xsd |
| https://schema.example.test/common.xsd | Bất kỳ | Absolute URL giữ nguyên |
| file:/.../common.xsd | Local file base | Local resource, cần policy cho phép |

Đây là minh họa URI resolution; xử lý chính xác theo RFC 3986/XML parser/catalog và final document base URI.

### 8.1. Sai chữ hoa/thường

Path URL trên nhiều web servers phân biệt case. orders.xsd khác Orders.xsd. Test chạy trên Linux/container vì Windows development filesystem có thể không phát hiện khác biệt này.

### 8.2. File không được package

XSD có thể tồn tại trong source tree nhưng bị bỏ khỏi JAR/WAR hoặc sai classpath. Build local pass không chứng minh deployed artifact có resource. Kiểm tra artifact và request public sau deployment.

### 8.3. Import URL nội bộ

WSDL có thể lộ http://orders-service:8080/internal/common.xsd. Consumer bên ngoài không resolve DNS private được. Thay bằng relative public resource hoặc contract hosting/catalog có version.

### 8.4. Namespace không khớp import

XSD imported namespace và namespace khai báo trong xs:import phải tương ứng schema thực tế. Tải HTTP 200 không chứng minh schema composition hợp lệ.

## 9. Static contract artifacts và XML Catalog

Một cách ổn định là quản lý WSDL/XSD như artifacts version hóa, sau đó serve chúng theo cấu trúc có thể dự đoán.

~~~text
contracts/
  orders/
    v1/
      orders.wsdl
      schemas/
        orders.xsd
        common.xsd
        money.xsd
      policy/
        ws-security-policy.xml
~~~

### 9.1. XML Catalog

XML Catalog cho phép map public/system identifiers hoặc URIs sang local files. Điều này hữu ích khi codegen/test cần reproducible builds, không phụ thuộc schema URL bên ngoài.

Ví dụ catalog đơn giản:

~~~xml
<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">
  <uri
      name="https://contracts.example.test/orders/v1/schemas/common.xsd"
      uri="schemas/common.xsd"/>
</catalog>
~~~

Cấu hình catalog resolver phụ thuộc JAXB/XJC/XML parser/toolchain. Catalog phải được pin cùng contract release và test rằng không silently resolve sang schema cũ.

### 9.2. Offline build

CI có thể validate/codegen từ local immutable artifacts để tránh network flakiness. Tuy nhiên bước deployment smoke test vẫn cần kiểm public URL đã publish và dependency links thực tế.

### 9.3. Không dùng catalog che lỗi deployment

Catalog local khiến test build pass dù public XSD URL trả 404. Giữ hai lớp kiểm tra riêng: offline contract validation và online publication smoke test.

## 10. Spring-WS endpoint publication test

Một bài kiểm thử publication cần kiểm tra URL trong servlet/application context thực tế. Các bước có thể gồm:

1. Start application với profile/container tương ứng.
2. Gọi GET vào WSDL publication URL.
3. Kiểm status, content type và XML parse.
4. Kiểm WSDL service/port/binding/soap:address.
5. Tải toàn bộ WSDL/XSD dependency closure.
6. Kiểm schema compile/validate.
7. POST một SOAP request synthetic tới endpoint trong WSDL.
8. Kiểm response/Fault đúng contract.
9. Ghi contract version/checksum và deployment identity.

### 10.1. Không chỉ assert HTTP 200

Một proxy có thể trả HTML login page hoặc generic SPA fallback với status 200. Kiểm Content-Type, XML root QName, WSDL definitions namespace và document validity.

### 10.2. WSDL publication URL convention

Spring-WS có conventions expose WSDL resources thông qua servlet mapping và bean name. Thay đổi context path hoặc servlet mapping có thể đổi URL. Đừng hard-code convention mà chưa verify trên version Spring-WS đang dùng.

### 10.3. Test từng port/binding

Nếu WSDL có nhiều ports, assert address và SOAP version cho từng binding được hỗ trợ. Không bỏ qua một port chỉ vì test port đầu thành công.

## 11. Download và validate dependency closure

Một validator nên thực hiện:

- Fetch root WSDL và giữ final URL sau redirects.
- Parse XML namespace-aware, disable unsafe external entities.
- Tìm wsdl:import, xs:import, xs:include, xs:redefine.
- Resolve location theo base URI của document chứa reference.
- Fetch dependency với allowlist/safe scheme policy.
- Theo dõi visited URIs để tránh loop.
- Kiểm status/content type/size và XML root QName.
- Kiểm targetNamespace với import/include declaration.
- Tiếp tục đệ quy.
- Compile schema graph bằng XML Schema processor.
- Báo lỗi kèm source URI và referenced location.

### 11.1. Cycle và duplicate imports

Schema graph có thể có shared dependencies hoặc cycle hợp lệ theo dependency semantics/tool handling. Dùng visited set theo canonicalized URI để tránh tải vô hạn; không đơn giản đánh dấu duplicate là error nếu XML Schema processor cho phép.

### 11.2. Redirect policy

Giới hạn redirect count và chỉ theo schemes/hosts được chấp thuận. Tránh để WSDL URL dẫn tới localhost, link-local metadata endpoint hoặc internal network resources trong validator. Contract URLs là input không tin cậy trong CI.

### 11.3. Content validation

Status 200 chưa đủ. Kiểm media/content thực tế là XML expected, parse đúng root definitions/schema, size hợp lý và namespace đúng. Cẩn thận proxy trả login HTML/maintenance page.

## 12. Service address và nhiều deployment environments

Một contract có thể được dùng ở dev, test, staging, production. Address phải được quản lý theo environment, nhưng contract schema/namespace/version thường phải giữ consistency nếu đó là cùng contract release.

| Environment | WSDL public URL | SOAP address dự kiến |
|---|---|---|
| Dev | https://dev.example.test/contracts/orders.wsdl | https://dev.example.test/soap/orders |
| Test | https://test.example.test/contracts/orders.wsdl | https://test.example.test/soap/orders |
| Staging | https://staging.example.test/contracts/orders.wsdl | https://staging.example.test/soap/orders |
| Production | https://api.example.com/contracts/orders.wsdl | https://api.example.com/soap/orders |

Đây là dữ liệu minh họa. Không đưa production address vào artifacts test nếu consumer test cần endpoint độc lập.

### 12.1. Tránh environment drift

Không để staging WSDL chứa production endpoint hoặc production WSDL trỏ test schema host. Có policy cho domain allowlist theo environment và test exact address.

### 12.2. Base URL config

Nếu application generate address động, cấu hình public base URL theo deployment values thay vì suy từ Host header không tin cậy. Validate scheme/host/path trước khi publish WSDL.

### 12.3. Immutable contract, configurable address

Một số tổ chức quản lý WSDL/XSD immutable, còn endpoint address được override qua client config/service registry. Cách này giảm khác biệt artifacts giữa environments, nhưng consumer cần biết không lấy address trong WSDL làm giá trị duy nhất. Document rõ endpoint discovery contract.

## 13. TLS, DNS và network path

Sau khi URL trong WSDL đúng về cú pháp, vẫn phải xác minh đường mạng.

### 13.1. DNS

Kiểm hostname public resolve về expected gateway/load balancer trong từng environment. Trong cluster, internal DNS có thể resolve khác public DNS. Không hard-code IP thay host nếu TLS certificate/virtual hosting phụ thuộc hostname.

### 13.2. TLS certificate

Kiểm:

- Certificate SAN khớp public hostname.
- Chain có trust anchor phù hợp.
- Certificate còn hiệu lực.
- TLS protocol/cipher policy đáp ứng client stack.
- Reverse proxy terminates TLS và upstream scheme xử lý đúng.
- SNI/hostname verification không bị disable.

### 13.3. mTLS

Nếu endpoint yêu cầu client certificate, GET WSDL có thể public trong khi SOAP POST yêu cầu mTLS, hoặc cả hai đều được bảo vệ. Kiểm policy thực tế cho từng URL/resource; không suy WSDL public đồng nghĩa service operation public.

### 13.4. Connectivity và firewall

Phân biệt DNS failure, TCP connection refused, timeout, TLS handshake failure, HTTP 404/401/403/502 và SOAP Fault. Mỗi tầng có hướng debug khác nhau.

## 14. Reverse proxy path và forwarded headers trong smoke tests

Một test sau triển khai nên gọi qua URL consumer thực dùng, không chỉ gọi service từ pod/container.

~~~text
Public client
  -> DNS
  -> TLS gateway
  -> ingress route
  -> service load balancer
  -> servlet context
  -> Spring-WS endpoint
~~~

Kiểm WSDL ở public path, mọi imported schema qua public path và soap:address trỏ public SOAP endpoint. Sau đó gửi SOAP POST qua chính address đó.

### 14.1. Kiểm X-Forwarded behavior

Dùng request test bình thường qua trusted proxy và kiểm address. Với security test riêng, gửi spoofed forwarding headers từ client side để xác nhận edge proxy overwrite/strip. Không làm thay đổi public route hoặc trust settings chỉ để cho WSDL test pass.

### 14.2. Redirect

Nếu WSDL URL redirect, client generated có thể không follow redirect giống browser. Nên công bố canonical stable URL; kiểm behavior của HTTP clients/tooling được hỗ trợ.

### 14.3. Compression và charset

Kiểm gzip/deflate, XML encoding declaration, response charset và proxy transformations. Không để middleware thay bytes/encoding làm XML parser thất bại.

## 15. SOAP smoke test từ WSDL service address

Sau khi tải WSDL và resolve schemas, test thực hiện một operation có tính an toàn hoặc dedicated health operation.

### 15.1. Chọn operation

Ưu tiên read-only operation với synthetic/non-sensitive ID hoặc health operation được thiết kế riêng. Không gửi SubmitOrder/ChargePayment/CancelOrder thật chỉ để kiểm endpoint. Nếu cần test write, dùng isolated tenant và cleanup/idempotency fixture theo test environment policy.

### 15.2. Lấy address từ port đúng

Test đọc WSDL, tìm service/port và binding QName mong muốn, lấy soap:address/soap12:address, sau đó gửi request tương ứng. Không hard-code URL rồi nói đã kiểm address trong WSDL.

### 15.3. Kiểm response

Assert SOAP version, operation response QName, schema validity, expected business code và correlation ID. Đảm bảo request đi qua public route, không bypass bằng internal service hostname.

### 15.4. Security

Dùng test credentials/certificates riêng. Nếu WS-Security enabled, ký đúng parts, Timestamp và Action theo policy. Không disable TLS hostname verification hoặc trust-all certificate trong smoke tests.

## 16. Automated URL and contract verification

Một kiểm tra deployment có thể chia thành các assertions:

| Check | Assertion |
|---|---|
| WSDL GET | Public URL status 200 và XML WSDL hợp lệ |
| Root document | Root QName là wsdl:definitions |
| Binding | Có SOAP 1.1/1.2 binding đúng dự kiến |
| Service port | Port name/binding đúng |
| Address scheme | HTTPS nếu policy yêu cầu |
| Address host | Host nằm trong allowlist environment |
| Address path | Prefix/context path đúng |
| XSD imports | Mọi dependencies resolve |
| Schema compile | XML Schema processor compile thành công |
| No internal leakage | Không chứa localhost/private hostname/internal port |
| SOAP POST | Operation trả response hợp lệ qua public address |
| TLS | Certificate/hostname/chain hợp lệ |
| Security | Authentication/WS-Security policy được enforce |

### 16.1. Pseudocode URL checker

~~~text
fetch root WSDL
parse WSDL namespace-aware
assert root = wsdl:definitions

for each service port:
    resolve port binding QName
    identify SOAP 1.1 or SOAP 1.2 address
    assert address host/scheme/path matches environment policy

for each WSDL/XSD import or include:
    resolve location against current document URI
    fetch dependency safely
    parse expected XML root and namespace
    recursively inspect dependencies

compile schema closure
send a safe SOAP request to selected public service address
assert response QName and contract behavior
~~~

Đây là thuật toán khái niệm; implementation cần secure XML parser, URI allowlist, redirect limits, size/time limits và cycle detection.

### 16.2. No internal address leakage

Tìm các host patterns không được công bố: localhost, 127.0.0.1, 0.0.0.0, service DNS names, private IP ranges, container ports hoặc internal domains. Không chỉ grep text nếu XML encode/URI escaping; parse URI fields từ WSDL.

### 16.3. Environment allowlist

Maintain allowed scheme/host/path prefixes per environment. Test không chỉ kiểm host khác expected mà còn port, path, context root và binding.

## 17. Ví dụ integration test cho WSDL publication

Một test HTTP-level có thể dùng Spring Boot test với random port và HTTP client:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WsdlPublicationIntegrationTest {

    @LocalServerPort
    int port;

    @Test
    void publishesOrdersWsdl() throws Exception {
        URI wsdlUri = URI.create(
            "http://localhost:" + port + "/soap/orders.wsdl"
        );

        HttpRequest request = HttpRequest.newBuilder(wsdlUri)
            .GET()
            .build();

        HttpResponse<String> response =
            HttpClient.newHttpClient().send(
                request, HttpResponse.BodyHandlers.ofString()
            );

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("definitions"));
    }
}
~~~

Đây là skeleton minh họa. Trong test chạy sau reverse proxy, hãy gọi public test URL và assert XML root QName/namespace, không chỉ dùng contains("definitions"). Random-port localhost test chỉ xác nhận local application publication path, chưa chứng minh public proxy address đúng.

### 17.1. Kiểm address trong XML

Parse WSDL bằng namespace-aware DOM/XPath và assert SOAP port address. Không dùng regex tìm một substring bất kỳ vì WSDL có thể có nhiều ports hoặc schema chứa URL khác.

### 17.2. Kiểm content type và XML

Assert media type/XML parse và root QName. Proxy có thể trả HTML 200; body string contains "definitions" không đủ.

## 18. Test XSD imports đệ quy

Một integration test hoặc deployment checker cần theo dõi nguồn gốc từng resource:

| Requested from | Reference | Resolved URL | Expected |
|---|---|---|---|
| orders.wsdl | schemas/orders.xsd | /contracts/schemas/orders.xsd | 200 + xs:schema |
| orders.xsd | common.xsd | /contracts/schemas/common.xsd | 200 + targetNamespace common |
| common.xsd | money.xsd | /contracts/schemas/money.xsd | 200 + correct schema |
| orders.wsdl | common.wsdl | /contracts/common.wsdl | 200 + wsdl:definitions |

Bảng minh họa dependency graph.

### 18.1. Kiểm resolution base URI

Mỗi import phải resolve theo URI của document đang chứa nó, không theo root WSDL một cách cứng nhắc. Nested schema import lấy base từ nested schema URL.

### 18.2. Kiểm namespace

Assert imported XSD targetNamespace khớp namespace của xs:import; included schema phù hợp include rules. HTTP 200 với XML schema khác namespace vẫn là lỗi contract.

### 18.3. Kiểm duplicate/loop

Dùng canonical URL/visited set để tránh fetch lặp. Report dependency graph có shared node, missing node và resolution failure để người vận hành biết chính xác resource nào không khả dụng.

## 19. Contract address và schema security

WSDL/XSD là tài liệu XML có thể chứa external references. Validator chạy trong CI/deployment phải giới hạn outbound fetch.

### 19.1. SSRF risk

Nếu checker tải mọi schemaLocation từ input bất kỳ, kẻ tấn công có thể khiến nó truy cập localhost, internal services hoặc metadata endpoints. Chỉ allow schemes/hosts/path đã phê duyệt và chặn private/link-local destinations theo network policy.

### 19.2. XML parser hardening

Disable external general/parameter entities và external DTD loading theo parser API; giới hạn entity expansion, document size và nesting. Không dùng parser mặc định chưa kiểm chứng với WSDL/XSD không tin cậy.

### 19.3. Redirect and DNS rebinding

Validate cả URL trước và sau redirect; không cho redirect sang host ngoài allowlist. Với môi trường nhạy cảm, kiểm resolved destination/address theo policy để ngăn SSRF qua DNS rebinding.

### 19.4. Offline catalog

Khi đã có immutable contract artifacts, dùng catalog/local resolver cho compile test. Deployment checker vẫn phải kiểm public import links để xác nhận publication.

## 20. Deployment environments và configuration precedence

URL công bố có thể đến từ config application, environment variables, deployment chart, servlet context, gateway route hoặc request headers. Phải biết nguồn nào là authority.

Một configuration có thể khai:

~~~yaml
soap:
  public-base-url: https://api.example.test
  orders-path: /soap/orders
  wsdl-path: /contracts/orders.wsdl
~~~

Đây là cấu trúc minh họa, không phải Spring-WS property mặc định. Ứng dụng cần binding/validation riêng.

### 20.1. Fail fast khi cấu hình sai

Validate public base URL ở startup/deployment:
- Scheme thuộc allowlist (https ở production theo policy).
- Host không phải localhost/private service hostname.
- Path prefix đúng environment.
- Không có userinfo/credentials trong URL.
- WSDL/endpoint paths tuyệt đối hoặc ghép path có quy tắc rõ.

### 20.2. Config không đồng nghĩa deployed behavior

Config value đúng nhưng proxy rewrite sai thì public WSDL vẫn sai. Ngược lại config nội bộ là HTTP nhưng public gateway HTTPS có thể hợp lệ nếu address generation biết trusted external scheme. Kiểm qua đường public.

### 20.3. Không hard-code production URL trong generated WSDL fixture test

Dùng expected URL riêng theo environment hoặc kiểm invariant host/path. Tránh cùng một test chỉ pass trên máy dev.

## 21. Troubleshooting theo symptom

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm |
|---|---|---|
| WSDL 404 | Servlet mapping/context path sai | GET đúng public path |
| WSDL 200 nhưng HTML | Gateway login/fallback page | Content-Type và root QName |
| soap:address là localhost | Proxy/external base URL sai | Parse port address |
| Address dùng HTTP | TLS termination/forwarded scheme không được nhận | Trusted proxy config |
| Missing context prefix | Ingress rewrite/forwarded prefix | Compare public path |
| XSD import 404 | Relative path/base URI sai hoặc resource thiếu | Resolve nested URL |
| XSD import 200 nhưng compile fail | Namespace/type/dependency mismatch | Schema processor |
| Browser mở WSDL nhưng codegen fail | Redirect/auth/relative imports/parser behavior | Dùng client/toolchain thật |
| Internal host leaked | WSDL generated từ upstream request | Public base URL strategy |
| SOAP POST 404 | soap:address path không route | Gọi endpoint từ WSDL |
| SOAP POST 415 | SOAP version/content type mismatch | Binding và message factory |
| TLS handshake fail | SAN/chain/protocol/mTLS | TLS diagnostics |
| Public WSDL OK, internal SOAP OK, public SOAP fail | Gateway auth/routing/header stripping | End-to-end public test |

## 22. Runbook chẩn đoán theo tầng

Khi deployment smoke test thất bại, đi theo thứ tự:

1. Resolve DNS của WSDL host.
2. Mở TCP/TLS tới host:port.
3. Verify certificate chain, SAN và TLS protocol.
4. GET WSDL bằng client tương đương consumer.
5. Kiểm redirects, status, content type và root QName.
6. Parse services/ports/bindings/soap:address.
7. Resolve từng import/include theo base URI và redirects.
8. Compile toàn bộ schema closure.
9. Kiểm URL address theo environment allowlist.
10. POST safe SOAP request tới address trích từ WSDL.
11. Kiểm HTTP status/content type/SOAP Fault.
12. Kiểm security policy và response QName.
13. So với contract version/checksum đã release.

Tách DNS/TLS/HTTP/XML/WSDL/XSD/SOAP/security/application errors thay vì chỉ ghi "integration failed".

## 23. Checklist triển khai

- WSDL retrieval URL public đúng và trả XML WSDL.
- WSDL root QName/namespace hợp lệ.
- Service/port/binding đúng SOAP version.
- soap:address/soap12:address dùng HTTPS và public hostname theo policy.
- Address path chứa đúng context path/proxy prefix.
- Không lộ localhost, private IP, internal DNS hay container port.
- Mọi wsdl:import và XSD import/include/redefine resolve được.
- Relative location resolve theo đúng document base URI.
- Nested dependencies được tải đệ quy và compile.
- Content-Type/root QName/schema namespaces đúng, không chỉ HTTP 200.
- Catalog/offline builds không che lỗi public publication.
- Trusted forwarded headers được proxy overwrite/strip đúng.
- WSDL không bị host injection qua untrusted Host/X-Forwarded headers.
- DNS/TLS/SAN/chain/mTLS được kiểm theo policy.
- SOAP smoke test gọi address trích từ WSDL qua public route.
- SOAP version, Action, security policy và response QName đúng.
- Endpoint test dùng safe/read-only operation hoặc isolated data.
- URL/schema checker có allowlist, redirect/size/time limits và SSRF protection.
- Deployment logs có contract version, deployment ID và failed dependency URI.
- Có rollback/mitigation nếu contract publication hoặc address sai.

## 24. Bài thực hành: xác minh Orders SOAP sau deployment

Bối cảnh: Spring-WS publish Orders WSDL dưới path /contracts/orders.wsdl; gateway public có prefix /integration; SOAP endpoint nằm dưới /soap/orders. WSDL import orders.xsd, schema này import common.xsd. Production dùng HTTPS, mTLS cho SOAP POST và không cho consumer truy cập private service DNS.

### Nhiệm vụ

1. Xác định WSDL retrieval URL public.
2. Xác định SOAP 1.1 và/hoặc SOAP 1.2 ports.
3. Parse soap:address từ đúng port/binding.
4. Xác minh address scheme, host, port và prefix /integration.
5. Tạo test fixture cho WSDL có address localhost và bảo đảm checker reject.
6. Tạo fixture có internal service hostname và private IP, checker reject.
7. Tải orders.xsd theo relative import từ WSDL.
8. Resolve common.xsd theo base URI của orders.xsd.
9. Test một dependency nested bị 404.
10. Test HTTP 200 trả HTML thay schema.
11. Test import namespace mismatch.
12. Compile schema dependency closure.
13. Kiểm proxy strip/overwrite X-Forwarded headers.
14. Test untrusted forwarded host không thay address public.
15. Kiểm DNS/TLS certificate SAN/chain ở staging.
16. GET WSDL và toàn bộ imports qua public gateway.
17. Lấy SOAP endpoint từ WSDL, gửi read-only GetOrder synthetic request.
18. Xác minh mTLS/WS-Security theo policy.
19. Ghi contract release checksum và deployment ID.
20. Thêm smoke checks vào release pipeline và xác định rollback criteria.

**Tiêu chí đạt:** Consumer bên ngoài tải được contract; mọi schema dependency resolve/compile; service address là public URL đúng environment; một SOAP request an toàn đi qua public route và nhận response đúng contract.

### 24.1. Tình huống tự kiểm

**A:** WSDL GET trả 200 nhưng soap:address là http://orders-service:8080/soap/orders. Tại sao chưa thể gọi deployment thành công? Những config/proxy facts nào cần xác minh?

**B:** Root WSDL tải được, nhưng orders.xsd import common.xsd bằng relative URI. Vì sao phải resolve từ URL của orders.xsd thay vì root WSDL?

**C:** WSDL GET qua browser hoạt động nhưng JAXB code generator lỗi khi tải import. Những khác biệt nào về redirect, authentication, relative URI, content type và parser cần kiểm?

**D:** Local service endpoint trả SOAP 200 nhưng public gateway trả 404. Hãy lần theo DNS/TLS/ingress prefix/servlet mapping và xác định smoke test nào phát hiện lỗi.

## 25. Ghi nhớ

- **WSDL retrieval URL khác SOAP endpoint URL.** Consumer GET contract nhưng POST tới address trong port.
- **WSDL có thể chứa nhiều services/ports/bindings.** Chọn đúng SOAP version và address.
- **soap:address phải là địa chỉ consumer truy cập được**, không phải container hostname/localhost.
- **Reverse proxy và TLS termination** có thể làm sai scheme, host, port hoặc context prefix nếu external URL generation không đúng.
- **WSDL/XSD dependency closure phải được resolve đệ quy.** HTTP 200 từng file chưa chứng minh schema graph compile được.
- **Relative imports resolve dựa base URI của document chứa reference.**
- **XML Catalog/offline builds hỗ trợ reproducibility nhưng không thay public publication smoke tests.**
- **WSDL/URL checker cần bảo vệ SSRF, redirects, XML parser và resource limits.**
- **Kiểm bằng SOAP POST tới address trích từ WSDL qua public route** mới chứng minh đường consumer thực sự hoạt động.
- **Tách DNS/TLS/HTTP/XML/WSDL/XSD/SOAP/security diagnostics** để tìm đúng tầng lỗi.

**Câu hỏi tự kiểm tra:** Sau deployment, WSDL public tải được nhưng khai báo SOAP address là hostname nội bộ và XSD import thứ hai bị 404. Hãy giải thích khác biệt WSDL URL và SOAP endpoint, resolve chuỗi relative imports, phân tích tác động reverse proxy/forwarded headers, đề xuất dependency-closure checker an toàn và mô tả smoke test cuối cùng phải gọi endpoint nào, bằng binding/security profile nào.

## 26. Tài liệu tham khảo để đối chiếu

- Spring Web Services Reference: WSDL publication, DefaultWsdl11Definition, MessageDispatcherServlet và endpoint configuration.
- WSDL 1.1 specification: definitions, types, import, service, port, binding và SOAP address.
- W3C XML Schema: import/include/redefine, targetNamespace và schema composition.
- RFC 3986: URI reference resolution và base URI.
- RFC 7239 và HTTP forwarding header guidance: proxy metadata và trust boundaries.
- OASIS XML Catalogs: URI resolution và offline schema mapping.
- W3C SOAP 1.1/1.2 specifications: bindings, envelope và fault handling.
- Spring Boot/Spring Framework deployment documentation: context path, servlet mapping, forwarded headers và proxy configuration.
- Organization gateway/ingress standards: public hostnames, TLS, mTLS, route prefixes và partner access.

Default WSDL publication behavior, forwarded-header support và property names có thể khác theo Spring-WS/Spring Boot/container versions. Pin dependencies và xác minh URL/dependency closure trên deployment stack thật; không suy public behavior chỉ từ embedded localhost test.

