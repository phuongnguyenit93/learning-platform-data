# Kết hợp điều kiện profile và nền tảng triển khai trong Spring Boot

## 1. Vấn đề bài học giải quyết

Một ứng dụng Spring Boot có thể chạy trong môi trường phát triển (`dev`), thử nghiệm (`staging`) hoặc production (`prod`). Cùng môi trường `prod`, ứng dụng lại có thể chạy trực tiếp trên máy ảo, trên Cloud Foundry hoặc trong Kubernetes. Trong các trường hợp đó, có những giá trị chỉ phụ thuộc vào **mục đích của môi trường** và có những giá trị chỉ phù hợp với **nền tảng triển khai**.

Ví dụ:

- Ở `dev`, ứng dụng dùng endpoint giả lập và bật log ở mức dễ quan sát.
- Ở `prod`, ứng dụng chọn endpoint sản xuất và tắt chức năng chỉ dành cho thử nghiệm.
- Nếu đang chạy trên Kubernetes, ứng dụng cần một số tùy chọn phù hợp với container.
- Một nhóm cấu hình chỉ được bật khi **đồng thời** profile là `prod` hoặc `staging` **và** nền tảng được nhận diện là Kubernetes.

Spring Boot hỗ trợ **tài liệu cấu hình có điều kiện** bằng hai thuộc tính:

```properties
spring.config.activate.on-profile
spring.config.activate.on-cloud-platform
```

Bài này hướng dẫn cách phối hợp cả hai điều kiện trong một tài liệu YAML hoặc `.properties`, quy tắc lựa chọn tài liệu, thứ tự ghi đè khi nhiều tài liệu cùng được kích hoạt, và một ứng dụng quan sát có thể chạy thử trên laptop mà không cần tạo cụm Kubernetes.

**Bối cảnh:** Java 21, Spring Boot 3.3.x, cấu hình Config Data. Các host, URL, tên môi trường và cờ chức năng trong ví dụ đều là dữ liệu giả lập dành cho học tập.

Sau khi hoàn thành, bạn có thể:

1. Giải thích khác biệt giữa profile và cloud platform.
2. Viết `application.yaml` nhiều tài liệu với dấu phân cách `---`.
3. Dùng `on-profile` với một profile hoặc biểu thức như `prod | staging`.
4. Dùng `on-cloud-platform: kubernetes` để kích hoạt theo nền tảng.
5. Giải thích vì sao hai điều kiện cùng xuất hiện có quan hệ **AND**.
6. Dự đoán cấu hình cuối cùng khi có nhiều tài liệu cùng phù hợp.
7. Mô phỏng nền tảng bằng `spring.main.cloud-platform` để thử nghiệm có kiểm soát.
8. Truy xuất kết quả qua `Environment`, `@ConfigurationProperties` và kiểm thử.
9. Tránh những lỗi cấu hình bất hợp lệ khi cố kích hoạt profile ngay trong tài liệu phụ thuộc profile.

## 2. Profile và cloud platform trả lời hai câu hỏi khác nhau

**Profile** là nhãn do ứng dụng hoặc người vận hành chọn để quyết định nhóm cấu hình nào phù hợp với một ngữ cảnh. Những tên như `dev`, `staging`, `prod`, `local` do nhóm phát triển tự quy ước. Bạn có thể chạy profile `prod` trên laptop để kiểm tra cấu hình mà không có gì tự động biến laptop thành hạ tầng production.

**Cloud platform** mô tả nền tảng đang chạy. Spring Boot cung cấp `CloudPlatform` để nhận diện một số môi trường triển khai nổi tiếng, trong đó có `KUBERNETES` và `CLOUD_FOUNDRY`. Cơ chế này sử dụng dấu hiệu từ environment và có thể được chỉ định rõ bằng thuộc tính `spring.main.cloud-platform`. Nền tảng triển khai cũng không quyết định sẵn profile.

| Câu hỏi | Profile | Cloud platform |
| --- | --- | --- |
| Nó thể hiện điều gì? | Mục đích/ngữ cảnh cấu hình của ứng dụng | Nền tảng runtime được nhận diện hoặc chỉ định |
| Do ai quyết định? | Ứng dụng, người chạy, pipeline hoặc công cụ triển khai | Tín hiệu nền tảng và/hoặc thuộc tính override |
| Ví dụ | `dev`, `staging`, `prod` | `kubernetes`, `cloud_foundry`, `none` |
| Cách chọn trong lab | `--spring.profiles.active=prod` | `--spring.main.cloud-platform=KUBERNETES` |
| Điều kiện tài liệu | `spring.config.activate.on-profile` | `spring.config.activate.on-cloud-platform` |

Hai trục độc lập tạo thành một **ma trận điều kiện**:

```text
                       CLOUD PLATFORM
                 Other / none      Kubernetes
               +----------------+------------------+
PROFILE  dev    | config dev     | config dev + K8s |
         staging| config staging | staging + K8s    |
         prod   | config prod    | prod + K8s       |
               +----------------+------------------+
```

Dấu `+` trong sơ đồ chỉ nghĩa là các tài liệu phù hợp được nạp và **gộp giá trị thuộc tính** theo quy tắc ưu tiên, chứ không có phép cộng giá trị số học. Một document chứa cả `on-profile` và `on-cloud-platform` sẽ chỉ được áp dụng ở những ô giao nhau thỏa cả hai điều kiện.

## 3. Tài liệu cấu hình có điều kiện là gì?

Một file `application.yaml` có thể chứa **nhiều tài liệu YAML**. Mỗi tài liệu được phân cách bằng một dòng `---`. Spring Boot xử lý từng tài liệu như một phần của Config Data, sau đó đưa những tài liệu **đang được kích hoạt** vào `Environment`.

Ví dụ đơn giản:

