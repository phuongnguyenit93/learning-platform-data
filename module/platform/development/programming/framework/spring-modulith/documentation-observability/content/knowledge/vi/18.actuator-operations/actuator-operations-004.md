# Giới hạn endpoint chỉ trong mạng quản trị

## 1. Vì sao Actuator cần một mạng quản trị riêng?

Trong ứng dụng Spring Boot sử dụng **Spring Modulith**, các module như **order**, **payment** và **notification** có thể được theo dõi bằng health, metrics, module metadata và tracing. Spring Boot Actuator cung cấp endpoint để hệ thống vận hành đọc những thông tin đó. Một số endpoint còn tiết lộ cấu hình, bean, thread dump, log hoặc thông tin nội bộ của ứng dụng. Nếu các URL quản trị được công bố cùng đường truy cập công khai với API nghiệp vụ, người ngoài có thể thăm dò cấu trúc và trạng thái hệ thống.

Bài thuộc chương **Actuator và vận hành** của **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Module học này hướng dẫn dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác trong Spring Boot qua module graph, Actuator, event metrics, tracing và context propagation. Chủ đề trực tiếp ở đây là **giới hạn endpoint chỉ trong mạng quản trị**: tách cổng quản trị, bind đúng địa chỉ mạng, kiểm soát exposure, đặt security policy, giới hạn route ở hạ tầng và xác minh từ cả mạng được phép lẫn mạng bị cấm.

Sau bài học, bạn có thể:

1. Phân biệt endpoint **được đăng ký**, **được expose**, **được phép truy cập** và **có thể tới được qua mạng**.
2. Dùng `management.server.port` và `management.server.address` để tạo listener quản trị riêng.
3. Chỉ expose các endpoint cần thiết và đặt access level phù hợp.
4. Bảo vệ Actuator bằng Spring Security, firewall, security group, ingress và Kubernetes NetworkPolicy.
5. Giữ các probe cần thiết cho orchestrator mà không mở rộng toàn bộ bề mặt quản trị.
6. Kiểm thử đường truy cập từ mạng quản trị, mạng nghiệp vụ và mạng công khai.

## 2. Bốn lớp bảo vệ cần phối hợp

Một endpoint chỉ thực sự nằm trong mạng quản trị khi cấu hình ứng dụng và hạ tầng cùng giới hạn được đường truy cập. Chỉ đổi port hoặc chỉ thêm Spring Security chưa đủ nếu ingress vẫn chuyển tiếp request từ Internet.

~~~mermaid
flowchart TD
    Client["Client / Monitoring agent"] --> Network["Network boundary"]
    Network --> Bind["Management listener: address + port"]
    Bind --> Exposure["Actuator exposure allowlist"]
    Exposure --> Access["Endpoint access level"]
    Access --> Auth["Authentication + authorization"]
    Auth --> Endpoint["Health / Metrics / Modulith"]
    Public["Public Internet / user network"] -.->|Denied by firewall / policy| Bind
~~~

| Lớp | Câu hỏi cần trả lời | Cơ chế |
| --- | --- | --- |
| **Network reachability** | Ai có thể mở kết nối TCP đến cổng quản trị? | Private subnet, firewall, security group, NetworkPolicy, bind address. |
| **HTTP exposure** | Endpoint ID nào có URL HTTP? | `management.endpoints.web.exposure.include/exclude`. |
| **Endpoint access** | Client được đọc hay thay đổi dữ liệu? | `management.endpoints.access.default`, `management.endpoint.<id>.access`. |
| **Identity and authorization** | Ai được phép gọi endpoint? | Spring Security, OAuth2 Resource Server, mTLS hoặc cơ chế nội bộ. |

**Nguyên tắc:** dùng nhiều lớp độc lập. Firewall giảm số client có thể tới listener; exposure giảm số endpoint có URL; access giảm thao tác được phép; authentication/authorization xác định danh tính và quyền. Nếu một lớp cấu hình sai, các lớp còn lại vẫn giúp thu hẹp rủi ro.

## 3. Tách management port khỏi cổng nghiệp vụ

Mặc định, Actuator HTTP thường dùng chung cổng với server ứng dụng. Đặt `management.server.port` để tạo cổng quản trị riêng:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9090
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info,metrics,prometheus,modulith
~~~

