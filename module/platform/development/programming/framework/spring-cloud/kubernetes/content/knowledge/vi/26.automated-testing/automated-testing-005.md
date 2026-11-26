# Kiểm thử lựa chọn cổng, namespace và bộ lọc

Trong chương **Kiểm thử tự động** của module **SPRING_CLOUD_KUBERNETES**, kiểm thử discovery cần trả lời ba câu hỏi: ứng dụng nhìn vào namespace nào, service nào được đưa vào kết quả và cổng nào được gắn vào mỗi instance.

Một danh sách không rỗng chưa đủ để kết luận đúng. Ứng dụng có thể tìm thấy đúng tên service nhưng nhầm namespace, hoặc chọn cổng metrics thay vì HTTP. Bài này xây dựng kiểm thử có dữ liệu đối chứng, dùng DiscoveryClient thật để phát hiện các sai lệch đó.

## 1. Phạm vi và điều kiện thực hành

Ví dụ Java sử dụng **Fabric8 blocking `KubernetesDiscoveryClient` của Spring Cloud Kubernetes nhánh 3.3**, với cách gọi API công khai được đối chiếu ở tag `v3.3.0`. Dùng JDK 17 trở lên và bộ dependency Spring Boot/Spring Cloud tương thích do BOM của dự án quản lý. Khi dùng nhánh khác, đối chiếu lại class, cấu hình và hành vi trước khi chuyển nguyên ví dụ.

Bài thực hành dùng:

- JUnit Jupiter, AssertJ và `ApplicationContextRunner` từ Spring Boot Test.
- Starter `spring-cloud-starter-kubernetes-fabric8`.
- Một cluster thử nghiệm, chẳng hạn kind hoặc minikube, truy cập được từ JVM chạy test.
- Kubeconfig có context được chỉ định tường minh.
- Tài khoản thử nghiệm có quyền tạo/xóa namespace và quản lý Service/Endpoints của fixture.

Mẫu tạo **Service không có selector** cùng **Endpoints được quản lý thủ công**. Không cần image hay Pod backend vì phép thử chỉ đọc mô hình discovery, không gửi lưu lượng tới địa chỉ instance.

