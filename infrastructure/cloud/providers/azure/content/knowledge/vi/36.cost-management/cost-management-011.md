# Quản lý cam kết chi tiêu và đánh giá chi phí mỗi workload

## 1. Vì sao không thể đánh giá chi phí chỉ bằng tổng hóa đơn?

Một hệ thống Azure thường chạy nhiều workload với đặc điểm khác nhau: API production hoạt động liên tục, dịch vụ xử lý đơn hàng tăng tải theo giờ, môi trường phát triển chỉ dùng trong giờ làm việc, cơ sở dữ liệu có công suất khá ổn định và công cụ phân tích dữ liệu chạy theo đợt. Nếu chỉ nhìn một con số chi phí toàn subscription, đội kỹ thuật khó biết **workload nào tạo giá trị, phần chi nào lãng phí và khoản cam kết chi tiêu nào thực sự có hiệu quả**.

Trong chương **Quản lý chi phí** của module `CLOUD_PROVIDERS_AZURE`, bài học này kết hợp kiến thức Azure từ subscription, resource group, Microsoft Entra ID/RBAC, Virtual Network, compute, storage, database, giám sát và bảo mật để giải quyết hai bài toán:

1. **Quản lý cam kết:** nên trả theo mức dùng thực tế (pay-as-you-go), mua Azure Reservations hay Azure Savings Plan for Compute ở phần tải nào? Ai có quyền mua, theo dõi sử dụng và chịu rủi ro khi workload thay đổi?
2. **Đánh giá từng workload:** phải phân bổ compute, dữ liệu, mạng, monitoring, dịch vụ dùng chung và ưu đãi cam kết thế nào để so sánh đúng chi phí và hiệu quả kinh doanh?

Sau bài này, người học có thể thu thập baseline, phân loại chi phí, tính điểm hòa vốn của cam kết, đọc các chỉ số utilization/coverage, thiết kế báo cáo unit economics, nhận diện chi phí chưa phân bổ và xây quy trình ra quyết định có bằng chứng.

**Nguyên tắc xuyên suốt:** mua cam kết là **quyết định tài chính dựa trên mô hình sử dụng dài hạn**, không phải thao tác giảm giá tự động cho mọi tài nguyên. Một mức giảm giá danh nghĩa lớn vẫn có thể làm tăng chi phí nếu khối lượng công việc không còn sử dụng được quyền lợi đã mua.

## 2. Bản đồ chi phí của một workload Azure

**Workload** là tập hợp tài nguyên và hoạt động cung cấp một khả năng nghiệp vụ cụ thể, ví dụ `orders-prod` xử lý đơn hàng. Workload có thể trải qua nhiều resource group, subscription và cả dịch vụ dùng chung; vì vậy resource group không luôn tương đương ranh giới tổng chi phí của workload.

~~~mermaid
flowchart TB
    W["Workload: orders-prod"] --> C["Compute: VM / App Service / AKS"]
    W --> D["Data: Azure SQL / Storage / Backup"]
    W --> N["Network: NAT / Gateway / Egress"]
    W --> O["Observability: Azure Monitor / Logs"]
    W --> S["Shared platform: Firewall / DNS / Identity"]
    W --> P["Chi phí phân bổ của cam kết / discount"]
    C --> M["Workload cost và unit economics"]
    D --> M
    N --> M
    O --> M
    S --> M
    P --> M
~~~

Tổng chi phí nên được chia thành các nhóm có thể giải thích:

| Nhóm | Ví dụ Azure | Điểm thường bị bỏ sót |
| --- | --- | --- |
| **Compute** | VM, VMSS, container/AKS node, App Service plan, một số dịch vụ serverless | Idle capacity, scale-out, instance không được gắn owner, mức hưởng discount |
| **Database** | Azure SQL, PostgreSQL, Cosmos DB và dịch vụ dữ liệu tương ứng | Storage, backup, read replicas, throughput, geo-replication |
| **Storage/backup** | Blob, Managed Disks, snapshots, backup vault | Dữ liệu cũ, loại redundancy, restore testing, transaction operations |
| **Networking** | Public IP, NAT Gateway, Load Balancer, Firewall, VPN/ExpressRoute, egress | Phí theo giờ và dung lượng truyền, traffic xuyên vùng hoặc qua region |
| **Monitoring/security** | Log Analytics ingestion/retention, Application Insights, dịch vụ bảo mật | Debug logs, lưu giữ quá dài, công cụ dùng chung |
| **Shared platform** | DNS, hub VNet, gateway, firewall, Key Vault, CI/CD agents | Nằm ở subscription của nhóm platform, thiếu tag workload |
| **Commitment/discount** | Reservation, savings plan, enterprise discount, Azure Hybrid Benefit nếu áp dụng | Mua trước, phần chưa dùng, quyền lợi áp dụng sang workload khác |

Để so sánh đúng, định nghĩa các lớp dữ liệu:

- **Direct cost:** chi phí có thể gắn trực tiếp với resource/workload.
- **Allocated shared cost:** phần chi phí nền tảng dùng chung được phân bổ theo quy tắc rõ ràng.
- **Unallocated cost:** khoản chưa đủ thông tin để gắn về một workload; phải hiển thị riêng.
- **Commitment-adjusted cost:** chi phí theo cách phân bổ lợi ích cam kết nhất quán, không cộng trùng khoản mua cam kết và mức sử dụng đã hưởng ưu đãi.

Một báo cáo tốt cho phép xem cả **chi phí vận hành của workload** và **mức chi/giá trị cam kết của toàn tổ chức**. Hai góc nhìn này có thể khác nhau về thời điểm ghi nhận, nhưng cần được đối soát về tổng.

## 3. Các cơ chế chi phí và cam kết thường gặp

### 3.1. Pay-as-you-go: trả theo mức sử dụng

Với mô hình trả theo mức dùng, tổ chức trả phí theo các meter và đơn giá áp dụng cho tài khoản, hợp đồng, dịch vụ, region và thời điểm. Đây là lựa chọn linh hoạt cho tải không ổn định, môi trường tạm, workload mới và trường hợp chưa biết hình dạng nhu cầu tương lai.

Linh hoạt không có nghĩa chi phí thấp nhất: một VM hoặc workload đủ điều kiện chạy ổn định nhiều giờ mỗi ngày có thể hưởng ưu đãi tốt hơn nếu được mua cam kết phù hợp. Tuy nhiên **đơn giá danh nghĩa** không đủ để ra quyết định; cần so sánh chi phí *trong toàn kỳ* và rủi ro giảm sử dụng.

### 3.2. Azure Reservations

**Azure Reservations** cung cấp ưu đãi giá cho **những dịch vụ/SKU được hỗ trợ** khi tổ chức cam kết theo kỳ hạn được sản phẩm cho phép, thường là một hoặc ba năm với nhiều sản phẩm. Cách tính và loại quyền lợi khác nhau theo dịch vụ: ví dụ VM reserved instances, các loại database hoặc dung lượng lưu trữ đủ điều kiện có thể có quy tắc riêng.

Đối với VM, reservation thường là **ưu đãi billing trên usage đủ điều kiện**; nó không tự động tạo VM, không buộc một VM cụ thể luôn chạy và **không mặc nhiên bảo đảm capacity được giữ chỗ trong một Availability Zone**. Azure Capacity Reservation và reservation discount là hai khái niệm khác nhau.

Các yếu tố cần kiểm tra trước khi mua:

- Loại dịch vụ/SKU, region, điều kiện về kích cỡ instance và scope áp dụng.
- Kỳ hạn, phương thức thanh toán và khả năng điều chỉnh sau mua theo chính sách sản phẩm hiện hành.
- Quy tắc áp dụng discount theo mức sử dụng và các dịch vụ/tính phí **không được bao phủ** như disk, egress, license hoặc phần phí riêng, tùy cấu hình.
- Lượng usage đủ điều kiện theo **từng giờ**; mức sử dụng thiếu trong giờ có thể làm quyền lợi bị bỏ trống và không tự tích lũy sang giờ sau.

