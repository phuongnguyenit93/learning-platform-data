# Tiền tố thuộc tính để tránh xung đột giữa các nguồn

Một ứng dụng Spring có thể đọc nhiều ConfigMap để lấy cấu hình từ các nhóm khác nhau. Nếu mỗi nhóm đều đặt các khóa ngắn như `base-url`, `timeout` hoặc `enabled`, việc nạp thành công tất cả nguồn chưa bảo đảm ứng dụng còn đọc được riêng từng bộ giá trị.

Trong chương **ConfigMap** của module **Spring Cloud Kubernetes (SPRING_CLOUD_KUBERNETES)**, bài học này giải thích cách đặt tiền tố cho khóa thuộc tính khi đọc ConfigMap qua API. Mục tiêu là để nhiều nhóm cấu hình cùng tồn tại, được bind đúng vào Java và được kiểm tra rõ ràng khi triển khai.

Các ví dụ lấy **Spring Cloud Kubernetes 3.3.3 với client Fabric8** làm mốc, sử dụng Config Data qua `spring.config.import`. Khi áp dụng vào dự án, chọn Spring Boot và Spring Cloud BOM tương thích. Cơ chế nạp qua Config Data và yêu cầu không trộn với bootstrap cũ được trình bày trong [Kubernetes PropertySource implementations](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config.html).

## 1. Xung đột phát sinh ở khóa hiệu lực, không chỉ ở tên ConfigMap

Giả sử dịch vụ đơn hàng cần gọi hai hệ thống:

| Hệ thống | ConfigMap | URL cần dùng | Timeout |
| --- | --- | --- | --- |
| Kho hàng | `inventory-settings` | `http://inventory.prefix-lab.svc.cluster.local` | 2 giây |
| Vận chuyển | `shipping-settings` | `http://shipping.prefix-lab.svc.cluster.local` | 5 giây |

Hai ConfigMap được khai báo như sau:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: inventory-settings
  namespace: prefix-lab
data:
  base-url: "http://inventory.prefix-lab.svc.cluster.local"
  timeout: "2s"
  max-attempts: "3"
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: shipping-settings
  namespace: prefix-lab
data:
  base-url: "http://shipping.prefix-lab.svc.cluster.local"
  timeout: "5s"
  max-attempts: "2"
~~~

Các URL minh họa tên Service trong namespace lab; ví dụ nạp cấu hình không tự tạo các Service hoặc chứng minh chúng đã truy cập được.

Kubernetes cho phép hai đối tượng khác tên có cùng các khóa `data`. Xung đột xuất hiện khi ứng dụng đưa cả hai bộ giá trị vào cùng không gian tên thuộc tính của Spring:

~~~text
inventory-settings: base-url, timeout, max-attempts
shipping-settings:  base-url, timeout, max-attempts

Environment:
  base-url     -> một giá trị hiệu lực
  timeout      -> một giá trị hiệu lực
  max-attempts -> một giá trị hiệu lực
~~~

Một lời gọi `environment.getProperty("base-url")` không chứa thông tin “tôi muốn giá trị từ kho hàng”. Nó chỉ hỏi khóa `base-url` theo thứ tự ưu tiên các nguồn.

Tên ConfigMap khác nhau không mặc nhiên trở thành tiền tố thuộc tính. Namespace Kubernetes khác nhau cũng không tự tách các khóa trong `Environment`.

## 2. Phân biệt giải quyết ghi đè và tách hai nhóm cấu hình

Nếu hai nguồn cùng cung cấp một khóa vì chủ đích muốn nguồn sau ghi đè mặc định, thứ tự ưu tiên là một công cụ phù hợp.

Ví dụ: ConfigMap mặc định có `app.page-size=20`, cấu hình triển khai của môi trường cung cấp `app.page-size=50`. Ứng dụng chỉ cần một giá trị cuối cùng cho cùng một ý nghĩa.

Ngược lại, dịch vụ đơn hàng cần cả URL kho hàng và URL vận chuyển cùng lúc. Chỉ đổi thứ tự nguồn sẽ thay đổi giá trị thắng, không tạo ra hai thuộc tính riêng.

| Ý định | Cách thiết kế |
| --- | --- |
| Một giá trị mặc định được thay thế theo môi trường | Giữ cùng khóa, quy định thứ tự ưu tiên |
| Hai thành phần cần hai giá trị độc lập | Tạo hai đường dẫn thuộc tính khác nhau |
| Hai nguồn có cùng khóa nhưng khác chủ sở hữu | Đặt tiền tố theo vai trò hoặc nguồn |
| Hai nguồn đã dùng các đường dẫn nghiệp vụ khác nhau | Có thể không cần thêm tiền tố của loader |

