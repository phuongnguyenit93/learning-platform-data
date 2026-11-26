# Kiểm thử nạp cấu hình bắt buộc, tùy chọn và fail-fast

Một ứng dụng Spring có thể không nạp được cấu hình vì nguồn không tồn tại, thiếu quyền, mất kết nối hoặc dữ liệu không hợp lệ. Những tình huống này cần có kỳ vọng khác nhau. Nếu gom tất cả thành “không đọc được thì dùng mặc định”, ứng dụng có thể khởi động với một cấu hình mà đội triển khai chưa từng chấp thuận.

Bài học thuộc chương **Kiểm thử tự động** của module **SPRING_CLOUD_KUBERNETES**. Nội dung tập trung vào cách kiểm thử chính sách nạp ConfigMap, Secret và các nguồn cấu hình mà Spring sử dụng. Các phép thử được nối với RBAC, trạng thái khởi động của Pod và yêu cầu cập nhật cấu hình; DiscoveryClient, Spring Cloud LoadBalancer và Configuration Watcher chỉ tham gia khi kịch bản thực sự cần chúng.

Sau bài học, bạn có thể:

- Phân biệt nguồn bắt buộc, giá trị bắt buộc và tính năng có thể vắng mặt.
- Kiểm thử `optional:` trên đường nạp Config Data thực.
- Kiểm tra fail-fast mà không nhầm nguồn rỗng với lỗi truy cập API.
- Thiết kế ma trận test cho thiếu nguồn, HTTP 403, timeout và dữ liệu sai.
- Kiểm soát retry, thời gian chờ và bằng chứng quan sát khi chạy trên Kubernetes.

## 1. Viết chính sách trước khi viết test

Giả sử dịch vụ `catalog` có:

- Cấu hình định tuyến bắt buộc để biết service cần gọi.
- Một mã phiên bản cấu hình để nhận diện đầu vào.
- Cờ bật gợi ý sản phẩm, mặc định tắt nếu nguồn bổ sung chưa tồn tại.
- Credential bắt buộc nếu một chức năng cần xác thực được bật.

Câu “cấu hình là tùy chọn” chưa đủ rõ. Cần trả lời tùy chọn ở lớp nào:

| Lớp | Ví dụ | Điều cần xác định |
| --- | --- | --- |
| Nguồn Config Data | File được import có thể chưa tồn tại | Có bỏ qua lỗi không tìm thấy location/resource không? |
| Tài nguyên Kubernetes | ConfigMap hoặc Secret có thể chưa được tạo | Cơ chế đọc API/mount xử lý sự vắng mặt ra sao? |
| Giá trị ứng dụng | `service-id` không được thiếu | Giá trị mặc định hoặc validation nào áp dụng? |
| Tính năng | Gợi ý sản phẩm có thể tắt | Khi nguồn vắng, hành vi fallback nào được chấp nhận? |

Một nguồn tùy chọn vẫn có thể chứa dữ liệu không hợp lệ khi nó xuất hiện. Một nguồn bắt buộc vẫn có thể tồn tại nhưng thiếu khóa nghiệp vụ cần thiết.

Vì vậy, mỗi kịch bản test nên ghi:

~~~text
Đường nạp: file import / Kubernetes API / volume / biến môi trường
Đầu vào: tồn tại, thiếu, bị từ chối, timeout hoặc sai dữ liệu
Chính sách: cho phép fallback hay dừng khởi động
Kết quả mong đợi: trạng thái ứng dụng và giá trị thực sự được dùng
Bằng chứng: exception/cause, yêu cầu API, bean cấu hình hoặc trạng thái container
~~~

Không coi “test không ném exception” là đủ nếu chưa biết ứng dụng đã dùng cấu hình nào.

## 2. Phân biệt optional, fail-fast và validation

Luồng khởi động có thể được mô tả:

~~~mermaid
flowchart TD
    A["Bắt đầu nạp nguồn"] --> B{"Đường nạp tìm thấy nguồn?"}
    B -->|Không| C["Xử lý theo hợp đồng của loader và nguồn"]
    B -->|Có| D["Đọc và parse dữ liệu"]
    C --> E{"Được phép tiếp tục?"}
    E -->|Không| F["Khởi động thất bại"]
    E -->|Có| G["Tập thuộc tính còn lại và fallback"]
    D --> H{"Đọc/parse thành công?"}
    H -->|Không| I["Chính sách lỗi, fail-fast và retry"]
    I --> E
    H -->|Có| G
    G --> J["Binding và validation"]
    J --> K{"Dữ liệu ứng dụng hợp lệ?"}
    K -->|Không| F
    K -->|Có| L["Ứng dụng khởi động với cấu hình đã xác định"]
~~~

### 2.1. `optional:` thuộc hợp đồng Config Data

Với nguồn file của Spring Boot:

~~~yaml
spring:
  config:
    import: "optional:file:/etc/catalog/extra.properties"
~~~

Tiền tố `optional:` cho phép tiếp tục khi location/resource tương ứng không tìm thấy. Nó không có nghĩa mọi exception đều bị bỏ qua, cũng không bảo đảm bean cấu hình sẽ hợp lệ sau đó.

Ví dụ:

- File tùy chọn vắng, các giá trị bắt buộc đã có ở nguồn khác: có thể khởi động.
- File tùy chọn vắng, giá trị bắt buộc không còn nguồn nào cấp: validation vẫn có thể làm khởi động thất bại.
- File tồn tại nhưng YAML lỗi hoặc một giá trị không chuyển kiểu được: phải kiểm tra lỗi tương ứng.

Đây là phạm vi của [Spring Boot — Optional Locations](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html#features.external-config.files.optional). Khi dùng loader của hệ thống bên ngoài, phải kiểm tra thêm cách loader đó biểu diễn lỗi; không suy mọi lỗi mạng đều là “not found”.

### 2.2. Fail-fast của Spring Cloud Kubernetes

Các thuộc tính chính sách riêng cho hai loại nguồn là:

~~~properties
spring.cloud.kubernetes.config.fail-fast=true
spring.cloud.kubernetes.secrets.fail-fast=true
~~~

Chúng điều khiển cách xử lý lỗi khi đọc nguồn tương ứng qua cơ chế của Spring Cloud Kubernetes. Không nhầm với `spring.cloud.config.fail-fast`, vốn thuộc Spring Cloud Config.

Fail-fast cũng không đồng nghĩa “không bao giờ thử lại”. Nếu retry được cấu hình và kích hoạt, việc dừng có thể diễn ra sau các lần thử được phép. Tài liệu [ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config/configmap-propertysource.html) mô tả các thuộc tính fail-fast và retry liên quan.

### 2.3. Validation kiểm tra dữ liệu cuối cùng

Ví dụ `@NotBlank` trên `serviceId` yêu cầu bean không được nhận chuỗi thiếu hoặc trắng. Nó không xác nhận giá trị đó đến từ ConfigMap nào.

Nếu máy CI vô tình cấp một `service-id` hợp lệ qua biến môi trường, validation có thể vượt qua dù nguồn dự định dùng chưa được nạp. Test cần kiểm tra giá trị marker riêng và cô lập nguồn ngoài khi muốn xác nhận đường nạp.

## 3. Chuẩn bị bộ test theo từng lớp

Các ví dụ Spring Boot bên dưới dùng **Java 17 trở lên, Spring Boot 3.5.x, JUnit Jupiter và AssertJ**. Phần kiểm thử core của Spring Cloud Kubernetes tham chiếu cụ thể **mã nguồn v3.3.0** để làm rõ hành vi và API được dùng trong ví dụ.

Dự án thực tế cần chốt bộ phiên bản Spring Boot/Spring Cloud/Spring Cloud Kubernetes tương thích. Những test chạm API hỗ trợ nội bộ của thư viện cần được xem lại khi nâng cấp; không coi hành vi của một tag là cam kết cho mọi bản sau.

Các dependency cơ bản trong dự án đã có dependency management của Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Chia bằng chứng thành ba lớp:

| Lớp test | Có thực hiện | Chưa chứng minh |
| --- | --- | --- |
| Spring Boot Config Data | Nạp file thật trong thư mục tạm, khởi động và bind bean | Kubernetes API, RBAC |
| Core nạp nguồn của Spring Cloud Kubernetes | Chạy mã xử lý named source với supplier được điều khiển | HTTP client, danh tính ServiceAccount, đường bootstrap đầy đủ |
| Tích hợp API hoặc cluster | Chạy client/loader thực với tình huống API xác định | Hành vi mọi môi trường nếu chưa có bằng chứng tương ứng |

Để kiểm thử quá trình import, ví dụ dùng `SpringApplication` thay vì chỉ đưa thuộc tính trực tiếp vào một context nhỏ. [SpringApplication](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html) đi qua quá trình chuẩn bị môi trường của Spring Boot, nơi Config Data được xử lý.

## 4. Mô hình cấu hình ứng dụng để quan sát kết quả

~~~java
package com.example.catalog.config;

import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "catalog.runtime")
public record CatalogRuntimeProperties(
    @NotBlank
    String serviceId,

    @NotBlank
    String configRevision,

    @DefaultValue("false")
    boolean recommendationsEnabled
) {
}
~~~

Trong ví dụ:

- `service-id` và `config-revision` là giá trị bắt buộc.
- `recommendations-enabled` có fallback xác định là `false`.
- `config-revision` là marker không nhạy cảm để kiểm tra nguồn có được nạp và ghi đè hay không.
- Các khóa `catalog.runtime.*` do ứng dụng định nghĩa; chúng chưa tự cấu hình client discovery hoặc load balancing.

Marker giúp quan sát nhưng chưa tự xác thực nguồn. Nếu có nhiều nguồn có thể cấp cùng marker, test vẫn phải kiểm soát nguồn và thứ tự ưu tiên.

## 5. Test nguồn file bắt buộc và tùy chọn qua Config Data thực

Bộ test dưới đây tạo file fixture bằng `@TempDir`. Mỗi kịch bản nạp một base file được chỉ định rõ, không dựa vào `application.yaml` của thư mục đang chạy.