Với cấu hình trên:

- API nghiệp vụ lắng nghe ở cổng **8080**.
- Actuator HTTP lắng nghe ở cổng **9090**.
- Đường dẫn mặc định của Actuator là `/actuator/{endpointId}`, trừ khi đã đổi base path hoặc path mapping.

Ví dụ địa chỉ:

~~~text
http://application-host:8080/api/orders
http://management-host:9090/actuator/health
http://management-host:9090/actuator/metrics
http://management-host:9090/actuator/modulith
~~~

**Cổng riêng không đồng nghĩa mạng riêng.** Nếu cả hai cổng đều bind trên `0.0.0.0` và firewall cho phép Internet truy cập 9090, endpoint quản trị vẫn công khai. Cần kết hợp bind address và chính sách mạng ở lớp hạ tầng.

Nếu ứng dụng không cần bất kỳ HTTP management endpoint nào, có thể tắt listener HTTP bằng `management.server.port: -1`. Đây là lựa chọn phù hợp khi chỉ dùng JMX hoặc một kênh quản trị khác; hãy xác nhận monitoring agent không còn phụ thuộc HTTP Actuator trước khi tắt.

### 3.1. Chỉ bind trên loopback khi chỉ quản trị tại cùng máy

Nếu ứng dụng chạy trực tiếp trên một máy và chỉ tiến trình cục bộ cần đọc Actuator:

~~~yaml
management:
  server:
    port: 9090
    address: 127.0.0.1
~~~

Lúc này management listener chỉ nhận kết nối trên loopback của máy đó. Một máy khác không thể gọi qua địa chỉ mạng LAN của host. Có thể dùng SSH tunnel hoặc một agent quản trị cục bộ để truy cập.

### 3.2. Bind trên interface nội bộ

Nếu máy chủ có interface dành riêng cho quản trị, có thể bind vào địa chỉ private cụ thể:

~~~yaml
management:
  server:
    port: 9090
    address: 10.20.5.12
~~~

Địa chỉ `10.20.5.12` chỉ là ví dụ; nó phải thực sự được gán cho interface của host/container tại thời điểm server khởi động. Nếu địa chỉ không tồn tại hoặc không thể bind, ứng dụng có thể không khởi động được.

**Điều kiện quan trọng:** Spring Boot chỉ cho phép bind management server vào địa chỉ khác server address khi management port khác server port. Nếu dùng chung port, không thể tạo một listener độc lập chỉ trên interface nội bộ bằng `management.server.address`.

### 3.3. Cổng quản trị có SSL riêng

Management server có thể có cấu hình SSL riêng khi dùng management port riêng:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
management:
  server:
    port: 9443
    ssl:
      enabled: true
~~~

Đây là ví dụ minh họa hai listener có SSL. Cấu hình key store/certificate và private key bằng secret manager hoặc mounted secret; không ghi secret trực tiếp vào repository. SSL bảo vệ nội dung và danh tính đầu cuối, nhưng **không thay thế network isolation**.

## 4. Chỉ expose endpoint cần thiết

Spring Boot mặc định chỉ expose `health` qua HTTP và JMX. Khi bật thêm endpoint, cần dùng allowlist nhỏ theo nhu cầu vận hành:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus,modulith
        exclude: shutdown,env,configprops,beans,heapdump,threaddump
~~~

Trong YAML, `include` và `exclude` nhận endpoint IDs, không phải URL path. `exclude` có ưu tiên cao hơn `include`. Không dùng `include: "*"` chỉ để tiện kiểm tra; nếu cần một endpoint mới, thêm đúng ID và đánh giá dữ liệu nó công bố.

### 4.1. Endpoint nào nên xem xét?