Với hai nguồn có tên khai báo tường minh trong `config.sources` của phiên bản minh họa, nguồn đứng sau có thể thắng khi khóa trùng. Cách locator thêm PropertySource vào đầu composite thể hiện trong [ConfigMapPropertySourceLocator tại v3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/config/ConfigMapPropertySourceLocator.java).

Ví dụ chưa dùng tiền tố:

~~~yaml
spring:
  cloud:
    kubernetes:
      config:
        namespace: prefix-lab
        include-profile-specific-sources: false
        use-name-as-prefix: false
        sources:
          - name: inventory-settings
          - name: shipping-settings
~~~

Trong phạm vi hai nguồn trên và không có nguồn ưu tiên cao hơn ghi đè, các khóa chung sẽ lấy giá trị của `shipping-settings`. Đây không phải kết quả mong muốn nếu mã gọi kho hàng và mã gọi vận chuyển đều đọc cùng khóa `base-url`.

## 3. Tiền tố biến đổi tên khóa như thế nào?

Về mặt khái niệm, loader biến đổi:

~~~text
khóa hiệu lực = tiền tố + "." + khóa đã đọc
~~~

Ví dụ:

~~~text
tiền tố: clients.inventory
khóa gốc: base-url

khóa hiệu lực: clients.inventory.base-url
~~~

Giá trị URL không bị thay đổi. Tên và namespace của ConfigMap cũng không bị đổi. Đây là phép đổi tên thuộc tính được đưa vào Spring, không phải một lần sửa đối tượng Kubernetes.

~~~mermaid
flowchart LR
    A["inventory-settings: base-url, timeout"] --> B["Tiền tố clients.inventory"]
    C["shipping-settings: base-url, timeout"] --> D["Tiền tố clients.shipping"]
    B --> E["clients.inventory.base-url và clients.inventory.timeout"]
    D --> F["clients.shipping.base-url và clients.shipping.timeout"]
    E --> G["Spring Environment và Binder"]
    F --> G
~~~

Phép ghép tiền tố với đường dẫn khóa được thực hiện trong [SourceDataFlattener tại v3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/config/SourceDataFlattener.java). Vì vậy:

- Không tự thêm dấu `.` ở cuối `explicit-prefix`.
- Không giả định loader loại bỏ một phần tên khóa cũ.
- Không giả định khóa cũ và khóa có tiền tố cùng được tạo ra.
- Cần cập nhật nơi đọc thuộc tính theo tên hiệu lực mới.

Nếu cần đồng thời hai tên để chuyển đổi hệ thống, phải thiết kế việc cung cấp hoặc ánh xạ hai tên một cách tường minh; thêm tiền tố không tự tạo bí danh tương thích.

## 4. Dùng tên ConfigMap làm tiền tố với `use-name-as-prefix`

Một cách nhanh để tách hai nguồn là dùng tên mỗi ConfigMap:

~~~yaml
spring:
  cloud:
    kubernetes:
      config:
        namespace: prefix-lab
        include-profile-specific-sources: false
        use-name-as-prefix: true
        sources:
          - name: inventory-settings
          - name: shipping-settings
~~~

Với các nguồn có tên được ghi rõ như trên, kết quả mong đợi là:

| ConfigMap | Khóa gốc | Khóa hiệu lực |
| --- | --- | --- |
| `inventory-settings` | `base-url` | `inventory-settings.base-url` |
| `inventory-settings` | `timeout` | `inventory-settings.timeout` |
| `inventory-settings` | `max-attempts` | `inventory-settings.max-attempts` |
| `shipping-settings` | `base-url` | `shipping-settings.base-url` |
| `shipping-settings` | `timeout` | `shipping-settings.timeout` |
| `shipping-settings` | `max-attempts` | `shipping-settings.max-attempts` |

Ứng dụng có thể đọc riêng:

~~~java
String inventoryUrl = environment.getRequiredProperty(
        "inventory-settings.base-url");
String shippingUrl = environment.getRequiredProperty(
        "shipping-settings.base-url");
~~~

Điểm thuận tiện là tên nguồn dễ nhìn thấy ngay trong khóa. Đổi lại, mã hoặc hợp đồng cấu hình của ứng dụng bị gắn với tên tài nguyên Kubernetes. Nếu đổi `inventory-settings` thành `inventory-settings-v2` và vẫn dùng tên làm tiền tố, các khóa hiệu lực cũng đổi.

Tài liệu mô tả `useNameAsPrefix` ở mức chung và từng mục nguồn trong [Using a ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config/configmap-propertysource.html). Bài dùng cách viết kebab-case như `use-name-as-prefix` khi cấu hình YAML.

