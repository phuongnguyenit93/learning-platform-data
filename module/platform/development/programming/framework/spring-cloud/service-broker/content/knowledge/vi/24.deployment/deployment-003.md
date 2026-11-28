# Triển khai trên Cloud Foundry, máy chủ ứng dụng hoặc Kubernetes

Một service broker xây dựng bằng Spring Boot có thể được triển khai trên nhiều môi trường: Cloud Foundry, máy chủ ứng dụng Java hoặc Kubernetes. Môi trường triển khai quyết định cách đóng gói ứng dụng, cấp cấu hình, công bố endpoint, quản lý tiến trình, mở rộng và theo dõi sức khỏe. Dù chạy ở đâu, broker vẫn phải thực hiện cùng một hợp đồng Open Service Broker API (OSB API), duy trì trạng thái service instance và binding, xử lý operation bất đồng bộ, bảo vệ credentials và kết nối an toàn với provider.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, cần nhìn deployment theo hai lớp. Lớp runtime chịu trách nhiệm chạy ứng dụng Spring Boot và cung cấp network, configuration, secret, health check cùng khả năng phục hồi. Lớp broker chịu trách nhiệm catalog, provision, update, bind, unbind, deprovision và các quy tắc idempotency. Một deployment tốt bảo đảm platform truy cập được endpoint ổn định, các replica dùng chung trạng thái bền vững và một lần restart không làm mất operation đang xử lý.

Bài học này so sánh ba lựa chọn triển khai, hướng dẫn quy trình thực tế cho từng môi trường, giải thích cách đăng ký broker với platform tiêu thụ OSB, và đưa ra các tiêu chí vận hành production. Điểm cần phân biệt là **deploy ứng dụng broker** và **đăng ký broker với Cloud Foundry hoặc platform khác** là hai bước riêng biệt.

## 1. Kiến trúc tổng thể và trách nhiệm của từng lớp

Service broker là một HTTP service thực thi OSB API. Platform như Cloud Foundry gọi broker để đọc catalog và yêu cầu thao tác trên service instance hoặc binding. Broker sau đó giao tiếp với provider, lưu trạng thái và trả kết quả theo hợp đồng.

Runtime có thể là Cloud Foundry, một máy chủ Linux chạy executable JAR, một servlet container chạy WAR hoặc Kubernetes. Những môi trường này không thay đổi các endpoint OSB mà broker phải cung cấp.

~~~mermaid
flowchart TB
    Platform["OSB-compatible platform"] -->|"HTTPS / OSB API"| Edge["Route / Reverse proxy / Ingress"]
    Edge --> Runtime["Spring Boot broker runtime"]
    Runtime --> State[("Durable state database")]
    Runtime --> Secret["Secret manager"]
    Runtime --> Provider["Provider APIs"]
    State --> Queue["Outbox / operation queue"]
    Queue --> Worker["Background worker"]
    Worker --> Provider
    Worker --> Secret
~~~

Các thành phần có trách nhiệm:

| Thành phần | Trách nhiệm |
|---|---|
| Platform consumer | Đăng ký broker, đọc catalog, gửi request và theo dõi operation |
| Runtime | Khởi chạy process, cấp network, cấu hình và giám sát ứng dụng |
| Broker application | Triển khai OSB API, kiểm tra request, điều phối lifecycle |
| State database | Lưu instance, binding, operation, idempotency và outbox |
| Secret manager | Lưu credentials và secret reference |
| Provider adapter | Gọi API hoặc SDK của hệ thống cung cấp tài nguyên |
| Worker | Tiếp tục operation dài, retry và reconciliation |

Một broker chạy trong Cloud Foundry không tự động được đăng ký làm service broker trên foundation đó. Tương tự, một broker chạy trong Kubernetes không tự động được Kubernetes core tiêu thụ qua OSB API. Runtime host và platform consumer là hai vai trò độc lập.

## 2. So sánh ba lựa chọn triển khai

| Tiêu chí | Cloud Foundry | Máy chủ ứng dụng / máy chủ Java | Kubernetes |
|---|---|---|---|
| Đóng gói phổ biến | Executable JAR hoặc buildpack artifact | Executable JAR; WAR nếu là ứng dụng Servlet chạy trong servlet container | Container image |
| Quản lý process | Cloud Foundry runtime | systemd/service manager hoặc application server | Deployment/Pod controller |
| Công bố endpoint | Route và platform router | Reverse proxy/load balancer/DNS | Service, Ingress hoặc Gateway |
| Cấu hình | Environment variables, service bindings | Environment, file cấu hình, secret manager | ConfigMap, Secret, external secret manager |
| Health check | App health check của Cloud Foundry | systemd, load balancer, Actuator/monitoring | Startup, liveness, readiness probes |
| Scaling | Số app instances | Nhiều process/node và load balancer | Deployment replicas, HPA |
| Rolling update | Deployment strategy của Cloud Foundry | Blue-green hoặc rolling qua load balancer | Deployment rollout |
| Phù hợp | Tổ chức đã vận hành Cloud Foundry | Hệ thống có máy chủ Java hoặc quy trình ứng dụng hiện hữu | Hệ thống container và platform orchestration |

