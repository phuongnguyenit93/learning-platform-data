# Cân nhắc Kanban khi cần quản lý dòng công việc liên tục

Một nhóm phụ trách nền tảng học trực tuyến có công việc đến từ nhiều nguồn. Product Owner muốn cải thiện chức năng **“Tiếp tục bài học đang dở”**; bộ phận hỗ trợ chuyển sang các lỗi học viên không thấy tiến độ; vận hành báo một batch job đồng bộ dữ liệu thất bại; đội bảo mật yêu cầu khắc phục một rủi ro phân quyền; đối tác lại cần xác nhận hợp đồng API trước ngày khai giảng.

Nhóm đang cố phân bổ tất cả việc vào Sprint hai tuần. Mỗi khi có sự cố quan trọng, kế hoạch Sprint bị điều chỉnh; những việc không khẩn thì bị treo ở trạng thái `In Progress`, còn Developer mở thêm ticket mới để không phải chờ review. Cuối Sprint, nhiều ticket mang nhãn “80% hoàn thành”, nhưng ít thay đổi đủ điều kiện **Definition of Done**. Một số người đề xuất bỏ hết lịch và “dùng Kanban”, nghĩa là tạo bảng ba cột *To Do – Doing – Done* rồi làm việc nào đến trước thì làm trước.

Cách hiểu đó **chưa đủ**. Kanban không phải một bảng màu sắc, cũng không phải lý do để bỏ mục tiêu sản phẩm hoặc giảm kiểm thử. **Kanban là cách quản lý và cải thiện dòng công việc bằng cách trực quan hóa, kiểm soát lượng việc đang xử lý, chủ động quản lý những việc bị chờ và dùng phản hồi để điều chỉnh chính sách.** Nó có thể đặc biệt hữu ích khi nhu cầu xuất hiện **liên tục, mức ưu tiên có thể biến động và việc chờ giữa các bước gây lãng phí đáng kể**.

Nhưng không phải cứ có việc phát sinh hoặc có hơn một team là Kanban tốt hơn Scrum. Lựa chọn cần dựa vào bản chất dòng nhu cầu, mục tiêu, quyền quyết định, mức khẩn cấp, rủi ro chất lượng và khả năng đội tự điều chỉnh. **Scrum, Kanban và các thực hành kỹ thuật của XP có thể bổ trợ nhau**, tùy cách tổ chức công việc thực tế.

Bài học thuộc chương **Lựa chọn cách tiếp cận** của mô-đun **AGILE_DEVELOPMENT**, hướng đến hiểu giá trị và nguyên tắc Agile, thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc để phát triển phần mềm thích ứng qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **Kanban như một chiến lược quản lý và cải tiến dòng giá trị**, phân biệt nó với bảng công việc và công cụ quản lý ticket.
2. Nhận diện dấu hiệu một nhóm đang có **dòng yêu cầu liên tục, thời gian đến bất định, nhiều loại công việc và hàng chờ**.
3. Phân biệt vấn đề cần Kanban với vấn đề do **mục tiêu sản phẩm mơ hồ, tổ chức component silos, thiếu kỹ năng hoặc CI/DoD yếu**.
4. So sánh **Kanban, Scrum và Scrum kết hợp Kanban** mà không biến chúng thành hai thái cực đối lập.
5. Thiết lập một **Definition of Workflow (DoW)** gồm phạm vi item, Start/Finish, trạng thái, chính sách kéo việc, WIP, xử lý blocker và kỳ vọng dịch vụ.
6. Hiểu **pull system**, **WIP limit**, chính sách ưu tiên, công việc khẩn và cách bảo vệ việc đã bắt đầu.
7. Sử dụng **Work in Progress, Throughput, Work Item Age và Cycle Time** với đơn vị, ranh giới và cách diễn giải nhất quán.
8. Tạo một **Service Level Expectation (SLE)** có cơ sở, phân biệt với thời hạn hợp đồng hoặc SLA.
9. Nhận diện bottleneck qua **aging WIP, blocked time, cumulative flow diagram (CFD)** và dòng công việc thực.
10. Thảo luận **Little’s Law và dự báo theo throughput** một cách có điều kiện, không hứa ngày hoàn thành chắc chắn.
11. Thiết kế nhịp **replenishment, flow review, delivery review, retrospective và product feedback** phù hợp.
12. Lựa chọn cách xử lý **incident, bug, feature, compliance và technical debt** trên cùng một luồng hoặc những luồng có chính sách riêng.
13. Đảm bảo **Definition of Done, kiểm thử, CI, quyền dữ liệu và giá trị người dùng** không bị đánh đổi để làm đẹp số liệu.
14. Xây kế hoạch thử Kanban có baseline, giả thuyết, chính sách minh bạch, guardrails và mốc đánh giá.
15. Nhận diện những sai lầm như **đẩy công việc vào mọi người, giấu WIP, chia ticket giả, dùng số Done để xếp hạng cá nhân hoặc bỏ tất cả planning**.

## 2. Kanban giải quyết vấn đề gì?

### 2.1. Đầu vào không đến thành những lô gọn gàng

Một nhóm xây sản phẩm có thể chọn trước một tập công việc cho vài tuần. Ngược lại, nhóm vận hành một dịch vụ đang chạy phải liên tục tiếp nhận:

- Sự cố production và lỗi người dùng gặp.
- Thay đổi bảo mật hoặc tuân thủ cần xử lý đúng hạn.
- Yêu cầu sửa/điều chỉnh tính năng đã phát hành.
- Việc bảo trì CI, database và dependency.
- Cải tiến nhỏ từ feedback người dùng.
- Nhu cầu phát triển tính năng mới có thể được làm rõ dần.

Không thể đoán chính xác **thứ tự và thời điểm xuất hiện tất cả yêu cầu**. Nếu mỗi việc mới đều được mở ngay, WIP tăng, việc đang làm bị ngắt quãng, hạng mục cũ già đi và thời gian hoàn tất khó dự báo.

**Kanban giúp đội điều tiết quá trình nhận việc và hoàn tất việc**, không hứa rằng mọi yêu cầu sẽ được xử lý ngay khi xuất hiện.

### 2.2. “Dòng liên tục” không có nghĩa làm việc không có điểm dừng

Ở đây, *continuous flow* nghĩa là hạng mục có thể được **kéo vào hệ thống và hoàn tất theo chính sách khi có năng lực**, thay vì chỉ bắt đầu/đóng việc vào một mốc timebox cố định. Đội vẫn có thể:

- Đặt Product Goal hoặc outcome theo quý.
- Họp replenishment định kỳ.
- Dùng mục tiêu cho một giai đoạn cải tiến.
- Tổ chức release window theo chính sách.
- Họp retrospective và trao đổi với stakeholder.
- Dừng nhận việc mới khi hệ thống quá tải.

**Liên tục là cách điều tiết luồng**, không phải “không bao giờ lập kế hoạch” hoặc “phải online 24/7”.

### 2.3. Kanban không tự động làm tăng tốc

Một bảng Kanban có thể phát hiện Review đang tắc, nhưng **không tự sinh reviewer có chuyên môn**. Một WIP limit có thể ngăn mở thêm việc, nhưng **không tự sửa lỗi bảo mật hoặc pipeline CI**. Một SLE có thể giúp trao đổi kỳ vọng, nhưng **không bảo đảm item bất kỳ hoàn tất trước deadline**.

Lợi ích xuất hiện khi đội dùng tín hiệu để thay đổi **chính sách, phân bổ sự hỗ trợ, cấu trúc công việc và kỹ thuật**.

## 3. Các điều kiện thường làm Kanban đáng cân nhắc

| Dấu hiệu quan sát | Tại sao Kanban có thể hữu ích | Câu hỏi cần xác minh |
| --- | --- | --- |
| Công việc phát sinh hằng ngày, không thể chọn hết vào đầu kỳ | Hệ thống kéo có thể nhận việc khi có năng lực | Có thật sự cần xử lý ngay hay chỉ thiếu chính sách intake? |
| Nhiều yêu cầu nhỏ, thời gian xử lý biến động | Đo phân phối cycle time và SLE giúp trao đổi kỳ vọng | Các work item đã được chia tương đối nhất quán chưa? |
| Nhiều việc bị chặn giữa code, review, test, duyệt | Trực quan hóa hàng chờ và giới hạn WIP | Điểm nghẽn thuộc năng lực hay chính sách? |
| Nhóm duy trì một dịch vụ lâu dài | Có thể quản lý hỗn hợp feature, bug, support và vận hành | Ranh giới dịch vụ và quyền ưu tiên có rõ không? |
| Yêu cầu khẩn đến xen vào công việc kế hoạch | Chính sách class of service và ngoại lệ WIP làm tác động minh bạch | Thế nào thực sự là incident/expedite? |
| Tính năng nhỏ có thể Done độc lập | Hạng mục được giao khi hoàn tất, không cần gom cuối Sprint | DoD và kiểm chứng đầu-cuối đã đáng tin chưa? |
| Cần dự báo thời gian phản hồi cho khách hàng | SLE từ phân phối lịch sử giúp quản lý kỳ vọng | Dữ liệu đủ đại diện cho loại yêu cầu này chưa? |
| Quy trình nhiều bước và phụ thuộc vào shared service | Có thể đo blocked time, work item age và luồng thực | Có cách giảm chuyển giao thay vì chỉ theo dõi không? |

**Các dấu hiệu này chỉ gợi ý phù hợp, không phải danh sách điều kiện bắt buộc.** Một nhóm không có incident vẫn có thể chọn Kanban. Một nhóm gặp incident thường xuyên cũng có thể dùng Scrum cùng các kỹ thuật quản lý flow, nếu Scrum Team giữ được mục tiêu và quy tắc của Scrum.

## 4. Khi nào Kanban chưa phải thay đổi quan trọng nhất?

### 4.1. Khi không biết đang tạo giá trị cho ai

Nếu Product Owner chưa làm rõ người dùng mục tiêu và backlog gồm những yêu cầu mâu thuẫn, đổi từ Sprint board sang Kanban board **không xác định được mục tiêu sản phẩm**. Cần làm rõ:

- Vấn đề người dùng.
- Product Goal hoặc outcome mong muốn.
- Ai có quyền sắp thứ tự.
- Những điều kiện an toàn và chất lượng.
- Cách kiểm chứng giải pháp.

Kanban giúp **đưa công việc qua hệ thống tốt hơn**, nhưng không tự bảo đảm đội đã chọn đúng việc.

### 4.2. Khi đội không có năng lực hoàn tất một lát cắt

Nếu mọi user story phải chờ lần lượt các nhóm UI, backend, database và QA, vấn đề có thể là **tổ chức theo component** và thiếu kỹ năng cross-functional. Bảng Kanban minh bạch điểm chờ; cải tiến thật có thể đòi thay đổi cách hình thành team, contract API, test và khả năng cộng tác.

### 4.3. Khi chất lượng phần mềm quá yếu

Nếu `Done` chỉ có nghĩa “code complete”, không có CI, test bảo mật hay xác nhận hợp đồng, throughput cao hơn có thể đưa lỗi ra người dùng nhanh hơn. Cần có tiêu chuẩn chất lượng và kiểm chứng **trước khi tối ưu tốc độ hoàn tất**.

### 4.4. Khi một deadline thực sự cần lập kế hoạch theo mốc

Một chương trình có ngày thi chứng chỉ, migration cuối kỳ hoặc nghĩa vụ pháp lý có thể cần **kế hoạch mốc, quản lý rủi ro, phân kỳ phát hành và phối hợp liên tổ chức**. Kanban vẫn có thể dùng để quản lý flow bên trong, nhưng không thay toàn bộ governance, hợp đồng và các quyết định liên quan.

### 4.5. Khi vấn đề chỉ là một blocker có thể giải quyết trực tiếp

Hai Developers chờ quyền truy cập một môi trường do chưa rõ người phê duyệt. Có thể chỉ cần **đổi quyền phối hợp, runbook và reviewer dự phòng**. Không nên dựng một hệ thống Kanban phức tạp với nhiều vai trò/sự kiện mới cho một nút nghẽn nhỏ.

## 5. So sánh Kanban, Scrum và các thực hành XP

### 5.1. Bảng so sánh theo vấn đề cần giải quyết

