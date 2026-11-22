# Rà soát chiến lược với góc nhìn nghiệp vụ, phát triển và vận hành

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích vì sao chiến lược kiểm thử cần được rà soát với sự tham gia của nghiệp vụ, phát triển và vận hành.
- Phân biệt mục tiêu chất lượng, chiến lược kiểm thử, kế hoạch kiểm thử và bằng chứng phát hành.
- Chuẩn bị thông tin đầu vào để review chiến lược dựa trên mục tiêu sản phẩm, kiến trúc, rủi ro và điều kiện vận hành.
- Khai thác góc nhìn nghiệp vụ để xác định hành trình quan trọng, tác động người dùng, quy tắc và mức chấp nhận rủi ro.
- Khai thác góc nhìn phát triển để đánh giá kiến trúc, testability, dependency, automation và khả năng duy trì kiểm thử.
- Khai thác góc nhìn vận hành để đánh giá SLI/SLO, triển khai, quan sát, phục hồi, capacity và hỗ trợ sau phát hành.
- Điều phối phiên review, xử lý khác biệt và ghi nhận quyết định có thể truy nguyên.
- Chuyển kết quả review thành thay đổi cụ thể trong phạm vi, cấp test, dữ liệu, môi trường, pipeline và monitoring.
- Theo dõi hành động và xác minh chiến lược đã được cải thiện sau khi áp dụng.

## 1. Vì sao cần rà soát chiến lược từ nhiều góc nhìn?

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, chiến lược kiểm thử xác định cách tổ chức thu thập bằng chứng rằng sản phẩm đáp ứng yêu cầu, kiểm soát rủi ro và đạt mục tiêu chất lượng. Chiến lược cần kết nối mục tiêu sản phẩm với cách thiết kế kiểm thử, nguồn lực, môi trường, dữ liệu, tự động hóa, phát hành và giám sát sau triển khai.

Một chiến lược được xây dựng chỉ từ góc nhìn QA có thể bao phủ nhiều test case nhưng bỏ qua ưu tiên kinh doanh, khả năng tích hợp hoặc điều kiện production. Một chiến lược chỉ do phát triển quyết định có thể tập trung vào unit test và độ phủ mã nhưng thiếu bằng chứng về hành trình người dùng. Một chiến lược chỉ do vận hành quyết định có thể chú trọng uptime và alert nhưng không kiểm tra đủ tính đúng đắn của quy tắc nghiệp vụ.

Rà soát với ba góc nhìn nghiệp vụ, phát triển và vận hành giúp phát hiện những giả định khác nhau trước khi chúng trở thành khoảng trống chất lượng. Nghiệp vụ giải thích điều gì quan trọng và hậu quả khi sai; phát triển giải thích hệ thống được xây dựng và thay đổi như thế nào; vận hành giải thích hệ thống hoạt động trong điều kiện thực tế, được triển khai, quan sát và phục hồi ra sao.

Ví dụ, sản phẩm bổ sung thanh toán bất đồng bộ. Góc nhìn nghiệp vụ yêu cầu khách hàng không bị trừ tiền hai lần và biết rõ trạng thái giao dịch. Góc nhìn phát triển xem xét idempotency, callback, event ordering và trạng thái dữ liệu. Góc nhìn vận hành xem xét queue lag, retry, cảnh báo giao dịch bất thường, đối soát và quy trình hoàn tiền. Chiến lược kiểm thử cần kết hợp các yêu cầu này thành bằng chứng ở nhiều cấp, từ unit và contract đến integration, E2E và monitoring.

Rà soát đa góc nhìn giúp:

- Kiểm tra chiến lược có bảo vệ đúng mục tiêu và hành trình quan trọng hay không.
- Phát hiện rủi ro nằm ở ranh giới giữa nhóm hoặc giữa service.
- Xác định test có thể tự động hóa và test cần đánh giá thủ công.
- Kiểm tra khả năng thực thi với kiến trúc, dữ liệu, môi trường và ngân sách hiện tại.
- Làm rõ ai sở hữu từng loại bằng chứng và quyết định phát hành.
- Giảm xung đột giữa tốc độ phát triển, mức kiểm soát và độ ổn định vận hành.
- Tạo vòng phản hồi từ sự cố và người dùng trở lại chiến lược kiểm thử.

Review không phải cuộc họp để mọi bên chỉ xác nhận tài liệu. Đây là hoạt động kiểm tra giả định, tìm khoảng trống, thống nhất đánh đổi và giao hành động có bằng chứng hoàn thành.

## 2. Phân biệt chiến lược kiểm thử với kế hoạch và kết quả kiểm thử

Trước khi review, cần thống nhất đối tượng được xem xét.

| Đối tượng | Câu hỏi chính | Ví dụ nội dung |
|---|---|---|
| Mục tiêu chất lượng | Sản phẩm cần đạt điều gì? | Thanh toán chính xác, dữ liệu được cách ly, hành trình hoàn tất ổn định. |
| Chiến lược kiểm thử | Tổ chức sẽ tạo bằng chứng bằng cách nào và ưu tiên ở đâu? | Phân tầng test, risk-based testing, contract test, E2E, performance và security. |
| Kế hoạch kiểm thử | Với thay đổi hoặc release cụ thể, ai làm gì, khi nào và ở đâu? | Phạm vi sprint, môi trường, dữ liệu, lịch chạy, người thực hiện. |
| Test case/suite | Tình huống nào được kiểm tra cụ thể? | Callback lặp chỉ tạo một capture record. |
| Bằng chứng | Kết quả nào hỗ trợ kết luận? | Test report, trace, metric, đối soát và phê duyệt ngoại lệ. |
| Quyết định phát hành | Có đủ căn cứ để chuyển giai đoạn không? | Pass các cổng bắt buộc, rủi ro còn lại được chấp nhận đúng thẩm quyền. |

Chiến lược thường ổn định hơn kế hoạch của một release nhưng cần được rà soát khi mục tiêu, kiến trúc, rủi ro hoặc cách vận hành thay đổi. Review một kế hoạch sprint không thay thế review chiến lược nếu vấn đề nằm ở cách tổ chức kiểm thử lâu dài.

