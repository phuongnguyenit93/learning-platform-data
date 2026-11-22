# Orchestration pipeline, phụ thuộc và khả năng chạy lại

## 1. Vì sao pipeline cần orchestration?

Một nền tảng dữ liệu thường gồm nhiều bước: nhận dữ liệu từ ứng dụng, kiểm tra định dạng, lưu vùng raw, chuẩn hóa, nối dữ liệu, tính chỉ số, cập nhật warehouse hoặc data lake, rồi cung cấp dữ liệu cho báo cáo và machine learning. Mỗi bước có thể chạy bằng một công cụ khác nhau. Nếu chỉ nối chúng bằng các cron job độc lập, hệ thống khó biết bước nào phải chạy trước, dữ liệu đầu vào đã sẵn sàng chưa, tác vụ nào đang lỗi và có thể chạy lại mà không tạo dữ liệu trùng hay không.

**Orchestration** là việc điều phối vòng đời thực thi của các tác vụ theo lịch, sự kiện và phụ thuộc; quản lý trạng thái, retry, timeout, concurrency, checkpoint và kết quả. Orchestrator thường không tự xử lý dữ liệu. Nó gọi worker, SQL job, container, function, notebook hoặc dịch vụ managed rồi ghi nhận tiến độ.

Một pipeline được điều phối tốt cần trả lời:

- Task nào cần chạy và phụ thuộc vào task nào?
- Khi nào dữ liệu được coi là sẵn sàng?
- Nếu task lỗi giữa chừng, chạy lại từ đâu?
- Chạy song song tới mức nào để không làm quá tải nguồn/đích?
- Làm sao tránh ghi trùng, publish trùng hoặc tạo partition chưa hoàn chỉnh?
- Làm sao phát hiện dữ liệu sai dù task kỹ thuật trả về thành công?
- Ai nhận cảnh báo và có thể khôi phục pipeline theo runbook nào?

Trong module **CLOUD_ARCHITECTURE**, orchestration pipeline là quyết định kiến trúc ảnh hưởng đến độ tin cậy, khả năng mở rộng, bảo mật, chi phí và vận hành của nền tảng dữ liệu. Công cụ scheduler chỉ là một phần; chất lượng của dependency graph, hợp đồng dữ liệu và khả năng chạy lại mới quyết định pipeline có đáng tin hay không.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô hình hóa pipeline dưới dạng DAG và khai báo dependency rõ ràng.
2. Chọn lịch, event trigger, sensor, scheduler hoặc workflow engine phù hợp.
3. Thiết kế task độc lập, idempotent và có checkpoint để retry an toàn.
4. Xử lý timeout, retry, backoff, concurrency, backfill và replay.
5. Quản lý dữ liệu đến muộn, dependency liên pipeline và điều kiện data readiness.
6. Theo dõi trạng thái, data quality, SLA, lineage và chi phí.
7. Thiết kế recovery/runbook cho pipeline thất bại hoặc chạy sai dữ liệu.

## 2. Pipeline, task, workflow và DAG

- **Pipeline:** chuỗi xử lý dữ liệu đầu cuối, từ nguồn đến sản phẩm dữ liệu.
- **Task:** đơn vị công việc có đầu vào, đầu ra, trạng thái và giới hạn tài nguyên.
- **Workflow:** mô tả trình tự, nhánh điều kiện, vòng lặp hoặc trạng thái của một quy trình.
- **DAG (Directed Acyclic Graph):** đồ thị có hướng không chu trình; cạnh thể hiện dependency giữa task. DAG phù hợp các pipeline mà task không phụ thuộc vòng lặp lẫn nhau trong cùng lần chạy.
- **Scheduler/orchestrator:** quyết định khi nào tạo run, task nào sẵn sàng, worker nào được cấp việc và trạng thái nào được ghi nhận.
- **Worker/executor:** thực thi task thực tế, ví dụ container chạy Spark, SQL job hoặc function.

### 2.1. Ví dụ một DAG dữ liệu

~~~mermaid
flowchart TD
    A["Extract application data"] --> B["Validate source schema"]
    B --> C["Load raw partition"]
    C --> D["Normalize and deduplicate"]
    D --> E["Build curated tables"]
    E --> F["Run data quality checks"]
    F --> G["Publish warehouse model"]
    G --> H["Refresh dashboard"]
    G --> I["Train feature dataset"]
~~~

Task refresh dashboard và train feature có thể chạy song song sau khi warehouse model hoàn tất. Nếu dashboard chỉ cần curated table, không nhất thiết phải phụ thuộc vào bước train feature. Dependency thừa làm tăng thời gian tổng và mở rộng blast radius khi một nhánh không cần thiết bị lỗi.

### 2.2. DAG phải biểu diễn dependency thật

Một cạnh A đến B có nghĩa B không được bắt đầu trước khi điều kiện hoàn tất của A được thỏa. Điều đó không luôn đồng nghĩa A chỉ cần exit code 0. Với dữ liệu, điều kiện hoàn tất có thể bao gồm:

- Partition đầu vào đã được commit/publish.
- Manifest đã ghi nhận đúng số file hoặc batch.
- Schema version tương thích.
- Quality checks đạt ngưỡng.
- Watermark cho biết dữ liệu đã đủ tới thời điểm cần xử lý.
- Upstream run thuộc đúng ngày, tenant, region hoặc business period.

Nếu task chỉ kiểm tra file tồn tại trong khi producer vẫn đang upload file, consumer có thể đọc dữ liệu dở dang. Nên dùng manifest/commit marker hoặc atomic publish để định nghĩa data readiness.

## 3. Chọn công cụ orchestration theo nhu cầu

Không có một orchestrator phù hợp với mọi workload. Có thể chọn scheduler đơn giản, managed workflow engine hoặc nền tảng DAG chuyên dụng.

| Loại công cụ | Phù hợp khi | Đánh đổi cần xem |
|---|---|---|
| Cron / scheduler đơn giản | Một số job độc lập, lịch cố định, ít dependency | Khó quản lý DAG, backfill, trạng thái và retry phức tạp |
| DAG orchestrator | Nhiều task, dependency, retry, sensor, backfill | Cần quản trị scheduler, metadata store, worker và nâng cấp tùy sản phẩm |
| Managed workflow service | Muốn giảm công vận hành control plane | Giới hạn thời gian, số bước, concurrency, state transition và chi phí theo provider |
| Event-driven orchestration | Pipeline bắt đầu khi file/message/event xuất hiện | Cần quản lý duplicate, ordering, event storm và dữ liệu đến muộn |
| Stream processor | Xử lý liên tục theo event/partition/window | Khác với batch DAG; cần quản lý checkpoint, state, watermark và consumer lag |

Các sản phẩm cụ thể có thể là Apache Airflow, managed Airflow, cloud workflow/state machine hoặc scheduler trong data platform. Cần so sánh theo operator/plugin, execution model, secret integration, network, audit, SLA, khả năng export trạng thái và chi phí.

**Orchestrator không phải engine xử lý dữ liệu mặc định.** Với dữ liệu lớn, task thường khởi chạy job trên compute engine phù hợp (SQL warehouse, Spark, container hoặc managed service), còn orchestrator chỉ điều phối và theo dõi.

## 4. Định nghĩa lịch và trigger

Pipeline có thể bắt đầu theo lịch hoặc theo sự kiện. Cách chọn ảnh hưởng freshness, tải hệ thống và hành vi khi upstream chậm.

### 4.1. Time-based schedule

Ví dụ chạy pipeline tổng hợp mỗi ngày lúc 02:00 UTC. Lịch phải xác định timezone, daylight saving time nếu khu vực áp dụng, cửa sổ dữ liệu và cách xử lý khi lịch bị bỏ lỡ.

- **Fixed schedule:** chạy theo thời điểm cố định.
- **Interval schedule:** chạy mỗi khoảng thời gian.
- **Data interval:** khoảng dữ liệu mà một run chịu trách nhiệm, ví dụ từ 00:00 đến 01:00.
- **Catchup:** tạo lại các run cho những khoảng lịch đã bỏ lỡ.
- **Misfire behavior:** xử lý lần chạy bị trễ hoặc scheduler downtime theo cách nào.

Không nên ngầm giả định một run “ngày 18” sẽ đọc dữ liệu của ngày 18. Nên truyền rõ data interval start/end hoặc business date như tham số bất biến của run.

### 4.2. Event-based trigger

Pipeline có thể được kích hoạt khi file upload hoàn tất và manifest được commit; CDC watermark vượt ngưỡng; upstream pipeline phát sự kiện hoàn thành; queue có message mới; hoặc nguồn bên ngoài gửi webhook.

Event trigger có thể phát nhiều lần, sai thứ tự hoặc đến trễ. Event ID, source identity, object version và business partition cần được dùng để deduplicate và xác định run phù hợp.

### 4.3. Sensor và data readiness

Sensor kiểm tra một điều kiện chưa sẵn sàng, ví dụ partition đã xuất hiện hay upstream run hoàn tất. Polling sensor đơn giản nhưng có thể tạo nhiều request; deferrable/event-based sensor tiết kiệm worker hơn nếu công cụ hỗ trợ.

Sensor cần timeout rõ, poll interval và jitter phù hợp, predicate xác định đầy đủ, alert khi dữ liệu không đến đúng SLA và xử lý trường hợp event đã đến nhưng nội dung dữ liệu chưa commit.

## 5. Quản lý dependency trong và giữa các pipeline

### 5.1. Dependency nội bộ DAG

Task downstream được chạy khi upstream đạt trạng thái được quy định. Nên dùng dependency tối thiểu và biểu diễn nhánh điều kiện rõ ràng.

~~~python
# Pseudocode: API/DSL tùy orchestrator.
extract >> validate >> load_raw >> transform
transform >> [build_dashboard_model, build_feature_table]
~~~

