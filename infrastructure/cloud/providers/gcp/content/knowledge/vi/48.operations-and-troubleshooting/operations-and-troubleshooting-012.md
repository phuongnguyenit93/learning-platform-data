# Phát hiện tăng chi phí bất thường từ billing và audit logs

Một ứng dụng đang hoạt động bình thường vẫn có thể tạo ra hóa đơn Google Cloud cao bất thường. Một máy ảo bị bỏ quên, số lượng instance tăng ngoài kế hoạch, truy vấn BigQuery quét nhiều dữ liệu, log bị ghi lặp, dữ liệu được chuyển qua region khác hoặc thông tin xác thực bị lộ đều có thể làm chi phí tăng nhanh. Nếu chỉ xem tổng tiền cuối tháng, nhóm vận hành thường phát hiện quá muộn và không biết thay đổi nào gây ra vấn đề.

Để điều tra hiệu quả, cần kết hợp **Cloud Billing** (dịch vụ nào, project nào, SKU nào đã phát sinh chi phí) với **Cloud Audit Logs** (ai hoặc danh tính nào đã thực hiện thay đổi tài nguyên và khi nào), rồi kiểm tra thêm metrics, deployment history và traffic. Billing và audit logs trả lời các câu hỏi khác nhau: chi phí tăng không tự chứng minh có một thao tác quản trị sai, còn một thao tác tạo resource không tự chứng minh resource đó là nguồn gây ra toàn bộ mức tăng.

Bài học thuộc chương **Vận hành và xử lý sự cố** của module **CLOUD_PROVIDERS_GCP**. Module hướng dẫn tổ chức project, IAM và VPC; triển khai Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu; bảo vệ tài nguyên, tự động hóa phát hành, theo dõi độ tin cậy và chi phí. Nội dung này tập trung vào việc nhận diện bất thường, truy tìm nguyên nhân và đưa ra hành động có kiểm soát trong hoạt động vận hành GCP.

> **Nguyên tắc an toàn:** Các truy vấn và bộ lọc dưới đây phục vụ quan sát/điều tra. Không tự động xóa máy ảo, xóa dữ liệu, vô hiệu hóa billing hoặc thu hồi quyền production chỉ dựa trên một cảnh báo chi phí. Mọi can thiệp phải xem xét SLO, người sở hữu workload, rủi ro bảo mật và kế hoạch khôi phục.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt billing account, project, service, SKU, usage date, invoice month, credits, taxes và adjustments.
- Hiểu độ trễ ghi nhận Cloud Billing và giới hạn của dữ liệu real-time cost.
- Thiết lập Budgets & alerts, cost anomalies, Billing export sang BigQuery và cost allocation.
- Dùng SQL tìm project, service và SKU có mức tăng bất thường, có cân nhắc dữ liệu chưa hoàn chỉnh.
- Đọc Cloud Audit Logs để xác định principal, method, resource và thời điểm thay đổi.
- Kết hợp billing, audit logs, deployment/traffic metrics để hình thành giả thuyết nguyên nhân.
- Tạo quy trình cảnh báo, phân loại độ nghiêm trọng, kiểm soát chi phí và tránh false positives.
- Xây dựng runbook điều tra kèm timeline, evidence, owner và cơ chế ngăn tái diễn.

## 1. Ba nguồn bằng chứng và một quy trình điều tra

| Nguồn | Trả lời được | Không tự trả lời được |
|---|---|---|
| Cloud Billing Reports / FinOps Hub | Tiền tăng ở project, service, SKU, thời gian nào; xu hướng và dự toán | Ai trực tiếp gây ra chi phí và thao tác nào là nguyên nhân |
| Cloud Billing export to BigQuery | Phân tích dữ liệu chi phí theo ngày, project, SKU, labels, credits; một số resource-level details | Diễn biến mọi API call hoặc căn nguyên security |
| Cloud Audit Logs | Principal, service, API method, resource và thời gian các sự kiện được log | Mức tiền chính xác của mỗi API call hoặc mọi thao tác dữ liệu khi logging chưa bật |
| Cloud Monitoring / service metrics | CPU, instances, requests, egress, log ingestion, DB load hoặc jobs | Giá tiền cuối cùng và discounts trong hóa đơn |
| CI/CD và change records | Bản phát hành, thay đổi cấu hình, reviewer, trigger và commit | Khẳng định một thay đổi cụ thể tạo ra chi phí nếu chưa đối chiếu |

Điều tra nên theo hướng **chi phí tăng ở đâu → mức sử dụng nào tăng → sự kiện hoặc thay đổi nào liên quan → thử xác minh giả thuyết → xử lý và đo lại**.

~~~mermaid
flowchart TD
    A["Budget / anomaly alert / daily report"]
    B["Xác minh scope, currency, độ trễ dữ liệu"]
    C["Billing: project → service → SKU → resource"]
    D["Monitoring: usage, instances, requests, egress"]
    E["Audit Logs: principal, method, resource, time"]
    F{"Có nguyên nhân đủ bằng chứng?"}
    G["Hành động an toàn theo owner/runbook"]
    H["Thêm quan sát, khoanh vùng giả thuyết"]
    I["Theo dõi chi phí và SLO sau xử lý"]
    J["Post-incident review và phòng tái diễn"]
    A --> B --> C
    C --> D
    C --> E
    D --> F
    E --> F
    F -->|"Có"| G --> I --> J
    F -->|"Chưa"| H --> C
~~~

Một đợt tăng chi phí có thể là hoạt động hợp lệ: chiến dịch marketing tăng traffic, migration sang region mới, chạy load test được duyệt hoặc batch cuối tháng. Nhiệm vụ điều tra là phân biệt **mức tăng hợp lệ có dự toán** với **chi phí ngoài dự kiến** và **tín hiệu xâm nhập bảo mật**.

## 2. Cấu trúc chi phí trong Cloud Billing

### Các khái niệm

| Trường/khái niệm | Ý nghĩa vận hành |
|---|---|
| Billing account | Tài khoản thanh toán gắn với một hoặc nhiều project |
| Project | Nơi phát sinh sử dụng resource; không phải lúc nào mọi khoản phí cũng có project ID |
| Service | Sản phẩm như Compute Engine, Cloud Run, BigQuery hoặc Cloud Storage |
| SKU | Đơn vị định giá chi tiết trong service, ví dụ loại compute, storage hoặc network transfer |
| usage_start_time / usage_end_time | Khoảng thời gian sử dụng được tính cho một dòng chi phí |
| export_time | Thời điểm bản ghi được xuất/cập nhật vào BigQuery |
| invoice.month | Tháng hóa đơn theo định dạng YYYYMM, có thể khác tháng sử dụng |
| cost | Chi phí trên dòng dữ liệu; không nhất thiết là số tiền sau credits |
| credits | Các khoản credit/discount tương ứng, thường là số âm |
| cost_type | Phân loại regular, tax, adjustment, rounding error... |
| currency | Đơn vị tiền của billing account; không cộng gộp nhiều currency tùy tiện |

**Gross cost** và **net cost** không phải cùng một chỉ số. Trong các ví dụ SQL, net cost được tính bằng **SUM(cost) + SUM(credits.amount)** ở phạm vi các dòng phù hợp. Khi credits thay đổi, net cost có thể tăng dù mức sử dụng thực tế không đổi. Ngược lại, nếu nhìn riêng cost mà bỏ qua credit, phân tích có thể không khớp chi phí sau giảm giá.

### Thời gian sử dụng khác thời gian hóa đơn

Một số dịch vụ ghi nhận sử dụng theo khoảng thời gian, nhưng dòng chi phí có thể xuất hiện muộn. Ở ranh giới cuối tháng, khoản sử dụng có thể vào invoice của tháng sau; adjustment hoặc tax được ghi trong kỳ khác. Vì vậy:

1. Phân tích xu hướng vận hành theo **usage_start_time**.
2. Đối soát hóa đơn theo **invoice.month**.
3. Ghi rõ timezone khi quy đổi ngày.
4. Kiểm tra cả cost, credits, cost_type và currency.
5. Không dùng ngày vừa bắt đầu hoặc một giờ hiện tại như “chi phí đã đủ để so sánh” khi dữ liệu còn trễ.

Cloud Billing thường có độ trễ cập nhật, có thể từ vài giờ đến hơn một ngày tùy dịch vụ và hình thức thanh toán. **Billing export không phải nguồn đo mức sử dụng theo thời gian thực**; dùng Cloud Monitoring/service metrics khi cần phát hiện đột biến ngay sau deploy.

## 3. Tổ chức scope và quyền truy cập

### Phạm vi chi phí

Một đội vận hành nên phân tách ít nhất:

- Billing account hoặc business unit.
- Project: development, staging, production, shared platform.
- Service và SKU.
- Environment, application, team owner hoặc cost center khi labels/tags được hỗ trợ.
- Resource ID nếu detailed billing export cung cấp thông tin phù hợp.

Không phải mọi SKU đều có chi phí ở cấp resource. Các thành phần dùng chung như network, commitment fees, logging, support hoặc tax có thể cần quy tắc phân bổ riêng. Một trường resource null **không phải luôn là lỗi export**.

### Các quyền thường cần

| Nhân sự/automation | Nhu cầu | Nguyên tắc cấp quyền |
|---|---|---|
| FinOps analyst | Xem billing reports và dữ liệu export | Quyền đọc billing và BigQuery dataset cần thiết |
| SRE/on-call | Xem service metrics, admin audit logs | Logging/Monitoring read-only phù hợp scope |
| Security responder | Điều tra IAM, Data Access và anomaly bảo mật | Quyền đọc audit logs nhạy cảm theo chính sách |
| Budget administrator | Tạo/sửa budget và notifications | Quyền Billing Budgets được phân tách |
| Cost responder automation | Gửi ticket/cảnh báo và đề xuất thay đổi | Quyền đọc/phát thông báo, không mặc định quyền xóa resource |

Quyền xem Cloud Audit Logs **không đồng nhất** với quyền đọc mọi loại log. Data Access logs có thể cần quyền như Private Logs Viewer trên bucket log tương ứng. Bản thân dữ liệu billing cũng nhạy cảm về tài chính và cấu trúc hệ thống; áp dụng IAM tối thiểu với dataset, dashboard và export.

## 4. Thiết lập Budgets, cost anomalies và kênh cảnh báo

### Budgets & alerts

Trong Google Cloud Console, vào **Billing → Budgets & alerts**, chọn billing account, rồi:

1. Tạo budget theo billing account hoặc lọc theo project/service phù hợp.
2. Chọn kỳ ngân sách và số tiền dự kiến.
3. Đặt threshold cảnh báo, ví dụ 50%, 80%, 100% cho actual spend và một forecast threshold nếu được hỗ trợ.
4. Chọn email recipients; có thể nối Pub/Sub để xử lý programmatic notifications.
5. Gán owner phản hồi, mức độ ưu tiên và runbook.
6. Kiểm tra người nhận có quyền/đầu mối trực rõ ràng.