Không có lựa chọn tốt nhất cho mọi tổ chức. Hãy chọn theo năng lực vận hành, yêu cầu mạng, tiêu chuẩn bảo mật, cách quản lý database và secret, cũng như platform sẽ gọi broker.

Một nguyên tắc chung cho cả ba môi trường: broker API nên stateless giữa các process/replica; dữ liệu nghiệp vụ phải nằm trong kho bền vững dùng chung. Không dùng heap hoặc local filesystem của một instance làm nguồn dữ liệu duy nhất.

## 3. Chuẩn bị ứng dụng Spring Boot trước khi triển khai

Spring Cloud Open Service Broker cung cấp framework để xây dựng Spring Boot application triển khai OSB API. Starter hỗ trợ ứng dụng Spring MVC và Spring WebFlux. Trước khi triển khai, xác định rõ phiên bản Java, Spring Boot, Spring Cloud Open Service Broker và web stack tương thích.

Một ứng dụng broker thường cần:

- Endpoint OSB API và authentication cho platform-to-broker.
- Catalog service và service/plan definitions.
- ServiceInstanceService và ServiceInstanceBindingService.
- Provider adapter cho hệ thống đích.
- Repository hoặc state store bền vững.
- Cơ chế quản lý operation bất đồng bộ nếu có thao tác dài.
- Cấu hình TLS, secret, timeout và connection pool.
- Health endpoint và logging có redaction.

Ví dụ cấu hình port cho Spring Boot:

~~~yaml
server:
  port: ${PORT:8080}
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 25s
~~~

Giá trị PORT có thể được cấp bởi runtime như Cloud Foundry hoặc container environment. Khi chạy trên máy chủ độc lập, nếu không có PORT thì ứng dụng dùng cổng 8080. Trong môi trường thật, điều chỉnh timeout shutdown theo thời gian request/operation cần hoàn tất và giới hạn dừng process.

Không đưa password, token hoặc private key vào application.yml được commit lên repository. Dùng environment injection hoặc secret manager.

## 4. Đóng gói executable JAR

Executable JAR là cách triển khai đơn giản cho ứng dụng Spring Boot có embedded web server. Có thể chạy cùng một artifact trên máy phát triển, máy chủ Java, Cloud Foundry hoặc trong container.

Ví dụ build với Maven:

~~~bash
./mvnw clean package
~~~

Chạy thử:

~~~bash
java -jar target/service-broker.jar
~~~

Tên JAR tùy theo artifactId và version của dự án. Kiểm tra log startup, port, database connectivity và health endpoint trước khi triển khai.

Một số lưu ý:

- Dùng JRE phù hợp với Java version lúc build.
- Đóng gói đúng driver và dependency runtime.
- Tắt debug endpoint không cần thiết.
- Cấu hình JVM memory phù hợp với giới hạn của runtime.
- Không ghi dữ liệu instance hoặc operation vào thư mục tạm.
- Dùng graceful shutdown để ngừng nhận request mới và kết thúc request đang chạy trong giới hạn thời gian.
- Lưu artifact với version bất biến để có thể rollback.

Executable JAR thường là lựa chọn phù hợp cho Spring Boot MVC hoặc WebFlux khi runtime cho phép process tự quản lý embedded server.

## 5. Triển khai broker trên Cloud Foundry

Cloud Foundry có thể vừa là nơi chạy ứng dụng broker, vừa là platform tiêu thụ OSB API. Hai vai trò này cần được cấu hình riêng:

1. Deploy Spring Boot broker như một Cloud Foundry application.
2. Đăng ký endpoint ứng dụng đó làm service broker để Cloud Controller có thể gọi catalog và các operation OSB.

Cloud Foundry quản lý app process, route, memory, instances, environment và health check. Broker vẫn phải tự quản lý provider, state, idempotency và response OSB.

### 5.1. Chuẩn bị organization và space

Đăng nhập và target đúng nơi triển khai:

~~~bash
cf api https://api.example.com
cf login
cf target -o platform-services -s production
~~~

Xác nhận context:

~~~bash
cf target
~~~

Dùng space riêng cho broker production nếu chính sách tổ chức yêu cầu tách workload nền tảng. Cấp quyền deploy cho nhóm vận hành phù hợp; không dùng tài khoản cá nhân làm credential lâu dài của pipeline.

### 5.2. Tạo manifest cho ứng dụng broker

Ví dụ manifest.yml:

~~~yaml
applications:
  - name: spring-cloud-service-broker
    path: target/service-broker.jar
    instances: 2
    memory: 1G
    disk_quota: 1G
    buildpacks:
      - java_buildpack
    routes:
      - route: broker.example.com
    health-check-type: http
    health-check-http-endpoint: /actuator/health/readiness
    env:
      SPRING_PROFILES_ACTIVE: cloudfoundry
      SERVER_SHUTDOWN: graceful
