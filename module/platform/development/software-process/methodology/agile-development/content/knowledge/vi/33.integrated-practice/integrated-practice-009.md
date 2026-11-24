# Lựa chọn các thực hành XP hỗ trợ một vấn đề chất lượng cụ thể

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **triệu chứng chất lượng**, **failure mode/cơ chế gây lỗi**, **tác động tới người dùng** và **nguyên nhân cần kiểm chứng** trước khi chọn thực hành Extreme Programming (XP).
2. Giải thích cơ chế của những thực hành XP như **Test-Driven Development (TDD), pair programming, continuous integration (CI), refactoring, simple design, collective code ownership, coding standards, small releases, sustainable pace** và cách cộng tác với người hiểu nghiệp vụ.
3. Lựa chọn **một nhóm nhỏ thực hành phù hợp** cho một vấn đề cụ thể thay vì yêu cầu đội áp dụng toàn bộ XP hoặc đánh giá thành công bằng số hoạt động.
4. Xây dựng **giả thuyết có thể kiểm chứng**, baseline, tiêu chí chọn, điều kiện tiên quyết, chi phí chuyển đổi, rủi ro và guardrail chất lượng.
5. Thực hành **Red–Green–Refactor** trên một quy tắc nghiệp vụ Java nhỏ, hiểu giới hạn của unit tests và khi nào cần contract/integration/security tests.
6. Kết hợp XP với **Scrum, Kanban, user story, Product Backlog, Definition of Done và phản hồi người dùng** mà không nhầm trách nhiệm framework.
7. Đo hiệu quả qua **lỗi lọt môi trường thật, rework, thời gian phản hồi test, độ ổn định CI, cycle time, work item age và tác động người dùng**, biết tránh suy diễn nhân quả từ vài con số.
8. Thiết kế và đánh giá một **thử nghiệm cải tiến bốn tuần**, trình bày lý do giữ/sửa/bỏ thực hành khi bối cảnh thay đổi.

## 1. Câu hỏi đúng không phải “Nên dùng XP nào?”, mà là “Chất lượng đang thất bại ở đâu?”

Một Scrum Team phát triển nền tảng học tập có các triệu chứng:

- Tính năng **“Tiếp tục học”** thường bị sửa lại vì hai thiết bị gửi cập nhật tiến độ gần như đồng thời.
- Unit tests của từng service đều xanh nhưng tích hợp Auth–API–DB vẫn thất bại.
- Mỗi thay đổi nhỏ trong module tiến độ phải chờ một chuyên gia duy nhất review.
- PR lớn, khó hiểu và nhánh tồn tại lâu; lỗi thường được phát hiện sát ngày release.
- Sau mỗi Sprint, có thêm nhiều story point nhưng học viên vẫn báo mất tiến độ.

Một đề xuất phổ biến là:

> “Hãy triển khai TDD, pair programming, refactoring, CI và mua một công cụ coverage mới, rồi đội sẽ trở thành XP.”

Đề xuất trên chưa chỉ ra **cơ chế gây lỗi**, thứ tự ưu tiên hay cách đo cải thiện. Nó có nguy cơ thay một vấn đề chất lượng bằng **một danh sách nghi thức và công cụ**.

Một cách có trách nhiệm hơn là:

> “Trong bốn tuần gần đây, những thay đổi liên quan ghi tiến độ thường có rework khi tích hợp và xuất hiện lỗi ghi lùi. Chúng ta sẽ xác minh nguyên nhân, thử TDD cho quy tắc cập nhật, pairing ở đoạn concurrency khó, kiểm chứng tích hợp thường xuyên và theo dõi lỗi/rework cùng thời gian phản hồi. Nếu dữ liệu không ủng hộ giả thuyết hoặc phát sinh rủi ro mới, sẽ điều chỉnh.”

**Nguyên tắc trung tâm:** Chọn thực hành XP **vì cơ chế giúp cải thiện chất lượng cụ thể**, không phải vì tên thực hành phổ biến hoặc vì một tổ chức khác đang dùng.

## 2. XP là gì trong bức tranh Agile tổng thể?

**Extreme Programming (XP)** là một phương pháp phát triển phần mềm trong họ Agile, nhấn mạnh phản hồi nhanh, chất lượng kỹ thuật, giao tiếp, đơn giản, can đảm và tôn trọng. Những mô tả XP qua các thời kỳ có danh sách thực hành khác nhau; vì vậy cần nói rõ **thực hành cụ thể đang chọn và mục đích**, không dùng nhãn XP làm bằng chứng chất lượng.

### Phân biệt các lớp quyết định

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Giá trị và nguyên tắc Agile** | Vì sao học sớm, cộng tác và giao phần mềm hoạt động? | Nhận phản hồi người dùng, thay đổi dựa trên bằng chứng |
| **Scrum** | Tổ chức trách nhiệm, Sprint, tạo tác, cam kết và kiểm tra–thích nghi thế nào? | Product Goal, Sprint Goal, Increment, Definition of Done |
| **Kanban** | Quan sát và cải tiến dòng công việc thế nào? | Workflow, WIP, work item age, cycle time, chính sách pull |
| **XP** | Phát triển phần mềm với phản hồi kỹ thuật và chất lượng tốt hơn thế nào? | TDD, pairing, CI, refactoring, simple design, small releases |
| **Công cụ** | Hỗ trợ hành vi và bằng chứng ở đâu? | JUnit, Git, pipeline CI, bảng công việc |
| **Kết quả** | Người dùng và đội thực sự hưởng lợi thế nào? | Giảm lỗi tiến độ, Increment đáng tin, phản hồi sớm |

**Scrum không bắt buộc dùng TDD**, và **XP không bắt buộc đội phải tổ chức Scrum**. Một Scrum Team có thể áp dụng những thực hành XP để nâng năng lực đạt DoD. Một đội vận hành theo Kanban cũng có thể dùng XP. Phải giữ nguyên các trách nhiệm và nghĩa vụ đang áp dụng, không dùng danh sách thực hành để thay tên framework cho đẹp.

### Phân biệt ba mệnh đề

1. “Chúng tôi **đã cài JUnit**” — chỉ nói về công cụ hoặc thư viện.
2. “Chúng tôi **viết test trước một thay đổi nhỏ và dùng kết quả để điều khiển thiết kế**” — mô tả hành vi TDD.
3. “Nhờ hành vi đó và những kiểm chứng liên quan, chúng tôi **giảm lỗi logic phát hiện muộn mà không tăng tổng thời gian giao giá trị**” — nêu giả thuyết kết quả có thể đo.

Thành công thực sự phải đi qua cả **hành vi và kết quả**, không chỉ công cụ được cài đặt.

## 3. Từ triệu chứng tới failure mode, không quy lỗi con người

Một lỗi nhìn thấy từ người dùng thường có nhiều nguyên nhân. Trước khi chọn kỹ thuật, cần hiểu **điều kiện làm lỗi xuất hiện**, nơi lẽ ra có thể phát hiện sớm và điều kiện tổ chức khiến lỗi lọt qua.

### Tách bốn tầng phân tích

| Tầng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Tác động người dùng** | Người dùng thực sự gặp gì? | Học viên tiếp tục tại giây 120 thay vì 300 đã lưu |
| **Triệu chứng kỹ thuật** | Hệ thống thể hiện điều gì? | Hai request cập nhật theo thứ tự khác với lúc gửi |
| **Failure mode/giả thuyết cơ chế** | Vì sao điều đó có thể xảy ra? | Last-write-wins, retry không idempotent, thiếu kiểm soát phiên bản |
| **Lỗ hổng phản hồi/quy trình** | Vì sao đội phát hiện muộn? | Thiếu test cạnh tranh, CI không chạy integration test, ghép nhánh cuối Sprint |

### Không kết luận từ một dấu hiệu

“Lỗi production tăng” không tự chứng minh Developers thiếu kỹ năng. Có thể do:

- Khối lượng người dùng hoặc loại giao dịch mới tăng mạnh.
- Phạm vi test không phản ánh dữ liệu/hành vi thật.
- API đối tác đổi hợp đồng mà đội không biết.
- Thiếu quyền sửa môi trường CI hoặc feedback từ người dùng đến muộn.
- Kiến trúc khó thay đổi khiến một sửa lỗi tạo lỗi khác.
- Mức độ phát hiện và ghi nhận sự cố đã tốt hơn trước.

Nếu nguyên nhân là **API bên ngoài thay đổi không báo trước**, chỉ bắt đội dùng TDD có thể giúp logic cục bộ nhưng không thay thế **contract tests, giao tiếp provider–consumer và chính sách tương thích**.

### Ngôn ngữ chẩn đoán không quy lỗi

Thay vì nói “Developer A viết code ẩu”, hãy đặt câu hỏi:

> “Trong lần ghi tiến độ bị lùi, điều kiện nào cho phép request cũ ghi sau request mới, test nào có thể tái hiện, và thay đổi cách làm nào sẽ giúp cả đội phát hiện trước khi release?”

Phân tích cơ chế tốt hơn phán xét cá nhân nếu muốn tạo **cải tiến lặp lại được**.

## 4. Tình huống xuyên suốt: lỗi ghi lùi tiến độ học

Sản phẩm có chức năng lưu vị trí học video. Một học viên dùng máy tính và điện thoại; thiết bị A gửi yêu cầu lưu vị trí 300 giây, trong khi thiết bị B còn đang phát và gửi vị trí 120 giây sau đó.

Trình tự minh họa:

~~~text
10:00:00  Thiết bị B bắt đầu gửi "progress = 120s", mạng chậm
10:00:01  Thiết bị A gửi "progress = 300s", server nhận và lưu
10:00:02  Request từ thiết bị B đến muộn, server ghi đè "120s"
10:00:03  Học viên mở lại bài, thấy vị trí 120s thay vì 300s
~~~

**Lưu ý nghiệp vụ:** “Không bao giờ cho tiến độ giảm” **không tự động là quy tắc đúng**. Người dùng có thể chủ động tua lại hoặc bắt đầu học lại. Đội phải cùng Product Owner làm rõ: vị trí phát cuối cùng, tiến độ hoàn tất tối đa, bookmark và thời điểm xác nhận có thể là **những khái niệm khác nhau**.

Trong bài này, để luyện lựa chọn XP, giả sử nhóm đã làm rõ yêu cầu:

> **Tiến độ hoàn tất lớn nhất của một bài** không được giảm do request đến muộn; một hành động “học lại từ đầu” phải có ngữ nghĩa và dữ liệu riêng. Hệ thống không được đọc/ghi tiến độ của tài khoản khác.

### Tác động và rủi ro

- Người học mất niềm tin vì việc đã học biến mất.
- Dữ liệu có thể không khôi phục chính xác nếu không có lịch sử.
- Retry/reorder/concurrency khó tái hiện bằng một vài thao tác thủ công.
- Nếu cache không tách phiên, lỗi có thể đi kèm **rủi ro quyền riêng tư**.
- Fix ngắn hạn bằng một phép so sánh ở UI có thể **che lỗi ở API/DB**, không xử lý nguồn gây hại.

### Không vội chọn kỹ thuật

Trước khi nói “dùng TDD”, đội cần xác minh:

1. Quy tắc nghiệp vụ đã được xác nhận bằng ví dụ cụ thể chưa?
2. Logic sai tại service, transaction trong DB, cache, hay thiết bị client?
3. Có log/timeline an toàn chứng minh thứ tự request và kết quả ghi không?
4. Unit tests nào đang có, integration/concurrency tests nào thiếu?
5. Thay đổi bị chặn ở đâu: review, môi trường test, hợp đồng giữa nhóm?
6. Điều kiện nào phải đáp ứng để coi Increment đạt Definition of Done?

## 5. Thu baseline trước khi quyết định thực hành

**Baseline** là bức tranh ban đầu theo phạm vi và định nghĩa rõ, giúp so sánh sau thử nghiệm. Đừng kéo mọi metric đang có lên dashboard rồi gọi đó là phân tích.

### Cần xác định

- **Loại việc:** Chỉ tính thay đổi liên quan tiến độ, retry và đồng bộ, hay cả UI thông thường?
- **Cửa sổ quan sát:** Ví dụ bốn tuần trước can thiệp; chọn kỳ đủ hiểu hoạt động.
- **Mốc start/finish:** Cycle time tính từ khi item bắt đầu thực hiện tới khi đạt DoD; work item age cho item chưa Done.
- **Định nghĩa lỗi:** Lỗi nghiệp vụ đã xác nhận, test failure, flaky test, incident, hoặc feedback người dùng?
- **Nhóm người dùng:** Có khác biệt về thiết bị, phiên bản mobile, kết nối kém hoặc quyền học?
- **Nguồn bằng chứng:** Issue liên kết PR/test/build, telemetry được phép, incident timeline, quan sát trực tiếp.

### Baseline giả định để học

| Tín hiệu | Bốn tuần trước khi thử (giả định) | Ràng buộc diễn giải |
| --- | ---: | --- |
| PBI liên quan tiến độ đã Done | 12 | Các item khác độ lớn và rủi ro |
| Lỗi ghi lùi được xác nhận sau release | 4 | Đếm trường hợp có cùng định nghĩa, không nhất thiết tất cả lỗi |
| Vòng rework do sai logic/quy tắc | 9 | Một item có thể có nhiều vòng, cần cách ghi nhất quán |
| Thời gian chờ review trung vị | 2,5 ngày/item | Chỉ với mẫu có đủ timestamp |
| Thời gian feedback CI quan trọng | 18 phút/lần | Đo percentiles và flaky tốt hơn một giá trị trung bình |
| Tỷ lệ chạy CI thất bại do test flaky | 12% trong số runs liên quan | Cần tách lỗi test và lỗi sản phẩm |
| PBI có contract/integration tests cho retry | 3/12 | Không tự suy ra test đã bao phủ đủ |

**Tất cả con số chỉ là giả định minh họa.** Không kết luận 4 lỗi là do thiếu TDD trước khi phân tích cơ chế của từng lỗi.

