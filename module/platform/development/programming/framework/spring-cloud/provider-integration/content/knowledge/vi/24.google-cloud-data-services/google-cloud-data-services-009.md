# Kiểm soát chi phí truy vấn, hạn ngạch và tài nguyên kết nối

## Mục tiêu bài học

Module **SPRING_CLOUD_PROVIDER_INTEGRATION** thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng. Khi ứng dụng dùng dữ liệu Google Cloud, chi phí và khả năng phục vụ không chỉ phụ thuộc vào câu SQL. Chúng còn phụ thuộc mô hình tính phí, lượng dữ liệu quét, quota của API, số job chạy đồng thời, số kết nối database, pool trong từng instance ứng dụng và cách autoscaling tạo thêm client.

Bài học tập trung vào ba nhóm tài nguyên thường bị nhầm lẫn:

- **Chi phí truy vấn:** tiền xử lý dữ liệu hoặc slot compute, lưu trữ và truyền dữ liệu.
- **Quota và system limit:** giới hạn API, query usage, job, instance hoặc tốc độ request.
- **Tài nguyên kết nối:** connection pool của Cloud SQL, session/channel của Spanner và client/job concurrency của BigQuery.

Sau bài học, bạn có thể:

1. Phân biệt on-demand pricing với capacity-based pricing của BigQuery.
2. Giảm bytes scanned bằng partition pruning, clustering và chọn cột cần thiết.
3. Ước lượng truy vấn bằng dry run và đặt maximum bytes billed.
4. Thiết lập custom query quota, budget alert và theo dõi INFORMATION_SCHEMA.JOBS.
5. Phân biệt quota có thể điều chỉnh với system limit cố định.
6. Tính tổng số kết nối Cloud SQL khi ứng dụng scale nhiều instance.
7. Cấu hình HikariCP và Cloud SQL Java Connector trong Spring Boot.
8. Hiểu multiplexed session và dynamic channel pool của Spanner Java client.
9. Theo dõi pool, quota, latency và xử lý lỗi quá tải bằng backoff.
10. Thiết kế test để chứng minh hệ thống không vượt ngân sách truy vấn hoặc connection budget.

## 1. Mô hình tài nguyên và chi phí

### 1.1. Phân biệt cost, quota, limit và pool

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Cost | Tài nguyên đã tiêu thụ được tính phí theo pricing model | Bytes billed của BigQuery, slot capacity, Cloud SQL instance và storage |
| Quota | Ngân sách sử dụng được áp dụng theo project, user hoặc API trong một khoảng thời gian | Query usage per day, Cloud SQL Admin API requests |
| System limit | Giới hạn kỹ thuật cố định hoặc không thể tự điều chỉnh qua quota request | Giới hạn response size hoặc giới hạn cấu trúc của một API |
| Connection/session pool | Tài nguyên client giữ hoặc mượn để gửi request tới database | HikariCP connections, Spanner multiplexed session và gRPC channels |

Một truy vấn có thể rẻ nhưng vẫn bị từ chối vì quota đã hết. Ngược lại, quota còn nhiều không có nghĩa ứng dụng đủ connection hoặc slot để xử lý thêm workload. Khi điều tra sự cố, cần xác định lớp nào đang cạn trước khi tăng quota hoặc mở rộng pool.

### 1.2. Ba nhóm dịch vụ dữ liệu

| Dịch vụ | Tài nguyên chính | Rủi ro cần kiểm soát |
| --- | --- | --- |
| BigQuery | Bytes scanned, slots, query jobs, API requests, storage | Query quét quá nhiều dữ liệu, job queue, quota hoặc reservation thiếu capacity |
| Cloud SQL | Database connections, CPU, memory, storage, Cloud SQL Admin API | Pool nhân lên theo số instance, hết max_connections, connector refresh hoặc login rate quá cao |
| Cloud Spanner | Transactions, multiplexed sessions, gRPC channels, compute capacity | Tạo nhiều client, channel congestion, transaction contention hoặc capacity không đủ |

Không dùng một con số pool chung cho cả ba dịch vụ. BigQuery là dịch vụ phân tích theo job; Cloud SQL là database quan hệ có giới hạn kết nối; Spanner dùng client library quản lý session và channel theo mô hình riêng.

## 2. Kiểm soát chi phí truy vấn BigQuery

### 2.1. Hiểu mô hình tính phí

BigQuery có hai mô hình tính compute phổ biến:

- **On-demand:** tính theo lượng dữ liệu được xử lý/billed bởi query. Đây là mô hình cần chú ý total_bytes_billed, dry run, maximumBytesBilled và custom query quota.
- **Capacity-based:** trả cho compute capacity (slots/reservations hoặc edition tương ứng). Trong mô hình này, total_slot_ms, reservation utilization và concurrency quan trọng hơn bytes billed để đánh giá compute usage.

Chi phí lưu trữ là nhóm riêng. Tối ưu query không tự động giảm storage bill; cần quản lý retention, partition expiration, table expiration và storage billing model.

Không quy đổi total_slot_ms thành một số tiền cố định cho mọi workload. Slot milliseconds là chỉ số sử dụng compute; chi phí thực tế phụ thuộc pricing model, edition, reservation và cam kết capacity của project.

### 2.2. Chỉ đọc những cột cần thiết

BigQuery lưu dữ liệu theo dạng columnar. Với on-demand query, chọn nhiều cột hơn làm tăng lượng dữ liệu phải đọc ngay cả khi ứng dụng chỉ hiển thị một phần kết quả.

Không nên:

~~~sql
SELECT *
FROM `acme-analytics.sales.orders`
WHERE order_date >= DATE '2026-01-01';
~~~

Nên chọn đúng cột:

~~~sql
SELECT
  order_id,
  customer_id,
  order_date,
  total_amount
FROM `acme-analytics.sales.orders`
WHERE order_date >= DATE '2026-01-01';
~~~

Nếu schema thay đổi thường xuyên, có thể dùng SELECT * EXCEPT (...) nhưng vẫn nên xác định rõ các cột không cần đọc. Đối với API phục vụ dashboard, tránh trả payload rộng hơn nhu cầu của client.

### 2.3. Partition pruning

Partitioning chia bảng thành các vùng dữ liệu theo cột partition, thường là ngày/giờ hoặc ingestion time. Khi query có predicate phù hợp trên cột partition, BigQuery có thể bỏ qua partition không liên quan; bytes scanned và query cost giảm.

Ví dụ bảng orders partition theo order_date:

~~~sql
SELECT
  customer_id,
  SUM(total_amount) AS revenue
