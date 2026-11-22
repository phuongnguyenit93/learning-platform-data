# Chất lượng mã là trách nhiệm chung với phạm vi sở hữu rõ ràng

## Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Giải thích vì sao **chất lượng mã là trách nhiệm chung** của những người tham gia tạo, thay đổi, kiểm thử, triển khai và vận hành phần mềm.
2. Phân biệt **trách nhiệm chung** với **trách nhiệm không có chủ sở hữu**; xác định ai chịu trách nhiệm cuối cùng cho từng quyết định và từng ranh giới kỹ thuật.
3. Xác định phạm vi sở hữu theo **module, domain, service, API, dữ liệu và khả năng vận hành**, thay vì chỉ dựa vào tên file hoặc chức danh.
4. Phân vai hợp lý giữa developer, reviewer, tech lead, QA, platform/SRE, security, product và người vận hành mà không đẩy toàn bộ chất lượng sang một nhóm.
5. Thiết kế cách cộng tác qua code review, Definition of Done, CODEOWNERS, test strategy, incident review và quản lý thay đổi liên nhóm.
6. Xử lý những tình huống có nhiều nhóm cùng chạm vào một hợp đồng bằng cách xác định owner, người cần tham vấn, bằng chứng và quy trình quyết định rõ ràng.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta học những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi hay không**. Những thuộc tính này không hình thành chỉ nhờ một lập trình viên viết code tốt. Chúng phụ thuộc vào quyết định của nhiều vai trò: người hiểu nghiệp vụ, người thiết kế giải pháp, người viết và review code, người kiểm thử, người quản lý hạ tầng, người bảo vệ an toàn và người theo dõi hệ thống sau triển khai.

**Chất lượng là trách nhiệm chung, nhưng mỗi quyết định vẫn cần một phạm vi sở hữu rõ ràng.** Nếu nói “mọi người cùng chịu trách nhiệm” mà không chỉ ra ai quyết định, ai thực hiện, ai kiểm chứng và ai xử lý khi có vấn đề, trách nhiệm có thể bị phân tán đến mức không ai hành động.

## 1. Vì sao chất lượng mã không thuộc riêng developer hoặc QA?

Một tính năng có thể được viết đúng theo yêu cầu nhưng vẫn gây lỗi trong sản xuất nếu:
- Yêu cầu nghiệp vụ mơ hồ hoặc bỏ sót trường hợp biên.
- Thiết kế không xét đến tính đồng thời, dữ liệu cũ hoặc lỗi của dịch vụ phụ thuộc.
- Code không có test cho hợp đồng quan trọng.
- Review chỉ kiểm tra style mà bỏ qua quyền truy cập hoặc tác dụng phụ.
- Pipeline không chạy kiểm tra cần thiết.
- Cấu hình triển khai khác môi trường kiểm thử.
- Không ai theo dõi metric hoặc chịu trách nhiệm xử lý sau release.

Chất lượng được tạo ra qua **toàn bộ vòng đời thay đổi**, không chỉ ở thời điểm viết mã.

### Ví dụ: một thay đổi tính phí vận chuyển

Giả sử sản phẩm thay ngưỡng miễn phí vận chuyển từ 500.000 lên 700.000 VND.

- **Product/business** xác nhận chính sách mới, ngày hiệu lực và cách xử lý đơn đã tạo.
- **Developer** xác định các luồng tính phí, cập nhật policy và bảo vệ bất biến.
- **Reviewer/domain owner** kiểm tra hợp đồng nghiệp vụ, trường hợp biên và ảnh hưởng tới caller.
- **QA** giúp xây dựng kịch bản kiểm thử cho preview, checkout, đơn hủy và lịch sử.
- **Platform/CI owner** bảo đảm pipeline chạy đúng bộ test và tạo artifact có thể truy nguyên.
- **SRE/operations** xác nhận metric, log, alert và kế hoạch rollback khi triển khai.
- **Finance/support** có thể cần xác nhận cách đối soát hoặc giải thích hóa đơn đã phát hành.

Không vai trò nào tự mình bảo đảm mọi thuộc tính. Nếu developer chỉ cập nhật checkout mà không ai chịu trách nhiệm về preview, hóa đơn hoặc dữ liệu lịch sử, hệ thống có thể có kết quả không nhất quán dù từng phần code đều biên dịch.

### Các thuộc tính chất lượng liên quan đến nhiều vai trò

| Thuộc tính | Quyết định có thể ảnh hưởng | Vai trò thường tham gia |
| --- | --- | --- |
| **Correctness** | Quy tắc, dữ liệu, trường hợp biên, invariant | Product/domain expert, developer, reviewer, QA |
| **Reliability** | Timeout, retry, transaction, phục hồi | Developer, reviewer, SRE/operations |
| **Security** | Authentication, authorization, secret, dữ liệu nhạy cảm | Developer, security, domain owner, operations |
| **Maintainability** | Ranh giới module, tên, phụ thuộc, test | Developer, reviewer, tech lead, architecture/domain owner |
| **Performance** | Workload, query, cache, giới hạn tài nguyên | Developer, platform, SRE, product |
| **Compatibility** | API, event, schema, client cũ | API owner, producer/consumer teams, QA |
| **Usability** | Thông báo lỗi, hành vi giao diện, quy trình hỗ trợ | Product, design, developer, support |
| **Operability** | Dashboard, alert, runbook, rollback | Service owner, SRE/operations, developer |

Danh sách vai trò là ví dụ. Một tổ chức nhỏ có thể để một người đảm nhiệm nhiều vai trò; điều quan trọng là **năng lực và quyết định cần thiết vẫn có người chịu trách nhiệm**.

## 2. Trách nhiệm chung không có nghĩa mọi người chịu trách nhiệm cho mọi thứ

Câu “chất lượng là việc của tất cả mọi người” dễ bị hiểu thành mỗi người có thể giả định người khác sẽ kiểm tra. Khi xảy ra lỗi, nhóm bắt đầu hỏi:
- Ai chịu trách nhiệm cho hợp đồng API?
- Ai phải kiểm tra migration?
- Ai quyết định mức rủi ro có thể chấp nhận?
- Ai xem alert sau release?
- Ai có quyền phê duyệt ngoại lệ?
- Ai duy trì test đang flake?

Nếu không có câu trả lời, chất lượng đang dựa vào trí nhớ và thiện chí cá nhân.

Một mô hình hữu ích là phân biệt:

- **Trách nhiệm thực hiện (Responsible):** người trực tiếp làm công việc.
- **Trách nhiệm giải trình/quyết định (Accountable):** người chịu trách nhiệm cuối cùng về kết quả trong phạm vi được giao.
- **Được tham vấn (Consulted):** người cung cấp chuyên môn hoặc ảnh hưởng tới quyết định.
- **Được thông báo (Informed):** người cần biết kết quả hoặc thay đổi.

Đây là cách diễn giải phổ biến của mô hình **RACI**. Mỗi tổ chức có thể dùng cách phân vai khác, nhưng cần tránh một việc có nhiều người được coi là “accountable cuối cùng” mà không rõ ai có quyền quyết định khi bất đồng.

### Trách nhiệm chung và ownership cụ thể

| Phát biểu | Vấn đề hoặc giá trị |
| --- | --- |
| “Ai cũng phải quan tâm chất lượng.” | Đúng về văn hóa, nhưng chưa xác định hành động |
| “Developer viết test cho logic mình thay đổi.” | Trách nhiệm thực hiện rõ |
| “Owner của Order API quyết định contract và tương thích.” | Phạm vi quyết định rõ |
| “Security được tham vấn khi thay đổi quyền hoặc dữ liệu nhạy cảm.” | Chuyên môn được tham gia đúng lúc |
| “Service owner theo dõi alert và điều phối phản ứng.” | Có người chịu trách nhiệm vận hành |
| “QA sẽ tìm mọi bug trước release.” | Đẩy trách nhiệm đúng đắn sang một vai trò và tạo cảm giác an toàn giả |

**QA không thể kiểm thử thay cho developer mọi trường hợp, reviewer không thể đọc thay mọi dòng code, và SRE không thể vận hành an toàn một dịch vụ mà không có thông tin từ người xây dựng nó.** Mỗi vai trò góp phần vào chất lượng ở ranh giới mà họ có chuyên môn và quyền hành động.

## 3. Xác định phạm vi sở hữu theo ranh giới thực

Sở hữu code không chỉ là “ai viết file này”. Một thành phần có thể được nhiều người sửa, nhưng cần biết ai hiểu và duy trì **hợp đồng, dữ liệu và vận hành** của nó.

### Các loại ranh giới sở hữu

