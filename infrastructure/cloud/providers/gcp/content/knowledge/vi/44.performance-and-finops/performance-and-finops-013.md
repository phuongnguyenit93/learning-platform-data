# Carbon Footprint và đánh giá tác động môi trường của workload

Tối ưu hiệu năng và chi phí chưa phản ánh toàn bộ hiệu quả sử dụng tài nguyên đám mây. Hai ứng dụng có chi phí tương đương có thể tạo ra lượng phát thải khí nhà kính ước tính khác nhau do loại tài nguyên, vị trí triển khai, thời điểm sử dụng điện và mức độ sử dụng thực tế. Ngược lại, chuyển workload sang một region có tỷ lệ năng lượng không carbon cao hơn nhưng làm tăng độ trễ, lưu lượng liên vùng và số bản sao cũng có thể không đạt lợi ích tổng thể mong muốn.

Trong chương **Hiệu năng và FinOps** của module **CLOUD_PROVIDERS_GCP**, bài học này hướng dẫn đo lường, phân tích và cải thiện tác động môi trường của workload trên Google Cloud. Nội dung nối kết tổ chức project, IAM, VPC, Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu với chi phí, hiệu năng, độ tin cậy và thực hành GreenOps/FinOps. Trọng tâm là **Google Cloud Carbon Footprint**, phương pháp luận và BigQuery export, cùng cách thiết kế thay đổi có thể chứng minh bằng số liệu, thay vì tuyên bố giảm phát thải chỉ từ ước đoán.

Sau bài học, người học có thể:

- Giải thích CO₂e, các phạm vi phát thải, location-based và market-based accounting.
- Hiểu Carbon Footprint đo lường điều gì, giới hạn bao phủ, mức tổng hợp và độ trễ xuất bản.
- Truy cập dashboard bằng IAM đúng trên Cloud Billing account.
- Thiết lập xuất dữ liệu Carbon Footprint vào BigQuery và truy vấn theo tháng, project, dịch vụ, region.
- Phân biệt phát thải ước tính do nhà cung cấp phân bổ với đo đạc năng lượng của từng VM, Pod hay request.
- Xây KPI carbon intensity theo đơn vị nghiệp vụ và đánh giá biến động công bằng.
- Phân tích các cơ hội tối ưu vùng, máy tính, serverless, Kubernetes, lưu trữ, mạng và batch.
- Cân bằng carbon, chi phí, latency, dữ liệu cư trú, an toàn và SLO.
- Thiết kế dashboard, quy trình kiểm chứng tác động và quản trị dữ liệu phục vụ báo cáo bền vững.

## 1. Carbon Footprint trong FinOps là gì?

**Carbon footprint** mô tả lượng khí nhà kính quy đổi về CO₂ tương đương (CO₂e) gắn với hoạt động đang xét. CO₂e không chỉ tính riêng carbon dioxide mà quy đổi tác động làm nóng lên của các khí nhà kính về một đơn vị chung.

Trong Google Cloud:

- **Cloud Billing** cho biết khoản chi phí theo sản phẩm, project, SKU và đơn vị sử dụng.
- **Cloud Monitoring** đo CPU, memory, network, số request, độ trễ, lỗi và các tín hiệu vận hành.
- **Carbon Footprint** cung cấp **ước tính phát thải** được Google phân bổ cho mức sử dụng các dịch vụ nằm trong phạm vi báo cáo, theo billing account, tháng, project, sản phẩm và địa điểm.

Không nên suy trực tiếp phát thải từ tiền thanh toán bằng một tỷ lệ kgCO₂e/USD cố định. Giá chịu ảnh hưởng của chiết khấu, hợp đồng, cấu trúc SKU và region, còn phát thải liên quan đến năng lượng, nguồn điện và phương pháp phân bổ. Chi phí và phát thải có thể cùng giảm khi xóa tài nguyên rảnh, nhưng quan hệ này không phải lúc nào cũng tuyến tính.

### 1.1. Các đơn vị cần phân biệt

| Đơn vị | Ý nghĩa | Ví dụ sử dụng |
|---|---|---|
| kWh | Năng lượng điện | Phân tích tiêu thụ và carbon intensity của lưới điện |
| gCO₂e/kWh | Cường độ phát thải của điện | So sánh đặc điểm nguồn điện giữa region |
| kgCO₂e | Khối lượng phát thải quy đổi | Tổng tháng trong BigQuery export |
| tCO₂e | Tấn phát thải quy đổi | Tổng quan trong Carbon Footprint dashboard |
| % CFE | Tỷ lệ năng lượng không carbon (carbon-free energy) theo phương pháp được công bố | Một tín hiệu khi chọn region |
| kgCO₂e/1.000 request | Cường độ phát thải trên đơn vị nghiệp vụ | Đánh giá hiệu quả API ở cùng mức chất lượng |

Quan hệ đổi đơn vị: **1 tCO₂e = 1.000 kgCO₂e**. Chỉ chuyển đổi đơn vị, không coi một tấn phát thải trong báo cáo của nhà cung cấp là một tấn phát thải trực tiếp Scope 1 của khách hàng.

## 2. Hiểu Scope 1, Scope 2 và Scope 3

Google Cloud Carbon Footprint mô tả các nguồn phát thải theo cách phân loại của **Greenhouse Gas Protocol (GHG Protocol)**:

| Scope trong báo cáo của Google | Loại nguồn | Ví dụ trong hoạt động trung tâm dữ liệu |
|---|---|---|
| Scope 1 | Phát thải trực tiếp từ hoạt động thuộc phạm vi báo cáo | Nhiên liệu cho máy phát dự phòng, khí làm lạnh rò rỉ |
| Scope 2 | Phát thải do điện năng được mua/sử dụng | Điện cho máy chủ, network, cooling, lighting |
| Scope 3 | Phát thải gián tiếp ở các khâu khác trong chuỗi giá trị nằm trong phạm vi mô hình | Chế tạo thiết bị, xây dựng trung tâm dữ liệu, một số hoạt động upstream |

**Rất quan trọng:** các scope trên là cách Google phân loại thành phần phát thải trong mô hình Carbon Footprint. Khi một doanh nghiệp mua dịch vụ đám mây, lượng phát thải gắn với dịch vụ đó thường liên quan đến **Scope 3 của doanh nghiệp mua**, theo chính sách kế toán khí nhà kính của tổ chức. Không lấy số Scope 1 của Google rồi ghi là Scope 1 trực tiếp của công ty khách hàng.

Carbon Footprint không bao trùm mọi hoạt động trong chuỗi giá trị của người dùng. Ví dụ, thiết bị khách hàng, lượng điện dùng tại văn phòng, thiết bị đầu cuối và các dịch vụ ngoài phạm vi sản phẩm báo cáo phải được đánh giá riêng nếu thuộc ranh giới kiểm kê tổ chức.

### 2.1. Location-based (theo địa điểm)

**Location-based** dùng đặc điểm nguồn điện tại lưới điện nơi tiêu thụ, thông qua hệ số phát thải theo vị trí và thời gian. Chỉ số này giúp đánh giá tương đối tác động của việc chọn region, thời điểm tính toán và cách phân phối workload, mặc dù báo cáo Carbon Footprint cuối cùng vẫn được tổng hợp theo **tháng**.