~~~java
package com.example.catalog.config;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.yaml.snakeyaml.error.YAMLException;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.config.ConfigDataNotFoundException;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.context.properties.bind.BindException;
import org.springframework.boot.context.properties.bind.validation.BindValidationException;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.StandardEnvironment;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ConfigDataLoadingPolicyTest {

    @TempDir
    Path directory;

    private static final String LOCAL_VALID = """
        catalog.runtime.service-id=catalog
        catalog.runtime.config-revision=local-001
        """;

    private static final String LOCAL_WITHOUT_REVISION = """
        catalog.runtime.service-id=catalog
        """;

    @Test
    void requiredSourceIsLoaded() throws IOException {
        Path remote = writeFixture("required.properties", """
            catalog.runtime.config-revision=required-002
            """);

        try (var context = start(
                remote.toUri().toString(),
                LOCAL_WITHOUT_REVISION)) {
            var properties =
                context.getBean(CatalogRuntimeProperties.class);

            assertThat(properties.serviceId()).isEqualTo("catalog");
            assertThat(properties.configRevision())
                .isEqualTo("required-002");
            assertThat(properties.recommendationsEnabled()).isFalse();
        }
    }

    @Test
    void requiredMissingSourceFailsEvenWhenLocalValuesAreValid() {
        String missing = directory.resolve("missing.properties")
            .toUri().toString();

        assertThatThrownBy(() -> startAndClose(missing, LOCAL_VALID))
            .satisfies(failure ->
                assertThat(findCause(
                    failure, ConfigDataNotFoundException.class))
                    .isNotNull());
    }

    @Test
    void optionalMissingSourceUsesApprovedFallback() throws IOException {
        String missing = directory.resolve("missing.properties")
            .toUri().toString();

        try (var context = start(
                "optional:" + missing,
                LOCAL_VALID)) {
            var properties =
                context.getBean(CatalogRuntimeProperties.class);

            assertThat(properties.serviceId()).isEqualTo("catalog");
            assertThat(properties.configRevision())
                .isEqualTo("local-001");
            assertThat(properties.recommendationsEnabled()).isFalse();
        }
    }

    @Test
    void optionalPresentSourceIsStillLoaded() throws IOException {
        Path extra = writeFixture("extra.properties", """
            catalog.runtime.config-revision=optional-003
            catalog.runtime.recommendations-enabled=true
            """);

        try (var context = start(
                "optional:" + extra.toUri(),
                LOCAL_VALID)) {
            var properties =
                context.getBean(CatalogRuntimeProperties.class);

            assertThat(properties.configRevision())
                .isEqualTo("optional-003");
            assertThat(properties.recommendationsEnabled()).isTrue();
        }
    }

    @Test
    void optionalMissingSourceDoesNotBypassRequiredValueValidation() {
        String missing = directory.resolve("missing.properties")
            .toUri().toString();

        assertThatThrownBy(() -> startAndClose(
                "optional:" + missing,
                LOCAL_WITHOUT_REVISION))
            .satisfies(failure ->
                assertThat(findCause(
                    failure, BindValidationException.class))
                    .isNotNull());
    }

    @Test
    void optionalPresentSourceWithInvalidValueFails() throws IOException {
        Path invalid = writeFixture("invalid.properties", """
            catalog.runtime.recommendations-enabled=not-a-boolean
            """);

        assertThatThrownBy(() -> startAndClose(
                "optional:" + invalid.toUri(),
                LOCAL_VALID))
            .satisfies(failure ->
                assertThat(findCause(failure, BindException.class))
                    .isNotNull());
    }

    @Test
    void optionalPresentSourceWithMalformedYamlFails() throws IOException {
        Path invalidYaml = writeFixture(
            "invalid.yaml", "catalog: [\n");

        assertThatThrownBy(() -> startAndClose(
                "optional:" + invalidYaml.toUri(),
                LOCAL_VALID))
            .satisfies(failure ->
                assertThat(findCause(failure, YAMLException.class))
                    .isNotNull());
    }

    private ConfigurableApplicationContext start(
            String importLocation, String localValues)
            throws IOException {
        Path base = writeFixture(
            "base.properties",
            "spring.config.import=" + importLocation + "\n"
                + localValues);

        var environment = new StandardEnvironment();
        environment.getPropertySources().remove(
            StandardEnvironment.SYSTEM_ENVIRONMENT_PROPERTY_SOURCE_NAME);
        environment.getPropertySources().remove(
            StandardEnvironment.SYSTEM_PROPERTIES_PROPERTY_SOURCE_NAME);

        var application = new SpringApplication(TestConfiguration.class);
        application.setEnvironment(environment);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);
        application.setRegisterShutdownHook(false);

        return application.run(
            "--spring.config.location=" + base.toUri(),
            "--spring.main.cloud-platform=none",
            "--spring.cloud.bootstrap.enabled=false",
            "--spring.cloud.kubernetes.enabled=false");
    }

    private void startAndClose(
            String importLocation, String localValues)
            throws IOException {
        try (var context = start(importLocation, localValues)) {
            // Close the context even if a negative case unexpectedly starts.
        }
    }

    private Path writeFixture(String name, String content)
            throws IOException {
        return Files.writeString(
            directory.resolve(name),
            content,
            StandardCharsets.UTF_8);
    }

    private static <T extends Throwable> T findCause(
            Throwable failure, Class<T> expectedType) {
        for (Throwable current = failure;
                current != null;
                current = current.getCause()) {
            if (expectedType.isInstance(current)) {
                return expectedType.cast(current);
            }
        }
        return null;
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(CatalogRuntimeProperties.class)
    @ImportAutoConfiguration(ValidationAutoConfiguration.class)
    static class TestConfiguration {
    }
}
~~~