Không phải mọi task đều cần phụ thuộc toàn bộ DAG. Nếu task tạo dashboard chỉ cần model daily_sales, để nó phụ thuộc đúng task tạo model đó thay vì chờ toàn bộ job ML.

### 5.2. Dependency liên pipeline

Pipeline B có thể cần output từ pipeline A. Có ba cách thường gặp:

1. **Explicit dataset/asset dependency:** A publish dataset/asset version; B chờ asset đó.
2. **Event/manifest:** A phát event sau khi commit output; B nhận event và kiểm tra manifest.
3. **External task sensor:** B kiểm tra trạng thái run của A theo business partition.

Ưu tiên dependency dựa trên data contract hoặc asset version. Chỉ chờ “job A thành công hôm nay” là chưa đủ nếu A chạy nhầm partition hoặc input chưa hoàn chỉnh.

### 5.3. Tránh dependency vòng

Nếu pipeline A chờ B và B lại chờ A, cả hai có thể không bao giờ chạy. Có thể tách thành các phase, dùng event handoff hoặc định nghĩa workflow state machine khác. DAG phải không có cycle; dependency liên pipeline cần được kiểm tra ở mức toàn hệ thống, không chỉ từng file DAG.

## 6. Task design: nhỏ, rõ và có hợp đồng

Một task tốt có:

- **Input contract:** dataset/partition/schema/version hoặc tham số đầu vào.
- **Output contract:** nơi ghi, schema, partition, manifest và trạng thái publish.
- **Precondition:** điều kiện dữ liệu và quyền cần có trước khi chạy.
- **Side effect:** task ghi ở đâu, phát event nào, gọi service nào.
- **Retry policy:** lỗi nào retry được và giới hạn ra sao.
- **Timeout/resource:** CPU, memory, disk, worker slot và deadline.
- **Observability:** log, metric, trace, run ID và owner.
- **Idempotency:** chạy lại có tạo kết quả sai hoặc side effect trùng không?

Giữ task đủ nhỏ để retry và quan sát riêng, nhưng tránh chia quá vụn làm tăng state transition, scheduling overhead và độ phức tạp. Một task transform gồm nhiều thao tác không có checkpoint có thể phải chạy lại từ đầu; ngược lại, tạo một task cho mỗi dòng dữ liệu là không hợp lý.

### 6.1. Phân tách control plane và data plane

Orchestrator quản lý control flow: run state, dependency, schedule, retry. Data plane thực hiện đọc/ghi/tính toán nặng. Không truyền dataset lớn qua metadata store hoặc XCom/state payload của orchestrator; chỉ truyền reference, partition, manifest hoặc object URI.

Điều này giúp tránh làm metadata database phình to, scheduler chậm và credential/dữ liệu nhạy cảm lan rộng.

## 7. Retry, timeout và backoff

Task có thể lỗi do network timeout, rate limit, worker restart, database failover hoặc dữ liệu không hợp lệ. Cần phân loại lỗi trước khi retry.

| Nhóm lỗi | Ví dụ | Hành vi thường phù hợp |
|---|---|---|
| Transient infrastructure | Timeout, connection reset, service 503 ngắn hạn | Retry có giới hạn |
| Throttling | API trả 429, warehouse giới hạn concurrency | Retry theo Retry-After/backoff, giảm concurrency |
| Data quality / schema | Field bắt buộc mất, schema không tương thích | Fail/quarantine hoặc chờ upstream; không retry vô hạn |
| Authorization/configuration | Credential hết hạn, role thiếu quyền, bucket sai | Fail nhanh, alert owner |
| Deterministic code error | Exception lặp lại với cùng input | Không retry nhiều lần nếu không thay code/input |
| Unknown outcome | Request đã commit nhưng response bị mất | Kiểm tra operation state/idempotency trước khi thực hiện lại |

### 7.1. Exponential backoff với jitter

Một chiến lược phổ biến:

\[
delay_n = \min(maxDelay,\ baseDelay \times 2^n) + jitter
\]

Jitter giúp tránh nhiều worker đồng loạt retry sau một outage. Cần có max attempts và max elapsed time; tổng thời gian retry không được vượt deadline của pipeline hoặc SLA downstream.

### 7.2. Timeout theo từng lớp

- Task timeout: thời gian tối đa cho một task.
- Sensor timeout: thời gian chờ data readiness.
- API/database timeout: thời gian chờ dependency.
- DAG/run deadline: thời gian tối đa của toàn pipeline.
- Queue visibility/lease: khoảng thời gian message được giữ cho consumer xử lý.

Timeout task không tự động hủy side effect ở remote service. Một task bị đánh dấu failed có thể đã ghi dữ liệu trước khi timeout. Lần retry cần kiểm tra operation/checkpoint hoặc idempotency.

## 8. Khả năng chạy lại: idempotency là nền tảng

Pipeline có thể chạy lại do retry, worker crash, scheduler restart, backfill, manual rerun hoặc replay event. **Idempotent task** bảo đảm cùng một input/run được thực hiện nhiều lần mà không tạo kết quả sai hoặc side effect trùng.

