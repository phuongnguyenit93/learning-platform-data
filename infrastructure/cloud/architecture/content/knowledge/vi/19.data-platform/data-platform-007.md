# Phục vụ phân tích, báo cáo và truy vấn liên miền

Một ứng dụng thường có nhiều dịch vụ nghiệp vụ, mỗi dịch vụ sở hữu dữ liệu và tối ưu database cho hoạt động giao dịch của mình. Booking Service cần xác nhận lịch nhanh và nhất quán; Payment Service ghi nhận trạng thái thanh toán; Customer Service quản lý hồ sơ; Inventory Service quản lý số lượng. Khi lãnh đạo cần báo cáo doanh thu theo khu vực, sản phẩm, khách hàng và thời gian, việc gọi trực tiếp từng database nghiệp vụ để ghép dữ liệu có thể tạo tải ngoài dự kiến, làm lộ cấu trúc nội bộ và khiến báo cáo không nhất quán.

**Nền tảng dữ liệu phân tích** cung cấp một đường đi riêng để thu thập, chuẩn hóa, liên kết và phục vụ dữ liệu từ nhiều miền cho báo cáo, dashboard, phân tích xu hướng và truy vấn liên miền. Nó thường kết hợp batch ingestion, change data capture (CDC), streaming/event, data lake hoặc warehouse, mô hình dữ liệu phân tích, catalog, semantic layer và công cụ BI/API truy vấn.

Mục tiêu là tạo khả năng phân tích đáng tin cậy mà không biến database giao dịch thành kho báo cáo dùng chung. Tuy nhiên, sao chép dữ liệu sang nền tảng phân tích cũng tạo thêm độ trễ, chi phí, bản sao nhạy cảm và yêu cầu quản trị. Kiến trúc phải xác định dữ liệu nào được đưa vào, ai sở hữu định nghĩa, freshness cần đạt, cách xử lý dữ liệu sai và ai được phép truy vấn.

Bài học thuộc phần **Nền tảng dữ liệu** của học phần thiết kế kiến trúc cloud. Trọng tâm là phục vụ phân tích, báo cáo và truy vấn liên miền bằng cách cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và khả năng vận hành theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Phân biệt workload OLTP và OLAP, hiểu vì sao báo cáo liên miền cần data platform.
- Chọn data warehouse, data lake hoặc lakehouse theo nhu cầu.
- Thiết kế ingestion bằng batch, CDC và streaming với checkpoint, schema và replay.
- Tổ chức dữ liệu theo domain, mô hình phân tích và semantic layer.
- Quản lý freshness, chất lượng, lineage, catalog và ownership.
- Bảo vệ dữ liệu liên miền bằng classification, least privilege, masking và audit.
- Tối ưu truy vấn, concurrency, partition, storage tier và chi phí.
- Đề xuất kiến trúc và kế hoạch kiểm thử cho một nền tảng phân tích thực tế.

## 1. Vì sao cần nền tảng dữ liệu phân tích?

Database giao dịch được thiết kế để phục vụ hoạt động nghiệp vụ trực tuyến. Các thao tác như tạo booking, cập nhật payment status hay kiểm tra inventory thường đọc/ghi một số bản ghi có cấu trúc rõ và cần latency thấp. Báo cáo phân tích lại có kiểu truy cập khác: quét nhiều bản ghi, kết hợp nhiều bảng, tổng hợp theo thời gian, nhóm theo dimension và tính toán trên lượng dữ liệu lớn.

Nếu công cụ BI chạy truy vấn nặng trực tiếp trên database production:

- Query báo cáo có thể tranh chấp CPU, memory, I/O và connection với giao dịch.
- Join nhiều miền làm query phụ thuộc schema nội bộ của từng service.
- Một báo cáo có thể ghép dữ liệu ở các thời điểm khác nhau mà không có định nghĩa consistency rõ.
- Service phải mở quyền đọc rộng cho BI, làm tăng bề mặt bảo mật.
- Thay đổi schema ở một service có thể phá dashboard và báo cáo của nhiều nhóm.
- Mỗi đội có thể tự định nghĩa doanh thu, khách hàng hoạt động hoặc đơn hoàn tất theo cách khác nhau.

Data platform tạo một đường phục vụ phân tích có kiểm soát, tách workload đọc nặng khỏi OLTP và cung cấp dữ liệu đã chuẩn hóa theo mục đích sử dụng.

### OLTP và OLAP khác nhau

| Đặc điểm | OLTP (giao dịch) | OLAP (phân tích) |
| --- | --- | --- |
| Mục tiêu | Thực hiện nghiệp vụ hiện thời | Hiểu xu hướng và tổng hợp dữ liệu |
| Truy cập | Nhiều read/write nhỏ, chọn lọc theo key | Scan, aggregate, join và group lớn |
| Latency | Thường cần thấp và ổn định | Có thể chấp nhận giây/phút tùy use case |
| Dữ liệu | Trạng thái hiện tại, transaction chi tiết | Lịch sử, snapshot, aggregate và dữ liệu liên miền |
| Mô hình | Chuẩn hóa theo transaction và ownership | Dimension/fact, wide table hoặc mô hình phục vụ query |
| Concurrency | Nhiều request nghiệp vụ đồng thời | Ít query hơn nhưng mỗi query có thể tiêu tốn nhiều tài nguyên |
| Tính nhất quán | Thường cần strong consistency trong transaction | Có thể eventual/freshness theo SLA |

Đây là khác biệt workload để chọn hệ thống và giới hạn phù hợp. OLTP vẫn có thể làm báo cáo nhỏ; OLAP cũng có thể nhận dữ liệu gần real-time nếu nền tảng đáp ứng.

## 2. Ranh giới dữ liệu giữa các miền

