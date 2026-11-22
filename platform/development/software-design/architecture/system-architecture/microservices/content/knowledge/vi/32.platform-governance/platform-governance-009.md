# Đánh giá độ trưởng thành qua kết quả thay vì số lượng dịch vụ

> **Chủ đề:** Software Design / Software Architecture / System Architecture / Microservices  
> **Nhóm kiến thức:** Nền tảng và quản trị (Platform & Governance)  
> **Mục tiêu:** Đánh giá độ trưởng thành kiến trúc và tổ chức kỹ thuật dựa trên kết quả người dùng, khả năng thay đổi an toàn, độ tin cậy, bảo mật, hiệu quả vận hành và kinh tế; tránh lấy số microservice, số cluster hoặc số công cụ làm thành tích.

## 1. Vấn đề: nhiều microservice chưa chắc là một hệ thống trưởng thành

Một tổ chức đang vận hành một ứng dụng nguyên khối có 20 module. Một năm sau, tổ chức công bố đã tách thành 120 microservice, có service mesh, Kubernetes và một bộ dashboard rất lớn. Số repository, pipeline và deployment tăng nhanh. Tuy nhiên, để sửa một tính năng checkout vẫn cần sáu nhóm phối hợp, incident kéo dài hơn trước, chi phí cloud tăng gấp đôi và khách hàng vẫn gặp lỗi thanh toán.

Nếu báo cáo kiến trúc chỉ ghi **“120 microservice được triển khai”**, người đọc có thể tưởng đó là dấu hiệu tiến bộ. Trong thực tế đây chỉ là **đầu ra của hoạt động kỹ thuật** (*output*), không chứng minh **kết quả** (*outcome*) mà hệ thống mang lại.

Một tổ chức khác vẫn dùng modular monolith cho lõi nghiệp vụ và chỉ tách một số service có lý do rõ ràng. Nhóm đó triển khai thay đổi nhanh, lỗi ít, dữ liệu đúng, phục hồi sự cố tốt và chi phí phù hợp. Theo thước đo số service, tổ chức này trông “ít hiện đại” hơn; theo kết quả thực, hệ thống có thể trưởng thành hơn.

**Luận điểm chính: kiến trúc là phương tiện để đạt kết quả, không phải một cuộc thi số lượng thành phần.** Độ trưởng thành cần được quan sát thông qua năng lực thay đổi, vận hành và phục vụ nhu cầu thực, có bằng chứng lặp lại theo thời gian.

~~~text
                  Business and User Outcomes
                /          |            \
               v           v             v
          Reliability   Change Flow   Correctness & Trust
               |           |             |
               +-----------+-------------+
                           |
                 Engineering Capabilities
             Testing, deployment, ownership,
             contracts, observability, security
                           |
                 Architectural Choices
          Monolith / modular monolith / services
          events / database / platform / tooling
                           |
                  Technical Components
                Number of services, pods,
                 repos, dashboards, tools
~~~

Tầng càng thấp càng dễ đếm, nhưng thường càng xa kết quả cuối cùng. Đếm container hay API không thể thay cho câu hỏi: “Khách hàng được phục vụ tốt hơn chưa?”, “Nhóm thay đổi hệ thống nhanh và an toàn hơn chưa?”, “Rủi ro và chi phí có được kiểm soát không?”.

## 2. Phân biệt output, capability, outcome và impact

Bốn loại thông tin này có vai trò khác nhau:

| Cấp | Câu hỏi | Ví dụ |
|---|---|---|
| **Activity** | Chúng ta đã làm gì? | Tổ chức workshop DDD, viết RFC, triển khai CI |
| **Output** | Chúng ta đã tạo ra gì? | 25 service, 40 dashboard, 12 template |
| **Capability** | Chúng ta đã có khả năng lặp lại nào? | Deploy độc lập, rollback trong vài phút, truy vết request xuyên service |
| **Outcome** | Người dùng và nhóm kỹ thuật được lợi gì? | Giảm lỗi checkout, lead time thấp, incident ngắn |
| **Impact** | Giá trị tổ chức đạt được trong dài hạn là gì? | Tăng chuyển đổi, giảm tổn thất, có khả năng mở rộng sản phẩm bền vững |

**Output cần để biết công việc đã diễn ra**, nhưng output không phải bằng chứng duy nhất của thành công. Một pipeline CI được tạo ra là output; khi phần lớn thay đổi đi qua pipeline mà không cần thủ công, thời gian phát hành giảm và rollback được kiểm chứng, ta mới thấy capability và outcome.

### 2.1. Ví dụ sai và đúng

**Tuyên bố thiếu căn cứ:**
- “Kiến trúc đã trưởng thành vì có 80 microservice.”
- “Đã áp dụng cloud native vì tất cả service chạy trên Kubernetes.”
- “Observability hoàn thiện vì có 1.000 metric.”
- “DevOps thành công vì mỗi team có pipeline.”
- “Hệ thống an toàn vì dùng mTLS và có security scanner.”

**Cách diễn đạt dựa trên kết quả:**
- “Thay đổi giá sản phẩm không cần release đồng thời ba domain, thời gian triển khai giảm từ 10 ngày xuống 2 ngày mà tỷ lệ lỗi không tăng.”
- “Trong ba tháng, 99,95% request checkout hợp lệ hoàn thành trong deadline đã thỏa thuận; sự cố được phát hiện và khôi phục nhanh hơn.”
- “Một lỗi Inventory không còn làm sập toàn bộ browse journey nhờ timeout, bulkhead và fallback đúng nghiệp vụ.”
- “Các phát hiện secret và quyền truy cập sai được chặn ở CI hoặc trước production, không lan thành incident.”
- “Chi phí xử lý mỗi đơn thành công giảm khi traffic tăng, không chỉ hóa đơn cloud tổng giảm vì người dùng ít đi.”

Kết quả cần có mẫu số, cửa sổ thời gian và điều kiện đo. Một câu “nhanh hơn 50%” không rõ nhanh ở khâu nào, đo như thế nào và chất lượng có giữ nguyên hay không sẽ dễ gây hiểu sai.

## 3. Không có một “mức trưởng thành microservice” phổ quát

Một hệ thống nhỏ với một team có thể rất trưởng thành khi là modular monolith có deployment tự động, test tốt và ownership rõ. Một hệ thống gồm hàng trăm service cũng có thể hợp lý nếu domain lớn, nhiều nhóm phát triển độc lập và mỗi service đáp ứng ranh giới đúng.

Do đó:
- Không mặc định “monolith → microservices → service mesh → event-driven everything” là đường tiến hóa bắt buộc.
- Không khuyến khích tách service chỉ để đạt mốc số lượng.
- Không đánh giá mọi đơn vị kinh doanh theo cùng một độ phức tạp bắt buộc.
- Không xem sử dụng nhiều cloud product là trưởng thành nếu không mang lại capability cần thiết.
- Không đồng nhất **mức đầu tư** với **mức đạt được**.
- Không đồng nhất **có tài liệu** với **thực thi thành công**.

Độ trưởng thành là **khả năng tạo và duy trì kết quả một cách có kiểm soát**, phù hợp quy mô, yêu cầu và rủi ro của sản phẩm.

### 3.1. Câu hỏi khởi đầu tốt hơn “chúng ta có bao nhiêu service?”

1. Nhóm có thể thay đổi một phần hệ thống mà không phá phần khác không?
2. Các customer journeys quan trọng có đạt reliability và latency SLO không?
3. Khi dependency lỗi, hệ thống degrade và phục hồi theo cách dự đoán được không?
4. Incident có phát hiện được, có owner và runbook, và có học được từ sự cố không?
5. Các thay đổi về dữ liệu, API và event có backward compatibility không?
6. Quyền truy cập, dữ liệu nhạy cảm và retention có được bảo vệ thực tế không?
7. Tổng chi phí phát triển, vận hành và phục vụ mỗi giao dịch có hợp lý không?
8. Platform có giúp team tự phục vụ hay tạo thêm bước phê duyệt?
9. Business có thể thử nghiệm, học và triển khai nhu cầu mới nhanh hơn mà không tăng rủi ro?
10. Mỗi năng lực trên có được chứng minh qua số liệu, kiểm thử và hành vi lặp lại không?

## 4. Bảy chiều đánh giá quan trọng

Một scorecard cân bằng có thể nhìn qua bảy chiều. Đây là khung tham khảo có thể điều chỉnh cho mỗi tổ chức, không phải chuẩn chấm điểm bắt buộc.

