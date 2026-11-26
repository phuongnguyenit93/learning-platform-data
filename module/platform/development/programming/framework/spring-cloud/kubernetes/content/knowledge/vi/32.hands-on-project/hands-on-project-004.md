# Theo dõi thuộc tính bị ghi đè từ nhiều nguồn

## Mục tiêu và sản phẩm của bài thực hành

Một giá trị đã được sửa trong ConfigMap nhưng ứng dụng vẫn trả về giá trị cũ. Nguyên nhân có thể là biến môi trường đang ghi đè, ứng dụng đọc một nguồn khác, Pod chưa nạp lại cấu hình hoặc bean vẫn giữ giá trị đã nhận lúc khởi tạo. Chỉ nhìn nội dung ConfigMap không phân biệt được những trường hợp này.

Trong bài thực hành thuộc module **SPRING_CLOUD_KUBERNETES**, bạn xây dựng một ứng dụng nhỏ để theo dõi **một key không nhạy cảm: `demo.message`**. Kết quả cần quan sát gồm:

- Giá trị hiệu lực trong Spring `Environment`.
- Nguồn thắng và các nguồn có cùng key nhưng bị che.
- Origin của thuộc tính nếu source hỗ trợ.
- Giá trị trong `@ConfigurationProperties` và giá trị được inject lúc tạo bean.
- Pod và profile liên quan đến lần quan sát.

Lab sử dụng Spring Cloud Kubernetes để đọc ConfigMap và một Secret chứa dữ liệu đánh dấu giả lập. DiscoveryClient, LoadBalancer và Configuration Watcher không được bổ sung vào đường chạy cơ sở vì không cần để giải thích thứ tự ghi đè. Phần cuối chỉ ra cách phân biệt vấn đề ưu tiên với vấn đề refresh khi hệ thống có watcher.

## 1. Mô hình cần kiểm chứng

### 1.1. Thứ tự ưu tiên giữa các nhóm nguồn

Trong phạm vi ứng dụng thông thường của lab, dự đoán từ cao xuống thấp là:

~~~text
Command-line argument
        ↓
SPRING_APPLICATION_JSON
        ↓
Java system property
        ↓
Biến môi trường của process
        ↓
Config Data, gồm nguồn Kubernetes được import
        ↓
Các giá trị mặc định còn lại
~~~

Đây là phần thứ tự liên quan đến lab, không phải toàn bộ danh sách nguồn của Spring Boot. Nguồn trong test, servlet container, Devtools hoặc bootstrap có thể làm bối cảnh khác đi. Xem [Externalized Configuration của Spring Boot](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html).

Các dạng biểu diễn sẽ được dùng cho cùng key:

| Nguồn | Cách biểu diễn |
| --- | --- |
| YAML ứng dụng | `demo.message: from-jar` hoặc cấu trúc YAML tương đương |
| ConfigMap/Secret PropertySource | `demo.message` sau khi nguồn được xử lý |
| Biến môi trường | `DEMO_MESSAGE=from-env` |
| Java system property | `-Ddemo.message=from-jvm`, trước `-jar` |
| JSON cấu hình | `{"demo":{"message":"from-json"}}` |
| Command-line của Spring Boot | `--demo.message=from-cli`, sau tên JAR |

Kubernetes không trực tiếp quyết định thứ tự trên. Kubernetes đưa file, biến môi trường hoặc resource API đến ứng dụng; Spring quyết định cách biến chúng thành PropertySource và chọn giá trị.

### 1.2. Thứ tự bên trong nhóm Kubernetes

Trong tài liệu Spring Cloud Kubernetes nhánh 3.3:

- Các ConfigMap trong danh sách sources được xử lý theo thứ tự; nguồn sau có thể ghi đè key trùng ở nguồn trước.
- Khi cùng bật ConfigMap và Secret PropertySource có key trùng, ConfigMap có ưu tiên cao hơn Secret.

Tham khảo [ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config/configmap-propertysource.html) và [Order of ConfigMaps and Secrets](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config/order_of_configMaps_and_secrets.html).

Không suy luận “Secret luôn thắng vì chứa dữ liệu nhạy cảm”. Độ nhạy cảm của dữ liệu và mức ưu tiên cấu hình là hai thuộc tính khác nhau.

Trong lab này, dự đoán đầy đủ cho marker là:

~~~text
from-cli
  > from-json
  > from-jvm
  > from-env
  > from-cm-override
  > from-cm-base
  > from-secret
  > from-jar
~~~

Dấu `>` chỉ mức ưu tiên trong cấu hình đã chọn, không phải thứ tự thời gian tạo resource. Khi dùng bộ phiên bản hoặc cơ chế nạp khác, phải kiểm chứng lại bằng nguồn runtime.