### 4.1. Cho phép một nguồn không thêm tiền tố

Có thể đặt chính sách chung là thêm tên nguồn rồi tắt cho một nguồn cụ thể:

~~~yaml
spring:
  cloud:
    kubernetes:
      config:
        namespace: prefix-lab
        use-name-as-prefix: true
        sources:
          - name: runtime-settings
            use-name-as-prefix: false
          - name: inventory-settings
          - name: shipping-settings
~~~

Thiết lập của từng mục `sources` có ưu tiên hơn lựa chọn chung. Nguồn `runtime-settings` được giữ khóa gốc; hai nguồn còn lại dùng tên ConfigMap.

Đây là một ngoại lệ có chủ đích. Những khóa không có tiền tố vẫn có thể xung đột với các nguồn khác, nên cần quy định rõ chúng thuộc phạm vi nào.

## 5. Dùng `explicit-prefix` để có tên thuộc tính ổn định

Tên tài nguyên thường phản ánh môi trường, quy trình tạo manifest hoặc phiên bản phát hành. Tên mà mã Java cần đọc nên phản ánh vai trò ổn định của cấu hình.

Với ví dụ đang xét:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      config:
        enabled: true
        namespace: prefix-lab
        include-profile-specific-sources: false
        fail-fast: true
        retry:
          enabled: false
        use-name-as-prefix: true
        sources:
          - name: inventory-settings
            explicit-prefix: clients.inventory
          - name: shipping-settings
            explicit-prefix: clients.shipping
      secrets:
        enabled: false
~~~

Đây là cấu hình ứng dụng đầy đủ cho chính sách tiền tố của ví dụ. Nó được dùng cùng hai ConfigMap ở phần 1.

Các lựa chọn tìm nguồn và tiền tố phải có sẵn trước lần đọc ConfigMap, chẳng hạn trong `application.yaml` đóng gói cùng ứng dụng. Không đặt duy nhất chính sách này trong nguồn mà ứng dụng chưa biết phải tìm và đọc ra sao.

Các khóa hiệu lực:

~~~properties
clients.inventory.base-url=http://inventory.prefix-lab.svc.cluster.local
clients.inventory.timeout=2s
clients.inventory.max-attempts=3

clients.shipping.base-url=http://shipping.prefix-lab.svc.cluster.local
clients.shipping.timeout=5s
clients.shipping.max-attempts=2
~~~

`explicit-prefix` chỉ được khai báo ở từng mục `spring.cloud.kubernetes.config.sources`. Không chuyển nó thành `spring.cloud.kubernetes.config.explicit-prefix` rồi kỳ vọng có tác dụng như một tiền tố chung.

Trong mô hình thuộc tính của phiên bản minh họa, `explicitPrefix` thuộc bản ghi `Source`, còn `useNameAsPrefix` tồn tại ở cả cấu hình chung và nguồn. Xem [ConfigMapConfigProperties tại v3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/config/ConfigMapConfigProperties.java).

### 5.1. Thứ tự lựa chọn tiền tố

| `explicit-prefix` của nguồn | `use-name-as-prefix` của nguồn | Lựa chọn chung | Kết quả |
| --- | --- | --- | --- |
| Không đặt | Không đặt | `false` | Giữ khóa gốc |
| Không đặt | Không đặt | `true` | Dùng tên nguồn |
| Không đặt | `false` | `true` | Giữ khóa gốc |
| Không đặt | `true` | `false` | Dùng tên nguồn |
| Có giá trị khác trắng | `false` | Bất kỳ | Dùng tiền tố tường minh |
| Có giá trị khác trắng | `true` | Bất kỳ | Dùng tiền tố tường minh |

Thứ tự là: tiền tố tường minh có nội dung, tiếp đến cờ ở mức nguồn, cuối cùng cờ chung. Chuỗi rỗng không phải cách đáng tin cậy để vô hiệu hóa một chính sách khác; cần bỏ tiền tố tường minh và chọn cờ phù hợp.

Quy tắc này được thể hiện trực tiếp trong `findPrefix` của [ConfigUtils tại v3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/config/ConfigUtils.java).

### 5.2. Đổi tên nguồn mà giữ hợp đồng với ứng dụng

Nếu quy trình triển khai đổi tên ConfigMap:

~~~yaml
sources:
  - name: inventory-settings-v2
    explicit-prefix: clients.inventory
~~~

thì, với cùng dữ liệu gốc, ứng dụng vẫn đọc `clients.inventory.base-url`. Chỉ mục nguồn phải được cập nhật để trỏ đúng tài nguyên mới.

