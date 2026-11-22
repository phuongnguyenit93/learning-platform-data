# Committed use discounts và sustained use discounts

Trong module `CLOUD_PROVIDERS_GCP`, người học khám phá Google Cloud từ quản trị project, IAM, VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu; qua đó biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành, theo dõi độ tin cậy và chi phí. Chương **Hiệu năng và FinOps** tập trung vào quyết định vận hành dựa trên dữ liệu. Bài này giải thích hai cơ chế tiết kiệm trên Google Cloud: **Committed Use Discounts (CUDs)** và **Sustained Use Discounts (SUDs)**.

Mục tiêu không phải tìm tỷ lệ giảm giá lớn nhất trong bảng giá, mà là tối thiểu hóa **tổng chi phí thực tế** theo mức sử dụng, khả năng thay đổi kiến trúc và rủi ro của cam kết. Bạn sẽ phân biệt từng loại giảm giá, hiểu cách áp dụng và thứ tự ưu tiên, tính toán một số ví dụ, phân tích coverage/utilization và lập quy trình mua CUD có kiểm soát.

> **Phạm vi dữ liệu:** Chính sách, dòng máy đủ điều kiện, tỷ lệ giảm giá và mô hình ghi nhận CUD có thể thay đổi theo SKU, tài khoản thanh toán, hợp đồng và thời điểm. Các tỷ lệ tiền tệ trong bài toán minh họa chỉ là **giả định để học**, không phải báo giá Google Cloud. Trước khi mua, phải kiểm tra Cloud Billing Console, CUD recommendations và tài liệu chính thức tại thời điểm quyết định.

## 1. Hai cơ chế chiết khấu giải quyết hai nhu cầu khác nhau

**Sustained Use Discount (SUD)** là chiết khấu theo *thời gian sử dụng đủ lâu trong một tháng* đối với **những Compute Engine resources đủ điều kiện**. SUD không yêu cầu ký hợp đồng hay mua trước; Compute Engine tự tính và áp dụng cho usage đủ điều kiện của Cloud Billing account. Thông thường, resource phải được sử dụng quá 25% thời gian của billing month mới bắt đầu được hưởng mức chiết khấu tăng dần.

**Committed Use Discount (CUD)** là chiết khấu đổi lấy cam kết **mua một mức tài nguyên hoặc chi tiêu tối thiểu**, thường trong **1 năm hoặc 3 năm**. Bạn phải trả khoản phí cam kết trong thời hạn hợp đồng, dù có sử dụng hết hay không. CUD phù hợp khi workload có **baseline ổn định và có thể dự báo**.

| Tiêu chí | SUD | CUD |
| --- | --- | --- |
| Có phải mua cam kết? | Không | Có, từ 1 năm hoặc 3 năm theo sản phẩm |
| Cách kích hoạt | Tự động với usage đủ điều kiện | Mua commitment theo sản phẩm/tài nguyên |
| Thời gian xét | Theo phần sử dụng trong billing month | Theo thời hạn commitment và cửa sổ áp dụng tương ứng |
| Ràng buộc | Chỉ các resource, machine series và billing account đủ điều kiện | Phạm vi phụ thuộc loại CUD, SKU, region, tài khoản |
| Khi workload giảm mạnh | Không phát sinh khoản phí SUD cố định | Vẫn chịu phí commitment đã mua |
| Mức tiết kiệm | Tăng theo tỷ lệ thời gian sử dụng, có trần theo series | Tỷ lệ theo sản phẩm, SKU, thời hạn và loại commitment |
| Đối tượng phù hợp | Usage dài nhưng chưa muốn khóa hợp đồng | Baseline đã đo được và có kế hoạch dài hạn |
| Có cộng dồn cùng giờ trên cùng usage? | Không | Không: một lượng usage không đồng thời nhận cả SUD và CUD |

Một thuật ngữ khác dễ nhầm là **reservation**: đặt trước năng lực Compute Engine ở vùng/zone phù hợp. **CUD không tự động giữ chỗ tài nguyên vật lý**; nếu workload cần bảo đảm năng lực, phải thiết kế reservation riêng và kiểm tra cơ chế liên kết với commitment. SUD cũng không giữ chỗ.

## 2. Phân biệt các loại CUD

Google Cloud có hai nhóm CUD chính: **resource-based** và **spend-based**. Phạm vi chiết khấu, tài nguyên đủ điều kiện và cách tính phí của hai nhóm không giống nhau.

### 2.1. Resource-based CUD

Với Compute Engine **resource-based commitment**, bạn cam kết lượng tài nguyên trong **một region và một cấu hình/dòng máy đủ điều kiện**. Tài nguyên có thể là vCPU, memory, một số GPU, Local SSD, sole-tenant nodes hoặc license theo điều kiện sản phẩm.

Ví dụ: workload backend dùng số lượng vCPU/RAM ổn định trên các VM N2 trong một region. Bạn dự báo rằng tối thiểu một lượng vCPU và RAM này luôn được sử dụng. Thay vì trả toàn bộ theo giá on-demand, bạn có thể mua resource-based commitment phù hợp với **baseline theo giờ**.

Đặc điểm cần lưu ý:

- Mỗi commitment có **project và region khi mua**; usage được hưởng phải phù hợp với region, loại/machine series và các quy tắc eligibility.
- **CUD sharing** có thể cho phép resource-based commitments từ một project bao phủ usage của các project khác dưới **cùng Cloud Billing account**, nếu cấu hình và điều kiện cho phép. Không được mặc định luôn bật hoặc luôn tắt; phải xem cài đặt hiện tại.
- Quy mô VM có thể thay đổi nhưng chỉ **phần resource phù hợp và đủ điều kiện** được bao phủ. Không được suy rằng bất cứ VM mới nào cũng tự hưởng CUD của VM cũ.
- Một số commitment liên quan GPU/Local SSD có yêu cầu reservation hoặc hình thức mua đặc thù. Kiểm tra tài liệu theo phần cứng.
- Resource-based CUD phù hợp với **capacity baseline ổn định**, nhưng có thể bị lãng phí nếu migrate sang machine family/region khác mà commitment không còn bao phủ.