### 8.1. Các mẫu idempotency

| Mẫu | Cách làm | Điều cần tránh |
|---|---|---|
| Deterministic output path | Ghi vào path theo dataset/partition/run version | Mỗi lần retry tạo path mới khiến dữ liệu trùng |
| Atomic replace/partition overwrite | Ghi staging rồi commit/replace partition | Xóa partition cũ trước khi output mới hoàn tất |
| Upsert với business key | Dùng unique key và merge theo quy tắc | Upsert không kiểm soát thứ tự có thể ghi đè dữ liệu mới hơn |
| Processed-event ledger | Ghi event ID đã xử lý trong transaction phù hợp | Đánh dấu processed trước khi side effect hoàn tất |
| Operation/idempotency key | Gắn key ổn định với một command | Sinh key mới mỗi lần retry |
| Manifest/commit marker | Chỉ publish dataset khi toàn bộ file/batch đã hoàn tất | Để consumer đọc file tạm hoặc output chưa đủ |

### 8.2. Ví dụ xử lý partition an toàn

~~~text
1. Xác định partition = business_date=2026-11-18.
2. Ghi output vào staging/run_id=run-abc.
3. Kiểm tra count, schema, checksum và quality rules.
4. Ghi manifest trạng thái VERIFIED.
5. Atomically publish partition pointer hoặc commit marker.
6. Consumer chỉ đọc partition có manifest COMMITTED.
~~~

Nếu worker chết ở bước 2, lần chạy lại có thể xóa staging của run cũ hoặc tiếp tục theo checkpoint. Nếu chết sau khi ghi manifest nhưng trước khi trả success, task phải nhận diện partition đã commit và không publish duplicate.

### 8.3. Side effect ngoài database

Nếu task gửi email, gọi API đối tác hoặc tạo ticket, database transaction nội bộ không bảo vệ được side effect bên ngoài. Dùng idempotency key của provider nếu hỗ trợ, lưu operation reference, kiểm tra trạng thái trước retry và có reconciliation. Không xem task failed là bằng chứng remote action chưa xảy ra.

## 9. Checkpoint và tiến độ xử lý

Checkpoint đánh dấu phần dữ liệu hoặc công việc đã hoàn tất để task tiếp tục mà không phải làm lại toàn bộ.

Có thể checkpoint theo source offset/CDC position, file/object manifest, partition/date range, primary-key range, batch sequence, stream processor checkpoint hoặc workflow state/step token.

Một checkpoint cần gắn với input version và transformation version. Nếu code transform thay đổi, không nên tự động resume giữa output cũ và mới trừ khi tương thích được chứng minh.

~~~yaml
run_id: sales-daily-20261118-01
dataset: curated.daily_sales
data_interval_start: "2026-11-17T00:00:00Z"
data_interval_end: "2026-11-18T00:00:00Z"
source_watermark: "cdc-position-00981"
transform_version: "git-sha-abc123"
batches:
  - id: region-01
    rows_read: 120000
    rows_written: 120000
    status: VERIFIED
  - id: region-02
    rows_read: 98000
    rows_written: 98000
    status: VERIFIED
publish_status: COMMITTED
~~~

Đây là manifest minh họa, không phải schema bắt buộc của một orchestrator. Trong thực tế cần ghi checksum, schema version, quality metrics, storage references, timestamp, owner và phê duyệt theo yêu cầu.

## 10. Backfill, replay và rerun khác nhau thế nào?

| Hành động | Ý nghĩa | Ví dụ |
|---|---|---|
| **Retry** | Thử lại cùng một task/run sau lỗi | API warehouse timeout |
| **Rerun** | Chạy lại một run đã tồn tại | Chạy lại business date vì worker lỗi |
| **Backfill** | Tạo run cho các data interval quá khứ chưa xử lý hoặc cần tính lại | Nạp dữ liệu 10 ngày bị thiếu |
| **Replay** | Phát lại event/message/change đã lưu | Replay event từ dead-letter hoặc stream offset |
| **Reprocess** | Tính lại dữ liệu từ input lịch sử bằng logic/version mới | Rebuild curated model sau sửa transform |

Backfill có thể tạo tải lớn và ảnh hưởng downstream. Cần giới hạn concurrency, ưu tiên workload, chọn khoảng thời gian, lưu transform version và tránh ghi đè kết quả mới hơn.

### 10.1. Data interval và run identity

Một DAG có thể có nhiều run cho cùng business date nhưng khác code version hoặc backfill reason. Nên phân biệt:

- Logical date/data interval: kỳ dữ liệu mà run xử lý.
- Run ID: một lần thực thi cụ thể.
- Input snapshot/version: tập dữ liệu nguồn đã được chọn.
- Transform version: logic được dùng.
- Backfill reason/actor: vì sao và ai kích hoạt.