Phương pháp location-based không phản ánh riêng các hợp đồng mua điện sạch/chứng nhận điện sạch trong cách tính Scope 2; nó phản ánh đặc tính lưới điện.

### 2.2. Market-based (theo thị trường)

**Market-based** tính Scope 2 theo phương pháp phản ánh hoạt động mua năng lượng sạch của Google, căn cứ các thỏa thuận và hệ số phát thải trong mô hình công bố. Đây là góc nhìn hữu ích cho báo cáo phát thải có liên quan đến hợp đồng năng lượng sạch của nhà cung cấp.

Hai con số location-based và market-based **không được cộng lại**; chúng là hai cách tính cho phần Scope 2 trong cùng một phạm vi hoạt động.

### 2.3. Công thức tổng phát thải

Với cùng một billing account/project/service/location/month:

\[
E_{\text{location}} = E_1 + E_{2,\text{location}} + E_3
\]

\[
E_{\text{market}} = E_1 + E_{2,\text{market}} + E_3
\]

Các giá trị trong báo cáo có thể chênh lệch rất nhỏ khi đối chiếu bằng phép cộng do làm tròn hoặc cách hiển thị. Không nên lấy hiệu số giữa hai tổng để gọi đó là “lượng carbon đã loại bỏ” do một thay đổi kỹ thuật cụ thể.

### 2.4. Carbon offsets không còn là trường tổng cần dùng

Trong schema Carbon Footprint hiện hành, hai trường `carbon_offsets_kgCO2e` và `carbon_footprint_total_kgCO2e.after_offsets` đã **deprecated** và trả về NULL. Các trường tổng cần sử dụng là `carbon_footprint_total_kgCO2e.location_based` và `carbon_footprint_total_kgCO2e.market_based`. Không tạo dashboard mới dùng giá trị after_offsets hoặc lấy NULL coi như “phát thải bằng 0”.

## 3. Carbon Footprint đo lường và phân bổ như thế nào?

Google Cloud dùng mô hình phân bổ ước tính dựa trên dữ liệu hoạt động máy móc/dịch vụ, năng lượng của trung tâm dữ liệu, đặc điểm lưới điện, hoạt động mua điện sạch và các nguồn phát thải gián tiếp được bao gồm.

~~~mermaid
flowchart LR
    Use[Google Cloud SKU usage] --> Allocation[Phân bổ năng lượng / hoạt động]
    DC[Data center energy + overhead] --> Allocation
    Grid[Hệ số phát thải lưới điện] --> Loc[Location-based Scope 2]
    CFE[Hợp đồng năng lượng sạch theo phương pháp Google] --> Market[Market-based Scope 2]
    Allocation --> Loc
    Allocation --> Market
    Other[Scope 1 + Scope 3 được phân bổ] --> Report[Carbon Footprint theo tháng]
    Loc --> Report
    Market --> Report
    Report --> BQ[BigQuery export]
~~~

Mô hình nhận diện phần năng lượng máy tính sử dụng khi chạy và năng lượng khi máy rảnh, cộng thêm overhead hỗ trợ như cooling và nguồn điện. Công nghệ cloud chia sẻ hạ tầng giữa nhiều khách hàng, nên phải sử dụng các quy tắc phân bổ để quy về các SKU, dịch vụ và khách hàng cụ thể.

**Hệ quả thực tế:**

- Số liệu là **ước tính được mô hình hóa**, không phải kết quả đo bằng công tơ riêng cho mỗi workload.
- Không phải mọi Google Cloud SKU/sản phẩm đều nằm trong phạm vi có thể phân bổ.
- Dữ liệu phát thải thuộc hoạt động dùng dịch vụ, không bao gồm trọn vẹn mọi tác động vật lý ngoài biên giới báo cáo của Google.
- Không có phép đo từng request, pod hoặc container trực tiếp trong export.
- Mô hình và hệ số đầu vào có thể thay đổi theo kỳ cập nhật phương pháp luận, làm lệch so sánh lịch sử nếu không lưu thông tin phiên bản.

### 3.1. Độ phân giải và độ trễ

Carbon Footprint dashboard tự tính dữ liệu theo billing account, **không cần bật một API Carbon Footprint riêng** chỉ để xem dashboard. Dữ liệu tháng trước có thể mất **tới 21 ngày** để hiển thị. Dashboard hiển thị tCO₂e, còn BigQuery export hiển thị kgCO₂e.

Export dùng **BigQuery Data Transfer Service**, tạo bảng theo phân vùng tháng và chạy theo lịch được Google công bố, thông thường ngày 15 của tháng tiếp theo. Cần quản lý ngày hoàn tất transfer để biết kỳ nào đã chốt cho báo cáo nội bộ.

Không dùng báo cáo Carbon Footprint để cảnh báo “CO₂e trong 5 phút vừa qua” hoặc tự nhận có số liệu phát thải theo từng request trực tiếp. Chỉ số hiệu năng theo phút/giờ dùng để điều tra nguyên nhân; Carbon Footprint theo tháng dùng để đối chiếu xu hướng và kết quả.

### 3.2. Giới hạn diễn giải con số 0

Một project hoặc dịch vụ có giá trị 0 hoặc không có bản ghi có thể do mức phát thải nhỏ/ước tính bằng 0, thiếu dữ liệu, phạm vi bao phủ, biến động phân bổ hoặc kỳ xuất dữ liệu chưa hoàn tất. **Không có bản ghi không đồng nghĩa workload phát thải bằng 0.**

Với `project.id` bị NULL, dữ liệu có thể không gắn được với project hoặc project đã bị xóa. Không âm thầm loại bỏ các bản ghi này khi đối chiếu tổng billing account; nên hiển thị nhóm `UNATTRIBUTED` hoặc tương đương.

## 4. Truy cập Carbon Footprint dashboard

### 4.1. IAM ở cấp Billing account

Để xem dữ liệu Carbon Footprint, tài khoản cần quyền trên **Cloud Billing account**, không chỉ role Viewer của một project.

| Role | Phạm vi | Ghi chú |
|---|---|---|
| `roles/billing.carbonViewer` | Billing account | Xem Carbon Footprint mà không cần xem chi phí chi tiết |
| `roles/billing.viewer` | Billing account | Xem dữ liệu billing và carbon theo quyền role |
| `roles/billing.admin` | Billing account | Có quyền quản trị billing rộng; không nên cấp chỉ để xem carbon |

Permission cốt lõi là `billing.accounts.getCarbonInformation`, cùng quyền liệt kê/xem billing account để điều hướng dashboard. Quản trị viên billing cần cấp quyền tại trang IAM của billing account; cấp `roles/viewer` ở project thường không đủ.

### 4.2. Thao tác trong Console

1. Mở **Google Cloud Console → Carbon Footprint** (mục Tools).
2. Chọn Cloud Billing account cần phân tích.
3. Mở tab **Location-based emissions** và **Market-based emissions**.
4. Xem tổng 12 tháng gần nhất và tháng đã hoàn tất gần nhất.
5. Xem diễn biến theo tháng, region; với tab location-based xem thêm breakdown theo project và product khi giao diện cung cấp.
6. Ghi nhận khoảng thời gian và phương pháp đo đang được dùng trước khi so sánh.

