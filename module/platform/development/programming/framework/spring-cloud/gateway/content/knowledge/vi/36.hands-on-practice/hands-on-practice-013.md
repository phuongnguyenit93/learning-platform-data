# Đóng gói, đo tải, theo dõi và diễn tập phục hồi gateway

## 1. Mục tiêu của bài thực hành

Trong module **SPRING_CLOUD_GATEWAY**, Gateway là cửa vào của các microservices. Một route có thể chạy đúng trên máy lập trình nhưng vẫn chưa sẵn sàng vận hành nếu image khó tái tạo, container chạy với quyền quá cao, không biết tải tối đa, không phát hiện được upstream chậm hoặc không phục hồi sau khi một instance bị lỗi.

Trong chương **Thực hành tổng hợp**, bài nối các năng lực route predicate, filter chain, path/header transformation, service discovery, authentication, rate limiting, circuit breaker, retry và TLS thành một quy trình triển khai/quan sát/phục hồi có thể đo lường.

Bài lab này đưa một Gateway WebFlux qua một vòng vận hành hoàn chỉnh:

1. **Đóng gói:** tạo executable JAR và OCI container image có thể tái tạo, chạy non-root, cấu hình tài nguyên và quản lý shutdown.
2. **Triển khai:** chạy local bằng Docker Compose, sau đó chuyển sang Kubernetes với probes, rolling update và PodDisruptionBudget.
3. **Đo tải:** tạo workload bằng Grafana k6, đo throughput, p95/p99 latency, lỗi và hành vi khi tăng tải.
4. **Theo dõi:** xuất metrics bằng Micrometer/Prometheus, xem dashboard Grafana, nối trace qua OpenTelemetry và log theo request.
5. **Diễn tập phục hồi:** chủ động làm chậm/tắt upstream, restart Gateway, mất Redis hoặc telemetry backend; quan sát retry, circuit breaker, alert và rollback.

Sau bài lab, bạn có thể bàn giao một image và một deployment có bằng chứng vận hành: dependency/build version, kết quả load test, dashboard, ngưỡng cảnh báo, kết quả recovery drill và hướng dẫn rollback.

> **Phạm vi ví dụ:** Spring Boot 4.x, Spring Cloud Gateway Server WebFlux 5.x, Java 17+, Docker/OCI, Kubernetes, Prometheus/Grafana và k6. Với Gateway 4.x, kiểm lại property prefix cũ và version tương ứng của Spring Cloud Release Train. Ví dụ trong bài dùng prefix mới **spring.cloud.gateway.server.webflux.***.

## 2. Kiến trúc lab và luồng dữ liệu