### 5.1. Vì sao test bắt buộc vẫn cấp local hợp lệ?

Test `requiredMissingSourceFailsEvenWhenLocalValuesAreValid` cố ý cấp đủ giá trị nghiệp vụ ở local. Kỳ vọng vẫn là thất bại vì location được import là bắt buộc.

Nhờ đó, test kiểm tra đúng hợp đồng nạp nguồn, thay vì chỉ thất bại tình cờ do thiếu một trường sau khi loader đã bỏ qua nguồn.

Với nguồn file, [ConfigDataNotFoundException](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/config/ConfigDataNotFoundException.html) là kiểu cha của các lỗi không tìm thấy location hoặc resource. Dùng kiểu cha ở đây tránh gắn test vào một lớp con không cần thiết.

### 5.2. Vì sao cần cả optional vắng và optional hiện diện?

Nếu chỉ thử nguồn tùy chọn vắng, một loader chưa bao giờ đọc nguồn đó cũng có thể cho kết quả test tương tự.

Test optional hiện diện kiểm tra marker và cờ tính năng đã thay đổi. Hai test dữ liệu sai xác nhận `optional:` không bị hiểu thành “bỏ qua mọi lỗi khi nguồn xuất hiện”.

Test malformed YAML có mục tiêu khác test binding: parser chưa đọc được tài liệu thì chưa đến bước chuyển một giá trị sang boolean.

### 5.3. Cô lập test khỏi môi trường cá nhân

Helper loại system properties và biến môi trường khỏi `Environment` của application test, không sửa dữ liệu toàn cục của tiến trình. Nó dùng base file tuyệt đối trong thư mục tạm và không mở web server.

Các cờ tắt Kubernetes trong helper chỉ dành cho nhóm test nguồn file. Không dùng cùng helper với cờ đó để rồi kết luận đường `kubernetes:` đã được kiểm thử.

Đối với dự án có thêm environment post-processor hoặc listener riêng, tiếp tục kiểm soát những thành phần đó. Tránh để test chính sách file vô tình đọc kubeconfig hoặc gọi API bên ngoài.

## 6. Không tìm thấy ConfigMap chưa chắc là lỗi fail-fast

Không nên chuyển nguyên kỳ vọng của nguồn `file:` sang `kubernetes:`.

Trong mã Spring Cloud Kubernetes **v3.3.0**, `NamedSourceData.compute(...)` trả nguồn rỗng nếu supplier không tìm thấy tên nguồn nào. Nhánh này không ném exception chỉ vì `failFast=true`. Khi supplier phát sinh exception, `ConfigUtils.onException(...)` mới quyết định ném lỗi tiếp hay ghi nhận để bỏ qua.

Bạn có thể xem trực tiếp [NamedSourceData v3.3.0](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.0/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/config/NamedSourceData.java) và [ConfigUtils v3.3.0](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.0/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/config/ConfigUtils.java).

Hệ quả cho thiết kế test:

- Cần có một case “API trả thành công nhưng không có ConfigMap tên đã yêu cầu”.
- Cần một case riêng “đọc API phát sinh lỗi”.
- Không dùng `fail-fast=true` như bằng chứng duy nhất rằng mọi tài nguyên có tên trong cấu hình bắt buộc phải tồn tại.
- Nếu giá trị là bắt buộc với ứng dụng, bổ sung validation và tránh fallback vô tình che việc thiếu nguồn.
- Nếu yêu cầu là bắt buộc đúng tài nguyên nguồn, cần kiểm tra sự hiện diện/nguồn gốc theo thiết kế, không chỉ kiểm tra một chuỗi cuối cùng khác rỗng.

Đây là hành vi được chỉ ra cho tag tham chiếu. Khi nâng phiên bản hoặc đổi giữa Fabric8 và Kubernetes Java Client, chạy lại test đặc tả hành vi trên đường dùng thật.

### 6.1. Test xử lý nguồn bằng mã core của thư viện

Nhóm test dưới đây cần `spring-cloud-kubernetes-commons` trong test classpath, với version được chốt theo bộ dependency của dự án. Có thể đã có artifact này qua starter config; không thêm một bản khác xung đột với dependency đang dùng.

Ví dụ dùng API của v3.3.0:

~~~java
package com.example.catalog.config;

import java.util.LinkedHashSet;

import org.junit.jupiter.api.Test;

