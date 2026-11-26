# Profile riêng cho local, kiểm thử và production

## 1. Chọn môi trường chạy bằng một hợp đồng rõ ràng

Một ứng dụng Spring có thể chạy trên máy lập trình viên, trong tiến trình kiểm thử và trong Pod production. Ba nơi này cần cùng logic nghiệp vụ nhưng khác địa chỉ phụ thuộc, dữ liệu kiểm thử, nguồn cấu hình và quyền truy cập Kubernetes.

Trong module `SPRING_CLOUD_KUBERNETES`, bài thuộc chương **Profile và ưu tiên**, tập trung vào cách tổ chức ba profile `local`, `test`, `prod`. Thiết kế này giúp phát triển và kiểm thử mà không phụ thuộc cluster, đồng thời yêu cầu deployment production chọn môi trường và nguồn cấu hình tường minh.

DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer và Configuration Watcher là các tính năng độc lập cần được chọn theo nhu cầu. Profile có thể điều khiển cấu hình của chúng, nhưng bản thân tên profile không tạo RBAC, không chứng minh Pod khỏe và không tự kích hoạt một cơ chế cập nhật cấu hình hoàn chỉnh.

Ví dụ sử dụng Java 17, Spring Boot 3.2 và Spring Cloud Kubernetes 3.1. Các dependency phải được quản lý bằng BOM tương thích của dự án. Những cấu hình, kiểm thử và đầu ra dưới đây là hướng dẫn thực hành, không phải bằng chứng đã chạy trên cluster thực tế.

| Profile môi trường | Mục đích | Nguồn thuộc tính của ví dụ | Điều kiện vận hành |
| --- | --- | --- | --- |
| `local` | Chạy, debug trên máy cá nhân | File local và token giả | Không cần truy cập Kubernetes API |
| `test` | Kiểm thử Spring context trong CI/IDE | Fixture trong test resources | Không cần cluster hoặc Secret thật |
| `prod` | Chạy bản triển khai trên Kubernetes | ConfigMap qua API và token từ Secret được inject | Có namespace, ServiceAccount và quyền phù hợp |

Đây là quy ước của dự án minh họa. Spring không dành ý nghĩa đặc biệt cho chuỗi `local`, `test` hoặc `prod`; phải tự khai báo cấu hình và cách kích hoạt tương ứng.

## 2. Phân biệt profile, nền tảng và ranh giới bảo mật

### 2.1. Profile chọn phần cấu hình và bean được áp dụng

Profile cho phép chọn nhóm cấu hình hoặc bean theo môi trường. File `application-local.yml` được xem xét khi `local` hoạt động; một bean có `@Profile("local")` chỉ đủ điều kiện đăng ký khi điều kiện profile khớp. `@Profile` cũng hỗ trợ biểu thức như `local | test`; xem [Profile API](https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/context/annotation/Profile.html).

Việc có file cấu hình chưa kích hoạt profile. Tên thư mục chạy, namespace Kubernetes hoặc tên image cũng không tự chọn `prod` theo quy ước của bài.

### 2.2. Profile `kubernetes` không đồng nghĩa với `prod`

Spring Cloud Kubernetes có thể tự thêm profile `kubernetes` khi phát hiện ứng dụng chạy trong Kubernetes. Cùng nền tảng đó có thể chứa môi trường phát triển, kiểm thử tích hợp hoặc production. Vì vậy, deployment vẫn cần chọn profile môi trường của nó, chẳng hạn `prod`.

