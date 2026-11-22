# Cloud Monitoring metrics, resource labels và dashboards

Khi một ứng dụng Java chạy trên Google Cloud, log cho biết sự kiện nào đã xảy ra, còn metrics cho thấy hệ thống đang hoạt động như thế nào theo thời gian. CPU tăng liên tục, độ trễ request vượt ngưỡng, số instance thay đổi hoặc hàng đợi ngày càng dài đều là tín hiệu cần được đo và theo dõi. Cloud Monitoring thu thập các phép đo đó thành time series, gắn chúng với tài nguyên phát sinh và cung cấp công cụ để truy vấn, trực quan hóa, tạo dashboard và cảnh báo.

Bài học thuộc module **CLOUD_PROVIDERS_GCP**. Module giúp người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Trong phạm vi bài này, chúng ta tập trung vào Cloud Monitoring, mô hình metric, resource labels, cách tạo metric ứng dụng và cách xây dựng dashboard để quan sát dịch vụ.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích metric type, monitored resource, time series và data point.
- Phân biệt metric labels, resource labels và resource metadata labels.
- Nhận diện metric kind GAUGE, DELTA, CUMULATIVE và value type.
- Chọn metric có sẵn hoặc thiết kế custom metric cho ứng dụng.
- Dùng Metrics Explorer để lọc, nhóm và tổng hợp time series.
- Tạo dashboard tập trung vào sức khỏe của service và trải nghiệm người dùng.
- Kiểm soát cardinality, quyền truy cập và chi phí thu thập metrics.

## 1. Cloud Monitoring và vai trò của metrics

Cloud Monitoring là dịch vụ quan sát của Google Cloud dùng để thu thập, truy vấn và hiển thị metrics từ tài nguyên Google Cloud, ứng dụng tùy chỉnh và một số nền tảng bên ngoài. Một metric là phép đo của một thuộc tính theo thời gian, chẳng hạn:

- CPU utilization của một VM.
- Số request mà một Cloud Run service xử lý.
- Độ trễ request của API.
- Dung lượng bộ nhớ hoặc dung lượng đĩa đang sử dụng.
- Số message đang chờ trong queue.
- Số đơn hàng được tạo hoặc số lần thanh toán thất bại.

Metrics bổ sung cho logs và traces:

| Loại telemetry | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Metrics | Điều gì đang thay đổi và mức độ thay đổi ra sao? | Error rate tăng lên 8% trong 5 phút |
| Logs | Sự kiện cụ thể nào đã xảy ra? | Request của đơn hàng ord-1042 thất bại do upstream timeout |
| Traces | Một request đi qua các thành phần nào và chậm ở đâu? | Span gọi payment-provider chiếm 2,4 giây |

Metrics phù hợp để quan sát xu hướng, so sánh với ngưỡng và phát hiện bất thường. Logs cung cấp ngữ cảnh cho từng sự kiện; traces giúp lần theo đường đi của request. Khi kết hợp ba loại dữ liệu, đội vận hành có thể phát hiện sự cố từ metrics, tìm sự kiện liên quan trong logs và xác định thành phần gây chậm qua traces.

### Nguồn metrics thường gặp

- **Metrics của Google Cloud:** được dịch vụ tạo sẵn, ví dụ CPU của Compute Engine hoặc request count của Cloud Run.
- **Metrics từ agent hoặc tích hợp:** được thu thập từ hệ điều hành, container, ứng dụng và phần mềm bên thứ ba.
- **Custom metrics:** do ứng dụng hoặc người dùng định nghĩa để đo dữ liệu riêng của workload.
- **Prometheus và OpenTelemetry metrics:** được thu thập qua cơ chế tích hợp tương ứng rồi đưa vào hệ thống quan sát.
- **Log-based metrics:** được tạo từ các log entry trong Cloud Logging; đây là loại metric phát sinh từ log, không phải metric mà ứng dụng gửi trực tiếp bằng Monitoring API.

Không cần tạo custom metric cho mọi thứ. Hãy kiểm tra metric có sẵn trước, sau đó chỉ bổ sung phép đo nghiệp vụ hoặc kỹ thuật mà metric tiêu chuẩn chưa thể hiện.

## 2. Mô hình metric: metric type, resource và time series

Cloud Monitoring tổ chức dữ liệu thành **time series**. Mỗi time series chứa các data point có timestamp, mô tả metric đang được đo và mô tả monitored resource tạo ra phép đo.

~~~mermaid
flowchart TD
    A["Metric descriptor<br/>metric type, kind, value type, unit"]
    B["Metric labels<br/>phân loại phép đo"]
    C["Monitored resource<br/>resource type và resource labels"]
    D["Data points<br/>giá trị và timestamp"]
    E["Time series"]
    A --> E
    B --> E
    C --> E
    D --> E
~~~

Ví dụ, metric CPU utilization có thể có metric type là **compute.googleapis.com/instance/cpu/utilization**. Monitored resource là một VM có resource type **gce_instance**. Các data point ghi lại mức CPU tại từng thời điểm. Nếu project có nhiều VM, mỗi VM có time series riêng.