### Phản hồi định tính cũng quan trọng

Một cuộc trao đổi với Developers/tester/PO có thể cho thấy:

- Test cạnh tranh khó viết vì DB test không có fixture cô lập.
- PR bị chờ vì chỉ một người hiểu transaction.
- Product Owner chưa phân biệt “vị trí xem cuối” với “tiến độ hoàn tất lớn nhất”.

Ba phát hiện đó gợi ý **ba đòn bẩy khác nhau**: tăng khả năng kiểm thử, giảm phụ thuộc tri thức, làm rõ nghiệp vụ. Không một thực hành XP đơn lẻ tự giải quyết tất cả.

## 6. Bản đồ chọn thực hành XP theo failure mode

| Vấn đề chất lượng có bằng chứng | Thực hành XP đáng cân nhắc | Cơ chế tác động | Điều kiện/giới hạn |
| --- | --- | --- | --- |
| Sai logic nghiệp vụ, lỗi trường hợp biên thường phát hiện muộn | **TDD + refactoring** | Đặc tả hành vi bằng test nhỏ trước code; thiết kế dễ kiểm chứng | Cần ví dụ nghiệp vụ đúng; unit tests không thay race/DB test |
| Một phần code quá khó hiểu và sửa chỗ này hỏng chỗ khác | **Refactoring + simple design + tests** | Giảm phức tạp, cải thiện cấu trúc không đổi hành vi ngoài | Cần safety net, phạm vi nhỏ và kiểm tra regression |
| Chỉ một người hiểu module quan trọng | **Pair programming + collective ownership + coding standards** | Truyền tri thức trong công việc, review sớm, giảm bottleneck | Có pairing có mục tiêu và luân chuyển; giữ quyền bảo mật |
| Code merge muộn, lỗi tích hợp dồn sát release | **Continuous Integration + small changes** | Phát hiện sai lệch thường xuyên khi diff còn nhỏ | CI đáng tin, contract/integration tests theo rủi ro |
| Mỗi thay đổi phải chờ review nhiều ngày | **Pairing/collective ownership** kết hợp giảm kích thước PR | Tăng khả năng nhận phản hồi và reviewer dự phòng | Pairing không tự thay review độc lập khi bắt buộc |
| Sản phẩm không có phản hồi người dùng đến khi release lớn | **Small releases + close customer collaboration** | Giảm độ trễ kiểm chứng giá trị | DoD, quyền dữ liệu và chính sách release vẫn bắt buộc |
| Đội làm thêm chức năng chưa cần, không thể thay đổi dễ | **Simple design + YAGNI + refactoring** | Giảm lô công việc và chi phí bảo trì tương lai | Không được bỏ yêu cầu vận hành/bảo mật đã biết |
| Lỗi lặp khi giao tiếp giữa nhóm API–UI | **CI + small changes**, bổ sung contract tests | Feedback trên hợp đồng giữa các thành phần | Contract tests là kỹ thuật bổ trợ; không thay kiểm chứng nghiệp vụ |
| Chạy deadline liên tục gây lỗi và burnout | **Sustainable pace + small releases + automation** | Giảm mệt mỏi và lô lớn, giữ khả năng tập trung | Cần chỉnh kế hoạch, quyền ưu tiên và năng lực tổ chức |
| Ngữ nghĩa acceptance criteria thường hiểu sai | **Close customer collaboration/whole-team conversation**, acceptance testing | Làm rõ ví dụ và feedback khi còn rẻ để sửa | PO/người nghiệp vụ phải có quyền quyết định ngữ nghĩa |

**Đừng chọn tất cả vì chúng đều có ích trong lý thuyết.** Xác định cơ chế chính và chọn một nhóm ít thực hành **bổ sung nhau**, phù hợp khả năng thử và rủi ro cần bảo vệ.

### Phân biệt XP gốc và kỹ thuật bổ trợ

TDD, pairing, CI, refactoring, thiết kế đơn giản, ownership chung, small releases và nhịp bền vững đều là những thực hành/ý tưởng quen thuộc của XP. **Contract testing, security scanning, feature flags, SLO và data migration strategies** có thể hỗ trợ rất tốt, nhưng không nên khẳng định đó là **những thực hành bắt buộc cốt lõi của mọi phiên bản XP**.

## 7. Quy trình chọn một nhóm thực hành có lý do

Một cách chọn thực hành hiệu quả gồm bảy bước:

1. **Nêu vấn đề có thể quan sát:** Ví dụ lỗi ghi lùi tiến độ được xác nhận trên các request đến lệch thứ tự.
2. **Xác định failure mode:** Logic monotonic sai, transaction race, thiếu phiên bản dữ liệu, contract không rõ hay CI không kiểm tra?
3. **Chỉ rõ mục tiêu chất lượng:** Giảm lỗi ghi lùi và phát hiện regression trước release; không bỏ phân quyền.
4. **Liệt kê các đòn bẩy phù hợp:** TDD cho quy tắc, pairing ở phần concurrency, CI chạy test thích hợp, refactoring để dễ test.
5. **Ưu tiên ít thực hành:** Chọn 1–3 can thiệp chính theo khả năng và cơ chế; các điều kiện chất lượng bắt buộc vẫn giữ.
6. **Định nghĩa bằng chứng/guardrail:** Các test tái hiện, thời gian feedback, lỗi sau release, tuổi item, DoD, khả năng khôi phục.
7. **Thử, quan sát, quyết định:** Giữ, chỉnh, loại hoặc mở rộng khi có dữ liệu và hiểu bối cảnh.

### Ma trận quyết định mẫu

| Tiêu chí | Câu hỏi kiểm chứng | Nguyên tắc |
| --- | --- | --- |
| **Mức phù hợp failure mode** | Thực hành tác động trực tiếp vào nguyên nhân nào? | Ưu tiên cơ chế cụ thể hơn khẩu hiệu |
| **Thời gian phản hồi** | Nhận tín hiệu sớm hơn bao nhiêu trong quy trình? | Đo đường phản hồi, không chỉ số test |
| **Điều kiện tiên quyết** | Thiếu dữ liệu test, CI, quyền hoặc hiểu biết nghiệp vụ không? | Đừng đặt TDD lên quy tắc chưa chốt rồi gọi test là chân lý |
| **Chi phí chuyển đổi** | Cần đào tạo, refactor hoặc tạo fixture bao nhiêu? | Thử lát cắt nhỏ trước |
| **Tác dụng phụ** | CI chậm/flaky, pairing quá tải, nhiều flag khó quản lý? | Ghi guardrail và ngưỡng xem lại |
| **Bảo vệ chất lượng** | DoD và các nghĩa vụ dữ liệu/quyền có giữ không? | Không dùng cải tiến để bỏ kiểm soát bắt buộc |
| **Khả năng chứng minh** | Có baseline, phép đo và ví dụ tái hiện không? | Tránh tuyên bố thành công dựa trên cảm giác |

### Không dùng bảng điểm như chân lý

Đội có thể thảo luận **cao/trung bình/thấp** theo tiêu chí, nhưng nếu tự gán điểm rồi cộng thành 87/100, kết quả không tự trở thành bằng chứng khoa học. Phải công khai giả định, độ không chắc và quyền quyết định.

## 8. TDD: dùng test điều khiển thiết kế, không chỉ nâng coverage

**Test-Driven Development (TDD)** tổ chức việc phát triển bằng vòng **Red – Green – Refactor**:

1. **Red:** Viết một test nhỏ mô tả hành vi mong muốn, thấy nó thất bại vì hành vi chưa được hỗ trợ.
2. **Green:** Viết lượng mã đủ để test đạt.
3. **Refactor:** Cải thiện cấu trúc mà vẫn giữ các test phù hợp đạt.

Sau đó lặp lại với một ví dụ biên hoặc thay đổi nhỏ khác.

~~~mermaid
flowchart LR
    A["Chốt ví dụ nghiệp vụ nhỏ"] --> B["RED: viết test thất bại đúng lý do"]
    B --> C["GREEN: mã tối thiểu làm test xanh"]
    C --> D["REFACTOR: cải thiện cấu trúc, giữ hành vi"]
    D --> E["Chạy lại tests và quan sát"]
    E --> A
~~~

### TDD giải quyết vấn đề gì?

- Buộc người viết làm rõ **hành vi có thể kiểm chứng** trước khi thêm implementation.
- Tạo phản hồi nhanh nếu quy tắc nhỏ bị phá bởi sửa đổi sau.
- Có thể gợi ý API đơn giản, tách phụ thuộc và cải thiện thiết kế.
- Kết hợp refactoring để code dễ duy trì.

### TDD không tự bảo đảm điều gì?

- Test có thể **khẳng định sai yêu cầu** nếu PO/người nghiệp vụ chưa làm rõ.
- Unit test đơn luồng không chứng minh an toàn khi **hai transaction thật chạy đồng thời**.
- Coverage 100% không có nghĩa đã test đúng các trường hợp quan trọng.
- Test double/mock có thể không trùng hành vi DB, Auth hoặc API thật.
- Việc viết test trước không thay **DoD, security review, migration plan hoặc kiểm tra tích hợp**.

**Câu hỏi chọn TDD:** Lỗi có bắt nguồn từ quy tắc nhỏ hoặc thiết kế khó kiểm chứng mà test nhanh có thể làm rõ không? Nếu có, TDD là ứng viên tốt. Nếu lỗi chủ yếu do contract bị đổi ngoài nhóm, cần thêm những cơ chế phản hồi khác.

## 9. Bài thực hành Java: Red–Green–Refactor với quy tắc tiến độ

Ta tách một **quy tắc thuần (pure policy)** khỏi HTTP, xác thực và cơ sở dữ liệu, để người học thấy rõ TDD kiểm chứng được gì. Ví dụ dùng **Java 17+** và **JUnit 5**; không giả định đây là API thật của nền tảng.

### Quy tắc nghiệp vụ được xác nhận cho bài tập

> Với trường **highestCompletedSecond**, bản ghi mới giữ giá trị cao hơn của số đã xác nhận và số vừa báo. Giá trị âm không hợp lệ. Đây không phải “vị trí video gần nhất” có thể tua lùi.

### Bước Red: viết test trước

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ProgressPolicyTest {

    @Test
    void doesNotDecreaseWhenOldReportArrivesLate() {
        assertEquals(300, ProgressPolicy.highestCompleted(300, 120));
    }

    @Test
    void advancesWhenHigherReportIsAccepted() {
        assertEquals(300, ProgressPolicy.highestCompleted(120, 300));
    }

    @Test
    void keepsSameValueOnRepeatedReport() {
        assertEquals(300, ProgressPolicy.highestCompleted(300, 300));
    }

    @Test
    void rejectsNegativeReportedSecond() {
        assertThrows(IllegalArgumentException.class,
                () -> ProgressPolicy.highestCompleted(100, -1));
    }
}
~~~

Khi test đầu tiên được viết mà chưa có lớp/method, code có thể **không biên dịch**. Trong TDD, điều quan trọng là xác nhận thất bại đúng vì hành vi đang thêm chưa được hiện thực, không phải vì môi trường build hỏng hoặc test viết sai.

### Bước Green: hiện thực tối thiểu

~~~java
final class ProgressPolicy {
    private ProgressPolicy() {}

    static int highestCompleted(int savedSecond, int reportedSecond) {
        if (savedSecond < 0 || reportedSecond < 0) {
            throw new IllegalArgumentException("seconds must be >= 0");
        }
        return Math.max(savedSecond, reportedSecond);
    }
}
~~~

Code nhỏ, dễ hiểu và test có thể chạy nhanh. **Refactor** lúc này có thể rất ít: tên hàm/biến đã rõ, logic không cần thêm abstraction. Không cần tạo một design pattern chỉ để chứng minh có “bước Refactor”.

### Bước Refactor và chọn test tiếp theo

Sau khi các test xanh, người học xem:

- Có logic trùng lặp hoặc naming chưa đúng nghĩa nghiệp vụ?
- Hàm **highestCompleted** có bị dùng nhầm cho **currentPlaybackPosition** không?
- Có cần tách các policy khác nhau để tránh làm test sai ngữ nghĩa?
- Cần test giới hạn hợp lệ lớn nhất của video hoặc chuyển đổi đơn vị thời gian không? Những giới hạn phải được **xác nhận** trước khi biến thành test.

### Giới hạn rất quan trọng: bài code chưa giải quyết transaction race

Nếu hai request cùng đọc giá trị 100, mỗi bên tính giá trị mới rồi ghi vào DB theo thứ tự khác nhau, **chỉ gọi Math.max trong memory không tự bảo đảm database không ghi lùi**. Phần lưu phải có **bảo đảm nguyên tử/đồng thời phù hợp**, ví dụ cập nhật có điều kiện trong DB hoặc optimistic concurrency, và **kiểm thử tích hợp với DB thật hoặc môi trường đại diện**.

Đội còn phải xử lý quyền tài khoản, retry, replay và cách phân biệt trường **highestCompletedSecond** với vị trí playback hiện tại. **Unit TDD là một lớp an toàn, không phải toàn bộ bằng chứng DoD.**

## 10. Bổ sung acceptance examples để TDD không kiểm thử nhầm sản phẩm

Trong tình huống tiến độ, người viết code có thể chọn một quy tắc nghe hợp lý nhưng trái mong muốn của người dùng. Vì vậy **cộng tác với Product Owner và người hiểu nghiệp vụ** cần diễn ra trước và trong khi viết test.

### Ví dụ cần chốt