Không dùng wall-clock start time làm business date mặc định; nếu run bắt đầu muộn qua nửa đêm, nó vẫn có thể xử lý interval của ngày trước.

### 10.2. Backfill an toàn

1. Xác định khoảng dữ liệu và phạm vi downstream bị ảnh hưởng.
2. Kiểm tra source retention và khả năng tái tạo input.
3. Chạy thử trên một interval nhỏ.
4. Định nghĩa output version/path hoặc atomic partition replacement.
5. Giới hạn concurrency để bảo vệ nguồn/đích.
6. Đối soát trước khi publish.
7. Chỉ cập nhật consumer pointer sau khi partition đạt quality gate.
8. Ghi nhận version, reason và kết quả.

## 11. Xử lý dữ liệu đến muộn và dependency theo watermark

Batch theo ngày có thể nhận event đến trễ do thiết bị offline, network hoặc upstream retry. Nếu pipeline chạy lúc 01:00 và đọc dữ liệu đến 00:00, một event của ngày hôm trước có thể đến lúc 03:00.

Các chiến lược:

- **Fixed delay:** chờ một khoảng trễ sau khi cửa sổ kết thúc trước khi finalize.
- **Watermark:** xác định mức thời gian/offset mà hệ thống tin rằng dữ liệu cũ hơn đã gần đầy đủ theo semantics nguồn.
- **Late-arrival window:** cho phép cập nhật partition cũ trong một khoảng thời gian.
- **Correction/restate:** phát hành phiên bản partition mới khi dữ liệu đến sau SLA.
- **Event-time processing:** xử lý theo timestamp nghiệp vụ, không chỉ thời điểm nhận.

Không nên coi watermark là bằng chứng tuyệt đối không còn dữ liệu đến muộn; nó là chính sách/ước lượng dựa trên đặc tính nguồn. Hệ thống cần quy định sự kiện đến sau watermark được bỏ, đưa vào correction hay làm thay đổi kết quả đã công bố.

## 12. Concurrency, pools và giới hạn tài nguyên

Orchestrator có thể khởi chạy nhiều task cùng lúc. Nếu concurrency không được kiểm soát, pipeline có thể làm quá tải database, API nguồn, warehouse, object storage hoặc cụm compute.

Các giới hạn thường dùng:

- DAG concurrency: số task đồng thời trong một DAG.
- Global parallelism: tổng task đang chạy của orchestrator.
- Task pool/queue: giới hạn nhóm task dùng chung dependency hoặc loại compute.
- Per-task concurrency: giới hạn số instance của task/map item.
- Warehouse slot/compute quota: giới hạn năng lực ở data engine.
- API rate limit: giới hạn lời gọi tới hệ thống ngoài.
- Priority: ưu tiên pipeline phục vụ SLA cao hơn.

| Workload | Giới hạn tham khảo | Lý do |
|---|---:|---|
| Extract từ production DB | 4 worker | Không làm tăng latency OLTP quá mức |
| Transform trên warehouse | Theo slot/warehouse quota | Tránh tranh chấp compute |
| Partner API ingestion | 2 request đồng thời cho một partner | Tuân thủ quota đối tác |
| Historical backfill | 1 pipeline cấp thấp | Không cạnh tranh với daily SLA |
| Data quality checks | Tối đa 8 task | Cân bằng tốc độ và chi phí |

Các con số chỉ là ví dụ. Phải xác định qua load test và quota thực tế. Nên dùng backpressure để pipeline chậm lại khi downstream đầy thay vì tiếp tục đẩy queue vô hạn.

## 13. Data quality là gate của pipeline

Task kỹ thuật thành công không bảo đảm dữ liệu đúng. Quality checks nên là một phần của DAG và có thể chặn publish nếu vi phạm rule quan trọng.

| Nhóm | Ví dụ rule |
|---|---|
| Schema | Cột bắt buộc có mặt, kiểu dữ liệu tương thích |
| Completeness | Tỷ lệ null, số record tối thiểu |
| Uniqueness | Business key không trùng |
| Validity | Giá trị thuộc miền hợp lệ, timestamp không vượt ngưỡng |
| Referential integrity | Child record có parent hợp lệ |
| Reconciliation | Tổng amount/count khớp nguồn hoặc control total |
| Freshness | Partition mới nhất không cũ hơn SLA |
| Distribution/anomaly | Số lượng, doanh thu hoặc tỷ lệ lỗi không lệch bất thường |

Rule cần phân biệt:

- **Hard failure:** dữ liệu sai có thể gây quyết định nghiệp vụ sai; chặn publish.
- **Soft warning:** lệch nhỏ được phép trong ngưỡng; cảnh báo và ghi nhận.
- **Quarantine:** tách record sai để điều tra, không âm thầm drop.

Quality gate nên gắn với dataset/version, lưu kết quả và lý do. Nếu rule thay đổi, cần biết partition nào phải reprocess.

## 14. Quan sát: trạng thái run, data lineage và SLA

Orchestration cần observability ở cả control plane và data plane.

### 14.1. Các trạng thái hữu ích