~~~

Manifest trên minh họa các thuộc tính thường dùng; buildpack, route, health check và giới hạn tài nguyên cần điều chỉnh theo foundation. Một số foundation có thể tự phát hiện Java buildpack hoặc sử dụng buildpack khác. Không cố định tên buildpack nếu platform đã quản lý buildpack mặc định.

Cloud Foundry cung cấp PORT cho app instance. Ứng dụng phải lắng nghe trên cổng được runtime cấp. Có thể cấu hình Spring Boot bằng server.port=${PORT:8080} để chạy đúng trong cả Cloud Foundry và môi trường local.

Không đưa broker password hoặc provider token vào manifest được commit. Cấp secret qua service binding, secret management hoặc pipeline variable có kiểm soát. Nếu ứng dụng đọc credentials từ VCAP_SERVICES, cần triển khai phần tích hợp cấu hình tương ứng.

### 5.3. Push ứng dụng

Build artifact rồi push:

~~~bash
./mvnw clean package
cf push -f manifest.yml
~~~

Kiểm tra trạng thái:

~~~bash
cf app spring-cloud-service-broker
cf logs spring-cloud-service-broker --recent
cf routes
~~~

Xác nhận đủ số instance, route hoạt động, health check pass và ứng dụng truy cập được database cùng provider API.

Cloud Foundry hỗ trợ manifest để lưu cấu hình deploy nhất quán. Tham số truyền trực tiếp vào cf push có thể override một số giá trị manifest; cần quản lý manifest như một phần của release configuration.

### 5.4. Đăng ký ứng dụng làm service broker

Sau khi route HTTPS hoạt động và authentication được cấu hình, admin Cloud Foundry có thể đăng ký broker:

~~~bash
cf create-service-broker BROKER-NAME BROKER-USERNAME BROKER-PASSWORD https://broker.example.com
~~~

Đây là ví dụ cú pháp với placeholder, không phải thông tin xác thực thật. Tránh ghi password trực tiếp vào script hoặc command history. Dùng cơ chế credential injection được tổ chức phê duyệt và hạn chế quyền đọc.

Kiểm tra broker:

~~~bash
cf service-brokers
cf marketplace
~~~

Service plans có thể được quản lý quyền truy cập theo organization hoặc phạm vi platform. Admin cần enable service access cho các plan phù hợp trước khi developer có thể tạo instance.

Ví dụ, sau khi plan được công bố và cấp quyền:

~~~bash
cf create-service SERVICE-NAME PLAN-NAME INSTANCE-NAME
~~~

Lệnh này là thao tác tiêu thụ service của platform; nó khác với cf create-service-broker, vốn đăng ký endpoint broker với Cloud Foundry.

### 5.5. Cập nhật broker sau release mới

Khi thay artifact hoặc cấu hình:

~~~bash
cf push -f manifest.yml
~~~

Dùng rolling deployment hoặc blue-green theo khả năng foundation nếu cần giảm downtime. Nếu thay đổi schema database, bảo đảm phiên bản cũ và mới tương thích trong giai đoạn chuyển tiếp. Không chạy migration phá vỡ schema trong khi instance cũ còn nhận request hoặc worker đang xử lý operation.

Sau khi deploy, kiểm tra catalog, authentication và một luồng provision/bind thử nghiệm. Nếu route hoặc broker credentials thay đổi, cập nhật thông tin đăng ký theo quy trình quản trị của foundation.

## 6. Triển khai trên máy chủ Java độc lập

Một broker có thể chạy trên Linux VM hoặc máy chủ vật lý bằng executable JAR. Mô hình này phù hợp khi tổ chức đã có reverse proxy, load balancer, hệ thống quản lý process và secret management riêng.

Kiến trúc thường gồm:

- Java runtime cài trên máy chủ.
- Executable JAR được triển khai vào thư mục release versioned.
- systemd hoặc service manager giữ process.
- Reverse proxy/load balancer công bố HTTPS.
- Database và secret manager nằm ngoài process.
- Monitoring thu thập health, logs và metrics.

Không nên chạy broker bằng terminal session của người quản trị. Khi SSH session kết thúc, process có thể dừng hoặc khó kiểm soát. Dùng service manager để khởi động cùng hệ thống, restart khi lỗi và quản lý quyền process.

### 6.1. Tạo user và thư mục triển khai

Ví dụ trên Linux:

~~~bash
sudo useradd --system --home /opt/service-broker --shell /usr/sbin/nologin service-broker
sudo mkdir -p /opt/service-broker/releases
sudo chown -R service-broker:service-broker /opt/service-broker
~~~

Tách thư mục release, log và cấu hình. JAR nên được đặt trong thư mục versioned để rollback không cần ghi đè artifact đang chạy.

### 6.2. Cấu hình systemd

