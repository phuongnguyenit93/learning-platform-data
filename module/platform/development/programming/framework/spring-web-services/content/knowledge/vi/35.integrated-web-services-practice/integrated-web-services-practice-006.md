# Bảo vệ một thao tác bằng WS-Security và phân quyền ở lớp dịch vụ

## Mục tiêu và bối cảnh

Bài thực hành thuộc chương **Thực hành tổng hợp** của module **SPRING_WEB_SERVICES**. Ta xây dựng một dịch vụ SOAP theo hướng **contract-first** với Spring Web Services: định nghĩa thông điệp bằng XSD, ánh xạ JAXB, triển khai `@Endpoint`, rồi bảo vệ thao tác nghiệp vụ bằng **WS-Security** và **Spring Security ở lớp service**. Đây là dạng tích hợp doanh nghiệp cần phân biệt rõ **xác thực danh tính của hệ thống gọi** với **quyền thực hiện một nghiệp vụ cụ thể**.

Sau bài này, bạn có thể:

1. Yêu cầu một yêu cầu SOAP mang `wsse:UsernameToken` và `wsu:Timestamp`, kiểm tra chúng trước khi gọi endpoint.
2. Đưa danh tính đã xác thực vào `SecurityContextHolder` và dùng `@PreAuthorize` để chặn lệnh không đủ quyền.
3. Trả SOAP Fault phù hợp cho trường hợp bị từ chối; kiểm thử cả luồng thành công và các đường thất bại.
4. Giải thích giới hạn của UsernameToken, cách chống replay, và khi nào cần ký thông điệp, chứng chỉ X.509 hoặc mTLS.

**Tình huống:** hệ thống đối tác gửi lệnh `ApproveOrder` để duyệt đơn hàng. Có hai tài khoản dịch vụ: `soap-approver` (có quyền `ORDER_APPROVE`) và `soap-reader` (không có quyền đó). Cả hai có thể xác thực thành công, nhưng chỉ `soap-approver` được duyệt đơn đang chờ.

| Tầng kiểm soát | Câu hỏi được trả lời | Thành phần |
| --- | --- | --- |
| TLS/HTTPS | Kênh truyền có được mã hóa và kiểm tra máy chủ không? | TLS, cấu hình web server/gateway |
| Xác thực thông điệp | Ai đang gửi SOAP request? Token và thời gian có hợp lệ không? | `Wss4jSecurityInterceptor`, `UserDetailsService` |
| Phân quyền nghiệp vụ | Danh tính này có quyền duyệt đơn không? | `@EnableMethodSecurity`, `@PreAuthorize` |
| Quy tắc miền nghiệp vụ | Đơn này có tồn tại, còn ở trạng thái chờ và được phép duyệt không? | `OrderApprovalService`, transaction/DB |

~~~mermaid
sequenceDiagram
    participant C as SOAP client
    participant H as HTTPS + SecurityFilterChain
    participant W as Wss4jSecurityInterceptor
    participant E as @Endpoint
    participant S as Service + @PreAuthorize
    C->>H: SOAP Envelope + WS-Security
    H->>W: Chuyển đến Spring-WS
    W->>W: Kiểm tra Timestamp, UsernameToken, replay
    alt Token không hợp lệ
        W-->>C: SOAP Fault - xác thực thất bại
    else Token hợp lệ
        W->>E: Đặt Authentication vào SecurityContext
        E->>S: approveOrder(orderId)
        alt Không có ORDER_APPROVE
            S-->>C: SOAP Fault - không đủ quyền
        else Có quyền và hợp lệ nghiệp vụ
            S-->>C: ApproveOrderResponse
        end
    end
~~~

## 1. Tạo hợp đồng SOAP trước

Đặt XSD ở `src/main/resources/xsd/orders.xsd`. Ví dụ dùng namespace cố định, phần tử request/response rõ ràng và kiểu dữ liệu dễ ánh xạ JAXB:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:demo:orders:v1"
           xmlns:tns="urn:demo:orders:v1"
           elementFormDefault="qualified">

    <xs:element name="ApproveOrderRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="ApproveOrderResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="xs:string"/>
                <xs:element name="status" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Dùng công cụ XJC/JAXB tương thích với **Jakarta XML Binding** (Spring Boot 3+/Spring-WS 4+) để sinh các lớp `ApproveOrderRequest` và `ApproveOrderResponse` trong package `com.example.orders.contract`. Cấu hình `DefaultWsdl11Definition` trỏ tới XSD nếu muốn xuất WSDL tại `/ws/orders.wsdl`. Ví dụ dưới đây giả định dự án đã cấu hình Spring Web Services để nhận SOAP tại `/ws`; **không đưa thông tin quyền, mật khẩu hay bí mật vào XSD/WSDL**.

