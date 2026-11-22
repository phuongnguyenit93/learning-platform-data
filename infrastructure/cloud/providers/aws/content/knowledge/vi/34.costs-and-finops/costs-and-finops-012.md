# Unit economics, phát hiện chi phí bất thường và dọn tài nguyên

FinOps không dừng ở việc xem hóa đơn hoặc tìm cách giảm tổng chi phí AWS. Một tổ chức cần biết mỗi sản phẩm, khách hàng, giao dịch hoặc đơn vị công việc tiêu tốn bao nhiêu tài nguyên; nhận ra khi mức chi tiêu lệch khỏi hành vi bình thường; và loại bỏ capacity không còn tạo ra giá trị. Ba năng lực này liên kết với nhau: **unit economics** cho biết hiệu quả kinh tế của workload, **cost anomaly detection** phát hiện thay đổi bất thường, còn **resource cleanup** biến dữ liệu thành hành động vận hành.

Một hóa đơn tăng chưa chắc là vấn đề. Nếu số đơn hàng tăng nhanh hơn chi phí, chi phí trên mỗi đơn có thể đang giảm. Ngược lại, hóa đơn gần như không đổi vẫn có thể che giấu một dịch vụ tăng giá trong khi dịch vụ khác giảm. Vì vậy, cần xem chi phí cùng với sản lượng, chất lượng dịch vụ, mức sử dụng và trách nhiệm sở hữu.

Bài học này xây dựng cách đo chi phí theo đơn vị kinh doanh, phân bổ chi phí dùng chung, cấu hình AWS Cost Anomaly Detection, điều tra nguyên nhân và dọn tài nguyên an toàn. Các công cụ như AWS Cost Explorer, Cost and Usage Reports, Cost Categories, AWS Budgets, AWS Compute Optimizer và Cost Optimization Hub được đặt vào cùng một quy trình FinOps.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích unit economics và chọn mẫu số phù hợp như đơn hàng, giao dịch thành công, active user, tenant hoặc request.
- Xây dựng numerator chi phí nhất quán từ direct cost, shared cost và các khoản phân bổ.
- Dùng cost allocation tags, Cost Categories, Cost Explorer và Cost and Usage Reports để phân tích chi phí theo trách nhiệm.
- Phân biệt unblended, net unblended, amortized và net amortized cost khi đo hiệu quả.
- Cấu hình monitor và alert subscription cho AWS Cost Anomaly Detection.
- Phân biệt anomaly detection với AWS Budgets và xử lý giới hạn về độ trễ, lịch sử và phạm vi giám sát.
- Điều tra anomaly theo service, account, Region và usage type; phối hợp dữ liệu billing với thay đổi kỹ thuật.
- Sử dụng Compute Optimizer và Cost Optimization Hub để tìm tài nguyên idle hoặc cần rightsizing.
- Thiết kế quy trình inventory, xác nhận owner, bảo vệ dữ liệu, stop/quarantine và delete tài nguyên.
- Đo savings thực tế và đưa kết quả trở lại vòng lặp FinOps.

## 2. Unit economics trong môi trường AWS

### 2.1 Khái niệm

Unit economics mô tả chi phí và giá trị kinh tế gắn với một đơn vị đầu ra của sản phẩm hoặc workload. Thay vì chỉ hỏi “tháng này AWS tốn bao nhiêu?”, đội sản phẩm và kỹ thuật cần trả lời:

- Một đơn hàng hoàn tất tốn bao nhiêu chi phí hạ tầng?
- Một active user mỗi tháng tạo ra bao nhiêu chi phí?
- Một tenant sử dụng nền tảng nhiều hơn mức trung bình bao nhiêu?
- Một request thành công hoặc một tác vụ xử lý dữ liệu tiêu tốn bao nhiêu?
- Khi tăng số khách hàng, chi phí trên mỗi khách hàng giảm hay tăng?

Một chỉ số đơn giản:

\[
\text{Unit cost} = \frac{\text{Chi phí được phân bổ cho workload}}{\text{Số đơn vị đầu ra}}
\]

Ví dụ, một ứng dụng chi 18.000 USD trong tháng và hoàn tất 120.000 đơn hàng:

\[
\frac{18.000}{120.000} = 0,15\text{ USD/đơn hàng}
\]

Tháng tiếp theo chi phí tăng lên 21.000 USD nhưng số đơn hàng tăng lên 150.000:

\[
\frac{21.000}{150.000} = 0,14\text{ USD/đơn hàng}
\]

Tổng chi phí tăng 16,7%, nhưng sản lượng tăng 25% và unit cost giảm khoảng 6,7%. Nếu chỉ nhìn tổng hóa đơn, đội vận hành có thể kết luận sai rằng hiệu quả đã xấu đi.

### 2.2 Chọn đúng đơn vị đầu ra

Mẫu số phải phản ánh giá trị mà sản phẩm cung cấp, có thể đo ổn định và không bị thao túng bởi cách triển khai kỹ thuật.

| Loại workload | Unit economics phù hợp | Mẫu số cần tránh |
|---|---|---|
| Thương mại điện tử | Chi phí trên đơn hàng hoàn tất, trên giao dịch thanh toán thành công | Tổng số lượt xem trang nếu mục tiêu là đơn hàng |
| SaaS nhiều tenant | Chi phí trên tenant hoạt động, trên user hoạt động, trên request thành công | Tổng tenant đã đăng ký nhưng không sử dụng |
| API platform | Chi phí trên 1.000 request thành công hoặc theo API product | Tổng request gồm retry nội bộ không tạo giá trị |
| Data platform | Chi phí trên TB xử lý, pipeline thành công hoặc bảng dữ liệu được phục vụ | Chỉ tính số job đã khởi chạy dù job thất bại |
| Machine learning | Chi phí trên 1.000 inference, token hoặc training run hoàn tất | Tổng invocation không phân biệt output hữu ích |
| Media processing | Chi phí trên phút video, GB media hoặc asset hoàn tất | Tổng byte upload chưa được xử lý |
| Internal developer platform | Chi phí trên workload/team/project được phục vụ | Số tài khoản IAM hoặc số người được cấp quyền |

Một sản phẩm có thể cần nhiều chỉ số song song. Ví dụ API platform theo dõi cost/request, cost/1.000 request thành công và cost/tenant để phân biệt hiệu quả kỹ thuật với mức tiêu thụ của khách hàng.

### 2.3 Xác định phạm vi chi phí

Numerator cần nhất quán qua các kỳ. Một mô hình đầy đủ có thể gồm:

    Workload cost
      = direct infrastructure cost
      + allocated shared platform cost
      + allocated network and security cost
      + allocated observability and backup cost
      + applicable software/license cost

Direct cost là khoản có thể gắn trực tiếp với workload, chẳng hạn EC2 instance riêng, database riêng hoặc S3 bucket có owner rõ. Shared cost là khoản phục vụ nhiều workload, chẳng hạn NAT Gateway, transit network, logging platform, shared Kubernetes cluster, support plan hoặc đội vận hành nền tảng.

Không phải báo cáo unit economics nào cũng cần đưa toàn bộ chi phí doanh nghiệp vào numerator. Hãy công bố ranh giới:

- **Infrastructure unit cost:** chỉ tính dịch vụ AWS và chi phí nền tảng trực tiếp.
- **Platform unit cost:** thêm phần chi phí shared platform được phân bổ.
- **Fully loaded unit cost:** thêm software license, support, chi phí vận hành và các khoản overhead theo chính sách tài chính.

Nếu một dashboard tháng này dùng net amortized cost nhưng dashboard tháng trước dùng unblended cost, xu hướng có thể thay đổi do cách ghi nhận commitment chứ không phải do workload. Ghi rõ cost basis trong tên chỉ số hoặc metadata.

### 2.4 Chọn cost basis phù hợp

Cost Explorer cung cấp nhiều cost metric:

| Cost basis | Ý nghĩa | Khi dùng |
|---|---|---|
| Unblended cost | Chi phí usage theo giá trị unblended; reservation fee/discount có thể xuất hiện thành line item riêng | Phân tích line item và đối chiếu usage/charge |
| Net unblended cost | Chi phí sau các discount áp dụng | Theo dõi mức chi tiêu sau discount; Cost Anomaly Detection dùng dữ liệu net unblended |
| Amortized cost | Phân bổ upfront và recurring reservation fee theo thời gian sử dụng của commitment | So sánh chi phí workload qua các kỳ có RI/Savings Plans |
| Net amortized cost | Chi phí commitment đã amortize và phản ánh discount áp dụng | Unit economics và benchmark hiệu quả sau discount |

Không có một cost basis đúng cho mọi báo cáo. Kế toán có thể cần đối chiếu invoice/cash timing; FinOps cần phân bổ commitment để nhìn effective cost; anomaly monitor dùng net unblended theo mô hình của AWS. Khi so sánh, hãy dùng cùng cost basis, time range, filter, currency và treatment cho credit/refund/tax.