`Endpoints` ở đây là lựa chọn tương thích với implementation đang kiểm thử. Với hệ thống dùng EndpointSlice, cần tạo fixture EndpointSlice và chạy client tương ứng; không đổi tên API object rồi giữ nguyên test. Xem [Kubernetes Service không có selector](https://kubernetes.io/docs/concepts/services-networking/service/#services-without-selectors) và [EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/).

Không bật ConfigMap/Secret PropertySource, Configuration Watcher hoặc LoadBalancer trong context tối thiểu này. Các thành phần đó có kiểm thử tích hợp riêng; phạm vi hiện tại là lựa chọn instance của discovery.

## 2. Chọn đúng đối tượng để assert

Cần quan sát cả hai phương thức:

| Phương thức | Cần kiểm tra | Chưa chứng minh được |
| --- | --- | --- |
| `getServices()` | Tập service ID được tìm thấy | Mỗi instance thuộc namespace nào |
| `getInstances(serviceId)` | Service ID, namespace, host, port và thuộc tính liên quan | Backend có thực sự nhận request thành công hay không |

Trong ví dụ, một kết quả được biểu diễn bằng bộ:

~~~text
(serviceId, namespace, host, port)
~~~

Hai instance `orders` trong hai namespace khác nhau phải là hai phần tử phân biệt, dù `getServices()` chỉ trả tên `orders` một lần. Dùng metadata `k8s_namespace` để giữ dấu hiệu namespace khi làm việc qua giao diện `ServiceInstance`.

Tránh chỉ assert `hasSize(2)`: hai phần tử đó có thể đều thuộc một namespace sai. Assert tập giá trị đầy đủ giúp phát hiện cả kết quả thiếu lẫn kết quả thừa.

## 3. Tách ba lớp lựa chọn

~~~mermaid
flowchart LR
    N["Phạm vi namespace"] --> L["Điều kiện nhãn service"]
    L --> F["Biểu thức lọc service"]
    F --> E["Endpoint được đưa vào kết quả"]
    E --> P["Chọn tên cổng và số cổng"]
    P --> I["ServiceInstance: namespace, host, port"]
~~~

Sơ đồ là mô hình suy luận để thiết kế ca kiểm thử; nó không cam kết thứ tự từng HTTP request nội bộ.

### Namespace

Dùng ba cấu hình riêng:

- Không đặt danh sách namespace: kiểm tra namespace mà client/provider phân giải.
- Đặt `spring.cloud.kubernetes.discovery.namespaces`: kiểm tra đúng tập namespace được chọn.
- Đặt `spring.cloud.kubernetes.discovery.all-namespaces=true`: kiểm tra phạm vi toàn cluster trong môi trường thử nghiệm.

Đừng bật đồng thời danh sách namespace và `all-namespaces` trong fixture chuẩn. Nếu dự án cho phép tổ hợp này, cần một ca đặc tả riêng theo phiên bản thay vì suy luận thứ tự ưu tiên.

### Nhãn và biểu thức

`spring.cloud.kubernetes.discovery.service-labels` là map điều kiện nhãn. Biểu thức `spring.cloud.kubernetes.discovery.filter` được đánh giá trên object Service của client đang dùng; ví dụ Fabric8 sử dụng `io.fabric8.kubernetes.api.model.Service`.

Một biểu thức dễ kiểm chứng:

~~~text
#root.metadata.name matches '^orders(-.*)?$'
~~~

Dùng toán tử `matches` hoặc truy cập map để tránh phụ thuộc vào khả năng gọi phương thức của evaluation context. Xem [DiscoveryClient nhánh 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/discovery-client.html).

Trong fixture Endpoints thủ công của bài, các nhãn discovery cần được gắn nhất quán lên Service và Endpoints. Đường đọc Endpoints của implementation này cũng áp điều kiện nhãn lên Endpoints. Thiếu nhãn ở một phía có thể tạo ra tình huống `getServices()` nhìn thấy tên nhưng `getInstances()` rỗng. Cách đọc này thể hiện trong [Fabric8KubernetesDiscoveryClientUtils tại v3.3.0](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.0/spring-cloud-kubernetes-fabric8-discovery/src/main/java/org/springframework/cloud/kubernetes/fabric8/discovery/Fabric8KubernetesDiscoveryClientUtils.java).

### Cổng

Cố tình dùng số khác nhau để tránh một assertion sai vẫn pass:

| Tên cổng | Service.port | targetPort | Endpoints port | Kết quả mong đợi khi chọn backend |
| --- | --- | --- | --- | --- |
| `http` | 80 | 8080 | 8080 | 8080 |
| `metrics` | 9090 | 19090 | 19090 | 19090 |
| `https`, nếu được thêm | 443 | 8443 | 8443 | 8443 |

Với client trực tiếp đọc Endpoints trong ví dụ, `ServiceInstance.port` lấy từ dữ liệu endpoint theo tên cổng. Không assert 80 chỉ vì manifest Service có `port: 80`. Xem [KubernetesDiscoveryClient tại v3.3.0](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.0/spring-cloud-kubernetes-fabric8-discovery/src/main/java/org/springframework/cloud/kubernetes/fabric8/discovery/KubernetesDiscoveryClient.java).

Với nhiều cổng, cần kiểm tra label `primary-port-name` của Service, property `discovery.primary-port-name` và các nhánh dự phòng. Đừng suy luận từ thứ tự manifest. Mã chọn cổng được mô tả trong [DiscoveryClientUtils tại v3.3.0](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.0/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/discovery/DiscoveryClientUtils.java).

## 4. Ma trận kiểm thử trước khi viết mã

Fixture dùng ba namespace A, B, C, đều có hậu tố riêng cho mỗi lần chạy:

| Namespace | Service | Nhãn `tier` | IP giả |
| --- | --- | --- | --- |
| A | `orders` | `backend` | `192.0.2.11` |
| B | `orders` | `backend` | `192.0.2.21` |
| C | `orders` | `backend` | `192.0.2.31` |
| A | `orders-admin` | `internal` | `192.0.2.12` |
| A | `inventory` | `backend` | `192.0.2.13` |
| A | `orders-shadow` | `frontend` | `192.0.2.14` |
| A | `orders-no-tier` | Không có | `192.0.2.15` |

Mỗi resource còn có nhãn `fixture-run=<runId>`. Điều kiện này giúp phép thử `all-namespaces` tránh lấy dữ liệu của lượt chạy khác. IP chỉ là dữ liệu giả trong API, không được dùng để gọi mạng.

Các ca tối thiểu:

| Ca | Thay đổi cấu hình/fixture | Kỳ vọng chính |
| --- | --- | --- |
| N1 | Namespace mặc định A | `orders` chỉ có IP của A |
| N2 | Danh sách A, B | Có IP của A và B; không có C |
| N3 | All namespaces | Có IP của cả A, B, C |
| L1 | Nhãn `tier=backend` | Giữ `orders`, `inventory` ở A |
| F1 | Chỉ biểu thức tên `orders...` | Giữ các tên orders; loại inventory |
| F2 | Nhãn backend và biểu thức tên | Chỉ giữ orders ở A |
| P1 | Property chọn `metrics` | Cổng 19090 |
| P2 | Label chọn metrics, property chọn http | Label thắng: 19090 |
| P3 | Một cổng duy nhất | Dùng cổng duy nhất |
| P4 | Có http và https, không chỉ định primary | Chọn https: 8443 |
| P5 | Đổi thứ tự khai báo, primary vẫn là http | Vẫn chọn 8080 |
| P6 | Label trỏ tên không tồn tại | Ghi nhận nhánh dự phòng của phiên bản |

Điểm quan trọng là có **C ngoài allowlist**, có service **đúng nhãn nhưng sai tên**, **đúng tên nhưng sai nhãn** và **thiếu nhãn**. Nếu chỉ tạo dữ liệu thỏa tất cả điều kiện, test chưa kiểm tra được việc loại trừ.

## 5. Tạo context tối thiểu cho client thật

Trong `pom.xml` của dự án thực hành, cần các dependency sau; để BOM quản lý version:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-fabric8</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Context của bài dùng binder thật cho `KubernetesDiscoveryProperties` và tạo `KubernetesDiscoveryClient` thật bằng factory công khai. Vì vậy, thay đổi property phải tác động tới kết quả thực tế; không mock `getInstances()` để tự trả chính danh sách đang được assert.

Đây là kiểm thử binding và lựa chọn discovery có truy cập API thật. Nó chưa kiểm tra toàn bộ auto-configuration của ứng dụng production. Để kiểm tra việc starter tự đăng ký bean trong production, bổ sung một smoke test với cấu hình ứng dụng thực.

`ApplicationContextRunner` tạo và đóng context cho từng lần `run`; xem [API ApplicationContextRunner](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html).

## 6. Ví dụ integration test hoàn chỉnh

Đặt lớp sau trong `src/test/java/com/example/discovery/DiscoverySelectionIT.java` của dự án thực hành. Lớp tạo namespace riêng cho từng test, quản lý fixture trực tiếp qua Kubernetes API và đóng client khi kết thúc.

Mã không yêu cầu ứng dụng chính khởi động. `DiscoveryConfiguration` đăng ký client thật và để Spring gọi lifecycle `EnvironmentAware` của nó; không viết lại thuật toán chọn cổng hoặc lọc.

~~~java
package com.example.discovery;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Consumer;

import io.fabric8.kubernetes.api.model.EndpointAddressBuilder;
import io.fabric8.kubernetes.api.model.EndpointPortBuilder;
import io.fabric8.kubernetes.api.model.EndpointSubsetBuilder;
import io.fabric8.kubernetes.api.model.EndpointsBuilder;
import io.fabric8.kubernetes.api.model.IntOrString;
import io.fabric8.kubernetes.api.model.NamespaceBuilder;
import io.fabric8.kubernetes.api.model.ServiceBuilder;
import io.fabric8.kubernetes.api.model.ServicePortBuilder;
import io.fabric8.kubernetes.client.Config;
import io.fabric8.kubernetes.client.KubernetesClient;
import io.fabric8.kubernetes.client.KubernetesClientBuilder;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.kubernetes.commons.discovery.KubernetesDiscoveryProperties;
import org.springframework.cloud.kubernetes.fabric8.discovery.KubernetesClientServicesFunctionProvider;
import org.springframework.cloud.kubernetes.fabric8.discovery.KubernetesDiscoveryClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

import static org.assertj.core.api.Assertions.assertThat;

class DiscoverySelectionIT {

    private static final String D = "spring.cloud.kubernetes.discovery.";
    private static final Port HTTP = new Port("http", 80, 8080);
    private static final Port METRICS = new Port("metrics", 9090, 19090);

    private final List<String> ownedNamespaces = new ArrayList<>();

    private KubernetesClient admin;
    private String contextName;
    private String runId;
    private String a;
    private String b;
    private String c;

    record Port(String name, int servicePort, int backendPort) {
    }

    record Seen(String serviceId, String namespace, String host, int port) {
    }

    @BeforeEach
    void createFixture() {
        contextName = System.getenv("TEST_KUBE_CONTEXT");
        if (contextName == null || contextName.isBlank()) {
            throw new IllegalStateException("Phải đặt TEST_KUBE_CONTEXT");
        }

        runId = UUID.randomUUID().toString().substring(0, 8);
        admin = newClient(contextName);

        a = createNamespace("sck-it-a-" + runId);
        b = createNamespace("sck-it-b-" + runId);
        c = createNamespace("sck-it-c-" + runId);

        put(a, "orders", "192.0.2.11",
                Map.of("tier", "backend"), HTTP, METRICS);
        put(b, "orders", "192.0.2.21",
                Map.of("tier", "backend"), HTTP, METRICS);
        put(c, "orders", "192.0.2.31",
                Map.of("tier", "backend"), HTTP, METRICS);

        put(a, "orders-admin", "192.0.2.12",
                Map.of("tier", "internal"), HTTP, METRICS);
        put(a, "inventory", "192.0.2.13",
                Map.of("tier", "backend"), HTTP, METRICS);
        put(a, "orders-shadow", "192.0.2.14",
                Map.of("tier", "frontend"), HTTP, METRICS);
        put(a, "orders-no-tier", "192.0.2.15",
                Map.of(), HTTP, METRICS);

        assertThat(admin.services().inNamespace(a)
                .withLabels(Map.of("fixture-run", runId))
                .list().getItems()).hasSize(5);
        assertThat(admin.endpoints().inNamespace(b)
                .withName("orders").get()).isNotNull();
        assertThat(admin.endpoints().inNamespace(c)
                .withName("orders").get()).isNotNull();
    }

    private String createNamespace(String name) {
        var namespace = new NamespaceBuilder()
                .withApiVersion("v1")
                .withKind("Namespace")
                .withNewMetadata()
                    .withName(name)
                    .addToLabels("fixture-run", runId)
                .endMetadata()
                .build();

        admin.namespaces().resource(namespace).create();
        ownedNamespaces.add(name);
        return name;
    }

    private void put(String namespace, String name, String ip,
            Map<String, String> extraLabels, Port... ports) {
        Map<String, String> labels = new HashMap<>(extraLabels);
        labels.put("fixture-run", runId);

        var servicePorts = java.util.Arrays.stream(ports)
                .map(port -> new ServicePortBuilder()
                        .withName(port.name())
                        .withProtocol("TCP")
                        .withPort(port.servicePort())
                        .withTargetPort(new IntOrString(port.backendPort()))
                        .build())
                .toList();

        var endpointPorts = java.util.Arrays.stream(ports)
                .map(port -> new EndpointPortBuilder()
                        .withName(port.name())
                        .withProtocol("TCP")
                        .withPort(port.backendPort())
                        .build())
                .toList();

        var service = new ServiceBuilder()
                .withApiVersion("v1")
                .withKind("Service")
                .withNewMetadata()
                    .withName(name)
                    .withNamespace(namespace)
                    .withLabels(labels)
                .endMetadata()
                .withNewSpec()
                    .withType("ClusterIP")
                    .withPorts(servicePorts)
                .endSpec()
                .build();

        admin.services().inNamespace(namespace).resource(service).create();

        var endpoints = new EndpointsBuilder()
                .withApiVersion("v1")
                .withKind("Endpoints")
                .withNewMetadata()
                    .withName(name)
                    .withNamespace(namespace)
                    .withLabels(labels)
                .endMetadata()
                .withSubsets(new EndpointSubsetBuilder()
                        .withAddresses(new EndpointAddressBuilder()
                                .withIp(ip).build())
                        .withPorts(endpointPorts)
                        .build())
                .build();

        admin.endpoints().inNamespace(namespace).resource(endpoints).create();
    }

    private void verify(Consumer<KubernetesDiscoveryClient> assertions,
            String... overrides) {
        new ApplicationContextRunner()
                .withUserConfiguration(DiscoveryConfiguration.class)
                .withPropertyValues(
                        "test.kube-context=" + contextName,
                        "spring.cloud.kubernetes.client.namespace=" + a,
                        D + "all-namespaces=false",
                        D + "include-not-ready-addresses=false",
                        D + "service-labels[fixture-run]=" + runId)
                .withPropertyValues(overrides)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(KubernetesDiscoveryClient.class);
                    assertions.accept(
                            context.getBean(KubernetesDiscoveryClient.class));
                });
    }

    private static List<Seen> seen(List<ServiceInstance> instances) {
        return instances.stream()
                .map(instance -> new Seen(
                        instance.getServiceId(),
                        instance.getMetadata().get("k8s_namespace"),
                        instance.getHost(),
                        instance.getPort()))
                .toList();
    }

    private static ServiceInstance expectOne(KubernetesDiscoveryClient client,
            String serviceId, String namespace, String ip, int port) {
        List<ServiceInstance> instances = client.getInstances(serviceId);
        assertThat(seen(instances)).containsExactly(
                new Seen(serviceId, namespace, ip, port));
        return instances.get(0);
    }

    private static KubernetesClient newClient(String contextName) {
        Config config = Config.autoConfigure(contextName);
        if (config.getCurrentContext() == null
                || !contextName.equals(config.getCurrentContext().getName())) {
            throw new IllegalStateException(
                    "Không phân giải được context thử nghiệm đã chỉ định");
        }
        return new KubernetesClientBuilder().withConfig(config).build();
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(KubernetesDiscoveryProperties.class)
    static class DiscoveryConfiguration {

        @Bean(destroyMethod = "close")
        KubernetesClient kubernetesClient(Environment environment) {
            return newClient(
                    environment.getRequiredProperty("test.kube-context"));
        }

        @Bean
        KubernetesDiscoveryClient discoveryClient(KubernetesClient client,
                KubernetesDiscoveryProperties properties,
                Environment environment) {
            var function =
                    KubernetesClientServicesFunctionProvider.servicesFunction(
                            properties, environment);
            return new KubernetesDiscoveryClient(client, properties, function);
        }
    }

    @AfterEach
    void cleanFixture() {
        if (admin == null) {
            return;
        }

        RuntimeException cleanupFailure = null;
        try {
            for (String namespace : ownedNamespaces) {
                try {
                    var current = admin.namespaces().withName(namespace).get();
                    if (current == null) {
                        continue;
                    }
                    var labels = current.getMetadata().getLabels();
                    if (labels == null
                            || !runId.equals(labels.get("fixture-run"))) {
                        throw new IllegalStateException(
                                "Namespace không còn thuộc fixture: " + namespace);
                    }
                    admin.namespaces().withName(namespace).delete();
                }
                catch (RuntimeException exception) {
                    if (cleanupFailure == null) {
                        cleanupFailure = exception;
                    }
                    else {
                        cleanupFailure.addSuppressed(exception);
                    }
                }
            }
        }
        finally {
            admin.close();
        }

        if (cleanupFailure != null) {
            throw cleanupFailure;
        }
    }

    @Test
    void defaultNamespaceContainsOnlyA() {
        verify(client -> expectOne(
                client, "orders", a, "192.0.2.11", 8080));
    }

    @Test
    void selectedNamespacesKeepDistinctInstancesAndUniqueServiceId() {
        verify(client -> {
            assertThat(seen(client.getInstances("orders")))
                    .containsExactlyInAnyOrder(
                            new Seen("orders", a, "192.0.2.11", 8080),
                            new Seen("orders", b, "192.0.2.21", 8080));

            long occurrences = client.getServices().stream()
                    .filter("orders"::equals)
                    .count();
            assertThat(occurrences).isEqualTo(1L);
        },
                D + "namespaces[0]=" + a,
                D + "namespaces[1]=" + b);
    }

    @Test
    void allNamespacesIncludeTheSentinelInC() {
        verify(client -> {
            assertThat(seen(client.getInstances("orders")))
                    .containsExactlyInAnyOrder(
                            new Seen("orders", a, "192.0.2.11", 8080),
                            new Seen("orders", b, "192.0.2.21", 8080),
                            new Seen("orders", c, "192.0.2.31", 8080));
        }, D + "all-namespaces=true");
    }

    @Test
    void serviceLabelsFilterNamesAndInstances() {
        verify(client -> {
            expectOne(client, "orders-shadow", a, "192.0.2.14", 8080);
            expectOne(client, "orders-no-tier", a, "192.0.2.15", 8080);
        });

        verify(client -> {
            assertThat(client.getServices())
                    .containsExactlyInAnyOrder("orders", "inventory");

            expectOne(client, "orders", a, "192.0.2.11", 8080);
            expectOne(client, "inventory", a, "192.0.2.13", 8080);
            assertThat(client.getInstances("orders-admin")).isEmpty();
            assertThat(client.getInstances("orders-shadow")).isEmpty();
            assertThat(client.getInstances("orders-no-tier")).isEmpty();
        }, D + "service-labels[tier]=backend");
    }

    @Test
    void spelFiltersNamesAndDirectInstanceLookups() {
        verify(client -> {
            assertThat(client.getServices()).containsExactlyInAnyOrder(
                    "orders", "orders-admin",
                    "orders-shadow", "orders-no-tier");
            expectOne(client, "orders", a, "192.0.2.11", 8080);
            assertThat(client.getInstances("inventory")).isEmpty();
        }, D + "filter=#root.metadata.name matches '^orders(-.*)?$'");
    }

    @Test
    void labelsAndSpelAreBothRequired() {
        verify(client -> {
            assertThat(client.getServices()).containsExactly("orders");
            expectOne(client, "orders", a, "192.0.2.11", 8080);
            assertThat(client.getInstances("inventory")).isEmpty();
            assertThat(client.getInstances("orders-admin")).isEmpty();
            assertThat(client.getInstances("orders-shadow")).isEmpty();
            assertThat(client.getInstances("orders-no-tier")).isEmpty();
        },
                D + "service-labels[tier]=backend",
                D + "filter=#root.metadata.name matches '^orders(-.*)?$'");
    }

    @Test
    void configuredPortUsesTheBackendNumber() {
        verify(client -> expectOne(
                client, "orders", a, "192.0.2.11", 19090),
                D + "primary-port-name=metrics");
    }

    @Test
    void serviceLabelOverridesThePortProperty() {
        put(a, "orders-override", "192.0.2.41",
                Map.of("tier", "backend", "primary-port-name", "metrics"),
                HTTP, METRICS);

        verify(client -> expectOne(
                client, "orders-override", a, "192.0.2.41", 19090),
                D + "primary-port-name=http");
    }

    @Test
    void singlePortAndHttpsFallbackHaveExplicitExpectations() {
        put(a, "single-port", "192.0.2.42", Map.of(),
                new Port("grpc", 707, 7070));
        put(a, "orders-tls", "192.0.2.43", Map.of(),
                HTTP, new Port("https", 443, 8443));

        verify(client -> {
            expectOne(client, "single-port", a, "192.0.2.42", 7070);

            ServiceInstance tls = expectOne(
                    client, "orders-tls", a, "192.0.2.43", 8443);
            assertThat(tls.isSecure()).isTrue();
            assertThat(tls.getUri().getScheme()).isEqualTo("https");
        }, D + "primary-port-name=not-present");
    }

    @Test
    void namedPortSelectionSurvivesDeclarationOrderChanges() {
        put(a, "orders-first", "192.0.2.44", Map.of(),
                HTTP, METRICS);
        put(a, "orders-second", "192.0.2.45", Map.of(),
                METRICS, HTTP);

        verify(client -> {
            expectOne(client, "orders-first", a, "192.0.2.44", 8080);
            expectOne(client, "orders-second", a, "192.0.2.45", 8080);
        }, D + "primary-port-name=http");
    }

    @Test
    void unmatchedLabelFallsBackInsteadOfTryingThePropertyAgain() {
        put(a, "orders-bad-label", "192.0.2.46",
                Map.of("primary-port-name", "not-present"), HTTP, METRICS);

        verify(client -> expectOne(
                client, "orders-bad-label", a, "192.0.2.46", 8080),
                D + "primary-port-name=metrics");
    }
}
~~~

