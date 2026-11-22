# `@ConditionalOnCloudPlatform` và phạm vi nhận diện nền tảng trong Spring Boot

**Chủ đề:** Spring Boot Auto Configuration  
**Ngữ cảnh:** Điều kiện môi trường  
**Mục tiêu:** Hiểu khi nào Spring Boot xem một cloud platform là active, điều kiện `@ConditionalOnCloudPlatform` kiểm tra điều gì, phạm vi nhận diện ra sao, cách kiểm thử và giới hạn cần chú ý trong triển khai thực tế.

## 1. Điều kiện này có nhiệm vụ gì?

`@ConditionalOnCloudPlatform` là một annotation của Spring Boot dùng để **chỉ đăng ký một cấu hình hoặc bean khi nền tảng cloud được chỉ định đang hoạt động** theo cơ chế nhận diện của framework. Nó nằm tại:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnCloudPlatform;
import org.springframework.boot.cloud.CloudPlatform;
```

Ví dụ minh họa một cấu hình chỉ có hiệu lực khi Spring Boot nhận diện Kubernetes:

```java
@AutoConfiguration
@ConditionalOnCloudPlatform(CloudPlatform.KUBERNETES)
public class KubernetesSupportAutoConfiguration {

    @Bean
    KubernetesDeploymentHints kubernetesDeploymentHints() {
        return new KubernetesDeploymentHints();
    }
}
```

Đây là đoạn minh họa API, chưa phải lớp độc lập có thể biên dịch, vì `KubernetesDeploymentHints` là kiểu do ứng dụng phải định nghĩa. Nếu điều kiện không khớp, các bean trong configuration đó không được đăng ký. Nếu điều kiện khớp, chúng có thể được đăng ký với điều kiện những điều kiện phụ khác cũng cho phép.

Annotation được sử dụng trên cả:

- **Lớp `@Configuration` / `@AutoConfiguration`:** điều kiện quyết định sự tham gia của toàn bộ cấu hình.
- **Phương thức `@Bean`:** điều kiện chỉ quyết định việc đăng ký bean từ một phương thức cụ thể.

Ví dụ trên một phương thức:

```java
@Bean
@ConditionalOnCloudPlatform(CloudPlatform.CLOUD_FOUNDRY)
CloudFoundryAdapter cloudFoundryAdapter() {
    return new CloudFoundryAdapter();
}
```

Đoạn này cũng chỉ minh họa cấu hình; kiểu `CloudFoundryAdapter` là kiểu ứng dụng cần tự triển khai. Cả hai trường hợp đều dùng một enum **`CloudPlatform`** làm giá trị bắt buộc của annotation.

## 2. Spring Boot xác định cloud platform bằng cách nào?

Spring Boot có enum `org.springframework.boot.cloud.CloudPlatform` với các phương thức quan trọng:

```java
CloudPlatform.KUBERNETES.isDetected(environment);
CloudPlatform.KUBERNETES.isEnforced(environment);
CloudPlatform.KUBERNETES.isActive(environment);
CloudPlatform.getActive(environment);
```

`environment` ở đây thuộc `org.springframework.core.env.Environment`:

- **`isDetected`**: nhận diện dấu hiệu đặc trưng của nền tảng trong `Environment`, chẳng hạn các biến môi trường.
- **`isEnforced`**: xem nền tảng đó có được ép chọn bởi khóa `spring.main.cloud-platform` hay không.
- **`isActive`**: quyết định nền tảng có hoạt động theo cơ chế nhận diện/ép chọn của Spring Boot hay không.
- **`getActive`**: lấy nền tảng đang hoạt động theo API của phiên bản tương ứng, hoặc `null` nếu không có nền tảng active.

Logic ở mức khái niệm:

```text
Environment của ứng dụng
      |
      |-- spring.main.cloud-platform đã ép chọn?
      |       |-- Có: dùng lựa chọn ép (KUBERNETES, NONE, ...)
      |       `-- Không: dựa trên dấu hiệu đặc trưng của nền tảng
      |
      `-- CloudPlatform tương ứng có active?
              |-- Có: condition khớp
              `-- Không: condition không khớp
```

