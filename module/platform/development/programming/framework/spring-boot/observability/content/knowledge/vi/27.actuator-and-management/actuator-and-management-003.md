# Management port trong Spring Boot Actuator

> **Chương:** Actuator và management  
> **Bài:** Management port  
> **Module:** SPRING_BOOT_OBSERVABILITY — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Management port là gì?

Ứng dụng Spring Boot thường mở một HTTP port để phục vụ request nghiệp vụ. Đồng thời, nền tảng vận hành cần các endpoint như health, metrics, info hoặc prometheus để kiểm tra trạng thái và thu thập telemetry.

Management port là cổng mạng phục vụ các management endpoints của Spring Boot Actuator. Các endpoint có thể dùng chung cổng với ứng dụng hoặc được phục vụ trên một cổng riêng. Tách cổng tạo một đường truy cập vận hành độc lập với traffic nghiệp vụ.

Ví dụ:
- Application server: 8080
- Management server: 8081
- Health: http://localhost:8081/actuator/health
- Metrics: http://localhost:8081/actuator/metrics

Tách port không tự động bảo vệ endpoint. Vẫn cần quyết định endpoint nào được expose, caller nào được phép truy cập, TLS, authentication và network policy.

~~~mermaid
flowchart LR
  U["API clients"] -->|8080| A["Spring Boot application"]
  A --> B["Business controllers"]
  M["Monitoring / probes"] -->|8081| C["Actuator management server"]
  C --> D["Health / metrics / info"]
  A --> E["Application services"]
  E --> F["Database / dependencies"]
~~~

## 2. Cùng port hay port riêng?

Spring Boot Actuator hỗ trợ hai mô hình:

| Mô hình | Cấu hình | Đặc điểm |
| --- | --- | --- |
| Same port | Không đặt management.server.port riêng | Management endpoints dùng web server chính |
| Separate port | Đặt management.server.port khác server.port | Management endpoints dùng management web server riêng theo cấu hình |

Same port đơn giản và phù hợp nhiều ứng dụng. Separate port hữu ích khi muốn:
- Tách đường probe/monitoring khỏi ingress public.
- Áp dụng firewall hoặc network policy riêng.
- Quản lý bind address hoặc TLS riêng.
- Tách port mapping của platform và application.

Port riêng cũng tạo thêm listener và cấu hình vận hành. Cần mở đúng port trong container/service, cấu hình probes, TLS, security chain và monitoring target.

## 3. Cấu hình application port và management port

Ví dụ application.yml:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
~~~

API được phục vụ trên 8080; Actuator web endpoints được phục vụ trên 8081 theo base path mặc định, nếu endpoint tương ứng được expose.

Management base path thường mặc định là /actuator. Có thể thay đổi:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
~~~

Khi đó health endpoint có thể là /manage/health tùy endpoint mapping. Base path là đường dẫn HTTP; management port là cổng TCP. Hai cấu hình này độc lập.

Nếu không đặt management.server.port, management endpoints thường chia sẻ application port. Nếu đặt một giá trị khác, Spring Boot cấu hình management web server riêng theo web application type và phiên bản.

## 4. Bind management server vào địa chỉ nào?

Có thể bind management listener vào interface cụ thể. Ví dụ chỉ bind loopback:

~~~yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
~~~

Caller từ container hoặc host khác thường không truy cập được qua network interface bên ngoài. Cấu hình này chỉ phù hợp khi probe/agent chạy cùng network namespace hoặc có cơ chế local access.

Trong Kubernetes, kubelet probe truy cập Pod IP từ node. Bind listener vào 127.0.0.1 có thể khiến probe không kết nối được. Cần hiểu network namespace và probe target trước khi chọn address.

Nếu monitoring cần truy cập từ network nội bộ, bind vào interface phù hợp và giới hạn caller bằng firewall, security group hoặc NetworkPolicy. Tránh bind management listener ra mọi interface mà không có kiểm soát.

## 5. Endpoint exposure không đồng nghĩa authorization

