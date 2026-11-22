# Xác định SLI, SLO, RTO và RPO cho ứng dụng Azure

## 1. Từ yêu cầu kinh doanh đến mục tiêu độ tin cậy

Một ứng dụng có thể chạy trên các dịch vụ Azure được đánh giá cao về tính sẵn sàng mà vẫn gây trải nghiệm kém: người dùng không đăng nhập được, API trả lỗi, thanh toán bị treo, hoặc dữ liệu đơn hàng không thể khôi phục sau sự cố. Vì vậy, thiết kế **độ tin cậy (reliability)** cần bắt đầu từ những gì người dùng và doanh nghiệp thực sự cần, rồi chuyển thành chỉ số đo lường và kế hoạch khôi phục có thể kiểm chứng.

Trong hệ sinh thái Microsoft Azure, ứng dụng thường kết hợp subscription, resource group, Microsoft Entra ID, mạng ảo, dịch vụ tính toán (App Service, Azure Container Apps, AKS), lưu trữ, cơ sở dữ liệu và hệ thống giám sát. Mỗi thành phần có một kiểu lỗi, thời gian phục hồi và khả năng mất dữ liệu khác nhau. Không có một con số mặc định nào áp dụng đúng cho tất cả ứng dụng.

Hãy xét ứng dụng đặt hàng trực tuyến **Orders**:

- Người dùng gửi yêu cầu đến API chạy trên Azure App Service.
- API xác thực danh tính, tạo đơn hàng trong Azure SQL Database và gửi sự kiện sang Azure Service Bus.
- Azure Monitor và Application Insights thu thập telemetry; nhóm trực vận hành nhận cảnh báo.
- Doanh nghiệp yêu cầu thao tác tạo đơn hàng nhanh, ít lỗi, và muốn tiếp tục xử lý đơn sau một sự cố vùng Azure (region).

Bốn khái niệm giải quyết những câu hỏi khác nhau:

| Khái niệm | Câu hỏi cốt lõi | Bản chất |
| --- | --- | --- |
| **SLI – Service Level Indicator** | Hiện tại người dùng đang nhận được chất lượng dịch vụ như thế nào? | **Phép đo** từ dữ liệu thực tế |
| **SLO – Service Level Objective** | Mức chất lượng nào được coi là đạt trong một khoảng thời gian? | **Mục tiêu** cho một hoặc nhiều SLI |
| **RTO – Recovery Time Objective** | Khi xảy ra gián đoạn, dịch vụ cần khôi phục trong bao lâu? | **Giới hạn thời gian khôi phục** mà doanh nghiệp chấp nhận |
| **RPO – Recovery Point Objective** | Sau thảm họa, doanh nghiệp có thể chấp nhận mất tối đa bao nhiêu dữ liệu gần nhất? | **Giới hạn mất dữ liệu theo thời gian** |

**SLO không phải RTO; RPO không phải thời gian hệ thống ngừng hoạt động.** SLI/SLO giúp điều hành chất lượng dịch vụ hằng ngày; RTO/RPO giúp thiết kế và kiểm chứng năng lực phục hồi khi có sự cố. Các chỉ số này liên quan đến nhau nhưng phải được xác định riêng.

### Mục tiêu sau bài học

Bạn có thể xác định SLI lấy người dùng làm trung tâm, đặt SLO với cửa sổ đo và error budget rõ ràng, xây RTO/RPO dựa trên tác động kinh doanh, chọn phương án Azure đáp ứng mục tiêu, viết truy vấn giám sát cơ bản và tổ chức diễn tập phục hồi có tiêu chí đạt/trượt.

## 2. Chọn SLI phản ánh trải nghiệm người dùng

SLI là một giá trị đo được từ các sự kiện, request, giao dịch hoặc probe. Đừng nhầm SLI với tên một công cụ. Application Insights, Azure Monitor hay Azure Load Testing chỉ giúp thu thập hoặc kiểm tra dữ liệu; nhóm vận hành vẫn phải **định nghĩa thế nào là một trải nghiệm tốt**.

### 2.1 Những SLI thường dùng

| Nhóm | Ví dụ SLI | Ý nghĩa đối với người dùng |
| --- | --- | --- |
| Availability / thành công | Tỷ lệ request hợp lệ được phục vụ thành công | Có hoàn tất được thao tác không? |
| Latency / độ trễ | Tỷ lệ request thành công hoàn tất trong 300 ms hoặc p95 latency | Thao tác có đủ nhanh không? |
| Correctness / tính đúng | Tỷ lệ đơn hàng có tổng tiền và trạng thái chính xác | Kết quả có đúng không? |
| Freshness / độ mới | Tỷ lệ đơn hàng xuất hiện trong báo cáo sau tối đa 2 phút | Dữ liệu có cập nhật kịp thời không? |
| Durability / độ bền dữ liệu | Tỷ lệ dữ liệu đã xác nhận có thể được truy xuất sau sự cố | Dữ liệu đã ghi có còn tồn tại không? |
| Completion / tác vụ nền | Tỷ lệ sự kiện được xử lý hoàn tất trong 5 phút | Hàng đợi và job bất đồng bộ có chạy kịp không? |

Không nên lấy CPU, dung lượng đĩa hoặc số replica làm SLI chính cho mục tiêu khách hàng. Chúng là **tín hiệu chẩn đoán** hữu ích, nhưng CPU dưới 50% không chứng minh rằng người dùng đang tạo đơn thành công.

### 2.2 Xác định tập request hợp lệ và phép đo

Với API tạo đơn, có thể định nghĩa:

- **Eligible requests**: tất cả yêu cầu POST /orders hợp lệ đã đi qua ranh giới đo đã chọn; loại trừ health probe nội bộ và traffic kiểm thử đã nhận diện theo quy tắc công bố.
- **Good requests**: các eligible request hoàn tất với kết quả nghiệp vụ đúng và không gặp lỗi thuộc trách nhiệm dịch vụ.
- **Bad requests**: các eligible request còn lại; bao gồm timeout hoặc lỗi 5xx và các lỗi nghiệp vụ theo quy định của SLI.