- QUEUED: run đã được tạo nhưng chưa bắt đầu.
- RUNNING: đang thực thi.
- WAITING: chờ dependency/sensor.
- RETRYING: sẽ thử lại theo policy.
- SUCCEEDED: task/run kết thúc thành công theo điều kiện định nghĩa.
- FAILED: lỗi cuối cùng hoặc không retry được.
- SKIPPED: không chạy do điều kiện/branch.
- CANCELLED: bị hủy có chủ đích.
- UPSTREAM_FAILED: dependency bắt buộc thất bại.
- TIMED_OUT: vượt deadline.
- COMPENSATING/RECONCILING: cần xử lý/đối soát bổ sung cho side effect nếu mô hình có dùng.

Tên trạng thái khác nhau giữa công cụ; quan trọng là định nghĩa semantics và mapping trong dashboard.

### 14.2. Metric theo dõi

| Metric | Câu hỏi |
|---|---|
| DAG success rate | Bao nhiêu run hoàn tất đúng SLA? |
| Task retry count | Task nào thường xuyên lỗi tạm thời? |
| Run duration p50/p95 | Thời gian pipeline có tăng không? |
| Queue/scheduler delay | Run chờ lâu do thiếu worker hay dependency? |
| Upstream data age | Dữ liệu mới nhất đã cũ bao lâu? |
| Data freshness lag | Dữ liệu công bố trễ bao lâu so với nguồn? |
| Backfill volume | Có nhiều lịch sử cần chạy lại không? |
| Quality failure/quarantine | Dataset nào không đạt rule? |
| Resource utilization/cost | Pipeline có dùng compute quá mức? |
| SLA miss count | Hệ thống có vi phạm cam kết dữ liệu? |

### 14.3. Data lineage và traceability

Mỗi output cần truy ngược được source dataset, source partition và source watermark; run ID, task ID và dependency version; transform code/version, config và schema version; quality checks; destination asset/table/partition; người hoặc service identity kích hoạt và phê duyệt.

Lineage giúp trả lời bảng này được tạo từ đâu, dùng phiên bản logic nào và report nào sẽ bị ảnh hưởng nếu nguồn đổi. Không nên chỉ dựa vào tên task hoặc log text để tái dựng lịch sử.

## 15. Bảo mật và quản trị orchestrator

Orchestrator thường có quyền đọc nguồn, ghi warehouse, chạy code và sử dụng secret. Nó là control plane nhạy cảm.

- **Least privilege:** mỗi pipeline/task có identity và quyền đúng nguồn/đích; tránh một credential quản trị dùng chung cho tất cả DAG.
- **Secret management:** lấy secret từ secret manager hoặc workload identity; không hardcode vào DAG, parameter hoặc log.
- **Code review:** DAG/script là executable code; giới hạn ai được deploy/sửa.
- **Network isolation:** worker chỉ kết nối tới endpoint cần thiết; private connectivity cho data store.
- **Artifact integrity:** pin image/dependency version, scan package và kiểm soát nguồn code.
- **Parameter validation:** không cho input user điều khiển shell/query một cách tùy tiện.
- **Audit:** ghi nhận ai trigger, retry, clear task, backfill, thay lịch, sửa connection/secret và thay quyền.
- **Environment separation:** dev/staging/prod có role, connection và data scope riêng.
- **Data minimization:** metadata store và task log chỉ lưu reference cần thiết, tránh payload nhạy cảm.

Thao tác clear task hoặc rerun có thể lặp side effect. Quyền vận hành nên đi kèm hướng dẫn và audit, không cấp rộng cho mọi developer.

## 16. Chi phí và vận hành

Chi phí pipeline không chỉ là compute transform. Cần tính orchestrator control plane/worker và metadata database; compute/warehouse/Spark/container; storage tạm, staging, manifest và output version; data transfer, API request, CDC/stream ingestion; retry, backfill, duplicate và chạy lại; log, metric, trace, lineage và retention; công vận hành scheduler, plugin, connection, upgrades và incident.

Các cách kiểm soát chi phí:

1. Dùng sensor/event-driven trigger thay vì polling quá dày khi có thể.
2. Chạy task lớn bằng compute engine chuyên dụng, không dùng worker orchestrator để xử lý data nặng.
3. Phân tầng priority; backfill chạy ngoài peak và có concurrency thấp.
4. Tránh chạy lại toàn pipeline khi chỉ một partition/task cần xử lý.
5. Cache metadata phù hợp và tránh truy vấn nguồn lặp lại.
6. Dọn temporary artifact theo lifecycle nhưng giữ manifest/audit cần thiết.
7. Đo cost per published dataset/partition hoặc per successful business run.

## 17. Case study: pipeline dữ liệu đặt phòng hằng ngày

**Bối cảnh:** nền tảng đặt phòng nhận dữ liệu booking từ OLTP database, payment event từ queue và dữ liệu đối tác qua API. Mỗi sáng, bộ phận kinh doanh cần dashboard doanh thu theo ngày; đội ML cần curated feature table. Partner API đôi lúc chậm, event thanh toán có thể đến muộn và backfill không được làm ảnh hưởng pipeline hằng ngày.