```yaml
app:
  message: from-base
---
spring:
  config:
    activate:
      on-profile: dev
app:
  message: from-dev
```

Tài liệu đầu tiên không có điều kiện nên làm cấu hình nền. Tài liệu thứ hai chỉ tham gia khi profile `dev` phù hợp. Nếu bạn chạy với:

```bash
java -jar app.jar --spring.profiles.active=dev
```

thì `app.message` có thể là `from-dev`. Nếu không kích hoạt `dev` và không có nguồn ghi đè khác, kết quả là `from-base`.

Những điều cần nhớ:

- `spring.config.activate.on-profile` kiểm tra một **profile expression**.
- `spring.config.activate.on-cloud-platform` kiểm tra **CloudPlatform**.
- Hai khóa này **không phải** lệnh bật profile hoặc tạo môi trường Kubernetes. Chúng chỉ quyết định một tài liệu đã có được đưa vào tập Config Data hay không.
- Khi hai điều kiện nằm trong **cùng một tài liệu**, Spring Boot yêu cầu **cả hai** đều khớp.
- Với các tài liệu được nạp cùng một file, những giá trị ở tài liệu sau có thể ghi đè giá trị trùng khóa của tài liệu trước. Trong ứng dụng thực, còn phải xét location, import, biến môi trường, tham số CLI và các nguồn có ưu tiên khác.
- Một tài liệu không thỏa điều kiện sẽ không đóng góp các thuộc tính trong tài liệu đó. Không có khái niệm “lấy một phần giá trị dù điều kiện sai”.

Các tài liệu ở ví dụ sau đều dùng những khóa không nhạy cảm để có thể quan sát mà không làm lộ secret.

## 4. Điều kiện `on-profile`: một profile, OR, AND và NOT

Cách đơn giản nhất:

```yaml
spring:
  config:
    activate:
      on-profile: prod
```

Chỉ tài liệu chứa đoạn trên mới phù hợp với profile `prod`.

Khi cần dùng nhiều profile, `on-profile` nhận biểu thức. Ví dụ:

```yaml
spring:
  config:
    activate:
      on-profile: "prod | staging"
```

Dấu `|` biểu diễn **OR**: chỉ cần một trong hai profile phù hợp. Đây là lựa chọn tốt khi `prod` và `staging` dùng chung một lớp cấu hình triển khai.

Một ví dụ điều kiện chặt hơn:

```yaml
spring:
  config:
    activate:
      on-profile: "prod & !legacy"
```

Nó yêu cầu `prod` đang hoạt động và `legacy` không hoạt động. Dấu `&` là AND, dấu `!` là NOT. Có thể dùng ngoặc để trình bày biểu thức phức tạp khi cần:

```yaml
spring:
  config:
    activate:
      on-profile: "prod & (blue | green)"
```

Khi dùng biểu thức, nên đặt nó trong dấu nháy YAML để tránh ký tự đặc biệt bị diễn giải theo cú pháp YAML hoặc gây khó đọc. Tên profile là quy ước do nhóm sở hữu ứng dụng đặt ra, vì vậy hãy giữ tên ngắn, dễ hiểu và nhất quán.

**Không nhầm** biểu thức `on-profile` với danh sách cấu hình `spring.profiles.active`. Ví dụ sau dùng hai profile cùng lúc:

```bash
java -jar app.jar --spring.profiles.active=prod,blue
```

Tài liệu có biểu thức `prod & blue` sẽ phù hợp. Một tài liệu có điều kiện `staging` sẽ không được kích hoạt chỉ vì `prod` cũng là môi trường phát hành.

## 5. Điều kiện `on-cloud-platform`: nhận diện nền tảng

Tài liệu dành riêng cho Kubernetes:

```yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
app:
  platform-note: running-on-kubernetes
```

Spring Boot chỉ đưa tài liệu này vào cấu hình hiệu lực khi cloud platform đang hoạt động phù hợp với `KUBERNETES`.

Spring Boot có cơ chế phát hiện nền tảng thông qua dấu hiệu môi trường. Trên Kubernetes, nó có thể sử dụng các biến môi trường liên quan đến service, ví dụ những cặp biến `*_SERVICE_HOST` và `*_SERVICE_PORT`, để nhận biết. Bạn không nên tự tạo vài biến với tên giống Kubernetes trong production để giả mạo việc phát hiện; khi cần thử nghiệm có kiểm soát, dùng thuộc tính override do framework hỗ trợ.

**Mô phỏng Kubernetes trên laptop:**

```bash
java -jar app.jar --spring.main.cloud-platform=KUBERNETES
```

Tùy chọn trên buộc Spring Boot xem cloud platform là `KUBERNETES` trong lần chạy đó, nên các tài liệu có `on-cloud-platform: kubernetes` có thể được kích hoạt mà không cần tạo cluster. Nó **không** cung cấp API server, service discovery, volume mount, DNS hay tính năng khác của Kubernetes. Vì thế, chỉ dùng cách này cho bài lab hoặc kiểm thử những nhánh cấu hình không phụ thuộc vào hạ tầng thực.

Muốn thử nhánh không có cloud platform, có thể buộc:

```bash
java -jar app.jar --spring.main.cloud-platform=NONE
```

Thuộc tính `spring.main.cloud-platform` hữu ích để thử nghiệm ma trận, nhưng trong triển khai thực phải quyết định dùng auto-detection hay cấu hình explicit, rồi giữ một quy ước nhất quán. `on-cloud-platform` **không phải** công cụ chọn profile. Kết hợp cloud platform với `prod` phải viết hai điều kiện trong cùng tài liệu.

## 6. Kết hợp hai điều kiện trong cùng một tài liệu

Ví dụ:

```yaml
spring:
  config:
    activate:
      on-profile: "prod | staging"
      on-cloud-platform: kubernetes
app:
  runtime-mode: release-on-kubernetes
  diagnostics-enabled: false
```

