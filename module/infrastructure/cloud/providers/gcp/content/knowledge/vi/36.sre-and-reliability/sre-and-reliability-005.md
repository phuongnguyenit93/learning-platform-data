# Thiết kế health checks, readiness và liveness theo nền tảng

Một dịch vụ có thể vẫn có tiến trình đang chạy nhưng không còn xử lý được yêu cầu. Ngược lại, một tiến trình có thể khỏe mạnh nhưng chưa nạp xong cấu hình, chưa kết nối được tài nguyên bắt buộc hoặc đang quá tải nên chưa thể nhận thêm lưu lượng. Nếu chỉ kiểm tra VM hay container còn hoạt động, hệ thống khó phân biệt những trạng thái này và dễ đưa ra hành động phục hồi sai.

Health check là phép kiểm tra có chủ đích để nền tảng quyết định một workload đã khởi động, còn hoạt động hay có thể nhận lưu lượng hay chưa. Trong Google Cloud, cách triển khai khác nhau giữa GKE, Cloud Run và Compute Engine. Thiết kế đúng cần bắt đầu từ ý nghĩa của từng trạng thái, sau đó mới chọn loại probe, endpoint, ngưỡng và hành động phù hợp.

## 1. Phân biệt startup, liveness và readiness

Ba loại kiểm tra thường gặp giải quyết ba câu hỏi khác nhau:

| Loại kiểm tra | Câu hỏi | Khi thất bại, nền tảng thường làm gì? | Ví dụ |
| --- | --- | --- | --- |
| Startup | Ứng dụng đã hoàn tất khởi tạo và có thể bước sang giai đoạn phục vụ chưa? | Dừng và khởi động lại container hoặc coi VM chưa hoàn tất khởi tạo, tùy nền tảng. | Chờ tải cấu hình, khởi tạo cache, chạy migration cần thiết và mở listener. |
| Liveness | Tiến trình còn có khả năng tiếp tục tiến triển không? | Khởi động lại container hoặc kích hoạt cơ chế sửa chữa VM nếu dùng autohealing. | Phát hiện deadlock, event loop bị treo hoặc worker không còn tiến triển. |
| Readiness | Workload có thể nhận thêm yêu cầu ngay lúc này không? | Ngừng gửi lưu lượng mới đến workload; tiến trình thường vẫn tiếp tục chạy. | Đang khởi tạo, mất kết nối tới dependency bắt buộc, đang drain hoặc chủ động tạm ngừng nhận việc. |

Startup probe hữu ích với ứng dụng khởi động chậm. Khi startup thành công, nền tảng mới bắt đầu liveness và readiness theo cách triển khai của nó. Liveness dành cho lỗi nội tại mà tiến trình không thể tự phục hồi. Readiness dành cho trạng thái tạm thời khiến workload không nên nhận yêu cầu mới.

Không nên dùng một endpoint duy nhất với logic giống hệt nhau cho mọi loại kiểm tra. Ví dụ, database tạm thời không truy cập được có thể khiến ứng dụng chưa sẵn sàng nhận yêu cầu, nhưng không có nghĩa tiến trình đã deadlock và cần bị khởi động lại. Nếu liveness phụ thuộc trực tiếp vào mọi dịch vụ bên ngoài, một sự cố chung của dependency có thể làm nhiều workload đồng loạt restart, tạo thêm tải và kéo dài sự cố.

## 2. Thiết kế hợp đồng health endpoint

Một ứng dụng HTTP có thể cung cấp ba endpoint riêng:

| Endpoint ví dụ | Điều kiện trả thành công | Điều kiện trả thất bại |
| --- | --- | --- |
| `GET /startupz` | Cấu hình đã nạp, khởi tạo cốt lõi hoàn tất, listener sẵn sàng. | Quá trình khởi tạo vẫn đang chạy hoặc thất bại không thể tiếp tục. |
| `GET /livez` | Tiến trình còn phản hồi và có khả năng xử lý công việc nội bộ. | Phát hiện trạng thái không thể tự phục hồi, chẳng hạn deadlock hoặc bộ xử lý chính không còn tiến triển. |
| `GET /readyz` | Ứng dụng có thể nhận yêu cầu mới và các dependency bắt buộc cho luồng xử lý đang hoạt động. | Ứng dụng đang khởi tạo, drain, quá tải có kiểm soát hoặc thiếu dependency thiết yếu. |