Trong kiến trúc hướng domain hoặc microservices, mỗi service sở hữu dữ liệu và quy tắc nghiệp vụ của mình. Data platform cần đọc dữ liệu từ nhiều miền nhưng không nên trở thành database trung tâm mà mọi service ghi trực tiếp.

~~~mermaid
flowchart LR
    subgraph DOMAINS["Nguồn nghiệp vụ / OLTP"]
        B["Booking Service<br/>Booking DB"]
        P["Payment Service<br/>Payment DB"]
        C["Customer Service<br/>Customer DB"]
        I["Inventory Service<br/>Inventory DB"]
    end
    B --> ING["Ingestion<br/>Batch / CDC / Events"]
    P --> ING
    C --> ING
    I --> ING
    ING --> LAKE[("Landing / Raw zone")]
    LAKE --> TRANSFORM["Validate, standardize,<br/>join and transform"]
    TRANSFORM --> CURATED[("Curated / Warehouse / Lakehouse")]
    CURATED --> SEM["Semantic models / Metrics"]
    SEM --> BI["BI / Dashboard / Analytics API"]
    SEM --> DS["Data science / ML"]
~~~

Service nguồn vẫn là nơi quyết định dữ liệu nghiệp vụ. Data platform nhận bản sao hoặc sự kiện để phục vụ phân tích, và cần ghi nhận nguồn, thời điểm, schema version và lineage.

### Quy tắc ownership

- Domain owner chịu trách nhiệm định nghĩa ý nghĩa và chất lượng dữ liệu phát ra.
- Data engineering chịu trách nhiệm ingestion, chuẩn hóa kỹ thuật và pipeline.
- Data product owner chịu trách nhiệm dataset phục vụ một nhóm người dùng cụ thể.
- BI/analytics owner chịu trách nhiệm metric, semantic definition và tài liệu báo cáo.
- Security/data governance xác định classification, retention, access và audit.

Không nên để nhóm BI phải tự suy đoán ý nghĩa các cột status, amount hoặc created_at từ schema ứng dụng. Cần contract có định nghĩa rõ.

## 3. Chọn data warehouse, data lake hay lakehouse

Không có một loại lưu trữ phù hợp mọi nhu cầu. Quyết định phụ thuộc dữ liệu có cấu trúc hay bán cấu trúc, kiểu query, concurrency, retention, governance và mức độ cần chia sẻ dữ liệu.

| Kiến trúc | Đặc điểm | Phù hợp khi | Đánh đổi |
| --- | --- | --- | --- |
| **Data warehouse** | Kho dữ liệu phân tích được tổ chức để query SQL, schema và performance cho BI | Báo cáo quản trị, KPI, dashboard và ad hoc SQL có cấu trúc | Chi phí compute/concurrency; ingest và model cần thiết kế |
| **Data lake** | Lưu nhiều loại dữ liệu ở object storage, thường giữ raw và nhiều format | Dữ liệu đa dạng, data science, lịch sử, batch/stream processing | Nếu thiếu catalog/schema/governance dễ thành data swamp |
| **Lakehouse** | Kết hợp object storage với metadata/table format và khả năng quản lý table/transaction cho analytics | Muốn linh hoạt dữ liệu lake cùng trải nghiệm table/SQL/BI | Thêm yêu cầu quản lý format, catalog, engine compatibility và compaction |
| **Operational data store (ODS)** | Tích hợp dữ liệu vận hành gần hiện thời cho query liên miền giới hạn | Tra cứu tác nghiệp hoặc tổng hợp trạng thái có SLA freshness thấp | Có thể tạo thêm một hệ thống operational quan trọng cần HA và consistency |

### Data warehouse

Warehouse thường phục vụ BI bằng SQL, dimension/fact model, materialized view hoặc aggregate table. Compute có thể tách khỏi storage, scale theo query và workload. Cần quản lý concurrency, workload queue, partition/clustering và cost per query.

### Data lake

Lake lưu dữ liệu thô và dữ liệu đã xử lý trên object storage. Dữ liệu có thể gồm CSV, JSON, Parquet, log, ảnh hoặc dữ liệu streaming được lưu theo file/object. Catalog, schema, partition và access policy quyết định khả năng khám phá và kiểm soát.

### Lakehouse

Lakehouse bổ sung metadata/table layer lên data lake để hỗ trợ schema evolution, snapshot/version, transaction semantics hoặc query engine theo khả năng của table format. Không phải mọi lakehouse đều cung cấp cùng mức ACID, concurrency hay interoperability; phải kiểm tra engine và format cụ thể.

### Cách chọn

- Dashboard quản trị có định nghĩa KPI rõ và nhiều người dùng SQL: warehouse thường là lựa chọn tự nhiên.
- Lưu log, file, raw event và tập dữ liệu đa dạng: lake có thể phù hợp.
- Muốn dùng cùng dữ liệu mở rộng cho BI, batch và ML: đánh giá lakehouse.
- Cần tra cứu trạng thái liên miền gần real-time cho tác nghiệp: xem ODS hoặc read model riêng, nhưng xác định SLA và không nhầm nó với source of truth.

## 4. Ingestion: đưa dữ liệu từ domain vào platform

Ingestion là đường thu nhận dữ liệu từ nguồn vào data platform. Ba kiểu phổ biến là batch, CDC và streaming. Chúng có thể kết hợp để đạt yêu cầu khác nhau.

### 4.1. Batch ingestion

Batch lấy dữ liệu theo lịch hoặc theo khoảng thời gian, ví dụ mỗi 15 phút hoặc mỗi đêm. Nguồn có thể xuất file, bảng snapshot hoặc API phân trang.

**Ưu điểm:** dễ vận hành, dễ kiểm soát số lượng, phù hợp báo cáo không cần freshness tức thời.

**Đánh đổi:** dữ liệu luôn trễ theo lịch; incremental extraction cần checkpoint để không bỏ sót hoặc đọc lặp; full reload có thể nặng.

