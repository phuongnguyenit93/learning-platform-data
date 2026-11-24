# Đề xuất cách áp dụng Agile cho nhóm phân tán hoặc nhiều nhóm cùng sản phẩm

Một nền tảng học trực tuyến muốn phát triển tính năng **“Học tiếp”**: khi quay lại ứng dụng, học viên được mở đúng bài đang học dở, trên cả web và thiết bị di động, không làm mất tiến độ và không thấy dữ liệu của người khác. Nhóm thiết kế sản phẩm làm việc tại Thành phố Hồ Chí Minh, một số Developers ở nhiều địa điểm khác, còn API tiến độ, nội dung khóa học và platform được các nhóm khác nhau phụ trách. Mọi người dùng chung một công cụ quản lý công việc nhưng phần lớn quyết định vẫn diễn ra qua tin nhắn riêng, hợp đồng API được kiểm tra muộn và mỗi nhóm báo “Done” theo một nghĩa khác nhau.

Lãnh đạo đề nghị “áp dụng Agile cho toàn bộ các nhóm”. Nhưng **chuyển mọi người sang cùng lịch họp, thêm một cấp điều phối hoặc mua công cụ mới không tự tạo ra phần mềm tích hợp, có giá trị**. Câu hỏi thực hành cần giải là: **Cấu trúc phối hợp tối thiểu nào giúp các thành viên phân tán và nhiều nhóm cùng một sản phẩm lựa chọn đúng việc, giao Increment an toàn, học từ phản hồi sớm và cải tiến liên tục?**

Bài này xây dựng một **đề xuất áp dụng Agile có thể thực thi và điều chỉnh theo bối cảnh**, thay vì một “công thức tổ chức” áp dụng mọi nơi. Chúng ta sẽ chọn mô hình phù hợp, phân quyền sản phẩm và kỹ thuật, thiết kế quy tắc trao đổi từ xa, đưa các thực hành Scrum, Kanban, XP vào một dòng giá trị chung, xây kế hoạch thử 90 ngày và dùng dữ liệu để quyết định mở rộng.

Nội dung thuộc chương **Thực hành tổng hợp** của module **AGILE_DEVELOPMENT**, kết nối các giá trị và nguyên tắc Agile với **user story, Product Backlog, Scrum, Kanban, Extreme Programming, đo flow và cải tiến dựa trên phản hồi**. Các con số, thời lượng và tên đội trong bài là **giả định phục vụ thực hành**, không phải chuẩn Scrum bắt buộc hoặc dữ liệu có thật của doanh nghiệp.

> **Định hướng:** Không tối ưu “số cuộc họp Agile”, “số story points” hay “mức bận của từng người”. Hãy tối ưu **khả năng một nhóm người phân tán cùng tạo ra giá trị được tích hợp, đáng tin và có thể kiểm chứng**, trong giới hạn an toàn và nhịp làm việc bền vững.

## 1. Kết quả học tập và sản phẩm thực hành

Sau bài học, người học có thể:

1. Chẩn đoán **phụ thuộc, điều kiện thời gian, ranh giới sản phẩm và chất lượng kỹ thuật** trước khi chọn cách phối hợp.
2. Phân biệt **một Scrum Team phân tán**, **nhiều Scrum Teams cùng một sản phẩm** và **nhiều sản phẩm liên kết bằng service contracts**.
3. Đề xuất **Product Goal, Product Backlog, trách nhiệm Product Owner, Sprint Goals, Increment và Definition of Done** đúng bối cảnh.
4. Soạn **working agreements từ xa**, kết hợp asynchronous communication, khoảng thời gian trao đổi trực tiếp, decision log và quy tắc escalation.
5. Thiết kế **user story mapping, vertical slicing, acceptance examples, refinement và prioritization** xuyên địa điểm.
6. Tổ chức **nhịp Scrum hoặc Kanban** giúp nhìn tiến triển, giới hạn WIP và phát hiện work items đang già đi.
7. Áp dụng **CI, test automation, API contracts, feature flags, observability, pairing và tích hợp sớm** để giảm sự phụ thuộc vào cuộc họp.
8. Thiết kế **kế hoạch phối hợp nhiều nhóm cho một Increment chung**, không nhân bản backlog và status reporting không cần thiết.
9. Lập **forecast và phương án ứng phó thay đổi, sự cố, nghỉ phép, phụ thuộc và chênh lệch múi giờ**.
10. Đề xuất **thước đo flow, chất lượng, kết quả người dùng và sức khỏe nhóm** cùng các giới hạn suy luận.
11. Xây **lộ trình thử nghiệm 30–60–90 ngày** với giả thuyết, owner, quality guardrails và điều kiện quyết định.
12. Trình bày, bảo vệ và điều chỉnh **một đề án áp dụng Agile** khi được giao tình huống phân tán hoặc nhiều nhóm cùng sản phẩm.

**Đầu ra kỳ vọng của bài thực hành:** một bản đề xuất có thể đem vào cuộc họp quyết định, gồm **bản đồ dòng giá trị, lựa chọn cấu trúc, Product Goal, cách vận hành backlog, working agreements, DoD, kế hoạch tích hợp, nhịp feedback, dashboard tối thiểu, rủi ro và lộ trình thử**.

## 2. Hai dạng phân tán cần xử lý khác nhau

**Nhóm phân tán (distributed team)** là một team có thành viên ở nhiều nơi hoặc nhiều múi giờ. **Nhiều nhóm cùng sản phẩm (multi-team single product)** là nhiều đội cùng đóng góp vào một sản phẩm hoặc Increment chung. Một tổ chức có thể gặp **cả hai** cùng lúc, nhưng vấn đề điều phối không hoàn toàn giống nhau.

| Khía cạnh | Một nhóm phân tán | Nhiều nhóm cùng sản phẩm | Khi đồng thời xảy ra |
| --- | --- | --- | --- |
| **Thách thức chính** | Thiếu ngữ cảnh chung, trao đổi bất đồng bộ, chênh thời gian | Phụ thuộc, tích hợp, ownership và ưu tiên chung | Chờ quyết định và hiểu sai interface dễ cộng dồn |
| **Định hướng** | Một mục tiêu và kế hoạch dễ truy cập cho mọi thành viên | Product Goal, Product Backlog, Product Owner và DoD chung khi là nhiều Scrum Teams trên một sản phẩm | Cần nguồn sự thật chung, không chỉ người ở văn phòng chính |
| **Nhịp feedback** | Kết hợp async với các phiên trao đổi đúng lúc | Feedback kỹ thuật và sản phẩm qua Increment tích hợp | Rút ngắn chờ giữa người và giữa service |
| **Rủi ro** | Quyết định qua DM, người vắng họp thiếu thông tin, quá tải ngoài giờ | Mỗi nhóm Done riêng, contract không tương thích, backlog chia cắt | Thông tin bị mất ở cả địa điểm và ranh giới nhóm |
| **Điểm bắt đầu** | Working agreements, tài liệu quyết định, công cụ hỗ trợ phối hợp | Xác định product boundary, ownership, integration, DoD | Chẩn đoán một dòng giá trị end-to-end |

### Ví dụ ba cấu hình

**Cấu hình A — Một Scrum Team phân tán:** Một Product Owner, một Scrum Master và Developers ở nhiều địa điểm cùng tạo một Increment. Không cần lập thêm “Scrum Team Việt Nam” và “Scrum Team từ xa” chỉ vì nơi làm việc khác nhau.

**Cấu hình B — Nhiều Scrum Teams cùng một sản phẩm:** Hai hoặc ba Scrum Teams cùng xây sản phẩm học tập với **một Product Goal, Product Backlog, Product Owner và Definition of Done chung**. Mỗi Scrum Team có thể có **Sprint Goal, Sprint Backlog và các sự kiện Scrum riêng**, nhưng tất cả Increment phải tích hợp được. Họ cần phối hợp các phụ thuộc phù hợp, không nhất thiết có một tầng “quản lý Scrum” mới.

**Cấu hình C — Nhiều sản phẩm có phụ thuộc:** Ứng dụng học tập, thanh toán và identity thực sự là các sản phẩm có vòng đời và ownership khác nhau. **Không áp một Product Backlog giả** cho tất cả chỉ vì API liên hệ; thay vào đó làm rõ product ownership, service contracts, ưu tiên liên sản phẩm và trách nhiệm vận hành.

**Bài này tập trung vào A và B**, đồng thời chỉ ra cách xử lý C khi xuất hiện. Chọn sai cấu hình sẽ kéo theo sai lệch trong trách nhiệm, backlog, DoD và quyền ra quyết định.

## 3. Chẩn đoán bối cảnh trước khi chọn framework

Một đề xuất tốt bắt đầu từ **vấn đề cần giải**, không từ “phải dùng Scrum, Kanban hay một mô hình mở rộng nào”. Dùng bốn góc nhìn:

1. **Người dùng và giá trị:** Ai cần sản phẩm làm được điều gì? Hành trình nào đang lỗi hoặc chậm?
2. **Dòng công việc:** Công việc đi qua những bước nào từ ý tưởng đến phản hồi? Thời gian chờ xuất hiện ở đâu?
3. **Con người và quyền quyết định:** Ai sở hữu mục tiêu, backlog, code, môi trường, dữ liệu và incident? Ai có thể đổi thứ tự hoặc dừng release?
4. **Kỹ thuật và phụ thuộc:** CI, contract tests, môi trường tích hợp, phiên bản API và monitoring đáng tin tới đâu?

### Bảng câu hỏi khảo sát ban đầu

| Nhóm câu hỏi | Câu hỏi cụ thể | Loại bằng chứng |
| --- | --- | --- |
| **Product** | Có Product Goal rõ không? Product Backlog chung hay mỗi đội giữ một bản? | Mô tả sản phẩm, lịch sử quyết định, PBIs thực tế |
| **Workflow** | Start/finish một story là gì? Các story chờ Review/Verify bao lâu? | Work item history, value-stream walkthrough |
| **Remote** | Quyết định ngoài cuộc họp được ghi ở đâu? Người vắng có thể phản biện khi nào? | Quan sát giao tiếp, phỏng vấn nhiều địa điểm |
| **Capacity** | Ai chịu incident, review, hỗ trợ, nghỉ phép và các request bất ngờ? | Lịch sử interruptions, on-call, WIP |
| **Integration** | Code tích hợp thường xuyên không? Consumer nào có thể bị phá contract? | CI events, contract tests, staging logs |
| **Security/data** | Ai xác nhận authorization và checkpoint correctness? | Tests, incident records, quy tắc domain |
| **Outcome** | Người học mở đúng bài, tiếp tục học và phản hồi ra sao? | Task analytics, usability observation, support |

### Đi theo một user story thật

Không chỉ hỏi “các team có họp không”; hãy chọn một story gần đây và ghi lại:

~~~text
Nhu cầu người học
  -> Làm rõ giả định và giá trị
  -> Product Backlog / chọn việc
  -> Developing
  -> API contract / Review
  -> Integration / Tests
  -> Increment đáp ứng DoD
  -> Rollout / Exposure
  -> Quan sát hành vi, lỗi và feedback
~~~

Với mỗi bước, ghi **owner, đầu ra, điều kiện hoàn tất, thời gian chủ động và thời gian chờ**. Phân biệt việc chờ do **không cùng giờ làm**, do **không rõ người quyết định**, do **hàng đợi chuyên môn**, và do **hệ thống kỹ thuật**. Những nguyên nhân khác nhau đòi biện pháp khác nhau.

### Đừng quy mọi vấn đề cho làm việc từ xa

Một môi trường staging liên tục hỏng vẫn hỏng khi mọi người ngồi cùng phòng. Ngược lại, thiếu ghi chép quyết định có thể ít lộ khi mọi người cùng địa điểm nhưng trở thành blocker lớn khi phân tán. Cần phân biệt **đặc tính hệ thống** với **tác động gia tăng của việc phân tán**.

## 4. Xác định tiêu chí thành công của đề án

Một chương trình có thể được gọi là “đã triển khai Agile” vì mọi người có bảng Sprint, 100% thành viên học Scrum hoặc số buổi họp tăng. Những số đó là **activity/output**, không phải **giá trị và năng lực thực**.

### Các lớp kết quả cần quan sát

| Lớp | Ví dụ | Có đủ chứng minh thành công không? |
| --- | --- | --- |
| **Activity** | Đào tạo thành viên, mở Daily Scrum online | Chưa |
| **Output** | Working agreement, backlog, contract document, CI template | Chưa |
| **Capability** | Người ở mọi địa điểm có thể làm rõ, tích hợp, kiểm thử và triển khai lát cắt an toàn | Đã là dấu hiệu năng lực, cần quan sát lặp lại |
| **Flow outcome** | Ít waiting/blocked age, cycle time ổn định hơn | Cần đối chiếu DoD, công việc và rủi ro |
| **Product outcome** | Học viên mở đúng bài nhanh và tin cậy hơn | Gần giá trị thực, vẫn cần phân khúc và bằng chứng |
| **Impact** | Học viên đạt mục tiêu học tập bền vững | Cần nghiên cứu dài hạn và kiểm soát yếu tố khác |

### Đề xuất một mục tiêu áp dụng Agile

> **Trong dòng giá trị phát triển tính năng Học tiếp**, chúng tôi muốn các Developers phân tán và những Scrum Teams cùng sản phẩm có thể **hoàn tất những lát cắt nhỏ đạt DoD và nhận phản hồi người học sớm hơn**, thông qua **Product Backlog chung, trao đổi bất đồng bộ có quyết định rõ, kiểm soát WIP và CI/contract tests**. Trong các vòng thử, chúng tôi sẽ xem **cycle time distribution, time-to-unblock, integration quality, task success và nhịp làm việc**; không được đánh đổi **phân quyền, tính đúng dữ liệu hay giấc ngủ và giờ nghỉ của người làm**.

Nếu **chưa có baseline**, bước đầu phải là xác minh định nghĩa và thu dữ liệu đủ đại diện. Không tự đặt “giảm 50% trong một Sprint” chỉ để đề án có KPI.

## 5. Chọn mô hình Agile bằng nhu cầu thực, không bằng khẩu hiệu

| Bối cảnh | Lựa chọn có thể phù hợp | Lý do | Cần cảnh giác |
| --- | --- | --- | --- |
| Một sản phẩm phức tạp, một Scrum Team phân tán có thể tạo Increment | **Scrum + XP + chính sách flow bổ sung** | Product Goal, Sprint Goal, kiểm tra/thích ứng; kỹ thuật tạo feedback | Biến Daily Scrum thành báo cáo cho manager |
| Nhiều Scrum Teams cùng một sản phẩm, integration thường xuyên | **Scrum với ownership sản phẩm và DoD chung + CI/contracts** | Chia PBIs và phối hợp để tạo Increment tích hợp | Mỗi team có backlog cạnh tranh hoặc gọi Done trước tích hợp |
| Nhóm platform/support nhận nhu cầu liên tục | **Kanban với explicit workflow, WIP và SLE** | Phù hợp pull, phân loại yêu cầu và flow feedback | Đánh đồng bảng Kanban với việc không cần ưu tiên |
| Có nhiều sản phẩm độc lập nhưng dùng chung một subsystem | **Product/service boundaries + contract/portfolio coordination** | Giữ ownership đúng sản phẩm, giảm handoff | Ép vào một Product Backlog chỉ vì có API |
| Codebase thay đổi khó, regression thường xuyên | **XP/CI/TDD/refactoring và quality automation** | Giảm chi phí thay đổi, hỗ trợ giao nhỏ | Chỉ thay quy trình họp mà bỏ nợ kỹ thuật |
| Nhu cầu phối hợp cấp portfolio có bằng chứng phức tạp | **Xem xét cơ chế mở rộng chính thức hoặc thiết kế nhẹ** | Có thể cần decision rights, lịch điều phối và quy tắc đầu tư | Chọn framework theo danh tiếng thay vì nút thắt |

### Quy trình lựa chọn trong sáu câu hỏi

1. Đang làm **một sản phẩm hay nhiều sản phẩm**?
2. Nhu cầu là **khám phá/phát triển phức tạp**, **dịch vụ liên tục** hay cả hai?
3. Team đã có năng lực **tạo Increment đạt chất lượng** đến đâu?
4. Những trở ngại nào **có thể sửa cục bộ**, trở ngại nào cần policy/owner cấp rộng?
5. Các thành viên có **khoảng làm việc trùng nhau** để trao đổi quyết định khó, và cách ghi quyết định cho người không tham dự là gì?
6. Chúng ta sẽ **đo cải thiện và dừng một cơ chế vô ích** bằng cách nào?

### Cấu trúc đề xuất mặc định để bắt đầu nhỏ

Với tình huống điển hình **hai Scrum Teams phân tán cùng sản phẩm học tập**, có thể bắt đầu với:

- **Một Product Goal, một Product Backlog, một Product Owner và một Definition of Done** cho sản phẩm.
- **Mỗi Scrum Team quản lý Sprint Goal, Sprint Backlog và cách tự tổ chức để tạo Increment**; không dùng “master Sprint Backlog” để chỉ huy từng task.
- **Một môi trường tích hợp và CI/contract tests**, để việc Done của mỗi nhóm có nghĩa trong Increment chung.
- **Working agreement từ xa**, gồm kênh cập nhật bất đồng bộ, thời điểm thảo luận trực tiếp và quyết định lưu ở nguồn chung.
- **Một bảng phụ thuộc tối thiểu** cho những việc thật sự chặn Increment.
- **Một vòng feedback sản phẩm** quan sát người học sau khi có lát cắt đủ chuẩn.
- **Một bộ số đo cân bằng và retrospective cải tiến** ở đúng phạm vi.

Đây là **đề xuất khởi điểm để kiểm chứng**, không phải mô hình bắt buộc. Nếu thực tế là một Scrum Team phân tán, giữ cấu trúc một team; nếu nhiều sản phẩm độc lập, không ép chung Product Backlog.

## 6. Thiết kế trách nhiệm sản phẩm khi có nhiều nhóm

Điều quan trọng nhất không phải ai chủ trì cuộc họp liên nhóm, mà là **ai có quyền chọn giá trị, ai bảo vệ Increment và ai xử lý phụ thuộc**.

### Một sản phẩm, nhiều Scrum Teams

Theo **Scrum Guide**, nhiều Scrum Teams làm cùng một sản phẩm phải chia sẻ **Product Goal, Product Backlog, Product Owner và Definition of Done**. Các team có thể có Sprint Goals và Sprint Backlogs khác nhau nhưng cần **tạo Increment tích hợp**. Không tự dựng một cấu trúc Product Owners độc lập tranh thứ tự cùng một sản phẩm chỉ vì số người tăng.

| Trách nhiệm | Nội dung | Rủi ro khi không rõ |
| --- | --- | --- |
| **Product Owner** | Tối đa hóa giá trị sản phẩm, chịu trách nhiệm hiệu quả Product Backlog, thứ tự và Product Goal | Hai team nhận ưu tiên mâu thuẫn, người dùng bị bỏ quên |
| **Developers của từng Scrum Team** | Tạo Increment đủ chất lượng, lập/điều chỉnh Sprint Backlog và phối hợp để đạt Sprint Goal | Story chỉ “xong phần tôi”, integration bị dồn |
| **Scrum Master** | Thiết lập Scrum theo Scrum Guide, hỗ trợ hiệu quả Scrum Team và tổ chức | Sự kiện trở thành báo cáo quản lý hoặc hình thức |
| **Owners kỹ thuật/service** | Ownership code, API contract, data, pipeline và incident theo ranh giới thực | Không ai có quyền sửa hoặc phục hồi service |
| **Platform/shared specialists** | Capability tự phục vụ, enablement hoặc review theo rủi ro | Mọi thay đổi chờ một người, khó dự báo |
| **Bên liên quan/người dùng** | Đưa bằng chứng nhu cầu, phản hồi Increment, thông tin ràng buộc | Product Backlog bị thay bằng danh sách mệnh lệnh |

**Scrum không quy định tất cả chức danh kỹ thuật ở bảng trên.** Các tên owner kỹ thuật/platform phản ánh nhu cầu vận hành thực tế; không được tạo các cấp quyền trái với accountability Scrum chỉ để có sơ đồ đẹp.

### Nhận diện ranh giới sản phẩm trước khi “dùng chung PO”

Hai service có API liên hệ **không mặc định là một sản phẩm**. Cần xem khách hàng, Product Goal, quyết định đầu tư, vòng đời và khả năng giao giá trị. Nếu là nhiều sản phẩm, mỗi sản phẩm có quyền ưu tiên phù hợp; quan hệ giữa chúng được điều phối bằng **service interface, contract và quyết định liên sản phẩm**.

### Khi một Product Owner bị quá tải

Product Owner có thể **ủy quyền công việc làm rõ, nghiên cứu, refinement hoặc phối hợp**, nhưng **vẫn chịu trách nhiệm về Product Backlog và tối đa hóa giá trị** trong bối cảnh Scrum. Nên tăng năng lực hỗ trợ sản phẩm, minh bạch quyền quyết định và giảm công việc hành chính; không tự nhân Product Owners theo số team rồi khiến Product Backlog phân mảnh.

## 7. Working agreement cho nhóm phân tán

Một nhóm phân tán cần thỏa thuận về **cách làm việc**, không chỉ “hãy online trên chat”. Working agreement là tập quy tắc **có thể thử và sửa**, giúp thông tin quan trọng không phụ thuộc người nào đang thức hoặc đang có mặt tại văn phòng.

### Mẫu thỏa thuận thực hành

| Chủ đề | Thỏa thuận đề xuất | Lý do và cách kiểm chứng |
| --- | --- | --- |
| **Nguồn sự thật** | Product Goal/Backlog, DoD, API contracts và quyết định quan trọng có nơi chung, quyền truy cập rõ | Người vắng họp vẫn thấy ngữ cảnh |
| **Trao đổi async** | Cập nhật có mục tiêu, ngữ cảnh, ảnh hưởng, câu hỏi/đề xuất, người cần quyết định và hạn hợp lý | Ít vòng hỏi lại và ít DM riêng |
| **Trao đổi đồng bộ** | Dùng cho bất định cao, tranh luận thiết kế, giải blocker hoặc incident; có agenda và kết luận | Không họp để đọc lại status |
| **Overlap window** | Chọn khoảng giờ làm việc trùng có tính đến múi giờ, xoay phiên nếu cần | Không mặc định một địa điểm phải họp ngoài giờ |
| **Thời gian phản hồi** | Kỳ vọng cho yêu cầu thường lệ theo class, không bắt trả lời tức thì 24/7 | Bảo vệ deep work, nghỉ phép và giấc ngủ |
| **Blocked items** | Ghi owner, nguyên nhân, bước tiếp; escalation khi age/rủi ro chạm ngưỡng đã thống nhất | Không để việc trôi trong chat |
| **Review và pairing** | PR nhỏ, reviewer rõ, phiên pairing có mục tiêu và timebox, chia sẻ kết luận | Feedback kỹ thuật sớm |
| **Quyết định** | Decision log ngắn: bối cảnh, lựa chọn, lý do, owner, ngày xem lại | Không lặp tranh luận sau mỗi lần bàn giao |
| **Incident** | Kênh riêng theo severity, on-call, handoff và quyền dừng rollout | Vấn đề an toàn không nằm trong queue thường lệ |
| **Nghỉ phép/bàn giao** | Có backup, tài liệu truy cập, owner service, không phụ thuộc một người | Khả năng tiếp diễn bền vững |

### Mẫu tin nhắn async đủ ngữ cảnh

~~~text
[DECISION NEEDED] Checkpoint khi học viên mở cùng khóa trên hai thiết bị

Mục tiêu: Lát cắt "Học tiếp" mở đúng bài, không mất tiến độ.
Hiện trạng: API dùng last-write-wins; mobile có thể gửi dữ liệu cũ.
Các lựa chọn:
  A. Giữ phiên bản cập nhật mới nhất theo quy tắc version/timestamp được xác nhận.
  B. Dùng so sánh version và xử lý conflict rõ ràng.
Tác động: Contract API, data migration, UI failure state.
Cần ý kiến: Product/domain owner + API/data owners.
Mốc xem lại: Trước khi consumer contract được chốt cho vòng tích hợp.
Nếu chưa đủ thông tin: đề xuất workshop ngắn có kết luận lưu lại.
Tài liệu: [liên kết đến nguồn quyết định chung trong hệ thống dự án].
~~~

Mẫu trên **không chứa token, dữ liệu người dùng thật hoặc bí mật**. Một tin nhắn “API lỗi, ai xem?” dễ kéo dài nhiều vòng; thông tin đầy đủ giúp người ở múi giờ khác có thể phản hồi khi bắt đầu ngày làm việc.

### Tách khẩn cấp và không khẩn cấp

**Standard request** có thể phản hồi trong khung giờ làm việc theo chính sách. **Incident mất dữ liệu hoặc lộ quyền** phải qua on-call/severity policy; không đợi người nhận chat thức dậy. Quy ước phải nói rõ **ai được phép kích hoạt sự cố, kênh nào và khi nào dừng rollout**.

## 8. Bất đồng bộ trước, đồng bộ khi quyết định thực sự cần

Làm việc phân tán không có nghĩa **mọi tương tác đều async**, cũng không phải “chỉ có video call mới là cộng tác”. Cần chọn phương thức theo **độ bất định, mức khẩn, độ khó của quyết định và mức độ phụ thuộc**.

| Tình huống | Ưu tiên đề xuất | Vì sao? |
| --- | --- | --- |
| Cập nhật kết quả test, PR, dependency status | **Async, liên kết nguồn** | Có thể tra cứu và phản hồi theo giờ làm |
| Góp ý một đề xuất kỹ thuật đủ rõ | **Async review có owner và mốc phản hồi** | Tạo dấu vết và cho phép đọc kỹ |
| Các bên chưa thống nhất ý nghĩa nghiệp vụ | **Workshop trực tiếp ngắn**, sau đó ghi quyết định | Tránh hàng chục lượt nhắn không giải quyết vấn đề |
| Product Owner và Developers thương lượng scope trong Sprint | **Trao đổi đồng bộ khi cần** và cập nhật backlog | Mục tiêu, rủi ro, trade-off cần rõ |
| Incident production có ảnh hưởng đáng kể | **Kênh incident đồng bộ theo policy** | Cần phối hợp nhanh và trách nhiệm rõ |
| Chia sẻ kiến thức lặp lại | **Docs, examples, pairing có timebox** | Vừa giúp tự chủ vừa tránh họp vô hạn |

### Khung giao tiếp để tránh “24 giờ chờ mỗi câu hỏi”

~~~mermaid
flowchart TD
    A["Có một câu hỏi / phụ thuộc"] --> B{"Khẩn hoặc rủi ro<br/>người dùng?"}
    B -->|Có| C["Incident/escalation<br/>theo severity policy"]
    B -->|Không| D{"Ngữ cảnh và<br/>lựa chọn đã rõ?"}
    D -->|Có| E["Async proposal/review<br/>có owner và mốc xem lại"]
    D -->|Không| F["Phiên collaboration ngắn<br/>trong giờ phù hợp"]
    E --> G{"Quyết định xong?"}
    F --> G
    G -->|Chưa| H["Làm rõ blocker,<br/>owner hoặc escalation"]
    G -->|Rồi| I["Decision log + contract<br/>+ cập nhật backlog/tests"]
    H --> E
~~~

Không dùng “async-first” để ép những vấn đề phức tạp vào văn bản dài vô tận. Cũng không dùng “cần trao đổi nhanh” để bắt mọi người luôn sẵn sàng ngoài giờ.

## 9. Đề xuất nhịp Scrum cho một nhóm phân tán

Trong Scrum, Sprint có độ dài **một tháng hoặc ngắn hơn**, cung cấp nhịp kiểm tra/thích ứng. Nhóm phân tán có thể giữ mục đích của các sự kiện Scrum nhưng **chuẩn bị thông tin bất đồng bộ để thời gian trực tiếp tập trung vào quyết định**.

| Sự kiện/hoạt động | Mục đích theo Scrum | Cách vận hành từ xa đề xuất | Dấu hiệu hình thức |
| --- | --- | --- | --- |
| **Sprint Planning** | Tại sao Sprint có giá trị; chọn PBIs phù hợp và kế hoạch thực hiện | Product Goal, thứ tự backlog, rủi ro và capacity được chia sẻ trước; phiên chính dành cho Why/What/How | Giao task theo người rồi bắt hứa story points |
| **Daily Scrum** | Developers kiểm tra tiến triển tới Sprint Goal và điều chỉnh Sprint Backlog | Kết hợp bảng tiến độ async với cuộc trao đổi Developers đúng thời điểm; vẫn là sự kiện 15 phút trong Scrum | Báo cáo “hôm qua/hôm nay” cho manager mà không đổi kế hoạch |
| **Sprint Review** | Kiểm tra Increment và môi trường, hợp tác với stakeholders để quyết định hướng tiếp | Gửi bản demo/video/tài liệu trước, trao đổi trực tiếp về outcome và Product Backlog | Chỉ đọc slide hoặc tổng điểm Done |
| **Sprint Retrospective** | Kiểm tra cách làm việc và lên kế hoạch nâng chất lượng/hiệu quả | Thu phản hồi trước theo cách an toàn; phiên chính chọn một cải tiến cụ thể có owner/metric | Hứa “cố giao nhanh hơn” lặp lại |
| **Product Backlog refinement** | Làm rõ/chia nhỏ/sắp các PBIs để đủ hiểu khi chọn | Async comments + phiên trao đổi ngắn các trường hợp phức tạp | Lập kế hoạch chi tiết mọi feature nhiều tháng hoặc không refinement |

**Lưu ý:** Scrum Guide quy định các Scrum events và timeboxes tương ứng; chuẩn bị async **không có nghĩa có thể tuyên bố “chúng tôi làm Scrum” nhưng bỏ sự kiện bắt buộc**. Nếu tổ chức chọn mô hình không Scrum, có thể sử dụng nhịp và chính sách phù hợp theo Kanban hoặc cách làm khác; cần gọi đúng bản chất thay vì duy trì tên hình thức.

### Một Sprint hai tuần minh họa

| Thời điểm | Việc quan trọng | Kết quả cần có |
| --- | --- | --- |
| **Trước Sprint** | Refinement thích hợp, ghi dependency, hiểu guardrails và năng lực | PBIs có thể thảo luận dựa trên ví dụ |
| **Đầu Sprint** | Sprint Planning cùng những người cần thiết | Sprint Goal, PBIs được chọn, Sprint Backlog khởi đầu |
| **Hằng ngày** | Developers điều chỉnh kế hoạch tới Sprint Goal, ghi blockers | Quyết định giúp việc tới Done, không chỉ status |
| **Trong Sprint** | CI, review, pairing, integration, tests và product discovery | Increment ngày càng tích hợp, ít surprise |
| **Cuối hoặc sớm hơn nếu phù hợp** | Hoàn thành Increment đạt DoD, cho người dùng thử theo policy | Bằng chứng kỹ thuật/sản phẩm, rollout an toàn |
| **Sprint Review + Retro** | Kiểm tra Increment, backlog và hiệu quả cách làm | Hướng sản phẩm cập nhật; thí nghiệm cải tiến tiếp theo |

**Không buộc một Increment đã đạt DoD phải đợi Sprint Review mới được phát hành.** Ngược lại, cũng không gọi một bản demo chưa kiểm tra quyền hoặc chưa tích hợp là Done chỉ vì đã đến lịch Review.

### Chênh lệch múi giờ và sự kiện

Nếu thành viên ở các múi giờ không có overlap bền vững, cần xem **sự phù hợp của cấu trúc team và nhịp phối hợp**, có thể xoay phiên giờ họp hoặc chia trách nhiệm theo khả năng cộng tác thực. Không yêu cầu một người họp đêm thường xuyên chỉ để giữ lịch thuận tiện cho số đông. Một cuộc họp “ngắn” cũng gây hại nếu bắt đầu vào giờ nghỉ cố định của người khác.

## 10. Nhiều Scrum Teams cùng sản phẩm: một mục tiêu và Increment tích hợp

**Cùng sản phẩm** đòi kết nối giá trị, không chỉ cùng lịch. Khi nhiều Scrum Teams tham gia, có thể thiết kế **một dòng Product Backlog được làm rõ và sắp thứ tự**, còn các team tự chọn cách góp phần vào Product Goal.

### Phân biệt cái gì chung và cái gì riêng

| Thành phần | Nhiều Scrum Teams trên một sản phẩm |
| --- | --- |
| **Product Goal** | **Chung**: cùng trạng thái tương lai mong muốn |
| **Product Backlog** | **Chung**: một danh sách công việc được sắp thứ tự cho sản phẩm |
| **Product Owner** | **Chung**: một accountability tối đa hóa giá trị |
| **Definition of Done** | **Chung**: mọi Increment phải đáp ứng cùng tiêu chuẩn chất lượng |
| **Sprint Goal** | Mỗi Scrum Team hình thành Sprint Goal thích hợp trong Sprint Planning của team; cần tránh mục tiêu mâu thuẫn |
| **Sprint Backlog** | Mỗi Scrum Team có Sprint Backlog do Developers quản lý, điều chỉnh khi học thêm |
| **Scrum events** | Mỗi Scrum Team thực hiện events; trao đổi liên nhóm bổ sung khi phụ thuộc thật đòi hỏi |
| **Increment** | Công việc từ nhiều team phải tích hợp thành Increment hữu ích, không ghép “Done riêng lẻ” trên giấy |

### Hai cách chia công việc để so sánh

