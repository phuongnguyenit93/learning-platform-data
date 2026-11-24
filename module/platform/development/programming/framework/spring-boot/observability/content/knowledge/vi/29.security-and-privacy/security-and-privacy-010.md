# Data retention cho observability trong Spring Boot

Observability tạo ra dữ liệu liên tục: metrics, logs, traces, events và thông tin vận hành. Nếu lưu tất cả vô thời hạn, chi phí storage và indexing tăng, truy vấn chậm hơn, dữ liệu nhạy cảm tồn tại lâu hơn mức cần thiết và phạm vi ảnh hưởng khi xảy ra sự cố bảo mật cũng lớn hơn. Nếu xóa quá sớm, đội vận hành có thể mất dữ liệu cần để điều tra incident, đối chiếu SLO hoặc đáp ứng yêu cầu kiểm toán. **Data retention** xác định dữ liệu nào được giữ, trong bao lâu, ở đâu, ai được truy cập và cách xóa dữ liệu khi hết hạn.

Trong module SPRING_BOOT_OBSERVABILITY, Data retention là một phần của Security và privacy. Chính sách cần phối hợp Micrometer metrics, application logs, distributed traces, exporters, collectors và backend storage. Bài tập trung vào cách phân loại tín hiệu, xác định retention theo mục đích, giảm dữ liệu trước khi export, quản lý TTL và deletion, xử lý backup/replica, access control, audit, kiểm thử và runbook vận hành.

## Mục tiêu học tập

1. Giải thích data retention và lý do cần chính sách riêng cho observability.
2. Phân biệt retention của metrics, logs, traces và audit records.
3. Xác định mục đích, owner, thời hạn và nơi lưu cho từng loại dữ liệu.
4. Phân biệt sampling, aggregation, redaction và retention.
5. Thiết kế TTL, rollover, compaction và deletion trong storage backend.
6. Xử lý backup, replica, archive và dữ liệu đã export sang bên thứ ba.
7. Giảm dữ liệu nhạy cảm trước khi rời ứng dụng.
8. Áp dụng access control, audit và legal hold.
9. Kiểm thử retention, deletion và khả năng phục hồi dữ liệu theo policy.

## 1. Data retention là gì?

Data retention là tập hợp quy tắc xác định dữ liệu được giữ trong bao lâu và cách xử lý dữ liệu trong suốt vòng đời. Với observability, dữ liệu có thể được tạo ở Spring Boot, chuyển qua agent hoặc Collector, được lưu trong backend, sao chép sang replica, backup hoặc archive rồi mới bị xóa.

Một policy đầy đủ cần trả lời:
- Dữ liệu được thu thập để phục vụ mục đích nào?
- Ai sở hữu dữ liệu và ai chịu trách nhiệm policy?
- Dữ liệu nào được phép chứa thông tin nhận diện?
- Dữ liệu lưu ở hệ thống nào và khu vực nào?
- TTL bắt đầu từ lúc tạo, ingest hay đóng partition?
- Khi hết hạn, dữ liệu bị xóa, aggregate hay archive?
- Backup/replica có cùng lịch xóa không?
- Làm sao chứng minh deletion đã hoàn tất?

### 1.1. Vòng đời dữ liệu observability

~~~mermaid
flowchart TD
    App["Spring Boot application"] --> Collect["Instrumentation / Collector"]
    Collect --> Filter["Filter, redact, sample"]
    Filter --> Store["Metrics / logs / traces backend"]
    Store --> Query["Dashboards and investigation"]
    Store --> Backup["Backup / archive"]
    Store --> Expiry["TTL / retention expiry"]
    Expiry --> Delete["Delete or cryptographic erase"]
    Backup --> ArchiveExpiry["Archive expiry"]
    ArchiveExpiry --> Delete
    Delete --> Audit["Deletion audit evidence"]
~~~