Trong dòng 3.1, nhận diện nền tảng dùng cơ chế của Spring Boot và có thể được điều khiển bởi `spring.main.cloud-platform`. Thuộc tính cũ `spring.cloud.kubernetes.enabled` đã bị loại bỏ từ dòng 3.0; không dùng nó làm công tắc cho ví dụ này. Xem [Kubernetes Ecosystem Awareness](https://docs.spring.io/spring-cloud-kubernetes/reference/3.1/kubernetes-awareness.html).

Hai loại profile có thể cùng tồn tại:

```text
Profile môi trường: prod
Profile nền tảng:   kubernetes
```

Quy tắc “chỉ một môi trường” bên dưới chỉ xét `local`, `test`, `prod`, không cấm profile nền tảng hoặc profile tính năng khác.

### 2.3. Profile không phải cơ chế cấp quyền

Bật `prod` không cấp quyền đọc ConfigMap. Bật `local` cũng không thu hồi quyền của kubeconfig hay ServiceAccount mà tiến trình đang có. Muốn cô lập CI với production, cần kiểm soát thông tin xác thực, mạng và quyền Kubernetes ngoài việc chọn profile.

Thiết kế tốt kết hợp hai lớp: cấu hình ứng dụng chỉ nạp những nguồn cần dùng, và môi trường chạy chỉ có quyền thực sự cần thiết.

## 3. Tổ chức file theo phần dùng chung và phần khác biệt

Giả định ứng dụng web Spring Boot đã có `spring-boot-starter-web`. Các dependency bổ sung cho ví dụ:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-fabric8-config</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Ví dụ chỉ cần tích hợp cấu hình qua Fabric8. Không thêm starter DiscoveryClient hoặc LoadBalancer chỉ để chọn profile; không trộn họ client Fabric8 và Kubernetes Java Client trong cùng thiết kế này.

Cấu trúc tài nguyên minh họa theo bố cục Maven thông thường:

```text
src/
  main/
    resources/
      application.yml
      application-local.yml
      application-prod.yml
  test/
    resources/
      application-test.yml
```

`application-test.yml` thuộc test classpath, không phải bộ cấu hình dành cho JAR production theo cách đóng gói thông thường. Nếu cần một tiến trình ứng dụng chạy trong cluster kiểm thử tích hợp, hãy thiết kế cấu hình phát hành riêng cho nhu cầu đó; không giả định JAR production sẽ chứa test resources.

### 3.1. `application.yml`: dùng chung và chưa chọn môi trường

```yaml
spring:
  application:
    name: checkout-service
  cloud:
    kubernetes:
      config:
        enabled: false
      secrets:
        enabled: false
      discovery:
        enabled: false

logging:
  level:
    root: INFO
```

File dùng chung không chứa `spring.profiles.active`, import Kubernetes hoặc token mặc định. Việc thiếu profile phải được phát hiện, thay vì âm thầm dùng dữ liệu local trong một deployment bị cấu hình sai.

Các trường bắt buộc của nhóm `checkout` cũng chưa có giá trị ở đây. Mỗi môi trường phải cung cấp bộ dữ liệu của mình. Tắt các tích hợp chưa dùng giúp tránh việc thêm một dependency rồi vô tình bắt đầu đọc tài nguyên cluster.

### 3.2. `application-local.yml`: dữ liệu giả và phụ thuộc trên máy cá nhân

```yaml
spring:
  main:
    cloud-platform: NONE

checkout:
  endpoint: "http://localhost:9095"
  timeout: 5s
  token: "local-dummy-token"

logging:
  level:
    example.checkout: DEBUG
```

`NONE` chủ động tắt nhận diện cloud platform cho lượt chạy local. Không có import `kubernetes:`; các tích hợp cấu hình, Secret và discovery vẫn tắt theo file dùng chung.

Token này chỉ là fixture. Endpoint trỏ tới dịch vụ giả hoặc phụ thuộc do người học chuẩn bị; bài không khởi tạo HTTP server tại cổng 9095. Việc bind cấu hình thành công chưa chứng minh endpoint đã kết nối được.

Chỉ bật log chi tiết cho package ứng dụng cần debug. Không tăng log toàn bộ client Kubernetes hoặc dump cấu hình chứa credential để kiểm tra profile.

### 3.3. `application-test.yml`: dữ liệu xác định cho kiểm thử context

```yaml
spring:
  main:
    cloud-platform: NONE

checkout:
  endpoint: "http://localhost:19095"
  timeout: 100ms
  token: "test-dummy-token"

logging:
  level:
    root: WARN
```

Fixture test khác local để một phép kiểm tra có thể phát hiện việc nạp nhầm file. Nó không dùng token thật, không chọn namespace production và không khai báo import từ cluster.

Endpoint trên không được gọi trong bài kiểm thử cấu hình ở phần 7. Nếu kiểm thử client HTTP, cần tạo server giả hoặc quản lý dịch vụ phụ thuộc riêng, bao gồm vòng đời và cổng của nó.

### 3.4. `application-prod.yml`: nạp cấu hình bên ngoài theo chủ đích

```yaml
spring:
  main:
    cloud-platform: KUBERNETES
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      config:
        enabled: true
        enableApi: true
        name: checkout-runtime
        namespace: "${APP_NAMESPACE}"
        includeProfileSpecificSources: false
        fail-fast: true
```

Profile này chọn một ConfigMap có tên cố định trong namespace do deployment cung cấp. `KUBERNETES` yêu cầu tích hợp nhận diện nền tảng theo mục tiêu của profile; nó không tạo cluster, không cung cấp token API và không cấp quyền truy cập.

Import được đặt riêng trong file prod để local và test không tham gia đường nạp nguồn ngoài này. Với Spring Cloud Kubernetes 3.1, `"kubernetes:"` kích hoạt Config Data và các thuộc tính `config` chọn tài nguyên cần đọc. Không đồng thời bật bootstrap legacy; xem [Kubernetes PropertySource implementations](https://docs.spring.io/spring-cloud-kubernetes/reference/3.1/property-source-config.html).

`secrets.enabled` vẫn là `false`: token production được Kubernetes inject bằng `secretKeyRef`, không được ứng dụng đọc qua Secrets API. DiscoveryClient và LoadBalancer chưa được dùng trong ví dụ; muốn dùng thì cần dependency, cấu hình và RBAC tương ứng.

Tắt `includeProfileSpecificSources` giúp lượt cơ sở chỉ đọc `checkout-runtime`, tránh tự tìm thêm tài nguyên theo những profile đang hoạt động. Nguồn ConfigMap có hậu tố profile là một cơ chế riêng với các file `application-local.yml` hay `application-prod.yml` trong JAR; xem [Using a ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/3.1/property-source-config/configmap-propertysource.html).

## 4. Kích hoạt profile từ đúng nơi

### 4.1. Local: chỉ rõ profile ở cấu hình chạy

Với một JAR đã được build, có thể chạy trong PowerShell:

```powershell
java -jar .\target\checkout-service.jar --spring.profiles.active=local
```

Đường dẫn JAR là minh họa, cần thay bằng artifact thực tế. IDE có thể truyền cùng application argument. Nếu dùng Java system property, đặt nó trước `-jar`:

```powershell
java "-Dspring.profiles.active=local" -jar .\target\checkout-service.jar
```

Chọn một cách cấu hình chủ động và kiểm tra các tham số có sẵn trong IDE/CI. Không giữ một biến môi trường cũ rồi suy rằng lần chạy mới chỉ chịu ảnh hưởng bởi file vừa chỉnh.

### 4.2. Test: khai báo ở lớp kiểm thử Spring

`@ActiveProfiles("test")` chọn profile cho Spring TestContext. Tạo file `application-test.yml` không làm mọi bài test tự dùng profile đó. Unit test không mở Spring context thì cũng không tự được hưởng cơ chế nạp file profile.

Ví dụ kiểm thử đầy đủ ở phần 7 dùng `inheritProfiles = false` để không cộng thêm profile từ lớp kiểm thử cha. Hành vi kế thừa được mô tả tại [ActiveProfiles API](https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/test/context/ActiveProfiles.html).

### 4.3. Production: deployment chọn profile ngay khi tạo tiến trình

Trong khai báo container:

```yaml
env:
  - name: SPRING_PROFILES_ACTIVE
    value: prod
```

Đây là trích đoạn; manifest thực hành đầy đủ nằm ở phần 8. Kubernetes cho phép thiết lập biến môi trường ở khai báo container; xem [Define Environment Variables for a Container](https://kubernetes.io/docs/tasks/inject-data-application/define-environment-variable-container/).

Không chờ tới khi đọc ConfigMap production mới tìm thấy chỉ thị bật `prod`, trong khi import ConfigMap lại nằm trong file chỉ được nạp sau khi `prod` đã hoạt động. Đầu vào chọn môi trường phải có sẵn từ cấu hình khởi chạy.

### 4.4. Không đặt lệnh tự kích hoạt trong file đã phụ thuộc profile

Không viết cấu hình sau vào `application-prod.yml`:

```yaml
# Không hợp lệ trong một file profile-specific
spring:
  profiles:
    active: prod
```

`spring.profiles.active` và `spring.profiles.default` thuộc tài liệu không phụ thuộc profile; không đặt chúng trong file profile-specific hoặc tài liệu đã được kích hoạt bằng `spring.config.activate.on-profile`. Cách tổ chức và các ràng buộc này có trong [Spring Boot Profiles](https://docs.spring.io/spring-boot/docs/3.2.12/reference/html/features.html#features.profiles).

Trong thiết kế của bài, deployment hoặc cấu hình chạy chọn profile, nên không cần một giá trị `active` cố định trong JAR.

## 5. Đăng ký kiểu cấu hình và phát hiện môi trường bị chọn sai

### 5.1. Một kiểu thuộc tính dùng chung cho ba môi trường

Tạo `CheckoutProperties.java`:

```java
package example.checkout;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(
    @NotNull URI endpoint,
    @NotNull Duration timeout,
    @NotBlank String token
) {
    @Override
    public String toString() {
        return "CheckoutProperties[redacted]";
    }
}
```

Cả ba môi trường có cùng hợp đồng về dữ liệu. Không cần nhân ba class chỉ vì các giá trị khác nhau. Các constraint phát hiện trường thiếu hoặc token blank; chúng chưa kiểm tra toàn bộ chính sách URL, timeout hoặc tính hợp lệ của thông tin xác thực.

Ghi đè `toString()` giúp tránh log cả record chứa token. Không log riêng accessor `token()` hoặc serialize toàn bộ bean qua endpoint chẩn đoán.

Tạo lớp ứng dụng:

```java
package example.checkout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(CheckoutProperties.class)
public class CheckoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(CheckoutApplication.class, args);
    }
}
```

### 5.2. Quy tắc dự án: đúng một profile môi trường

Spring cho phép nhiều profile đồng thời. Để các môi trường của ví dụ không bị trộn, thêm `RuntimeProfilePolicy.java`:

```java
package example.checkout;

import java.util.Arrays;
import java.util.Set;

import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class RuntimeProfilePolicy {
    private static final Set<String> ENVIRONMENTS =
        Set.of("local", "test", "prod");

    @Bean
    static BeanFactoryPostProcessor requireOneEnvironment(Environment environment) {
        return beanFactory -> {
            long count = Arrays.stream(environment.getActiveProfiles())
                .filter(ENVIRONMENTS::contains)
                .count();

            if (count != 1) {
                throw new IllegalStateException(
                    "Activate exactly one environment profile: local, test, prod"
                );
            }
        };
    }
}
```

Đây là chính sách tự bổ sung, không phải mặc định của Spring. Nó chấp nhận `prod,kubernetes` vì chỉ có một profile trong tập môi trường, nhưng từ chối `local,test` hoặc không có profile môi trường nào.

`BeanFactoryPostProcessor` được dùng ở giai đoạn xử lý bean definitions; ví dụ chỉ đọc `Environment`, không lấy các bean nghiệp vụ ra khởi tạo sớm. Vòng đời liên quan được mô tả trong [BeanFactoryPostProcessor API](https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/beans/factory/config/BeanFactoryPostProcessor.html).

Config Data đã được xử lý trước bước này. Nếu vô tình bật `prod` cùng `test`, import Kubernetes có thể đã được thử và báo lỗi trước khi guard chạy. Guard giúp phát hiện cấu hình không được chấp nhận, không phải hàng rào ngăn mọi yêu cầu mạng; CI vẫn phải kiểm soát profile và quyền truy cập ngay từ đầu.

### 5.3. Đọc bằng chứng cấu hình mà không in token

Tạo `ProfileConfigurationEvidence.java`:

```java
package example.checkout;

import java.util.Arrays;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class ProfileConfigurationEvidence {
    private static final Logger log =
        LoggerFactory.getLogger(ProfileConfigurationEvidence.class);

    @Bean
    ApplicationRunner reportProfileConfiguration(
            Environment environment, CheckoutProperties properties) {
        return args -> log.info(
            "PROFILE_CONFIG_READY profiles={} timeout={} tokenConfigured={}",
            Arrays.toString(environment.getActiveProfiles()),
            properties.timeout(),
            properties.token() != null && !properties.token().isBlank()
        );
    }
}
```

Với local và không có override bên ngoài, đầu ra kỳ vọng có phần nội dung:

```text
PROFILE_CONFIG_READY profiles=[local] timeout=PT5S tokenConfigured=true
```

Dòng này xác nhận profile quan sát được và một số trường sau binding, không chứng minh endpoint khỏe hay token được hệ thống đích chấp nhận. Nếu cần xác định nguồn thắng, quan sát thêm tên PropertySource/origin với dữ liệu đã che, thay vì công bố toàn bộ `Environment`.

## 6. Khi nào dùng @Profile cho bean?

Các giá trị khác nhau thường chỉ cần file cấu hình khác nhau. `@Profile` hữu ích khi phải chọn một implementation hoặc nhóm bean riêng, chẳng hạn adapter giả trong local/test và adapter gọi hệ thống thật ở prod.

Một trích đoạn cấu hình cho chẩn đoán chỉ ở môi trường phát triển/kiểm thử:

```java
@Bean
@Profile("local | test")
ApplicationRunner announceNonProductionMode() {
    return args -> log.info("Non-production diagnostics enabled");
}
```

Đoạn này minh họa một phương thức bên trong class `@Configuration` có logger và import phù hợp. Nó không thay thế guard profile hoặc cấu hình bảo mật của ứng dụng.

Tránh `@Profile("!prod")` cho một bean giả có ảnh hưởng nghiệp vụ nếu mọi môi trường ngoài prod chưa được định nghĩa rõ. Một lỗi gõ tên profile có thể làm điều kiện phủ định vẫn đúng. Biểu thức khẳng định `local | test` thể hiện chính xác hai nơi được phép dùng implementation đó.

Nếu hai implementation cùng một interface cùng được đăng ký do nhiều profile hoạt động, ứng dụng có thể không biết inject bean nào hoặc dùng lựa chọn không như mong muốn. Thiết kế chính sách profile trước khi dùng `@Primary` để che sự mơ hồ.

## 7. Kiểm thử để chứng minh profile test thực sự độc lập

Đặt lớp kiểm thử sau trong test sources, cùng package hoặc dưới package ứng dụng:

```java
package example.checkout;

import java.net.URI;
import java.time.Duration;
import java.util.Arrays;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles(value = "test", inheritProfiles = false)
class TestProfileConfigurationTest {
    @Autowired
    private CheckoutProperties properties;

    @Autowired
    private Environment environment;

    @Test
    void usesTestFixtureWithoutKubernetesConfigImport() {
        assertThat(Arrays.asList(environment.getActiveProfiles()))
            .contains("test")
            .doesNotContain("local", "prod");

        assertThat(properties.endpoint())
            .isEqualTo(URI.create("http://localhost:19095"));
        assertThat(properties.timeout())
            .isEqualTo(Duration.ofMillis(100));
        assertThat(properties.token()).isEqualTo("test-dummy-token");

        assertThat(environment.getProperty(
            "spring.cloud.kubernetes.config.enabled", Boolean.class))
            .isFalse();
        assertThat(environment.getProperty(
            "spring.cloud.kubernetes.secrets.enabled", Boolean.class))
            .isFalse();
        assertThat(environment.getProperty("spring.config.import")).isNull();
    }
}
```

Đây là một phép kiểm thử Spring context cấu hình: nó có thể phát hiện file test không được đóng gói vào test classpath, profile bị chọn sai, fixture bị ghi đè hoặc import cấu hình ngoài bị thêm ngoài ý muốn. Nó không gọi HTTP, không thử DiscoveryClient và không xác nhận RBAC production.

Việc so token với hằng số ở đây chỉ áp dụng cho fixture giả. Không đưa token thật vào expected value của test, báo cáo lỗi hoặc snapshot.

Môi trường CI vẫn có thể cung cấp các thuộc tính khác qua biến môi trường, Java system properties hoặc cấu hình chạy. Assertion của ví dụ sẽ làm các thay đổi ảnh hưởng đến fixture trở nên nhìn thấy được; muốn chứng minh tiến trình không có đường truy cập production, cần bổ sung cách ly môi trường và quyền, không chỉ kiểm tra vài thuộc tính.

Tách rõ kiểm thử unit, kiểm thử context và kiểm thử tích hợp với cluster. Chỉ nhóm cuối cùng mới nên được cấp quyền cluster riêng, có tài nguyên và dữ liệu riêng, cùng quy trình dọn dẹp phù hợp.

## 8. Thực hành profile prod trên một namespace riêng

Manifest sau minh họa hình thức cung cấp cấu hình của prod bằng dữ liệu giả trong namespace `profile-lab`. Tên profile `prod` ở đây phục vụ bài thực hành, không biến namespace lab thành môi trường production thật.

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: profile-lab
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: checkout-runtime
  namespace: profile-lab
data:
  checkout.endpoint: "http://payment-api.profile-lab.svc.cluster.local:8080"
  checkout.timeout: "1500ms"
---
apiVersion: v1
kind: Secret
metadata:
  name: checkout-credentials
  namespace: profile-lab
type: Opaque
stringData:
  token: "lab-only-prod-token-not-a-real-credential"
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: checkout-app
  namespace: profile-lab
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: checkout-config-reader
  namespace: profile-lab
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: checkout-config-reader
  namespace: profile-lab
subjects:
  - kind: ServiceAccount
    name: checkout-app
    namespace: profile-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: checkout-config-reader
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-service
  namespace: profile-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: checkout-service
  template:
    metadata:
      labels:
        app: checkout-service
    spec:
      serviceAccountName: checkout-app
      containers:
        - name: app
          image: registry.example.com/learning/checkout-service:profiles-lab
          ports:
            - containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
            - name: APP_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
            - name: CHECKOUT_TOKEN
              valueFrom:
                secretKeyRef:
                  name: checkout-credentials
                  key: token
```

Thay image bằng image thực tế chứa ứng dụng và các file cấu hình main resources. Endpoint `payment-api` là địa chỉ phụ thuộc minh họa, không được manifest này tạo ra; runner chỉ kiểm tra dữ liệu cấu hình nên không yêu cầu gọi nó trong bước này.

`APP_NAMESPACE` lấy namespace của Pod; `CHECKOUT_TOKEN` được Kubernetes lấy từ Secret và đưa vào môi trường container. Ứng dụng không cần quyền Secrets API cho đường inject này. Quyền của ứng dụng đối với ConfigMap vẫn được cấp riêng qua RoleBinding. Cách dùng `secretKeyRef` và giới hạn cập nhật biến môi trường được trình bày tại [Distribute Credentials Securely Using Secrets](https://kubernetes.io/docs/tasks/inject-data-application/distribute-credentials-secure/).

Role của bài chỉ phục vụ lần đọc ConfigMap ban đầu trong namespace lab, không cấp quyền discovery hoặc watch. Khi bổ sung tính năng khác, phải xét đúng tài nguyên và thao tác API mà tính năng đó cần, thay vì sao chép một Role rộng cho mọi môi trường.

Sau khi lưu manifest thực hành, chẳng hạn `profiles-lab.yaml`:

```powershell
kubectl apply -f .\profiles-lab.yaml
kubectl -n profile-lab rollout status deployment/checkout-service --timeout=120s
kubectl -n profile-lab get pods -l app=checkout-service -o wide

$podName = 'THAY-BANG-TEN-POD-THUC'
kubectl -n profile-lab get pod $podName -o 'custom-columns=NAME:.metadata.name,UID:.metadata.uid,SA:.spec.serviceAccountName,IMAGE:.spec.containers[*].image'
kubectl -n profile-lab logs $podName -c app --tail=150
```

Với dữ liệu này, log ứng dụng cần cho thấy `prod` trong tập profile đang hoạt động và timeout tương đương `PT1.5S`. Tập profile có thể chứa thêm `kubernetes`; không buộc thứ tự hoặc toàn bộ chuỗi profile phải đúng một hình thức trình bày cố định.

Manifest chưa khai báo readiness probe. Rollout hoặc trạng thái Pod không thay thế bằng chứng binding, kiểm tra kết nối phụ thuộc và tiêu chí sức khỏe của một deployment hoàn chỉnh.

## 9. Quan hệ với ưu tiên và các cách mở rộng

### 9.1. Profile chọn dữ liệu, không khóa cứng giá trị hiệu lực

Với cấu hình ở cùng nhóm vị trí, file theo profile bổ sung hoặc ghi đè file dùng chung. Các nguồn khác vẫn tham gia cơ chế ưu tiên của Spring Boot. Chẳng hạn, chạy local với `--checkout.timeout=8s` có thể khiến bean nhận 8 giây thay vì giá trị 5 giây trong file local.

Vì vậy, khi một giá trị không đúng kỳ vọng, cần xem cả profile đang hoạt động và nguồn của thuộc tính đó. Chỉ nhìn tên `application-prod.yml` không đủ để khẳng định mọi giá trị hiệu lực đến từ file ấy. Xem [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/docs/3.2.12/reference/html/features.html#features.external-config).

Không giải quyết môi trường bị trộn bằng cách thử hoán đổi thứ tự `local,prod` cho đến khi một giá trị có vẻ đúng. Chính sách của bài từ chối cả hai cùng hoạt động, kể cả trong trường hợp một số thuộc tính có thể được framework phân giải theo thứ tự.

### 9.2. `on-profile` là điều kiện khớp, không phải lệnh bật profile

Thay cho nhiều file, có thể dùng tài liệu YAML tách bằng `---` với điều kiện `spring.config.activate.on-profile`. Ví dụ trích đoạn:

```yaml
spring:
  application:
    name: checkout-service
---
spring:
  config:
    activate:
      on-profile: local
checkout:
  timeout: 5s
```

Tài liệu thứ hai chỉ có hiệu lực khi `local` đã hoạt động. Nó không tự kích hoạt `local` chỉ vì được đặt trong cùng file. Đoạn này minh họa cách tổ chức thay thế, chưa chứa đủ cấu hình bắt buộc của toàn bộ ứng dụng trong bài.

Chọn cách chia file hoặc nhiều tài liệu phù hợp với dự án rồi dùng nhất quán. Tránh để cùng một thuộc tính nằm ở nhiều chỗ chỉ vì tồn tại cả hai cách tổ chức.

### 9.3. Profile tính năng có thể đi cùng một môi trường

Nếu cần thêm một tập cấu hình quan sát hệ thống, có thể dùng profile phụ như `observability` cùng `prod`. Với nhu cầu lặp lại, Spring Boot có profile groups; nhóm được khai báo trong tài liệu không phụ thuộc profile.

Ví dụ thiết kế mở rộng trong file dùng chung:

```yaml
spring:
  profiles:
    group:
      release:
        - prod
        - observability
```

Kích hoạt `release` sẽ thêm các profile thành viên theo cơ chế nhóm. Guard của bài vẫn thấy đúng một môi trường là `prod`. Nội dung `observability` cần được định nghĩa riêng nếu sử dụng; đoạn minh họa không tự cài Actuator hoặc hệ thống giám sát.

Không đưa `local` vào nhóm hoặc `spring.profiles.include` dùng chung cho mọi lượt chạy. Nếu làm vậy, một lần chạy prod vẫn có thể mang theo cấu hình local và bị chính sách môi trường từ chối.

## 10. Ma trận kiểm chứng và chẩn đoán

### 10.1. Các lượt thử có ý nghĩa

Thực hiện từng lượt với cấu hình chạy và môi trường đã biết. Khi đổi profile của deployment, tạo Pod mới; không xem đó là một thay đổi thuộc tính nghiệp vụ thông thường trong cùng context.

| Lượt thử | Kỳ vọng | Bằng chứng cần xem |
| --- | --- | --- |
| Chạy JAR với `local` | Dùng fixture local, không import Kubernetes của prod | Profile đang hoạt động, timeout 5 giây và cấu hình import |
| Chạy lớp test với `@ActiveProfiles("test")` | Fixture test và assertion đạt | Kết quả kiểm thử cùng các giá trị đã kiểm tra |
| Không chọn `local`, `test` hoặc `prod` | Không khởi động thành công theo chính sách | Lỗi guard profile; có thể có lỗi cấu hình khác nếu môi trường bị can thiệp |
| Chọn đồng thời `local,test` | Guard từ chối | Thông báo yêu cầu đúng một profile môi trường |
| Chọn đồng thời `test,prod` | Tổ hợp không được chấp nhận | Có thể lỗi import trước guard; phải bỏ prod khỏi lượt test |
| Chạy profile prod trong namespace lab hợp lệ | Bind dữ liệu từ ConfigMap và Secret được inject | UID Pod, profile có prod, timeout 1,5 giây và token không blank |
| Bỏ Secret hoặc khóa mà `secretKeyRef` bắt buộc tham chiếu | Container có thể chưa khởi động được | Events/trạng thái Pod, không chờ log runner chưa tồn tại |
| Token được cung cấp nhưng là chuỗi blank | Validation bean thất bại | Lỗi trường `checkout.token`, không xuất token thật |
| Prod không đọc được ConfigMap hoặc không có các trường cần thiết | Không đạt nạp cấu hình hoặc validation | Lỗi API/quyền, nguồn đã chọn và constraint của bean |
| Local thêm `--checkout.timeout=8s` | Timeout hiệu lực có thể thành 8 giây | Bean thực tế và nguồn ghi đè, không chỉ file local |

### 10.2. Câu hỏi giúp khoanh vùng nhanh

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| Chạy test nhưng thấy dữ liệu local | Có `@ActiveProfiles` chưa, file test nằm đúng classpath không, có kế thừa profile không |
| Test cố kết nối cluster | Import hoặc bootstrap dùng chung, profile prod bị thêm, feature được bật hoặc quyền môi trường bị dùng ngoài chủ đích |
| Pod có profile kubernetes nhưng không có prod | Kiểm tra `SPRING_PROFILES_ACTIVE` trong khai báo container và cấu hình khởi chạy thực tế |
| Prod báo không tìm thấy `APP_NAMESPACE` | Downward API và biến môi trường container, không điền namespace mặc định tùy tiện |
| Có lỗi 403 khi nạp ConfigMap | Đúng ServiceAccount, namespace, RoleBinding và thao tác API bị từ chối |
| File prod thay đổi mà Pod vẫn giữ cấu hình cũ | Image, Pod UID, thời điểm khởi động và file thực tế trong artifact |
| Token Secret đã đổi nhưng container vẫn dùng giá trị cũ | Biến môi trường không tự cập nhật; cần kế hoạch tạo lại container/rollout |
| Một bean giả xuất hiện ở sai môi trường | Biểu thức @Profile, nhiều profile cùng hoạt động và chính sách chọn môi trường |

Configuration Watcher không phải cơ chế chuyển một context từ local sang prod. Việc kích hoạt profile ảnh hưởng đến tập bean và cấu hình khởi tạo; với thiết kế này, thay môi trường bằng một lần khởi động mới và kiểm chứng lại dữ liệu, quyền cùng sức khỏe Pod.

Một lượt triển khai chỉ được xem là đã kiểm chứng profile khi biết chính xác tập profile đang hoạt động, nguồn của các thuộc tính quan trọng và bean mà consumer sử dụng. Kết quả kiểm thử cấu hình, quyền truy cập cluster và sức khỏe phụ thuộc là các bằng chứng riêng cần được đánh giá đúng phạm vi.