### 17.1. DAG đề xuất

~~~mermaid
flowchart TD
    Start["Scheduled daily run / upstream events"] --> Booking["Extract booking snapshot"]
    Start --> Payment["Ingest payment events"]
    Start --> Partner["Fetch partner updates"]
    Booking --> Raw["Commit raw manifests"]
    Payment --> Raw
    Partner --> Raw
    Raw --> Validate["Schema + completeness checks"]
    Validate --> Transform["Normalize and deduplicate"]
    Transform --> Curated["Publish curated partition"]
    Curated --> Finance["Build daily revenue model"]
    Curated --> Feature["Build ML features"]
    Finance --> Quality["Reconcile totals and quality"]
    Feature --> Quality
    Quality --> Publish["Publish versioned datasets"]
    Publish --> Dashboard["Refresh business dashboard"]
~~~

### 17.2. Thiết kế run

- Mỗi daily run có data interval cố định theo timezone nghiệp vụ đã chọn.
- Booking extract lấy snapshot/CDC watermark rõ; payment ingestion ghi event ID để deduplicate.
- Partner API có rate limit, timeout, retry/backoff và checkpoint theo partner/page/token.
- Raw partition chỉ được publish khi manifest cho biết các file/batch đã hoàn tất.
- Quality task kiểm tra schema, record count, duplicate business key và payment total theo currency.
- Curated output được ghi theo transform version; chỉ commit/publish sau khi quality gate đạt.
- Finance dashboard và ML feature có thể chạy song song nếu dependency độc lập.
- Backfill có queue/priority riêng và concurrency thấp; không chiếm hết worker/warehouse.

### 17.3. Xử lý lỗi

| Tình huống | Hành vi |
|---|---|
| Partner API 429 | Tuân thủ Retry-After, giảm concurrency, tiếp tục từ checkpoint |
| Payment event đến trễ | Ghi late event, chạy correction/restate partition theo policy |
| Worker chết sau write | Kiểm tra manifest/partition commit và chạy lại idempotent |
| Schema partner đổi | Fail validation/quarantine, alert owner, không publish dữ liệu sai |
| Finance reconciliation lệch | Chặn dashboard publish, phân loại mismatch và chạy đối soát |
| Backfill kéo dài | Hạ priority/concurrency, bảo vệ daily SLA |

### 17.4. Tiêu chí nghiệm thu

- Dashboard nhận đúng business date và đạt freshness SLA.
- Payment duplicate không làm tăng tổng doanh thu.
- Partner paging có checkpoint và không bỏ sót trang.
- Output chỉ được consumer đọc sau khi manifest COMMITTED.
- Backfill không làm daily pipeline miss SLA.
- Có thể rerun một partition mà không nhân đôi output.
- Mọi output có lineage tới source watermark và transform version.

## 18. Runbook xử lý pipeline lỗi

Khi pipeline lỗi, không nên clear/rerun toàn bộ DAG ngay. Một runbook an toàn:

1. Xác định pipeline, run ID, data interval, task lỗi và trạng thái upstream.
2. Kiểm tra task log, error category, worker health, resource exhaustion và dependency status.
3. Xác định side effect đã xảy ra chưa: output file, DB write, API call, publish event hay manifest.
4. Kiểm tra checkpoint/manifest và xác định batch nào đã VERIFIED/COMMITTED.
5. Nếu lỗi transient, retry cùng operation identity; nếu lỗi dữ liệu/schema, quarantine và sửa input/code trước.
6. Nếu dữ liệu đã publish sai, xác định consumer bị ảnh hưởng, thu hồi/đánh dấu version và phát hành correction theo quy trình.
7. Chạy lại task hoặc partition nhỏ nhất có thể.
8. Đối soát output và downstream trước khi đánh dấu incident resolved.
9. Ghi root cause, số liệu tác động, run ID và biện pháp ngăn tái diễn.

Đừng sửa trực tiếp trạng thái metadata database của orchestrator để làm cho DAG xanh. Trạng thái kỹ thuật phải phản ánh kết quả thực tế của dữ liệu.

