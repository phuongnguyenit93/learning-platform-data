# Managed Service for Prometheus trên GKE

Khi chạy nhiều ứng dụng trên Google Kubernetes Engine (GKE), nhóm vận hành cần biết workload nào đang hoạt động, tỷ lệ request lỗi có tăng hay không, độ trễ thay đổi ra sao và tài nguyên cluster còn đủ hay không. Prometheus cung cấp mô hình thu thập metrics theo chu kỳ, lưu chuỗi thời gian và truy vấn bằng PromQL. Google Cloud Managed Service for Prometheus cung cấp backend tương thích Prometheus được quản lý, giúp lưu trữ và truy vấn metrics ở quy mô Google Cloud mà không phải tự vận hành toàn bộ máy chủ Prometheus.

Trên GKE, **managed collection** triển khai cơ chế thu thập metrics do Google quản lý trong cluster. Người vận hành khai báo workload và endpoint cần scrape bằng tài nguyên Kubernetes như `PodMonitoring` hoặc `ClusterPodMonitoring`; dữ liệu được gửi đến Cloud Monitoring để truy vấn, tạo dashboard và cảnh báo bằng PromQL.

Bài học này tập trung vào cách thiết kế, bật và vận hành Managed Service for Prometheus trên GKE, từ cấu hình endpoint, kiểm tra dữ liệu đến bảo mật, chi phí và xử lý lỗi.

## 1. Prometheus và Managed Service for Prometheus

Prometheus là hệ thống giám sát dựa trên time series. Mỗi mẫu dữ liệu gồm tên metric, tập label, giá trị và thời điểm. Ví dụ:

```text
http_requests_total{method="GET",status="200"} 1842
```

Trong ví dụ này:

- `http_requests_total` là tên metric.
- `method` và `status` là label mô tả chuỗi dữ liệu.
- `1842` là giá trị counter tại thời điểm được ghi nhận.

Prometheus thường hoạt động theo mô hình pull: collector truy cập endpoint metrics của ứng dụng theo một chu kỳ, đọc dữ liệu dạng exposition format rồi lưu thành time series. PromQL dùng để tính toán trên dữ liệu theo khoảng thời gian, tổng hợp theo label và phát hiện điều kiện bất thường.

Google Cloud Managed Service for Prometheus cung cấp dịch vụ lưu trữ và truy vấn tương thích Prometheus. Dữ liệu được lưu trong backend quản lý của Cloud Monitoring. Người dùng có thể dùng PromQL trong giao diện Cloud Monitoring, dashboard, alerting policy và các công cụ tích hợp phù hợp.

Cần phân biệt hai phần:

| Thành phần | Trách nhiệm |
|---|---|
| Managed collection | Khám phá target và scrape metrics từ workload trong cluster |
| Managed Service for Prometheus backend | Nhận, lưu trữ, lập chỉ mục và phục vụ truy vấn time series |
| Cloud Monitoring | Cung cấp metrics scope, dashboard, alerting, IAM và tích hợp vận hành |
| PromQL | Ngôn ngữ truy vấn dữ liệu Prometheus |
| Kubernetes monitoring resources | Khai báo Pod và endpoint mà collector cần thu thập |

Managed Service for Prometheus không tự biết mọi endpoint trong ứng dụng. Nhóm phát triển cần expose metrics endpoint và nhóm nền tảng cần khai báo cách scrape endpoint đó.

## 2. Kiến trúc managed collection trên GKE

Khi bật managed collection, GKE cài đặt và quản lý các thành phần collector cần thiết trong cluster. Collector phát hiện Pod được khai báo trong tài nguyên monitoring, lấy metrics theo chu kỳ rồi gửi dữ liệu đến backend Google Cloud.

~~~mermaid
flowchart TD
    A[Application Pods] --> B[/metrics endpoint]
    C[PodMonitoring or ClusterPodMonitoring] --> D[Managed collectors in GKE]
    B --> D
    D --> E[Google Cloud Managed Service for Prometheus]
    E --> F[Cloud Monitoring metrics scope]
    F --> G[PromQL queries and dashboards]
    F --> H[Alerting policies]
    H --> I[Notification channels]
~~~

Luồng hoạt động:

1. Ứng dụng xuất metrics qua HTTP endpoint, thường là `/metrics`.
2. `PodMonitoring` hoặc `ClusterPodMonitoring` chọn Pod theo label và khai báo port, path, interval.
3. Managed collectors trong GKE khám phá target và scrape dữ liệu.
4. Metrics được gửi đến backend Managed Service for Prometheus.
5. Người vận hành truy vấn dữ liệu bằng PromQL, xây dựng dashboard và cấu hình cảnh báo trong Cloud Monitoring.

