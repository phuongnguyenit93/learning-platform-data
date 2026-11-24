# Điều chỉnh chính sách, kỹ thuật và cách phối hợp theo kết quả

Một nhóm phát triển nền tảng học trực tuyến liên tục trễ mục tiêu Sprint. Mỗi lần họp cải tiến, mọi người thống nhất sẽ “giao tiếp tốt hơn” và “cố gắng test sớm hơn”. Hai tuần sau, bảng công việc vẫn có nhiều thẻ chờ review, các bản sửa lỗi đến dồn vào cuối Sprint và tính năng **“Học tiếp”** chưa thể giao an toàn. Nhóm họp nhiều nhưng cách làm không thay đổi.

Một nhóm khác bắt đầu bằng bằng chứng: **thời gian chờ review chiếm phần lớn cycle time**, nhiều công việc được bắt đầu đồng thời, còn lỗi tiến độ học tập chỉ được phát hiện khi tích hợp cuối kỳ. Họ thử **giới hạn WIP**, quy định rõ khi nào có thể kéo thêm việc, tổ chức **review/pairing sớm** và thêm **kiểm thử tự động ở cấp API** cho quy tắc checkpoint. Sau một khoảng đủ để quan sát, họ so sánh flow, lỗi và trải nghiệm người học, giữ những thay đổi có ích rồi điều chỉnh phần chưa phù hợp.

Sự khác nhau nằm ở **cải tiến dựa trên kết quả**: không chỉ nêu lời hứa, mà lựa chọn một giả thuyết, thay đổi cách vận hành, xem bằng chứng và quyết định tiếp. Trong Agile, những đòn bẩy có thể điều chỉnh gồm **chính sách làm việc**, **thực hành kỹ thuật** và **cách con người phối hợp**. Cải tiến liên tục cần cân bằng cả ba để giao phần mềm tăng dần, nhận phản hồi sớm, giữ chất lượng và tạo giá trị.

Bài thuộc chương **Cải tiến liên tục** của module **AGILE_DEVELOPMENT**. Các ví dụ kết nối với user story, backlog, Scrum, Kanban, Extreme Programming (XP) và đo lường dòng công việc; mục tiêu là giúp bạn **đề xuất và kiểm chứng thay đổi nhỏ trong hệ thống làm việc**, không sao chép một bộ nghi thức hoặc đổ lỗi cho cá nhân.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao **cải tiến liên tục là chu trình kiểm tra và thích ứng**, không phải danh sách hành động của một buổi retrospective.
2. Phân biệt ba nhóm đòn bẩy **chính sách – kỹ thuật – phối hợp**, đồng thời hiểu quan hệ phụ thuộc giữa chúng.
3. Chọn một vấn đề dựa trên **bằng chứng về kết quả sản phẩm, flow, chất lượng và tính bền vững** thay vì ý kiến to nhất trong phòng.
4. Mô tả hiện trạng bằng **Definition of Workflow, chính sách rõ ràng, WIP, work item age, cycle time và throughput** nếu phù hợp với cách nhóm vận hành.
5. Viết một **giả thuyết cải tiến có thể kiểm chứng** gồm thay đổi định thử, cơ chế kỳ vọng, metric, guardrails, thời gian và người chịu trách nhiệm.
6. Điều chỉnh các chính sách về **bắt đầu/kết thúc việc, giới hạn WIP, xử lý blocked items, review, chất lượng và lớp dịch vụ** dựa trên nhu cầu.
7. Chọn thực hành kỹ thuật như **TDD, CI, kiểm thử API, code review, refactoring, feature flags và tích hợp thường xuyên** để giải quyết loại lỗi hay độ trễ cụ thể.
8. Cải thiện phối hợp thông qua **swarming, pairing, làm rõ quyền quyết định, trao đổi với Product Owner và bên liên quan**, tránh tăng họp vô mục đích.
9. Phân tích một thử nghiệm thay đổi, nhận diện **kết quả ngoài ý muốn, biến động dữ liệu và giới hạn suy luận nhân quả**.
10. Quyết định **giữ, điều chỉnh, quay lại hoặc thử tiếp** một thay đổi và duy trì vòng học hỏi qua Scrum, Kanban hoặc XP.

## 2. Cải tiến liên tục: thay đổi hệ thống làm việc theo bằng chứng

**Cải tiến liên tục** (*continuous improvement*, thường gắn với tư duy *Kaizen*) là quá trình phát hiện chỗ có thể tốt hơn, thử thay đổi có chủ đích, học từ kết quả và chuẩn hóa hoặc điều chỉnh cách làm. Cải tiến có thể rất nhỏ; điều quan trọng là **có vòng phản hồi và quyết định thực sự**.

~~~mermaid
flowchart LR
    A["Quan sát kết quả<br/>và vấn đề"] --> B["Lập giả thuyết<br/>nguyên nhân có thể"]
    B --> C["Chọn một thay đổi<br/>đủ nhỏ, an toàn"]
    C --> D["Thử trong phạm vi<br/>và cửa sổ rõ"]
    D --> E["Đo outcome, flow,<br/>quality, guardrails"]
    E --> F{"Kết quả nói gì?"}
    F -->|Tốt và đáng tin| G["Giữ/chuẩn hóa<br/>và chia sẻ"]
    F -->|Chưa tốt| H["Điều chỉnh/hoàn tác<br/>hoặc thử giả thuyết khác"]
    F -->|Chưa đủ dữ liệu| I["Tăng quan sát<br/>hoặc thiết kế phép thử"]
    G --> A
    H --> A
    I --> A
~~~

Không phải mọi thay đổi cần thử nghiệm ngẫu nhiên hay dashboard phức tạp. Một thỏa thuận phối hợp nhỏ có thể được kiểm tra bằng số việc bị chặn và phản hồi thành viên. Nhưng nhóm cần nêu rõ **đang giải quyết điều gì và điều kiện nào chứng tỏ thay đổi hữu ích**.

### Ba câu hỏi trước khi thay đổi

1. **Kết quả nào đang không đạt?** Ví dụ mất dữ liệu, người dùng chờ quá lâu, item già đi, hoặc nhóm thường xuyên làm thêm giờ.
2. **Điều gì trong hệ thống có thể gây ra kết quả đó?** Đây là **giả thuyết**, không mặc định là nguyên nhân đã được chứng minh.
3. **Thay đổi nhỏ nhất nào có thể kiểm chứng giả thuyết mà không gây rủi ro không chấp nhận được?**

Một câu “mọi người cần chủ động hơn” không xác định được điều kiện vận hành. Một thay đổi như “trong hai tuần, khi hàng chờ review có hai PR quá một ngày làm việc, các Developers ưu tiên review trước khi kéo user story mới” **có thể thực hiện, quan sát và điều chỉnh**.

## 3. Ba nhóm đòn bẩy: chính sách, kỹ thuật và cách phối hợp

| Nhóm thay đổi | Nó điều chỉnh điều gì? | Ví dụ cụ thể | Khi nào hữu ích? |
| --- | --- | --- | --- |
| **Chính sách (policies)** | Quy tắc minh bạch để công việc đi qua hệ thống | WIP limit, tiêu chí pull, xử lý blocker, định nghĩa Done, chính sách review, service class | Khi có nhiều việc dở, ưu tiên mơ hồ, hàng chờ hoặc quyết định không nhất quán |
| **Kỹ thuật (engineering practices)** | Khả năng thay đổi, kiểm tra, tích hợp và vận hành phần mềm an toàn | TDD, CI, test API, refactoring, pairing, contract tests, database migration, monitoring | Khi lỗi phát hiện muộn, thay đổi khó, build hỏng, tích hợp chậm hoặc production thiếu tin cậy |
| **Phối hợp (collaboration)** | Dòng thông tin, trách nhiệm, hỗ trợ và quyết định giữa người với người | Product/engineering/QA trao đổi ví dụ, swarming blocker, trao đổi với người dùng, rõ ownership | Khi hiểu sai yêu cầu, phụ thuộc chéo, chờ phê duyệt, handoff hoặc cô lập kiến thức |

**Ba đòn bẩy liên quan nhau.** Chẳng hạn, nếu code review bị tắc:

- Đổi **chính sách:** giới hạn số PR chờ, thống nhất tiêu chí ưu tiên review.
- Đổi **kỹ thuật:** giảm kích thước PR, dùng CI/static checks để người review tập trung vào vấn đề khó.
- Đổi **phối hợp:** pairing hoặc swarm vào thay đổi quan trọng, có người dự phòng khi reviewer chính vắng.

Chỉ yêu cầu người review “nhanh hơn” mà không giảm WIP, hỗ trợ automation hoặc chia sẻ kiến thức thường không giải quyết điểm nghẽn.

### Thay đổi đồng thời cả ba có thể gây khó đọc kết quả

Đôi khi cần gói thay đổi vì các yếu tố phụ thuộc nhau, nhưng nếu ngay một lúc đổi toàn bộ policy, pipeline, cấu trúc nhóm và công cụ, rất khó biết **điều gì thực sự tạo khác biệt**. Nên ưu tiên **một giả thuyết có trọng tâm**, xác định các thay đổi tối thiểu để giả thuyết được thử an toàn và theo dõi tác dụng phụ.

## 4. Kết quả nào đáng dùng để định hướng cải tiến?

Trong Agile, “kết quả” không chỉ là thời gian hoàn thành ticket. Cần nhìn ít nhất bốn lớp bằng chứng:

| Lớp bằng chứng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Giá trị sản phẩm/outcome** | Người dùng có được lợi từ thay đổi? | Tỷ lệ học viên mở lại đúng bài, thời gian tìm bài, tiếp tục học hữu ích |
| **Chất lượng/an toàn** | Phần mềm có đúng, ổn định và được tin cậy? | Lỗi checkpoint, sai quyền, lỗi hồi quy, thời gian phục hồi |
| **Flow/delivery** | Công việc đi qua hệ thống ra sao? | WIP, cycle time, throughput, work item age, blocked time |
| **Sức khỏe hệ thống làm việc** | Nhóm có thể duy trì nhịp làm việc không? | Làm thêm giờ, gián đoạn liên tục, chia sẻ hiểu biết, phản hồi thành viên |

Một thay đổi có thể làm **throughput tăng** nhưng khiến lỗi lọt production tăng. Cải tiến ấy chưa chắc có ích. Một chính sách giảm WIP có thể ban đầu làm ít việc được “bắt đầu” hơn, nhưng tăng số việc **thực sự Done** và giảm căng thẳng; cần đo đúng điểm kết thúc và guardrails.

### Output không tự bằng outcome

- **Output:** đã viết thêm 50 test, đã ban hành quy định review, đã có thêm hai buổi sync.
- **Outcome:** lỗi tiến độ được phát hiện sớm hơn, cycle time giảm mà chất lượng không xấu đi, quyết định ưu tiên được làm rõ nhanh hơn.
- **Impact:** sản phẩm đáng tin hơn, người học đạt mục tiêu thuận tiện hơn, nhóm làm việc bền vững hơn.

