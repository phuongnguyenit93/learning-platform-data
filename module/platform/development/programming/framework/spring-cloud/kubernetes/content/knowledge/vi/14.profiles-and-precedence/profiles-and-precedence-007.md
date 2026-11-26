# Placeholder và giá trị mặc định

Trong chương **Profile và ưu tiên** của module **SPRING_CLOUD_KUBERNETES**, placeholder giúp cấu hình Spring tham chiếu giá trị đến từ biến môi trường, ConfigMap, Secret hoặc một thuộc tính khác.

Giá trị mặc định hữu ích khi ứng dụng thực sự có thể hoạt động với một lựa chọn dự phòng. Nó cũng có thể che giấu lỗi triển khai: sai tên biến, thiếu nguồn cấu hình hoặc thiếu credential nhưng ứng dụng vẫn khởi động với một giá trị không phù hợp.

Bài này hướng dẫn đọc chính xác biểu thức placeholder, xác định nơi fallback được áp dụng và kiểm chứng hành vi khi cấu hình thiếu, rỗng hoặc sai kiểu. Ví dụ dùng Java 17 trở lên và Spring Boot 3.x; khi ghép vào ứng dụng Spring Cloud Kubernetes, tiếp tục dùng bộ version Boot/Cloud tương thích của project.

## 1. Cú pháp placeholder của Spring

Dạng cơ bản:

```text
${ten-thuoc-tinh}
${ten-thuoc-tinh:gia-tri-mac-dinh}
```

Ví dụ trong `application.yaml`:

```yaml
partner:
  host: "${PARTNER_HOST:partner-gateway}"
  port: "${PARTNER_PORT:8080}"
  base-url: "http://${partner.host}:${partner.port}"
```