Một con số phát thải được cung cấp cho billing account không tự động trả lời câu hỏi “microservice A phát bao nhiêu?”. Cần ánh xạ project/service/region sang workload, rồi ghi rõ độ tin cậy của phép phân bổ.

### 4.3. Có thể xem mà không xem chi phí

`roles/billing.carbonViewer` hữu ích khi nhóm Sustainability hoặc SRE chỉ cần xem phát thải và không cần quyền truy cập hóa đơn. Tuy nhiên, khi cùng xây dashboard carbon + chi phí trong BigQuery, cần thêm các quyền đọc dataset phù hợp và phân tách dữ liệu theo nguyên tắc least privilege.

## 5. Xuất dữ liệu Carbon Footprint vào BigQuery

Carbon Footprint không có dedicated public API để truy vấn dữ liệu trực tiếp. Đường tích hợp được Google hướng dẫn là **BigQuery Data Transfer Service** để xuất dữ liệu, rồi dùng **BigQuery SQL/API** phân tích. Không nhầm cơ chế này với Cloud Billing cost export: hai nguồn có schema, độ phân giải và mục đích khác nhau.

### 5.1. Kiến trúc dữ liệu

~~~mermaid
flowchart LR
    BA[Cloud Billing account] --> Carbon[Carbon Footprint monthly report]
    Carbon --> DTS[BigQuery Data Transfer Service]
    DTS --> Raw[(BigQuery carbon_footprint)]
    Billing[Cloud Billing cost/usage export] --> Cost[(BigQuery billing tables)]
    Raw --> Model[Clean views / metric definitions]
    Cost --> Model
    Model --> Dash[Looker Studio / BI / FinOps dashboard]
    Model --> Review[Quarterly GreenOps review]
~~~

Phương án này phân tách **raw source** và **derived metrics**. Nên giữ nguyên export gốc, xây view/tables riêng cho dashboard và ghi cách xử lý NULL, chọn phương pháp tính, các kỳ thiếu dữ liệu, phạm vi billing account.

### 5.2. Quyền và bước cấu hình

Việc tạo export cần permission tương ứng trên project đích (ví dụ `resourcemanager.projects.update`, `serviceusage.services.enable` và `bigquery.transfers.update`), đồng thời `billing.accounts.getCarbonInformation` trên billing account. Google đưa ra các role rộng cho bước thiết lập thuận tiện, nhưng tổ chức có thể dùng role tùy chỉnh để giới hạn quyền triển khai.

Quy trình trên Console:

1. Chọn billing account ở Carbon Footprint.
2. Chọn **Data export**.
3. Chọn project lưu export; mở BigQuery Data Transfer Service.
4. Chọn nguồn **Google Cloud Carbon Footprint Exports**.
5. Chọn hoặc tạo BigQuery dataset đích; khai báo billing account ID.
6. Lưu transfer và cấp consent/quyền cần thiết.
7. Kiểm tra transfer run và bảng `carbon_footprint` xuất hiện.
8. Lập lịch backfill cho dữ liệu lịch sử nếu cần.

BigQuery storage và query có chi phí, cần dataset location, retention policy và IAM riêng. Nếu dự án dùng VPC Service Controls, phải kiểm tra yêu cầu ingress policy cho BigQuery/BigQuery Data Transfer và danh tính dịch vụ xuất dữ liệu theo tài liệu Google.

### 5.3. Ví dụ tạo transfer bằng bq

~~~bash
bq mk \
  --transfer_config \
  --target_dataset=carbon_reporting \
  --display_name="Monthly Google Cloud Carbon Footprint" \
  --params='{"billing_accounts":"XXXXXX-XXXXXX-XXXXXX"}' \
  --data_source='61cede5a-0000-2440-ad42-883d24f8f7b8'
~~~

Đây là ví dụ hình thức; thay billing account ID/dataset thật, cấu hình quyền, project, location và data-source enrollment cần thiết. Theo tài liệu Google, nếu tạo transfer ngoài Console, có trường hợp cần **enroll data source** trước khi chạy. Transfer mới không tự bảo đảm đã có đầy đủ dữ liệu lịch sử; backfill cần được yêu cầu riêng.

### 5.4. Độ hạt của dữ liệu export

Mỗi record đại diện lượng phát thải ước tính theo tổ hợp **billing account + project + service + location + usage month** trong schema công bố. Tên bảng thường là `carbon_footprint`.

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `usage_month` | DATE | Ngày đầu tháng sử dụng |
| `billing_account_id` | STRING | Billing account |
| `project.id` | STRING | Project ID, có thể NULL |
| `project.number` | STRING | Project number |
| `service.id`, `service.description` | STRING | Dịch vụ GCP |
| `location.region`, `location.location` | STRING | Region/location |
| `carbon_model_version` | INTEGER | Phiên bản mô hình tính |
| `carbon_footprint_total_kgCO2e.location_based` | FLOAT | Tổng location-based |
| `carbon_footprint_total_kgCO2e.market_based` | FLOAT | Tổng market-based |
| `carbon_footprint_kgCO2e.scope1` | FLOAT | Thành phần Scope 1 |
| `carbon_footprint_kgCO2e.scope2.location_based` | FLOAT | Scope 2 theo địa điểm |
| `carbon_footprint_kgCO2e.scope2.market_based` | FLOAT | Scope 2 theo thị trường |
| `carbon_footprint_kgCO2e.scope3` | FLOAT | Thành phần Scope 3 |

Tên trường có chữ hoa/thường và cấu trúc RECORD/STRUCT; phải dùng đúng schema đã export, không suy từ tên trên dashboard.

## 6. Ví dụ SQL: phân tích theo tháng, project và region

Các câu SQL dưới đây dùng **GoogleSQL** (BigQuery Standard SQL), giả định bảng `PROJECT_ID.carbon_reporting.carbon_footprint` được tạo bởi transfer. Chúng là mẫu; không tạo resource thật hay ghi vào hệ thống sản xuất.

### 6.1. Tổng phát thải từng tháng theo billing account

~~~sql
SELECT
  billing_account_id,
  usage_month,
  ROUND(SUM(carbon_footprint_total_kgCO2e.location_based), 3)
      AS location_based_kgco2e,
  ROUND(SUM(carbon_footprint_total_kgCO2e.market_based), 3)
      AS market_based_kgco2e
FROM `PROJECT_ID.carbon_reporting.carbon_footprint`
WHERE usage_month >= DATE '2026-01-01'
  AND usage_month < DATE '2027-01-01'
GROUP BY billing_account_id, usage_month
ORDER BY usage_month, billing_account_id;
~~~

Trong ví dụ dùng ký hiệu backtick quanh fully-qualified table name. Dùng date filter để giảm lượng dữ liệu quét và bảo đảm không trộn kỳ tháng chưa hoàn thành vào tháng đã chốt. **Không cộng hai cột location-based và market-based thành một tổng.**

### 6.2. Top project theo location-based carbon