Một chỉ số **engineering** là bằng chứng về năng lực thay đổi; nó không tự chứng minh người học thích hay được lợi từ chức năng mới. Cần nối từ cải tiến cách làm tới **Increment có giá trị và phản hồi người dùng**.

## 5. Chẩn đoán trước khi sửa: hiện tượng, giả thuyết, nguyên nhân

Giả sử đội thấy “80% user stories hoàn tất ở hai ngày cuối Sprint”. Có thể có nhiều nguyên nhân:

- Story quá lớn, thiếu lát cắt end-to-end.
- Backlog item chưa rõ quy tắc, Developers phải đợi Product Owner.
- Review/test chỉ được kéo vào khi “code complete”.
- CI flaky khiến thay đổi liên tục phải chạy lại.
- Môi trường tích hợp không ổn định.
- Quá nhiều work items cùng lúc và phụ thuộc một chuyên gia.
- Nhóm chỉ đánh dấu Done hàng loạt vào cuối tuần dù phần mềm đã sẵn sàng sớm hơn.

**Hiện tượng không xác định duy nhất nguyên nhân.** Cần đối chiếu dữ liệu workflow, quan sát trực tiếp, phỏng vấn người liên quan và xem ví dụ công việc cụ thể.

### Phương pháp “5 Whys” dùng như gợi ý, không như chứng cứ

~~~text
Hiện tượng: Nhiều story không đạt Done đến gần cuối Sprint.
Tại sao?       Nhiều story đang chờ review.
Tại sao?       Reviewer thường đồng thời đang code feature mới.
Tại sao?       Chưa có thỏa thuận ưu tiên hoàn tất trước khi bắt đầu thêm.
Giả thuyết:   Nếu giới hạn WIP và ưu tiên review theo tín hiệu hàng đợi,
              tuổi story và thời gian chờ review sẽ giảm.
~~~

Chuỗi hỏi trên **chỉ là mô hình giả thuyết**. Thực tế còn có thể là PR quá lớn, reviewer thiếu quyền, quy tắc kiến trúc mơ hồ hoặc CI chậm. Không ép “5 câu tại sao” tới kết luận “do ai đó thiếu trách nhiệm”.

### Một cách kiểm tra hiện trạng

1. Chọn 8–15 work items gần đây **cùng loại và cùng ranh giới workflow**, không chỉ các item thành công.
2. Ghi thời gian ở Doing, review, blocked, test và chờ release.
3. Xem phân bố thời gian, không chỉ trung bình; chú ý các item già bất thường.
4. Hỏi người tham gia về các quyết định và phụ thuộc đã xảy ra.
5. Xác định giả thuyết có thể kiểm chứng và những lời giải thích thay thế.

Đừng dùng dữ liệu như “bằng chứng buộc tội”. Nếu muốn mọi người khai báo blocker trung thực, tổ chức phải tạo được **môi trường không trừng phạt việc làm lộ vấn đề**.

## 6. Đo flow có định nghĩa, không dùng số ticket như chất lượng

Trong Kanban Guide, bốn flow metrics cơ bản thường được nêu gồm **WIP, throughput, work item age và cycle time**. Chúng hữu ích dù nhóm dùng Kanban làm cách tổ chức chính hay chỉ áp một số thực hành vào Scrum.

| Metric | Định nghĩa thực hành | Cách dùng cho cải tiến |
| --- | --- | --- |
| **Work in Progress (WIP)** | Số work items đã bắt đầu nhưng chưa đạt điểm kết thúc theo Definition of Workflow | Thấy quá tải và việc bắt đầu nhiều hơn khả năng hoàn tất |
| **Throughput** | Số work items hoàn tất trong một khoảng đo | Theo dõi năng lực đưa việc tới Done; cần định nghĩa item nhất quán |
| **Work item age** | Thời gian một item đang làm chưa Done tính từ khi bắt đầu | Phát hiện nguy cơ bị tắc **trước khi** item hoàn tất |
| **Cycle time** | Thời gian một item đã hoàn tất đi từ start tới finish | Đọc độ trễ và biến thiên của hệ thống |

### Ví dụ nhỏ

Giả sử bốn feature tương đối cùng loại hoàn tất với cycle time: **3, 5, 8, 12 ngày làm việc**.

- Trung bình: \((3+5+8+12)/4=7\) ngày.
- Trung vị: \((5+8)/2=6{,}5\) ngày.
- Một item mất 12 ngày cho thấy **đuôi dài** đáng tìm hiểu.

Nếu một feature đang dở đã **11 ngày**, thông tin work item age có thể hữu ích **ngay hôm nay**. Không cần đợi feature hoàn tất mới biết có nguy cơ trễ.

**Đừng kết luận mọi feature tiếp theo sẽ xong trong bảy ngày.** Tập mẫu quá nhỏ, biến thiên cao và feature có thể khác kích thước, phụ thuộc, mức rủi ro.

### Đường đo phải nhất quán

Nếu tuần trước cycle time tính từ “In Development” tới “Done” còn tuần sau tính từ “Ready” tới “Released”, kết quả không so sánh trực tiếp. Tương tự, chia một user story thành 10 ticket kỹ thuật sẽ làm throughput tăng **mà chưa chắc giá trị tăng**.

### Kết hợp flow với outcome

Nhóm cải thiện từ 12 ngày xuống 6 ngày để giao một lát cắt, nhưng lát cắt không giúp người học mở bài nhanh hơn: **flow đã tốt hơn, giả thuyết sản phẩm cần đổi**. Ngược lại, người học thích tính năng nhưng đội cần hai tháng mới cập nhật được một lỗi nhỏ: **outcome tốt, khả năng thích ứng còn yếu**.

## 7. Xem chính sách rõ ràng như một giả thuyết vận hành

**Chính sách (policy)** là những quy tắc và kỳ vọng chung về cách xử lý công việc. Trong Kanban, chúng cần được **thể hiện rõ trong Definition of Workflow**, gồm ranh giới công việc, trạng thái, điều kiện dịch chuyển, WIP control và các chính sách liên quan. Chính sách tốt phải **dễ hiểu, có thể quan sát và điều chỉnh được**.

### Ví dụ bản đồ workflow

~~~mermaid
flowchart LR
    A["Ready<br/>đủ rõ để pull"] --> B["Developing<br/>WIP ≤ 2"]
    B --> C["Review/Verify<br/>WIP ≤ 2"]
    C --> D["Done<br/>đạt tiêu chí rõ"]
    B -. "Blocked: hiện rõ<br/>và được hỗ trợ" .-> E["Gỡ phụ thuộc"]
    C -. "Blocked: hiện rõ<br/>và được hỗ trợ" .-> E
    E --> B
~~~

Đây là **chính sách minh họa**, không phải WIP limit mặc định cho mọi nhóm. Với một team đông người hoặc công việc có tính chất khác, con số có thể phù hợp hoặc không. Hàng blocked phải được thấy rõ; không nên “giấu” item bằng cách chuyển sang cột ngoài WIP chỉ để dashboard đẹp.

### Một thỏa thuận workflow tốt trả lời

1. **Loại công việc nào nằm trong workflow?** User stories, bugs, incidents hay tất cả?
2. **Bắt đầu khi nào?** Có điều kiện rõ cho một item được kéo vào Doing?
3. **Kết thúc khi nào?** “Done” là code merged, đạt Definition of Done hay đã release?
4. **WIP được kiểm soát ở đâu?** Quy tắc khi cột đầy?
5. **Blocked xử lý thế nào?** Ai phối hợp, khi nào escalate, có ghi nguyên nhân?
6. **Việc khẩn cấp đi theo chính sách nào?** Có làm gián đoạn mọi thứ hay có điều kiện rõ?
7. **Khi nào chính sách được xem lại?** Dựa trên kết quả nào để giữ hoặc đổi?

Việc làm rõ quy tắc thường giúp giảm **mơ hồ và tái thương lượng liên tục**, nhưng cũng có thể tạo quan liêu nếu quá nhiều bước xét duyệt không đóng góp giá trị.

## 8. Thử thay đổi WIP và chính sách pull

Giả sử nhóm thường có 9 items Doing, ba người thường xuyên phải chuyển ngữ cảnh, và có hai item chờ review hơn bốn ngày. Nhóm muốn giảm thời gian tới Done.

### Giả thuyết thay đổi

> “Nếu trong ba tuần chúng ta không bắt đầu story mới khi Review/Verify đã đầy, ưu tiên hỗ trợ hoàn tất item cũ và giới hạn tổng WIP của workflow ở mức phù hợp, thì work item age của các story sẽ giảm, cycle time bớt đuôi dài và throughput không giảm bền vững. Chất lượng và làm thêm giờ không được xấu đi.”

### Phải làm gì khi WIP chạm giới hạn?

- **Không kéo thêm việc chỉ để mọi người luôn có ticket đang gán.**
- Hỗ trợ review, kiểm thử, sửa CI, làm rõ yêu cầu và gỡ blocker cho item đang dở.
- Nếu không thể giúp vì thiếu kỹ năng, dùng pairing/kiến thức chung hoặc xử lý nguyên nhân cản trở.
- Nếu cần công việc khẩn, dùng **chính sách ngoại lệ đã thống nhất**, ghi rõ tác động tới các item khác.
- Sau cửa sổ thử, xem dữ liệu và phản hồi trước khi giữ một con số WIP.

### Đo điều gì?

| Dấu hiệu | Trước thử | Khi thử | Cần diễn giải |
| --- | --- | --- | --- |
| WIP theo thời gian | Nhiều item song song | Có giảm? | Giảm do hỗ trợ hoàn tất hay do bỏ ghi công việc? |
| Work item age | Có item >10 ngày | Tuổi item già giảm? | Xem các item bị chặn thực tế |
| Cycle time distribution | Đuôi dài | Trung vị/percentiles thay đổi? | Đừng chỉ nhìn một trung bình |
| Throughput | Số item Done | Có ổn định/tăng về dài hạn? | Có đổi cách chia item không? |
| Rework/defects | Lỗi sau review/test | Có tăng không? | Chất lượng là guardrail |
| Team load | Chuyển ngữ cảnh/làm thêm giờ | Có bền vững hơn? | Hỏi người thực hiện và quan sát |

Không nên tuyên bố “WIP thấp luôn tốt”. Giới hạn quá chặt khi workflow chưa rõ có thể gây tình trạng chờ vô ích hoặc làm nghẽn công việc khẩn; phải kiểm chứng trong **bối cảnh năng lực và biến thiên nhu cầu**.

## 9. Điều chỉnh chính sách chất lượng: rõ “Done”, không hạ chuẩn

Khi công việc bị trễ, một phản ứng sai là **giảm Definition of Done**, bỏ kiểm thử hoặc gọi “code complete” thành Done. Cách này làm chỉ số giao hàng đẹp nhưng chuyển rủi ro sang người dùng và những Sprint tiếp theo.

### Những chính sách cần phân biệt

