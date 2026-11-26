# Log tên ứng dụng, namespace, Pod và phiên bản triển khai

Trong chương **Khả năng quan sát** của module **SPRING_CLOUD_KUBERNETES**, một dòng log cần giúp người vận hành trả lời ngay: ứng dụng nào tạo ra sự kiện, ở namespace nào, từ Pod nào và đang chạy phiên bản triển khai nào. Những thông tin này đặc biệt hữu ích khi nhiều replica cùng xử lý yêu cầu hoặc khi hai phiên bản cùng tồn tại trong một đợt rolling update.

Một thông báo như `Cannot discover inventory service` chưa đủ để xác định phạm vi lỗi. Nếu biết nó đến từ `order-api`, namespace `shop`, Pod `order-api-7b8c6d9f54-k2m9q`, phiên bản `1.4.2`, bạn có thể đối chiếu chính xác cấu hình DiscoveryClient, quyền RBAC và thay đổi triển khai liên quan.

Bài học dùng **Spring Boot 3.5.x**, Java 17 trở lên và hệ thống logging mặc định của Spring Boot với Logback. Ứng dụng có thể tích hợp Spring Cloud Kubernetes 3.3.x theo BOM tương thích của dự án. Cách lấy bốn thông tin nhận diện trong bài không yêu cầu ứng dụng tự gọi Kubernetes API.

Sau bài học, bạn có thể:

- Chọn nguồn đáng tin cậy cho tên ứng dụng, namespace, Pod và phiên bản.
- Truyền metadata của Pod vào container bằng Downward API.
- Đưa metadata vào từng sự kiện log JSON qua cấu hình Spring Boot.
- Phân biệt phiên bản ứng dụng, định danh Pod, lần rollout và phiên bản cấu hình.
- Kiểm tra log khi nhiều replica hoặc nhiều phiên bản cùng chạy mà không làm lộ Secret.

## 1. Bốn trường nhận diện phục vụ bốn câu hỏi khác nhau

Đề xuất schema tối thiểu của bài:

| Trường log | Ví dụ | Câu hỏi được trả lời | Nguồn sử dụng trong bài |
| --- | --- | --- | --- |
| `application_name` | `order-api` | Dịch vụ logic nào tạo sự kiện? | `spring.application.name`, được truyền từ label tên ứng dụng |
| `k8s_namespace` | `shop` | Instance thuộc phạm vi triển khai nào? | Downward API: `metadata.namespace` |
| `k8s_pod_name` | `order-api-7b8c6d9f54-k2m9q` | Replica nào tạo sự kiện? | Downward API: `metadata.name` |
| `app_version` | `1.4.2` | Bản ứng dụng được khai báo cho Pod này là gì? | Label `app.kubernetes.io/version` trên Pod |
| `k8s_pod_uid` | `6e3265db-...` | Đây có đúng là cùng một đối tượng Pod không? | Downward API: `metadata.uid`, bổ sung khi cần |

Bốn trường đầu là trọng tâm bài học; UID là thông tin bổ sung để phân biệt một Pod bị xóa rồi được tạo lại với cùng tên. Trong hệ thống có nhiều cluster hoặc nhiều container trong một Pod, có thể bổ sung `cluster_name` và `container_name` theo hợp đồng thu thập log.

Các tên trường dùng dấu gạch dưới ở đây là **schema minh họa của bài**, không phải tên bắt buộc của Kubernetes hoặc OpenTelemetry. Nếu tổ chức đã dùng ECS hay schema khác, hãy ánh xạ một lần sang schema đó và dùng nhất quán trong toàn bộ pipeline.

### 1.1. Tên ứng dụng phải ổn định giữa các replica

`application_name` nên là `order-api`, không phải tên Pod. Nhờ vậy có thể tìm mọi sự kiện của cùng dịch vụ dù Deployment thay Pod hoặc tăng số replica.

Tên Kubernetes Service, tên Deployment và `spring.application.name` có thể khác nhau. Nếu chủ đích dùng cùng tên thì chuẩn hóa trong pipeline triển khai; không mặc định rằng Spring tự đồng bộ cả ba giá trị.

