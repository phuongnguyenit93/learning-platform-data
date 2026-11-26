# Nạp bắt buộc và nạp tùy chọn khi nguồn cấu hình không có

Trong chương **Nạp Config Data** của module **Spring Cloud Kubernetes (SPRING_CLOUD_KUBERNETES)**, bài học này trả lời một câu hỏi vận hành: ứng dụng nên dừng khởi động hay tiếp tục dùng giá trị mặc định khi không nhận được cấu hình từ Kubernetes?

Một dịch vụ đơn hàng có thể chạy với thông báo giao diện mặc định nếu thiếu ConfigMap trang trí. Tuy nhiên, dịch vụ không nên nhận đơn khi chưa biết vùng xử lý hoặc giới hạn số mặt hàng. Vì vậy, quyết định “bắt buộc” phải gắn với yêu cầu của ứng dụng, thay vì chỉ dựa vào việc có hay không có tiền tố `optional:`.

Các ví dụ dùng cơ chế Config Data của Spring Boot và Spring Cloud Kubernetes; không kết hợp với cơ chế bootstrap cũ. Với phần đọc API, ví dụ và nhận xét về nguồn không tồn tại được giới hạn ở **Spring Cloud Kubernetes 3.3.3, client Fabric8**. Khi áp dụng vào dự án, chọn Spring Boot và Spring Cloud BOM tương thích với nhau, đồng thời kiểm tra hành vi của phiên bản và client đang sử dụng. Cách kích hoạt Config Data bằng `spring.config.import` và yêu cầu chọn một trong hai cơ chế được mô tả trong [tài liệu Spring Cloud Kubernetes 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config.html).

## 1. Xác định chính xác điều gì đang thiếu

Cụm từ “không có cấu hình” có thể chỉ nhiều tình huống khác nhau:

| Tình huống | Ví dụ | Điều cần quyết định hoặc kiểm tra |
| --- | --- | --- |
| Không có location hoặc tài nguyên Config Data | File được import chưa được mount | Location có được phép vắng mặt không? |
| Không có đối tượng Kubernetes theo tên cần tìm | Không có ConfigMap `orders-required` trong namespace `config-data-lab` | Loader coi đó là nguồn rỗng hay phát sinh lỗi? |
| Có đối tượng nhưng thiếu khóa | Có ConfigMap, thiếu `app.orders.region` | Ứng dụng có mặc định hoặc validation cho khóa này không? |
| Không được phép đọc | ServiceAccount thiếu quyền `list configmaps` | Sửa RBAC và chính sách xử lý lỗi truy cập |
| Không liên lạc được với API server | Timeout, lỗi DNS hoặc lỗi TLS | Chẩn đoán kết nối; cân nhắc retry có giới hạn |
| Có dữ liệu nhưng dữ liệu không hợp lệ | `app.orders.max-items=abc` hoặc số âm | Sửa dữ liệu; kiểm tra chuyển kiểu và ràng buộc nghiệp vụ |
| Đọc nhầm phạm vi | Nhầm namespace, tên hoặc profile | Kiểm tra đích tra cứu trước khi kết luận nguồn bị thiếu |

Một nguồn tồn tại chưa chắc đã đủ dữ liệu. Ngược lại, ứng dụng có thể đủ dữ liệu nhờ biến môi trường dù ConfigMap không tồn tại. Cần xác định hợp đồng mong muốn là **bắt buộc có giá trị hợp lệ** hay **bắt buộc có đúng một đối tượng Kubernetes**.

Ví dụ, “phải biết vùng xử lý” là yêu cầu về giá trị. “Mỗi bản phát hành phải tham chiếu ConfigMap có tên và phiên bản đã phê duyệt” còn là yêu cầu triển khai; validation một thuộc tính Java không chứng minh được danh tính của đối tượng đã cung cấp thuộc tính ấy.

## 2. Ba lớp chính sách cần tách biệt

Có ba câu hỏi cần trả lời theo thứ tự:

1. **Location có được phép không tồn tại không?** Đây là phạm vi của `optional:` trong Config Data, khi resolver hoặc loader báo lỗi không tìm thấy tương ứng.
2. **Lỗi đọc nguồn Kubernetes có làm khởi động thất bại không?** Với Spring Cloud Kubernetes, xem các thuộc tính `config.fail-fast`, `secrets.fail-fast` và retry của từng loại nguồn.
3. **Bộ giá trị cuối cùng có đủ và hợp lệ không?** Ứng dụng phải kiểm tra các thuộc tính thiết yếu sau khi tổng hợp cấu hình.

Sơ đồ sau diễn tả quyết định thiết kế, không phải cam kết rằng mọi client đều phân loại lỗi giống nhau:

~~~mermaid
flowchart TD
    A["Bắt đầu nạp cấu hình"] --> B{"Đọc được nguồn?"}
    B -->|Có| C["Gộp các thuộc tính"]
    B -->|Không| D{"Nguồn vắng mặt được chấp nhận?"}
    D -->|Có| E["Dùng các nguồn còn lại và mặc định an toàn"]
    D -->|Không| F["Dừng khởi động"]
    E --> C
    C --> G{"Thuộc tính thiết yếu hợp lệ?"}
    G -->|Có| H["Tiếp tục khởi động"]
    G -->|Không| F
~~~

Trong thiết kế này, việc tiếp tục khởi động chỉ được chấp nhận khi ứng dụng vẫn hoạt động đúng với dữ liệu còn lại. “Tiến trình Java chưa thoát” chưa đủ để kết luận dịch vụ có thể nhận lưu lượng.

## 3. Hiểu `optional:` bằng nguồn file trước

Với một file được import trực tiếp, sự khác biệt rất rõ:

~~~yaml
spring:
  config:
    import: "file:/etc/order-policy/policy.properties"
~~~

Nếu file bắt buộc này không tồn tại, quá trình nạp Config Data thất bại.

Để cho phép file vắng mặt:

~~~yaml
spring:
  config:
    import: "optional:file:/etc/order-policy/policy.properties"
~~~