## 19. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Dùng cron job rời rạc cho DAG phức tạp | Không biết dependency và trạng thái tổng | Khai báo workflow graph và upstream contract |
| Trigger khi file vừa xuất hiện | Consumer đọc file chưa upload xong | Manifest/commit marker và readiness predicate |
| Task không idempotent | Retry tạo duplicate hoặc side effect lặp | Deterministic output, upsert, operation key |
| Retry mọi lỗi | Tăng tải, lặp lỗi deterministic | Phân loại transient/permanent/unknown |
| Không có timeout | Sensor/task chờ vô hạn | Task, sensor và run deadline |
| Truyền data lớn qua orchestrator metadata | Metadata DB phình và scheduler chậm | Truyền reference, path, partition, manifest |
| Backfill không giới hạn concurrency | Ảnh hưởng pipeline production | Queue/priority/pool riêng |
| Dùng wall-clock thay business interval | Partition sai ngày và khó tái lập | Data interval và timezone rõ |
| Quality check chỉ là cảnh báo nhưng vẫn publish | Dashboard sai vẫn được sử dụng | Hard quality gate cho invariant trọng yếu |
| Không quản lý late-arriving data | Tổng hợp thiếu hoặc bị sửa không có dấu vết | Watermark, late window và correction process |
| Task thành công đồng nghĩa dữ liệu đúng | Có thể publish output sai | Reconciliation và quality checks |
| Clear cả DAG khi một task lỗi | Tốn chi phí và tạo side effect trùng | Rerun task/partition tối thiểu sau kiểm tra |

## 20. Checklist review orchestration pipeline

### DAG và dependency

- [ ] DAG không có cycle; dependency phản ánh yêu cầu dữ liệu thật.
- [ ] Mỗi task có input/output contract, owner và trạng thái rõ.
- [ ] Data readiness dựa trên manifest, watermark hoặc upstream asset version.
- [ ] Dependency liên pipeline có timeout và semantics rõ.
- [ ] Nhánh optional/failure được khai báo có chủ đích.

### Retry và khả năng chạy lại

- [ ] Task có timeout, retry policy, backoff/jitter và error classification.
- [ ] Side effect có idempotency hoặc operation state.
- [ ] Checkpoint gắn với input version và transform version.
- [ ] Rerun/backfill/replay có phạm vi và concurrency giới hạn.
- [ ] Có xử lý duplicate, late data và unknown outcome.
- [ ] Output dùng staging/manifest/atomic publish để tránh đọc dữ liệu dở dang.

### Data quality và vận hành

- [ ] Có schema, completeness, uniqueness, validity, reconciliation và freshness checks.
- [ ] Hard failure/quarantine/warning có rule và owner.
- [ ] Có run ID, lineage, source watermark, transform version và manifest.
- [ ] Dashboard theo success, duration, retry, queue delay, freshness, lag và quality.
- [ ] SLA miss/quality failure có alert và runbook.

### Bảo mật và chi phí

- [ ] Task identity theo least privilege; secret lấy từ nguồn bảo vệ.
- [ ] Worker/network và environment được phân tách phù hợp.
- [ ] Code/DAG deployment có review và audit.
- [ ] Backfill và workload nặng có pool/priority riêng.
- [ ] Đo cost per dataset/partition hoặc per successful run.

## 21. Bài tập thực hành

**Bối cảnh:** một công ty có ba nguồn: booking OLTP, payment event stream và dữ liệu đối tác qua REST API. Họ cần tạo bảng doanh thu hằng ngày lúc 07:00, bảng sản phẩm phân tích lúc 08:00 và feature table cho ML. API đối tác có quota thấp; event thanh toán đến muộn tới 2 giờ; job lịch sử có thể chạy lại 90 ngày.

Hãy thiết kế orchestration:

1. Vẽ DAG và xác định task nào có thể chạy song song.
2. Chọn scheduler/time trigger hay event trigger cho từng nguồn; định nghĩa business interval/timezone.
3. Định nghĩa data readiness và dependency giữa pipeline.
4. Thiết kế checkpoint cho REST pagination, CDC offset và output partition.
5. Xây dựng retry/backoff/timeout theo từng loại lỗi.
6. Mô tả idempotency để retry hoặc rerun không nhân đôi booking/payment.
7. Định nghĩa late-arriving window, watermark và correction cho payment event đến muộn.
8. Thiết kế backfill 90 ngày với priority/concurrency thấp và versioned output.
9. Đưa data quality gates vào trước khi publish dashboard/feature table.
10. Xác định dashboard, alert, SLA và runbook khi DAG miss deadline.

**Gợi ý tự kiểm tra:** Một event đã vào queue không có nghĩa partition đã hoàn chỉnh. Một task exit code 0 không chứng minh dữ liệu hợp lệ. Backfill không được ghi đè partition mới hơn bằng logic cũ. Mỗi lần rerun cần biết input snapshot, data interval, transform version và output commit state.

## 22. Ghi nhớ

Orchestration điều phối task và dependency; nó không thay thế data processing engine, data contract hoặc quality assurance. Một DAG đáng tin phải biểu diễn đúng khi nào dữ liệu sẵn sàng, task nào có thể song song, lỗi nào retry được và output nào đã thực sự commit.

Khả năng chạy lại an toàn dựa trên idempotency, checkpoint, manifest, versioning và reconciliation. Backfill/replay phải có phạm vi, priority và concurrency rõ; dữ liệu đến muộn cần watermark/correction; vận hành cần lineage, freshness, SLA, alert và runbook. Thiết kế tốt giúp pipeline phục hồi từ lỗi từng phần mà không nhân đôi side effect, publish dữ liệu dở dang hoặc làm quá tải hệ thống nguồn và đích.
