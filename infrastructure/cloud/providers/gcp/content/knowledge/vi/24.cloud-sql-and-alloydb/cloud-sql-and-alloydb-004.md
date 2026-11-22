# Cloud SQL high availability và cơ chế failover

Một dịch vụ Java `orders-api` chạy trên Cloud Run lưu đơn hàng vào Cloud SQL for PostgreSQL. Khi zone chứa database gặp sự cố, mọi request ghi đơn đều có nguy cơ lỗi. **High availability (HA)** của Cloud SQL giảm thời gian gián đoạn bằng cách duy trì **primary và standby ở hai zone trong cùng region**, tự chuyển vai trò khi primary không còn phục vụ được.

Nhưng **HA không đồng nghĩa không downtime**, không thay thế backup và cũng **không tự xử lý transaction bị ngắt trong ứng dụng**. Bài học giải thích cơ chế, giới hạn, cấu hình và kiểm thử failover, rồi thiết kế ứng dụng Java có thể phục hồi kết nối mà không tạo đơn hàng hoặc thanh toán trùng.

Bài thuộc chương **Cloud SQL và AlloyDB** của mô-đun `CLOUD_PROVIDERS_GCP`, kết nối kiến thức project/IAM/VPC với Compute Engine, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu, triển khai tự động và theo dõi độ tin cậy cùng chi phí. Ví dụ chính dùng **Cloud SQL for PostgreSQL**; MySQL và SQL Server có các điều kiện/cờ backup, logging và tính năng riêng.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **ZONAL** và **REGIONAL (HA)**, primary, standby và read replica.
2. Mô tả **synchronous replication** và quy trình automatic/manual failover trong cùng region.
3. Đánh giá đúng **RTO, RPO**, những transaction có kết quả không chắc chắn và giới hạn của SLA.
4. Bật, xác minh và diễn tập Cloud SQL HA với `gcloud` trong môi trường lab.
5. Thiết kế kết nối Java/HikariCP, retry có giới hạn và idempotency cho nghiệp vụ ghi.
6. Phân biệt failover nội vùng với **PITR, backup, read replica và disaster recovery liên vùng**.
7. Lập dashboard, runbook và dự toán chi phí cho hệ thống production.

## 1. Vì sao Cloud SQL cần HA?

Một Cloud SQL instance kiểu **ZONAL** vận hành tại một zone. Cloud SQL có thể tự khắc phục một số lỗi máy chủ, nhưng khi **toàn zone không khả dụng**, instance ZONAL không tự chuyển sang zone khác với cùng cơ chế HA. Muốn giảm rủi ro đó, chọn **REGIONAL**.

| Khía cạnh | ZONAL | REGIONAL / HA |
| --- | --- | --- |
| Vị trí database | Một zone | Primary và standby ở **hai zone khác nhau**, cùng region |
| Chống mất một zone | Cần quy trình phục hồi thủ công | Có **automatic failover** khi điều kiện cho phép |
| Chuyển quyền ghi | Một primary | Standby trở thành primary |
| Endpoint ứng dụng | Endpoint instance | **Giữ cùng IP/connection name** khi failover nội vùng thông thường |
| Đọc từ standby | Không có standby | **Không**; standby HA không phải read replica để scale đọc |
| Dữ liệu đã commit | Phụ thuộc khả dụng và backup | Replication đồng bộ qua storage của hai zone để bảo vệ committed writes |
| Chi phí cơ sở | Theo tài nguyên instance | Cao hơn vì thêm thành phần dự phòng, thường xấp xỉ gấp đôi phần CPU/RAM/storage |
| Khi mất cả region | Cần DR/restore | **HA nội vùng vẫn không đủ** |

REGIONAL phù hợp database quan trọng trên Cloud Run, GKE, App Engine hoặc Compute Engine. Không phải mọi project dev/test cần HA: chi phí standby và việc kiểm thử phục hồi phải tương xứng SLO.

## 2. Kiến trúc primary, standby và storage đồng bộ

~~~mermaid
flowchart LR
    APP["Orders API<br/>Cloud Run / GKE"] --> EP["Cloud SQL endpoint<br/>giữ ổn định"]
    EP --> P["Primary - zone A<br/>đọc + ghi"]
    P --> D1[("Persistent disk A")]
    P --> SYNC["Synchronous replication"]
    SYNC --> D2[("Persistent disk B")]
    D2 --> S["Standby - zone B<br/>không nhận app queries"]
    CTRL["Cloud SQL HA control<br/>health + failover"] -.-> P
    CTRL -.-> S
~~~

Cloud SQL sử dụng cơ chế sao chép đồng bộ đến storage ở cả hai zone: một transaction được báo **commit thành công** sau khi dữ liệu ghi tương ứng đã được nhân bản bền vững theo cơ chế HA. Khi primary hoặc zone A gặp lỗi, Cloud SQL có thể đưa standby zone B lên vai trò primary, rồi định tuyến kết nối mới tới đó.

**Ba giới hạn thiết kế:**

- **Standby không phải read replica.** Không gửi `SELECT` trực tiếp tới standby để tăng throughput đọc.
- **HA chỉ bao phủ một region.** Nếu cả region gặp sự cố kéo dài, cần kiến trúc DR khác.
- **HA không tránh mọi restart.** Một số lỗi tài nguyên, ví dụ hết RAM, có thể khiến Cloud SQL **restart** thay vì failover; phải kiểm tra operation log để phân biệt.

### 2.1. Standby sau khi failover

Sau khi zone B trở thành primary, B **tiếp tục là primary** ngay cả khi A hoạt động trở lại. Cloud SQL tái tạo primary cũ thành **standby mới**. Hệ thống **không tự failback** sang zone A ngay khi nó khỏe; nếu có yêu cầu quay về zone A, phải lên kế hoạch **manual failover/failback** riêng.