Tiền tố ổn định giúp tách việc chọn tài nguyên khỏi tên thuộc tính nghiệp vụ. Nó không tự làm ConfigMap mới tồn tại, không cấp quyền truy cập và không xác nhận nội dung trong tài nguyên mới là đúng.

## 6. Bind hai nguồn vào một mô hình cấu hình Java

Khi khóa hiệu lực đã có cấu trúc `clients.inventory.*` và `clients.shipping.*`, ứng dụng có thể dùng một lớp cấu hình chứa hai nhánh.

### 6.1. Điều kiện mẫu

Ví dụ dùng Java 17 trở lên, Spring Boot 3.x cùng bộ phiên bản Spring Cloud tương thích với mốc đã nêu. Các dependency cần cho mẫu là:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-fabric8-config</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Đoạn này giả định dự án đã quản lý phiên bản bằng BOM. Bài không cần DiscoveryClient, Spring Cloud LoadBalancer hay Configuration Watcher để chứng minh hai nhóm thuộc tính không xung đột.

### 6.2. Mô hình thuộc tính

~~~java
package example.orders;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "clients")
public record ClientProperties(
        @Valid @NotNull Target inventory,
        @Valid @NotNull Target shipping) {

    public record Target(
            @NotNull URI baseUrl,
            @NotNull Duration timeout,
            @NotNull @Min(1) Integer maxAttempts) {
    }
}
~~~

`@Valid` yêu cầu validation đi vào nhánh con. Kiểu wrapper `Integer` cùng `@NotNull` giúp phát hiện thiếu `max-attempts`, thay vì để một giá trị mặc định primitive làm mờ nguyên nhân.

Hai thuộc tính `inventory` và `shipping` dùng chung cấu trúc `Target` nhưng được bind từ các đường dẫn khác nhau. Cách đặt tên kebab-case của khóa như `base-url` được Spring Boot ánh xạ sang `baseUrl`; Binder cũng chuyển giá trị có đơn vị như `2s` sang `Duration`. Xem [Externalized Configuration của Spring Boot](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html).

Ở đây có hai loại “prefix” khác vai trò:

| Thiết lập | Vai trò |
| --- | --- |
| `explicit-prefix: clients.inventory` | Đổi tên khóa khi đưa nguồn vào Spring |
| `@ConfigurationProperties(prefix = "clients")` | Chọn nhánh thuộc tính để bind vào Java |

Annotation ở Java không tự thêm `clients` vào các khóa đang thiếu tiền tố. Loader cũng không tự biết lớp Java nào cần sử dụng các khóa đã đổi tên.

### 6.3. Đăng ký và quan sát hai bộ giá trị

~~~java
package example.orders;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }

    @Bean
    ApplicationRunner showClientSettings(ClientProperties properties) {
        return args -> {
            ClientProperties.Target inventory = properties.inventory();
            ClientProperties.Target shipping = properties.shipping();

            System.out.printf(
                    "inventory: url=%s, timeout=%s, attempts=%d%n",
                    inventory.baseUrl(),
                    inventory.timeout(),
                    inventory.maxAttempts());

            System.out.printf(
                    "shipping: url=%s, timeout=%s, attempts=%d%n",
                    shipping.baseUrl(),
                    shipping.timeout(),
                    shipping.maxAttempts());
        };
    }
}
~~~

Với đúng hai nguồn ban đầu, đúng tiền tố và không có nguồn khác ghi đè, đầu ra dự kiến:

~~~text
inventory: url=http://inventory.prefix-lab.svc.cluster.local, timeout=PT2S, attempts=3
shipping: url=http://shipping.prefix-lab.svc.cluster.local, timeout=PT5S, attempts=2
~~~

Đây là đầu ra để đối chiếu khi thực hành. URL chuyển được sang `URI` không đồng nghĩa Service đã truy cập được. Tương tự, một URL bị gán nhầm sang nhánh khác vẫn có thể hợp lệ về cú pháp và vượt qua các ràng buộc trên.

Nếu cả hai nhánh là thiết yếu, không đặt sẵn hai URL mặc định giống nhau để che lỗi bind. Hãy để thiếu nhánh hoặc thiếu thuộc tính làm xuất hiện lỗi cấu hình rõ ràng.

## 7. Tiền tố với YAML nhúng và khóa đã có cấu trúc

Có thể thay ConfigMap kho hàng bằng một tài nguyên có một file YAML nhúng:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: inventory-settings
  namespace: prefix-lab
data:
  order-service.yaml: |-
    base-url: "http://inventory.prefix-lab.svc.cluster.local"
    timeout: 2s
    max-attempts: 3
