# Cloud Logging, log entries và structured logging

Khi một ứng dụng Java chạy trên Google Cloud, log là một trong những nguồn dữ liệu đầu tiên giúp đội vận hành hiểu điều gì đã xảy ra trong một request, một lần triển khai hoặc một tác vụ nền. Tuy nhiên, log chỉ hữu ích khi có cấu trúc nhất quán, xác định được nguồn phát sinh và giữ lại đủ ngữ cảnh để tìm kiếm. Một dòng chữ tự do như “Có lỗi xảy ra” khó giúp điều tra; một log entry có severity, tên sự kiện, mã đơn hàng, service và trace có thể dẫn người vận hành đến đúng request trong vài thao tác.

Bài học thuộc module **CLOUD_PROVIDERS_GCP**. Module khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu. Người học thực hành lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Trong phạm vi bài này, chúng ta tập trung vào Cloud Logging, cấu trúc của một log entry và cách phát ra structured logs từ ứng dụng Java để hỗ trợ tìm kiếm, phân tích và cảnh báo.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích Cloud Logging thu thập, lưu trữ và định tuyến log như thế nào.
- Nhận diện các thành phần quan trọng của một LogEntry.
- Phân biệt text log, structured log và audit log.
- Thiết kế JSON log có severity, event name và ngữ cảnh nghiệp vụ rõ ràng.
- Phát structured log từ ứng dụng Java và liên kết log với trace.
- Truy vấn log trong Logs Explorer và sử dụng log cho giám sát vận hành.
- Kiểm soát dữ liệu nhạy cảm, quyền truy cập và chi phí lưu trữ log.

## 1. Cloud Logging giải quyết vấn đề gì?

Cloud Logging là dịch vụ quản lý log của Google Cloud. Dịch vụ tiếp nhận log từ ứng dụng, tài nguyên hạ tầng và nhiều dịch vụ Google Cloud; cung cấp khả năng tìm kiếm, truy vấn, xem log theo thời gian và định tuyến log đến nơi lưu trữ hoặc xử lý khác.

Một ứng dụng có thể chạy trên nhiều môi trường:

- **Cloud Run:** log ghi ra stdout và stderr của container được nền tảng thu thập.
- **Google Kubernetes Engine (GKE):** log container và log hệ thống được thu thập theo cấu hình logging của cluster.
- **Compute Engine:** có thể cài Ops Agent để thu thập log ứng dụng, log hệ điều hành và dữ liệu giám sát từ máy ảo.
- **Dịch vụ Google Cloud:** nhiều dịch vụ tự tạo log nền tảng và audit log trong Cloud Logging.

Cloud Logging tập trung các nguồn này trong một giao diện chung. Người vận hành có thể lọc theo project, loại tài nguyên, tên service, mức độ nghiêm trọng, thời gian hoặc trường dữ liệu trong payload. Điều đó giúp điều tra một sự cố xuyên qua nhiều thành phần mà không phải đăng nhập vào từng máy chủ để đọc tệp log riêng.

### Luồng log tổng quát

~~~mermaid
flowchart TD
    A["Ứng dụng Java và dịch vụ Google Cloud"]
    B["stdout / stderr / agent / API"]
    C["Cloud Logging"]
    D["Log Router"]
    E["Log buckets và Logs Explorer"]
    F["BigQuery / Pub/Sub / Cloud Storage"]
    G["Log-based metrics và cảnh báo"]
    A --> B --> C --> D
    D --> E
    D --> F
    E --> G
~~~

Ứng dụng tạo sự kiện log; runtime hoặc agent chuyển sự kiện đến Cloud Logging; Log Router áp dụng cấu hình định tuyến và bộ lọc để quyết định nơi lưu hoặc chuyển tiếp. Logs Explorer dùng để tìm và phân tích log đã được lưu. Log-based metrics có thể chuyển mẫu log thành chuỗi thời gian để theo dõi và tạo cảnh báo.

Không phải mọi log đều đến từ ứng dụng. Ví dụ, audit log ghi lại hoạt động quản trị hoặc truy cập tài nguyên, còn application log mô tả sự kiện nghiệp vụ và kỹ thuật do ứng dụng phát ra. Phân biệt nguồn log giúp điều tra đúng câu hỏi.

## 2. Log entry là đơn vị dữ liệu cơ bản

Cloud Logging biểu diễn mỗi sự kiện dưới dạng một **LogEntry**. Một log entry có phần metadata mô tả nguồn, thời gian và mức độ nghiêm trọng, cùng một payload chứa nội dung sự kiện.

Các trường thường gặp:

| Trường | Ý nghĩa | Ví dụ hoặc lưu ý |
|---|---|---|
| logName | Tên log trong project | projects/PROJECT_ID/logs/stdout |
| resource | Tài nguyên tạo ra log | cloud_run_revision, k8s_container, gce_instance |
| timestamp | Thời điểm sự kiện xảy ra | Nên phản ánh thời điểm phát sinh log |
| receiveTimestamp | Thời điểm Cloud Logging nhận log | Do hệ thống tiếp nhận ghi nhận |
| severity | Mức độ nghiêm trọng | INFO, WARNING, ERROR |
| insertId | Định danh entry trong một log | Hỗ trợ nhận diện entry trùng lặp |
| labels | Các nhãn metadata | Dùng cho thuộc tính có số lượng giá trị giới hạn |
| trace | Trace ID liên kết với Cloud Trace | Có dạng projects/PROJECT_ID/traces/TRACE_ID |
| spanId | Span liên quan trong trace | Hỗ trợ đi từ log đến span |
| httpRequest | Thông tin request HTTP | Method, URL, status, latency và kích thước |
| operation | Thông tin về một thao tác gồm nhiều log | Có thể nhóm các bước của cùng một operation |
| sourceLocation | Vị trí nguồn phát log | File, dòng và hàm nếu được cung cấp |
| jsonPayload | Payload dạng JSON có cấu trúc | Phù hợp với application log |
| textPayload | Payload dạng văn bản | Thường gặp với log dòng chữ thuần |
| protoPayload | Payload dạng protocol buffer | Thường dùng cho audit log |

Một LogEntry có một dạng payload tương ứng; ứng dụng không cần tự tạo cả jsonPayload, textPayload và protoPayload cho cùng một entry. Với structured logging, ứng dụng phát JSON để Cloud Logging có thể phân tích thành các trường. Với log văn bản thông thường, nội dung thường nằm trong textPayload.

### Metadata khác payload như thế nào?

Metadata trả lời các câu hỏi “log đến từ đâu?”, “xảy ra khi nào?” và “nghiêm trọng đến mức nào?”. Payload trả lời “sự kiện gì đã xảy ra?” và mang theo ngữ cảnh nghiệp vụ.

Ví dụ, một log entry của Cloud Run có thể có resource là cloud_run_revision, severity là ERROR và timestamp là thời điểm request thất bại. Payload JSON có thể chứa event là payment.authorization_failed, orderId và mã lỗi của cổng thanh toán. Nhờ tách biệt hai lớp dữ liệu, người vận hành có thể lọc tất cả lỗi của một revision trước, rồi mới tìm các lỗi thuộc một loại nghiệp vụ.

### Monitored resource

Trường resource mô tả tài nguyên được giám sát đã phát ra log. Resource type quyết định bộ nhãn resource có thể có. Một số ví dụ:

| Môi trường | Resource type thường gặp | Nhãn có thể dùng để lọc |
|---|---|---|
| Cloud Run | cloud_run_revision | project_id, service_name, revision_name, location |
| GKE | k8s_container | project_id, location, cluster_name, namespace_name, pod_name, container_name |
| Compute Engine | gce_instance | project_id, instance_id, zone |

Khi log được thu thập qua tích hợp của nền tảng, thông tin resource thường được gắn tự động. Vì vậy, ứng dụng không cần chèn tên pod hoặc revision vào mọi dòng log chỉ để nhận diện nguồn. Nếu ứng dụng chạy ngoài môi trường có tích hợp, cần chọn cách gửi log và khai báo resource phù hợp để Cloud Logging phân loại đúng.

## 3. Severity và cách chọn mức độ log

Severity cho biết mức độ quan trọng của một sự kiện. Cloud Logging hỗ trợ các mức từ DEFAULT, DEBUG, INFO, NOTICE, WARNING, ERROR, CRITICAL, ALERT đến EMERGENCY.

| Severity | Dùng khi | Ví dụ |
|---|---|---|
| DEBUG | Thông tin chi tiết phục vụ gỡ lỗi | Giá trị trạng thái nội bộ đã được loại bỏ dữ liệu nhạy cảm |
| INFO | Hoạt động bình thường đáng ghi nhận | Đơn hàng được tiếp nhận |
| NOTICE | Sự kiện bình thường nhưng cần chú ý | Tác vụ bảo trì đã chuyển sang chế độ dự phòng |
| WARNING | Bất thường có thể phục hồi hoặc chưa gây lỗi trực tiếp | Một lần gọi phụ thuộc bị retry |
| ERROR | Một thao tác thất bại và cần điều tra | Không thể ghi đơn hàng vào cơ sở dữ liệu |
| CRITICAL | Lỗi nghiêm trọng ảnh hưởng lớn đến chức năng | Thành phần cốt lõi ngừng phục vụ |
| ALERT | Cần hành động khẩn cấp | Cơ chế bảo vệ chính không còn hoạt động |
| EMERGENCY | Hệ thống hoặc dịch vụ không thể tiếp tục hoạt động | Sự cố diện rộng cần xử lý ngay |