| Endpoint | Mục đích | Gợi ý phạm vi |
| --- | --- | --- |
| `health` | Trạng thái ứng dụng và health contributors. | Có thể cần cho orchestrator; giới hạn chi tiết và route. |
| `info` | Thông tin ứng dụng do cấu hình cung cấp. | Chỉ expose nếu không tiết lộ dữ liệu nhạy cảm. |
| `metrics` | Đọc meter và đo lường. | Chỉ mạng monitoring/admin. |
| `prometheus` | Scrape metrics cho Prometheus. | Chỉ Prometheus hoặc monitoring subnet. |
| `modulith` | Metadata application module và quan hệ phụ thuộc. | Chỉ mạng quản trị/kiến trúc. |
| `env`, `configprops` | Thông tin cấu hình và environment. | Tránh expose từ xa nếu không có nhu cầu đã được kiểm soát. |
| `beans`, `conditions` | Cấu trúc bean và auto-configuration. | Dùng trong chẩn đoán nội bộ, không expose công khai. |
| `heapdump`, `threaddump` | Dữ liệu chẩn đoán runtime có thể lớn hoặc nhạy cảm. | Hạn chế đặc biệt; chỉ bật trong quy trình sự cố. |
| `loggers`, `shutdown` | Thay đổi logging hoặc dừng ứng dụng. | Tránh mở rộng quyền; yêu cầu authorization nghiêm ngặt nếu bật. |

### 4.2. Đặt access level tường minh

Ở các phiên bản Spring Boot hỗ trợ endpoint access properties, có thể mặc định từ chối và chỉ mở read-only cho endpoint cần thiết:

~~~yaml
management:
  endpoints:
    access:
      default: none
  endpoint:
    health:
      access: read-only
    info:
      access: read-only
    metrics:
      access: read-only
    prometheus:
      access: read-only
    modulith:
      access: read-only
~~~

Endpoint phải vừa **được expose** qua HTTP vừa **được cho phép access** thì mới khả dụng. Access level không tự tạo authentication, cũng không thay firewall. Với Spring Boot 3.x cũ hơn hoặc các bản chưa hỗ trợ property này, cần kiểm tra đúng reference của version; dùng exposure và Spring Security để kiểm soát thay vì copy cấu hình không tương thích.

## 5. Bảo vệ bằng Spring Security

Nếu Actuator nằm trên mạng quản trị, vẫn nên yêu cầu danh tính hợp lệ. Ví dụ dưới đây dành cho ứng dụng Spring MVC/Spring Security servlet và giả định management endpoint được expose trên management listener.

Ứng dụng cần dependency Spring Security phù hợp, chẳng hạn `spring-boot-starter-security`. Ví dụ dùng HTTP Basic chỉ để minh họa; trong môi trường thật, hãy cấp role cho monitoring service account và operator theo danh tính riêng.

### 5.1. Dùng EndpointRequest thay vì hardcode path

`EndpointRequest` tạo matcher dựa trên các endpoint Actuator và base path được cấu hình. Điều này tránh bỏ sót endpoint khi đổi `management.endpoints.web.base-path`:

~~~java
package com.example.shop.security;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .anyRequest().hasRole("OPS"))
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Chain đầu tiên chỉ match Actuator endpoint và yêu cầu role `OPS`; chain thứ hai xử lý phần còn lại của ứng dụng. Thứ tự chain rất quan trọng: nếu một chain tổng quát bắt request trước, matcher cho Actuator có thể không được áp dụng như dự kiến.

Rule health được cho phép không cần đăng nhập để kubelet có thể gọi readiness/liveness probe; chỉ dùng cách này khi response health đã được giới hạn chi tiết, ví dụ `management.endpoint.health.show-details: never`, và cổng quản trị không thể truy cập từ mạng công khai. Nếu chính sách yêu cầu mọi request phải xác thực, cần chọn cơ chế probe phù hợp thay vì để probe thất bại.

Ví dụ dùng HTTP Basic để minh họa cơ chế authorization. Cần cấu hình danh tính có role `OPS`; user mặc định do Spring Boot tạo không tự có role này. Production nên tích hợp danh tính từ hệ thống phù hợp (ví dụ OAuth2 Resource Server, SSO hoặc mTLS ở proxy), quản lý secret an toàn và dùng HTTPS. Nếu dùng WebFlux, cần cấu hình `SecurityWebFilterChain` và `ServerWebExchangeMatcher` tương ứng; không copy servlet `SecurityFilterChain` vào reactive application.

### 5.2. Nếu có custom SecurityFilterChain, hãy quản lý toàn bộ rule