### 2.5 Phân biệt fixed cost và variable cost

- **Fixed cost** tương đối ổn định trong một khoảng thời gian, ví dụ baseline EC2, database provisioned, cluster control plane hoặc một số endpoint.
- **Variable cost** thay đổi theo usage, ví dụ request, data transfer, GB processed, log ingestion, I/O hoặc storage growth.
- **Step cost** tăng theo ngưỡng capacity, ví dụ phải thêm node, shard, replica hoặc NAT Gateway khi tải vượt mức.

Tách ba loại giúp dự đoán hành vi khi sản lượng tăng. Nếu fixed cost cao nhưng variable cost thấp, unit cost thường giảm khi quy mô tăng. Nếu variable cost tăng nhanh hơn sản lượng, unit economics có thể xấu đi do data transfer, retry, log volume hoặc query pattern.

## 3. Thu thập và phân bổ dữ liệu chi phí

### 3.1 Cost allocation tags

Tag là cặp key/value gắn vào AWS resource. Một bộ tag có cấu trúc giúp phân bổ chi phí theo sản phẩm, môi trường, owner và cost center:

| Tag key | Ví dụ value | Mục đích |
|---|---|---|
| Application | commerce-api | Sản phẩm hoặc workload |
| Environment | production, staging, dev | Phân biệt môi trường |
| Owner | team-payments | Đội chịu trách nhiệm |
| CostCenter | CC-1042 | Đối chiếu tài chính |
| BusinessUnit | retail | Phân bổ theo đơn vị kinh doanh |
| DataClass | critical, internal | Gợi ý retention và kiểm soát |
| Lifecycle | ephemeral, persistent | Hỗ trợ quy trình cleanup |

AWS có AWS-generated cost allocation tags và user-defined cost allocation tags. Cả hai loại phải được kích hoạt riêng trong Billing and Cost Management trước khi xuất hiện trong Cost Explorer hoặc cost allocation report. Sau khi gắn/kích hoạt, tag có thể mất đến 24 giờ để xuất hiện trong Billing console.

Cost allocation report bao gồm cả chi phí của tài nguyên có tag và không có tag; cuối billing cycle, tổng chi phí trên báo cáo phải đối chiếu với tổng trên Bills page và các báo cáo billing cùng kỳ. Tài nguyên không có tag không biến mất khỏi tổng; chúng nằm trong phần chưa phân bổ. Không đưa dữ liệu nhạy cảm, PII hoặc secret vào tag.

Một lỗi thường gặp là gắn tag nhưng quên activate cost allocation tag. Khi đó, tag có thể nhìn thấy trên resource nhưng chưa xuất hiện trong Cost Explorer như một dimension phân bổ chi phí. Hãy quản lý cả tagging policy lẫn bước activate trong Billing.

### 3.2 Cost Categories

Cost Categories ánh xạ line item chi phí thành nhóm kinh doanh bằng rule. Các dimension có thể dùng để phân loại gồm:

- AWS account.
- Cost allocation tag.
- Charge type như credit, refund hoặc reservation fee.
- Service.
- Region.
- Usage type.
- Billing entity như AWS hoặc AWS Marketplace.

Rule được đánh giá theo thứ tự. Nếu một line item khớp nhiều rule, rule khớp đầu tiên quyết định category value. Nên đặt rule cụ thể trước rule tổng quát và khai báo default value để không bỏ lại các khoản chưa khớp.

Ví dụ tổ chức có ba nhóm Engineering, Marketing và Operations. Chi phí có tag Application=commerce-api hoặc Application=payments có thể được xếp vào Engineering; Application=campaign-site vào Marketing; phần còn lại vào Operations. Một category có thể tạo phân cấp theo business unit, application hoặc cost center.

### 3.3 Phân bổ shared cost

Không phải mọi khoản đều gắn trực tiếp với một team. Chi phí shared network, logging, security tooling hoặc platform cluster cần một driver phân bổ có thể giải thích:

| Shared cost | Driver phân bổ gợi ý |
|---|---|
| Shared NAT/data transfer | GB processed hoặc bytes theo workload |
| Shared Kubernetes cluster | vCPU-hours, memory GB-hours hoặc namespace request |
| Central logging | GB log ingest hoặc retained GB-month |
| Shared database | Query units, connection time hoặc storage consumed |
| Internal platform team | Số workload được phục vụ hoặc mức tiêu thụ capacity |
| Support plan | Tỷ trọng chi phí AWS theo policy tài chính |

Không mặc định chia đều khi mức tiêu thụ khác nhau. Nếu một team tạo 70% log volume, phân bổ 70% chi phí logging theo GB ingest thường phản ánh quan hệ nhân quả tốt hơn chia đều cho năm team.

Cost Categories hỗ trợ split charge rules cho shared cost. Các phương pháp gồm:

- **Proportional:** phân bổ theo tỷ trọng chi phí của từng target.
- **Fixed:** phân bổ theo tỷ lệ phần trăm do tổ chức chỉ định.
- **Even split:** chia đều cho các target.

Lưu ý quan trọng: split charge được thể hiện trên trang chi tiết Cost Categories. Các khoản phân bổ này không xuất hiện và không làm thay đổi dữ liệu trong Cost Explorer, Cost and Usage Reports hoặc các công cụ AWS Cost Management khác. Hãy dùng chúng như một lớp phân bổ quản trị; nếu cần unit economics ở mức line item, hãy thực hiện allocation trong data pipeline/reporting riêng.

### 3.4 Cost Explorer và Cost and Usage Reports

Cost Explorer phù hợp để xem xu hướng và phân tích tương tác theo service, account, Region, usage type, tag và cost category. Đây là nơi bắt đầu điều tra một khoản tăng bất thường.

AWS Cost and Usage Reports (CUR) cung cấp dữ liệu chi phí/usage chi tiết hơn và được giao vào S3. Report có thể chọn hourly, daily hoặc monthly granularity, chia theo product/resource và tag. AWS cập nhật report ít nhất mỗi ngày; một report mới có thể mất đến 24 giờ để xuất hiện lần đầu. File cập nhật trong tháng có tính cumulative và được điều chỉnh cho đến khi charge được finalized.

Với phân tích unit economics, có thể dùng Athena hoặc công cụ BI để join CUR với dữ liệu sản phẩm:

    AWS CUR / Data Exports
          |
          +---- cost, usage type, account, Region, tag
          |
    Product analytics / order ledger / tenant usage
          |
          +---- order_id, tenant_id, request_count, success_count
          |
    Allocation model
          |
    Unit cost by product / tenant / business unit

Không join chi phí với dữ liệu sản phẩm chỉ bằng ngày nếu workload có nhiều Region, account hoặc môi trường. Dùng các key như account, Region, resource tag, usage type và time window để giảm nhầm lẫn.

### 3.5 Chuẩn hóa dữ liệu trước khi tính

Trước khi tính unit cost:

1. Chọn cost basis thống nhất.
2. Chọn time window có cùng timezone và ranh giới kỳ.
3. Xác định cách xử lý credit, refund, tax, support và Marketplace.
4. Xác định cách phân bổ shared cost.
5. Kiểm tra tag coverage và phần chi phí chưa phân bổ.
6. Dùng denominator từ hệ thống nghiệp vụ đã reconcile.
7. Ghi rõ dữ liệu nào là estimate, provisional hay finalized.

Một số usage/cost line item có thể cập nhật sau thời điểm phát sinh. Đừng coi số liệu ngày hiện tại là số cuối cùng để chốt unit economics tháng. Dùng cùng mức độ finality khi so sánh các kỳ.

## 4. Xây dựng chỉ số unit economics

### 4.1 Cost per transaction

Ví dụ một hệ thống thanh toán có chi phí tháng:

| Thành phần | Chi phí |
|---|---:|
| EC2/ECS application | 4.000 USD |
| RDS/Aurora | 3.500 USD |
| Network/NAT/ALB | 1.200 USD |
| S3/backup | 500 USD |
| Logs/metrics/security | 800 USD |
| Shared platform allocation | 1.000 USD |
| **Tổng** | **11.000 USD** |

Nếu có 2.000.000 giao dịch thành công:

\[
\text{Cost per transaction} = \frac{11.000}{2.000.000} = 0,0055\text{ USD}
\]

Nếu denominator dùng tất cả request gồm retry và thất bại, chỉ số có thể thấp giả tạo vì mẫu số tăng mà giá trị kinh doanh không tăng. Hãy đo riêng:

- Cost per attempted transaction.
- Cost per successful transaction.
- Cost per failed transaction nếu cần phân tích lãng phí.

### 4.2 Cost per tenant