### 2.2. Spend-based CUD

Với **spend-based commitment**, bạn cam kết một lượng **chi tiêu đủ điều kiện** trong thời hạn hợp đồng. Phạm vi có thể là một dịch vụ nhất định hoặc một nhóm dịch vụ, tùy sản phẩm CUD.

Ví dụ: **Compute flexible CUD** có thể bao phủ những SKU đủ điều kiện của **Compute Engine, Google Kubernetes Engine và Cloud Run** trong Cloud Billing account. Nó linh hoạt hơn resource-based commitment đối với nhiều biến thể máy, project và region, nhưng **không phải mọi SKU trong ba dịch vụ đều đủ điều kiện**.

- Có các **service-specific spend-based CUDs** áp dụng cho một dịch vụ nhất định, chẳng hạn các chương trình CUD phù hợp của Cloud SQL hoặc sản phẩm khác. Mỗi dịch vụ có cách định nghĩa eligible spend/region riêng.
- Compute flexible CUD có thể dùng để bao phủ **eligible usage** trải rộng nhiều project hoặc dịch vụ trên cùng billing account; không thể chia sẻ CUD giữa các billing accounts khác nhau.
- Quy tắc ưu tiên có thể áp dụng service-specific commitments trước compute flexible commitments khi một usage thuộc nhiều phạm vi.
- Với chương trình **spend-based CUD mới**, cam kết thường được biểu diễn theo **discounted spend**; chương trình legacy có thể dùng cách nhập **on-demand-equivalent spend**. Không được dùng nhầm đơn vị trong lúc mua.
- Với một số sản phẩm mới như Flexible Savings Plans, cửa sổ entitlement có thể là **tháng**, không hoàn toàn giống cách tính hourly commitments truyền thống. Luôn xem terms của commitment cụ thể.

### 2.3. So sánh lựa chọn

| Workload | Ưu tiên đánh giá | Lý do |
| --- | --- | --- |
| VM cùng family, cùng region, chạy ổn định 24/7 | Resource-based CUD | Match tốt baseline CPU/RAM theo region/series. |
| VM thay đổi machine family hoặc region nhưng tổng eligible spend ổn định | Compute flexible CUD | Mức chi tiêu ổn định hơn cấu hình tài nguyên. |
| Một đội có Compute Engine, GKE và Cloud Run đủ điều kiện trên cùng billing account | Compute flexible CUD | Có thể chia sẻ phạm vi eligible spend giữa nhiều dịch vụ. |
| Cloud SQL workload liên tục | CUD dành riêng cho Cloud SQL nếu đủ điều kiện | Không dùng nhầm Compute Engine resource-based CUD để bao phủ toàn bộ Cloud SQL bill. |
| Development VMs chỉ chạy giờ hành chính, hay đổi kích thước | On-demand + scheduling/rightsize, SUD nếu eligible | Cam kết dài hạn có thể làm tổng phí tăng. |
| Workload thí điểm chưa rõ quy mô | Theo dõi trước khi mua | Dữ liệu lịch sử ngắn dễ làm dự báo sai. |

**Chú ý:** Giá discount của Cloud Run phụ thuộc billing mode và loại workload. Đừng coi "Cloud Run luôn được giảm X%" hay "mọi Cloud Run spend đều eligible" là đúng; hãy kiểm tra danh sách SKU đủ điều kiện và giá CUD của từng loại request-based, instance-based, jobs, functions hoặc worker pools.

## 3. SUD hoạt động như thế nào?

### 3.1. Mốc 25%, 50%, 75% và 100% của tháng

SUD áp dụng cho resource đủ điều kiện đã sử dụng hơn **25% thời lượng tháng**, rồi tăng dần theo mức sử dụng. Google Cloud sử dụng các mức tiến triển 25%, 50%, 75%, 100% để tính chiết khấu tăng dần. Kết quả là **effective discount rate** trên tổng usage của tháng thấp hơn mức chiết khấu cận biên ở giờ sau cùng.

Với nhóm tài nguyên có **mức SUD tối đa 30%**, các con số minh họa trong tài liệu Compute Engine là:

| Sử dụng tương đương trong tháng | Effective SUD trên tổng eligible usage |
| --- | --- |
| 25% hoặc ít hơn | 0% |
| 50% | 10% |
| 75% | 20% |
| 100% | 30% |

Nhóm có mức SUD tối đa **20%** có đường chiết khấu riêng. Đừng lấy bảng 30% áp dụng cho tất cả VM.

### 3.2. Resource/machine series nào được SUD?

Theo tài liệu Compute Engine, các machine series có SUD phổ biến bao gồm:

| Nhóm | Mức SUD tối đa khi dùng đủ điều kiện cả tháng |
| --- | --- |
| N1 predefined/custom; M1/M2; một số N1 GPU và sole-tenant resources | Tới 30% |
| N2/N2D predefined/custom; C2; các sole-tenant resources tương ứng | Tới 20% |
| E2, C3/C4, N4 và nhiều series mới | **Không có SUD**; on-demand pricing của chúng đã được thiết kế khác |

Tỷ lệ tối đa chỉ nói về **resource thuộc chương trình**; hóa đơn VM còn có disk, image/license, network, egress và nhiều SKU không nhất thiết được hưởng SUD. SUD không áp dụng cho mọi GPU, mọi machine type hay mọi sản phẩm Google Cloud.

Giới hạn cần nhớ:

- Tài liệu SUD áp dụng với **Self-serve/Online Cloud Billing accounts**, không nên mặc định mọi hình thức hợp đồng doanh nghiệp được hưởng cùng cơ chế.
- SUD cho VM đủ điều kiện từ **Compute Engine và GKE**; không áp dụng cho VM do **App Engine standard/flexible** hay Dataflow tạo ra theo danh sách giới hạn của chương trình.
- **Không áp dụng SUD cho phần usage đã được CUD bao phủ**.
- Không áp dụng với phần usage thuộc Always Free quota tương ứng.
- SUD thường hiển thị thành **monthly credits** trên hóa đơn/report; không phải khoản tiền mặt có thể chuyển sang tháng khác.

### 3.3. Tính một ví dụ SUD

Giả sử một **eligible N1 resource** có on-demand cost giả định **0,10 USD/giờ** cho chính phần tài nguyên được SUD, và tháng xét có **720 giờ**. Ví dụ cố tình bỏ qua license, disk, network, taxes, các discounts khác và trường hợp resource không đủ điều kiện.

**Kịch bản A — dùng 50% tháng:** 360 giờ.

~~~text
Eligible on-demand cost = 360 × 0,10 = 36,00 USD
Effective SUD ở mức 50% tháng = 10%
SUD credit = 36,00 × 10% = 3,60 USD
Net eligible compute cost = 36,00 − 3,60 = 32,40 USD
~~~

**Kịch bản B — dùng cả tháng:** 720 giờ.

~~~text
Eligible on-demand cost = 720 × 0,10 = 72,00 USD
Effective SUD khi dùng cả tháng = 30%
SUD credit = 72,00 × 30% = 21,60 USD
Net eligible compute cost = 72,00 − 21,60 = 50,40 USD
~~~

SUD **không có nghĩa "sử dụng đến giờ thứ 181 là giảm 30% toàn bộ bill"**. Chiết khấu tăng theo từng khoảng sử dụng và mức effective chỉ đạt trần khi dùng cả tháng đủ điều kiện.

Nếu thay N1 bằng một E2 VM, bài toán SUD này không áp dụng. Nếu 360 giờ đã được CUD bao phủ thì cũng không được áp dụng thêm SUD cho cùng lượng usage.

## 4. Phạm vi và thứ tự áp dụng CUD, SUD

Một Cloud Billing account có thể đồng thời có resource-based CUD, compute flexible CUD và usage đủ điều kiện cho SUD. **Không phải lấy ba tỷ lệ chiết khấu nhân vào nhau**.

Tổng quát đối với eligible Compute Engine usage:

1. Google Cloud áp dụng **resource-based CUD** cho phần usage đáp ứng scope/cấu hình.
2. Phần eligible còn lại có thể được bao phủ bởi **compute flexible CUD**, theo thứ tự ưu tiên commitments của billing account và sản phẩm.
3. Phần **không được commitment bao phủ** được tính on-demand; nếu bản thân resource và billing account đủ điều kiện SUD thì phần này có thể được hưởng SUD theo quy tắc của chương trình.

~~~mermaid
flowchart TD
  USAGE[Compute Engine eligible usage từng giờ] --> R{Matched resource-based CUD?}
  R -->|Yes| RC[Apply resource-based CUD]
  R -->|No, remaining usage| F{Eligible flexible CUD capacity?}
  F -->|Yes| FC[Apply compute flexible CUD]
  F -->|No| OD[Charge on-demand]
  OD --> S{SUD eligible and monthly threshold met?}
  S -->|Yes| SC[Apply SUD on uncovered eligible usage]
  S -->|No| ND[No SUD]
~~~

Đây là mô hình khái niệm để học; việc gán SKU/commitment có thể phức tạp hơn khi có nhiều spend-based commitments, service-specific commitments, credit programs và billing account cụ thể. Hãy dùng CUD Analysis và billing export để kiểm tra **kết quả thực tế**.

**Không cộng dồn:** ví dụ "resource-based CUD giảm 35% và SUD giảm tiếp 30%" trên cùng usage là sai. Bạn chỉ có thể thấy hai loại savings trên cùng một billing account vì chúng áp dụng trên **những phần usage khác nhau**.

### 4.1. CUD sharing và scope

Resource-based commitments truyền thống gắn region và project mua; chia sẻ sang project khác phụ thuộc **CUD sharing setting** và loại billing account. Từ giữa năm 2026, một số tài khoản mới có mặc định CUD sharing khác tài khoản cũ. Vì vậy, phải **đọc setting thực tế**, không suy từ tuổi project.

Spend-based commitments thường áp dụng ở **Cloud Billing account scope**, nhưng vẫn có điều kiện region và eligible SKU riêng. Một cam kết dành cho region A không đương nhiên chuyển sang region B nếu sản phẩm có giới hạn region. Chuyển project sang **billing account khác** có thể làm mất khả năng áp dụng commitment hiện hữu.

### 4.2. Commitment có phải reservation?

Không. CUD là cơ chế **giá/chi phí**, không phải mặc định đảm bảo sức chứa vùng/zone. Khi cần bảo đảm GPU hoặc máy hiếm có sẵn lúc scale, hãy xem **Compute Engine Reservations** và quy tắc kết hợp commitments với reservations; không dùng một purchase CUD như bằng chứng Google Cloud đã giữ đủ năng lực.

## 5. Phân biệt CUD coverage, utilization và savings

Ba chỉ số dùng trong FinOps có ý nghĩa khác nhau:

| Chỉ số | Ý nghĩa | Nếu thấp thì sao? |
| --- | --- | --- |
| **CUD coverage** | Tỷ lệ **eligible usage/spend** được commitments bao phủ trong kỳ. | Nhiều eligible usage còn tính on-demand; có thể có cơ hội mua thêm, nhưng phải xem tính ổn định. |
| **CUD utilization** | Tỷ lệ phần **commitment đã mua** thực sự được sử dụng trong kỳ. | Có capacity/spend đã trả nhưng không được dùng hết, gây chi phí lãng phí. |
| **CUD savings** | Khoản tiết kiệm thực tế theo chương trình và định nghĩa báo cáo. | Có thể thấp do mức usage, underutilization, scope mismatch, thay đổi giá hoặc CUD không đúng loại. |

