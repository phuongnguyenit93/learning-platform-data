# Lọc dịch vụ bằng label và điều kiện biểu thức được hỗ trợ

Trong chương **Khám phá dịch vụ** của module **SPRING_CLOUD_KUBERNETES**, bài này hướng dẫn giới hạn các Kubernetes Service mà ứng dụng cần khám phá. Hai công cụ chính là bộ lọc label qua `spring.cloud.kubernetes.discovery.service-labels` và biểu thức Spring Expression Language (SpEL) qua `spring.cloud.kubernetes.discovery.filter`.

Một namespace có thể chứa API nghiệp vụ, cơ sở dữ liệu, thành phần giám sát và các Service phục vụ vận hành. Nếu ứng dụng chỉ cần gọi nhóm API thương mại, việc đưa mọi Service vào kết quả khám phá gây nhiễu và tăng khả năng chọn sai đích. Bộ lọc giúp mô tả rõ tập Service liên quan đến ứng dụng, đồng thời hỗ trợ sử dụng DiscoveryClient và Spring Cloud LoadBalancer có chủ đích.

Sau bài học, bạn có thể:

- Phân biệt label trên Service với label trên Pod và selector của Service.
- Viết bộ lọc nhiều label có quan hệ AND.
- Dùng biểu thức SpEL trả về boolean để lọc theo tên hoặc metadata của Service.
- Kết hợp hai loại bộ lọc và dự đoán kết quả bằng bảng ví dụ.
- Kiểm tra cấu hình có hiệu lực, kết quả DiscoveryClient và các trường hợp dịch vụ biến mất ngoài ý muốn.

Các ví dụ cấu hình dưới đây dành cho ứng dụng dùng Kubernetes DiscoveryClient trực tiếp với Kubernetes API. Chọn implementation và dependency tương thích với phiên bản Spring Boot, Spring Cloud và Spring Cloud Kubernetes của dự án. Nếu dùng mô hình DiscoveryServer qua HTTP, cần xác định cấu hình lọc thuộc thành phần thực sự truy vấn Kubernetes; không mặc định việc đặt các thuộc tính này ở HTTP client sẽ thay đổi danh sách Service trên server.

## 1. Đối tượng được lọc là Kubernetes Service

Một Service Kubernetes có metadata riêng và có thể chọn các Pod thông qua `spec.selector`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
  namespace: commerce
  labels:
    app.kubernetes.io/part-of: commerce
    discovery.example.com/enabled: "true"
    tier: api
spec:
  selector:
    app: catalog
  ports:
    - name: http
      port: 8080
      targetPort: 8080
```

Ba vị trí thường bị nhầm có vai trò khác nhau:

| Vị trí | Ví dụ | Vai trò |
| --- | --- | --- |
| `Service.metadata.labels` | `tier: api` | Gắn metadata cho Service; bộ lọc khám phá theo label xét tại đây. |
| `Service.spec.selector` | `app: catalog` | Chọn các Pod mà Service hướng lưu lượng tới. |
| `Pod.metadata.labels` | `app: catalog` | Metadata của Pod; có thể được selector của Service sử dụng. |

Nếu chỉ gắn `discovery.example.com/enabled: "true"` vào Pod, Service không tự động có label đó. Vì vậy, bộ lọc yêu cầu label này trên Service vẫn có thể loại Service khỏi kết quả khám phá, dù Service đang trỏ đúng tới các Pod khỏe mạnh.

Nếu triển khai qua Deployment, label ở `Deployment.spec.template.metadata.labels` sẽ được gắn cho Pod được tạo ra. Nó cũng không tự sao chép sang `Service.metadata.labels`. Với Helm hoặc công cụ sinh manifest, kiểm tra đối tượng Service sau khi render để bảo đảm label xuất hiện đúng chỗ.

Khám phá được Service và gọi được ứng dụng là hai điều kiện riêng. Một Service có thể khớp mọi điều kiện lọc nhưng chưa có endpoint sẵn sàng, chọn sai Pod hoặc khai báo cổng không phù hợp. Bộ lọc metadata không thay thế kiểm tra sức khỏe và cấu hình định tuyến.

## 2. Tập Service kết quả được hình thành như thế nào?

Có thể hiểu tập Service được chấp nhận theo mô hình:

```text
Service trong phạm vi namespace và quyền đọc của DiscoveryClient
    -> khớp tất cả label yêu cầu
    -> thỏa biểu thức SpEL, nếu có
    -> thuộc tập Service được bộ lọc chấp nhận
