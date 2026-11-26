# Cấu hình theo profile trong YAML nhiều tài liệu

Trong chương **Profile và ưu tiên** của module **SPRING_CLOUD_KUBERNETES**, một nhu cầu thường gặp là giữ các giá trị chung và các biến thể môi trường trong cùng một nội dung YAML. Ví dụ, `inventory-service` cần timeout khác nhau khi chạy local, production và production trên Kubernetes.

YAML nhiều tài liệu cho phép diễn đạt các biến thể ấy bằng dấu `---`. Tuy nhiên, cần phân biệt ba việc: chia tài liệu YAML, kích hoạt profile và xác định giá trị thắng khi nhiều nguồn cùng khai báo một thuộc tính.

Bài này dùng cú pháp `spring.config.activate.on-profile` của Spring Boot với Config Data. Phần đọc ConfigMap qua API được đối chiếu với Spring Cloud Kubernetes **5.1.0**. Khi áp dụng, chọn Spring Boot, Spring Cloud và starter theo bộ phiên bản tương thích của dự án; không suy ra phiên bản dự án từ các ví dụ.

## 1. Một file vật lý, nhiều tài liệu logic

Một file `application.yaml` có thể chứa nhiều tài liệu YAML:

```yaml
inventory:
  client:
    timeout: 2s
---
spring:
  config:
    activate:
      on-profile: "dev"
inventory:
  client:
    timeout: 5s
```

Có hai tài liệu:

- Tài liệu đầu không có điều kiện profile, cung cấp giá trị chung.
- Tài liệu sau chỉ được chọn khi điều kiện `dev` khớp.

Khi profile `dev` hoạt động, timeout trong ví dụ là `5s`. Khi `dev` không hoạt động và không có nguồn khác ghi đè, timeout là `2s`.

Dấu `---` tự nó chỉ tách tài liệu. Nó không mang nghĩa “phần sau là dev”, không tự tạo profile và không bảo đảm dữ liệu sau nó được Spring sử dụng.

Cũng cần giữ đúng tên thuộc tính. Hai tài liệu cùng khai báo `inventory.client.timeout` là hai ứng viên cho cùng một cấu hình; chúng không tạo ra hai HTTP client riêng.

## 2. Ví dụ đầy đủ: phần chung, dev, prod và prod trên Kubernetes

Nội dung `application.yaml` minh họa:

```yaml
spring:
  application:
    name: inventory-service

inventory:
  client:
    base-url: "http://localhost:8091"
    timeout: 2s
  audit-enabled: false

---
spring:
  config:
    activate:
      on-profile: "dev"

inventory:
  client:
    timeout: 5s

---
spring:
  config:
    activate:
      on-profile: "prod"

inventory:
  client:
    base-url: "https://inventory.example"
    timeout: 800ms
  audit-enabled: true

---
spring:
  config:
    activate:
      on-profile: "prod & kubernetes"

inventory:
  client:
    base-url: "http://inventory-api:8080"
    timeout: 500ms
```

`inventory.*` là các thuộc tính nghiệp vụ do ứng dụng tự định nghĩa. Ứng dụng cần bind và sử dụng chúng; viết `timeout` trong YAML không tự cấu hình mọi HTTP client.

Các địa chỉ là minh họa. `inventory-api` giả định có Service phù hợp với cách phân giải DNS của Pod, không phải bằng chứng Service đã tồn tại.

### Những tài liệu nào được chọn?

| Profile hoạt động | Tài liệu được chọn | Base URL dự kiến | Timeout dự kiến | Audit |
| --- | --- | --- | --- | --- |
| Không khai báo profile riêng | Chung | `http://localhost:8091` | `2s` | `false` |
| `dev` | Chung, dev | `http://localhost:8091` | `5s` | `false` |
| `prod` | Chung, prod | `https://inventory.example` | `800ms` | `true` |
| `prod,kubernetes` | Chung, prod, prod & kubernetes | `http://inventory-api:8080` | `500ms` | `true` |
| `dev,prod` | Chung, dev, prod | `https://inventory.example` | `800ms` | `true` |

