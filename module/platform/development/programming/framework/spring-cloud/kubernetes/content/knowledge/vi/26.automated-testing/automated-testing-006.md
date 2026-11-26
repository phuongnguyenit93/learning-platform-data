# Kiểm thử thứ tự ưu tiên ConfigMap và Secret

## Mục tiêu và phạm vi

Trong chương **Kiểm thử tự động** của module **SPRING_CLOUD_KUBERNETES**, việc kiểm thử cấu hình cần trả lời hai câu hỏi khác nhau: ứng dụng có nạp đúng nguồn hay không, và nguồn nào quyết định giá trị khi nhiều nơi cùng khai báo một key.

Bài học này tập trung vào ConfigMap và Secret được Spring Cloud Kubernetes đưa vào Spring Environment. Sau bài học, bạn có thể:

- Viết ca kiểm thử có xung đột giá trị thật sự giữa hai nguồn.
- Chứng minh cả ConfigMap và Secret đã được nạp trước khi kết luận về ưu tiên.
- Kiểm tra giá trị hiệu lực qua Environment và bean cấu hình.
- Tách ưu tiên giữa hai nguồn Kubernetes khỏi ưu tiên toàn cục của Spring Boot.
- Kiểm soát profile, namespace, fixture, vòng đời context và cấu hình máy chạy test.
- Phân biệt thứ tự ưu tiên với lỗi quyền, dữ liệu thiếu và hành vi refresh.

Các ví dụ chỉ dùng giá trị tổng hợp, không dùng thông tin xác thực thật. Chúng là hướng dẫn thực hành, không phải kết quả test đã chạy trong repository hiện tại.

## 1. Xác định chính xác quy tắc cần kiểm thử

Khi ConfigMap và Secret cùng được nạp qua cơ chế PropertySource của Spring Cloud Kubernetes và cùng cung cấp một property, **giá trị từ ConfigMap có ưu tiên cao hơn Secret**. Không suy luận rằng Secret luôn thắng vì chứa dữ liệu nhạy cảm. Xem [Order of ConfigMaps and Secrets](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/order_of_configMaps_and_secrets.html).

Ví dụ:

| Nguồn | Key | Giá trị tổng hợp |
| --- | --- | --- |
| ConfigMap | `demo.precedence.winner` | `from-configmap` |
| Secret, sau giải mã | `demo.precedence.winner` | `from-secret` |
| Giá trị mặc định của ứng dụng | `demo.precedence.winner` | `from-default` |

Nếu không có nguồn ưu tiên cao hơn can thiệp, kết quả mong đợi là `from-configmap`.

Cần giới hạn phát biểu này vào đúng cơ chế nạp. Nếu Secret được đưa thành biến môi trường của tiến trình còn ConfigMap được nạp bằng Config Data, bạn đang so sánh hai loại PropertySource khác. Khi cả hai được đưa qua `envFrom`, quy tắc của PodSpec lại là một tầng khác nữa.

Một tên tài nguyên Kubernetes không mang theo “độ ưu tiên” chung cho mọi cách tiêu thụ.

## 2. Tách ba tầng ưu tiên

| Tầng | Ví dụ xung đột | Cách thiết kế test |
| --- | --- | --- |
| Bên trong một nguồn | Key phẳng và key trong file cấu hình nhúng | Dùng một ConfigMap/Secret, thay một yếu tố |
| Giữa các nguồn Kubernetes | ConfigMap và Secret cùng key | Cùng tên key, giá trị khác, chứng minh cả hai đã nạp |
| Toàn bộ Environment | Config Data và command-line argument | Giữ nguồn Kubernetes, thêm đúng một override bên ngoài |

Với Config Data, cấu hình import được xử lý theo quy tắc Spring Boot; command-line argument, Java system property và biến môi trường có thể có ưu tiên cao hơn dữ liệu import. Cơ chế bootstrap cũ cần được kiểm thử riêng, theo release đang dùng. Xem [Kubernetes PropertySource implementations](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config.html).

Không trộn tất cả tầng trong test đầu tiên. Nếu vừa bật profile, vừa dùng nhiều ConfigMap, vừa đặt giá trị tại `@SpringBootTest(properties = ...)`, kết quả khó chỉ ra quy tắc nào đã được xác minh.