Nguyên tắc thiết kế:

- Ưu tiên incremental load theo watermark/version nếu nguồn hỗ trợ.
- Không chỉ dựa vào updated_at nếu timestamp không đáng tin hoặc có update đến trễ; cân nhắc overlap window và reconciliation.
- Ghi checkpoint sau khi batch đã commit thành công vào target.
- Dùng idempotent merge/upsert để retry không tạo duplicate.
- Có late-arriving data và backfill policy.

### 4.2. Change Data Capture (CDC)

CDC ghi nhận thay đổi từ database source, thường qua transaction log hoặc cơ chế native của engine. Nó có thể đưa insert/update/delete sang downstream mà không phải scan toàn bảng liên tục.

~~~mermaid
flowchart LR
    DB[("Source database")] --> LOG["Transaction log / CDC connector"]
    LOG --> BROKER[("Change stream / broker")]
    BROKER --> SINK["CDC consumer"]
    SINK --> RAW[("Raw change records")]
    RAW --> MERGE["Apply changes / build current state"]
    MERGE --> CURATED[("Analytics tables")]
~~~

CDC cần quan tâm:

- Snapshot ban đầu và vị trí log bắt đầu theo dõi.
- Checkpoint/offset và khôi phục sau consumer restart.
- Thứ tự thay đổi theo key/partition.
- Delete/tombstone và update nhiều lần.
- Schema evolution và DDL compatibility.
- Log retention ở database; connector mất quá lâu có thể không còn log để bắt kịp.
- Replication slot/binlog retention có thể làm tăng storage hoặc gây áp lực database nếu consumer bị lag.

CDC phản ánh thay đổi database, không tự động chuyển thành ngữ nghĩa nghiệp vụ. Một row update có thể là trạng thái trung gian, sửa dữ liệu hoặc thay đổi kỹ thuật; cần transform theo domain contract.

### 4.3. Streaming và domain event

Streaming nhận event do domain service phát khi một sự kiện nghiệp vụ xảy ra, ví dụ BookingConfirmed hoặc PaymentCaptured. Đây là cách truyền ngữ nghĩa domain rõ hơn CDC khi producer thiết kế event contract tốt.

Streaming phù hợp với dashboard gần real-time, alerting hoặc phản ứng theo sự kiện. Nhưng producer/consumer cần quản lý schema, ordering, duplicate, retry, partition key, offset, retention và DLQ.

### So sánh batch, CDC và streaming

| Tiêu chí | Batch | CDC | Domain event streaming |
| --- | --- | --- | --- |
| Freshness | Theo lịch | Gần real-time tùy log/connector | Gần real-time tùy publish/consumer |
| Ngữ nghĩa | Snapshot hoặc tập bản ghi | Thay đổi vật lý/row-level | Sự kiện nghiệp vụ |
| Ảnh hưởng nguồn | Có thể tạo query scan | Đọc transaction log nhưng có overhead/retention | Producer phát event; cần outbox/broker |
| Delete/update | Cần logic watermark/upsert | Thường có record thay đổi/delete | Producer định nghĩa event/contract |
| Replay/backfill | Chạy lại batch hoặc snapshot | Phụ thuộc log retention và offset | Phụ thuộc broker retention/archive |
| Độ phức tạp | Thường thấp hơn | Connector, offsets, schema evolution | Event design, delivery, ordering và ownership |

Chọn theo freshness cần thiết. Không dùng streaming cho mọi dữ liệu chỉ vì muốn real-time; batch đủ tốt có thể đơn giản và rẻ hơn.

## 5. Data contract và schema evolution

Pipeline liên miền dễ bị hỏng khi producer thay đổi schema mà consumer không biết. Data contract xác định:

- Tên và ý nghĩa field.
- Data type, unit, timezone và nullability.
- Primary/business key và semantics của event.
- Version, compatibility rule và thời điểm deprecation.
- Privacy classification và quyền sử dụng.
- Freshness expectation, owner và kênh thông báo thay đổi.

Ví dụ field amount phải ghi rõ là tiền theo minor unit hay decimal, currency nào, gross hay net, và thời điểm quy đổi tỷ giá nếu có. Field status phải có enumeration và ý nghĩa transition.

### Schema evolution

Thay đổi thường gặp:

- Thêm field optional có default hoặc cách xử lý null rõ ràng.
- Đổi tên field, thường cần giai đoạn dual-read/dual-write hoặc mapping layer.
- Đổi type hoặc semantics, cần version mới và migration.
- Xóa field chỉ sau khi consumer cũ đã chuyển.
- Thay đổi event meaning không nên chỉ tăng version type một cách hình thức.

Với format Avro/Protobuf/JSON Schema hoặc table schema, dùng compatibility mode phù hợp và kiểm tra contract trong CI. Backward-compatible về cấu trúc không nhất thiết tương thích về nghiệp vụ.

### Source schema không phải analytical model

Không nên sao chép nguyên mọi bảng OLTP rồi gọi đó là warehouse model. Bảng nguồn phản ánh cách service ghi dữ liệu; mô hình phân tích cần đáp ứng câu hỏi kinh doanh, có lịch sử, dimension, fact, định nghĩa metric và xử lý late data.

## 6. Tổ chức mô hình dữ liệu liên miền

Sau khi thu nhận, dữ liệu thường đi qua các lớp. Một cách tổ chức phổ biến:

~~~mermaid
flowchart TD
    SRC["Domain sources"] --> RAW["Raw / Bronze<br/>Lưu bản ghi nguồn và metadata"]
    RAW --> CLEAN["Validated / Silver<br/>Chuẩn hóa, dedup, quality checks"]
    CLEAN --> MART["Curated / Gold<br/>Business model, facts, dimensions"]
    MART --> SEM["Semantic layer / certified metrics"]
    SEM --> CONSUME["Dashboards, reports, APIs, ML"]
