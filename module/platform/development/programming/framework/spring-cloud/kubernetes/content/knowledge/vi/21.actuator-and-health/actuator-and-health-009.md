# Phân biệt tín hiệu trong ứng dụng với trạng thái Pod

Trong chương **Actuator và sức khỏe** của module **SPRING_CLOUD_KUBERNETES**, một câu hỏi thường gặp là: tại sao Actuator báo khỏe nhưng Pod chưa Ready, hoặc tại sao ứng dụng đang từ chối traffic mà Pod vẫn có phase `Running`? Những kết quả này có thể hoàn toàn hợp lý vì chúng mô tả những lớp khác nhau của hệ thống.

Ứng dụng Spring biết trạng thái nội bộ và những dependency mà nó kiểm tra. Kubelet biết kết quả probe và vòng đời container. Kubernetes tổng hợp thêm các điều kiện để biểu diễn trạng thái Pod; cơ chế định tuyến lại có thời điểm cập nhật riêng. Không nên coi bất kỳ một giá trị nào là bản sao tức thời của toàn bộ các lớp còn lại.

Bài học dùng ví dụ **Spring Boot 3.5.x**, Java 17 trở lên và **Spring Cloud Kubernetes 3.3.x** theo BOM tương thích của dự án. Ứng dụng cần Actuator và một web server để cung cấp HTTP probe. Cách kết nối availability với probe thuộc Spring Boot và Kubernetes, không đòi hỏi bật toàn bộ tính năng Spring Cloud Kubernetes.

Sau bài học, bạn có thể:

- Phân biệt trạng thái availability, health response, probe, container state, Pod phase và Pod condition.
- Giải thích vì sao `Running`, `UP` và `Ready=True` không đồng nghĩa.
- Dự đoán tác động khi readiness hoặc liveness thay đổi.
- Đối chiếu tín hiệu của ứng dụng với Pod nhiều container và EndpointSlice.
- Điều tra lỗi discovery, RBAC hoặc cập nhật cấu hình mà không quy kết sai rằng Pod phải restart.

## 1. Đặt tên đúng cho từng lớp tín hiệu

| Lớp | Ví dụ | Thành phần tạo hoặc tổng hợp | Điều nó mô tả |
| --- | --- | --- | --- |
| Availability trong ứng dụng | `ReadinessState.REFUSING_TRAFFIC` | Spring Boot và mã ứng dụng | Trạng thái nội bộ về khả năng hoặc ý định phục vụ |
| Health indicator/group | `UP`, `DOWN`, `OUT_OF_SERVICE` | Actuator và các contributor được chọn | Kết quả kiểm tra thuộc một phạm vi cụ thể |
| HTTP probe response | HTTP `200`, `503`, timeout | Web server ứng dụng và đường kết nối | Điều kubelet thực sự quan sát được qua endpoint |
| Kết quả probe của container | Thành công/thất bại theo ngưỡng | Kubelet | Kết quả sau lịch kiểm tra, timeout và threshold |
| Trạng thái container | `waiting`, `running`, `terminated`; `ready` | Runtime và kubelet | Tiến trình container cùng trạng thái sẵn sàng của nó |
| Pod phase | `Pending`, `Running`, `Succeeded`, `Failed`, `Unknown` | Kubernetes | Tóm tắt vòng đời của Pod |
| Pod conditions | `ContainersReady`, `Ready`, `Initialized` | Kubelet hoặc controller có trách nhiệm | Các điều kiện khác nhau của Pod |
| Trạng thái endpoint | `ready`, `serving`, `terminating` | Controller quản lý EndpointSlice | Thông tin mà thành phần định tuyến có thể sử dụng |

Ví dụ, `readinessState` là ID một health contributor; `readiness` là tên health group; `ReadinessState` là kiểu trạng thái trong Spring Boot; còn `Ready` là tên một condition của Pod. Chúng liên quan nhưng không phải cùng một trường dữ liệu.

Khi báo sự cố, tránh câu “health đỏ”. Hãy viết cụ thể: “`/readyz` của Pod A trả HTTP 503 lúc 10:15:02, trong khi `status.conditions[Ready]` đọc từ API lúc 10:15:03 vẫn là True”. Cách ghi này giữ được nguồn, thời điểm và phạm vi của từng quan sát.

## 2. Trạng thái trong bộ nhớ không phải kết quả kiểm tra mạng

### 2.1. Availability của Spring Boot

Spring Boot duy trì hai loại trạng thái availability thường dùng:

| Loại | Giá trị | Ý nghĩa trong ứng dụng |
| --- | --- | --- |
| Liveness | `CORRECT` | Trạng thái nội bộ được coi là cho phép tiếp tục hoạt động |
| Liveness | `BROKEN` | Trạng thái nội bộ hỏng theo mô hình availability, cần cơ chế phục hồi thích hợp |
| Readiness | `ACCEPTING_TRAFFIC` | Ứng dụng sẵn sàng nhận traffic |
| Readiness | `REFUSING_TRAFFIC` | Ứng dụng không muốn nhận traffic lúc này |

Theo vòng đời Spring Boot, ứng dụng có thể đã khởi tạo context nhưng vẫn đang chạy các `ApplicationRunner` hoặc `CommandLineRunner`. Vì vậy, nó có thể live trước khi ready. Readiness theo vòng đời chỉ chuyển sang sẵn sàng sau khi các tác vụ khởi động tương ứng hoàn tất. Xem [Spring Boot: Application Availability](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html#features.spring-application.application-availability).

Đây không phải một bộ phát hiện tự động mọi deadlock, lỗi nghiệp vụ hoặc tình trạng quá tải. Nếu có điều kiện nghiệp vụ bổ sung, ứng dụng cần biểu diễn điều kiện đó bằng availability hoặc health contributor phù hợp.

### 2.2. Actuator biểu diễn trạng thái qua health group

Với cấu hình probe thông thường, `livenessState` và `readinessState` được biểu diễn qua nhóm liveness/readiness. Ví dụ readiness đang từ chối traffic có thể dẫn tới:

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"status":"OUT_OF_SERVICE"}
```

Nhưng một giá trị availability tồn tại trong bộ nhớ không bảo đảm endpoint HTTP đang truy cập được. Trong lúc web server chưa khởi động hoặc đã đóng connector khi shutdown, kubelet có thể nhận connection refused hoặc timeout thay vì JSON.

Ngược lại, JSON `UP` chỉ có nghĩa trong phạm vi contributor hoặc nhóm được hỏi. Health tổng thể có thể chứa những dependency không nằm trong readiness. Không dùng kết quả của `/actuator/health` để suy ra `/actuator/health/readiness` mà chưa biết thành viên của hai phạm vi.

### 2.3. Kubelet quan sát kết quả bên ngoài

Với HTTP probe, kubelet đánh giá kết quả HTTP và khả năng hoàn tất request, không đọc JSON để suy diễn logic ứng dụng. Một cấu hình sai path trả `404`, một quy tắc security trả `401/403` hoặc một timeout đều có thể làm probe lỗi dù trạng thái readiness trong JVM vẫn là `ACCEPTING_TRAFFIC`.

Mức phản ứng còn phụ thuộc timeout, chu kỳ và ngưỡng probe. Tài liệu [Kubernetes: Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/) mô tả các tham số này và cách đánh giá probe.

Vì thế, luôn tách hai câu hỏi: **ứng dụng đang công bố điều gì, và kubelet có thực sự đọc được điều đó qua đường probe đã cấu hình không?**

## 3. Đọc đúng container state, Pod phase và Pod condition

### 3.1. Container đang chạy chưa chắc đang ready

`status.containerStatuses` chứa thông tin cho từng container, chẳng hạn:

```yaml
containerStatuses:
  - name: app
    ready: false
    restartCount: 0
    state:
      running:
        startedAt: "2026-11-24T03:00:00Z"