Bảng giả định chỉ có nội dung minh họa quyết định các khóa này và không có nguồn khác ghi đè. Khi không có profile được khai báo tường minh, Spring vẫn có cơ chế default profile; không nên hiểu hàng đầu là Spring hoàn toàn không có khái niệm profile.

Ở hàng `prod,kubernetes`:

1. Phần chung cung cấp mọi giá trị ban đầu.
2. Tài liệu `prod` thay URL, timeout và audit.
3. Tài liệu cuối thay URL và timeout.
4. Audit vẫn là `true` vì tài liệu cuối không khai báo lại khóa đó.

Tài liệu có điều kiện không phải một bản cấu hình độc lập bắt buộc khai báo lại toàn bộ cây. Những khóa không bị thay vẫn có thể được phân giải từ phần chung hoặc nguồn khác.

Việc `dev` và `prod` cùng hoạt động là hợp lệ về mặt biểu thức nhưng thường không phải ý định triển khai. Không dùng tên profile để giả định hai môi trường tự loại trừ nhau.

## 3. Hiểu đúng quy tắc “tài liệu sau thắng”

Với file do **Spring Boot Config Data** xử lý, các tài liệu được xét theo thứ tự trong file; tài liệu được kích hoạt ở phía sau có thể ghi đè khóa từ tài liệu trước. Xem [Working With Multi-Document Files](https://docs.spring.io/spring-boot/4.0/reference/features/external-config.html#features.external-config.files.multi-document).

Trong ví dụ, tài liệu `prod & kubernetes` không thắng vì biểu thức của nó “cụ thể hơn”. Nó thắng các khóa trùng vì nằm sau các tài liệu phù hợp khác trong cách bố trí này.

Nếu đưa tài liệu `prod` xuống sau tài liệu `prod & kubernetes`, timeout `800ms` của `prod` có thể thắng timeout `500ms`. Không có quy tắc tự xếp biểu thức có nhiều điều kiện lên trên biểu thức ít điều kiện.

### Phạm vi của nhận định trên

Có hai thứ tự khác nhau:

| Phạm vi | Câu hỏi cần giải quyết |
| --- | --- |
| Bên trong một nội dung YAML | Những tài liệu nào khớp và được kết hợp theo cách nào? |
| Giữa các PropertySource | Giá trị từ file, import, môi trường hay command line có ưu tiên cao hơn? |

Một dòng YAML nằm cuối file không tự thắng biến môi trường hoặc command line.

Ngoài ra, không nên giả định mọi loader đều xử lý nhiều tài liệu giống hệt Spring Boot. Trong Spring Cloud Kubernetes 5.1.0, lớp [ProfileActivationAwareYamlPropertiesFactoryBean](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v5.1.0/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/config/ProfileActivationAwareYamlPropertiesFactoryBean.java) của đường đọc API tách tài liệu chung và tài liệu có điều kiện profile, rồi áp dụng phần chung trước phần có điều kiện.

Vì vậy, không dựa vào thủ thuật đưa một tài liệu chung xuống cuối để ghi đè profile khi chuyển giữa loader API và file do Boot nạp. Bố trí **phần chung trước, phần theo profile sau** như ví dụ giúp ý định rõ ràng và tránh phụ thuộc vào khác biệt này.

Thứ tự `dev,prod` trong danh sách profile không phải quy tắc tổng quát để đảo thứ tự những tài liệu bên trong cùng YAML. Với hai tài liệu profile của ví dụ, tài liệu `prod` vẫn nằm sau `dev`. Đừng suy rộng nhận định này sang thứ tự các file `application-dev.yaml`, `application-prod.yaml` hoặc các nguồn import khác.

## 4. Kích hoạt profile và đặt điều kiện cho tài liệu

Hai thuộc tính có vai trò khác nhau:

| Thuộc tính | Vai trò |
| --- | --- |
| `spring.profiles.active` | Yêu cầu kích hoạt những profile được chỉ định |
| `spring.config.activate.on-profile` | Điều kiện để chọn một tài liệu cấu hình |

Ví dụ:

```yaml
spring:
  config:
    activate:
      on-profile: "prod"
```

Đoạn trên có nghĩa “chọn tài liệu này khi prod khớp”. Nó không có nghĩa “hãy bật prod”.

### Kích hoạt khi chạy ứng dụng

Với ứng dụng demo đã được đóng gói và dùng `application.yaml` ở mục 2:

```powershell
java -jar inventory-service.jar --spring.profiles.active=dev
java -jar inventory-service.jar --spring.profiles.active=prod,kubernetes
```

Đây là hai lần chạy thay thế nhau để so sánh, không phải yêu cầu chạy đồng thời.

Trong phần cấu hình container của Deployment:

```yaml
env:
  - name: SPRING_PROFILES_ACTIVE
    value: "prod,kubernetes"
```

Fragment này nằm trong container đích, không phải ở `metadata` của Deployment.

Namespace tên `prod`, label `environment=prod` hay tên ConfigMap có hậu tố `-prod` không tự kích hoạt Spring profile `prod`. Cũng không có quy tắc chung rằng chạy trong Kubernetes sẽ tự kích hoạt một Spring profile có tên `kubernetes`.

Spring Boot có điều kiện riêng `on-cloud-platform` cho tài liệu do Config Data xử lý. Điều kiện nền tảng và tên Spring profile là hai cơ chế khác nhau; khả năng hỗ trợ của một loader đọc nội dung từ xa cần được kiểm tra riêng.

### Không tạo vòng kích hoạt bên trong tài liệu có điều kiện

Với Config Data của Spring Boot, `spring.profiles.active` và `spring.profiles.default` chỉ được đặt trong tài liệu không theo profile. `spring.profiles.include` và định nghĩa profile group cũng cần tuân theo giới hạn tương ứng. Xem [Profiles](https://docs.spring.io/spring-boot/4.0/reference/features/profiles.html).

Không viết:

```yaml
# Minh họa cấu hình không hợp lệ với Spring Boot Config Data.
spring:
  config:
    activate:
      on-profile: "prod"
  profiles:
    active: "kubernetes"
```

Nếu cần một tập profile đi cùng nhau, có thể đặt group trong phần chung:

```yaml
spring:
  profiles:
    group:
      production:
        - prod
        - kubernetes
```

Sau đó kích hoạt `production` tại nơi khởi chạy. Không đặt định nghĩa group này vào chính một tài liệu có điều kiện profile.

Đối với ví dụ ConfigMap qua API ở phần sau, profile được cung cấp từ môi trường khởi động. Cách đó giúp loader biết tập profile cần dùng trước khi lựa chọn dữ liệu của ConfigMap.

## 5. Biểu thức profile và kiểu dữ liệu cần chú ý

Có thể dùng biểu thức rõ ràng:

| Giá trị `on-profile` | Điều kiện |
| --- | --- |
| `"dev"` | Profile dev khớp |
| `"prod & kubernetes"` | Cả prod và kubernetes cùng khớp |
| `"prod | staging"` | Ít nhất một trong prod hoặc staging khớp |
| `"!prod"` | Prod không khớp |

`"!prod"` bao gồm mọi trường hợp không có prod; nó không đồng nghĩa “chỉ dành cho dev”.

Khi kết hợp `&` và `|`, dùng ngoặc để xác định nhóm, ví dụ `"(prod | staging) & kubernetes"`. Quy tắc biểu thức được mô tả trong [Spring Framework Profiles](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/Profiles.html).

Nên viết biểu thức trong dấu nháy để giữ nó là một chuỗi YAML rõ ràng. Đặc biệt, đừng để `!` hoặc `&` ở đầu giá trị bị hiểu theo cú pháp khác của YAML.

### Danh sách không tự nối thêm giữa các profile

Với cấu hình được Spring Boot bind thành `List`, một danh sách có ưu tiên cao hơn thay thế danh sách thấp hơn, thay vì tự nối phần tử. Ví dụ độc lập với mục 2:

```yaml
inventory:
  regions:
    - north
    - central
---
spring:
  config:
    activate:
      on-profile: "dev"
inventory:
  regions:
    - sandbox
```

Khi dev hoạt động, danh sách dự kiến là `[sandbox]`, không phải `[north, central, sandbox]`. Xem [Merging Complex Types](https://docs.spring.io/spring-boot/4.0/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.merging-complex-types).

Khi chuyển nội dung sang một loader khác, cần xác nhận cách loader đó kết hợp cấu trúc và tạo PropertySource. Với cấu hình chứa danh sách, nên khai báo đầy đủ danh sách mong muốn ở phần override để ý định dễ kiểm tra.

Các giá trị như `800ms` và `2s` chỉ trở thành thời lượng khi thành phần sử dụng hoặc cơ chế binding xử lý chúng theo kiểu phù hợp. YAML nhiều tài liệu quyết định giá trị cấu hình được chọn; nó không tự xác nhận timeout đã được HTTP client áp dụng.

## 6. Đặt YAML nhiều tài liệu trong một ConfigMap

Có hai lớp YAML cần phân biệt:

1. YAML của resource Kubernetes, gồm `apiVersion`, `kind`, `metadata` và `data`.
2. Chuỗi YAML ứng dụng được lưu bên trong một giá trị của `data`.

Ví dụ dùng một khóa file mang tên ứng dụng:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: inventory-settings
  namespace: training
data:
  inventory-service.yaml: |-
    inventory:
      client:
        base-url: "http://localhost:8091"
        timeout: 2s
      audit-enabled: false

    ---
    spring:
      config:
        activate:
          on-profile: "dev"
    inventory:
      client:
        timeout: 5s

    ---
    spring:
      config:
        activate:
          on-profile: "prod"
    inventory:
      client:
        base-url: "https://inventory.example"
        timeout: 800ms
      audit-enabled: true

    ---
    spring:
      config:
        activate:
          on-profile: "prod & kubernetes"
    inventory:
      client:
        base-url: "http://inventory-api:8080"
        timeout: 500ms
```

Kubernetes lưu `data.inventory-service.yaml` như một chuỗi. Nó không tự chọn tài liệu `prod` dựa trên namespace hoặc label. Cách lưu dữ liệu dạng file trong ConfigMap được trình bày tại [ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/).

Dấu `---` bên trong block `|-` được thụt lề cùng nội dung chuỗi. Sau khi lấy chuỗi hoặc mount thành file, nó trở thành dấu tách tài liệu của YAML ứng dụng.

Ngược lại, một dấu `---` ở cấp ngoài cùng của manifest có thể tách hai resource Kubernetes. Đặt sai cấp sẽ làm thay đổi ý nghĩa cấu trúc, không chỉ làm khác cách trình bày.

Dùng block literal `|` hoặc `|-` để giữ xuống dòng. Không thay bằng block folded `>` khi nội dung cần giữ cấu trúc YAML và dấu tách tài liệu.

### Đường A: Spring Cloud Kubernetes đọc ConfigMap qua API

Các điều kiện của ví dụ:

- Có starter Config tương thích, chẳng hạn `spring-cloud-starter-kubernetes-fabric8-config` theo BOM phù hợp.
- Client xác thực được với Kubernetes API.
- ServiceAccount có quyền phù hợp với request mà client/phiên bản thực sự thực hiện.
- Namespace `training` và ConfigMap `inventory-settings` đã tồn tại.
- Profile được cung cấp từ môi trường khởi động.

Cấu hình được đóng gói trong ứng dụng để loader biết phải tìm nguồn nào:

```yaml
spring:
  application:
    name: inventory-service
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      config:
        enabled: true
        name: inventory-settings
        namespace: training
        include-profile-specific-sources: false
        use-name-as-prefix: false
      secrets:
        enabled: false
      discovery:
        enabled: false
```

Cấu hình container:

```yaml
env:
  - name: SPRING_PROFILES_ACTIVE
    value: "prod,kubernetes"
```

Hai fragment trên minh họa cấu hình ứng dụng và container, không phải một Deployment hoàn chỉnh. Không đặt duy nhất tên nguồn hoặc cấu hình import bên trong chính ConfigMap chưa được tìm thấy.

Các tên trong ví dụ có vai trò khác nhau:

| Giá trị | Vai trò |
| --- | --- |
| `inventory-service` | `spring.application.name` |
| `inventory-settings` | Tên resource ConfigMap |
| `inventory-service.yaml` | Khóa dữ liệu chứa YAML, phù hợp tên ứng dụng |
| `prod`, `kubernetes` | Các Spring profile hoạt động |

`include-profile-specific-sources: false` tránh việc tìm thêm resource có tên theo profile trong ví dụ. Nó không có nghĩa tắt việc xét `on-profile` bên trong chuỗi YAML.

`use-name-as-prefix: false` giúp các khóa vẫn được dùng dưới dạng `inventory.client.timeout`. Nếu bật prefix theo nguồn, cần kiểm tra lại tên thuộc tính mà ứng dụng đọc.

Tài liệu [Using a ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html) mô tả cách chọn resource và xử lý khóa YAML. Cơ chế matcher 5.1.0 đối chiếu `on-profile` với tập profile của môi trường nằm trong [PropertySourceUtils](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v5.1.0/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/config/PropertySourceUtils.java).

Không kết hợp Config Data import với legacy bootstrap để nạp lại cùng một nguồn. Các điều kiện của đường import được mô tả trong [Kubernetes PropertySource implementations](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config.html).

Ví dụ chỉ cần đọc cấu hình. DiscoveryClient, Spring Cloud LoadBalancer, đọc Secret và Configuration Watcher không phải điều kiện để hiểu hay sử dụng các tài liệu profile này.

### Đường B: mount nội dung thành file cho Spring Boot

Có thể dùng cùng ConfigMap để tạo file `application.yaml` và để Spring Boot đọc bằng Config Data. Trong trường hợp này, tiến trình không cần tự gọi ConfigMap API chỉ để đọc file ấy.

Phần bổ sung cho Pod template:

```yaml
spec:
  template:
    spec:
      containers:
        - name: inventory-service
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "prod,kubernetes"
            - name: SPRING_CONFIG_ADDITIONAL_LOCATION
              value: "file:/etc/inventory-config/"
          volumeMounts:
            - name: inventory-config
              mountPath: /etc/inventory-config
              readOnly: true
      volumes:
        - name: inventory-config
          configMap:
            name: inventory-settings
            items:
              - key: inventory-service.yaml
                path: application.yaml
```

Đây cũng là fragment, cần tích hợp vào Deployment đã có. `SPRING_CONFIG_ADDITIONAL_LOCATION` bổ sung thư mục cấu hình; dấu `/` cuối chỉ rõ đây là thư mục cần tìm file cấu hình.

Ở đường này, ứng dụng nhận được file `/etc/inventory-config/application.yaml`. Tên khóa ban đầu trong ConfigMap không còn là tên mà Boot phải tự suy ra vì `items.path` đã ánh xạ rõ.

Khi thực hành đường B, không giữ import `kubernetes:` chỉ để nạp lại chính dữ liệu này. So sánh hai đường trên từng cấu hình độc lập giúp tránh tạo thêm nguồn trùng khóa mà không chủ đích.

Đưa cả chuỗi YAML vào một biến môi trường bằng `envFrom` không tự yêu cầu Spring phân tích chuỗi đó thành các tài liệu và khóa nghiệp vụ. Cần chọn một cơ chế nạp nội dung được hỗ trợ.

## 7. Phần theo profile vẫn chịu ưu tiên của nguồn cấu hình

Với đường API sử dụng Config Data import, giá trị nhập có ưu tiên cao hơn tài liệu khai báo import. Nguồn có ưu tiên cao hơn như biến môi trường và command line vẫn có thể thay giá trị từ import. Xem [Property source precedence](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config.html#_property_source_precedence).

Xét `prod,kubernetes` đang hoạt động và không có nguồn ngoài nào khác:

```text
inventory.client.timeout = 500ms
```

Nếu container có thêm:

```yaml
env:
  - name: SPRING_PROFILES_ACTIVE
    value: "prod,kubernetes"
  - name: INVENTORY_CLIENT_TIMEOUT
    value: "300ms"
```

thì giá trị hiệu lực dự kiến là `300ms`.

Với ứng dụng demo dùng Config Data thông thường và command-line properties vẫn được bật:

```powershell
java -jar inventory-service.jar --spring.profiles.active=prod,kubernetes --inventory.client.timeout=250ms
```

Giá trị command line `250ms` có ưu tiên cao hơn file/import và biến môi trường trong ví dụ.

| Điều kiện | Timeout dự kiến |
| --- | --- |
| Chỉ các tài liệu ở mục 2, active `prod,kubernetes` | `500ms` |
| Thêm biến môi trường `INVENTORY_CLIENT_TIMEOUT=300ms` | `300ms` |
| Thêm command line `--inventory.client.timeout=250ms` | `250ms` |

Các giá trị khác vẫn được phân giải theo nguồn riêng của từng khóa. Không phải toàn bộ tài liệu `prod & kubernetes` bị loại chỉ vì một khóa timeout bị ghi đè.

Nếu triển khai có thêm file theo profile, nhiều ConfigMap, Config Server, nguồn Secret hoặc mã tùy biến PropertySource, cần tính cả các nguồn đó. Bảng trên không thay thế việc kiểm tra môi trường thực tế.

Không dùng nhận định “ConfigMap luôn thắng local” như một quy tắc độc lập với cơ chế nạp. Config Data và legacy bootstrap có cách tổ chức nguồn khác nhau.

## 8. Kiểm chứng bằng các khóa cấu hình không nhạy cảm

Có thể đặt lớp sau trong package được ứng dụng Spring quét:

```java
import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class ProfileConfigurationReport {

    @Bean
    ApplicationRunner reportProfileConfiguration(Environment environment) {
        return args -> {
            System.out.println(
                    "activeProfiles=" +
                    Arrays.toString(environment.getActiveProfiles()));

            String[] keys = {
                    "inventory.client.base-url",
                    "inventory.client.timeout",
                    "inventory.audit-enabled"
            };

            for (String key : keys) {
                System.out.println(key + "=" + environment.getProperty(key));
            }
        };
    }
}
```

Đoạn này đọc đúng ba khóa demo đã biết không chứa credential. Nó không dump toàn bộ `Environment` và không tự expose endpoint quản trị.

Với `prod,kubernetes` hoạt động, không có override ngoài, kết quả dự kiến:

```text
activeProfiles=[prod, kubernetes]
inventory.client.base-url=http://inventory-api:8080
inventory.client.timeout=500ms
inventory.audit-enabled=true
```

Đây là kết quả mong đợi của bài minh họa, không phải kết quả đã chạy trên cluster.

Khi không có active profile tường minh, `getActiveProfiles()` có thể trả mảng rỗng dù cơ chế default profile vẫn tồn tại. Không kết luận ứng dụng lỗi chỉ từ `activeProfiles=[]`.

### Một trình tự kiểm tra có thể giải thích được

1. Xác nhận version và đường nạp: file do Boot đọc hay ConfigMap API.
2. Xác nhận tập profile thực tế từ lần khởi động đang kiểm tra.
3. Xác nhận đúng namespace, ConfigMap, khóa dữ liệu hoặc đường mount.
4. Dựa vào bảng ở mục 2 để xác định những tài liệu phải khớp.
5. Kiểm tra các khóa demo hiệu lực.
6. Nếu giá trị khác dự kiến, tìm nguồn có ưu tiên cao hơn và origin nếu công cụ cung cấp.
7. Kiểm tra thành phần nghiệp vụ thực sự sử dụng cấu hình, chẳng hạn timeout của HTTP client.

Việc đọc trực tiếp ConfigMap chỉ chứng minh dữ liệu resource tồn tại. Nó không chứng minh ứng dụng đã nạp đúng nguồn hoặc sử dụng giá trị từ tài liệu dự kiến.

Nếu dùng Actuator để tìm nguồn, chỉ mở các endpoint cần thiết với kiểm soát truy cập phù hợp. Không đưa Secret, token hoặc cấu hình nhạy cảm vào log hay báo cáo để tìm thứ tự ưu tiên.

## 9. Các lỗi dễ gặp khi viết YAML nhiều tài liệu

| Lỗi hoặc hiện tượng | Nguyên nhân cần xem xét | Hướng xử lý |
| --- | --- | --- |
| Phần prod không được chọn | Chưa kích hoạt prod, sai tên profile hoặc sai khóa activation | Kiểm tra profile hiệu lực và `on-profile` |
| Phần dev cũng áp dụng ngoài dev | Thiếu điều kiện sau dấu `---` | Thêm điều kiện cho đúng tài liệu |
| Cả dev và prod đều có tác động | Hai profile cùng hoạt động | Sửa ý định kích hoạt; không dựa vào tên để loại trừ |
| Khóa cuối file không thắng | Có nguồn khác ưu tiên cao hơn hoặc loader có quy tắc khác | Kiểm tra PropertySource và cơ chế nạp |
| Profile có vẻ đúng nhưng khóa không tồn tại | Sai tên file dữ liệu, prefix, đường mount hoặc ConfigMap chưa nạp | Kiểm tra toàn bộ đường cung cấp |
| YAML lỗi khi thêm một phần Spring mới | Lặp lại cùng khóa mapping trong một tài liệu hoặc sai thụt lề | Gộp cấu trúc trong cùng tài liệu |
| Nội dung trong ConfigMap bị tách thành resource khác | Dấu `---` ra ngoài block chuỗi | Đặt đúng cấp thụt lề của `data` |
| Parser nhận YAML nhưng hành vi activation sai | Dùng cú pháp cũ hoặc loader khác với giả định | Đối chiếu đúng phiên bản và loader |
| Danh sách mất phần tử nền | Danh sách bị thay thế bởi phần override | Khai báo đủ danh sách mong muốn |
| Đã sửa ConfigMap nhưng tiến trình chưa đổi | Chưa có cơ chế nạp lại phù hợp | Chọn rollout hoặc quy trình refresh được hỗ trợ |

Trong một tài liệu, không khai báo hai khóa `spring:` riêng rồi kỳ vọng parser tự gộp. Có thể lặp lại `spring:` ở các tài liệu khác nhau vì chúng được tách bằng `---`.

Các ví dụ cũ có thể dùng `spring.profiles: production` để chọn tài liệu. Với Spring Boot Config Data hiện đại, dùng `spring.config.activate.on-profile` theo [Config Data Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-Config-Data-Migration-Guide). Không trộn cú pháp lịch sử với cú pháp hiện đại mà bỏ qua cách loader xử lý.

Một file YAML hợp lệ về cú pháp cũng chưa đủ. `@PropertySource` thông thường không phải đường nạp hỗ trợ YAML nhiều tài liệu và activation như Config Data. Cần dùng đúng cơ chế cấu hình của ứng dụng.

## 10. Giữ thiết kế profile rõ ràng trong triển khai Kubernetes

Nên đặt phần chung trước, mỗi biến thể có điều kiện rõ ràng và các khóa override có chủ đích. Chỉ tạo thêm một tài liệu khi nó đại diện cho một điều kiện cấu hình cần giải thích.

Profile là cơ chế lựa chọn cấu hình, không phải ranh giới bảo mật. Người có quyền đọc ConfigMap có thể đọc cả chuỗi, kể cả tài liệu production không được chọn trong Pod của họ. Không cất mật khẩu hoặc token trong một phần YAML rồi dựa vào profile để che giấu chúng.

Cũng không xem thay `SPRING_PROFILES_ACTIVE` trong Deployment là cách đổi profile tức thì của mọi tiến trình đang chạy. Việc thay Pod template cần đi qua triển khai instance mới. Với các bean được chọn theo profile, nên xác định tập profile khi tạo ApplicationContext thay vì giả định một thông báo refresh sẽ tổ chức lại toàn bộ ứng dụng.

Configuration Watcher có thể hỗ trợ đường cập nhật cấu hình được thiết kế riêng; nó không thay thế việc xác định profile và cơ chế ưu tiên. DiscoveryClient, LoadBalancer và health check cũng không quyết định tài liệu YAML nào thắng.

Một giá trị cấu hình có thể giải thích được cần trả lời bốn câu hỏi: **nội dung được nạp từ đâu, profile nào đang hoạt động, tài liệu nào khớp và nguồn nào cuối cùng cung cấp giá trị hiệu lực**. Khi trả lời được cả bốn, YAML nhiều tài liệu trở thành cách tổ chức cấu hình có thể kiểm chứng cho cùng một ứng dụng ở nhiều môi trường.