Đánh giá điều kiện là:

```text
documentActive =
    (activeProfiles phù hợp với "prod | staging")
    AND
    (CloudPlatform đang hoạt động là KUBERNETES)
```

Bảng chân trị:

| Profile đang hoạt động | Cloud platform | Tài liệu trên có được nạp? | Vì sao |
| --- | --- | --- | --- |
| `dev` | `NONE` | Không | Cả hai nhánh đều không phù hợp |
| `dev` | `KUBERNETES` | Không | Cloud đúng nhưng profile sai |
| `prod` | `NONE` | Không | Profile đúng nhưng cloud sai |
| `prod` | `KUBERNETES` | Có | Cả hai nhánh phù hợp |
| `staging` | `KUBERNETES` | Có | `staging` thỏa biểu thức OR và cloud đúng |
| `staging` | `NONE` | Không | Cloud không phù hợp |
| Không chỉ định profile | `KUBERNETES` | Không | Không có `prod` hoặc `staging` phù hợp |

Khi không khai báo profile hoạt động, Spring Boot có khái niệm **default profile**, thông thường tên `default`. Do đó, không có profile active rõ ràng không có nghĩa mọi biểu thức trên profile đều bị vô hiệu hóa; chẳng hạn tài liệu điều kiện `on-profile: default` có thể áp dụng. Bảng trên chỉ xét `prod` và `staging`.

Nếu đưa `on-profile` và `on-cloud-platform` vào **hai tài liệu khác nhau**, Spring Boot đánh giá chúng riêng. Hai tài liệu cùng phù hợp có thể cùng đóng góp thuộc tính, nhưng bạn không thể hiểu việc đặt một điều kiện ở document A và một điều kiện ở document B là tạo ra AND giữa chúng. Muốn có AND, đặt cả hai trong cùng document.

## 7. Ứng dụng thực hành: Deployment Conditions Observer

Ta tạo một ứng dụng Spring Boot console in ra profile, cloud platform và các giá trị đã được chọn. Ứng dụng không cần Spring Web, Kubernetes SDK hoặc quyền truy cập cụm Kubernetes.

### 7.1. Cấu trúc dự án

```text
deployment-conditions/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/
    ├── main/
    │   ├── java/dev/example/deployment/
    │   │   ├── DeploymentConditionsApplication.java
    │   │   └── DemoProperties.java
    │   └── resources/
    │       └── application.yaml
    └── test/
        └── java/dev/example/deployment/
            └── ProductionKubernetesTest.java
```

Tạo một dự án Gradle dùng Java 21 và Spring Boot 3.3.x. Dùng Gradle Wrapper do công cụ tạo dự án cung cấp để không phụ thuộc Gradle cài toàn máy.

`settings.gradle`:

```groovy
rootProject.name = 'deployment-conditions'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Trong repository đã quản lý version plugin qua convention hoặc version catalog, hãy dùng hệ thống quản lý sẵn có của repository. Bản mẫu trên chỉ trình bày cấu hình tối thiểu cho project độc lập.

### 7.2. Thiết kế các tài liệu YAML

`src/main/resources/application.yaml`:

```yaml
# Tài liệu 1: áp dụng cho mọi môi trường.
spring:
  application:
    name: deployment-conditions
  main:
    web-application-type: none

demo:
  mode: base
  platform: generic
  endpoint: "https://service.example.test/base"
  features:
    audit: false
    metrics: false

---
# Tài liệu 2: chỉ khi profile dev.
spring:
  config:
    activate:
      on-profile: dev

demo:
  mode: development
  endpoint: "http://localhost:9091"

---
# Tài liệu 3: chỉ khi profile prod.
spring:
  config:
    activate:
      on-profile: prod

demo:
  mode: production-generic
  endpoint: "https://service.example.test/prod"

---
# Tài liệu 4: áp dụng với mọi profile nếu cloud là Kubernetes.
spring:
  config:
    activate:
      on-cloud-platform: kubernetes

demo:
  platform: kubernetes

---
# Tài liệu 5: yêu cầu (prod hoặc staging) VÀ Kubernetes.
spring:
  config:
    activate:
      on-profile: "prod | staging"
      on-cloud-platform: kubernetes

demo:
  mode: kubernetes-release
  features:
    metrics: true
```

Năm tài liệu minh họa bốn kiểu phạm vi:

1. **Nền chung**: tài liệu 1 đặt giá trị an toàn có thể dùng khi không có điều kiện đặc biệt.
2. **Theo profile**: tài liệu 2 và 3 thay `demo.mode`/`demo.endpoint` nhưng không sửa `demo.platform`.
3. **Theo cloud platform**: tài liệu 4 chỉ thay `demo.platform` bất kể profile, nên khi chạy `dev` trong Kubernetes, mode vẫn là `development`.
4. **Theo giao của hai điều kiện**: tài liệu 5 chỉ thay mode và metrics nếu cloud là Kubernetes **và** active profile phù hợp với `prod | staging`.

Dùng domain `example.test` để minh họa; đó không phải endpoint thật. Chương trình chỉ in chuỗi và không gửi HTTP request tới các địa chỉ đó.

**Thứ tự tài liệu có ý nghĩa.** Ví dụ, với `prod` + Kubernetes, tài liệu 3 đặt `demo.mode=production-generic`, nhưng tài liệu 5 ở phía sau có giá trị `demo.mode=kubernetes-release` và cũng phù hợp, nên ghi đè giá trị này trong phạm vi cùng file. Tài liệu 5 không đặt `demo.endpoint`, nên endpoint vẫn là giá trị đến từ tài liệu 3.

### 7.3. Binding các giá trị thành đối tượng Java

`src/main/java/dev/example/deployment/DemoProperties.java`:

```java
package dev.example.deployment;

