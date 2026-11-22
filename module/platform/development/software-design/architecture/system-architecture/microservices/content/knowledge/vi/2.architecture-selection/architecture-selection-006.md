# Đo mức độ sẵn sàng của tổ chức và nền tảng kỹ thuật khi lựa chọn Microservices

> **Bối cảnh:** Chủ đề thuộc nhóm **Lựa chọn kiến trúc** trong **Software Design Architecture → System Architecture → Microservices**. Mục tiêu là đánh giá một cách có chứng cứ xem tổ chức, đội ngũ và nền tảng vận hành đã đủ khả năng tiếp nhận độ phức tạp phân tán của Microservices hay chưa; từ đó quyết định triển khai, thử nghiệm có giới hạn, đầu tư năng lực nền tảng, hoặc tiếp tục với Modular Monolith.

## 1. Vì sao phải đo mức độ sẵn sàng?

Microservices chia một hệ thống thành các dịch vụ có ranh giới nghiệp vụ và vòng đời triển khai tương đối độc lập. Lợi ích tiềm năng gồm: nhiều nhóm phát triển song song, mở rộng từng phần, triển khai từng dịch vụ và cô lập một phần lỗi. Đổi lại, ứng dụng phải xử lý giao tiếp qua mạng, lỗi từng phần, nhất quán dữ liệu liên dịch vụ, kiểm soát phiên bản API, giám sát nhiều thành phần và chi phí vận hành cao hơn.

Một kiến trúc có thể đúng về mặt thiết kế nhưng thất bại khi tổ chức chưa có người chịu trách nhiệm vận hành, không tự động hóa triển khai hoặc chưa biết điều tra giao dịch đi qua nhiều dịch vụ. Vì vậy câu hỏi cần trả lời không phải là “Chúng ta có dùng được Docker/Kubernetes không?”, mà là:

- **Nhu cầu:** Vấn đề kinh doanh và quy mô thay đổi có thực sự cần triển khai, sở hữu, mở rộng độc lập?
- **Tổ chức:** Có các nhóm đủ quyền quyết định và chịu trách nhiệm xuyên suốt vòng đời dịch vụ?
- **Kỹ thuật:** Có thể phát hành, giám sát, bảo mật, khôi phục và quản lý dữ liệu trên nhiều dịch vụ một cách lặp lại?
- **Kinh tế:** Giá trị thu được có lớn hơn chi phí hạ tầng, nền tảng, nhân sự, điều phối và sự cố?
- **Khả năng tiến hóa:** Có thể chuyển đổi theo từng bước và dừng lại khi bằng chứng cho thấy lợi ích chưa đạt?

**Đầu ra của đánh giá** phải là quyết định kiến trúc kèm điều kiện và kế hoạch hành động: tiếp tục Modular Monolith; thực hiện một pilot có giới hạn; hoặc áp dụng Microservices theo từng miền nghiệp vụ. Điểm số chỉ là một phần bằng chứng, không thay thế phán đoán kiến trúc.

## 2. Định nghĩa phạm vi trước khi chấm

Không nên hỏi chung “công ty đã sẵn sàng cho Microservices chưa” nếu từng sản phẩm, nhóm và môi trường có năng lực khác nhau. Viết rõ phạm vi đánh giá:

| Thuộc tính | Cần xác định | Ví dụ |
|---|---|---|
| Sản phẩm | Hệ thống/luồng nghiệp vụ được xét | Nền tảng bán hàng trực tuyến |
| Mục tiêu | Vấn đề cần giải quyết và kết quả mong muốn | Giảm phụ thuộc giữa nhóm Checkout và Catalog |
| Ranh giới | Những miền nghiệp vụ có thể tách | Catalog, Checkout, Fulfillment |
| Hiện trạng | Kiến trúc, lưu lượng, tần suất thay đổi, sự cố | Monolith có các module, triển khai chung |
| Phạm vi vận hành | Production, staging, khu vực, dữ liệu nhạy cảm | Production ở hai vùng |
| Chân trời | Khi nào phải ra quyết định/đo lại | Đánh giá hiện tại và sau 90 ngày |
| Người quyết định | Chủ sở hữu sản phẩm, kỹ thuật và rủi ro | Product lead, tech lead, SRE, security, data owner |

Phân biệt **nhu cầu phân tán** với **sở thích công nghệ**. Ví dụ, ứng dụng có lượng truy cập vừa phải nhưng ba nhóm thường xuyên chờ nhau khi phát hành có thể có nhu cầu tách ranh giới triển khai; ngược lại, tải cao không tự động dẫn đến Microservices vì một Monolith được tối ưu và nhân bản cũng có thể đáp ứng.

## 3. Thu thập chứng cứ: đo hoạt động thực tế

Chấm dựa trên bằng chứng trong khoảng thời gian đủ đại diện, chẳng hạn 4–12 tuần gần nhất, và ghi rõ giai đoạn quan sát. Kết hợp dữ liệu định lượng với phỏng vấn và diễn tập. Dữ liệu lấy từ pipeline triển khai, hệ thống giám sát, incident, kho mã, hồ sơ thay đổi, sơ đồ phụ thuộc và quyền sở hữu hệ thống.

**Bốn nhóm chứng cứ nên có:**

1. **Dòng chảy phát triển:** từ merge đến production mất bao lâu, bao nhiêu bước thủ công, tỷ lệ phát hành thất bại và thời gian phục hồi; lấy số liệu theo dịch vụ hoặc sản phẩm, tránh trung bình che giấu nhóm yếu.
2. **Vận hành và độ tin cậy:** SLI/SLO, cảnh báo có thể hành động, thời gian phát hiện và xử lý sự cố, runbook, nhật ký trực, khả năng truy vết yêu cầu qua nhiều thành phần.
3. **Cấu trúc tổ chức:** sơ đồ nhóm, quyền quyết định, ai sở hữu code–runtime–dữ liệu, đường đi khi cần thay đổi schema/API, cách xử lý phụ thuộc giữa nhóm.
4. **Năng lực nền tảng:** hạ tầng dưới dạng mã, pipeline mẫu, quản lý secrets, phân quyền, registry, khôi phục thảm họa, quản lý chi phí, quy ước API và môi trường thử nghiệm.