Hãy thống nhất cách dùng severity trong toàn bộ ứng dụng. Không ghi mọi sự kiện thành ERROR chỉ để làm nổi bật log; cách làm đó khiến dashboard và cảnh báo mất ý nghĩa. Một request bị từ chối do người dùng nhập dữ liệu không hợp lệ có thể là WARNING hoặc INFO tùy quy ước, trong khi lỗi kết nối cơ sở dữ liệu khiến request không hoàn thành thường là ERROR.

Severity cũng không thay thế trạng thái nghiệp vụ. Một khoản thanh toán bị từ chối theo quy tắc của ngân hàng có thể là kết quả nghiệp vụ bình thường, dù ứng dụng cần ghi rõ event payment.declined. Hãy chọn severity theo tác động vận hành và ghi event name để thể hiện ý nghĩa nghiệp vụ.

## 4. Text logging và structured logging

### Text logging

Ví dụ log văn bản:

~~~text
2026-11-19 09:42:18 ERROR PaymentService - Không thể xác nhận thanh toán cho đơn hàng ord-1042
~~~

Log này đọc được bằng mắt, nhưng máy khó tách chính xác event, order ID, mã lỗi và các trường khác. Nếu cần tìm mọi lỗi thanh toán của một đơn hàng, người vận hành có thể phải dựa vào chuỗi văn bản và biểu thức tìm kiếm dễ vỡ.

### Structured logging

Cùng sự kiện có thể được biểu diễn thành JSON:

~~~json
{
  "severity": "ERROR",
  "message": "Không thể xác nhận thanh toán",
  "event": "payment.authorization_failed",
  "orderId": "ord-1042",
  "paymentProvider": "example-payments",
  "errorCode": "UPSTREAM_TIMEOUT",
  "retryable": true
}
~~~

Mỗi thuộc tính có một tên và kiểu dữ liệu rõ ràng. Cloud Logging có thể lưu phần thuộc tính tùy chỉnh trong jsonPayload; người vận hành có thể lọc theo event, orderId, paymentProvider hoặc retryable mà không phải phân tích câu văn.

Structured logging không chỉ là “in JSON”. Để dữ liệu có thể sử dụng lâu dài, cần giữ schema ổn định, tên trường nhất quán, kiểu dữ liệu đúng và mỗi sự kiện nằm trên một dòng JSON hợp lệ. Không thay tên orderId thành order_id ở một service khác nếu không có lý do và quy ước chung.

### Các trường đặc biệt trong JSON log

Khi Cloud Logging nhận structured log từ các môi trường hỗ trợ nhận diện JSON, một số trường đặc biệt được ánh xạ thành metadata của LogEntry thay vì giữ nguyên như thuộc tính payload thông thường.

| Trường JSON | Tác dụng |
|---|---|
| severity | Đặt severity của log entry |
| message | Nội dung tóm tắt dễ đọc trong giao diện log |
| logging.googleapis.com/trace | Liên kết entry với trace |
| logging.googleapis.com/spanId | Liên kết entry với span trong trace |
| logging.googleapis.com/trace_sampled | Cho biết trace đã được lấy mẫu |
| logging.googleapis.com/labels | Gắn labels cho log entry |
| logging.googleapis.com/sourceLocation | Cung cấp vị trí source code |

Các trường đặc biệt cần đúng tên và đúng định dạng. Ví dụ trace phải là tên tài nguyên trace đầy đủ, gồm project ID và trace ID. Nếu chỉ ghi một chuỗi trace ID vào một thuộc tính tùy chỉnh, Cloud Logging không nhất thiết tự liên kết entry với Cloud Trace.

## 5. Phát structured log từ ứng dụng Java

Có nhiều cách đưa log Java vào Cloud Logging. Với Cloud Run, cách đơn giản và thường phù hợp là ghi JSON ra stdout; nền tảng thu thập log container và phân tích các trường JSON được hỗ trợ. Với GKE, cấu hình thu thập log của cluster cần được bật và hoạt động đúng. Với Compute Engine, có thể dùng Ops Agent để thu thập tệp log hoặc dữ liệu từ ứng dụng.