Các tỷ lệ so sánh phải **cùng loại đơn vị**. Không cộng "10 vCPU + 20 GiB memory" để tính một utilization rate chung. Cloud Billing CUD Analysis cũng không hiển thị utilization gộp cho nhiều loại CUD có đơn vị khác nhau.

Mô hình đơn giản:

~~~text
Coverage ≈ Eligible usage covered by CUD / Total eligible usage
Utilization ≈ Applied commitment / Purchased commitment
~~~

Với spend-based CUD trong consumption model mới, usage đã có discounted rates; báo cáo coverage có thể chuẩn hóa theo **on-demand-equivalent eligible cost** để so sánh. Không lấy trực tiếp net billed spend của mọi SKU chia cho committed spend rồi kết luận coverage, vì mẫu số và tử số có thể ở hai đơn vị tiền khác nhau.

### 5.1. Tại sao coverage cao chưa chắc tiết kiệm tốt?

Một đội mua 100 đơn vị capacity cam kết nhưng chỉ dùng 60 đơn vị thường xuyên. Có thể có **coverage 100%** cho usage 60 đơn vị nhưng utilization chỉ **60%**; vẫn phải trả phí cho phần capacity chưa dùng. Ngược lại, đội có utilization 100% và coverage 45% đã sử dụng hết cam kết, nhưng 55% eligible usage còn on-demand. Nếu phần dư chỉ là spike, mua thêm CUD có thể không có lợi.

### 5.2. Rủi ro khi chuyển workload

Khi quyết định chuyển N2 VMs sang một series khác, region khác, Cloud Run hoặc kiến trúc serverless, phải hỏi:

- Commitment cũ còn bao phủ eligible SKU mới không?
- Còn bao lâu tới ngày hết hạn?
- CUD sharing có giúp các project khác dùng phần capacity cam kết không?
- Nếu chuyển workloads ngay, phần fee không sử dụng là bao nhiêu?
- Savings dự kiến của kiến trúc mới có đủ bù chi phí cam kết còn lại?

Giữ một VM không hiệu quả chỉ để "không lãng phí CUD" cũng có thể là sai lầm sunk-cost. So sánh **tổng chi phí từ hiện tại trở đi**, gồm phí commitment không tránh được và phần chi phí biến đổi có thể giảm.

## 6. Ví dụ tính toán CUD và điểm hòa vốn

### 6.1. Resource-based CUD (giả định)

Giả sử một tài nguyên capacity chuẩn có giá on-demand **1 USD/giờ** nếu sử dụng đủ mức 10 units; một commitment tương ứng có phí **0,65 USD/giờ** và bao phủ tối đa 10 units/hour. Tỷ lệ giá trong ví dụ là **giả định**, không phải discount chính thức.

| Tình huống | Eligible usage thật | On-demand giả định | Tổng phí CUD trước overage | Diễn giải |
| --- | --- | --- | --- | --- |
| Chạy 10/10 units | 1,00 USD/h | 1,00 USD/h | 0,65 USD/h | Tiết kiệm 0,35 USD/h nếu đủ match. |
| Chạy 9/10 units | 0,90 USD/h | 0,90 USD/h | 0,65 USD/h | Một phần commitment không dùng, vẫn tiết kiệm so với on-demand. |
| Chạy 6/10 units | 0,60 USD/h | 0,60 USD/h | 0,65 USD/h | Lỗ 0,05 USD/h so với on-demand chưa tính SUD. |
| Chạy 16/10 units | 1,60 USD/h | 1,60 USD/h | 0,65 + 0,60 = 1,25 USD/h | 10 units được bao phủ; 6 units tính ngoài commitment. |

Từ phép tính đơn giản:

~~~text
On-demand cost của 10 units = 1,00 USD/h
Commitment fee = 0,65 USD/h
Break-even usage fraction ≈ 0,65 / 1,00 = 65%
~~~

**65% chỉ là điểm hòa vốn giữa CUD và on-demand thuần** trong giả định này. Khi eligible on-demand usage có thể hưởng SUD hoặc hợp đồng/credits khác, điểm hòa vốn thực tế có thể cao hơn. Còn nếu mua một gói spend-based CUD theo discounted spend, **không được áp công thức 10 units của resource-based CUD một cách máy móc**.

### 6.2. Đừng bỏ qua SUD ở phương án đối chứng

Giả sử workload resource N1 đủ điều kiện SUD chạy cả tháng. Với giá on-demand 1,00 USD/h, **SUD tối đa 30%** cho eligible usage có thể làm chi phí hiệu quả còn khoảng 0,70 USD/h. Commitment giả định 0,65 USD/h khi dùng hết chỉ tiết kiệm thêm khoảng 0,05 USD/h so với phương án có SUD.

Như vậy, nói "mua CUD tiết kiệm 35%" là **không đủ** cho quyết định tài chính: phải so sánh với phương án **tốt nhất mà tổ chức đang có**, gồm SUD, existing commitments, rightsizing, scheduling và giá hợp đồng.

### 6.3. Tách chi phí cố định và biến đổi

Để so sánh theo cả vòng đời commitment:

~~~text
Total cost with CUD
  = Commitment fees over term
  + Uncovered eligible usage at applicable rates
  + Non-eligible usage (disks, network, licences, ...)
  + Other platform and operations costs
  - Applicable separate savings

Total cost without new CUD
  = Eligible usage at applicable existing rates
  + Non-eligible usage
  + Other platform and operations costs
  - Existing applicable discounts (such as SUD)
~~~

Các phí chung giống nhau có thể triệt tiêu khi so sánh, nhưng phải giữ những khoản thay đổi do kiến trúc hoặc contract. Với các trường hợp có **CUD credit accounting legacy** hay **consumption model discounts mới**, chỉ cộng đúng các dòng phí/credits một lần.