Managed collection có thể thu thập một số metrics Kubernetes và node đã tích hợp theo cấu hình GKE. Metrics riêng của ứng dụng vẫn cần được expose và khai báo. Phạm vi metrics hệ thống có thể phụ thuộc loại cluster, phiên bản và cấu hình; hãy kiểm tra target thực tế trước khi dựa vào một metric trong dashboard.

Managed collection giúp giảm công việc quản lý collector và backend, nhưng không loại bỏ trách nhiệm thiết kế metrics. Nhóm vẫn cần kiểm soát số lượng series, label, chu kỳ scrape, quyền truy cập và chất lượng cảnh báo.

## 3. Chuẩn bị project và GKE cluster

Trước khi bật Managed Service for Prometheus, xác định project chứa cluster, location, quyền của người triển khai, mạng đi ra Google APIs và project dùng để xem metrics.

### Bật API cần thiết

Cloud Monitoring API cần được bật trong project:

~~~bash
gcloud services enable monitoring.googleapis.com \
  --project="PROJECT_ID"
~~~

Người thực hiện cần quyền bật service API. Nếu tổ chức dùng project quản trị hoặc metrics scope riêng, hãy xác định rõ project nào chứa cluster và project nào dùng làm scoping project để truy vấn.

### Bật managed collection cho cluster hiện có

Với GKE cluster hiện có, có thể bật managed collection bằng Google Cloud CLI:

~~~bash
gcloud container clusters update "CLUSTER_NAME" \
  --location="LOCATION" \
  --enable-managed-prometheus \
  --project="PROJECT_ID"
~~~

Khi tạo cluster mới, có thể bật tùy chọn tương ứng trong lệnh tạo cluster hoặc cấu hình cluster. Cú pháp cụ thể có thể thay đổi theo loại cluster và phiên bản Google Cloud CLI; kiểm tra `gcloud container clusters create --help` hoặc tài liệu GKE đang áp dụng trước khi chạy trong production.

Sau khi bật, chờ các thành phần quản lý được triển khai và kiểm tra trạng thái cluster. Không giả định lệnh update thành công đồng nghĩa mọi target ứng dụng đã được scrape.

### Kiểm tra trạng thái trong cluster

Có thể kiểm tra tài nguyên monitoring và các collector:

~~~bash
kubectl get podmonitoring -A
kubectl get clusterpodmonitoring
kubectl get pods -n gmp-system
~~~

Nếu cluster chưa có tài nguyên `PodMonitoring`, lệnh đầu có thể trả về danh sách rỗng. Nếu namespace collector khác với kỳ vọng hoặc cluster chưa hoàn tất triển khai, kiểm tra trạng thái managed collection và sự kiện Kubernetes trước khi kết luận collector lỗi.

Với cluster dùng private nodes, xác minh đường kết nối cần thiết đến Google APIs, DNS, proxy hoặc Private Google Access theo kiến trúc mạng. Collector cần gửi metrics đến backend; firewall hoặc egress policy quá chặt có thể làm gián đoạn việc gửi dữ liệu.

## 4. Expose metrics từ ứng dụng

Ứng dụng cần cung cấp endpoint metrics mà collector có thể truy cập từ mạng Pod. Endpoint thường dùng HTTP và đường dẫn `/metrics`, nhưng có thể tùy chỉnh.

Ví dụ, một container khai báo port có tên `metrics`:

~~~yaml
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
      containers:
        - name: app
          image: REGION-docker.pkg.dev/PROJECT_ID/apps/orders-api:VERSION
          ports:
            - name: http
              containerPort: 8080
            - name: metrics
              containerPort: 9090
~~~

Ứng dụng phải thực sự lắng nghe trên port 9090 và xuất dữ liệu theo định dạng Prometheus. Chỉ khai báo `containerPort` không tự tạo endpoint metrics. Thư viện client Prometheus cho ngôn ngữ ứng dụng thường hỗ trợ counter, gauge, histogram và summary.

Các loại metric phổ biến:

| Loại | Ý nghĩa | Ví dụ |
|---|---|---|
| Counter | Giá trị chỉ tăng, trừ khi process khởi động lại | Tổng request, exception, message đã xử lý |
| Gauge | Giá trị có thể tăng hoặc giảm | Số request đang xử lý, độ dài queue |
| Histogram | Phân phối quan sát theo bucket | Thời gian xử lý request, kích thước payload |
| Summary | Phân phối quan sát và quantile được tính ở phía client | Độ trễ theo quantile của từng process |