**Alerts-only budgets không phải hard cap.** Đạt ngưỡng không tự động dừng máy ảo, API hoặc chi tiêu. Google Cloud có cơ chế spend-cap budgets cho một số dịch vụ đủ điều kiện, nhưng không nên suy ra rằng mọi project hoặc SKU đều được chặn khi chạm budget.

### Cost anomalies / FinOps Hub

Cloud Billing có tính năng **phát hiện bất thường về chi phí** dựa trên xu hướng và độ lệch. Trong Console có thể xem Anomalies/FinOps Hub và cấu hình ngưỡng notification tùy tính năng và quyền khả dụng. Cần hiểu:

- Anomaly detection phụ thuộc chi phí đã được báo cáo, nên cũng chịu reporting delay.
- Mức lệch được phát hiện không tự giải thích nguyên nhân kỹ thuật.
- Các ngưỡng nên cân nhắc **cost impact** và **deviation percentage** để tránh spam ở dịch vụ chi phí nhỏ.
- Email notification, daily digest hoặc programmatic Pub/Sub notification phụ thuộc cấu hình và khả năng hỗ trợ hiện tại; kiểm tra kỹ kênh đang bật.

Ví dụ, tăng từ 1 lên 4 đơn vị tiền (300%) có thể không cần báo khẩn; tăng từ 500 lên 800 đơn vị (60%) có tác động ngân sách lớn hơn. Cảnh báo nên cân bằng cả **mức tăng tuyệt đối** và **mức tăng tương đối**.

### Programmatic notifications

Có thể nối budget hoặc anomaly event (tùy tính năng) đến Pub/Sub, xử lý bằng Cloud Run function/service hoặc Workflows để gửi ticket/chat message cho đội trực.

~~~mermaid
flowchart LR
    BILL["Cloud Billing budget / anomaly"] --> TOPIC["Pub/Sub topic"]
    TOPIC --> HANDLER["Notification handler"]
    HANDLER --> DEDUP["Deduplicate + enrich"]
    DEDUP --> TICKET["Incident / FinOps ticket"]
    DEDUP --> DASH["Link Billing / Logs Explorer"]
    DEDUP --> HUMAN["Owner xác minh và xử lý"]
~~~

Pub/Sub có thể giao thông báo lặp hoặc không theo thứ tự. Handler cần **idempotency/deduplication**, kiểm tra schema, ghi correlation ID và giới hạn quyền. Với budget Pub/Sub, các thông báo có thể đến nhiều lần/ngày thay vì chỉ khi vượt threshold. Không viết handler tự động tắt billing cho production chỉ vì nhận một message.

## 5. Bật Billing export sang BigQuery

Để điều tra chi tiết, thiết lập **Cloud Billing → Billing export → BigQuery export**:

1. Chọn billing account cần phân tích.
2. Chuẩn bị BigQuery project/dataset với location hợp lệ theo hướng dẫn Billing export.
3. Bật **Standard usage cost export** để xem account/project/service/SKU/labels/credits.
4. Cân nhắc **Detailed usage cost export** nếu cần các thông tin chi phí cấp resource mà dịch vụ hỗ trợ.
5. Thiết lập quyền đọc dataset cho nhóm FinOps/SRE; không mở public.
6. Ghi thời điểm bật export, billing account ID, dataset location, retention và chi phí truy vấn.
7. Xác nhận dữ liệu thực sự đã bắt đầu xuất hiện trước khi thiết lập dashboard.

### Tên bảng thường gặp

~~~text
STANDARD:
  PROJECT.DATASET.gcp_billing_export_v1_BILLING_ACCOUNT_ID

DETAILED:
  PROJECT.DATASET.gcp_billing_export_resource_v1_BILLING_ACCOUNT_ID

PRICING:
  PROJECT.DATASET.cloud_pricing_export
~~~

Trong bảng billing thực, dấu phân cách của billing account ID có thể được biểu diễn bằng underscore ở tên bảng; hãy **copy chính xác tên bảng xuất hiện trong BigQuery**, không đoán từ billing account ID.

Standard export không chứa chi phí cấp resource cho tất cả dòng. Detailed export có phạm vi rộng hơn nhưng một số dịch vụ và charge vẫn không có resource-level details. Bật export không nhất thiết hồi tố toàn bộ lịch sử billing trước đó; khả năng backfill và thời gian xuất hiện dữ liệu phụ thuộc dataset location và loại export.

### Lưu ý vận hành dữ liệu

- Dataset export có thể trở nên lớn; đặt giới hạn truy vấn, dùng filter thời gian và tạo views chuẩn hóa.
- Billing export schema có thể được bổ sung trường theo thời gian; tránh SELECT * trong dashboard.
- Nếu gán label sau khi tài nguyên đã chạy, chi phí trước thời điểm gán thường không được retroactively gắn label đó.
- Resource location và invoice month phục vụ các góc nhìn khác nhau.
- Tạo data freshness check; thiếu dòng hôm nay chưa đủ bằng chứng chi phí đã giảm.

## 6. SQL: tìm project, service và SKU có chi phí tăng

Các ví dụ BigQuery sau dùng **Standard usage cost export** và GoogleSQL. Thay đường dẫn bảng minh họa bằng tên bảng thực tế được xuất trong dataset của bạn. Hãy chạy trên dữ liệu mà danh tính đang sử dụng được phép đọc; không đưa billing account ID thật vào repository công khai.

### 6.1 Tổng net cost theo ngày và service

~~~sql
-- Thay billing-lab.billing_export và tên bảng bằng giá trị thực.
-- Giới hạn 14 ngày đã qua; không dùng hôm nay làm ngày đủ dữ liệu.
WITH line_items AS (
  SELECT
    DATE(usage_start_time, 'UTC') AS usage_date,
    COALESCE(project.id, 'UNATTRIBUTED') AS project_id,
    service.description AS service_name,
    currency,
    cost_type,
    CAST(cost AS NUMERIC)
      + CAST(IFNULL((
        SELECT SUM(c.amount)
        FROM UNNEST(credits) AS c
      ), 0) AS NUMERIC) AS net_cost
  FROM `billing-lab.billing_export.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`
  WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 16 DAY)
    AND usage_start_time < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 DAY)
)
SELECT
  usage_date,
  project_id,
  service_name,
  currency,
  ROUND(SUM(net_cost), 2) AS net_cost
FROM line_items
WHERE cost_type = 'regular'
GROUP BY usage_date, project_id, service_name, currency
ORDER BY usage_date DESC, net_cost DESC;
~~~

**Đọc kết quả:** Lọc project/service nào đóng góp mức tăng lớn nhất trước khi xuống SKU. Dòng UNATTRIBUTED có thể xuất hiện do một số khoản phí không gắn trực tiếp với project; không tự xóa chúng khỏi tổng báo cáo tài chính.

Ở đây dùng UTC để dễ kiểm tra và ghi nhận mốc. Nếu báo cáo nghiệp vụ sử dụng Asia/Ho_Chi_Minh, hãy chọn một timezone thống nhất cho cả bảng so sánh và ghi rõ. Tránh so ngày UTC với ngày theo timezone khác mà không chuẩn hóa.

### 6.2 Top SKU chi phí tăng trong hai cửa sổ đã hoàn tất

Ví dụ so tổng 7 ngày gần nhất được coi là đủ dữ liệu (kết thúc trước hiện tại 3 ngày) với 7 ngày ngay trước đó. Đây là **heuristic** để điều tra, không phải định nghĩa chính thức của Google Cloud anomaly detection.

~~~sql
DECLARE last_complete_day DATE
  DEFAULT DATE_SUB(CURRENT_DATE('UTC'), INTERVAL 3 DAY);

WITH daily AS (
  SELECT
    DATE(usage_start_time, 'UTC') AS usage_day,
    COALESCE(project.id, 'UNATTRIBUTED') AS project_id,
    service.description AS service_name,
    sku.description AS sku_name,
    currency,
    SUM(
      CAST(cost AS NUMERIC)
      + CAST(IFNULL((
        SELECT SUM(c.amount)
        FROM UNNEST(credits) AS c
      ), 0) AS NUMERIC)
    ) AS net_cost
  FROM `billing-lab.billing_export.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`
  WHERE DATE(usage_start_time, 'UTC')
    BETWEEN DATE_SUB(last_complete_day, INTERVAL 13 DAY)
        AND last_complete_day
    AND cost_type = 'regular'
  GROUP BY usage_day, project_id, service_name, sku_name, currency
),
comparison AS (
  SELECT
    project_id,
    service_name,
    sku_name,
    currency,
    SUM(IF(usage_day BETWEEN DATE_SUB(last_complete_day, INTERVAL 6 DAY)
                         AND last_complete_day, net_cost, 0)) AS current_7d,
    SUM(IF(usage_day BETWEEN DATE_SUB(last_complete_day, INTERVAL 13 DAY)
                         AND DATE_SUB(last_complete_day, INTERVAL 7 DAY),
           net_cost, 0)) AS previous_7d
  FROM daily
  GROUP BY project_id, service_name, sku_name, currency
)
SELECT
  project_id,
  service_name,
  sku_name,
  currency,
  ROUND(current_7d, 2) AS current_7d,
  ROUND(previous_7d, 2) AS previous_7d,
  ROUND(current_7d - previous_7d, 2) AS increase_absolute,
  ROUND(
    SAFE_DIVIDE(current_7d - previous_7d, NULLIF(previous_7d, 0))
      * 100, 1
  ) AS increase_percent
FROM comparison
WHERE current_7d - previous_7d > 20
ORDER BY increase_absolute DESC
LIMIT 50;
~~~

**Diễn giải:** Ngưỡng tăng trên 20 đơn vị tiền của billing account là **ví dụ**, phải thay theo quy mô chi tiêu và currency. Với previous_7d = 0, phần trăm tăng không xác định; SAFE_DIVIDE trả NULL thay vì lỗi, nhưng tuyệt đối không bỏ qua những SKU mới bắt đầu phát sinh chi phí. Dữ liệu hai tuần có thể chịu ảnh hưởng ngày nghỉ, chiến dịch hoặc lịch batch; nên so cùng loại ngày hoặc lịch workload khi cần.

### 6.3 Phân biệt gross, credits và net

~~~sql
SELECT
  DATE(usage_start_time, 'UTC') AS usage_day,
  service.description AS service_name,
  currency,
  ROUND(SUM(CAST(cost AS NUMERIC)), 2) AS gross_cost,
  ROUND(SUM(
    CAST(IFNULL((
      SELECT SUM(c.amount)
      FROM UNNEST(credits) AS c
    ), 0) AS NUMERIC)
  ), 2) AS credits_amount,
  ROUND(SUM(
    CAST(cost AS NUMERIC)
    + CAST(IFNULL((
      SELECT SUM(c.amount)
      FROM UNNEST(credits) AS c
    ), 0) AS NUMERIC)
  ), 2) AS net_cost