Retention không chỉ là cấu hình TTL ở backend chính. Dữ liệu có thể tồn tại trong queue, cache, replica, backup, export file, SIEM hoặc data lake. Phải lập bản đồ đường đi trước khi tuyên bố một loại dữ liệu đã được xóa.

### 1.2. Retention không đồng nghĩa backup

Backup phục vụ khôi phục sau sự cố; retention phục vụ giới hạn thời gian lưu dữ liệu. Backup có thể giữ bản sao cũ sau khi dữ liệu đã hết hạn ở primary store. Vì vậy backup cần lịch hết hạn, kiểm soát truy cập và quy trình xử lý deletion request phù hợp.

## 2. Phân loại dữ liệu observability

Không nên áp dụng cùng một TTL cho mọi tín hiệu. Mỗi loại có mục đích, dung lượng, cardinality và độ nhạy khác nhau.

| Loại dữ liệu | Mục đích chính | Đặc điểm | Retention cần cân nhắc |
| --- | --- | --- | --- |
| Metrics | Trend, SLI/SLO, alerting | Aggregated time series | Thời gian đủ dài để phân tích xu hướng |
| Application logs | Điều tra sự kiện/lỗi | Nội dung tự do, có thể chứa PII | Ngắn hơn nếu có dữ liệu chi tiết |
| Distributed traces | Điều tra request cụ thể | Volume lớn, có sampling | Ngắn hơn hoặc tiered |
| Audit records | Chứng minh hành động/quyền truy cập | Yêu cầu integrity và truy xuất | Theo policy pháp lý/tổ chức |
| Profiles | Tối ưu CPU/memory | Có thể chứa stack/context | Ngắn, access hạn chế |
| Events | Deployment, config, incident | Dữ liệu mốc thời gian | Theo mục đích điều tra |

Bảng chỉ đưa ra hướng thiết kế, không phải thời hạn pháp lý mặc định. Retention cụ thể phải dựa trên yêu cầu nghiệp vụ, pháp luật áp dụng, hợp đồng, SLO, chi phí và data classification.

### 2.1. Metrics

Metrics thường được aggregate theo time series. Raw resolution có thể hữu ích cho điều tra ngắn hạn; downsampling giúp giữ xu hướng dài hạn với chi phí thấp hơn. Tuy nhiên, downsampling có thể làm mất spikes ngắn hoặc chi tiết histogram nếu aggregation không phù hợp.

### 2.2. Logs

Logs có thể chứa request payload fragments, user identifiers, exception messages, SQL text hoặc headers. Đây thường là tín hiệu có nguy cơ privacy cao. Giảm nội dung ngay khi log, đặt retention ngắn cho log chi tiết và chỉ archive loại log có mục đích rõ ràng.

### 2.3. Traces

Traces liên kết nhiều spans của một request. Chúng hữu ích để điều tra latency và dependency failures nhưng có thể mang URL, database attributes, baggage hoặc custom attributes. Sampling giảm volume trước storage; retention xác định thời gian lưu spans đã được ingest.

### 2.4. Audit records

Audit records có mục tiêu khác application logs. Chúng ghi nhận hành động cần truy vết như thay đổi quyền, truy cập dữ liệu hoặc thao tác quản trị. Không coi application logs là audit trail đáng tin nếu chúng có thể bị sửa, sampling hoặc xóa theo retention ngắn. Audit store cần integrity, access controls và policy riêng.

## 3. Xây dựng retention policy

Một policy nên được viết theo data class thay vì theo tên sản phẩm storage. Ví dụ policy record:

| Trường | Ví dụ |
| --- | --- |
| Data class | Application error logs |
| Purpose | Incident investigation |
| Owner | Service/platform operations |
| Classification | Internal, may contain identifiers |
| Source | Spring Boot application |
| Destination | Central log backend |
| Retention | Theo lịch được phê duyệt |
| Access | Operations role, audited |
| Deletion | TTL và backup expiry |
| Exceptions | Legal hold theo phê duyệt |

### 3.1. Mục đích và data minimization