## 3. Thiết kế fixture chống kết quả đỗ giả

Chỉ kiểm tra `winner=from-configmap` là chưa đủ. Nếu Secret bị tắt hoặc không được đọc, assertion đó vẫn có thể đỗ.

Fixture nên có một key trùng và một key riêng cho mỗi nguồn:

| Key | ConfigMap | Secret |
| --- | --- | --- |
| `demo.precedence.winner` | `from-configmap` | `from-secret` |
| `demo.probe.configmap-marker` | `cm-loaded` | Không có |
| `demo.probe.secret-marker` | Không có | `secret-loaded` |

Ba assertion nền tảng:

1. Marker ConfigMap đọc được với giá trị dự kiến.
2. Marker Secret đọc được với giá trị dự kiến.
3. Key trùng nhận giá trị từ ConfigMap.

Khi cần chẩn đoán sâu hơn, xem các PropertySource ứng viên có chứa key trùng. Marker chứng minh nguồn được nạp; ứng viên chứa giá trị khác nhau giúp phát hiện lỗi fixture hoặc nhầm key.

Manifest tương đương cho bài lab:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: precedence-demo
  namespace: precedence-test
data:
  demo.precedence.winner: "from-configmap"
  demo.probe.configmap-marker: "cm-loaded"
---
apiVersion: v1
kind: Secret
metadata:
  name: precedence-demo
  namespace: precedence-test
type: Opaque
stringData:
  demo.precedence.winner: "from-secret"
  demo.probe.secret-marker: "secret-loaded"
```

ConfigMap và Secret được phép cùng tên vì khác loại tài nguyên. Trong manifest, `stringData` thuận tiện cho dữ liệu tổng hợp. Phản hồi đọc Secret từ API thường sử dụng `data` với giá trị mã hóa base64; mock HTTP phải phản ánh dạng đọc này.

Không dùng cùng một chuỗi cho key trùng ở cả hai nguồn. Khi hai bên đều là `enabled`, test không thể chứng minh nguồn nào thắng.

## 4. Lập ma trận kiểm thử trước khi viết mã

Bắt đầu bằng các ca độc lập:

| Mã ca | Thiết lập key trùng | Kết quả mong đợi | Điều kiện bổ sung |
| --- | --- | --- | --- |
| P1 | Có ở cả ConfigMap và Secret | `from-configmap` | Cả hai marker tồn tại |
| P2 | Chỉ Secret có key, ConfigMap vẫn có marker | `from-secret` | ConfigMap vẫn được nạp |
| P3 | Cả hai không có key, vẫn có marker | `from-default` | Hai nguồn vẫn được nạp |
| P4 | P1 và command-line override | `from-cli` | Hai nguồn Kubernetes vẫn tồn tại |
| P5 | Tắt Secret có chủ đích | Marker Secret không có | Không dùng ca này để kết luận ưu tiên |
| P6 | ConfigMap có chuỗi rỗng tại key trùng | Kiểm tra rõ chính sách giá trị rỗng | Không tự coi chuỗi rỗng là key không tồn tại |
| P7 | API Secret trả 403 | Kết quả theo chính sách fail-fast | Không gọi đây là “Secret ưu tiên thấp” |

P1–P4 kiểm tra việc giải quyết giá trị. P5 là ca đối chứng cho cơ chế bật/tắt nguồn. P7 kiểm tra lỗi tải cấu hình. Chúng không thay thế nhau.

Với key chỉ có ở Secret, P2 xác nhận nguồn ưu tiên thấp hơn vẫn cung cấp những property không bị che. Ưu tiên được áp dụng theo key, không có nghĩa toàn bộ Secret bị loại bỏ khi có ConfigMap.

## 5. Chọn môi trường cho bài kiểm thử

Ví dụ chính dùng:

- Java 17 trở lên và JUnit Jupiter.
- Spring Boot với Config Data.
- `spring-cloud-starter-kubernetes-fabric8-config`.
- Fabric8 Kubernetes Mock Server ở CRUD mode.
- Một context Spring mới được mở và đóng trong từng test.

Tọa độ dependency tối thiểu, với phiên bản được BOM tương thích của dự án quản lý:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-fabric8-config</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>io.fabric8</groupId>
    <artifactId>kubernetes-server-mock</artifactId>
    <scope>test</scope>
</dependency>
```