### Cách đọc các assertion

Ca namespace A/B assert chính xác hai bộ giá trị. Nếu implementation vô tình mở rộng sang toàn cluster, instance trong C làm test fail. Nếu implementation bỏ qua B, tập kết quả cũng không khớp.

Ca nhãn có một lượt không lọc để chứng minh service bị loại thực sự có endpoint trước đó. Nhờ vậy, kết quả rỗng sau khi lọc không chỉ là hậu quả của fixture thiếu dữ liệu.

Ca kết hợp nhãn và SpEL dùng bốn đối chứng:

- `inventory` đúng nhãn nhưng sai tên.
- `orders-shadow` đúng tên nhưng sai nhãn.
- `orders-admin` đúng tên nhưng thuộc tier khác.
- `orders-no-tier` đúng tên nhưng thiếu nhãn cần thiết.

Cả `getServices()` và `getInstances()` đều được kiểm tra. Nếu chỉ lọc danh sách tên nhưng vẫn trả endpoint khi gọi trực tiếp service ID bị loại, test sẽ phát hiện.

Ca `unmatchedLabelFallsBackInsteadOfTryingThePropertyAgain` là kiểm thử đặc tả cho nhánh 3.3 đã nêu: label chọn một tên không có trong endpoint không khiến client thử lại property `metrics`; nhánh dự phòng có `http` nên trả 8080. Nếu nâng phiên bản làm hành vi thay đổi, hãy xem xét lại hợp đồng thay vì sửa assertion chỉ để build xanh.