SaaS nhiều tenant thường có shared platform. Tổng chi phí tháng có thể gồm:

    Total cost = direct tenant cost + shared platform cost

Ví dụ:

- Chi phí riêng theo tenant: 6.000 USD.
- Chi phí shared platform: 9.000 USD.
- Có 300 tenant active.

Nếu chia đều shared cost:

    Shared cost per tenant = 9.000 / 300 = 30 USD

Tenant có workload riêng 12 USD sẽ có fully allocated cost 42 USD. Tuy nhiên, chia đều chỉ hợp lý nếu mỗi tenant tiêu thụ gần tương đương. Nếu mức sử dụng khác biệt, có thể phân bổ theo request, storage, vCPU-hours hoặc data egress.

Không nên sử dụng một driver duy nhất cho mọi shared cost. Ví dụ logging phân bổ theo GB ingest, network theo GB transfer và control plane theo workload count có thể hợp lý hơn một tỷ lệ cố định cho tất cả.

### 4.3 Cost per active user

    Cost per active user = total allocated workload cost / monthly active users

Phải định nghĩa active user rõ ràng: người đăng nhập, người thực hiện ít nhất một hành động có giá trị hay người tạo giao dịch? Nếu thay đổi định nghĩa giữa các tháng, xu hướng sẽ không còn so sánh được.

Với sản phẩm freemium, nên theo dõi cả cost per active user và cost per paying user. Nếu user miễn phí sử dụng nhiều compute nhưng không chuyển đổi, chỉ số cost per paying user có thể tăng dù cost per active user ổn định.

### 4.4 Contribution margin và giá bán

Unit economics có thể kết hợp chi phí hạ tầng với doanh thu:

\[
\text{Contribution margin per unit} =
\text{Revenue per unit} - \text{Variable cost per unit}
\]

AWS cost thường chỉ là một phần variable cost. Nếu muốn fully loaded margin, phải cộng payment processing, support, license, customer success và các chi phí khác theo chính sách tài chính. Đừng gọi AWS cost per order là gross margin nếu numerator chỉ chứa hạ tầng.

### 4.5 Đánh giá xu hướng

Theo dõi đồng thời:

- Total spend.
- Output volume.
- Unit cost.
- Service availability/latency/error rate.
- Capacity headroom.
- Cost allocation coverage.

Unit cost giảm nhưng error rate tăng hoặc latency vượt SLO không phải tối ưu thành công. Một thay đổi làm giảm instance size nhưng khiến retry tăng có thể làm chi phí request thực tế cao hơn.

### 4.6 Mô hình dashboard

Một dashboard FinOps cấp sản phẩm có thể gồm:

| Nhóm | KPI |
|---|---|
| Spend | Net amortized cost, actual month-to-date, forecast cuối tháng |
| Unit economics | Cost/order, cost/active tenant, cost/1.000 request |
| Efficiency | CPU/memory utilization, cache hit ratio, request per vCPU-hour |
| Reliability | Availability, latency p95/p99, error rate, restore readiness |
| Allocation | % tagged cost, unallocated cost, shared cost by driver |
| Optimization | Estimated savings, realized savings, pending recommendations |
| Anomaly | Anomaly count, impact USD, time-to-detect, time-to-triage |

Đặt owner cho từng KPI. Nếu unit cost tăng, owner sản phẩm cần xác nhận sản lượng; owner nền tảng cần kiểm tra capacity/network; FinOps cần xác nhận cost basis và allocation.

## 5. AWS Cost Anomaly Detection

### 5.1 Chức năng

AWS Cost Anomaly Detection sử dụng mô hình machine learning để nhận diện mức chi tiêu khác thường so với pattern lịch sử. Mô hình có thể xem xét seasonality theo tuần/tháng và xu hướng tăng trưởng tự nhiên nhằm giảm false positive.

Anomaly không có nghĩa là đã xảy ra lỗi hoặc bị tấn công. Một chiến dịch marketing, release mới, migration, tăng traffic hoặc bật thêm Region có thể tạo ra một thay đổi chi phí hợp lệ. Detection chỉ báo rằng spend khác pattern dự kiến; đội vận hành phải xác định nguyên nhân và quyết định hành động.

Cost Anomaly Detection phân tích net unblended cost data. Sau khi billing data được xử lý, dịch vụ chạy khoảng ba lần mỗi ngày. Cost Explorer có thể trễ đến 24 giờ, vì vậy anomaly có thể được phát hiện sau usage tối đa khoảng 24 giờ. Monitor mới có thể cần đến 24 giờ mới bắt đầu detect; một service subscription mới cần 10 ngày historical usage data cho service đó trước khi phát hiện anomaly.

Đây không phải công cụ chặn chi tiêu, rate limiter hay alert real-time theo từng API call.

### 5.2 Điều kiện và phạm vi

Cost Anomaly Detection là tính năng trong Cost Explorer, do đó cần bật Cost Explorer và cấp IAM permission thích hợp. Cost monitors và alert subscriptions được quản lý trong account tạo chúng. Monitor cho linked accounts, cost allocation tags và cost categories chỉ được tạo từ management account theo mô hình AWS Organizations.

Cost Anomaly Detection không giám sát third-party product/service thông thường trong AWS Marketplace, ngoại trừ third-party foundation models trên Amazon Bedrock. Để theo dõi Marketplace charge, dùng AWS Budgets với Billing Entity filter hoặc phân tích billing data riêng.

### 5.3 AWS managed monitor và customer managed monitor

AWS hiện có hai phương thức monitor:

| Monitor | Cách hoạt động | Khi phù hợp |
|---|---|---|
| AWS managed | Tự động theo dõi tất cả giá trị trong dimension được chọn và tự bao gồm account/tag/category mới | Cần coverage rộng và ít công bảo trì |
| Customer managed | Chọn các giá trị cụ thể, tối đa 10 account hoặc tag value cho một monitor | Cần giám sát một nhóm nhỏ hoặc cấu hình threshold/nhóm riêng |

Các dimension chính:

- AWS services.
- Linked accounts.
- Cost allocation tags.
- Cost Categories.

AWS managed monitor có thể theo dõi tối đa 5.000 giá trị trong một dimension; nếu nhiều hơn, monitor theo dõi 5.000 giá trị có tổng spend cao nhất. Customer managed monitor cho phép chọn tối đa 10 giá trị theo dimension được hỗ trợ. Customer managed AWS services monitor không được hỗ trợ.

AWS managed monitor phù hợp với coverage toàn tổ chức. Customer managed monitor phù hợp với nhóm dự án, account production trọng yếu hoặc team cần threshold riêng. Tránh tạo nhiều monitor chồng lấn trên cùng dimension nếu chúng tạo cảnh báo trùng lặp.

Alert subscription gắn với AWS managed monitor dùng cùng threshold cho mọi giá trị được monitor. Nếu cần định tuyến thông báo khác nhau theo từng account/tag value, có thể dùng AWS User Notifications với JSON filtering patterns.

### 5.4 Alert subscription và threshold

Sau khi tạo monitor, gắn ít nhất một alert subscription để chỉ định người nhận và kênh thông báo.

Các lựa chọn frequency:

- **Individual alerts:** gửi khi anomaly được phát hiện; cần Amazon SNS topic.
- **Daily summaries:** email tổng hợp top 10 anomaly của ngày trước, sắp theo cost impact.
- **Weekly summaries:** email tổng hợp các anomaly trong tuần.

Threshold điều khiển việc gửi alert, không điều khiển việc mô hình phát hiện anomaly. Có hai loại:

- **Absolute threshold:** gửi khi total cost impact đạt hoặc vượt một số USD.
- **Percentage threshold:** gửi khi total impact percentage đạt hoặc vượt tỷ lệ đã đặt.

Có thể kết hợp hai threshold bằng AND hoặc OR. Các anomaly thấp hơn threshold vẫn được ghi nhận trong Detected anomalies; chỉ việc gửi thông báo bị lọc theo threshold.

Ví dụ, nhóm FinOps muốn nhận cảnh báo khi impact vượt 500 USD hoặc impact percentage vượt 100%. Nhóm có thể cấu hình hai threshold kết hợp OR để không bỏ qua anomaly lớn theo giá trị tuyệt đối hoặc anomaly tăng mạnh trên một workload có baseline nhỏ.

### 5.5 Root cause analysis

Anomaly detail có thể xếp hạng root cause theo mức đóng góp USD qua bốn dimension:

- AWS service.
- AWS account.
- Region.
- Usage type.

Thông tin thường gồm expected spend, actual spend, total impact, impact percentage, duration, monitor và anomaly details link. Severity phản ánh mức độ bất thường so với pattern lịch sử, không chỉ dựa vào số USD tuyệt đối.

Ví dụ:

| Dimension | Giá trị |
|---|---|
| Service | Amazon EC2 |
| Account | production |
| Region | ap-southeast-1 |
| Usage type | BoxUsage:m7i.large |
| Expected spend | 300 USD |
| Actual spend | 1.300 USD |
| Total impact | 1.000 USD |
| Impact percentage | 333,3% |

Đây là ví dụ minh họa cách đọc anomaly. Root cause chỉ cho biết dimension có đóng góp lớn; vẫn phải kiểm tra resource ID, deployment, CloudTrail và metric để xác định nguyên nhân cụ thể.

### 5.6 EventBridge integration

Cost Anomaly Detection tích hợp EventBridge. Rule có thể bắt event Anomaly Detected từ source aws.ce rồi gửi đến SNS, Lambda, workflow incident hoặc hệ thống thông báo nội bộ. Event có thể chứa anomaly ID, monitor ARN, impact, root cause, account, Region, service, usage type và anomaly details link.

Một luồng xử lý phù hợp:

    Cost Anomaly Detection
             |
         EventBridge
             |
      Filter by impact/severity
             |
        SNS / Lambda
             |
       FinOps incident
             |
    Triage + owner + action

EventBridge giúp điều phối thông báo và workflow. Không nên để rule tự động terminate resource chỉ vì anomaly xuất hiện; cần lớp kiểm tra owner, resource state, data protection và approval.

## 6. Phân biệt anomaly detection, budgets và cost monitoring

| Công cụ | Câu hỏi chính | Cơ chế |
|---|---|---|
| Cost Anomaly Detection | Chi tiêu có lệch khỏi pattern lịch sử không? | Machine learning, seasonality và root cause |
| AWS Budgets | Chi tiêu/usage có chạm ngưỡng đã đặt hoặc forecast vượt ngưỡng không? | Threshold actual hoặc forecast |
| Cost Explorer | Chi phí đến từ đâu và thay đổi thế nào? | Phân tích lịch sử theo dimension/filter |
| CUR/Data Exports | Line item nào tạo ra cost/usage? | Dữ liệu chi tiết để query và reconcile |
| CloudWatch | Ứng dụng/tài nguyên có metric bất thường không? | Metrics, logs, alarms |
| Compute Optimizer | Tài nguyên có dư capacity hoặc idle không? | Phân tích utilization và recommendation |

AWS Budgets có thể cảnh báo actual spend hoặc forecasted spend khi vượt một giá trị USD hay tỷ lệ budget. Budget thường phù hợp với giới hạn ngân sách cố định, trong khi Cost Anomaly Detection phù hợp với thay đổi khác thường so với baseline. Dùng cả hai:

- Budget kiểm soát hạn mức theo tháng/quý/năm.
- Anomaly Detection tìm spike không mong đợi.
- Cost Explorer/CUR xác định service, usage type và line item.
- CloudWatch/CloudTrail xác định thay đổi runtime và người thực hiện.

Không coi budget alert là phát hiện nguyên nhân. Một account có thể vượt budget vì kế hoạch tăng trưởng đã được phê duyệt; một anomaly có thể xảy ra nhưng vẫn nằm dưới budget tổng.

## 7. Quy trình điều tra cost anomaly

### 7.1 Bước 1: xác nhận tín hiệu

Khi nhận alert:

1. Mở anomaly details link.
2. Xác nhận thời gian bắt đầu, thời gian kết thúc và trạng thái ongoing/resolved.
3. Kiểm tra expected spend, actual spend, total impact và impact percentage.
4. Kiểm tra monitor type, account, service, Region và usage type.
5. Kiểm tra xem thay đổi có nằm trong release, migration, campaign hoặc kế hoạch capacity đã duyệt không.

Nếu cost data mới đang được xử lý, không kết luận từ một biểu đồ tạm thời. So sánh các kỳ có cùng cost basis và kiểm tra lại khi billing data được cập nhật.

### 7.2 Bước 2: phân tích root cause

Sử dụng Cost Explorer để filter theo:

- Service và usage type.
- Linked account.
- Region và Availability Zone nếu phù hợp.
- Cost allocation tag hoặc Cost Category.
- Operation, charge type và resource nếu dữ liệu hỗ trợ.

So sánh ngày anomaly với ngày trước đó, cùng thứ trong tuần và các chu kỳ tương tự. Xem chi phí tăng do quantity, rate, resource count, data transfer, request, storage, commitment hay credit/refund.

### 7.3 Bước 3: đối chiếu thay đổi kỹ thuật

Kết hợp:

- CloudTrail để tìm API create/modify/scale/launch.
- Deployment log, pipeline release và change request.
- CloudWatch metrics về CPU, request, concurrency, bytes, queue depth và errors.
- Application log để tìm retry loop, bot traffic hoặc query tăng đột biến.
- Tag/owner để xác định team phụ trách.
- CUR/Data Exports để tìm usage type, operation và resource-level cost.

Một anomaly EC2 có thể đến từ autoscaling, instance family mới, môi trường test bị bỏ quên hoặc cryptomining. Một anomaly NAT có thể đến từ data transfer, retry hoặc traffic đi sai route. Một anomaly CloudWatch có thể do log volume tăng, retention không giới hạn hoặc custom metric cardinality tăng.

### 7.4 Bước 4: phân loại nguyên nhân

| Nhóm nguyên nhân | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Tăng trưởng hợp lệ | Request/order/user tăng cùng kỳ campaign | Cập nhật forecast và unit economics |
| Thay đổi kiến trúc | Thêm Region, replica, Multi-AZ hoặc migration | Xác nhận business case và estimate mới |
| Lỗi cấu hình | Instance lớn hơn, NAT dư, log retention sai | Sửa cấu hình và kiểm tra regression |
| Lỗi ứng dụng | Retry loop, cache miss, query scan, runaway job | Rollback/fix code và giới hạn workload |
| Lạm dụng hoặc compromise | Resource lạ, Region mới, GPU/compute tăng bất thường | Kích hoạt incident security, bảo toàn evidence và cô lập theo runbook |
| Billing/data issue | Cost report bất thường nhưng usage metric không đổi | Kiểm tra AWS Health/Support và chờ dữ liệu xác nhận |

### 7.5 Bước 5: giảm tác động và theo dõi

Chọn hành động theo nguyên nhân:

- Dừng job batch sai hoặc giới hạn concurrency.
- Scale down workload tạm thời theo capacity plan.
- Gỡ resource đã xác nhận không còn dùng.
- Chặn request abuse hoặc sửa retry/backoff.
- Cập nhật route/cache để giảm data processing.
- Escalate security incident nếu có dấu hiệu compromise.

Không tắt database, NAT, endpoint hoặc instance chỉ vì chi phí cao. Hãy kiểm tra phụ thuộc, RTO, DR, data durability và owner trước khi thay đổi. Sau khi xử lý, theo dõi spend và application metric để xác nhận anomaly đã kết thúc.

### 7.6 Bước 6: ghi nhận và cải thiện

Mỗi anomaly cần một record:

| Trường | Nội dung |
|---|---|
| Anomaly ID | ID từ Cost Anomaly Detection |
| Owner | Team xử lý |
| Root cause | Service/account/Region/usage type và nguyên nhân đã xác nhận |
| Business context | Release, campaign, migration hoặc incident |
| Cost impact | USD và phần trăm |
| Action | Thay đổi đã thực hiện |
| Realized savings | Chi phí thực tế giảm sau hành động, nếu có |
| Prevention | Budget, alarm, quota, tag, guardrail hoặc test bổ sung |

Gửi feedback assessment phù hợp trên anomaly detail khi có thể xác nhận anomaly là chính xác hay không phải vấn đề. Feedback giúp cải thiện hệ thống phát hiện.

## 8. Tìm cơ hội tối ưu bằng Compute Optimizer và Cost Optimization Hub

### 8.1 AWS Compute Optimizer

Compute Optimizer phân tích cấu hình và utilization metric để đưa ra rightsizing hoặc idle resource recommendations. Recommendation là gợi ý dựa trên dữ liệu lịch sử; nó không tự hiểu mọi kế hoạch kinh doanh, seasonality hoặc workload tương lai.

Các recommendation idle hiện hỗ trợ nhiều nhóm resource:

- EC2 instances và EC2 Auto Scaling groups.
- EBS volumes.
- ECS services chạy trên Fargate.
- Aurora và RDS databases.
- NAT Gateway.
- DynamoDB provisioned tables.
- ElastiCache, MemoryDB và DocumentDB.
- WorkSpaces.
- SageMaker endpoints.

Recommendation được refresh hằng ngày. Lookback mặc định thường là 14 ngày; có ngoại lệ như EBS/NAT attachment status dùng 32 ngày và WorkSpaces connection activity dùng 63 ngày. Với một số resource như ElastiCache, recommendation có thể xuất hiện trễ sau khi bật Compute Optimizer.

