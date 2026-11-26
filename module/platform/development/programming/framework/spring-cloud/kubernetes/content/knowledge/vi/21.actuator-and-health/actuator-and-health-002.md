# HealthIndicator liên quan tới Kubernetes và khám phá dịch vụ

## Mục tiêu và bối cảnh

Trong chương **Actuator và sức khỏe** của module **SPRING_CLOUD_KUBERNETES**, bài này giúp bạn đọc đúng tín hiệu health khi ứng dụng Spring chạy trên Kubernetes: đâu là thông tin về Pod, đâu là kết quả kiểm tra DiscoveryClient và đâu mới là bằng chứng dịch vụ đích phục vụ được yêu cầu.

Giả sử `order-service` gọi `catalog` qua Spring Cloud LoadBalancer. Kubernetes vẫn thấy container chạy, nhưng người dùng không xem được sản phẩm. Một phản hồi `UP` chỉ có ý nghĩa khi biết phép kiểm tra đứng sau nó. Bạn cần lần theo ba câu hỏi:

1. Tiến trình của `order-service` có hoạt động và sẵn sàng nhận lưu lượng không?
2. Cơ chế khám phá dịch vụ có trả về thông tin phù hợp không?
3. Đường gọi thật tới `catalog` có thành công không?

Bài học dùng ví dụ Spring Boot 3.5, Spring Cloud Commons 4.3 và Spring Cloud Kubernetes 3.3; các dependency Spring Cloud được quản lý bởi BOM tương thích. Khi dùng dòng khác, đối chiếu lại tên contributor, điều kiện tự cấu hình và package Java theo phiên bản đó. Các đoạn cấu hình dưới đây là ví dụ để đưa vào ứng dụng thực hành, không phải một dự án triển khai hoàn chỉnh.

## 1. Tách các lớp sức khỏe trước khi đọc Actuator

| Tín hiệu | Câu hỏi được trả lời | Điều chưa chứng minh |
| --- | --- | --- |
| Container đang chạy, Pod có phase `Running` | Kubernetes đã khởi chạy workload đến đâu? | Ứng dụng đã sẵn sàng phục vụ |
| `livenessState` | Trạng thái sống nội bộ của ứng dụng là gì? | API Kubernetes và các dịch vụ phụ thuộc đều tốt |
| `readinessState` | Ứng dụng đang chấp nhận lưu lượng theo trạng thái availability hay không? | Mọi nghiệp vụ và dependency đều đã được kiểm tra |
| Contributor `kubernetes` | Ứng dụng nhận biết bối cảnh Kubernetes/Pod như thế nào? | Toàn bộ cluster, node hoặc control plane đang khỏe |
| `discoveryComposite` / `discoveryClient` | Các phép kiểm tra discovery đã cấu hình cho kết quả gì? | Dịch vụ `catalog` có instance dùng được và gọi HTTP thành công |
| Kiểm tra một yêu cầu nghiệp vụ | Đường gọi cụ thể có thành công trong điều kiện kiểm tra không? | Mọi đường gọi khác đều thành công |