**Phương án chia theo lớp kỹ thuật:** Team A làm toàn bộ UI, Team B toàn bộ API; cả hai báo Sprint Done khi code merge. Sản phẩm chỉ chạy được sau khi tích hợp ở vòng sau.

**Phương án hướng lát cắt giá trị:** Team A hoặc B (với hỗ trợ ranh giới chuyên môn phù hợp) nhận một tập PBIs cho phép người học đủ quyền mở lại bài trên web; tập khác giải quyết trường hợp mobile/checkpoint lỗi; các shared services cung cấp **hợp đồng và năng lực cần thiết**. Mọi phần tích hợp sớm và đạt DoD chung trước khi gọi là Done.

Không phải lúc nào mỗi Scrum Team cũng có thể làm full-stack mọi subsystem. **Cross-functional** cần được hiểu là **khả năng tạo giá trị tổng thể của Scrum Team và tổ chức nhiều nhóm theo boundaries phù hợp**, không phải bắt mọi thành viên trở thành chuyên gia mọi thứ. Các phụ thuộc thật cần được làm rõ để không có hàng đợi ẩn.

### Cách đồng bộ liên nhóm vừa đủ

Một trao đổi liên nhóm ngắn có thể cần trong những thời điểm:

- Chốt **API contract** hoặc thay quy tắc nghiệp vụ ảnh hưởng consumer.
- Có **dependency blocked** không thể giải trong một Scrum Team.
- Thay **schema/migration/rollout** cần owner ở nhiều dịch vụ.
- Có quyết định chung về **Definition of Done, integration environment hoặc incident**.

Đầu ra là **quyết định, owner, điều kiện kiểm chứng và mốc tiếp theo**, không phải bản tổng hợp “team A 80% – team B 70%”. Nếu hợp đồng và automated tests làm thay được một phần đồng bộ, hãy giảm cuộc họp tương ứng.

## 11. Kanban cho công việc liên tục và nút thắt nhiều nhóm

Ngay cả khi Scrum Teams dùng Sprint, một số dòng việc như **platform support, triage, security consultations và production incidents** thường có nhu cầu liên tục. **Kanban** có thể giúp định nghĩa và cải tiến workflow, không buộc mọi yêu cầu phải nằm trong Sprint của nhóm sản phẩm.

### Một workflow dịch vụ chung

~~~text
Incoming → Triage / Accepted → Working → Verify → Resolved
                             │
                             └── Blocked: owner + lý do + next action

Policies đề xuất:
  Standard: có điều kiện tiếp nhận và SLE dựa trên lịch sử.
  Fixed-date: chỉ dành cho mốc có căn cứ, lập kế hoạch sớm.
  Expedite: incident/rủi ro nghiêm trọng theo severity policy.
  Enablement: pairing/coaching có mục tiêu chuyển giao năng lực.
  Capability: đầu tư self-service, không lẫn support ticket đơn lẻ.
~~~

Đặt tên class of service là **lựa chọn chính sách**, không bắt buộc dùng đúng năm lớp trên. Mục tiêu là để những người yêu cầu hiểu **đường vào, mức ưu tiên, người chịu trách nhiệm và thời điểm cần escalation**.

### Flow metrics quan trọng

| Metric | Định nghĩa đúng | Câu hỏi hành động |
| --- | --- | --- |
| **WIP** | Số work items đang làm, chưa hoàn tất | Có quá nhiều việc cùng tranh reviewer/specialist? |
| **Throughput** | Số work items hoàn tất theo một cửa sổ | Có thể dự báo nhu cầu và năng lực bằng dữ liệu thực? |
| **Work item age** | Tuổi của item đang dở theo start đã định | Item nào sắp bị tắc cần xử lý hôm nay? |
| **Cycle time** | Thời gian từ start tới finish của item đã Done | Phân bố thời gian phục vụ có phù hợp kỳ vọng? |
| **Blocked/wait time** | Khoảng chờ theo policy bổ sung | Nút thắt nằm ở phụ thuộc nào? |

### SLE không phải lời hứa deadline cho mọi request

Giả sử một luồng tư vấn thường lệ có **Service Level Expectation: 85% request đủ điều kiện hoàn tất trong tối đa bốn ngày làm việc** (chỉ là ví dụ). Điều này không bảo đảm 100% request xong ngày thứ tư; tuổi item tăng gần kỳ vọng giúp người phụ trách **kiểm tra blocker, năng lực và bước tiếp**. Incident có chính sách riêng; không để lộ dữ liệu đợi hàng standard.

### Kanban xuyên nhóm không đồng nghĩa một siêu bảng

Không nhân bản mọi task của các team vào một board khổng lồ. Có thể quản lý **dependency tickets** liên kết tới PBIs gốc, ghi **requester, provider, việc cần xác nhận, rủi ro, owner, mốc xem lại**. Nếu một API contract không còn là phụ thuộc sau khi đã ổn định và có tests, đóng dependency; không tiếp tục duy trì cuộc họp vĩnh viễn.

## 12. User story mapping và Product Backlog chung

Khi phân tán, việc chỉ chia nhiệm vụ qua chat dễ tạo **các mảnh chức năng riêng lẻ**, không có hành trình người dùng xuyên suốt. **User story mapping** giúp mọi người cùng nhìn dòng tác vụ và chọn các lát cắt nhỏ có giá trị.

### Hành trình Học tiếp

~~~text
Người học
  → Truy cập khóa học
  → Nhìn thấy điểm tiếp tục
  → Chọn Học tiếp
  → Mở bài đúng quyền
  → Khôi phục tiến độ
  → Xác nhận đã tiếp tục học

Release thử 1:
  Một người có quyền, một checkpoint hợp lệ, mở đúng bài.

Release thử 2:
  Không có checkpoint, bài bị xóa, quyền hết hạn, lỗi lưu.

Release thử 3:
  Nhiều thiết bị, checkpoint xung đột, cải tiến trải nghiệm.
~~~

**Quan trọng:** Các lát cắt đầu có thể nhỏ về **phạm vi nghiệp vụ**, nhưng **không được hoãn các kiểm tra an toàn dữ liệu và phân quyền bắt buộc** đến Release 2/3. Với mỗi lát cắt, DoD phải bảo vệ trường hợp sai quyền và trạng thái lỗi phù hợp. Các số thứ tự release chỉ là phương án minh họa, cần khám phá người dùng và rủi ro thật.

### Một số Product Backlog Items mẫu

| Thứ tự giả định | User story / công việc | Giá trị/rủi ro | Acceptance evidence |
| --- | --- | --- | --- |
| 1 | Là học viên đủ quyền, tôi muốn mở bài đang dở từ trang khóa học | Giảm thao tác tìm bài | Luồng E2E đúng bài, đúng quyền, test được |
| 2 | Là học viên không có checkpoint, tôi cần hành vi bắt đầu hợp lệ | Tránh trạng thái trống/nhầm lẫn | UI/API xử lý trường hợp chưa có |
| 3 | Là học viên, tôi cần biết lưu tiến độ thành công hay thất bại | Tránh tin nhầm dữ liệu đã lưu | Chỉ hiển thị thành công sau xác nhận |
| 4 | Là học viên, tôi không muốn checkpoint trên thiết bị cũ ghi đè sai tiến độ | Tính đúng dữ liệu nhiều thiết bị | Quy tắc conflict/version và tests |
| 5 | Nhóm cần observability phù hợp cho luồng checkpoint | Khả năng phát hiện/khôi phục lỗi | Logs/metrics an toàn, alert và owner |
| 6 | Nghiên cứu khả năng thấy nút Học tiếp trên mobile | Kiểm chứng giả thuyết UX | Kịch bản quan sát, quyết định từ feedback |

Backlog có thể chứa **công việc kỹ thuật, nghiên cứu và giảm rủi ro**, không chỉ user stories theo khuôn “Là..., tôi muốn...”. Product Owner chịu trách nhiệm thứ tự dựa trên **giá trị, rủi ro, phụ thuộc và học hỏi**, còn Developers tham gia làm rõ khả thi và chất lượng.

### Refinement khi mọi người không cùng chỗ

1. Product Owner chia sẻ **problem statement, outcome và một số ví dụ** trước.
2. Developers và stakeholders để lại **câu hỏi, giả định và phụ thuộc** theo async.
3. Các trường hợp không thống nhất được đưa vào **phiên refinement ngắn**.
4. Lát cắt được **chia tới mức có thể kiểm tra end-to-end** với DoD.
5. Những điểm chưa rõ/ngoại lệ được ghi vào backlog hoặc risk log, không bị chôn trong chat.

Refinement là hoạt động **liên tục**, không cần mỗi team họp dài theo lịch cứng cho tất cả PBIs. Nhưng “async” không có nghĩa **bỏ cơ hội cùng hiểu nghiệp vụ**.

## 13. Acceptance examples và hợp đồng API giảm hiểu nhầm từ xa

Ví dụ cụ thể thường dễ được các địa điểm cùng hiểu hơn một mô tả mơ hồ kiểu “Học tiếp hoạt động tốt”.

### Kịch bản hành vi minh họa

~~~gherkin
Feature: Tiếp tục một khóa học đúng tiến độ và quyền

  Scenario: Người học còn quyền mở checkpoint hợp lệ
    Given học viên A còn quyền vào khóa K
      And checkpoint của A là bài B ở vị trí 120 giây
    When A chọn Học tiếp ở khóa K
    Then ứng dụng mở đúng bài B
      And phục hồi vị trí đã xác nhận theo quy tắc

  Scenario: Không tiết lộ checkpoint thuộc tài khoản khác
    Given checkpoint C thuộc học viên A
      And học viên B không được quyền truy cập C
    When B yêu cầu checkpoint C qua API
    Then API từ chối theo quy tắc phân quyền
      And không trả thông tin tiến độ của A

  Scenario: Lưu tiến độ thất bại
    Given học viên A đang ở bài B
    When request lưu checkpoint không được server xác nhận
    Then giao diện không nói "Đã lưu thành công"
      And có phản hồi lỗi phù hợp để người học quyết định tiếp
~~~

Kịch bản là **đề xuất để các bên xác nhận**, không thay chính sách domain/security thực. Một quy tắc như “checkpoint nào thắng khi hai thiết bị cập nhật” cần Product Owner và các chuyên gia liên quan quyết định rõ trước khi viết tests.

### Bảng trách nhiệm hợp đồng producer–consumer

| Khía cạnh | API producer cần xác nhận | Consumer cần xác nhận |
| --- | --- | --- |
| **Schema và version** | Các trường, optional/required, deprecation | Trường thực dùng, fallback khi thiếu |
| **Semantics** | Vị trí bài, timestamp, trạng thái hoàn thành | UI diễn giải “Học tiếp” thế nào |
| **Authorization** | Kiểm tra quyền tại server và resource | Gửi identity đúng, không suy quyền từ UI |
| **Error** | Lỗi bị từ chối, conflict, unavailable | Không hiển thị thành công giả, retry phù hợp |
| **Consistency** | Khi nào một checkpoint được xác nhận lưu | Điều kiện hiển thị trạng thái “Đã lưu” |
| **Compatibility** | Old/new consumers, migration plan | Kế hoạch cập nhật web/mobile và job nền |
| **Observability** | Request ID, trace và log an toàn | Cách chẩn đoán lỗi E2E không lộ dữ liệu |

### Contract tests không thay trao đổi nghiệp vụ

Khi đã thống nhất kỳ vọng, **automated contract/API tests** giúp phát hiện sớm thay đổi phá consumer. Nhưng nếu kỳ vọng ban đầu sai, tests vẫn có thể xanh. Vì vậy, người phân tán cần **kết nối ví dụ nghiệp vụ, hợp đồng và điều kiện quality**, chứ không chỉ một file JSON/OpenAPI.

## 14. Definition of Done và khả năng tích hợp liên tục

Một sai lầm nghiêm trọng khi nhiều nhóm cùng sản phẩm là **mỗi nhóm có định nghĩa Done khác nhau**: UI Done khi merge, API Done khi unit test xanh, QA Done sau tuần sau. Khi đó sản phẩm chung **chưa có Increment đáng tin**, dù mọi dashboard đều báo hoàn tất.

### Đề xuất các điều kiện chất lượng chung

Một **Definition of Done phù hợp bối cảnh sản phẩm** có thể yêu cầu:

- Thay đổi đã được **tích hợp và hoạt động cùng phần liên quan** của sản phẩm.
- **Acceptance examples** quan trọng được xác nhận, có bằng chứng kiểm thử thích hợp.
- **Unit, API, contract, integration checks** liên quan chạy đạt và không bị bỏ qua trái policy.
- Không lộ dữ liệu người khác; authorization, secrets và logging **đáp ứng tiêu chuẩn an toàn**.
- Thay đổi dữ liệu có **migration/compatibility** và kế hoạch giám sát/khôi phục phù hợp.
- Có thể **deploy artifact đã kiểm chứng** theo chính sách, và biết tác động khi bật exposure.
- Monitoring, alerts, ownership, documentation/runbook **đủ cho mức rủi ro**.
- Không còn lỗi nghiêm trọng chặn mục tiêu hoặc nghĩa vụ bắt buộc.

Đây là **gợi ý để nhóm cùng xác lập DoD**, không phải danh sách Scrum Guide bắt buộc từng bullet. DoD theo tiêu chuẩn tổ chức nếu có; khi nhiều Scrum Teams cùng sản phẩm, **phải dùng một DoD chung**. Những yêu cầu bổ sung theo PBI hoặc release cũng cần được thể hiện minh bạch.

### Phân biệt build, deploy, release và outcome

~~~mermaid
flowchart LR
    A["Small change + tests"] --> B["CI feedback"]
    B --> C["Artifact có định danh"]
    C --> D["Increment đạt DoD"]
    D --> E["Deploy theo policy"]
    E --> F["Release / exposure<br/>theo quyết định sản phẩm"]
    F --> G["Quan sát hành vi<br/>và business guardrails"]
    G --> H["Backlog và lựa chọn<br/>được điều chỉnh"]
~~~

**Deploy không tự bằng release** nếu dùng feature flag. **Release không tự bằng outcome** khi người học chưa thấy hoặc chưa sử dụng được giải pháp. Một nhóm từ xa nên công bố rõ **từng mốc** để stakeholders không hiểu nhầm “code merged” là “khách hàng đã được hưởng lợi”.

### Rủi ro kiểm thử “chạy xanh” nhưng sai

Không tối ưu số tests hoặc coverage thuần túy. Một pipeline có tests **flaky, giả định nghiệp vụ sai, hoặc bỏ qua trường hợp phân quyền** vẫn có thể phát hành lỗi. Chọn test strategy theo rủi ro và kiểm tra độ tin cậy của pipeline, đặc biệt khi các team ở nhiều nơi không thể cùng debug ngay.

## 15. XP và thực hành kỹ thuật giảm chi phí phối hợp

**Extreme Programming** giúp các thành viên và team phân tán **nhận phản hồi kỹ thuật sớm, chia sẻ kiến thức và thay đổi nhỏ**. Điều này không xóa nhu cầu trao đổi nghiệp vụ, nhưng giảm số lần phải họp chỉ để tìm hiểu “vì sao tích hợp hỏng”.

| Thực hành XP/kỹ thuật | Áp dụng cho team phân tán | Bằng chứng cần xem |
| --- | --- | --- |
| **Continuous Integration** | Thay đổi nhỏ tích hợp thường xuyên, CI trả feedback rõ | Time-to-green, build reliability, contract failures |
| **TDD/test-first** | Cùng xác nhận ví dụ rồi viết checks để bảo vệ hành vi | Lỗi hồi quy, rework và chất lượng thay đổi |
| **Pair programming** | Pairing remote có mục tiêu, luân phiên người dẫn và thời hạn | Chuyển giao kiến thức, ít single point of failure |
| **Refactoring** | Cải thiện thiết kế có tests bảo vệ, cập nhật contract khi cần | Code dễ sửa và ít phá consumer |
| **Simple design** | Ranh giới service/interface rõ, tránh cấu trúc quá phức tạp | Ít handoff, cognitive load hợp lý |
| **Small releases** | Lát cắt nhỏ và progressive rollout theo policy | Time-to-feedback, sự cố và khả năng khôi phục |
| **Collective ownership phù hợp** | Cùng trách nhiệm code theo quyền và chuyên môn rõ | Ít chờ reviewer duy nhất, chất lượng ổn |

### Remote pairing không phải call mở cả ngày

Một phiên pairing tốt có **vấn đề cụ thể, thời lượng vừa đủ, quyền truy cập, test kỳ vọng và quyết định sau phiên**. Ví dụ security specialist cùng một Developer xây test sai quyền trên API checkpoint; sau đó nhóm có thể tự xử lý ca thường lệ. Không đòi mọi thành viên bật camera/micro liên tục hoặc chia sẻ desktop ngoài giờ.

### Chia sẻ tri thức qua artifact

