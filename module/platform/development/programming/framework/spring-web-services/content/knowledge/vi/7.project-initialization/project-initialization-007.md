# Tách cấu hình theo môi trường và quản lý URL dịch vụ

## 1. Vấn đề khi khởi tạo dự án SOAP ở nhiều môi trường

Một dịch vụ **Spring Web Services (Spring-WS)** theo hướng **contract-first** có thể hoạt động trong máy phát triển (*local*), môi trường tích hợp (*development*), kiểm thử nghiệm thu (*staging/UAT*) và sản xuất (*production*). Cấu trúc thông điệp XML, namespace nghiệp vụ, SOAP operation và các ràng buộc XSD/WSDL thường phải giữ ổn định theo phiên bản hợp đồng. Tuy nhiên, nhiều thông tin vận hành lại thay đổi theo môi trường: cổng HTTP, địa chỉ hệ thống đối tác, URL công bố dịch vụ, chứng chỉ TLS, timeout và chính sách bảo mật.

Nếu ghi cứng những giá trị đó trong mã Java, rất dễ xảy ra tình trạng:

- Bản build dành cho production vô tình gọi URL của staging.
- Client lấy WSDL rồi cố kết nối tới `localhost` hoặc một hostname nội bộ.
- Reverse proxy phục vụ HTTPS nhưng WSDL quảng bá `http://`.
- Chuyển môi trường làm thay đổi `targetNamespace` hoặc `SOAPAction`, phá vỡ client đã sinh từ hợp đồng.
- Một mật khẩu keystore hoặc token xuất hiện trong repository, file cấu hình mẫu hoặc log.
- Môi trường production chạy được ứng dụng nhưng thất bại khi handshake TLS hoặc truy cập endpoint của đối tác.

Mục tiêu của bài là xây dựng **một ứng dụng Spring-WS, một hợp đồng SOAP có kiểm soát và cách cấu hình riêng cho từng môi trường**. Ví dụ xuyên suốt gồm:

- **Dịch vụ cung cấp (SOAP provider):** `OrdersService`, xử lý `GetOrderRequest` và trả `GetOrderResponse`.
- **Dịch vụ được gọi (SOAP consumer/client):** `PartnerOrdersClient` gọi hệ thống đối tác.
- **Hợp đồng nghiệp vụ:** namespace `https://example.org/orders/v1`, operation `GetOrder`, action `urn:example:orders:GetOrder`.
- **Endpoint công bố ra ngoài:** khác nhau giữa local, staging và production, tùy cấu hình hạ tầng.

Các địa chỉ `example.org` dưới đây chỉ mang tính minh họa và **không phải endpoint có thể gọi thật**.

### Kết quả cần đạt

Sau bài học, bạn cần có khả năng:

1. Phân biệt các URL liên quan tới SOAP: endpoint client gọi, SOAP endpoint của server, URL tải WSDL, địa chỉ trong `soap:address`, URL XSD import và URI của namespace/SOAPAction.
2. Dùng **Spring Boot externalized configuration** và **Spring profiles** để tách phần chung với thông số local, staging, production.
3. Bind và kiểm tra cấu hình bằng `@ConfigurationProperties` thay cho rải chuỗi URL trong endpoint/client.
4. Cấu hình `WebServiceTemplate`, `MessageDispatcherServlet` và công bố WSDL đúng chính sách.
5. Xử lý reverse proxy, TLS, WS-Security, chứng chỉ, timeout, logging và các lỗi thường gặp khi đổi môi trường.
6. Thiết kế kiểm thử để phát hiện sai URL và sai hợp đồng trước khi phát hành.

## 2. Phân biệt những «URL» dễ bị nhầm trong dự án Spring-WS

Từ «URL dịch vụ» thường bị dùng cho nhiều thứ khác nhau. Trước khi cấu hình phải xác định rõ **vai trò và nguồn chuẩn của từng giá trị**.

| Giá trị | Ví dụ | Dùng để làm gì? | Có thường đổi theo môi trường? |
|---|---|---|---|
| **Client target URL** | `https://partner-stg.example.org/soap/orders` | `WebServiceTemplate` gửi SOAP POST tới hệ thống đối tác | Có |
| **Public SOAP endpoint** | `https://soap.example.org/ws` | Hệ thống bên ngoài gửi SOAP POST tới dịch vụ của ta | Có thể |
| **WSDL document URL** | `https://soap.example.org/ws/orders.wsdl` | Client tải metadata WSDL bằng HTTP GET | Có thể |
| **WSDL `soap:address location`** | `https://soap.example.org/ws` | Địa chỉ được hợp đồng quảng bá cho một `port` | Phụ thuộc chính sách công bố |
| **XSD import URL** | `https://soap.example.org/ws/orders.xsd` | Công cụ client lấy schema tham chiếu từ WSDL/XSD | Phụ thuộc cách đóng gói/công bố |
| **Namespace URI** | `https://example.org/orders/v1` | Xác định QName của XML element/type, WSDL definitions | Thường **không đổi theo môi trường** |
| **SOAPAction / action URI** | `urn:example:orders:GetOrder` | Định danh ý định SOAP request theo binding | Không tự đổi theo môi trường |
| **WS-Addressing `wsa:To`** | `https://soap.example.org/ws` | Địa chỉ đích logic trong SOAP Header khi dùng WS-Addressing | Có thể, theo routing/policy |

**Cốt lõi:** `https://example.org/orders/v1` là một **XML namespace URI**, không phải URL để `WebServiceTemplate` gọi. Tương tự, `urn:example:orders:GetOrder` là **action** của operation, không phải endpoint HTTP. Đừng thay namespace hoặc SOAPAction khi chuyển staging sang production chỉ để «đồng bộ» với domain.

### Một yêu cầu, hai phía URL khác nhau

```mermaid
flowchart LR
  subgraph Inbound["SOAP provider của chúng ta"]
    Ext["Client doanh nghiệp"] -->|"POST https://soap.example.org/ws"| RP["Reverse proxy"]
    RP -->|"HTTP nội bộ /ws"| APP["Spring-WS MessageDispatcherServlet"]
    APP --> EP["@Endpoint: GetOrder"]
    Ext -.->|"GET /ws/orders.wsdl"| RP
  end
  subgraph Outbound["SOAP client của chúng ta"]
    APP --> C["WebServiceTemplate"]
    C -->|"POST partner URL cấu hình riêng"| PARTNER["Đối tác SOAP"]
  end
```

Có thể một ứng dụng chỉ làm provider hoặc chỉ làm consumer. Bài này đưa cả hai vai trò vào ví dụ để làm rõ **URL inbound công bố** và **URL outbound của client không phải cùng một cấu hình**.

## 3. Quy tắc chia cấu hình: hợp đồng ổn định, hạ tầng thay đổi

