# Cam kết sử dụng và quyền lợi giảm giá theo mô hình nhà cung cấp

Nhà cung cấp cloud thường giảm đơn giá compute khi khách hàng cam kết sử dụng tài nguyên hoặc chi tiêu trong một thời hạn. Các chương trình này có thể giảm đáng kể chi phí VM, container, serverless hoặc GPU đủ điều kiện, nhưng đổi lại tổ chức phải duy trì mức sử dụng hoặc khoản chi đã cam kết. Nếu mua quá nhiều, phần commitment không được dùng vẫn có thể bị tính phí; nếu mua quá ít, phần usage vượt cam kết tiếp tục chịu giá theo nhu cầu.

Trong module **CLOUD_CORE_SERVICES_COMPUTE**, quyết định mua commitment cần dựa trên workload thực tế: VM chạy liên tục, node pool nền, worker biến động, function theo request, GPU theo chiến dịch và capacity cần giữ cho availability. Bài học này giải thích các mô hình cam kết phổ biến, phân biệt quyền lợi giảm giá với bảo đảm capacity, cách ước tính mức cam kết, theo dõi utilization/coverage và chọn chương trình theo mô hình của AWS, Microsoft Azure và Google Cloud.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt pay-as-you-go, reservation, reserved instance, savings plan và committed use discount.
- Giải thích khác biệt giữa cam kết theo tài nguyên và cam kết theo mức chi tiêu.
- Phân biệt billing discount với capacity reservation.
- Đọc các thuộc tính của commitment: thời hạn, phạm vi, loại tài nguyên, vùng, mức chi tiêu và phương thức thanh toán.
- Tính utilization, coverage, unused commitment và hiệu quả tiết kiệm thực tế.
- Chọn baseline ổn định để cam kết mà không khóa toàn bộ peak hoặc workload biến động.
- So sánh các mô hình AWS, Azure và Google Cloud ở mức nguyên tắc.
- Xây dựng quy trình mua, phân bổ, theo dõi, điều chỉnh và gia hạn commitment.
- Nhận diện rủi ro khi thay đổi instance family, region, kiến trúc, license hoặc mức sử dụng.

## 1. Mô hình trả tiền compute

Cloud compute có thể được tính phí theo thời gian chạy, mức tài nguyên được cấp, số request, thời gian thực thi hoặc mức sử dụng thực tế. Các lựa chọn phổ biến gồm:

| Mô hình | Cách tính cơ bản | Phù hợp với |
|---|---|---|
| On-demand / pay-as-you-go | Trả theo mức sử dụng thực tế, không cam kết dài hạn | Workload mới, biến động, ngắn hạn hoặc khó dự báo |
| Reserved capacity / reservation | Giữ trước một loại capacity hoặc cấu hình theo điều kiện nhà cung cấp | Workload cần bảo đảm khả năng có tài nguyên ở vùng/loại máy cụ thể |
| Reserved Instance / resource commitment | Cam kết dùng cấu hình hoặc nhóm tài nguyên đủ điều kiện trong thời hạn | Workload ổn định, cấu hình ít thay đổi |
| Savings plan / spend commitment | Cam kết mức chi tiêu compute theo giờ hoặc kỳ tính phí để nhận đơn giá thấp hơn | Workload ổn định về ngân sách nhưng có thể đổi loại máy/dịch vụ |
| Committed use discount (CUD) | Cam kết mức tài nguyên hoặc mức chi tiêu theo sản phẩm/phạm vi | Workload có baseline dự đoán được |
| Spot / interruptible | Dùng capacity dư với giá thấp hơn, có thể bị thu hồi | Batch, CI, xử lý nền có retry/checkpoint |
| Serverless per-request | Trả theo request, thời gian thực thi và tài nguyên cấu hình | Traffic không đều, ít tải nền hoặc workload event-driven |

Tên gọi và điều kiện cụ thể khác nhau giữa nhà cung cấp. Không nên giả định “reservation”, “commitment” hoặc “savings plan” ở các cloud có cùng phạm vi hoặc cùng quyền lợi.

### 1.1. Vì sao nhà cung cấp giảm giá khi có cam kết?

Commitment giúp nhà cung cấp dự báo nhu cầu, lập kế hoạch capacity và giảm biến động sử dụng. Đổi lại, khách hàng chấp nhận nghĩa vụ thanh toán trong thời hạn, thường từ một đến vài năm tùy chương trình.

Mức giảm giá phụ thuộc vào:

- Thời hạn cam kết.
- Mức trả trước hoặc lịch thanh toán.
- Loại tài nguyên và sản phẩm đủ điều kiện.
- Phạm vi áp dụng: project, subscription, account, region hoặc instance family.
- Mức độ linh hoạt khi thay đổi cấu hình.
- Chương trình cụ thể và điều khoản tại thời điểm mua.

Giá niêm yết, tỷ lệ giảm và điều kiện trao đổi/hủy có thể thay đổi. Luôn dùng trang giá và điều khoản hiện hành trong billing account của tổ chức khi lập đề xuất mua.