Chỉ giữ dữ liệu cần cho mục đích đã xác định. Nếu mục tiêu là đo tỷ lệ HTTP 5xx, metrics với status/outcome có thể đủ; không cần lưu toàn bộ request body. Nếu mục tiêu là điều tra query latency, normalized statement và duration có thể hữu ích hơn raw bind parameters.

### 3.2. Owner và review

Mỗi data class cần owner chịu trách nhiệm:
- phê duyệt mục đích và retention;
- xác định access roles;
- rà soát thay đổi schema/attributes;
- xác minh backend áp dụng TTL;
- xử lý exceptions/legal holds;
- xác nhận deletion và audit evidence.

Review policy khi thay đổi exporter, Collector, backend, cloud region, data processor hoặc loại telemetry mới.

### 3.3. Retention theo mục đích, không theo khả năng storage

Backend có thể cho phép lưu nhiều năm nhưng điều đó không tự tạo lý do để giữ dữ liệu lâu như vậy. Thời hạn cần dựa trên nhu cầu điều tra, chu kỳ báo cáo, hợp đồng và quy định được áp dụng cho tổ chức.

## 4. Sampling, aggregation và retention

Ba cơ chế thường bị nhầm lẫn:

| Cơ chế | Thời điểm | Tác dụng | Dữ liệu bị ảnh hưởng |
| --- | --- | --- | --- |
| Sampling | Trước hoặc trong quá trình trace recording/export | Chọn trace/span được giữ | Trace volume |
| Aggregation/downsampling | Trong pipeline hoặc storage | Gộp dữ liệu thành resolution thấp hơn | Metrics/events tùy hệ thống |
| Retention/TTL | Sau khi dữ liệu đã được lưu | Xóa dữ liệu khi hết hạn | Dữ liệu đã ingest |

Sampling không phải retention. Một trace bị drop trước export không thể được phục hồi bằng cách tăng retention. Ngược lại, trace được export vẫn cần TTL để giới hạn thời gian lưu.

### 4.1. Head sampling và tail sampling

Head sampling quyết định sớm khi trace bắt đầu. Nó tiết kiệm tài nguyên nhưng có thể bỏ lỡ trace lỗi nếu quyết định drop đã được đưa ra trước khi biết kết quả cuối. Tail sampling tại Collector có thể giữ trace lỗi/latency cao nếu toàn bộ spans của trace được chuyển tới cùng pipeline và Collector có đủ dữ liệu để ra quyết định.

Dù dùng sampler nào, retention backend vẫn cần được cấu hình riêng. Đừng dùng sampling probability như cam kết lưu dữ liệu trong một số ngày.

### 4.2. Metrics downsampling

Một chiến lược có thể giữ metrics độ phân giải cao trong thời gian ngắn rồi lưu rollups theo phút/giờ trong thời gian dài hơn. Cần xác định aggregation đúng cho từng loại meter:
- counter: tính rate hoặc tổng theo window;
- gauge: chọn average/min/max hoặc last value theo mục đích;
- histogram: merge buckets hoặc tính quantiles theo khả năng backend;
- summary: hiểu giới hạn khi tổng hợp percentile.

Không lấy trung bình các percentile đã tính độc lập rồi gọi đó là percentile toàn hệ thống.

## 5. Retention của metrics, logs và traces

### 5.1. Metrics backend

Metrics backend thường cung cấp retention theo tenant, workspace, block hoặc time-series database configuration. Khi downsample:
- giữ raw data đủ cho incident investigation;
- giữ rollups đủ cho capacity/SLO trends;
- giữ histogram buckets cần thiết cho latency analysis;
- theo dõi cardinality và series churn;
- kiểm tra retention có áp dụng cho remote-write replicas và long-term storage.

### 5.2. Log backend

Log storage có thể dùng index lifecycle, data stream lifecycle hoặc TTL theo partition. Thiết kế cần:
- rollover theo size/age;
- hot/warm/cold tiers nếu có;
- delete index/partition khi hết hạn;
- giới hạn retention cho debug logs;
- tách security/audit logs khỏi application logs;
- bảo đảm archive có encryption và access controls.