### 3.1. Những thành phần nên bất biến theo một phiên bản hợp đồng

Với một bản WSDL/XSD đã được phê duyệt, cần kiểm soát:

- `targetNamespace`, QName của request/response/fault và thứ tự cấu trúc XML.
- Operation name, `wsdl:message`, SOAP binding, phiên bản SOAP, SOAPAction được công bố.
- Ràng buộc XSD như `minOccurs`, `nillable`, enum và định dạng mã nghiệp vụ.
- Chính sách bảo mật/WS-Security là một phần của hợp đồng tích hợp, nếu có.

Thay đổi các thành phần trên thường phải trải qua review hợp đồng và kiểm thử tương thích. **Profile** không phải cơ chế để tạo nhiều định nghĩa operation khác nhau dưới cùng một version mà các consumer không biết.

### 3.2. Những thành phần thường là cấu hình môi trường

| Nhóm | Ví dụ nên externalize |
|---|---|
| HTTP runtime | `server.port`, context path, TLS termination, forwarding |
| Outbound client | URL của partner, connect/read timeout, network proxy |
| Inbound publication | Có cho phép rewrite `soap:address` theo request/proxy hay không |
| Security deployment | Truststore, keystore, alias, đường dẫn chứng chỉ, secret từ hệ quản lý bí mật |
| Diagnostics | Log level, correlation ID, telemetry endpoint, mức che nội dung nhạy cảm |
| Feature tích hợp | Mở/tắt stub local, lựa chọn endpoint mock được kiểm soát |

Lưu ý: `soap:address` **đôi khi** được phép khác nhau theo môi trường, nhưng cũng có các hợp đồng yêu cầu địa chỉ trong WSDL được giữ nguyên. Điều này phải được quyết định bởi chính sách hợp đồng; không tự ý biến đổi WSDL đã ký duyệt.

### 3.3. Nguồn cấu hình và thứ tự ưu tiên

Spring Boot hỗ trợ nhiều nguồn cấu hình bên ngoài như `application.yml`, các file `application-<profile>.yml`, biến môi trường, system properties và command-line arguments. Các nguồn có độ ưu tiên theo quy tắc **externalized configuration** của Spring Boot; giá trị có độ ưu tiên cao hơn có thể ghi đè giá trị thấp hơn.

Thực hành phù hợp là:

1. File chung giữ **cấu trúc cấu hình, default không nhạy cảm và tên property**.
2. Profile local chứa địa chỉ mock/service chạy trên máy phát triển.
3. Staging và production lấy endpoint được cấp từ môi trường triển khai hoặc hệ quản lý cấu hình; không cần rebuild JAR.
4. Secret và password đến từ secret manager/Kubernetes Secret/vault hoặc cơ chế quản lý bí mật tương đương.
5. Cấu hình bắt buộc phải được kiểm tra **ngay khi khởi động**, tránh để lỗi chỉ xuất hiện ở lần gọi SOAP đầu tiên.

Không sử dụng nhiều profile chồng nhau một cách ngẫu nhiên. Nếu đồng thời kích hoạt `local,prod`, một giá trị có thể bị override theo thứ tự khiến hệ thống gọi sai đích. Mỗi bản triển khai cần quy định một **tập profile hợp lệ** và phát hiện profile xung đột trong pipeline hoặc bootstrap nếu cần.

## 4. Gợi ý cấu trúc dự án Spring-WS

Một cấu trúc khởi đầu gọn cho ví dụ:

```text
orders-soap/
  pom.xml                         (hoặc build.gradle)
  src/
    main/
      java/org/example/orders/
        OrdersSoapApplication.java
        config/
          SoapProperties.java
          SoapServerConfig.java
          SoapClientConfig.java
        endpoint/
          OrdersEndpoint.java
        client/
          PartnerOrdersClient.java
        service/
          OrdersService.java
        contract/
          ...                    (JAXB được sinh từ XSD)
      resources/
        application.yml
        application-local.yml
        application-staging.yml
        application-prod.yml
        wsdl/
          orders.wsdl
        xsd/
          orders.xsd
    test/
      java/
        ...                      (test cấu hình và contract)
```

Đây là **sơ đồ minh họa**, không yêu cầu tạo các file phụ trong bài học. Phần `contract/` có thể nằm dưới thư mục build sinh mã, phụ thuộc plugin JAXB/XJC. Tránh chỉnh trực tiếp class JAXB được sinh: khi cần đổi wire format, sửa XSD/hợp đồng theo quy trình kiểm soát thay đổi rồi sinh lại.

Với Spring Boot 3.x và Spring-WS 4.x, nhóm dependency thường cần gồm **Spring Web Services starter**, JAXB runtime/tooling tương thích với `jakarta.xml.bind`, **validation starter** nếu dùng `jakarta.validation`, cùng test starter/Spring-WS test. Không trộn thư viện `javax.xml.bind` của stack cũ với `jakarta.xml.bind` của stack mới. Phiên bản cụ thể cần khớp Spring Boot BOM và yêu cầu dự án; không đặt version ngẫu nhiên cho từng dependency.

## 5. Tách cấu hình bằng `application.yml` và profile

Ví dụ bên dưới minh họa **một cấu trúc thuộc tính duy nhất** để cả provider và client đọc nhất quán:

- `app.soap.publisher.transform-wsdl-locations` điều khiển có thay `soap:address` theo request khi công bố WSDL hay không.
- `app.soap.partner.endpoint` là HTTP URL **outbound** mà SOAP client gọi.
- `app.soap.partner.connect-timeout` và `read-timeout` là thời gian chờ của HTTP transport.

### 5.1. File chung: `application.yml`

```yaml
spring:
  application:
    name: orders-soap

server:
  port: ${SERVER_PORT:8080}

app:
  soap:
    publisher:
      transform-wsdl-locations: false
    partner:
      endpoint: ${PARTNER_SOAP_URL}
      connect-timeout: ${PARTNER_CONNECT_TIMEOUT:3s}
      read-timeout: ${PARTNER_READ_TIMEOUT:10s}
```

Trong cấu hình này, `${PARTNER_SOAP_URL}` là **placeholder bắt buộc** khi không có profile nào override property. Nếu thiếu giá trị, ứng dụng cần báo lỗi cấu hình lúc bind khởi động. Điều đó giúp phát hiện deployment chưa được cấp endpoint, tránh âm thầm fallback sang staging.

Không đặt `PARTNER_SOAP_URL` mặc định là một URL production hoặc staging cố định trong file chung: thiếu cấu hình phải được nhìn thấy rõ thay vì dẫn request đến môi trường ngoài dự kiến.

### 5.2. Profile phát triển: `application-local.yml`

```yaml
app:
  soap:
    partner:
      endpoint: http://localhost:9090/ws
      connect-timeout: 1s
      read-timeout: 3s
    publisher:
      transform-wsdl-locations: false

logging:
  level:
    org.springframework.ws: DEBUG
```