**Không nhầm việc “có công cụ” với “dùng công cụ thành thạo”.** Một cụm Kubernetes không chứng minh tổ chức có thể vận hành Microservices nếu cấu hình thủ công, không có giới hạn tài nguyên, không tập trung log và không ai phụ trách sự cố. Tương tự, có sơ đồ “mỗi nhóm một service” không chứng minh nhóm đó có quyền triển khai độc lập.

Đối với mỗi nhận định, lưu: mô tả, nguồn chứng cứ, giai đoạn, nhóm phụ trách, mức tin cậy và hạn chế. Khi dữ liệu thiếu, ghi rõ **chưa đo được**, không tự chấm tối đa.

## 4. Thang trưởng thành 0–4

Dùng một thang nhất quán cho từng chiều đánh giá. Đây là **rubric đề xuất cho quyết định nội bộ**, không phải tiêu chuẩn bắt buộc của mọi doanh nghiệp.

| Mức | Mô tả | Bằng chứng điển hình |
|---|---|---|
| **0 — Chưa có** | Không có năng lực hoặc không xác định được chủ sở hữu | Không có pipeline, không có người trực, không có quy trình |
| **1 — Thủ công/riêng lẻ** | Một số cá nhân làm được nhưng phụ thuộc kiến thức cá nhân | Release làm tay, một người biết rollback |
| **2 — Lặp lại được** | Có quy trình được thực hành thường xuyên, nhưng còn nhiều bước thủ công | Pipeline cơ bản, checklist triển khai, dashboard một phần |
| **3 — Chuẩn hóa/tự động** | Phần lớn nhóm dùng chung một cơ chế, có đo lường và kiểm soát | CI/CD có quality gates, tracing, ownership, rollback đã diễn tập |
| **4 — Tự phục vụ/cải tiến** | Đội sản phẩm tự chủ trong rào chắn phù hợp và cải tiến dựa trên dữ liệu | Golden path, SLO, tự động hóa phục hồi, xem xét chi phí và rủi ro định kỳ |

Một chiều chỉ được mức 3 khi **đa số luồng công việc trong phạm vi đánh giá** thực sự đạt mức đó. Một lần demo thành công chưa đủ để chấm thành năng lực ổn định. Nếu các nhóm lệch nhau nhiều, ghi cả mức điển hình và mức yếu nhất ở các luồng trọng yếu.

## 5. Mười chiều cần đánh giá

Đề xuất phân bổ 50% cho tổ chức/kinh tế và 50% cho nền tảng kỹ thuật. Trọng số có thể thay đổi khi có lý do và phải được xác định **trước** khi biết kết quả.

| Mã | Chiều đánh giá | Trọng số | Câu hỏi trọng tâm |
|---|---|---:|---|
| O1 | Ranh giới nghiệp vụ và mục tiêu sản phẩm | 12 | Có biết vì sao và tách ở đâu? |
| O2 | Đội tự chủ và sở hữu dịch vụ | 10 | Một nhóm có chịu trách nhiệm trọn vòng đời? |
| O3 | Năng lực phát triển và vận hành | 10 | Có đủ kỹ năng, thời gian trực và phối hợp? |
| O4 | Quản trị kiến trúc và quyết định | 8 | Các nhóm có giao ước rõ mà vẫn tự chủ? |
| O5 | Kinh tế và năng lực đầu tư | 10 | Có ngân sách, chi phí cơ hội và thước đo giá trị? |
| T1 | CI/CD và phát hành độc lập | 12 | Có thể build–test–deploy–rollback an toàn? |
| T2 | Hạ tầng, runtime và nền tảng | 10 | Có môi trường nhất quán và tự phục vụ? |
| T3 | Observability và độ tin cậy | 10 | Có thể thấy, khoanh vùng và xử lý lỗi phân tán? |
| T4 | Dữ liệu, tích hợp và hợp đồng | 10 | Có ranh giới dữ liệu, API và nhất quán rõ? |
| T5 | Bảo mật và kiểm soát truy cập | 8 | Có thể kiểm soát danh tính, secrets và audit? |
| | **Tổng** | **100** | **Tổ chức 50, kỹ thuật 50** |

### O1. Ranh giới nghiệp vụ và mục tiêu sản phẩm (12%)

**Cần kiểm tra:** các luồng kinh doanh quan trọng, bounded context, mức coupling giữa module, nhịp thay đổi, điểm nghẽn chung khi phát hành. Có thể phân tích domain bằng Event Storming, sơ đồ năng lực nghiệp vụ, bản đồ luồng dữ liệu và lịch sử thay đổi cùng nhau.

**Bằng chứng:** danh sách capability và owner, sơ đồ phụ thuộc, số lần một thay đổi nhỏ phải sửa nhiều module/nhóm, nhu cầu scale khác nhau, mục tiêu đo được như lead time hoặc độ ổn định của một miền.

**Dấu hiệu chưa sẵn sàng:** ranh giới được chọn theo bảng database hoặc tầng kỹ thuật; nhóm chưa thống nhất ngôn ngữ nghiệp vụ; phải gọi đồng bộ nhiều service chỉ để hoàn thành tác vụ cơ bản. Khi đó nên làm rõ module và hợp đồng bên trong Monolith trước.

### O2. Đội tự chủ và sở hữu dịch vụ (10%)

**Cần kiểm tra:** một dịch vụ có nhóm chủ sở hữu rõ ràng từ roadmap đến production, bao gồm kiểm thử, triển khai, cảnh báo và quyết định khắc phục? Có quy tắc khi owner vắng mặt? Nhóm có quyền triển khai trong guardrail đã thỏa thuận?

**Bằng chứng:** service catalog, bảng owner/backup owner, trách nhiệm on-call, lịch sử deploy tự chủ, mức phụ thuộc phê duyệt từ nhóm trung tâm, bản đồ phụ thuộc thay đổi giữa nhóm.

**Dấu hiệu chưa sẵn sàng:** mỗi service đều phải đợi một đội vận hành làm hộ hoặc nhiều nhóm cùng thay đổi dữ liệu của nhau. Cắt code thành nhiều repository không giải quyết được ownership.

### O3. Năng lực phát triển và vận hành (10%)