### 5.3. Trace backend

Trace backend có thể lưu spans theo block/partition hoặc TTL. Volume phụ thuộc traffic, spans per trace, sampling rate và attribute size. Cần đo ingest rate và storage growth, đặt TTL theo data class, và kiểm tra compaction/deletion của block store.

### 5.4. Spring Boot không phải nơi duy nhất cấu hình retention

Spring Boot/Micrometer tạo và export telemetry; retention thường được quản lý tại Collector, metrics/logs/traces backend hoặc storage platform. Không tìm một property Spring Boot chung để đặt retention cho mọi backend. Cấu hình phải đặt tại nơi dữ liệu thực sự được lưu.

## 6. Giảm dữ liệu trước khi export

Retention tốt bắt đầu từ việc không thu thập dữ liệu không cần thiết. Dữ liệu đã export tới nhiều hệ thống sẽ khó xóa đồng bộ hơn.

Các biện pháp:
- allowlist attributes thay vì capture toàn bộ headers;
- redact Authorization, cookies, tokens và query secrets;
- không ghi request/response bodies mặc định;
- không đưa user/order/request IDs vào metric labels;
- normalize SQL và bỏ bind values;
- giới hạn baggage keys và value length;
- chuẩn hóa exception categories;
- giới hạn event payload và stack traces.

### 6.1. Redaction trong ứng dụng

Ví dụ log metadata an toàn:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {
    private static final Logger log =
            LoggerFactory.getLogger(PaymentService.class);

    public void authorize(String paymentMethod, String accountReference) {
        log.info("Payment authorization requested: method={}, accountRefPresent={}",
                paymentMethod, accountReference != null);
        // Perform authorization without logging accountReference itself.
    }
}
~~~

Ví dụ chỉ ghi loại payment method đã được validate và việc có reference hay không; không ghi account reference. Nếu paymentMethod do caller gửi, allowlist/normalize trước khi log để giữ tập giá trị hữu hạn.

### 6.2. Redaction ở Collector

Collector processors có thể filter/drop attributes hoặc redact nội dung trước khi export tới backend. Đây là lớp bảo vệ bổ sung, không nên là lớp duy nhất nếu dữ liệu đã được ghi vào local logs, queues hoặc exporter debug output.

### 6.3. Không dùng high-cardinality field để định danh bản ghi

Trace ID có thể giúp tra cứu một request cụ thể trong trace backend, nhưng không phù hợp làm metric label. User ID, email, account number và request payload cần được loại bỏ hoặc tokenization theo policy. Tokenization vẫn là dữ liệu có thể liên kết nếu mapping còn tồn tại; cần bảo vệ mapping riêng.

## 7. TTL, rollover, compaction và deletion

TTL là khoảng thời gian dữ liệu được phép tồn tại trước khi hết hạn. Backend có thể thực hiện deletion theo chu kỳ, không nhất thiết xóa đúng giây TTL kết thúc.

### 7.1. Xác định mốc bắt đầu TTL

Một số hệ thống tính TTL từ event timestamp; hệ thống khác từ ingest time hoặc index creation time. Nếu event đến trễ hoặc replay từ queue, retention có thể khác mong đợi. Policy cần nêu rõ timestamp nào là căn cứ.

### 7.2. Rollover và partitioning

Rollover tạo index/block mới theo tuổi hoặc dung lượng. Partition theo ngày/tuần giúp xóa dữ liệu hết hạn bằng cách drop partition, nhưng partition quá nhỏ tạo overhead metadata và query planning. Chọn granularity theo ingest rate và backend.

### 7.3. Compaction và tombstones

Một số storage engines đánh dấu dữ liệu đã xóa bằng tombstones và thu hồi dung lượng sau compaction. Vì vậy TTL expiry và physical space reclamation có thể xảy ra ở thời điểm khác nhau. Theo dõi compaction backlog và storage usage; không tuyên bố physical erase ngay khi record không còn queryable.