### 1.2. Discount và capacity reservation là hai quyền lợi khác nhau

Một commitment có thể giảm giá cho usage đủ điều kiện nhưng không bảo đảm rằng một VM/GPU cụ thể sẽ luôn có sẵn tại một zone. Ngược lại, capacity reservation có thể giữ khả năng khởi tạo tài nguyên nhưng không nhất thiết tự tạo discount.

| Câu hỏi | Billing discount | Capacity reservation |
|---|---|---|
| Mục tiêu | Giảm đơn giá cho usage đủ điều kiện | Bảo đảm khả năng có tài nguyên theo phạm vi reservation |
| Có cam kết thanh toán? | Thường có với commitment plan | Tùy loại reservation và dịch vụ |
| Bảo đảm instance có thể khởi tạo? | Không mặc nhiên | Có thể, theo điều khoản/loại reservation |
| Có thể áp dụng cho nhiều cấu hình? | Tùy mức linh hoạt của chương trình | Thường gắn với region/zone/family/capacity cụ thể hơn |
| Ví dụ | Savings Plan hoặc CUD | Zonal capacity reservation hoặc reserved capacity |

Nếu workload cần cả chi phí thấp và capacity chắc chắn, có thể phải kết hợp hai cơ chế. Xác minh cách quyền lợi được áp dụng đồng thời và tránh tính cùng một usage hai lần trong mô hình tiết kiệm.

## 2. Commitment theo tài nguyên và theo chi tiêu

Hai nhóm cam kết phổ biến khác nhau ở đơn vị mà khách hàng hứa sử dụng.

### 2.1. Resource-based commitment

Resource-based commitment cam kết một lượng tài nguyên cụ thể, ví dụ số vCPU, RAM, GPU hoặc một cấu hình instance trong region/nhóm sản phẩm nhất định.

Đặc điểm thường gặp:

- Phù hợp khi workload ổn định về cấu hình và vùng triển khai.
- Có thể có mức giảm tốt hơn khi cam kết ít linh hoạt hơn.
- Dễ định lượng số tài nguyên được bao phủ.
- Có rủi ro unused commitment nếu workload giảm hoặc chuyển sang cấu hình không đủ điều kiện.
- Phải xem quy tắc thay đổi size, family, OS, tenancy, region và phạm vi chia sẻ.

Ví dụ: tổ chức cam kết 32 vCPU và 128 GiB RAM Compute Engine trong một region trong thời hạn nhất định. Nếu usage thực tế chuyển sang region khác hoặc loại tài nguyên không thuộc phạm vi, commitment có thể không được sử dụng hết.

### 2.2. Spend-based commitment

Spend-based commitment cam kết một mức chi tiêu cho usage đủ điều kiện, thường được đo theo số tiền mỗi giờ hoặc kỳ tính phí. Quyền lợi giảm giá được áp dụng cho usage đủ điều kiện trong phạm vi của chương trình.

Đặc điểm thường gặp:

- Linh hoạt hơn khi instance family, size hoặc dịch vụ đủ điều kiện thay đổi.
- Không nhất thiết bảo đảm một loại máy cụ thể.
- Có thể áp dụng trên nhiều project/subscription/region tùy chương trình.
- Phần commitment không được hấp thụ bởi usage đủ điều kiện vẫn có thể tạo chi phí không được tận dụng.
- Cần hiểu thứ tự áp dụng discount và quy tắc phân bổ benefit.

Ví dụ: tổ chức cam kết 20 USD mỗi giờ cho một nhóm compute đủ điều kiện. Nếu usage đủ điều kiện thấp hơn mức này, phần cam kết dư không tự động chuyển thành tín dụng có thể dùng cho dịch vụ bất kỳ.

### 2.3. So sánh hai cách cam kết

| Tiêu chí | Theo tài nguyên | Theo chi tiêu |
|---|---|---|
| Đơn vị commitment | vCPU, RAM, GPU, instance/configuration hoặc đơn vị tài nguyên | USD/giờ hoặc mức chi tiêu theo kỳ |
| Tính linh hoạt | Thường thấp hơn | Thường cao hơn trong phạm vi eligible usage |
| Rủi ro chính | Workload đổi cấu hình/vùng khiến tài nguyên cam kết không được dùng | Eligible spend giảm khiến phần cam kết không được hấp thụ |
| Phù hợp | Baseline compute ổn định, cấu hình rõ | Workload có thể thay đổi loại compute nhưng mức chi tiêu tương đối ổn định |
| Cần theo dõi | Mức dùng từng loại tài nguyên và vùng | Mức sử dụng benefit theo giờ/kỳ và phạm vi eligible |

## 3. Thuộc tính cần đọc trước khi mua

Đừng so sánh hai chương trình chỉ bằng phần trăm giảm giá. Cần chuẩn hóa các thuộc tính sau:

### 3.1. Thời hạn (term)

Thời hạn có thể là một năm, ba năm hoặc cấu trúc khác tùy chương trình. Term dài hơn thường có thể cho đơn giá thấp hơn nhưng làm tăng rủi ro khi workload thay đổi.