~~~

Với nguồn được nhận diện và tiền tố `clients.inventory`, các thuộc tính sau khi đọc vẫn là:

~~~text
clients.inventory.base-url
clients.inventory.timeout
clients.inventory.max-attempts
~~~

Không phải:

~~~text
clients.inventory.order-service.yaml.base-url
~~~

Tiền tố áp dụng cho các khóa thuộc tính đã được xử lý từ nội dung, không thêm tên file nhúng vào mọi đường dẫn.

Đường xử lý dữ liệu theo tên nguồn và bước chọn cách làm phẳng có thể xem trong [NamedSourceData tại v3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/config/NamedSourceData.java).

### 7.1. Khóa gốc có tiền tố sẵn sẽ được ghép tiếp

Nếu dữ liệu gốc đã là:

~~~yaml
data:
  clients.inventory.base-url: "http://inventory.prefix-lab.svc.cluster.local"
~~~

rồi nguồn vẫn có:

~~~yaml
explicit-prefix: clients.inventory
~~~

thì khóa hiệu lực sẽ thành:

~~~text
clients.inventory.clients.inventory.base-url
~~~

Loader không tự phát hiện và loại bỏ phần trùng. Lớp Java ở phần 6 đang chờ `clients.inventory.base-url` nên sẽ không nhận được giá trị tại đường dẫn mong muốn.

Cần chọn một trong hai hợp đồng:

- Dữ liệu gốc dùng các khóa cục bộ như `base-url`; loader thêm tiền tố.
- Dữ liệu gốc đã có đường dẫn đầy đủ; loader giữ nguyên khóa.

### 7.2. Áp dụng cho cấu trúc con cũng là phép ghép đường dẫn

Nếu file nhúng chứa:

~~~yaml
retry:
  enabled: true
  backoff: 500ms
~~~

và nguồn dùng tiền tố `clients.inventory`, đường dẫn mới là `clients.inventory.retry.enabled` và `clients.inventory.retry.backoff`.

Khi thay đổi cấu trúc gốc, phải cập nhật mô hình Java tương ứng. Tiền tố chỉ quyết định phần đầu của đường dẫn; nó không thay thế việc thiết kế các thuộc tính con.

## 8. Những trường hợp tiền tố chưa đủ để tránh xung đột

### 8.1. Hai nguồn dùng cùng tiền tố tường minh

Ví dụ:

~~~yaml
sources:
  - name: inventory-settings
    explicit-prefix: clients.remote
  - name: shipping-settings
    explicit-prefix: clients.remote
~~~

Cả hai lại tạo ra `clients.remote.base-url` và `clients.remote.timeout`. Khóa hiệu lực vẫn trùng nên thứ tự ưu tiên vẫn phải chọn một giá trị.

Muốn giữ riêng hai bộ dữ liệu, chọn hai nhánh riêng. Nếu cố ý cùng nhánh để ghi đè mặc định, phải ghi rõ đó là thiết kế ghi đè.

### 8.2. Cùng tên ConfigMap ở hai namespace

Giả sử có hai đối tượng đều tên `shared-settings`, một ở namespace kho hàng và một ở namespace vận chuyển. Dùng tên làm tiền tố có thể khiến cả hai cùng tạo khóa `shared-settings.timeout`.

Namespace dùng để chọn tài nguyên không tự xuất hiện trong tiền tố tên nguồn. Khi ứng dụng thực sự cần đọc cả hai, dùng tiền tố tường minh khác nhau và cấp quyền truy cập đúng từng namespace.

### 8.3. Một nguồn không dùng tiền tố khai báo đúng đường dẫn đang được bảo vệ

Một nguồn khác có thể chứa trực tiếp:

~~~yaml
data:
  clients.inventory.timeout: "9s"
~~~

Nếu nguồn đó được nạp không có tiền tố, nó vẫn có thể tham gia cạnh tranh cho khóa `clients.inventory.timeout`.

Thêm tiền tố làm giảm xung đột ngoài ý muốn; nó không khóa quyền ghi đè đường dẫn. Muốn kiểm soát thay đổi còn cần quy ước chủ sở hữu thuộc tính, quản lý nguồn triển khai và RBAC thích hợp.

### 8.4. Biến môi trường hoặc tham số khởi động ghi đè cùng đường dẫn

Spring còn đọc các nguồn ngoài Kubernetes PropertySource. Một tham số khởi động như:

~~~shell
java -jar order-service.jar --clients.inventory.timeout=9s
~~~