Một time series được phân biệt bởi metric type, các giá trị metric labels và monitored resource cùng các giá trị resource labels. Vì vậy, cùng một metric type có thể tạo ra nhiều time series khi nó được ghi cho nhiều tài nguyên hoặc nhiều tổ hợp label khác nhau.

### Metric descriptor

Metric descriptor là định nghĩa của một metric type. Descriptor mô tả:

- **type:** tên định danh của metric, ví dụ compute.googleapis.com/instance/cpu/utilization.
- **metricKind:** phép đo là GAUGE, DELTA hay CUMULATIVE.
- **valueType:** kiểu dữ liệu của giá trị, chẳng hạn DOUBLE hoặc INT64.
- **unit:** đơn vị đo, ví dụ %, s, By hoặc {request}.
- **labels:** các chiều phân loại thuộc metric type.
- **displayName** và **description:** thông tin giúp người vận hành hiểu metric.

Metric type có sẵn do Google Cloud service định nghĩa. Với custom metric, đội phát triển thiết kế descriptor để các service, dashboard và alert dùng cùng một ý nghĩa đo lường.

### Metric kind và value type

Metric kind mô tả quan hệ giữa các phép đo liên tiếp:

| Metric kind | Ý nghĩa | Ví dụ |
|---|---|---|
| GAUGE | Giá trị tại một thời điểm | Số connection đang mở, queue depth, CPU utilization |
| DELTA | Mức thay đổi trong một khoảng thời gian | Số request phát sinh trong 1 phút |
| CUMULATIVE | Tổng tích lũy tăng dần từ một thời điểm bắt đầu | Tổng số byte đã gửi kể từ khi tiến trình bắt đầu |

Value type mô tả kiểu dữ liệu:

| Value type | Dữ liệu | Ví dụ |
|---|---|---|
| BOOL | Đúng/sai | Trạng thái bật/tắt |
| INT64 | Số nguyên 64 bit | Số request, số item trong queue |
| DOUBLE | Số thực | CPU utilization, latency |
| DISTRIBUTION | Phân bố nhiều giá trị | Histogram độ trễ request |
| STRING | Chuỗi trong một số metric tích hợp hoặc nguồn ngoài | Không được hỗ trợ cho custom metrics |

Hãy chọn kind theo ý nghĩa thực tế. Queue depth là GAUGE vì nó có thể tăng hoặc giảm tại mỗi lần lấy mẫu. Số request phát sinh trong một khoảng thường là DELTA. Tổng số request từ khi tiến trình bắt đầu là CUMULATIVE. Nếu dùng sai kind, các phép tính rate, delta hoặc tổng hợp trong biểu đồ có thể dẫn đến kết luận sai.

Lưu ý khi tự định nghĩa metric: mô hình Cloud Monitoring nói chung có GAUGE, DELTA và CUMULATIVE, nhưng không phải mọi tổ hợp kind/value type đều được phép cho custom metric. Với metric có tiền tố custom.googleapis.com, tổ hợp DELTA không được hỗ trợ; STRING cũng không được hỗ trợ cho custom metric. Ví dụ trong bài dùng GAUGE và INT64 nên phù hợp với cách ghi time series trực tiếp qua Monitoring API. Cumulative metric có thể cần được chuyển đổi bằng phép tổng hợp thích hợp trước khi dùng để vẽ biểu đồ hoặc tạo alert.

Với latency, không nên chỉ ghi một giá trị trung bình nếu cần biết tail latency. Distribution metric hoặc histogram giữ thông tin phân bố để có thể phân tích các percentile như P50, P95 và P99. Một giá trị trung bình thấp vẫn có thể che giấu một nhóm request rất chậm.

## 3. Resource labels và metric labels

Đây là hai nhóm label có vai trò khác nhau nhưng cùng tham gia xác định time series.

**Resource labels** mô tả nguồn phát sinh dữ liệu: project, location, VM, cluster, pod hoặc service. Tập label hợp lệ phụ thuộc monitored resource type.

**Metric labels** mô tả phép đo: method, response code, loại thao tác hoặc kết quả. Tập label hợp lệ được định nghĩa trong metric descriptor.

Ví dụ, metric đếm request của một Cloud Storage bucket có thể có metric labels **method** và **response_code**, trong khi monitored resource **gcs_bucket** có resource labels **project_id**, **bucket_name** và **location**. Nhờ đó, người vận hành có thể phân tích request theo method và response code, đồng thời xác định bucket và region tạo ra các request đó.

### Ví dụ resource type và resource labels

| Nguồn | Monitored resource type | Resource labels thường gặp |
|---|---|---|
| Compute Engine VM | gce_instance | project_id, instance_id, zone |
| GKE container | k8s_container | project_id, location, cluster_name, namespace_name, pod_name, container_name |
| Cloud Run revision | cloud_run_revision | project_id, location, service_name, revision_name, configuration_name |
| Cloud Storage bucket | gcs_bucket | project_id, bucket_name, location |

Danh sách label chính xác phụ thuộc descriptor của từng resource type và có thể thay đổi theo dịch vụ. Khi tạo filter hoặc custom metric, hãy tra descriptor tương ứng thay vì tự đặt tên label theo suy đoán.

