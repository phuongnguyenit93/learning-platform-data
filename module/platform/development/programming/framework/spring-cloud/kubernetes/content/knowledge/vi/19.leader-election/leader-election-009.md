# Thời gian phát hiện mất leader và chọn leader mới

## Mục tiêu của bài học

Một ứng dụng Spring chạy ba Pod có thể chỉ cho một Pod thực hiện vòng quét báo cáo. Khi Pod đó gặp lỗi, hai Pod còn lại cần tiếp quản. Câu hỏi vận hành cần trả lời là: **từ lúc công việc của leader bị gián đoạn đến lúc một Pod khác tiếp tục công việc, hệ thống phải chờ bao lâu?**

Trong phạm vi Spring Cloud Kubernetes, câu trả lời phụ thuộc vào cơ chế bầu leader, tín hiệu sức khỏe, khả năng truy cập Kubernetes API và cách ứng dụng bắt đầu hoặc dừng tác vụ. Không thể lấy một tham số thời gian rồi coi đó là thời gian khôi phục của toàn bộ nghiệp vụ.

Sau bài học, bạn có thể:

- Phân biệt thời gian phát hiện lỗi, thời gian giành quyền leader và thời gian khôi phục công việc.
- Ước lượng độ trễ của cơ chế ConfigMap dựa trên readiness, watch và kiểm tra định kỳ.
- Đọc đúng ý nghĩa của lease duration, renew deadline và retry period khi sử dụng cơ chế Lease.
- Thiết kế phép đo chuyển leader, nhận diện các yếu tố làm kết quả xấu đi và chọn tham số theo mục tiêu vận hành.

## 1. Xác định cơ chế trước khi tính thời gian

Spring Cloud Kubernetes có các cách triển khai bầu leader khác nhau. Bài này dùng **Fabric8 Leader dựa trên ConfigMap của Spring Cloud Kubernetes 3.3.0** làm mốc cụ thể cho ví dụ thực hành. Đây là mốc để giải thích hành vi, không phải khuyến nghị chọn phiên bản cho dự án mới. Dependency phải được quản lý bằng Spring Cloud BOM tương thích với Spring Boot của dự án.

Cơ chế này phát các sự kiện Spring Integration `OnGrantedEvent` và `OnRevokedEvent`. Thêm đúng module leader khi ứng dụng cần một tác vụ có leader; không cần bật DiscoveryClient hay Spring Cloud LoadBalancer chỉ để bầu leader. Xem [tài liệu Leader Election nhánh 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/leader-election.html).

| Nội dung cần kiểm tra | Cơ chế ConfigMap dùng trong phần thực hành | Cơ chế native được tài liệu 5.1 mô tả |
| --- | --- | --- |
| Nhóm thuộc tính nhận diện | `spring.cloud.kubernetes.leader.*` | `spring.cloud.kubernetes.leader.election.*` |
| Dữ liệu điều phối | ConfigMap chứa định danh leader theo role | Bản ghi điều phối trong Lease hoặc ConfigMap |
| Nhịp cần hiểu | `update-period` và đường xử lý watch | `retry-period`, `renew-deadline`, `lease-duration` |
| Sự kiện ứng dụng | `OnGrantedEvent`, `OnRevokedEvent` | `StartLeadingEvent`, `StopLeadingEvent`, `NewLeaderEvent` |