## 3. RTO, RPO và SLA: đo đúng phạm vi

| Chỉ số | Câu hỏi | Cloud SQL HA giải quyết thế nào? |
| --- | --- | --- |
| **RTO** (Recovery Time Objective) | Có thể gián đoạn bao lâu trước khi phục hồi dịch vụ? | Cloud SQL cho biết failover thường khiến instance không sẵn sàng **khoảng 60 giây**; thời gian thực tế có thể khác |
| **RPO** (Recovery Point Objective) | Chấp nhận mất bao nhiêu dữ liệu đã ghi? | Replication đồng bộ nhằm bảo toàn **committed writes** khi mất một zone; khác hoàn toàn RPO của async replica/PITR |
| **SLA** | Mức khả dụng dịch vụ theo hợp đồng? | Còn tùy edition, cấu hình/tier đủ điều kiện và điều khoản SLA hiện hành |
| **Application recovery** | Người dùng có gửi đơn thành công lại không? | Cần retry/reconnect/idempotency và kiểm tra phụ thuộc sau failover |

**Không biến “khoảng 60 giây” thành cam kết RTO tối đa**. Lỗi client, DNS/network, pool connections, khởi tạo JVM, saturation sau failover và các phụ thuộc ngoài database có thể khiến ứng dụng phục hồi lâu hơn.

### 3.1. Commit không chắc chắn là gì?

~~~mermaid
sequenceDiagram
    participant A as Java API
    participant P as Primary
    participant S as Standby / HA storage
    A->>P: COMMIT order A100
    P->>S: Replicate committed data
    S-->>P: Sync complete
    Note over A,P: Kết nối bị cắt khi phản hồi COMMIT đang về
    A-xP: Không nhận được kết quả rõ ràng
    Note over A: Không biết transaction đã COMMIT hay chưa
~~~

Có hai khả năng khi client mất kết nối tại mốc commit:

1. Database **đã commit**, nhưng client không nhận được phản hồi.
2. Database **chưa commit**, transaction bị rollback khi kết nối mất.

Cả hai đều có thể hiện thành một lỗi JDBC. Vì vậy **không tự retry một lệnh tạo đơn mới mà không có idempotency key**, ngay cả khi storage có RPO tốt.

### 3.2. Edition không đồng nghĩa cùng SLA

Cloud SQL **Enterprise** và **Enterprise Plus** có các mức SLA/tính năng bảo trì khác nhau; tài liệu hiện hành nêu các mức **99,95%** và **99,99%** tương ứng khi đáp ứng điều kiện. Không lấy mức 99,99% của Enterprise Plus để gán mặc định cho mọi Cloud SQL instance. Phải kiểm tra **edition, máy chuyên dụng, cấu hình HA và hợp đồng SLA** trong project.

## 4. Failover tự động diễn ra khi nào?

Quy trình điển hình:

1. Primary hoặc zone đang chứa primary không đáp ứng các **health signals**.
2. Cloud SQL xác định lỗi đủ điều kiện, standby/secondary zone còn khỏe, và bắt đầu failover.
3. Standby trở thành primary mới, khôi phục phục vụ đọc/ghi qua **cùng endpoint instance**.
4. Các kết nối TCP/PostgreSQL hiện tại bị ngắt; **application phải kết nối lại**.
5. Cloud SQL tái tạo bản dự phòng mới và phục hồi khả năng HA sau sự cố.

~~~mermaid
flowchart TD
    A["Primary unhealthy"] --> B{"Standby/secondary zone healthy?"}
    B -->|Có| C["Cloud SQL failover"]
    C --> D["Standby trở thành primary"]
    D --> E["Clients reconnect<br/>cùng endpoint"]
    E --> F["Tạo lại standby khi zone cũ khỏe"]
    B -->|Không| G["Không thể failover bình thường"]
    G --> H["Incident / restore / DR runbook"]
~~~

### 4.1. Không phải lỗi nào cũng gây failover

| Tình huống | Hành vi cần dự kiến |
| --- | --- |
| Lỗi zone A, standby B khỏe | Automatic failover theo điều kiện |
| Lỗi VM/primary đủ điều kiện | Có thể failover |
| Instance thiếu RAM hoặc resource exhaustion | Có thể **restart**, không nhất thiết failover |
| Primary đang bảo trì hoặc đang chạy operation dài | Failover có thể bị hạn chế/trì hoãn theo điều kiện |
| Standby/zone B không khỏe | Không có đích an toàn để failover |
| Cả hai zone hoặc cả region không khả dụng | HA nội vùng không giải quyết |
| Ứng dụng hoặc Cloud SQL Auth Proxy mất kết nối | Không chứng minh database đã failover; có thể chỉ là lỗi mạng/identity |

Khi điều tra, đối chiếu **Operations history**, database logs, application logs và trạng thái monitoring. Không dùng một exception `connection reset` để suy ra chắc chắn failover.

## 5. HA khác read replica, backup và disaster recovery

| Công cụ | Mục tiêu chính | Đặc điểm |
| --- | --- | --- |
| **Cloud SQL HA standby** | Khả dụng khi mất zone | Cùng region, đồng bộ, **không đọc trực tiếp**, automatic failover |
| **Read replica cùng region** | Scale đọc, giảm tải primary | Replication khác HA standby; **không tự biến thành primary** nếu mất zone |
| **Cross-region read replica** | Đọc gần người dùng/DR | Async replication, có **replication lag**; promote hoặc thủ tục DR riêng |
| **Automated backup + PITR** | Khôi phục do xóa nhầm, hỏng logic, sai migration | Restore theo thời điểm, thường không tức thì; phải thử restore |
| **AlloyDB HA** | Khả dụng trên hệ PostgreSQL-compatible khác | Kiến trúc/storage và các thao tác failover riêng; không áp lệnh Cloud SQL vào AlloyDB |