```

Đây là mô hình logic để suy luận điều kiện chấp nhận. Nó không cam kết mọi implementation đều gửi cùng một truy vấn API hoặc thực thi các bước ở cùng một nơi.

Đối với một Service `s`, điều kiện kết hợp có thể viết thành:

```text
accepted(s) = inScope(s) AND labelsMatch(s) AND expressionMatch(s)
```

Trong đó:

- `inScope(s)` phụ thuộc namespace đang khám phá, cấu hình phạm vi và RBAC.
- `labelsMatch(s)` đúng khi Service có đủ các cặp key–value được cấu hình.
- `expressionMatch(s)` đúng khi biểu thức được cấu hình đánh giá thành `true` trên Service.

Khi không cấu hình một loại bộ lọc, loại đó không bổ sung điều kiện loại trừ. Một biểu thức rộng không thể đưa Service nằm ngoài namespace được truy vấn vào kết quả, cũng không thể cấp thêm quyền đọc Kubernetes API.

Trong phạm vi module, ConfigMap hoặc Secret có thể tham gia cung cấp cấu hình cho ứng dụng; Spring Cloud LoadBalancer có thể sử dụng các instance được khám phá. Tuy nhiên, việc lọc Service là trách nhiệm của luồng khám phá. Không cần thêm Configuration Watcher chỉ để tạo một điều kiện lọc tĩnh.

## 3. Lọc theo một hoặc nhiều label

### 3.1. Một label: chỉ nhận Service được công bố cho khám phá

Cấu hình trong `application.yml` của ứng dụng gọi dịch vụ:

```yaml
spring:
  application:
    name: storefront
  cloud:
    kubernetes:
      discovery:
        service-labels:
          "[discovery.example.com/enabled]": "true"
```

Ý nghĩa: chỉ chấp nhận Service có `metadata.labels['discovery.example.com/enabled']` bằng chuỗi `true`.

Label Kubernetes có giá trị kiểu chuỗi. Đặt `"true"`, `"false"` hoặc các giá trị giống số trong dấu nháy giúp tránh nhầm với boolean hoặc số trong YAML. Dấu chấm và dấu gạch chéo trong key là một phần của key label; không tách key thành nhiều thuộc tính.

Trong map cấu hình Spring Boot, key được viết là `"[discovery.example.com/enabled]"`: cặp ngoặc vuông yêu cầu bộ bind cấu hình giữ nguyên key chứa ký tự `/`, còn dấu nháy giúp YAML đọc key đó đúng cách. Key label thực trên Kubernetes vẫn là `discovery.example.com/enabled`, không có ngoặc vuông. Vì vậy, manifest Service ở mục 1 dùng tên label nguyên bản, còn ví dụ `service-labels` dùng cú pháp key trong ngoặc vuông. Chỉ quote key chứa `/` mà bỏ ngoặc vuông có thể làm mất ký tự khi bind map và khiến điều kiện không khớp.

`discovery.example.com/enabled` là quy ước minh họa do hệ thống tự đặt. Spring Cloud Kubernetes không yêu cầu key cụ thể này. Trong môi trường thật, nhóm vận hành nên chọn prefix thuộc phạm vi quản lý của mình và dùng thống nhất giữa manifest và cấu hình ứng dụng.

### 3.2. Nhiều label: mọi cặp đều phải khớp

```yaml
spring:
  cloud:
    kubernetes:
      discovery:
        service-labels:
          "[app.kubernetes.io/part-of]": "commerce"
          "[discovery.example.com/enabled]": "true"
