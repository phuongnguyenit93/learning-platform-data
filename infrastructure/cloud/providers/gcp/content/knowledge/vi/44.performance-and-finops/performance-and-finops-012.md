# Unit economics, showback và chargeback trên dữ liệu billing

Một công ty vận hành nhiều sản phẩm trên Google Cloud: API đặt hàng chạy Cloud Run, hệ thống phân tích dùng BigQuery, cơ sở dữ liệu trên Cloud SQL và các cụm GKE dùng chung. Hóa đơn Cloud Billing cho biết doanh nghiệp phải thanh toán bao nhiêu, nhưng chưa trả lời được ba câu hỏi quản trị quan trọng:

1. Một giao dịch thành công, một nghìn API request hoặc một khách hàng hoạt động đang tiêu tốn bao nhiêu chi phí cloud?
2. Mỗi đội, sản phẩm và cost center thực sự sử dụng bao nhiêu, kể cả phần hạ tầng chung và chiết khấu?
3. Các khoản đó chỉ cần **báo cáo minh bạch** hay phải **phân bổ thành chi phí nội bộ** cho từng bộ phận?

**Unit economics** đo chi phí trên một đơn vị giá trị nghiệp vụ. **Showback** cung cấp báo cáo chi phí cho nhóm sử dụng mà không chuyển ngân sách giữa các đơn vị. **Chargeback** phân bổ hoặc ghi nhận chi phí thực sự vào ngân sách, sổ quản trị hoặc hệ thống tài chính nội bộ theo quy tắc đã duyệt. Cả ba đều cần dữ liệu cloud billing được chuẩn hóa, thông tin sở hữu tài nguyên, đơn vị đo nghiệp vụ và quy trình đối soát.

Trong module **CLOUD_PROVIDERS_GCP**, Cloud Billing export sang BigQuery là điểm kết nối giữa quản trị project/IAM, nhãn tài nguyên, GKE, Cloud Run, BigQuery, Cloud Monitoring và FinOps. Bài học này tập trung vào thiết kế một mô hình chi phí đáng tin cậy, xây truy vấn SQL tái sử dụng được, xử lý phần chưa phân bổ và dùng unit cost để ra quyết định thay vì chỉ cắt giảm hóa đơn.

Sau bài học, bạn có thể:

- Phân biệt unit economics, cost allocation, showback và chargeback.
- Bật và lựa chọn Cloud Billing export chuẩn, chi tiết và pricing/FOCUS phù hợp.
- Hiểu `cost`, `credits`, `cost_at_list`, `cost_type`, `invoice.month` và thời gian sử dụng.
- Dùng project, label, tag, tài nguyên và mapping ownership để phân bổ chi phí.
- Xây BigQuery view chuẩn hóa, đối chiếu hóa đơn và tránh nhân đôi dòng phí khi `UNNEST`.
- Phân bổ shared cost theo driver minh bạch và bảo toàn tổng chi phí.
- Tính cost per request, transaction, customer hoặc data unit với mẫu số đúng.
- Xây dashboard showback và quy trình chargeback có kiểm soát.
- Quản lý CUD, promotions, thuế, điều chỉnh, dữ liệu đến muộn, quyền truy cập và chất lượng dữ liệu.

## 1. Ba khái niệm và mục đích sử dụng

### Unit economics

Unit economics trả lời: **“Để tạo ra một đơn vị kết quả nghiệp vụ, chúng ta cần bao nhiêu chi phí?”**

Ví dụ:

- Chi phí cloud trên 1.000 request API thành công.
- Chi phí hạ tầng cho một đơn hàng hoàn tất.
- Chi phí BigQuery trên một báo cáo được sử dụng.
- Chi phí lưu trữ và xử lý trên mỗi GiB dữ liệu khách hàng.
- Chi phí inference trên một câu trả lời AI được chấp nhận.

Một công thức cơ bản:

\[
Unit\ Cost = \frac{Attributed\ Cloud\ Cost}{Completed\ Business\ Units}
\]

Với API, có thể dùng `Cost per 1,000 successful requests = Cost / Successful requests * 1,000`. Mẫu số phải là đơn vị có giá trị được định nghĩa rõ, không mặc định dùng số CPU-second hay số request HTTP ở load balancer nếu nghiệp vụ cần số giao dịch thành công.

### Showback

Showback hiển thị ai đã tiêu thụ tài nguyên và mức chi phí ước tính hoặc đã ghi nhận. Không có bút toán nội bộ bắt buộc. Mục tiêu là tạo trách nhiệm, minh bạch và động lực tối ưu.

Ví dụ dashboard hàng tháng báo: đội Payments sử dụng 12.000 đơn vị tiền tệ trên môi trường production, trong đó 7.000 là chi phí trực tiếp và 5.000 là phần hạ tầng chung được phân bổ theo driver đã công bố.

### Chargeback

Chargeback sử dụng cùng dữ liệu và quy tắc phân bổ, nhưng còn ghi nhận khoản phí vào cost center, ngân sách, intercompany account hoặc sổ kế toán quản trị. Vì có ảnh hưởng tài chính thực, chargeback cần:

- Quy tắc tính và ngày hiệu lực được phê duyệt.
- Owner của từng khoản và cách xử lý `unallocated`.
- Đối soát tổng chi phí với dữ liệu nguồn.
- Quy trình chốt kỳ, tranh chấp, điều chỉnh và audit.
- Phân biệt rõ báo cáo nội bộ với hóa đơn thực do nhà cung cấp phát hành.

Chargeback **không có nghĩa Google Cloud tự phát hành hóa đơn riêng cho từng team**. Đây là cơ chế kế toán hoặc phân bổ nội bộ của doanh nghiệp.

| Thuộc tính | Unit economics | Showback | Chargeback |
|---|---|---|---|
| Câu hỏi chính | Một unit tốn bao nhiêu? | Nhóm nào đang tiêu bao nhiêu? | Nhóm nào chịu chi phí bao nhiêu? |
| Đầu vào | Chi phí đã phân bổ + business volume | Chi phí cloud + ownership | Cost ledger + allocation policy + approval |
| Kết quả | KPI hiệu quả | Dashboard hoặc báo cáo | Bút toán/phân bổ nội bộ |
| Tác động ngân sách | Gián tiếp | Chủ yếu tạo minh bạch | Trực tiếp |
| Mức yêu cầu kiểm soát | Cần định nghĩa metric | Cần kiểm chứng allocation | Cần đối soát, khóa kỳ và audit |

## 2. Kiến trúc dữ liệu FinOps trên Google Cloud

Một hệ thống báo cáo chi phí nên tách dữ liệu billing gốc khỏi các quy tắc phân bổ nội bộ và KPI nghiệp vụ. Không sửa dữ liệu export nguồn để “khớp ngân sách”.