Tài liệu 5.1 mô tả cơ chế native được bật bằng `spring.cloud.kubernetes.leader.election.enabled=true` và lưu ý đây là cơ chế đang chuyển tiếp. Hãy kiểm tra phiên bản và auto-configuration thực tế trước khi áp dụng. Không trộn hai nhóm thuộc tính hoặc đăng ký listener của cơ chế này cho cơ chế kia. Tham khảo [mô tả cơ chế native](https://docs.spring.io/spring-cloud-kubernetes/reference/leader-election.html).

**Một ConfigMap chứa tên leader không tự có thời hạn hết hiệu lực như lease.** Việc cùng sử dụng loại tài nguyên ConfigMap cũng không có nghĩa hai implementation có cùng thuật toán.

## 2. Bốn mốc cần đo

Giả sử `report-worker-a` đang là leader, còn `report-worker-b` và `report-worker-c` là ứng viên dự phòng.

| Mốc | Ý nghĩa | Cách quan sát |
| --- | --- | --- |
| `t0` | Lỗi bắt đầu ảnh hưởng đến công việc của leader | Thời điểm fault injection hoặc dấu vết nghiệp vụ cuối cùng |
| `t_visible` | Tín hiệu mà cơ chế bầu leader sử dụng đã thể hiện lỗi | Pod không Ready, bản ghi được giải phóng hoặc điều kiện lease hết hiệu lực |
| `t_granted` | Một ứng viên giành được quyền leader | Log sự kiện được cấp quyền ở Pod mới |
| `t_work` | Leader mới bắt đầu phần việc có ý nghĩa | Log bắt đầu vòng xử lý, nhận batch hoặc thực hiện bước nghiệp vụ đầu tiên |

Từ đó:

```text
T_signal   = t_visible - t0
T_election = t_granted - t_visible
T_start    = t_work - t_granted

T_resume   = t_work - t0
           = T_signal + T_election + T_start
```

Đây là cách phân rã để lập ngân sách và quan sát. Những bước bên trong có thể chạy đồng thời; không cộng thêm các timeout đã được tính vào một mốc khác.

Nếu mục tiêu là “báo cáo tiếp theo hoàn tất trong 30 giây”, cần đo thêm `t_done` và thời gian xử lý nghiệp vụ. `T_resume` chỉ kết thúc ở lúc tiếp tục công việc, chưa chứng minh dữ liệu đã được xử lý xong.

Có leader dự phòng đã Ready giúp giảm phụ thuộc vào việc tạo Pod mới. Nếu chỉ chạy một replica, thời gian khôi phục còn phụ thuộc scheduling, tải image, khởi động JVM, khởi tạo Spring và readiness.

## 3. ConfigMap: lúc nào ứng viên cho rằng leader cũ không còn phù hợp?

Trong implementation Fabric8 3.3.0, vòng kiểm tra đọc ConfigMap, lấy Pod đang giữ role và kiểm tra readiness của Pod đó. Nếu leader vẫn Ready, ứng viên giữ nguyên kết quả. Nếu leader không còn phù hợp và bản thân ứng viên Ready, ứng viên có thể thử cập nhật bản ghi bằng resource version đã đọc. Các cập nhật cạnh tranh không cùng thắng trên một phiên bản tài nguyên.

Điểm cần nhớ là tín hiệu ở đây gắn với **Pod readiness**, không phải một heartbeat nghiệp vụ có TTL. Logic cụ thể nằm trong [Fabric8LeadershipController của tag v3.3.0](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.0/spring-cloud-kubernetes-fabric8-leader/src/main/java/org/springframework/cloud/kubernetes/fabric8/leader/Fabric8LeadershipController.java).

Vì vậy, ba tình huống sau có ý nghĩa khác nhau:

- Pod chuyển sang không Ready: ứng viên có thể có căn cứ để tiếp quản.
- Thread xử lý báo cáo bị treo nhưng endpoint readiness vẫn trả thành công: cơ chế có thể tiếp tục chấp nhận leader cũ.
- Kubernetes API không truy cập được: ứng viên không có đủ điều kiện đọc và cập nhật tài nguyên điều phối; thêm replica không giải quyết được điểm nghẽn này.

Không nên mô tả mọi trường hợp leader “không làm việc” là Pod “đã chết”. Một tiến trình còn chạy, một Pod còn Ready và một tác vụ còn tiến triển là ba trạng thái cần quan sát riêng.

### 3.1. Kiểm tra định kỳ không phải con đường duy nhất

`LeaderInitiator` của mốc phiên bản này lập lịch gọi kiểm tra trạng thái theo `update-period`. Mặc định của `LeaderProperties` là **60 giây**; đây là chu kỳ kiểm tra, không phải cam kết thời gian chuyển leader.

Nguồn xác định hai chi tiết này là [LeaderInitiator v3.3.0](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.0/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/leader/LeaderInitiator.java) và [LeaderProperties v3.3.0](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.0/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/leader/LeaderProperties.java).

Ngoài lịch định kỳ:

- Watch ConfigMap có thể kích hoạt cập nhật khi bản ghi leader thay đổi. Xem [Fabric8LeaderRecordWatcher v3.3.0](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.0/spring-cloud-kubernetes-fabric8-leader/src/main/java/org/springframework/cloud/kubernetes/fabric8/leader/Fabric8LeaderRecordWatcher.java).
- Watch readiness của Pod có thể kích hoạt cập nhật khi trạng thái sẵn sàng thay đổi. Xem [Fabric8PodReadinessWatcher v3.3.0](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.0/spring-cloud-kubernetes-fabric8-leader/src/main/java/org/springframework/cloud/kubernetes/fabric8/leader/Fabric8PodReadinessWatcher.java).

Với `update-period=5s`, một lần chuyển leader nhanh hơn 5 giây hoàn toàn có thể xảy ra qua watch. Ngược lại, chu kỳ 5 giây không giúp phát hiện một lỗi nghiệp vụ không làm thay đổi tín hiệu sức khỏe.

### 3.2. Ước lượng đường đi của độ trễ

Khi lỗi đã phản ánh lên trạng thái Pod, có thể dùng mô hình gần đúng:

```text
T_resume ≈ T_pod_signal
         + T_observe
         + T_read_and_compete
         + T_start_work

Nếu watch hoạt động:
    T_observe chủ yếu gồm truyền sự kiện và xử lý callback.

Nếu phải chờ lịch kiểm tra:
    thời gian chờ đến lượt kiểm tra tiếp theo thường nằm trong [0, P),
    với P = update-period.
```

Khoảng `[0, P)` chỉ đúng khi lịch chạy đều, vòng kiểm tra không bị kẹt và không có độ trễ bất thường. Nó chưa bao gồm thời gian thực thi lệnh API, tranh chấp, khởi động tác vụ hoặc chờ phục hồi kết nối.

Watch và kiểm tra định kỳ là hai đường có thể phát hiện cùng một thay đổi. Khi cả hai chạy bình thường, không cộng toàn bộ thời gian của cả hai vào cùng một lần chuyển leader. Khi một đường bị lỗi, kết quả phụ thuộc đường còn lại và khả năng phục hồi của implementation.

## 4. Readiness, liveness và lỗi node đóng góp thời gian khác nhau

Readiness quyết định Pod có sẵn sàng phục vụ hay không. Liveness giúp kubelet quyết định khi nào cần khởi động lại container. Startup probe bảo vệ giai đoạn khởi động trước khi những probe còn lại bắt đầu hoạt động. Chúng không phải cùng một bộ đếm. Tham khảo [Kubernetes về các loại probe](https://kubernetes.io/docs/concepts/workloads/pods/probes/).

Ví dụ cấu hình readiness:

```yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 2
  timeoutSeconds: 1
  failureThreshold: 3
```

Giả sử Pod đang hoạt động ổn định, endpoint bắt đầu thất bại liên tục và mỗi lần kiểm tra thất bại trả về gần như ngay lập tức. Với chu kỳ 2 giây và ngưỡng 3 lần, một mô hình thời gian đơn giản cho kết quả khoảng **4 đến 6 giây** từ lúc lỗi xuất hiện đến khi đủ ba lần thất bại:

```text
Thời gian chờ lần kiểm tra lỗi đầu tiên: từ gần 0 đến gần 2 giây
Khoảng cách từ lần lỗi thứ nhất đến lần lỗi thứ ba: khoảng 4 giây
```

Đây là phép tính minh họa theo giả thiết, không phải cận cứng Kubernetes đảm bảo. Nếu kiểm tra phải chờ timeout, kubelet bận, startup chưa hoàn thành hoặc trạng thái truyền lên API chậm, kết quả khác đi.

| Sự cố | Điều gì có thể làm tăng thời gian? | Điều phải kiểm tra |
| --- | --- | --- |
| HTTP readiness liên tục thất bại | Nhịp probe, số lần thất bại, timeout và cập nhật trạng thái | Thời điểm Pod thật sự mất Ready |
| Container kết thúc | Trạng thái container, nhịp báo cáo của kubelet, quá trình khởi động lại | Phân biệt sự kiện container với trạng thái Pod |
| Node mất kết nối | Cơ chế theo dõi node và cập nhật điều kiện Pod | Không dùng riêng công thức HTTP probe |
| Vòng quét báo cáo bị kẹt | Readiness có thể vẫn thành công | Chỉ báo tiến triển của tác vụ và chính sách dừng an toàn |
| JVM hoặc CPU bị đình trệ | Probe, callback và tác vụ đều có thể trễ | GC, throttling, độ trễ scheduler |

Không gắn readiness với điều kiện “Pod này phải đang là leader”. Trong ví dụ ConfigMap, ứng viên cần Ready để giành quyền; nếu follower luôn không Ready vì chưa là leader, nhóm có thể rơi vào vòng chờ không có ứng viên đủ điều kiện.

Readiness cũng không tự dừng một thread đang xử lý. Nếu ứng dụng nhường quyền khi không còn Ready, logic nghiệp vụ vẫn phải có cách ngừng nhận việc mới và kết thúc công việc đang chạy theo chính sách phù hợp.

## 5. Một ví dụ tính ngân sách phục hồi

Giả sử nhóm đã có ba Pod Ready. Một lỗi làm readiness của leader thất bại nhanh và liên tục. Ta chọn các giả thiết minh họa:

| Thành phần | Giá trị dùng để tính |
| --- | --- |
| Phản ánh lỗi qua readiness | 4–6 giây |
| Truyền watch và bắt đầu xử lý | 0,2 giây |
| Đọc trạng thái, giành quyền và nhận sự kiện | 0,4 giây |
| Chuẩn bị và bắt đầu công việc | 0,6 giây |
| Chu kỳ kiểm tra dự phòng | 5 giây |

Nếu watch tới kịp:

```text
T_resume ≈ (4 đến 6) + 0,2 + 0,4 + 0,6
         ≈ 5,2 đến 7,2 giây
```

Nếu cùng tình huống phải chờ lịch kiểm tra, bỏ thành phần watch và thay bằng thời gian chờ trong `[0, 5)`:

```text
T_resume ≈ (4 đến 6) + (0 đến gần 5) + 0,4 + 0,6
         ≈ từ 5 đến gần 12 giây
```

Các con số là dữ liệu giả định để học cách tính. Chưa thể dùng khoảng 5–12 giây làm SLO cho hệ thống thật.

Nếu giảm `update-period` từ 5 giây xuống 1 giây, ta chỉ giảm phần chờ lịch kiểm tra. Phần 4–6 giây do tín hiệu readiness vẫn còn. Trong đường watch hoạt động tốt, thay đổi đó có thể cải thiện rất ít thời gian tiếp quản.

Muốn đạt mục tiêu dưới 3 giây trong ví dụ này, cần xem lại toàn bộ ngân sách và chất lượng tín hiệu, thay vì chỉ thay một thuộc tính leader.

## 6. Khi dùng Lease: ba thời gian có vai trò riêng

Phần này là đối chiếu cho implementation sử dụng cơ chế lease; không áp dụng các thuộc tính sau vào ví dụ ConfigMap 3.3.0.

Trong nhóm thuộc tính `spring.cloud.kubernetes.leader.election`, tài liệu Spring Cloud Kubernetes 5.1 liệt kê các giá trị mặc định sau:

| Thuộc tính | Mặc định | Vai trò trong mô hình |
| --- | --- | --- |
| `retry-period` | `2s` | Nhịp thử giành quyền hoặc gia hạn |
| `renew-deadline` | `10s` | Ngân sách leader dành cho việc gia hạn trước khi bỏ quyền |
| `lease-duration` | `15s` | Khoảng thời gian ứng viên xét bản ghi chưa được gia hạn trước khi có thể tiếp quản |

Tên và mặc định có trong [phụ lục thuộc tính Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html). Cần giữ quan hệ thời gian phù hợp với validation của client đang dùng; cấu hình thông thường có `retry-period < renew-deadline < lease-duration`, với khoảng đệm cho các lần thử và độ trễ.

### 6.1. Không cộng máy móc renew deadline với lease duration

Giả sử bản ghi vừa được gia hạn thành công tại giây 0, leader chết ở giây 1, không giải phóng quyền và ứng viên đã quan sát bản ghi đó. Trong mô hình lý tưởng với lease 15 giây và nhịp thử 2 giây:

```text
Giây 0:      gia hạn thành công
Giây 1:      leader chết
Gần giây 15: bản ghi đủ lâu không đổi để ứng viên có thể tiếp quản
Sau đó:      chờ lượt thử, ghi thành công, rồi bắt đầu tác vụ
```

Thời gian chờ đến lần giành quyền có thể xấp xỉ **14 đến 16 giây tính từ sự cố**, chưa tính thời gian API, jitter, tranh chấp và bắt đầu công việc. Không phải “chờ 10 giây rồi chờ thêm 15 giây”.

`renew-deadline` chủ yếu chi phối lúc leader còn sống tự kết luận không gia hạn được nữa. Việc leader tự bỏ quyền và việc follower được phép lấy quyền là hai điều kiện riêng. Nếu bản ghi không được giải phóng thành công, follower vẫn phải tuân theo điều kiện hết hiệu lực.

Mốc quan sát cũng quan trọng: một client có thể tính khoảng thời gian bản ghi không đổi bằng đồng hồ cục bộ, thay vì tin tuyệt đối vào timestamp của máy khác. Mã [client-go v0.32.0](https://raw.githubusercontent.com/kubernetes/client-go/v0.32.0/tools/leaderelection/leaderelection.go) minh họa rõ cách tiếp cận này. Đây là nguồn đối chiếu thuật toán, không phải khẳng định ứng dụng Fabric8 gọi thư viện Go.

### 6.2. Hết hiệu lực không có nghĩa tài nguyên bị xóa

Lease không phải bộ hẹn giờ ở API server tự xóa object đúng lúc hết hạn. Ứng viên đọc bản ghi và xét điều kiện thời gian của thuật toán. Vì vậy:

- Object còn tồn tại không có nghĩa leader còn hoạt động.
- `renewTime` cũ là một bằng chứng cần đặt trong ngữ cảnh, không phải toàn bộ kết luận.
- Chờ đủ lease duration vẫn không giúp giành quyền nếu API server tiếp tục không truy cập được.
- Graceful release thành công có thể giúp ứng viên lấy quyền sớm hơn đường chờ hết hạn.

Đối với cơ chế native của Spring Cloud Kubernetes, dùng đúng listener và kiểm tra hành vi release của client cùng phiên bản triển khai. Không giả định việc đóng ứng dụng luôn giải phóng được quyền khi mạng hoặc API đang lỗi.

## 7. Chuẩn bị ví dụ thực hành với ConfigMap

Phần thực hành dưới đây là các đoạn cấu hình để đưa vào một ứng dụng lab; chúng không được thực thi tự động. Dùng cluster thử nghiệm và namespace `leader-lab`. Các Pod và ConfigMap trong ví dụ cùng namespace.

### 7.1. Dependency và cấu hình ứng dụng

Trong dự án đã có Spring Boot Web, Actuator và Spring Cloud BOM quản lý mốc Spring Cloud Kubernetes 3.3.0, thêm:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-kubernetes-fabric8-leader</artifactId>
</dependency>
```

Cấu hình ứng dụng dùng cho phép đo:

```yaml
spring:
  application:
    name: report-worker
  cloud:
    kubernetes:
      client:
        namespace: ${POD_NAMESPACE}
      leader:
        enabled: true
        auto-startup: true
        namespace: ${POD_NAMESPACE}
        role: report-loop
        config-map-name: report-leaders
        create-config-map: false
        update-period: 5s
        publish-failed-events: true

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info

logging:
  level:
    org.springframework.cloud.kubernetes.commons.leader: DEBUG
    org.springframework.cloud.kubernetes.fabric8.leader: DEBUG
```

`POD_NAMESPACE` được cung cấp qua Downward API ở Pod. `role` và tên ConfigMap phải giống nhau trên các replica cùng tham gia một cuộc bầu. Dùng ConfigMap riêng cho dữ liệu điều phối để dễ quan sát và tránh lẫn với cấu hình nghiệp vụ.

Các thuộc tính trên được nạp khi ứng dụng khởi động. Trong thí nghiệm, thay `update-period` rồi triển khai lại và chờ hệ thống ổn định trước khi đo lượt tiếp theo. Không giả định thay ConfigMap cấu hình hoặc gọi Configuration Watcher sẽ tự lập lịch lại bộ kiểm tra leader đang chạy.

### 7.2. RBAC và tài nguyên điều phối

Ví dụ dưới tạo sẵn ConfigMap, nên ứng dụng không cần quyền `create` ConfigMap. Các quyền watch/list được giới hạn trong namespace lab. Quyền `get/update` được tách để giới hạn vào đúng tên bản ghi điều phối.

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: leader-lab
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: report-worker
  namespace: leader-lab
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: report-leaders
  namespace: leader-lab
data: {}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: report-leader-access
  namespace: leader-lab
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["report-leaders"]
    verbs: ["get", "update"]
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["list", "watch"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: report-leader-access
  namespace: leader-lab
subjects:
  - kind: ServiceAccount
    name: report-worker
    namespace: leader-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: report-leader-access
```

Quyền list/watch ConfigMap ở đây cho phép đọc các ConfigMap trong namespace lab, nên không coi đây là bộ quyền tối thiểu cho mọi môi trường. Nếu muốn thu hẹp watch theo tên, phải kiểm tra request thực tế của client và điều kiện field selector tương ứng. Kubernetes không cho giới hạn quyền `create` bằng `resourceNames` theo cách dùng cho `get/update`; xem [RBAC và giới hạn theo tên tài nguyên](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Trong phần Pod template của Deployment, đặt `serviceAccountName: report-worker`, sử dụng image đã chứa cấu hình và mã lab, đồng thời khai báo:

```yaml
# Trích phần container của Pod template; không phải manifest Deployment đầy đủ.
env:
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
  - name: POD_NAMESPACE
    valueFrom:
      fieldRef:
        fieldPath: metadata.namespace
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 2
  timeoutSeconds: 1
  failureThreshold: 3
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 1
  failureThreshold: 3
```

Chạy ba replica và dùng nhãn Pod `app: report-worker` cho các lệnh quan sát phía sau. Nếu có startup probe hoặc thời gian khởi động dài, ghi nhận chúng trong điều kiện thí nghiệm.

### 7.3. Log sự kiện và lần hoạt động đầu tiên

Một bean quan sát tối giản:

```java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicBoolean;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.integration.leader.event.OnGrantedEvent;
import org.springframework.integration.leader.event.OnRevokedEvent;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;

@Configuration
@EnableScheduling
public class LeaderTimeline {

    private static final Logger log =
            LoggerFactory.getLogger(LeaderTimeline.class);

    private static final String ROLE = "report-loop";
    private final AtomicBoolean leader = new AtomicBoolean();

    @Value("${POD_NAME:local}")
    private String pod;

    @EventListener
    public void onGranted(OnGrantedEvent event) {
        if (ROLE.equals(event.getRole())) {
            leader.set(true);
            log.info("LEADER_GRANTED pod={} role={} at={}",
                    pod, ROLE, Instant.now());
        }
    }

    @EventListener
    public void onRevoked(OnRevokedEvent event) {
        if (ROLE.equals(event.getRole())) {
            leader.set(false);
            log.info("LEADER_REVOKED pod={} role={} at={}",
                    pod, ROLE, Instant.now());
        }
    }

    @Scheduled(fixedDelay = 1000)
    public void observeWork() {
        if (leader.get()) {
            log.info("LEADER_TICK pod={} role={} at={}",
                    pod, ROLE, Instant.now());
        }
    }
}
```

Đây là mã **quan sát**, chưa phải cơ chế bảo vệ nghiệp vụ. `LEADER_TICK` đầu tiên sau `LEADER_GRANTED` cho biết scheduler của Pod mới bắt đầu hoạt động dưới cờ leader. Nhịp một giây của ví dụ cũng đóng góp độ trễ đo được.

Cờ `AtomicBoolean` không hủy một thao tác đang chạy và không ngăn khoảng đua giữa kiểm tra cờ với ghi dữ liệu. Nếu thay log bằng tác vụ thật, cần thiết kế xử lý hủy, checkpoint và bảo vệ ghi ở hệ thống đích.

Callback sự kiện cần ngắn. Không chạy vòng xử lý báo cáo dài ngay trong `onGranted`; hãy chuyển việc sang executor được quản lý để tránh giữ luồng xử lý sự kiện và làm chậm điều phối.

## 8. Đo một lần chuyển leader

### Bước 1: Xác nhận nhóm đã ổn định

Các lệnh sau chạy trong PowerShell sau khi triển khai lab:

```powershell
kubectl get pods -n leader-lab -l app=report-worker -o wide
kubectl get configmap report-leaders -n leader-lab -o yaml
kubectl auth can-i get configmaps/report-leaders -n leader-lab --as=system:serviceaccount:leader-lab:report-worker
kubectl auth can-i update configmaps/report-leaders -n leader-lab --as=system:serviceaccount:leader-lab:report-worker
kubectl auth can-i watch pods -n leader-lab --as=system:serviceaccount:leader-lab:report-worker
```

Kiểm tra ba Pod đều Ready, bản ghi đã có leader cho role `report-loop`, và chỉ một Pod đang phát `LEADER_TICK` trong giai đoạn ổn định. Tài khoản chạy các lệnh `--as` phải có quyền impersonation; nếu không, nhờ người quản trị kiểm tra hoặc quan sát phản hồi API của ứng dụng.

### Bước 2: Theo dõi log và trạng thái ở các cửa sổ riêng

```powershell
kubectl logs -n leader-lab -l app=report-worker --all-containers=true --prefix=true --timestamps=true --tail=100 --max-log-requests=10 -f
```

```powershell
kubectl get pods -n leader-lab -l app=report-worker -w
```

```powershell
kubectl get configmap report-leaders -n leader-lab -w -o yaml
```

Log theo selector theo dõi các Pod được chọn khi lệnh bắt đầu; khi Deployment tạo Pod thay thế, có thể cần mở lại luồng log để đưa Pod mới vào tập quan sát. Giữ log từ các follower đã tồn tại để không bỏ lỡ ứng viên tiếp quản.

### Bước 3: Thử nhánh kết thúc có điều phối

Lấy tên leader từ ConfigMap, không chọn Pod ngẫu nhiên:

```powershell
$record = kubectl get configmap report-leaders -n leader-lab -o json | ConvertFrom-Json
$leaderPod = $record.data.'leader.id.report-loop'

if ([string]::IsNullOrWhiteSpace($leaderPod)) {
    throw "Chua co ban ghi leader cho role report-loop"
}

[DateTimeOffset]::UtcNow.ToString("O")
kubectl delete pod $leaderPod -n leader-lab --wait=false
```

Lệnh xóa Pod thông thường tạo một thử nghiệm kết thúc có điều phối. Nó có thể cho Spring thời gian dừng và nhường quyền; không đại diện đầy đủ cho OOM kill, máy chết hoặc tiến trình biến mất đột ngột.

Timestamp in ngay trước lệnh là mốc thao tác của người thử nghiệm. Nếu cần `t0` chính xác cho sự cố nghiệp vụ, thu thêm dấu vết tại điểm fault injection hoặc thời điểm tiến trình dừng. Không đánh đồng thời điểm gửi yêu cầu xóa với thời điểm tác vụ thật sự ngừng.

### Bước 4: Ghi các mốc

Ví dụ một bản ghi đo giả lập:

```text
09:00:00.000  thao tác gây dừng bắt đầu
09:00:00.700  quan sát leader cũ không Ready
09:00:01.050  Pod B ghi LEADER_GRANTED
09:00:01.800  Pod B ghi LEADER_TICK đầu tiên

T_signal   = 0,700 giây
T_election = 0,350 giây
T_start    = 0,750 giây
T_resume   = 1,800 giây
```

Nếu không thu được `t_visible`, báo trực tiếp `t0 → t_granted` và `t_granted → t_work`; không tự đặt số để lấp khoảng trống. Đồng bộ đồng hồ giữa các node và máy điều khiển trước khi trừ timestamp từ nhiều nguồn. Với khoảng thời gian trong cùng một tiến trình, nên đo bằng đồng hồ đơn điệu.

## 9. Tách các loại lỗi để kết quả có ý nghĩa

Một phép thử xóa Pod thành công chưa đủ để kết luận hệ thống phục hồi tốt trong mọi sự cố.

| Kịch bản trong lab | Điều cần đo | Điều không được suy ra |
| --- | --- | --- |
| Kết thúc Pod thông thường | Thời gian dừng, giải phóng quyền và tiếp quản | Không coi là hard crash |
| Dừng tiến trình đột ngột bằng công cụ thử lỗi phù hợp | Thời điểm tiến trình mất, thay đổi readiness, quyền leader mới | Không giả định có callback revoke ở tiến trình đã chết |
| Làm readiness thất bại nhưng giữ JVM chạy | Độ trễ probe và hành vi nhường quyền | Không coi readiness là lệnh hủy mọi tác vụ |
| Làm tác vụ ngừng tiến triển nhưng readiness vẫn thành công | Khoảng trống quan sát sức khỏe nghiệp vụ | Không kết luận update-period nhỏ sẽ chữa được |
| Chặn riêng đường truy cập API của một Pod | Hành vi khi một ứng viên bị cô lập | Không kết luận Pod bị cô lập đã dừng ghi vào hệ thống khác |
| Làm API gián đoạn với mọi ứng viên | Thời gian không thể điều phối và thời gian phục hồi sau đó | Không hứa cận thời gian failover khi API còn lỗi |

Không dùng force delete object Pod để chứng minh tiến trình trên node đã chết. Trong tình huống node bị cô lập, việc mất object ở API và việc container thực sự dừng là hai điều khác nhau.

Với mỗi cấu hình, lặp lại nhiều lượt sau khi nhóm đã ổn định và ghi:

- Phiên bản thư viện, số replica, loại lock và bộ tham số.
- Loại lỗi, cách tạo lỗi và vị trí lấy timestamp.
- `T_resume`, thời gian leader mới bắt đầu và hoàn thành công việc.
- Số lần chuyển leader ngoài dự kiến, lỗi API và hiện tượng xử lý trùng.

Tính median và các percentile như p95 từ đủ mẫu của từng kịch bản. Với ít mẫu, giữ cả số liệu thô và giá trị lớn nhất quan sát được. Không gộp nhánh graceful rất nhanh với nhánh hard crash để che đi độ trễ của từng loại lỗi.

## 10. Điều chỉnh thời gian mà không tạo chuyển leader liên tục

### Giảm nhịp kiểm tra có chi phí

Giả sử có `N` ứng viên và chu kỳ kiểm tra `P` giây, số lượt kiểm tra định kỳ cơ sở xấp xỉ:

```text
số lượt kiểm tra mỗi giây ≈ N / P
```

Đây là số lượt logic, không phải chính xác số HTTP request. Mỗi lượt có thể đọc nhiều tài nguyên; watch, reconnect và cạnh tranh còn tạo thêm request.

Với ba ứng viên:

- `P=60s`: khoảng 0,05 lượt/giây.
- `P=5s`: khoảng 0,6 lượt/giây.
- `P=1s`: khoảng 3 lượt/giây.

Nếu có hàng trăm nhóm tác vụ, tổng tải khác xa một nhóm lab. Hãy quan sát độ trễ và phản hồi throttling của API trước khi giảm đồng loạt các khoảng thời gian.

### Chọn ngưỡng theo mục tiêu và số liệu

Một quy trình thực tế:

1. Đặt mục tiêu cho **công việc tiếp tục hoặc hoàn tất**, với điều kiện lỗi cụ thể.
2. Đo phần thời gian lớn nhất đang đến từ readiness, điều phối hay khởi động tác vụ.
3. Điều chỉnh thành phần đó và giữ khoảng đệm cho tải bình thường, GC và độ trễ mạng.
4. Đo lại độ trễ cùng số lần chuyển leader ngoài dự kiến.
5. Chỉ giữ thay đổi khi cả thời gian khôi phục và độ ổn định đáp ứng mục tiêu.

Ví dụ, một mục tiêu tiếp tục xử lý trong 20 giây có thể được phân bổ thử thành 6 giây cho tín hiệu lỗi, 5 giây cho điều phối, 3 giây cho chuẩn bị và 6 giây dự phòng. Đây là thiết kế ngân sách, không phải mặc định sản phẩm.

Với Lease, tăng thời hạn giúp chịu được những khoảng gián đoạn gia hạn dài hơn nhưng có thể kéo dài đường tiếp quản sau crash. Giảm quá mạnh có thể làm leader thay đổi vì độ trễ ngắn hạn. Tính sẵn sàng cần được đánh giá cùng nguy cơ công việc bị ngắt và lặp lại.

## 11. Leader mới xuất hiện không đồng nghĩa leader cũ đã ngừng mọi tác động

Một cập nhật tài nguyên điều phối thành công không hủy được lệnh ghi database đã gửi từ Pod cũ. JVM cũ cũng có thể tiếp tục sau một khoảng pause hoặc vẫn truy cập database trong khi bị mất kết nối Kubernetes API.

Do đó, việc đo thời gian chọn leader phải đi kèm cách bảo vệ tác động nghiệp vụ:

- Ngừng nhận việc mới khi biết mình mất quyền.
- Cho tác vụ đang chạy kiểm tra điều kiện hủy ở các điểm an toàn.
- Dùng idempotency key hoặc unique constraint cho một đơn vị công việc.
- Dùng checkpoint để leader mới biết phần nào đã hoàn tất.
- Khi yêu cầu độc quyền ghi nghiêm ngặt, thiết kế fencing token hoặc cơ chế tương đương được hệ thống đích kiểm tra.

Fencing token phải được cấp và so sánh theo một quy tắc tăng đơn điệu có ý nghĩa đối với hệ thống đích. Tên Pod, timestamp tự tạo và `resourceVersion` của ConfigMap không tự trở thành một fencing token hợp lệ cho database.

Tài liệu mã client-go cũng nêu giới hạn leader election không tự cung cấp fencing. Bài học vận hành là không dùng một log `LEADER_GRANTED` làm bằng chứng rằng mọi tác động từ leader cũ đã bị chặn.

Nếu tiến trình bị kill hoặc node mất điện, không thể chờ nó phát `OnRevokedEvent`. Khả năng tiếp quản phải được quan sát ở ứng viên còn sống; tính đúng đắn của dữ liệu cần được bảo vệ ở đường xử lý.

## 12. Chẩn đoán khi thời gian chuyển leader không như dự kiến

| Hiện tượng | Hướng kiểm tra trước |
| --- | --- |
| Không có leader ngay từ đầu | Namespace, role, tên ConfigMap, ConfigMap có tồn tại khi tắt auto-create, readiness của ứng viên và RBAC |
| API trả 403 | ServiceAccount thực tế của Pod, RoleBinding và quyền với đúng loại tài nguyên |
| Có 409 khi nhiều ứng viên cùng thử | Kiểm tra tranh chấp resource version; một lần xung đột có thể là bình thường, cần xem có tiến triển sau đó không |
| Leader mới xuất hiện nhanh hơn update-period | Tìm sự kiện watch hoặc lần nhường quyền; không vội kết luận cấu hình bị bỏ qua |
| Leader cũ còn Ready nhưng công việc không chạy | Đo tiến triển nghiệp vụ, thread và scheduler; readiness hiện tại có thể chưa đại diện đúng lỗi |
| Pod đã không Ready nhưng tiếp quản chậm | Đối chiếu watch, lịch kiểm tra, timeout API, trạng thái Ready của follower và độ trễ callback |
| Có quyền leader nhưng tác vụ bắt đầu muộn | Executor bận, scheduler trễ, lấy checkpoint hoặc kết nối hệ thống đích chậm |
| Chuyển leader qua lại liên tục | Probe không ổn định, CPU/GC, độ trễ API, lỗi mạng hoặc bộ thời gian quá sát |
| Gần như mọi Pod đều thất bại cùng lúc | Điểm phụ thuộc chung: API, namespace/RBAC, hoặc readiness kiểm tra một dịch vụ chung |

Không chỉ nhìn số replica và trạng thái `Running`. Cần đối chiếu Ready, dữ liệu điều phối và dấu vết công việc trên cùng trục thời gian.

## 13. Tự kiểm tra hiểu biết

1. **Với ConfigMap 3.3.0, update-period 5 giây có bảo đảm tiếp quản trong 5 giây sau mọi lỗi không?**  
   Không. Tín hiệu lỗi có thể chưa thay đổi, API có thể lỗi, hoặc công việc mới chưa bắt đầu. Khoảng 5 giây chỉ mô tả nhịp kiểm tra trong điều kiện phù hợp.

2. **Tại sao watch giúp chuyển leader nhanh nhưng không thay thế một readiness có ý nghĩa?**  
   Watch truyền thay đổi đã có. Nếu Pod vẫn Ready dù tác vụ bị treo, việc nhận sự kiện nhanh hơn không tạo ra tín hiệu lỗi còn thiếu.

3. **Với Lease, leader tự bỏ quyền sau khi không gia hạn được có đồng nghĩa follower được giành quyền ngay không?**  
   Chỉ có thể tiếp quản sớm nếu trạng thái điều phối cho phép, chẳng hạn quyền đã được giải phóng thành công. Nếu không, ứng viên vẫn cần xét điều kiện hết hiệu lực và cập nhật bản ghi thành công.

4. **Tại sao log cấp quyền leader chưa đủ để chứng minh phục hồi nghiệp vụ?**  
   Nó chưa chứng minh scheduler bắt đầu, tác vụ tiến triển, công việc hoàn tất hoặc tác động từ leader cũ đã bị chặn.

5. **Nếu chỉ cần chạy một tác vụ định kỳ, có bắt buộc thêm toàn bộ tính năng Spring Cloud Kubernetes không?**  
   Không. Xác định trước nhu cầu điều phối; chọn module cần thiết và so sánh với cách tổ chức tác vụ khác, như Kubernetes CronJob nếu bài toán phù hợp. DiscoveryClient, cấu hình Secret, LoadBalancer và Configuration Watcher phục vụ những nhu cầu riêng.

Một báo cáo chuyển leader có giá trị cần nêu được **cơ chế, phiên bản, loại lỗi, mốc thời gian và kết quả công việc**. Từ đó mới có thể chọn bộ tham số và mục tiêu phục hồi đáng tin cậy.