### 7.4. Deletion evidence

Lưu bằng chứng tối thiểu về policy version, data class, thời điểm deletion job chạy, phạm vi partition/index và kết quả. Audit evidence không nên sao chép nội dung dữ liệu đã bị xóa. Với yêu cầu deletion theo subject, cần biết backend có hỗ trợ filter/delete theo subject hay phải dùng partition/key strategy từ đầu.

## 8. Backup, replicas, archive và downstream copies

Dữ liệu observability có thể được sao chép sang:
- replicas để tăng availability;
- snapshots để disaster recovery;
- object storage để archive;
- SIEM/data lake để correlation;
- vendor SaaS để search/alerting;
- local disk buffers hoặc message queues.

Mỗi bản sao phải nằm trong data inventory và retention policy.

### 8.1. Backup expiration

Backup có lịch hết hạn riêng. Nếu một record đã hết TTL ở primary nhưng vẫn tồn tại trong snapshot, policy phải mô tả thời điểm snapshot hết hạn hoặc cách xử lý restore để không hồi sinh dữ liệu đã hết hạn.

### 8.2. Restore behavior

Khi restore backup cũ, hệ thống cần chạy expiry/deletion reconciliation trước khi mở quyền truy cập rộng. Nếu không, dữ liệu đã hết hạn có thể xuất hiện trở lại. Kiểm thử restore workflow với dữ liệu có expiry timestamps.

### 8.3. Downstream processors

Nếu telemetry được gửi sang SIEM, data lake hoặc vendor, hợp đồng và processor configuration cần quy định retention, deletion, region, subprocessors và notification khi policy thay đổi. Không thể bảo đảm deletion toàn bộ chỉ bằng cách xóa dữ liệu ở backend đầu tiên.

## 9. Access control, encryption và legal hold

Retention dài làm tăng thời gian dữ liệu có thể bị truy cập. Kết hợp retention với:
- authentication và role-based access;
- tenant/service isolation;
- encryption in transit và at rest;
- audit logs cho query/export/admin actions;
- hạn chế bulk export;
- secrets management cho exporter credentials;
- legal hold có owner, scope và expiry/review.

### 9.1. Least privilege

Developer có thể cần truy cập traces của service mình; security team có thể cần audit logs; platform operator quản lý backend. Không cấp quyền đọc mọi log/trace cho mọi người chỉ vì họ có quyền deploy ứng dụng.

### 9.2. Legal hold và exception

Legal hold có thể tạm dừng deletion cho phạm vi dữ liệu xác định. Hold cần lý do, người phê duyệt, phạm vi, ngày review và điều kiện release. Không biến hold thành retention vô thời hạn mặc định.

### 9.3. Encryption và key lifecycle

Encryption at rest không thay thế retention. Nếu dùng cryptographic erasure, cần quản lý key theo data class/tenant và chứng minh mọi bản sao ciphertext không thể giải mã sau key destruction. Backup của key có thể làm vô hiệu mục tiêu erase nếu không được xử lý.

## 10. Kiểm thử retention và deletion

Không chỉ kiểm tra cấu hình TTL tồn tại; cần xác minh dữ liệu thực sự biến mất theo semantics backend.

| Test | Mục tiêu | Bằng chứng |
| --- | --- | --- |
| TTL policy test | Cấu hình đúng data class | Backend policy/config |
| Expiry integration test | Dữ liệu hết hạn không còn queryable | Query trước/sau expiry |
| Backup expiry test | Snapshot cũ được xóa theo lịch | Inventory/restore test |
| Restore reconciliation | Restore không hồi sinh expired data | Expiry reconciliation report |
| Redaction test | Secret/PII không được export | Captured telemetry assertions |
| Access test | Role chỉ đọc đúng scope | Authorization tests/audit |
| Legal hold test | Hold chặn deletion đúng phạm vi | Hold/release audit |
| Deletion audit test | Có bằng chứng xóa | Job logs và backend state |