Cuối phiên kỹ thuật quan trọng, để lại **test, contract, ADR/decision note hoặc runbook**. Video ghi hình có thể hỗ trợ khi được phép, nhưng **không thay tài liệu tra cứu ngắn và có phiên bản**. Với dữ liệu cá nhân hoặc bí mật kỹ thuật, phải tuân thủ quy định truy cập/ghi hình.

## 16. Thiết kế pipeline chung cho Increment từ nhiều nhóm

Một CI pipeline tốt giúp team phát hiện **integration breaks** theo nhịp nhanh hơn lịch họp. Mỗi service có thể có pipeline riêng, nhưng cần các điểm kiểm chứng **producer–consumer và end-to-end** khi thay đổi giao nhau.

~~~mermaid
flowchart TD
    A["Team A: UI/consumer"] --> C["Checks mỗi thay đổi<br/>unit + API consumer"]
    B["Team B: checkpoint/API"] --> D["Checks mỗi thay đổi<br/>unit + provider contract + auth"]
    C --> E["Versioned artifacts"]
    D --> E
    E --> F["Integration environment<br/>và cross-service checks"]
    F --> G{"DoD, security,<br/>compatibility đạt?"}
    G -->|Chưa| H["Owner xử lý, feedback<br/>qua CI/board ngay"]
    H --> C
    G -->|Đạt| I["Deploy/rollout có kiểm soát"]
    I --> J["Health + task outcome<br/>+ feedback"]
~~~

### Các nguyên tắc thiết kế

1. **Không chờ cuối Sprint mới tích hợp.** Phát hiện contract/data mismatch ngay khi có thay đổi liên quan.
2. **Một nguồn artifact đáng tin:** biết phiên bản nào đã kiểm chứng, cấu hình/secrets theo môi trường.
3. **Có ownership khi pipeline đỏ:** pipeline không được ở trạng thái “không ai chịu” giữa hai múi giờ.
4. **Tách quality gates kỹ thuật khỏi exposure:** có thể deploy bản đã kiểm chứng nhưng chưa bật cho người dùng.
5. **Progressive delivery theo rủi ro:** canary/flag/rollback nếu phù hợp, không dùng flag để che vi phạm DoD.
6. **Bảo vệ dữ liệu khi migration:** rollback code không tự hoàn tác dữ liệu bị sửa hoặc xóa; cần kế hoạch bảo vệ/khôi phục riêng.
7. **Không phụ thuộc một cá nhân:** pipeline và hướng xử lý lỗi có tài liệu, quyền dự phòng và support.

### Kế hoạch compatibility khi đổi schema

~~~text
Expand:
  Thêm schema/contract mới, giữ consumers cũ còn hoạt động.

Migrate:
  Backfill hoặc chuyển dữ liệu an toàn có kiểm tra,
  hỗ trợ old/new consumer theo kế hoạch.

Contract:
  Chỉ bỏ interface/schema cũ khi đã xác nhận
  consumers không còn phụ thuộc và có bằng chứng tương thích.

Guardrails:
  Quyền truy cập, tính đúng tiến độ, telemetry,
  khôi phục dữ liệu, người có quyền dừng rollout.
~~~

Đặc biệt với ứng dụng mobile có người dùng offline hoặc phiên bản cũ, **đừng xóa hợp đồng cũ chỉ vì các team phát triển đã merge code mới**.

## 17. Dự báo, capacity và mục tiêu của các team phân tán

Phân tán làm tăng nhu cầu **minh bạch về năng lực thực và phụ thuộc**, không có nghĩa tổ chức phải hứa ngày hoàn tất chính xác khi còn bất định.

### Tránh nhầm bốn khái niệm

| Khái niệm | Định nghĩa làm việc | Ví dụ |
| --- | --- | --- |
| **Product Goal** | Trạng thái tương lai muốn đạt cho sản phẩm | Học viên tiếp tục học đúng vị trí và tin cậy |
| **Sprint Goal** | Mục tiêu duy nhất cho Sprint của Scrum Team | Có lát cắt Học tiếp an toàn cho người đủ quyền |
| **Forecast** | Dự báo dựa trên bằng chứng, biến thiên và giả định | Tập PBIs đã hiểu có xác suất hoàn tất trong khoảng tuần nhất định |
| **Hard constraint** | Điều kiện không được vi phạm | Quy định phân quyền, migration an toàn, mốc bắt buộc theo hợp đồng |

**Target và forecast không tương đương commitment bất chấp điều kiện.** Một team chịu trách nhiệm minh bạch tiến triển và điều chỉnh kế hoạch; người quản lý cần hỗ trợ trade-off khi phụ thuộc hoặc capacity thay đổi.

### Capacity thực khác số người trên sơ đồ

Một team có 6 Developers nhưng:

- Một người trực incident theo lịch.
- Một người nghỉ phép trong Sprint.
- Hai người hỗ trợ review của service dùng chung.
- Một số thành viên không có khung giờ overlap đủ lâu cho thảo luận phức tạp.

Không thể lấy **6 × số ngày làm việc** làm thời gian viết feature không gián đoạn. Capacity cần bao gồm review, kiểm thử, khắc phục sự cố, học kỹ năng và thời gian trao đổi thiết yếu. Không đặt một tỷ lệ “luôn phải lên lịch 100%” rồi dùng tăng ca bù.

### Dự báo dựa trên throughput minh họa

Giả sử một workflow có số feature PBIs cùng loại đã Done trong sáu tuần:

~~~text
Tuần:       1  2  3  4  5  6
Completed:  3  5  4  2  5  5
~~~

Throughput trung bình là:

\[
\frac{3+5+4+2+5+5}{6}=4\text{ PBIs/tuần}.
\]

Nếu còn 12 PBIs **thực sự tương đồng về ranh giới và mức độ rủi ro**, phép chia thô là **3 tuần**. **Không phải lời hứa hoàn tất chắc chắn sau ba tuần**: năng lực có thể thay đổi do nghỉ phép, incident, phụ thuộc hoặc loại việc. Với quyết định quan trọng, có thể dùng **phân bố throughput lịch sử và mô phỏng Monte Carlo** để đưa ra khoảng có xác suất, ghi rõ mẫu, loại việc và assumptions.

### Khi các team cùng sản phẩm có lịch Sprint khác nhau

Không bắt buộc tất cả Scrum Teams phải có Sprint start/end trùng nhau để được xem là cùng sản phẩm. Nhưng họ phải **phối hợp integration, Product Goal và DoD**. Một đề xuất vận hành có thể thống nhất **nhịp xem Increment hoặc cửa sổ phụ thuộc chung** nếu điều đó giảm chờ thật; chỉ đồng bộ lịch khi lợi ích cao hơn chi phí thay đổi cách làm.

### Khi nhiều request chen ngang

Nếu một incident nghiêm trọng chiếm một số Developers trong Sprint, cần **cập nhật Sprint Backlog, xem ảnh hưởng Sprint Goal, thông báo phụ thuộc và điều chỉnh forecast**. Không hứa cùng khối lượng như khi không có sự cố, cũng không cắt quality gates để làm đẹp biểu đồ.

## 18. Đo flow, chất lượng, giá trị và sức khỏe thay vì giám sát con người

Với team phân tán, đo mức “online”, thời gian mở camera hoặc số message dễ dẫn tới giám sát xâm lấn nhưng **không nói lên hiệu quả phần mềm**. Cần bộ chỉ số phản ánh **dòng công việc và kết quả**, với định nghĩa phù hợp.

### Dashboard tối thiểu đề xuất

| Câu hỏi | Metric/quan sát | Cần đối chiếu |
| --- | --- | --- |
| **Giá trị người dùng có đến sớm hơn?** | Time-to-testable-slice, task success Học tiếp, phản hồi | Exposure, cohort, trường hợp sai quyền |
| **Work items có tới Done ổn định?** | Cycle time distribution, throughput theo loại việc | Work item size/mix, DoD, số lượng mẫu |
| **Có blocker tồn đọng không?** | Work item age, blocked time và dependency age | Owner và nguyên nhân thật |
| **Tích hợp giữa nhóm có đáng tin?** | CI reliability, contract checks, thời điểm phát hiện lỗi | Test coverage theo rủi ro, flaky tests |
| **Release có an toàn?** | Incidents, failure impact, recovery và monitoring | Độ đầy đủ của việc phát hiện và báo lỗi |
| **Nhóm có bền vững?** | Interruption, làm thêm giờ không mong muốn, phản hồi tổng hợp | Không theo dõi chi tiết cá nhân |
| **Remote collaboration có hiệu quả?** | Time-to-decision, số vòng làm rõ, độ trễ gỡ blocker | Kết quả quyết định, không chỉ thời gian họp |

### Một metric contract mẫu

~~~text
METRIC: end_to_end_cycle_time_feature
PURPOSE: Thời gian một feature PBI đi tới Increment đạt DoD.
POPULATION: Feature PBIs của dòng Học tiếp; incidents theo flow riêng.
START: PBI được bắt đầu làm theo Definition of Workflow.
FINISH: PBI đáp ứng DoD của sản phẩm.
TIME: Ngày làm việc hoặc ngày lịch, phải công bố nhất quán.
WINDOW: Các items hoàn tất trong cửa sổ quan sát xác định.
AGGREGATION: Median, phân bố/percentiles, count và ngoại lệ.
SEGMENTS: Nhóm có phụ thuộc contract, thiết bị web/mobile khi phù hợp.
SOURCE: Workflow history đối chiếu CI/DoD evidence.
GUARDRAILS: Escaped defects, authorization, data loss, overtime.
OWNER: Người chịu trách nhiệm định nghĩa và kiểm tra dữ liệu.
~~~

### Ví dụ so sánh phân bố

Giả sử năm PBIs trước thí nghiệm có cycle time **5, 8, 10, 14, 22 ngày**; sau là **4, 6, 8, 11, 18 ngày**. Median giảm từ **10 xuống 8 ngày**, nhưng item **18 ngày** vẫn cho thấy một đuôi dài cần điều tra. Với **mẫu chỉ năm mỗi kỳ**, không có cơ sở nói một thay đổi tổ chức **chắc chắn gây ra** mức giảm 20%; cũng cần xem loại công việc, nghỉ phép, kiến trúc và định nghĩa Done.

### Goodhart trong môi trường phân tán

Nếu manager yêu cầu “mọi người phản hồi chat dưới năm phút”, người làm có thể **trả lời cho có, mất deep work và phải làm ngoài giờ**. Nếu đánh giá theo số task hoàn tất, họ có thể **chia vụn tasks hoặc giấu blocked items**. Chọn metric như **time-to-decision và time-to-unblock** trong bối cảnh, đồng thời bảo vệ thời gian tập trung và nghỉ ngơi.

### Cách dùng số đo

Số liệu là **đầu vào để thảo luận giả thuyết và điều chỉnh workflow**. Không nên dùng cycle time, commit count, story points hoặc giờ online để xếp hạng cá nhân, đặc biệt khi trách nhiệm và loại việc khác nhau.

## 19. Product discovery và feedback người dùng từ nhiều địa điểm

Một sản phẩm có nhiều team thường rất giỏi tối ưu build/deploy nhưng vẫn có thể giải **sai vấn đề**. Product Owner, Developers và người hiểu người dùng cần nhìn **bằng chứng hành vi thực**, không chỉ cập nhật tiến độ kỹ thuật.

### Hai vòng phản hồi cần nối với nhau

~~~mermaid
flowchart LR
    A["Giả thuyết nhu cầu<br/>người học"] --> B["Thử một lát cắt<br/>giá trị có bảo vệ"]
    B --> C["Increment đạt DoD"]
    C --> D["Rollout phù hợp<br/>và thu feedback"]
    D --> E{"Giá trị có<br/>được xác nhận?"}
    E -->|Có| F["Tiếp tục/mở rộng<br/>có kiểm soát"]
    E -->|Chưa| G["Điều chỉnh giải pháp<br/>hoặc Product Backlog"]
    G --> A
    F --> A
    H["CI / contract / quality feedback"] -.-> C
    H -.-> B
~~~

### Định nghĩa task success thay vì chỉ click

Giả sử có **150 lượt Học tiếp hợp lệ**, trong đó **105 lượt mở đúng bài trong 60 giây**, thì tỷ lệ task success của **lượt được quan sát** là:

\[
\frac{105}{150}\times 100\%=70\%.
\]

Con số không có nghĩa **70% học viên duy nhất** đạt được kết quả, vì một người có thể thử nhiều lượt. Cần xác định eligibility, người/phiên/lượt, cách ghi event, thiết bị, quyền và nhóm người dùng đã được exposure. Không tự gán mọi thay đổi sau release cho Agile nếu có chiến dịch nhắc học hoặc thay nội dung khóa cùng lúc.

### Nghiên cứu người dùng từ xa

- Thực hiện **phỏng vấn/quan sát tác vụ có sự đồng ý**, với nhóm người học đại diện phù hợp.
- Dùng **prototype có mục tiêu học rõ**, không bắt xây toàn bộ tính năng trước nghiên cứu.
- Tạo **bản tóm tắt phát hiện và bằng chứng** để người ở mọi múi giờ có thể xem.
- Trao đổi **trade-off sản phẩm** khi feedback trái giả thuyết.
- Bảo vệ **dữ liệu cá nhân, quyền truy cập và consent**, không tự ý chia sẻ bản ghi nhạy cảm qua chat.
- Xem cả những người có trải nghiệm khác nhau: **mobile, kết nối yếu, accessibility, người mới/quay lại**.

### Đưa feedback trở lại backlog

Trong Sprint Review hoặc phiên khám phá phù hợp, Product Owner cùng Developers và stakeholders kiểm tra **Increment, thị trường/điều kiện sử dụng và giả thuyết sản phẩm**. Kết quả có thể là **tăng ưu tiên lỗi mobile, đổi thiết kế nút, làm rõ trường hợp offline hoặc dừng một feature ít giá trị**. Nếu Review chỉ là demo cho đủ quy trình mà backlog bất biến, vòng feedback còn thiếu.

## 20. Phân quyền, dữ liệu và an toàn trong nhóm xuyên địa điểm

Phân tán làm tăng nhu cầu **quyền truy cập rõ, quản lý secrets, audit và tiêu chuẩn xử lý sự cố**, nhất là khi nhiều team phụ trách cùng luồng dữ liệu người học.

### Guardrails không thương lượng

| Rủi ro | Thực hành áp dụng | Không được đánh đổi |
| --- | --- | --- |
| **Sai quyền truy cập** | Server-side authorization, policy rõ, API tests và review theo rủi ro | Không tin rằng UI đã ẩn nút là đủ bảo mật |
| **Lộ dữ liệu học viên** | Least privilege, redaction, phân quyền dashboard/log | Không gửi token/checkpoint nhạy cảm trong chat/ticket |
| **Mất/corrupt checkpoint** | Dữ liệu có validation, migration/backfill checks, khả năng phục hồi | Không coi rollback code là rollback data |
| **Secrets và cấu hình** | Secret manager, môi trường tách biệt, rotation, audit | Không dùng secrets production để debug local |
| **Thay contract ảnh hưởng consumer cũ** | Versioning, expand–migrate–contract, compat tests | Không xóa field cũ khi mobile offline chưa nâng cấp |
| **Release gây hại** | Progressive rollout/health monitoring, người có quyền dừng | Không bỏ quality gates để kịp demo |
| **Lỗi production ngoài giờ** | Severity/on-call/handoff và phương án liên lạc | Không phụ thuộc một cá nhân thức 24/7 |

### Remote access không đồng nghĩa quyền vô hạn

Self-service tốt giúp làm đúng **dễ nhất**: Developers tự tạo môi trường, build và deploy artifact đã kiểm chứng trong **các quyền/giới hạn rõ**. Ngoại lệ có rủi ro cao cần kênh quyết định và bằng chứng phù hợp. Không coi việc “bỏ hết phê duyệt” là thước đo Agile.

### Kiểm soát thay đổi của service chung

Một thay đổi trong identity hoặc quyền khóa học có thể ảnh hưởng nhiều team. Cần rõ **producer/service owner, consumer contracts, test evidence, điều kiện rollout và incident roles**; không đẩy trách nhiệm từ nhóm này sang nhóm khác chỉ vì lỗi xuất hiện ở ranh giới.

## 21. Xử lý sự cố và bàn giao giữa múi giờ

Một điểm mạnh tiềm năng của nhóm phân tán là có thể **quan sát và xử lý sự cố xuyên khung giờ**, nhưng chỉ khi trách nhiệm, quyền và thông tin bàn giao rõ. Đây **không phải lý do ép mỗi người trực 24/7**.

### Một incident minh họa

Sau rollout Học tiếp, monitoring cho thấy một số request bị trả checkpoint của tài khoản khác. Đây là **rủi ro riêng tư/bảo mật nghiêm trọng**, không phải support ticket ưu tiên thường lệ.

~~~text
1. Detect/Report:
   Alert hoặc báo cáo đáng tin, ghi tác động và thời điểm.

2. Declare:
   Kích hoạt incident policy và chỉ định incident owner/commander.