Nên ưu tiên histogram cho các phép tổng hợp latency trên nhiều Pod. Quantile được tính riêng trên từng Summary thường không thể tổng hợp chính xác thành quantile toàn cluster.

### Thiết kế tên metric và label

Tên metric cần thể hiện ý nghĩa, đơn vị và loại dữ liệu. Ví dụ:

- `http_requests_total`: tổng request đã xử lý.
- `http_request_duration_seconds_bucket`: bucket thời gian xử lý request.
- `queue_messages_pending`: số message đang chờ.
- `process_resident_memory_bytes`: bộ nhớ resident của process.

Label nên có số lượng giá trị hữu hạn và ổn định, chẳng hạn `method`, `status_code`, `namespace`, `app` hoặc `region`. Tránh label có giá trị gần như duy nhất cho mỗi request hoặc user.

Không dùng các trường như user ID, email, session ID, request ID, trace ID hoặc URL chứa mã định danh làm label metric. Mỗi tổ hợp label tạo một time series; cardinality tăng nhanh làm tăng chi phí, dung lượng và độ trễ truy vấn.

## 5. Khai báo PodMonitoring

`PodMonitoring` là tài nguyên Kubernetes namespaced. Nó chọn Pod trong cùng namespace với tài nguyên và khai báo endpoint cần scrape. Đây là cách phổ biến để cấu hình metrics cho một ứng dụng cụ thể.

Ví dụ dưới đây chọn các Pod có label `app: orders-api` trong namespace `production`:

~~~yaml
apiVersion: monitoring.googleapis.com/v1
kind: PodMonitoring
metadata:
  name: orders-api
  namespace: production
spec:
  selector:
    matchLabels:
      app: orders-api
  endpoints:
    - port: metrics
      path: /metrics
      interval: 30s
~~~

Lưu thành `pod-monitoring.yaml` và áp dụng:

~~~bash
kubectl apply -f pod-monitoring.yaml
kubectl describe podmonitoring orders-api -n production
~~~

Các trường chính:

- `metadata.namespace`: namespace chứa tài nguyên PodMonitoring.
- `spec.selector.matchLabels`: label selector chọn Pod cần scrape.
- `endpoints.port`: tên port của container hoặc port được hỗ trợ trong cấu hình.
- `endpoints.path`: đường dẫn HTTP trả về metrics.
- `endpoints.interval`: chu kỳ scrape; giá trị ngắn hơn tạo nhiều mẫu dữ liệu và tải lớn hơn.

Tên port `metrics` trong PodMonitoring phải khớp port mà Pod expose. Nếu ứng dụng dùng port 9090 nhưng cấu hình trỏ sang port HTTP 8080, collector có thể kết nối nhầm endpoint hoặc không đọc được metrics.

Có thể khai báo nhiều endpoint trong một PodMonitoring khi một workload cung cấp nhiều endpoint metrics. Tuy nhiên, nên giữ cấu hình rõ ràng để người vận hành dễ xác định target nào tương ứng với ứng dụng nào.

### PodMonitoring và ClusterPodMonitoring

Hai loại tài nguyên có phạm vi khác nhau:

| Tài nguyên | Phạm vi chọn Pod | Trường hợp sử dụng |
|---|---|---|
| PodMonitoring | Trong namespace chứa tài nguyên | Metrics của một ứng dụng hoặc nhóm workload trong namespace |
| ClusterPodMonitoring | Trên phạm vi cluster | Một thành phần dùng chung cần scrape Pod ở nhiều namespace |

Ví dụ ClusterPodMonitoring cho một exporter được triển khai theo cùng label trên các namespace:

~~~yaml
apiVersion: monitoring.googleapis.com/v1
kind: ClusterPodMonitoring
metadata:
  name: shared-exporter
spec:
  selector:
    matchLabels:
      app: shared-exporter
  endpoints:
    - port: metrics
      path: /metrics
      interval: 30s
~~~

Do tài nguyên cluster-scoped có thể chọn Pod ở nhiều namespace, selector cần đủ cụ thể để tránh thu thập nhầm hoặc trùng target. Chỉ dùng ClusterPodMonitoring khi phạm vi toàn cluster thực sự cần thiết; nếu workload thuộc một namespace, PodMonitoring thường dễ kiểm soát hơn.

### Tránh scrape trùng