Một SOAP Body hợp lệ về mặt hợp đồng có dạng:

~~~xml
<ord:ApproveOrderRequest xmlns:ord="urn:demo:orders:v1">
    <ord:orderId>ORD-1001</ord:orderId>
</ord:ApproveOrderRequest>
~~~

Ở bước này, bất kỳ ai cũng có thể tạo Body hợp lệ; vì vậy riêng xác thực XSD không đủ để bảo vệ lệnh duyệt.

## 2. Chuẩn bị thư viện và ranh giới bảo mật HTTP

Với Spring Boot 3.x, Spring Security 6.x và Spring-WS 4.x, dùng BOM của Spring Boot để quản lý phiên bản tương thích thay vì tự trộn nhiều phiên bản WSS4J. Các dependency trọng tâm trong Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web-services</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.ws</groupId>
        <artifactId>spring-ws-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>

    <!-- Dùng cho bài kiểm thử Spring-WS -->
    <dependency>
        <groupId>org.springframework.ws</groupId>
        <artifactId>spring-ws-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Trong `application.yml` của ứng dụng mẫu có thể khai báo:

~~~yaml
spring:
  webservices:
    path: /ws
~~~

**Điểm dễ nhầm:** kiểm tra HTTP của `SecurityFilterChain` diễn ra trước khi Spring-WS đọc `wsse:Security` trong SOAP Header. Nếu bắt mọi HTTP request phải có Basic/Bearer authentication, yêu cầu WS-Security hợp lệ có thể bị chặn từ cổng HTTP. Ta cho phép request đi qua đường `/ws/**` tới interceptor SOAP; quyền thực sự vẫn được kiểm tra **bắt buộc** tại WS-Security và lớp service. Với REST hoặc tài nguyên khác, cấu hình luật riêng.

## 3. Xác thực WS-Security và kết nối với Spring Security

`Wss4jSecurityInterceptor` chạy trên request SOAP, kiểm tra các hành động bảo mật trong Header. `SpringSecurityPasswordValidationCallbackHandler` tra thông tin người dùng qua `UserDetailsService`; sau xác thực thành công, nó tạo `Authentication` để lớp service dùng.

Ví dụ Java dưới đây minh họa một cấu hình cho môi trường lab. Hai bí mật lấy từ biến môi trường `WS_APPROVER_SECRET` và `WS_READER_SECRET`; **không điền mật khẩu thật vào mã nguồn**.

~~~java
package com.example.orders;

import java.util.Objects;
import org.apache.wss4j.common.cache.MemoryReplayCache;
import org.apache.wss4j.common.cache.ReplayCache;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.InMemoryUserDetailsManager;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;
import org.springframework.ws.soap.security.wss4j2.callback.SpringSecurityPasswordValidationCallbackHandler;

@Configuration
@EnableMethodSecurity
public class SoapSecurityBeans {

    @Bean
    UserDetailsService soapUsers() {
        String approverSecret = Objects.requireNonNull(
            System.getenv("WS_APPROVER_SECRET"), "Missing WS_APPROVER_SECRET");
        String readerSecret = Objects.requireNonNull(
            System.getenv("WS_READER_SECRET"), "Missing WS_READER_SECRET");

        return new InMemoryUserDetailsManager(
            User.withUsername("soap-approver")
                .password(approverSecret)
                .authorities("ORDER_APPROVE")
                .build(),
            User.withUsername("soap-reader")
                .password(readerSecret)
                .authorities("ORDER_READ")
                .build()
        );
    }

    @Bean
    SpringSecurityPasswordValidationCallbackHandler soapPasswordCallback(
            UserDetailsService soapUsers) {
        var handler = new SpringSecurityPasswordValidationCallbackHandler();
        handler.setUserDetailsService(soapUsers);
        return handler;
    }

    @Bean
    ReplayCache soapReplayCache() {
        return new MemoryReplayCache();
    }