## 3. Chuẩn bị trước phiên review

Một phiên review hiệu quả cần bắt đầu từ tài liệu và dữ liệu đã có. Không nên dành phần lớn thời gian để các nhóm kể lại thông tin có thể đọc trước.

### 3.1. Xác định trigger và phạm vi

Review có thể được kích hoạt khi:

- Sản phẩm mở rộng người dùng, thị trường, tenant hoặc hành trình nghiệp vụ.
- Kiến trúc thay đổi, tách service, chuyển database hoặc thêm dependency.
- Nhóm phát hành độc lập hoặc chuyển sang CI/CD với tốc độ cao hơn.
- Sự cố, lỗi lọt hoặc phản hồi người dùng cho thấy khoảng trống kiểm thử.
- SLO, SLA, yêu cầu bảo mật hoặc quy định thay đổi.
- Chi phí test, thời gian pipeline hoặc tỷ lệ flaky vượt mức chấp nhận.
- Thay đổi tổ chức, ownership hoặc năng lực làm ảnh hưởng khả năng thực thi.

Ghi rõ review toàn bộ chiến lược hay chỉ một phần, ví dụ kiểm thử migration, kiểm soát API hoặc năng lực phục hồi. Phạm vi rõ giúp tránh thảo luận lan sang những vấn đề chưa cần quyết định.

### 3.2. Thu thập đầu vào

Chuẩn bị các nguồn phù hợp:

- Mục tiêu sản phẩm, roadmap, hành trình và acceptance criteria.
- Risk register, incident report, escaped defect và phản hồi người dùng.
- Kiến trúc, dependency map, API/event contract và data flow.
- Test strategy hiện tại, test inventory, coverage và execution report.
- Pipeline duration, flaky rate, thời gian chờ runner và chi phí automation.
- Môi trường, cấu hình, test data, quota và giới hạn dịch vụ phụ thuộc.
- SLI/SLO, dashboard, alert, runbook và báo cáo capacity.
- Kế hoạch release, migration, rollback và disaster recovery.
- Ownership, ma trận kỹ năng và nguồn lực của các nhóm.

Không cần đưa toàn bộ dữ liệu vào một tài liệu. Cần chọn bằng chứng trả lời câu hỏi review và cung cấp liên kết có thể truy nguyên.

### 3.3. Gửi câu hỏi trước

Gửi trước một số câu hỏi để mỗi nhóm chuẩn bị góc nhìn:

- Nghiệp vụ: hành trình nào quan trọng nhất, điều gì không được phép sai và rủi ro nào thay đổi?
- Phát triển: thay đổi nào khó kiểm thử, dependency nào dễ gây lỗi và test nào đang thiếu?
- Vận hành: điều gì thường hỏng trong production, tín hiệu nào phát hiện sớm và khả năng phục hồi ra sao?

### 3.4. Xác định người tham gia

Mời người có thể cung cấp thông tin hoặc quyết định, chẳng hạn product owner/business analyst, QA/test lead, developer/architect, service owner, SRE/operations, security/privacy owner và release manager. Không cần mời đông người nếu họ không có vai trò trong phạm vi review.

### 3.5. Đặt tiêu chí thành công cho phiên review

Ví dụ đầu ra cần đạt:

- Xác định các khoảng trống chiến lược có rủi ro cao.
- Thống nhất thay đổi cần thiết trong phạm vi hoặc lớp kiểm thử.
- Xác định owner và nguồn lực cho hành động.
- Ghi nhận rủi ro còn lại và người có thẩm quyền chấp nhận.
- Xác định thời điểm kiểm tra hiệu quả sau khi áp dụng.

## 4. Rà soát từ góc nhìn nghiệp vụ

Góc nhìn nghiệp vụ trả lời câu hỏi: sản phẩm cần làm đúng điều gì, với ai, trong điều kiện nào và hậu quả ra sao nếu không đúng?

### 4.1. Mục tiêu và kết quả người dùng

Kiểm tra chiến lược có liên kết với mục tiêu sản phẩm và kết quả người dùng hay không:

- Người dùng chính và nhóm sử dụng mới đã được xác định chưa?
- Hành trình nào tạo giá trị hoặc doanh thu quan trọng?
- Tác vụ nào có hậu quả cao nếu thất bại?
- Người dùng có thể thực hiện thao tác theo nhiều cách hoặc trên nhiều kênh không?
- Có hành trình ngoại lệ, hỗ trợ thủ công hoặc phụ thuộc đối tác không?
- Tiêu chí chất lượng có phản ánh trải nghiệm thực tế không?

Ví dụ, chỉ đo API response time có thể không phản ánh thời gian người dùng hoàn tất đặt hàng nếu còn bước xác nhận thanh toán và giữ hàng bất đồng bộ.

### 4.2. Quy tắc và bất biến nghiệp vụ

Rà soát các quy tắc quan trọng:

- Trạng thái và chuyển tiếp hợp lệ.
- Tính toán tiền, thuế, phí, chiết khấu và hoàn tiền.
- Quyền và giới hạn theo vai trò hoặc tenant.
- Điều kiện duy nhất, idempotency và chống xử lý trùng.
- Thời hạn, timezone, lịch làm việc và điều kiện hết hạn.
- Đối soát giữa các hệ thống.
- Chính sách dữ liệu, lưu trữ và xóa.

Nghiệp vụ cần xác nhận những hành vi nào được phép thay đổi và hành vi nào phải tiếp tục đúng sau release. Đây là đầu vào cho regression test và tiêu chí chấp nhận.

### 4.3. Ưu tiên theo tác động

Không nên phân bổ nỗ lực kiểm thử chỉ theo số lượng tính năng. Hãy xem hậu quả khi lỗi xảy ra:

- Thiệt hại tài chính hoặc giao dịch sai.
- Mất dữ liệu hoặc lộ dữ liệu.
- Gián đoạn hành trình cốt lõi.
- Ảnh hưởng uy tín, hợp đồng hoặc tuân thủ.
- Tác động đến nhóm người dùng dễ bị tổn thương hoặc nhóm có ít phương án thay thế.
- Khả năng phát hiện và khôi phục.