Ví dụ unit file /etc/systemd/system/service-broker.service:

~~~ini
[Unit]
Description=Spring Cloud Service Broker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=service-broker
Group=service-broker
WorkingDirectory=/opt/service-broker
EnvironmentFile=/etc/service-broker/service-broker.env
ExecStart=/usr/bin/java -XX:MaxRAMPercentage=75 -jar /opt/service-broker/current/service-broker.jar
SuccessExitStatus=143
Restart=on-failure
RestartSec=5
TimeoutStopSec=40
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
~~~

File environment có thể chứa profile, database URL và các tham số không nhạy cảm. Nếu chứa credentials, giới hạn quyền file, ví dụ chỉ root và service-broker đọc được; tốt hơn là dùng secret manager hoặc credential provider chuyên dụng.

Ví dụ lệnh quản lý:

~~~bash
sudo systemctl daemon-reload
sudo systemctl enable service-broker
sudo systemctl start service-broker
sudo systemctl status service-broker
~~~

Đọc log qua journal:

~~~bash
sudo journalctl -u service-broker -n 100 --no-pager
~~~

Không ghi credentials hoặc request payload nhạy cảm vào journal. Thiết lập log rotation, retention và quyền đọc log phù hợp.

### 6.3. Công bố HTTPS qua reverse proxy

Có thể dùng Nginx, HAProxy hoặc load balancer của tổ chức để terminate TLS và chuyển request tới Spring Boot process chạy ở loopback/private interface.

Ví dụ cấu hình Nginx rút gọn:

~~~nginx
server {
    listen 443 ssl;
    server_name broker.example.com;

    ssl_certificate     /etc/ssl/certs/broker.crt;
    ssl_certificate_key /etc/ssl/private/broker.key;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_connect_timeout 5s;
        proxy_read_timeout 120s;
    }
}
~~~

Đây là cấu hình minh họa. Cần bổ sung TLS policy, certificate rotation, request size limits, rate limiting và trusted proxy settings theo hạ tầng. Chỉ tin forwarded headers từ proxy đã được kiểm soát. Không expose cổng 8080 trực tiếp ra mạng công cộng nếu reverse proxy là lớp bảo vệ dự kiến.

OSB endpoint có thể thực hiện operation dài. Timeout ở proxy, load balancer, platform và broker phải được thiết kế đồng bộ. Với asynchronous operation, response tiếp nhận phải được trả nhanh theo OSB contract; worker tiếp tục thực hiện tác vụ sau đó.

## 7. Triển khai WAR trên servlet container

Nếu tổ chức yêu cầu deploy artifact vào một application server như Apache Tomcat, ứng dụng Spring Boot theo Servlet stack có thể được đóng gói thành WAR.

Cần lưu ý: tài liệu Spring Boot hiện hành nêu rõ WebFlux mặc định dùng embedded Reactor Netty và không hỗ trợ WAR deployment theo cách traditional servlet container. Vì vậy, mô hình WAR này áp dụng cho ứng dụng Servlet/MVC phù hợp; không áp dụng máy móc cho broker WebFlux.

### 7.1. Cấu hình SpringBootServletInitializer

Main application class:

~~~java
@SpringBootApplication
public class ServiceBrokerApplication
        extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(ServiceBrokerApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(ServiceBrokerApplication.class, args);
    }
}
~~~

Class này cho phép servlet container khởi tạo Spring Boot application thông qua Servlet initializer. Giữ main method nếu muốn WAR vẫn có thể chạy theo cách executable khi build tool hỗ trợ.

### 7.2. Cấu hình Maven WAR

Trong Maven, đổi packaging:

~~~xml
<packaging>war</packaging>
~~~

Đánh dấu embedded servlet container dependency là provided để container ngoài cung cấp servlet runtime:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
~~~

Nếu dùng Gradle, áp dụng WAR plugin và đưa runtime container dependency vào providedRuntime theo hướng dẫn Spring Boot. Không dùng compileOnly thay thế một cách tùy tiện vì có thể làm thiếu dependency trên test runtime.

Build:

~~~bash
./mvnw clean package
~~~

Kết quả là WAR trong target/. Deploy vào Tomcat hoặc servlet container tương thích với Servlet/Jakarta API mà phiên bản Spring Boot yêu cầu.

### 7.3. Vận hành trên application server

Khi deploy WAR, cần kiểm tra:

- Phiên bản Tomcat/servlet container tương thích với Spring Boot.
- Servlet API namespace và phiên bản Jakarta tương ứng.
- Context path của ứng dụng và URL broker đã đăng ký.
- Cấu hình datasource và connection pool.
- TLS termination và reverse proxy.
- Logging, thread pool và graceful shutdown.
- Cách rolling deployment hoặc restart container.
- Không để nhiều phiên bản ứng dụng cùng ghi schema không tương thích.

Nếu platform đã đăng ký URL có context path, thay đổi context path cần cập nhật broker registration hoặc route. Kiểm tra endpoint catalog sau khi deploy thay vì giả định ứng dụng luôn nằm ở root path.