Hãy xem:

- Ngày bắt đầu và ngày hết hạn.
- Có tự động gia hạn không và điều kiện gia hạn.
- Cam kết có thể thay đổi, trao đổi, hủy hoặc hoàn tiền không.
- Điều khoản có khác nhau giữa reservation và savings plan không.
- Điều gì xảy ra khi account/subscription/project được chuyển hoặc đóng.

Không mua term dài chỉ vì tỷ lệ giảm cao nếu roadmap compute, region hoặc license chưa ổn định.

### 3.2. Phạm vi áp dụng (scope)

Scope xác định usage nào được hưởng benefit. Có thể là:

- Một resource hoặc instance family.
- Một region hoặc tập region.
- Một project, subscription, account hoặc billing account.
- Một nhóm dịch vụ đủ điều kiện.
- Usage của một tổ chức hoặc nhóm account liên kết.

Scope rộng tăng khả năng hấp thụ benefit khi workload di chuyển giữa project/team, nhưng có thể làm việc phân bổ chi phí khó hơn. Scope hẹp dễ gắn ownership nhưng tăng rủi ro unused khi tài nguyên thay đổi.

### 3.3. Đơn vị cam kết và mức commitment

Đơn vị có thể là:

- Số vCPU/RAM/GPU mỗi giờ.
- Số instance thuộc family/region.
- Mức USD/giờ.
- Mức chi tiêu theo tháng hoặc kỳ entitlement.

Phải phân biệt commitment amount với On-Demand spend. Ví dụ, cam kết 10 USD/giờ không nhất thiết có nghĩa usage theo giá niêm yết là 10 USD/giờ; đó có thể là mức benefit hoặc giá trị cam kết theo định nghĩa riêng của chương trình.

### 3.4. Phương thức thanh toán

Một số chương trình cho phép trả trước toàn bộ, trả trước một phần hoặc trả theo kỳ. So sánh tổng nghĩa vụ trong cả term, không chỉ dòng tiền tháng đầu.

Xem xét:

- Tổng chi phí danh nghĩa trong term.
- Cash flow và ngân sách CAPEX/OPEX.
- Ảnh hưởng tỷ giá, thuế và billing currency.
- Hóa đơn khi usage vượt commitment.
- Hóa đơn khi usage thấp hơn commitment.
- Chi phí license/OS/network/storage có nằm trong benefit hay không.

## 4. Tính mức tiết kiệm và mức sử dụng commitment

Mục tiêu là đo khoản tiền thực sự tiết kiệm sau khi tính unused commitment và usage vượt phạm vi. Không nên dùng phần trăm discount quảng cáo như mức tiết kiệm chắc chắn của toàn bộ hóa đơn.

### 4.1. Các chỉ số cơ bản

**Commitment utilization** đo mức benefit đã được usage đủ điều kiện hấp thụ:

\[
Utilization = \frac{Used\ commitment\ benefit}{Purchased\ commitment\ benefit} \times 100\%
\]

**Coverage** đo tỷ lệ eligible usage được benefit bao phủ:

\[
Coverage = \frac{Eligible\ usage\ covered}{Total\ eligible\ usage} \times 100\%
\]

**Effective savings** so sánh chi phí thực tế sau commitment với chi phí giả định nếu dùng On-Demand cho cùng lượng usage:

\[
Effective\ savings = \frac{OnDemand\ baseline - Actual\ cost}{OnDemand\ baseline} \times 100\%
\]

Định nghĩa cách tính cần nhất quán với hóa đơn: credit, tax, support, license, network và storage có thể không nằm trong cùng phạm vi.

### 4.2. Ví dụ resource-based commitment

Giả sử một nhóm compute có nhu cầu On-Demand ổn định 100 đơn vị tài nguyên mỗi giờ. Giá On-Demand là 0,10 USD/đơn vị/giờ. Một commitment giảm đơn giá xuống 0,07 USD/đơn vị/giờ và tổ chức cam kết 80 đơn vị mỗi giờ.

| Kịch bản | Usage thực tế | Chi phí nếu On-Demand | Chi phí với commitment | Nhận xét |
|---|---:|---:|---:|---|
| Dùng đúng 80 | 80 | 8,00 USD | 5,60 USD | Toàn bộ commitment được dùng; tiết kiệm 30% |
| Dùng 100 | 100 | 10,00 USD | 5,60 + 2,00 = 7,60 USD | 80 đơn vị được giảm giá, 20 đơn vị trả On-Demand |
| Chỉ dùng 60 | 60 | 6,00 USD | 5,60 USD | Commitment dư 20 đơn vị; tiết kiệm thực tế chỉ khoảng 6,7% |
| Chỉ dùng 20 | 20 | 2,00 USD | 5,60 USD | Chi phí commitment cao hơn On-Demand khoảng 3,60 USD |

Đây là mô hình số học minh họa cho commitment theo tài nguyên có nghĩa vụ thanh toán toàn bộ lượng đã cam kết. Cách áp dụng và giá thực tế của từng nhà cung cấp có thể khác.