Actuator có cơ chế exposure để quyết định endpoint nào được publish qua web/JMX. Ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Cấu hình này cho phép các endpoint được liệt kê xuất hiện qua web nếu endpoint tương ứng có mặt trên classpath. Nó không thay thế authentication/authorization.

Cần phân biệt:
- Exposure: endpoint có được publish qua web/JMX hay không.
- Authorization: caller nào được phép gọi endpoint.
- Network reachability: caller có thể kết nối tới listener hay không.
- Endpoint access: endpoint được phép read/write theo policy và version.
- Data sanitization: response có lộ dữ liệu nhạy cảm hay không.

Một endpoint không exposed qua web vẫn có thể được expose qua JMX nếu cấu hình khác. Một endpoint exposed nhưng bị Spring Security chặn vẫn không truy cập được nếu caller thiếu quyền.

Không expose env, configprops, heapdump, threaddump hoặc logfile công khai chỉ để debug nhanh. Các endpoint này có thể tiết lộ cấu hình, runtime hoặc dữ liệu nhạy cảm.

## 6. Health endpoint trên management port

Health endpoint thường được dùng để kiểm tra trạng thái ứng dụng:

~~~http
GET /actuator/health
~~~

Khi management port riêng được cấu hình, health endpoint có thể được phục vụ tại management port. Spring Boot có thể cung cấp health groups như liveness và readiness tùy version/configuration.

- Liveness: process có cần restart vì không còn hoạt động bình thường?
- Readiness: instance có sẵn sàng nhận traffic nghiệp vụ không?
- General health: trạng thái tổng hợp của các health contributors được cấu hình.

Không đưa mọi dependency vào liveness một cách thiếu chọn lọc. Nếu database tạm thời unavailable và liveness fail, platform có thể restart pods liên tục dù process vẫn sống; điều đó có thể làm sự cố nặng hơn.

Readiness phù hợp hơn để tạm ngừng routing traffic tới instance không sẵn sàng. Liveness nên phản ánh tình trạng process cần restart, tránh phụ thuộc vào downstream có thể phục hồi độc lập.

## 7. Management port và Kubernetes probes

Kubernetes startup/readiness/liveness probes có thể gọi Actuator health groups. Ví dụ Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: example/order-service:1.0
          ports:
            - name: http
              containerPort: 8080
            - name: management
              containerPort: 8081
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: management
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: management
            periodSeconds: 10
~~~

Đây là ví dụ cấu hình. Cần bật/provide health groups tương ứng trong Spring Boot version đang dùng và xác minh path thực tế. containerPort mô tả port trong Pod; nó không tự mở firewall hay tạo Kubernetes Service.

Nếu probe dùng port name management, container phải khai báo đúng port name và ứng dụng phải bind listener tới interface kubelet truy cập được.

Readiness failure khiến Pod bị loại khỏi endpoints phục vụ traffic qua Service. Liveness failure có thể khiến kubelet restart container sau khi vượt failure threshold. Startup probe trì hoãn liveness/readiness evaluation trong giai đoạn khởi động dài.

Cấu hình timeout, period và failure threshold theo startup/recovery behavior thực tế. Không đặt quá nhạy khiến spike ngắn hoặc management server chậm gây restart loop.

## 8. Management port riêng có thực sự độc lập?

Management port riêng tạo listener riêng, nhưng không phải process riêng. Nó vẫn chạy trong cùng JVM, dùng chung heap, CPU và phần lớn application context.

Điều này có nghĩa:
- CPU starvation có thể làm cả API và Actuator phản hồi chậm.
- JVM pause/GC ảnh hưởng cả hai listeners.
- Health endpoint có thể không phản ánh mọi failure mode nếu management server vẫn sống trong khi business server gặp lỗi.
- Thread pool/connector behavior phụ thuộc web server và Spring Boot version.
- Port riêng không bảo vệ endpoint khỏi lỗi code hoặc dependency trong cùng process.