### 10.1. Test redaction trước export

Dùng test exporter hoặc in-memory collector receiver. Tạo telemetry chứa marker giả lập như token-test-value và email giả, sau đó xác minh marker không xuất hiện trong attributes, logs hoặc payload đã export. Không dùng secret thật trong test.

### 10.2. Test TTL có kiểm soát

Dùng retention rất ngắn ở test backend hoặc clock abstraction nếu backend hỗ trợ. Tạo record, truy vấn trước expiry, đợi/advance clock theo test contract và xác minh record không còn queryable. Physical storage có thể được reclaim muộn hơn do compaction; test cần phân biệt logical deletion với physical reclamation.

### 10.3. Test deletion xuyên pipeline

Tạo một synthetic record có correlation marker riêng trong môi trường test. Theo dõi marker qua primary, replica, archive và downstream. Sau deletion, xác minh marker không còn queryable trong các nơi thuộc scope. Không phát tán dữ liệu thật để kiểm tra deletion.

## 11. Troubleshooting data retention

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Storage tăng dù TTL đã cấu hình | TTL chưa áp dụng index mới hoặc compaction backlog | Kiểm tra policy attachment, partitions và compaction |
| Dữ liệu cũ vẫn queryable | TTL tính từ ingest time hoặc job chưa chạy | Kiểm tra timestamp basis và expiry job |
| Primary đã xóa nhưng backup còn | Backup retention độc lập | Lập lịch snapshot expiry và restore reconciliation |
| Dữ liệu xuất hiện lại sau restore | Restore không áp dụng expiry policy | Chạy reconciliation trước khi mở truy cập |
| PII còn trong traces | Attribute capture chưa redact | Filter trước export và kiểm thử payload |
| Log backend có data lâu hơn mong đợi | Index lifecycle policy sai hoặc archive copy | Kiểm tra toàn bộ downstream inventory |
| Metrics lịch sử mất quá sớm | Retention thấp hoặc downsampling sai | Xem lại SLO/reporting needs và tiered storage |
| Trace volume vượt ngân sách | Sampling thấp chưa đủ hoặc spans quá lớn | Kiểm tra traffic, spans/trace và attributes |
| Deletion job chạy nhưng dung lượng không giảm | Tombstones/compaction chưa hoàn tất | Kiểm tra storage engine reclamation |
| Không chứng minh được deletion | Thiếu audit evidence | Ghi job scope, time, policy version và result |
| Legal hold giữ dữ liệu vô hạn | Không có review/expiry owner | Thiết lập review cadence và release process |
| SaaS vẫn giữ bản sao | Vendor policy không đồng bộ | Kiểm tra contract, processor settings và deletion API |

### 11.1. Quy trình điều tra

1. Xác định data class và mục đích lưu.
2. Lập sơ đồ source → Collector → backend → replica/backup/archive/downstream.
3. Xác định TTL clock: event time, ingest time hay index time.
4. Kiểm tra policy có gắn vào mọi index/tenant/stream mới.
5. Kiểm tra expiry jobs, tombstones, compaction và physical reclamation.
6. Tìm bản sao ngoài primary store.
7. Xác minh legal hold hoặc exception có đang áp dụng.
8. Kiểm tra deletion evidence và quyền truy cập.
9. Chạy synthetic deletion test nếu cần xác nhận end-to-end.

## 12. Production checklist

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| Data inventory đầy đủ | Metrics/logs/traces/audit/backup/downstream |
| Purpose và owner xác định | Policy record có người chịu trách nhiệm |
| Retention theo data class | TTL được phê duyệt và cấu hình |
| Sampling tách biệt retention | Trace sampling và backend TTL rõ |
| Redaction trước export | Test không thấy secret/PII marker |
| Metrics downsampling hợp lý | SLI/histogram vẫn phân tích được |
| Log lifecycle rõ | Rollover, hot/warm/cold và expiry |
| Trace lifecycle rõ | Sampling, TTL, block compaction |
| Backup/replica có expiry | Restore không hồi sinh expired data |
| Downstream processor được quản lý | Contract/retention/deletion scope |
| Access control và encryption | Role, audit, at-rest/in-transit |
| Legal hold có review | Owner, scope, review/release |
| Deletion evidence | Job result và policy version |
| Retention drift được cảnh báo | Storage age/expired data monitoring |
| Restore và deletion được test | Evidence từ môi trường test |