~~~mermaid
flowchart LR
    A[Cloud Billing account] --> B[BigQuery billing export]
    B --> C[Canonical billing view]
    D[Project / labels / tags / resource inventory] --> E[Ownership mapping]
    C --> F[Allocation engine]
    E --> F
    G[Business metrics: requests / orders / users] --> H[Unit economics mart]
    F --> H
    F --> I[Showback dashboard]
    F --> J[Approved chargeback ledger]
    H --> K[Product / Finance / Engineering]
    I --> K
    J --> L[Finance / ERP / GL]
    M[Controls: reconciliation / quality / audit] --> F
    M --> J
~~~

Có thể tổ chức các lớp dữ liệu:

1. **Raw export:** bảng do Cloud Billing ghi vào BigQuery; chỉ đọc và không làm biến đổi.
2. **Canonical layer:** view có cùng schema ổn định, tính gross/net, phân biệt tháng invoice và usage.
3. **Ownership layer:** mapping project, tag, label, team, product, cost center có ngày hiệu lực.
4. **Allocation ledger:** mỗi khoản được gán trực tiếp hoặc chia theo một rule; tổng vẫn bảo toàn.
5. **Business metrics:** đơn hàng, request thành công, user hoặc job từ hệ thống vận hành.
6. **Unit economics + reporting:** mart và dashboard theo product/team/period.
7. **Chargeback journal:** phiên bản đã chốt, được kiểm toán và Finance phê duyệt.

Tách lớp giúp sửa quy tắc phân bổ mà không làm mất dấu dữ liệu Cloud Billing gốc. Khi Finance hỏi “vì sao team A tăng 12%?”, có thể lần ngược từ dashboard tới rule, line items và invoice.

## 3. Chọn và cấu hình Cloud Billing export

Cloud Billing hỗ trợ xuất dữ liệu vào BigQuery theo các loại khác nhau. Cấu hình export thực hiện tại Billing account trong Google Cloud Console, không phải từ một bảng BigQuery do người dùng tự ghi.

| Loại export | Bảng điển hình | Dùng cho |
|---|---|---|
| Standard usage cost | `gcp_billing_export_v1_<ACCOUNT_ID>` | Phân tích cost theo project, SKU, service, region, label, tag |
| Detailed usage cost | `gcp_billing_export_resource_v1_<ACCOUNT_ID>` | Phân bổ tới tài nguyên khi dịch vụ cung cấp thông tin đó |
| Pricing data | `cloud_pricing_export` | Tham chiếu giá SKU và mô hình định giá, phân tích biến động |
| FOCUS usage cost | Dataset/bảng riêng do Google cung cấp, hiện có giới hạn theo launch stage | Chuẩn hóa theo FinOps Open Cost and Usage Specification |
| CUD metadata | Export bổ sung về commitment, tùy tính khả dụng | Phân tích commitment và phân bổ lợi ích CUD |

**Không UNION ALL bản standard và detailed của cùng billing account** để tính tổng, vì detailed đã bao gồm những trường có trong standard. Làm vậy sẽ nhân đôi chi phí. Chọn một nguồn chính, thường là detailed export nếu cần resource attribution.

### Bật export qua Console

1. Chọn Billing account đang thanh toán cho các project.
2. Tạo hoặc chọn project dữ liệu FinOps có BigQuery dataset phù hợp.
3. Vào **Billing → Billing export → BigQuery export**.
4. Bật standard hoặc detailed usage export theo nhu cầu; có thể bật pricing export riêng.
5. Kiểm tra billing account có quyền ghi vào dataset và quyền người đọc báo cáo.
6. Chờ dữ liệu bắt đầu xuất; kiểm tra bảng, cột, thời điểm dữ liệu mới nhất và số tiền.

Nếu tổ chức có nhiều billing accounts, cần thu thập đúng từng account và bảo đảm không đếm cùng một dòng phí hai lần. Không giả định tất cả dự án nằm trong một billing account.

### Độ trễ và phạm vi lịch sử

Billing export không phải dòng sự kiện real-time. Khi mới bật export, dữ liệu có thể mất nhiều giờ để xuất hiện; việc nạp dữ liệu hồi tố theo cấu hình và location có thể mất nhiều ngày. Phạm vi backfill phụ thuộc loại export, vị trí dataset và thời điểm bật; **không được giả định dữ liệu từ trước khi bật luôn có đầy đủ**.

Các bảng có thể được Google cập nhật schema theo thời gian. Để dashboard không vỡ khi thêm cột mới, dùng canonical views với tập cột được kiểm soát, có kiểm thử schema và kế hoạch migration khi trường thay đổi.

## 4. Hiểu đúng các trường Cloud Billing

| Trường trong standard/detailed export | Ý nghĩa và lưu ý |
|---|---|
| `billing_account_id` | Billing account của dòng phí; khóa đối soát khi có nhiều account |
| `invoice.month` | Kỳ hóa đơn dạng YYYYMM; có thể khác tháng phát sinh usage |
| `usage_start_time`, `usage_end_time` | Khoảng phát sinh sử dụng; dùng cho phân tích vận hành và unit economics |
| `project.id`, `project.name` | Project phát sinh phí; một số dòng có thể không có project |
| `service.id`, `sku.id` | Định danh dịch vụ/SKU; ưu tiên ID cho mapping, description để hiển thị |
| `cost` | Chi phí theo mô hình tiêu thụ và giá hợp đồng áp dụng, **chưa cộng các credits trong mảng** |
| `cost_at_list` | Chi phí ở giá list theo default consumption model, có trong dữ liệu theo thời điểm hỗ trợ |
| `credits` | Mảng các khoản credit/discount gắn với dòng phí; `credits.amount` thường là số âm |
| `cost_type` | `regular`, `tax`, `adjustment` hoặc `rounding_error` |
| `currency` | Đồng tiền hóa đơn; không được SUM USD và VND như một đơn vị |
| `usage.amount`, `usage.unit` | Lượng dùng theo đơn vị gốc của SKU |
| `usage.amount_in_pricing_units` | Lượng dùng theo đơn vị định giá; không phải business units |
| `labels` | Resource labels dạng lặp key/value; không đầy đủ cho mọi dịch vụ/SKU |
| `project.labels` | Labels gắn project; có thể dùng fallback ownership |
| `tags` | Resource manager tags dạng lặp; gồm key, value, namespace và inherited |
| `resource.name` | Tên tài nguyên trong detailed export khi dịch vụ hỗ trợ |
| `export_time` | Mốc xuất dữ liệu, hữu ích cho kiểm tra freshness và late adjustments |

### Ba góc nhìn chi phí không được trộn lẫn

- **List cost:** giá niêm yết trước điều kiện thương mại, thường tham chiếu `cost_at_list` nếu trường hiện diện và phù hợp kỳ.
- **Cost before credits:** tổng `cost` ở giá áp dụng cho billing account, có thể đã gồm negotiated pricing.
- **Cost after credits:** tổng `cost` cộng các `credits.amount`; dùng làm cơ sở phân tích net cost theo chính sách.

Không gọi `SUM(cost)` là “giá list” khi billing account có negotiated pricing. Không lấy `cost - credits` nếu credits.amount đã âm: ví dụ cost 100 và credits -20 thì net là **80**, không phải 120.