Một Pod có thể được chọn bởi nhiều tài nguyên monitoring. Điều này có thể tạo target trùng, tăng ingestion và gây nhầm lẫn khi truy vấn. Khi thiết kế selector, hãy kiểm tra toàn bộ PodMonitoring và ClusterPodMonitoring đang áp dụng, kể cả cấu hình do nhóm nền tảng hoặc chart cài đặt.

Nếu cluster đang dùng Prometheus Operator với `ServiceMonitor` hoặc `PodMonitor`, không mặc định rằng managed collection sẽ tự đọc các custom resource đó. Hãy chuyển cấu hình sang tài nguyên monitoring mà GKE Managed Service for Prometheus hỗ trợ hoặc triển khai cơ chế collection tương thích đã được kiểm chứng.

## 6. Truy vấn metrics bằng PromQL

PromQL cho phép tính toán tốc độ tăng của counter, tổng hợp theo label, lấy phân vị từ histogram và so sánh giá trị theo thời gian.

Có thể mở Cloud Monitoring, chọn Metrics Explorer và sử dụng chế độ PromQL để truy vấn metrics Prometheus. Chọn đúng project hoặc metrics scope chứa dữ liệu và khoảng thời gian phù hợp.

### Tính tốc độ request

Giả sử ứng dụng xuất counter `http_requests_total`:

~~~promql
sum by (namespace, method, status_code) (
  rate(http_requests_total[5m])
)
~~~

`rate()` tính tốc độ tăng trung bình mỗi giây trong cửa sổ 5 phút. Dùng `rate()` cho counter thay vì lấy giá trị hiện tại của counter làm lưu lượng tức thời.

Tổng request theo namespace:

~~~promql
sum by (namespace) (
  rate(http_requests_total[5m])
)
~~~

### Tính tỷ lệ lỗi

Ví dụ metric có label `status_code`:

~~~promql
sum(rate(http_requests_total{status_code=~"5.."}[5m]))
/
sum(rate(http_requests_total[5m]))
~~~

Biểu thức trả về tỷ lệ request 5xx trên tổng request trong cửa sổ 5 phút. Cần xử lý trường hợp mẫu số bằng 0 và kiểm tra tên label thực tế do ứng dụng xuất ra.

### Tính p95 latency từ histogram

Nếu ứng dụng xuất histogram `http_request_duration_seconds_bucket`:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_request_duration_seconds_bucket[5m])
  )
)
~~~

Biểu thức trên tổng hợp bucket trên các Pod trước khi tính phân vị p95. Nếu cần phân tách theo namespace hoặc service, thêm label tương ứng vào phần `sum by`.

### Kiểm tra target

Prometheus cung cấp metric `up` cho trạng thái scrape của target:

~~~promql
up
~~~

Giá trị 1 thường biểu thị scrape thành công; giá trị 0 cho biết lần scrape gần nhất thất bại. Có thể lọc theo namespace hoặc job sau khi xác định các label có trong dữ liệu:

~~~promql
up{namespace="production"}
~~~

Không nên giả định mọi cluster đều có cùng tập label. Hãy khám phá series thực tế trong PromQL editor trước khi viết dashboard và alert.

### Tìm hiểu tên metric trong Cloud Monitoring

Metrics Prometheus được hiển thị trong hệ sinh thái Cloud Monitoring với metric type theo quy ước Prometheus, thường có tiền tố `prometheus.googleapis.com/`. Tên metric, loại metric và label có thể xuất hiện dưới dạng metric descriptor của Cloud Monitoring. Dùng PromQL giúp làm việc theo tên metric Prometheus quen thuộc, trong khi Metrics Explorer cũng hỗ trợ xem metadata và các tài nguyên liên quan.

## 7. Dashboard và cảnh báo

Metrics chỉ hữu ích khi giúp người vận hành trả lời câu hỏi và hành động đúng lúc. Dashboard nên phản ánh sức khỏe dịch vụ, mức sử dụng tài nguyên và trải nghiệm người dùng.

### Thiết kế dashboard theo tín hiệu vận hành

Với một API chạy trên GKE, có thể tổ chức dashboard thành các nhóm:

| Nhóm | Metric hoặc truy vấn gợi ý | Câu hỏi cần trả lời |
|---|---|---|
| Traffic | Request/second theo service, namespace | Lưu lượng có thay đổi bất thường? |
| Errors | Tỷ lệ 4xx/5xx, exception rate | Người dùng có gặp lỗi? |
| Latency | p50, p95, p99 từ histogram | Request có chậm hơn bình thường? |
| Saturation | CPU, memory, queue depth, throttling | Workload có gần chạm giới hạn? |
| Availability | `up`, replica ready, Pod restart | Target và workload có hoạt động? |
| Dependencies | Connection pool, DB latency, downstream error | Phụ thuộc bên ngoài có gây ảnh hưởng? |