~~~

Bronze/Silver/Gold là một cách đặt tên phổ biến, không phải yêu cầu bắt buộc. Có thể dùng raw/clean/curated hoặc landing/conformed/mart miễn ranh giới và tiêu chí rõ.

### Raw layer

Raw lưu dữ liệu gần với định dạng nguồn, có metadata như source, ingestion timestamp, event ID, schema version và partition. Nó hữu ích cho audit, replay và xây lại các lớp sau. Cần retention, encryption và quyền truy cập chặt vì raw có thể chứa dữ liệu nhạy cảm.

### Clean/conformed layer

Lớp này chuẩn hóa timestamp/timezone, currency/unit, mã tham chiếu, deduplicate, xử lý null, validate schema và áp dụng quy tắc chất lượng. Dữ liệu liên miền cần mapping ID và master/reference data có owner.

### Curated/mart layer

Tổ chức theo câu hỏi phân tích: doanh thu theo ngày/khu vực, tỷ lệ hủy, thời gian hoàn tất booking, hiệu suất payment provider. Tạo fact/dimension, aggregate hoặc materialized view để phục vụ query hiệu quả.

### Fact và dimension

Trong mô hình dimensional:

- **Fact** lưu sự kiện đo lường ở grain rõ ràng, ví dụ một dòng booking, một lần payment attempt hoặc một dòng doanh thu.
- **Dimension** mô tả ngữ cảnh như khách hàng, dịch vụ, bác sĩ, khu vực hoặc ngày.

Điều quan trọng là xác định grain. Nếu fact booking có một dòng mỗi booking nhưng join trực tiếp payment attempts có nhiều dòng trên mỗi booking, tổng doanh thu có thể bị nhân lên. Cần aggregate payment về grain phù hợp hoặc tạo fact riêng cho payment event.

### Slowly changing dimensions

Nếu tên khu vực hoặc phân khúc khách hàng thay đổi, báo cáo lịch sử có thể cần:

- Dùng giá trị hiện tại cho mọi lịch sử (Type 1).
- Giữ các phiên bản theo thời gian hiệu lực (Type 2).
- Lưu một số trường lịch sử theo quy tắc riêng.

Chọn theo câu hỏi nghiệp vụ. Báo cáo doanh thu tại thời điểm giao dịch có thể cần lịch sử dimension khi đó; báo cáo theo tổ chức hiện tại có thể dùng mapping mới nhất.

## 7. Truy vấn liên miền và semantic layer

Một báo cáo liên miền thường kết hợp Booking, Payment, Customer, Inventory hoặc Support. Khó khăn không chỉ là join dữ liệu mà là **định nghĩa chung**:

- Một booking được coi là hoàn tất khi nào?
- Doanh thu tính lúc authorization, capture hay settlement?
- Khách hàng hoạt động dựa trên login, booking hay payment?
- Booking hủy có tính vào tổng booking tạo mới không?
- Refund được trừ vào ngày refund hay ngày giao dịch ban đầu?

Nếu mỗi dashboard viết SQL riêng, cùng một metric có thể cho kết quả khác nhau.

### Semantic layer

Semantic layer định nghĩa entity, relationship, measure, dimension và business metric dùng chung. BI tool, API hoặc analyst có thể sử dụng cùng định nghĩa thay vì tự viết lại logic.

Ví dụ:

~~~text
Metric: Net Revenue
Grain: currency + business_date + market
Definition:
  captured_amount
  - refunded_amount
Filters:
  exclude test transactions
Currency:
  report in transaction currency or converted currency
Owner:
  Finance data product
Freshness:
  updated hourly
~~~

Đây là định nghĩa minh họa. Tổ chức cần thống nhất cách ghi nhận partial refund, chargeback, tax, fee, FX và timezone.

### Join liên miền

Join qua domain cần key mapping và quy tắc cardinality rõ. Không giả định hai service dùng cùng một customer ID hoặc ID không bao giờ thay đổi. Có thể cần conformed dimension, identity mapping service hoặc crosswalk table với owner.

### Truy vấn trực tiếp hay data product?

Federated query có thể truy vấn nhiều nguồn theo yêu cầu mà không ingest mọi dữ liệu trước. Nó tiện cho exploratory analysis hoặc dữ liệu ít dùng, nhưng query phụ thuộc availability, network và performance của nguồn; có thể làm tải tăng trên hệ thống giao dịch.

Data product/curated dataset phù hợp báo cáo lặp lại, KPI được chứng nhận và workload cần performance ổn định. Federated query và materialization có thể cùng tồn tại theo data class và nhu cầu freshness.

## 8. Freshness, consistency và late-arriving data

Data platform thường không cập nhật tức thời. Dữ liệu trải qua thời gian từ lúc commit ở source tới khi ingestion, transform và semantic model hoàn tất. Đây là data latency/freshness.

### Định nghĩa freshness SLA

| Dataset | Freshness mục tiêu giả định | Lý do |
| --- | --- | --- |
| Dashboard vận hành booking | Dưới 2 phút | Theo dõi backlog và lỗi gần hiện tại |
| Báo cáo doanh thu | Mỗi giờ | Phục vụ quản trị trong ngày |
| Báo cáo tài chính chốt ngày | Hoàn tất trước 08:00 ngày làm việc kế tiếp | Cần đối soát và kiểm tra |
| Dataset phân tích xu hướng | Hàng ngày | Không cần realtime |

Các số trên là mục tiêu ví dụ, không phải cam kết chung. Freshness phải đo theo source commit time, ingestion time và publish time; không chỉ dựa vào lịch job.

### Eventual consistency và dashboard

Khi Payment Service ghi capture nhưng analytics pipeline chưa nhận event, dashboard doanh thu có thể chưa phản ánh giao dịch. Giao diện nên hiển thị “dữ liệu cập nhật lúc...” hoặc freshness status nếu người dùng có thể diễn giải con số như trạng thái tức thời.