| Đầu vào/tình huống | Kết quả mong đợi cho highestCompletedSecond | Câu hỏi phải làm rõ |
| --- | --- | --- |
| Đã lưu 300, báo 120 | Giữ 300 | Đây là tiến độ hoàn tất tối đa, không phải bookmark cuối |
| Đã lưu 120, báo 300 | Chuyển 300 | “Đã hoàn tất” được xác định khi nào? |
| Đã lưu 300, báo lại 300 | Giữ 300 | Request trùng có cần tăng version hoặc tạo event không? |
| Báo -1 | Từ chối | Trạng thái lỗi/mã phản hồi nào theo contract? |
| Bài dài 200 giây, báo 300 | Chưa được quyết | Có chặn, giới hạn hoặc cần metadata bài học? |
| Học viên chủ động học lại | Chưa được quyết cho trường này | Reset có tách event/field riêng không? |
| Tài khoản B gửi request cho A | Không được ghi/đọc trái quyền | Xác minh server-side identity, không tin accountId client |
| Hai transaction cùng cập nhật | Không bị ghi lùi theo quy tắc đã xác nhận | Bảo đảm nguyên tử và thử nghiệm cạnh tranh ở DB |

### Lớp bằng chứng tương ứng

- **Acceptance examples:** Người nghiệp vụ và Developers thống nhất ngữ nghĩa.
- **Unit TDD:** Quy tắc nhỏ đúng trong các ví dụ cục bộ.
- **Integration/concurrency tests:** DB, transaction và retry hoạt động đúng.
- **Contract/security tests:** Auth và API bảo vệ ranh giới.
- **Selected end-to-end tests:** Người học thực sự mở lại được bài phù hợp trong những tình huống quan trọng.

**Không phải mọi kỹ thuật trong bảng đều là “thực hành XP nguyên gốc”.** Chúng là những bổ sung theo rủi ro để một lựa chọn XP có thể bảo vệ chất lượng sản phẩm thực.

## 11. Pair programming: chọn khi feedback về thiết kế và tri thức đang quá chậm

**Pair programming** là hai người cùng làm trên một thay đổi, liên tục trao đổi để hiểu vấn đề, đưa quyết định thiết kế và kiểm chứng. Một biến thể quen thuộc là **driver** thực hiện thao tác code, **navigator** quan sát mục tiêu, rủi ro và hướng tiếp; cả hai chuyển vai linh hoạt.

### Khi nào pairing là lựa chọn tốt?

- Module concurrency chỉ có một người hiểu, tạo **single point of failure**.
- Lỗi khó tái hiện và cần hai góc nhìn kỹ thuật/kiểm thử.
- PR thường bị trả lại nhiều vòng vì thiết kế không được thảo luận sớm.
- Người mới cần phát triển năng lực với codebase phức tạp.
- Quy tắc dữ liệu và contract nhiều điều kiện cần kiểm tra ngay trong lúc viết.

### Một phiên pairing có mục tiêu

Trong 60–90 phút minh họa, hai Developer cùng làm:

1. Đọc acceptance examples về request đến muộn.
2. Viết test Red cho quy tắc hoặc tình huống concurrency được kiểm chứng.
3. Thảo luận ranh giới unit test và DB integration test.
4. Viết thay đổi nhỏ, chạy kiểm tra, cùng review diff.
5. Ghi quyết định về cách tránh lost update và kế hoạch test sau.
6. Kết thúc bằng việc cả hai có thể **giải thích, sửa và hỗ trợ** phần code.

Thời lượng trên chỉ là ví dụ, không phải chuẩn XP bắt buộc. Pairing có thể ngắn/dài, tại chỗ hoặc từ xa theo nhu cầu.

### Anti-pattern của pairing

| Tình huống | Vấn đề | Hành vi tốt hơn |
| --- | --- | --- |
| Một người code, người kia im lặng | Không có feedback hai chiều | Thỏa thuận mục tiêu, đặt câu hỏi và luân chuyển vai |
| Pairing chỉ để “kèm người yếu” | Tạo kỳ thị và bỏ lợi ích thiết kế | Pairing để chia sẻ tri thức và giảm rủi ro kỹ thuật |
| Mọi ticket đều buộc hai người bất kể bối cảnh | Có thể tốn cơ hội không tương xứng | Ưu tiên vùng rủi ro cao hoặc cần lan tỏa tri thức |
| Pairing thay mọi kiểm tra độc lập | Có thể vi phạm separation of duties | Giữ review/phê duyệt độc lập nếu chính sách bắt buộc |
| Cố tính số giờ pairing là chỉ số năng suất | Khuyến khích ghi hình thức | Đánh giá chất lượng, review wait và năng lực dự phòng |

### Lợi ích cần được kiểm chứng

Có ít vòng review trả lại hơn không? Có thêm người đủ hiểu module để hỗ trợ sự cố không? Lỗi cùng loại có giảm không? Không nên kết luận hiệu quả chỉ từ **số giờ hai người ngồi cùng nhau**.

## 12. Continuous Integration: khi lỗi phát hiện quá muộn

**Continuous Integration (CI)** là thực hành kết hợp những thay đổi nhỏ thường xuyên và kiểm chứng tự động để phát hiện sai lệch sớm. Trong XP, CI hỗ trợ giữ hệ thống ở trạng thái tích hợp, giảm xung đột và vòng sửa lỗi dài.

### Cơ chế tác động

~~~mermaid
flowchart TD
    A["Thay đổi nhỏ đã làm rõ"] --> B["Unit tests, static checks"]
    B --> C["Tích hợp theo chính sách"]
    C --> D["CI: build và tests liên quan"]
    D --> E{"Tín hiệu đạt?"}
    E -- "Không" --> F["Khoanh vùng, sửa khi diff còn nhỏ"]
    F --> B
    E -- "Có" --> G["Contract/integration kiểm chứng ranh giới"]
    G --> H{"Ranh giới đúng?"}
    H -- "Không" --> F
    H -- "Có" --> I["Đánh giá DoD và điều kiện tiếp theo"]
~~~

### Những lớp kiểm tra điển hình

| Lớp | Câu hỏi | Chú ý |
| --- | --- | --- |
| Static/lint/build | Code có hợp lệ và xây dựng được? | Không thay test nghiệp vụ |
| Unit tests | Quy tắc nhỏ có đúng? | Không tự phát hiện transaction race |
| Contract tests | Bên cung cấp và bên dùng hiểu cùng hợp đồng? | Mock một phía không chứng minh provider thật |
| Integration tests | Auth/API/DB/cache và transaction có hoạt động đúng? | Cần fixture, version và môi trường đáng tin |
| Selected E2E tests | Hành trình người dùng trọng yếu có hoạt động? | Ít, ổn định, tránh nhiều test flaky trùng lặp |
| Security/data checks | Quyền và toàn vẹn dữ liệu được giữ? | Dùng theo mức rủi ro và nghĩa vụ bắt buộc |
| Deployment checks | Artifact và môi trường sẵn sàng? | Deploy xanh chưa chứng minh outcome |

### Pipeline minh họa

~~~yaml
# Chỉ mô tả ý tưởng, KHÔNG phải cấu hình CI chạy trực tiếp.
on_small_change:
  - build_and_static_checks
  - unit_tests
  - changed_contract_tests
before_integration:
  - required_review
  - required_checks_green
after_integration:
  - progress_db_concurrency_tests
  - auth_api_integration_tests
  - selected_end_to_end_flow
release_when_allowed:
  - definition_of_done_verified
  - observability_and_recovery_ready
~~~

### CI xanh là điều kiện cần hay đủ?

Nếu pipeline chưa kiểm tra đồng thời, 1.000 unit tests vẫn có thể xanh trong khi DB ghi lùi. CI chỉ phản hồi trên **những giả định và test đã được đưa vào**. Do đó cải thiện CI cần xem **độ đúng và độ ổn định của tín hiệu**, không chỉ chạy nhiều hơn.

### Xử lý pipeline đỏ

- Phân biệt lỗi sản phẩm, lỗi cấu hình/môi trường, test flaky và thay đổi hợp đồng có chủ đích.
- Sửa sớm khi thay đổi còn nhỏ; không coi chạy lại tới khi xanh là chiến lược.
- Nếu cần cách ly test flaky, phải ghi owner, rủi ro, kiểm chứng thay thế nếu được phép và thời hạn sửa.
- Không bỏ kiểm tra bắt buộc để cải thiện throughput ngắn hạn.

### Tần suất tích hợp

Không có quy tắc Scrum bắt mỗi người merge đúng một số lần/ngày. Hãy ưu tiên **thay đổi đủ nhỏ để feedback đến sớm**, phù hợp chính sách review và mức rủi ro của sản phẩm.

## 13. Refactoring: cải thiện cấu trúc để lần thay đổi sau an toàn hơn

**Refactoring** là thay đổi cấu trúc bên trong code mà **giữ hành vi quan sát được theo phạm vi đã xác định**. Nó có thể làm giảm trùng lặp, tách phụ thuộc, làm rõ tên và giảm sự phức tạp khiến thay đổi nhỏ gây lỗi lớn.

### Ví dụ khái niệm

Trước:

~~~text
Controller vừa:
  - đọc phiên đăng nhập
  - quyết định quyền của khóa học
  - so sánh tiến độ
  - truy vấn và ghi DB
  - tạo HTTP response
  - gửi event telemetry
~~~

Sau một số bước refactor nhỏ có test:

~~~text
Controller:
  - kiểm soát giao tiếp HTTP và dữ liệu phiên

Authorization boundary:
  - xác nhận quyền theo chính sách

ProgressPolicy:
  - quy tắc nghiệp vụ thuần, dễ unit-test

ProgressRepository:
  - lưu dữ liệu với cơ chế transaction/đồng thời đã chọn

Telemetry boundary:
  - ghi tín hiệu được phép, không lộ dữ liệu nhạy cảm
~~~

Đây là **phân tách trách nhiệm minh họa**, không bắt buộc mọi codebase phải tạo đúng năm class/layer. Càng nhiều abstraction không tự tốt hơn.

### Chiến lược refactor an toàn

1. Xác định hành vi hiện tại cần giữ và phần chưa có test.
2. Thêm những kiểm tra bảo vệ **hành vi quan trọng** trước khi đổi cấu trúc.
3. Thực hiện các bước nhỏ, chạy test sau từng bước.
4. Review mức độ giảm phức tạp thay vì số file/class mới tạo.
5. Kiểm tra integration/security nếu đổi ranh giới dữ liệu hoặc quyền.
6. Tránh trộn thay đổi hành vi nghiệp vụ với thay đổi cấu trúc không cần thiết trong cùng một diff khó đọc.

### Refactor khác sửa lỗi và thêm tính năng

- **Refactor:** Cấu trúc đổi, hành vi quan sát được giữ như đã xác định.
- **Bug fix:** Hành vi không mong muốn được sửa, cần test thể hiện trước/sau.
- **Feature:** Bổ sung khả năng hoặc quy tắc mới theo nhu cầu.

Trong thực tế có thể cần làm cùng giai đoạn, nhưng nên giữ **ranh giới quyết định và bằng chứng** rõ để người review dễ hiểu.

## 14. Simple design và YAGNI: giảm lỗi từ cấu trúc phức tạp không cần thiết