### Credits không đồng nghĩa tiết kiệm vận hành

Các credits có thể bao gồm Free Tier, sustained use, committed use, spend-based discount, promotion hoặc các loại credit khác. Nếu một team được hưởng khoản promotion một lần, unit cost net có thể giảm dù hệ thống không hiệu quả hơn. Nên báo **gross, discount, promotion và net** riêng khi đánh giá xu hướng unit economics.

Phí commitment, credits do commitment và chính sách chia sẻ CUD có thể nằm ở project/SKU khác với workload sử dụng. Chargeback cần quyết định rõ có phân bổ phí và credit đó theo usage hưởng lợi, theo ngân sách commitment hay giữ ở FinOps central pool.

## 5. Hai loại tháng: usage month và invoice month

**Usage month** dựa trên thời điểm sử dụng theo timezone báo cáo. **Invoice month** dựa trên `invoice.month` của dòng Cloud Billing.

Giả sử một request chạy ngày 31/10 nhưng dòng phí được ghi nhận trong hóa đơn tháng 11. Khi đo cost per request tháng 10, khoản đó có thể thuộc usage October; khi đối soát hóa đơn phải nằm trong invoice November. Nếu chỉ nhìn một tháng mà không phân biệt, hai báo cáo có thể “không khớp” dù cả hai đúng theo định nghĩa.

| Mục đích | Trục thời gian | Vì sao |
|---|---|---|
| Unit cost của sản phẩm | Usage period, cùng timezone với business KPI | Ghép được chi phí với số giao dịch tạo ra |
| Báo cáo hóa đơn thực trả | `invoice.month` | Đối chiếu theo kỳ vendor billing |
| Chargeback theo hóa đơn | Invoice month và policy kỳ kế toán | Phù hợp chốt sổ nội bộ |
| Tối ưu theo ngày | `usage_start_time` | Nhận diện thay đổi workload gần thời điểm xảy ra |
| Phân tích correction | Cả usage và invoice month | Phát hiện phí đến muộn hoặc điều chỉnh hồi tố |

Đối với usage-based analytics, định nghĩa timezone rõ ràng; với report tháng tài chính, dùng kỳ theo Finance. Không tự lấy `invoice.month` làm định nghĩa cho “chi phí của request phát sinh trong tháng”.

## 6. Chuẩn hóa billing data trong BigQuery

Giả sử bạn đã bật **detailed usage cost export** vào bảng:

~~~text
finops-billing-prod.billing_raw.gcp_billing_export_resource_v1_XXXXXX_XXXXXX_XXXXXX
~~~

Tên trên là ví dụ. Thay bằng project, dataset và bảng thực tế của tổ chức. Trước khi tạo view, bảo đảm dataset `finops_mart` đã tồn tại và người thực hiện có quyền tạo view.

### Tạo canonical view không nhân đôi credits và labels

~~~sql
CREATE OR REPLACE VIEW
  `finops-billing-prod.finops_mart.v_billing_canonical` AS
SELECT
  billing_account_id,
  invoice.month AS invoice_month,
  FORMAT_DATE('%Y%m', DATE(usage_start_time, 'Asia/Ho_Chi_Minh'))
    AS usage_month,
  DATE(usage_start_time, 'Asia/Ho_Chi_Minh') AS usage_date,
  usage_start_time,
  export_time,
  project.id AS project_id,
  project.name AS project_name,
  service.id AS service_id,
  service.description AS service_name,
  sku.id AS sku_id,
  sku.description AS sku_name,
  cost_type,
  currency,
  CAST(cost AS NUMERIC) AS cost_before_credits,
  COALESCE((
    SELECT SUM(CAST(c.amount AS NUMERIC))
    FROM UNNEST(credits) AS c
  ), NUMERIC '0') AS credit_amount,
  CAST(cost AS NUMERIC) + COALESCE((
    SELECT SUM(CAST(c.amount AS NUMERIC))
    FROM UNNEST(credits) AS c
  ), NUMERIC '0') AS net_cost,
  COALESCE((
    SELECT ANY_VALUE(t.value)
    FROM UNNEST(tags) AS t
    WHERE t.key = 'cost_center'
      AND t.namespace = 'YOUR_TAG_NAMESPACE'
  ), (
    SELECT ANY_VALUE(l.value)
    FROM UNNEST(labels) AS l
    WHERE l.key = 'cost_center'
  ), (
    SELECT ANY_VALUE(pl.value)
    FROM UNNEST(project.labels) AS pl
    WHERE pl.key = 'cost_center'
  ), 'unallocated') AS owner_key
FROM
  `finops-billing-prod.billing_raw.gcp_billing_export_resource_v1_XXXXXX_XXXXXX_XXXXXX`;
~~~

**Giải thích:**

1. `CAST(cost AS NUMERIC)` và `credits` được tính riêng theo từng dòng; mảng `credits` dùng subquery để không nhân bản dòng phí.
2. `tags`, `labels` và `project.labels` cũng dùng scalar subqueries thay vì `CROSS JOIN UNNEST` nhiều mảng cùng lúc.
3. Ưu tiên owner theo tag `cost_center` có namespace xác định, rồi resource label, project label và cuối cùng `unallocated`. Thứ tự này là **quy tắc nội bộ minh họa**, không phải quy tắc tự động của Google.
4. `usage_month` dùng múi giờ đã thống nhất; `invoice_month` giữ nguyên trường hóa đơn.
5. View không phân bổ shared cost; nó chỉ tạo dữ liệu nền phục vụ bước phân bổ tiếp theo.

`ANY_VALUE` giúp lấy một giá trị cho key, nhưng nếu nguồn có nhiều giá trị mâu thuẫn cùng key, nó không bảo đảm lựa chọn có ý nghĩa kinh doanh. Cần có data quality check và policy rõ ràng cho metadata không hợp lệ. Thay `YOUR_TAG_NAMESPACE` bằng namespace được tổ chức quản trị; không nên dựa chỉ vào tag key nếu nhiều organization/namespace có tên trùng.

Đối với đối soát tài chính yêu cầu độ chính xác rất cao, nên dùng phương pháp cộng giá trị ở mức micros hoặc quy tắc làm tròn đã được Finance phê duyệt, vì trường `cost` và `credits.amount` có thể được export dưới dạng floating point. Các ví dụ dùng NUMERIC nhằm đơn giản hóa; cần xác minh mức làm tròn với invoice thật.

### Cảnh báo khi UNNEST nhiều repeated fields

Một dòng phí có 2 resource labels, 3 tags và 2 credits. Truy vấn:

~~~sql
SELECT *
FROM `...` AS b,
UNNEST(b.labels) AS l,
UNNEST(b.tags) AS t,
UNNEST(b.credits) AS c;
~~~

có thể tạo 2 × 3 × 2 = **12 dòng** từ một dòng export. Nếu sau đó SUM(cost), chi phí bị nhân 12 lần. Truy vấn này chỉ minh họa **anti-pattern**, không dùng trong báo cáo.