import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        String mode,
        String platform,
        URI endpoint,
        Features features
) {
    public record Features(
            boolean audit,
            boolean metrics
    ) {}
}
```

`@ConfigurationProperties` binding nhóm `demo.*` theo kiểu rõ ràng. `URI` giúp thể hiện endpoint là một địa chỉ, `boolean` giúp feature flags có nghĩa cụ thể. Giá trị bên trong record là kết quả **sau khi Spring Boot chọn và gộp các nguồn cấu hình**, không phải toàn bộ các giá trị thô từ từng tài liệu.

### 7.4. In kết quả cấu hình từ ứng dụng

`src/main/java/dev/example/deployment/DeploymentConditionsApplication.java`:

```java
package dev.example.deployment;

import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.cloud.CloudPlatform;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.ConfigurableEnvironment;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DeploymentConditionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(DeploymentConditionsApplication.class, args);
    }

    @Bean
    ApplicationRunner inspect(
            ConfigurableEnvironment environment,
            DemoProperties demo) {
        return args -> {
            CloudPlatform cloud = CloudPlatform.getActive(environment);

            System.out.println("=== DEPLOYMENT CONDITIONS ===");
            System.out.println("activeProfiles = "
                    + Arrays.toString(environment.getActiveProfiles()));
            System.out.println("cloudPlatform = "
                    + (cloud == null ? "<none>" : cloud.name()));
            System.out.println("demo.mode = " + demo.mode());
            System.out.println("demo.platform = " + demo.platform());
            System.out.println("demo.endpoint = " + demo.endpoint());
            System.out.println("demo.features.audit = "
                    + demo.features().audit());
            System.out.println("demo.features.metrics = "
                    + demo.features().metrics());

            System.out.println("Environment demo.mode = "
                    + environment.getProperty("demo.mode"));
        };
    }
}
```

Phần `activeProfiles` cho biết profile được kích hoạt rõ ràng. Phần `cloudPlatform` cho biết nền tảng Spring Boot xác định đang hoạt động. Các trường `demo.*` cho thấy tài liệu nào đã cung cấp hoặc ghi đè từng giá trị. `Environment.getProperty()` giúp đối chiếu một khóa với giá trị được binding vào record.

Ứng dụng không in toàn bộ biến môi trường hoặc secret; nó chỉ quan sát các khóa giả lập được thiết kế trước. Trong dự án thật, không nên log tất cả property hoặc đưa cấu hình nhạy cảm lên endpoint công khai để chẩn đoán.

## 8. Chạy ma trận profile và cloud platform

Từ thư mục gốc project, dùng các lệnh bên dưới. Mỗi lần chạy `bootRun` khởi động một tiến trình mới rồi in kết quả. Vì đã đặt `web-application-type: none`, ứng dụng không cần mở cổng HTTP.

### Thí nghiệm A — không chọn profile, không buộc cloud platform

macOS/Linux:

```bash
./gradlew bootRun --args='--spring.main.cloud-platform=NONE'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.main.cloud-platform=NONE"
```

Kỳ vọng:

```text
activeProfiles = []
cloudPlatform = NONE
demo.mode = base
demo.platform = generic
demo.features.audit = false
demo.features.metrics = false
```

Trong trường hợp không buộc cloud platform, kết quả phát hiện phụ thuộc môi trường thực. Thí nghiệm chủ động đặt `NONE` để tránh việc laptop hoặc CI có sẵn biến môi trường dẫn tới khác biệt khó giải thích.

### Thí nghiệm B — profile `dev`, cloud platform NONE

macOS/Linux:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev --spring.main.cloud-platform=NONE'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev --spring.main.cloud-platform=NONE"
```

Kỳ vọng:

```text
activeProfiles = [dev]
cloudPlatform = NONE
demo.mode = development
demo.platform = generic
demo.endpoint = http://localhost:9091
demo.features.metrics = false
```

Điều kiện profile phù hợp nên tài liệu 2 được nạp. Hai tài liệu phụ thuộc Kubernetes không được nạp.

### Thí nghiệm C — `dev` nhưng mô phỏng Kubernetes

```bash
./gradlew bootRun --args='--spring.profiles.active=dev --spring.main.cloud-platform=KUBERNETES'
```

Kỳ vọng:

```text
activeProfiles = [dev]
cloudPlatform = KUBERNETES
demo.mode = development
demo.platform = kubernetes
demo.features.metrics = false
```

Đây là trường hợp giúp phân biệt hai điều kiện: tài liệu 4 có thể được nạp vì cloud đúng, còn tài liệu 5 **không** được nạp vì `dev` không khớp `prod | staging`. Vì vậy `mode` vẫn là `development`.

### Thí nghiệm D — `prod` nhưng không có Kubernetes

```bash
./gradlew bootRun --args='--spring.profiles.active=prod --spring.main.cloud-platform=NONE'
```

Kỳ vọng:

```text
activeProfiles = [prod]
cloudPlatform = NONE
demo.mode = production-generic
demo.platform = generic
demo.endpoint = https://service.example.test/prod
demo.features.metrics = false
```

Tài liệu theo profile `prod` phù hợp, còn hai tài liệu yêu cầu Kubernetes bị bỏ qua.

### Thí nghiệm E — `prod` trên Kubernetes

```bash
./gradlew bootRun --args='--spring.profiles.active=prod --spring.main.cloud-platform=KUBERNETES'
```

Kỳ vọng:

```text
activeProfiles = [prod]
cloudPlatform = KUBERNETES
demo.mode = kubernetes-release
demo.platform = kubernetes
demo.endpoint = https://service.example.test/prod
demo.features.metrics = true
```

