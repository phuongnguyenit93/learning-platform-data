# Giả lập Kubernetes API phù hợp với loại client

## Mục tiêu bài học

Trong chương **Kiểm thử tự động** của module **SPRING_CLOUD_KUBERNETES**, một API giả lập hữu ích phải đứng đúng ranh giới mà ứng dụng thực sự gọi. Ứng dụng dùng Fabric8, Kubernetes Java Client hoặc HTTP DiscoveryClient có thể cùng làm việc với khái niệm “dịch vụ”, nhưng chúng không dùng cùng kiểu Java, cơ chế khởi tạo hay giao thức ở mọi tầng.

Bài học giúp bạn:

- Nhận diện client đang được dùng và chọn cách giả lập phù hợp.
- Viết kiểm thử qua HTTP cho một adapter đọc ConfigMap.
- Phân biệt đối tượng không tồn tại, thiếu quyền và dữ liệu cấu hình không hợp lệ.
- Chuẩn bị fixture cho discovery, ConfigMap, Secret và LIST/WATCH.
- Tổ chức vòng đời mock server khi kiểm thử Spring, tránh phụ thuộc kubeconfig của máy.
- Xác định phần nào vẫn cần kiểm thử với Kubernetes thật.

Các ví dụ mã là tài liệu thực hành. Chúng không biểu thị rằng test đã được chạy trong repository hoặc cluster hiện tại.

## 1. Chọn ranh giới kiểm thử trước khi chọn công cụ

Giả sử ứng dụng `orders-api` có ba nhu cầu: đọc cấu hình, tìm `inventory-api` và chọn một instance để gọi. Có thể kiểm thử ở các ranh giới khác nhau:

| Mục tiêu | Thành phần thật trong test | Thành phần giả lập |
| --- | --- | --- |
| Logic nghiệp vụ khi không có inventory | Service nghiệp vụ | Một abstraction do ứng dụng định nghĩa hoặc `DiscoveryClient` |
| Request Kubernetes và giải mã phản hồi | Adapter cùng Kubernetes client thật | Kubernetes API qua HTTP |
| Auto-configuration Spring | Context Spring và starter đang dùng | API đúng với provider |
| HTTP DiscoveryClient | HTTP client của Spring Cloud Kubernetes | Discovery Server |
| Quyền RBAC, admission, controller | Ứng dụng, client và cluster thử nghiệm | Chỉ những hệ thống ngoài phạm vi |

Nếu mock trực tiếp `DiscoveryClient.getInstances(...)`, bạn có thể kiểm tra nhánh nghiệp vụ khi không tìm thấy instance. Test đó không xác nhận namespace, đường dẫn Kubernetes API hay việc giải mã Service/EndpointSlice.

Nếu dùng Kubernetes client thật trỏ đến server HTTP giả lập, bạn kiểm tra thêm request và serialization/deserialization. Tuy nhiên, server giả lập không tự trở thành một control plane Kubernetes đầy đủ.

Hãy viết câu mô tả trước mỗi test, chẳng hạn: “Adapter trả về phiên bản cấu hình từ ConfigMap trong namespace đã truyền, nhưng không biến lỗi 403 thành kết quả không tìm thấy.” Câu này quyết định fixture và assertion cần thiết.

## 2. Nhận diện đúng họ client