### Resource metadata labels

Ngoài các label bắt buộc được định nghĩa bởi monitored resource type, Cloud Monitoring còn có resource metadata labels. Một số metadata do hệ thống cung cấp ở dạng chỉ đọc; một số tài nguyên cho phép người dùng gắn metadata labels khi cấu hình tài nguyên.

Metadata labels hữu ích để phân loại và lọc dữ liệu trong truy vấn. Tuy nhiên, chúng có thể được bổ sung không đồng bộ và không có cùng cam kết về độ trễ như label được định nghĩa trực tiếp trong monitored resource type hoặc metric descriptor. Vì vậy, không nên dựa vào metadata labels để kích hoạt alert nhạy cảm hoặc hành động tự động như autoscaling. Với điều kiện phản ứng cần độ tin cậy cao, hãy dùng label được định nghĩa chính thức của resource hoặc metric type.

## 4. Cardinality: vì sao thiết kế label rất quan trọng?

Cardinality là số tổ hợp giá trị label có thể tạo ra các time series riêng. Mỗi tổ hợp metric labels và resource labels có thể trở thành một time series. Khi số giá trị của label tăng nhanh, số time series và lượng dữ liệu cần lưu trữ, truy vấn cũng tăng.

Giả sử một metric có:

- 3 môi trường: dev, staging, production.
- 4 region.
- 5 loại kết quả.
- 2 phương thức thanh toán.

Số tổ hợp tối đa là:

\[
3 \times 4 \times 5 \times 2 = 120
\]

Nếu thêm customerId với hàng trăm nghìn giá trị, số time series có thể tăng đột biến. Thêm request ID, order ID hoặc session ID sẽ khiến mỗi sự kiện gần như tạo một chuỗi riêng.

### Nên và không nên dùng làm label

| Thuộc tính | Khuyến nghị | Lý do |
|---|---|---|
| environment | Nên | Tập giá trị nhỏ và ổn định |
| region | Nên | Số region hữu hạn |
| status_class | Nên | Ví dụ 2xx, 4xx, 5xx |
| payment_method | Có thể | Nếu tập phương thức được kiểm soát |
| route | Dùng route template | /orders/{orderId} có cardinality thấp hơn URL đầy đủ |
| customerId | Không nên | Số lượng giá trị lớn và thay đổi liên tục |
| orderId | Không nên | Mỗi đơn hàng có thể tạo một series mới |
| requestId hoặc traceId | Không nên | Giá trị gần như duy nhất cho từng request |
| URL có query string | Không nên | Có thể chứa dữ liệu động và nhạy cảm |
| timestamp hoặc nội dung lỗi tự do | Không nên | Tạo ra quá nhiều giá trị khác nhau |

Các định danh như customerId, orderId, requestId phù hợp hơn với logs hoặc traces, nơi có thể truy vấn theo từng sự kiện. Metrics nên giữ chiều phân loại có tập giá trị hữu hạn.

Cardinality không chỉ phụ thuộc số lượng label. Số giá trị có thể có của từng label và tổ hợp giữa chúng mới quyết định số time series. Hãy ước tính cardinality trước khi phát hành custom metric, sau đó theo dõi Metrics Management để tìm metric có lượng time series tăng bất thường.

## 5. Chọn metric có sẵn cho Cloud Run, GKE và Compute Engine

Trước khi tạo metric mới, hãy kiểm tra Metrics Explorer hoặc Metrics list để biết dịch vụ đã cung cấp phép đo phù hợp hay chưa.

Một số nhóm metric thường được dùng:

| Nền tảng | Metric cần theo dõi | Mục đích |
|---|---|---|
| Cloud Run | Request count | Đo lưu lượng request |
| Cloud Run | Request latency | Theo dõi thời gian xử lý và tail latency |
| Cloud Run | Instance count | Theo dõi số instance đang phục vụ |
| Cloud Run | Container CPU và memory utilization | Phát hiện giới hạn tài nguyên |
| Compute Engine | CPU utilization | Phát hiện VM quá tải hoặc nhàn rỗi |
| Compute Engine | Disk bytes và disk utilization | Theo dõi năng lực lưu trữ |
| GKE | Container CPU và memory | Theo dõi tài nguyên workload |
| GKE | Pod/container restart hoặc trạng thái | Phát hiện workload không ổn định |

Tên metric type, nhãn và đơn vị có thể khác nhau theo loại tài nguyên và phiên bản tích hợp. Khi viết filter, hãy chọn metric trong Metrics Explorer hoặc tra Metrics list để xác nhận tên chính xác và monitored resource tương ứng.

### Cách chọn metric theo mục tiêu

- Để biết lưu lượng tăng hay giảm, theo dõi request count hoặc throughput.
- Để biết người dùng có gặp lỗi không, theo dõi error count hoặc error ratio.
- Để biết service phản hồi chậm, theo dõi latency distribution và percentile.
- Để biết có thiếu tài nguyên không, theo dõi CPU, memory, disk và số instance.
- Để biết hệ thống xử lý công việc nền có kịp không, theo dõi queue depth, tuổi message lâu nhất và tốc độ xử lý.