| Chính sách | Nội dung phù hợp | Sai lầm thường gặp |
| --- | --- | --- |
| **Definition of Done (Scrum)** | Cam kết chất lượng cho Increment; công việc phải đạt mới là phần của Increment | Hạ DoD để đóng ticket cho đủ mục tiêu |
| **Acceptance criteria của PBI** | Điều kiện cụ thể giúp làm rõ một nhu cầu và cách xác nhận | Xem như thay thế hoàn toàn các tiêu chuẩn chất lượng chung |
| **Definition of Workflow (Kanban)** | Ranh giới, trạng thái, chính sách rõ để công việc đi qua flow | Giả định một workflow áp dụng cho mọi loại việc |
| **Pull/review policy** | Khi nào kéo việc mới, khi nào review và xử lý blocker | Chính sách quá cứng gây chờ hoặc thiếu người chịu trách nhiệm |
| **Release/deployment policy** | Ai quyết định exposure, gates và cách bảo vệ production | Nhầm code merge với release và outcome |

### Ví dụ cải tiến đúng

**Trước:** “Story Done khi PR đã được approve.” Nhiều lỗi checkpoint chỉ xuất hiện khi build integration sau đó.

**Sau khi phân tích:** Nhóm giữ chất lượng nhưng làm rõ rằng Increment liên quan phải có **unit/API regression tests, integration checks quan trọng, kiểm soát quyền và xác nhận quy tắc nghiệp vụ**, rồi thiết kế pipeline giúp kiểm tra sớm hơn.

**Điểm khác biệt:** Không thêm thủ tục ký tên cuối kỳ, mà dịch việc chứng minh chất lượng **về gần thời điểm thực hiện** bằng automation, review và thảo luận ví dụ.

## 10. Cải tiến kỹ thuật dựa trên loại lỗi thật

Không phải cứ “làm TDD” hoặc “thêm CI” là tất cả vấn đề được giải quyết. Cần đặt **loại rủi ro hoặc độ trễ** trước khi chọn công cụ.

| Triệu chứng có bằng chứng | Giả thuyết kỹ thuật | Thực hành đáng thử | Bằng chứng sau thử |
| --- | --- | --- | --- |
| Lỗi nghiệp vụ lặp lại sau refactor | Thiếu kiểm thử quy tắc nhỏ | TDD/unit regression tests ở domain | Lỗi tái xuất ít hơn, CI bắt sớm hơn |
| Lỗi API chỉ thấy ở staging | Thiếu feedback tích hợp sớm | Contract/API integration tests và CI | Contract breaks bị phát hiện trước merge/release |
| Build thường xuyên hỏng sau nhiều ngày | Nhánh sống lâu, tích hợp muộn | Tích hợp thay đổi nhỏ, CI đáng tin | Thời gian nhánh tồn tại và fix build giảm |
| PR rất lớn, khó review | Thay đổi quá nhiều nội dung mỗi lần | Chia vertical slices, refactor và review thường xuyên | Review age, defect/rework có cải thiện? |
| UI báo lưu thành công giả | Xử lý bất đồng bộ thiếu kiểm tra | Component/API tests cho success/pending/failure | Không còn lỗi trạng thái lưu trong phạm vi hỗ trợ |
| Database migration hay gây outage | Schema không tương thích old/new versions | Expand–migrate–contract, migration tests | Ít lỗi deploy, khả năng phục hồi tốt hơn |
| Triển khai chậm do kiểm tra thủ công lặp lại | Chưa tự động hóa kiểm tra có oracle rõ | Test automation và pipeline phù hợp | Deployment waiting time giảm, quality guardrails đạt |
| Bugs chỉ thấy sau production | Thiếu observability/rollout kiểm soát | Monitoring, smoke, canary và điều kiện dừng | Phát hiện và giảm hậu quả sự cố nhanh hơn |

### Kỹ thuật nào không thể giải quyết thay vấn đề sản phẩm?

Nếu học viên không sử dụng nút Học tiếp vì **nó không giải quyết nhu cầu**, thêm 1.000 unit tests không làm tính năng có ích hơn. Nếu mục tiêu người dùng mơ hồ, nên ưu tiên **nghiên cứu nhu cầu, user story mapping, ví dụ nghiệp vụ và phát hành lát cắt để học** trước khi tối ưu sâu một kiến trúc không cần thiết.

### Giới hạn của các số đo kỹ thuật

Code coverage cao không chứng minh kiểm thử đã bảo vệ đúng quy tắc; số commit hay PR không phải năng suất con người; deployment frequency cao không chứng minh người dùng nhận giá trị. Cần **số đo chất lượng thực và outcome sản phẩm** đồng hành.

## 11. CI, TDD, refactoring và test automation như một vòng học hỏi

Một trường hợp điển hình trong XP là **test-first/TDD** kết hợp CI và refactoring:

~~~text
Làm rõ quy tắc nghiệp vụ bằng ví dụ
      |
      v
Viết automated check cho hành vi đã hiểu
      |
      v
Triển khai thay đổi nhỏ
      |
      v
Refactor có bảo vệ của tests
      |
      v
Tích hợp thường xuyên, CI chạy
      |
      v
Nhận feedback; khám phá rủi ro còn thiếu
      |
      '--> Thêm ví dụ/kiểm tra và điều chỉnh thiết kế
~~~

Khi nhóm thấy nhiều lỗi phân quyền chỉ xuất hiện ở cuối Sprint, có thể chọn **API authorization tests** thay vì chỉ bổ sung nhiều UI end-to-end tests. Mục tiêu là **feedback đúng rủi ro sớm hơn**. Người thử khám phá vẫn cần đặt câu hỏi về trường hợp chưa có trong tests, đặc biệt điều kiện dữ liệu thật, session và quyền truy cập.

### Ví dụ ngắn về kiểm tra hồi quy

Giả sử sản phẩm quy định: người học không được xem checkpoint của tài khoản khác. Một ví dụ kiểm tra tự động có thể được mô tả bằng Gherkin:

~~~gherkin
Feature: Chỉ đọc tiến độ học tập được cấp quyền

  Scenario: Học viên không được đọc checkpoint của người khác
    Given tài khoản A có checkpoint ở khóa học K
      And tài khoản B không có quyền đọc tiến độ của A
    When B yêu cầu checkpoint thuộc A qua API
    Then hệ thống từ chối theo chính sách phân quyền
      And response không tiết lộ nội dung checkpoint của A
~~~

Sau khi tự động hóa bài kiểm tra quan trọng, cần đo **thời gian phản hồi pipeline, độ ổn định của test và lỗi lọt production**. Nếu suite quá flaky, Developers có thể mất niềm tin; cải tiến tiếp theo là **sửa chất lượng tests** thay vì chỉ thêm số lượng.

## 12. Cải tiến phối hợp: giảm thời gian chờ và mất ngữ cảnh

Nhiều vấn đề được gọi là “vấn đề kỹ thuật” thực ra bắt nguồn từ **cách chuyển thông tin hoặc quyền quyết định**:

- User story được bàn giao với ví dụ mơ hồ, Developers đợi Product Owner trả lời.
- PR chỉ một chuyên gia hiểu, người đó nghỉ thì hàng review bị chặn.
- Người kiểm thử chỉ nhìn feature khi code xong nên phát hiện sai quy tắc muộn.
- Hai nhóm phụ thuộc API nhưng không có lịch trao đổi contract sớm.
- Một người xử lý nhiều việc gấp vì mọi người đều gán “priority high”.

### Những thỏa thuận phối hợp có thể thử

| Tình huống | Thay đổi có chủ đích | Kết quả kỳ vọng |
| --- | --- | --- |
| Yêu cầu thường thiếu ví dụ | **Three amigos** giữa góc nhìn nghiệp vụ, phát triển và kiểm thử trước khi làm lát cắt khó | Ít câu hỏi chặn giữa chừng, giảm rework do hiểu sai |
| Reviewer duy nhất thành nút thắt | **Pairing/knowledge sharing**, reviewer dự phòng và review theo rủi ro | Review age giảm mà chất lượng không giảm |
| Nhiều item gần Done nhưng không xong | **Swarming** để hoàn tất một item thay vì mỗi người bắt đầu việc khác | Work item age và WIP giảm |
| Product Owner quá nhiều yêu cầu rời rạc | Nhịp **backlog clarification** và quy tắc kênh ưu tiên | Bớt gián đoạn, quyết định thứ tự rõ |
| Phụ thuộc giữa hai team xuất hiện muộn | **Contract review** sớm và đối tác phối hợp được xác định | Ít lỗi tích hợp/đợi phê duyệt |
| Họp nhiều nhưng không ra quyết định | Mỗi cuộc họp có mục đích, đầu ra và người quyết định | Thời gian họp giảm, blocker resolution nhanh |

**Three amigos** không bắt buộc ba chức danh riêng; điều quan trọng là có đủ **góc nhìn nghiệp vụ, kỹ thuật và chất lượng**. Pairing không thay được mọi code review; swarming cũng không đồng nghĩa mọi người lao vào một việc không cần thiết. Chọn theo **điểm nghẽn thực tế**.

### Vai trò và quyền quyết định phải rõ

Trong Scrum, **Product Owner** chịu trách nhiệm tối đa hóa giá trị và sắp xếp Product Backlog; **Developers** quyết định cách biến PBIs thành Increment đạt Definition of Done; **Scrum Master** hỗ trợ hiệu quả Scrum Team và loại bỏ trở ngại. Các trách nhiệm này không tự biến mất khi nhóm thử một chính sách Kanban hoặc một kỹ thuật XP.

Một manager có thể giúp gỡ phụ thuộc tổ chức, bảo vệ năng lực và cải thiện môi trường. Nhưng không nên yêu cầu mọi thay đổi nhỏ phải có thêm một tầng phê duyệt chỉ vì “cần quản lý cải tiến”.

## 13. Chọn thay đổi bằng giả thuyết có thể kiểm chứng

Một **improvement experiment** nên đủ cụ thể để đánh giá, không phải một lời hứa cảm tính.

### Mẫu ghi nhận giả thuyết

~~~text
IMPROVEMENT ID:
  Một mã ngắn để liên kết quyết định và bằng chứng.

OBSERVED PROBLEM:
  Triệu chứng và dữ liệu, loại công việc bị ảnh hưởng.

HYPOTHESIS:
  Nếu thay đổi [chính sách/kỹ thuật/phối hợp] trong [phạm vi],
  thì [kết quả đo] sẽ cải thiện vì [cơ chế].

BASELINE:
  Mức hiện tại, khoảng quan sát, định nghĩa metric.

CHANGE:
  Quy tắc hoặc hành vi cụ thể sẽ khác đi, ai thực hiện.

SCOPE & TIMEBOX:
  Loại việc, nhóm, môi trường và cửa sổ đánh giá.

SUCCESS / DECISION CRITERIA:
  Điều kiện giữ/điều chỉnh/dừng; mức bất định.

GUARDRAILS:
  Chất lượng, bảo mật, giá trị người dùng, tính bền vững.

EVIDENCE COLLECTION:
  Nguồn metrics, phản hồi định tính, ai đối chiếu.

REVIEW DATE & OWNER:
  Ai phối hợp đánh giá, có quyền quyết định điều gì.
~~~

### Ví dụ một giả thuyết hoàn chỉnh