FROM `acme-analytics.sales.orders`
WHERE order_date >= DATE '2026-10-01'
  AND order_date < DATE '2026-11-01'
GROUP BY customer_id;
~~~

Predicate trên partition column nên trực tiếp và có khoảng thời gian cụ thể. Nếu bọc cột partition trong biểu thức phức tạp hoặc dùng điều kiện không thể pruning, query có thể đọc nhiều partition hơn dự kiến.

Đặt yêu cầu bắt buộc lọc partition cho workload lớn khi phù hợp. Với bảng partition theo ingestion time, cân nhắc _PARTITIONDATE hoặc _PARTITIONTIME theo loại partition đã tạo.

### 2.4. Clustering

Clustering sắp xếp dữ liệu theo các cột thường được lọc hoặc join. BigQuery có thể prune block dựa trên điều kiện clustering để giảm bytes đọc thực tế.

Ví dụ bảng partition theo ngày và cluster theo customer_id, region:

~~~sql
SELECT order_id, total_amount
FROM `acme-analytics.sales.orders`
WHERE order_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-07'
  AND customer_id = 'cust-1001';
~~~

Partition pruning loại ngày ngoài khoảng; clustering giúp giảm block phải đọc bên trong các partition còn lại. Chọn clustering columns theo pattern truy vấn thực tế, không thêm nhiều cột chỉ để tối ưu chung.

### 2.5. LIMIT không phải cơ chế chặn chi phí

Với bảng không clustered, LIMIT 100 chỉ giới hạn số dòng trả về; nó không nhất thiết giảm bytes phải đọc. Không dùng LIMIT làm guardrail chi phí cho query quét bảng lớn.

Khi cần xem dữ liệu mẫu, dùng Preview, bq head hoặc API đọc một phần dữ liệu. Khi cần giới hạn chi phí thật, dùng partition filter, dry run và maximum bytes billed.

### 2.6. Tránh tính toán lặp lại

Nếu nhiều truy vấn thực hiện cùng phép biến đổi nặng:

- Materialize kết quả trung gian vào bảng phù hợp.
- Dùng scheduled query hoặc materialized view khi workload lặp lại và semantics cho phép.
- Tạo bảng aggregate cho dashboard đọc thường xuyên.
- Chỉ refresh phần dữ liệu thay đổi nếu pipeline hỗ trợ incremental processing.
- Đánh giá query cache nhưng không dựa vào cache như một bảo đảm chi phí.

Materialize có thể tăng storage cost, nhưng storage của bảng kết quả thường thấp hơn việc lặp lại một phép scan/transform lớn. Cần so sánh tổng compute + storage + refresh frequency.

### 2.7. Federated query và dữ liệu ngoài

Với external/federated query, lượng bytes có thể không ước lượng đầy đủ trước khi chạy. Dry run có thể báo 0 hoặc một lower bound dù query thực tế vẫn đọc dữ liệu và phát sinh phí. Không dùng dry run làm guard duy nhất cho query đọc Cloud SQL, Cloud Storage hoặc nguồn ngoài.

Kiểm soát thêm:

- Giới hạn ngày/phân vùng hoặc phạm vi object được đọc.
- Đặt location tương thích giữa BigQuery và nguồn dữ liệu khi có thể.
- Theo dõi chi phí truyền dữ liệu và cross-region.
- Cân nhắc load dữ liệu vào BigQuery trước khi chạy phân tích lặp lại.

## 3. Ước lượng query và đặt giới hạn mỗi job

### 3.1. Dry run

Dry run kiểm tra cú pháp và ước lượng bytes sẽ được xử lý mà không thực thi query. Dry run không dùng query slots và không bị tính phí query processing.

Java BigQuery client:

~~~java
import com.google.cloud.bigquery.BigQuery;
import com.google.cloud.bigquery.BigQueryOptions;
import com.google.cloud.bigquery.Job;
import com.google.cloud.bigquery.JobInfo;
import com.google.cloud.bigquery.JobStatistics;
import com.google.cloud.bigquery.QueryJobConfiguration;
import com.google.cloud.bigquery.QueryParameterValue;

public long estimateBytes(BigQuery bigQuery, String sql) {
    QueryJobConfiguration dryRunConfig =
            QueryJobConfiguration.newBuilder(sql)
                    .setUseLegacySql(false)
                    .setDryRun(true)
                    .setUseQueryCache(false)
                    .build();

    Job job = bigQuery.create(JobInfo.of(dryRunConfig));
    JobStatistics.QueryStatistics statistics = job.getStatistics();
    return statistics.getTotalBytesProcessed();
}

// BigQuery client được tạo một lần và tái sử dụng trong ứng dụng.
BigQuery bigQuery = BigQueryOptions.getDefaultInstance().getService();
~~~

Đặt location phù hợp với dataset/job khi chạy ở region khác US/EU. Không tạo BigQuery client mới cho mỗi request HTTP; giữ client như một bean dùng chung.

### 3.2. Giới hạn bytes billed cho mỗi query

Với on-demand pricing, maximumBytesBilled khiến query bị từ chối trước khi chạy nếu ước lượng bytes billed vượt ngưỡng. Khi bị từ chối, query không phát sinh phí xử lý.

~~~java
long maxBytesBilled = 50L * 1024 * 1024 * 1024; // 50 GiB

QueryJobConfiguration guardedConfig =
        QueryJobConfiguration.newBuilder(sql)
                .setUseLegacySql(false)
                .setMaximumBytesBilled(maxBytesBilled)
                .build();

// Gửi guardedConfig qua BigQuery client sau khi ứng dụng đã kiểm tra
// chính sách và query parameters.
~~~

Đây là guard cho từng job, không phải quota tổng của project. Một service có thể gửi nhiều job, mỗi job đều nằm dưới ngưỡng nhưng tổng usage vẫn rất lớn.

Ước lượng của query trên clustered table có thể là upper bound trước khi block pruning hoàn tất. Vì vậy một query có thể bị từ chối dù bytes thực tế sau khi chạy có thể thấp hơn ngưỡng. Đặt ngưỡng dựa trên pattern query và kiểm tra error bytesBilledLimitExceeded.

### 3.3. Kết hợp dry run và maximum bytes billed

Quy trình đề xuất cho endpoint nhận SQL/report request:

1. Chọn SQL template được kiểm soát trong ứng dụng.
2. Bind parameter, không nối chuỗi từ input người dùng.
3. Chạy dry run và lấy estimated bytes.
4. So sánh estimate với ngưỡng theo endpoint/tenant/job type.
5. Nếu vượt ngưỡng, trả lỗi rõ ràng hoặc yêu cầu người dùng thu hẹp phạm vi.
6. Nếu đạt, submit job với maximumBytesBilled.
7. Lưu job ID, caller, label, thời gian và usage sau khi hoàn tất.

Dry run có thể không đưa ra estimate đáng tin cậy cho external/federated query hoặc bảng có row-level security. Với những trường hợp này, dùng policy khác như allowlist query, giới hạn nguồn/phạm vi dữ liệu và kiểm tra usage sau chạy.

### 3.4. Query parameters và job labels

Không nối giá trị filter từ HTTP request trực tiếp vào SQL. Dùng named parameters:

~~~java
import com.google.cloud.bigquery.BigQuery;
import com.google.cloud.bigquery.JobId;
import com.google.cloud.bigquery.BigQueryOptions;
import com.google.cloud.bigquery.QueryJobConfiguration;
import com.google.cloud.bigquery.QueryParameterValue;
import com.google.cloud.bigquery.TableResult;
import java.util.Map;
import java.util.UUID;

BigQuery bigQuery = BigQueryOptions.getDefaultInstance().getService();
QueryJobConfiguration config =
        QueryJobConfiguration.newBuilder("""
            SELECT order_id, total_amount
            FROM `acme-analytics.sales.orders`
            WHERE customer_id = @customerId
              AND order_date >= @fromDate
            """)
            .setUseLegacySql(false)
            .addNamedParameter(
                    "customerId",
                    QueryParameterValue.string(customerId))
            .addNamedParameter(
                    "fromDate",
                    QueryParameterValue.date(fromDate.toString()))
            .setMaximumBytesBilled(maxBytesBilled)
            .setLabels(Map.of(
                    "service", "order-reporting",
                    "environment", "production"))
            .build();

// Với dataset ở region khác US/EU, cung cấp location trong JobId.
JobId jobId = JobId.newBuilder()
        .setLocation("asia-southeast1")
        .setJob("order-report-" + UUID.randomUUID())
        .build();
TableResult results = bigQuery.query(config, jobId);
~~~

Job labels giúp phân tích usage theo service, môi trường hoặc workload. Có thể đặt labels trên QueryJobConfiguration hoặc JobInfo tùy cách submit job. Label phải tuân theo quy tắc tên/giá trị của BigQuery và không chứa dữ liệu cá nhân hoặc secret. Dùng label có cardinality vừa phải; không tạo label value duy nhất cho mọi request nếu sẽ làm khó báo cáo.

## 4. Quota BigQuery và giới hạn API

### 4.1. Custom query quota theo ngày

Với on-demand pricing, BigQuery có quota query usage theo ngày:

| Quota | Mặc định được tài liệu công bố | Phạm vi |
| --- | --- | --- |
| QueryUsagePerDay | 200 TiB mỗi project mỗi ngày | Tổng usage của tất cả người dùng trong project |
| QueryUsagePerUserPerDay | Không giới hạn theo mặc định | Áp dụng mức quota riêng cho từng user/service account trong project |

Có thể đặt custom quota thấp hơn hoặc cao hơn theo nhu cầu được hỗ trợ. Quota ngày reset lúc nửa đêm theo Pacific Time, không phải múi giờ của ứng dụng. Hai quota này chỉ áp dụng cho on-demand query pricing.

Custom quota là safeguard gần đúng, không phải hard billing cap tuyệt đối. BigQuery có thể đôi khi cho phép query vượt mức đã đặt. Nếu cần kiểm soát chặt hơn cho từng job, kết hợp maximumBytesBilled.

Không thể đặt quota riêng cho một user hoặc service account cụ thể bằng cách tạo một override cá nhân; user-level custom quota được áp dụng đồng nhất theo cơ chế quota của project.

### 4.2. Cấu hình custom quota

Trong Google Cloud Console:

1. Mở **IAM & Admin → Quotas & System Limits**.
2. Lọc service là **BigQuery API**.
3. Tìm quota **Query usage per day** và/hoặc **Query usage per day per user**.
4. Chọn quota, bấm Edit và bỏ lựa chọn Unlimited nếu đang bật.
5. Nhập giới hạn mới theo TiB.
6. Submit thay đổi và theo dõi trạng thái quota.

Principal thay đổi quota cần quyền serviceusage.quotas.update, thường thông qua role Quota Administrator hoặc quyền tương đương. Không cấp role quản trị quota cho runtime service account của ứng dụng.

### 4.3. Quota API và job concurrency

BigQuery còn có quota cho API requests, query jobs, pending jobs, concurrent jobs và một số phương thức đọc dữ liệu. Ví dụ, tài liệu BigQuery API core mô tả giới hạn request theo user/method và concurrent request; các giá trị thay đổi theo loại API, region, project và pricing model.

Không hard-code quota vào logic nghiệp vụ như một hằng số vĩnh viễn. Trước khi phát hành, kiểm tra trang Quotas & Limits của project và tài liệu hiện hành. Khi nhận quotaExceeded, rateLimitExceeded hoặc HTTP 429:

- Giảm tốc độ submit job và số request song song.
- Dùng exponential backoff có jitter cho lỗi tạm thời.
- Không retry vô hạn hoặc retry lỗi cú pháp/permission.
- Giữ job ID ổn định khi retry thao tác submit để tránh tạo job trùng.
- Tách workload batch khỏi interactive workload nếu cần kiểm soát queue.

### 4.4. Quota khác với slot capacity

Quota giới hạn lượng request hoặc usage trong phạm vi nhất định. Slot capacity là compute resource mà BigQuery dùng để thực thi query. Một workload có thể còn quota nhưng chậm vì slot contention hoặc reservation không đủ; ngược lại, reservation còn slot nhưng API quota đã bị chạm.

Khi dùng capacity-based pricing:

- Theo dõi slot utilization và reservation assignment.
- Phân biệt job đang pending với job đang chạy.
- Đánh giá workload theo thời gian, concurrency và slot milliseconds.
- Không dùng maximumBytesBilled như cơ chế giới hạn tiền của reservation pricing.

## 5. Theo dõi usage BigQuery bằng INFORMATION_SCHEMA

### 5.1. Báo cáo bytes billed theo user

BigQuery lưu telemetry của query jobs trong INFORMATION_SCHEMA.JOBS*. Ví dụ dưới đây tổng hợp bytes billed theo user trong 7 ngày:

~~~sql
SELECT
  user_email,
  COUNT(*) AS query_count,
  SUM(total_bytes_billed) AS bytes_billed,
  SUM(total_slot_ms) AS total_slot_ms