Ứng dụng cũng có thể gửi log trực tiếp bằng Cloud Logging API hoặc thư viện Google Cloud Logging. Cách gửi trực tiếp hữu ích trong một số kiến trúc, nhưng cần quản lý client, batching, retry và quyền IAM. Chọn một đường thu thập phù hợp cho mỗi luồng log để tránh ghi trùng cùng một sự kiện qua cả stdout và API.

### Bước 1: Thêm thư viện JSON

Ví dụ dưới đây dùng Jackson để tuần tự hóa dữ liệu thành JSON. Dự án có thể quản lý phiên bản Jackson qua BOM hoặc cơ chế dependency management đang sử dụng.

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
</dependency>
~~~

### Bước 2: Tạo bộ ghi log có cấu trúc

Lớp sau minh họa cách tạo một JSON object cho mỗi sự kiện rồi ghi một dòng ra stdout. Ứng dụng không ghép chuỗi JSON thủ công, vì vậy các ký tự đặc biệt trong dữ liệu được serializer escape đúng cách.

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

public final class StructuredLog {
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private StructuredLog() {
    }

    public static void orderAccepted(
            String orderId,
            String traceId,
            String spanId,
            boolean traceSampled) {

        ObjectNode entry = MAPPER.createObjectNode();
        entry.put("severity", "INFO");
        entry.put("message", "Đơn hàng đã được tiếp nhận");
        entry.put("event", "order.accepted");
        entry.put("orderId", orderId);

        addTraceContext(entry, traceId, spanId, traceSampled);
        write(entry);
    }

    public static void paymentFailed(
            String orderId,
            String errorCode,
            boolean retryable) {

        ObjectNode entry = MAPPER.createObjectNode();
        entry.put("severity", "ERROR");
        entry.put("message", "Không thể xác nhận thanh toán");
        entry.put("event", "payment.authorization_failed");
        entry.put("orderId", orderId);
        entry.put("errorCode", errorCode);
        entry.put("retryable", retryable);
        write(entry);
    }

    private static void addTraceContext(
            ObjectNode entry,
            String traceId,
            String spanId,
            boolean traceSampled) {

        String projectId = System.getenv("GOOGLE_CLOUD_PROJECT");
        if (projectId == null || projectId.isBlank()
                || traceId == null || traceId.isBlank()) {
            return;
        }

        entry.put(
                "logging.googleapis.com/trace",
                "projects/" + projectId + "/traces/" + traceId);

        if (spanId != null && !spanId.isBlank()) {
            entry.put("logging.googleapis.com/spanId", spanId);
        }

        entry.put(
                "logging.googleapis.com/trace_sampled",
                traceSampled);
    }

    private static void write(ObjectNode entry) {
        try {
            System.out.println(MAPPER.writeValueAsString(entry));
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException(
                    "Không thể tuần tự hóa structured log", exception);
        }
    }
}
~~~

Trong ví dụ, orderId và errorCode là thuộc tính tùy chỉnh nằm trong jsonPayload. severity và message được Cloud Logging nhận diện. Hàm addTraceContext chỉ ghi trường trace khi có project ID và trace ID; trong ứng dụng thực tế, hãy lấy trace ID và span ID từ thư viện tracing đang dùng, không tự sinh ID ngẫu nhiên cho mỗi dòng log.

Trace ID và span ID phải theo định dạng mà hệ thống tracing sử dụng. Với Cloud Trace, trace ID thường có 32 ký tự hexadecimal và span ID có 16 ký tự hexadecimal. Giá trị trace được ghi vào trường đặc biệt cần bao gồm tên tài nguyên đầy đủ như projects/my-project/traces/TRACE_ID.

### Bước 3: Gọi logger tại điểm có ý nghĩa

~~~java
public final class OrderService {
    public Order createOrder(CreateOrderCommand command) {
        Order order = repository.save(Order.from(command));

        // Các giá trị định danh được ghi cùng sự kiện.
        // Không ghi token, mật khẩu hoặc toàn bộ nội dung thanh toán.
        StructuredLog.orderAccepted(
                order.getId(),
                tracing.currentTraceId(),
                tracing.currentSpanId(),
                tracing.isCurrentTraceSampled());

        return order;
    }
}
~~~

Đoạn code trên giả định ứng dụng có một thành phần tracing cung cấp trace ID và span ID của request hiện tại. Tên API của thành phần tracing phụ thuộc thư viện được tích hợp; hãy nối với OpenTelemetry hoặc cơ chế tracing thực tế của dự án. Nếu chưa có tracing, vẫn có thể ghi structured log với event và orderId trước, sau đó bổ sung trace correlation.