| Khía cạnh | Kanban | Scrum | XP |
| --- | --- | --- | --- |
| **Trọng tâm** | Quản lý và cải tiến dòng công việc | Khung làm việc kiểm tra–thích ứng để giải quyết vấn đề phức tạp và tạo giá trị | Kỹ thuật và cộng tác nhằm phát triển phần mềm chất lượng, thích ứng |
| **Nhịp công việc** | Kéo việc và hoàn tất theo năng lực, có feedback cadences phù hợp | Sprint có timebox tối đa một tháng | Vòng phản hồi kỹ thuật ngắn, tích hợp/giao phần mềm thường xuyên |
| **Vai trò** | Kanban Guide không áp đặt bộ vai trò như Scrum | Product Owner, Scrum Master, Developers | Có thực hành và vai trò trong các cách mô tả XP; không thay quyền tổ chức tự động |
| **Backlog/nguồn vào** | Hàng chờ lựa chọn và replenishment theo chính sách | Product Backlog, Sprint Backlog | Câu chuyện/ưu tiên khách hàng trong bối cảnh XP |
| **Giới hạn công việc** | Kiểm soát WIP là cơ chế trung tâm | Scrum không bắt buộc WIP limit cố định, nhưng team có thể áp dụng | Có thể kết hợp small batches và giới hạn việc |
| **Các phép đo flow** | WIP, throughput, work item age, cycle time | Có thể dùng flow metrics; Scrum Guide không bắt buộc bộ này | Có thể dùng flow metrics để đánh giá cải tiến kỹ thuật |
| **Chất lượng** | Phải có chính sách Finish và chất lượng phù hợp | Increment đáp ứng Definition of Done | TDD, CI, refactoring, pairing và các thực hành chất lượng khác |
| **Ưu điểm nổi bật** | Minh bạch hàng chờ, giảm WIP và hỗ trợ dự báo luồng | Sprint Goal, Product Goal, sự kiện kiểm tra sản phẩm | Khả năng sửa mã an toàn và nhận phản hồi kỹ thuật sớm |
| **Giới hạn nếu dùng riêng** | Không tự chỉ ra việc nào có giá trị nhất hoặc kiến trúc đúng | Timebox không tự loại bỏ blocker, WIP cao hoặc test yếu | Kỹ thuật tốt không tự làm rõ portfolio và thứ tự kinh doanh |

**Không có phép so sánh “Scrum là lập kế hoạch, Kanban là không lập kế hoạch”.** Cả hai đều cần lựa chọn công việc, minh bạch và phản hồi; chúng khác ở cấu trúc làm việc và cam kết chính thức.

### 5.2. Không chọn chỉ vì “Scrum bị interrupt”

Một Scrum Team có thể:

- Đưa rủi ro và khả năng công việc phát sinh vào Sprint Planning.
- Giảm phạm vi Sprint Backlog và giữ Sprint Goal rõ.
- Dùng WIP limit và quản lý aging work.
- Tách đường incident phù hợp với quyền và chất lượng.
- Trao đổi điều chỉnh Sprint Backlog khi điều kiện thay đổi.

Nếu đội vẫn thấy **Sprint Goal liên tục mất ý nghĩa** vì dòng nhu cầu không thể lập kế hoạch hợp lý theo timebox, việc cân nhắc Kanban hoặc thay đổi cấu trúc hỗ trợ/vận hành là chính đáng.

### 5.3. Scrum kết hợp Kanban

Một đội có thể **giữ đủ Scrum** và sử dụng Kanban để cải thiện cách công việc trôi trong Sprint:

- Sprint Goal vẫn là commitment của Sprint Backlog.
- Các sự kiện Scrum vẫn giữ mục đích.
- Product Owner vẫn chịu trách nhiệm về Product Backlog.
- Definition of Done vẫn áp dụng cho Increment.
- Developers dùng pull/WIP policies và flow metrics để giảm việc dở dang.

Đây không phải “Scrum phiên bản đã bỏ những thứ bất tiện”. Khi tuyên bố dùng Scrum, cần giữ các accountability, events, artifacts và commitments chính thức của Scrum.

### 5.4. Khi một đội chia hai dòng công việc

Một đội sản phẩm có thể duy trì Sprint cho các thay đổi sản phẩm lớn, trong khi một nhóm dịch vụ hỗ trợ sử dụng Kanban cho yêu cầu vận hành. Cũng có thể cùng một nhóm dùng flow policies để xử lý mọi việc. Điều cần làm rõ là:

- Một người có bị **giao đầy năng lực ở cả hai cơ chế** không?
- Incident có thực sự cần preemption?
- Ai quyết định thứ tự giữa product features và vận hành?
- Công việc ngoài kế hoạch được ghi vào đâu?
- Có giữ được chất lượng và mức phục vụ theo rủi ro không?

Đừng che sự xung đột năng lực bằng hai board không liên hệ.

## 6. Kanban là chiến lược thay đổi dựa trên hệ thống đang có

### 6.1. Bắt đầu từ công việc thật

Một ý tưởng quan trọng trong Kanban Method là **bắt đầu với cách làm hiện tại**, nhìn nó thật rõ rồi tiến hóa theo những thay đổi có chủ đích. Điều này không có nghĩa mọi quy trình hiện tại đều tốt; nó giảm rủi ro áp một mẫu lý tưởng không phù hợp.

Một bước khám phá có thể hỏi:

1. Công việc đi vào từ đâu?
2. Ai có quyền quyết định việc nào được nhận?
3. Khi nào team đã bắt đầu xử lý?
4. Những bước thực sự cần thiết để Done?
5. Ai/nguyên nhân nào thường khiến việc phải chờ?
6. Có loại việc nào cần chính sách khác?
7. Khi nào người yêu cầu thực sự nhận kết quả?
8. Cách chất lượng và rủi ro được kiểm chứng?

### 6.2. Phân biệt ba lớp

- **Phương pháp/chiến lược Kanban:** quản lý dòng giá trị bằng minh bạch workflow, kiểm soát WIP, quản lý các hạng mục đang chạy và cải tiến.
- **Kanban board:** cách trực quan hóa trạng thái và chính sách, trên công cụ số hoặc bảng vật lý.
- **Đội/ngữ cảnh:** những người, trách nhiệm, sản phẩm và ràng buộc đang sử dụng hệ thống.

Một bảng kéo thả **không tự chứng minh** đã có pull system, WIP control hoặc phản hồi.

### 6.3. Thay đổi tiến hóa không phải thỏa hiệp vĩnh viễn

Ví dụ board cho thấy các hạng mục luôn tắc ở QA. Đội có thể bắt đầu bằng giới hạn WIP, pairing viết test và tham gia sớm vào refinement. Sau vài tuần, nếu bottleneck do cấu trúc team tách biệt, đội cần thảo luận **thay đổi tổ chức sâu hơn**.

Kanban không buộc đội giữ mọi vai trò cũ mãi mãi; nó giúp **dựa trên bằng chứng để đổi hệ thống**.

## 7. Thiết lập Definition of Workflow (DoW)

### 7.1. DoW trả lời câu hỏi về chính hệ thống

Trong *The Kanban Guide*, **Definition of Workflow** mô tả cách công việc trôi trong hệ thống Kanban. Cần làm rõ ít nhất:

- **Work items:** những gì được coi là công việc.
- **Start:** điểm mà một item được coi là đã bắt đầu.
- **Finish:** điểm mà một item được coi là hoàn tất.
- **Các trạng thái:** các bước công việc chuyển qua giữa Start và Finish.
- **Cách kiểm soát WIP:** giới hạn hoặc cơ chế chủ động kiểm soát lượng việc đang mở.
- **Các chính sách rõ:** quy tắc work item chuyển giữa trạng thái.
- **Service Level Expectation (SLE):** kỳ vọng thời gian hoàn tất theo dữ liệu hoặc giả định minh bạch.

**Không có một DoW chuẩn duy nhất cho mọi đội.** Trạng thái `Review` có thể hợp lý với đội phát triển; đội hỗ trợ có thể có `Investigating`, `Waiting on Vendor` hoặc các đường phù hợp với dịch vụ.

### 7.2. Ví dụ DoW cho nhóm nền tảng học

| Thành phần | Ví dụ quy tắc |
| --- | --- |
| **Phạm vi item** | PBI, bug, security fix, support improvement được chấp nhận vào một dịch vụ |
| **Start** | Khi item được kéo từ `Ready` sang `In Progress` |
| **Finish** | Khi kết quả đáp ứng chính sách chất lượng/DoD liên quan và được đánh dấu `Done` |
| **Trạng thái** | `Ready → In Progress → Review → Verification → Done` |
| **WIP control** | Giới hạn In Progress = 3; Review = 2; tổng vùng Start–Finish = 5 (thử nghiệm) |
| **Pull criteria** | Có năng lực trống; item rõ phạm vi, người nhận/khả năng hỗ trợ và rủi ro |
| **Blocked policy** | Item đã Start vẫn được tính WIP; ghi lý do, tác động và bước gỡ blocker |
| **Expedite policy** | Chỉ một trường hợp đủ tiêu chí khẩn có quyền vượt giới hạn theo thẩm quyền công bố |
| **Finish policy** | Không đánh dấu Done khi thiếu kiểm tra bắt buộc; link bằng chứng vào ticket |
| **SLE** | Thử nghiệm kỳ vọng 85% item Standard hoàn tất ≤ 8 ngày lịch, sẽ hiệu chỉnh bằng lịch sử |
| **Feedback** | Kiểm tra aging WIP hằng ngày làm việc; replenishment và service review theo lịch phù hợp |

Các giá trị 3, 2, 5 và 8 ngày là **con số giả định để thực hành**, không phải mức WIP/SLE phổ quát. Cần xem tổng giới hạn và giới hạn cột có mâu thuẫn vận hành hay không; ví dụ này chủ động giới hạn **cả cột lẫn toàn hệ thống**.

### 7.3. DoW khác Definition of Done

- **DoW** mô tả *dòng công việc* và điều kiện di chuyển trên board.
- **DoD** mô tả *tiêu chuẩn chất lượng cần đạt* đối với Increment trong Scrum, hoặc tiêu chuẩn tương ứng khi đội dùng cách làm khác.

Nếu một đội dùng Scrum kết hợp Kanban, **Finish của DoW không được dùng để lách DoD**. Có thể có release queue riêng sau khi Increment đã Done; ranh giới phải rõ để không trộn cycle time phát triển với thời gian chờ phát hành.

### 7.4. DoW phải có phiên bản và người hiểu nó

Khi đổi Start từ `In Progress` sang `Ready`, cycle time sẽ tăng dù tốc độ thực hiện không đổi vì ranh giới đã mở rộng. Do đó:

- Ghi ngày hiệu lực chính sách.
- Giữ giải thích cho báo cáo trước–sau.
- Làm rõ ngoại lệ như cancel/reopen/blocked.
- Onboard thành viên mới bằng workflow thật, không bắt họ suy từ màu cột.
- Xem lại DoW khi loại công việc hoặc cấu trúc nhóm thay đổi.

## 8. Thiết kế bảng Kanban để nhìn đúng dòng

### 8.1. Board tối thiểu

```text
Options       Ready       In Progress       Review        Verify       Done
  nhiều       có giới hạn    [WIP <= 3]       [WIP <= 2]    [WIP <= 2]
                           |<--------- vùng từ Start đến Finish -------->|
                       tổng WIP toàn vùng: ví dụ <= 5
```

Đây là sơ đồ minh họa; ký hiệu `<=` diễn đạt giới hạn, không áp đặt cách tổ chức chính thức. Trong hệ thống thật, các trạng thái và giới hạn cần phản ánh **nơi công việc thật sự chờ**, không sao chép một template đẹp.

### 8.2. Không cần một cột cho mọi bước vi mô

Nếu board có 18 cột cho những thao tác kéo dài vài phút, người làm có thể mất thời gian quản lý ticket hơn làm sản phẩm. Ngược lại, ba cột chung chung có thể che điểm nghẽn Review kéo dài cả tuần.

**Nguyên tắc:** tạo cột hoặc chính sách riêng khi nó giúp một quyết định, làm lộ hàng chờ hoặc rõ trách nhiệm.

### 8.3. Đưa blocked item lên bề mặt

Một item bị chặn nên hiển thị:

- Lý do khách quan: chờ test environment, review, quyền hoặc API.
- Thời điểm bắt đầu bị chặn.
- Người/bộ phận có thể giúp.
- Bước tiếp theo và mốc xem lại.
- Tác động tới outcome hoặc deadline.

**Blocked vẫn thuộc WIP** nếu đã Start mà chưa Finish. Không chuyển về Backlog hoặc ẩn khỏi dashboard chỉ để báo WIP thấp.

### 8.4. Swimlane và nhãn

Có thể tách hiển thị:

- Standard work.
- Production incident thật.
- Fixed-date item.
- Security/compliance cần kiểm chứng.

Nhưng không cần tạo một hàng riêng cho từng stakeholder hay từng Developer. Swimlane có ích nếu **chính sách và cách quản lý dòng thực sự khác**.

### 8.5. Work item phải gắn với giá trị hoặc rủi ro

Một thẻ nên có đủ bối cảnh:

```text
ID: LP-214
Loại: Bug / Standard
Mục đích: học viên thấy đúng bài đang dở
Tác động: lỗi ở khóa có bài đã hoàn thành
Điều kiện chấp nhận:
  - cùng tài khoản, khóa hợp lệ: đúng bài tiếp theo
  - khóa hết quyền: không thể mở nội dung
  - dữ liệu chưa đồng bộ: thể hiện giới hạn trung thực
Rủi ro: phân quyền và độ mới dữ liệu
Blocker: cần contract với LMS (nếu có)
Bằng chứng Done: PR, tests và kiểm chứng phù hợp
Liên kết: tài liệu, phản hồi người dùng và incident liên quan
```

Không biến mỗi cuộc chat, mỗi commit hoặc mỗi thao tác đặt tên biến thành một “PBI giá trị” chỉ để tăng throughput.

## 9. Pull system: kéo khi có năng lực, không đẩy để ai cũng bận

### 9.1. Push và Pull

Trong hệ thống **push**, một người có thể giao thêm một item cho Developer ngay khi có yêu cầu, bất kể người đó đang làm ba việc khác. Những người ở bước sau có thể nhận một lô lớn đúng lúc đã quá tải.