**Không giả định có thể hủy, exchange hoặc hoàn tiền reservation mà không mất phí.** Quy tắc đổi/hủy, giới hạn và cách xử lý phụ thuộc dịch vụ, chương trình mua và chính sách Azure có hiệu lực tại thời điểm giao dịch; phải xác nhận trong điều khoản thực tế trước khi phê duyệt.

### 3.3. Azure Savings Plan for Compute

**Azure Savings Plan for Compute** là cơ chế cam kết **mức chi mỗi giờ** cho phần compute đủ điều kiện trong kỳ hạn được cung cấp (thường có lựa chọn một hoặc ba năm). Đổi lại, mức sử dụng compute đáp ứng điều kiện có thể nhận đơn giá ưu đãi, theo quy tắc áp dụng của sản phẩm.

Khác với reservation thường gắn chặt hơn với loại tài nguyên/đặc tính cấu hình, savings plan hướng tới tính linh hoạt trong nhóm compute đủ điều kiện. Tuy nhiên:

- Không phải mọi dịch vụ Azure, mọi meter và mọi loại chi phí compute đều nằm trong danh sách được hưởng.
- Cam kết **theo giờ** vẫn phát sinh nghĩa vụ thanh toán ngay cả khi usage đủ điều kiện trong giờ đó thấp.
- Phần usage vượt khả năng sử dụng cam kết được tính theo đơn giá thích hợp theo hợp đồng và quy tắc Azure; **không phải toàn bộ workload mặc nhiên được giảm giá**.
- Một savings plan đã mua thường bị ràng buộc theo kỳ hạn; phải xác nhận điều khoản mua, thay đổi và khả năng hủy, không lập kế hoạch dựa trên giả định có thể thoát cam kết dễ dàng.

### 3.4. Azure Hybrid Benefit và điều khoản giá khác

**Azure Hybrid Benefit** (khi tổ chức có giấy phép đủ điều kiện) có thể làm giảm thành phần license của một số workload Windows Server/SQL hoặc sản phẩm hỗ trợ. Đây là quyền lợi liên quan đến **license và điều kiện sử dụng**, không tương đương Reservation hay Savings Plan.

Các loại ưu đãi, tín dụng, giá theo hợp đồng doanh nghiệp và chương trình khuyến mại cũng ảnh hưởng chi phí thực trả. Không cộng phần trăm ưu đãi một cách máy móc: các cơ chế có **điều kiện áp dụng và thứ tự xử lý riêng**, và một workload có thể chỉ được hưởng một tập con của các ưu đãi đó.

### 3.5. Cam kết hợp đồng tổng thể và cam kết tài nguyên là khác nhau

Một số tổ chức có **cam kết chi tiêu Azure theo hợp đồng** (ví dụ cam kết tiêu thụ trong một thỏa thuận thương mại). Đây là nghĩa vụ tài chính ở tầng hợp đồng, khác với việc mua một reservation hay savings plan để áp dụng đơn giá ưu đãi cho usage cụ thể.

| Hình thức | Đơn vị quyết định | Rủi ro chính |
| --- | --- | --- |
| Pay-as-you-go | Meter, giờ hoặc lượt sử dụng thực tế | Đơn giá bình quân cao nếu tải ổn định đủ điều kiện ưu đãi |
| Reservation | Đặc tính tài nguyên/dịch vụ đủ điều kiện và kỳ hạn | Cấu hình/region/tải thay đổi khiến quyền lợi không dùng hết |
| Savings Plan for Compute | Mức cam kết chi tiêu compute mỗi giờ và kỳ hạn | Mua quá cao so với mức usage đủ điều kiện theo giờ |
| Cam kết hợp đồng Azure | Nghĩa vụ tổng thể theo hợp đồng của tổ chức | Chi tiêu không đủ điều kiện/không đạt mức cam kết theo điều khoản |
| Azure Hybrid Benefit | Quyền sử dụng giấy phép có đủ điều kiện | Thiếu quyền license, không đáp ứng điều kiện cấp phép hoặc áp dụng sai |

**Không tự suy luận rằng khoản mua một sản phẩm ưu đãi chắc chắn được tính vào cam kết hợp đồng.** Tính đủ điều kiện, cách ghi nhận và chính sách thanh toán phải kiểm tra theo thỏa thuận cụ thể.

## 4. Reservation và savings plan khác nhau ở điểm nào?

| Câu hỏi | Azure Reservations | Azure Savings Plan for Compute |
| --- | --- | --- |
| Cam kết điều gì? | Sử dụng/cấu hình dịch vụ hoặc tài nguyên đủ điều kiện trong một kỳ hạn | Mức chi compute đủ điều kiện trên mỗi giờ trong một kỳ hạn |
| Linh hoạt khi đổi loại compute? | Phụ thuộc loại reservation, quy tắc size flexibility/scope và điều kiện dịch vụ | Thường linh hoạt hơn trong tập compute đủ điều kiện |
| Phù hợp với | Tải nền ổn định, cấu hình và region tương đối dự đoán được | Nhu cầu compute ổn định về tổng nhưng có thể dịch chuyển giữa các dạng compute được hỗ trợ |
| Nguy cơ underutilization | Giờ không có usage phù hợp để hưởng discount | Giờ usage đủ điều kiện thấp hơn mức cam kết tiền |
| Có đảm bảo VM capacity không? | Không tự động đảm bảo capacity cho VM | Không |
| Có tự động tối ưu mọi dịch vụ Azure không? | Không | Không |
| Xác minh điều gì trước mua? | SKU, region, scope, thời hạn, utilization, quy tắc đổi/hủy | Eligible compute, mức tiêu thụ theo giờ, scope, thời hạn, khả năng thay đổi |
| Chỉ số theo dõi | Utilization, coverage và khoản chưa dùng | Utilization của mức cam kết, coverage, tiết kiệm thực tế |

Một tổ chức có thể sở hữu **cả reservation và savings plan**. Azure áp dụng lợi ích theo cơ chế và quy tắc ưu tiên của hệ thống billing; khi phân tích phải dựa vào **usage đã được áp ưu đãi thực tế**, tránh giả định một giờ compute sẽ được nhận hai lần cùng một quyền lợi.

Cần xem đề xuất tối ưu trong Azure Advisor/Cost Management như **đầu vào quyết định**, không phải lệnh mua. Đề xuất dựa trên lịch sử sử dụng, còn kế hoạch sản phẩm, migration, thay đổi vùng và lịch tắt máy do đội nghiệp vụ cung cấp.

## 5. Thu baseline trước khi quyết định cam kết

### 5.1. Cần dữ liệu bao nhiêu lâu?

Với workload có lịch sử đủ ổn định, bắt đầu bằng vài chu kỳ sử dụng và đối chiếu xu hướng theo mùa, ngày trong tuần, giờ trong ngày, thay đổi release hoặc sự kiện sản phẩm. Dữ liệu 7 ngày có thể cho tín hiệu ban đầu nhưng ít đáng tin nếu workload có lịch batch hàng tháng hoặc traffic tăng mạnh vào cuối quý.

Các trường tối thiểu:

| Trường | Mục đích |
| --- | --- |
| Subscription ID, resource group, resource ID | Xác định ranh giới sở hữu và cost meter |
| Region, service, SKU/meter | Kiểm tra tính đủ điều kiện của ưu đãi |
| Usage date/hour, quantity, unit | Tính đặc tính tải, giờ không hoạt động, công suất nền |
| Actual cost, amortized cost nếu có | Đối soát chi phí mua cam kết và mức dùng |
| Pricing/benefit ID được cung cấp trong dữ liệu | Liên kết usage được hưởng reservation/savings plan |
| Workload, environment, owner, costCenter | Phân bổ cho đúng đơn vị |
| Application throughput/business unit | Tính chi phí trên một đơn vị giá trị |
| Kế hoạch 12–36 tháng | Ước lượng thay đổi công nghệ/khối lượng trong kỳ cam kết |

**Quan sát theo giờ là quan trọng.** Hai workload có cùng tổng 720 vCPU-hours một tháng nhưng một workload chạy đều cả tháng còn workload kia chỉ chạy 72 giờ với công suất gấp mười. Chúng có thể cần chiến lược cam kết khác nhau.

