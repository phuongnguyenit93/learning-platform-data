# Phân biệt kiểm thử sau triển khai với giám sát liên tục

## 1. Vì sao cần phân biệt hai hoạt động?

Sau khi một phiên bản được triển khai, nhóm cần xác nhận dịch vụ thực sự hoạt động trong môi trường đích và tiếp tục theo dõi chất lượng khi người dùng sử dụng. Hai hoạt động thường được nhắc đến là **kiểm thử sau triển khai (post-deployment testing)** và **giám sát liên tục (continuous monitoring)**. Chúng cùng góp phần bảo vệ chất lượng vận hành, nhưng có mục tiêu, cách tạo bằng chứng và kiểu hành động khác nhau.

Kiểm thử sau triển khai chủ động thực hiện một tập kiểm tra có mục đích và kết quả mong đợi trên phiên bản vừa triển khai. Ví dụ, sau khi cập nhật dịch vụ đặt hàng, pipeline gọi health endpoint, đăng nhập bằng tài khoản kiểm thử, tạo một đơn hàng tổng hợp và xác nhận trạng thái đơn được lưu đúng.

Giám sát liên tục quan sát trạng thái và hành vi của hệ thống theo thời gian bằng metric, log, trace, sự kiện, synthetic signal và dữ liệu trải nghiệm người dùng. Ví dụ, dashboard theo dõi tỷ lệ tạo đơn thành công, p95 latency, lỗi HTTP, queue lag, saturation và các cảnh báo khi chỉ số vượt ngưỡng.

Một lần kiểm thử thành công chỉ cho biết các kịch bản đã chạy đạt trong điều kiện và thời điểm đó. Nó không chứng minh mọi hành trình người dùng sẽ luôn hoạt động. Ngược lại, dashboard không có cảnh báo không chứng minh mọi chức năng đều đúng; có thể chưa có tín hiệu cho một lỗi nghiệp vụ hoặc một luồng hiếm gặp.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, cần phối hợp hai hoạt động để:

- Xác nhận nhanh bản triển khai có thể phục vụ các hành vi trọng yếu.
- Phát hiện suy giảm hoặc bất thường tiếp diễn trong vận hành.
- Đưa ra quyết định tiếp tục rollout, tạm dừng, rollback hoặc kích hoạt incident.
- Liên kết thay đổi triển khai với bằng chứng kỹ thuật và tác động người dùng.
- Bảo đảm có người chịu trách nhiệm xử lý kết quả và cảnh báo.

## 2. Định nghĩa và mục tiêu

### 2.1. Kiểm thử sau triển khai

Post-deployment testing là hoạt động chạy các kiểm tra được xác định trước sau khi artifact hoặc cấu hình đã được triển khai vào môi trường mục tiêu. Nó trả lời câu hỏi: **phiên bản vừa triển khai có thực hiện đúng các hành vi và điều kiện đã chọn hay không?**

Mục tiêu thường gồm:

- Xác nhận deployment hoàn tất và đúng phiên bản.
- Kiểm tra dịch vụ khởi động, sẵn sàng và có thể truy cập.
- Xác nhận các endpoint, luồng nghiệp vụ hoặc tích hợp trọng yếu.
- Phát hiện lỗi cấu hình, migration, quyền, dependency hoặc kết nối.
- Kiểm tra các hành vi có rủi ro cao bằng dữ liệu và tài khoản được kiểm soát.
- Cung cấp bằng chứng cho quyết định tiếp tục rollout hoặc mở lưu lượng.

Post-deployment testing có thể gồm smoke test, sanity test, health/readiness check, API test, contract verification, synthetic transaction, kiểm tra migration và một tập end-to-end có giới hạn. Không phải mọi test hồi quy đều cần chạy sau mỗi lần deploy; phạm vi phải dựa trên rủi ro, thời gian và khả năng tác động đến môi trường thật.

### 2.2. Giám sát liên tục

Continuous monitoring là việc thu thập, tổng hợp, phân tích và phản ứng với tín hiệu từ hệ thống trong suốt thời gian vận hành. Nó trả lời câu hỏi: **dịch vụ đang hoạt động như thế nào theo thời gian và người dùng có đang nhận được chất lượng mong đợi hay không?**

Mục tiêu thường gồm:

- Theo dõi availability, latency, traffic, error rate và saturation.
- Quan sát hành trình và kết quả nghiệp vụ thực tế.
- Phát hiện xu hướng suy giảm, bất thường và lỗi lặp lại.
- Theo dõi SLI/SLO và mức tiêu thụ error budget.
- Cung cấp tín hiệu để điều tra, cảnh báo và xử lý incident.
- Đánh giá tác động của deployment, thay đổi cấu hình và rollout.

Giám sát có thể dùng metric, log, distributed trace, event, real user monitoring (RUM), synthetic monitoring và dữ liệu từ hệ thống nghiệp vụ. Tín hiệu cần được gắn với service, phiên bản, vùng, tenant hoặc hành trình phù hợp để hỗ trợ chẩn đoán.

### 2.3. Bảng phân biệt nhanh