Nếu BOM của dự án không quản lý artifact mock, khai báo phiên bản phù hợp với Fabric8 client được resolve thực tế. Không thêm một mock server mới hơn tùy ý rồi bỏ qua xung đột dependency.

Mã dùng các API Config Data và thuộc tính có trong nhánh Spring Cloud Kubernetes 3.3.x; khi áp dụng cho release khác, đối chiếu BOM, metadata cấu hình và tài liệu của release đó. Có thể xem [resolver Fabric8 3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-fabric8-config/src/main/java/org/springframework/cloud/kubernetes/fabric8/config/Fabric8ConfigDataLocationResolver.java) để hiểu việc client được tạo trong giai đoạn Config Data.

Nếu ứng dụng dùng Kubernetes Java Client, giữ nguyên ma trận và assertion nhưng thay mock/client đúng implementation. Không chuyển ứng dụng sang Fabric8 chỉ để chạy một ví dụ test.

## 6. Ví dụ tích hợp: khởi động Spring thật với fixture API

### 6.1. Vì sao không chỉ mock MapPropertySource?

Một test tự tạo hai map rồi dùng `addFirst(...)` chỉ kiểm tra thứ tự bạn vừa lập trình. Nó không xác minh loader Spring Cloud Kubernetes, giải mã Secret hoặc binding vào bean.

Ví dụ dưới đây seed tài nguyên vào API mock trước khi gọi `SpringApplication.run(...)`. Spring dùng starter thật để tải cấu hình. Không có `@SpringBootTest` nên không phụ thuộc context được khởi tạo trước phần thiết lập fixture.

Trong tiến trình test riêng, tắt autoconfiguration kubeconfig của Fabric8 bằng tùy chọn JVM `-Dkubernetes.disable.autoConfig=true`. URL mock và namespace vẫn được truyền tường minh. Đây là cấu hình dành cho runner kiểm thử, không phải thay đổi cấu hình triển khai của ứng dụng.

### 6.2. Lớp kiểm thử P1–P4