Một metric riêng lẻ thường không đủ để kết luận. Ví dụ CPU cao có thể là do lưu lượng tăng bình thường hoặc do vòng lặp lỗi. Hãy kết hợp request count, latency, error rate và resource utilization để hiểu nguyên nhân.

## 6. Tạo custom metric cho ứng dụng Java

Custom metric dùng để đo dữ liệu ứng dụng mà metric có sẵn chưa thể hiện, chẳng hạn số đơn hàng tạo thành công, số công việc chờ xử lý hoặc thời gian một bước nghiệp vụ hoàn tất.

Google khuyến nghị dùng framework instrumentation mở và trung lập như **OpenTelemetry** cho ứng dụng mới. OpenTelemetry cung cấp API đo lường và cho phép chuyển dữ liệu qua exporter hoặc collector phù hợp. Nếu cần tích hợp trực tiếp với Cloud Monitoring API, Java client library cũng có thể ghi time series.

### Thiết kế metric trước khi viết code

Ví dụ cần đo số item đang chờ xử lý của worker:

| Thuộc tính | Lựa chọn |
|---|---|
| Metric type | custom.googleapis.com/orders/queue_depth |
| Ý nghĩa | Số item đang chờ tại thời điểm đo |
| Metric kind | GAUGE |
| Value type | INT64 |
| Unit | {item} |
| Metric labels | Không cần trong ví dụ cơ bản |
| Monitored resource | generic_task đại diện cho task của ứng dụng |

Queue depth có thể tăng hoặc giảm nên dùng GAUGE. Không dùng DELTA cho giá trị tồn tại hiện tại. Nếu cần đếm số đơn hàng mới trong mỗi khoảng thời gian, hãy thiết kế một counter phù hợp và xác định rõ cách chuyển counter thành rate.

### Bật API và quyền ghi metric

~~~bash
export PROJECT_ID="your-project-id"

gcloud config set project "$PROJECT_ID"
gcloud services enable monitoring.googleapis.com \
  --project="$PROJECT_ID"
~~~

Service account chạy ứng dụng cần quyền ghi metrics, thường là vai trò **roles/monitoring.metricWriter**. Cấp quyền cho đúng service account của workload. Khi chạy trên Google Cloud, dùng Application Default Credentials dựa trên danh tính runtime; không nhúng khóa service account JSON vào JAR hoặc container image.

### Thêm Java client library

Với Maven, thêm Cloud Monitoring client library. Dự án nên quản lý phiên bản bằng Google Cloud Libraries BOM để các thư viện Google Cloud tương thích với nhau.

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-monitoring</artifactId>
</dependency>
~~~

### Ghi một GAUGE time series

Ví dụ dưới đây ghi queue depth của một task. generic_task giúp mô tả nguồn phát metric bằng project, location, namespace, job và task ID. Task ID cần đại diện cho một nguồn ghi ổn định và duy nhất trong phạm vi thích hợp để tránh nhiều process ghi đè hoặc tạo điểm dữ liệu sai thứ tự cho cùng một time series.

~~~java
import com.google.api.Metric;
import com.google.api.MonitoredResource;
import com.google.cloud.monitoring.v3.MetricServiceClient;
import com.google.monitoring.v3.CreateTimeSeriesRequest;
import com.google.monitoring.v3.Point;
import com.google.monitoring.v3.ProjectName;
import com.google.monitoring.v3.TimeInterval;
import com.google.monitoring.v3.TimeSeries;
import com.google.monitoring.v3.TypedValue;
import com.google.protobuf.util.Timestamps;

import java.io.IOException;

public final class QueueDepthPublisher {
    private QueueDepthPublisher() {
    }

    public static void publish(
            String projectId,
            String taskId,
            long queueDepth) throws IOException {

        if (queueDepth < 0) {
            throw new IllegalArgumentException(
                    "queueDepth không thể âm");
        }

        TimeInterval interval = TimeInterval.newBuilder()
                .setEndTime(Timestamps.fromMillis(
                        System.currentTimeMillis()))
                .build();

        Point point = Point.newBuilder()
                .setInterval(interval)
                .setValue(TypedValue.newBuilder()
                        .setInt64Value(queueDepth))
                .build();

        Metric metric = Metric.newBuilder()
                .setType("custom.googleapis.com/orders/queue_depth")
                .build();

        MonitoredResource resource = MonitoredResource.newBuilder()
                .setType("generic_task")
                .putLabels("project_id", projectId)
                .putLabels("location", "asia-southeast1")
                .putLabels("namespace", "orders")
                .putLabels("job", "orders-api")
                .putLabels("task_id", taskId)
                .build();

        TimeSeries timeSeries = TimeSeries.newBuilder()
                .setMetric(metric)
                .setResource(resource)
                .addPoints(point)
                .build();

        CreateTimeSeriesRequest request =
                CreateTimeSeriesRequest.newBuilder()
                        .setName(ProjectName.of(projectId).toString())
                        .addTimeSeries(timeSeries)
                        .build();

        try (MetricServiceClient client =
                     MetricServiceClient.create()) {
            client.createTimeSeries(request);
        }
    }
}
~~~