## 8. Triển khai trên Kubernetes

Kubernetes phù hợp khi tổ chức vận hành container platform và cần rolling rollout, autoscaling, network policy hoặc quản lý workload theo declarative manifest.

Đóng gói broker thành image, sau đó dùng Deployment, Service và Ingress/Gateway. Database và secret nên nằm ngoài vòng đời Pod.

Một manifest Deployment rút gọn:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: service-broker
  namespace: service-broker
spec:
  replicas: 2
  selector:
    matchLabels:
      app: service-broker
  template:
    metadata:
      labels:
        app: service-broker
    spec:
      serviceAccountName: service-broker
      containers:
        - name: broker
          image: registry.example.com/platform/service-broker:1.0.0
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: kubernetes
            - name: SPRING_DATASOURCE_URL
              valueFrom:
                secretKeyRef:
                  name: service-broker-runtime
                  key: datasource-url
            - name: SPRING_DATASOURCE_USERNAME
              valueFrom:
                secretKeyRef:
                  name: service-broker-runtime
                  key: datasource-username
            - name: SPRING_DATASOURCE_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: service-broker-runtime
                  key: datasource-password
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: "1"
              memory: 1Gi
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            failureThreshold: 3
~~~

Đây là mẫu để minh họa, cần thêm securityContext, imagePullSecrets, topology spread, PDB, network policy và cấu hình TLS theo cluster. Tên Secret và key phải tồn tại trước khi Pod khởi chạy.

Service nội bộ:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: service-broker
  namespace: service-broker
spec:
  selector:
    app: service-broker
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

Ingress hoặc Gateway công bố HTTPS endpoint cho platform. Chỉ expose OSB API và các endpoint thực sự cần thiết; không expose Actuator management endpoint ra Internet.

### 8.1. Health probes và readiness

- Startup probe cho phép ứng dụng có đủ thời gian khởi động.
- Liveness probe kiểm tra process còn hoạt động để tiếp tục chạy.
- Readiness probe xác định Pod có thể nhận request mới hay chưa.

Không đưa provider API chậm vào liveness probe. Provider tạm thời unavailable không nên khiến Kubernetes restart toàn bộ broker Pod. Readiness có thể phụ thuộc database nếu broker không thể xử lý request an toàn khi mất state store; hãy tránh kiểm tra dependency quá rộng gây flapping.

### 8.2. Scaling và rollout

Khi tăng replicas, tất cả Pod phải dùng cùng database, idempotency store và operation records. Worker cần claim operation bằng lease hoặc cơ chế atomic khác để tránh xử lý trùng.

HPA có thể scale theo CPU hoặc custom metric. Tuy nhiên, giới hạn maxReplicas theo connection pool và rate limit provider. Rolling update cần tương thích schema database giữa phiên bản cũ và mới.

Triển khai và kiểm tra:

~~~bash
kubectl apply -f service-broker.yaml
kubectl rollout status deployment/service-broker -n service-broker
kubectl get pods,service,ingress -n service-broker
kubectl logs deployment/service-broker -n service-broker --since=15m
~~~

Kubernetes quản lý container và traffic, không tự động trở thành OSB consumer. Nếu một platform khác gọi broker, nó cần truy cập được endpoint HTTPS. Nếu Kubernetes cluster muốn tiêu thụ broker theo OSB, cần controller/client tích hợp OSB.

## 9. Cấu hình theo môi trường và quản lý secrets

Cùng một artifact nên có thể triển khai ở nhiều môi trường mà không phải build lại chỉ để đổi URL database hoặc provider token.

Có thể phân loại cấu hình:

| Dữ liệu | Ví dụ | Cách quản lý |
|---|---|---|
| Runtime | Port, profile, timeout, log level | Environment variable hoặc ConfigMap |
| Platform endpoint | Public broker URL, trusted proxy | Configuration theo môi trường |
| Database | JDBC/R2DBC URL, pool size | Environment và secret reference |
| Broker authentication | Username/password hoặc credential material | Secret manager |
| Provider credentials | Cloud token, API key, client certificate | Secret manager, rotation |
| TLS | Certificate, private key, truststore | Certificate manager/secret volume |
| Business state | Instance, binding, operation | Durable database |

Không commit secret vào manifest, Dockerfile, application.yml hoặc shell script. Kubernetes Secret có thể được mount hoặc inject nhưng cần encryption at rest và RBAC phù hợp. Trên Cloud Foundry, dùng service binding hoặc cơ chế secret của foundation; trên máy chủ, dùng secret manager hoặc file có quyền truy cập hạn chế.

Không ghi toàn bộ environment, VCAP_SERVICES hoặc object credentials vào log. Khi rotate provider token hoặc broker authentication, cần có quy trình cập nhật secret và rollout an toàn để tránh downtime.

## 10. Authentication và TLS giữa platform với broker