### 4.3. Ví dụ spend-based commitment

Giả sử một chương trình yêu cầu cam kết 10 USD/giờ cho eligible usage. Trong một giờ, usage đủ điều kiện chỉ đạt mức benefit tương đương 7 USD; phần còn lại của commitment không được sử dụng. Ở giờ khác, eligible usage tương đương 14 USD; benefit chỉ áp dụng đến giới hạn commitment và phần vượt chịu mức giá theo quy tắc chương trình.

Điểm cần kiểm tra trong báo cáo billing:

- Commitment được đo theo On-Demand equivalent hay theo giá sau discount?
- Benefit unused có được carry forward không?
- Benefit được áp dụng theo giờ, tháng hay entitlement window?
- Usage nào được tính eligible?
- Benefit được chia giữa project/team theo thứ tự nào?

Không tự giả định phần unused của giờ này bù được phần vượt ở giờ khác. Một số chương trình đo theo giờ, một số có cửa sổ khác; phải dùng đúng semantics của sản phẩm.

### 4.4. Discount rate không phải effective savings

Nếu chương trình quảng bá giảm 40% cho usage đủ điều kiện nhưng chỉ 50% baseline được commitment bao phủ và 80% commitment được sử dụng, tiết kiệm thực tế của toàn bộ eligible spend thấp hơn nhiều so với 40%.

Khi trình bày business case, luôn đưa:

- On-Demand baseline.
- Eligible usage.
- Commitment amount.
- Expected utilization và coverage.
- Usage vượt commitment.
- Unused commitment.
- Total cost và effective savings.

## 5. Chọn baseline để cam kết

Commitment nên dựa trên phần workload ổn định, không dựa trên peak hoặc một tháng bất thường.

### 5.1. Phân tích lịch sử usage

Thu thập dữ liệu đủ dài để bao gồm ngày thường, cuối tuần, mùa cao điểm, release, batch window và các đợt tăng tải. Phân tích:

- Compute usage theo giờ/ngày/tháng.
- Instance family, size, region và OS/license.
- CPU/memory utilization và thời gian idle.
- Minimum capacity phục vụ HA và failure scenarios.
- Autoscaling baseline, peak và trough.
- Workload đã cam kết trước đó và ngày hết hạn.
- Dịch vụ đủ điều kiện theo chương trình.

### 5.2. Dùng baseline ổn định thay vì peak

Ví dụ workload có compute usage theo giờ:

```text
Tải nền ban đêm:       40 units
Ngày làm việc:         65 units
Giờ cao điểm:         100 units
Sự kiện theo mùa:     140 units
```

Nếu cam kết 100 units vì đó là peak thường thấy, phần usage ban đêm có thể tạo unused commitment. Một chiến lược thận trọng hơn là cam kết phần baseline ổn định, còn phần burst dùng On-Demand, autoscaling hoặc Spot nếu workload chịu được gián đoạn.

### 5.3. Phân loại workload

| Loại workload | Độ ổn định | Cách tiếp cận |
|---|---|---|
| Database production chạy liên tục | Cao | Có thể phù hợp với resource-based hoặc reservation phù hợp |
| API baseline luôn cần tối thiểu replica | Trung bình đến cao | Cam kết baseline, phần scale-out dùng linh hoạt |
| Worker theo queue | Biến động | Cam kết mức nền nhỏ; phần burst theo nhu cầu |
| GPU training theo chiến dịch | Thấp đến trung bình | Chỉ cam kết khi lịch sử và roadmap đủ ổn định |
| CI/test ephemeral | Thấp | Ưu tiên pay-as-you-go hoặc Spot/interruptible |
| Serverless theo request | Phụ thuộc traffic và chương trình | Kiểm tra eligibility, baseline và spend window |
| Disaster recovery standby | Có thể ổn định nhưng ít dùng | Phân biệt chi phí giữ capacity với benefit theo usage |

### 5.4. Loại bỏ lãng phí trước khi mua discount

Discount giảm đơn giá nhưng không sửa được overprovisioning. Trước khi cam kết:

- Rightsize VM/Pod và bỏ instance không dùng.
- Tắt môi trường dev/test ngoài giờ nếu phù hợp.
- Điều chỉnh autoscaling min/max và schedule.
- Dọn disk, snapshot, image và tài nguyên orphaned.
- Tối ưu CPU/RAM, storage IOPS và network.
- Đo cost per request/job thay vì chỉ nhìn tổng usage.

Chỉ cam kết trên baseline sau khi đã giảm waste. Nếu mua commitment trước rồi mới rightsize, utilization có thể tụt và lợi ích giảm giá bị triệt tiêu.

## 6. Các chương trình của nhà cung cấp

Tên chương trình, phạm vi, mức giảm, thời hạn và quyền trao đổi thay đổi theo sản phẩm, region, loại account và thời điểm. Các ví dụ dưới đây giúp hiểu cách phân loại; trước khi mua cần xác minh trong tài liệu và billing console hiện hành.

### 6.1. AWS

Các chương trình compute phổ biến gồm:

- **Compute Savings Plans:** cam kết một mức chi tiêu compute theo giờ. Theo tài liệu AWS, chương trình có tính linh hoạt cao trên EC2 và có thể áp dụng cho Fargate/Lambda đủ điều kiện, với phạm vi rộng hơn về instance family/size/region so với lựa chọn gắn chặt vào family/region.
- **EC2 Instance Savings Plans:** cam kết chi tiêu theo giờ trong một instance family và region; linh hoạt hơn theo size trong phạm vi chương trình nhưng hẹp hơn Compute Savings Plans.
- **EC2 Reserved Instances:** quyền lợi giá dựa trên thuộc tính và term của RI. Standard/Convertible, Regional/Zonal có quy tắc khác nhau về thay đổi và capacity.
- **On-Demand Capacity Reservations:** cơ chế giữ capacity EC2 theo Availability Zone; đây là quyền lợi capacity, khác với Savings Plans discount.

Điểm cần nhớ:

- Savings Plans thường là cam kết tài chính, không tự bảo đảm capacity.
- Compute Savings Plans có phạm vi linh hoạt hơn nhưng không nhất thiết cho mức discount giống mọi RI.
- EC2 RI và Capacity Reservation có thể có quan hệ áp dụng khác nhau theo loại RI và cấu hình.
- Savings Plans không áp dụng cho Spot usage theo tài liệu AWS.
- Term, payment option và eligible services cần kiểm tra theo loại plan.

### 6.2. Microsoft Azure

Các lựa chọn thường gặp:

- **Azure Reservations:** cam kết một loại resource/configuration trong thời hạn để nhận billing discount. Với VM, thuộc tính như region và instance family/size có thể ảnh hưởng phạm vi áp dụng.
- **Azure Savings Plan for Compute:** cam kết một mức chi tiêu compute theo giờ; benefit được áp dụng cho usage compute đủ điều kiện trong scope của plan.
- **Pay-as-you-go:** phù hợp với phần usage biến động hoặc chưa đủ ổn định để cam kết.

Điểm cần nhớ:

- Reservation là billing benefit và không làm thay đổi trạng thái runtime của resource.
- Reservation VM không mặc nhiên bao gồm mọi khoản software, network và storage; cần đọc phạm vi covered charges.
- Savings Plan linh hoạt hơn khi workload thay đổi giữa các loại compute đủ điều kiện.
- Điều kiện exchange/refund/cancel khác nhau giữa reservation và savings plan; không giả định có thể hủy mọi commitment.
- Scope có thể ảnh hưởng cách benefit được chia sẻ giữa subscription/billing scope.

### 6.3. Google Cloud

Google Cloud có các nhóm Committed Use Discounts (CUDs):

- **Resource-based CUDs:** cam kết mức tài nguyên Compute Engine, ví dụ vCPU, memory, GPU hoặc một số tài nguyên khác, thường gắn với region và project/scope theo chương trình.
- **Spend-based CUDs:** cam kết mức chi tiêu cho một sản phẩm/dịch vụ đủ điều kiện; đơn vị có thể là mức USD/giờ hoặc mô hình entitlement theo chương trình.
- **On-demand usage:** phần usage không được benefit bao phủ tiếp tục chịu mức giá tương ứng.

Điểm cần nhớ:

- Resource-based CUD phù hợp với nhu cầu tài nguyên dự đoán được.
- Spend-based CUD linh hoạt theo chi tiêu đủ điều kiện nhưng vẫn bị giới hạn bởi sản phẩm, billing account và scope.
- Một số CUD có tính region-specific; một số loại khác có phạm vi rộng hơn tùy dịch vụ.
- Cam kết thường có nghĩa vụ thanh toán trong term; không nên mua trước khi hiểu chính xác cách benefit được tính và phân bổ.

### 6.4. Bảng so sánh định hướng

| Nhà cung cấp | Cam kết theo tài nguyên | Cam kết theo chi tiêu | Cần chú ý |
|---|---|---|---|
| AWS | EC2 Reserved Instances; EC2 Instance Savings Plans gắn family/region | Compute Savings Plans theo mức USD/giờ | Phân biệt discount với On-Demand Capacity Reservation; eligibility theo EC2/Fargate/Lambda |
| Azure | Reservations cho resource/configuration đủ điều kiện | Savings Plan for Compute theo hourly spend | Covered charges, scope, exchange/refund policy và eligible services |
| Google Cloud | Resource-based CUD cho Compute Engine | Spend-based CUD theo sản phẩm/eligible usage | Region/project/billing scope, resource categories và term |

Bảng này chỉ mô tả nhóm mô hình. Không dùng nó thay cho điều khoản sản phẩm cụ thể, vì eligibility và quyền lợi có thể khác theo series, OS, region, account và ngày mua.

## 7. Commitment không thay thế capacity planning

Giảm giá không có nghĩa tài nguyên sẽ sẵn sàng trong một zone hoặc region khi cần. Workload yêu cầu HA, GPU cụ thể hoặc capacity cho DR phải có kế hoạch capacity riêng.

### 7.1. Capacity reservation