## 7. Ghi nhận CUD trong Cloud Billing: mô hình cũ và mới

Một sai lầm phổ biến là nhìn tổng credits giảm rồi kết luận CUD đem lại khoản tiết kiệm bằng credits, trong khi nhiều spend-based CUD hiện dùng **consumption model discounted rates**.

### 7.1. Legacy credits

Một số CUD trong mô hình cũ ghi usage ở on-demand rate và đưa discount qua **credit**. Resource-based CUD cũng có các dòng fee/credits theo cách ghi nhận của Cloud Billing. Khi phân tích cần ghép usage, credit và **commitment fee** ở đúng scope; chỉ cộng credits mà bỏ commitment fee sẽ thổi phồng savings.

### 7.2. Spend-based CUD mới

Google Cloud đã triển khai mô hình **Spend-based CUD discounts**, trong đó usage được tính với **giá đã chiết khấu** theo **consumption model** phù hợp, thay vì luôn có một khoản credit riêng để triệt tiêu giá list.

Hệ quả FinOps:

- `cost` trên billing export có thể đã phản ánh discounted price cho SKU dùng consumption model.
- Không thể kết luận "không có CUD credit nghĩa là không được hưởng CUD".
- Phải đối chiếu **consumption model**, commitment fees, các SKU đủ điều kiện và CUD Analysis.
- Mẫu báo cáo cũ dựa trên `credits.type` có thể chưa cho thấy đầy đủ spend-based savings trong mô hình mới.
- Tài khoản có legacy commitments đang migration cần xem **Cloud Billing Overview** để biết lịch áp dụng của chính tài khoản đó; không giả định mọi tài khoản chuyển đổi trong cùng ngày.

### 7.3. CUD và billing attribution

Commitment mua tại Cloud Billing account có thể được **attributed** về project sử dụng theo cài đặt attribution. Vì thế, khi chỉ mở Billing Report của một project, bạn có thể không thấy toàn bộ fee hoặc credit của account. Đánh giá hiệu quả cam kết phải bắt đầu ở **billing-account scope**, sau đó phân bổ chi phí nội bộ theo policy FinOps.

Với nhiều team, nên quy định trước cách **showback/chargeback** khoản fee cam kết chưa sử dụng. Nếu không, một team có thể được ghi nhận savings trong khi team khác chịu phí commitment bỏ không.

## 8. Phân tích dữ liệu trước khi quyết định mua

Một quyết định CUD tốt cần dữ liệu **theo giờ** hoặc cửa sổ entitlement đúng loại, không chỉ trung bình tháng. Biến động giữa ngày thường và cuối tuần, autoscaling và lịch deploy có thể làm baseline thấp hơn trung bình.

### 8.1. Các câu hỏi cần trả lời

1. Trong 30/60/90 ngày gần đây, **eligible usage** của từng SKU, region, machine family hoặc dịch vụ là bao nhiêu?
2. Bao nhiêu phần đã được **existing CUDs** bao phủ? Còn bao nhiêu phần on-demand, được SUD hay có contract discount khác?
3. Baseline ở percentile thận trọng (ví dụ P10/P20 của eligible hourly usage) là bao nhiêu?
4. Workload sắp chuyển vùng, đổi machine family, xuống cấp, đổi cloud hoặc chuyển sang Cloud Run/GKE không?
5. Rightsizing, auto-stop non-production, schedule và cache có làm giảm baseline không?
6. Commitment mới có phù hợp với budget, cash flow và chính sách phê duyệt không?
7. Phần usage ngoài commitment có đủ ổn định để mua thêm không, hay chỉ là spike không dự báo?

### 8.2. Dùng Billing Reports và CUD Analysis

Trong Google Cloud Console (tên mục có thể thay đổi theo giao diện):

1. Mở **Billing**, chọn đúng **Cloud Billing account**.
2. Mở **Reports** hoặc **Cost table** để xem tổng chi phí, service/SKU, project, region và savings filters.
3. Mở **Committed use discounts (CUDs)** hoặc **CUD Analysis**.
4. Chọn loại commitment, thời gian và scope.
5. Xem **Coverage** (bao nhiêu eligible usage/spend được bao phủ), **Utilization** (đã dùng bao nhiêu commitment), **Savings** (mức tiết kiệm) và ngày hết hạn.
6. So sánh với **CUD Recommender** rồi kiểm tra điều kiện và các thay đổi workload sắp tới.

Báo cáo có độ trễ cập nhật; ngày gần nhất có thể chưa đầy đủ. Nếu dữ liệu có gap hoặc một commitment mới bắt đầu giữa kỳ, không dùng số liệu non-representative để mua lượng lớn.

### 8.3. Phân tích Cloud Billing export qua BigQuery

Với Cloud Billing **standard/detailed usage cost export** được bật trong BigQuery, có thể dùng SQL để phân nhóm theo service và SKU. Ví dụ đọc **cost sau pricing nhưng trước credits** cùng tổng credits; thay tên table theo billing account của bạn:

~~~sql
SELECT
  invoice.month AS invoice_month,
  service.description AS service_name,
  sku.description AS sku_name,
  ROUND(SUM(cost), 2) AS cost_before_credits,
  ROUND(SUM(
    IFNULL(
      (SELECT SUM(c.amount) FROM UNNEST(credits) AS c),
      0)
  ), 2) AS credits_amount,
  ROUND(SUM(
    cost + IFNULL(
      (SELECT SUM(c.amount) FROM UNNEST(credits) AS c),
      0)
  ), 2) AS reported_cost_after_credits