**Cần kiểm tra:** năng lực về hệ thống phân tán, networking, timeout/retry, idempotency, eventual consistency, event processing, bảo mật, quan sát vận hành và xử lý sự cố. Đo mức phụ thuộc vào cá nhân hoặc nhà cung cấp.

**Bằng chứng:** diễn tập incident, kết quả game day, hướng dẫn vận hành được sử dụng, pair review các ca lỗi phân tán, khả năng tự hoàn thành một release chuẩn của nhóm sản phẩm.

**Dấu hiệu chưa sẵn sàng:** không có năng lực trực production; chưa ai từng xử lý retry gây ghi trùng; nhân lực hiện tại chỉ đủ phát triển tính năng và sửa sự cố của Monolith. Cần dành capacity thực cho đào tạo và hỗ trợ nền tảng.

### O4. Quản trị kiến trúc và quyết định (8%)

**Cần kiểm tra:** nguyên tắc ranh giới, phiên bản API/event, tiêu chuẩn tối thiểu về bảo mật, telemetry, ownership, deprecation, ADR và kiểm tra phụ thuộc. Có cơ chế quyết định tranh chấp ranh giới dữ liệu mà không tạo nút cổ chai phê duyệt?

**Bằng chứng:** ADR thực tế, compatibility policy, catalog phiên bản API, review sự kiện thay đổi hợp đồng, kiến trúc tham chiếu và golden path có người duy trì.

**Dấu hiệu chưa sẵn sàng:** mọi nhóm tự chọn giao thức/log/auth không tương thích, hoặc ngược lại mọi quyết định nhỏ đều chờ hội đồng kiến trúc. Quản trị cần giới hạn các rủi ro chung, giữ quyền tự chủ ở chi tiết nội bộ.

### O5. Kinh tế và năng lực đầu tư (10%)

**Cần kiểm tra:** tổng chi phí sở hữu gồm hạ tầng, môi trường, log/trace/metric, nền tảng, bảo mật, đường truyền, backup, công sức vận hành và chi phí chuyển đổi. Cần xác định lợi ích kỳ vọng và thời điểm đo lại, gồm cả chi phí cơ hội của việc ngừng phát triển sản phẩm để tách hệ thống.

**Bằng chứng:** baseline chi phí hiện tại, dự báo cloud và telemetry, capacity của platform team, ngân sách đào tạo, mục tiêu thay đổi có giá trị kinh doanh và phương án rollback kiến trúc.

**Dấu hiệu chưa sẵn sàng:** lý do duy nhất là “giống công ty lớn”; chưa biết chi phí môi trường/service; tách hàng chục dịch vụ nhưng không có nguồn lực duy trì. **Microservices không tự động rẻ hơn, nhanh hơn hoặc đáng tin cậy hơn.**

### T1. CI/CD và phát hành độc lập (12%)

**Cần kiểm tra:** build, unit/integration/contract test, kiểm tra security, artifact bất biến, pipeline production, triển khai không gián đoạn, feature flag, rollback/roll-forward và tương thích schema. Việc phát hành một dịch vụ có bắt buộc tái triển khai toàn bộ không?

**Bằng chứng:** chạy thử release từ commit đến production, lịch sử pipeline, tỷ lệ bước thủ công, change failure rate, thời gian phục hồi, nhật ký rollback và quy tắc phê duyệt thay đổi theo mức rủi ro.

**Dấu hiệu chưa sẵn sàng:** release phụ thuộc thao tác SSH, cấu hình môi trường khác nhau, không kiểm tra hợp đồng và không có cách phục hồi dữ liệu khi đổi schema. Tăng số dịch vụ khi đó làm tăng xác suất và chi phí lỗi phát hành.

### T2. Hạ tầng, runtime và nền tảng (10%)

**Cần kiểm tra:** môi trường được khai báo bằng mã, cấu hình và secrets tách khỏi artifact, provisioning lặp lại, discovery/DNS, ingress, TLS, quota, autoscaling khi cần, registry, policy tài nguyên và vòng đời môi trường. Kubernetes là một lựa chọn, không phải điều kiện bắt buộc.

**Bằng chứng:** thử tạo môi trường mới từ mã, service template/golden path, dashboard capacity, tài liệu vận hành nền tảng, thời gian tự phục vụ của developer và drift giữa các môi trường.

**Dấu hiệu chưa sẵn sàng:** mỗi service cần cấu hình thủ công rất khác nhau, không có giới hạn tài nguyên, thiếu quản lý hạ tầng hoặc platform team trở thành điểm nghẽn của mọi release.

### T3. Observability và độ tin cậy (10%)

**Cần kiểm tra:** metrics ở mức dịch vụ và trải nghiệm người dùng, log có cấu trúc, correlation/trace ID xuyên biên giới, distributed tracing, alert theo tác động người dùng, SLI/SLO, dashboard, runbook, timeout, circuit breaker, bulkhead, retry có backoff/jitter và quy trình incident.

**Bằng chứng:** chọn một giao dịch lỗi và lần theo được qua các service; xem dashboard đo latency/error rate; kiểm chứng cảnh báo; thử tình huống một dependency chậm hoặc unavailable; review postmortem có hành động cải tiến.

**Dấu hiệu chưa sẵn sàng:** chỉ thấy HTTP 500 ở gateway mà không biết lỗi nằm ở đâu; retry không giới hạn gây khuếch đại tải; mọi cảnh báo đều gửi cho một người; không có cách xác minh hậu quả đối với nghiệp vụ.

### T4. Dữ liệu, tích hợp và hợp đồng (10%)

**Cần kiểm tra:** quyền sở hữu dữ liệu theo miền, tránh truy cập trực tiếp bảng của service khác, cách giao tiếp sync/async, phiên bản API/event, idempotency, xử lý dữ liệu trễ/trùng/sai thứ tự, outbox/inbox khi cần, saga hoặc quy trình bù trừ, khả năng đối soát và khôi phục.

**Bằng chứng:** sơ đồ dữ liệu và owner, danh sách transaction xuyên miền, contract test, tình huống mất kết nối, tài liệu consistency model, kế hoạch migration schema mở rộng–thu hẹp và test khôi phục dữ liệu.

**Dấu hiệu chưa sẵn sàng:** yêu cầu transaction ACID xuyên nhiều database nhưng không có phương án nghiệp vụ, shared database không giới hạn quyền ghi, consumer bị vỡ khi producer đổi payload. Đây thường là rủi ro lớn hơn việc chạy container.