```java
package example.precedence;

import io.fabric8.kubernetes.api.model.ConfigMapBuilder;
import io.fabric8.kubernetes.api.model.SecretBuilder;
import io.fabric8.kubernetes.client.KubernetesClient;
import io.fabric8.kubernetes.client.server.mock.EnableKubernetesMockClient;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.Environment;
import org.springframework.core.env.StandardEnvironment;

import static org.junit.jupiter.api.Assertions.*;

@EnableKubernetesMockClient(https = false, crud = true)
class ConfigMapSecretPrecedenceTest {
    private static final String NAMESPACE = "precedence-test";
    private static final String NAME = "precedence-demo";
    private static final String KEY = "demo.precedence.winner";
    private static final String CM_MARKER =
        "demo.probe.configmap-marker";
    private static final String SECRET_MARKER =
        "demo.probe.secret-marker";

    KubernetesClient client;

    @Test
    void configMapWinsWhenBothSourcesProvideTheKey() {
        seed(
            Map.of(KEY, "from-configmap",
                CM_MARKER, "cm-loaded"),
            Map.of(KEY, "from-secret",
                SECRET_MARKER, "secret-loaded"));

        try (ConfigurableApplicationContext context = open(Map.of())) {
            assertBothSourcesLoaded(context.getEnvironment());
            assertWinner(context, "from-configmap");
        }
    }

    @Test
    void secretSuppliesTheKeyMissingFromConfigMap() {
        seed(
            Map.of(CM_MARKER, "cm-loaded"),
            Map.of(KEY, "from-secret",
                SECRET_MARKER, "secret-loaded"));

        try (ConfigurableApplicationContext context = open(Map.of())) {
            assertBothSourcesLoaded(context.getEnvironment());
            assertWinner(context, "from-secret");
        }
    }

    @Test
    void defaultAppliesWhenNeitherSourceProvidesTheKey() {
        seed(
            Map.of(CM_MARKER, "cm-loaded"),
            Map.of(SECRET_MARKER, "secret-loaded"));

        try (ConfigurableApplicationContext context = open(Map.of())) {
            assertBothSourcesLoaded(context.getEnvironment());
            assertWinner(context, "from-default");
        }
    }

    @Test
    void commandLineCanOverrideTheKubernetesValue() {
        seed(
            Map.of(KEY, "from-configmap",
                CM_MARKER, "cm-loaded"),
            Map.of(KEY, "from-secret",
                SECRET_MARKER, "secret-loaded"));

        try (ConfigurableApplicationContext context =
                open(Map.of(KEY, "from-cli"))) {
            assertBothSourcesLoaded(context.getEnvironment());
            assertWinner(context, "from-cli");
        }
    }

    private void seed(
            Map<String, String> configValues,
            Map<String, String> secretValues) {

        client.configMaps().inNamespace(NAMESPACE)
            .resource(new ConfigMapBuilder()
                .withNewMetadata()
                    .withName(NAME)
                    .withNamespace(NAMESPACE)
                .endMetadata()
                .withData(configValues)
                .build())
            .create();

        Map<String, String> encoded = new HashMap<>();
        secretValues.forEach((key, value) ->
            encoded.put(key, Base64.getEncoder().encodeToString(
                value.getBytes(StandardCharsets.UTF_8))));

        client.secrets().inNamespace(NAMESPACE)
            .resource(new SecretBuilder()
                .withNewMetadata()
                    .withName(NAME)
                    .withNamespace(NAMESPACE)
                .endMetadata()
                .withType("Opaque")
                .withData(encoded)
                .build())
            .create();
    }

    private ConfigurableApplicationContext open(
            Map<String, String> overrides) {

        StandardEnvironment environment = new StandardEnvironment();

        // Cô lập PropertySource của Spring khỏi giá trị máy chạy test.
        environment.getPropertySources().remove(
            StandardEnvironment.SYSTEM_ENVIRONMENT_PROPERTY_SOURCE_NAME);
        environment.getPropertySources().remove(
            StandardEnvironment.SYSTEM_PROPERTIES_PROPERTY_SOURCE_NAME);

        SpringApplication application =
            new SpringApplication(TestApplication.class);
        application.setEnvironment(environment);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setRegisterShutdownHook(false);
        application.setDefaultProperties(
            Map.of(KEY, "from-default"));

        Map<String, String> options = new LinkedHashMap<>();
        options.put("spring.application.name", NAME);
        options.put("spring.main.cloud-platform", "KUBERNETES");
        options.put("spring.cloud.bootstrap.enabled", "false");
        options.put("spring.profiles.active", "precedence-test");

        // Không nạp application.yaml mặc định của module hiện tại.
        options.put("spring.config.location",
            "optional:classpath:/precedence-no-default-config/");
        options.put("spring.config.import", "kubernetes:");

        options.put("spring.cloud.kubernetes.client.master-url",
            client.getConfiguration().getMasterUrl());
        options.put("spring.cloud.kubernetes.client.namespace",
            NAMESPACE);

        options.put("spring.cloud.kubernetes.config.enabled", "true");
        options.put("spring.cloud.kubernetes.config.name", NAME);
        options.put("spring.cloud.kubernetes.config.namespace",
            NAMESPACE);
        options.put(
            "spring.cloud.kubernetes.config.include-profile-specific-sources",
            "false");
        options.put("spring.cloud.kubernetes.config.use-name-as-prefix",
            "false");
        options.put("spring.cloud.kubernetes.config.fail-fast", "true");
        options.put("spring.cloud.kubernetes.config.retry.enabled",
            "false");

        options.put("spring.cloud.kubernetes.secrets.enabled", "true");
        options.put("spring.cloud.kubernetes.secrets.enable-api", "true");
        options.put("spring.cloud.kubernetes.secrets.name", NAME);
        options.put("spring.cloud.kubernetes.secrets.namespace",
            NAMESPACE);
        options.put(
            "spring.cloud.kubernetes.secrets.include-profile-specific-sources",
            "false");
        options.put("spring.cloud.kubernetes.secrets.use-name-as-prefix",
            "false");
        options.put("spring.cloud.kubernetes.secrets.fail-fast", "true");
        options.put("spring.cloud.kubernetes.secrets.retry.enabled",
            "false");

        options.put("spring.cloud.kubernetes.discovery.enabled", "false");
        options.putAll(overrides);

        List<String> arguments = new ArrayList<>();
        options.forEach((key, value) ->
            arguments.add("--" + key + "=" + value));

        return application.run(arguments.toArray(String[]::new));
    }

    private static void assertBothSourcesLoaded(
            Environment environment) {
        assertEquals("cm-loaded",
            environment.getRequiredProperty(CM_MARKER));
        assertEquals("secret-loaded",
            environment.getRequiredProperty(SECRET_MARKER));
    }

    private static void assertWinner(
            ConfigurableApplicationContext context,
            String expected) {
        assertEquals(expected,
            context.getEnvironment().getRequiredProperty(KEY));
        assertEquals(expected,
            context.getBean(PrecedenceProperties.class).winner());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableConfigurationProperties(PrecedenceProperties.class)
    static class TestApplication {
    }

    @ConfigurationProperties(prefix = "demo.precedence")
    public record PrecedenceProperties(String winner) {
    }
}
```