Khi Spring Security có trên classpath mà ứng dụng chưa khai báo `SecurityFilterChain`, Spring Boot có thể auto-configure quy tắc bảo vệ Actuator. Khi tự khai báo một `SecurityFilterChain`, cấu hình bảo mật mặc định của Boot sẽ nhường quyền kiểm soát; bạn phải định nghĩa đầy đủ rule cho cả Actuator và API nghiệp vụ.

Không tạo chain `permitAll()` cho toàn bộ Actuator chỉ vì cổng quản trị nằm trong subnet nội bộ. Mạng nội bộ có thể bị xâm nhập, bị cấu hình sai hoặc được dùng chung bởi workload không đáng tin cậy.

### 5.3. Tách role theo endpoint khi cần

Nếu monitoring agent chỉ cần scrape Prometheus còn operator cần đọc Modulith metadata, có thể tạo policy chi tiết hơn:

~~~java
@Bean
@Order(1)
SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher(EndpointRequest.toAnyEndpoint())
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(EndpointRequest.to("prometheus"))
                .hasRole("METRICS")
            .requestMatchers(EndpointRequest.to("health"))
                .hasAnyRole("OPS", "METRICS")
            .anyRequest().hasRole("OPS"))
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Đây là ví dụ chính sách theo endpoint, không phải cấu hình hoàn chỉnh cho mọi hệ thống. Hãy kết hợp chain còn lại cho API nghiệp vụ như mục trước, xác định cách cấp role cho service account và kiểm thử cả request thiếu danh tính lẫn sai role.

Đoạn này là **phương án thay thế method `actuatorSecurity` ở mục 5.1**, không khai báo thêm một chain trùng matcher và cùng thứ tự. Nếu muốn Prometheus scrape không dùng HTTP Basic, chỉ cho phép `prometheus` từ network/service account monitoring theo chính sách đã chọn; đừng vô tình cho phép mọi endpoint.

## 6. Network firewall và routing

Bind address giới hạn interface mà process lắng nghe. Firewall hoặc network policy giới hạn nguồn được phép kết nối tới interface đó. Cần cấu hình cả hai.

### 6.1. Máy chủ hoặc private cloud

Ví dụ policy logic:

| Nguồn | Đích | Cổng | Kết quả |
| --- | --- | ---: | --- |
| Monitoring subnet `10.20.0.0/16` | Management IP `10.20.5.12` | TCP 9090 | Allow |
| Bastion subnet `10.30.4.0/24` | Management IP `10.20.5.12` | TCP 9090 | Allow |
| Public Internet | Management IP `10.20.5.12` | TCP 9090 | Deny |
| User subnet | Management IP `10.20.5.12` | TCP 9090 | Deny |
| User subnet | Application IP | TCP 8080/8443 | Theo chính sách API nghiệp vụ |

Đây là mô hình minh họa; chọn CIDR theo mạng thực tế và nguyên tắc least privilege. Không chỉ chặn inbound ở host: kiểm tra cả cloud security group, load balancer, NAT, route table và firewall ở subnet.

### 6.2. Không đưa management port vào public load balancer

Nếu load balancer public chỉ cần chuyển API nghiệp vụ, chỉ khai báo listener/rule đến cổng ứng dụng. Không tạo rule path `/actuator/**` hoặc listener thứ hai đến management port. Kiểm tra cả ingress controller, API gateway, service mesh và reverse proxy; một route vô tình wildcard có thể làm endpoint quản trị xuất hiện trên hostname công khai.

Nếu cần scrape metrics từ bên ngoài cluster, dùng monitoring gateway/private connectivity/VPN có kiểm soát, hoặc một Collector/agent trong cùng mạng quản trị. Tránh publish cổng quản trị ra Internet chỉ vì Prometheus ở một network khác.

## 7. Docker: cổng quản trị không publish ra host công khai

Ứng dụng trong container thường cần bind management listener vào interface có thể nhận request từ mạng container. Nếu bind `127.0.0.1` bên trong container, một Prometheus/agent ở container khác không thể kết nối qua container IP.

Ví dụ cấu hình app trong Docker:

~~~yaml
server:
  port: 8080