| Chiều | Kết quả mong muốn | Dấu hiệu dễ đếm nhưng chưa đủ |
|---|---|---|
| Giá trị người dùng và nghiệp vụ | Luồng quan trọng hoạt động tốt, mang lại giá trị | Số API endpoint hoặc feature flags |
| Tốc độ thay đổi an toàn | Phát hành nhanh, ít hỏng, dễ rollback | Số pipeline, số lần deploy thuần túy |
| Độ tin cậy và khả năng phục hồi | SLO đạt, blast radius nhỏ, phục hồi nhanh | Số dashboard, số pod |
| Chất lượng hợp đồng và dữ liệu | API/event tương thích, dữ liệu nhất quán đủ dùng | Số schema, số topic |
| Bảo mật và quản trị rủi ro | Ít quyền thừa, dữ liệu được kiểm soát, lỗi được phát hiện | Số scanner và policy PDF |
| Hiệu quả vận hành và kinh tế | Chi phí trên kết quả hữu ích hợp lý, công sức vận hành giảm | Tổng cloud spend hay CPU utilization |
| Năng lực nhóm và nền tảng | Team tự phục vụ trong guardrails, cognitive load phù hợp | Số team, repo, template |

Các chiều có thể xung đột: tăng kiểm soát bảo mật có thể làm chậm một đường triển khai; tối ưu cloud cost quá mức có thể giảm headroom; tách dịch vụ giúp release độc lập nhưng tăng on-call và dependency. Do đó không nên chấm một con số duy nhất rồi bỏ qua các trade-off.

## 5. Kết quả người dùng và nghiệp vụ là mốc tham chiếu đầu tiên

Thay vì bắt đầu từ sơ đồ service, hãy chọn **critical user journeys** như:
- Người dùng đăng nhập và xác thực.
- Tìm kiếm sản phẩm.
- Thêm giỏ hàng.
- Đặt hàng và thanh toán.
- Kiểm tra trạng thái đơn.
- Nhận thông báo giao hàng.
- Người bán cập nhật tồn kho.

Với mỗi journey, cần thỏa thuận:
- Người dùng xem kết quả thành công là gì?
- Trạng thái “được chấp nhận” và “đã hoàn tất” khác nhau thế nào?
- Deadline end-to-end?
- Loại lỗi nào là lỗi hệ thống, loại nào là kết quả nghiệp vụ hợp lệ?
- Có rủi ro dữ liệu sai, duplicate transaction hoặc stale result không?
- Journey có phụ thuộc nhóm khác, bên thứ ba hoặc quy trình async không?
- Chỉ số nào liên hệ với giá trị sản phẩm?

Ví dụ API POST /orders trả HTTP 202 nhanh nhưng Payment saga kẹt 30 phút. Nếu chỉ đo latency HTTP, báo cáo có thể rất đẹp, trong khi user vẫn không hoàn thành đặt hàng.

### 5.1. Đo outcome đầu-cuối

Một số chỉ số khả thi:
- Tỷ lệ đơn đặt thành công trong thời gian được cam kết.
- Tỷ lệ thanh toán trùng hoặc cần xử lý thủ công.
- p95/p99 thời gian từ “đặt hàng” đến “đơn được xác nhận”.
- Tỷ lệ yêu cầu hỗ trợ vì trạng thái đơn không chính xác.
- Tỷ lệ tìm kiếm có kết quả hữu ích trong deadline.
- Tỷ lệ tính năng được phát hành và sử dụng thực tế.
- Thời gian phản hồi sự cố ảnh hưởng khách hàng.

Cần phân biệt **outcome kỹ thuật** và **business outcome**. Tỷ lệ chuyển đổi chịu ảnh hưởng của giá, chiến dịch marketing và hành vi khách hàng, không chỉ kiến trúc; không kết luận một refactor gây tăng doanh thu nếu không có thiết kế đo/đối chứng thích hợp.

### 5.2. Phân tích theo cohort

Một tỷ lệ thành công toàn hệ thống có thể che:
- Một region latency rất cao.
- Một nhóm người dùng mobile thường timeout.
- Một phương thức thanh toán lỗi.
- Một tenant lớn gây hot partition.
- Một catalog rất lớn gặp N+1 query.

Hãy phân nhóm có ý nghĩa theo product path, region, client type, dependency, tier hoặc workload class. Giữ quyền riêng tư và giới hạn cardinality khi đo; không đưa user ID hay email vào metric label.

## 6. Độ tin cậy: đo SLI/SLO, không đếm số lớp dự phòng

Một hệ thống có ba region, nhiều replica và service mesh chưa chắc đáng tin nếu lỗi schema, config hoặc shared database khiến mọi region cùng hỏng.

**SLI (Service Level Indicator)** là phép đo chất lượng quan sát được. **SLO (Service Level Objective)** là mục tiêu đặt trên SLI trong một cửa sổ đã thống nhất.

Ví dụ:
- Availability SLI: tỷ lệ request hợp lệ nhận được kết quả đúng theo hợp đồng.
- Latency SLI: tỷ lệ request hoàn thành dưới deadline.
- Freshness SLI: tỷ lệ thay đổi nguồn được phản ánh ở read model trong giới hạn.
- Completion SLI: tỷ lệ saga hoặc job kết thúc hợp lệ đúng hạn.
- Correctness SLI: tỷ lệ nghiệp vụ không tạo duplicate hoặc sai lệch trạng thái.

### 6.1. Một SLO minh họa cho Checkout

~~~text
Good Checkout Ratio
  = số yêu cầu Checkout hợp lệ đạt terminal outcome đúng
    trong <= 30 giây
    /
    tổng số yêu cầu Checkout hợp lệ đủ tuổi đánh giá
~~~

Mục tiêu ví dụ: 99,5% trên cửa sổ 28 ngày. Đây là ngưỡng minh họa, phải điều chỉnh theo nhu cầu sản phẩm và rủi ro.

Chỉ lấy số saga đã COMPLETED để đo duration sẽ bỏ qua saga treo mãi và tạo **survivorship bias**. Mẫu số phải có những workflow đã bắt đầu và đủ thời gian đánh giá, kể cả chúng chưa đạt terminal.

### 6.2. Error budget dẫn dắt thay đổi

Nếu SLO là 99,9%, phần không tốt cho phép theo mô hình đơn giản là 0,1% trong cửa sổ. **Error budget** giúp team cân bằng tốc độ thay đổi với ổn định:
- Khi còn budget và không có rủi ro bất thường, có thể canary những thay đổi đã kiểm.
- Khi burn rate vượt ngưỡng, ưu tiên sửa reliability và giảm rollout rủi ro.
- Không dùng budget như “quyền được làm hỏng dữ liệu”; correctness/security policy vẫn là giới hạn cứng.

Một tổ chức trưởng thành không chỉ báo cáo “uptime 99,99%” mà biết **SLO nào bảo vệ trải nghiệm thực**, budget đang bị đốt bởi đâu, ai có quyền quyết và cách thay đổi hành vi khi vượt ngưỡng.

### 6.3. Resilience đo bằng hành vi lỗi

Câu hỏi đánh giá:
- Dependency chậm 10 lần thì caller có deadline, bulkhead và load shedding không?
- Một service lỗi có làm lan sang tất cả customer journeys không?
- Khi mất một zone/replica, hệ thống có đủ headroom không?
- Retry có giới hạn, idempotent và backoff hợp lý không?
- Queue backlog có phát hiện được và rút giảm sau phục hồi không?
- Khi restore backup, dữ liệu có đúng, RTO/RPO có được kiểm chứng không?
- Một lỗi cache có đánh sập database không?
- Đã test failover/chaos trong phạm vi an toàn chưa?

Đếm số circuit breaker hoặc số backup không thay bằng việc **thử và quan sát kết quả**.

## 7. Khả năng thay đổi: tốc độ đi cùng chất lượng

Một kiến trúc được kỳ vọng giúp các team phát triển độc lập. Để biết có đạt điều đó không, theo dõi thực tế từ ý tưởng đến production và từ production đến phản hồi học tập.

Những chỉ số của luồng thay đổi thường được nhắc đến:
- **Deployment frequency:** tần suất đưa thay đổi vào production.
- **Change lead time:** thời gian từ thời điểm được chọn trong quy trình thay đổi đến production; phải định nghĩa điểm bắt đầu rõ.
- **Change failure rate:** tỷ lệ deployment gây sự cố, rollback, hotfix hoặc remediation theo định nghĩa đã thống nhất.
- **Failed deployment recovery time:** thời gian khôi phục sau deployment lỗi, đo theo semantic cụ thể.
- **Deployment rework rate:** tỷ lệ thay đổi cần sửa lại ngoài kế hoạch, nếu tổ chức chọn theo dõi.

Các bộ metric và thuật ngữ có thể phát triển theo thời gian; hãy công bố **định nghĩa nội bộ đang dùng**, không so sánh mù với bảng xếp hạng bên ngoài.