Đây là ví dụ tối giản dựa trên Cloud Monitoring API. Ứng dụng cần có ADC và quyền roles/monitoring.metricWriter. Metric descriptor có thể được Cloud Monitoring tạo tự động từ dữ liệu lần ghi đầu tiên; với môi trường production, nên định nghĩa descriptor rõ ràng khi cần kiểm soát display name, description, unit, metric kind, value type và labels. Khi descriptor đã được tạo, không tùy tiện thay đổi ý nghĩa metric hoặc đổi kiểu dữ liệu.

Trong hệ thống có nhiều instance, hãy dùng monitored resource mô tả đúng nguồn ghi. global chỉ có label project_id và có thể gây va chạm hoặc ghi sai thứ tự nếu nhiều process cùng ghi một time series. generic_task, generic_node hoặc resource type cụ thể phù hợp hơn khi cần phân biệt các task hay node. Với GKE, Google Cloud Managed Service for Prometheus hoặc OpenTelemetry thường phù hợp hơn việc tự xây một đường ghi metric riêng cho từng container.

### Đọc và kiểm tra metric

Sau khi gửi data point, mở Metrics Explorer trong Cloud Monitoring:

1. Chọn metric custom.googleapis.com/orders/queue_depth.
2. Chọn monitored resource generic_task.
3. Lọc theo resource.label.namespace, resource.label.job hoặc resource.label.task_id.
4. Kiểm tra giá trị queue depth theo thời gian.
5. Nếu không thấy dữ liệu, kiểm tra project, Monitoring API, quyền metric writer, resource labels bắt buộc và timestamp của point.

Data point không xuất hiện tức thì trong mọi biểu đồ. Hãy kiểm tra khoảng thời gian truy vấn, độ trễ ingestion và filter trước khi kết luận việc ghi metric thất bại.

## 7. Truy vấn và tổng hợp metrics trong Metrics Explorer

Metrics Explorer cho phép chọn metric type, monitored resource, bộ lọc và cách hiển thị. Một truy vấn thường gồm:

- Metric type: xác định phép đo.
- Resource type: xác định nguồn phát sinh.
- Metric labels: lọc hoặc nhóm theo thuộc tính của phép đo.
- Resource labels: lọc hoặc nhóm theo thuộc tính của tài nguyên.
- Time range: khoảng thời gian cần phân tích.
- Alignment và aggregation: cách chuẩn hóa data point và tổng hợp nhiều time series.

Ví dụ filter cho request count của Cloud Run service:

~~~text
metric.type = "run.googleapis.com/request_count"
AND resource.type = "cloud_run_revision"
AND resource.label.service_name = "orders-api"
~~~

Để phân tích một metric custom:

~~~text
metric.type = "custom.googleapis.com/orders/queue_depth"
AND resource.type = "generic_task"
AND resource.label.namespace = "orders"
~~~

Tên metric và label phải khớp với descriptor thực tế. Nếu không chắc, hãy chọn metric và label từ giao diện Metrics Explorer thay vì gõ tên đoán.

### Alignment và cross-series aggregation

Khi truy vấn time series, Cloud Monitoring có thể chia dữ liệu thành các khoảng thời gian và tính một giá trị đại diện cho mỗi khoảng. Quá trình này gọi là alignment. Ví dụ, dữ liệu thô mỗi 10 giây có thể được căn chỉnh thành trung bình hoặc giá trị lớn nhất trong mỗi phút.

Cross-series aggregation kết hợp nhiều time series thành một hoặc nhiều chuỗi kết quả. Ví dụ, có thể tính tổng request của tất cả instance, hoặc tính CPU trung bình theo zone.

| Thao tác | Câu hỏi phù hợp |
|---|---|
| Align mean | Giá trị trung bình trong mỗi khoảng là bao nhiêu? |
| Align max | Đỉnh cao nhất trong mỗi khoảng là bao nhiêu? |
| Align rate | Tốc độ tăng của counter theo đơn vị thời gian là bao nhiêu? |
| Align delta | Giá trị thay đổi trong mỗi khoảng là bao nhiêu? |
| Reduce sum | Tổng lưu lượng của tất cả instance là bao nhiêu? |
| Reduce mean | Mức trung bình giữa các instance là bao nhiêu? |
| Group by resource label | Region, zone hoặc service nào có giá trị cao? |

Hãy chọn alignment phù hợp với metric kind. Counter tích lũy thường cần chuyển thành rate hoặc delta trước khi so sánh theo thời gian. Gauge như queue depth thường dùng mean hoặc max tùy mục tiêu. Với latency distribution, chọn cách hiển thị percentile phù hợp thay vì lấy trung bình rồi coi đó là tail latency.

## 8. Xây dựng dashboard trong Cloud Monitoring

Dashboard tập hợp những biểu đồ và thông tin cần thiết vào một màn hình để đội vận hành theo dõi hệ thống. Cloud Monitoring cung cấp dashboard dựng sẵn cho nhiều dịch vụ Google Cloud và cho phép tạo custom dashboard để kết hợp metrics, logs, traces, alert và SLO.

