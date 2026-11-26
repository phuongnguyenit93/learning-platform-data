# Fail-fast và retry khi không đọc được nguồn

## Mục tiêu và phạm vi

Trong chương **Nạp Config Data** của module **SPRING_CLOUD_KUBERNETES**, ứng dụng Spring có thể lấy cấu hình từ ConfigMap hoặc Secret trong quá trình khởi động. Nếu Kubernetes API chưa truy cập được, ServiceAccount thiếu quyền hoặc nguồn cấu hình sai tên, ứng dụng cần có hành vi rõ ràng: tiếp tục với cấu hình thay thế đã được chấp nhận, hay dừng sau một số lần thử hữu hạn.

Bài này giúp bạn:

- Phân biệt lỗi đọc nguồn với lỗi thiếu hoặc sai giá trị cấu hình.
- Cấu hình fail-fast và retry cho từng loại nguồn Kubernetes.
- Ước lượng thời gian chờ, phối hợp với probe và cơ chế khởi động lại container.
- Kiểm chứng hành vi bằng log của đúng tiến trình, trạng thái Pod và các tình huống lỗi có kiểm soát.

Phép thử chỉ cần tính năng nạp cấu hình và quyền RBAC tương ứng. DiscoveryClient, Spring Cloud LoadBalancer và Configuration Watcher phục vụ các nhu cầu khác trong module; không cần bật chúng để chữa lỗi nạp Config Data lúc khởi động.

## 1. Bốn cơ chế giải quyết bốn câu hỏi khác nhau

| Cơ chế | Câu hỏi được giải quyết | Giới hạn cần nhớ |
| --- | --- | --- |
| Fail-fast của nguồn Kubernetes | Khi thao tác đọc nguồn phát sinh lỗi, ứng dụng có dừng khởi động không? | Không tự kiểm tra mọi khóa nghiệp vụ bắt buộc |
| Retry của nguồn Kubernetes | Có gọi lại thao tác đọc đã thất bại trong tiến trình hiện tại không? | Không tự sửa namespace, RBAC hay dữ liệu sai |
| `optional:` trong Config Data | Có được bỏ qua tình huống location/resource được coi là không tồn tại không? | Không phải chỉ thị bỏ qua mọi exception |
| Validation cấu hình ứng dụng | Giá trị cuối cùng có đủ và hợp lệ để ứng dụng làm việc không? | Lỗi validation sau khi nạp không tự được retry bởi bộ nạp nguồn |

**Fail-fast có thể đi cùng retry.** Khi retry được bật đúng điều kiện, lỗi đọc được thử lại trong giới hạn đã chọn; nếu vẫn thất bại thì quá trình khởi động kết thúc bằng lỗi. Vì vậy, fail-fast không nhất thiết có nghĩa là thoát ngay sau yêu cầu HTTP đầu tiên.

Luồng quyết định cho một nguồn bắt buộc:

~~~mermaid
flowchart TD
    A[Bắt đầu nạp nguồn] --> B{Đọc thành công?}
    B -->|Có| C[Bind và kiểm tra giá trị cấu hình]
    C --> D{Dữ liệu hợp lệ?}
    D -->|Có| E[Tiếp tục khởi động]
    D -->|Không| F[Dừng với lỗi validation]
    B -->|Không| G{Fail-fast có hiệu lực?}
    G -->|Không| H[Tiếp tục theo xử lý lỗi của bộ nạp]
    H --> C
    G -->|Có| I{Retry hoạt động và còn lượt?}
    I -->|Có| J[Chờ backoff]
    J --> A
    I -->|Không| K[Dừng với lỗi đọc nguồn]
~~~

Sơ đồ thể hiện chính sách của bài, không khẳng định mọi lỗi hoặc mọi nguồn thiếu đều được chuyển thành cùng một loại exception.

## 2. Phân loại lỗi trước khi chọn chính sách