3. Contain:
   Dừng hoặc giảm exposure theo thẩm quyền;
   bảo vệ dữ liệu trước khi tối ưu tốc độ delivery.

4. Diagnose/Recover:
   Owners API, identity, platform, data phối hợp;
   ghi bằng chứng tối thiểu, không đưa secrets vào chat.

5. Communicate:
   Cập nhật đúng stakeholders, mức ảnh hưởng và điều đã biết.

6. Handover:
   Chuyển trạng thái, rủi ro còn lại, quyết định và next action
   giữa các ca trực/múi giờ, có người nhận rõ.

7. Learn:
   Hậu kiểm có trách nhiệm, sửa tests, monitoring, policy,
   backlog và vận hành để giảm lặp.
~~~

### Mẫu handoff trong sự cố

| Trường | Nội dung cần có |
| --- | --- |
| **Incident ID, severity, owner** | Thông tin điều phối chính xác và người chịu trách nhiệm ca hiện tại |
| **Tác động đã biết** | Nhóm người dùng/dịch vụ bị ảnh hưởng; điểm chưa xác minh |
| **Đã thực hiện** | Containment, rollback/flag, kiểm tra dữ liệu và quyết định |
| **Hệ thống đang ở trạng thái nào** | Phiên bản service, feature exposure, trạng thái alert |
| **Rủi ro còn lại** | Dữ liệu cần khôi phục, API chưa chắc chắn, unknowns |
| **Next actions, người nhận** | Ai làm gì, phụ thuộc ai và mốc review |
| **Kênh cập nhật** | Liên hệ theo incident policy, không dùng chat cá nhân làm nguồn duy nhất |

**Không áp cùng SLE support thường lệ cho incident bảo mật**. Nếu incident chiếm capacity của Sprint, cập nhật forecast và công khai trade-off; không ép team vẫn giao tất cả PBIs như chưa hề có sự cố.

## 22. Điều phối chuyên gia dùng chung, platform và product teams

Một team phân tán có thể bị chặn bởi **chuyên gia security/data hoặc platform engineer**. Giải pháp không chỉ là lập thêm nhóm chat có người ấy; cần chọn **kiểu tương tác phù hợp nhu cầu**.

| Nhu cầu | Kiểu tương tác nên cân nhắc | Đầu ra mong muốn |
| --- | --- | --- |
| Developers cần tự tạo staging theo mẫu | **X-as-a-Service/self-service** | Golden path, docs, task success, support route |
| Team chưa hiểu authorization | **Facilitating/coaching** | Cặp làm mẫu, tests/policy, team tự xử lý trường hợp thường |
| Thay schema checkpoint phức tạp | **Collaboration có timebox** | Contract, migration/compat plan, owners |
| Subsystem thuật toán khó cần chuyên sâu | **Complicated-subsystem ownership với interface** | Service/contract rõ, tránh buộc mọi team học sâu |
| Nhiều Product Owners cùng tranh capacity platform | **Product/platform prioritization có người đủ quyền** | Backlog, trade-off, mốc hỗ trợ và đầu tư |

Các mẫu tương tác này thường gắn với **Team Topologies**, là **lựa chọn tham khảo**, không bắt buộc tổ chức có đủ bốn loại team để “đạt Agile”.

### Platform như một sản phẩm nội bộ

Platform cần **người dùng nội bộ, mục tiêu, backlog, interface, quality, hỗ trợ và feedback**. Nên xem **tỷ lệ tác vụ tự thực hiện thành công, time-to-unblock, reliability và trải nghiệm Developers**, không chỉ số ticket đóng.

Ví dụ, nếu có **80 tác vụ tạo staging hợp lệ**, **60** tác vụ tự hoàn tất và môi trường sử dụng được mà không cần nhân viên platform thao tác:

\[
\text{Self-service task success}=\frac{60}{80}\times100\%=75\%.
\]

Đây là **75% tác vụ**, không tự đồng nghĩa 75% Developers tự chủ. Nếu template báo success nhưng môi trường không chạy, phải sửa điều kiện “thành công”.

### Giảm demand lặp thay vì chỉ tăng đội hỗ trợ

Nếu 30 request/tháng đều cần platform engineer thao tác một cấu hình giống nhau, cân nhắc **automation/self-service** thay vì tuyển thêm người chỉ làm thao tác đó. Nhưng một request migration rủi ro cao vẫn có thể cần chuyên môn sâu hoặc nhiều team collaboration. Mục tiêu là **cân bằng tự chủ, chuyên sâu và an toàn**.

## 23. Ra quyết định khi có thay đổi ưu tiên xuyên nhóm

Với nhiều nhóm cùng sản phẩm, Product Owner chịu trách nhiệm Product Backlog nhưng không có nghĩa họ phải trực tiếp quyết định từng dòng code, môi trường hoặc tình huống incident. Quyền ra quyết định phải **rõ đến nơi có dữ liệu và trách nhiệm**, trong giới hạn chất lượng.

### Decision rights đề xuất

| Loại quyết định | Trách nhiệm chính | Khi nào cần tham gia thêm? |
| --- | --- | --- |
| **Vấn đề và thứ tự Product Backlog** | Product Owner | Developers, stakeholders, security/domain khi có rủi ro |
| **Sprint Goal và kế hoạch Sprint của team** | Scrum Team lập Sprint Goal; Developers quản lý Sprint Backlog | PO tham gia điều chỉnh scope, phụ thuộc liên team |
| **Thiết kế/triển khai service** | Developers và owners kỹ thuật | Khi đổi public API, dữ liệu hoặc tiêu chuẩn tổ chức |
| **Dừng một rollout gây hại** | Người có thẩm quyền theo incident/release policy | Incident owners, service owners, Product Owner theo tác động |
| **Shared platform capacity** | Platform product owner/người có thẩm quyền đầu tư | Những Product Owners sử dụng và người quản trị rủi ro |
| **Nghĩa vụ pháp lý/bảo mật** | Policy/security owner có quyền hợp lệ | Product/engineering owners để thiết kế phương án an toàn |

### Ví dụ thay đổi giữa Sprint

Sprint Goal của một Scrum Team là **“Người học đủ quyền có thể mở lại đúng bài đang dở từ trang khóa học”**. Giữa Sprint:

1. **Sự cố checkpoint lộ dữ liệu**: kích hoạt incident ngay, cập nhật capacity và tác động tới Sprint Goal.
2. **Marketing muốn thêm huy hiệu**: PO xem Product Backlog, không tự động ép vào Sprint.
3. **API phát hiện rule xung đột thiết bị**: Developers trao đổi với PO và service owner để làm rõ/cập nhật Sprint Backlog, bảo vệ DoD.

Nếu **Sprint Goal trở nên lỗi thời**, theo Scrum Guide **chỉ Product Owner có quyền hủy Sprint**. Đó là trường hợp đặc biệt, không phải thủ thuật để cấp trên thay kế hoạch mỗi ngày.

### Decision log cho người không cùng giờ

~~~text
DECISION-ID: CHECKPOINT-CONFLICT-01
QUESTION: Hai thiết bị cập nhật checkpoint khác phiên bản thì sao?
CONTEXT: Mobile có thể offline, cần tránh ghi đè tiến độ mới.
OPTIONS: Compare version; retry với conflict; fallback có thông báo.
DECISION: [Quyết định được xác nhận với owners có thẩm quyền]
RATIONALE: Bảo vệ tính đúng và trải nghiệm học.
IMPACT: API semantics, UI error state, compatibility tests.
OWNER: Product/domain + service owners theo phạm vi.
FOLLOW-UP: Test/monitoring và mốc đánh giá sau rollout.
~~~

Quyết định nên được lưu **ở nguồn chung có phân quyền**, không chỉ trong DM hoặc bản ghi cuộc gọi mà nhiều người không được xem.

## 24. Lộ trình áp dụng 30–60–90 ngày

Đề xuất nên bắt đầu bằng **thử nghiệm có phạm vi và tiêu chí đánh giá**, tránh đồng loạt tái tổ chức hoặc áp mọi thực hành cho mọi team. Dưới đây là kế hoạch tham khảo cho **hai Scrum Teams phân tán cùng một sản phẩm học tập**; lịch không phải nghĩa vụ của Scrum Guide và cần chỉnh theo rủi ro thực.

### Ngày 1–30: hiểu dòng giá trị, thống nhất trách nhiệm và tạo nền phản hồi

**Mục tiêu:** Biết rõ sản phẩm, sự chờ đợi và những điều kiện an toàn; thử một số thỏa thuận giúp mọi thành viên hiểu cùng vấn đề.

| Workstream | Việc đề xuất | Bằng chứng/đầu ra |
| --- | --- | --- |
| **Product** | Xác định Product Goal, một Product Backlog, PO, stakeholders và problem statement Học tiếp | Mục tiêu, thứ tự backlog, cách nhận feedback |
| **Teams** | Làm rõ mỗi Scrum Team, Sprint Goal, Scrum Master, Developers và DoD chung | Không còn ba định nghĩa “Done” xung đột |
| **Remote** | Thử working agreement, overlap window, async update và decision log | Người vắng buổi họp hiểu quyết định/next action |
| **Workflow** | Theo dấu 5–10 PBIs gần đây, ghi start–finish, blocked, handoffs, incidents | Baseline ban đầu có giới hạn mẫu công khai |
| **Engineering** | Kiểm tra CI/contract/authorization, xác định rủi ro kỹ thuật cao | Danh sách checks và owners cần ưu tiên |
| **User discovery** | Quan sát tác vụ Học tiếp hiện tại trong mẫu phù hợp | Tình huống thất bại và giả thuyết giá trị |

**Quyết định cuối tháng:** Những trở ngại lớn nhất là **giao tiếp từ xa**, **ưu tiên sản phẩm**, **API**, **môi trường** hay **chất lượng tích hợp**? Chọn tối đa vài đòn bẩy có tác động đáng kể và đủ quyền thử, thay vì lập đồng thời 20 chính sách mới.

### Ngày 31–60: tạo Increment nhỏ tích hợp và giảm chờ

**Mục tiêu:** Có một hoặc vài lát cắt Học tiếp đạt DoD, được kiểm chứng trong môi trường phù hợp; phụ thuộc liên team có cách xử lý rõ.

| Workstream | Việc đề xuất | Bằng chứng/đầu ra |
| --- | --- | --- |
| **Product Backlog** | Chia vertical slices, làm rõ acceptance examples và thứ tự | PBIs có giá trị và rủi ro rõ |
| **Teams/flow** | Thử ưu tiên hoàn tất khi Review/Verify đầy, theo dõi work item age | Ít items già đi, biết blocker thật |
| **API** | Chốt contract cho Học tiếp, test đúng quyền/conflict | Producer/consumer có bằng chứng tương thích |
| **CI/DoD** | Tích hợp thường xuyên, cải thiện reliability và kiểm tra E2E | Increment thực sự đạt DoD, không ghép muộn |
| **Remote collaboration** | Phiên workshop ngắn theo dependency; async decisions có owner | Time-to-decision/time-to-unblock giảm nếu giả thuyết đúng |
| **Release/feedback** | Rollout có kiểm soát khi đạt guardrails, theo dõi task success | Bằng chứng người học và lỗi thực |

**Quyết định cuối tháng:** Giữ hoặc sửa những thỏa thuận nào? Nếu CI tốt lên nhưng staging vẫn luôn phải xin người platform, cần **đầu tư platform** chứ không tăng số cuộc họp Scrum.

### Ngày 61–90: kiểm tra khả năng lặp lại và mở rộng có chọn lọc

**Mục tiêu:** Không chỉ có một bản demo thành công; các team có thể lặp lại việc tạo Increment, điều chỉnh Product Backlog từ feedback và vận hành có trách nhiệm.

| Workstream | Việc đề xuất | Bằng chứng/đầu ra |
| --- | --- | --- |
| **Flow** | So phân bố cycle time, blocked age, throughput cùng loại việc | Mức cải thiện có bối cảnh, đuôi dài đã điều tra |
| **Quality** | Xem escaped defects, CI reliability, incidents và release recovery | Không chuyển lỗi tới người dùng để giảm lead time |
| **User outcome** | Xem task success theo cohort/thiết bị và phản hồi | Hướng sản phẩm được sửa khi giả thuyết sai |
| **Sustainability** | Phỏng vấn nhóm, overtime/interruption, rotation/on-call | Nhịp phối hợp không phụ thuộc họp khuya/1 cá nhân |
| **Governance** | Xem decision rights, chính sách cấp capacity và phụ thuộc liên sản phẩm | Những blocker ngoài quyền team có owner/đường xử lý |
| **Scaling** | Thử cơ chế hiệu quả ở lát cắt hoặc team tương đồng khác khi phù hợp | Điều kiện áp dụng được hiểu, không nhân bản hình thức |

**Quyết định cuối quý:** **Giữ, sửa, dừng hoặc mở rộng** từng thực hành. Không gọi 90 ngày là “Agile transformation hoàn tất”; đây là **một vòng học có bằng chứng**, có thể lặp lại với vấn đề mới.

### Cách gắn owner mà không dựng thêm tầng chỉ huy

~~~text
Product Goal / ưu tiên: Product Owner
Sprint Goals / Sprint Backlogs: từng Scrum Team, Developers lập kế hoạch
Definition of Done chung: các Scrum Teams và tiêu chuẩn áp dụng
API/data contracts: service owners + consumers
CI/integration: Developers + platform owners theo ownership thực
Remote working agreement: thành viên nhóm cùng thiết kế và xem lại
Quality/incident policies: owners theo thẩm quyền rủi ro
Outcome/measurement: Product + engineering + người có nguồn dữ liệu
Escalation hệ thống: lãnh đạo/portfolio/platform khi vượt quyền team
~~~

**Không có một chức danh “người chịu trách nhiệm mọi thứ” thay cho các accountabilities này.** Mỗi quyết định phải ở nơi có đủ bối cảnh và quyền hành động.

## 25. Case study tổng hợp: hai Scrum Teams phân tán xây “Học tiếp”

Đây là **tình huống mô phỏng** dùng để kết hợp tất cả quyết định ở trên; các số liệu chỉ phục vụ học tập.

### 25.1. Tổ chức và ràng buộc

Một công ty có một sản phẩm học trực tuyến. Hai Scrum Teams làm trên cùng sản phẩm:

| Scrum Team | Thành viên phân tán | Năng lực chính | Phụ thuộc đáng chú ý |
| --- | --- | --- | --- |
| **Team Trải nghiệm** | Product design, frontend/mobile, một số full-stack Developers | Hành trình người học, UI, trải nghiệm | Checkpoint API, course metadata, release flag |
| **Team Tiến độ** | Backend, data, API/QA engineering | Checkpoint, quyền, consistency | Identity policy, migration, consumers web/mobile |

Một **Product Owner** chịu trách nhiệm Product Goal và một Product Backlog chung; mỗi Scrum Team có accountability Scrum Master trong cấu hình tổ chức phù hợp, Sprint Goal/Sprint Backlog của mình và **cùng Definition of Done**. Một platform capability phục vụ build/deploy/staging, nhưng không tự quyết định giá trị thay Product Owner.

Đội làm việc ở nhiều địa điểm; không giả định ai cũng có giờ làm trùng toàn bộ. Họ giữ một **khoảng giao tiếp trực tiếp có sự đồng thuận**, các quyết định còn lại có thể đọc/bổ sung async.

### 25.2. Product Goal và mô tả vấn đề

**Product Goal:** “Người học quay lại đúng vị trí và tiếp tục lộ trình học một cách thuận tiện, tin cậy trên các thiết bị được hỗ trợ.”

**Problem statement:** Nhiều học viên đủ quyền phải tự tìm lại bài, một số gặp checkpoint không nhất quán giữa các thiết bị; nhóm chưa có baseline đủ đáng tin về task success.

**Giả thuyết sản phẩm:** Đường Học tiếp với hành vi rõ khi chưa có checkpoint, hết quyền, mất kết nối hoặc có conflict sẽ tăng khả năng người học mở đúng bài và tiếp tục học, trong khi không vi phạm quyền dữ liệu.

### 25.3. Phân chia Product Backlog theo lát cắt

| PBI mẫu | Team dẫn dắt giả định | Điều cần phối hợp | Bằng chứng Done |
| --- | --- | --- | --- |
| **PBI-1: Học tiếp một checkpoint hợp lệ** | Team Trải nghiệm | API contract với Team Tiến độ | E2E, quyền, UI đúng trạng thái |
| **PBI-2: API checkpoint đọc đúng quyền** | Team Tiến độ | Consumers web/mobile | Contract/authorization tests |
| **PBI-3: Chưa có checkpoint** | Team Trải nghiệm | Domain semantics | Hành vi bắt đầu hợp lệ đã xác nhận |
| **PBI-4: Conflict hai thiết bị** | Team Tiến độ phối hợp Team Trải nghiệm | Data/version, UI failure/retry | Tests đồng thời, thông báo và tính đúng |
| **PBI-5: Observability lỗi Học tiếp** | Các Developers/service owners | Platform monitoring | Không lộ dữ liệu, có alert/runbook phù hợp |