Spring Boot cung cấp hai nhóm probe `liveness` và `readiness` dựa trên application availability. Khi định nghĩa thêm health group, chỉ đưa vào các contributor phục vụ đúng quyết định của nhóm đó. Xem [Spring Boot: Kubernetes Probes](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

Luồng quan sát có thể hình dung như sau:

~~~mermaid
flowchart TD
    K[Kubelet] --> L["GET /actuator/health/liveness"]
    K --> R["GET /actuator/health/readiness"]
    O[Người vận hành] --> P["GET /actuator/health/platform"]
    P --> M["kubernetes: bối cảnh Pod"]
    P --> D["discoveryComposite: tín hiệu discovery"]
    C[Luồng nghiệp vụ] --> LB[Spring Cloud LoadBalancer]
    LB --> I[Danh sách instance từ discovery]
    I --> T[Gọi thực tế tới catalog]
~~~

Sơ đồ tách đường probe và đường nghiệp vụ để bạn kiểm tra từng giả thuyết. Nó không hàm ý rằng health endpoint tự thực hiện toàn bộ đường gọi qua LoadBalancer.

## 2. Contributor Kubernetes phản ánh điều gì?

Pod Health Indicator của Spring Cloud Kubernetes có thể cung cấp tên/IP Pod, namespace, service account, tên/IP node và dấu hiệu ứng dụng đang chạy bên trong hay bên ngoài Kubernetes. Contributor này phụ thuộc vào các module, bean và điều kiện môi trường thực tế. Không nên kỳ vọng thêm Actuator là luôn có mọi trường metadata. Xem [Pod Health Indicator, dòng 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/pod-health-indicator.html).

Thông tin này hữu ích khi đối chiếu một lỗi discovery với danh tính workload:

- Ứng dụng tưởng rằng nó ở namespace nào?
- Pod sử dụng service account nào?
- Bản ghi log và health có thuộc cùng một replica không?
- Bạn có đang kiểm tra nhầm tiến trình chạy local thay vì Pod trong cluster không?

**Giới hạn diễn giải:** metadata về Pod không phải bản xác nhận sức khỏe cluster. Chẳng hạn, nhận biết được namespace `health-lab` không chứng minh service account có quyền liệt kê Service trong namespace đó. Tên node xuất hiện cũng không thay cho kiểm tra condition của Node.

Các giá trị đã được đọc hoặc giữ trong bộ nhớ còn có thể tồn tại khi kết nối API gặp lỗi. Vì vậy, cần xác định implementation thực hiện thao tác nào trước khi diễn giải `UP` thành “API server vừa được gọi thành công”.

Bạn có thể tắt riêng contributor này:

~~~yaml
management:
  health:
    kubernetes:
      enabled: false
~~~

Tắt health contributor không đồng nghĩa tắt chức năng DiscoveryClient, đọc ConfigMap hoặc đọc Secret. Nếu một health group đang `include: kubernetes`, hãy sửa membership của nhóm cho khớp trước khi khởi động lại.

## 3. DiscoveryClientHealthIndicator và contributor tổng hợp

### 3.1 Phép kiểm tra mặc định

Spring Cloud Commons cung cấp `DiscoveryClientHealthIndicator` và `DiscoveryCompositeHealthContributor`. Trong bố cục thường gặp, Actuator hiển thị một contributor `discoveryComposite` chứa thành phần con `discoveryClient`; contributor tổng hợp cũng có thể chứa các discovery indicator khác.

Cấu hình điều khiển indicator mặc định:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          enabled: true
          include-description: false
          use-services-query: true
        composite-indicator:
          enabled: true
~~~

Với `use-services-query: true`, indicator dùng `DiscoveryClient.getServices()`. Khi đổi thành `false`, nó gọi `DiscoveryClient.probe()`. Cờ `include-description` điều khiển mô tả của kết quả health, không phải cơ chế phân quyền truy cập endpoint. Xem [Spring Cloud Commons: Health Indicators](https://docs.spring.io/spring-cloud-commons/reference/4.3/spring-cloud-commons/common-abstractions.html#_health_indicators).

Hai phép gọi cần được phân biệt:

| Phép gọi | Loại dữ liệu mong đợi | Ví dụ câu hỏi |
| --- | --- | --- |
| `getServices()` | Các service ID mà client biết | Có những tên dịch vụ nào trong phạm vi discovery? |
| `getInstances("catalog")` | Các instance ứng với service ID | Client hiện biết địa chỉ nào của `catalog`? |

Một danh sách có tên `catalog` không cho biết `catalog` còn endpoint sẵn sàng. Một danh sách instance không rỗng cũng chưa xác nhận đường mạng, TLS, xác thực hoặc nghiệp vụ của instance đó.

### 3.2 Khi nào UP, DOWN hoặc UNKNOWN?

Trong implementation Commons 4.3.0 được tham chiếu:

- Chưa nhận tín hiệu khởi tạo discovery: indicator trả `UNKNOWN`.
- Đã khởi tạo, phép gọi kiểm tra thành công: trả `UP`.
- Phép gọi phát sinh exception: trả `DOWN`.

Nhánh gọi `getServices()` không đòi danh sách phải có phần tử mới trả `UP`. Đây là lý do `"services": []` có thể đi cùng `"status": "UP"`. Xem [mã nguồn DiscoveryClientHealthIndicator 4.3.0](https://raw.githubusercontent.com/spring-cloud/spring-cloud-commons/v4.3.0/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/health/DiscoveryClientHealthIndicator.java).

Diễn giải cho tình huống `order-service`:

| Kết quả quan sát | Kết luận có thể rút ra | Việc cần kiểm tra tiếp |
| --- | --- | --- |
| Discovery `UP`, không có service ID | Phép kiểm tra hoàn tất mà không ném exception | Namespace, bộ lọc và danh sách Service thật |
| Discovery `UP`, có `catalog` | Client thấy tên dịch vụ | Instance, trạng thái ready và port |
| Discovery `DOWN`, có lỗi `Forbidden` trong log | Một thao tác đã bị từ chối quyền | Service account, resource, verb, namespace |
| Discovery `UNKNOWN` lúc khởi động | Indicator chưa xác nhận đã khởi tạo | Tiến trình khởi tạo, sự kiện và implementation |
| Discovery `UP` trong lúc API gián đoạn | Phép kiểm tra hiện chưa phát hiện lỗi | Client có đọc cache/informer hoặc trạng thái cũ không? |

Bảng là hướng chẩn đoán, không phải bảo đảm mọi client phản ứng giống nhau. Fabric8, Kubernetes Java Client và HTTP DiscoveryClient có đường lấy dữ liệu khác nhau. Với HTTP DiscoveryClient, cần phân biệt lỗi ứng dụng tới DiscoveryServer và lỗi DiscoveryServer tới Kubernetes API.

### 3.3 probe() không mặc nhiên rẻ hơn

`use-services-query: false` có thể hữu ích khi liệt kê catalog quá tốn kém. Tuy nhiên, implementation mặc định của `DiscoveryClient.probe()` vẫn gọi `getServices()`. Chỉ implementation ghi đè nó bằng thao tác nhẹ hơn mới tạo ra khác biệt tương ứng. Xem [hợp đồng DiscoveryClient 4.3.0](https://raw.githubusercontent.com/spring-cloud/spring-cloud-commons/v4.3.0/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/DiscoveryClient.java).

Do đó, trước khi đổi cờ, hãy xác định client được inject và đo thời gian kiểm tra. Không suy rằng cờ này tạo một lệnh ping TCP, gọi endpoint nghiệp vụ, hoặc chứng minh dữ liệu discovery mới được đồng bộ.

Nếu muốn ngừng riêng phép kiểm tra mặc định:

~~~properties
spring.cloud.discovery.client.health-indicator.enabled=false
~~~

Nếu muốn ngừng contributor tổng hợp:

~~~properties
spring.cloud.discovery.client.composite-indicator.enabled=false
~~~

Hai cờ trên khác với việc tắt toàn bộ service discovery. Khi tắt, đối chiếu lại các health group có tham chiếu tới contributor vừa bỏ.

## 4. Đọc cây health thay vì chỉ nhìn trạng thái gốc

Ví dụ dưới đây đã rút gọn, giả định người gọi được xem chi tiết và các contributor tương ứng tồn tại:

~~~json
{
  "status": "UP",
  "components": {
    "kubernetes": {
      "status": "UP"
    },
    "discoveryComposite": {
      "status": "UP",
      "components": {
        "discoveryClient": {
          "status": "UP",
          "details": {
            "services": ["order-service", "catalog"]
          }
        }
      }
    },
    "livenessState": {
      "status": "UP"
    },
    "readinessState": {
      "status": "UP"
    }
  }
}
~~~

`status` ở cấp gốc là kết quả tổng hợp, còn `components` thể hiện các thành phần và composite lồng nhau. Chi tiết có thể bị ẩn tùy chính sách hiển thị. API cũng hỗ trợ đường dẫn xuống thành phần con. Xem [Actuator Health API](https://docs.spring.io/spring-boot/3.5/api/rest/actuator/health.html).

Với cây minh họa này, các đường cần phân biệt là:

~~~text
/actuator/health
/actuator/health/kubernetes
/actuator/health/discoveryComposite
/actuator/health/discoveryComposite/discoveryClient
/actuator/health/liveness
/actuator/health/readiness
~~~

`liveness` và `readiness` ở đây là health group; `livenessState` và `readinessState` là ID contributor. `discoveryComposite/discoveryClient` là đường đi qua một composite. Đọc cây của ứng dụng thực tế trước khi dùng các tên này trong giám sát hoặc cấu hình nhóm.

Nếu endpoint gốc chỉ trả `{"status":"UP"}`, chưa thể kết luận các contributor Kubernetes hoặc discovery không tồn tại. Trước tiên kiểm tra quyền xem component/detail và dependency của ứng dụng.

## 5. Cấu hình nhóm phục vụ từng quyết định

### 5.1 Dependency cho ứng dụng thực hành

Giả định dự án đã có web starter và BOM Spring Cloud tương thích, thêm Actuator và chọn **một** implementation Kubernetes client. Ví dụ sử dụng Fabric8:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-fabric8</artifactId>
</dependency>
~~~

Không thêm đồng thời các starter Fabric8, Kubernetes Java Client và HTTP DiscoveryClient chỉ để tạo nhiều dòng health. Mỗi lựa chọn phải khớp kiến trúc của ứng dụng.

### 5.2 Cấu hình nền

Ví dụ `application.yml` cho Pod có cả contributor `kubernetes` và `discoveryComposite`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service
  cloud:
    kubernetes:
      discovery:
        all-namespaces: false
        include-not-ready-addresses: false
    discovery:
      client:
        health-indicator:
          enabled: true
          include-description: false
          use-services-query: true
        composite-indicator:
          enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      show-components: never
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState
        platform:
          include: kubernetes,discoveryComposite
          show-details: when-authorized
          show-components: when-authorized
          roles: OPS
~~~

Các đường sử dụng là:

| Đường dẫn | Người dùng chính | Vai trò trong ví dụ |
| --- | --- | --- |
| `/actuator/health/liveness` | Kubelet | Kiểm tra sống nội bộ |
| `/actuator/health/readiness` | Kubelet | Quyết định tiếp nhận lưu lượng |
| `/actuator/health/platform` | Người vận hành được phép | Chẩn đoán tích hợp nền tảng |

Nếu contributor trong `include` không tồn tại, Spring Boot mặc định kiểm tra membership và có thể làm ứng dụng không khởi động. Hãy sửa dependency hoặc danh sách thành viên phù hợp môi trường; đừng tắt validation để che tên sai. Tài liệu [Health Groups](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.health.groups) mô tả việc tổ chức nhóm.

`roles: OPS` điều khiển quyền xem chi tiết health theo cơ chế của Actuator. Nó không tạo người dùng, gán role hay thay thế quy tắc truy cập HTTP. Nếu dự án dùng Spring Security, phải cấu hình cho kubelet gọi được hai URL probe và bảo vệ đường chẩn đoán phù hợp. Không đưa tài khoản quản trị hoặc token API Kubernetes vào probe manifest.

Khi cần xem cây trong môi trường lab cô lập, có thể tạm đặt `show-details` và `show-components` của nhóm `platform` thành `always`. Chỉ thực hiện khi đường endpoint đã được giới hạn truy cập. Port-forward tạo đường truy cập tới Pod nhưng không tự xác thực người gọi với Spring Security.

### 5.3 HTTP status là một phần hợp đồng probe

Với ánh xạ mặc định của Spring Boot:

| Health status | HTTP status |
| --- | --- |
| `UP` | `200` |
| `DOWN` | `503` |
| `OUT_OF_SERVICE` | `503` |
| `UNKNOWN` | `200` |

Nếu dùng `UNKNOWN` để biểu diễn điều kiện phải chặn lưu lượng, bạn phải xác định ánh xạ thích hợp cho nhóm đó. Kubelet không đọc JSON rồi tự hiểu `UNKNOWN` là lỗi. Tránh quy tắc đổi mọi trạng thái của endpoint chẩn đoán thành lý do restart ứng dụng.

## 6. Nối probe với container đúng cổng

Đây là fragment của `spec.template.spec` trong Deployment; image chỉ là tên minh họa và namespace `health-lab` cần được chuẩn bị:

~~~yaml
serviceAccountName: order-service
containers:
  - name: order-service
    image: example/order-service:health-lab
    ports:
      - name: http
        containerPort: 8080
    env:
      - name: POD_NAMESPACE
        valueFrom:
          fieldRef:
            fieldPath: metadata.namespace
      - name: SPRING_CLOUD_KUBERNETES_CLIENT_NAMESPACE
        valueFrom:
          fieldRef:
            fieldPath: metadata.namespace
    startupProbe:
      httpGet:
        path: /actuator/health/liveness
        port: http
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 30
    livenessProbe:
      httpGet:
        path: /actuator/health/liveness
        port: http
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: http
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 3
~~~

Startup probe dành ngân sách khởi động xấp xỉ `30 × 5 = 150` giây trong ví dụ; chọn lại theo dữ liệu khởi động thực tế. Khi startup probe chưa thành công, Kubernetes chưa thực hiện liveness/readiness probe. Readiness thất bại làm Pod không ready; liveness thất bại đủ ngưỡng có thể làm container bị khởi động lại. Xem [khái niệm probes của Kubernetes](https://kubernetes.io/docs/concepts/workloads/pods/probes/).

HTTP probe coi mã `200–399` là thành công, vì vậy cần tránh redirect tới trang đăng nhập. Đo cả độ trễ và HTTP status; một request bị timeout không trở thành thành công chỉ vì kết quả health cuối cùng có thể là `UP`. Xem [cấu hình HTTP probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

Trong ví dụ, probe dùng cùng cổng `8080` với ứng dụng. Nếu tách `management.server.port`, cân nhắc bật `management.endpoint.health.probes.add-additional-paths=true` và probe qua `/livez`, `/readyz` trên cổng chính. Điều này giúp tránh tình huống cổng quản trị vẫn phản hồi trong khi hạ tầng HTTP phục vụ nghiệp vụ gặp vấn đề.

Không dùng `/actuator/health` gốc làm liveness chỉ vì đường này dễ nhớ: về sau thêm một indicator kiểm tra bên ngoài có thể khiến API Kubernetes hoặc dịch vụ phụ thuộc gián đoạn kéo theo restart hàng loạt.

## 7. Khi cần kiểm tra riêng một dịch vụ bắt buộc

`order-service` có thể thấy catalog discovery hoạt động, nhưng không tìm được instance của `catalog`. Nếu điều kiện này quan trọng, hãy viết một indicator có hợp đồng hẹp và đặt tên thể hiện đúng điều nó đo.

Ví dụ dưới đây dành cho ứng dụng Spring MVC dùng blocking `DiscoveryClient`. Đặt lớp trong package được component scan:

~~~java
package com.example.orders.health;

import java.util.List;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component("catalogInstances")
public class CatalogInstancesHealthIndicator implements HealthIndicator {

    private final DiscoveryClient discoveryClient;
    private final String serviceId;

    public CatalogInstancesHealthIndicator(
            DiscoveryClient discoveryClient,
            Environment environment) {
        this.discoveryClient = discoveryClient;
        this.serviceId =
                environment.getProperty("catalog.service-id", "catalog");
    }

    @Override
    public Health health() {
        try {
            List<ServiceInstance> instances =
                    discoveryClient.getInstances(serviceId);

            Health.Builder result = instances.isEmpty()
                    ? Health.down()
                    : Health.up();

            return result
                    .withDetail("check", "instance-discovery")
                    .withDetail("serviceId", serviceId)
                    .withDetail("instanceCount", instances.size())
                    .build();
        }
        catch (RuntimeException ex) {
            return Health.down()
                    .withDetail("check", "instance-discovery")
                    .withDetail("serviceId", serviceId)
                    .withDetail("reason", "discovery-query-failed")
                    .withDetail("errorType", ex.getClass().getSimpleName())
                    .build();
        }
    }
}
~~~

Hợp đồng của indicator này là **“DiscoveryClient hiện trả về ít nhất một instance của dịch vụ đã chọn”**. Nó không mở kết nối HTTP tới các instance và không sử dụng LoadBalancer để thực thi một yêu cầu. Thông tin có thể vẫn phản ánh cache hoặc bộ lọc của client.

Ban đầu, thêm `catalogInstances` vào nhóm chẩn đoán:

~~~yaml
management:
  endpoint:
    health:
      group:
        platform:
          include: kubernetes,discoveryComposite,catalogInstances
~~~

Đây là đoạn thay thế giá trị `platform.include` trong cấu hình nền, không phải thêm một khóa `management` trùng lặp vào cùng YAML document. Bean health tự viết cũng có thể tham gia health tổng thể; hai nhóm probe vẫn giữ danh sách thành viên riêng.

Nếu `catalog` là điều kiện bắt buộc để nhận **mọi** lưu lượng, có thể cân nhắc cấu hình:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,catalogInstances
~~~

Trước khi áp dụng, xác định hành vi khi `catalog` mất toàn bộ replica:

- Nếu `order-service` vẫn nhận đơn vào hàng đợi hoặc trả dữ liệu dự phòng, rút tất cả replica khỏi Service có thể làm mất một khả năng vẫn hữu ích.
- Nếu mọi endpoint đều cần catalog ngay lập tức, loại instance khỏi lưu lượng có thể đúng, nhưng phải hiểu rằng sự cố dùng chung có thể làm toàn bộ `order-service` không ready.
- Nếu một số API cần catalog, một số không cần, một health group readiness cho cả Pod không diễn tả hết khác biệt đó. Cần xử lý ở luồng gọi, hoặc thiết kế ranh giới triển khai phù hợp.

**Không thêm `catalogInstances` vào liveness.** Restart `order-service` không tạo ra instance `catalog`.

Không kiểm tra chính `order-service` như dependency bắt buộc dựa trên danh sách endpoint ready của nó: Pod cần ready mới xuất hiện trong danh sách, nhưng lại cần xuất hiện trong danh sách mới ready. Vòng phụ thuộc này có thể chặn bootstrap, nhất là replica đầu tiên.

### Chi phí và giới hạn thời gian

Đoạn Java trên gọi client đồng bộ ngay trong request health và không tự áp một timeout mới. Thời hạn kết nối/đọc phải được cấu hình theo client thực tế. Với client reactive, cần thiết kế `ReactiveHealthIndicator` phù hợp, tránh gọi thao tác blocking trực tiếp trên event loop.

Ví dụ 120 replica, mỗi replica có một request health gọi discovery mỗi 5 giây:

~~~text
120 / 5 = 24 lần gọi logic mỗi giây
~~~

Đó là số lần gọi logic vào discovery; không nhất thiết là 24 request API Kubernetes vì implementation có thể đọc dữ liệu trong bộ nhớ. Nếu giám sát, readiness và endpoint health gốc cùng kích hoạt indicator, tổng số lần gọi còn tăng.

Khi phép kiểm tra cần gọi qua mạng, nên có timeout hữu hạn, giới hạn đồng thời và cơ chế lưu snapshot có thời điểm lấy mẫu. Nếu dùng snapshot, phải định nghĩa tuổi dữ liệu được chấp nhận; đừng giữ `UP` vô thời hạn sau khi luồng cập nhật đã dừng. Giá trị `timeoutSeconds` của kubelet không thay thế timeout phía Java client.

## 8. RBAC: phân biệt quyền của ứng dụng và quyền đọc health

Có hai đường phân quyền độc lập:

1. Người vận hành hoặc kubelet gọi HTTP vào ứng dụng: do bảo mật HTTP của ứng dụng và mạng quyết định.
2. Kubernetes client của ứng dụng gọi API server: dùng danh tính Kubernetes, thông thường là service account của Pod, và bị RBAC kiểm soát.

Người dùng được phép xem Actuator không tự có quyền `list services`. Ngược lại, service account được đọc Service không làm URL Actuator trở thành công khai.

Ví dụ sau cấp quyền đọc trong **một namespace**, dành cho bài lab discovery dùng Service và Endpoints. Namespace `health-lab` phải tồn tại:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: order-service
  namespace: health-lab
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: order-discovery-reader
  namespace: health-lab
rules:
  - apiGroups: [""]
    resources: ["services", "endpoints", "pods"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: order-discovery-reader
  namespace: health-lab
subjects:
  - kind: ServiceAccount
    name: order-service
    namespace: health-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: order-discovery-reader
~~~

Role và RoleBinding có phạm vi namespace như trên; chúng không cấp quyền cluster-wide. Xem [Kubernetes: RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Đây là mẫu khởi đầu để đối chiếu nhu cầu thực tế. Các quyền đọc Pod phụ thuộc đường discovery/metadata được bật; thu hẹp nếu client không dùng. Không cấp quyền đọc Secret hoặc ConfigMap chỉ để làm health discovery chuyển sang `UP`. Tính năng cấu hình có yêu cầu quyền riêng và cần được đánh giá độc lập.

Nếu chọn discovery qua EndpointSlice, quyền tương ứng nằm ở API group `discovery.k8s.io`:

~~~yaml
- apiGroups: ["discovery.k8s.io"]
  resources: ["endpointslices"]
  verbs: ["get", "list", "watch"]
~~~

Đây là phần tử cần ghép vào `rules` của Role khi sử dụng tính năng đó. Đồng thời phải bật chế độ EndpointSlice tương ứng và dùng client/cluster hỗ trợ. Không coi quyền đọc `endpoints` của core API là quyền đọc `endpointslices`.

Spring Cloud Kubernetes có tùy chọn `spring.cloud.kubernetes.discovery.use-endpoint-slices=true` và mặc định không bao gồm địa chỉ chưa ready. Xem [DiscoveryClient for Kubernetes, dòng 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/discovery-client.html).

Để đối chiếu quyền bằng danh tính của Pod:

~~~powershell
kubectl auth can-i list services -n health-lab --as=system:serviceaccount:health-lab:order-service
kubectl auth can-i watch endpoints -n health-lab --as=system:serviceaccount:health-lab:order-service
kubectl auth can-i list endpointslices.discovery.k8s.io -n health-lab --as=system:serviceaccount:health-lab:order-service
~~~

Các lệnh `--as` cần quyền impersonation của tài khoản đang chạy `kubectl`. Nếu bị từ chối impersonation, đó chưa phải bằng chứng service account thiếu quyền đọc resource; cần người có quyền thực hiện phép đối chiếu thích hợp.

## 9. Thực hành đọc health theo từng giả thuyết

Các lệnh dưới đây dành cho môi trường lab đã triển khai ứng dụng và `catalog`. Thay tên Pod bằng tên thực tế, không gửi chuỗi `<ten-pod-order>` nguyên văn vào terminal.

### Bước 1: Xác định đúng replica và danh tính

~~~powershell
kubectl -n health-lab get pods -l app=order-service -o wide
kubectl -n health-lab get pod <ten-pod-order> -o jsonpath='{.spec.serviceAccountName}'
kubectl -n health-lab describe pod <ten-pod-order>
~~~

Đối chiếu tên Pod, IP, namespace, service account, restart count và sự kiện probe. `Running` cùng restart count bằng 0 vẫn có thể đi kèm `Ready=False`.

Đọc log cùng khoảng thời gian quan sát:

~~~powershell
kubectl -n health-lab logs <ten-pod-order> --since=10m
~~~

Tìm thông tin khởi tạo client, namespace, đồng bộ informer, lỗi `401`, `403` hoặc timeout. Không chỉ dựa vào dòng exception cuối cùng nếu log có nguyên nhân gốc trước đó.

### Bước 2: Gọi đúng nhóm health

Mở một terminal giữ port-forward:

~~~powershell
kubectl -n health-lab port-forward pod/<ten-pod-order> 18080:8080
~~~

Tại terminal khác:

~~~powershell
curl.exe -i http://127.0.0.1:18080/actuator/health/liveness
curl.exe -i http://127.0.0.1:18080/actuator/health/readiness
curl.exe -i http://127.0.0.1:18080/actuator/health/platform
~~~

Nếu `platform` cần xác thực, dùng cơ chế xác thực đã cấu hình cho lab; port-forward không bỏ qua quy tắc ứng dụng. Chỉ đọc tiếp cây contributor khi có quyền xem.

Ghi nhận riêng HTTP status, body và thời gian phản hồi. Nếu liveness `200`, readiness `200` và platform `503`, đây có thể là kết quả đúng với cấu hình tách nhóm: ứng dụng còn phục vụ được trong khi tích hợp nền tảng đang có lỗi.

### Bước 3: Đối chiếu tên Service và endpoint

~~~powershell
kubectl -n health-lab get service catalog -o yaml
kubectl -n health-lab get endpoints catalog -o yaml
kubectl -n health-lab get endpointslices -l kubernetes.io/service-name=catalog -o yaml
~~~

Đọc loại resource mà client thực tế sử dụng. Đối chiếu selector của Service với label Pod, port/targetPort, địa chỉ và trạng thái ready. Một Service tồn tại mà không có endpoint phù hợp vẫn có thể xuất hiện trong `getServices()`.

Nếu ứng dụng chỉ discovery một namespace, đừng so kết quả của nó với `kubectl get services -A` rồi kết luận client làm mất dữ liệu. Với nhiều namespace, tên dịch vụ còn có thể trùng nhau; bài lab nên giữ phạm vi rõ ràng.

### Bước 4: Kiểm tra đường gọi nghiệp vụ

Từ đường mạng tương đương ứng dụng, gọi một endpoint đọc an toàn của `catalog`, chẳng hạn API tra cứu sản phẩm của môi trường lab. So sánh kết quả với `catalogInstances`.

Nếu chỉ port-forward thẳng tới catalog từ máy cá nhân, bạn mới kiểm tra đường máy cá nhân tới Pod; chưa chứng minh `order-service` truy cập được catalog qua mạng cluster, Service DNS hoặc LoadBalancer.

Với ứng dụng dùng Spring Cloud LoadBalancer, cần kiểm tra thêm service ID, port được chọn, khả năng cache danh sách instance, timeout, TLS và xác thực phía đích. `DiscoveryClientHealthIndicator` không tự xác nhận các phần này.

## 10. Ma trận tình huống để thực hành chẩn đoán

Chỉ gây lỗi trong lab cô lập. Với thay đổi RBAC, replica hoặc bộ lọc, lưu cấu hình ban đầu để khôi phục sau thí nghiệm; chờ thời gian đồng bộ của client trước khi đánh giá.

| Tình huống | Tín hiệu có thể quan sát | Kết luận và hành động |
| --- | --- | --- |
| `catalog` không có replica ready | Tên Service vẫn tồn tại; `getInstances("catalog")` có thể rỗng | Discovery tổng quát `UP` chưa đủ; kiểm tra endpoint và indicator chuyên biệt |
| Cấu hình sai namespace | Discovery có thể `UP` nhưng thiếu dịch vụ mong đợi | So namespace thực tế của client với nơi triển khai catalog |
| Service account thiếu quyền | Log có `403 Forbidden`; health có thể `DOWN` hoặc khởi tạo bị lỗi | Đọc đúng resource/verb/namespace trong lỗi rồi sửa Role |
| Lỗi kết nối tới API server | Client có thể lỗi, khởi tạo chậm hoặc vẫn trả cache | Đối chiếu log đồng bộ và tuổi dữ liệu, không đòi mọi client lập tức `DOWN` |
| `catalog` từ chối xác thực | Có instance, discovery vẫn `UP`, request nghiệp vụ `401/403` | Kiểm tra credential phía catalog, không sửa RBAC Kubernetes tùy tiện |
| NetworkPolicy chặn đường ứng dụng tới catalog | Danh sách instance tồn tại nhưng request timeout | Kiểm tra tuyến mạng và policy của luồng dữ liệu |
| Probe đi sai cổng hoặc bị bảo mật chặn | Kubelet báo thất bại trong khi curl ở cổng khác thành công | Đối chiếu URL, port, context path, HTTP status và security |
| ConfigMap đã đổi nhưng Pod còn dùng giá trị cũ | Kubernetes/discovery health vẫn có thể `UP` | Đối chiếu cấu hình hiệu lực và cơ chế cập nhật, không suy từ health |

Trường hợp cuối gắn với phạm vi rộng hơn của module: ConfigMap, Secret và Configuration Watcher giải quyết việc nạp hoặc chuyển thay đổi cấu hình. Các contributor trong bài này không chứng minh refresh đã tới mọi replica, bean đã nhận giá trị mới hay credential mới đã được dùng thành công.

Nếu cần quan sát việc áp dụng cấu hình, có thể bổ sung số phiên bản cấu hình không nhạy cảm hoặc thời điểm cập nhật vào telemetry phù hợp. Không đưa nội dung Secret, bearer token hay toàn bộ biến môi trường vào health detail.

## 11. Chọn tính năng thực sự cần

Hãy bắt đầu từ cách ứng dụng tìm và gọi dịch vụ:

| Kiến trúc | Hướng quan sát hợp lý |
| --- | --- |
| Gọi Kubernetes Service qua DNS, không dùng DiscoveryClient | Dùng probe Spring Boot; theo dõi Service, endpoint và lỗi request thật |
| Dùng DiscoveryClient để lấy instance cho LoadBalancer | Bổ sung discovery health và chỉ báo instance cho dependency quan trọng |
| Dùng HTTP DiscoveryClient qua DiscoveryServer | Quan sát riêng client tới server và server tới Kubernetes |
| Chỉ dùng ConfigMap/Secret, không cần khám phá instance | Tập trung vào cấu hình hiệu lực; không thêm discovery chỉ để có contributor |
| Có fallback khi dịch vụ phụ thuộc lỗi | Đặt kiểm tra dependency ở nhóm chẩn đoán, cân nhắc kỹ tác động lên readiness |

`include-not-ready-addresses=true` có thể phục vụ công cụ quan sát cần nhìn thấy endpoint chưa ready. Với luồng nghiệp vụ thông thường, bật nó chỉ để làm danh sách instance không rỗng có thể khiến caller chọn một Pod chưa sẵn sàng. Tương tự, tắt một indicator chỉ làm thay đổi tín hiệu health, không sửa được namespace, quyền hoặc đường mạng sai.

## 12. Kết quả cần đạt sau bài thực hành

Sau khi hoàn thành lab, bạn cần có các bằng chứng sau:

- Một cây health đã xác định được ID contributor thật và client đang sử dụng.
- Hai probe chỉ phục vụ quyết định sống và sẵn sàng của ứng dụng; nhóm chẩn đoán có quyền truy cập phù hợp.
- Một lần đối chiếu `services` với instance và endpoint của `catalog` để thấy rõ giới hạn của `UP`.
- Một lỗi namespace hoặc RBAC được giải thích bằng danh tính, resource và phạm vi cụ thể.
- Một quyết định có lý do về việc kiểm tra catalog có tham gia readiness hay chỉ phục vụ quan sát.

Một thiết kế health hữu ích phải trả lời được: **đang kiểm tra điều gì, dữ liệu đến từ đâu, kết quả còn mới đến mức nào và ai sẽ hành động khi phép kiểm tra thất bại**.