Một lỗi hiếm trong hoàn tiền có thể cần mức kiểm soát cao hơn lỗi giao diện phổ biến nhưng ít hậu quả.

### 4.4. Tiêu chí chấp nhận và mức rủi ro được chấp nhận

Kiểm tra tiêu chí có đo được và được hiểu giống nhau giữa product, QA và engineering không. Những cụm như “nhanh”, “ổn định”, “không mất dữ liệu” cần được diễn đạt thành hành vi, chỉ số hoặc điều kiện kiểm tra.

Nghiệp vụ cần tham gia quyết định đánh đổi, nhưng không tự ý chấp nhận rủi ro thuộc thẩm quyền bảo mật, pháp lý hoặc vận hành. Quyền phê duyệt cần theo chính sách của tổ chức.

### 4.5. Phản hồi và dữ liệu người dùng

Rà soát xem chiến lược có sử dụng:

- Ticket hỗ trợ và phản hồi sau release.
- Tỷ lệ hoàn thành/bỏ dở hành trình.
- Phân tích usability và accessibility.
- Khiếu nại, hoàn tiền, giao dịch bất thường.
- Khác biệt theo nhóm người dùng, vùng, thiết bị hoặc tenant.

Không diễn giải số ticket đơn thuần thành tỷ lệ lỗi toàn bộ người dùng. Cần xét sai lệch kênh, mẫu và ngữ cảnh.

### 4.6. Câu hỏi review dành cho nghiệp vụ

- Những hành trình nào phải được bảo vệ trong mọi release?
- Hành vi nào có hậu quả không thể chấp nhận nếu sai?
- Tiêu chí hiện tại có phản ánh mục tiêu mới và nhóm người dùng mới không?
- Quy tắc nghiệp vụ nào đang nằm trong kinh nghiệm của một vài cá nhân?
- Có phản hồi production nào chưa được chuyển thành test hoặc tiêu chí không?
- Ai có quyền chấp nhận ngoại lệ và rủi ro còn lại?

## 5. Rà soát từ góc nhìn phát triển

Góc nhìn phát triển trả lời câu hỏi: hệ thống được xây dựng như thế nào, thay đổi lan truyền ra sao và nhóm có thể kiểm tra hành vi một cách đáng tin cậy đến đâu?

### 5.1. Kiến trúc và dependency

Kiểm tra:

- Thành phần, service và ranh giới sở hữu có rõ không?
- API, event, schema và dependency nào có thể bị ảnh hưởng?
- Có consumer hoặc phiên bản cũ cùng tồn tại không?
- Hệ thống xử lý timeout, retry, duplicate, ordering và partial failure thế nào?
- Có shared database, shared state hoặc cấu hình toàn cục không?
- Thay đổi có ảnh hưởng migration hoặc dữ liệu lịch sử không?

Kiến trúc càng phân tán thì bằng chứng contract, integration và traceability càng quan trọng. Không thể chỉ dựa vào unit test của từng repository để kết luận hành trình xuyên service hoạt động đúng.

### 5.2. Testability

Rà soát khả năng kiểm tra:

- Có thể điều khiển đầu vào, clock, trạng thái và dependency không?
- Có thể tạo dữ liệu đại diện và dữ liệu biên không?
- Có thể quan sát kết quả qua API, event, log hoặc state không?
- Có cơ chế reset/cleanup và cô lập test không?
- Có thể mô phỏng lỗi hoặc dependency chậm không?
- Test có thể chạy độc lập và tái lập không?

Nếu một hành vi quan trọng không thể kiểm thử do thiết kế, có thể cần cải thiện testability trong code hoặc kiến trúc. Không nên bù mọi khó khăn bằng E2E hoặc thao tác thủ công.

### 5.3. Phân tầng test

Kiểm tra phân bổ giữa:

- Unit test cho logic và quy tắc thuần.
- Component test cho hành vi trong service/module.
- Contract test cho API, event và schema.
- Integration test cho database, broker và dependency thật.
- System/E2E cho hành trình xuyên thành phần.
- Non-functional test cho hiệu năng, bảo mật, độ tin cậy và khả năng phục hồi.

Mỗi test cần có mục tiêu rõ và vị trí phù hợp. Một chiến lược có quá nhiều E2E có thể chậm và khó chẩn đoán; quá nhiều unit test mà thiếu contract/integration có thể bỏ sót lỗi ranh giới.

### 5.4. Automation và CI/CD

Rà soát:

- Test quan trọng nào chạy tự động trên mỗi commit, pull request hoặc release?
- Pipeline có thời gian phản hồi phù hợp không?
- Test selection có thể bỏ sót test liên quan không?
- Sharding và parallelism có ổn định, cô lập dữ liệu và giới hạn tài nguyên không?
- Kết quả flaky, retry và skipped được xử lý thế nào?
- Artifact, test report và log có được lưu và truy nguyên không?
- Quality gate có phân biệt Fail, Blocked và Inconclusive không?

Automation không tự tạo ra chất lượng. Cần kiểm tra assertion, dữ liệu, tính ổn định và khả năng phát hiện defect.

### 5.5. Code review, static analysis và dependency

Xác định lớp kiểm soát phù hợp:

- Review theo rủi ro và ownership.
- Static analysis, lint và type checking.
- Dependency scanning và kiểm tra license khi cần.
- Secret scanning và kiểm soát cấu hình.
- Contract/schema validation.
- Migration review và backward compatibility.

Các kiểm tra này bổ sung cho test runtime; không nên coi chúng thay thế bằng chứng hành vi.

### 5.6. Test data và môi trường phát triển

Kiểm tra dữ liệu có:

- Đại diện cho phân bố và trường hợp quan trọng.
- Có ID/namespace để tránh tranh chấp.
- Có thể tái tạo theo version.
- Được xử lý theo yêu cầu quyền riêng tư.
- Bao gồm dữ liệu cũ, thiếu, lỗi và trạng thái chuyển tiếp.