```

Cấu hình trên tương đương điều kiện:

```text
part-of == "commerce" AND enabled == "true"
```

Một Service có thêm các label khác vẫn được chấp nhận. Bộ lọc yêu cầu các cặp đã chỉ định tồn tại và khớp giá trị, không yêu cầu toàn bộ map label phải giống hệt map cấu hình.

| `part-of` trên Service | `enabled` trên Service | Kết quả bộ lọc label |
| --- | --- | --- |
| `commerce` | `true` | Chấp nhận |
| `commerce` | `false` | Loại |
| `analytics` | `true` | Loại |
| `commerce` | Không có key | Loại |
| Không có key | `true` | Loại |

Các key rút gọn trong bảng lần lượt là `app.kubernetes.io/part-of` và `discovery.example.com/enabled`.

### 3.3. Không đặt cú pháp selector tùy ý vào map label

`service-labels` là map key–value để diễn đạt yêu cầu khớp label. Không dùng nó như nơi chứa nguyên văn biểu thức Kubernetes label selector.

Ví dụ sau không diễn đạt phép OR:

```yaml
# Không dùng để biểu diễn tier là api hoặc worker.
spring:
  cloud:
    kubernetes:
      discovery:
        service-labels:
          tier: "api,worker"
```

Chuỗi `api,worker` không được hiểu thành hai giá trị lựa chọn. Tương tự, không đặt `in (...)`, `notin (...)`, `!=` hoặc chuỗi regex vào giá trị map rồi kỳ vọng hệ thống diễn giải thành toán tử.

Nếu cần OR, điều kiện thiếu key hoặc kết hợp tên Service với label, dùng biểu thức được hỗ trợ qua thuộc tính `filter`. Cú pháp selector của `kubectl` ở phần thực hành là một giao diện khác, không phải bằng chứng rằng `service-labels` nhận toàn bộ cú pháp đó.

## 4. Lọc bằng biểu thức SpEL

### 4.1. Ngữ cảnh đánh giá và kiểu kết quả

Thuộc tính `spring.cloud.kubernetes.discovery.filter` nhận biểu thức SpEL. Trong ngữ cảnh lọc Service, `#root` đại diện cho đối tượng Kubernetes Service mà implementation đang đánh giá.

Những ví dụ trong bài truy cập các thuộc tính metadata cơ bản:

```text
#root.metadata.name
#root.metadata.labels
#root.metadata.labels['tier']
```

Đối tượng gốc là Service của Kubernetes client đang được implementation sử dụng, không phải `ServiceInstance` của Spring Cloud. Vì thế, không viết biểu thức dựa trên giả định có `#root.host`, `#root.port` hoặc `#root.isSecure()` trong ngữ cảnh này.

Biểu thức phải biểu đạt một điều kiện trả về boolean. Với implementation dựa trên client Kubernetes khác nhau, các chi tiết của kiểu đối tượng gốc có thể khác nhau. Ưu tiên các thuộc tính metadata rõ ràng, đồng thời đối chiếu hỗ trợ với phiên bản dependency đã chọn khi áp dụng vào dự án.

Đừng đưa một chuỗi JSONPath, JSON Patch, CEL hoặc lệnh shell vào `filter`. Đây cũng không phải nơi gửi nguyên văn Kubernetes label selector. Một regex đứng riêng không tự trở thành biểu thức lọc Service; cần dùng nó cùng toán tử như `matches`.

### 4.2. Lọc tên bằng regex

Ví dụ chỉ nhận các Service có tên kết thúc bằng `-api`:

```yaml
spring:
  cloud:
    kubernetes:
      discovery:
        filter: "#root.metadata.name matches '^.+-api$'"
```

Trong biểu thức này:

- `#root.metadata.name` lấy tên Service.
- `matches` là toán tử so khớp regex của SpEL.
- `'^.+-api$'` yêu cầu có phần tên phía trước và kết thúc bằng `-api`.

`catalog-api` và `checkout-api` khớp; `catalog-worker` và `api` không khớp. Hậu tố `-api` chỉ là quy ước đặt tên, không chứng minh Service thực sự cung cấp HTTP API hoặc đang khỏe mạnh.

Dấu `#` có ý nghĩa chú thích trong YAML ở các ngữ cảnh không được quote. Vì vậy, luôn đặt biểu thức trong dấu nháy hoặc dùng block scalar. Các ví dụ dùng dấu nháy kép bao toàn biểu thức, còn chuỗi bên trong SpEL dùng dấu nháy đơn để dễ đọc.

### 4.3. Lọc giá trị label bằng điều kiện an toàn khi thiếu metadata label