import org.springframework.cloud.kubernetes.commons.config.ConfigUtils;
import org.springframework.cloud.kubernetes.commons.config.MultipleSourcesContainer;
import org.springframework.cloud.kubernetes.commons.config.NamedSourceData;
import org.springframework.cloud.kubernetes.commons.config.SourceData;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class NamedSourceFailurePolicyTest {

    @Test
    void failFastPropagatesSupplierFailure() {
        var apiFailure =
            new IllegalArgumentException("simulated source read failure");

        NamedSourceData source = failingSource(apiFailure);

        assertThatThrownBy(() -> read(source, true))
            .isInstanceOf(IllegalStateException.class)
            .hasCause(apiFailure);
    }

    @Test
    void nonFailFastDoesNotProduceUsableBusinessConfiguration() {
        var apiFailure =
            new IllegalArgumentException("simulated source read failure");

        SourceData result = read(failingSource(apiFailure), false);

        assertThat(result).isNotNull();
        assertThat(result.sourceData())
            .doesNotContainKey("catalog.runtime.config-revision");
    }

    @Test
    void emptyLookupResultDoesNotThrowEvenWithFailFast() {
        NamedSourceData source = new NamedSourceData() {
            @Override
            public MultipleSourcesContainer dataSupplier(
                    LinkedHashSet<String> sourceNames) {
                return MultipleSourcesContainer.empty();
            }
        };

        SourceData result = read(source, true);

        assertThat(result.sourceData()).isEmpty();
    }

    private static NamedSourceData failingSource(
            RuntimeException failure) {
        return new NamedSourceData() {
            @Override
            public MultipleSourcesContainer dataSupplier(
                    LinkedHashSet<String> sourceNames) {
                throw failure;
            }
        };
    }

    private static SourceData read(
            NamedSourceData source, boolean failFast) {
        return source.compute(
            "catalog-required",
            ConfigUtils.Prefix.DEFAULT,
            "configmap",
            false,
            failFast,
            "config-policy-test",
            new String[0]);
    }
}
~~~

Những test này thực thi phần xử lý named source của Spring Cloud Kubernetes với supplier được điều khiển. Chúng không tự viết lại thuật toán fail-fast trong một hàm giả của ứng dụng.

Tuy nhiên, supplier giả chưa phải HTTP client. Exception mô phỏng không chứng minh việc chuyển HTTP 403 hay timeout thành exception trên client thực. Test không fail-fast cũng chưa khởi động application context; nó chỉ xác nhận đường xử lý này không cung cấp khóa nghiệp vụ mong đợi khi lỗi đọc xảy ra.

Đối với source rỗng, test thứ ba thể hiện rõ lý do cần tách “không tìm thấy nguồn” khỏi “lỗi đọc nguồn”. Không đổi assertion thành “phải ném lỗi” chỉ dựa vào tên fail-fast.

### 6.2. Không suy `optional:kubernetes:` là chính sách bỏ mọi lỗi

Spring Cloud Kubernetes có Config Data loader riêng. Ở tag tham chiếu, [KubernetesConfigDataLoader](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.0/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/config/KubernetesConfigDataLoader.java) gọi các property source locator để lấy dữ liệu.

Tiền tố optional ở location không tự biến mọi exception từ locator thành `ConfigDataNotFoundException`. Một lỗi ném ra do fail-fast và một nguồn không tìm thấy có thể đi qua các nhánh khác nhau.

Vì vậy, với cặp chính sách `optional:kubernetes:` và `fail-fast=true`, cần chạy case lỗi API trên đúng version/client rồi kiểm tra cause và kết quả. Không gán kỳ vọng “optional luôn thắng” hoặc “fail-fast luôn xác nhận nguồn tồn tại” mà chưa có phép thử tương ứng.

## 7. Kiểm thử đường nạp Kubernetes thực

### 7.1. Cấu hình đầu vào của một nhóm test ConfigMap

Cấu hình minh họa cho test tích hợp chỉ đọc ConfigMap:

~~~yaml
spring:
  application:
    name: catalog
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      config:
        enabled: true
        name: catalog-required
        namespace: config-policy-test
        include-profile-specific-sources: false
        fail-fast: true
        retry:
          enabled: false
      secrets:
        enabled: false
      discovery:
        enabled: false
~~~

Các tham số chọn nguồn và chính sách lỗi cần có trước lúc loader đọc nguồn: đặt trong cấu hình khởi động, biến môi trường hoặc tham số được quản lý phù hợp. Chỉ đặt `fail-fast` trong chính ConfigMap đang không đọc được không thể thay thế việc cấp chính sách từ trước.

Ví dụ này cố ý:

- Chỉ định namespace và tên nguồn.
- Tắt nguồn theo profile để giảm những lần tìm kiếm ngoài kịch bản.
- Tắt Secret và discovery trong nhóm test đang tập trung ConfigMap.
- Tắt retry để quan sát một lỗi đọc mà không cộng thêm vòng thử lại.

Nếu chạy test API ngoài cluster, bảo đảm điều kiện lựa chọn loader Kubernetes thực sự được thỏa mãn. Với môi trường mock đã kiểm soát, có thể cần đặt cloud platform Kubernetes theo cơ chế phiên bản đó; việc này chỉ chọn đường xử lý, không tự tạo kết nối hoặc quyền Kubernetes.

Sử dụng Config Data hoặc legacy bootstrap theo một cách rõ ràng. Tài liệu [Kubernetes PropertySource implementations](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config.html) lưu ý không trộn hai cơ chế tải nguồn này.

### 7.2. Ma trận cho API stub hoặc cluster thử nghiệm