FROM `billing-lab.billing_export.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`
WHERE DATE(usage_start_time, 'UTC')
  BETWEEN DATE_SUB(CURRENT_DATE('UTC'), INTERVAL 14 DAY)
      AND DATE_SUB(CURRENT_DATE('UTC'), INTERVAL 3 DAY)
  AND cost_type = 'regular'
GROUP BY usage_day, service_name, currency
ORDER BY usage_day DESC, net_cost DESC;
~~~

Nếu gross ổn định nhưng net tăng, xem có thay đổi credits, discounts hoặc commitment allocation không. Nếu gross và usage quantity đều tăng, điều tra workload/consumption. Đừng gộp thuế hoặc adjustment vào chi phí sử dụng trong truy vấn phát hiện sự cố kỹ thuật mà không có phân loại riêng.

### 6.4 Chi phí cấp resource từ detailed export

Nếu đã bật detailed usage cost export và service hỗ trợ trường resource:

~~~sql
SELECT
  COALESCE(project.id, 'UNATTRIBUTED') AS project_id,
  service.description AS service_name,
  sku.description AS sku_name,
  COALESCE(resource.name, '(no resource detail)') AS resource_name,
  currency,
  ROUND(SUM(
    CAST(cost AS NUMERIC)
    + CAST(IFNULL((
      SELECT SUM(c.amount) FROM UNNEST(credits) AS c
    ), 0) AS NUMERIC)
  ), 2) AS net_cost
FROM `billing-lab.billing_export.gcp_billing_export_resource_v1_XXXXXX_XXXXXX_XXXXXX`
WHERE DATE(usage_start_time, 'UTC')
  BETWEEN DATE_SUB(CURRENT_DATE('UTC'), INTERVAL 10 DAY)
      AND DATE_SUB(CURRENT_DATE('UTC'), INTERVAL 3 DAY)
  AND cost_type = 'regular'
GROUP BY project_id, service_name, sku_name, resource_name, currency
ORDER BY net_cost DESC
LIMIT 100;
~~~

Trường resource.name có thể NULL ngay cả khi export đang hoạt động đúng. Không dùng resource name làm khóa nối duy nhất với audit logs nếu tên có thể trùng theo project/zone, nếu resource đã bị tạo lại hoặc resource ID được biểu diễn khác nhau. Luôn ghép thêm project, service, location và time window khi có thể.

### SQL và an toàn chi phí truy vấn

- Thử trên khoảng thời gian nhỏ, dùng BigQuery dry run để ước tính bytes scanned.
- Lưu normalized view với schema ổn định; Billing export có thể bổ sung trường trong tương lai.
- Không hard-code currency rồi cộng các tài khoản dùng đơn vị khác nhau.
- Dùng cost_type = 'regular' cho phân tích usage operational và dùng tất cả cost_type khi đối soát invoice.
- Khi báo cáo net cost âm vì credit, không kết luận đó là “âm sử dụng”.
- Lưu query version, filter và timezone để kết quả có thể tái hiện.

## 7. Phát hiện bất thường có baseline thay vì một ngưỡng cố định

Một budget threshold có ích để quản lý trần chi phí tháng nhưng không đủ cho mọi dạng bất thường. Ví dụ, một đợt tăng 70% trong hai giờ đầu buổi sáng có thể đáng điều tra dù tổng chi tiêu tháng vẫn dưới budget.

### Xây baseline theo service/project

Một chiến lược thực tế:

1. Chọn chỉ số: net cost hoặc gross cost, và không đổi giữa các lần so.
2. Chia theo project/service/SKU hoặc cost center có chủ sở hữu.
3. Chọn các ngày đã hoàn thiện dữ liệu theo SLA nội bộ, ví dụ chậm 2–3 ngày; không coi đó là bảo đảm từ Cloud Billing.
4. So ngày mục tiêu với cùng thứ trong 4–8 tuần trước nếu traffic có chu kỳ tuần.
5. Tính median và mức phân tán thay vì chỉ trung bình nếu có spike cũ.
6. Đặt cả ngưỡng tuyệt đối và tương đối; xem xét workload mới chưa có baseline.
7. Enrich với triển khai, sự kiện marketing, test tải và biến động traffic trước khi báo sự cố.

### Pseudocode cho rule phát hiện

~~~text
baseline = median(daily_cost_of_same_weekday_over_previous_6_weeks)
actual = cost_of_last_verified_complete_day
absolute_increase = actual - baseline
relative_increase = absolute_increase / max(baseline, small_floor)

if not enough_history:
    alert "new workload / insufficient baseline" with lower confidence
else if actual > minimum_impact
    and absolute_increase > absolute_threshold
    and relative_increase > relative_threshold:
    create anomaly candidate

enrich with known changes, traffic metrics and audit logs
assign owner and verify before remediation
~~~

Baseline bằng 0 đòi hỏi xử lý riêng, không thể báo “tăng vô hạn phần trăm” rồi auto-delete. Với dịch vụ có phát sinh theo mùa hoặc batch cuối tháng, dùng lịch nghiệp vụ thay vì chỉ cùng thứ trong tuần.

### Tránh false positives và false negatives

| Hiện tượng | Có thể gây hiểu nhầm | Cách kiểm tra |
|---|---|---|
| Billing export cập nhật muộn | Ngày gần nhất thấp giả hoặc tăng dồn về sau | Dùng data freshness, kiểm tra export_time |
| Thay đổi credits/discount | Net cost tăng dù usage không tăng | Xem gross, credits và invoice |
| Lịch chạy batch | Một ngày cao hơn bình thường | Đối chiếu scheduler và lịch nghiệp vụ |
| Mùa vụ/chiến dịch | Traffic tăng hợp lệ | So requests, business volume và release |
| Project mới tạo | Chưa có lịch sử chi phí | Alert theo spend tuyệt đối và owner |
| Resource dùng chung | Không biết team chịu chi phí | Labels, tags, allocation rule |
| Thay đổi SKU/rate | Chi phí tăng nhưng usage gần như cũ | So SKU, quantity và pricing changes |
| Mở rộng quota | Chưa có phí ngay nhưng mở nguy cơ tăng | Audit logs, quota và workload metrics |
| Sự cố bảo mật | Giao dịch ngoài giờ và resource lạ | Kết hợp IAM events, source IP, resource changes |

Cloud Billing cost anomaly detection được quản lý có thể là lớp cảnh báo bổ sung. Tự viết baseline trong BigQuery giúp kiểm soát logic theo workload, nhưng cần bảo trì và không nên coi là kết quả tính phí chính thức.

## 8. Cloud Audit Logs: tìm ai đã làm gì, ở đâu và lúc nào

Cloud Audit Logs ghi lại các loại sự kiện khác nhau tùy service và logging configuration:

| Loại | Đặc điểm | Khi điều tra chi phí |
|---|---|---|
| Admin Activity | Ghi các thay đổi cấu hình/metadata, bật mặc định | Tìm VM mới, resize, bật service, thay đổi bucket/config |
| Data Access | Đọc/ghi dữ liệu theo quyền và dịch vụ; thường cần bật (BigQuery có ngoại lệ) | Tìm truy vấn hoặc thao tác dữ liệu tạo usage nếu được log |
| System Event | Sự kiện hệ thống do Google thực hiện | Phân biệt hoạt động platform với thao tác người dùng |
| Policy Denied | Quyền truy cập bị chính sách từ chối | Phát hiện hành vi bất thường hoặc permission misconfiguration |

**Data Access logs không được bật mặc định cho hầu hết dịch vụ** (BigQuery có ngoại lệ). Nếu trước đây chưa bật, thường không thể truy xuất các sự kiện không được ghi. Bật thêm Data Access logging có thể phát sinh chi phí lưu log; cần cân bằng phạm vi, retention và bảo mật.

### Các trường cần đọc

| Trường audit log | Ý nghĩa |
|---|---|
| timestamp | Thời điểm sự kiện được ghi |
| protoPayload.serviceName | API service, ví dụ compute.googleapis.com |
| protoPayload.methodName | API method/operation |
| protoPayload.resourceName | Resource được thao tác nếu có |
| protoPayload.authenticationInfo.principalEmail | Principal gọi API khi log có thông tin |
| protoPayload.requestMetadata.callerIp | Địa chỉ nguồn khi được ghi và không bị ẩn |
| protoPayload.status | Trạng thái lỗi hoặc thành công của call |
| operation.id / operation.first / operation.last | Theo dõi long-running operations khi có |
| resource.labels | Project, zone, instance hoặc monitored resource metadata |

Không phải event nào cũng có tất cả trường, và principal có thể được redacted trong một số ngữ cảnh. Một operation có thể ghi nhiều log entries; không đếm mỗi log entry như một máy ảo được tạo thành công.

### Tìm sự kiện tạo VM

Trong Logs Explorer, lọc:

~~~text
log_id("cloudaudit.googleapis.com/activity")
protoPayload.serviceName="compute.googleapis.com"
protoPayload.methodName:"instances.insert"
~~~

Đặt thêm time range (ví dụ vài giờ/ngày trước khi SKU Compute Engine tăng), project và zone để giảm nhiễu. Cách tìm substring ở methodName phù hợp với một số phiên bản API; nếu không có kết quả, xem tên method thực tế trong audit log service-specific, không tự kết luận không có sự kiện.

### Tìm thay đổi cấu hình compute có thể làm tăng giá

~~~text
log_id("cloudaudit.googleapis.com/activity")
protoPayload.serviceName="compute.googleapis.com"
(
  protoPayload.methodName:"instances.insert" OR
  protoPayload.methodName:"instances.setMachineType" OR
  protoPayload.methodName:"disks.insert" OR
  protoPayload.methodName:"instanceGroupManagers"
)
~~~

Những sự kiện trên là **ứng viên nguyên nhân**. Cần xem kết quả operation, loại VM/disk, thời gian chạy và billing breakdown để kiểm tra mức tăng cost có tương ứng hay không. Với autoscaling, một số thay đổi có thể do service agent hoặc controller, không phải con người trực tiếp click Create.

### Tìm sự kiện Cloud Run/GKE/Cloud SQL

~~~text
log_id("cloudaudit.googleapis.com/activity")
(
  protoPayload.serviceName="run.googleapis.com" OR
  protoPayload.serviceName="container.googleapis.com" OR
  protoPayload.serviceName="cloudsql.googleapis.com"
)
~~~

Sau khi xác định service, thêm điều kiện methodName/resourceName cụ thể. Ví dụ, Cloud Run update về min instances, GKE node pool size và Cloud SQL tier/HA/replica là những thay đổi cần đối chiếu. Audit log không thay thế việc đọc cấu hình hiện tại và deployment history.

### Query qua gcloud CLI

Ví dụ tìm một nhóm Admin Activity event:

~~~bash
export PROJECT_ID="example-production-project"

gcloud logging read \
  'log_id("cloudaudit.googleapis.com/activity") AND
   protoPayload.serviceName="compute.googleapis.com" AND
   protoPayload.methodName:"instances.insert"' \
  --project="$PROJECT_ID" \
  --freshness=7d \
  --limit=100 \
  --format="table(timestamp,protoPayload.authenticationInfo.principalEmail,protoPayload.methodName,protoPayload.resourceName)"
~~~

Lệnh là truy vấn **read-only**. Kết quả phụ thuộc IAM, audit logging, retention và khoảng thời gian được giữ. Dùng Logs Explorer khi cần xem details và liên kết tới operation. Không xem principalEmail là bằng chứng đầy đủ về người chịu trách nhiệm: call có thể đến từ service account do pipeline sử dụng.

### Kiểm tra thay đổi trên Cloud Billing account

Cloud Billing cũng có audit logs riêng cho các API quản lý billing account và resource billing association. Nếu bất thường liên quan đến việc project chuyển billing account, thay đổi quyền billing hoặc billing account bị đóng/mở, hãy kiểm tra Logs Explorer với service:

~~~text
protoPayload.serviceName="cloudbilling.googleapis.com"
~~~

Tùy vị trí resource, quyền và cách lưu logs, có thể cần chọn phạm vi **billing account** thay vì chỉ project ứng dụng. Tiếp tục lọc theo Admin Activity, timestamp, principal và methodName thực tế trong kết quả. Tài liệu Cloud Billing audit logging liệt kê các method như UpdateResourceBillingProtection và DisableResourceBilling cho một số thao tác liên kết hoặc vô hiệu hóa billing.

Đừng nhầm một thay đổi liên kết billing với nguyên nhân kỹ thuật tạo nhiều CPU hours hoặc egress. Một project chuyển billing account có thể làm báo cáo của **từng tài khoản** tăng/giảm dù workload sử dụng không đổi. Khi đó cần đối chiếu project association, thời điểm và hai phía báo cáo tài chính.

## 9. Nối billing với audit logs: tương quan, không vội quy kết

Khi điều tra, nên vẽ một timeline gồm:

1. **Mốc phát hiện:** budget/anomaly alert phát ra lúc nào?
2. **Mốc sử dụng:** usage_start_time cho thấy SKU nào bắt đầu tăng?
3. **Mốc thay đổi:** Audit Logs và CI/CD ghi sự kiện nào ngay trước thời điểm đó?
4. **Mốc workload:** Cloud Monitoring cho thấy requests, node count, network bytes hoặc CPU thay đổi ra sao?
5. **Mốc xử lý:** thay đổi nào đã được thực hiện và metrics có trở về mức bình thường không?
6. **Mốc billing xác nhận:** chi phí theo usage date có phản ánh xu hướng giảm sau khi dữ liệu xuất đủ không?

### Ví dụ timeline giả định

| Thời gian UTC | Nguồn | Sự kiện | Câu hỏi tiếp theo |
|---|---|---|---|
| 09:00 | CI/CD | Release orders-api phiên bản 2.3 | Có đổi autoscaling/logging không? |
| 09:03 | Admin Activity | Service account deploy cập nhật Cloud Run service | Revision cấu hình khác gì? |
| 09:07 | Monitoring | Instance count tăng từ 3 lên 25 | Do requests, concurrency hay min instances? |
| 09:10 | Monitoring | DB connections tăng, P95 latency tăng | Retry storm hay traffic hợp lệ? |
| 12:00 | Billing | Cloud Run và Cloud SQL usage tăng | Chi phí thuộc SKU nào? |
| Ngày hôm sau | Anomaly report | Cost deviation vượt ngưỡng | Cần xác minh với owner và usage hoàn chỉnh |

Đây là ví dụ minh họa, không phải một event timeline thực tế. Nếu ngày hôm sau hóa đơn tăng, **không** khẳng định chính release ở 09:00 là nguyên nhân chỉ vì diễn ra gần thời gian tăng; phải kiểm tra thay đổi cấu hình, traffic, usage và những sự kiện khác.

### Khóa nối audit và billing

Các yếu tố có thể liên kết:

| Thuộc tính | Từ Billing | Từ Audit/Monitoring | Lưu ý |
|---|---|---|---|
| Project | project.id | resource.labels.project_id hoặc parent resource | Chuẩn hóa project ID |
| Service | service.description | protoPayload.serviceName | Tên hiển thị và API service name không cùng định dạng |
| Resource | resource.name (nếu có) | protoPayload.resourceName / resource.labels | Có thể thiếu hoặc biểu diễn khác nhau |
| Region/zone | location hoặc system labels | resource labels, API request | Một SKU có thể là global/multi-region |
| Thời gian | usage_start_time / export_time | timestamp | Billing có độ trễ |
| Owner | labels/tags/project mapping | principalEmail, change ticket | Principal gọi API không luôn là owner chi phí |

Không có một khóa SQL join phổ quát bảo đảm ghép mọi billing line item với một Audit Log entry. Kết hợp dữ liệu cần hiểu từng service và có thể phải dùng mapping resource inventory/deployment history.

### Quy trình truy nguyên không vội kết luận

Giả sử Cloud Storage network egress tăng:

1. Billing cho thấy **SKU network transfer** tăng, chứ không phải storage capacity.
2. Metrics xác nhận bytes egress tăng theo bucket/endpoint phù hợp nếu có.
3. Kiểm tra CDN hit ratio, cache misses, request patterns và region của client.
4. Kiểm tra thay đổi cache metadata, load balancer/CDN policies, CORS hoặc public ACL.
5. Audit Logs tìm configuration changes; Data Access logs chỉ sử dụng nếu đã bật và có đủ quyền.
6. Kiểm tra chiến dịch traffic hợp lệ, bot crawl, abuse hoặc lỗi code download lặp.
7. Áp dụng biện pháp phù hợp, đo lại usage và chi phí sau khi billing cập nhật.

Nếu nguyên nhân là CDN bypass do một thay đổi cấu hình, sửa CDN/cache policy có thể giảm egress. Nếu là truy cập trái phép, cần phối hợp Security để kiểm soát abuse, quyền đọc và bảo vệ dữ liệu, không chỉ tối ưu caching.

## 10. Kiểm tra metrics theo nhóm nguồn chi phí

Billing xác định **phần tiền**; Cloud Monitoring và service-specific metrics giúp xác định **cơ chế tạo ra chi phí**.

| SKU/Service tăng | Metrics hoặc trạng thái cần quan sát | Những giả thuyết thường gặp |
|---|---|---|
| Compute Engine VM CPU/RAM | Số VM, machine type, thời gian chạy, MIG size | VM tạo thêm, resize, batch chưa dừng |
| Persistent Disk / snapshots | Dung lượng, loại disk, snapshot count và tuổi | Disk orphan, snapshot retention quá dài |
| GKE nodes/workload | Node count, node pool, Pod requests, autoscaling | Node pool tăng, requests overprovision, stuck workloads |
| Cloud Run CPU/memory | Request rate, concurrency, instance count, min instances | Traffic tăng, instance-based billing, min instances đổi |
| Cloud SQL | CPU, storage, connections, instance tier, replicas | Tier/HA thay đổi, workload quá tải, storage auto-grow |
| BigQuery | Jobs, bytes processed, slot consumption, reservations | Truy vấn full scan, job lặp, pipeline thiếu filter |
| Cloud Storage | Stored bytes, operations, network egress, object versions | Data copy, download loop, lifecycle sai, retention |
| Cloud Logging | Ingestion bytes, log volume theo service/severity | Debug logging tăng, retry loop, duplicate logs |
| Pub/Sub | Messages published/delivered, backlog, subscriptions | Publish loop, duplicate delivery, nhiều subscriptions |
| Cloud CDN / Load Balancing | Request count, response size, cache hit/miss, egress | Cache miss, bot traffic, object lớn |
| Secret Manager / Cloud KMS | API request counts theo loại, lỗi/quota | Ứng dụng đọc secret/key liên tục thay vì cache hợp lý |

Đừng chỉ nhìn CPU khi truy nguyên BigQuery hoặc network egress: tài nguyên tính phí có thể nằm ở bytes processed, operations hoặc transfer chứ không phải CPU utilization.

### Cloud Run: nhìn autoscaling và database cùng lúc

Ví dụ Spring Boot service có HikariCP maximumPoolSize 10 và max 40 instances. Nếu tất cả instance cùng sử dụng tối đa pool, database có thể phải chịu khoảng:

~~~text
40 instances × 10 connections/instance
  = 400 potential database connections
~~~

Đây là upper bound cấu hình, không phải số connection thực tế. Nhưng nó nhắc nhóm cần xem **Cloud Run scaling** và **Cloud SQL connections** cùng nhau. Nếu ứng dụng retry vô hạn khi DB chậm, số request/instance có thể tăng, tạo cả lỗi nghiệp vụ lẫn chi phí.

### BigQuery: bytes processed khác dung lượng dataset

BigQuery on-demand queries thường chịu ảnh hưởng số bytes processed/billed, còn các mô hình capacity-based pricing có cách tính khác. Một dataset không tăng kích thước vẫn có thể tạo chi phí cao vì truy vấn lặp nhiều lần, thiếu partition pruning hoặc SELECT * trên bảng lớn.

Cách điều tra:

- Xem BigQuery Job History hoặc INFORMATION_SCHEMA.JOBS_BY_PROJECT trong project/region phù hợp.
- Kiểm tra job ID, principal, creation_time, total_bytes_processed/total_bytes_billed và error.
- Tìm scheduled queries, automation hoặc dashboard làm refresh nhiều lần.
- Kiểm tra partition filters, clustering, cache và slot utilization theo billing model.

INFORMATION_SCHEMA có phạm vi region/project và yêu cầu IAM riêng; không dùng số bytes billed làm công thức chung cho mọi mô hình giá. Dữ liệu job metadata có thể chịu retention/visibility khác Billing export.

### Cloud Logging: chính cơ chế quan sát cũng tạo chi phí

Ứng dụng bật DEBUG trong production có thể ghi hàng triệu message không cần thiết; logging ingestion và retention tăng. Tuy nhiên, tắt toàn bộ security/audit logs để tiết kiệm có thể khiến sự cố khó điều tra và vi phạm chính sách. Hướng xử lý:

1. Nhóm logs theo service và severity; tìm nguồn tăng volume.
2. Kiểm tra release thay đổi log level, duplicate exporters hoặc retry loop.
3. Giảm log không có giá trị, sampling traffic logs phù hợp.
4. Giữ audit/security events bắt buộc, correlation ID và error signals.
5. Đo lại ingestion, error triage capability và chi phí.

## 11. Khi tăng chi phí là tín hiệu an ninh