**Phân biệt “HA” với “DR”:** HA Cloud SQL thường xử lý lỗi trong **một region**; DR xử lý tình huống **region bị sự cố** hoặc cần phục hồi từ bản sao/backup ở vùng khác. Với **Cloud SQL Enterprise Plus**, một số cấu hình có **advanced disaster recovery / designated DR replica / switchover**; đó là quy trình riêng, không phải failover HA standby hai zone.

### 5.1. Read replica không phải standby HA

Một read replica có endpoint và trạng thái replication riêng, có thể nhận đọc khi khỏe. Khi primary HA failover, replica ngoài zone sự cố có thể tiếp tục kết nối tới primary mới; replica ở zone hỏng cũng bị gián đoạn. Nếu cần bảo đảm availability cho read replicas, xem hỗ trợ HA trên replica và phân bố zone.

**Không** chuyển ứng dụng từ primary sang read replica chỉ vì nhìn thấy “replica”, trừ khi đã **promote**, đánh giá RPO và cập nhật connection endpoints theo runbook.

## 6. Điều kiện trước khi bật HA

Mô-đun thực hành dùng **PostgreSQL**, nhưng Cloud SQL cũng có MySQL và SQL Server. Các engine có điều kiện backup/logging khác nhau.

| Kiểm tra | Lý do |
| --- | --- |
| Region hỗ trợ edition và machine type | HA đòi hỏi hai zone phù hợp và năng lực ở region |
| Chọn `REGIONAL` thay vì `ZONAL` | Bật mô hình primary + standby |
| **Automated backups + PITR** cho PostgreSQL theo điều kiện cấu hình | Hỗ trợ quy trình backup/recovery; nên được kiểm tra trước khi bật HA |
| MySQL: backups và binary logs theo yêu cầu engine | Không dùng cờ PostgreSQL để thay cho `--enable-bin-log` |
| IAM `cloudsql.instances.update` và operation permissions | Chỉ deployer/DBA có quyền thay đổi HA |
| SLO, change window và rollback plan | Bật HA trên instance hiện hữu **có restart/downtime** |
| Billing budget và quota | REGIONAL làm tăng chi phí CPU/RAM/storage |
| Ứng dụng hỗ trợ reconnect/idempotency | Failover đóng mọi kết nối hiện hữu |

**Không bật HA như một thao tác chỉ đọc**. Chuyển một instance đã có từ ZONAL sang REGIONAL thường restart và có thể mất từ vài phút đến lâu hơn tùy disk size và load. Với production phải có change approval và kiểm tra tác động lên giao dịch.

## 7. Preflight chỉ đọc với gcloud

Giả định có instance tên `orders-db-ha-lab` ở `asia-southeast1`. Thay bằng tên instance được phép xem.

~~~bash
gcloud auth list
gcloud config get-value project

gcloud sql instances list --project=PROJECT_ID

gcloud sql instances describe orders-db-ha-lab \
  --project=PROJECT_ID \
  --format="yaml(name,state,region,gceZone,secondaryGceZone,connectionName,settings.availabilityType,settings.backupConfiguration,ipAddresses)"

gcloud sql operations list \
  --instance=orders-db-ha-lab \
  --project=PROJECT_ID \
  --limit=20
~~~

Đối chiếu output với bảng:

| Field | Giá trị mong đợi của HA |
| --- | --- |
| `settings.availabilityType` | `REGIONAL` |
| `gceZone` | Zone hiện tại của primary |
| `secondaryGceZone` | Zone khác trong cùng region |
| `state` | Thường `RUNNABLE` khi instance sẵn sàng |
| `settings.backupConfiguration` | Backups và PITR theo cấu hình được hỗ trợ |
| `connectionName` | Identifier dùng bởi connector/Auth Proxy |
| `ipAddresses` | Endpoint đang dùng; **đừng đưa public IP vào log không cần thiết** |

**Nếu instance chưa tồn tại hoặc người dùng không có quyền đọc**, không tạo hay sửa production chỉ để hoàn tất bước này. Các lệnh trên dùng để **khảo sát**, không ép failover.

## 8. Tạo một PostgreSQL HA instance trong project lab

Ví dụ dành cho **người đã được cấp quyền**, có budget và hiểu instance này phát sinh chi phí liên tục:

~~~bash
gcloud services enable sqladmin.googleapis.com \
  --project=PROJECT_ID

gcloud sql instances create orders-db-ha-lab \
  --project=PROJECT_ID \
  --database-version=POSTGRES_16 \
  --edition=ENTERPRISE \
  --region=asia-southeast1 \
  --cpu=2 \
  --memory=7680MB \
  --storage-size=20 \
  --storage-auto-increase \
  --availability-type=REGIONAL \
  --backup-start-time=02:00 \
  --enable-point-in-time-recovery
~~~

**Đây là ví dụ tạo tài nguyên tính phí thật**. Các flags `--cpu` và `--memory` tương ứng **Enterprise edition**; Enterprise Plus dùng machine tier được hỗ trợ, không áp cặp flags này như nhau. Chọn loại machine, disk, private IP, public IP, vùng, backup retention, deletion protection và CMEK theo yêu cầu tổ chức. Không mặc định database để public chỉ vì lab.

Một số project/region có thể có quota hoặc zone capacity khác; nếu lệnh thất bại, kiểm tra quyền/edition/quota chứ không thử xóa instance tồn tại. Tài liệu CLI chính thức là nguồn đối chiếu cho những flags thay đổi.

### 8.1. Bật HA cho instance đã có

Nếu preflight xác định instance `ZONAL` và DBA đã phê duyệt:

~~~bash
# GÂY TÁC ĐỘNG: có thể restart và tạo downtime!
gcloud sql instances patch INSTANCE_NAME \
  --availability-type=REGIONAL \
  --project=PROJECT_ID