### 5.2. Thu thập dữ liệu trong Azure Portal

Luồng tham khảo, tùy account/scope đang hỗ trợ:

1. Mở **Azure Portal → Cost Management** ở subscription, resource group hoặc billing scope cần phân tích.
2. Vào **Cost Analysis**; chọn một khoảng thời gian đủ đại diện, cách xem chi phí và granularity phù hợp.
3. Group by **Service name**, **Resource**, **Resource group**, **Meter** hoặc **Tag** khi có dữ liệu.
4. So sánh **Actual cost** và **Amortized cost** khi tính năng được hỗ trợ để hiểu các khoản mua cam kết và phân bổ.
5. Xem mục liên quan đến **Reservations**, **Savings plans**, Recommendations, Utilization/Coverage theo vai trò/quyền của tài khoản.
6. Với phân tích lặp lại, cấu hình **Cost Management exports / cost details** về nơi lưu trữ được bảo vệ hoặc dùng API thích hợp, rồi lưu snapshot có thời điểm truy xuất.

Giao diện và một số dữ liệu khác nhau theo loại thỏa thuận, scope, phiên bản API và quyền. Có độ trễ nhập dữ liệu; không dùng biểu đồ của ngày hiện tại để kết luận chi phí cuối cùng của ngày đã hoàn tất.

### 5.3. Định nghĩa đường cơ sở “không có cam kết”

Để đánh giá lợi ích cam kết, cần một mô hình **chi phí thay thế hợp lý** nếu không có cam kết, tính theo giá có hiệu lực với tài khoản và usage đủ điều kiện. Không nên dùng “giá niêm yết công khai” nếu tổ chức đã có giá hợp đồng hoặc lợi ích license khiến mức so sánh khác.

Gọi:

- `C_on_demand`: chi phí dự kiến của cùng usage theo phương án không mua cam kết mới, đã xét các ưu đãi hợp lệ hiện có.
- `C_committed`: tiền cam kết phải trả trong kỳ cộng chi phí usage ngoài cam kết và các khoản phát sinh liên quan.
- `Savings_net = C_on_demand - C_committed`.

Nếu `Savings_net` dương, phương án cam kết giảm chi phí trong **giả định đang dùng**; nhưng còn phải xét độ không chắc chắn của forecast, chi phí cơ hội và rủi ro nghĩa vụ dài hạn.

## 6. Bài toán hòa vốn: mua reservation có đáng không?

Ví dụ thuần túy để học cách tính. Giả sử một đơn vị compute đủ điều kiện có:

- Đơn giá on-demand giả định: **0,28 USD/giờ**.
- Đơn giá hiệu dụng của reservation khi tính trên toàn bộ giờ cam kết: **0,19 USD/giờ**.
- Một tháng mẫu dài **720 giờ** (30 ngày).
- Chỉ mua **một** đơn vị capacity tương ứng; bỏ qua các khoản disk, network, license hoặc thuế không thuộc ưu đãi trong phép so sánh này.

Nếu trả theo mức dùng và workload thực sự chạy `H` giờ:

~~~text
Cost_on_demand = H × 0,28

Cost_reservation = 720 × 0,19 = 136,80 USD

Break-even hours = 136,80 / 0,28
                 ≈ 488,57 giờ/tháng

Break-even utilization ≈ 488,57 / 720 ≈ 67,9%
~~~

| Mức sử dụng của đơn vị compute | Giờ dùng | On-demand | Reservation cho tháng | Chênh lệch (on-demand − reservation) |
| --- | ---: | ---: | ---: | ---: |
| 50% | 360 | 100,80 USD | 136,80 USD | **−36,00 USD** |
| 65% | 468 | 131,04 USD | 136,80 USD | **−5,76 USD** |
| 85% | 612 | 171,36 USD | 136,80 USD | **+34,56 USD** |
| 100% | 720 | 201,60 USD | 136,80 USD | **+64,80 USD** |

Dấu `+` cho thấy tiết kiệm trong ví dụ; dấu `−` cho thấy trả nhiều hơn vì không sử dụng đủ cam kết.

**Giới hạn của ví dụ:** Giá là giả định để học, không phải giá Azure hiện hành. Reservation thực tế có cách tính theo thời hạn/meter, điều kiện đủ chuẩn, chính sách áp dụng và khả năng hưởng lợi của nhiều resource trong scope. Giá có thể khác theo region/SKU/OS/hợp đồng; tháng thực tế không cố định 720 giờ. Không được dùng con số 67,9% làm ngưỡng mua bắt buộc cho mọi loại reservation.

### 6.1. Đo utilization theo giờ, không lấy trung bình mù quáng

Một reservation có thể bao phủ các tài nguyên phù hợp trong **scope áp dụng**, không nhất thiết một VM cố định. Tuy nhiên discount không biến usage của giờ ít tải thành quyền lợi cộng dồn cho giờ cao điểm sau. Do đó, cần vẽ biểu đồ lượng usage phù hợp **theo giờ** để xác định phần nền có thể cam kết.

Nếu workload có 24 giờ sử dụng ổn định, reservation dễ khớp hơn. Nếu chỉ chạy giờ hành chính nhưng cùng subscription có workload khác cùng loại dùng ngoài giờ, một phạm vi chia sẻ discount **có thể** cải thiện utilization, miễn là các tài nguyên thực sự đủ điều kiện và quy tắc scope cho phép.

### 6.2. Cẩn thận với thay đổi kiến trúc

Trong kỳ cam kết, workload có thể:

- Chuyển từ VM sang dịch vụ khác không hưởng cùng reservation.
- Đổi region, size family hoặc OS/licensing, làm giảm khả năng khớp.
- Giảm tải nhờ cache, code tối ưu hoặc thay đổi business.
- Tăng tải theo đợt rồi giảm sâu sau chiến dịch.
- Được di chuyển sang subscription/billing scope khác.

Một mô hình tiết kiệm nên có ít nhất **kịch bản cơ sở, thấp và cao**, không chỉ ngoại suy đường thẳng từ tháng gần nhất.

## 7. Cách tính cam kết Azure Savings Plan for Compute

Với savings plan, con số cần quyết định là **mức chi compute được cam kết mỗi giờ**, trên các loại usage đủ điều kiện. Lợi ích phụ thuộc mức sử dụng đủ điều kiện theo từng giờ và giá ưu đãi cụ thể.

Giả sử một tổ chức đang cân nhắc mức cam kết **2,00 USD/giờ**. Đây là **số minh họa**, không phải mức đề xuất từ Azure hay mức tối thiểu được hệ thống xác nhận.

~~~text
Cam kết cho 1 giờ = 2,00 USD
Chi phí cam kết cho 30 ngày (720 giờ)
                   = 2,00 × 720
                   = 1.440 USD
~~~

Hãy xét hai tình huống về **lượng usage đủ điều kiện quy về chi phí ở đơn giá savings plan trong giờ** (chỉ mô hình hóa mức tiêu thụ cam kết, chưa phải hóa đơn đầy đủ):

| Tình huống | Usage đủ điều kiện ở mức giá ưu đãi/giờ | Giá trị cam kết sử dụng | Phần cam kết chưa dùng |
| --- | ---: | ---: | ---: |
| Giờ tải thấp | 1,50 USD | 1,50 USD | 0,50 USD |
| Giờ tải cao | 2,50 USD | 2,00 USD | 0 USD |

Khi usage vượt cam kết, **phần usage còn lại** chịu quy tắc tính giá và quyền lợi thực tế của Azure; không được lấy chênh `0,50 USD` ở bảng trên rồi mặc định phần vượt được tính đúng 0,50 USD giá ưu đãi. Billing engine áp dụng cam kết và định giá usage ngoài cam kết theo cơ chế hỗ trợ.

**Điểm cốt lõi:** Giờ tải thấp có thể để thừa một phần nghĩa vụ thanh toán; giờ tải cao không “bù lại” phần cam kết đã thừa ở giờ trước. Vì vậy cần phân tích **phân bố hourly eligible consumption**, không chỉ tổng chi tiêu tháng.