**Đây là heuristic nhận diện cấu hình/môi trường, không phải phép thử kết nối hay xác thực cloud.** Spring Boot không tự gọi Kubernetes API chỉ để xác nhận Pod có tồn tại, cũng không chứng minh quyền truy cập, dịch vụ hoặc tài nguyên cloud đã sẵn sàng. Việc ép một giá trị có thể làm điều kiện khớp trên laptop ngay cả khi không có cluster.

## 3. Phạm vi nền tảng mà Spring Boot hiểu

Trong dòng **Spring Boot 3.3.x**, enum `CloudPlatform` có các hằng:

| Hằng enum | Ý nghĩa |
| --- | --- |
| `NONE` | Không chọn nền tảng cloud; hữu ích khi cần tránh nhận diện nhầm |
| `CLOUD_FOUNDRY` | Cloud Foundry |
| `HEROKU` | Heroku |
| `SAP` | SAP Cloud platform |
| `NOMAD` | HashiCorp Nomad (xuất hiện từ Spring Boot 3.1) |
| `KUBERNETES` | Nền tảng Kubernetes |
| `AZURE_APP_SERVICE` | Azure App Service |

`CloudPlatform.NONE` là một giá trị đặc biệt để diễn tả trạng thái không sử dụng cloud platform cụ thể, không phải một nhà cung cấp cloud riêng. Giá trị cấu hình tương ứng thường được đặt `spring.main.cloud-platform=NONE`.

**Giới hạn phạm vi:** Không phải mọi nhà cung cấp cloud hoặc kiểu hạ tầng đều có enum riêng. Trên Spring Boot 3.3, `CloudPlatform.KUBERNETES` nói về Kubernetes nói chung, không xác định cluster do **GKE**, **EKS** hay **AKS** quản lý. Chạy trên máy ảo EC2, Docker local hoặc một máy chủ cloud thông thường cũng không mặc định đồng nghĩa với Kubernetes.

Danh sách hằng và thuật toán detection là API phụ thuộc phiên bản. Khi đổi Spring Boot major/minor, phải kiểm tra Javadoc đúng dòng phiên bản đang chạy; không suy diễn mọi enum có trong Spring Boot mới đều có ở 3.3.

## 4. Kubernetes được nhận diện qua dấu hiệu gì?

Tài liệu triển khai cloud của Spring Boot 3.3 mô tả việc tự nhận diện Kubernetes dựa trên các biến môi trường liên quan đến service theo mẫu `"*_SERVICE_HOST"` và `"*_SERVICE_PORT"`.

Ví dụ các dấu hiệu thường thấy trong Pod:

```text
KUBERNETES_SERVICE_HOST=10.96.0.1
KUBERNETES_SERVICE_PORT=443
```

Điểm cần phân biệt:

1. Trong Pod có đầy đủ tín hiệu tương ứng, Spring Boot có thể phát hiện môi trường Kubernetes.
2. Một deployment tùy biến có thể không inject các biến service đó; hệ thống **có thể bỏ sót** Kubernetes dù thật sự đang ở cluster.
3. Một máy local hoặc CI bị cấu hình với các dấu hiệu tương tự có thể dẫn đến **nhận diện nhầm**.
4. Chạy ứng dụng trong container Docker **không đủ để kết luận** rằng Kubernetes đã active.

Đừng dùng một dấu hiệu môi trường làm bằng chứng bảo mật. Nó không xác thực người dùng, không chứng minh kết nối Kubernetes API server, không thay thế token hoặc quyền RBAC và không xác nhận tài nguyên cloud có tồn tại.

### 4.1. Ép nhận diện bằng `spring.main.cloud-platform`

Spring Boot cho phép ép kết quả nhận diện thông qua property:

```yaml
# application.yml
spring:
  main:
    cloud-platform: KUBERNETES
```

Một cách tương đương khi chạy một JAR đã đóng gói:

```bash
java -jar app.jar --spring.main.cloud-platform=KUBERNETES
```

Lệnh chỉ là ví dụ vận hành; `app.jar` phải có sẵn từ ứng dụng của bạn.