## 7. Chạy bằng Maven Failsafe

Để tên lớp `*IT` được thực thi trong pha integration test, thêm cấu hình plugin vào phần `build/plugins` của dự án thực hành. Dùng version plugin được quản lý bởi parent/BOM/plugin management của dự án:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <failIfNoTests>true</failIfNoTests>
    </configuration>
</plugin>
~~~

Failsafe mặc định nhận các mẫu tên như `*IT`. Chỉ chạy `mvn test` thường chưa thực thi lớp này. Xem [quy tắc chọn test của Maven Failsafe](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/inclusion-exclusion.html).

Ví dụ PowerShell:

~~~powershell
$env:TEST_KUBE_CONTEXT = "kind-sck-dev"

kubectl --context $env:TEST_KUBE_CONTEXT cluster-info
if ($LASTEXITCODE -ne 0) { throw "Không truy cập được cluster thử nghiệm." }

.\mvnw.cmd verify "-Dit.test=DiscoverySelectionIT"
if ($LASTEXITCODE -ne 0) { throw "Integration test không thành công." }
~~~

Khi dùng minikube hoặc cluster khác, thay context bằng giá trị đã có trong kubeconfig. JVM và `kubectl` phải sử dụng cùng nguồn kubeconfig. Ví dụ dùng `Config.autoConfigure(contextName)` và kiểm tra context đã phân giải; cấu hình Fabric8 vẫn cần được quản lý nhất quán trong môi trường chạy. Tham khảo [Fabric8 Config](https://github.com/fabric8io/kubernetes-client/blob/v7.3.1/kubernetes-client-api/src/main/java/io/fabric8/kubernetes/client/Config.java).

Nếu không đặt `TEST_KUBE_CONTEXT` hoặc không truy cập được API, bộ integration test phải fail rõ ràng. Trong CI, tạo một job có cluster và quyền cần thiết để chạy lớp này; không coi một lượt chạy không có test hoặc bị skip là bằng chứng lựa chọn discovery đúng.

Kết quả cần lưu cùng báo cáo gồm:

- Phiên bản Spring Boot, Spring Cloud Kubernetes và Fabric8 thực tế.
- Chế độ client, loại API endpoint và context thử nghiệm.
- Số test đã chạy, kết quả và lỗi nếu có.
- Fixture/namespace liên quan khi thất bại, không lưu credential kubeconfig.

## 8. Kiểm tra thêm các biên quan trọng

Ví dụ trên có thể được mở rộng theo các chiều sau:

| Biên | Fixture và assertion nên bổ sung |
| --- | --- |
| Nhiều điều kiện nhãn | Service thỏa cả hai, chỉ một hoặc không điều kiện nào; xác nhận ngữ nghĩa kết hợp |
| Namespace rỗng | Namespace tồn tại nhưng không có service phù hợp; assert kết quả rỗng có chủ đích |
| Cấu hình namespace sai | Phân biệt namespace không tồn tại, không có dữ liệu và không đủ quyền |
| Không có endpoint sẵn sàng | Tạo ready/not-ready address riêng, kiểm tra `include-not-ready-addresses` |
| Nhiều subset | Mỗi subset có địa chỉ và cổng đã biết; kiểm tra toàn bộ tuple |
| Không có tên cổng mong muốn | Có và không có `http`/`https`; tách hành vi dự phòng khỏi chính sách của ứng dụng |
| Nhãn primary đặt nhầm lên Pod | Service không có label đó; test phải cho thấy label Pod không điều khiển lựa chọn primary của Service |
| Nhãn dùng ký tự đặc biệt hợp lệ | Kiểm tra cú pháp map binding và metadata của fixture |
| SpEL sai cú pháp | Kiểm tra lỗi khởi tạo context hoặc thời điểm đánh giá theo implementation |
| SpEL trả false với mọi service | Assert rỗng và có một control không lọc chứng minh fixture tồn tại |
| HTTP discovery client | Kiểm tra cấu hình namespace/filter trên discovery server, không chỉ phía consumer |

Nhiều điều kiện nhãn phải được hiểu theo selector thực tế; tham khảo [Labels and Selectors](https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/).

Không ép tạo Service không hợp lệ trên API thật chỉ để đi qua một nhánh xử lý dữ liệu lỗi. Những trường hợp không thể biểu diễn bằng resource hợp lệ có thể được kiểm tra ở tầng thấp hơn bằng fixture mô hình hoặc API giả, kèm giải thích phạm vi.

Nếu không chỉ định được một cổng có ý nghĩa và client rơi vào nhánh chọn phần tử đầu tiên, đừng biến thứ tự ngẫu nhiên đó thành hợp đồng nghiệp vụ. Test ứng dụng nên phát hiện cấu hình thiếu định danh hoặc bổ sung quy tắc cấu hình bắt buộc. Việc thư viện có fallback không đồng nghĩa fallback đó phù hợp với ứng dụng.

## 9. Phân biệt discovery, load balancing và kết nối mạng

Bộ test trên chứng minh client tạo ra instance đúng dữ liệu API. Nó chưa chứng minh DNS, NetworkPolicy, TLS certificate hoặc backend HTTP thực sự hoạt động.

Đặc biệt, không dùng test DiscoveryClient để suy ra mọi cấu hình LoadBalancer có cùng quy tắc cổng:

| Đường đi | Đích cần kiểm chứng |
| --- | --- |
| Discovery trực tiếp tới endpoint | IP backend và cổng endpoint |
| LoadBalancer dùng instance discovery | Instance được supplier/balancer chọn, request đích và cơ chế cache |
| Chế độ LoadBalancer đi qua Service | Tên Service theo namespace và cổng Service của chế độ đó |

`spring.cloud.kubernetes.discovery.primary-port-name` và `spring.cloud.kubernetes.loadbalancer.portName` phục vụ các đường chọn cổng khác nhau. Khi dùng chế độ Service của Kubernetes LoadBalancer, cần test riêng URL và cổng tương ứng. Xem [LoadBalancer nhánh 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/load-balancer.html).

Tương tự, `isSecure() = true` và scheme `https` chỉ là thuộc tính của instance trong test. Chưa có TLS handshake diễn ra vì IP của fixture là dữ liệu giả.

Một bộ test đầy đủ cho ứng dụng có thể gồm:

1. Test lựa chọn discovery như bài này.
2. Smoke test với auto-configuration và ServiceAccount thực của ứng dụng.
3. Test request qua Spring Cloud LoadBalancer tới backend thật có dấu hiệu nhận biết instance.
4. Test mạng và readiness của Pod trong cluster.

Không cần bật thêm ConfigMap/Secret API hoặc Configuration Watcher chỉ để chạy test lựa chọn discovery. Cấu hình và quyền bổ sung cần gắn với tính năng đang được xác minh.

## 10. Tránh test pass sai và test chập chờn

### Không tự tạo kết quả mong đợi bằng chính thuật toán cần kiểm thử

Tránh viết một hàm chọn cổng trong test rồi dùng nó tính expected port. Nếu hàm đó sao chép cùng lỗi với production, test vẫn pass.

Các số 8080, 19090 và 8443 trong ví dụ là giá trị đầu vào đã biết của fixture. Assertion ghi rõ giá trị nào phải được chọn trong từng trường hợp.

### Không dựa vào phần tử đầu tiên hoặc thứ tự trả về

Kubernetes list và quá trình xử lý nội bộ không tạo ra một thứ tự nghiệp vụ đáng tin cậy. Dùng `containsExactlyInAnyOrder` cho tập instance; chỉ dùng `containsExactly` khi kỳ vọng đúng một phần tử.

### Không biến lỗi quyền thành kết quả rỗng hợp lệ

Lỗi `403`, timeout hoặc context không khởi động phải làm test fail. Không catch mọi exception rồi trả `List.of()`. Một test kết quả rỗng chỉ có giá trị khi API hoạt động và fixture đối chứng tồn tại.

### Chờ theo điều kiện khi có informer/cache

Client blocking cụ thể của ví dụ đọc API trực tiếp; mẫu không dùng vòng chờ cho việc khởi tạo informer. Nếu chuyển sang implementation có cache, cần chờ điều kiện quan sát được với timeout hữu hạn, chẳng hạn tập tuple đã khớp expected.

Tránh `Thread.sleep(5000)` cố định. Với assertion loại trừ, trước tiên chứng minh cache đã nhìn thấy dữ liệu đối chứng hoặc đã hoàn tất lần đồng bộ cần thiết; danh sách rỗng ngay lúc cache chưa tải xong không chứng minh bộ lọc đúng.

### Cô lập fixture và kết thúc tài nguyên

Mỗi test dùng namespace và `fixture-run` riêng. Không dùng namespace chung rồi xóa toàn bộ service sau test. Mẫu chỉ yêu cầu xóa namespace đã tạo và còn mang marker của lượt chạy.

Xóa namespace có thể hoàn tất bất đồng bộ. CI cần kiểm tra việc dọn môi trường theo timeout của job, đặc biệt khi có admission policy/finalizer. Nếu cleanup lỗi, báo lỗi đó thay vì che giấu; không mở rộng phạm vi xóa để làm sạch bằng mọi giá.

## 11. Đọc lỗi để xác định nguyên nhân

| Kết quả quan sát | Điểm cần kiểm tra đầu tiên |
| --- | --- |
| `getServices()` có tên nhưng instance rỗng | Endpoints cùng tên/namespace, nhãn trên Endpoints, ready address |
| Có IP của C trong test A/B | Cấu hình namespace thực tế, binding danh sách, trạng thái context |
| Mất instance của B | Resource trong B, quyền đọc B, danh sách namespace |
| Port là 80 thay vì 8080 | Đang kiểm tra đường đi Service hay endpoint; số cổng trong fixture |
| Port là 19090 khi mong 8080 | Label `primary-port-name` của Service và property được bind |
| Chỉ filter tên pass, gọi trực tiếp ID bị loại vẫn có instance | Đường lọc `getInstances` và phiên bản client |
| Test tất cả namespace có dữ liệu lạ | Nhãn `fixture-run` trên cả Service/Endpoints, môi trường test |
| Context không khởi tạo | Dependency, property binding, biểu thức sai cú pháp, tạo client |
| `403 Forbidden` | Danh tính client thử nghiệm và RBAC cần cho phép thử |
| Scheme https đúng nhưng request thật lỗi | TLS/network thuộc tầng kiểm thử kết nối riêng |

Khi điều tra, ghi lại cấu hình đã bind và các tuple không nhạy cảm. Có thể lấy Service/Endpoints của đúng namespace để đối chiếu, nhưng không dump kubeconfig hay token vào log.

Đừng sửa expected chỉ dựa trên kết quả vừa nhìn thấy. Đầu tiên xác định test đang kiểm tra hợp đồng nào, input thực tế là gì và implementation/version nào đã chạy.

## 12. Bài thực hành tự kiểm chứng

Hoàn thành các việc sau:

1. Chạy ma trận namespace mặc định, A/B và toàn cluster; giải thích vì sao C là đối chứng cần thiết.
2. Chạy bộ lọc nhãn, bộ lọc biểu thức và tổ hợp cả hai; chỉ ra từng fixture bị loại vì điều kiện nào.
3. Xác nhận property chọn metrics trả 19090, không phải 9090.
4. Xác nhận label của Service ưu tiên hơn property trong ca có chủ đích.
5. Đổi thứ tự cổng và xác nhận chọn theo tên vẫn ổn định.
6. Thêm một ca namespace đúng nhưng thiếu quyền, bảo đảm lỗi không bị biến thành danh sách rỗng.
7. Ghi rõ những gì test chưa chứng minh: traffic backend, TLS, cache LoadBalancer và auto-configuration production.

Một bộ kiểm thử đạt mục tiêu khi có thể chỉ ra chính xác **service nào được giữ, service nào bị loại, instance thuộc namespace nào và vì sao cổng đó được chọn**.
