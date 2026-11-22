# Maintenance, nâng cấp phiên bản và thay đổi schema trên Cloud SQL và AlloyDB

Một hệ thống bán lẻ lưu đơn hàng trong **Cloud SQL for PostgreSQL**, phục vụ API trên **Cloud Run** và worker trên **GKE**. Đội nền tảng muốn nhận bản vá bảo mật, nâng PostgreSQL lên major version mới và thêm cột cho trạng thái giao hàng mà không làm gián đoạn phiên thanh toán. Ở hệ thống phân tích khác, **AlloyDB for PostgreSQL** có primary và read pools cần được bảo trì theo lịch riêng.

Ba loại thay đổi trên **không giống nhau**:

- **Maintenance:** Google Cloud cập nhật phần mềm/hạ tầng được quản lý. Có thể cần chuyển đổi hoặc khởi động lại thành phần, làm rớt kết nối tạm thời.
- **Database engine upgrade:** đổi phiên bản tương thích của PostgreSQL, đặc biệt **major version**, có thể thay behavior, extension và yêu cầu downtime riêng.
- **Schema migration:** đội ứng dụng thay bảng, cột, index, constraint hoặc dữ liệu. Dù Google quản lý máy chủ, **tính tương thích với code và lock do DDL vẫn là trách nhiệm của đội ứng dụng**.

Bài học thuộc chương **Cloud SQL và AlloyDB**, mô-đun **CLOUD_PROVIDERS_GCP**. Nội dung kết nối tổ chức project/IAM/VPC, Cloud Run, GKE, lưu trữ và cơ sở dữ liệu với tự động hóa phát hành, bảo vệ tài nguyên, độ tin cậy và chi phí. Ví dụ tập trung vào PostgreSQL vì cả hai sản phẩm đều hỗ trợ hệ sinh thái này; **không áp nguyên lệnh PostgreSQL cho Cloud SQL MySQL hoặc SQL Server**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt maintenance version, PostgreSQL minor/major version và ứng dụng schema version.
2. Cấu hình, kiểm tra **maintenance window**, thời điểm rollout, notifications và **deny period** theo giới hạn Cloud SQL/AlloyDB.
3. Chuẩn bị đường phục hồi khi mất kết nối: connection pooling, retries có giới hạn, HA, read replicas và kiểm thử SLO.
4. Lập kế hoạch major version upgrade bằng in-place hoặc migration sang hệ thống mới; hiểu rollback **không phải downgrade tại chỗ**.
5. Triển khai thay đổi schema theo **expand → backfill → switch → contract**, tránh DDL lock kéo dài và phá code phiên bản cũ.
6. Vận hành migration từ CI/CD, giám sát, thử khôi phục và đánh giá RTO/RPO cùng chi phí.

## 2. Bốn loại phiên bản cần theo dõi

| Thứ được cập nhật | Ai điều khiển chính? | Ví dụ | Tác động cần đánh giá |
| --- | --- | --- | --- |
| **Maintenance release** | Google Cloud phát hành, người dùng chọn lịch/điều kiện được hỗ trợ. | Bản vá hệ thống, thành phần engine. | Kết nối gián đoạn ngắn, patch bảo mật, thông báo lịch. |
| **PostgreSQL minor compatibility** | Dịch vụ quản lý theo chính sách sản phẩm. | 16.3 → 16.4. | Lỗi đã vá, extension/driver, có thể đi cùng maintenance. |
| **PostgreSQL major version** | Đội vận hành chủ động lập kế hoạch nâng cấp. | 15 → 16, nếu là target hỗ trợ. | Breaking changes, flags, extensions, downtime, rollback. |
| **Application schema version** | Đội phát triển/DBA. | Thêm `orders.customer_note_v2`. | Locks, backfill, tương thích nhiều revision ứng dụng. |

Một lệnh **self-service maintenance** không phải lệnh nâng PostgreSQL major version. Tương tự, nâng engine thành công không khiến migration Flyway/Liquibase của ứng dụng tự được áp.

~~~mermaid
flowchart LR
    CODE["Cloud Run / GKE revisions"] --> DRIVER["DB drivers / pools"]
    DRIVER --> DB["Cloud SQL hoặc AlloyDB"]
    MAINT["Maintenance release"] -. "Bản vá do nền tảng quản lý" .-> DB
    ENGINE["Major version upgrade"] -. "Kiểm thử tương thích engine" .-> DB
    MIG["Schema/data migration"] -. "DDL + backfill do app quản lý" .-> DB
    CI["CI/CD + approval"] --> ENGINE
    CI --> MIG
    OBS["Monitoring + Audit Logs"] -. "Theo dõi toàn tuyến" .-> DB
~~~

## 3. Cloud SQL: maintenance window và deny period

### 3.1. Lịch bảo trì không cam kết downtime bằng 0

Cloud SQL có **maintenance window**: ngày và giờ ưu tiên để **bắt đầu** maintenance, với khoảng lên lịch một giờ. Có thể chọn thứ tự rollout:

| Maintenance timing | Ý nghĩa |
| --- | --- |
| `Any` | Không chỉ định tuần cụ thể; thường gần đầu đợt rollout. |
| `Week 1` (`preview`) | Khoảng 7–14 ngày sau thông báo. |
| `Week 2` (`production`) | Khoảng 15–21 ngày sau thông báo. |
| `Week 5` (`week5`) | Khoảng 35–42 ngày sau thông báo. |

**Mẫu staging trước production:** đặt staging ở `Week 1`, production ở `Week 2` hoặc `Week 5`, chạy smoke/connection tests sau staging maintenance trước khi cho production cập nhật. Chọn giờ ít traffic và kiểm tra **múi giờ**: giờ truyền bằng `gcloud` được hiểu theo **UTC**, không tự theo giờ người vận hành.

Một maintenance event có thể làm database không nhận kết nối trong một khoảng thời gian. Độ gián đoạn phụ thuộc edition, topology, workload và connection behavior; **maintenance window không phải giới hạn cứng về thời gian outage**. Cả khi đã đặt lịch, thay đổi bảo mật khẩn cấp vẫn có thể được áp ngoài lịch.