Nếu cần kiểm tra business server thực sự nhận request, cấu hình health check phù hợp hoặc kiểm tra application port riêng. Management health endpoint chỉ chứng minh đường management endpoint hoạt động và health contributors báo trạng thái tương ứng.

## 9. TLS cho management port

Management server có thể được cấu hình SSL riêng trong các phiên bản Spring Boot hỗ trợ. Cần phân biệt SSL của application server và management server; khi dùng separate port, cấu hình TLS management có thể khác.

Ví dụ khái niệm:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: classpath:server.p12
    key-store-password: ${SERVER_KEYSTORE_PASSWORD}

management:
  server:
    port: 9443
    ssl:
      enabled: true
      key-store: classpath:management.p12
      key-store-password: ${MANAGEMENT_KEYSTORE_PASSWORD}
~~~

Property và khả năng dùng SSL riêng cho management server phụ thuộc Spring Boot version/web server. Kiểm tra reference phiên bản thực tế. Không commit keystore password hoặc private key vào source control; dùng secret management.

Nếu monitoring agent scrape HTTPS, cấu hình CA/truststore và hostname verification đúng. Không tắt certificate validation để xử lý lỗi scrape trong production.

## 10. Spring Security trên management endpoints

Khi Spring Security có mặt, Actuator endpoints có thể chịu security filter chain. Nếu tự định nghĩa SecurityFilterChain, cần bảo đảm management endpoints được bảo vệ đúng mà không vô tình khóa health probes hoặc mở metrics cho mọi caller.

Ví dụ minh họa một security chain riêng:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http)
            throws Exception {
        return http
                .securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(EndpointRequest.to("health"))
                        .permitAll()
                        .anyRequest().hasRole("OPS"))
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .anyRequest().authenticated())
                .build();
    }
}
~~~

Đây là ví dụ khung. Cần dependency Actuator/Security, authentication provider, matcher và thứ tự chain phù hợp. Nếu health endpoint cần probe truy cập không xác thực, chỉ permit endpoint/group cụ thể và cân nhắc network isolation. Không permit toàn bộ actuator paths chỉ để probe hoạt động.

Management port riêng không tự tạo security boundary trong Spring Security. Authorization vẫn cần được cấu hình và kiểm thử.

## 11. Metrics và Prometheus scrape qua management port

Nếu dùng Micrometer Prometheus registry và endpoint được expose, Prometheus có thể scrape management port:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  server:
    port: 8081
~~~

Prometheus target có thể trỏ tới order-service:8081/actuator/prometheus trong network nội bộ. Tên service/port phụ thuộc deployment manifest và service discovery.

Không expose metrics endpoint qua public ingress nếu không cần. Metrics có thể chứa tên service, route, dependency, JVM và business dimensions. Dù không chứa PII, vẫn có thể tiết lộ topology và behavior hệ thống.

Nếu application port và management port khác nhau, scrape config phải dùng management target. Health probe có thể dùng management port trong khi API traffic dùng application port.

## 12. Reverse proxy, ingress và port mapping

Trong container, server.port và management.server.port là port bên trong container. Host mapping, Kubernetes Service targetPort hoặc proxy upstream phải trỏ đúng listener.

Ví dụ Docker:

~~~bash
docker run -p 8080:8080 -p 8081:8081 order-service:latest
~~~

Ví dụ Kubernetes Service chỉ expose application port:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: order-service
spec:
  selector:
    app: order-service
  ports:
    - name: http
      port: 80
      targetPort: 8080
~~~

Management port không được đưa vào Service public này. Monitoring có thể truy cập trực tiếp Pod management port, dùng Service nội bộ riêng hoặc scrape discovery phù hợp.

Không tạo Ingress public tới management port nếu không có yêu cầu vận hành cụ thể và kiểm soát bảo mật đầy đủ. Ingress routing path không thay thế authentication/network policy.

## 13. Management port và graceful shutdown

Khi ứng dụng shutdown, management listener cũng thuộc cùng process lifecycle. Readiness nên chuyển sang trạng thái không nhận traffic trước khi instance dừng hoàn toàn nếu graceful shutdown được cấu hình.