```

Đoạn rút gọn trên mô tả một container vẫn có tiến trình chạy nhưng chưa đủ điều kiện ready. Readiness thất bại không bắt buộc phải kết thúc tiến trình.

Khi container vừa restart, xem thêm `lastState`, reason, exit code và timestamp để biết lần chạy trước kết thúc ra sao. Một lần restart container trong cùng Pod không nhất thiết tạo Pod UID mới.

### 3.2. `Running` là phase vòng đời

Một Pod ở phase `Running` không đồng nghĩa mọi container đều healthy hoặc ứng dụng sẵn sàng xử lý yêu cầu. Phase là tóm tắt vòng đời, không phải báo cáo thành công của mọi API nghiệp vụ.

Cột `STATUS` trong `kubectl get pods` còn có thể hiển thị các giá trị như `CrashLoopBackOff` hoặc `Terminating`. Đây là cách trình bày để hỗ trợ người dùng, không phải tất cả đều là giá trị của `status.phase`. Xem [Kubernetes: Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/).

Ví dụ một Pod có `STATUS=CrashLoopBackOff` có thể cần điều tra container đang chờ sau nhiều lần thất bại, trong khi phase không phải một enum tên `CrashLoopBackOff`. `Terminating` thường liên quan quá trình xóa; cần xem cả `metadata.deletionTimestamp`.

### 3.3. `Ready` là một condition của Pod

Các condition cần đọc thường gồm:

| Condition | Câu hỏi hỗ trợ chẩn đoán |
| --- | --- |
| `PodScheduled` | Pod đã được xếp lên node chưa? |
| `Initialized` | Giai đoạn init theo cấu hình Pod đã hoàn tất chưa? |
| `ContainersReady` | Các container liên quan đã đủ điều kiện ready chưa? |
| `Ready` | Pod có đủ điều kiện sẵn sàng theo cơ chế Kubernetes không? |

Danh sách condition cụ thể có thể thay đổi theo phiên bản và tính năng của cluster. Mỗi condition có status riêng, như `True`, `False` hoặc `Unknown`, cùng reason/message và thời điểm chuyển trạng thái.

Với Pod khai báo `readinessGates`, container ready chưa đủ: các custom condition được yêu cầu cũng phải đạt. Một gate chưa được controller cập nhật có thể giữ Pod không ready ngay cả khi ứng dụng và mọi container đã ready. Xem [Kubernetes: Pod Conditions](https://kubernetes.io/docs/concepts/workloads/pods/pod-condition/).

Cột `READY` dạng `1/2` hoặc `2/2` trong bảng Pod chủ yếu giúp nhìn số container ready. Khi có gate, đừng dùng mỗi phân số này để thay thế việc đọc condition `Ready`.

## 4. Probe là cầu nối, không phải phép đồng bộ tức thời

Luồng readiness thường gặp:

```text
Ứng dụng thay đổi ReadinessState
                  │
                  v
Actuator trả kết quả của readiness group
                  │
                  v
Kubelet gọi đúng endpoint và áp dụng ngưỡng probe
                  │
                  v
Trạng thái ready của container được cập nhật
                  │
                  v
Pod Ready được tổng hợp cùng container khác và readiness gate
                  │
                  v
EndpointSlice và thành phần định tuyến nhận thay đổi
```

Những mũi tên là các bước xử lý, không phải một giao dịch nguyên tử. Tại một thời điểm ngắn, hai người đọc hai lớp khác nhau có thể thấy kết quả chưa đồng nhất.

Các probe có vai trò khác nhau:

| Probe | Tác động khi thất bại đủ ngưỡng | Điều không nên suy ra |
| --- | --- | --- |
| Startup | Kubelet xử lý container khởi động thất bại theo cấu hình restart áp dụng | Ứng dụng đã sẵn sàng nghiệp vụ chỉ vì startup probe thành công |
| Liveness | Kubelet kết thúc container và áp dụng chính sách restart phù hợp | Chắc chắn tạo một đối tượng Pod mới |
| Readiness | Container không ready, góp phần làm Pod không ready | Tự động restart JVM hoặc hủy mọi request đang chạy |

Khi có startup probe, Kubernetes trì hoãn liveness/readiness cho đến khi startup probe thành công. Điều này cho phép dành thời gian khởi động riêng. Cơ chế được mô tả trong [Kubernetes: Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/).

Nếu không cấu hình readiness probe, Kubernetes không tự biết rằng nó nên gọi endpoint Actuator nào. Tạo health group trong Spring Boot không tự thêm `readinessProbe` vào Deployment.

## 5. Ví dụ kết nối availability với probe

### 5.1. Phía Spring Boot

Cấu hình sau cố ý chỉ dùng hai availability contributor để quan sát rõ cầu nối:

```yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      show-details: never
      show-components: never
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState
```

Hai đường dẫn bổ sung `/livez` và `/readyz` nằm trên cổng phục vụ chính. Tính năng này hữu ích khi Actuator có thể dùng cổng quản trị riêng: probe trên cổng quản trị còn phản hồi không chứng minh cổng nghiệp vụ vẫn nhận kết nối được. Xem [Spring Boot: Kubernetes Probes](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

Nếu ứng dụng có Spring Security, cần cho phép kubelet truy cập đúng endpoint probe theo chính sách của hệ thống. `show-details: never` chỉ giới hạn nội dung hiển thị; nó không tự cấp quyền truy cập HTTP hoặc loại bỏ yêu cầu đăng nhập.

### 5.2. Phía Kubernetes

Đoạn dưới là **một phần Pod spec**, thường đặt trong `spec.template.spec` của Deployment. Cần ghép với manifest của ứng dụng, không dùng như một Deployment hoàn chỉnh:

```yaml
containers:
  - name: app
    image: registry.example.com/learning/order-api:1.4.2
    ports:
      - name: http
        containerPort: 8080
    startupProbe:
      httpGet:
        path: /livez
        port: http
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 36
    livenessProbe:
      httpGet:
        path: /livez
        port: http
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /readyz
        port: http
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 2
      successThreshold: 2