OSB API thường được platform gọi qua HTTPS và broker authentication theo cấu hình tích hợp. Cần thống nhất:

- Broker base URL.
- API version được hỗ trợ.
- Cơ chế xác thực platform-to-broker.
- TLS certificate và trust chain.
- Network allowlist hoặc private connectivity nếu áp dụng.
- Timeout và request size limit.
- Cách rotate broker credentials.

Cloud Foundry có thể lưu username/password khi admin đăng ký broker. Platform gửi thông tin xác thực khi gọi broker theo cơ chế mà integration hỗ trợ. Ứng dụng Spring cần cấu hình authentication filter/security phù hợp; không giả định chỉ vì app đã có HTTPS thì endpoint đã được bảo vệ.

Nếu dùng reverse proxy, xác định rõ TLS kết thúc ở proxy hay tại Spring Boot. Chỉ tin X-Forwarded-* từ proxy tin cậy. Không expose endpoint quản trị hoặc actuator nhạy cảm qua cùng route public.

## 11. Database, operation và idempotency trong mọi runtime

Deployment có thể thay thế process bất kỳ lúc nào. Cloud Foundry có thể restart app instance; systemd có thể restart service sau lỗi; Kubernetes có thể reschedule Pod. Do đó, broker không được phụ thuộc vào bộ nhớ tiến trình để giữ trạng thái cần thiết cho retry.

Các dữ liệu cần lưu bền vững:

- Service instance ID và provider resource ID.
- Service binding ID và provider principal ID.
- Operation ID, operation type, state và last operation result.
- Request fingerprint và idempotency key.
- Outbox event, retry schedule và worker lease.
- Secret reference thay vì secret plaintext.
- Audit metadata và correlation ID.

Khi platform retry provision vào replica khác, broker phải nhận diện request cũ và trả trạng thái/kết quả phù hợp. Khi worker restart giữa deprovision, operation phải được tiếp tục từ checkpoint. Nếu provider timeout sau side effect, cần reconciliation trước khi tạo hoặc xóa lại tài nguyên.

Không sử dụng sticky session như cách thay thế persistence. Sticky session không bảo đảm khi instance bị thay thế và không giúp worker khác đọc được operation.

## 12. Tách API process và background worker

Broker có thể xử lý operation dài theo hai mô hình:

**Một process**: API và worker chạy trong cùng ứng dụng. Dễ triển khai nhưng cần giới hạn worker concurrency, graceful shutdown và tránh mỗi replica xử lý cùng một job.

**Hai process/Deployment**: API nhận request và ghi operation/outbox; worker đọc queue/database và gọi provider. Có thể scale độc lập và kiểm soát tài nguyên riêng.

Trong cả hai mô hình:

1. Ghi operation và outbox bền vững trước khi trả response async.
2. Worker claim operation bằng lease hoặc atomic update.
3. Gọi provider bằng idempotency key ổn định.
4. Lưu provider operation/resource reference.
5. Retry theo policy có giới hạn.
6. Reconcile kết quả chưa xác định.
7. Cập nhật trạng thái để last_operation phản ánh đúng kết quả.

Không tạo background task chỉ bằng thread trong HTTP handler rồi trả async response. Process restart có thể làm mất task. Dùng database/outbox hoặc queue bền vững.

## 13. Health check, graceful shutdown và timeout

Mỗi runtime có cơ chế health check khác nhau, nhưng broker cần phân biệt ba khái niệm:

- **Process health**: JVM còn hoạt động và không bị kẹt.
- **Readiness**: broker có thể nhận request mới với các dependency bắt buộc.
- **Business operation health**: các operation đang chạy có tiến triển hay bị treo.

Không nên đưa tất cả provider dependency vào liveness. Một provider outage không đồng nghĩa JVM bị hỏng. Readiness có thể kiểm tra database state store, nhưng cần cân nhắc tác động nếu database tạm thời chậm.

Graceful shutdown nên:

1. Ngừng nhận request mới.
2. Chờ request đang xử lý trong thời hạn cho phép.
3. Worker ngừng claim operation mới.
4. Worker hoàn tất hoặc nhả lease cho operation đang chạy.
5. Đóng connection pool và client.
6. Thoát process trước khi runtime buộc dừng.

Timeout giữa platform, proxy, runtime và provider phải thống nhất. Nếu operation cần nhiều phút, dùng asynchronous flow của OSB thay vì giữ HTTP connection mở quá lâu.

## 14. Mở rộng và high availability

Mở rộng broker không chỉ là tăng số process. Cần tính cả database, provider quota, connection pool và worker concurrency.

| Thành phần | Cách mở rộng | Giới hạn cần tính |
|---|---|---|
| API | Nhiều app instances, server processes hoặc Pod replicas | CPU, memory, request concurrency |
| Worker | Nhiều worker consumer | Lease, provider rate limit, queue depth |
| Database | Connection pool, HA/replica, partition/index | Số connection, transaction contention, storage |
| Secret manager | Client pool/cache có kiểm soát | Rate limit, secret rotation, access policy |
| Provider | Adapter concurrency và backoff | Quota, API rate limit, operation duration |