Không dùng analytics warehouse để trả lời giao dịch cần quyết định ngay, như xác nhận slot còn trống hay số dư có đủ hay không. Những quyết định đó thuộc transaction service/source of truth.

### Late-arriving data và event correction

Event có thể đến trễ, out-of-order hoặc được sửa sau đó. Pipeline cần:

- Lưu event/record time và ingestion time riêng.
- Cho phép cập nhật partition/window đã đóng khi nghiệp vụ yêu cầu.
- Dùng watermark và late-arrival window phù hợp.
- Có backfill/reprocess theo date range hoặc event ID.
- Dùng upsert/merge và business key để tránh duplicate.
- Ghi audit khi số liệu lịch sử bị điều chỉnh.

### Reconciliation

So sánh count, sum hoặc trạng thái giữa nguồn và curated dataset theo khoảng thời gian/partition. Chênh lệch cần được phân loại: dữ liệu đến trễ, filter, delete, duplicate, transformation bug hay source correction.

## 9. Data quality và kiểm soát pipeline

Chất lượng dữ liệu cần được kiểm tra liên tục thay vì chỉ kiểm tra cuối dự án.

| Nhóm | Ví dụ |
| --- | --- |
| Schema | Field/type/version đúng hợp đồng |
| Completeness | Không thiếu customer ID hoặc booking date bắt buộc |
| Uniqueness | Event ID hoặc business key không bị duplicate ngoài policy |
| Validity | Amount không âm khi rule không cho phép; status thuộc enumeration |
| Referential integrity | Payment tham chiếu booking hợp lệ |
| Consistency | Currency, timezone và unit thống nhất |
| Freshness | Partition/dataset được cập nhật trong SLA |
| Reconciliation | Count/sum theo source khớp với rule đối soát |

### Data quality gate

Dataset chỉ nên được đánh dấu certified/published khi các kiểm tra bắt buộc đạt. Nếu lỗi:

- Dừng promote dữ liệu sai sang curated layer.
- Cách ly record lỗi vào quarantine.
- Ghi số lỗi, nguồn, schema version và reason code.
- Cảnh báo owner/consumer.
- Cho phép sửa dữ liệu hoặc code rồi replay có kiểm soát.

Không nên silently drop record lỗi mà không có metric và audit, vì báo cáo sẽ thiếu dữ liệu nhưng người dùng không biết.

## 10. Metadata, catalog, lineage và ownership

Khi số dataset tăng, người dùng cần biết dataset nào tồn tại, ai sở hữu, cập nhật khi nào, metric được tính thế nào, có chứa dữ liệu nhạy cảm không, nguồn và transformation nào tạo ra nó, và ai có quyền sử dụng.

### Data catalog

Catalog ghi metadata kỹ thuật và nghiệp vụ: tên dataset, mô tả, schema, owner, tags, classification, freshness, quality status, access policy và ví dụ query phù hợp.

### Lineage

Lineage mô tả đường đi từ source field/table/event qua pipeline và transformation tới curated dataset, metric và dashboard. Khi source schema đổi hoặc số liệu sai, lineage giúp xác định consumer bị ảnh hưởng.

### Data product

Một data product nên có:

- Owner chịu trách nhiệm.
- Contract/schema được version.
- Mục đích và nhóm consumer.
- Quality/freshness SLO.
- Chính sách access và retention.
- Documentation, lineage và support channel.
- Quy trình deprecation và change notification.

Không phải mọi bảng trung gian đều cần data product công bố rộng. Chỉ công bố những dataset có consumer và hợp đồng rõ.

## 11. Bảo mật và quản trị dữ liệu liên miền

Data platform tập trung bản sao dữ liệu từ nhiều domain, nên một lỗi quyền có thể làm lộ phạm vi dữ liệu lớn hơn hệ thống nguồn.

### Classification và least privilege

Phân loại dữ liệu ít nhất thành public, internal, confidential và restricted theo policy tổ chức. PII, dữ liệu tài chính, thông tin sức khỏe hoặc thông tin định danh cần mức bảo vệ phù hợp và giới hạn mục đích sử dụng.

Quyền truy cập nên xét:

- Identity của user/service và nhóm công việc.
- Dataset/table/column/row scope.
- Tenant, region và purpose nếu cần.
- Môi trường production/non-production.
- Quyền export, download, share và tạo bản sao.
- Thời hạn cấp quyền và quy trình revoke.

### Masking và pseudonymization

Không phải analyst nào cũng cần email, phone hoặc tên thật. Có thể token hóa, hash có kiểm soát, mask hoặc loại bỏ trường nhận dạng trong curated dataset. Hash không tự động làm dữ liệu vô danh nếu vẫn có thể liên kết hoặc dò ngược.

### Row-level và column-level security

Nếu người dùng chỉ được xem dữ liệu một khu vực hoặc một tenant, áp policy tại query engine/semantic layer và kiểm tra cả đường export. Không phụ thuộc vào filter tự viết ở từng dashboard.

### Encryption và secret

- Mã hóa at rest và in transit.
- Quản lý key, rotation, quyền decrypt và backup key.
- Secret cho ingestion connector nằm trong secret manager.
- Không ghi payload nhạy cảm vào log hoặc dead-letter storage thiếu bảo vệ.
- Audit truy vấn, export và thay đổi access policy.

### Data lifecycle và deletion

Xóa dữ liệu ở source có thể cần lan sang raw, curated, materialized view, search index, export, backup và downstream. Cần xác định deletion propagation, legal hold, retention và bằng chứng hoàn tất. Không mặc định xóa một row trong nguồn sẽ tự xóa mọi bản sao analytics.

## 12. Hiệu năng và khả năng mở rộng truy vấn