Tạo dashboard ở Cloud Monitoring và lưu PromQL query theo tên dễ hiểu. Với hệ thống nhiều project, metrics scope cho phép truy vấn dữ liệu từ các project được thêm vào scope; quyền IAM vẫn được áp dụng theo từng tài nguyên và project.

### Cảnh báo bằng PromQL

Cloud Monitoring hỗ trợ tạo alerting policy với PromQL condition. Ví dụ phát hiện target không scrape được trong namespace production:

~~~promql
sum by (namespace, job) (
  up{namespace="production"} == 0
) > 0
~~~

Có thể đặt thời gian duy trì điều kiện, chẳng hạn 5 phút, để tránh cảnh báo do một lần scrape lỗi ngắn. Cấu hình notification channel phù hợp như email, PagerDuty hoặc webhook đã được tổ chức phê duyệt.

Một cảnh báo tốt cần có:

- Tên thể hiện dịch vụ và tác động.
- Điều kiện đủ nhạy để phát hiện vấn đề nhưng tránh nhiễu.
- Duration hoặc cửa sổ đánh giá phù hợp.
- Severity và người chịu trách nhiệm.
- Hướng dẫn xử lý hoặc liên kết runbook.
- Cơ chế deduplicate và grouping để không gửi quá nhiều thông báo.

Không tạo alert chỉ dựa trên CPU cao trong một khoảng rất ngắn nếu chưa hiểu hành vi tải. Kết hợp saturation với latency, error rate, traffic và tình trạng replica để xác định tác động thực tế.

### Recording rule và alert rule

Với truy vấn lặp lại hoặc dashboard phức tạp, recording rule có thể lưu kết quả biểu thức để truy vấn nhanh và thống nhất. Alert rule đánh giá điều kiện và tạo cảnh báo khi trạng thái kéo dài theo chính sách. Trên GKE Managed Service for Prometheus, có thể dùng cơ chế rule evaluation được hỗ trợ trong cấu hình triển khai của tổ chức hoặc dùng Cloud Monitoring alerting policy với PromQL. Chọn một nơi quản lý rule rõ ràng để tránh hai hệ thống cùng phát cảnh báo cho một điều kiện.

## 8. Bảo mật và phân quyền

Metrics thường không chứa secret, nhưng vẫn có thể tiết lộ cấu trúc hệ thống, tên dịch vụ, tenant, endpoint nội bộ, mã lỗi hoặc hành vi người dùng. Cần quản lý metrics như dữ liệu vận hành có kiểm soát.

### Phân quyền IAM

Tách quyền ghi metrics và quyền xem metrics:

- Workload hoặc collector cần quyền ghi metrics theo cơ chế GKE managed collection được cấu hình.
- Người xem dashboard và truy vấn thường cần quyền Monitoring Viewer phù hợp.
- Người tạo alert, dashboard hoặc thay đổi cấu hình monitoring cần quyền quản trị tương ứng.
- Không cấp quyền quản trị project chỉ để một nhóm đọc dashboard.

Các role phổ biến gồm `roles/monitoring.viewer` cho nhu cầu xem và truy vấn, `roles/monitoring.metricWriter` cho principal cần ghi metrics. Với managed collection, kiểm tra danh tính và quyền do GKE thiết lập theo hướng dẫn của nền tảng; tránh tự cấp role rộng cho node service account hoặc toàn bộ workload nếu không cần.

### Bảo vệ endpoint metrics

- Chỉ cho phép collector và thành phần giám sát hợp lệ truy cập endpoint.
- Không expose port metrics ra Internet công khai.
- Dùng NetworkPolicy hoặc cơ chế kiểm soát mạng phù hợp để giới hạn luồng truy cập.
- Không đưa token, mật khẩu, thông tin cá nhân hoặc nội dung request vào metric label.
- Nếu endpoint cần TLS hoặc xác thực, dùng cơ chế được hỗ trợ trong cấu hình scrape và quản lý credential bằng Secret Manager.
- Không dùng cùng một credential có quyền rộng cho nhiều ứng dụng.

### Bảo vệ dữ liệu và truy vấn

Giới hạn quyền truy cập project, metrics scope, dashboard và alert policy theo nhóm. Kiểm tra log truy cập và thay đổi cấu hình monitoring. Khi chia sẻ dashboard, tránh để label hoặc tên series làm lộ thông tin khách hàng hay môi trường nội bộ.