Idle criteria khác nhau theo loại resource. Ví dụ:

- EC2 idle có thể được đánh giá qua peak CPU và network I/O trong lookback period.
- EBS unattached được xác định theo attachment status, còn idle volume dựa trên read/write activity.
- Fargate service cần xem CPU và memory.
- RDS/Aurora cần xem database connection, CPU và IOPS.
- NAT Gateway cần kiểm tra trạng thái, route table association và packet/connection activity.

Không dùng một ngưỡng CPU duy nhất để kết luận mọi resource không còn giá trị.

### 8.2 Rightsizing recommendation

Compute Optimizer có thể đề xuất thay đổi instance type/size, EBS volume, ECS service hoặc RDS DB instance. Với EC2, recommendation có thể dựa trên CPU, memory nếu có metric, network, disk và workload pattern. Memory metric cần được cung cấp qua CloudWatch Agent hoặc nguồn metric được hỗ trợ.

Lookback period có thể chọn 14 ngày, 32 ngày hoặc 93 ngày. 14/32 ngày không phát sinh phí bổ sung; 93 ngày cần Enhanced Infrastructure Metrics trả phí. Nếu workload có chu kỳ cuối tháng, 32 ngày có thể phản ánh pattern tốt hơn 14 ngày.

Đừng chỉ nhìn average CPU. Kiểm tra peak/p95/p99, memory, network, EBS throughput, queue depth, latency, burstable CPU credit và thời gian batch. Một instance có CPU thấp trong phần lớn thời gian nhưng cần peak cao trong giờ thanh toán có thể không phù hợp để downsize mạnh.

### 8.3 AWS Cost Optimization Hub

Cost Optimization Hub tổng hợp và ưu tiên recommendation từ nhiều account và Region. Các nhóm recommendation gồm rightsizing, idle resource deletion, Savings Plans và Reserved Instances. Hub tính estimated savings theo commercial terms cụ thể như RI/Savings Plans và có cơ chế deduplicate các recommendation chồng lấn để không cộng savings hai lần.

Ví dụ, một EC2 instance có thể vừa được đề xuất stop vì idle vừa được đề xuất rightsizing. Không thể vừa stop instance vừa tiết kiệm thêm bằng rightsizing trên cùng thời gian. Cost Optimization Hub chọn hành động có lợi hơn trong phép tính aggregate thay vì cộng cả hai savings.

Hub refresh recommendation hằng ngày và có thể cần đến 24 giờ để import đầy đủ sau khi bật. Khi dùng Organizations, management account có thể bật coverage cho member accounts.

Tính năng mới cần lưu ý: từ 17-11-2026, Cost Optimization Hub cho phép stop idle EC2 instance ngay từ trang Savings opportunities. Hành động stop dùng quyền của người thao tác và có màn hình xác nhận hiển thị dữ liệu mất đi và chi phí vẫn tiếp tục. Cần bật Cost Optimization Hub và Compute Optimizer để có idle recommendations.

### 8.4 Đọc savings estimate đúng cách

Estimated monthly savings là tiềm năng ước tính, không phải khoản tiết kiệm đã thực hiện. Giá trị có thể dựa trên On-Demand hoặc after-discount pricing tùy savings estimation preference và loại resource. Cost Optimization Hub giúp tính đến RI/Savings Plans hiện có và deduplicate recommendation, nhưng actual savings vẫn phụ thuộc usage sau thay đổi.

Đo realized savings bằng cách so sánh chi phí trước/sau đã normalize theo sản lượng, thời gian, Region, discount và thay đổi kiến trúc. Nếu traffic giảm 40% trong tháng sau khi rightsize, không thể gán toàn bộ bill giảm cho hành động rightsize.

## 9. Quy trình dọn tài nguyên an toàn

### 9.1 Nguyên tắc

Cleanup phải dựa trên inventory, owner, dependency và chính sách dữ liệu. Một resource không có traffic trong 14 ngày chưa chắc là vô dụng: nó có thể là DR standby, hệ thống cuối tháng, môi trường kiểm thử theo quý hoặc tài nguyên phục vụ forensic/compliance.

Dùng quy trình:

    Discover
       |
    Identify owner and purpose
       |
    Check metrics, dependencies and schedule
       |
    Confirm backup / retention / recovery
       |
    Notify owner and obtain approval
       |
    Stop or quarantine first when possible
       |
    Observe impact and billing
       |
    Delete explicitly after confirmation
       |
    Verify resource and cost removal

### 9.2 Inventory và owner

Kết hợp các nguồn:

- AWS Resource Explorer hoặc AWS Config để inventory resource.
- Resource Groups Tagging API để tìm resource theo tag.
- AWS Organizations và account inventory để xác định account/owner.
- Cost Explorer/CUR để tìm resource có chi phí nhưng thiếu tag.
- Compute Optimizer/Cost Optimization Hub để tìm idle và rightsizing opportunities.
- CloudTrail để xác định principal tạo hoặc sửa resource.

Tag Owner, Application, Environment, CostCenter và Lifecycle nên được yêu cầu khi tạo resource. Với tài nguyên cũ thiếu tag, xác định owner bằng CloudTrail, IaC state, deployment pipeline và service dependency trước khi dọn.

### 9.3 Phân loại resource cleanup

| Nhóm | Ứng viên cần xem xét | Rủi ro cần kiểm tra |
|---|---|---|
| Compute | EC2 stopped lâu ngày, instance idle, ASG không có traffic, ECS service/task không hoạt động | DR, scheduled job, capacity reservation, instance store, Auto Scaling ownership |
| Block storage | EBS volume available/unattached, volume idle, snapshot cũ | Volume tách tạm, forensic, backup, AMI đang tham chiếu |
| Network | Elastic IP không association, NAT Gateway idle, load balancer không target | DR route, failover, static IP allowlist, DNS và traffic hiếm |
| Database | RDS/Aurora idle, read replica không dùng, cluster test | Backup retention, replica lag, PITR, batch/quarter-end workload |
| Object storage | S3 version cũ, incomplete multipart upload, storage class không phù hợp | Legal hold, Object Lock, restore requirement, lifecycle |
| Observability | Log group không dùng, retention vô thời hạn, metric cardinality cao | Audit retention, incident investigation, compliance |
| Data processing | SageMaker endpoint idle, Glue/EMR cluster còn chạy, batch worker dư | Scheduled workloads, model warm-up, data pipeline |
| Security/platform | Endpoint, ENI, key, certificate hoặc secret cũ | Resource do AWS service quản lý, dependency, rotation và recovery |

### 9.4 Stop, scale down hay delete?

Ưu tiên hành động có thể đảo ngược nếu chưa đủ bằng chứng:

1. Scale down hoặc giảm desired capacity nếu resource thuộc Auto Scaling/ECS/EKS.
2. Stop EC2/RDS hoặc tắt scheduler nếu workload hỗ trợ và owner xác nhận.
3. Quarantine/disable route hoặc endpoint theo runbook nếu cần quan sát.
4. Snapshot/backup dữ liệu trước khi delete.
5. Xóa resource bằng ID cụ thể sau khi hết thời gian quan sát và được phê duyệt.

Stop EC2 làm dừng compute charge nhưng không loại bỏ mọi chi phí:

- EBS volume vẫn được tính phí.
- Elastic IP vẫn có thể bị tính phí.
- Savings Plans/Reserved Instances commitment vẫn tiếp tục.
- Instance store data và data trong memory bị mất.
- Public IPv4 tự động gán có thể thay đổi khi start lại.

Một EC2 instance thuộc Auto Scaling group hoặc do dịch vụ khác quản lý có thể không stop trực tiếp được. Hãy thay đổi desired capacity hoặc cấu hình của controller sở hữu resource.

### 9.5 EBS volumes và snapshots

EBS volume trạng thái available là volume không gắn với instance tại thời điểm truy vấn. Đây chỉ là candidate; volume có thể đang chờ restore, migration hoặc DR. Trước khi delete:

- Xác nhận owner và ngày detach.
- Kiểm tra CloudTrail, attachment history và IaC state.
- Xác nhận volume không phải root volume của quy trình phục hồi.
- Tạo snapshot nếu chính sách yêu cầu.
- Xác nhận snapshot được giữ theo retention và có thể restore.
- Kiểm tra volume không được tham chiếu bởi workflow hoặc AMI.

Snapshot có thể là nền tảng của AMI hoặc recovery plan. Không xóa snapshot chỉ vì cũ; kiểm tra AMI, AWS Backup recovery point, sharing, Recycle Bin và retention policy. Recovery point do AWS Backup quản lý phải được xử lý qua AWS Backup API/console và chịu Vault Lock/lifecycle; không giả định EC2 DeleteSnapshot có thể xóa nó.

