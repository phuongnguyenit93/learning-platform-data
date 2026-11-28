# HTTP server nhúng và lựa chọn môi trường triển khai phù hợp

Một dịch vụ Spring Web Services có thể chạy trong **HTTP server nhúng** (embedded server), đóng gói thành executable JAR; triển khai WAR lên servlet container do platform quản lý; hoặc chạy embedded server phía sau **reverse proxy / ingress / load balancer**. Ba mô hình đều phục vụ SOAP endpoint, nhưng khác nhau về packaging, server lifecycle, TLS, routing, resource limits, scaling, patching và trách nhiệm vận hành.

Module **SPRING_WEB_SERVICES** học phát triển SOAP theo hướng **contract-first** với XSD/WSDL, JAXB/OXM, endpoint, SOAP client, SOAP Fault, interceptors, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. Vì vậy, lựa chọn HTTP server phải giữ đúng URL endpoint, SOAP 1.1/1.2 binding, HTTP method/Content-Type/SOAPAction, WSDL/XSD publication, request limits, timeouts và MIME/MTOM attachments.

Các ví dụ dùng Spring Boot 3.x / Spring Framework 6 / Spring-WS 4.x / Java 17+ làm baseline minh họa, không phải khẳng định về version mới nhất. Dự án thực tế phải theo BOM đã chọn và kiểm tương thích API, đặc biệt không trộn Boot 2 / `javax.servlet` với Boot 3 / `jakarta.servlet`.

> **Nguyên tắc:** embedded server là quyết định đóng gói và vận hành. Nó không tự thay Spring-WS message processing, SOAP security, TLS trust policy, XML parser hardening hay kiến trúc triển khai.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả vai trò servlet container, embedded HTTP server và `MessageDispatcherServlet`.
- So sánh executable JAR, WAR/external container và embedded server sau proxy.
- Chọn Tomcat, Jetty hoặc servlet container được platform hỗ trợ theo nhu cầu thực tế.
- Cấu hình dependency, servlet mapping và SOAP endpoint path.
- Phân biệt Boot auto-configuration với đăng ký dispatcher thủ công.
- Thiết kế TLS/mTLS, forwarded headers và trust boundary.
- Giới hạn request size, MIME parts, connections, threads và timeouts.
- Công bố WSDL/XSD qua context path/reverse proxy.
- Thiết kế health checks, graceful shutdown và rolling deployment.
- Kiểm thử endpoint, WSDL, Fault, TLS và MTOM trên HTTP server thật.

## 2. Đường đi của một SOAP request

Spring-WS xử lý nội dung SOAP bên trong ứng dụng web. Embedded servlet container nhận HTTP request, filter chain xử lý transport policies, rồi `MessageDispatcherServlet` dispatch SOAP payload tới endpoint.

~~~mermaid
flowchart TD
    A["SOAP client"] --> B["DNS / Load balancer / Reverse proxy"]
    B --> C["HTTP connector: Tomcat / Jetty"]
    C --> D["Servlet filters / Spring Security"]
    D --> E["MessageDispatcherServlet"]
    E --> F["SOAP / MIME MessageFactory"]
    F --> G["Endpoint mapping + interceptors"]
    G --> H["@Endpoint + JAXB/OXM"]
    H --> I["Application service / database"]
    I --> J["SOAP response / SOAP Fault"]
~~~

| Lớp | Trách nhiệm | Ví dụ lỗi |
|---|---|---|
| Proxy/load balancer | Routing, TLS termination, headers, edge limits | 502/504, 413 |
| Embedded server | HTTP parsing, socket, connector, Servlet lifecycle | 400, reset, timeout |
| Servlet filters | HTTP authentication/authorization, tracing | 401/403 |
| `MessageDispatcherServlet` | Dispatch SOAP tới Spring-WS | Không tìm endpoint |
| Message factory | Parse SOAP Envelope/MIME | XML/MIME malformed |
| Interceptors | WS-Security, validation, audit | Security/validation Fault |
| `@Endpoint` | SOAP operation mapping | Contract/business Fault |
| Application service | Business rules, DB, idempotency | Receiver Fault |

Một HTTP 413 từ proxy có thể xảy ra trước khi SOAP Envelope được parse, vì vậy endpoint không có cơ hội tạo SOAP Fault. Client phải xử lý transport errors song song với SOAP Fault.

## 3. Embedded server là gì và không phải là gì?

Embedded servlet container được đóng gói trong runtime của ứng dụng. Khi chạy executable JAR, Spring Boot khởi tạo application context và server factory; server mở connector rồi phục vụ Servlet.