FROM
  `region-asia-southeast1`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE
  creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  AND job_type = 'QUERY'
  AND state = 'DONE'
  AND (statement_type IS NULL OR statement_type != 'SCRIPT')
GROUP BY user_email
ORDER BY bytes_billed DESC;
~~~

Thay asia-southeast1 bằng region chứa job. Location thực thi query phải khớp location của INFORMATION_SCHEMA view. Điều kiện trên creation_time giúp giới hạn khoảng thời gian cần đọc.

### 5.2. Vì sao loại SCRIPT?

Multi-statement query có job cha với statement_type = SCRIPT và các child jobs. Job cha có thể chứa tổng usage của các child jobs. Nếu cộng cả cha và con, báo cáo có thể double-count. Khi tổng hợp chi phí/slot usage, loại SCRIPT hoặc xây logic cộng job cha/con phù hợp.

### 5.3. Những trường cần theo dõi

| Trường | Ý nghĩa | Dùng để |
| --- | --- | --- |
| total_bytes_processed | Bytes đã xử lý | Đánh giá scan volume |
| total_bytes_billed | Bytes được tính phí trong on-demand model | Báo cáo billed usage |
| total_slot_ms | Slot milliseconds | Phân tích compute consumption |
| user_email | Identity gửi job | Xác định caller/service account tiêu thụ |
| job_id | Định danh job | Truy vết job |
| reservation_id | Reservation chạy job | Phân tích workload theo capacity |
| query_info.resource_warning | Cảnh báo tài nguyên của query | Tìm query có resource pressure |
| error_result | Lỗi job | Phân biệt quota, bytes cap và lỗi SQL |

total_bytes_billed có thể rỗng với query đọc bảng có row-level access policy. Trong capacity pricing, trường này mang tính thông tin; không phải số tiền bị tính theo bytes. total_slot_ms cũng không trực tiếp bằng tiền nếu chưa xét pricing model.

### 5.4. Monitoring và cảnh báo

Tạo dashboard theo:

- Bytes billed theo project, service account, label và giờ/ngày.
- Query count, failed jobs và quota errors.
- Slot milliseconds và job pending/running.
- Query latency p50/p95/p99.
- Top query theo bytes billed hoặc slot usage.
- Tỷ lệ job bị từ chối do maximumBytesBilled.

Kết hợp INFORMATION_SCHEMA với Cloud Monitoring và Cloud Billing reports. INFORMATION_SCHEMA phục vụ telemetry chi tiết theo job; Cloud Billing phản ánh dữ liệu billing và có độ trễ báo cáo riêng.

## 6. Budget, reservations và chính sách chi phí

### 6.1. Budget alert không mặc định chặn usage

Cloud Billing budget có thể theo dõi chi phí theo billing account, project, service hoặc label và gửi cảnh báo theo ngưỡng thực tế/dự báo. Tuy nhiên, **alerts-only budget không tự động dừng dịch vụ hoặc đặt hard cap**. Billing data cũng có độ trễ; khi nhận cảnh báo, một phần usage đã phát sinh có thể chưa hiển thị.

Với dịch vụ hỗ trợ spend cap budget, có thể cấu hình giới hạn chi tiêu theo một project và một service đủ điều kiện. Cơ chế này dùng estimated gross cost để thực thi, có độ trễ và không ngăn các request đang chạy hoàn tất. Không coi spend cap là cơ chế thay thế maximum bytes billed, custom quota và guardrail trong ứng dụng.

### 6.2. Kết hợp nhiều lớp kiểm soát

| Lớp | Cơ chế | Phạm vi |
| --- | --- | --- |
| Query design | Partition, clustering, chọn cột, materialize | Giảm lượng dữ liệu cần xử lý |
| Per-job | Dry run và maximum bytes billed | Chặn query on-demand vượt ngưỡng |
| Project/user | Custom daily query quota | Hạn chế tổng query usage trong ngày |
| Compute capacity | Reservation/slot assignment | Phân bổ compute và kiểm soát concurrency |
| Billing | Budget alert hoặc spend cap nếu đủ điều kiện | Theo dõi chi phí tổng thể và cảnh báo |
| Application | Allowlist query, rate limit, queue, authorization | Chặn request không phù hợp trước khi tạo job |

Không một lớp nào thay thế hoàn toàn lớp khác. Ví dụ, quota ngày có thể chặn cả nhóm phân tích khi một user dùng hết quota; per-job cap không kiểm soát được số lượng job nhỏ; budget alert không nhất thiết chặn query.

### 6.3. Chọn on-demand hay capacity

On-demand phù hợp workload biến động, dễ bắt đầu và dễ gắn guardrail bằng bytes. Capacity-based phù hợp workload ổn định hoặc cần throughput/latency dự đoán hơn, nhưng cần theo dõi slot utilization, reservation assignment và concurrency.

Trước khi đổi pricing model:

1. Tổng hợp query usage và slot milliseconds trong một khoảng thời gian đại diện.
2. Tách workload interactive, scheduled và batch.
3. Đánh giá peak concurrency và giờ cao điểm.
4. Ước lượng reservation/edition phù hợp với workload.
5. Kiểm tra job có bị queue hoặc thiếu slot không.
6. So sánh chi phí capacity với on-demand, bao gồm storage và workload tăng trưởng.

## 7. Cloud SQL: giới hạn kết nối và connection budget

### 7.1. Connection là tài nguyên của cả ứng dụng và database

Mỗi database connection tiêu thụ tài nguyên ở client và server. Cloud SQL có giới hạn kết nối tổng thể theo engine, cấu hình instance và memory. Tăng số connection không tự động tăng throughput; nếu database thiếu CPU/memory, nhiều connection hơn có thể làm contention và latency tăng.

Với Cloud SQL MySQL, kiểm tra giới hạn hiện tại:

~~~sql
SHOW VARIABLES LIKE 'max_connections';
~~~

Với Cloud SQL PostgreSQL:

~~~sql
SELECT name, setting
FROM pg_settings
WHERE name = 'max_connections';
~~~

Giá trị mặc định/khả năng tăng phụ thuộc machine type và memory. Với PostgreSQL, còn phải tính backend processes như autovacuum workers và worker processes khi điều chỉnh max_connections. Không copy một con số từ môi trường khác vào production.

### 7.2. Tính tổng kết nối khi scale ngang

HikariCP pool nằm trong từng process. Nếu có nhiều pod/container, mỗi process có một pool riêng. Tổng connection tiềm năng phải tính trên toàn bộ fleet:

~~~text
Total peak connections
  = max application instances x maximumPoolSize
  + background workers
  + scheduled jobs
  + migration/admin connections
  + old/new instances during rolling deployment
~~~

Ví dụ:

| Thành phần | Số lượng | Pool/connections mỗi instance | Tổng tối đa |
| --- | ---: | ---: | ---: |
| Cloud Run/GKE application | 12 | 5 | 60 |
| Worker nền | 3 | 4 | 12 |
| Migration/admin job | 1 | 3 | 3 |
| Dự phòng khi rollout | 2 | 5 | 10 |
| **Tổng ước lượng** | | | **85** |

Nếu database chỉ cho phép 100 client connections, cấu hình trên đã sử dụng phần lớn ngân sách. Cần để buffer cho failover, maintenance, DBA, monitoring và các workload khác. Đừng đặt maximumPoolSize bằng max_connections của database.

Cloud Run có giới hạn 100 connections trên mỗi container instance cho **built-in Cloud SQL connection**. Khi dùng Cloud SQL Auth Proxy sidecar, Cloud SQL Language Connector hoặc kết nối IP trực tiếp, giới hạn built-in này không áp dụng; tuy nhiên giới hạn max_connections của database vẫn áp dụng.

### 7.3. HikariCP trong Spring Boot

Spring Boot dùng HikariCP làm connection pool mặc định trong nhiều cấu hình JDBC. Ví dụ dưới đây là điểm bắt đầu để thử tải, không phải cấu hình tối ưu cho mọi instance:

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 5
      minimum-idle: 1
      connection-timeout: 10000
      idle-timeout: 600000
~~~

Ý nghĩa:

| Thuộc tính | Tác dụng |
| --- | --- |
| maximum-pool-size | Số connection tối đa trong pool của một process |
| minimum-idle | Số connection idle mục tiêu mà pool duy trì |
| connection-timeout | Thời gian tối đa chờ lấy connection từ pool trước khi lỗi |
| idle-timeout | Thời gian connection idle có thể ở trong pool khi số idle vượt minimum-idle |

Khi ứng dụng chạy serverless hoặc scale-to-zero, minimum-idle lớn có thể tạo connection ngay khi instance khởi động. Khi scale out nhiều instance cùng lúc, điều này tạo connection storm. Có thể đặt minimum-idle thấp hơn, thậm chí 0 nếu workload phù hợp, rồi đo cold-start và connection latency.

### 7.4. Giữ connection trong thời gian ngắn

Luôn đóng connection, statement và result set bằng try-with-resources để connection được trả về pool:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement(
                     "SELECT status FROM orders WHERE order_id = ?")) {
    statement.setString(1, orderId);
    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            return resultSet.getString("status");
        }
    }
}
~~~

Không giữ connection trong lúc gọi HTTP API bên ngoài, gửi email hoặc chờ người dùng. Lấy connection ngay trước transaction/query và trả lại ngay sau khi xong. Connection leak khiến pool hết connection dù database còn capacity.

### 7.5. Hạn chế transaction dài

Transaction dài giữ connection và lock lâu hơn. Hãy:

- Giữ transaction ngắn, không thực hiện network call trong transaction.
- Chia batch lớn thành nhiều transaction nhỏ khi semantics nghiệp vụ cho phép.
- Đặt timeout cho query và transaction.
- Chỉ retry transaction từ đầu khi lỗi có thể retry, không tiếp tục giữa transaction đã bị abort.
- Thiết kế write idempotent nếu client không biết chắc commit đã thành công trước khi connection bị ngắt.

## 8. Cloud SQL Java Connector và quota kết nối

### 8.1. Connector không thay connection pool

Cloud SQL Java Connector/Auth Proxy tạo đường kết nối được xác thực và mã hóa tới Cloud SQL. Connector không phải connection pool thay thế HikariCP. Kiến trúc thường gồm:

~~~text
Spring Boot DataSource
        |
      HikariCP
        |
 JDBC driver + Cloud SQL Java Connector
        |
 Cloud SQL instance
~~~

Ứng dụng vẫn phải giới hạn pool và tổng connection theo fleet. Không tạo connector hoặc DataSource mới cho từng HTTP request.

### 8.2. Cấu hình Spring Boot với PostgreSQL Socket Factory

Thêm dependency PostgreSQL Socket Factory tương thích với Java Connector version của dự án. Cấu hình ví dụ cho IAM database authentication:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql:///APP_DATABASE?cloudSqlInstance=PROJECT_ID:REGION:INSTANCE_NAME&socketFactory=com.google.cloud.sql.postgres.SocketFactory
    username: IAM_DATABASE_USER
    hikari:
      maximum-pool-size: 5
      minimum-idle: 1
      connection-timeout: 10000
      data-source-properties:
        enableIamAuth: true
        sslmode: disable
        cloudSqlRefreshStrategy: lazy
~~~

Thay APP_DATABASE, PROJECT_ID, REGION, INSTANCE_NAME và IAM_DATABASE_USER bằng cấu hình môi trường. Với database user/password thông thường, lấy password từ Secret Manager hoặc cơ chế secret injection được quản lý; không commit password vào YAML.

Cloud SQL Java Connector xử lý TLS, do đó driver-level SSL thường được tắt theo hướng dẫn của connector. Xác minh thuộc tính cụ thể theo engine và phiên bản JDBC driver đang dùng.

### 8.3. Connector refresh và Cloud SQL Admin API quota

Cloud SQL Auth Proxy và Language Connectors sử dụng quota của Cloud SQL Admin API. Connector refresh metadata/certificate khoảng mỗi giờ; mỗi refresh thường thực hiện hai API calls cho mỗi process và mỗi instance được kết nối.

Ước lượng đơn giản:

~~~text
Admin API calls per hour
  = connector processes
  x Cloud SQL instances per process
  x 2 calls per refresh
~~~

Ví dụ 4 connector processes cùng kết nối 3 Cloud SQL instances có thể tạo khoảng 24 API calls mỗi giờ cho refresh. Khi autoscaling nhanh, số connector process tăng có thể tạo burst API request. Dùng một DataSource/connector lifecycle ổn định trong mỗi process, theo dõi Admin API quota và tránh khởi tạo connector theo request.

### 8.4. Lazy refresh cho serverless

Trong môi trường serverless có CPU throttling khi instance idle, Cloud SQL Connector có thể cấu hình refresh strategy là lazy để refresh khi cần thay vì chạy refresh nền theo lịch. Điều này giúp tránh background refresh bị trì hoãn hoặc tiêu thụ CPU ngoài thời gian xử lý request.