1. **Domain ownership:** ai hiểu và duy trì quy tắc nghiệp vụ, thuật ngữ và invariant?
2. **Code ownership:** ai chịu trách nhiệm cho package, module hoặc repository?
3. **API ownership:** ai quyết định schema, version, lỗi và tương thích?
4. **Data ownership:** ai quyết định nguồn dữ liệu chính thức, quyền truy cập, retention và migration?
5. **Operational ownership:** ai theo dõi sức khỏe dịch vụ, alert, capacity và incident?
6. **Security ownership:** ai xác nhận threat model, quyền, secret và biện pháp kiểm soát?
7. **Platform ownership:** ai duy trì CI, build system, deployment tooling và shared infrastructure?

Những ranh giới này có thể thuộc cùng một nhóm hoặc nhiều nhóm khác nhau. Cần công bố cách phối hợp khi chúng giao nhau.

### Ví dụ: Order Service

Giả sử Order Service gồm API, logic đơn hàng, repository và worker xử lý sự kiện.

~~~mermaid
flowchart TD
    A[Product / Domain] --> B[Order contract and rules]
    B --> C[Order service team]
    C --> D[API and application logic]
    C --> E[Data access and events]
    F[Security] --> D
    G[Platform / SRE] --> H[CI, deployment, observability]
    H --> C
    I[Consumer teams] --> B
    J[QA / Test engineering] --> C
~~~

Sơ đồ thể hiện quan hệ cộng tác, không phải sơ đồ tổ chức bắt buộc. Team Order có thể sở hữu hành vi và vận hành của service; consumer teams được tham vấn khi contract thay đổi; platform hỗ trợ hạ tầng; security tham gia vào rủi ro tương ứng.

### Dấu hiệu phạm vi sở hữu chưa rõ

- Nhiều nhóm cùng sửa một schema nhưng không ai quyết định version.
- Một thư viện chung bị thay đổi mà các consumer không được thông báo.
- Alert phát sinh nhưng nhóm phát triển nghĩ đó là việc của operations.
- Nhóm vận hành không biết service cần bao nhiêu thời gian để khôi phục.
- Test contract thất bại nhưng không biết producer hay consumer phải sửa.
- Một package có CODEOWNERS nhưng owner không còn hoạt động hoặc không có quyền quyết định.
- Mỗi nhóm dùng một định nghĩa khác nhau cho cùng trạng thái nghiệp vụ.

Khi gặp những dấu hiệu này, giải pháp đầu tiên thường là **làm rõ ranh giới và hợp đồng**, không phải lập thêm một cuộc họp chung cho mọi thay đổi.

## 4. Vai trò của developer: chịu trách nhiệm cho thay đổi mình tạo ra

Developer có trách nhiệm chất lượng ngay từ lúc hiểu yêu cầu và thiết kế thay đổi, không chỉ sau khi code review.

Các việc quan trọng:
- Làm rõ đầu vào, đầu ra, trường hợp biên và hành vi lỗi.
- Xác định module và owner bị ảnh hưởng.
- Chọn cấu trúc giúp thể hiện rõ ý định và bảo vệ invariant.
- Viết test ở tầng phù hợp cho logic và hợp đồng thay đổi.
- Xử lý cảnh báo và lỗi phát hiện được trong phạm vi.
- Cập nhật tài liệu, migration và observability khi thay đổi đòi hỏi.
- Mô tả rủi ro, giới hạn và cách kiểm chứng trong pull request.
- Theo dõi thay đổi sau triển khai theo quy trình của service.

### Developer không chỉ “hoàn thành ticket”

Một ticket có thể nói “thêm endpoint hủy đơn”. Một thay đổi có trách nhiệm cần làm rõ:
- Ai có quyền hủy?
- Đơn ở trạng thái nào được hủy?
- Hủy có hoàn tiền hoặc giải phóng tồn kho không?
- Request lặp lại có an toàn không?
- Event nào được phát và khi nào?
- API trả kết quả thế nào nếu thao tác đang chạy?
- Có client cũ phụ thuộc vào mã lỗi không?

Nếu những câu hỏi này chưa được trả lời, developer nên đưa chúng ra để quyết định với domain owner/product thay vì tự đoán rồi đẩy rủi ro cho reviewer.

### Trách nhiệm sau khi mở PR

Tác giả nên:
- Cung cấp bối cảnh và lý do thay đổi.
- Phản hồi review bằng bằng chứng.
- Không dismiss cảnh báo chỉ vì test hiện tại xanh.
- Cập nhật test khi phát hiện trường hợp bị bỏ sót.
- Thông báo khi phạm vi hoặc hợp đồng thay đổi.
- Hỗ trợ theo dõi lỗi liên quan sau triển khai theo thỏa thuận ownership.

Điều đó không có nghĩa tác giả phải chịu trách nhiệm cá nhân cho mọi sự cố. Chất lượng là trách nhiệm của hệ thống và nhóm; mục tiêu là **học và xử lý nguyên nhân**, không tìm người để đổ lỗi.

## 5. Vai trò của reviewer: kiểm tra quyết định và rủi ro

Code review không phải cuộc thi tìm lỗi chính tả hoặc chứng minh reviewer biết nhiều hơn tác giả. Review là cơ chế chia sẻ hiểu biết và kiểm tra những quyết định có thể ảnh hưởng tới người dùng, module khác hoặc khả năng bảo trì.

Reviewer nên xem:
- Thay đổi có giải quyết đúng yêu cầu không?
- Tên và cấu trúc có diễn đạt đúng trách nhiệm không?
- Có thay đổi API, dữ liệu, transaction, quyền hoặc tác dụng phụ không?
- Test có kiểm tra hành vi quan trọng và trường hợp lỗi không?
- Có phụ thuộc mới, vòng phụ thuộc hoặc coupling không cần thiết không?
- Có migration, rollback, logging hoặc metric cần thiết không?
- Phạm vi thay đổi có lớn hơn mục tiêu mà không có lý do không?

### Review theo rủi ro

Không cần áp cùng độ sâu review cho mọi thay đổi.

| Loại thay đổi | Trọng tâm review |
| --- | --- |
| Đổi tên biến cục bộ | Ý nghĩa, consistency, không thay hành vi |
| Sửa logic tính tiền | Đơn vị, làm tròn, biên, invariant, test |
| Thay đổi authorization | Chủ thể, hành động, tài nguyên, đường truy cập phụ |
| Đổi schema/API | Tương thích, consumer, version, migration |
| Thay transaction/concurrency | Atomicity, idempotency, lock, retry, rollback |
| Tối ưu hot path | Workload, p95/p99, memory, query, error rate |
| Thay pipeline/deployment | Artifact, secret, quyền triển khai, rollout, rollback |

### Review comment nên giúp người viết hành động

Một nhận xét hữu ích:

> “Nếu hai request cùng hủy một đơn, cả hai có thể đọc trạng thái ACTIVE trước khi cập nhật. Hợp đồng có yêu cầu chỉ một request thành công không? Hãy kiểm tra cập nhật có điều kiện hoặc transaction và thêm test đồng thời phù hợp.”

Một nhận xét ít hữu ích:

> “Code này không tốt. Viết lại đi.”

Review comment nên phân biệt:
- **Blocker:** có lỗi hoặc rủi ro cần xử lý trước khi merge.
- **Suggestion:** phương án cải thiện có thể cân nhắc.
- **Question:** điểm chưa rõ cần tác giả giải thích.
- **Nit:** chi tiết nhỏ không ảnh hưởng quyết định lớn.

Nếu tổ chức dùng nhãn khác, điều quan trọng là mọi người hiểu mức độ bắt buộc và cách giải quyết bất đồng.

## 6. Vai trò của QA và test engineering: xây dựng chiến lược kiểm chứng

QA không phải “người nhận code ở cuối dây chuyền rồi tìm mọi lỗi”. Vai trò có giá trị hơn khi tham gia sớm để giúp nhóm xác định **rủi ro nào cần kiểm thử, ở tầng nào và bằng bằng chứng gì**.

QA/test engineering có thể:
- Phân tích yêu cầu và tìm tình huống biên.
- Xây dựng test strategy theo rủi ro.
- Thiết kế test dữ liệu, contract và integration.
- Xác định test flakiness và độ ổn định môi trường.
- Kiểm tra tính đầy đủ của test theo hành vi, không chỉ coverage.
- Hỗ trợ kiểm thử exploratory cho luồng phức tạp.
- Phân tích lỗi tái hiện và cải thiện khả năng kiểm chứng.
- Hỗ trợ nhóm thiết lập quality gate đáng tin cậy.

### Developer và QA cùng sở hữu chất lượng test