### 7.1. Chọn mức cam kết theo tải nền

Một phương pháp thực tế:

1. Thu chuỗi hourly usage đủ điều kiện trong thời gian đại diện.
2. Loại bỏ những spike bất thường hoặc dự báo thay đổi kiến trúc chưa phản ánh trong lịch sử.
3. Xem phân vị thấp và mức tiêu thụ lặp lại phần lớn các giờ, cộng với kế hoạch tăng/giảm tải.
4. Tính phương án nhiều mức cam kết ứng viên và chi phí còn lại theo quy tắc giá áp dụng.
5. Ưu tiên phương án **không làm đội tài chính bị khóa vào mức chi không còn phù hợp** nếu workload giảm mạnh.
6. Sau khi mua, theo dõi utilization/coverage, xem cả phần cam kết chưa dùng và usage on-demand còn lại.

Không mặc định Savings Plan luôn tối ưu hơn Reservation hoặc ngược lại. Với workload khá cố định, reservation phù hợp có thể cho hiệu quả khác với mức tiết kiệm và độ linh hoạt của savings plan; cần so sánh đề xuất và dữ liệu thực tế của tài khoản.

## 8. Các chỉ số quản lý cam kết cần đọc đúng

### 8.1. Utilization và coverage

**Utilization** thể hiện **bao nhiêu phần quyền lợi/cam kết đã được sử dụng** trong khoảng thời gian, theo cách Azure định nghĩa cho sản phẩm đó. **Coverage** thể hiện **bao nhiêu phần usage đủ điều kiện của tập workload đang được áp ưu đãi**. Tùy loại cam kết, số liệu có thể dựa trên giờ, mức chi hoặc các normalized units khác.

Ví dụ khái niệm:

~~~text
Utilization = quyền lợi/cam kết thực sự sử dụng
              --------------------------------- × 100%
                  tổng quyền lợi/cam kết khả dụng

Coverage = usage đủ điều kiện được hưởng ưu đãi
           ------------------------------------ × 100%
                   tổng usage đủ điều kiện
~~~

Không tự diễn giải đây là công thức billing chính xác cho mọi Azure reservation/savings plan; dashboard Azure có thể định nghĩa utilization/coverage theo đơn vị cụ thể của từng sản phẩm.

| Quan sát | Ý nghĩa gợi ý | Hành động |
| --- | --- | --- |
| **Utilization cao, coverage thấp** | Cam kết đang dùng tốt nhưng nhiều usage chưa được phủ | Đánh giá nhu cầu mua thêm khi có baseline bền vững |
| **Utilization thấp, coverage cao** | Có thể thừa cam kết trên giờ/tài nguyên không còn sử dụng | Kiểm tra scope, resize, workload thay đổi và điều khoản điều chỉnh |
| **Cả hai cao** | Cam kết khớp tốt tập usage hiện tại | Theo dõi thay đổi tải, hạn dùng và cost thực |
| **Cả hai thấp** | Cam kết không khớp hoặc workload giảm/đổi cấu hình | Điều tra eligibility, scope, quyền lợi chưa dùng và kế hoạch tương lai |

**Utilization 100% không đồng nghĩa tổng chi phí được tối ưu.** Nếu một savings plan bị sử dụng hết mỗi giờ nhưng nhiều giờ còn usage on-demand lớn, có thể vẫn có cơ hội cam kết thêm. Ngược lại, coverage gần 100% nhưng utilization thấp có thể báo hiệu đã mua quá nhiều.

### 8.2. Amortized cost và lợi ích cam kết

Khi mua trước reservation hoặc savings plan, **Actual cost** có thể ghi khoản mua tại thời điểm thanh toán, còn usage được giảm giá hoặc có phần giá được khấu trừ. **Amortized cost** thường phân bổ giá trị cam kết theo thời gian và usage phù hợp, giúp nhìn chi phí vận hành từng workload nhất quán hơn.

Ví dụ một reservation được trả trước 1.440 USD cho khoảng giả định 12 tháng và không có thay đổi giá trị theo thời gian. Phân tích đơn giản chia đều:

~~~text
Chi phí phân bổ theo tháng ≈ 1.440 / 12 = 120 USD/tháng
~~~

Nhưng **phép chia 1/12 chỉ là minh họa**: bảng dữ liệu amortized thực tế dựa trên thời gian hiệu lực, usage được áp benefit, các khoản chưa dùng và cách tính của Azure. Không tự viết phép chia thay thế dữ liệu cost chính thức trong báo cáo tài chính nếu doanh nghiệp yêu cầu đối soát chặt chẽ.

### 8.3. Unused commitment là khoản chi cần có chủ sở hữu

**Unused reservation/unused savings plan commitment** là phần quyền lợi/giá trị mua nhưng chưa được sử dụng trong kỳ theo quy tắc sản phẩm. Khoản này vẫn có thể tạo chi phí tổ chức. Khi phân bổ workload, nên ghi riêng:

- `Covered usage cost`: phần chi của workload có được hưởng lợi ích.
- `Uncovered eligible usage`: phần usage đủ điều kiện nhưng không nhận ưu đãi.
- `Unused commitment cost`: phần cam kết không sử dụng, có owner rõ ràng.
- `Commitment management adjustment`: chênh lệch hoặc bút toán điều chỉnh nếu phương pháp nội bộ yêu cầu.

Nếu chỉ gán phần hưởng lợi cho các workload mà **bỏ quên unused commitment**, dashboard có thể thể hiện tổng chi phí các workload thấp hơn nghĩa vụ thực tế của tổ chức.

## 9. Quản lý scope áp dụng quyền lợi và quyền sở hữu

Azure có những lựa chọn scope áp dụng benefit (ví dụ một subscription, phạm vi chia sẻ đủ điều kiện hoặc các scope được sản phẩm hỗ trợ). Các lựa chọn chính xác phụ thuộc Reservation/Savings Plan, loại thỏa thuận billing và chính sách hiện hành.

### 9.1. Một workload sở hữu cam kết riêng

Ví dụ subscription sản xuất chạy workload `orders-prod` ổn định. Một nhóm có thể được giao ngân sách, trách nhiệm và quyền theo dõi reservation riêng. Lợi ích của cách này là dễ quy trách nhiệm; hạn chế là khi `orders-prod` giảm tải, cam kết có thể còn thừa dù workload khác ở subscription khác vẫn có usage tương thích.

### 9.2. Chia sẻ quyền lợi giữa các workload

Nếu có nhiều ứng dụng trong cùng phạm vi đủ điều kiện và các workload dùng service/SKU tương thích, tổ chức có thể chọn scope dùng chung để tăng utilization. Khi đó phải định nghĩa **phân bổ lợi ích và unused cost**:

- Workload A sử dụng discount trong giờ nào?
- Workload B có quyền lợi tương ứng không, hay cơ chế billing tự phân bổ theo usage?
- Ai chịu chi phí của giờ cam kết chưa dùng?
- Một workload mới có thể làm thay đổi phần discount từng workload nhận trong báo cáo hay không?
- Chủ sở hữu tài chính nào duyệt mua, gia hạn, thay đổi phạm vi và xử lý tranh chấp chargeback?

Quyền tạo/xem cam kết và quyền Cost Management không nhất thiết giống quyền quản lý VM. Sử dụng Microsoft Entra ID/RBAC và vai trò billing/Reservation/Savings Plan phù hợp để phân tách **người đề xuất, người duyệt mua, người quản lý benefit và người nhận báo cáo**.

## 10. Tạo mô hình phân bổ chi phí theo workload

### 10.1. Quy ước dữ liệu cần nhất quán

Trước tiên xác định các khóa:

| Khóa | Ví dụ | Vai trò |
| --- | --- | --- |
| `workload` | `orders`, `catalog`, `analytics` | Sản phẩm/khả năng nghiệp vụ |
| `environment` | `prod`, `staging`, `dev` | Mục đích vận hành |
| `costCenter` | `CC-042` | Chủ sở hữu tài chính |
| `owner` | `team-orders` | Đội chịu trách nhiệm kỹ thuật |
| `subscriptionId` | ID subscription | Phạm vi phân tích và quyền |
| `resourceId` | ARM resource ID | Tìm resource phát sinh chi phí |
| `billingPeriod` | `2026-11` | Đối soát cùng kỳ |
| `benefitId` | ID quyền lợi nếu dữ liệu có | Theo dõi usage của reservation/savings plan |

Tags giúp showback/chargeback nhưng **không có nghĩa là luôn đầy đủ**. Một số charge, chi phí mua cam kết, chi phí chia sẻ, resource dùng chung hoặc dữ liệu quá khứ không có tag. Vì vậy, cần thêm **bảng mapping** theo resource ID, subscription, owner và thời điểm hiệu lực.

### 10.2. Quy tắc phân bổ trực tiếp, chia sẻ và chưa phân bổ

Xây mô hình phân bổ minh bạch:

~~~text
Workload allocated cost
  = Direct amortized cost
  + Allocated shared platform cost
  + Allocated unused commitment (nếu chính sách quy định)
  + Other approved adjustments

Unallocated cost
  = Total in-scope cost
  - Sum(allocated workload costs)
~~~

Trong báo cáo, cần phân biệt dòng **direct usage** và dòng **allocated shared cost** để không cộng trùng. Khi quy tắc phân bổ nội bộ dùng dữ liệu actual thay vì amortized, phải khai báo rõ và điều chỉnh phần mua cam kết tương ứng để vẫn đối soát được tổng.

**Quy tắc quan trọng:** Không lấy tổng actual (đã có khoản mua cam kết) rồi cộng thêm toàn bộ amortized usage trong cùng báo cáo như thể chúng là chi phí độc lập. Đây là lỗi double counting rất thường gặp khi ghép dữ liệu nhiều nguồn.

### 10.3. Ví dụ phân bổ chi phí Firewall dùng chung

Một Azure Firewall ở hub network phục vụ `orders-prod` và `catalog-prod`. Giả sử chi phí Firewall được phép phân bổ trong kỳ là **900 USD**, có cơ sở thống kê traffic phù hợp để chia:

| Workload | Tỷ lệ đo được theo quy tắc đã duyệt | Chi phí Firewall phân bổ |
| --- | ---: | ---: |
| `orders-prod` | 70% | 630 USD |
| `catalog-prod` | 30% | 270 USD |
| **Tổng** | **100%** | **900 USD** |

**Không mặc định tỷ lệ traffic là thước đo công bằng duy nhất.** Firewall có phần chi phí nền theo giờ và phần chi theo dữ liệu, nên có thể phải tách: chi phí nền phân bổ theo số workload/đặt trước, chi phí biến đổi phân bổ theo lưu lượng thực tế. Với các dịch vụ khác, dùng driver phù hợp như GB lưu trữ, số request, vCPU-hours, số user hoặc mức sử dụng thực tế.

Một mô hình allocation cần có **phiên bản quy tắc, owner, hiệu lực từ ngày nào** và khả năng tái hiện số liệu đã công bố. Khi đổi tỷ lệ, ghi rõ có restate kỳ cũ hay không.

### 10.4. Tài nguyên không tag và “chi phí mồ côi”

Tạo danh sách resource/cost row chưa có workload owner:

1. Rà theo resource ID và resource group.
2. Tìm trong deployment/IaC hoặc lịch sử tạo tài nguyên.
3. Gửi chủ sở hữu subscription/platform xác nhận.
4. Với charge không có resource ID tương ứng, lập quy tắc phân bổ theo service/billing scope.
5. Nếu chưa đủ bằng chứng, giữ mục **Unallocated** có số tiền và người phụ trách điều tra; đừng tự gán tùy tiện để làm đẹp tỷ lệ allocation.

## 11. Đánh giá hiệu quả chi phí theo đơn vị giá trị

Chi phí thấp hơn tổng thể **không luôn tốt hơn** nếu doanh thu/throughput hoặc chất lượng dịch vụ giảm nhiều hơn. Gắn chi phí với khối lượng nghiệp vụ giúp phân tích công bằng khi workload tăng trưởng.

### 11.1. Cost per business unit

Ví dụ `orders-prod` có tổng chi phí đã phân bổ trong tháng là **12.000 USD** (bao gồm phần phù hợp của compute, dữ liệu, mạng, monitoring và cam kết). Có **60.000 đơn hàng thành công, không trùng** được ghi nhận.

~~~text
Cost per successful order
  = 12.000 / 60.000
  = 0,20 USD / đơn hàng

Cost per 1.000 successful orders
  = 0,20 × 1.000
  = 200 USD
~~~

Nếu tháng sau chi phí là 13.500 USD nhưng số đơn thành công tăng lên 90.000:

~~~text
13.500 / 90.000 = 0,15 USD / đơn hàng
~~~

Tổng chi tăng, nhưng **chi phí trên đơn vị giá trị giảm 25%**. Đây có thể là dấu hiệu cải thiện hiệu quả, nếu SLO, bảo mật, chất lượng đơn hàng và cách tính chi phí giữa hai tháng nhất quán.

**Chọn mẫu số đúng:** không đếm cả request retry, event lặp, đơn hàng test hoặc đơn thất bại nếu mục tiêu là “chi phí trên một đơn thành công”. Với dữ liệu batch/analytics, có thể dùng chi phí trên GB xử lý hợp lệ, job thành công, 1.000 report, customer active hoặc đơn vị nghiệp vụ phù hợp.

### 11.2. Các chỉ số bổ trợ

| KPI | Cách hiểu | Lưu ý |
| --- | --- | --- |
| **Total allocated workload cost** | Tổng chi phí quy về workload | Kiểm tra direct/shared/unused |
| **Unit cost** | Chi phí trên giao dịch hoặc đơn vị giá trị | Chuẩn hóa denominator giữa kỳ |
| **Cost growth vs business growth** | So chi phí và tải/giá trị tăng thế nào | Chú ý mùa vụ và thay đổi chức năng |
| **Idle capacity ratio** | Tỷ lệ công suất không mang lại giá trị theo ngưỡng định nghĩa | Thận trọng với headroom bắt buộc để chịu lỗi |
| **Commitment utilization** | Mức dùng quyền lợi đã mua | Cần xem theo giờ và theo loại sản phẩm |
| **Eligible usage coverage** | Bao nhiêu usage có ưu đãi | Cao không bảo đảm không có overcommit |
| **Unallocated cost ratio** | Chi phí chưa gắn owner/tài nguyên | Theo dõi liên tục chất lượng dữ liệu |
| **Forecast accuracy** | Dự báo chênh thực tế ra sao | Cần chờ dữ liệu kỳ hoàn chỉnh |
| **Cost per SLO-compliant transaction** | Gắn chi phí với chất lượng phục vụ | Tránh tiết kiệm bằng cách giảm độ tin cậy |

Unit economics phải đi cùng **SLO và yêu cầu độ tin cậy**. Không nên xóa capacity dự phòng, backup hoặc logging bảo mật để làm giảm chi phí trên đơn hàng mà gây rủi ro outage hoặc vi phạm dữ liệu.

## 12. Mô hình báo cáo tháng: actual, amortized và phần unused

Giả sử ba workload dùng cùng subscription và một tập cam kết compute dùng chung. Báo cáo quản trị theo **amortized basis** có số liệu giả định:

| Khoản chi đã phân bổ | orders-prod | catalog-prod | analytics-batch | Tổng |
| --- | ---: | ---: | ---: | ---: |
| Direct compute/data/storage | 6.000 | 3.200 | 1.300 | 10.500 |
| Platform/network/observability chia sẻ | 1.200 | 700 | 300 | 2.200 |
| Phần unused commitment được phân bổ theo chính sách | 180 | 120 | 100 | 400 |
| **Tổng theo workload** | **7.380** | **4.020** | **1.700** | **13.100** |