> **Quan sát:** Các story thuộc luồng tiến độ học tập có median review waiting time khoảng ba ngày làm việc; nhiều PR chỉ được review khi gần hết Sprint.  
> **Giả thuyết:** Khi hàng Review/Verify có hai item, Developers ưu tiên review/pairing trước khi kéo story mới, giúp giảm thời gian chờ review và tuổi item dở mà vẫn bảo vệ chất lượng.  
> **Phạm vi:** Những PBIs cùng loại trong ba tuần, không dùng sự cố production khẩn làm mẫu giống story thông thường.  
> **Bằng chứng:** Review waiting time, work item age, cycle time, WIP, lỗi review bỏ sót, phản hồi nhóm.  
> **Guardrails:** Không tăng lỗi hồi quy hay làm thêm giờ; blocked items được xử lý theo chính sách công khai.  
> **Quyết định:** Sau ba tuần, xem kết quả, sự thay đổi về thành phần item và chi phí phối hợp để giữ, thay con số WIP hoặc dừng.

**Một giả thuyết không cần chính xác tuyệt đối từ đầu.** Nó cần **có thể bác bỏ hoặc điều chỉnh bằng bằng chứng**. Nếu phát hiện workflow thay đổi cách ghi thời gian, hãy ghi lại định nghĩa đo thay vì so sánh các số không tương đồng.

## 14. PDCA và vòng thực nghiệm cải tiến

Một khung có ích là **Plan–Do–Check–Act (PDCA)**. Nó nhắc nhóm rằng **kế hoạch cải tiến chỉ là giả thuyết**, cần thực hiện, kiểm tra và hành động theo kết quả.

| Bước PDCA | Câu hỏi | Ví dụ với chính sách review |
| --- | --- | --- |
| **Plan — Lập kế hoạch** | Vấn đề gì, vì sao xảy ra, đổi gì, đo thế nào? | Review age cao; giả thuyết cần ưu tiên hoàn tất trước kéo việc mới |
| **Do — Thực hiện** | Thử thay đổi với phạm vi và thời gian đã chọn | Hai tuần áp dụng WIP limit phù hợp và pairing ở PR khó |
| **Check — Kiểm tra** | Bằng chứng thực tế hỗ trợ hay bác bỏ giả thuyết? | So sánh work item age, cycle time, rework và cảm nhận team |
| **Act — Hành động** | Giữ, điều chỉnh, loại bỏ hay thử tiếp? | Giữ nguyên rule nếu hữu ích, đổi ngưỡng nếu gây chờ, cập nhật cách ghi chính sách |

### “Check” không phải kiểm tra để chứng minh mình đã đúng

Nếu chỉ tìm bằng chứng xác nhận ý tưởng, nhóm có thể bỏ qua chuyện **thời gian review giảm nhưng lỗi lọt tăng**. Khi Plan, cần nêu trước **các điều kiện thất bại/guardrails** để tránh thay đổi cách diễn giải sau khi thấy kết quả.

### “Act” phải tạo ra sự thay đổi thật

Một retro ghi “cải thiện quá trình review” mà không xác định thỏa thuận, owner, nhịp kiểm tra hoặc quyết định áp dụng thì vòng PDCA **chưa khép**. Một hành động đủ nhỏ và được thử ngay thường tốt hơn danh sách 15 ý tưởng nhưng không ai sở hữu.

### Khi nào cần thử rộng hơn?

Nếu quy tắc đã có tín hiệu hữu ích trên một loại công việc, có thể **mở rộng dần sang loại khác** với điều kiện đo thích hợp. Không tự suy rằng một thỏa thuận tốt cho story UI cũng đúng cho **incident nghiêm trọng** hoặc thay đổi cơ sở dữ liệu có nhiều phụ thuộc.

## 15. Quyết định đòn bẩy nào nên thử trước

Khi đứng trước cùng một triệu chứng, nhiều cách cải tiến có thể hợp lý. Thay vì chọn theo sở thích công cụ hay chức danh, hãy xem **giả thuyết về nơi tạo độ trễ/sai sót**.

| Triệu chứng | Giả thuyết có thể có | Đòn bẩy thử | Tín hiệu kỳ vọng | Guardrail |
| --- | --- | --- | --- | --- |
| Story thường chờ review lâu | WIP quá cao và không có ưu tiên hoàn tất | **Chính sách:** pull/WIP, review escalation | Review age/cycle time giảm | Defects không tăng |
| Review vẫn lâu dù WIP thấp | PR lớn, thay đổi khó hiểu | **Kỹ thuật:** PR nhỏ, refactor, CI checks | Review duration/rework giảm | Không chia vụn thiếu ngữ cảnh |
| Chỉ một người approve được | Silo kiến thức, thiếu reviewer dự phòng | **Phối hợp:** pairing, kiến thức chung, ownership rõ | Blocked time giảm | Không mất trách nhiệm kỹ thuật |
| Build xanh nhưng tích hợp lỗi muộn | Thiếu contract/integration checks | **Kỹ thuật:** CI và API tests theo rủi ro | Lỗi được bắt trước môi trường cuối | Test đáng tin, chạy đủ nhanh |
| User story liên tục thay đổi cách hiểu | Thiếu ví dụ và trao đổi sớm | **Phối hợp:** three amigos, ví dụ nghiệp vụ | Rework và clarification time giảm | Không biến refinement thành họp kéo dài |
| Team liên tục bị gián đoạn bởi sự cố | Chính sách xử lý việc khẩn không rõ | **Chính sách + phối hợp:** triage, expedite có điều kiện, người trực luân phiên | Ít ngắt quãng không cần thiết, xử lý sự cố nhanh | Sự cố nghiêm trọng vẫn được ưu tiên |
| Release ít vì phải deploy thủ công | Quy trình thiếu tự động hóa và kiểm tra | **Kỹ thuật:** pipeline, artifact định danh, smoke tests | Deployment waiting time giảm | An toàn sản xuất được bảo vệ |
| Người học không dùng tính năng mới | Vấn đề chưa được giải quyết đúng | **Sản phẩm + phối hợp:** nghiên cứu, kiểm chứng giả thuyết | Task success/outcome cải thiện | Không tối ưu click gây hại |

**Thay đổi chính sách không thay được năng lực kỹ thuật**, và kỹ thuật không sửa được quy tắc ưu tiên không rõ. Ngược lại, một buổi họp nhiều người không giải quyết được pipeline flaky nếu không có thời gian và trách nhiệm cải thiện tests.

### Đừng tối ưu cục bộ mà làm cả hệ thống tệ đi

Ví dụ, bắt reviewers luôn trả lời trong một giờ có thể làm **review waiting time** giảm, nhưng khiến họ không thể hoàn tất việc của mình và phải liên tục chuyển ngữ cảnh. Khi đó **cycle time toàn workflow**, chất lượng review và sức khỏe nhóm có thể xấu đi.

Phải đo **kết quả end-to-end** và tác động qua các bước, không chỉ thời gian của một cột riêng.

## 16. Đọc dữ liệu trước–sau một cải tiến

Giả sử nhóm thử chính sách ưu tiên hoàn tất và CI review checks. Dữ liệu **minh họa**, cùng định nghĩa story và ranh giới workflow, được ghi:

| Chỉ số | Giai đoạn trước | Giai đoạn thử | Cách diễn giải |
| --- | ---: | ---: | --- |
| **Median cycle time** | 9 ngày làm việc | 6 ngày làm việc | Có tín hiệu giao việc nhanh hơn, cần xem phân bố và loại việc |
| **WIP trung bình** | 11 items | 6 items | Có ít công việc dở hơn |
| **Median review waiting time** | 3 ngày | 1 ngày | Phù hợp giả thuyết nút thắt review giảm |
| **Throughput** | 13 stories/3 tuần | 14 stories/3 tuần | Gần tương đương; số ít và mix công việc khác nhau |
| **Lỗi hồi quy đáng chú ý** | 2 trường hợp | 1 trường hợp | Chưa đủ cơ sở khẳng định độ tin cậy tăng vì mẫu nhỏ |
| **Giờ làm thêm** | Cao ở cuối kỳ | Ít hơn theo ghi nhận | Cần kiểm tra dữ liệu và phản hồi về tính bền vững |

### Cách không nên kết luận

> “Chính sách WIP đã làm cycle time giảm đúng 33,3% và chắc chắn giảm lỗi 50%.”

Kết luận này quá mạnh: chưa biết **loại story, mức độ phức tạp, kỳ nghỉ, thay đổi nhân sự hoặc nguồn gây lỗi** có khác nhau không. Hai trường hợp lỗi so với một trường hợp lỗi không đủ cho tỷ lệ lỗi có ý nghĩa.

### Cách diễn giải thận trọng

> “Trong ba tuần thử, WIP và thời gian chờ review giảm; median cycle time cũng thấp hơn và throughput chưa cho thấy suy giảm rõ. Các tín hiệu phù hợp với giả thuyết ưu tiên hoàn tất giúp flow tốt hơn. Tuy nhiên, mẫu còn nhỏ và có thể có thay đổi loại công việc. Nhóm đề xuất giữ thỏa thuận thêm một chu kỳ, theo dõi phân bố cycle time, loại lỗi và phản hồi người thực hiện.”

**Kết quả tốt không bắt buộc phải là bằng chứng nhân quả tuyệt đối**, nhưng phải đủ trung thực để chọn bước tiếp có rủi ro chấp nhận được.

### Phân biệt thay đổi tuyệt đối và tương đối

Median cycle time từ **9 xuống 6 ngày** giảm **3 ngày** và giảm khoảng \(3/9\times 100\%\approx33{,}3\%\) về mặt số học. Điều đó không cho biết **mọi item** đều nhanh hơn 33,3%, vì mỗi kỳ có một tập items và phân bố khác nhau.

## 17. Case study: cải tiến ba đòn bẩy cho tính năng “Học tiếp”

Đây là **tình huống giả định** của một đội phát triển nền tảng học trực tuyến. Các mốc và số liệu dùng để học cách ra quyết định, không phải kết quả nghiên cứu của dự án thật.

### 17.1. Bối cảnh và triệu chứng

Đội có tám Developers, một Product Owner và một Scrum Master; nhóm có các năng lực kiểm thử, thiết kế và vận hành được phối hợp theo nhu cầu. Họ muốn giao luồng **học viên mở lại đúng bài từ vị trí dở**.

Trong hai Sprint gần nhất:

- Nhiều story bắt đầu sớm nhưng chỉ Done cuối Sprint.
- Review phụ thuộc một người hiểu phần tiến độ học tập.
- UI và API có thay đổi riêng, chỉ tích hợp gần thời điểm demo.
- Một số lỗi liên quan quyền học hoặc checkpoint chỉ xuất hiện ở staging.
- Product Owner liên tục nhận câu hỏi “Nếu một học viên có hai checkpoint thì chọn cái nào?” khi code gần xong.
- Người học thử phải thao tác nhiều bước mới quay lại bài.

### 17.2. Cùng làm rõ vấn đề thay vì đổ lỗi

Nhóm chọn một user story: “Là học viên có bài đang dở, tôi muốn mở lại bài ấy từ trang khóa học để không phải tìm thủ công.”