~~~

Trước khi chạy, kiểm tra cấu hình backups/PITR của PostgreSQL theo mục 7. Với MySQL, quy trình HA có yêu cầu backup/binary logging và các cờ cấu hình khác; không áp lệnh PostgreSQL mẫu rồi coi đã đáp ứng mọi engine.

**Không dùng `--availability-type=ZONAL` làm “rollback đơn giản”**: vô hiệu HA sẽ bỏ bảo vệ failover và có thể restart. Muốn hoàn nguyên thay đổi production phải có đánh giá kỹ thuật và phê duyệt.

## 9. Manual failover để kiểm tra ứng dụng

Cloud SQL hỗ trợ **manual failover** để diễn tập giống sự kiện failover thật. Chỉ chạy trên **HA instance**, không có instance operation khác đang diễn ra, standby khỏe và ứng dụng đã được chuẩn bị.

~~~bash
# DỪNG: chỉ chạy sau khi người sở hữu instance chấp thuận.
gcloud sql instances failover orders-db-ha-lab \
  --project=PROJECT_ID
~~~

**Tác động thực:** kết nối database đang mở bị cắt, request có thể thất bại, primary chuyển zone, standby cần được tái tạo. Đây **không phải bài lab read-only** và không được chạy trên production mà thiếu change window.

Kiểm chứng sau đó:

~~~bash
gcloud sql instances describe orders-db-ha-lab \
  --project=PROJECT_ID \
  --format="yaml(state,region,gceZone,secondaryGceZone,settings.availabilityType,connectionName)"

gcloud sql operations list \
  --instance=orders-db-ha-lab \
  --project=PROJECT_ID \
  --limit=20
~~~

**Kỳ vọng:** `gceZone` có thể chuyển sang zone trước đó là standby; instance cuối cùng ở trạng thái phục vụ được; connection name không đổi. Sau đó ứng dụng **tự reconnect và thực hiện được giao dịch**. Chỉ báo “operation DONE” không đủ để khẳng định nghiệp vụ phục hồi.

### 9.1. Failback không tự động

Sau failover, đợi cấu hình dự phòng phục hồi khỏe trước khi cân nhắc **manual failback**. Failback thực hiện thao tác failover ngược lại và **cũng làm gián đoạn kết nối**. Không tự chạy failover lần thứ hai chỉ để biểu đồ “quay về zone A”.

## 10. Ứng dụng Java cần làm gì khi failover?

Cloud SQL giữ endpoint trong failover HA nội vùng, nhưng **không giữ các TCP sessions đã mở**. Với Java JDBC/HikariCP:

- Tránh dùng một `Connection` hoặc `PreparedStatement` tĩnh, dài hạn qua nhiều requests.
- Dùng pool có **connection timeout, maximum pool size và max lifetime** phù hợp.
- Khi gặp lỗi mạng, hủy connection hỏng, lấy connection mới từ pool.
- Retry **kết nối mới** với backoff có giới hạn; không tạo tight loop khi DB đang unavailable.
- Nếu lỗi giữa transaction, **retry từ đầu transaction** trên connection mới; không dùng lại transaction đã lỗi.
- Dùng **idempotency key** để xử lý transaction outcome không rõ tại mốc COMMIT.

**Cloud SQL Auth Proxy và Java Connector không giữ lại transaction bị đứt**. Auth Proxy cũng mất connections khi failover và ứng dụng phải tạo kết nối mới. Dù kết nối sau failover dùng cùng connection name, nó không thể “tiếp tục” một transaction đã mất.

### 10.1. Ví dụ cấu hình HikariCP

Một Spring Boot service với `spring-boot-starter-jdbc`, PostgreSQL driver và HikariCP có thể bắt đầu bằng các thiết lập:

~~~properties
spring.datasource.hikari.maximum-pool-size=5
spring.datasource.hikari.minimum-idle=0
spring.datasource.hikari.connection-timeout=10000
spring.datasource.hikari.validation-timeout=5000
spring.datasource.hikari.max-lifetime=1800000
spring.datasource.hikari.idle-timeout=600000
~~~

Đây là **ví dụ**, không phải thông số tối ưu cho mọi workload. Chọn pool theo số instances × concurrency × giới hạn `max_connections` của Cloud SQL:

~~~text
Pool tối đa dự tính = số application instances × maximumPoolSize

Ví dụ: 20 Cloud Run instances × 5 = tối đa khoảng 100
kết nối pool (chưa kể migrations, jobs, monitoring, tools).
~~~

Nếu GKE/Cloud Run autoscale, tổng connection count có thể vượt DB quota nhanh hơn bạn nghĩ. Có thể cần managed connection pooling khi edition/tính năng hỗ trợ, nhưng vẫn phải size và test.

### 10.2. Mẫu retry an toàn

~~~text
BEGIN attempt:
  1. Lấy connection mới với timeout.
  2. Kiểm tra requestId/idempotencyKey.
  3. Thực hiện toàn bộ transaction.
  4. COMMIT.
  5. Trả kết quả ổn định cho cùng requestId.

Nếu lỗi kết nối trước commit hoặc commit outcome không rõ:
  - Bỏ connection/transaction lỗi.
  - Chờ exponential backoff + jitter, tổng attempts có giới hạn.
  - Thử lại toàn bộ transaction với CÙNG idempotencyKey.
  - Nếu hết giới hạn, trả lỗi có thể retry hoặc ghi queue/outbox.

Không retry một lệnh ghi không-idempotent bằng một requestId mới.
~~~

Thời gian retry phải phù hợp timeout của caller (Cloud Run request deadline/HTTP client) và workload, không chờ vô hạn.

## 11. Bài Java/JDBC: không tạo shipping task trùng khi retry

