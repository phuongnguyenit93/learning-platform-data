# Thiết lập tài nguyên JVM theo giới hạn container

Một ứng dụng Spring chạy tốt trên máy phát triển vẫn có thể bị Kubernetes khởi động lại khi đưa vào Pod: Java heap còn trống nhưng container đã hết bộ nhớ, hoặc CPU bị giới hạn khiến quá trình khởi động và thu gom rác kéo dài. Thiết lập tài nguyên JVM cần bắt đầu từ giới hạn của container và đặc điểm tải thực tế.

Trong module **SPRING_CLOUD_KUBERNETES**, ứng dụng còn có thể sử dụng DiscoveryClient, nguồn cấu hình ConfigMap/Secret và Spring Cloud LoadBalancer. Các thành phần này cùng chia sẻ tài nguyên với nghiệp vụ. Configuration Watcher nếu chạy thành Deployment riêng cần ngân sách riêng; không cộng toàn bộ bộ nhớ của nó vào JVM ứng dụng.

Bài học thuộc chương **Đóng gói ứng dụng**, tập trung vào cách thiết lập và kiểm chứng ngân sách JVM. Sau bài này, bạn có thể:

- Phân biệt Kubernetes requests/limits với kích thước Java heap.
- Chọn cách đặt heap cố định hoặc theo phần trăm bộ nhớ container.
- Dự trù bộ nhớ ngoài heap và mức đồng thời phù hợp với CPU.
- Cấu hình một Deployment có JVM options và health probes nhất quán.
- Thu thập bằng chứng để phân biệt Java OOM, container OOM và CPU throttling.

## 1. Phạm vi ví dụ và các giả định

Các ví dụ JVM bên dưới hướng tới **HotSpot/OpenJDK 21 chạy trong Linux container**. Với JDK khác, bản cập nhật khác hoặc JVM của nhà cung cấp khác, hãy kiểm tra các tùy chọn được hỗ trợ và giá trị thực tế. Không áp dụng các cờ HotSpot này cho ứng dụng biên dịch thành native executable.

Ví dụ sử dụng dịch vụ `catalog`:

- Chạy ứng dụng Spring Boot dưới dạng executable JAR, phục vụ HTTP tại cổng `8080`.
- Đã có Actuator; security cho phép kubelet truy cập các đường dẫn probe được minh họa.
- Đã chọn cặp phiên bản Spring Boot/Spring Cloud tương thích; bài này không thay đổi dependency.
- Có image ứng dụng tại registry mà cluster truy cập được.
- Các lệnh thực hành dùng namespace thử nghiệm `spring-cloud-lab`.

Các con số bộ nhớ và thời gian probe trong bài là **đầu vào minh họa để đo đạc**, không phải cấu hình mặc định cho mọi ứng dụng Spring.

## 2. Requests, limits và heap là ba khái niệm khác nhau

| Thiết lập | Vai trò | Không thể suy ra trực tiếp |
| --- | --- | --- |
| `requests.memory` | Đầu vào cho scheduler khi bố trí Pod | JVM sẽ đặt `-Xmx` bằng request |
| `limits.memory` | Giới hạn bộ nhớ áp dụng cho container | Toàn bộ dung lượng này dành cho heap |
| `requests.cpu` | Đầu vào lập lịch và phân chia CPU khi tranh chấp | Số thread Java nên bằng giá trị request |
| `limits.cpu` | Giới hạn lượng CPU time container được sử dụng | Container được cấp riêng từng ấy lõi vật lý |
| `-Xmx` | Trần Java heap | Trần bộ nhớ của cả tiến trình |

Trên Linux, runtime dùng cgroups để thực thi giới hạn. CPU vượt quota có thể bị throttling; bộ nhớ vượt giới hạn có thể dẫn tới OOM kill. Request không thay thế limit. Việc dùng quá memory request cũng không tự động làm container bị kill ngay tại request. Xem [Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/).

Ví dụ:

```yaml
resources:
  requests:
    cpu: "250m"
    memory: "768Mi"
  limits:
    cpu: "1000m"
    memory: "1Gi"
```

Trong ví dụ này:

- `250m` tương ứng `0,25` CPU; `1000m` tương ứng `1` CPU.
- Bộ nhớ request là `768 MiB`, còn limit là `1024 MiB`.
- `-Xmx768m`, nếu được đặt, là một quyết định riêng của người cấu hình.
- Nếu Pod có sidecar, đọc resources của từng container. Không lấy tổng ngân sách của Pod làm heap cho một JVM.