| Dấu hiệu | Khả năng hồi phục chỉ bằng chờ và thử lại | Việc cần làm |
| --- | --- | --- |
| Timeout, kết nối bị ngắt trong thời gian ngắn | Có thể | Retry hữu hạn, đồng thời kiểm tra mạng và timeout của client |
| API trả lỗi máy chủ hoặc quá tải | Có thể | Backoff và giới hạn tổng thời gian; xem tình trạng control plane |
| HTTP 401 | Thường cần sửa xác thực | Kiểm tra token, cấu hình client và cơ chế cấp thông tin xác thực |
| HTTP 403 / Forbidden | Thường cần sửa phân quyền | Kiểm tra ServiceAccount, namespace, Role và RoleBinding |
| Không tìm thấy ConfigMap/Secret dự kiến | Thường cần sửa tên hoặc thứ tự triển khai | Xác nhận nguồn tồn tại; kiểm tra cách implementation xử lý nguồn vắng mặt |
| YAML sai, giá trị không chuyển được kiểu | Thường cần sửa dữ liệu | Sửa nội dung và triển khai lại cấu hình đúng |
| Đọc được nguồn nhưng thiếu khóa bắt buộc | Cần bổ sung hoặc sửa nguồn | Dùng validation để ngăn ứng dụng chạy với dữ liệu thiếu |

Một lỗi thường xuyên có thể trở thành tạm thời nếu hệ thống bên ngoài được sửa trong lúc ứng dụng đang thử lại. Tuy nhiên, cấu hình retry không bảo đảm bộ nạp tự phân biệt và chỉ retry các lỗi tạm thời. Có thể thấy 403 bị lặp lại đến hết ngân sách; điều đó không làm RoleBinding tự xuất hiện.

Đối với cấu hình quan trọng như thông tin kết nối hoặc giới hạn xử lý nghiệp vụ, nên chọn chính sách dừng rõ ràng khi không thể có dữ liệu hợp lệ. Chỉ tiếp tục khi dữ liệu thay thế đã được xác định, kiểm tra và chấp nhận cho đúng môi trường.

## 3. Đặt chính sách ở nơi có thể đọc trước nguồn từ xa

Các thiết lập để tìm nguồn, xử lý lỗi và retry phải có sẵn trước khi đọc nguồn đó. Đặt chúng trong cấu hình đóng gói cùng ứng dụng, biến môi trường của container hoặc tham số khởi động phù hợp.

Không đặt duy nhất `fail-fast`, số lần retry hay namespace trong chính ConfigMap đang không đọc được. Khi lỗi xảy ra trước lúc nạp nội dung, các giá trị nằm trong nguồn ấy chưa thể điều khiển thao tác đang thất bại.

Bài dùng Config Data import:

~~~yaml
spring:
  config:
    import: "kubernetes:"
~~~

Không bật thêm legacy bootstrap cho cùng cơ chế nạp. Tài liệu Spring Cloud Kubernetes quy định chọn Config Data hoặc bootstrap, không dùng cả hai cách đồng thời. Xem [Kubernetes PropertySource implementations — 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config.html).

Đây cũng là lý do một phương thức nghiệp vụ gắn `@Retryable`, một `ApplicationRunner` hoặc vòng lặp trong controller không sửa được lỗi Config Data xảy ra trước khi application context được tạo xong.

## 4. Cấu hình minh họa cho ConfigMap

### 4.1. Phạm vi phiên bản và dependency

Phần dependency dưới đây minh họa theo **Spring Cloud Kubernetes 3.3.x**, dùng Fabric8. Sử dụng BOM Spring Cloud tương thích với Spring Boot của ứng dụng; không tự gán phiên bản độc lập cho từng thư viện. Nếu dự án dùng nhánh khác, đối chiếu tài liệu của chính nhánh đó, nhất là dependency hỗ trợ retry/AOP.

Trong dự án Spring Boot web thực hành, các dependency cần thiết cho ví dụ gồm:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-fabric8-config</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.retry</groupId>
    <artifactId>spring-retry</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
~~~

Với nhánh được minh họa, tài liệu yêu cầu bật fail-fast và có các dependency retry/AOP để sử dụng retry. Chỉ khai báo `retry.enabled=true` không đủ nếu thiếu thành phần cần thiết. Xem [ConfigMap PropertySource — fail-fast và retry, phiên bản 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config/configmap-propertysource.html).

### 4.2. Cấu hình local của ứng dụng

Ứng dụng có tên `config-demo`, chạy trong namespace lab `config-lab`:

~~~yaml
spring:
  application:
    name: config-demo
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      config:
        enabled: true
        enable-api: true
        name: config-demo
        namespace: config-lab
        include-profile-specific-sources: false
        fail-fast: true
        retry:
          enabled: true
          max-attempts: 4
          initial-interval: 1000
          multiplier: 2.0
          max-interval: 4000
      secrets:
        enabled: false
      discovery:
        enabled: false

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true

logging:
  level:
    org.springframework.cloud.kubernetes: DEBUG
    org.springframework.retry.support.RetryTemplate: DEBUG
~~~

Chỉ một ConfigMap được chỉ định để lượt thử dễ giải thích. Secrets bị tắt trong lượt thử này; một lỗi từ nguồn khác sẽ không làm lẫn kết quả. Không bật Configuration Watcher hoặc cơ chế reload.

Trong môi trường thực tế, chỉ giữ mức log chi tiết trong thời gian cần điều tra. Không ghi toàn bộ Environment hoặc nội dung Secret để chứng minh việc nạp nguồn.

### 4.3. ConfigMap chứa dữ liệu nghiệp vụ

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: config-demo
  namespace: config-lab
data:
  catalog.region: "ap-southeast"
  catalog.timeout-ms: "1500"
~~~

ConfigMap này chứa giá trị ứng dụng sử dụng. Các thiết lập điều khiển việc đọc vẫn nằm ở cấu hình local của ứng dụng.

## 5. Kiểm tra dữ liệu sau khi nạp

Trong dự án Java 17 trở lên dùng Jakarta Validation, khai báo cấu hình có kiểm tra ràng buộc:

~~~java
package example.configdemo;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(
        @NotBlank String region,
        @Min(100) @Max(10000) int timeoutMs) {
}
~~~

Đăng ký kiểu cấu hình và thêm một dấu mốc sau khi bind thành công:

~~~java
package example.configdemo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableConfigurationProperties(CatalogProperties.class)
public class ConfigDemoApplication {
    private static final Logger log =
            LoggerFactory.getLogger(ConfigDemoApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner configurationMarker(CatalogProperties properties) {
        return args -> log.info(
                "CONFIG_BOUND region={} timeoutMs={}",
                properties.region(), properties.timeoutMs());
    }
}
~~~

Trong ví dụ, thiếu `catalog.region` hoặc timeout ngoài khoảng sẽ làm việc tạo bean cấu hình thất bại. Không thêm giá trị mặc định cho hai khóa này trong lượt thử, vì giá trị mặc định có thể che tình huống nguồn chưa cung cấp dữ liệu.

Dấu mốc `CONFIG_BOUND` cho thấy bean đã được bind và vượt qua các ràng buộc trên; nó không thay thế trạng thái Ready của toàn ứng dụng, cũng không chứng minh nguồn duy nhất của giá trị là ConfigMap. Biến môi trường hoặc tham số có độ ưu tiên cao hơn có thể cung cấp cùng khóa. Trước khi thử lỗi nguồn, kiểm tra rằng không có các override như `CATALOG_REGION` hoặc `CATALOG_TIMEOUTMS`.

Các ràng buộc được kiểm tra trên **giá trị cuối cùng**. Nếu nghiệp vụ yêu cầu chứng minh nguồn gốc hoặc phiên bản cấu hình, cần thêm cơ chế xác nhận tương ứng; validation giá trị không tự xác minh nguồn gốc. Quy tắc binding và thứ tự nguồn được trình bày trong [Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html).

## 6. Retry thực sự chờ bao lâu?

### 6.1. Đọc đúng các tham số

| Tham số dưới `spring.cloud.kubernetes.config.retry` | Giá trị minh họa | Ý nghĩa trong lượt thử |
| --- | ---: | --- |
| `enabled` | `true` | Cho phép retry nếu các điều kiện kích hoạt khác thỏa mãn |
| `max-attempts` | `4` | Tối đa bốn lần thực hiện, gồm lần đầu và tối đa ba lần thử lại |
| `initial-interval` | `1000` | Khoảng chờ ban đầu, đơn vị mili giây |
| `multiplier` | `2.0` | Tăng khoảng chờ theo hệ số hai |
| `max-interval` | `4000` | Giới hạn khoảng chờ của mỗi bước backoff, đơn vị mili giây |

Với chính sách minh họa và các lần đọc đều lỗi:

~~~text
Lần 1 thất bại -> chờ 1 giây
Lần 2 thất bại -> chờ 2 giây
Lần 3 thất bại -> chờ 4 giây
Lần 4 thất bại -> hết lượt, truyền lỗi lên

Tổng backoff = 1 + 2 + 4 = 7 giây
~~~

Không có khoảng ngủ retry sau lần cuối cùng. Thời gian mỗi lần gọi không nằm trong bảy giây trên.

Ở cơ chế Config Data của nhánh minh họa, retry bao quanh thao tác locator, không phải lời hứa rằng một attempt luôn tương ứng đúng một HTTP request đến API. Nếu có nhiều nguồn, profile hoặc retry của HTTP client bên dưới, số API request và số dòng log có thể khác số attempt. Cách bọc retry thể hiện trong [ConfigDataRetryableConfigMapPropertySourceLocator — mã nguồn chính thức](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/3.3.x/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/config/ConfigDataRetryableConfigMapPropertySourceLocator.java).

### 6.2. Tính một ngân sách khởi động

Có thể ước lượng cho một chuỗi thao tác đơn giản:

~~~text
Tổng thời gian ≈ tổng thời gian các attempt
              + tổng backoff
              + thời gian khởi tạo ứng dụng còn lại
~~~

Ví dụ giả định mỗi attempt hoàn tất trong tối đa hai giây, có bốn attempt, tổng backoff bảy giây và phần khởi tạo còn lại mất năm giây:

~~~text
4 × 2 + 7 + 5 = 20 giây
~~~

Đây là phép tính minh họa với giả định đã nêu, không phải thời hạn cứng do `max-attempts` bảo đảm. Phải giới hạn connect/read timeout của đúng Kubernetes client đang dùng. Một attempt chứa nhiều API request, timeout không được giới hạn hoặc retry lồng nhau có thể làm tổng thời gian dài hơn nhiều.

Với nhiều ConfigMap và Secret, hãy đo toàn bộ tiến trình khởi động thay vì nhân một công thức cố định rồi coi đó là kết quả chính xác. Cần dành dư địa cho máy chậm, kết nối TLS và tải control plane.

## 7. Phân biệt `optional:`, nguồn vắng mặt và lỗi đọc

Một ví dụ Config Data ở cấp Spring Boot:

~~~properties
spring.config.import=optional:file:/etc/app/extra.properties
~~~

Tiền tố `optional:` cho phép bỏ qua việc location được coi là không tồn tại. Nó không có nghĩa là chấp nhận YAML hỏng, lỗi validation hay mọi lỗi mạng/xác thực. Quy tắc chung nằm ở phần Optional Locations của [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html).

Tương tự, không lấy:

~~~properties
spring.config.import=optional:kubernetes:
~~~

làm cách thay thế việc cấu hình `spring.cloud.kubernetes.config.fail-fast` hoặc `spring.cloud.kubernetes.secrets.fail-fast`. Tác dụng còn phụ thuộc exception mà implementation Kubernetes chuyển lên cho Config Data. Đặc biệt, exception Kubernetes API 403 không tự biến thành lỗi location-not-found chỉ vì thêm `optional:`.

Chiều ngược lại cũng cần chú ý: `spring.config.import=kubernetes:` không có `optional:` **chưa tự bảo đảm mọi ConfigMap có tên dự kiến đều tồn tại và mọi khóa đều được cấp**. Bộ nạp có thể đọc API thành công nhưng nhận một tập dữ liệu không chứa nguồn mong muốn. Ví dụ implementation Fabric8 của nhánh 3.3 có đường xử lý dữ liệu rỗng khi không có ConfigMap phù hợp; đó khác với một API request phát sinh lỗi. Xem [Fabric8ConfigUtils — mã nguồn chính thức](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/3.3.x/spring-cloud-kubernetes-fabric8-config/src/main/java/org/springframework/cloud/kubernetes/fabric8/config/Fabric8ConfigUtils.java).

Hệ quả đối với phép thử:

- Dùng lỗi đọc thực sự, chẳng hạn 403 có kiểm soát trong lab, để kiểm chứng fail-fast và retry của bộ nạp.
- Dùng nguồn thiếu khóa hoặc dữ liệu sai để kiểm chứng validation riêng.
- Nếu việc không tìm thấy nguồn không phát sinh lỗi ở bộ nạp, retry của bộ nạp không tự chờ đến lúc khóa nghiệp vụ xuất hiện.

## 8. Secret có chính sách và đường nạp riêng

Nếu ứng dụng thực sự đọc Secret qua Kubernetes API, cần bật đường đọc đó và cấu hình namespace, tên nguồn, quyền phù hợp. Một mẫu riêng cho Secret:

~~~yaml
spring:
  cloud:
    kubernetes:
      secrets:
        enabled: true
        enable-api: true
        name: config-demo-credentials
        namespace: config-lab
        fail-fast: true
        retry:
          enabled: true
          max-attempts: 4
          initial-interval: 1000
          multiplier: 2.0
          max-interval: 4000
~~~

`config.fail-fast` và `config.retry.*` không tự đặt chính sách cho Secret. Nếu cần cả hai nguồn, khai báo chính sách cho cả `config` và `secrets`. Với nhánh minh họa, đường Secret API không bật mặc định; bật fail-fast nhưng để đường API tắt không tạo ra phép thử đọc Secret qua API. Xem [Secrets PropertySource — 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config/secrets-propertysource.html).

Nếu Secret được mount thành file rồi ứng dụng dùng `configtree:`, hãy kiểm tra hành vi của Config Data filesystem, quyền đọc file và việc mount volume. Nếu Kubernetes chưa khởi động được container vì thiếu nguồn mount hoặc tham chiếu environment bắt buộc, Spring chưa chạy để thực hiện retry. Các thuộc tính retry Kubernetes ở trên không điều khiển mọi đường nạp Secret vào Pod.

Trong bài thực hành chính, giữ `secrets.enabled=false`; không tạo Secret thật chỉ để kiểm chứng retry và không in giá trị nhạy cảm vào log.

## 9. RBAC và probe cho môi trường lab

### 9.1. Một danh tính đọc được và một danh tính bị từ chối

Giả sử namespace `config-lab` đã được tạo riêng cho thực hành. Các tài nguyên RBAC minh họa:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: config-demo
  namespace: config-lab
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: config-denied
  namespace: config-lab
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: config-reader
  namespace: config-lab
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: config-demo-reader
  namespace: config-lab
subjects:
  - kind: ServiceAccount
    name: config-demo
    namespace: config-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: config-reader
~~~

Deployment `config-demo` cần chạy image chứa mã và cấu hình ở trên, dùng `serviceAccountName: config-demo`, có nhãn `app=config-demo` và cho phép client xác thực đến Kubernetes API.

Role chỉ đọc ConfigMap trong namespace lab. Đường đọc của Fabric8 3.3 có thể list ConfigMap trong namespace rồi lọc theo tên; chỉ cấp `get` cho một tên chưa chắc đủ. Ở phiên bản khác, đối chiếu thao tác API thực tế trước khi quyết định quyền. Không thêm quyền Secret hoặc quyền quản trị cluster để vượt qua một lỗi ConfigMap.

ServiceAccount `config-denied` chỉ được dùng để tạo lỗi trong lượt thử. Không giả định rằng tên này luôn không có quyền: xác minh nó không được cấp quyền gián tiếp bởi RoleBinding hoặc ClusterRoleBinding khác.

Nếu tài khoản vận hành được phép impersonation, kiểm tra:

~~~powershell
kubectl auth can-i list configmaps -n config-lab --as=system:serviceaccount:config-lab:config-demo
kubectl auth can-i list configmaps -n config-lab --as=system:serviceaccount:config-lab:config-denied
~~~

Kỳ vọng lần lượt là `yes` và `no`. Nếu lệnh bị từ chối impersonation, cần người có quyền phù hợp kiểm tra; đó chưa phải bằng chứng về quyền của ứng dụng.

### 9.2. Cho phép thời gian khởi động nhưng không nhận tải sớm

Phần probe có thể ghép vào container web thực hành:

~~~yaml
ports:
  - name: http
    containerPort: 8080
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 5
  failureThreshold: 24
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
~~~

Đây là fragment của container, không phải Deployment đầy đủ. Với thiết lập minh họa, startup probe dành khoảng 120 giây theo chu kỳ kiểm tra; hãy chọn ngân sách dựa trên thời gian khởi động đo được.

Startup probe bảo vệ khoảng khởi động trước khi liveness/readiness bắt đầu kiểm tra theo cơ chế probe. Readiness điều khiển việc Pod đủ điều kiện nhận lưu lượng qua Service; liveness có thể dẫn đến khởi động lại container. Xem [Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

Startup probe không giữ tiến trình sống nếu chính ứng dụng thoát do fail-fast. Sau khi ứng dụng đã có cấu hình hợp lệ, cũng không nên tự làm liveness phụ thuộc việc Kubernetes API luôn truy cập được chỉ để đọc lại cấu hình không cần thiết.

## 10. Kiểm chứng bằng các lượt thử có kiểm soát

Các thao tác dưới đây dành cho namespace lab và Deployment mẫu đã triển khai. Chúng không phải hướng dẫn làm gián đoạn control plane. Giữ một replica để dễ theo dõi và phục hồi các override giữa các lượt thử.

### Lượt A — Đọc thành công

Chạy với ServiceAccount `config-demo`, ConfigMap hợp lệ và cấu hình retry ban đầu. Kiểm tra:

~~~powershell
kubectl -n config-lab rollout status deployment/config-demo
kubectl -n config-lab get pods -l app=config-demo
kubectl -n config-lab logs deployment/config-demo --timestamps --tail=200
~~~

Kỳ vọng có `CONFIG_BOUND region=ap-southeast timeoutMs=1500`, ứng dụng khởi động và Pod Ready. Không cần thấy retry khi thao tác đọc đã thành công.

### Lượt B — Lỗi đọc, fail-fast bật, retry tắt

Giữ `fail-fast=true`, tắt retry bằng override và đổi ServiceAccount:

~~~powershell
kubectl -n config-lab set env deployment/config-demo SPRING_CLOUD_KUBERNETES_CONFIG_RETRY_ENABLED=false
kubectl -n config-lab set serviceaccount deployment/config-demo config-denied
~~~

Hai lệnh làm thay đổi Pod template; chỉ bắt đầu thu thập kết quả sau khi xác định Pod mới thuộc cấu hình cuối cùng. Kỳ vọng lỗi Forbidden từ việc đọc ConfigMap, không có `CONFIG_BOUND` trong lần khởi động lỗi và không hoàn tất khởi động ứng dụng.

Không dùng thời gian rất ngắn hay đúng một dòng log làm bằng chứng duy nhất. Dù đã tắt retry của nguồn, Kubernetes client bên dưới vẫn có hành vi kết nối và timeout riêng.

### Lượt C — Lỗi đọc, retry bật nhưng không khôi phục quyền

Giữ ServiceAccount bị từ chối và bật lại retry:

~~~powershell
kubectl -n config-lab set env deployment/config-demo SPRING_CLOUD_KUBERNETES_CONFIG_RETRY_ENABLED=true
~~~

Với cấu hình local bốn attempt, quan sát việc thử lại có giới hạn và cuối cùng khởi động thất bại. Đối chiếu timestamp, log retry và exception cuối cùng trong **cùng một lần chạy container**. Không lấy số lần restart của container làm số attempt retry.

### Lượt D — Khôi phục quyền trong khi cùng tiến trình đang retry

Để dễ thao tác bằng tay, dùng ngân sách riêng cho lượt này:

~~~powershell
kubectl -n config-lab set env deployment/config-demo SPRING_CLOUD_KUBERNETES_CONFIG_RETRY_MAXATTEMPTS=6 SPRING_CLOUD_KUBERNETES_CONFIG_RETRY_INITIALINTERVAL=5000 SPRING_CLOUD_KUBERNETES_CONFIG_RETRY_MAXINTERVAL=10000
~~~

Hệ số vẫn là 2.0. Nếu tất cả các lần đều lỗi, riêng tổng backoff là `5 + 10 + 10 + 10 + 10 = 45` giây, chưa tính thời gian đọc. Ngay khi thấy các attempt thất bại của container mới, cấp quyền bằng một RoleBinding tạm trong terminal khác:

~~~powershell
kubectl -n config-lab create rolebinding retry-lab-recovery --role=config-reader --serviceaccount=config-lab:config-denied
~~~

Nếu thay đổi quyền có hiệu lực trước khi hết lượt, một lần đọc tiếp theo có thể thành công. Tiêu chí cần kiểm chứng là **cùng Pod UID và cùng lần chạy container** chuyển từ lỗi đọc sang `CONFIG_BOUND` rồi Ready, không phải container đã restart và thành công ở lần khởi động mới.

Đây là mô phỏng khôi phục một điều kiện bên ngoài. Nó không có nghĩa là 403 thông thường sẽ tự hết. Nếu hết lượt trước khi được cấp quyền, ghi nhận là khởi động thất bại; chỉ coi lần sau là một lượt khởi động mới.

### Lượt E — Đọc được nhưng giá trị không hợp lệ

Khôi phục ServiceAccount đọc được, rồi trong bản ConfigMap lab đặt `catalog.region` thành chuỗi rỗng hoặc `catalog.timeout-ms` thành `50`. Khởi động Pod mới để nạp lại dữ liệu.

Kỳ vọng lỗi bind/validation và không có dấu mốc thành công. Không mong chờ bộ retry đọc nguồn lặp lại chỉ vì một bean nghiệp vụ không vượt qua validation sau đó. Sửa ConfigMap về dữ liệu hợp lệ và khởi động lại cho lượt xác nhận cuối.

### Cách đọc đúng log và trạng thái

Trước tiên lấy tên và UID Pod mới cần quan sát:

~~~powershell
kubectl -n config-lab get pods -l app=config-demo -o custom-columns='NAME:.metadata.name,UID:.metadata.uid,RESTARTS:.status.containerStatuses[0].restartCount'
~~~

Sau đó dùng đúng tên Pod hiển thị, thay `TEN_POD` trong các lệnh:

~~~powershell
kubectl -n config-lab logs TEN_POD --timestamps --tail=300
kubectl -n config-lab describe pod TEN_POD
kubectl -n config-lab logs TEN_POD --previous --timestamps --tail=300
~~~

`--previous` chỉ có dữ liệu khi container đã có lần chạy trước còn log được giữ lại. Nếu Pod có nhiều container, chọn đúng container ứng dụng bằng `-c`. Trong rolling update, Pod cũ còn Ready có thể làm Deployment vẫn phục vụ được dù Pod mới liên tục lỗi; không suy ra phiên bản mới đã khởi động thành công chỉ từ tình trạng phục vụ chung.

Bảng ghi kết quả nên có:

| Lượt | Pod UID / lần chạy container | Chính sách đang có hiệu lực | Lỗi gốc | Diễn biến retry | Kết quả cuối |
| --- | --- | --- | --- | --- | --- |
| A | Ghi thực tế | Đọc được | Không | Không cần thử lại | Bound và Ready |
| B | Ghi thực tế | Fail-fast, retry tắt | Forbidden | Không retry ở tầng nguồn | Khởi động lỗi |
| C | Ghi thực tế | Retry hữu hạn | Forbidden | Hết ngân sách | Khởi động lỗi |
| D | Ghi thực tế | Retry, được khôi phục quyền | Forbidden rồi đọc được | Thành công trước khi hết lượt | Cùng tiến trình tiếp tục |
| E | Ghi thực tế | Đọc được, validation bật | Giá trị không hợp lệ | Không retry vì lỗi validation này | Khởi động lỗi |

Đây là các kết quả kỳ vọng của thiết kế phép thử, không phải số liệu đã chạy sẵn.

### Phục hồi môi trường sau các lượt lỗi

Đưa Deployment về ServiceAccount ban đầu, gỡ các override retry để quay về cấu hình đóng gói và xóa đúng RoleBinding tạm đã tạo:

~~~powershell
kubectl -n config-lab set serviceaccount deployment/config-demo config-demo
kubectl -n config-lab set env deployment/config-demo SPRING_CLOUD_KUBERNETES_CONFIG_RETRY_ENABLED- SPRING_CLOUD_KUBERNETES_CONFIG_RETRY_MAXATTEMPTS- SPRING_CLOUD_KUBERNETES_CONFIG_RETRY_INITIALINTERVAL- SPRING_CLOUD_KUBERNETES_CONFIG_RETRY_MAXINTERVAL-
kubectl -n config-lab delete rolebinding retry-lab-recovery --ignore-not-found
kubectl -n config-lab rollout status deployment/config-demo
~~~

Khôi phục dữ liệu ConfigMap hợp lệ trước lần xác nhận cuối. Thay đổi ConfigMap không tự bảo đảm tiến trình đang chạy đã nạp lại; với lượt thử không bật reload, khởi động lại Pod theo quy trình triển khai của lab để xác nhận cấu hình mới.

## 11. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách xử lý |
| --- | --- |
| Bật `retry.enabled` nhưng không có backoff | Kiểm tra fail-fast, dependency và việc chính sách có sẵn trước lúc import |
| Dùng `spring.cloud.config.retry.*` cho Kubernetes | Dùng đúng nhóm `spring.cloud.kubernetes.config.retry.*`; nhóm đầu thuộc Spring Cloud Config Server client |
| Bật fail-fast của ConfigMap rồi mong Secret có cùng hành vi | Khai báo chính sách Secret riêng nếu đường đọc Secret được dùng |
| Không có ConfigMap nhưng không thấy lỗi đọc | Kiểm tra hành vi nguồn rỗng và dùng validation cho khóa bắt buộc |
| Lặp 403 rất lâu | Sửa RBAC; giảm ngân sách retry nếu chỉ kéo dài một lỗi cấu hình cố định |
| Chỉ tăng `max-attempts` khi startup vẫn bị dừng | Đối chiếu API timeout, startup probe, deadline triển khai và retry lồng nhau |
| Đếm `CrashLoopBackOff` là retry của Spring | Phân biệt restart của kubelet với attempt bên trong một lần chạy ứng dụng |
| Mong Configuration Watcher chữa một context chưa khởi động | Chữa đường nạp ban đầu; watcher xử lý thay đổi cấu hình theo cơ chế và điều kiện riêng |
| Đặt mọi giá trị local mặc định để ứng dụng luôn Ready | Chỉ dùng fallback khi nghiệp vụ chấp nhận; kiểm tra dữ liệu cuối cùng và dấu hiệu vận hành |

Đặc biệt, sau khi container thoát do fail-fast, chính sách restart của Pod có thể khiến nó tiếp tục khởi động lại. Mỗi lần chạy có một ngân sách retry mới. Retry hữu hạn trong Spring vì vậy không đồng nghĩa cả Pod sẽ chỉ thử khởi động hữu hạn trong suốt vòng đời.

Nếu nhiều replica khởi động đồng thời, các lịch backoff giống nhau có thể tạo các đợt gọi API cùng thời điểm. Chọn ngân sách hợp lý, kiểm soát tốc độ rollout và đo tải thực tế. Nếu cần jitter hoặc phân loại exception tùy chỉnh, dùng cơ chế được phiên bản thư viện hỗ trợ; không tự bịa thêm một thuộc tính cấu hình không có trong phiên bản đang chạy.

## 12. Tiêu chí hoàn tất

Bạn đã kiểm chứng được chính sách khi có bằng chứng cho cả đường thành công và đường thất bại:

1. Xác định chính xác ConfigMap/Secret nào, namespace nào và đường đọc API hay filesystem.
2. Xác nhận chính sách fail-fast/retry có hiệu lực từ trước khi đọc nguồn.
3. Chứng minh thao tác đọc lỗi được thử lại hữu hạn hoặc không retry đúng theo cấu hình.
4. Phân biệt số attempt, API request và số lần khởi động lại container.
5. Chứng minh thiếu hoặc sai giá trị bắt buộc bị chặn bởi validation.
6. Đối chiếu thời gian khởi động với probe và xác nhận Pod chỉ Ready sau khi ứng dụng đủ điều kiện phục vụ.
7. Phục hồi quyền, dữ liệu và các override của môi trường lab.

Một chính sách phù hợp cho triển khai phải cho biết ứng dụng chấp nhận chờ bao lâu, chờ lỗi nào có cơ hội hồi phục và khi nào cần dừng để người vận hành sửa nguyên nhân. Việc lựa chọn đúng tính năng Spring Cloud Kubernetes bắt đầu từ những bằng chứng đó.