### 6.3. Những điều ví dụ chủ động kiểm soát

- API mock và fixture có trước thời điểm loader Config Data chạy.
- Mỗi ca có tài nguyên và context riêng theo vòng đời extension/test.
- Secret được bật cả tính năng lẫn việc đọc qua API.
- Namespace, tên tài nguyên và prefix được đặt rõ.
- Profile-specific source bị tắt để tránh đưa thêm nguồn vào P1.
- Chỉ P4 đặt key mục tiêu trên command line.
- Giá trị hiệu lực được kiểm tra ở Environment và bean `@ConfigurationProperties`.
- Context được đóng trước khi extension dừng mock.

Việc bỏ hai PropertySource hệ thống trong ví dụ nhằm cô lập logic Spring. Nó không có nghĩa mọi thư viện Java ngừng đọc trực tiếp system property hoặc môi trường; vì vậy runner Fabric8 vẫn cần được cấu hình riêng, tránh kubeconfig/proxy cá nhân.

Các option được ghép bằng Map rồi mới chuyển thành arguments. Điều này cho phép thay một tùy chọn mà không truyền trùng cùng tên command-line option.

Giá trị `from-default` trong ví dụ đến từ `SpringApplication.setDefaultProperties(...)`. Nó không đại diện cho mọi vị trí `application.yaml`. Muốn kiểm tra thứ tự giữa file khai báo import và dữ liệu import, hãy thêm một test dùng file cấu hình riêng cho đúng đường đi đó.

## 7. Quan sát nguồn ứng viên mà không khóa cứng tên nội bộ

Khi P1 thất bại, chỉ nhìn giá trị cuối cùng có thể chưa đủ. Bạn cần biết ConfigMap và Secret đã cung cấp key trùng chưa.

Có thể bổ sung helper sau vào lớp test để chỉ xem key tổng hợp của bài lab:

```java
record Candidate(String sourceName, Object value) {
}

static List<Candidate> candidates(
        ConfigurableEnvironment environment, String key) {
    List<Candidate> result = new ArrayList<>();
    for (org.springframework.core.env.PropertySource<?> source
            : environment.getPropertySources()) {
        collect(source, key, result);
    }
    return result;
}

static void collect(
        org.springframework.core.env.PropertySource<?> source,
        String key,
        List<Candidate> result) {
    if (source instanceof
            org.springframework.core.env.CompositePropertySource composite) {
        for (org.springframework.core.env.PropertySource<?> nested
                : composite.getPropertySources()) {
            collect(nested, key, result);
        }
        return;
    }

    // Adapter tổng hợp có thể ủy quyền về chính các nguồn bên dưới.
    if ("configurationProperties".equals(source.getName())) {
        return;
    }

    Object value = source.getProperty(key);
    if (value != null) {
        result.add(new Candidate(source.getName(), value));
    }
}
```

Ví dụ assertion bổ sung cho P1:

```java
List<Candidate> found =
    candidates(context.getEnvironment(), KEY);

assertTrue(found.stream()
    .anyMatch(candidate ->
        "from-configmap".equals(candidate.value())));
assertTrue(found.stream()
    .anyMatch(candidate ->
        "from-secret".equals(candidate.value())));
```