### T5. Bảo mật và kiểm soát truy cập (8%)

**Cần kiểm tra:** xác thực giữa service, phân quyền mức quyền tối thiểu, TLS và bảo vệ dữ liệu trong truyền/lưu, quản lý secrets, xoay vòng khóa, phân tách môi trường, quét dependency/image, audit, phân loại dữ liệu và quy trình xử lý lỗ hổng.

**Bằng chứng:** đường đi của identity từ client qua gateway đến service, kiểm tra quyền từng workload, policy truy cập data store, lịch sử secret rotation, scan pipeline, kết quả thử xâm nhập/phân tích threat và diễn tập thu hồi quyền.

**Dấu hiệu chưa sẵn sàng:** shared static credential cho nhiều service, secrets trong source code, service nội bộ được tin cậy mặc định, không kiểm soát ai có thể truy cập dữ liệu nhạy cảm. Phân tán làm tăng số điểm cần bảo vệ.

## 6. Chỉ số đo: tránh đánh giá theo cảm nhận

Đề xuất tập dữ liệu quan sát đủ nhỏ để duy trì thường xuyên. Chọn chỉ số liên quan đến mục tiêu chuyển đổi và ghi baseline trước khi pilot.

| Nhóm | Chỉ số | Cách hiểu và giới hạn |
|---|---|---|
| Delivery | Tần suất triển khai production | Đo từng đội/miền; tăng số lần deploy chỉ có ý nghĩa khi ổn định |
| Delivery | Lead time của thay đổi | Từ thay đổi mã được ghi nhận đến chạy trong production; nêu rõ điểm đầu/cuối đo |
| Delivery | Tỷ lệ thay đổi gây lỗi | Định nghĩa lỗi cần rollback/hotfix/incident; thống nhất mẫu số |
| Recovery | Thời gian phục hồi sau triển khai lỗi | Đo thực tế bằng log incident; xem cả phân phối thay vì chỉ số trung bình |
| Reliability | Availability và latency theo SLI/SLO | Đo theo trải nghiệm người dùng, không chỉ trạng thái pod |
| Reliability | Sự cố liên dịch vụ | Số ca lỗi lan truyền, retry storm, timeout; phân loại theo ảnh hưởng |
| Operability | Tỷ lệ luồng có trace đầy đủ | Có thể liên kết gateway, service, queue và thao tác dữ liệu |
| Ownership | Phạm vi có owner/on-call/runbook | Đánh giá khả năng duy trì, không chỉ có tên trong danh sách |
| Independence | Thay đổi cần phối hợp đa nhóm | Tỷ lệ thay đổi phải chờ release/merge/schema của nhóm khác |
| Platform | Thời gian cấp môi trường hoặc dịch vụ mới | Từ yêu cầu đến môi trường được dùng và vận hành an toàn |
| Cost | Chi phí vận hành theo capability/traffic | Bao gồm hạ tầng, telemetry và công sức con người |
| Data | Lỗi hợp đồng/đối soát dữ liệu | Ghi lỗi do schema, event trùng/thất lạc và thời gian sửa sai |

Ví dụ, SLO khả dụng **99,9%** trong 30 ngày tương ứng error budget khoảng **43,2 phút** không đáp ứng mục tiêu (nếu đo theo thời gian và định nghĩa SLI phù hợp). Con số này minh họa cách tính, không phải SLO bắt buộc. Nếu sản phẩm hiện chưa theo dõi SLI tin cậy, hãy bổ sung đo lường trước khi kết luận rằng hệ thống đã “ổn định”.

Các chỉ số delivery thường được nhắc đến trong thực hành DevOps/DORA nên được dùng như **tín hiệu vận hành**, không trở thành mục tiêu để tối ưu bằng mọi giá. Một đội release rất thường xuyên nhưng rollback thủ công và gây incident liên tục chưa chứng minh sẵn sàng.

## 7. Tính điểm có trọng số và cổng bắt buộc

Với mỗi chiều có trọng số w và mức trưởng thành s từ 0 đến 4:

**Điểm đóng góp = w × s / 4.**

**Điểm tổng = tổng điểm đóng góp của 10 chiều, từ 0 đến 100.**

Tính thêm **điểm tổ chức (O1–O5, tối đa 50)** và **điểm kỹ thuật (T1–T5, tối đa 50)** để không cho một phía quá mạnh che đi phía còn lại. Kèm **độ tin cậy của bằng chứng** (cao/trung bình/thấp) và ghi rõ những mục chưa đo được.

Bảng diễn giải **tham khảo**, cần hiệu chỉnh theo mức rủi ro, quy mô và yêu cầu của sản phẩm:

| Điểm tổng | Định hướng sơ bộ | Điều kiện kèm theo |
|---:|---|---|
| 0–39 | Chưa thích hợp để nhân rộng Microservices | Ưu tiên modular hóa, CI/CD, ownership và đo lường |
| 40–69 | Có thể nghiên cứu/pilot nhỏ với giới hạn rõ | Chỉ thử trong phạm vi cô lập; khắc phục cổng còn thiếu |
| 70–84 | Có thể tách dần từng capability | Cả tổ chức và kỹ thuật đạt mức chấp nhận, cổng bắt buộc đạt |
| 85–100 | Có năng lực vận hành đáng kể | Vẫn phải chứng minh lợi ích kinh doanh và ranh giới đúng |

Không sử dụng điểm tổng như điều kiện duy nhất. Ví dụ đề xuất thêm điều kiện **mỗi phía đạt ít nhất 30/50** trước khi mở rộng và không có rủi ro trọng yếu chưa xử lý. Đây là ngưỡng quản trị có thể điều chỉnh theo quyết định thực tế.

### Cổng bắt buộc (hard gates)

Đánh dấu **Đạt / Chưa đạt / Chưa có bằng chứng** cho từng cổng. “Chưa có bằng chứng” không được coi là đạt:

- **G1 — Ownership:** mỗi dịch vụ production có owner, backup, người xử lý incident và quyền dừng triển khai.
- **G2 — Release an toàn:** có pipeline lặp lại, test tối thiểu theo rủi ro, khả năng rollback/roll-forward và quy trình tương thích schema.
- **G3 — Quan sát và sự cố:** có log, metrics, truy vết một giao dịch xuyên dịch vụ và runbook cho luồng quan trọng.
- **G4 — Bảo mật:** secrets không lưu trong mã, quyền tối thiểu, xác thực giữa thành phần và quy trình vá lỗ hổng.
- **G5 — Dữ liệu:** có owner cho mỗi nhóm dữ liệu, định nghĩa tính nhất quán, chiến lược chống xử lý trùng và cách đối soát/bù trừ.
- **G6 — Năng lực duy trì:** có thời gian, ngân sách, nhân lực và trách nhiệm rõ để vận hành sau khi pilot thành production.

Một cổng chưa đạt **không luôn cấm mọi thử nghiệm**. Có thể làm prototype trên dữ liệu giả/môi trường cô lập để học; tuy nhiên không nâng thành service production quan trọng hoặc mở rộng số lượng dịch vụ trước khi giải quyết rủi ro liên quan.

### Ví dụ chấm một sản phẩm

| Chiều | Trọng số | Mức 0–4 | Điểm đóng góp |
|---|---:|---:|---:|
| O1 | 12 | 2 | 6,0 |
| O2 | 10 | 3 | 7,5 |
| O3 | 10 | 2 | 5,0 |
| O4 | 8 | 2 | 4,0 |
| O5 | 10 | 1 | 2,5 |
| T1 | 12 | 3 | 9,0 |
| T2 | 10 | 2 | 5,0 |
| T3 | 10 | 2 | 5,0 |
| T4 | 10 | 1 | 2,5 |
| T5 | 8 | 2 | 4,0 |
| **Tổng** | **100** | | **50,5 / 100** |

Điểm tổ chức là **25,0/50**; điểm kỹ thuật là **25,5/50**. Nếu thêm G5 chưa đạt do hai miền đang ghi chung một bảng dữ liệu và không có cơ chế đối soát, kết luận phù hợp là **chưa mở rộng Microservices**. Đội có thể tiếp tục cải thiện tính độc lập bên trong Modular Monolith, bổ sung quản trị dữ liệu và thí điểm một capability có ranh giới rõ.

## 8. Phương pháp đánh giá từng bước

### Bước 1 — Chốt giả thuyết quyết định

Viết thành câu có thể kiểm chứng: “Tách capability X thành dịch vụ độc lập sẽ giảm thời gian chờ phát hành từ A xuống B, trong khi vẫn giữ SLO Y và chi phí tăng không vượt ngân sách Z.” Không có giả thuyết rõ thì chấm điểm dễ biến thành hoạt động hợp thức hóa quyết định đã chọn.

Chọn ít nhất một chỉ số giá trị (ví dụ thời gian đưa tính năng ra production), một chỉ số an toàn (ví dụ error rate/incident), một chỉ số chi phí và giới hạn thời gian đo.

### Bước 2 — Vẽ bản đồ ranh giới và phụ thuộc

Liệt kê capability, nhóm chủ quản, module hiện tại, bảng dữ liệu, API/event và dependency. Xác định nơi thay đổi thường đi cùng nhau. Nếu hai phần luôn cần transaction tức thời và cùng thay đổi schema, đó là tín hiệu **chưa có biên phân tách tốt**; có thể giữ chung module hoặc service.

Không chỉ vẽ hình hộp dịch vụ. Ghi chú loại phụ thuộc: gọi đồng bộ, tiêu thụ event, cùng DB, cùng release pipeline, cùng credential hay cùng người trực. Những phụ thuộc này quyết định mức tự chủ thực tế.

### Bước 3 — Phỏng vấn nhiều vai trò và đối chiếu dữ liệu

Trao đổi với product owner, developer, QA, SRE/operations, platform, data, security và finance. Yêu cầu mỗi bên đưa một ví dụ gần đây: release thành công, release lỗi, thay đổi schema, incident, thêm môi trường, cấp quyền truy cập. Đối chiếu lời kể với log/pipeline/ticket; nếu lệch nhau thì ghi điều chưa rõ.

Dùng bảng đánh giá 10 chiều, thu tối thiểu một bằng chứng xác nhận cho mỗi điểm từ mức 2 trở lên. Các phần chưa đo được phải tạo nhiệm vụ thiết lập baseline.

### Bước 4 — Thực hiện bài kiểm tra thực tế

Chọn một luồng quan trọng nhưng có rủi ro được kiểm soát. Chạy thử theo thứ tự:

1. Tạo môi trường từ mã hoặc template tiêu chuẩn.
2. Thay đổi nhỏ trên một component; build, test và deploy theo pipeline thường dùng.
3. Ghi lại thời gian, số lần cần người can thiệp và phụ thuộc tổ chức.
4. Cố ý tạo lỗi đã kiểm soát (timeout dependency, consumer nhận event trùng hoặc instance chết).
5. Phát hiện qua telemetry, lần theo trace/log, xử lý theo runbook và rollback/khôi phục.
6. Kiểm tra dữ liệu sau sự cố; xác nhận không có đơn hàng/thanh toán bị nhân đôi hoặc mất trạng thái.
7. Thu thập evidence và thời gian thực tế, đóng các lỗ hổng đã phát hiện.

Bài kiểm tra này có giá trị cao hơn việc chỉ phỏng vấn “đội có biết vận hành Microservices không?”. Mọi thử nghiệm gây lỗi cần thực hiện trong môi trường và phạm vi đã được kiểm soát.

### Bước 5 — Chấm điểm, xác định cổng và rủi ro

Hai hoặc nhiều vai trò độc lập chấm dựa trên cùng chứng cứ, sau đó giải quyết chênh lệch bằng dữ liệu cụ thể. Chốt tổng điểm, điểm tổ chức/kỹ thuật, trạng thái sáu cổng, rủi ro còn lại và mức tin cậy. Không làm tròn nhằm vượt ngưỡng.

Sắp xếp lỗ hổng theo **xác suất × tác động × phạm vi ảnh hưởng**, đồng thời xét chi phí khắc phục và phụ thuộc. Một lỗ hổng bảo mật hoặc tính nhất quán dữ liệu có thể ưu tiên cao hơn nhiều mục trưởng thành có điểm thấp nhưng ít ảnh hưởng.