~~~sql
SELECT
  billing_account_id,
  COALESCE(project.id, 'UNATTRIBUTED') AS project_id,
  ROUND(SUM(carbon_footprint_total_kgCO2e.location_based), 3)
      AS kgco2e_location_based
FROM `PROJECT_ID.carbon_reporting.carbon_footprint`
WHERE usage_month = DATE '2026-09-01'
GROUP BY billing_account_id, project_id
ORDER BY kgco2e_location_based DESC;
~~~

Không tự kết luận project đứng đầu là “lãng phí nhất”: project có quy mô lớn hơn thường có phát thải tuyệt đối lớn hơn. Cần so sánh thêm công việc đã xử lý và SLO để tìm nơi có hiệu quả thấp.

### 6.3. Ma trận project × service × region

~~~sql
SELECT
  usage_month,
  COALESCE(project.id, 'UNATTRIBUTED') AS project_id,
  service.description AS service_name,
  COALESCE(location.region, 'UNKNOWN_REGION') AS region,
  ROUND(SUM(carbon_footprint_total_kgCO2e.location_based), 3)
      AS kgco2e_location_based,
  ROUND(SUM(carbon_footprint_total_kgCO2e.market_based), 3)
      AS kgco2e_market_based
FROM `PROJECT_ID.carbon_reporting.carbon_footprint`
WHERE usage_month BETWEEN DATE '2026-07-01' AND DATE '2026-09-01'
GROUP BY usage_month, project_id, service_name, region
ORDER BY usage_month, kgco2e_location_based DESC;
~~~

Nhóm này giúp trả lời “tháng nào, project nào, dịch vụ nào và region nào là điểm nóng?”. Khi phân tích một billing account cụ thể, thêm filter `billing_account_id`; nếu đang xuất nhiều billing account, phải giữ dimension billing_account_id để tránh gộp những dữ liệu không thuộc cùng owner.

### 6.4. Đối chiếu các Scope, tránh nhầm loại tổng

~~~sql
SELECT
  usage_month,
  ROUND(SUM(carbon_footprint_kgCO2e.scope1), 3) AS scope1_kg,
  ROUND(SUM(carbon_footprint_kgCO2e.scope2.location_based), 3)
      AS scope2_location_kg,
  ROUND(SUM(carbon_footprint_kgCO2e.scope2.market_based), 3)
      AS scope2_market_kg,
  ROUND(SUM(carbon_footprint_kgCO2e.scope3), 3) AS scope3_kg,
  ROUND(SUM(carbon_footprint_total_kgCO2e.location_based), 3)
      AS total_location_kg,
  ROUND(SUM(carbon_footprint_total_kgCO2e.market_based), 3)
      AS total_market_kg
FROM `PROJECT_ID.carbon_reporting.carbon_footprint`
WHERE usage_month = DATE '2026-09-01'
GROUP BY usage_month;
~~~

Tổng location-based đối chiếu Scope 1 + Scope 2 location-based + Scope 3; market-based đối chiếu Scope 1 + Scope 2 market-based + Scope 3. Kiểm tra NULL, rounding và model_version trước khi kết luận dữ liệu sai lệch.

### 6.5. Gắn phiên bản mô hình và tình trạng dữ liệu

~~~sql
SELECT
  usage_month,
  carbon_model_version,
  COUNT(*) AS row_count,
  COUNTIF(project.id IS NULL) AS unattributed_rows,
  COUNTIF(carbon_footprint_total_kgCO2e.location_based IS NULL)
      AS missing_location_values
FROM `PROJECT_ID.carbon_reporting.carbon_footprint`
WHERE usage_month >= DATE '2026-01-01'
GROUP BY usage_month, carbon_model_version
ORDER BY usage_month, carbon_model_version;
~~~

Số model version thay đổi có thể báo hiệu cần đối chiếu phương pháp luận; không mặc định dữ liệu hai kỳ dùng cùng hệ số. Một tháng xuất hiện nhiều model version cần được kiểm tra ở độ hạt phù hợp và so sánh với release notes.

## 7. Xây KPI carbon intensity theo workload

Phát thải tuyệt đối chưa đủ cho đánh giá hiệu quả. Workload phục vụ lượng request gấp đôi có thể phát thải tăng 20% nhưng **kgCO₂e trên 1.000 request** giảm. Cần đo cả **absolute footprint** và **workload-normalized intensity**.

### 7.1. Công thức

\[
\text{Carbon intensity} =
\frac{E_{\text{workload (kgCO₂e)}}}
{\text{Business output}} .
\]

Đơn vị đầu ra có thể là:

- 1.000 HTTP requests hợp lệ (cùng loại, kích thước và mức độ phức tạp).
- 1.000 đơn hàng hoàn tất.
- Một triệu records xử lý trong batch ETL.
- Một giờ video được xử lý hoặc một GB dữ liệu xử lý.
- Một mô hình ML được huấn luyện đến ngưỡng chất lượng xác định.

Đặt KPI theo thứ có ý nghĩa nghiệp vụ. Đừng tối ưu số request bằng cách chia nhỏ request hoặc giảm chất lượng dịch vụ mà không tính đến output thực.

### 7.2. Ví dụ minh họa

Giả định một ứng dụng có số liệu nội bộ:

| Kỳ | Tổng location-based (kgCO₂e) | Đơn hàng hoàn tất | kgCO₂e / 1.000 đơn |
|---|---:|---:|---:|
| Tháng A | 420 | 140.000 | 3,00 |
| Tháng B | 480 | 240.000 | 2,00 |

Mặc dù phát thải tuyệt đối tăng 60 kgCO₂e, intensity giảm từ 3 xuống 2 kgCO₂e trên 1.000 đơn. Đây là **ví dụ giả lập**, không phải số đo thực tế của một hệ thống Google Cloud.

Nếu mục tiêu của tổ chức là giảm phát thải tuyệt đối, intensity giảm **không đủ** để tuyên bố đã đạt mục tiêu. Cần theo dõi đồng thời tổng lượng phát thải, cường độ, mức độ tăng trưởng workload, SLO và cost.

### 7.3. Attribution theo team/service

Nếu mỗi workload dùng project riêng hoặc có ownership rõ ràng, có thể tổng hợp Carbon Footprint theo project. Nếu nhiều dịch vụ cùng dùng một project, dữ liệu native chưa đủ để biết chính xác pod/VM nào đóng góp bao nhiêu.

Google công bố cách **ước lượng** chi tiết hơn bằng cách join Carbon Footprint export với Cloud Billing detailed cost/usage export, rồi phân bổ phát thải tại cùng billing account, project, product, region, month theo tỷ trọng **cost at list** của resource/label. Đây là **ước lượng phân bổ**, không phải đo điện ở cấp resource.

Đặc biệt phải:

- Aggregate dữ liệu billing lên đúng cùng grain trước khi join.
- Không join row-by-row khiến Carbon Footprint bị nhân bản khi có nhiều billing line items.
- Dùng denominator chỉ gồm các resource hợp lệ trong cùng nhóm.
- Kiểm tra tổng phân bổ bằng tổng gốc để tránh double counting hoặc phần dư không rõ owner.
- Ghi lại phần “unattributed/unallocated” thay vì ép phân bổ tất cả khi thiếu dữ liệu.
- Ghi phương pháp và độ tin cậy trên dashboard.