Họ theo dõi flow của những story tương tự, xem lỗi và quan sát một vài tác vụ người học. Các giả thuyết nổi lên:

1. **Chính sách:** quá nhiều story cùng Doing, thiếu pull policy khi Review/Verify đã đầy.
2. **Kỹ thuật:** test tự động chủ yếu happy path; thiếu kiểm tra cấp API về quyền và trường hợp checkpoint không hợp lệ.
3. **Phối hợp:** ví dụ nghiệp vụ chỉ được trao đổi vào lúc nghiệm thu; một reviewer bị phụ thuộc quá nhiều.
4. **Sản phẩm:** nút Học tiếp có thể không dễ hiểu, dù API đúng.

Họ chọn **một gói thay đổi nhỏ có liên hệ rõ** cho luồng này, không định cải tổ toàn tổ chức.

### 17.3. Lần thử thứ nhất — đổi chính sách flow

**Thay đổi:** Chỉ kéo thêm story khi nhóm còn năng lực hoàn tất; khi Review/Verify có hai item, Developers ưu tiên review và gỡ phụ thuộc cho chúng. Item blocked vẫn hiển thị và được bàn tại Daily Scrum.

**Bằng chứng:** WIP, work item age, thời gian chờ review và throughput trong ba tuần; ghi những lần việc khẩn cấp phải phá giới hạn.

**Guardrail:** Không bỏ qua review quan trọng, không yêu cầu mọi người làm thêm giờ.

**Kết quả giả định:** Hàng đợi review ngắn hơn nhưng có lúc Developers chờ người hiểu chính sách checkpoint. Nhóm nhận ra **giới hạn WIP không tự giải quyết thiếu hiểu biết miền**.

### 17.4. Lần thử thứ hai — đổi thực hành kỹ thuật

**Thay đổi:** Developers đưa các kiểm tra checkpoint/phân quyền xuống cấp unit và API, tích hợp UI–API theo lát cắt nhỏ, chạy CI mỗi lần thay đổi và làm rõ trạng thái pending/saved/error.

**Bằng chứng:** Lỗi API bị bắt trước staging, thời gian build và độ flaky, số regression phát hiện sau tích hợp, thời gian tới Done.

**Guardrail:** CI xanh phải bao gồm kiểm thử bắt buộc; không cắt bỏ kiểm tra bảo mật để làm pipeline nhanh hơn.

**Kết quả giả định:** Một test phát hiện UI đang báo “Đã lưu” trước khi request xác nhận. Nhóm sửa logic và tạo regression check, giảm nguy cơ mất tiến độ.

### 17.5. Lần thử thứ ba — đổi phối hợp

**Thay đổi:** Trước khi bắt đầu feature liên quan tiến độ, Product Owner, Developers và người có năng lực kiểm thử cùng đưa ví dụ:

- Nếu chưa có checkpoint, điều gì xảy ra?
- Nếu bài đã hoàn thành, “tiếp tục” có nghĩa gì?
- Khi hai tab cùng lưu, chính sách xung đột là gì?
- Nếu quyền học hết hạn, có được mở bài không?

Một Developer khác pair cùng chuyên gia tiến độ để chia sẻ hiểu biết và giảm rủi ro thiếu reviewer.

**Bằng chứng:** Số lần story bị chặn vì chưa rõ quy tắc, rework do sai kỳ vọng, review waiting time và phản hồi người tham gia.

**Kết quả giả định:** Các ví dụ được làm rõ sớm, ít thay đổi lớn sau khi code gần xong; nhịp trao đổi ngắn nhưng có mục đích.

### 17.6. Kiểm chứng outcome của sản phẩm

Khi Increment đạt chất lượng, nhóm thử với người học phù hợp và đo:

| Lớp kết quả | Dữ liệu cần | Diễn giải |
| --- | --- | --- |
| **Flow** | WIP, cycle time, throughput, work item age | Đội có thể giao những lát cắt mới nhanh hơn không? |
| **Quality** | Lỗi checkpoint, quyền, regression, sự cố vận hành | Tốc độ cải tiến có gây tổn hại không? |
| **Product outcome** | Tỷ lệ mở đúng bài, thời gian tìm lại bài, quan sát tác vụ | Người học có nhận lợi ích thật không? |
| **Sustainability** | Chuyển ngữ cảnh, làm thêm giờ, khả năng chia sẻ kiến thức | Nhịp thay đổi có bền vững không? |

Nếu flow tốt nhưng học viên vẫn khó hiểu nút, nhóm phải **đổi giải pháp sản phẩm**, không chỉ tiếp tục tối ưu review. Nếu outcome tốt nhưng một lỗi quyền xảy ra, **phải bảo vệ chất lượng**, không dùng sự hài lòng để bù cho an toàn.

### 17.7. Lưu bài học thành chính sách và backlog mới

Sau các lần thử, đội có thể:

1. Giữ chính sách **ưu tiên hoàn tất và WIP phù hợp** trong Definition of Workflow.
2. Thêm **regression checks bắt buộc** cho checkpoint/phân quyền vào quality policy/DoD.
3. Duy trì buổi làm rõ **ví dụ nghiệp vụ ngắn cho các story có rủi ro trạng thái phức tạp**, không bắt buộc mọi ticket nhỏ họp một giờ.
4. Thử một phương án nhãn hoặc vị trí nút với người dùng và xem outcome.
5. Chọn **một giả thuyết cải tiến tiếp theo** từ dữ liệu, tránh lập danh sách hàng chục hành động không sở hữu.

**Bài học:** Một cải tiến nhỏ có giá trị không phải thay nhiều thứ cùng lúc, mà là **tạo thay đổi có căn cứ, kiểm tra đủ rộng cả flow–quality–outcome và giữ điều thật sự hữu ích**.

## 18. Trong Scrum: gắn cải tiến với Sprint Review và Retrospective

Scrum dựa vào **minh bạch, kiểm tra và thích ứng**. **Sprint Review** tập trung kiểm tra kết quả Sprint và tiến triển tới Product Goal với bên liên quan; **Sprint Retrospective** tập trung tìm cách tăng chất lượng và hiệu quả của Scrum Team.

### Các sự kiện hỗ trợ điều gì?

| Điểm phản hồi | Câu hỏi cải tiến | Ví dụ |
| --- | --- | --- |
| **Sprint Planning** | Có rủi ro/giới hạn năng lực nào cần xét để đạt Sprint Goal? | Story Học tiếp có cần test phân quyền ngay từ đầu? |
| **Daily Scrum** | Điều gì đang cản trở tiến triển tới Sprint Goal, cần điều chỉnh kế hoạch gì? | Hai story chờ review, Developers swarm/gỡ blocker |
| **Sprint Review** | Increment và phản hồi cho thấy sản phẩm có đang tạo giá trị đúng hướng? | Học viên không nhận ra nút, Product Backlog cần đổi |
| **Sprint Retrospective** | Chất lượng và hiệu quả hợp tác/tiến trình cần thay đổi gì? | Review age cao, thử chính sách pull và pairing |
| **Trong Sprint bất kỳ lúc nào** | Có bằng chứng mới cần phản ứng ngay không? | CI thất bại hoặc phát hiện lỗi phân quyền phải xử lý sớm |

Scrum Guide không buộc Retrospective phải tạo **đúng một** hành động cải tiến, cũng không buộc mọi thay đổi chờ tới cuối Sprint. Cải tiến giá trị nhất nên được xử lý **sớm khi phù hợp**; những cải tiến được chọn có thể đưa vào Sprint Backlog của Sprint kế tiếp.

### Không biến Sprint Goal thành KPI bắt buộc đạt bằng mọi giá

Một Sprint Goal định hướng Developers phối hợp để tạo mục tiêu; **Definition of Done** bảo vệ tính chất Increment. Nếu rủi ro an toàn khiến công việc chưa đạt Done, không được hạ chuẩn để “thành công Sprint”.

Nếu Sprint Review cho thấy giả định sản phẩm sai, Product Owner có thể **sắp xếp lại Product Backlog**. Nếu Retro cho thấy lỗi hệ thống làm việc, Scrum Team có thể thay chính sách hoặc kỹ thuật. **Hai dòng phản hồi sản phẩm và quy trình cần thông với nhau**, không đóng thành hai cuộc họp chỉ để báo cáo.

### Ví dụ hành động Retro đủ cụ thể

**Không đủ:** “Cải thiện review.”

**Tốt hơn:** “Trong Sprint kế tiếp, khi có hai PR ở Review/Verify, Developers kiểm tra hàng đợi trước khi mở story mới; chúng ta ghi review waiting time, work item age và số lỗi review bỏ sót. Ở Retro sau, quyết định giữ hay điều chỉnh.”

## 19. Trong Kanban: cải tiến chính sách dựa trên dòng công việc

Kanban hướng đến **tối ưu dòng giá trị** bằng cách xác định và trực quan hóa workflow, kiểm soát WIP, quản lý work items chủ động và cải tiến liên tục. Không cần giả định Kanban phải có Sprint, một chức danh quản lý mới hay một board cố định áp dụng mọi nhóm.

### Definition of Workflow làm chính sách có thể quan sát

Một workflow hữu ích thể hiện:

- Đơn vị giá trị/work item và điểm bắt đầu–kết thúc.
- Các trạng thái thực tế và cách công việc dịch chuyển.
- Cách **kiểm soát WIP**.
- Những **explicit policies** liên quan đến pull, review, blocked, expedite và chất lượng.
- Một **Service Level Expectation (SLE)** nếu áp dụng: khoảng thời gian kỳ vọng work item hoàn tất với **một xác suất**, dựa trên dữ liệu hiện có hoặc ước lượng có công bố.

### SLE không phải deadline chắc chắn

Ví dụ giả định:

> “Với feature nhỏ thuộc nhóm thường lệ, chúng tôi kỳ vọng **85%** các work items hoàn tất trong **tối đa 10 ngày làm việc** từ khi bắt đầu theo Definition of Workflow.”

Đây là **phát biểu xác suất** để hỗ trợ quản lý work item age và kỳ vọng, không phải bảo đảm mọi item xong ngày thứ mười. Nếu một item đã 9 ngày, nhóm nên xem nguy cơ, phụ thuộc và hỗ trợ trước khi quá muộn.

### Các nhịp feedback có thể giúp

| Hoạt động thích nghi | Câu hỏi | Dữ liệu có ích |
| --- | --- | --- |
| **Theo dõi công việc đang dở** | Item nào bị chặn, item nào già, giúp ai trước? | WIP, work item age, blocked reason |
| **Replenishment** | Việc nào nên được pull khi có năng lực? | Giá trị, rủi ro, loại công việc, WIP |
| **Service delivery review** | Dịch vụ đang đáp ứng kỳ vọng tới mức nào? | Cycle time, throughput, SLE, variation |
| **Operations review nếu nhiều dòng giá trị** | Phụ thuộc xuyên hệ thống ở đâu? | Tắc nghẽn chéo, chất lượng, nhu cầu/năng lực |
| **Improvement workshop** | Chính sách nào cần thử thay đổi? | Dữ liệu trend, tình huống cụ thể, guardrails |