Môi trường cần có version, cấu hình và dependency rõ. Nếu local, CI và staging khác nhau, cần xác định khác biệt nào có thể ảnh hưởng kết quả.

### 5.7. Câu hỏi review dành cho phát triển

- Ranh giới service và hợp đồng nào cần bằng chứng riêng?
- Test có kiểm tra đúng hậu điều kiện và side effect không?
- Thay đổi có testability đủ tốt không?
- Pipeline có chạy đúng test vào đúng thời điểm không?
- Có test nào chậm, flaky hoặc không còn giá trị cần xử lý không?
- Phiên bản, schema, config và artifact có truy nguyên được không?
- Rủi ro kỹ thuật nào cần vận hành hoặc nghiệp vụ cùng quyết định?

## 6. Rà soát từ góc nhìn vận hành

Góc nhìn vận hành trả lời câu hỏi: sản phẩm hoạt động như thế nào trong production, nhóm nhận biết vấn đề ra sao và có thể khôi phục an toàn đến mức nào?

### 6.1. SLI, SLO và trải nghiệm thực tế

Rà soát:

- SLI có đo đúng hành trình hoặc kết quả người dùng cần không?
- SLO có phản ánh mức dịch vụ đã cam kết không?
- Latency dùng phân vị nào và điểm đo ở đâu?
- Error rate có tính timeout, retry và lỗi nghiệp vụ không?
- Có metric theo tenant, vùng, endpoint hoặc loại giao dịch khi cần không?
- Alert có hành động được hay chỉ tạo thông báo nhiễu?

Một request trả HTTP 200 không nhất thiết đồng nghĩa nghiệp vụ hoàn tất. Vận hành cần phối hợp với nghiệp vụ để định nghĩa business metric như tỷ lệ thanh toán thành công cuối cùng hoặc thời gian đơn hàng chuyển sang trạng thái xác nhận.

### 6.2. Observability

Kiểm tra khả năng quan sát:

- Log có cấu trúc, timestamp và correlation ID.
- Metric về traffic, errors, latency và saturation.
- Trace xuyên service và qua queue.
- Dashboard và alert có owner.
- Có thể liên kết telemetry với release/version.
- Có thể điều tra lỗi mà không cần truy cập dữ liệu nhạy cảm không cần thiết.

Nếu test phát hiện lỗi nhưng production không có tín hiệu tương ứng, chiến lược có thể cần bổ sung observability để phát hiện sớm hơn.

### 6.3. Triển khai và phát hành

Rà soát:

- Có thể triển khai từng phần hoặc canary không?
- Feature flag có default và quy trình tắt rõ không?
- Migration có tương thích với phiên bản cũ/mới không?
- Rollback hoặc forward-fix có khả thi và đã diễn tập chưa?
- Health check và smoke test sau triển khai có đủ không?
- Có tiêu chí dừng rollout dựa trên metric không?
- Ai điều phối release và xử lý khi quality gate không đạt?

### 6.4. Độ tin cậy và phục hồi

Xác minh:

- Retry, timeout, circuit breaker và bulkhead.
- Backup/restore và tính nhất quán sau phục hồi.
- RTO/RPO nếu áp dụng.
- Failover, degradation và dependency outage.
- Queue backlog, dead-letter và replay.
- Khả năng xử lý giao dịch dở dang và đối soát.
- Runbook, escalation và diễn tập incident.

### 6.5. Capacity và chi phí vận hành

Rà soát:

- Tải hiện tại và dự báo tăng trưởng.
- CPU, memory, I/O, network và connection pool.
- Quota dịch vụ bên ngoài.
- Chi phí môi trường test và thời gian runner.
- Khả năng mở rộng và điểm nghẽn.
- Tác động của performance test hoặc stress test lên môi trường chung.

### 6.6. Hỗ trợ và phản hồi sau phát hành

Kiểm tra:

- Support có biết cách ghi nhận và phân loại phản hồi không?
- Ticket có liên kết được với incident, release và hành trình không?
- Có quy trình chuyển vấn đề sang engineering/QA không?
- Bài học incident có được chuyển thành regression test hoặc runbook không?
- Người dùng có nhận được cập nhật phù hợp không?

### 6.7. Câu hỏi review dành cho vận hành

- Hành vi sai có được phát hiện trước khi người dùng báo không?
- Alert có phân biệt triệu chứng kỹ thuật với tác động nghiệp vụ không?
- Có đủ dữ liệu để định vị nguyên nhân xuyên service không?
- Rollback, restore và đối soát đã được thực hành chưa?
- Có rủi ro nào chỉ xuất hiện ở quy mô hoặc topology production không?
- Test nào cần chạy sau deploy hoặc theo lịch để bảo vệ vận hành?

## 7. Kết nối ba góc nhìn thành một chiến lược thống nhất

Mỗi góc nhìn cung cấp một phần của bức tranh. Chiến lược cần biến các thông tin này thành mục tiêu, rủi ro, kiểm soát và bằng chứng liên kết.

### 7.1. Ma trận góc nhìn

| Chủ đề | Nghiệp vụ | Phát triển | Vận hành |
|---|---|---|---|
| Hành trình cốt lõi | Giá trị và hậu quả khi lỗi | Service/API tham gia và state transition | SLI, dashboard và khả năng khôi phục hành trình |
| Dữ liệu | Tính đúng, đầy đủ và quy tắc | Schema, transaction, event và migration | Backup, restore, đối soát và retention |
| Hiệu năng | Kỳ vọng trải nghiệm và thời điểm cao điểm | Query, algorithm, cache và concurrency | Capacity, saturation, autoscaling và alert |
| Tích hợp | Quy tắc với đối tác và consumer | Contract, timeout, retry và versioning | Quota, network, credential và dependency health |
| Bảo mật | Nghĩa vụ và mức chấp nhận rủi ro | AuthN/AuthZ, validation và secure design | Monitoring, incident response và access control |
| Phát hành | Thời điểm và phạm vi ra mắt | Build, test, migration và compatibility | Canary, rollback, health và on-call readiness |
| Sự cố | Tác động người dùng và ưu tiên | Cơ chế lỗi và regression test | Detection, containment, recovery và postmortem |