Một cost spike bất thường có thể là hậu quả của credential bị lộ, crypto-mining trái phép, workload được tạo bởi principal lạ, storage egress hoặc API abuse. Đừng tự mặc định mọi cost spike là tấn công; nhưng nên phân loại sớm để không bỏ lỡ tín hiệu.

### Các dấu hiệu đáng ưu tiên

- VM/GPU mới được tạo tại region ít dùng, ngoài lịch triển khai.
- Service account mới hoặc key mới có quyền rộng, được sử dụng bất thường.
- API usage tăng mạnh mà traffic nghiệp vụ không tăng tương ứng.
- Network egress đến những destination không giải thích được.
- IAM policy hoặc firewall thay đổi ngay trước khi các resource lạ xuất hiện.
- Logging disabled hoặc audit retention/sinks bị sửa không theo quy trình.
- Nhiều resource được tạo rồi xóa nhanh, xuất hiện ở nhiều project.

### Phân biệt ba tình huống

| Nhóm | Ví dụ | Cách xử lý |
|---|---|---|
| Thay đổi hợp lệ | Marketing campaign hoặc batch đã duyệt | Xác minh owner, cập nhật forecast/budget |
| Lỗi cấu hình/vận hành | Cron job lặp, debug logs, min instances tăng | Rollback/change control, bảo vệ SLO |
| Nghi ngờ xâm nhập | Principal lạ tạo máy đào tiền mã hóa | Kích hoạt security incident response, giữ bằng chứng và cô lập có kiểm soát |

### Khi nghi có credential compromise

1. Xác nhận scope: project, principal, resource, thời gian và phí dự kiến.
2. Ghi evidence từ logs/asset inventory theo quy trình bảo mật; hạn chế log payload nhạy cảm.
3. Báo Security/on-call và người sở hữu billing account.
4. Đánh giá việc vô hiệu hóa credential/thu hồi quyền hoặc cô lập resource theo runbook, bảo đảm không phá hỏng dịch vụ trọng yếu ngoài dự kiến.
5. Xem xét các project khác có dùng cùng principal hoặc key không.
6. Khôi phục bằng danh tính/khóa an toàn và kiểm chứng luồng nghiệp vụ.
7. Theo dõi audit/billing sau xử lý, rà soát root cause và tránh tái diễn.

**Không xóa ngay resource nghi bị chiếm quyền khi chưa xem xét bảo toàn chứng cứ**. Tùy sự cố, việc stop/quarantine hoặc snapshot phục vụ điều tra có thể quan trọng; mọi thao tác phải tuân thủ chính sách ứng phó sự cố và bảo vệ dữ liệu.

### Audit Logs và attribution

Sự kiện có principalEmail là một service account không đủ để biết ai ra quyết định. Cần đối chiếu với Cloud Build trigger, commit, CI runner identity, service agent và quyền impersonation. Một service account có thể được sử dụng hợp lệ bởi automation hoặc bị lạm dụng; nhật ký xác định **danh tính gọi API**, không luôn xác định **con người cuối cùng**.

## 12. Runbook 0–15–60 phút khi nhận cảnh báo

Mục tiêu không phải xóa chi phí trong vài giây mà là **giảm tổn thất mà không gây outage hoặc mất dữ liệu lớn hơn**.

### 0–15 phút: xác minh và phân loại

1. Ghi alert ID, thời điểm, billing account, currency, project, budget/anomaly threshold.
2. Kiểm tra xem thông báo mới hay bị gửi trùng; xác minh kênh và dữ liệu gốc.
3. Mở Billing Reports hoặc BigQuery với cùng filter để xác định service/SKU.
4. Đánh giá độ trễ dữ liệu: hôm nay hoặc hôm qua có thể chưa đầy đủ.
5. Xác minh mức tác động tuyệt đối; tránh nâng P1 vì một khoản tăng rất nhỏ.
6. Xác định workload owner, business event và change calendar.
7. Nếu có dấu hiệu xâm nhập, chuyển ngay quy trình Security Incident Response.

### 15–60 phút: khoanh vùng và hành động có kiểm soát

1. Dùng detailed export/resource inventory để xác định resource, nếu có.
2. So metrics trước/sau: instances, egress, requests, BigQuery jobs, logs volume.
3. Tìm Admin Activity / Data Access audit events tương ứng.
4. Đối chiếu PR/deploy/config change/quota changes.
5. Tính chi phí tăng thêm dự kiến và đánh giá rủi ro tiếp tục.
6. Chọn hành động tối thiểu: rollback release, giảm debug logs, sửa job schedule, giới hạn autoscaling theo runbook.
7. Cần approval/communication nếu có tác động production hoặc compliance.
8. Theo dõi cả cost driver và service SLI/SLO sau thay đổi.

### Sau 60 phút đến 24 giờ: xác nhận và ngăn tái diễn

- Kiểm tra usage/cost sau xử lý khi Billing export cập nhật, không đợi dashboard tức thì.
- Ghi root cause, contributing factors, timeline và evidence links.
- Đánh giá có cần điều chỉnh budget forecast hoặc anomaly threshold.
- Thêm guardrails: quota, labels, IaC review, branch protection, tests, retention policy.
- Đưa action items vào tracker có owner, priority, deadline và tiêu chí kiểm chứng.
- Theo dõi resource orphan và chi phí tiếp tục phát sinh; xác nhận cleanup an toàn.

### Mức độ nghiêm trọng gợi ý

| Severity | Điều kiện minh họa | Cách phản hồi |
|---|---|---|
| SEV1 | Nghi xâm nhập hoặc nguy cơ tác động ngân sách rất lớn/lan rộng nhanh | Security incident + incident commander |
| SEV2 | Chi phí vượt threshold lớn, workload sai cấu hình đang tăng | SRE/FinOps on-call, change control |
| SEV3 | Tăng chi phí vừa phải, có owner và chưa rủi ro tiếp diễn cao | Ticket và xử lý trong giờ làm việc |
| Informational | Mức tăng đã được dự toán, chiến dịch hợp lệ | Gắn known change và cập nhật forecast |

Các mức độ trên là ví dụ; tổ chức nên đặt ngưỡng định lượng dựa vào budget, burn rate và business criticality.

## 13. Tự động hóa phát hiện mà không tự động gây outage

Một quy trình FinOps/SRE có thể kết hợp hai luồng bổ sung:

1. **Gần thời gian thực:** Cloud Monitoring alerts từ request rate, autoscaling, egress, query jobs hoặc log ingestion để phát hiện workload bất thường ngay khi xảy ra.
2. **Theo dữ liệu chi phí đã báo cáo:** Billing budgets/anomaly notifications hoặc Scheduled Queries trên Billing export để xác nhận giá trị tiền và tìm SKU gây tăng.

Không kỳ vọng Billing export phát hiện được từng phút. Với những thay đổi rất nhanh, hãy dùng quota, metrics và guardrails resource để hạn chế blast radius trước khi hóa đơn xuất đủ.

### Mô hình tham khảo

~~~mermaid
flowchart TD
    BILL["Cloud Billing export → BigQuery"]
    METRIC["Cloud Monitoring metrics"]
    NOTI["Budget / anomaly notifications"]
    QUERY["Scheduled query / Workflows"]
    RULE["Anomaly rule + data freshness gate"]
    PUB["Pub/Sub / incident event bus"]
    ENRICH["Enrich with audit logs, owner and changes"]
    DEDUP["Dedup / severity / cooldown"]
    HUMAN["SRE + FinOps + Security"]
    ACTION["Manual approval / safe automated remediation"]
    VERIFY["Measure usage, SLO and delayed cost"]
    BILL --> QUERY --> RULE --> PUB
    METRIC --> PUB
    NOTI --> PUB
    PUB --> ENRICH --> DEDUP --> HUMAN --> ACTION --> VERIFY
~~~

Một scheduler chạy quá thường xuyên không làm Billing export trở thành realtime. Nếu khoảng thời gian dữ liệu chưa đủ đầy, rule nên trả trạng thái **INSUFFICIENT_DATA** và giữ việc cảnh báo sớm cho metrics.

### Thiết kế handler cảnh báo

Handler nên:

- Kiểm tra event source, schema version, billing account/project được phép và quyền nhận thông báo.
- Đặt idempotency key dựa trên event ID hoặc tổ hợp account, budget/anomaly ID, time bucket và category.
- Deduplicate vì Pub/Sub delivery có thể lặp; dùng cooldown hợp lý cho cùng nguyên nhân.
- Xác định owner từ project catalog, labels hoặc service ownership; không mặc định người gọi API là người nhận ticket.
- Gửi thông báo gồm tác động, dashboard, time window, resource/SKU candidates và độ tin cậy của dữ liệu.
- Hạn chế gọi BigQuery/API quá nhiều để bản thân bộ phát hiện không tạo chi phí không cần.
- Không ghi toàn bộ billing dataset hoặc audit log nhạy cảm vào public chat.
- Không chạy hành động phá hủy production từ payload chưa được xác minh.

### Pseudocode rule xử lý

~~~text
on_cost_signal(signal):
    validate_signal_source_and_scope(signal)
    key = build_dedup_key(signal)

    if already_processed(key):
        return

    context = fetch_current_cost_breakdown_or_mark_delayed(signal)
    metrics = fetch_resource_metrics(signal.project, signal.time_window)
    change_events = find_relevant_admin_audit_events(
        signal.project, signal.time_window)
    owner = resolve_owner(signal.project, signal.service)

    severity = classify_impact_and_security_indicators(
        context, metrics, change_events)
    create_or_update_incident(key, owner, severity, evidence_links)

    if severity_is_critical:
        page_on_call()
    else:
        send_to_triage_queue()

    # Remediation phải dùng approval/runbook; không auto-delete production.
~~~

Đây là mã giả, không phải handler hoàn chỉnh. Trong triển khai thật cần timeout, error handling, retry, IAM, observability và dữ liệu dedup bền vững.

### Có nên tự động tắt Billing của một project?

Vô hiệu hóa Billing có thể làm ngừng những dịch vụ thiết yếu hoặc gây mất khả năng truy cập dữ liệu; tác động phục hồi có thể phức tạp hơn phần chi phí được tiết kiệm. Nếu tổ chức dùng tự động hóa kiểu này, cần:

1. Chỉ cho phép trên resource/project được phê duyệt, thường là môi trường test không trọng yếu.
2. Có thông tin owner, business criticality, exception và escalation path.
3. Chạy dry-run và kiểm tra preconditions trước.
4. Ghi audit và cơ chế khôi phục billing/service có người chịu trách nhiệm.
5. Kiểm tra với tình huống thông báo lặp, trễ hoặc sai threshold.

Với production, ưu tiên xử lý nguyên nhân cục bộ (ví dụ dừng job test ngoài kế hoạch) hơn một thao tác tắt toàn project. **Cảnh báo chi phí là đầu vào để ra quyết định, không phải lệnh tự động phá hủy resource.**

## 14. Bốn tình huống điều tra thực tế