Với HTTP probe, quy ước đơn giản là trả `200 OK` (hoặc một mã thành công được nền tảng chấp nhận) khi đạt điều kiện; trả `503 Service Unavailable` khi chưa sẵn sàng hoặc không khỏe. Endpoint nên phản hồi nhanh, có chi phí thấp và không trả payload nhạy cảm. Không chuyển hướng health endpoint qua trang đăng nhập hoặc reverse proxy có thể làm thay đổi mã phản hồi.

Các endpoint cần kiểm tra đúng điều cần biết:

- `/startupz` không nên đợi những dependency tùy chọn. Nếu database là điều kiện bắt buộc để khởi động ứng dụng, startup có thể xác minh kết nối hoặc xác minh pool đã được tạo. Nếu dependency tạm thời gián đoạn, hãy cân nhắc để ứng dụng khởi động nhưng báo readiness thất bại, thay vì lặp lại khởi động vô hạn.
- `/livez` nên kiểm tra trạng thái nội bộ. Tránh gọi database, API bên ngoài hoặc dịch vụ khác trên mỗi lần liveness probe. Nếu dependency gặp sự cố, restart hàng loạt ứng dụng không thể sửa được dependency đó.
- `/readyz` có thể kiểm tra dependency thiết yếu, connection pool, khả năng ghi/đọc tài nguyên bắt buộc, giới hạn hàng đợi và trạng thái drain. Chỉ kiểm tra những điều kiện thực sự quyết định ứng dụng có thể nhận thêm yêu cầu.

Nếu ứng dụng có nhiều loại yêu cầu với dependency khác nhau, hãy xác định rõ readiness đại diện cho luồng nào. Một dịch vụ vẫn có thể phục vụ endpoint đọc khi dịch vụ ghi tạm thời lỗi; việc đánh dấu toàn bộ instance không sẵn sàng có thể loại bỏ năng lực phục vụ vẫn còn hoạt động.

Health endpoint không thay thế giám sát SLI/SLO. Một probe trả thành công chỉ cho biết điều kiện kiểm tra đã đạt; nó không chứng minh độ trễ, tỷ lệ lỗi, tính đúng đắn dữ liệu hoặc trải nghiệm người dùng đều tốt.

## 3. Chọn cơ chế và tham số probe

Kubernetes và GKE hỗ trợ bốn cơ chế kiểm tra chính:

| Cơ chế | Cách hoạt động | Phù hợp khi |
| --- | --- | --- |
| HTTP GET | Gửi GET tới địa chỉ và port của container; mã phản hồi từ `200` đến dưới `400` được coi là thành công. | Ứng dụng có endpoint health rõ ràng. |
| TCP socket | Thử mở kết nối TCP tới port; kết nối thành công được coi là đạt. | Cần xác nhận listener đã mở, chưa cần kiểm tra logic ứng dụng. |
| Exec | Chạy lệnh trong container; exit code `0` là thành công. | Có phép kiểm tra cục bộ đơn giản mà HTTP/gRPC không thể biểu đạt. |
| gRPC | Gọi gRPC Health Checking Protocol; trạng thái `SERVING` là thành công. | Ứng dụng cung cấp health service theo giao thức gRPC. |

TCP chỉ chứng minh port đang nhận kết nối. Nó không xác nhận ứng dụng đã nạp cấu hình đúng, truy vấn database thành công hay endpoint nghiệp vụ có thể xử lý yêu cầu. Exec probe cũng có chi phí tạo tiến trình; tránh chạy lệnh nặng hoặc đặt tần suất quá dày trên cluster có mật độ Pod cao.

Các tham số thường gặp trong Kubernetes:

| Tham số | Ý nghĩa | Cách chọn |
| --- | --- | --- |
| `initialDelaySeconds` | Thời gian chờ trước lần kiểm tra đầu tiên. | Chỉ dùng khi cần; startup probe thường diễn đạt thời gian khởi tạo rõ hơn. |
| `periodSeconds` | Khoảng thời gian giữa các lần kiểm tra. | Cân bằng tốc độ phát hiện với chi phí probe. |
| `timeoutSeconds` | Thời gian tối đa chờ một lần kiểm tra. | Phải lớn hơn thời gian phản hồi bình thường nhưng đủ nhỏ để phát hiện treo. |
| `failureThreshold` | Số lần thất bại liên tiếp trước khi kết luận thất bại. | Tăng nếu hệ thống có dao động ngắn; không tăng quá cao khiến lỗi kéo dài. |
| `successThreshold` | Số lần thành công liên tiếp để phục hồi trạng thái sau khi thất bại. | Với liveness và startup của Kubernetes phải là `1`; readiness có thể lớn hơn `1`. |
| `terminationGracePeriodSeconds` | Thời gian cho container kết thúc có kiểm soát sau khi bị dừng. | Phù hợp với thời gian drain và hoàn tất công việc đang xử lý. |

Với startup probe, có thể ước tính ngân sách khởi tạo bằng `failureThreshold × periodSeconds`. Ví dụ `30 × 10s` cho phép ứng dụng khoảng 300 giây để khởi động trước khi probe kết luận thất bại. Hãy đo thời gian khởi động thực tế ở điều kiện tải và tài nguyên thấp, rồi đặt ngưỡng có khoảng dự phòng hợp lý.

Liveness thường nên có ngưỡng chịu lỗi cao hơn readiness. Một lần timeout ngắn có thể khiến readiness tạm thời thất bại và workload ngừng nhận lưu lượng mới; liveness chỉ nên thất bại khi ứng dụng thực sự không thể tự phục hồi. Ngược lại, nếu readiness có `failureThreshold` quá lớn, lưu lượng có thể tiếp tục đến instance đã lỗi trong thời gian dài.

## 4. Thiết kế trên GKE và Kubernetes

GKE sử dụng cơ chế probe của Kubernetes. Kubelet kiểm tra từng container trong Pod và thực hiện hành động theo loại probe:

- Startup thất bại đủ số lần: kubelet dừng container; restart policy quyết định việc khởi động lại.
- Liveness thất bại đủ số lần: kubelet dừng và khởi động lại container đó.
- Readiness thất bại: container vẫn chạy, nhưng Pod được đánh dấu `Ready=false`; EndpointSlice của Service không còn dùng Pod đó làm endpoint phục vụ lưu lượng thông thường.

Khi một container có `startupProbe`, kubelet chưa chạy liveness và readiness cho container đó cho đến khi startup thành công. Sau đó liveness và readiness hoạt động định kỳ trong suốt vòng đời container.

### 4.1. Ví dụ cấu hình Deployment

Ví dụ sau giả định ứng dụng nghe HTTP trên port `8080` và triển khai ba endpoint `/startupz`, `/livez`, `/readyz` như phần trước:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          image: REGION-docker.pkg.dev/PROJECT_ID/apps/orders-api:TAG
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /startupz
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 30
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

Áp dụng và quan sát trạng thái:

```bash
kubectl apply -f orders-api.yaml
kubectl rollout status deployment/orders-api -n production
kubectl get pods -n production
kubectl describe pod POD_NAME -n production
kubectl get endpointslice -n production
```

`kubectl describe pod` cho biết sự kiện probe, số lần restart và trạng thái container. EndpointSlice giúp xác minh Pod không sẵn sàng đã được loại khỏi tập endpoint của Service. Không chỉ dựa vào trạng thái `Running`: Pod có thể `Running` nhưng `Ready=false`.

### 4.2. Tách hành vi của readiness và liveness

Giả sử database tạm thời không truy cập được:

1. `/livez` vẫn trả thành công vì tiến trình, event loop và bộ xử lý nội bộ còn hoạt động.
2. `/readyz` trả `503` nếu database là dependency bắt buộc cho mọi yêu cầu đang nhận.
3. Pod tiếp tục chạy, nhưng Service không gửi lưu lượng mới đến Pod đó.
4. Khi database phục hồi và ứng dụng kiểm tra lại thành công đủ số lần, Pod trở lại `Ready`.

Nếu liveness cũng kiểm tra database, mọi Pod có thể bị restart cùng lúc. Sau khi khởi động lại, chúng vẫn không kết nối được database, tiếp tục thất bại và làm tăng tải kết nối trong lúc dependency đang phục hồi.

### 4.3. Health check của GKE LoadBalancer là lớp riêng