management:
  server:
    port: 9090
    address: 0.0.0.0
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus,modulith
~~~

Chỉ bind `0.0.0.0` trong container không có nghĩa phải publish port ra host. Ví dụ Docker Compose có thể chỉ công bố cổng ứng dụng:

~~~yaml
services:
  shop:
    image: shop-modulith:latest
    ports:
      - "8080:8080"
    expose:
      - "9090"
    networks:
      - app-net
      - management-net

  prometheus:
    image: prom/prometheus:latest
    networks:
      - management-net

networks:
  app-net:
  management-net:
    internal: true
~~~

Trong ví dụ này, `expose` chỉ mô tả cổng nội bộ cho network; nó không publish cổng 9090 ra host như `ports`. Network `internal` giúp giới hạn kết nối bên ngoài theo khả năng của Docker network. Với môi trường thực, cần kiểm tra các network khác mà container `shop` tham gia; một network thứ hai có route ra ngoài vẫn có thể làm management port reachable từ workload cùng network.

## 8. Kubernetes: Service riêng và NetworkPolicy

Trong Kubernetes, một cách triển khai rõ ràng là:

- Pod mở application port và management port.
- Service public/internal cho API nghiệp vụ chỉ target application port.
- Service quản trị kiểu **ClusterIP** chỉ target management port.
- Không tạo Ingress public cho Service quản trị.
- NetworkPolicy chỉ cho phép monitoring namespace/pod và bastion workload cần thiết truy cập management port.

### 8.1. Deployment và Service

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: shop-modulith
  namespace: shop
spec:
  replicas: 2
  selector:
    matchLabels:
      app: shop-modulith
  template:
    metadata:
      labels:
        app: shop-modulith
    spec:
      containers:
        - name: app
          image: example/shop-modulith:1.0.0
          ports:
            - name: http
              containerPort: 8080
            - name: management
              containerPort: 9090
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: management
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: management
---
apiVersion: v1
kind: Service
metadata:
  name: shop-api
  namespace: shop
spec:
  selector:
    app: shop-modulith
  ports:
    - name: http
      port: 80
      targetPort: http
  type: ClusterIP
---
apiVersion: v1
kind: Service
metadata:
  name: shop-management
  namespace: shop
spec:
  selector:
    app: shop-modulith
  ports:
    - name: management
      port: 9090
      targetPort: management
  type: ClusterIP
~~~

Hai Service ở đây đều là `ClusterIP`; API nghiệp vụ có thể được expose qua Ingress/Gateway riêng theo yêu cầu. Service quản trị không được gắn với public ingress. Probe của kubelet gọi endpoint readiness/liveness trên Pod; nếu bind management vào loopback trong container, kubelet truy cập qua Pod IP có thể thất bại. Trong Pod, thường bind management vào interface phù hợp và dựa vào NetworkPolicy để giới hạn nguồn.

### 8.2. NetworkPolicy chỉ cho monitoring namespace

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-management-from-monitoring
  namespace: shop
spec:
  podSelector:
    matchLabels:
      app: shop-modulith
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: monitoring
          podSelector:
            matchLabels:
              app: prometheus
      ports:
        - protocol: TCP
          port: 9090
~~~

NetworkPolicy cần CNI hỗ trợ enforcement. Selector namespace và pod ở cùng phần tử `from` có nghĩa pod được chọn trong namespace được chọn. Nếu cần cho phép bastion hoặc probe/agent khác, thêm rule cụ thể và review theo least privilege. NetworkPolicy không tự cấu hình HTTP authentication; giữ Spring Security nếu endpoint chứa metadata nhạy cảm.

Kubelet thực hiện HTTP probe tới Pod IP. Cách node-originated traffic tương tác với NetworkPolicy có thể phụ thuộc CNI và nền tảng; xác minh probe thực tế không bị chặn sau khi áp policy. Nếu phải thêm ngoại lệ cho node/probe, giới hạn theo cơ chế mà CNI hỗ trợ và tiếp tục giữ management Service khỏi public ingress.

### 8.3. Không quên đường egress và node access

Một policy ingress chặn pod nguồn không đồng nghĩa management port không thể được truy cập từ mọi đường khác. Kiểm tra:

- CNI có thực thi NetworkPolicy hay không.
- NodePort/LoadBalancer/Ingress có expose management Service hoặc Pod port không.
- Host network, privileged DaemonSet, node-level agent hoặc port-forward có tạo đường truy cập riêng không.
- Monitoring namespace có thật sự chỉ chứa workload đáng tin cậy không.
- Egress rule của monitoring agent cho phép tới đúng management Service và không cần mở rộng tùy tiện.

## 9. Health probes: mở đúng phần cần thiết

Kubernetes thường cần health endpoints để kiểm tra readiness/liveness. Có thể bật health probes riêng:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus,modulith
~~~

`/actuator/health/liveness` và `/actuator/health/readiness` giúp phân biệt process còn sống với ứng dụng sẵn sàng nhận traffic. Không nên đưa các chi tiết health contributor nội bộ ra response công khai. Nếu cần endpoint health cho load balancer public, cân nhắc một health response tối giản riêng và giới hạn đường gọi; không vì probe cần health mà expose cả `metrics`, `env`, `beans` hoặc `modulith`.

Lưu ý về readiness: một dependency bên ngoài tạm thời không sẵn sàng không phải lúc nào cũng nên làm liveness thất bại. Nếu liveness phụ thuộc database/backend, Kubernetes có thể restart hàng loạt pod trong lúc dependency chung đang outage. Thiết kế health groups theo ý nghĩa phục hồi của hệ thống.

## 10. Kiểm thử từ mạng được phép và mạng bị cấm

Một cấu hình mạng quản trị chỉ được xác nhận khi kiểm tra cả positive và negative path. Thực hiện từ đúng môi trường mạng, không suy luận từ việc `curl localhost` trên máy developer.

### 10.1. Positive test từ management network

Từ Prometheus/monitoring pod hoặc bastion được cấp quyền:

~~~bash
curl -i http://shop-management.shop.svc.cluster.local:9090/actuator/health
curl -i http://shop-management.shop.svc.cluster.local:9090/actuator/metrics
~~~

Kỳ vọng: DNS resolve, TCP kết nối và endpoint trả response phù hợp với security policy. Nếu dùng Spring Security, client cần credentials hoặc workload identity hợp lệ.

### 10.2. Negative test từ user/public network

Từ một pod thuộc namespace không được phép hoặc một máy ngoài VPN:

~~~bash
curl --connect-timeout 3 -i \
  http://shop-management.shop.svc.cluster.local:9090/actuator/metrics
~~~

Kỳ vọng ở lớp mạng: kết nối bị timeout/refused hoặc không có route, tùy cách triển khai policy. Nếu request vẫn tới ứng dụng và nhận HTTP 401/403, Spring Security đã từ chối request nhưng network isolation chưa được chứng minh. Cần phân biệt hai lớp kết quả.

### 10.3. Kiểm tra public ingress

Gọi thử các path Actuator trên hostname công khai của ứng dụng:

~~~bash
curl -i https://api.example.com/actuator/health
curl -i https://api.example.com/actuator/modulith
curl -i https://api.example.com/actuator/env
~~~

Kỳ vọng: các đường dẫn quản trị không được route từ public ingress; thường trả 404/403 tại gateway hoặc không có route. Không chỉ kiểm tra status code: xác nhận response được tạo bởi ingress hay ứng dụng, vì 404 từ app vẫn chứng minh request đã đi đến app.

### 10.4. Kiểm tra listener và port thực tế

Trên host hoặc trong container, xác minh process đang lắng nghe đúng interface/port bằng công cụ phù hợp như `ss`, `netstat`, container inspect hoặc platform tooling. Kiểm tra không có listener ngoài dự kiến trên management port. Ghi lại bind address, service endpoints, firewall rules và network policy như bằng chứng cấu hình.