### 3.2. Deny maintenance period

**Deny period** tránh maintenance được lên lịch trong thời gian kinh doanh nhạy cảm. Cloud SQL cho phép khoảng **1–90 ngày** theo điều kiện sản phẩm. Từ **15/08/2025**, instance có maintenance version **cũ hơn 12 tháng** không được đặt deny period mới trước khi cập nhật lên bản đủ mới.

Ví dụ: tránh scheduled maintenance trong tuần flash sale, nhưng phải chủ động chừa kỳ nhận bản vá sau đó. Deny period **không chặn mọi thao tác người dùng tự kích hoạt**, không phải công cụ vô hiệu hóa bản vá khẩn và không bảo đảm không downtime vì các nguyên nhân khác.

Không nối nhiều deny periods chỉ để hoãn bản vá vô thời hạn. Với primary có read replicas, cần kiểm tra tác động deny period tới cả các replicas.

### 3.3. Đọc cấu hình và chỉnh lịch bằng `gcloud`

Các lệnh Bash sau sử dụng **tên tài nguyên giả định**. Lệnh `patch` **ghi cấu hình thật**, chỉ chạy trong project thử nghiệm đã được duyệt:

~~~bash
PROJECT_ID="retail-lab"
SQL_INSTANCE="orders-db"

# READ-ONLY: đọc trạng thái, lịch, phiên bản engine và maintenance.
gcloud sql instances describe "$SQL_INSTANCE" \
  --project="$PROJECT_ID" --format=yaml

# WRITE: đặt cửa sổ Chủ nhật 02:00 UTC và Week 2.
gcloud sql instances patch "$SQL_INSTANCE" \
  --project="$PROJECT_ID" \
  --maintenance-window-day=SUNDAY \
  --maintenance-window-hour=2 \
  --maintenance-release-channel=production

# READ-ONLY: xác minh cấu hình trả về, không chỉ tin vào lệnh vừa gửi.
gcloud sql instances describe "$SQL_INSTANCE" \
  --project="$PROJECT_ID" \
  --format="yaml(settings.maintenanceWindow,maintenanceVersion,availableMaintenanceVersions)"
~~~

Với Việt Nam (`Asia/Ho_Chi_Minh`), **02:00 UTC là 09:00 sáng**, không phải 02:00 sáng. Nếu muốn khoảng 02:00 sáng giờ Việt Nam vào Chủ nhật, cần chuyển thành **19:00 UTC thứ Bảy**.

Đăng ký **maintenance notifications** phù hợp project và người nhận; Cloud SQL không mặc nhiên gửi email cho tất cả operators. Khi dự kiến bảo trì, kiểm tra trạng thái instance, kế hoạch phát hành ứng dụng, alerting và runbook.

### 3.4. Self-service maintenance và phiên bản hiện tại

Cloud SQL có thể cho phép **chủ động cập nhật maintenance version** trước lịch chung:

~~~bash
# READ-ONLY: xác minh maintenanceVersion và availableMaintenanceVersions
# trong kết quả describe trước khi chọn giá trị.
gcloud sql instances describe "$SQL_INSTANCE" \
  --project="$PROJECT_ID" --format=yaml

# WRITE, CHỈ MINH HỌA: thay giá trị bằng version thật do describe trả về.
gcloud sql instances patch "$SQL_INSTANCE" \
  --project="$PROJECT_ID" \
  --maintenance-version="REPLACE_WITH_AVAILABLE_MAINTENANCE_VERSION"
~~~

Không tự đoán chuỗi maintenance version. Sau khi cập nhật, **không thể đơn giản đổi ngược về một maintenance version cũ**. Với replica topology, chọn đúng quy trình cập nhật primary/replicas theo tài liệu.

## 4. AlloyDB: bảo trì ở cấp cluster

AlloyDB cũng được Google Cloud quản lý nhưng có **mô hình primary/read pool** và thuộc tính maintenance riêng.

| Thuộc tính | Cloud SQL for PostgreSQL | AlloyDB for PostgreSQL |
| --- | --- | --- |
| Scope cấu hình thường dùng | Instance. | Cluster, gồm primary và read pools. |
| Maintenance window | Một giờ theo ngày/giờ UTC. | Giờ bắt đầu ưu tiên; sự kiện có thể kéo dài sau cửa sổ. |
| Rollout timing | `Any`, `Week 1`, `Week 2`, `Week 5` được hỗ trợ. | Dùng maintenance window, notifications và staging cluster theo hướng dẫn AlloyDB. |
| Deny period | Tối đa **90 ngày**, có ràng buộc bản vá quá cũ. | Tối đa **30 ngày**, cần cluster ở maintenance version đủ mới. |
| Update order | Tùy cơ chế maintenance và replica topology. | Theo tài liệu: read pools trước, sau đó primary trong scheduled maintenance. |
| PostgreSQL minor | Managed theo chính sách Cloud SQL. | AlloyDB tự áp minor compatibility updates qua maintenance. |
| Major version | In-place hoặc migration tùy engine/phiên bản. | In-place major upgrade ở cluster hoặc migration sang cluster mới. |

**Deny period không chặn emergency maintenance** và có giới hạn sản phẩm. Không dùng ngưỡng 90 ngày của Cloud SQL cho AlloyDB.

### 4.1. Cấu hình cửa sổ AlloyDB

~~~bash
PROJECT_ID="retail-lab"
REGION="asia-southeast1"
ALLOY_CLUSTER="analytics-db"

# READ-ONLY: xem maintenanceUpdatePolicy và maintenanceSchedule.
gcloud alloydb clusters describe "$ALLOY_CLUSTER" \
  --project="$PROJECT_ID" --region="$REGION" --format=yaml

# WRITE: ưu tiên bắt đầu bảo trì Chủ nhật 02:00 UTC.
gcloud alloydb clusters update "$ALLOY_CLUSTER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --maintenance-window-day=SUNDAY \
  --maintenance-window-hour=2