Đây là thí nghiệm trung tâm: tài liệu 3, 4 và 5 đều phù hợp. `mode` và `metrics` đến từ tài liệu 5; `platform` đến từ tài liệu 4; `endpoint` vẫn đến từ tài liệu 3 vì tài liệu 5 không ghi đè khóa này.

### Thí nghiệm F — `staging` trên Kubernetes

```bash
./gradlew bootRun --args='--spring.profiles.active=staging --spring.main.cloud-platform=KUBERNETES'
```

Kỳ vọng:

```text
activeProfiles = [staging]
cloudPlatform = KUBERNETES
demo.mode = kubernetes-release
demo.platform = kubernetes
demo.endpoint = https://service.example.test/base
demo.features.metrics = true
```

Biểu thức `prod | staging` khớp nhờ `staging`, nhưng tài liệu 3 chỉ dành cho `prod` nên không cung cấp endpoint. `demo.endpoint` sẽ giữ giá trị nền từ tài liệu 1.

### Thí nghiệm G — kiểm tra nguồn ưu tiên cao hơn Config Data

Đối số ứng dụng có thể ghi đè thuộc tính hiệu lực trong thí nghiệm:

```bash
./gradlew bootRun --args='--spring.profiles.active=prod --spring.main.cloud-platform=KUBERNETES --demo.mode=from-cli'
```

Kỳ vọng `demo.mode=from-cli`. Điều này **không** có nghĩa tài liệu 5 ngừng được kích hoạt; nó vẫn phù hợp với điều kiện. Chỉ riêng khóa `demo.mode` bị một nguồn có ưu tiên cao hơn ghi đè. Các khóa `demo.platform` và `demo.features.metrics` vẫn phản ánh tài liệu Kubernetes trong ví dụ.

Trên Windows, có thể dùng `.\gradlew.bat bootRun --args="..."` với các đối số tương tự. Lưu ý dấu nháy là cú pháp của shell để truyền một chuỗi `--args` cho Gradle, còn mỗi đối số `--spring...` nằm bên trong được truyền cho ứng dụng Spring Boot.

### 8.1. Bảng đối chiếu kết quả

| Profile | Cloud | `demo.mode` | `demo.platform` | `demo.features.metrics` |
| --- | --- | --- | --- | --- |
| không chọn | NONE | `base` | `generic` | `false` |
| dev | NONE | `development` | `generic` | `false` |
| dev | KUBERNETES | `development` | `kubernetes` | `false` |
| prod | NONE | `production-generic` | `generic` | `false` |
| prod | KUBERNETES | `kubernetes-release` | `kubernetes` | `true` |
| staging | KUBERNETES | `kubernetes-release` | `kubernetes` | `true` |
| prod + CLI override | KUBERNETES | `from-cli` | `kubernetes` | `true` |

Hãy điền kết quả thực tế sau mỗi lệnh và đối chiếu từng thuộc tính, thay vì chỉ kiểm tra `demo.mode`. Sự khác biệt giữa các trường giải thích rõ cơ chế **gộp** những tài liệu đang hoạt động.

## 9. Cấu hình nhiều tài liệu trong `.properties`

Không bắt buộc phải dùng YAML. Spring Boot 3.3 cũng hỗ trợ **multi-document properties** với dòng phân cách có cú pháp `#---` hoặc `!---`.

Ví dụ `application.properties`:

```properties
demo.mode=base
demo.platform=generic
#---
spring.config.activate.on-profile=prod
demo.mode=production-generic
#---
spring.config.activate.on-cloud-platform=kubernetes
demo.platform=kubernetes
#---
spring.config.activate.on-profile=prod | staging
spring.config.activate.on-cloud-platform=kubernetes
demo.mode=kubernetes-release
```

Quy tắc dùng separator trong `.properties` cần chú ý: dòng phân cách không có khoảng trắng ở đầu, đúng ba dấu gạch nối, và các dòng ngay trước/sau separator không được dùng cùng loại tiền tố comment với dòng separator theo quy định của Spring Boot. Không đơn giản đặt một chuỗi `---` trần trong `.properties` rồi kỳ vọng nó hoạt động giống YAML.

Các tài liệu trong `.properties` cũng được xét điều kiện và gộp theo thứ tự. Để giảm nhầm lẫn, trong dự án thực tế nên chọn một định dạng chính cho mỗi location. Khi vừa có `.properties` vừa có YAML ở cùng một location, Spring Boot có quy tắc ưu tiên định dạng riêng; điều đó là một lớp ưu tiên khác với thứ tự tài liệu trong cùng file.

## 10. Cách đặt profile và điều kiện cho đúng

### 10.1. `spring.profiles.active` phải đặt ở nơi hợp lệ

Một lỗi dễ gặp là cố dùng điều kiện profile để kích hoạt profile khác ngay trong cùng tài liệu:

```yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    active: metrics
```

Đây là cấu hình **không hợp lệ**. `spring.profiles.active` và `spring.profiles.default` không được dùng trong profile-specific documents hoặc documents được kích hoạt bởi `spring.config.activate.on-profile`. Spring Boot cũng áp dụng ràng buộc tương tự với các cơ chế chọn hoặc mở rộng profile khác như `spring.profiles.include` và định nghĩa profile group. Đừng dựa vào tài liệu có điều kiện để sửa danh sách profile đã dùng nhằm đánh giá chính điều kiện đó.

Đặt active profile qua CLI, biến môi trường hoặc một tài liệu không gắn profile, ví dụ:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Nếu cần nhóm profile, định nghĩa `spring.profiles.group` trong cấu hình hợp lệ không phụ thuộc profile và chọn nhóm qua cơ chế được Spring Boot hỗ trợ. Hãy coi cấu hình lựa chọn profile và cấu hình được profile kích hoạt là hai trách nhiệm khác nhau.

### 10.2. Điều kiện cloud không tự đổi profile