Một dashboard nên trả lời các câu hỏi cụ thể:

- Service có đang nhận request không?
- Error rate và latency có vượt mức bình thường không?
- CPU, memory hoặc số instance có dấu hiệu thiếu năng lực không?
- Queue có tăng liên tục hoặc xử lý chậm không?
- Sự cố bắt đầu ở service, region hay revision nào?

### Các loại widget thường dùng

| Widget | Khi nào dùng |
|---|---|
| Line chart | Quan sát metric thay đổi theo thời gian |
| Stacked area chart | So sánh đóng góp của nhiều nhóm vào tổng |
| Heatmap | Quan sát phân bố giá trị, ví dụ latency distribution |
| Scorecard hoặc indicator | Hiển thị một giá trị tổng hợp và so với ngưỡng |
| Table | So sánh nhiều service, instance hoặc region |
| Alert chart/list | Theo dõi trạng thái alert policy và incident |
| Logs panel | Xem log liên quan ngay trên dashboard |
| Text | Ghi chú, hướng dẫn hoặc định nghĩa ngưỡng vận hành |

Không cần đưa tất cả widget vào một dashboard. Mỗi biểu đồ nên có tiêu đề mô tả metric, đơn vị, phạm vi tài nguyên và cách tổng hợp.

### Tạo dashboard qua Google Cloud Console

1. Mở Google Cloud Console và chọn project hoặc metrics scope phù hợp.
2. Vào **Monitoring → Dashboards**.
3. Chọn **Create custom dashboard**.
4. Đặt tên phản ánh service hoặc mục đích, ví dụ **Orders API - Service Health**.
5. Chọn **Add widget**, sau đó thêm chart, scorecard, table hoặc widget cần thiết.
6. Với mỗi metric widget, chọn metric type, resource type, filter, alignment, aggregation và cách hiển thị.
7. Thêm dashboard-wide filter hoặc variable nếu dashboard cần dùng cho nhiều service, region hoặc environment.
8. Sắp xếp widget theo thứ tự ưu tiên, nhóm thành section nếu dashboard có nhiều nội dung.
9. Lưu dashboard và chia sẻ quyền truy cập phù hợp qua IAM.

Dashboard dựng sẵn của Google Cloud giúp bắt đầu nhanh với metrics tiêu chuẩn. Custom dashboard phù hợp khi cần xem nhiều service cùng nhau hoặc theo dõi chỉ số nghiệp vụ. Một số dashboard service-specific được hệ thống tạo tự động và không thể sửa trực tiếp; có thể sao chép chart phù hợp sang custom dashboard.

### Bố cục dashboard cho Orders API

~~~text
┌──────────────────────────────────────────────────────────────────┐
│ ORDERS API — SERVICE HEALTH                                      │
├────────────────────────┬────────────────────────┬────────────────┤
│ Request rate           │ Error ratio            │ P95 latency    │
│ requests / second      │ percent                │ milliseconds   │
├────────────────────────┴────────────────────────┴────────────────┤
│ Request count and errors over time                               │
│                                                                  │
├─────────────────────────────────┬────────────────────────────────┤
│ CPU / memory / instance count   │ Queue depth / processing rate  │
│ grouped by revision             │ grouped by worker               │
├─────────────────────────────────┴────────────────────────────────┤
│ Active alerts, recent incidents and related logs                 │
└──────────────────────────────────────────────────────────────────┘
~~~

Thứ tự này đặt trải nghiệm request ở đầu dashboard, tài nguyên và worker ở giữa, còn cảnh báo và log hỗ trợ điều tra ở cuối. Người vận hành có thể nhìn thấy vấn đề trước rồi mới đi sâu vào nguyên nhân.

### Dashboard-wide filters và variables

Dashboard-wide filter giúp lọc nhiều widget cùng lúc, chẳng hạn chỉ xem một region hoặc environment. Variables có thể điều khiển truy vấn của các widget được chọn. Với dashboard dùng chung cho nhiều service, có thể tạo variable service để người trực vận hành chuyển ngữ cảnh mà không phải sửa từng biểu đồ.

Hãy kiểm tra mọi widget có hỗ trợ filter hoặc variable hay không. Một số widget có truy vấn hoặc nguồn dữ liệu riêng và có thể không phản ứng với tất cả filter chung.

### Giữ dashboard dễ đọc và tải nhanh

- Chỉ hiển thị những metric hỗ trợ quyết định vận hành.
- Dùng filter để giới hạn service, region, zone hoặc namespace.
- Giảm số time series trên một chart bằng cách group hoặc aggregate phù hợp.
- Không tạo một chart riêng cho từng request hoặc từng người dùng.
- Chọn time range mặc định phù hợp với ca trực và mục tiêu quan sát.
- Đặt tiêu đề, đơn vị và chú giải rõ ràng; không buộc người xem đoán màu hoặc trục.
- Chia dashboard lớn thành section hoặc nhiều dashboard theo service và vai trò.