Đây là những nhịp **có thể áp dụng theo nhu cầu**, không phải bắt buộc thêm mọi cuộc họp có tên Kanban vào lịch. Mục tiêu là **thay đổi chính sách dựa trên tín hiệu dòng thực**, không tạo nghi thức báo cáo mới.

### Khi workflow đổi, dữ liệu cũ có còn so sánh được?

Nếu thay ranh giới “Done” từ **code merged** sang **Increment đạt quality gates và sẵn sàng release**, throughput/cycle time sẽ thay đổi do **định nghĩa**, không nhất thiết do năng lực. Cần ghi nhận ngày đổi policy, chú thích số liệu và chỉ so sánh khi cùng đơn vị/rang giới hoặc có phương pháp điều chỉnh.

## 20. Trong XP: tăng khả năng thay đổi an toàn

XP nhấn mạnh những thực hành kỹ thuật và vòng phản hồi ngắn như **TDD/test-first, continuous integration, refactoring, pair programming, simple design và small releases**.

| Nhu cầu cải tiến | Thực hành XP có thể giúp | Điều cần đo |
| --- | --- | --- |
| Rủi ro phá quy tắc khi sửa mã | Test-first/TDD và regression tests | Lỗi hồi quy, chi phí sửa và thời gian phản hồi |
| Tích hợp muộn | Continuous Integration | Build reliability, phát hiện lỗi tích hợp sớm |
| Code khó thay đổi | Refactoring có test bảo vệ | Cycle time của thay đổi tương tự, rework |
| Một người giữ kiến thức | Pair programming/knowledge sharing | Blocked time, review age, khả năng hỗ trợ chéo |
| Phản hồi người dùng chậm | Small releases và lát cắt có giá trị | Thời gian từ giả thuyết tới exposure và outcome |
| Thiết kế quá phức tạp | Simple design + kiểm chứng theo nhu cầu | Chi phí thay đổi, phạm vi không cần thiết, lỗi |

**Không áp dụng TDD như một khẩu hiệu bắt buộc cho mọi loại công việc.** Có những tình huống cần khám phá mô hình nghiệp vụ, thiết bị hoặc UI trước khi xác định oracle; có thể dùng spike có timebox, prototype, exploratory testing hoặc thử tích hợp. Khi quy tắc đã rõ, tự động hóa kiểm tra phù hợp sẽ giúp thay đổi tiếp an toàn.

### Cải tiến kỹ thuật không nhất thiết phải đổi framework quản lý

Một Scrum Team hoặc nhóm Kanban có thể thực hành TDD, CI, pairing và small releases mà không “chuyển toàn bộ tổ chức sang XP”. Cần kiểm tra sự tương thích của chính sách và responsibility, đặc biệt cách ownership/review tác động đến việc nhiều người có thể sửa chung code.

## 21. Tắc nghẽn ở cấp tổ chức: đôi khi một nhóm không tự sửa được

Không phải mọi điểm nghẽn nằm trong quyền của một Scrum Team. Ví dụ:

- Môi trường staging dùng chung và liên tục hỏng.
- Quyền triển khai cần phê duyệt qua nhiều phòng nhưng tiêu chí không rõ.
- Một dịch vụ nền tảng chỉ có một người có quyền sửa.
- Chính sách ưu tiên sản phẩm thay đổi hàng ngày bởi nhiều lãnh đạo.
- Hệ thống đánh giá nhân sự thưởng cho số ticket cá nhân nên mọi người ngại swarming.
- Năng lực bảo mật, vận hành hoặc nghiên cứu người dùng không được bố trí cho các rủi ro quan trọng.

### Cách xử lý phụ thuộc xuyên nhóm

1. **Thể hiện phụ thuộc và ảnh hưởng bằng bằng chứng**: item chờ bao lâu, lỗi/chất lượng và kết quả người dùng bị ảnh hưởng thế nào.
2. **Phân biệt phần đội tự sửa được** với phần cần quyền quyết định khác.
3. **Xác định owner phía tổ chức** cho hành động gỡ nút thắt, tránh chỉ ghi “chờ bên ngoài”.
4. **Thử thay đổi ở phạm vi an toàn**: cơ chế đặt lịch môi trường, contract review sớm, self-service pipeline, policy rõ.
5. **Kiểm chứng cả hệ thống**: một team nhanh hơn có làm team khác tắc thêm không?
6. **Công bố ảnh hưởng tới dự báo/giá trị**, không giấu phụ thuộc bằng cách chuyển item ra khỏi workflow.

### Ví dụ chính sách phê duyệt

Nếu việc deploy vẫn phải được một nhóm vận hành kiểm tra, có thể thử:

- Chuẩn hóa artifact và evidence để phê duyệt nhanh, nhất quán.
- Tự động hóa các kiểm tra có oracle rõ và audit trail.
- Phân loại thay đổi thường lệ/đặc biệt theo rủi ro, tuân thủ nghĩa vụ thực.
- Đo **deployment waiting time, change failures, recovery time và chất lượng thực tế**.

Không nên loại bỏ phê duyệt **bắt buộc theo pháp lý/hợp đồng** chỉ để số liệu flow trông tốt. Mục tiêu là giảm **lãng phí và sự không rõ ràng**, vẫn bảo vệ các ràng buộc chính đáng.

## 22. Thay đổi an toàn: giới hạn thử nghiệm, guardrails và quyền quay lại

Không phải mọi cải tiến đều là thử nghiệm vô hại. Một quy tắc mới có thể làm tăng thời gian chờ sự cố; một pipeline mới có thể đưa mã sai tới production nhanh hơn; một chính sách yêu cầu luôn pairing có thể tiêu tốn năng lực mà không giúp các công việc đơn giản.

### Phân loại trước khi thử

| Loại thay đổi | Ví dụ | Cách giảm rủi ro |
| --- | --- | --- |
| **Dễ hoàn tác, tác động nhỏ** | Thay format câu hỏi trong Daily Scrum, thử giới hạn hai PR review | Timebox ngắn, ghi mục tiêu, xem phản hồi |
| **Tác động nhiều người hoặc workflow** | Đổi tiêu chí pull, trách nhiệm reviewer và lịch handoff | Đồng thuận những người chịu ảnh hưởng, công khai chính sách, giữ khả năng điều chỉnh |
| **Có ảnh hưởng chất lượng/production** | Bỏ bước kiểm tra, auto deploy, đổi schema dữ liệu | Đánh giá an toàn, quality gates, thử môi trường kiểm soát, rollback/roll-forward |
| **Liên quan bảo mật/tuân thủ** | Thay quyền duyệt, chính sách ghi log học viên | Quyền quyết định phù hợp, kiểm soát pháp lý và riêng tư, audit trail |

### Mẫu guardrails của một cải tiến

Một thử nghiệm “đưa review xuống một ngày” phải nêu:

- **Không bỏ kiểm tra phân quyền/quality gate quan trọng.**
- Không dùng làm thêm giờ kéo dài để đạt số mục tiêu.
- Không làm quá tải một người duy nhất.
- Không giảm khả năng xử lý incident mức cao.
- Nếu rủi ro nghiêm trọng xuất hiện, **dừng thử ngay**, không đợi buổi retrospective.

### Khi nào hoàn tác?

Cần **quyết định trước** những trường hợp phải quay lại chính sách cũ hoặc sửa thử nghiệm. Ví dụ nếu policy mới khiến lỗi sản xuất tăng rõ, đối tượng chịu ảnh hưởng không được hỗ trợ hoặc hàng blocked bị giấu, nhóm nên tạm ngừng/điều chỉnh ngay.

Không mọi thay đổi đều có thể rollback đơn giản: migration dữ liệu hoặc tái tổ chức ownership có thể để lại phụ thuộc. Vì vậy, **độ dễ hoàn tác** là một tiêu chí khi chọn phép thử đầu tiên.

## 23. Thiết kế nhịp kiểm tra kết quả và bảng điều hành tối thiểu

Một hệ thống cải tiến hiệu quả cần biết **lúc nào dữ liệu đã đủ và ai có thể hành động**. Xem dashboard mỗi giờ không làm outcome D7 đến nhanh hơn; nhưng chờ cuối Sprint để phản ứng với lỗi mất dữ liệu lại quá muộn.

### Nhịp phản hồi gợi ý

| Thời điểm/trigger | Điều xem | Quyết định |
| --- | --- | --- |
| **Ngay khi phát hiện rủi ro cao** | Sai quyền, mất dữ liệu, build critical fail, incident | Dừng rollout, khôi phục an toàn, thông báo và điều tra |
| **Hằng ngày hoặc mỗi lần quản lý flow** | Work item age, WIP, blocked items, hàng chờ review | Swarm, gỡ blocker, điều chỉnh pull trước khi item già |
| **Mỗi vòng giao hàng ngắn** | Cycle time, chất lượng CI, lỗi tích hợp, kết quả lát cắt | Sửa cách làm, test và triển khai phù hợp |
| **Sprint Review hoặc nhịp phản hồi sản phẩm** | Increment, outcome gần, quan sát bên liên quan | Thay Product Backlog và mục tiêu khám phá |
| **Sprint Retrospective / improvement review** | Giả thuyết thay đổi, bằng chứng, guardrails và phản hồi nhóm | Giữ, sửa, dừng hoặc thử tiếp |
| **Sau cửa sổ cohort đủ dài** | Retention/học tập có ý nghĩa, tác động dài hạn | Kiểm tra hướng Product Goal và mức đầu tư |

### Một bảng điều hành gọn

| Câu hỏi | Metric/nguồn | Cửa sổ | Ai sử dụng |
| --- | --- | --- | --- |
| Người học đã được lợi? | Task success, time-to-resume, phản hồi học viên | Theo exposure/cohort | Product Owner và Scrum Team |
| Tính năng có đáng tin? | Checkpoint errors, security checks, incident logs | Liên tục và sau release | Developers, bảo mật/vận hành |
| Công việc có đi đến Done? | WIP, age, cycle time, throughput | Hằng ngày/tuần | Những người điều hành flow |
| Thử nghiệm chính sách có tác dụng? | Review waiting time + flow/quality guardrails | Cửa sổ thử đã định | Scrum Team/nhóm cải tiến |
| Mọi người có duy trì được nhịp? | Phản hồi nhóm, làm thêm giờ, phụ thuộc chuyên gia | Theo chu kỳ thích hợp | Team và người hỗ trợ tổ chức |

**Ít chỉ số nhưng có chủ đích** tốt hơn nhiều dashboard không ai dùng để quyết định. Mọi metric cần thống nhất **đơn vị, thời điểm bắt đầu/kết thúc, nguồn và giới hạn diễn giải**.

### Decision log một trang

~~~text
IMPROVEMENT:
  [Tên thay đổi]

VẤN ĐỀ & BASELINE:
  [Tình huống thực, cách đo, nguồn dữ liệu]

GIẢ THUYẾT:
  [Nếu X thì Y vì Z]

PHẠM VI THỬ:
  [Loại việc, team, timebox, người phối hợp]

BẰNG CHỨNG:
  [Flow, quality, outcome, sustainability, ngoại lệ]