An toàn hơn là lấy đúng một giá trị metadata bằng correlated subquery và tổng credits trong subquery trên chính dòng gốc, như canonical view ở trên. Nếu phải phân tích nhiều labels, hãy làm báo cáo riêng theo key hoặc xây bảng trung gian với allocation weight có tổng đúng bằng 1.

## 7. Truy vấn đối soát hóa đơn

Đối soát trước khi tạo showback hoặc chargeback. Không nên phân bổ từ một dataset chưa xác định được tổng chi phí.

### Tổng cost/credit theo tháng hóa đơn

~~~sql
SELECT
  billing_account_id,
  invoice_month,
  currency,
  cost_type,
  ROUND(SUM(cost_before_credits), 2) AS cost_before_credits,
  ROUND(SUM(credit_amount), 2) AS credits,
  ROUND(SUM(net_cost), 2) AS net_cost
FROM `finops-billing-prod.finops_mart.v_billing_canonical`
WHERE invoice_month = '202610'
GROUP BY 1, 2, 3, 4
ORDER BY billing_account_id, invoice_month, currency, cost_type;
~~~

Đây là truy vấn theo tháng **hóa đơn**, gồm cả `regular`, `tax`, `adjustment` và `rounding_error` để không làm mất dòng cần cho đối soát. Tổng có thể cần quy trình làm tròn phù hợp và đối chiếu với invoice thực của Cloud Billing account.

### Phân tích theo usage month

~~~sql
SELECT
  usage_month,
  currency,
  service_name,
  ROUND(SUM(net_cost), 2) AS net_cost
FROM `finops-billing-prod.finops_mart.v_billing_canonical`
WHERE usage_month BETWEEN '202609' AND '202610'
  AND cost_type = 'regular'
GROUP BY 1, 2, 3
ORDER BY usage_month, net_cost DESC;
~~~

Truy vấn này phản ánh chi phí sử dụng theo thời điểm usage, không phải hóa đơn tháng. Khi Google Cloud phát hành correction cho usage cũ, số liệu quá khứ có thể thay đổi khi chạy lại view. Để chargeback ổn định, cần lưu snapshot cùng thời điểm chốt sổ và phiên bản điều chỉnh.

### Kiểm tra các dòng không có project

Không phải mọi phí đều gắn một `project.id`. Có phí support, adjustment hoặc credit được ghi nhận ngoài project. Nếu tự loại các dòng `project.id IS NULL`, tổng phân bổ sẽ thiếu so với invoice. Hãy đưa chúng vào một nhóm `central`, `shared` hoặc `unallocated` rồi xử lý theo policy.

## 8. Mô hình ownership: project, labels, tags và mapping

### Project-per-team hoặc project-per-product

Tách project rõ ràng giúp quy trách nhiệm dễ và giảm số dòng không phân bổ. Đây thường là nền tảng tốt:

- `payments-prod` thuộc Product Payments.
- `catalog-prod` thuộc Product Catalog.
- `shared-network-prod` là shared platform.
- `sandbox-research` thuộc nhóm nghiên cứu với budget riêng.

Nhưng một project dùng chung nhiều workload vẫn cần labels/tags hoặc driver để chia chi phí. Project ID không phải lúc nào cũng tương đương cost center.

### Labels

Đề xuất hệ thống labels chuẩn cho tài nguyên hỗ trợ:

| Key | Ví dụ | Ý nghĩa |
|---|---|---|
| `cost_center` | `cc-210` | Đơn vị chịu chi phí |
| `product` | `checkout` | Sản phẩm |
| `environment` | `prod` | Môi trường |
| `owner_team` | `payments` | Đội vận hành |
| `workload` | `checkout-api` | Thành phần ứng dụng |

Labels không tự retroactive về thời điểm trước khi được gắn. Chúng cũng không xuất hiện trên mọi SKU hoặc loại dịch vụ. Không đánh giá độ phủ labels chỉ bằng số lượng resource đã gắn label; hãy tính **tỷ lệ chi phí** thực sự có ownership phù hợp.

### Tags

Google Cloud Resource Manager tags có mô hình quyền và kế thừa theo hierarchy, phù hợp với cost center do tổ chức quản trị. Trong billing export, `tags` chứa key, value, namespace và thông tin inherited khi được hỗ trợ. Tags có độ trễ truyền vào export và coverage theo loại resource; chúng không phải cơ chế tự động áp dụng hoàn hảo cho mọi phí.

### Mapping table có ngày hiệu lực

Khi một project đổi owner giữa tháng, không nên sửa thông tin chủ sở hữu của các kỳ đã chốt. Dùng bảng mapping có hiệu lực theo thời gian:

| project_id | owner_key | product | valid_from | valid_to |
|---|---|---|---|---|
| `payments-prod` | `cc-210` | `checkout` | 2026-01-01 | 2026-11-01 |
| `payments-prod` | `cc-220` | `checkout` | 2026-11-01 | null |
| `shared-platform-prod` | `shared` | `platform` | 2026-01-01 | null |

Sử dụng khoảng nửa mở `valid_from <= usage_date < valid_to` để không có ngày giao thoa. Bảng mapping phải có unique/conflict checks, owner duyệt và version/rule ID.

### Thứ tự attribution khuyến nghị

1. Quy tắc tài nguyên/tenant trực tiếp có chứng cứ (resource ID, workload label).
2. Tag cost center được governance phê duyệt.
3. Resource/project labels đáng tin cậy.
4. Project ownership mapping có ngày hiệu lực.
5. Shared pool theo service hoặc SKU.
6. `unallocated` có owner điều tra; **không được âm thầm bỏ khỏi báo cáo**.

Thứ tự cụ thể do tổ chức quyết định và phải được ghi tài liệu. Nếu một project label và tag mâu thuẫn, cần cảnh báo và xác minh, không lựa chọn ngẫu nhiên rồi chargeback.

## 9. GKE, tài nguyên chung và giới hạn phân bổ

Trong GKE, một cluster có thể phục vụ nhiều namespace và nhóm. Detailed billing export không mặc định chia chính xác chi phí mỗi pod trên mọi SKU. Cần bật **GKE cost allocation** nếu muốn dùng các labels như:

- `goog-k8s-cluster-name` cho cluster.
- `k8s-namespace` cho namespace.
- `k8s-label/<key>` cho Kubernetes labels được hỗ trợ.

Sau khi bật cost allocation, dữ liệu có thể cần thời gian mới xuất hiện; việc gắn nhãn cho pod/namespace không khiến lịch sử phát sinh trước đó được chia lại đầy đủ. Một số loại tài nguyên và mô hình vận hành có giới hạn được Google Cloud công bố.

Tránh coi namespace là cost center duy nhất nếu một namespace phục vụ nhiều product. Có thể dùng label `team`, `product`, tỷ lệ requested resources hoặc metric tiêu thụ thực tế theo workload, nhưng phải chốt driver và phân tích tác động trước khi dùng làm chargeback.