| Mã case | Đầu vào | Kỳ vọng cần kiểm tra |
| --- | --- | --- |
| K1 | Nguồn tồn tại, dữ liệu đúng | Khởi động thành công; bean có marker riêng của nguồn |
| K2 | API thành công, nguồn được chọn không có | Ghi nhận hành vi loader; giá trị bắt buộc còn thiếu phải bị từ chối theo hợp đồng ứng dụng |
| K3 | Nguồn tồn tại nhưng thiếu khóa bắt buộc | Không nhầm “tìm thấy tài nguyên” với cấu hình đủ dữ liệu |
| K4 | API trả 403, fail-fast bật, retry tắt | Không hoàn tất khởi động; cause xác nhận lỗi phân quyền |
| K5 | Cùng lỗi 403, fail-fast tắt, fallback hợp lệ | Có thể tiếp tục theo đường được hỗ trợ; xác nhận đúng fallback và dấu hiệu nguồn lỗi |
| K6 | Fail-fast tắt nhưng không có dữ liệu bắt buộc | Validation vẫn từ chối; không gán lỗi này cho fail-fast |
| K7 | API không đáp ứng trong thời gian cho phép | Lỗi có giới hạn thời gian; nguyên nhân không bị báo nhầm là thiếu ConfigMap |
| K8 | HTTP 5xx rồi phục hồi trong ngân sách retry | Số lần thử và marker cuối cùng đúng theo kịch bản |
| K9 | Import optional kết hợp lỗi API | Kết quả được kiểm tra theo đúng cặp optional/fail-fast và implementation đang dùng |
| K10 | Nguồn optional có dữ liệu sai | Không tiếp tục với dữ liệu không hợp lệ ngoài chính sách được định nghĩa |

K5 phải có dữ liệu local hợp lệ vì mục tiêu là quan sát chính sách đọc nguồn, không để validation vô tình chặn trước khi phân biệt được kết quả. K6 cố ý bỏ fallback bắt buộc để kiểm tra lớp bảo vệ phía sau.

Để kiểm tra “nguồn bắt buộc đúng tên đã được nạp”, dùng marker chỉ có trong fixture nguồn đó và kiểm tra thêm dấu vết truy vấn. Nếu chính sách yêu cầu chứng minh nguồn gốc, marker đơn thuần vẫn cần được nối với metadata của nguồn và cơ chế quan sát phù hợp.

### 7.3. Stub đúng endpoint mà client thực sử dụng

Một test có thể cấu hình stub `GET /.../configmaps/catalog-required` nhưng client đang `LIST` các ConfigMap trong namespace rồi lọc tên. Khi đó, stub chưa tác động đến đường đi cần kiểm tra.

Ở đường Fabric8 của tag v3.3.0 tham chiếu, [Fabric8ConfigMapsCache](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.0/spring-cloud-kubernetes-fabric8-config/src/main/java/org/springframework/cloud/kubernetes/fabric8/config/Fabric8ConfigMapsCache.java) đọc danh sách ConfigMap theo namespace. API stub cần xử lý request thực mà client gửi.

Khi triển khai test:

1. Cố định namespace, profile và danh tính thử.
2. Trỏ client vào API thử nghiệm bằng cấu hình được hỗ trợ ở phiên bản đó.
3. Kiểm soát các lần discovery hoặc truy vấn phụ nếu client thực hiện chúng.
4. Ghi lại method/path/status của request liên quan.
5. Xác nhận request đọc cấu hình thực sự đã xảy ra.
6. Kiểm tra trạng thái khởi động và giá trị bean hoặc cause lỗi.
7. Dọn client, server và cache/tài nguyên test theo vòng đời của bộ fixture.

Đối với list thành công nhưng không có đối tượng được chọn, trả một danh sách hợp lệ thiếu tên nguồn tương ứng. Đừng dùng HTTP 404 để đại diện cho mọi trường hợp thiếu một object nếu client không gọi endpoint lấy riêng object đó.

API stub mô phỏng phản hồi 403 có thể kiểm tra xử lý lỗi của client/loader. Nó chưa chứng minh RoleBinding thật trên cluster đã từ chối đúng ServiceAccount.

## 8. Kiểm tra RBAC và Secret ở lớp phù hợp

### 8.1. Quyền đọc cấu hình phải thuộc đúng danh tính

Tách hai tài khoản thử:

- ServiceAccount được cấp quyền đọc cấu hình cần thiết trong namespace test.
- ServiceAccount không có quyền đọc cấu hình đó, để tạo case từ chối thật.

Không chạy application bằng kubeconfig quản trị rồi dùng kết quả đó để kết luận ServiceAccount có quyền.

Quyền phải phù hợp request thực. Với client đọc bằng danh sách ở ví dụ Fabric8 tham chiếu, cấp mỗi `get` theo một `resourceNames` cụ thể chưa đáp ứng request `list` namespace. Khi đổi implementation hoặc chế độ đọc ở phiên bản khác, kiểm tra lại hợp đồng quyền thay vì sao chép Role cũ.