Local sử dụng một SOAP stub/test server ở cổng 9090. Đây là endpoint **minh họa**, cần khởi chạy hoặc thay thế bằng mock thực trong bài thực hành. DEBUG phù hợp lúc phát triển, nhưng không nên tự động bật logging toàn bộ nội dung SOAP chứa dữ liệu thật hoặc header WS-Security.

### 5.3. Profile tích hợp: `application-staging.yml`

```yaml
app:
  soap:
    publisher:
      transform-wsdl-locations: true

server:
  forward-headers-strategy: framework
```

Ở ví dụ này, staging **cho phép** rewrite địa chỉ trong WSDL và hạ tầng staging có reverse proxy đáng tin. Outbound `app.soap.partner.endpoint` vẫn lấy từ biến `PARTNER_SOAP_URL` của deployment. Phần `forward-headers-strategy` chỉ phù hợp nếu proxy đã kiểm soát, thay thế/xóa header do client ngoài gửi và cung cấp `Forwarded` hoặc `X-Forwarded-*` đúng. Nếu hệ thống không có proxy đáng tin, không nên bật xử lý forwarded headers chỉ để «sửa» URL.

### 5.4. Profile sản xuất: `application-prod.yml`

```yaml
app:
  soap:
    publisher:
      transform-wsdl-locations: false

logging:
  level:
    org.springframework.ws: INFO
```

Ở ví dụ này, production dùng **WSDL có địa chỉ công khai được phê duyệt**, nên không rewrite. Nếu kiến trúc production yêu cầu rewrite, phải thay chính sách theo hợp đồng và kiểm thử qua URL công khai trước khi phát hành. `PARTNER_SOAP_URL` trong production được cấp qua deployment environment/secret store; không commit chuỗi chứa credential vào source.

### 5.5. Bảng giá trị thực tế giữa các môi trường

| Thuộc tính | Local | Staging | Production |
|---|---|---|---|
| `SPRING_PROFILES_ACTIVE` | `local` | `staging` | `prod` |
| `server.port` | `8080` | Port container nội bộ | Port container nội bộ |
| `PARTNER_SOAP_URL` | Local mock `http://localhost:9090/ws` | URL đối tác staging được cấp | URL đối tác production được cấp |
| `transform-wsdl-locations` | `false` | `true` nếu contract cho phép | `false` theo ví dụ hợp đồng cố định |
| Xác thực/TLS | Có thể dùng mock/stub an toàn | Cert/CA staging | Cert/CA production |
| Log payload | Chỉ bật cục bộ khi dữ liệu giả và đã che | Hạn chế | Hạn chế nghiêm ngặt |

Chú ý: `localhost` **bên trong container** là chính container đó, không phải máy host hoặc container đối tác. Khi chạy Docker Compose/Kubernetes, cần dùng tên service, DNS hoặc endpoint được hạ tầng cấp, thay vì sao chép URL local vào deployment.

## 6. Bind cấu hình theo kiểu dữ liệu và kiểm tra lúc khởi động

Đọc chuỗi rải rác bằng `@Value("${...}")` có thể hoạt động với vài property, nhưng dự án có nhiều URL và timeout sẽ khó kiểm tra tính nhất quán. Spring Boot hỗ trợ `@ConfigurationProperties` để bind các thuộc tính liên quan vào một object có kiểu rõ ràng.

### 6.1. Định nghĩa `SoapProperties`

Ví dụ dùng Java record, Spring Boot 3.x và Bean Validation:

```java
package org.example.orders.config;

import java.time.Duration;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.soap")
public record SoapProperties(
        @Valid @NotNull Publisher publisher,
        @Valid @NotNull Partner partner) {

    public record Publisher(
            boolean transformWsdlLocations) {
    }

    public record Partner(
            @NotBlank String endpoint,
            @NotNull Duration connectTimeout,
            @NotNull Duration readTimeout) {
    }
}
```

Kích hoạt binding bằng một trong các cơ chế được Spring Boot hỗ trợ, ví dụ:

```java
package org.example.orders;

import org.example.orders.config.SoapProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(SoapProperties.class)
public class OrdersSoapApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersSoapApplication.class, args);
    }
}
```

Không cần đồng thời bật cả `@ConfigurationPropertiesScan` và `@EnableConfigurationProperties` cho cùng record. Binding dùng **relaxed property naming**, nên YAML `transform-wsdl-locations` được ánh xạ sang field Java `transformWsdlLocations`.

**Điều kiện để validation hoạt động:** cần có Bean Validation provider tương thích (ví dụ dependency `spring-boot-starter-validation` trong Boot 3). `@NotBlank`/`@NotNull` phát hiện thiếu giá trị, nhưng **chưa chứng minh endpoint URL hợp lệ**. Cần kiểm tra thêm scheme, host, userinfo và quy tắc bảo mật.

### 6.2. Kiểm tra URL và timeout trước khi tạo client

Ví dụ một helper chỉ chấp nhận endpoint HTTP(S) có host:

```java
import java.net.URI;
import java.time.Duration;
import java.util.Locale;
import java.util.Set;

public final class EndpointChecks {
    private EndpointChecks() {}

    public static URI parseHttpEndpoint(String raw) {
        URI uri = URI.create(raw);
        String scheme = uri.getScheme();
        if (scheme == null
                || !Set.of("http", "https")
                       .contains(scheme.toLowerCase(Locale.ROOT))
                || uri.getHost() == null
                || uri.getUserInfo() != null
                || uri.getFragment() != null) {
            throw new IllegalArgumentException(
                "SOAP endpoint must be an HTTP(S) URL with a host");
        }
        return uri;
    }

    public static Duration positive(Duration value, String propertyName) {
        if (value == null || value.isZero() || value.isNegative()) {
            throw new IllegalArgumentException(
                propertyName + " must be positive");
        }
        return value;
    }
}
```

Có thể gọi helper trong constructor hoặc bean factory của client để **fail fast**. Trong production, thường còn cần ràng buộc `https` bắt buộc, hostname/domain nằm trong danh sách được phép và chứng chỉ tin cậy. Các quyết định này thuộc chính sách triển khai; không nên cấm `http://localhost` cho stub local nếu môi trường local đã được xác định là không chứa dữ liệu thật.

**Không đặt username/password trong URL** như `https://user:password@host/ws`. URI parser có thể chấp nhận userinfo, nhưng thông tin đó dễ bị lộ qua exception, monitoring và log, đồng thời không thay thế cấu hình xác thực SOAP/TLS đúng cách.

## 7. Cấu hình SOAP client outbound bằng `WebServiceTemplate`