### 7.1. Vì sao deployment frequency không đủ?

Một team triển khai 100 lần/ngày vì phải sửa lỗi, rollback liên tục chưa chắc tốt hơn team deploy 10 lần/ngày với thay đổi nhỏ, an toàn và mang lại giá trị. Đếm deployment không nói:
- Thay đổi có đến người dùng thực không?
- Có phải rollback/hotfix không?
- Review/test có làm tắc pipeline không?
- Có nhiều team phải đồng bộ một deployment không?
- Một migration kéo dài bao nhiêu ngày?
- Sau release có đo adoption và kết quả không?

Dùng bộ chỉ số cân bằng: **lead time + failure/recovery + business outcome**.

### 7.2. Độc lập release phải là năng lực thật

Ví dụ Product Team muốn thay hành vi gợi ý. Nếu phải chờ:
1. Customer Team đổi shared DTO.
2. Order Team nâng shared model.
3. Platform Team cập nhật gateway.
4. Analytics Team nâng event parser.
5. Cùng một release window cho bốn service.

Thì có nhiều microservice nhưng autonomy thấp. Kiến trúc có thể vẫn là **distributed monolith**: tách process mà coupling thay đổi còn chặt.

Một indicator đáng chú ý:

~~~text
Independent Change Ratio
  = số thay đổi trong phạm vi một bounded context
    triển khai mà không đòi release đồng thời ở context khác
    /
    số thay đổi trong phạm vi tương ứng
~~~

Cần định nghĩa rõ “thay đổi độc lập” và chọn tập thay đổi có thể so sánh. Tính độc lập không đồng nghĩa không giao tiếp: cần thỏa thuận contract khi thay đổi interface.

### 7.3. Tỷ lệ đổi cùng lúc và hiệu quả release

Có thể đo:
- Số service phải deploy cho một user story điển hình.
- Số team phải đồng bộ trong một thay đổi contract.
- Tỷ lệ thay đổi buộc chỉnh shared schema hoặc shared DB.
- Thời gian chờ phê duyệt/đợi nhóm khác.
- Thời gian từ merge đến deploy tự động.
- Tỷ lệ rollback thành công trong thời gian đã thỏa thuận.
- Số feature flags tồn lâu mà không có owner.
- Mức độ an toàn khi chạy phiên bản cũ/mới cùng lúc.

Con số thấp không tự động tốt cho mọi use case; một quy trình thay đổi payment toàn hệ thống có thể cần nhiều bên phê duyệt chính đáng.

## 8. Khả năng vận hành: khôi phục quan trọng hơn số dashboard

Một hệ thống với 300 dashboard nhưng không biết request người dùng đi qua service nào vẫn có thể vận hành kém.

Một tổ chức trưởng thành có khả năng:
1. Phát hiện vấn đề ảnh hưởng người dùng.
2. Xác định phạm vi và mức độ ưu tiên.
3. Tìm owner của service và customer journey.
4. Khoanh vùng dependency, deployment hoặc dữ liệu sai.
5. Chọn mitigation ít rủi ro và có khả năng rollback.
6. Khôi phục dịch vụ trong mục tiêu.
7. Xử lý phần dữ liệu/backlog/saga còn dở.
8. Rút kinh nghiệm và kiểm tra biện pháp ngăn tái diễn.

### 8.1. Nhóm chỉ số vận hành

| Chỉ số | Câu hỏi |
|---|---|
| Time to detect | Mất bao lâu từ lúc ảnh hưởng bắt đầu đến khi phát hiện? |
| Time to acknowledge | Có ai chịu trách nhiệm và bắt đầu xử lý? |
| Time to mitigate | Mất bao lâu để hạn chế tác động người dùng? |
| Time to restore | Mất bao lâu để service/journey hồi phục đạt yêu cầu? |
| Customer-impact duration | Người dùng bị ảnh hưởng bao lâu, mức nào? |
| Blast radius | Bao nhiêu journey/region/tenant bị ảnh hưởng? |
| Incident recurrence | Lỗi tương tự có lặp sau biện pháp khắc phục? |
| Action item completion | Các biện pháp đã hứa có được thực hiện và chứng minh? |

Cần biết cách xác định thời điểm bắt đầu/kết thúc. Một sự cố dữ liệu sai nhưng API vẫn trả 200 không thể đo như outage HTTP thông thường.

### 8.2. “Có runbook” khác “runbook chạy được”

Bằng chứng mạnh hơn có thể là:
- On-call chưa từng gặp service vẫn định vị được owner và dashboard.
- Rollback đã được diễn tập, không cần người viết ban đầu.
- Reconciliation xử lý được saga kẹt mà không thanh toán trùng.
- Restore từ backup đã được thử trong môi trường cách ly.
- Alert chỉ bật khi cần hành động và có hướng xử lý.
- Incident review ghi các yếu tố hệ thống, không chỉ đổ lỗi con người.
- Thay đổi từ postmortem làm giảm khả năng tái diễn có bằng chứng.

## 9. Chất lượng ranh giới và hợp đồng tích hợp

Một hệ thống có service tách riêng nhưng dùng chung bảng dữ liệu, shared mutable domain library và đổi enum không kiểm soát sẽ rất khó thay đổi.

Đánh giá:
- Service có domain owner và consumer inventory rõ không?
- API/event schemas có version và semantic contract không?
- Breaking change có được phát hiện trước release không?
- Có consumer contract tests và migration path không?
- Có bao nhiêu sự cố do event deserialization, shared DTO hoặc schema migration?
- Consumer có thể chậm nâng phiên bản mà hệ thống vẫn hoạt động không?
- Có direct database access xuyên owner không?
- Có event payload chứa dữ liệu nhạy cảm quá mức không?
- Data consistency và nguồn sự thật được mô tả không?
- Có phương án xử lý replay, duplicate, out-of-order và DLQ không?

### 9.1. Không lấy “số event topic” làm mức độ event-driven

Một hệ thống có 200 topic nhưng message được publish kiểu fire-and-forget không có outbox, không idempotency và không DLQ runbook có thể kém trưởng thành hơn hệ thống có 10 topic được quản trị rõ.

Một event contract trưởng thành có:
- Tên sự kiện và ý nghĩa nghiệp vụ rõ.
- Owner và danh sách consumer.
- Schema/version, compatibility rules.
- Event ID, correlation ID và ordering scope.
- Delivery assumptions và retry/replay semantics.
- Phân loại dữ liệu, retention và quyền truy cập.
- SLO xử lý, monitoring, DLQ/reconciliation policy.
- Migration/deprecation process.

### 9.2. Chỉ số về contract và coupling

Một số tín hiệu:
- Consumer compatibility failures trước và sau production.
- Sự cố do thay đổi public API/event.
- Tỷ lệ schema changes có migration plan.
- Số shared database writes xuyên boundary.
- Thời gian deprecate interface cũ sau khi consumer di chuyển.
- Số team cần phối hợp cho thay đổi cục bộ.
- Số fallback/adapter tạm không có owner hoặc deadline.

Không tối đa hóa “zero integration coordination” bằng mọi giá. Contract quan trọng cần được thảo luận; mục tiêu là **không phải phối hợp cho những chi tiết đáng lẽ nội bộ**.

## 10. Bảo mật và quản trị dữ liệu: kết quả kiểm soát, không chỉ checklist

Một platform có nhiều security scanner, role IAM, WAF rule và secret store nhưng vẫn cho phép log chứa token hoặc service truy cập dữ liệu tenant khác là chưa đạt kết quả mong muốn.

Thay vì đếm công cụ, đo:
- Thời gian phát hiện và khắc phục lỗ hổng theo mức nghiêm trọng và exposure.
- Tỷ lệ secrets được quản lý và xoay theo policy.
- Số quyền đặc quyền không còn owner.
- Tỷ lệ endpoint nhạy cảm có authorization/integration tests.
- Tỷ lệ service có workload identity riêng và least privilege.
- Số sự cố lộ token/PII hoặc truy cập trái phép.
- Khả năng khoanh vùng blast radius của credential compromise.
- Tỷ lệ dữ liệu nhạy cảm có owner, classification, retention và purpose.
- Tỷ lệ yêu cầu xóa/chỉnh sửa dữ liệu được thực thi đúng hạn, có bằng chứng tại downstream.
- Số bản sao dữ liệu ngoài mục đích được phát hiện và xử lý.

Không dùng “không có incident báo cáo” làm bằng chứng đủ: có thể thiếu monitoring hoặc văn hóa báo cáo. Cần **kiểm thử chủ động, audit có kiểm soát và đo hiệu quả biện pháp**.

### 10.1. Security guardrails giúp tự chủ