Trong hệ thống **pull**, bước tiếp theo nhận việc **khi có khả năng xử lý theo chính sách**, với thông tin đủ rõ và giới hạn WIP phù hợp.

Ví dụ:

> “Review có WIP limit 2 và đang đủ hai PR. Developer chưa đẩy PR thứ ba vào hàng chờ không được quản lý; nhóm cùng nhìn trạng thái, xử lý review đang mở hoặc quyết định ngoại lệ có lý do.”

Trong thực tế PR có thể tồn tại trên Git, nhưng board phải thể hiện **sự thật là có công việc đang chờ**. Không lợi dụng pull policy để làm biến mất hàng chờ ở công cụ.

### 9.2. “Kéo việc” không có nghĩa tự chọn việc dễ nhất

Nếu mọi người chỉ kéo ticket dễ để nhanh Done, việc khó hoặc giá trị cao có thể già đi mãi. Cần chính sách lựa chọn có xem:

- Giá trị người dùng.
- Rủi ro và thời hạn.
- Age của công việc đang mở.
- Phụ thuộc và năng lực.
- Cost of Delay khi có cơ sở.
- Sự cố hoặc nghĩa vụ cần ưu tiên.

**Pull là quyền và trách nhiệm lấy công việc theo một chính sách minh bạch**, không phải tự do chọn bất kỳ ticket dễ nhất.

### 9.3. Có thể “không kéo” mà vẫn tạo giá trị

Khi WIP đã đạt giới hạn, một thành viên chưa có nhiệm vụ mới có thể:

- Giúp viết hoặc sửa test cho item gần Done.
- Pairing điều tra blocker.
- Review PR đang chờ.
- Cải thiện dữ liệu thử.
- Chuẩn bị refinement có mục tiêu.
- Phối hợp giải quyết một phụ thuộc.
- Gỡ lỗi CI cản trở toàn dòng.

Không nên đánh giá “người chưa mở task mới” là kém năng suất nếu họ đang giúp **toàn bộ hệ thống hoàn tất nhanh hơn và đúng chất lượng**.

## 10. Giới hạn WIP: cơ chế giảm hàng chờ và chuyển ngữ cảnh

### 10.1. WIP là gì?

**Work in Progress** là số work item đã bắt đầu nhưng chưa kết thúc trong ranh giới đã chọn, tại một thời điểm quan sát. Một item blocked vẫn là WIP nếu chưa Done.

**WIP limit** là quy tắc chủ động điều tiết số item được mở trong một trạng thái, một nhóm trạng thái hoặc toàn hệ thống.

### 10.2. Vì sao WIP cao có thể làm hệ thống chậm?

Khi có quá nhiều việc song song:

- Reviewer phải chia thời gian giữa nhiều PR.
- Developer đổi ngữ cảnh liên tục.
- Test environment bị tranh tài nguyên.
- Những câu hỏi nghiệp vụ chưa chốt tích tụ.
- Công việc cũ bị quên; đến lúc quay lại phải đọc lại bối cảnh.
- Một lỗi tích hợp bị phát hiện khi nhiều thay đổi đã được xếp lên trên nó.

Không có một con số WIP “tốt cho mọi đội”. Giới hạn phù hợp phụ thuộc loại công việc, kỹ năng, mức cộng tác và khả năng xử lý các bước.

### 10.3. Bắt đầu đặt WIP limit thế nào?

Một thử nghiệm khả thi:

1. Quan sát WIP thực và hàng chờ hiện tại.
2. Chọn một mức giới hạn đủ để **lộ nút nghẽn** nhưng vẫn xử lý được các trường hợp cần song song.
3. Thống nhất khi đầy WIP thì **ưu tiên gỡ việc đang mở**.
4. Đặt chính sách ngoại lệ khẩn có điều kiện.
5. Xem tác động lên age, cycle time, throughput và chất lượng qua vài tuần.
6. Điều chỉnh bằng dữ liệu, không coi giới hạn đầu tiên là mệnh lệnh vĩnh viễn.

**Không mặc định WIP limit = số Developers.** Một hạng mục có thể cần nhiều người, trong khi một Developer có thể hỗ trợ hoàn tất item của người khác.

### 10.4. Một ví dụ về quá tải cục bộ

Bảng có:

| Trạng thái | WIP hiện tại | Limit |
| --- | ---: | ---: |
| In Progress | 2 | 3 |
| Review | 3 | 2 |
| Verification | 1 | 2 |
| **Tổng** | **6** | **5** (limit toàn hệ thống) |

Nhóm đang vượt **Review limit và system WIP limit**. Nếu một Developer muốn bắt đầu task mới, chính sách nên khiến nhóm **xử lý công việc đang kẹt**, không tự động mở thêm.

Nhưng đừng trừng phạt người báo số vượt giới hạn. **Việc thấy vượt limit giúp phát hiện chính sách chưa phù hợp hoặc trở ngại thật.**

### 10.5. WIP thấp không tự chứng minh dòng tốt

Giả sử WIP giảm từ 10 xuống 2 vì nhóm chuyển tám item bị chặn về `Ready`. Số WIP có vẻ tốt nhưng người dùng vẫn chờ và work item age bị làm sai. Đó là **tối ưu báo cáo, không phải cải tiến**.

Nếu WIP giảm thật nhưng throughput cũng giảm mạnh vì không có kỹ năng review, cần xử lý bottleneck; giảm WIP không phải phép màu.

## 11. Replenishment: quyết định công việc nào được nhận tiếp

### 11.1. Không nhầm `Options` với WIP

Một hệ thống Kanban có thể có tập các lựa chọn lớn, nhưng chỉ một phần **đã được cam kết xử lý hoặc bắt đầu**. Đội cần làm rõ điểm commitment nếu dùng, để không hứa xử lý mọi yêu cầu đang có.

Ví dụ:

- `Options`: nhiều đề xuất, chưa được sắp để kéo ngay.
- `Ready`: các item đã rõ phạm vi, có thể chọn khi đủ năng lực.
- `In Progress`: đã Start, tính WIP.
- `Done`: đã Finish theo policy.

**Việc có hàng trăm lựa chọn không có nghĩa đội đang WIP hàng trăm item**, nhưng vẫn nên quản lý số lượng và tuổi yêu cầu tồn đọng nếu đó là vấn đề sản phẩm.

### 11.2. Replenishment hỏi những gì?

Khi có năng lực hoặc theo lịch:

1. Điều gì có giá trị/cần giảm rủi ro nhất?
2. Những item nào đã đủ hiểu để kéo?
3. Có deadline/incident thật không?
4. Có loại việc nào đang bị đói ưu tiên?
5. Có phụ thuộc phải làm rõ trước?
6. Có năng lực để hoàn tất theo DoD?
7. Những việc nào nên loại khỏi lựa chọn vì không còn giá trị?

**Một Product Owner vẫn có thể chịu trách nhiệm sắp thứ tự Product Backlog** nếu nhóm dùng Scrum; replenishment không tự động thay trách nhiệm ấy bằng cuộc bỏ phiếu của mọi người.

### 11.3. Nhịp replenishment không cần là một Sprint Planning khác tên

Có thể:

- Họp 20 phút hai lần/tuần để chọn những việc đủ Ready.
- Kéo liên tục khi có ô trống theo thứ tự rõ.
- Có buổi xem nhu cầu cùng stakeholder mỗi tuần.
- Duy trì mục tiêu sản phẩm qua một giai đoạn dài hơn.

Lịch nào phù hợp tùy **tốc độ đến, độ biến động và thời gian cần để làm rõ**, không do tên Kanban áp đặt một nhịp cố định.

## 12. Chính sách ưu tiên: bảo vệ việc quan trọng mà không làm mọi việc thành khẩn

### 12.1. Ưu tiên không chỉ là thứ tự một hàng

Khi cân nhắc, hỏi:

- Việc có giảm nguy cơ mất dữ liệu hoặc lộ quyền không?
- Người dùng nào bị ảnh hưởng, với hậu quả gì?
- Có deadline hợp đồng/tuân thủ đã xác nhận không?
- Việc đang WIP đã gần Done hay đang già bất thường?
- Có dependency làm nhiều item khác bị chặn?
- Giá trị của việc trì hoãn là gì?
- Có thể chia một lát cắt nhỏ để học trước không?

Những câu hỏi giúp **quyết định theo ngữ cảnh**, không phải chấm điểm thiếu nguồn rồi coi kết quả là sự thật.

### 12.2. Classes of Service là thực hành tùy chọn

Trong Kanban Method, một số nhóm dùng các **classes of service** như:

| Loại minh họa | Tình huống | Chính sách cần rõ |
| --- | --- | --- |
| **Standard** | Cải tiến sản phẩm thường ngày | Kéo theo thứ tự ưu tiên, dùng SLE phù hợp |
| **Expedite** | Sự cố production thực sự, rủi ro nghiêm trọng | Ai được khai báo, giới hạn WIP ngoại lệ, escalation |
| **Fixed Date** | Thay đổi phải xong trước một mốc thực có chi phí trễ rõ | Ngày, nguồn ràng buộc, cách chuẩn bị sớm |
| **Intangible** | Giảm nợ kỹ thuật, cải tiến CI có lợi dài hạn khó quy ngay tiền | Ngăn bị trì hoãn vô hạn; xét tác động tới hệ thống |

**Tên và số class không bắt buộc theo Kanban Guide**; đây là một tập lựa chọn phổ biến trong Kanban Method. Một team có thể dùng ít loại hơn hoặc phân nhóm theo rủi ro sản phẩm.

### 12.3. Khi nào được expedite?

Một chính sách minh họa:

> “Expedite dùng khi có sự cố production quan trọng hoặc nguy cơ dữ liệu/bảo mật đủ tiêu chí được phê duyệt. Người có thẩm quyền khai báo và ghi tác động. Tại một thời điểm, luồng chỉ nhận một item expedite theo chính sách thử nghiệm; team công bố những item Standard bị ảnh hưởng. Nếu sự cố vượt khả năng, kích hoạt incident response riêng.”

**Không dùng expedite cho mọi yêu cầu của một stakeholder có chức danh cao.** Nếu mọi item đều expedite thì thực chất không còn ưu tiên.

### 12.4. Fixed Date không phải “deadline tôi muốn”

Một hạng mục cần tương thích với quy định vào ngày 30 có rủi ro trễ khác với mong muốn “mình thích demo thứ Sáu”. Cần phân biệt:

- **Ngày bắt buộc:** nguồn, hậu quả và người có thẩm quyền.
- **Ngày mục tiêu:** thỏa thuận ưu tiên và độ bất định.
- **SLE:** xác suất lịch sử về thời gian hoàn tất item.
- **Kỳ vọng phản hồi:** mức dịch vụ và bối cảnh vận hành.

Không đổi nhãn Standard thành Fixed Date chỉ vì muốn vượt hàng chờ.

## 13. Chi phí chậm trễ và trách nhiệm ra quyết định

### 13.1. Cost of Delay là công cụ đặt câu hỏi

*Cost of Delay* mô tả giá trị bị mất hoặc rủi ro tăng khi trì hoãn một lựa chọn. Với một số nhu cầu, việc chậm một tuần không đáng kể; với vá lỗi quyền truy cập đang gây rò rỉ, chi phí có thể nghiêm trọng và yêu cầu phản ứng ngay.

Nhưng chi phí trễ thường **khó định lượng chính xác**. Hãy nêu giả định thay vì biến điểm số bất định thành sự thật.

### 13.2. Ví dụ hai yêu cầu

**A — Cải thiện tìm kiếm khóa học:** người học bỏ nhiều thời gian lọc khóa; dữ liệu quan sát cho thấy cơ hội cải thiện, nhưng chưa có deadline cứng.

**B — Sửa lỗi quyền truy cập tiến độ:** có bằng chứng tài khoản có thể đọc tiến độ của người khác.

Nhóm không nên xử lý B như một ticket Standard vì “A đến trước”. Cần kích hoạt phân loại rủi ro, phối hợp bảo mật và incident response nếu đủ tiêu chí. **Không dùng công thức xếp hạng để thay nghĩa vụ bảo vệ người dùng**.

### 13.3. Ai quyết định thứ tự?

Tùy tổ chức:

- Product Owner định hướng giá trị và thứ tự Product Backlog trong Scrum.
- Người trực/sự cố có quyền kích hoạt đường incident theo chính sách.
- Developers chọn cách xử lý kỹ thuật và tạo Increment đạt chất lượng.
- Chuyên gia bảo mật/dữ liệu có trách nhiệm kiểm soát rủi ro đặc thù.
- Stakeholder cung cấp ngữ cảnh và ràng buộc.

**Kanban không tự định nghĩa bộ vai trò hoặc thay cấu trúc quyền quyết định đã có**. Điều quan trọng là **chính sách ra quyết định rõ, nhất quán và có thể xem lại**.

## 14. Cadences: vẫn cần phản hồi và kế hoạch khi dùng Kanban

### 14.1. Phân biệt cadences với timebox bắt buộc

Kanban không áp đặt Sprint, nhưng đội vẫn cần các vòng:

- Xem nhu cầu và chọn việc tiếp.
- Kiểm tra dòng hiện tại, blocker, age và WIP.
- Xem mức phục vụ thực tế cho người yêu cầu.
- Xem chất lượng, release và incident.
- Xem chiến lược sản phẩm và đầu tư.
- Cải tiến chính sách/thiết kế workflow.

Những cadences được mô tả trong Kanban Method như replenishment, service delivery review, operations review và strategy review là **những thực hành có thể điều chỉnh**, không phải tất cả các cuộc họp bắt buộc phải thêm vào lịch của mọi team.

### 14.2. Một lịch tối giản minh họa

| Nhịp minh họa | Mục đích | Người cần thiết | Đầu ra |
| --- | --- | --- | --- |
| **Mỗi ngày làm việc** (10–15 phút nếu hữu ích) | Xem item già, blocker và WIP; điều chỉnh cách phối hợp | Những người xử lý dòng | Hành động gỡ điểm nghẽn, không phải báo cáo cá nhân |
| **Hai lần/tuần** | Replenishment: chọn item Ready khi có năng lực | Người quyết định ưu tiên, Developers, người liên quan | Lựa chọn rõ, ít item cam kết vượt năng lực |
| **Hằng tuần** | Service delivery review: xem cycle time/SLE và các vấn đề đang trễ | Team và stakeholder phù hợp | Điều chỉnh kỳ vọng, chính sách |
| **Mỗi hai tuần** | Product feedback: xem Increment, nhu cầu và outcome | PO, người dùng/stakeholder, team | Backlog và giả thuyết được cập nhật |
| **Hằng tháng** | Retrospective/flow improvement | Những người cùng hệ thống | Một hoặc hai thử nghiệm cải tiến |
| **Theo nhu cầu** | Incident/risk coordination | Người có quyền và chuyên môn | Bảo vệ người dùng, kiểm soát sự cố |

Lịch chỉ là ví dụ. Có nhóm nhận nhiều yêu cầu cần replenishment mỗi ngày; có nhóm ổn định chỉ cần một lần mỗi tuần. **Không sao chép lịch rồi biến công cụ giảm họp thành bảy cuộc họp mới**.

### 14.3. Daily flow review không phải báo cáo ba câu hỏi cho người quản lý

Có thể đi **từ phải sang trái trên board**, ưu tiên item gần Done:

1. Việc nào đã ở Verification và có thể hoàn tất hôm nay?
2. Review nào bị chặn và ai có thể giúp?
3. Item nào đã gần hoặc vượt SLE?
4. Có vượt WIP limit? Vì sao?
5. Có cần ngừng kéo việc mới?
6. Có rủi ro cần báo cho người yêu cầu?
7. Nếu có sự cố, ai xử lý và hoạt động khác bị ảnh hưởng thế nào?

Mục đích là quản lý **dòng hạng mục**, không kiểm tra từng người có làm việc liên tục không.

### 14.4. Họp không thay các chính sách và công cụ

Nếu board không được cập nhật, PR không có bằng chứng và mọi quyết định chỉ nói miệng, thêm daily flow review có thể không giải quyết vấn đề. Cần **thông tin đáng tin, chính sách rõ và quyền gỡ blocker**.

## 15. Các tín hiệu tối thiểu của hệ thống Kanban

### 15.1. Bốn flow metrics cốt lõi

*The Kanban Guide* nêu bốn phép đo dòng công việc:

| Chỉ số | Định nghĩa theo hệ thống đã chọn | Câu hỏi |
| --- | --- | --- |
| **Work in Progress (WIP)** | Số item đã Start và chưa Finish ở một thời điểm | Có bao nhiêu việc đang mở? |
| **Throughput** | Số item qua Finish trong một đơn vị thời gian | Trong tuần này đã hoàn tất bao nhiêu? |
| **Work Item Age** | Thời gian đã trôi qua từ Start của item **chưa Finished** tới hiện tại | Việc nào đang già và cần hỗ trợ? |
| **Cycle Time** | Thời gian từ Start tới Finish của item **đã Finished** | Một item mất bao lâu để hoàn tất? |

Không chỉ xem ba item Done gần đây mà bỏ qua một item bị chặn 30 ngày. **Age của WIP là tín hiệu đang xảy ra**, còn cycle time là mô tả của các item đã hoàn tất.

### 15.2. Đơn vị cần rõ

- WIP: **item tại một thời điểm**.
- Throughput: **item/kỳ** như item/tuần.
- Work Item Age: **giờ/ngày lịch hoặc ngày làm việc** kể từ Start.
- Cycle Time: **giờ/ngày**, theo quy tắc thời gian đã thống nhất.

Nếu đo bằng ngày làm việc, cần lịch nghỉ và cách tính nhất quán. Nếu Start/Finish được ghi tại **đầu ngày tương đối Dn** thì D3 tới D8 = **5 ngày lịch**, không cộng cả ngày biên.

### 15.3. Không dùng throughput thay outcome

Một đội tăng throughput bằng cách tách một PBI thành 15 ticket nhỏ không chứng minh người học hoàn thành khóa nhanh hơn. Cần kết hợp:

- Hành vi người dùng và outcome.
- Chất lượng Increment/DoD.
- Lỗi hồi quy, sự cố, bảo mật.
- Tính biến động các loại công việc.
- Tần suất và phạm vi release.
- Độ mới và tính hợp lệ của dữ liệu.

**Số liệu flow hỗ trợ quyết định về hệ thống làm việc, không phải thành tích sản phẩm đầy đủ.**

## 16. Bộ dữ liệu ví dụ: quan sát một dòng Kanban liên tục

Để hiểu Kanban như hệ thống thực, xét **12 work item giả định** của đội phát triển và hỗ trợ nền tảng học. Mỗi mốc `D1`, `D2`, ... là **đầu một ngày lịch tương đối**, không phải ngày thực trong năm. Khi một item Start ở đầu D3 và Finish ở đầu D8, cycle time theo quy ước là **5 ngày**.

### 16.1. Dữ liệu Start/Finish

| Item | Start | Finish | Cycle time (ngày) | Công việc minh họa |
| --- | --- | --- | ---: | --- |
| K1 | D1 | D3 | 2 | Sửa thông báo khóa hết quyền |
| K2 | D1 | D5 | 4 | Sửa trường tiến độ từ LMS |
| K3 | D2 | D6 | 4 | Sửa lỗi URL mở bài |
| K4 | D3 | D7 | 4 | Bổ sung test phân quyền |
| K5 | D4 | D9 | 5 | Cải tiến trang khóa học |
| K6 | D6 | D10 | 4 | Khắc phục batch trễ |
| K7 | D7 | D11 | 4 | Sửa lỗi lịch sử bài |
| K8 | D8 | D14 | 6 | Bổ sung trạng thái đồng bộ |
| K9 | D9 | D13 | 4 | Fix API khi không có tiến độ |
| K10 | D11 | D16 | 5 | Lát cắt Tiếp tục bài học |
| K11 | D12 | D17 | 5 | Cải thiện contract test |
| K12 | D14 | D19 | 5 | Tối ưu lỗi timeout |

Dữ liệu được tạo để luyện tập, **không phải benchmark công nghiệp** và cũng chưa có bằng chứng rằng 12 item tương đương nhau về độ lớn/rủi ro.

### 16.2. Tính cycle time trung bình, trung vị

```text
Danh sách theo thứ tự K1..K12:
2, 4, 4, 4, 5, 4, 4, 6, 4, 5, 5, 5

Tổng = 2 + 4 + 4 + 4 + 5 + 4
     + 4 + 6 + 4 + 5 + 5 + 5
     = 52 ngày-item

Trung bình = 52 / 12
           = 4,333... ngày/item

Sắp tăng:
2, 4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 6

Trung vị = (giá trị thứ 6 + thứ 7) / 2
         = (4 + 4) / 2
         = 4 ngày
```

Một item có cycle time **6 ngày** và phần lớn hoàn tất trong 4–5 ngày. Trung bình **4,33 ngày** không có nghĩa “một item mới chắc chắn Done trong 4,33 ngày”.

### 16.3. Tính WIP tại đầu D12

Theo quy ước thời điểm:

```text
WIP(t) = số item có Start <= t < Finish
         (gồm item đã Start nhưng chưa có Finish)

Tại đầu D12:
K8:  D8  <= D12 < D14 -> đang WIP
K9:  D9  <= D12 < D13 -> đang WIP
K10: D11 <= D12 < D16 -> đang WIP
K11: D12 <= D12 < D17 -> đang WIP

K7 đã Finish ở đầu D11.
K12 chỉ Start tại đầu D14.

WIP tại đầu D12 = 4 item: K8, K9, K10, K11.
```

Work item age ở **đầu D12**:

- K8: 12 − 8 = **4 ngày**.
- K9: 12 − 9 = **3 ngày**.
- K10: 12 − 11 = **1 ngày**.
- K11: 12 − 12 = **0 ngày**.

Tổng age tại một thời điểm **không phải cycle time**; age của K8 còn tiếp tục tăng cho đến khi K8 Finished.

### 16.4. Tính throughput theo ba kỳ

Chọn ba khoảng thời gian **không chồng lấn**:

- Kỳ 1: từ đầu D1 đến **trước** đầu D8.
- Kỳ 2: từ đầu D8 đến **trước** đầu D15.
- Kỳ 3: từ đầu D15 đến **trước** đầu D22.

| Kỳ | Finish thuộc khoảng | Các item | Throughput |
| --- | --- | --- | ---: |
| D1 ≤ Finish < D8 | D3, D5, D6, D7 | K1, K2, K3, K4 | **4** |
| D8 ≤ Finish < D15 | D9, D10, D11, D13, D14 | K5, K6, K7, K9, K8 | **5** |
| D15 ≤ Finish < D22 | D16, D17, D19 | K10, K11, K12 | **3** |
| **Ba kỳ** | | **12 item** | **12** |

Throughput bình quân minh họa là **12/3 = 4 item/kỳ**. Nhưng **mẫu ba kỳ quá nhỏ**, và kỳ cuối không có Start mới sau D14 trong tập dữ liệu, nên không được coi bốn item/tuần là tốc độ ổn định chắc chắn của team.

### 16.5. Điều đáng thảo luận thay vì chỉ tính số

1. K8 mất **6 ngày** vì khó kỹ thuật, chờ môi trường hay cả hai?
2. Tại D12 có **4 item WIP**, nhưng những bước nào đang quá tải?
3. Kỳ 3 throughput thấp hơn do ít item vào, do blocker hay biến động bình thường?
4. Nếu K10 rất lớn còn các item kia nhỏ, nên dự báo hỗn hợp bằng item count thế nào?
5. Có item **đã Start nhưng chưa Finish** ở thời điểm báo cáo mà tập Completed items bỏ qua không?
6. Nếu đội thay `Done` từ “merge code” sang “đạt DoD”, phép đo trước–sau còn so sánh trực tiếp được không?

Một dashboard hữu ích phải giúp **đặt câu hỏi đúng**, không chỉ tính ra các con số.

## 17. Work Item Age và Service Level Expectation

### 17.1. Thời gian đã trôi qua là tín hiệu sớm

**Cycle Time** chỉ hoàn chỉnh khi item Finished. **Work Item Age** hiện diện khi item **chưa hoàn tất**. Nếu một PBI bị chặn ở Review ngày thứ 13, chỉ xem cycle time của item Done có thể che vấn đề đó.

Một buổi flow review nên kiểm tra:

- Item nào đã mở lâu nhất?
- Item nào gần hoặc vượt SLE?
- Có blocker nào chưa được ai tiếp nhận?
- Có thể **swarm/pair/review** để hoàn tất hơn là mở thêm việc không?
- Nếu deadline có nguy cơ trễ, đã chủ động báo người yêu cầu chưa?

### 17.2. SLE là kỳ vọng xác suất

**Service Level Expectation (SLE)** thường được diễn đạt bằng một mức thời gian và phần trăm:

> “Dựa trên dữ liệu phù hợp, chúng tôi kỳ vọng **85%** những item Standard thuộc loại này hoàn tất trong **không quá 8 ngày lịch** kể từ Start.”

Các con số là **ví dụ**, không phải SLE bắt buộc theo Kanban. Một SLE nên:

- Nêu **loại item/phạm vi hệ thống**.
- Nêu **Start và Finish**.
- Nêu **đơn vị thời gian**.
- Nêu **mức phần trăm** và nguồn lịch sử/giả định.
- Được xem lại khi workflow hoặc mix công việc thay đổi.

**SLE không đồng nghĩa SLA** và không phải lời hứa 100% mọi item sẽ xong đúng thời hạn.

### 17.3. SLE minh họa từ dữ liệu 12 item

Với 12 cycle time đã sắp:

```text
2, 4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 6

Nearest-rank percentile 85:
ceil(0,85 × 12) = ceil(10,2) = vị trí 11
Giá trị thứ 11 = 5 ngày

11 / 12 item = khoảng 91,7% hoàn tất <= 5 ngày.
```

Có thể nói **“Trong mẫu 12 item, khoảng 91,7% hoàn tất không quá năm ngày”**. Nhưng đây chưa phải bằng chứng mạnh để chốt SLE bên ngoài, vì:

- Mẫu rất nhỏ.
- Item trộn nhiều loại.
- Khả năng rủi ro dài hạn chưa xuất hiện.
- Cách chia ticket có thể thay đổi.
- Dữ liệu không phản ánh đầy đủ item bị hủy/reopened.
- Kỳ quan sát có thể không đại diện.

Nếu nhóm vẫn muốn bắt đầu, có thể lập **SLE tạm thời có ghi giả định**, thu thêm dữ liệu trước khi cam kết với stakeholder.

### 17.4. Quản lý item vượt SLE

Item age **10 ngày** trong hệ thống có SLE tạm “85% ≤ 8 ngày” không có nghĩa Developer “kém năng suất”; nghĩa là item đang **cần hỗ trợ và cập nhật kỳ vọng**. Đội cần điều tra:

- Đã bị chặn bởi ai/cái gì?
- Có thể đổi cách thực hiện mà vẫn đạt chất lượng không?
- Có điều kiện để chia một lát cắt end-to-end thật không?
- Cần nâng mức ưu tiên vì tác động rủi ro mới không?
- Có cần báo lại dự báo và giải thích cho người dùng không?

**Không bỏ test, hạ DoD hoặc đổi Start date** chỉ để item quay về trong SLE.

## 18. Cumulative Flow Diagram (CFD) và hàng chờ

### 18.1. CFD thể hiện điều gì?

**Cumulative Flow Diagram** thường trực quan hóa số item tích lũy qua các trạng thái theo thời gian. Nó có thể giúp nhận ra:

- Đường Started tăng nhanh hơn đường Finished → **WIP tích tụ**.
- Một dải trạng thái `Review` dày lên → khả năng hàng chờ review tăng.
- Đường Finished phẳng → item không đi qua Finish trong một khoảng.
- Dải giữa Started và Finished ổn định hơn → WIP có thể đang ổn định.
- Độ dốc hoàn tất thay đổi → throughput có thể biến động.

### 18.2. Sơ đồ khái niệm

```text
Số item tích lũy
^
|                                Started   /------
|                           _____/        /
|                      ____/    WIP      /
|                 ____/                 /
|            ____/     Finished   _____/
|       ____/                  __/
|  ____/                    __/
|_/_______________________/___________________> Thời gian

Khoảng giữa Started và Finished là WIP theo ranh giới đo.
Một CFD thực tế thường dùng các dải trạng thái xếp chồng.
```

Sơ đồ này chỉ minh họa. **Khi diễn giải CFD, phải kiểm tra cách công cụ đếm item và chuyển trạng thái**.

### 18.3. CFD không tự chỉ ra nguyên nhân

Một dải Verification tăng có thể do:

- Thiếu kỹ năng/test environment.
- Nhiều item lớn cùng tới bước kiểm chứng.
- Dữ liệu test không đúng.
- Tiêu chuẩn chất lượng thay đổi.
- Tool cập nhật trạng thái trễ.
- Phụ thuộc team ngoài.

Cần **xem các item thực và trao đổi với người đang xử lý** trước khi kết luận “QA là nút cổ chai” hoặc “Developer quá nhanh”.

### 18.4. Đọc CFD cùng aging WIP

CFD nhìn hệ thống tổng thể. Aging WIP giúp đội **nhìn từng item chưa Done**. Hai góc nhìn bổ trợ nhau: một CFD ổn định vẫn có thể che một item ngoại lệ đang kẹt quá lâu; một item kẹt không tự nói cả hệ thống đang không ổn định.

## 19. Little’s Law: hiểu quan hệ trung bình, không dùng làm deadline

### 19.1. Công thức

Trong một hệ thống dòng công việc có ranh giới và điều kiện ổn định phù hợp, **Little’s Law** liên hệ:

```text
Average WIP = Average throughput rate × Average cycle time

Average cycle time = Average WIP / Average throughput rate
```

Ví dụ một hệ thống **giả định tương đối ổn định** có:

- WIP bình quân: **8 item**.
- Throughput bình quân: **4 item/tuần**.

Cycle time bình quân tương ứng:

```text
8 item / (4 item/tuần) = 2 tuần
```

Đây là quan hệ **về trung bình của hệ thống**, không hứa một PBI cụ thể sẽ Finished sau đúng hai tuần.

### 19.2. Kiểm tra điều kiện trước khi áp dụng

- WIP, throughput và cycle time đo **cùng ranh giới**.
- Dòng không tăng backlog WIP không giới hạn trong kỳ quan sát.
- Item vào/ra/được hủy có chính sách minh bạch.
- Khoảng quan sát đủ đại diện.
- Cách chia item và các loại công việc không đổi đột ngột.
- Không lấy một snapshot WIP duy nhất làm WIP bình quân dài hạn.
- Đơn vị được đổi nhất quán, ví dụ ngày hay tuần.
- Đầu vào và hoàn tất không bị chỉnh số để đạt KPI.

Little’s Law là quan hệ mạnh khi dùng đúng, nhưng **không phải công cụ thay việc điều tra rủi ro của từng item**.

### 19.3. Giảm WIP có thể giảm cycle time — có điều kiện

Giả sử throughput thực sự giữ mức 4 item/tuần, WIP bình quân giảm từ 8 xuống 6 thì cycle time bình quân theo quan hệ trên giảm từ **2 tuần xuống 1,5 tuần**. Tuy nhiên:

- Nếu giới hạn làm throughput giảm, kết quả có thể khác.
- Nếu item khó hơn trước, cycle time biến động.
- Nếu có bottleneck mới, quy luật bình quân không cho biết cách sửa.
- Nếu đội chỉ giấu blocked items, dữ liệu không còn đáng tin.

Vì vậy, hãy **thử nghiệm WIP control và quan sát cả throughput, age và chất lượng**, không quản lý dựa trên một phép chia duy nhất.

## 20. Dự báo bằng throughput: khi nào đáng dùng?

### 20.1. Dự báo không phải lời hứa cứng

Một nhóm có throughput theo tuần (giả định):

| Tuần | Item Finished |
| --- | ---: |
| 1 | 4 |
| 2 | 6 |
| 3 | 5 |
| 4 | 3 |
| 5 | 6 |
| 6 | 5 |
| 7 | 4 |
| 8 | 7 |
| **Tổng** | **40** |

Trung bình: **40 / 8 = 5 item/tuần**. Mẫu lịch sử có các tuần **3–7 item**.

Nếu còn **20 item tương tự**, một ước tính tuyến tính thô là:

```text
20 item / 5 item/tuần = 4 tuần
```

Không được kết luận “chắc chắn bốn tuần”, vì nhu cầu thay đổi, item lớn nhỏ khác nhau, những công việc chưa thấy có thể xuất hiện và throughput biến động.

### 20.2. Dự báo có điều kiện

Một cách trao đổi tốt hơn:

> “Với cách chia item và mix công việc gần giống tám tuần qua, tổng 20 item còn lại có thể cần khoảng vài tuần; phép chia trung bình gợi ý bốn tuần, nhưng cần xem độ biến động và những item đang bị chặn. Chúng ta sẽ cập nhật khi có dữ liệu mới.”

Không nên tự gán mức **85% chắc chắn** cho một khoảng thời gian chỉ được chọn cảm tính.

### 20.3. Mô phỏng Monte Carlo

Với dữ liệu lịch sử đủ phù hợp, đội có thể:

1. Lấy mẫu throughput theo tuần từ lịch sử.
2. Cộng số item Finished trong mỗi kịch bản.
3. Xem cần bao nhiêu tuần để đạt số item mục tiêu.
4. Lặp nhiều kịch bản để có phân phối thời gian.
5. Nêu các phân vị cùng giả định về đầu vào/cách chia work item.

Mô phỏng có thể hữu ích khi lượng công việc đủ lớn và dòng tương đối ổn định. Tuy nhiên **mô phỏng trên lịch sử không còn đại diện sẽ cho kết quả sai dù chạy hàng triệu vòng**.

### 20.4. Nhớ phân biệt forecast Done và forecast Release

Nếu một work item chỉ Finished khi Increment đạt DoD, nhưng doanh nghiệp phát hành theo cửa sổ tháng, dự báo 20 item Done **không phải** dự báo 20 item đã Released cho tất cả học viên.

Cần xem:

- Release queue.
- Deployment và approval cadence.
- Feature flags/rollout.
- Nghĩa vụ tuân thủ.
- Tương thích dữ liệu.
- Outcome theo thời gian sử dụng thực tế.

## 21. Quản lý việc không được dự đoán trước và incident

### 21.1. Hàng chờ liên tục cần nguồn intake đáng tin

Nguồn intake có thể là:

- Product Backlog và phản hồi từ người dùng.
- Support tickets có dấu vết ảnh hưởng.
- Lỗi CI hoặc batch jobs được xác nhận.
- Sự cố bảo mật và vận hành.
- Yêu cầu tuân thủ có mốc.
- Technical debt được mô tả bằng cơ chế gây chi phí thay đổi.

Đội không nên cho mọi tin nhắn riêng tự trở thành việc đã Start. Cần **một đường tiếp nhận công khai và người/chính sách quyết định khi nào item được nhận vào hệ thống**.

### 21.2. Incident cần cơ chế riêng, không phải chỉ một nhãn đỏ

Một sự cố nghiêm trọng đang ảnh hưởng production có thể phải dùng **incident response** ngay:

- Phân loại tác động.
- Kích hoạt người trực có thẩm quyền.
- Giảm tác động, bảo vệ dữ liệu.
- Ghi quyết định/timeline.
- Phục hồi và đánh giá sau sự cố.

Việc tạo item Expedite trên board giúp **thấy ảnh hưởng lên dòng công việc**, nhưng không thay runbook, trách nhiệm bảo mật hoặc kiểm soát khẩn cấp.

### 21.3. Việc khẩn có chi phí chuyển ngữ cảnh

Giả sử team đang có ba PBI Standard, phải dừng hai item để sửa lỗi phân quyền. Team cần ghi:

- Những item nào tạm dừng và ai bị ảnh hưởng.
- Những deadline/SLE nào có nguy cơ trễ.
- Ai sẽ cập nhật người yêu cầu.
- Item nào cần được tiếp tục khi sự cố ổn.
- Có cần cải thiện test để tránh lặp lại không.

**Đừng giả vờ throughput không bị ảnh hưởng bởi incident** bằng cách ghi một lượng effort ngầm và vẫn giữ các forecast cũ.

### 21.4. Nếu mọi ngày đều có “khẩn”, cần điều tra hệ thống

Những nguyên nhân có thể gồm:

- Chất lượng sản phẩm yếu.
- Thiếu phân quyền ưu tiên.
- Thói quen stakeholder gắn nhãn gấp.
- Quá ít đầu tư vào technical debt.
- Một hệ thống đối tác bất ổn.
- Thiếu năng lực hỗ trợ và on-call.
- Các thay đổi được phát hành với rủi ro chưa kiểm soát.

Kanban giúp **nhìn sự mất cân bằng**, nhưng cần đầu tư vào chất lượng, cấu trúc trách nhiệm và sản phẩm để giảm nguồn phát sinh.

## 22. Chất lượng kỹ thuật và Definition of Done trong dòng liên tục

### 22.1. Định nghĩa Finish phải bảo vệ chất lượng

Đối với PBI phát triển phần mềm, một item có thể cần:

- Acceptance criteria được kiểm chứng.
- Automated tests theo rủi ro.
- Code review phù hợp.
- Tích hợp vào hệ thống.
- Kiểm tra quyền và dữ liệu quan trọng.
- Tương thích hợp đồng API.
- Cập nhật tài liệu/observability cần thiết.
- Đáp ứng **Definition of Done** nếu dùng Scrum.

**Không được đổi Finish thành “Developer đã viết code”** chỉ để nâng throughput. Kỹ thuật và sản phẩm sẽ trả giá bằng rework hoặc sự cố.

### 22.2. XP giúp Kanban xử lý được đầu vào liên tục

Các thực hành **TDD, Pair Programming, Continuous Integration, Refactoring và Collective Code Ownership** có thể:

- Giảm thời gian phát hiện lỗi.
- Giảm hàng chờ review nhờ chia sẻ hiểu biết.
- Tạo PR nhỏ và tích hợp thường xuyên.
- Duy trì chất lượng khi thay đổi thứ tự backlog.
- Giúp một item đủ nhỏ để Done khi không cần đợi một đợt release lớn.

**Kanban không thay TDD/CI**, và XP không thay chính sách intake/WIP. Hai nhóm thực hành bổ sung nhau.

### 22.3. Phát hành liên tục khác quản lý dòng công việc liên tục

Một đội có thể sử dụng Kanban nhưng **chỉ được deploy production theo cửa sổ mỗi tháng**. Họ vẫn có thể:

- Kéo PBI khi có năng lực.
- Tạo Increment Done thường xuyên.
- Chạy CI/contract tests trên từng thay đổi.
- Theo dõi release-ready queue riêng.
- Thu nhận feedback từ prototype hoặc nhóm pilot được phép.

**Continuous flow không buộc Continuous Deployment.** Đội phải phân biệt development cadence, verification/validation cadence và release cadence.

### 22.4. Không hy sinh kiểm soát dữ liệu khi xử lý expedite