## 11. Những lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Management port vẫn truy cập từ Internet | Port 9090 được publish hoặc public firewall/ingress cho phép. | Bỏ public mapping/rule, giới hạn private subnet và kiểm tra lại từ bên ngoài. |
| `management.server.address` không có tác dụng | Management port trùng server port hoặc address không gán cho interface. | Dùng management port riêng và bind vào IP thực sự có trên host. |
| App chạy trong Docker nhưng monitoring container không kết nối được | Management bind vào `127.0.0.1` trong container. | Bind vào interface container phù hợp, dùng private network và không publish port ra host. |
| Kubernetes readiness probe thất bại | Management chỉ bind loopback, probe gọi Pod IP; sai port/path hoặc health group chưa bật. | Bind interface phù hợp trong Pod, xác minh named port và health probe path. |
| Service quản trị bị public | Ingress/Gateway/LoadBalancer trỏ nhầm vào management Service/port. | Tách Service, bỏ public route và kiểm tra targetPort. |
| Endpoint trả 404 | Chưa expose, sai base path, endpoint không có dependency hoặc gateway rewrite. | Kiểm tra endpoint ID, exposure, base path và app logs. |
| Endpoint trả 401/403 | Thiếu danh tính hoặc role không đúng. | Kiểm tra auth header/identity provider và authorization rule. |
| Custom SecurityFilterChain làm API khác bị mở | Boot security auto-config đã back off nhưng chain còn lại thiếu rule. | Khai báo chain cho Actuator và application, kiểm tra thứ tự. |
| `metrics` mở nhưng `modulith` không có | Modulith Actuator chưa có dependency hoặc endpoint chưa expose. | Kiểm tra starter/module Actuator và include list. |
| Prometheus scrape thất bại | NetworkPolicy không cho phép monitoring pod hoặc auth chưa cấu hình. | Cho phép đúng namespace/pod, thiết lập credentials phù hợp. |
| Health lộ component details | Health show-details cấu hình quá rộng. | Giới hạn details theo quyền và response public tối giản. |
| Chặn port ở host nhưng vẫn truy cập được | Có đường qua reverse proxy, service mesh, NodePort hoặc port-forward. | Kiểm tra toàn bộ đường route và policy ở từng lớp. |

## 12. Quy trình triển khai an toàn

~~~mermaid
flowchart TD
    A["Liệt kê endpoint và client quản trị"] --> B["Tách management port"]
    B --> C["Bind private interface"]
    C --> D["Allowlist endpoint IDs"]
    D --> E["Access level + Spring Security"]
    E --> F["Firewall / SG / Service / NetworkPolicy"]
    F --> G["Positive test từ monitoring"]
    G --> H["Negative test từ user/public"]
    H --> I{"Có đường truy cập ngoài dự kiến?"}
    I -->|Có| F
    I -->|Không| J["Ghi runbook và giám sát thay đổi"]
~~~

1. **Lập danh sách endpoint và client:** Prometheus, orchestrator probes, operator, automation hoặc support tooling.
2. **Tách management port:** xác định cổng nghiệp vụ và cổng quản trị riêng.
3. **Chọn bind address:** loopback nếu chỉ truy cập cục bộ; private interface/Pod interface nếu có agent ở mạng quản trị.
4. **Allowlist endpoint:** chỉ expose `health`, `metrics`, `prometheus`, `modulith` hoặc các ID thật sự cần.
5. **Đặt quyền và danh tính:** read-only khi phù hợp, role riêng cho monitoring/operator, TLS và secret management.
6. **Giới hạn route:** firewall/security group, private Service, ingress rule và NetworkPolicy.
7. **Chạy hai nhóm test:** client được phép phải truy cập được; client không được phép phải bị chặn ở lớp mạng và lớp ứng dụng.
8. **Lưu bằng chứng:** cấu hình bind/port, endpoint allowlist, security rules, kết quả positive/negative test và người sở hữu quyền.

## 13. Vận hành endpoint Module Actuator và metrics

Trong ứng dụng Spring Modulith, endpoint `modulith` có thể cung cấp metadata về application modules và dependency; `metrics`/`prometheus` có thể chứa tên module, event counters hoặc thông tin hiệu năng. Dữ liệu này giúp kiểm chứng kiến trúc và quan sát runtime nhưng cũng có thể tiết lộ package, tên module, công nghệ hoặc quy mô hệ thống.

Ví dụ allowlist cho monitoring:

~~~yaml
management:
  server:
    port: 9090
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,metrics,prometheus,modulith
  endpoint:
    health:
      show-details: never
~~~