Đây là assertion về sự hiện diện của ứng viên, không thay thế assertion giá trị cuối cùng. Không phụ thuộc vào chỉ số cố định như “PropertySource thứ ba” hoặc tên chứa chính xác một chuỗi nội bộ của provider.

Helper này chỉ dành cho giá trị tổng hợp. Với cấu hình thật, chẩn đoán nên ghi tên nguồn và sự hiện diện của key, tránh ghi nội dung Secret vào log hay báo cáo thất bại.

## 8. Ngăn các override trong test làm che mất kết quả

Một lỗi phổ biến:

```java
@SpringBootTest(properties = {
    "demo.precedence.winner=from-configmap"
})
class MisleadingPrecedenceTest {
    // Assertion winner == from-configmap có thể đỗ
    // dù ConfigMap và Secret đều chưa được nạp.
}
```

Giá trị test đã quyết định kết quả trước khi bạn quan sát tương quan của hai nguồn Kubernetes. Tương tự, `@TestPropertySource` hoặc `@DynamicPropertySource` có thể che key mục tiêu.

Dùng thuộc tính test để đặt URL mock, namespace và cờ loader. Chỉ đặt key mục tiêu ở tầng override khi chính tầng đó là đối tượng của ca kiểm thử, như P4.

Đối với biến môi trường và system property, viết test riêng với môi trường/tiến trình được kiểm soát. Bộ test chính đã loại hai PropertySource đó nên không chứng minh các quy tắc của chúng. Xem [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) trước khi xây dựng assertion ưu tiên toàn cục.

Không mô phỏng một biến môi trường bằng cách đổi tên một MapPropertySource rồi kết luận relaxed binding của biến môi trường thật đã được kiểm tra.

## 9. Tăng dần độ phức tạp: format, profile và nhiều nguồn

Sau khi P1–P4 ổn định, mở rộng từng chiều:

| Chiều mở rộng | Fixture gợi ý | Điều cần giữ cố định |
| --- | --- | --- |
| File nhúng | `application.yaml` hoặc `application.properties` trong data | Không thêm key phẳng trùng ngoài ý muốn |
| Profile | Giá trị base và giá trị của một profile | Profile active được truyền rõ |
| Nhiều ConfigMap | Hai nguồn có thứ tự khai báo tường minh | Chưa thêm Secret trong bước đầu |
| Nhiều Secret | Nguồn có key trùng và marker riêng | Namespace và cách chọn nguồn |
| Prefix | Hai nguồn có prefix khác nhau | Key sau prefix được xác định trước |
| Nhiều namespace | Cùng tên tài nguyên, giá trị khác | Danh sách namespace mục tiêu |

Spring Cloud Kubernetes có quy tắc riêng khi xử lý dữ liệu phẳng, file nhúng, profile-specific source và danh sách source. Vì vậy, kết quả của một fixture đơn giản không tự chứng minh mọi tổ hợp này. Đối chiếu [ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html) khi tạo ma trận bổ sung.

Ví dụ fixture riêng cho kiểm thử file YAML nhúng:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: precedence-demo
  namespace: precedence-test
data:
  application.yaml: |-
    demo:
      precedence:
        winner: from-configmap-yaml
      probe:
        configmap-marker: cm-loaded