~~~mermaid
flowchart LR
    K["k6 load generator"] -->|HTTP :8080| G["Gateway replicas"]
    G -->|route /api/orders/**| O["orders-service"]
    G -->|metrics :9001| P["Prometheus"]
    P --> D["Grafana dashboards"]
    G -->|OTLP traces| T["OpenTelemetry Collector"]
    T --> V["Trace backend"]
    G --> L["Central log collector"]
~~~

- Client/k6 chỉ gọi **public listener** của Gateway.
- Gateway chuyển request tới orders-service.
- Management listener riêng cung cấp health và metrics cho hệ thống vận hành.
- Prometheus scrape từng Gateway instance; Grafana đọc Prometheus để vẽ dashboard.
- Traces được export tới OpenTelemetry Collector. Log được thu thập từ stdout hoặc agent theo hạ tầng.
- Trong Kubernetes, ingress/service public chỉ mở cổng HTTP ứng dụng; management port chỉ được phép từ probe và monitoring workloads.

### 2.1. Cây thư mục gợi ý

~~~text
gateway/
├── pom.xml
├── mvnw
├── .mvn/
├── .dockerignore
├── Dockerfile
├── compose.yaml
├── src/
│   └── main/
│       └── resources/
│           └── application.yml
└── ops/
    ├── prometheus/
    │   ├── prometheus.yml
    │   └── rules/
    │       └── gateway.yml
    ├── k6/
    │   └── gateway-load.js
    ├── grafana/
    │   └── dashboards/
    └── kubernetes/
        ├── gateway-deployment.yaml
        ├── gateway-service.yaml
        ├── gateway-pdb.yaml
        └── gateway-servicemonitor.yaml
~~~

Đây là cấu trúc để tổ chức bài lab; nếu dự án hiện tại đã có thư mục deployment/observability thì dùng cấu trúc sẵn có và giữ cùng một nguồn cấu hình.

### 2.2. Điều kiện đầu vào

- JDK 17 trở lên, Maven Wrapper hoặc Gradle Wrapper theo dự án.
- Docker Engine/BuildKit và Docker Compose plugin.
- Một Gateway WebFlux đã có route tới backend.
- Một backend test có endpoint ổn định, ví dụ GET /orders/42.
- Kubernetes cluster và kubectl cho phần triển khai cluster.
- Prometheus/Grafana hoặc stack tương đương.
- k6 CLI hoặc container k6.
- Nếu dùng tracing: OpenTelemetry Collector và trace backend như Tempo/Jaeger/Zipkin.

**Không chạy stress test vào production hoặc hệ thống không thuộc quyền kiểm soát.** Bắt đầu trong local/staging, đặt giới hạn tải và có người vận hành theo dõi.

## 3. Chuẩn hóa ứng dụng Gateway trước khi đóng gói

### 3.1. Dependencies cần có

Với Maven và Spring Cloud BOM đúng release train, các dependency cốt lõi thường là:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Nếu route dùng lb://SERVICE-ID, thêm spring-cloud-starter-loadbalancer và Discovery Client tương ứng. Nếu dùng JWT Resource Server, Redis RateLimiter, CircuitBreaker hoặc tracing, thêm đúng starter cho những chức năng thực sự được cấu hình. Không pin version riêng từng Spring Cloud artifact; để BOM quản lý.

### 3.2. Route và management listener

Ví dụ application.yml cho Gateway Server WebFlux 5.x:

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
  cloud:
    gateway:
      server:
        webflux:
          metrics:
            enabled: true
          httpclient:
            pool:
              metrics: true
          routes:
            - id: orders-api
              uri: http://orders:80
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1

management:
  server:
    port: 9001
  endpoints:
    web:
      exposure:
        include: health,prometheus,metrics
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
  metrics:
    tags:
      application: spring-cloud-gateway
      environment: lab
    distribution:
      percentiles-histogram:
        http.server.requests: true
        http.client.requests: true
  tracing:
    sampling:
      probability: 0.1
~~~

Giải thích:

- 8080 nhận traffic ứng dụng; 9001 dành cho management.
- server.shutdown: graceful và spring.lifecycle.timeout-per-shutdown-phase cho Spring thời gian hoàn tất request đang xử lý khi nhận tín hiệu shutdown.
- health, prometheus, metrics là các endpoint cần thiết trong lab. Không expose env, configprops, heapdump, gateway hoặc loggers ra public listener.
- management.endpoint.health.probes.enabled bật health groups cho startup/readiness/liveness.
- spring.cloud.gateway.server.webflux.metrics.enabled bật Gateway metrics filter theo namespace 5.x; httpclient.pool.metrics thu thập metrics connection pool.
- http.server.requests và http.client.requests là các metric/observation cần kiểm tra ở runtime. Tên meter cụ thể có thể khác theo phiên bản và registry; luôn xem /actuator/metrics trước khi viết PromQL.
- management.tracing.sampling.probability: 0.1 lấy mẫu 10% traces. Trong test ngắn có thể tăng tạm để quan sát; không mặc định lấy 100% mọi request production.

Với Gateway 4.x, property thường nằm dưới spring.cloud.gateway.*; kiểm BOM và configuration properties của release train đang dùng trước khi copy YAML.

### 3.3. Export trace bằng OpenTelemetry

Với Spring Boot 4, thêm spring-boot-starter-opentelemetry nếu chọn OTLP tracing. Ví dụ cấu hình endpoint của Collector:

~~~yaml
management:
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: http://otel-collector:4318/v1/traces
          transport: http
  tracing:
    sampling:
      probability: 0.1
~~~

Endpoint trên là ví dụ cho OTLP/HTTP. Nếu Collector dùng gRPC, TLS, auth header hoặc endpoint khác, cấu hình transport/SSL/headers tương ứng. Đặt credentials trong Secret hoặc secret manager, không commit token vào application.yml.

Spring Boot có thể tạo trace và propagate context khi dùng các client được auto-configure. Gateway WebFlux cũng có observation cho outbound HTTP. Kiểm tra trace thực tế qua Gateway → backend; nếu backend tự tạo client không instrumented hoặc xóa propagation headers thì trace có thể bị đứt.

### 3.4. Management port phải được bảo vệ

Tách port không tự động biến Actuator thành private. Cần:

- Không publish 9001 ra Internet/Ingress public.
- Chỉ cho Prometheus, Kubernetes probes và operator network được truy cập.
- Dùng Spring Security/network policy phù hợp với môi trường.
- Chỉ expose các endpoint cần thiết.
- Không để response health chứa hostname, credentials hoặc dependency details nhạy cảm.

Trong Docker Compose, management port chỉ cần nằm trên internal Compose network. Trong Kubernetes, dùng Service riêng cho management và NetworkPolicy giới hạn nguồn scrape.

## 4. Đóng gói OCI image

### 4.1. Dockerfile nhiều stage

Ví dụ Maven Wrapper, Java 17:

~~~dockerfile
# Pin các base image theo tag và digest trong pipeline production.
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace

COPY .mvn/ .mvn/
COPY mvnw pom.xml ./
RUN chmod +x mvnw
RUN ./mvnw -B dependency:go-offline

COPY src/ src/
RUN ./mvnw -B verify

FROM eclipse-temurin:17-jre AS runtime
WORKDIR /app

COPY --from=build --chown=10001:10001 /workspace/target/*.jar /app/app.jar

ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=75.0 -XX:+ExitOnOutOfMemoryError"

USER 10001:10001
EXPOSE 8080 9001

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Điểm quan trọng:

- Build stage chứa Maven và JDK; runtime stage chỉ chứa JRE và executable JAR.
- ./mvnw verify chạy test/verification trước khi image được tạo. Nếu dự án cần integration test có service phụ thuộc, tách profile test và chạy trong CI trước build image.
- USER 10001:10001 chạy ứng dụng bằng UID/GID không phải root. Runtime image không cần chmod hoặc ghi vào thư mục ứng dụng.
- MaxRAMPercentage giúp JVM tính heap theo giới hạn bộ nhớ container; giá trị 75% chỉ là điểm bắt đầu, cần đo heap/direct memory/metaspace và native overhead.
- ExitOnOutOfMemoryError làm process thoát khi OOM để orchestrator có thể restart; nó không thay resource sizing hay memory monitoring.
- ENTRYPOINT dạng exec giúp JVM nhận SIGTERM trực tiếp để graceful shutdown hoạt động.

Nếu dùng Gradle, thay build stage bằng Gradle Wrapper và copy artifact từ build/libs/. Không trộn ví dụ Maven vào dự án Gradle.

Dockerfile trên giả định dự án Maven một module và tạo một executable JAR trong target/. Với multi-module build, copy các POM module cần thiết trước bước dependency cache và chỉ rõ artifact Gateway cần đưa sang runtime stage.

### 4.2. .dockerignore

~~~text
.git
.gitignore
.idea
.vscode
*.iml
target/
build/
.env
.env.*
secrets/
*.log
.DS_Store
~~~

Không đưa .env, private key, local credentials, build cache hoặc repository metadata vào build context. Nếu build cần secret để tải dependency private, dùng BuildKit secret mount hoặc CI secret store; không dùng ARG/ENV để nhúng token vào image layer.

### 4.3. Build và kiểm tra image

~~~bash
docker build -t gateway-lab:local .
docker image inspect gateway-lab:local
docker history gateway-lab:local
~~~

Trong pipeline:

1. Chạy unit/integration tests trước khi build.
2. Pin base image bằng digest; dùng tag dễ đọc nhưng không dựa vào latest.
3. Sinh SBOM và scan CVEs cho image/dependencies.
4. Ký image và xác minh chữ ký ở bước deploy nếu supply-chain policy yêu cầu.
5. Đẩy image với immutable tag hoặc digest; không ghi đè tag release đã phát hành.
6. Lưu commit SHA, BOM versions, image digest và test report làm release evidence.

Docker multi-stage build giảm build tools trong runtime image, nhưng không tự bảo đảm image đã được vá. Cần cập nhật base image và rebuild định kỳ.

## 5. Chạy local bằng Docker Compose

### 5.1. Prometheus scrape config

Tạo ops/prometheus/prometheus.yml:

~~~yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - /etc/prometheus/rules/gateway.yml

scrape_configs:
  - job_name: spring-cloud-gateway
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - gateway:9001
~~~

Prometheus scrape management listener qua network nội bộ. Trong Kubernetes, không scrape một ClusterIP load-balanced như một target duy nhất nếu cần số liệu từng replica; dùng Pod discovery hoặc ServiceMonitor/PodMonitor.

### 5.2. Compose stack

Ví dụ compose.yaml:

~~~yaml
services:
  orders:
    image: traefik/whoami:v1.11
    expose:
      - "80"

  gateway:
    build:
      context: .
      dockerfile: Dockerfile
    image: gateway-lab:local
    ports:
      - "127.0.0.1:8080:8080"
    expose:
      - "9001"
    depends_on:
      - orders
    read_only: true
    tmpfs:
      - /tmp
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true

  prometheus:
    image: prom/prometheus:PINNED_VERSION
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.retention.time=7d
    ports:
      - "127.0.0.1:9090:9090"
    volumes:
      - ./ops/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./ops/prometheus/rules:/etc/prometheus/rules:ro
      - prometheus-data:/prometheus
    depends_on:
      - gateway

  grafana:
    image: grafana/grafana:PINNED_VERSION
    ports:
      - "127.0.0.1:3000:3000"
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: change-this-local-password
    volumes:
      - grafana-data:/var/lib/grafana
    depends_on:
      - prometheus

volumes:
  prometheus-data:
  grafana-data:
~~~

Thay PINNED_VERSION bằng tag/digest đã được kiểm thử của Prometheus và Grafana; đổi mật khẩu lab và không dùng mật khẩu mẫu ở môi trường chia sẻ. Các port Prometheus/Grafana được bind vào loopback để không mở cho mạng bên ngoài. Named volumes giữ dữ liệu Prometheus/Grafana qua lần recreate container.

traefik/whoami là backend demo trả thông tin request, không phải order service thật. Trong môi trường dự án, thay bằng orders-service có contract và health endpoint riêng. Route http://orders:80 cần khớp hostname/port service trong Compose.

### 5.3. Giữ route config nhất quán

Route orders-api đã khai báo trong application.yml ở mục 3.2. URI http://orders:80 dùng tên service trong Compose; trong Kubernetes, có thể dùng cùng tên nếu Service orders nằm trong namespace của Gateway. Không khai báo lại cùng route trong một profile riêng. Nếu cần profile local, chỉ override các thuộc tính thực sự khác môi trường và giữ một nguồn khai báo route.

Compose depends_on mặc định sắp thứ tự start container, không chứng minh backend đã sẵn sàng nhận request. Với backend thật, thêm healthcheck phù hợp rồi dùng depends_on condition service_healthy nếu image hỗ trợ; nếu không, xác minh Gateway/backend có retry/startup behavior phù hợp.

Khởi động:

~~~bash
docker compose up -d --build
docker compose ps
docker compose logs -f gateway
~~~

Kiểm tra:

~~~bash
curl -i http://localhost:8080/api/orders/42
curl -i http://localhost:9090/-/healthy
~~~

Management port 9001 không được publish ra host trong Compose trên. Prometheus vẫn scrape được qua DNS gateway:9001 bên trong network Compose. Nếu cần kiểm endpoint từ host, tạo port-forward/debug path tạm thời có kiểm soát, không publish management port công khai.

Mở Grafana ở http://localhost:3000, thêm Prometheus data source với URL http://prometheus:9090, rồi tạo dashboard ở mục 8.

## 6. Triển khai Gateway trên Kubernetes

### 6.1. Deployment với tài nguyên và health probes

Ví dụ gateway-deployment.yaml:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gateway
  namespace: app
spec:
  replicas: 3
  revisionHistoryLimit: 5
  minReadySeconds: 10
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: gateway
  template:
    metadata:
      labels:
        app: gateway
    spec:
      terminationGracePeriodSeconds: 45
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
      containers:
        - name: gateway
          image: registry.example.com/platform/gateway@sha256:REPLACE_WITH_DIGEST
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
            - name: management
              containerPort: 9001
          volumeMounts:
            - name: tmp-dir
              mountPath: /tmp
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: production
          resources:
            requests:
              cpu: 500m
              memory: 512Mi
            limits:
              cpu: "2"
              memory: 1Gi
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: management
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: management
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: management
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
      volumes:
        - name: tmp-dir
          emptyDir: {}
~~~

Thay digest bằng image đã ký/scan trong registry của tổ chức. CPU/memory requests và limits là giá trị khởi đầu cho lab, **không phải sizing production**. Đo heap, direct buffers, native memory, GC, CPU throttling và p95/p99 trước khi chốt.

Ý nghĩa probes:

- **Startup probe:** cho ứng dụng đủ thời gian khởi động. Trong khi startup probe chưa thành công, Kubernetes chưa chạy liveness/readiness probes.
- **Liveness probe:** phát hiện process bị kẹt hoặc không còn tiến triển và yêu cầu restart khi vượt ngưỡng lỗi.
- **Readiness probe:** quyết định Pod có được nhận traffic từ Service hay không. Nếu readiness fail, Pod bị loại khỏi endpoints sẵn sàng.
- **Liveness không nên phụ thuộc mọi backend:** nếu orders-service tạm mất, restart liên tục tất cả Gateway replicas có thể làm sự cố lan rộng. Readiness chỉ nên kiểm điều kiện thực sự cần để Pod nhận traffic; không đưa toàn bộ downstream vào readiness nếu Gateway vẫn phục vụ được những routes khác.

Startup/liveness/readiness ở ví dụ gọi management port 9001. Cần xác nhận Spring Boot đã bật health probes và management listener thực sự lắng nghe trên port đó.

### 6.2. Service public và management riêng

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: gateway
  namespace: app
  labels:
    app: gateway
spec:
  selector:
    app: gateway
  ports:
    - name: http
      port: 80
      targetPort: http
---
apiVersion: v1
kind: Service
metadata:
  name: gateway-management
  namespace: app
  labels:
    app: gateway
    monitoring: enabled
spec:
  type: ClusterIP
  selector:
    app: gateway
  ports:
    - name: management
      port: 9001
      targetPort: management
~~~

Ingress chỉ trỏ tới Service gateway port 80. Service management là ClusterIP riêng, không tạo Ingress public. NetworkPolicy cần giới hạn port 9001 cho namespace monitoring và các nguồn probe/operator được phép; quy tắc chính xác phụ thuộc CNI và cluster networking.

### 6.3. PodDisruptionBudget và autoscaling

Với Deployment có ba replicas, có thể dùng PDB:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: gateway
  namespace: app
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: gateway
~~~

PDB hạn chế voluntary disruptions làm số Pod sẵn sàng giảm dưới hai. PDB không ngăn mọi lỗi đồng thời, node failure hoặc mọi cách xóa Pod; nó cũng không thay rolling update strategy và replica count.

HPA là tùy chọn khi đã có metrics-server và load test xác định scaling behavior:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: gateway
  namespace: app
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: gateway
  minReplicas: 3
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
~~~

CPU 70% là ví dụ, không phải ngưỡng tối ưu cho mọi Gateway. HPA cần CPU requests để tính utilization. Khi test autoscaling, tạo đủ thời gian cho metrics collection, scale-up stabilization và Pod startup; đừng đánh giá chỉ sau vài giây tăng tải.

### 6.4. Prometheus Operator ServiceMonitor

Nếu cluster dùng Prometheus Operator, ServiceMonitor có thể scrape management Service:

~~~yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: gateway
  namespace: monitoring
  labels:
    release: prometheus
spec:
  namespaceSelector:
    matchNames:
      - app
  selector:
    matchLabels:
      monitoring: enabled
  endpoints:
    - port: management
      path: /actuator/prometheus
      interval: 15s
      scrapeTimeout: 5s
~~~

Label selector phải khớp cấu hình Prometheus Operator của cluster. ServiceMonitor là CRD; nếu không cài Prometheus Operator, dùng Prometheus Kubernetes service discovery/Pod discovery tương đương. Xác nhận từng replica được scrape, không chỉ một địa chỉ Service load-balanced.

Triển khai các manifest core và kiểm tra endpoints:

~~~bash
kubectl apply -f ops/kubernetes/gateway-deployment.yaml
kubectl apply -f ops/kubernetes/gateway-service.yaml
kubectl apply -f ops/kubernetes/gateway-pdb.yaml
kubectl rollout status deployment/gateway -n app
kubectl get pods,svc,endpointslices -n app
~~~

Chỉ apply ServiceMonitor khi Prometheus Operator CRD đã được cài và label selector khớp Prometheus instance:

~~~bash
kubectl apply -f ops/kubernetes/gateway-servicemonitor.yaml
~~~

Để chạy k6 từ máy lập trình, mở port-forward ở một terminal riêng:

~~~bash
kubectl port-forward service/gateway 8080:80 -n app
~~~

### 6.5. Graceful shutdown và rolling update

Khi rollout hoặc node drain:

1. Pod bắt đầu termination; Kubernetes cập nhật trạng thái endpoint để traffic mới dần ngừng đi vào Pod.
2. Container nhận SIGTERM.
3. Spring Boot graceful shutdown ngừng nhận request mới và chờ request đang xử lý trong giới hạn đã cấu hình.
4. Sau terminationGracePeriodSeconds, Kubernetes có thể kill process còn chạy.

Ở ví dụ, Spring có 30 giây cho shutdown phase và Pod có 45 giây termination grace. Chừa thời gian cho endpoint propagation và shutdown. Kiểm thử với request dài/streaming; không giả định mọi client/proxy đều giữ kết nối vô hạn.

## 7. Đo tải bằng Grafana k6

### 7.1. Xác định mục tiêu trước khi chạy

Một load test chỉ có ý nghĩa khi biết câu hỏi cần trả lời:

- Gateway phục vụ được bao nhiêu requests/second ở latency mục tiêu?
- Khi tăng concurrency, p95/p99 bắt đầu vượt SLO ở mức nào?
- 5xx, timeout hoặc 429 xuất hiện ở mức tải nào?
- CPU, heap, direct memory và connection pool tăng ra sao?
- Backend hay Gateway trở thành bottleneck trước?
- Khi một backend instance mất, throughput/latency thay đổi thế nào?

Đặt SLO thử nghiệm ban đầu để minh họa:

| Chỉ số | Ngưỡng lab minh họa |
| --- | --- |
| p95 request latency | dưới 300 ms |
| p99 request latency | dưới 800 ms |
| HTTP failures ngoài dự kiến | dưới 1% |
| Check hợp đồng response | ít nhất 99% thành công |
| Gateway replicas | không restart/OOM trong bài load ổn định |

Đây là ngưỡng khởi đầu để luyện cách đo, không phải cam kết SLA. Hãy thay bằng SLO thật của API, traffic mix, payload size và backend.

### 7.2. Script k6 với smoke/load/stress/soak profiles

Tạo ops/k6/gateway-load.js:

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

const baseURL = __ENV.BASE_URL || 'http://localhost:8080';
const profile = __ENV.PROFILE || 'smoke';

const profiles = {
  smoke: [
    { duration: '30s', target: 2 },
    { duration: '1m', target: 2 },
    { duration: '15s', target: 0 },
  ],
  load: [
    { duration: '2m', target: 10 },
    { duration: '5m', target: 10 },
    { duration: '2m', target: 0 },
  ],
  stress: [
    { duration: '2m', target: 20 },
    { duration: '2m', target: 40 },
    { duration: '2m', target: 80 },
    { duration: '1m', target: 0 },
  ],
  soak: [
    { duration: '5m', target: 20 },
    { duration: '30m', target: 20 },
    { duration: '5m', target: 0 },
  ],
};

export const options = {
  scenarios: {
    gateway_traffic: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: profiles[profile] || profiles.smoke,
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<300', 'p(99)<800'],
    checks: ['rate>0.99'],
  },
};

export default function () {
  const response = http.get(baseURL + '/api/orders/42', {
    headers: {
      Accept: 'text/plain, application/json',
    },
    tags: {
      route: 'orders-api',
    },
  });

  check(response, {
    'Gateway returns HTTP 200': (r) => r.status === 200,
    'response body is not empty': (r) => r.body && r.body.length > 0,
  });

  sleep(1);
}
~~~

Giải thích:

- **smoke:** xác nhận route, auth và backend hoạt động ở tải nhỏ.
- **load:** giữ tải dự kiến trong vài phút để quan sát latency và resource usage.
- **stress:** tăng tải từng bậc để tìm điểm bão hòa; đánh dấu test không đạt khi vượt threshold. Nếu cần abort sớm, cấu hình abortOnFail cho threshold theo tài liệu k6.
- **soak:** giữ tải lâu để tìm memory growth, connection leak, queue buildup hoặc degradation theo thời gian.
- Thresholds làm k6 trả exit code thất bại khi không đạt ngưỡng. Checks chỉ ghi nhận assertions; nếu muốn check fail cả test run, phải đặt threshold cho metric checks như ví dụ.
- Script dùng ramping VUs, một closed workload model. Khi response chậm, VU giữ lâu hơn và tốc độ request có thể giảm. Nếu cần kiểm tra một arrival rate cố định, dùng constant-arrival-rate executor và theo dõi dropped_iterations.

Các ngưỡng p95/p99 trong script phải khớp mục tiêu lab. Nếu backend demo hoặc môi trường local chậm hơn, hãy điều chỉnh sau khi ghi rõ lý do; không nới ngưỡng chỉ để có kết quả xanh.

### 7.3. Chạy các profiles

Từ PowerShell:

~~~powershell
$env:BASE_URL = 'http://localhost:8080'
$env:PROFILE = 'smoke'
k6 run .\ops\k6\gateway-load.js

$env:PROFILE = 'load'
k6 run .\ops\k6\gateway-load.js

$env:PROFILE = 'stress'
k6 run .\ops\k6\gateway-load.js

$env:PROFILE = 'soak'
k6 run .\ops\k6\gateway-load.js
~~~

Trên Linux/macOS:

~~~bash
BASE_URL=http://localhost:8080 PROFILE=smoke k6 run ops/k6/gateway-load.js
BASE_URL=http://localhost:8080 PROFILE=load k6 run ops/k6/gateway-load.js
BASE_URL=http://localhost:8080 PROFILE=stress k6 run ops/k6/gateway-load.js
BASE_URL=http://localhost:8080 PROFILE=soak k6 run ops/k6/gateway-load.js
~~~

Nếu chạy k6 trong container, gắn script vào container và kết nối vào đúng Compose/Kubernetes network. Không dùng localhost bên trong container để gọi Gateway container khác; dùng service DNS hoặc địa chỉ port-forward phù hợp.

### 7.4. Đo arrival rate cố định khi cần

Nếu yêu cầu là “Gateway phải chịu được 100 request bắt đầu mỗi giây”, VU ramp không mô hình hóa chính xác mục tiêu đó. Có thể dùng scenario riêng:

~~~javascript
export const options = {
  scenarios: {
    fixed_rate: {
      executor: 'constant-arrival-rate',
      rate: 100,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 50,
      maxVUs: 200,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<300', 'p(99)<800'],
    dropped_iterations: ['count==0'],
  },
};
~~~

Đây là cấu hình thay thế cho khối export const options trong script chính, không khai báo đồng thời hai biến options. Cần cấp đủ VUs để k6 duy trì arrival rate; nếu không, dropped_iterations tăng và test không còn tạo đúng tải mong muốn. Load generator cũng phải đủ CPU/network để không trở thành bottleneck.

### 7.5. Quy trình chạy load test có kiểm soát

1. Ghi version image, config, số Gateway replicas và backend replicas.
2. Kiểm tra smoke test trước.
3. Warm-up để JVM JIT, connection pool và caches ổn định.
4. Chạy load test với một traffic mix cố định.
5. Ghi kết quả k6 và snapshot Prometheus/Grafana cùng khoảng thời gian.
6. Lặp lại với một biến thay đổi mỗi lần: replicas, CPU, pool, timeout hoặc backend capacity.
7. Chạy stress test có giới hạn thời gian/concurrency và người theo dõi.
8. Chạy soak test sau khi load test đã ổn định.
9. Lưu test script, environment, image digest, raw output và kết luận.

Khi test rate limiter, 429 có thể là kết quả **đúng theo policy** chứ không phải lỗi hệ thống. Tạo scenario riêng cho quota behavior, xác định response 429/Retry-After mong muốn và cấu hình expected-status/checks phù hợp. Đừng gộp 429 dự kiến vào baseline success test rồi kết luận hệ thống lỗi.

### 7.6. Đọc kết quả

| Kết quả | Cách diễn giải ban đầu |
| --- | --- |
| Throughput tăng, p95 ổn định | Còn headroom ở mức tải đó |
| p95 tăng trước p99 rất mạnh | Một phần requests đang bị queueing/chậm |
| p99 tăng, p50 ổn định | Tail latency hoặc một nhóm backend instance có vấn đề |
| 5xx tăng cùng connect timeout | Kiểm network, backend listener, pool và timeout |
| 429 tăng đúng ngưỡng quota | Rate limiter đang enforce policy |
| CPU throttling cao | Container CPU limit có thể quá thấp |
| Heap/direct memory tăng liên tục | Kiểm body buffering, pool, leak và workload |
| Pending connections tăng | Kiểm pool capacity, backend latency và concurrency |
| Gateway ổn nhưng backend quá tải | Tăng capacity backend hoặc giới hạn tải ở Gateway |

Không kết luận bottleneck từ một metric đơn lẻ. Đối chiếu k6, Gateway metrics, backend metrics, traces và resource metrics trong cùng time window.

## 8. Theo dõi bằng Prometheus, Grafana, traces và logs

### 8.1. Xác nhận metrics thực sự được xuất

Sau khi ứng dụng chạy, kiểm tra endpoint nội bộ:

~~~bash
curl -s http://localhost:9001/actuator/health
curl -s http://localhost:9001/actuator/metrics
curl -s http://localhost:9001/actuator/metrics/http.server.requests
curl -s http://localhost:9001/actuator/metrics/http.client.requests
curl -s http://localhost:9001/actuator/prometheus
~~~

Nếu metric không tồn tại:

1. Kiểm dependency Actuator và Micrometer registry.
2. Kiểm endpoint đã được expose chưa.
3. Kiểm Gateway metrics/observability đã bật trong đúng namespace version chưa.
4. Gửi request qua Gateway rồi kiểm lại; một số meter chỉ xuất hiện sau khi có traffic.
5. Dùng tên meter từ Actuator metrics endpoint để viết dashboard, không đoán tên từ Prometheus normalized name.

Các meter thường cần theo dõi:

| Metric | Ý nghĩa vận hành |
| --- | --- |
| http.server.requests | Request đến Gateway, status, method, route/URI tags tùy instrumentation |
| http.client.requests | Request outbound từ Gateway tới upstream |
| spring.cloud.gateway.requests | Gateway metrics filter ở các version có meter này |
| jvm.memory.used / jvm.gc.pause | Heap/GC behavior |
| process.cpu.usage / system.cpu.usage | CPU pressure |
| application.ready.time | Thời gian ứng dụng đạt trạng thái ready |
| HTTP client pool metrics | Active/idle/pending connections và acquire pressure khi bật pool metrics |

Không phải mọi version/runtime đều xuất cùng một tập meter. Gateway 5.x có Gateway HTTP client observation tên http.client.requests; các metric Gateway-specific khác phụ thuộc filter/version. Kiểm endpoint trước khi dùng PromQL.

### 8.2. PromQL mẫu

Tỷ lệ request HTTP 5xx trong 5 phút, nếu Prometheus đã scrape histogram/counter của http.server.requests:

~~~promql
sum(rate(http_server_requests_seconds_count{
  application="spring-cloud-gateway",
  status=~"5.."
}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    application="spring-cloud-gateway"
  }[5m])),
  1
)
~~~

p95 latency tổng hợp:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      application="spring-cloud-gateway"
    }[5m])
  )
)
~~~

Request rate:

~~~promql
sum(rate(http_server_requests_seconds_count{
  application="spring-cloud-gateway"
}[1m]))
~~~

Tên series/labels phụ thuộc Micrometer naming convention và common tags của ứng dụng. Nếu metric của bạn dùng prefix khác, thay tên theo dữ liệu thật ở Prometheus Explore. Không copy query rồi kết luận “không có traffic” khi label application/uri khác.

### 8.3. Dashboard Grafana nên có

Tạo dashboard theo từng nhóm câu hỏi:

| Row/panel | Nội dung | Câu hỏi cần trả lời |
| --- | --- | --- |
| Traffic | Requests/sec theo route/method | Traffic đang tăng ở route nào? |
| Status | 2xx/4xx/5xx/429 | Lỗi do backend, quota hay client? |
| Latency | p50/p95/p99 | Đuôi latency bắt đầu xấu ở thời điểm nào? |
| Upstream | http.client.requests theo service/route | Gateway hay backend đang chậm? |
| Connection pool | Active/idle/pending/acquire timeout | Gateway đang thiếu connection hay backend đang giữ connection lâu? |
| JVM | Heap, non-heap, direct buffers, GC pause | Có memory pressure hoặc GC pause? |
| Kubernetes | Ready replicas, restarts, CPU/memory, HPA | Pod có bị restart/throttle/scale chậm? |
| Resilience | Circuit breaker state, retry attempts, fallback | Gateway đang phục hồi hay retry quá mức? |
| Test annotations | Smoke/load/stress/soak start/end | Kết quả thay đổi có trùng thời điểm test? |

Dùng dashboard riêng cho backend nếu có quyền quan sát service đó. Nếu chỉ nhìn Gateway, bạn có thể thấy outbound latency tăng nhưng không biết service nào hoặc dependency nào gây chậm.

### 8.4. Cardinality và dữ liệu nhạy cảm

- Dùng route ID hoặc URI template làm dimension; không gắn raw path chứa order ID/user ID.
- Không thêm JWT subject, email, session ID, request ID hoặc raw query vào metric labels.
- Gateway path tags có thể làm cardinality tăng nhanh; chỉ bật khi đã giới hạn path thành template an toàn.
- Không log Authorization, Cookie, request/response body hoặc private forwarded headers.
- Management endpoints không được public; chỉ monitoring network được scrape.

Một metric label có giá trị mới theo từng request có thể tạo hàng trăm nghìn time series, làm Prometheus tốn bộ nhớ và query chậm. Trace ID nên nằm trong trace/log correlation, không phải metric label.

### 8.5. Tracing theo request

Spring Boot hỗ trợ Micrometer Tracing với OpenTelemetry/OTLP. Trong lab:

1. Thêm starter OpenTelemetry phù hợp với Boot version.
2. Cấu hình Collector endpoint và sampling probability.
3. Gửi request có W3C trace context.
4. Mở trace backend và kiểm spans qua Gateway tới backend.
5. Đối chiếu span latency với Gateway/client metrics và backend logs.

Trong production, sampling 10% là điểm bắt đầu có thể cân nhắc, nhưng tỷ lệ cuối phải theo lưu lượng, chi phí và yêu cầu điều tra. Tăng 100% chỉ trong bài test ngắn, có giới hạn. Không ghi raw request body/token vào span attributes.

### 8.6. Structured logs và correlation

Một log event vận hành có thể có các trường:

~~~json
{
  "timestamp": "2026-11-24T10:15:30Z",
  "service": "spring-cloud-gateway",
  "environment": "staging",
  "routeId": "orders-api",
  "method": "GET",
  "status": 503,
  "durationMs": 420,
  "errorCategory": "UPSTREAM_UNAVAILABLE",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7"
}
~~~

Đây là schema minh họa, không phải log tự sinh mặc định. Hãy log một event có ích cho điều tra, thêm route ID/status/latency/error category và trace context. Không echo credentials, payload hoặc toàn bộ headers vào log.

Metrics giúp thấy xu hướng liên tục; traces giúp đi theo một request; logs cung cấp sự kiện và nguyên nhân đã redact. Ba tín hiệu bổ sung cho nhau, không thay thế nhau.

## 9. Thiết lập alert và SLO

### 9.1. Alert nên gắn với hành động

Tạo ops/prometheus/rules/gateway.yml. Ví dụ này giả định Prometheus đang nhận histogram/counter http.server.requests và common tag application:

~~~yaml
groups:
  - name: gateway-slo
    rules:
      - alert: GatewayHigh5xxRatio
        expr: |
          (
            sum(rate(http_server_requests_seconds_count{
              application="spring-cloud-gateway",
              status=~"5.."
            }[5m]))
            /
            clamp_min(sum(rate(http_server_requests_seconds_count{
              application="spring-cloud-gateway"
            }[5m])), 1)
          ) > 0.01
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: Gateway 5xx ratio is above 1 percent
          description: Check route, upstream status, LoadBalancer and connection pool.

      - alert: GatewayP95LatencyHigh
        expr: |
          histogram_quantile(
            0.95,
            sum by (le) (
              rate(http_server_requests_seconds_bucket{
                application="spring-cloud-gateway"
              }[5m])
            )
          ) > 0.3
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: Gateway p95 latency is above 300ms
          description: Compare inbound and outbound latency, CPU, GC and pool metrics.
~~~

Các ngưỡng 1% và 300ms chỉ là ví dụ lab. Nếu meter name/labels khác ở version đang chạy, sửa rule theo metric thật trước khi reload Prometheus. Alert rule cần được load và kiểm tra trong Prometheus; file tồn tại trên đĩa không chứng minh alert đã hoạt động.

Prometheus đánh giá rule, nhưng notification cần Alertmanager được cấu hình; có thể dùng Grafana Alerting thay thế nếu đó là hệ thống cảnh báo của tổ chức.

| Alert | Điều kiện lab gợi ý | Hành động đầu tiên |
| --- | --- | --- |
| Gateway 5xx ratio | Trên 1% liên tục 5 phút | Phân loại upstream status, connect errors và route |
| p95 latency | Vượt SLO 10 phút | Xem upstream latency, pool, CPU/GC và traces |
| Ready replicas thấp | Dưới 2 trong Deployment 3 replicas | Kiểm probes, rollout, node/resource pressure |
| Restart/OOM | Restart count tăng hoặc OOMKilled | Kiểm memory limit, direct buffers, heap/GC |
| Pool acquire pressure | Pending/acquire timeout tăng | Kiểm pool metrics, backend latency và max connections |
| Circuit breaker mở | Open state kéo dài | Kiểm failure source, backend health và fallback |
| Telemetry gap | Prometheus scrape down hoặc trace export lỗi | Kiểm collector/monitoring network, không bỏ qua request path |

Không đặt alert cho mọi lần 429 nếu rate limiting đang hoạt động đúng. Có thể alert khi 429 vượt baseline hoặc xảy ra trên client/tenant quan trọng ngoài dự kiến.

Định nghĩa SLO trước khi tính error budget: quyết định rõ 4xx do client, 429 quota dự kiến và các endpoint health có được tính vào tập request hay không. Ví dụ availability SLO 99.9% có error budget 0.1% trong cửa sổ đo; đừng trộn traffic synthetic, probe và business traffic nếu mục tiêu đo chỉ dành cho API người dùng.

### 9.2. Phân biệt symptom và cause

Ví dụ:

~~~text
Symptom:
  Gateway 5xx tăng

Possible causes:
  - backend trả HTTP 503
  - no ServiceInstance từ LoadBalancer
  - connection refused / DNS / TLS
  - connect/response timeout
  - Redis rate limiter hoặc custom filter lỗi
  - circuit breaker fallback
  - Gateway pod quá tải / pool acquire timeout
~~~

Alert chỉ báo symptom; runbook phải giúp operator xác định nguồn lỗi. Gắn link dashboard, trace search, deployment revision và runbook vào alert để giảm thời gian điều tra.

## 10. Diễn tập lỗi và phục hồi

Chỉ chạy failure injection trong local/staging hoặc môi trường được phê duyệt. Mỗi drill cần có người quan sát, ngưỡng dừng, thời gian giới hạn và cách khôi phục.

### 10.1. Drill A — Mất một backend instance

**Thao tác:** với backend chạy nhiều replicas, dừng một replica hoặc xóa một Pod trong staging. Nếu Gateway dùng Kubernetes Service, Service sẽ chuyển traffic tới endpoints còn Ready. Nếu dùng lb://SERVICE-ID, xác minh LoadBalancer chọn instance còn hoạt động.

**Quan sát:**

- Upstream request success/failure.
- Service/EndpointSlice và ServiceInstance list.
- Retry attempts và circuit breaker state.
- p95/p99 latency trong lúc endpoint thay đổi.

**Đạt khi:** Gateway tiếp tục phục vụ qua instances còn lại; lỗi chỉ giới hạn trong thời gian hội tụ đã định; không có retry amplification hoặc 5xx kéo dài.

Compose demo với một orders container không thể chứng minh failover nhiều instance. Dùng Kubernetes replicas hoặc discovery-backed route để làm drill này.

### 10.2. Drill B — Upstream chậm hơn response timeout

Dùng Toxiproxy hoặc một backend test có thể delay response. Tạo độ trễ lớn hơn response timeout đã cấu hình trong Gateway.

Ví dụ cấu hình Gateway WebFlux 5.x:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            connect-timeout: 1000
            response-timeout: 2s
~~~

Connect timeout ở ví dụ là milliseconds; response timeout là duration. Các giá trị chỉ dùng cho lab.

**Quan sát:** latency, timeout/error status, retry count, circuit breaker state và backend đang xử lý request dang dở hay không.

**Đạt khi:** request vượt deadline trả lỗi theo policy; Gateway không giữ tài nguyên vô hạn; retry chỉ áp dụng cho method/idempotency phù hợp; circuit breaker không biến lỗi thành business success giả.

### 10.3. Drill C — Backend trả 503

Cấu hình mock backend trả HTTP 503 trong một khoảng thời gian. Phân biệt trường hợp này với connect refused hoặc không tìm được ServiceInstance:

- Upstream HTTP 503: backend đã nhận request và trả response.
- Connect failure: Gateway không nhận được HTTP response từ backend.
- Empty ServiceInstance: LoadBalancer không chọn được đích.

**Đạt khi:** logs/metrics/traces cho thấy đúng nguồn lỗi; status/fallback phù hợp API contract; alert và runbook chỉ tới backend health/capacity thay vì discovery khi không có bằng chứng discovery hỏng.

### 10.4. Drill D — Redis rate limiter không sẵn sàng

Nếu route dùng RedisRateLimiter:

1. Ghi lại baseline quota behavior và Redis metrics.
2. Trong staging, dừng Redis hoặc chặn kết nối từ Gateway.
3. Gửi request có tốc độ thấp rồi tăng dần.
4. Quan sát Gateway error/status, logs và Redis connection failures.
5. Khôi phục Redis và kiểm quota state.

Chủ động quyết định policy **fail-open hay fail-closed** khi Redis unavailable. Không giả định Gateway luôn trả 429 hoặc luôn cho qua; behavior còn phụ thuộc filter/error handling và phiên bản. Với API nhạy cảm, fail-open có thể bỏ qua quota; fail-closed có thể làm gián đoạn traffic. Ghi quyết định và kiểm thử theo contract.

### 10.5. Drill E — Restart/rollout Gateway

Thực hiện rolling update hoặc xóa một Pod qua cơ chế eviction/rollout trong staging:

~~~bash
kubectl rollout restart deployment/gateway -n app
kubectl rollout status deployment/gateway -n app
kubectl get pods -n app -l app=gateway -w
kubectl get endpointslices -n app
~~~

**Quan sát:**

- Readiness chuyển trạng thái và endpoints cập nhật.
- Số replicas Ready không giảm dưới PDB trong voluntary disruption được quản lý đúng.
- Request đang xử lý được drain trong termination grace.
- Không tăng đột biến 502/503 khi Pod thay thế khởi động.
- Replica mới dùng đúng image digest và config revision.

PDB được thực thi qua Eviction API trong các voluntary disruptions phù hợp; lệnh xóa Pod trực tiếp có thể bỏ qua PDB. Không dùng thao tác destructive trên cluster production để thử nghiệm.

### 10.6. Drill F — Monitoring/Collector bị gián đoạn

Trong staging, tạm dừng Prometheus hoặc OpenTelemetry Collector:

- Gateway có tiếp tục xử lý request business không?
- Prometheus scrape gap có được cảnh báo?
- Trace export queue/drop/failure có tăng không?
- Exporter có làm tăng latency hoặc tài nguyên đáng kể?
- Sau khi Collector trở lại, dữ liệu có tiếp tục được gửi hay một phần đã bị drop?

Telemetry backend không được trở thành dependency đồng bộ bắt buộc cho mỗi request business. Theo dõi exporter errors/queue và xác định retention/gap behavior thực tế.

### 10.7. Drill G — Rollback một bản release lỗi

Trước drill, lưu image digest và config revision của release đang ổn định. Triển khai canary có chủ đích chứa một thay đổi test gây lỗi, quan sát alert, sau đó rollback.

~~~bash
kubectl rollout undo deployment/gateway -n app
kubectl rollout status deployment/gateway -n app
kubectl get deployment gateway -n app -o wide
~~~

Nếu cấu hình được quản lý bằng ConfigMap/Helm/GitOps, rollback cả config revision; đổi image về cũ nhưng giữ property mới có thể khiến ứng dụng cũ không bind được cấu hình. Kiểm tra route definitions, secret references và schema/cache compatibility.

**Đạt khi:** image và config quay về cùng một release; replicas Ready; smoke test pass; error rate/latency trở lại baseline; không mất dữ liệu hoặc lặp side effects.

## 11. Runbook khi Gateway suy giảm

### 11.1. Trình tự phản ứng

1. **Xác nhận ảnh hưởng:** route nào, region/zone nào, từ thời điểm nào, status/latency ra sao.
2. **Kiểm rollout:** image digest, config revision, số replicas Ready, restarts và events.
3. **Phân loại lỗi:** route miss, 401/403/429, upstream HTTP 5xx, no ServiceInstance, connect/DNS/TLS/timeout hay fallback.
4. **Đối chiếu upstream:** backend request count, health, latency, dependency/database.
5. **Kiểm tài nguyên Gateway:** CPU throttling, heap/direct memory, GC pause, pool pending acquire, event loop.
6. **Kiểm resilience:** retry attempts, circuit breaker state, fallback behavior.
7. **Chọn mitigation:** rollback, giảm traffic, scale, disable một route có kiểm soát hoặc khôi phục backend dependency.
8. **Xác minh phục hồi:** smoke test, load thấp, error ratio và p95/p99.
9. **Ghi timeline:** trigger, detection, mitigation, recovery và follow-up action.

### 11.2. Bảng symptom → hướng điều tra

| Triệu chứng | Hướng điều tra đầu tiên |
| --- | --- |
| 404 tăng đột ngột | Route predicates, path rewrite, route config revision |
| 401/403 tăng | JWT issuer/JWK, scopes, identity provider |
| 429 tăng | Rate limiter, Redis, quota key, client traffic |
| 502/503 tăng | Upstream status, LoadBalancer instances, connect errors, circuit breaker |
| 504 tăng | Backend latency, response timeout, network path |
| p99 tăng nhưng p50 ổn | Slow instance, queueing, connection pool, dependency tail latency |
| Gateway OOM/restart | Heap/direct buffers, body caching, container limit |
| Không có metrics | Actuator exposure, Prometheus scrape, registry dependency |
| Không có traces | Sampling, OTLP endpoint, Collector connectivity, propagation |
| Traffic mất sau rollout | Readiness, Service selectors, image/config mismatch, public ingress |

### 11.3. Bằng chứng cần lưu sau mỗi drill

- k6 summary và raw output.
- Image digest, config revision, replica count.
- Prometheus dashboard/export trong test window.
- Trace IDs mẫu đã redact.
- Gateway/backend logs đã lọc credentials/PII.
- Kubernetes events, rollout history và EndpointSlice snapshots.
- Kết quả pass/fail theo tiêu chí đã thống nhất.
- Thời gian phát hiện, thời gian khôi phục và người phụ trách.

Không lưu raw bearer tokens, cookies, customer payload hoặc private keys trong evidence pack.

## 12. Tiêu chí nghiệm thu toàn bài lab

| Nhóm | Tiêu chí hoàn thành |
| --- | --- |
| Build | CI verify pass, image có tag/digest bất biến, SBOM/scan evidence |
| Container | Multi-stage, non-root, read-only filesystem nếu ứng dụng hỗ trợ, resource limits |
| Deployment | 3 replicas, startup/liveness/readiness đúng, rolling update và graceful shutdown |
| Availability | PDB và Service selectors phù hợp; management port private |
| Load | Smoke/load/stress/soak có profile, k6 thresholds và output được lưu |
| Performance | Throughput, p95/p99, error ratio và resource usage được đối chiếu SLO |
| Metrics | Prometheus scrape từng replica; Grafana dashboard có traffic/errors/latency/JVM/pool |
| Tracing/logs | Trace qua Gateway tới backend; logs có route/status/trace ID và đã redact |
| Recovery | Hoàn tất ít nhất drills backend-down, backend-slow, Gateway rollout và rollback |
| Runbook | Có symptom mapping, mitigation, verification và rollback instructions |

### 12.1. Checklist trước khi kết thúc

- [ ] Dockerfile build thành công bằng đúng Maven/Gradle Wrapper của dự án.
- [ ] Tests chạy trước khi image được publish.
- [ ] Image không chứa credentials, .env hoặc private key.
- [ ] Runtime chạy non-root và chỉ có quyền cần thiết.
- [ ] Management port không được publish public.
- [ ] Health probes phân biệt startup, liveness và readiness.
- [ ] CPU/memory requests/limits được đo thay vì copy nguyên giá trị lab.
- [ ] Prometheus scrape được từng Gateway replica.
- [ ] Grafana hiển thị request rate, status, p95/p99, JVM và pool metrics.
- [ ] k6 smoke/load/stress/soak có output và thresholds rõ.
- [ ] Load generator không trở thành bottleneck của bài đo.
- [ ] 429 dự kiến được tách khỏi lỗi ngoài dự kiến.
- [ ] Traces được propagate qua Gateway và backend.
- [ ] Logs/traces/metrics không chứa token, cookie hoặc PII.
- [ ] Backend-down và backend-slow drills cho kết quả đúng contract.
- [ ] Redis/telemetry failure policy đã được thử nếu các dependency này có trong kiến trúc.
- [ ] Rolling update và rollback được diễn tập trên staging.
- [ ] Có evidence pack và runbook cho người trực vận hành.

## 13. Tổng kết và tài liệu tham khảo

Một Gateway chỉ sẵn sàng vận hành khi bạn có thể **đóng gói lặp lại, triển khai an toàn, đo được giới hạn, nhìn thấy request và khôi phục có kiểm chứng**. Docker image tốt giúp runtime gọn và ít quyền; Kubernetes probes/PDB/graceful shutdown giúp quản lý vòng đời Pod; k6 giúp lượng hóa throughput và tail latency; Prometheus/Grafana/Tracing giúp định vị bottleneck; recovery drills chứng minh hệ thống phản ứng đúng khi upstream, Redis, Gateway hoặc monitoring gặp sự cố.

Không dùng một lần load test thành công để tuyên bố năng lực production. Lưu cấu hình, image digest, workload profile, SLO, resource limits và môi trường chạy cùng kết quả; lặp lại khi đổi Gateway version, route/filter, backend, JVM hoặc hạ tầng.

### Tài liệu tham khảo chính thức

- [Spring Boot — Container Images và Dockerfiles](https://docs.spring.io/spring-boot/reference/packaging/container-images/).
- [Spring Boot — Actuator Metrics và Prometheus](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
- [Spring Boot — Actuator Health Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
- [Spring Boot — Tracing và OpenTelemetry](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
- [Spring Boot — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html).
- [Spring Cloud Gateway — Configuration Properties và Observability](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html).
- [Spring Cloud Gateway — Actuator API](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/actuator-api.html).
- [Docker — Build best practices](https://docs.docker.com/build/building/best-practices/).
- [Docker — Multi-stage builds](https://docs.docker.com/build/building/multi-stage/).
- [Kubernetes — Liveness, Readiness và Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/).
- [Kubernetes — Pod Disruptions và PodDisruptionBudget](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/).
- [Grafana k6 — Scenarios và Executors](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/).
- [Grafana k6 — Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/).