### Shared cost không chỉ có GKE

Các khoản thường cần phân bổ:

- Shared VPC, NAT, load balancer, egress và CDN.
- GKE control plane/node pools dùng chung.
- Centralized logging, monitoring, security scanning.
- BigQuery reservation dùng chung nhiều team.
- Artifact Registry, CI/CD platform và secrets platform.
- Support plan, phí license hoặc cam kết mua chung.

Nếu dịch vụ không cung cấp tín hiệu quy trách nhiệm đáng tin, phân bổ theo một driver minh bạch hoặc giữ ở central pool. Không tự gán 100% chi phí cho team tạo tài nguyên nếu các team khác cùng hưởng lợi.

## 10. Phương pháp phân bổ direct, shared và unallocated

### Phân bổ trực tiếp

Direct cost gán cho một cost center khi có căn cứ đủ mạnh: project chuyên dụng, tag/label được phê duyệt, resource-to-workload mapping hoặc dữ liệu tiêu thụ của một team.

### Phân bổ chi phí chung

Shared cost cần một driver được chủ sở hữu hạ tầng, team sản phẩm và Finance thống nhất.

| Khoản chung | Driver khả thi | Điều kiện cần kiểm tra |
|---|---|---|
| GKE cluster shared | CPU/memory requested hoặc actual usage theo namespace | Resource limits, system overhead, idle capacity |
| Shared BigQuery reservation | Slot-ms theo job/team, reservation usage | Job labels, sự phù hợp với reservation assignment |
| Network egress shared | Bytes theo ứng dụng hoặc service flow | Dữ liệu egress đo đủ và không đếm trùng |
| Central logging | Ingested GiB hoặc volume theo service | Log routing và dữ liệu tổng hợp |
| Central security | Số resource, mức rủi ro hoặc % direct spend | Có cơ sở công bằng, phê duyệt |
| Support plan | Tỷ lệ spend hoặc thỏa thuận fixed budget | Cách xử lý khoản không đo theo resource |

Không có một driver “công bằng tuyệt đối”. Quan trọng là **đơn giản, có kiểm chứng, ổn định và tương xứng với khả năng kiểm soát chi phí của team**.

### Công thức có trọng số

Với pool chi phí chung `S` và driver `w_i` của team i:

\[
AllocatedSharedCost_i = S \times \frac{w_i}{\sum_{j=1}^{n}w_j}
\]

Khi tổng driver bằng 0, không được chia cho 0 hoặc tạo khoản chargeback mất dấu. Dùng fallback do policy quy định (ví dụ giữ ở `unallocated-shared`) và mở điều tra.

### Ví dụ hai sản phẩm

Trong một tháng, bỏ qua thuế/adjustment để tập trung vào vận hành:

| Khoản | Payments | Catalog |
|---|---:|---:|
| Direct net cost | 1.800 USD | 1.200 USD |
| Tỷ trọng direct | 60% | 40% |
| Shared pool cần phân bổ | Tổng pool: 600 USD | Phân bổ theo 60% / 40% |
| Shared cost được phân bổ | 360 USD | 240 USD |
| **Total allocated** | **2.160 USD** | **1.440 USD** |

Tổng sau phân bổ là `2.160 + 1.440 = 3.600 USD`, đúng bằng `1.800 + 1.200 + 600`. Không được vừa giữ 600 USD ở shared center vừa cộng 600 USD phân bổ vào hai team trong cùng báo cáo tổng; đó là double counting.

Đây là ví dụ minh họa, chưa tính CUD allocation, tax và adjustment. Với chargeback thật, mỗi loại cost có thể có policy riêng.

## 11. Mẫu SQL phân bổ shared pool

Giả sử canonical view có cột `owner_key`; hai team `payments` và `catalog` đã nhận direct costs, trong khi các khoản shared được gắn `shared-platform`. Ví dụ dưới đây phân bổ shared pool theo tỷ lệ direct **net regular cost dương**.

~~~sql
WITH monthly AS (
  SELECT
    owner_key,
    SUM(net_cost) AS net_regular_cost
  FROM `finops-billing-prod.finops_mart.v_billing_canonical`
  WHERE invoice_month = '202610'
    AND currency = 'USD'
    AND cost_type = 'regular'
  GROUP BY 1
),
direct AS (
  SELECT
    owner_key,
    net_regular_cost AS direct_cost,
    GREATEST(net_regular_cost, NUMERIC '0') AS driver
  FROM monthly
  WHERE owner_key IN ('payments', 'catalog')
),
weights AS (
  SELECT
    owner_key,
    direct_cost,
    SAFE_DIVIDE(driver, SUM(driver) OVER ()) AS allocation_weight
  FROM direct
),
shared AS (
  SELECT COALESCE(SUM(net_regular_cost), NUMERIC '0') AS shared_cost
  FROM monthly
  WHERE owner_key = 'shared-platform'
)
SELECT
  w.owner_key,
  ROUND(w.direct_cost, 2) AS direct_cost,
  ROUND(s.shared_cost * w.allocation_weight, 2) AS allocated_shared_cost,
  ROUND(w.direct_cost + s.shared_cost * w.allocation_weight, 2)
    AS total_allocated_cost
FROM weights AS w
CROSS JOIN shared AS s
ORDER BY w.owner_key;
~~~

Đây là mô hình didactic. Trong thực tế phải:

- Có danh sách owner chính thức, không hard-code chỉ hai owner nếu đang chargeback toàn doanh nghiệp.
- Đưa `unallocated` và các owner khác vào bảng đối soát, không làm mất phí.
- Chọn driver phản ánh tiêu thụ hơn khi có metric đo được.
- Tách commitment fees, taxes và adjustments theo policy riêng.
- Xử lý tổng driver bằng 0; `SAFE_DIVIDE` trả NULL và không nên ghi sổ khoản chưa phân bổ.
- Phân bổ phần cent lẻ bằng quy tắc deterministic để tổng sau ROUND vẫn khớp tổng pool.
- Kiểm tra dấu chi phí và điều chỉnh âm trước khi dùng tỷ lệ.

Một **allocation ledger** production nên có cột `source_line_id/rule_id/period/owner/weight/allocated_amount/allocation_version`, và ràng buộc tổng weight cho từng dòng đủ điều kiện bằng 1. Nếu billing export không có khóa dòng tự nhiên duy nhất, hãy tạo surrogate key từ các trường ổn định cộng ingestion identifier theo thiết kế dedup đã kiểm thử; không giả định một hash của `project+sku+date` là duy nhất.

## 12. Tính unit economics bằng dữ liệu nghiệp vụ

Billing export chỉ cung cấp lượng sử dụng cloud như GiB-month, vCPU-hour, requests của SKU hoặc query bytes. **Business unit** thường nằm trong hệ thống khác:

- Số order thanh toán thành công trong ứng dụng.
- Số API requests thành công ở load balancer/Cloud Monitoring.
- Số active customers theo định nghĩa sản phẩm.
- Số phiên xử lý AI được chấp nhận.
- Số data pipelines hoàn tất đúng hạn.