### 1.2. Namespace cần lấy từ Pod đang chạy

Không gán cứng `default` cho mọi môi trường. Cùng một tên ứng dụng có thể xuất hiện trong nhiều namespace. Ghép tên ứng dụng với namespace giúp tránh lẫn log giữa môi trường thử nghiệm, staging và production.

Namespace cũng không tự chứng minh môi trường nghiệp vụ. Nếu cần trường `deployment_environment`, truyền riêng theo quy ước của tổ chức thay vì suy đoán từ tên namespace.

### 1.3. Tên Pod không phải phiên bản phần mềm

Hậu tố trong tên Pod do Deployment quản lý không phải SemVer của ứng dụng. `pod-template-hash` cũng không phải phiên bản ứng dụng hoặc Git commit theo một hợp đồng mặc định.

Một container restart trong cùng Pod có thể giữ nguyên tên và UID của Pod. Vì vậy, khi điều tra restart, cần kết hợp timestamp, restart count và log container trước đó; không suy ra một UID tương đương với một lần chạy JVM duy nhất.

## 2. Luồng dữ liệu nhận diện nên đơn giản

Trong bài, nguồn dữ liệu được bố trí như sau:

```text
Pipeline phát hành
  ├─ chọn image đã được kiểm chứng
  └─ đặt label tên ứng dụng và phiên bản trong Pod template
                         │
                         v
                  Kubernetes tạo Pod
                         │
             Downward API cung cấp metadata
                         │
                         v
        Biến môi trường của container khi khởi động
                         │
                         v
            Spring Boot cấu hình logger JSON
                         │
                         v
        stdout → hệ thống thu thập log → nơi truy vấn
```

Ưu điểm của luồng này là metadata nhận diện không cần chờ ApplicationContext tạo xong, không cần mỗi sự kiện log phải truy vấn API server và không phụ thuộc khả năng discovery có hoạt động hay không.