Không áp dụng lazy refresh một cách máy móc cho mọi workload. Đo connection establishment latency sau idle và cân nhắc trade-off giữa cold connection với background refresh.

### 8.5. IAM database authentication

IAM database authentication giúp workload dùng IAM identity thay cho password tĩnh, nhưng không loại bỏ database connection limits. Tài liệu Cloud SQL cho MySQL nêu quota authorization login IAM là 12.000 logins mỗi phút cho mỗi instance; kiểm tra tài liệu theo engine đang sử dụng trước khi áp dụng con số này. Dù quota cao, không nên tạo login mới cho mỗi query.

Dùng pool để tái sử dụng connection đã xác thực. Khi token/credential hết hạn hoặc connection bị đóng, connector và pool sẽ tạo connection mới theo cơ chế của thư viện.

## 9. Cloud Spanner: multiplexed sessions và gRPC channels

### 9.1. Spanner không dùng HikariCP như Cloud SQL

Spanner Java client không phải JDBC database thông thường trong đường truy cập native. Client quản lý session và gRPC channel. Không đặt HikariCP maximumPoolSize rồi giả định nó điều khiển Spanner concurrency.

Với Java client library phiên bản 6.98.0 trở lên, multiplexed sessions được bật mặc định. Một multiplexed session có thể phục vụ nhiều transaction đồng thời; ứng dụng không cần tự tạo một session cho mỗi request.

### 9.2. Tái sử dụng Spanner client

Tạo Spanner client và DatabaseClient một lần trong Spring context, sau đó dùng lại:

~~~java
import com.google.cloud.spanner.DatabaseClient;
import com.google.cloud.spanner.DatabaseId;
import com.google.cloud.spanner.Spanner;
import com.google.cloud.spanner.SpannerOptions;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SpannerConfiguration {

    @Bean(destroyMethod = "close")
    Spanner spannerClient(
            @Value("${spring.cloud.gcp.project-id}") String projectId) {
        SpannerOptions options = SpannerOptions.newBuilder()
                .setProjectId(projectId)
                .enableDynamicChannelPool()
                .build();
        return options.getService();
    }

    @Bean
    DatabaseClient databaseClient(
            Spanner spanner,
            @Value("${spring.cloud.gcp.project-id}") String projectId,
            @Value("${app.spanner.instance-id}") String instanceId,
            @Value("${app.spanner.database-id}") String databaseId) {
        return spanner.getDatabaseClient(
                DatabaseId.of(projectId, instanceId, databaseId));
    }
}
~~~

Trong ứng dụng thật, cung cấp projectId, instanceId và databaseId qua configuration properties hoặc constructor-bound configuration class. Không tạo Spanner client trong mỗi method nghiệp vụ.

### 9.3. Dynamic channel pool

Dynamic channel pooling không bật mặc định trong Java client. Nếu không bật, client thường dùng 4 gRPC channels (8 nếu dùng gRPC-GCP extension). Bật dynamic channel pool để thư viện tự điều chỉnh số channel theo workload:

~~~java
SpannerOptions options = SpannerOptions.newBuilder()
        .setProjectId(projectId)
        .enableDynamicChannelPool()
        .build();
~~~

Mỗi gRPC channel sử dụng một TCP connection. Mỗi RPC cần thread để thực thi; do đó số channel, concurrency và thread pool đều ảnh hưởng tài nguyên client. Dynamic channel pool có thể giúp tránh thiếu hoặc thừa channel khi tải thay đổi.

Không đặt setNumChannels nếu muốn dùng dynamic channel pool, vì cấu hình số channel tĩnh sẽ vô hiệu hóa cơ chế dynamic.

### 9.4. Không áp dụng cấu hình session pool cũ một cách máy móc

Một số ví dụ cũ cấu hình SessionPoolOptions với minSessions/maxSessions. Trong Java client mới, multiplexed session được dùng mặc định và các tùy chọn session pool cũ đã deprecated/không còn chức năng theo API hiện hành. Kiểm tra phiên bản client trước khi sao chép cấu hình cũ từ blog hoặc sample.

Với client cũ chưa hỗ trợ multiplexed sessions, sizing session pool cần dựa trên số transaction đồng thời của **một application instance**. Tăng pool vượt quá concurrency mà instance xử lý được sẽ tiêu thụ thêm tài nguyên và có thể làm hệ thống kém ổn định.

### 9.5. Transaction contention và retry

Spanner có thể abort read-write transaction do contention. Dùng transaction API của client library để retry transaction theo semantics được hỗ trợ; callback transaction phải có thể chạy lại an toàn.

Không đặt side effect ngoài Spanner (gửi email, gọi payment API) bên trong transaction callback có thể retry. Ghi ý định side effect vào outbox trong transaction rồi xử lý ở bước riêng.

Theo dõi transaction aborts, latency, CPU utilization, request rate và channel saturation. Khi tăng concurrency, đánh giá cả capacity của instance Spanner lẫn khả năng client gửi RPC.

## 10. Retry, backoff và xử lý quá tải

### 10.1. Phân loại lỗi trước khi retry

| Lỗi | Hướng xử lý |
| --- | --- |
| HTTP 429 hoặc RESOURCE_EXHAUSTED | Giảm tốc độ, backoff có jitter, kiểm tra quota/capacity |
| UNAVAILABLE hoặc lỗi mạng tạm thời | Retry có giới hạn nếu thao tác an toàn |
| SQL syntax/invalid query | Không retry; sửa query |
| Permission denied/unauthenticated | Sửa IAM/credentials; không retry liên tục |
| maximumBytesBilled exceeded | Thu hẹp query hoặc điều chỉnh ngưỡng sau review |
| Connection pool timeout | Kiểm tra leak, concurrency, pool sizing và DB capacity |
| Transaction aborted | Retry toàn bộ transaction nếu nghiệp vụ và client library cho phép |

### 10.2. Exponential backoff có jitter

Khi quota hoặc database tạm thời quá tải, retry ngay lập tức từ nhiều instance sẽ tạo retry storm. Dùng exponential backoff có jitter và giới hạn số lần retry:

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

Duration delay = Duration.ofMillis(200);
Duration maxDelay = Duration.ofSeconds(10);