Trong ứng dụng production, có thể dùng SLF4J/Logback hoặc framework logging hiện tại cùng JSON encoder để giữ các tính năng quen thuộc như MDC, logger name, thread và exception handling. Điều quan trọng là output cuối cùng phải là JSON hợp lệ, một event trên mỗi dòng, và các trường đặc biệt của Cloud Logging được đặt đúng tên.

### Bước 4: Xác minh trên Cloud Run

Khi ứng dụng chạy trên Cloud Run và ghi JSON ra stdout, mở Logs Explorer của đúng project rồi lọc theo resource type và service name:

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
~~~

Để tìm lỗi thanh toán:

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
severity>=ERROR
jsonPayload.event="payment.authorization_failed"
~~~

Để tìm một đơn hàng cụ thể:

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
jsonPayload.orderId="ord-1042"
~~~

Nếu các trường được parse đúng, chúng sẽ xuất hiện dưới dạng trường riêng trong phần chi tiết log entry. Nếu toàn bộ JSON nằm trong textPayload hoặc chỉ hiện như một chuỗi văn bản, hãy kiểm tra ứng dụng có ghi đúng một JSON object trên mỗi dòng hay không, output có bị bọc thêm prefix văn bản hay không và runtime có đang thu thập đúng stdout hay không.

## 6. Thiết kế schema log có thể dùng lâu dài

Một schema tốt giúp nhiều service tạo ra log có thể truy vấn cùng cách. Hãy xác định một nhóm trường chung, sau đó thêm thuộc tính riêng của từng domain.

| Nhóm | Trường gợi ý | Mục đích |
|---|---|---|
| Sự kiện | event, eventVersion | Phân loại sự kiện và quản lý thay đổi schema |
| Dịch vụ | service, environment, version | Nhận diện ứng dụng và bản phát hành |
| Nghiệp vụ | orderId, customerId nội bộ, paymentId | Liên kết log với đối tượng nghiệp vụ |
| Tương quan | requestId, correlationId, trace | Theo dấu một request qua nhiều service |
| Kết quả | outcome, errorCode, retryable | Phân tích thành công, thất bại và khả năng retry |
| Thời gian | eventTime | Thời điểm nghiệp vụ nếu khác thời điểm ghi log |

Một số nguyên tắc giúp schema ổn định:

1. Dùng tên trường có ý nghĩa và nhất quán giữa các service. Chọn orderId hoặc order_id theo quy ước của hệ thống và giữ nguyên.
2. Dùng kiểu dữ liệu phù hợp. retryable là boolean; attempt là số; event và orderId là chuỗi.
3. Đặt event name theo dạng ổn định như order.accepted hoặc payment.authorization_failed. Tránh tạo tên event từ nội dung động.
4. Thêm eventVersion khi thay đổi cấu trúc hoặc ý nghĩa payload theo cách có thể ảnh hưởng đến consumer.
5. Không dùng message làm trường duy nhất để biểu diễn sự kiện. message dành cho người đọc; event và các trường dữ liệu dành cho truy vấn.
6. Giữ payload đủ nhỏ để có thể tìm kiếm và đọc nhanh. Không đính kèm object nghiệp vụ lớn hoặc request body nguyên vẹn.

Các trường labels có thể được dùng cho metadata có số lượng giá trị giới hạn, chẳng hạn environment hoặc component. Không đưa orderId, user ID, request ID hoặc giá trị duy nhất theo từng request vào labels. Các giá trị có cardinality cao làm tăng độ phức tạp khi lập chỉ mục và truy vấn; chúng thường phù hợp hơn trong jsonPayload.

## 7. Liên kết log với request và trace

Một request có thể đi qua API gateway, Cloud Run service, Pub/Sub và worker chạy trên GKE. Mỗi thành phần có thể phát log riêng. Nếu log có request ID hoặc trace context chung, người vận hành có thể lần theo toàn bộ luồng xử lý.

Phân biệt hai loại định danh:

- **Request ID hoặc correlation ID:** mã do ứng dụng hoặc gateway dùng để liên kết các log thuộc cùng một luồng nghiệp vụ. Có thể được truyền qua header nội bộ đã thống nhất.
- **Trace ID và span ID:** định danh của distributed trace. Trace biểu diễn toàn bộ đường đi; span biểu diễn một thao tác hoặc một đoạn xử lý trong trace.