Giả sử endpoint `POST /shipments` có `requestId` cố định từ client hoặc được tạo và lưu bền vững trước khi xử lý. PostgreSQL tạo hai bảng:

~~~sql
CREATE TABLE IF NOT EXISTS processed_requests (
    request_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shipping_tasks (
    request_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'READY'
);
~~~

Ví dụ Java xử lý **một transaction** trên một connection JDBC mới lấy từ pool:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class ShippingRepository {
    // Caller đóng/hoàn trả Connection và retry cả method với CÙNG requestId.
    public static boolean createOnce(
            Connection db, String requestId, String orderId)
            throws SQLException {
        boolean originalAutoCommit = db.getAutoCommit();
        db.setAutoCommit(false);
        try {
            int inserted;
            try (PreparedStatement p = db.prepareStatement(
                    "INSERT INTO processed_requests(request_id, order_id) "
                    + "VALUES (?, ?) ON CONFLICT DO NOTHING")) {
                p.setString(1, requestId);
                p.setString(2, orderId);
                inserted = p.executeUpdate();
            }

            if (inserted == 1) {
                try (PreparedStatement p = db.prepareStatement(
                        "INSERT INTO shipping_tasks "
                        + "(request_id, order_id) VALUES (?, ?)")) {
                    p.setString(1, requestId);
                    p.setString(2, orderId);
                    p.executeUpdate();
                }
            }
            db.commit();   // Marker + side effect cùng commit.
            return inserted == 1;
        } catch (SQLException failure) {
            try {
                db.rollback();
            } catch (SQLException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
            throw failure;
        } finally {
            db.setAutoCommit(originalAutoCommit);
        }
    }
}
~~~

**Ý nghĩa:** nếu commit trước khi failover đã thành công nhưng client mất response, retry với `requestId` cũ gặp unique constraint và không tạo task thứ hai. Nếu transaction chưa commit, retry có thể chèn mới rồi hoàn tất. Unique key hoạt động kể cả khi nhiều Pods/instances đồng thời gọi API.

**Giới hạn của ví dụ:** trong production cần kiểm tra **payload hash/orderId** khi requestId đã tồn tại; một requestId tái sử dụng với payload khác phải trả conflict, không silently bỏ qua. Nếu lỗi xảy ra lúc `setAutoCommit(originalAutoCommit)`, caller phải xử lý connection không an toàn và trả nó về pool theo cơ chế library. Những side effects ngoài PostgreSQL (gửi email, thanh toán) **không nằm trong transaction JDBC**: dùng outbox, idempotency key ở đối tác hoặc quy trình reconcile.

### 11.1. Minh họa crash window

| Thời điểm lỗi | DB state | Retry an toàn |
| --- | --- | --- |
| Trước `COMMIT` | Transaction rollback | Chèn và tạo task |
| Sau `COMMIT` nhưng trước response | Có marker và task | Phát hiện duplicate, không tạo thêm |
| Sau DB commit nhưng trước gửi Pub/Sub event | DB có dữ liệu, event có thể mất | **Transactional outbox** khi cần atomic DB state + publish |
| Trong lúc gọi payment API ngoài DB | Không biết trạng thái payment | Idempotency token với payment provider + reconcile |

**RPO tốt của Cloud SQL không loại bỏ “unknown commit outcome” ở phía client.**

## 12. Kết nối từ Cloud Run, GKE và Compute Engine

| Nền tảng | Cách kết nối thường dùng | Cần kiểm tra khi failover |
| --- | --- | --- |
| **Cloud Run** | Cloud SQL integration, Java connector hoặc Auth Proxy/Private IP | Concurrency, pool size × max instances, timeout, VPC egress và service account |
| **GKE** | Workload Identity Federation, Cloud SQL Auth Proxy sidecar/connector hoặc Private IP | Nhiều Pod replicas cùng retry, Pod readiness và NetworkPolicy |
| **Compute Engine** | Service account VM + Auth Proxy/connector hoặc IP bảo vệ | Persistent proxy lifecycle, firewall, service health |
| **App Engine** | Connector/integration theo môi trường | Instance scaling và connection quota |
| **AlloyDB** | API/connector HA riêng | **Không dùng** lệnh `gcloud sql instances` của Cloud SQL |

### 12.1. IAM và mạng không được bỏ qua

- Runtime identity cần quyền **Cloud SQL Client** khi dùng connector/Auth Proxy theo cấu hình; database vẫn cần **database authentication/role** riêng.
- Private IP cần đường mạng từ VPC và cấu hình Private Service Access/PSC tùy kiến trúc.
- Dùng TLS/chứng chỉ, IAM DB auth hoặc Secret Manager theo chính sách; **không nhúng mật khẩu DB trong image**.
- Không mở public IP hoặc authorized network `0.0.0.0/0` chỉ để test failover.
- Trong cross-project topology, kiểm tra cả service account IAM, VPC routing, region và quota.

Một lỗi kết nối sau failover có thể do application pool, proxy, firewall, IAM hoặc DNS/PSC, **không nhất thiết database chưa chuyển primary**.

## 13. Backup, PITR và phục hồi dữ liệu ngoài HA

HA bảo vệ trước **sự cố một zone**, nhưng dữ liệu lỗi do ứng dụng hoặc con người **cũng được nhân bản đồng bộ**:

~~~text
UPDATE accounts SET balance = 0;   -- Lỗi nghiệp vụ
            |
            v
Dữ liệu sai được ghi bền vững vào cả hai zone của HA.
~~~

Vì vậy cần:

- **Automated backups** với retention và location đáp ứng RPO/RTO nghiệp vụ.
- **Point-in-time recovery (PITR)** để phục hồi theo thời điểm khi được bật và logs còn trong retention.
- **Thử restore** định kỳ bằng instance thử; không xem việc backup “SUCCESS” là bằng chứng ứng dụng phục hồi được.
- Xử lý secrets/encryption keys, IAM, connection endpoints và migration rollback trong runbook.
- **Cross-region DR replica** hoặc chiến lược phù hợp nếu yêu cầu phục hồi khi cả region bị ảnh hưởng.

**RTO/RPO của PITR/backup/async replica không giống HA failover**. Ví dụ recovery bằng bản sao async có thể chịu replication lag; restore từ backup có thời gian dựng instance và kiểm tra nhất quán.

## 14. Operations, Logs và Cloud Monitoring

### 14.1. Quan sát failover qua operation log

~~~bash
gcloud sql operations list \
  --instance=orders-db-ha-lab \
  --project=PROJECT_ID \
  --limit=30

# Khi có OPERATION_ID thật:
gcloud sql operations describe OPERATION_ID \
  --project=PROJECT_ID
~~~

Trong Console: **Cloud SQL → instance → Operations/Logs** để xem **Failover**, **Restart**, maintenance, zone change và lỗi thao tác. Trường hợp failover được kích hoạt bởi ai có thể cần **Cloud Audit Logs** với audit logging thích hợp.

Đọc Cloud Logging:

~~~bash
gcloud logging read \
  'resource.type="cloudsql_database" AND severity>=ERROR' \
  --project=PROJECT_ID --freshness=1h --limit=50
~~~

**Lưu ý:** application JDBC exceptions nằm trong log **Cloud Run/GKE/VM**, không nhất thiết có trong `cloudsql_database`. Cần kết hợp hai nguồn.

### 14.2. Dashboard tối thiểu

| Nhóm | Chỉ số/tín hiệu | Hành động khi bất thường |
| --- | --- | --- |
| Cloud SQL instance | State/availability, operations failover/restart | Xác định thực sự có failover không |
| Database | CPU, memory, disk utilization | Phân biệt quá tải với lỗi zone |
| Connections | Active connections, connection errors | Phát hiện retry storm hoặc pool exhaustion |
| Latency | Query time, transaction errors | Đánh giá DB đã phục vụ bình thường chưa |
| Ứng dụng | HTTP 5xx, timeout, p95/p99, retry count | Đánh giá trải nghiệm người dùng |
| Dữ liệu | Số đơn đúng, duplicate IDs, invariant violations | Đánh giá hiệu ứng nghiệp vụ |
| DR | Backup/PITR status, replica lag, restore drill | Đánh giá khả năng khôi phục ngoài HA |
| FinOps | CPU/RAM/storage, backups, networking, logs | Kiểm soát chi phí sau khi bật HA |

Tài liệu Google Cloud lưu ý **metrics failover tự động không nhất thiết bao gồm manual failover**. Vì vậy cần **operation history + logs + kiểm thử ứng dụng** khi diễn tập; không kết luận thử nghiệm thất bại chỉ vì biểu đồ automatic failover không tăng.

## 15. Runbook diễn tập failover an toàn

**Điều kiện bắt buộc:** môi trường test/HA lab, chủ sở hữu phê duyệt, có backup/PITR, client instrumentation và tiêu chí dừng.

~~~mermaid
flowchart TD
    P["Preflight: DB REGIONAL + standby healthy"] --> B["Backup và xác minh ứng dụng"]
    B --> I["Ghi initial zone, instance endpoint, metrics"]
    I --> F["Manual failover trên LAB"]
    F --> O["Theo dõi operation + JDBC errors"]
    O --> R["Ứng dụng reconnect + bounded retry"]
    R --> D{"SLO/DB invariants đạt?"}
    D -->|Có| DONE["Ghi RTO quan sát + postmortem"]
    D -->|Không| STOP["Dừng canary / mở incident / DR runbook"]
~~~

### 15.1. Trước failover

1. Lấy `gcloud sql instances describe`, ghi `gceZone`/`secondaryGceZone`, region, availability type.
2. Kiểm tra standby healthy, không có operation dài đang chạy.
3. Chạy probe an toàn: `SELECT 1` và API request test có `requestId`.
4. Ghi RTO mục tiêu, thời gian, traffic, connection error baseline, app/database CPU.
5. Kiểm tra Cloud SQL backup/PITR và quyền theo môi trường.

### 15.2. Trong failover

- DBA chạy **một lần** `gcloud sql instances failover` cho instance lab.
- Theo dõi operations, HTTP 5xx, JDBC connection errors, pool checkout time, retries, DB connection count.
- Quan sát người dùng thử có bị lỗi tạm hay không; **không retry vô hạn** và không hạ IAM/network policy để chữa lỗi.
- Nếu phải dừng, ưu tiên giữ **khả năng phục hồi dữ liệu** và liên hệ người điều hành incident; không liên tiếp failover/failback.

### 15.3. Sau failover

- Xác nhận primary zone mới, endpoint/connection name ổn định, status và standby đang được phục hồi.
- Chạy `SELECT 1` và nghiệp vụ ghi/đọc trong lab; kiểm tra duplicate IDs và kết quả transaction.
- Tính **RTO quan sát** từ thời điểm service không đáp ứng đến thời điểm SLO phục hồi (không lấy thời gian CLI kết thúc).
- Ghi sự khác biệt giữa **automatic failover, manual failover, restart** và tác động lên backups/replicas.
- Lưu runbook, alerts và thay đổi retry/backoff cần thiết.

## 16. Troubleshooting sau khi bật HA

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| `availabilityType=ZONAL` | Chưa bật HA hoặc patch chưa hoàn tất | Describe/operation log |
| Không thấy standby zone | Instance chưa REGIONAL hoặc đang tái cấu hình | `secondaryGceZone`, status, operations |
| Instance mất kết nối ~1 phút | Failover đang diễn ra | Operations + zone change |
| Mất kết nối nhưng không có Failover | Restart do memory/CPU hoặc sự cố network/connector | Operation type, resources, app logs |
| Sau failover JDBC tiếp tục lỗi | Pool giữ connection hỏng, retry không tạo connection mới | Pool metrics, connection validation |
| Cloud SQL Auth Proxy vẫn chạy nhưng app lỗi | Proxy không giữ session cũ, hoặc IAM/network/config | Proxy logs, reconnect, credentials |
| App retry tạo hai đơn | Thiếu idempotency khi commit result mơ hồ | Unique request ID, DB records |
| GKE tăng replicas nhưng DB `too many connections` | Pool size × Pod count quá lớn | Pool settings, max_connections |
| Read replica không phục vụ | Replica ở zone lỗi hoặc lag/sai kết nối | Replica zone, status, replication lag |
| Bật HA gây downtime | Chuyển ZONAL → REGIONAL có restart | Change record/operation duration |
| Manual failover không tăng metric automatic failover | Metric loại này chỉ theo dõi automatic events | Operations history |
| Hóa đơn tăng sau HA | Standby CPU/RAM/storage và backups/network | Cloud Billing SKU, edition/region |

## 17. Chi phí: đánh đổi với độ sẵn sàng

Cloud SQL HA có phần tài nguyên primary/standby và storage across zones. Tài liệu mô tả cấu hình HA khoảng **gấp đôi chi phí standalone phần CPU, RAM và storage**, chưa gồm backups, mạng, read replicas, logging, data egress và các dịch vụ liên quan.

| Khoản chi | Cần dự toán |
| --- | --- |
| Primary + standby | CPU/memory theo edition, tier và region |
| Storage | Dung lượng, loại disk, regional redundancy |
| Backups/PITR | Retention, transaction logs, dung lượng restore |
| Read replicas/DR | Mỗi replica, network transfer và region khác |
| Connection/data traffic | Network/VPC, egress, Cloud SQL connectors |
| Observability | Logging, Monitoring và traces |
| Diễn tập | Workload test, instance lab, temporary resources |

**Không tự xem HA là “tăng phí nhưng không thay đổi gì khác”**: với một số workload, availability giảm sự cố, nhưng cần điều chỉnh connection pools, retry và SLO để tận dụng. Dùng **Cloud Billing Reports, budgets và alerting**; budget alert **không tự chặn chi tiêu**.

### 17.1. Ước lượng đơn giản

Giả sử chi phí CPU/RAM/storage của một **standalone** ở cùng tier/region là `C` mỗi tháng:

~~~text
Chi phí phần cơ sở của HA ≈ 2 × C

Tổng chi phí hệ thống ≈ HA base + backup/PITR + network
                       + read replicas/DR + observability + app resources
~~~

Đây là **mô hình tương đối**, không phải báo giá. Tra bảng giá theo engine/edition, machine, disk, region và billing SKU thực tế.

## 18. Tình huống tổng hợp: Orders API và failover hai zone

**Bối cảnh:** `orders-api` Java trên Cloud Run, Cloud SQL PostgreSQL Enterprise HA ở hai zone trong `asia-southeast1`, Cloud Storage chứa hóa đơn và Pub/Sub phát `OrderPaid`.

**Sự cố:** primary zone ngừng phục vụ. Trong lúc failover, 2% request tạm lỗi `SQLTransientConnectionException`; một số request ghi đơn không biết COMMIT thành công hay chưa.

**Thiết kế xử lý:**

| Lớp | Biện pháp |
| --- | --- |
| Cloud SQL | `REGIONAL` primary+standby, backups/PITR, monitoring |
| Cloud Run | Bounded retries với jitter, không vượt request deadline |
| Java | HikariCP kết nối mới, pool size theo tổng instances |
| Database | Unique `request_id`/idempotency key, transaction cho business state |
| Pub/Sub | Transactional outbox để không mất `OrderPaid` sau DB COMMIT |
| Networking | Private connectivity, Auth Proxy/Java Connector, IAM tối thiểu |
| DR | Cross-region replica/restore drill nếu yêu cầu mất region |
| SRE | Dashboard 5xx, latency, connection errors, operation logs, restore/HA drills |

**Kết quả mong đợi:** request mới có thể tạm thất bại trong cửa sổ failover, rồi kết nối lại qua endpoint cũ; request ghi lặp với **cùng idempotency key** không tạo đơn hàng/trả tiền hai lần. Điều này là mục tiêu vận hành **cần kiểm chứng bằng thử nghiệm**, không phải điều Cloud SQL tự đảm bảo cho mã ứng dụng bất kỳ.

## 19. Bài tập thực hành và tự kiểm tra

**Bài 1 — Audit HA read-only.** Dùng `gcloud sql instances describe` trên instance lab và xác định `availabilityType`, primary/secondary zones, trạng thái, backups và PITR.

*Đạt:* Hai zone khác nhau trong cùng region, `REGIONAL` và prerequisites đúng.

**Bài 2 — Tính RTO.** Trong môi trường được phép, ghi timestamp ứng dụng bắt đầu lỗi, chạy failover một lần, ghi timestamp SLO phục hồi.

*Đạt:* Có **RTO quan sát** của ứng dụng, không suy từ “~60 giây” hoặc output CLI.

**Bài 3 — Transaction outcome.** Giả lập COMMIT thành công nhưng client timeout; gửi lại cùng `requestId`.

*Đạt:* Chỉ có một record nghiệp vụ; unique key giữ bất biến.

**Bài 4 — DR thiết kế.** Cơ sở dữ liệu phải phục hồi sau khi **cả region** mất điện dài ngày. Đề xuất thành phần bổ sung.

*Đáp án gợi ý:* Cross-region DR replica/backup và runbook promotion/restore phù hợp RPO/RTO; HA hai zone là chưa đủ.

**Câu 5.** Standby HA có thể phục vụ read queries như read replica không?

*Đáp án:* Không. Standby HA là đích failover, không phải read endpoint.

**Câu 6.** Failover có tạo connection string mới bắt buộc cho ứng dụng không?

*Đáp án:* Với HA nội vùng thông thường, giữ IP/connection name; nhưng các TCP/JDBC connections cũ bị đóng, phải reconnect.

**Câu 7.** Nếu Cloud SQL HA có đồng bộ storage, có còn cần backups/PITR không?

*Đáp án:* Có. Delete/schema mistakes và dữ liệu sai cũng được đồng bộ, cần restore/PITR.

**Câu 8.** Lỗi `connection reset` luôn chứng tỏ failover?

*Đáp án:* Không. Có thể do mạng, proxy, pool, maintenance hoặc restart; xem Operations/logs.

**Câu 9.** Sau failover, primary có tự quay lại zone A khi zone A khỏe không?

*Đáp án:* Không. Zone B tiếp tục primary; failback là thao tác riêng, có gián đoạn.

**Câu 10.** Vì sao không retry transaction ngay từ `INSERT` cuối cùng trên connection đã lỗi?

*Đáp án:* Transaction/session có thể bị hủy hoặc commit không chắc chắn; cần connection mới, retry **toàn bộ transaction** cùng idempotency key.

**Câu 11.** Read replica khác region có bảo đảm RPO bằng 0 như HA đồng bộ hai zone không?

*Đáp án:* Không. Replication async có thể có lag, cần DR plan/monitoring.

**Câu 12.** Instance vừa đổi ZONAL → REGIONAL có hoàn toàn không downtime?

*Đáp án:* Không. Cấu hình mới có thể restart, cần change window.

**Câu 13.** Có nên tăng JDBC pool size vô hạn khi failover để kết nối lại nhanh?

*Đáp án:* Không. Retry storm/DB max_connections có thể kéo dài outage; cần pool limits và backoff.

**Câu 14.** Có thể dùng giá/SLA của Enterprise Plus cho instance Enterprise không?

*Đáp án:* Không. Edition và điều kiện SLA/billing phải kiểm tra riêng.

## 20. Checklist production

- [ ] Database production quan trọng đã đánh giá HA `REGIONAL` và hai zone.
- [ ] Edition, máy chuyên dụng, region, SLA và chi phí được phê duyệt.
- [ ] Backups/PITR có retention rõ, được kiểm thử restore.
- [ ] Primary/standby healthy; có giám sát status/operations.
- [ ] Ứng dụng dùng pool với connection validation, timeout và bounded retry.
- [ ] Idempotency key bảo vệ các transaction khi kết quả COMMIT không chắc chắn.
- [ ] External side effects (Pub/Sub, payment, email) có outbox/reconcile.
- [ ] Cloud Run/GKE/VM IAM, database roles, VPC/private network/TLS đúng.
- [ ] Connection budget tính theo **instances × pool size**.
- [ ] Có runbook manual failover/failback, kiểm tra positive và negative.
- [ ] Có DR plan riêng khi mất region: replica/backup/restore/promotion.
- [ ] Alerts cho SQL errors, latency, connections, CPU/disk, backup và business SLO.
- [ ] Mọi thay đổi availability type, zone, failover trên production cần approval.
- [ ] Budget và billing review bao gồm HA storage, replicas, backups và network.

## 21. Kết luận

**Cloud SQL high availability** sử dụng **primary–standby ở hai zone trong một region**, đồng bộ storage và có thể tự failover khi zone/instance primary không phục vụ được. Kết nối cũ sẽ bị gián đoạn; ứng dụng phải **reconnect và retry an toàn**, còn việc rollback dữ liệu hoặc mất cả region cần **backup/PITR và DR riêng**.

Đối với Java service, nguyên tắc vận hành quan trọng nhất là: **REGIONAL HA + đúng SLO + kiểm thử failover + connection pool giới hạn + retry toàn transaction với idempotency key + giám sát và dự toán chi phí**.

## Tài liệu tham khảo chính thức

- [Cloud SQL: Availability overview](https://cloud.google.com/sql/docs/availability)
- [Cloud SQL for PostgreSQL: High availability](https://cloud.google.com/sql/docs/postgres/high-availability)
- [Enable/disable Cloud SQL HA (PostgreSQL)](https://cloud.google.com/sql/docs/postgres/configure-ha)
- [Cloud SQL for PostgreSQL: Instance settings](https://cloud.google.com/sql/docs/postgres/instance-settings)
- [Cloud SQL for PostgreSQL: Editions and SLAs](https://cloud.google.com/sql/docs/postgres/choose-edition)
- [Cloud SQL for PostgreSQL: Manage database connections](https://cloud.google.com/sql/docs/postgres/manage-connections)
- [Cloud SQL Auth Proxy and failover](https://cloud.google.com/sql/docs/postgres/sql-proxy)
- [Cloud SQL PostgreSQL: Replication and read replicas](https://cloud.google.com/sql/docs/postgres/replication)
- [Cross-region replica promotion / DR](https://cloud.google.com/sql/docs/postgres/replication/cross-region-replicas)
- [Cloud SQL PostgreSQL: Disaster recovery](https://cloud.google.com/sql/docs/postgres/intro-to-cloud-sql-disaster-recovery)
- [Cloud SQL PostgreSQL: Logging](https://cloud.google.com/sql/docs/postgres/logging)
- [gcloud sql instances create](https://cloud.google.com/sdk/gcloud/reference/sql/instances/create)
- [gcloud sql instances failover](https://cloud.google.com/sdk/gcloud/reference/sql/instances/failover)
- [Cloud SQL pricing](https://cloud.google.com/sql/pricing)

