# Tổng hợp manifest, kiểm thử và bằng chứng vận hành

## Mục tiêu và kết quả bàn giao

Bài thực hành cuối cần tạo ra một bộ bàn giao mà người khác có thể triển khai lại, chạy lại phép thử và hiểu vì sao kết quả được chấp nhận. Một ảnh chụp Pod ở trạng thái Running hoặc một lần gọi HTTP thành công chưa đủ chứng minh discovery, cấu hình, quyền và khả năng phục hồi đều đúng.

Trong module **SPRING_CLOUD_KUBERNETES**, bộ bàn giao của bài này gồm:

- Mã ứng dụng và bộ phiên bản dependency đã chốt.
- Manifest nguồn cùng bản đã render được dùng để triển khai.
- Kịch bản kiểm tra có đầu vào, kỳ vọng và điều kiện đạt.
- Bằng chứng gắn với image, cluster, Pod, cấu hình và thời điểm.
- Cách phục hồi trạng thái lab và những giới hạn chưa kiểm thử.

Các lệnh là hướng dẫn cho người học chạy trong **cluster lab riêng**, không phải kết quả thực nghiệm đã được chạy sẵn. Chỉ đánh dấu PASS sau khi có bằng chứng thật.

## 1. Chốt kiến trúc và phạm vi kiểm thử

Lab sử dụng một image Java, chạy với hai profile:

~~~mermaid
flowchart LR
    U[Người kiểm thử qua port-forward] --> C[demo-client]
    C --> D[DiscoveryClient]
    D --> K[Kubernetes API: Service và EndpointSlice]
    C --> L[Spring Cloud LoadBalancer - POD]
    L --> B1[catalog-api Pod A]
    L --> B2[catalog-api Pod B]
    M[ConfigMap revision] --> C
    S[Secret giả lập] --> C
~~~

| Thành phần | Lựa chọn của lab | Bằng chứng cần có |
| --- | --- | --- |
| Discovery | Fabric8, EndpointSlice, một namespace | Instance trong JVM khớp backend Ready |
| LoadBalancer | Mode POD, gọi bằng service ID | Response đi qua các backend Pod |
| ConfigMap | Nạp qua API khi khởi động | Revision trong ứng dụng khớp lượt triển khai |
| Secret | Giá trị giả lập, đọc qua API | Cấu hình bắt buộc có mặt; không xuất giá trị |
| Cập nhật cấu hình | Rollout có kiểm soát | Trước/sau restart và phương án quay lại |
| Sức khỏe | Startup/readiness/liveness của Spring Boot | Probe đạt và trạng thái EndpointSlice phù hợp |
| Configuration Watcher | Không triển khai trong đường cơ sở | Ghi rõ chưa kiểm thử hot refresh |
| Leader election | Không cần cho ứng dụng HTTP của lab | Không thêm thư viện/quyền liên quan |

Mode POD của Spring Cloud Kubernetes LoadBalancer dùng DiscoveryClient để lấy instance. Không được lấy một lần gọi DNS Service làm bằng chứng riêng rằng nhánh LoadBalancer này hoạt động. Xem [LoadBalancer for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/load-balancer.html).

Bộ phiên bản minh họa: JDK 21, Spring Boot 3.5.3, Spring Cloud BOM 2025.0.3, Spring Cloud Kubernetes 3.3.3. Đối chiếu [BOM tại tag 2025.0.3](https://github.com/spring-cloud/spring-cloud-release/blob/v2025.0.3/spring-cloud-dependencies/pom.xml). Khi dùng bộ khác, ghi phiên bản thực tế và xác minh lại các thuộc tính.

## 2. Tổ chức bộ bàn giao

~~~text
sck-evidence/
  pom.xml
  Dockerfile
  src/main/java/example/evidence/
    EvidenceApplication.java
    BackendController.java
    ClientConfiguration.java
    ClientController.java
  src/main/resources/
    application.yaml
    application-client.yaml
  manifests/base/
    kustomization.yaml
    namespace.yaml
    access.yaml
    configuration.yaml
    workloads.yaml
  evidence/<run-id>/
    versions.json
    dependencies.txt
    rendered-r1.yaml
    rendered-r1.sha256.txt
    rollout.txt
    pods.txt
    images.json
    endpointslices.json
    ready-backends.json
    config-r1.json
    instances.json
    calls.csv
    fault-results.csv
    config-r2.json
    config-rollback.json
    client.log
    backend.log
    results.csv
  RUNBOOK.md
~~~

Thư mục evidence do người chạy lab tạo cho từng lượt, không tái sử dụng một tên chung rồi ghi đè bằng chứng cũ. Các tên tệp là quy ước để liên kết kết quả với phép thử.

Manifest có Secret trong bài chỉ chứa dữ liệu giả lập. Với hệ thống thật, dùng bản bàn giao đã loại giá trị bí mật hoặc cơ chế tham chiếu Secret; không đóng gói credential thật trong rendered manifest hoặc log.

## 3. Ứng dụng tham chiếu tối thiểu

Nếu đã có ứng dụng đáp ứng các endpoint tương đương, có thể giữ mã hiện tại và ánh xạ phép thử sang hợp đồng của nó. Mẫu dưới đây giúp lab tự chứa, không cần một dịch vụ bên ngoài.

### 3.1. Dependency và image

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.3</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>sck-evidence</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>2025.0.3</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-kubernetes-fabric8-config</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-kubernetes-fabric8-loadbalancer</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`Dockerfile`:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/sck-evidence-0.0.1-SNAPSHOT.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Giữ cùng image cho hai profile giúp tập trung bằng chứng vào hành vi triển khai. Tag local không thay thế digest trong bộ bàn giao triển khai thật.

### 3.2. Ứng dụng và backend

`EvidenceApplication.java`:

~~~java
package example.evidence;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EvidenceApplication {

    public static void main(String[] args) {
        SpringApplication.run(EvidenceApplication.class, args);
    }
}
~~~

`BackendController.java`:

~~~java
package example.evidence;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("backend")
public class BackendController {

    private static final Logger log =
            LoggerFactory.getLogger(BackendController.class);

    private final String pod;

    public BackendController(@Value("${POD_NAME:local}") String pod) {
        this.pod = pod;
    }

    @GetMapping("/api/id")
    public BackendReply identity(
            @RequestHeader(value = "X-Request-Id", defaultValue = "none")
            String requestId) {
        log.info("backend_request requestId={} pod={}", requestId, pod);
        return new BackendReply(pod, "v1", requestId);
    }

    public record BackendReply(String pod, String version, String requestId) {
    }
}
~~~

### 3.3. Client dùng DiscoveryClient và LoadBalancer

`ClientConfiguration.java`:

~~~java
package example.evidence;

import java.time.Duration;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
@Profile("client")
public class ClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        var factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(2));
        factory.setReadTimeout(Duration.ofSeconds(2));
        return RestClient.builder().requestFactory(factory);
    }
}
~~~