Khi ứng dụng có OpenTelemetry hoặc Cloud Trace instrumentation, hãy truyền trace context qua các lời gọi service-to-service và đưa trace ID/span ID hiện tại vào structured log. Cloud Logging có thể liên kết log entry với trace khi trường trace được ghi đúng định dạng. Điều này giúp chuyển từ log sang trace để xem latency và quan hệ giữa các span.

Không tự tạo trace ID mới ở từng service nếu mục tiêu là theo dõi cùng một request. Hãy tiếp tục context được truyền qua giao thức, đồng thời tạo span mới cho mỗi thao tác cần đo. Với request không có trace context, có thể dùng request ID riêng để tương quan log.

Không đưa toàn bộ URL có query string, header xác thực hoặc cookie vào log HTTP. Nếu cần thông tin HTTP, chỉ ghi method, route template, status code, latency và các trường đã được cho phép. Ví dụ route template /orders/{orderId} hữu ích hơn URL chứa thông tin người dùng.

## 8. Truy vấn log trong Logs Explorer

Logs Explorer hỗ trợ lọc theo metadata và trường payload. Một truy vấn thường bắt đầu bằng resource type, sau đó thêm điều kiện theo resource label, severity và jsonPayload.

**Tìm log ERROR của Cloud Run service:**

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
severity>=ERROR
~~~

**Tìm lỗi theo loại sự kiện:**

~~~text
resource.type="cloud_run_revision"
jsonPayload.event="payment.authorization_failed"
~~~

**Tìm theo mã đơn hàng:**

~~~text
jsonPayload.orderId="ord-1042"
~~~

**Tìm log của một namespace GKE:**

~~~text
resource.type="k8s_container"
resource.labels.namespace_name="production"
severity>=WARNING
~~~

**Tìm log theo trace:**

~~~text
trace="projects/my-project/traces/0123456789abcdef0123456789abcdef"
~~~

Có thể kết hợp điều kiện bằng AND, OR và NOT, hoặc dùng dấu ngoặc để nhóm biểu thức. Khi điều tra, hãy thu hẹp theo khoảng thời gian và resource trước; sau đó lọc theo severity, event, mã lỗi hoặc trace. Điều này thường hiệu quả hơn việc tìm một chuỗi từ khóa chung trên toàn project.

Nếu truy vấn không trả về kết quả, kiểm tra project đang chọn, khoảng thời gian, resource type và tên trường thực tế. Một trường nằm trong jsonPayload phải được truy vấn theo tiền tố jsonPayload; trường metadata như severity hoặc trace được truy vấn trực tiếp.

## 9. Từ log đến giám sát và cảnh báo

Log giúp giải thích sự kiện đã xảy ra. Khi cần theo dõi xu hướng hoặc phát hiện điều kiện vận hành, có thể dùng log-based metrics để đếm hoặc đo các sự kiện phù hợp.

Ví dụ, ứng dụng phát event payment.authorization_failed với severity ERROR. Có thể tạo counter metric dựa trên filter tương ứng, sau đó dùng metric trong biểu đồ hoặc alert policy. Khi số lỗi tăng vượt ngưỡng trong một cửa sổ thời gian, đội vận hành nhận cảnh báo.

Quy trình cơ bản:

1. Xác định một sự kiện có ý nghĩa vận hành và đảm bảo ứng dụng ghi event name ổn định.
2. Viết filter trong Logs Explorer để chỉ khớp đúng sự kiện.
3. Tạo log-based metric từ filter đã xác minh.
4. Kiểm tra metric có tăng đúng khi sự kiện phát sinh hay không.
5. Tạo alert policy với ngưỡng, thời gian đánh giá và notification channel phù hợp.
6. Kiểm tra cảnh báo trong môi trường thử nghiệm và điều chỉnh để giảm cảnh báo giả.

Không nên dùng log làm nguồn duy nhất cho mọi chỉ số độ tin cậy. Latency, request count, error rate và saturation thường nên được thu thập bằng metrics phù hợp; log bổ sung nguyên nhân và ngữ cảnh cho từng sự kiện. Khi kết hợp metric, log và trace, người vận hành có thể phát hiện bất thường, tìm request liên quan và xác định thành phần gây lỗi.

## 10. Bảo vệ dữ liệu và kiểm soát chi phí log

Log thường được nhiều nhóm sử dụng và có thể được xuất sang hệ thống khác. Vì vậy, mọi dữ liệu được ghi cần được xem như dữ liệu có thể được người có quyền đọc và được lưu giữ theo chính sách của tổ chức.

### Không ghi bí mật hoặc dữ liệu nhạy cảm

Không ghi:

- Mật khẩu, API key, access token, cookie phiên hoặc authorization header.
- Khóa riêng, secret payload hoặc chuỗi kết nối chứa thông tin xác thực.
- Số thẻ thanh toán, dữ liệu cá nhân không cần thiết hoặc nội dung request/response đầy đủ.
- Dữ liệu từ exception nếu thông báo lỗi có thể chứa câu lệnh, token hoặc thông tin người dùng.

Hãy lọc và che dữ liệu ngay trong ứng dụng trước khi tuần tự hóa. Việc xóa trường sau khi log đã đến Cloud Logging không bảo đảm mọi bản sao, sink hoặc hệ thống downstream đều không còn dữ liệu đó.

### Giới hạn khối lượng log

- Dùng INFO cho sự kiện vận hành quan trọng; chỉ bật DEBUG trong thời gian và phạm vi cần thiết.
- Không ghi một dòng log cho mỗi bước nhỏ trong vòng lặp có lưu lượng lớn nếu không có nhu cầu điều tra tương ứng.
- Không ghi toàn bộ request body hoặc response body. Ghi mã định danh và các thuộc tính tối thiểu cần cho điều tra.
- Tránh lặp lại stack trace ở nhiều tầng cho cùng một lỗi. Chọn nơi ghi lỗi có đủ ngữ cảnh.
- Dùng sampling có chủ đích cho sự kiện thành công có lưu lượng rất lớn; vẫn giữ đầy đủ log lỗi hoặc sự kiện bảo mật theo yêu cầu.
- Xác định retention và log bucket phù hợp với yêu cầu vận hành, pháp lý và chi phí.

### Quyền truy cập và định tuyến

Sử dụng IAM để giới hạn ai có thể xem log, cấu hình bucket, tạo sink hoặc thay đổi chính sách định tuyến. Tách quyền đọc log khỏi quyền quản trị cấu hình logging khi có thể. Với log nhạy cảm hoặc audit log, tuân theo chính sách phân quyền và lưu giữ của tổ chức.

Log Router có thể đưa log đến log bucket hoặc đích bên ngoài như BigQuery, Pub/Sub và Cloud Storage thông qua sink. Trước khi tạo sink, xác định mục đích, phạm vi filter, quyền ghi của sink và chính sách lưu giữ ở đích. Một sink quá rộng có thể sao chép dữ liệu nhiều hơn nhu cầu và làm tăng chi phí.

Exclusion filter có thể loại các log không cần lưu khỏi luồng lưu trữ phù hợp. Hãy kiểm thử filter và xem xét tác động đến điều tra sự cố trước khi loại bỏ log. Không loại bỏ audit log hoặc sự kiện bảo mật bắt buộc chỉ để giảm chi phí.

## 11. Phân biệt application log và audit log

Application log do ứng dụng tạo để mô tả xử lý nghiệp vụ hoặc kỹ thuật, ví dụ đơn hàng được tạo, thanh toán thất bại hoặc worker retry một message.

Audit log ghi lại hoạt động truy cập và thay đổi trên tài nguyên hoặc dịch vụ Google Cloud. Cloud Audit Logs có các nhóm log như Admin Activity, Data Access, System Event và Policy Denied. Những log này có cấu trúc payload chuyên biệt và thường chứa thông tin về principal, method, resource và kết quả của thao tác.

Ví dụ:

- Một Java service ghi event order.created là application log.
- Một quản trị viên thay đổi IAM policy của project tạo audit log loại Admin Activity.
- Một principal đọc dữ liệu từ một dịch vụ có bật Data Access audit logging có thể tạo audit log tương ứng.

Không nên ghi application event rồi coi đó là bằng chứng thay thế audit log. Hai loại log phục vụ các mục tiêu khác nhau và có nguồn tạo, quyền truy cập, cấu trúc cùng chính sách lưu giữ khác nhau.

## 12. Tình huống thực hành: điều tra lỗi thanh toán

Một hệ thống gồm API chạy trên Cloud Run và worker xử lý thanh toán. Người dùng báo rằng một số đơn hàng bị treo ở trạng thái chờ. Đội vận hành cần xác định lỗi bắt đầu từ API, message queue hay worker.

Hãy triển khai một schema log chung cho hai service:

- event: tên sự kiện ổn định như order.accepted, payment.requested, payment.authorization_failed và payment.completed.
- orderId: mã đơn hàng dùng để liên kết sự kiện nghiệp vụ.
- correlationId: mã tương quan xuyên qua API và worker.
- trace: trace ID nếu có distributed tracing.
- severity: INFO cho luồng bình thường, WARNING cho retry có thể phục hồi và ERROR cho thao tác thất bại cần điều tra.
- errorCode và retryable: mã lỗi ổn định cùng cờ cho biết có thể retry hay không.