### Một mẫu số tốt phải thỏa các điều kiện

1. Có định nghĩa nghiệp vụ thống nhất và không thay đổi âm thầm.
2. Không đếm lặp retry hoặc cùng một đơn hàng ở nhiều bước.
3. Cùng time zone và kỳ đo với phần cost được dùng.
4. Được phân ranh giới theo đúng product/tenant/region nếu chi phí cũng chia như vậy.
5. Có khả năng kiểm tra chất lượng và truy nguyên về event nguồn.

### Ví dụ chi phí trên 1.000 request

Với số liệu ở phần trên:

- Payments: 2.160 USD, 1.200.000 request thành công ⇒ `2.160 / 1.200.000 × 1.000 = 1,80 USD` mỗi 1.000 request.
- Catalog: 1.440 USD, 600.000 request thành công ⇒ `1.440 / 600.000 × 1.000 = 2,40 USD` mỗi 1.000 request.

Payments có tổng cloud cost lớn hơn nhưng **unit cost thấp hơn**. Vì vậy chỉ so sánh tổng hóa đơn có thể dẫn tới quyết định sai. Tuy nhiên, cần xem chất lượng workload, loại request và SLO trước khi nói Payments hiệu quả hơn Catalog.

### Ghép allocation mart với business metrics

Giả sử có hai bảng nội bộ đã chuẩn hóa:

- `finops_mart.monthly_allocated_cost`: `usage_month`, `product`, `currency`, `allocated_cost`.
- `product_metrics.monthly_success`: `usage_month`, `product`, `successful_requests`.

~~~sql
WITH c AS (
  SELECT
    usage_month,
    product,
    currency,
    SUM(allocated_cost) AS cloud_cost
  FROM `finops-billing-prod.finops_mart.monthly_allocated_cost`
  WHERE usage_month = '202610'
  GROUP BY 1, 2, 3
),
m AS (
  SELECT
    usage_month,
    product,
    SUM(successful_requests) AS requests
  FROM `finops-billing-prod.product_metrics.monthly_success`
  WHERE usage_month = '202610'
  GROUP BY 1, 2
)
SELECT
  c.usage_month,
  c.product,
  c.currency,
  c.cloud_cost,
  m.requests,
  ROUND(SAFE_DIVIDE(c.cloud_cost * 1000, m.requests), 4)
    AS cost_per_1000_successful_requests
FROM c
LEFT JOIN m
  ON c.usage_month = m.usage_month
 AND c.product = m.product;
~~~

Các bảng mart trong ví dụ phải được doanh nghiệp tạo theo schema mô tả; chúng **không tự có** chỉ vì đã bật Billing export.

Quan trọng: **aggregate cost và business metric đến cùng grain trước khi JOIN**. Nếu JOIN từng dòng billing với từng request, mỗi dòng cost có thể nhân với nhiều event và tạo tổng sai. Khi `requests` bằng 0, `SAFE_DIVIDE` trả NULL, cần hiển thị là “không có mẫu số hợp lệ”, không ép thành 0 USD/unit.

### Average vs marginal unit cost

Unit cost bình quân gồm cả chi phí cố định và shared cost. **Marginal cost** là chi phí tăng thêm khi xử lý một đơn vị workload bổ sung. Hai con số này khác nhau khi có autoscaling, CUD, idle capacity hoặc phí license cố định.

Khi quyết định capacity, nên phân tích cả fixed/variable cost và throughput. Một giảm giá promotion làm net unit cost thấp hơn nhưng không chứng minh capacity hiệu quả hơn.

## 13. Phân biệt showback và chargeback trên dashboard

### Dashboard showback

Một dashboard phục vụ product/engineering nên có:

- Tổng cost trước credits và sau credits theo kỳ.
- Cost theo project, product, owner/team, môi trường, service và SKU.
- Direct, shared, centrally retained và unallocated.
- Phần trăm cost có attribution hợp lệ.
- Biến động theo kỳ và nguyên nhân: workload growth, unit price, discounts, architecture.
- Unit cost và mẫu số nghiệp vụ tương ứng.
- Danh sách mục cần xử lý: unlabeled resources, idle spend, anomaly, forecast.

Showback nên hiển thị **công thức và rule phân bổ**. Nếu một team không thể hiểu vì sao phải chịu 500 USD phí NAT chung, họ sẽ khó hành động tối ưu.

### Chargeback statement

Chargeback cần thêm:

| Trường | Mục đích |
|---|---|
| Accounting period | Kỳ hạch toán nội bộ |
| Billing account / currency | Dữ liệu đầu vào đối soát |
| Cost center và owner | Đối tượng chịu chi phí |
| Allocation policy/version | Quy tắc có hiệu lực |
| Direct cost | Chi phí quy trách nhiệm trực tiếp |
| Shared cost allocated | Phần chi phí chung được chia |
| Discounts/credits allocated | Khoản giảm trừ theo policy |
| Tax/adjustment policy | Xử lý dòng không gắn usage thường |
| Total chargeback | Tổng cần ghi nhận |
| Approval và status | Draft, reviewed, approved, posted, adjusted |
| Trace ID | Liên kết tới source rows, allocation ledger và run |

Chargeback không nên thực hiện bằng cách cho mỗi team toàn quyền truy cập billing export có thể tiết lộ giá hợp đồng hoặc dữ liệu dự án khác. Dùng authorized views, policy tags, row-level security hoặc mart có phân quyền theo owner; Finance giữ quyền xem toàn bộ.

## 14. Quy trình chốt kỳ và đối soát

Không nên ghi bút toán từ dashboard đang thay đổi theo giờ. Một quy trình đề xuất:

1. **Ingest:** kiểm tra dữ liệu export tới thời điểm chốt đã đủ.
2. **Normalize:** áp canonical schema, timezone và policy cho credits.
3. **Assign:** map ownership trực tiếp; giữ bucket `unallocated`.
4. **Allocate:** chia các shared pools theo driver có hiệu lực.
5. **Reconcile:** so sánh tổng trước/sau phân bổ với nguồn và invoice.
6. **Quality gate:** kiểm tra tỷ lệ unallocated, label conflicts, null currency, missing metrics.
7. **Review:** gửi showback draft cho owners và Finance.
8. **Dispute window:** cho phép owner phản hồi, ghi lý do và bằng chứng.
9. **Approve and freeze:** khóa bản tính theo version, đóng kỳ.
10. **Post chargeback:** xuất journal/ERP và lưu trace.
11. **Adjust later:** adjustment/correction tới sau được ghi bằng bút toán bổ sung hoặc restatement được phê duyệt.

### Phép đối soát bắt buộc

\[
\sum Direct + \sum Shared + \sum Unallocated + \sum Central
= \sum Source\ Net\ Costs
\]

Ở vế trái, `Shared` phải được hiểu là **phần đã gán sau phân bổ hoặc phần giữ lại**, không được tính cả shared pool gốc và phần đã phân bổ vào các team. Với phân bổ theo nhiều lớp, cần đối soát ở từng stage.