~~~text
java -jar payments-soap-service.jar
  -> Spring Boot ApplicationContext
  -> ServletWebServerFactory
  -> embedded Tomcat / Jetty
  -> Servlet filters
  -> MessageDispatcherServlet
  -> Spring-WS endpoints
~~~

Embedded server giúp service tự quản lý start/stop, port, context path và connector configuration. Nhưng nó **không tự**:

- Tạo contract XSD/WSDL hoặc kiểm tương thích payload.
- Xác thực UsernameToken, XML Signature hoặc cấp quyền tenant.
- Bảo vệ parser khỏi XXE nếu message factory chưa harden.
- Chuyển HTTP 413/502 thành SOAP Fault.
- Làm endpoint stateless/idempotent.
- Tự scale ngang hay quản lý DB/outbound HTTP pools.

Đây là lớp HTTP runtime trong kiến trúc SOAP.

## 4. Ba mô hình deployment

~~~mermaid
flowchart TB
    subgraph A["A. Embedded trực tiếp"]
      A1["SOAP client"] --> A2["Java process + embedded server"]
      A2 --> A3["Spring-WS endpoint"]
    end
    subgraph B["B. External container"]
      B1["SOAP client"] --> B2["Tomcat/Jetty platform"]
      B2 --> B3["payments.war"]
      B3 --> B4["Spring-WS endpoint"]
    end
    subgraph C["C. Embedded sau proxy"]
      C1["SOAP client"] --> C2["Ingress / API gateway"]
      C2 --> C3["Java container + embedded server"]
      C3 --> C4["Spring-WS endpoint"]
    end
~~~

| Tiêu chí | Embedded trực tiếp | WAR/external | Embedded sau proxy |
|---|---|---|---|
| Packaging | Executable JAR | WAR | JAR/container image |
| Server lifecycle | Ứng dụng | Platform/container | App và proxy chia trách nhiệm |
| Connector config | App properties/beans | Container admin | Proxy + app |
| TLS | Embedded connector hoặc edge | Container/proxy | Thường ingress, có thể mTLS nội bộ |
| Scaling | Process/orchestrator | Container cluster | Orchestrator/LB |
| Phù hợp | Service độc lập | App server fleet chuẩn hóa | Kubernetes/edge gateway |

Không có lựa chọn tốt nhất cho mọi nơi. Chọn theo năng lực vận hành, trách nhiệm patching, certificate lifecycle, routing và deployment platform.

## 5. Tomcat, Jetty và dependency baseline

Spring Boot hỗ trợ embedded servlet containers qua dependency và auto-configuration. Tomcat là lựa chọn thường gặp; Jetty có thể phù hợp với platform đã chuẩn hóa Jetty. Chọn theo support matrix/BOM, servlet API, tuning, observability và integration tests, không chỉ benchmark chung.

Với Maven và Spring Boot dependency management, baseline có thể gồm:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web-services</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Đây là fragment, version do BOM quản lý. Nếu thay Tomcat bằng Jetty, làm theo hướng dẫn của đúng Boot release: exclude starter mặc định và thêm starter tương ứng. Kiểm dependency tree để chỉ có container implementation mong muốn và không có xung đột Servlet/JAXB/SAAJ/WSS4J.

~~~bash
mvn dependency:tree
./gradlew dependencies --configuration runtimeClasspath
~~~

Chạy lệnh tương ứng với build tool thật. Không copy dependency snippet từ Boot release khác mà không kiểm Jakarta Servlet version và compatibility.

## 6. MessageDispatcherServlet và endpoint mapping

`MessageDispatcherServlet` là Servlet trung tâm của Spring-WS. Servlet mapping xác định path HTTP được dispatch tới Spring-WS; endpoint mapping dựa trên SOAP payload QName.

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class HealthEndpoint {
    private static final String NS = "urn:example:health:v1";

    @PayloadRoot(namespace = NS, localPart = "CheckStatusRequest")
    @ResponsePayload
    public CheckStatusResponse check(
            @RequestPayload CheckStatusRequest request) {
        return new CheckStatusResponse("UP");
    }
}
~~~

Generated JAXB classes `CheckStatusRequest` và `CheckStatusResponse` được sinh từ XSD theo contract-first. SOAP endpoint mapping là **QName của payload root**, không phải Java method name hoặc URL path.