### 7.4. Một phép phân bổ gần đúng

Với nhóm `g = (billing_account, project, service, region, month)`:

\[
\widehat{E}_{i} =
E_g \times \frac{\text{ListCost}_{i}}{\sum_{j \in g}\text{ListCost}_{j}} .
\]

Chỉ áp dụng nếu mẫu số dương và nguồn Carbon Footprint/billing khớp về phạm vi. Đây là phép ước lượng ở resource-level theo tỷ trọng cost, **không phải emission factor vật lý riêng của VM i**.

Nếu chiết khấu rất khác giữa tài nguyên, nên dùng cost at list theo hướng dẫn Google thay vì net cost để tránh méo phân bổ. Nếu không có số liệu cost at list đáng tin cậy, để phần đó không phân bổ và công bố giới hạn.

## 8. Chọn region với carbon-aware architecture

Google công bố **Carbon-Free Energy percentage (CFE%)** và **grid carbon intensity (gCO₂e/kWh)** theo region, kèm bộ lọc/nhãn **Low CO₂** cho một số vị trí. Hai chỉ số không đồng nghĩa:

- CFE% phản ánh tỷ lệ năng lượng không carbon theo phương pháp Google trong region.
- Grid carbon intensity phản ánh phát thải điện theo hỗn hợp nguồn điện lưới.
- Carbon Footprint monthly report phản ánh phân bổ phát thải của **usage thực tế** ở mức tổng hợp.

Một region có CFE% cao không đương nhiên có latency tốt, cost thấp, đủ quota hoặc khả năng đáp ứng data residency. Lựa chọn region cần đánh giá đa mục tiêu.

### 8.1. Ma trận quyết định region

| Yếu tố | Câu hỏi cần trả lời |
|---|---|
| Data residency | Dữ liệu được phép lưu/xử lý ở đâu? |
| Latency | p95/p99 đến người dùng và dependency có đạt SLO? |
| Reliability | HA, DR, region pair và RTO/RPO đạt yêu cầu? |
| Cost | Compute, database, network egress, cross-region traffic thay đổi thế nào? |
| Capacity | SKU, accelerator, quota, managed service có sẵn? |
| Sustainability | CFE%, grid carbon intensity và Carbon Footprint lịch sử thế nào? |
| Operational risk | Migration, consistency, backups, security và compliance có bị ảnh hưởng? |

Đối với người dùng ở Việt Nam, có thể so sánh các region châu Á liên quan theo yêu cầu network và data residency. Không khuyến nghị chuyển tất cả dữ liệu sang một region xa chỉ vì CFE% cao nếu làm tăng độ trễ, lưu lượng và rủi ro vận hành.

### 8.2. Carbon-aware batch scheduling

Workload batch như ETL, training, reindex hoặc dựng báo cáo có thể có cửa sổ chạy linh hoạt. Có thể:

1. Xác định deadline nghiệp vụ và dữ liệu phải sẵn sàng trước thời điểm nào.
2. Kiểm tra region hợp lệ và khả năng chuyển việc sang region khác.
3. So sánh nguồn điện/cường độ carbon theo dữ liệu phù hợp, không giả định Carbon Footprint monthly export là tín hiệu thời gian thực.
4. Chọn thời điểm/region ít carbon hơn nếu chi phí, độ trễ và SLO không bị vi phạm.
5. Ghi baseline, số job, tài nguyên, output, thời gian, CO₂e ước tính và chi phí.

Với hệ thống cần lập lịch theo **cường độ carbon theo giờ**, sử dụng nguồn tín hiệu theo giờ được cấp phép/được kiểm chứng và đánh giá độ tin cậy, không suy ra từ bảng Carbon Footprint tháng.

## 9. Cải thiện hiệu quả Compute Engine và GKE

### 9.1. Compute Engine: ưu tiên loại bỏ lãng phí

Những cơ hội thường gặp:

- Xóa VM, disk, image, IP, load balancer và tài nguyên thực sự bỏ quên.
- Rightsize VM theo CPU, memory, throughput và latency thực tế.
- Tự động stop/start môi trường dev/test không cần chạy 24/7.
- Dùng Managed Instance Group/autoscaling cho tải biến thiên.
- Đánh giá machine family/CPU thế hệ mới, profiling và hiệu suất trên đơn vị công việc.
- Loại bỏ disk dư thừa nhưng giữ đủ backup, retention và RPO.

Rightsizing phải xét cả workload peak, memory working set, network, IOPS, GC và tail latency. Một VM dùng CPU trung bình thấp có thể vẫn cần headroom cho batch spike, failover hoặc transaction peak. Chỉ nhìn trung bình CPU rồi cắt một nửa máy có thể làm SLO xấu và gây retry lớn hơn.

### 9.2. GKE: tối ưu cấp Pod và node

Với Kubernetes:

- Xem requests/limits, tỷ lệ sử dụng tài nguyên và pod Pending/OOMKilled.
- Tinh chỉnh HPA/VPA theo dữ liệu thực tế; hiểu tác động lên node autoscaler.
- Cải thiện bin-packing để ít node rảnh hơn mà vẫn giữ HA.
- Dùng GKE Autopilot hoặc Standard theo mức kiểm soát/năng lực vận hành.
- Loại bỏ namespaces, jobs, clusters và preview environments không còn dùng.
- Xem loại node, accelerator và kiến trúc phù hợp workload.
- Giám sát cluster capacity/zone spread, rollout surge và disruption budget.

**Không đồng nhất “node ít hơn” với “độ tin cậy đủ”.** Cần giữ khả năng chịu lỗi zone/node theo SLO; tránh đặt PodDisruptionBudget vô lý khiến bảo trì không thể diễn ra.

### 9.3. JVM trong container

Ứng dụng Java/Spring có thể lãng phí vì heap quá lớn, thread pool vượt CPU hoặc container giữ minimum replicas cao. Các phép đo hữu ích: process RSS, heap/GC, CPU throttling, connection pool, startup và request latency.

Điều chỉnh concurrency và heap theo load test, không tăng container memory chỉ để tránh mọi OOM mà không điều tra. Việc tiết kiệm memory có thể cho phép đặt nhiều pod hơn trên node, nhưng cần chứng minh không làm tăng GC pause và p99 latency.

## 10. Cloud Run, functions và kiến trúc theo nhu cầu

Cloud Run có thể scale theo request và giảm số instance khi tải thấp. Tuy nhiên, **scale-to-zero không bảo đảm footprint bằng 0**: các dịch vụ phụ thuộc, lưu trữ, networking và baseline hạ tầng vẫn tồn tại, còn báo cáo Carbon Footprint vẫn tính theo phương pháp phân bổ.

### 10.1. Các nút điều chỉnh

- **Minimum instances:** giữ >0 chỉ khi lợi ích cold start/SLO được chứng minh.
- **Maximum instances:** tránh scale không kiểm soát và bảo vệ downstream database.
- **Concurrency:** tăng hợp lý để tận dụng CPU/memory, nhưng đo queueing và tail latency.
- **CPU/memory:** size theo traffic và startup profile thực.
- **Request/Job architecture:** tách batch có vòng đời rõ ràng sang Cloud Run Jobs.
- **Retry policy:** tránh retry storm gây số lần xử lý và resource consumption tăng.
- **Caching:** giảm xử lý lặp và số lần gọi database/API, nhưng đo cache memory và invalidation.