## 2. Chuẩn bị môi trường và cấu trúc project

Cần JDK 21, Maven, Docker, kubectl và một cluster lab. Ví dụ dưới đây dùng kind và PowerShell; cluster tên `property-lab` có context `kind-property-lab`.

Nếu chưa có cluster lab này, có thể tạo:

~~~powershell
kind create cluster --name property-lab
~~~

Nếu cluster đã tồn tại, sử dụng nó. Quy trình tạo cluster và nạp image tham khảo [kind Quick Start](https://kind.sigs.k8s.io/docs/user/quick-start/).

Tạo project với cấu trúc:

~~~text
property-lab/
  pom.xml
  Dockerfile
  src/main/java/example/propertylab/PropertyLabApplication.java
  src/main/java/example/propertylab/DemoProperties.java
  src/main/java/example/propertylab/PropertyProbe.java
  src/main/resources/application.yaml
  k8s-resources.yaml
  deployment.yaml
~~~

Để có một bộ minh họa cố định, POM dùng Spring Boot `3.5.3` và Spring Cloud BOM `2025.0.3`. BOM này quản lý Spring Cloud Kubernetes `3.3.3`; xem [BOM tại tag 2025.0.3](https://github.com/spring-cloud/spring-cloud-release/blob/v2025.0.3/spring-cloud-dependencies/pom.xml). Ghi lại phiên bản đã resolve khi chạy lab với bộ khác.

### 2.1. Khai báo dependency

Nội dung `pom.xml`:

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
    <artifactId>property-lab</artifactId>
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

Lab không thêm starter bootstrap. Với nhánh đang xét, nguồn Kubernetes được nạp bằng `spring.config.import`; không đồng thời nạp cùng nguồn qua bootstrap. Xem [Kubernetes PropertySource implementations](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config.html).

### 2.2. Khai báo ứng dụng và bean cấu hình

`PropertyLabApplication.java`:

~~~java
package example.propertylab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(DemoProperties.class)
public class PropertyLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(PropertyLabApplication.class, args);
    }
}
~~~

`DemoProperties.java`:

~~~java
package example.propertylab;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public class DemoProperties {

    private String message = "from-bean-default";

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }
}
~~~

Giá trị khởi tạo `from-bean-default` thuộc bean. Nó không tự tạo một PropertySource trong Environment; chỉ được dùng nếu quá trình bind không cung cấp giá trị khác.

## 3. Tạo điểm quan sát chỉ dành cho marker

### 3.1. Theo dõi Environment, bean và các nguồn có cùng key

`PropertyProbe.java`:

~~~java
package example.propertylab;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.origin.Origin;
import org.springframework.boot.origin.OriginLookup;
import org.springframework.core.env.CompositePropertySource;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PropertyProbe {

    private static final String KEY = "demo.message";

    private final ConfigurableEnvironment environment;
    private final DemoProperties properties;
    private final String injectedAtConstruction;

    public PropertyProbe(
            ConfigurableEnvironment environment,
            DemoProperties properties,
            @Value("${demo.message:from-value-default}")
            String injectedAtConstruction) {
        this.environment = environment;
        this.properties = properties;
        this.injectedAtConstruction = injectedAtConstruction;
    }

    @GetMapping("/lab/property")
    public Snapshot inspect() {
        List<Candidate> candidates = new ArrayList<>();

        for (PropertySource<?> source : environment.getPropertySources()) {
            // Adapter tổng hợp; bỏ qua để không đếm lại nguồn bên dưới.
            if (!"configurationProperties".equals(source.getName())) {
                collect(source, candidates);
            }
        }

        String pod = System.getenv("HOSTNAME");
        return new Snapshot(
                KEY,
                environment.getProperty(KEY, "<absent>"),
                properties.getMessage(),
                injectedAtConstruction,
                pod == null ? "local" : pod,
                Arrays.asList(environment.getActiveProfiles()),
                List.copyOf(candidates));
    }

    private void collect(PropertySource<?> source, List<Candidate> candidates) {
        if (source instanceof CompositePropertySource composite) {
            for (PropertySource<?> nested : composite.getPropertySources()) {
                collect(nested, candidates);
            }
            return;
        }

        Object value = source.getProperty(KEY);
        if (value != null) {
            Origin origin = OriginLookup.getOrigin(source, KEY);
            candidates.add(new Candidate(
                    candidates.size() + 1,
                    source.getName(),
                    String.valueOf(value),
                    origin == null ? "<not-provided>" : origin.toString()));
        }
    }

    public record Snapshot(
            String key,
            String environment,
            String bound,
            String injectedAtConstruction,
            String pod,
            List<String> activeProfiles,
            List<Candidate> candidates) {
    }

    public record Candidate(
            int priority,
            String source,
            String value,
            String origin) {
    }
}
~~~