Data warehouse/lakehouse có thể xử lý khối lượng lớn, nhưng query tốn kém nếu dữ liệu và workload không được tổ chức tốt.

### Partitioning

Chia dữ liệu theo date, region hoặc key phù hợp giúp engine đọc ít partition hơn. Tuy nhiên partition quá nhỏ tạo nhiều file/metadata; partition quá lớn khiến scan không chọn lọc. Chọn theo filter thực tế của query.

### Columnar format

Format columnar như Parquet phù hợp query phân tích vì engine có thể đọc các cột cần thiết và tận dụng compression/encoding. File nhỏ quá nhiều gây overhead; cần compaction và quản lý file size theo engine.

### Clustering/sorting

Sắp xếp hoặc cluster theo key thường được filter/join có thể giảm data scan. Hiệu quả phụ thuộc engine và phân bố dữ liệu; benchmark bằng query thực tế.

### Materialized view và aggregate

Query dashboard lặp lại có thể dùng pre-aggregate hoặc materialized view. Cần xác định refresh cadence, dependency, freshness và chi phí lưu kết quả. Aggregate phải giữ đúng grain để không double count.

### Workload management

Phân nhóm workload:

- Dashboard/BI interactive cần latency ổn định.
- Ad hoc analyst query có thể tiêu thụ tài nguyên lớn và cần quota.
- Batch transformation có thể chạy theo lịch.
- ML/feature extraction có pattern truy cập khác.

Dùng resource group, queue, concurrency cap, query timeout và workload isolation nếu nền tảng hỗ trợ. Không để một query ad hoc chiếm toàn bộ compute production.

### Caching và result reuse

Cache query result hoặc semantic metric có thể giảm chi phí nhưng cần invalidation theo freshness và quyền truy cập. Không chia sẻ cache key giữa tenant/role nếu kết quả khác nhau theo quyền.

## 13. Reliability, backup và recovery cho data platform

Data pipeline có thể lỗi ở scheduler, connector, broker, object storage, catalog, compute engine hoặc semantic model. Cần thiết kế từng lớp có thể phục hồi:

- Checkpoint/offset lưu bền vững.
- Retry có backoff và giới hạn.
- Dead-letter/quarantine cho record không hợp lệ.
- Idempotent load/merge và dedup event.
- Raw immutable/archive để backfill khi transformation sai.
- Version hóa code, schema và data model.
- Backup catalog, metadata, configuration và critical state.
- Restore test cho warehouse/lakehouse và quyền truy cập.
- Reprocess có giới hạn để không tạo tải đột biến lên nguồn.

### Replay và backfill

Replay có thể tạo duplicate nếu pipeline không idempotent. Trước khi chạy lại:

1. Xác định source partition/time range/event ID.
2. Chốt logic transformation/version muốn áp dụng.
3. Dùng staging hoặc target version riêng nếu thay đổi lớn.
4. Deduplicate theo event ID/business key.
5. Validate row count/sum/quality.
6. Promote dữ liệu và ghi audit.

### Disaster recovery

Data platform cần DR cho raw data, curated data, catalog, key, pipeline code và orchestration state. Backup object data mà quên catalog hoặc key có thể khiến dữ liệu không thể truy cập. Xác định RPO/RTO theo data product và mức ảnh hưởng của việc báo cáo gián đoạn.

## 14. Governance và quy trình thay đổi liên miền

Khi nhiều domain cùng phát dữ liệu, cần một cơ chế thay đổi mà không làm consumer bất ngờ.

### Schema registry/contract checks

Producer publish schema mới phải chạy compatibility checks. Consumer có thể đăng ký contract test. Thay đổi phá vỡ tương thích cần version mới, dual publishing/reading trong giai đoạn chuyển tiếp và deprecation window.

### Data owner và stewardship

Mỗi metric được chứng nhận cần business owner chịu trách nhiệm định nghĩa. Data steward có thể quản lý glossary, mapping và quality rules. Data engineering không nên tự quyết định một metric tài chính có ý nghĩa nghiệp vụ gì.

### Certified dataset và self-service

Cho phép analyst khám phá dữ liệu self-service qua catalog, sandbox và query quota. Nhưng báo cáo chính thức nên dùng certified dataset/metric có owner, test và version. Sandbox cần retention và cleanup.

### Data access request

Quy trình cấp quyền nên nêu mục đích, phạm vi, thời hạn, owner phê duyệt và log truy cập. Không cấp quyền rộng vĩnh viễn chỉ vì người dùng cần một dashboard.

## 15. Chọn batch, near-real-time hay federated query

| Phương án | Khi phù hợp | Rủi ro/cost |
| --- | --- | --- |
| Batch warehouse | Báo cáo định kỳ, KPI, lịch sử | Freshness theo lịch, batch window |
| CDC/streaming lakehouse | Theo dõi gần hiện thời, data products nhiều consumer | Connector/broker, offset, schema, ordering và vận hành |
| Operational data store/read model | Tra cứu liên miền phục vụ tác nghiệp | Phải vận hành thêm read model và consistency |
| Federated query | Khám phá, nguồn ít dùng hoặc chưa cần materialize | Phụ thuộc network/availability nguồn, tải trực tiếp, latency biến động |
| Hybrid | Kết hợp dữ liệu curated với lookup trực tiếp có kiểm soát | Cần quy định rõ freshness và nguồn nào chuẩn |

### Câu hỏi quyết định

1. Người dùng cần dữ liệu mới đến mức nào?
2. Query có lặp lại và có thể tối ưu bằng model/aggregate không?
3. Nguồn có chịu được tải truy vấn hay phải tách workload?
4. Dữ liệu có cần historical snapshot hoặc audit không?
5. Consumer có cần SQL ad hoc hay API theo nghiệp vụ?
6. Đội ngũ có thể vận hành CDC/streaming và schema evolution không?
7. Chi phí compute, storage, network và freshness có hợp lý không?