Giảm tối đa instance có thể giảm lãng phí ở một số trường hợp, nhưng đừng biến giới hạn autoscaling thành nguyên nhân mất availability.

### 10.2. Ví dụ kiểm chứng thay đổi

Một API chạy Cloud Run muốn giảm minimum instances từ 4 xuống 1. Thực hiện:

1. Chụp baseline 2–4 tuần có đại diện đủ tải và giờ thấp điểm.
2. Ghi throughput, p95/p99 latency, error rate, cold starts, CPU/memory và cost.
3. Thử 1 minimum instance trên staging hoặc canary có traffic phù hợp.
4. Kiểm tra hành vi khi lưu lượng đột tăng và database connection pool.
5. Quan sát một tháng Carbon Footprint đã hoàn tất, kiểm tra các biến số khác.
6. Chỉ công bố kết quả giảm phát thải **ước tính** khi so sánh cùng phương pháp, cùng ranh giới và nêu rõ mức độ quy thuộc.

Nếu cùng project có nhiều dịch vụ thay đổi đồng thời, không thể gán toàn bộ chênh lệch Carbon Footprint của project cho việc giảm minimum instances của một service.

## 11. Lưu trữ, cơ sở dữ liệu và network

### 11.1. Cloud Storage

- Áp lifecycle policy cho temporary files, exports và log/artifact không còn cần.
- Chọn storage class theo tần suất truy cập và điều kiện khôi phục, không chỉ chọn loại rẻ nhất.
- Tránh giữ dữ liệu trùng lặp hoặc backup không có owner/retention.
- Giảm số lần đọc/ghi không cần thiết; gom việc xử lý và cache khi phù hợp.
- Xem chi phí và tác động của **replication** theo yêu cầu DR.

Thay đổi storage class có thể làm tăng retrieval/operation cost và latency; xóa backup để “giảm carbon” mà phá RPO là lựa chọn sai.

### 11.2. Cloud SQL, Spanner và BigQuery

- Cloud SQL: rightsize instance, connection pool, replica thực sự cần, backup và disk.
- Spanner: chọn compute capacity/storage config theo tải thực, tránh provisioning quá dư.
- BigQuery: partition, clustering, filter, incremental processing; giảm full-table scan và pipeline chạy lặp.
- Dataflow/Pub/Sub: giảm duplicate processing, tối ưu batch/streaming và retention/backlog.
- Đặt data location phù hợp để hạn chế cross-region traffic không cần thiết.

BigQuery chi phí scan giảm không tự chứng minh phát thải giảm cùng tỷ lệ; cần theo dõi dữ liệu Carbon Footprint và workload output.

### 11.3. Mạng và phân phối nội dung

- Colocate application và database có traffic lớn khi data residency/SLO cho phép.
- Dùng cache/CDN cho nội dung phù hợp, giảm origin processing và truyền tải lặp.
- Tránh sao chép dữ liệu xuyên region không có yêu cầu nghiệp vụ rõ ràng.
- Theo dõi egress và topology, nhất là khi thử chuyển workload sang region khác.

CDN, load balancer hoặc nhân bản sang nhiều vùng có thể tăng một số nguồn phát thải trong khi giảm ở nơi khác. Cần xét **end-to-end system boundary** và reliability thay vì chỉ xem resource bị tắt.

## 12. Khi chi phí và carbon không cùng chiều

| Quyết định | Khả năng ảnh hưởng chi phí | Khả năng ảnh hưởng phát thải | Điều phải kiểm tra |
|---|---|---|---|
| Xóa VM bỏ quên | Thường giảm | Thường giảm | Không còn dependency hoặc DR cần thiết |
| Đổi sang VM nhỏ hơn | Có thể giảm | Có thể giảm | SLO và retry rate |
| Chuyển region có CFE% cao | Có thể tăng hoặc giảm | Có thể giảm | Network, data residency, redundancy |
| Tăng cache | Tốn cache RAM/chi phí | Có thể giảm backend compute | Cache hit, invalidation, net effect |
| Thêm read replica | Thường tăng | Thường tăng | Có thực sự cần cho availability/read SLO? |
| Scale-to-zero | Thường giảm khi tải thấp | Có thể giảm | Cold start, downstream baseline |
| Di chuyển batch theo giờ | Có thể thay đổi | Phụ thuộc cường độ điện theo thời điểm | Deadline, data motion, hourly signals |
| Tăng compression | Thêm CPU | Giảm network/storage nếu hiệu quả | Net CPU vs transferred data |

Không tối ưu một chỉ số duy nhất. Đặt hệ tiêu chí có constraint cứng: **safety, security, compliance, SLO, RTO/RPO**, sau đó so sánh cost và estimated CO₂e trong không gian lựa chọn còn lại.

## 13. Thiết kế dashboard GreenOps + FinOps

Một dashboard hữu ích tách ba nhóm dữ liệu:

~~~mermaid
flowchart TB
    Carbon[Carbon Footprint monthly export] --> Metric[Metric layer]
    Cost[Billing export / cost-at-list] --> Metric
    Usage[Monitoring + app business metrics] --> Metric
    Metric --> Exec[Executive overview: absolute + intensity]
    Metric --> Eng[Engineering: project / region / service hotspots]
    Metric --> Gov[Governance: coverage, lag, ownership, controls]
~~~

### 13.1. Bộ KPI khuyến nghị

| KPI | Nguồn | Chu kỳ | Cảnh báo diễn giải |
|---|---|---|---|
| Total location-based kgCO₂e | Carbon Footprint | Tháng | Cùng billing account và ranh giới |
| Total market-based kgCO₂e | Carbon Footprint | Tháng | Không cộng với location-based |
| kgCO₂e theo project/service/region | Carbon Footprint | Tháng | Ảnh hưởng mix sản phẩm và model |
| kgCO₂e / 1.000 giao dịch | Carbon + business output | Tháng | Business output phải cùng kỳ/phạm vi |
| Cost per transaction | Billing + business output | Ngày/tháng | Chiết khấu, tín dụng, list vs net |
| Idle resource inventory | Monitoring/Recommender | Tuần | Cần xác minh trước khi xóa |
| Project ownership coverage | Resource inventory | Tháng | Phân loại không có owner |
| Reporting completeness/lag | DTS metadata | Tháng | Không báo cáo kỳ chưa đủ dữ liệu |

Số liệu phát thải có thể cần truy cập hạn chế theo billing account. Tạo BigQuery authorized views/row-level hoặc dataset riêng nếu nhiều team chỉ được xem dữ liệu họ sở hữu. Tránh đưa billing account ID không cần thiết, dữ liệu cost riêng tư hoặc event metadata nhạy cảm vào dashboard công khai.

### 13.2. Data quality gates

Trước khi phát hành báo cáo tháng:

1. Xác nhận transfer run hoàn tất thành công.
2. Xác nhận `usage_month` mục tiêu đã có dữ liệu và nằm trong kỳ được công bố.
3. So sánh tổng carbon theo billing account với dashboard và phạm vi query.
4. Kiểm tra NULL project/location, giá trị thiếu và định nghĩa scope.
5. Kiểm tra phiên bản carbon model/methodology thay đổi.
6. Đối chiếu biến động project/service với billing usage và sự kiện hạ tầng.
7. Ghi ngày export, ngày chốt dữ liệu và version dashboard.
8. Lưu đường dẫn giải trình và người phê duyệt kết quả.

## 14. Kiểm chứng tác động của một biện pháp tối ưu

Một chiến dịch GreenOps nên được quản lý như thử nghiệm kỹ thuật, không phải tổng hợp các câu chuyện “chúng tôi đã tắt 10 VM nên giảm X tấn carbon” khi chưa đo lường.

### 14.1. Đặt giả thuyết

Ví dụ: “Rightsizing một GKE node pool sẽ giảm CPU/memory được cấp phát nhưng không sử dụng; với cùng số giao dịch và p99 latency, phát thải ước tính trên mỗi giao dịch giảm”.

### 14.2. Ghi baseline và confounders

| Dữ liệu | Trước thay đổi | Sau thay đổi |
|---|---|---|
| Khoảng thời gian | Tháng đủ dữ liệu | Tháng đủ dữ liệu |
| Tổng giao dịch | Cùng định nghĩa | Cùng định nghĩa |
| Tải trung bình và peak | Ghi nhận | Ghi nhận |
| p95/p99, error rate, SLO | Ghi nhận | Ghi nhận |
| Service/region architecture | Inventory | Inventory |
| Chi phí | Chọn list/net rõ | Cùng phương pháp |
| Carbon Footprint | Location-based + market-based | Cùng phạm vi |
| Carbon model version | Ghi nhận | Ghi nhận |

Những biến ảnh hưởng: seasonal traffic, thay đổi tính năng, sự kiện marketing, Google thay đổi mô hình phân bổ, region switch, outage, DR testing, traffic source mix, thời gian thu thập và chi phí nền.

### 14.3. Tính chênh lệch

Giả sử một project đã có baseline cùng điều kiện so sánh:

| Chỉ số | Trước (giả lập) | Sau (giả lập) |
|---|---:|---:|
| Đơn hàng/tháng | 200.000 | 200.000 |
| Carbon location-based | 560 kgCO₂e | 490 kgCO₂e |
| Carbon per 1.000 đơn | 2,80 kg | 2,45 kg |
| p99 latency | 420 ms | 425 ms |
| Error rate | 0,10% | 0,10% |

Chênh lệch tuyệt đối = -70 kgCO₂e/tháng; intensity giảm 0,35 kgCO₂e/1.000 đơn. Đây **chỉ là dữ liệu minh họa**. Khi công bố tác động thực, phải nêu việc phân bổ theo project có thể chứa nhiều workload và thay đổi ngoài thí nghiệm.

Với experiment traffic A/B hoặc canary trong cùng tháng, Carbon Footprint native chưa có resolution đủ để phân biệt hai deployment ở mức container. Có thể dùng resource-level estimate từ chi phí và Monitoring để ra quyết định kỹ thuật, nhưng phải gắn nhãn “ước lượng nội bộ”, không trình bày thành số đo carbon chính thức từ Carbon Footprint.

### 14.4. Cách phát biểu kết quả có trách nhiệm

Phù hợp: “Sau tối ưu, tổng location-based phát thải ước tính của project giảm 12,5% giữa hai kỳ, ở mức output tương đương; các thay đổi khác và carbon model được ghi nhận.”

Không phù hợp: “Service A giảm đúng 70 kgCO₂e do thay một dòng JVM flag” nếu báo cáo chỉ có số liệu tổng project và không có bằng chứng phân bổ.

## 15. Thực hành: đánh giá carbon của API thương mại điện tử

**Bối cảnh:** một doanh nghiệp có Cloud Run API, Cloud SQL database, Pub/Sub event pipeline, Cloud Storage artifacts và BigQuery analytics. Mục tiêu là tìm nguồn phát thải ước tính cao, lập danh sách tối ưu có kiểm chứng mà vẫn giữ SLO.

### Bước 1: xác định phạm vi

- Chọn billing account đúng và các project thuộc workload.
- Liệt kê service/region và owner.
- Chọn location-based làm góc nhìn vận hành, giữ market-based song song cho báo cáo.
- Chọn 3–6 tháng hoàn tất, không dùng tháng đang chạy.

### Bước 2: xác thực quyền và export

- Billing admin cấp Carbon Footprint Viewer.
- Data/platform team tạo export BigQuery qua Data Transfer Service.
- Kiểm tra tên bảng, dataset location, transfer status và backfill.
- Tạo read-only view cho kỹ sư nếu cần phân quyền theo project.

### Bước 3: tìm hotspots

- Chạy query theo tháng, project/service/region.
- Đánh dấu service và project tăng mạnh, kể cả nhóm project NULL.
- Đối chiếu chi phí, quota, instance count và usage metrics.
- Không chọn giảm resource chỉ dựa trên một biểu đồ carbon.

### Bước 4: tạo shortlist hành động

Ví dụ:

1. Đóng preview environments không có traffic trong 7 ngày.
2. Rightsize VM staging có CPU/memory thấp và không phục vụ lịch test.
3. Giảm min instances trên Cloud Run service có p99 cold start trong giới hạn.
4. Thêm lifecycle policy cho intermediate objects đã hết hạn giữ.
5. Partition BigQuery và sửa query full-scan trong pipeline analytics.

Mỗi hành động phải có owner, mức rủi ro, điều kiện rollback, phạm vi resource, dự báo chi phí và tác động carbon cần kiểm chứng.

### Bước 5: triển khai có kiểm soát

- Đo tải và SLO trước/sau.
- Canary hoặc stage trước khi thay production.
- Thực hiện rollback nếu error rate/latency/RTO-RPO vượt guardrail.
- Cập nhật resource inventory, chi phí và thay đổi kiến trúc.

### Bước 6: xác minh theo kỳ carbon đã chốt

Sau khi dữ liệu Carbon Footprint được xuất cho tháng đủ dữ liệu, so sánh tuyệt đối và intensity theo cùng phạm vi; ghi carbon_model_version, số liệu output và mọi confounder. Kết quả có thể chỉ khẳng định tính định hướng nếu attribution ở project bị pha trộn.

## 16. Troubleshooting Carbon Footprint

**Không tìm thấy Carbon Footprint trong Console.** Kiểm tra billing account đang chọn, quyền trên billing account, tình trạng dữ liệu và khu vực Tools; không chỉ xin thêm Project Viewer.

**Không có dữ liệu tháng trước.** Dữ liệu có thể trễ tới 21 ngày; kiểm tra lịch hoàn tất và transfer run. Không diễn giải tháng chưa có dữ liệu là footprint 0.

**BigQuery table chưa xuất hiện.** Kiểm tra dataset, BigQuery Data Transfer Service, transfer config, permission và data source enrollment nếu cấu hình ngoài Console. Đọc log của transfer run.