Ví dụ tài liệu:

```yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
```

không tự biến active profile thành `prod`. Kubernetes có thể chạy ứng dụng `dev` hoặc `staging`. Nếu nhóm của bạn muốn quy ước mọi deployment production phải bật `prod`, cấu hình điều đó trong manifest/pipeline triển khai bằng nguồn hợp lệ.

### 10.3. Một tài liệu có thể phù hợp nhưng vẫn không quyết định giá trị cuối

Khi `prod` và Kubernetes cùng phù hợp, tài liệu 5 của ví dụ được nạp. Nhưng nếu có `--demo.mode=from-cli`, giá trị cuối vẫn là `from-cli`. Điều kiện chỉ quyết định **tài liệu có tham gia không**, còn ưu tiên PropertySource quyết định **giá trị nào thắng**.

Trong chẩn đoán, hãy hỏi hai câu riêng:

1. Tài liệu chứa khóa có được kích hoạt không?
2. Nếu có, nguồn nào cuối cùng quyết định khóa đó?

Trả lời được câu thứ nhất không đảm bảo câu thứ hai.

### 10.4. Chỉ định đúng thời điểm `spring.main.cloud-platform`

Trong lab, truyền `--spring.main.cloud-platform=KUBERNETES` từ dòng lệnh giúp Spring Boot xác định cloud platform ngay lúc nạp cấu hình. Không trông chờ một giá trị được khai báo **bên trong chính tài liệu chỉ kích hoạt khi cloud là Kubernetes** sẽ quyết định cloud platform cho tài liệu đó. Với deployment thật, nên để nền tảng được phát hiện theo điều kiện thực tế hoặc đặt override bằng nguồn ổn định có hiệu lực sớm.

### 10.5. Profile không phải bảo mật

Profile `prod` không có nghĩa tài liệu chỉ được đọc trong production thật. Bất kỳ ai kiểm soát tham số khởi chạy đều có thể bật `prod` trên máy khác. Vì vậy, không đưa token, mật khẩu hoặc private key vào source YAML chỉ vì một tài liệu có điều kiện `on-profile: prod`.

Với secret, dùng cơ chế quản lý bí mật của nền tảng, quyền truy cập và nguồn cấu hình bên ngoài; điều kiện activation chỉ giúp lựa chọn cấu hình. Đừng in secret ra log khi quan sát.

## 11. Kiểm thử điều kiện với Spring Boot Test

Một cách giữ hành vi ổn định khi refactor cấu hình là viết test cho những tổ hợp quan trọng. Ví dụ muốn xác nhận `prod` + Kubernetes kích hoạt tài liệu 5, còn `prod` + NONE vẫn nhận cấu hình production thông thường.

### 11.1. Kiểm thử nhánh `prod` + Kubernetes

`src/test/java/dev/example/deployment/ProductionKubernetesTest.java`:

```java
package dev.example.deployment;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(properties = {
        "spring.main.cloud-platform=KUBERNETES"
})
@ActiveProfiles("prod")
class ProductionKubernetesTest {

    @Autowired
    DemoProperties demo;

    @Test
    void activatesProfileAndPlatformDocumentTogether() {
        assertEquals("kubernetes-release", demo.mode());
        assertEquals("kubernetes", demo.platform());
        assertEquals("https://service.example.test/prod",
                demo.endpoint().toString());
        assertTrue(demo.features().metrics());
    }
}
```

Chạy:

macOS/Linux:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

Test này đặt profile qua `@ActiveProfiles` và ép cloud platform bằng một thuộc tính test. Nó không cần gọi Kubernetes thật. `@SpringBootTest` khởi động context để giá trị của các tài liệu có điều kiện được nạp và binding như trong ứng dụng.

### 11.2. Kiểm thử nhánh production thông thường

Có thể tạo thêm một lớp test:

```java
package dev.example.deployment;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(properties = {
        "spring.main.cloud-platform=NONE"
})
@ActiveProfiles("prod")
class ProductionGenericTest {

    @Autowired
    DemoProperties demo;

    @Test
    void doesNotActivateKubernetesOnlyDocument() {
        assertEquals("production-generic", demo.mode());
        assertEquals("generic", demo.platform());
        assertFalse(demo.features().metrics());
    }
}
```

Khi hai test đạt kết quả mong đợi, bạn đã tạo bằng chứng rằng cùng một profile `prod` có thể nhận giá trị khác nhau tùy cloud platform. Nếu thêm một tài liệu YAML mới ở cuối file sau này, những test này sẽ giúp phát hiện việc thay đổi giá trị mà không cần mở ứng dụng và đọc log bằng tay.

### 11.3. Nên kiểm thử gì thêm?

Với ứng dụng có nhiều cấu hình điều kiện, chọn thêm những tổ hợp mang ý nghĩa nghiệp vụ:

- `dev` + Kubernetes vẫn không nhận giá trị dành riêng cho phát hành.
- `staging` + Kubernetes nhận tài liệu kết hợp nhờ toán tử OR.
- Không có active profile và `NONE` giữ giá trị nền.
- Khi đặt một property bằng CLI, giá trị hiệu lực tuân theo thứ tự ưu tiên của các nguồn.
- Cấu hình không hợp lệ hoặc sai kiểu được phát hiện sớm bằng binding/validation.
- Các giá trị nhạy cảm không bị xuất ra log hoặc endpoint quan sát.

Không nhất thiết tạo một test cho mọi hoán vị nếu có quá nhiều profile và platform. Hãy ưu tiên những tổ hợp có hành vi khác nhau hoặc từng gây lỗi triển khai.

## 12. Chẩn đoán khi kết quả khác dự đoán

### 12.1. Tài liệu profile không được nạp

Kiểm tra:

1. Tên profile chính xác, ví dụ `prod` khác `production` nếu nhóm chưa quy ước alias/group.
2. Active profile thực sự đến từ đâu: CLI, biến môi trường, Java system properties, cấu hình nền hoặc test.
3. Biểu thức `on-profile` có cần OR, AND hay NOT, và profile `default` có tham gia không.
4. Tài liệu YAML có dấu `---` đúng vị trí và khóa `spring.config.activate.on-profile` nằm trong đúng document không.
5. Có một nguồn khác ghi đè cùng khóa sau khi tài liệu được nạp không.

Một lỗi thường gặp là thấy `demo.mode=base` rồi kết luận file YAML không được tìm. File có thể đã được tìm nhưng tài liệu `prod` bên trong nó không được kích hoạt.

### 12.2. Tài liệu Kubernetes không được nạp dù đang chạy trong container

Container không đồng nghĩa Kubernetes. Docker trên laptop không mặc nhiên được Spring Boot nhận diện là Kubernetes. Kiểm tra cloud platform mà Spring Boot thật sự xác định; bài lab có `CloudPlatform.getActive(environment)` để quan sát.

Nếu trong Kubernetes thật mà detection khác mong đợi, kiểm tra dấu hiệu môi trường, môi trường chạy đặc biệt, quy tắc detection của phiên bản đang dùng và cấu hình `spring.main.cloud-platform`. Trong môi trường thử nghiệm, có thể buộc `KUBERNETES` để cô lập lỗi điều kiện, nhưng không nên xem đó là bằng chứng một cluster thật đã cung cấp các dịch vụ phụ trợ.

### 12.3. Đặt cả `on-profile` và `on-cloud-platform` nhưng chỉ một điều kiện đúng

Spring Boot yêu cầu cả hai cùng đúng khi cùng tồn tại trong một tài liệu. Ví dụ `dev` + Kubernetes **không** làm tài liệu `prod | staging` + Kubernetes hoạt động. Giải quyết bằng cách sửa điều kiện theo ý định vận hành hoặc đặt những khóa thực sự dùng chung vào tài liệu chỉ có `on-cloud-platform`.

### 12.4. Profile đúng, cloud đúng, nhưng giá trị vẫn khác

Kiểm tra:

- Tài liệu có điều kiện nào **đứng sau** và ghi đè khóa trong cùng file?
- File profile-specific như `application-prod.yaml` có cung cấp cùng khóa không?
- Có `spring.config.import` hoặc `spring.config.additional-location` không?
- Biến môi trường hay CLI có ưu tiên cao hơn cấu hình file không?
- Khi dùng `@ConfigurationProperties`, tên property có khớp quy tắc relaxed binding không?
- App đã được khởi động lại sau khi thay file chưa?

Với những trường hợp khó, có thể chạy ứng dụng trong môi trường kiểm soát, bật logging chẩn đoán Config Data theo hướng dẫn phù hợp và tra cứu thông tin qua Actuator `env`/`configprops` đã bảo vệ. Không xuất toàn bộ bí mật ra log để kiểm tra thứ tự ưu tiên.

### 12.5. Cấu hình lỗi vì `spring.profiles.active` nằm trong tài liệu có `on-profile`

Đây là ràng buộc của Spring Boot. Di chuyển việc bật profile về một nguồn không phụ thuộc profile hoặc sang tham số khởi chạy. Không sửa bằng cách bọc thêm một điều kiện cloud vì tài liệu vẫn thuộc loại không hợp lệ cho việc khai báo active profile.

### 12.6. Có nhiều profile cùng hoạt động

Nếu cùng bật `prod` và `staging`, các tài liệu có điều kiện profile riêng cho từng tên đều có thể phù hợp. Khi các tài liệu cùng khai báo một khóa, thứ tự file, location và quy tắc profile-specific phải được xét. Đừng coi việc bật nhiều profile là một cơ chế chọn “chỉ một môi trường”. Trong đa số hệ thống, nên có một quy ước rõ ràng để tránh kết hợp các profile mâu thuẫn.

### 12.7. Giá trị chỉ đổi sau khi restart

Các tài liệu điều kiện được quyết định trong quá trình nạp Config Data lúc khởi động. Thay file `application.yaml` hoặc đổi biến môi trường ngoài tiến trình không tự làm bean đã binding nhận giá trị mới. Những cơ chế refresh động cần được thiết kế, bảo vệ và thử nghiệm riêng. Với bài này, mỗi thí nghiệm là một lần khởi động mới.

## 13. Khi nên dùng tài liệu có điều kiện, khi nên tách file

Cả hai cách dưới đây đều hợp lệ:

**Cách A: Một file nhiều tài liệu.**

```text
src/main/resources/application.yaml
  document nền
  document on-profile: dev
  document on-profile: prod
  document on-cloud-platform: kubernetes
  document kết hợp profile + Kubernetes
```

Ưu điểm: mọi điều kiện nằm gần nhau, người học dễ thấy ma trận, phù hợp ứng dụng nhỏ và số điều kiện vừa phải. Hạn chế: file dài, nhiều document cùng ghi đè một khóa dễ gây khó chẩn đoán khi lớn lên.

**Cách B: Nhiều file cộng với tài liệu điều kiện.**

```text
src/main/resources/
├── application.yaml
├── application-dev.yaml
└── application-prod.yaml
```

`application-prod.yaml` chứa thuộc tính theo profile; bạn vẫn có thể dùng tài liệu `on-cloud-platform` trong một file phù hợp để phân tách trường hợp runtime. Với hệ thống lớn, việc chia file theo nhiệm vụ giúp giảm tập trung quá nhiều logic vào một file, nhưng cần rõ thứ tự ưu tiên giữa các location, file profile-specific và các document.

