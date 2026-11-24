# Phân biệt cơ sở dữ liệu phục vụ giao dịch và kho phân tích BigQuery

## Mục tiêu học tập

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, Spring Boot tích hợp các dịch vụ managed của AWS, Azure và Google Cloud để lưu trữ dữ liệu, xử lý messaging, phân tích và bảo vệ quyền truy cập. Trên Google Cloud, một quyết định kiến trúc quan trọng là chọn nơi ghi nhận giao dịch nghiệp vụ và nơi phân tích dữ liệu phát sinh từ những giao dịch đó.

Bài học giúp bạn phân biệt **cơ sở dữ liệu giao dịch (OLTP)** với **kho dữ liệu phân tích (OLAP/data warehouse)**, hiểu vị trí của BigQuery và thiết kế kiến trúc kết hợp:

1. Phân biệt mục tiêu, access pattern và đặc tính của OLTP với OLAP.
2. Chọn Cloud SQL, Spanner hoặc Firestore cho dữ liệu vận hành theo mô hình nghiệp vụ.
3. Hiểu BigQuery tối ưu cho quét dữ liệu, tổng hợp, join và phân tích quy mô lớn.
4. Hiểu vì sao BigQuery có ACID transaction nhưng vẫn không phải lựa chọn mặc định cho checkout hoặc CRUD từng bản ghi.
5. Thiết kế luồng dữ liệu từ cơ sở dữ liệu giao dịch sang BigQuery bằng batch, CDC hoặc event streaming.
6. Xác định source of truth, data freshness, event ordering, idempotency và cách xử lý dữ liệu đến muộn.
7. Tổ chức raw, curated và mart layer; chọn partition, clustering và schema phân tích.
8. Tích hợp Spring Boot với database vận hành và BigQuery theo đúng ranh giới trách nhiệm.
9. Kiểm soát chi phí, quyền truy cập, chất lượng dữ liệu và khả năng đối soát.
10. Lựa chọn kiến trúc theo yêu cầu latency, consistency, scale và chi phí.

## 1. Hai loại workload, hai mục tiêu thiết kế

### 1.1. OLTP là gì?

OLTP (Online Transaction Processing) phục vụ các thao tác nghiệp vụ diễn ra trong ứng dụng: tạo đơn, xác nhận thanh toán, cập nhật tồn kho, đăng nhập, thay đổi hồ sơ hoặc đặt chỗ.

Một request OLTP thường:

- Đọc một số bản ghi theo khóa chính hoặc index.
- Kiểm tra điều kiện nghiệp vụ.
- Ghi một số bản ghi liên quan.
- Commit hoặc rollback thành một transaction.
- Trả kết quả cho người dùng trong thời gian ngắn.

Ví dụ khi khách đặt một tài sản cho thuê, hệ thống phải kiểm tra lịch trống, giữ chỗ, tạo reservation và ghi nhận trạng thái thanh toán. Nếu hai khách cùng đặt một khoảng thời gian, hệ thống cần kiểm soát cạnh tranh để không xác nhận hai reservation xung đột.

Cơ sở dữ liệu OLTP được thiết kế để xử lý nhiều request đồng thời, truy cập theo key, cập nhật nhỏ và transaction có ranh giới rõ ràng.

### 1.2. OLAP là gì?

OLAP (Online Analytical Processing) phục vụ phân tích và hỗ trợ quyết định. Người dùng thường đặt câu hỏi trên một lượng dữ liệu lớn:

- Doanh thu theo tháng, vùng hoặc nhóm khách hàng.
- Tỷ lệ hủy đơn theo kênh tiếp thị.
- Thời gian trung bình từ đặt chỗ đến xác nhận.
- Tồn kho và mức sử dụng theo mùa.
- Phân tích cohort, funnel và hành vi theo thời gian.
- Phát hiện xu hướng hoặc bất thường trên lịch sử nhiều tháng/năm.

Một truy vấn OLAP có thể đọc hàng triệu hoặc hàng tỷ dòng, join nhiều tập dữ liệu, group, aggregate và dùng window function. Kết quả thường là một bảng tổng hợp nhỏ hơn nhiều so với dữ liệu đầu vào.