for (int attempt = 1; attempt <= 5; attempt++) {
    try {
        return executeOperation();
    } catch (TransientDataException error) {
        if (attempt == 5) {
            throw error;
        }

        long jitterMillis = ThreadLocalRandom.current()
                .nextLong(Math.max(1, delay.toMillis() / 2),
                          Math.max(2, delay.toMillis() + 1));
        Thread.sleep(jitterMillis);
        delay = delay.multipliedBy(2).compareTo(maxDelay) > 0
                ? maxDelay
                : delay.multipliedBy(2);
    }
}
throw new IllegalStateException("Unreachable");
~~~

Đây là minh họa chiến lược; trong production nên dùng retry library hoặc cơ chế retry của Google client library nếu đã được cấu hình phù hợp. Không bọc thêm retry layer bên ngoài khi client đã tự retry cùng loại lỗi, nếu điều đó làm nhân số lần gọi.

### 10.3. Retry phải idempotent

Với query/job submit, lưu job ID hoặc request ID để nhận biết lần submit trước đã được tạo hay chưa. Với Cloud SQL/Spanner write, dùng unique key, transaction hoặc idempotency key để tránh ghi trùng khi client không biết chắc commit đã hoàn tất trước lúc mất kết nối.

Nếu lỗi xảy ra giữa transaction, retry từ đầu transaction theo semantics của database. Không chỉ chạy lại câu lệnh cuối cùng trong một transaction đã abort.

## 11. Observability cho query và connection pool

### 11.1. BigQuery

Theo dõi:

- Bytes billed/processed theo job, user và label.
- Query count, job errors và quota exceeded.
- Pending/running jobs và slot utilization.
- Query latency, resource warnings và top expensive jobs.
- Reservation utilization nếu dùng capacity model.

### 11.2. Cloud SQL và HikariCP

Theo dõi ít nhất:

| Metric | Ý nghĩa |
| --- | --- |
| Hikari active | Connection đang được ứng dụng mượn |
| Hikari idle | Connection đang rảnh trong pool |
| Hikari pending/waiting | Thread đang chờ connection |
| Hikari max | Giới hạn pool của process |
| Cloud SQL connections | Số connection tới instance |
| Database CPU/memory | Tài nguyên server |
| Query latency/lock waits | Chất lượng xử lý database |

Nếu active gần maximumPoolSize và pending tăng, pool có thể đang là bottleneck. Nếu connection count tăng nhưng CPU database đã cao, tăng pool có thể làm tình trạng xấu hơn. Tối ưu query và transaction trước khi tăng connection limit.

### 11.3. Spanner

Theo dõi instance CPU, request latency, transaction aborts, read/write throughput, gRPC channel utilization và retry rate. Khi dùng dynamic channel pool, quan sát tail latency và channel growth để xác định client có bị under-provisioned hay không.

### 11.4. Correlation và labels

Gắn service name, environment, workload type và correlation ID phù hợp vào logs/job labels. Không log SQL parameter chứa thông tin nhạy cảm hoặc secret. Dùng trace ID để liên kết request Spring Boot với BigQuery job ID hoặc transaction/database logs.

## 12. Runbook kiểm soát tài nguyên

Trước khi phát hành workload dữ liệu:

1. Xác định BigQuery pricing model và region.
2. Đặt maximum bytes billed cho query on-demand quan trọng.
3. Thiết lập project/user daily query quota phù hợp.
4. Kiểm tra budget alert và người nhận cảnh báo.
5. Theo dõi INFORMATION_SCHEMA.JOBS theo user, label và workload.
6. Xác định Cloud SQL max_connections trên instance thật.
7. Tính tổng Hikari maximumPoolSize nhân với max replicas của toàn fleet.
8. Cộng thêm worker, migration, monitoring và rolling deployment headroom.
9. Đặt connection timeout và theo dõi pool pending.
10. Dùng Cloud SQL Connector/Proxy theo đúng lifecycle, không tạo connector mỗi request.
11. Tái sử dụng Spanner client; xác minh multiplexed sessions và dynamic channel pool.
12. Kiểm thử quota exceeded, connection timeout, transaction abort và scale-out.

Khi xảy ra sự cố:

- **BigQuery cost tăng:** xem top jobs theo bytes billed/slot ms, caller và query text; xác định query scan rộng hoặc chạy lặp.
- **BigQuery quota exceeded:** kiểm tra quota ID, project/user scope và reset time; không chỉ tăng quota nếu query pattern chưa được tối ưu.
- **Cloud SQL connection exhausted:** xem Hikari active/idle/pending, connection count, max replicas và leak; không tăng max_connections ngay khi chưa đánh giá memory.
- **Spanner latency tăng:** xem transaction abort, CPU, request concurrency và channel pool; phân biệt contention với thiếu client channel.

## 13. Bài tập thực hành tổng hợp

Một ứng dụng Spring Boot có hai workload:

- Service order-reporting chạy BigQuery query để tạo báo cáo doanh thu theo ngày.
- Service order-api ghi đơn hàng vào Cloud SQL PostgreSQL.
- Một worker khác dùng Cloud Spanner để cập nhật projection phục vụ đọc.

### Yêu cầu A — BigQuery query cost

1. Tạo query báo cáo dùng partition filter theo ngày.
2. So sánh bytes estimate giữa SELECT * và query chỉ chọn cột cần thiết.
3. Chạy dry run bằng Java BigQuery client.
4. Từ chối query nếu estimated bytes vượt ngưỡng của endpoint.
5. Submit query với maximumBytesBilled.
6. Gắn job label theo service/environment.
7. Truy vấn INFORMATION_SCHEMA.JOBS_BY_PROJECT để tổng hợp bytes billed theo user.

### Yêu cầu B — Quota và budget

1. Đặt QueryUsagePerDay và QueryUsagePerUserPerDay cho project sandbox.
2. Kiểm tra thời điểm quota reset theo Pacific Time.
3. Tạo budget alert ở mức 50%, 80% và 100%.
4. Chứng minh budget alert không tự dừng query.
5. Tạo test xử lý quotaExceeded và HTTP 429 bằng backoff có jitter.

### Yêu cầu C — Cloud SQL connection budget

1. Đọc max_connections của Cloud SQL PostgreSQL.
2. Cấu hình Hikari maximumPoolSize = 5 và minimumIdle = 1.
3. Giả lập 10 application replicas; tính tổng pool capacity.
4. Cộng worker và migration connections vào budget.
5. Load test để quan sát active, idle và pending connections.
6. Thử scale out đồng thời và xác định connection storm.
7. Xác minh DataSource/Cloud SQL Connector chỉ được tạo một lần trong mỗi application instance.

### Yêu cầu D — Spanner client resource