Chú ý đơn vị: Kubernetes `Mi` và `Gi` là đơn vị nhị phân. Hậu tố `m` trong `cpu: 250m` là millicpu; hậu tố `m` trong `-Xmx512m` là đơn vị dung lượng của tùy chọn JVM. Không viết `memory: 512m` để biểu diễn 512 MiB.

## 3. Container tiêu thụ nhiều hơn Java heap

Một mô hình dự toán hữu ích là:

```text
Bộ nhớ container cần dự trù
  ≈ Java heap
  + metaspace và dữ liệu lớp
  + code cache
  + thread stacks
  + direct/native buffers
  + cấu trúc JVM, GC, agent và thư viện native
  + phần sử dụng khác được tính vào cgroup
```

Dấu `≈` nhắc rằng đây là mô hình lập ngân sách. Số liệu RSS, JVM committed và container working set có phạm vi khác nhau; không cộng chúng với nhau như các vùng độc lập.

| Nhóm bộ nhớ | Ví dụ liên quan đến dịch vụ Spring |
| --- | --- |
| Heap | Đối tượng nghiệp vụ, cache, JSON, hàng đợi, dữ liệu discovery giữ trong bộ nhớ |
| Metaspace | Metadata của lớp ứng dụng, Spring, proxy và thư viện |
| Code cache | Mã máy do JIT tạo |
| Thread stacks | Thread HTTP, executor, scheduler, client và thread nội bộ JVM |
| Direct/native buffers | NIO, HTTP client, TLS, thư viện mạng |
| Phần khác | GC bookkeeping, native allocation, monitoring agent và tài nguyên khác của container |

Với platform threads, số thread và kích thước stack cùng ảnh hưởng dự toán. Chẳng hạn, `160` thread với mức stack cấu hình `1 MiB` tạo ra quy mô dự trù khoảng `160 MiB` cho stack. Đây không phải khẳng định mọi stack luôn resident đủ 1 MiB; stack còn có guard pages và dữ liệu phụ trợ. Với virtual threads, không áp dụng phép nhân này cho từng virtual thread.

Cần phân biệt:

- **Reserved**: không gian địa chỉ đã dành trước.
- **Committed**: phần đã được commit theo góc nhìn JVM.
- **Resident/working set**: số liệu ở tầng hệ điều hành hoặc container, tùy công cụ.

Native Memory Tracking giúp phân tích các vùng do HotSpot theo dõi, nhưng không bao phủ mọi cấp phát của thư viện native bên ngoài. Vì vậy, NMT không phải phép đo thay thế cho bộ nhớ container. Xem [Diagnostic Tools — Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html).

## 4. Lập ngân sách trước khi chọn phần trăm heap

Giả sử lần đo thử ban đầu của `catalog` cho phép lập ngân sách sau trong container `1Gi`:

| Khoản dự trù | MiB |
| --- | ---: |
| Heap tối đa | 512 |
| Metaspace và dữ liệu lớp | 112 |
| Code cache | 64 |
| Thread stacks | 80 |
| Direct/native buffers | 80 |
| JVM, GC, agent và phần khác | 64 |
| Biên dự phòng | 112 |
| **Tổng** | **1024** |

Đây là bảng giả định của bài học, không phải thống kê về mọi ứng dụng Spring. Các dòng ngoài heap cũng **không tự trở thành giới hạn JVM** chỉ vì đã được ghi trong bảng.

Cách suy ra trần heap:

```text
L = giới hạn bộ nhớ container = 1024 MiB
N = dự trù ngoài heap        = 400 MiB
S = biên dự phòng            = 112 MiB

H_max <= L - N - S
      <= 512 MiB
```

Tỷ lệ khởi điểm tương ứng là `512 / 1024 = 50%`.

Nếu đặt heap thành `75%`, heap có thể đạt khoảng `768 MiB`, chỉ còn `256 MiB` cho các khoản ngoài heap và biên dự phòng. Với chính giả định trên, ngân sách này không còn phù hợp. Tăng `-Xmx` có thể làm container dễ bị kill hơn dù lỗi ban đầu trông giống thiếu heap.