Role/RoleBinding và danh tính chịu kiểm tra được mô tả trong [Kubernetes — Using RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

### 8.2. Secret có chính sách và đường cấp dữ liệu riêng

Test Secret cần xem các thuộc tính `spring.cloud.kubernetes.secrets.*`, không chỉ bật fail-fast của ConfigMap.

Đối với đọc Secret qua API, xác nhận tính năng đọc API thực sự đã bật và danh tính được cấp quyền tương ứng. Chỉ đặt `secrets.fail-fast=true` chưa chứng minh ứng dụng đã cố đọc Secret. Xem [Spring Cloud Kubernetes — Secrets PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config/secrets-propertysource.html).

Nếu Secret được cấp qua volume hoặc biến môi trường, test đường đó riêng. Dữ liệu fixture phải là giá trị giả; không dùng credential thật để kiểm tra thông báo validation hoặc log.

Với dữ liệu bắt buộc:

- Thiếu cả Secret là một case.
- Secret có nhưng thiếu key là một case khác.
- Key có nhưng dữ liệu không hợp lệ là case thứ ba.
- Credential đúng định dạng nhưng bị dịch vụ đích từ chối thuộc test tích hợp với dịch vụ đó.

Kết quả test cần tránh hiển thị giá trị Secret trong assertion, property source hoặc exception được thu thập làm artifact.

## 9. Optional ở manifest Kubernetes là một cơ chế khác

Ví dụ tham chiếu biến môi trường từ ConfigMap:

~~~yaml
env:
  - name: CATALOG_RUNTIME_SERVICEID
    valueFrom:
      configMapKeyRef:
        name: catalog-required
        key: service-id
        optional: false
~~~

Ví dụ nguồn volume được khai báo có thể vắng:

~~~yaml
volumes:
  - name: extra-config
    configMap:
      name: catalog-extra
      optional: true
~~~

Hai thuộc tính `optional` trên thuộc về việc Kubernetes chuẩn bị container/volume. Chúng không phải `optional:` của Spring Boot hoặc `fail-fast` của Spring Cloud Kubernetes.

Khi thiếu một tham chiếu không optional, container có thể chưa được tạo hoặc chưa khởi động ứng dụng. Trường hợp đó không có exception fail-fast từ JVM vì Spring chưa chạy.

Với nguồn volume optional, ứng dụng vẫn phải có chính sách cho file hoặc khóa vắng. Kubernetes cho phép thiếu nguồn chưa đồng nghĩa các `@ConfigurationProperties` của ứng dụng đã có giá trị hợp lệ.

Hành vi tham chiếu nguồn được mô tả trong [Kubernetes — Configure a Pod to Use a ConfigMap](https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/) và [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/).

Khi đọc kết quả một test triển khai, phân biệt:

| Quan sát | Lớp cần điều tra trước |
| --- | --- |
| Container waiting vì không có ConfigMap/Secret/key | Kubelet và tham chiếu trong Pod spec |
| JVM đã chạy rồi thoát vì lỗi nguồn cấu hình | Đường bootstrap/load của Spring |
| Nguồn đọc được nhưng validation từ chối | Hợp đồng dữ liệu ứng dụng |
| Ứng dụng chạy nhưng chưa Ready | Readiness và điều kiện phục vụ thực tế |

Không cho case “mong fail-fast” vượt qua chỉ vì Pod không Ready do image không pull được.

## 10. Retry có giới hạn và ngân sách thời gian

Trước tiên, test fail-fast với retry tắt để nhận diện lỗi gốc. Sau đó mới thêm nhóm test retry:

- API lỗi một số lần rồi trả dữ liệu hợp lệ.
- API tiếp tục lỗi đến khi hết lượt.
- API chậm hoặc timeout.
- Lỗi xác định không có khả năng tự phục hồi, chẳng hạn quyền 403 chưa được sửa.

Ngân sách khởi động có thể ước lượng:

~~~text
Thời gian nạp cấu hình
    ≈ tổng thời gian các request
      + tổng thời gian backoff
      + thời gian xử lý và khởi tạo còn lại
~~~

Đặt timeout cho từng request, giới hạn retry và deadline cho test. Một deadline chỉ bao quanh bước chờ Pod không thay thế timeout của client; ứng dụng có thể vẫn bị mắc ở một request đang chờ.

Với API stub, số request toàn bộ có thể gồm truy vấn phụ hoặc lần gọi theo profile. Đếm chính xác loại request đang kiểm tra, không mặc định tổng request của server bằng số lần retry của một nguồn.

Khi chạy trên Kubernetes, startup/liveness probe phải phù hợp ngân sách được thiết kế. Nếu probe làm chết container trước khi loader hoàn tất chu kỳ thử hợp lệ, test đang quan sát việc bị giết bởi probe, không phải kết quả hết retry của loader.

“Fail-fast” cần được diễn đạt thành kỳ vọng quan sát được, chẳng hạn không hoàn tất khởi động sau lỗi đọc không được chấp nhận và kết thúc trong ngân sách đã đặt. Không dùng một con số mili giây tuyệt đối tùy ý để kiểm tra toàn bộ quá trình khởi động trên mọi máy CI.

## 11. Thu thập bằng chứng và chống kết quả xanh giả

### 11.1. Kiểm tra thành công

Một case thành công nên kiểm tra:

- Application context hoặc ứng dụng đã hoàn tất khởi động.
- Các giá trị bean đúng với nguồn dự định, có marker riêng.
- Fallback đúng nếu kịch bản cho phép thiếu nguồn.
- Các tính năng dùng cấu hình cần thiết thực sự có thể hoạt động.
- Nếu chạy trên Pod, trạng thái readiness và danh tính instance được ghi nhận.

Không chỉ kiểm tra một property có tồn tại trong `Environment`: thành phần sử dụng có thể chưa bind hoặc vẫn giữ một giá trị đã tạo trước.

### 11.2. Kiểm tra thất bại

Một case thất bại cần chỉ rõ:

~~~text
Giai đoạn: chuẩn bị container / nạp nguồn / binding / validation
Nguyên nhân: nguồn không có / 403 / timeout / parse / giá trị không hợp lệ
Chính sách: import, fail-fast và retry đang dùng
Bằng chứng: cause hoặc phản hồi API, trạng thái tiến trình/container
Thời gian: bắt đầu và kết thúc trong ngân sách của test
~~~

Với unit/integration test trong JVM, kiểm tra kiểu cause và thuộc tính liên quan. Với API stub, giữ method/path/status và số request cần thiết. Với cluster, giữ Pod spec đã render, UID, trạng thái container, event và log đã loại dữ liệu nhạy cảm.

Không dùng một đoạn log chung như “Application failed” làm bằng chứng duy nhất. Không coi hết thời gian chờ Ready là thành công cho một test âm; test phải phân biệt fail-fast với lỗi image, thiếu tài nguyên hoặc không được scheduling.

### 11.3. Tránh che lỗi bằng fixture

| Cách test dễ che lỗi | Điều chỉnh |
| --- | --- |
| Luôn cấp mọi khóa bằng thuộc tính test ưu tiên cao | Chỉ cấp những giá trị mà kịch bản chủ đích có |
| Dùng cùng marker ở local và remote | Dùng marker khác nhau để nhận biết kết quả |
| Giả lập 404 cho client đang list | Stub đúng request và dạng phản hồi thực |
| Chỉ assert context thất bại | Kiểm tra cause và giai đoạn tương ứng |
| Chỉ thử optional vắng | Thêm optional hiện diện và dữ liệu sai |
| Dùng quyền quản trị cho mọi case | Chạy đúng danh tính cần kiểm tra |
| Dựa vào profile hoặc kubeconfig trên máy cá nhân | Chỉ định fixture, client và môi trường test |
| Viết lại logic fail-fast trong mock rồi test mock đó | Chạy loader/core thực và giữ phần mô phỏng ở ranh giới I/O |

Nếu dùng nhiều test chạy song song, cấp namespace hoặc tên tài nguyên riêng, không chia sẻ trạng thái retry, dữ liệu fixture hoặc cache ngoài dự kiến.

## 12. Phạm vi liên quan tới discovery, load balancing và watcher

Một ứng dụng có thể chỉ cần nạp ConfigMap lúc khởi động. Không bắt buộc bật thêm DiscoveryClient, Spring Cloud LoadBalancer hoặc Configuration Watcher để thực hiện các test chính sách nạp này.

Khi ứng dụng dùng các tính năng đó, thêm test theo đúng trách nhiệm:

| Tính năng | Điều cần kiểm tra thêm |
| --- | --- |
| DiscoveryClient | Namespace và quyền đọc nguồn discovery; tìm đúng instance |
| Spring Cloud LoadBalancer | Cấu hình được dùng bởi client thực; chọn/gọi backend phù hợp |
| Configuration Watcher | Phát hiện và thông báo thay đổi; kết quả áp dụng của từng replica |
| Sức khỏe Pod | Phân biệt startup, readiness và việc có thể phục vụ nghiệp vụ |

Fail-fast khi khởi động không tự định nghĩa cách xử lý một cập nhật cấu hình sai sau đó. Nếu ứng dụng đang dùng bản A rồi watcher thông báo bản B không hợp lệ, cần test riêng ứng dụng giữ A, báo lỗi, cần restart hay hành xử theo cơ chế khác đã thiết kế.

Không giả định việc validation từ chối B sẽ tự rollback mọi thành phần về A như một giao dịch. Hành vi cập nhật phải được quan sát ở bean, tài nguyên sử dụng cấu hình và từng Pod.

## 13. Bài thực hành và tiêu chí hoàn thành

1. Viết chính sách cho một nguồn bắt buộc và một nguồn optional của ứng dụng.
2. Chạy bộ test Config Data với nguồn có, thiếu và dữ liệu sai trong dự án thử nghiệm phù hợp.
3. Kiểm tra test bắt buộc vẫn từ chối nguồn thiếu ngay cả khi local có dữ liệu hợp lệ.
4. Kiểm tra optional vắng dùng đúng fallback, optional hiện diện được nạp và optional không bỏ qua lỗi dữ liệu sai.
5. Đặc tả hành vi nguồn rỗng và lỗi đọc của version Spring Cloud Kubernetes đang dùng.
6. Thêm test tích hợp API hoặc cluster cho lỗi 403, timeout và dữ liệu bắt buộc thiếu.
7. Kiểm tra retry trong một nhóm riêng có ngân sách thời gian hữu hạn.
8. Ghi rõ bằng chứng nào thuộc loader, validation, RBAC, container startup và readiness.

Bài thực hành đạt mục tiêu khi mỗi tình huống thiếu hoặc lỗi cấu hình có một kỳ vọng rõ, phép thử quan sát đúng đường nạp và kết quả không bị nguồn fallback ngoài dự kiến che mất. Những nguồn được phép vắng phải dẫn tới một hành vi đã thiết kế; những điều kiện bắt buộc không đạt phải được phát hiện ở đúng lớp chịu trách nhiệm.