Đối tượng **`WebServiceTemplate`** thường được dùng để marshal request JAXB, gửi SOAP request qua HTTP và unmarshal response. Điểm quan trọng trong quản lý môi trường là **địa chỉ gọi phải đến từ cấu hình**, không nằm cứng trong service code.

### 7.1. Cấu hình marshaller và template

Giả định JAXB classes đã sinh từ XSD hợp đồng nằm trong package `org.example.orders.contract`:

```java
package org.example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;

@Configuration
public class SoapClientConfig {

    @Bean
    public Jaxb2Marshaller partnerMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("org.example.orders.contract");
        return marshaller;
    }

    @Bean
    public WebServiceTemplate partnerWebServiceTemplate(
            Jaxb2Marshaller partnerMarshaller) {
        WebServiceTemplate template = new WebServiceTemplate();
        template.setMarshaller(partnerMarshaller);
        template.setUnmarshaller(partnerMarshaller);
        return template;
    }
}
```

Đây là cấu hình tối thiểu minh họa **XML mapping**. Để timeout `connectTimeout`/`readTimeout` thực sự có hiệu lực, cần cấu hình **HTTP message sender** của `WebServiceTemplate` theo API và phiên bản Spring-WS/HTTP client đang dùng. Việc chỉ khai báo hai timeout trong YAML **chưa tự động tác động** lên transport SOAP. Tương tự, TLS truststore, mTLS, HTTP proxy và authentication phải được cấu hình ở tầng transport phù hợp.

Nếu dự án có nhiều SOAP partners, nên đặt tên riêng từng `WebServiceTemplate` hoặc dùng `@Qualifier` để tránh inject nhầm template.

### 7.2. Dùng URL từ properties tại thời điểm gọi

```java
package org.example.orders.client;

import org.example.orders.config.SoapProperties;
import org.example.orders.config.EndpointChecks;
import org.springframework.stereotype.Service;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.client.core.SoapActionCallback;
import org.example.orders.contract.GetOrderRequest;
import org.example.orders.contract.GetOrderResponse;

@Service
public class PartnerOrdersClient {
    private static final String ACTION =
        "urn:example:orders:GetOrder";

    private final WebServiceTemplate template;
    private final String endpoint;

    public PartnerOrdersClient(
            WebServiceTemplate partnerWebServiceTemplate,
            SoapProperties properties) {
        this.template = partnerWebServiceTemplate;
        this.endpoint = EndpointChecks
            .parseHttpEndpoint(properties.partner().endpoint())
            .toString();

        EndpointChecks.positive(
            properties.partner().connectTimeout(), "connectTimeout");
        EndpointChecks.positive(
            properties.partner().readTimeout(), "readTimeout");
    }

    public GetOrderResponse getOrder(String orderId) {
        GetOrderRequest request = new GetOrderRequest();
        request.setOrderId(orderId);

        Object result = template.marshalSendAndReceive(
            endpoint,
            request,
            new SoapActionCallback(ACTION));

        return (GetOrderResponse) result;
    }
}
```

Đoạn này giả định generator tạo JAXB root classes có thể marshal và unmarshal trực tiếp, đồng thời project đã có marshaller mapping thích hợp. Nếu root được tạo qua `JAXBElement`/`ObjectFactory`, phải bọc request và giải bọc response theo generated model; tránh ép kiểu trực tiếp như ví dụ khi không phù hợp.

Phần **`ACTION`** đến từ WSDL binding nên được quản lý cùng hợp đồng, không gắn vào URL môi trường. Đối với SOAP 1.1, `SoapActionCallback` đặt SOAPAction phù hợp; với SOAP 1.2, message factory/binding và cơ chế action phải được kiểm chứng riêng bằng HTTP capture. Callback không tự chuyển SOAP version.

**Điểm thiếu có chủ đích của ví dụ tối thiểu:** helper kiểm tra timeout, nhưng template chưa cài HTTP sender để áp dụng timeout. Đây là một việc triển khai bắt buộc trước khi dùng production. Không đánh dấu hoàn thành chỉ vì properties được bind đúng và helper đã chạy.

### 7.3. Có thể cấu hình default URI của template không?

Có. Ví dụ:

```java
template.setDefaultUri(properties.partner().endpoint());
```

Khi đó client có thể dùng overload `marshalSendAndReceive(request, callback)` không truyền URI mỗi lần. Chọn một trong hai cách tùy mô hình:

- **Đối tác cố định cho một client:** cấu hình `defaultUri` từ properties và gọi qua template.
- **Đối tác/môi trường được chọn theo nghiệp vụ:** truyền URI cho từng lần gọi, nhưng phải lấy từ **danh sách endpoint được phép**, không nhận URL tùy ý từ người dùng cuối để tránh server-side request forgery (SSRF).

Thay URL đích không đòi sửa JAXB class nếu XSD/WSDL contract giữ nguyên. Tuy nhiên, URL mới có thể dùng chính sách TLS, certificate, WS-Security hoặc SOAP binding khác, nên vẫn cần kiểm thử trên môi trường đích.

## 8. Cấu hình SOAP provider và URL WSDL được công bố

Khi đóng vai trò provider, Spring-WS thường có `MessageDispatcherServlet` tiếp nhận SOAP POST và phục vụ metadata WSDL/XSD. Hai URL phải được phân biệt:

- **WSDL URL:** trình duyệt/client dùng HTTP GET, ví dụ `/ws/orders.wsdl`.
- **SOAP endpoint:** client gửi SOAP POST, ví dụ `/ws` nếu WSDL có `soap:address location="/ws"` hoặc địa chỉ public tương ứng.

### 8.1. Công bố WSDL tĩnh đã phê duyệt

Nếu đối tác yêu cầu đúng bản `orders.wsdl` đã được phê duyệt, dùng `SimpleWsdl11Definition`:

```java
package org.example.orders.config;

import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.transport.http.MessageDispatcherServlet;
import org.springframework.ws.wsdl.wsdl11.SimpleWsdl11Definition;

@EnableWs
@Configuration
public class SoapServerConfig {

    @Bean
    public ServletRegistrationBean<MessageDispatcherServlet>
            messageDispatcherServlet(
                    ApplicationContext applicationContext,
                    SoapProperties properties) {
        MessageDispatcherServlet servlet =
            new MessageDispatcherServlet();
        servlet.setApplicationContext(applicationContext);
        servlet.setTransformWsdlLocations(
            properties.publisher().transformWsdlLocations());

        return new ServletRegistrationBean<>(servlet, "/ws/*");
    }

    @Bean(name = "orders")
    public SimpleWsdl11Definition ordersWsdl() {
        SimpleWsdl11Definition definition =
            new SimpleWsdl11Definition();
        definition.setWsdl(
            new ClassPathResource("wsdl/orders.wsdl"));
        return definition;
    }
}
```

Với cấu hình trên và context path mặc định:

- Bean `orders` thường được phục vụ ở `GET /ws/orders.wsdl`.
- SOAP POST thường đi qua mapping `/ws/*`, với URL thực phụ thuộc `soap:address`/reverse proxy.
- Khi `transformWsdlLocations=false`, địa chỉ trong static WSDL được giữ theo tài liệu nguồn.
- Khi `transformWsdlLocations=true`, Spring-WS có thể biến đổi location trong WSDL theo request hiện tại. Điều này chỉ nên bật khi hợp đồng cho phép, và phải kiểm tra URL thực trả về.

**Không kết luận** servlet mapping `/ws/*` tự quyết định chính xác tất cả các địa chỉ trong WSDL: file WSDL vẫn có thể công bố một `soap:address` độc lập. Nếu thử local bằng file WSDL production, client cần override endpoint URL hoặc dùng bản hợp đồng dành riêng cho môi trường theo quy trình phê duyệt.

### 8.2. Nếu WSDL sinh từ XSD

Khi hợp đồng được quản lý ở dạng XSD và nhóm cho phép Spring-WS sinh WSDL, có thể dùng `DefaultWsdl11Definition`:

```java
@Bean(name = "orders")
public DefaultWsdl11Definition ordersWsdl(XsdSchema ordersSchema) {
    DefaultWsdl11Definition definition =
        new DefaultWsdl11Definition();
    definition.setPortTypeName("OrdersPort");
    definition.setLocationUri("/ws");
    definition.setTargetNamespace("https://example.org/orders/v1");
    definition.setSchema(ordersSchema);
    return definition;
}
```

Đây là **lựa chọn thay thế** bean `SimpleWsdl11Definition` ở mục 8.1, không đăng ký cả hai bean cùng tên `orders`. Khi sinh WSDL, phải kiểm tra snapshot đã công bố, SOAPAction, request/response naming convention và tính tương thích. Đừng để tên Java method hoặc môi trường thay đổi hợp đồng ngoài dự kiến.

## 9. Reverse proxy, hostname công khai và `soap:address`

Trong production, SOAP provider thường nhận request qua load balancer hoặc API gateway:

```text
Client đối tác
  -> https://soap.example.org/ws/orders.wsdl
  -> HTTPS reverse proxy / gateway
  -> http://orders-service:8080/ws/orders.wsdl

Client đối tác
  -> https://soap.example.org/ws         (SOAP POST)
  -> HTTPS reverse proxy / gateway
  -> http://orders-service:8080/ws
```

Vấn đề xuất hiện khi ứng dụng xây `soap:address` dựa vào URL nội bộ `http://orders-service:8080/ws` thay vì URL bên ngoài. Client tải được WSDL nhưng code được sinh ra lại gọi hostname nội bộ không tồn tại trong mạng đối tác.

### 9.1. Hai chính sách quản lý address

**Chính sách A — địa chỉ cố định trong WSDL đã phê duyệt**

- File `orders.wsdl` chứa `soap:address location="https://soap.example.org/ws"`.
- Giữ `transformWsdlLocations=false`.
- Proxy route đến đúng endpoint nội bộ.
- Test xác nhận tài liệu GET được công bố vẫn có address chính xác như bản đã phê duyệt.

**Chính sách B — address thay đổi có kiểm soát theo môi trường**

- Hợp đồng cho phép thay hostname/scheme/port/path của `soap:address` mà vẫn giữ operation và XML contract.
- Bật `transformWsdlLocations=true` với `MessageDispatcherServlet`.
- Proxy gửi các forwarded headers được chuẩn hóa, ứng dụng xử lý chúng theo cấu hình phù hợp.
- Test từ mạng ngoài chứng minh WSDL quảng bá đúng URL public của **từng** môi trường.

Nếu file WSDL được xác thực bằng checksum hoặc ký số byte-for-byte, mọi rewrite sẽ thay đổi bytes; cần xác định chính sách chữ ký/phê duyệt và không âm thầm đổi nội dung. Ngay cả khi chỉ đổi `soap:address`, client có thể bị ảnh hưởng bởi TLS, firewall hoặc chính sách mạng.

### 9.2. Forwarded headers phải đến từ proxy đáng tin

Reverse proxy có thể gửi:

```http
X-Forwarded-Proto: https
X-Forwarded-Host: soap.example.org
X-Forwarded-Port: 443
```

hoặc HTTP `Forwarded` theo chuẩn tương ứng. Cấu hình Spring Boot có thể sử dụng:

```yaml
server:
  forward-headers-strategy: framework
```

Tuy nhiên, forwarded headers có thể bị **giả mạo** nếu proxy chuyển nguyên header do client bên ngoài tự đặt. Chỉ tin dữ liệu này khi:

1. Proxy/gateway thay thế hoặc xóa header không đáng tin trước khi chuyển tiếp.
2. Backend chỉ nhận request qua các điểm vào tin cậy.
3. Hostname, scheme và prefix công khai được kiểm tra trong staging/integration test.
4. Hệ thống tránh tạo WSDL quảng bá một host do người gửi HTTP tự quyết định.

Khi gateway thay đổi prefix (ví dụ public `/api/soap` thành internal `/ws`), cần kiểm tra cả path và context path. Việc bật `forward-headers-strategy` không bảo đảm mọi cấu hình path rewrite đều tự động khớp; hãy tải WSDL **qua URL public** và đối chiếu `soap:address`, không chỉ thử với localhost.

### 9.3. Trường hợp WSDL import XSD bên ngoài

Ví dụ:

```xml
<xs:import
    namespace="https://example.org/orders/v1"
    schemaLocation="orders.xsd"/>
```

Nếu WSDL được tải từ `https://soap.example.org/ws/orders.wsdl`, client thường giải quyết relative location thành `https://soap.example.org/ws/orders.xsd`. Vì vậy, service phải **công bố đúng schema URL** hoặc cung cấp catalog/gói offline; không thể giả định file `src/main/resources/xsd/orders.xsd` tự có thể tải qua mạng.

Spring-WS có thể phục vụ `XsdSchema` bean qua servlet và hỗ trợ biến đổi một số schema locations tùy cấu hình. Khi áp dụng, phải kiểm tra toàn bộ cây `xs:include`/`xs:import`, `wsdl:import` và cơ chế rewrite; tránh chỉ kiểm tra duy nhất file WSDL gốc.

## 10. TLS, WS-Security và chứng chỉ theo môi trường

Thông tin bảo mật thường có phần **ổn định theo hợp đồng** và phần **biến động theo môi trường**:

| Nội dung | Gần hợp đồng | Gần triển khai |
|---|---|---|
| Dịch vụ yêu cầu HTTPS/mTLS | Chính sách xác thực và bảo mật kết nối | Host, port, CA, client cert, truststore |
| WS-Security signing/encryption | Element phải ký/mã hóa, thuật toán/profile chấp nhận | Key alias, certificate chain, keystore, secrets |
| Timestamp/replay | Quy tắc chấp nhận, tolerance theo policy | Đồng bộ đồng hồ, retention/cache và giám sát |
| Authorization | Quy tắc quyền theo operation/role | Mapping client identity, quyền theo tenant/môi trường |
| Endpoint URL | Phân biệt port/service hợp đồng | DNS và route thực tế theo môi trường |

Không nên đưa password keystore, private key hoặc token thật vào `application-prod.yml`. Tên property có thể xuất hiện trong YAML, còn giá trị do môi trường triển khai cung cấp:

```yaml
app:
  soap:
    security:
      key-store-location: ${SOAP_KEYSTORE_LOCATION}
      key-store-password: ${SOAP_KEYSTORE_PASSWORD}
      trust-store-location: ${SOAP_TRUSTSTORE_LOCATION}
      trust-store-password: ${SOAP_TRUSTSTORE_PASSWORD}
```

Đây là **ví dụ một cấu trúc property bảo mật có thể bổ sung**; record `SoapProperties` ở mục 6 mới chỉ mô hình hóa `publisher` và `partner`. Muốn cấu hình này có hiệu lực, phải mở rộng cấu hình typed properties, wiring TLS transport/mTLS hoặc `Wss4jSecurityInterceptor` và test tương ứng. Việc đặt property trong YAML tự nó **không tự bật TLS client authentication hay WS-Security**.

Quy tắc vận hành:

- Staging và production dùng **chứng chỉ/khóa tách biệt**; chỉ trust CA được phê duyệt.
- Kiểm tra certificate expiry, hostname verification, certificate chain và quy trình luân chuyển khóa.
- Không tắt hostname verification hoặc certificate validation để «chữa» lỗi môi trường.
- Không log chuỗi chứa password, private key, token WS-Security hoặc nguyên văn SOAP Header nhạy cảm.
- Nếu URL chuyển từ `https://partner.example.org` sang hostname khác, phải kiểm tra lại chứng chỉ và trust policy dù XML contract không đổi.
- Mã xử lý SOAP Fault nên che thông tin nội bộ, nhưng vẫn có correlation ID đủ để truy vết.

## 11. Khởi động theo profile và kiểm tra thông số đã nạp

### 11.1. Chọn profile đúng môi trường

Trong shell POSIX, ví dụ local:

```bash
SPRING_PROFILES_ACTIVE=local ./mvnw spring-boot:run
```

Trong Windows PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = 'local'
.\mvnw.cmd spring-boot:run
```

Trong deployment staging:

```text
SPRING_PROFILES_ACTIVE=staging
PARTNER_SOAP_URL=https://partner-stg.example.org/soap/orders
```

Trong deployment production:

```text
SPRING_PROFILES_ACTIVE=prod
PARTNER_SOAP_URL=https://partner.example.org/soap/orders
```

Đây là **giá trị minh họa**, cần được cấp bằng manifest/deployment system thay vì copy thủ công vào source. Tránh đưa các credential production vào command line dễ xuất hiện trong shell history hoặc process list.

### 11.2. Kiểm tra giá trị hiệu lực thay vì đoán

Một file cấu hình tồn tại trong repository không chứng minh nó đã được nạp. Trước khi cho phép ứng dụng bắt đầu nhận traffic, cần xác nhận:

1. Active profile đúng (local/staging/prod) và không có tổ hợp profile xung đột.
2. Client endpoint URL có scheme, host, port và path mong đợi.
3. Timeout đã được bind **và thực sự gắn vào HTTP message sender**.
4. Cấu hình TLS/truststore/keystore và WS-Security được wiring, chứng chỉ hợp lệ.
5. `MessageDispatcherServlet` có mapping đúng, WSDL/XSD GET thành công và địa chỉ quảng bá đúng.
6. Không có cấu hình fallback làm production vô tình gọi mock/staging.

Khi ghi log xác nhận cấu hình, chỉ nên ghi tên profile, hostname đã được phê duyệt và kết quả kiểm tra. Không dump toàn bộ Spring `Environment`, query string có bí mật, passwords hoặc raw SOAP security headers. Nếu cần cung cấp health/readiness signal, giới hạn thông tin phù hợp với quyền của người xem.

## 12. Kiểm thử cấu hình và URL theo từng lớp

Quản lý cấu hình chỉ thực sự đáng tin khi có **kiểm thử ở cả mức binding properties và network integration**.

### 12.1. Test startup và profile resolution

| Ca kiểm thử | Cách thực hiện | Kỳ vọng |
|---|---|---|
| Profile local | Bật `local` với mock SOAP server | Endpoint trỏ tới mock, timeout ngắn |
| Profile staging | Bật `staging`, cấp `PARTNER_SOAP_URL` staging | Không dùng URL local/prod; config bind thành công |
| Profile prod thiếu URL | Bật `prod` nhưng không cấp `PARTNER_SOAP_URL` | **Fail fast**, không khởi động ở trạng thái sai |
| URL không hợp lệ | Cấp `ftp://...` hoặc URI thiếu host | Validation từ chối trước SOAP call |
| URL có userinfo | Cấp `https://user:pass@host/ws` | Validation từ chối |
| Timeout âm/0 | Cấp `PARTNER_READ_TIMEOUT=0s` | Validation từ chối |
| Trộn profile | Cấp `local,prod` | Pipeline/bootstrap phát hiện và chặn theo policy |

Ví dụ `@ConfigurationProperties` dễ kiểm thử bằng `ApplicationContextRunner` hoặc test khởi động Spring Boot với một tập property cụ thể. Khi test profile production, tránh tạo kết nối thật tới đối tác: test phân giải config là một bước, test tích hợp mạng là bước riêng có môi trường và quyền rõ ràng.

### 12.2. Test outbound SOAP client

Sử dụng `MockWebServiceServer` của Spring-WS cho phần logic SOAP client:

1. Mock request `GetOrderRequest` phải có đúng QName và namespace.
2. Kiểm tra `SOAPAction` theo WSDL khi SOAP 1.1 binding yêu cầu.
3. Trả response hợp lệ và xác nhận JAXB unmarshal đúng.
4. Trả SOAP Fault để xác nhận exception mapping.
5. Giả lập các lỗi kết nối/timeout trong lớp thích hợp để kiểm tra hành vi xử lý lỗi.

Mock HTTP/SOAP chỉ xác nhận ứng dụng phản ứng đúng khi giao thức được giả lập. Để kiểm tra **thật sự gọi đúng host, DNS, proxy, timeout và TLS**, cần một integration test trên mạng dành riêng cho môi trường.

### 12.3. Test inbound WSDL publication

Nếu local server chạy ở cổng 8080:

```bash
curl -i "http://localhost:8080/ws/orders.wsdl"
```