SLI tỷ lệ thành công trong cửa sổ W:

\[
\mathrm{SLI_{success}}(W)=\frac{\text{số request tốt trong }W}{\text{số request hợp lệ trong }W}\times100\%.
\]

Ví dụ có 1.000.000 yêu cầu hợp lệ trong 28 ngày, trong đó 998.900 yêu cầu tốt:

\[
\mathrm{SLI_{success}}=\frac{998\,900}{1\,000\,000}\times100\%=99{,}89\%.
\]

Khi thiết lập mẫu số, phải thống nhất ít nhất các điều kiện sau:

1. **Ranh giới đo**: API gateway, ingress, Front Door hay instrumentation trong ứng dụng? Request bị lỗi trước khi tới ứng dụng có thể không xuất hiện trong application logs.
2. **Nhóm người dùng/đường đi**: toàn bộ khách hàng, riêng thao tác đặt hàng, khu vực địa lý hoặc tenant quan trọng?
3. **Trạng thái thành công**: 4xx do client gửi dữ liệu không hợp lệ có thể là hành vi đúng; không nên mặc định tính mọi 4xx như lỗi dịch vụ. Ngược lại, HTTP 200 nhưng nghiệp vụ tạo đơn sai cũng không phải good request.
4. **Timeout và retry**: request timeout phía khách hàng, bị load balancer từ chối hay bị lặp do retry được đếm thế nào? Đếm request hay giao dịch nghiệp vụ cuối cùng?
5. **Thiếu dữ liệu**: giai đoạn mất telemetry không được tự động diễn giải thành 100% thành công.

Nguyên tắc quan trọng là **không làm đẹp số liệu bằng cách tùy tiện loại lỗi hoặc bảo trì có ảnh hưởng thực tế đến người dùng**. Mọi ngoại lệ phải được định nghĩa trước, ghi vào tài liệu và áp dụng nhất quán.

### 2.3 SLI độ trễ: percentile và ngưỡng tốt

Có hai cách đo phổ biến:

- **p95 latency**: 95% request được quan sát có độ trễ không vượt quá giá trị p95. Ví dụ p95 = 280 ms cho biết 95% mẫu có thời gian đáp ứng tối đa khoảng 280 ms.
- **Tỷ lệ request nhanh**: số eligible request hoàn tất trong ngưỡng 300 ms chia cho tất cả eligible request. Cách này dễ ghép với error budget vì mỗi request được phân loại tốt/xấu.

Hai cách không hoàn toàn tương đương khi định nghĩa thêm tiêu chí thành công, timeout, sampling và cửa sổ đo. Ví dụ SLI tổng hợp:

\[
\mathrm{SLI_{fast\_success}}=
\frac{\text{request thành công và latency}\leq300\,\mathrm{ms}}
{\text{request hợp lệ}}\times100\%.
\]

Đặt ngưỡng đo dựa vào thao tác thực tế. API đọc sản phẩm có thể có mục tiêu khác với quy trình thanh toán nhiều bước hoặc job đồng bộ dữ liệu; không áp một ngưỡng 300 ms cho mọi tác vụ.

## 3. Đặt SLO có thể vận hành

**SLO** quy định một hoặc nhiều ngưỡng mục tiêu của SLI và **cửa sổ đánh giá**. Ví dụ minh họa cho Orders:

| Hành trình | SLI | SLO minh họa | Cửa sổ |
| --- | --- | --- | --- |
| Tạo đơn hàng | Tỷ lệ request hợp lệ hoàn tất đúng | Tối thiểu **99,9%** | Rolling 28 ngày |
| Đọc danh sách đơn | Tỷ lệ request thành công trong ≤ 300 ms | Tối thiểu **95%** | Rolling 28 ngày |
| Đồng bộ sự kiện đơn | Tỷ lệ event được xử lý trong ≤ 5 phút | Tối thiểu **99,5%** | Rolling 7 ngày |
| Đăng nhập | Tỷ lệ lượt đăng nhập người dùng hoàn tất thành công, đo trên toàn hành trình | Mục tiêu do nghiệp vụ và ranh giới trách nhiệm thống nhất | Rolling 28 ngày |

Các tỷ lệ trong bảng chỉ là **giả định học tập**, không phải SLA chính thức của Azure hay cam kết của dịch vụ Orders thực tế.

Một SLO tốt nên ghi thành câu đầy đủ:

> Trong mọi cửa sổ trượt 28 ngày, ít nhất 99,9% yêu cầu tạo đơn hợp lệ của người dùng production phải hoàn tất với kết quả đúng. Phép đo dựa trên telemetry tại ranh giới API đã chọn, có ghi nhận timeout và lỗi tại ingress; lưu lượng tổng hợp được tách riêng.

Ngoài tỷ lệ, tài liệu SLO nên có chủ sở hữu, phương pháp tính, nguồn dữ liệu, phạm vi môi trường/region, ngưỡng volume tối thiểu, quy tắc thiếu dữ liệu, dashboard, cảnh báo và hành động khi vi phạm.

### 3.1 Phân biệt SLO và SLA

- **SLO** là mục tiêu vận hành do nhóm cung cấp dịch vụ đặt ra; có thể nghiêm ngặt hơn, thấp hơn hoặc đo khác phạm vi SLA.
- **SLA (Service Level Agreement)** là cam kết trong thỏa thuận dịch vụ, có thể kèm điều kiện áp dụng hoặc cơ chế service credit. SLA của từng sản phẩm Azure phụ thuộc SKU, cấu hình, region, điều khoản và thời điểm.
- **SLI** là con số thực đo trên ranh giới ứng dụng của bạn. Không thể lấy SLA của một dịch vụ thành phần làm bằng chứng rằng toàn bộ ứng dụng đạt SLO.

Nếu hệ thống gồm nhiều thành phần nối tiếp, tất cả đều bắt buộc hoạt động, độ sẵn sàng tổng thể có thể thấp hơn từng thành phần. Trong một mô hình độc lập đơn giản:

\[
A_{\mathrm{end\ to\ end}}\approx A_1\times A_2\times\cdots\times A_n.
\]

Ví dụ giả định hai thành phần độc lập, mỗi thành phần có availability 99,9%, thì availability lý thuyết của đường đi phụ thuộc cả hai là khoảng 99,8001%. **Đây chỉ là mô hình minh họa**: sự cố có thể tương quan, có cache, retry, fallback và nhiều trạng thái suy giảm khác nhau.

### 3.2 Error budget: lượng lỗi được phép trong cửa sổ

Với SLO tỷ lệ thành công 99,9%:

\[
\mathrm{ErrorBudgetFraction}=1-0{,}999=0{,}001=0{,}1\%.
\]

Nếu có 2.000.000 eligible request trong cửa sổ, error budget tương ứng:

\[
2\,000\,000\times0{,}001=2\,000\ \text{request xấu}.
\]

Nếu thực tế có 2.600 request xấu, nhóm đã vượt ngân sách 600 request và SLI chỉ còn 99,87%, thấp hơn SLO 99,9%.

**Chú ý phân biệt ngân sách request và thời gian ngừng hoạt động**. Với SLO dựa trên tỷ lệ request, không thể tự động đổi 2.000 request lỗi thành số phút downtime vì lưu lượng thay đổi theo giờ. Nếu thiết lập riêng một SLO availability theo thời gian và giả định lỗi hoàn toàn:

\[
28\times24\times60\times(1-0{,}999)=40{,}32\ \text{phút}.
\]

Con số 40,32 phút chỉ là **minh họa cho ngân sách dựa trên thời gian** của cửa sổ 28 ngày, không thay thế cách tính request-based ở trên.

### 3.3 Burn rate và chính sách phản ứng

**Burn rate** cho biết ngân sách lỗi bị tiêu thụ nhanh hơn tốc độ cho phép bao nhiêu lần:

\[
\mathrm{BurnRate}=
\frac{\mathrm{ObservedErrorFraction}}
{1-\mathrm{SLOTarget}}.
\]

Với SLO 99,9%, tỷ lệ lỗi cho phép là 0,1%. Nếu trong một khoảng quan sát gần đây tỷ lệ lỗi là 1%, burn rate bằng **10×**. Như vậy, nếu tình trạng kéo dài, ngân sách sẽ hết nhanh hơn mức dự kiến.

Có thể thiết lập cảnh báo đa cửa sổ, chẳng hạn một cửa sổ ngắn để nhận biết sự cố nghiêm trọng và một cửa sổ dài để tránh cảnh báo thoáng qua. Không dùng cùng một ngưỡng burn rate cho mọi SLO; hãy điều chỉnh theo tải, tác động người dùng và quy trình trực ca.

Khi error budget cạn, nhóm có thể tạm giảm thay đổi rủi ro cao, ưu tiên sửa reliability, tăng độ bao phủ của canary, rollback hoặc bổ sung kiểm thử. Chính sách này cần do chủ dịch vụ và các bên liên quan thống nhất; không có một cơ chế Azure tự động quyết định thay nhóm phát triển.

## 4. RTO và RPO: hai trục của kế hoạch khôi phục

### 4.1 RTO – mất bao lâu để cung cấp lại dịch vụ?

**Recovery Time Objective (RTO)** là giới hạn thời gian chấp nhận được để khôi phục chức năng dịch vụ đã định nghĩa sau một sự kiện gián đoạn thuộc phạm vi kế hoạch. Để đo nhất quán, cần chỉ rõ:

- **Điểm bắt đầu**: thời điểm dịch vụ bắt đầu không đáp ứng tiêu chí tối thiểu do sự cố, không chỉ thời điểm hệ thống phát cảnh báo hay nhân sự bắt đầu xử lý.
- **Điểm kết thúc**: thời điểm hành trình quan trọng đã hoạt động lại ở mức tối thiểu được thống nhất và đã qua kiểm chứng.
- **Phạm vi**: hệ thống nào, mức suy giảm nào, traffic bao nhiêu, khu vực người dùng nào, và loại thảm họa nào.

Ví dụ sự cố bắt đầu lúc 10:00, hệ thống nhận biết lúc 10:06, chuyển vùng và xác minh xong lúc 10:42. **Thời gian khôi phục đo được là 42 phút**, không phải 36 phút tính từ lúc cảnh báo. Nếu RTO mục tiêu là 45 phút, lần diễn tập này đạt mục tiêu về thời gian, miễn là tiêu chí chức năng phục hồi được đáp ứng.

RTO thường gồm nhiều công đoạn:

\[
T_{\mathrm{recover}}=
T_{\mathrm{detect}}+
T_{\mathrm{declare}}+
T_{\mathrm{failover}}+
T_{\mathrm{restore/verify}}.
\]

Công thức là mô hình hoạch định; trong thực tế có bước chạy song song, phụ thuộc lẫn nhau và thời gian chờ của DNS, identity, database, network hoặc ứng dụng.

### 4.2 RPO – có thể mất bao nhiêu dữ liệu?

**Recovery Point Objective (RPO)** là giới hạn mất dữ liệu chấp nhận được, biểu diễn theo khoảng thời gian giữa thời điểm sự cố và **điểm dữ liệu có thể khôi phục nhất quán**.

Ví dụ sự cố xảy ra lúc 10:00; điểm khôi phục nhất quán gần nhất là 09:55. Dữ liệu đã được xác nhận ghi trong khoảng 09:55–10:00 có nguy cơ mất, nên **mức mất dữ liệu theo thời gian là 5 phút**. Nếu RPO mục tiêu là 10 phút thì lần này đạt về mặt điểm khôi phục; vẫn phải kiểm tra dữ liệu được khôi phục có nhất quán và nghiệp vụ xử lý lại được hay không.

RPO không phải lịch lưu backup đơn thuần. Một bản sao lưu mỗi 15 phút chưa chắc chứng minh RPO 15 phút nếu backup có độ trễ, thất bại, không nhất quán hoặc không khôi phục được. **Replication cũng không luôn đồng nghĩa RPO = 0**: sao chép bất đồng bộ có độ trễ và có thể chưa nhận tất cả commit trước khi vùng nguồn ngừng hoạt động.