| Khía cạnh | Kiểm thử sau triển khai | Giám sát liên tục |
|---|---|---|
| Câu hỏi chính | Kịch bản đã chọn có đạt sau khi deploy không? | Hệ thống và người dùng đang trải nghiệm điều gì theo thời gian? |
| Mục tiêu | Xác nhận có chủ đích trên phiên bản vừa triển khai | Phát hiện và theo dõi trạng thái vận hành liên tục |
| Cách hoạt động | Chạy test có bước, input và expected result | Thu thập và phân tích telemetry/sự kiện |
| Thời điểm | Ngay sau deploy, theo từng giai đoạn rollout hoặc theo lịch | Liên tục trong cửa sổ vận hành |
| Phạm vi | Tập kịch bản và điều kiện được chọn | Tín hiệu trên lưu lượng, tài nguyên và hành vi thực tế |
| Kết quả | Passed, failed, blocked, inconclusive và artifact test | Metric, log, trace, alert, dashboard và incident signal |
| Tác nhân | Test runner, pipeline hoặc người kiểm thử | Agent, collector, telemetry backend và hệ thống cảnh báo |
| Hành động | Chặn rollout, chạy lại, sửa hoặc rollback theo gate | Điều tra, cảnh báo, giảm tải, rollback hoặc incident response |
| Giới hạn | Không bao phủ mọi thời điểm và mọi hành vi | Không tự chứng minh mọi quy tắc nghiệp vụ nếu không có tín hiệu phù hợp |

## 3. Các loại kiểm thử thường chạy sau triển khai

### 3.1. Deployment verification

Xác nhận bản triển khai đã áp dụng đúng artifact và cấu hình:

- Build ID, image digest hoặc release version đúng với kế hoạch.
- Replica/pod hoặc process ở trạng thái mong đợi.
- Migration và bước khởi tạo hoàn tất.
- Cấu hình, feature flag và secret reference được nạp đúng.
- Route, DNS, TLS và endpoint hoạt động.

Kiểm tra deployment verification không chỉ nhìn trạng thái công cụ báo “success”. Cần xác nhận workload thực sự chạy phiên bản dự kiến và có thể phục vụ yêu cầu.

### 3.2. Health và readiness check

Health check có thể kiểm tra process còn sống, còn readiness check xác nhận instance sẵn sàng nhận traffic theo định nghĩa của dịch vụ. Các check nên có timeout, dependency scope và trạng thái rõ.

Không nên đưa mọi dependency vào liveness check theo cách khiến một sự cố phụ thuộc làm process liên tục khởi động lại. Phân biệt:

- **Liveness:** process có còn hoạt động và có thể tiếp tục không?
- **Readiness:** instance có đủ điều kiện nhận traffic không?
- **Startup check:** ứng dụng đã hoàn tất khởi động chưa?
- **Dependency check:** các hệ thống phụ thuộc quan trọng có sẵn sàng không?

Health endpoint xanh không đồng nghĩa luồng nghiệp vụ hoàn chỉnh đã hoạt động. Nó chỉ xác nhận những điều kiện endpoint đó thực sự kiểm tra.

### 3.3. Smoke test

Smoke test là tập kiểm tra nhỏ, chạy nhanh để xác nhận các chức năng cốt lõi sau thay đổi. Ví dụ:

- Dịch vụ trả phản hồi hợp lệ.
- Người dùng kiểm thử có thể đăng nhập.
- API đọc dữ liệu trọng yếu hoạt động.
- Một luồng tạo hoặc tra cứu đối tượng có thể hoàn tất.
- Kết nối đến dependency chính được xác nhận.

Smoke test nên ngắn và ổn định để hỗ trợ quyết định rollout. Không nên biến smoke suite thành một bộ hồi quy dài, khó chẩn đoán.

### 3.4. Sanity test

Sanity test tập trung vào một vùng chức năng hoặc thay đổi cụ thể để xác nhận hành vi liên quan có vẻ đúng sau triển khai. Ví dụ, sau khi thay đổi cách tính thuế, sanity test xác nhận một số trường hợp đại diện có kết quả đúng.

Smoke test thường xác nhận các chức năng cốt lõi có hoạt động; sanity test thường kiểm tra nhanh vùng vừa thay đổi. Ranh giới có thể khác nhau giữa các tổ chức, vì vậy cần ghi rõ mục tiêu và phạm vi thay vì dựa vào tên gọi.

### 3.5. API và contract verification

Kiểm tra API sau deploy có thể xác nhận status code, schema, authentication, authorization và quy tắc phản hồi. Contract verification xác nhận provider vẫn đáp ứng hợp đồng mà consumer sử dụng.

Test cần chạy trên đúng phiên bản provider và môi trường. Nếu dùng mock hoặc sandbox, phải ghi rõ phần nào đã xác nhận bằng dịch vụ thật và phần nào chỉ được mô phỏng.

### 3.6. Synthetic transaction và end-to-end test có kiểm soát

Synthetic transaction tạo một hành trình kiểm thử bằng tài khoản hoặc dữ liệu tổng hợp để xác nhận nhiều thành phần phối hợp. Ví dụ, tạo một đơn hàng kiểm thử, kiểm tra trạng thái thanh toán giả lập và xác nhận thông báo được ghi nhận.

Nếu chạy trong production, cần:

- Dùng tenant/tài khoản và dữ liệu được phê duyệt.
- Tránh tạo thanh toán, email, SMS hoặc tác dụng phụ thật ngoài ý muốn.
- Có định danh rõ để truy vết và dọn dữ liệu.
- Giới hạn tần suất, quyền và phạm vi thao tác.
- Bảo đảm test không ảnh hưởng khách hàng hoặc báo cáo nghiệp vụ.

### 3.7. Kiểm tra migration và dữ liệu

Sau migration, có thể kiểm tra schema, số lượng bản ghi, constraint, checksum hoặc một số invariant nghiệp vụ. Với thay đổi dữ liệu quan trọng, cần có phương án đối soát và phục hồi.

Một vài truy vấn kiểm tra không thay thế kiểm thử đầy đủ trên dữ liệu đại diện. Cần ghi rõ phạm vi dữ liệu đã xác nhận, cách xử lý dữ liệu lỗi và giới hạn của phép kiểm tra.

## 4. Các hình thức giám sát liên tục

### 4.1. Metrics

Metrics là số liệu theo thời gian hoặc theo sự kiện được tổng hợp để quan sát xu hướng. Những nhóm tín hiệu phổ biến:

- **Traffic:** số request, transaction, job hoặc message.
- **Errors:** lỗi HTTP, exception, timeout, retry và thất bại nghiệp vụ.
- **Latency:** thời gian phản hồi, thường theo p50/p90/p95/p99.
- **Saturation:** CPU, memory, disk, connection pool, thread pool, queue và quota.
- **Business metrics:** đơn hàng thành công, thanh toán hoàn tất, tỷ lệ đăng nhập, đối soát hoặc xử lý hồ sơ.

Có thể sử dụng mô hình RED (Rate, Errors, Duration) cho dịch vụ request/response và USE (Utilization, Saturation, Errors) cho tài nguyên. Đây là các cách tổ chức quan sát, không phải danh sách bắt buộc cho mọi hệ thống.

### 4.2. Logs

Log ghi lại sự kiện và ngữ cảnh tại một thời điểm. Log có cấu trúc giúp lọc theo service, version, severity, correlation ID và loại lỗi. Cần tránh ghi token, mật khẩu, dữ liệu cá nhân hoặc nội dung nhạy cảm không cần thiết.

Log hữu ích cho điều tra chi tiết nhưng không nên là nguồn duy nhất để đánh giá availability. Một hệ thống có thể ghi log rất nhiều nhưng vẫn không có metric tổng hợp về tỷ lệ request thành công.

### 4.3. Distributed tracing

Trace liên kết các span qua nhiều dịch vụ để cho thấy đường đi của một request hoặc transaction. Trace giúp xác định thành phần gây chậm, lỗi hoặc retry trong luồng phân tán.

Sampling cần cân bằng giữa chi phí và khả năng quan sát. Nếu chỉ giữ trace thành công hoặc sampling quá thấp, nhóm có thể bỏ lỡ lỗi hiếm. Với sự kiện quan trọng, có thể tăng sampling có chọn lọc theo lỗi hoặc rủi ro.

### 4.4. Real User Monitoring (RUM)

RUM thu thập tín hiệu từ trải nghiệm người dùng thực, ví dụ thời gian tải trang, lỗi JavaScript, thiết bị, trình duyệt và vùng địa lý. RUM cho biết trải nghiệm thực tế khác nhau theo người dùng và điều kiện mạng như thế nào.

RUM cần tuân thủ chính sách quyền riêng tư, consent, data minimization và thời hạn lưu. Không thu thập nội dung nhạy cảm chỉ vì công cụ cho phép.

### 4.5. Synthetic monitoring

Synthetic monitoring chạy định kỳ các request hoặc hành trình mô phỏng từ những điểm quan sát đã chọn. Nó có thể phát hiện lỗi ngay cả khi lưu lượng người dùng thấp.

Synthetic monitoring có đặc điểm giống kiểm thử vì chủ động thực hiện kịch bản có expected result. Khi chạy theo lịch liên tục để theo dõi availability, nó là một nguồn tín hiệu trong hệ thống monitoring. Vì vậy, tên công cụ không quyết định ranh giới; mục đích, tần suất, cách đánh giá và hành động mới là yếu tố quan trọng.

### 4.6. Event và business telemetry

Một số lỗi không thể phát hiện chỉ bằng CPU hoặc HTTP status. Ví dụ, request trả 200 nhưng giao dịch không được ghi nhận, đơn hàng bị tạo trùng hoặc trạng thái thanh toán không đồng bộ. Business telemetry theo dõi sự kiện và invariant nghiệp vụ để phát hiện những tình huống này.

Các sự kiện cần có định danh, schema, timestamp và quy tắc chống đếm trùng. Việc thu thập phải cân nhắc dữ liệu cá nhân và quyền truy cập.

## 5. Phối hợp kiểm thử sau triển khai với giám sát

Hai hoạt động nên được thiết kế như một vòng phản hồi:

~~~text
Triển khai phiên bản
        |
        v
Xác nhận deployment và readiness
        |
        v
Chạy post-deployment smoke/sanity/synthetic tests
        |
        v
Gate quyết định: tiếp tục, tạm dừng hay rollback
        |
        v
Mở rộng traffic theo giai đoạn
        |
        v
Continuous monitoring: metrics, logs, traces, RUM, events
        |
        v