Capacity reservation nhằm giữ khả năng khởi tạo một loại tài nguyên trong phạm vi nhất định. Cần kiểm tra:

- Zone/region và instance family/size.
- Số lượng capacity được giữ.
- Thời điểm bắt đầu/kết thúc và trạng thái reservation.
- Có thể dùng cùng discount program nào.
- Chi phí khi reservation không được sử dụng.

### 7.2. Commitment discount

Discount commitment giúp giảm giá usage đủ điều kiện nhưng có thể không đảm bảo:

- Có đủ GPU hoặc instance type tại zone đang thiếu capacity.
- Có đủ IP/subnet, network interface hoặc quota.
- Database, storage hoặc NAT có capacity tương ứng.
- Workload đạt RTO/RPO khi một zone/region lỗi.

Khi lập kế hoạch production, tách rõ mục tiêu chi phí và mục tiêu availability. Một hệ thống có thể có commitment discount cho baseline, capacity reservation cho workload quan trọng và On-Demand headroom cho burst/failover.

## 8. Chiến lược kết hợp các mô hình giá

Không cần đưa toàn bộ workload vào cùng một chương trình. Có thể phân tầng theo độ ổn định và yêu cầu vận hành.

### 8.1. Baseline + burst

Một mô hình thường dùng:

- Commitment bao phủ phần baseline ổn định.
- On-Demand xử lý phần tải vượt baseline.
- Spot/interruptible chạy job có thể retry hoặc checkpoint.
- Serverless xử lý event/traffic không đều nếu cost profile phù hợp.
- Capacity reservation giữ tài nguyên quan trọng nếu yêu cầu availability.

### 8.2. Tách theo môi trường

| Môi trường | Hướng tiếp cận |
|---|---|
| Production core | Cam kết baseline đã chứng minh; capacity plan riêng cho HA |
| Staging | Lịch bật/tắt, rightsizing, commitment nếu usage ổn định và đủ điều kiện |
| Development | Pay-as-you-go, shared pool hoặc tắt ngoài giờ |
| Batch/ETL | Spot/interruptible hoặc On-Demand theo deadline; commitment chỉ cho baseline ổn định |
| DR standby | Đánh giá chi phí giữ capacity, storage replication và mức readiness yêu cầu |

### 8.3. Tránh overcommit

Overcommit xảy ra khi tổng nghĩa vụ cam kết lớn hơn usage đủ điều kiện ổn định. Để hạn chế:

- Chừa phần biến động và mùa vụ.
- Không cộng usage Spot hoặc resource không đủ điều kiện vào baseline.
- Loại usage sắp decommission hoặc có roadmap đổi platform.
- Tính các commitment hiện có trước khi mua thêm.
- Dùng forecast thận trọng và stress scenario.
- Mua theo từng đợt, đánh giá utilization rồi mới tăng.

## 9. Quy trình mua commitment

### Bước 1: Làm sạch baseline

Thu thập hóa đơn và usage theo service, region, family, OS, environment, account và team. Rightsize trước khi chọn mức cam kết.

### Bước 2: Xác định eligible usage

Đọc điều kiện chương trình để biết usage nào được áp dụng benefit. Loại khỏi baseline các khoản không đủ điều kiện như storage, network, license hoặc Spot nếu chương trình không bao phủ.

### Bước 3: Phân loại ổn định và biến động

Chia usage thành:

- Baseline liên tục.
- Seasonal/predictable burst.
- Unpredictable burst.
- Ephemeral/test.
- DR/failover capacity.

### Bước 4: Chọn loại commitment

Chọn resource-based khi cấu hình ổn định; chọn spend-based khi eligible spend ổn định hơn cấu hình. So sánh flexibility, scope, term và nghĩa vụ thanh toán.

### Bước 5: Mô phỏng các kịch bản

Tính cost khi usage thấp, bằng baseline, cao hơn baseline và thay đổi region/family. Xem unused commitment và On-Demand overage.

### Bước 6: Phê duyệt

Business case cần có:

- Tổng commitment và term.
- On-Demand baseline.
- Expected utilization/coverage.
- Effective savings.
- Rủi ro underutilization và workload change.
- Owner và cost center.
- Điều kiện review, renewal và exit.

### Bước 7: Mua theo từng đợt

Mua mức vừa phải cho baseline đã xác nhận, theo dõi 1–3 chu kỳ billing hoặc khoảng thời gian đại diện rồi mới tăng nếu utilization ổn định. Chu kỳ cụ thể tùy term và tốc độ thay đổi workload.

## 10. Theo dõi utilization, coverage và cost allocation

Sau khi mua, commitment cần được quản lý như một tài sản tài chính có owner.

### 10.1. Dashboard commitment

Theo dõi:

- Purchased commitment và remaining term.
- Utilization theo giờ/ngày/tháng.
- Coverage của eligible usage.
- Unused commitment và usage vượt benefit.
- Cost avoidance so với On-Demand baseline.
- Phân bổ benefit theo project/subscription/team.
- Thay đổi workload làm commitment không còn phù hợp.
- Upcoming expiry và renewal recommendation.