### 7.2. Chuyển từ chủ đề sang câu hỏi kiểm chứng

Với mỗi chủ đề, hãy viết câu hỏi có thể trả lời bằng bằng chứng. Ví dụ:

- Nghiệp vụ: “Một giao dịch có thể tạo nhiều capture không?”
- Phát triển: “Handler có idempotent khi nhận cùng callback đồng thời không?”
- Vận hành: “Metric nào phát hiện số capture bất thường và ai nhận alert?”

Ba câu hỏi liên kết thành một kiểm soát xuyên vòng đời: quy tắc nghiệp vụ, cơ chế kỹ thuật và phát hiện sau triển khai.

### 7.3. Xác định nơi tạo bằng chứng

Không phải bằng chứng nào cũng cần được tạo ở cùng một môi trường:

- Unit/component trong pipeline service.
- Contract ở provider/consumer pipeline.
- Integration trong môi trường có dependency phù hợp.
- E2E trong staging hoặc môi trường đại diện.
- Performance/security/resilience trong môi trường chuyên biệt.
- Canary, synthetic monitoring và business metric sau triển khai.

Mỗi bằng chứng cần owner và điều kiện hiệu lực. Kết quả staging không chứng minh thuộc tính production chưa được mô phỏng; telemetry production không thay thế kiểm thử trước khi mở rộng traffic.

## 8. Đánh giá tính khả thi và chi phí của chiến lược

Một chiến lược bao phủ nhiều rủi ro nhưng không thể thực hiện thường xuyên sẽ không tạo ra bằng chứng như mong đợi. Review cần đánh giá cả giá trị và khả năng thực thi.

### 8.1. Nguồn lực và năng lực

- Có đủ người sở hữu test, dữ liệu, môi trường và automation không?
- Có người dự phòng cho hoạt động quan trọng không?
- Kỹ năng security, performance, data hoặc reliability có sẵn không?
- Có thời gian để bảo trì test và xử lý flaky không?
- Các nhóm có thể phối hợp theo lịch phát hành hiện tại không?

### 8.2. Thời gian phản hồi

Đo thời gian từ commit đến kết quả của các lớp test. Xác định critical path, queue time, setup, execution và aggregation. Test quan trọng cần chạy sớm; test nặng có thể chạy theo trigger hoặc trước release, nhưng phải có kiểm soát thay thế cho rủi ro chưa được kiểm tra ngay.

### 8.3. Chi phí và lợi ích

So sánh:

- Chi phí runner, môi trường, dữ liệu và công cụ.
- Chi phí bảo trì automation và test data.
- Thời gian chờ do pipeline hoặc môi trường.
- Chi phí incident, rollback, hỗ trợ và lỗi lọt.
- Mức giảm rủi ro hoặc tăng khả năng phát hiện.

Không nên chỉ tối ưu chi phí test nếu làm tăng đáng kể rủi ro mất dữ liệu hoặc gián đoạn. Ngược lại, không cần giữ một suite đắt đỏ nếu nó không tạo thêm bằng chứng có giá trị và có phương án kiểm tra phù hợp hơn.

### 8.4. Tính ổn định và độ tin cậy

Kiểm tra flaky rate, test bị skip, môi trường không sẵn sàng, dữ liệu dùng chung và kết quả inconclusive. Một chiến lược dựa trên test không ổn định có thể khiến nhóm bỏ qua cảnh báo hoặc mất niềm tin vào quality gate.

## 9. Điều phối phiên review

Phiên review cần có người điều phối, cách ghi quyết định và quy tắc xử lý bất đồng.

### 9.1. Vai trò

- **Facilitator**: giữ phạm vi, điều phối lượt trao đổi và làm rõ câu hỏi.
- **Business representative**: xác nhận mục tiêu, hành trình và tác động.
- **Development representative**: giải thích kiến trúc, thay đổi và khả năng kiểm thử.
- **Operations representative**: cung cấp dữ liệu production, SLO và điều kiện vận hành.
- **QA/test lead**: kết nối rủi ro với chiến lược và bằng chứng.
- **Decision owner**: đưa ra hoặc phê duyệt quyết định trong thẩm quyền.
- **Recorder**: ghi nhận phát hiện, quyết định, action và owner.

Một người có thể giữ nhiều vai trò trong nhóm nhỏ, nhưng cần làm rõ ai có quyền quyết định cuối cùng.

### 9.2. Agenda tham khảo

| Thời lượng | Nội dung | Đầu ra |
|---|---|---|
| 5–10 phút | Mục tiêu, trigger và phạm vi | Thống nhất câu hỏi review. |
| 10–15 phút | Mục tiêu và rủi ro nghiệp vụ | Hành trình và hậu quả ưu tiên. |
| 10–15 phút | Kiến trúc và khả năng kiểm thử | Dependency, contract và khoảng trống kỹ thuật. |
| 10–15 phút | Vận hành và dữ liệu production | SLO, incident, monitoring và recovery gap. |
| 10–15 phút | Đối chiếu chiến lược hiện tại | Giữ, sửa, bổ sung hoặc loại bỏ kiểm soát. |
| 10 phút | Quyết định và hành động | Owner, deadline, evidence và risk acceptance. |

Thời lượng là ví dụ; review phức tạp có thể cần nhiều phiên làm việc.

### 9.3. Cách thảo luận

- Bắt đầu từ dữ kiện và câu hỏi, không từ giải pháp đã chọn sẵn.
- Mỗi bên nêu điều mình biết, giả định và điều chưa biết.
- Yêu cầu ví dụ hoặc bằng chứng khi có nhận định mâu thuẫn.
- Ghi riêng vấn đề cần quyết định và vấn đề cần điều tra thêm.
- Không để một vai trò chiếm toàn bộ thời gian.
- Kết thúc mỗi chủ đề bằng kết luận, owner hoặc bước tiếp theo.

### 9.4. Xử lý bất đồng

Khi các bên không thống nhất:

1. Làm rõ mục tiêu chung và hậu quả cần tránh.
2. Phân biệt dữ kiện với giả định.
3. Xác định tiêu chí hoặc chính sách có thẩm quyền.
4. So sánh các phương án và đánh đổi.
5. Thử nghiệm hoặc thu thập dữ liệu nếu có thể.
6. Giao người có thẩm quyền quyết định và ghi rủi ro còn lại.

Không cần ép mọi người đồng ý về mọi chi tiết. Điều quan trọng là quyết định, lý do, giới hạn và trách nhiệm được ghi nhận.

## 10. Đánh giá và cập nhật chiến lược sau review

Sau phiên review, cần biến phát hiện thành thay đổi cụ thể.

### 10.1. Phân loại kết quả

Mỗi nội dung có thể được phân loại:

- Giữ nguyên: chiến lược hiện tại vẫn phù hợp, có bằng chứng hỗ trợ.
- Sửa đổi: mục tiêu, phạm vi, ngưỡng hoặc cách thực hiện cần cập nhật.
- Bổ sung: cần thêm test, dữ liệu, môi trường, monitoring hoặc vai trò.
- Loại bỏ: kiểm soát không còn liên quan hoặc không tạo giá trị đủ lớn.
- Điều tra thêm: chưa đủ bằng chứng để quyết định.
- Chấp nhận rủi ro: có người đúng thẩm quyền chấp nhận trong phạm vi và thời hạn rõ.

### 10.2. Cập nhật các thành phần chiến lược

Tùy phát hiện, cập nhật:

- Risk register và impact analysis.
- Test scope, test level và coverage objectives.
- Acceptance criteria và quality criteria.
- Contract, integration và E2E suite.
- Test data, fixture, environment và dependency simulation.
- Automation, CI pipeline, sharding và quality gate.
- Performance, security, resilience và accessibility testing.
- SLI/SLO, dashboard, alert và synthetic monitoring.
- Release checklist, rollback, runbook và incident response.
- Ownership, skill matrix và kế hoạch chuyển giao.

### 10.3. Kiểm tra tính nhất quán

Một thay đổi chiến lược có thể ảnh hưởng đến nhiều tài liệu hoặc pipeline. Ví dụ, đổi tiêu chí latency cần cập nhật test workload, ngưỡng báo cáo, dashboard và release gate. Nếu chỉ cập nhật một nơi, nhóm có thể có nhiều định nghĩa khác nhau.

### 10.4. Quản lý phiên bản và hiệu lực

Ghi phiên bản chiến lược, ngày hiệu lực, phạm vi áp dụng, lý do thay đổi và người phê duyệt. Khi có release đang chạy theo chiến lược cũ, cần xác định giai đoạn chuyển tiếp và cách xử lý bằng chứng đã tạo trước đó.

## 11. Ma trận review chiến lược ba góc nhìn

Ma trận sau có thể dùng trong workshop để kiểm tra những chủ đề quan trọng.

| Chủ đề | Nghiệp vụ cần xác nhận | Phát triển cần xác nhận | Vận hành cần xác nhận | Bằng chứng/đầu ra |
|---|---|---|---|---|
| Hành trình chính | Kết quả và mức tác động | Service/state/contract tham gia | SLI, alert và recovery | E2E đại diện, business metric. |
| Dữ liệu | Quy tắc và bất biến | Schema, transaction, migration | Backup, restore, reconciliation | Data test, migration report. |
| Tích hợp | Quy tắc với đối tác | API/event contract, retry | Quota, network, dependency health | Contract/integration test. |
| Hiệu năng | Kỳ vọng trải nghiệm | Query, concurrency, resource use | Capacity, saturation, autoscaling | Load test, SLI/SLO. |
| Bảo mật | Nghĩa vụ và tác động | Auth, authorization, secure design | Monitoring, access, incident response | Security test, audit evidence. |
| Phát hành | Phạm vi và thời điểm | Build, test, compatibility | Canary, rollback, on-call | Release package, smoke, rollout report. |
| Sự cố | Tác động và ưu tiên | Cơ chế lỗi và regression | Detection, containment, recovery | Incident review, action verification. |
| Năng lực | Mức hỗ trợ cần thiết | Testability và ownership | Runbook và người trực | Skill matrix, rehearsal. |

Có thể bổ sung cột “trạng thái hiện tại”, “khoảng trống”, “mức rủi ro”, “owner” và “deadline” để biến ma trận thành action tracker.

## 12. Ví dụ xuyên suốt: review chiến lược trước khi mở rộng dịch vụ đặt hàng

Giả sử một sản phẩm đặt hàng nội bộ chuẩn bị mở cho nhiều khách hàng bên ngoài. Kiến trúc hiện tại gồm Order, Payment, Inventory và Notification services. Traffic dự kiến tăng, có thêm tenant, đối tác thanh toán mới và cam kết dịch vụ cao hơn.

### 12.1. Góc nhìn nghiệp vụ

Nhóm nghiệp vụ xác định:

- Đặt hàng và thanh toán là hành trình cốt lõi.
- Không được ghi nhận thanh toán trùng hoặc lộ dữ liệu giữa tenant.
- Người dùng cần thấy trạng thái đơn và thanh toán rõ ràng.
- Tải cao điểm xảy ra trong các chiến dịch.
- Đối tác cần API ổn định và thông báo thay đổi trước.

### 12.2. Góc nhìn phát triển

Nhóm phát triển xác định:

- Payment callback có thể lặp hoặc đến trễ.
- Order và Inventory xử lý event bất đồng bộ.
- Consumer có thể chạy phiên bản cũ trong rolling deployment.
- Cần contract test cho provider/consumer và schema event.
- Test data phải phân tách tenant và hỗ trợ giao dịch trạng thái đặc biệt.
- E2E hiện tại quá ít để kiểm tra failure path, nhưng quá chậm để chạy trên mọi commit.

### 12.3. Góc nhìn vận hành

Nhóm vận hành xác định:

- Chưa có metric trực tiếp cho giao dịch trùng và thời gian hoàn tất đơn.
- Queue lag tăng khi provider phản hồi chậm.
- Rollback adapter có thể cần tương thích với dữ liệu đã ghi.
- Cần canary theo tenant hoặc tỷ lệ traffic.
- Runbook đối soát và xử lý payment pending chưa được diễn tập.

### 12.4. Quyết định chiến lược

| Phát hiện | Thay đổi chiến lược | Owner đề xuất |
|---|---|---|
| Rủi ro callback lặp/trễ | Thêm unit/component và integration test idempotency, retry, ordering | Payment team + QA. |
| Consumer version cũ | Thêm contract/version matrix và test rolling deployment | Provider/consumer owners. |
| Cách ly tenant | Thêm security/data isolation test ở service và E2E đại diện | Service owners + security. |
| Không đo được kết quả cuối | Thêm business SLI cho order/payment completion và duplicate transaction | Product + SRE. |
| Queue lag chưa có runbook | Thêm alert, dashboard và diễn tập xử lý backlog | Operations/platform. |
| E2E quá chậm | Chuyển kiểm tra logic chi tiết xuống cấp thấp, giữ E2E cho hành trình quan trọng | QA + development. |
| Rollback chưa được kiểm chứng | Thêm rehearsal cho rollout, migration và phục hồi dữ liệu | Release owner + operations. |

### 12.5. Bằng chứng xác nhận sau review

Chiến lược cập nhật cần chỉ rõ test nào chạy trên mỗi commit, test nào chạy khi contract thay đổi, test nào bắt buộc trước release và tín hiệu nào theo dõi sau rollout. Mỗi hành động có owner, deadline và tiêu chí xác minh. Chỉ khi các kiểm soát được triển khai và kiểm tra trong điều kiện phù hợp, nhóm mới có thể kết luận khoảng trống đã được xử lý.

## 13. Đo hiệu quả của hoạt động review

Review có giá trị khi tạo ra thay đổi hữu ích và làm giảm rủi ro hoặc tăng chất lượng bằng chứng.

### 13.1. Chỉ số về chất lượng review

- Tỷ lệ review có đại diện của các vai trò cần thiết.
- Tỷ lệ phát hiện được liên kết với bằng chứng hoặc rủi ro cụ thể.
- Tỷ lệ quyết định có owner và deadline.
- Tỷ lệ hành động được hoàn thành và xác minh hiệu quả.
- Thời gian từ trigger đến khi chiến lược được cập nhật.
- Số vấn đề chưa giải quyết hoặc ngoại lệ quá hạn.

### 13.2. Chỉ số về chiến lược sau cập nhật

- Tỷ lệ rủi ro trọng yếu có bằng chứng kiểm thử hoặc vận hành.
- Tỷ lệ hành trình quan trọng có coverage phù hợp.
- Flaky rate và thời gian pipeline.
- Tỷ lệ lỗi lọt hoặc incident tái diễn.
- MTTD/MTTR theo định nghĩa nhất quán.
- Tỷ lệ release bị chờ vì thiếu bằng chứng hoặc owner.
- Chi phí kiểm thử so với mức giảm rủi ro.

### 13.3. Đánh giá định tính

Hỏi các nhóm:

- Chiến lược mới có dễ hiểu và dễ thực hiện không?
- Trách nhiệm ở ranh giới đã rõ hơn chưa?
- Bằng chứng có giúp quyết định phát hành nhanh và tự tin hơn không?
- Có kiểm soát nào gây gánh nặng mà không tạo giá trị tương xứng không?
- Sự cố hoặc phản hồi mới có được chuyển thành cải tiến không?

### 13.4. Không tối ưu chỉ số riêng lẻ

Tăng số test có thể làm pipeline chậm mà không giảm rủi ro. Giảm thời gian pipeline có thể do bỏ qua test. Giảm số incident có thể do telemetry thiếu. Hãy xem các chỉ số cùng nhau và đối chiếu với bằng chứng thực tế.

## 14. Hồ sơ review và action tracker

Một hồ sơ review có thể gồm:

| Trường | Nội dung |
|---|---|
| Review ID | Mã phiên review hoặc change request. |
| Trigger | Sự kiện kích hoạt review. |
| Scope | Sản phẩm, service, hành trình và thuộc tính chất lượng. |
| Participants | Đại diện nghiệp vụ, phát triển, vận hành, QA và bên liên quan. |
| Inputs | Tài liệu, metric, incident, test report và kiến trúc đã xem. |
| Findings | Khoảng trống, rủi ro, giả định và điểm mạnh đã xác minh. |
| Decision | Giữ, sửa, bổ sung, loại bỏ, điều tra hoặc chấp nhận rủi ro. |
| Strategy version | Phiên bản chiến lược trước/sau. |
| Action owner | Người chịu trách nhiệm từng hành động. |
| Due date | Thời hạn và mốc kiểm tra. |
| Evidence | Test, dashboard, runbook, PR, rehearsal hoặc report. |
| Risk acceptance | Người phê duyệt, phạm vi và thời hạn ngoại lệ. |
| Follow-up | Ngày đánh giá hiệu quả và trigger review tiếp theo. |

### 14.1. Mẫu mô tả hành động

> **Khoảng trống:** [bằng chứng hoặc kiểm soát còn thiếu].
>
> **Rủi ro:** [hậu quả và phạm vi nếu không xử lý].
>
> **Hành động:** [thay đổi cụ thể trong test, code, quy trình hoặc vận hành].
>
> **Owner/deadline:** [vai trò chịu trách nhiệm và thời hạn].
>
> **Bằng chứng hoàn thành:** [report, test, dashboard, runbook hoặc diễn tập].
>
> **Tiêu chí hiệu quả:** [điều kiện chứng minh rủi ro giảm].

Không đóng action chỉ vì đã tạo ticket hoặc tổ chức cuộc họp. Cần bằng chứng rằng thay đổi đã được thực hiện và có hiệu quả theo tiêu chí đã thống nhất.

## 15. Những sai lầm thường gặp khi review chiến lược