Một dấu hiệu trưởng thành là team có thể deploy độc lập **bên trong rào chắn an toàn**:
- CI ngăn secret leak và cấu hình rủi ro.
- API tự enforce identity, authorization và tenant isolation.
- Platform cung cấp secret rotation và policy templates.
- Khi cần ngoại lệ, có owner, lý do, thời hạn và kiểm soát bù trừ.

Nếu mọi thay đổi phải chờ họp architecture board, tốc độ giảm. Nếu mọi policy chỉ là wiki và không ai kiểm tra, rủi ro tăng. Độ trưởng thành nằm ở **khả năng tự phục vụ an toàn được kiểm chứng**, không phải số trang policy.

### 10.2. Data correctness cũng là năng lực trưởng thành

Một hệ thống thanh toán không trùng giao dịch khi timeout và retry có thể đáng giá hơn tăng thêm một lớp cache. Đo:
- Duplicate prevention rate.
- Số giao dịch có trạng thái “không xác định” phải reconcile.
- Tỷ lệ thất bại compensation.
- Projection staleness so với nguồn.
- Tỷ lệ mismatch giữa write model và read model.
- Thời gian phục hồi sau replay hoặc schema migration.
- Số lần yêu cầu customer support can thiệp vào consistency.

Các chỉ số phải có định nghĩa và mẫu số để so sánh. Không đếm tất cả retries là lỗi dữ liệu; có retry thành công và hợp lệ.

## 11. Hiệu quả chi phí: chi phí trên một đơn vị giá trị

Tổng chi phí cloud giảm có thể do traffic giảm, ngừng một thị trường hoặc tắt chức năng. Tổng chi phí tăng có thể hợp lý nếu phục vụ gấp nhiều lần người dùng với chất lượng tốt hơn.

Cần kết hợp chi phí với **khối lượng công việc hữu ích**:

~~~text
Cost per successful order
  = attributed cost of serving Order workflow
    /
    number of successful orders in same window
~~~

Hoặc:
- Cost per 1.000 valid API requests đạt SLO.
- Cost per GB processed có tính toàn vẹn.
- Cost per active user journey.
- Cost per event processed bền vững.
- Cost to operate/restore một service theo mức vận hành.

Chi phí “attributed cost” cần cách phân bổ rõ: database dùng chung, monitoring, network egress, support licenses, người vận hành và storage/backup. Không so sánh số của các nhóm khi một nhóm bị tính toàn bộ chi phí chung còn nhóm khác không.

### 11.1. Đếm microservice có thể che chi phí không nhìn thấy

Mỗi service có thể thêm:
- Pipeline, image build, runtime và base memory.
- Sidecar, proxy, network và TLS.
- Connection pool, DB/broker client.
- Dashboard, alert và on-call ownership.
- Security patching, secret và quyền truy cập.
- API contract, versioning, test và migration.
- Incident coordination và cross-team communication.

Một service rỗng có thể ít dùng CPU nhưng vẫn tạo cognitive load và operational surface area. Nếu tách service giúp domain độc lập, scale hiệu quả và failure isolation thì chi phí đó có thể đáng. Cần chứng minh lợi ích vượt chi phí.

### 11.2. FinOps và kiến trúc

Đo:
- Idle resource và capacity headroom theo SLO.
- Request/operation unit cost.
- Chi phí storage nhân bản và retention.
- Network egress giữa region/zone/service.
- Redis/DB cache misses và read/write amplification.
- Tỷ lệ autoscaling sử dụng tài nguyên có ích.
- Chi phí observability tương ứng với mức tín hiệu hữu ích.
- Cost anomaly sau release.
- Số lần service ít traffic nhưng có support burden lớn.

Không tối ưu bill bằng cách cắt hết dự phòng cần thiết. Độ trưởng thành kinh tế có nghĩa **quyết định chi phí hiểu rõ trade-off với availability, security, latency và hiệu suất phát triển**.

## 12. Platform maturity: developer self-service thay vì số công cụ

Platform team có thể tạo nhiều template, chart và command-line tools, nhưng người dùng nội bộ vẫn phải tạo ticket để xin cluster, chờ cấu hình IAM hoặc hỏi đúng một chuyên gia khi deploy lỗi.

Một platform trưởng thành được xem như **sản phẩm nội bộ** phục vụ những team xây tính năng. Câu hỏi:
- Onboard một service mới mất bao lâu từ yêu cầu hợp lệ đến môi trường sẵn sàng?
- Developer tự tạo môi trường, deploy, xem trace, rollback được không?
- Golden path có được áp dụng vì hữu ích hay vì bắt buộc?
- Tỷ lệ platform support tickets giảm theo loại vấn đề?
- Những bước nào cần phê duyệt thủ công, vì sao?
- Người dùng có thể đi ngoài golden path khi có lý do hợp lý và vẫn đáp ứng contract không?
- Platform có SLO, documentation, owner và feedback loop không?

### 12.1. Outcome-based platform measures

| Outcome | Tín hiệu |
|---|---|
| Tạo service nhanh và an toàn | Time to first successful deploy |
| Tự phục vụ hiệu quả | Tỷ lệ thao tác deploy/env/secret không cần ticket |
| Giảm cognitive load | Thời gian setup và đánh giá từ developer |
| Vận hành tốt | Rollback success, health checks, tracing coverage |
| Guardrails hoạt động | Violation caught pre-production, exception lifecycle |
| Adoption tự nhiên | Tỷ lệ team sử dụng và tiếp tục sử dụng golden path |
| Platform ổn định | Platform SLO và developer-impact duration |
| Chi phí phục vụ có kiểm soát | Unit cost, idle waste và support toil |

Đừng biến “adoption 100%” thành mục tiêu mù: với workload khác biệt, một ngoại lệ được quản trị có thể tốt hơn ép team dùng template không phù hợp.

### 12.2. Platform as a product

Platform cần:
- Xác định user persona: developer, QA, on-call, security, data engineer.
- Thu thập jobs-to-be-done thay vì chỉ yêu cầu tính năng kỹ thuật.
- Có roadmap ưu tiên theo giảm thời gian chờ và giảm lỗi.
- Đo thành công của người dùng nội bộ.
- Cung cấp APIs/docs có version.
- Phản hồi incident và bug như sản phẩm thật.
- Xác định trách nhiệm phân chia giữa platform và service owner.

Mức trưởng thành không tăng chỉ vì platform team to hơn; nó tăng khi những nhóm khác **làm việc độc lập hơn mà vẫn an toàn**.

## 13. Con người và tổ chức: cognitive load, ownership, khả năng phối hợp

Kiến trúc và tổ chức tác động lẫn nhau. Một team sở hữu 40 microservice có thể ngập trong alert, dependency update và on-call. Nếu phải dành phần lớn thời gian “giữ đèn sáng”, quyền tự chủ trên giấy ít có giá trị.

Đo các kết quả:
- Tỷ lệ thời gian dành cho planned product work so với toil.
- On-call pages có cần hành động và số false positives.
- Time-to-understand một service khi người mới nhận ownership.
- Số hệ thống cần hiểu để giao một thay đổi thông thường.
- Thời gian chờ cross-team dependency.
- Developer experience qua khảo sát có câu hỏi cụ thể.
- Tỷ lệ bàn giao service có runbook, dashboard, contract và DRI.
- Kết quả incident review và tốc độ khắc phục systemic issues.

### 13.1. Team autonomy là capability, không phải khẩu hiệu

Dấu hiệu:
- Team tự triển khai thay đổi không ảnh hưởng public contract.
- Team có quyền xem metric/trace, deploy và rollback.
- Có quyền thiết kế domain data nội bộ trong policy.
- Phải phối hợp khi API/event/security/data contract thay đổi.
- Không phụ thuộc một cá nhân “giữ chìa khóa” production.
- Có escalation khi quyết định liên nhóm bị xung đột.
- Có đủ nhân lực và kỹ năng để vận hành service mình sở hữu.

**Tự chủ không có nghĩa bỏ qua hợp đồng chung.** Một team được quyền chọn thư viện logging nhưng vẫn phải truyền trace context và không log PII. Quyền chọn công cụ là đầu vào; khả năng vận hành xuyên service là kết quả.

### 13.2. Không đếm số team như thước đo phân quyền

Chia một nhóm thành tám nhóm không tự tạo ra independence. Nếu mọi thay đổi vẫn cần đủ tám người đồng ý và các nhóm chia sẻ cùng DB, cơ cấu tổ chức có thể còn làm chậm hơn.

Đánh giá ranh giới theo **mức coupling trong công việc**, chứ không theo số team/repository.

## 14. Phản ví dụ: distributed monolith rất nhiều service