Health check của LoadBalancer Service hoạt động bên ngoài cluster và khác với startup, readiness, liveness của Pod. Với GKE LoadBalancer Service, gói kiểm tra có thể được trả lời bởi `kube-proxy` hoặc `cilium-agent` trên node; nó không phải request được gửi trực tiếp đến Pod. Hành vi node nào được coi là khỏe còn phụ thuộc `externalTrafficPolicy` và loại backend.

Vì vậy, nếu Load Balancer báo backend không khỏe, hãy kiểm tra cả hai lớp: Pod readiness/EndpointSlice và health check của Load Balancer. Kiểm tra port đích, NodePort hoặc NEG, firewall rule và `externalTrafficPolicy`. Một health check của Load Balancer thành công không có nghĩa từng Pod đều khỏe; tương tự, Pod Ready không bảo đảm firewall cho health checker đã được cấu hình đúng.

## 5. Thiết kế trên Cloud Run

Cloud Run cung cấp health checks cho container của service. Theo tài liệu Google Cloud hiện hành, service có thể cấu hình:

- Startup probe để xác nhận container đã khởi tạo và sẵn sàng nhận traffic.
- Liveness probe để phát hiện container không thể tiếp tục hoạt động; khi thất bại đủ ngưỡng, Cloud Run dừng container và tạo instance thay thế.
- Readiness probe để tạm ngừng gửi request mới đến instance chưa sẵn sàng; instance vẫn tồn tại và có thể nhận traffic trở lại sau khi probe thành công. Tính năng readiness probe hiện được tài liệu đánh dấu **Preview**.

Cloud Run hỗ trợ HTTP, TCP và gRPC cho các probe này; không có cơ chế `exec` như Kubernetes. HTTP health endpoint cần dùng HTTP/1. Với HTTP probe, phản hồi `2xx` hoặc `3xx` được coi là thành công. Nếu dùng gRPC, ứng dụng phải triển khai gRPC Health Checking Protocol.

### 5.1. Cấu hình YAML minh họa

```yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: orders-api
spec:
  template:
    spec:
      containers:
        - image: REGION-docker.pkg.dev/PROJECT_ID/apps/orders-api:TAG
          ports:
            - containerPort: 8080
          startupProbe:
            httpGet:
              path: /startupz
              port: 8080
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 18
          livenessProbe:
            httpGet:
              path: /livez
              port: 8080
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: 8080
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
            successThreshold: 2
```

Đây là cấu hình minh họa; hãy kiểm tra tính khả dụng của readiness probe trong giai đoạn Preview và phiên bản công cụ đang dùng trước khi áp dụng production. Các thay đổi cấu hình tạo revision mới. Có thể triển khai YAML bằng `gcloud run services replace` sau khi thay các giá trị mẫu bằng tên project, region, image và cấu hình thực tế.

### 5.2. Lưu ý về hành vi Cloud Run

Startup probe là cổng khởi tạo quan trọng. Khi startup probe thành công, Cloud Run coi container đã sẵn sàng nhận traffic. Do đó, endpoint startup phải bảo đảm ứng dụng có thể phục vụ an toàn ngay tại thời điểm đó; không nên để startup thành công khi ứng dụng vẫn chưa thể xử lý request đầu tiên và trông chờ readiness probe chạy sau để ngăn traffic.

Readiness probe bắt đầu sau khi startup thành công. Nếu readiness thất bại vượt `failureThreshold`, Cloud Run ngừng gửi request mới đến instance mà không dừng instance. Khi probe thành công liên tiếp theo `successThreshold`, instance có thể nhận traffic lại. Có một giới hạn cần biết: nếu bật session affinity, Cloud Run vẫn có thể tiếp tục gửi request đến cùng instance dù readiness của instance thất bại.

Liveness phù hợp để phát hiện deadlock hoặc lỗi nội tại không thể tự phục hồi. Khi liveness thất bại đủ ngưỡng, Cloud Run dừng container; các request đang được xử lý có thể kết thúc với lỗi `503`, rồi autoscaling khởi tạo instance mới. Cloud Run cũng giới hạn restart khi một service liên tục gặp restart để tránh vòng lặp khởi động mất kiểm soát.