### Tình huống A — Cloud Run tăng gấp nhiều lần sau deploy

Giả sử Orders API chạy Spring Boot trên Cloud Run. Chi phí Cloud Run tăng sau một bản phát hành, nhưng lượng đơn hàng thành công gần như không đổi.

**Điều tra:**

1. Billing: xem service/SKU CPU, memory và thời gian sử dụng có tăng không.
2. Monitoring: requests, instances, concurrency, CPU utilization và error rate.
3. Cloud Run revision configs: min instances, concurrency, max instances và CPU allocation/billing mode.
4. Cloud Audit Logs: thay đổi cấu hình Cloud Run, principal deploy, method/time.
5. Deployment history: commit có đổi HikariCP, retry policy, log level hoặc startup logic không.
6. Database: connection errors và query latency có tăng không.

**Giả thuyết:** release làm tăng độ trễ mỗi request, dẫn đến nhiều instance hơn; hoặc cấu hình minimum instances bị thay đổi. Nếu traffic hợp lệ tăng thì nguyên nhân là workload volume, không nhất thiết do lỗi release.

**Hành động có kiểm soát:** rollback revision nếu user-facing SLO suy giảm; hoặc tối ưu concurrency/min instances sau load test. Kiểm tra cost trend khi dữ liệu billing cập nhật và xác nhận không tăng DB errors.

### Tình huống B — Compute Engine/GKE có tài nguyên mồ côi

Một batch test tạo thêm VM hoặc node pool rồi không cleanup. Billing hiển thị Compute Engine CPU và Persistent Disk tăng.

**Điều tra:**

- Detailed export/resource inventory cho biết resource candidates.
- Compute Engine Audit Logs cho biết insert hoặc resize, principal/caller và time window.
- GKE audit/change logs cho thấy cluster/node pool thay đổi nếu tài nguyên thuộc GKE.
- Resource labels, owner và TTL xác nhận đây có phải test resource không.
- Monitoring xác nhận CPU gần như idle không đồng nghĩa toàn bộ chi phí bằng 0.

**Hành động:** hỏi owner và kiểm tra có thuộc MIG, cluster hoặc hệ thống backup/DR không. Chỉ dừng/xóa tài nguyên đã được chứng minh không còn dùng, theo quy trình approval và có thể rollback. Disk/snapshot có retention riêng; dừng VM không tự xóa boot disk.

### Tình huống C — Cloud Storage/network egress tăng dù object count ổn định

Billing cho thấy network egress tăng, nhưng số object và dung lượng bucket gần như không đổi.

**Điều tra:**

1. Phân biệt SKU storage capacity, Class A/B operations và network transfer.
2. Đo bytes egress, request count, CDN cache hit ratio nếu có.
3. Xem log HTTP/load balancer, user agent, path và HTTP status theo chính sách bảo mật.
4. Tìm thay đổi Cache-Control, URL map, Cloud CDN mode hoặc bucket IAM.
5. Xem Data Access logs nếu đã bật và có quyền; không coi thiếu log là bằng chứng không có download.
6. Đối chiếu release asset mới, user campaign hoặc bot crawl.

**Hành động:** sửa caching, chống abuse hoặc điều chỉnh access controls theo nguyên nhân. Nếu dữ liệu không được phép công khai, kích hoạt security response; CDN invalidation không thu hồi được những bản sao đã bị download ra bên ngoài.

### Tình huống D — BigQuery chi phí cao do dashboard

Một dashboard mới refresh liên tục bằng các truy vấn full scan. Billing cho thấy BigQuery Analysis tăng, nhưng không có resource mới nào được tạo.

**Điều tra:**

- Project/service/SKU trong Billing export.
- BigQuery Job History và INFORMATION_SCHEMA theo region/project.
- Principal của job, scheduled query/BI tool và total_bytes_billed nếu on-demand.
- Dấu vết tạo/sửa scheduled query hoặc dashboard trong change records.
- Query plan, partition filters, materialized views và refresh cadence.

**Hành động:** áp dụng partition pruning, hạn chế refresh, materialization hoặc capacity model phù hợp. Test kết quả query đúng trước khi thay đổi logic; đo lại billed bytes/slot usage và chi phí thực tế.

### Tổng kết bốn tình huống

| Tình huống | Driver chi phí | Bằng chứng quyết định | Rủi ro khi xử lý vội |
|---|---|---|---|
| Cloud Run | CPU/memory/instances | Revision config + metrics + Billing | Outage do giới hạn scale quá thấp |
| VM/GKE orphan | VM/node/disk hours | Resource inventory + audit + owner | Xóa nhầm hạ tầng dùng chung |
| Storage egress | Bytes transferred/requests | CDN/HTTP metrics + config changes | Làm public data vô tình hoặc gây 403 |
| BigQuery | Query bytes/slots | Job history + billing SKU | Làm sai dashboard hoặc pipeline nghiệp vụ |

## 15. Labels, tags và cost attribution

Nếu không biết workload nào sở hữu chi phí, quá trình điều tra sẽ bị chậm dù dữ liệu export đầy đủ. Một mô hình ownership thường có:

| Metadata | Ví dụ | Ý nghĩa |
|---|---|---|
| application | orders-api | Service chịu trách nhiệm |
| environment | production | Tách môi trường |
| team | commerce | Nhóm sở hữu |
| cost_center | cc-102 | Phân bổ tài chính |
| managed_by | terraform | Nguồn quản lý cấu hình |
| expires_at | 2026-11-30 | Tín hiệu cho tài nguyên lab tạm |

Không phải dịch vụ hoặc SKU nào cũng hỗ trợ mọi label/tag ở cấp resource. Nên kết hợp:

- Project hierarchy rõ ràng.
- Resource labels/tags nơi được hỗ trợ và được Billing export.
- Danh mục service ownership với người trực và escalation.
- Shared-cost allocation rule cho network, platform, support và hạ tầng chung.
- Báo cáo UNATTRIBUTED hoặc UNALLOCATED để làm rõ nguồn chưa được gắn nhãn.

**Đừng nhầm label với quyền IAM hay chính sách TTL.** Một label expires_at tự nó không tự xóa VM; cần automation kiểm tra sở hữu, approval và điều kiện an toàn trước cleanup.

### Vấn đề labels xuất hiện trễ

Gán label cho resource hôm nay thường không gắn lại cho chi phí của các ngày trước. Một số thông tin tag có độ trễ propagate. Vì vậy, báo cáo chi phí có thể cho thấy một resource ở nhóm UNLABELED trong giai đoạn đầu dù hiện tại đã có label. Tránh điều chỉnh lịch sử dữ liệu một cách im lặng; nếu cần phân bổ lại, ghi rõ allocation rule và version của quy tắc.

### Chỉ số chi phí theo giá trị nghiệp vụ

Ngoài cost/project, xem:

~~~text
Cost per successful order
  = attributable net service cost / successful orders

Cost per 1,000 API requests
  = attributable net cost / valid requests * 1000

BigQuery cost per report
  = attributable analytics cost / completed reports
~~~

Đây là các KPI gần đúng nếu đã xác định attribution. Khi traffic tăng hợp lệ, tổng hóa đơn có thể tăng nhưng **cost per successful order** giữ nguyên hoặc giảm. Điều đó không nhất thiết là sự cố; cần xem hiệu suất đơn vị và forecast.

## 16. Phát hiện sớm qua quota và cấu hình hạ tầng

Chi phí thường là hậu quả của những điều kiện kỹ thuật: instance max quá cao, jobs không có deadline, log level DEBUG, storage lifecycle bỏ quên, cross-region transfer hoặc API gọi liên tục.

### Guardrails trước khi sự cố xảy ra

| Kiểm soát | Giảm rủi ro | Cần chú ý |
|---|---|---|
| Cloud Run max instances | Giới hạn số instance khi burst | Có thể làm rơi request nếu cấu hình quá thấp |
| GKE ResourceQuota/requests/limits | Kiểm soát capacity trong namespace | Overprovision có thể làm Pod Pending |
| CI job timeout/cleanup | Tránh VM/cluster test chạy mãi | Cần fallback sweeper nếu runner chết |
| Project/service quotas | Giới hạn một số dạng sử dụng | Không phải hard cap tổng hóa đơn |
| BigQuery maximum bytes billed | Chặn query quá lớn theo giới hạn | Cần chọn ngưỡng phù hợp với báo cáo hợp lệ |
| Logging filters/sampling | Tránh log volume không cần thiết | Không loại audit/security events bắt buộc |
| Storage lifecycle/retention | Giảm object versions/snapshots cũ | Có thể xóa dữ liệu cần phục hồi nếu policy sai |
| IAM/Org Policy | Hạn chế tạo resource hoặc region ngoài kế hoạch | Phải test policy để tránh chặn workload hợp lệ |

Các guardrail nên được định nghĩa bằng Infrastructure as Code/policy-as-code, có review và test trước khi áp dụng. Một thay đổi chi phí “tối ưu” khiến người dùng gặp lỗi nhiều hơn có thể tạo tổng tổn thất kinh doanh lớn hơn.

### Chú ý khi giới hạn autoscaling

Không chỉ giảm max instances để chặn chi phí. Cần kiểm tra:

- Throughput và latency SLO.
- Giới hạn CPU/memory/connection pool.
- Tốc độ scale-out và các request bị từ chối.
- Quota downstream (Cloud SQL, Pub/Sub, API đối tác).
- Lượng backlog và độ trễ xử lý.

Một quyết định tốt có thể là xử lý retry storm hoặc lỗi loop, thay vì giảm công suất cho cả request hợp lệ.

## 17. Thực hành phân tích bằng dữ liệu tổng hợp

Nếu chưa có quyền truy cập Billing export thật, có thể học logic phát hiện trên một tập dữ liệu giả định. Dữ liệu dưới đây là **synthetic**, không phải số liệu sử dụng hay bảng giá Google Cloud.

### Một bảng chi phí ngày

| Ngày | Project | Service | Net cost (đơn vị giả định) |
|---|---|---|---:|
| 2026-11-09 | orders-prod | Cloud Run | 20 |
| 2026-11-10 | orders-prod | Cloud Run | 22 |
| 2026-11-11 | orders-prod | Cloud Run | 21 |
| 2026-11-12 | orders-prod | Cloud Run | 19 |
| 2026-11-13 | orders-prod | Cloud Run | 20 |
| 2026-11-14 | orders-prod | Cloud Run | 21 |
| 2026-11-15 | orders-prod | Cloud Run | 85 |
| 2026-11-15 | orders-prod | Cloud SQL | 26 |

Tập giả định cho thấy Cloud Run tăng từ khoảng 20 lên 85 đơn vị vào ngày 15/11. Trước khi kết luận incident, nhóm phải xem metric instance/requests, bản phát hành, campaign và chi phí Cloud SQL. Có thể phát hiện bằng threshold tuyệt đối và tương đối, nhưng dữ liệu này quá ngắn để chứng minh yếu tố mùa vụ.