Một quy trình phù hợp:
1. Instance bắt đầu shutdown.
2. Readiness chuyển sang refusing traffic.
3. Load balancer/service routing ngừng gửi request mới.
4. Server hoàn tất request đang chạy trong shutdown grace period.
5. Process dừng và management listener đóng.

Không dựa vào management port riêng để giữ health endpoint sống độc lập sau khi application process đã dừng. Listener cùng JVM nên đóng theo process lifecycle.

## 14. Troubleshooting management port

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| API hoạt động nhưng Actuator không truy cập được | Management port sai hoặc listener chưa bind | Startup logs, port config, process listener |
| Actuator vẫn chạy trên 8080 | management.server.port chưa được áp dụng | Profile/property source và effective config |
| Kubernetes probe connection refused | Port name/path sai hoặc bind loopback | Pod listener, probe targetPort, bind address |
| Probe trả 404 | Health group/path chưa bật hoặc base path đổi | Endpoint mapping và exposure |
| Probe trả 401/403 | Security chain chặn probe | Endpoint matcher và auth policy |
| Prometheus scrape timeout | Network policy, wrong port hoặc management server quá tải | Target, connectivity, scrape logs |
| Metrics endpoint trả 404 | Prometheus registry thiếu hoặc endpoint chưa exposed | Dependency, exposure include |
| Port mở nhưng response chậm | JVM CPU/GC/thread starvation | Process metrics, thread dump |
| TLS handshake failure | CA, certificate, hostname hoặc protocol mismatch | Certificate chain/truststore |
| Management port bị public | Service/Ingress expose nhầm | Service ports, ingress, firewall |
| Health xanh nhưng API không phục vụ | Management listener khỏe trong khi application path lỗi | Probe application port và business checks |
| Shutdown kéo dài | Graceful shutdown/readiness lifecycle | Shutdown phase logs và probe state |

### Quy trình điều tra

1. Xác nhận server.port, management.server.port và active profile.
2. Kiểm tra startup log cho biết management server chạy trên port nào.
3. Kiểm tra listener bind address và container port.
4. Gọi health endpoint từ cùng network path với probe/monitoring.
5. Kiểm tra base path, exposure và authorization.
6. Kiểm tra TLS nếu dùng HTTPS.
7. Kiểm tra Kubernetes Service, targetPort, NetworkPolicy và ingress.
8. Đối chiếu management health với application port và business request.
9. Kiểm tra metrics scrape và endpoint latency.

## 15. Tình huống thực tế: tách management port trong Kubernetes

**Bối cảnh:** order-service phục vụ API trên 8080. Platform yêu cầu health probes và Prometheus scrape dùng port nội bộ riêng, không qua public ingress.

### Bước 1 — cấu hình listener

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      exposure:
        include: health,prometheus
~~~

### Bước 2 — khai báo container ports

Khai báo 8080 cho HTTP và 8081 cho management. Đảm bảo application bind vào interface phù hợp với kubelet và monitoring agents.

### Bước 3 — cấu hình probes

Readiness/liveness dùng path Actuator tương ứng trên named port management. Xác minh health groups có mặt trong version và app configuration.

### Bước 4 — giới hạn network

Public Service chỉ target 8080. Management port được scrape qua Pod discovery hoặc internal-only Service. Network policy chỉ cho phép node/probe/monitoring sources cần thiết.

### Bước 5 — bảo vệ endpoint

Expose health và prometheus theo nhu cầu. Các endpoint khác không được publish. Cấu hình authorization hoặc network isolation phù hợp; không dựa vào port riêng như lớp bảo vệ duy nhất.

### Bước 6 — xác minh

- API request thành công trên application port.
- Probe health trả kết quả đúng trên management port.
- Prometheus scrape nhận metrics.
- Management port không đi qua public ingress.
- Pod readiness thay đổi đúng khi app không sẵn sàng.
- Liveness không restart pod chỉ vì dependency tạm thời lỗi ngoài phạm vi liveness.