Một hệ thống có:
- 90 service và 90 repository.
- Deployment trên Kubernetes.
- 200 topic.
- Một shared “customer-core” library.
- Nhiều service đọc/ghi cùng database.
- Không có versioned API contract.
- Feature mới phải cập nhật 8 service đồng thời.
- Một lỗi schema lan sang 30 consumer.
- Mỗi service có dashboard, nhưng không có end-to-end trace.
- Incident owner không rõ, team này đổ lỗi team kia.

Những con số lớn không tạo sự trưởng thành. Đây có thể là **distributed monolith** nếu process tách nhưng coupling về dữ liệu, thay đổi và failure còn chặt.

Dấu hiệu đo được:
- Lead time kéo dài.
- Change failure rate tăng.
- Incident blast radius rộng.
- Tần suất synchronized release cao.
- On-call burden và cloud bill tăng.
- Không thể rollback một service riêng.
- Tỷ lệ event contract violations cao.
- Người dùng không thấy cải thiện.

Không nhất thiết phải gộp ngay tất cả service về một monolith. Cần tìm boundary sai, shared database access, contract thiếu và ownership mờ; thay đổi có căn cứ, đo lại sau mỗi bước.

## 15. Phản ví dụ: modular monolith trưởng thành

Một ứng dụng có một deployment artifact nhưng:
- Module rõ theo domain, dependency direction được kiểm.
- APIs nội bộ qua interface versioned khi cần.
- Integration và unit tests đáng tin.
- Deploy tự động, rollback có kiểm.
- Tracing, logs, metrics và SLO đầu-cuối.
- Quyền truy cập và dữ liệu được phân quyền đúng.
- Database migration có expand/contract.
- Nhóm có thể triển khai tính năng với ít coordination.
- Chi phí vận hành phù hợp tải.
- Khi cần scale hoặc tách một boundary, có dữ liệu quyết định.

Đây có thể là lựa chọn hợp lý và trưởng thành. **Tách thành microservice là một lựa chọn để giải quyết vấn đề cụ thể**, không phải bài thi phải đạt mốc số service.

### 15.1. Khi nào tách service là outcome-driven?

Một quyết định tách nên nêu rõ giả thuyết:
- Domain có tốc độ thay đổi độc lập.
- Ownership rõ và ít transaction xuyên boundary.
- Có nhu cầu scale khác biệt đáng kể.
- Failure isolation hoặc security isolation mang lại lợi ích.
- Một module đang làm chậm deployment toàn hệ thống.
- Yêu cầu data residency hoặc compliance khác.
- Có đội đủ năng lực vận hành độc lập.

Sau khi tách, đo:
- Lead time của hai domain có giảm không?
- SLO của mỗi journey tốt hơn không?
- Có giảm diện tích lỗi không?
- Chi phí network/ops có vượt lợi ích không?
- Số change phải phối hợp có giảm không?
- Data consistency có còn đảm bảo không?

Nếu không có cải thiện hoặc không có lý do duy trì chi phí, cân nhắc đổi boundary hoặc hợp nhất một phần.

## 16. Chọn metric dẫn dắt và metric kết quả

**Lagging indicators** phản ánh hậu quả đã xảy ra: incident, downtime, chi phí trên order, conversion. **Leading indicators** phản ánh năng lực/điều kiện có thể ảnh hưởng tương lai: contract tests, canary coverage, rollback drills, dependency budgets, security patch latency.

Một scorecard cân bằng cần cả hai.

| Mục tiêu | Leading signal | Lagging outcome |
|---|---|---|
| Release an toàn | Automated contract tests, canary, rollback rehearsal | Deployment failures, recovery duration |
| Giảm sự cố API | SLO alerts, dependency timeouts, failure injection | Customer-impact minutes |
| Tránh dữ liệu sai | Idempotency tests, versioned events, reconciliation | Duplicate transactions, projection mismatch |
| Phòng secret leak | Secret scans, least-privilege reviews | Exposed credentials/incidents |
| Tăng tự chủ | Self-service pipeline, consumer inventory | Lead time, cross-team blockers |
| Giảm cloud waste | Cost attribution, autoscaling policies | Unit cost per successful operation |
| Giảm overload | Load tests, rate/concurrency limits | p99 under peak, dropped valid requests |

Leading signal chỉ có ý nghĩa nếu thực sự dẫn đến outcome. Một trăm bài test không có giá trị nếu tất cả chỉ kiểm “service starts” và không bắt được lỗi ảnh hưởng user.

### 16.1. Một metric không nên vừa làm mục tiêu duy nhất vừa làm thưởng phạt cứng

Khi một metric trở thành mục tiêu duy nhất, người ta có thể tối ưu con số thay vì hệ thống. Ví dụ:
- Chia một feature thành 20 deployment để tăng frequency.
- Đóng incident sớm rồi mở lại để cải thiện MTTR.
- Tránh báo cáo lỗi để làm đẹp change failure rate.
- Chỉ đo những request đã thành công để cải thiện p99.
- Tách service nhỏ không cần thiết để tăng “microservice adoption”.
- Cắt monitoring để giảm cost/transaction.
- Chuyển lỗi sang 4xx để giảm 5xx.

Hãy dùng metric theo **bộ**, kết hợp kiểm tra chất lượng dữ liệu, bối cảnh và đánh giá định tính. Không thưởng phạt team chỉ bằng một ranking.

## 17. Cách xây một scorecard độ trưởng thành

Một scorecard nên trả lời rõ ba lớp:

1. **Outcome:** kết quả người dùng hoặc tổ chức mong muốn.
2. **Evidence:** số liệu, log, kiểm thử, khảo sát, incident review nào chứng minh?
3. **Next action:** điểm nghẽn nào cần thay đổi để cải thiện?

Mẫu:

| Chiều | Outcome mong muốn | Evidence | Owner | Hành động tiếp theo |
|---|---|---|---|---|
| Checkout reliability | Giảm thao tác treo quá hạn | Saga terminal SLI, incident tickets | Checkout | Timeout/reconciliation |
| Safe delivery | Đổi một module không rollback nhiều service | Lead time, change failure, release coupling | Domain team | Consumer contract tests |
| Operational recovery | Phục hồi nhanh và ít ảnh hưởng | Incident timelines, restore drills | On-call/service owner | Runbook/canary |
| Data governance | Tránh bản sao nhạy cảm không chủ | Data inventory, deletion propagation | Data owner | Contract/retention |
| Platform enablement | Developer tự deploy/rollback | Self-service completion time | Platform | Golden path |
| Cost effectiveness | Cost trên completed order ổn định | Cloud allocation + business volume | Service/FinOps | Right-size/optimize |

### 17.1. Mẫu phiếu đánh giá từng chỉ số

~~~yaml
metricId: checkout_completion_within_30s
purpose: Protect customer checkout experience
owner: checkout-team
numerator: eligible checkouts with valid terminal result <= 30s
denominator: all eligible checkouts old enough to evaluate
window: 28d
segmentation:
  - region
  - payment_provider_type
source:
  - durable saga state
  - checkout events
constraints:
  - exclude only explicitly invalid test traffic
  - never count still-stuck sagas as completed
targetRef: approved-checkout-slo
reviewCadence: weekly
actionWhenBreached: review backlog, dependency and incident
~~~

Đây là metadata minh họa, không phải một SLO đã được phê duyệt. Mục đích là cho phép người khác hiểu **cách tính, owner, nguồn sự thật và hành động**.

### 17.2. Độ tin cậy của dữ liệu đo

Trước khi tin dashboard:
- Có nguồn dữ liệu đúng nghĩa completion không?
- Có missing events, duplicate retries hoặc sampling không?
- Start/end timestamps dùng clock nào?
- Mẫu số có loại bỏ các request đã timeout/hang không?
- Deployments có bao gồm rollback/hotfix không?
- Incident start time lấy khi phát hiện hay khi thực sự ảnh hưởng user?
- Cost attribution có nhất quán theo window không?
- Segment ít traffic có interval tin cậy thấp không?
- Thay đổi cách đo có tạo “cải thiện” giả so với baseline không?

Một tổ chức trưởng thành không chỉ có dữ liệu; tổ chức còn **biết dữ liệu có thể sai ở đâu**.

## 18. Thang mô tả theo năng lực, không phải số service

Có thể dùng năm mức mô tả **cho từng chiều riêng**. Không nên biến thành một chứng chỉ bắt buộc hay điểm tổng duy nhất:

| Mức mô tả | Đặc điểm |
|---|---|
| **0 — Không quan sát được** | Không có owner/mẫu số/định nghĩa; chỉ có cảm nhận hoặc đếm output |
| **1 — Có đo nhưng phản ứng** | Metric lẻ, incident xử lý thủ công, kết quả thiếu ổn định |
| **2 — Có quy trình lặp lại** | SLO/contract/rollback cơ bản, một số kiểm soát tự động |
| **3 — Được quản lý bằng kết quả** | Metric có owner, threshold, review/action, giảm lỗi qua nhiều chu kỳ |
| **4 — Học và tối ưu liên tục** | Chủ động thử nghiệm, dự báo rủi ro, điều chỉnh architecture dựa vào bằng chứng |