Nếu ứng dụng khởi động chậm, hãy tăng ngân sách startup probe thay vì nới liveness đến mức phát hiện deadlock quá muộn. Với biến môi trường hoặc secret được nạp lúc khởi động, endpoint startup nên chỉ thành công sau khi cấu hình cần thiết đã được xác minh.

## 6. Thiết kế trên Compute Engine và Managed Instance Groups

Máy ảo Compute Engine không có bộ startup/readiness/liveness probe cho container như Kubernetes. Thay vào đó, Google Cloud cung cấp health check cho hai mục đích vận hành quan trọng:

1. **Load balancing:** xác định backend có đủ khỏe để nhận kết nối hoặc request mới hay không. Backend không khỏe bị loại khỏi tập backend đủ điều kiện nhận traffic; VM không tự động bị khởi động lại chỉ vì health check của Load Balancer thất bại.
2. **MIG autohealing:** xác định VM có ứng dụng không khỏe để Managed Instance Group sửa chữa, thường bằng cách tạo lại VM. Đây là hành động mạnh hơn và cần ngưỡng thận trọng.

Nên tạo health check riêng cho Load Balancer và autohealing. Health check của Load Balancer có thể phát hiện lỗi nhanh để chuyển traffic. Health check autohealing cần bảo thủ hơn để tránh xóa và tạo lại VM khỏe chỉ vì một lần chậm phản hồi hoặc một sự cố mạng ngắn.

### 6.1. Tạo health check cho Load Balancer

Ví dụ tạo HTTP health check cho backend lắng nghe port `8080`:

```bash
gcloud compute health-checks create http orders-lb-health \
  --port=8080 \
  --request-path=/readyz \
  --check-interval=5s \
  --timeout=3s \
  --healthy-threshold=2 \
  --unhealthy-threshold=3
```

Health checker gửi request tới endpoint đã cấu hình. Backend chỉ được coi là khỏe sau số lần probe thành công liên tiếp; nhiều lần thất bại liên tiếp sẽ khiến backend bị đánh dấu không khỏe. Tham số `timeout` phải nhỏ hơn hoặc bằng `check-interval`.

### 6.2. Cấu hình autohealing cho MIG

Tạo health check riêng với khoảng kiểm tra thưa hơn, sau đó gắn nó với MIG:

```bash
gcloud compute health-checks create http orders-autoheal-health \
  --port=8080 \
  --request-path=/healthz \
  --check-interval=30s \
  --timeout=5s \
  --healthy-threshold=2 \
  --unhealthy-threshold=3

gcloud compute instance-groups managed update orders-mig \
  --health-check=orders-autoheal-health \
  --initial-delay=300 \
  --zone=ZONE
```

`--initial-delay` cho MIG thời gian để VM mới khởi động và chạy startup script. Trong thời gian này, MIG bỏ qua các lần health check thất bại vì ứng dụng có thể chưa sẵn sàng. Giá trị tối đa là 3600 giây; ví dụ `300` giây cần được điều chỉnh theo số liệu thời gian khởi tạo thực tế.

Health check của autohealing có thể khiến MIG xóa và tạo lại VM. Trước khi bật, hãy xác minh instance template, startup script, dữ liệu stateful, cấu hình mạng và khả năng tạo VM thay thế. Tránh dùng một endpoint readiness quá nhạy làm tín hiệu autohealing, vì một dependency bên ngoài bị gián đoạn có thể khiến nhiều VM bị thay thế dù bản thân VM vẫn hoạt động.

### 6.3. Firewall và nguồn probe

Health checker của Google Cloud cần kết nối được tới backend. Nếu ingress firewall chặn các nguồn probe hoặc port health check, backend sẽ bị đánh dấu không khỏe dù ứng dụng vẫn chạy. Hãy xác định chính xác loại Load Balancer và backend trước khi tạo firewall rule: dải nguồn probe thay đổi theo loại Load Balancer, IPv4/IPv6 và kiến trúc proxy.

Với nhiều backend dùng Google Front Ends, dải IPv4 thường gặp gồm `35.191.0.0/16` và `130.211.0.0/22`; không áp dụng hai dải này một cách máy móc cho mọi loại Load Balancer. Tra cứu bảng probe IP ranges chính thức, chỉ cho phép protocol/port cần thiết và giới hạn rule bằng network tag hoặc service account phù hợp.