Đơn vị tiền: **USD**, số liệu minh họa và phải được tính từ dữ liệu tương thích. Nếu doanh nghiệp chưa muốn phân bổ unused commitment về workload, có thể giữ dòng **“unused commitment – FinOps owner” = 400 USD** ở cấp platform và chỉ showback 12.700 USD vào các workload, miễn là tổng **12.700 + 400 = 13.100 USD** vẫn được đối soát.

**Không cộng thêm 400 USD nếu phần unused commitment đã có trong một nhóm chi phí ở nguồn dữ liệu.** Bảng trên giả định từng dòng loại trừ nhau và đã loại bỏ bút toán trùng. Trong thực tế, cần sử dụng cấu trúc dữ liệu amortized và cách trình bày benefit đã được xác minh với billing account.

### 12.1. Mẫu bảng nguồn dữ liệu

~~~csv
period,workload,environment,cost_category,allocation_method,amount_usd,owner
2026-11,orders,prod,direct,resource-id,6000,team-orders
2026-11,orders,prod,shared,approved-share,1200,team-platform
2026-11,orders,prod,unused-commitment,policy-v1,180,team-finops
2026-11,catalog,prod,direct,resource-id,3200,team-catalog
2026-11,catalog,prod,shared,approved-share,700,team-platform
2026-11,catalog,prod,unused-commitment,policy-v1,120,team-finops
2026-11,analytics,batch,direct,resource-id,1300,team-analytics
2026-11,analytics,batch,shared,approved-share,300,team-platform
2026-11,analytics,batch,unused-commitment,policy-v1,100,team-finops
~~~

CSV này là **định dạng báo cáo nội bộ giả định**, không phải schema chính thức mà Azure Cost Management xuất ra. Khi xây pipeline, cần mapping từ trường nguồn Azure có thật sang schema quản trị, lưu thông tin nguồn dữ liệu, thời gian extract và phiên bản quy tắc allocation.

### 12.2. Kiểm tra đối soát

Một báo cáo chỉ nên công bố khi:

~~~text
Total management cost (cùng basis và scope)
  = Sum(allocated workload cost)
  + Remaining unallocated cost
  + Approved reconciliation adjustments
~~~

Các khoản điều chỉnh có thể xuất phát từ độ trễ dữ liệu, credit/discount, rounding, currency conversion hoặc quy tắc phân bổ khoản mua trước. Phải ghi giải thích, không tự điều chỉnh một khoản để ép tổng bằng nhau.

## 13. Cost Management exports và dữ liệu lịch sử

Khi tổ chức có nhiều workload, thao tác export thủ công hàng tháng khó tái hiện. Một luồng dữ liệu thực tế:

~~~mermaid
flowchart LR
    A["Azure Cost Management cost details / exports"] --> B["Storage được bảo vệ"]
    B --> C["Xác thực schema, scope và thời gian"]
    C --> D["Resource-to-workload mapping + tags"]
    D --> E["Direct / shared / commitment allocation"]
    E --> F["Báo cáo FinOps theo workload"]
    F --> G["Budget, review và quyết định"]
~~~

Các điều kiện vận hành:

- Giới hạn quyền đọc dữ liệu billing/cost; đây có thể là thông tin thương mại nhạy cảm.
- Dùng Managed Identity hoặc cơ chế xác thực an toàn cho pipeline khi có thể.
- Giữ dữ liệu gốc và snapshot đã chuẩn hóa, có timestamp UTC và billing period.
- Xác nhận cost details schema, tên cột, loại dữ liệu, đơn vị tiền tệ và tính năng exports được hỗ trợ tại billing scope.
- Xử lý dữ liệu được cập nhật muộn hoặc điều chỉnh sau kỳ; báo cáo cần trạng thái **preliminary/finalized** theo chính sách.
- Chặn double counting khi nhập lại cùng bản export hoặc khi kết hợp actual/amortized của một giao dịch.
- Không đưa access key, SAS token, thông tin chiết khấu bí mật hoặc dữ liệu billing nhạy cảm vào repository hay log công khai.

Nếu sử dụng bảng dữ liệu chung giữa nhóm ứng dụng và FinOps, cần quyền theo phạm vi vì đơn giá hợp đồng, dữ liệu mua cam kết và thông tin thương mại có thể không phù hợp chia sẻ rộng rãi.

## 14. Đặt budget và cảnh báo sau khi có cam kết

Budget trả lời “mức chi có vượt kế hoạch không?”; reservation/savings plan trả lời “có ưu đãi nào phù hợp với usage không?”. Hai công cụ **bổ sung** nhau.

Ví dụ workload `orders-prod` được duyệt ngân sách 8.000 USD/tháng, đồng thời tổ chức mua một reservation dùng chung. Khi tạo hoặc sửa budget:

1. Xác định budget scope có bao gồm khoản mua cam kết hoặc usage được phân bổ không, theo loại tài khoản và cách hiển thị.
2. Không mặc định budget Actual và dashboard Amortized bằng nhau trong mọi kỳ.
3. Có thể đặt các ngưỡng **Actual 60%, 80%, 100%** và **Forecasted 100%** nếu tính năng áp dụng được.
4. Gắn người nhận cảnh báo với owner workload và FinOps; nếu scope giao nhau, tránh tạo vòng thông báo trùng không có chủ sở hữu.
5. Ngoài budget, theo dõi **utilization/coverage và ngày hết hạn cam kết** — một budget bình thường vẫn có thể che giấu cam kết không được dùng.
6. Khi workload scale xuống hoặc chuyển kiến trúc, cập nhật forecast và phương án cam kết trong cùng chu kỳ review.

Một Action Group hoặc automation có thể tạo ticket chi phí theo chính sách, nhưng **budget không tự động dừng chi tiêu**. Không xây quy tắc tắt database/backup/production khi chạm ngưỡng nếu chưa đánh giá rủi ro dịch vụ, quyền và cơ chế phê duyệt.

## 15. Quy trình ra quyết định mua hoặc điều chỉnh cam kết

Để tránh mua vì thấy một “discount %” hấp dẫn, tổ chức cần một quy trình có owner và dữ liệu.

### 15.1. Đề xuất đầu tư cam kết

Mẫu quyết định:

~~~yaml
proposal_id: finops-commitment-orders-2026-11
workload: orders-prod
owner: team-orders
financial_owner: finops
scope: "<verified-billing-and-benefit-scope>"
product: "<reservation-or-savings-plan>"
eligible_usage:
  history_window: "<representative-period>"
  baseline_hours: "<observed-hourly-usage>"
  service_sku_region: "<exact-supported-configuration>"
forecast:
  low_case: "<predicted-eligible-usage>"
  base_case: "<predicted-eligible-usage>"
  high_case: "<predicted-eligible-usage>"
comparison:
  payg_reference: "<account-specific-pricing>"
  committed_total: "<full-term-obligation>"
  unused_risk: "<low-usage-scenario>"
  expected_net_savings: "<validated-model-output>"
controls:
  approver: "<authorized-role>"
  review_cycle: "monthly"
  renewal_owner: "<authorized-role>"
  expiry_review: "<date-before-expiration>"
decision: "<approve-defer-reject>"
~~~

Mẫu là tài liệu quản trị nội bộ, không phải Azure API. Cần **ghi rõ kỳ hạn, nghĩa vụ toàn kỳ, tổng tiền tại các kịch bản** thay vì chỉ báo tiết kiệm mỗi tháng.

### 15.2. Checklist phê duyệt

| Câu hỏi | Bằng chứng |
| --- | --- |
| Usage đủ điều kiện và ổn định ở mức nào? | Hourly baseline theo SKU/region/service |
| Có thay đổi kiến trúc trong kỳ hạn không? | Roadmap migration, autoscale, sản phẩm |
| Có cam kết hiện có phủ usage này không? | Utilization/coverage và benefit allocation |
| Lựa chọn nào tiết kiệm thực tế hơn? | So sánh pay-as-you-go, reservation và savings plan trên cùng workload |
| Lỗi dự báo lớn nhất là gì? | Phương án thấp/cơ sở/cao, underutilization |
| Ai chịu trách nhiệm phần unused? | Chargeback/showback policy |
| Ai được quyền mua, đổi phạm vi, gia hạn? | Quyền billing/benefit được kiểm tra |
| Điều kiện đổi/hủy/hoàn tiền có thực sự tồn tại? | Điều khoản và chính sách hiệu lực tại thời điểm mua |
| Có ảnh hưởng đến SLO/bảo mật không? | Kiến trúc và mô hình capacity, backup |
| Nếu không mua thì sao? | Chi phí và lợi thế linh hoạt của pay-as-you-go |