    @Bean
    Wss4jSecurityInterceptor wsSecurityInterceptor(
            SpringSecurityPasswordValidationCallbackHandler soapPasswordCallback,
            ReplayCache soapReplayCache) {
        var interceptor = new Wss4jSecurityInterceptor();
        // Thứ tự action phải tương thích với thứ tự client phát sinh.
        interceptor.setValidationActions("Timestamp UsernameToken");
        interceptor.setValidationCallbackHandler(soapPasswordCallback);
        interceptor.setTimestampStrict(true);
        interceptor.setValidationTimeToLive(300);
        interceptor.setFutureTimeToLive(60);
        interceptor.setValidationReplayCache(soapReplayCache);
        interceptor.setSecureResponse(false); // Lab: response đi qua HTTPS.
        return interceptor;
    }

    @Bean
    SecurityFilterChain httpSecurity(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.ignoringRequestMatchers("/ws/**"))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/ws/**").permitAll()
                .anyRequest().denyAll())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .build();
    }
}
~~~

Đăng ký interceptor cho tất cả SOAP endpoints của ứng dụng. Cấu hình này đặt ở một class riêng để Spring khởi tạo các bean theo đúng quan hệ phụ thuộc:

~~~java
package com.example.orders;

import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

@Configuration
@EnableWs
public class SoapEndpointConfiguration implements WsConfigurer {
    private final Wss4jSecurityInterceptor wsSecurity;

    public SoapEndpointConfiguration(Wss4jSecurityInterceptor wsSecurity) {
        this.wsSecurity = wsSecurity;
    }

    @Override
    public void addInterceptors(List<EndpointInterceptor> interceptors) {
        interceptors.add(wsSecurity);
    }
}
~~~

**Tại sao hai tầng xác thực và phân quyền phải nối với nhau?** Nếu dùng `SimplePasswordValidationCallbackHandler` chỉ để kiểm tra mật khẩu mà không có cơ chế đưa danh tính vào `SecurityContextHolder`, `@PreAuthorize` có thể không thấy `Authentication` phù hợp. Callback dựa trên Spring Security ở trên giải quyết chính khoảng nối đó. Spring Security còn cần `@EnableMethodSecurity` để bật kiểm tra annotation trên các bean service.

**Giới hạn quan trọng của mã lab:** cơ chế `PasswordDigest` của WS-Security cần bên xác thực có bí mật tương thích để tính/so sánh digest. Ví dụ `InMemoryUserDetailsManager` trên giữ bí mật dạng có thể sử dụng trực tiếp trong bộ nhớ; không áp dụng nguyên trạng như một giải pháp quản lý mật khẩu production với BCrypt/Argon2. Khi tích hợp thực tế, cân nhắc xác thực bằng chữ ký X.509, mTLS kết hợp ánh xạ identity, hoặc một cơ chế chứng thực đã được thiết kế cho kho mật khẩu băm và chính sách bảo mật của doanh nghiệp. Không tự gắn tiền tố `{bcrypt}` lên bí mật rồi cho rằng UsernameToken PasswordDigest sẽ tự tương thích.

`MemoryReplayCache` giúp nhận ra nonce đã xử lý **trong một JVM**. Nếu triển khai nhiều instance, phải dùng cơ chế replay cache được chia sẻ/đồng bộ giữa các instance hoặc một giải pháp có bảo đảm chống phát lại tương đương; chỉ giới hạn timestamp là chưa đủ. Các máy phải đồng bộ giờ và chọn cửa sổ thời gian đủ chặt.

## 4. Phân quyền ngay trong service nghiệp vụ

Endpoint chỉ làm nhiệm vụ nhận và trả XML. Quyền duyệt phải nằm trong service để các đường gọi khác (ví dụ tác vụ nội bộ, endpoint khác) cũng chịu cùng chính sách. `@PreAuthorize` kiểm tra quyền **trước khi thân phương thức chạy**.

~~~java
package com.example.orders;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderApprovalService {
    // Dữ liệu giả lập trong lab; production dùng repository và transaction.
    private final Map<String, String> stateById =
        new ConcurrentHashMap<>(Map.of("ORD-1001", "PENDING"));

    @PreAuthorize("hasAuthority('ORDER_APPROVE')")
    public String approveOrder(String orderId) {
        return stateById.compute(orderId, (id, previous) -> {
            if (previous == null) {
                throw new IllegalArgumentException("Order does not exist");
            }
            if (!"PENDING".equals(previous)) {
                throw new IllegalStateException("Order already processed");
            }
            return "APPROVED";
        });
    }
}
~~~

~~~java
package com.example.orders;

import com.example.orders.contract.ApproveOrderRequest;
import com.example.orders.contract.ApproveOrderResponse;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrderEndpoint {
    private static final String NS = "urn:demo:orders:v1";
    private final OrderApprovalService service;

    public OrderEndpoint(OrderApprovalService service) {
        this.service = service;
    }

    @PayloadRoot(namespace = NS, localPart = "ApproveOrderRequest")
    @ResponsePayload
    public ApproveOrderResponse approve(@RequestPayload ApproveOrderRequest request) {
        String newStatus = service.approveOrder(request.getOrderId());
        var response = new ApproveOrderResponse();
        response.setOrderId(request.getOrderId());
        response.setStatus(newStatus);
        return response;
    }
}
~~~

Gọi service **qua bean được Spring inject** như ví dụ trên. Nếu một phương thức trong chính `OrderApprovalService` gọi nội bộ tới phương thức khác có `@PreAuthorize` trên cùng đối tượng (self-invocation), proxy Spring AOP có thể không áp dụng kiểm tra cho lời gọi nội bộ đó. Trong ứng dụng thật, đồng thời kiểm soát phạm vi dữ liệu (tenant/owner), trạng thái đơn và tính nguyên tử bằng transaction, khóa hoặc optimistic locking. Quyền `ORDER_APPROVE` chỉ là điều kiện cần, không thay thế các quy tắc nghiệp vụ.

## 5. SOAP request có WS-Security

Thông điệp dưới đây mang tính **minh họa cấu trúc**. Thời gian, nonce và digest phải do client tạo tại lúc gửi; giá trị cố định dưới đây không phải credential dùng để gửi thật.

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
    xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
    xmlns:ord="urn:demo:orders:v1">
  <soapenv:Header>
    <wsse:Security soapenv:mustUnderstand="1">
      <wsu:Timestamp wsu:Id="TS-1">
        <wsu:Created>2026-11-27T04:07:00Z</wsu:Created>
        <wsu:Expires>2026-11-27T04:12:00Z</wsu:Expires>
      </wsu:Timestamp>
      <wsse:UsernameToken wsu:Id="UT-1">
        <wsse:Username>soap-approver</wsse:Username>
        <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">BASE64_DIGEST</wsse:Password>
        <wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">BASE64_NONCE</wsse:Nonce>
        <wsu:Created>2026-11-27T04:07:00Z</wsu:Created>
      </wsse:UsernameToken>
    </wsse:Security>
  </soapenv:Header>
  <soapenv:Body>
    <ord:ApproveOrderRequest>
      <ord:orderId>ORD-1001</ord:orderId>
    </ord:ApproveOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Với UsernameToken dạng `PasswordDigest`, giá trị digest được tính từ nonce đã giải mã, thời điểm tạo và bí mật theo profile UsernameToken. Việc đặt nonce + timestamp cùng replay cache giúp giảm nguy cơ phát lại; **PasswordDigest không tự ký hoặc bảo vệ tính toàn vẹn SOAP Body**. Kẻ có khả năng sửa nội dung trên đường truyền vẫn là mối đe dọa nếu không dùng HTTPS/chữ ký thông điệp.

Trên Spring-WS client, `Wss4jSecurityInterceptor` cũng có thể thêm UsernameToken và Timestamp tự động:

~~~java
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.client.support.interceptor.ClientInterceptor;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

// Tạo interceptor riêng cho client, không dùng lại bean xác thực của server.
var clientSecurity = new Wss4jSecurityInterceptor();
clientSecurity.setSecurementActions("Timestamp UsernameToken");
clientSecurity.setSecurementUsername("soap-approver");
clientSecurity.setSecurementPassword(System.getenv("WS_APPROVER_SECRET"));
clientSecurity.setSecurementPasswordType("PasswordDigest");
clientSecurity.setValidateResponse(false);

// Giả sử template đã được cấu hình JAXB marshaller/unmarshaller.
WebServiceTemplate template = new WebServiceTemplate();
template.setInterceptors(new ClientInterceptor[] { clientSecurity });
// template.setMarshaller(marshaller);
// template.setUnmarshaller(marshaller);
// template.marshalSendAndReceive("https://host.example/ws", request);
~~~

Thứ tự `Timestamp UsernameToken` phải tương thích với `validationActions` trên server; Spring-WS có thể kiểm tra thứ tự bảo mật. `setValidateResponse(false)` chỉ phù hợp với mẫu lab khi server không ký response và kênh đã dùng HTTPS. Nếu đối tác yêu cầu response có WS-Security Signature/Encryption, cần cấu hình cả chiều trả về và xác minh phía client.

## 6. Phân biệt lỗi xác thực, lỗi quyền và lỗi nghiệp vụ

Một request không có Header `wsse:Security`, sai mật khẩu, timestamp hết hạn hoặc nonce bị phát lại phải bị WSS4J từ chối **trước khi endpoint gọi service**. Một request có UsernameToken hợp lệ nhưng thiếu `ORDER_APPROVE` sẽ bị `@PreAuthorize` chặn. Mặc định, lỗi phân quyền phát sinh trong service có thể đi qua chuỗi xử lý exception của SOAP; nên ánh xạ rõ thành SOAP Fault ổn định.

~~~java
package com.example.orders;

import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.soap.server.endpoint.SoapFaultMappingExceptionResolver;

@Configuration
public class SoapFaultConfiguration {
    @Bean
    SoapFaultMappingExceptionResolver soapFaultResolver() {
        var resolver = new SoapFaultMappingExceptionResolver();
        var mappings = new Properties();
        mappings.setProperty(
            "org.springframework.security.access.AccessDeniedException",
            "CLIENT,Operation is not permitted");
        resolver.setExceptionMappings(mappings);
        resolver.setOrder(1);
        return resolver;
    }
}
~~~

Với SOAP 1.1, phản hồi từ chối quyền có thể có dạng:

~~~xml
<soap:Fault xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <faultcode>soap:Client</faultcode>
    <faultstring>Operation is not permitted</faultstring>
</soap:Fault>
~~~

Tên fault code khác khi dùng SOAP 1.2 (ví dụ `Sender`). **SOAP Fault không đồng nghĩa HTTP 403**: nhiều SOAP 1.1 service trả HTTP 500 cùng Fault theo quy ước SOAP/WS-I. Client cần đọc Fault trong Envelope thay vì chỉ suy luận từ HTTP status. Không đưa stack trace, mật khẩu, nội dung token hoặc chi tiết phân quyền nhạy cảm vào `faultstring`. Các lỗi miền như “đã duyệt trước đó” cũng cần được ánh xạ thành fault nghiệp vụ có mã nhất quán theo hợp đồng, thay vì để lộ exception Java.

## 7. Bộ kiểm thử bắt buộc

Tạo hai cặp credential hợp lệ trong môi trường lab (qua biến môi trường) và gửi các request SOAP thực đến `/ws` bằng Spring-WS `WebServiceTemplate`, SoapUI hoặc một SOAP client tương thích. Mỗi trường hợp nên bắt đầu với đơn ở trạng thái `PENDING`, có kiểm tra trạng thái sau lời gọi để xác nhận lệnh bị từ chối **không tạo tác dụng phụ**.

| Tình huống | Kỳ vọng | Điều cần xác minh |
| --- | --- | --- |
| `soap-approver`, token và timestamp hợp lệ | `ApproveOrderResponse` trả `APPROVED` | Chỉ thực hiện duyệt một lần |
| Không có `wsse:Security` | SOAP Fault do lớp WS-Security | Không vào thân service |
| Sai mật khẩu/digest hoặc username không tồn tại | SOAP Fault xác thực | Không thay đổi trạng thái đơn |
| Timestamp hết hạn hoặc vượt thời gian cho phép | SOAP Fault xác thực | Cửa sổ thời gian được áp dụng |
| Gửi lại đúng UsernameToken nonce đã được chấp nhận | SOAP Fault chống replay | Cache đang hoạt động đúng phạm vi triển khai |
| `soap-reader` với token hợp lệ | SOAP Fault không đủ quyền | `@PreAuthorize` thực sự chạy |
| `soap-approver` duyệt đơn đã APPROVED | Fault nghiệp vụ | Không duyệt lần hai |
| Dùng Body sai namespace hoặc không hợp XSD | Lỗi định tuyến/validation tương ứng | Không thực hiện nghiệp vụ |

Gợi ý cho kiểm thử method security (không cần gửi SOAP): gọi trực tiếp **bean được Spring quản lý** và đặt `Authentication` có/không có `ORDER_APPROVE` trong `SecurityContextHolder`. Trường hợp thiếu quyền phải phát sinh `AccessDeniedException`. Kiểm thử này chỉ chứng minh phần phân quyền service; các kiểm thử WS-Security cần đi qua interceptor và SOAP envelope để chứng minh toàn tuyến.

Trường hợp kiểm tra sâu hơn: cấu hình cố ý bỏ `@EnableMethodSecurity` hoặc đăng ký sai interceptor trong một nhánh thử nghiệm để thấy vì sao chỉ có annotation/mật khẩu trong cấu hình vẫn có thể tạo lỗ hổng. Khôi phục cấu hình chuẩn ngay sau thử nghiệm.

## 8. Hoàn thiện cho tích hợp doanh nghiệp

- **Chứng thực và danh tính:** dùng tài khoản riêng cho mỗi đối tác, nguyên tắc quyền tối thiểu, vô hiệu hóa tài khoản ngay khi thu hồi; không dùng chung `ORDER_APPROVE` cho mọi đối tác. Nếu dùng X.509, phải kiểm tra chuỗi tin cậy, hạn dùng, thuật toán, chính sách thu hồi chứng chỉ và ánh xạ chứng chỉ sang danh tính/quyền ở Spring Security.
- **Bí mật và đường truyền:** bắt buộc HTTPS/TLS; lấy secret từ secret manager, có cơ chế xoay vòng và nhật ký truy cập; tránh log SOAP Header chứa token. UsernameToken PasswordDigest **không thay thế** TLS hoặc chữ ký XML. Khi cần chống sửa nội dung từ đầu đến cuối qua nhiều trung gian, áp dụng XML Signature cho SOAP Body và các phần Header liên quan, đồng thời xác minh đúng phần đã ký.
- **Replay và độ tin cậy:** kiểm tra Timestamp, Nonce, replay cache; trong cụm nhiều node dùng phương án cache chống replay nhất quán; đồng bộ thời gian; có rate limit và giới hạn kích thước XML, depth và payload. Không cho parser tải DTD/external entity từ nguồn không tin cậy.
- **Phân quyền:** tách `Authentication` (ai) khỏi `GrantedAuthority` (được làm gì) và kiểm tra tenant/ownership, trạng thái nghiệp vụ tại service/repository. Luồng duyệt thực tế cần transaction và idempotency key để tránh xử lý lặp nếu client retry khi mất phản hồi.
- **Tương thích:** thống nhất SOAP 1.1/1.2, namespace, action, thứ tự WS-Security, yêu cầu Timestamp, chứng chỉ và WS-SecurityPolicy/WSDL với đối tác. Thử với ít nhất một công cụ client ngoài Java để phát hiện khác biệt canonicalization, chữ ký và biểu diễn lỗi.
- **Quan sát:** lưu audit theo `correlationId`, danh tính đã xác thực, mã thao tác, ID đơn và kết quả, nhưng che hoàn toàn mật khẩu, digest, nonce và khóa riêng. Phân biệt lỗi xác thực, lỗi quyền, lỗi hợp đồng và lỗi nghiệp vụ trong metric.

**Bài tập mở rộng:** chuyển từ `UsernameToken` sang chữ ký SOAP bằng X.509 cho client doanh nghiệp; xác thực chữ ký và kiểm tra phần Body được ký; ánh xạ subject/certificate thumbprint được tin cậy sang `Authentication` có quyền `ORDER_APPROVE`. Giữ nguyên `@PreAuthorize` ở service để xác thực bằng cơ chế nào cũng phải qua cùng chính sách quyền.

## Câu hỏi tự đánh giá

1. Vì sao một `UsernameToken` hợp lệ chưa đủ để cho phép thực hiện `ApproveOrder`?
2. Nếu `@PreAuthorize` đã được viết nhưng không bật `@EnableMethodSecurity`, điều gì có thể xảy ra?
3. Vì sao kiểm tra timestamp mà không dùng nonce/replay cache vẫn chưa ngăn được mọi yêu cầu phát lại?
4. Nếu dịch vụ có ba node sau load balancer, cần đổi gì trong cơ chế chống replay?
5. Khi nào mTLS đủ cho yêu cầu tích hợp và khi nào nên thêm chữ ký XML/WS-Security?
6. Nếu cùng một đơn được duyệt đồng thời hai lần, cơ chế phân quyền đã giải quyết vấn đề này chưa? Bạn cần thêm cơ chế gì?

### Tài liệu tham khảo

- [Spring Web Services Reference — Securing Your Web Services](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/)
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring-WS `Wss4jSecurityInterceptor` Javadoc](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/soap/security/wss4j2/Wss4jSecurityInterceptor.html)
- [Apache WSS4J User Guide — replay cache, UsernameToken và chữ ký](https://ws.apache.org/wss4j/user_guide.html)