Hiệu năng dashboard phụ thuộc số lượng chart và số time series mà mỗi chart phải tải. Dashboard càng nhiều series càng có thể tải chậm hoặc khó đọc. Hãy lọc và tổng hợp trước khi thêm widget.

## 9. Từ dashboard đến alert policy

Dashboard giúp người vận hành chủ động quan sát. Alert policy giúp hệ thống phát hiện điều kiện cần hành động và thông báo cho người phụ trách.

Ví dụ, dashboard cho thấy P95 latency tăng trong 15 phút. Alert policy có thể kiểm tra điều kiện latency vượt ngưỡng liên tục trong một khoảng thời gian và gửi thông báo đến notification channel.

Khi thiết kế alert:

1. Chọn metric đại diện đúng cho tác động người dùng hoặc rủi ro vận hành.
2. Xác định resource và filter để alert chỉ áp dụng cho service cần theo dõi.
3. Chọn alignment period và aggregation phù hợp với metric kind.
4. Đặt threshold dựa trên baseline, SLO hoặc yêu cầu nghiệp vụ.
5. Chọn thời gian duy trì điều kiện để giảm cảnh báo do dao động ngắn.
6. Cấu hình notification channel và hướng dẫn xử lý incident.
7. Kiểm thử bằng dữ liệu thử nghiệm hoặc tình huống mô phỏng.

Không tạo alert chỉ vì một metric thay đổi. Alert nên biểu thị tình huống cần hành động, chẳng hạn error ratio vượt ngân sách lỗi hoặc queue age tăng đến mức đe dọa SLA. Với tín hiệu quan trọng, ưu tiên metric labels và resource labels được định nghĩa chính thức; tránh dựa vào resource metadata labels có thể được cập nhật không đồng bộ.

## 10. IAM và quyền truy cập Cloud Monitoring

Quyền cần thiết phụ thuộc vai trò của người hoặc workload:

- Workload ghi custom metrics cần quyền ghi, thường là **roles/monitoring.metricWriter**.
- Người xem dashboard và metrics cần quyền đọc phù hợp, thường là **roles/monitoring.viewer**.
- Người tạo hoặc chỉnh sửa dashboard, alert policy và cấu hình Monitoring cần quyền quản lý tương ứng; cấp theo nhiệm vụ thực tế.

Không cấp quyền quản trị Monitoring cho mọi service account chỉ vì ứng dụng cần gửi metric. Tách danh tính ghi metrics khỏi danh tính quản lý dashboard. Với môi trường nhiều project, xác định metrics scope để người vận hành có thể xem dữ liệu từ các project được phép mà vẫn giữ ranh giới quyền truy cập.

## 11. Chi phí và quản lý metric usage

Metrics có chi phí theo loại dữ liệu, khối lượng ingest và cách sử dụng. User-defined metrics là tính năng tính phí. Cardinality cao có thể làm tăng số time series và lượng dữ liệu được ghi nhận. Một metric có nhiều label giá trị duy nhất có thể tốn kém hơn dự kiến dù số metric type không nhiều.

Các biện pháp kiểm soát:

- Tái sử dụng metric có sẵn khi phù hợp.
- Thiết kế label có cardinality hữu hạn và loại bỏ chiều không cần thiết.
- Không tạo metric mới cho mỗi khách hàng, đơn hàng, request hoặc session.
- Chỉ thu thập tần suất đủ để đáp ứng mục tiêu vận hành.
- Theo dõi Metrics Management để xem ingestion, sample, số time series, metric usage và metric không được sử dụng.
- Xem xét custom metric nào đang được dashboard hoặc alert policy tham chiếu trước khi loại bỏ.
- Ước tính chi phí trước khi triển khai metric ở quy mô lớn.

Không giảm tần suất hoặc loại bỏ metric quan trọng một cách máy móc để tiết kiệm chi phí. Hãy xác định tín hiệu nào cần cho SLO, alert, điều tra và capacity planning, rồi tối ưu những chiều dữ liệu không đem lại giá trị tương ứng.

## 12. Bài tập thực hành: dashboard sức khỏe Orders API

Giả sử hệ thống có một Cloud Run service **orders-api** và một worker chạy trên GKE. Nhóm vận hành muốn theo dõi request, lỗi, độ trễ và tình trạng xử lý hàng đợi.

Hãy thực hiện trong project thử nghiệm:

1. Mở Metrics Explorer và tìm metric request count, request latency và instance count của Cloud Run.
2. Xác nhận monitored resource type và resource labels của **cloud_run_revision**.
3. Tạo filter chỉ lấy service **orders-api**; so sánh dữ liệu theo revision hoặc location.
4. Tạo custom metric **custom.googleapis.com/orders/queue_depth** cho queue depth, dùng GAUGE và monitored resource phù hợp với worker task.
5. Dùng metric labels hoặc resource labels có tập giá trị nhỏ, chẳng hạn environment và region; không đưa orderId hoặc requestId vào metric labels.
6. Tạo custom dashboard **Orders API - Service Health**.
7. Thêm widget cho request rate, error ratio, P95 latency, CPU/memory, instance count và queue depth.
8. Thêm filter để chuyển giữa region hoặc environment nếu các widget hỗ trợ.
9. Tạo alert policy thử nghiệm khi error ratio hoặc queue depth vượt ngưỡng đã chọn.
10. Tạo lưu lượng và mô phỏng worker xử lý chậm; kiểm tra dashboard phản ánh đúng thay đổi và alert được kích hoạt.
11. Kiểm tra Metrics Management để đánh giá cardinality và lượng metric được ingest.