**Permission denied khi export.** Kiểm tra `billing.accounts.getCarbonInformation` ở billing account và `bigquery.transfers.update`/permission dự án đích, thay vì cấp Owner bừa bãi.

**Số liệu dashboard khác SQL.** Kiểm tra đơn vị tCO₂e vs kgCO₂e, lựa chọn location-based/market-based, billing account, kỳ tháng, các project NULL, query filter và dữ liệu backfill.

**Hai phương pháp cho tổng khác nhau.** Đó là khác biệt Scope 2 location-based/market-based, không phải lỗi do cộng sai; đối chiếu schema và methodology.

**Project đã xóa không còn tên.** Trường project.id có thể NULL; giữ nhóm unattributed để đối chiếu tổng thay vì bỏ dòng.

**Trường after_offsets toàn NULL.** Trường đã deprecated; chuyển sang tổng location-based hoặc market-based hiện hành.

**Một microservice không có số phát thải riêng.** Native export chỉ tới project/service/region/month; nếu cần resource-level estimate, join billing usage và phân bổ theo phương pháp đã công bố, dán nhãn approximation.

**CO₂e tăng dù đã giảm VM.** Kiểm tra growth traffic, service mix, thay đổi region, workload khác, model_version và tháng chưa so sánh tương đương.

**Chuyển region làm carbon giảm nhưng latency tăng.** Đánh giá lại SLO, data location, downstream egress và khả năng tài nguyên; không chấp nhận giảm footprint bằng cách phá yêu cầu người dùng.

## 17. Sai lầm phân tích thường gặp

1. **Gộp location-based và market-based thành một số tổng:** hai góc nhìn không được cộng.
2. **Cho rằng Carbon Footprint là công tơ từng VM:** đây là ước tính phân bổ theo shared cloud infrastructure.
3. **So sánh một tháng chưa có dữ liệu với tháng hoàn tất:** dữ liệu không đồng kỳ.
4. **Quên project.id NULL:** làm sai đối chiếu tổng billing account.
5. **Cộng Scope 1/2/3 của nhà cung cấp như Scope 1/2/3 của khách hàng:** nhầm ownership của kiểm kê khí nhà kính.
6. **Lấy chênh lệch model version làm thành tích tối ưu:** cần kiểm tra thay đổi phương pháp.
7. **Nhân đôi Carbon Footprint khi join nhiều billing rows:** cần aggregate đúng grain.
8. **Tối ưu cost rồi tuyên bố carbon giảm cùng tỷ lệ:** cost và CO₂e không tuyến tính.
9. **Chọn region chỉ dựa vào CFE%:** bỏ qua residency, cost, latency, network và HA.
10. **Xóa backup hoặc giảm HA để “xanh hơn”:** phá SLO/RPO/RTO.
11. **Bỏ qua vấn đề dữ liệu nhạy cảm trong dashboard:** billing và resource usage cần quyền truy cập hạn chế.
12. **Dùng từ “net zero” chỉ vì giá trị market-based thấp:** điều này không có nghĩa toàn bộ vòng đời workload không phát thải.

## 18. Checklist vận hành

### Đo lường

- [ ] Xác định billing account, project, dịch vụ và phạm vi workload.
- [ ] Hiểu Scope 1/2/3 của Google trong báo cáo, không nhầm scope doanh nghiệp.
- [ ] Lưu riêng location-based và market-based.
- [ ] Dùng đúng đơn vị kgCO₂e ở export và tCO₂e trong dashboard.
- [ ] Dùng kỳ tháng đã hoàn tất và ghi model_version.
- [ ] Tạo Carbon Footprint export vào BigQuery, xác nhận transfer hoàn tất.
- [ ] Không loại bỏ dự án NULL hoặc các khoản chưa phân bổ khi đối chiếu tổng.

### Phân tích và tối ưu

- [ ] Có absolute emissions và workload-normalized carbon intensity.
- [ ] KPI business output cùng thời gian, phạm vi và định nghĩa.
- [ ] Đã xác định hotspots theo project/service/region.
- [ ] Sử dụng cost-at-list/resource allocation chỉ khi ghi rõ approximation.
- [ ] Đánh giá region theo CFE%, carbon intensity, residency, latency, price.
- [ ] Đã xem xét idle/rightsizing/autoscaling/storage lifecycle/network.
- [ ] Mọi thay đổi có SLO, security, HA và cost guardrails.

### Quản trị

- [ ] Có data owner, FinOps/GreenOps lead và reviewer.
- [ ] IAM Carbon Footprint Viewer cấp ở billing account, BigQuery dataset có least privilege.
- [ ] Dữ liệu thô, derived views, version metric và báo cáo được quản lý riêng.
- [ ] Có runbook xử lý thiếu dữ liệu, transfer failure và methodology changes.
- [ ] Có baseline, phương pháp so sánh và kế hoạch rollback.
- [ ] Không dùng kết quả ước lượng resource-level như số đo kiểm kê chính thức chưa được phê duyệt.

## 19. Tài liệu tham khảo chính thức

- [Google Cloud Carbon Footprint](https://cloud.google.com/carbon-footprint)
- [View Carbon Footprint data](https://cloud.google.com/carbon-footprint/docs/view-carbon-data)
- [Carbon Footprint methodology](https://cloud.google.com/carbon-footprint/docs/methodology)
- [Carbon Footprint export to BigQuery](https://cloud.google.com/carbon-footprint/docs/export)
- [Carbon Footprint export data schema](https://cloud.google.com/carbon-footprint/docs/data-schema)
- [Carbon Footprint IAM roles](https://cloud.google.com/carbon-footprint/docs/iam)
- [Carbon Footprint API / BigQuery Data Transfer](https://cloud.google.com/carbon-footprint/docs/api)
- [Custom Carbon Footprint dashboard and resource attribution](https://cloud.google.com/carbon-footprint/docs/custom-dashboard)
- [Carbon Footprint release notes](https://cloud.google.com/carbon-footprint/docs/release-notes)
- [Carbon-free energy for Google Cloud regions](https://cloud.google.com/sustainability/region-carbon)
- [Sustainability: continuously measure and improve](https://cloud.google.com/architecture/framework/sustainability/continuously-measure-improve)
- [Sustainability: low-carbon regions](https://cloud.google.com/architecture/framework/sustainability/low-carbon-regions)
- [Cloud Billing export to BigQuery](https://cloud.google.com/billing/docs/how-to/export-data-bigquery)
- [Google Cloud Active Assist recommendations](https://cloud.google.com/recommender/docs/overview)

**Kết luận:** Carbon Footprint cung cấp một cơ sở định lượng để nhìn tác động môi trường ước tính của hoạt động Google Cloud, nhưng phải đọc đúng **ranh giới và phương pháp**. Hãy phân tích location-based và market-based tách biệt, dùng dữ liệu theo billing account/project/service/region/month, kết hợp KPI hiệu năng và business output, rồi ưu tiên loại bỏ tài nguyên không cần thiết, rightsizing, workload placement và tối ưu kiến trúc. Một quyết định GreenOps tốt cần giảm phát thải có bằng chứng mà vẫn giữ yêu cầu bảo mật, chất lượng dịch vụ, độ tin cậy và chi phí.