### Bước 6 — Ra quyết định, gắn owner và đo lại

Ghi quyết định qua ADR hoặc hồ sơ quyết định có thể tìm lại được: bối cảnh, phương án, chứng cứ, tiêu chí, lợi ích, chi phí, rủi ro, điều kiện go/no-go và ngày đánh giá lại. Mỗi việc khắc phục có owner, thời hạn và tiêu chí hoàn thành có thể đo. Đo lại sau pilot hoặc khi có biến cố đáng kể (thay tổ chức, thay nền tảng, tăng tải, sự cố lớn).

## 9. Bảng quyết định: Microservices hay Modular Monolith?

Điểm sẵn sàng kỹ thuật chỉ trả lời “có thể vận hành được đến đâu”; vẫn cần hỏi “phân tách có cần thiết không”.

| Tình huống | Lựa chọn thường hợp lý | Lý do cần kiểm chứng |
|---|---|---|
| Một vài nhóm nhỏ, domain còn thay đổi liên tục | Modular Monolith với module boundaries rõ | Đơn giản hóa transaction, debug và deployment khi boundary chưa ổn |
| Nhiều đội có lifecycle khác nhau, capability tương đối ổn định | Pilot Microservices theo một capability | Kiểm chứng triển khai và ownership độc lập |
| Một thành phần có profile tải/độ tin cậy đặc biệt | Tách thành service chuyên biệt nếu cost-benefit hợp lý | Có thể scale và xử lý rủi ro riêng |
| Release chung gây chờ đợi nhưng code phụ thuộc chặt | Giảm coupling và cải thiện pipeline trước | Chia deployment chưa tạo độc lập khi runtime/data còn phụ thuộc |
| Cần giao dịch nhất quán tức thời xuyên nhiều miền | Cân nhắc giữ trong một boundary | Tránh biến thao tác đơn giản thành workflow phân tán khó phục hồi |
| Đã có platform, on-call, telemetry và domain ownership mạnh | Tách dần theo mục tiêu sản phẩm | Độ phức tạp phát sinh có nơi chịu trách nhiệm |

**Modular Monolith không đồng nghĩa với bước thụt lùi.** Nó cho phép giữ các module, hợp đồng, kiểm thử và quyền sở hữu rõ ràng với một đơn vị triển khai. Nếu nhu cầu thay đổi, các module có boundary tốt là điểm xuất phát hữu ích cho việc tách service. Ngược lại, một Distributed Monolith là tình trạng có nhiều process nhưng vẫn deploy cùng nhau, chia sẻ database và phải phối hợp sửa đổi liên tục.

## 10. Kịch bản thực hành: hệ thống thương mại điện tử

Giả sử một sản phẩm có các miền **Catalog**, **Checkout**, **Inventory** và **Payment**. Hệ thống hiện là Monolith và có ba nhóm phát triển sản phẩm. Catalog thay đổi thường xuyên; Checkout và Payment đang cập nhật chung vài bảng. Triển khai production đã tự động, nhưng tracing chỉ bao phủ API gateway; không có đội on-call riêng cho payment; mọi thay đổi schema phải phối hợp nhiều nhóm.

**Nhu cầu được nêu:** nhóm Catalog muốn phát hành độc lập vì phải đợi lịch release chung, còn nhóm Checkout cần bảo đảm không tạo đơn/thanh toán trùng khi kết nối chập chờn.

**Cách đọc mức sẵn sàng:**

- **T1 tương đối khá:** pipeline đã tự động, nhưng phải kiểm tra khả năng rollback khi đổi schema và contract test trước khi tách.
- **T3 còn lỗ hổng:** nếu tách Checkout–Payment, lúc yêu cầu timeout sẽ khó biết thanh toán thành công hay thất bại; cần trace/correlation ID và runbook.
- **T4 có rủi ro cổng:** shared write vào bảng chung khiến ranh giới dữ liệu chưa rõ; cần ownership, hợp đồng và chiến lược idempotency/đối soát.
- **O2/O3 chưa chắc đạt:** số service tăng nhưng chưa có trực vận hành và nguồn lực xử lý incident cho các service mới.
- **O1 có cơ hội:** Catalog có ngôn ngữ và vòng đời nghiệp vụ tương đối độc lập, là ứng viên thử nghiệm tốt hơn luồng thanh toán.

**Quyết định đề xuất:** giữ Checkout–Payment trong boundary vận hành chung ở giai đoạn đầu; làm rõ module và quyền sở hữu bảng dữ liệu; chuẩn hóa tracing, SLO, on-call. Sau đó cân nhắc tách **Catalog read capability** hoặc luồng không chứa giao dịch tài chính làm pilot, nếu đo được lợi ích phát hành/scale. Không tách tất cả các miền cùng lúc chỉ vì sơ đồ mục tiêu có bốn ô dịch vụ.

**Định nghĩa thành công của pilot (minh họa):** đội Catalog có thể thay đổi và phát hành mà không yêu cầu Checkout deploy; một phiên bản API cũ và mới cùng chạy an toàn trong thời gian chuyển đổi; sự cố giả lập được phát hiện và rollback trong thời gian chấp nhận; chi phí vận hành được đo và có owner chịu trách nhiệm. Ngưỡng cụ thể phải lấy từ baseline/SLO của chính sản phẩm.

## 11. Lộ trình tăng sẵn sàng theo từng đợt

Một kế hoạch 90 ngày có thể dùng làm ví dụ tổ chức công việc, nhưng không phải cam kết thời gian áp dụng cho mọi đội:

| Giai đoạn minh họa | Việc làm | Tiêu chí hoàn tất có thể kiểm chứng |
|---|---|---|
| Ngày 1–15: baseline | Lập capability map, owner map, đo delivery/reliability, phỏng vấn | Có số liệu nền và rủi ro trọng yếu được ghi |
| Ngày 16–30: nền tảng tối thiểu | Chuẩn hóa CI/CD, secrets, template, logs/metrics/trace | Một nhóm tự deploy và truy vết lỗi end-to-end |
| Ngày 31–45: hợp đồng và dữ liệu | Xác định owner dữ liệu, versioning, contract tests, idempotency | Mô phỏng consumer cũ và event trùng đạt yêu cầu |
| Ngày 46–70: pilot | Tách capability phù hợp, triển khai canary/feature flag, đo cost/SLI | Có chứng cứ deploy, rollback, incident và quyền sở hữu |
| Ngày 71–90: quyết định | So với baseline, cập nhật rubric/ADR và roadmap | Quyết định mở rộng, điều chỉnh hoặc dừng có tiêu chí rõ |