GIỚI HẠN:
  [Mẫu nhỏ, mix công việc, sự kiện ngoài dự kiến]

QUYẾT ĐỊNH:
  [Giữ / đổi / hoàn tác / thử thêm] và lý do

NEXT ACTION:
  [Owner, thay đổi cụ thể, ngày xem lại]
~~~

Nhật ký không nhất thiết là một tài liệu trang trọng; một thẻ improvement trong backlog cũng có thể chứa đủ thông tin. Điều quan trọng là **khả năng kiểm tra những gì đã thử và học được**, không phải số biểu mẫu.

## 24. Các phản mẫu khiến “cải tiến liên tục” thành hình thức

### 24.1. Lặp lại câu “giao tiếp tốt hơn”

Không xác định ai cần trao đổi gì, lúc nào, nhằm quyết định nào. **Cải tiến:** thử một thỏa thuận cụ thể như làm rõ ví dụ nghiệp vụ trước khi bắt đầu story có quy tắc phức tạp; đo clarification time và rework.

### 24.2. Retrospective nào cũng có 10 hành động

Nhiều ý tưởng nhưng không đủ năng lực thực hiện. **Cải tiến:** chọn một hoặc vài giả thuyết tác động cao, làm nhỏ, gắn owner, timebox và mốc review; giữ những ý tưởng còn lại để ưu tiên sau.

### 24.3. Thay chính sách nhưng không nói với người thực hiện

WIP limit trên bảng không khớp thỏa thuận thực tế; mỗi người giải thích “Done” khác nhau. **Cải tiến:** công khai quy tắc, đi qua ví dụ, xác định ngoại lệ và ngày kiểm tra.

### 24.4. Tối ưu số lượng ticket Done

Nhóm chia mỗi story thành nhiều task nhỏ để throughput tăng. **Cải tiến:** theo dõi đơn vị giá trị nhất quán, cycle time, chất lượng và outcome sản phẩm.

### 24.5. Hạ Definition of Done để đạt mục tiêu Sprint

Đẩy lỗi về tương lai và làm con số đẹp giả. **Cải tiến:** điều chỉnh phạm vi, ưu tiên và năng lực; giữ điều kiện chất lượng bắt buộc.

### 24.6. Yêu cầu mọi người bận 100%

Không ai có thời gian review, swarm, học kỹ thuật hoặc xử lý sự cố. **Cải tiến:** quản lý WIP theo flow, ưu tiên hoàn tất việc; xem sự chờ và chuyển ngữ cảnh.

### 24.7. Áp đặt WIP limit giống nhau cho mọi nhóm

Nhu cầu, loại công việc, số người và phụ thuộc khác nhau. **Cải tiến:** bắt đầu bằng dữ liệu hệ thống riêng, thử và cập nhật con số theo kết quả.

### 24.8. Đổi nhiều thứ cùng lúc rồi tuyên bố đã chứng minh nguyên nhân

Không phân biệt tác động của policy, test automation hay thay nhân sự. **Cải tiến:** nêu rõ gói thay đổi, lời giải thích thay thế, giữ độ khiêm tốn trong kết luận và chọn thử tiếp.

### 24.9. Dùng số đo để so sánh/xếp hạng từng người

Khuyến khích né việc khó, không báo blocker, hạn chế hỗ trợ người khác. **Cải tiến:** đo hệ thống, không thưởng/phạt cá nhân qua story points, throughput hoặc bug counts.

### 24.10. Chỉ đo flow, bỏ qua giá trị người dùng

Một nhóm có thể giao nhanh tính năng không ai cần. **Cải tiến:** xem product outcome và phản hồi cùng delivery metrics.

### 24.11. Chỉ đo outcome, bỏ qua chất lượng

Conversion tăng có thể đồng thời xảy ra cùng lỗi dữ liệu. **Cải tiến:** guardrails bắt buộc và theo dõi reliability, privacy, security.

### 24.12. Trông đợi một công cụ mới sửa vấn đề văn hóa

Thêm board hoặc CI server không giải quyết trách nhiệm mơ hồ, sợ báo lỗi hay quyền quyết định thiếu rõ. **Cải tiến:** cải thiện thỏa thuận, sự an toàn khi nêu trở ngại và năng lực hỗ trợ, cùng công cụ phù hợp.

### 24.13. Giữ nguyên cải tiến dù dữ liệu bất lợi

Chính sách đã được lãnh đạo ủng hộ nên không ai dám thừa nhận nó tạo thêm chờ. **Cải tiến:** định nghĩa điều kiện điều chỉnh/hoàn tác trước khi thử, ghi cả phản hồi tiêu cực.

### 24.14. Cho rằng một kết quả ngắn hạn là bằng chứng nhân quả

Cycle time giảm đúng kỳ có ít sự cố hoặc người dùng đổi mùa học. **Cải tiến:** xem mix công việc, phân bố và thời gian dài hơn nếu cần; nêu mức chắc chắn.

### 24.15. Đợi đến cuối Sprint mới phản ứng với lỗi nghiêm trọng

Sai phân quyền hoặc mất dữ liệu cần hành động ngay. **Cải tiến:** có cơ chế escalation, quality gates và incident response theo mức rủi ro.

### 24.16. Tạo quá nhiều cuộc họp “để Agile hơn”

Họp nhiều không chứng minh hợp tác tốt, đôi khi kéo dài việc. **Cải tiến:** mỗi nhịp có mục đích và quyết định rõ, bỏ những bước trùng lặp không tạo thông tin hoặc hành động.

### 24.17. “Xây hết backlog cải tiến rồi sẽ tốt”

Improvement backlog là **tập giả thuyết ưu tiên**, không phải cam kết thực hiện mọi ý tưởng. **Cải tiến:** kiểm tra điều gì đang thực sự giới hạn giá trị và chọn việc phù hợp năng lực.

### 24.18. Đóng issue ngay khi đã sửa code

Một lỗi có thể tái xuất hoặc người dùng chưa được phục hồi. **Cải tiến:** phân biệt code fix, kiểm thử, deploy, sửa dữ liệu nếu cần, monitoring và outcome; chỉ công bố phần đã kiểm chứng.

## 25. Workshop 75–90 phút: điều chỉnh cách làm bằng bằng chứng

Đây là **workshop mô phỏng**, không phải sự kiện bắt buộc trong Scrum, Kanban hay XP.

**Tình huống:** Nền tảng học trực tuyến muốn giao luồng Học tiếp an toàn nhưng nhiều story chờ review và phát sinh lỗi ở cuối Sprint. Có ba loại kết quả cần nhìn: **flow, chất lượng và giá trị người học**.

| Bước | Thời lượng gợi ý | Việc thực hiện | Đầu ra |
| --- | ---: | --- | --- |
| **1. Chọn một vấn đề** | 10 phút | Xem dữ liệu workflow, lỗi và phản hồi người dùng | Problem statement không đổ lỗi |
| **2. Tìm giả thuyết** | 10 phút | Dùng 5 Whys hoặc map flow, liệt kê lời giải thích | 2–3 giả thuyết có thể kiểm tra |
| **3. Chọn đòn bẩy** | 15 phút | Phân loại chính sách, kỹ thuật và phối hợp | Một thay đổi trọng tâm, lý do và giới hạn |
| **4. Thiết kế thử nghiệm** | 15 phút | Viết baseline, scope, timebox, owner và guardrails | Improvement experiment card |
| **5. Mô phỏng tình huống** | 10–15 phút | Đóng vai item bị blocked, CI hỏng hoặc yêu cầu mới | Quy tắc phản ứng cụ thể, ngoại lệ |
| **6. Đánh giá dữ liệu giả định** | 10–15 phút | So sánh flow và chất lượng trước/sau | Quyết định có căn cứ và giới hạn suy luận |
| **7. Chuẩn hóa và chia sẻ** | 5–10 phút | Cập nhật policy hoặc việc tiếp theo | Người sở hữu, mốc đánh giá và thông tin cần báo |

### Dữ liệu workshop được cung cấp

| Quan sát | Trước thử | Sau thử |
| --- | ---: | ---: |
| Median review waiting time | 3 ngày | 1,5 ngày |
| Median cycle time | 9 ngày | 7 ngày |
| WIP trung bình | 10 items | 7 items |
| Throughput trong 3 tuần | 12 items | 13 items |
| Lỗi mức ảnh hưởng đáng kể | 1 trường hợp | 2 trường hợp |
| Phản hồi nhóm về chuyển ngữ cảnh | Nhiều | Ít hơn |

**Câu hỏi bắt buộc:** Có nên giữ chính sách mới ngay không, khi flow tốt hơn nhưng lỗi đáng kể từ một lên hai? Cần xem **loại lỗi, rủi ro, sample size, nguyên nhân và quality guardrails**; không tuyên bố thành công hoặc thất bại chỉ từ một số nhỏ.

### Tiêu chí hoàn thành workshop

1. Có **một vấn đề được phát biểu bằng bằng chứng** thay vì đánh giá cá nhân.
2. Thay đổi được chọn liên hệ rõ với **cơ chế gây vấn đề giả định**.
3. Chính sách/kỹ thuật/phối hợp được mô tả đủ cụ thể để thực hiện.
4. Có **baseline, metric, guardrail, timebox và người chịu trách nhiệm**.
5. Nêu ít nhất một **lời giải thích thay thế** cho kết quả thử.
6. Có một **quyết định phù hợp mức tin cậy** và hành động tiếp theo.

## 26. Bài tập tự kiểm tra và gợi ý

### Bài tập A — Phân loại đòn bẩy

Cho các đề xuất:

1. “Khi Review/Verify có hơn hai work items, Developers ưu tiên giúp hoàn tất trước khi pull thêm story.”
2. “Bổ sung API contract tests vào CI để kiểm tra quyền truy cập tiến độ.”
3. “Product Owner và Developers cùng làm rõ ví dụ nghiệp vụ trước khi triển khai story đa trạng thái.”
4. “Tất cả team phải báo thêm số commit mỗi ngày.”
5. “Pair programming cho một module chỉ một người đang hiểu.”

**Gợi ý:** (1) chủ yếu là **policy**; (2) là **engineering**; (3) là **collaboration**; (5) là **collaboration kết hợp engineering**. (4) chưa nêu kết quả cần cải thiện, dễ thành số đo hoạt động thiếu giá trị.

### Bài tập B — Viết giả thuyết có thể bác bỏ

Nhóm có nhiều lỗi tích hợp UI–API bị phát hiện sát cuối Sprint. Hãy điền:

~~~text
Vấn đề: ...
Giả thuyết nguyên nhân: ...
Chính sách/kỹ thuật/phối hợp sẽ thử: ...
Thời gian và phạm vi: ...
Metric chính: ...
Guardrail: ...
Điều kiện giữ/đổi/dừng: ...
~~~

**Gợi ý:** Có thể thử contract tests và tích hợp một lát cắt dọc sớm, đo thời gian từ coding tới lỗi được phát hiện, số lỗi tích hợp lọt và cycle time. Không dùng “thêm 100 test” làm metric giá trị duy nhất.

### Bài tập C — Dùng work item age