1. Tạo một Spanner bean dùng chung trong Spring context.
2. Kiểm tra phiên bản Java client có multiplexed sessions mặc định.
3. Bật dynamic channel pool và so sánh p95/p99 latency.
4. Tạo transaction contention và quan sát abort/retry.
5. Đảm bảo transaction callback không gửi side effect bên ngoài.

### Ma trận đánh giá

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Query quét vượt maximum bytes | Job bị từ chối trước khi chạy |
| Daily query quota hết | Ứng dụng báo quota error và không retry liên tục |
| Budget alert chạm ngưỡng | Notification được gửi; query không tự động bị dừng bởi alerts-only budget |
| Cloud SQL pool hết connection | Request chờ tối đa connectionTimeout rồi thất bại có kiểm soát |
| Cloud Run scale out | Tổng connections vẫn nằm trong database budget |
| Cloud SQL connector refresh | Admin API usage được theo dõi, connector không tạo theo request |
| Spanner concurrency tăng | Client tái sử dụng, multiplexed sessions và channel pool hoạt động đúng |
| Transaction abort | Retry toàn transaction, không lặp side effect |

### Tiêu chí hoàn thành

- Có dry run và maximum bytes billed cho query on-demand.
- Có quota ngày và dashboard usage theo job/user.
- Tính được tổng Cloud SQL connections trên toàn bộ fleet.
- Có Hikari pool config, connection timeout và leak monitoring.
- Tái sử dụng Cloud SQL connector/DataSource và Spanner client.
- Có retry/backoff giới hạn và idempotency cho thao tác ghi.
- Phân biệt rõ những guardrail là quota, system limit hay budget alert.

## 14. So sánh với AWS và Azure

| Nhu cầu | Google Cloud | AWS | Azure |
| --- | --- | --- | --- |
| Kiểm soát scan cost cho data warehouse | BigQuery dry run, maximumBytesBilled, custom query quotas, reservations | Athena scan bytes, workgroup data usage controls và capacity/reservations theo dịch vụ | Synapse/serverless SQL data processed limits, dedicated SQL pool capacity |
| Query telemetry | INFORMATION_SCHEMA.JOBS, slot milliseconds, Cloud Monitoring | CloudWatch, query history và workgroup metrics | Azure Monitor, query insights và workspace metrics |
| Database connection pooling | Cloud SQL + HikariCP/Cloud SQL Connector | RDS/Aurora + HikariCP, RDS Proxy khi phù hợp | Azure SQL Database + HikariCP, connection pooling/managed identity |
| Connection limit | Cloud SQL max_connections theo engine/instance; Cloud Run built-in connection cap | Engine max connections và giới hạn RDS Proxy/client | SQL connection limits theo tier/service objectives |
| Distributed database client | Spanner multiplexed sessions và gRPC channels | DynamoDB SDK connection/HTTP client pools hoặc Aurora/DAX theo workload | Cosmos DB SDK client reuse, connection mode và endpoint topology |
| Quota governance | Cloud Quotas, BigQuery custom query quotas, budgets | Service Quotas, Budgets và workgroup controls | Azure quotas/limits, Cost Management budgets |

Không ánh xạ trực tiếp một quota BigQuery thành một giới hạn Athena/Synapse. Mỗi dịch vụ có đơn vị tính phí, phạm vi quota và cách giới hạn compute khác nhau. Khi chuyển cloud, giữ lại nguyên tắc: estimate trước khi chạy, giới hạn per job, quota tổng, theo dõi usage và tính connection budget theo toàn bộ fleet.

## Tổng kết

Kiểm soát chi phí và tài nguyên dữ liệu cần nhiều lớp. Với BigQuery on-demand, giảm bytes scanned bằng chọn cột, partition pruning, clustering và materialize; dùng dry run cùng maximumBytesBilled để bảo vệ từng job; dùng custom daily query quota và INFORMATION_SCHEMA để quản lý usage theo project/user. Budget alert giúp cảnh báo chi phí nhưng alerts-only budget không tự động dừng dịch vụ.

Với Cloud SQL, connection budget phải tính trên toàn bộ replicas: số instance tối đa nhân maximumPoolSize, cộng worker, migration và headroom khi rolling deployment. HikariCP cần giới hạn hợp lý, connection được trả lại pool, transaction ngắn và connector/DataSource được tái sử dụng. Cloud SQL Java Connector còn dùng Cloud SQL Admin API quota để refresh metadata/certificate.

Với Spanner Java client mới, multiplexed sessions được bật mặc định; tái sử dụng một Spanner client và cân nhắc dynamic channel pool thay vì sao chép cấu hình session pool cũ đã deprecated. Theo dõi query usage, connection pool, database capacity và retry rate để phân biệt quota exhaustion với bottleneck thực tế.

## Tài liệu tham khảo

- [BigQuery — Estimate and control costs](https://docs.cloud.google.com/bigquery/docs/best-practices-costs) — on-demand/capacity pricing, dry run, maximum bytes billed và cách giảm bytes scanned.
- [BigQuery — Quotas and limits](https://docs.cloud.google.com/bigquery/quotas) — query job, API quota và system limits.
- [BigQuery — Create custom query quotas](https://docs.cloud.google.com/bigquery/docs/custom-quotas) — project/user daily query usage quota, reset time và giới hạn của custom quota.
- [BigQuery — INFORMATION_SCHEMA.JOBS](https://docs.cloud.google.com/bigquery/docs/information-schema-jobs) — bytes billed, slot milliseconds, query jobs và báo cáo usage.
- [BigQuery Java — Dry run query sample](https://docs.cloud.google.com/bigquery/docs/samples/bigquery-query-dry-run) — Java BigQuery client và QueryJobConfiguration.setDryRun.
- [Cloud Billing — Budgets and budget alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets) — budget threshold, notifications và giới hạn của alerts-only budget.
- [Cloud SQL — Manage database connections](https://docs.cloud.google.com/sql/docs/postgres/manage-connections) — HikariCP, connection pool, connection count và exponential backoff.
- [Cloud SQL — Quotas and limits](https://docs.cloud.google.com/sql/docs/quotas) — max_connections, Cloud Run built-in connection limit và Admin API quotas.
- [Cloud Spanner — Sessions](https://docs.cloud.google.com/spanner/docs/sessions) — multiplexed sessions, session usage và dynamic channel pooling.
- [Cloud Spanner Java — SpannerOptions.Builder](https://docs.cloud.google.com/java/docs/reference/google-cloud-spanner/latest/com.google.cloud.spanner.SpannerOptions.Builder) — dynamic channel pool configuration.