- **Chỉ mời QA review**: bỏ qua mục tiêu nghiệp vụ và điều kiện production. Hãy có đại diện phù hợp của business, development và operations.
- **Review tài liệu mà không xem dữ liệu**: quyết định dựa trên giả định cũ. Hãy dùng incident, metric, test result và phản hồi thực tế.
- **Biến review thành buổi báo cáo trạng thái**: không tìm khoảng trống hoặc đưa ra quyết định. Hãy đặt câu hỏi và kiểm tra bằng chứng.
- **Không xác định phạm vi**: thảo luận lan rộng và không hoàn tất. Hãy nêu trigger, câu hỏi và đầu ra trước phiên.
- **Để một góc nhìn chi phối**: ưu tiên cục bộ làm giảm chất lượng tổng thể. Hãy liên kết tác động nghiệp vụ, kỹ thuật và vận hành.
- **Đồng nhất coverage với chất lượng**: bỏ sót assertion, contract và hành trình. Hãy đánh giá bằng chứng theo rủi ro.
- **Không xử lý đánh đổi**: các nhóm rời cuộc họp với giả định khác nhau. Hãy ghi quyết định, lý do và người có thẩm quyền.
- **Giao action chung chung**: không thể xác minh hoàn thành. Hãy nêu thay đổi, owner, deadline và evidence.
- **Không theo dõi action**: khoảng trống vẫn tồn tại sau review. Hãy có action tracker và follow-up.
- **Chỉ đo số test hoặc số cuộc họp**: không biết chất lượng chiến lược có cải thiện không. Hãy đo lỗi lọt, độ phủ rủi ro, pipeline và khả năng phục hồi.
- **Không cập nhật chiến lược sau incident**: bài học không quay lại quy trình kiểm thử. Hãy chuyển phát hiện thành test, tiêu chí, monitoring hoặc runbook.
- **Không version hóa quyết định**: khó biết release nào áp dụng quy tắc nào. Hãy ghi phiên bản, ngày hiệu lực và giai đoạn chuyển tiếp.
- **Coi mọi bất đồng là cần đạt đồng thuận tuyệt đối**: review bị kéo dài. Hãy phân biệt vấn đề cần thêm bằng chứng với quyết định thuộc thẩm quyền cụ thể.

## 16. Quy trình thực hành rà soát chiến lược

Nhóm có thể áp dụng trình tự sau:

1. **Xác định trigger và phạm vi**: nêu thay đổi, câu hỏi review và đầu ra mong đợi.
2. **Chuẩn bị bằng chứng**: thu thập mục tiêu, rủi ro, kiến trúc, test report, incident, SLO và kế hoạch release.
3. **Nghe góc nhìn nghiệp vụ**: xác nhận hành trình, quy tắc, tác động và mức chấp nhận rủi ro.
4. **Nghe góc nhìn phát triển**: kiểm tra dependency, contract, testability, automation và tính khả thi.
5. **Nghe góc nhìn vận hành**: kiểm tra telemetry, SLO, rollout, capacity, recovery và support.
6. **Đối chiếu chiến lược hiện tại**: xác định phần phù hợp, khoảng trống, trùng lặp và kiểm soát lỗi thời.
7. **Đánh giá đánh đổi**: so sánh rủi ro, chi phí, thời gian phản hồi và khả năng thực thi.
8. **Đưa ra quyết định**: giữ, sửa, bổ sung, loại bỏ, điều tra hoặc chấp nhận rủi ro.
9. **Giao hành động**: chỉ định owner, deadline, dependency và tiêu chí hiệu quả.
10. **Cập nhật tài liệu và pipeline**: version hóa chiến lược, test, dữ liệu, môi trường, monitoring và gate liên quan.
11. **Xác minh sau áp dụng**: kiểm tra bằng chứng mới và theo dõi chỉ số trong điều kiện thực tế.
12. **Đặt trigger review tiếp theo**: xác định thời điểm hoặc thay đổi sẽ kích hoạt lần rà soát tiếp.

## 17. Tự kiểm tra

Trước khi kết thúc một phiên review chiến lược, hãy tự hỏi:

- Trigger, mục tiêu và phạm vi review đã rõ chưa?
- Có bằng chứng hiện tại từ nghiệp vụ, phát triển và vận hành không?
- Hành trình và quy tắc nghiệp vụ quan trọng đã được xác định chưa?
- Kiến trúc, contract, dependency và testability đã được xem xét chưa?
- SLI/SLO, monitoring, rollout, rollback và recovery đã được xem xét chưa?
- Chiến lược có phân bổ bằng chứng ở cấp service, contract, integration và E2E phù hợp không?
- Test data, môi trường, nguồn lực và chi phí có đủ để thực hiện không?
- Những khác biệt hoặc xung đột đã được giải quyết bằng dữ kiện và thẩm quyền phù hợp chưa?
- Mỗi khoảng trống có rủi ro, owner, deadline và bằng chứng hoàn thành không?
- Các ngoại lệ có người chấp nhận, phạm vi và thời hạn rõ không?
- Chiến lược, pipeline, monitoring và runbook đã được cập nhật nhất quán chưa?
- Có cách xác minh hiệu quả sau khi áp dụng không?
- Đã ghi phiên bản, quyết định và trigger review tiếp theo chưa?

## Kết luận

Rà soát chiến lược kiểm thử với góc nhìn nghiệp vụ, phát triển và vận hành giúp kiểm tra toàn bộ chuỗi từ giá trị người dùng đến kiến trúc, bằng chứng kỹ thuật và khả năng vận hành production. Nghiệp vụ xác định điều quan trọng và hậu quả khi sai; phát triển đánh giá cách xây dựng, tích hợp và kiểm thử; vận hành xác nhận khả năng quan sát, triển khai, phục hồi và hỗ trợ. Khi các góc nhìn được kết nối bằng dữ liệu, rủi ro, quyết định và hành động có owner, chiến lược sẽ khả thi hơn và phản ánh đúng điều kiện thực tế. Review chỉ hoàn tất về mặt cải tiến khi thay đổi được áp dụng, bằng chứng được xác minh và kết quả được theo dõi qua các lần phát hành tiếp theo.