Lỗi quyền truy cập người học không thể được giải quyết bằng “bỏ qua test A/B để nhanh Done”. Incident và bảo mật có thể yêu cầu hành động khẩn, nhưng **khẩn không có nghĩa được phép bất cẩn với dữ liệu nhạy cảm**. Có thể giảm phạm vi change, dùng safe mode hoặc biện pháp tạm theo runbook; vẫn cần kiểm chứng thích hợp.

## 23. Case study: lựa chọn Kanban cho nhóm hỗn hợp sản phẩm và hỗ trợ

**Các mốc, team và chỉ số trong phần này đều là tình huống giả định để học**, không phải kết quả một dự án thật.

### 23.1. Bối cảnh

Một nhóm sáu người phụ trách:

- Phần web cho học viên quay lại khóa học.
- API tiến độ và kết nối LMS.
- Batch đồng bộ dữ liệu hàng đêm.
- Sửa lỗi và hỗ trợ vận hành liên quan sản phẩm.
- Tăng chất lượng kiểm thử và CI.

Mỗi hai tuần họ có kế hoạch khoảng tám PBI, nhưng thường phát sinh incident/bug và yêu cầu dữ liệu. Có nhiều việc “code complete” nhưng đợi review/test vài ngày. Product Owner vẫn giữ Product Goal “học viên tìm lại đúng bài nhanh và an toàn”.

### 23.2. Vấn đề được quan sát

Trong bốn tuần minh họa:

| Tín hiệu | Baseline |
| --- | ---: |
| WIP cao nhất trong tuần | 13 item |
| WIP trung bình theo snapshot hằng ngày | 9 item |
| Median cycle time item Done | 10 ngày lịch |
| Item đang mở già nhất | 18 ngày |
| Throughput trung bình | 4 item/tuần |
| PR chờ review trung vị | 3 ngày |
| Incident thực trong kỳ | 2 |
| Lỗi hồi quy được ghi nhận | 2 |

Có một số dấu hiệu rằng **việc chờ và WIP cao** đang ảnh hưởng khả năng hoàn tất. Nhưng chưa thể kết luận Kanban chắc chắn là giải pháp; cần điều tra **điểm nghẽn review, DoD, kỹ năng và cách ưu tiên**.

### 23.3. Lựa chọn được xem xét

**Phương án A — Giữ Scrum và thêm flow practices:**

- Giữ Sprint Goal và các events.
- Dùng WIP limits.
- Đưa aging WIP vào Daily Scrum.
- Phân loại incident và dự phòng năng lực.
- Chia PBI nhỏ, cải thiện CI.

**Phương án B — Dùng Kanban làm cơ chế quản lý dòng chính:**

- Không chọn khối lượng Sprint cố định làm điểm bắt đầu công việc.
- Replenishment khi có năng lực.
- DoW, WIP control, SLE, pull và service policies rõ.
- Giữ review sản phẩm/retrospective theo nhịp.
- Đo và cải tiến flow trong bối cảnh nhu cầu liên tục.

**Phương án C — Tách dòng hỗ trợ và phát triển:**

- Dòng incident/support có chính sách riêng.
- Dòng phát triển sản phẩm có nhịp Scrum hoặc Kanban thích hợp.
- Quản lý rõ việc **cùng một người đang được tính vào hai dòng**, không gán toàn bộ năng lực hai lần.

Đội chọn **thử Phương án B trong sáu tuần** vì nhu cầu liên tục và Sprint Goal thường xuyên không còn khả năng phản ánh cách công việc thực tế đến. Tuy nhiên họ vẫn giữ Product Goal và nhịp stakeholder review, không bỏ chất lượng.

### 23.4. Thiết lập DoW thử nghiệm

| Thành phần | Chính sách của team (giả định) |
| --- | --- |
| **Phạm vi** | Bug, PBI nhỏ và cải tiến kỹ thuật của dịch vụ học tập |
| **Start** | Chuyển Ready → In Progress |
| **Finish** | Đạt tiêu chuẩn Done có test/tích hợp và kiểm tra quyền nếu liên quan |
| **WIP limits** | Tổng 5; In Progress 3, Review 2, Verification 2 |
| **Blocked** | Vẫn là WIP; ghi người phụ trách gỡ blocker và bước tiếp |
| **Expedite** | Incident thật theo tiêu chí on-call; tối đa một item expedite đồng thời theo thử nghiệm |
| **Standard** | Kéo theo ưu tiên giá trị, rủi ro và mức Ready |
| **Fixed date** | Nghĩa vụ có mốc rõ; chuẩn bị sớm và theo dõi age |
| **SLE** | Mục tiêu kỳ vọng tạm thời 85% item Standard ≤ 8 ngày, chờ hiệu chỉnh |
| **Feedback** | Xem aging WIP mỗi ngày, replenishment hai lần/tuần, sản phẩm hai tuần/lần |

WIP limit tổng **5** là rào chắn chung; không có nghĩa ba giới hạn cột 3 + 2 + 2 cho phép mở đồng thời bảy item. **Giới hạn tổng và giới hạn cục bộ phải cùng được tuân thủ/điều chỉnh có lý do.**

### 23.5. Tuần 1: nhìn sự thật, không ép người

Nhóm nhập các item đang tồn tại lên board:

- Ba item chờ review.
- Hai item đợi dữ liệu batch.
- Một PBI chưa có acceptance criteria.
- Hai item Code Complete nhưng chưa kiểm thử quyền.
- Nhiều ý tưởng chưa đủ Ready.

Họ thống nhất **đánh dấu blocked và không xóa age cũ**. Những việc không đủ điều kiện Done không được đẩy sang cột Done chỉ để “dọn bảng”.

### 23.6. Tuần 2: giới hạn mở mới và gỡ review bottleneck

Dựa trên board, Developers thấy việc review bị tập trung ở một người hiểu authentication. Họ:

1. Pairing tìm hiểu quy tắc quyền truy cập.
2. Chia PR lớn thành thay đổi nhỏ hơn có test.
3. Tạo reviewer dự phòng theo mức rủi ro phù hợp.
4. Tự động hóa format/lint để reviewer tập trung vào hành vi.
5. Cùng xử lý item cũ trước khi kéo tiếp.

Những thay đổi này có thể hỗ trợ Kanban; **không phải bản thân việc vẽ cột tạo ra năng lực review**.

### 23.7. Tuần 3: một incident thật xuất hiện

LMS batch thất bại làm dữ liệu tiến độ bị trễ. Đội kích hoạt chính sách incident, phân công người xử lý, ghi những PBI Standard phải tạm dừng và thông báo stakeholder về rủi ro.

Sau phục hồi, họ tạo item cải tiến **giám sát batch và retry an toàn**. Không dùng sự cố làm lý do từ bỏ kiểm chứng hoặc ghi **“đạt 100% SLE”**.

### 23.8. Tuần 4: xem tín hiệu và phản hồi người dùng

Review sản phẩm tập trung vào:

- Lát cắt nào đã Done và có thể sử dụng?
- Học viên có mở đúng bài hơn không?
- Độ trễ dữ liệu còn gây hiểu lầm không?
- Có lỗi phân quyền hoặc truy cập sai khóa không?
- Việc kéo Standard có bị đói vì Incident không?
- SLE hiện có còn thực tế cho các loại công việc khác nhau không?

Product Owner điều chỉnh thứ tự lựa chọn. Team tiếp tục đo **flow và outcome**, thay vì coi một Sprint bị hủy là “mất kỷ luật”.

### 23.9. Tuần 5–6: đánh giá thử nghiệm

Giả sử dữ liệu minh họa:

| Tín hiệu | Baseline 4 tuần | Sau thử nghiệm 6 tuần |
| --- | ---: | ---: |
| WIP cao nhất trong tuần | 13 | 7 |
| WIP trung bình theo snapshot hằng ngày | 9 | 6 |
| Median cycle time item Done | 10 ngày | 7 ngày |
| Item đang mở già nhất | 18 ngày | 11 ngày |
| Throughput bình quân | 4 item/tuần | 5 item/tuần |
| PR chờ review trung vị | 3 ngày | 1 ngày |
| Lỗi hồi quy ghi nhận/kỳ | 2 | 2 |
| Tỷ lệ người học mở đúng bài trong mẫu thử | 72% | 80% |

Đây **không phải thử nghiệm kiểm soát nhân quả**: loại PBI, mức hỗ trợ, CI, kỹ năng reviewer và số người dùng đều có thể thay đổi. Nhưng nó có thể là **bằng chứng khởi đầu** để nhóm hỏi có nên giữ pull/WIP policy, thay SLE hoặc đầu tư tiếp vào kỹ thuật nào.

### 23.10. Quyết định sau thử nghiệm

Giả sử cả team ghi nhận giảm context switching và ít item bị quên hơn, họ có thể:

- Giữ DoW và WIP tổng sau khi xem năng lực.
- Điều chỉnh SLE với dữ liệu các loại item đủ đại diện.
- Tạo một mức ưu tiên rõ cho security incidents.
- Duy trì product feedback review hai tuần một lần.
- Dọn những thẻ/cột không giúp ra quyết định.
- Giữ DoD và test không đổi.
- Xem lại sau một giai đoạn khi môi trường hoặc lượng incident biến động.

**Thành công không phải “chúng ta đã chuyển sang Kanban” mà là hệ thống phục vụ giá trị tốt hơn trong giới hạn chất lượng và năng lực bền vững.**

## 24. Chọn Kanban theo bối cảnh: năm tình huống đối chiếu

### 24.1. Nhóm bảo trì production với yêu cầu đến liên tục

**Bối cảnh:** bug, incident, bản vá, hỗ trợ khách hàng và cải tiến nhỏ đến mỗi ngày. Một mục tiêu Sprint ít khi bao phủ được toàn bộ nhu cầu.

**Cân nhắc:** Kanban thường phù hợp để quản lý intake, WIP, xử lý khẩn, aging, thời gian chờ và SLE. Vẫn cần incident policy riêng, kỹ thuật đáng tin và phản hồi giá trị.

### 24.2. Scrum Team xây sản phẩm mới, có Sprint Goal rõ

**Bối cảnh:** team có mục tiêu Sprint có ý nghĩa, mỗi Sprint tạo Increment và thường ít interruption. Vấn đề chủ yếu là PR/verification cuối Sprint bị dồn.

**Cân nhắc:** **chưa cần bỏ Scrum**. Có thể áp dụng WIP limits, swarming, Kanban metrics và test/CI trong Sprint. Xem liệu timebox vẫn giúp tập trung và học hỏi không.

### 24.3. Đội tích hợp API cho nhiều product teams

**Bối cảnh:** nhiều request phục vụ những team khác nhau, mức ưu tiên thay đổi, một phần công việc phải đáp ứng SLA bên ngoài.

**Cân nhắc:** Kanban có thể làm rõ **dịch vụ được cung cấp, luồng yêu cầu, class of service và SLE**. Nhưng cần quản lý quyền quyết định chung và giải pháp kỹ thuật giảm phụ thuộc; đừng để “nhóm shared service” trở thành hàng chờ bất tận.

### 24.4. Dự án migration nhiều ràng buộc và một mốc bắt buộc

**Bối cảnh:** chuyển dữ liệu hàng trăm nghìn học viên, có ngày dừng hệ thống đã duyệt và kiểm chứng không thể bỏ.

**Cân nhắc:** Kanban hữu ích cho dòng work item và risk burn-down, nhưng **kế hoạch migration, rehearsal, governance, dependency map và release plan** vẫn cần. Không được viện dẫn “continuous flow” để bỏ phê duyệt hoặc kiểm tra dữ liệu.

### 24.5. Một đội lớn có nhiều sản phẩm thật sự độc lập

**Bối cảnh:** cùng phòng ban nhưng phục vụ ba sản phẩm có Product Goals riêng.

**Cân nhắc:** Trước khi chọn Kanban, cần **phân định các sản phẩm và quyền ưu tiên**. Một board khổng lồ có thể che những luồng khác nhau; có thể cần DoW/SLE riêng, nhóm ổn định hoặc các Kanban systems kết nối theo dịch vụ.

## 25. Lộ trình thử Kanban trong 30 ngày

Lộ trình dưới đây là **ví dụ để điều chỉnh**, không phải quy trình chứng nhận hoặc quy định chính thức của Kanban Guide.

### Tuần 1 — Khảo sát và baseline

- Quan sát yêu cầu đi vào, thời điểm Start và Finish thật.
- Phân loại incident, bug, feature, security và technical debt.
- Hỏi stakeholder mức phục vụ và thời hạn thực.
- Vẽ workflow hiện tại, gồm những điểm chờ quan trọng.
- Đếm WIP hiện tại, age của item lâu nhất, throughput theo kỳ.
- Kiểm tra DoD/tiêu chuẩn chất lượng và dữ liệu có đáng tin không.
- Ghi một **giả thuyết cải tiến** rõ, không vội đặt 20 KPI.

**Đầu ra:** bản DoW thử nghiệm và baseline với giới hạn dữ liệu.

### Tuần 2 — Kiểm soát WIP và minh bạch policies

- Chọn WIP limits có thể thử theo năng lực.
- Thống nhất Ready, pull, Finish, blocked, cancel/reopen.
- Thiết lập đường incident/expedite có tiêu chí.
- Ghi cách chọn item Standard.
- Bắt đầu flow review tập trung item già.
- Không tự ý thay đổi DoD để đạt target.