### 10.2. Showback và chargeback

- **Showback:** báo cho team biết benefit/chi phí commitment đang được phân bổ thế nào.
- **Chargeback:** ghi nhận phần chi phí commitment vào cost center theo quy tắc tổ chức.

Nếu một billing account chia sẻ benefit cho nhiều project, cần quy tắc phân bổ minh bạch. Không nên để một team mua commitment nhưng team khác sử dụng benefit mà không có ownership hoặc cơ chế chia sẻ chi phí.

### 10.3. Cảnh báo

Đặt cảnh báo khi:

- Utilization giảm dưới ngưỡng trong nhiều kỳ.
- Coverage giảm vì workload đổi family/region hoặc dịch vụ.
- Eligible usage vượt commitment kéo dài.
- Có resource mới nhưng chưa được bao phủ.
- Commitment sắp hết hạn hoặc tự động gia hạn.
- Một project/team không còn dùng benefit được phân bổ.

Ngưỡng nên dựa trên baseline và mục tiêu tài chính; không có tỷ lệ utilization duy nhất phù hợp cho mọi chương trình.

## 11. Ví dụ: chọn commitment cho nền tảng API

Một nền tảng API có ba nhóm compute:

- API production tối thiểu luôn cần 40 vCPU.
- Autoscaling có thể tăng thêm 20–60 vCPU vào giờ cao điểm.
- Worker batch cần 0–30 vCPU và có thể bị trì hoãn.

### 11.1. Phân loại usage

| Nhóm | Baseline | Peak | Độ ổn định | Hướng xem xét |
|---|---:|---:|---|---|
| API core | 40 vCPU | 60 vCPU | Cao | Resource commitment hoặc spend plan phù hợp |
| API burst | 0 | 20 vCPU | Biến động | On-Demand hoặc autoscaling |
| Batch worker | 0 | 30 vCPU | Không liên tục | Spot/interruptible hoặc On-Demand theo deadline |

### 11.2. Mức commitment ban đầu

Tổ chức không nên cam kết 90 vCPU chỉ vì đó là peak cộng worker. Một lựa chọn thận trọng là phân tích baseline 40 vCPU trong nhiều tháng, kiểm tra roadmap và region, rồi cam kết một phần hoặc toàn bộ baseline đủ điều kiện. Phần burst giữ linh hoạt.

### 11.3. Theo dõi sau mua

Sau khi mua, nếu API core giảm từ 40 xuống 25 vCPU do tối ưu code hoặc chuyển container platform, utilization có thể giảm. Cần đánh giá thay đổi scope/exchange nếu chương trình cho phép, hoặc đưa usage khác đủ điều kiện vào scope nếu chính sách cho phép. Nếu không có cách điều chỉnh, phải tính unused commitment trong forecast đến hết term.

## 12. Các yếu tố làm commitment mất hiệu quả

### 12.1. Thay đổi kiến trúc

Di chuyển VM sang serverless, thay instance family, đổi region hoặc chuyển sang managed service có thể khiến usage không còn eligible. Trước migration, lập bản đồ commitment hiện tại và ngày hết hạn.

### 12.2. Rightsizing sau khi đã mua

Rightsizing giảm usage và có thể làm commitment thừa. Điều này không có nghĩa nên tránh tối ưu; hãy tính tổng cost sau rightsizing thay vì giữ tài nguyên lãng phí chỉ để tận dụng discount.

### 12.3. Seasonality và business downturn

Cam kết dựa trên mùa cao điểm có thể bị unused khi nhu cầu giảm. Dùng baseline qua nhiều chu kỳ, forecast và scenario downside.

### 12.4. Scope và account changes

Chuyển subscription/project/account hoặc thay cấu trúc tổ chức có thể làm benefit không còn áp dụng như dự kiến. Xác minh billing scope, sharing configuration và quyền quản trị.

### 12.5. Currency, tax và billing differences

Giá niêm yết, currency, thuế, support plan, license và cách phân bổ credit có thể khiến chi phí thực tế khác mô hình. Dùng dữ liệu invoice thực tế để đối chiếu.

## 13. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chọn commitment chỉ theo discount rate cao nhất | Có thể khóa usage không ổn định | So effective savings và rủi ro unused |
| Cam kết theo peak | Dư commitment trong giờ thấp tải | Cam kết baseline, xử lý burst linh hoạt |
| Nhầm discount với capacity reservation | Có discount nhưng không khởi tạo được tài nguyên cần thiết | Lập capacity reservation riêng nếu cần |
| Không rightsize trước khi mua | Giảm giá cho tài nguyên dư thừa | Loại waste rồi mới tính baseline |
| Coi mọi dịch vụ compute đều eligible | Benefit không áp dụng cho một số usage | Kiểm tra product/region/family/OS eligibility |
| Không tính scope | Benefit nằm ở account/project khác với usage | Chọn scope và sharing rõ ràng |
| Không theo dõi utilization | Commitment dư kéo dài đến hết term | Dashboard, alert và owner |
| Dùng Spot vào baseline cam kết | Usage có thể không đủ điều kiện hoặc không ổn định | Tách Spot khỏi baseline commitment |
| Mua term dài khi roadmap chưa rõ | Khó thay đổi khi migration/rightsizing | Chọn term phù hợp độ chắc chắn và flexibility |
| Không tính phần vượt commitment | Tổng cost cao hơn dự báo | Mô phỏng baseline, burst và peak |
| Gia hạn tự động mà không review | Khóa mức commitment cũ dù nhu cầu đã đổi | Review trước renewal và phê duyệt lại |