## 16. Ví dụ kiến trúc: báo cáo hiệu quả nền tảng đặt lịch

**Bối cảnh giả định:** Nền tảng đặt lịch có Booking, Payment, Customer và Provider Service. Ban điều hành muốn dashboard doanh thu theo ngày/khu vực, tỷ lệ hủy, tỷ lệ thanh toán thành công và hiệu suất nhà cung cấp. Dashboard cần cập nhật trong vòng 15 phút; báo cáo tài chính được đối soát cuối ngày. Database production không được chịu query BI nặng.

~~~mermaid
flowchart TD
    subgraph SOURCE["Operational domains"]
        B[("Booking DB")]
        P[("Payment DB")]
        C[("Customer DB")]
        V[("Provider DB")]
    end
    B --> ING["CDC + Domain events"]
    P --> ING
    C --> ING
    V --> ING
    ING --> RAW[("Raw data lake<br/>append-only with source metadata")]
    RAW --> CLEAN["Schema validation<br/>dedup + standardize"]
    CLEAN --> MODEL["Curated warehouse model<br/>FactBooking / FactPayment<br/>Customer / Provider / Date dimensions"]
    MODEL --> METRIC["Semantic layer<br/>Revenue, cancellation rate,<br/>payment success"]
    METRIC --> DASH["Executive dashboards"]
    MODEL --> FIN["Daily finance reconciliation"]
    ING --> MON["Pipeline monitoring / DLQ"]
~~~

### Quyết định dữ liệu

- Booking Service phát booking created/confirmed/cancelled events hoặc CDC phù hợp.
- Payment Service cung cấp authorization/capture/refund với operation reference, currency và timestamp.
- Customer/Provider dimension được snapshot hoặc CDC với effective time khi báo cáo cần lịch sử.
- Raw layer giữ event/change record với source, event ID, schema version và ingestion time.
- Curated layer tạo fact riêng cho booking và payment để tránh nhân bản số liệu khi join one-to-many.
- Semantic layer định nghĩa doanh thu theo capture trừ refund, tỷ lệ hủy và tỷ lệ payment success.
- Dashboard hiển thị freshness timestamp; báo cáo tài chính chạy reconciliation với nguồn payment.

### Freshness và consistency

Dashboard vận hành có freshness mục tiêu 15 phút, nhưng báo cáo tài chính chốt theo ngày chỉ được xác nhận sau reconciliation. Nếu một payment đến muộn hoặc provider gửi correction, báo cáo cần ghi adjustment thay vì âm thầm thay đổi số liệu mà không audit.

### Bảo mật

Analyst xem doanh thu và khu vực không cần phone/email khách hàng. Curated mart loại hoặc mask PII; row-level policy giới hạn market; truy vấn và export được audit.

### Tiêu chí xác nhận

- Số booking theo ngày khớp quy tắc nghiệp vụ và nguồn.
- Tổng captured/refunded amount khớp phép đối soát theo currency.
- Event duplicate không làm tăng doanh thu hai lần.
- Event late/correction được phản ánh có audit.
- Pipeline đạt freshness 15 phút trong tải thường và có cảnh báo khi vượt SLA.
- Dashboard query không tác động đáng kể đến database OLTP.

## 17. Bài thực hành: xây nền tảng báo cáo liên miền

**Tình huống:** Một doanh nghiệp có Order Service, Payment Service, Customer Service và Fulfillment Service. Các database độc lập. Nhóm quản trị cần báo cáo doanh thu theo ngày/region, số đơn hoàn tất, tỷ lệ refund và thời gian từ thanh toán đến giao hàng. Dashboard cần freshness dưới 10 phút; báo cáo tài chính chốt mỗi ngày. Dữ liệu khách hàng gồm email và số điện thoại, chỉ nhóm CS được xem raw PII. Đây là dữ kiện mô phỏng.

### Nhiệm vụ

1. **Chọn nền tảng:** so sánh warehouse, lake và lakehouse theo query pattern, data type, storage, concurrency, governance và cost; quyết định có cần ODS hoặc federated query.
2. **Thiết kế ingestion:** chọn batch, CDC hoặc domain event cho từng source; xác định snapshot đầu, offset/checkpoint, schema evolution, delete handling, replay và backfill.
3. **Thiết kế data model:** xác định grain cho FactOrder, FactPayment, FactFulfillment; dimension Customer, Product, Region và Date; xử lý one-to-many, refund, late event và SCD.
4. **Định nghĩa semantic metric:** viết định nghĩa doanh thu, tỷ lệ refund, đơn hoàn tất và thời gian fulfillment; ghi đơn vị, currency, timezone, filter, owner và freshness.
5. **Thiết kế security/governance:** classification, PII masking, row/column access, role theo team, catalog, lineage, retention và deletion propagation; chứng minh analyst không thể đọc raw email/phone.
6. **Thiết kế reliability/performance/cost:** retry/DLQ/reconciliation, query workload groups, partitioning, compaction, concurrency, budget và DR; đề xuất alert theo freshness và pipeline lag.

### Ma trận kiểm thử

| Phép thử | Tình huống | Bằng chứng cần có |
| --- | --- | --- |
| Duplicate event | Cùng payment event giao hai lần | Curated revenue không tăng gấp đôi |
| Late event | Refund đến sau ngày chốt | Metric điều chỉnh đúng và audit được |
| Schema change | Source thêm field hoặc đổi type | Contract check chặn thay đổi phá vỡ hoặc version được migrate |
| Connector outage | CDC dừng và offset lag | Alert, recovery và replay không mất/nhân đôi dữ liệu |
| Bad record | Amount/currency không hợp lệ | Record vào quarantine, owner nhận cảnh báo |
| Freshness breach | Pipeline chậm hơn 10 phút | Dashboard hiện stale indicator và alert |
| Access violation | Analyst thử truy vấn PII | Query bị từ chối/mask và audit có dấu vết |
| Query overload | Ad hoc query scan toàn dataset | Workload isolation/timeout giữ dashboard trong SLO |
| Data deletion | Customer yêu cầu xóa theo policy | Bản sao curated/downstream được xử lý theo lifecycle |
| Recovery | Reprocess partition đã lỗi | Số liệu đúng, idempotent và có reconciliation |