Nếu không có `PARTNER_HOST` và `PARTNER_PORT` từ nguồn cấu hình đã nạp, URL được suy ra từ các giá trị dự phòng. Placeholder có thể nằm trong một chuỗi dài hơn và có thể tham chiếu thuộc tính khác. [Property placeholders trong Spring Boot](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html#features.external-config.files.property-placeholders).

| Biểu thức | Khi key chưa có giá trị để resolve |
| --- | --- |
| `${demo.label}` | Không khai báo fallback |
| `${demo.label:guest}` | Dùng chuỗi `guest` |
| `${demo.label:}` | Dùng chuỗi rỗng |
| `${demo.limit:20}` | Dùng văn bản `20`, sau đó consumer có thể chuyển kiểu |
| `${partner.url:http://partner-gateway:8080}` | Dùng toàn bộ URL làm fallback |
| `${PRIMARY_LABEL:${SECONDARY_LABEL:guest}}` | Thử nguồn chính, rồi nguồn phụ, cuối cùng là `guest` |

Dấu `:` sau tên key phân tách phần fallback. Những dấu `:` trong URL của ví dụ vẫn là một phần của giá trị mặc định.

Nên dùng dấu nháy cho chuỗi YAML chứa placeholder, nhất là khi có URL, dấu ngoặc hoặc nội dung dễ bị hiểu khác bởi YAML.

### Dùng tên thuộc tính chuẩn khi tham chiếu

Với thuộc tính của ứng dụng, ưu tiên tên dạng chữ thường và kebab-case, chẳng hạn `${demo.retry-count:3}`. Spring Boot khuyến nghị dạng này để hỗ trợ việc đối chiếu tên thuộc tính.

Đừng suy đoán tên biến môi trường chỉ bằng cách thêm dấu gạch dưới. Theo quy tắc canonical của Boot, `demo.retry-count` tương ứng với `DEMO_RETRYCOUNT`: dấu chấm đổi thành gạch dưới, dấu gạch ngang bị bỏ.

Một alias viết tường minh như `${REQUEST_LIMIT:20}` lại có nghĩa ứng dụng chủ động tìm key `REQUEST_LIMIT`; tên này là một phần hợp đồng cấu hình của ví dụ, không phải tên tự sinh từ `demo.limit`.

## 2. Placeholder được resolve sau khi chọn nguồn phù hợp

Giả sử cấu hình đang có:

```yaml
demo:
  limit: "${REQUEST_LIMIT:20}"
```

Để hiểu `demo.limit`, cần phân biệt hai bước:

1. Tìm giá trị có hiệu lực cho key `demo.limit` theo các nguồn cấu hình và độ ưu tiên.
2. Nếu giá trị được chọn chứa placeholder, resolve các tham chiếu bên trong.

Ví dụ các trường hợp độc lập:

| Nguồn đầu vào | `demo.limit` mà consumer nhận |
| --- | --- |
| YAML trên, không có `REQUEST_LIMIT` | `20` |
| YAML trên và `REQUEST_LIMIT=35` | `35` |
| YAML trên, `REQUEST_LIMIT=35`, đồng thời có env `DEMO_LIMIT=50` | `50` theo độ ưu tiên nguồn Boot thông thường |
| Có tham số `--demo.limit=70` và không có nguồn đặc biệt cao hơn | `70` |

Trong trường hợp `DEMO_LIMIT=50`, nguồn biến môi trường đã cung cấp trực tiếp key logic `demo.limit`; ứng dụng không cần dùng biểu thức YAML để suy ra `35`.

Fallback của placeholder không phải một property source mới, cũng không có quyền ưu tiên cao hơn các nguồn khác. Nó là một nhánh dự phòng tại nơi biểu thức đó được resolve.

### Fallback không tự tìm “giá trị hợp lệ tiếp theo”

Nếu nguồn có ưu tiên cao cung cấp một chuỗi rỗng hoặc một chuỗi sai kiểu, Spring không mặc nhiên bỏ qua nó để tìm giá trị đẹp hơn ở nguồn thấp hơn.

Tương tự, nếu đọc ConfigMap thất bại do RBAC hoặc không tìm thấy thư mục import bắt buộc, ứng dụng có thể lỗi trước khi đến bước resolve placeholder. Viết `:20` không sửa được lỗi truy cập hay lỗi thiết lập nguồn.

## 3. Thiếu, rỗng và sai kiểu có hành vi khác nhau

Xét:

```yaml
demo:
  banner: "${DISPLAY_LABEL:guest}"
  limit: "${REQUEST_LIMIT:20}"
```

| Đầu vào | Kết quả resolve hoặc sử dụng |
| --- | --- |
| Không có `DISPLAY_LABEL` | `banner` dùng `guest` |
| `DISPLAY_LABEL=""` | `banner` là chuỗi rỗng |
| `DISPLAY_LABEL="   "` | `banner` chứa khoảng trắng |
| Không có `REQUEST_LIMIT` | Giá trị dự phòng là `20` |
| `REQUEST_LIMIT=abc` và consumer yêu cầu `int` | Chuyển kiểu thất bại |
| `REQUEST_LIMIT=0` và consumer yêu cầu số dương | Chuyển kiểu thành công, kiểm tra nghiệp vụ phải từ chối |

Placeholder mặc định không có ý nghĩa “dùng fallback nếu chuỗi trống hoặc sai”. Bạn phải thiết kế validation hoặc chuẩn hóa riêng nếu hợp đồng cấu hình yêu cầu xử lý chuỗi trống như giá trị vắng mặt.

Không sao chép cú pháp shell Bash `${NAME:-guest}` để kỳ vọng cùng hành vi trong Spring. Với cú pháp placeholder Spring thông thường, phần sau dấu `:` là fallback; dấu `-` có thể trở thành một ký tự của giá trị dự phòng.

### Placeholder lồng nhau

```yaml
demo:
  owner: "${PRIMARY_OWNER:${TEAM_OWNER:unassigned}}"
```

Đây là chuỗi ưu tiên tường minh: `PRIMARY_OWNER`, rồi `TEAM_OWNER`, rồi `unassigned`. Nếu `PRIMARY_OWNER` có giá trị rỗng, nó vẫn có thể chặn việc dùng `TEAM_OWNER`.

Giữ chuỗi tham chiếu ngắn và có thể lần ngược. Tránh tự tham chiếu hoặc vòng lặp:

```yaml
demo:
  first: "${demo.second}"
  second: "${demo.first}"
```

Không có điểm kết thúc cho việc resolve hai thuộc tính trên. Thêm fallback vào một chỗ không có nghĩa mọi vòng tham chiếu đã được loại bỏ.

## 4. Kubernetes lưu dữ liệu, Spring resolve placeholder

Một ConfigMap có thể chứa nguyên văn:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: placeholder-example
data:
  application.yaml: |-
    demo:
      banner: "${DISPLAY_LABEL:from-config-default}"
```

Kubernetes lưu chuỗi và có thể mount chuỗi đó thành tệp. Việc thay `${DISPLAY_LABEL:...}` bằng giá trị là công việc của Spring khi tài liệu được nạp và thuộc tính được sử dụng.

Chỉ có key tên `application.yaml` trong ConfigMap chưa đủ để Spring đọc được nó. Cần một đường phân phối và nạp cấu hình:

| Cách triển khai | Việc cần thiết trước khi placeholder có thể được dùng |
| --- | --- |
| Mount ConfigMap thành tệp | Mount đúng đường dẫn và cho Spring Boot tìm hoặc import tệp |
| ConfigMap qua Spring Cloud Kubernetes API | Có starter, import cấu hình, chọn nguồn và RBAC phù hợp |
| Secret thành volume cấu hình | Mount, quyền đọc tệp và cơ chế nạp như configtree hoặc import tệp |
| Giá trị qua env | Container phải nhận được biến môi trường tương ứng |

Spring Cloud Kubernetes dùng `spring.config.import: "kubernetes:"` cho cơ chế Config Data; đây là bước nạp nguồn, không phải một dạng cú pháp placeholder khác. [Kubernetes PropertySource implementations](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config.html).

### Phân biệt các lớp biểu thức

| Cú pháp | Thành phần xử lý thường gặp |
| --- | --- |
| `${demo.label:guest}` | Placeholder của Spring khi đi qua bộ resolve cấu hình |
| `#{...}` trong `@Value` | Spring Expression Language |
| `$(VAR_NAME)` trong vị trí Kubernetes hỗ trợ | Kubernetes mở rộng tham chiếu biến theo quy tắc của nó |
| `${NAME:-guest}` trong script Bash | Shell thực thi script đó |

Không coi mọi chuỗi có dấu dollar trong manifest là biểu thức Spring hoặc shell. Ví dụ, `kubectl apply` thông thường không tự thay tất cả `${...}` trong nội dung ConfigMap bằng biến của terminal. Một công cụ render hoặc script bên ngoài có thể xử lý trước, nhưng đó là một bước riêng.

Kubernetes cũng có cơ chế env reference của riêng nó, với cú pháp và phạm vi hỗ trợ khác Spring. [Khai báo biến môi trường cho container](https://kubernetes.io/docs/tasks/inject-data-application/define-environment-variable-container/).

## 5. Lab: quan sát fallback, chuỗi rỗng và lỗi chuyển kiểu

Lab dùng một ứng dụng Spring Boot web tối thiểu và ConfigMap được mount. Không cần gọi Kubernetes API từ tiến trình Java. Bạn cần cluster lab, quyền tạo Namespace/ConfigMap/Deployment và một image thực chứa ứng dụng.

Các tên tệp bên dưới là tệp người học tạo khi thực hành. Image không nên đặt sẵn các biến thử nghiệm `DISPLAY_LABEL`, `REQUEST_LIMIT` hoặc `DEMO_BANNER`.

### 5.1. Ứng dụng quan sát

Dependency web, với version do Spring Boot parent/BOM quản lý:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

Tệp `src/main/resources/application.yaml`:

```yaml
spring:
  application:
    name: placeholder-demo
```

Tệp `PlaceholderDemoApplication.java`:

```java
package com.example.placeholder;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PlaceholderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PlaceholderDemoApplication.class, args);
    }
}
```

Tệp `PlaceholderViewController.java` trong cùng package:

```java
package com.example.placeholder;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PlaceholderViewController {

    private final String banner;
    private final int limit;
    private final String clientTag;
    private final Environment environment;

    public PlaceholderViewController(
            @Value("${demo.banner:consumer-default}") String banner,
            @Value("${demo.limit:20}") int limit,
            @Value("${demo.client-tag:from-injection}") String clientTag,
            Environment environment) {
        if (limit < 1) {
            throw new IllegalArgumentException("demo.limit must be positive");
        }
        this.banner = banner;
        this.limit = limit;
        this.clientTag = clientTag;
        this.environment = environment;
    }

    @GetMapping("/lab/placeholders")
    public Map<String, Object> view() {
        return Map.of(
                "banner", banner,
                "limit", limit,
                "clientTag", clientTag,
                "clientTagInEnvironment",
                environment.getProperty("demo.client-tag", "<absent>")
        );
    }
}
```

Constructor nhận chuỗi đã resolve và `int` đã chuyển kiểu. Điều kiện số dương được kiểm tra riêng, không được suy ra từ việc có fallback `20`.

Các thuộc tính trong endpoint đều là dữ liệu lab không nhạy cảm. Không mở rộng endpoint để trả token hoặc toàn bộ môi trường.

### 5.2. Namespace, ConfigMap và Deployment

Tệp `namespace.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: placeholder-lab
```

Tệp `configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: placeholder-demo-files
  namespace: placeholder-lab
data:
  application.yaml: |-
    demo:
      banner: "${DISPLAY_LABEL:from-config-default}"
      limit: "${REQUEST_LIMIT:20}"
```

Tệp `deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: placeholder-demo
  namespace: placeholder-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: placeholder-demo
  template:
    metadata:
      labels:
        app: placeholder-demo
    spec:
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: app
          image: registry.example.com/training/placeholder-demo:1.0
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_CONFIG_ADDITIONAL_LOCATION
              value: "file:/etc/placeholder-demo/"
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
          volumeMounts:
            - name: configuration
              mountPath: /etc/placeholder-demo
              readOnly: true
      volumes:
        - name: configuration
          configMap:
            name: placeholder-demo-files
```

Thay image minh họa bằng image thật của bạn, chạy được với UID 10001 và có thể được cluster kéo về. Thư mục bổ sung kết thúc bằng `/` để Spring Boot tìm tệp cấu hình bên trong.

Lab này đọc volume, nên không cấp token ServiceAccount cho Java. Nếu thêm tính năng Spring Cloud Kubernetes gọi API như DiscoveryClient hoặc nạp ConfigMap qua API, phải thiết kế xác thực và RBAC riêng cho biến thể đó.

### 5.3. Quan sát giá trị mặc định

Sau khi chuẩn bị image thực, chạy trong môi trường lab:

```shell
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
kubectl apply -f deployment.yaml
kubectl -n placeholder-lab rollout status deployment/placeholder-demo --timeout=180s
kubectl -n placeholder-lab get pods -l app=placeholder-demo
```

Đợi ứng dụng khởi tạo HTTP server xong. Mở terminal riêng cho port-forward:

```shell
kubectl -n placeholder-lab port-forward deployment/placeholder-demo 8080:8080
```

Từ terminal khác:

```shell
curl http://localhost:8080/lab/placeholders
```

Với đúng nguồn cấu hình trong lab và không có ghi đè khác, kết quả dự kiến:

```json
{
  "banner": "from-config-default",
  "limit": 20,
  "clientTag": "from-injection",
  "clientTagInEnvironment": "<absent>"
}
```

Ở đây có hai tầng fallback khác nhau:

- `demo.banner` đã tồn tại trong YAML. Biểu thức bên trong dùng fallback `from-config-default` vì thiếu `DISPLAY_LABEL`. Fallback `consumer-default` ở annotation không được dùng.
- `demo.client-tag` chưa tồn tại trong nguồn nào. Annotation cung cấp `from-injection` cho tham số constructor, nhưng không đăng ký một key mới vào `Environment`.

### 5.4. Cấp giá trị thật và cấp giá trị rỗng

Thêm biến môi trường:

```shell
kubectl -n placeholder-lab set env deployment/placeholder-demo DISPLAY_LABEL=cluster-label
kubectl -n placeholder-lab rollout status deployment/placeholder-demo --timeout=180s
```

Kết nối lại port-forward tới Pod mới rồi gọi endpoint; `banner` dự kiến là `cluster-label`.

Tiếp theo, đặt biến bằng chuỗi rỗng:

```shell
kubectl -n placeholder-lab set env deployment/placeholder-demo DISPLAY_LABEL=
kubectl -n placeholder-lab rollout status deployment/placeholder-demo --timeout=180s
```

Sau khi kết nối lại tới Pod mới, `banner` dự kiến là `""`, không phải `from-config-default` hoặc `consumer-default`. Controller của lab chấp nhận banner rỗng nhằm cho thấy hành vi này.

Bỏ biến thử nghiệm để quay về trạng thái thiếu key:

```shell
kubectl -n placeholder-lab set env deployment/placeholder-demo DISPLAY_LABEL-
kubectl -n placeholder-lab rollout status deployment/placeholder-demo --timeout=180s
```

### 5.5. Giá trị có mặt nhưng sai kiểu

Thử:

```shell
kubectl -n placeholder-lab set env deployment/placeholder-demo REQUEST_LIMIT=abc
kubectl -n placeholder-lab get pods -l app=placeholder-demo
```

Pod mới dự kiến lỗi khởi tạo bean vì không chuyển được `abc` thành `int`. Nó không tự dùng lại `20`.

Xem log Pod mới, thay `POD_NEW` bằng tên cụ thể:

```shell
kubectl -n placeholder-lab logs POD_NEW -c app
```

Trong rollout lỗi, Pod cũ có thể vẫn phục vụ. Không dùng response từ Pod cũ để kết luận cấu hình `abc` đã được chấp nhận.

Khôi phục bằng cách bỏ biến:

```shell
kubectl -n placeholder-lab set env deployment/placeholder-demo REQUEST_LIMIT-
kubectl -n placeholder-lab rollout status deployment/placeholder-demo --timeout=180s
```

Nếu thử giá trị `0`, việc chuyển sang số thành công nhưng constructor từ chối vì `demo.limit` phải dương. Hai lỗi này nằm ở hai bước khác nhau.

## 6. Mặc định trong annotation, trong Environment và khi bind

Một hệ thống nên xác định rõ nơi sở hữu giá trị mặc định, thay vì lặp một con số ở nhiều chỗ.

| Cách khai báo | Phạm vi của mặc định |
| --- | --- |
| YAML `demo.limit: 20` | Là giá trị thuộc tính trong một nguồn cấu hình |
| YAML `demo.limit: "${REQUEST_LIMIT:20}"` | Dự phòng trong biểu thức tạo giá trị `demo.limit` |
| `@Value("${demo.limit:20}")` | Dự phòng tại điểm inject này |
| `environment.getProperty("demo.limit", Integer.class, 20)` | Dự phòng của lần gọi API này |
| `@DefaultValue("20")` khi bind constructor | Dự phòng của thuộc tính được bind vào đối tượng cấu hình |

### Environment không tự nhận mặc định từ nơi khác

Ví dụ:

```java
int limit = environment.getProperty("demo.limit", Integer.class, 20);
String token = environment.getRequiredProperty("partner.api-token");
```

Lệnh đầu trả mặc định khi không có key để resolve; lệnh sau yêu cầu có thuộc tính và sẽ lỗi nếu không tìm được. Cả hai không thay thế kiểm tra miền giá trị hoặc yêu cầu chuỗi không rỗng. [PropertyResolver API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/env/PropertyResolver.html).

Nếu hai consumer viết `@Value("${demo.limit:20}")` và `@Value("${demo.limit:30}")`, khi key vắng mặt chúng có thể nhận hai giá trị khác nhau. Đây là một lý do nên gom hợp đồng cấu hình của cùng chức năng vào một nơi.

### DefaultValue cho ConfigurationProperties

Với Spring Boot, một ví dụ constructor binding là:

```java
package com.example.placeholder;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @DefaultValue("20") int batchSize
) {
}
```

Đăng ký kiểu này bằng `@EnableConfigurationProperties(WorkerProperties.class)` trên một lớp cấu hình hoặc bằng configuration property scanning. Khi không có `worker.batch-size`, đối tượng được bind có `batchSize = 20`.

Các điểm cần nhớ:

- `@DefaultValue` chỉ được dùng khi không tìm thấy thuộc tính; thuộc tính tồn tại nhưng rỗng không được mặc nhiên coi là thiếu.
- Giá trị của annotation phải là hằng; nó không hỗ trợ resolve biểu thức placeholder như `${OTHER_SIZE:20}`.
- Mặc định của đối tượng cấu hình không tự được thêm ngược vào `Environment`.

Hai giới hạn đầu được nêu trong [DefaultValue API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/properties/bind/DefaultValue.html). Vì vậy, một chỗ khác dùng `${worker.batch-size}` vẫn cần có nguồn hoặc fallback của chính nó; không thể trông chờ mặc định trong record tự trở thành cấu hình toàn cục.

## 7. Chọn fallback theo hợp đồng vận hành

| Loại cấu hình | Quyết định thường phù hợp |
| --- | --- |
| Nhãn hiển thị không ảnh hưởng nghiệp vụ | Có thể có giá trị mặc định rõ ràng |
| Kích thước lô hoặc timeout | Có thể mặc định nếu giá trị được kiểm tra và phù hợp tải dự kiến |
| Địa chỉ hệ thống chỉ dùng trên máy phát triển | Đặt dự phòng trong cấu hình dev phù hợp |
| Credential bắt buộc | Thiếu hoặc rỗng phải bị phát hiện, không dùng token giả để tiếp tục |
| Định danh tenant hoặc đích xử lý dữ liệu | Yêu cầu khai báo tường minh nếu mặc định có thể chọn sai đối tượng |

Default không nên là cách làm mọi lỗi cấu hình biến mất. Nếu một dependency bắt buộc chưa được cấu hình, việc khởi động thành công bằng một đích sai có thể khó phát hiện hơn lỗi khởi động rõ ràng.

### Thuộc tính bắt buộc và kiểm tra chuỗi rỗng

Một bean ví dụ cho ứng dụng thật:

```java
package com.example.placeholder;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

@Component
public class PartnerAccess {

    private final String apiToken;

    public PartnerAccess(@Value("${partner.api-token}") String apiToken) {
        if (!StringUtils.hasText(apiToken)) {
            throw new IllegalArgumentException(
                    "partner.api-token must not be blank"
            );
        }
        this.apiToken = apiToken;
    }
}
```

Đây là ví dụ bổ sung riêng, không phải bean cần thêm vào lab ở phần 5 khi lab chưa cấp credential. Trong ứng dụng Spring Boot mặc định, khi bean này được khởi tạo, placeholder bắt buộc không resolve được sẽ gây lỗi; nếu giá trị là chuỗi rỗng hoặc chỉ khoảng trắng, kiểm tra trong constructor sẽ từ chối.

Spring Boot cấu hình bộ xử lý placeholder mặc định cho `@Value`. Nếu ứng dụng tự tùy biến cơ chế resolve hoặc dùng Spring thuần, cần xét cấu hình cụ thể. [Using @Value](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html).

Một placeholder nằm trong YAML nhưng chưa được consumer sử dụng không bảo đảm đã được kiểm tra bắt buộc. Hợp đồng cần được thực thi lúc bind, tạo bean hoặc validation ở thời điểm bạn yêu cầu.

Với tập thuộc tính lớn, nên dùng `@ConfigurationProperties` cùng validation để kiểm tra kiểu và ràng buộc có cấu trúc. Cần phân biệt lỗi thiếu giá trị với lỗi chuỗi rỗng, lỗi định dạng và lỗi nghiệp vụ.

### Default theo profile

Ví dụ trong cấu hình dev:

```yaml
partner:
  base-url: "${PARTNER_BASE_URL:http://localhost:9090}"
```

Trong cấu hình prod, có thể yêu cầu cung cấp rõ:

```yaml
partner:
  base-url: "${PARTNER_BASE_URL}"
```

Cần kích hoạt đúng profile và bảo đảm thuộc tính bắt buộc được consumer kiểm tra. Profile chọn tài liệu; placeholder resolve các tham chiếu trong giá trị được chọn. Fallback không tự bật profile và không tự chuyển namespace Kubernetes.

Đừng đưa một fallback dành cho máy phát triển vào tài liệu chung nếu ứng dụng production có thể vô tình dùng nó.

## 8. Placeholder không thay thế cơ chế cập nhật cấu hình

Giá trị inject vào trường `final` của controller lab là giá trị tại lúc tạo bean. Sửa ConfigMap hoặc nguồn tham chiếu về sau không tự ghi lại trường đó.

Khi triển khai với Spring Cloud Kubernetes, cần xem riêng nguồn dữ liệu cập nhật ra sao, có cơ chế refresh hay không và bean/client có thể đổi cấu hình trong tiến trình đang chạy hay không. Configuration Watcher, nếu dùng, vẫn cần cấu hình và quyền phù hợp; cú pháp placeholder không tự tạo ra chức năng theo dõi thay đổi.

Với biến môi trường của container, sửa ConfigMap/Secret nguồn cũng không làm môi trường tiến trình đang chạy tự đổi. Với volume, tệp có thể cập nhật nhưng bean đã giữ giá trị vẫn có vòng đời riêng. [ConfigMap và hành vi cập nhật](https://kubernetes.io/docs/concepts/configuration/configmap/).

Do đó, kiểm tra cả giá trị nguồn và giá trị consumer đang sử dụng, nhất là khi một default từng được dùng lúc khởi động.

## 9. Chẩn đoán theo chuỗi resolve

Khi thấy fallback xuất hiện ngoài dự kiến, hãy lần ngược biểu thức:

1. Xác định key consumer yêu cầu, ví dụ `demo.limit`.
2. Tìm nguồn có hiệu lực cho key đó; nguồn cao hơn có thể bỏ qua hoàn toàn biểu thức trong YAML.
3. Xem giá trị được chọn có tham chiếu key nào khác, ví dụ `REQUEST_LIMIT`.
4. Kiểm tra key tham chiếu có được đưa vào container và có nằm trong nguồn Spring đọc hay không.
5. Phân biệt không tồn tại với tồn tại nhưng rỗng.
6. Kiểm tra bước chuyển kiểu, validation và vòng đời bean.

| Hiện tượng | Nguyên nhân cần xét |
| --- | --- |
| Luôn nhận `20` dù đã đặt biến | Sai tên biến, sai container, key chưa được nạp hoặc đang quan sát Pod cũ |
| Nhận chuỗi rỗng thay vì fallback | Key tồn tại với giá trị rỗng |
| Nhận dấu gạch ngang trước fallback | Đã dùng nhầm cú pháp shell `:-` |
| Ứng dụng lỗi khi nhận `abc` | Fallback không xử lý lỗi chuyển kiểu |
| Consumer có default nhưng Environment báo thiếu | Default nằm tại điểm inject/bind, không phải nguồn toàn cục |
| Có ConfigMap nhưng vẫn thiếu placeholder | Chưa mount/import, chọn sai namespace/tên nguồn hoặc thiếu quyền API |
| Lỗi vòng tham chiếu | Chuỗi placeholder không có điểm kết thúc |
| Pod khởi động nhưng credential không hợp lệ | Có thể đã dùng fallback không phù hợp hoặc thiếu validation |

Kiểm tra bằng thuộc tính không nhạy cảm hoặc mã phiên bản cấu hình. Tránh xuất token, mật khẩu hay toàn bộ biến môi trường chỉ để tìm lỗi tên key.

Một hợp đồng cấu hình tốt nêu được key nào bắt buộc, key nào có fallback, giá trị rỗng có hợp lệ không, kiểu dữ liệu và giới hạn nghiệp vụ là gì. Với Kubernetes, bổ sung đường cấp dữ liệu và cách triển khai lại/refresh để giá trị đã resolve thực sự tới được consumer.