FROM `BILLING_PROJECT.billing_dataset.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
WHERE usage_start_time >= TIMESTAMP("2026-09-01")
GROUP BY invoice_month, service_name, sku_name
ORDER BY invoice_month DESC, reported_cost_after_credits DESC;
~~~

**Giới hạn của query:**

- Nó chỉ nhóm `cost` và `credits` của những line items có trong export; **không phải phép tính CUD savings hoàn chỉnh**. Trong mô hình mới, chiết khấu theo consumption model có thể đã nằm trong `cost`.
- Một SKU có thể có nhiều consumption models, nên muốn đo chính xác CUD mới phải phân tích thêm **consumption model** và fee lines theo schema hiện hành của **detailed export**.
- Query có thể bao gồm taxes, adjustments hoặc fees tùy cách lọc SKU và invoice month; kết quả không trực tiếp là giá on-demand đối chứng.
- Không tự phát sinh dữ liệu lịch sử trước ngày billing export được bật. Khi thiếu lịch sử, dùng Billing Reports/CUD Analysis hoặc nguồn dữ liệu được phép khác.
- Chỉ người có quyền phù hợp được xem BigQuery export và báo cáo chi phí; không công bố project IDs, contract discounts hoặc invoice data nhạy cảm.

### 8.4. Đọc dữ liệu theo giờ

Đối với resource-based CUD, gom eligible vCPU/memory usage theo **hour + region + machine series + billing-account scope** rồi xem phân phối. Với Compute flexible CUD, gom **eligible spend theo consumption model/rules** trên đúng phạm vi billing account. Đừng nhầm total VM spend với eligible spend; license, persistent disk hoặc egress có thể không được bao phủ trong gói đang xét.

Một dạng báo cáo hữu ích:

| Khoảng thời gian | Usage baseline phù hợp | Usage đỉnh | Existing CUD coverage | Đề xuất |
| --- | --- | --- | --- | --- |
| Giờ thấp điểm ngày thường | 8 units | 12 units | 6 units | Cân nhắc tăng nhẹ nếu baseline bền vững |
| Giờ cao điểm ngày thường | 10 units | 18 units | 6 units | Overage biến động: cần xem P10/median |
| Cuối tuần | 5 units | 9 units | 6 units | Không tăng CUD chỉ dựa vào giờ cao điểm |
| Sau rightsizing dự kiến | 4–7 units | 12 units | 6 units | Hoãn mua mới đến khi có số đo ổn định |

Đơn vị units chỉ là khái niệm minh họa. Trong thực tế, phân tích resource-based theo vCPU/RAM tách biệt; spend-based theo đơn vị tiền và eligible SKUs.

## 9. CUD Recommender và phê duyệt mua

**CUD Recommender** trong Google Cloud sử dụng usage lịch sử, existing commitments và mức coverage mục tiêu để gợi ý commitment cho một số sản phẩm đủ điều kiện. Recommendation không phải mệnh lệnh mua: nó không biết chắc kế hoạch ngừng hệ thống, thay hợp đồng hoặc migrate trong tương lai nếu bạn chưa đưa các ràng buộc đó vào review.

Quy trình gợi ý:

1. Thu thập usage tối thiểu 30–90 ngày đại diện; bổ sung dữ liệu mùa vụ hoặc một chu kỳ kinh doanh dài hơn nếu có.
2. Loại khỏi baseline những workloads đang chuẩn bị shutdown, rightsize, hoặc chuyển sang loại tài nguyên không còn eligible.
3. So sánh **1 năm** và **3 năm**: ba năm thường giảm sâu hơn nhưng giữ rủi ro chuyển đổi lâu hơn.
4. So sánh **resource-based** và **spend-based/flexible** theo stability của resource versus spend.
5. Dùng CUD Recommender và Pricing Calculator/chi phí cam kết để kiểm tra break-even so với phương án đang được SUD.
6. Kiểm tra region, SKU eligibility, quyền tài khoản, CUD sharing và phí hiện hữu; duyệt qua FinOps + chủ workload + người có thẩm quyền chi tiêu.
7. Chỉ người được ủy quyền mới mua tại Billing Console. **Không mua tự động bằng pipeline** khi chưa có review và approval.

Spend-based CUD có tính ràng buộc: thường **không thể hủy, giảm mức cam kết hoặc đổi thời hạn sau khi mua**. Những chi tiết như thay đổi scope, migration hoặc chuyển billing account đòi hỏi xem terms cụ thể và có thể cần Cloud Billing Support. Một cuộc mua có thể tạo nghĩa vụ chi phí nhiều năm, vì vậy không coi đây là thay đổi cấu hình thử nghiệm có thể rollback.

## 10. Một kịch bản FinOps từ đầu đến cuối

Công ty có ba nhóm workload:

- **Backend VM N2 chạy đều** ở một region: workload 24/7, CPU/RAM có thể dự báo, ít thay đổi kiến trúc trong 12 tháng.
- **GKE batch processing**: có một số jobs chạy theo lịch và dùng tài nguyên biến động; usage ban đêm/cuối tuần không ổn định.
- **Cloud Run API**: số request biến động mạnh, nhưng tổng eligible spend giữa các dịch vụ có thể tương đối ổn định.

Cách tiếp cận:

1. **Backend N2:** kiểm tra current SUD tối đa của N2 (khác N1), đánh giá resource-based CUD cho phần vCPU/RAM baseline theo region. Chỉ cam kết lượng chắc chắn dùng, không lấy peak capacity.
2. **GKE:** phân biệt phần Compute Engine VM nodes có thể nhận resource-based CUD/SUD và phần service/SKU thuộc phạm vi Compute flexible CUD; đừng tính trùng hai khoản.
3. **Cloud Run:** xác định billing mode và eligible SKU trước khi đưa vào Compute flexible CUD. Nếu chi phí lên xuống theo giờ, xem tổng eligible spend có đủ bền để commitment phát huy tác dụng không.
4. **Tài khoản:** kiểm tra tất cả project nằm trong cùng Cloud Billing account, settings CUD sharing và existing commitments.
5. **Tối ưu trước:** giảm VM idle, rightsizing, chuyển batch phù hợp sang Spot nếu đáp ứng reliability, rồi mới quyết định lượng cam kết.
6. **Theo dõi sau:** hàng tuần xem coverage, utilization, savings và phần phí commitment lãng phí; mỗi tháng điều chỉnh forecast và chuẩn bị rollover trước khi commitment hết hạn.

Một phương án mua hợp lý có thể là resource-based CUD cho phần N2 ổn định và compute flexible CUD ở mức **thấp hơn** cho phần eligible spend còn lại. Cũng có thể không cần mua compute flexible nếu biến động quá lớn. Tỷ lệ discount cao không bù được fee commitments bỏ không.

## 11. SUD, CUD và các biện pháp tối ưu khác

CUD và SUD là **pricing optimizations**, không thay thế **engineering efficiency**.

| Biện pháp | Giá trị | Rủi ro/cần lưu ý |
| --- | --- | --- |
| Rightsizing VM/container | Giảm usage thực sự theo CPU/RAM | Phải load test và đo SLO sau resize |
| Schedule non-production off-hours | Giảm số giờ chạy | Có thể làm mất SUD nhưng tổng tiền vẫn giảm mạnh |
| Autoscaling có giới hạn | Duy trì năng lực theo tải | Không cam kết phần spike ngắn hạn |
| Spot VMs cho batch fault-tolerant | Giá thấp cho workload chịu gián đoạn | Có thể bị reclaim; Compute flexible CUD không áp dụng cho Spot VMs |
| SUD cho eligible VMs | Tự động, không lock-in | Chỉ một số machine series/billing accounts |
| Resource-based CUD | Phù hợp baseline phần cứng cố định | Scope region/series và phí cố định |
| Compute flexible CUD | Bao phủ eligible spend đa dịch vụ | Phụ thuộc SKU eligibility và cam kết chi phí |
| Cloud Run/GKE architectural optimization | Giảm quản trị, tăng hiệu quả | Tính lại pricing/costs và migration risk |

**Ví dụ nghịch lý:** Một VM test chạy 24/7 được SUD 30%; nếu tắt máy 16 giờ/ngày và cuối tuần, phần trăm SUD có thể giảm hoặc mất. Tuy nhiên, tổng usage hours giảm mạnh, nên **bill cuối tháng thường vẫn thấp hơn**. Đừng bật máy chỉ để “giữ SUD”.

## 12. Theo dõi commitment sau khi mua

Không dừng ở giao dịch mua. Theo dõi theo chu kỳ cố định:

### Hằng tuần

- **Utilization** của từng commitment và **coverage** của eligible spend.
- Uncovered spend ở giờ cao/thấp điểm; kiểm tra vì sao dưới/ngoài commitment.
- Workload thay đổi machine type, region, project, service hoặc billing account.
- Tỷ lệ chi phí đã có CUD nhưng vẫn có phần **không đủ điều kiện**, ví dụ license, storage hoặc network.
- Sự kiện spike/thay đổi SLO làm tăng nhu cầu năng lực.

### Hằng tháng

- Đối chiếu **CUD Analysis**, **Billing Reports**, cost table và invoice-month dữ liệu đầy đủ.
- Đánh giá savings **sau khi trừ phí commitment**, so với kịch bản on-demand + SUD + các tối ưu khác.
- Gắn trách nhiệm finance và các team: phí cam kết không dùng được phân bổ cho ai?
- Cập nhật forecast, kế hoạch migrate và ngày hết hạn.
- Đề xuất purchase bổ sung chỉ nếu baseline bền vững; không phản ứng bằng mua thêm sau một đợt traffic spike.

### Trước khi commitment hết hạn

- Tái tính baseline từ usage hiện tại, không copy lượng cũ.
- Kiểm tra migration, giảm kích thước, thay region và sản phẩm mới.
- So sánh điều kiện pricing hiện hành với thời điểm mua cũ.
- Có quyết định renew, thu hẹp phạm vi hoặc quay lại on-demand theo mô hình được cho phép.

## 13. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| "Mọi VM chạy cả tháng đều giảm SUD 30%" | Chỉ machine series/resource đủ điều kiện; một số tối đa 20%, nhiều series không có SUD. | Kiểm tra series/SKU và billing account eligibility. |
| "SUD cần đăng ký trước" | SUD tự động với usage đủ điều kiện. | Không mua commitment chỉ để nhận SUD. |
| "CUD và SUD được cộng trên cùng giờ chạy" | Discount types loại trừ nhau với cùng lượng usage. | Phân tích phần usage covered và uncovered. |
| "Mua CUD bằng số giờ trung bình tháng" | Commitment phải phù hợp baseline theo thời gian và scope. | Xem hourly distribution, percentiles và các ngày thấp điểm. |
| "CUD tự đặt trước capacity" | Discount contract khác với reservation. | Thiết kế reservation riêng khi cần bảo đảm năng lực. |
| "Mọi khoản Cloud Run/GKE/VM đều được compute flexible CUD" | Chỉ selected eligible SKUs/billing modes. | Xem SKU Group và service-specific pricing. |
| "Không thấy credit nghĩa là không có CUD" | Spend-based CUD mới có discounted consumption models. | Đọc consumption model và CUD Analysis. |
| "Coverage cao nghĩa là mua đúng" | Có thể utilization thấp và phí bỏ không. | Đọc cả coverage, utilization, savings sau fee. |
| "Gọi CUD recommendation là đủ để mua" | Model lịch sử không biết kế hoạch tương lai. | Bổ sung forecast và approval của FinOps/owner. |
| "Có thể hủy commitment khi workload giảm" | Commitment tạo nghĩa vụ trả phí theo thời hạn. | Review điều kiện, stop/go approval trước khi mua. |
| "Chỉ xem cost của một project" | Commitment fee/savings có thể được phân bổ theo billing account. | Đánh giá toàn billing account rồi attribution theo project. |
| "Mua thêm CUD để chữa bill tăng đột biến" | Spike có thể không bền vững. | Ưu tiên điều tra traffic, rightsizing, quota và baseline. |

## 14. Bài thực hành đọc và phân tích CUD/SUD

Thực hiện **chỉ ở chế độ đọc**, không cần mua cam kết:

1. Chọn một Cloud Billing account mà bạn được cấp quyền xem báo cáo. Nếu không có quyền, dùng dữ liệu giả định của bài để tính.
2. Mở **Billing → Reports**, lọc Compute Engine; ghi lại eligible usage, credit SUD (nếu có), spend-based CUD discounts hoặc resource-based CUD credits và commitment fee lines.
3. Mở **CUD Analysis → Coverage** cho khoảng thời gian 30 hoặc 90 ngày; ghi phần usage có CUD, còn on-demand.
4. Chuyển sang **Utilization**, xem từng commitment hoặc scope; ghi nhận các giờ underutilized.
5. Lấy ví dụ một machine series có và một series không có SUD. Giải thích vì sao tỉ lệ discount khác nhau.
6. Giả định một workload còn chạy 18 tháng; so sánh 12-month versus 36-month commitment về savings và lock-in risk.
7. Viết một **CUD purchase decision memo** ngắn gồm baseline, expected savings, downside case, rollout/migration plan và người phê duyệt.
8. Chỉ đề xuất mua sau khi memo được review và điều khoản sản phẩm được xác minh.

Bảng tổng hợp có thể dùng trong review:

| Hạng mục | Câu hỏi trả lời trước khi mua |
| --- | --- |
| Candidate | CUD thuộc loại resource-based hay spend-based? |
| Scope | Billing account, project, region, machine family, eligible SKUs cụ thể? |
| Baseline | Usage/spend thấp nhất có tính lặp lại là bao nhiêu? |
| Existing savings | Có SUD/CUD khác hoặc contract pricing nào đang áp dụng? |
| Terms | 1 hay 3 năm, phí định kỳ, đơn vị committed spend, ngày bắt đầu? |
| Risk | Dừng/migrate workload, thay region, không đủ utilization thì sao? |
| Recovery | Có thể chuyển eligible usage từ project khác để dùng commitment không? |
| Decision | Net savings kỳ vọng, break-even, phê duyệt và lịch review? |

## 15. Checklist nắm vững CUD và SUD

- [ ] Giải thích được SUD tự động theo eligible usage trên 25% billing month.
- [ ] Nhớ SUD tối đa 20% hoặc 30% tùy series; không áp dụng mọi loại VM.
- [ ] Phân biệt resource-based CUD và spend-based/flexible CUD.
- [ ] Biết CUD thường có thời hạn 1 hoặc 3 năm và tạo phí cam kết.
- [ ] Hiểu CUD không tự bảo đảm reservation/capacity.
- [ ] Không áp dụng đồng thời SUD và CUD trên cùng phần usage.
- [ ] Biết resource-based CUD chịu ràng buộc region/series, và sharing phụ thuộc billing account.
- [ ] Biết compute flexible CUD có thể bao phủ eligible Compute Engine/GKE/Cloud Run spend nhưng không phải mọi SKU.
- [ ] Phân biệt CUD legacy credits và discounted consumption models mới.
- [ ] Tính được coverage, utilization, savings và kiểm tra đơn vị.
- [ ] So sánh CUD với phương án on-demand **có SUD**, không chỉ list price.
- [ ] Dùng Billing Reports, CUD Analysis và CUD Recommender để đánh giá trước khi mua.
- [ ] Biết commitments khó hoặc không thể hủy/giảm sau khi mua; có quy trình approval.
- [ ] Quyết định lượng commitment theo baseline, không theo traffic peak.
- [ ] Lập quy trình theo dõi utilization, expiration, migration và unused fees.
- [ ] Cân nhắc rightsizing, scheduling và Spot trước khi khóa chi phí nhiều năm.

## Tài liệu tham khảo

- [Google Cloud — Committed use discounts overview](https://docs.cloud.google.com/docs/cuds) — loại CUD, phạm vi dịch vụ và thời hạn cam kết.
- [Compute Engine — Committed use discounts overview](https://docs.cloud.google.com/compute/docs/instances/committed-use-discounts-overview) — resource-based và compute flexible CUD, phạm vi, eligible usage, thứ tự áp dụng.
- [Compute Engine — Resource-based CUDs](https://docs.cloud.google.com/compute/docs/instances/signing-up-committed-use-discounts) — cấu hình cam kết tài nguyên, ràng buộc region và loại machine.
- [Compute Engine — Sustained use discounts](https://docs.cloud.google.com/compute/docs/sustained-use-discounts) — cơ chế tự động, mốc sử dụng, dòng máy eligible và tỷ lệ 20%/30%.
- [Spend-based CUDs và consumption models](https://docs.cloud.google.com/docs/cuds-multiprice) — discounted prices thay cho legacy credits, hướng dẫn mua và migration.
- [Compute Engine reservations with commitments](https://docs.cloud.google.com/compute/docs/instances/reservations-with-commitments) — phân biệt commitment và capacity reservation.
- [Cloud Billing — CUD Analysis](https://docs.cloud.google.com/billing/docs/how-to/analyze-cuds) — coverage, utilization, savings và hiệu quả commitment.
- [Cloud Billing — CUD recommendations](https://docs.cloud.google.com/docs/cuds-recommender) — usage insights, đề xuất mức cam kết.
- [Cloud Billing — Savings and credits reports](https://docs.cloud.google.com/billing/docs/how-to/reports/savings-and-credits) — chi phí, discounts, credits và attribution.
- [Cloud Billing — Compute flexible CUD savings](https://docs.cloud.google.com/billing/docs/how-to/cud-analysis-flexible) — tính savings và tài nguyên eligible.
- [Cloud Billing — Export usage cost data to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery) — thiết lập export và phân tích hóa đơn theo SKU.