Cần có **người phê duyệt tài chính** và **người xác nhận roadmap kỹ thuật**. Dự báo chỉ do FinOps tính có thể bỏ sót kế hoạch di chuyển hạ tầng; dự báo chỉ do kỹ thuật tính có thể bỏ sót nghĩa vụ hợp đồng và cơ chế ghi nhận chi phí.

### 15.3. Mua và quản lý trong Portal

Quy trình khái quát, tùy sản phẩm/quyền:

1. Đăng nhập Azure Portal, chọn đúng tenant và billing scope/subscription liên quan.
2. Mở khu vực **Reservations** hoặc **Savings plans** tương ứng; kiểm tra khuyến nghị và bộ lọc scope.
3. Đối chiếu eligible usage, thời hạn, tùy chọn thanh toán, đơn giá thực tế và scope benefit với đề xuất đã được duyệt.
4. Xác nhận khả năng áp dụng và quy tắc mua/đổi/hủy đang có hiệu lực.
5. Người có quyền thực hiện giao dịch theo quy trình tổ chức; lưu purchase ID, owner, thời điểm, phạm vi, kỳ hạn và ngân sách liên quan.
6. Sau mua, theo dõi utilization/coverage theo thời gian, hiệu quả tiết kiệm và ngày gia hạn.

**Việc mua cam kết có thể tạo nghĩa vụ tài chính dài hạn.** Không nên mô phỏng bằng giao dịch mua thật chỉ để hoàn thành bài thực hành. Mọi tính toán trong bài có thể thực hiện bằng dữ liệu giả định hoặc dữ liệu đọc được mà không mua sản phẩm.

## 16. Theo dõi cam kết trong suốt vòng đời

### 16.1. Dashboard vận hành hàng tháng

Một dashboard FinOps theo workload nên có:

- Chi phí direct + shared + commitment-adjusted trong tháng, cùng phương pháp tính.
- Actual/Amortized, ghi rõ source, period, cost type và currency.
- Cost per business unit và xu hướng so với business activity.
- Reservation/Savings Plan utilization và coverage theo quyền lợi.
- Unused commitment value, owner và lý do biến động.
- Top cost drivers: compute, database, storage, networking, monitoring.
- Các workload chưa có tag/owner hoặc chi phí shared chưa phân bổ.
- Kỳ hạn, ngày hết hạn, người duyệt gia hạn hoặc quyết định không gia hạn.
- Forecast theo ba kịch bản, các budget alerts và thay đổi architecture đã dự kiến.

Đánh giá dashboard cần có **bộ lọc theo subscription/resource group, workload, môi trường và thời gian**; cùng một công thức cho mọi workload để so sánh đáng tin cậy.

### 16.2. Nhịp review

| Thời điểm | Người chủ trì | Quyết định |
| --- | --- | --- |
| Hàng tuần với workload biến động | SRE/owner | Tải có lệch baseline? Có resource mới hoặc log tăng bất thường? |
| Hàng tháng | FinOps + owner workload | Cost/unit, utilization, coverage, unused, phân bổ shared, forecast |
| Trước kỳ gia hạn cam kết | Finance + platform + workload owner | Gia hạn, giảm mức, thay đổi sản phẩm/scope hoặc trở lại pay-as-you-go |
| Trước migration / major release | Architecture + FinOps | Cấu hình/region mới có làm quyền lợi trở nên không phù hợp? |
| Sau sự cố chi phí | Incident owner | Nguyên nhân, hoạt động phát hiện, hướng xử lý và action items |

Có thể thiết lập nhắc việc khi cam kết sắp hết hạn và khi utilization thấp kéo dài. Tuy nhiên, không nên tự động mua lại cùng số lượng khi không có **forecast được cập nhật**; một workload đã giảm sử dụng sẽ tiếp tục bị overcommit nếu chỉ sao chép quyết định cũ.

### 16.3. Runbook khi utilization giảm

~~~mermaid
flowchart TD
    A["Utilization thấp / unused commitment tăng"] --> B["Kiểm tra benefit, scope và nguồn dữ liệu"]
    B --> C["So thay đổi usage theo giờ, SKU, region và workload"]
    C --> D{"Giảm tải có tạm thời?"}
    D -->|"Có"| E["Giữ theo dõi và kế hoạch tải dự kiến"]
    D -->|"Không"| F["Đánh giá điều chỉnh scope / allocation / kế hoạch kỳ hạn"]
    F --> G["Kiểm tra điều khoản sản phẩm và quyền phê duyệt"]
    G --> H["Thực hiện phương án khả thi hoặc chấp nhận rủi ro còn lại"]
    E --> I["Đối soát tiền cam kết và báo cáo"]
    H --> I
~~~

Không áp dụng một thao tác exchange/cancel mặc định. Nếu chính sách sản phẩm không cho phép thay đổi, cần **ghi nhận nghĩa vụ chưa sử dụng**, tính vào dự báo và tránh mua thêm cam kết chồng chéo.

## 17. Chi phí tối ưu phải giữ được chất lượng phục vụ

Nhiều hành động giảm chi phí xung đột với availability hoặc security. Ví dụ giảm replica production để tăng CPU utilization có thể khiến hệ thống không đủ năng lực nếu mất Availability Zone; tắt geo-replication để giảm bill có thể làm không đạt RPO; giảm log ingestion tùy tiện có thể khiến đội vận hành không phát hiện tấn công.

Tạo một **guardrail** cho từng đề xuất:

| Thao tác tối ưu | Lợi ích có thể có | Điều kiện bắt buộc kiểm tra |
| --- | --- | --- |
| Right-size VM/DB | Giảm compute/throughput cost | CPU, memory, latency, throughput và peak tải |
| Tắt dev/test ngoài giờ | Giảm chi phí theo giờ | Lịch batch, tác vụ cần chạy, disk/storage vẫn còn phí |
| Dùng Reservation/Savings Plan | Giảm đơn giá usage ổn định | Tính đủ điều kiện, thời hạn, rủi ro unused |
| Giảm log debug không cần thiết | Giảm ingest/retention | Giữ audit, security, diagnostics cần thiết |
| Đổi storage tier/lifecycle | Giảm storage dài hạn | Truy cập, retrieval latency, fee và yêu cầu retention |
| Giảm backup/replication | Có thể giảm phí nhưng tăng rủi ro | RTO/RPO, tuân thủ, DR và mục tiêu phục hồi |
| Cắt capacity dự phòng | Giảm cost ngắn hạn | Khả năng chịu lỗi zone, SLA/SLO và khả năng autoscale |

Đánh giá **hiệu quả chi phí** là tối ưu **giá trị trên mỗi đơn vị tiêu thụ** trong giới hạn nghiệp vụ, không phải giảm con số hóa đơn bằng mọi giá.