## 9. Hiệu năng, cardinality và chi phí

Chi phí và hiệu năng của Managed Service for Prometheus phụ thuộc lượng dữ liệu được scrape và gửi lên backend. Hai yếu tố thường gây tăng trưởng ngoài dự kiến là chu kỳ scrape quá ngắn và cardinality cao.

### Ước lượng số time series

Một metric có nhiều label. Nếu metric có 5 giá trị method, 6 giá trị status, 20 route và 10 instance, số tổ hợp tối đa có thể đạt:

\[
5 \times 6 \times 20 \times 10 = 60{,}000
\]

Đây là ước lượng tổ hợp lý thuyết; số series thực tế phụ thuộc dữ liệu được phát sinh. Nếu thêm user ID hoặc request ID với hàng triệu giá trị, cardinality có thể tăng rất nhanh.

### Điều chỉnh scrape interval

Ví dụ:

| Chu kỳ scrape | Mẫu trên một series trong một giờ | Nhận xét |
|---|---:|---|
| 15 giây | 240 | Phù hợp một số tín hiệu cần độ phân giải cao, ingestion tăng |
| 30 giây | 120 | Cân bằng thường gặp cho metrics ứng dụng |
| 60 giây | 60 | Giảm ingestion, phù hợp tín hiệu ít biến động |

Đây là số mẫu lý thuyết nếu target luôn scrape thành công. Tổng lượng dữ liệu còn phụ thuộc số target, số metric và label.

Không đặt interval quá ngắn cho mọi workload. Với metrics phục vụ capacity planning, 30 hoặc 60 giây có thể đủ; một số tín hiệu vận hành cần độ phân giải cao hơn. Đánh giá yêu cầu phát hiện, giới hạn hệ thống và ngân sách trước khi chọn.

### Giảm cardinality

- Dùng label có tập giá trị hữu hạn.
- Không gắn định danh duy nhất cho từng request hoặc người dùng.
- Tránh xuất metric trùng lặp từ nhiều exporter.
- Dùng metric relabeling hoặc cơ chế lọc được hỗ trợ để bỏ series không cần thiết.
- Giới hạn số label và kích thước label theo thiết kế.
- Theo dõi số active series, ingestion và thay đổi đột biến sau mỗi lần phát hành.

Đừng loại bỏ metric quan trọng chỉ để giảm chi phí. Xác định tín hiệu nào hỗ trợ SLO, xử lý sự cố và capacity planning, rồi loại bỏ dữ liệu trùng hoặc ít giá trị.

### Theo dõi chi phí

Cloud Monitoring tính phí theo mô hình và bảng giá hiện hành của dịch vụ; Managed Service for Prometheus có chi phí liên quan đến lượng samples ingest và các tính năng sử dụng. Hãy xem trang Billing, báo cáo SKU và tài liệu giá hiện hành để xác định đơn giá theo region/tài khoản. Không dùng một mức giá cố định trong runbook nếu chưa được kiểm tra theo thời điểm.

## 10. Vận hành nhiều cluster và nhiều project

Một tổ chức có thể có nhiều cluster GKE theo môi trường hoặc khu vực. Cần thiết kế label và metrics scope để truy vấn xuyên project mà vẫn phân biệt được nguồn dữ liệu.

Nên chuẩn hóa các chiều nhận diện:

- `project_id`: project chứa cluster.
- `location`: region hoặc zone.
- `cluster`: tên cluster.
- `namespace`: namespace Kubernetes.
- `job` hoặc label ứng dụng: workload logic.

Dùng tên cluster và namespace nhất quán giữa môi trường. Không dùng label `environment` tùy ý nếu cùng một giá trị đã có ý nghĩa khác ở workload khác. Hãy thống nhất quy ước đặt tên và tránh tạo label trùng nghĩa.

### Metrics scope

Metrics scope là cách một scoping project xem dữ liệu Cloud Monitoring từ một hoặc nhiều project được thêm vào scope. Khi dùng nhiều cluster, có thể chọn một project vận hành làm scoping project và thêm các project chứa cluster.

Cách này cho phép dashboard và PromQL truy vấn nhiều nguồn trong cùng phạm vi. Việc thêm project vào metrics scope không tự cấp quyền đọc dữ liệu; principal vẫn cần IAM phù hợp ở các project liên quan.

### Phân tách môi trường