Ví dụ firewall rule minh họa cho một loại backend có yêu cầu các dải IPv4 trên:

```bash
gcloud compute firewall-rules create allow-orders-health-checks \
  --network=VPC_NAME \
  --direction=INGRESS \
  --action=ALLOW \
  --source-ranges=35.191.0.0/16,130.211.0.0/22 \
  --target-tags=allow-health-checks \
  --rules=tcp:8080
```

Không mở toàn bộ VPC hoặc toàn bộ port chỉ để làm health check hoạt động. Kiểm tra cả port của backend service, port của NEG hoặc NodePort tùy kiến trúc Load Balancer.

## 7. So sánh hành vi theo nền tảng

| Nền tảng | Startup | Readiness | Liveness / phục hồi | Điểm cần chú ý |
| --- | --- | --- | --- | --- |
| GKE / Kubernetes | `startupProbe` của kubelet; thất bại sẽ dừng container. | `readinessProbe` đánh dấu Pod không Ready và loại khỏi endpoint Service. | `livenessProbe` thất bại sẽ dừng và restart container. | Có HTTP, TCP, exec, gRPC; probe của Pod khác health check LoadBalancer. |
| Cloud Run service | Startup probe; thành công đồng nghĩa container được coi là sẵn sàng nhận traffic. | Readiness probe đang Preview; tạm dừng traffic mới khi thất bại. | Liveness probe dừng container để Cloud Run tạo instance khác. | HTTP, TCP, gRPC; HTTP probe dùng HTTP/1; session affinity ảnh hưởng readiness. |
| Compute Engine VM / MIG | Startup script và `initial-delay` của autohealing tạo thời gian khởi tạo. | Health check của Load Balancer quyết định backend có nhận traffic hay không. | Health check autohealing có thể khiến MIG tạo lại VM. | Tách health check Load Balancer và autohealing; cấu hình firewall cho probe. |

Các nền tảng không dùng cùng một trạng thái để biểu đạt mọi mục tiêu. Khi thiết kế kiến trúc đa nền tảng, hãy giữ hợp đồng endpoint và ý nghĩa nghiệp vụ nhất quán, sau đó ánh xạ sang hành vi cụ thể của từng nền tảng.

## 8. Kiểm thử và vận hành health checks

Không nên triển khai probe chỉ bằng cách xác nhận endpoint trả `200` trong điều kiện bình thường. Hãy kiểm thử cả những tình huống chuyển trạng thái:

1. **Khởi động chậm:** cố ý làm chậm nạp cấu hình hoặc warm cache. Startup phải có đủ thời gian; liveness không được restart ứng dụng trước khi startup hoàn tất.
2. **Dependency mất kết nối:** ngắt database hoặc API bắt buộc trong môi trường thử nghiệm. Readiness cần phản ánh khả năng phục vụ; liveness không được gây restart hàng loạt nếu tiến trình vẫn tiến triển.
3. **Deadlock hoặc worker treo:** mô phỏng lỗi nội tại có kiểm soát. Liveness cần phát hiện trong khoảng thời gian mục tiêu và nền tảng phải phục hồi đúng cách.
4. **Quá tải:** tăng request hoặc hàng đợi. Readiness có thể tạm ngừng nhận traffic mới theo chính sách backpressure; probe không nên tự tạo thêm tải đáng kể.
5. **Drain và rollout:** kết thúc Pod hoặc thay revision. Ứng dụng cần ngừng nhận yêu cầu mới, hoàn tất hoặc hủy công việc theo thời hạn và cho phép workload mới trở nên Ready trước khi chuyển tải.
6. **Firewall hoặc sai port:** kiểm tra health checker từ đúng mạng và backend. Xác minh probe không bị chặn bởi VPC firewall, NetworkPolicy hoặc cấu hình listener.

Trong vận hành, theo dõi ít nhất:

- Số lần restart container, `CrashLoopBackOff`, thời gian startup và tỷ lệ Pod Ready.
- Số lần readiness/liveness thất bại, nguyên nhân timeout và thời gian phục hồi.
- Trạng thái backend health của Load Balancer và số VM MIG bị sửa chữa.
- Tỷ lệ lỗi, độ trễ, saturation, độ sâu hàng đợi và SLO của luồng nghiệp vụ.