Khi giảm limit từ `1Gi` xuống `768Mi`, không được giả định mọi khoản ngoài heap cũng giảm `25%`. Số lớp, agent và số thread có thể gần như giữ nguyên. Nếu vẫn giữ `N = 400 MiB` và `S = 112 MiB`, phần còn lại cho heap chỉ là `256 MiB`. Khi đó cần đo lại workload, giảm mức đồng thời hoặc tăng limit.

## 5. Chọn một cơ chế chính để điều khiển heap

### 5.1. Heap cố định

```text
-Xms128m -Xmx512m
```

Cách này thể hiện rõ ngân sách của một cấu hình triển khai. Đổi limit container phải đi kèm việc xem xét lại heap và phần ngoài heap.

`-Xms` không cần luôn bằng `-Xmx`. Đặt hai giá trị bằng nhau có thể phù hợp với một số yêu cầu hiệu năng, nhưng làm tăng mức commit ban đầu và giảm khoảng linh hoạt. Quyết định này cần dựa vào thời gian khởi động và hành vi dưới tải.

### 5.2. Heap theo tỷ lệ

```text
-Xms128m -XX:MaxRAMPercentage=50.0
```

HotSpot có container support trên Linux và dùng thông tin môi trường để tính toán tài nguyên. `MaxRAMPercentage` điều khiển phép tính heap tối đa, không giới hạn tổng bộ nhớ JVM. Kích thước cuối cùng còn chịu các quy tắc ergonomics và làm tròn; phải đọc giá trị hiệu lực. Xem [The java Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).

Tỷ lệ giúp dùng lại image trong nhiều mức limit, nhưng không thay thế dự toán ngoài heap. Ví dụ `50%` trong bài được chọn từ bảng ngân sách, không phải vì đây là tỷ lệ tối ưu chung.

Không kết hợp tùy tiện `-Xmx` với `MaxRAMPercentage` rồi cho rằng cả hai cùng điều khiển heap. Khi đã cung cấp `-Xmx`, không kỳ vọng thay đổi phần trăm sẽ làm heap tối đa đổi theo limit.

### 5.3. Những tùy chọn cần hiểu trước khi thêm

| Tùy chọn | Ý nghĩa thực hành |
| --- | --- |
| `-Xms`, `-Xmx` | Kích thước heap ban đầu và tối đa |
| `-XX:MaxRAMPercentage` | Tỷ lệ dùng trong tính toán heap tối đa |
| `-Xss` | Kích thước stack của platform thread; giảm quá mức có thể gây `StackOverflowError` |
| `-XX:MaxMetaspaceSize` | Giới hạn metaspace; đặt thiếu có thể gây OOM khi nạp lớp |
| `-XX:MaxDirectMemorySize` | Giới hạn direct buffer thuộc phạm vi JVM quản lý; không bao phủ mọi native allocation |
| `-XX:ActiveProcessorCount` | Ghi đè số CPU mà JVM dùng cho một số quyết định ergonomics |

Không cần đặt tất cả các cờ trong bảng ở lần triển khai đầu. Đặc biệt, không ép metaspace, direct memory và stack xuống rất thấp chỉ để bảng tổng vừa limit. Làm như vậy có thể chuyển lỗi từ OOMKilled sang lỗi nạp lớp, thiếu direct buffer hoặc tràn stack.

## 6. CPU ảnh hưởng đến GC, startup và số request đang giữ trong bộ nhớ

CPU limit là ngân sách thời gian CPU. `limits.cpu: 500m` không có nghĩa Java chỉ được tạo nửa thread. Nhiều thread runnable vẫn có thể tranh nhau ngân sách nhỏ đó.

Một chuỗi diễn biến cần theo dõi trong thực nghiệm:

```text
CPU quota thấp
  -> xử lý request và GC chậm hơn
  -> request hoặc hàng đợi tồn tại lâu hơn
  -> nhiều đối tượng còn sống đồng thời hơn
  -> bộ nhớ và độ trễ có thể cùng tăng
```

Đây là một giả thuyết chẩn đoán, không phải mọi lần tăng memory đều do CPU. Hãy đối chiếu CPU usage, throttling, queue depth, GC và độ trễ trong cùng khoảng thời gian.

Các quyết định cần gắn với số liệu:

- Giới hạn executor và số request đồng thời thay vì tạo thread không giới hạn.
- Chặn hàng đợi tăng vô hạn bằng cơ chế từ chối, timeout hoặc backpressure thích hợp.
- Kiểm tra startup trong đúng quota CPU dự kiến, kể cả khi nhiều replica khởi động cùng lúc.
- Đọc số CPU JVM nhận diện thay vì suy từ số lõi của node.
- Chỉ dùng `ActiveProcessorCount` khi có lý do cụ thể; đặt `2` không cấp thêm CPU cho container có limit `500m`.

Không thay collector, số GC thread và số worker của mọi pool cùng lúc. Nếu một lần thử thay nhiều biến, rất khó xác định nguyên nhân cải thiện hay suy giảm.

## 7. Deployment mẫu cho image chạy JAR trực tiếp

Ví dụ này dành cho image có entrypoint dạng exec:

```dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

`/app/app.jar` phải tồn tại trong image. Đoạn trên chỉ minh họa cách khởi chạy, không phải một Dockerfile đầy đủ. JVM đọc `JAVA_TOOL_OPTIONS` khi khởi tạo; không cần ghép chuỗi biến này qua shell.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
  namespace: spring-cloud-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: catalog
  template:
    metadata:
      labels:
        app: catalog
    spec:
      containers:
        - name: app
          image: registry.example.com/training/catalog:1.0.0
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: "250m"
              memory: "768Mi"
            limits:
              cpu: "1000m"
              memory: "1Gi"
          env:
            - name: JAVA_TOOL_OPTIONS
              value: >-
                -Xms128m
                -XX:MaxRAMPercentage=50.0
                -XX:+ExitOnOutOfMemoryError
                -Xlog:gc=info
            - name: SPRING_APPLICATION_NAME
              value: catalog
            - name: SERVER_PORT
              value: "8080"
            - name: MANAGEMENT_ENDPOINT_HEALTH_PROBES_ENABLED
              value: "true"
            - name: MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE
              value: health,metrics
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 36
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
```

Thay image bằng image thực tế và tạo namespace thử nghiệm trước khi áp dụng. Những yêu cầu ServiceAccount/RBAC cho discovery hoặc đọc cấu hình vẫn phải được thiết lập theo các tính năng ứng dụng đã bật; manifest này chỉ minh họa resources, JVM và probes.

Các điểm cần đọc đúng:

- YAML folded scalar `>-` ghép JVM options thành chuỗi cách nhau bằng khoảng trắng.
- `ExitOnOutOfMemoryError` hỗ trợ kết thúc JVM khi gặp OOM thuộc phạm vi xử lý của HotSpot. Không coi cờ này là bảo đảm xử lý mọi lỗi tài nguyên hoặc kernel OOM kill. Cờ được giới thiệu trong [Java — New JVM Options](https://www.oracle.com/java/technologies/javase/9-new-features.html).
- GC log mức `info` là tín hiệu ban đầu; cần đánh giá lượng log trước khi tăng mức chi tiết.
- Startup probe cho phép chờ khoảng `36 × 5 = 180` giây theo cấu hình minh họa. Đây không phải cam kết JVM sẽ khởi động trong 180 giây; cần đo phân bố thời gian startup.
- Readiness thất bại làm Pod không sẵn sàng nhận lưu lượng qua các cơ chế chọn endpoint tương ứng; thất bại readiness không tự khởi động lại container.
- Liveness/startup thất bại tới ngưỡng có thể dẫn tới restart. Không dùng restart để che việc thiếu CPU hoặc thiếu memory.

Spring Boot cung cấp các health group liveness/readiness qua Actuator. Không gắn lỗi tạm thời của dịch vụ bên ngoài vào liveness một cách máy móc, vì có thể gây khởi động lại hàng loạt. Xem [Spring Boot — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

`JAVA_OPTS` không phải biến mà mọi JVM tự đọc. Nó chỉ có tác dụng nếu entrypoint cụ thể của image xử lý biến đó. Tương tự, exec form không tự mở rộng `"$JAVA_OPTS"` thành nhiều đối số. Luôn kiểm tra hợp đồng khởi chạy của image.

## 8. Với Paketo Buildpacks, giữ nhất quán cơ chế tính bộ nhớ

Image được tạo bằng Spring Boot build-image hoặc bootBuildImage có thể dùng Paketo. Khi đó launcher và memory calculator có thể đã sinh các JVM options.

Paketo tính heap từ tổng bộ nhớ container trừ phần ngoài heap và headroom; kết quả được đưa vào `JAVA_TOOL_OPTIONS`. Không sao chép nguyên bộ cờ heap của ví dụ JAR trực tiếp vào image này mà bỏ qua phép tính sẵn có. Xem [Paketo Java Buildpack Reference](https://paketo.io/docs/reference/java-reference/).

Ví dụ phần biến môi trường dành riêng cho image Paketo:

```yaml
env:
  - name: BPL_JVM_HEAD_ROOM
    value: "10"
  - name: BPL_JVM_THREAD_COUNT
    value: "80"
```

Hai giá trị trên là ví dụ, cần thay bằng số liệu của ứng dụng:

- `BPL_JVM_HEAD_ROOM` cung cấp phần trăm bộ nhớ để chừa lại.
- `BPL_JVM_THREAD_COUNT` là giả định cho bộ tính bộ nhớ. **Nó không đặt số HTTP worker và không giới hạn số thread thực tế.**
- Nếu ứng dụng thực sự tạo 180 platform threads nhưng calculator được khai báo 80, phép tính có thể thiếu ngân sách.
- Không giả định một biến `BPL_*` có tác dụng trên image JAR thông thường.

Các biến và quy tắc ghép JVM flags phụ thuộc buildpack đang dùng. Đọc startup log để biết options cuối cùng; hướng dẫn cấu hình nằm ở [Paketo — Configure the JVM at Runtime](https://paketo.io/docs/howto/java/#configure-the-jvm-at-runtime).

Đối với bài thực hành, chọn **một** nhánh image để triển khai: tự đặt ngân sách JVM cho image JAR trực tiếp, hoặc dùng calculator của Paketo và kiểm chứng đầu vào. Không chồng hai chiến lược mà không biết giá trị hiệu lực.

## 9. JVM options khác cấu hình ứng dụng Spring

Cần xác định tầng tiêu thụ cấu hình:

| Loại cấu hình | Thành phần đọc | Cách áp dụng trong bài |
| --- | --- | --- |
| `-Xmx`, `MaxRAMPercentage`, `-Xss` | JVM lúc khởi tạo | Đổi cấu hình khởi chạy và tạo tiến trình JVM mới |
| URL dịch vụ, timeout, tính năng nghiệp vụ | Spring và bean ứng dụng | Có thể hỗ trợ refresh nếu được thiết kế phù hợp |
| `resources.requests/limits` | Kubernetes/runtime | Quản lý qua cấu hình triển khai, đồng bộ với ngân sách JVM |
| Quyền list/watch tài nguyên | Kubernetes API/RBAC | Cấp đúng quyền cho thành phần thật sự cần |

Đặt một key `jvm.max-heap` trong ConfigMap mà Spring đọc không làm JVM hiểu đó là `-Xmx`. Configuration Watcher kích hoạt refresh ứng dụng cũng không khởi tạo lại JVM để đọc lại `JAVA_TOOL_OPTIONS`. Xem cơ chế refresh trong [Spring Cloud Kubernetes Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Nếu Deployment lấy `JAVA_TOOL_OPTIONS` qua `configMapKeyRef`, giá trị environment được gán khi container khởi chạy. Sửa ConfigMap không cập nhật environment của tiến trình đang chạy; cần tạo container mới. Với cấu hình này, có thể dùng quy trình rollout có kiểm soát sau khi cập nhật ConfigMap. Xem [Configure a Pod to Use a ConfigMap](https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/).

Ví dụ lệnh vận hành trong môi trường thực hành:

```powershell
kubectl rollout restart deployment/catalog -n spring-cloud-lab
kubectl rollout status deployment/catalog -n spring-cloud-lab
```

Nếu sửa trực tiếp env trong Pod template của Deployment thì thay đổi đó đã kích hoạt rollout; không cần gọi restart thêm chỉ để áp dụng cùng thay đổi.

Trong phạm vi bài này, mỗi lần đổi limit hoặc heap đều được kiểm chứng bằng Pod mới. Không giả định một JVM đang chạy sẽ tự tính lại heap tối đa khi giới hạn môi trường thay đổi.

## 10. Đọc giá trị hiệu lực trong container

### 10.1. Thu thập trạng thái Kubernetes trước

Các lệnh dưới đây dùng PowerShell. Trong bài thực hành một replica, lấy tên Pod như sau:

```powershell
kubectl get pods -n spring-cloud-lab -l app=catalog
$podName = kubectl get pods -n spring-cloud-lab -l app=catalog -o jsonpath='{.items[0].metadata.name}'

kubectl get pod $podName -n spring-cloud-lab -o yaml
kubectl describe pod $podName -n spring-cloud-lab
kubectl logs $podName -n spring-cloud-lab -c app
kubectl top pod $podName -n spring-cloud-lab --containers
```

Nếu đang rollout hoặc có nhiều replica, chọn đúng Pod và đối chiếu thời điểm tạo, image, resources. Không mặc định phần tử đầu tiên là Pod mới nhất.

`kubectl top` cần Metrics Server hoặc hệ thống cung cấp Resource Metrics API. Nó cho ảnh chụp usage ở tầng container, không cho biết heap, metaspace hay native buffer đang chiếm bao nhiêu.

Khi container đã restart:

```powershell
kubectl logs $podName -n spring-cloud-lab -c app --previous
kubectl get pod $podName -n spring-cloud-lab -o jsonpath='{.status.containerStatuses[?(@.name=="app")].lastState.terminated}'
```

Nếu chưa có lần terminate trước đó, phần lastState hoặc previous log có thể trống. Nếu Pod cũ đã bị thay thế, cần log tập trung và lịch sử metrics để điều tra.

### 10.2. Xác minh nhận diện container

Với image có executable `java`:

```powershell
kubectl exec $podName -n spring-cloud-lab -c app -- java -XshowSettings:system -version
kubectl exec $podName -n spring-cloud-lab -c app -- java -XshowSettings:vm -version
kubectl exec $podName -n spring-cloud-lab -c app -- java -Xlog:os+container=trace -version
```

Dùng kết quả để xem JVM nhận được thông tin cgroup, bộ nhớ và CPU thế nào. Nếu JVM nhìn thấy bộ nhớ node thay vì limit container, phải kiểm tra JDK build, khả năng hỗ trợ cgroup và cấu hình runtime trước khi tin vào phần trăm heap.

Các lệnh này tạo **một JVM chẩn đoán mới**, có thể đọc cùng environment nhưng không chắc có đầy đủ đối số của JVM ứng dụng. Chúng không thay thế việc đọc flags của tiến trình đang phục vụ request. Trong container đã gần cạn memory, tiến trình chẩn đoán cũng tiêu thụ thêm tài nguyên; ưu tiên tái hiện trên Pod thử nghiệm.

### 10.3. Đọc tiến trình ứng dụng bằng jcmd

Nếu image có `jcmd` và Java là PID `1`:

```powershell
kubectl exec $podName -n spring-cloud-lab -c app -- jcmd 1 VM.flags
kubectl exec $podName -n spring-cloud-lab -c app -- jcmd 1 GC.heap_info
kubectl exec $podName -n spring-cloud-lab -c app -- jcmd 1 Thread.print
```

Nếu launcher không exec Java thành PID 1, xác định PID thực tế trước. Attach còn phụ thuộc user, namespace và cấu hình cho phép chẩn đoán. Image JRE hoặc distroless có thể không có `jcmd`; hãy chuẩn bị image chẩn đoán phù hợp cho staging thay vì mặc định mọi image đều hỗ trợ.

`Thread.print` giúp xem thread và trạng thái chờ; không dùng riêng số lượng thread để kết luận CPU thiếu. `GC.heap_info` cũng không phản ánh toàn bộ memory container. Xem [The jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).

Đối với cấu hình 1 GiB/50% trong bài, cần xác nhận heap tối đa thực tế ở gần ngân sách 512 MiB, có xét làm tròn. Nếu khác nhiều, tìm flags bị ghi đè từ entrypoint, environment hoặc buildpack.

## 11. Quan sát heap, native memory và latency cùng lúc

### 11.1. Metrics ứng dụng

Khi endpoint metrics được bật và truy cập theo chính sách của môi trường, có thể kiểm tra qua port-forward:

```powershell
kubectl port-forward deployment/catalog -n spring-cloud-lab 18080:8080
```

Trong cửa sổ PowerShell khác:

```powershell
curl.exe "http://localhost:18080/actuator/metrics/jvm.memory.used?tag=area:heap"
curl.exe "http://localhost:18080/actuator/metrics/jvm.memory.max?tag=area:heap"
curl.exe "http://localhost:18080/actuator/metrics/jvm.threads.live"
```

Các meter có sẵn phụ thuộc registry và cấu hình. Theo dõi thêm GC pause, allocation, thread, buffer pool, CPU và độ trễ HTTP. Tên meter trong endpoint Actuator có thể khác tên chuẩn hóa khi xuất sang Prometheus. Xem [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).

Không so sánh trực tiếp heap used với `limits.memory` rồi kết luận container còn an toàn. Heap chỉ là một phần ngân sách.

### 11.2. Native Memory Tracking trong phiên chẩn đoán

Khởi tạo JVM của Pod thử nghiệm với tùy chọn bổ sung:

```text
-XX:NativeMemoryTracking=summary
```

Giữ nguyên các JVM options khác khi thêm tùy chọn này. Sau khi rollout, có thể chạy:

```powershell
kubectl exec $podName -n spring-cloud-lab -c app -- jcmd 1 VM.native_memory summary scale=MB
kubectl exec $podName -n spring-cloud-lab -c app -- jcmd 1 VM.native_memory baseline
```

Sau một khoảng tải ổn định:

```powershell
kubectl exec $podName -n spring-cloud-lab -c app -- jcmd 1 VM.native_memory summary.diff scale=MB
```

Lấy lại `$podName` nếu rollout đã tạo Pod mới. NMT cần được bật từ lúc JVM khởi tạo và có overhead; dùng nó có chủ đích. Đối chiếu phần tăng của Heap, Class, Thread, Code, GC với bộ nhớ container, đồng thời nhớ giới hạn phạm vi NMT đã nêu ở trên.

Không cộng tổng committed của NMT với container working set: hai số này mô tả các góc nhìn chồng lấn nhau.

## 12. Phân biệt các kiểu thiếu tài nguyên

| Dấu hiệu | Giả thuyết cần kiểm tra | Bằng chứng và hành động tiếp theo |
| --- | --- | --- |
| `OutOfMemoryError: Java heap space` | Heap không đáp ứng live set hoặc có giữ tham chiếu ngoài dự kiến | Xem heap sau GC, cache, queue, payload và lịch sử tăng; chỉ tăng heap khi ngân sách cho phép |
| `OutOfMemoryError: Metaspace` | Giới hạn metaspace thiếu hoặc số class/classloader tăng | Đọc giới hạn hiệu lực, số lớp và hoạt động tạo proxy/classloader |
| Lỗi cấp direct buffer | Buffer ngoài heap hoặc mức đồng thời vượt dự toán | Xem buffer pool, client mạng, vòng đời buffer và giới hạn direct memory |
| `unable to create native thread` | Thiếu native memory hoặc chạm giới hạn thread/PID | Xem số thread, pool không giới hạn, stack và giới hạn PID |
| Last termination `OOMKilled` | Tiến trình bị OOM killer kết thúc | Đối chiếu memory limit, metrics, thời điểm và bằng chứng node/cgroup |
| Exit code `137` | Tiến trình nhận SIGKILL trong nhiều môi trường Linux | Không dùng riêng code 137 để kết luận OOM; xem termination reason và sự kiện |
| Pod `Evicted` | Áp lực tài nguyên hoặc điều kiện eviction trên node | Đọc message, events và trạng thái node |
| Latency tăng, CPU throttling cao | Quota CPU hoặc mức đồng thời không phù hợp | Đối chiếu usage, throttling, queue, GC và probe failures |

Java OOM và kernel OOM kill là hai đường lỗi khác nhau. Kernel có thể kill JVM trước khi JVM ghi được OOM log hoặc heap dump. Kubernetes minh họa việc vượt giới hạn bộ nhớ và termination trong [Assign Memory Resources to Containers and Pods](https://kubernetes.io/docs/tasks/configure-pod-container/assign-memory-resource/).

Nếu cần heap dump cho điều tra, chuẩn bị trước `HeapDumpOnOutOfMemoryError`, đường dẫn ghi được và dung lượng lưu trữ phù hợp. Không kỳ vọng dump xuất hiện khi tiến trình bị SIGKILL. Heap dump có thể chứa dữ liệu đã đọc từ Secret; cần kiểm soát quyền truy cập và thời gian lưu. Tránh đặt dump lớn vào `emptyDir.medium: Memory` khi đang chẩn đoán thiếu RAM.

## 13. Thực nghiệm để chốt cấu hình

Thực hiện trên môi trường thử nghiệm, dùng cùng image và bộ dữ liệu đại diện:

1. **Ghi lại đầu vào.** Lưu trong kết quả thử nghiệm JDK build, image, requests/limits, JVM flags, loại image và tính năng Spring Cloud Kubernetes đang bật.
2. **Đo cold start.** Từ Pod mới tới Ready, quan sát CPU, memory peak và startup log; thử cả khi nhiều replica bắt đầu cùng lúc.
3. **Làm nóng ứng dụng.** Chạy đủ các đường nghiệp vụ, discovery, HTTP client và nạp cấu hình thực sự được sử dụng.
4. **Giữ tải ổn định.** Theo dõi heap sau GC, native/container memory, latency, errors, CPU và thread count.
5. **Tạo tải đột biến có giới hạn.** Kiểm tra timeout, queue, mức đồng thời và khả năng trở về trạng thái ổn định.
6. **Thử thao tác cấu hình đúng phạm vi.** Nếu có Configuration Watcher, thực hiện refresh cấu hình ứng dụng; quan sát các bean/client có được giải phóng đúng vòng đời hay không.
7. **Thay một biến.** Ví dụ thay CPU limit trong khi giữ ngân sách heap, hoặc thay heap trong khi giữ CPU. So sánh trên cùng kịch bản.
8. **Chốt cấu hình và cách theo dõi.** Ghi lý do chọn heap, biên dự phòng, request, limit và ngưỡng cảnh báo; triển khai dần rồi theo dõi.

Đối với bài học này, một kết quả đạt yêu cầu cần có các bằng chứng:

- JVM đọc đúng giới hạn container và heap tối đa hiệu lực đã được xác nhận.
- Không có restart do thiếu tài nguyên trong kịch bản thử đã mô tả.
- Heap sau GC và bộ nhớ ngoài heap không tăng không giới hạn qua các chu kỳ tải.
- Container còn khoảng dự phòng đã lựa chọn tại các đỉnh quan sát được.
- Độ trễ, tỷ lệ lỗi và thời gian startup đáp ứng mục tiêu đã đặt.
- Không có hàng đợi hoặc thread pool tăng vô hạn để duy trì throughput.
- Đổi JVM options được xác minh trên tiến trình mới, không chỉ bằng việc xem ConfigMap đã thay đổi.

Bằng chứng trên chỉ có hiệu lực trong phạm vi tải và thời gian đã thử. Cần tiếp tục quan sát khi lượng dữ liệu, số service, payload hoặc tính năng tích hợp thay đổi.

## 14. Áp dụng vào Spring Cloud Kubernetes

Khi dự toán tài nguyên, hãy giữ đúng các thành phần mà ứng dụng thật sự cần:

- **DiscoveryClient:** số lượng tài nguyên được quan sát và phạm vi namespace có thể ảnh hưởng dữ liệu giữ trong bộ nhớ. Chọn phạm vi đáp ứng nghiệp vụ và RBAC tương ứng; không mở quyền toàn cluster chỉ để tiện cấu hình.
- **ConfigMap/Secret:** chỉ nạp dữ liệu cần thiết. Việc dữ liệu đến từ Kubernetes không làm nó miễn phí về bộ nhớ sau khi được chuyển thành cấu hình hoặc đối tượng.
- **Spring Cloud LoadBalancer và HTTP client:** xem cache, pool kết nối, timeout và mức đồng thời trong tổng ngân sách của ứng dụng.
- **Configuration Watcher:** đo riêng nếu chạy như controller/Deployment độc lập. Chỉ cộng tài nguyên của client và luồng xử lý refresh nằm trong JVM ứng dụng vào ngân sách JVM đó.
- **Sức khỏe Pod:** dùng probes để biểu diễn trạng thái ứng dụng, kết hợp metrics và termination reason để điều tra tài nguyên. Một endpoint trả `UP` không chứng minh JVM còn đủ headroom.

Nếu dịch vụ chỉ cần gọi Kubernetes Service qua DNS và đọc cấu hình đã mount, hãy đánh giá việc có cần thêm discovery hoặc watcher vào kiến trúc hay không. Quyết định bỏ hay giữ một thành phần phải dựa trên yêu cầu chức năng và số liệu, không chỉ mong muốn giảm vài MiB.

Kết quả của việc thiết lập tài nguyên là một cấu hình có lý do rõ ràng: container có ngân sách xác định, heap để lại đủ chỗ cho phần ngoài heap, mức đồng thời phù hợp với CPU và có cách kiểm chứng khi tải hoặc cấu hình thay đổi.