Nếu Prometheus chỉ cần scrape metrics, có thể tách quyền:

- Service account của Prometheus được phép đọc `prometheus`.
- Operator có role `OPS` để đọc `health`, `metrics` và `modulith`.
- Endpoint nhạy cảm như `env`, `configprops`, `beans`, `heapdump`, `threaddump`, `shutdown` không expose qua HTTP trừ khi có quy trình đặc biệt.

Không để metrics label chứa dữ liệu cá nhân hoặc ID có cardinality cao. Giới hạn endpoint là một phần của bảo vệ telemetry; vẫn cần kiểm soát nội dung metrics, trace attributes và logs.

## 14. Checklist xác minh trước production

- [ ] `server.port` và `management.server.port` được tách nếu cần listener riêng.
- [ ] `management.server.address` bind vào đúng interface và khác server address chỉ khi port khác.
- [ ] Management port không được publish qua public load balancer/Ingress/NodePort.
- [ ] Endpoint exposure dùng allowlist; không bật `*` nếu không có lý do và kiểm soát phù hợp.
- [ ] Endpoint access mặc định được giới hạn theo khả năng của phiên bản Spring Boot.
- [ ] Spring Security có rule cho Actuator và rule riêng cho API nghiệp vụ.
- [ ] Monitoring agent/operator có danh tính và quyền tối thiểu.
- [ ] Firewall/security group/NetworkPolicy chỉ cho nguồn cần thiết.
- [ ] Health probe được giữ hoạt động mà không mở rộng toàn bộ Actuator.
- [ ] Positive test từ mạng quản trị thành công.
- [ ] Negative test từ user/public network bị chặn ở lớp mạng.
- [ ] Public ingress không chuyển tiếp các path quản trị.
- [ ] Response health không tiết lộ component details không cần thiết.
- [ ] Có logs/metrics theo dõi truy cập bị từ chối và thay đổi cấu hình mạng.
- [ ] Runbook ghi rõ owner, port, CIDR, Service, role và quy trình cấp/thu hồi quyền.

## 15. Tài liệu tham khảo chính thức

- **Spring Boot — Monitoring and Management Over HTTP:** https://docs.spring.io/spring-boot/reference/actuator/monitoring.html — management port, address, base path, SSL và tắt HTTP endpoints.
- **Spring Boot — Actuator Endpoints:** https://docs.spring.io/spring-boot/reference/actuator/endpoints.html — endpoint access levels, exposure allowlist và endpoint availability.
- **Spring Boot — Spring Security:** https://docs.spring.io/spring-boot/reference/web/spring-security.html — `SecurityFilterChain`, `EndpointRequest` và hành vi auto-configuration.
- **Spring Boot 3.5 — Actuator Endpoints:** https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html — exposure và security khi dùng Boot 3.5.
- **Kubernetes — Network Policies:** https://kubernetes.io/docs/concepts/services-networking/network-policies/ — giới hạn ingress/egress theo pod, namespace và port.
- **Kubernetes — Service:** https://kubernetes.io/docs/concepts/services-networking/service/ — ClusterIP và cách Service định tuyến đến Pod.
- **Spring Modulith — Production-ready Features:** https://docs.spring.io/spring-modulith/reference/production-ready.html — Module Actuator và metadata application module.

## 16. Tổng kết

Để **giới hạn endpoint chỉ trong mạng quản trị**, hãy phối hợp bốn lớp: **listener address/port**, **HTTP exposure**, **endpoint access và authentication/authorization**, cùng **network routing/firewall**. `management.server.port` tạo cổng riêng; `management.server.address` giới hạn interface khi port khác cổng ứng dụng; allowlist chỉ công bố endpoint cần thiết; Spring Security bảo vệ danh tính và quyền.

Khi triển khai Docker/Kubernetes, giữ management port trong private network, tách Service quản trị khỏi public Ingress và cho phép đúng monitoring workload qua NetworkPolicy. Luôn kiểm tra cả đường được phép và đường bị cấm. Endpoint health cần thiết cho probe không phải lý do để expose toàn bộ Actuator; Module Actuator, metrics và metadata kiến trúc nên chỉ đến được từ các client quản trị đã được xác định.