# READ-ONLY: xác minh cluster đã lưu chính sách.
gcloud alloydb clusters describe "$ALLOY_CLUSTER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(maintenanceUpdatePolicy,maintenanceSchedule)"
~~~

Nếu muốn tránh đợt flash sale bằng AlloyDB deny period, lệnh cập nhật có các tham số `--deny-maintenance-period-start-date`, `--deny-maintenance-period-end-date` và `--deny-maintenance-period-time`. **Không dùng tên biến giả để chạy ở production**; xác nhận giới hạn 30 ngày, maintenance version hiện tại và ý nghĩa UTC trước khi ghi.

### 4.2. Staging cluster và read pools

Thiết kế một **staging cluster tương tự production** về major version, extensions và kiểu workload, để nhận maintenance trước production đủ thời gian kiểm thử. Với scheduled maintenance, AlloyDB có thể cập nhật read pools trước primary, tạo **gián đoạn theo từng loại instance**. Vì vậy:

- Không giả định application đọc qua read pool sẽ liên tục có capacity không đổi.
- Kiểm tra connection retries, read routing, replica lag và fallback phù hợp.
- Theo dõi hiệu suất query, invalid connections, latency và error-rate theo từng endpoint.
- Không coi primary/read pool high availability là bằng chứng **zero-downtime** cho mọi maintenance hoặc major upgrade.

## 5. Chống gián đoạn ở tầng ứng dụng

### 5.1. Kết nối cơ sở dữ liệu là tài nguyên có thể mất

Trong maintenance, failover hoặc engine upgrade, **TCP connections đang mở có thể bị ngắt**. Không một policy IAM hay backup nào ngăn được request đang giữ transaction bị lỗi khi connection mất.

~~~mermaid
flowchart LR
    USER["Client"] --> APP["Cloud Run / GKE app"]
    APP --> POOL["Connection pool"]
    POOL --> DB["Cloud SQL / AlloyDB primary"]
    DB -. "Maintenance / failover" .-> LOST["Connection reset / timeout"]
    LOST --> RECON["Loại bỏ connection lỗi, kết nối lại"]
    RECON --> POOL
    APP --> CHECK["Idempotency + transaction boundaries"]
~~~

Nên có:

1. **Connection pool** có validation/idle timeout/max lifetime hợp lý, phát hiện connection hỏng và không giữ connection mãi.
2. **Connection timeouts** và **statement timeouts** rõ ràng; không treo vô hạn khi backend không sẵn sàng.
3. **Retry có backoff + jitter** chỉ cho lỗi tạm thời và các thao tác **an toàn để thử lại**.
4. **Idempotency key** hoặc transaction/unique constraint cho `POST` tạo đơn, ghi hóa đơn, chuyển tiền.
5. **Circuit breaker/backpressure** để tránh mọi Cloud Run/GKE replica đồng thời retry làm cơ sở dữ liệu quá tải sau recovery.
6. Readiness/liveness probes không khiến hàng nghìn Pods bị restart liên tục vì một đợt DB maintenance ngắn.

**Không retry một transaction đã có side effects chỉ vì client không nhận được response.** Nếu commit có thể đã thành công nhưng kết nối mất trước khi nhận ACK, ứng dụng phải đọc trạng thái theo operation ID hoặc xử lý qua idempotency trước khi ghi lại.

### 5.2. HA, replicas và PITR giải quyết vấn đề khác nhau

| Thành phần | Giúp gì? | Không thay thế được |
| --- | --- | --- |
| **High availability/failover** | Giảm thời gian gián đoạn một số lỗi thành phần. | Ứng dụng reconnect và retry đúng; major upgrade downtime. |
| **Read replica/read pool** | Chia tải đọc, tăng khả năng phục vụ một số loại truy vấn. | Writable primary; không mặc nhiên là mục tiêu write sau lỗi. |
| **Automated backup / PITR** | Khôi phục dữ liệu về điểm trước sự cố trong retention được cấu hình. | RTO tức thì, khôi phục không mất dữ liệu, tự động rollback schema/engine. |
| **Maintenance window** | Chọn thời điểm ít ảnh hưởng hơn. | Cam kết không gián đoạn; tránh bản vá khẩn cấp. |
| **Schema expand-contract** | Cho phép code cũ/mới cùng hoạt động khi rollout. | Không loại bỏ mọi DDL lock và dữ liệu lỗi. |

**RTO** là thời gian phục hồi chấp nhận được; **RPO** là mức dữ liệu có thể mất. Ví dụ RTO 15 phút và RPO 5 phút là **mục tiêu nghiệp vụ minh họa**, không phải bảo đảm mặc định từ Google Cloud. Backup chỉ có giá trị khi đã **diễn tập restore và đo thực tế**.

## 6. Nâng cấp PostgreSQL major version: chuẩn bị và lựa chọn

### 6.1. Minor khác major

PostgreSQL minor updates chủ yếu mang bản vá lỗi/bảo mật, trong khi **major** có thể thay đổi behavior SQL, planner, extensions, flags hoặc defaults. Cloud SQL và AlloyDB có các quy trình, lịch cập nhật minor riêng; **major upgrade cần được lập kế hoạch như change có khả năng gián đoạn**.

Trước major upgrade, kiểm kê:

- Version hiện tại, **target versions thực sự được sản phẩm hỗ trợ** và release lifecycle.
- JDBC/psycopg/ORM versions; ứng dụng Java/Spring Boot, migration tooling và client driver.
- Extensions (`PostGIS`, `pg_stat_statements`, `pglogical`...), chức năng SQL bị loại bỏ hoặc thay defaults.
- Database flags, encoding/collation, roles, privileges, cron jobs, views, triggers và logical replication slots.
- Primary/replicas/read pool topology, replication lag và external CDC/Datastream consumers.
- Thời gian downtime chấp nhận được, chiến lược backup/PITR, điểm dừng phát hành và cutover.