Điểm quan sát cố định key `demo.message`, không nhận tên property tùy ý. Chỉ dùng các chuỗi đánh dấu trong lab; không đổi key thành mật khẩu hoặc token để thử.

Các source được duyệt theo thứ tự tìm kiếm của Environment. `priority` trong response là số thứ tự ứng viên có key, không phải một mã ưu tiên nội bộ của Spring. Tham khảo [MutablePropertySources](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/env/MutablePropertySources.html).

Origin là thông tin tùy source cung cấp, có thể là tài nguyên và dòng/cột hoặc không có. Không suy ra nguồn chưa được nạp chỉ vì không có origin. Xem [OriginLookup](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/origin/OriginLookup.html).

Đây là bộ quan sát cho một key scalar đơn giản. Nó không thay thế toàn bộ Binder của Spring Boot, không mô phỏng mọi trường hợp list/map hoặc placeholder nhiều tầng.

### 3.2. Cấu hình nguồn và Actuator

`src/main/resources/application.yaml`:

~~~yaml
spring:
  application:
    name: property-lab
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      client:
        namespace: property-lab
      config:
        enabled: true
        enable-api: true
        namespace: property-lab
        include-profile-specific-sources: false
        use-name-as-prefix: false
        fail-fast: true
        sources:
          - name: lab-base
          - name: lab-override
      secrets:
        enabled: true
        enable-api: true
        namespace: property-lab
        include-profile-specific-sources: false
        use-name-as-prefix: false
        fail-fast: true
        sources:
          - name: lab-secret
      discovery:
        enabled: false
      reload:
        enabled: false

demo:
  message: from-jar

management:
  server:
    port: 9090
  endpoints:
    web:
      exposure:
        include: health,env,configprops
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
    health:
      probes:
        enabled: true
  health:
    kubernetes:
      enabled: false
~~~

Các quyết định có chủ ý:

- Namespace được đặt rõ để tránh đọc nhầm tài nguyên cùng tên ở nơi khác.
- Nguồn theo profile được tắt trong lượt cơ sở; không tự phát sinh thêm ConfigMap có hậu tố profile.
- Không thêm prefix cho key; các nguồn thực sự cạnh tranh cùng `demo.message`.
- Reload trong ứng dụng được tắt; ConfigMap thay đổi không tự trở thành giá trị mới trong JVM.
- Health contributor Kubernetes được tắt để lab chỉ cần quyền đọc nguồn cấu hình; probe của ứng dụng vẫn được dùng.
- Cổng management là 9090; truy cập qua port-forward đến Pod lab.

Secret qua Kubernetes API phải được bật rõ và cần quyền phù hợp; đây không phải mặc định của cơ chế đọc Secret qua API. Xem [Secrets PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config/secrets-propertysource.html).

Actuator `env` và `configprops` giữ `show-values: never`. Các giá trị bị che không có nghĩa source không tồn tại. Giá trị marker được đọc qua điểm quan sát riêng. Xem [sanitization của Actuator](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.sanitization).

## 4. Tạo dữ liệu và RBAC trong namespace lab

Nội dung `k8s-resources.yaml`:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: property-lab
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: property-lab
  namespace: property-lab
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: property-lab-config-reader
  namespace: property-lab