**Đầu ra:** board phản ánh dòng thật và mọi người hiểu chính sách.

### Tuần 3 — Giảm một bottleneck có bằng chứng

- Quan sát chỗ age/WIP tích tụ.
- Chọn một cải tiến kỹ thuật hoặc phối hợp: pairing review, contract tests, cải thiện CI, chia PBI nhỏ.
- Thử trên phạm vi cụ thể.
- Theo dõi các tác động không mong muốn.
- Giữ việc khẩn đi đúng runbook, không dùng expedite tùy tiện.

**Đầu ra:** một thay đổi nhỏ có thể kiểm tra bằng dữ liệu và phản hồi nhóm.

### Tuần 4 — Review service, chất lượng và outcome

- Xem throughput, cycle time phân phối và aging WIP.
- Xem lỗi hồi quy, incident, SLE và workload bền vững.
- Xem người dùng/stakeholder có được giá trị đúng nhu cầu không.
- Xác định nơi đo sai do đổi chính sách hoặc thiếu dữ liệu.
- Giữ, điều chỉnh hoặc bỏ một chính sách.
- Chọn một thử nghiệm tiếp theo và mốc xem lại.

**Đầu ra:** DoW v1.1 và quyết định có chứng cứ, không phải “áp dụng Kanban xong rồi”.

### 25.1. Một thay đổi cần ưu tiên nếu năng lực kỹ thuật thấp

Nếu sau tuần 1 phát hiện không có contract test cho quyền học viên, **ưu tiên dựng rào chắn chất lượng trước việc tối ưu throughput**. Kanban có thể tiếp tục hỗ trợ minh bạch WIP, nhưng không thể thay yêu cầu bảo vệ dữ liệu.

## 26. Quản trị và trách nhiệm trong hệ thống pull

### 26.1. Product Owner vẫn cần nếu đội làm Scrum

Khi một Scrum Team sử dụng Kanban, Product Owner vẫn có accountability tối đa hóa giá trị sản phẩm và quản lý Product Backlog hiệu quả. Không chuyển trách nhiệm sang “người cầm bảng Kanban” chỉ vì tên phương pháp.

Nếu đội **không dùng Scrum**, họ vẫn phải xác định rõ ai có quyền:

- Quyết định thứ tự dịch vụ và các trade-off.
- Chấp nhận những yêu cầu nào vào hệ thống.
- Phân loại rủi ro/incident.
- Xác nhận một deadline hoặc nghĩa vụ.
- Chấp nhận release theo chính sách.
- Giao tiếp với người yêu cầu về SLE/kỳ vọng.

### 26.2. Không dùng Kanban để bỏ qua kiểm soát thật

Một đội có thể deploy production theo cửa sổ đã duyệt, giữ review bảo mật bắt buộc và vẫn dùng Kanban cho phần phát triển. Có thể:

- Chuẩn bị automated tests/evidence sớm.
- Đưa những việc Done vào release-ready queue riêng.
- Quan sát queue age và thời gian phê duyệt.
- Làm rõ người có quyền release.
- Phân loại emergency change theo chính sách.
- Học từ release và incident để giảm chi phí lặp lại.

**Pull system không phải quyền bỏ qua governance**.

### 26.3. Các nhóm phụ thuộc nhau cần hiển thị chờ đợi

Nếu API tiến độ phụ thuộc LMS team hoặc đối tác:

- Ghi dependency rõ trong item.
- Xác định hợp đồng cần thay và người phối hợp.
- Có mốc thảo luận tương thích.
- Dùng contract tests và integration tests.
- Báo sớm khi age có nguy cơ vượt SLE.
- Tìm cách giảm dependency qua architecture hoặc feature teams.

Không tạo “WIP đẹp” bằng cách đẩy mọi việc bị chặn sang một board của team khác rồi xem như hoàn tất.

### 26.4. Năng lực phục vụ cần có giới hạn bền vững

Kanban không mang ý nghĩa “xử lý mọi request ngay”. Một mức phục vụ có trách nhiệm cần:

- Năng lực và kỹ năng có thật.
- Thời gian kiểm chứng chất lượng.
- Dự phòng cho incident khi môi trường cần.
- Người thay thế phù hợp.
- Thỏa thuận giờ làm và trực sự cố.
- Dữ liệu biến động để dự báo.
- Minh bạch rủi ro khi nhu cầu lớn hơn khả năng hoàn tất.

**Tối ưu sử dụng 100% thời gian của từng người** có thể tăng hàng chờ và giảm khả năng xử lý sự cố. Đội nên tối ưu **khả năng giao giá trị ổn định**, không tối đa hóa vẻ bận rộn.

## 27. Anti-pattern khi “chuyển sang Kanban”

| Anti-pattern | Vấn đề thật | Hướng điều chỉnh |
| --- | --- | --- |
| “Tạo board ba cột là đã dùng Kanban.” | Chưa có Start/Finish, WIP control và chính sách. | Xây DoW, quản lý age và phản hồi. |
| “Kanban nghĩa là không lập kế hoạch.” | Không có cơ chế chọn việc sẽ tạo hỗn loạn ưu tiên. | Replenishment, mục tiêu và ưu tiên rõ. |
| “Ai rảnh cứ nhận ticket mới.” | WIP tăng, item cũ bị bỏ. | Pull khi có năng lực và kiểm tra WIP policy. |
| “Blocked không tính WIP.” | Giấu hàng chờ và age. | Tính item đã Start chưa Finish, hiển thị blocker. |
| “Giới hạn WIP là số Developer.” | Không xét swarming, review và phụ thuộc. | Thử nghiệm theo năng lực toàn hệ thống. |
| “WIP vượt là lỗi cá nhân.” | Dẫn tới thao túng trạng thái. | Điều tra hệ thống và điều chỉnh có lý do. |
| “Mọi việc đều Expedite.” | Không còn ưu tiên và phá khả năng dự báo. | Tiêu chí khẩn nghiêm túc, ghi ngoại lệ. |
| “Người có chức vụ cao được nhảy hàng tự động.” | Đánh tráo chi phí chậm trễ và rủi ro. | Chính sách ưu tiên minh bạch dựa trên tác động. |
| “Done khi code đã viết xong.” | Thiếu test/tích hợp, tạo rework. | Finish gắn với chất lượng/DoD. |
| “Bỏ CI để giảm cycle time.” | Đẩy lỗi sang production. | Cải tiến test và pipeline, không bỏ rào chắn. |
| “Throughput tăng là giá trị tăng.” | Có thể tăng bằng cách chia ticket giả. | Xem outcome và DoD, nhất quán work item. |
| “SLE 85% trong 8 ngày nghĩa là mọi item xong ngày 8.” | Diễn giải kỳ vọng xác suất thành bảo đảm. | Trao đổi phân phối và giới hạn dự báo. |
| “Cycle time trung bình thấp thì không có việc kẹt.” | Completed items che aging WIP. | Xem age của item chưa Finished. |
| “Little’s Law bảo đảm deadline.” | Quan hệ trung bình không dự báo từng item. | Kiểm tra điều kiện và bất định. |
| “Scrum và Kanban không thể dùng chung.” | Bỏ mất cơ hội cải thiện flow trong Sprint. | Giữ Scrum đúng và dùng Kanban practices có chủ đích. |
| “Kanban không có role nên không cần Product Owner.” | Bỏ trách nhiệm chọn giá trị và quyết định. | Làm rõ authority và giữ PO nếu dùng Scrum. |
| “Muốn Kanban tốt phải release hằng ngày.” | Nhầm continuous flow với Continuous Deployment. | Tách Done, release và validation. |
| “Incident là ticket Standard có màu đỏ.” | Thiếu escalation, quyền và khôi phục. | Incident policy/runbook rõ. |
| “CFD phình là chắc chắn QA làm chậm.” | Không đủ bằng chứng về nguyên nhân. | Xem item, biến động và ranh giới. |
| “Mẫu WIP limit của đội khác là chuẩn.” | Khác loại việc, kỹ năng và năng lực. | Đo baseline, thử và xem lại. |
| “Mọi team phải bỏ Sprint khi có support work.” | Nhiều nhóm vẫn dùng Scrum tốt với flow policies. | Chẩn đoán tác động thật tới Sprint Goal. |
| “Xếp hạng Developer theo item Done.” | Khuyến khích việc dễ, giấu việc khó. | Dùng metrics cho cải tiến hệ thống, không trừng phạt. |
| “Kanban là đích đến cuối cùng.” | Workflow sẽ tiếp tục thay đổi theo nhu cầu. | Evolutionary change, inspect and adapt. |

## 28. Checklist ra quyết định và vận hành

### 28.1. Trước khi chọn Kanban

- [ ] Đã xác định **người dùng, dịch vụ và outcome** của nhóm.
- [ ] Biết nhu cầu đến đều/biến động và mức interruption thật.
- [ ] Có bằng chứng về WIP, blocked time và tuổi công việc.
- [ ] Đã phân biệt vấn đề flow với vấn đề Product Goal/kiến trúc/DoD.
- [ ] Có quyền quyết định ưu tiên và trách nhiệm incident rõ.
- [ ] Đã xem liệu Scrum + Kanban practices có đủ đáp ứng không.
- [ ] Không chọn framework chỉ vì số người hoặc mong muốn giảm họp.
- [ ] Biết các ràng buộc vận hành/pháp lý không được bỏ.

### 28.2. Khi tạo Definition of Workflow

- [ ] Work item và loại công việc được định nghĩa rõ.
- [ ] Start/Finish có mốc kiểm chứng được.
- [ ] Các trạng thái phản ánh bước làm và điểm chờ thật.
- [ ] WIP control có phạm vi và quy tắc ngoại lệ.
- [ ] Pull/Ready/blocked/expedite/cancel/reopen có chính sách.
- [ ] Có tiêu chuẩn chất lượng/DoD khi Finish.
- [ ] SLE có phần trăm, thời gian và giả định dữ liệu rõ.
- [ ] Lịch replenishment và feedback phù hợp.
- [ ] Mọi người biết cách xem lại/chỉnh sửa DoW.

### 28.3. Khi dùng flow metrics

- [ ] WIP bao gồm item blocked đã Start chưa Finished.
- [ ] Cycle time chỉ tính khi item Finished.
- [ ] Work item age áp dụng cho item chưa Finished.
- [ ] Throughput đếm số item qua Finish trong kỳ nhất quán.
- [ ] Dùng phân phối/trung vị/phân vị cùng các item đuôi dài, không chỉ mean.
- [ ] Phân loại các item khi mix công việc không đồng nhất.
- [ ] Không tự đổi Start date, Done hoặc tách ticket vì KPI.
- [ ] Nếu dùng Little’s Law, kiểm tra ranh giới và tính ổn định.
- [ ] Forecast ghi rõ giả định, không tự gắn mức chắc chắn.
- [ ] Xem guardrail về test, chất lượng và tác động người dùng.

### 28.4. Khi xem lại và cải tiến

- [ ] Item già nhất và blocker được thảo luận có hành động cụ thể.
- [ ] Nhóm đã thử ưu tiên **hoàn tất việc cũ** khi WIP đầy.
- [ ] Có cải tiến kỹ thuật hoặc phối hợp đi kèm thay đổi board.
- [ ] Stakeholder có phản hồi về mức phục vụ và giá trị nhận được.
- [ ] Thời gian review/CI và release queue được nhìn riêng khi cần.
- [ ] Thỏa thuận giờ làm và incident on-call bền vững.
- [ ] Có đánh giá tác động của policy lên cả throughput và chất lượng.
- [ ] Có quyết định giữ, sửa hoặc bỏ một thỏa thuận dựa trên dữ liệu.

## 29. Bài tập thực hành

### Bài tập 1 — Nhận diện bối cảnh phù hợp

Một team bảo trì ứng dụng học tập có 12 ticket hỗ trợ mỗi tuần, hai lỗi khẩn bất định và ba user stories cải tiến. Một team khác tập trung xây một sản phẩm mới với Sprint Goal rõ và ít việc phát sinh.

Hãy đề xuất **Kanban, Scrum hoặc Scrum + Kanban practices** cho từng team. Giải thích ít nhất bốn tiêu chí và những dữ liệu còn thiếu trước khi quyết định.

### Bài tập 2 — Vẽ DoW

Thiết kế **Definition of Workflow** cho một dịch vụ nhận bug, security fixes và feature improvements. Yêu cầu có:

- Work item types.
- Start/Finish.
- Các trạng thái và blocked policy.
- WIP control toàn hệ thống và một hoặc hai cột.
- Pull và Ready criteria.
- SLE tạm và nguồn dữ liệu.
- Cách xử lý expedite/cancel/reopen.
- Quality guardrail.
- Mốc feedback.

Giải thích một chính sách nào nên được điều chỉnh sau bốn tuần.

### Bài tập 3 — Tính cycle time

Dựa trên 12 item ở mục 16:

1. Tính cycle time của K5, K8, K10 và K12.
2. Tính tổng cycle time.
3. Tính trung bình và trung vị.
4. Vì sao kết quả không đủ để bảo đảm thời gian của một item mới?
5. Nếu đổi cách đếm ngày lịch thành ngày làm việc, cần thêm thông tin gì?

### Bài tập 4 — WIP và work item age

Tại **đầu D12** của dữ liệu mục 16:

1. Những item nào đang WIP?
2. WIP bằng bao nhiêu?
3. Work item age của từng item?
4. K7 và K12 có thuộc WIP không, vì sao?
5. Vì sao không được cộng age của các item hiện tại để gọi đó là cycle time?

### Bài tập 5 — Throughput theo kỳ

Dùng ba kỳ [D1, D8), [D8, D15), [D15, D22):

1. Xác định các item Finished trong mỗi kỳ.
2. Tính throughput và bình quân đơn giản.
3. Nếu K8 Finished đúng đầu D15 thay vì D14, kỳ nào cần tính K8?
4. Vì sao số lượng item không tự đo giá trị?
5. Nếu hệ thống thường nhận thêm incident vào kỳ thứ ba, dự báo sẽ thay đổi thế nào?

### Bài tập 6 — WIP limit và pull

Board có In Progress 2/3, Review 3/2, Verification 1/2, tổng WIP 6/5. Developer muốn Start PBI mới.

Hãy giải thích:

- Những giới hạn nào đã bị vượt?
- Nên kiểm tra item nào trước?
- Có thể giúp Review bằng những cách nào?
- Khi nào một ngoại lệ expedite có lý?
- Vì sao không chuyển item blocked về Backlog chỉ để giảm WIP?

### Bài tập 7 — SLE và aging WIP

Một tập 12 cycle time: **2, 4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 6** ngày.

1. Tính P85 theo nearest-rank.
2. Có bao nhiêu item ≤ 5 ngày?
3. Vì sao mẫu này chưa đủ để tuyên bố SLA 100%?
4. Một item đang age 8 ngày cần được quản lý thế nào?
5. Viết một cách diễn đạt SLE rõ, có giới hạn.

### Bài tập 8 — Little’s Law

Một hệ thống ổn định giả định có WIP bình quân 8 item và throughput bình quân 4 item/tuần.

1. Tính cycle time bình quân.
2. Nếu WIP giảm còn 6, throughput giữ nguyên, cycle time theo Little’s Law là bao nhiêu?
3. Liệt kê năm điều kiện cần xem trước khi suy từ số liệu.
4. Vì sao không được cam kết mọi PBI sẽ Done trong thời gian ấy?

### Bài tập 9 — Forecast từ throughput

Dữ liệu tám tuần **4, 6, 5, 3, 6, 5, 4, 7** item; backlog còn 20 item.

1. Tính tổng, trung bình, min/max.
2. Tính ước tính tuyến tính thô số tuần cần.
3. Viết một forecast có điều kiện.
4. Khi nào mô phỏng Monte Carlo hữu ích?
5. Vì sao forecast Done không phải forecast Released nếu production chỉ có cửa sổ mỗi tháng?

### Bài tập 10 — Incident và Standard work

Có một bug báo giao diện lệch màu, một yêu cầu thêm biểu đồ học tập, và một sự cố có bằng chứng tài khoản A có thể đọc tiến độ B.

- Việc nào cần cơ chế incident/expedite?
- Ai có quyền phân loại mức độ?
- Team cần thông báo tác động lên những Standard items nào?
- Điều kiện chất lượng nào không được bỏ?
- Sau sự cố, item cải tiến phòng ngừa nên được chọn và theo dõi thế nào?

### Bài tập 11 — Scrum cùng Kanban

Một Scrum Team muốn dùng WIP limits, aging WIP và pull trong Sprint. Một thành viên đề xuất bỏ Sprint Review và thay Sprint Goal bằng “throughput = 10”.

Hãy phản biện, giữ đúng các thành tố Scrum, đồng thời nêu **ba cách Kanban hỗ trợ chất lượng Sprint**.

### Bài tập 12 — Đọc CFD

CFD của một team cho thấy vùng Review dày dần, đường Started tăng đều nhưng đường Finished gần như phẳng trong một tuần.

1. Nêu ba giả thuyết cần kiểm tra.
2. Chọn hai thử nghiệm cải thiện.
3. Định nghĩa chỉ số/guardrail theo dõi.
4. Vì sao không đủ bằng chứng để đổ lỗi cho reviewer?
5. Nếu item có tuổi 20 ngày chưa Done, chỉ số nào giúp đội thấy nó ngay?

### Bài tập 13 — Lựa chọn cho hệ thống legacy

Nhóm hỗ trợ LMS cũ nhận công việc liên tục nhưng chỉ được deploy production theo cửa sổ bốn tuần. Có ràng buộc kiểm thử dữ liệu và quyền truy cập.

Hãy đề xuất **Kanban DoW, release-ready queue, SLE và kiểm soát chất lượng**; phân biệt Done/Deployed/Released/Validated. Vì sao continuous flow không đồng nghĩa bypass change policy?

### Bài tập 14 — Thử nghiệm Kanban 30 ngày

Đội có WIP trung bình 12, cycle time trung vị 11 ngày, thường chờ review; người dùng phàn nàn lỗi tiến độ.

Thiết kế kế hoạch 30 ngày:

1. Vấn đề và giả thuyết cải thiện.
2. Baseline và cách đo Start/Finish.
3. Một thay đổi WIP/pull policy.
4. Một cải tiến CI, test hoặc pairing.
5. Cách đo chất lượng và outcome.
6. Mốc đánh giá và quyết định giữ/sửa/bỏ.

### Bài tập 15 — Chống hành vi tối ưu sai

Quản lý nói: “Tháng này mỗi Developer phải Done 20 ticket; nếu thiếu thì chia ticket thành nhiều phần hoặc đóng trước rồi test sau.”

Hãy trình bày vì sao đề xuất ấy gây rủi ro cho flow, DoD, dữ liệu và người dùng. Đề xuất **một bộ tín hiệu ở cấp hệ thống** và cách dùng metrics để học thay vì xếp hạng cá nhân.

## 30. Đáp án chọn lọc và câu hỏi tự kiểm

### 30.1. Phép tính của bộ dữ liệu 12 item

- **K5:** D4 → D9 = **5 ngày**.
- **K8:** D8 → D14 = **6 ngày**.
- **K10:** D11 → D16 = **5 ngày**.
- **K12:** D14 → D19 = **5 ngày**.
- Tổng cycle time: **52 ngày-item**.
- Trung bình: **52/12 ≈ 4,33 ngày/item**.
- Trung vị: **4 ngày**.
- WIP đầu D12: **K8, K9, K10, K11 = 4 item**.
- Age tương ứng: **4, 3, 1, 0 ngày**.
- Throughput ba kỳ: **4, 5, 3 item**.
- P85 nearest-rank: vị trí **11**, giá trị **5 ngày**.
- Số item ≤ 5 ngày: **11/12 ≈ 91,7%**.

### 30.2. Little’s Law

- WIP bình quân 8 / throughput 4 item/tuần = **2 tuần cycle time bình quân**, nếu điều kiện áp dụng phù hợp.
- WIP bình quân 6 / throughput 4 item/tuần = **1,5 tuần**.
- Không áp dụng thẳng cho deadline của một item riêng; chú ý ranh giới, ổn định, loại việc, thống kê và chất lượng.

### 30.3. Forecast throughput

- Tổng tám tuần: **40 item**.
- Trung bình: **5 item/tuần**.
- Min/max quan sát: **3/7 item/tuần**.
- Ước tính thô cho 20 item tương tự: **4 tuần**.
- Đừng biến phép chia này thành bảo đảm có xác suất cao nếu chưa kiểm tra dữ liệu và bất định.

### 30.4. Những câu hỏi tự phản tư

1. Khi nào tôi nên **thử giảm WIP trước khi đổi phương pháp làm việc**?
2. Tôi có thể chỉ ra **Start, Finish, Work Item và SLE** của một dịch vụ cụ thể không?
3. Tôi có biết **việc nào đang già nhưng chưa Done**, chứ không chỉ xem Completed items không?
4. Tôi có phân biệt **incident thật** với yêu cầu được gắn “urgent” không?
5. Tôi có hiểu **Kanban không bỏ Product Goal, chất lượng, quản trị hoặc feedback** không?
6. Tôi có thể nêu một **đánh đổi khi dùng Kanban thay vì Scrum** trong bối cảnh của nhóm mình không?
7. Tôi có biết cách **giữ Scrum đúng nghĩa và bổ sung WIP/flow practices** không?
8. Tôi có thể giải thích vì sao **continuous flow không buộc release hằng ngày** không?
9. Tôi có kế hoạch **đo tác dụng và ngừng chính sách không hiệu quả** không?
10. Những chỉ số nào cần kết hợp để biết **người học nhận giá trị thật**?

## 31. Tóm tắt kiến thức cốt lõi

**Cân nhắc Kanban khi đội phải quản lý một dòng công việc đến liên tục, khó dự báo chính xác theo timebox, có nhiều loại yêu cầu, hàng chờ và công việc bị chặn.** Giá trị của Kanban nằm ở khả năng **làm minh bạch workflow, kiểm soát WIP, kéo việc theo năng lực, chú ý work item age, cải thiện dòng và học từ các tín hiệu có thật**.

Chọn Kanban không có nghĩa bỏ mục tiêu sản phẩm, lập kế hoạch, release governance hay tiêu chuẩn chất lượng. **Scrum và Kanban có thể kết hợp**: một Scrum Team giữ Product Goal, Sprint Goal, Sprint events và Definition of Done, đồng thời dùng WIP control, pull và flow metrics để giảm việc dở dang. Các thực hành XP như TDD, CI, pairing và refactoring giúp dòng công việc kỹ thuật đủ tin cậy để cải tiến lâu dài.

Một hệ thống Kanban cần có **Definition of Workflow** rõ về work items, Start/Finish, trạng thái, WIP, chính sách và SLE. Bốn phép đo **WIP, Throughput, Work Item Age và Cycle Time** giúp nhìn các khía cạnh bổ trợ. **Little’s Law và forecast throughput** có ích khi ranh giới và điều kiện phù hợp, nhưng không tạo cam kết tuyệt đối hoặc thay đánh giá rủi ro.

Cuối cùng, **“Kanban phù hợp” không được kết luận từ một bảng ba cột hoặc số ticket Done cao**. Hãy bắt đầu từ **vấn đề dịch vụ, người dùng và điểm chờ**, thử một thay đổi nhỏ, quan sát cả **flow, chất lượng và outcome**, rồi giữ/sửa/bỏ chính sách dựa trên bằng chứng. Đó là cách quản lý dòng công việc liên tục mà vẫn trung thành với tinh thần **phản hồi sớm, giao giá trị tăng dần và cải tiến liên tục của Agile**.

## Tài liệu tham khảo

1. [The Kanban Guide](https://kanbanguides.org/english/) — Kanban như chiến lược tối ưu hóa flow, Definition of Workflow, WIP control, Service Level Expectation, WIP/throughput/work item age/cycle time.
2. [Kanban University — The Official Guide to the Kanban Method](https://kanban.university/kanban-guide/) — phát triển phương pháp từ hệ thống hiện tại, giới hạn WIP, quản lý dòng, feedback loops và cải tiến tiến hóa.
3. David J. Anderson, *Kanban: Successful Evolutionary Change for Your Technology Business* (2010) — hệ thống kéo, chính sách và quá trình thay đổi Kanban trong tổ chức công nghệ.
4. Daniel S. Vacanti, *Actionable Agile Metrics for Predictability: An Introduction* (2015) — cycle time, throughput, Work Item Age, cumulative flow và phân tích dự báo.
5. Daniel S. Vacanti, *When Will It Be Done? Lean-Agile Forecasting to Answer Your Customers' Most Important Question* (2017) — dự báo theo flow và quản lý bất định.
6. [The Scrum Guide](https://scrumguides.org/scrum-guide.html), phiên bản tháng 11/2020 — Scrum Team, Sprint Goal, Product Backlog, Increment, Definition of Done, Scrum events.
7. [Scrum.org — Kanban Guide for Scrum Teams](https://www.scrum.org/resources/kanban-guide-scrum-teams) — cách bổ sung flow practices và Kanban metrics khi vẫn vận hành Scrum.
8. [Manifesto for Agile Software Development](https://agilemanifesto.org/) và [Principles](https://agilemanifesto.org/principles.html) — giá trị, phản hồi, khả năng thích ứng và giao phần mềm hoạt động.
9. Kent Beck & Cynthia Andres, *Extreme Programming Explained: Embrace Change*, ấn bản 2 (2004) — các thực hành TDD, Pair Programming, CI và refactoring giúp phản hồi kỹ thuật nhanh.
10. John D. C. Little, “A Proof for the Queuing Formula: L = λW”, *Operations Research* 9(3), 1961 — nền tảng quan hệ Little’s Law.
11. Donald G. Reinertsen, *The Principles of Product Development Flow: Second Generation Lean Product Development* (2009) — hàng chờ, WIP, batch size, cost of delay và thiết kế dòng sản phẩm.
12. [DORA — DevOps Research and Assessment](https://dora.dev/) — chỉ số và nghiên cứu hiệu quả giao phần mềm trong bối cảnh chất lượng, độ tin cậy và cải tiến hệ thống.
13. [Martin Fowler — Continuous Integration](https://martinfowler.com/articles/continuousIntegration.html) — tích hợp thường xuyên và kiểm tra tự động để giảm lỗi tích hợp muộn.