Production và non-production có thể dùng scoping project hoặc dashboard riêng tùy yêu cầu kiểm soát. Điều này giúp giảm nhầm lẫn khi trực sự cố, hạn chế quyền truy cập và theo dõi chi phí theo môi trường.

## 11. Xử lý sự cố thu thập và truy vấn

Khi không thấy metrics hoặc dashboard có dữ liệu thiếu, kiểm tra từ endpoint đến backend theo thứ tự. Không nên bắt đầu bằng cách sửa nhiều cấu hình cùng lúc vì sẽ khó xác định nguyên nhân.

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không có target | Managed collection chưa bật, CRD chưa được nhận diện, selector không khớp Pod | Kiểm tra cluster setting, PodMonitoring, label Pod |
| Target tồn tại nhưng scrape lỗi | Port/path sai, ứng dụng không lắng nghe, NetworkPolicy chặn | Kiểm tra container port, endpoint, Pod logs và network |
| Có target nhưng không có series mong muốn | Ứng dụng chưa expose metric hoặc metric name/label khác | Gọi endpoint trong cluster và kiểm tra nội dung exposition |
| PromQL trả về rỗng | Sai project/metrics scope, khoảng thời gian, label hoặc metric name | Kiểm tra scope, time range, khám phá series |
| Dữ liệu trễ | Chu kỳ scrape, gửi dữ liệu, ingestion hoặc truy vấn | So sánh timestamp sample và trạng thái target |
| Chi phí tăng đột biến | Cardinality, target trùng, interval quá ngắn | Kiểm tra active series, selector và scrape config |
| Một số Pod mất metrics | Pod thay đổi label, restart, readiness hoặc endpoint không ổn định | Kiểm tra rollout, Pod events và target health |

### Kiểm tra cấu hình Kubernetes

~~~bash
kubectl get podmonitoring -A -o yaml
kubectl get clusterpodmonitoring -o yaml
kubectl get pods -n production --show-labels
kubectl describe podmonitoring orders-api -n production
~~~

Đối chiếu label selector với label thực tế của Pod. Kiểm tra port được đặt tên đúng và ứng dụng lắng nghe trên địa chỉ có thể truy cập từ collector.

### Kiểm tra endpoint từ trong cluster

Có thể dùng một Pod chẩn đoán được phê duyệt để gọi endpoint nội bộ:

~~~bash
kubectl run metrics-check \
  -n production \
  --rm -it \
  --restart=Never \
  --image=curlimages/curl \
  -- curl -sS http://POD_IP:9090/metrics
~~~

Thay host và port bằng endpoint thực tế trong cluster. Nếu dùng Pod IP hoặc Service DNS, bảo đảm lệnh phản ánh đúng cách collector truy cập target. Xóa Pod chẩn đoán sau khi hoàn tất và tránh in dữ liệu nhạy cảm ra terminal.

### Kiểm tra truy vấn và metrics scope

Nếu endpoint scrape thành công nhưng PromQL không trả kết quả:

1. Chọn đúng project hoặc metrics scope trong Cloud Monitoring.
2. Mở rộng time range để bao gồm thời điểm scrape.
3. Chạy `up` để xác định target có dữ liệu hay không.
4. Kiểm tra metric name và label thực tế.
5. Kiểm tra bộ lọc dashboard hoặc alert có loại bỏ series hay không.
6. Xem log collector và lỗi ghi metrics nếu có quyền truy cập.

Không kết luận collector hỏng chỉ vì một metric cụ thể không xuất hiện; metric có thể chỉ được phát khi có sự kiện hoặc chưa được ứng dụng đăng ký.

## 12. Tình huống thực hành: giám sát orders-api trên GKE

Một nhóm triển khai `orders-api` trên cluster `gke-prod`, namespace `production`. Ứng dụng expose metrics tại port 9090, path `/metrics`, với các counter request và histogram latency.

### Bước 1 — Bật managed collection

Xác minh Monitoring API đã bật và cluster đã bật managed collection:

~~~bash
gcloud services enable monitoring.googleapis.com \
  --project="PROJECT_ID"

gcloud container clusters update "gke-prod" \
  --location="asia-southeast1" \
  --enable-managed-prometheus \
  --project="PROJECT_ID"
~~~

### Bước 2 — Xác nhận Pod có label và port

Pod template của Deployment cần có label `app: orders-api` và port container tên `metrics`. Kiểm tra:

~~~bash
kubectl get pods -n production --show-labels
kubectl get deployment orders-api -n production -o yaml
~~~

### Bước 3 — Tạo PodMonitoring