Phát hiện bất thường hoặc xác nhận ổn định
        |
        +------> Incident/rollback/mitigation nếu vượt ngưỡng
        |
        v
Review kết quả, cập nhật test và monitoring
~~~

### 5.1. Kiểm thử xác nhận có chủ đích

Test sau deploy cần chọn các kịch bản có khả năng phát hiện lỗi triển khai nhanh: sai image, cấu hình thiếu, quyền không đúng, migration chưa hoàn tất hoặc luồng nghiệp vụ cốt lõi bị hỏng.

### 5.2. Monitoring theo dõi điều kiện thực tế

Sau khi test đạt, monitoring tiếp tục quan sát khi traffic tăng, dữ liệu tích lũy, job nền chạy hoặc dependency thay đổi. Nó có thể phát hiện suy giảm không xuất hiện trong vài phút đầu.

### 5.3. Dùng deployment marker để liên kết tín hiệu

Ghi lại thời điểm deploy, version, commit, region, canary cohort và feature flag. Khi metric thay đổi, nhóm có thể so sánh trước/sau và xác định tín hiệu có liên quan đến rollout không.

### 5.4. Dùng cùng định nghĩa nhưng không đánh đồng bằng chứng

Test và monitoring có thể cùng theo dõi tỷ lệ tạo đơn thành công, nhưng nguồn và cách diễn giải khác nhau. Test chạy một tập giao dịch được kiểm soát; monitoring quan sát traffic thật hoặc synthetic signal theo thời gian. Báo cáo nên giữ nguồn, sample và giới hạn riêng.

## 6. Thiết kế phạm vi post-deployment testing

### 6.1. Bắt đầu từ thay đổi và rủi ro

Xem xét loại thay đổi:

- Code nghiệp vụ hoặc thuật toán.
- API, event, schema hoặc contract.
- Cấu hình, secret reference và feature flag.
- Runtime, thư viện hoặc base image.
- Hạ tầng, mạng, gateway và database.
- Migration, batch job hoặc dữ liệu.
- Cơ chế xác thực, phân quyền và bảo mật.

Với mỗi thay đổi, xác định hành vi có thể bị ảnh hưởng, mức độ nghiêm trọng nếu lỗi và test ngắn nhất có thể cung cấp bằng chứng đáng tin.

### 6.2. Chọn tập kiểm tra theo lớp

Một tập post-deployment có thể gồm:

1. Deployment identity và version check.
2. Startup, liveness và readiness.
3. Smoke test cho API/hành trình cốt lõi.
4. Sanity test cho vùng vừa thay đổi.
5. Contract hoặc integration check cho dependency trọng yếu.
6. Migration/data invariant check.
7. Synthetic transaction an toàn nếu cần xác nhận end-to-end.

Không phải release nào cũng cần tất cả lớp. Ghi rõ tiêu chí chọn hoặc bỏ, nhất là với test có tác dụng phụ hoặc thời gian dài.

### 6.3. Chọn môi trường và dữ liệu

Staging có thể hỗ trợ kiểm tra rộng với dữ liệu tổng hợp; production canary có thể xác nhận một số hành vi trên cấu hình thật với phạm vi rất nhỏ. Test trong production phải có phê duyệt, tài khoản và dữ liệu an toàn, cùng cơ chế dừng.

Không dùng dữ liệu production tùy tiện trong test. Nếu cần kiểm tra dữ liệu thực, tuân thủ quy trình truy cập và bảo vệ dữ liệu; cân nhắc snapshot đã xử lý hoặc synthetic data có phân bố phù hợp.

### 6.4. Xác định expected result

Mỗi test cần nêu:

- Điều kiện đầu vào và trạng thái trước khi chạy.
- Hành động được thực hiện.
- Kết quả mong đợi và tiêu chí pass/fail.
- Timeout và retry policy.
- Tác dụng phụ được phép.
- Cách cleanup hoặc bù trừ.
- Artifact cần lưu và thông tin định danh.

Một test chỉ kiểm tra endpoint trả HTTP 200 có thể bỏ sót lỗi nghiệp vụ. Chọn assertion phản ánh hành vi quan trọng, ví dụ trạng thái đơn, số tiền, quyền sở hữu và sự kiện được phát.

## 7. Thiết kế continuous monitoring

### 7.1. Chọn tín hiệu gắn với trải nghiệm và rủi ro

Bắt đầu từ câu hỏi người dùng hoặc nghiệp vụ cần trả lời. Ví dụ:

- Người dùng có đăng nhập được không?
- Giao dịch có hoàn tất trong thời gian mong đợi không?
- Dữ liệu có được cập nhật đúng và đủ không?
- Job nền có xử lý backlog kịp không?
- Dịch vụ có đủ tài nguyên khi traffic tăng không?
- Một vùng hoặc một nhóm tenant có đang gặp lỗi riêng không?

Sau đó chọn metric, log, trace, event hoặc RUM phù hợp. Tránh thu thập mọi thứ mà không có người dùng hoặc hành động cụ thể.

### 7.2. Định nghĩa SLI và SLO

SLI (Service Level Indicator) là chỉ số đo một khía cạnh dịch vụ; SLO (Service Level Objective) là mục tiêu đã thống nhất cho SLI trong một cửa sổ thời gian.