Sau khi triển khai, thực hiện:

1. Tạo một đơn hàng thử nghiệm và ghi nhận orderId.
2. Xác nhận API phát event order.accepted và worker phát event payment.requested với cùng orderId/correlationId.
3. Mô phỏng lỗi timeout từ dịch vụ thanh toán trong môi trường thử nghiệm.
4. Mở Logs Explorer, lọc theo orderId và kiểm tra chuỗi sự kiện.
5. Lọc severity>=ERROR và event payment.authorization_failed để tìm log lỗi.
6. Nếu trace được bật, mở trace liên quan để kiểm tra latency của các span gọi dịch vụ thanh toán.
7. Tạo log-based metric đếm payment.authorization_failed và xác nhận metric tăng khi lỗi được mô phỏng.
8. Kiểm tra log không chứa token, cookie hoặc dữ liệu thanh toán nhạy cảm.

Kết quả mong đợi là người vận hành có thể đi từ một orderId đến các log của API và worker, nhận diện điểm thất bại và xem trace liên quan mà không cần tìm kiếm thủ công trên nhiều máy chủ.

## 13. Checklist trước khi đưa structured logging vào production

- [ ] Mỗi log entry là một JSON object hợp lệ trên một dòng.
- [ ] Severity được chọn theo tác động vận hành và dùng nhất quán.
- [ ] Event name ổn định, có ý nghĩa và không chứa giá trị động.
- [ ] Tên trường và kiểu dữ liệu thống nhất giữa các service.
- [ ] Resource type và resource labels được gắn đúng cho môi trường triển khai.
- [ ] Request ID, correlation ID hoặc trace context được truyền xuyên suốt khi phù hợp.
- [ ] Các trường trace và span được ghi theo định dạng Cloud Logging yêu cầu.
- [ ] Không ghi mật khẩu, token, cookie, khóa riêng hoặc dữ liệu cá nhân không cần thiết.
- [ ] Log volume, sampling, retention và sink phù hợp với nhu cầu và ngân sách.
- [ ] Quyền xem log và quyền quản trị logging được giới hạn bằng IAM.
- [ ] Truy vấn Logs Explorer và log-based metric đã được kiểm tra bằng sự kiện thử nghiệm.

## Câu hỏi tự kiểm tra

**1. Một LogEntry gồm những phần chính nào?**

LogEntry có metadata như logName, resource, timestamp, severity và trace; đồng thời có một payload phù hợp như jsonPayload, textPayload hoặc protoPayload.

**2. Structured logging giúp ích gì so với log văn bản?**

JSON có trường và kiểu dữ liệu rõ ràng, giúp truy vấn theo event, orderId, errorCode hoặc thuộc tính khác mà không phải phân tích câu văn tự do.

**3. Vì sao không nên đặt requestId hoặc orderId vào labels?**

Đây thường là các giá trị có cardinality cao. Chúng phù hợp hơn trong jsonPayload; labels nên dành cho metadata có tập giá trị giới hạn.

**4. Làm thế nào để Cloud Logging liên kết log với trace?**

Ghi trace context đúng định dạng, trong đó trường logging.googleapis.com/trace chứa tên tài nguyên trace đầy đủ và trường span tương ứng nếu có.

**5. Cloud Run thu thập structured log theo cách nào trong ví dụ của bài?**

Ứng dụng ghi JSON ra stdout; nền tảng thu thập log container và phân tích các trường JSON được hỗ trợ.

**6. Application log có thay thế audit log không?**

Không. Application log mô tả xử lý của ứng dụng; audit log ghi lại hoạt động truy cập hoặc thay đổi trên tài nguyên và dịch vụ theo cơ chế audit của Google Cloud.

## Kết luận

Cloud Logging cung cấp nơi tập trung để tìm kiếm và phân tích log từ ứng dụng Java, hạ tầng và dịch vụ Google Cloud. Hiểu cấu trúc LogEntry giúp phân biệt metadata với payload, chọn severity đúng và lọc theo monitored resource. Structured logging đưa sự kiện vào JSON có schema ổn định, giúp Logs Explorer truy vấn theo trường và kết nối log với trace. Khi thiết kế schema, cần chú ý bảo vệ dữ liệu nhạy cảm, kiểm soát cardinality, khối lượng log, quyền IAM và chính sách lưu giữ để hệ thống quan sát vừa hữu ích vừa có chi phí phù hợp.
