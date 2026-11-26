# Kiểm thử DiscoveryClient với nhiều Service và endpoint

## 1. Mục tiêu và ranh giới kiểm thử

Trong chương **Kiểm thử tự động** của module **SPRING_CLOUD_KUBERNETES**, DiscoveryClient cần được kiểm chứng bằng dữ liệu có thể phân biệt các lỗi ghép Service, chọn endpoint và chọn cổng. Một test chỉ khẳng định “danh sách không rỗng” có thể vẫn xanh khi client trả về toàn bộ endpoint của một Service khác.

Sau bài học, bạn cần xây dựng được bộ kiểm thử trả lời các câu hỏi:

- `getServices()` có trả đúng các Service thuộc phạm vi đã cấu hình không?
- `getInstances(serviceId)` có trả đúng địa chỉ của Service được hỏi, không lẫn Service khác?
- Client có chọn đúng cổng backend khi Service công bố nhiều cổng không?
- Endpoint chưa Ready có được đưa vào kết quả đúng theo cấu hình không?
- Sau khi thêm hoặc bớt replica, kết quả có hội tụ về tập instance mới không?
- Test đang dùng implementation Kubernetes thật hay một mock trả lại dữ liệu được lập trình sẵn?

DiscoveryClient cung cấp dữ liệu discovery. Nó không tự chứng minh rằng mọi địa chỉ đều gọi HTTP thành công, và không chứng minh Spring Cloud LoadBalancer đã phân phối lời gọi theo một chiến lược cụ thể. Các yêu cầu ấy cần lớp kiểm thử riêng.

### 1.1. Phân biệt ba lớp kiểm thử

| Lớp kiểm thử | Đối tượng được kiểm chứng | Giới hạn kết luận |
| --- | --- | --- |
| Unit test code sử dụng discovery | Logic ứng dụng khi nhận danh sách instance, danh sách rỗng hoặc lỗi | Mock DiscoveryClient không kiểm tra ánh xạ Kubernetes |
| Integration test adapter/client | Client Spring chuyển dữ liệu Kubernetes thành ServiceInstance | Cần biết API, cấu hình và hành vi mock server hoặc API server thực |
| Kiểm thử trong cụm | Discovery cùng API, danh tính workload, controller và cập nhật tài nguyên | Còn phụ thuộc mạng, runtime và thành phần thực tế được triển khai |

Ví dụ chính trong bài chạy JUnit bên trong một Kubernetes Job và dùng Kubernetes API thật. Các backend có thể là ứng dụng echo nhỏ vì mục tiêu là kiểm tra dữ liệu discovery; không cần dựng toàn bộ nghiệp vụ, ConfigMap, Secret hay Configuration Watcher.

### 1.2. Khóa implementation và API trước khi viết fixture

Phải ghi rõ ít nhất bốn thông tin: Spring Boot, Spring Cloud BOM, implementation Kubernetes client và API endpoint đang kiểm thử.

Ví dụ chọn:

| Thành phần | Phạm vi minh họa |
| --- | --- |
| Java | 21 |
| Spring Boot | 3.5.0 |
| Spring Cloud BOM | 2025.0.0 |
| Spring Cloud Kubernetes | Được BOM quản lý, thuộc dòng 3.3.0 |
| Implementation | Fabric8 |
| API trong ví dụ chính | `core/v1 Endpoints` |
| Chế độ discovery | Blocking, không bật cache bổ sung |