Ví dụ:

- SLI: tỷ lệ request tạo đơn hợp lệ hoàn tất thành công.
- SLO: mục tiêu tỷ lệ thành công trong cửa sổ 30 ngày theo điều kiện đã định.
- SLI: p95 latency của API tra cứu đơn.
- SLO: p95 nằm trong ngưỡng mục tiêu với workload và phạm vi xác định.

Định nghĩa cần làm rõ request hợp lệ, lỗi được tính, loại trừ, vùng, tenant, cửa sổ và nguồn dữ liệu. SLO không nên chỉ chọn vì dễ đo; nó cần phản ánh trải nghiệm và cam kết phù hợp.

### 7.3. Thiết kế alert có thể hành động

Một alert tốt cần:

- Phản ánh tác động hoặc rủi ro cần hành động.
- Có ngưỡng, cửa sổ và điều kiện rõ.
- Có owner hoặc on-call nhận cảnh báo.
- Có mức độ và hướng dẫn điều tra.
- Có liên kết dashboard, runbook hoặc incident process.
- Hạn chế cảnh báo trùng lặp và nhiễu.

Không nên cảnh báo cho mọi metric thay đổi nhỏ. Cảnh báo quá nhiều làm người trực bỏ qua tín hiệu quan trọng. Metric có thể được hiển thị trên dashboard mà không cần tạo alert.

### 7.4. Theo dõi error budget

Với dịch vụ dùng SLO, error budget thể hiện mức lỗi hoặc suy giảm được phép trong cửa sổ mục tiêu. Tốc độ tiêu thụ error budget có thể giúp phát hiện khi release mới làm chất lượng giảm nhanh.

Burn-rate alert kết hợp mức tiêu thụ và cửa sổ thời gian để phát hiện vi phạm SLO có ý nghĩa. Cần chọn cửa sổ và ngưỡng theo mức tác động; không sao chép con số mẫu mà không hiểu lưu lượng và yêu cầu dịch vụ.

### 7.5. Phân đoạn và tránh cardinality không kiểm soát

Phân đoạn theo version, region, service, endpoint hoặc cohort có thể giúp tìm lỗi chỉ xuất hiện ở một nhóm. Tuy nhiên, tạo label có giá trị duy nhất cho mỗi user, request hoặc order có thể làm tăng cardinality, chi phí và rủi ro riêng tư. Dùng correlation ID trong trace/log theo cơ chế phù hợp thay vì biến mọi định danh thành metric label.

### 7.6. Quản lý dashboard và runbook

Dashboard cần thể hiện tín hiệu quan trọng, đơn vị, phạm vi, thời điểm cập nhật và ngưỡng. Runbook cần hướng dẫn người trực xác nhận alert, tìm bằng chứng, giảm thiểu, escalation và xác nhận phục hồi.

Dashboard không thay thế runbook; runbook không thay thế người chịu trách nhiệm. Mỗi alert quan trọng cần có owner và đường liên hệ rõ.

## 8. Quyết định rollout dựa trên test và monitoring

### 8.1. Progressive delivery

Với canary hoặc progressive rollout, phiên bản mới được triển khai cho một phần nhỏ traffic hoặc một nhóm instance trước. Nhóm đánh giá post-deployment tests và monitoring trước khi mở rộng.

Các giai đoạn có thể gồm:

1. Deploy vào một nhóm instance hoặc cohort nhỏ.
2. Xác nhận version, readiness và smoke test.
3. Theo dõi error rate, latency, saturation và business metric.
4. So sánh canary với baseline hoặc cohort ổn định.
5. Tiếp tục tăng traffic nếu điều kiện đạt.
6. Tạm dừng hoặc rollback nếu tiêu chí dừng bị kích hoạt.

### 8.2. Kết hợp hard checks và tín hiệu vận hành

Một release gate có thể yêu cầu:

- Post-deployment smoke test bắt buộc đạt.
- Không có lỗi nghiêm trọng trong synthetic transaction.
- Error rate và latency không vượt ngưỡng đã xác định.
- Business invariant không suy giảm.
- Không có alert hoặc incident vượt mức dừng.

Test pass nhưng monitoring xấu vẫn phải dừng để điều tra. Monitoring bình thường nhưng test bắt buộc fail cũng không được bỏ qua chỉ vì chưa có khách hàng báo lỗi.

### 8.3. Điều kiện rollback và forward-fix

Trước rollout, xác định:

- Tín hiệu nào kích hoạt pause hoặc rollback.
- Ai có quyền quyết định và ai thực hiện.
- Có thể rollback artifact/config an toàn không?
- Migration có tương thích ngược không?
- Khi không thể rollback, phương án forward-fix hoặc tắt feature flag là gì?
- Dữ liệu đã tạo bởi phiên bản mới được xử lý thế nào?
- Làm sao xác nhận hệ thống ổn định sau hành động?

Rollback không phải lúc nào cũng là lựa chọn an toàn, đặc biệt khi schema hoặc dữ liệu đã thay đổi. Cần kiểm tra tương thích và có kế hoạch dữ liệu trước khi dựa vào rollback.

## 9. Phân loại kết quả và phản ứng