### 9.6 Elastic IP, NAT Gateway và Load Balancer

Elastic IP không association có thể vẫn phát sinh phí. Tuy nhiên, nó có thể được giữ để failover, allowlist đối tác hoặc disaster recovery. Xác nhận DNS, firewall và runbook trước khi release.

NAT Gateway idle cần kiểm tra route table, active connection, packet metrics và AZ. Nếu thay NAT bằng VPC endpoint hoặc kiến trúc khác, xác minh route và security policy trước khi xóa. Cost Optimizer xem NAT idle khi gateway không associated với route table và không có traffic/connection trong lookback theo tiêu chí hiện hành.

Load balancer không có target hoặc traffic có thể là endpoint chờ failover, blue/green deployment hoặc maintenance. Kiểm tra listener, target group, DNS, WAF, certificate, security group và service ownership trước khi delete.

### 9.7 RDS/Aurora và dữ liệu

Database không có connection trong lookback period có thể là standby, DR hoặc workload chỉ chạy định kỳ. Trước khi stop/delete:

- Kiểm tra connection, CPU, IOPS, replica và Global Database topology.
- Kiểm tra backup retention, PITR và snapshot restore.
- Xác định application owner và thời gian chạy theo lịch.
- Kiểm tra endpoint, secret, DNS và downstream dependency.
- Thử restore snapshot trong môi trường riêng nếu dữ liệu quan trọng.

Một số RDS engines hỗ trợ stop có thời hạn rồi tự start lại; giới hạn và hành vi phụ thuộc engine/deployment. Không coi stop là giải pháp lâu dài nếu resource vẫn tồn tại và storage/backup vẫn tính phí.

### 9.8 S3 và CloudWatch Logs

Với S3, xem storage class, versioning, noncurrent versions, incomplete multipart uploads, replication và lifecycle. Có thể dùng lifecycle để chuyển tier hoặc xóa đối tượng hết hạn theo policy. Với Object Lock/legal hold, không cố xóa trước khi hết retention.

Với CloudWatch Logs, log group không đặt retention có thể giữ dữ liệu vô thời hạn. Đặt retention phù hợp với audit, incident response và compliance. Không xóa log chỉ để giảm chi phí khi chưa xác nhận yêu cầu lưu trữ; có thể giảm log verbosity, sampling hoặc retention sau khi owner phê duyệt.

## 10. Ví dụ AWS CLI để tìm cleanup candidate

Các lệnh dưới đây chỉ truy vấn inventory. Chạy theo từng account và Region, vì AWS resource là regional hoặc account-scoped tùy dịch vụ. Không dùng kết quả truy vấn như lệnh xóa tự động.

Các lệnh ví dụ dùng cú pháp Bash với dấu gạch chéo ngược để nối dòng. Nếu chạy trong PowerShell, hãy nhập lệnh trên một dòng hoặc dùng ký tự nối dòng của PowerShell.

### 10.1 EBS volume chưa attach

    aws ec2 describe-volumes \
      --filters Name=status,Values=available \
      --query 'Volumes[].{VolumeId:VolumeId,SizeGiB:Size,Type:VolumeType,CreateTime:CreateTime,Encrypted:Encrypted,Tags:Tags}' \
      --output table \
      --region ap-southeast-1

### 10.2 Elastic IP chưa association

    aws ec2 describe-addresses \
      --query 'Addresses[?AssociationId==null].{PublicIp:PublicIp,AllocationId:AllocationId,Domain:Domain,Tags:Tags}' \
      --output table \
      --region ap-southeast-1

### 10.3 NAT Gateway

    aws ec2 describe-nat-gateways \
      --filter Name=state,Values=available \
      --query 'NatGateways[].{NatGatewayId:NatGatewayId,SubnetId:SubnetId,VpcId:VpcId,State:State,CreateTime:CreateTime}' \
      --output table \
      --region ap-southeast-1

Kết quả trên chỉ liệt kê NAT Gateway ở trạng thái available. Để kết luận idle, cần kiểm tra route table association, CloudWatch metrics, flow logs và DR design.

### 10.4 RDS database inventory

    aws rds describe-db-instances \
      --query 'DBInstances[].{Id:DBInstanceIdentifier,Engine:Engine,Class:DBInstanceClass,Status:DBInstanceStatus,MultiAZ:MultiAZ,StorageGiB:AllocatedStorage,BackupRetention:BackupRetentionPeriod}' \
      --output table \
      --region ap-southeast-1

Lệnh không chứng minh DB idle. Cần đối chiếu connection, CPU, IOPS, query, replica và lịch nghiệp vụ.

### 10.5 CloudWatch log groups

    aws logs describe-log-groups \
      --query 'logGroups[].{Name:logGroupName,StoredBytes:storedBytes,RetentionDays:retentionInDays,Created:creationTime}' \
      --output table \
      --region ap-southeast-1

Log group không có retentionInDays có thể giữ log vô thời hạn. Chọn retention theo data classification và yêu cầu audit.

### 10.6 Snapshot inventory

    aws ec2 describe-snapshots \
      --owner-ids self \
      --query 'Snapshots[].{SnapshotId:SnapshotId,VolumeId:VolumeId,StartTime:StartTime,State:State,SizeGiB:VolumeSize,Description:Description}' \
      --output table \
      --region ap-southeast-1

Đối chiếu snapshot với AMI, AWS Backup, retention, sharing và recovery plan trước khi xóa.

### 10.7 Hành động delete có kiểm soát

Chỉ sau khi owner xác nhận, backup/retention đã được kiểm tra và change approval hoàn tất, mới dùng lệnh xóa với ID cụ thể. Ví dụ cú pháp:

    # Ví dụ thao tác phá hủy: chỉ dùng ID đã được phê duyệt
    aws ec2 delete-volume --volume-id vol-0123456789abcdef0 --region ap-southeast-1

    # Release một Elastic IP cụ thể sau khi xác nhận không còn failover/allowlist
    aws ec2 release-address --allocation-id eipalloc-0123456789abcdef0 --region ap-southeast-1

    # Xóa một snapshot cụ thể sau khi xác nhận không được AMI/backup policy tham chiếu
    aws ec2 delete-snapshot --snapshot-id snap-0123456789abcdef0 --region ap-southeast-1

Không thay ID cụ thể bằng wildcard hoặc vòng lặp quét toàn account. Với resource do CloudFormation, Terraform, EKS, RDS, AWS Backup hoặc dịch vụ khác quản lý, thay đổi qua owner/controller tương ứng để tránh resource được tạo lại hoặc làm lệch IaC state.

## 11. Tự động hóa cleanup có guardrail

### 11.1 Tag và lifecycle policy

Một resource cleanup policy có thể dùng tag:

| Tag | Ý nghĩa |
|---|---|
| Owner | Người/đội phải xác nhận |
| Environment | Production, staging, dev, sandbox |
| Lifecycle | Persistent, ephemeral, temporary |
| CleanupAfter | Ngày sớm nhất được xem xét cleanup |
| DataClass | Phân loại dữ liệu và retention |
| DoNotDelete | Cờ loại trừ khỏi automation theo policy |

Tag không tự tạo quyền xóa. Automation cần kiểm tra tag, owner, account/Region allowlist, trạng thái resource, dependency, retention và approval.

### 11.2 Quy trình dry-run

Trước khi tự động stop/delete:

1. Chạy discovery chỉ đọc.
2. Tạo danh sách candidate cùng evidence và estimated savings.
3. Bỏ qua resource thiếu owner hoặc tag bắt buộc.
4. Kiểm tra dependency, backup và service ownership.
5. Gửi report để owner review.
6. Chỉ áp dụng hành động được allowlist và phê duyệt.
7. Lưu CloudTrail event, action result và rollback procedure.

Một job có thể chạy theo EventBridge schedule và gọi Lambda/Step Functions/Systems Manager Automation. Ưu tiên automation cho discovery, report và nhắc owner. Chỉ tự động delete resource có policy rõ, dữ liệu không stateful và rollback được kiểm chứng.

### 11.3 Approval và separation of duties

Người phát hiện candidate không nhất thiết là người phê duyệt delete. Tách quyền:

- Read-only inventory/recommendation.
- Stop/scale resource.
- Snapshot/backup.
- Delete/release.
- Quản trị policy/allowlist.

IAM policy nên giới hạn action theo resource tag, account, Region và resource type khi dịch vụ hỗ trợ condition. SCP/permission boundary có thể chặn các hành động nguy hiểm ở cấp Organization. CloudTrail phải ghi lại principal và request để phục vụ audit.

### 11.4 Idempotency và rollback

Automation phải an toàn khi chạy lại:

- Kiểm tra trạng thái hiện tại trước mỗi hành động.
- Bỏ qua resource đã xóa hoặc không còn match.
- Không xóa nếu owner/tag/backup state thay đổi sau lần discovery.
- Ghi operation ID, resource ID, timestamp và approval reference.
- Có timeout, retry giới hạn và dead-letter/error workflow.
- Sau stop, theo dõi health/alarms trước khi delete.
- Rollback phải chỉ rõ cách start/recreate và dữ liệu nào không thể phục hồi.

Stop EC2 không khôi phục được instance store hoặc memory đã mất. Delete EBS không thể đảo ngược nếu không có snapshot. Release Elastic IP có thể khiến địa chỉ không lấy lại được. Mọi automation phải nêu rõ giới hạn này.

## 12. Ưu tiên hành động theo savings, effort và risk

Không phải recommendation nào có savings lớn nhất cũng nên làm trước. Một cách ưu tiên:

\[
\text{Priority score} =
\frac{\text{Expected monthly savings} \times \text{Confidence}}
{\text{Implementation effort} \times \text{Business risk factor}}
\]

Đây là mô hình quản trị nội bộ, không phải công thức AWS. Team có thể dùng thang điểm 1–5 cho confidence, effort và risk để sắp xếp backlog.

| Action | Savings potential | Effort | Risk |
|---|---|---|---|
| Xóa EBS volume unattached đã xác nhận dư | Trung bình | Thấp | Thấp đến trung bình nếu snapshot/owner rõ |
| Đặt log retention | Trung bình | Thấp | Trung bình nếu ảnh hưởng audit |
| Rightsize non-production EC2 | Trung bình | Thấp đến trung bình | Thấp nếu có rollback |
| Rightsize production database | Cao | Trung bình/cao | Cao nếu thiếu benchmark |
| Tắt NAT Gateway | Có thể cao | Trung bình | Cao nếu route/DR chưa rõ |
| Thay đổi Savings Plans commitment | Cao | Trung bình | Cao nếu forecast usage sai |
| Dọn snapshot/backup cũ | Có thể cao | Trung bình | Rất cao nếu retention/legal hold |

Đặt SLA cho backlog theo mức độ:

- Quick win: ít effort, rủi ro thấp, owner xác nhận nhanh.
- Engineering change: cần benchmark, test và deployment.
- Financial commitment: cần forecast, term và approval tài chính.
- Data retention/security: cần compliance, legal và security owner.

## 13. Ví dụ thực tế: SaaS nhiều tenant

### 13.1 Bối cảnh

Một nền tảng SaaS có 300 tenant active. Trong tháng:

- Tổng AWS cost theo net amortized basis: 21.000 USD.
- 150.000 đơn hàng được xử lý.
- 300 tenant hoạt động.
- Chi phí shared logging/network/platform đã được phân bổ theo usage driver.

Unit economics:

    Cost per order = 21.000 / 150.000 = 0,14 USD
    Cost per tenant = 21.000 / 300 = 70 USD

Tháng trước cost per order là 0,15 USD. Dù tổng bill tăng, hiệu quả theo đơn hàng cải thiện. Tuy nhiên, cost per tenant có thể khác nhiều giữa tenant nhỏ và tenant lớn; cần thêm cost distribution p50/p90 để nhận diện tenant tiêu thụ cao.

### 13.2 Phát hiện anomaly

Cost Anomaly Detection tạo anomaly cho Amazon EC2:

- Expected spend: 300 USD.
- Actual spend: 1.300 USD.
- Impact: 1.000 USD.
- Root cause: một account production, Region ap-southeast-1, usage type EC2 instance-hour.

FinOps kiểm tra deployment history và phát hiện một autoscaling group test bị đặt min capacity bằng 20 thay vì 2. CloudTrail xác định thời điểm update; CloudWatch cho thấy CPU thấp và request gần như bằng 0.

Đội platform xác nhận resource không phục vụ DR, hạ min capacity về 2 instance theo baseline đã phê duyệt và cập nhật IaC để lần deploy sau không tạo lại capacity sai. Sau khi spend trở lại baseline, anomaly được đóng và action được ghi vào backlog.

### 13.3 Cleanup và realized savings

Compute Optimizer đề xuất idle EC2 và EBS unattached. Owner xác nhận:

- Một EC2 test có thể stop.
- Một EBS volume là volume tạm sau migration và có snapshot đã được kiểm tra.
- Một NAT Gateway thuộc DR route nên giữ lại.
- Một log group không còn dùng có thể đặt retention 90 ngày sau khi audit owner đồng ý.

Không xóa tất cả candidate cùng lúc. Thực hiện từng nhóm, theo dõi application health và cost 7–30 ngày, sau đó đo savings đã normalize theo số order.

### 13.4 Kết quả cần theo dõi

| Chỉ số | Trước | Sau |
|---|---:|---:|
| AWS cost | 21.000 USD | Đo actual kỳ sau |
| Cost/order | 0,14 USD | So sánh sau khi normalize volume |
| Idle EC2 | 1 candidate | Stop và kiểm tra |
| EBS unattached | 1 candidate | Snapshot + delete sau approval |
| NAT Gateway | 1 idle-looking | Giữ do DR |
| Anomaly impact | 1.000 USD | Xác nhận đã kết thúc |

Không ghi savings dự kiến thành savings thực tế. Chỉ công nhận realized savings sau khi billing data phản ánh thay đổi và đã loại trừ traffic/price/discount variance.

## 14. Lab: xây dựng vòng lặp unit economics và cleanup

### Mục tiêu

Tạo một báo cáo cost per unit, cấu hình anomaly alert, tìm cleanup candidate và chứng minh một hành động tối ưu có tác động thực tế.

### Bước 1: Chuẩn bị cost allocation

1. Chọn một workload có owner rõ.
2. Gắn Application, Environment, Owner, CostCenter.
3. Kích hoạt cost allocation tags trong Billing.
4. Chờ dữ liệu tag xuất hiện; kiểm tra tagged và untagged cost.
5. Tạo Cost Category nếu cần nhóm hoặc phân bổ shared cost.

### Bước 2: Tạo unit economics report

1. Chọn net amortized cost hoặc cost basis được tổ chức thống nhất.
2. Lấy cost theo account, Region, service, usage type và tag.
3. Lấy denominator từ hệ thống sản phẩm: order, request, tenant hoặc active user.
4. Tính cost/unit theo tháng và theo workload.
5. Tách direct và shared cost.
6. Ghi coverage, assumptions và phần chưa phân bổ.

### Bước 3: Cấu hình Cost Anomaly Detection

1. Bật Cost Explorer.
2. Tạo AWS managed service monitor.
3. Tạo monitor theo linked account hoặc cost allocation tag nếu cần.
4. Tạo alert subscription.
5. Chọn individual alerts qua SNS cho cảnh báo cần phản ứng nhanh hoặc daily/weekly email summary.
6. Chọn absolute/percentage threshold phù hợp với quy mô workload.
7. Kiểm tra EventBridge integration nếu muốn tạo workflow incident.

### Bước 4: Tìm cleanup candidate

1. Bật Compute Optimizer và Cost Optimization Hub theo quyền.
2. Xem idle EC2, EBS, RDS, NAT và resource type được hỗ trợ.
3. Dùng CLI discovery ở mục 10 để đối chiếu inventory.
4. Ghi owner, usage evidence, retention và estimated savings.
5. Phân loại stop, scale down, snapshot, delete hoặc keep.

### Bước 5: Thực hiện một hành động có thể đảo ngược

Chọn resource non-production có owner xác nhận. Stop hoặc scale down theo runbook. Theo dõi ứng dụng, CloudWatch và billing data. Chỉ xóa sau khi có approval và đã xác minh backup/rollback.

### Bước 6: Báo cáo kết quả

Ghi:

- Unit cost trước/sau.
- Total spend trước/sau.
- Sản lượng và workload mix.
- Resource đã thay đổi.
- Anomaly được xử lý.
- Savings ước tính và savings thực tế.
- Rủi ro/giới hạn còn lại.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Unit economics trả lời câu hỏi gì?

**Đáp án:** Chi phí và giá trị kinh tế trên một đơn vị đầu ra như đơn hàng, tenant, user hoặc request thành công.

**Câu 2.** Vì sao tổng AWS bill tăng không nhất thiết là hiệu quả giảm?

**Đáp án:** Nếu sản lượng tăng nhanh hơn chi phí, unit cost có thể giảm. Cần xem total spend cùng denominator.

**Câu 3.** Cost per successful transaction khác cost per attempted transaction thế nào?

**Đáp án:** Successful transaction chỉ tính giao dịch tạo giá trị thành công; attempted transaction gồm cả retry/thất bại. Hai mẫu số phục vụ câu hỏi khác nhau.

**Câu 4.** Vì sao phải ghi rõ cost basis?