rules:
  - apiGroups: [""]
    resources: ["configmaps", "secrets"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: property-lab-config-reader
  namespace: property-lab
subjects:
  - kind: ServiceAccount
    name: property-lab
    namespace: property-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: property-lab-config-reader
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: lab-base
  namespace: property-lab
data:
  application.yaml: |-
    demo:
      message: from-cm-base
    lab:
      loaded-from-base: true
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: lab-override
  namespace: property-lab
data:
  application.yaml: |-
    demo:
      message: from-cm-override
    lab:
      loaded-from-override: true
---
apiVersion: v1
kind: Secret
metadata:
  name: lab-secret
  namespace: property-lab
type: Opaque
stringData:
  demo.message: from-secret
~~~

Secret trên chỉ chứa một marker giả lập. Namespace dành riêng cho lab vì quyền list Secret có thể đọc dữ liệu Secret trong phạm vi namespace. Không dùng bộ quyền này nguyên trạng cho namespace chứa credential thật.

Ứng dụng chỉ đọc nguồn ban đầu, không có cơ chế watch trong lượt cơ sở nên mẫu không cấp quyền watch. Tính năng khác có thể cần các verb hoặc resource khác; không mở quyền chỉ để làm biến mất một lỗi không liên quan đến bài.

Áp dụng:

~~~powershell
$contextName = "kind-property-lab"
$ns = "property-lab"

kubectl --context=$contextName apply -f k8s-resources.yaml
~~~

Kiểm tra ServiceAccount nếu tài khoản operator có quyền impersonate:

~~~powershell
$saSubject = "system:serviceaccount:$($ns):property-lab"

kubectl --context=$contextName auth can-i get configmaps -n $ns --as=$saSubject
kubectl --context=$contextName auth can-i list configmaps -n $ns --as=$saSubject
kubectl --context=$contextName auth can-i get secrets -n $ns --as=$saSubject
kubectl --context=$contextName auth can-i list secrets -n $ns --as=$saSubject
~~~

Nếu bị từ chối impersonation, chưa thể kết luận ServiceAccount của ứng dụng thiếu quyền. Trong mọi trường hợp, log request từ ứng dụng mới là bằng chứng đường đọc runtime đã hoạt động.

## 5. Build image và triển khai lượt cơ sở

### 5.1. Dockerfile

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/property-lab-0.0.1-SNAPSHOT.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Build và nạp image vào kind:

~~~powershell
mvn package -DskipTests
docker build -t property-lab:1 .
kind load docker-image property-lab:1 --name property-lab
~~~

`JAVA_TOOL_OPTIONS` được JVM xử lý khi khởi động; args của container được nối sau ENTRYPOINT. Điều này giúp phân biệt `-Ddemo.message` với `--demo.message` trong các lượt sau.

Nếu dùng cluster khác, đưa image vào registry hoặc runtime mà cluster truy cập được và đổi trường image tương ứng.

### 5.2. Deployment

Nội dung `deployment.yaml`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: property-lab
  namespace: property-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: property-lab
  template:
    metadata:
      labels:
        app: property-lab
    spec:
      serviceAccountName: property-lab
      containers:
        - name: app
          image: property-lab:1
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
            - name: management
              containerPort: 9090
          env: []
          args: []
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
              port: management
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: management
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: management
            periodSeconds: 10
~~~

Không cần tạo Service hay Ingress cho lab này. Dùng port-forward để đọc chính Pod được chọn.

~~~powershell
kubectl --context=$contextName apply -f deployment.yaml
kubectl --context=$contextName rollout status deployment/property-lab -n $ns --timeout=180s
kubectl --context=$contextName get pods -n $ns -l app=property-lab
~~~

Nếu rollout không đạt, đọc log và sự kiện trước khi kiểm tra thứ tự ghi đè:

~~~powershell
kubectl --context=$contextName logs deployment/property-lab -n $ns -c app --tail=150
~~~

Phải giải quyết lỗi nạp nguồn/RBAC trước khi ghi nhận rằng một source “đã thua”. Không có source do không đọc được khác với có source nhưng bị nguồn khác che.

## 6. Ghi nhận lần quan sát đầu tiên

### 6.1. Chọn đúng Pod và mở port-forward

Trong terminal dành cho port-forward, đặt context và namespace như ở trên rồi lấy một Pod đang chạy, không trong quá trình xóa:

~~~powershell
$podJson = kubectl --context=$contextName get pods -n $ns -l app=property-lab -o json
if ($LASTEXITCODE -ne 0) {
    throw "Khong doc duoc danh sach Pod"
}

$podName = (($podJson | ConvertFrom-Json).items |
    Where-Object {
        $_.status.phase -eq "Running" -and
        $null -eq $_.metadata.deletionTimestamp
    } |
    Sort-Object { $_.metadata.creationTimestamp } -Descending |
    Select-Object -First 1).metadata.name

if ([string]::IsNullOrWhiteSpace($podName)) {
    throw "Chua co Pod phu hop de quan sat"
}

kubectl --context=$contextName port-forward "pod/$podName" -n $ns 18080:8080 19090:9090
~~~

Trong terminal khác:

~~~powershell
$probe = Invoke-RestMethod "http://127.0.0.1:18080/lab/property"
$probe | Select-Object key, environment, bound, injectedAtConstruction, pod, activeProfiles
$probe.candidates | Format-Table priority, source, value, origin -AutoSize
~~~

Kết quả dự kiến ở lượt cơ sở:

~~~text
environment              = from-cm-override
bound                    = from-cm-override
injectedAtConstruction   = from-cm-override

Thứ tự các ứng viên của demo.message:
  from-cm-override
  from-cm-base
  from-secret
  from-jar
~~~

Tên source và origin cụ thể có thể thay đổi theo implementation. Đừng viết bài kiểm tra phụ thuộc toàn bộ chuỗi tên source khi chỉ cần kiểm chứng nguồn và giá trị.

### 6.2. Đối chiếu Actuator

~~~powershell
$envView = Invoke-RestMethod "http://127.0.0.1:19090/actuator/env/demo.message"
$envView.property | Format-List
$envView.activeProfiles
$envView.propertySources | Select-Object name, property
~~~

Endpoint property đơn cung cấp nguồn thắng và các PropertySource theo thứ tự ưu tiên; origin được hiển thị nếu có. Xem [API Environment của Actuator](https://docs.spring.io/spring-boot/3.5/api/rest/actuator/env.html).

Giá trị có thể là `******` do sanitization. Giữ nguyên chế độ che; dùng `/lab/property` để so sánh marker.

Có thể đọc `/actuator/configprops` để kiểm tra sự có mặt của bean prefix `demo` và thông tin bind được endpoint cung cấp. Giá trị bean trong lab đã có ở trường `bound`, nên không cần bật hiển thị toàn bộ cấu hình.

Không dùng riêng source đầu tiên trong toàn bộ Environment để suy ra winner. Source đó có thể không chứa key đang xét; phải tìm ứng viên theo chính key.

## 7. Tăng dần lớp ghi đè

Mỗi lượt bên dưới sửa **phần env/args của cùng container trong deployment.yaml**, giữ nguyên các trường còn lại. Dùng manifest làm nguồn điều khiển thống nhất cho các lượt.

Sau khi sửa, chạy:

~~~powershell
kubectl --context=$contextName apply -f deployment.yaml
kubectl --context=$contextName rollout status deployment/property-lab -n $ns --timeout=180s
~~~

Pod mới thay Pod cũ thì port-forward cũ có thể kết thúc. Dừng phiên cũ bằng Ctrl+C nếu cần, chọn lại Pod và mở port-forward như phần 6 trước khi đọc kết quả.

### 7.1. Lượt E: biến môi trường

~~~yaml
env:
  - name: DEMO_MESSAGE
    value: from-env
args: []
~~~

Dự kiến ba trường giá trị đều là `from-env` sau khởi động mới. Các marker ConfigMap và Secret vẫn có trong danh sách ứng viên phía dưới.

Điều này chứng minh nguồn thấp hơn không bị xóa; nó chỉ không cung cấp giá trị hiệu lực cho key đang xét.

### 7.2. Lượt J: thêm Java system property

~~~yaml
env:
  - name: DEMO_MESSAGE
    value: from-env
  - name: JAVA_TOOL_OPTIONS
    value: "-Ddemo.message=from-jvm"
args: []
~~~

Dự kiến winner là `from-jvm`; system property có ưu tiên cao hơn biến môi trường.

`JAVA_TOOL_OPTIONS` chỉ chứa marker của lab. Không dùng cách đưa credential thật vào log/lệnh khởi động để thử thứ tự ưu tiên.

### 7.3. Lượt G: thêm SPRING_APPLICATION_JSON

~~~yaml
env:
  - name: DEMO_MESSAGE
    value: from-env
  - name: JAVA_TOOL_OPTIONS
    value: "-Ddemo.message=from-jvm"
  - name: SPRING_APPLICATION_JSON
    value: '{"demo":{"message":"from-json"}}'
args: []
~~~

Dự kiến winner là `from-json`. Dùng JSON trong YAML như trên để không phải xử lý nhiều lớp escape của PowerShell và native command.

Không nhầm biến `SPRING_APPLICATION_JSON` với một biến môi trường thông thường chỉ được đọc tại vị trí systemEnvironment: Spring Boot tách nội dung JSON thành nguồn cấu hình có thứ tự riêng.

### 7.4. Lượt C: thêm command-line argument

~~~yaml
env:
  - name: DEMO_MESSAGE
    value: from-env
  - name: JAVA_TOOL_OPTIONS
    value: "-Ddemo.message=from-jvm"
  - name: SPRING_APPLICATION_JSON
    value: '{"demo":{"message":"from-json"}}'
args:
  - "--demo.message=from-cli"
~~~

Dự kiến winner là `from-cli`. Lúc này danh sách marker cần giải thích được:

~~~text
from-cli → from-json → from-jvm → from-env
         → from-cm-override → from-cm-base → from-secret → from-jar
~~~

Nếu giá trị không như dự kiến, trước tiên xác minh container args/env thực tế, Pod đang được truy cập và cấu hình có nằm trong đúng lần rollout hay không. Đừng đổi thứ tự sources trong ConfigMap để chữa một command-line override.

## 8. Gỡ từng lớp và xác định nguồn dự phòng

### 8.1. Gỡ theo thứ tự ngược lại

Từ lượt C, thực hiện các lượt riêng:

| Lượt | Thay đổi trong manifest | Winner dự kiến |
| --- | --- | --- |
| R1 | Bỏ args `--demo.message`, giữ ba env entry | `from-json` |
| R2 | Bỏ entry `SPRING_APPLICATION_JSON` | `from-jvm` |
| R3 | Bỏ entry `JAVA_TOOL_OPTIONS` | `from-env` |
| R4 | Bỏ entry `DEMO_MESSAGE`, trở về `env: []` | `from-cm-override` |

Sau mỗi lượt: apply, chờ rollout, chọn lại Pod, mở port-forward và ghi kết quả.

Mục tiêu không chỉ là thấy giá trị đổi. Cần chỉ ra ứng viên tiếp theo đã trở thành winner và các nguồn khác vẫn ở đúng thứ tự.

### 8.2. Bỏ marker khỏi ConfigMap override

Trong `k8s-resources.yaml`, sửa riêng phần `application.yaml` của `lab-override` thành:

~~~yaml
data:
  application.yaml: |-
    lab:
      loaded-from-override: true
~~~

Giữ nguyên resource và các tài nguyên còn lại. Sau đó:

~~~powershell
kubectl --context=$contextName apply -f k8s-resources.yaml
kubectl --context=$contextName rollout restart deployment/property-lab -n $ns
kubectl --context=$contextName rollout status deployment/property-lab -n $ns --timeout=180s
~~~

Sau khi kết nối lại Pod mới, dự kiến winner là `from-cm-base`.

Nguồn override vẫn có thể được nạp, nhưng không còn chứa key này. Việc nó không xuất hiện trong danh sách `candidates` không chứng minh source bị mất; danh sách chỉ gồm source có `demo.message`. Có thể kiểm tra riêng marker `lab.loaded-from-override` bằng cơ chế quan sát nội bộ thích hợp nếu cần.

### 8.3. Bỏ marker khỏi ConfigMap base

Sửa dữ liệu của `lab-base` thành:

~~~yaml
data:
  application.yaml: |-
    lab:
      loaded-from-base: true
~~~

Apply resource, restart Deployment, chờ rollout và quan sát lại. Khi không có lớp env/JVM/JSON/CLI, winner dự kiến là `from-secret`.

Đây là lượt chứng minh Secret đã được nạp từ trước nhưng bị ConfigMap che, thay vì suy từ việc resource Secret tồn tại trên cluster.

### 8.4. Tắt nguồn Secret để thấy giá trị từ JAR

Giữ cả hai ConfigMap không có `demo.message` như trên. Trong Deployment, dùng:

~~~yaml
env:
  - name: SPRING_CLOUD_KUBERNETES_SECRETS_ENABLED
    value: "false"
args: []
~~~

Apply và chờ rollout. Dự kiến winner là `from-jar`; nguồn Secret không còn tham gia theo cấu hình khởi động của lượt này.

Khôi phục dữ liệu hai ConfigMap và phần env/args về lượt cơ sở sau khi hoàn thành chuỗi. Không dùng xóa Secret thật như phương pháp tìm nguồn dự phòng trong hệ thống vận hành.

## 9. Phân biệt ghi đè với chưa nạp lại cấu hình

### 9.1. Thử thay ConfigMap khi JVM chưa khởi động lại

Trở về lượt cơ sở. Đổi marker trong `lab-override` thành `from-cm-override-v2` và chỉ apply `k8s-resources.yaml`, chưa restart Deployment.

Đọc lại `/lab/property` trên chính Pod đang chạy. Vì lab đã tắt reload và không triển khai Configuration Watcher, JVM không có lý do tự nạp lại PropertySource. Kết quả còn `from-cm-override` là phù hợp với thiết kế này.

Sau khi rollout restart và kết nối tới Pod mới, dự kiến thấy `from-cm-override-v2`.

| Lớp quan sát | Câu hỏi |
| --- | --- |
| Resource trên API server | ConfigMap đã lưu giá trị mới chưa? |
| Environment trong JVM | PropertySource đã được nạp lại chưa? |
| Bean nghiệp vụ | Bean đã bind/refresh hoặc được tạo lại chưa? |
| Replica được truy cập | Có đúng Pod/phiên bản cần kiểm tra không? |

### 9.2. Khi hệ thống có Configuration Watcher

Trong hệ thống đã có watcher, kiểm tra thêm nguồn được theo dõi, sự kiện, yêu cầu refresh và việc ứng dụng áp dụng thay đổi. Không chỉ thấy resource đổi rồi kết luận mọi bean phải đổi.

Các trường `environment`, `bound` và `injectedAtConstruction` có thể giúp định vị sự khác biệt. Tuy nhiên, controller trong lab không được gắn `@RefreshScope`; giá trị inject vào constructor không tự đọc lại ở mỗi request. Hành vi rebind/refresh phải được xác minh theo cơ chế thực sự bật.

Nếu Environment đã nạp marker mới nhưng `DEMO_MESSAGE` vẫn cung cấp một giá trị có ưu tiên cao hơn, refresh đúng vẫn không làm ConfigMap trở thành winner. Cần giải quyết nguồn ghi đè, không lặp refresh vô hạn.

### 9.3. envFrom là một đường đưa dữ liệu khác

Nếu cùng ConfigMap được đưa vào Pod bằng `envFrom` hoặc `env.valueFrom`, giá trị đó đi vào process environment. Còn trong lab, nguồn được đọc qua Kubernetes API thành PropertySource của Config Data.

Cùng resource Kubernetes có thể xuất hiện qua hai đường với hai mức ưu tiên khác nhau. Trường hợp đó, chỉnh danh sách `config.sources` không đổi thứ tự của biến môi trường đã được inject.

Biến môi trường được tạo từ ConfigMap không tự thay đổi trong process đang chạy khi ConfigMap đổi; cần tạo lại Pod để nhận giá trị mới theo cách đó. Xem [ConfigMaps của Kubernetes](https://kubernetes.io/docs/concepts/configuration/configmap/).

## 10. Các biến thể giúp kiểm tra khả năng chẩn đoán

### 10.1. Chuỗi rỗng khác với không có key

Từ cấu hình không có CLI/JSON/JVM override, thử:

~~~yaml
env:
  - name: DEMO_MESSAGE
    value: ""
args: []
~~~

Chuỗi rỗng là một giá trị tồn tại. Dự kiến Environment và bean nhận chuỗi rỗng, không tự rơi xuống ConfigMap hoặc giá trị mặc định của `@Value`.

Khi ghi báo cáo, biểu diễn rõ `""` thay vì để ô trống, tránh nhầm với chưa quan sát hoặc không có thuộc tính.

### 10.2. JSON null không phải cách xóa giá trị thấp hơn

Trong lượt có Java system property `from-jvm`, đổi JSON thành:

~~~yaml
- name: SPRING_APPLICATION_JSON
  value: '{"demo":{"message":null}}'
~~~

Null trong nguồn JSON không che giá trị ở nguồn thấp hơn theo cơ chế của Spring Boot; dự kiến `from-jvm` lại có hiệu lực. Đây là khác biệt cần kiểm tra khi một công cụ sinh JSON dùng null để biểu diễn “không đặt”.

Không dùng null như một quy tắc xóa property chung cho mọi loại nguồn.

### 10.3. Prefix làm đổi tên key

Sau khi loại hết lớp override ở cấp process, có thể thử cấu hình source override với:

~~~yaml
spring:
  cloud:
    kubernetes:
      config:
        sources:
          - name: lab-base
          - name: lab-override
            explicit-prefix: override
~~~

Nguồn override lúc này cung cấp key dạng `override.demo.message` thay vì cạnh tranh trực tiếp với `demo.message`. Đây là đổi namespace của key, không phải giảm mức ưu tiên.

Biến thể sửa cấu hình đóng gói nên phải build image với tag mới, nạp image và cập nhật Deployment; chỉ sửa file trên máy không thay nội dung JAR đang chạy.

### 10.4. Profile tạo thêm nguồn cần truy vết

Lượt cơ sở tắt `include-profile-specific-sources`. Nếu bật lại và kích hoạt profile, có thể có thêm nguồn Kubernetes tương ứng profile, hoặc thêm tài liệu cấu hình trong JAR.

Khi kết quả khác dự kiến, ghi `activeProfiles` và tên source thực tế. Kiểm tra nguồn theo profile theo [ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config/configmap-propertysource.html), không chỉ tìm tên ConfigMap gốc.

### 10.5. Nhiều replica có thể đang giữ các ảnh chụp khác nhau

Thử tăng `replicas` lên hai, rồi quan sát từng Pod bằng port-forward với cổng local khác nhau. Luôn ghi trường `pod` của response.

Trong lúc rollout, hai Pod có thể chạy image, env hoặc ảnh chụp nguồn lúc khởi động khác nhau. Gọi qua Service cân bằng tải có thể khiến giá trị trông như thay đổi ngẫu nhiên dù từng Pod nhất quán.

Không gọi đó là xung đột thứ tự ưu tiên trước khi loại trừ khác biệt replica và thời điểm nạp cấu hình.

## 11. Runbook khi giá trị thực tế không đúng dự đoán

| Hiện tượng | Điều cần kiểm tra trước | Bằng chứng quyết định |
| --- | --- | --- |
| Không có candidate ConfigMap | Đường import, quyền, tên/namespace và key | Log nạp nguồn, tên source, dữ liệu marker |
| Có candidate nhưng không thắng | Các source phía trên cho cùng key | Danh sách ứng viên theo thứ tự |
| Đổi ConfigMap nhưng JVM giữ giá trị cũ | Reload/refresh có được bật và chạy không | So sánh resource, Environment và Pod |
| Environment mới nhưng bean cũ | Vòng đời bean, rebind/refresh và cache | So sánh ba trường giá trị của probe |
| Giá trị thắng từ systemEnvironment | Env trực tiếp, envFrom hoặc valueFrom | Pod template và source runtime |
| Chỉ một số request thấy giá trị khác | Nhiều replica hoặc rollout chưa hoàn tất | Pod, image và thời điểm quan sát |
| Actuator trả dấu sao | Sanitization | Source/origin và điểm quan sát marker |
| Chuỗi rỗng thắng mọi nguồn dưới | Key có tồn tại với giá trị rỗng | Response JSON thể hiện `""` |
| Giá trị khác giữa local và Pod | Profile, bootstrap, biến môi trường hoặc nguồn ngoài JAR | Bộ source runtime của từng môi trường |

Trình tự điều tra:

~~~mermaid
flowchart TD
    A[Giá trị không như dự đoán] --> B[Xác định key canonical và Pod]
    B --> C[Đọc giá trị Environment]
    C --> D[Liệt kê các source có cùng key]
    D --> E{Nguồn mong muốn có key?}
    E -->|Không| F[Kiểm tra nạp nguồn, namespace, quyền và tên key]
    E -->|Có nhưng bị che| G[Xác định nguồn ưu tiên cao hơn]
    E -->|Có và đang thắng| H[Kiểm tra bean, refresh và cache nghiệp vụ]
~~~

Không bắt đầu bằng xóa biến môi trường hoặc Secret trên một workload thật. Trước tiên chứng minh nguồn nào cung cấp giá trị hiệu lực và mục đích của nguồn đó.

## 12. Bằng chứng bàn giao và tiêu chí hoàn thành

Với mỗi lượt, lưu bản ghi không nhạy cảm:

| Trường | Nội dung |
| --- | --- |
| Lượt thử | Cơ sở, E, J, G, C hoặc R1–R4 |
| Bộ phiên bản | Boot, Cloud BOM, Kubernetes client đã resolve |
| Workload | Namespace, Deployment, Pod, image/tag hoặc digest |
| Thời điểm | Sau rollout, sau apply nguồn hay trước refresh |
| Key | `demo.message` |
| Giá trị | Environment, bound, injectedAtConstruction |
| Winner | Tên source thực tế và origin nếu có |
| Nguồn bị che | Danh sách các ứng viên còn lại |
| Kết luận | Ghi đè, chưa nạp lại, chưa bind/refresh hoặc khác replica |

Đạt yêu cầu bài thực hành khi:

1. Dự đoán và giải thích đúng winner trong chuỗi ConfigMap/Secret/JAR.
2. Chứng minh thứ tự env, system property, JSON và command-line bằng các lượt riêng.
3. Gỡ từng lớp và thấy nguồn dự phòng tương ứng.
4. Phân biệt source không được nạp với source có mặt nhưng bị che.
5. Phân biệt cập nhật resource, cập nhật Environment và cập nhật bean.
6. Quan sát đúng Pod, giữ các giá trị nhạy cảm được che và không mở endpoint dump tùy ý.
7. Nêu được cách giới hạn nguồn, đặt prefix hoặc bỏ override dư thừa khi áp dụng vào hệ thống thật.

Sau lab, có thể xóa riêng các resource đã tạo bằng manifest nếu không cần giữ:

~~~powershell
kubectl --context=$contextName delete -f deployment.yaml
kubectl --context=$contextName delete -f k8s-resources.yaml
~~~

Manifest thứ hai có Namespace `property-lab` nên thao tác xóa cũng xóa namespace và tài nguyên bên trong. Chỉ dùng khi namespace này dành riêng cho lab và không chứa công việc khác cần giữ.