Các runtime có cách thực hiện khác nhau:
- Cloud Foundry scale app instances bằng cấu hình hoặc CLI.
- Máy chủ độc lập scale bằng nhiều node/process sau load balancer.
- Kubernetes scale Deployment replicas hoặc HPA.

Không tăng API replicas vượt khả năng database. Một broker có thể nhận nhiều request hơn nhưng lại làm nghẽn provider hoặc state store. Đặt concurrency limit theo từng provider và từng tenant nếu cần.

## 15. Logging, metrics và audit khi triển khai

Mỗi môi trường cần thu thập log tập trung và metric đủ để chẩn đoán operation.

Các field hữu ích:
- operation ID và correlation ID dạng opaque.
- instance/binding reference đã được kiểm soát.
- operation type và state transition.
- provider adapter và provider request ID an toàn.
- duration, retry count và error category.
- runtime instance ID hoặc Pod name để xác định process.

Không ghi password, token, connection string, request body hoặc credentials object. Không dùng instance ID, tenant name hoặc email làm metric label có cardinality cao. Trace và exception message cũng cần được kiểm soát.

Audit nên ghi actor, thời điểm, operation và kết quả. Log access cần giới hạn theo vai trò và retention policy.

## 16. Quy trình release và rollback

Một release broker cần kiểm tra cả ứng dụng lẫn dữ liệu. Quy trình tổng quát:

1. Build artifact hoặc container image từ source revision xác định.
2. Chạy test và kiểm tra dependency/image.
3. Đưa cấu hình môi trường và secret vào hệ thống quản lý.
4. Kiểm tra migration schema theo hướng tương thích.
5. Deploy vào staging.
6. Kiểm tra health, catalog và authentication.
7. Chạy thử provision, bind, unbind, update và deprovision.
8. Kiểm tra async operation, retry và provider reconciliation.
9. Promote cùng artifact sang production.
10. Theo dõi lỗi, latency, operation backlog và provider failures.

Rollback ứng dụng không tự rollback database schema hoặc side effect ở provider. Dùng migration theo hướng expand/contract: thêm cấu trúc tương thích trước, deploy code mới, backfill, rồi mới loại bỏ cấu trúc cũ sau khi không còn phiên bản cũ sử dụng.

Với Cloud Foundry, dùng chiến lược rolling/blue-green phù hợp. Với máy chủ, deploy release directory mới rồi chuyển symlink/service configuration sau khi kiểm tra. Với Kubernetes, dùng Deployment rollout và giữ image version cũ để rollback.

Không rollback khi worker cũ và mới có cách diễn giải operation state không tương thích. Cần bảo đảm operation record và schema vẫn đọc được bởi phiên bản sẽ được khôi phục.

## 17. Kiểm tra deployment end-to-end

Một deployment chỉ được xem là sẵn sàng khi platform có thể gọi broker và broker thực hiện được lifecycle với provider.

Checklist kiểm thử:

| Bài kiểm tra | Kết quả mong đợi |
|---|---|
| DNS/route/Ingress | Platform truy cập được broker base URL |
| TLS | Certificate hợp lệ và hostname khớp |
| Authentication | Caller hợp lệ được phép; caller sai bị từ chối |
| Catalog | JSON đúng OSB API version và plan/capability |
| Provision | Instance được tạo và state được lưu bền vững |
| Async operation | Platform đọc last_operation cho đến kết quả cuối |
| Binding | Credentials được tạo và trả đúng consumer |
| Unbind | Đúng principal/credential bị thu hồi |
| Update | State và provider configuration được cập nhật |
| Deprovision | Tài nguyên được thu hồi và operation hoàn tất |
| Retry | Request lặp không tạo tài nguyên trùng |
| Restart | Operation tiếp tục sau khi process/Pod restart |
| Multi-replica | Request tới replica khác vẫn thấy cùng state |
| Secret rotation | Broker tiếp tục hoạt động sau khi credential được đổi |
| Rollback | Phiên bản cũ đọc được schema/operation tương thích |

Ngoài health endpoint, cần test từ chính mạng của platform consumer. Một request catalog thành công từ máy phát triển không chứng minh Cloud Controller hoặc platform production truy cập được route.

## 18. Lỗi triển khai thường gặp

**Chỉ deploy ứng dụng mà quên đăng ký broker.** Cloud Foundry có thể chạy app broker nhưng Cloud Controller chưa biết endpoint. Hoàn thành cả bước deploy app và create-service-broker.

**Để port cố định không phù hợp runtime.** Cloud Foundry cấp PORT động; cấu hình Spring Boot đọc biến môi trường đó.

**Dùng WAR cho WebFlux.** Spring Boot hiện hành không hỗ trợ traditional WAR deployment cho WebFlux. Dùng executable JAR hoặc container runtime phù hợp; chỉ dùng WAR cho Servlet stack tương thích.

