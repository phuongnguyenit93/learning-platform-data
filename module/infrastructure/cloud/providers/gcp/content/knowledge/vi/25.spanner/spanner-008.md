# Sessions, connection management và Java Spanner client

Một API đơn hàng trên **Cloud Run Java/Spring Boot**, worker trên **GKE** và database **Spanner** đều hoạt động ổn định lúc tải thấp. Khi traffic tăng, p99 latency cao dù CPU của ứng dụng còn dư. Có người đề nghị tạo client mới cho mỗi HTTP request; người khác muốn tăng `maxSessions` lên hàng nghìn. Muốn giải quyết đúng, phải phân biệt **session phía Spanner**, **gRPC channel**, **transaction** và phiên bản Java SDK đang chạy.

Bài này thuộc chương **Spanner**, mô-đun **CLOUD_PROVIDERS_GCP**. Nội dung liên hệ IAM/VPC, Compute Engine, Cloud Run, GKE, tự động hóa triển khai và quản lý độ tin cậy, chi phí. Ví dụ dùng **Spanner GoogleSQL dialect** (cú pháp tham số `@name`), không áp nguyên SQL cho database dùng PostgreSQL dialect.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt session, multiplexed session, gRPC channel, `Spanner`, `DatabaseClient`, JDBC connection và transaction.
2. Hiểu vì sao Java Spanner SDK mới **không cần chỉnh session pool cũ** theo thói quen.
3. Tạo client một lần cho vòng đời ứng dụng; đóng `ResultSet`, read-only transaction và service đúng lúc.
4. Đọc/ghi dữ liệu bằng Java, hiểu `ABORTED` và callback có thể được retry.
5. Kiểm soát concurrency khi Cloud Run/GKE scale, chẩn đoán client/server latency và lỗi tài nguyên.
6. Vận hành theo IAM tối thiểu, quan sát metrics, kiểm thử hiệu năng và dự toán chi phí.