Với giá trị trên, các điều kiện cần `KUBERNETES` có thể khớp ngay cả ngoài cluster. Việc này hữu ích cho unit/integration test kiểm tra đăng ký bean, nhưng **không tạo Kubernetes API, node, ConfigMap, ServiceAccount hoặc kết nối cloud**.

Nếu Spring Boot nhận diện nhầm nền tảng trong môi trường kiểm thử, có thể ép không chọn cloud:

```properties
spring.main.cloud-platform=NONE
```

Có thể ép Cloud Foundry để kiểm tra một nhánh khác:

```properties
spring.main.cloud-platform=CLOUD_FOUNDRY
```

Nếu cấu hình override này xuất hiện trong file theo profile, biến môi trường hoặc đối số JVM/CLI, cần xem nguồn cấu hình ưu tiên thực tế. Khi yêu cầu auto-detection, hãy bảo đảm không có override đang áp dụng.

## 5. Bài thực hành độc lập bằng Java 17 và Spring Boot 3.3.5

Ví dụ dùng `ApplicationContextRunner` để kiểm tra ba kiểu quyết định: condition ở mức lớp, condition ở mức phương thức, và override platform. Không cần web server, Docker hoặc Kubernetes thật.

### 5.1. Cấu trúc dự án

```text
cloud-platform-condition-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── CloudPlatformConditionTest.java
```

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>cloud-platform-condition-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Tạo `src/test/java/demo/CloudPlatformConditionTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnCloudPlatform;
import org.springframework.boot.cloud.CloudPlatform;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class CloudPlatformConditionTest {

    static final class KubernetesMarker {
    }

    static final class KubernetesProbe {
    }

    static final class CloudFoundryMarker {
    }

    // Condition tại mức class: mọi @Bean bên trong đều chịu điều kiện.
    @AutoConfiguration
    @ConditionalOnCloudPlatform(CloudPlatform.KUBERNETES)
    static class KubernetesAutoConfiguration {

        @Bean
        KubernetesMarker kubernetesMarker() {
            return new KubernetesMarker();
        }

        @Bean
        KubernetesProbe kubernetesProbe() {
            return new KubernetesProbe();
        }
    }

    // Condition tại mức method: chỉ có một bean bị điều kiện chi phối.
    @AutoConfiguration
    static class CloudFoundryAutoConfiguration {

        @Bean
        @ConditionalOnCloudPlatform(CloudPlatform.CLOUD_FOUNDRY)
        CloudFoundryMarker cloudFoundryMarker() {
            return new CloudFoundryMarker();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(
                            KubernetesAutoConfiguration.class,
                            CloudFoundryAutoConfiguration.class
                    )
            );

    @Test
    void kubernetesOverrideRegistersOnlyKubernetesBeans() {
        runner.withPropertyValues("spring.main.cloud-platform=KUBERNETES")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(KubernetesMarker.class);
                    assertThat(context).hasSingleBean(KubernetesProbe.class);
                    assertThat(context).doesNotHaveBean(CloudFoundryMarker.class);
                    assertThat(CloudPlatform.KUBERNETES.isActive(
                            context.getEnvironment())).isTrue();
                });
    }

    @Test
    void cloudFoundryOverrideRegistersOnlyCloudFoundryBean() {
        runner.withPropertyValues("spring.main.cloud-platform=CLOUD_FOUNDRY")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(KubernetesMarker.class);
                    assertThat(context).doesNotHaveBean(KubernetesProbe.class);
                    assertThat(context).hasSingleBean(CloudFoundryMarker.class);
                });
    }

    @Test
    void noneOverrideDisablesCloudSpecificBeanConditions() {
        runner.withPropertyValues("spring.main.cloud-platform=NONE")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(KubernetesMarker.class);
                    assertThat(context).doesNotHaveBean(KubernetesProbe.class);
                    assertThat(context).doesNotHaveBean(CloudFoundryMarker.class);
                });
    }

    @Test
    void otherCloudDoesNotMatchEitherAnnotation() {
        runner.withPropertyValues("spring.main.cloud-platform=HEROKU")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(KubernetesMarker.class);
                    assertThat(context).doesNotHaveBean(CloudFoundryMarker.class);
                });
    }
}
```