Spring Cloud Kubernetes có các implementation discovery dựa trên Fabric8, Kubernetes Java Client và HTTP DiscoveryClient. HTTP DiscoveryClient được thiết kế để gọi Spring Cloud Kubernetes Discovery Server. Xem [các loại DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

| Dấu hiệu trong dependency hoặc kiểu Java | Đích HTTP trực tiếp | Cách giả lập phù hợp |
| --- | --- | --- |
| `spring-cloud-starter-kubernetes-fabric8...`, `io.fabric8.kubernetes.client.KubernetesClient` | Kubernetes API | Fabric8 Kubernetes Mock Server hoặc server HTTP có contract tương thích |
| `spring-cloud-starter-kubernetes-client...`, `io.kubernetes.client.openapi.ApiClient` | Kubernetes API | MockWebServer/WireMock hoặc mock API đã kiểm tra tương thích |
| `spring-cloud-starter-kubernetes-discoveryclient` | Spring Cloud Kubernetes Discovery Server | Stub API của Discovery Server |
| Chỉ sử dụng DNS Service | DNS và đường mạng Service | Kiểm thử ở tầng mạng phù hợp; có thể không cần mock Kubernetes API |

Hai kiểu `io.fabric8.kubernetes.api.model.ConfigMap` và `io.kubernetes.client.openapi.models.V1ConfigMap` không thay thế trực tiếp cho nhau. Annotation khởi tạo client Fabric8 cũng không tự tạo `ApiClient` của Kubernetes Java Client.

Server Fabric8 trả về HTTP nên về nguyên tắc client khác có thể gọi nó. Khả năng đó phải được kiểm tra theo endpoint và giao thức cần dùng; không nên suy ra toàn bộ tính năng đều tương thích chỉ vì một lệnh GET thành công.

Không thêm cả hai họ starter vào cùng ứng dụng chỉ để dùng tiện ích mock của một họ. Điều đó có thể thay đổi classpath và auto-configuration mà test đang muốn xác minh.

## 3. Chuẩn bị dependency và phiên bản

Các ví dụ bên dưới dùng Java 17 trở lên và JUnit Jupiter đã được cấu hình trong dự án kiểm thử. Hai nhánh client là **hai lựa chọn**, có thể thực hành trong hai module thử nghiệm riêng.

Mốc API tham chiếu:

| Nhánh ví dụ | Mốc để đọc mã và đối chiếu chữ ký |
| --- | --- |
| Fabric8 | Kubernetes Client/Mock Server `7.4.0` |
| Kubernetes Java Client | `client-java` `22.0.0`, kiểu request builder kết thúc bằng `execute()` |
| HTTP mock cho nhánh Java Client | MockWebServer `4.12.0`, package `okhttp3.mockwebserver` |

Đây là các mốc minh họa, không phải yêu cầu nâng hoặc hạ dependency của ứng dụng Spring. Trong dự án thật, giữ phiên bản client và test library tương thích với BOM/release train đang sử dụng. Khi dùng MockWebServer đời khác, kiểm tra cả tọa độ Maven lẫn package import.

Với Fabric8, dependency kiểm thử cần tương ứng phiên bản client:

```xml
<dependency>
    <groupId>io.fabric8</groupId>
    <artifactId>kubernetes-server-mock</artifactId>
    <version>7.4.0</version>
    <scope>test</scope>
</dependency>
```

Ví dụ giả định `io.fabric8:kubernetes-client` cùng phiên bản đã có trên classpath, cùng implementation HTTP mà client yêu cầu.

Với nhánh Kubernetes Java Client độc lập:

```xml
<dependency>
    <groupId>io.kubernetes</groupId>
    <artifactId>client-java</artifactId>
    <version>22.0.0</version>
</dependency>
<dependency>
    <groupId>com.squareup.okhttp3</groupId>
    <artifactId>mockwebserver</artifactId>
    <version>4.12.0</version>
    <scope>test</scope>
</dependency>
```

Không ghép các con số trên vào một ứng dụng đang có dependency management khác rồi xem lỗi liên kết thư viện là lỗi Kubernetes. Hãy kiểm tra dependency tree và chữ ký API trước.

## 4. Xác định hợp đồng chung cho ví dụ đọc ConfigMap

Ta cần đọc key `demo.config-version` từ ConfigMap `orders-api` trong namespace `test`. Đây là quy ước do ứng dụng ví dụ đặt ra.

Hợp đồng mong muốn:

| Phản hồi | Kết quả của adapter |
| --- | --- |
| 200, có key không rỗng | `Optional.of(value)` |
| 404 cho ConfigMap được yêu cầu | `Optional.empty()` |
| 200, thiếu key hoặc key chỉ chứa khoảng trắng | `IllegalStateException` |
| 401/403 hoặc lỗi HTTP khác | Báo lỗi client, giữ thông tin nguyên nhân |

Không quy mọi lỗi thành “không tìm thấy”. Nếu 403 bị biến thành Optional rỗng, tầng nghiệp vụ có thể âm thầm dùng cấu hình mặc định và che mất lỗi phân quyền.

Fixture phản hồi HTTP thành công:

```json
{
  "apiVersion": "v1",
  "kind": "ConfigMap",
  "metadata": {
    "name": "orders-api",
    "namespace": "test",
    "resourceVersion": "12"
  },
  "data": {
    "demo.config-version": "cfg-02"
  }
}
```

Đây là fixture cho **adapter đọc một key**, chưa phải bài kiểm thử PropertySource của Spring. Kiểm thử `application.yaml` trong ConfigMap, profile và property precedence cần được thực hiện ở tầng tích hợp Spring.

## 5. Nhánh Fabric8: dùng client thật với Kubernetes Mock Server

### 5.1. Adapter cần kiểm thử

Ví dụ lớp `Fabric8ConfigVersionReader`:

```java
package example.k8stest;

import io.fabric8.kubernetes.api.model.ConfigMap;
import io.fabric8.kubernetes.client.KubernetesClient;
import java.util.Optional;

public final class Fabric8ConfigVersionReader {
    private final KubernetesClient client;

    public Fabric8ConfigVersionReader(KubernetesClient client) {
        this.client = client;
    }

    public Optional<String> read(String namespace, String name) {
        ConfigMap configMap = client.configMaps()
            .inNamespace(namespace)
            .withName(name)
            .get();

        if (configMap == null) {
            return Optional.empty();
        }

        String value = configMap.getData() == null
            ? null
            : configMap.getData().get("demo.config-version");

        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                "ConfigMap lacks demo.config-version");
        }
        return Optional.of(value);
    }
}
```

Ở đường đọc này, Fabric8 có thể biểu diễn tài nguyên 404 bằng `null`. Các lỗi như 403 vẫn đi ra bằng exception; adapter không bắt chung rồi trả về Optional rỗng.

### 5.2. Expectations mode cho phản hồi cụ thể

Fabric8 có expectations mode và CRUD mode. Expectations phù hợp với việc cố định đường dẫn, mã HTTP và phản hồi; CRUD giữ trạng thái tài nguyên trong bộ nhớ. Xem [Mocking Kubernetes trong Fabric8 7.4.0](https://github.com/fabric8io/kubernetes-client/blob/v7.4.0/README.md#mocking-kubernetes).

```java
package example.k8stest;

import io.fabric8.kubernetes.api.model.ConfigMapBuilder;
import io.fabric8.kubernetes.api.model.StatusBuilder;
import io.fabric8.kubernetes.client.KubernetesClient;
import io.fabric8.kubernetes.client.KubernetesClientException;
import io.fabric8.kubernetes.client.server.mock.EnableKubernetesMockClient;
import io.fabric8.kubernetes.client.server.mock.KubernetesMockServer;
import java.util.Optional;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

@EnableKubernetesMockClient(https = false, crud = false)
class Fabric8ConfigVersionReaderTest {
    KubernetesMockServer server;
    KubernetesClient client;

    @Test
    void readsVersionFromRequestedNamespace() {
        server.expect().get()
            .withPath("/api/v1/namespaces/test/configmaps/orders-api")
            .andReturn(200, new ConfigMapBuilder()
                .withNewMetadata()
                    .withName("orders-api")
                    .withNamespace("test")
                .endMetadata()
                .addToData("demo.config-version", "cfg-02")
                .build())
            .once();

        var reader = new Fabric8ConfigVersionReader(client);

        assertEquals(Optional.of("cfg-02"),
            reader.read("test", "orders-api"));
    }

    @Test
    void representsMissingConfigMapAsEmpty() {
        server.expect().get()
            .withPath("/api/v1/namespaces/test/configmaps/orders-api")
            .andReturn(404, new StatusBuilder()
                .withCode(404)
                .withReason("NotFound")
                .withStatus("Failure")
                .withMessage("ConfigMap absent in this test")
                .build())
            .once();

        var reader = new Fabric8ConfigVersionReader(client);

        assertTrue(reader.read("test", "orders-api").isEmpty());
    }

    @Test
    void preservesForbiddenAsAnError() {
        server.expect().get()
            .withPath("/api/v1/namespaces/test/configmaps/orders-api")
            .andReturn(403, new StatusBuilder()
                .withCode(403)
                .withReason("Forbidden")
                .withStatus("Failure")
                .withMessage("Read forbidden in this test")
                .build())
            .once();

        var reader = new Fabric8ConfigVersionReader(client);

        KubernetesClientException error = assertThrows(
            KubernetesClientException.class,
            () -> reader.read("test", "orders-api"));

        assertEquals(403, error.getCode());
    }
}
```

Annotation đưa client/server vào các field tương ứng và quản lý vòng đời của chúng. Ví dụ chọn HTTP rõ ràng bằng `https = false` để tập trung vào contract đọc dữ liệu; test TLS cần cấu hình và assertion riêng. Xem [annotation của phiên bản tham chiếu](https://github.com/fabric8io/kubernetes-client/blob/v7.4.0/junit/kubernetes-server-mock/src/main/java/io/fabric8/kubernetes/client/server/mock/EnableKubernetesMockClient.java).

Test 200 đồng thời phát hiện đường dẫn hoặc namespace sai vì phản hồi thành công chỉ gắn với request đã khai báo. Riêng test 404 cần đặc biệt kiểm tra request thực tế: một request không khớp expectation cũng có thể nhận 404 từ mock. Khi mở rộng bộ test, dùng request log/verification của đúng phiên bản mock để phân biệt hai nguồn 404 này.

Thêm test 200 thiếu key để kiểm tra chính sách dữ liệu của adapter. Không chỉ kiểm tra trường hợp client nhận được một đối tượng bất kỳ.

### 5.3. CRUD mode khi cần trạng thái và cô lập namespace

Khi mục tiêu là đọc dữ liệu đã tạo, không cần viết expectation cho mọi GET. Ví dụ sau kiểm tra việc cùng tên tài nguyên ở hai namespace không bị lẫn:

```java
package example.k8stest;

import io.fabric8.kubernetes.api.model.ConfigMapBuilder;
import io.fabric8.kubernetes.client.KubernetesClient;
import io.fabric8.kubernetes.client.server.mock.EnableKubernetesMockClient;
import java.util.Optional;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

@EnableKubernetesMockClient(https = false, crud = true)
class Fabric8NamespaceIsolationTest {
    KubernetesClient client;

    @Test
    void readsConfigOnlyFromTheRequestedNamespace() {
        seed("test", "cfg-test");
        seed("other", "cfg-other");

        var reader = new Fabric8ConfigVersionReader(client);

        assertEquals(Optional.of("cfg-test"),
            reader.read("test", "orders-api"));
        assertEquals(Optional.of("cfg-other"),
            reader.read("other", "orders-api"));
    }

    private void seed(String namespace, String version) {
        client.configMaps().inNamespace(namespace)
            .resource(new ConfigMapBuilder()
                .withNewMetadata()
                    .withName("orders-api")
                    .withNamespace(namespace)
                .endMetadata()
                .addToData("demo.config-version", version)
                .build())
            .create();
    }
}
```

CRUD mode giúp giảm thiết lập fixture, nhưng mức xử lý namespace, validation và controller không tương đương cluster thật. Test trên chứng minh adapter chọn namespace trong phạm vi mock, chưa chứng minh Namespace hoặc RoleBinding đã được triển khai đúng.

Tách expectations mode và CRUD mode thành các lớp có mục đích rõ ràng. Trộn stateful dispatcher với expectation đặc biệt mà không hiểu thứ tự ưu tiên dễ tạo test khó giải thích.

## 6. Nhánh Kubernetes Java Client: cấu hình ApiClient về HTTP mock

### 6.1. Adapter dùng kiểu dữ liệu của Kubernetes Java Client

```java
package example.k8stest;

import io.kubernetes.client.openapi.ApiException;
import io.kubernetes.client.openapi.apis.CoreV1Api;
import io.kubernetes.client.openapi.models.V1ConfigMap;
import java.util.Optional;

public final class OfficialConfigVersionReader {
    private final CoreV1Api api;

    public OfficialConfigVersionReader(CoreV1Api api) {
        this.api = api;
    }

    public Optional<String> read(String namespace, String name)
            throws ApiException {
        try {
            V1ConfigMap configMap = api
                .readNamespacedConfigMap(name, namespace)
                .execute();

            if (configMap == null) {
                throw new IllegalStateException(
                    "API returned no ConfigMap body");
            }

            String value = configMap.getData() == null
                ? null
                : configMap.getData().get("demo.config-version");

            if (value == null || value.isBlank()) {
                throw new IllegalStateException(
                    "ConfigMap lacks demo.config-version");
            }
            return Optional.of(value);
        } catch (ApiException error) {
            if (error.getCode() == 404) {
                return Optional.empty();
            }
            throw error;
        }
    }
}
```

Chữ ký trong ví dụ thuộc kiểu request builder của phiên bản tham chiếu; client đời khác có thể dùng chữ ký khác. Đối chiếu [CoreV1Api 22.0.0](https://github.com/kubernetes-client/java/blob/v22.0.0/kubernetes/src/main/java/io/kubernetes/client/openapi/apis/CoreV1Api.java).

Ở nhánh này, adapter xử lý `ApiException` mã 404 một cách tường minh. Hợp đồng bên ngoài giống nhánh Fabric8 dù cách client biểu diễn phản hồi khác nhau.

### 6.2. Test kiểm tra cả dữ liệu và request

Ví dụ dưới đây chỉ có một lời gọi đồng bộ trong mỗi test, nên có thể dùng hàng đợi phản hồi. Mỗi test có server riêng, cổng ngẫu nhiên và timeout hữu hạn.

```java
package example.k8stest;

import io.kubernetes.client.openapi.ApiClient;
import io.kubernetes.client.openapi.ApiException;
import io.kubernetes.client.openapi.apis.CoreV1Api;
import java.util.Optional;
import java.util.concurrent.TimeUnit;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OfficialConfigVersionReaderTest {
    private MockWebServer server;
    private ApiClient apiClient;
    private OfficialConfigVersionReader reader;

    @BeforeEach
    void setUp() throws Exception {
        server = new MockWebServer();
        server.start();

        String rootUrl = server.url("/").toString();
        apiClient = new ApiClient()
            .setBasePath(rootUrl.substring(0, rootUrl.length() - 1))
            .setConnectTimeout(1000)
            .setReadTimeout(1000);

        reader = new OfficialConfigVersionReader(
            new CoreV1Api(apiClient));
    }

    @AfterEach
    void tearDown() throws Exception {
        if (apiClient != null) {
            apiClient.getHttpClient().dispatcher().cancelAll();
            apiClient.getHttpClient().connectionPool().evictAll();
            apiClient.getHttpClient().dispatcher()
                .executorService().shutdownNow();
        }
        if (server != null) {
            server.shutdown();
        }
    }

    @Test
    void readsAndDecodesTheVersion() throws Exception {
        server.enqueue(json(200, """
            {
              "apiVersion": "v1",
              "kind": "ConfigMap",
              "metadata": {
                "name": "orders-api",
                "namespace": "test",
                "resourceVersion": "12"
              },
              "data": {"demo.config-version": "cfg-02"}
            }
            """));

        assertEquals(Optional.of("cfg-02"),
            reader.read("test", "orders-api"));

        assertConfigReadRequest();
    }

    @Test
    void represents404AsEmpty() throws Exception {
        server.enqueue(json(404, status(404, "NotFound")));

        assertTrue(reader.read("test", "orders-api").isEmpty());

        assertConfigReadRequest();
    }

    @Test
    void doesNotHide403AsMissingConfiguration() throws Exception {
        server.enqueue(json(403, status(403, "Forbidden")));

        ApiException error = assertThrows(ApiException.class,
            () -> reader.read("test", "orders-api"));

        assertEquals(403, error.getCode());
        assertConfigReadRequest();
    }

    private void assertConfigReadRequest() throws Exception {
        RecordedRequest request =
            server.takeRequest(1, TimeUnit.SECONDS);
        assertNotNull(request, "Expected a request to the mock API");
        assertEquals("GET", request.getMethod());
        assertEquals(
            "/api/v1/namespaces/test/configmaps/orders-api",
            request.getPath());
        assertEquals(1, server.getRequestCount());
    }

    private static MockResponse json(int code, String body) {
        return new MockResponse()
            .setResponseCode(code)
            .setHeader("Content-Type", "application/json")
            .setBody(body);
    }

    private static String status(int code, String reason) {
        return """
            {
              "apiVersion": "v1",
              "kind": "Status",
              "status": "Failure",
              "code": %d,
              "reason": "%s",
              "message": "Synthetic API response for this test"
            }
            """.formatted(code, reason);
    }
}
```

`new ApiClient()` ở đây được cấu hình trực tiếp về mock, thay vì gọi một hàm tự tìm kubeconfig hoặc thông tin in-cluster. Việc đặt base path và timeout dựa trên [API của ApiClient](https://github.com/kubernetes-client/java/blob/v22.0.0/kubernetes/src/main/java/io/kubernetes/client/openapi/ApiClient.java).

Đóng executor/connection pool chỉ phù hợp vì test sở hữu client riêng. Nếu ứng dụng dùng HTTP client chia sẻ, chủ sở hữu tài nguyên đó phải quản lý vòng đời; không đóng nó từ một test khác đang chạy song song.

MockWebServer hỗ trợ lập trình phản hồi và đọc lại request; xem [tài liệu phiên bản 4.12.0](https://github.com/square/okhttp/blob/parent-4.12.0/mockwebserver/README.md). Không dùng `takeRequest()` không timeout trong test có thể thiếu request, vì nó có thể chờ vô hạn.

### 6.3. Khi nào chuyển từ queue sang Dispatcher?

Nếu context Spring khởi tạo nhiều lister, gọi health check hoặc mở watch, thứ tự request có thể thay đổi. Một hàng đợi “phản hồi đầu tiên dành cho ConfigMap, phản hồi thứ hai dành cho Service” trở nên mong manh.

Khi đó, dùng Dispatcher dựa trên:

- HTTP method.
- Đường dẫn đã phân tích.
- Namespace.
- Query parameter có ý nghĩa như `labelSelector`, `watch` hoặc `resourceVersion`.

Không so sánh cứng toàn bộ chuỗi query nếu thứ tự tham số không thuộc contract cần kiểm thử. Request ngoài danh sách phải nhận phản hồi thất bại rõ ràng và xuất hiện trong chẩn đoán; không trả 200 cho mọi đường dẫn.

Nếu test có background request hợp lệ, thay assertion “chỉ có đúng một request” bằng kiểm tra request mục tiêu và các bất biến phù hợp. Đừng sao chép assertion của test adapter đồng bộ sang toàn bộ context Spring.

## 7. Fixture phải khớp tài nguyên và thao tác

### 7.1. GET một đối tượng khác với LIST

| Thao tác | Đường dẫn điển hình | Kiểu phản hồi |
| --- | --- | --- |
| Đọc ConfigMap | `/api/v1/namespaces/test/configmaps/orders-api` | `ConfigMap` |
| Liệt kê ConfigMap | `/api/v1/namespaces/test/configmaps` | `ConfigMapList` |
| Liệt kê Service | `/api/v1/namespaces/test/services` | `ServiceList` |
| Liệt kê Endpoints | `/api/v1/namespaces/test/endpoints` | `EndpointsList` |
| Liệt kê EndpointSlice | `/apis/discovery.k8s.io/v1/namespaces/test/endpointslices` | `EndpointSliceList` |

Không trả một ConfigMap đơn lẻ cho request LIST. Fixture rỗng cho LIST vẫn cần cấu trúc danh sách phù hợp, ví dụ:

```json
{
  "apiVersion": "v1",
  "kind": "ConfigMapList",
  "metadata": {"resourceVersion": "12"},
  "items": []
}
```

Một số đường khởi tạo client còn gọi `/version`, `/api`, `/apis` hoặc API discovery của group. Hãy xem request thực tế của client/release đang dùng rồi bổ sung fixture. Không khẳng định mọi client luôn có cùng chuỗi khởi tạo.

### 7.2. Dữ liệu discovery cần có quan hệ hợp lệ

Khi kiểm thử tích hợp DiscoveryClient, tạo fixture theo quan hệ nghiệp vụ:

- Service `inventory-api` nằm trong namespace mục tiêu.
- Cổng có tên/protocol đúng, nhất là khi Service có nhiều cổng.
- Endpoints hoặc EndpointSlice có địa chỉ và cổng phù hợp.
- Trạng thái ready/not-ready phản ánh kịch bản kiểm thử.
- Pod/metadata được cung cấp nếu implementation cần đọc thêm.
- Tài nguyên ở namespace khác hoặc không khớp label phải bị loại đúng thiết kế.

Tạo một Service trong mock không bảo đảm có controller tự sinh Endpoints hoặc EndpointSlice. Bạn phải cấp fixture phụ thuộc hoặc dùng môi trường có controller thật.

Một test discovery có ý nghĩa nên xác nhận instance được trả về có đúng host, port, service ID và namespace. Chỉ kiểm tra “danh sách không rỗng” có thể bỏ lọt việc trả nhầm dịch vụ.

### 7.3. Secret cần được giả lập ở dạng API trả về

Fixture Secret chỉ sử dụng dữ liệu tổng hợp. Phản hồi đọc Secret sử dụng `data` với giá trị mã hóa base64; đừng giả định API sẽ trả lại trường đầu vào `stringData`.

Ví dụ một giá trị thử nghiệm không phải bí mật thật:

```json
{
  "apiVersion": "v1",
  "kind": "Secret",
  "metadata": {"name": "orders-api-test", "namespace": "test"},
  "type": "Opaque",
  "data": {"sample": "dGVzdC1vbmx5"}
}
```

Kiểm tra kiểu dữ liệu Java của model trong client đã chọn trước khi giải mã. Không mặc định mọi thư viện trả cùng kiểu và không giải mã base64 hai lần. Với Fabric8, có thể đối chiếu [model Secret của phiên bản tham chiếu](https://github.com/fabric8io/kubernetes-client/blob/v7.4.0/kubernetes-model-generator/kubernetes-model-core/src/generated/java/io/fabric8/kubernetes/api/model/Secret.java).

Khi test thất bại, chẩn đoán nên nêu tên key hoặc loại lỗi; không cần in toàn bộ giá trị Secret.

## 8. Khởi tạo mock đúng thời điểm trong kiểm thử Spring

Đường đi thường gặp:

```text
Khởi động mock server
  -> đăng ký fixture cho giai đoạn khởi tạo
  -> cung cấp URL/namespace cho đúng provider
  -> tạo hoặc khởi động Spring context
  -> chờ cache/informer sẵn sàng nếu có
  -> gọi hành vi cần kiểm thử
  -> xác minh kết quả và request
  -> dừng tác vụ nền, context/client và mock server
```

### 8.1. Client bean thông thường

Với bean được tạo trong context chính, có thể dùng cấu hình kiểm thử đưa đúng `KubernetesClient` hoặc `ApiClient` vào bean cần dùng. Nếu chỉ đánh dấu bean test là `@Primary`, vẫn phải kiểm tra các consumer có lấy đúng bean đó hay không; không suy ra một bean cấp thấp sẽ thay mọi client nội bộ của starter.

Spring hỗ trợ `@DynamicPropertySource` để cung cấp giá trị động từ tài nguyên bên ngoài. Method phải là static và nhận một `DynamicPropertyRegistry`. Xem [dynamic property sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html).

Ví dụ ý tưởng cho thuộc tính **do test tự định nghĩa**:

```java
@DynamicPropertySource
static void apiProperties(DynamicPropertyRegistry registry) {
    registry.add("test.kubernetes-api-url",
        () -> mockServer.url("/").toString());
}
```

Ví dụ giả định `mockServer` đã được khởi động và còn sống khi context dùng supplier. Thuộc tính `test.kubernetes-api-url` không phải thuộc tính tự động của Spring Cloud Kubernetes. Bean test phải đọc nó rồi đặt vào `ApiClient.setBasePath(...)` hoặc cấu hình URL của Fabric8, tùy client.

### 8.2. Config Data hoặc bootstrap là ranh giới sớm hơn

Nếu đang kiểm thử việc nạp ConfigMap bằng `spring.config.import: "kubernetes:"`, request có thể xuất hiện trong giai đoạn chuẩn bị Environment, trước khi bean test thông thường được tạo. Đăng ký mock client trong `@BeforeEach` có thể quá muộn.

Cần bảo đảm server, fixture và cấu hình provider đã có trước thời điểm loader khởi tạo client. Không giả định `@Primary` trong context chính hoặc mọi cơ chế dynamic property đều can thiệp được vào mọi bootstrap path; xác minh bằng request ghi nhận tại mock.

Chọn Config Data hoặc cơ chế bootstrap phù hợp release, không bật lẫn hai cách để chữa lỗi test. Xem [Kubernetes PropertySource implementations](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config.html).

Một test PropertySource nên đặt giá trị khác nhau ở cấu hình mặc định và ConfigMap, sau đó kiểm tra giá trị hiệu lực. Nếu cả hai đều là `cfg-02`, test có thể đỗ dù loader chưa gọi API. Khi muốn kiểm tra lỗi tải cấu hình, cấu hình fail-fast/optional phải phản ánh chính sách thật.

### 8.3. Context cache và chạy song song

Spring có thể tái sử dụng context giữa các test. Nếu server của lớp trước đã dừng nhưng context còn giữ URL cũ, test sau có thể lỗi ngẫu nhiên.

Thiết kế vòng đời server đi cùng vòng đời context. Dùng context riêng hoặc làm bẩn context khi endpoint/fixture thay đổi theo cách không tương thích cache. Mỗi test chạy song song cần namespace/tên tài nguyên hoặc server riêng; không chia sẻ một queue phản hồi có trạng thái ngoài ý muốn.

## 9. LIST/WATCH cần kịch bản thay đổi, không chỉ một phản hồi GET

Informer thường tải danh sách rồi theo dõi thay đổi. Fixture phải mô tả cả dữ liệu ban đầu và diễn biến tiếp theo. Với watch JSON qua HTTP, mỗi event là một JSON object trong luồng; không tự đổi thành SSE.

Ví dụ chuỗi event cho một ConfigMap:

```json
{"type":"ADDED","object":{"apiVersion":"v1","kind":"ConfigMap","metadata":{"name":"orders-api","namespace":"test","resourceVersion":"13"},"data":{"demo.config-version":"cfg-01"}}}
{"type":"MODIFIED","object":{"apiVersion":"v1","kind":"ConfigMap","metadata":{"name":"orders-api","namespace":"test","resourceVersion":"14"},"data":{"demo.config-version":"cfg-02"}}}
```

Kịch bản cần nêu rõ LIST trước đó trả resourceVersion nào, request watch dùng query gì và lúc nào luồng đóng. Xử lý tài nguyên quá cũ có thể cần relist khi gặp `410 Gone`. Đối chiếu [Kubernetes API Concepts](https://kubernetes.io/docs/reference/using-api/api-concepts/#efficient-detection-of-changes).

Đừng chỉ assert mock đã gửi event. Kiểm tra kết quả mà consumer quan sát sau sự kiện, chẳng hạn discovery loại bỏ một endpoint hoặc bean đọc cấu hình nhận phiên bản mới theo cơ chế hỗ trợ.

Với trạng thái bất đồng bộ, chờ theo điều kiện có thời hạn; không dùng `Thread.sleep(...)` cố định để giả định cache đã cập nhật. Khi dừng test, đóng watch/informer trước server để tránh vòng reconnect không mong muốn.

## 10. HTTP DiscoveryClient cần mock Discovery Server

Nếu ứng dụng dùng HTTP DiscoveryClient, caller trực tiếp nói chuyện với Discovery Server. Stub Kubernetes `/api/v1/...` tại URL của Discovery Server sẽ sai contract.

Discovery Server có các endpoint như `/apps` và `/apps/{name}`. Payload là thông tin dịch vụ/instance theo contract của server, không phải nguyên một `ServiceList` của Kubernetes. Xem [Discovery Server endpoints](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-discoveryserver.html).

Tách mục tiêu kiểm thử:

| Mục tiêu | Cách tổ chức |
| --- | --- |
| Caller giải mã danh sách instance | Mock HTTP Discovery Server |
| Discovery Server chuyển tài nguyên Kubernetes thành instance | Chạy implementation server với mock Kubernetes API phù hợp |
| Caller và server tương thích release | Kiểm thử hợp đồng hoặc chạy cả hai với version được khóa |
| Discovery dùng ServiceAccount đúng quyền | Kiểm thử server trên cluster thử nghiệm |

Khi caller nhận 403 từ Discovery Server, đó không tự động là lỗi RBAC Kubernetes của caller. Có thể đó là phân quyền HTTP ở tầng server. Muốn chẩn đoán RBAC, cần theo dõi request từ Discovery Server đến Kubernetes API.

## 11. Mở rộng tới LoadBalancer và Configuration Watcher

### 11.1. Spring Cloud LoadBalancer

Nếu chỉ kiểm tra thuật toán chọn instance hoặc xử lý danh sách rỗng, giả lập abstraction cung cấp instance có thể đủ. Nếu kiểm tra nguồn instance từ Kubernetes, giữ DiscoveryClient thật và cấp fixture API phù hợp.

Một kiểm thử chọn đích cần quan sát host/port hoặc server nghiệp vụ nhận request. Không gọi địa chỉ Pod tổng hợp trong fixture rồi kỳ vọng nó có server thật phía sau. Đặt backend HTTP thử nghiệm riêng khi mục tiêu bao gồm lời gọi mạng.

Đừng yêu cầu mọi implementation chọn luân phiên tuyệt đối nếu đó không phải contract được cấu hình. Kiểm tra điều quan trọng với ứng dụng: chỉ chọn instance hợp lệ, dùng đúng cổng và xử lý lỗi theo chính sách.

### 11.2. Configuration Watcher

Có thể kiểm thử một phần chuỗi bằng mock: sự kiện ConfigMap/Secret được nhận diện, tìm đúng ứng dụng đích và phát yêu cầu refresh đúng đường dẫn. Backend nhận refresh là một server HTTP khác với Kubernetes API mock.

Test cần phân biệt:

- Mock API phát sự kiện.
- Watcher xử lý sự kiện và gửi thông báo.
- Instance Spring nhận thông báo.
- Giá trị cấu hình thực sự thay đổi trong bean phục vụ yêu cầu.

Một assertion “đã gửi POST refresh” chỉ chứng minh một mắt xích. Mount file trong Pod, đồng bộ kubelet và hành vi refresh đầy đủ cần các test có phạm vi tương ứng.

Nếu kiến trúc chỉ dùng rollout để cập nhật cấu hình và không triển khai Watcher, không cần thêm mock Watcher vào mọi bộ test.

## 12. Thiết kế lỗi và retry để test có ý nghĩa

| Kịch bản | Điều cần kiểm tra |
| --- | --- |
| 200 với danh sách rỗng | Phân biệt không có instance với lỗi truy cập API |
| 404 tài nguyên yêu cầu | Chính sách thiếu nguồn cấu hình có đúng không |
| 401/403 | Lỗi được giữ nguyên hoặc chuyển thành lỗi miền rõ ràng |
| 429/5xx | Retry có giới hạn, hành vi sau khi hết retry |
| JSON sai hoặc thiếu key bắt buộc | Không âm thầm coi là dữ liệu hợp lệ |
| Phản hồi chậm/ngắt kết nối | Timeout hữu hạn và lỗi không bị treo |
| Request sai namespace | Mock không trả nhầm fixture thành công |
| Watch đóng hoặc lỗi | Đóng tài nguyên, khôi phục theo chính sách cần kiểm thử |

Client có thể có retry mặc định. Nếu expectation cho 500 chỉ dùng `once()`, lần retry sau có thể nhận 404 do không còn phản hồi khớp, làm bạn chẩn đoán sai. Fabric8 mô tả vấn đề này trong [FAQ về test phản hồi lỗi](https://github.com/fabric8io/kubernetes-client/blob/main/doc/FAQ.md#why-are-my-tests-for-failure-scenarios-4xx5xx-running-slow).

Tách hai mục tiêu:

- Test ánh xạ lỗi: cấu hình retry phù hợp để nhìn rõ mã lỗi cần kiểm tra.
- Test retry: cấp đủ chuỗi phản hồi và xác minh số lần/thời hạn theo chính sách đã chọn.

Không sửa retry toàn cục bằng system property mà quên khôi phục, khiến các lớp test khác phụ thuộc thứ tự chạy. Nếu cần thay đổi cấu hình JVM dùng chung, phải cô lập vòng đời hoặc tiến trình.

## 13. Những điều mock không chứng minh được

Test mock HTTP giúp tìm lỗi request và xử lý phản hồi sớm. Nó không đủ để kết luận các hành vi sau đúng trên hệ thống triển khai:

- Role/RoleBinding thực sự cho phép ServiceAccount đọc tài nguyên.
- Admission, schema validation và field ownership của API server.
- Controller tạo EndpointSlice theo Service selector.
- Kubelet chiếu ConfigMap/Secret, bao gồm độ trễ cập nhật.
- DNS Service, NetworkPolicy và kết nối Pod.
- Tương thích đầy đủ với phiên bản Kubernetes mục tiêu.

Trả 403 từ mock chỉ chứng minh cách ứng dụng phản ứng với 403. Nó không kiểm tra rule RBAC có đúng API group, namespace hay verb.

Chọn cấp môi trường theo mục tiêu: mock cho feedback nhanh; API server thật cho semantics API cần thiết; cluster thử nghiệm cho controller, mạng và Pod. Một môi trường chỉ có API server/etcd vẫn không tự có đầy đủ kubelet, DNS hoặc mọi controller.

## 14. Chẩn đoán test đang thất bại

Khi một test mock không đỗ, kiểm tra theo thứ tự:

1. **Đúng client chưa?** So sánh dependency, kiểu bean và provider được khởi tạo.
2. **Đúng URL chưa?** Request phải đến loopback/port của mock, không phải kubeconfig máy.
3. **Đúng thời điểm chưa?** Server và fixture có trước bootstrap/Config Data không?
4. **Đúng endpoint chưa?** Phân biệt GET/LIST/WATCH, core API và API group.
5. **Đúng request chưa?** Namespace, selector, query và header có phù hợp?
6. **Đúng body chưa?** Object/List/Status, kind, metadata và data có đúng cấu trúc?
7. **Có request nền hoặc retry không?** Chúng có tiêu thụ queue phản hồi không?
8. **Đúng assertion chưa?** Đang kiểm tra hành vi ứng dụng hay chỉ kiểm tra fixture?
9. **Đã đóng tài nguyên chưa?** Client, watch, executor và context còn giữ trạng thái không?

Giữ request log vừa đủ để xác định lỗi. Không biến một expectation quá rộng thành cách làm test đỗ nếu nó che mất namespace hoặc đường dẫn sai.

## 15. Bài tập và tiêu chí hoàn thành

Thực hành với **một** họ client mà ứng dụng của bạn sử dụng:

1. Chạy ba kịch bản 200, 404 và 403 cho adapter đọc ConfigMap; xác minh request đi đúng namespace.
2. Thêm kịch bản 200 thiếu `demo.config-version` và chứng minh nó không bị hiểu là tài nguyên không tồn tại.
3. Tạo cùng tên ConfigMap ở hai namespace với giá trị khác nhau; kiểm tra tính cô lập.
4. Với discovery, tạo Service có hai cổng và fixture endpoint tương ứng; xác minh host/port được chọn theo cấu hình.
5. Nếu dùng informer, dựng LIST ban đầu rồi MODIFIED event; chờ theo điều kiện và kiểm tra kết quả consumer.
6. Viết rõ một test cần cluster thật, chẳng hạn xác minh RoleBinding hoặc Service selector sinh EndpointSlice.

Một bộ test đạt mục tiêu bài học khi:

- Client thật đúng với provider của ứng dụng; dependency test không vô tình thay kiến trúc.
- Endpoint, namespace và fixture được khai báo rõ, không phụ thuộc cluster cá nhân.
- Có assertion cho dữ liệu thành công, dữ liệu thiếu và lỗi quyền.
- Timeout, retry, request nền và vòng đời tài nguyên được kiểm soát.
- Kết quả test cho biết nó chứng minh điều gì và phần nào chưa được bao phủ.
- Test tích hợp Spring, LoadBalancer hoặc Watcher chỉ được thêm khi tính năng đó thực sự được sử dụng.

Khi review một test, hãy thử đổi namespace, đường dẫn hoặc mã 403 trong fixture. Nếu test vẫn đỗ mà lẽ ra phải phát hiện thay đổi, ranh giới hoặc assertion của nó cần được làm rõ.