**Đáp án:** Unblended, net unblended, amortized và net amortized phân bổ discount/commitment khác nhau; đổi basis có thể làm xu hướng thay đổi dù usage không đổi.

**Câu 5.** Cost allocation tags phải làm gì trước khi dùng trong Cost Explorer?

**Đáp án:** Gắn tag và activate cost allocation tag trong Billing. AWS-generated và user-defined tags phải kích hoạt riêng; dữ liệu có thể mất đến 24 giờ để xuất hiện.

**Câu 6.** Cost Categories split charge có làm thay đổi CUR và Cost Explorer không?

**Đáp án:** Không. Split charge được thể hiện trên trang chi tiết Cost Categories và không làm thay đổi CUR, Cost Explorer hoặc các công cụ Cost Management khác.

**Câu 7.** AWS Cost Anomaly Detection phân tích cost basis nào?

**Đáp án:** Net unblended cost data.

**Câu 8.** Vì sao Cost Anomaly Detection không phải real-time alert?

**Đáp án:** Dịch vụ chạy khoảng ba lần/ngày sau khi billing data được xử lý; Cost Explorer có thể trễ đến 24 giờ.

**Câu 9.** Một service mới cần bao lâu historical data để bắt đầu phát hiện anomaly?

**Đáp án:** 10 ngày historical service usage data theo tài liệu hiện hành.

**Câu 10.** Threshold trong anomaly subscription có ngăn model detect anomaly nhỏ không?

**Đáp án:** Không. Threshold chỉ lọc notification; anomaly dưới threshold vẫn xuất hiện trong Detected anomalies.

**Câu 11.** AWS managed monitor khác customer managed monitor ở đâu?

**Đáp án:** Managed tự theo dõi tất cả giá trị trong dimension và tự mở rộng; customer managed chọn tập giá trị cụ thể, tối đa 10 account/tag value theo dimension hỗ trợ.

**Câu 12.** Cost Anomaly Detection có theo dõi toàn bộ AWS Marketplace không?

**Đáp án:** Không. Third-party Marketplace products/services thường không được monitor, ngoại trừ third-party foundation models trên Amazon Bedrock. Dùng AWS Budgets để theo dõi Marketplace charges.

**Câu 13.** AWS Budgets và Cost Anomaly Detection bổ sung cho nhau thế nào?

**Đáp án:** Budgets cảnh báo khi actual/forecast chạm ngưỡng; anomaly detection tìm pattern spend khác thường so với lịch sử.

**Câu 14.** Compute Optimizer idle recommendation có thể dựa trên lookback bao lâu?

**Đáp án:** Mặc định thường 14 ngày, nhưng một số resource có ngoại lệ như EBS/NAT attachment 32 ngày và WorkSpaces 63 ngày.

**Câu 15.** Vì sao không xóa EBS volume chỉ vì status là available?

**Đáp án:** Volume có thể chờ migration, restore, DR hoặc forensic; cần xác nhận owner, dependency, backup và retention.

**Câu 16.** Stop EC2 có dừng mọi chi phí không?

**Đáp án:** Không. EBS, Elastic IP và RI/Savings Plans commitment có thể tiếp tục tính phí.

**Câu 17.** Vì sao phải kiểm tra ASG trước khi stop EC2?

**Đáp án:** ASG hoặc service controller có thể tự tạo lại instance hoặc không cho stop trực tiếp; phải thay đổi desired capacity/configuration của controller.

**Câu 18.** Vì sao phải xem seasonality trước khi dọn resource idle?

**Đáp án:** Workload có thể chạy theo tháng, quý, chiến dịch hoặc DR; lookback ngắn có thể không bao phủ chu kỳ hoạt động.

**Câu 19.** Estimated savings trong Cost Optimization Hub có phải realized savings?

**Đáp án:** Không. Đó là tiềm năng ước tính; phải đo billing actual sau thay đổi và normalize theo usage để công nhận savings.

**Câu 20.** Vì sao automation cleanup cần dry-run, approval và idempotency?

**Đáp án:** Để tránh xóa nhầm resource/data, kiểm soát quyền, xử lý chạy lặp và lưu evidence/rollback cho audit.

## 16. Checklist vận hành FinOps

- [ ] Unit metric có định nghĩa rõ, owner và denominator ổn định.
- [ ] Numerator dùng cost basis nhất quán và có phạm vi công bố.
- [ ] Direct/shared cost được phân bổ theo driver có thể giải thích.
- [ ] Cost allocation tags đã được activate và coverage được đo.
- [ ] Cost Categories có rule order/default value hợp lý.
- [ ] Split charge được hiểu là lớp phân bổ quản trị, không thay CUR/Cost Explorer.
- [ ] CUR/Data Exports có S3 destination, granularity và owner.
- [ ] Unit cost được xem cùng availability, latency, errors và capacity.
- [ ] Cost Anomaly Detection có monitor phù hợp và subscription có recipient.
- [ ] Threshold absolute/percentage phù hợp với quy mô từng workload.
- [ ] Đã hiểu độ trễ billing và phạm vi Marketplace của anomaly detection.
- [ ] AWS Budgets theo dõi actual/forecast so với hạn mức.
- [ ] Anomaly có owner, triage process, incident link và feedback.
- [ ] Compute Optimizer/Cost Optimization Hub được bật theo phạm vi account/Region.
- [ ] Idle recommendation được kiểm tra theo seasonality và business schedule.
- [ ] Resource cleanup có inventory, owner, backup, dependency và approval.
- [ ] Stop/scale down được ưu tiên khi có thể đảo ngược.
- [ ] Delete dùng resource ID cụ thể và qua owner/controller.
- [ ] Automation có dry-run, allowlist, idempotency, audit và rollback.
- [ ] Savings được đo lại theo actual cost đã normalize theo sản lượng.

## 17. Tài liệu tham khảo chính thức

1. [AWS Cost Anomaly Detection – overview](https://docs.aws.amazon.com/cost-management/latest/userguide/manage-ad.html) — mô hình phát hiện, độ trễ và giới hạn.
2. [Getting started with Cost Anomaly Detection](https://docs.aws.amazon.com/cost-management/latest/userguide/getting-started-ad.html) — monitor types, alert subscriptions và thresholds.
3. [Using EventBridge with Cost Anomaly Detection](https://docs.aws.amazon.com/cost-management/latest/userguide/cad-eventbridge.html) — event schema và workflow.
4. [AWS Cost Allocation Tags](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/cost-alloc-tags.html) — activate và phân loại cost bằng tag.
5. [Creating Cost Categories](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/create-cost-categories.html) — rule grouping và split charge.
6. [Splitting charges within Cost Categories](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/splitcharge-cost-categories.html) — proportional, fixed và even split.
7. [Exploring data using Cost Explorer](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-exploring-data.html) — unblended, amortized và net cost.
8. [AWS Cost and Usage Reports](https://docs.aws.amazon.com/cur/latest/userguide/what-is-cur.html) — dữ liệu chi phí/usage chi tiết.
9. [Creating a cost budget](https://docs.aws.amazon.com/cost-management/latest/userguide/create-cost-budget.html) — actual/forecast thresholds.
10. [Cost Optimization Hub](https://docs.aws.amazon.com/cost-management/latest/userguide/cost-optimization-hub.html) — tổng hợp và ưu tiên savings recommendations.
11. [Viewing idle resource recommendations](https://docs.aws.amazon.com/compute-optimizer/latest/ug/view-idle-recommendations.html) — idle criteria và lookback theo resource.
12. [Rightsizing recommendation preferences](https://docs.aws.amazon.com/compute-optimizer/latest/ug/rightsizing-preferences.html) — lookback, CPU/memory headroom và performance risk.
13. [Stopping idle resources](https://docs.aws.amazon.com/cost-management/latest/userguide/coh-stop-idle-resources.html) — stop idle EC2 từ Cost Optimization Hub.
14. [AWS Cost Optimization Hub now supports stopping idle EC2 instances](https://aws.amazon.com/about-aws/whats-new/2026/11/cost-hub-stop-idle-ec2/) — thay đổi công bố ngày 17-11-2026.
15. [AWS Resource Groups Tagging API](https://docs.aws.amazon.com/resourcegroupstagging/latest/APIReference/Welcome.html) — inventory và truy vấn resource tags.
16. [AWS CloudTrail](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-user-guide.html) — audit API activity và thay đổi resource.

---

**Kết luận:** Unit economics cho biết chi phí tạo ra một đơn vị giá trị; anomaly detection cho biết khi nào spend lệch khỏi hành vi dự kiến; cleanup biến bằng chứng thành hành động có kiểm soát. Một chương trình FinOps trưởng thành kết hợp cả ba với dữ liệu phân bổ tin cậy, owner rõ ràng, guardrail bảo vệ dữ liệu và đo savings bằng actual cost sau khi đã chuẩn hóa theo sản lượng.