Cách diễn giải ví dụ:

**Release maturity mức 1:** team biết mỗi tháng deploy bao nhiêu lần nhưng không biết có bao nhiêu rollback hoặc bao nhiêu thay đổi buộc các team khác release cùng.

**Release maturity mức 3:** team đo lead time, failure, coupling, chạy compatibility checks và dùng kết quả để điều chỉnh pipeline.

**Reliability mức 4:** ngoài SLO và incident review, team diễn tập dependency failure, đo customer impact, đưa bài học vào test/guardrail và xác nhận tỷ lệ tái diễn giảm.

### 18.1. Không chấm theo trung bình đơn giản

Một tổ chức đạt “4” ở self-service deployment nhưng “0” ở tenant isolation không nên được công bố “trưởng thành 3,2/4” rồi xem như tốt. Một số chiều là **ngưỡng an toàn bắt buộc**, không bù được bằng tốc độ hay chi phí.

Có thể trình bày profile theo từng chiều, nêu rõ red flags và minimum viable control, thay vì chỉ xếp hạng tổng.

### 18.2. Đánh giá theo workload và risk tier

Một hệ thống thanh toán có yêu cầu consistency, audit và incident response khác một dịch vụ gợi ý nội dung không quan trọng. Cần phân loại:
- Tier của user journey.
- Mức độ nhạy cảm dữ liệu.
- Traffic peak.
- Dependency và blast radius.
- Regulatory/contractual obligations.
- Business criticality.

Không áp cùng mục tiêu phục hồi vài giây cho mọi batch job, và không cho payment hệ thống quan trọng bỏ idempotency chỉ vì một service đơn giản khác không cần.

## 19. Thu thập evidence từ đâu?

| Nguồn | Có thể chứng minh | Giới hạn |
|---|---|---|
| CI/CD records | Lead time, deployment count, rollback/hotfix | Cần liên kết commit/PR/release và định nghĩa |
| Observability | Latency, error, saturation, traces, customer journey | Sampling, missing spans, 200 không đồng nghĩa nghiệp vụ đúng |
| Durable workflow state | Saga completion, timeout, compensation | Cần semantics rõ và dữ liệu đáng tin |
| Incident management | Thời gian tác động, nguyên nhân, recurrence | Incident reporting có thể không nhất quán |
| Service catalog | Owner, API, data, SLO, runbook, dependencies | Metadata có thể stale |
| Contract/schema registry | Compatibility và consumer versions | Không tự phát hiện semantic change |
| Security/IAM audit | Quyền và truy cập, findings, secrets | Không chứng minh hoàn toàn không có lỗ hổng |
| Cloud billing/FinOps | Cost và allocation | Shared cost, usage spikes, accounting delay |
| Developer survey | Cognitive load, self-service pain points | Cảm nhận chủ quan, cần đối chiếu hành vi |
| Business analytics | Conversion, retention, completed orders | Bị ảnh hưởng bởi yếu tố ngoài kiến trúc |
| Load/failover drills | Headroom, blast radius, restore khả thi | Điều kiện test có thể khác production |

Không cần ngay lập tức mua một bộ công cụ maturity mới. Bắt đầu bằng những nguồn hiện có, định nghĩa rõ và ưu tiên các lỗ hổng đo lường ảnh hưởng quyết định.

## 20. Tách metric về team, service và journey

Một hệ thống nhiều team có ít nhất ba góc nhìn:

**Service-level:** Order API p99, connection pool saturation, number of retries, data consistency, security posture.

**Team-level:** change lead time, cross-team blockers, operational toil, ability to rollback, incident ownership.

**Journey-level:** tỷ lệ checkout thành công, payment completion, customer-impact time, tổng chi phí trên đơn.

Không lấy service-level metric để suy trực tiếp journey-level outcome: mọi service có p99 tốt chưa chắc checkout hoàn tất nếu callback bị mất. Tương tự, business outcome tốt không phủ nhận một service có critical vulnerability.

### 20.1. Nền tảng chung cần báo cáo ở góc nhìn người dùng nội bộ

Platform deployment service có uptime cao nhưng developer vẫn mất hai ngày chờ quyền có nghĩa **platform outcome chưa tốt**. Cần đo cả reliability của platform API và thời gian nhóm sản phẩm thực hiện việc cần làm.

### 20.2. Dữ liệu cần được phân nhóm theo bối cảnh

So sánh hai team phải xét:
- Criticality.
- Số legacy dependency.
- Workload type.
- Phạm vi sở hữu.
- Mức thay đổi nghiệp vụ.
- Yêu cầu pháp lý.
- Cấp độ tự động hóa trước đây.
- Chất lượng và tuổi codebase.

Xếp hạng team mà không xét bối cảnh dễ tạo cạnh tranh số liệu và giấu incident. Mục tiêu là tìm **điểm nghẽn có thể cải thiện**, không phải làm đẹp leaderboard.

## 21. Case study: hai hệ thống có số service khác nhau

Giả sử tổ chức A có 75 microservice; tổ chức B có một modular monolith và 8 service chuyên biệt. Đây là ví dụ giả định:

| Chỉ số trong cùng điều kiện giả định | A: 75 services | B: modular + 8 services |
|---|---:|---:|
| Median lead time cho thay đổi sản phẩm | 12 ngày | 2 ngày |
| Thay đổi cần release đồng thời nhiều domain | 65% | 12% |
| Tỷ lệ deployment gây rollback/remediation | 14% | 4% |
| Thời gian phục hồi median sau deployment lỗi | 90 phút | 20 phút |
| Checkout completion đúng hạn | 96,8% | 99,5% |
| Cost trên một đơn thành công | 0,42 đơn vị | 0,21 đơn vị |
| Service/journey có owner và runbook được kiểm | 70% | 98% |
| Số service | 75 | 9 đơn vị triển khai chính |

Không có kết luận “modular monolith luôn tốt hơn”. B có thể đang ở quy mô nhỏ hơn hoặc có yêu cầu khác; cần so sánh theo workload, traffic, rủi ro, nguồn lực và mẫu số tương đương.

Nhưng nếu các điều kiện có thể đối chiếu, chỉ số **outcome** cho thấy B có thể trưởng thành hơn A, bất chấp số service ít hơn.

### 21.1. Phân tích của tổ chức A

Những câu hỏi cần điều tra:
- Có dùng chung database hoặc domain model library khiến mỗi thay đổi lan nhiều nơi không?
- Các service có đúng bounded context không?
- Tỷ lệ event/schema breaking changes và synchronized release bao nhiêu?
- Có contract testing và expand-and-contract không?
- On-call có bị chia nhỏ ownership?
- Có nhiều retries gây overload downstream không?
- Có path nào đáng ra nên gộp lại?

Đừng phản xạ “hợp nhất mọi service”. Hãy định vị coupling và dùng kết quả thử nghiệm để điều chỉnh boundary.

### 21.2. Phân tích của tổ chức B

Các câu hỏi:
- Monolith có deployment bottleneck khi đội ngũ/tải tăng không?
- Module boundaries có được enforce không?
- Có transaction hotspot hoặc shared DB contention?
- Feature flag và migration cho phép release độc lập theo module không?
- Đã có runbook và khả năng tách module khi cần?
- Có domain nào yêu cầu scale/failure isolation độc lập rõ rệt?

B cũng phải đánh giá liên tục; thành công hôm nay không đảm bảo kiến trúc phù hợp khi traffic và tổ chức thay đổi.

## 22. Ví dụ quyết định tách một dịch vụ

Một Checkout module hiện nằm trong monolith. Đề xuất tách Payment Adapter thành service riêng vì provider latency không ổn định và cần isolate retries/secret access.

**Nếu chỉ viết:** “Tách một service để tăng microservice count”, quyết định chưa có lý do.

**Một hypothesis có thể kiểm chứng:**

~~~text
Problem:
  Payment provider intermittently slow, consuming checkout workers.
Current impact:
  Checkout p99 above target during provider degradation.
Expected capability:
  Dedicated concurrency budget and failure isolation for payment integration.
Expected outcome:
  Browse/cart remains available when payment provider slows.
  Checkout surfaces pending/unavailable honestly; no duplicate charges.
Guardrails:
  Idempotency, audit, least privilege, data minimization.
Costs:
  New service deployment, network hop, on-call, tracing, events.
Decision checkpoint:
  Compare SLI, blast radius, recovery, toil and unit cost after rollout.