### SQL chạy trên CTE tổng hợp

~~~sql
WITH sample AS (
  SELECT DATE '2026-11-09' AS usage_day, 'Cloud Run' AS service, 20.0 AS net_cost
  UNION ALL SELECT DATE '2026-11-10', 'Cloud Run', 22.0
  UNION ALL SELECT DATE '2026-11-11', 'Cloud Run', 21.0
  UNION ALL SELECT DATE '2026-11-12', 'Cloud Run', 19.0
  UNION ALL SELECT DATE '2026-11-13', 'Cloud Run', 20.0
  UNION ALL SELECT DATE '2026-11-14', 'Cloud Run', 21.0
  UNION ALL SELECT DATE '2026-11-15', 'Cloud Run', 85.0
  UNION ALL SELECT DATE '2026-11-15', 'Cloud SQL', 26.0
),
baseline AS (
  SELECT
    service,
    AVG(net_cost) AS baseline_cost
  FROM sample
  WHERE usage_day < DATE '2026-11-15'
  GROUP BY service
),
target AS (
  SELECT
    service,
    SUM(net_cost) AS target_cost
  FROM sample
  WHERE usage_day = DATE '2026-11-15'
  GROUP BY service
)
SELECT
  target.service,
  ROUND(target_cost, 2) AS target_cost,
  ROUND(baseline_cost, 2) AS baseline_cost,
  ROUND(target_cost - IFNULL(baseline_cost, 0), 2) AS absolute_increase,
  ROUND(
    100 * SAFE_DIVIDE(
      target_cost - baseline_cost,
      NULLIF(baseline_cost, 0)
    ), 1
  ) AS percent_increase,
  CASE
    WHEN baseline_cost IS NULL THEN 'NEW_SERVICE_OR_NO_HISTORY'
    WHEN target_cost >= 50
       AND target_cost - baseline_cost >= 30
       AND target_cost > 2 * baseline_cost THEN 'ANOMALY_CANDIDATE'
    ELSE 'REVIEW'
  END AS detection_result
FROM target
LEFT JOIN baseline USING (service)
ORDER BY target_cost DESC;
~~~

Với dữ liệu minh họa, Cloud Run được xếp **ANOMALY_CANDIDATE** vì chi phí vượt cả ngưỡng tuyệt đối lẫn ngưỡng tương đối. Cloud SQL không có lịch sử trong tập dữ liệu nên được đánh dấu khác, tránh chia cho 0.

Mục đích ví dụ là học logic điều kiện; thực tế nên dùng nhiều tuần, cùng thứ hoặc chu kỳ nghiệp vụ và phải chờ dữ liệu đủ. **Một rule phát hiện chỉ tạo ứng viên điều tra, không tạo bản án nguyên nhân.**

### Bài thực hành tăng độ khó

Hãy tự sửa dataset:

1. Thêm một tuần có Cloud Run cost tăng do sự kiện marketing đã được duyệt.
2. Thêm một service mới không có lịch sử.
3. Thêm credit âm khiến net cost thấp nhưng gross tăng.
4. Thêm dữ liệu một ngày chưa hoàn chỉnh rồi chứng minh vì sao phải loại ngày đó.
5. Tạo một allowlist cho planned maintenance và một ticket điều tra cho spike chưa giải thích.

Khi test phát hiện, kiểm tra cả false positive và false negative chứ không chỉ báo đúng ngày có giá trị 85.

## 18. Đối soát kết quả trước khi báo nguyên nhân cuối cùng

Một hệ thống báo cáo chi phí có thể khác với giao diện Billing vì thời gian, bộ lọc, credits hoặc cách nhóm khoản phí. Trước khi viết root cause, cần đối soát:

| Câu hỏi | Kiểm tra |
|---|---|
| Có đúng billing account không? | Billing account ID và các project liên kết |
| Có đúng đơn vị tiền không? | currency trong export, tránh gộp nhiều account |
| So theo usage hay invoice? | usage_start_time khác invoice.month |
| Dữ liệu đã đầy đủ? | export_time, độ trễ service, ngày đã hoàn tất |
| Có tính credits? | cost + credits.amount, phân biệt gross/net |
| Có tính tax/adjustment? | cost_type và mục đích báo cáo |
| Resource ID có thiếu? | Detailed export coverage và resource.name null |
| Labels có đầy đủ? | Ngày áp dụng, propagation và giới hạn dịch vụ |
| Sự kiện audit là thành công? | protoPayload.status, operation, follow-up event |
| Principal thuộc tổ chức nào? | Service account owner, impersonation, CI trigger |

### Gross tăng nhưng net không tăng

Ví dụ một commitment discount vẫn bù cho workload nên net cost ổn định. Khi đó có thể chưa phải sự cố ngân sách hiện tại nhưng vẫn là tín hiệu tăng consumption và tăng rủi ro nếu credit/commitment hết hạn. Hãy báo hai chiều **resource usage** và **cost after credits**.

### Net tăng nhưng usage không tăng

Kiểm tra discounts, credit expiration, SKU price, billing account agreement, currency hoặc adjustment. Đây có thể là vấn đề dự toán/tài chính, không phải lỗi resource mới. Audit Logs về VM creation không giải thích những thay đổi đó.

### Chi phí giảm ngay sau khi sửa cấu hình?

Không đánh giá ngay theo Billing report vì usage reporting có thể trễ. Đầu tiên xác minh resource metrics đã giảm, ví dụ instance count, bytes processed hoặc log ingestion. Sau đó xác nhận billed costs khi dữ liệu xuất đủ và ghi rõ khoảng thời gian đã chờ.

### Chi phí tháng không khớp query theo ngày

Nếu cần đối soát hóa đơn, nhóm theo **invoice.month** và tính cả các loại cost_type theo hướng dẫn Cloud Billing; query theo ngày sử dụng có thể khác do các khoản ghi muộn hoặc adjustment. Không sửa SQL bằng cách cộng thêm một “số chênh” thủ công mà không tìm khoản phí tương ứng.

## 19. Mẫu báo cáo điều tra chi phí bất thường

Một báo cáo hữu ích cần đủ rõ để SRE, FinOps và Security hiểu cùng một sự kiện.

~~~markdown
# Cost anomaly investigation: CA-2026-011

## Thông tin
- Status: INVESTIGATING / CONFIRMED / RESOLVED / FALSE_POSITIVE
- Billing account: <internal reference>
- Project/service/SKU:
- Currency:
- Detection source: Budget / anomaly / query / metrics
- Detected at (UTC):
- Owner / on-call:
- Business criticality:

## Tác động
- Baseline: ... (định nghĩa thời gian và phương pháp)
- Observed cost: ... (gross/net, nguồn dữ liệu)
- Estimated excess: ... (kèm độ trễ/độ chắc chắn)
- Run rate nếu tiếp diễn:
- SLO và ảnh hưởng nghiệp vụ:
- Khả năng liên quan đến security incident:

## Timeline
| UTC | Nguồn | Event/metric | Evidence link |
|---|---|---|---|
| | | | |

## Giả thuyết
1. ...
2. ...

## Bằng chứng
- Billing export query (version/filters):
- Metrics dashboard:
- Audit Logs query:
- Change/deployment record:
- Resource inventory:

## Root cause và contributing factors
- Root cause (chỉ khi đã xác minh):
- Yếu tố làm mức tăng lớn hơn:
- Các giả thuyết đã loại và lý do:

## Remediation
- Action:
- Owner/approver:
- SLO guardrails:
- Rollback path:

## Verification
- Driver metric trước/sau:
- Billing cost sau khi xuất đủ:
- No-regression checks:
- Cleanup / security follow-up:

## Phòng tái diễn
| Action | Owner | Deadline | Cách kiểm chứng |
|---|---|---|---|
| | | | |
~~~

Mẫu này dùng để ghi evidence và quyết định, không thay thế Security incident report khi có xâm nhập. Không dán credential, raw customer data hoặc billing dataset chứa thông tin nhạy cảm vào tài liệu chia sẻ công khai. Giữ liên kết đến Logs Explorer/Billing dashboard có IAM phù hợp.

## 20. Bài tập thực hành: từ alert đến giải thích nguyên nhân

Giả sử nhóm vận hành Orders API trên Cloud Run, dùng Cloud SQL, Cloud Storage và BigQuery để làm báo cáo. Một ngày, FinOps gửi cảnh báo: **tổng chi phí usage của project orders-prod tăng đáng kể so với tuần trước**.

Mục tiêu bài tập là tìm bằng chứng xác nhận hoặc loại bỏ các giả thuyết, tạo báo cáo và đề xuất hành động an toàn. Không cần tạo resource tính phí trên GCP để hoàn thành phần phân tích ban đầu; có thể dùng synthetic SQL ở mục 17.

### Phần A — Chuẩn bị

1. Xác định billing account và project test hoặc dataset được cấp phép.
2. Ghi owner, business criticality và ngưỡng cost impact có ý nghĩa.
3. Mở Cloud Billing Reports và lọc đúng project/period/currency.
4. Kiểm tra budget/anomaly notifications đã được cấu hình hay chưa.
5. Xác nhận có Billing export Standard/Detailed và thời gian bắt đầu thu thập.
6. Kiểm tra quyền xem Cloud Logging, Audit Logs và metrics.

**Bằng chứng:** danh sách nguồn dữ liệu, phạm vi, thời gian, IAM và mức độ trễ dữ liệu.

### Phần B — Phân tích BigQuery

1. Chạy SQL nhóm net cost theo project/service/ngày trên dữ liệu được phép.
2. Liệt kê ba service đóng góp tuyệt đối lớn nhất vào mức tăng.
3. Drill down xuống SKU của service đứng đầu.
4. So sánh gross, credits và net để loại trừ biến động discount.
5. Nếu có Detailed export, tìm resource candidates và kiểm tra các dòng resource.name NULL.
6. Lập bảng baseline và actual với cùng timezone, currency và cost_type.
7. Ghi các giả định về data completeness và planned workload changes.

**Bằng chứng:** query đã lưu (hoặc bản trích không nhạy cảm), bảng delta và cách tính ngưỡng.

### Phần C — Đối chiếu Audit Logs và metrics

1. Giả sử Cloud Run là service tăng mạnh: xem changes trong Admin Activity của run.googleapis.com.
2. Đối chiếu revision configs, deployment time và Cloud Run instance count.
3. Xem Cloud SQL connections và error rate để tìm tín hiệu retry/DB saturation.
4. Nếu không có thay đổi cấu hình, kiểm tra traffic tăng hợp lệ hoặc hệ thống gọi API lặp.
5. Nếu dùng service account, tìm owner của pipeline và commit/triggers liên quan.
6. Kiểm tra có principal lạ, service lạ hoặc resource tạo ngoài lịch hay không.
7. Ghi một bảng timeline để giải thích mức độ tương quan và bằng chứng còn thiếu.