### Mức độ chính xác và chênh lệch

Các dòng Cloud Billing có thể có rounding errors, taxes, adjustments hoặc late-monetized usage. Hãy thống nhất:

- Nguồn sự thật của invoice total.
- Đơn vị tiền và quy tắc FX nếu có nhiều currency.
- Quy tắc ROUND và phần lẻ.
- Ngưỡng chênh lệch được phép và cách xử lý vượt ngưỡng.
- Chính sách không hồi tố hoặc restatement của kỳ đã chốt.

Không hợp nhất các khoản `tax`, `rounding_error` và `adjustment` vào `regular` mà không có ghi chú, vì unit cost kỹ thuật có thể bị bóp méo.

## 15. Kiểm soát chất lượng dữ liệu và đo attribution coverage

Một pipeline FinOps production cần chỉ số chất lượng độc lập:

| Kiểm tra | Ví dụ SLI |
|---|---|
| Freshness | Số giờ từ export_time mới nhất tới thời điểm kiểm tra |
| Attribution coverage | % net regular cost đã map tới owner hợp lệ |
| Unallocated spend | Số tiền còn ở unallocated và xu hướng |
| Mapping conflicts | Số dòng tag/label/project mapping mâu thuẫn |
| Reconciliation | Sai lệch tổng net cost trước/sau allocation |
| Denominator quality | % product-month có business units hợp lệ |
| Audit completeness | % chargeback lines có rule ID và source trace |
| Timeliness | % kỳ được chốt trước hạn kế toán |

Ví dụ đo phần phí chưa quy owner:

~~~sql
SELECT
  invoice_month,
  currency,
  ROUND(SUM(net_cost), 2) AS total_regular_net_cost,
  ROUND(SUM(IF(owner_key = 'unallocated', net_cost, 0)), 2)
    AS unallocated_net_cost,
  ROUND(
    100 * SAFE_DIVIDE(
      SUM(IF(owner_key = 'unallocated', ABS(net_cost), 0)),
      SUM(ABS(net_cost))
    ), 2
  ) AS unallocated_share_of_absolute_cost_pct
FROM `finops-billing-prod.finops_mart.v_billing_canonical`
WHERE cost_type = 'regular'
  AND invoice_month = '202610'
GROUP BY 1, 2;
~~~

Metric phần trăm trong ví dụ dùng **absolute cost** để tránh tình huống credits âm làm mẫu số gần 0 hoặc đổi dấu. Đây là metric coverage vận hành, không phải tỷ lệ sử dụng ngân sách trong báo cáo tài chính.

Đừng chỉ cố đạt 100% coverage bằng cách gán mọi phí chưa rõ cho một team tùy ý. Tốt hơn là minh bạch unallocated và giảm nó bằng dữ liệu ownership tốt hơn.

## 16. CUD, Free Tier, promotion và lợi ích mua chung

Chiết khấu từ cam kết sử dụng có thể tạo biến động lớn trong chi phí và yêu cầu quy tắc allocation riêng:

- **CUD fees:** phí cam kết phải được giữ ở central finance, gán tới owner hợp đồng hoặc chia cho workloads theo lợi ích?
- **CUD credits:** credit nhận được có phản ánh mức sử dụng hưởng lợi hay bị ghi ở một nguồn khác?
- **Unused commitment:** ai chịu phần cam kết chưa sử dụng? Nên giữ ở cost owner mua cam kết hoặc pool chung?
- **Free Tier/promotion:** có được chuyển lợi ích miễn phí tới sản phẩm hay giữ ở báo cáo ngoài hiệu quả vận hành?
- **Negotiated pricing:** báo cáo list cost có nên hiện rõ cho team không; thông tin hợp đồng có giới hạn truy cập không?

Hãy chọn ít nhất hai KPI:

1. **Operational unit cost:** cố gắng tách biến động giá/credit một lần để đo hiệu quả kỹ thuật.
2. **Financial net unit cost:** chi phí sau các credits được policy phân bổ, phù hợp ngân sách.

CUD metadata export và Cloud Billing pricing export có thể hỗ trợ phân tích cơ chế chiết khấu, nhưng không tự quyết định ai là người hưởng lợi. Mô hình phân bổ vẫn cần chính sách FinOps.

## 17. Bảo mật, quyền truy cập và vận hành dữ liệu billing

Billing export có thể tiết lộ mức chi tiêu, giá hợp đồng, cấu trúc project, dịch vụ sử dụng và chiến lược mua cam kết. Đây là dữ liệu tài chính có độ nhạy cảm.

### IAM và truy cập

- Giới hạn quyền đọc raw billing dataset cho nhóm FinOps/Finance và service accounts chuyên dụng.
- Để product teams chỉ xem authorized views hoặc mart của chính họ.
- Dùng BigQuery row-level security, column-level controls và policy tags khi cần.
- Tách quyền tạo/mutate allocation rules khỏi quyền approve/posted chargeback.
- Bảo vệ workflow CI/CD, BigQuery scheduled queries và Dataform/dbt jobs nếu dùng.
- Ghi audit log cho thay đổi chính sách, mapping, SQL và dữ liệu export.

### Chi phí phân tích billing

BigQuery queries đọc nhiều tháng raw billing có thể tốn chi phí, nhất là với hàng tỷ dòng. Có thể:

- Giới hạn thời gian trong query.
- Dùng partitioning/clustering cho các bảng mart do tổ chức tạo.
- Materialize các bảng tổng hợp theo ngày/tháng.
- Dùng dry run và maximum bytes billed cho query lớn.
- Không liên tục JOIN raw billing với clickstream gốc.
- Lưu snapshot cho kỳ chargeback đã chốt.

Nếu export table có partitioning, cần kiểm tra partition column thực tế rồi dùng predicate phù hợp để giảm scan. Không tự thay đổi schema hoặc partitioning của bảng gốc do Google quản lý.

### Theo dõi vận hành

Cloud Monitoring và pipeline logs có thể cảnh báo khi export trễ, canonical view lỗi schema, số liệu bất thường, tỷ lệ unallocated tăng hoặc reconciliation fail. Một báo cáo FinOps có số liệu sai nhưng vẫn hiển thị dashboard là rủi ro vận hành đáng kể.

## 18. Quy trình thử nghiệm end-to-end

Giả sử doanh nghiệp vận hành ba nhóm: Payments, Catalog và Shared Platform. Tổ chức muốn mỗi tháng xuất report showback, sau hai tháng pilot mới chargeback.

### Giai đoạn A: nền tảng dữ liệu

1. Bật detailed usage cost export trên billing account.
2. Tạo canonical view với cách tính net cost và currency rõ ràng.
3. Định nghĩa tháng invoice và tháng usage; phân biệt trong dashboard.
4. Lập mapping project, tag và label cho ba cost centers.
5. Kiểm tra các dòng non-regular, credits và dự án không có owner.