Cặp phiên bản Boot/BOM trên đã được công bố tương thích trong [thông báo Spring Cloud 2025.0.0](https://spring.io/blog/2025/05/29/spring-cloud-2025-0-0-is-abvailable/). Đây là bộ phiên bản cố định để minh họa, không phải yêu cầu nâng/hạ phiên bản của mọi dự án. Dự án dùng bộ phiên bản khác cần áp dụng cùng hợp đồng test với dependency đã chọn.

Ví dụ chủ động kiểm tra nhánh tương thích Endpoints. Kubernetes đã đánh dấu Endpoints là API cũ và khuyến khích EndpointSlice; xem [Service của Kubernetes](https://kubernetes.io/docs/concepts/services-networking/service/). Nếu triển khai dùng EndpointSlice, bổ sung nhánh kiểm thử tương ứng ở phần cuối; kết quả của test Endpoints không đại diện cho nhánh đó.

Không trộn starter Fabric8, Kubernetes Java Client và HTTP DiscoveryClient trong cùng fixture rồi suy rằng mọi implementation đều đã được kiểm chứng. Đối chiếu [DiscoveryClient của Spring Cloud Kubernetes dòng 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/discovery-client.html) với cấu hình của dự án.

## 2. Xây dựng fixture có khả năng bắt lỗi

### 2.1. Ma trận tài nguyên

Mỗi lần chạy sử dụng một namespace riêng, với các tài nguyên:

| Service | Pod được chọn | Cổng Service → backend | Kỳ vọng mặc định |
| --- | --- | --- | --- |
| `catalog` | Hai Pod Ready và một Pod chưa Ready | `api: 80 → 8080`, `admin: 90 → 9090` | Hai instance, dùng cổng 8080 |
| `billing` | Một Pod Ready | `api: 80 → 8082` | Một instance, dùng cổng 8082 |
| `empty` | Không có Pod | `api: 80 → 8080` | Có tên Service nhưng không có instance |
| `excluded` | Chọn cùng backend với billing, khác label discovery | `api: 80 → 8082` | Bị bộ lọc loại bỏ |
| `missing` | Không tạo Service | Không có | Không có instance |

Đặt label `primary-port-name=api` cho Service catalog để lựa chọn cổng là tường minh. Cổng admin được đặt trước trong manifest nhằm bắt test phụ thuộc vị trí phần tử.

Địa chỉ kỳ vọng lấy từ Pod IP thực tế. Không hard-code IP của lần chạy trước và không dùng ClusterIP làm địa chỉ mong đợi của instance backend.

### 2.2. Các assertion có ý nghĩa

Với mỗi Service, kiểm tra đồng thời:

1. Số lượng và tập host đúng, không thêm và không thiếu.
2. `serviceId` đúng.
3. Cổng instance đúng backend port đã thiết kế.
4. Namespace metadata đúng.
5. Scheme/security phù hợp với hợp đồng fixture.
6. Không trùng cặp host/port trong phạm vi fixture này.

Dùng so sánh không phụ thuộc thứ tự nhưng vẫn bảo toàn số lần xuất hiện. Chuyển kết quả sang `Set` trước khi assert có thể che lỗi client trả trùng.

Oracle của bài lấy danh tính backend từ Pod status, còn cổng kỳ vọng là giá trị đã định trong hợp đồng fixture. Không tạo expected bằng cách gọi lại cùng DiscoveryClient hoặc sao chép chính thuật toán chọn cổng đang cần kiểm tra.

## 3. Dự án Maven tối thiểu cho integration test

Tạo một dự án kiểm thử riêng với cấu trúc:

~~~text
discovery-it/
  pom.xml
  Dockerfile
  fixtures.yaml
  discovery-rbac.yaml
  discovery-job.yaml
  src/test/java/com/example/discovery/DiscoveryTestApplication.java
  src/test/java/com/example/discovery/DiscoveryClientIT.java
  src/test/resources/application-discovery-it.properties
~~~

Các đường dẫn trong ví dụ là tệp bạn tạo trong thư mục thực hành. Bài học không yêu cầu sửa code sản phẩm để mở endpoint quản trị hoặc đưa thư viện kiểm thử vào image phát hành.

### 3.1. Dependency và cách kích hoạt

Nội dung `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>discovery-it</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>21</java.version>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-dependencies</artifactId>
        <version>2025.0.0</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>

  <dependencies>
    <dependency>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-starter-kubernetes-fabric8</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.awaitility</groupId>
      <artifactId>awaitility</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <profiles>
    <profile>
      <id>cluster-it</id>
      <build>
        <plugins>
          <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-failsafe-plugin</artifactId>
            <configuration>
              <failIfNoTests>true</failIfNoTests>
              <includes>
                <include>**/*IT.java</include>
              </includes>
            </configuration>
            <executions>
              <execution>
                <goals>
                  <goal>integration-test</goal>
                  <goal>verify</goal>
                </goals>
              </execution>
            </executions>
          </plugin>
        </plugins>
      </build>
    </profile>
  </profiles>
</project>
~~~

Không cần Spring Boot repackage plugin vì image thực hành chạy Maven/JUnit, không chạy executable JAR của sản phẩm. Phiên bản plugin và các dependency kiểm thử được parent/BOM quản lý.

Maven Failsafe được gắn vào cả `integration-test` và `verify`; lệnh cần dùng là `mvn -Pcluster-it verify`. Chỉ gọi một phase trước `verify` có thể không làm build thất bại đúng theo kết quả integration test. Xem [Maven Failsafe: cách sử dụng](https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html).

### 3.2. Spring context kiểm thử

Tệp `DiscoveryTestApplication.java`:

~~~java
package com.example.discovery;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;

@SpringBootConfiguration
@EnableAutoConfiguration
@EnableDiscoveryClient
public class DiscoveryTestApplication {
}
~~~

Tệp `application-discovery-it.properties`:

~~~properties
spring.application.name=discovery-it
spring.main.web-application-type=none

spring.cloud.discovery.enabled=true
spring.cloud.kubernetes.discovery.enabled=true
spring.cloud.kubernetes.discovery.all-namespaces=false
spring.cloud.kubernetes.discovery.use-endpoint-slices=false
spring.cloud.kubernetes.discovery.include-external-name-services=false
spring.cloud.kubernetes.discovery.service-labels.test-suite=discovery-it

spring.cloud.kubernetes.discovery.metadata.add-labels=true
spring.cloud.kubernetes.discovery.metadata.labels-prefix=svc.
spring.cloud.kubernetes.discovery.metadata.add-annotations=false
spring.cloud.kubernetes.discovery.metadata.add-pod-labels=false
spring.cloud.kubernetes.discovery.metadata.add-pod-annotations=false

spring.cloud.kubernetes.discovery.cacheable.blocking.enabled=false
spring.cloud.kubernetes.discovery.cacheable.reactive.enabled=false

spring.cloud.kubernetes.config.enabled=false
spring.cloud.kubernetes.secrets.enabled=false
~~~

Namespace và tùy chọn include-not-ready sẽ được truyền bằng `@DynamicPropertySource` trong lớp test. Không có cấu hình static instance cho SimpleDiscoveryClient, không dùng `@MockBean` thay thế DiscoveryClient và không bật cơ chế refresh cấu hình ngoài mục tiêu bài.

## 4. Tạo các Service và backend phân biệt được nhau

Lưu nội dung sau thành `fixtures.yaml`. Tài nguyên không khai báo namespace để lệnh apply có thể đưa toàn bộ fixture vào namespace riêng của lần chạy.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-ready
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog
      cohort: ready
  template:
    metadata:
      labels:
        app: catalog
        cohort: ready
    spec:
      automountServiceAccountToken: false
      containers:
        - name: echo
          image: hashicorp/http-echo:1.0.0
          args: ["-listen=:8080", "-text=catalog"]
          ports:
            - name: api
              containerPort: 8080
          readinessProbe:
            tcpSocket:
              port: api
            periodSeconds: 2
          resources:
            requests:
              cpu: 10m
              memory: 16Mi
            limits:
              cpu: 200m
              memory: 64Mi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-not-ready
spec:
  replicas: 1
  selector:
    matchLabels:
      app: catalog
      cohort: not-ready
  template:
    metadata:
      labels:
        app: catalog
        cohort: not-ready
    spec:
      automountServiceAccountToken: false
      containers:
        - name: echo
          image: hashicorp/http-echo:1.0.0
          args: ["-listen=:8080", "-text=catalog-not-ready"]
          ports:
            - name: api
              containerPort: 8080
          readinessProbe:
            tcpSocket:
              port: 65534
            periodSeconds: 2
          resources:
            requests:
              cpu: 10m
              memory: 16Mi
            limits:
              cpu: 200m
              memory: 64Mi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: billing
spec:
  replicas: 1
  selector:
    matchLabels:
      app: billing
  template:
    metadata:
      labels:
        app: billing
    spec:
      automountServiceAccountToken: false
      containers:
        - name: echo
          image: hashicorp/http-echo:1.0.0
          args: ["-listen=:8082", "-text=billing"]
          ports:
            - name: api
              containerPort: 8082
          readinessProbe:
            tcpSocket:
              port: api
            periodSeconds: 2
          resources:
            requests:
              cpu: 10m
              memory: 16Mi
            limits:
              cpu: 200m
              memory: 64Mi
---
apiVersion: v1
kind: Service
metadata:
  name: catalog
  labels:
    test-suite: discovery-it
    team: catalog
    primary-port-name: api
spec:
  publishNotReadyAddresses: false
  selector:
    app: catalog
  ports:
    - name: admin
      port: 90
      targetPort: 9090
    - name: api
      port: 80
      targetPort: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: billing
  labels:
    test-suite: discovery-it
    team: billing
spec:
  selector:
    app: billing
  ports:
    - name: api
      port: 80
      targetPort: 8082
---
apiVersion: v1
kind: Service
metadata:
  name: empty
  labels:
    test-suite: discovery-it
spec:
  selector:
    app: no-such-backend
  ports:
    - name: api
      port: 80
      targetPort: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: excluded
  labels:
    test-suite: other-suite
spec:
  selector:
    app: billing
  ports:
    - name: api
      port: 80
      targetPort: 8082
~~~

http-echo có thể cấu hình cổng nghe bằng `-listen` và nội dung phản hồi bằng `-text`; xem [README của http-echo](https://github.com/hashicorp/http-echo/blob/main/README.md).

Pod catalog-not-ready chạy server nhưng probe cố ý kiểm tra cổng không được mở. Vì chỉ readiness thất bại, container có thể tiếp tục chạy mà không bị restart vì lỗi probe đó. Không chờ Deployment này rollout thành công: trạng thái chưa Ready là một phần dữ liệu kiểm thử.

Cổng admin 9090 chỉ dùng để kiểm tra chọn cổng; fixture không chạy server admin tại đó. Test discovery sẽ phát hiện việc chọn nhầm cổng bằng assertion, còn test HTTP nếu có chỉ gọi cổng api.

Kubernetes controller tự tạo Endpoints và EndpointSlice từ selector của Service. Không patch tay các đối tượng do controller quản lý rồi mong dữ liệu cố định; thay đổi replica hoặc readiness của Pod để tạo trạng thái mong muốn.

## 5. Mã kiểm thử DiscoveryClient thật

Tệp `DiscoveryClientIT.java` sau đây sử dụng JUnit, AssertJ và Awaitility. Thay đổi tài nguyên được thực hiện qua KubernetesClient; dữ liệu cần kiểm chứng được lấy qua DiscoveryClient của Spring.

~~~java
package com.example.discovery;

import java.time.Duration;
import java.util.List;
import java.util.Objects;

import io.fabric8.kubernetes.api.model.Pod;
import io.fabric8.kubernetes.client.KubernetesClient;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest(
    classes = DiscoveryTestApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("discovery-it")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@Execution(ExecutionMode.SAME_THREAD)
class DiscoveryClientIT {

    private static final String NAMESPACE =
        Objects.requireNonNull(System.getenv("TEST_NAMESPACE"),
            "TEST_NAMESPACE must identify the isolated test namespace");

    private static final boolean INCLUDE_NOT_READY =
        Boolean.parseBoolean(
            System.getenv().getOrDefault("INCLUDE_NOT_READY", "false")
        );

    @DynamicPropertySource
    static void discoveryProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.cloud.kubernetes.client.namespace",
            () -> NAMESPACE
        );
        registry.add(
            "spring.cloud.kubernetes.discovery.namespaces[0]",
            () -> NAMESPACE
        );
        registry.add(
            "spring.cloud.kubernetes.discovery.include-not-ready-addresses",
            () -> INCLUDE_NOT_READY
        );
    }

    @Autowired
    ApplicationContext context;

    @Autowired
    KubernetesClient kubernetes;

    private DiscoveryClient discovery;

    @BeforeAll
    void selectRealKubernetesDiscoveryClient() {
        assertThat(NAMESPACE).startsWith("sck-discovery-");

        List<DiscoveryClient> providers =
            context.getBeansOfType(DiscoveryClient.class)
                .values()
                .stream()
                .filter(bean -> bean.getClass().getName()
                    .startsWith("org.springframework.cloud.kubernetes.fabric8."))
                .toList();

        assertThat(providers)
            .as("one real Fabric8 discovery provider must exist")
            .hasSize(1);

        discovery = providers.getFirst();
    }

    @BeforeEach
    void waitForBaseline() {
        convergesTo(2);
    }

    @AfterEach
    void restoreReplicaCount() {
        kubernetes.apps()
            .deployments()
            .inNamespace(NAMESPACE)
            .withName("catalog-ready")
            .scale(2);

        convergesTo(2);
    }

    @Test
    void listsOnlyServicesSelectedByLabels() {
        assertThat(discovery.getServices())
            .containsExactlyInAnyOrder("catalog", "billing", "empty");
    }

    @Test
    void mapsEachServiceToItsOwnBackendAddressesAndPort() {
        assertAllInstances(2);
    }

    @Test
    void returnsNoInstancesForEmptyUnknownAndExcludedServices() {
        assertAllInstances(2);

        assertThat(discovery.getServices()).contains("empty");
        assertThat(discovery.getInstances("empty")).isEmpty();
        assertThat(discovery.getInstances("missing")).isEmpty();
        assertThat(discovery.getInstances("excluded")).isEmpty();
    }

    @Test
    void reflectsReplicaAdditionAndRemoval() {
        kubernetes.apps()
            .deployments()
            .inNamespace(NAMESPACE)
            .withName("catalog-ready")
            .scale(3);

        convergesTo(3);

        kubernetes.apps()
            .deployments()
            .inNamespace(NAMESPACE)
            .withName("catalog-ready")
            .scale(1);

        convergesTo(1);
    }

    private void convergesTo(int readyCatalogReplicas) {
        await()
            .alias("discovery converges in namespace " + NAMESPACE
                + ", ready catalog replicas=" + readyCatalogReplicas
                + ", includeNotReady=" + INCLUDE_NOT_READY)
            .pollInterval(Duration.ofMillis(500))
            .atMost(Duration.ofSeconds(90))
            .untilAsserted(() -> assertAllInstances(readyCatalogReplicas));
    }

    private void assertAllInstances(int readyCatalogReplicas) {
        List<Pod> catalogPods = livePods("catalog");

        List<Pod> readyCohort = catalogPods.stream()
            .filter(pod -> "ready".equals(
                pod.getMetadata().getLabels().get("cohort")))
            .toList();

        List<Pod> notReadyCohort = catalogPods.stream()
            .filter(pod -> "not-ready".equals(
                pod.getMetadata().getLabels().get("cohort")))
            .toList();

        assertThat(catalogPods).hasSize(readyCatalogReplicas + 1);
        assertThat(readyCohort)
            .hasSize(readyCatalogReplicas)
            .allMatch(this::isReady);

        assertThat(notReadyCohort).hasSize(1);
        assertThat(notReadyCohort.getFirst().getStatus().getPhase())
            .isEqualTo("Running");
        assertThat(isReady(notReadyCohort.getFirst())).isFalse();

        List<Pod> billingPods = livePods("billing");
        assertThat(billingPods).hasSize(1).allMatch(this::isReady);

        List<String> catalogHosts =
            selectedHosts(catalogPods);
        List<String> billingHosts =
            selectedHosts(billingPods);

        assertThat(catalogHosts)
            .hasSize(readyCatalogReplicas + (INCLUDE_NOT_READY ? 1 : 0));

        assertThat(discovery.getServices())
            .containsExactlyInAnyOrder("catalog", "billing", "empty");

        assertInstances("catalog", 8080, catalogHosts);
        assertInstances("billing", 8082, billingHosts);
    }

    private List<Pod> livePods(String app) {
        return kubernetes.pods()
            .inNamespace(NAMESPACE)
            .withLabel("app", app)
            .list()
            .getItems()
            .stream()
            .filter(pod -> pod.getMetadata().getDeletionTimestamp() == null)
            .filter(pod -> pod.getStatus() != null)
            .toList();
    }

    private boolean isReady(Pod pod) {
        return pod.getStatus() != null
            && pod.getStatus().getConditions() != null
            && pod.getStatus().getConditions().stream().anyMatch(condition ->
                "Ready".equals(condition.getType())
                    && "True".equals(condition.getStatus()));
    }

    private List<String> selectedHosts(List<Pod> pods) {
        List<Pod> selected = pods.stream()
            .filter(pod -> INCLUDE_NOT_READY || isReady(pod))
            .toList();

        assertThat(selected).allSatisfy(pod ->
            assertThat(pod.getStatus().getPodIP()).isNotBlank());

        return selected.stream()
            .map(pod -> pod.getStatus().getPodIP())
            .toList();
    }

    private void assertInstances(
        String serviceId,
        int expectedPort,
        List<String> expectedHosts
    ) {
        List<ServiceInstance> actual = discovery.getInstances(serviceId);

        assertThat(actual)
            .as("hosts of service %s", serviceId)
            .extracting(ServiceInstance::getHost)
            .containsExactlyInAnyOrderElementsOf(expectedHosts);

        assertThat(actual)
            .extracting(ServiceInstance::getHost, ServiceInstance::getPort)
            .doesNotHaveDuplicates();

        assertThat(actual).allSatisfy(instance -> {
            assertThat(instance.getServiceId()).isEqualTo(serviceId);
            assertThat(instance.getPort()).isEqualTo(expectedPort);
            assertThat(instance.isSecure()).isFalse();
            assertThat(instance.getUri().getScheme()).isEqualTo("http");
            assertThat(instance.getMetadata())
                .containsEntry("k8s_namespace", NAMESPACE)
                .containsEntry("svc.team", serviceId);
        });
    }
}
~~~

### 5.1. Những lỗi bộ test có thể phát hiện

- Trả địa chỉ billing khi được hỏi catalog: so sánh host thất bại.
- Trả Service port 80 thay vì backend port 8080/8082: assertion cổng thất bại.
- Lấy cổng đầu tiên trong fixture catalog: giá trị admin 9090 không đạt hợp đồng.
- Bỏ qua label discovery: danh sách Service hoặc ca excluded thất bại.
- Trả endpoint chưa Ready trong chế độ mặc định: số lượng và tập host không đúng.
- Giữ endpoint đã bị loại sau scale-down: tập host không hội tụ.
- Trả trùng endpoint: kiểm tra số lần xuất hiện và duplicate thất bại.
- Không có implementation Kubernetes thật trong context: bước chọn provider thất bại.

Việc chọn provider ở đây có chủ đích gắn với Fabric8 để tránh một CompositeDiscoveryClient hoặc SimpleDiscoveryClient che mất việc cấu hình sai. Nếu mục tiêu là kiểm tra chính bean Composite mà code sản phẩm sử dụng, thêm một test riêng cho wiring và tập kết quả của bean đó.

### 5.2. Vì sao dùng Awaitility?

Kubernetes controller, trạng thái Ready và dữ liệu client không cập nhật đồng thời với lệnh scale. Awaitility poll điều kiện thực tế trong giới hạn đã định, thay cho `Thread.sleep` theo phỏng đoán.

Lệnh scale nằm ngoài vòng poll. Nếu đặt mutation trong `untilAsserted`, mỗi lần thử có thể phát sinh thao tác mới và làm sai ý nghĩa của test. Cũng không bắt rồi bỏ qua mọi exception: lỗi HTTP 403 hoặc cấu hình sai cần được lộ ra để điều tra.

Cách dùng `untilAsserted` và giới hạn thời gian được mô tả trong [Awaitility Usage](https://github.com/awaitility/awaitility/wiki/Usage). Lifecycle và chế độ chạy tuần tự thuộc [JUnit 5](https://docs.junit.org/5.12.2/user-guide/).

`@AfterEach` đưa replica về baseline ngay cả khi assertion thất bại. Tài nguyên vẫn thuộc namespace của lần chạy; bước dọn namespace sẽ do phần điều phối thực hiện sau khi thu thập bằng chứng.

Trong bộ phiên bản minh họa, namespace được đưa vào metadata bằng key `k8s_namespace`, còn label team được thêm prefix thành `svc.team`. Assertion phải theo đúng hợp đồng metadata của implementation; xem [hằng số discovery của bản 3.3.0](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.0/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/discovery/KubernetesDiscoveryConstants.java).

## 6. Quyền của Job kiểm thử

Tạo `discovery-rbac.yaml`:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: discovery-it
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: discovery-it
rules:
  - apiGroups: [""]
    resources: ["pods", "services", "endpoints"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get"]
  - apiGroups: ["apps"]
    resources: ["deployments/scale"]
    resourceNames: ["catalog-ready"]
    verbs: ["get", "patch", "update"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: discovery-it
subjects:
  - kind: ServiceAccount
    name: discovery-it
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: discovery-it
~~~

Role có hai mục đích khác nhau:

- Quyền đọc Pod/Service/Endpoints phục vụ discovery và xây dựng oracle.
- Quyền scale catalog-ready phục vụ tạo biến động fixture.

Quyền scale là quyền của **test harness**, không phải yêu cầu chung cho ứng dụng dùng DiscoveryClient. Bộ test này cũng không chứng minh ứng dụng sản phẩm hoạt động với Role chỉ đọc tối thiểu, vì Job đang có thêm quyền điều khiển fixture.

Nếu mục tiêu là kiểm chứng RBAC tối thiểu, tách identity tạo/scale fixture khỏi identity của ứng dụng cần kiểm tra. Không thêm quyền đọc Secret hoặc ConfigMap vì bài này không sử dụng chúng. Tham khảo [ServiceAccount của Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/security-service-accounts.html).

## 7. Đóng gói và chạy test trong cụm

### 7.1. Image chỉ dành cho kiểm thử

Tạo `Dockerfile`:

~~~dockerfile
FROM maven:3.9.9-eclipse-temurin-21
WORKDIR /tests
COPY pom.xml .
COPY src ./src
RUN mvn -B -DskipTests test-compile
ENTRYPOINT ["mvn", "-B", "-Pcluster-it", "verify"]
~~~

Lớp build chỉ biên dịch test; các test Kubernetes được thực thi khi Job chạy. Image này chứa Maven và mã kiểm thử nên không dùng làm image phát hành sản phẩm.

Build từ thư mục dự án:

~~~powershell
docker build -t sck-discovery-it:dev-001 .
~~~

Với kind:

~~~powershell
kind load docker-image sck-discovery-it:dev-001 --name sck-local
~~~

Với minikube:

~~~powershell
minikube image load sck-discovery-it:dev-001 -p sck-local
~~~

Với cụm từ xa, push vào registry mà node truy cập được và dùng địa chỉ image đó trong Job. Không dùng lệnh load của cụm cục bộ để suy rằng image đã có ở node từ xa.

### 7.2. Job thực thi JUnit

Tạo `discovery-job.yaml`:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: discovery-it
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 900
  template:
    metadata:
      labels:
        app: discovery-it-runner
    spec:
      serviceAccountName: discovery-it
      automountServiceAccountToken: true
      restartPolicy: Never
      containers:
        - name: tests
          image: sck-discovery-it:dev-001
          imagePullPolicy: Never
          env:
            - name: TEST_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
            - name: INCLUDE_NOT_READY
              value: "false"
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: "2"
              memory: 1536Mi
~~~

`imagePullPolicy: Never` phù hợp khi đã load image vào cụm lab. Nếu dùng registry, đổi policy theo quy trình pull. Backend echo vẫn cần image có trên node hoặc được pull thành công.

Job cần kết nối tới Kubernetes API. Ví dụ Maven cũng có thể tải thêm plugin/dependency khi chạy; nếu CI không cho truy cập repository bên ngoài, chuẩn bị mirror hoặc cache đầy đủ rồi kiểm tra đường chạy offline riêng.

`backoffLimit: 0` giúp một lần test thất bại không bị retry toàn bộ rồi che mất tín hiệu không ổn định. `activeDeadlineSeconds` giới hạn thời gian Job, khác giới hạn hội tụ 90 giây của từng assertion. Xem [Job của Kubernetes](https://kubernetes.io/docs/concepts/workloads/controllers/job/).

### 7.3. Namespace riêng cho từng lần chạy

Các lệnh dùng PowerShell, giả định đã có cụm IPv4 single-stack và context phù hợp:

~~~powershell
$KubeContext = 'kind-sck-local'
$TestNamespace = 'sck-discovery-' + [guid]::NewGuid().ToString('N').Substring(0, 8)

kubectl --context $KubeContext create namespace $TestNamespace
kubectl --context $KubeContext -n $TestNamespace apply -f fixtures.yaml
kubectl --context $KubeContext -n $TestNamespace apply -f discovery-rbac.yaml
~~~

Dùng context của profile nếu chọn minikube. Xác nhận các lệnh apply thành công trước khi tiếp tục.

Có thể xem nhanh fixture:

~~~powershell
kubectl --context $KubeContext -n $TestNamespace get services
kubectl --context $KubeContext -n $TestNamespace get pods -o wide
kubectl --context $KubeContext -n $TestNamespace get endpoints catalog billing empty
~~~

Đối với catalog-not-ready, `Running` nhưng `0/1 Ready` là trạng thái cố ý. Đừng sửa probe để “làm cụm xanh” trước khi chạy test.

Tạo Job:

~~~powershell
kubectl --context $KubeContext -n $TestNamespace apply -f discovery-job.yaml
~~~

### 7.4. Theo dõi cả Complete lẫn Failed

Tạo Job thành công chỉ chứng minh API chấp nhận tài nguyên. CI phải chờ trạng thái kết thúc và trả lỗi khi test hoặc hạ tầng thất bại.

Ví dụ PowerShell có giới hạn thời gian:

~~~powershell
$DeadlineUtc = [DateTime]::UtcNow.AddMinutes(16)
$JobSucceeded = $false

while ([DateTime]::UtcNow -lt $DeadlineUtc) {
    $JobJson = kubectl --context $KubeContext -n $TestNamespace get job discovery-it -o json
    if ($LASTEXITCODE -ne 0) {
        throw 'Cannot read test Job state'
    }

    $JobState = $JobJson | ConvertFrom-Json

    if ($JobState.status.conditions | Where-Object {
        $_.type -eq 'Failed' -and $_.status -eq 'True'
    }) {
        break
    }

    if ($JobState.status.conditions | Where-Object {
        $_.type -eq 'Complete' -and $_.status -eq 'True'
    }) {
        $JobSucceeded = $true
        break
    }

    Start-Sleep -Seconds 2
}

kubectl --context $KubeContext -n $TestNamespace get job discovery-it -o wide
kubectl --context $KubeContext -n $TestNamespace get pods -o wide
kubectl --context $KubeContext -n $TestNamespace logs job/discovery-it -c tests --tail=400 --timestamps=true

if (-not $JobSucceeded) {
    kubectl --context $KubeContext -n $TestNamespace get events --sort-by=.metadata.creationTimestamp
    throw 'Discovery integration test failed or exceeded its time budget'
}
~~~

Nếu Job chưa tạo được container, logs có thể chưa tồn tại; Events và Pod state sẽ chỉ ra lỗi image, mount hoặc scheduling. Không biến trường hợp thiếu log thành kết quả test đạt.

Maven verify phải báo số test chạy và không có failure/error; cấu hình `failIfNoTests` bảo vệ trường hợp sai pattern khiến không có integration test nào thực thi. Giữ log và báo cáo của lần chạy theo quy trình CI trước khi dọn Pod/namespace.

### 7.5. Chạy biến thể include-not-ready

Bộ test đọc `INCLUDE_NOT_READY` lúc tạo Spring context. Chạy lại toàn bộ với:

~~~yaml
- name: INCLUDE_NOT_READY
  value: "true"
~~~

Tạo **namespace mới** và Job mới từ đầu cho biến thể này. Không sửa biến môi trường trong một Spring context đã chạy rồi mong DiscoveryClient tự được tạo lại với cấu hình khác.

Kỳ vọng:

| Chế độ | catalog lúc baseline | billing |
| --- | --- | --- |
| `false` | Hai địa chỉ Ready | Một địa chỉ Ready |
| `true` | Hai địa chỉ Ready và địa chỉ chưa Ready | Một địa chỉ Ready |

Ở cả hai chế độ, assertion vẫn kiểm tra host thực tế và cổng chính xác. Trả ba instance bất kỳ không đủ để biến thể thứ hai đạt.

Giữ `publishNotReadyAddresses=false` của Service không đổi để không trộn hai cơ chế điều khiển. Một biến thể khác có thể kiểm tra publish-not-ready của Kubernetes, nhưng cần kỳ vọng riêng.

### 7.6. Thu thập bằng chứng và dọn đúng namespace

Nếu test thất bại, ưu tiên giữ:

- Log JUnit/Maven và tên test/assertion lỗi.
- Bộ phiên bản dependency, image test và cấu hình include-not-ready.
- Danh sách Pod gồm IP, readiness, deletion timestamp nếu đang scale.
- Service cùng Endpoints của namespace kiểm thử.
- Events liên quan nếu lỗi đến từ hạ tầng.

Namespace chỉ chứa fixture giả, nhưng vẫn không xuất token, kubeconfig hoặc Secret của runner. Sau khi đã thu thập bằng chứng:

~~~powershell
if ($TestNamespace -notmatch '^sck-discovery-[0-9a-f]{8}$') {
    throw 'Unexpected test namespace'
}

kubectl --context $KubeContext delete namespace $TestNamespace
~~~

Trong CI, đặt bước thu thập và cleanup vào khối được chạy cả khi test lỗi. Giữ nguyên trạng thái thất bại của build; cleanup thành công không được ghi đè kết quả test.

## 8. Mở rộng hợp đồng mà không làm lẫn các chế độ

### 8.1. Nhiều namespace có Service trùng tên

Tạo hai namespace riêng, mỗi namespace có Service catalog nhưng backend và label nhận dạng khác nhau.

| Cấu hình discovery | Kỳ vọng cần kiểm tra |
| --- | --- |
| Chỉ namespace A | Không có địa chỉ hay metadata của B |
| Chỉ namespace B | Không có địa chỉ hay metadata của A |
| Danh sách A và B | `getServices()` có thể chỉ có một tên catalog; `getInstances("catalog")` phải phản ánh đúng tập instance trong phạm vi được chọn |
| Namespace C không được chọn | Không đóng góp dữ liệu dù có Service cùng tên |

Không khẳng định namespace isolation bằng một fixture chỉ có tài nguyên ở một namespace. Không có dữ liệu đối chứng ở B thì test không thể phát hiện client vô tình đọc rộng hơn.

Không tự ghép `namespace/service` rồi giả định đó là service ID được implementation hỗ trợ. Kiểm tra namespace bằng metadata và cấu hình phạm vi. Với nhiều namespace, RoleBinding phải được thiết kế cho các namespace được phép; tránh cấp ClusterRole rộng chỉ để làm test xanh.

### 8.2. EndpointSlice phải có fixture và đường client riêng

Với chế độ EndpointSlice, một Service có thể tương ứng nhiều slice. Client cần tổng hợp đúng tập endpoint của tất cả slice liên quan qua label `kubernetes.io/service-name`, không coi tên slice là service ID. Xem [API EndpointSlice](https://kubernetes.io/docs/reference/kubernetes-api/discovery/endpoint-slice-v1/).

Bộ ca nên có:

| Ca | Dữ liệu | Assertion quan trọng |
| --- | --- | --- |
| Hai slice cùng Service | Mỗi slice giữ một phần backend | Không bỏ sót slice thứ hai |
| Slice của Service khác | Host/port dễ phân biệt | Không ghép nhầm vào Service đang hỏi |
| Thêm slice | Một địa chỉ mới trong slice mới | Tập instance tăng đúng một địa chỉ |
| Xóa slice | Một phần backend bị loại | Địa chỉ thuộc slice đó biến mất |
| Readiness | Endpoint có ready true/false | Theo đúng hợp đồng include-not-ready của client |
| Nhiều nhóm cổng | Cùng tên cổng nhưng backend có số cổng khác nhau | So sánh cặp host/port đúng từng nhóm |
| IPv6 hoặc dual-stack | Địa chỉ theo từng addressType | Không làm sai host/URI, không áp dụng oracle IPv4 một cách máy móc |

Nếu cần fixture cố định với nhiều slice mà không tạo hàng trăm Pod, dùng Service không có selector và các slice do test sở hữu. Gắn label managed-by riêng, không để controller của Service có selector ghi đè dữ liệu. Những địa chỉ mô phỏng trong fixture dạng này chỉ phục vụ kiểm thử ánh xạ, không tự đại diện cho backend gọi được.

Ngược lại, test controller thực nên dùng Service có selector và các Pod thật như ví dụ chính. Hai loại fixture kiểm tra hai lớp hành vi khác nhau.

Chỉ đổi `spring.cloud.kubernetes.discovery.use-endpoint-slices` chưa đủ để chứng minh test đã đi qua API này: cần implementation/phiên bản hỗ trợ, quyền trên `discovery.k8s.io/endpointslices` và bằng chứng client thực sự truy vấn đúng đường API. Tài liệu [EndpointSlices của Kubernetes](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/) giải thích quan hệ Service, slice và backend.

### 8.3. Cổng chính, HTTPS và metadata

Ví dụ chính kiểm tra label `primary-port-name=api`. Bổ sung các ca độc lập nếu sản phẩm dùng quy tắc khác:

- Cổng chính từ property khi Service không có label tương ứng.
- Label và property cùng tồn tại để kiểm tra độ ưu tiên.
- Cổng tên http/https khi không cấu hình cổng chính.
- Metadata label/annotation được bật hoặc tắt.
- Endpoint có nhiều nhóm target port.
- Service ExternalName, headless hoặc kiểu đặc biệt thực sự được dùng.

Đừng biến “client trả cổng nào đó” thành hợp đồng chấp nhận được. Ghi rõ số cổng và scheme mong muốn cho từng ca.

`isSecure=true` hoặc URI scheme https chỉ phản ánh dữ liệu discovery/quy tắc cấu hình. Nó không chứng minh TLS handshake, chứng chỉ, hostname verification hoặc nội dung phản hồi hợp lệ. Cần test kết nối riêng nếu yêu cầu bao gồm các hành vi này.

### 8.4. Cache và biến động tài nguyên

Ví dụ tắt lớp cache discovery bổ sung để giữ phạm vi dễ hiểu. Nếu sản phẩm bật cache ở DiscoveryClient hoặc Spring Cloud LoadBalancer, chạy bộ ca biến động với cấu hình cache đó:

1. Đợi baseline được nhìn thấy qua đường đọc cần kiểm tra.
2. Thay đổi một tài nguyên.
3. Poll đến khi tập kết quả mới đúng.
4. Ghi nhận thời gian hội tụ trong ngân sách đã chọn.
5. Kiểm tra địa chỉ cũ đã biến mất, không chỉ địa chỉ mới đã xuất hiện.

Một lần assertion đạt không chứng minh một SLO hội tụ trong mọi điều kiện. Đo hiệu năng hoặc độ trễ dưới tải cần thiết kế thử nghiệm riêng, có số mẫu và điều kiện đo.

## 9. Những cách viết test dễ cho kết quả xanh sai

| Cách viết | Vì sao chưa đủ? | Cách cải thiện |
| --- | --- | --- |
| Chỉ assert danh sách không rỗng | Client có thể trả nhầm Service | So sánh đúng host/port và service ID |
| Chỉ assert số instance | Hai địa chỉ sai vẫn có đúng số lượng | Kiểm tra tập địa chỉ chính xác |
| Assert phần tử đầu tiên | Thứ tự không phải hợp đồng ổn định | So sánh không phụ thuộc thứ tự |
| Chuyển sang Set ngay | Làm mất bằng chứng trùng lặp | Giữ List và kiểm tra số lần xuất hiện |
| Dùng cùng thuật toán để dựng expected | Test lặp lại lỗi của implementation | Dùng fixture và oracle độc lập |
| Mock DiscoveryClient để trả fixture | Chỉ xác nhận stub hoặc code người gọi | Dùng client thật cho test adapter |
| Sleep cố định | Máy nhanh lãng phí, máy chậm vẫn lỗi | Poll có timeout theo điều kiện |
| Catch mọi exception rồi retry | Lỗi quyền hoặc cấu hình bị che | Chỉ chờ trạng thái hội tụ phù hợp |
| Gọi Service URL rồi kết luận discovery đúng | Lời gọi có thể chỉ qua DNS/ClusterIP | Gọi và assert DiscoveryClient trực tiếp |
| Chỉ chạy một namespace | Không có đối chứng về isolation | Thêm namespace có dữ liệu cùng tên |
| Tạo Job xong là PASS | Test có thể chưa chạy hoặc đã lỗi | Kiểm tra trạng thái cuối và Maven result |

Khi dùng mock API server để tăng tốc vòng lặp, mock cần phục vụ đúng list/get và watch nếu implementation sử dụng watch. Test phải kiểm tra request đi tới đúng namespace, label/field selector và API resource. Mock CRUD không tự chạy các controller của Kubernetes, nên tạo Service trên mock không tự sinh backend giống cụm thật.

Dùng mock server có thể kiểm tra nhiều hình dạng dữ liệu biên nhanh hơn, nhưng giữ một số test trong cụm để phát hiện sai khác về API, RBAC và controller.

## 10. Chẩn đoán khi integration test thất bại

| Dấu hiệu | Bằng chứng ưu tiên | Hướng kiểm tra |
| --- | --- | --- |
| Không tìm thấy provider Fabric8 | Báo cáo Spring context và dependency | Starter, profile, auto-configuration và chế độ client |
| Kubernetes API trả 403 | Verb, resource và namespace trong lỗi | ServiceAccount, RoleBinding, quyền read hoặc scale |
| catalog có ba instance khi include=false | Endpoints addresses/notReadyAddresses cùng Pod Ready | Cờ include-not-ready, publish-not-ready và implementation |
| catalog trả cổng 9090 | Service label và ports của Endpoints | Quy tắc chọn primary port |
| getServices có excluded | Cấu hình map service-labels và label Service | Property binding, fixture hoặc client filter |
| Sau scale vẫn giữ host cũ | Pod deletion timestamp, Endpoints và kết quả discovery | Controller chưa hội tụ, cache hoặc mutation chưa hoàn tất |
| Maven không chạy test | Profile, include pattern và số test | Failsafe/verify, không chấp nhận zero-test |
| Job chưa chạy container | Describe Pod và Events | Image chưa load/pull, tài nguyên node hoặc policy |
| Test ở laptop thất bại nhưng Job đạt | Danh tính và vị trí chạy | Kubeconfig, namespace và cơ chế kích hoạt in-cluster |

Có thể lấy dữ liệu chẩn đoán trong namespace của lần chạy:

~~~powershell
kubectl --context $KubeContext -n $TestNamespace get pods -o wide
kubectl --context $KubeContext -n $TestNamespace get services -o yaml
kubectl --context $KubeContext -n $TestNamespace get endpoints catalog billing empty excluded -o yaml
kubectl --context $KubeContext -n $TestNamespace get events --sort-by=.metadata.creationTimestamp
~~~

Chỉ tăng timeout sau khi đã biết hệ thống đang tiến triển hợp lệ nhưng chậm hơn ngân sách. Timeout dài hơn không sửa được namespace sai, label sai, quyền thiếu hoặc một provider chưa được tạo.

## 11. Tiêu chí hoàn thành bài học

- [ ] Bộ phiên bản, implementation và API endpoint được ghi rõ.
- [ ] Test sử dụng DiscoveryClient thật cho mục tiêu ánh xạ Kubernetes.
- [ ] Có ít nhất hai Service với host và cổng backend phân biệt được.
- [ ] So sánh tập instance chính xác, không phụ thuộc thứ tự và không che duplicate.
- [ ] Có Service rỗng, Service không tồn tại và Service bị loại bởi label.
- [ ] Có ca endpoint chưa Ready với hai chế độ cấu hình.
- [ ] Có ca thêm và bớt replica, chờ hội tụ bằng assertion có giới hạn.
- [ ] Test kiểm tra namespace metadata đúng hợp đồng phiên bản.
- [ ] Identity test và quyền phục vụ điều khiển fixture được phân biệt với quyền của sản phẩm.
- [ ] CI phát hiện failure, timeout và trường hợp không có test nào chạy.
- [ ] Namespace của từng lần chạy được cô lập và được dọn sau khi giữ bằng chứng.
- [ ] Kết luận không mở rộng từ test Endpoints sang EndpointSlice, HTTP, TLS hoặc cân bằng tải khi chưa có phép thử tương ứng.

Bằng chứng hoàn thành phù hợp là báo cáo test đã chạy trên fixture cụ thể, nêu rõ chế độ include-not-ready, kết quả ánh xạ của từng Service và khả năng hội tụ sau thay đổi replica. Từ đó, bạn có cơ sở bổ sung test kết nối hoặc Spring Cloud LoadBalancer nếu ứng dụng thật cần những tính năng này.