`ClientController.java`:

~~~java
package example.evidence;

import java.util.List;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.server.ResponseStatusException;

@RestController
@Profile("client")
public class ClientController {

    private static final Logger log =
            LoggerFactory.getLogger(ClientController.class);

    private final DiscoveryClient discovery;
    private final RestClient client;
    private final String pod;
    private final String revision;
    private final boolean credentialConfigured;

    public ClientController(
            DiscoveryClient discovery,
            @LoadBalanced RestClient.Builder builder,
            @Value("${POD_NAME:local}") String pod,
            @Value("${lab.revision}") String revision,
            @Value("${lab.credential}") String credential) {
        this.discovery = discovery;
        this.client = builder.build();
        this.pod = pod;
        this.revision = revision;
        this.credentialConfigured = !credential.isBlank();
    }

    @GetMapping("/api/config")
    public ConfigReply config() {
        return new ConfigReply(pod, revision, credentialConfigured);
    }

    @GetMapping("/api/instances")
    public List<InstanceReply> instances() {
        return discovery.getInstances("catalog-api").stream()
                .map(instance -> new InstanceReply(
                        instance.getHost(), instance.getPort()))
                .toList();
    }

    @GetMapping("/api/call")
    public CallReply call() {
        String requestId = UUID.randomUUID().toString();
        try {
            BackendReply backend = client.get()
                    .uri("http://catalog-api/api/id")
                    .header("X-Request-Id", requestId)
                    .retrieve()
                    .body(BackendReply.class);
            if (backend == null) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_GATEWAY, "empty backend response");
            }
            log.info("client_call requestId={} caller={} backend={} revision={}",
                    requestId, pod, backend.pod(), revision);
            return new CallReply(requestId, pod, revision, backend);
        }
        catch (RestClientException ex) {
            log.warn("client_call_failed requestId={} caller={} type={}",
                    requestId, pod, ex.getClass().getSimpleName());
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE, "backend unavailable");
        }
    }

    public record ConfigReply(
            String pod, String revision, boolean credentialConfigured) {
    }

    public record InstanceReply(String host, int port) {
    }

    public record BackendReply(
            String pod, String version, String requestId) {
    }

    public record CallReply(
            String requestId, String caller, String revision,
            BackendReply backend) {
    }
}
~~~