```yaml
spring:
  cloud:
    kubernetes:
      discovery:
        filter: >-
          #root.metadata.labels != null
          and #root.metadata.labels['tier'] == 'api'
```

`>-` là cách viết YAML nhiều dòng rồi gộp thành một chuỗi. Dòng bắt đầu bằng `#root` trong block này là nội dung biểu thức, không phải chú thích YAML.

Điều kiện đầu kiểm tra map label tồn tại. Toán tử `and` đánh giá ngắn mạch: khi vế trái sai, vế phải không cần được đánh giá. Nhờ đó, việc đọc key trong một map null được tránh. Với map tồn tại nhưng thiếu key `tier`, phép lấy giá trị cho key trả về null và so sánh với `'api'` không khớp.

Có thể đọc label chứa dấu chấm hoặc dấu gạch chéo bằng cú pháp map:

```text
#root.metadata.labels['app.kubernetes.io/part-of'] == 'commerce'
```

Không đổi đoạn trong ngoặc vuông thành một chuỗi truy cập thuộc tính như `labels.app.kubernetes.io/part-of`; đó không còn là cách đọc nguyên một key label.

### 4.4. OR và nhóm điều kiện

Giả sử muốn nhận Service có `tier` là `api` hoặc `worker`:

```yaml
spring:
  cloud:
    kubernetes:
      discovery:
        filter: >-
          #root.metadata.labels != null
          and (#root.metadata.labels['tier'] == 'api'
          or #root.metadata.labels['tier'] == 'worker')
```

Dấu ngoặc làm rõ hai giá trị thay thế thuộc cùng một nhóm. Nếu kết hợp thêm điều kiện về tên, tiếp tục dùng dấu ngoặc để tránh người đọc phải suy đoán độ ưu tiên toán tử.

Các điều kiện đơn giản, dễ giải thích và có thể dự đoán bằng bảng dữ liệu thường thích hợp hơn biểu thức dài. Chỉ dùng khả năng truy cập dữ liệu và toán tử mà phiên bản đang triển khai hỗ trợ; không giả định có bean tùy ý, hàm tùy biến hoặc toàn bộ năng lực của một ngữ cảnh SpEL khác.

Giữ biểu thức trong cấu hình do nhóm triển khai quản lý. Không ghép dữ liệu từ request người dùng thành một biểu thức để đánh giá.

## 5. Kết hợp label và biểu thức trong một cấu hình

Ứng dụng `storefront` chỉ cần khám phá API thuộc hệ thống thương mại, đã được công bố cho khám phá và có hậu tố `-api`:

```yaml
spring:
  application:
    name: storefront
  cloud:
    kubernetes:
      discovery:
        service-labels:
          "[app.kubernetes.io/part-of]": "commerce"
          "[discovery.example.com/enabled]": "true"
        filter: "#root.metadata.name matches '^.+-api$'"
```

Bộ lọc label xác định nhóm nghiệp vụ và trạng thái công bố. Biểu thức bổ sung điều kiện về tên. Service phải thỏa cả hai, không phải chỉ cần thỏa một trong hai.

Giả sử tất cả Service sau cùng nằm trong namespace đang được khám phá và DiscoveryClient có đủ quyền đọc:

| Tên Service | `part-of` | `enabled` | Khớp label | Khớp tên | Được chấp nhận |
| --- | --- | --- | --- | --- | --- |
| `catalog-api` | `commerce` | `true` | Có | Có | Có |
| `checkout-api` | `commerce` | `true` | Có | Có | Có |
| `catalog-worker` | `commerce` | `true` | Có | Không | Không |
| `payment-api` | `commerce` | `false` | Không | Có | Không |
| `metrics-api` | `observability` | `true` | Không | Có | Không |
| `legacy-api` | `commerce` | Thiếu key | Không | Có | Không |

Bảng dùng tên key rút gọn như phần trước. Chỉ `catalog-api` và `checkout-api` thỏa toàn bộ điều kiện. Việc chúng xuất hiện trong kết quả liệt kê không bảo đảm mỗi Service đều có instance sử dụng được ở thời điểm gọi.