Một cảnh báo health check nên dẫn người vận hành tới lớp lỗi phù hợp: ứng dụng, dependency, tài nguyên, cấu hình probe, IAM, mạng hay firewall. Nếu chỉ cảnh báo “unhealthy” mà không có metric và log liên quan, việc xử lý sẽ chậm và dễ chọn sai hành động.

## 9. Lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Liveness gọi database hoặc API bên ngoài | Dependency lỗi làm nhiều container restart cùng lúc. | Giữ liveness tập trung vào tiến trình; đưa dependency vào readiness nếu thực sự bắt buộc. |
| Dùng TCP port làm bằng chứng duy nhất | Port mở nhưng ứng dụng chưa xử lý được request. | Dùng HTTP/gRPC endpoint phản ánh trạng thái ứng dụng. |
| Không có startup probe cho ứng dụng khởi động lâu | Liveness bắt đầu quá sớm và restart container liên tục. | Thiết kế startup probe với ngân sách đủ cho thời gian khởi tạo. |
| Readiness trả thành công trong lúc drain | Traffic mới vẫn đến instance đang chuẩn bị dừng. | Đổi trạng thái readiness trước khi kết thúc và phối hợp termination grace period. |
| Probe thực hiện truy vấn nặng hoặc tần suất quá dày | Tăng CPU, kết nối và tải lên dependency. | Dùng phép kiểm tra rẻ, cache trạng thái phù hợp và chọn interval có chủ đích. |
| Dùng cùng health check cho Load Balancer và MIG autohealing | Probe nhạy của Load Balancer có thể gây tạo lại VM quá sớm. | Tạo hai health check với ngưỡng và chu kỳ phù hợp từng hành động. |
| Quên firewall hoặc cấu hình sai port | Backend bị coi là không khỏe dù ứng dụng hoạt động. | Xác minh dải IP probe, protocol, port, tag và backend type. |
| Trả chi tiết lỗi hoặc bí mật từ health endpoint | Lộ thông tin nội bộ và tạo bề mặt tấn công. | Trả trạng thái tối giản; lưu chi tiết trong log và metric được kiểm soát. |

## 10. Bài tập thực hành

Một hệ thống xử lý đơn hàng có ba thành phần: API chạy trên Cloud Run, worker chạy trên GKE và một nhóm VM trong MIG chạy tác vụ nền. Database dùng chung đôi khi có sự cố ngắn. Trong thời gian đó, tiến trình ứng dụng vẫn hoạt động nhưng không thể xử lý yêu cầu cần database.

Hãy thiết kế health checks cho hệ thống:

1. Định nghĩa điều kiện thành công/thất bại cho `/startupz`, `/livez` và `/readyz`.
2. Chọn dependency nào cần được kiểm tra trong readiness và giải thích vì sao không đưa tất cả dependency vào liveness.
3. Cấu hình `startupProbe`, `livenessProbe`, `readinessProbe` cho worker GKE. Đặt ngân sách startup theo số liệu khởi động đo được.
4. Cấu hình Cloud Run startup/liveness và đánh giá readiness probe Preview cùng ảnh hưởng của session affinity.
5. Tạo health check Load Balancer và health check autohealing riêng cho MIG; đặt `initial-delay` để tránh sửa chữa VM khi startup script còn chạy.
6. Mô phỏng database gián đoạn, deadlock, quá tải và rollout; ghi lại hành động của từng nền tảng, thời gian phát hiện và thời gian phục hồi.

Kết quả cần có một bảng ánh xạ trạng thái ứng dụng sang hành động của từng nền tảng, cùng các metric giúp xác nhận health check cải thiện độ tin cậy mà không tạo vòng lặp restart hoặc sửa chữa ngoài ý muốn.

## Tài liệu tham khảo

- [Kubernetes: Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)
- [Kubernetes: Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
- [Cloud Run: Configure container health checks for services](https://docs.cloud.google.com/run/docs/configuring/healthchecks)
- [GKE: About LoadBalancer Services and health checks](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/service-load-balancer)
- [Cloud Load Balancing: Health checks overview](https://docs.cloud.google.com/load-balancing/docs/health-check-concepts)
- [Compute Engine: Set up an application-based health check and autohealing](https://docs.cloud.google.com/compute/docs/instance-groups/autohealing-instances-in-migs)