Kết quả mong đợi là dashboard cho thấy tình trạng tổng thể của API và worker, đồng thời cho phép chuyển từ chỉ số tổng hợp sang resource hoặc revision cụ thể khi điều tra.

## 13. Checklist trước khi phát hành metrics và dashboard

- [ ] Đã kiểm tra metric có sẵn trước khi tạo custom metric.
- [ ] Metric descriptor có tên, mô tả, unit, kind và value type đúng ý nghĩa.
- [ ] Monitored resource type phản ánh đúng nguồn phát dữ liệu.
- [ ] Resource labels và metric labels được phân biệt rõ.
- [ ] Không dùng ID duy nhất hoặc URL động làm metric label.
- [ ] Cardinality được ước tính và theo dõi sau triển khai.
- [ ] Gauge, delta và cumulative được chọn đúng với cách đo.
- [ ] Alignment, aggregation và percentile phù hợp với loại metric.
- [ ] Dashboard có mục tiêu rõ, widget có tiêu đề và đơn vị.
- [ ] Dashboard filter và variable hoạt động đúng trên các widget.
- [ ] Alert policy có ngưỡng, thời gian đánh giá và hướng dẫn xử lý.
- [ ] Service account chỉ có quyền Monitoring cần thiết.
- [ ] Metric ingestion và chi phí được theo dõi định kỳ.

## Câu hỏi tự kiểm tra

**1. Một time series trong Cloud Monitoring được xác định bởi những thành phần nào?**

Nó gắn metric type và các giá trị metric labels với một monitored resource cụ thể cùng các giá trị resource labels, rồi lưu các data point theo thời gian.

**2. Resource labels khác metric labels ở điểm nào?**

Resource labels mô tả nguồn phát sinh dữ liệu, ví dụ VM, pod hoặc service. Metric labels mô tả chiều phân loại của phép đo, ví dụ method hoặc response code.

**3. Vì sao queue depth thường là GAUGE?**

Vì nó biểu diễn số item đang chờ tại một thời điểm và có thể tăng hoặc giảm giữa các lần đo.

**4. Vì sao không nên đưa orderId vào metric labels?**

Vì mỗi orderId có thể tạo một time series riêng, làm cardinality tăng nhanh. orderId phù hợp hơn với logs hoặc traces.

**5. Dashboard khác alert policy như thế nào?**

Dashboard trực quan hóa metrics để người vận hành quan sát. Alert policy đánh giá điều kiện theo thời gian và gửi thông báo khi cần hành động.

**6. Khi nào nên dùng custom metric?**

Khi cần đo dữ liệu nghiệp vụ hoặc kỹ thuật riêng mà metrics có sẵn chưa cung cấp, chẳng hạn queue depth hoặc số đơn hàng được xử lý.

## Tài liệu tham khảo

- [Metrics, time series và resources](https://docs.cloud.google.com/monitoring/api/v3/metrics)
- [Components of the metric model: labels và cardinality](https://docs.cloud.google.com/monitoring/api/v3/metric-model)
- [Structure of time series](https://docs.cloud.google.com/monitoring/api/v3/metrics-details)
- [Value types and metric kinds](https://docs.cloud.google.com/monitoring/api/v3/kinds-and-types)
- [Monitored resource types](https://docs.cloud.google.com/monitoring/api/resources)
- [User-defined metrics overview](https://docs.cloud.google.com/monitoring/custom-metrics)
- [Create user-defined metrics with the API](https://docs.cloud.google.com/monitoring/custom-metrics/creating-metrics)
- [Java client library sample: write time series](https://docs.cloud.google.com/monitoring/docs/samples/monitoring-quickstart)
- [Dashboards overview](https://docs.cloud.google.com/monitoring/dashboards)
- [Create and manage custom dashboards](https://docs.cloud.google.com/monitoring/charts/dashboards)
- [Cloud Monitoring quotas and limits](https://docs.cloud.google.com/monitoring/quotas)

## Kết luận

Cloud Monitoring biến phép đo của hạ tầng và ứng dụng thành time series có thể truy vấn và trực quan hóa. Metric type định nghĩa ý nghĩa phép đo; monitored resource cùng resource labels xác định nguồn; metric labels bổ sung các chiều phân tích. Thiết kế label hợp lý giúp kiểm soát cardinality và chi phí. Metrics Explorer hỗ trợ lọc, alignment và aggregation, còn dashboard đưa các tín hiệu quan trọng vào một màn hình để đội vận hành theo dõi. Khi kết hợp metric có sẵn, custom metrics, dashboard và alert policy, nhóm phát triển có thể theo dõi sức khỏe dịch vụ và phát hiện vấn đề trước khi ảnh hưởng lan rộng.