Nếu chỉ bật biểu thức `name matches ...`, `metrics-api` cũng có thể khớp tên. Nếu chỉ bật bộ lọc label, `catalog-worker` có thể được chấp nhận. Điều kiện kết hợp cần được thiết kế từ yêu cầu nghiệp vụ thay vì thêm dần mà không biết mỗi điều kiện loại đối tượng nào.

## 6. Kiểm tra bằng Kubernetes API và DiscoveryClient

### 6.1. Quan sát dữ liệu Service trước

Các lệnh sau là ví dụ để thực hành trong cluster của bạn:

```bash
kubectl -n commerce get services --show-labels

kubectl -n commerce get services \
  -l 'app.kubernetes.io/part-of=commerce,discovery.example.com/enabled=true'

kubectl -n commerce get service catalog-api -o yaml
```

Dấu phẩy trong selector của lệnh `kubectl` thể hiện quan hệ AND giữa hai yêu cầu label. Lệnh này giúp kiểm tra phần điều kiện label trên dữ liệu thực tế; nó không chạy biểu thức SpEL của Spring.

Cú pháp xuống dòng bằng `\` trong ví dụ dành cho shell kiểu Bash. Khi dùng PowerShell hoặc terminal khác, có thể viết mỗi lệnh trên một dòng để tránh khác biệt ký tự nối dòng.

Nếu `kubectl` thấy Service nhưng ứng dụng không thấy, chưa thể kết luận bộ lọc sai: tài khoản của người chạy `kubectl` có thể khác ServiceAccount của Pod. Kiểm tra đúng namespace và quyền truy cập được cấp cho ứng dụng.

### 6.2. Đọc kết quả thực tế của DiscoveryClient

Trong môi trường phát triển, thêm một probe nhỏ vào ứng dụng đã có Kubernetes DiscoveryClient được cấu hình:

```java
import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DiscoveryProbeConfiguration {

    @Bean
    ApplicationRunner discoveryProbe(DiscoveryClient discoveryClient) {
        return args -> {
            List<String> serviceIds = discoveryClient.getServices();
            serviceIds.stream()
                    .sorted()
                    .forEach(id -> System.out.println("discovered=" + id));

            List<ServiceInstance> instances =
                    discoveryClient.getInstances("catalog-api");

            for (ServiceInstance instance : instances) {
                System.out.printf("catalog-api instance=%s:%d%n",
                        instance.getHost(), instance.getPort());
            }
        };
    }
}
```

Probe minh họa hai quan sát khác nhau:

1. `getServices()` cho biết những service ID mà client liệt kê.
2. `getInstances("catalog-api")` cho biết các instance client trả về cho một service ID cụ thể.

Probe này chỉ in trạng thái tại thời điểm ứng dụng chạy đoạn khởi tạo. Nó không theo dõi thay đổi liên tục và không gửi HTTP request tới các instance. Không in toàn bộ metadata hoặc Secret chỉ để kiểm tra một điều kiện lọc.

Trong ứng dụng có nhiều DiscoveryClient hoặc CompositeDiscoveryClient, xác định bean nào đang phục vụ lời gọi. Nếu một client khác vẫn trả về service ID cùng tên, kết quả tổng hợp có thể gây hiểu nhầm về hiệu lực bộ lọc Kubernetes.

### 6.3. Kiểm tra cả hành vi liệt kê và tra cứu trực tiếp

Không dùng bộ lọc như lời hứa rằng mọi API khám phá hoặc mọi implementation đều xử lý tên bị loại giống nhau. Với phiên bản và đường đi thực tế của dự án, kiểm tra tối thiểu:

| Quan sát | Điều cần xác nhận |
| --- | --- |
| `getServices()` | Các tên được liệt kê có đúng tập dự kiến không? |
| `getInstances("catalog-api")` | Service được chấp nhận có instance đúng host và port không? |
| `getInstances("catalog-worker")` | Tra cứu trực tiếp một tên bị loại có hành vi gì trong implementation đang dùng? |
| Lời gọi qua LoadBalancer | Đường gọi thực tế có dùng đúng DiscoveryClient và chính sách dự kiến không? |

Phạm vi áp dụng bộ lọc trên đường liệt kê, cache và tra cứu tên cụ thể cần được kiểm tra ở implementation đang dùng. Kết quả rỗng từ `getInstances()` còn có thể do không có endpoint phù hợp hoặc điều kiện readiness; không quy mọi kết quả rỗng cho SpEL.

Nếu yêu cầu là ngăn một workload truy cập một dịch vụ, phải có chính sách truy cập phù hợp. Việc tên Service không xuất hiện trong `getServices()` không chặn một ứng dụng gọi trực tiếp địa chỉ DNS của Service.

## 7. RBAC, namespace và vòng đời cập nhật

### 7.1. Bộ lọc không cấp quyền đọc tài nguyên

DiscoveryClient cần quyền Kubernetes API phù hợp với implementation và tính năng được bật. Việc đọc Service, Endpoints hoặc EndpointSlice có thể đòi hỏi các tài nguyên và thao tác khác nhau. Cấu hình lọc không thay thế Role, ClusterRole hoặc RoleBinding.

Kubernetes RBAC thông thường không phải cơ chế cấp quyền đọc dựa trên việc Service có một label cụ thể. Nếu ServiceAccount có quyền liệt kê Service trong namespace, thêm bộ lọc label ở ứng dụng không tự làm quyền đó hẹp hơn. Phân biệt rõ phạm vi dữ liệu ứng dụng chọn dùng với quyền dữ liệu mà API server cấp.

Nếu cần xác minh quyền, người có quyền impersonation phù hợp có thể kiểm tra:

```bash
kubectl auth can-i list services \
  --as=system:serviceaccount:commerce:storefront \
  -n commerce