`@LoadBalanced RestClient.Builder` nhận service ID thay cho địa chỉ Pod cố định. Tham khảo [Spring Cloud Commons 4.3](https://docs.spring.io/spring-cloud-commons/reference/4.3/spring-cloud-commons/common-abstractions.html).

Điểm quan sát Secret chỉ trả boolean; nó không chứng minh rotation Secret hoặc việc credential dùng được ở một hệ thống ngoài. Phạm vi bài chỉ xác minh giá trị bắt buộc đã được nạp lúc khởi động.

### 3.4. Cấu hình theo profile

`application.yaml`:

~~~yaml
spring:
  application:
    name: sck-evidence
  cloud:
    discovery:
      enabled: false
      client:
        health-indicator:
          enabled: false
    kubernetes:
      discovery:
        enabled: false
      config:
        enabled: false
      secrets:
        enabled: false
      reload:
        enabled: false

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
  health:
    kubernetes:
      enabled: false
~~~

`application-client.yaml`:

~~~yaml
spring:
  config:
    import: "kubernetes:"
  cloud:
    discovery:
      enabled: true
    loadbalancer:
      cache:
        enabled: false
      retry:
        enabled: false
    kubernetes:
      client:
        namespace: sck-evidence
      discovery:
        enabled: true
        all-namespaces: false
        namespaces:
          - sck-evidence
        service-labels:
          app: catalog-api
        use-endpoint-slices: true
        include-not-ready-addresses: false
        primary-port-name: http
      loadbalancer:
        mode: POD
      config:
        enabled: true
        namespace: sck-evidence
        name: demo-client-config
        include-profile-specific-sources: false
        fail-fast: true
      secrets:
        enabled: true
        enable-api: true
        namespace: sck-evidence
        name: demo-client-secret
        include-profile-specific-sources: false
        fail-fast: true
~~~

Nhánh 3.3 hỗ trợ lựa chọn EndpointSlice với thuộc tính tương ứng và yêu cầu cluster/RBAC phù hợp. Xem [DiscoveryClient for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/discovery-client.html). Tắt cache LoadBalancer không đồng nghĩa loại bỏ mọi cache hoặc độ trễ hội tụ của client Kubernetes.

Config Data chỉ được import ở profile client. Backend không cần đọc cấu hình qua API. Không thêm bootstrap song song với `spring.config.import`; xem [Kubernetes PropertySource implementations](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config.html).

## 4. Tổng hợp manifest nguồn bằng Kustomize

Kustomize giúp giữ một tập tài nguyên nguồn và render thành đầu vào triển khai xác định. Bản đã render mới là đối tượng được hash, kiểm tra và apply trong lượt thử. Tham khảo [quản lý đối tượng bằng Kustomize](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/).

### 4.1. Namespace và danh tính

`manifests/base/namespace.yaml`:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: sck-evidence
~~~

`manifests/base/access.yaml`:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: demo-client
  namespace: sck-evidence
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: catalog-api
  namespace: sck-evidence
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: demo-client-reader
  namespace: sck-evidence
rules:
  - apiGroups: [""]
    resources: ["services", "pods"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["configmaps", "secrets"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: demo-client-reader
  namespace: sck-evidence
subjects:
  - kind: ServiceAccount
    name: demo-client
    namespace: sck-evidence
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: demo-client-reader
~~~

Role chỉ được gắn cho client. Backend không có nhu cầu gọi Kubernetes API nên không nhận RoleBinding và sẽ không mount token.

Quyền list Secret có thể đọc dữ liệu Secret trong namespace; vì vậy namespace này chỉ chứa dữ liệu lab giả lập. Mẫu không phải bộ quyền dùng chung cho mọi môi trường.

### 4.2. Nguồn cấu hình

`manifests/base/configuration.yaml`:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: demo-client-config
  namespace: sck-evidence
data:
  application.yaml: |-
    lab:
      revision: r1
---
apiVersion: v1
kind: Secret
metadata:
  name: demo-client-secret
  namespace: sck-evidence
type: Opaque
stringData:
  lab.credential: lab-only-placeholder
~~~

Giá trị Secret giả lập không được đưa vào response hoặc log. Chỉ lưu trạng thái đã nạp và danh tính nguồn. Trong hệ thống thật, không dùng một bản rendered chứa Secret làm tệp chia sẻ tự do.

### 4.3. Workload và Service

`manifests/base/workloads.yaml`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
  namespace: sck-evidence
spec:
  replicas: 2
  revisionHistoryLimit: 3
  progressDeadlineSeconds: 180
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      serviceAccountName: catalog-api
      automountServiceAccountToken: false
      terminationGracePeriodSeconds: 30
      containers:
        - name: app
          image: sck-evidence:1
          imagePullPolicy: IfNotPresent
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: backend
            - name: SPRING_APPLICATION_NAME
              value: catalog-api
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 512Mi
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
  namespace: sck-evidence
  labels:
    app: catalog-api
spec:
  selector:
    app: catalog-api
  ports:
    - name: http
      port: 80
      targetPort: http
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: demo-client
  namespace: sck-evidence
spec:
  replicas: 1
  revisionHistoryLimit: 3
  progressDeadlineSeconds: 180
  selector:
    matchLabels:
      app: demo-client
  template:
    metadata:
      labels:
        app: demo-client
    spec:
      serviceAccountName: demo-client
      automountServiceAccountToken: true
      terminationGracePeriodSeconds: 30
      containers:
        - name: app
          image: sck-evidence:1
          imagePullPolicy: IfNotPresent
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: client
            - name: SPRING_APPLICATION_NAME
              value: demo-client
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 512Mi
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: demo-client
  namespace: sck-evidence
  labels:
    app: demo-client
spec:
  selector:
    app: demo-client
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

Startup probe cho ứng dụng thời gian khởi tạo trước các probe còn lại. Readiness điều khiển khả năng nhận traffic; liveness phục vụ phát hiện tình trạng cần restart. Xem [cấu hình probe Kubernetes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

Trong lab, readiness client không phụ thuộc trực tiếp việc backend đang có replica. Vì vậy cần phép thử nghiệp vụ riêng; Pod Ready không bảo đảm mọi dependency bên ngoài còn đáp ứng.

### 4.4. Kustomization

`manifests/base/kustomization.yaml`:

~~~yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - namespace.yaml
  - access.yaml
  - configuration.yaml
  - workloads.yaml
~~~

Trước khi render, kiểm tra các liên kết: Service selector khớp Pod label, port name khớp targetPort, profile đúng, tên ConfigMap/Secret khớp cấu hình ứng dụng, ServiceAccount khớp RoleBinding.

Kubernetes controller sẽ tạo EndpointSlice cho backend của Service theo trạng thái thực tế. Không tự ghi IP Pod vào manifest để khiến một lần gọi thành công.

## 5. Tạo một lượt kiểm thử có định danh

Các lệnh PowerShell được chạy từ thư mục project lab. Ví dụ dùng kind tên `sck-evidence`; nếu đã có cluster, dùng context phù hợp.

~~~powershell
kind create cluster --name sck-evidence
~~~

Chỉ tạo khi cluster đó chưa tồn tại. Sau đó khởi tạo biến và thư mục kết quả:

~~~powershell
$labContext = "kind-sck-evidence"
$labNamespace = "sck-evidence"
$runId = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$runDir = Join-Path "evidence" $runId
New-Item -ItemType Directory -Path $runDir -Force | Out-Null

function Invoke-Kube {
    $commandOutput = & kubectl --context=$labContext @args
    if ($LASTEXITCODE -ne 0) {
        throw "kubectl failed; inspect the command and stderr before continuing"
    }
    $commandOutput
}
~~~

Hàm wrapper kiểm tra exit code của native command. Không coi pipeline cuối thành công là bằng chứng mọi lệnh trước đã thành công.

### 5.1. Build và chụp bộ phiên bản

~~~powershell
mvn package -DskipTests
if ($LASTEXITCODE -ne 0) { throw "Build failed" }

$dependencyOutput = mvn dependency:tree "-Dincludes=org.springframework.cloud:*,io.fabric8:*"
if ($LASTEXITCODE -ne 0) { throw "Dependency inventory failed" }
$dependencyOutput | Set-Content -LiteralPath (Join-Path $runDir "dependencies.txt") -Encoding UTF8

docker build -t sck-evidence:1 .
if ($LASTEXITCODE -ne 0) { throw "Image build failed" }

kind load docker-image sck-evidence:1 --name sck-evidence
if ($LASTEXITCODE -ne 0) { throw "Image load failed" }

$versions = Invoke-Kube version -o json | ConvertFrom-Json
[pscustomobject]@{
    runId = $runId
    capturedAtUtc = [DateTime]::UtcNow.ToString("o")
    context = $labContext
    namespace = $labNamespace
    kubectl = $versions.clientVersion.gitVersion
    apiServer = $versions.serverVersion.gitVersion
    declaredBoot = "3.5.3"
    declaredCloudBom = "2025.0.3"
    resolvedDependencies = "dependencies.txt"
} | ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath (Join-Path $runDir "versions.json") -Encoding UTF8
~~~

Build trên không chạy test ứng dụng; kết quả compile/package phải được ghi riêng với kiểm thử tích hợp bên dưới. Dependency resolve và image runtime mới là dữ liệu dùng để đối chiếu phiên bản thực tế.

Nếu rebuild ứng dụng, dùng tag mới và nạp lại image tương ứng; không âm thầm tái sử dụng tag cũ rồi suy rằng Pod đã chạy mã mới.

### 5.2. Render, hash và kiểm tra với API server

Tạo namespace trước để server-side dry-run của các resource namespaced có nơi hợp lệ:

~~~powershell
Invoke-Kube apply -f manifests/base/namespace.yaml
$rendered = Invoke-Kube kustomize manifests/base
$renderedR1 = Join-Path $runDir "rendered-r1.yaml"
$rendered | Set-Content -LiteralPath $renderedR1 -Encoding UTF8

Get-FileHash -LiteralPath $renderedR1 -Algorithm SHA256 |
    Format-List |
    Out-String |
    Set-Content -LiteralPath (Join-Path $runDir "rendered-r1.sha256.txt") -Encoding UTF8

Invoke-Kube apply --dry-run=server -f $renderedR1
~~~

Namespace được apply riêng vì dry-run Namespace không lưu namespace xuống cluster để các request tiếp theo sử dụng. Ghi rõ thao tác khởi tạo này trong runbook.

Server-side dry-run kiểm tra request/validation/admission ở mức tương ứng. Nó không chạy Pod, không chứng minh discovery hay nghiệp vụ; xem [kubectl apply](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_apply/).

Khi đạt, apply **chính tệp đã hash**:

~~~powershell
Invoke-Kube apply -f $renderedR1

$rolloutOutput = @(
    Invoke-Kube rollout status deployment/catalog-api -n $labNamespace --timeout=180s
    Invoke-Kube rollout status deployment/demo-client -n $labNamespace --timeout=180s
)
$rolloutOutput | Set-Content -LiteralPath (Join-Path $runDir "rollout.txt") -Encoding UTF8
~~~

Nếu có lỗi, giữ stdout/stderr và trạng thái FAILED hoặc BLOCKED theo nguyên nhân. Không xóa kết quả rồi chỉ lưu lần chạy tốt.

### 5.3. Chụp danh tính workload và image thực tế

~~~powershell
Invoke-Kube get pods -n $labNamespace -o wide |
    Set-Content -LiteralPath (Join-Path $runDir "pods.txt") -Encoding UTF8

$podList = Invoke-Kube get pods -n $labNamespace -o json | ConvertFrom-Json
$imageRows = @(
    foreach ($podItem in $podList.items) {
        foreach ($containerState in $podItem.status.containerStatuses) {
            [pscustomobject]@{
                pod = $podItem.metadata.name
                uid = $podItem.metadata.uid
                serviceAccount = $podItem.spec.serviceAccountName
                container = $containerState.name
                image = $containerState.image
                imageID = $containerState.imageID
                ready = $containerState.ready
                restarts = $containerState.restartCount
            }
        }
    }
)
ConvertTo-Json -InputObject $imageRows -Depth 6 |
    Set-Content -LiteralPath (Join-Path $runDir "images.json") -Encoding UTF8
~~~

ImageID ở runtime giúp phát hiện khác biệt mà tag không thể hiện. Một snapshot chỉ phản ánh thời điểm chụp, nên cần chụp thêm sau thao tác gây lỗi hoặc rollout quan trọng.

## 6. Ma trận kiểm thử và tiêu chí đạt

Đặt các tiêu chí trước khi chạy:

| ID | Phép thử | Điều kiện đạt trong lab |
| --- | --- | --- |
| M01 | Render và dry-run | Render xác định, có hash, server chấp nhận |
| R01 | Danh tính/RBAC | Client đọc đúng resource, không có quyền ghi ngoài nhu cầu |
| H01 | Rollout/probe | Hai backend và một client Ready, không restart bất thường |
| C01 | Nạp cấu hình | Revision r1 và credentialConfigured=true |
| D01 | Discovery | Instance ứng dụng khớp địa chỉ backend Ready |
| L01 | Đường gọi LoadBalancer | Request ID khớp, có response từ cả hai backend trong lượt mẫu |
| F01 | Backend mất tạm thời | Lỗi được quan sát; sau phục hồi đường gọi hoạt động lại |
| C02 | Cập nhật ConfigMap | Phân biệt trước restart và sau rollout có r2 |
| B01 | Quay lại cấu hình | Sau khôi phục và restart, client trở về r1 |
| E01 | Bằng chứng | Có dữ liệu, timestamp và liên kết tới từng kết luận |

Mục tiêu hội tụ có thể đặt là 60 giây cho lab; đây là ngưỡng thử nghiệm do người chạy chọn, không phải bảo đảm thời gian từ Spring hoặc Kubernetes. Đo thực tế và ghi giới hạn môi trường nếu không đạt.

## 7. Kiểm tra RBAC và trạng thái cơ sở

### 7.1. Quyền được phép và quyền phải bị từ chối

Các lệnh impersonation yêu cầu operator có quyền tương ứng. Nếu không có quyền impersonate, ghi BLOCKED cho phép thử này hoặc dùng phương án kiểm tra bằng danh tính thật; không suy ra ServiceAccount ứng dụng bị lỗi.

~~~powershell
$clientSubject = "system:serviceaccount:$($labNamespace):demo-client"

$allowed = @(
    Invoke-Kube auth can-i list services -n $labNamespace --as=$clientSubject
    Invoke-Kube auth can-i watch endpointslices.discovery.k8s.io -n $labNamespace --as=$clientSubject
    Invoke-Kube auth can-i list configmaps -n $labNamespace --as=$clientSubject
    Invoke-Kube auth can-i list secrets -n $labNamespace --as=$clientSubject
)
if (@($allowed | Where-Object { $_.Trim() -ne "yes" }).Count -gt 0) {
    throw "Required RBAC check did not return yes"
}

$deniedAnswer = & kubectl --context=$labContext auth can-i delete pods -n $labNamespace --as=$clientSubject
$deniedExit = $LASTEXITCODE

if ($deniedExit -ne 1 -or ($deniedAnswer -join "").Trim() -ne "no") {
    throw "Expected denial was not verified; inspect permissions and impersonation"
}

[pscustomobject]@{
    capturedAtUtc = [DateTime]::UtcNow.ToString("o")
    subject = $clientSubject
    requiredReads = "PASS"
    deletePodsDenied = "PASS"
} | ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $runDir "rbac.json") -Encoding UTF8
~~~

Không đưa lệnh có kỳ vọng exit code 1 qua wrapper vốn coi mọi exit code khác 0 là lỗi. Một kết quả `no` đúng kỳ vọng khác với lỗi kết nối hoặc bị từ chối impersonation.

Kiểm tra thêm client không có quyền ghi ConfigMap nếu đó là yêu cầu thiết kế, và backend không có quyền list nguồn Kubernetes. Các kiểm tra phân quyền không thay thế việc quan sát request thật từ JVM.

### 7.2. Chọn đúng client Pod

Đọc lại danh sách Pod sau rollout:

~~~powershell
$clientPodList = Invoke-Kube get pods -n $labNamespace -l app=demo-client -o json |
    ConvertFrom-Json

$clientPod = ($clientPodList.items |
    Where-Object {
        $_.status.phase -eq "Running" -and
        $null -eq $_.metadata.deletionTimestamp
    } |
    Select-Object -First 1).metadata.name

if ([string]::IsNullOrWhiteSpace($clientPod)) {
    throw "No client Pod available"
}

$clientPod
~~~

Trong terminal riêng, dùng đúng Pod vừa xác định:

~~~powershell
kubectl --context=kind-sck-evidence port-forward -n sck-evidence pod/TEN_CLIENT_POD 18080:8080
~~~

Thay `TEN_CLIENT_POD` bằng tên thực tế. Terminal chạy phép thử tiếp tục dùng `http://127.0.0.1:18080`. Port-forward tới Pod giúp gắn response với một replica rõ ràng.

### 7.3. Kiểm tra health và cấu hình ban đầu

~~~powershell
$liveness = Invoke-RestMethod "http://127.0.0.1:18080/actuator/health/liveness" -TimeoutSec 5
$readiness = Invoke-RestMethod "http://127.0.0.1:18080/actuator/health/readiness" -TimeoutSec 5
$configR1 = Invoke-RestMethod "http://127.0.0.1:18080/api/config" -TimeoutSec 5

if ($liveness.status -ne "UP" -or $readiness.status -ne "UP") {
    throw "Probe endpoint did not report UP"
}
if ($configR1.revision -ne "r1" -or $configR1.credentialConfigured -ne $true) {
    throw "Initial configuration contract failed"
}
if ($configR1.pod -ne $clientPod) {
    throw "Response came from a different Pod"
}

[pscustomobject]@{
    capturedAtUtc = [DateTime]::UtcNow.ToString("o")
    response = $configR1
} | ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath (Join-Path $runDir "config-r1.json") -Encoding UTF8
~~~

Chỉ trả boolean cho Secret vẫn cần phối hợp với việc ứng dụng yêu cầu property bắt buộc và chỉ cấu hình đúng nguồn Secret trong lab. Không dùng boolean này để tuyên bố đã kiểm thử đăng nhập tới database hay rotation credential.

## 8. Đối chiếu Kubernetes EndpointSlice với DiscoveryClient

Một Service có thể có nhiều EndpointSlice. Cần đọc tất cả Slice thuộc Service, kiểm tra địa chỉ và port, không lấy phần tử đầu tiên làm đại diện cho toàn bộ backend. Xem [EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/).

Đoạn dưới chờ tối đa khoảng 60 giây để trạng thái ứng dụng khớp backend Ready trong cấu hình lab:

~~~powershell
$deadline = [DateTime]::UtcNow.AddSeconds(60)
$instanceMatch = $false

do {
    $sliceJson = Invoke-Kube get endpointslices.discovery.k8s.io -n $labNamespace -l kubernetes.io/service-name=catalog-api -o json --request-timeout=5s
    $sliceList = $sliceJson | ConvertFrom-Json

    $readyRows = @(
        foreach ($sliceItem in $sliceList.items) {
            $httpPort = ($sliceItem.ports |
                Where-Object { $_.name -eq "http" } |
                Select-Object -First 1).port

            foreach ($endpointItem in $sliceItem.endpoints) {
                if ($endpointItem.conditions.ready -eq $true) {
                    foreach ($endpointAddress in $endpointItem.addresses) {
                        [pscustomobject]@{
                            slice = $sliceItem.metadata.name
                            pod = $endpointItem.targetRef.name
                            address = $endpointAddress
                            port = $httpPort
                        }
                    }
                }
            }
        }
    )

    $instances = @(Invoke-RestMethod "http://127.0.0.1:18080/api/instances" -TimeoutSec 5)
    $expectedHosts = @($readyRows.address | Sort-Object -Unique)
    $actualHosts = @($instances.host | Sort-Object -Unique)
    $readyPodNames = @($readyRows.pod | Sort-Object -Unique)

    if ($expectedHosts.Count -gt 0 -and $actualHosts.Count -gt 0) {
        $hostDifference = @(Compare-Object -ReferenceObject $expectedHosts -DifferenceObject $actualHosts)
        $badPorts = @($instances | Where-Object { $_.port -ne 8080 })
        $instanceMatch = (
            $readyPodNames.Count -eq 2 -and
            $hostDifference.Count -eq 0 -and
            $badPorts.Count -eq 0
        )
    }

    if (-not $instanceMatch) {
        Start-Sleep -Seconds 1
    }
} while (-not $instanceMatch -and [DateTime]::UtcNow -lt $deadline)

$sliceJson | Set-Content -LiteralPath (Join-Path $runDir "endpointslices.json") -Encoding UTF8
ConvertTo-Json -InputObject $readyRows -Depth 6 |
    Set-Content -LiteralPath (Join-Path $runDir "ready-backends.json") -Encoding UTF8
ConvertTo-Json -InputObject $instances -Depth 6 |
    Set-Content -LiteralPath (Join-Path $runDir "instances.json") -Encoding UTF8

if (-not $instanceMatch) {
    throw "Discovery did not match the two ready backends within the lab target"
}
~~~

Đoạn thử dành cho mẫu Service/port và topology lab đang dùng. Với dual-stack hoặc tùy chọn lọc địa chỉ khác, phải điều chỉnh hợp đồng so sánh phù hợp thay vì coi mọi khác biệt số lượng địa chỉ là lỗi.

Lỗi API hoặc lỗi HTTP sẽ dừng lượt kiểm tra; không tự chuyển thành PASS khi hết thời gian. Nếu cần cơ chế retry cho lỗi vận chuyển trong harness, phải ghi riêng số lần lỗi và lý do.

## 9. Chứng minh đường gọi qua LoadBalancer

### 9.1. Hàm lấy một mẫu request

~~~powershell
function Get-LabCallSample {
    $startedAtUtc = [DateTime]::UtcNow.ToString("o")
    $watch = [System.Diagnostics.Stopwatch]::StartNew()

    try {
        $reply = Invoke-RestMethod "http://127.0.0.1:18080/api/call" -TimeoutSec 8
        $watch.Stop()
        [pscustomobject]@{
            capturedAtUtc = $startedAtUtc
            httpStatus = 200
            elapsedMs = $watch.ElapsedMilliseconds
            requestId = $reply.requestId
            caller = $reply.caller
            backendPod = $reply.backend.pod
            revision = $reply.revision
            correlationValid = (
                -not [string]::IsNullOrWhiteSpace($reply.requestId) -and
                $reply.requestId -eq $reply.backend.requestId
            )
            failureKind = ""
        }
    }
    catch {
        $watch.Stop()
        $httpStatus = 0
        if ($null -ne $_.Exception.Response) {
            $httpStatus = [int]$_.Exception.Response.StatusCode
        }

        [pscustomobject]@{
            capturedAtUtc = $startedAtUtc
            httpStatus = $httpStatus
            elapsedMs = $watch.ElapsedMilliseconds
            requestId = ""
            caller = ""
            backendPod = ""
            revision = ""
            correlationValid = $false
            failureKind = if ($httpStatus -eq 0) { "transport" } else { "http" }
        }
    }
}
~~~

HTTP status `0` trong tệp kết quả là quy ước của harness cho lỗi vận chuyển, không phải status HTTP thật. Ví dụ port-forward bị ngắt phải được phân biệt với ứng dụng trả 503.

### 9.2. Gọi nhiều lần và kiểm tra nội dung

~~~powershell
$callRows = @(
    for ($requestIndex = 0; $requestIndex -lt 30; $requestIndex++) {
        Get-LabCallSample
        Start-Sleep -Milliseconds 100
    }
)

$callRows | Export-Csv -LiteralPath (Join-Path $runDir "calls.csv") -NoTypeInformation -Encoding UTF8

$badCalls = @($callRows |
    Where-Object {
        $_.httpStatus -ne 200 -or
        $_.correlationValid -ne $true -or
        $_.revision -ne "r1" -or
        $_.caller -ne $clientPod
    })

$observedBackends = @($callRows |
    Where-Object { $_.httpStatus -eq 200 } |
    Select-Object -ExpandProperty backendPod -Unique)

$unexpectedBackends = @($observedBackends |
    Where-Object { $_ -notin $readyPodNames })

if ($badCalls.Count -gt 0 -or
    $observedBackends.Count -lt 2 -or
    $unexpectedBackends.Count -gt 0) {
    throw "LoadBalancer path did not satisfy the lab contract"
}
~~~

Kết quả cần thể hiện request thực sự tới backend qua service ID, với request ID được truyền xuyên suốt. Không chỉ kiểm tra status 200 từ client.

Quan sát cả hai backend trong lượt mẫu là tiêu chí của cấu hình lab này. Không dùng một mẫu nhỏ để kết luận phân phối luôn cân bằng hoặc tính xác suất chọn backend ở mọi tình huống.

Từ một `requestId` trong CSV, tìm dòng tương ứng trong log client và backend. Không cần in payload Secret để tạo tương quan vận hành.

## 10. Kiểm thử sự cố và phục hồi

### 10.1. Mất toàn bộ backend

Trong terminal điều khiển, xác nhận baseline là hai replica rồi đưa backend về không replica, chỉ trong namespace lab:

~~~powershell
Invoke-Kube scale deployment/catalog-api -n $labNamespace --replicas=0
Invoke-Kube get pods -n $labNamespace -l app=catalog-api
~~~

Quan sát `/api/instances` hội tụ về danh sách rỗng và gọi `/api/call` nhiều lần:

~~~powershell
$faultRows = @(
    for ($requestIndex = 0; $requestIndex -lt 15; $requestIndex++) {
        Get-LabCallSample
        Start-Sleep -Seconds 1
    }
)
$faultRows | Export-Csv -LiteralPath (Join-Path $runDir "fault-results.csv") -NoTypeInformation -Encoding UTF8
~~~

Kỳ vọng sau khi backend đã hết và client hội tụ:

- Đường gọi nghiệp vụ báo không khả dụng; mẫu controller chuyển lỗi RestClient thành 503.
- Lỗi vận chuyển của harness, nếu có, được ghi riêng.
- Client không restart liên tục chỉ vì backend không có replica.
- Readiness client có thể vẫn UP theo thiết kế đã chọn; nó không thay thế kết quả nghiệp vụ.

Nếu vẫn có 200 trong thời gian ngắn, kiểm tra thời điểm Pod thực sự dừng và trạng thái cache/connection trước khi kết luận. Nếu không quan sát được lỗi nghiệp vụ sau khi backend đã hết, phép thử chưa chứng minh tình huống mất backend.

### 10.2. Phục hồi và đo thời gian

~~~powershell
$recoveryStartedAt = [DateTime]::UtcNow

Invoke-Kube scale deployment/catalog-api -n $labNamespace --replicas=2
Invoke-Kube rollout status deployment/catalog-api -n $labNamespace --timeout=180s

$recoveryDeadline = [DateTime]::UtcNow.AddSeconds(60)
$recoverySample = $null

do {
    $candidateSample = Get-LabCallSample
    if ($candidateSample.httpStatus -eq 200 -and
        $candidateSample.correlationValid -eq $true) {
        $recoverySample = $candidateSample
        break
    }
    Start-Sleep -Seconds 1
} while ([DateTime]::UtcNow -lt $recoveryDeadline)

if ($null -eq $recoverySample) {
    throw "Business call did not recover within the lab target"
}

[pscustomobject]@{
    capturedAtUtc = [DateTime]::UtcNow.ToString("o")
    recoveryStartedAtUtc = $recoveryStartedAt.ToString("o")
    elapsedSeconds = ([DateTime]::UtcNow - $recoveryStartedAt).TotalSeconds
    firstSuccessfulSample = $recoverySample
} | ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath (Join-Path $runDir "recovery.json") -Encoding UTF8
~~~

Phép đo trên gồm thời gian tạo/khởi động Pod và hội tụ discovery, không chỉ độ trễ của LoadBalancer. Tách các mốc nếu muốn tối ưu một đoạn cụ thể.

Sau phục hồi, chạy lại phép so sánh D01 và lượt gọi L01, lưu bằng tên khác như `instances-after-recovery.json` và `calls-after-recovery.csv` để không làm mất bằng chứng baseline.

### 10.3. Biến thể: xóa một backend Pod

Có thể xóa một Pod backend đã xác định trong khi terminal khác lấy mẫu request. Deployment sẽ tạo Pod thay thế.

Ghi thời điểm xóa, Pod UID cũ/mới, số lỗi trong cửa sổ chuyển tiếp và thời điểm bộ instance ổn định. Không cam kết không có lỗi chỉ từ việc có hai replica; graceful termination, readiness, cache và request đang xử lý đều ảnh hưởng.

Nếu thực hiện biến thể này, bổ sung kết quả riêng. Không đánh dấu đã kiểm thử failover từng Pod khi chỉ chạy phép scale về không.

## 11. Kiểm tra cập nhật cấu hình và quay lại

### 11.1. Revision mới chưa được JVM nạp

Trong `manifests/base/configuration.yaml`, đổi riêng `lab.revision` từ `r1` thành `r2`, giữ Secret giả lập nguyên trạng. Render thành tệp mới:

~~~powershell
$renderedR2 = Join-Path $runDir "rendered-r2.yaml"
Invoke-Kube kustomize manifests/base |
    Set-Content -LiteralPath $renderedR2 -Encoding UTF8

Get-FileHash -LiteralPath $renderedR2 -Algorithm SHA256 |
    Format-List |
    Out-String |
    Set-Content -LiteralPath (Join-Path $runDir "rendered-r2.sha256.txt") -Encoding UTF8

Invoke-Kube apply --dry-run=server -f $renderedR2
Invoke-Kube apply -f $renderedR2
~~~

Đọc `/api/config` trên Pod client hiện tại trước restart. Với thiết kế nạp lúc khởi động, giá trị còn r1 là kỳ vọng. Lưu `config-before-restart.json` kèm timestamp và Pod.

Nếu thấy r2 ngay, không tự bỏ qua khác biệt: kiểm tra có cơ chế refresh khác đang bật, Pod đã thay hoặc cấu hình thực tế khác mẫu không.

### 11.2. Rollout client nhận revision r2

~~~powershell
Invoke-Kube rollout restart deployment/demo-client -n $labNamespace
Invoke-Kube rollout status deployment/demo-client -n $labNamespace --timeout=180s
~~~

Chọn lại client Pod, ghi UID mới và mở lại port-forward. Sau đó:

~~~powershell
$configR2 = Invoke-RestMethod "http://127.0.0.1:18080/api/config" -TimeoutSec 5
if ($configR2.revision -ne "r2" -or $configR2.credentialConfigured -ne $true) {
    throw "New Pod did not load revision r2"
}

[pscustomobject]@{
    capturedAtUtc = [DateTime]::UtcNow.ToString("o")
    response = $configR2
} | ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath (Join-Path $runDir "config-r2.json") -Encoding UTF8
~~~

Đổi tham chiếu Pod hiện tại trong harness khi chạy lại phép thử. Lượt gọi mới cần mong đợi revision r2; không giữ assertion r1 của baseline rồi diễn giải thất bại đó thành lỗi LoadBalancer.

### 11.3. Khôi phục revision r1

Khôi phục manifest nguồn về r1 để phản ánh trạng thái mong muốn. Với lab riêng, có thể apply lại bản rendered-r1 đã lưu rồi restart client:

~~~powershell
Invoke-Kube apply -f $renderedR1
Invoke-Kube rollout restart deployment/demo-client -n $labNamespace
Invoke-Kube rollout status deployment/demo-client -n $labNamespace --timeout=180s
~~~

Chọn Pod mới và mở lại port-forward, xác minh revision r1 rồi lưu `config-rollback.json`.

Apply lại cả bộ rendered-r1 cũng khôi phục các replica và tài nguyên trong bộ đó. Đừng dùng thao tác này cho namespace chia sẻ mà không biết những thay đổi vận hành nào sẽ bị thay thế.

`rollout undo` của Deployment không tự khôi phục nội dung ConfigMap/Secret độc lập. Vì vậy rollback phải ghi cả image và nguồn cấu hình cần phục hồi. Tham khảo [Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/).

### 11.4. Nếu chọn hot refresh bằng Configuration Watcher

Đó là một phạm vi bổ sung. Cần thêm manifest, image/version watcher, ServiceAccount/RBAC, nguồn/label theo dõi, đường HTTP hoặc Bus và cơ chế refresh bean.

Bằng chứng tối thiểu phải nối được: resource thay đổi → watcher nhận biết → gửi thông báo → ứng dụng nhận → giá trị/hành vi đổi trên từng replica. Đọc [Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/spring-cloud-kubernetes-configuration-watcher.html).

Không lấy phép thử rollout ở phần trên để đánh dấu PASS cho watcher. Khi không triển khai watcher, ghi NOT_RUN hoặc không áp dụng theo phạm vi đã thống nhất.

## 12. Thu thập log và hoàn thiện hồ sơ

### 12.1. Lưu log sau các lượt thử

~~~powershell
Invoke-Kube logs -n $labNamespace -l app=demo-client --all-containers=true --prefix=true --timestamps=true --since=30m --max-log-requests=5 |
    Set-Content -LiteralPath (Join-Path $runDir "client.log") -Encoding UTF8

Invoke-Kube logs -n $labNamespace -l app=catalog-api --all-containers=true --prefix=true --timestamps=true --since=30m --max-log-requests=5 |
    Set-Content -LiteralPath (Join-Path $runDir "backend.log") -Encoding UTF8

Invoke-Kube get pods -n $labNamespace -o wide |
    Set-Content -LiteralPath (Join-Path $runDir "pods-final.txt") -Encoding UTF8

Invoke-Kube get events -n $labNamespace --sort-by=.metadata.creationTimestamp |
    Set-Content -LiteralPath (Join-Path $runDir "events.txt") -Encoding UTF8
~~~

Log Pod đã bị xóa có thể không còn lấy được bằng các lệnh trên. Nếu cần bằng chứng xuyên suốt sự cố, thu log trước thao tác, stream log trong terminal riêng hoặc dùng hệ thống log tập trung đã có. Không ghi “không có lỗi” chỉ vì log của Pod cũ đã mất.

Giữ timestamp và request ID để đối chiếu. Không bật log toàn bộ HTTP body hoặc xuất Secret nhằm tăng số lượng bằng chứng.

### 12.2. Mẫu results.csv

Mỗi dòng là một phép thử thực sự thực hiện:

~~~csv
testId,status,expected,observed,evidence
M01,PASS,server accepts rendered manifest,replace with actual result,rendered-r1.yaml
R01,PASS,required reads allowed and delete denied,replace with actual result,rbac.json
H01,PASS,2 backend and 1 client Ready,replace with actual result,pods.txt
C01,PASS,r1 and credential present,replace with actual result,config-r1.json
D01,PASS,discovery matches Ready backends,replace with actual result,instances.json
L01,PASS,correlated calls reach both backends,replace with actual result,calls.csv
F01,PASS,unavailable observed then recovery,replace with actual result,recovery.json
C02,PASS,new Pod reads r2,replace with actual result,config-r2.json
B01,PASS,configuration restored to r1,replace with actual result,config-rollback.json
W01,NOT_RUN,watcher outside baseline scope,not deployed,scope declaration
~~~

Đây là mẫu cấu trúc, không phải kết quả đã đạt. Khi tạo tệp thật, điền observed và status từ bằng chứng; không sao chép nguyên các dòng PASS trước khi chạy.

Dùng các trạng thái rõ ràng:

| Trạng thái | Cách sử dụng |
| --- | --- |
| PASS | Có bằng chứng đáp ứng điều kiện đã đặt |
| FAIL | Đã chạy, kết quả trái kỳ vọng |
| BLOCKED | Chưa xác minh được do điều kiện môi trường/quyền/đầu vào |
| NOT_RUN | Chưa chạy hoặc ngoài phạm vi; ghi lý do |

Không gộp tất cả thành PASS vì build hoặc rollout đã thành công. Một phép thử bị chặn không được biến thành “không áp dụng” chỉ để hoàn tất báo cáo.

### 12.3. Nội dung RUNBOOK.md

Runbook cần cho phép người nhận:

1. Xác định cluster/context, namespace, phiên bản và image cần dùng.
2. Build hoặc lấy đúng image, render và kiểm tra hash đầu vào.
3. Khởi tạo namespace, dry-run, apply và chờ rollout theo thứ tự.
4. Chạy từng phép thử và hiểu điều kiện PASS/FAIL.
5. Định vị lỗi theo đường cấu hình, RBAC, discovery, HTTP hoặc probe.
6. Khôi phục hai backend, revision mong muốn và kết nối port-forward.
7. Quay lại bộ image/cấu hình đã xác minh.
8. Dọn riêng tài nguyên lab khi không cần nữa.

Nêu rõ các giá trị còn giả lập, mục tiêu thời gian, phép thử chưa chạy và giới hạn của môi trường local. Tên tệp hoặc ảnh chụp không thay thế diễn giải observed.

## 13. Tiêu chí chấp nhận bộ bàn giao

Bộ bàn giao đạt yêu cầu khi người khác có thể nối được:

~~~text
Mã nguồn và bộ dependency
        → image/runtime identity
        → manifest nguồn và bản render có hash
        → workload/Pod/ServiceAccount trên cluster
        → phép thử với kỳ vọng rõ
        → response, log và snapshot có thời điểm
        → kết luận và cách phục hồi
~~~

Cần kiểm tra:

- Manifest không phụ thuộc IP Pod, context ẩn hoặc giá trị chỉ tồn tại trên máy tác giả.
- Quyền của client/backend đúng nhu cầu; không dùng cluster-admin để bỏ qua lỗi.
- Kết quả discovery và đường gọi nghiệp vụ được chứng minh riêng.
- Trạng thái Ready, restart và sự hội tụ khi backend thay đổi có bằng chứng.
- ConfigMap/Secret được nạp theo đúng nguồn và thời điểm đã chọn.
- Cập nhật cấu hình, rollback và giới hạn watcher được mô tả đúng phạm vi.
- Không có credential thật trong bộ kết quả chia sẻ.
- Mỗi kết luận có tệp bằng chứng; các điểm chưa đạt vẫn được giữ nguyên trạng thái.

Sau khi hoàn tất, dừng các phiên port-forward. Nếu namespace dành riêng cho lab và không cần giữ tài nguyên:

~~~powershell
kubectl --context=kind-sck-evidence delete namespace sck-evidence
~~~

Thao tác này xóa tài nguyên trong namespace đó. Chỉ dọn sau khi đã lưu bằng chứng cần thiết và xác nhận không có workload khác cần giữ. Không cần xóa cluster để hoàn tất bài.