Chạy:

```bash
mvn test
```

**Kết quả mong đợi:** bốn test thành công. Trong báo cáo Maven Surefire thông thường sẽ có:

```text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
```

Mã test không in stdout riêng. Nội dung từng phép thử:

- Khi ép `KUBERNETES`, lớp auto-configuration Kubernetes được kích hoạt và tạo hai bean. Nhánh Cloud Foundry không khớp.
- Khi ép `CLOUD_FOUNDRY`, chỉ nhánh Cloud Foundry tạo bean trong các nhánh đã khai báo.
- Khi ép `NONE`, các điều kiện cloud cụ thể không khớp.
- Khi ép `HEROKU`, không có bean trong ví dụ vì không cấu hình nhánh nào dành cho Heroku.

**Lưu ý về độ tin cậy của test:** Cố ý không viết assertion “trên máy local thì phải không nhận diện cloud” khi không kiểm soát environment. CI có thể chạy bên trong Kubernetes và làm test đó phụ thuộc môi trường. Property override giúp cô lập hành vi Spring Boot cần kiểm chứng.

### 5.2. Kiểm tra auto-detection thực tế

Nếu cần kiểm tra detection nguyên bản, tạo một `Environment` kiểm soát được các property source và dấu hiệu đặc trưng của nền tảng, đồng thời **không** đặt `spring.main.cloud-platform`. So sánh kết quả `CloudPlatform.getActive(environment)` và `CloudPlatform.KUBERNETES.isActive(environment)` trong những trường hợp có/không có dấu hiệu phù hợp.

Khi test cần khẳng định kết nối được Kubernetes/Cloud Foundry thật, phải viết integration test riêng có hạ tầng, credential, service account và quyền API phù hợp. `ApplicationContextRunner` trong ví dụ này chỉ chứng minh kết quả đăng ký bean, không chứng minh hạ tầng hoạt động.

## 6. Phân biệt điều kiện cloud với các điều kiện khác

| Cơ chế | Câu hỏi nó trả lời |
| --- | --- |
| `@ConditionalOnCloudPlatform(CloudPlatform.KUBERNETES)` | Spring Boot có xem Kubernetes là active không? |
| `@ConditionalOnProperty(name = "app.feature.enabled")` | Thuộc tính cấu hình có đáp ứng điều kiện không? |
| `@Profile("k8s")` | Profile `k8s` có được bật không? |
| `@ConditionalOnClass(KubernetesClient.class)` | Thư viện/lớp tùy chọn có trên classpath không? |
| `@ConditionalOnBean(SomeBean.class)` | Container đã nhận diện bean phụ thuộc hay chưa? |
| `@ConditionalOnWebApplication` | Application context có thuộc loại web tương ứng không? |

Các cơ chế trên độc lập và có thể kết hợp với nhau:

- `@Profile("k8s")` **không tự động khớp** chỉ vì đang chạy trên Kubernetes. Profile do Spring active profiles quyết định.
- `@ConditionalOnProperty(name="spring.main.cloud-platform", havingValue="KUBERNETES")` **không tương đương** `@ConditionalOnCloudPlatform(KUBERNETES)`: điều kiện property chỉ xét giá trị override đã khai báo; condition cloud còn có thể dựa trên nhận diện tự động ngay khi không có property đó.
- Có Kubernetes client trên classpath không đồng nghĩa đang ở Kubernetes. Có thể dùng client từ local để kết nối cluster từ xa, trong khi `@ConditionalOnCloudPlatform` không khớp.
- Có cloud platform active cũng không bảo đảm bean khác đã sẵn sàng. Điều kiện classpath hoặc bean dependency có thể cần thêm để tránh lỗi khởi tạo.

Nếu một tính năng chỉ nên bật khi **vừa ở Kubernetes vừa được người vận hành cho phép**, hãy kết hợp hai điều kiện:

```java
@Bean
@ConditionalOnCloudPlatform(CloudPlatform.KUBERNETES)
@ConditionalOnProperty(
        prefix = "app.discovery",
        name = "enabled",
        havingValue = "true"
)
ClusterDiscovery clusterDiscovery() {
    return new ClusterDiscovery();
}
```