Trong staging:

```bash
curl -i "https://soap-stg.example.org/ws/orders.wsdl"
```

Đối chiếu:

- HTTP GET tải được WSDL 1.1 hợp lệ.
- `targetNamespace`, `wsdl:operation`, `soap:operation@soapAction` và SOAP binding khớp hợp đồng.
- `soap:address@location` quảng bá **đúng URL public** đã được phê duyệt cho môi trường.
- Mọi `xs:import` và `wsdl:import` có thể resolve với quyền của client.
- Khi dự án yêu cầu static WSDL giữ nguyên bytes, so sánh checksum hoặc snapshot theo quy tắc phê duyệt.

Nếu có thay đổi có chủ đích chỉ ở `soap:address` theo môi trường, CI phải diff có kiểm soát: **chỉ** những khác biệt đã cho phép được chấp nhận. Một thay đổi ngoài ý muốn ở operation, XSD QName hoặc SOAPAction phải khiến kiểm thử thất bại.

### 12.4. Test toàn đường đi qua reverse proxy

Một kiểm thử end-to-end cần đi đúng đường mà client thực dùng:

```mermaid
flowchart LR
  T["Test client ngoài mạng backend"] --> P["Public HTTPS + DNS"]
  P --> R["Gateway / reverse proxy"]
  R --> S["MessageDispatcherServlet"]
  S --> E["SOAP endpoint"]
  E --> V["Validation + service"]
  V --> E
  E --> T
```

Các điều kiện kiểm:

1. DNS resolution và TLS handshake thành công, hostname trên chứng chỉ khớp.
2. WSDL tải được từ URL public, `soap:address` không lộ IP/host nội bộ.
3. Request SOAP POST đi qua đúng proxy path, không lệch context path.
4. SOAPAction, content type, SOAP version và payload QName phù hợp WSDL.
5. Schema validation, SOAP Fault và WS-Security hoạt động khi dùng client độc lập.
6. Request lỗi xác thực, sai chữ ký hoặc sai XSD bị chặn mà không rò dữ liệu bí mật.

## 13. Ma trận lỗi thường gặp khi chuyển môi trường

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra và cách xử lý |
|---|---|---|
| Local chạy được, staging không kết nối được | `PARTNER_SOAP_URL` sai DNS/port/path, firewall chặn | Kiểm tra host, route, connectivity từ **mạng chạy ứng dụng** |
| Production gọi nhầm staging | Fallback URL hoặc profile bị override | In effective profile và URL đã mask, chặn prod->staging qua policy |
| WSDL trả về `http://orders-service:8080/ws` | Proxy headers/rewrite sai | Kiểm tra `soap:address` khi tải WSDL từ URL public |
| WSDL GET chạy nhưng SOAP POST lỗi 404 | URL document khác endpoint SOAP; gateway sai route | Đối chiếu `soap:address`, servlet mapping và proxy path |
| Client download WSDL được nhưng sinh mã thất bại | XSD import URL trả 404, schemaLocation sai | Truy cập các import và đóng gói schema/catalog phù hợp |
| TLS handshake failure | CA/chứng chỉ không tin cậy, cert hết hạn, mTLS chưa gửi client cert | Kiểm tra chain, truststore, key alias và hostname |
| SOAP Fault bảo mật chỉ có ở staging | Khác biệt profile WS-Security/timestamp hoặc clock | Đối chiếu policy, đồng bộ thời gian, chứng chỉ môi trường |
| HTTP 415 hoặc VersionMismatch | SOAP version hoặc media type không khớp binding | Kiểm tra `text/xml`/`application/soap+xml` và Envelope namespace |
| `No endpoint mapping found` | QName request khác hợp đồng, namespace đổi theo profile | Giữ namespace ổn định, kiểm tra `@PayloadRoot` |
| Có config timeout nhưng client treo lâu | Timeout chưa gắn vào HTTP sender, retry không giới hạn | Kiểm tra message sender, retry, proxy/network timeout |
| Endpoint chạy được trong container nhưng `localhost` từ nơi khác không tới | Nhầm network namespace | Dùng DNS service/port mapping phù hợp |
| Profile prod khởi động dù thiếu biến URL | Có default âm thầm trong YAML hoặc validation thiếu | Loại fallback nguy hiểm, ràng buộc fail-fast |
| Log lộ thông tin nội bộ | Ghi full SOAP Envelope, exception chứa URL có credential | Mask/redact logs và phân quyền truy cập telemetry |

### Quy trình chẩn đoán nhanh, có thể tái lập

Khi thấy lỗi môi trường, thực hiện theo thứ tự:

1. Xác định profile đang kích hoạt, giá trị config đã bind và nguồn override chính.
2. Phân biệt lỗi là **inbound SOAP provider** hay **outbound SOAP client**.
3. Với outbound, kiểm tra URL client dùng, DNS, TCP/TLS, certificate và HTTP request trước khi kiểm tra SOAP payload.
4. Với inbound, tải WSDL qua URL public, kiểm tra `soap:address` và import, sau đó mới gửi SOAP POST.
5. So sánh SOAP version, media type, SOAPAction và QName với WSDL/XSD đã chốt.
6. Xem SOAP Fault, correlation ID và metrics ở nơi được phép; không in secrets hoặc toàn bộ payload nhạy cảm.
7. Thêm regression test để sự cố không tái diễn trong lần chuyển môi trường tiếp theo.

## 14. Những thực hành cần tránh

### 14.1. Không thay namespace theo hostname

**Sai hướng thiết kế:**

```xml
<!-- Local -->
<xs:schema targetNamespace="http://localhost:8080/orders"/>
<!-- Production -->
<xs:schema targetNamespace="https://soap.example.org/orders"/>
```

Namespace xác định kiểu XML. Thay namespace theo hostname khiến QName khác nhau, JAXB/WSDL/client có thể không tương thích. Thay đổi namespace chỉ nên diễn ra theo **version hợp đồng**, không chỉ vì đổi môi trường.

### 14.2. Không gắn URL outbound vào Java source

**Dễ gây lỗi:**

```java
private static final String SOAP_URL =
    "https://partner-stg.example.org/soap/orders";
```

**Tốt hơn:** lấy `SoapProperties.partner.endpoint` từ nguồn cấu hình đã được kiểm tra. Cách này cho phép một artifact deploy nhiều môi trường và hỗ trợ đổi endpoint khẩn cấp theo quy trình vận hành mà không sửa Java.

### 14.3. Không tùy tiện tắt xác thực TLS

Chứng chỉ staging không hợp lệ không phải lý do để tắt hostname verification hoặc trust-all certificates. Sửa truststore, CA, cert chain, hostname hoặc cấu hình mTLS; test bằng chứng chỉ test hợp lệ.

### 14.4. Không tin header forwarded từ client bất kỳ