Tiền tố `optional:` gắn với location đó. Spring Boot mô tả cơ chế này trong phần [Optional Locations](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html#features.external-config.files.optional). Nó không tạo giá trị mặc định cho các khóa của ứng dụng. File vắng mặt được bỏ qua nhưng một thuộc tính bắt buộc chưa có giá trị vẫn cần được phát hiện ở lớp kiểm tra cấu hình.

Không nên dùng `spring.config.on-not-found=ignore` như lựa chọn mặc định cho cả ứng dụng: phạm vi bỏ qua lỗi không tìm thấy sẽ rộng hơn việc đánh dấu riêng một location là tùy chọn.

Cũng không coi `optional:` là cơ chế sửa YAML sai cú pháp, giá trị không chuyển được sang số hoặc cấu hình nghiệp vụ không hợp lệ. Cho phép thiếu nguồn và chấp nhận dữ liệu sai là hai chính sách khác nhau.

## 4. Áp dụng cho `kubernetes:`: cẩn thận với ý nghĩa “bắt buộc”

Hai cách khai báo thường gặp là:

~~~yaml
spring:
  config:
    import: "kubernetes:"
~~~

và:

~~~yaml
spring:
  config:
    import: "optional:kubernetes:"
~~~

Đặt chuỗi có dấu `:` trong dấu nháy khi viết YAML. Tên ConfigMap, namespace và lựa chọn loại nguồn được cấu hình bằng các thuộc tính Spring Cloud Kubernetes tương ứng; không tự suy ra cú pháp dạng `kubernetes:ten-configmap` cho ví dụ trong bài.

### 4.1. Không có `optional:` chưa bảo đảm ConfigMap theo tên phải tồn tại

Với nguồn được tra cứu theo tên trong Spring Cloud Kubernetes 3.3.3/Fabric8, đường đọc ConfigMap có thể trả về dữ liệu rỗng khi không tìm thấy đối tượng phù hợp. `NamedSourceData` xử lý tập tên tìm thấy rỗng bằng một nguồn rỗng, còn `KubernetesConfigDataLoader` lấy các PropertySource từ locator.

Từ mã nguồn này, có thể suy ra: chỉ khai báo `spring.config.import="kubernetes:"` không đủ để khẳng định “thiếu ConfigMap theo tên thì ứng dụng chắc chắn dừng”. Đây là nhận xét theo phiên bản và đường đọc đã nêu, không phải quy tắc chung cho mọi bản phát hành. Xem [NamedSourceData tại tag v3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/config/NamedSourceData.java) và [KubernetesConfigDataLoader tại tag v3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/config/KubernetesConfigDataLoader.java).

Do đó, một chính sách bắt buộc đáng tin cậy cần ghi rõ:

- Nạp từ nguồn nào, tên gì, namespace nào.
- Khi đọc nguồn phát sinh lỗi thì có dừng hay không.
- Các thuộc tính thiết yếu phải có giá trị gì hoặc thỏa ràng buộc nào.
- Có cho phép biến môi trường hoặc nguồn khác cung cấp các thuộc tính ấy không.

Nếu hợp đồng triển khai bắt buộc sự tồn tại của chính ConfigMap, cần thêm kiểm tra đối tượng trong quy trình triển khai hoặc một cơ chế kiểm tra nguồn được thiết kế riêng. Không dùng một giá trị mặc định ngầm để thay thế yêu cầu đó.

### 4.2. `fail-fast` xử lý lỗi nạp nguồn, không thay thế validation

Ví dụ chính sách đọc ConfigMap:

~~~yaml
spring:
  cloud:
    kubernetes:
      config:
        fail-fast: true
        retry:
          enabled: false
~~~

Thuộc tính đầy đủ là `spring.cloud.kubernetes.config.fail-fast`. Tài liệu ghi mặc định là `false`; bật `true` để lỗi nạp ConfigMap làm khởi động thất bại. Ví dụ tắt retry nhằm giúp quan sát lỗi trong lab dễ hơn. Xem [cấu hình ConfigMap và fail-fast](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config/configmap-propertysource.html).

Không đồng nhất “không có đối tượng phù hợp” với “lệnh gọi API phát sinh ngoại lệ”. Trong đường đọc đã phân tích, trường hợp đầu có thể tạo nguồn rỗng; trường hợp sau mới đi qua cơ chế xử lý lỗi.

Nếu sau này bật retry, cần các dependency hỗ trợ đúng với phiên bản đang dùng, đặt số lần thử và khoảng chờ hữu hạn. Retry phù hợp với lỗi tạm thời; nó không tự tạo ConfigMap hay cấp quyền còn thiếu.

### 4.3. Cấu hình chính sách ở nơi ứng dụng đọc được trước

Các lựa chọn phục vụ việc tìm và đọc nguồn phải có sẵn trước lần đọc đó. Đặt `spring.config.import`, tên nguồn, namespace, `fail-fast` và lựa chọn retry trong cấu hình đóng gói cùng ứng dụng hoặc trong nguồn khởi động thích hợp.

Ví dụ, không đặt duy nhất `fail-fast: true` trong chính ConfigMap mà ứng dụng chưa đọc được rồi kỳ vọng giá trị ấy sẽ điều khiển lần đọc thất bại đầu tiên.

## 5. Tình huống A: cấu hình đơn hàng là bắt buộc

Giả sử ứng dụng `order-service` cần:

| Thuộc tính | Hợp đồng |
| --- | --- |
| `app.orders.region` | Phải có chuỗi khác rỗng |
| `app.orders.max-items` | Phải có số nguyên từ 1 đến 100 |
| Nguồn dự kiến | ConfigMap `orders-required` |
| Namespace lab | `config-data-lab` |
| Lỗi gọi API | Làm khởi động thất bại |
| Giá trị mặc định cho hai thuộc tính | Không đặt trong tình huống bắt buộc |

Đây là hợp đồng của ví dụ. Mỗi hệ thống phải chọn ràng buộc theo nghiệp vụ thực tế; giới hạn 100 không phải giới hạn của Spring hay Kubernetes.

### 5.1. Điều kiện thực hành

Ứng dụng mẫu có Java 17 trở lên, Spring Boot 3.x tương thích với Spring Cloud Kubernetes 3.3.3 qua BOM phù hợp, cùng hai dependency sau. Đoạn XML chỉ minh họa phần dependency; không phải toàn bộ file build:

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

Bài chỉ cần tính năng cấu hình. Không cần thêm DiscoveryClient, Spring Cloud LoadBalancer hoặc Configuration Watcher để minh họa lần nạp ban đầu. Chỉ bổ sung những tính năng đó khi bài toán triển khai có yêu cầu tương ứng.

### 5.2. Cấu hình ứng dụng

Nội dung `application.yaml` cho tình huống A:

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
        name: orders-required
        namespace: config-data-lab
        include-profile-specific-sources: false
        fail-fast: true
        retry:
          enabled: false
      secrets:
        enabled: false
~~~

Ví dụ chỉ đọc một ConfigMap theo tên và không tìm thêm nguồn theo profile. Việc tắt Secrets giữ phạm vi quan sát gọn: không có lần đọc Secret API không cần thiết.

Tên và namespace được ghi rõ để lỗi gõ nhầm không bị che bởi cơ chế suy ra tên nguồn. Cách lựa chọn ConfigMap qua `config.name`, `spring.application.name` và danh sách `sources` được trình bày trong [tài liệu nguồn ConfigMap](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config/configmap-propertysource.html).

### 5.3. Kiểm tra thuộc tính khi khởi động

Tạo một kiểu cấu hình được bind và validate:

~~~java
package example.orders;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.orders")
public record OrderPolicyProperties(
        @NotBlank String region,
        @NotNull @Min(1) @Max(100) Integer maxItems) {
}
~~~

Đăng ký bằng cách quét `@ConfigurationProperties` trong package của ứng dụng:

~~~java
package example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Dùng `Integer` cùng `@NotNull` để phân biệt việc thiếu `max-items` với một số được cung cấp. `@Min` và `@Max` kiểm tra miền giá trị; `@NotBlank` loại chuỗi null, rỗng hoặc chỉ có khoảng trắng.

Trong ví dụ này, bean cấu hình được đăng ký lúc khởi động, dependency validation có trên classpath và không trì hoãn việc kiểm tra bằng lazy initialization. Nhờ đó, thiếu thuộc tính thiết yếu được phát hiện trong quá trình tạo application context.

Validation kiểm tra **giá trị cuối cùng**. Nếu biến môi trường hoặc nguồn hợp lệ khác đã cung cấp đủ thuộc tính, ứng dụng có thể khởi động dù ConfigMap dự kiến không tồn tại. Nếu yêu cầu cấm điều này, phải bổ sung chính sách kiểm tra nguồn, thay vì suy diễn từ kết quả validation.

### 5.4. Dữ liệu cần cung cấp

ConfigMap tương ứng:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-required
  namespace: config-data-lab
data:
  app.orders.region: "vn-south"
  app.orders.max-items: "20"
~~~

Các giá trị trong `data` được viết dưới dạng chuỗi. Hai khóa được dùng trực tiếp để bind vào `OrderPolicyProperties`.

Khi thực hành, cần áp dụng namespace và RBAC ở phần 7, tạo ConfigMap rồi chạy image của ứng dụng với đúng ServiceAccount. Không đặt hai giá trị này trong biến môi trường của lần thử thiếu nguồn, vì chúng sẽ làm thay đổi kết quả cần quan sát.

## 6. Tình huống B: nguồn tùy chọn với mặc định an toàn

Trong một môi trường đào tạo độc lập, ứng dụng được phép dùng vùng `training` và tối đa 10 mặt hàng. ConfigMap chỉ cung cấp phần tùy chỉnh giao diện. Đây là lựa chọn có chủ đích cho lab, không phải mặc định dùng khi hệ thống đơn hàng thật bị mất cấu hình.

Thay toàn bộ `application.yaml` của tình huống A bằng mẫu sau khi thử tình huống B; không ghép hai mẫu thành hai khóa `spring` trùng nhau:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:kubernetes:"
  cloud:
    kubernetes:
      config:
        enabled: true
        name: order-display
        namespace: config-data-lab
        include-profile-specific-sources: false
        fail-fast: true
        retry:
          enabled: false
      secrets:
        enabled: false

app:
  orders:
    region: "training"
    max-items: 10
  ui:
    banner: "Môi trường học tập"
    promotion-enabled: false
~~~

Giữ `fail-fast: true` là chủ ý: việc không tìm thấy nguồn theo tên được phép dẫn tới sử dụng mặc định trong đường đọc đã nêu, nhưng lỗi truy cập API không được coi như một lần triển khai bình thường.

Với phiên bản/client trong bài, thiếu ConfigMap `order-display` có thể trả về nguồn rỗng; các mặc định lab vẫn đáp ứng validation. Điều này không chứng minh rằng riêng `optional:` đã bắt và bỏ qua mọi lỗi của API server.

Một ConfigMap giao diện có thể cung cấp:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-display
  namespace: config-data-lab
data:
  app.ui.banner: "Thực hành Config Data"
  app.ui.promotion-enabled: "false"
~~~

Theo quy tắc ưu tiên Config Data, giá trị được import có thể ghi đè giá trị trong tài liệu khai báo import; biến môi trường vẫn có thể ghi đè Config Data. Do đó, khi kiểm tra banner, phải biết cả cấu hình trong image lẫn biến môi trường của Pod. Xem [thứ tự ưu tiên Kubernetes PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config.html#_property_source_precedence).

Không nên tạo mặc định “an toàn giả”, chẳng hạn tự chọn vùng xử lý thật khi mất cấu hình hoặc tự bật một tính năng có tác động nghiệp vụ. Một mặc định chỉ phù hợp khi chủ sở hữu ứng dụng đã xác định hành vi đó là đúng cho môi trường đang chạy.

## 7. RBAC cho lab đọc ConfigMap qua API

Đọc API và đọc file đã mount là hai đường khác nhau. Trong lab API, ứng dụng sử dụng ServiceAccount riêng và quyền trong namespace lab:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: config-data-lab
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: order-config-reader
  namespace: config-data-lab
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: order-configmap-reader
  namespace: config-data-lab
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: order-configmap-reader-binding
  namespace: config-data-lab
subjects:
  - kind: ServiceAccount
    name: order-config-reader
    namespace: config-data-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: order-configmap-reader
~~~

Đoạn cần đặt trong Pod template của Deployment là:

~~~yaml
spec:
  template:
    spec:
      serviceAccountName: order-config-reader
~~~

Đây là đoạn trích để tích hợp vào Deployment của ứng dụng, không phải manifest Deployment hoàn chỉnh.

Đường đọc Fabric8 3.3.3 dùng danh sách ConfigMap trong namespace trước khi lọc theo tên, nên lab có quyền `list` dù ứng dụng khai báo một tên cụ thể. Xem [Fabric8ConfigUtils tại v3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-fabric8-config/src/main/java/org/springframework/cloud/kubernetes/fabric8/config/Fabric8ConfigUtils.java). Không tự giới hạn Role bằng `resourceNames` rồi giả định một lệnh list không lọc tên sẽ hoạt động.

Lab chỉ minh họa nạp cấu hình ban đầu, vì vậy Role không cấp quyền đọc Secret hoặc quyền Discovery. Nếu sau này bật cơ chế theo dõi thay đổi, cần đánh giá quyền `watch` theo cách hoạt động thực tế. Quan hệ giữa dependency và quyền tài nguyên được mô tả trong [Security Configurations Inside Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/security-service-accounts.html).

Dưới tài khoản quản trị có quyền impersonation phù hợp, có thể kiểm tra quyền dự kiến bằng:

~~~shell
kubectl auth can-i list configmaps --namespace=config-data-lab --as=system:serviceaccount:config-data-lab:order-config-reader
kubectl auth can-i get configmaps --namespace=config-data-lab --as=system:serviceaccount:config-data-lab:order-config-reader
~~~

Kết quả `yes` chỉ kiểm tra phân quyền cho danh tính được hỏi. Nó chưa chứng minh Pod đã dùng đúng ServiceAccount, đã tìm đúng tên nguồn hoặc đã nhận được các giá trị cần thiết.

## 8. Secret và volume: hai ý nghĩa “tùy chọn” khác nhau

### 8.1. Nếu đọc Secret qua Spring Cloud Kubernetes

Chính sách lỗi của Secret có thuộc tính riêng:

~~~yaml
spring:
  cloud:
    kubernetes:
      secrets:
        enabled: true
        enable-api: true
        name: order-credentials
        namespace: config-data-lab
        fail-fast: true
        retry:
          enabled: false
~~~

Đây là cấu hình cho một phương án riêng; không cần bật trong hai lab ConfigMap ở trên. Nếu dùng phương án này, phải cấp quyền Secret thích hợp. Không suy ra rằng `config.fail-fast=true` đã áp dụng cho Secret.

Tài liệu khuyến nghị cân nhắc Secret được mount thay vì mở quyền đọc Secret qua API; xem [Secrets PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/secrets-propertysource.html). Dù nhận Secret bằng cách nào, ứng dụng vẫn cần kiểm tra thông tin xác thực bắt buộc. Không dùng mật khẩu mẫu hoặc chuỗi rỗng để biến việc thiếu Secret thành một lần khởi động “thành công”.

### 8.2. Nếu mount ConfigMap thành file

Giả sử Pod có đoạn volume sau:

~~~yaml
spec:
  containers:
    - name: order-service
      image: your-registry/order-service:lab
      volumeMounts:
        - name: display-config
          mountPath: /etc/order-display
          readOnly: true
  volumes:
    - name: display-config
      configMap:
        name: order-display-file
        optional: true
~~~

Đây là đoạn trích Pod spec; cần thay image và tích hợp vào manifest hoàn chỉnh khi thực hành. Nếu ConfigMap có khóa `display.properties`, nội dung khóa sẽ xuất hiện thành file `/etc/order-display/display.properties`.

Cấu hình Spring tương ứng:

~~~yaml
spring:
  config:
    import: "optional:file:/etc/order-display/display.properties"

app:
  ui:
    banner: "Môi trường học tập"
~~~

Ở đây có hai bên đưa ra quyết định:

| Thiết lập | Bên thực thi | Vai trò |
| --- | --- | --- |
| `configMap.optional: true` | Kubernetes/kubelet | Cho phép tham chiếu ConfigMap vắng mặt; nội dung volume có thể rỗng |
| `optional:file:...` | Spring Boot | Cho phép file được import không tồn tại |

Chỉ đặt tiền tố ở Spring không giúp container chạy qua một lỗi mount nguồn bắt buộc của Kubernetes. Ngược lại, chỉ cho phép volume rỗng không giúp Spring bỏ qua một file import bắt buộc bị thiếu. Kubernetes mô tả các trường hợp này trong [Optional references và Optional ConfigMaps](https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/#optional-references).

Với Secret volume, thuộc tính của nguồn volume dùng `secretName`:

~~~yaml
volumes:
  - name: order-credentials
    secret:
      secretName: order-credentials
      optional: false
~~~

Kubernetes mặc định yêu cầu các Secret không tùy chọn phải có trước khi container khởi động; xem [Optional Secrets](https://kubernetes.io/docs/concepts/configuration/secret/#optional-secrets). Đây là điều kiện do kubelet thực thi trước hoặc ngoài quá trình nạp Config Data của Java.

Nếu chỉ cần đọc các file đã mount bằng `file:` hoặc `configtree:`, hãy cân nhắc khả năng của Spring Boot trước khi thêm client Kubernetes vào ứng dụng. Lựa chọn tính năng nên đi theo nhu cầu đọc API, discovery, cân bằng tải hoặc cập nhật cấu hình thực tế.

## 9. Ma trận quan sát cho hai tình huống API

Các kết quả dưới đây là **kỳ vọng thực hành** theo cấu hình và phạm vi phiên bản của bài. Thực hiện từng tình huống trong namespace lab, với đúng ServiceAccount. Để quan sát việc thiếu cấu hình, không cung cấp lại các khóa đang thử qua biến môi trường hoặc tham số khởi động.

| Lần thử | Thay đổi đầu vào | Kỳ vọng |
| --- | --- | --- |
| A1 | ConfigMap `orders-required` có đủ hai khóa hợp lệ | Ứng dụng vượt qua bước kiểm tra cấu hình |
| A2 | Không có `orders-required`, không có nguồn nào khác cấp hai khóa | Nguồn có thể rỗng; validation làm ứng dụng thất bại khi khởi động |
| A3 | ConfigMap chỉ có `app.orders.region` | Validation phát hiện `maxItems` chưa có |
| A4 | `app.orders.max-items` có giá trị `abc` | Binding thất bại vì không chuyển được sang số nguyên |
| A5 | `app.orders.max-items` bằng `0` | Binding có thể chuyển kiểu, nhưng validation không cho phép giá trị |
| A6 | ServiceAccount mất quyền list ConfigMap | Lỗi đọc API; `fail-fast=true` làm khởi động thất bại |
| B1 | Không có `order-display`, API vẫn đọc được namespace | Ứng dụng dùng mặc định lab và vượt qua validation |
| B2 | Có `order-display` với banner hợp lệ | Nguồn import cung cấp banner tùy chỉnh |
| B3 | Có `optional:kubernetes:` nhưng bị từ chối quyền đọc | Không coi `optional:` là bảo đảm khởi động; xử lý theo lỗi và fail-fast |
| B4 | Có mặc định nhưng một nguồn ưu tiên cao hơn cấp số không hợp lệ | Mặc định không cứu được giá trị ghi đè sai; kiểm tra cấu hình vẫn thất bại |

Với nguồn file, thử riêng hai biến thể ở phần 3: cùng một đường dẫn chưa có file, bản bắt buộc phải dừng ở Config Data còn bản tùy chọn đi tiếp đến các bước kiểm tra tiếp theo.

Nếu kết quả khác kỳ vọng, ghi lại phiên bản Spring Boot, Spring Cloud Kubernetes, loại client, profile đang active, tên nguồn, namespace và danh sách nguồn có thể cấp cùng khóa. Những thông tin này giúp phân biệt khác biệt phiên bản với một biến môi trường còn sót từ lần thử trước.

## 10. Chẩn đoán bằng log, sự kiện và sức khỏe Pod

Dùng các lệnh đọc sau, thay `POD_NAME` bằng Pod của ứng dụng:

~~~shell
kubectl get configmap orders-required --namespace=config-data-lab
kubectl get pod POD_NAME --namespace=config-data-lab -o wide
kubectl describe pod POD_NAME --namespace=config-data-lab
kubectl logs POD_NAME --namespace=config-data-lab --container=order-service
kubectl logs POD_NAME --namespace=config-data-lab --container=order-service --previous
~~~

Lệnh `--previous` chỉ có dữ liệu khi đã có container instance trước đó và log còn khả dụng.

Đọc bằng chứng theo lớp:

- **Không có log Java, Events báo lỗi mount hoặc tham chiếu cấu hình:** kiểm tra Pod spec, ConfigMap/Secret, namespace và tính tùy chọn của tham chiếu Kubernetes.
- **Có log Java báo Forbidden:** kiểm tra ServiceAccount và RoleBinding; một ConfigMap tồn tại không có nghĩa ứng dụng được phép đọc.
- **Có log timeout hoặc lỗi TLS:** kiểm tra đường kết nối và cấu hình client trước khi thay đổi chính sách bắt buộc.
- **Có lỗi binding hoặc validation:** nguồn có thể đã được đọc thành công nhưng thiếu khóa hoặc có giá trị sai.
- **Ứng dụng chạy nhưng giá trị vẫn là mặc định:** kiểm tra tên nguồn, profile, namespace và thứ tự ưu tiên của các nguồn cùng khóa.

Không dùng riêng trạng thái `Running` để xác nhận bài toán đã đúng. Với tình huống bắt buộc, cần thấy ứng dụng dừng vì thiếu cấu hình thiết yếu. Với tình huống tùy chọn, cần thấy ứng dụng có hành vi mặc định đã định nghĩa và readiness phản ánh khả năng phục vụ thực tế.

Readiness và liveness phục vụ các mục đích khác nhau. Không tự biến sự vắng mặt của một ConfigMap giao diện tùy chọn thành nguyên nhân khởi động lại liên tục. Ngược lại, cũng không báo sẵn sàng khi ứng dụng chưa đáp ứng hợp đồng cấu hình nghiệp vụ.

Khi ghi nhận kết quả, chỉ ghi tên nguồn, phạm vi và trạng thái kiểm tra cần thiết. Không in mật khẩu, token hoặc toàn bộ nội dung Secret để chứng minh việc nạp thành công.

## 11. Nguồn xuất hiện sau khi khởi động không đồng nghĩa Java đã nhận thay đổi

Một nguồn tùy chọn có thể chưa có ở thời điểm Pod khởi động và xuất hiện sau đó. Cần xác định riêng cơ chế để ứng dụng nhận cấu hình mới.

Config Data chủ yếu giải quyết lần nạp cấu hình khi khởi động. Nếu file trong volume được Kubernetes cập nhật, không suy ra rằng bean Java đã tự bind lại. Có thể chọn rollout/restart theo quy trình triển khai, hoặc thiết kế cơ chế refresh phù hợp.

Spring Cloud Kubernetes Configuration Watcher là một lựa chọn cho nhu cầu thông báo thay đổi và refresh; nó không phải điều kiện để dùng `optional:`. Tài liệu giải thích sự khác biệt giữa file volume được cập nhật và Spring application context được refresh trong [Spring Cloud Kubernetes Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Ứng dụng chỉ cần cấu hình ở lần khởi động đầu tiên có thể chọn một quy trình triển khai rõ ràng mà chưa cần thêm Watcher. Nếu dùng refresh, cần xác định lại cách kiểm tra giá trị mới và cách xử lý cấu hình không hợp lệ, thay vì chỉ dựa vào kiểm tra lúc khởi động.

## 12. Tiêu chí hoàn thành chính sách nạp cấu hình

Một chính sách có thể đưa vào triển khai khi nhóm vận hành và nhóm phát triển trả lời thống nhất các điểm sau:

- Mỗi nguồn được xác định bằng cơ chế đọc, tên, namespace hoặc đường dẫn cụ thể.
- Nguồn tùy chọn có mặc định được chấp nhận cho đúng môi trường; không lấy mặc định lab thay cho cấu hình production.
- Các thuộc tính thiết yếu được kiểm tra về sự hiện diện, kiểu dữ liệu và miền giá trị.
- Chính sách `fail-fast` và retry được chọn riêng cho ConfigMap và Secret.
- Lỗi không tồn tại được phân biệt với lỗi phân quyền, mạng và dữ liệu sai.
- Khi cần bắt buộc sự tồn tại của một đối tượng cụ thể, quy trình triển khai có kiểm tra đối tượng tương ứng.
- Kết quả thử có bằng chứng từ log hoặc Events và giá trị hiệu lực không nhạy cảm, thay vì chỉ từ trạng thái Pod.
- Cách nhận cấu hình sau khi nguồn xuất hiện hoặc thay đổi đã được xác định.

Kết quả mong muốn là một quyết định rõ ràng: thiếu nguồn nào thì dừng, thiếu nguồn nào thì chạy với hành vi mặc định nào, và lỗi nào phải được xử lý trước khi cho ứng dụng nhận lưu lượng.