### Deliverables

- Sơ đồ kiến trúc và quyết định warehouse/lake/lakehouse.
- Data source inventory và ingestion matrix.
- Data contracts và schema version policy.
- Data model có grain, facts, dimensions và semantic metrics.
- Freshness/quality SLO và dashboard vận hành.
- Security/access matrix, lineage và retention.
- Load, failure, replay, DR và cost validation plan.
- ADR ghi quyết định, giả định, rủi ro và trigger review.

## 18. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi cho data platform |
| --- | --- |
| **Operational Excellence** | Pipeline có owner, SLA, catalog, lineage, quality checks, runbook và replay/backfill không? |
| **Security** | Data classification, least privilege, masking, encryption, key, audit, retention và deletion propagation có rõ? |
| **Reliability** | Checkpoint, retry, DLQ, idempotent merge, backup, restore và reconciliation đã được thử? |
| **Performance Efficiency** | OLTP đã được tách khỏi analytical workload? Partition, columnar format, materialization và concurrency có phù hợp query? |
| **Cost Optimization** | Ingestion cadence, storage tier, compute pause/scale, scan bytes, egress, retention và idle capacity có được kiểm soát? |
| **Sustainability** | Có tránh copy dữ liệu không cần thiết, pipeline chạy lại dư thừa, query scan toàn bộ và retention vô hạn không? |

## 19. Những sai lầm thường gặp

**Chạy BI trực tiếp trên database OLTP.** Query scan/join lớn tranh chấp tài nguyên và coupling schema với service.

**Tạo một kho dữ liệu tập trung nhưng không có owner.** Không ai chịu trách nhiệm định nghĩa, chất lượng hoặc freshness của dataset.

**Copy nguyên schema nguồn thành mô hình phân tích.** Source model tối ưu ghi giao dịch, không nhất thiết phù hợp fact/dimension và metric.

**Coi CDC là event nghiệp vụ.** Row-level change không phải lúc nào cũng phản ánh ý nghĩa business event.

**Chọn streaming dù batch đáp ứng yêu cầu.** Tăng chi phí broker, connector, schema, monitoring và vận hành không cần thiết.

**Không xác định grain khi join.** Quan hệ one-to-many có thể làm nhân số tiền hoặc số đơn.

**Định nghĩa KPI riêng trong từng dashboard.** Các nhóm báo cáo ra kết quả khác nhau cho cùng một thuật ngữ.

**Không xử lý duplicate và late-arriving data.** Tổng hợp sai hoặc lịch sử thay đổi không có audit.

**Không có freshness indicator.** Người dùng hiểu dashboard stale là trạng thái thời điểm hiện tại.

**Cho analyst đọc PII vì thuận tiện.** Bản sao dữ liệu tập trung làm tăng phạm vi rò rỉ.

**Không quản lý schema evolution.** Source change có thể âm thầm phá pipeline hoặc đổi nghĩa metric.

**Không thử replay/restore.** Khi transformation sai, nhóm không có đường tái tạo dữ liệu đáng tin.

## 20. Checklist trước khi đưa data platform vào production

- [ ] Workload OLTP và OLAP được phân biệt; báo cáo nặng không làm ảnh hưởng database giao dịch.
- [ ] Warehouse/lake/lakehouse/ODS được chọn theo access pattern và freshness, có lý do.
- [ ] Source domain, owner, data contract và quyền phát dữ liệu được xác định.
- [ ] Batch/CDC/streaming có checkpoint, schema handling, retry, replay và delete semantics.
- [ ] Raw/clean/curated layer có ranh giới, retention và tiêu chí promote.
- [ ] Fact grain, dimension, key mapping, SCD và metric definition được tài liệu hóa.
- [ ] Semantic layer/certified dataset có owner và business glossary.
- [ ] Freshness, completeness, validity, uniqueness và reconciliation có SLO/test.
- [ ] Late event, duplicate, correction và backfill có cách xử lý.
- [ ] Catalog, lineage, classification và ownership có thể tra cứu.
- [ ] IAM, tenant/row/column policy, masking, encryption, audit và deletion propagation được kiểm soát.
- [ ] Query workload isolation, partition, compaction, concurrency và cost guardrail được thiết lập.
- [ ] Pipeline có dashboard, alert, DLQ/quarantine và runbook.
- [ ] Raw, curated, metadata/catalog, keys và pipeline state có backup/recovery phù hợp.
- [ ] Đã thử connector outage, schema change, duplicate, bad data, access violation và replay.
- [ ] TCO bao gồm ingestion, storage, compute, query scan, network, logs, retention và nhân lực.
- [ ] ADR ghi các giả định, đánh đổi, owner và điều kiện review.

Nền tảng dữ liệu phân tích giúp tổ chức trả lời câu hỏi liên miền mà vẫn giữ workload giao dịch trong ranh giới phù hợp. Một thiết kế tốt bắt đầu từ **câu hỏi nghiệp vụ và freshness cần đạt**, sau đó chọn warehouse/lake/lakehouse, cách ingestion, data model và semantic definition. Chất lượng của platform được quyết định bởi hợp đồng nguồn, ownership, kiểm soát schema, bảo mật bản sao dữ liệu, khả năng replay và reconciliation. Khi những phần này được vận hành cùng nhau, báo cáo và phân tích có thể mở rộng mà vẫn rõ nguồn gốc, đáng tin cậy và kiểm soát được chi phí.