### 4.3 Quan hệ giữa RTO và RPO

~~~mermaid
flowchart LR
    A["09:55\nĐiểm khôi phục nhất quán"] --> B["10:00\nSự cố bắt đầu"]
    B --> C["10:06\nPhát hiện/công bố"]
    C --> D["10:42\nDịch vụ phục hồi"]
~~~

- **Mất dữ liệu theo thời gian thực tế:** 10:00 − 09:55 = **5 phút**; so với RPO.
- **Thời gian gián đoạn thực tế:** 10:42 − 10:00 = **42 phút**; so với RTO.
- Hai giá trị **độc lập tương đối**: có thể phục hồi rất nhanh nhưng mất nhiều dữ liệu, hoặc mất gần như không có dữ liệu nhưng mất nhiều giờ để khởi động lại dịch vụ.

RTO và RPO phải kèm **loại sự cố**. Một mục tiêu cho lỗi một instance hoặc một availability zone không tự động áp dụng được cho mất toàn bộ region, bị xóa dữ liệu có chủ ý, hay mã hóa dữ liệu do ransomware.

## 5. Xác định mục tiêu theo tác động kinh doanh

Trước khi chọn công nghệ, cần thực hiện **Business Impact Analysis (BIA)** ở mức phù hợp. Hỏi chủ sản phẩm, vận hành và bảo mật:

1. Hành trình nào bắt buộc phải hoạt động để doanh nghiệp tiếp tục phục vụ khách hàng?
2. Nếu ngừng 5 phút, 30 phút, 4 giờ hoặc một ngày, tổn thất giao dịch, uy tín và nghĩa vụ tuân thủ là gì?
3. Các bản ghi nào tuyệt đối không được mất, dữ liệu nào có thể dựng lại, và ai chịu trách nhiệm đối soát?
4. Những người dùng hoặc vùng địa lý nào quan trọng; hệ thống có giờ cao điểm, thời hạn giao dịch hay thời điểm đóng sổ không?
5. Giới hạn ngân sách để đổi lấy khả năng phục hồi nhanh và giữ dữ liệu gần thời điểm sự cố là bao nhiêu?

Bảng mục tiêu **minh họa** cho ứng dụng Orders:

| Thành phần/hành trình | SLO tham khảo | RTO tình huống mất region | RPO tình huống mất region | Lý do |
| --- | --- | --- | --- | --- |
| API tạo đơn | 99,9% giao dịch tốt / 28 ngày | ≤ 45 phút | ≤ 5 phút đối với đơn đã ghi | Mất giao dịch làm gián đoạn bán hàng |
| Tra cứu catalog | 99,5% request tốt / 28 ngày | ≤ 4 giờ | ≤ 24 giờ cho dữ liệu có thể đồng bộ lại | Có thể sử dụng bản cache và làm mới |
| Dashboard báo cáo | 99% job hoàn tất đúng hạn / 7 ngày | ≤ 8 giờ | ≤ 1 giờ | Có thể nạp lại dữ liệu từ nguồn giao dịch |
| Nhật ký kiểm toán quan trọng | Đo tỷ lệ bản ghi được lưu trữ đúng và đầy đủ | Theo chính sách điều tra/tuân thủ | Có thể yêu cầu mất dữ liệu rất thấp | Khó tái tạo sự kiện đã xảy ra |

Đây là các mục tiêu thiết kế giả định, **chưa phải bằng chứng Azure bảo đảm đạt RTO/RPO**. Ví dụ RPO ≤ 5 phút cho đơn hàng có thể không phù hợp nếu giao dịch tài chính yêu cầu không mất commit nào. Khi hệ thống cần RPO gần 0, kiến trúc, giao thức xác nhận và cơ chế đối soát phải được thiết kế/đánh giá riêng.

### 5.1 Những phụ thuộc thường bị quên

Đối với API đặt hàng, cần liệt kê đủ đường đi:

~~~mermaid
flowchart TD
    U["Người dùng"] --> F["Azure Front Door / DNS"]
    F --> W["App Service / API"]
    W --> I["Microsoft Entra ID hoặc nhà cung cấp danh tính"]
    W --> D["Azure SQL Database"]
    W --> Q["Azure Service Bus"]
    Q --> J["Worker xử lý nền"]
    W --> O["Azure Monitor / Application Insights"]
~~~

Trong sơ đồ, các thành phần có vai trò khác nhau; không phải mọi thao tác đều đi qua tất cả chúng. Hãy vẽ **critical path riêng cho từng hành trình**. Một DR plan chỉ khởi động được App Service ở vùng dự phòng nhưng thiếu route DNS, secrets, role assignment, kết nối database hoặc hàng đợi thì chưa đạt RTO đầu cuối.

## 6. Thiết kế Azure để đáp ứng SLI/SLO

SLI tốt phải được duy trì nhờ kiến trúc chứ không chỉ nhờ dashboard:

- **Chống lỗi một instance:** sử dụng khả năng scale-out, health checks, retry có giới hạn, timeout và circuit breaker hợp lý; theo dõi tác động tới người dùng thực.
- **Chống lỗi zone:** xem xét các SKU/dịch vụ Azure hỗ trợ availability zones và cấu hình zone redundancy theo từng region. Hỗ trợ và cơ chế hoạt động khác nhau giữa sản phẩm.
- **Chống lỗi region:** chuẩn bị điểm truy cập có khả năng đổi hướng (ví dụ Front Door và routing phù hợp), lớp tính toán tại vùng khác, dữ liệu có chiến lược replication/restore, cấu hình mạng, identity và secrets tương ứng.
- **Giữ đúng dữ liệu:** dùng transaction, idempotency key, outbox/inbox hoặc đối soát khi có retry, failover và sự kiện đến trùng lặp; không coi tỷ lệ HTTP 2xx là đủ.
- **Giảm vùng ảnh hưởng:** tách workload, phân quyền theo resource group/subscription phù hợp, giới hạn quyền automation và thay đổi triển khai bằng canary/rolling update khi dịch vụ hỗ trợ.