## 14. Checklist trước khi mua và trong vận hành

**Trước khi mua**

- [ ] Đã rightsize và loại bỏ resource không dùng.
- [ ] Đã phân tích usage theo giờ/region/family/service trong khoảng thời gian đại diện.
- [ ] Đã xác định eligible usage và các khoản không được bao phủ.
- [ ] Đã tách baseline, burst, seasonal, batch và DR capacity.
- [ ] Đã so resource-based với spend-based commitment.
- [ ] Đã đọc term, scope, payment, exchange/cancel/refund và renewal terms.
- [ ] Đã tính unused commitment, overage và effective savings.
- [ ] Đã có owner, cost center và phê duyệt ngân sách.

**Trong vận hành**

- [ ] Theo dõi utilization và coverage theo kỳ.
- [ ] Theo dõi unused commitment và usage vượt benefit.
- [ ] Phân bổ benefit minh bạch giữa team/project.
- [ ] Review khi đổi instance family, region, architecture hoặc license.
- [ ] Cảnh báo trước khi commitment hết hạn.
- [ ] Đánh giá lại forecast trước renewal.
- [ ] Tách billing discount khỏi capacity reservation và HA requirement.

## 15. Kết luận

Commitment giảm đơn giá compute để đổi lấy nghĩa vụ sử dụng tài nguyên hoặc chi tiêu trong một thời hạn. Resource-based commitment phù hợp với nhu cầu cấu hình ổn định; spend-based commitment linh hoạt hơn khi eligible spend ổn định nhưng loại compute có thể thay đổi. Cả hai đều có rủi ro unused commitment nếu baseline giảm hoặc usage không còn đủ điều kiện.

Hãy rightsize trước, phân tích lịch sử usage, xác định baseline, kiểm tra scope/term/eligibility và mô phỏng kịch bản thấp-cơ sở-cao trước khi mua. Theo dõi utilization, coverage, unused benefit và effective savings trong suốt term. Quan trọng nhất, tách quyền lợi giảm giá khỏi bảo đảm capacity: workload cần HA hoặc tài nguyên khan hiếm vẫn phải có kế hoạch capacity reservation và quota riêng.

## Tài liệu nhà cung cấp tham khảo

- [AWS – What are Savings Plans?](https://docs.aws.amazon.com/savingsplans/latest/userguide/what-is-savings-plans.html)
- [AWS – Compute Savings Plans and Reserved Instances](https://docs.aws.amazon.com/savingsplans/latest/userguide/sp-ris.html)
- [Microsoft Azure – Decide between a savings plan and a reservation](https://learn.microsoft.com/en-us/azure/cost-management-billing/savings-plan/decide-between-savings-plan-reservation)
- [Microsoft Azure – What are Azure Reservations?](https://learn.microsoft.com/en-us/azure/cost-management-billing/reservations/save-compute-costs-reservations)
- [Google Cloud – Committed use discounts](https://docs.cloud.google.com/docs/cuds)

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Pay-as-you-go | Thanh toán theo mức sử dụng thực tế, không có commitment dài hạn. |
| Commitment | Nghĩa vụ sử dụng tài nguyên hoặc chi tiêu trong thời hạn đã chọn. |
| Resource-based commitment | Cam kết một lượng tài nguyên hoặc cấu hình cụ thể. |
| Spend-based commitment | Cam kết một mức chi tiêu cho usage đủ điều kiện. |
| Reserved Instance | Chương trình giá ưu đãi gắn với thuộc tính tài nguyên theo quy tắc nhà cung cấp. |
| Savings Plan | Chương trình giảm giá đổi lấy mức chi tiêu compute đã cam kết. |
| Committed Use Discount (CUD) | Quyền lợi giảm giá khi cam kết tài nguyên hoặc chi tiêu trên Google Cloud. |
| Capacity reservation | Cơ chế giữ khả năng khởi tạo tài nguyên trong phạm vi xác định. |
| Utilization | Tỷ lệ commitment benefit đã được usage đủ điều kiện sử dụng. |
| Coverage | Tỷ lệ eligible usage được benefit bao phủ. |
| Unused commitment | Phần cam kết không được usage đủ điều kiện hấp thụ. |
| Effective savings | Mức tiết kiệm thực tế so với baseline On-Demand tương đương. |
| Scope | Phạm vi resource/project/subscription/account được áp dụng benefit. |
| Term | Thời hạn commitment. |
| Eligible usage | Usage đáp ứng điều kiện của chương trình giảm giá. |