**Không tự đặt target bằng cách tăng một đơn vị version**. Hãy đọc trường `upgradableDatabaseVersions` hoặc lệnh kiểm tra khả năng nâng cấp của dịch vụ. Một số extensions và replication configurations có điều kiện đặc biệt.

### 6.2. In-place hay migration sang hệ thống mới?

| Phương án | Ưu điểm | Rủi ro / khi nào cân nhắc |
| --- | --- | --- |
| **In-place major upgrade** | Giữ tên/địa chỉ và nhiều cấu hình của instance/cluster; ít công việc đổi endpoint. | DB có thể không sẵn sàng; rollback không phải hạ major version tại chỗ. |
| **Migrate sang DB/cluster mới** | Có môi trường chạy song song, kiểm thử trước cutover, quyền chọn downtime. | Đồng bộ dữ liệu, extension/collation, replication, đổi endpoint và chi phí song song. |
| **Export/import** | Đơn giản về khái niệm cho dữ liệu nhỏ hoặc downtime được phép. | Downtime theo export/import; dữ liệu lớn rất chậm, cần đối chiếu toàn vẹn. |
| **Database Migration Service** khi hỗ trợ nguồn/đích | Có thể giảm thời gian cutover khi dùng replication/CDC. | Cần kiểm tra hạn chế DDL, extensions, network, replication slots và lag. |

Đối với hệ thống cần downtime **gần bằng 0**, đánh giá migration/song song và application cutover theo yêu cầu cụ thể; **không tuyên bố in-place major upgrade là zero-downtime**.

### 6.3. Cloud SQL for PostgreSQL: in-place major upgrade

Cloud SQL có quy trình **precheck → pre-upgrade backup → upgrade → post-upgrade backup**. Nó dùng cơ chế phù hợp PostgreSQL, có thể giữ instance ID và địa chỉ, nhưng instance bị **unavailable trong một khoảng thời gian**.

~~~bash
PROJECT_ID="retail-lab"
INSTANCE="orders-db"

# READ-ONLY: xác nhận source version, options được nâng cấp và replicas.
gcloud sql instances describe "$INSTANCE" \
  --project="$PROJECT_ID" --format=yaml

# WRITE, MINH HỌA: chỉ chạy sau precheck, backup và change approval.
# Target enum phải nằm trong upgradableDatabaseVersions của instance.
gcloud sql instances patch "$INSTANCE" \
  --project="$PROJECT_ID" \
  --database-version=POSTGRES_16
~~~

Nếu có replicas, phải đọc **đúng quy trình theo topology**: upgrade từng replica trước primary hoặc dùng lựa chọn **include replicas** mà Cloud SQL hỗ trợ, với hành vi recreation và giới hạn riêng. Không âm thầm đổi version primary khi external replication/CDC consumers chưa sẵn sàng. Với Cloud SQL PostgreSQL, một số quy trình in-place major upgrade **xóa logical replication slots**, nên phải ghi nhận và tái tạo chúng để phục hồi stream sau upgrade theo tài liệu.

**Rollback:** sau khi upgrade thành công, không coi việc chạy lại `--database-version=POSTGRES_15` là thao tác khôi phục. Có thể cần **restore backup trước nâng cấp vào một instance phục hồi mới**, cấu hình lại endpoint/replicas và đánh giá dữ liệu ghi phát sinh sau thời điểm backup. Backup và PITR cần kiểm tra điều kiện phiên bản, target và lịch giữ trước khi dựa vào chúng.

### 6.4. AlloyDB: in-place major upgrade

AlloyDB gắn phiên bản PostgreSQL major với **cluster**, tự cập nhật minor compatibility qua maintenance. In-place major upgrade cần prechecks và có thể ảnh hưởng tới **primary lẫn read pools**. Tài liệu Google Cloud cho biết quá trình nâng toàn cluster có thể mất **từ hàng chục phút đến nhiều giờ**, downtime của primary **thường khoảng 20–60 phút**, phụ thuộc kích thước/schema/topology; không lấy các số này làm SLA cho mọi cluster.

~~~bash
REGION="asia-southeast1"
PROJECT_ID="retail-lab"
CLUSTER="analytics-db"

# READ-ONLY: đọc version, topology và trạng thái cluster.
gcloud alloydb clusters describe "$CLUSTER" \
  --project="$PROJECT_ID" --region="$REGION" --format=yaml

# WRITE, MINH HỌA: target phải là major version được hỗ trợ.
# Không thực thi khi chưa có backup/restore drill, prechecks, approval.
gcloud alloydb clusters upgrade "$CLUSTER" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --version=POSTGRES_16 \
  --async
~~~

Nếu major upgrade đã hoàn tất, **AlloyDB không cho hạ phiên bản ngay trên cluster đó**; đường về phiên bản cũ là **restore backup trước nâng cấp để tạo cluster mới** rồi đổi đường ứng dụng. Trong quá trình nâng cấp có những thời điểm chỉ được cancel có điều kiện; không xem `--async` là chạy nền hoàn toàn an toàn hoặc không gián đoạn. Với hệ thống chỉ chịu được vài phút downtime, cần đánh giá migration thay vì chọn in-place theo thói quen.

### 6.5. Checklist trước và sau major upgrade

**Trước:**

1. Khóa phạm vi thay đổi, có owner/change window và đóng băng các schema migrations không liên quan.
2. Diễn tập trên **bản sao dữ liệu đại diện**, cùng extensions, flags, replica topology và workload query.
3. Xác minh backup thành công, phục hồi được, có số đo RTO/RPO.
4. Kiểm tra target version, driver/ORM, `pg_dump`/restore compatibility và các tính năng bị deprecate.
5. Lập kế hoạch ngắt/khoanh vùng traffic ghi, retry, health probes, migration/CDC slots, fallback endpoint.

**Sau:**