Ví dụ với API đặt hàng:
- Developer viết unit test cho policy tính giá và validation.
- QA giúp thiết kế ma trận đầu vào, trạng thái và kết quả.
- Developer và QA cùng xác nhận test tích hợp qua HTTP.
- Service owner xác nhận metric và hành vi sau triển khai.
- Product/domain owner xác nhận expected behavior.

Nếu developer giao toàn bộ test cho QA, lỗi có thể được phát hiện muộn và test khó cô lập. Nếu QA chỉ kiểm tra đúng kịch bản do developer cung cấp, những giả định bị bỏ sót có thể không được phát hiện.

### Chọn tầng test theo câu hỏi

| Câu hỏi | Tầng test thường phù hợp |
| --- | --- |
| Công thức có tính đúng ở các biên không? | Unit test |
| API có mapping và trả lỗi đúng không? | API/integration test |
| Producer và consumer hiểu cùng schema không? | Contract test |
| Transaction và constraint có hoạt động trên DB thật không? | Integration test với database |
| Hệ thống chịu được tải mục tiêu không? | Load/stress test |
| Người dùng có hoàn thành quy trình không? | End-to-end/usability test |
| Hệ thống có phục hồi sau lỗi phụ thuộc không? | Resilience/failure test |

Không phải mọi thay đổi cần tất cả các tầng. Nhóm chọn theo **rủi ro và ranh giới bị tác động**, tránh cả thiếu kiểm thử lẫn một bộ E2E quá lớn, chậm và khó chẩn đoán.

## 7. Vai trò của tech lead và domain owner

**Tech lead** thường giúp nhóm giữ chất lượng kỹ thuật xuyên qua nhiều thay đổi:
- Làm rõ kiến trúc và ranh giới phụ thuộc.
- Xác định rủi ro kỹ thuật cần tham vấn.
- Hỗ trợ quyết định trade-off.
- Bảo đảm tiêu chuẩn có thể thực hiện và phù hợp với bối cảnh.
- Phát triển năng lực review và thiết kế trong nhóm.
- Điều phối các thay đổi có blast radius lớn.

**Domain owner/product domain expert** chịu trách nhiệm làm rõ ý nghĩa nghiệp vụ:
- Thuật ngữ và trạng thái.
- Quy tắc và ngoại lệ.
- Quyền quyết định và dữ liệu chuẩn.
- Thời điểm hiệu lực.
- Kết quả mong đợi và hậu quả khi sai.

Hai vai trò có thể thuộc cùng một người ở nhóm nhỏ, nhưng hai loại quyết định vẫn khác nhau. Tech lead không nên tự quyết định chính sách hoàn tiền nếu không có thẩm quyền nghiệp vụ; product owner cũng không nên tự quyết định chi tiết transaction mà không có đánh giá kỹ thuật.

### Khi có bất đồng

Ví dụ product muốn triển khai ngay tính năng xóa tài khoản, developer lo dữ liệu lịch sử và nghĩa vụ retention.

Cách xử lý:
1. Product/domain owner xác nhận yêu cầu xóa có ý nghĩa gì với người dùng và quy định áp dụng.
2. Security/legal/privacy chuyên môn được tham vấn khi cần.
3. Developer và tech lead đề xuất mô hình xóa, ẩn danh hoặc retention phù hợp.
4. Data owner xác nhận bảng, bản sao, backup và luồng downstream.
5. Người có thẩm quyền quyết định trade-off và ghi lại.
6. Nhóm triển khai cùng tiêu chí kiểm chứng.

Không nên kết thúc bằng “business yêu cầu nên dev phải làm” hoặc “dev không thích nên không làm”. Quyết định cần có **ngữ cảnh, người có thẩm quyền và bằng chứng**.

## 8. Vai trò của platform/SRE/operations: làm cho phần mềm vận hành được

Một ứng dụng có thể có code đúng nhưng khó vận hành nếu:
- Không có health check phù hợp.
- Không thể truy vết request qua các dịch vụ.
- Alert không có người nhận hoặc quá nhiễu.
- Không có giới hạn timeout/concurrency.
- Không biết rollback hoặc phục hồi dữ liệu thế nào.
- Build artifact không tái lập hoặc không truy nguyên được commit.

Platform/SRE/operations hỗ trợ:
- Nền tảng CI/CD, môi trường và công cụ.
- Observability: logs, metrics, traces.
- Alerting, runbook và quy trình incident.
- Capacity, resource limits, deployment strategy.
- Backup/restore, migration và disaster recovery.
- Guardrail vận hành và reliability practices.

### Developer vẫn sở hữu khả năng vận hành của service

Platform có thể cung cấp logging library và dashboard template, nhưng developer/service team phải:
- Ghi log có ý nghĩa, không lộ dữ liệu nhạy cảm.
- Tạo metric phản ánh trạng thái nghiệp vụ quan trọng.
- Đặt timeout và retry theo hợp đồng phụ thuộc.
- Cung cấp health/readiness semantics đúng.
- Viết runbook cho tình huống đặc thù.
- Tham gia điều tra và sửa nguyên nhân lỗi.

Không nên “ném” dịch vụ sang operations sau release mà không có tài liệu, metric và người hiểu code. Ngược lại, developer không nên tự xây một hệ thống monitoring riêng khi nền tảng đã có cơ chế dùng chung phù hợp.

## 9. Vai trò của security: tích hợp an toàn vào quy trình phát triển

Security không nên chỉ xuất hiện ở bước audit cuối cùng. Các quyết định về quyền, dữ liệu, dependency và ranh giới tin cậy cần được xem xét ngay khi thiết kế.

Security có thể:
- Hỗ trợ threat modeling.
- Xác định dữ liệu nhạy cảm và ranh giới tin cậy.
- Review authentication/authorization.
- Hướng dẫn secret management và cryptography.
- Đánh giá dependency và cấu hình runtime.
- Xác nhận quy trình xử lý vulnerability.
- Tư vấn logging, audit và retention.

Developer/service owner vẫn phải triển khai và kiểm tra biện pháp bảo vệ trong code. Một security review không thay thế việc test quyền ở từng endpoint hoặc service method liên quan.

### Ví dụ: kiểm tra quyền theo tài nguyên

Một API nhận orderId và trả chi tiết đơn. Kiểm tra người dùng đã đăng nhập chưa là chưa đủ; cần xác minh người dùng có quyền xem **đơn cụ thể** đó không.

~~~java
import java.util.Objects;

record UserId(String value) {
    UserId {
        Objects.requireNonNull(value, "value");
        if (value.isBlank()) {
            throw new IllegalArgumentException("user id is required");
        }
    }
}

record OrderId(String value) {
    OrderId {
        Objects.requireNonNull(value, "value");
        if (value.isBlank()) {
            throw new IllegalArgumentException("order id is required");
        }
    }
}

record OrderSummary(OrderId id, UserId ownerId, long totalVnd) {}

interface OrderReader {
    OrderSummary findById(OrderId id);
}

interface OrderAccessPolicy {
    boolean canRead(UserId actor, OrderSummary order);
}

final class OrderQueryService {
    private final OrderReader reader;
    private final OrderAccessPolicy accessPolicy;

    OrderQueryService(
            OrderReader reader, OrderAccessPolicy accessPolicy) {
        this.reader = Objects.requireNonNull(reader);
        this.accessPolicy = Objects.requireNonNull(accessPolicy);
    }

    OrderSummary getOrder(UserId actor, OrderId orderId) {
        Objects.requireNonNull(actor, "actor");
        OrderSummary order = Objects.requireNonNull(
                reader.findById(orderId), "order");
        if (!accessPolicy.canRead(actor, order)) {
            throw new SecurityException("not allowed to read this order");
        }
        return order;
    }
}
~~~

Ví dụ chỉ minh họa ranh giới policy và service. Trong ứng dụng thật, cần xử lý cả trường hợp không tìm thấy, tránh lộ thông tin về sự tồn tại của tài nguyên khi hợp đồng bảo mật yêu cầu, xác minh quyền ở các đường truy cập khác và bảo đảm policy được triển khai đúng.

**Ai sở hữu điều gì?**
- Security hỗ trợ xác định mô hình đe dọa và nguyên tắc kiểm soát.
- Domain/service owner xác nhận quy tắc ai được xem đơn.
- Developer triển khai check tại ranh giới phù hợp.
- QA/developer kiểm thử người được phép và không được phép.
- Operations hỗ trợ audit/alert nếu có truy cập bất thường.

Không có vai trò nào có thể thay thế toàn bộ phần việc của các vai trò còn lại.

## 10. Product và design cũng góp phần vào chất lượng mã