~~~

Nếu tách service mà p99, blast radius hoặc correctness không cải thiện, cần xem lại implementation, placement và ranh giới. Đây là hành vi của tổ chức trưởng thành: **đánh giá quyết định theo kết quả đo được, không bảo vệ lựa chọn vì đã đầu tư công sức**.

## 23. Một kế hoạch baseline → experiment → review

Đánh giá trưởng thành không nhất thiết bắt đầu bằng chương trình “microservices transformation” kéo dài nhiều năm. Có thể lặp theo chu kỳ:

### Giai đoạn A — Xác định 3–5 outcome quan trọng

Chọn theo tổn thất và cơ hội:
- Checkout reliability.
- Independent release.
- Time to restore incident.
- Sensitive data handling.
- Cost per completed order.
- Platform self-service onboarding.

Không chọn 50 chỉ số khi chưa có người sở hữu và hành động. Một dashboard lớn không giúp nếu không ai xem hoặc không có quyền ra quyết định.

### Giai đoạn B — Đo baseline đáng tin

Một window đủ dài để thấy chu kỳ tải, release, incident và seasonality. Có thể bắt đầu 4–8 tuần tùy traffic, nhưng cần nêu rõ lý do và độ tin cậy. Ghi release, traffic mix, chiến dịch và thay đổi cách đo.

### Giai đoạn C — Tìm điểm nghẽn hệ thống

Ví dụ:
- 60% lead time là chờ team khác update shared DTO.
- 40% incident do deploy và rollback mất nhiều bước.
- Cache stampede gây DB timeout khi peak.
- 30% support ticket là do trạng thái đơn stale.
- Onboarding một service mất 7 ngày vì IAM thủ công.
- Chi phí observability tăng nhưng trace bị thiếu.

### Giai đoạn D — Chọn một can thiệp

Chỉ chọn một số thay đổi có liên hệ nhân quả hợp lý:
- Hợp đồng API và consumer tests.
- Canary/rollback automation.
- Idempotency và saga reconciliation.
- Redis cache loader concurrency.
- Golden path self-service.
- Phân loại dữ liệu và log redaction.

### Giai đoạn E — Đo outcome sau thay đổi

So sánh cùng loại workload và thời gian tương ứng:
- Latency/error/complete outcome.
- Lead time/release coupling.
- Operational toil.
- Cost có chuẩn hóa theo lượng giao dịch.
- Side effects không mong muốn, ví dụ tăng stale dữ liệu.

Không lấy một tuần traffic thấp làm bằng chứng capacity đã cải thiện.

### Giai đoạn F — Tiếp tục, sửa hoặc dừng

Nếu kết quả tốt và bền, nhân rộng. Nếu không, xem assumptions, rollback hoặc thử giải pháp khác. Không cần tạo một service mới chỉ để chứng minh quý này có nhiều thành phần hơn.

## 24. Ví dụ lộ trình cải thiện trong một quý

**Tình trạng ban đầu giả định:**
- Checkout p99 không ổn định.
- Mất 10 ngày để release một thay đổi cross-domain.
- Sự cố thường thiếu trace context.
- Có 40 service nhưng nhiều service không có owner/runbook rõ.
- Một phần data warehouse nhận PII không cần thiết.

### Tuần 1–2: Làm rõ outcome và owner

- Thống nhất customer journey SLO.
- Gắn owner cho những service và contract quan trọng.
- Xác định cách đo lead time và failure.
- Inventory dữ liệu nhạy cảm trong events/analytics.
- Đặt baseline customer-impact và operational toil.

### Tuần 3–6: Sửa các nút thắt có tác động lớn

- Thêm end-to-end tracing/correlation.
- Consumer contract tests cho hai đường tích hợp rủi ro.
- Canary + rollback cho một service điển hình.
- Hạn chế retry và overload ở dependency chung.
- Bỏ field PII không cần thiết khỏi event mới với migration có kiểm soát.

### Tuần 7–10: Kiểm chứng khả năng vận hành

- Test dependency failure và rollback.
- Xác minh saga idempotency/reconciliation.
- Thử self-service onboarding một service.
- Audit runbook và owner accessibility.
- Đánh giá deletion/retention propagation của dữ liệu đã đồng bộ.

### Tuần 11–12: Đánh giá kết quả

- So sánh SLO và incident-impact.
- So sánh lead time và cross-team blockers.
- So sánh recovery, rollback success.
- Đối chiếu security/data contract findings.
- Tính chi phí trên đơn thành công.
- Ghi những improvement được xác nhận và vấn đề chưa giải.

Các hoạt động trên là ví dụ; tổ chức có thể điều chỉnh theo năng lực và rủi ro. **Kết quả mục tiêu không phải “tăng 10 service trong quý” mà là năng lực giao sản phẩm an toàn đã tốt hơn và được chứng minh.**

## 25. Quy trình review kiến trúc theo bằng chứng

Một buổi kiến trúc review có thể đổi từ trình bày số lượng service sang bốn câu hỏi:

**1. Outcome nào đang không đạt?** Ví dụ checkout completion, change lead time, incident recovery.

**2. Nguyên nhân kỹ thuật/tổ chức nào được evidence ủng hộ?** Ví dụ shared DB lock, synchronized release, thiếu tracing, manual approval.

**3. Những phương án nào giải quyết vấn đề, với trade-off gì?** Ví dụ giữ modular monolith, tách một service, caching, queue, thay contract hoặc cải tiến deployment.

**4. Sau khi làm, đo gì để xác định thành công hoặc nên rollback?** SLI, unit cost, failure rate, coupling và correctness.

### 25.1. ADR theo outcome

~~~text
Title: Introduce per-domain contract testing
Status: Proposed

Observed problem:
  Recent releases broke downstream consumers.
Evidence:
  7 compatibility incidents in 90 days;
  40% cross-team changes require emergency coordination.

Decision:
  Adopt provider/consumer contract tests and compatibility rules.

Expected capabilities:
  Detect breaking schema and behavior before deployment.
  Allow consumer migration without lockstep releases.

Expected outcomes:
  Fewer compatibility incidents.
  Lower cross-team release wait.
  Safe rollback of one service.

Costs and risks:
  Test maintenance, version ownership, migration period.

Review date:
  After two release cycles and 90-day trend.
~~~

ADR không chỉ ghi “chúng tôi chọn Kafka” hoặc “chúng tôi chọn Kubernetes”. Nó nên giải thích **vấn đề, kỳ vọng kết quả và điều kiện xem lại**.

### 25.2. Không ép team phải chứng minh hoàn hảo mới được thay đổi

Các quyết định kỹ thuật luôn có uncertainty. Với thay đổi có thể đảo ngược và blast radius thấp, làm thử có giám sát có thể tốt hơn chờ nghiên cứu hàng tháng. Với data migration không thể rollback hoặc thay đổi authorization, cần review và kiểm chứng chặt hơn.

Độ trưởng thành là **ra quyết định tương xứng rủi ro**, không phải tạo nhiều tài liệu nhất.

## 26. Anti-pattern khi đo độ trưởng thành

**“Chúng ta có X microservice nên trưởng thành hơn.”** Service count là topology inventory, không phải SLO, autonomy hay business value.

**“Mọi module phải tách thành service.”** Tăng network, vận hành và coupling trong khi domain chưa cần.

**“Càng nhiều công cụ càng tốt.”** Công cụ không tự giải quyết toil nếu không được tích hợp, sở hữu và sử dụng đúng.

**“Đạt 100% Kubernetes adoption là thành công.”** Nếu lead time tăng và rollback khó hơn, outcome có thể giảm.

**“Mỗi team phải deploy thật nhiều để điểm cao.”** Dễ khuyến khích chia deployment vô ích và bỏ qua failure rate.

**“Không có incident tức hệ thống ổn định.”** Có thể thiếu detection hoặc dữ liệu bị sai âm thầm.

**“Uptime của từng service là đủ.”** Người dùng có thể bị kẹt ở saga, projection hoặc third-party dependency dù service HTTP trả 200.

**“Chỉ đo p50 latency.”** Tail latency và deadline ở critical journey có thể tệ, nhất là khi fan-out.

**“Chỉ đếm số test.”** Test không kiểm behavior, contract và failure mode có thể tạo false confidence.

**“Đếm số alert là observability.”** Nhiều alert không hành động được làm on-call bị quá tải.

**“Đếm security policies là security maturity.”** Không có enforcement, audit và remediations thì policy chỉ là output.

**“Giảm cloud bill là thành công.”** Có thể giảm vì lượng đơn thành công giảm, hoặc cắt hết capacity dự phòng.

**“Một điểm maturity tổng đại diện tất cả.”** Một lỗ hổng tenant isolation không được bù bằng tốc độ deployment tốt.