1. Xác minh target engine version và trạng thái primary/replica/read pool.
2. Kiểm thử API end-to-end: tạo đơn, đọc đơn, thanh toán, báo cáo và các queries trọng yếu.
3. Với PostgreSQL, xem xét chạy **`ANALYZE`** để cập nhật thống kê query planner sau major upgrade theo hướng dẫn.
4. Kiểm tra extensions, roles, database flags, logical replication/CDC streams và backup/PITR mới.
5. Theo dõi p95/p99 query latency, locks, CPU/memory, errors, connection pool và chi phí ít nhất trong cửa sổ giám sát đã thống nhất.

## 7. Thay đổi schema không gián đoạn: expand → migrate → contract

### 7.1. Vì sao `ALTER TABLE` vẫn rủi ro trên managed DB?

Cloud SQL/AlloyDB quản lý hạ tầng, **không đảm bảo mọi câu DDL không chặn giao dịch**. Một `ALTER TABLE`, validate constraint, rebuild index hoặc migration dữ liệu lớn có thể:

- Chờ table lock hoặc chặn giao dịch khác.
- Giữ transaction mở quá lâu, tăng replication lag và log/WAL.
- Tạo I/O/CPU pressure, ảnh hưởng SLO checkout.
- Phá revision ứng dụng cũ nếu đổi tên/xóa cột mà code cũ còn dùng.

Trên PostgreSQL, **đừng đánh giá chi phí DDL chỉ bằng số dòng SQL**. Một migration một dòng trên bảng hàng trăm triệu bản ghi có thể có rủi ro lớn hơn nhiều file migration nhỏ.

### 7.2. Chiến lược expand-contract

Giả sử `orders` đang có cột `customer_note` và muốn chuyển dần sang `customer_note_v2`.

~~~mermaid
flowchart LR
    E["1. Expand: thêm cột mới"] --> W["2. Deploy: đọc fallback / dual-write"]
    W --> B["3. Backfill theo batch"]
    B --> V["4. Verify + switch readers"]
    V --> C["5. Contract: bỏ cột cũ sau rollback window"]
~~~

| Giai đoạn | Database | Ứng dụng |
| --- | --- | --- |
| **Expand** | Thêm `customer_note_v2` nullable. | Code cũ tiếp tục chạy bình thường. |
| **Dual write/read fallback** | Hai cột cùng tồn tại. | Code mới ghi cả hai, đọc v2 rồi fallback v1 khi cần. |
| **Backfill** | Cập nhật dữ liệu cũ theo batch có theo dõi. | Cả hai revisions còn tương thích. |
| **Switch** | Kiểm tra count/null, correctness và read replicas. | Chuyển dần đọc v2 theo feature flag/canary. |
| **Contract** | Bỏ cột cũ khi chắc chắn không còn consumer phụ thuộc. | Rollback về code cũ cần được thay bằng phương án có kiểm soát. |

**Thứ tự quan trọng:** thêm cấu trúc mới **trước**, chuyển app dùng nó **sau**, xóa cấu trúc cũ **cuối cùng**. Không dùng một migration `RENAME COLUMN` trực tiếp nếu Cloud Run đang phân phối traffic tới nhiều revisions vẫn dùng tên cũ.

### 7.3. SQL ví dụ cho PostgreSQL

Giả sử bảng `orders(id BIGINT PRIMARY KEY, customer_note TEXT, ...)` đã tồn tại. Chạy trong môi trường lab có dữ liệu thử:

~~~sql
-- WRITE: giai đoạn EXPAND, thêm cột không phá code cũ.
SET lock_timeout = '5s';
SET statement_timeout = '30s';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_note_v2 TEXT;
~~~

Giới hạn timeout giúp giảm khả năng migration chờ lock vô hạn; **không đảm bảo migration tự an toàn**. Ứng dụng mới ghi cả `customer_note` và `customer_note_v2` trong cùng transaction, không tạo logic dual-write tách thành hai HTTP requests.

Ví dụ **một batch backfill**, chạy lặp có kiểm soát đến khi hết dòng:

~~~sql
-- WRITE: tối đa 500 hàng/batch, tránh một UPDATE kéo dài toàn bảng.
WITH batch AS (
  SELECT id
  FROM orders
  WHERE customer_note_v2 IS NULL AND customer_note IS NOT NULL
  ORDER BY id
  LIMIT 500
  FOR UPDATE SKIP LOCKED
)
UPDATE orders AS o
SET customer_note_v2 = o.customer_note
FROM batch
WHERE o.id = batch.id
  AND o.customer_note_v2 IS NULL;
~~~

Để tránh race với giao dịch mới, **dual-write phải được triển khai trước khi backfill**; khi có cập nhật song song, cần quy tắc consistency rõ ràng. Cách dùng `SKIP LOCKED` hỗ trợ chia batch nhưng **không thay thế kiểm chứng dữ liệu**. Theo dõi số hàng được cập nhật, lỗi, thời gian chạy, WAL/replication lag và API p95 trước khi tăng batch size.

Kiểm tra tiến độ:

~~~sql
-- READ-ONLY: số hàng còn cần điền từ cột cũ.
SELECT count(*) AS remaining
FROM orders
WHERE customer_note IS NOT NULL
  AND customer_note_v2 IS NULL;

-- READ-ONLY: thử đối chiếu giá trị đã backfill.
SELECT count(*) AS mismatched
FROM orders
WHERE customer_note IS DISTINCT FROM customer_note_v2;
~~~

`mismatched = 0` **chưa đủ chứng minh migration đúng tất cả luồng nghiệp vụ**; cần test cả create/update, null semantics, consumer đọc cột, index/queries và sampling. Nếu NULL mang ý nghĩa riêng, không tự điền giá trị `UNKNOWN` mà không có quyết định nghiệp vụ.

Khi mọi consumer đã chuyển và thời hạn rollback qua đi, **contract** mới được cân nhắc:

~~~sql
-- DESTRUCTIVE: CHỈ chạy sau approval, backup và xác minh không còn dependency.
ALTER TABLE orders DROP COLUMN customer_note;
~~~

**Xóa cột có thể làm rollback code cũ thất bại ngay.** Đây không phải thao tác “cleanup” vô hại; phải quản lý như change có rủi ro cao.

### 7.4. Tạo index trên bảng lớn