**Kết quả mong muốn:** management traffic có đường truy cập riêng và được giới hạn, trong khi application traffic giữ routing bình thường.

## 16. Bài thực hành và câu hỏi tự kiểm tra

### Bài tập A — cùng port và port riêng

Chạy ứng dụng với management endpoints trên application port. Sau đó đặt management.server.port khác. So sánh URL, listener, startup logs và cách truy cập.

### Bài tập B — bind address

Bind management server vào 127.0.0.1 rồi thử truy cập từ container/network khác. Giải thích vì sao probe có thể thất bại. Chọn bind address và network controls phù hợp.

### Bài tập C — endpoint exposure và security

Expose health, info, metrics và prometheus trong môi trường test. Cấu hình Spring Security để health probe được truy cập theo policy và các endpoint vận hành khác yêu cầu role OPS. Kiểm thử 200/401/403/404.

### Bài tập D — Kubernetes probes

Cấu hình startup/readiness/liveness trên management port. Mô phỏng startup chậm, readiness failure và liveness failure. Xác nhận hành vi routing/restart đúng mong muốn.

### Bài tập E — TLS

Bật HTTPS cho management listener nếu phiên bản hỗ trợ. Kiểm tra certificate chain, hostname và Prometheus scrape TLS config. Không tắt xác minh certificate.

### Bài tập F — network isolation

Public Service chỉ expose application port. Tạo internal management path cho monitoring/probes. Kiểm tra không có ingress public tới actuator paths ngoài policy.

### Câu hỏi tự kiểm tra

1. Management port khác application port ở mục đích nào?
2. Khi nào nên dùng same port và khi nào cần separate port?
3. management.server.port ảnh hưởng listener nào?
4. Management base path khác port như thế nào?
5. Endpoint exposure có đồng nghĩa authorization không?
6. Vì sao bind 127.0.0.1 có thể làm Kubernetes probe thất bại?
7. Liveness và readiness khác nhau thế nào?
8. Vì sao không nên đưa mọi dependency vào liveness?
9. Management port riêng có phải process riêng không?
10. Cấu hình TLS management listener cần kiểm tra điều gì?
11. Làm sao bảo vệ Actuator bằng Spring Security?
12. Prometheus cần scrape management port hay application port?
13. Vì sao không nên expose management port qua public ingress?
14. Health xanh trên management port có chứng minh API business hoạt động không?
15. Làm thế nào kiểm tra management port trong Docker/Kubernetes?

**Tiêu chí hoàn thành:** cấu hình được same/separate management port; hiểu bind address và base path; phân biệt exposure/network/auth; cấu hình health probes; bảo vệ management endpoints; kết nối Prometheus; kiểm tra TLS, container networking và graceful shutdown.

## 17. Ghi nhớ

- Management port là listener phục vụ Actuator web endpoints; có thể dùng chung application port hoặc tách riêng.
- management.server.port cấu hình port management; server.port cấu hình application server.
- Port riêng không phải process riêng và không tự động bảo vệ endpoint.
- Exposure, authorization và network reachability là ba lớp khác nhau.
- Chỉ expose endpoint cần thiết; bảo vệ metrics và thông tin vận hành bằng security/network policy.
- Bind address phải tương thích với probe/monitoring network; loopback có thể khiến caller ngoài namespace không truy cập được.
- Readiness quyết định instance có nhận traffic hay không; liveness quyết định process có cần restart.
- Không để dependency tạm thời lỗi làm liveness fail nếu restart không giải quyết vấn đề.
- Cấu hình Kubernetes port names, probes, Service targetPort và NetworkPolicy khớp management listener.
- Management port riêng vẫn chia sẻ JVM resources và lifecycle với application server.
- Xác minh TLS, scrape target, shutdown behavior và application health trên đường truy cập thực tế.

## Tài liệu tham khảo

- [Spring Boot Reference — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Reference — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html)
- [Spring Boot Reference — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Boot Reference — Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.security)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
- [Kubernetes — Services](https://kubernetes.io/docs/concepts/services-networking/service/)