**Lưu ý phiên bản quan trọng:** tài liệu hiện hành cho biết **multiplexed sessions bật mặc định trong `google-cloud-spanner` Java từ 6.98.0**. Ở Javadoc mới, lớp **`SessionPoolOptions` đã deprecated**, các options pool cũ không còn tác dụng khi dùng mô hình multiplexed. Bài viết cũ về `minSessions=100`, `maxSessions=400` chỉ thích hợp với **regular session pools** trong cấu hình/client legacy. Xem [Spanner sessions](https://cloud.google.com/spanner/docs/sessions) và [SessionPoolOptions API](https://cloud.google.com/java/docs/reference/google-cloud-spanner/latest/com.google.cloud.spanner.SessionPoolOptions).

## 2. Session không đồng nghĩa TCP connection

| Đối tượng | Bản chất | Vòng đời cần thiết |
| --- | --- | --- |
| **Regular session** | Context do server cấp cho database; thông thường chỉ xử lý **một transaction đồng thời**. | Tái sử dụng trong pool của client legacy. |
| **Multiplexed session** | Một server session hỗ trợ **nhiều concurrent operations/transactions**. | Được Java SDK mới quản lý tự động. |
| **gRPC channel** | Kênh mạng từ process Java tới Spanner API, có thể phục vụ nhiều RPCs. | Dùng lại và theo dõi mức đồng thời. |
| **`Spanner` service** | Đối tượng Java quản lý resources, channels và session mechanism. | Thường một instance trên mỗi JVM process, đóng khi shutdown. |
| **`DatabaseClient`** | Giao diện thao tác một database qua `Spanner`. | Tạo lúc khởi động và dùng lại xuyên các requests. |
| **`ResultSet`/`ReadOnlyTransaction`** | Stream/context của một thao tác đọc. | Đóng ngay sau khi xử lý. |
| **JDBC `Connection`** | Abstraction JDBC có cách pooling riêng. | Không gán một-một với native `DatabaseClient` hay session. |

~~~mermaid
flowchart LR
    WEB["HTTP requests / worker threads"] --> DB["Shared DatabaseClient"]
    DB --> SERVICE["Shared Spanner service"]
    SERVICE --> SESSION["Multiplexed session"]
    SERVICE --> CHANNELS["gRPC channel pool"]
    SESSION --> CLOUD["Spanner database"]
    CHANNELS --> CLOUD
    TX["Transaction/read contexts ngắn hạn"] -. "Do DatabaseClient tạo" .-> DB
~~~

Session là tài nguyên phía Spanner, **không phải mỗi session là một socket**. Với regular sessions, tạo session cần RPC và có thể bị giới hạn khi nhiều operations mượn cùng pool. Với multiplexed sessions, **một session có thể thực hiện nhiều transactions đồng thời**, giảm overhead và rủi ro cạn pool do mượn session.

| Câu hỏi | Regular sessions (legacy) | Multiplexed Java SDK mới |
| --- | --- | --- |
| Có cần nhiều sessions cho các transaction đồng thời? | Thường **có**. | **Không** theo tỷ lệ một-một. |
| Có cần tăng `minSessions/maxSessions` để tăng tải? | Có thể, sau khi đo. | **Không**; các tùy chọn này đã deprecated. |
| Cần kiểm soát resource nào? | Session pool, streams và gRPC channels. | Streams/transactions, concurrency và **gRPC channels**. |
| `ListSessions` có liệt kê đúng loại session? | Có thể dùng để xem regular sessions. | **Không liệt kê multiplexed sessions**. |

**Quan trọng:** dùng multiplexed sessions không có nghĩa có thể bỏ `ResultSet.close()`, giữ một transaction mở vô hạn hoặc tạo `Spanner` object mới mỗi request. Các vấn đề về stream, CPU, gRPC channels và application lifecycle vẫn tồn tại.

## 3. Khởi tạo Java Spanner client đúng vòng đời

### 3.1. Dependency và danh tính

Thư viện native Java có tọa độ Maven:

~~~text
com.google.cloud:google-cloud-spanner
~~~

Sử dụng version đã pin/test qua **Google Cloud Libraries BOM** hoặc dependency management của dự án; chọn **6.98.0 trở lên** nếu muốn mặc định multiplexed sessions. Trên Cloud Run, dùng **runtime service account** với **Application Default Credentials (ADC)**; trên GKE, ưu tiên **Workload Identity Federation for GKE**. Không nhúng service-account JSON key vào image hoặc repository. Đọc thêm phần IAM và mạng ở cuối bài.

### 3.2. Java ví dụ: shared client và query có tham số

Giả sử một database dùng GoogleSQL có schema:

~~~sql
CREATE TABLE Orders (
  OrderId STRING(64) NOT NULL,
  Status STRING(32) NOT NULL
) PRIMARY KEY (OrderId);
~~~

Đây là **DDL minh họa**, không phải lệnh được phép chạy trên production. Đối với application Java, tạo một repository theo vòng đời process:

~~~java
import com.google.cloud.spanner.DatabaseClient;
import com.google.cloud.spanner.DatabaseId;
import com.google.cloud.spanner.ResultSet;
import com.google.cloud.spanner.Spanner;
import com.google.cloud.spanner.SpannerOptions;
import com.google.cloud.spanner.Statement;

public final class OrdersRepository implements AutoCloseable {
    private final Spanner spanner;
    private final DatabaseClient db;

    public OrdersRepository(String project, String instance, String database) {
        SpannerOptions options = SpannerOptions.newBuilder()
                .setProjectId(project)
                .enableDynamicChannelPool() // Cần benchmark trước production.
                .build();
        spanner = options.getService();
        db = spanner.getDatabaseClient(DatabaseId.of(project, instance, database));
    }

    public String findStatus(String orderId) {
        Statement statement = Statement.newBuilder(
                        "SELECT Status FROM Orders WHERE OrderId = @id")
                .bind("id").to(orderId)
                .build();
        try (ResultSet rows = db.singleUse().executeQuery(statement)) {
            return rows.next() ? rows.getString("Status") : null;
        }
    }

    public long markPaid(String orderId) {
        Statement update = Statement.newBuilder(
                        "UPDATE Orders SET Status = @status WHERE OrderId = @id")
                .bind("status").to("PAID")
                .bind("id").to(orderId)
                .build();
        return db.readWriteTransaction().run(txn -> txn.executeUpdate(update));
    }

    @Override
    public void close() {
        spanner.close();
    }
}
~~~

Trong một CLI demo ngắn, `OrdersRepository` có thể được tạo và đóng bằng `try-with-resources`:

~~~java
try (OrdersRepository repo =
         new OrdersRepository("retail-lab", "retail-spanner", "orders")) {
    System.out.println(repo.findStatus("O-1001"));
}
~~~

**Trong Spring Boot:** đăng ký repository là **singleton bean** và dùng lifecycle destroy/shutdown hook để gọi `close()` **một lần** khi instance dừng. Không tạo trong controller method và không gọi `close()` cuối request. Nếu nhiều repository cùng chia sẻ một `Spanner` service, cần định nghĩa **một nơi chịu trách nhiệm close**.

`markPaid()` chỉ minh họa API DML; không tự biến nó thành quy trình thanh toán an toàn. Production cần kiểm tra quyền người dùng, trạng thái hợp lệ, idempotency và các tác dụng phụ ngoài DB.

## 4. Read contexts và đóng tài nguyên

### 4.1. Single-use read

`db.singleUse()` phù hợp cho một query độc lập. Đọc một tập kết quả lớn có thể dùng streaming, nhưng luôn đóng stream, kể cả khi return sớm:

~~~java
Statement q = Statement.newBuilder(
        "SELECT OrderId, Status FROM Orders WHERE Status = @state LIMIT 10")
    .bind("state").to("PENDING")
    .build();

try (ResultSet rs = db.singleUse().executeQuery(q)) {
    while (rs.next()) {
        System.out.println(rs.getString("OrderId"));
    }
}
~~~

### 4.2. Nhiều reads nhất quán tại một timestamp

`db.readOnlyTransaction()` phù hợp khi nhiều truy vấn cần nhìn **cùng một snapshot**, và phải đóng context khi xong:

~~~java
import com.google.cloud.spanner.ReadOnlyTransaction;

try (ReadOnlyTransaction tx = db.readOnlyTransaction()) {
    try (ResultSet r1 = tx.executeQuery(
            Statement.of("SELECT COUNT(*) AS Cnt FROM Orders"))) {
        if (r1.next()) {
            System.out.println("all=" + r1.getLong("Cnt"));
        }
    }
    try (ResultSet r2 = tx.executeQuery(
            Statement.of("SELECT COUNT(*) AS Cnt FROM Orders WHERE Status = 'PAID'"))) {
        if (r2.next()) {
            System.out.println("paid=" + r2.getLong("Cnt"));
        }
    }
} // Đóng transaction ngay sau hai reads.
~~~

Spanner hỗ trợ **strong read** và các mức **staleness** có chủ đích. Reporting cho phép dữ liệu hơi cũ có thể cân nhắc stale reads; kiểm tra tồn kho/số dư cần semantics nhất quán phù hợp. Không giữ read-only transaction trong khi gọi HTTP bên ngoài hoặc đợi user input.

## 5. Read-write transactions, `ABORTED` và retry an toàn

### 5.1. Transaction callback có thể chạy nhiều lần

Spanner có thể **abort** read-write transaction khi có contention. Java `DatabaseClient.readWriteTransaction().run(...)` quản lý retry cho các transaction bị `ABORTED` trong phạm vi thư viện. Vì vậy callback phải **an toàn khi được gọi lại**, có timeout và không giữ tài nguyên quá lâu.

~~~java
long affected = db.readWriteTransaction().run(txn -> {
    Statement update = Statement.newBuilder(
            "UPDATE Orders SET Status=@state WHERE OrderId=@id")
        .bind("state").to("CONFIRMED")
        .bind("id").to("O-1001")
        .build();
    return txn.executeUpdate(update);
});
~~~

**Không gửi email, gọi hệ thống thanh toán, publish Pub/Sub hoặc tạo Cloud Task trong transaction callback.** Một lần `ABORTED` có thể chạy lại callback và tạo side effects bên ngoài hai lần. Chỉ chứa các reads/writes thuộc transaction và các tính toán không gây side effect. Nếu cần điều phối việc khác sau commit, cân nhắc **transactional outbox**.

~~~mermaid
flowchart LR
    REQ["POST /orders"] --> TX["Read-write transaction"]
    TX --> O["Ghi Orders + Outbox"]
    O --> C["Commit"]
    C --> PUB["Publisher riêng"]
    PUB --> PS["Pub/Sub"]
    PS --> W["Idempotent consumer"]
~~~

Nếu publisher gửi sự kiện thành công nhưng chết trước khi đánh dấu đã gửi, message có thể phát lại. Dùng **event ID** và idempotent consumer, không hứa rằng một transaction Spanner có thể commit đồng thời với Pub/Sub hay API bên ngoài.

### 5.2. Phân biệt lỗi retry được với lỗi nghiệp vụ

| Trạng thái | Ý nghĩa khả dĩ | Cách xử lý |
| --- | --- | --- |
| `ABORTED` | Transaction bị abort/contended. | Dùng transaction runner; rút ngắn transaction, xem hotspot và abort rate. |
| `UNAVAILABLE` | Dịch vụ/network tạm không sẵn sàng. | Backoff/jitter theo client policy, chỉ retry khi thao tác an toàn. |
| `DEADLINE_EXCEEDED` | Quá deadline, commit outcome đôi khi chưa rõ. | Tra cứu theo operation ID/idempotency; tránh ghi trùng. |
| `RESOURCE_EXHAUSTED` | Quota/capacity, gRPC queueing hoặc regular pool legacy cạn. | Đọc chi tiết lỗi và metrics; không tăng pool theo phản xạ. |
| `PERMISSION_DENIED` | Principal/Spanner IAM/database role không đủ quyền. | Kiểm tra ADC, IAM/FGAC, không retry vô hạn. |
| `INVALID_ARGUMENT` | SQL, query parameter hoặc request không hợp lệ. | Sửa code/data. |
| `NOT_FOUND` | Instance, database, bảng hoặc regular session không còn. | Kiểm tra resource/schema/session mode. |

`DEADLINE_EXCEEDED` không có nghĩa database chắc chắn **chưa commit**. Với nghiệp vụ thu tiền/tạo đơn, lưu business operation ID trong kho bền vững và kiểm tra kết quả trước khi thử lại.

### 5.3. Transaction dài làm xấu concurrency

Giữ transaction ngắn để giảm contention, lock time và aborts. Nếu phải xử lý 100.000 records, cân nhắc batching/partitioned DML hoặc jobs theo điều kiện cụ thể; **không** tạo một transaction khổng lồ giữ khóa suốt quá trình gọi API ngoài. Partitioned DML có semantics khác transaction read-write thông thường và cần đánh giá idempotency/đơn vị atomicity.

## 6. Quản lý gRPC channels trong Java client mới

### 6.1. Bắt đầu từ mặc định và đo

Từ `google-cloud-spanner` 6.98.0:

- **Multiplexed sessions bật mặc định**; không cần tùy chỉnh `minSessions/maxSessions`.
- **Dynamic gRPC channel pooling mặc định tắt**; muốn thử bật gọi `SpannerOptions.Builder.enableDynamicChannelPool()`.
- Khi không dùng dynamic, client Java có **4 gRPC channels** theo cấu hình thông thường, hoặc **8 channels** khi gRPC-GCP extension bật; kiểm tra đúng version/config.
- Một gRPC channel hỗ trợ **khoảng tối đa 100 requests concurrent** theo hướng dẫn Spanner, nhưng con số cần được so với loại RPC/độ trễ/traffic thực tế.
- Nếu gọi **`setNumChannels(...)`**, dynamic channel pooling bị **tắt**, kể cả trước đó đã gọi `enableDynamicChannelPool()`.

Ví dụ cấu hình trong phần 3 bật dynamic channels:

~~~java
SpannerOptions options = SpannerOptions.newBuilder()
    .setProjectId("retail-lab")
    .enableDynamicChannelPool()
    .build();
~~~

Đây là **một biến của thí nghiệm hiệu năng**, không phải bắt buộc. Với workload nhỏ, pool mặc định có thể phù hợp hơn; với lượng RPC biến thiên, dynamic pool có thể giảm nghẽn mà không phải đoán static channel count.

### 6.2. SessionPoolOptions truyền thống đã deprecated

Một số hướng dẫn legacy đặt `minSessions=100`, `maxSessions=400` và giả định mỗi concurrent transaction cần một session riêng. Cách tính đó chỉ phù hợp khi client sử dụng **regular session pool**.

Ở client multiplexed hiện đại, Javadoc mô tả `SessionPoolOptions` đã deprecated và các tùy chọn của pool không còn chức năng. Vì vậy:

1. Đọc chính xác dependency version, không trích một blog cũ làm nguồn duy nhất.
2. Xác định session mode rồi mới đề xuất session pool tuning.
3. Xem **gRPC channels, outstanding RPCs, query plans, Spanner CPU, aborts** trước.
4. Dù dùng multiplexed, vẫn **đóng `ResultSet` và read-only transaction**, cùng `Spanner.close()` lúc shutdown.

Với client cũ còn regular pool, điều chỉnh `minSessions/maxSessions` theo **mức concurrency trên mỗi JVM**, kiểm tra session acquire wait, tài nguyên bị giữ và `ListSessions`, đồng thời lập kế hoạch nâng SDK. Đặt pool cực lớn khi có hàng trăm Cloud Run instances còn có thể làm tổng session resources tăng không cần thiết.

### 6.3. Không phải mọi bottleneck do channels

~~~text
End-to-end request latency
  = app CPU/queueing
  + client connection/gRPC/retry
  + Spanner server processing/locking
  + response serialization
~~~

Nếu **client p99 cao mà server processing latency thấp**, điều tra channels, mạng, retries và queueing. Nếu **server latency cũng cao**, xem Spanner compute, CPU, query plans, indexes và **hot keys**. Chỉ tăng channels khi có bằng chứng channel congestion; nếu bottleneck ở database, nhiều channels có thể làm tải thêm.

## 7. Cloud Run/GKE autoscaling và backpressure

### 7.1. Một shared client trên mỗi process

~~~text
Cloud Run instance A (Java process)
  OrdersController, PaymentsController
            ↓
  Shared OrdersRepository → Shared DatabaseClient/Spanner

Cloud Run instance B (process khác)
  Client riêng của process B, không dùng chung bộ nhớ A.
~~~

Tương tự trên **GKE mỗi Pod/JVM**. Trong Spring Boot, controller không tạo service object mới mỗi request. Đóng client bằng lifecycle hook khi có cơ hội shutdown, nhưng không dựa vào callback shutdown luôn chạy khi VM/Pod bị kill đột ngột.

### 7.2. Ước lượng concurrent DB operations

Ví dụ tải giả định:

~~~text
Cloud Run max instances:            30
HTTP concurrency mỗi instance:      40
Request đồng thời tối đa lý thuyết: 30 × 40 = 1.200

Nếu khoảng 25% requests đang thực hiện Spanner RPC:
Concurrent Spanner operations ước tính ≈ 1.200 × 0,25 = 300
~~~

Đó **không phải 300 sessions multiplexed cần tạo**. Số RPCs/transactions thực tế còn phụ thuộc thời gian gọi DB, số lệnh mỗi HTTP request, retries và session mode. Với workload ổn định có thể ước lượng qua Little's Law:

~~~text
Concurrent operations ≈ arrival rate (ops/s) × average DB latency (s)
Ví dụ: 800 ops/s × 0,1 s = 80 operations concurrent.
~~~

Ở burst, tải tức thời và p99 có thể vượt con số trung bình. Cần thử cùng **max instances, HTTP concurrency, connection/channel pool, CPU Spanner** và năng lực downstream. Không tăng max instances vô hạn chỉ vì API latency tăng.

### 7.3. Kiểm soát tải và hotspot

- Giới hạn outstanding DB operations, dùng hàng đợi ngắn và deadline rõ ràng; tránh memory bùng nổ.
- Chỉ retry `ABORTED` theo transaction runner; không viết retry loop bên ngoài vô hạn.
- Giữ transactions ngắn và **không làm network I/O ngoài trong callback**.
- Thiết kế primary keys tránh viết dồn vào một key/range (ví dụ monotonically increasing IDs).
- Với Pub/Sub workers trên GKE, ack **sau commit** và dùng business idempotency key.
- Dùng query parameters/indexes phù hợp để giảm scan và CPU.

## 8. IAM, mạng và thao tác kiểm tra

### 8.1. Danh tính riêng cho mỗi workload

| Principal | Nhu cầu | Quyền nên cân nhắc |
| --- | --- | --- |
| Cloud Run runtime SA | Đọc/ghi orders. | `roles/spanner.databaseUser` ở scope hợp lý và database role/FGAC nếu áp dụng. |
| GKE worker identity | Xử lý các event liên quan. | Workload Identity Federation for GKE và quyền Spanner tối thiểu. |
| CI/deployer | Deploy ứng dụng, gán runtime SA. | Deploy role và `iam.serviceAccounts.actAs`; không cần DB Admin mặc định. |
| DBA/platform | DDL và thay đổi instance/database. | Admin role riêng, phê duyệt và audit. |
| Auditor | Xem config/metrics. | Reader/Monitoring phù hợp, không cần quyền ghi dữ liệu. |

ADC trên local có thể dùng principal khác hoàn toàn runtime identity Cloud Run/GKE. Nếu local chạy được nhưng production `PERMISSION_DENIED`, xác nhận **principal đang thật sự gọi Spanner**, IAM allow/deny policy và database-level roles. Không dùng key JSON gắn trong JAR.

### 8.2. Endpoint là Google API, không phải private IP của Cloud SQL

Native Spanner Java SDK kết nối tới **Spanner API** qua endpoint được hỗ trợ, không kết nối trực tiếp một VM database. Khi dùng Cloud Run/GKE private networking, kiểm tra **Google APIs egress**, DNS, Private Google Access/Private Service Connect khi có và VPC Service Controls. Cloud NAT/VPC routing, IAM và database authorization là các lớp khác nhau. Không mở external IP cho mọi GKE nodes chỉ để sửa lỗi `PERMISSION_DENIED`.

### 8.3. Ví dụ `gcloud` read-only

~~~bash
PROJECT_ID="retail-lab"
INSTANCE_ID="retail-spanner"
DATABASE_ID="orders"

# READ-ONLY: xác nhận CLI principal và project.
gcloud auth list
gcloud config get-value project

# READ-ONLY: cấu hình Spanner instance và database.
gcloud spanner instances describe "$INSTANCE_ID" \
  --project="$PROJECT_ID" --format=yaml
gcloud spanner databases describe "$DATABASE_ID" \
  --instance="$INSTANCE_ID" --project="$PROJECT_ID"

# READ-ONLY: truy vấn GoogleSQL khi principal được cấp quyền đọc.
gcloud spanner databases execute-sql "$DATABASE_ID" \
  --instance="$INSTANCE_ID" --project="$PROJECT_ID" \
  --sql="SELECT COUNT(*) AS Cnt FROM Orders"
~~~

Resource IDs chỉ minh họa; không có instance hay database thật được tạo bằng các lệnh này. Với database PostgreSQL dialect, điều chỉnh DDL/parameter syntax theo dialect đó.

## 9. Quan sát session, client và server latency

| Lớp | Tín hiệu / metric có ích | Mục đích |
| --- | --- | --- |
| Spanner | `spanner.googleapis.com/instance/session_count` | Số sessions phía database; **không** dùng như một phép đếm gRPC connections. |
| Spanner server | CPU utilization, request latencies, transaction aborts, query stats. | Phân biệt thiếu compute, query tốn CPU hay contention. |
| Spanner client | `spanner.googleapis.com/client/operation_latencies` | Latency bao gồm các attempts/retries theo client. |
| Spanner client | `spanner.googleapis.com/client/attempt_latencies` | Latency mỗi RPC attempt. |
| Kết nối | `spanner.googleapis.com/client/gfe_connectivity_error_count` | Các lỗi trước khi client nhận response header từ Google Front End. |
| Ứng dụng | Request p50/p95/p99, RPC count, concurrent DB calls và error codes. | Phân tích ảnh hưởng tới người dùng. |
| Cloud Run/GKE | Container/Pod count, CPU, memory, throttling, restarts. | Autoscaling có gây tăng RPC/resources không? |

Client-side metrics có thể yêu cầu bật **Cloud Monitoring API** và quyền `roles/monitoring.metricWriter` cho principal xuất metrics. Metrics server có độ trễ sampling, nên kiểm tra khoảng thời gian và tải tương ứng; không kết luận từ một điểm lẻ.

**`ListSessions`** có thể hữu ích khi tìm sessions bị bỏ quên của **regular session pools** qua `createTime` và `approximateLastUseTime`. API **không liệt kê multiplexed sessions**, vì vậy danh sách trống không chứng minh client không dùng session. Với multiplexed, xem **client/server latency, gRPC channel utilization, RPC queueing và CPU**.

## 10. Tình huống vận hành: retail API gặp p99 tăng đột biến

### 10.1. Triệu chứng

Một dịch vụ Java trên Cloud Run dùng Spanner để xem và cập nhật đơn hàng. Trong giờ sale:

| Tín hiệu | Mức trước tải | Mức khi tăng tải | Giả thuyết |
| --- | ---: | ---: | --- |
| HTTP requests/s | 100 | 900 | Cloud Run scale-out mạnh. |
| p99 HTTP latency | 180 ms | 2.100 ms | Có hàng đợi hoặc query chậm. |
| Spanner server p99 | 70 ms | 85 ms | Server không chậm tương ứng với client. |
| Client operation p99 | 100 ms | 1.600 ms | Client/network/queueing/retry đáng xem xét. |
| Java library | 6.124.0 | 6.124.0 | Multiplexed sessions mặc định. |

**Số liệu giả định** nhằm thực hành phân tích, không phải benchmark Spanner. Vì server p99 chỉ tăng ít nhưng client p99 tăng nhiều, **không vội nâng Spanner processing units hoặc `maxSessions`**.

### 10.2. Kế hoạch điều tra

1. Xác nhận Java client version, việc `Spanner` có được tạo một lần mỗi process hay không, và stream/transaction closure.
2. Kiểm tra Cloud Run instance count, concurrency, thread pool, CPU/memory và số RPCs mỗi request.
3. So client operation/attempt latency, retries, GFE connectivity errors và server processing latency.
4. Xem dynamic channel pool đã bật hay đang dùng static channels; đối chiếu channel congestion và log.
5. Thử bật **dynamic channel pooling** trong staging/traffic canary với cùng workload. Không đổi CPU, max instances và query code đồng thời.
6. Quan sát p95/p99, aborts, 5xx, cost và mức tiêu thụ tài nguyên; rollback cấu hình nếu không cải thiện.

Nếu client và server cùng chậm, chuyển hướng điều tra **Spanner CPU, query scans/indexes, hot keys, read-write lock contention**. Cải thiện networking không sửa được một SQL query quét dữ liệu quá lớn.

### 10.3. Chi phí không chỉ nằm ở sessions

Spanner billing chủ yếu gắn với **compute capacity, database storage, backup, network/data transfer và các tính năng theo bảng giá**, không phải cứ tạo một session là một khoản phí cố định. Tuy nhiên session/channel quá nhiều vẫn dùng resources và có thể làm hiệu suất kém; Cloud Run/GKE scale-out cũng phát sinh CPU/RAM và lưu lượng.

Nên đo **chi phí trên mỗi đơn hàng thành công** cùng p99/error rate. Đừng tăng compute gấp đôi khi lỗi thực tế là tạo client mới trên từng request.

## 11. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Điều cần kiểm tra |
| --- | --- | --- |
| Request đầu tiên chậm, request tiếp theo nhanh | ADC/JVM/client/gRPC warm-up hoặc Spanner query initialization. | Startup trace, client creation, channel initialization. |
| Tăng HTTP concurrency làm p99 tăng | Client RPC queueing, channel congestion, Spanner CPU hoặc application thread contention. | Client/server latencies, channels, CPU và queue lengths. |
| `minSessions` không thay đổi kết quả | Java SDK mới dùng multiplexed; tùy chọn pool cũ deprecated. | Dependency version, session mode và gRPC channels. |
| Legacy app báo session pool exhausted | Regular pool nhỏ, ResultSet/read-only transaction không đóng. | Session acquire time, leak traces, ListSessions nếu phù hợp. |
| `ABORTED` tăng | Read-write contention, transactions dài/hotspot. | Abort rate, hot keys, duration; TransactionRunner. |
| `DEADLINE_EXCEEDED` khi ghi | Deadline, network hoặc trạng thái commit chưa rõ. | Trace, operation ID và idempotency trước khi retry. |
| `RESOURCE_EXHAUSTED` | Quota/capacity, client channels hoặc session pool legacy. | Chi tiết error, compute, channels và quotas. |
| `PERMISSION_DENIED` chỉ trên GKE | Workload identity/database role khác local ADC. | Effective principal, Spanner IAM/FGAC, audit logs. |
| `NOT_FOUND` | Sai database/table, hoặc regular session bị xóa trong client cũ. | Resource IDs, schema, version/mode. |
| Stream đọc không bao giờ kết thúc | ResultSet chưa đóng, query lớn hoặc client đọc chậm. | Try-with-resources, streaming/paging và memory. |
| Session count thấp nhưng p99 cao | Multiplexed session vẫn chạy nhiều transactions. | gRPC capacity, app queueing, server CPU và query latency. |
| Không có client-side metrics | Chưa bật Monitoring API/metric export hoặc thiếu IAM. | Telemetry configuration, `roles/monitoring.metricWriter`. |

**Runbook ngắn:** xác định đúng project/instance/database và principal → kiểm tra Java client version/mode → xác minh singleton và resource closure → so sánh latency client/server → xem autoscaling/CPU/query plans → thử thay **một biến** và xác minh SLO. Không sửa `PERMISSION_DENIED` bằng cách tăng channel count, hoặc sửa timeout bằng cách cấp project Owner.

## 12. Bài tập thực hành

### Bài 1 — Session hay channel?

Một ứng dụng có 80 transactions đồng thời. Có bắt buộc phải tạo 80 TCP connections hay 80 sessions không? Giải thích sự khác nhau giữa **regular** và **multiplexed sessions**.

### Bài 2 — Tìm resource leak

Một controller tạo `SpannerOptions.getService()` mỗi HTTP request, mở query `ResultSet` rồi không đóng. Liệt kê ba hậu quả về tài nguyên hoặc latency. Đề xuất lifecycle Spring singleton và cách đóng tài nguyên.

### Bài 3 — Query có tham số

Viết `getStatus(String orderId)` bằng `db.singleUse()`, `Statement` có named parameter và `try-with-resources`. Vì sao không ghép `orderId` trực tiếp thành SQL string?

### Bài 4 — Retry transaction

Một callback `readWriteTransaction().run(...)` vừa update Spanner vừa gọi email provider. Nếu lần đầu bị `ABORTED`, điều gì xảy ra khi runner retry? Sửa thiết kế bằng **outbox + idempotent consumer**.

### Bài 5 — Pool config cũ

Code dùng `google-cloud-spanner` 6.124.0, nhưng tài liệu nội bộ yêu cầu `SessionPoolOptions.setMinSessions(100)`. Bạn kiểm tra gì trước và nên tối ưu theo số liệu nào thay vì làm theo hướng dẫn cũ?

### Bài 6 — Tính concurrent RPC

Cloud Run `max instances=24`, `concurrency=50`. Giả sử cùng một thời điểm 30% requests đang thực hiện một Spanner RPC. Ước lượng số Spanner operations concurrent tối đa. Có nên đặt số sessions bằng kết quả đó trên Java SDK mới?

**Gợi ý:** 24 × 50 × 0,30 = **360 concurrent operations** theo giả định, **không** suy ra cần 360 multiplexed sessions.

### Bài 7 — So sánh consistency

Dashboard chấp nhận dữ liệu cũ một phút, nhưng checkout cần cập nhật trạng thái đơn nhất quán. Khi nào chọn single-use strong read, read-only transaction có bound phù hợp hoặc read-write transaction? Những thao tác nào không được đưa vào retry callback?

### Bài 8 — IAM

Local ADC truy cập Spanner thành công nhưng Cloud Run service báo `PERMISSION_DENIED`. Nêu thứ tự kiểm tra runtime service account, Spanner IAM, database role/FGAC, VPC Service Controls và network path.

### Bài 9 — Benchmark gRPC pool

Thiết kế thí nghiệm A/B: A dùng mặc định gRPC pool, B bật `enableDynamicChannelPool()`. Giữ nguyên workload, Java version, database compute, Cloud Run concurrency và schema; đo **client p95/p99, server processing latency, errors, CPU, RPC throughput và chi phí** trước khi chọn.

## 13. Checklist production và tài liệu chính thức

| Hạng mục | Điều cần xác minh |
| --- | --- |
| **Version/mode** | Java SDK được pin và kiểm thử; biết multiplexed sessions bật mặc định hay không. |
| **Client lifecycle** | Shared `Spanner`/`DatabaseClient` trên mỗi process, đóng `Spanner` khi shutdown. |
| **Resource closure** | `ResultSet`/read-only transaction được đóng; không giữ context quá lâu. |
| **Transaction retry** | `ABORTED` dùng runner; callback không có tác dụng phụ ngoài DB; business idempotency. |
| **Concurrent load** | Cloud Run/GKE autoscaling, outstanding DB ops, deadlines và backpressure phù hợp. |
| **gRPC channels** | Mặc định hoặc dynamic channels được benchmark; không kết hợp vô ý với `setNumChannels`. |
| **Identity/network** | ADC, runtime SA/Workload Identity, Spanner IAM/FGAC, Google APIs egress. |
| **Monitoring** | Client/server p95/p99, session count theo mode, CPU, aborts, errors và channel pressure. |
| **SLO/cost** | Đánh giá compute, storage, client CPU/memory, network, cost per transaction. |
| **Recovery** | Có runbook IAM, network, quota, `ABORTED`, timeout và rollback Java dependency/config. |

Nguồn chính thức để kiểm chứng API theo phiên bản:

- [Spanner sessions và multiplexed sessions](https://cloud.google.com/spanner/docs/sessions)
- [Spanner sessions — phần Multiplexed sessions](https://cloud.google.com/spanner/docs/sessions)
- [Bắt đầu dùng Spanner với Java](https://cloud.google.com/spanner/docs/getting-started/java)
- [Spanner Java `Spanner` lifecycle](https://cloud.google.com/java/docs/reference/google-cloud-spanner/latest/com.google.cloud.spanner.Spanner)
- [Spanner Java `DatabaseClient`](https://cloud.google.com/java/docs/reference/google-cloud-spanner/latest/com.google.cloud.spanner.DatabaseClient)
- [Spanner Java `TransactionRunner`](https://cloud.google.com/java/docs/reference/google-cloud-spanner/latest/com.google.cloud.spanner.TransactionRunner)
- [Spanner Java `SessionPoolOptions` (deprecated)](https://cloud.google.com/java/docs/reference/google-cloud-spanner/latest/com.google.cloud.spanner.SessionPoolOptions)
- [Spanner client-side metrics](https://cloud.google.com/spanner/docs/view-manage-client-side-metrics)
- [Spanner metrics](https://cloud.google.com/spanner/docs/metrics)
- [Spanner error codes](https://cloud.google.com/spanner/docs/error-codes)
- [Spanner IAM](https://cloud.google.com/spanner/docs/iam)
- [Spanner pricing](https://cloud.google.com/spanner/pricing)

**Ghi nhớ:** session là tài nguyên phía Spanner; gRPC channel là đường RPC; cả hai **không đồng nghĩa một HTTP request hay JDBC connection**. Java client mới dùng multiplexed sessions nên **không cần chỉnh session pool cũ**, nhưng vẫn phải tái sử dụng client đúng vòng đời, đóng streaming resources, giữ transaction callback an toàn khi retry và kiểm soát concurrency. **Đo p99 từ client đến server trước khi tăng resources** để bảo vệ độ tin cậy cùng chi phí.