Với bảng PostgreSQL đang có traffic:

~~~sql
-- WRITE: ví dụ tạo index tránh khóa ghi kéo dài.
-- CREATE INDEX CONCURRENTLY PHẢI chạy ngoài explicit transaction block.
CREATE INDEX CONCURRENTLY IF NOT EXISTS
  idx_orders_customer_created
ON orders (customer_id, created_at DESC);
~~~

`CONCURRENTLY` vẫn tốn CPU/I/O, thời gian, WAL và có thể thất bại; nếu lỗi, cần kiểm tra trạng thái index (có thể tồn tại index không hợp lệ) trước khi retry. Flyway/Liquibase hoặc migration runner phải **hỗ trợ bước không nằm trong transaction**. Với constraint lớn, cân nhắc khả năng `NOT VALID`/`VALIDATE CONSTRAINT` của PostgreSQL cho loại constraint hỗ trợ, nhưng không tự áp cho mọi `UNIQUE`/`NOT NULL` case.

## 8. Migration tooling và CI/CD

### 8.1. Một runner chịu trách nhiệm, không phải mọi Pod

Một anti-pattern nguy hiểm là để **mỗi Cloud Run instance/GKE Pod chạy DDL khi start**. Khi rollout 30 replicas, nhiều process có thể cùng tranh migration lock, tăng cold start, phá API availability hoặc khiến deployment rollback không ổn định.

Thiết kế tốt hơn:

~~~text
PR: schema change
   → SQL review + static lint
   → test DB có dữ liệu đại diện
   → tạo/kiểm tra backup & rollback plan
   → CI migration job (một runner có locking)
   → deploy app canary
   → verify + backfill job riêng
   → rollout toàn bộ app
   → contract cleanup ở release sau
~~~

**Flyway/Liquibase** (hoặc công cụ tương tự) giúp quản lý version, checksums và lịch sử migration, nhưng **không bảo đảm mọi migration là transactional/rollbackable**. Với những câu DDL không thể chạy trong transaction, phải cấu hình runner phù hợp và có validation riêng.

### 8.2. Phân quyền và credentials

- **Migration principal** cần quyền DDL/ALTER ở schema cụ thể, không mặc định cấp project Owner hay PostgreSQL superuser.
- **Application runtime principal** thường chỉ cần SELECT/INSERT/UPDATE/DELETE theo bảng/tính năng; không cần quyền thay schema.
- **CI/deployer** cần quyền gọi migration job và quyền `iam.serviceAccounts.actAs` khi liên quan, không được lộ DB password vào pipeline logs.
- Dùng **Secret Manager**, IAM database authentication hoặc phương án xác thực được sản phẩm hỗ trợ; khóa và mật khẩu cần rotation.
- Với private DB endpoint, migration runner phải có **VPC route/Private Service Connect/Private Service Access** theo topology; có IAM mà thiếu đường mạng vẫn không kết nối được.

Nếu Cloud SQL/AlloyDB chứa dữ liệu cá nhân, logs/SQL query text có thể tiết lộ dữ liệu; redaction và log retention cũng là phần của change plan.

## 9. Theo dõi lock và tình trạng migration

### 9.1. Kiểm tra các session kéo dài

Ví dụ truy vấn PostgreSQL read-only (cần quyền xem metadata tương ứng):

~~~sql
SELECT pid, usename, state, wait_event_type, wait_event,
       now() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start ASC
LIMIT 20;
~~~

~~~sql
SELECT l.pid, l.locktype, l.mode, l.granted,
       c.relname AS relation_name
FROM pg_locks AS l
LEFT JOIN pg_class AS c ON c.oid = l.relation
WHERE l.relation IS NOT NULL
ORDER BY l.granted ASC, l.pid
LIMIT 50;
~~~

Kết quả **không trực tiếp chỉ ra chính xác blocker chain**; để phân tích ai chặn ai, có thể dùng `pg_blocking_pids(pid)` và công cụ quan sát chuyên dụng. Không tự `pg_terminate_backend` trên production chỉ vì thấy session lâu; cần xác định transaction của người dùng, backup, DDL và tác động rollback.

### 9.2. Chỉ số cần giám sát trong change window

| Nhóm | Ví dụ tín hiệu | Hành động |
| --- | --- | --- |
| **Availability** | Connection errors, 5xx, downtime, failover event. | Xem routing/reconnect, kích hoạt runbook khi vượt SLO. |
| **Latency** | Query p95/p99, Cloud Run request p95, lock wait. | Dừng/tạm giảm backfill nếu contention tăng. |
| **Capacity** | CPU, memory, disk usage/IOPS, connection count, WAL. | Throttle migration, pool sizing, kiểm tra quota. |
| **Replication** | Replica/read pool health và lag. | Không switch read traffic khi data chưa bắt kịp. |
| **Correctness** | Rows migrated, mismatch count, app business invariants. | Chặn contract phase nếu còn sai. |
| **Recovery** | Backup status, PITR window, restore test duration. | Không bắt đầu major upgrade nếu chưa có đường phục hồi tin cậy. |
| **Cost** | Thời gian DB song song, backup/storage, logs, network transfer. | Dự toán và cảnh báo ngân sách. |

**Một migration nhanh không nhất thiết tốt nếu p99 checkout tăng mạnh.** Đo cả business SLI, không chỉ thời gian chạy câu DDL.

## 10. Tình huống sản xuất: hệ thống bán lẻ

### 10.1. Mục tiêu

- `orders-db`: Cloud SQL for PostgreSQL primary/HA phục vụ checkout; read replica cho reporting.
- `analytics-db`: AlloyDB primary và read pool cho phân tích.
- Cloud Run chạy `orders-api`, GKE chạy worker hóa đơn.
- Đội muốn thêm cột `customer_note_v2` và lên lịch engine upgrade tránh giờ bán hàng cao điểm.
- SLO checkout: **99,95% availability** (giả định) với p95 nhỏ hơn 300 ms; mọi thay đổi phải đo và rollback được theo giai đoạn.