**Lưu state trong local filesystem hoặc heap.** Restart hoặc scale làm mất dữ liệu. Dùng database/secret store bền vững.

**Đặt credentials trong manifest hoặc image.** Secret có thể lộ qua Git, image layer hoặc log. Dùng secret manager và quyền truy cập tối thiểu.

**Không cấu hình health check đúng endpoint.** Runtime có thể restart app đang khởi động hoặc route traffic vào app chưa sẵn sàng. Phân biệt liveness và readiness.

**Giữ HTTP request mở cho operation dài.** Proxy hoặc platform timeout. Dùng asynchronous operation theo OSB khi phù hợp.

**Scale worker không có lease/idempotency.** Nhiều process có thể cùng gọi provider. Dùng claim atomic, key ổn định và reconciliation.

**Rollback code nhưng bỏ qua migration.** Phiên bản cũ có thể không đọc được schema mới. Dùng migration tương thích và có kế hoạch rollback dữ liệu.

**Chỉ kiểm tra runtime health.** Process healthy không có nghĩa catalog hoặc provider adapter hoạt động. Test lifecycle OSB end-to-end.

## 19. Chọn môi trường theo nhu cầu vận hành

**Cloud Foundry** phù hợp khi tổ chức đã có foundation và muốn runtime quản lý route, app instances, staging, environment và log. Đây cũng là môi trường có thể đóng vai trò OSB consumer, nhưng việc deploy broker và đăng ký broker vẫn là hai thao tác riêng.

**Máy chủ ứng dụng** phù hợp khi hệ thống có Java application server hoặc quy trình vận hành VM hiện hữu. Executable JAR thường đơn giản cho Spring Boot; WAR dành cho ứng dụng Servlet cần triển khai vào servlet container. Với WebFlux, dùng executable JAR hoặc container thay cho WAR deployment truyền thống.

**Kubernetes** phù hợp khi tổ chức vận hành container orchestration và cần declarative deployment, autoscaling, network policy và rollout. Dùng Deployment cho broker API stateless, Service/Ingress/Gateway cho network, ConfigMap/Secret cho cấu hình và database bền vững cho state. Kubernetes chỉ là runtime trừ khi có controller/client được tích hợp để tiêu thụ OSB API.

Dù chọn môi trường nào, hãy bảo đảm broker có endpoint HTTPS ổn định, authentication rõ ràng, state store bền vững, operation có thể phục hồi và quy trình release/rollback đã kiểm thử.

## 20. Nguyên tắc triển khai trong Spring Cloud Service Broker

Triển khai broker như một Spring Boot application thực thi OSB API. Chọn executable JAR cho runtime quản lý process hoặc container; chọn WAR chỉ khi ứng dụng Servlet cần chạy trên servlet container tương thích. Trên Cloud Foundry, push ứng dụng bằng manifest rồi đăng ký route đó với Cloud Controller như một service broker. Trên máy chủ độc lập, dùng systemd/service manager và reverse proxy HTTPS. Trên Kubernetes, dùng Deployment, Service, Ingress/Gateway, probes và secret management.

Không phụ thuộc vào bộ nhớ của process để lưu instance, binding hoặc operation. Tất cả runtime cần dùng chung state database, idempotency records và outbox/queue bền vững. Tách API và worker khi cần scale riêng; cấu hình graceful shutdown, timeout và retry theo đặc tính provider.

Trước khi công bố broker, kiểm tra catalog, authentication, provision, binding, unbinding, update, deprovision, last_operation, retry và restart recovery từ mạng của platform consumer. Deployment hoàn chỉnh khi runtime ổn định, platform truy cập được endpoint và broker duy trì đúng lifecycle của tài nguyên qua restart, rollout và lỗi provider.

## Tài liệu tham khảo

- [Spring Cloud Open Service Broker](https://spring.io/projects/spring-cloud-open-service-broker/)
- [Spring Boot – Traditional Deployment](https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html)
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Cloud Foundry – Pushing an app with cf push](https://docs.cloudfoundry.org/devguide/deploy-apps/deploy-app.html)
- [Cloud Foundry – Deploying with app manifests](https://docs.cloudfoundry.org/devguide/deploy-apps/manifest.html)
- [Cloud Foundry – Managing Service Brokers](https://docs.cloudfoundry.org/services/managing-service-brokers.html)
- [Cloud Foundry – Rolling app deployments](https://docs.cloudfoundry.org/devguide/deploy-apps/rolling-deploy.html)
- [Kubernetes – Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes – Services](https://kubernetes.io/docs/concepts/services-networking/service/)
- [Kubernetes – Ingress](https://kubernetes.io/docs/concepts/services-networking/ingress/)
- [Kubernetes – Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)
- [Kubernetes – Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Open Service Broker API Specification](https://github.com/openservicebrokerapi/servicebroker/blob/master/spec.md)