Một yêu cầu không rõ có thể tạo ra code phức tạp và khó bảo trì:
- Trạng thái nghiệp vụ không được định nghĩa.
- Cách xử lý lỗi hoặc retry không thống nhất.
- Ngày hiệu lực của chính sách không rõ.
- Không biết dữ liệu nào là nguồn chuẩn.
- Nhiều stakeholder đưa ra yêu cầu mâu thuẫn.

Product/design góp phần bằng cách:
- Nêu mục tiêu và kết quả người dùng cần.
- Xác định ví dụ và trường hợp ngoại lệ.
- Làm rõ thứ tự ưu tiên khi yêu cầu xung đột.
- Chấp nhận hoặc điều chỉnh phạm vi khi rủi ro kỹ thuật được giải thích.
- Xác nhận hành vi có thể quan sát được.
- Tham gia đánh giá khi một trade-off ảnh hưởng trải nghiệm.

Developer cần diễn giải rủi ro bằng ngôn ngữ có thể ra quyết định, ví dụ:

> “Nếu cho phép xóa đơn đã thanh toán ngay, báo cáo đối soát sẽ mất dữ liệu gốc. Có thể thay bằng trạng thái đã hủy và giữ bản ghi tài chính theo chính sách retention. Cần xác nhận lựa chọn này với nghiệp vụ và người phụ trách dữ liệu.”

Đó là trao đổi có ích hơn “database không cho làm” hoặc “cần refactor trước”.

## 11. Code ownership: CODEOWNERS hữu ích đến đâu?

Nhiều nền tảng quản lý Git hỗ trợ cơ chế **CODEOWNERS** để chỉ định nhóm hoặc người review cho một số đường dẫn.

Ví dụ cú pháp minh họa:

~~~text
# Ví dụ CODEOWNERS
/src/orders/**          @team-orders
/src/security/**        @team-security
/platform/ci/**         @team-platform
/api/public/**          @team-api-governance
~~~

Cú pháp cụ thể và cách áp dụng quyền phê duyệt phụ thuộc nền tảng Git và cấu hình repository. File CODEOWNERS thường giúp:
- Định tuyến review đến người hiểu khu vực.
- Làm rõ ai cần được thông báo khi code thay đổi.
- Giảm nguy cơ một module ít người hiểu bị sửa mà không có chuyên môn phù hợp.
- Hỗ trợ duy trì ownership khi nhóm lớn.

Nhưng CODEOWNERS **không tự chứng minh code tốt**:
- Owner có thể phê duyệt mà không đọc kỹ.
- Người được chỉ định có thể đã rời nhóm.
- Một thay đổi xuyên nhiều package có thể có nhiều owner.
- File có thể chỉ định team nhưng không xác định ai quyết định contract liên nhóm.
- Một quy tắc review bắt buộc có thể bị cấu hình sai hoặc bypass theo quyền.

### Quản lý CODEOWNERS có trách nhiệm

- Dùng nhóm ổn định hoặc alias tổ chức thay vì chỉ tên cá nhân nếu phù hợp.
- Có owner dự phòng và cách xử lý khi không ai phản hồi.
- Review danh sách khi tổ chức hoặc module thay đổi.
- Chỉ định owner theo ranh giới có ý nghĩa, không biến mọi file thành vùng phê duyệt của quá nhiều nhóm.
- Xác định khi nào cần owner của consumer/API/security tham gia.
- Ghi rõ yêu cầu phê duyệt bắt buộc trong branch protection nếu nền tảng hỗ trợ.

Ownership tốt giúp người thay đổi tìm đúng người; nó không được dùng làm lý do để mọi thành viên khác ngừng quan tâm chất lượng.

## 12. Ranh giới sở hữu và shared components

Một thư viện dùng chung hoặc module nền tảng có thể phục vụ nhiều team. Nếu một nhóm thay đổi mà không hiểu ảnh hưởng, toàn bộ consumer có thể bị phá.

Ví dụ một thư viện Money được nhiều service dùng:
- Service Orders cần phép cộng và trừ tiền.
- Service Billing cần quy tắc scale/làm tròn.
- Reporting cần format và đơn vị.
- API clients cần serialization tương thích.

Có thể có một **owner của thư viện** chịu trách nhiệm API và versioning, nhưng consumer teams vẫn chịu trách nhiệm xác nhận cách dùng trong domain của họ.

### Quy tắc cộng tác cho shared component

1. **Có owner của contract:** một nhóm duy trì public API và compatibility policy.
2. **Có consumer visibility:** biết những service nào phụ thuộc và phiên bản đang dùng.
3. **Thay đổi có version:** breaking change có kế hoạch migration.
4. **Có contract tests:** kiểm tra hành vi công khai và ví dụ tiêu thụ.
5. **Có rollout strategy:** nâng theo nhóm hoặc giai đoạn nếu cần.
6. **Có deprecation window:** công bố thời hạn hỗ trợ và hướng thay thế.
7. **Có feedback loop:** consumer báo vấn đề và owner xử lý.

Không nên giải quyết bằng cách bắt mọi nhóm cùng sửa mọi lần. Cũng không nên để shared library trở thành “common” không có ai quản lý. **Một owner duy trì contract, các consumer sở hữu cách tích hợp của mình.**

## 13. Handoff giữa các nhóm: nơi chất lượng dễ bị rơi

Handoff xảy ra khi công việc chuyển từ:
- Product sang engineering.
- Developer sang QA.
- Engineering sang operations.
- Một team producer sang consumer.
- Một nhóm triển khai sang nhóm duy trì.
- Nhóm hiện tại sang nhóm khác sau tái cấu trúc tổ chức.

Rủi ro thường không nằm ở việc thiếu một cuộc họp, mà ở **thông tin và quyền quyết định không đi cùng thay đổi**.

### Một handoff tốt cần gì?

- **Mục tiêu:** thay đổi nhằm giải quyết vấn đề gì.
- **Hợp đồng:** đầu vào, đầu ra, lỗi, quyền và tương thích.
- **Phạm vi:** module/service/data bị ảnh hưởng.
- **Bằng chứng:** test, build, migration và quan sát đã thực hiện.
- **Giới hạn:** điều gì chưa kiểm chứng hoặc còn rủi ro.
- **Vận hành:** metric, alert, runbook, rollback.
- **Owner tiếp theo:** ai nhận trách nhiệm và có đủ quyền/công cụ không.

### Ví dụ handoff sang operations

Không đủ:
> “Feature đã deploy. Nhờ Ops theo dõi.”

Tốt hơn:
> “Order export đã bật cho 10% tenant. Theo dõi export_job_failure_rate, thời gian hoàn tất và số job đang chờ. Nếu tỷ lệ lỗi vượt guardrail đã thống nhất hoặc queue tăng liên tục, dừng rollout và chuyển traffic về luồng cũ. Runbook nêu cách tra job ID và retry an toàn. Owner dịch vụ Orders trực ca cùng SRE trong giai đoạn canary.”

Các metric và ngưỡng cần được điền theo hệ thống thật. Ví dụ cho thấy handoff phải mang theo **hành động và người chịu trách nhiệm**, không chỉ một trạng thái “done”.

## 14. Definition of Done: định nghĩa hoàn tất chung

**Definition of Done (DoD)** là thỏa thuận về điều kiện để một công việc được xem là hoàn tất. DoD giúp nhóm tránh tình trạng developer nói “đã code xong”, QA nói “chưa test”, operations nói “chưa thể vận hành”.

DoD cần đủ rõ để dùng hằng ngày, nhưng không nên biến mọi ticket thành một checklist khổng lồ không phân biệt rủi ro.

### Ví dụ DoD chung cho thay đổi phần mềm

- Yêu cầu và hành vi chấp nhận đã được làm rõ.
- Thay đổi tuân theo ranh giới và convention của module.
- Unit test hoặc kiểm thử phù hợp được bổ sung/cập nhật.
- Build và quality gates bắt buộc đạt.
- API/schema/data migration được review khi bị ảnh hưởng.
- Security/privacy review được thực hiện khi thay đổi chạm ranh giới tương ứng.
- Tài liệu và thông tin vận hành được cập nhật khi cần.
- PR được review bởi owner phù hợp.
- Rollout/rollback và observability được xác định với thay đổi có rủi ro vận hành.
- Không còn blocker chưa được giải quyết hoặc chấp nhận theo quy trình có thẩm quyền.

### DoD theo mức rủi ro

| Mức thay đổi | Điều kiện hoàn tất có thể cần |
| --- | --- |
| **Thay đổi nhỏ, không ảnh hưởng runtime** | Build, lint/format, review phù hợp |
| **Logic nghiệp vụ** | Unit tests, trường hợp biên, domain review |
| **API hoặc event contract** | Compatibility, contract test, consumer notification |
| **Database migration** | Migration test, backup/rollback hoặc forward-fix, đối soát |
| **Bảo mật/quyền** | Security review, test allow/deny, audit phù hợp |
| **Hot path hoặc capacity** | Benchmark/load test và guardrail vận hành |
| **Production rollout rủi ro cao** | Canary, dashboard, alert, rollback owner |

DoD không nên yêu cầu load test cho một sửa lỗi chính tả trong tài liệu, nhưng cũng không nên để thay đổi transaction quan trọng chỉ cần “unit test xanh”.

## 15. Collaborate sớm: shift-left mà không tạo thêm thủ tục

**Shift-left** nghĩa là đưa hoạt động phát hiện rủi ro về sớm hơn trong vòng đời phát triển, khi chi phí sửa thường thấp hơn.

Ví dụ:
- Product và developer thống nhất trạng thái trước khi code.
- Security tham gia threat modeling trước khi chọn API.
- QA giúp xác định trường hợp biên khi viết acceptance criteria.
- Platform tư vấn khả năng triển khai và quan sát trước khi tạo dependency mới.
- Consumer team review schema trước khi producer phát hành breaking change.

Shift-left không có nghĩa mọi người phải tham gia mọi cuộc họp. Cần chọn **đúng người, đúng thời điểm, đúng quyết định**.

### Những tín hiệu nên mời chuyên môn sớm

- Có dữ liệu cá nhân hoặc nhạy cảm.
- Thay đổi quyền truy cập hoặc identity.
- Thay public API, event hoặc shared library.
- Migration lớn hoặc thay đổi schema khó rollback.
- Tác động tới transaction, đồng thời hoặc idempotency.
- Thay đổi giới hạn tải, cache, retry hoặc queue.
- Thêm dịch vụ bên ngoài hoặc phụ thuộc mới.
- Thay đổi ảnh hưởng nhiều domain/team.

Nếu chỉ thay một hàm nội bộ không có tác động vượt module, review của owner và test phù hợp có thể đủ.

## 16. Quyết định liên nhóm cần được ghi lại

Khi một thay đổi ảnh hưởng nhiều team, thông tin trong chat hoặc lời nói có thể thất lạc. Một **Architecture Decision Record (ADR)** hoặc decision note ngắn giúp ghi:
- Bối cảnh và vấn đề.
- Các phương án đã cân nhắc.
- Quyết định và lý do.
- Hợp đồng/ràng buộc.
- Các nhóm bị ảnh hưởng.
- Rủi ro còn lại.
- Thời điểm hoặc điều kiện xem xét lại.

### Ví dụ: thay đổi schema sự kiện

Một event OrderCreated cần thêm trường currency.

Các câu hỏi cần được quyết định:
- Trường có bắt buộc không?
- Consumer cũ có xử lý payload có trường mới không?
- Producer có phát giá trị mặc định không?
- Event lịch sử không có trường sẽ được diễn giải thế nào?
- Có cần version mới không?
- Consumer nào phải cập nhật?
- Khi nào có thể bỏ tương thích cũ?

Producer team sở hữu việc phát hành event theo contract. Consumer teams chịu trách nhiệm kiểm tra cách họ đọc event. Một owner API/event có thể điều phối versioning và quyết định tương thích. QA hỗ trợ test contract; platform hỗ trợ schema registry hoặc pipeline nếu có.

**Ghi ADR không thay thế trao đổi**, nhưng nó giúp kết quả trao đổi trở thành tri thức có thể truy nguyên.

## 17. Cộng tác qua incident và lỗi sau triển khai

Một sự cố production có thể cho thấy:
- Test thiếu trường hợp thực tế.
- Ownership không rõ.
- Alert không có người nhận.
- Runbook không cập nhật.
- Một nhóm thay API mà consumer không được thông báo.
- Quality gate không kiểm tra đúng rủi ro.
- Hệ thống thiếu cơ chế giới hạn hoặc phục hồi.

Incident review nên tìm **điều kiện hệ thống cho phép sự cố xảy ra và kéo dài**, không chỉ xác định ai viết dòng code cuối cùng.

### Post-incident review có ích nên trả lời

1. Điều gì đã xảy ra và ảnh hưởng tới ai?
2. Tín hiệu đầu tiên xuất hiện khi nào?
3. Hệ thống và quy trình đã phản ứng thế nào?
4. Những giả định nào không đúng?
5. Vì sao kiểm tra trước release không phát hiện?
6. Ownership/handoff có điểm nào thiếu?
7. Biện pháp giảm thiểu nào đã có tác dụng?
8. Cần thay đổi test, gate, observability hoặc quy trình ra sao?
9. Ai sở hữu từng hành động và khi nào xem lại?

### Blameless không có nghĩa không có trách nhiệm

Một review không đổ lỗi cá nhân vẫn cần:
- Owner rõ cho hành động khắc phục.
- Thời hạn hoặc trigger.
- Ưu tiên theo mức rủi ro.
- Bằng chứng hoàn tất.
- Cập nhật runbook và tri thức.

Mục tiêu là tạo điều kiện để người tham gia báo cáo sai sót và học từ hệ thống, đồng thời bảo đảm các hành động cải thiện thực sự xảy ra.

## 18. RACI minh họa cho một thay đổi có nhiều ranh giới

Bảng sau minh họa cách phân vai trong một thay đổi API tạo đơn. Mỗi tổ chức cần điều chỉnh theo quyền và cơ cấu thật.

| Hoạt động | Product/domain | Developer/team owner | Reviewer/tech lead | QA | Security | Platform/SRE |
| --- | --- | --- | --- | --- | --- | --- |
| Xác nhận quy tắc nghiệp vụ | **A/R** | C | C | C | I | I |
| Thiết kế API/domain | C | **R** | **A** | C | C | C |
| Triển khai logic và unit test | I | **A/R** | C | C | C | I |
| Test strategy/acceptance | C | R | C | **A/R** | C | I |
| Đánh giá quyền/dữ liệu nhạy cảm | C | R | C | C | **A/C** | C |
| CI/CD và artifact | I | R | C | C | C | **A/R** |
| Rollout/observability | I | R | C | C | C | **A/R** |
| Theo dõi hành vi nghiệp vụ | **A** | R | C | C | I | C |

A là người chịu trách nhiệm giải trình/ra quyết định cuối cùng trong phạm vi được giao; R là người thực hiện; C là người được tham vấn; I là người được thông báo.

Bảng chỉ có ý nghĩa khi:
- Mỗi hoạt động có người chịu trách nhiệm cuối cùng rõ.
- Người được gán A có thẩm quyền và thông tin để quyết định.
- Không nhầm C với người phải phê duyệt.
- Không dùng bảng thay cho giao tiếp trong thay đổi thực tế.

Trong một nhóm nhỏ, một người có thể giữ nhiều vai trò. Không cần duy trì một ma trận phức tạp cho mọi ticket; dùng nó cho các ranh giới hoặc hoạt động lặp lại dễ bị bỏ sót.

## 19. Tránh ownership trở thành silo

Sở hữu rõ không có nghĩa “file này là của tôi, người khác không được đụng”. Ownership nhằm bảo đảm **có người duy trì và ra quyết định**, đồng thời cho phép người khác đóng góp theo quy trình.

### Dấu hiệu silo

- Một nhóm không chia sẻ tài liệu vì sợ mất quyền kiểm soát.
- Chỉ một người biết deploy hoặc sửa module quan trọng.
- PR bị chặn hàng tuần vì owner không có người thay thế.
- Team consumer không được phép góp ý dù chịu ảnh hưởng trực tiếp.
- Các nhóm tối ưu metric riêng làm xấu trải nghiệm toàn hệ thống.
- Shared library có owner nhưng không có cơ chế tiếp nhận contribution.

### Cách giảm silo

- Dùng pair/mob review cho khu vực có kiến thức tập trung.
- Có tài liệu về contract và cách vận hành.
- Duy trì owner chính và owner dự phòng.
- Cho consumer team tham gia review thay đổi hợp đồng.
- Chia sẻ test fixtures và môi trường kiểm thử phù hợp.
- Thực hiện knowledge transfer khi thay người hoặc chuyển module.
- Dùng contribution guide và quy trình escalation rõ.

**Owner là người bảo đảm chất lượng và tính liên tục của khu vực, không phải người độc quyền mọi thay đổi.**

## 20. Quản lý thay đổi liên nhóm mà không làm chậm mọi việc

Một thay đổi liên nhóm thường thất bại vì một trong hai cực:
- Không thông báo cho nhóm bị ảnh hưởng, khiến consumer phát hiện khi release.
- Yêu cầu quá nhiều phê duyệt cho mọi thay đổi, khiến việc nhỏ cũng chậm.

Có thể phân tầng theo **blast radius** và **mức phá vỡ hợp đồng**.

| Phạm vi thay đổi | Cách phối hợp có thể phù hợp |
| --- | --- |
| Nội bộ một module, không đổi contract | Owner module và reviewer phù hợp |
| Chạm module khác nhưng contract ổn định | Tham vấn owner bị ảnh hưởng, test integration |
| Thay public API hoặc event | Consumer notification, contract review, version/deprecation |
| Thay schema dữ liệu quan trọng | Data owner, migration plan, backup/rollback, đối soát |
| Thay bảo mật hoặc quyền | Security/domain owner tham gia sớm |
| Thay nền tảng chung | Platform owner và các consumer đại diện, rollout theo giai đoạn |

### Thỏa thuận thời gian phản hồi review

Nếu owner là nút thắt, nhóm có thể thống nhất:
- Thời gian phản hồi ban đầu.
- Người dự phòng.
- Quy tắc escalation.
- Trường hợp nào cần phê duyệt bắt buộc.
- Cách xử lý khi owner không khả dụng.

Không nên tự động bỏ review của owner chỉ vì chậm. Nếu quy trình thường xuyên chậm, cần sửa ownership, năng lực hoặc phạm vi phê duyệt.

## 21. Java example: tách trách nhiệm nhưng giữ hợp đồng rõ

Giả sử nghiệp vụ hủy đơn có hai phần:
- **OrderCancellationPolicy** quyết định đơn có thể hủy theo trạng thái.
- **OrderCancellationService** điều phối việc đọc đơn, kiểm tra quyền và cập nhật trạng thái.

Ví dụ Java 17:

~~~java
import java.util.Objects;

enum OrderStatus {
    PENDING,
    CONFIRMED,
    SHIPPED,
    CANCELLED
}

record Order(String id, String ownerId, OrderStatus status) {
    Order {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(ownerId, "ownerId");
        Objects.requireNonNull(status, "status");
        if (id.isBlank() || ownerId.isBlank()) {
            throw new IllegalArgumentException("invalid order");
        }
    }
}

@FunctionalInterface
interface OrderCancellationPolicy {
    boolean canCancel(Order order);
}

final class DefaultOrderCancellationPolicy
        implements OrderCancellationPolicy {
    @Override
    public boolean canCancel(Order order) {
        Objects.requireNonNull(order, "order");
        return order.status() == OrderStatus.PENDING
                || order.status() == OrderStatus.CONFIRMED;
    }
}

interface OrderRepository {
    Order findRequired(String orderId);
    void markCancelled(String orderId);
}

@FunctionalInterface
interface OrderAuthorization {
    boolean canCancel(String actorId, Order order);
}

final class OrderCancellationService {
    private final OrderRepository repository;
    private final OrderCancellationPolicy policy;
    private final OrderAuthorization authorization;

    OrderCancellationService(
            OrderRepository repository,
            OrderCancellationPolicy policy,
            OrderAuthorization authorization) {
        this.repository = Objects.requireNonNull(repository);
        this.policy = Objects.requireNonNull(policy);
        this.authorization = Objects.requireNonNull(authorization);
    }

    void cancel(String actorId, String orderId) {
        Objects.requireNonNull(actorId, "actorId");
        Objects.requireNonNull(orderId, "orderId");

        Order order = repository.findRequired(orderId);
        if (!authorization.canCancel(actorId, order)) {
            throw new SecurityException("not allowed to cancel order");
        }
        if (!policy.canCancel(order)) {
            throw new IllegalStateException("order cannot be cancelled");
        }
        repository.markCancelled(orderId);
    }
}
~~~

Ví dụ này minh họa ranh giới:
- **Policy** sở hữu quy tắc trạng thái.
- **Authorization** sở hữu quyết định quyền theo actor và order.
- **Service** điều phối thứ tự đọc, kiểm tra và ghi.
- **Repository** sở hữu cách lưu trữ.

Trong ứng dụng thật, markCancelled phải bảo đảm cập nhật an toàn khi hai request đồng thời. Có thể cần transaction, update có điều kiện hoặc optimistic locking. Ví dụ chưa giải quyết concurrency và không nên được xem là triển khai hoàn chỉnh cho production.

### Test cho từng trách nhiệm

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class DefaultOrderCancellationPolicyTest {
    private final DefaultOrderCancellationPolicy policy =
            new DefaultOrderCancellationPolicy();

    @Test
    void allowsPendingAndConfirmedOrders() {
        assertTrue(policy.canCancel(
                new Order("O-1", "U-1", OrderStatus.PENDING)));
        assertTrue(policy.canCancel(
                new Order("O-2", "U-1", OrderStatus.CONFIRMED)));
    }

    @Test
    void rejectsShippedAndCancelledOrders() {
        assertFalse(policy.canCancel(
                new Order("O-3", "U-1", OrderStatus.SHIPPED)));
        assertFalse(policy.canCancel(
                new Order("O-4", "U-1", OrderStatus.CANCELLED)));
    }
}
~~~

Test policy không cần database. Một test riêng cho service có thể xác nhận:
- Người không có quyền không làm thay đổi repository.
- Đơn không ở trạng thái cho phép không bị cập nhật.
- Đơn hợp lệ và được phép chỉ được cập nhật theo hợp đồng.
- Khi repository lỗi, service không giả vờ thành công.

### Ai review phần nào?

| Phần thay đổi | Owner/chuyên môn cần xem |
| --- | --- |
| Trạng thái được phép hủy | Domain owner |
| Kiểm tra người gọi có quyền hủy | Security/domain owner |
| Thứ tự điều phối và xử lý lỗi | Developer/service owner |
| Atomic update, transaction | Data/service owner |
| Kịch bản hủy và kết quả người dùng | QA/product |
| Alert, log, rollback | Service owner/operations |

Không phải mọi PR cần sáu người phê duyệt. Bảng chỉ cho thấy **ai cần có hiểu biết hoặc tham gia quyết định** khi thay đổi chạm tới phần trách nhiệm của họ.

## 22. Definition of Ownership: ghi lại ai sở hữu điều gì

Một ownership map đơn giản có thể gồm:

~~~text
MODULE / DOMAIN:
Mục đích:
Phạm vi code:
Phạm vi dữ liệu:
Public APIs / Events:
Primary owner:
Backup owner:
Domain decision owner:
Required reviewers:
Security contact:
Operational owner:
Consumers / dependent teams:
Definition of Done:
Required tests / quality gates:
Build / test / deploy instructions:
Dashboards / alerts:
Runbook / rollback:
Known risks:
Escalation path:
Last reviewed:
~~~

Không cần công khai mọi thông tin nhạy cảm trong repository. Có thể trỏ tới hệ thống nội bộ phù hợp, miễn là người có quyền truy cập tìm được thông tin khi cần.

### Ownership map cần được duy trì

Cập nhật khi:
- Module được tách hoặc hợp nhất.
- API trở thành public hoặc có consumer mới.
- Team chuyển trách nhiệm.
- Một dependency hoặc nền tảng chung thay đổi.
- Service chuyển môi trường hoặc mô hình vận hành.
- Người owner rời nhóm.
- Incident cho thấy đường escalation không rõ.

Một ownership map cũ có thể nguy hiểm hơn không có map vì tạo niềm tin sai rằng đã có người chịu trách nhiệm.

## 23. Các anti-pattern trong cộng tác và trách nhiệm

### 23.1. “QA sẽ tìm bug”

Developer không viết test, reviewer không kiểm tra trường hợp biên vì nghĩ QA chịu trách nhiệm cuối. Bug được phát hiện muộn và test khó xác định nguyên nhân.

**Cách cải thiện:** Developer bảo vệ logic và hợp đồng ở tầng phù hợp; QA hỗ trợ chiến lược và kiểm thử độc lập.

### 23.2. “Dev xong rồi, Ops tự vận hành”

Không có dashboard, runbook hoặc rollback; khi sự cố xảy ra, operations phải đoán hành vi service.

**Cách cải thiện:** Service team cung cấp khả năng vận hành và phối hợp SRE trước release.

### 23.3. “Security duyệt rồi nên code an toàn”

Một lần review không bảo đảm mọi endpoint, đường truy cập và thay đổi sau này đều được bảo vệ.

**Cách cải thiện:** Security hỗ trợ thiết kế và kiểm soát; developer và owner duy trì test và thực thi trong code.

### 23.4. “Owner phải sửa mọi file”

Ownership biến thành độc quyền, PR chờ một người và kiến thức tập trung.

**Cách cải thiện:** Owner duy trì hợp đồng, review theo rủi ro, có backup và cho phép contribution.

### 23.5. “Không ai phản đối tức là đã đồng ý”

Những người bị ảnh hưởng không được thông báo hoặc không hiểu thay đổi, đến khi triển khai mới phát hiện.

**Cách cải thiện:** Xác định consumer và người cần tham vấn từ đầu; ghi quyết định và compatibility plan.

### 23.6. “Mọi người cùng chịu trách nhiệm” nhưng không có người quyết định

Bất đồng kéo dài, ticket bị bỏ và các nhóm đẩy trách nhiệm cho nhau.

**Cách cải thiện:** Chỉ định accountable owner cho từng quyết định và đường escalation.

### 23.7. “Có CODEOWNERS là đủ”

File chỉ định người review nhưng không bảo đảm owner hiểu rủi ro, còn hoạt động hoặc có thẩm quyền.

**Cách cải thiện:** Kiểm tra ownership map, backup, quyền phê duyệt và thời gian phản hồi.

### 23.8. “Done nghĩa là code đã merge”

Test, migration, tài liệu và observability chưa hoàn tất nhưng ticket đóng.

**Cách cải thiện:** Dùng DoD theo mức rủi ro và xác nhận cả phần vận hành khi thay đổi yêu cầu.

### 23.9. Review chỉ tập trung vào style

PR có formatter và naming đúng nhưng thiếu authorization hoặc sai transaction.

**Cách cải thiện:** Tự động hóa style để reviewer tập trung vào hành vi, ranh giới và rủi ro.

### 23.10. Tìm người chịu lỗi thay vì tìm điều kiện gây lỗi

Sau incident, nhóm chỉ yêu cầu người viết cẩn thận hơn. Không có test, alert hoặc quy trình nào thay đổi.

**Cách cải thiện:** Phân tích hệ thống, ghi hành động có owner và kiểm tra hiệu quả sau đó.

## 24. Đo hiệu quả cộng tác mà không biến thành xếp hạng cá nhân

Có thể quan sát:
- Thời gian chờ owner review.
- Tỷ lệ PR phải sửa vì yêu cầu chưa rõ.
- Số thay đổi liên nhóm bị phát hiện muộn.
- Tỷ lệ incident có action item được hoàn thành.
- Số alert không có owner hoặc runbook.
- Tỷ lệ module có owner chính và dự phòng.
- Thời gian onboarding để một người tìm được cách test/deploy module.
- Số lần contract bị phá mà consumer không được thông báo.

Nhưng cần thận trọng:
- Thời gian review dài có thể do PR quá lớn hoặc thiếu người, không phải reviewer kém.
- Số bug được phát hiện có thể tăng vì QA/test tốt hơn.
- Số incident ít có thể do lưu lượng thấp, không phải ownership tốt.
- Số PR được merge nhanh có thể tăng vì review hời hợt.
- Tỷ lệ action item đóng cao không bảo đảm hành động giảm tái diễn.

**Không dùng các metric này để xếp hạng hoặc quy trách nhiệm cá nhân một cách máy móc.** Chúng hữu ích để phát hiện điểm nghẽn quy trình và cải thiện cách cộng tác.

### Một số câu hỏi đánh giá định tính

- Người mới có biết hỏi ai khi contract không rõ không?
- Nhóm consumer có được thông báo trước khi API thay đổi không?
- Developer có thể chạy test và tái hiện lỗi mà không cần xin quyền không cần thiết không?
- Khi alert xuất hiện, người trực có biết bước đầu tiên là gì không?
- Người review có hiểu phạm vi quyết định mình đang phê duyệt không?
- Một nhóm có thể đóng góp vào shared component mà không tạo phụ thuộc tổ chức không?

Phản hồi từ những câu hỏi này thường giúp giải thích metric tốt hơn.

## 25. Quy trình cộng tác cho một thay đổi từ đầu đến vận hành

Một quy trình thực tế có thể gồm:

1. **Làm rõ vấn đề:** product/domain owner xác nhận mục tiêu, trạng thái, quy tắc và tiêu chí chấp nhận.
2. **Xác định phạm vi:** developer tìm module, API, dữ liệu và consumer bị ảnh hưởng.
3. **Gọi đúng chuyên môn:** mời security, platform, QA hoặc data owner khi ranh giới của họ bị tác động.
4. **Thống nhất quyết định:** ghi lại trade-off, contract, owner và điều kiện không được phá.
5. **Triển khai theo ranh giới:** developer viết code, test và tài liệu trong phạm vi sở hữu.
6. **Review có trọng tâm:** reviewer/owner kiểm tra hành vi, rủi ro, phụ thuộc và khả năng thay đổi.
7. **Kiểm chứng:** CI, QA và integration tests cung cấp bằng chứng theo mức rủi ro.
8. **Chuẩn bị vận hành:** service owner/SRE xác nhận metric, alert, runbook và rollback khi cần.
9. **Triển khai có kiểm soát:** canary/rollout theo kế hoạch phù hợp.
10. **Theo dõi và học:** xem metric, lỗi, phản hồi người dùng; cập nhật test, gate và ownership nếu phát hiện khoảng trống.

Không phải mọi công việc cần một buổi họp ở mỗi bước. Với thay đổi nhỏ, nhiều bước có thể được thực hiện qua PR và checklist. Với thay đổi API/data/security lớn, cần tham vấn sớm và ghi quyết định rõ hơn.

## 26. Case study: thay đổi trạng thái đơn hàng qua ba nhóm

Một hệ thống có:
- **Order team:** sở hữu Order Service và trạng thái đơn.
- **Warehouse team:** nhận event để chuẩn bị hàng.
- **Mobile team:** hiển thị trạng thái và cho phép người dùng yêu cầu hủy.

Yêu cầu mới: đơn đã xác nhận có thể được hủy trước khi kho bắt đầu đóng gói.

### Nếu không xác định ownership

Order team thêm trạng thái CANCEL_REQUESTED, nhưng:
- Warehouse team chỉ hiểu CONFIRMED và CANCELLED.
- Mobile team hiển thị CANCEL_REQUESTED như trạng thái không xác định.
- Không rõ ai phát event và ai xử lý đơn đang được kho chuẩn bị.
- Không ai quyết định có hoàn tồn kho hay không.
- Test của từng team đều xanh trên mô hình cũ.

Vấn đề không đơn thuần là code thiếu một enum. Đây là **thay đổi contract xuyên nhiều ranh giới**.

### Cách phối hợp

1. **Product/domain owner** xác định thời điểm hủy hợp lệ, kết quả người dùng và cách xử lý khi kho đã bắt đầu.
2. **Order team** sở hữu trạng thái chính thức, transition và API/event contract.
3. **Warehouse team** xác nhận event cần thiết, idempotency và cách xử lý event đến trễ.
4. **Mobile team** xác nhận cách hiển thị, retry và tương thích phiên bản ứng dụng cũ.
5. **QA** lập ma trận trạng thái, thứ tự event, request lặp và lỗi phụ thuộc.
6. **Security** được tham vấn về quyền hủy đơn.
7. **Platform/SRE** xác nhận metric cho event lag, lỗi consumer và khả năng rollback.
8. Các nhóm thống nhất rollout và điều kiện dừng.

### Hợp đồng và test cần có

- Chỉ chủ đơn hoặc actor được ủy quyền mới được yêu cầu hủy.
- Transition hợp lệ được định nghĩa theo trạng thái và thời điểm.
- Consumer có thể nhận event lặp mà không xử lý tác dụng phụ hai lần.
- Event mới tương thích hoặc có version/migration phù hợp.
- Mobile client cũ có hành vi fallback đã xác nhận.
- Có metric để biết event bị trễ hoặc consumer không xử lý.
- Có quy trình đối soát nếu trạng thái Order và Warehouse lệch.

### Ai quyết định điều gì?

Order team sở hữu contract trạng thái và event; Warehouse team sở hữu cách xử lý ở phía kho; Mobile team sở hữu cách trình bày và tương tác client; product/domain owner quyết định quy tắc nghiệp vụ; QA và chuyên môn khác tham gia kiểm chứng. Không một nhóm nào có thể tự thay đổi toàn bộ contract mà bỏ qua các consumer.

**Bài học:** Ownership rõ không loại bỏ nhu cầu cộng tác. Nó giúp mỗi nhóm biết phần mình phải bảo đảm và những thay đổi nào bắt buộc cần tham vấn nhóm khác.

## 27. Mẫu thỏa thuận ownership cho một module

Có thể dùng mẫu ngắn sau để bắt đầu:

~~~text
MODULE / DOMAIN:
Mục đích:
Phạm vi code:
Phạm vi dữ liệu:
Public APIs / Events:
Primary owner:
Backup owner:
Domain decision owner:
Required reviewers:
Security contact:
Operational owner:
Consumers / dependent teams:
Definition of Done:
Required tests / quality gates:
Build / test / deploy instructions:
Dashboards / alerts:
Runbook / rollback:
Known risks:
Escalation path:
Ngày xem lại:
~~~

Mẫu này không bắt buộc phải có đủ tên cá nhân cho mọi vai trò. Nếu một vai trò chưa được phân công, cần ghi rõ **khoảng trống cần giải quyết**, không điền một nhóm chung chung để tạo cảm giác đã có owner.

## 28. Bài tập tự luyện

### Bài tập 1 — Phân biệt trách nhiệm chung và ownership

Một PR thay đổi cách tính tổng tiền đơn hàng. Developer nói “QA sẽ kiểm tra”; QA nói “tôi chỉ test theo acceptance criteria”; Product nói “tôi đã ghi yêu cầu”; reviewer chỉ xem style.

Hãy xác định trách nhiệm nào đang bị bỏ trống. Đề xuất ai cần:
- Xác nhận quy tắc làm tròn.
- Viết unit test.
- Review trường hợp biên.
- Kiểm tra API response.
- Xác nhận kết quả nghiệp vụ.
- Theo dõi sai lệch sau triển khai.

*Gợi ý:* Nhiều vai trò cùng góp phần nhưng phải có owner cuối cùng cho từng quyết định.

### Bài tập 2 — Thiết kế RACI cho migration database

Một migration đổi kiểu cột tiền và chuyển dữ liệu lịch sử. Hãy lập bảng RACI cho:
- Xác định semantics và đơn vị tiền.
- Thiết kế migration.
- Kiểm tra dữ liệu cũ.
- Backup/restore.
- Integration test.
- Triển khai.
- Đối soát sau migration.
- Rollback hoặc forward-fix.

Nêu ai có quyền quyết định khi product deadline xung đột với rủi ro dữ liệu.

### Bài tập 3 — CODEOWNERS không phản hồi

Một module quan trọng chỉ có một owner. Người đó nghỉ hai tuần, PR sửa lỗi bảo mật bị chờ review.

Hãy đề xuất:
- Cách xử lý sự cố hiện tại theo quyền tổ chức.
- Cơ chế owner dự phòng.
- Cập nhật CODEOWNERS/ownership map.
- Cách tránh tập trung kiến thức vào một người.
- Quy tắc escalation mà không bỏ qua kiểm soát cần thiết.

### Bài tập 4 — Review xuyên nhiều nhóm

Order team muốn đổi tên event OrderPaid thành PaymentCompleted. Ba consumer chưa được thông báo.

Hãy lập danh sách những người cần tham vấn, hợp đồng cần kiểm tra, chiến lược tương thích và điều kiện xóa event cũ. Giải thích vì sao producer team không nên tự quyết định thời điểm ngừng hỗ trợ consumer.

### Bài tập 5 — QA phát hiện lỗi sau release

Một bug phân quyền xuất hiện production dù QA đã test các trường hợp hợp lệ. Nhóm đề xuất yêu cầu QA tăng số lượng test thủ công.

Hãy phân tích những lớp kiểm soát cần xem lại:
- Acceptance criteria và threat model.
- Unit/integration tests.
- Authorization policy.
- Code review/ownership.
- Observability và incident response.

Đề xuất hành động có owner và bằng chứng hoàn tất; tránh chỉ thêm một yêu cầu “QA cẩn thận hơn”.

### Bài tập 6 — Developer và SRE bất đồng về retry

Developer muốn retry năm lần cho mọi lỗi HTTP; SRE lo hệ thống phụ thuộc đang quá tải.

Hãy mô tả:
- Những dữ liệu cần thu thập.
- Ai sở hữu hợp đồng retry/idempotency.
- Vai trò của timeout, backoff, jitter và giới hạn concurrency.
- Test nào cần có.
- Metric nào xác nhận chính sách không làm khuếch đại sự cố.

### Bài tập 7 — Viết Definition of Done theo rủi ro

Hãy tạo hai DoD:
1. Sửa lỗi hiển thị văn bản ở màn hình nội bộ.
2. Thay đổi luồng thanh toán và migration dữ liệu.

So sánh những điều kiện cần có và giải thích vì sao không nên dùng cùng một checklist nặng cho cả hai.

### Bài tập 8 — Incident review không đổ lỗi

Một sự cố xảy ra vì một consumer không xử lý event mới. Producer đã merge code sau khi một reviewer approve, nhưng không có contract test hoặc consumer notification.

Hãy viết các câu hỏi post-incident review và action items:
- Thay đổi contract.
- Ownership và notification.
- Contract tests.
- Rollout.
- Monitoring.
- Owner và thời hạn.

Không quy toàn bộ nguyên nhân cho cá nhân reviewer hoặc developer.

## 29. Tự kiểm tra kiến thức

**Câu 1.** Chất lượng mã có phải trách nhiệm riêng của developer?

*Trả lời:* Không. Developer có trách nhiệm với thay đổi mình tạo, nhưng chất lượng còn phụ thuộc yêu cầu, review, kiểm thử, nền tảng, bảo mật, triển khai và vận hành.

**Câu 2.** “Mọi người cùng chịu trách nhiệm” có đủ để xác định owner?

*Trả lời:* Không. Cần xác định người thực hiện, người quyết định cuối cùng, người tham vấn và người cần được thông báo cho từng hoạt động quan trọng.

**Câu 3.** CODEOWNERS có bảo đảm thay đổi được review đúng chất lượng?

*Trả lời:* Không. Nó hỗ trợ định tuyến ownership; vẫn cần owner hoạt động, review có trọng tâm và quy tắc phê duyệt phù hợp.

**Câu 4.** QA có thể thay developer viết mọi unit test?

*Trả lời:* Không. Developer nên bảo vệ logic và hợp đồng gần code; QA hỗ trợ chiến lược, kịch bản và kiểm chứng độc lập ở các tầng phù hợp.

**Câu 5.** SRE có chịu trách nhiệm toàn bộ khả năng vận hành của service?

*Trả lời:* Không. SRE/platform cung cấp nền tảng và chuyên môn; service team vẫn phải xây dựng metric, timeout, runbook và hiểu hành vi của service mình.

**Câu 6.** Khi thay đổi event, producer team có thể tự quyết định xóa version cũ?

*Trả lời:* Không nếu consumer còn phụ thuộc. Cần biết consumer, compatibility, thời hạn deprecation và điều kiện chuyển đổi.

**Câu 7.** Một DoD giống nhau cho mọi loại thay đổi có tốt không?

*Trả lời:* DoD chung giúp thống nhất, nhưng mức kiểm chứng nên điều chỉnh theo rủi ro và phạm vi thay đổi.

**Câu 8.** Blameless incident review có nghĩa không giao owner cho hành động khắc phục?

*Trả lời:* Không. Không đổ lỗi cá nhân vẫn cần owner, thời hạn, bằng chứng hoàn tất và đánh giá hiệu quả.

**Câu 9.** Ownership rõ có nghĩa chỉ owner được sửa code?

*Trả lời:* Không. Owner duy trì hợp đồng và chất lượng; người khác vẫn có thể đóng góp theo quy trình review và phối hợp phù hợp.

**Câu 10.** Dấu hiệu nào cho thấy trách nhiệm chung đang bị phân tán?

*Trả lời:* Không ai quyết định contract, alert không có người nhận, consumer không được thông báo, test bị đẩy qua lại hoặc incident action không có owner.

## Ghi nhớ

**Chất lượng mã là trách nhiệm chung với phạm vi sở hữu rõ ràng.** Developer bảo vệ thay đổi mình tạo; reviewer kiểm tra quyết định và rủi ro; QA hỗ trợ chiến lược kiểm chứng; tech lead và domain owner làm rõ ranh giới kỹ thuật/nghiệp vụ; security bảo vệ ranh giới tin cậy; platform/SRE giúp hệ thống có thể triển khai và vận hành; product xác nhận giá trị và hành vi mong đợi. Mỗi nhóm cần biết **phần nào mình sở hữu, hợp đồng nào mình duy trì, ai có quyền quyết định và khi nào phải tham vấn nhóm khác**. CODEOWNERS, Definition of Done, RACI, ADR và incident review chỉ có giá trị khi được dùng để làm rõ trách nhiệm và tạo bằng chứng. Một nhóm cộng tác tốt không đẩy chất lượng qua hàng rào giữa các vai trò; họ cùng bảo vệ kết quả, đồng thời giữ **owner, ranh giới và hành động** đủ rõ để không có việc quan trọng nào bị bỏ trống.