Đây là mã minh họa trong một configuration đã có sẵn; `ClusterDiscovery` là lớp cần được định nghĩa bởi ứng dụng. Cả hai điều kiện đều phải khớp. Nếu mục tiêu chỉ là feature flag không phụ thuộc cloud, ưu tiên `@ConditionalOnProperty` riêng.

## 7. Hiểu đúng ranh giới của phát hiện nền tảng

### 7.1. Phát hiện Kubernetes không phải nhận diện provider

`CloudPlatform.KUBERNETES` không nói cluster chạy trên EKS, GKE, AKS hay Kubernetes tự quản. Để chọn integration đặc thù nhà cung cấp, cần metadata/cấu hình provider riêng và kiểm chứng khả năng kết nối tương ứng.

### 7.2. Chạy trong container không tự động có cloud condition

Local Docker, Kubernetes Pod, Heroku dyno và VM trên cloud là các môi trường khác nhau. Một container chỉ là cơ chế đóng gói/chạy; nó không cung cấp đầy đủ tín hiệu đặc thù của các platform được hỗ trợ. Không bật bean cloud-specific chỉ vì thấy một container image hoặc biến `HOSTNAME`.

### 7.3. `spring.main.cloud-platform` là lựa chọn ép, không bảo đảm hạ tầng

Cấu hình có thể được đặt chủ động trong local/test để tái hiện. Điều đó không chứng minh DNS, API endpoint, RBAC, ServiceAccount hoặc tài nguyên đã sẵn sàng. Ngược lại, `NONE` không phải cơ chế ngăn ứng dụng truy cập cloud; nó chỉ làm thay đổi hành vi nhận diện của Spring Boot.

### 7.4. Điều kiện không tự động đổi sau startup

Các điều kiện auto-configuration được sử dụng khi xây dựng application context. Sửa biến môi trường hoặc file cấu hình sau khi ứng dụng đã khởi động không tự động đăng ký lại bean đã bị loại. Khi thay đổi platform mode, cần tạo lại context hoặc triển khai lại theo quy trình vận hành thích hợp.

### 7.5. Không dùng như kiểm tra an ninh

Dấu hiệu env và cấu hình ép chọn không phải attestation bảo mật. Để gọi cloud API, vẫn phải xác thực, kiểm soát quyền và xác nhận tài nguyên. Một bean có condition khớp không bảo đảm quyền cloud của ứng dụng đã hợp lệ.

## 8. Chẩn đoán khi bean không xuất hiện

Thực hiện theo thứ tự:

1. **Xem scope annotation:** `@ConditionalOnCloudPlatform` đặt trên lớp hay trên phương thức? Có điều kiện khác cùng áp dụng không?
2. **Kiểm tra `spring.main.cloud-platform`:** đang ép `NONE`, `HEROKU`, `CLOUD_FOUNDRY` hay `KUBERNETES`? Có nguồn cấu hình ưu tiên cao hơn ghi đè không?
3. **Kiểm tra dấu hiệu nhận diện:** với Kubernetes, xem các biến service mà Spring Boot phiên bản đang dùng có được container cung cấp hay không.
4. **Kiểm tra version và enum:** chỉ dựa trên `CloudPlatform` của Spring Boot thực tế đang chạy, không suy diễn từ tài liệu phiên bản khác.
5. **Xem Condition Evaluation Report:** chạy ứng dụng với `--debug` và tìm lý do của `OnCloudPlatformCondition`. Có Actuator với endpoint conditions được cấu hình/expose phù hợp thì có thể xem `/actuator/conditions`.
6. **Tái hiện tối thiểu:** dùng `ApplicationContextRunner` với `spring.main.cloud-platform=KUBERNETES` rồi đổi thành `NONE`, sau đó so sánh các bean đã đăng ký.
7. **Tách vấn đề runtime:** nếu bean xuất hiện nhưng gọi Kubernetes API thất bại, đó là vấn đề kết nối/credential/permissions, không nhất thiết là lỗi đánh giá condition.

Ví dụ xem báo cáo điều kiện của một ứng dụng JAR đã có:

```bash
java -jar app.jar --debug --spring.main.cloud-platform=KUBERNETES
```

Báo cáo sẽ giúp phân biệt *condition không khớp* với *bean đã được đăng ký nhưng khởi tạo thất bại*. Tránh bật các endpoint nội bộ ra Internet không được bảo vệ.

## 9. Tình huống thiết kế thực tế

**Tình huống A — Cấu hình chỉ dành cho Kubernetes:** Có một nhóm bean phục vụ đường dẫn hoặc thông tin deployment đặc trưng Kubernetes. Đặt annotation trên lớp auto-configuration; bổ sung classpath condition nếu thư viện Kubernetes là tùy chọn. Sau đó vẫn cần thử quyền và kết nối API.

**Tình huống B — Dùng cùng JAR ở local và trên Kubernetes:** Để test wiring mà không triển khai cluster, dùng property override `KUBERNETES`. Khi ứng dụng production dùng detection thực, kiểm tra các dấu hiệu env deployment; nếu phải ép giá trị, hãy đặt một cách có chủ đích trong cấu hình vận hành.

**Tình huống C — Chỉ muốn tách dev và prod:** Dùng profile hoặc property ứng dụng. `CloudPlatform` không đại diện cho lifecycle stage; một production có thể chạy trên Kubernetes, VM hoặc hạ tầng khác.

**Tình huống D — Muốn phân biệt cloud vendor:** Không dùng mỗi `KUBERNETES` để kết luận AWS/Azure/Google. Cần một cấu hình/provider detector riêng có hợp đồng rõ ràng.

## 10. Câu hỏi tự kiểm tra

**1.** `@ConditionalOnCloudPlatform(KUBERNETES)` có chắc khớp khi chạy trên Docker laptop?  
**Trả lời:** Không. Docker không đồng nghĩa Kubernetes; kết quả phụ thuộc nhận diện thực tế hoặc override.

**2.** Nếu ép `spring.main.cloud-platform=KUBERNETES` trong test mà không có cluster, có thể khớp không?  
**Trả lời:** Có. Điều kiện kiểm tra trạng thái active do Spring Boot quyết định; nó không thử kết nối API server.

**3.** GKE/EKS/AKS có cần ba enum khác nhau không?  
**Trả lời:** Đối với `CloudPlatform.KUBERNETES`, không; chúng đều có thể được nhận diện theo nền tảng Kubernetes, không phản ánh provider.

**4.** Đã bật profile `k8s`, điều kiện cloud tự khớp?  
**Trả lời:** Không. Profile và cloud platform hoạt động độc lập.

**5.** CI nhận diện nhầm cloud, cấu hình nào có thể vô hiệu hóa detection?  
**Trả lời:** `spring.main.cloud-platform=NONE`, với hiểu biết rằng đây chỉ là override trong Spring Boot.

**6.** Khi condition khớp, có được bảo đảm Kubernetes client sẽ kết nối thành công?  
**Trả lời:** Không. Kết nối, DNS, API server, credential và RBAC thuộc tầng runtime.

## 11. Ghi nhớ

`@ConditionalOnCloudPlatform` là công cụ chọn **nhánh cấu hình theo nền tảng mà Spring Boot nhận diện**, thông qua `CloudPlatform` và `Environment`. Nó có phạm vi hỗ trợ hữu hạn theo phiên bản, có cơ chế ép lựa chọn qua `spring.main.cloud-platform`, và **không chứng thực hạ tầng hoặc quyền truy cập**. Thiết kế đúng là kiểm thử việc đăng ký bean riêng biệt với kiểm thử tích hợp cloud, và sử dụng profile/property khi mục tiêu thực sự là cấu hình tính năng hoặc giai đoạn triển khai.

### Tài liệu chính thức

- [Spring Boot 3.3 API — `@ConditionalOnCloudPlatform`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnCloudPlatform.html)
- [Spring Boot 3.3 API — `CloudPlatform`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/cloud/CloudPlatform.html)
- [Spring Boot 3.3 Reference — Deploying to the Cloud](https://docs.spring.io/spring-boot/3.3/how-to/deployment/cloud.html)
- [Spring Boot Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