```

Thay image minh họa bằng image thực tế. Với Deployment thông thường, container chạy theo chính sách restart của workload; bài học không thay đổi chính sách đó.

Startup probe ở đây kiểm tra liveness, nên nó có thể thành công trước khi các tác vụ khởi động nghiệp vụ hoàn tất. Khi đó readiness vẫn có thể thất bại cho đến lúc ứng dụng thực sự sẵn sàng. Đây là hai mốc khác nhau có chủ đích.

Không diễn giải `periodSeconds × failureThreshold` thành cam kết thời gian chuyển trạng thái chính xác. Lịch kiểm tra, thời điểm lỗi, timeout và vòng cập nhật status đều ảnh hưởng thời gian quan sát. `successThreshold: 2` cũng có thể tạo một khoảng chờ khi ứng dụng đã hồi phục nhưng Pod chưa trở lại ready.

## 6. Ví dụ chủ động từ chối traffic trong ứng dụng

Một ứng dụng đang chạy có thể cần ngừng nhận traffic mới để thực hiện một thao tác quản trị có kiểm soát. Ví dụ sau chỉ cập nhật availability trong Spring, không gọi API Kubernetes và không patch Pod status:

```java
package example.health;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public final class AdmissionControl {

    private final ApplicationContext context;

    public AdmissionControl(ApplicationContext context) {
        this.context = context;
    }

    public void refuseNewTraffic() {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.REFUSING_TRAFFIC);
    }

    public void acceptNewTraffic() {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
```

Đặt lớp trong phạm vi component scan. Quy trình quản trị hoặc mã nghiệp vụ đã được thiết kế cho việc này có thể inject bean và gọi phương thức sau khi ứng dụng hoàn tất startup. API phát sự kiện được mô tả tại [Spring Boot: AvailabilityChangeEvent](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html).

Không tự mở một endpoint quản trị công khai chỉ để gọi hai phương thức này. Khi khôi phục, chỉ công bố `ACCEPTING_TRAFFIC` sau khi các điều kiện phục vụ đã đạt. Nếu nhiều thành phần cùng điều khiển readiness, cần một cơ chế tổng hợp và quyền sở hữu trạng thái rõ ràng; một thành phần không nên vô tình bật lại traffic khi thành phần khác vẫn cần từ chối.

Giả sử dùng cấu hình nhóm và probe ở phần trước, khi gọi `refuseNewTraffic()`:

1. Readiness trong ứng dụng chuyển sang `REFUSING_TRAFFIC`.
2. Readiness endpoint phản ánh trạng thái không phục vụ, thường là HTTP 503 với mapping mặc định.
3. Liveness có thể tiếp tục trả 200 vì trạng thái sống không thay đổi.
4. Sau các lần kiểm tra và cập nhật tương ứng, container/Pod chuyển sang không ready.
5. Phase Pod vẫn có thể là `Running`; không cần có restart chỉ vì readiness thất bại.

`REFUSING_TRAFFIC` thể hiện ý định ứng dụng qua API readiness, như định nghĩa trong [Spring Boot: ReadinessState](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ReadinessState.html). Bản thân sự kiện này không phải bộ chặn mọi request ở web server. Trong khoảng hệ thống định tuyến chưa cập nhật, qua kết nối đã mở hoặc khi gọi thẳng Pod IP, request vẫn có thể tới ứng dụng.

Nếu nghiệp vụ đòi hỏi chặn cứng một loại thao tác, cần cơ chế admission ở chính luồng xử lý bên cạnh readiness. Cũng cần xử lý riêng worker nhận message hoặc tác vụ nền: readiness HTTP không tự dừng chúng.

## 7. Đọc những tổ hợp tưởng như mâu thuẫn

Bảng sau là các tình huống minh họa, không phải cam kết rằng một nguyên nhân duy nhất luôn tạo ra tổ hợp đó:

| Quan sát | Giải thích có thể có | Việc cần kiểm tra tiếp |
| --- | --- | --- |
| Pod `Running`, `/readyz` trả 503 | Tiến trình sống nhưng ứng dụng chưa nhận traffic | Startup task, readiness state và contributor của nhóm |
| `/readyz` đã 503 nhưng Pod Ready tạm thời vẫn True | Chưa đủ ngưỡng hoặc status chưa cập nhật | Probe thực tế, timestamp, failure threshold |
| `/readyz` đã 200 nhưng Pod Ready vẫn False | Chờ ngưỡng hồi phục, container khác chưa ready hoặc gate chưa đạt | Từng container và toàn bộ conditions |
| `/actuator/health` báo DOWN nhưng Pod Ready True | Nhóm tổng thể có contributor lỗi ngoài readiness | Endpoint mà probe thực sự gọi và thành viên của từng nhóm |
| Actuator ứng dụng báo UP nhưng kubelet probe lỗi | Sai path/cổng, timeout, security hoặc khác đường mạng | Events và cấu hình probe, không chỉ JSON từ port-forward |
| Container `app` ready nhưng Pod chỉ `1/2` | Một container khác chưa ready | Container status và log của đúng container đó |
| Tất cả container ready nhưng Pod Ready False | Có readiness gate chưa đạt hoặc điều kiện chuyển tiếp khác | `readinessGates`, reason/message và controller quản lý gate |
| Restart count tăng nhưng Pod UID giữ nguyên | Container restart trong cùng đối tượng Pod | `lastState`, log `--previous`, reason và exit code |
| Pod có nhãn/metadata đầy đủ nhưng không nhận traffic | Metadata nhận diện không quyết định readiness hay selector đúng | Probe, conditions, Service selector và endpoint |
| Pod Ready True nhưng một API nghiệp vụ vẫn lỗi | Probe không kiểm chứng toàn bộ chức năng hoặc dependency | Request thực tế, log, metric và phạm vi health check |

Ví dụ thứ tư không có nghĩa lỗi dependency được bỏ qua. Nó cho thấy hệ thống đang có hai chính sách: điều kiện tối thiểu để phục vụ và tín hiệu chẩn đoán rộng hơn. Người vận hành cần biết chính sách đó có đúng với hợp đồng dịch vụ không.

Tương tự, `Ready=True` không phải kiểm thử đầu cuối và không chứng minh mọi client đều gọi được ứng dụng. DNS, Service port, network policy, ingress, TLS hoặc cấu hình client vẫn có thể gây lỗi ở những lớp khác.

## 8. Tín hiệu Spring Cloud Kubernetes cần được đọc trong đúng phạm vi

### 8.1. Pod Health Indicator không phải bản sao của Pod Ready

Spring Cloud Kubernetes có health contributor cung cấp thông tin nhận diện môi trường như tên Pod, địa chỉ, namespace, service account và node. Tài liệu mô tả phạm vi này tại [Spring Cloud Kubernetes 3.3: Pod Health Indicator](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/pod-health-indicator.html).

Thấy contributor đó trong Actuator không có nghĩa nó đã kiểm tra tất cả container hoặc sao chép condition `Ready` của Pod vào ứng dụng. Nó cũng không chứng minh mọi ConfigMap/Secret cần thiết đã được đọc hoặc mọi dependency nghiệp vụ đều hoạt động.

Khi không cần contributor này, có thể dùng khóa cấu hình được tài liệu hỗ trợ:

```properties
management.health.kubernetes.enabled=false
```

Đó là thay đổi phạm vi contributor, không phải lệnh đổi Pod Ready. Nếu contributor được liệt kê tường minh trong một health group, cần điều chỉnh membership tương ứng khi tắt nó.

### 8.2. DiscoveryClient và LoadBalancer có góc nhìn riêng

Một client có thể đang dùng dữ liệu discovery đã cache, trong khi Pod đích vừa đổi readiness. Cơ chế cập nhật, bộ lọc địa chỉ ready, chế độ LoadBalancer và đường đi qua Kubernetes Service quyết định khi nào client ngừng chọn địa chỉ đó.

Đừng giả định DiscoveryClient luôn gọi trực tiếp vào health endpoint của từng instance trước mỗi lần trả danh sách. Cũng không suy ra Pod `Running` thì chắc chắn nên được đưa vào danh sách đích.

Nếu gọi thẳng Pod IP theo danh sách cache, cần kiểm chứng client có tôn trọng trạng thái endpoint và thời gian cập nhật hay không. Nếu gọi qua Service, cần kiểm tra cả selector, target port và endpoint của Service. Hai đường đi có thể cho kết quả khác nhau trong giai đoạn chuyển tiếp.

### 8.3. Lỗi cấu hình hoặc RBAC không đồng nghĩa liveness hỏng

Một request đọc ConfigMap trả `403` cho biết có vấn đề về quyền hoặc phạm vi request. Nếu ứng dụng vẫn có cấu hình hợp lệ đã nạp và chính sách cho phép sử dụng, JVM có thể tiếp tục live và ready trong khi refresh đang lỗi.

Nếu ứng dụng chưa có Secret bắt buộc hoặc bản cấu hình đang dùng không còn được phép sử dụng, nó có thể cần từ chối traffic hoặc fail startup theo thiết kế. Quyết định dựa trên khả năng phục vụ hiện tại, không chỉ dựa vào việc một API call vừa thất bại.

Restart một ứng dụng không tự sửa được RoleBinding thiếu quyền. Cần giữ lỗi quyền trong kênh chẩn đoán và sửa đúng namespace, service account, resource cùng thao tác cần thiết.

### 8.4. Watcher ready không chứng minh ứng dụng đích đã refresh

Configuration Watcher là một workload khác. Pod watcher Ready chỉ mô tả điều kiện của watcher theo probe/gate của nó. Muốn xác nhận ứng dụng đích đã áp dụng cấu hình, cần bằng chứng từ đúng instance đích, chẳng hạn sự kiện áp dụng thành công hoặc mã phiên bản cấu hình đang có hiệu lực.

Không gộp sức khỏe watcher, khả năng thông báo và kết quả áp dụng cấu hình thành một tín hiệu duy nhất. Nếu chỉ cần DNS của Service và cấu hình mount sẵn, không bật thêm client Kubernetes chỉ để đọc lại trạng thái Pod của chính ứng dụng.

## 9. Pod Ready và traffic: hiểu cả EndpointSlice lẫn giai đoạn dừng

Với Service có selector và endpoint do controller quản lý, EndpointSlice chứa thông tin địa chỉ cùng các condition như `ready`, `serving`, `terminating`. Thành phần tiêu thụ endpoint sử dụng những tín hiệu này để quyết định đích. `publishNotReadyAddresses` là một cấu hình đặc biệt cần kiểm tra trước khi giả định địa chỉ không ready sẽ không được công bố. Xem [Kubernetes: EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/).

Không diễn giải việc Pod mất Ready thành “mọi gói tin lập tức bị chặn”. Có nhiều lớp cần hội tụ và có thể còn kết nối cũ, request đang xử lý hoặc client cache địa chỉ. Cách proxy xử lý endpoint terminating cũng phụ thuộc điều kiện và implementation.

### 9.1. Đang dừng không có nghĩa tiến trình đã chết

Trong rollout hoặc scale down, một Pod có thể đã có deletion timestamp nhưng ứng dụng vẫn xử lý nốt công việc. Endpoint có thể mang tổ hợp `terminating=true`, `ready=false`, trong khi tín hiệu phục vụ dùng cho draining vẫn cần được xem riêng. Kubernetes có ví dụ trong [Explore Termination Behavior for Pods And Their Endpoints](https://kubernetes.io/docs/tutorials/services/pods-and-endpoint-termination-flow/).

Vì vậy, ảnh chụp thấy `Terminating`, tiến trình Java còn log và một request cũ hoàn tất không nhất thiết là lỗi. Cần xác định request mới hay cũ, đường định tuyến nào và ngân sách dừng còn bao lâu.

### 9.2. Availability và graceful shutdown cần phối hợp

Spring Boot hỗ trợ graceful shutdown của web server. Có thể cấu hình tường minh theo dự án:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
```

Timeout này áp dụng theo shutdown phase của Spring, không phải toàn bộ thời gian sống còn lại của Pod. Pod cần `terminationGracePeriodSeconds` phù hợp cho việc dừng, hook nếu có và phần công việc còn lại; một hook `preStop` cũng tiêu thụ ngân sách termination.

Không chỉ đặt hai con số bằng nhau rồi coi việc draining đã được bảo đảm. Cần kiểm tra tín hiệu kết thúc có đến JVM, thời gian request thực tế và độ trễ cập nhật tuyến. Cách từ chối request mới trong graceful shutdown còn phụ thuộc web server và persistent connection. Xem [Spring Boot: Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html).

Khi connector đã đóng, không nhất thiết còn đọc được một JSON readiness cuối cùng. Connection refused trong giai đoạn đó có thể phù hợp với tiến trình shutdown, không phải bằng chứng rằng trước đó ứng dụng không công bố readiness đúng.

## 10. Quy trình điều tra từ ứng dụng ra hạ tầng

Ví dụ dùng namespace `shop`, Service `order-api` và container `app`. Thay `POD_NAME` bằng Pod thực tế. Các lệnh dưới phục vụ quan sát; việc thay đổi readiness được thực hiện qua cơ chế thử nghiệm hoặc quản trị của ứng dụng đã được thiết kế và bảo vệ.

### Bước 1: Giữ đúng danh tính và mốc thời gian

```powershell
kubectl -n shop get pod POD_NAME -o wide

$podSnapshot = kubectl -n shop get pod POD_NAME -o json | ConvertFrom-Json
$podSnapshot.metadata.uid
$podSnapshot.metadata.deletionTimestamp
$podSnapshot.status.phase
```

Lưu ý nếu Deployment đã thay Pod hoặc cùng tên được tạo lại, cần đối chiếu UID. Không ghép log của lần chạy cũ với status của một đối tượng mới chỉ vì tên gần giống nhau.

### Bước 2: Đọc condition và từng container

```powershell
$podSnapshot.status.conditions |
    Format-Table type,status,reason,lastTransitionTime

$podSnapshot.status.containerStatuses |
    Select-Object name,ready,restartCount,state,lastState |
    ConvertTo-Json -Depth 6

kubectl -n shop describe pod POD_NAME
```

Trong `describe`, kiểm tra probe path/cổng, events, reason và message. Khi có init container hoặc sidecar, đọc đúng phần trạng thái liên quan; log của container `app` không đủ giải thích mọi lỗi trong Pod.

`lastTransitionTime` thể hiện lần condition đổi trạng thái, không phải timestamp của mọi lần probe. Snapshot đọc từ API là trạng thái đã được ghi nhận; nó không phải một phép đo trực tiếp mới vào JVM đúng lúc bạn chạy lệnh.

### Bước 3: Đọc log hiện tại và lần container trước nếu cần

```powershell
kubectl -n shop logs POD_NAME -c app --tail=100
kubectl -n shop logs POD_NAME -c app --previous --tail=100
```

Lệnh `--previous` chỉ có ích khi có lần container trước và log còn được giữ. So sánh thời gian startup, lỗi tải cấu hình, tín hiệu shutdown và event probe; đừng kết luận restart chỉ từ một dòng stack trace không có mốc thời gian.

### Bước 4: Hỏi đúng endpoint của đúng Pod

```powershell
kubectl -n shop port-forward pod/POD_NAME 18080:8080

# Chạy trong terminal khác.
curl.exe -i http://localhost:18080/livez
curl.exe -i http://localhost:18080/readyz
curl.exe -i http://localhost:18080/actuator/health
```

Đối chiếu cả HTTP status lẫn nội dung. Port-forward giúp chọn đúng Pod nhưng không tái tạo đầy đủ đường đi từ kubelet tới Pod, từ Service tới backend hoặc qua ingress. Nếu curl thành công mà kubelet vẫn timeout, cần kiểm tra đường mạng, cổng và thời điểm thay vì bỏ qua events.

Truy cập phải theo security của ứng dụng. Nếu path probe trả 401/403 hoặc chuyển hướng sang trang đăng nhập, sửa chính sách cho endpoint cần thiết; không mở toàn bộ Actuator để che nguyên nhân.

### Bước 5: Đối chiếu Service và endpoint

```powershell
kubectl -n shop get service order-api -o yaml
kubectl -n shop get endpointslices -l kubernetes.io/service-name=order-api -o yaml
```

Xem selector, port/targetPort, `publishNotReadyAddresses`, endpoint conditions và `targetRef` của đúng Pod. Một Service không chọn Pod vì nhãn sai là vấn đề khác với Pod bị loại do readiness.

Nếu ứng dụng gọi qua DiscoveryClient/LoadBalancer, tiếp tục kiểm tra dữ liệu đích mà client đang dùng và thời điểm cập nhật. Không mặc định ảnh chụp EndpointSlice ở API giống hệt danh sách đang cache trong client.

### Bước 6: Kết luận theo chuỗi bằng chứng

Một mô tả rõ ràng có thể là:

> Tiến trình ứng dụng vẫn chạy và liveness trả 200. Readiness trả 503 do ứng dụng chủ động từ chối traffic. Sau ngưỡng readiness, container không ready và Pod Ready=False; phase vẫn Running, restart count không tăng. Endpoint của Pod chuyển trạng thái phù hợp sau cập nhật. Vì vậy đây là thay đổi khả năng nhận traffic, không phải một lần crash.

Đây là mẫu cách diễn giải, không phải kết quả thực nghiệm đã chạy trong bài. Báo cáo thực tế cần điền timestamp, Pod UID và nguồn quan sát.

## 11. Thực hành đọc tín hiệu bằng các tình huống có kiểm soát

Dùng môi trường thử nghiệm có cấu hình ở phần ví dụ và công cụ gọi `AdmissionControl` qua luồng được kiểm soát. Không tạo tình huống lỗi trên production chỉ để kiểm chứng khái niệm.

| Tình huống | Trong ứng dụng | Điều nên quan sát ở Kubernetes | Điều chưa được kết luận |
| --- | --- | --- | --- |
| Đang chạy tác vụ startup | Chưa nhận traffic theo vòng đời | Container có thể running nhưng chưa ready | Ứng dụng đã sẵn sàng chỉ vì Java đã khởi động |
| Gọi `refuseNewTraffic()` sau startup | Readiness từ chối, liveness có thể giữ tốt | Ready chuyển sau probe; restart count không tăng chỉ vì readiness | Tiến trình đã bị dừng |
| Gọi `acceptNewTraffic()` khi đủ điều kiện | Readiness chấp nhận | Có thể chờ success threshold trước khi Ready=True | API status cập nhật tức thời cùng câu lệnh Java |
| Container phụ chưa ready | Endpoint của `app` có thể vẫn tốt | Pod không ready do container/gate liên quan | Lỗi chắc chắn nằm trong Spring Boot |
| Probe gọi nhầm path | Availability nội bộ có thể tốt | Events ghi lỗi HTTP hoặc timeout | Ứng dụng tự đánh giá không sẵn sàng |
| Database health tổng thể lỗi nhưng không thuộc readiness | Health tổng thể có thể DOWN, readiness vẫn UP | Pod có thể tiếp tục Ready | Mọi chức năng nghiệp vụ vẫn thành công |
| Lỗi refresh ConfigMap nhưng dữ liệu cũ vẫn dùng được | Tín hiệu refresh lỗi, availability tùy chính sách | Pod có thể vẫn Running và Ready | Kubernetes đã áp dụng cấu hình mới thành công |
| Container restart trong cùng Pod | Một lần chạy JVM mới | UID có thể giữ nguyên, restart count tăng | Deployment chắc chắn tạo Pod mới |

Mục tiêu là ghép các quan sát thành cùng một diễn biến, không ép mọi lớp phải có cùng từ ngữ hoặc cùng thời điểm chuyển trạng thái.

## 12. Những nhầm lẫn cần loại bỏ

| Nhầm lẫn | Cách hiểu chính xác hơn |
| --- | --- |
| `UP` đồng nghĩa Pod Ready | `UP` thuộc contributor hoặc group được hỏi; Pod Ready tổng hợp thêm tín hiệu Kubernetes |
| `Running` đồng nghĩa nhận traffic | Running là phase vòng đời; cần xem readiness, conditions và đường định tuyến |
| Readiness lỗi sẽ restart ứng dụng | Readiness điều khiển điều kiện nhận traffic; restart có nguyên nhân và chính sách riêng |
| Gửi availability event tự patch Pod | Event đổi trạng thái trong ứng dụng; probe và kubelet là cầu nối trong cấu hình này |
| Pod Health Indicator kiểm tra toàn Pod | Contributor có phạm vi cụ thể, không tự thay thế condition Ready của Pod |
| Ready=False chặn ngay mọi request | Có độ trễ hội tụ, kết nối hiện có và đường gọi có thể không qua Service |
| Tất cả container ready thì mọi readiness gate đã đạt | Gate là điều kiện bổ sung, phải đọc riêng |
| Container restart luôn là Pod mới | Cùng Pod có thể chứa nhiều lần chạy của container |
| Lỗi RBAC nên chữa bằng restart | Cần sửa quyền và phạm vi; quyết định availability dựa trên khả năng phục vụ |

Một kết luận về sức khỏe cần nêu rõ đang nói tới ứng dụng, endpoint, container, Pod hay đường định tuyến. Khi tách đúng các lớp đó, các giá trị `UP`, `Running`, `Ready=False` hoặc `Terminating` trở thành những mảnh bằng chứng có thể giải thích cùng nhau, giúp vận hành Spring Cloud Kubernetes chính xác hơn.