Danh sách minh họa **không phải cách duy nhất chia PBIs**. Một PBI có thể cần Developers ở cả hai team cùng tạo lát cắt. Tránh biến PBI-1/2 thành hai việc “Done” riêng mà **không có Increment tích hợp**; nếu cần, có thể viết lại lát cắt và phụ thuộc để giá trị hoàn tất end-to-end.

### 25.4. Sprint Goals minh họa

Hai Scrum Teams có thể xây các Sprint Goals **bổ trợ** mà không cần cùng wording:

- **Team Trải nghiệm:** “Một học viên đủ quyền có thể mở bài đang dở từ trang khóa học với UI phản hồi đúng.”
- **Team Tiến độ:** “Checkpoint API phục vụ lát cắt Học tiếp đúng quyền và contract tương thích cho consumer.”

Điều kiện phối hợp: **hai mục tiêu phải tạo ra giá trị có thể tích hợp**, không được tách để một team gọi Done khi consumer chưa kiểm chứng. Scrum Teams cùng chia Product Goal/Backlog/PO/DoD nhưng **mỗi team có Sprint Goal của mình**.

### 25.5. Một chuỗi tương tác từ xa có thể thực hiện

~~~mermaid
sequenceDiagram
    participant PO as Product Owner
    participant UX as Team Trải nghiệm
    participant API as Team Tiến độ
    participant PL as Platform
    participant U as Học viên
    PO->>UX: Product Goal và acceptance examples
    PO->>API: Ưu tiên và rủi ro checkpoint
    UX->>API: Consumer contract và trường hợp sai quyền
    API-->>UX: Semantics, version và test cases
    API->>PL: Yêu cầu CI/staging chuẩn
    PL-->>API: Self-service capability và support
    UX->>API: Tích hợp và chạy contract/E2E checks
    API-->>UX: Bằng chứng tương thích và DoD
    UX->>U: Rollout có kiểm soát
    U-->>PO: Feedback và task success
    PO->>UX: Cập nhật Product Backlog
    PO->>API: Quyết định ưu tiên tiếp
~~~

Sơ đồ nhấn **đầu ra và feedback**, không có nghĩa mọi message phải diễn ra tuần tự theo thời gian; nhiều việc có thể chạy song song. Chủ sở hữu service và security policy vẫn phải chịu trách nhiệm phần liên quan.

### 25.6. Xử lý một blocker bất đồng bộ