```

Đây chỉ là ví dụ kiểm tra quyền `list` đối với Service. Tài khoản `storefront`, namespace và các tài nguyên cần kiểm tra phải khớp triển khai thật; kết quả này không chứng minh toàn bộ cơ chế khám phá đã được cấp đủ quyền.

### 7.2. Thay label của Service và thay biểu thức là hai loại thay đổi

- **Thay label trên Service:** dữ liệu tài nguyên Kubernetes thay đổi. Thời điểm DiscoveryClient phản ánh phụ thuộc cơ chế watch, informer, cache hoặc lần truy vấn tiếp theo của implementation.
- **Thay cấu hình `service-labels` hoặc `filter`:** cấu hình ứng dụng thay đổi. Việc chỉnh nguồn ConfigMap không tự bảo đảm bean DiscoveryClient đang chạy sẽ nhận điều kiện mới.

Với cấu hình ứng dụng, cách dễ dự đoán trong bài thực hành là cập nhật cấu hình rồi rollout ứng dụng theo quy trình triển khai hiện có. Nếu dự án sử dụng refresh cấu hình, cần xác minh chính thuộc tính và bean liên quan hỗ trợ vòng đời đó. Configuration Watcher có thể tham gia thông báo thay đổi cấu hình khi được thiết lập phù hợp, nhưng không nên suy ra rằng nó tự tái tạo mọi thành phần khám phá.

Ngoài cache của lớp khám phá, luồng dùng Spring Cloud LoadBalancer cũng có thể có cache riêng. Vì vậy, không kỳ vọng mọi lời gọi chuyển đích ngay lập tức sau một lần chỉnh label. Quan sát cả kết quả khám phá lẫn đường gọi thực tế và thời gian hội tụ của hệ thống.

## 8. Chẩn đoán lỗi theo dấu hiệu

| Dấu hiệu | Nguyên nhân nên kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Service mong muốn không được liệt kê | Label đặt trên Pod, thiếu label trên Service hoặc giá trị không khớp | Đọc `Service.metadata.labels` và so sánh từng key–value. |
| Tất cả Service biến mất | Nhiều label tạo điều kiện AND quá chặt, sai namespace hoặc thiếu quyền đọc | Kiểm tra phạm vi và quyền trước, sau đó đối chiếu từng điều kiện. |
| Điều kiện OR không hoạt động | Đặt chuỗi `api,worker` trong map `service-labels` | Dùng SpEL với hai phép so sánh nối bằng `or`. |
| Biểu thức gây lỗi khi gặp Service không có label | Truy cập map null hoặc giả định key luôn tồn tại | Thêm điều kiện kiểm tra null và làm rõ chính sách cho key bị thiếu. |
| Ứng dụng báo lỗi parse hoặc evaluate expression | Sai dấu nháy, sai cú pháp SpEL, truy cập thuộc tính không tồn tại hoặc kết quả không phải boolean | Rút biểu thức về phép so sánh đơn giản, kiểm tra lỗi gốc và kiểu Service. |
| Đổi ConfigMap nhưng điều kiện lọc chưa đổi | Cấu hình chưa được nạp lại hoặc bean không được tạo lại | Xác minh cơ chế cập nhật; rollout theo quy trình khi cần. |
| `getServices()` đúng nhưng gọi vẫn thất bại | Không có endpoint sẵn sàng, sai port, lỗi mạng hoặc cache chưa hội tụ | Kiểm tra instance, readiness, cổng và đường gọi. |
| Một tên bị loại vẫn xuất hiện | Có client khác trong kết quả tổng hợp hoặc cấu hình đặt sai thành phần | Xác định DiscoveryClient và môi trường cấu hình đang có hiệu lực. |

Một biểu thức hợp lệ trả về `false` chỉ có nghĩa Service không thỏa điều kiện. Biểu thức không hợp lệ hoặc gây lỗi đánh giá là lỗi cấu hình cần xử lý; không thiết kế hệ thống dựa vào giả định rằng mọi lỗi biểu thức đều được âm thầm chuyển thành `false`.

Khi điều tra, bắt đầu với một Service cụ thể và một điều kiện đơn giản. Sau khi xác nhận namespace, quyền đọc và dữ liệu metadata, mới ghép đủ điều kiện. Điều này giúp phân biệt lỗi phạm vi dữ liệu với lỗi cú pháp hoặc logic của biểu thức.

## 9. Quy ước thiết kế bộ lọc dễ vận hành

### 9.1. Dùng label cho ý nghĩa nghiệp vụ ổn định

Các label như `app.kubernetes.io/part-of` hoặc một key công bố nội bộ giúp thể hiện ý định rõ hơn việc suy luận mọi thứ từ tên Service. Nhóm triển khai phải bảo đảm các Service mới được gắn label theo quy ước; nếu không, chính sách yêu cầu label sẽ chủ động loại các Service thiếu metadata.

Lọc theo tên hữu ích khi có quy ước đặt tên ổn định, nhưng đổi tên Service có thể làm nó mất khỏi tập khám phá. Khi đổi quy ước, rà soát cả biểu thức và các nơi gọi service ID.

### 9.2. Giữ biểu thức nhỏ và có dữ liệu ví dụ

Với mỗi điều kiện, lưu trong tài liệu triển khai một ví dụ được nhận và một ví dụ bị loại. Khi thêm OR, ngoặc hoặc kiểm tra thiếu key, cập nhật bảng dự kiến trước khi rollout.

Nếu một biểu thức dài đang mô phỏng danh mục nhóm dịch vụ phức tạp, cân nhắc chuẩn hóa label để có thể diễn đạt phần lớn yêu cầu bằng các cặp key–value. Cách này giảm phụ thuộc vào chi tiết cấu trúc đối tượng của Kubernetes client.

### 9.3. Dùng đúng công cụ cho từng yêu cầu

| Yêu cầu | Thành phần phù hợp |
| --- | --- |
| Chỉ khám phá nhóm Service liên quan | Bộ lọc label và SpEL của DiscoveryClient |
| Chọn Pod đích phía sau Service | `Service.spec.selector` và endpoint do Kubernetes quản lý |
| Chọn instance cho lời gọi của ứng dụng | Spring Cloud LoadBalancer với nguồn instance phù hợp |
| Giới hạn quyền đọc Kubernetes API | RBAC theo tài nguyên và phạm vi cần thiết |
| Kiểm soát lưu lượng giữa workload | NetworkPolicy khi hạ tầng mạng hỗ trợ, cùng các cơ chế xác thực và phân quyền cần thiết |
| Phát hiện và xử lý thay đổi cấu hình | Cơ chế cấu hình, rollout hoặc refresh đã được dự án xác minh |

Bộ lọc chỉ cần thiết khi ứng dụng thực sự dùng khám phá qua Kubernetes API và cần thu hẹp tập dữ liệu. Một ứng dụng chỉ gọi tên DNS Service cố định có thể không cần bật DiscoveryClient, LoadBalancer hay Configuration Watcher cho yêu cầu đó.

## 10. Bài thực hành tổng hợp

Thực hành trong namespace thử nghiệm với ứng dụng đã cấu hình Kubernetes DiscoveryClient và quyền đọc cần thiết. Các bước dưới đây là nội dung hướng dẫn cho người học, không phải kết quả chạy trên một cluster cụ thể.

1. Tạo hoặc chọn ba Service thử nghiệm: `catalog-api`, `checkout-api` và `catalog-worker`. Mỗi Service có selector và cổng phù hợp với workload thử nghiệm của bạn.
2. Gắn trên cả ba Service hai label: `app.kubernetes.io/part-of=commerce` và `discovery.example.com/enabled=true`.
3. Áp dụng cấu hình kết hợp ở mục 5 rồi triển khai lại ứng dụng gọi.
4. Chạy probe DiscoveryClient. Với phần liệt kê qua bộ lọc, tập dự kiến gồm `catalog-api` và `checkout-api`; `catalog-worker` bị loại bởi tên.
5. Đổi `discovery.example.com/enabled` của `checkout-api` thành `false`. Quan sát thời điểm thay đổi dữ liệu được phản ánh; sau khi hệ thống hội tụ, Service này không còn thỏa bộ lọc label.
6. Đặt lại label thành `true`, sau đó xóa key này khỏi `checkout-api`. Kiểm tra rằng thiếu key cũng không thỏa yêu cầu label.
7. Trong cấu hình thử nghiệm riêng, thay điều kiện hậu tố bằng biểu thức OR theo `tier` ở mục 4.4; gắn label tương ứng rồi xác minh hai nhánh OR và trường hợp thiếu `tier`.
8. Kiểm tra riêng việc gọi `getInstances()` bằng tên bị loại và lời gọi qua LoadBalancer nếu ứng dụng dùng nó. Ghi nhận hành vi của phiên bản đang triển khai.
9. Khôi phục cấu hình và label của môi trường thử nghiệm theo quy trình của nhóm.

Khi ghi kết quả, tách bốn loại quan sát: dữ liệu Service, cấu hình ứng dụng đang có hiệu lực, danh sách service ID và danh sách instance. Một kết quả HTTP thành công hoặc thất bại duy nhất không đủ chứng minh toàn bộ chính sách lọc đúng.

## 11. Tự kiểm tra kiến thức

**Vì sao Service không được khám phá dù Pod có label yêu cầu?**

Bộ lọc xét label của Service. Label Pod chỉ tham gia chọn Pod khi selector của Service sử dụng nó; label không tự sao chép giữa hai loại tài nguyên.

**Hai key trong `service-labels` có tạo phép OR không?**

Không. Các cặp key–value là các điều kiện đồng thời. Muốn có lựa chọn `tier=api` hoặc `tier=worker`, dùng biểu thức boolean hỗ trợ `or` và nhóm điều kiện rõ ràng.

**Vì sao biểu thức cần kiểm tra `metadata.labels != null`?**

Service không nhất thiết có label. Kiểm tra null với `and` giúp tránh truy cập map không tồn tại, đồng thời nêu rõ rằng Service thiếu metadata yêu cầu sẽ bị loại.

**Ẩn tên Service khỏi kết quả khám phá có chặn gọi DNS trực tiếp không?**

Không. Bộ lọc khám phá không thay thế kiểm soát mạng, xác thực hoặc phân quyền. Cần kiểm tra cả đường tra cứu trực tiếp của client và đường gọi thực tế khi thiết kế hệ thống.

**Có cần Configuration Watcher để dùng bộ lọc không?**

Không cần cho cấu hình lọc tĩnh. Chỉ bổ sung cơ chế theo dõi hoặc refresh khi có yêu cầu cập nhật lúc chạy và đã xác minh cách các thành phần liên quan nhận cấu hình mới.

Khi hoàn thành bài, bạn cần giải thích được vì sao từng Service được nhận hoặc bị loại bằng dữ liệu cụ thể: phạm vi khám phá, từng label bắt buộc và kết quả boolean của biểu thức. Đây là cơ sở để triển khai chính sách khám phá rõ ràng và chẩn đoán thay đổi khi ứng dụng chạy trên Kubernetes.