BigQuery được thiết kế cho kiểu truy vấn này: lưu trữ dạng columnar, tách compute khỏi storage và phân phối công việc truy vấn trên nhiều worker. [Tài liệu BigQuery mô tả kiến trúc storage/compute và xử lý song song](https://docs.cloud.google.com/bigquery/docs/introduction).

### 1.3. So sánh OLTP và OLAP

| Tiêu chí | OLTP | OLAP |
| --- | --- | --- |
| Mục tiêu | Thực hiện giao dịch nghiệp vụ | Phân tích và tổng hợp |
| Đơn vị truy cập | Một vài row/document theo key | Nhiều row và nhiều cột |
| Đọc/ghi | Đọc và ghi nhỏ, thường xuyên | Đọc rộng, tổng hợp; ingestion theo lô hoặc stream |
| Transaction | Rất quan trọng với từng nghiệp vụ | Có thể dùng transaction cho thao tác dữ liệu phân tích, nhưng không tối ưu cho CRUD từng row |
| Schema | Thường chuẩn hóa theo quan hệ nghiệp vụ | Thường denormalize theo câu hỏi phân tích |
| Index/partition | Index phục vụ lookup và update | Partition, clustering, column pruning |
| Latency mong muốn | Phản hồi nhanh cho request người dùng | Từ giây đến phút tùy truy vấn và SLA |
| Concurrency | Nhiều giao dịch ngắn, cạnh tranh trên dữ liệu | Nhiều query phân tích song song và có thể được xếp hàng |
| Người dùng | Backend service, ứng dụng nghiệp vụ | Analyst, BI, data scientist, báo cáo |
| Ví dụ | Tạo reservation, trừ tồn kho | Doanh thu theo tháng, occupancy rate |

Không có quy tắc rằng OLTP chỉ có vài dòng hoặc OLAP chỉ đọc. Điểm khác biệt là access pattern và mục tiêu tối ưu. Một báo cáo có thể đọc ít dòng nhưng vẫn là OLAP; một transaction có thể ghi nhiều bảng nhưng vẫn là OLTP.

### 1.4. Ví dụ cùng một nghiệp vụ nhìn từ hai workload

Giả sử ứng dụng quản lý đơn đặt chỗ:

**OLTP request:** khách xác nhận reservation R-1001.

1. Đọc reservation theo ID.
2. Kiểm tra trạng thái hiện tại là PENDING.
3. Kiểm tra điều kiện thanh toán.
4. Cập nhật reservation thành CONFIRMED.
5. Ghi payment reference và outbox event.
6. Commit transaction rồi trả kết quả.

**OLAP query:** nhà quản lý muốn xem tỷ lệ xác nhận theo tháng trong 24 tháng.

1. Đọc lịch sử hàng triệu reservation.
2. Nhóm theo tháng và kênh đặt chỗ.
3. Đếm số reservation và số reservation được xác nhận.
4. Tính tỷ lệ và so sánh xu hướng.
5. Trả bảng kết quả cho dashboard.

Nếu đưa truy vấn phân tích này vào database vận hành, nó có thể cạnh tranh CPU, I/O, memory và connection với request checkout. Nếu dùng BigQuery để cập nhật trạng thái từng reservation trong request, bạn đang dùng kho phân tích cho access pattern mà nó không được tối ưu.

## 2. BigQuery là kho phân tích, không phải database checkout

### 2.1. BigQuery tối ưu điều gì?

BigQuery là data warehouse được quản lý, dùng GoogleSQL để phân tích dữ liệu lớn. Một số đặc điểm kiến trúc:

- **Columnar storage:** query chỉ cần một số cột có thể đọc các cột đó thay vì toàn bộ row.
- **Tách storage và compute:** dung lượng lưu trữ và tài nguyên truy vấn có thể mở rộng độc lập.
- **Distributed query execution:** công việc quét, join và aggregate được chia cho nhiều worker.
- **Serverless operations:** người dùng không phải tự provision máy database hoặc shard query cluster.
- **Analytics ecosystem:** tích hợp BI, machine learning, geospatial analytics, external tables và data pipelines.

Các đặc tính này giúp BigQuery xử lý phân tích quy mô lớn hiệu quả. [BigQuery storage dùng định dạng columnar và hỗ trợ query analytics](https://docs.cloud.google.com/bigquery/docs/best-practices-storage).

### 2.2. Vì sao BigQuery không phải lựa chọn mặc định cho OLTP?

Một ứng dụng checkout cần đọc/ghi một bản ghi theo ID và hoàn thành transaction ngắn. BigQuery tập trung vào việc đọc và xử lý tập dữ liệu lớn. Một số khác biệt thực tế:

- Mỗi query được thực thi như một query job; không nên tạo một query job cho mỗi thao tác cập nhật đơn lẻ trong đường request có latency nghiêm ngặt.
- DML như UPDATE, DELETE và MERGE được hỗ trợ, nhưng thiết kế DML theo batch/tập dữ liệu phù hợp hơn thao tác cập nhật một row liên tục.
- Transaction có thể giữ lock trên table khi thực hiện mutating DML; cạnh tranh cập nhật cùng table có giới hạn riêng.
- Chi phí query có thể phụ thuộc lượng dữ liệu được đọc hoặc compute capacity đã cấp.
- BigQuery không thay thế cơ chế ràng buộc nghiệp vụ và transaction boundary của database vận hành.

Google khuyến nghị tránh DML cập nhật hoặc chèn từng row vì đó là cách dùng BigQuery như hệ thống OLTP; nên batch các thay đổi hoặc dùng database được thiết kế cho OLTP. [Best practices về hiệu năng truy vấn](https://docs.cloud.google.com/bigquery/docs/best-practices-performance-compute).

### 2.3. BigQuery vẫn có transaction ACID

Cần tránh hiểu sai rằng BigQuery hoàn toàn không có transaction. BigQuery hỗ trợ:

- Một câu DML có implicit transaction: thay đổi được commit khi statement thành công.
- Multi-statement transaction với BEGIN TRANSACTION, COMMIT TRANSACTION và ROLLBACK TRANSACTION.
- Atomic mutation trên nhiều table trong phạm vi transaction.
- Snapshot isolation cho các thao tác được hỗ trợ.

Ví dụ cập nhật một bảng tổng hợp và ghi audit record trong cùng transaction phân tích:

~~~sql
BEGIN TRANSACTION;

UPDATE analytics.mart.monthly_revenue
SET reviewed = TRUE
WHERE month_key = DATE '2026-10-01';

INSERT INTO analytics.audit.review_log
    (month_key, action, reviewed_at)
VALUES
    (DATE '2026-10-01', 'REVIEWED', CURRENT_TIMESTAMP());

COMMIT TRANSACTION;
~~~

Transaction này phù hợp với một tác vụ xử lý dữ liệu hoặc hiệu chỉnh dữ liệu phân tích. Nó không biến BigQuery thành nơi xử lý từng request checkout.

Một số giới hạn quan trọng của multi-statement transaction:

- Transaction phải nằm trong một query, trừ trường hợp sử dụng session mode.
- Transaction không được lồng nhau.
- DDL tác động đến entity vĩnh viễn như tạo/xóa table không được hỗ trợ bên trong transaction.
- Khi transaction mutates (update/delete) một table, BigQuery dùng lock cấp table; các mutating transaction khác trên cùng table có thể bị hủy.
- Multi-statement transaction có giới hạn concurrency thấp hơn DML statement độc lập.
- Transaction có giới hạn về số table được mutate và partition modifications.

Vì vậy, hãy dùng transaction BigQuery cho tác vụ xử lý dữ liệu phân tích có ranh giới rõ ràng; đừng lấy nó thay cho transaction ngắn, tần suất cao của ứng dụng. [Chi tiết transaction và concurrency](https://docs.cloud.google.com/bigquery/docs/transactions).

### 2.4. Một số hiểu nhầm thường gặp

| Nhận định | Đánh giá |
| --- | --- |
| BigQuery không hỗ trợ transaction | Sai: hỗ trợ ACID transaction cho các thao tác được quy định |
| Có ACID nên có thể dùng BigQuery làm database checkout | Sai: ACID không đồng nghĩa phù hợp với point update và latency OLTP |
| DML có thể cập nhật row nên dùng thay Cloud SQL | Sai: DML tối ưu cho thay đổi theo tập và có giới hạn concurrency |
| BigQuery chỉ lưu dữ liệu batch cũ | Sai: có Storage Write API, CDC và streaming analytics |
| Dữ liệu ghi vào BigQuery luôn đồng bộ ngay với database nguồn | Sai: freshness phụ thuộc load/CDC/streaming pipeline và cấu hình |
| BigQuery chỉ dùng cho dashboard | Sai: còn dùng cho ELT, ML, geospatial, data sharing và phân tích ad hoc |

## 3. Chọn database vận hành trên Google Cloud

BigQuery là đích phân tích; ứng dụng vẫn cần một hệ thống ghi nhận trạng thái nghiệp vụ. Lựa chọn OLTP phụ thuộc mô hình dữ liệu, consistency, transaction, scale và access pattern.

### 3.1. Cloud SQL

Cloud SQL là dịch vụ relational database managed cho PostgreSQL, MySQL và SQL Server.

Phù hợp khi:
- Ứng dụng có mô hình quan hệ, foreign key và SQL quen thuộc.
- Transaction nghiệp vụ cần ACID.
- Workload có quy mô vùng hoặc khu vực và phù hợp với khả năng mở rộng của Cloud SQL.
- Hệ thống đang dùng PostgreSQL/MySQL/SQL Server và muốn giảm công việc vận hành database.

Ví dụ: reservation, payment, customer profile, invoice và inventory với quan hệ rõ ràng.

[Cloud SQL là dịch vụ relational database managed](https://docs.cloud.google.com/sql/docs/introduction).

### 3.2. Spanner

Spanner là relational database phân tán, hỗ trợ transaction mạnh và scale ngang cho workload cần tính sẵn sàng và nhất quán trên phạm vi rộng.

Phù hợp khi:
- Ứng dụng cần relational model và transaction ACID.
- Khối lượng giao dịch hoặc quy mô phân tán vượt mô hình database vùng thông thường.
- Cần strong/external consistency trên các replica phân tán.
- Hệ thống có yêu cầu availability và scale toàn cầu.

Spanner có transaction read-write và read-only; mức đảm bảo consistency mạnh giúp ứng dụng xây dựng logic nghiệp vụ phân tán. Đổi lại, kiến trúc, schema và key design cần được thiết kế theo đặc tính của Spanner. [Spanner transaction và external consistency](https://docs.cloud.google.com/spanner/docs/transactions).

### 3.3. Firestore

Firestore là document database NoSQL managed. Nó phù hợp với:
- Dữ liệu document linh hoạt.
- Ứng dụng mobile/web cần realtime listener và offline support.
- Hồ sơ người dùng, trạng thái ứng dụng, nội dung hoặc dữ liệu có cấu trúc lồng nhau.
- Workload có query pattern phù hợp với document model và index của Firestore.

Firestore hỗ trợ ACID transaction trên nhiều document. Tuy nhiên, mô hình collection/document và cách query khác relational database; không chọn chỉ vì muốn tránh schema SQL. [Firestore overview và transaction capabilities](https://docs.cloud.google.com/firestore/native/docs/overview).

### 3.4. Bigtable và các lựa chọn chuyên biệt

Cloud Bigtable phù hợp với workload key-based, throughput lớn, dữ liệu time-series hoặc wide-column. Nó không phải lựa chọn thay thế trực tiếp cho relational transaction database hoặc BigQuery warehouse.

Memorystore phù hợp làm cache/in-memory data store cho dữ liệu cần truy cập rất nhanh, không phải source of truth duy nhất cho giao dịch quan trọng.

### 3.5. Bảng lựa chọn

| Dịch vụ | Mô hình | Workload chính | Khi nên cân nhắc |
| --- | --- | --- | --- |
| Cloud SQL | Relational | OLTP | Ứng dụng SQL truyền thống, transaction vùng |
| Spanner | Relational phân tán | OLTP quy mô lớn | Cần consistency mạnh và scale phân tán |
| Firestore | Document NoSQL | OLTP/document | Backend mobile/web, document và realtime |
| Bigtable | Wide-column | Operational data/throughput cao | Key lookup, time-series, dữ liệu rất lớn |
| BigQuery | Columnar warehouse | OLAP | Báo cáo, tổng hợp, BI, ML và phân tích lịch sử |

Đây không phải bảng xếp hạng. Một hệ thống có thể dùng nhiều dịch vụ cùng lúc nếu mỗi dịch vụ giữ đúng vai trò.

## 4. Kiến trúc kết hợp OLTP và BigQuery

### 4.1. Luồng dữ liệu tổng quát

Ứng dụng ghi giao dịch vào database vận hành. Dữ liệu được chuyển sang BigQuery qua CDC, event streaming hoặc batch ingestion. BigQuery giữ dữ liệu phục vụ phân tích; dashboard và analyst truy vấn dữ liệu này.

~~~mermaid
flowchart TD
    USER["Web / Mobile / Partner API"] --> API["Spring Boot services"]
    API --> OLTP["OLTP database<br/>Cloud SQL / Spanner / Firestore"]
    API --> OUTBOX["Outbox event in same OLTP transaction"]
    OUTBOX --> PUB["Pub/Sub"]
    PUB --> FLOW["Dataflow / streaming transform"]
    OLTP --> CDC["Datastream CDC"]
    CDC --> RAW["BigQuery raw / replicated tables"]
    FLOW --> RAW
    RAW --> CURATED["Curated analytical tables"]
    CURATED --> MART["Data marts / aggregate tables"]
    MART --> BI["Looker / dashboards / analyst"]
    CURATED --> APIQ["Analytics API / scheduled reports"]
~~~

Các nguyên tắc:

1. Database vận hành là nơi ghi nhận trạng thái nghiệp vụ chuẩn.
2. BigQuery là nơi phân tích dữ liệu đã được chuyển và chuẩn hóa.
3. Luồng chuyển dữ liệu phải có retry, quan sát và cơ chế xử lý duplicate.
4. Dashboard chấp nhận freshness theo SLA đã thống nhất.
5. Không yêu cầu một transaction Spring duy nhất commit đồng thời trên Cloud SQL và BigQuery.

### 4.2. Tách command path và analytics path

**Command path** xử lý hành động làm thay đổi trạng thái:
- Tạo reservation.
- Xác nhận thanh toán.
- Hủy đơn.
- Trừ tồn kho.
- Kiểm tra điều kiện và commit transaction.

**Analytics path** xử lý câu hỏi:
- Tỷ lệ reservation thành công.
- Doanh thu theo ngày.
- Mức sử dụng theo vùng.
- Phân tích cohort.
- Dự báo nhu cầu.

Không để truy vấn dashboard quét hàng tỷ dòng chạy trên connection pool của database vận hành. Không để API checkout phụ thuộc vào việc BigQuery query job hoàn tất.

### 4.3. Source of truth và bản sao phân tích

Với mỗi entity nghiệp vụ, cần xác định hệ thống nào là source of truth. Ví dụ:

| Dữ liệu | Source of truth | Bản sao phân tích |
| --- | --- | --- |
| Reservation status | Cloud SQL hoặc Spanner | BigQuery reservation fact |
| Payment status | Payment service/OLTP database | BigQuery payment events |
| Customer profile | Database vận hành | BigQuery customer dimension |
| Inventory availability | Database vận hành | BigQuery inventory snapshot/history |
| Clickstream | Event pipeline/Pub/Sub | BigQuery event fact |

Nếu BigQuery chưa nhận được một thay đổi, trạng thái checkout vẫn phải được quyết định từ database vận hành. Không đọc bản sao BigQuery để kiểm tra tồn kho hoặc xác nhận thanh toán ngay sau khi commit.

### 4.4. Không dual-write trực tiếp vào hai hệ thống

Một anti-pattern là:

1. Spring service commit transaction vào Cloud SQL.
2. Spring service ghi thêm một row vào BigQuery.
3. Trả response thành công nếu cả hai lệnh thành công.

Nếu bước 1 thành công nhưng bước 2 thất bại, hệ thống có trạng thái giao dịch đã commit nhưng analytics bị thiếu. Nếu bước 2 thành công rồi bước 1 rollback, BigQuery có dữ liệu không có trong source of truth. Hai hệ thống không tham gia chung một transaction manager mặc định.

Giải pháp phù hợp hơn:
- Transactional outbox.
- CDC từ transaction log.
- Event-driven pipeline với idempotency.
- Batch extract/load có watermark và đối soát.

Đây là cách biến cập nhật phân tích thành một luồng bất đồng bộ có thể retry và kiểm tra.

## 5. Chuyển dữ liệu bằng Transactional Outbox và Pub/Sub

### 5.1. Transactional Outbox là gì?

Transactional outbox ghi dữ liệu nghiệp vụ và event cần phát vào cùng một database transaction. Một publisher riêng đọc outbox rồi gửi event đến Pub/Sub.

Nếu transaction nghiệp vụ rollback, outbox event cũng rollback. Nếu transaction commit, cả dữ liệu nghiệp vụ và event record đều tồn tại để publisher gửi sau.

### 5.2. Ví dụ Spring Boot với Spring Data JPA

Giả sử service dùng Cloud SQL PostgreSQL và Spring Data JPA. Hai repository phải dùng cùng datasource và cùng transaction manager:

~~~java
@Service
public class ReservationService {

    private final ReservationRepository reservations;
    private final OutboxEventRepository outbox;

    public ReservationService(
            ReservationRepository reservations,
            OutboxEventRepository outbox) {
        this.reservations = reservations;
        this.outbox = outbox;
    }

    @Transactional
    public Reservation confirm(UUID reservationId) {
        Reservation reservation = reservations.findById(reservationId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Reservation not found"));

        reservation.confirm();

        OutboxEvent event = OutboxEvent.create(
                UUID.randomUUID(),
                "ReservationConfirmed",
                reservation.getId().toString(),
                reservation.toAnalyticsPayload());

        outbox.save(event);
        return reservations.save(reservation);
    }
}
~~~

Trong cùng transaction, service cập nhật reservation và ghi outbox event. Nếu có lỗi trước commit, cả hai thay đổi đều rollback.

toAnalyticsPayload() nên tạo event contract ổn định, không serialize toàn bộ JPA entity có thể chứa lazy relation, dữ liệu nhạy cảm hoặc field nội bộ.

### 5.3. Publisher và duplicate delivery

Một publisher định kỳ hoặc worker riêng:
1. Đọc outbox event chưa publish.
2. Gửi message tới Pub/Sub.
3. Chờ broker xác nhận.
4. Đánh dấu event đã publish.
5. Retry khi lỗi tạm thời.

Có một cửa sổ lỗi: publisher gửi message thành công nhưng crash trước khi đánh dấu outbox row. Lần chạy sau có thể gửi lại cùng event. Vì vậy, outbox publisher thường tạo **at-least-once delivery**; consumer cần idempotent.

Event nên có:
- event_id duy nhất.
- event_type và schema_version.
- aggregate_id như reservation ID.
- occurred_at là thời điểm nghiệp vụ xảy ra.
- published_at hoặc ingestion timestamp ở pipeline.
- Payload chứa các field cần cho analytics.

Không dùng timestamp nhận message làm thay thế thời điểm nghiệp vụ. Hai thời điểm này giúp đo pipeline lag và xử lý event đến muộn.

### 5.4. Pub/Sub và Dataflow

Pub/Sub phân phối event đến subscriber. Dataflow có thể đọc message, validate schema, enrich hoặc transform rồi ghi vào BigQuery. Google cung cấp template Pub/Sub to BigQuery cho message JSON phù hợp với schema table; nếu cần transform phức tạp, dùng Dataflow pipeline tùy chỉnh. [Dataflow Pub/Sub to BigQuery template](https://docs.cloud.google.com/dataflow/docs/guides/templates/provided/pubsub-to-bigquery).

Một pipeline có thể:
- Kiểm tra event_id và schema version.
- Chuẩn hóa timestamp và currency.
- Loại hoặc đưa message lỗi vào dead-letter path.
- Bổ sung dimension từ cache/reference data.
- Ghi raw event vào BigQuery.
- Ghi metric về throughput, lag, duplicate và invalid record.

### 5.5. Idempotency và deduplication

Pub/Sub/event pipeline có thể giao message lại. BigQuery table append-only có thể chứa duplicate nếu consumer ghi lại cùng event.

Một số chiến lược:
- Giữ event_id và deduplicate trong query/curation.
- Dùng staging table rồi MERGE theo event ID.
- Dùng sink/stream semantics phù hợp và checkpoint.
- Đảm bảo transformation có thể chạy lại mà không làm sai tổng hợp.
- Lưu trạng thái xử lý theo batch/event ID ở nơi phù hợp.

Ví dụ chọn event mới nhất theo event_id:

~~~sql
CREATE OR REPLACE TABLE analytics.curated.reservation_events AS
SELECT * EXCEPT(row_number)
FROM (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY event_id
            ORDER BY ingested_at DESC
        ) AS row_number
    FROM analytics.raw.reservation_events
)
WHERE row_number = 1;
~~~

Đây là bước curation; raw layer vẫn giữ event gốc để phục vụ audit và replay.

## 6. Chuyển dữ liệu bằng Change Data Capture (CDC)

### 6.1. CDC khác event nghiệp vụ thế nào?

CDC đọc thay đổi ở tầng database, thường từ transaction log hoặc replication log. Nó có thể ghi nhận insert, update và delete của bảng nguồn.

Event nghiệp vụ diễn tả ý nghĩa domain, ví dụ ReservationConfirmed. CDC diễn tả thay đổi dữ liệu, ví dụ row reservation có status chuyển từ PENDING sang CONFIRMED.

| Tiêu chí | Domain event / Outbox | CDC |
| --- | --- | --- |
| Ý nghĩa | Nêu điều gì đã xảy ra trong nghiệp vụ | Nêu row nào đã thay đổi |
| Payload | Do ứng dụng định nghĩa | Theo schema bảng nguồn và connector |
| Phụ thuộc schema database | Ít hơn nếu event contract ổn định | Có, thay đổi schema cần quản lý |
| Captures update/delete | Theo event mà ứng dụng phát | Có thể capture trực tiếp từ log |
| Use case | Business analytics, event-driven integration | Replicate bảng, đồng bộ dữ liệu, audit thay đổi |
| Công cụ | Outbox, Pub/Sub, Dataflow | Datastream hoặc CDC platform |

Không phải chọn một trong hai cho mọi trường hợp. Một hệ thống có thể dùng CDC để replicate bảng và domain event để truyền ý nghĩa nghiệp vụ.

### 6.2. Datastream đến BigQuery

Datastream hỗ trợ capture change từ các nguồn như Cloud SQL for MySQL và PostgreSQL rồi đưa vào BigQuery. BigQuery destination dùng Storage Write API và CDC functionality để áp dụng thay đổi. [Datastream BigQuery destination](https://docs.cloud.google.com/datastream/docs/destination-bigquery).

Các lựa chọn write mode thường gặp:

- **Merge:** BigQuery phản ánh trạng thái hiện tại của source table; cần primary key để hợp nhất thay đổi.
- **Append-only:** lưu các change event như insert, update và delete để giữ lịch sử thay đổi.

Chọn merge nếu cần bản sao trạng thái hiện tại để phân tích. Chọn append-only nếu cần lịch sử thay đổi và tự xây dựng mô hình temporal/audit. Đọc kỹ giới hạn connector, source database và schema trước khi triển khai.

### 6.3. Full backfill và ongoing replication

CDC thường có hai giai đoạn:

1. **Backfill:** sao chép dữ liệu hiện hữu của bảng nguồn.
2. **Change replication:** liên tục đọc thay đổi mới từ transaction log.

Cần xác định checkpoint/watermark và quy tắc xử lý thay đổi trong lúc backfill. Không giả định mọi bảng đều đã đồng bộ chỉ vì stream đã chạy; theo dõi trạng thái từng table và độ trễ.

### 6.4. Schema evolution

Khi source table đổi schema:
- Xác định field mới có nullable hay required.
- Kiểm tra kiểu dữ liệu và conversion.
- Đánh giá table đích và consumer query.
- Version hóa event/schema contract nếu có domain event.
- Triển khai thay đổi theo thứ tự tương thích ngược.
- Theo dõi lỗi CDC và dữ liệu bị từ chối.

Không đổi kiểu field tùy ý nếu dashboard, view, scheduled query hoặc downstream consumer đang phụ thuộc schema cũ.

## 7. Batch ingestion và ELT

### 7.1. Khi nào chọn batch?

Batch phù hợp khi:
- Báo cáo không cần cập nhật từng giây.
- Hệ thống nguồn có thể xuất snapshot theo lịch.
- Dữ liệu lịch sử cần backfill.
- Nguồn là file CSV, Avro hoặc Parquet.
- Muốn đơn giản hóa pipeline và giảm số lượng event nhỏ.

Luồng batch phổ biến:
1. Export dữ liệu nguồn theo khoảng thời gian hoặc watermark.
2. Ghi file vào Cloud Storage.
3. Nạp file vào BigQuery staging table bằng load job.
4. Kiểm tra schema, row count và dữ liệu lỗi.
5. Transform sang curated table.
6. Cập nhật watermark sau khi batch hoàn tất.

### 7.2. Incremental load bằng watermark

Nếu không dùng CDC, có thể dùng cột updated_at hoặc sequence để lấy phần dữ liệu thay đổi kể từ lần chạy trước.

Ví dụ logic:
- Lưu watermark cuối cùng đã commit.
- Truy vấn source với updated_at > last_watermark và updated_at <= batch_upper_bound.
- Export phần dữ liệu đó.
- Load vào staging table.
- MERGE staging vào curated table theo primary key.
- Chỉ cập nhật watermark sau khi merge thành công.

Dùng khoảng thời gian có overlap nhỏ hoặc sequence ổn định để giảm nguy cơ bỏ sót record do clock skew/late commit. MERGE phải idempotent; chạy lại batch không tạo duplicate hoặc làm lùi trạng thái mới hơn.

### 7.3. Raw, curated và mart

Một warehouse thường chia thành các lớp:

| Layer | Mục đích | Ví dụ |
| --- | --- | --- |
| Raw/landing | Giữ dữ liệu gần nguồn, dễ replay và audit | raw.reservation_cdc |
| Curated | Chuẩn hóa kiểu, tên, khóa và deduplicate | curated.reservations |
| Mart | Tối ưu cho câu hỏi nghiệp vụ/dashboard | mart.monthly_revenue |

Không biến raw table thành dashboard table trực tiếp nếu dữ liệu cần deduplicate, chuẩn hóa currency hoặc áp dụng business rule.

### 7.4. ELT khác ETL như thế nào?

- **ETL:** extract, transform rồi load; biến đổi trước khi ghi vào warehouse.
- **ELT:** extract và load dữ liệu trước, sau đó transform bằng SQL/compute trong warehouse.

BigQuery thường phù hợp với ELT: nạp raw data rồi chạy SQL để tạo curated/mart. Tuy nhiên, nếu dữ liệu cần lọc PII hoặc validate trước khi lưu, transform ở upstream pipeline có thể cần thiết.

## 8. Thiết kế data model cho BigQuery

### 8.1. OLTP normalized, OLAP analytical model

Database vận hành thường chuẩn hóa để tránh update anomaly và giữ consistency. Warehouse thường dùng mô hình dimensional để query báo cáo dễ hơn.

Ví dụ OLTP:
- customers
- reservations
- reservation_items
- payments
- assets

Ví dụ mô hình phân tích:
- fact_reservations
- fact_payments
- dim_customer
- dim_asset
- dim_date
- dim_channel

Fact table chứa sự kiện hoặc số đo; dimension table chứa ngữ cảnh để lọc và nhóm. Cần xác định grain của fact table, ví dụ một row cho mỗi reservation, mỗi payment attempt hay mỗi reservation status event.

### 8.2. Star schema

~~~mermaid
flowchart TD
    FACT["fact_reservations<br/>date_key, customer_key, asset_key<br/>reservation_count, amount, duration"]
    DATE["dim_date<br/>date_key, day, month, quarter, year"]
    CUSTOMER["dim_customer<br/>customer_key, segment, region"]
    ASSET["dim_asset<br/>asset_key, category, city"]
    CHANNEL["dim_channel<br/>channel_key, source, campaign"]
    DATE --> FACT
    CUSTOMER --> FACT
    ASSET --> FACT
    CHANNEL --> FACT
~~~

Star schema giúp analyst viết query dễ hiểu và giảm việc lặp lại join logic. BigQuery cũng hỗ trợ nested/repeated field và denormalized model; chọn schema dựa trên query pattern, data governance và maintainability.

### 8.3. Fact table cần xác định grain

Ví dụ fact_reservations có grain một row cho mỗi reservation. Khi đó:
- reservation_count có thể là 1.
- gross_amount là tổng tiền của reservation.
- duration_days là thời gian thuê.
- created_date_key là ngày tạo.
- confirmed_date_key có thể nullable nếu chưa xác nhận.

Không trộn một row/reservation với một row/payment attempt trong cùng fact table mà không có grain rõ. Nếu một reservation có nhiều lần thanh toán, nên có fact riêng hoặc định nghĩa grain khác.

### 8.4. Slowly Changing Dimension (SCD)

Thông tin dimension có thể thay đổi theo thời gian, ví dụ khách hàng đổi vùng hoặc tài sản đổi danh mục.

- **SCD Type 1:** ghi đè giá trị cũ; phù hợp khi không cần lịch sử.
- **SCD Type 2:** tạo version mới với valid_from, valid_to, is_current; giữ lịch sử thay đổi.
- **Snapshot:** lưu trạng thái tại các thời điểm định kỳ.

Chọn theo câu hỏi phân tích. Nếu muốn biết doanh thu tháng trước theo vùng của khách hàng tại thời điểm giao dịch, cần dimension history hoặc snapshot tương ứng; dùng giá trị hiện tại có thể làm sai báo cáo lịch sử.

## 9. Data freshness, consistency và event time

### 9.1. Freshness là một SLA

BigQuery có thể nhận dữ liệu qua:
- Batch load job theo lịch.
- Storage Write API.
- Datastream CDC.
- Pub/Sub và Dataflow.
- Export/import từ hệ thống khác.

Mỗi luồng có độ trễ và đặc tính khác nhau. Hãy định nghĩa freshness SLA, ví dụ dashboard tài chính cập nhật mỗi giờ, dashboard vận hành cập nhật trong vài phút, hoặc báo cáo quản trị cập nhật theo ngày. Đây là ví dụ mục tiêu kiến trúc, không phải cam kết mặc định của dịch vụ.

### 9.2. Ingestion time và event time

Hai timestamp cần phân biệt:

- event_time/occurred_at: thời điểm sự kiện xảy ra ở source.
- ingested_at: thời điểm pipeline nhận hoặc ghi dữ liệu vào BigQuery.

Một event xảy ra lúc 10:00 có thể đến BigQuery lúc 10:03 hoặc muộn hơn do retry. Nếu dashboard group theo ingestion time, báo cáo có thể xếp event vào sai ngày nghiệp vụ.

Lưu cả hai timestamp để:
- Đo pipeline lag.
- Xử lý late-arriving data.
- Tái tính partition hoặc aggregate.
- Đối chiếu dữ liệu source và warehouse.

### 9.3. Strong consistency ở source không đồng nghĩa BigQuery replica tức thời

Cloud SQL/Spanner/Firestore có semantics consistency riêng cho dữ liệu vận hành. Khi dữ liệu được chuyển qua CDC hoặc event pipeline, BigQuery là bản sao phân tích có độ trễ.

Một request vừa commit reservation có thể đọc lại trạng thái mới từ database vận hành nhưng dashboard chưa cập nhật. Đây là hành vi bình thường nếu pipeline bất đồng bộ. Không dùng BigQuery để trả lời câu hỏi đòi hỏi read-after-write ngay lập tức.

### 9.4. CDC merge và max staleness

Với Datastream destination, BigQuery có cơ chế CDC merge và cấu hình data staleness. max_staleness là một phần trade-off giữa freshness và chi phí xử lý background merge. Hãy chọn theo SLA dashboard và đo độ trễ thực tế; không mặc định giá trị nhỏ nhất luôn tốt nhất. [Datastream destination mô tả merge mode và staleness limit](https://docs.cloud.google.com/datastream/docs/configure-bigquery-destination).

### 9.5. Late data và correction

Dữ liệu có thể đến muộn do:
- Thiết bị offline.
- Publisher retry.
- CDC backlog.
- Source transaction commit trễ.
- Pipeline tạm dừng hoặc backfill.

Pipeline cần cho phép cập nhật lại partition hoặc aggregate bị ảnh hưởng. Không giả định partition ngày hôm qua đã bất biến nếu event có thể đến muộn. Đặt quy tắc correction window và quy trình reprocess.

## 10. Spring Boot: ranh giới giữa transaction và analytics

### 10.1. Tầng vận hành

Spring Boot dùng JDBC/JPA hoặc Spring Data phù hợp với database vận hành:
- Cloud SQL: JDBC driver, connection pool và Spring Data JPA/JDBC.
- Spanner: Spring Cloud GCP Spanner integration.
- Firestore: Spring Data Cloud Firestore reactive repository hoặc client API.

Transaction nghiệp vụ chạy trên transaction manager của database nguồn. Các repository tham gia transaction phải dùng cùng datasource/transaction manager nếu muốn atomic.

### 10.2. Tầng analytics

Spring Boot có thể dùng BigQuery Java client hoặc BigQueryTemplate để:
- Chạy truy vấn phục vụ báo cáo.
- Tạo query job theo lịch hoặc theo yêu cầu.
- Đọc kết quả đã aggregate.
- Nạp batch từ file hoặc stream.
- Kiểm tra job status và ghi metadata vận hành.

Không cần đưa BigQuery vào mọi service. Có thể tách Analytics API hoặc reporting worker để giới hạn quyền và cô lập tải query.

### 10.3. Ví dụ service transaction OLTP

~~~java
@Service
public class PaymentApplicationService {

    private final PaymentRepository payments;
    private final ReservationRepository reservations;

    public PaymentApplicationService(
            PaymentRepository payments,
            ReservationRepository reservations) {
        this.payments = payments;
        this.reservations = reservations;
    }

    @Transactional
    public Payment confirmPayment(
            UUID reservationId, String providerReference) {

        Reservation reservation = reservations.findById(reservationId)
                .orElseThrow();

        Payment payment = Payment.confirmed(
                reservationId, providerReference);

        reservation.markPaid();
        payments.save(payment);
        reservations.save(reservation);

        return payment;
    }
}
~~~

Đây là transaction nghiệp vụ trên database vận hành. Trong hệ thống có outbox, service sẽ ghi thêm event record vào cùng transaction để pipeline phân tích nhận thay đổi sau commit.

### 10.4. Ví dụ BigQuery query trong analytics service

Ví dụ giả định schema mart có reservation_date kiểu DATE và total_amount kiểu NUMERIC; DTO và accessor được chọn theo đúng schema đó.

~~~java
import com.google.cloud.bigquery.BigQuery;
import com.google.cloud.bigquery.FieldValueList;
import com.google.cloud.bigquery.QueryJobConfiguration;
import com.google.cloud.bigquery.QueryParameterValue;
import com.google.cloud.bigquery.TableResult;

@Service
public class ReservationAnalyticsService {

    private final BigQuery bigQuery;

    public ReservationAnalyticsService(BigQuery bigQuery) {
        this.bigQuery = bigQuery;
    }

    public List<DailyRevenue> revenueByDay(LocalDate startDate)
            throws InterruptedException {

        String sql = """
            SELECT
              reservation_date,
              COUNT(*) AS reservation_count,
              SUM(total_amount) AS revenue
            FROM analytics.mart.fact_reservations
            WHERE reservation_date >= @startDate
            GROUP BY reservation_date
            ORDER BY reservation_date
            """;

        QueryJobConfiguration config =
                QueryJobConfiguration.newBuilder(sql)
                        .addNamedParameter(
                                "startDate",
                                QueryParameterValue.date(startDate.toString()))
                        .setUseLegacySql(false)
                        .setMaximumBytesBilled(5_000_000_000L)
                        .build();

        TableResult result = bigQuery.query(config);

        List<DailyRevenue> rows = new ArrayList<>();
        for (FieldValueList row : result.iterateAll()) {
            rows.add(new DailyRevenue(
                    LocalDate.parse(
                            row.get("reservation_date").getStringValue()),
                    row.get("reservation_count").getLongValue(),
                    row.get("revenue").getNumericValue().bigDecimalValue()));
        }

        return rows;
    }
}
~~~

Ví dụ minh họa analytics query; DTO DailyRevenue và imports còn lại do ứng dụng định nghĩa. API có thể trả kết quả tổng hợp cho dashboard. Nếu query lớn hoặc có thể chạy lâu, hãy submit job bất đồng bộ, lưu job ID và cho client poll thay vì giữ HTTP request mở.

### 10.5. Không đặt hai transaction manager vào một @Transactional

@Transactional chỉ điều khiển transaction manager được Spring chọn. Một method có cả JPA repository và BigQuery client không tự trở thành transaction phân tán.

Ví dụ không an toàn về mặt atomicity:

~~~java
@Transactional
public void confirmAndWriteAnalytics(UUID reservationId) {
    reservationRepository.confirm(reservationId);
    bigQueryTemplate.writeJsonStream(...);
}
~~~

Transaction manager của Cloud SQL không thể rollback một write đã commit vào BigQuery. Nếu BigQuery call thất bại, transaction database có thể rollback; nếu BigQuery đã ghi thành công nhưng database rollback, dữ liệu analytics vẫn tồn tại.

Hãy dùng outbox/CDC hoặc workflow có retry và reconciliation thay cho giả định atomic cross-service.

### 10.6. API báo cáo và cache

Nếu dashboard được gọi thường xuyên:
- Precompute aggregate table hoặc materialized view khi phù hợp.
- Cache kết quả theo khoảng thời gian và filter.
- Dùng query parameters.
- Giới hạn date range và page size.
- Đưa query nặng vào background job.
- Hiển thị thời điểm dữ liệu được cập nhật gần nhất.

Không chạy một query full scan mới cho mỗi lần người dùng refresh dashboard nếu có thể tái sử dụng aggregate.

## 11. Tối ưu BigQuery cho OLAP

### 11.1. Partitioning

Partition table theo cột ngày/thời gian hoặc ingestion time để query có thể bỏ qua partition không liên quan.

Ví dụ:
- fact_reservations partition theo reservation_date.
- fact_payments partition theo payment_date.
- event_log partition theo ingestion date hoặc event date tùy yêu cầu.

Query nên có filter trên partition column:

~~~sql
SELECT
    reservation_date,
    SUM(total_amount) AS revenue
FROM analytics.mart.fact_reservations
WHERE reservation_date >= DATE '2026-10-01'
  AND reservation_date < DATE '2026-11-01'
GROUP BY reservation_date;
~~~

Partition pruning giảm lượng dữ liệu được đọc khi filter phù hợp. [Tài liệu query partitioned tables](https://docs.cloud.google.com/bigquery/docs/querying-partitioned-tables).

### 11.2. Clustering

Clustering sắp xếp dữ liệu theo một số cột để BigQuery có thể giảm block scan khi query filter các cột đó. Ví dụ cluster fact_reservations theo customer_id, asset_id hoặc region nếu query pattern thường dùng các field này.

Không chọn clustering chỉ theo cardinality. Hãy dựa trên query filter, phân bố dữ liệu và kích thước partition. [Tài liệu clustered tables](https://docs.cloud.google.com/bigquery/docs/clustered-tables).

### 11.3. Projection và aggregation

Tránh SELECT * nếu chỉ cần một số cột. BigQuery columnar nên số cột được chọn ảnh hưởng trực tiếp đến lượng dữ liệu cần đọc.

Đưa aggregate vào SQL:
- COUNT, SUM, AVG.
- GROUP BY.
- Window functions.
- APPROX_COUNT_DISTINCT khi độ chính xác xấp xỉ được chấp nhận.
- Pre-aggregation hoặc materialized view cho dashboard lặp lại.

LIMIT không đảm bảo giảm bytes scanned nếu query vẫn phải đọc toàn bộ table để xác định kết quả. [Best practices giảm dữ liệu xử lý](https://docs.cloud.google.com/bigquery/docs/best-practices-performance-compute).

### 11.4. Chi phí compute và storage

BigQuery có mô hình tính phí compute và storage riêng:
- On-demand: query được tính theo dữ liệu xử lý.
- Capacity-based: dùng slot/reservation để cấp năng lực compute.
- Storage: phụ thuộc lượng dữ liệu và loại storage billing model.

Để kiểm soát chi phí:
- Dùng dry run và maximumBytesBilled.
- Filter partition.
- Chọn cột cần thiết.
- Dùng materialized view/aggregate table khi workload phù hợp.
- Đặt quota hoặc budget alert.
- Theo dõi bytes processed, slot usage và job history.

Chi phí cần được xem cùng freshness và concurrency; query nhanh hơn không nhất thiết rẻ hơn nếu scan quá nhiều dữ liệu. [Hướng dẫn estimate và control costs](https://docs.cloud.google.com/bigquery/docs/best-practices-costs).

## 12. Bảo mật và quản trị dữ liệu

### 12.1. Tách quyền database vận hành và warehouse

Runtime service account của Spring Boot cần quyền trên database nguồn theo use case. Pipeline CDC/Dataflow cần quyền đọc source log, ghi Pub/Sub/BigQuery và quản lý checkpoint tương ứng. Analyst chỉ nên có quyền đọc dataset/mart cần thiết.

Không dùng một service account Owner cho cả:
- API checkout.
- CDC connector.
- Dataflow worker.
- BI dashboard.
- Migration pipeline.

Tách principal giúp giảm blast radius và dễ audit.

### 12.2. IAM trong BigQuery

BigQuery hỗ trợ quyền ở project, dataset, table, row và column. Ví dụ:
- Job User để tạo query job trong project.
- Data Viewer để đọc dataset/table.
- Data Editor để ghi dữ liệu vào dataset.
- Row-level access policy để giới hạn row theo điều kiện.
- Policy tags/column-level security cho field nhạy cảm.

Cấp quyền theo dataset hoặc table khi phù hợp thay vì mở rộng toàn project.

### 12.3. PII và dữ liệu nhạy cảm

Không replicate mọi cột của OLTP vào warehouse chỉ vì có thể. Trước khi đưa dữ liệu vào BigQuery:
- Phân loại PII và dữ liệu nhạy cảm.
- Loại field không phục vụ phân tích.
- Tokenize hoặc pseudonymize identifier nếu có thể.
- Áp dụng policy tags và row-level access.
- Đặt retention, deletion và legal hold policy.
- Kiểm tra dữ liệu nhạy cảm trong log và event payload.

Một bản sao analytics có thể tồn tại lâu hơn dữ liệu nghiệp vụ; cần thiết kế chính sách xóa/ẩn danh đồng bộ với yêu cầu pháp lý và nghiệp vụ.

### 12.4. Audit và lineage

Theo dõi:
- Source database và source table.
- CDC stream hoặc event topic.
- Schema version.
- Pipeline run/job ID.
- Watermark và thời điểm ingest.
- Transformation version.
- Số row đọc/ghi/reject.
- Dataset/table đích.

Lineage giúp truy ngược dashboard metric đến nguồn và giải thích chênh lệch số liệu.

## 13. Đối soát và chất lượng dữ liệu

### 13.1. Vì sao cần reconciliation?

Một pipeline có thể mất event, nhận duplicate, chuyển đổi sai kiểu hoặc trễ dữ liệu. Cần đối chiếu OLTP với warehouse theo batch/window:

- Số lượng record theo ngày.
- Tổng tiền theo currency.
- Số reservation theo trạng thái.
- Min/max event timestamp.
- Số event duplicate.
- Số event bị reject.
- Watermark source và target.

Không so sánh một bảng source đang thay đổi với một bảng target chưa hoàn tất backfill mà không cố định cùng snapshot/window.

### 13.2. Kiểm tra chất lượng

Ví dụ query kiểm tra duplicate event ID:

~~~sql
SELECT
    event_id,
    COUNT(*) AS copies
FROM analytics.raw.reservation_events
GROUP BY event_id
HAVING COUNT(*) > 1
ORDER BY copies DESC;
~~~

Ví dụ kiểm tra reservation không có customer key:

~~~sql
SELECT COUNT(*) AS invalid_rows
FROM analytics.curated.reservations
WHERE customer_id IS NULL;
~~~

Có thể tự động hóa kiểm tra bằng scheduled query, Dataform assertions, pipeline validation hoặc job riêng. Khi quality check thất bại, không publish mart mới như thể dữ liệu đã hợp lệ.

### 13.3. Replay và backfill

Khi pipeline lỗi:
1. Xác định khoảng thời gian hoặc event ID bị ảnh hưởng.
2. Kiểm tra source log retention hoặc outbox history còn đủ dữ liệu.
3. Reprocess vào raw/staging.
4. Deduplicate theo event ID hoặc primary key.
5. Rebuild curated/mart partition liên quan.
6. Đối soát lại count và aggregate.
7. Ghi lại incident và pipeline version.

Thiết kế replay ngay từ đầu sẽ giảm rủi ro phải khôi phục thủ công.

## 14. Chọn chiến lược đồng bộ theo yêu cầu

| Nhu cầu | Cách tiếp cận | Điểm cần lưu ý |
| --- | --- | --- |
| Báo cáo cập nhật mỗi ngày | Batch export/load | Đơn giản, freshness theo lịch |
| Dashboard cập nhật trong vài phút | Datastream CDC hoặc Pub/Sub/Dataflow | Theo dõi lag và schema evolution |
| Cần ý nghĩa nghiệp vụ rõ ràng | Outbox + domain event | Event contract, duplicate và ordering |
| Cần bản sao gần trạng thái hiện tại của bảng | Datastream merge mode | Cần primary key và hiểu max staleness |
| Cần giữ lịch sử mọi thay đổi | Append-only CDC/event log | Dung lượng lớn, curation/dedup cần thiết |
| Backfill lịch sử nhiều năm | Batch load/Datastream backfill | Kiểm tra location, schema và quota |
| Query dashboard lặp lại | Curated/mart/materialized view | Tính trước aggregate và cache |
| Checkout/availability cần read-after-write | Database OLTP | Không đọc BigQuery làm nguồn quyết định |

Không có một độ trễ đúng cho mọi hệ thống. Chọn pipeline dựa trên SLA, khối lượng dữ liệu, chi phí và khả năng vận hành.

## 15. Lỗi kiến trúc thường gặp

| Vấn đề | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Dùng BigQuery làm source of truth cho checkout | Latency và consistency không phù hợp | Ghi vào Cloud SQL/Spanner/Firestore |
| Chạy dashboard scan lớn trên OLTP | Cạnh tranh CPU/I/O/connection với request | Chuyển phân tích sang BigQuery |
| Dual-write database và BigQuery trong một method | Một bên commit, bên kia lỗi | Outbox, CDC hoặc event pipeline |
| Không có event ID | Khó deduplicate | Dùng ID ổn định cho mỗi event |
| Chỉ lưu ingestion timestamp | Báo cáo sai ngày nghiệp vụ khi event trễ | Lưu event time và ingestion time |
| Không version hóa schema | Consumer lỗi khi field thay đổi | Schema evolution tương thích ngược |
| Query SELECT * và không filter partition | Chi phí và latency tăng | Projection và partition pruning |
| Dùng DML từng row liên tục | Quá nhiều job và contention | Batch DML hoặc Storage Write API phù hợp |
| Tin rằng ACID BigQuery đồng nghĩa OLTP | Chọn sai database | Đánh giá access pattern và transaction latency |
| Không có reconciliation | Mất dữ liệu/duplicate khó phát hiện | Đối soát count, sum, watermark và quality |
| Cấp Owner cho mọi service | Tăng rủi ro bảo mật | IAM least privilege theo workload |
| Không có replay plan | Backfill sự cố khó khăn | Raw layer, checkpoint và idempotent transform |

## 16. Bài tập thực hành

### Bài A — Phân loại workload

Liệt kê 10 thao tác của ứng dụng đặt chỗ. Phân loại từng thao tác thành OLTP hoặc OLAP. Giải thích vì sao tạo reservation và tính doanh thu theo tháng cần hai access pattern khác nhau.

### Bài B — Chọn database vận hành

So sánh Cloud SQL, Spanner và Firestore cho:
- Reservation và payment.
- Hồ sơ khách hàng.
- Trạng thái ứng dụng mobile.
- Workload cần transaction toàn cầu.

Nêu schema, consistency, latency, query và lý do chọn.

### Bài C — Thiết kế outbox

Tạo bảng outbox_event trong Cloud SQL. Viết service @Transactional cập nhật reservation và insert event. Tạo publisher gửi event sang Pub/Sub. Giả lập crash sau khi publish nhưng trước khi đánh dấu processed; chứng minh consumer xử lý duplicate an toàn.

### Bài D — CDC với Datastream

Tạo Cloud SQL sandbox và cấu hình Datastream tới BigQuery. So sánh merge mode với append-only mode. Xác định cách backfill và cách theo dõi data staleness.

### Bài E — Dataflow streaming

Đưa event JSON từ Pub/Sub vào Dataflow rồi ghi BigQuery. Kiểm tra schema validation, dead-letter, event ID, event time và pipeline lag.

### Bài F — Batch ingestion

Xuất dữ liệu source theo watermark ra Cloud Storage. Tạo staging table, load batch, merge vào curated table. Chạy lại cùng batch và xác minh không tạo duplicate.

### Bài G — Star schema

Thiết kế fact_reservations, fact_payments, dim_customer, dim_asset, dim_date. Xác định grain của từng fact và cách xử lý customer đổi region theo SCD Type 2.

### Bài H — Data freshness và reconciliation

Đặt freshness SLA cho dashboard. Viết query so sánh count và sum theo ngày giữa source snapshot và BigQuery. Tạo cảnh báo khi lag hoặc số liệu chênh vượt ngưỡng.

### Bài I — Chi phí query

Tạo bảng partition theo ngày và cluster theo customer ID. So sánh bytes processed của query có partition filter với query không có filter. Thử maximumBytesBilled và dry run.

### Bài J — Bảo mật và lineage

Tách service account cho API, Datastream/Dataflow và analyst. Áp dụng quyền dataset/table, policy tag cho PII, ghi lại source, pipeline run ID và schema version.

### Câu hỏi tự kiểm tra

1. OLTP và OLAP khác nhau chủ yếu ở access pattern nào?
2. Vì sao database OLTP thường chuẩn hóa schema?
3. Vì sao BigQuery dùng columnar storage cho analytics?
4. BigQuery có ACID transaction không?
5. Vì sao ACID không làm BigQuery trở thành lựa chọn mặc định cho checkout?
6. Cloud SQL phù hợp với loại ứng dụng nào?
7. Khi nào nên cân nhắc Spanner thay Cloud SQL?
8. Firestore khác relational database ở data model nào?
9. Source of truth có ý nghĩa gì trong kiến trúc hybrid?
10. Vì sao không dual-write trực tiếp Cloud SQL và BigQuery?
11. Transactional outbox giải quyết vấn đề nào?
12. Vì sao outbox publisher vẫn có thể gửi duplicate?
13. CDC khác domain event như thế nào?
14. Datastream merge mode khác append-only mode ra sao?
15. Batch load khác streaming ingestion ở freshness và vận hành thế nào?
16. Event time khác ingestion time ở điểm nào?
17. Vì sao BigQuery replica có thể stale so với OLTP source?
18. Raw, curated và mart layer phục vụ mục đích gì?
19. Grain của fact table là gì?
20. SCD Type 2 giúp phân tích lịch sử như thế nào?
21. Vì sao BigQuery DML từng row không phù hợp với workload giao dịch tần suất cao?
22. Multi-statement transaction BigQuery có giới hạn concurrency nào đáng chú ý?
23. Partition pruning giảm chi phí ra sao?
24. Vì sao LIMIT không luôn giảm bytes scanned?
25. Cần reconciliation những chỉ số nào để phát hiện thiếu/duplicate dữ liệu?

**Kết quả mong đợi:** người học chọn đúng database vận hành theo workload OLTP, dùng BigQuery cho phân tích OLAP, giải thích được ACID transaction của BigQuery cùng giới hạn của nó, thiết kế được outbox/CDC/batch pipeline, xác định source of truth và freshness SLA, xây dựng data model phân tích, kiểm soát IAM/chi phí và đối soát chất lượng dữ liệu trong kiến trúc Spring Boot trên Google Cloud.

## Tài liệu tham khảo

- [BigQuery overview and architecture](https://docs.cloud.google.com/bigquery/docs/introduction)
- [BigQuery storage optimization and columnar storage](https://docs.cloud.google.com/bigquery/docs/best-practices-storage)
- [BigQuery multi-statement transactions](https://docs.cloud.google.com/bigquery/docs/transactions)
- [BigQuery DML best practices and concurrency](https://docs.cloud.google.com/bigquery/docs/data-manipulation-language)
- [Avoid point-specific DML and optimize query computation](https://docs.cloud.google.com/bigquery/docs/best-practices-performance-compute)
- [Cloud SQL overview](https://docs.cloud.google.com/sql/docs/introduction)
- [Spanner transactions](https://docs.cloud.google.com/spanner/docs/transactions)
- [Firestore overview](https://docs.cloud.google.com/firestore/native/docs/overview)
- [Datastream BigQuery destination](https://docs.cloud.google.com/datastream/docs/destination-bigquery)
- [Datastream BigQuery merge and append-only modes](https://docs.cloud.google.com/datastream/docs/configure-bigquery-destination)
- [Dataflow Pub/Sub to BigQuery template](https://docs.cloud.google.com/dataflow/docs/guides/templates/provided/pubsub-to-bigquery)
- [BigQuery partitioned tables](https://docs.cloud.google.com/bigquery/docs/querying-partitioned-tables)
- [BigQuery clustered tables](https://docs.cloud.google.com/bigquery/docs/clustered-tables)
- [BigQuery cost control](https://docs.cloud.google.com/bigquery/docs/best-practices-costs)