**Zone redundancy khác DR liên vùng**: nhiều zone trong cùng region giúp chịu một số sự cố cục bộ nhưng không tự bảo vệ khỏi sự cố ảnh hưởng toàn region. Ngược lại, bố trí multi-region không tự bảo đảm dữ liệu nhất quán hoặc thao tác failover tức thời.

### 6.1 Kết nối mục tiêu với cấu hình quan sát được

Với SLO API, cần thu thập dữ liệu ở ranh giới mà người dùng trải nghiệm. Application Insights SDK/auto-instrumentation cung cấp request, dependency, exception và distributed tracing; Azure Monitor thu thập metrics/logs và cấu hình alerts; availability tests mô phỏng trải nghiệm từ vị trí ngoài ứng dụng.

Kết hợp ít nhất hai góc nhìn:

- **Inside-out:** thời gian và kết quả request của backend, dependency SQL, lỗi trong ứng dụng, saturation của compute.
- **Outside-in:** probe HTTP/HTTPS, login hoặc journey thử nghiệm xuyên qua edge, DNS, routing và mạng. Probe đơn giản không chứng minh quy trình đặt hàng thật hoạt động đúng.

Nếu thiếu telemetry ở ingress, request chết trước khi vào ứng dụng có thể bị bỏ sót. Các loại probe và user telemetry cũng có sai lệch riêng; hãy mô tả chúng trong định nghĩa SLI.

## 7. Thiết kế Azure để đáp ứng RTO/RPO

Lựa chọn kỹ thuật DR cần xuất phát từ từng nguồn dữ liệu và từng kịch bản mất dịch vụ:

| Nhu cầu | Dịch vụ/khả năng Azure thường xem xét | Điểm phải xác minh bằng thử nghiệm |
| --- | --- | --- |
| Tính toán ở vùng dự phòng | Triển khai App Service, Azure Container Apps, AKS hoặc VM ở region thứ hai; Azure Site Recovery cho tình huống VM phù hợp | Thời gian provision/start, image/config, autoscale, health check, DNS/route, phụ thuộc |
| Cơ sở dữ liệu giao dịch | Khả năng failover group hoặc active geo-replication của Azure SQL tùy loại dịch vụ và cấu hình; backup/point-in-time restore | Độ trễ sao chép, tính nhất quán, chuyển endpoint, dữ liệu mất, quyền, hành vi ứng dụng sau failover |
| Dữ liệu phân tán | Azure Cosmos DB multi-region và lựa chọn consistency/failover phù hợp | RPO thực tế, cơ chế conflict, session/consistency, phương án backup khi dữ liệu bị xóa sai |
| Blob/file | Các tùy chọn redundancy và geo-redundancy của Azure Storage (ví dụ GRS/GZRS/RA-GRS tùy dịch vụ, region) | Điều kiện failover, replication lag, phạm vi dịch vụ hỗ trợ, dữ liệu vừa ghi |
| Sao lưu và phục hồi | Azure Backup và cơ chế backup/PITR của từng dịch vụ | Tần suất, retention, kiểm tra khôi phục thực, tính bất biến/khả năng chống xóa khi cần |
| Routing và health | Azure Front Door, Traffic Manager, DNS, load balancing và health probe phù hợp | Cách xác định endpoint khỏe, propagation, cache, TLS/certificate, route an toàn |

Khả năng hỗ trợ, chi phí, SLA và hành vi failover thay đổi theo SKU, region, cấu hình và thời điểm. **Không suy ra RTO/RPO cam kết từ tên tính năng “geo-redundant” hoặc “auto-failover”**. Phải kiểm tra giới hạn dịch vụ trong kiến trúc thực tế và diễn tập.

### 7.1 Replication và backup giải quyết các rủi ro khác nhau

Replication giúp có dữ liệu tại nơi dự phòng nhanh hơn, nhưng có thể sao chép cả thay đổi sai, thao tác xóa hoặc dữ liệu bị mã hóa. Backup độc lập, có retention và kiểm tra khả năng khôi phục, giúp xử lý các kịch bản logic corruption và tấn công; tuy nhiên phục hồi từ backup có thể mất nhiều thời gian hơn failover qua replica.

Một chiến lược cần bao gồm cả **đứt vùng** lẫn **hỏng dữ liệu logic**. Tùy mục tiêu, kết hợp replica cho RTO thấp và backup/point-in-time restore cho khả năng quay về điểm dữ liệu sạch.

### 7.2 Dữ liệu nhất quán xuyên nhiều thành phần

Ví dụ API ghi đơn hàng vào Azure SQL rồi phát sự kiện vào Service Bus. Khi failover region, có thể xảy ra:

- Đơn hàng đã commit ở SQL nhưng sự kiện chưa gửi.
- Sự kiện đã gửi nhưng chưa được consumer xác nhận.
- Sự kiện gửi lại sau khi consumer từng xử lý thành công.

Vì vậy, RPO không chỉ là “database còn dữ liệu đến phút nào”. Cần định nghĩa điểm nhất quán giữa đơn, thanh toán, trạng thái hàng đợi và các hệ thống tích hợp. Các mẫu thiết kế như **transactional outbox**, xử lý idempotent, retry có backoff và job reconciliation giúp ứng dụng phục hồi chính xác sau khi các thành phần có RPO khác nhau.

### 7.3 Kịch bản lỗi quyết định thiết kế

| Kịch bản | Cách ứng phó cần chứng minh |
| --- | --- |
| Một instance App Service lỗi | Health probe, scale-out/restart/route sang instance khỏe |
| Availability zone gặp sự cố | Cấu hình chịu lỗi zone và dữ liệu phụ trợ không là điểm lỗi duy nhất |
| Cả region ngừng hoạt động | Khả năng cung cấp dịch vụ ở region khác, failover dữ liệu và đường truy cập |
| Xóa nhầm/corruption dữ liệu | Backup, point-in-time restore, phân quyền, đối soát và quy trình lấy lại dữ liệu sạch |
| Token hoặc identity lỗi | Khả năng truy cập dịch vụ/quyền phục hồi theo kịch bản, không lưu bí mật trong runbook |
| Sự cố hạ tầng do cập nhật cấu hình | Rollback/cấu hình đã được kiểm chứng; kiểm soát blast radius |