Một workflow có SLE kỳ vọng 85% các feature thông thường Done trong tối đa 10 ngày làm việc. Một feature đang dở đã 9 ngày, có blocker chờ xác nhận chính sách quyền học.

1. Feature đã chắc chắn trễ SLE chưa?
2. Nhóm nên làm gì ngay hôm nay?
3. Nếu chính sách mới yêu cầu “kéo thêm việc để mọi người có việc”, điều gì có thể xảy ra?
4. Dữ liệu nào cần khi review cải tiến?

**Gợi ý:** SLE là kỳ vọng xác suất, không lời hứa mọi item; cần làm việc với người có quyền quyết định, nhìn blocker, ưu tiên hoàn tất và tránh tăng WIP không cần.

### Bài tập D — Phân tích thay đổi trước/sau

Sau ba tuần giảm WIP, throughput tăng từ 12 lên 14 item; cycle time trung vị giảm từ 8 xuống 6 ngày. Nhưng có một sự cố dữ liệu mới.

1. Có thể khẳng định giảm WIP **gây ra** cải thiện không?
2. Sự cố dữ liệu cần được phân loại/điều tra thế nào?
3. Nên tiếp tục, dừng hay điều chỉnh chính sách khi nào?
4. Nếu những item sau nhỏ hơn trước, phép so sánh bị ảnh hưởng gì?

**Gợi ý:** Tách **chênh lệch quan sát** khỏi **suy luận nhân quả**. An toàn dữ liệu là guardrail; một sự cố nghiêm trọng có thể cần hành động ngay dù metrics flow tốt.

### Bài tập E — Chọn cải tiến giữa chính sách, kỹ thuật và phối hợp

Ba story của tính năng tiến độ đều chờ một người kiểm tra schema trong hai ngày; đồng thời CI thường thất bại do test dữ liệu phụ thuộc thứ tự chạy.

Hãy đề xuất:

- Một thay đổi chính sách giúp nhìn và giảm hàng chờ.
- Một thay đổi kỹ thuật để CI đáng tin hơn.
- Một thay đổi phối hợp để giảm phụ thuộc cá nhân.
- Hai metrics flow và hai quality/guardrail metrics.
- Một điều kiện cho biết thay đổi đang tạo ra chi phí không đáng.

**Gợi ý:** Review age/work item age, WIP, flakiness, lỗi tích hợp, làm thêm giờ và quy tắc dữ liệu. Không đánh giá bằng số người bận liên tục.

### Bài tập F — Sprint Retrospective có kết quả thật

Tại Retrospective, mọi người đề xuất 12 thay đổi và đều có vẻ hợp lý, nhưng chỉ còn đủ năng lực thử một thay đổi nhỏ trong Sprint kế tiếp.

1. Chọn ưu tiên theo tiêu chí nào?
2. Ai có trách nhiệm về vấn đề flow và ai quyết định thứ tự Product Backlog?
3. Mục tiêu cải tiến khác Sprint Goal thế nào?
4. Có thể thêm hành động vào Sprint Backlog mà vẫn giữ Sprint Goal không?
5. Nếu lỗi quyền xảy ra giữa Sprint, có cần đợi Retro mới xử lý?

**Gợi ý:** Chọn theo rủi ro và tác động tới Sprint Goal, chi phí thử, khả năng hoàn tác, dữ liệu và trách nhiệm Scrum. Lỗi an toàn cần xử lý ngay theo policy.

### Bài tập G — Phối hợp và tâm lý an toàn

Team thường không ghi blocked time vì sợ bị đánh giá kém. Dashboard vì thế cho thấy cycle time tốt, nhưng mọi người liên tục làm ngoài giờ để giải quyết phụ thuộc.

1. Vấn đề số liệu và quản trị ở đây là gì?
2. Chỉ thêm yêu cầu “ghi blocked chính xác” có đủ không?
3. Những chính sách và hành vi lãnh đạo nào giúp dữ liệu trung thực hơn?
4. Nên xem thêm guardrails nào về sức khỏe nhóm?

**Gợi ý:** Metric bị tác động bởi hệ thống đánh giá. Không thể cải tiến dựa trên dữ liệu khi nhóm phải che giấu thực tế; cần mục đích học hỏi, quyền nêu vấn đề và phản ứng không đổ lỗi.

### Bài tập H — Cải tiến kỹ thuật chưa tạo outcome

Nhóm rút ngắn thời gian deploy từ hai ngày xuống 15 phút, nhưng học viên vẫn khó tìm bài và D7 meaningful return không đổi.

1. Đã có cải tiến nào?
2. Vì sao chưa thể khẳng định cải tiến tạo giá trị học tập?
3. Nên thử giả thuyết sản phẩm nào?
4. Continuous Delivery tốt giúp học giả thuyết mới thế nào?

**Gợi ý:** Đường giao hàng đã tốt hơn nhưng **vấn đề sản phẩm có thể chưa được giải quyết**. Cần quan sát tác vụ, thay phương án, phát hành lát cắt nhỏ và đo outcome.

## 27. Checklist điều chỉnh theo kết quả

- [ ] Có một **vấn đề cụ thể**, xác định theo kết quả thay vì đổ lỗi cá nhân.
- [ ] Phân biệt **hiện tượng, nguyên nhân giả định và bằng chứng**.
- [ ] Đã xem cả **giá trị sản phẩm, flow, chất lượng và tính bền vững**.
- [ ] Định nghĩa WIP, throughput, work item age, cycle time phù hợp cùng workflow.
- [ ] Không dùng số story points, commit, bug hoặc ticket Done để xếp hạng cá nhân.
- [ ] Chọn một **đòn bẩy có cơ chế rõ**: policy, engineering, collaboration hoặc gói tối thiểu.
- [ ] Chính sách mới có **điều kiện cụ thể, người chịu ảnh hưởng và ngoại lệ**.
- [ ] Nếu áp dụng Kanban, Definition of Workflow và WIP control được hiểu nhất quán.
- [ ] Nếu dùng SLE, phát biểu xác suất và điểm bắt đầu/kết thúc rõ, không biến thành deadline tuyệt đối.
- [ ] Nếu dùng Scrum, Sprint Goal, Product Goal, quyền quyết định và Definition of Done không bị xuyên tạc.
- [ ] Thực hành XP được chọn để xử lý **rủi ro kỹ thuật thực**, không phải để gắn nhãn.
- [ ] Product Owner, Developers và các năng lực liên quan có kênh làm rõ ví dụ nghiệp vụ sớm.
- [ ] Có cơ chế phối hợp/swarms/pairing khi điểm nghẽn hoặc phụ thuộc xuất hiện.
- [ ] Giả thuyết cải tiến có **phạm vi thử, thời gian, baseline, metric và owner**.
- [ ] Nêu trước các **guardrails** bảo vệ dữ liệu, quyền riêng tư, chất lượng và sức khỏe nhóm.
- [ ] Có cơ chế **dừng/hoàn tác** khi xuất hiện rủi ro không chấp nhận được.
- [ ] Thu bằng chứng trước/sau với **cùng đơn vị, ranh giới và quy tắc đo**.
- [ ] Có xem phân bố, loại việc, mùa vụ, sự kiện ngoài dự kiến và lời giải thích thay thế.
- [ ] Không tuyên bố quan hệ nhân quả chắc chắn chỉ từ một kết quả ngắn hạn.
- [ ] Không biến họp, số hành động hoặc nhiều dashboard thành thước đo thành công.
- [ ] Retrospective và review dẫn tới **quyết định rõ**, không chỉ danh sách mong muốn.
- [ ] Phản hồi Sprint Review/người dùng thực sự ảnh hưởng tới Product Backlog khi phù hợp.
- [ ] Việc ở cấp tổ chức được gắn người có quyền xử lý, không giấu trong trạng thái “chờ bên ngoài”.
- [ ] Nhóm có thể nói **đã giữ, sửa hoặc bỏ điều gì** vì kết quả đo được.
- [ ] Bài học được ghi vừa đủ trong workflow, code tests, tài liệu thỏa thuận hoặc decision log.
- [ ] Luôn sẵn sàng lặp lại vòng học hỏi khi bối cảnh, sản phẩm hoặc năng lực nhóm thay đổi.

## 28. Tài liệu đọc thêm và tổng kết

- [Agile Manifesto](https://agilemanifesto.org/): các giá trị/phương châm giao phần mềm có ích, hợp tác và thích ứng.
- [The Scrum Guide](https://scrumguides.org/): Sprint Goal, Product Goal, Definition of Done, Sprint Review và Sprint Retrospective.
- [The Kanban Guide](https://kanbanguides.org/): Definition of Workflow, kiểm soát WIP, bốn flow metrics và Service Level Expectation.
- Kent Beck và Cynthia Andres, *Extreme Programming Explained: Embrace Change*, ấn bản 2 (2004): TDD, CI, refactoring, pairing, small releases và kỷ luật kỹ thuật.
- Mike Rother, *Toyota Kata* (2009): tư duy cải tiến có mục tiêu, kiểm tra điều kiện hiện tại và thử nghiệm có chủ đích.
- W. Edwards Deming, *Out of the Crisis* (1986): hệ thống chất lượng, quản lý và học hỏi từ quá trình.
- Mary và Tom Poppendieck, *Lean Software Development: An Agile Toolkit* (2003): giảm lãng phí, tối ưu toàn hệ thống và xây chất lượng vào quá trình.
- Gene Kim, Jez Humble, Patrick Debois và John Willis, *The DevOps Handbook* (2016; ấn bản sau có cập nhật): flow, feedback và học hỏi giữa phát triển–vận hành.
- Jez Humble và David Farley, *Continuous Delivery* (2010): khả năng đưa thay đổi an toàn tới production.
- [DORA](https://dora.dev/): nghiên cứu về năng lực giao phần mềm và độ ổn định; là nguồn bổ trợ cho việc đo cải tiến kỹ thuật.

**Kết luận:** Cải tiến liên tục trong Agile không phải thêm cuộc họp, ban hành nhiều quy tắc hay mua một công cụ mới. Nó là khả năng **quan sát kết quả thật, chọn giả thuyết có căn cứ, thử thay đổi chính sách–kỹ thuật–phối hợp phù hợp, kiểm tra tác động và điều chỉnh một cách trung thực**.

**Chính sách** giúp công việc được kéo và hoàn tất có ý thức; **thực hành kỹ thuật** giúp thay đổi phần mềm nhanh và an toàn; **phối hợp** giúp thông tin và trách nhiệm đến đúng người đúng lúc. Cả ba phải phục vụ **giá trị người dùng, chất lượng đáng tin, dòng công việc hiệu quả và nhịp làm việc bền vững**.

**Điểm cần nhớ:** Một cải tiến chỉ thật sự hoàn tất khi nhóm biết **đã thay đổi điều gì, điều gì xảy ra sau đó, có rủi ro hay giới hạn kết luận nào và quyết định tiếp là gì**. Giữ điều có ích, sửa điều chưa tốt, bỏ điều không còn phù hợp và tiếp tục học — đó là cách Agile thích ứng bằng phản hồi sớm và cải tiến liên tục.