Chọn một quy ước cho nhóm phát triển. Đối với nhánh chỉ dành cho Kubernetes và nhiều profile, điều kiện phối hợp trong một document thường dễ diễn đạt hơn một cấu trúc lặp rất nhiều file. Đối với một giá trị secret hoặc endpoint thật, lưu nó trong nguồn cấu hình được quản lý bên ngoài thay vì nhúng vào tài liệu đóng gói.

## 14. Mẫu áp dụng cho triển khai thật

Một phương án tổ chức thực tế:

- `application.yaml` đóng gói: tên ứng dụng, thông số chung và các giá trị nền không nhạy cảm.
- `application-prod.yaml` hoặc tài liệu `on-profile: prod`: hành vi chung của production, ví dụ cờ chức năng và mức logging phù hợp.
- Tài liệu `on-cloud-platform: kubernetes`: những lựa chọn runtime riêng của Kubernetes, ví dụ một tên service DNS giả lập trong lab.
- Tài liệu có **cả** `on-profile: prod | staging` và `on-cloud-platform: kubernetes`: điều chỉnh một tính năng chỉ dùng cho release trên Kubernetes.
- Secret, credential, token và địa chỉ đặc thù hệ thống: đến từ nguồn ngoài được quản lý, chẳng hạn biến môi trường, ConfigMap/Secret mount hoặc kho secret, với quyền truy cập thích hợp.

Manifest triển khai Kubernetes có thể cấu hình profile bằng biến môi trường:

```yaml
env:
  - name: SPRING_PROFILES_ACTIVE
    value: prod
```

Đây là một **đoạn minh họa** thuộc spec của container, không phải bản manifest Kubernetes hoàn chỉnh. Spring Boot nhận profile `prod`; việc nhận diện Kubernetes là trách nhiệm riêng của cơ chế cloud platform. Nếu muốn chỉ định cloud platform tường minh, có thể thêm cấu hình tương ứng theo quy định của môi trường, nhưng tránh lặp nhiều nguồn gây mâu thuẫn.

Cách này giữ **hai trục điều kiện** độc lập. Ví dụ có thể chạy profile `staging` trên Kubernetes để thử nhánh phát hành trong điều kiện gần production, hoặc chạy `prod` trên hạ tầng không phải Kubernetes mà vẫn nhận các thuộc tính production chung.

## 15. Bài tập tự kiểm tra

**Bài 1.** Với `on-profile: "prod | staging"` và `on-cloud-platform: kubernetes`, tài liệu có được kích hoạt khi profile là `dev` trên Kubernetes không? Vì sao?

**Bài 2.** Cùng tài liệu trên, khi profile `staging` hoạt động nhưng cloud platform là `NONE`, tài liệu có được nạp không?

**Bài 3.** Một document `on-cloud-platform: kubernetes` đứng trước document kết hợp `on-profile: prod` + `on-cloud-platform: kubernetes`. Cả hai cùng đặt `demo.mode` và đều phù hợp. Trong cùng file, không có nguồn khác, giá trị nào thường được ưu tiên?

**Bài 4.** Có thể dùng `spring.config.activate.on-profile: prod` trong một document rồi đặt `spring.profiles.active=metrics` bên dưới để tự bật profile phụ không?

**Bài 5.** Chạy profile `prod` trên laptop có đồng nghĩa CloudPlatform là `KUBERNETES` không? Làm sao mô phỏng cloud platform trong lab?

**Bài 6.** Vì sao một tài liệu đã được kích hoạt vẫn có thể không quyết định giá trị cuối của một khóa?

**Bài 7.** Profile `prod` + Kubernetes trả về `demo.endpoint` từ tài liệu `prod`, nhưng `demo.mode` từ tài liệu kết hợp. Điều đó cho biết Spring Boot gộp tài liệu như thế nào?

**Bài 8.** Một kỹ sư muốn lưu production token trong `application-prod.yaml` vì file chỉ được nạp khi profile `prod` hoạt động. Bạn sẽ giải thích rủi ro gì?

Gợi ý:

1. Không; profile không khớp, nên AND sai.
2. Không; cloud không khớp.
3. Document kết hợp ở sau có thể ghi đè cùng khóa khi cả hai đều được nạp.
4. Không; `spring.profiles.active` không hợp lệ trong document được kích hoạt bằng `on-profile`.
5. Không. Có thể dùng `--spring.main.cloud-platform=KUBERNETES` trong lab.
6. Vì còn thứ tự ưu tiên giữa document, file, location và các nguồn như CLI.
7. Những khóa khác nhau có thể giữ giá trị từ những document khác nhau; chỉ khóa trùng mới bị ghi đè.
8. File đóng gói vẫn có thể bị đọc từ artifact hoặc repository; profile không phải ranh giới bảo vệ secret.

## 16. Tài liệu tham khảo và cách học tiếp

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): multi-document YAML/Properties, `spring.config.activate.on-profile`, `spring.config.activate.on-cloud-platform`, thứ tự Config Data.
- [Spring Boot — Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html): cách chọn profile, default profile và giới hạn của các thuộc tính chọn profile.
- [Spring Boot — Deploying to the Cloud](https://docs.spring.io/spring-boot/how-to/deployment/cloud.html): phát hiện nền tảng và cách chỉ định `spring.main.cloud-platform` khi cần.

Sau bài này, hãy giữ lại một bản chạy được của **Deployment Conditions Observer** và bảng kết quả ma trận. Khi có một cấu hình “chỉ sai trên Kubernetes production”, hãy xác định lần lượt: profile thực sự hoạt động, cloud platform được Spring Boot nhận diện, những tài liệu `activate` phù hợp, thứ tự tài liệu cùng các nguồn ngoài file, rồi đối chiếu giá trị hiệu lực của từng khóa. Đó là cách sử dụng tài liệu có điều kiện một cách chủ động và có thể kiểm chứng.