### 9.1. Kết quả post-deployment test

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| Passed | Kịch bản chạy hợp lệ và đạt expected result | Ghi bằng chứng; tiếp tục bước theo gate |
| Failed | Kịch bản chạy và không đạt expected result | Dừng bước liên quan, điều tra và xử lý |
| Blocked | Không thể chạy do môi trường, quyền, dữ liệu hoặc dependency | Khắc phục điều kiện; không coi là pass |
| Inconclusive | Kết quả thiếu hoặc mâu thuẫn, không thể kết luận | Bổ sung bằng chứng hoặc chạy lại |
| Skipped/Not run | Không được thực hiện theo phạm vi đã định | Ghi lý do và đánh giá khoảng trống |
| Not applicable | Điều kiện test không áp dụng với căn cứ được review | Giữ lý do trong báo cáo |

### 9.2. Trạng thái monitoring

Monitoring thường không chỉ có pass/fail. Có thể dùng:

- Normal: tín hiệu nằm trong vùng vận hành dự kiến.
- Warning: có xu hướng hoặc ngưỡng cảnh báo cần theo dõi.
- Alert/Degraded: điều kiện cần người trực điều tra hoặc giảm thiểu.
- Critical: tác động nghiêm trọng cần incident response.
- No data/Unknown: telemetry không đến hoặc không đủ để kết luận.

**No data không đồng nghĩa Normal.** Mất telemetry có thể là vấn đề của ứng dụng, collector hoặc nền tảng giám sát; cần có kiểm tra sức khỏe cho chính hệ thống monitoring.

### 9.3. Kết hợp kết quả

| Post-deployment test | Monitoring | Diễn giải và hành động |
|---|---|---|
| Passed | Normal | Có thể tiếp tục rollout theo kế hoạch và duy trì quan sát |
| Passed | Warning/Degraded | Test đã chọn đạt nhưng vận hành có dấu hiệu xấu; tạm dừng mở rộng và điều tra |
| Failed | Normal | Không bỏ qua test fail; xác minh lỗi và dừng gate liên quan |
| Blocked | Normal | Thiếu bằng chứng test; xử lý nguyên nhân blocked và đánh giá rủi ro |
| Passed | No data/Unknown | Không đủ tín hiệu vận hành; kiểm tra telemetry trước khi tiếp tục nếu monitoring là điều kiện bắt buộc |
| Inconclusive | Critical | Ưu tiên incident response và giảm thiểu tác động |

Không dùng một bảng kết hợp cố định thay cho chính sách. Với hệ thống có rủi ro cao, một test bắt buộc fail có thể chặn rollout bất kể monitoring chưa ghi nhận tác động.

## 10. Trách nhiệm trong kiểm thử sau deploy và monitoring

| Vai trò | Trách nhiệm |
|---|---|
| Release/deployment owner | Xác định phiên bản, thời điểm, phạm vi rollout và deployment marker |
| Test owner/QA | Thiết kế post-deployment test, expected result, dữ liệu và xác nhận kết quả |
| Service owner | Chịu trách nhiệm hành vi dịch vụ, rủi ro và hành động khắc phục |
| Platform/SRE | Duy trì hạ tầng, telemetry, alerting, dashboard và cơ chế rollout |
| On-call/incident commander | Nhận cảnh báo, điều phối incident và giảm thiểu tác động |
| Product/business owner | Xác định chỉ số nghiệp vụ và mức ảnh hưởng đến người dùng |
| Security/privacy owner | Xác nhận yêu cầu chuyên môn và cách xử lý tín hiệu nhạy cảm |
| Release authority | Quyết định tiếp tục, tạm dừng hoặc phát hành theo thẩm quyền |

Một nhóm có thể kiêm nhiều vai trò, nhưng cần chỉ định rõ ai theo dõi trong cửa sổ rollout, ai nhận alert và ai được quyền dừng hoặc tiếp tục. Không để test runner tạo cảnh báo nhưng không có người nhận.

## 11. Bảo đảm an toàn cho test trong môi trường production

Post-deployment testing có thể chạy trong production để xác nhận cấu hình thật, nhưng cần kiểm soát tác động:

- Ưu tiên endpoint read-only hoặc thao tác có thể đảo ngược.
- Dùng tài khoản, tenant và dữ liệu synthetic được phê duyệt.
- Đánh dấu giao dịch test để loại khỏi báo cáo kinh doanh.
- Giới hạn tần suất, số lượng và phạm vi request.
- Không kích hoạt thanh toán, email, SMS hoặc hành động bên ngoài thật nếu chưa có cơ chế an toàn.
- Dùng idempotency key và định danh test run để tránh tạo dữ liệu trùng.
- Có cleanup hoặc bù trừ được kiểm soát.
- Bảo vệ credential và log.
- Xác định người có quyền dừng test.

Nếu không thể bảo đảm an toàn, chạy kiểm thử trên staging hoặc sandbox có độ trung thực phù hợp và ghi rõ giới hạn so với production. Không vì muốn xác nhận nhanh mà tạo tác dụng phụ lên khách hàng.

## 12. Xử lý alert và chuyển sang incident

Khi monitoring phát cảnh báo:

1. Xác nhận alert có dữ liệu hợp lệ và phạm vi ảnh hưởng.
2. Kiểm tra deployment marker, version, feature flag và thay đổi gần nhất.
3. Đối chiếu metric, log, trace, RUM và business event.
4. Xác định mức độ, người dùng và dịch vụ bị ảnh hưởng.
5. Thực hiện runbook: pause rollout, giảm traffic, tắt feature hoặc rollback nếu phù hợp.
6. Kích hoạt incident process khi đạt ngưỡng.
7. Thông báo các bên liên quan theo quy trình.
8. Xác nhận phục hồi bằng cả test và tín hiệu vận hành.
9. Ghi nhận defect, action và test/alert cần bổ sung.

Nếu monitoring không có dữ liệu, kiểm tra collector, pipeline telemetry, quyền, quota và backend. Không kết luận hệ thống bình thường chỉ vì không có alert.

## 13. Ví dụ thực tế

### Ví dụ A: Triển khai phiên bản mới của API đặt hàng

Sau khi deploy, pipeline xác nhận image digest đúng, readiness đạt, API tạo đơn trả kết quả mong đợi với tài khoản test và đơn hàng được lưu ở trạng thái hợp lệ. Smoke test pass.

Khi mở canary lên một tỷ lệ traffic nhỏ, monitoring cho thấy p95 latency tăng và queue lag tăng dù smoke test vẫn pass. Nhóm tạm dừng rollout, dùng trace để xác định một truy vấn mới gây chậm, sau đó rollback hoặc áp dụng biện pháp đã được phê duyệt. Ví dụ cho thấy test sau deploy xác nhận kịch bản đã chọn, còn monitoring phát hiện suy giảm dưới tải thực tế.

### Ví dụ B: Thay đổi schema database

Deployment pipeline chạy migration và kiểm tra schema version. Post-deployment test đọc/ghi một bản ghi tổng hợp, xác nhận constraint và trạng thái dữ liệu cơ bản.

Monitoring tiếp tục theo dõi lock wait, query latency, connection pool, replication lag và lỗi truy cập dữ liệu. Khi traffic tăng, lock wait vượt ngưỡng. Nhóm tạm dừng rollout và đánh giá migration. Một test pass trên vài bản ghi không đủ để chứng minh migration hoạt động tốt ở quy mô dữ liệu lớn.

### Ví dụ C: Triển khai giao diện web

Sau deploy, smoke test xác nhận trang tải, đăng nhập test account và một hành trình tìm kiếm cơ bản. RUM tiếp tục theo dõi thời gian tải, lỗi JavaScript và tỷ lệ tương tác theo browser/device.

Một nhóm người dùng Safari gặp lỗi JavaScript không xuất hiện trong smoke test chạy trên Chromium. RUM giúp phát hiện phân đoạn bị ảnh hưởng; nhóm dùng log client và replay đã được xử lý theo chính sách để điều tra. Nhóm bổ sung test trình duyệt phù hợp và điều chỉnh canary.

### Ví dụ D: Dịch vụ thanh toán

Post-deployment test xác nhận health, token test và một giao dịch sandbox hoặc giao dịch production an toàn theo quy trình được phê duyệt. Monitoring theo dõi tỷ lệ giao dịch thành công, timeout, giao dịch trùng, độ trễ provider và chênh lệch đối soát.

Nếu tỷ lệ HTTP 2xx vẫn cao nhưng business event cho thấy nhiều giao dịch ở trạng thái pending quá lâu, monitoring nghiệp vụ phát cảnh báo. Nhóm kiểm tra provider, callback và consumer; chỉ số HTTP đơn lẻ không đủ phản ánh hoàn tất thanh toán.

### Ví dụ E: Job xử lý dữ liệu nền

Sau deploy, test xác nhận worker khởi động, đọc một message synthetic và ghi kết quả đúng. Monitoring liên tục theo dõi queue depth, oldest message age, retry count, dead-letter queue và processing latency.

Khi backlog tăng nhưng worker vẫn health, nhóm biết vấn đề nằm ở throughput hoặc dependency thay vì tiến trình bị dừng. Test sau deploy không thay thế giám sát tải và tiến độ xử lý theo thời gian.

## 14. Mẫu kế hoạch post-deployment verification và monitoring

~~~yaml
deployment_validation:
  release_id: "orders-5.2.0"
  build_id: "build-2052"
  environment: "production-canary"
  deployment_marker: "deploy-orders-2052"

post_deployment_tests:
  - id: DEPLOY-VERSION
    purpose: "Xác nhận đúng artifact"
    expected: "running image digest matches release manifest"
    required: true
    owner: "release-engineering"

  - id: ORDER-SMOKE
    purpose: "Xác nhận luồng tạo đơn tổng hợp"
    expected: "test order is created with expected state"
    data: "approved-synthetic-tenant"
    side_effects: "tagged-and-cleaned"
    required: true
    owner: "order-test-owner"

monitoring:
  window: "canary-observation-window"
  signals:
    - name: "order_success_rate"
      source: "business-events"
      owner: "order-service-owner"
    - name: "http_p95_latency"
      source: "service-metrics"
      owner: "sre-on-call"
    - name: "queue_oldest_message_age"
      source: "queue-telemetry"
      owner: "platform-team"
  alert_routes:
    warning: "service-on-call"
    critical: "incident-response"