## 18. Các lỗi phân tích thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Mua cam kết chỉ vì thấy “giảm giá X%” | Underutilization làm chi phí tăng | Tính chi phí toàn kỳ theo hourly usage và kịch bản thấp/cao |
| So Actual có khoản mua trước với Amortized usage rồi cộng cả hai | Double counting | Chọn một cost basis nhất quán và đối soát adjustment |
| Đọc utilization tháng cao rồi bỏ qua từng giờ | Bỏ lỡ giờ cam kết rỗng | Phân tích hourly eligible usage và quyền lợi |
| Nhầm Reservation với capacity reservation | Thiếu capacity dù đã mua discount | Thiết kế capacity/HA riêng |
| Xem Savings Plan là discount cho mọi dịch vụ Azure | Forecast tiết kiệm quá cao | Kiểm tra danh sách eligible meters và usage thực |
| Không xem scope/region/SKU khi chuyển workload | Benefit hết phù hợp | Review lại trước migration |
| Quy hết chi phí subscription cho một app | Sai đơn vị giá trị | Mapping resource/tag, shared allocation và unallocated |
| Không phân bổ unused commitment cho ai | Che giấu chi phí ràng buộc | Có FinOps owner và reconciliation |
| Tính cost/order từ tổng request gồm retry | Unit cost bị bóp méo | Dùng giao dịch thành công duy nhất |
| Thấy workload cost tăng là kết luận kém hiệu quả | Bỏ qua tăng trưởng nghiệp vụ | So unit cost và SLO |
| Tin dữ liệu cost ngày hiện tại là cuối cùng | Quyết định dựa trên số liệu chưa đủ | Ghi thời gian extract, nhận diện data latency |
| Tự động gia hạn theo lịch mà không xem usage | Lặp lại overcommit | Quyết định lại theo forecast và roadmap |
| Giảm backup hoặc số replica để đạt budget | Nguy cơ mất dữ liệu/outage | Guardrail với RTO/RPO/SLO và security |

## 19. Bài thực hành tổng hợp: ra quyết định cho ba workload

**Bối cảnh:** Tổ chức quản lý subscription Azure với ba workload:

- `orders-prod`: API và database hoạt động gần như 24/7, cần HA.
- `catalog-prod`: API có traffic tương đối ổn định nhưng thay đổi instance theo mùa.
- `analytics-batch`: compute chạy theo đợt mỗi ngày và có những ngày không chạy.

Nhóm FinOps dự định đánh giá một reservation và một savings plan, đồng thời lập bảng tổng chi phí theo workload trong kỳ tháng 11/2026. Không có nhu cầu mua thật.

### Nhiệm vụ A — Phân loại usage và định nghĩa scope

Giả sử dữ liệu sau (giá và mức sử dụng hoàn toàn minh họa):

| Workload | Usage đủ điều kiện theo giờ | Đặc điểm | Ưu tiên xem xét |
| --- | --- | --- | --- |
| `orders-prod` | 24/7, gần như không thay đổi SKU | Compute nền ổn định | So reservation phù hợp với pay-as-you-go |
| `catalog-prod` | Tải nền đều, có thêm burst và thay đổi kiểu instance | Nhiều loại compute đủ điều kiện | Xem savings plan và mức commit bảo thủ |
| `analytics-batch` | 6 giờ/ngày, vài ngày không chạy | Biến động cao | Ưu tiên linh hoạt; tránh mua riêng cam kết cho toàn bộ giờ |

Yêu cầu: ghi những dữ liệu thực tế cần thêm trước khi mua (region, SKU, giờ dùng, pricing của tài khoản, roadmap, các cam kết đã tồn tại).

### Nhiệm vụ B — Tính hòa vốn reservation

Sử dụng dữ liệu mục 6: 720 giờ/tháng, pay-as-you-go 0,28 USD/giờ và reservation hiệu dụng 0,19 USD/giờ. Tính:

1. Chi phí nếu workload chạy 468 giờ.
2. Chi phí khi workload chạy 612 giờ.
3. Ngưỡng hòa vốn theo giờ và tỷ lệ utilization.
4. Vì sao không thể ra quyết định cuối cùng nếu workload dự kiến migrate sau sáu tháng trong cam kết một năm?

**Đáp án định hướng:** Với 468 giờ, on-demand 131,04 USD thấp hơn reservation 136,80 USD; với 612 giờ, on-demand 171,36 USD cao hơn 136,80 USD. Hòa vốn khoảng 488,57 giờ hoặc 67,9%. Migration có thể khiến nửa sau kỳ cam kết không còn usage tương thích, vì vậy phải tính nghĩa vụ toàn kỳ và các kịch bản hậu migration.

### Nhiệm vụ C — Mô hình hóa Savings Plan

Xem mức commitment 2,00 USD/giờ và các giờ có eligible usage theo mức giá ưu đãi tương đương 1,50 USD hoặc 2,50 USD. Xác định phần cam kết chưa dùng, cách xử lý usage vượt cam kết và vì sao tổng tháng chưa đủ để chọn cam kết.

**Đáp án định hướng:** Giờ usage 1,50 USD có 0,50 USD cam kết chưa dùng; giờ 2,50 USD dùng hết mức cam kết và phần usage còn lại tính theo quy tắc billing tương ứng. Usage giờ cao không bù được phần cam kết bỏ trống ở giờ thấp.

### Nhiệm vụ D — Phân bổ chi phí và tính unit cost

Dùng bảng mục 12 để:

1. Tính tổng `orders-prod`, `catalog-prod`, `analytics-batch` và tổng tổ chức.
2. Đề xuất một cách phân bổ 2.200 USD platform/shared cost với driver có thể đo.
3. Nếu `orders-prod` có 36.900 giao dịch hợp lệ, tính cost/order dựa trên chi phí đã phân bổ 7.380 USD.
4. Giải thích cách xử lý 400 USD unused commitment nếu chính sách FinOps giữ phần đó ở cấp platform thay vì phân bổ cho ứng dụng.

**Đáp án định hướng:** Tổng theo workload là 7.380 + 4.020 + 1.700 = **13.100 USD**. Với 36.900 giao dịch hợp lệ, `orders-prod` có cost/order là **0,20 USD**. Nếu giữ unused commitment ở cấp platform, phải chuyển đúng khoản khỏi tổng phân bổ cho các workload, vẫn đối soát tổng chi 13.100 USD và ghi rõ owner chi phí. Không tự động cộng lại phần unused đang có trong nguồn.

### Nhiệm vụ E — Viết quyết định và dashboard

Hoàn thiện mẫu đề xuất mục 15.1 với ba kịch bản (thấp, cơ sở, cao), lựa chọn sản phẩm và lý do, số tiền nghĩa vụ toàn kỳ, owner, ngày review và kế hoạch đo utilization/coverage. Phác dashboard có cost per 1.000 giao dịch, top cost drivers, unused commitment, unallocated cost và budget alert.

**Tiêu chí đạt:** Bản đề xuất có bằng chứng usage theo giờ, chi phí so sánh cùng basis, dự báo rủi ro dài hạn, sự đồng thuận tài chính/kỹ thuật, phương pháp cost allocation kiểm tra được và phương án theo dõi sau quyết định.

## 20. Nguyên tắc cần ghi nhớ

1. **Phân tích từng workload** theo chi phí trực tiếp, phần chia sẻ và trách nhiệm cam kết; ranh giới workload có thể vượt resource group hoặc subscription.
2. **Hiểu đúng sản phẩm:** Reservations ưu đãi cho usage/cấu hình phù hợp, Savings Plan for Compute cam kết mức chi compute theo giờ; cam kết hợp đồng và Azure Hybrid Benefit có cơ chế riêng.
3. **Tính trên usage đủ điều kiện theo giờ và toàn kỳ hạn**, xem thêm roadmap, region, SKU và phương án rủi ro thấp/cao.
4. **Theo dõi utilization và coverage đồng thời**, đừng bỏ quên unused commitment hoặc usage chưa hưởng ưu đãi.
5. **Chọn một cost basis nhất quán** khi so sánh Actual, Amortized và các bút toán phân bổ; luôn đối soát khoản chưa phân bổ.
6. **Tính cost trên đơn vị giá trị nghiệp vụ**, giữ SLO, bảo mật, backup và độ tin cậy làm giới hạn tối ưu.
7. **Có owner và vòng review liên tục** cho việc mua, điều chỉnh, gia hạn, budget alert và cost allocation.

Quản lý cam kết chi tiêu có hiệu quả khi tổ chức kết nối được **dữ liệu sử dụng Azure → nghĩa vụ cam kết → chi phí từng workload → giá trị nghiệp vụ → quyết định có thể kiểm chứng**. Khi mô hình này minh bạch, nhóm phát triển và FinOps mới đánh giá được khoản tiết kiệm thực chất, phát hiện cam kết kém hiệu quả và giữ cho kiến trúc Azure đáp ứng cả yêu cầu kỹ thuật lẫn khả năng chi trả.