**Bằng chứng:** links Logs Explorer, dashboard và change records, không đưa payload nhạy cảm vào báo cáo.

### Phần D — Đề xuất quyết định

Xây dựng ba phương án:

- **No action/forecast update:** khi traffic tăng hợp lệ và unit cost ổn định.
- **Controlled rollback/fix:** khi một deploy hoặc cấu hình gây lỗi retry, log volume hoặc scale ngoài dự kiến.
- **Security incident response:** khi có tín hiệu credential abuse/resource lạ.

Với mỗi phương án, ghi:

- Lợi ích dự kiến.
- Rủi ro đối với SLO, dữ liệu, khách hàng.
- Người có quyền approve và người vận hành.
- Cách rollback.
- Chỉ số xác minh sau thay đổi.

Không thực hiện thao tác dừng, xóa hoặc đổi IAM trên production trong bài tập nếu chưa có quy trình được phê duyệt. Có thể kiểm tra logic dự đoán bằng dữ liệu giả hoặc môi trường thử nghiệm được cấp riêng.

### Phần E — Viết báo cáo và cải tiến

1. Điền mẫu báo cáo mục 19 với dữ liệu đã kiểm tra.
2. Nêu một root cause hoặc danh sách giả thuyết nếu chưa đủ bằng chứng.
3. Định lượng phần chi phí tăng thêm trong currency đúng, với phạm vi và mức độ chắc chắn.
4. Đề xuất ba preventive actions có owner và deadline.
5. Đặt một monitoring alert và một cost anomaly rule có ngưỡng phù hợp.
6. Thử trường hợp Pub/Sub notification bị gửi lặp trong handler giả lập.
7. Đề xuất cách xác minh chi phí đã giảm sau khi dữ liệu billing được cập nhật đầy đủ.

### Tiêu chí hoàn thành

| Nội dung | Đạt khi |
|---|---|
| Tính đúng dữ liệu | Phân biệt usage vs invoice, gross vs net, currency và data delay |
| Phát hiện | Có baseline, ngưỡng tuyệt đối/tương đối và cách xử lý service mới |
| Khoanh vùng | Nêu project, service, SKU và resource nếu dữ liệu cho phép |
| Audit correlation | Có principal/method/time và không coi tương quan là nhân quả |
| Bảo mật | Xác định dấu hiệu nghi xâm nhập và đường escalation |
| Hành động | Có owner, approval, tác động SLO và rollback path |
| Đo lại | Dùng metrics trước, billing sau khi export đủ |
| Báo cáo | Có timeline, evidence, conclusion và action items |

## 21. Checklist phản ứng với tăng chi phí bất thường

- [ ] Xác định billing account/project chính xác.
- [ ] Xác minh alert không chỉ là thông báo lặp hoặc ngưỡng đã biết.
- [ ] Ghi thời gian, timezone, currency và billing period.
- [ ] Phân biệt số tiền thực tế, forecast và ước tính chưa finalized.
- [ ] Kiểm tra độ trễ dữ liệu Billing export/Reports.
- [ ] Phân biệt usage date với invoice month.
- [ ] So sánh gross cost, credits và net cost.
- [ ] Xem cost_type (regular/tax/adjustment) đúng mục đích.
- [ ] Xác định project, service, SKU gây tăng theo mức tuyệt đối.
- [ ] Kiểm tra resource-level data nếu service/export hỗ trợ.
- [ ] Xem workload metrics và resource inventory.
- [ ] Đối chiếu deploy/config changes trong Audit Logs.
- [ ] Kiểm tra principalEmail, resourceName và operation status nếu có.
- [ ] Xác nhận Data Access logging có được bật trong phạm vi cần thiết không.
- [ ] Xem bất thường IAM, service account, keys hoặc API usage lạ.
- [ ] Kiểm tra traffic/campaign/batch được phê duyệt trước khi kết luận lỗi.
- [ ] Xác định owner, escalation và business criticality.
- [ ] Không auto-delete/tắt billing production chỉ từ một cost signal.
- [ ] Đánh giá SLO trước khi giảm autoscaling/capacity.
- [ ] Nếu security compromise, bảo toàn chứng cứ và dùng incident runbook.
- [ ] Đặt expiration/cleanup owner cho resource lab hoặc tạm.
- [ ] Lưu query, filter, timeline và evidence links.
- [ ] Đo driver metric trước/sau remediation.
- [ ] Xác nhận billed cost trend khi dữ liệu xuất đầy đủ.
- [ ] Tạo preventive actions và cập nhật forecast/budget hợp lý.

## Câu hỏi tự kiểm tra

**1. Vì sao không thể dùng Billing export như một bộ đếm chi phí theo từng giây?**

Vì usage và cost được báo cáo có độ trễ và có thể có điều chỉnh/ghi nhận muộn. Dùng metrics hoặc resource quotas cho phát hiện kỹ thuật gần thời gian thực; Billing dùng để phân tích tiền khi dữ liệu đủ.

**2. Tại sao tăng 100% không luôn nghiêm trọng hơn tăng 20%?**

Vì tác động tuyệt đối khác nhau. Tăng từ 1 lên 2 có thể ít ảnh hưởng hơn tăng từ 1.000 lên 1.200. Cần kết hợp mức tăng tuyệt đối, tỷ lệ và budget.

**3. cost khác net cost như thế nào?**

Net cost của một nhóm dòng thường được tính bằng cost cộng các credits áp dụng. Discount/credit thay đổi có thể làm net cost tăng dù workload không đổi.

**4. Khi nào dùng usage_start_time và khi nào dùng invoice.month?**

Theo usage_start_time để phát hiện xu hướng vận hành theo thời điểm sử dụng; theo invoice.month để đối soát các dòng thuộc một hóa đơn.

**5. Data Access audit logs có luôn sẵn để tra cứu không?**

Không. Hầu hết dịch vụ cần cấu hình bật trước, có ngoại lệ như BigQuery; retention và IAM vẫn ảnh hưởng khả năng truy cập.

**6. Có thể nối trực tiếp mọi billing line với một log bằng resource.name không?**

Không. Detailed export chỉ hỗ trợ resource-level ở các phạm vi nhất định; resource.name có thể NULL hoặc khác định dạng so với resourceName trong audit logs. Cần kết hợp project, service, location, time và inventory.

**7. Tại sao service account xuất hiện trong audit log chưa chỉ ra ai chịu trách nhiệm cuối cùng?**

Vì service account có thể được sử dụng bởi Cloud Build, automation, impersonation hoặc workload controller. Phải đối chiếu pipeline trigger, commit và quyền impersonation.

**8. Nếu Budget alert vượt 100%, GCP có tự dừng mọi dịch vụ không?**

Không đối với alerts-only budget. Spend-cap budgets chỉ áp dụng cho một số dịch vụ đủ điều kiện và có hành vi riêng. Mọi hành động kiểm soát chi tiêu phải được thiết kế và đánh giá ảnh hưởng.

**9. Nếu gross cost không đổi nhưng net cost tăng, nên xem gì?**

Xem credits, discounts, commitment allocation, pricing, tax/adjustment và scope billing trước khi quy kết lỗi kỹ thuật.

**10. Một Cloud Run revision mới có thể làm chi phí tăng dù requests không tăng không?**

Có. Chẳng hạn request mất nhiều CPU time hơn, concurrency thấp hơn, retry tăng hoặc min instances thay đổi; cần đo instances/CPU/latency và thay đổi cấu hình.

**11. Vì sao cần deduplicate Pub/Sub cost notifications?**

Vì thông báo có thể được gửi lặp hoặc không theo thứ tự. Không deduplicate có thể tạo nhiều ticket hoặc chạy hành động remediation nhiều lần.

**12. Vì sao không nên tắt log toàn bộ để giảm hóa đơn?**

Vì có thể mất audit/security evidence và khả năng xử lý sự cố. Nên tối ưu sampling/retention cho log không thiết yếu trong khi giữ dữ liệu bắt buộc theo chính sách.

## Tài liệu tham khảo

- [Cloud Billing — Export usage cost data to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery)
- [Cloud Billing — Standard usage cost data schema](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage)
- [Cloud Billing — Detailed usage cost data schema](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage)
- [Cloud Billing — Create and manage budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets)
- [Cloud Billing — Programmatic budget/anomaly notifications](https://docs.cloud.google.com/billing/docs/how-to/budgets-programmatic-notifications)
- [Cloud Billing — View and manage cost anomalies](https://docs.cloud.google.com/billing/docs/how-to/manage-anomalies)
- [Cloud Billing — Audit logging](https://docs.cloud.google.com/billing/docs/audit-logging)
- [Cloud Logging — Understanding audit logs](https://docs.cloud.google.com/logging/docs/audit/understanding-audit-logs)
- [Cloud Logging — Enable Data Access audit logs](https://docs.cloud.google.com/logging/docs/audit/configure-data-access)
- [Cloud Logging — Audit logs best practices](https://docs.cloud.google.com/logging/docs/audit/best-practices)
- [Compute Engine — Audit logging](https://docs.cloud.google.com/compute/docs/logging/audit-logging)
- [BigQuery — INFORMATION_SCHEMA.JOBS views](https://docs.cloud.google.com/bigquery/docs/information-schema-jobs)
- [Cloud Monitoring — Metrics and alerting overview](https://docs.cloud.google.com/monitoring/docs/monitoring-overview)
- [Google Cloud — Cost optimization framework](https://docs.cloud.google.com/architecture/framework/cost-optimization)
- [Google Cloud Pricing Calculator](https://cloud.google.com/products/calculator)

## Kết luận

Phát hiện tăng chi phí bất thường là công việc chung của **FinOps, SRE và Security**. Cloud Billing cho biết chi phí tăng ở project, service và SKU nào; Detailed export có thể giúp khoanh vùng resource; Cloud Audit Logs ghi các thao tác thay đổi cấu hình và danh tính gọi API; Monitoring cùng change records giúp kiểm tra nguyên nhân. Không nguồn dữ liệu nào tự chứng minh đầy đủ toàn bộ câu chuyện, đặc biệt khi Billing có độ trễ và audit logs có phạm vi ghi nhận tùy dịch vụ.

Một quy trình đáng tin cậy cần baseline có ý nghĩa, ngưỡng tác động tuyệt đối và tương đối, kiểm tra data freshness, timeline sự kiện, người chịu trách nhiệm và hành động không gây gián đoạn ngoài dự kiến. Sau khi xử lý, hãy đo sự thay đổi của **resource metrics trước**, rồi xác minh **chi phí thực tế** khi dữ liệu xuất đủ. Cuối cùng, dùng post-incident review để cải thiện guardrails, quyền IAM, CI/CD, cost attribution và hệ thống cảnh báo, từ đó giảm cả số tiền thất thoát lẫn thời gian phát hiện sự cố tiếp theo.