có thể làm giá trị hiệu lực khác ConfigMap dù tiền tố của ConfigMap đúng. Vì vậy, khi chẩn đoán cần kiểm tra cả đường dẫn hiệu lực và nguồn nào đang có ưu tiên cao hơn.

Không diễn giải việc “có tiền tố” thành “cấu hình từ nguồn này luôn thắng”.

### 8.5. Nguồn chọn theo label có thể trả về nhiều đối tượng

Một selector label có thể chọn nhiều ConfigMap. Phải tính tới số đối tượng thực tế được chọn và khóa hiệu lực của từng đối tượng; không coi một mục trong danh sách `sources` luôn tương ứng với đúng một ConfigMap.

Trong bài thực hành, danh sách nguồn được khai báo theo tên cụ thể để quan sát rõ phép đổi tên. Khi chuyển sang label, cần kiểm tra quy tắc tiền tố và hành vi của đúng phiên bản/client, đặc biệt nếu nhiều đối tượng có cùng khóa và cùng tiền tố tường minh.

### 8.6. Profile phục vụ ghi đè theo môi trường, không thay cho nhánh nghiệp vụ

Cấu hình nền và cấu hình của profile có thể cùng cung cấp một khóa cho cùng thành phần. Khi đó việc profile ghi đè giá trị nền thường là chủ đích.

Không dùng profile `inventory` và `shipping` như giải pháp chung để giữ hai URL độc lập nếu ứng dụng cần sử dụng cả hai cùng lúc. Ví dụ chính tắt tìm thêm nguồn theo profile để người học chỉ quan sát xung đột và tiền tố của hai ConfigMap đã nêu.

## 9. Đừng làm mất các khóa chuẩn mà Spring Boot cần đọc

Nếu ConfigMap chứa:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: runtime-settings
  namespace: prefix-lab
data:
  server.port: "8080"
~~~

và áp dụng `use-name-as-prefix: true`, ứng dụng sẽ có khóa `runtime-settings.server.port`. Nó không còn là khóa chuẩn `server.port` mà auto-configuration mong đợi.

Một cách thiết kế là chia rõ nguồn cấu hình runtime và nguồn tùy biến của các client:

~~~yaml
spring:
  cloud:
    kubernetes:
      config:
        namespace: prefix-lab
        include-profile-specific-sources: false
        use-name-as-prefix: true
        sources:
          - name: runtime-settings
            use-name-as-prefix: false
          - name: inventory-settings
            explicit-prefix: clients.inventory
          - name: shipping-settings
            explicit-prefix: clients.shipping
~~~

Đây là một biến thể của danh sách nguồn ở phần 5; giữ các cấu hình bật Config Data, fail-fast, retry và Secrets theo ví dụ đầy đủ khi tích hợp.

Trong biến thể này:

| Nguồn | Khóa gốc | Khóa hiệu lực |
| --- | --- | --- |
| Runtime | `server.port` | `server.port` |
| Kho hàng | `timeout` | `clients.inventory.timeout` |
| Vận chuyển | `timeout` | `clients.shipping.timeout` |

Cách tương tự áp dụng khi cân nhắc các khóa chuẩn như `spring.datasource.url`. Chỉ thêm tiền tố khi mã tiêu thụ thực sự được thiết kế để đọc đường dẫn mới.

## 10. Tiền tố không đổi cơ chế truy cập Kubernetes

Để chạy ví dụ API, ứng dụng cần đọc các ConfigMap trong namespace `prefix-lab` bằng đúng ServiceAccount của Pod.

Một mẫu phân quyền cho lab chỉ nạp cấu hình ban đầu:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: prefix-lab
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: order-config-reader
  namespace: prefix-lab
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: order-configmap-reader
  namespace: prefix-lab
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: order-configmap-reader-binding
  namespace: prefix-lab
subjects:
  - kind: ServiceAccount
    name: order-config-reader
    namespace: prefix-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: order-configmap-reader
~~~

Pod template của Deployment cần dùng:

~~~yaml
spec:
  template:
    spec:
      serviceAccountName: order-config-reader
~~~

Đoạn Pod template trên là phần trích để tích hợp vào Deployment ứng dụng. Image, nhãn, container và các cấu hình triển khai khác vẫn phải được cung cấp trong manifest hoàn chỉnh.

Quyền đọc ConfigMap và nhu cầu của từng tính năng Spring Cloud Kubernetes được mô tả trong [Security Configurations Inside Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/security-service-accounts.html). Lab không cấp quyền Secret hay Discovery vì không sử dụng các tính năng ấy.

Đổi `explicit-prefix` không khắc phục lỗi `Forbidden`, timeout API hoặc nhầm namespace. Cần phân biệt lỗi đọc nguồn với lỗi đọc sai tên thuộc tính sau khi nguồn đã được nạp.