~~~yaml
apiVersion: monitoring.googleapis.com/v1
kind: PodMonitoring
metadata:
  name: orders-api
  namespace: production
spec:
  selector:
    matchLabels:
      app: orders-api
  endpoints:
    - port: metrics
      path: /metrics
      interval: 30s
~~~

Áp dụng và kiểm tra:

~~~bash
kubectl apply -f pod-monitoring.yaml
kubectl describe podmonitoring orders-api -n production
~~~

### Bước 4 — Xác minh metrics

Trong Cloud Monitoring PromQL editor, chạy:

~~~promql
up{namespace="production"}
~~~

Sau đó kiểm tra tốc độ request:

~~~promql
sum by (status_code) (
  rate(http_requests_total{namespace="production"}[5m])
)
~~~

Và p95 latency:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_request_duration_seconds_bucket{namespace="production"}[5m])
  )
)
~~~

Tên metric và label phải khớp với những gì ứng dụng thực tế xuất ra. Nếu query rỗng, kiểm tra target, endpoint và metrics scope trước khi sửa truy vấn.

### Bước 5 — Tạo cảnh báo

Tạo PromQL alert condition phát hiện target không scrape được:

~~~promql
sum by (namespace, job) (
  up{namespace="production"} == 0
) > 0
~~~

Đặt thời gian duy trì phù hợp, gán severity, chọn notification channel và liên kết runbook. Có thể tạo cảnh báo riêng cho error rate hoặc latency khi nhóm đã xác định ngưỡng theo SLO.

### Bước 6 — Đưa vào vận hành

- Gắn dashboard với service owner và môi trường.
- Kiểm tra cảnh báo trong một lần diễn tập.
- Theo dõi số series và lượng samples ingest.
- Rà soát label mới sau mỗi lần phát hành.
- Đưa manifest PodMonitoring vào quy trình quản lý cấu hình có review.
- Kiểm tra quyền IAM, metrics scope và notification channel định kỳ.

Sau khi hoàn thành, nhóm có thể quan sát lưu lượng, lỗi, latency và tình trạng scrape của `orders-api` từ Cloud Monitoring mà không phải tự vận hành một backend Prometheus riêng cho cluster.

## 13. Checklist triển khai và vận hành

### Trước khi bật

- [ ] Xác định project, cluster, location và metrics scope.
- [ ] Bật Cloud Monitoring API.
- [ ] Xác minh quyền triển khai và quyền ghi metrics theo mô hình GKE.
- [ ] Kiểm tra egress đến Google APIs và chính sách mạng.
- [ ] Thống nhất tên metric, label và chu kỳ scrape.

### Khi cấu hình collection

- [ ] Managed collection đã được bật trên cluster.
- [ ] Ứng dụng expose endpoint metrics hợp lệ.
- [ ] PodMonitoring hoặc ClusterPodMonitoring chọn đúng Pod.
- [ ] Port, path và interval khớp với ứng dụng.
- [ ] Không có target trùng hoặc selector quá rộng.
- [ ] Kiểm tra dữ liệu bằng `up` và một truy vấn PromQL thực tế.

### Khi đưa vào production

- [ ] Dashboard thể hiện traffic, errors, latency và saturation.
- [ ] Alert có severity, duration, notification channel và runbook.
- [ ] IAM được cấp theo nguyên tắc tối thiểu.
- [ ] Endpoint metrics không bị public ngoài ý muốn.
- [ ] Label không chứa thông tin nhạy cảm và không gây cardinality cao.
- [ ] Có theo dõi ingestion, active series và chi phí.

### Vận hành định kỳ

- [ ] Rà soát target lỗi và metrics bị mất.
- [ ] Kiểm tra selector khi Deployment thay đổi label.
- [ ] Rà soát dashboard, alert và notification channel.
- [ ] Kiểm tra metrics scope và quyền truy cập đa project.
- [ ] Đánh giá cardinality và chu kỳ scrape khi thêm workload.
- [ ] Diễn tập xử lý cảnh báo và cập nhật runbook.

Managed Service for Prometheus trên GKE kết hợp cách thu thập quen thuộc của Prometheus với backend quản lý của Google Cloud. Khi ứng dụng xuất metrics rõ ràng, PodMonitoring chọn đúng target, label được thiết kế có kiểm soát và PromQL gắn với dashboard cùng cảnh báo có ý nghĩa, nhóm vận hành có thể theo dõi sức khỏe workload trên một hoặc nhiều cluster mà không phải tự quản lý toàn bộ hạ tầng lưu trữ Prometheus.