rollout_decision:
  continue_when:
    - "all required post-deployment tests pass"
    - "monitoring signals remain within approved thresholds"
  pause_when:
    - "required test is blocked or inconclusive"
    - "warning threshold is exceeded"
  rollback_or_mitigate_when:
    - "critical user-impact threshold is exceeded"
  approver: "release-authority"
~~~

Đây là mẫu khái niệm. Ngưỡng, thời lượng quan sát, hành động và tên owner phải lấy từ SLO, chính sách release và năng lực vận hành thực tế. Không dùng nguyên văn các giá trị mẫu làm cấu hình production.

## 15. Những sai lầm thường gặp

- **Coi smoke test pass là đủ:** test chỉ xác nhận một số kịch bản tại một thời điểm.
- **Coi không có alert là hệ thống khỏe:** telemetry có thể mất hoặc alert chưa được cấu hình.
- **Dùng health endpoint làm bằng chứng nghiệp vụ:** process sống không có nghĩa giao dịch hoàn tất.
- **Chạy test production gây tác dụng phụ:** tạo giao dịch, gửi thông báo hoặc làm nhiễu số liệu thật.
- **Không gắn deployment marker:** khó liên kết thay đổi với suy giảm.
- **Không theo dõi theo phiên bản/canary:** lỗi chỉ xuất hiện trên cohort mới bị che bởi số tổng.
- **Dùng ngưỡng alert thiếu ngữ cảnh:** tạo alert noise hoặc bỏ sót tác động.
- **Không phân biệt blocked với passed:** thiếu bằng chứng bị hiểu nhầm là đạt.
- **Chỉ theo dõi hạ tầng:** CPU và memory bình thường nhưng hành vi nghiệp vụ có thể sai.
- **Chỉ theo dõi HTTP status:** request thành công ở tầng giao thức nhưng kết quả nghiệp vụ chưa hoàn tất.
- **Không có owner/on-call:** alert không dẫn đến hành động.
- **Rollback không xét dữ liệu:** phiên bản cũ có thể không tương thích schema mới.
- **Không xác nhận sau rollback:** nhóm không biết hệ thống đã phục hồi hay chưa.
- **Không cập nhật test và alert sau incident:** cùng lỗi có thể tái diễn mà không được phát hiện sớm.

## 16. Checklist vận hành sau triển khai

### Trước khi deploy

- [ ] Artifact, build ID và cấu hình được chốt.
- [ ] Rủi ro và hành vi cần xác nhận sau deploy đã được xác định.
- [ ] Post-deployment test có expected result, timeout và owner.
- [ ] Tài khoản/dữ liệu synthetic và tác dụng phụ được kiểm soát.
- [ ] Dashboard, alert, SLO và runbook đã sẵn sàng.
- [ ] Deployment marker và version metadata được cấu hình.
- [ ] Điều kiện pause, rollback hoặc forward-fix được thống nhất.
- [ ] On-call, release owner và người có quyền quyết định đã được xác định.

### Ngay sau deploy

- [ ] Xác nhận đúng artifact và phiên bản.
- [ ] Kiểm tra startup/readiness và dependency trọng yếu.
- [ ] Chạy smoke/sanity/API/contract test phù hợp.
- [ ] Xác minh dữ liệu và migration nếu có.
- [ ] Lưu report, log, trace và run ID.
- [ ] Không mở rộng rollout khi hard test chưa có kết quả hợp lệ.

### Trong cửa sổ monitoring

- [ ] Theo dõi traffic, errors, latency và saturation.
- [ ] Theo dõi business metric và hành trình quan trọng.
- [ ] Phân đoạn tín hiệu theo version, region hoặc canary cohort.
- [ ] Xác nhận telemetry vẫn đến và dashboard cập nhật.
- [ ] Alert có owner, runbook và escalation path.
- [ ] Dừng hoặc giảm rollout khi ngưỡng đã thống nhất bị vượt.

### Khi kết thúc rollout

- [ ] Đã đủ thời gian và dữ liệu để đánh giá ổn định theo kế hoạch.
- [ ] Không còn alert hoặc incident chưa được xử lý vượt ngưỡng.
- [ ] Các test blocked/not run có quyết định và owner.
- [ ] Kết quả test và monitoring được liên kết với release record.
- [ ] Hành động sau phát hành có thời hạn và người chịu trách nhiệm.
- [ ] Bài học từ sự cố được chuyển thành test, metric hoặc alert phù hợp.

## Kết luận

Kiểm thử sau triển khai chủ động xác nhận các kịch bản đã chọn trên phiên bản vừa đưa vào môi trường; giám sát liên tục quan sát trạng thái, trải nghiệm và tín hiệu nghiệp vụ trong suốt thời gian vận hành. Test cung cấp bằng chứng có expected result nhưng chỉ bao phủ điều kiện đã chạy; monitoring phản ánh diễn biến thực tế nhưng phụ thuộc vào chất lượng telemetry và quy tắc cảnh báo. Kết hợp deployment verification, smoke/sanity test, synthetic transaction, SLI/SLO, alert, canary và quy trình incident giúp nhóm quyết định rollout có căn cứ. Mỗi hoạt động cần owner, ngưỡng, dữ liệu an toàn và hành động rõ ràng để bảo vệ người dùng sau phát hành.