Nếu chọn mount ConfigMap thành file rồi để Spring Boot đọc `file:`, các lựa chọn tiền tố thuộc `spring.cloud.kubernetes.config.sources` không tự áp dụng cho đường đọc file đó. Khi ấy, có thể đặt đường dẫn đầy đủ trong nội dung file hoặc thiết kế cách nạp khác. Kubernetes phân biệt các cách tiêu thụ ConfigMap qua API, biến môi trường và volume trong [tài liệu ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/).

Tiền tố cũng không thay thế việc bảo vệ dữ liệu nhạy cảm. Nếu dùng Secret, chính sách nguồn và quyền truy cập Secret được thiết kế riêng; tên thuộc tính có tiền tố không làm giá trị bí mật an toàn hơn.

## 11. Thực hành đối chiếu tên khóa và giá trị hiệu lực

Các bước dưới đây dành cho môi trường lab của người học, với ứng dụng, namespace và quyền đã được chuẩn bị. Kết quả nêu trong bảng là kỳ vọng theo cấu hình của bài.

### 11.1. Xác nhận hai nguồn gốc

~~~shell
kubectl get configmap inventory-settings --namespace=prefix-lab -o yaml
kubectl get configmap shipping-settings --namespace=prefix-lab -o yaml
~~~

Các đầu ra vẫn chứa khóa `base-url`, `timeout` và `max-attempts`. Không mong đợi `kubectl` hiển thị tiền tố `clients.inventory` chỉ vì ứng dụng đã bật tiền tố trong loader.

Nếu không đọc được tài nguyên bằng danh tính ứng dụng, kiểm tra ServiceAccount và RoleBinding trước khi sửa tên thuộc tính.

### 11.2. Kiểm tra các đường dẫn mà ứng dụng đang hỏi

Với chính sách `explicit-prefix` ở phần 5, có thể dùng trong mã quan sát:

~~~java
String inventoryUrl = environment.getRequiredProperty(
        "clients.inventory.base-url");
String shippingUrl = environment.getRequiredProperty(
        "clients.shipping.base-url");
~~~

Mã đọc cũ như `environment.getRequiredProperty("base-url")` không tự được chuyển sang một trong hai nhánh.

Trong môi trường lab cô lập không có nguồn khác cấp khóa cũ, khóa `base-url` sẽ không có giá trị từ hai nguồn đã được thêm tiền tố. Nếu nó vẫn có giá trị, cần tìm nguồn đang cung cấp khóa ấy thay vì kết luận loader đã tự giữ bí danh.

### 11.3. Ma trận kiểm tra hành vi

| Tình huống | Kết quả cần quan sát |
| --- | --- |
| Hai nguồn không có tiền tố | Một bộ giá trị hiệu lực ở các khóa chung; không giữ riêng hai client |
| Bật tiền tố theo tên | Có `inventory-settings.*` và `shipping-settings.*` |
| Dùng hai tiền tố tường minh | Có `clients.inventory.*` và `clients.shipping.*` |
| Đảo thứ tự hai nguồn nhưng khóa hiệu lực tách biệt | Hai nhánh vẫn giữ đúng giá trị của nguồn tương ứng |
| Đặt cùng một tiền tố cho cả hai nguồn | Xung đột quay lại ở đường dẫn chung |
| Bật tiền tố nhưng mã vẫn đọc khóa cũ | Mã không nhận được giá trị từ nguồn tại tên mới |
| Gán nhầm hai tiền tố cho hai nguồn | Kiểu Java vẫn có thể hợp lệ nhưng vai trò URL bị đảo |
| Dữ liệu đã có tiền tố rồi loader thêm tiếp | Xuất hiện đường dẫn lặp; binding mong đợi bị thiếu |
| Đổi tên ConfigMap nhưng giữ tiền tố tường minh | Hợp đồng thuộc tính giữ nguyên nếu nguồn mới được đọc đúng |
| Thêm tiền tố vào `server.port` | Không còn cung cấp khóa chuẩn như dự định |
| Một nguồn ưu tiên cao hơn cấp cùng khóa mới | Giá trị hiệu lực có thể khác ConfigMap |
| Thiếu một nhánh thiết yếu và không có nguồn khác cung cấp | Validation của mô hình đầy đủ phải phát hiện thiếu cấu hình |

Không chỉ kiểm tra rằng hai URL “đều có giá trị”. Cần đối chiếu URL kho hàng với nhánh kho hàng và URL vận chuyển với nhánh vận chuyển. Sự hoán đổi hai URL là lỗi nghiệp vụ ngay cả khi cả hai đều là URI hợp lệ.