~~~text
Servlet mapping:       /ws/*
Endpoint URI:          /ws/payments
Context path:          /
WSDL publication URL:  phụ thuộc WsdlDefinition và servlet mapping
~~~

Không mặc định mọi ứng dụng publish WSDL ở hậu tố .wsdl. Phải GET URL thực, kiểm service/port/binding/operation và XSD imports.

## 7. Boot auto-configuration hay servlet registration thủ công?

Chọn **một chiến lược rõ ràng**. Nếu Boot starter đã đăng ký Spring-WS servlet, sử dụng auto-configuration. Nếu muốn kiểm soát mapping/name/load-on-startup hoặc có nhiều dispatcher, đăng ký thủ công và tắt/điều chỉnh auto-config theo đúng Boot version. Không cấu hình cả hai trùng path.

### 7.1. Boot auto-configuration

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /

spring:
  webservices:
    path: /ws
~~~

Property này phụ thuộc Boot version. Kiểm configuration properties/BOM của dự án, startup logs và integration tests để xác nhận servlet mapping thực tế.

### 7.2. Đăng ký thủ công

~~~java
import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.transport.http.MessageDispatcherServlet;

@Configuration
public class SoapServletConfiguration {

    @Bean
    public ServletRegistrationBean<MessageDispatcherServlet>
            soapServlet(ApplicationContext applicationContext) {
        MessageDispatcherServlet servlet =
            new MessageDispatcherServlet();
        servlet.setApplicationContext(applicationContext);
        servlet.setTransformWsdlLocations(true);

        ServletRegistrationBean<MessageDispatcherServlet> bean =
            new ServletRegistrationBean<>(servlet, "/ws/*");
        bean.setName("soap");
        bean.setLoadOnStartup(1);
        return bean;
    }
}
~~~

Đây là **phương án thay thế** auto-configuration cùng path. `setTransformWsdlLocations(true)` hỗ trợ điều chỉnh location trong WSDL dựa URL request; sau proxy phải kiểm forwarded headers/public host. Nó không thay proxy trust policy.

### 7.3. Nhiều servlet mappings

Nhiều dispatcher có thể hữu ích khi cần tách contract families, URL hoặc security chain. Cần mapping không overlap, WSDL URLs duy nhất, security bảo vệ mọi path và tests cho cả route cũ/mới. Nếu chỉ có một contract family, một dispatcher thường dễ vận hành hơn.

## 8. Port, context path và profiles

Một ứng dụng thường cấu hình:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /

spring:
  webservices:
    path: /ws

management:
  server:
    port: 8081
~~~

Port management riêng không có nghĩa Actuator được public. Bảo vệ network binding, ingress, authentication và endpoint exposure.

Production profile có thể bật graceful shutdown:

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

30 giây chỉ là ví dụ; chọn theo request deadlines và platform termination grace period. Không lưu private key/password/truststore credentials plaintext trong YAML đã commit. Dùng secrets injection, mounted secret hoặc platform secret manager.

## 9. Executable JAR so với WAR

| Đặc điểm | Executable JAR | WAR/external container |
|---|---|---|
| Start | SpringApplication.run | Container deploy WAR |
| Server | Embedded trong runtime | Platform cung cấp |
| Lifecycle | Process/app quản lý | External container quản lý |
| Connector/TLS | App configuration | Container admin/proxy |
| Patch | Rebuild/deploy app image | Platform patch container và app |
| Context path | App/server config | WAR/container config |
| Tài nguyên | Theo process/container | Có thể chia sẻ container resources |

Executable JAR entry point:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PaymentsSoapApplication {
    public static void main(String[] args) {
        SpringApplication.run(PaymentsSoapApplication.class, args);
    }
}
~~~

External WAR thường cần Servlet initializer:

~~~java
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

public class PaymentsSoapWarInitializer
        extends SpringBootServletInitializer {
    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(PaymentsSoapApplication.class);
    }
}
~~~

Packaging và dependency scope `provided` phụ thuộc build plugin/BOM. Trong external deployment, không đồng thời khởi tạo embedded connector khác nếu kiến trúc không chủ đích yêu cầu.

## 10. Reverse proxy và forwarded headers

Production thường đặt ingress/gateway trước embedded server để quản lý public TLS, routing, WAF, rate limits và DNS.

~~~mermaid
flowchart LR
    C["SOAP partner"] --> L["Load balancer"]
    L --> P["Ingress / reverse proxy"]
    P --> S["Embedded server :8080"]
    S --> W["Spring-WS /ws/*"]
~~~

Kiểm proxy terminate TLS hay pass-through; backend dùng HTTP/HTTPS/mTLS; ai ghi Host/X-Forwarded-Proto/X-Forwarded-Host; backend chỉ nhận traffic từ proxy tin cậy; proxy có rewrite HTTP status/SOAP Fault hay không; WSDL `soap:address` có public hostname đúng không.

Nếu backend port 8080 mở rộng, caller có thể bỏ qua WAF/rate limits bằng cách gọi trực tiếp. Dùng network policy/firewall/service mesh để giới hạn nguồn. Chỉ tin forwarded headers từ proxy đã strip/rewrite header do caller gửi; nếu không, WSDL có thể lộ host nội bộ hoặc chịu host-header injection.

## 11. TLS termination và mTLS

**TLS tại embedded server:** app sở hữu server certificate/private key; certificate lifecycle phải quản lý trên từng service/replica.

**TLS tại proxy:** edge sở hữu public certificate, backend nhận traffic nội bộ. Cần đánh giá TLS/mTLS từ proxy tới app để bảo vệ trust boundary nội bộ.

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:/run/secrets/soap-server.p12
    key-store-type: PKCS12
    key-alias: soap-server
~~~

Ví dụ chỉ nêu server keystore; password phải inject từ secret source. Client certificate authentication cần truststore/client-auth policy cụ thể và test handshake.

mTLS xác thực peer của TLS connection; WS-Security UsernameToken xác thực message credential; XML Signature bảo vệ XML elements được ký. Không mặc định client certificate đã được proxy xác minh thì Spring app tự biết identity ấy. Cần identity propagation channel tin cậy hoặc end-to-end mTLS.

## 12. Timeout và deadline budget

| Timeout | Ý nghĩa | Rủi ro khi cấu hình sai |
|---|---|---|
| Client connect | Thiết lập connection | Chờ lâu khi server down |
| Client read | Chờ response | Client timeout trước xử lý hợp lệ |
| Proxy upstream | Gateway chờ backend | Gateway đóng trước app hoàn tất |
| Server keep-alive/idle | Giữ connection nhàn rỗi | Cạn connection |
| DB/downstream | Chờ dependency | Giữ request thread và pool |
| Graceful shutdown | Chờ in-flight work | Kill process quá sớm |

Không đặt mọi timeout bằng nhau. Xây deadline budget xuyên client→proxy→server→DB/downstream và chừa thời gian trả response. Với payment/upload, timeout **không chứng minh** server chưa commit; cần idempotency/reconciliation.

## 13. Request limits và MTOM attachments

SOAP request có thể là XML đơn hoặc multipart/related. Cần giới hạn độc lập:

- HTTP request body bytes, kể cả chunked transfer thực tế.
- SOAP XML bytes, XML depth/nodes/text length.
- MIME part count, per-part bytes và total attachment bytes.
- MIME headers/Content-ID length.
- Upload duration/read-idle timeout.
- Temp disk quota và cleanup.
- Số upload lớn chạy đồng thời.

Không giả định một property Spring Boot áp lên mọi proxy, servlet connector và MIME parser. Cấu hình giới hạn ở ingress, container/message factory và application attachment handling. Với file lớn, stream tới storage có giới hạn; không mặc định copy toàn bộ vào `byte[]`.

Proxy có thể buffer toàn body, chặn 413 hoặc timeout upload chậm. Integration test phải gửi MTOM body qua ingress production; mock trong process không chứng minh behavior của ingress. Không log raw SOAP Envelope/attachments trong production vì lộ credentials/PII và tạo log I/O lớn.

## 14. Thread pools và outbound connection pools

Endpoint đồng bộ thường chiếm HTTP request thread trong khi JAXB, WS-Security, DB và outbound SOAP calls chạy. Nếu downstream chậm, server có thể bão hòa dù CPU chưa 100%.

| Metric | Ý nghĩa |
|---|---|
| Active/max request threads | Concurrency server |
| Queued/busy connections | Áp lực connector |
| DB pool active/pending | Nghẽn database |
| Outbound HTTP pool leased/pending | Nghẽn SOAP client/downstream |
| P95/P99 latency | Tail latency |
| Rejections/timeouts | Saturation/backpressure |
| Heap/GC | XML/DOM/JAXB/attachments allocation |

Không tăng max threads để che DB chậm. Nếu DB pool chỉ có 30 connections, 500 request threads có thể cùng chờ DB. Dùng bounded concurrency, rate limit, timeout và backpressure. `WebServiceTemplate` outbound dùng message sender/HTTP client riêng; tuning pool inbound không tự cấu hình outbound SOAP client.

Endpoint beans thường singleton. Không lưu current username, tenant, request DTO hoặc SoapMessage trong field. Request state nằm ở local variables; shared dependencies phải thread-safe.

## 15. WSDL/XSD publication qua context path và proxy

WSDL có thể chứa `soap:address`, XSD imports/includes và locations. Khi chạy sau proxy, không để URL backend nội bộ như http://payments:8080/ws bị publish cho partner.

Kiểm canonical public URL/scheme; trusted forwarded headers; dispatcher transform WSDL locations; XSD imports resolve từ client network; management/debug endpoints không lẫn public route; soap:address khớp endpoint public. Giữ QName/XSD/WSDL operations ổn định giữa môi trường và chỉ thay endpoint address theo cấu hình. Khi đổi path, cần versioning/deprecation plan.

Partner tải WSDL thành công không chứng minh SOAP operation, database hay WS-Security hoạt động. Actuator health UP cũng không chứng minh WSDL publication và SOAP invocation pass. Cần smoke test cả hai.

## 16. Liveness, readiness và graceful shutdown

**Liveness** cho biết process còn sống; **readiness** cho biết instance có nên nhận traffic mới. Health check không nên gọi business operation có side effect. Không expose actuator diagnostics rộng ra Internet.

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Cấu hình phụ thuộc Boot version; chỉ expose endpoints cần thiết và bảo vệ management port/path.

Rolling shutdown mong muốn:

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant LB as Load balancer
    participant A as SOAP app
    P->>LB: Mark instance not-ready / drain
    LB-->>A: Stop new traffic
    P->>A: SIGTERM
    A->>A: Stop accepting requests
    A->>A: Finish bounded in-flight work
    A-->>P: Shutdown complete
~~~

Spring Boot hỗ trợ graceful shutdown trên embedded server tương thích. Readiness/drain phối hợp với timeout-per-shutdown-phase và platform grace period. Long-running SOAP uploads cần deadline, durable state, idempotency và status/reconciliation; không kéo dài shutdown vô hạn.

## 17. Container image, orchestration và horizontal scaling

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/payments-soap-service.jar app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Base image theo patch policy; `EXPOSE` chỉ là metadata, không public firewall/port. Chạy non-root nếu tương thích, cấp temp disk quota và không dùng container memory toàn bộ làm heap.

Nhiều replica cần externalize replay/nonce cache, idempotency records, business data, file storage, quota state và certificates/secrets. Nếu replay cache chỉ local JVM, cùng token có thể tới replica khác và lọt replay. Nếu idempotency chỉ in-memory, restart có thể tạo payment trùng.

## 18. External servlet container: trách nhiệm và rủi ro

WAR phù hợp khi tổ chức có servlet-container fleet, patching, certificate lifecycle và monitoring tập trung. Cần làm rõ ai quản lý JDK/Servlet versions, connectors, TLS, request size, thread pools, graceful redeploy và incident response.

Shared container có thể gặp dependency/classloader conflicts giữa JAXB, SAAJ, XML Security và WSS4J. JNDI DataSource/transactions có thể chỉ tồn tại ở production. Cần integration tests trên đúng external container; local embedded tests không đủ chứng minh WAR deployment tương thích.

## 19. Spring Security và routing

HTTP filter chain và Spring-WS EndpointInterceptor là hai lớp riêng:

~~~text
SOAP servlet path:  /ws/*
Management path:    /actuator/*
Internal admin:     /admin/* (nếu có)
~~~

Nếu UsernameToken là cơ chế xác thực chính, HTTP route có thể cho request đến SOAP dispatcher theo policy, nhưng WSS4J phải bắt buộc token và business authorization. `permitAll()` ở HTTP layer không có nghĩa SOAP operation public. Mọi dispatcher mapping phải đi qua đúng filter/interceptor chain.

Kiểm HTTP methods, CSRF nếu dùng browser cookies, CORS nếu có browser use case, context paths và alternate routes. Không tắt CSRF toàn ứng dụng chỉ để SOAP client server-to-server hoạt động.

## 20. HTTP/2, keep-alive và SOAP interoperability

SOAP stacks thường dùng HTTP/1.1; hỗ trợ HTTP/2 ở proxy không có nghĩa SOAP clients phải dùng HTTP/2. Kiểm ALPN, TLS, gateway và client stack trước khi bật.

Keep-alive/idle timeout cần đồng bộ giữa client, proxy và server. Giải phóng outbound HTTP connections đúng lifecycle; không để slow client upload giữ threads vô hạn. SOAP request có thể dùng Content-Length hoặc chunked transfer; enforce actual stream bytes, không chỉ tin header Content-Length. Với MTOM multipart, test framing thực tế.

| HTTP result | Client behavior |
|---|---|
| 200 + SOAP response | Parse và kiểm QName/contract |
| 500 + SOAP Fault | Parse Fault theo SOAP version |
| 401/403 | Transport authentication/authorization |
| 413 | Body quá lớn; có thể không có SOAP Envelope |
| 502/503/504 | Proxy/upstream failure; retry có idempotency |
| 400 | HTTP/parser/framing/content type |
| Connection timeout/reset | Outcome có thể chưa rõ; reconcile side effects |

Không mặc định mọi HTTP 500 là SOAP Fault; proxy có thể trả HTML. Kiểm Content-Type và SOAP Envelope trước khi phân loại.

## 21. Observability và secret management

Log metadata-only có thể theo mẫu:

~~~text
event=soap_request_completed
service=payments-soap
operation=SubmitPayment
soapVersion=1.1
transport=https
result=SUCCESS
httpStatus=200
requestBytes=1840
responseBytes=920
durationMs=84
partnerId=partner-a
correlationId=corr-7f13
~~~

Không log raw SOAP Body, PasswordText, UsernameToken, certificate private material, XML Signature secrets/tokens hoặc PDF. Metrics nên gồm request status, SOAP Fault categories, connector busy threads, connections/queues, attachment bytes/count, WS-Security failures, DB/outbound pool, P95/P99 latency, heap/GC, readiness transitions và shutdown duration.

Không dùng requestId/accountId làm metric tags có cardinality cao. Dùng operation/normalized route/partner tier; chi tiết correlation để ở logs/audit có access controls.

Secrets (keystore/truststore passwords, WS-Security callbacks, DB passwords) phải inject từ platform Secrets/Vault/KMS hoặc file mount được bảo vệ. Làm rõ quyền đọc, rotation/reload, audit, dev/stage/prod separation và diagnostics redaction. Không commit credentials vào YAML hay image.

## 22. Kiểm thử server nhúng từ unit đến wire

| Test | Điều cần chứng minh |
|---|---|
| Unit test endpoint/service | Business behavior |
| `MockWebServiceClient` | Spring-WS server endpoint/interceptors trong mock context |
| `MockWebServiceServer` | Outbound `WebServiceTemplate` |
| `@SpringBootTest(RANDOM_PORT)` | Boot context và embedded HTTP route |
| HTTP integration | Actual status, headers, Content-Type, POST và SOAP envelope |
| TLS integration | Certificate, hostname, mTLS |
| Proxy integration | Public URL, forwarded headers, limits/timeouts |
| Load/concurrency | Thread/DB pools, latency, resource budgets |
| Shutdown test | Readiness, drain, in-flight requests |

Random-port test skeleton:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.LocalServerPort;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
class SoapHttpIntegrationTest {
    @LocalServerPort
    int port;

    @Test
    void soapEndpointIsReachable() {
        String endpoint = "http://localhost:" + port + "/ws/payments";
        // Gửi SOAP Envelope synthetic với Content-Type/SOAPAction đúng.
        // Assert response QName/status và không có Fault ngoài dự kiến.
    }
}
~~~

Đây là skeleton; endpoint URL phải khớp context path + servlet path thực tế. Test GET WSDL và kiểm definitions/binding/operation/imports/public soap:address. Test riêng SOAP POST, HTTP 500 Fault, SOAP 1.1/1.2, WS-Security và MIME/MTOM. Không chỉ GET root path rồi kết luận SOAP service hoạt động.

## 23. Quy trình triển khai và rollback

1. Build artifact/image bất biến theo commit/version.
2. Kiểm dependency tree và Java/Servlet/JAXB/SAAJ/WSS4J compatibility.
3. Chạy unit, contract, security, HTTP và TLS tests.
4. Kiểm WSDL/XSD public locations và soap:address.
5. Deploy canary, probe liveness/readiness.
6. Gửi synthetic SOAP request không có side effect hoặc test transaction.
7. Quan sát connector, DB/outbound pools, Fault rates và latency.
8. Route traffic dần qua load balancer.
9. Drain instance cũ và chờ in-flight requests trong shutdown budget.
10. Xác nhận attachment temp files đã cleanup và không có transaction trùng.

Rollback không chỉ chạy image cũ. Nếu release mới thay WSDL/XSD, signed SOAP policy hoặc endpoint path, client có thể đã đổi generated code/certificate/config. Phải xét contract version, DB compatibility, idempotency records, partner rollout và address migration.

## 24. Chọn môi trường triển khai: ma trận quyết định

| Điều kiện | Phương án thường phù hợp | Lý do |
|---|---|---|
| Microservice độc lập/container | Embedded JAR sau ingress | Artifact tự chứa, rollout theo service |
| App-server fleet chuẩn hóa | WAR/external | Connector/runtime tập trung |
| Cần WAF, public TLS, rate limit chung | Embedded sau proxy | Chính sách edge tập trung |
| Cần mTLS đến process | Embedded TLS hoặc mTLS proxy→backend | Đúng trust boundary |
| Dùng JNDI/shared resources legacy | WAR/external | Tận dụng platform-managed resources |
| MTOM file lớn | Cả hai đều có thể | Streaming/limits/tests quyết định |
| Nhiều contract families | Multiple dispatcher có chủ đích | Tách routing/security |

Quyết định phải làm rõ ai chịu trách nhiệm patching, TLS, scaling, routing, limits, WSDL, restart và incident response; không chỉ dựa tên container.

## 25. Troubleshooting thường gặp

| Triệu chứng | Khả năng | Hướng kiểm |
|---|---|---|
| App start nhưng /ws 404 | Servlet mapping sai/chưa register | Boot auto-config vs custom bean |
| Hai servlet cùng path | Auto-config + registration thủ công | Chọn một chiến lược |
| WSDL address lộ hostname nội bộ | Forwarded headers/transform sai | Trusted proxy/public URL |
| Không tìm endpoint | QName/namespace không khớp | PayloadRoot và XSD |
| SOAP 1.2 unsupported media type | Server bind SOAP 1.1 | Envelope namespace/Content-Type/binding |
| HTTP 413 trước endpoint | Proxy/connector limit | Kiểm mọi layer |
| MTOM upload OOM | Buffering/byte[]/raw logging | Streaming/storage quotas |
| Threads bão hòa | DB/downstream chậm | Bounded pools/backpressure |
| TLS direct works, proxy fails | Termination/forwarding/trust | Proxy→backend TLS and host |
| Shutdown làm request fail | Readiness/drain/timeouts lệch | Graceful shutdown sequence |
| WSDL imports fail ở client | Relative path/rewrite | Resolve locations qua public route |
| HTTP 500 trả HTML | Gateway error page | Content-Type/Envelope |
| Duplicate request sau timeout | Idempotency không atomic | requestId + reconciliation |
| WAR fail nhưng JAR pass | Classloader/dependency/JNDI | Test external container |
| Health UP nhưng SOAP fail | Health probe quá nông | SOAP contract smoke test |

## 26. Bài thực hành: đóng gói SOAP service thành executable JAR

**Bối cảnh:** dịch vụ chứng từ có /ws/documents và /ws/partners, dùng JAXB contract-first, WS-Security UsernameToken, XML Signature và MTOM cho file lớn. Platform deploy container image qua ingress HTTPS; embedded server chỉ nghe mạng nội bộ.

### Nhiệm vụ

1. Chọn Boot BOM/Java/Jakarta baseline tương thích Spring-WS/WSS4J.
2. Chọn embedded container được BOM/platform hỗ trợ.
3. Chọn auto-config hoặc custom dispatcher, không đăng ký trùng.
4. Cấu hình servlet path, endpoint URL và WSDL/XSD publication.
5. Kiểm public soap:address sau ingress.
6. Đặt HTTP/MIME limits, timeout và pools.
7. Chọn TLS termination ở ingress hoặc end-to-end/mTLS.
8. Tin forwarded headers chỉ từ ingress được kiểm soát.
9. Bảo vệ actuator/management network.
10. Định nghĩa readiness, liveness, graceful shutdown và drain.
11. Quản lý key/truststore qua secrets.
12. Dùng replay cache/idempotency bền giữa replicas.
13. Tạo image non-root và resource limits.
14. Test SOAP 1.1/1.2, Fault, WSDL, WS-Security và MTOM.
15. Test qua ingress với HTTP 413/502/504.
16. Load test uploads, concurrency và shutdown.
17. Canary, quan sát metrics và rollback theo contract version.
18. Viết runbook certificate rotation và endpoint path migration.

### Câu hỏi tự kiểm tra

1. Embedded server khác `MessageDispatcherServlet` thế nào?
2. Hai servlet cùng path có thể gây vấn đề gì?
3. Vì sao GET WSDL không chứng minh SOAP POST hoạt động?
4. Tại sao forwarded headers cần trust proxy?
5. TLS terminate ở proxy có nghĩa backend đã xác thực partner certificate không?
6. HTTP 413 có luôn tạo SOAP Fault không?
7. Vì sao tăng max threads có thể làm DB overload?
8. Inbound server pool có tự cấu hình outbound `WebServiceTemplate` không?
9. WSDL public address sai ảnh hưởng client thế nào?
10. Liveness khác readiness ra sao?
11. Drain cần xảy ra trước bước nào của shutdown?
12. MTOM upload cần quota ở các lớp nào?
13. Vì sao embedded JAR vẫn cần NetworkPolicy?
14. WAR có thể gặp classloader conflicts nào?
15. Health UP có chứng minh WS-Security hoạt động không?
16. Timeout sau SubmitPayment có chứng minh chưa commit không?
17. SOAP 1.2 client gọi SOAP 1.1 endpoint cần kiểm gì?
18. Vì sao không log raw SOAP Envelope production?

### Đáp án tham khảo

| Câu | Trả lời |
|---|---|
| 1 | Embedded server nhận HTTP/Servlet; dispatcher dispatch SOAP vào Spring-WS. |
| 2 | Registration trùng/ambiguous, endpoint path không rõ. |
| 3 | WSDL route chỉ kiểm metadata, không kiểm runtime POST/security. |
| 4 | Caller có thể giả header nếu proxy không strip/rewrite. |
| 5 | Không; TLS ở proxy xác thực peer của proxy. |
| 6 | Không; request có thể bị chặn trước SOAP parse. |
| 7 | Nhiều request cùng chờ DB, tăng queue/memory. |
| 8 | Không; outbound message sender có pool riêng. |
| 9 | Client gọi host private/sai URL hoặc không resolve WSDL. |
| 10 | Liveness process còn sống; readiness có nhận traffic được không. |
| 11 | Mark not-ready/drain trước khi ngừng connector. |
| 12 | Ingress, connector, MIME parser, attachment storage và app quotas. |
| 13 | Chỉ cho phép dependencies/ingress cần thiết, chặn bypass port. |
| 14 | JAXB/SAAJ/XML Security/WSS4J version conflict và JNDI assumptions. |
| 15 | Không; probe có thể không gọi SOAP endpoint/security. |
| 16 | Không; response có thể mất sau commit. Dùng idempotency/reconcile. |
| 17 | Envelope namespace, Content-Type, WSDL binding, message factory. |
| 18 | Lộ credentials/PII/binary và tăng log I/O/storage. |

## 27. Checklist trước khi chọn môi trường

- [ ] Đã xác định JAR, WAR hay embedded server sau proxy.
- [ ] Boot/Framework/Spring-WS/JAXB/SAAJ/WSS4J/Servlet API tương thích.
- [ ] Một chiến lược register dispatcher cho mỗi path.
- [ ] Endpoint, context path, WSDL/XSD imports và public soap:address đã test.
- [ ] Container selection dựa BOM/support/integration tests.
- [ ] HTTP methods, Content-Type, SOAPAction và SOAP versions đúng.
- [ ] TLS/mTLS, hostname validation, truststore và proxy trust boundary rõ.
- [ ] Forwarded headers chỉ tin từ proxy được kiểm soát.
- [ ] Body/MIME/XML depth/timeouts/temp storage có giới hạn.
- [ ] Inbound, outbound SOAP client và DB pools tuning riêng.
- [ ] Không tăng thread count khi chưa đo downstream capacity.
- [ ] HTTP filters và WSS4J interceptors bảo vệ tất cả SOAP paths.
- [ ] WSDL publication tách management/debug routes.
- [ ] Liveness/readiness không tạo business side effects.
- [ ] Graceful shutdown/drain khớp platform grace period.
- [ ] Image non-root, patched base image, JVM memory budget phù hợp.
- [ ] Secrets/certificates inject/rotate có audit.
- [ ] Replay cache/idempotency nhất quán giữa replicas.
- [ ] Logs/metrics metadata-only, không raw SOAP/token/attachment.
- [ ] Có unit, mock, random-port HTTP, TLS, proxy và load tests.
- [ ] Rollback/contract version/deployment runbook đã kiểm thử.

## 28. Tổng kết

Embedded HTTP server giúp SOAP service được đóng gói và vận hành như ứng dụng độc lập: executable JAR khởi động servlet container, server nhận HTTP, rồi `MessageDispatcherServlet` dispatch SOAP vào Spring-WS endpoint/interceptors. Đây là phương án phù hợp với nhiều microservices/container platforms. **WAR trên external servlet container** vẫn phù hợp khi tổ chức quản lý app server tập trung; **embedded server sau reverse proxy** phù hợp khi cần routing, public TLS, WAF, rate limits và quản trị edge.

Không nên chọn theo tên Tomcat/Jetty hay benchmark đơn lẻ. Hãy quyết định ai sở hữu lifecycle, patching, connector/TLS, WSDL publication, scaling và incident response. Kiểm cả đường đi SOAP: **endpoint mapping, SOAP 1.1/1.2 Content-Type, public WSDL/XSD URLs, UsernameToken/Signature validation, MIME/MTOM limits, SOAP Fault và retry semantics**. Reverse proxy không thay XML/WS-Security; health probe không thay SOAP smoke test; timeout không chứng minh giao dịch chưa commit.

Một môi trường production ổn định kết hợp **container được hỗ trợ**, **một chiến lược servlet registration rõ**, **TLS/trust boundary đúng**, **request/thread/connection limits**, **graceful shutdown/readiness**, **idempotency/replay state dùng chung giữa replicas** và **integration tests qua chính ingress**. Khi trách nhiệm giữa application, servlet container, proxy và platform được phân định, dịch vụ Spring Web Services có thể triển khai độc lập mà vẫn giữ contract SOAP và mức bảo mật vận hành nhất quán.