### 10.2. Kế hoạch thay đổi an toàn

| Thời điểm | Công việc | Điều kiện chuyển tiếp |
| --- | --- | --- |
| **T-14 ngày** | Kiểm kê engine versions, extension, replication/CDC, lịch maintenance và workload. | Có owner, change ticket, rollback plan. |
| **T-10 ngày** | Khôi phục backup lên lab/staging; chạy migration và load test. | Data correctness và p95 ổn định. |
| **T-7 ngày** | Cấu hình maintenance notifications, xác nhận cửa sổ ít traffic. | Có SRE trực và cảnh báo hoạt động. |
| **T-3 ngày** | Expand schema, deploy code dual-write/read-fallback. | Code cũ/mới đều hoạt động. |
| **T-2 ngày** | Backfill có giới hạn, đo WAL/locks/replica lag. | Mismatch được xử lý, không vi phạm SLO. |
| **T-1 ngày** | Switch readers, test nghiệp vụ và rollback code. | Không còn consumer phụ thuộc cột cũ khi contract sau này. |
| **Ngày nâng engine** | Thực hiện **major upgrade riêng**, không ghép với nhiều DDL phá tương thích. | Backup/restore plan, maintenance window và monitoring đạt. |
| **Sau ổn định** | `ANALYZE`, acceptance tests, review lag/CDC, đóng incident/change. | Không còn lỗi và thông số chi phí chấp nhận. |

Đây là **lịch minh họa**, không phải thời gian bảo trì sản phẩm cam kết. Tách rollout schema và major engine upgrade thành **hai change độc lập** giúp khoanh vùng nguyên nhân khi lỗi.

### 10.3. Kịch bản “code đã lên nhưng migration bị kẹt lock”

Giả sử DDL `ALTER TABLE` đang chờ lock trong giờ cao điểm:

1. **Ngừng deploy thêm** và ghi nhận migration ID/SQL, thời gian bắt đầu.
2. Xem `pg_stat_activity`, `pg_locks`, `pg_blocking_pids`, ảnh hưởng API 5xx/p95.
3. Nếu mới chỉ **expand cột nullable**, ưu tiên hủy migration an toàn hoặc giảm traffic theo kế hoạch thay vì kill tất cả sessions.
4. Trả ứng dụng về revision tương thích (nếu cần); **không chạy DROP COLUMN** trong incident.
5. Lên lịch thử lại off-peak với timeout, batch/DDL strategy điều chỉnh.

### 10.4. Kịch bản “major upgrade xong nhưng JDBC lỗi”

Nếu DB major upgrade đã thành công nhưng Java driver/SQL query báo lỗi:

- Kiểm tra phiên bản driver và behavior/defaults của PostgreSQL mới.
- Chặn hoặc giảm traffic theo runbook; thử bản app đã tương thích.
- Nếu không thể phục hồi nhanh, đánh giá **restore pre-upgrade backup vào instance/cluster mới** và chuyển endpoint qua proxy/config có kiểm soát.
- Ghi nhận **các writes sau thời điểm backup**; không giả định restore về phiên bản cũ giữ nguyên mọi giao dịch mới.

**Đường quay lại engine cũ khác hoàn toàn rollback một Kubernetes Deployment.** Không bao giờ thử downgrade in-place khi dịch vụ không hỗ trợ.

## 11. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| `connection reset` trong maintenance | Kết nối bị cắt khi chuyển đổi thành phần. | Logs, connection pool, retry/idempotency, maintenance event. |
| App 5xx tăng nhưng DB đã READY | Pool chứa stale connections, DNS/route hoặc read replica lag. | Pool metrics, DB connections, endpoints, replica status. |
| Không đặt được Cloud SQL deny period | Maintenance version quá cũ, độ dài/format không hợp lệ. | Describe maintenance version, giới hạn 90 ngày và yêu cầu cập nhật. |
| AlloyDB deny 60 ngày bị từ chối | AlloyDB giới hạn tối đa 30 ngày hoặc version không đủ mới. | Cluster maintenance policy/docs. |
| Cloud SQL major upgrade precheck fail | Unsupported extension/flags, replication/objects không tương thích. | `upgradableDatabaseVersions`, upgrade logs, checklist. |
| AlloyDB major upgrade mất nhiều thời gian | Dữ liệu/schema/read pools lớn; precheck hoặc upgrade phases. | Upgrade status, Cloud Logging, guidance theo topology. |
| Sau major upgrade query chậm | Planner statistics cũ, flag/default đổi, index/extension khác. | `ANALYZE`, `EXPLAIN (ANALYZE, BUFFERS)` trên môi trường an toàn, metrics. |
| Migration chờ hàng phút | DDL lock và long-running transactions. | `pg_stat_activity`, `pg_locks`, blocker chain; `lock_timeout`. |
| App revision cũ lỗi `column does not exist` | Đã DROP/RENAME trước khi tất cả consumer được chuyển. | Schema history, rollout revisions, rollback compatibility. |
| `CREATE INDEX CONCURRENTLY` thất bại | Chạy trong transaction, thiếu dung lượng hoặc conflict/timeout. | Runner config, index validity, logs; không retry mù. |
| Replica/CDC không theo kịp | WAL tăng do backfill, logical slot hoặc topology sau upgrade. | Replication lag, slots, worker throughput. |
| Rollback code không sửa được lỗi | Schema đã phá tương thích hoặc engine đã nâng major. | Xác định điểm không thể đảo, backup/recovery plan. |

## 12. Bài tập

### Bài 1 — Phân loại thay đổi

Phân loại bốn thao tác sau: (a) Cloud SQL nhận maintenance patch; (b) PostgreSQL 15 → 16; (c) thêm index ở bảng `orders`; (d) Java JDBC driver nâng phiên bản. Với thao tác nào có thể có downtime? Loại nào nằm ngoài `maintenance window` của Cloud SQL?

### Bài 2 — Maintenance window và timezone