**“So sánh team bằng số liệu thô.”** Workload, criticality và legacy burden khác nhau; ranking thô gây phản tác dụng.

**“Sau khi tách service không được gộp lại.”** Kiến trúc phải được đánh giá theo kết quả; consolidation đôi khi là cải tiến.

**“Platform chỉ phục vụ khi team tạo ticket.”** Self-service thấp dù số automation script nhiều.

**“Mọi thay đổi bắt buộc architecture board duyệt.”** Gate thủ công có thể làm hỏng outcome thay đổi an toàn nhanh.

**“Team tự chủ thì không phải theo chuẩn chung.”** Phá auth, API/event contract và telemetry khiến những team khác chịu rủi ro.

## 27. Bài tập thực hành: đánh giá hai lựa chọn kiến trúc

Hệ thống Commerce đang có 18 service. Nhóm A đề xuất tách thêm 12 service vì muốn đạt mục tiêu “30 microservice trước cuối năm”. Nhóm B đề xuất giữ số service hiện có, nhưng cải thiện consumer contract tests, triển khai canary và chia capacity budget cho Checkout/Payment.

Các số giả định 60 ngày gần nhất:

~~~text
Checkout completion within 30s:      97,0%
Checkout target:                     99,5%
Median change lead time:            8 ngày
Cross-service release coordination: 55% changes
Change failure rate:                16%
Recovery after failed deployment:   90 phút median
Service owner/runbook coverage:     70%
Cost per successful order:          0,36 cost units
Number of services:                 18
~~~

Nhóm A dự kiến có 30 service nhưng chưa nêu ảnh hưởng tới SLO, release coupling hoặc recovery. Nhóm B nêu mục tiêu sau hai quý:

~~~text
Checkout completion:                >= 99,5%
Median change lead time:           <= 4 ngày
Cross-service coordination:        giảm có kiểm chứng
Change failure rate:               giảm trong window tương đương
Recovery after failed deployment:  <= 30 phút median
Owner/runbook coverage:            >= 95%
Cost per successful order:         không tăng quá budget
~~~

Đây là mục tiêu minh họa, không phải ngưỡng chuẩn bắt buộc.

### 27.1. Câu hỏi

1. Tại sao “30 service” không tự chứng minh maturity tăng?
2. Outcome nào có liên quan trực tiếp tới trải nghiệm người dùng?
3. Nếu có 12 service mới, những chi phí vận hành/contract nào phát sinh?
4. Vì sao tỷ lệ thay đổi cần đồng bộ 55% gợi ý coupling?
5. Consumer contract tests có thể giảm rủi ro nào?
6. Canary và rollback giải quyết khâu nào của incident recovery?
7. Nếu throughput tăng nhưng duplicate payment tăng, đánh giá có thể coi thành công không?
8. Những metric nào phải chuẩn hóa theo workload trước khi so sánh?
9. Khi nào tách một service cụ thể vẫn có thể là lựa chọn đúng?
10. Đội ngũ cần dữ liệu gì trước khi quyết định?

### 27.2. Định hướng giải

- Đặt tiêu chí theo journey SLO, flow và correctness.
- Inventory dependencies, current bottlenecks và owner.
- Dùng consumer tests/migration để giảm breaking changes.
- Dùng canary, rollback, tracing để phát hiện/giảm tác động deployment lỗi.
- Chỉ tách service nơi có bounded context, nhu cầu scale hoặc failure isolation được chứng minh.
- Đo cost/transaction và total on-call toil, không chỉ số pod.
- Review kết quả sau nhiều release và theo window/traffic tương đương.

Một phương án có thể phối hợp cả A và B: vẫn tách một vài service có lý do, đồng thời xây năng lực phát hành an toàn. Số lượng service cuối cùng là **hệ quả** của các quyết định đúng, không phải mục tiêu chính.

## 28. Checklist khi báo cáo độ trưởng thành lên lãnh đạo

1. **Bắt đầu bằng customer/business outcomes**, không mở đầu bằng số repository, service hoặc tool.
2. **Có baseline và mục tiêu đo được** cho journey quan trọng.
3. **Công bố cách tính** cho SLI/SLO, lead time, failure, recovery và cost.
4. **Đưa chất lượng dữ liệu đo vào báo cáo**, không ẩn missing data hoặc thay đổi methodology.
5. **Nêu cả kết quả tốt và rủi ro chưa giải**, đặc biệt security/data correctness.
6. **Phân biệt capability với output** như pipeline được tạo so với rollback thực sự chạy được.
7. **Đánh giá ranh giới kiến trúc qua coupling**, không qua tổng số service.
8. **Đo interoperability/contract compatibility** và sự cố do thay đổi liên nhóm.
9. **Đo reliability đầu-cuối** và khả năng degrade/recover khi dependency lỗi.
10. **Đưa data governance và security vào tiêu chí cứng**, không bù bằng tốc độ release.
11. **Theo dõi developer self-service**, time-to-first-deploy và operational toil.
12. **Đo chi phí trên đơn vị công việc hữu ích** và headroom cần thiết.
13. **Nêu chính sách so sánh** theo risk tier, workload và quy mô.
14. **Không dùng một metric làm thưởng phạt cứng**, tránh gaming và giấu lỗi.
15. **Trình bày giả thuyết về nhân quả**, không tự khẳng định cải thiện kinh doanh do một thay đổi kiến trúc.
16. **Ghi rõ owner và hành động tiếp theo** cho outcome chưa đạt.
17. **Có thời hạn xem lại quyết định kiến trúc**, không bất biến hóa microservices.
18. **Dùng một số case thực**: incident, rollback, feature release, cost anomaly.
19. **Khuyến khích hợp nhất/tách service khi có bằng chứng**, không theo thời trang.
20. **Cho thấy quá trình học tập:** vấn đề được phát hiện, thử nghiệm, kết quả và cải tiến.

## 29. Mẫu báo cáo một trang

~~~text
Architecture Maturity Review — Period: [window]

Business-critical journeys:
  Checkout:
    SLO / actual / trend / impact
  Browse:
    SLO / actual / trend / impact

Safe delivery:
  Change lead time:
  Deployment failures:
  Failed deployment recovery:
  Cross-team release coupling:

Operational resilience:
  Customer-impact incidents:
  Median recovery / worst incidents:
  Tested failover and restore:

Data and security:
  Critical findings open/overdue:
  Contract violations:
  Sensitive-data lineage/deletion coverage:

Platform and team effectiveness:
  Self-service completion time:
  Developer toil:
  Ownership/runbook coverage:

Economic efficiency:
  Cost per completed business operation:
  Capacity headroom and major waste:

Top 3 confirmed bottlenecks:
  1.
  2.
  3.

Next experiments:
  Change / expected outcome / owner / deadline / guardrail

Context:
  Workload mix, incident changes, releases, measurement caveats

Architectural inventory (appendix, not score):
  Service count / repos / clusters / topics
~~~

Service count có thể vẫn cần cho capacity planning, ownership inventory, security patching và chi phí vận hành. Nó chỉ không nên được thăng thành **điểm số trưởng thành**.

## 30. Kết luận cần ghi nhớ

- **Độ trưởng thành thể hiện ở kết quả ổn định và có thể lặp lại**, không ở số microservice, pod, repo, dashboard hoặc framework.
- **Kiến trúc là một lựa chọn để đạt năng lực**, như thay đổi độc lập, phục hồi nhanh, cô lập lỗi, bảo vệ dữ liệu và mở rộng có kiểm soát.
- **Đo cả người dùng lẫn kỹ thuật:** business journey SLO, dữ liệu đúng, safe delivery, incident impact, team autonomy, platform self-service và unit cost.
- **Chỉ số phải có định nghĩa, mẫu số, cửa sổ, owner và hành động**; tránh tối ưu một con số khiến người dùng chịu thiệt.
- **Microservice không tự bảo đảm autonomy** nếu các nhóm còn dùng shared DB, shared model và phải release đồng thời.
- **Một modular monolith có thể rất trưởng thành**, và một distributed monolith có thể rất non trẻ dù có hàng trăm service.
- **Các ràng buộc bảo mật, dữ liệu và correctness là điều kiện an toàn**, không được bù bằng tần suất deployment hay chi phí thấp.
- **Platform tốt giúp các nhóm tự phục vụ trong guardrails**, không tạo thêm approval gate vô ích.
- **Đánh giá phải dẫn đến quyết định:** đo baseline, tìm bottleneck, thay đổi có giả thuyết, kiểm chứng outcome, giữ hoặc điều chỉnh.
- **Số service nên là hệ quả của ranh giới và nhu cầu thực**, không phải mục tiêu để báo cáo thành tích.