Team Trải nghiệm mở PR dùng trường \`lastConfirmedPosition\`. API owner ở địa điểm khác phát hiện field này sẽ không đủ khi mobile offline. Thay vì gửi DM “fix giùm” rồi chờ một ngày, người mở PBI:

1. Ghi **vấn đề, consumer behavior, ví dụ conflict và tác động đến Sprint Goal** vào nguồn chung.
2. Chỉ định **owner cần quyết định và mốc xem lại**.
3. Đề xuất hai phương án có trade-off, đánh dấu blocker và tác động WIP.
4. Dùng một **phiên trao đổi ngắn** nếu async không giải được bất định.
5. Ghi quyết định thành **API contract, automated tests và cập nhật backlog**.

Khi người ở địa điểm khác làm việc, họ có thể hiểu bối cảnh và phản hồi **mà không phải hỏi lại mọi thứ**.

### 25.7. Một biến cố thay đổi kế hoạch

Giữa Sprint, mobile phát hiện lỗi replay một checkpoint cũ có thể ghi đè tiến độ mới. Product Owner và Developers cần hiểu **rủi ro người học, khả năng tái hiện và hướng xử lý**, điều chỉnh Sprint Backlogs để giữ DoD và Sprint Goals trong chừng mực phù hợp.

Nếu lỗi đã ảnh hưởng production nghiêm trọng, kích hoạt **incident response** theo policy và điều chỉnh forecast. Không tự động ép “giữ đủ tất cả PBIs đã chọn” bằng cách bỏ test. Nếu Sprint Goal lỗi thời, quyền hủy Sprint thuộc Product Owner theo Scrum Guide.

### 25.8. Đưa Increment tới người dùng và học

Khi checks và DoD đạt, team có thể deploy bản phù hợp, dùng flag/rollout để exposure cho một nhóm người học đủ điều kiện. Theo dõi:

- **Task success:** mở đúng bài, thời gian và các trường hợp thất bại.
- **Safety:** sai quyền, mất tiến độ, conflict, rollback/recovery.
- **Reliability:** API errors/latency theo giới hạn được xác nhận.
- **Feedback:** quan sát người dùng trên web/mobile, ngữ cảnh thực.
- **Flow:** thời gian từ bắt đầu tới DoD, blocked age và review waiting.

Nếu UI trên mobile vẫn không rõ dù pipeline tốt hơn, Product Owner **sửa giả thuyết sản phẩm**; không “scale thêm framework” để thay feedback người dùng.

### 25.9. Kết quả giả định sau thử

| Tín hiệu | Baseline giả định | Sau hai vòng thử | Diễn giải thận trọng |
| --- | ---: | ---: | --- |
| Median cycle time feature PBIs | 14 ngày | 9 ngày | Có tín hiệu flow tốt, cần kiểm tra mix/DoD |
| Median review waiting | 4 ngày | 1,5 ngày | Có thể do review policy + PR nhỏ |
| WIP trung bình | 11 | 7 | Ít việc dở, xác minh không giấu blockers |
| Time-to-staging | 3 ngày | 3 giờ | Self-service có thể loại thao tác/chờ |
| API contract mismatch sát release | 5 lần | 2 lần | Mẫu nhỏ, định nghĩa sự kiện phải nhất quán |
| Task success Học tiếp | 50% lượt đủ điều kiện | 68% | Cần cohort, tracking, exposure và kiểm tra nguyên nhân |
| Incidents sai quyền/mất dữ liệu | Chưa có baseline đủ tin cậy | Có monitoring/tests tốt hơn | Không tuyên bố đã giảm tỷ lệ từ dữ liệu thiếu |
| Overtime ngoài kế hoạch | Chưa đo hệ thống | Theo dõi phản hồi/cửa sổ mới | Không gọi cải tiến bền vững khi chưa có bằng chứng |

Các số **không chứng minh nhân quả**: công việc có thể dễ hơn, team có thêm hỗ trợ hoặc exposure khác. Dùng chúng để **đặt câu hỏi và quyết định tiếp**, không làm case study “thành công tuyệt đối”.

### 25.10. Điều gì được giữ và điều gì cần đổi?

**Giữ khi có bằng chứng phù hợp:** một Product Goal/Backlog/DoD chung, contract tests, CI, working agreement async có owner, review/flow policies tạo ích lợi.

**Điều chỉnh:** lịch họp gây mệt mỏi, SLE không phù hợp loại việc, thiếu hỗ trợ mobile/offline, môi trường test chưa đáng tin.

**Không triển khai vội:** một tầng quản lý Agile mới chỉ để cập nhật tiến độ, một master board sao chép mọi task hoặc KPI velocity xuyên nhóm.

## 26. Risk register cho đề án áp dụng Agile phân tán

Rủi ro phải có **biện pháp phòng ngừa, owner và tín hiệu kích hoạt**, không chỉ một danh sách “nguy cơ cao/trung bình/thấp”.

| Rủi ro | Tín hiệu sớm | Biện pháp và owner gợi ý |
| --- | --- | --- |
| **Thiếu ngữ cảnh do async** | Nhiều vòng hỏi lại, decisions trái nhau | Mẫu quyết định, owner, nguồn chung; working agreement |
| **Họp ngoài giờ gây kiệt sức** | Thành viên liên tục phải thức khuya, vắng họp | Overlap hợp lý, xoay phiên, chuẩn bị async; nhóm/manager |
| **Product Backlog phân mảnh** | Các team chọn PBIs cạnh tranh, không rõ PO | Củng cố Product Goal/Backlog/PO; Product Owner và Scrum Teams |
| **Done không tích hợp** | Cuối Sprint phát hiện API không khớp | DoD chung, contract tests, CI; Developers/service owners |
| **Chuyên gia chung quá tải** | Request age tăng, người duy nhất không có backup | Risk-based review, coaching, platform backlog; policy owner |
| **API phá phiên bản cũ** | Consumer fails, mobile offline dùng schema cũ | Versioning/expand–migrate–contract; producer/consumers |
| **Lộ dữ liệu học viên** | Authorization failures, log chứa dữ liệu nhạy cảm | Server-side access checks, least privilege, incident policy |
| **SLE bị hiểu là deadline tuyệt đối** | Review yêu cầu phạt cá nhân khi “trễ SLE” | Giải thích xác suất, xem age và phân bố; flow owner |
| **Dữ liệu metrics bị thao túng** | Points tăng, Done đổi nghĩa, blockers biến mất | Metric contract, evidence/DoD, không xếp hạng cá nhân |
| **Cơ chế liên nhóm quá nặng** | Nhiều họp, waiting time không giảm | Thử tối thiểu, đo time-to-decision, dừng hoạt động vô ích |
| **Mất tri thức khi nghỉ phép** | Không ai deploy/sửa được một service | Backup/rotation, docs/runbook và pairing |
| **Feedback sản phẩm đến muộn** | Chỉ demo mock, exposure và outcome chưa đo | Release thử an toàn, UX research, decision review |
| **Overload do incident** | Forecast không đổi dù nhiều người trực sự cố | Capacity rõ, cập nhật Sprint Backlog và stakeholder expectation |

### Quy tắc phản ứng theo mức rủi ro

- **Rủi ro an toàn/dữ liệu nghiêm trọng:** dừng/giới hạn exposure theo policy, xử lý ngay; không chờ retro.
- **Blocker đe dọa Increment:** owner và next action rõ, quyết định trong khung giờ phù hợp hoặc escalation đúng cấp.
- **Trở ngại lặp nhưng chưa khẩn:** đưa vào improvement/engineering/platform backlog, thử giải gốc.
- **Bất định sản phẩm:** nghiên cứu/kiểm chứng sớm, không cố khóa scope dài hạn.

## 27. Bộ công cụ tối thiểu, không biến công cụ thành quy trình

Không có yêu cầu “bắt buộc dùng Jira, Slack, Miro, Zoom hoặc một bộ phần mềm cụ thể” để được coi là Agile. Chọn **khả năng cần thiết**, không chọn tên ứng dụng.

| Năng lực cần | Đặc điểm tối thiểu | Dấu hiệu nên cải tiến |
| --- | --- | --- |
| **Product Backlog và Sprint/flow view** | Sắp thứ tự, liên kết PBIs với mục tiêu và phụ thuộc, lịch sử trạng thái | Có ba nguồn khác nhau, copy tay mỗi ngày |
| **Tài liệu/decision log** | Tìm kiếm được, versioned, quyền rõ, owner | Quyết định chỉ nằm trong tin nhắn riêng |
| **Async collaboration** | Thread theo chủ đề, liên kết issue, chính sách phản hồi | Ai cũng bị ping mọi lúc, khó tìm ngữ cảnh |
| **Video/real-time collaboration** | Hỗ trợ quyết định khó, pairing và workshop | Họp để đọc status, người ở xa không thể tham gia công bằng |
| **Source control/PR review** | Thay đổi nhỏ, reviewer phù hợp, checks rõ | PR đợi nhiều ngày hoặc một người độc quyền review |
| **CI/CD** | Feedback đáng tin, artifact định danh, deploy có policy | Test flaky, staging khác production quá mức, bỏ guardrails |
| **Monitoring/incident** | Health, trace và điều phối sự cố có owner | Người dùng báo lỗi trước monitoring, không ai nhận incident |
| **User research/analytics** | Task success có định nghĩa, cohort/consent phù hợp | Chỉ đếm lượt click, tracking thiếu |

### Quy tắc “mỗi thông tin một nguồn chính”

Một Product Backlog có thể được liên kết từ nhiều dashboard, nhưng **không nên có năm bản sao được cập nhật thủ công**. Decision log liên kết tới PBI/API contract, automated tests liên kết tới code và pipeline. Người ở địa điểm khác cần biết **tìm thông tin chính ở đâu**, không hỏi ai là “người giữ file”.

### Tránh biến hoạt động cá nhân thành dashboard giám sát

Không dùng thời gian bật camera, trạng thái online, số phím gõ hoặc số tin nhắn để kết luận năng suất. Đo **mức hoàn tất giá trị, chất lượng, tính minh bạch và khả năng hợp tác** ở cấp workflow/team, bảo vệ quyền riêng tư và sự tin cậy.

## 28. Mẫu đề án một trang trình người có quyền quyết định

Để tránh một kế hoạch chỉ gồm danh sách buổi họp hoặc slide giải thích framework, có thể dùng mẫu sau làm **đầu ra chính của bài thực hành**.

~~~text
TÊN ĐỀ ÁN:
  Áp dụng Agile cho [team phân tán/nhiều Scrum Teams một sản phẩm]

SẢN PHẨM / NGƯỜI NHẬN GIÁ TRỊ:
  [Product Goal, hành trình, nhóm người dùng đủ điều kiện]

VẤN ĐỀ VÀ BẰNG CHỨNG:
  [Một số work items thật, waiting, lỗi, feedback người dùng]

CẤU HÌNH ĐƯỢC CHỌN:
  [Một Scrum Team phân tán / nhiều Scrum Teams cùng sản phẩm
   / nhiều sản phẩm dùng chung services; lý do]

PRODUCT OWNERSHIP:
  [PO, Product Backlog, Product Goal, boundaries và stakeholders]

TEAM RESPONSIBILITIES:
  [Scrum accountabilities, Sprint Goals, service/incident owners]

WORKING AGREEMENT:
  [Nguồn sự thật, async, overlap, review, quyết định, escalation]

FLOW:
  [Start/finish, WIP control, blocked policy, SLE nếu phù hợp]

ENGINEERING & QUALITY:
  [DoD chung, CI, contract/E2E tests, data/security guardrails]

FEEDBACK:
  [Increment, rollout, user research/task outcome, review cadence]

DEPENDENCIES:
  [Requesters, providers, interface, owners và next actions]

30-60-90 PLAN:
  [Giai đoạn, thay đổi, ai làm, mốc đánh giá]

METRICS:
  [Baseline/cách lấy, flow, quality, product outcome, sustainability]

RISKS:
  [Phạm vi impact, rủi ro an toàn, capacity và mitigation]

DECISION:
  [Giữ / sửa / dừng / mở rộng; người có quyền và mốc xem lại]
~~~

### Một ví dụ điền rút gọn

| Trường | Đề xuất minh họa cho sản phẩm học trực tuyến |
| --- | --- |
| **Vấn đề** | Học viên khó tìm bài dở; feature PBIs chờ API review và staging lâu |
| **Cấu hình** | Hai Scrum Teams phân tán cùng một sản phẩm, không lập thêm cấp PO |
| **Product ownership** | Một Product Goal, Product Backlog, Product Owner, DoD chung |
| **Working agreement** | Async decision notes, overlap hợp lý, timeboxed collaboration |
| **Quality** | API/authorization tests, CI, migration compatibility, incident ownership |
| **Flow** | WIP/age được xem hằng ngày, blocked items có owner |
| **Feedback** | Release thử Học tiếp theo policy, quan sát task success web/mobile |
| **Metrics** | Cycle time, blocked time, CI health, task success, overtime |
| **90 ngày** | Baseline → lát cắt tích hợp → đánh giá và mở rộng có chọn lọc |
| **Guardrails** | Không mất dữ liệu, sai quyền hoặc buộc người làm việc ngoài giờ thường xuyên |

### Cách bảo vệ đề án trước lãnh đạo

Người phê duyệt có thể hỏi: “Tại sao không tổ chức một cuộc họp liên nhóm mỗi ngày?” Trả lời bằng **phụ thuộc thực và chi phí điều phối**: nếu hai team chỉ cần cập nhật contract, **test tự động + trao đổi theo quyết định** có thể hiệu quả hơn báo cáo hằng ngày. Nếu nhiều blocker lặp và không ai có quyền quyết, cần **một cơ chế escalation có người chịu trách nhiệm**, không thể thay bằng async documents. Một đề xuất tốt thể hiện **điều kiện nào khiến chúng ta thay lựa chọn**, không bảo vệ một framework như giáo điều.

## 29. Các phản mẫu khi áp dụng Agile cho nhóm phân tán hoặc nhiều nhóm

### 29.1. “Chuyển tất cả họp sang video là đã Agile từ xa”

Lịch họp dài, thiếu quyết định và người ở múi giờ khác phải thức khuya. **Cải tiến:** async context trước, đồng bộ khi cần quyết định, log kết quả và xem lại thời gian chờ.

### 29.2. “Online liên tục mới được coi là đóng góp”

Khuyến khích phản hồi nhanh cho có, phá deep work và giờ nghỉ. **Cải tiến:** service expectations theo mức khẩn, đo kết quả team và thời gian gỡ blocker.

### 29.3. “Thông tin quan trọng nằm ở DM của hai người”

Các thành viên khác thiếu ngữ cảnh khi người quyết định nghỉ hoặc đổi giờ. **Cải tiến:** ghi quyết định/contract ở nguồn chung được phân quyền.

### 29.4. “Async nghĩa là không bao giờ họp”

Tranh luận nghiệp vụ phức tạp bị kéo dài hàng chục lượt nhắn. **Cải tiến:** collaboration có mục tiêu, timebox, người có quyền và decision log.

### 29.5. “Cứ có nhiều team thì cần framework quy mô lớn”

Nhiều vấn đề đến từ API contracts, CI và decision rights chưa rõ. **Cải tiến:** chẩn đoán value stream; thử cơ chế nhỏ và bổ sung cấu trúc khi có bằng chứng.

### 29.6. “Một sản phẩm chia cho ba team thì cần ba Product Owners độc lập”

Ưu tiên bị chia nhỏ; không ai chịu trách nhiệm Product Backlog sản phẩm. **Cải tiến:** với nhiều Scrum Teams cùng một sản phẩm, cùng Product Goal/Backlog/PO/DoD.

### 29.7. “Mọi sản phẩm dùng chung API phải có một Product Backlog”

Nhầm phụ thuộc service với ranh giới sản phẩm. **Cải tiến:** xác định ownership sản phẩm thật và điều phối bằng hợp đồng/ưu tiên liên sản phẩm.

### 29.8. “Team UI Done, team API Done là Increment Done”

Chưa tích hợp, tiêu chuẩn khác nhau. **Cải tiến:** DoD chung, contract/E2E checks và tích hợp liên tục.

### 29.9. “Sprint Goal của hai team phải giống hệt câu chữ”

Nhầm Product Goal chung với Sprint Goal của từng Scrum Team. **Cải tiến:** mỗi team xây Sprint Goal bổ trợ, không mâu thuẫn với Product Goal và Increment chung.

### 29.10. “Mọi team phải có cùng WIP limit và story points”

Khác workflow, capacity, rủi ro khiến so sánh sai. **Cải tiến:** explicit policy và định nghĩa dữ liệu từng flow; không xếp hạng velocity.

### 29.11. “Để phối hợp tốt phải gom mọi task vào một master board”

Sao chép báo cáo tạo thêm overhead mà không giải quyết dependency. **Cải tiến:** chỉ link những phụ thuộc chặn Increment và có owner/next action.

### 29.12. “Cứ họp Daily Scrum liên nhóm là không cần CI”

Cuộc họp không phát hiện được mọi API regression. **Cải tiến:** contract tests, CI, integration environments và trao đổi khi cần.

### 29.13. “Cắt tests để giữ lịch phát hành chung”

Tăng nguy cơ mất checkpoint hoặc sai quyền. **Cải tiến:** giữ DoD/guardrails, điều chỉnh phạm vi và rollout theo rủi ro.

### 29.14. “Đã deploy thì người dùng đã nhận giá trị”

Feature có thể chưa bật hoặc không giúp tác vụ. **Cải tiến:** phân biệt deploy/release/exposure/outcome và kiểm chứng người dùng.

### 29.15. “Các team không cần biết contract nếu đã có meeting”

Ngữ cảnh miệng không được kiểm chứng và versioning thiếu rõ. **Cải tiến:** versioned contracts, acceptance examples, automated compatibility checks.

### 29.16. “Chỉ chuyên gia security mới được review mọi PR”

Một người trở thành nút thắt cho rủi ro thấp. **Cải tiến:** policy theo rủi ro, automation, coaching và backup, vẫn giữ review bắt buộc khi cần.

### 29.17. “Platform team chỉ tồn tại để nhận ticket”

Request lặp không được loại bỏ; chờ ngày càng tăng. **Cải tiến:** platform as a product, self-service, service catalog và feedback Developers.

### 29.18. “Incident production đợi tới ngày làm việc chung tiếp theo”

Rủi ro người dùng bị kéo dài. **Cải tiến:** severity/on-call, handoff xuyên ca, quyền dừng rollout rõ.

### 29.19. “Vì Agile nên mọi yêu cầu mới phải vào Sprint ngay”

Sprint Goal phân tán, forecast không còn ý nghĩa. **Cải tiến:** triage, PO sắp backlog, điều chỉnh scope và xử lý incident riêng.

### 29.20. “Thưởng đội có velocity cao nhất để tạo cạnh tranh”

Story points không cùng thang, khuyến khích làm đẹp số. **Cải tiến:** xem flow/product/quality trong bối cảnh, không xếp hạng con người.

### 29.21. “Retro càng nhiều action items càng hiệu quả”

Không theo dõi được tác động, chỉ tăng danh sách việc. **Cải tiến:** một vài experiments có owner, baseline, guardrails và mốc quyết định.

### 29.22. “Bản họp được ghi hình là đủ tài liệu”

Không ai có thời gian xem lại hai giờ video để tìm API decision. **Cải tiến:** tóm tắt quyết định, contract, tests và next actions ở nguồn chung.

### 29.23. “Đồng bộ lịch Sprint là mục tiêu của phối hợp”

Đổi lịch gây overhead nhưng không giảm integration breaks. **Cải tiến:** đo dependency và chất lượng tích hợp, chỉ đồng bộ cadence nếu thật sự giúp.

### 29.24. “Phải mở rộng cùng cách làm từ pilot sang mọi team”

Pilot có thể khác sản phẩm, người, mức phụ thuộc và hỗ trợ. **Cải tiến:** mô tả điều kiện thử, đo baseline riêng và thích ứng theo dòng giá trị.

### 29.25. “Ít ticket hỗ trợ nghĩa là platform tự phục vụ tốt”

Developers có thể ngại báo lỗi hoặc dùng workaround rủi ro. **Cải tiến:** đo task success, time-to-unblock, reliability và trải nghiệm thực.

### 29.26. “Tự chủ là được bỏ tất cả kiểm soát”

Tạo nguy cơ rò rỉ dữ liệu/vi phạm nghĩa vụ. **Cải tiến:** tự chủ trong guardrails rõ, điều kiện kiểm tra và escalation theo rủi ro.

### 29.27. “Đã có dashboard là đủ minh bạch”

Chỉ số không có owner và không dẫn tới quyết định. **Cải tiến:** metric contract, review giả thuyết, decision log và sự thay đổi backlog/policy.

### 29.28. “Phân tán là vấn đề của con người, không phải kiến trúc”

API coupling, flaky CI và shared database có thể làm team cùng phòng vẫn chậm. **Cải tiến:** kiểm tra kỹ thuật, interface và flow, không chỉ “team bonding”.

## 30. Workshop thực hành 90 phút: bảo vệ một đề án Agile phân tán

Workshop này là **bài tập tổng hợp**, không phải sự kiện bắt buộc của Scrum/Kanban. Người học có thể thực hiện theo nhóm 4–8 người đóng vai **Product Owner, Developers, Scrum Master, platform/service owner và người quan tâm đến an toàn sản phẩm**.

### Tình huống đầu vào

Một sản phẩm học trực tuyến có **hai Scrum Teams phân tán**. Người học gặp lỗi Học tiếp, UI và API được nghiệm thu riêng, staging lỗi và Product Backlog hiện có hai bản sao với thứ tự mâu thuẫn. Những người ở hai địa điểm thường chờ một ngày để làm rõ contract. Lãnh đạo muốn “tăng 30% velocity” và thêm cuộc họp điều phối hằng ngày.

| Bước | Thời lượng | Hoạt động | Đầu ra |
| --- | ---: | --- | --- |
| **1. Nhận diện bối cảnh** | 10 phút | Phân biệt một sản phẩm/nhiều sản phẩm, thành viên phân tán và dependency | Sơ đồ ownership và giả định |
| **2. Chọn mục tiêu giá trị** | 10 phút | Viết Product Goal và problem statement Học tiếp | Outcome người học cần kiểm chứng |
| **3. Chẩn đoán flow** | 10 phút | Theo dấu một PBI, ghi Review/staging/API wait | Bản đồ dòng giá trị |
| **4. Thiết kế ownership** | 10 phút | Thống nhất PO/Backlog/DoD, Sprint Goals và service owners | Cấu trúc trách nhiệm |
| **5. Làm working agreement** | 10 phút | Async/sync, overlap, decision log và escalation | Thỏa thuận có thể thử |
| **6. Thiết kế lát cắt và tests** | 15 phút | Viết một PBI, Gherkin và integration/contract checks | Evidence cho một Increment |
| **7. Lập kế hoạch thử** | 10 phút | Chọn 30–60–90 milestones và owner | Bản triển khai có giới hạn |
| **8. Chọn metric/guardrails** | 10 phút | Flow, quality, user outcome và sustainability | Metric contract ngắn |
| **9. Giả lập blocker** | 5 phút | Một API conflict hoặc incident xuất hiện | Trade-off và decision log |

### Dữ liệu giả định cho nhóm phân tích

| Chỉ số | Hiện trạng | Câu hỏi cần hỏi thêm |
| --- | ---: | --- |
| Median cycle time feature | 13 ngày làm việc | Start/finish và DoD được định nghĩa thế nào? |
| Median Review/Verify wait | 4 ngày | Chờ người, CI hay contract? |
| WIP trung bình | 12 items | Có items bị giấu ở board khác không? |
| Median time-to-staging | 3 ngày | Tác vụ nào lặp và có thể self-service? |
| Số lỗi checkpoint nghiêm trọng | Chưa có baseline tin cậy | Có monitoring và incident records phù hợp? |
| Task success Học tiếp mobile | Chưa xác định eligibility | Cần đo bằng lượt/phiên/người? |
| Giờ họp ngoài giờ | Có khi xảy ra | Độ trễ, người bị ảnh hưởng và cách thay thế? |

### Ba quyết định bắt buộc trong phần trình bày

1. **Tại sao cần một Product Backlog/PO/DoD chung trong bối cảnh đã xác định?** Nếu nhóm cho rằng đây thực chất là nhiều sản phẩm, phải chứng minh product boundaries.
2. **Khi nào dùng async và khi nào yêu cầu đồng bộ?** Phải có ví dụ incident, hợp đồng API và câu hỏi thường lệ.
3. **Tại sao không dùng mục tiêu “velocity +30%”?** Phải đề xuất một outcome/flow metric có định nghĩa, chất lượng và guardrails.

### Rubric đánh giá đề án

| Tiêu chí | Cần có để đạt yêu cầu |
| --- | --- |
| **Đúng bối cảnh** | Không nhầm distributed team và nhiều sản phẩm; product boundary giải thích được |
| **Giá trị** | Product Goal và một user outcome quan sát được |
| **Scrum/Kanban/XP** | Chọn đúng vai trò/thực hành, không dùng tên hình thức |
| **Remote collaboration** | Có working agreement, decision log và chính sách incident |
| **Integration/quality** | DoD, contract/API checks, CI và dữ liệu an toàn |
| **Thực thi** | Lộ trình, owner, capacity/phụ thuộc và trường hợp thay đổi |
| **Bằng chứng** | Baseline hoặc kế hoạch thu, metric contract, guardrails, review |
| **Tính thích ứng** | Biết khi nào giữ, sửa, dừng hoặc mở rộng cơ chế |

### Câu hỏi phản biện mở rộng

Nếu hai nhóm áp dụng kế hoạch trên nhưng **CI tốt lên mà task success không đổi**, có phải thất bại toàn bộ không? **Không nhất thiết:** technical capability có thể tiến bộ, nhưng giả thuyết thiết kế sản phẩm chưa đúng hoặc chưa đủ exposure. Cần **không nhầm hai vòng feedback**, giữ điều kỹ thuật có ích và đổi hướng sản phẩm dựa trên người dùng.

## 31. Bài tập tự kiểm tra có gợi ý đáp án

### Bài tập A — Chọn đúng cấu hình đội

Ba tình huống:

1. Một Product Owner, một Scrum Team gồm Developers ở ba địa điểm cùng quản lý một Product Backlog.
2. Ba Scrum Teams cùng tạo một ứng dụng học tập, nhưng mỗi team tự giữ Product Goal, Product Owner và DoD khác nhau.
3. Một sản phẩm học tập và một sản phẩm thanh toán độc lập cùng phụ thuộc identity API.

Hãy đề xuất mô hình ownership, cách phối hợp và lý do **không nên áp cùng cấu trúc** cho cả ba.

**Gợi ý:** (1) một Scrum Team phân tán với working agreements tốt; (2) nếu thật sự cùng một sản phẩm, Product Goal, Product Backlog, Product Owner và DoD chung theo Scrum Guide, có Increment tích hợp; (3) product ownership riêng và service contracts/cross-product decisions khi cần.

### Bài tập B — Viết working agreement bất đồng bộ

Team gồm thành viên ở nhiều địa điểm, có khoảng thời gian trực tiếp trùng nhau rất ngắn. Một API decision thường bị để trong DM và khi một người nghỉ phép, công việc tắc ba ngày.

Viết **sáu điều** của working agreement, ít nhất bao gồm nguồn sự thật, async update, phản hồi thường lệ, workshop khi bất định cao, handoff và escalation.

**Gợi ý:** Nêu **ai cập nhật ở đâu, thông tin tối thiểu, thời gian đáp ứng có căn cứ, quyền quyết định và cách người không dự họp đọc lại kết luận**. Tránh cam kết mọi người online 24/7.

### Bài tập C — Chia một user story end-to-end

Story ban đầu: “Xây toàn bộ dashboard tiến độ học tập”. Team A định làm UI trong Sprint 1, Team B làm database trong Sprint 2, Team C tích hợp Sprint 3.

Hãy chia thành **ít nhất ba lát cắt giá trị có thể kiểm chứng**, xác định acceptance examples và điều kiện an toàn không được hoãn.

**Gợi ý:** Học viên có checkpoint hợp lệ mở đúng bài; người không có checkpoint bắt đầu đúng; trường hợp lỗi/xung đột có hành vi phù hợp. **Authorization và dữ liệu đúng** là điều kiện cho mọi lát cắt có liên quan, không đợi phần cuối.

### Bài tập D — Scrum nhiều nhóm trên một sản phẩm

Hai Scrum Teams làm một sản phẩm: Team A có Sprint Goal “UI Học tiếp đúng trải nghiệm”; Team B có Sprint Goal “Checkpoint API đúng quyền”. Cả hai báo Done theo DoD riêng, nhưng E2E chưa chạy.

1. Thành phần chung nào Scrum Guide yêu cầu?
2. Hai Sprint Goals riêng có phải vấn đề không?
3. Khi nào Increment thực sự đủ điều kiện?
4. Cần bổ sung CI/contract checks và phối hợp gì?

**Gợi ý:** Product Goal/Backlog/PO/DoD chung; Sprint Goals riêng có thể bổ trợ. Không gọi phần chưa tích hợp là Increment Done nếu chưa đạt DoD chung.

### Bài tập E — Kanban support và SLE

Platform team có workflow support thường lệ và SLE giả định **85% requests hoàn tất trong tối đa bốn ngày làm việc**. Một request đã chờ 3,5 ngày; request khác liên quan lộ dữ liệu người dùng.

1. Request đầu đã chắc chắn trễ chưa?
2. Cần xem age/blocked reason và owner thế nào?
3. Vì sao incident không nằm trong cùng policy FIFO?
4. Nếu first response nhanh nhưng consumer vẫn bị chặn, nên đo thêm gì?

**Gợi ý:** SLE là kỳ vọng xác suất, dùng để quản lý age; incident theo severity. Đo **time-to-unblock và tác động end-to-end**, không chỉ số ticket đóng.

### Bài tập F — Dự báo throughput

Throughput của bốn tuần có PBIs tương đồng: **3, 5, 4, 4 items/tuần**. Còn 16 items tương đồng.

1. Throughput trung bình là bao nhiêu?
2. Nếu chia thô, ước lượng bao nhiêu tuần?
3. Vì sao không nên báo một ngày chắc chắn?
4. Nếu một API dependency ngoài team bị trễ, thay đổi forecast và thông báo ra sao?

**Gợi ý:** \(16/4=4\) items/tuần và \(16/4=4\) tuần theo phép chia thô; phải xét biến thiên, loại việc, capacity và chất lượng; cập nhật forecast thay vì giấu blocker.

### Bài tập G — Dữ liệu flow và ranh giới đo

Một team trước kia tính Done khi đạt API/E2E checks, sau khi “áp dụng Agile” đổi Done thành PR merged. Median cycle time báo cáo từ 12 ngày còn 6 ngày.

1. So sánh ấy có đáng tin không?
2. Làm sao giữ cả mốc PR merged và Increment đạt DoD để phân tích?
3. Quality guardrails nào cần xem?
4. Nếu team khác vẫn dùng DoD cũ, có thể xếp hạng hai team không?

**Gợi ý:** Không trộn khác định nghĩa; ghi metric contract riêng, giữ DoD chung khi cùng sản phẩm, xem chất lượng, integration và product outcome.

### Bài tập H — API conflict giữa các múi giờ

Team mobile ở địa điểm A phát hiện checkpoint cũ có thể ghi đè bản mới; API owner ở địa điểm B đang ngoài giờ. Có người đề nghị tự chỉnh schema production ngay để kịp demo.

Hãy viết **một tin nhắn async quyết định** có: mục tiêu, bằng chứng, lựa chọn, owner, deadline hợp lý và guardrails. Nêu **khi nào phải mở incident ngay**.

**Gợi ý:** Nếu đã có mất dữ liệu/sai quyền production thì severity policy ngay; nếu chưa khẩn, ghi quyết định vào nguồn chung và collaboration đúng lúc. Không tự ý phá contract hoặc bỏ bảo vệ.

### Bài tập I — Phân biệt code, deploy, release và outcome

Một feature Học tiếp được merge hôm thứ Hai, deployed staging thứ Ba, deployed production dưới flag thứ Tư, bật thử cho nhóm đủ điều kiện thứ Sáu và tới tuần sau mới có mẫu task success.

1. Mốc nào là code merge, deploy, release/exposure?
2. Khi nào có thể nói Increment đạt DoD?
3. Vì sao thứ Tư chưa đủ chứng minh user value?
4. Quyết định nào có thể được đưa ra khi task success thấp trên mobile?

**Gợi ý:** Các mốc không thay nhau; DoD theo tiêu chuẩn đã xác nhận; product feedback cần người dùng được exposure và đủ dữ liệu.

### Bài tập J — Review bottleneck không hết khi thêm họp

Hai Scrum Teams cùng sản phẩm phải chờ một reviewer chung ba ngày cho mỗi thay đổi. Tổ chức thêm một cuộc họp điều phối hằng ngày, nhưng waiting time không đổi.

1. Giả thuyết nguyên nhân cần xem là gì?
2. Có thể giảm demand hoặc tăng capacity phù hợp bằng cách nào?
3. Review nào phải giữ vì rủi ro?
4. Đo cải tiến bằng gì ngoài số buổi họp?

**Gợi ý:** PR nhỏ, policy risk-based, API tests, coaching, backup, service ownership; time-to-unblock, quality và developer feedback.

### Bài tập K — Nhịp bền vững

Một Scrum Team phân tán có Daily Scrum vào giờ rất muộn của một nhóm thành viên. Họ còn phải trả lời chat thường lệ trong vài phút mọi ngày, kể cả ngày nghỉ.

1. Quy định nào gây rủi ro tới sustainable pace?
2. Có thể thay đổi giờ họp, async prep và class of service ra sao?
3. Incident on-call khác yêu cầu thường lệ ở điểm nào?
4. Cần theo dõi kết quả gì mà không giám sát chi tiết con người?

**Gợi ý:** Xoay phiên/thiết kế overlap công bằng, response expectations hợp lý, on-call có bù đắp và backup, theo dõi gián đoạn/overtime tổng hợp.

### Bài tập L — Tính tỷ lệ self-service thực

Trong tháng có 100 tác vụ tạo staging đủ điều kiện, 80 tác vụ hoàn tất, trong đó 65 tác vụ tự hoàn tất không cần người platform can thiệp.

1. Tỷ lệ tác vụ hoàn tất?
2. Self-service success tính trên tổng tác vụ?
3. 65/80 diễn giải khác 65/100 ra sao?
4. Có thể kết luận 65% Developers tự chủ không?

**Gợi ý:** 80%, 65%; 65/80 = 81,25% **trong số tác vụ đã hoàn tất**, bỏ qua tác vụ thất bại. Chưa biết số người duy nhất.

### Bài tập M — Lựa chọn cách áp dụng Agile

Một doanh nghiệp có 4 Scrum Teams trên **hai sản phẩm**, 1 platform support team và 1 nhóm chuyên gia data. Lãnh đạo muốn áp một lịch Sprint, một Product Backlog và một velocity target toàn công ty.

Hãy đề xuất cấu hình **ownership, Scrum/Kanban, platform/self-service và cơ chế cross-product** phù hợp, đồng thời giải thích **điều gì thực sự cần chung và điều gì không**.

**Gợi ý:** Product Goal/Backlog/PO/DoD theo từng sản phẩm; các team thuộc cùng một sản phẩm dùng chung những thành phần Scrum cần thiết, platform có thể Kanban theo demand, cross-product coordination cho hợp đồng/capacity, không so velocity.

### Bài tập N — Ra quyết định giữ, sửa hoặc dừng

Sau 60 ngày, CI reliability tốt hơn và thời gian chờ review giảm, nhưng số giờ họp ngoài giờ tăng và người học trên mobile vẫn mở nhầm bài.

1. Cải tiến nào nên cân nhắc giữ?
2. Quy tắc remote nào nên sửa?
3. Giả thuyết product nào cần kiểm tra lại?
4. Có đủ bằng chứng để “scale toàn tổ chức” chưa?

**Gợi ý:** Giữ kỹ thuật/flow có bằng chứng, sửa overlap/sync không bền vững, nghiên cứu mobile UX/checkpoint, chưa nhân rộng mô hình nếu guardrails và outcome chưa đạt.

### Bài tập O — Chuyển yêu cầu mơ hồ thành đề án

Phát biểu của lãnh đạo:

> “Đưa mọi team vào Agile càng sớm càng tốt, họp sync mỗi ngày, tăng 30% tốc độ và chuyển sang remote-first.”

Hãy viết lại thành đề xuất gồm **sản phẩm và vấn đề, nhóm liên quan, quyền quyết định, mục tiêu, thử nghiệm, đo flow/quality/user value, guardrails và review 30–60–90 ngày**.

**Gợi ý:** Không tự hứa tăng 30% nếu thiếu baseline; chọn một dòng giá trị, working agreement có bảo vệ giờ nghỉ và CI/DoD, xây giả thuyết có thể bị bác bỏ.

## 32. Checklist đánh giá một đề án Agile phân tán hoặc nhiều nhóm

### A. Bối cảnh và định hướng

- [ ] Đã phân biệt **một Scrum Team phân tán, nhiều Scrum Teams cùng một sản phẩm và nhiều sản phẩm liên kết**.
- [ ] Người dùng và **Product Goal** được mô tả rõ, không chỉ “đổi sang Agile”.
- [ ] Có một hành trình hoặc **value stream** để theo dõi giá trị end-to-end.
- [ ] Đã kiểm tra **nguồn chờ và rủi ro thực**, không mặc định làm việc từ xa là nguyên nhân mọi vấn đề.
- [ ] Có **baseline hoặc kế hoạch đo**, nêu giới hạn dữ liệu.
- [ ] Không chọn framework chỉ vì số người, chứng nhận hay tên gọi phổ biến.

### B. Sản phẩm, Scrum và backlog

- [ ] Khi nhiều Scrum Teams cùng một sản phẩm, **Product Goal, Product Backlog, Product Owner và Definition of Done** chung.
- [ ] Mỗi Scrum Team có **Sprint Goal/Sprint Backlog và khả năng tự điều chỉnh kế hoạch** của mình.
- [ ] Không dùng master backlog giả cho nhiều sản phẩm độc lập chỉ vì có API liên quan.
- [ ] Product Owner có quyền sắp thứ tự Product Backlog dựa trên giá trị và feedback.
- [ ] User stories được **chia theo lát cắt có thể kiểm chứng** chứ không chỉ các lớp kỹ thuật.
- [ ] Acceptance examples được hiểu chung bởi Developers và người có kiến thức nghiệp vụ.
- [ ] Refinement được thực hiện **đúng lúc và đủ sâu** để làm rõ rủi ro, phụ thuộc và mục tiêu.
- [ ] Sprint Review dẫn tới **quyết định về sản phẩm**, không chỉ báo cáo output.

### C. Làm việc phân tán

- [ ] Có **nguồn sự thật chung** cho backlog, DoD, contracts, quyết định và blockers.
- [ ] Working agreement có quy tắc **async, sync, owner, thời hạn phản hồi và escalation**.
- [ ] Chọn **overlap window bền vững/công bằng**, không ép một nhóm liên tục làm ngoài giờ.
- [ ] Quyết định quan trọng được tóm tắt **bằng văn bản với lý do và bước tiếp**.
- [ ] Người không tham dự cuộc họp vẫn có thể hiểu và phản hồi trong phạm vi phù hợp.
- [ ] Review/pairing từ xa có mục tiêu và timebox, không bắt online/camera liên tục.
- [ ] Có chính sách **nghỉ phép, người dự phòng và handoff**, không phụ thuộc một cá nhân.
- [ ] Incident có **kênh/severity/on-call** riêng, không chờ phản hồi chat thường lệ.

### D. Kỹ thuật và chất lượng

- [ ] Mọi thay đổi liên quan được **tích hợp và kiểm tra sớm**, không dồn tới cuối Sprint.
- [ ] **Definition of Done** phản ánh chất lượng của Increment chung, không hạ để kịp deadline.
- [ ] API producers/consumers có **contract, versioning, semantics và compatibility tests** khi cần.
- [ ] CI đáng tin và có owner khi đỏ, không chỉ chạy build qua loa.
- [ ] Authorization được kiểm tra **ở server**, secrets và dữ liệu nhạy cảm được bảo vệ.
- [ ] Migration dữ liệu có kế hoạch compatibility/kiểm tra/khôi phục phù hợp.
- [ ] Đã phân biệt **code complete, Done, deploy, release và outcome**.
- [ ] Release có giám sát, người có quyền dừng và incident path phù hợp rủi ro.
- [ ] Không giả định rollback code có thể khôi phục dữ liệu đã bị sửa/xóa.

### E. Flow, phụ thuộc và năng lực

- [ ] Workflow có start/finish rõ, work items bị chặn **được hiển thị trung thực**.
- [ ] Có chính sách **kiểm soát WIP và ưu tiên hoàn tất**, không chỉ khuyến khích bắt đầu thêm.
- [ ] Theo dõi **work item age, throughput và cycle time distribution** đúng đơn vị.
- [ ] SLE nếu dùng được hiểu là **kỳ vọng xác suất**, không bảo đảm 100% mọi request.
- [ ] Mỗi dependency quan trọng có **requester, provider, output, owner và mốc xem lại**.
- [ ] Không sao chép toàn bộ tasks sang board điều phối mà thiếu quyết định.
- [ ] Platform/self-service và specialists có **chính sách hỗ trợ, quyền, capacity và guardrails**.
- [ ] Capacity/forecast tính đến **nghỉ phép, incident, review, học hỏi và biến thiên**.
- [ ] Không dùng story points, số commit, số chat hoặc trạng thái online để xếp hạng người.

### F. Kết quả và cải tiến liên tục

- [ ] Có **metric contract** cho những số đo được dùng ra quyết định.
- [ ] Có **quality/security guardrails và điều kiện dừng** khi rủi ro nghiêm trọng xuất hiện.
- [ ] Có **product outcome** được kiểm chứng với người dùng phù hợp, không chỉ deploy nhiều.
- [ ] Có quan sát **làm thêm giờ, interruptions, cognitive load và trải nghiệm nhóm** ở mức bảo vệ riêng tư.
- [ ] Đã xem **mẫu số, cohort, loại công việc và lời giải thích thay thế** trước khi suy nhân quả.
- [ ] Các cải tiến có **giả thuyết, owner, timebox và mốc đánh giá**.
- [ ] Lộ trình 30–60–90 ngày tạo **kiến thức và quyết định**, không chỉ số buổi training.
- [ ] Có quyền **giữ, sửa, bỏ hoặc mở rộng** cơ chế, không ép tất cả nhóm giống nhau.
- [ ] Các quyết định về Product Backlog, CI/DoD, policy và platform có người **đủ thẩm quyền**.

**Cách dùng checklist:** Không coi đây là bộ chứng nhận “đạt Agile” hoặc bắt mọi ô phải áp cho mọi bối cảnh. Chọn **những mục liên quan trực tiếp tới rủi ro, sản phẩm và team đang xét**, xác minh bằng công việc thực, rồi cải tiến những điểm có lợi ích rõ.

## 33. Tài liệu tham khảo và tổng kết

- [Agile Manifesto](https://agilemanifesto.org/) và [12 nguyên tắc Agile](https://agilemanifesto.org/principles.html): hợp tác, phần mềm hoạt động, phản hồi sớm, thay đổi và nhịp phát triển bền vững.
- [The Scrum Guide](https://scrumguides.org/): Product Goal, Sprint Goal, Product Backlog, Product Owner, Definition of Done, Increment, các sự kiện Scrum và nhiều Scrum Teams trên một sản phẩm.
- [The Kanban Guide](https://kanbanguides.org/): Definition of Workflow, WIP, throughput, cycle time, work item age và Service Level Expectation.
- Kent Beck và Cynthia Andres, *Extreme Programming Explained: Embrace Change*, ấn bản 2 (2004): TDD, CI, refactoring, pairing, small releases và feedback kỹ thuật.
- Jeff Patton, *User Story Mapping* (2014): khám phá hành trình, xây backlog và chọn các lát cắt giá trị tăng dần.
- Matthew Skelton và Manuel Pais, *Team Topologies: Organizing Business and Technology Teams for Fast Flow* (2019): thiết kế team boundaries, cognitive load và interaction modes.
- Nicole Forsgren, Jez Humble và Gene Kim, *Accelerate: The Science of Lean Software and DevOps* (2018): năng lực giao phần mềm, độ tin cậy và kết quả tổ chức.
- Jez Humble và David Farley, *Continuous Delivery* (2010): xây pipeline, kiểm thử, triển khai thay đổi an toàn và thường xuyên.
- Donald G. Reinertsen, *The Principles of Product Development Flow* (2009): hàng đợi, WIP, biến thiên và kinh tế của dòng phát triển sản phẩm.
- [DORA](https://dora.dev/): nguồn nghiên cứu/thực hành về năng lực giao phần mềm, reliability và cải tiến liên tục.
- [Google SRE Books](https://sre.google/books/): dịch vụ đáng tin, on-call, monitoring và incident management.
- [Nexus Guide](https://www.scrum.org/resources/nexus-guide), [LeSS](https://less.works/), [Scrum@Scale](https://www.scrumatscale.com/), [SAFe](https://scaledagileframework.com/): tư liệu để nghiên cứu những phương án phối hợp nhiều nhóm khi cần; không phải danh sách bắt buộc.

### Năm nguyên tắc để đưa đề án vào thực tế

**1. Giữ một hướng giá trị rõ ràng.** Với nhiều Scrum Teams trên cùng một sản phẩm, cùng Product Goal, Product Backlog, Product Owner và DoD. Với nhiều sản phẩm độc lập, giữ boundaries đúng và điều phối bằng interfaces/decisions.

**2. Xây sự minh bạch phù hợp với phân tán.** Quyết định, hợp đồng, backlog và cách xử lý blocker phải có nguồn chung; dùng async để tiết kiệm chờ, dùng đồng bộ khi cần hiểu và quyết định, bảo vệ giờ nghỉ.

**3. Tích hợp và kiểm chứng sớm.** Vertical slices, CI, contract/API tests, feedback kỹ thuật và Definition of Done giúp nhiều nhóm tạo **Increment thực**, không chỉ báo Done riêng.

**4. Quản lý dòng và chất lượng toàn hệ thống.** Nhìn WIP, work item age, cycle time, time-to-unblock, reliability, dữ liệu người dùng và nhịp làm việc; không tối ưu story points, số cuộc họp hoặc mức bận cá nhân.

**5. Mở rộng theo bằng chứng.** Bắt đầu với một value stream có ranh giới rõ, thử working agreement và năng lực kỹ thuật phù hợp, đánh giá 30–60–90 ngày, rồi giữ/sửa/dừng/mở rộng theo kết quả. Không biến một mô hình tổ chức thành khuôn bất biến.

**Kết luận:** Áp dụng Agile cho nhóm phân tán hoặc nhiều nhóm cùng sản phẩm là bài toán **thiết kế sự cộng tác và dòng giá trị có trách nhiệm**, không chỉ là chọn một framework. Một đề xuất tốt làm rõ **người dùng cần gì, ai quyết định điều gì, Increment được tích hợp và bảo vệ thế nào, mọi người trao đổi khi không cùng nơi/giờ ra sao, và bằng chứng nào cho biết cách làm đang tốt hơn**.

**Điểm cần nhớ:** **Cùng định hướng sản phẩm, minh bạch qua khoảng cách, chất lượng được tích hợp, phản hồi đến sớm và chính sách được sửa theo bằng chứng** — đó là cách các nhóm phân tán hoặc nhiều nhóm có thể thực hành Agile để **giao sản phẩm tăng dần, thích ứng và cải tiến liên tục**.