```

Secret tương ứng phải cung cấp nội dung cấu hình đúng định dạng sau giải mã. Đừng nhầm base64 của cả file YAML với từng giá trị property.

Nếu bật prefix khiến hai key trở thành `public.demo.precedence.winner` và `private.demo.precedence.winner`, chúng không còn là cùng một property. Test khi đó cần xác nhận cả hai tên hiệu lực thay vì gọi đó là xung đột giữa ConfigMap và Secret.

## 10. Phân biệt thiếu key, chuỗi rỗng và lỗi tải nguồn

### 10.1. Key không tồn tại

P2 bỏ key mục tiêu khỏi ConfigMap nhưng giữ marker ConfigMap. Nhờ vậy, kết quả từ Secret chứng minh fallback theo key; nó không dựa vào việc tắt toàn bộ ConfigMap.

P3 giữ marker ở cả hai nguồn rồi bỏ key mục tiêu ở cả hai. Đây là cách chứng minh default được dùng vì key không có, thay vì vì loader không hoạt động.

### 10.2. Chuỗi rỗng không phải key bị xóa

Nếu ConfigMap có `demo.precedence.winner: ""`, cần quan sát cả giá trị thô và giá trị bean. Không tự suy ra Secret được chọn chỉ vì giá trị ConfigMap không có nội dung.

Nếu ứng dụng yêu cầu chuỗi không rỗng, bổ sung validation phù hợp ở bean cấu hình và test kết quả khởi động thất bại. Đó là chính sách hợp lệ dữ liệu, tách với cơ chế tìm nguồn thắng.

### 10.3. HTTP 403 không phải ưu tiên thấp

Để kiểm tra 403, dùng expectation/dispatcher phù hợp với request GET/LIST mà provider thực sự gửi. Giữ các tài nguyên còn lại hợp lệ và đặt fail-fast/retry theo mục tiêu test.

Nếu context phải thất bại, assert việc khởi động thất bại và nguyên nhân trong chuỗi exception thay vì phụ thuộc toàn bộ thông báo lỗi. Nếu thiết kế cho phép bỏ qua nguồn không đọc được, kiểm tra hành vi đó có chủ đích.

API Secret không được đọc chỉ vì bạn đã tạo Secret. Cần bật cơ chế đọc tương ứng và cung cấp quyền trong môi trường thật. Xem [Secrets PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/secrets-propertysource.html).

## 11. Không dùng thời điểm apply để suy ra thứ tự ưu tiên

Một bài kiểm thử có thể tạo Secret trước rồi ConfigMap sau. Kết quả ConfigMap thắng không có nghĩa “tài nguyên tạo sau sẽ ghi đè”.

Thứ tự ưu tiên do cơ chế cấu hình quyết định, không phải thời gian tạo, `resourceVersion`, tuổi tài nguyên hay thứ tự in ra của `kubectl get`.

Có thể thêm một ca đối chứng đổi thứ tự seed hai tài nguyên nhưng giữ nguyên cấu hình loader và các giá trị. Kết quả giải quyết key vẫn cần tuân theo cùng quy tắc đã xác định.

Tương tự, gọi `get configmap` trước `get secret` trong mã kiểm tra không mô phỏng thứ tự PropertySource của Spring. Hãy để loader thật thực hiện đường nạp của nó.

## 12. Tách kiểm thử lúc khởi động khỏi kiểm thử cập nhật cấu hình

Bốn ca chính mở context mới cho từng fixture. Chúng chứng minh ưu tiên tại thời điểm khởi động.

Nếu ứng dụng dùng Configuration Watcher hoặc cơ chế refresh, cần kịch bản riêng:

1. Nạp cả hai nguồn, xác nhận ConfigMap đang thắng và Secret có marker.
2. Đổi giá trị key trùng chỉ trong Secret.
3. Chờ cơ chế cập nhật theo điều kiện có thời hạn.
4. Xác nhận giá trị hiệu lực vẫn do ConfigMap quyết định.
5. Bỏ key trùng khỏi ConfigMap theo cơ chế được hỗ trợ.
6. Xác nhận giá trị chuyển sang Secret sau refresh hoặc sau khởi động lại, đúng với thiết kế.

Không kết luận bước 5 luôn có hiệu lực trên bean đang chạy. Xóa property, rebind và refresh có giới hạn theo loại bean và cơ chế được dùng; test phải bao phủ hành vi ứng dụng thực tế. Nếu dự án cập nhật cấu hình bằng rollout, tạo Pod/context mới thay vì giả định refresh tồn tại.

Thông báo “đã nhận sự kiện ConfigMap” hoặc một POST refresh thành công chưa chứng minh bean phục vụ yêu cầu đã đổi giá trị.

Khi ConfigMap/Secret được tiêu thụ qua biến môi trường hoặc volume, viết test tương ứng cơ chế đó. Đừng dùng kết quả PropertySource qua API để suy ra tiến trình nhận biến môi trường mới hay kubelet đã đồng bộ file.

## 13. Phạm vi mock và kiểm tra trên Kubernetes thật

Mock API giúp kiểm tra loader, cấu trúc dữ liệu và thứ tự ưu tiên mà không cần một cluster hoàn chỉnh. Nó không xác nhận:

- ServiceAccount thật có quyền đọc ConfigMap/Secret.
- Role/RoleBinding đúng namespace và đúng verb.
- Admission hoặc chính sách bảo mật cho phép triển khai.
- Volume projection và độ trễ cập nhật trên Pod.
- Những khác biệt cấu hình giữa image thử nghiệm và image release.

Một smoke test trên namespace lab nên sử dụng đúng image, ServiceAccount và cơ chế nạp của triển khai. Tạo fixture không nhạy cảm, xác minh marker và giá trị qua hành vi ứng dụng hoặc endpoint nội bộ được thiết kế cho quan sát.

Không mở toàn bộ Actuator Environment hoặc công khai Secret chỉ để kiểm tra ưu tiên. Chỉ cần quan sát marker tổng hợp và nguồn quyết định trong phạm vi được phép.

Nếu ứng dụng không dùng DiscoveryClient, LoadBalancer hoặc Watcher trong đường nạp cấu hình này, không bật chúng chỉ để hoàn thành test. Giữ phạm vi vừa đủ để kiểm thử quy tắc đang xét.

## 14. Chẩn đoán khi kết quả khác dự kiến

| Dấu hiệu | Nguyên nhân cần kiểm tra trước |
| --- | --- |
| ConfigMap thắng nhưng marker Secret thiếu | Secret bị tắt, đọc API chưa bật, sai tên/namespace hoặc lỗi quyền |
| Cả hai marker thiếu | Import chưa chạy, thiếu starter, sai URL hoặc context khởi động trước fixture |
| Marker đủ nhưng giá trị là `from-default` | Sai key, prefix, format hoặc fixture không chứa key mục tiêu |
| Giá trị đến từ test/CLI | Key bị đặt tại nguồn ưu tiên cao hơn |
| Environment đúng nhưng bean khác | Prefix binding, conversion, bean cũ hoặc thời điểm khởi tạo |
| Đúng khi chạy riêng, sai khi chạy cả bộ | Context cache, tài nguyên chung, system property hoặc fixture rò giữa các test |
| Chỉ sai khi bật profile | Có nguồn profile hoặc file nhúng khác đang tham gia |
| 403 bị hiểu là “không có key” | Chính sách bỏ qua lỗi tải nguồn che mất nguyên nhân |
| Test treo hoặc chạy quá lâu | Retry, timeout, request nền hoặc tài nguyên chưa đóng |

Khi điều tra, ghi rõ provider, release, import mode, namespace, active profiles, tên nguồn và key tổng hợp. Không sửa kỳ vọng test theo giá trị hiện tại trước khi xác định nguồn nào đã tham gia.

Với tên PropertySource nội bộ thay đổi giữa các phiên bản, ưu tiên assertion về hành vi và sự hiện diện của dữ liệu hơn assertion toàn bộ tên chuỗi.

## 15. Bài tập và tiêu chí hoàn thành

Thực hiện trong module lab được cấu hình đúng dependency:

1. Chạy P1–P4 và ghi nhận cả giá trị Environment lẫn bean.
2. Tắt Secret có chủ đích rồi chứng minh assertion marker trong P1 phát hiện vấn đề.
3. Đổi thứ tự tạo hai tài nguyên; giải thích vì sao đó không phải cơ chế ưu tiên.
4. Thêm ca ConfigMap có chuỗi rỗng và xác định chính sách validation của ứng dụng.
5. Chuyển fixture sang YAML nhúng, sau đó thêm một profile có giá trị khác.
6. Viết một test phân biệt lỗi tải Secret với trường hợp Secret không có key.
7. Nêu một kiểm tra trên cluster thật mà mock không thay thế được.

Bộ kiểm thử hoàn thành mục tiêu khi chứng minh được **hai nguồn thực sự được nạp**, **giá trị nào thắng tại key trùng**, **key riêng vẫn tồn tại**, và **override ngoài Kubernetes được kiểm tra có chủ đích**.

Khi thay BOM, provider hoặc cơ chế từ bootstrap sang Config Data, chạy lại các ca hợp đồng này. Chúng giúp phát hiện thay đổi hành vi cấu hình trước khi nó ảnh hưởng đến các Pod đang triển khai.