### Giai đoạn B: showback pilot

6. Tính direct costs, giữ shared pool tách biệt.
7. Chọn driver cho shared network, logging và GKE cluster có tài liệu giải thích.
8. Đối soát direct + allocated + unallocated/central với nguồn.
9. Xây dashboard theo team, product, service, environment.
10. Đưa unit cost từ số lượng request/order có định nghĩa nghiệp vụ.
11. Mời product owners xem báo cáo và sửa metadata ownership còn thiếu.

### Giai đoạn C: chargeback có kiểm soát

12. Finance phê duyệt các policy: tax, CUD, promotion, shared, rounding.
13. Đặt kỳ chốt, dispute window, approval và versioning.
14. Tạo chargeback statement bất biến theo kỳ đã chốt.
15. Xuất journal vào hệ thống tài chính nếu tổ chức thực sự áp dụng chargeback.
16. Ghi lại correction late invoice vào adjustment cycle thay vì sửa âm thầm kỳ đã khóa.

### Giai đoạn D: cải tiến liên tục

17. Tìm nguyên nhân unit cost tăng: traffic mix, architecture, overprovisioning, giá SKU hoặc commitment.
18. Đề xuất tối ưu có dự báo savings và ảnh hưởng SLO.
19. Theo dõi trước/sau thay đổi với cùng định nghĩa mẫu số.
20. Rà soát độ công bằng của allocation driver sau mỗi quý.

## 19. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Tổng trên dashboard gấp đôi hóa đơn | UNION standard và detailed hoặc UNNEST nhiều mảng | Chỉ dùng một export gốc; correlated subqueries cho repeated fields |
| Sum cost khác số thực trả | Bỏ qua credits, tax, adjustment hoặc rounding | Đối soát theo invoice.month, currency, cost_type |
| Đơn giá cloud giảm đột ngột | Promotion, CUD credit hoặc negotiated price thay đổi | Tách before-credits, promotion, discounts và net |
| Unit cost tăng dù request không đổi | Shared allocation đổi, traffic mix hoặc cố định tăng | Kiểm tra rule version, denominator và cost decomposition |
| Một project không có owner | Thiếu tag/label hoặc mới tạo | Mapping fallback có ngày hiệu lực; đưa unallocated vào review |
| Labels mới không xuất hiện cho tháng cũ | Metadata không retroactive | Không tái phân bổ lịch sử tùy tiện; dùng rule có ngày hiệu lực |
| Chưa thấy chi phí GKE theo namespace | Chưa bật cost allocation hoặc chưa đủ thời gian | Bật GKE cost allocation, kiểm tra giới hạn SKU và độ trễ |
| Chi phí tháng sử dụng khác hóa đơn | Late-monetized usage, corrections hoặc timezone | Tách usage_month và invoice_month, chốt kỳ có adjustment policy |
| Chargeback có tổng khác nguồn vài cent | Rounding ở từng owner thay vì sau phân bổ | Quy tắc phân phối remainder deterministic, đối soát sau ROUND |
| Cost per unit bằng 0 hoặc NULL | Mẫu số thiếu/0, negative credit hoặc sai JOIN | Kiểm tra business metric, SAFE_DIVIDE, cohort và credit policy |
| Dashboard team thấy phí của team khác | Raw billing dataset cấp quá rộng | Dùng authorized views/RLS và kiểm thử phân quyền |
| SQL bị lỗi khi Google thêm field | Query `SELECT *`, schema drift | Canonical view có schema ổn định và contract tests |

## 20. Checklist trước khi công bố số liệu

- [ ] Billing accounts và kiểu export được xác định, không đếm trùng standard/detailed.
- [ ] Dữ liệu export có đủ kỳ; freshness và backfill được kiểm chứng.
- [ ] Canonical view phân biệt invoice month, usage month và currency.
- [ ] Gross/list, before-credits, credits, net được định nghĩa minh bạch.
- [ ] Không tạo double count khi xử lý repeated labels, tags, credits.
- [ ] Phân biệt `regular`, `tax`, `adjustment` và `rounding_error`.
- [ ] Có ownership mapping theo project/resource/tag/label với ngày hiệu lực.
- [ ] Shared cost có policy, driver, owner và cách xử lý tổng driver bằng 0.
- [ ] Có nhóm unallocated/central và kế hoạch giảm phí chưa quy trách nhiệm.
- [ ] Tổng sau phân bổ khớp tổng trước phân bổ theo từng account/currency/period.
- [ ] CUD, promotion, Free Tier, phí cam kết được xử lý theo policy.
- [ ] Business denominator được dedup, đúng grain, timezone và cùng period.
- [ ] Unit cost có định nghĩa và phân biệt operational vs financial view.
- [ ] Showback dashboard hiển thị direct/shared/allocated và có drill-down.
- [ ] Chargeback có approval, freeze, dispute, adjustment và traceability.
- [ ] Quyền raw billing hạn chế; mart có bảo mật theo cost center.
- [ ] Có kiểm tra schema drift, freshness, label coverage và reconciliation.
- [ ] Có ngân sách vận hành BigQuery và các cảnh báo chất lượng dữ liệu.

## 21. Kết luận

**Unit economics** giúp đo chi phí cloud theo kết quả nghiệp vụ; **showback** tạo minh bạch về người sử dụng và chi phí; **chargeback** biến allocation policy thành trách nhiệm tài chính nội bộ. Ba năng lực này chỉ hữu ích khi dữ liệu billing được chuẩn hóa và đối soát, ownership đáng tin cậy, shared costs được phân bổ công bằng và mẫu số nghiệp vụ đúng.

Trên Google Cloud, detailed Cloud Billing export và BigQuery là nền tảng thuận lợi để xây canonical cost layer, allocation mart, unit economics dashboard và chargeback ledger. Hãy bắt đầu bằng báo cáo không phá hủy dữ liệu nguồn, công khai phần chưa phân bổ, thỏa thuận quy tắc với Finance và product owners rồi mới ghi sổ. Mục tiêu cuối cùng của FinOps không phải làm cho mọi khoản phí có một cái tên, mà là giúp các nhóm đưa ra quyết định cân bằng **giá trị, hiệu năng, độ tin cậy và chi phí**.

## Tài liệu tham khảo

- [Set up Cloud Billing data export to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-setup)
- [Understand Cloud Billing data tables](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables)
- [Standard usage cost export schema](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage)
- [Detailed usage cost export schema](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage)
- [Example queries for Cloud Billing data export](https://docs.cloud.google.com/billing/docs/how-to/bq-examples)
- [Get key spending insights from GKE cost allocation](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cost-allocations)
- [Google Cloud Billing reports and cost management](https://docs.cloud.google.com/billing/docs/how-to/reports)
- [BigQuery partitioned tables](https://docs.cloud.google.com/bigquery/docs/partitioned-tables)
- [BigQuery authorized views](https://docs.cloud.google.com/bigquery/docs/authorized-views)
- [FinOps Foundation: Framework](https://www.finops.org/framework/)