**Simple design** ưu tiên giải pháp đủ đơn giản để đáp ứng nhu cầu hiện đã hiểu, dễ kiểm chứng và dễ thay đổi. **YAGNI (You Aren't Gonna Need It)** nhắc đừng xây trước những tính năng/abstraction chưa có bằng chứng cần dùng.

### Ví dụ

Đội chuẩn bị sửa lỗi tiến độ. Một đề xuất là:

> “Hãy xây hẳn một engine đồng bộ đa thiết bị tổng quát, plugin hóa tất cả kiểu media, thêm event bus, cache phân tán và framework conflict resolution cho mọi trường hợp tương lai.”

Có thể những khả năng này sẽ hữu ích trong sản phẩm khác, nhưng với vấn đề đã biết **request cũ ghi lùi highestCompletedSecond**, nên hỏi:

- Quy tắc nghiệp vụ tối thiểu đã xác nhận là gì?
- Kiểm soát nguyên tử nào DB đang hỗ trợ?
- Có thể thêm một test và thay đổi nhỏ đúng chỗ không?
- Đâu là yêu cầu thực về tải, availability, dữ liệu và audit?
- Chúng ta sẽ biết lúc nào cần mở rộng thiết kế?

### Không dùng YAGNI để bỏ chất lượng

“Chưa cần” **không áp dụng** với phân quyền bắt buộc, kiểm soát mất dữ liệu, khả năng khôi phục có nghĩa vụ hay DoD hiện hành. Đơn giản không phải cắt giảm điều kiện an toàn; đơn giản là tránh **cấu trúc giả định không phục vụ nhu cầu và rủi ro đã biết**.

### Kết hợp TDD + simple design

Một test hành vi cụ thể khuyến khích API vừa đủ; refactoring giúp mở rộng thiết kế khi xuất hiện ca mới. Bộ ba tạo vòng **học qua ví dụ → mã nhỏ → thiết kế thích nghi**, không phải “thiết kế toàn bộ tương lai từ đầu”.

## 15. Small releases: phản hồi người dùng sớm hơn, nhưng không phải phát hành code lỗi

**Small releases** giảm kích thước những thay đổi được đưa tới người dùng theo điều kiện sản phẩm và chính sách. Khi rủi ro phơi nhiễm có thể kiểm soát, phản hồi đến nhanh hơn, giúp đội thấy nhu cầu thực thay vì giả định.

### Phân biệt bốn trạng thái

| Trạng thái | Ý nghĩa | Không đồng nghĩa |
| --- | --- | --- |
| **Merge** | Thay đổi vào codebase tích hợp | Increment đã đạt DoD |
| **Increment đạt DoD** | Phần sản phẩm sử dụng được, đáp ứng chuẩn chất lượng | Đã deploy/release cho mọi người |
| **Deploy** | Đưa artifact vào môi trường | Người dùng đã được bật chức năng |
| **Release** | Cung cấp khả năng cho nhóm người dùng theo chính sách | Outcome đã đạt hoặc rủi ro bằng không |

### Một lộ trình nhỏ cho tiến độ học

1. Giao phần sửa **quy tắc highestCompletedSecond**, đã kiểm chứng đồng thời và phân quyền.
2. Đưa ra nhóm người dùng đủ điều kiện theo chính sách, với telemetry an toàn và khả năng phản ứng.
3. Xác nhận lỗi ghi lùi có còn xuất hiện trong tình huống đã biết không.
4. Xem phản hồi người dùng về vị trí tiếp tục; có thể nhận ra cần phân biệt **bookmark** với **tiến độ hoàn tất**.
5. Chọn lát cắt tiếp theo theo Product Goal, không mở rộng kỹ thuật trước khi cần.

### Feature flag có đủ không?

Feature flag có thể tách deploy khỏi bật khả năng, nhưng **không biến code chưa đạt DoD thành Done** và không thay kiểm tra quyền tại server. Cần test những trạng thái cần hỗ trợ, người có quyền bật/tắt và kế hoạch xóa flag cũ.

### Rollback có thể không khôi phục dữ liệu

Nếu sửa tiến độ kéo theo migration, rollback phiên bản code chưa chắc hoàn tác các bản ghi đã bị thay đổi. Đội cần kế hoạch **đối soát, backup/restore và tương thích cũ–mới** phù hợp, không lấy small releases làm lý do bỏ đánh giá dữ liệu.

## 16. Collective code ownership, coding standards và sustainable pace

Ba thực hành này thường không có “demo đẹp” nhưng hỗ trợ khả năng chất lượng được duy trì khi nhóm lớn lên hoặc có nhân sự nghỉ.

### Collective code ownership — giảm phụ thuộc một cá nhân

Tư duy ownership chung khuyến khích những người trong đội đủ năng lực có thể cải thiện vùng code chung, cùng bảo vệ test và thiết kế. Điều đó **không có nghĩa mọi người được sửa bất kỳ dữ liệu hoặc môi trường production nào**; quyền truy cập, review độc lập và phê duyệt vẫn tuân thủ chính sách.

Ví dụ sau vài phiên pairing, hai Developer ngoài tác giả ban đầu có thể đọc, sửa và review module tiến độ với test phù hợp. Đây là tín hiệu giảm bottleneck tốt hơn việc đếm số người được thêm vào nhóm chat.

### Coding standards — giúp diff và ý định dễ hiểu

Quy ước tên, định dạng, cấu trúc test, cách biểu đạt lỗi và quản lý dependency có thể giảm tranh luận vụn trong review. **Có thể tự động hóa** format/lint để con người tập trung vào logic, contract, quyền và thiết kế.

Không cần dùng cùng một style trên mọi ngôn ngữ/repository nếu không có lý do chung; tiêu chuẩn phải **phục vụ khả năng cộng tác và chất lượng**, không chỉ đẹp bảng điểm.

### Sustainable pace — bảo vệ chất lượng dài hạn

Đội liên tục overtime để hoàn tất story point có thể bỏ qua review, test hoặc phản hồi, sau đó mất nhiều thời gian sửa lỗi. **Nhịp bền vững** cần kế hoạch phù hợp năng lực, minh bạch phụ thuộc, xử lý sự cố và quyền ưu tiên.

Không dùng khẩu hiệu sustainable pace để từ chối trách nhiệm xử lý sự cố khẩn; cần **cơ chế ứng phó và luân phiên** được tổ chức có trách nhiệm, tránh coi khủng hoảng liên tục là bình thường.

## 17. Chọn ít thực hành có quan hệ nhân quả rõ, không chọn theo độ nổi tiếng

Với vấn đề **request cũ ghi lùi tiến độ**, ta có thể so sánh các phương án:

| Phương án thử | Cơ chế chính | Phần giải quyết | Điều còn thiếu |
| --- | --- | --- | --- |
| **Chỉ tăng số unit test** | Nhiều ví dụ logic được bảo vệ | Quy tắc thuần như highestCompletedSecond | Transaction race, auth, contract, feedback test |
| **Chỉ yêu cầu pair mọi PR** | Feedback sớm và lan tỏa tri thức | Review chậm, hiểu code chưa đồng đều | Test và transaction guarantee cần kiểm chứng |
| **Chỉ merge thường xuyên hơn** | Giảm diff và tuổi nhánh | Xung đột tích hợp đến muộn | CI phải test đúng failure mode, không chỉ build |
| **Chỉ refactor module lớn** | Cải thiện cấu trúc | Độ khó sửa/đặt test | Chưa chắc nghiệp vụ đúng, có thể làm tăng rủi ro nếu thiếu test |
| **TDD quy tắc + pairing điểm khó + CI kiểm tra DB** | Kết hợp feedback nghiệp vụ, thiết kế, đồng thời và tích hợp | Bao phủ các nguyên nhân đã điều tra | Vẫn cần kiểm chứng quyền, dữ liệu, DoD và outcome |

Không nhất thiết chọn phương án cuối nếu baseline cho thấy **một nguyên nhân khác**. Ví dụ nếu DB đã bảo đảm nguyên tử nhưng lỗi đến từ cache hiển thị sai phiên, cần tập trung kiểm chứng **session isolation và phản hồi client**.

### Một nguyên tắc xếp thứ tự

**Giảm nguy cơ gây hại rõ ràng trước, sau đó cải thiện tốc độ phản hồi.** Nếu đã biết có lỗi phân quyền hoặc mất dữ liệu, không được trì hoãn biện pháp an toàn chỉ để đủ bốn tuần đo A/B test của một practice.

## 18. Thiết kế một chuỗi bằng chứng từ ví dụ đến Increment

Những thực hành XP có thể tạo feedback kỹ thuật nhưng sản phẩm cần **nhiều lớp chứng cứ** để được coi là sử dụng được.

~~~mermaid
flowchart TD
    A["Vấn đề người học + Product Goal"] --> B["AC và ví dụ về tiến độ/quyền"]
    B --> C["TDD: kiểm chứng quy tắc thuần"]
    C --> D["Pairing/refactoring: thiết kế dễ kiểm tra"]
    D --> E["CI: build + tests nhanh"]
    E --> F["Integration tests: DB, retry, Auth"]
    F --> G["DoD: Increment tích hợp và dùng được"]
    G --> H["Release theo chính sách"]
    H --> I["Phản hồi người dùng + vận hành"]
    I --> A
~~~

### Gắn từng lớp với trách nhiệm

| Lớp | Người có thể đóng góp | Bằng chứng |
| --- | --- | --- |
| Ý nghĩa bài gần nhất, học lại và hoàn tất | Product Owner/người nghiệp vụ, Developers, tester | Acceptance examples được xác nhận |
| Quy tắc thuần | Developers | Unit tests Red–Green–Refactor và code review |
| Cơ chế đồng thời ở DB | Developers, chuyên môn dữ liệu | Integration tests có tranh chấp thực, transaction analysis |
| Quyền truy cập và phiên | Developers, người có thẩm quyền bảo mật theo chính sách | Security/integration tests, review khi bắt buộc |
| Tích hợp provider–consumer | Nhóm UI/API và người liên quan | Contract tests, smoke tests phiên bản được hỗ trợ |
| Increment chất lượng | Scrum Team với Developers chịu trách nhiệm DoD | Bằng chứng DoD trên phần sản phẩm tích hợp |
| Phát hành/ứng phó | Vai trò được ủy quyền theo release/incident policy | Telemetry, quyết định release, kế hoạch khôi phục |

Người thực hiện có thể kiêm nhiều chuyên môn; bảng không tạo thêm một hệ cấp bậc giữa PO, Scrum Master và Developers.

## 19. Thiết kế kiểm thử concurrency và idempotency ngoài phạm vi unit TDD

Đây là phần quan trọng nhất trong tình huống tiến độ: **code đúng khi chạy một mình không chứng minh ghi dữ liệu đúng khi chạy đồng thời**.

### Một integration scenario tối thiểu

1. Tạo hai request **được xác thực** của cùng học viên cho cùng bài học bằng dữ liệu thử có quyền hợp lệ.
2. Thiết lập dữ liệu ban đầu, ví dụ **highestCompletedSecond = 100**.
3. Cho hai request báo giá trị **120** và **300** đến DB theo thứ tự có thể tái hiện.
4. Kiểm tra sau khi cả hai hoàn tất, giá trị được lưu phải là **300** theo quy tắc đã chốt, bất kể thứ tự ghi.
5. Kiểm tra một request lặp lại không tạo trạng thái sai hoặc tác dụng phụ không được phép.
6. Lặp với các thứ tự xen kẽ khác nhau và cùng phạm vi transaction thực tế.

### Những gì cần làm rõ trước test

- Cơ chế nào bảo đảm cập nhật nguyên tử: câu lệnh UPDATE có điều kiện, transaction/locking, version check hay giải pháp đã được kiến trúc lựa chọn?
- Một request cùng dữ liệu nhưng khác request ID có cần tạo event mới không?
- Nếu cùng lúc có **học lại từ đầu**, đây có phải một operation độc lập cần version/command khác không?
- Nếu API trả conflict, client retry thế nào cho an toàn?
- Nếu request đến từ tài khoản khác, backend kiểm soát **identity và authorization** ở ranh giới nào?

### Cẩn trọng với test “giả lập đồng thời”

Một unit test gọi hàm hai lần liên tiếp **không tái tạo hai transaction cùng lúc**. Một integration test sử dụng database giả trong memory có thể có hành vi isolation khác production. Đội nên chọn môi trường đại diện thích hợp, thiết lập test có thể tái hiện điều kiện cạnh tranh, và kiểm tra thêm bằng quan sát production được phép.

### Không viết SQL cụ thể khi chưa biết hệ DB

Các giải pháp nguyên tử có cú pháp và semantics khác nhau theo database. Một hướng chung như **cập nhật giá trị lớn nhất trong một thao tác có tính nguyên tử** có thể hữu ích cho rule monotonic, nhưng phải xác minh kỹ **transaction isolation, quyền, schema, replication và contract** của hệ thống thực.

## 20. Tích hợp XP với Scrum: thực hành kỹ thuật hỗ trợ cam kết chất lượng

Scrum và XP giải những câu hỏi khác nhau:

- **Scrum** giúp Scrum Team có trách nhiệm, mục tiêu và cơ hội kiểm tra–thích nghi để tạo Increment có giá trị.
- **XP** cung cấp một số thực hành phát triển giúp Developers nhận feedback kỹ thuật sớm, cải thiện thiết kế và bảo vệ chất lượng.

### Một Sprint với XP có thể trông thế nào?

| Mốc | Scrum cung cấp gì? | XP bổ sung điều gì? |
| --- | --- | --- |
| Product Backlog refinement | Làm rõ Product Goal, PBI, rủi ro, thứ tự | Acceptance examples, thảo luận thiết kế đơn giản |
| Sprint Planning | Scrum Team xác định Sprint Goal, Developers chọn PBI và lập kế hoạch | Chia lát cắt nhỏ, lên kế hoạch test trước và tích hợp sớm |
| Công việc hằng ngày | Developers thích nghi Sprint Backlog hướng Sprint Goal | TDD, pairing, CI, refactoring và review |
| Kiểm chứng Increment | Definition of Done là tiêu chuẩn chất lượng | Test nhiều lớp, CI và thiết kế đáng tin giúp đạt DoD |
| Sprint Review | Kiểm tra Increment và tiến triển Product Goal | Small releases và bằng chứng feedback có thể giúp Review thực chất |
| Sprint Retrospective | Cải tiến chất lượng và hiệu quả | Quan sát vòng rework, pipeline, pairing, chất lượng thiết kế |

### Những điểm phải giữ đúng theo Scrum

- Product Owner chịu trách nhiệm tối đa hóa giá trị và Product Backlog, không trực tiếp quyết định mọi kỹ thuật.
- Developers tạo kế hoạch Sprint, tuân thủ DoD, thích nghi Sprint Backlog và tạo Increment.
- Scrum Master hỗ trợ Scrum và hiệu quả Scrum Team, không biến thành người phân task TDD/CI cho từng Developer.
- Nếu nhiều Scrum Team cùng một sản phẩm, họ chia sẻ Product Goal, Product Backlog, Product Owner và **cùng định nghĩa/tuân thủ một DoD**.
- Một PBI chưa đạt DoD không được coi là phần của Increment hoàn thành.

### XP không miễn nghĩa vụ phát hành

TDD, CI và pairing không cho phép bỏ bảo mật hoặc nghĩa vụ dữ liệu. Nếu thay đổi cần review độc lập hay migration được kiểm chứng, điều đó vẫn phải được thực hiện theo chính sách.

## 21. Tích hợp XP với Kanban: cải thiện dòng chảy mà không ép Sprint

Một đội phát triển hoặc hỗ trợ có thể chọn cách quản lý luồng theo Kanban và đưa XP vào nơi dòng việc đang nghẽn.

### Ví dụ workflow

~~~text
Ready
  -> Đang làm rõ hành vi/test
  -> Phát triển + TDD/pairing khi phù hợp
  -> Review và CI
  -> Tích hợp/kiểm chứng DoD
  -> Done
~~~

Không cần mọi trạng thái có một cột riêng; quan trọng là **workflow thực** và các chính sách chuyển trạng thái được hiểu rõ.

### Tín hiệu Kanban hỗ trợ lựa chọn XP

| Quan sát flow | Giả thuyết cần kiểm tra | Thực hành có thể thử |
| --- | --- | --- |
| Item già thường chờ review của một chuyên gia | Tri thức tập trung và PR khó đọc | Pairing + ownership chung + PR nhỏ |
| Nhiều item quay lại từ Test về Doing | Test/hành vi được làm rõ muộn | TDD + acceptance examples + CI |
| WIP cao và có nhiều nhánh sống lâu | Bắt đầu thêm trước khi hoàn tất tích hợp | Small changes, CI, WIP limit |
| Cycle time dài do lỗi pipeline không đáng tin | Flaky và môi trường kéo dài vòng feedback | Cải thiện CI/test fixture, phân loại lỗi |
| Nhiều item Done nhưng production lỗi tăng | Done policy không phản ánh chất lượng | Rà DoD/quality policy và kiểm chứng theo rủi ro |

### Không nhầm giới hạn WIP là một thực hành XP bắt buộc

**WIP limit** thuộc hướng quản lý flow, thường gắn với Kanban. Đội có thể kết hợp nó với XP để tập trung **finish before start**, nhưng không nên tuyên bố đó là một bước bắt buộc của mọi mô hình XP.

### Tránh tối ưu việc riêng từng người

Nếu Developers được thưởng số item đang làm, họ có thể bỏ review của đồng đội để kéo ticket mới. Pairing và ownership chung chỉ phát huy khi nhóm coi **hoàn tất Increment chất lượng** quan trọng hơn làm mọi người đều bận rộn.

## 22. Xây giả thuyết can thiệp cho tình huống ghi lùi tiến độ

Từ phân tích failure mode, ta tách **hai giả thuyết liên quan nhưng khác nhau**, tránh dồn mọi thực hành thành một giải pháp không thể đánh giá.

### Giả thuyết A: sai quy tắc nghiệp vụ và feedback thiết kế muộn

> “Nếu Developers và Product Owner chốt ví dụ nghiệp vụ trước, rồi dùng TDD cho logic highestCompletedSecond và refactor thành một policy dễ kiểm chứng, các lỗi quy tắc phát hiện trong review/integration có thể giảm.”

**Cơ chế:** Ví dụ rõ → test thất bại trước thay đổi → implementation nhỏ → regression chạy nhanh.

**Bằng chứng:** Test tái hiện ca 300/120; số vòng rework do quy tắc; thời điểm lỗi được tìm thấy; mức độ thay đổi dễ hiểu.

**Giới hạn:** Không chứng minh transaction và phân quyền đúng.

### Giả thuyết B: lỗi tranh chấp DB và tích hợp phát hiện muộn

> “Nếu pair ở đoạn transaction khó, tích hợp thay đổi nhỏ thường xuyên và chạy integration/concurrency test trong CI, lỗi ghi lùi do request đến sai thứ tự có thể được phát hiện trước release.”

**Cơ chế:** Trao đổi thiết kế sớm → cơ chế ghi nguyên tử được kiểm chứng → pipeline kiểm tra ranh giới thật.

**Bằng chứng:** Test chạy với DB đại diện, các kiểu xen kẽ request; thời gian feedback; lỗi integration và lỗi sau phát hành.

**Giới hạn:** CI có thể chậm/flaky nếu dữ liệu test và môi trường chưa đủ tin cậy.

### Hai giả thuyết không loại trừ nhau

Đội có thể triển khai đồng thời vì cần khắc phục rủi ro dữ liệu, nhưng **không được quy riêng lợi ích cho một thực hành** khi nhiều thay đổi xảy ra cùng lúc. Khi đánh giá, ghi rõ phạm vi, thứ tự can thiệp và các yếu tố cùng thay đổi.

## 23. Kế hoạch thử nghiệm bốn tuần theo một vấn đề chất lượng

Lịch dưới đây là **mẫu học tập**, không phải cam kết rằng lỗi nghiêm trọng có thể để tồn tại thêm bốn tuần. Nếu đã có rủi ro mất dữ liệu hoặc lộ quyền đang hoạt động, **ưu tiên xử lý an toàn và ứng phó theo chính sách ngay**, sau đó đánh giá cải tiến quy trình.

### Tuần 1 — Hiểu failure mode và có baseline

- Chọn một nhóm item cùng loại, liên quan ghi tiến độ/retry/concurrency.
- Phân tích timeline của hai đến ba lỗi thật bằng dữ liệu có quyền.
- Cùng PO xác nhận ngữ nghĩa **highestCompleted** và **playback bookmark**.
- Ghi mức hiện tại của rework, thời gian review, lỗi CI/flaky và item đang mở.
- Xác định test nào có thể tái hiện được lỗi trong môi trường an toàn.
- Làm rõ DoD, quyền dữ liệu và những kiểm soát bắt buộc.

**Đầu ra:** Bản mô tả vấn đề, failure mode được kiểm chứng hoặc mức chưa biết, giả thuyết và guardrail.

### Tuần 2 — Thử TDD + làm rõ ví dụ trên lát cắt nhỏ

- Chọn quy tắc thuần hoặc một điểm thay đổi phù hợp để viết test trước.
- Pair trong một phiên có mục tiêu để lan tỏa hiểu biết về quy tắc.
- Làm Red–Green–Refactor từng thay đổi nhỏ; chạy lại unit tests.
- Thêm integration/concurrency test cho đường DB quan trọng.
- Tích hợp thường xuyên trong phạm vi chính sách, không chờ một nhánh lớn cuối Sprint.

**Đầu ra:** Những test mới đúng failure mode, code dễ kiểm chứng và một lát cắt đã được tích hợp theo DoD khi đủ điều kiện.

### Tuần 3 — Cải thiện feedback và reliability

- Xem pipeline có trả phản hồi đủ nhanh/đáng tin không; phân loại flaky.
- Điều chỉnh fixture/DB test để có thể tái hiện cạnh tranh.
- Pair hoặc review chéo ở phần chỉ một người hiểu, luân chuyển tri thức.
- Quan sát rework, blocker, thời gian chờ review, lỗi test và chất lượng.
- Chặn hoặc sửa kịp thời khi phát hiện rủi ro dữ liệu.

**Đầu ra:** Một vòng phản hồi hoạt động ổn định hơn, không chỉ nhiều test hơn.

### Tuần 4 — Đánh giá và quyết định

- So sánh những thay đổi có phạm vi tương đương và cùng định nghĩa metric.
- Xem lỗi ghi lùi có được phát hiện trước release hoặc giảm trong điều kiện có thể quan sát không.
- Xem cycle time, work item age và chi phí test/CI có cải thiện hay bị kéo dài.
- Ghi những biến cùng thay đổi: phiên bản API, test infrastructure, người review, tải, loại item.
- Quyết định giữ, sửa, dừng hoặc mở rộng; chia sẻ bối cảnh áp dụng.

**Đầu ra:** Kết luận có giới hạn, action tiếp theo và trách nhiệm được xác nhận.

### Mẫu experiment card

~~~text
VẤN ĐỀ:
  Request cập nhật tiến độ đến lệch thứ tự có thể làm dữ liệu ghi lùi.

FAILURE MODE:
  Rule chưa được xác nhận rõ; thiếu transaction/concurrency test;
  tích hợp và review thường đến muộn.

GIẢ THUYẾT:
  TDD rule + pairing điểm khó + CI chạy test DB đồng thời
  có thể phát hiện lỗi sớm và giảm rework/lỗi thoát.

CAN THIỆP:
  1. Chốt acceptance examples.
  2. Red–Green–Refactor trên logic thuần.
  3. Pair kiểm tra cơ chế DB; tích hợp test vào CI.

ĐO:
  Lỗi ghi lùi được xác nhận; thời điểm phát hiện;
  rework theo item; CI feedback; flaky;
  cycle time, aging WIP và chất lượng sản phẩm.

GUARDRAIL:
  DoD, quyền tài khoản, không lộ dữ liệu,
  kiểm tra transaction, khôi phục và sustainable pace.

QUYẾT ĐỊNH:
  Giữ/sửa/bỏ/mở rộng; người có quyền, bằng chứng,
  yếu tố gây nhiễu và ngày xem lại.
~~~

## 24. Đo tác động: không dùng số test hoặc coverage như chứng chỉ chất lượng

### Ba tầng chỉ số cần xem cùng nhau

| Tầng | Ví dụ đo | Điều chỉ số có thể giúp trả lời |
| --- | --- | --- |
| **Adoption/hành vi** | Có vòng Red–Green–Refactor, có pairing ở vùng rủi ro, code được tích hợp thường xuyên? | Thực hành có đang được sử dụng đúng mục đích? |
| **Feedback/dòng kỹ thuật** | Thời gian CI, flaky, test thất bại đúng failure mode, rework và review wait | Lỗi có được phát hiện sớm hơn và sửa với chi phí thấp hơn? |
| **Kết quả chất lượng/sản phẩm** | Lỗi ghi lùi thoát ra production, sự cố dữ liệu, task success, Increment đạt DoD | Chất lượng và giá trị người dùng có cải thiện? |

### Coverage là tín hiệu, không phải kết luận

- Coverage cao có thể đi cùng test kém assert hoặc bỏ ca concurrency.
- Coverage thấp không tự đồng nghĩa mọi thay đổi đều nguy hiểm; cần xem rủi ro và vùng chưa được kiểm chứng.
- Ép 100% coverage như KPI thưởng phạt có thể khiến đội viết test hình thức hoặc bỏ trường hợp khó.
- Ưu tiên **bài test bắt đúng failure mode** cùng kiểm chứng tích hợp, không chạy theo một tỷ lệ đẹp.

### Độ tin cậy pipeline

Thời gian pipeline trung bình 10 phút không cho biết một số lần chạy mất 40 phút hay tỷ lệ flaky bao nhiêu. Có thể xem **trung vị và phân vị cao**, phân nhóm test và nguồn lỗi để ra quyết định, nhưng phải dùng mẫu đủ hiểu và cùng cách tính.

### Điều không nên quy kết

Nếu số bug sau release giảm từ 4 xuống 1 trong bốn tuần, không được lập tức nói **TDD giúp giảm lỗi 75%** khi:

- Mẫu nhỏ và việc thay đổi độ khó khác nhau.
- Một số lỗi đã được xử lý khẩn trước thử nghiệm.
- Cùng kỳ đội thêm transaction check và sửa hạ tầng.
- Số người dùng, phiên bản client hoặc năng lực phát hiện thay đổi.
- Một lỗi nghiêm trọng có thể có tác động lớn hơn nhiều lỗi nhỏ.

Cần ghi kết quả **như quan sát**, kết hợp định tính, guardrail và thời gian đủ phù hợp trước khi khẳng định xu hướng.

## 25. Trường hợp A: lỗi logic nghiệp vụ lặp lại sau các lần sửa nhỏ

### Bối cảnh

Một module tính trạng thái hoàn tất bài học có nhiều điều kiện: tỷ lệ xem, bài học bắt buộc, quyền xem và tình huống người học mở lại. Mỗi lần Developer sửa một nhánh điều kiện, một nhánh khác có thể sai. Review thường tìm thấy lỗi sau khi code đã viết khá nhiều.

### Failure mode giả định

- Quy tắc nghiệp vụ được diễn đạt bằng lời nhưng **thiếu ví dụ biên**.
- Code có nhiều nhánh lồng nhau và khó kiểm thử độc lập.
- Người viết mới thêm điều kiện mà không có regression tests.
- DoD yêu cầu test hành vi liên quan nhưng những test đó thường đến cuối.

### Chọn thực hành

**Ưu tiên 1: Làm rõ acceptance examples với người hiểu nghiệp vụ.** Nếu điều kiện hoàn tất còn tranh cãi, viết test trước có nguy cơ đóng băng một hiểu lầm.

**Ưu tiên 2: TDD với từng quy tắc nhỏ.** Viết một ví dụ thất bại, thêm mã tối thiểu, tiếp tục với trường hợp đối nghịch/biên.

**Ưu tiên 3: Refactoring/simplest design.** Khi test bảo vệ hành vi, tách logic thuần khỏi truy cập dữ liệu và giảm nhánh khó đọc.

### Tại sao không chọn CI là can thiệp duy nhất?

Nếu CI đã chạy đầy đủ những test **không kiểm tra trường hợp biên**, việc chạy thường xuyên hơn vẫn có thể cho đèn xanh giả. Cần **nâng chất lượng test và hiểu nghiệp vụ**, sau đó CI giúp thực thi chúng thường xuyên.

### Chỉ số và guardrail

| Giả thuyết | Tín hiệu | Guardrail |
| --- | --- | --- |
| Test trước giúp bắt lỗi quy tắc sớm | Vòng rework do logic, ca lỗi được phát hiện trước merge | Không ép 100% coverage hoặc tạo test không có assert |
| Refactor giúp thay đổi dễ hơn | Kích thước diff, thời gian hiểu/sửa lỗi, review feedback | Giữ hành vi đã xác nhận, chạy regression |
| Ví dụ nghiệp vụ rõ giúp bớt tranh cãi | Số lần phải hỏi lại về acceptance, thay đổi do hiểu sai | Không tự đặt quy tắc khi PO/người nghiệp vụ chưa xác nhận |

### Quyết định sau thử

Nếu test nhanh, dễ hiểu nhưng lỗi vẫn chủ yếu xuất hiện ở transaction/cache thật, cần **giữ lợi ích unit TDD nhưng chuyển trọng tâm sang kiểm chứng tích hợp**, không ép đội viết thêm hàng trăm unit tests.

## 26. Trường hợp B: pipeline xanh nhưng lỗi tích hợp đến sát release

### Bối cảnh

Hai nhóm phát triển ứng dụng học tập và API tiến độ. Mỗi bên test riêng với mock. Provider thay trường response hoặc mã lỗi; consumer được cập nhật sau. Các nhánh lớn thường hợp nhất ngay trước mốc phát hành.

### Chẩn đoán

- Unit tests không bao phủ **hợp đồng provider–consumer thực**.
- PR và nhánh lâu khiến sai lệch tích tụ.
- Môi trường tích hợp không đồng nhất phiên bản, test đôi lúc flaky.
- Review/communication về API quá muộn.

### Thực hành XP được chọn

**Continuous Integration + changes nhỏ** là trọng tâm, vì failure mode chính là phản hồi về tương thích đến muộn.

**Pairing ngắn giữa các bên hoặc trong phần khó** có thể giúp thống nhất cách xử lý lỗi. **Coding standards/collective ownership** giúp giảm phụ thuộc vào một người giữ contract.

### Kỹ thuật bổ trợ cần có

**Contract testing** và integration tests theo các phiên bản còn được hỗ trợ là những kỹ thuật cần thiết để CI thực sự **kiểm tra đúng ranh giới**. Đây là phần bổ trợ, không nên nói “thực hành XP bắt buộc mọi đội dùng đúng một công cụ contract testing”.

### Tại sao không chỉ thêm người kiểm thử thủ công?

Thêm người test cuối Sprint có thể giúp phát hiện nhiều lỗi hơn nhưng chưa giảm **độ trễ phát hiện**, vẫn còn nhiều rework và code đã lệch lâu. Phản hồi liên tục có thể rẻ hơn nếu test đáng tin và thay đổi nhỏ.

### Dấu hiệu cải thiện

- API break được phát hiện ở PR/CI thay vì môi trường release.
- PR nhỏ, thời gian fix build đỏ ngắn hơn.
- Các client version được hỗ trợ vẫn hoạt động qua thay đổi.
- Cycle time của lát cắt tích hợp không tăng do chờ một lô review cuối.
- Lỗi production và độ tin cậy của pipeline **không suy giảm**.

## 27. Trường hợp C: module khó, một chuyên gia duy nhất luôn bị chờ

### Bối cảnh

Một Developer là người duy nhất hiểu transaction ghi tiến độ. Mọi thay đổi phải chờ người này review; khi họ nghỉ, team không dám sửa bug. Cần giảm rủi ro phụ thuộc cá nhân mà vẫn giữ chất lượng.

### Thực hành được cân nhắc

| Ứng viên | Cơ chế | Quyết định |
| --- | --- | --- |
| **Pair programming theo mục tiêu** | Người chuyên môn truyền mô hình hệ thống trong lúc giải quyết lỗi thật | Ưu tiên ở thay đổi concurrency và schema |
| **Collective code ownership** | Nhiều Developer có năng lực và quyền hợp lệ sửa/test module | Áp dụng từng bước, giữ review thích hợp |
| **Coding standards và test dễ hiểu** | Giảm chi phí đọc code và review | Tự động hóa quy tắc đơn giản, viết ví dụ rủi ro |
| **TDD/CI** | Test giúp người mới tự kiểm tra thay đổi | Dùng đúng vùng thay đổi, không thay hiểu transaction |
| **Thêm một cổng phê duyệt của chuyên gia** | Tăng tính độc lập trong ngắn hạn nhưng cũng tăng hàng chờ | Không chọn làm giải pháp dài hạn nếu chỉ củng cố bottleneck |

### Lộ trình nhỏ

1. Chọn một lỗi tái hiện được trong module, không bắt đầu bằng refactor lớn.
2. Chuyên gia pair với một người khác, cùng đọc timeline/test và viết thay đổi nhỏ.
3. Người thứ hai giải thích lại failure mode và tự bổ sung một test.
4. Luân chuyển reviewer/pair khi đạt đủ năng lực, theo quyền được ủy quyền.
5. Đo thời gian review, lỗi và khả năng nhiều người cùng hỗ trợ sự cố.

### Giới hạn quan trọng

Một số hệ thống yêu cầu **phân tách nhiệm vụ và quyền phê duyệt độc lập**. Collective ownership không đồng nghĩa bỏ những quyền đó. Nếu test và quyền không đủ, cần phối hợp người có thẩm quyền thay vì tự tuyên bố “ai cũng có thể merge”.

## 28. Trường hợp D: đội phát hành lớn, thiếu phản hồi sản phẩm

### Bối cảnh

Đội xây cả quý mới phát hành các chức năng gợi ý bài học, quản lý danh sách và tiếp tục học. Kỹ thuật tương đối ổn định, nhưng học viên ít sử dụng tính năng mới vì giải pháp không đúng nhu cầu.

### Chẩn đoán khác với lỗi code

Failure mode chính có thể là **giả thuyết giá trị không được kiểm chứng sớm**, không phải thiếu unit tests. Bắt đội dùng TDD cho mọi file có thể nâng chất lượng code nhưng chưa giúp hiểu người dùng có cần gợi ý bài học hay không.

### Thực hành XP có thể giúp

- **Small releases** để đưa một lát cắt đã đạt DoD tới nhóm người dùng đủ điều kiện.
- **Close customer collaboration/whole-team conversation** để nhận phản hồi về tác vụ học.
- **Simple design/YAGNI** để không xây hàng loạt chức năng chưa được chứng minh cần thiết.
- **CI/tests** làm nền giúp release nhỏ an toàn, nhưng không thay nghiên cứu người dùng.

### Kỹ thuật sản phẩm bổ trợ

Phỏng vấn, usability test, product analytics có quyền, feature discovery và phân tích funnel là **phương pháp bổ trợ**. Không nên đặt tất cả dưới nhãn “XP practices” chỉ để có một danh sách dài.

### Chỉ số và rủi ro

**Đo:** Thời gian từ giả thuyết tới phản hồi người dùng, task success, tỷ lệ người được tiếp cận thực sự hoàn thành tác vụ và lỗi nghiêm trọng.

**Bảo vệ:** Không phát hành một biến thể đã biết có lỗi quyền/nhạy cảm chỉ để “thử trên người dùng”. DoD và các điều kiện release giữ nguyên ý nghĩa.

## 29. Trường hợp E: CI chậm và flaky — có nên thêm test?

### Bối cảnh

Một đội có pipeline chạy khoảng 45 phút, thất bại ngẫu nhiên; nhiều người rerun cho tới khi xanh. TDD cho quy tắc nhỏ có thể phản hồi nhanh tại máy cá nhân, nhưng pipeline chung vẫn gây chờ kéo dài.

### Phân biệt vấn đề

- **Thiếu test quan trọng** làm lỗi thoát ra sản phẩm.
- **Test không đáng tin** làm đội bỏ qua tín hiệu thật.
- **Pipeline chậm** kéo dài vòng merge/review.
- **Môi trường không đại diện** làm test xanh ở CI nhưng sai ở production.

Những vấn đề này có thể xảy ra đồng thời nhưng cần **phương án riêng**.

### Lựa chọn thực hành và kỹ thuật

- **CI đáng tin** là mục tiêu chính: phân loại lỗi, cô lập dữ liệu test, sửa race, tối ưu lớp test.
- **TDD** giữ phản hồi logic cục bộ nhanh, nhưng không tự chữa test flaky do môi trường.
- **Small changes** giúp khoanh vùng lỗi, giảm thời gian debug diff lớn.
- **Pairing** có thể hữu ích khi debug test flaky phức tạp hoặc luân chuyển tri thức.
- **Test selection/parallelization** là kỹ thuật hạ tầng bổ trợ nếu không tạo lỗ hổng kiểm chứng.

### Quy tắc quyết định

Không có kết luận “test nhiều hơn luôn tốt hơn”. Tập trung vào **tín hiệu liên quan, ổn định, lặp lại được**, với feedback đủ nhanh. Cấm đơn giản hóa bằng cách **bỏ hẳn test bắt buộc** để làm đẹp thời gian CI.

### Một phép thử cải tiến

Ghi:

- Khoảng thời gian CI trước/sau theo loại thay đổi, trung vị và các lần chậm nhất.
- Tỷ lệ lỗi do **test flaky** được phân loại, không trộn lỗi sản phẩm thật.
- Số lần rerun, thời gian chờ merge và lỗi lọt production.
- Chi phí bảo trì test/môi trường.

Chọn một nhóm test flaky có nguyên nhân rõ, sửa fixture/điều kiện đồng bộ, quan sát lại trong kỳ đủ phù hợp rồi mới mở rộng.

## 30. Khi thực hành XP không phải đòn bẩy chính

Điều cần học không chỉ là chọn đúng XP, mà còn biết **khi nào cần giải quyết vấn đề khác trước**.

| Vấn đề thật | Vì sao áp thêm XP chưa đủ? | Hành động nên làm trước hoặc song song |
| --- | --- | --- |
| Product Owner chưa làm rõ nhu cầu | TDD có thể khóa một giả định sai thành test | Làm rõ Product Goal, AC, ví dụ người dùng và quyền quyết định |
| Stakeholders giao việc mâu thuẫn qua nhiều kênh | CI không quyết định thứ tự sản phẩm | Làm rõ Product Backlog và cơ chế trao đổi đúng vai trò |
| API đối tác thay hợp đồng ngoài thời điểm đội kiểm soát | Pairing trong code nội bộ không tự sửa contract bên ngoài | Thiết kế kiểm chứng/giám sát tương thích và liên hệ đối tác |
| Môi trường CI không có quyền/tài nguyên | Bảo mọi người “test nhiều hơn” không giúp chạy test | Giải quyết hạ tầng và quyền sở hữu môi trường |
| Chất lượng giảm vì tổ chức ép deadline bỏ test | Thêm lời kêu gọi TDD không thay được quyền quyết định | Bảo vệ DoD/guardrail, điều chỉnh phạm vi và kế hoạch |
| Dữ liệu đã mất do migration | Refactoring không tự khôi phục dữ liệu | Ứng phó, đối soát, backup/restore và quyền điều tra |
| Đội đo năng suất bằng point mỗi cá nhân | Pairing có thể bị phạt vì “tốn hai người” | Điều chỉnh cơ chế đánh giá và mục tiêu hệ thống |
| Không có ai đủ hiểu concurrency hoặc bảo mật | CI xanh có thể che test sai | Huy động chuyên môn và làm rõ thiết kế/test có thẩm quyền |

### Một quyết định đúng có thể là “chưa triển khai XP ngay”

Nếu điều chưa biết quan trọng nhất là **ngữ nghĩa tiến độ theo nhu cầu học viên**, ưu tiên đầu tiên nên là **cộng tác làm rõ ví dụ nghiệp vụ**. Sau khi có điều kiện chấp nhận, đội mới quyết TDD, CI hay pairing nào giải được failure mode cụ thể.

Không dùng việc “chưa chọn XP” làm lý do ngừng phát triển kỹ thuật; vẫn phải giữ chất lượng và các nghĩa vụ hiện có.

## 31. Bảng phản ví dụ khi áp dụng XP máy móc

| Cách làm lệch mục tiêu | Tác động có thể xảy ra | Cách cải thiện |
| --- | --- | --- |
| **Bắt dùng TDD cho mọi thay đổi mà không hiểu failure mode** | Viết test hình thức, chậm không rõ lý do | Chọn vùng quy tắc/rủi ro phù hợp, học từ ví dụ nhỏ |
| **Coverage = 100% nghĩa là không có bug** | Che race, dữ liệu, bảo mật và hiểu lầm nghiệp vụ | Xem chất lượng assertion và các lớp kiểm tra theo rủi ro |
| **Test chỉ được viết sau code nhưng vẫn gọi TDD** | Mất vòng thiết kế từ test trước | Làm rõ Red–Green–Refactor và học qua một ca nhỏ |
| **Đẩy mọi test lên E2E** | CI chậm, flaky, khó khoanh vùng | Chia test đúng tầng và giữ một số E2E quan trọng |
| **Mock provider rồi tin API đã tích hợp** | Sai contract chỉ lộ sau merge | Kiểm chứng provider/consumer thật và integration tests |
| **Pairing mọi giờ để ghi KPI** | Tốn công, không tăng feedback | Pair theo rủi ro, mục tiêu và quan sát kết quả |
| **Một người luôn lái, người kia ngồi im** | Không chia sẻ tri thức | Luân chuyển driver/navigator, cùng giải thích thiết kế |
| **Pairing được xem là miễn review bắt buộc** | Mất độc lập kiểm soát | Giữ review/separation of duties theo chính sách |
| **Tất cả code đều được sửa tự do** | Có thể vượt quyền, ảnh hưởng production | Collective ownership trong ranh giới quyền/DoD |
| **Refactor cả module không có test** | Lỗi hồi quy khó phát hiện | Tạo safety net và thay đổi cấu trúc từng bước |
| **Refactoring trở thành viết lại từ đầu** | Tạo lô lớn và rủi ro mới | Phân biệt refactor với rewrite, chọn phạm vi có bằng chứng |
| **YAGNI nghĩa là bỏ logging/security** | Vi phạm chất lượng/điều kiện vận hành | Không bỏ yêu cầu đã biết và guardrail bắt buộc |
| **CI chỉ chạy build và lint** | Pipeline xanh giả về tích hợp | Bổ sung test có nghĩa theo failure mode |
| **CI đỏ thì rerun đến khi xanh** | Lỗi flaky che lỗi thật | Phân loại và sửa nguồn bất ổn |
| **Nhánh dài nhiều tuần nhưng nói đã CI** | Xung đột và lệch contract dồn muộn | Tích hợp thay đổi nhỏ theo chính sách |
| **Release thật nhanh dù chưa đạt DoD** | Tác hại dữ liệu và uy tín | Giữ DoD và release criteria, chia lát cắt an toàn |
| **Feature flag giúp gọi code lỗi là Done** | Nhánh có thể được bật và gây hại | Kiểm tra cấu hình cần hỗ trợ và quyền |
| **Tính số test mới là hiệu quả XP** | Test phình nhưng giá trị không đổi | Đo thời điểm phát hiện lỗi, rework, outcome |
| **Tăng số merge mỗi Developer là mục tiêu** | PR bị chia hình thức, cạnh tranh cá nhân | Xem chất lượng, flow, khả năng hoàn tất |
| **Thử quá nhiều practice trong một tuần** | Không biết cái gì có tác dụng, đội quá tải | Chọn 1–3 can thiệp có cơ chế rõ và xem lại |
| **Chỉ sao chép cách làm của đội khác** | Khác failure mode, quyền và môi trường | Ghi bối cảnh, giả thuyết và giới hạn áp dụng |
| **Dùng XP để tránh làm rõ Product Goal** | Code tốt nhưng có thể không ai cần | Kết nối kỹ thuật với acceptance/outcome |
| **Bắt người mệt mỏi tăng tốc để đạt KPI** | Chất lượng giảm và burnout | Sustainable pace, điều chỉnh kế hoạch và năng lực |

## 32. Mẫu tài liệu ra quyết định chọn thực hành XP

Khi đội cần lựa chọn một thực hành cụ thể, nên tạo một **decision record ngắn** có thể đọc lại sau thử nghiệm. Tránh một biểu mẫu dài khiến việc cải tiến bị chặn.

### Mẫu một trang

~~~text
DECISION ID:
  XP-QUALITY-EXAMPLE-01

VẤN ĐỀ CHẤT LƯỢNG:
  Lỗi gì ảnh hưởng ai, vào thời điểm nào, mức độ bao nhiêu?
  Đâu là bằng chứng và đâu chỉ là giả thuyết?

FAILURE MODE:
  Cơ chế nào được xác nhận / còn chưa rõ?
  Test hoặc feedback nào lẽ ra phát hiện sớm hơn?

MỤC TIÊU:
  Giảm rủi ro cụ thể nào?
  Có điều kiện chất lượng hoặc nghĩa vụ nào bắt buộc?

ỨNG VIÊN:
  TDD, pairing, CI, refactoring, simple design, small release...
  Mỗi thực hành tác động vào cơ chế gì?

QUYẾT ĐỊNH:
  Chọn ít thực hành nhất đủ thử;
  ai tham gia, bắt đầu trên lát cắt nào, vì sao?

TIÊN QUYẾT:
  Ví dụ nghiệp vụ, dữ liệu test, quyền, pipeline, người review...

BASELINE VÀ ĐO:
  Lỗi/rework/feedback time/flow/outcome
  cùng mốc start/finish, kỳ quan sát và nguồn dữ liệu.

GUARDRAILS:
  DoD, security, privacy, data consistency,
  khả năng khôi phục, review bắt buộc và nhịp bền vững.

ĐIỀU KIỆN DỪNG:
  Rủi ro tăng, test bắt buộc không đạt, pipeline không đáng tin,
  tác dụng phụ không chấp nhận được.

KẾT LUẬN SAU THỬ:
  Quan sát; giới hạn; yếu tố gây nhiễu;
  giữ/sửa/bỏ/mở rộng; owner và mốc xem lại.
~~~

### Mẫu điền cho lỗi ghi lùi

| Trường | Nội dung minh họa |
| --- | --- |
| **Vấn đề** | Request cũ tới muộn làm giảm highestCompletedSecond đã xác nhận |
| **Giả thuyết cơ chế** | Unit rule chưa rõ, DB update chưa nguyên tử, CI chưa chạy concurrency test |
| **Mục tiêu** | Không ghi lùi theo nghiệp vụ; phát hiện hồi quy trước release |
| **Chọn** | Acceptance examples + TDD rule + pairing concurrency + CI tích hợp |
| **Không chọn làm can thiệp chính** | Đạt 100% coverage, mua dashboard mới, refactor toàn hệ thống |
| **Tiên quyết** | PO chốt ngữ nghĩa progress; fixture DB; môi trường và quyền test |
| **Bằng chứng** | Unit + concurrency/integration tests, rework, CI reliability, lỗi production |
| **Guardrail** | DoD, server-side auth, không lộ dữ liệu, transaction semantics, khả năng khôi phục |
| **Điều kiện dừng** | Test rủi ro đỏ, phát hiện dữ liệu sai hoặc vượt quyền, CI mất tin cậy |
| **Xem lại** | Sau những thay đổi tương đồng và kỳ quan sát được thống nhất |

### Một phép đo minh họa cần diễn giải đúng

Giả sử trước thử nghiệm, trong một nhóm hạng mục cùng loại có **12 PBI Done** và ghi nhận **9 vòng rework do logic/tích hợp**; sau thử có **10 PBI Done** và **4 vòng rework**. Đặt cùng một quy tắc ghi nhận:

\[
\text{Rework cycles per completed PBI}_{\text{trước}}=\frac{9}{12}=0{,}75
\]

\[
\text{Rework cycles per completed PBI}_{\text{sau}}=\frac{4}{10}=0{,}40
\]

Tín hiệu quan sát là **số vòng rework/PBI giảm 0,35** trong hai nhóm được ghi nhận. **Không được kết luận có bằng chứng nhân quả chắc chắn hoặc toàn tổ chức giảm 46,7% chi phí**, vì:

- Mười và mười hai item là mẫu nhỏ; độ khó và loại việc có thể khác nhau.
- Một vòng rework có thể mất 20 phút hoặc nhiều ngày.
- Những item chưa Done có thể đang tích lũy rework chưa được tính.
- Đồng thời có thể đã sửa DB, cải thiện CI, thay reviewer hoặc thay định nghĩa lỗi.
- Có thể do kiểm thử kém đi khiến ít lỗi được ghi nhận hơn; cần xem guardrail chất lượng.

### Thêm số liệu flow để không bỏ sót item chưa Done

Một snapshot giả định có sáu item Done với cycle time **4, 6, 9, 10, 12, 19 ngày** và ba item chưa Done có age **8, 15, 20 ngày**.

- Throughput của **kỳ quan sát** là 6 item Done, không tự là 6 item/ngày.
- Cycle time trung vị của những item Done là **(9 + 10) / 2 = 9,5 ngày**.
- Cycle time trung bình là **(4 + 6 + 9 + 10 + 12 + 19) / 6 = 10 ngày**.
- Những item còn mở tuổi 15 và 20 ngày cần được xem theo loại việc, rủi ro và service level expectation nếu có.

Không được gộp age của item chưa Done vào cycle time như thể item đã hoàn thành. Và chỉ sáu item Done **chưa đủ** để kết luận thực hành XP giúp dự báo chắc chắn.

## 33. Bài tập thực hành lựa chọn XP theo vấn đề cụ thể

### Bài tập 1 — Từ triệu chứng đến failure mode

Người học báo “mất tiến độ”, Developers thấy unit tests xanh và chưa rõ request nào ghi sau.

**Yêu cầu:** Viết bốn tầng: tác động người dùng, triệu chứng kỹ thuật, ít nhất ba giả thuyết cơ chế và lỗ hổng feedback. Chỉ ra bằng chứng nào giúp loại trừ từng giả thuyết.

**Gợi ý:** Đừng tự kết luận thiếu TDD trước khi kiểm tra timeline, DB và quy tắc nghiệp vụ.

### Bài tập 2 — Chọn ba thực hành, loại hai thực hành

Một module ghi tiến độ có nhiều vòng rework do quy tắc và concurrency; đội có CI chạy unit tests nhưng không có DB integration tests. Người hiểu transaction là một chuyên gia duy nhất.

**Yêu cầu:** Chọn tối đa ba thực hành XP làm can thiệp chính; giải thích cơ chế, thứ tự, điều kiện tiên quyết; nêu hai thực hành chưa cần ưu tiên và vì sao.

### Bài tập 3 — Red–Green–Refactor trên Java

Dùng quy tắc highestCompletedSecond của bài học.

**Yêu cầu:** Trình bày thứ tự viết test trước khi có implementation, giải thích test nào thất bại trước, viết phương án implementation tối thiểu và chỉ ra refactor có ý nghĩa nếu code phát triển phức tạp hơn.

**Điều kiện:** Phân biệt rule thuần với transaction guarantee; không tuyên bố hàm Math.max tự xử lý concurrency trong DB.

### Bài tập 4 — TDD với yêu cầu chưa rõ

PO chưa biết “tiến độ học” có được giảm khi học viên tua lại video hay không. Developer muốn viết test “progress luôn tăng”.

**Yêu cầu:** Viết ba câu hỏi nghiệp vụ, đề xuất tách **currentPlaybackPosition** khỏi **highestCompletedSecond** khi phù hợp và mô tả vì sao test có thể kiểm chứng đúng một quy tắc sai.

### Bài tập 5 — Test cạnh tranh thật

Hai request ghi 120 và 300 đọc cùng giá trị ban đầu 100. Một unit test gọi hàm lần lượt luôn xanh.

**Yêu cầu:** Viết một integration scenario có hai transaction, kết quả mong đợi, cách tái hiện thứ tự, vấn đề auth và điều kiện để chứng minh database không ghi lùi trong phạm vi được kiểm thử.

### Bài tập 6 — Chọn pairing theo rủi ro

Một Developer duy nhất hiểu transaction của module thanh toán khóa học; mọi PR chờ họ xem nhiều ngày.

**Yêu cầu:** Thiết kế hai phiên pairing có mục tiêu, cách luân chuyển hiểu biết, bằng chứng review wait giảm và một kiểm soát độc lập không được bỏ.

### Bài tập 7 — CI xanh giả

Provider đổi tên một trường API. Client test với mock cũ, service test với dữ liệu mới; cả hai pipeline riêng đều xanh.

**Yêu cầu:** Phân biệt unit tests, provider–consumer contract tests và integration tests; thiết kế nơi đưa kiểm chứng contract vào vòng CI.

### Bài tập 8 — Khi nào refactoring an toàn?

Controller hiện kiểm tra quyền, tính tiến độ, truy DB, tạo response và ghi event. Hệ thống thiếu regression tests.

**Yêu cầu:** Đề xuất kế hoạch refactor nhỏ có safety net, điểm cần kiểm tra khi tách boundary, khác biệt giữa refactor và sửa bug.

### Bài tập 9 — Simple design, YAGNI và guardrails

Để sửa request đến muộn, một nhóm đề xuất xây event sourcing và conflict-resolution framework cho mọi loại nội dung trong tương lai.

**Yêu cầu:** Liệt kê ba thông tin cần xác nhận trước khi chọn kiến trúc lớn, một giải pháp nhỏ cần kiểm chứng, và hai yêu cầu bảo mật/dữ liệu không được viện YAGNI để bỏ.

### Bài tập 10 — Small releases nhưng chưa đạt DoD

Một tính năng sau feature flag chưa được kiểm tra phân quyền, nhưng đội muốn deploy/release để nhận phản hồi sớm.

**Yêu cầu:** Phân biệt merge, Increment đạt DoD, deploy và release; xác định hành động an toàn và trách nhiệm kiểm tra trước khi mở.

### Bài tập 11 — Quan sát một pair programming session

Trong phiên pairing, một người code 90 phút, người kia xem điện thoại; cuối buổi hai người báo “đã thực hành XP”.

**Yêu cầu:** Đề xuất chuẩn bị trước phiên, driver/navigator, cách luân chuyển vai và ba dấu hiệu phản hồi có chất lượng.

### Bài tập 12 — Review nhiều vòng

Một module liên tục bị trả PR do tên khó hiểu, logic rải rác và chỉ một người đủ khả năng review.

**Yêu cầu:** So sánh tác dụng của pair programming, refactoring, coding standards và collective ownership. Chọn một can thiệp thử trước, nêu guardrail.

### Bài tập 13 — CI chậm và flaky

Pipeline mất 45 phút, khoảng một phần mười lần chạy thất bại không ổn định; developer thường bấm rerun.

**Yêu cầu:** Đặt câu hỏi phân loại lỗi, chọn thực hành chính, thiết kế baseline và kế hoạch làm test ổn định, nêu vì sao xóa các test bắt buộc không phải cải tiến chất lượng.

### Bài tập 14 — Scrum + XP

Một Scrum Team có Product Goal, Sprint Goal, Product Backlog và DoD nhưng nhiều PBI chờ tích hợp ở cuối Sprint.

**Yêu cầu:** Chọn hai thực hành XP và một thực hành Kanban bổ sung, giải thích cách chúng hỗ trợ Scrum mà không thay đổi accountabilities/events/artifacts/commitments.

### Bài tập 15 — Kanban + XP

Một đội flow-first hỗ trợ API nhận việc liên tục, WIP cao và luôn mở thêm việc khi có người rảnh.

**Yêu cầu:** Đề xuất chính sách WIP/pull và thực hành XP tương ứng với failure mode, phân biệt điểm Done của đội với Increment/DoD trong Scrum.

### Bài tập 16 — Đọc dữ liệu rework

Trước thử nghiệm có 12 PBI Done, 9 vòng rework; sau thử nghiệm có 10 PBI Done, 4 vòng rework.

**Yêu cầu:** Tính rework cycles/PBI trước/sau. Giải thích ít nhất bốn lý do chưa được quy toàn bộ thay đổi cho TDD hoặc pairing.

**Gợi ý đáp án:** **0,75** và **0,40** vòng/PBI đã Done; cần xem loại item, item chưa Done, định nghĩa rework, mức phát hiện và các thay đổi cùng kỳ.

### Bài tập 17 — Cycle time và aging WIP

Sáu item Done có cycle time **4, 6, 9, 10, 12, 19 ngày**; ba item chưa Done có age **8, 15, 20 ngày**.

**Yêu cầu:** Tính throughput của kỳ, mean/median cycle time và nêu vì sao age của item chưa Done không được nhập vào tập cycle time. Chọn item cần điều tra theo bối cảnh.

**Gợi ý đáp án:** Throughput **6 item trong kỳ**, mean **10 ngày**, median **9,5 ngày**; item age 20 có thể cần ưu tiên xem nguyên nhân, không tự quy lỗi cá nhân.

### Bài tập 18 — Khi không nên bắt đầu bằng XP

Một nhóm code rất ít bug nhưng tính năng không được người dùng sử dụng. PO chưa xác nhận vấn đề khách hàng; lãnh đạo muốn ép TDD 100% codebase.

**Yêu cầu:** Chẩn đoán failure mode, đề xuất việc làm rõ sản phẩm và phản hồi người dùng trước, chọn thực hành XP có thể hỗ trợ delivery sau đó.

### Bài tập 19 — Thiết kế experiment card

Đội muốn xử lý lỗi tiến độ sau release và giảm rework trong bốn tuần.

**Yêu cầu:** Điền đủ các trường vấn đề, failure mode, giả thuyết, can thiệp, baseline, metric, guardrail, người phối hợp, điều kiện dừng, các yếu tố gây nhiễu và quyết định cuối thử.

### Bài tập 20 — Bảo vệ tính bền vững

Đội đạt velocity cao nhờ overtime và bỏ một số test. Sự cố production tăng, nhưng quản lý khẳng định “XP cần mạnh tay hơn nữa”.

**Yêu cầu:** Phân tích vì sao vấn đề không chỉ nằm ở việc thiếu kỹ thuật; đề xuất cách giữ sustainable pace, chất lượng và quyền ưu tiên, cộng một thực hành XP giúp giảm rework.

### Bài tập 21 — Chọn một phương án trong ba tình huống

Ba đội có vấn đề:

A. Lỗi nhánh if/else nghiệp vụ lặp lại dù tích hợp và CI nhanh.

B. Lỗi provider–consumer xuất hiện sau khi merge nhiều nhánh dài.

C. Người dùng không hiểu tính năng đã được phát hành dù test kỹ thuật xanh.

**Yêu cầu:** Với mỗi đội, chọn 1–3 thực hành XP, nêu kỹ thuật bổ trợ không nhất thiết thuộc XP, một phép đo và một guardrail.

### Bài tập 22 — Viết quyết định giữ/sửa/bỏ có căn cứ

Sau một tháng dùng pairing và CI, reviewer wait giảm nhưng lỗi production gần như chưa đổi. Cùng kỳ đội vừa thay schema và tăng số người dùng mobile.

**Yêu cầu:** Viết kết luận 150–250 từ phân biệt dữ liệu quan sát, giả thuyết, biến gây nhiễu và hành động tiếp theo. Không tuyên bố thất bại hoặc thành công chỉ từ một chỉ số.

## 34. Rubric tự đánh giá một phương án lựa chọn XP

Một câu trả lời tốt không nhất thiết chọn **nhiều thực hành nhất**. Hãy đánh giá phương án bằng những tiêu chí sau.

| Chiều đánh giá | Chưa đạt | Đang phát triển | Đạt tốt |
| --- | --- | --- | --- |
| **Vấn đề chất lượng** | Chỉ nói “code kém” hoặc “đội chưa XP” | Có triệu chứng nhưng ít bằng chứng | Nêu tác động người dùng, phạm vi và ví dụ có thể kiểm chứng |
| **Failure mode** | Quy lỗi cá nhân hoặc chọn nguyên nhân bằng cảm giác | Có vài giả thuyết nhưng chưa nêu cách phân biệt | Gắn mỗi giả thuyết với bằng chứng, độ bất định và điều kiện kích hoạt |
| **Lựa chọn thực hành** | Đề xuất mọi practice XP | Chọn ít practice nhưng lý do chung chung | Chọn 1–3 cơ chế phù hợp với nguyên nhân và chỉ ra giới hạn |
| **Test và kỹ thuật** | Tin một loại test hoặc coverage là đủ | Có test nhưng thiếu ranh giới quan trọng | Phân biệt unit, contract, integration, security và tình huống thực |
| **Chất lượng/guardrail** | Đề xuất bỏ DoD hoặc giảm quyền để nhanh | Có nói về an toàn nhưng chưa có điều kiện cụ thể | Giữ DoD, phân quyền, dữ liệu, khôi phục và quyền quyết định rõ |
| **Đo lường** | Chỉ đếm số test/PR/giờ pairing | Có metric nhưng mốc đo chưa nhất quán | Có baseline, start/finish, mẫu số, kỳ, flow/quality/outcome |
| **Học hỏi và thích nghi** | Kết luận trước khi thử | Có xem kết quả nhưng ít giới hạn | Có điều kiện dừng, confounders, quyết định giữ/sửa/bỏ |
| **Phối hợp** | Một cá nhân phải làm thay tất cả | Có nói tới PO/tester/Dev | Đúng người làm rõ giá trị, kỹ thuật, bảo mật và release theo thẩm quyền |

### Ba dấu hiệu đáp án trưởng thành

1. **Biết nói “chưa đủ bằng chứng”:** Chưa xác định được lỗi do logic hay DB thì chưa khẳng định TDD sẽ giải quyết.
2. **Biết nói “không chọn”:** Không ép pair mọi giờ, không sửa toàn kiến trúc hoặc tăng coverage chỉ vì công cụ đo được.
3. **Biết nêu điều kiện đổi quyết định:** Nếu lỗi chủ yếu là contract, chuyển trọng tâm sang CI/contract tests; nếu là nhu cầu sai, quay lại khám phá sản phẩm.

### Gợi ý hình thức báo cáo nhóm

Một nhóm học viên có thể trình bày:

- 1 sơ đồ failure mode với tối đa ba giả thuyết chính.
- 1 bảng chọn/không chọn thực hành và cơ chế.
- 1 ví dụ test **trước/sau** hoặc bằng chứng pipeline.
- 1 experiment card có baseline, guardrails, thời điểm xem lại.
- 1 kết luận giới hạn theo dữ liệu, không xếp hạng cá nhân.

Như vậy bài thực hành tập trung **lập luận và năng lực điều chỉnh**, không phải học thuộc tên gọi.

## 35. Checklist chọn và triển khai XP theo một vấn đề chất lượng

### Trước khi chọn thực hành

- [ ] Đã nêu rõ **người dùng hoặc hệ thống bị ảnh hưởng** và tác động chất lượng?
- [ ] Có một **ví dụ có thể tái hiện** hoặc dữ liệu đủ tin về lỗi?
- [ ] Phân biệt **triệu chứng, failure mode và nguyên nhân chưa chắc chắn**?
- [ ] Có ghi nguồn evidence, thời gian, phiên bản và phạm vi lỗi?
- [ ] Không quy lỗi cá nhân khi chưa phân tích cơ chế của hệ thống?
- [ ] Những rủi ro dữ liệu/bảo mật đang gây hại đã được xử lý khẩn theo chính sách nếu cần?
- [ ] Product Owner/người nghiệp vụ đã xác nhận ngữ nghĩa hành vi cần bảo vệ?
- [ ] Có biết **nhóm nào, codebase/contract nào** bị ảnh hưởng?
- [ ] Đã nhận diện phần công việc cần **review độc lập hoặc phê duyệt có thẩm quyền**?
- [ ] Có baseline đủ rõ về lỗi, rework, flow, CI và chất lượng?

### Khi chọn ứng viên

- [ ] Mỗi thực hành XP được chọn có **cơ chế tác động cụ thể** tới failure mode?
- [ ] Đã so sánh **TDD, pairing, CI, refactoring, simple design, small releases** theo nhu cầu thay vì độ phổ biến?
- [ ] Đã phân biệt thực hành XP với **kỹ thuật bổ trợ** như contract/security tests hoặc migration?
- [ ] Đã chọn **một nhóm nhỏ** thực hành đủ thử thay vì triển khai đồng loạt?
- [ ] Các điều kiện tiên quyết như môi trường test, dữ liệu fixture, kỹ năng và quyền đã rõ?
- [ ] Có cân nhắc chi phí học hỏi, thời gian feedback và tác dụng phụ?
- [ ] Không dùng YAGNI hoặc “phản hồi nhanh” làm cớ bỏ điều kiện chất lượng bắt buộc?
- [ ] Nếu không thể xác định nguyên nhân, có kế hoạch thu thêm bằng chứng trước?

### TDD và feedback kỹ thuật

- [ ] Red–Green–Refactor được hiểu **đúng trình tự và mục đích**?
- [ ] Test thất bại **vì hành vi mong muốn chưa có**, không do build hỏng hoặc setup sai?
- [ ] Test có assertion rõ, gắn với ví dụ nghiệp vụ được xác nhận?
- [ ] Refactor có giữ hành vi đã xác định và chạy regression test?
- [ ] Không dùng code coverage như chứng chỉ hết bug?
- [ ] Đã đánh giá những **ranh giới unit tests không bao phủ**?
- [ ] Có kiểm tra provider–consumer, DB transaction, retry và phân quyền khi liên quan?
- [ ] CI chạy các kiểm tra cần thiết với tín hiệu tin cậy?
- [ ] Test flaky được điều tra và sửa, không mặc định rerun tới khi xanh?
- [ ] Code được tích hợp thành thay đổi đủ nhỏ để phản hồi tới sớm?

### Pairing, ownership và thiết kế

- [ ] Pairing có mục tiêu rõ, có đối thoại hai chiều và có thể luân chuyển vai?
- [ ] Không biến số giờ pairing thành KPI hoặc dùng pairing thay mọi review bắt buộc?
- [ ] Có kế hoạch lan tỏa tri thức vùng code khó, giảm phụ thuộc một người?
- [ ] Collective ownership vẫn giữ phân quyền và trách nhiệm theo chính sách?
- [ ] Coding standards giảm chi phí review, không thành tranh luận hình thức?
- [ ] Simple design ưu tiên nhu cầu đã biết mà không bỏ yêu cầu an toàn?
- [ ] Sustainable pace được bảo vệ; không dựa vào overtime để tạo vẻ hiệu quả?

### Sản phẩm, flow và chất lượng

- [ ] XP đang hỗ trợ **Product Goal hoặc mục tiêu dịch vụ có nghĩa**, không chỉ hoạt động code?
- [ ] Nếu dùng Scrum, accountability/events/artifacts/commitments và DoD được giữ?
- [ ] Nếu dùng Kanban, workflow/WIP/age/blocked policies được hiểu và cải tiến?
- [ ] Những lát cắt có thể **tích hợp và đạt DoD**, không dồn kiểm thử vào cuối?
- [ ] Không nhầm merge, Increment đạt DoD, deploy, release và outcome?
- [ ] Small releases có kiểm soát quyền, dữ liệu, telemetry và khả năng khôi phục?
- [ ] Có vòng lấy **phản hồi người dùng thực** theo quyền được phép?
- [ ] Không dùng story point, số merge hoặc số unit test để xếp hạng năng suất cá nhân?

### Sau thử nghiệm

- [ ] Có phép đo **hành vi áp dụng, feedback kỹ thuật và kết quả chất lượng**?
- [ ] Những item chưa Done và lỗi production cũng được xem, không chỉ hạng mục đã đóng?
- [ ] Metric có mẫu số, kỳ đo và định nghĩa start/finish nhất quán?
- [ ] Có phân biệt correlation và causal claim, nhất là khi đổi nhiều thực hành cùng lúc?
- [ ] Đã ghi confounders như API đối tác, tải, nhân sự, cơ chế phát hiện lỗi?
- [ ] Có điều kiện dừng khi chất lượng hoặc bảo mật suy giảm?
- [ ] Có quyết định rõ: **giữ, điều chỉnh, dừng, thu thêm dữ liệu hoặc mở rộng**?
- [ ] Có owner và thời điểm xem lại hành động?
- [ ] Bài học được chia sẻ **cùng bối cảnh**, tránh ép đội khác sao chép khi failure mode khác?

Checklist là **công cụ suy nghĩ**, không phải bài kiểm tra đủ phần trăm để được công nhận XP. Một phương án đơn giản nhưng đánh đúng failure mode, giữ DoD và có bằng chứng có thể tốt hơn danh sách dài những kỹ thuật chưa dùng thật.

## 36. Tổng kết

- **Bắt đầu từ lỗi chất lượng có bằng chứng**, không bắt đầu từ tên XP practice. Tách tác động người dùng, triệu chứng, failure mode và lỗ hổng phản hồi trước khi quyết định.
- **TDD** phù hợp khi cần làm rõ hành vi và thiết kế bằng vòng **Red–Green–Refactor**. Một unit test cho logic thuần **không chứng minh** transaction race, quyền truy cập hoặc tích hợp API đúng.
- **Pair programming, collective ownership và coding standards** hữu ích khi feedback thiết kế chậm, tri thức tập trung hoặc review là bottleneck; chúng không xóa yêu cầu kiểm soát độc lập.
- **Continuous Integration và thay đổi nhỏ** giúp phát hiện sai lệch sớm nếu pipeline thực sự kiểm chứng những ranh giới quan trọng; đèn xanh từ test thiếu hoặc flaky không đủ tin.
- **Refactoring, simple design và YAGNI** giảm phức tạp và giúp code dễ thay đổi khi giữ hành vi/quality guardrails; không phải cớ bỏ bảo mật, dữ liệu hoặc khả năng khôi phục đã biết.
- **Small releases và cộng tác người dùng** rút ngắn độ trễ học hỏi sản phẩm khi Increment đã đạt DoD và release đáp ứng chính sách.
- **Không cần áp dụng mọi thực hành XP.** Hãy chọn một nhóm nhỏ với cơ chế nhân quả, điều kiện tiên quyết, chi phí, guardrails và khả năng kiểm chứng rõ.
- **Scrum, Kanban và XP bổ trợ nhau theo bối cảnh:** Scrum tổ chức trách nhiệm và Increment; Kanban giúp quản lý flow; XP tăng phản hồi kỹ thuật. Không dùng cách kết hợp để làm sai trách nhiệm của framework hay bỏ chất lượng.
- **Đo tác động đa chiều:** Rework, lỗi thoát production, CI reliability, work item age, cycle time, chất lượng Increment và kết quả người dùng. Một tháng dữ liệu nhỏ hoặc số test tăng không chứng minh hiệu quả nhân quả.
- **Thử nghiệm và thích nghi là mục tiêu:** Phương án được chọn cần có giả thuyết, baseline, bằng chứng, điều kiện dừng, thời điểm xem lại và quyết định tiếp theo.

Khi được hỏi **“Đội chúng ta nên áp dụng TDD, pair programming, CI hay refactoring?”**, câu trả lời tốt không phải một tên thực hành duy nhất. Hãy bắt đầu bằng:

> **“Vấn đề chất lượng cụ thể nào đang ảnh hưởng người dùng, chúng ta biết gì về cơ chế gây lỗi, thực hành nào sẽ tạo phản hồi sớm đúng chỗ và bằng chứng nào chứng minh cải thiện mà vẫn giữ an toàn?”**