Đội checkout muốn bảo trì lúc **02:00 sáng Chủ nhật giờ Việt Nam**. Với `gcloud` cấu hình UTC, ngày và giờ tương ứng là gì? Hãy phân biệt `Week 1` và `Week 2` của Cloud SQL, rồi giải thích vì sao không nên nhận bản vá lần đầu ở production.

**Gợi ý:** 02:00 Chủ nhật ICT = **19:00 UTC thứ Bảy**, không phải 02:00 UTC Chủ nhật.

### Bài 3 — Deny period

Một nhóm muốn tránh bảo trì 45 ngày trong mùa cao điểm trên Cloud SQL và AlloyDB. Có thể dùng cùng cấu hình cho cả hai không? Nêu giới hạn 90/30 ngày, yêu cầu version và rủi ro hoãn bản vá.

### Bài 4 — Reconnect và idempotency

Cloud SQL rớt kết nối sau khi transaction tạo đơn **có thể đã commit**, nhưng trước khi ứng dụng nhận confirmation. Client retry `POST /orders`. Hãy mô tả operation ID, unique constraint, truy vấn trạng thái trước retry và backoff để không tạo hai đơn.

### Bài 5 — Major upgrade

Một Cloud SQL PostgreSQL 15 có read replicas và Datastream logical replication. Hãy lập checklist precheck, backup, extension/slot, upgrade order, read replica lag và xác nhận sau nâng lên version được hỗ trợ. Vì sao rollback không phải patch ngược database version?

### Bài 6 — Expand-contract

Bảng `orders` có 100 triệu hàng, phiên bản ứng dụng cũ đọc `customer_note`. Hãy thiết kế các bước đưa `customer_note_v2` vào sử dụng, trình bày dual-write, backfill batch, kiểm thử mismatch và thời điểm an toàn để bỏ cột cũ.

### Bài 7 — `CREATE INDEX CONCURRENTLY`

Vì sao nên cân nhắc `CREATE INDEX CONCURRENTLY` trên bảng PostgreSQL đang có traffic? Nó có thể chạy trong transaction block không? Khi thất bại, vì sao không nên retry vô điều kiện?

### Bài 8 — Runbook và SLO

Một AlloyDB primary/read pool chuẩn bị nâng major version. SLO cho phép outage write tối đa 5 phút, nhưng thử nghiệm staging mất 30 phút. Bạn có nên dùng in-place upgrade trên production không? Hãy đề xuất cách lựa chọn migration song song, cửa sổ thay đổi, kết nối ứng dụng và kế hoạch khôi phục.

## 13. Checklist production và tài liệu chính thức

| Hạng mục | Điều phải xác minh |
| --- | --- |
| **Maintenance** | Đúng product/instance/cluster, UTC window, rollout timing, notifications, deny period hợp lệ. |
| **Version** | Engine major/minor hiện tại, target hỗ trợ, extensions, flags, drivers, replication/CDC. |
| **Availability** | HA/read pools, connection pool, timeout, reconnect, retry + idempotency, SLO. |
| **Backup** | Automated/on-demand backup và PITR đúng scope, đã thử restore và đo RTO/RPO. |
| **Schema** | Expand-contract, SQL review, migration locks, backfill/validation, không DROP sớm. |
| **Release** | One migration runner, schema history, IaC/change approval, canary và fallback app revision. |
| **IAM/network** | Migration principal tối thiểu, runtime SA riêng, VPC/PSC/PSA route, secrets an toàn. |
| **Observability** | DB connections, locks, replica lag, CPU/IO, application 5xx/p95, audit/change logs. |
| **Recovery** | Biết bước nào rollback code được, bước nào cần restore DB mới và chuyển endpoint. |
| **Cost** | Staging/parallel instances, backups, storage/WAL, replicas, logging và downtime. |

Tài liệu chính thức để đối chiếu điều kiện/giới hạn theo phiên bản và edition:

- [Cloud SQL for PostgreSQL — Maintenance overview](https://cloud.google.com/sql/docs/postgres/maintenance)
- [Cloud SQL — View and set maintenance windows](https://cloud.google.com/sql/docs/postgres/set-maintenance-window)
- [Cloud SQL — Self-service maintenance](https://cloud.google.com/sql/docs/postgres/self-service-maintenance)
- [Cloud SQL — Major version upgrade in-place](https://cloud.google.com/sql/docs/postgres/upgrade-major-db-version-inplace)
- [Cloud SQL — Major upgrade by migration](https://cloud.google.com/sql/docs/postgres/upgrade-major-db-version-migrate)
- [Cloud SQL — Back up and recover](https://cloud.google.com/sql/docs/postgres/backup-recovery/backup-options)
- [AlloyDB — Maintenance overview](https://cloud.google.com/alloydb/docs/maintenance)
- [AlloyDB — Maintenance windows and deny periods](https://cloud.google.com/alloydb/docs/maintenance-windows)
- [AlloyDB — Database version policies](https://cloud.google.com/alloydb/docs/db-version-policies)
- [AlloyDB — Major version upgrade overview](https://cloud.google.com/alloydb/docs/major-version-upgrade-inplace-overview)
- [AlloyDB — Perform major version upgrade](https://cloud.google.com/alloydb/docs/upgrade-db-inplace-major-version)
- [AlloyDB — Backups and PITR](https://cloud.google.com/alloydb/docs/backup/overview)
- [PostgreSQL — Explicit locking](https://www.postgresql.org/docs/current/explicit-locking.html)
- [PostgreSQL — CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html)

**Ghi nhớ:** **Maintenance** là bản cập nhật do nền tảng quản lý nhưng ứng dụng vẫn phải chịu được kết nối gián đoạn; **major engine upgrade** cần kiểm thử và kế hoạch phục hồi riêng; **schema migration** cần giữ tương thích giữa các revisions, kiểm soát DDL locks và backfill theo batch. Với Cloud SQL và AlloyDB, đừng đánh đồng HA với zero downtime hoặc rollback code với downgrade database. Mục tiêu là **nâng cấp có thể kiểm chứng, phục hồi có diễn tập và không vượt SLO lẫn ngân sách**.