Mỗi kịch bản có thể có RTO/RPO khác nhau. Hãy ghi phiên bản kế hoạch, người chịu trách nhiệm và điều kiện chuyển từ phục hồi thường sang DR chính thức.

## 8. Thu thập SLI bằng Azure Monitor và Application Insights

### 8.1 Chọn nguồn telemetry

Đối với Application Insights dạng workspace-based, logs của request thường nằm ở bảng **AppRequests** trong Log Analytics workspace, với các trường như TimeGenerated, AppRoleName, Success, DurationMs và ItemCount. Tên bảng và trường có thể khác nếu bạn truy vấn qua bề mặt Application Insights khác hoặc cách instrument tùy chỉnh; cần kiểm tra schema thật trên ứng dụng.

Ví dụ minh họa tỷ lệ request thành công của ứng dụng Orders trong **28 ngày trượt**:

~~~kusto
let lookback = 28d;
AppRequests
| where TimeGenerated >= ago(lookback)
| where AppRoleName == "orders-api"
| where Name !in ("GET /healthz", "GET /readyz")
| summarize
    Eligible = sum(ItemCount),
    Good = sumif(ItemCount, Success == true)
| extend
    SuccessSLI_pct = iff(
        Eligible == 0,
        real(null),
        100.0 * todouble(Good) / todouble(Eligible)
    )
| project Eligible, Good, SuccessSLI_pct
~~~

Ý nghĩa:

- **ItemCount** giúp ước lượng số request gốc khi Application Insights sampling được bật; cộng mỗi dòng log như một request có thể làm sai tỷ lệ.
- **Success** phản ánh giá trị mà instrumentation gán; nếu định nghĩa nghiệp vụ cần loại các lỗi client được mong đợi hoặc đánh giá kết quả đơn hàng thực tế, phải chuẩn hóa trường/logic SLI thay vì chỉ dựa vào Success.
- **Name** và **AppRoleName** là giá trị ví dụ; thay bằng tên ứng dụng, operation và bộ lọc phù hợp trên môi trường thực.
- Nếu **Eligible = 0**, không được đánh dấu SLO đạt 100%; đó là trạng thái **thiếu dữ liệu/không có lưu lượng**, cần xử lý theo chính sách.
- Sampling có thể ảnh hưởng phép đo các phân đoạn lưu lượng thấp. Với SLI quan trọng, xem xét telemetry ở edge, metrics không sampling hoặc nguồn transaction đáng tin cậy, và đối chiếu cách tính.

Ví dụ tỷ lệ request thành công và hoàn thành trong **≤ 300 ms**:

~~~kusto
AppRequests
| where TimeGenerated >= ago(28d)
| where AppRoleName == "orders-api"
| where Name !in ("GET /healthz", "GET /readyz")
| summarize
    Eligible = sum(ItemCount),
    FastGood = sumif(ItemCount, Success == true and DurationMs <= 300)
| extend
    FastSuccessSLI_pct = iff(
        Eligible == 0,
        real(null),
        100.0 * todouble(FastGood) / todouble(Eligible)
    )
| project Eligible, FastGood, FastSuccessSLI_pct
~~~

Nếu muốn đánh giá độ trễ theo p95, có thể sử dụng percentile trên DurationMs sau khi lọc cùng một nhóm request. Tuy nhiên percentile trên các dòng log đã sampling có thể không hoàn toàn phản ánh trọng số ItemCount. Với SLI đòi hỏi độ chính xác cao, phải kiểm chứng thiết kế thu thập và cách tính percentile.

### 8.2 Dashboard và cảnh báo

Đối với Orders, dashboard tối thiểu nên hiển thị:

1. SLI theo ngày/giờ và SLI trong cửa sổ rolling 28 ngày, cùng SLO target.
2. Eligible request, bad request, lượng error budget còn lại và burn rate.
3. Latency p50/p95/p99 hoặc tỷ lệ nhanh, lưu lượng, lỗi theo route/region/tenant.
4. Tình trạng dependency SQL, Service Bus, ngoại lệ, retry, hàng đợi.
5. Kết quả synthetic availability test từ nhiều địa điểm, Azure Service Health và tình trạng tài nguyên liên quan.

Trong Azure Monitor có thể dùng Log Analytics/KQL, metrics, workbook/dashboard, metric hoặc log search alert và Action Group để gửi thông báo tới nhóm chịu trách nhiệm. Với cảnh báo quan trọng, ghi rõ **cửa sổ và tỷ lệ mẫu tối thiểu**, quy tắc no-data, nơi nhận, runbook và cách chống bão cảnh báo.

**SLO không đồng nghĩa alert threshold:** một lần trả lỗi có thể chưa vi phạm SLO 28 ngày, nhưng một luồng lỗi nhanh và liên tục phải được phát hiện ngay. Các cảnh báo burn rate đa cửa sổ giúp cân bằng độ nhạy và nhiễu.

## 9. Đo RTO/RPO bằng diễn tập thay vì phỏng đoán

RTO/RPO là mục tiêu. Để biết kiến trúc thực tế đạt được hay không, phải tổ chức **DR exercise** và lưu kết quả từng lần diễn tập.

### 9.1 Kịch bản diễn tập mất region

Giả sử:

- RTO mục tiêu: **≤ 45 phút** cho hành trình tạo đơn trở lại ở mức tối thiểu.
- RPO mục tiêu: **≤ 5 phút** cho đơn hàng đã được xác nhận.
- Sự cố mô phỏng bắt đầu lúc **10:00**, người trực được cảnh báo lúc **10:06**.
- API ở region phụ và database đích được đưa vào hoạt động, health check và một đơn hàng thử thành công lúc **10:42**.
- Sau đối soát, điểm dữ liệu commit nhất quán cuối cùng trước sự cố ở nguồn là **09:57**.