### 11.4. Đọc log và trạng thái Pod theo đúng lớp lỗi

~~~shell
kubectl describe pod POD_NAME --namespace=prefix-lab
kubectl logs POD_NAME --namespace=prefix-lab --container=order-service
kubectl logs POD_NAME --namespace=prefix-lab --container=order-service --previous
~~~

Thay `POD_NAME` bằng tên Pod thực tế. `--previous` chỉ hữu ích khi có container instance trước đó và log còn khả dụng.

| Bằng chứng | Điều nên kiểm tra |
| --- | --- |
| API trả `Forbidden` | Quyền của ServiceAccount đối với ConfigMap |
| Log cho thấy nhầm tên nguồn hoặc namespace | Danh sách `sources` và phạm vi tìm tài nguyên |
| Lỗi không tìm thấy thuộc tính | Đường dẫn mới sau phép thêm tiền tố |
| Validation báo thiếu nhánh `inventory` hoặc `shipping` | Tiền tố, dữ liệu và nguồn thực sự được nạp |
| Cấu hình hợp lệ nhưng gọi sai dịch vụ | Ánh xạ vai trò giữa tên nguồn và tiền tố |
| Pod chạy nhưng giá trị khác dự kiến | Nguồn ghi đè, profile hoặc phiên bản cấu hình |

Liveness hoặc trạng thái `Running` không chứng minh việc ánh xạ tiền tố đúng. Readiness và các bước xác nhận hành vi phải phản ánh khả năng phục vụ của ứng dụng, không chỉ sự tồn tại của tiến trình Java.

## 12. Chuyển sang tiền tố là một thay đổi hợp đồng cấu hình

Khi ứng dụng cũ đọc `timeout` nhưng ứng dụng mới đọc `clients.inventory.timeout`, việc đổi cấu hình loader cần đi cùng thay đổi nơi đọc cấu hình.

Một trình tự triển khai có thể gồm:

1. Lập bảng nguồn, khóa cũ, khóa hiệu lực mới và thành phần sử dụng.
2. Chọn tên tiền tố ổn định theo vai trò, tránh gắn không cần thiết với tên tài nguyên có thể đổi.
3. Cập nhật mô hình Java, nơi đọc thuộc tính và các nguồn ghi đè được phép.
4. Chuẩn bị manifest và cấu hình ứng dụng phù hợp với cùng phiên bản hợp đồng.
5. Xác nhận riêng từng nhánh bằng giá trị mẫu dễ phân biệt.
6. Rollout phiên bản ứng dụng tương ứng và xác định cách rollback cùng bộ cấu hình.

Ví dụ bảng chuyển đổi:

| Nguồn | Khóa cũ | Khóa mới | Nơi sử dụng |
| --- | --- | --- | --- |
| `inventory-settings` | `base-url` | `clients.inventory.base-url` | Client kho hàng |
| `inventory-settings` | `timeout` | `clients.inventory.timeout` | Client kho hàng |
| `shipping-settings` | `base-url` | `clients.shipping.base-url` | Client vận chuyển |
| `shipping-settings` | `timeout` | `clients.shipping.timeout` | Client vận chuyển |

Nếu cần giai đoạn tương thích, phải xác định rõ ứng dụng đọc tên cũ, tên mới hay một ánh xạ chuyển tiếp có thời hạn. Không dựa vào giá trị mặc định ngầm để làm thay đổi tên khóa “có vẻ vẫn chạy”.

Configuration Watcher có thể là một phần của thiết kế nhận cập nhật, nhưng không tự sửa nơi đọc thuộc tính khi tiền tố đã đổi. Bài thực hành chỉ yêu cầu nạp cấu hình lúc khởi động; nếu bổ sung refresh, cần kiểm tra riêng kiểu bean, cơ chế cập nhật và tính nhất quán của hai nhánh.

Trước khi chấp nhận chính sách tiền tố, cần xác nhận:

- Mỗi nguồn có chủ sở hữu và vai trò rõ ràng.
- Có bảng khóa hiệu lực sau khi nạp, bao gồm các ngoại lệ không dùng tiền tố.
- Các tiền tố tường minh độc lập là khác nhau.
- Không vô tình thêm tiền tố hai lần.
- Các khóa chuẩn của Spring Boot vẫn được cung cấp đúng tên khi cần.
- Mô hình Java bind theo đúng cấu trúc mới và phát hiện thiếu cấu hình thiết yếu.
- Quyền đọc nguồn, cơ chế cập nhật và cách kiểm tra giá trị hiệu lực đã được xác định.