## 13. Bài thực hành: thiết kế retention policy cho order-service

**Bối cảnh:** order-service xuất Micrometer metrics, structured logs và OpenTelemetry traces tới Collector. Telemetry được lưu ở metrics backend, log backend và trace backend; một số logs được chuyển tiếp sang SIEM. Logs hiện có request identifiers và traces có database attributes. Storage cost tăng và đội security cần chứng minh dữ liệu hết hạn được xóa khỏi các bản sao.

**Nhiệm vụ:**

1. Lập inventory mọi telemetry source, Collector, backend, replica, backup và downstream.
2. Phân loại metrics, logs, traces, audit records và xác định purpose/owner.
3. Đề xuất retention theo từng data class dựa trên policy tổ chức và yêu cầu điều tra.
4. Thiết kế raw metrics retention cùng downsampling cho trend dài hạn.
5. Đặt logs chi tiết và traces vào TTL phù hợp; tách audit records.
6. Kiểm tra sampling không bị nhầm với retention.
7. Redact token, email, query values và identifiers trước export.
8. Cấu hình rollover/TTL và kiểm tra policy áp dụng cho index/stream mới.
9. Lập lịch backup/archive expiry và restore reconciliation.
10. Thêm access control, encryption, audit và legal hold workflow.
11. Tạo synthetic marker và kiểm thử deletion end-to-end qua backend/replica/SIEM test sink.
12. Viết runbook cho TTL drift, storage growth, deletion failure và restore.

**Kết quả mong đợi:** data inventory, retention policy có owner/purpose/TTL, pipeline redaction, backend lifecycle configuration, deletion evidence và runbook.

## 14. Ghi nhớ

Data retention xác định dữ liệu observability nào được giữ, trong bao lâu, ở đâu, ai truy cập và cách xóa. Metrics, logs, traces, audit records và backups có mục đích/độ nhạy khác nhau nên cần policy riêng. Sampling giảm trace volume trước storage; aggregation/downsampling giảm độ phân giải; TTL xóa dữ liệu đã lưu. Ba cơ chế này không thay thế nhau.

Giảm dữ liệu ngay tại nguồn, redact trước export và tránh thu thập secrets/PII không cần thiết. Theo dõi TTL ở primary, replicas, queues, backups, archives và downstream processors. Kiểm thử logical deletion, physical reclamation, restore reconciliation và audit evidence. Retention phải dựa trên mục đích, yêu cầu tổ chức/pháp lý và data classification; không có một thời hạn chung phù hợp cho mọi hệ thống. Dùng metrics để theo dõi storage/expiry, logs để ghi nhận lifecycle jobs và audit, traces để điều tra request trong khoảng thời gian được policy cho phép.

**Tài liệu tham khảo:**
- [OpenTelemetry — Collector Processors](https://opentelemetry.io/docs/collector/components/processor/)
- [OpenTelemetry — Collector Configuration](https://opentelemetry.io/docs/collector/configuration/)
- [Prometheus — Storage](https://prometheus.io/docs/prometheus/latest/storage/)
- [Grafana Loki — Retention](https://grafana.com/docs/loki/latest/operations/storage/retention/)
- [Grafana Tempo — Retention](https://grafana.com/docs/tempo/latest/configuration/manifest/)
- [Elasticsearch — Data Streams and ILM](https://www.elastic.co/guide/en/elasticsearch/reference/current/index-lifecycle-management.html)
- [Micrometer Observation — Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)