Tính:

\[
\mathrm{ActualRTO}=10{:}42-10{:}00=42\ \mathrm{phút};
\quad
\mathrm{ActualRPO}=10{:}00-09{:}57=3\ \mathrm{phút}.
\]

Về mặt hai mục tiêu thời gian trong tình huống này, **đều đạt**. Tuy nhiên, kết luận cuối chỉ được đưa ra sau khi kiểm tra dữ liệu đơn, khả năng ghi mới, xử lý queue, trạng thái thanh toán, tuyến mạng và trải nghiệm người dùng. Không coi lệnh failover trả về thành công là thời điểm dịch vụ đã khôi phục.

### 9.2 Các mốc cần ghi lại

| Mốc | Nội dung bằng chứng | Vì sao cần |
| --- | --- | --- |
| T0 – gián đoạn | Log/probe đầu tiên cho thấy dịch vụ rớt dưới mức phục vụ tối thiểu | Tính RTO từ lúc ảnh hưởng khách hàng |
| T1 – phát hiện | Azure Monitor alert, người trực nhận thông báo | Tách thời gian phát hiện khỏi thao tác xử lý |
| T2 – tuyên bố DR | Quyết định có thẩm quyền, người chỉ huy sự cố | Tránh failover trái quy trình |
| T3 – khôi phục kỹ thuật | Region phụ, database, routing, secrets, permissions hoạt động | Kiểm tra phụ thuộc kỹ thuật |
| T4 – xác minh nghiệp vụ | Giao dịch thử và hành trình khách hàng đạt tiêu chí | Điểm kết thúc RTO đã thống nhất |
| Recovery point | Timestamp/transaction ID cuối cùng nhất quán, có thể khôi phục và đối chiếu | Tính RPO và xác định dữ liệu cần xử lý |

Thực hiện diễn tập ở môi trường được phê duyệt, tránh gây sự cố ngoài ý muốn. Với dịch vụ có khả năng failover gây mất dữ liệu, chỉ thực hiện thao tác chuyển vùng thật khi đã chuẩn bị scope, owner, rollback/failback và đánh giá rủi ro.

### 9.3 Runbook ngắn cho Orders

Một runbook DR có thể theo trình tự:

1. **Phát hiện và khoanh vùng**: xác nhận sự cố thật, phân biệt lỗi ứng dụng với lỗi Azure region; xem Azure Service Health, telemetry và dấu hiệu của phụ thuộc.
2. **Tuyên bố trạng thái sự cố**: người có thẩm quyền quyết định chuyển DR; ghi T0, mức ảnh hưởng và stakeholder.
3. **Bảo vệ dữ liệu**: xác định thời điểm replica/backup nhất quán, tạm ngăn ghi xung đột nếu kiến trúc yêu cầu; ghi nhận nguy cơ RPO.
4. **Kích hoạt vùng phụ**: đưa compute, route, database, secrets, kết nối mạng và queues vào trạng thái đã định; áp dụng script/IaC đã thử nghiệm.
5. **Kiểm tra đầu cuối**: tạo đơn thử, truy vấn dữ liệu, thử xác thực, kiểm tra event processing, error rate và latency dưới tải phù hợp.
6. **Thông báo và giám sát**: cập nhật tình trạng cho vận hành/kinh doanh, theo dõi SLI, kiểm tra nợ queue và dữ liệu cần đối soát.
7. **Failback có kiểm soát**: chỉ quay lại vùng nguồn khi dữ liệu, hướng ghi, routing và tiêu chí nghiệp vụ đều sẵn sàng. Failback là một kế hoạch riêng, không tự động diễn ra ngay sau failover.

Runbook cần được version-control, lưu nơi có thể truy cập khi hệ thống chính bị lỗi, diễn tập định kỳ và gán người trực cụ thể. Nếu chỉ một người biết cách phục hồi, RTO dự kiến rất khó đạt trong thực tế.

## 10. Liên hệ SLO với RTO/RPO và trade-off chi phí

Một thiết kế có thể **đạt RTO/RPO** trong một lần thảm họa nhưng **vi phạm SLO** trong cửa sổ đánh giá. Ví dụ SLO availability theo thời gian là 99,9% trong 28 ngày có ngân sách khoảng 40,32 phút gián đoạn hoàn toàn; sự cố mất region dài 42 phút có thể vượt ngân sách ấy, dù RTO 45 phút vẫn đạt.

Ngược lại, ứng dụng có SLI 99,95% trong tháng vừa qua vẫn có thể chưa có backup, chưa diễn tập failover và không đáp ứng RPO khi dữ liệu bị hỏng. Cần nhìn cả **chất lượng vận hành thường ngày** lẫn **khả năng chống chịu sự kiện hiếm nhưng tác động lớn**.

Các lựa chọn có trade-off thực tế:

- Đặt SLO cao hơn có thể đòi hỏi redundancy, giám sát chặt hơn, canary, kiểm thử fault injection và vận hành trực ca tốt hơn.
- RTO càng ngắn thường cần compute/route dự phòng sẵn sàng hơn; active-active hoặc warm standby tốn chi phí hơn cold restore trong nhiều trường hợp.
- RPO càng nhỏ thường đòi hỏi replication nhanh hơn, cơ chế đồng bộ/nhất quán nghiêm ngặt hơn hoặc khả năng phục hồi theo giao dịch; vẫn phải tính tới lỗi logic.
- Sử dụng nhiều region tăng chi phí truyền dữ liệu, vận hành, kiểm thử và độ phức tạp của identity/network. Những khoản này phải được so với tổn thất khi gián đoạn.

Một lựa chọn thực tế là **phân cấp theo mức độ quan trọng**: giao dịch và dữ liệu cốt lõi có mục tiêu cao hơn, báo cáo có thể chấp nhận khôi phục chậm hơn. Không nên đặt tất cả hệ thống ở mức “99,999% và RPO bằng 0” mà chưa có BIA, phương án kỹ thuật và ngân sách xác nhận.