Downward API cho phép đưa các trường Pod như tên, namespace, UID và một label cụ thể vào container. Đây là khả năng có sẵn của Kubernetes; ứng dụng không cần một Kubernetes Java client chỉ để đọc các giá trị được inject. Xem [Kubernetes: Downward API](https://kubernetes.io/docs/concepts/workloads/pods/downward-api/).

Vì không thực hiện yêu cầu API từ ứng dụng để lấy các trường đó, không cần cấp quyền `get/list/watch pods` cho mục đích nhận diện log này. Những tính năng khác như DiscoveryClient, nạp ConfigMap/Secret qua API hoặc Configuration Watcher vẫn cần đánh giá RBAC theo chức năng và client thực tế.

## 3. Khai báo label đúng trên Pod template

Kubernetes có bộ label khuyến nghị, trong đó `app.kubernetes.io/name` biểu diễn tên ứng dụng và `app.kubernetes.io/version` biểu diễn phiên bản ứng dụng. Label là giá trị do người triển khai cung cấp; Kubernetes không tự xác minh nó khớp với nội dung image. Xem [Kubernetes: Recommended Labels](https://kubernetes.io/docs/concepts/overview/working-with-objects/common-labels/).

Ví dụ Deployment dưới dùng label để làm nguồn cho tên và phiên bản:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
  namespace: shop
  labels:
    app.kubernetes.io/name: order-api
    app.kubernetes.io/version: "1.4.2"
spec:
  replicas: 2
  selector:
    matchLabels:
      app.kubernetes.io/name: order-api
  template:
    metadata:
      labels:
        app.kubernetes.io/name: order-api
        app.kubernetes.io/version: "1.4.2"
    spec:
      containers:
        - name: app
          image: registry.example.com/learning/order-api:1.4.2
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_APPLICATION_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.labels['app.kubernetes.io/name']
            - name: APP_VERSION
              valueFrom:
                fieldRef:
                  fieldPath: metadata.labels['app.kubernetes.io/version']
            - name: K8S_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
            - name: K8S_POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
            - name: K8S_POD_UID
              valueFrom:
                fieldRef:
                  fieldPath: metadata.uid
```

Đây là ví dụ minh họa; cần thay image bằng image ứng dụng có thật và chuẩn bị namespace `shop` trước khi áp dụng. Các cấu hình tài nguyên, probe và security của workload cần theo yêu cầu triển khai của dự án.

Những điểm cần đọc kỹ:

- `fieldRef` tham chiếu metadata của **Pod**, không phải metadata của Deployment.
- Label chỉ đặt ở `metadata.labels` của Deployment sẽ không đủ cho ví dụ này. Phải có label ở `spec.template.metadata.labels` để Pod nhận được nó.
- `SPRING_APPLICATION_NAME` là tên biến môi trường được Spring Boot ánh xạ tới `spring.application.name`.
- `APP_VERSION`, `K8S_NAMESPACE`, `K8S_POD_NAME` và `K8S_POD_UID` là tên do bài học quy ước. Kubernetes không tự tạo chúng nếu bạn chưa khai báo.
- Selector giữ tên ứng dụng ổn định; phiên bản được đặt trên Pod template nhưng không nằm trong selector của ví dụ.

Cách expose tên và namespace qua `env.valueFrom.fieldRef` được minh họa trong [Kubernetes: Expose Pod Information Through Environment Variables](https://kubernetes.io/docs/tasks/inject-data-application/environment-variable-expose-pod-information/).

Không dùng tên Pod tự ghép từ tên Deployment và một hậu tố dự đoán. Cũng không dựa vào giả định rằng `HOSTNAME` luôn bằng tên Pod trong mọi kiểu cấu hình. Downward API biểu đạt trực tiếp ý định cần lấy `metadata.name`.

## 4. Đưa metadata vào log JSON của Spring Boot

Với Spring Boot 3.5 và cấu hình Logback mặc định, có thể dùng `application.yml` như sau:

```yaml
spring:
  application:
    name: "${SPRING_APPLICATION_NAME:order-api}"
  main:
    banner-mode: "off"

logging:
  structured:
    format:
      console: logstash
    json:
      add:
        "[application_name]": "${spring.application.name}"
        "[k8s_namespace]": "${K8S_NAMESPACE:local}"
        "[k8s_pod_name]": "${K8S_POD_NAME:local-process}"
        "[app_version]": "${APP_VERSION:local}"
        "[k8s_pod_uid]": "${K8S_POD_UID:local}"
```

`logging.structured.format.console=logstash` chọn JSON cho console. Nhóm `logging.structured.json.add` bổ sung các trường tĩnh vào sự kiện được formatter này ghi. Các thuộc tính tương ứng có trong [Spring Boot: Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html).

Các khóa map được viết dạng `"[application_name]"` thay vì `application_name` để giữ nguyên dấu gạch dưới khi Spring Boot bind cấu hình. Dấu ngoặc vuông thuộc cú pháp cấu hình, không xuất hiện trong tên trường JSON đầu ra. Với YAML, cần giữ cả dấu nháy quanh khóa có ngoặc. Quy tắc bảo toàn khóa map được mô tả tại [Spring Boot: Binding Maps](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.maps).

Ví dụ cố ý dùng tên trường phẳng để người học dễ kiểm tra đầu ra và tránh nhầm dấu chấm trong tên trường với object JSON lồng nhau. `logstash` ở đây là định dạng; ứng dụng không bắt buộc phải kết nối trực tiếp tới một tiến trình Logstash để ghi được JSON.

Các giá trị `local` và `local-process` giúp chạy trên máy phát triển khi chưa có biến môi trường Kubernetes. Trong một môi trường Kubernetes thật, thấy các giá trị này cần được coi là dấu hiệu kiểm tra lại manifest hoặc pipeline. Không để giá trị mặc định che việc thiếu metadata của production.

Cấu hình tắt banner nhằm giữ phần console được Spring Boot quản lý tập trung vào sự kiện log. Nó không chuyển mọi `System.out.println`, output của script entrypoint hoặc lỗi JVM trước khi logging khởi tạo thành JSON.

### 4.1. Đặt cấu hình ở nơi logger đọc được khi khởi động

Đặt phần cấu hình logging nền tảng trong cấu hình được nạp sớm, chẳng hạn `application.yml` đóng gói cùng ứng dụng, và nhận giá trị nhận diện từ biến môi trường. Không chờ đến `@PostConstruct` mới sửa pattern hoặc bổ sung metadata cho những sự kiện đã phát sinh trước đó.

Nếu ứng dụng dùng một `logback-spring.xml` tùy biến, chỉ thêm các thuộc tính trên chưa bảo đảm appender riêng sẽ đổi encoder. Phải kiểm tra appender có sử dụng structured formatter/encoder tương ứng của Spring Boot. Hướng dẫn và giới hạn này được nêu trong [Spring Boot: Structured Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html#features.logging.structured).

Không tự ghép JSON bằng chuỗi như `"{\"message\":\"" + message + "\"}"`. Dấu nháy, xuống dòng hoặc exception có thể làm hỏng bản ghi. Hãy để JSON formatter xử lý escape và serialization.

### 4.2. Một bản ghi mong đợi

Đầu ra dưới đây được rút gọn và xuống dòng để dễ đọc. Trong console thực tế, một sự kiện JSON nên được phát thành một bản ghi trên một dòng:

```json
{
  "@timestamp": "2026-11-24T03:15:20.104Z",
  "level": "INFO",
  "logger_name": "example.observability.DeploymentIdentityLog",
  "thread_name": "main",
  "message": "Deployment identity is available",
  "event": "deployment_identity",
  "application_name": "order-api",
  "k8s_namespace": "shop",
  "k8s_pod_name": "order-api-7b8c6d9f54-k2m9q",
  "app_version": "1.4.2",
  "k8s_pod_uid": "6e3265db-731d-4e99-a30e-4f7ff7be5a83"
}
```

Một số trường khác của formatter có thể xuất hiện ngoài các trường đã rút gọn trên. Đặc biệt, `@version` của định dạng Logstash, nếu xuất hiện, là thông tin định dạng log; đừng nhầm nó với `app_version` của ứng dụng.

## 5. Ghi sự kiện nghiệp vụ mà không lặp metadata ở mọi nơi

Khi formatter đã thêm metadata cố định, mã Java chỉ cần ghi nội dung sự kiện. Ví dụ một component phát sự kiện nhận diện khi Spring chạy các runner:

```java
package example.observability;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public final class DeploymentIdentityLog implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(DeploymentIdentityLog.class);

    @Override
    public void run(ApplicationArguments args) {
        log.atInfo()
                .addKeyValue("event", "deployment_identity")
                .log("Deployment identity is available");
    }
}
```

Lớp này đặt trong phạm vi component scan của ứng dụng. Sự kiện cho biết runner đã thực thi và giúp kiểm tra metadata; nó không phải phép kiểm chứng rằng mọi dependency đều healthy hay tất cả runner khác đã hoàn tất.

SLF4J 2 hỗ trợ fluent API và cặp key-value cho sự kiện, được mô tả tại [SLF4J User Manual](https://www.slf4j.org/manual.html). Với formatter JSON tương ứng, dùng trường `event` ổn định giúp truy vấn dễ hơn việc phân tích lại câu message.

Các log HTTP, scheduler hoặc listener đi qua cùng appender cũng nhận metadata tĩnh từ cấu hình. Không cần thêm `application_name` và `k8s_pod_name` bằng tay ở mỗi câu `log.info(...)`.

Tránh dùng các tên trường nhận diện cố định làm key-value tùy ý từ input người dùng. Ví dụ request header không được phép tự ghi đè `k8s_namespace` hoặc `app_version`; nguồn của chúng phải là metadata triển khai đã được kiểm soát.

## 6. Vì sao không đặt metadata tĩnh vào MDC một lần ở main thread?

Một cách dễ gây lỗi là gọi:

```java
MDC.put("k8s_pod_name", podName);
```

chỉ một lần khi ứng dụng khởi động rồi kỳ vọng mọi thread đều có giá trị đó. Với Logback, MDC gắn với ngữ cảnh của thread; thread xử lý HTTP, thread pool, scheduler hoặc tác vụ bất đồng bộ không mặc nhiên chia sẻ toàn bộ MDC của main thread. Xem [Logback: Mapped Diagnostic Context](https://logback.qos.ch/manual/mdc.html).

Vì vậy, bài học chia ngữ cảnh thành hai loại:

| Loại ngữ cảnh | Ví dụ | Cách đưa vào log |
| --- | --- | --- |
| Cố định cho một tiến trình/container | Tên ứng dụng, namespace, Pod, phiên bản | Cấu hình formatter hoặc cơ chế enrichment tĩnh |
| Theo một yêu cầu hoặc tác vụ | Request ID, trace ID, mã thao tác | Cơ chế context propagation/MDC phù hợp với mô hình thực thi |

Nếu dùng MDC cho request, cần thiết lập và dọn ngữ cảnh đúng vòng đời, đồng thời truyền ngữ cảnh qua các ranh giới bất đồng bộ theo framework đang dùng. Trong ứng dụng reactive, không giả định một request gắn với duy nhất một thread.

Bài học không yêu cầu bạn tự viết filter chỉ để lặp lại metadata tĩnh. Trace ID cũng không thay thế tên Pod hoặc phiên bản: trace mô tả đường đi của công việc, còn các trường triển khai xác định instance nào đã xử lý nó.

## 7. Phiên bản triển khai phải có nguồn và ý nghĩa rõ ràng

Trong ví dụ, `app_version` được hiểu là **phiên bản ứng dụng mà pipeline khai báo cho Pod**, lấy từ label. Muốn trường này đáng tin, pipeline phải đảm bảo label và artifact được phát hành cùng nhau.

| Giá trị | Nên hiểu là gì? | Điều không nên suy ra |
| --- | --- | --- |
| `app.kubernetes.io/version` | Phiên bản ứng dụng do người triển khai công bố | Kubernetes đã kiểm tra code bên trong image |
| Image tag `1.4.2` | Tên tham chiếu image theo quy ước registry/pipeline | Nội dung tag không thể bị thay đổi trong mọi registry |
| Image digest | Định danh nội dung image theo digest | Tự động có sẵn qua mọi trường Downward API |
| Build version hoặc Git commit | Dấu vết artifact được tạo ở bước build | Luôn trùng label nếu pipeline cấu hình sai |
| Deployment revision | Mốc thay đổi do cơ chế Deployment quản lý | Chính là phiên bản phần mềm hoặc Git commit |
| `config_revision` | Bản cấu hình ứng dụng đã áp dụng | Chính là phiên bản image đang chạy |

### 7.1. Đồng bộ phiên bản trong pipeline

Một quy trình phát hành nên lấy một nguồn release đã xác định rồi tạo image reference và label phiên bản một cách nhất quán. Trong triển khai yêu cầu tái lập chính xác, tham chiếu image theo digest giúp giảm sự mơ hồ của tag có thể được ghi lại.

Nếu cần log cả phiên bản build thực tế và phiên bản khai báo, dùng hai trường khác nhau, chẳng hạn `build_version` và `app_version`. Khi chúng không khớp, điều tra pipeline hoặc artifact; không âm thầm ghi đè giá trị này bằng giá trị kia.

Không tự đọc phiên bản từ tên Pod, PID hay thời gian khởi động. Những dữ liệu đó mô tả instance và thời điểm chạy, không xác định nội dung phần mềm.

### 7.2. Không biến version thành selector cố định

Trong ví dụ, `spec.selector.matchLabels` chỉ chứa tên ứng dụng; Pod template có thêm version để tìm kiếm và nhận diện. Mỗi lần thay version, không cần sửa selector cố định của Deployment.

Rolling update xuất phát từ thay đổi Pod template, không phải chỉ từ việc sửa label ở metadata ngoài cùng của Deployment. Hãy cập nhật image và metadata thuộc Pod template theo cùng thay đổi phát hành. Có thể đối chiếu cơ chế này trong [Kubernetes: Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/).

### 7.3. Biến môi trường không phải metadata cập nhật liên tục

Giá trị được inject vào môi trường container không phải subscription theo dõi thay đổi label. Sửa label của một Pod đang chạy không làm JVM tự nhận `APP_VERSION` mới. Với định danh release, giữ giá trị cố định theo tiến trình là lựa chọn phù hợp.

Nếu muốn chạy bản mới, phát hành image và Pod mới qua luồng rollout. Đổi nhãn version trên một Pod đang chạy code cũ có thể làm sai thông tin ở hệ thống thu thập log, nhất là khi collector cũng đọc label hiện tại của Pod.

## 8. Liên hệ với các tính năng Spring Cloud Kubernetes

### 8.1. DiscoveryClient và Spring Cloud LoadBalancer

Khi DiscoveryClient không tìm được dịch vụ hoặc lời gọi qua LoadBalancer thất bại, log nên nhận diện **ứng dụng và Pod gọi đi** bằng bốn trường nền tảng. Tên dịch vụ đích cần nằm ở trường riêng như `target_service`.

Ví dụ quy ước một sự kiện lỗi gồm:

```json
{
  "event": "downstream_call_failed",
  "application_name": "order-api",
  "k8s_namespace": "shop",
  "k8s_pod_name": "order-api-7b8c6d9f54-k2m9q",
  "app_version": "1.4.2",
  "target_service": "inventory-service",
  "failure_kind": "NO_AVAILABLE_INSTANCE"
}
```

Đây là phần trường nghiệp vụ minh họa, không phải schema lỗi tự động được mọi client sinh ra. Tránh đổi `application_name` thành tên downstream, vì như vậy sẽ mất thông tin ứng dụng nào thực sự phát log.

### 8.2. ConfigMap, Secret và Configuration Watcher

Ứng dụng có thể giữ nguyên image `1.4.2` nhưng áp dụng một cấu hình mới. Đừng thay `app_version` thành phiên bản ConfigMap. Khi cần theo dõi reload, ghi sự kiện riêng sau khi áp dụng thành công:

```java
log.atInfo()
        .addKeyValue("event", "config_applied")
        .addKeyValue("config_revision", "rules-2026-11-24-02")
        .log("Validated configuration was applied");
```

Đoạn này nằm trong mã xử lý cấu hình của ứng dụng, tại thời điểm dữ liệu đã được kiểm tra và áp dụng. `config_revision` là mã phiên bản cấu hình do quy trình của ứng dụng quản lý; ví dụ không coi nó là tính năng tự động của Configuration Watcher.

Log từ watcher và log từ ứng dụng nhận thông báo là hai nguồn khác nhau. Metadata của watcher phải nhận diện chính watcher. Để biết instance đích đã đổi cấu hình, tìm sự kiện áp dụng thành công từ đúng Pod ứng dụng; một thông báo gửi đi thành công chưa chứng minh mọi Pod đã dùng bản mới.

Không dùng sự kiện `config_applied` để in giá trị Secret, token, mật khẩu hoặc toàn bộ Spring Environment. Thông tin cần giữ là cấu hình nào đã được áp dụng, kết quả gì và tại instance nào.

### 8.3. Thông tin Pod trong Actuator không tự trở thành metadata log

Spring Cloud Kubernetes có thể cung cấp thông tin Pod cho các chức năng của nó, nhưng điều đó không đồng nghĩa console appender tự có đủ trường theo schema của bài. Log enrichment vẫn cần cấu hình rõ ràng ở ứng dụng hoặc collector.

Không bật discovery, watcher hoặc cấp quyền đọc Pod qua API chỉ để bổ sung namespace vào log. Chọn tính năng Spring Cloud Kubernetes theo nhu cầu nghiệp vụ và triển khai; dùng Downward API cho nhu cầu nhận diện đơn giản này.

## 9. Trách nhiệm của ứng dụng và hệ thống thu thập log

Ứng dụng trong bài ghi JSON ra console. Container runtime và cơ chế logging của Kubernetes xử lý luồng `stdout`/`stderr`; hệ thống thu thập có thể đọc và chuyển tiếp tới nơi lưu trữ tập trung. Kiến trúc và cách xem log được mô tả tại [Kubernetes: Logging Architecture](https://kubernetes.io/docs/concepts/cluster-administration/logging/).

Một pipeline thu thập nên quy định rõ:

1. Có parse JSON của ứng dụng thành trường truy vấn được hay chỉ lưu nguyên chuỗi trong `message`?
2. Metadata của collector và của ứng dụng dùng cùng tên trường hay có bước ánh xạ?
3. Khi hai nguồn có giá trị khác nhau, giá trị nào được giữ và có phát hiện xung đột không?
4. Có bảo toàn timestamp sự kiện của ứng dụng, hay chỉ còn timestamp tiếp nhận log?
5. Có lưu log đủ lâu sau khi Pod bị xóa để điều tra rollout hoặc restart không?

Ví dụ, ứng dụng ghi `k8s_pod_name`, còn collector ghi `kubernetes.pod.name`. Hai trường có thể cùng biểu diễn một dữ kiện nhưng không nên được hiểu là hai Pod khác nhau. Chọn schema đích và ánh xạ có chủ đích.

Giữ nội dung JSON hợp lệ trước khi collector nhận. Không thêm prefix text vào trước object JSON ở appender rồi kỳ vọng parser vẫn coi cả dòng là JSON. Nếu công cụ xem log thêm prefix để phân biệt nguồn, đó là định dạng hiển thị của công cụ; cần phân biệt nó với payload gốc của container.

Pod name và Pod UID có nhiều giá trị khác nhau theo thời gian. Có thể lưu chúng để điều tra, nhưng không mặc nhiên đưa mọi trường thành nhãn index hoặc nhãn time series. Chính sách index, cardinality và retention phải phù hợp với backend đang dùng.

## 10. Kiểm tra metadata ở local và trong Kubernetes

Các lệnh dưới là hướng dẫn thực hành trong môi trường của người học. `POD_NAME` cần thay bằng tên Pod thật; không yêu cầu tạo thêm quyền ghi cho service account của ứng dụng.

### 10.1. Kiểm tra định dạng trên máy phát triển

Khi chạy local không có các biến môi trường Kubernetes, một sự kiện đi qua formatter cần có:

```text
application_name = order-api
k8s_namespace    = local
k8s_pod_name     = local-process
app_version     = local
```

Nếu thấy nguyên `${K8S_NAMESPACE:local}` trong log, cần kiểm tra đường nạp cấu hình và placeholder. Nếu log vẫn là text, xem phiên bản Spring Boot, khóa cấu hình và appender tùy biến; không chỉ kết luận rằng JSON collector bị lỗi.

### 10.2. Đối chiếu log với chính Pod

Trong PowerShell hoặc terminal có `kubectl`, chạy:

```powershell
kubectl -n shop get pods -l app.kubernetes.io/name=order-api --show-labels

kubectl -n shop get pod POD_NAME -o yaml

kubectl -n shop logs POD_NAME -c app --tail=50
```

Từ thông tin Pod, đối chiếu `metadata.name`, `metadata.namespace`, `metadata.uid` và label `app.kubernetes.io/version` với JSON. Khi chỉ cần đọc metadata, tránh sao chép toàn bộ YAML có thông tin không cần thiết vào báo cáo hoặc kênh trao đổi công khai.

Nếu container trước đó đã kết thúc và log còn được giữ, kiểm tra:

```powershell
kubectl -n shop logs POD_NAME -c app --previous --tail=50
```

`--previous` là log của lần container trước trong Pod đó, không phải lệnh xem toàn bộ lịch sử mọi Pod từng bị Deployment thay thế. Log tập trung vẫn cần thiết nếu muốn truy tìm sự kiện sau khi Pod đã bị xóa.

### 10.3. Kiểm tra rolling update và nhiều replica

Trong môi trường thử nghiệm, triển khai bản `1.4.3` bằng cách cập nhật image cùng label phiên bản ở Pod template theo quy trình phát hành. Trong thời gian chuyển đổi, tình huống mong đợi là:

| Nhóm Pod | `application_name` | `k8s_namespace` | `k8s_pod_name` | `app_version` |
| --- | --- | --- | --- | --- |
| Pod cũ | `order-api` | `shop` | Tên Pod cũ | `1.4.2` |
| Pod mới | `order-api` | `shop` | Tên Pod mới | `1.4.3` |

Việc hai phiên bản cùng xuất hiện trong log ở giai đoạn này là bình thường. Truy vấn chỉ theo tên ứng dụng sẽ trộn hai nhóm; muốn tìm lỗi mới sau phát hành cần thêm khoảng thời gian, namespace và `app_version`.

Có thể xem log của các Pod đang khớp label:

```powershell
kubectl -n shop logs -l app.kubernetes.io/name=order-api -c app --since=10m --tail=100
```

Đầu ra gộp không thay thế việc kiểm tra từng Pod khi nghi một replica lỗi. Thời gian log được giữ và phạm vi Pod còn tồn tại giới hạn kết quả của `kubectl logs`.

### 10.4. Ma trận kiểm tra đầu ra

| Tình huống | Điều mong đợi |
| --- | --- |
| Hai replica cùng phiên bản | Cùng tên ứng dụng, namespace, version; khác Pod name/UID |
| Cùng ứng dụng ở hai namespace | `application_name` giống nhau; `k8s_namespace` phân biệt rõ |
| Log từ request hoặc scheduler | Vẫn có đủ metadata tĩnh dù thread không phải `main` |
| Rolling update | Mỗi Pod giữ đúng phiên bản được khai báo cho bản nó chạy |
| Thiếu label version trong Pod template | Phát hiện metadata thiếu/rỗng hoặc không đúng; sửa pipeline |
| Container restart trong cùng Pod | Có thể giữ tên và UID Pod; phân biệt bằng thời gian và log `--previous` |
| Reload ConfigMap thành công | `app_version` giữ nguyên; `config_revision` riêng phản ánh bản được áp dụng |
| Collector thêm metadata | Không có xung đột hoặc giá trị đè lẫn nhau ngoài chính sách đã định |

Placeholder mặc định xử lý trường hợp không tìm thấy thuộc tính; đừng mặc định nó là phép kiểm tra mọi chuỗi rỗng, sai định dạng hoặc sai nội dung. Pipeline và kiểm tra triển khai cần bắt được các trường hợp đó.

## 11. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Namespace luôn là `default` | Giá trị bị gán cứng thay vì lấy từ Pod | Dùng `metadata.namespace` và đối chiếu Pod thật |
| Không có `APP_VERSION` đúng | Label chỉ nằm trên Deployment, không nằm trên Pod template | Đặt label ở `spec.template.metadata.labels` |
| Log main có metadata nhưng log HTTP thiếu | Chỉ đặt MDC ở thread khởi động | Đưa metadata tĩnh vào formatter hoặc cơ chế enrichment chung |
| Version log khác artifact | Pipeline cập nhật label và image không nhất quán | Kiểm tra nguồn release, image thực tế và build metadata |
| Mọi Pod cùng một tên trong log | Gán cứng tên Pod hoặc nhầm tên Deployment | Lấy `metadata.name` qua Downward API |
| Sửa label mà log tiến trình không đổi | Nhầm môi trường container với cơ chế cập nhật liên tục | Giữ metadata release cố định; rollout Pod mới khi phát hành |
| Nhìn `@version=1` rồi tưởng đang chạy bản 1 | Nhầm phiên bản định dạng Logstash với version ứng dụng | Truy vấn trường `app_version` riêng |
| Mỗi dòng là một chuỗi JSON nằm trong JSON khác | Collector hoặc formatter đã serialize thêm một lần | Xác định nơi parse và serialize, loại bước bọc thừa |
| Log JSON hỏng ở message có dấu nháy | Tự ghép JSON bằng chuỗi | Dùng formatter/encoder JSON |
| Thấy Pod của watcher trong log rồi tưởng là Pod ứng dụng | Không phân biệt nguồn phát và đối tượng nhận thông báo | Giữ tên ứng dụng/Pod của nguồn phát, dùng trường target riêng |

Bộ metadata nhận diện chỉ hữu ích khi nguồn dữ liệu đáng tin, tên trường nhất quán và giá trị đi theo đúng sự kiện. Với ứng dụng Spring trên Kubernetes, việc lấy thông tin từ Pod bằng Downward API rồi thêm vào formatter từ lúc khởi động tạo nền tảng rõ ràng để điều tra discovery, RBAC, cập nhật cấu hình và sự cố giữa các phiên bản triển khai.