Nếu proxy cho phép bên ngoài tự đặt `X-Forwarded-Host`, ứng dụng có thể tạo WSDL với địa chỉ do kẻ gọi quyết định. Cần kiểm soát trusted proxies và xử lý headers tại edge.

### 14.5. Không coi HTTP 200 của WSDL là đã tích hợp thành công

GET WSDL 200 chỉ chứng minh metadata có thể tải. Cần kiểm tra SOAP POST, JAXB mapping, schema validation, SOAP Fault, TLS/WS-Security, timeout và client liên thông thực.

## 15. Bài thực hành theo từng mốc

Giả sử bạn xây ứng dụng **Orders SOAP Provider** có thêm client gửi yêu cầu tới đối tác.

**Mốc A — tách cấu hình**

1. Tạo `application.yml` cho cấu hình chung, các file `application-local.yml`, `application-staging.yml`, `application-prod.yml`.
2. Đặt outbound target URL vào `app.soap.partner.endpoint` và truyền bằng environment variable ở staging/prod.
3. Tạo `SoapProperties` với `@ConfigurationProperties` và validation.
4. Chứng minh ứng dụng không khởi động khi thiếu URL ở production.

**Mốc B — công bố WSDL**

1. Đóng gói WSDL tĩnh hoặc XSD làm nguồn sinh WSDL theo chính sách hợp đồng.
2. Đăng ký `MessageDispatcherServlet` và bean `orders`.
3. Kiểm tra GET `/ws/orders.wsdl`; xác nhận SOAPAction, QName, namespace và `soap:address`.
4. Thử cả hai chế độ rewrite location trong môi trường kiểm thử và giải thích khác biệt; chỉ dùng chế độ được hợp đồng cho phép khi deploy thực.

**Mốc C — SOAP client**

1. Sinh JAXB từ XSD, cấu hình `WebServiceTemplate` và `Jaxb2Marshaller`.
2. Gọi SOAP operation qua endpoint từ `SoapProperties`, không có URL hard-coded trong client.
3. Cấu hình HTTP message sender để áp dụng `connect-timeout` và `read-timeout` thực sự.
4. Kiểm thử request/response, SOAP Fault và timeout với mock/stub trước khi gọi đối tác thật.

**Mốc D — tích hợp vận hành**

1. Cấu hình HTTPS, truststore, mTLS hoặc WS-Security theo môi trường và hợp đồng.
2. Test qua public proxy; xác minh WSDL, imported XSD, SOAP POST, hostname certificate và logging an toàn.
3. Tạo ma trận local/staging/prod cho endpoint, profile, cert, timeout và chính sách WSDL rewrite.
4. Thêm regression checks vào CI để phát hiện thay đổi hợp đồng và URL sai môi trường.

### Câu hỏi tự kiểm tra

1. Tại sao `targetNamespace` không nên thay đổi giữa local và production, trong khi client target URL thường phải thay?
2. Khác biệt giữa `https://soap.example.org/ws/orders.wsdl` và `https://soap.example.org/ws` là gì?
3. Nếu `setTransformWsdlLocations(true)`, điều kiện nào khiến WSDL được trả về có thể sai hoặc không đáng tin?
4. Vì sao dùng `@ConfigurationProperties` và `@NotBlank` vẫn chưa đủ để chứng minh client chỉ gọi HTTPS endpoint hợp lệ?
5. Vì sao khai báo timeout trong YAML không bảo đảm `WebServiceTemplate` thực sự timeout đúng hạn?
6. Khi chuyển client sang partner production URL, cần xác nhận điều gì về TLS, WS-Security và SOAP binding?
7. Nếu staging và production dùng hai WSDL khác nhau về SOAPAction hoặc namespace, đó có còn là «chỉ thay cấu hình môi trường» không?

## 16. Definition of Done: quản lý URL và cấu hình theo môi trường

Một ứng dụng Spring-WS sẵn sàng tích hợp ổn định khi đáp ứng các điều kiện:

- [ ] **Tách biệt cấu hình:** artifact Java/Spring có thể triển khai ở các môi trường mục tiêu mà không sửa source; endpoint không bị hard-code.
- [ ] **Hợp đồng:** QName, SOAPAction, XSD/WSDL và SOAP binding giữ đúng version đã phê duyệt.
- [ ] **Fail-fast:** profile, URL, scheme, host, timeout và cấu hình bắt buộc được kiểm tra khi khởi động.
- [ ] **SOAP client:** `WebServiceTemplate` dùng URL từ properties; message sender có timeout, proxy/TLS và chính sách retry hợp lý.
- [ ] **SOAP provider:** URL tải WSDL và địa chỉ trong `soap:address` đúng chính sách của mỗi môi trường; schema import tải được.
- [ ] **Proxy và TLS:** hostname public, forwarded headers, chứng chỉ và kết nối qua gateway đã được kiểm thử.
- [ ] **Bảo mật:** credential, private key, token và mật khẩu không nằm trong repository/log; chứng chỉ được quản lý riêng theo môi trường.
- [ ] **Liên thông:** ít nhất một client ngoài stack Spring-WS gọi thành công, nhận response/fault đúng hợp đồng.
- [ ] **Hồi quy:** pipeline có test cấu hình, WSDL snapshot/diff, kiểm thử âm tính và smoke test HTTP(S).

Khi đạt các điểm trên, bạn có thể điều chỉnh môi trường triển khai mà vẫn giữ **ranh giới hợp đồng SOAP ổn định**: phía client biết nơi cần gọi, phía server công bố đúng địa chỉ và cả hai cùng tuân thủ XSD/WSDL đã thống nhất.

## 17. Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): nguồn property, thứ tự ưu tiên, environment variables và cách bind.
- [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): cơ chế profile-specific configuration và cách kích hoạt.
- [Spring Boot — Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): typed binding và validation.
- [Spring Boot — Embedded Web Servers](https://docs.spring.io/spring-boot/reference/web/servlet.html): runtime servlet và các yếu tố web server liên quan.
- [Spring Web Services — Reference Documentation](https://docs.spring.io/spring-ws/docs/current/reference/html/): SOAP client/server, contract-first, JAXB, WSDL publication và security.
- [Spring Web Services — MessageDispatcherServlet API](https://docs.spring.io/spring-ws/docs/current/api/org/springframework/ws/transport/http/MessageDispatcherServlet.html): servlet xử lý SOAP và công bố metadata WSDL/XSD.
- [Spring Web Services — WebServiceTemplate API](https://docs.spring.io/spring-ws/docs/current/api/org/springframework/ws/client/core/WebServiceTemplate.html): gọi SOAP và cấu hình transport/message factory.
- [W3C — WSDL 1.1](https://www.w3.org/TR/wsdl.html): `soap:address`, binding, namespace và SOAP operation.