## 11. Checklist thiết kế mục tiêu độ tin cậy

Đối với **mỗi hành trình quan trọng** của ứng dụng Azure, tài liệu vận hành nên ghi:

| Mục | Câu hỏi phải có câu trả lời |
| --- | --- |
| Chủ sở hữu và giá trị kinh doanh | Ai chịu trách nhiệm? Người dùng mất gì khi hành trình không hoạt động? |
| SLI | Good event, eligible event, measurement boundary và nguồn telemetry là gì? |
| SLO | Ngưỡng bao nhiêu, trong cửa sổ nào; error budget và no-data rule ra sao? |
| SLA liên quan | Cam kết của chính sản phẩm/đối tác/nhà cung cấp nào cần đối chiếu? |
| RTO | Kịch bản nào, T0/T4 được xác định thế nào, mức dịch vụ tối thiểu ra sao? |
| RPO | Dữ liệu nào, mốc nhất quán nào, phép đo mất dữ liệu và cơ chế đối soát là gì? |
| Kiến trúc Azure | Các điểm lỗi đơn, phụ thuộc zone/region, replication, backup, network, identity? |
| Bằng chứng | Dashboard SLI, cảnh báo, kết quả restore/DR drill gần nhất, actual RTO/RPO? |
| Vận hành | Runbook, người duyệt failover, on-call, truyền thông, rollback/failback? |
| Chi phí và phê duyệt | Lựa chọn nào được đồng ý, khi nào xem lại mục tiêu? |

Tài liệu phải được cập nhật khi thay đổi region, SKU, database, luồng dữ liệu, traffic, lịch phát hành hay yêu cầu nghiệp vụ. Một SLO/RTO/RPO tốt có người sở hữu, phép đo nhất quán và được kiểm chứng nhiều lần.

## 12. Bài tập vận dụng và tự kiểm tra

### Bài tập 1: Tính SLI, error budget và burn rate

Ứng dụng Orders có SLO **99,9%** request tạo đơn thành công trong **28 ngày**. Trong cửa sổ vừa qua, telemetry đã kiểm tra cho thấy có **1.200.000** eligible requests, trong đó **1.198.500** good requests.

Yêu cầu: tính SLI, số request xấu, error budget, số request xấu còn được phép và kết luận đạt hay trượt SLO.

**Lời giải tham khảo:**

- SLI = 1.198.500 / 1.200.000 × 100% = **99,875%**.
- Request xấu = 1.200.000 − 1.198.500 = **1.500**.
- Error budget cho phép = 1.200.000 × 0,001 = **1.200 request xấu**.
- Ngân sách còn lại = 1.200 − 1.500 = **−300**: đã vượt 300 request xấu, **SLO không đạt**.
- Error fraction thực tế = 1.500 / 1.200.000 = **0,125%**. Burn rate tính trên cả cửa sổ = 0,125% / 0,1% = **1,25×**.

### Bài tập 2: Kiểm chứng RTO/RPO

Ứng dụng có **RTO ≤ 30 phút**, **RPO ≤ 10 phút** khi mất region. Sự cố xảy ra lúc **14:00**; đội vận hành nhận cảnh báo lúc **14:05**, hoàn thành failover lúc **14:25**, nhưng đến **14:38** giao dịch mới đầu tiên mới thực hiện thành công. Bản ghi cuối cùng khôi phục nhất quán thuộc thời điểm **13:53**.

**Lời giải tham khảo:**

- Actual RTO = 14:38 − 14:00 = **38 phút** → **không đạt** RTO 30 phút. Việc hoàn thành failover kỹ thuật lúc 14:25 chưa đủ chứng minh dịch vụ đã hoạt động.
- Actual RPO = 14:00 − 13:53 = **7 phút** → **đạt** RPO 10 phút về mốc thời gian, với điều kiện các giao dịch được khôi phục nhất quán và đã đối soát.
- Biện pháp cải tiến RTO: giảm thời gian xác nhận sự cố, tự động hóa bước chuyển tuyến an toàn, khởi động trước compute vùng phụ, kiểm thử network/identity/dependency và tiêu chí canary.

### Bài tập 3: Chọn phương án kiến trúc

Một dashboard nội bộ có thể dựng lại dữ liệu từ hệ thống nguồn sau 24 giờ. Trong khi đó API thanh toán không được phép xác nhận thành công rồi làm mất giao dịch khi failover. Hãy đề xuất SLI/SLO, RTO/RPO **khác nhau** cho hai hệ thống, giải thích việc chọn backup, replica, cơ chế đối soát và ngân sách. Không lấy một con số duy nhất áp cho cả hai.

### Câu hỏi tự kiểm tra

1. Vì sao số liệu CPU hoặc số replica không phải SLI tốt cho hành trình tạo đơn?
2. Một API trả HTTP 200 nhưng tạo đơn sai: theo SLI nghiệp vụ, request này nên được tính thế nào?
3. Tại sao error budget request-based không thể tự đổi thành “phút downtime”?
4. Hệ thống đạt SLO tháng này đã chứng minh được RPO sau thảm họa chưa? Vì sao?
5. Tại sao geo-replication không tự động bảo đảm RPO = 0 và không thay thế backup độc lập?
6. Vì sao actual RTO phải kết thúc ở thời điểm khôi phục hành trình nghiệp vụ, thay vì lúc lệnh failover trả thành công?
7. Khi thiết kế DR cho ứng dụng gồm Front Door, App Service, Entra ID, Azure SQL và Service Bus, bạn cần kiểm tra phụ thuộc nào ngoài bản thân compute?

**Điểm cần ghi nhớ:** Hãy chọn **SLI đo trải nghiệm thật**, đặt **SLO kèm cửa sổ và error budget**, xây **RTO/RPO theo tác động kinh doanh và kịch bản sự cố**, sau đó dùng Azure Monitor/Application Insights, khả năng dự phòng/phục hồi của từng dịch vụ và diễn tập DR để kiểm chứng. Mục tiêu chỉ có giá trị vận hành khi đo được, có chủ sở hữu và có bằng chứng đạt/trượt.