Không cần chạy đồng loạt tất cả hạng mục. Nên giải quyết trước những thiếu hụt **chặn triển khai an toàn**: ownership/on-call, pipeline, observability, secrets và ranh giới dữ liệu. Những cải tiến ít rủi ro có thể làm ngay trong Monolith và tiếp tục hữu ích dù không chọn Microservices.

### Ví dụ backlog cải thiện năng lực

| Vấn đề | Hành động cụ thể | Owner khả dĩ | Chứng cứ nghiệm thu |
|---|---|---|---|
| Không tìm được root cause qua nhiều thành phần | Thêm correlation ID, trace context và dashboard theo business transaction | Platform + service team | Truy vết được một giao dịch khi dependency lỗi |
| Schema gây release đồng bộ | Thiết lập expand–migrate–contract, kiểm thử consumer | Data owner + service teams | Consumer cũ vẫn hoạt động trong cửa sổ chuyển đổi |
| Rollback phụ thuộc một cá nhân | Chuẩn hóa pipeline và diễn tập roll-forward/rollback | DevOps + product team | Một thành viên trực chạy được theo runbook |
| Không rõ ai trực service | Service catalog, lịch on-call, escalation, postmortem | Engineering manager | Mỗi service có owner và quy trình được thử |
| Cost thiếu minh bạch | Gắn nhãn workload, thu thập chi phí infra/telemetry | Platform + FinOps | Báo cáo chi phí theo capability và theo kỳ |
| Retry gây giao dịch lặp | Thiết lập idempotency key, deduplication và đối soát | Domain team | Test lỗi mạng/trùng thông điệp không tạo tác dụng kép |

## 12. Các câu hỏi phỏng vấn và bài kiểm tra sát thực tế

**Đối với Product/Business:** Capability nào cần thay đổi độc lập và vì sao? Có doanh thu, trải nghiệm người dùng hoặc thời gian ra thị trường nào bị ảnh hưởng bởi release chung? Nếu tách trong sáu tháng mà lead time không đổi, ta có tiếp tục không?

**Đối với Engineering:** Lần gần nhất thay đổi một module phải sửa module khác là khi nào? Có thể release một capability mà không đợi nhóm khác không? Khi đổi API/schema, các consumer đang chạy phiên bản cũ sẽ ra sao? Ranh giới nào đã ổn định và ranh giới nào vẫn phải học thêm?

**Đối với Operations/SRE:** Nếu một dependency timeout trong 15 phút, ai được cảnh báo và đọc dashboard gì? Có thể phân biệt lỗi network, lỗi business và lỗi dữ liệu? Ai quyết định rollback, và khôi phục dữ liệu ra sao? Có diễn tập vào thời điểm không có chuyên gia chính?

**Đối với Platform/DevOps:** Một nhóm tự tạo service mới và triển khai an toàn cần những bước nào? Service có mặc định logs, metrics, trace, secrets, policy và pipeline không? Có quota/cost guardrail? Mức độ tự phục vụ được đo như thế nào?

**Đối với Data/Security:** Ai có quyền ghi dữ liệu thuộc miền khác? Làm sao đối soát sự kiện trùng hoặc gửi trễ? Credential giữa service được cấp và xoay vòng thế nào? Nếu một workload bị xâm phạm, phạm vi quyền có được giới hạn không?

**Bài kiểm tra kỹ thuật gợi ý:** đưa ra yêu cầu “Customer nhấn Thanh toán, Payment xử lý thành công nhưng Checkout không nhận được response”. Nhóm phải mô tả: trạng thái đơn, idempotency, cách tra cứu kết quả thanh toán, timeout/retry, cơ chế đối soát, telemetry và thông điệp hiển thị cho người dùng. Một phương án có thể thực thi và kiểm thử được cho thấy mức sẵn sàng cao hơn câu trả lời chung chung “cứ dùng message queue”.

## 13. Những sai lầm thường gặp khi đánh giá

1. **Đếm số công cụ thay cho năng lực:** có Docker, Kafka hoặc Kubernetes không đồng nghĩa có pipeline, ownership, resiliency và vận hành an toàn.
2. **Dùng một điểm số để che cổng rủi ro:** tổng điểm cao không bù được lỗ hổng bảo mật hoặc không có khả năng khôi phục giao dịch tài chính.
3. **Bắt mọi đội dùng cùng kiến trúc:** từng miền có nhu cầu và năng lực khác nhau; kiến trúc hỗn hợp có thể là lựa chọn hợp lý.
4. **Chỉ phỏng vấn lãnh đạo:** tình trạng thực tế của release và incident thường được thấy rõ hơn từ người trực tiếp triển khai và vận hành.
5. **Dùng demo một lần để chấm mức trưởng thành:** năng lực phải lặp lại qua nhóm, người và tình huống, kể cả khi người chủ chốt vắng mặt.
6. **Bỏ qua chi phí nhận thức:** nhiều service làm tăng số repository, môi trường, hợp đồng, dashboard, cảnh báo, pipeline và quyết định liên nhóm.
7. **Xem network như lời gọi hàm nội bộ:** request có thể timeout dù tác vụ đã thành công; retry có thể gây trùng; lỗi có thể lan truyền hoặc kéo dài.
8. **Tách database trước khi làm rõ ownership:** shared tables và distributed transactions sẽ bộc lộ coupling chưa được giải quyết.
9. **Chọn boundary theo tổ chức nhất thời:** nhóm có thể đổi tên/cấu trúc; domain boundary cần gắn vào nghiệp vụ và được điều chỉnh bằng bằng chứng thay đổi.
10. **Không có điều kiện dừng:** pilot thiếu baseline và tiêu chí go/no-go có thể trở thành việc tách toàn hệ thống không có cơ sở kiểm soát.

## 14. Mẫu hồ sơ đánh giá có thể tái sử dụng

Dưới đây là cấu trúc một hồ sơ đánh giá cho mỗi sản phẩm hoặc capability:

**Thông tin đầu vào**

- Tên sản phẩm/capability và phiên bản phạm vi:
- Mục tiêu kinh doanh và vấn đề hiện tại:
- Người tài trợ, người quyết định, người đánh giá:
- Giai đoạn lấy số liệu và hệ thống chứng cứ:
- Ranh giới nghiệp vụ và dependency đáng chú ý:
- Kiến trúc hiện tại và phương án thay thế:

**Bảng đánh giá**

| Chiều | Mức 0–4 | Điểm có trọng số | Chứng cứ/đường dẫn | Tin cậy | Lỗ hổng và owner |
|---|---:|---:|---|---|---|
| O1 | | | | | |
| O2 | | | | | |
| O3 | | | | | |
| O4 | | | | | |
| O5 | | | | | |
| T1 | | | | | |
| T2 | | | | | |
| T3 | | | | | |
| T4 | | | | | |
| T5 | | | | | |

**Cổng:** G1 __; G2 __; G3 __; G4 __; G5 __; G6 __ (Đạt/Chưa đạt/Chưa có bằng chứng).

**Kết quả:** Điểm tổ chức __/50; điểm kỹ thuật __/50; tổng __/100; độ tin cậy __; rủi ro trọng yếu __.

**Quyết định:** Chọn một phương án có lý do: (a) duy trì/chuẩn hóa Modular Monolith; (b) pilot giới hạn; (c) tách dần theo capability. Ghi rõ điều kiện để bắt đầu, phạm vi thử nghiệm, cách rollback, chỉ số cần đạt, chi phí tối đa, người phụ trách và ngày đánh giá lại.

### Mẫu ADR ngắn

**ADR: Đánh giá mức sẵn sàng để tách Catalog**

- **Trạng thái:** Đề xuất / Được chấp thuận / Bị bác bỏ / Thay thế.
- **Bối cảnh:** Release chung làm nhóm Catalog chờ nhóm Checkout; cần cải thiện độc lập thay đổi.
- **Phương án:** (1) Giữ Modular Monolith và tách ownership/module; (2) Tách Catalog thành service có API rõ; (3) Tách đồng thời toàn bộ hệ thống.
- **Chứng cứ:** lead time và deploy baseline, điểm 10 chiều, trạng thái sáu cổng, phân tích ranh giới dữ liệu, chi phí/khả năng vận hành.
- **Quyết định và lý do:** nêu lựa chọn theo lợi ích và mức rủi ro đã chứng minh.
- **Điều kiện:** owner/on-call, hợp đồng API, telemetry, CI/CD, rollback và giới hạn dữ liệu.
- **Cách đo:** lead time, incident/SLO, số thay đổi cần phối hợp, chi phí hoạt động, phản hồi developer.
- **Đánh giá lại:** sau pilot hoặc khi điều kiện kinh doanh/kỹ thuật thay đổi.

## 15. Checklist sử dụng trước buổi quyết định

### Tổ chức và mục tiêu

- [ ] Có vấn đề kinh doanh cụ thể mà độc lập triển khai hoặc mở rộng giúp giải quyết.
- [ ] Có bản đồ capability, bounded context và dependency trọng yếu.
- [ ] Mỗi candidate service có một owner, backup và kênh escalation.
- [ ] Các nhóm có quyền triển khai trong phạm vi tiêu chuẩn an toàn chung.
- [ ] Có khả năng vận hành 24/7 hoặc mức hỗ trợ phù hợp SLO của sản phẩm.
- [ ] Có ngân sách/timebox cho platform, đào tạo, incident và công cụ.
- [ ] Có baseline lead time, sự cố, chi phí, phụ thuộc liên nhóm.
- [ ] Có người ra quyết định và thời điểm đánh giá lại.

### Kỹ thuật và vận hành

- [ ] CI/CD build–test–deploy có thể chạy lặp lại và có phương án rollback.
- [ ] API/event có chính sách tương thích phiên bản và contract test.
- [ ] Môi trường/cấu hình/secrets được quản lý nhất quán, có thể tái tạo.
- [ ] Logs, metrics và traces cho phép theo dấu giao dịch end-to-end.
- [ ] Có SLI/SLO, alert có thể hành động, runbook và diễn tập incident.
- [ ] Có timeout, retry có giới hạn, backoff và idempotency ở nơi cần thiết.
- [ ] Có owner dữ liệu, consistency model, cơ chế bù trừ và đối soát.
- [ ] Có xác thực/phân quyền giữa service, secrets rotation và audit.
- [ ] Có kiểm soát tài nguyên, môi trường, traffic và chi phí quan sát.
- [ ] Có kiểm tra tải, lỗi từng phần, khôi phục và phương án rollback pilot.

### Chứng cứ và quyết định

- [ ] Mỗi điểm rubric có bằng chứng và mức tin cậy rõ.
- [ ] Tổng điểm và hai nhóm điểm được tính từ cùng phiên bản trọng số.
- [ ] Sáu cổng có trạng thái và kế hoạch khắc phục nếu chưa đạt.
- [ ] Có so sánh Microservices với Modular Monolith theo mục tiêu thực tế.
- [ ] Pilot có phạm vi nhỏ, chỉ số go/no-go, owner và ngân sách.
- [ ] Quyết định được ghi thành ADR và sẽ được đo lại bằng số liệu.

## 16. Kết luận thực hành

Sẵn sàng cho Microservices là khả năng **đưa nhiều dịch vụ qua toàn bộ vòng đời một cách độc lập, an toàn, có thể quan sát và có chi phí chấp nhận được**. Hãy dùng mục tiêu kinh doanh để quyết định có cần sự độc lập đó, dùng rubric và các cổng để đo khả năng thực hiện, rồi dùng pilot để kiểm chứng giả thuyết.

Nếu ranh giới nghiệp vụ chưa ổn định hoặc nền tảng chưa bảo đảm release, dữ liệu, bảo mật và xử lý sự cố, việc củng cố **Modular Monolith, quyền sở hữu module, CI/CD và observability** là tiến bộ thực chất. Khi nhu cầu và năng lực đã đủ rõ, tách từng capability có giá trị và đo kết quả sẽ kiểm soát được rủi ro tốt hơn việc chia hệ thống hàng loạt.
