# Đối chiếu quyết định của nhóm với bốn giá trị cùng mười hai nguyên tắc Agile

> **Thông điệp chính:** Agile không phải một bộ nghi thức có thể được chứng nhận chỉ bằng việc tổ chức Sprint, viết user story hoặc dựng bảng Kanban. Một nhóm phát triển phần mềm thực hành Agile khi **ra quyết định có chủ đích, kiểm tra tác động lên con người và giá trị người dùng, giao phần mềm đáng tin, học từ phản hồi và thay đổi cách làm khi có bằng chứng mới**. Bốn giá trị và mười hai nguyên tắc của *Manifesto for Agile Software Development* là **lăng kính để xem xét lựa chọn và đánh đổi**, không phải danh sách điều khoản để chấm điểm cơ học.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Trình bày đúng tinh thần **bốn giá trị Agile**: con người và tương tác; phần mềm hoạt động; cộng tác với khách hàng; phản hồi với thay đổi — đồng thời hiểu vế bên phải **vẫn có giá trị**.
2. Diễn giải **mười hai nguyên tắc Agile** theo các nhóm: tạo giá trị, phản hồi sớm, cộng tác, động lực, giao tiếp, đo tiến độ, nhịp bền vững, chất lượng kỹ thuật, sự đơn giản, tự tổ chức và cải tiến.
3. Phân biệt **quan sát/sự kiện, diễn giải, giả định, lựa chọn, ràng buộc bắt buộc, quyết định và kết quả** khi xem lại một quyết định của nhóm.
4. Dùng **ma trận bốn giá trị × mười hai nguyên tắc** để đặt câu hỏi đúng và nhận ra các mâu thuẫn, thay vì kết luận tùy tiện “đội đã/không Agile”.
5. Đánh giá các quyết định phổ biến: chốt backlog, thay đổi Sprint Goal, chia user story, giảm kiểm thử để kịp hạn, xử lý sự cố, ưu tiên tài liệu, review code và phản hồi người dùng.
6. Vận dụng Scrum, Kanban và XP **đúng tầng mục đích**, tránh đồng nhất Agile với một framework hoặc công cụ.
7. Viết **decision record ngắn** nêu mục tiêu sản phẩm, phương án, bằng chứng, giá trị/nguyên tắc liên quan, rủi ro, người có thẩm quyền, thử nghiệm và mốc xem lại.
8. Chọn phép đo phù hợp giữa **outcome, Increment/DoD, WIP, throughput, cycle time, work item age, chất lượng và nhịp làm việc**, không dùng metric làm mục tiêu tự thân.
9. Phân tích một tình huống xuyên suốt về **luồng lưu và tiếp tục bài học** với người dùng, Product Owner, Developers, đội vận hành và stakeholder ở nhiều múi giờ.
10. Đề xuất một thay đổi có thể kiểm chứng khi quyết định hiện tại **đi ngược giá trị/nguyên tắc** hoặc không tạo ra kết quả như dự kiến.

## 2. Tình huống mở đầu: “Chúng ta đã làm Scrum đúng quy trình”

Một Scrum Team phát triển nền tảng học trực tuyến tuyên bố:

> “Chúng ta đã Agile: Sprint Planning đủ người, Daily Scrum đều, backlog có story points, Sprint Review có slide và dashboard velocity tăng.”

Nhưng trong ba Sprint gần đây:

- Product Owner nhận phản hồi rằng người học **không chắc tiến độ đã được lưu** khi mạng chập chờn, nhưng backlog vẫn ưu tiên thay màu giao diện vì kế hoạch quý đã chốt.
- Một yêu cầu đổi trạng thái API được thảo luận trong cuộc gọi, song Developer ở múi giờ khác không dự, không thấy **acceptance criteria** cập nhật.
- Nhiều PBI được báo “xong code” cuối Sprint; integration tests chờ môi trường, nên chưa đạt **Definition of Done**.
- Đội bỏ qua refactoring và test đường lỗi để “giữ velocity”, dẫn đến lỗi hồi quy và sự cố production.
- Developers liên tục làm thêm giờ; Retrospective ghi “cần giao tiếp tốt hơn” nhưng không có thay đổi cách làm.

Một bên nói “đội chưa tuân thủ Scrum”, bên khác nói “Agile cho phép linh hoạt nên làm thế là đúng”. Hai nhận định này đều **thiếu đánh giá quyết định và kết quả cụ thể**.

Đối chiếu với Agile Manifesto cần hỏi:

1. Những **quyết định thật** nào tạo ra các kết quả trên?
2. Chúng ưu tiên điều gì, đánh đổi điều gì, có bị ràng buộc bắt buộc nào không?
3. Có bằng chứng nào cho thấy phần mềm tạo giá trị và người dùng được lắng nghe?
4. Các quyết định phù hợp hoặc xung đột với **giá trị và nguyên tắc nào**?
5. Nếu thay cách làm, **điều gì sẽ được kiểm chứng**, vào lúc nào, bằng chỉ báo nào?

**Không thể đánh giá tính Agile của nhóm chỉ bằng số cuộc họp, số ticket, velocity hay tên công cụ.**

## 3. Hiểu đúng Manifesto trước khi dùng để ra quyết định

### 3.1. Bốn giá trị là các ưu tiên tương đối, không phải lệnh cấm

Năm 2001, Manifesto for Agile Software Development nêu bốn cặp giá trị. Có thể diễn giải bằng tiếng Việt:

| Ưu tiên cao hơn | Vế vẫn có giá trị | Câu hỏi khi quyết định |
|---|---|---|
| **Cá nhân và tương tác** (*Individuals and interactions*) | Quy trình và công cụ (*Processes and tools*) | Công cụ/quy trình đang hỗ trợ con người phối hợp, hay buộc họ phục vụ công cụ? |
| **Phần mềm hoạt động** (*Working software*) | Tài liệu đầy đủ/đồ sộ (*Comprehensive documentation*) | Chúng ta có Increment hoạt động và bằng chứng chất lượng, hay chỉ có báo cáo tiến độ? |
| **Cộng tác với khách hàng** (*Customer collaboration*) | Đàm phán hợp đồng (*Contract negotiation*) | Chúng ta có học từ người dùng/stakeholder, đồng thời tôn trọng nghĩa vụ thực tế? |
| **Phản hồi với thay đổi** (*Responding to change*) | Tuân theo kế hoạch (*Following a plan*) | Kế hoạch đang là giả thuyết có thể điều chỉnh, hay ràng buộc dù bằng chứng đã khác? |

Manifesto cũng nói rõ **các yếu tố ở vế phải có giá trị**, nhưng những yếu tố vế trái được coi trọng hơn. Vì vậy:

- Không được dùng “con người hơn quy trình” để bỏ kiểm soát bảo mật hoặc biến quyết định thành trao đổi miệng không truy tìm được.
- Không được dùng “phần mềm hoạt động hơn tài liệu” để bỏ acceptance criteria, API contract, runbook hay bằng chứng tuân thủ bắt buộc.
- Không được dùng “cộng tác hơn hợp đồng” để xem nhẹ điều khoản đã ký hoặc thẩm quyền phê duyệt.
- Không được dùng “thích ứng hơn kế hoạch” để thay Sprint Goal vô nguyên tắc hoặc không dự báo hậu quả của thay đổi.

### 3.2. Mười hai nguyên tắc bổ sung chiều sâu cho bốn giá trị

Nếu chỉ nhớ bốn cặp, một đội có thể viện “linh hoạt” để bỏ kế hoạch hoặc viện “con người” để họp không ngừng. **Mười hai nguyên tắc** làm rõ điều Agile muốn đạt: **khách hàng nhận giá trị sớm, phần mềm chạy được, thay đổi được đón nhận, cộng tác liên tục, con người được tin tưởng, làm việc bền vững, thiết kế kỹ thuật tốt và thường xuyên tự điều chỉnh**.

Các phần tiếp theo **diễn giải ngắn theo ý nghĩa**, không sao chép nguyên văn Manifesto. Số thứ tự **P1–P12** được giữ để người học đối chiếu với [12 Principles](https://agilemanifesto.org/principles.html).

### 3.3. Giá trị là định hướng, nguyên tắc là câu hỏi, thực hành là lựa chọn

| Tầng | Ví dụ | Không nên nhầm thành |
|---|---|---|
| **Giá trị** | Đặt tương tác có ý nghĩa cao hơn thủ tục hình thức | “Mọi quy trình đều xấu” |
| **Nguyên tắc** | Kinh doanh và kỹ thuật phối hợp thường xuyên; giao sản phẩm hoạt động sớm | “Bắt buộc họp hai giờ mỗi ngày” |
| **Thực hành** | Three Amigos, pair programming, user story mapping, CI | “Thực hành nào cũng bắt buộc để Agile” |
| **Framework/phương pháp** | Scrum, Kanban, XP | “Làm Scrum là tự động đạt 12 nguyên tắc” |
| **Công cụ** | Backlog board, Git, CI, video call, dashboard | “Cài công cụ là đã thay đổi văn hóa và outcome” |
| **Bằng chứng** | Người học tiếp tục bài thành công; PBI đạt DoD | “Tỷ lệ ticket chuyển Done bằng giá trị thực” |

Một cách lựa chọn đúng có thể **sử dụng nhiều thực hành khác nhau** để phục vụ cùng một giá trị, tùy sản phẩm và điều kiện nhóm.

### 3.4. Cách đọc một phát biểu Agile gây tranh luận

Lấy câu: “Working software hơn tài liệu nên không cần cập nhật API contract”.

Kiểm tra:

1. **Mục tiêu:** có phải giảm thời gian làm tài liệu không tạo giá trị?
2. **Hệ quả:** thiếu API contract làm frontend/backend hiểu khác nhau và code không tích hợp?
3. **Người chịu ảnh hưởng:** người dùng nhận thông báo sai, reviewer không xác minh được?
4. **Ràng buộc:** có yêu cầu bảo mật/hợp đồng bắt buộc cần ghi nhận?
5. **Phương án khác:** cập nhật **hợp đồng ngắn, có version và test** thay vì viết tài liệu dài.

Kết luận: **không cần tài liệu thừa** là hợp tinh thần Agile; **bỏ thông tin thiết yếu để phần mềm không còn hoạt động đáng tin** lại mâu thuẫn chính giá trị ưu tiên phần mềm hoạt động.

## 4. Bốn giá trị như bốn câu hỏi khi quyết định

### 4.1. V1 — Cá nhân và tương tác hơn quy trình và công cụ

**Tình huống:** Một Developer backend cần hiểu ngoại lệ timeout. Nhóm yêu cầu tạo một ticket dài, chờ ba cấp duyệt rồi mới được hỏi Product Owner dù Product Owner và Tester đang sẵn sàng.

**Vấn đề cần xem:** thủ tục hiện tại có thực sự bảo vệ chất lượng/quyền quyết định hay chỉ gây thời gian chờ?

**Phương án có thể thử:**

- Một cuộc trao đổi ngắn giữa Product Owner, Developers, Tester để làm rõ ví dụ.
- Sau đó cập nhật acceptance criteria và API contract nơi người vắng mặt có thể đọc.
- Giữ các kiểm soát/thẩm quyền bắt buộc, không dùng gọi miệng để thay phê duyệt.

**Dấu hiệu tốt:** ít vòng hỏi lại, work item age giảm, hai bên dùng cùng ví dụ và không tăng lỗi chất lượng.

**Cạm bẫy:** biến “cần tương tác” thành họp liên tục hoặc phụ thuộc người nói nhiều nhất. Tương tác có giá trị phải **giúp người khác hành động** và để lại kết luận phù hợp.

### 4.2. V2 — Phần mềm hoạt động hơn tài liệu đồ sộ

**Tình huống:** Cuối Sprint, báo cáo ghi “85% tính năng lưu tiến độ đã hoàn thành”, nhưng E2E không chạy và không có Increment đáp ứng DoD.

**Vấn đề:** phần trăm trên dashboard không chứng minh người học có thể lưu/tiếp tục bài an toàn.

**Phương án có thể thử:**

- Chia PBI thành lát dọc nhỏ, có hành vi người dùng kiểm chứng được.
- Tích hợp và chạy test thường xuyên, không để kiểm thử vào ngày cuối.
- Cập nhật những tài liệu **thật sự phục vụ vận hành, handoff và bảo vệ người dùng**.
- Không gắn Done khi còn thiếu kiểm tra bắt buộc.

**Dấu hiệu tốt:** Increment có thể sử dụng, feedback thực, DoD đạt, lỗi hồi quy giảm.

**Cạm bẫy:** “đã chạy trên laptop” không tự là **working software** đủ chất lượng và tích hợp theo yêu cầu sản phẩm.

### 4.3. V3 — Cộng tác với khách hàng hơn thương lượng hợp đồng

**Tình huống:** Hợp đồng ban đầu mô tả “lưu tiến độ”, nhưng phản hồi cho thấy người học quan tâm nhất tới **không bị mất tiến độ khi mạng yếu**.

**Vấn đề:** đội có hiểu mục đích người dùng và làm việc với stakeholder để kiểm chứng không, hay chỉ bám danh sách tính năng?

**Phương án có thể thử:**

- Product Owner trao đổi với stakeholders/người học phù hợp.
- Xác định điều có thể thay đổi trong phạm vi hợp đồng, điều cần phê duyệt.
- Thử lát cắt làm rõ trạng thái **CONFIRMED/FAILED/UNKNOWN** và kiểm tra tác dụng.
- Dùng kết quả để điều chỉnh Product Backlog, thông báo rủi ro/chi phí cơ hội minh bạch.

**Dấu hiệu tốt:** ít hiểu sai nhu cầu, phản hồi sớm, outcome người học có xu hướng cải thiện sau đủ dữ liệu.

**Cạm bẫy:** cộng tác không có nghĩa stakeholder có thể đơn phương bỏ yêu cầu pháp lý, bảo mật hoặc cam kết hợp đồng.

### 4.4. V4 — Phản hồi với thay đổi hơn tuân theo kế hoạch

**Tình huống:** Đội dự kiến xây animation cho nút “Tiếp tục”, nhưng test với người học cho thấy luồng lưu tiến độ có lỗi nghiêm trọng.

**Vấn đề:** liệu kế hoạch có được cập nhật theo thông tin mới và mục tiêu giá trị?

**Phương án có thể thử:**

- Nêu bằng chứng và mức ảnh hưởng tới người học.
- Product Owner sắp lại backlog; Developers đánh giá kỹ thuật và Sprint Goal.
- Điều chỉnh phạm vi để bảo vệ chất lượng và mục tiêu, không tùy tiện đổi Sprint Goal.
- Nếu đang có sự cố, xử lý theo chính sách ứng cứu.

**Dấu hiệu tốt:** nhóm phản ứng với tín hiệu đúng mức, không giao lỗi nghiêm trọng chỉ để giữ baseline cũ; stakeholder hiểu đánh đổi.

**Cạm bẫy:** đổi việc mỗi khi có tin nhắn “gấp” không phải thích ứng thông minh; đó có thể là **WIP cao và thiếu cơ chế ưu tiên**.

### 4.5. Một quyết định có thể phục vụ nhiều giá trị

Ví dụ: **xây contract test cho API và cùng làm rõ ví dụ trạng thái lưu**.

| Giá trị | Liên hệ |
|---|---|
 **V1** | Giúp Product Owner, frontend, backend, Tester trao đổi dựa trên cùng ví dụ |
| **V2** | Chuyển quyết định thành kiểm chứng hành vi có thể chạy trên build |
| **V3** | Lấy trải nghiệm thật của người học làm cơ sở cho trạng thái UI |
| **V4** | Khi hợp đồng API thay đổi, test báo khác biệt sớm để điều chỉnh |

Một hành động không nhất thiết “đạt cả bốn giá trị” để được chọn; điều quan trọng là **biết mục tiêu, hậu quả và giới hạn của lựa chọn**.

## 5. Nguyên tắc P1–P3: giá trị sớm, thích ứng và giao phần mềm thường xuyên

### 5.1. P1 — Ưu tiên làm khách hàng hài lòng nhờ giá trị được giao sớm và liên tục

**Diễn giải:** Mục tiêu không phải giao một gói tính năng đồ sộ sau nhiều tháng mà không kiểm tra nhu cầu. Nhóm tìm cách tạo **phần có ích, có thể sử dụng và có thể lấy phản hồi** từ sớm.

**Quyết định minh họa:**

- Lựa chọn A: trong ba tháng xây toàn bộ “hệ thống thông báo học tập thông minh” rồi mới mở cho người dùng.
- Lựa chọn B: giao trước khả năng lưu tiến độ đáng tin ở một luồng bài học, đo lỗi và tỷ lệ quay lại, rồi mới mở rộng nhắc học.

Nếu B đáp ứng giá trị và kiểm soát bắt buộc, nó thường giúp giảm bất định sớm hơn. Tuy nhiên **giao nhỏ không được phép giao phần mềm chưa an toàn, không đạt DoD hoặc gây hại dữ liệu người học**.

**Câu hỏi khi đối chiếu:** “Người dùng nhận **giá trị nào có thể kiểm chứng**, sớm nhất ở đâu, với bằng chứng gì?” Đừng chỉ hỏi “đã đóng bao nhiêu ticket?”.

### 5.2. P2 — Đón nhận yêu cầu thay đổi, kể cả khi việc phát triển đã tiến xa

**Diễn giải:** Thông tin mới về khách hàng, công nghệ hoặc bối cảnh có thể xuất hiện muộn. Nhóm duy trì khả năng **đánh giá và phản hồi với thay đổi có giá trị**, thay vì phủ nhận chỉ vì “đã chốt kế hoạch”.

Ví dụ Product Owner biết người học mất mạng thường xuyên:

- Cách phản ứng không tốt: “Hết quyền thay đổi vì sprint đã khóa.”
- Cách phản ứng cũng không tốt: “Dừng toàn bộ công việc khác ngay dù chưa xác định mức tác động.”
- Cách phản ứng tốt hơn: xác minh tín hiệu, tác động và độ khẩn; xem thay đổi nào giúp Product Goal; thương lượng phạm vi, dự báo và giữ chất lượng.

**Phân biệt:** thay đổi late-stage có thể tốn công, ảnh hưởng hợp đồng hoặc nghĩa vụ thật. **Đón nhận không đồng nghĩa luôn chấp nhận ngay**, mà là *mở cửa cho thông tin có giá trị và ra quyết định có trách nhiệm*.

### 5.3. P3 — Giao phần mềm hoạt động thường xuyên, ưu tiên chu kỳ ngắn

**Diễn giải:** Vòng phản hồi càng dài, giả định sai càng dễ tồn tại lâu. Nhóm tìm cách **tích hợp và đưa ra Increment đủ chất lượng** ở nhịp phù hợp, thay vì đợi mọi thành phần hoàn tất rồi mới kiểm tra.

Ví dụ một đội:

- Chia UI, API và database thành ba giai đoạn nối tiếp, mỗi giai đoạn kết thúc bằng báo cáo → tới cuối quý mới có luồng học hoàn chỉnh.
- Hoặc chia thành **lát dọc**: lưu một điểm tiến độ hợp lệ, đọc lại, xử lý timeout, rồi mở rộng thiết bị.

Nhịp giao có thể là mỗi vài ngày/tuần tùy sản phẩm và rủi ro. **Không có một tần suất phát hành production bắt buộc cho mọi sản phẩm**; nhưng cần chủ động rút ngắn vòng kiểm tra giả định và tích hợp.

### 5.4. Bảng đối chiếu P1–P3

| Nguyên tắc | Dấu hiệu quyết định phù hợp | Tín hiệu phản mẫu | Bằng chứng cần xem |
|---|---|---|---|
| **P1** — Giá trị sớm và liên tục | Có lát cắt tạo lợi ích và phản hồi người dùng | Chỉ báo cáo output, không biết người học hưởng gì | Outcome, phản hồi, Increment đạt DoD |
| **P2** — Đón nhận thay đổi | Có chính sách đánh giá dữ liệu mới và thích ứng thứ tự/phạm vi | Kế hoạch đóng băng bất kể sự cố hoặc tín hiệu mạnh | Decision log, backlog thay đổi có lý do |
| **P3** — Giao thường xuyên | Tích hợp liên tục, lát cắt kiểm chứng được | Tích hợp/kiểm thử dồn cuối, thời gian tới feedback dài | Nhịp Increment, build quality, cycle time |

### 5.5. Tình huống đánh đổi: phát hành sớm hay chờ kiểm chứng?

Nếu tính năng xử lý dữ liệu học tập chưa kiểm tra phân quyền đầy đủ, câu trả lời **không phải** “P3 đòi giao sớm nên cứ phát hành”. Có thể:

- Thu nhỏ phạm vi thành lát cắt **không gây rủi ro chưa kiểm soát**.
- Dùng môi trường thử để kiểm chứng với người có quyền phù hợp.
- Hoàn thiện test/DoD và release controls trước khi mở cho người dùng.
- Dự báo lại thời điểm giao và thông báo bằng chứng.

P1 và P3 có ý nghĩa trong **bối cảnh phần mềm hoạt động đáng tin**; không ưu tiên tốc độ bằng cách chuyển rủi ro chưa được phép sang người học.

## 6. Nguyên tắc P4–P6: cộng tác, động lực và giao tiếp hiệu quả

### 6.1. P4 — Người hiểu nghiệp vụ và Developers làm việc cùng nhau thường xuyên

**Diễn giải:** Sự thật nghiệp vụ không thể chỉ được viết một lần rồi “ném qua tường” cho kỹ thuật. Khi cách hiểu thay đổi, cần phối hợp đủ thường xuyên để giảm việc làm lại.

Một quyết định phù hợp:

- Product Owner, Developers và Tester làm rõ ví dụ **đã lưu/chưa lưu/chưa xác định** trước khi code.
- Những câu hỏi có người quyết định được chỉ rõ; kết luận cập nhật vào acceptance criteria.
- Điều chưa rõ được nêu minh bạch trong backlog thay vì Dev tự suy đoán.

Không nhất thiết phải **tổ chức một cuộc họp dài mỗi ngày**; tương tác có thể diễn ra qua hội thoại trực tiếp hoặc async có cấu trúc theo nhu cầu. Trong Scrum, Product Owner có accountability với Product Backlog, nhưng **việc cộng tác không chỉ là “gửi ticket cho PO phê duyệt”**.

### 6.2. P5 — Xây công việc quanh những người có động lực, tạo điều kiện và tin tưởng họ

**Diễn giải:** Đội cần **mục tiêu rõ, sự hỗ trợ, môi trường, thẩm quyền phù hợp và niềm tin** để tự tìm cách thực hiện. Kiểm soát vi mô dựa trên số phút online hoặc số commit có thể phá động lực và giảm minh bạch.

Quyết định minh họa:

- Cách yếu: quản lý chỉ định từng người phải đóng năm ticket/ngày, mọi PR cần hỏi quản lý dù đúng thẩm quyền kỹ thuật.
- Cách có ích hơn: Product Owner làm rõ giá trị, Developers tự lập kế hoạch kỹ thuật và chịu trách nhiệm DoD, Scrum Master hỗ trợ gỡ trở ngại; tổ chức cấp môi trường, quyền và thời gian cần thiết.

**Tin tưởng không nghĩa không kiểm chứng:** đội vẫn dùng tiêu chí Done, review, kiểm soát bảo mật, kết quả người dùng và trách nhiệm công khai. Tin tưởng đi cùng **khả năng minh bạch và tự quản**, không phải miễn trách nhiệm.

### 6.3. P6 — Hội thoại trực tiếp là cách truyền đạt phong phú, hiệu quả trong nhóm phát triển

**Diễn giải:** Khi vấn đề mơ hồ, cần đối thoại để giải thích và kiểm tra cách hiểu nhanh. Manifesto ưu tiên **trao đổi trực diện** như cách truyền thông hiệu quả, nhưng điều đó không có nghĩa **mọi nhóm phải cùng văn phòng** hoặc mọi cập nhật đều cần video call.

Trong nhóm phân tán:

- Dùng video/âm thanh cho quyết định nhiều đánh đổi, pairing/debug khi thực sự có ích.
- Dùng tài liệu, chat/PR và decision log để người khác múi giờ đọc được.
- Trước cuộc họp nêu **vấn đề, lựa chọn, ví dụ**; sau cuộc họp ghi **đã quyết/chưa quyết, người phụ trách, nguồn hiện hành**.
- Tôn trọng giờ làm và khả năng tiếp cận của người tham gia.

**Phản mẫu:** “P6 nói trao đổi trực tiếp, vậy ai không bật camera ở cuộc họp đêm coi như không cộng tác.” Điều đó bỏ qua khả năng tiếp cận, nhịp bền vững và mục đích thật của nguyên tắc.

### 6.4. Bảng đối chiếu P4–P6

| Nguyên tắc | Câu hỏi tốt | Sai lệch cần cảnh giác | Điều nhóm có thể làm |
|---|---|---|---|
| **P4** | Người hiểu nhu cầu có tham gia đúng lúc Developers cần quyết định? | Nghiệp vụ và kỹ thuật hoạt động như hai dây chuyền bàn giao | Refinement liên tục, Three Amigos, quyết định có nguồn |
| **P5** | Đội có năng lực, quyền và sự tin tưởng để thực hiện? | Chỉ thị vi mô, phụ thuộc phê duyệt mọi thao tác | Làm rõ quyền quyết định, hỗ trợ môi trường, pairing |
| **P6** | Cách giao tiếp giúp hiểu đúng và không loại người khác múi giờ? | Họp status dài, kết luận bị mất hoặc yêu cầu online 24/7 | Sync khi mơ hồ, async khi rõ, ghi kết luận |

### 6.5. Trách nhiệm không tự biến mất khi “mọi người cùng cộng tác”

Một nhóm có thể thảo luận mở, nhưng vẫn cần biết:

- Ai chịu trách nhiệm **thứ tự Product Backlog**?
- Ai tạo Increment và giữ **Definition of Done**?
- Ai hỗ trợ hiệu quả Scrum và tháo trở ngại?
- Ai có thẩm quyền kiểm soát bảo mật/pháp lý/vận hành khi áp dụng?

Trong Scrum, đó là **Product Owner, Developers và Scrum Master** cho các accountability được Scrum định nghĩa, song tổ chức có thể có **thẩm quyền bổ sung** cho rủi ro và nghĩa vụ. Cộng tác không biến mọi quyền quyết định thành phiếu bầu ngang nhau.

## 7. Nguyên tắc P7–P9: đo bằng phần mềm, làm việc bền vững và giữ chất lượng kỹ thuật

### 7.1. P7 — Phần mềm hoạt động là thước đo tiến độ quan trọng hàng đầu

**Diễn giải:** Báo cáo giờ công, số story points hay phần trăm code không thể thay việc **chứng minh một khả năng thật sự chạy được và đáp ứng tiêu chí chất lượng**.

Ví dụ:

- Một PBI có trạng thái “Done” vì code đã merge nhưng kiểm tra tích hợp fail **không phải Increment đạt DoD**.
- Một demo dùng dữ liệu giả không phản ánh điều kiện người học thật cần được giải thích phạm vi, không trình bày như đã giao tính năng hoàn chỉnh.
- Một release nhỏ có thể sử dụng, qua test thích hợp và được phản hồi mang nhiều thông tin hơn mười trang “90% hoàn thành”.

**Không hiểu sai** P7 thành “outcome không quan trọng”; phần mềm hoạt động là bằng chứng tiến độ tạo sản phẩm, còn **người dùng có đạt kết quả mong muốn** hay không vẫn cần đo riêng.

### 7.2. P8 — Phát triển theo nhịp bền vững, các bên có thể duy trì lâu dài

**Diễn giải:** Agile không phải tăng tốc bằng cách làm thêm giờ vô hạn. Sponsors, Developers và users cần hướng tới **nhịp có thể duy trì**, vì mệt mỏi làm tăng lỗi và nợ kỹ thuật.

Quyết định phản mẫu:

> “Bỏ Retro, bỏ test đường lỗi và yêu cầu cả đội làm đêm cho tới khi đạt số ticket cam kết.”

Một phương án khác:

- Giảm WIP và chia phạm vi nhỏ để tăng khả năng hoàn tất.
- Làm rõ chi phí cơ hội khi incident xuất hiện.
- Lập kế hoạch theo **năng lực thực tế**, có nghỉ, review, support và phụ thuộc.
- Sửa nguyên nhân gây sự cố lặp thay vì chỉ chữa cháy.
- Không lấy việc người lao động im lặng làm bằng chứng họ không quá tải.

**Bền vững** không đồng nghĩa không bao giờ phải ứng cứu khẩn, nhưng nghĩa là **cơ chế xử lý khẩn và phục hồi không dựa vào kiệt sức thường xuyên**.

### 7.3. P9 — Liên tục quan tâm tới sự xuất sắc kỹ thuật và thiết kế tốt

**Diễn giải:** Khả năng phản hồi với thay đổi phụ thuộc vào kiến trúc, test và chất lượng. Nếu mỗi sửa đổi gây lỗi hồi quy, đội sẽ ngày càng khó Agile dù backlog rất linh hoạt.

Các thực hành có thể hỗ trợ:

- **TDD** cho quy tắc nhỏ; không coi unit tests là đủ với mọi rủi ro.
- **Continuous Integration** để biết nhanh các thay đổi có tích hợp được không.
- **Pairing/code review** để chia tri thức và phát hiện sai giả định.
- **Refactoring và simple design** để giữ chi phí thay đổi ở mức hợp lý.
- **Contract/integration tests** để bảo vệ ranh giới UI–API.
- **Quan sát sự cố thực** để cập nhật kiểm chứng.

Lựa chọn phù hợp có thể **dành năng lực cho kỹ thuật nền tảng** thay vì luôn thêm feature mới. Cần diễn đạt tác dụng mong muốn: ít lỗi, tích hợp sớm, giảm lead time cho thay đổi tương lai — không chỉ “tăng test coverage” cho đẹp.

### 7.4. Bảng đối chiếu P7–P9

| Nguyên tắc | Bằng chứng tốt | Phản mẫu | Cân nhắc thực hành |
|---|---|---|---|
| **P7** | Increment hoạt động, tích hợp, đạt DoD | Velocity tăng nhưng không có phần dùng được | Lát cắt dọc, kiểm tra end-to-end theo rủi ro |
| **P8** | Nhịp giao đều, tải hợp lý, ít overtime lặp | Dùng làm thêm giờ làm “buffer” thường trực | WIP, capacity thật, trực ứng cứu có chính sách |
| **P9** | CI tin cậy, lỗi hồi quy được phòng/phát hiện sớm | Bỏ refactor/test để có số lượng feature | XP/TDD/CI, review, refactoring có mục tiêu |

### 7.5. P7 và P9 có thể căng thẳng bề ngoài nhưng hỗ trợ nhau

Đội có thể lo rằng dành một Sprint sửa test flaky làm **giảm số feature ngay bây giờ**. Khi test flaky khiến mọi thay đổi cần chạy lại nhiều lần, chi phí tiếp tục làm feature có thể cao hơn:

1. Phân tích nguyên nhân, bằng chứng và tác động thực tế của test flaky.
2. Xác định một cải tiến nhỏ, ví dụ **dữ liệu thử độc lập**.
3. Ghi chi phí cơ hội và tác dụng kỳ vọng: giảm build đỏ giả, tăng niềm tin CI.
4. Thử, đo, đánh giá tác dụng thay vì cho rằng mọi công việc nội bộ đều có giá trị.

**Phần mềm hoạt động** và **chất lượng kỹ thuật** không phải hai lựa chọn đối lập; chất lượng là điều kiện giúp phần mềm tiếp tục hoạt động khi thay đổi.

## 8. Nguyên tắc P10–P12: đơn giản, tự tổ chức và cải tiến liên tục

### 8.1. P10 — Đơn giản: tối đa hóa phần việc không cần làm

**Diễn giải:** Giá trị không tăng theo số tính năng, số dòng code, số tài liệu hay số cuộc họp. Nhóm tìm **giải pháp nhỏ nhất đủ tạo và kiểm chứng giá trị** trong điều kiện chất lượng/ràng buộc cần thiết.

Ví dụ:

- Giả thuyết: người học bỏ dở vì không biết tiến độ đã lưu.
- Phương án A: xây hệ thống AI gợi ý học tập, badge, gamification và dashboard mới.
- Phương án B: trước tiên hiển thị trạng thái lưu đúng và kiểm chứng liệu người dùng bớt bỏ dở.

Nếu dữ liệu cho thấy vấn đề chính là trạng thái lưu, B giúp **tránh làm các phần chưa cần**. Nhưng không được dùng “đơn giản” để bỏ logging bắt buộc, quyền truy cập hoặc khả năng khôi phục dữ liệu thiết yếu.

**P10 không có nghĩa làm công việc cẩu thả ít effort nhất**. Nó đề cập **tránh công việc không tạo giá trị**, vẫn giữ kiểm chứng và thiết kế đủ tốt.

### 8.2. P11 — Kiến trúc, yêu cầu và thiết kế tốt nổi lên từ những đội có khả năng tự tổ chức

**Diễn giải:** Người gần vấn đề kỹ thuật và người dùng cần quyền phối hợp, đưa ra lựa chọn trong phạm vi trách nhiệm. Thiết kế tốt thường xuất hiện qua **thử nghiệm, trao đổi và điều chỉnh**, không chỉ lệnh từ một chức danh.

Ví dụ:

- Product Owner nêu **kết quả người học cần**, rủi ro và thứ tự ưu tiên.
- Developers cùng đánh giá API contract, test strategy, sự đơn giản và khả năng thay đổi.
- Stakeholders/chuyên gia cung cấp thông tin, kiểm soát bắt buộc hoặc quyết định theo quyền hạn.
- Đội học từ Increment thật thay vì bắt một kiến trúc lớn “đúng từ đầu”.

Trong Manifesto, nguyên tắc dùng khái niệm **self-organizing teams**. Scrum Guide 2020 sử dụng **self-managing Scrum Team** cho việc quyết định ai làm gì, khi nào, thế nào trong phạm vi Scrum. Hai cách diễn đạt có ngữ cảnh riêng, không nên tự coi là định nghĩa giống hệt trong mọi tổ chức.

**Tự tổ chức không đồng nghĩa không có ràng buộc** hoặc ai cũng được bỏ qua chính sách cần thiết.

### 8.3. P12 — Thường xuyên suy ngẫm về hiệu quả rồi điều chỉnh cách làm

**Diễn giải:** Agile không hoàn thành khi đội “cài xong Scrum”. Đội nhìn lại dữ liệu, tương tác, chất lượng và outcome để **thay đổi hành vi cụ thể**, rồi kiểm tra tác dụng.

Một Retrospective yếu:

> “Cần giao tiếp tốt hơn. Cần test nhiều hơn.”

Một cải tiến có thể kiểm chứng:

> “Trong hai Sprint tiếp theo, các PBI thay API trạng thái lưu sẽ có ví dụ accepted và contract test trước merge; theo dõi số vòng hỏi lại và lỗi contract phát hiện muộn; guardrail là DoD và chất lượng production không suy giảm.”

Không cần mỗi retro tạo mười việc. **Chọn ít cải tiến, thực hiện thật và xem lại** có ý nghĩa hơn.

### 8.4. Bảng đối chiếu P10–P12

| Nguyên tắc | Câu hỏi khi ra quyết định | Sai lệch phổ biến | Dấu hiệu hiệu quả |
|---|---|---|---|
| **P10** — Đơn giản | Có phần công việc nào chưa cần làm để kiểm chứng giá trị không? | Tăng scope vì “đã tính trong kế hoạch” | Lát cắt nhỏ, ít rework, outcome rõ |
| **P11** — Đội tự tổ chức | Ai có thông tin và trách nhiệm để chọn cách làm? | Quyết định kỹ thuật từ xa thiếu thực tế, hoặc ai cũng tự làm trái chính sách | Team ownership, thiết kế thích ứng, chất lượng |
| **P12** — Nhìn lại và điều chỉnh | Đã học điều gì, hành động nào thay đổi và có tác dụng? | Retro nghi thức, không xem lại action cũ | Thử nghiệm nhỏ, bằng chứng, giữ–sửa–dừng |

### 8.5. Giữ sự đơn giản không đồng nghĩa từ chối tài liệu quyết định

Một ADR một trang giải thích **vì sao API có trạng thái UNKNOWN** có thể giảm nhiều ngày hỏi lại. Nó là **tài liệu vừa đủ** để tránh chi phí hiểu sai, không phải đối tượng cần cắt bỏ chỉ vì P10.

Ngược lại, viết bộ đặc tả 200 trang cho ba trạng thái trước khi làm được một test nhỏ có thể là dấu hiệu đang **tối ưu sản lượng tài liệu thay vì học từ hành vi phần mềm**.

Đánh giá dựa vào **khả năng người khác tiếp tục an toàn và phần mềm được kiểm chứng**, không chỉ số trang.

## 9. Trước khi đối chiếu: tách sự kiện, giả định, mục tiêu và quyết định

### 9.1. Một quyết định có thể hợp lý ở thời điểm này nhưng sai khi bối cảnh thay đổi

Giả sử đầu Sprint nhóm chọn làm giao diện “Tiếp tục bài”. Khi đó Product Owner chưa có thông tin rằng người học mạng yếu thường mất tiến độ. Đến giữa Sprint, dữ liệu support mới chỉ ra lỗi ảnh hưởng lớn.

Để đánh giá công bằng:

- **Thông tin có sẵn tại thời điểm quyết định:** mục tiêu, dữ liệu, hạn chế và giả định lúc đó.
- **Thông tin xuất hiện sau:** phản hồi người dùng, test mới, sự cố, thay đổi hợp đồng.
- **Hành động sau khi biết thêm:** nhóm có kiểm tra và thích ứng không?

Không dùng tri thức xuất hiện về sau để kết luận những người ở thời điểm trước **cố ý làm sai**. Nhưng cũng không xem một quyết định cũ là bất khả thay đổi chỉ vì khi đó hợp lý.

### 9.2. Sáu khối thông tin cần phân biệt

| Thành phần | Định nghĩa | Ví dụ |
|---|---|---|
| **Sự kiện/quan sát** | Có nguồn kiểm tra hoặc trải nghiệm được ghi nhận rõ | Ba báo cáo mất tiến độ có bước tái hiện |
| **Diễn giải** | Cách nhóm hiểu các sự kiện | Lỗi có thể liên quan trạng thái timeout |
| **Giả định** | Điều chưa được xác minh nhưng đang ảnh hưởng lựa chọn | Phần lớn người học dùng mạng ổn định |
| **Mục tiêu/giới hạn** | Kết quả mong muốn và điều không thể đánh đổi | Tăng tỷ lệ học tiếp; giữ kiểm soát quyền dữ liệu |
| **Lựa chọn/đánh đổi** | Những cách hành động khả thi và chi phí cơ hội | Sửa timeout trước hay hoàn thành animation trước |
| **Quyết định + điều kiện xem lại** | Ai chọn gì, vì sao và bằng chứng nào khiến đổi ý | Thử sửa timeout trong lát cắt nhỏ, xem lỗi và hành vi người học |

Nếu một người nói “chúng ta đã thất bại vì Product Owner không lắng nghe”, hãy yêu cầu **sự kiện, thời điểm, quyết định và tác động** trước khi biến cảm nhận thành kết luận quy trách nhiệm.

### 9.3. Mẫu mô tả quyết định một trang

~~~text
ID / ngày / phạm vi:
Product Goal hoặc mục tiêu dịch vụ:
Người dùng/stakeholder chịu ảnh hưởng:
Sự kiện và nguồn bằng chứng:
Các giả định chưa được xác minh:
Ràng buộc bắt buộc và người có thẩm quyền:
Phương án A/B/C:
Điều mỗi phương án tạo ra / đánh đổi:
Giá trị Agile liên quan:
Nguyên tắc P1–P12 liên quan:
Quyết định và lý do:
Ai chịu trách nhiệm thực hiện và xác nhận:
Tín hiệu đánh giá (giá trị, flow, chất lượng, bền vững):
Guardrails / điều không được đánh đổi:
Mốc xem lại và các lựa chọn giữ–sửa–dừng:
~~~

Đối với quyết định nhỏ, có thể rút xuống vài dòng trong PBI/PR. **Độ chi tiết cần tương xứng mức rủi ro, chi phí đổi và số người bị ảnh hưởng.**

### 9.4. Quyết định khác hành động và khác kết quả

Ví dụ:

1. **Quyết định:** thêm contract test cho trạng thái UNKNOWN trước merge.
2. **Hành động:** Developers hiện thực test, đưa vào CI và cập nhật contract.
3. **Output:** một bộ test mới cùng báo cáo CI.
4. **Tác động vận hành:** ít lỗi hiểu sai hợp đồng phát hiện muộn hơn.
5. **Outcome người dùng:** ít trường hợp nhận thông báo “Đã lưu” giả; người học tin tưởng khả năng tiếp tục bài hơn.

Đội có thể **thực hiện hành động đúng nhưng outcome chưa đổi** do giả thuyết chưa đầy đủ. Khi đó cần điều chỉnh, không kết luận chỉ từ việc “đã thêm test”.

### 9.5. Kiểm soát quyền quyết định

Manifesto khuyến khích cộng tác, nhưng một đội không thể tự bỏ:

- Nghĩa vụ pháp lý/hợp đồng đã xác nhận.
- Kiểm soát quyền, dữ liệu, bảo mật bắt buộc.
- Quyết định Product Backlog thuộc accountability của Product Owner trong Scrum.
- Thẩm quyền khẩn cấp/rollout/on-call theo chính sách tổ chức.

Trong quyết định, ghi rõ **ai được tham vấn, ai thực hiện, ai có quyền quyết định và ai cần được thông tin**. Cộng tác mở không đồng nghĩa lấy ý kiến đa số để hợp thức hóa một lựa chọn vượt quyền.

## 10. Quy trình sáu bước đối chiếu một quyết định với Agile

### 10.1. Bước 1 — Xác định quyết định thật và thời điểm

Đừng xem xét câu trừu tượng “đội có Agile không?”. Hãy chọn một quyết định cụ thể:

> “Trong Sprint 14, nhóm giữ backlog không đổi dù có báo cáo người học mất tiến độ.”

Ghi **người ra quyết định, thời điểm, phạm vi và bằng chứng lúc đó**. Có thể cần phân biệt **không thay đổi Sprint Goal** (hợp lý theo Scrum nếu mục tiêu vẫn có giá trị) với **không xử lý sự cố nghiêm trọng** (có thể gây hại).

### 10.2. Bước 2 — Làm rõ mục đích, ràng buộc và người chịu ảnh hưởng

Hỏi:

- Product Goal/Sprint Goal đang phục vụ điều gì?
- Ai nhận giá trị, ai chịu rủi ro nếu chờ?
- Những nghĩa vụ, giới hạn chất lượng và quyền quyết định nào áp dụng?
- Có lựa chọn an toàn nào khác không?

Không nên so sánh phương án mà chưa biết **điều kiện bắt buộc**; phương án tăng tốc bằng cách bỏ kiểm soát quyền dữ liệu có thể **không hợp lệ để chọn**.

### 10.3. Bước 3 — Đối chiếu bốn giá trị, ghi cả điều được lợi và bị mất

Với từng giá trị, đặt ít nhất một câu hỏi:

1. **V1:** ai cần tương tác để hiểu và thực hiện? Quy trình/công cụ đang giúp hay chặn?
2. **V2:** khi nào có phần mềm hoạt động và bằng chứng chất lượng? Tài liệu nào thực sự cần?
3. **V3:** có feedback thực từ khách hàng/đại diện phù hợp? Có nghĩa vụ hợp đồng phải giữ?
4. **V4:** quyết định dựa trên thông tin mới hay chỉ bảo vệ kế hoạch cũ? Thay đổi có được triage?

Đánh dấu **tác dụng dự kiến và bất lợi có thể có**, thay vì chọn “Có/Không” rồi cộng điểm.

### 10.4. Bước 4 — Tìm 2–5 nguyên tắc liên quan nhất và kiểm tra toàn bộ nhóm nguyên tắc

Không phải mọi quyết định cần bài luận riêng cho 12 nguyên tắc. Nhưng để tránh **cherry-picking**:

- Chọn nguyên tắc có quan hệ nhân quả trực tiếp với vấn đề.
- **Quét nhanh cả P1–P12** để nhận ra nguyên tắc có nguy cơ bị xâm phạm.
- Ghi rõ vì sao một nguyên tắc **không liên quan trực tiếp** trong quyết định này, nếu cần.
- Khi có mâu thuẫn bề ngoài, xem **ràng buộc, phương án khác và tác động dài hạn**.

Ví dụ bỏ test để release sớm có vẻ phục vụ P3 nhưng xung đột P7, P9 và cả mục tiêu P1. Đừng dùng đúng **một nguyên tắc thuận tiện** làm giấy phép cho quyết định nguy hiểm.

### 10.5. Bước 5 — Chọn phương án nhỏ đủ tạo bằng chứng

Một phương án tốt:

- Phục vụ mục tiêu sản phẩm/người dùng đã rõ.
- Đáp ứng ràng buộc và Definition of Done.
- Tạo phản hồi sớm, có phạm vi có thể quản lý.
- Có **người phối hợp/thẩm quyền** rõ.
- Không đánh đổi nhịp làm bền vững bằng việc làm thêm vô hạn.
- Có thể **điều chỉnh hoặc dừng** nếu giả thuyết sai.

Đôi khi quyết định tốt nhất là **không xây thêm feature**, mà thu thập bằng chứng thiếu, giảm WIP, sửa test flaky hoặc chờ quyền pháp lý cần thiết.

### 10.6. Bước 6 — Đo kết quả và cập nhật quyết định

Nhóm đặt:

- **Một hoặc hai tín hiệu giá trị:** người học hoàn thành, quay lại, ít mất tiến độ.
- **Tín hiệu giao phần mềm:** Increment đạt DoD, thời gian có feedback, lỗi.
- **Tín hiệu flow:** WIP, work item age, cycle time, blockers.
- **Guardrails:** bảo mật, riêng tư, quyền, chất lượng, overtime.
- **Mốc xem lại:** sau một hai Sprint hoặc khoảng đủ lấy phản hồi, không phải mọi phép đo cần cùng thời hạn.

Nếu kết quả không như dự đoán, hỏi **“Giả thuyết nào sai, điều kiện nào đổi?”**, không tìm một người chịu lỗi vì cuộc thử nghiệm hợp lý chưa thành công.

### 10.7. Luồng ra quyết định

~~~mermaid
flowchart TD
    A["Quyết định cụ thể + thời điểm"] --> B["Sự kiện, mục tiêu, ràng buộc, các bên"]
    B --> C["So bốn giá trị: hỗ trợ và đánh đổi"]
    C --> D["Quét P1–P12: phù hợp, căng thẳng, chưa biết"]
    D --> E{"Có vi phạm điều kiện bắt buộc?"}
    E -->|"Có"| F["Loại phương án / xin làm rõ đúng thẩm quyền"]
    E -->|"Không"| G["Chọn hành động nhỏ, có bằng chứng và guardrails"]
    F --> B
    G --> H["Thực hiện; quan sát outcome, flow, chất lượng"]
    H --> I{"Có đạt mục đích không?"}
    I -->|"Có"| J["Giữ và chuẩn hóa phần hữu ích"]
    I -->|"Không/chưa rõ"| K["Sửa giả thuyết, đổi phạm vi hoặc dừng"]
    J --> B
    K --> B
~~~

Sơ đồ là **phương pháp thực hành đề xuất của bài học**, không phải nghi thức mới hay tiêu chuẩn bắt buộc của Manifesto.

## 11. Ma trận đối chiếu 4 giá trị và 12 nguyên tắc

### 11.1. Bảng bốn giá trị — hành vi và bằng chứng

| Giá trị | Câu hỏi kiểm tra trong cuộc họp quyết định | Bằng chứng có thể xem | Tín hiệu cảnh báo |
|---|---|---|---|
| **V1 — Con người & tương tác** | Những người có thông tin/quyền quyết định đã cùng hiểu vấn đề chưa? | Hội thoại có ví dụ, quyết định được truyền tới người liên quan, handoff rõ | Nhiều vòng hỏi lại, tin nhắn trôi, người có quyền bị loại |
| **V2 — Phần mềm hoạt động** | Khi nào chứng minh hành vi thật đáp ứng DoD? | Increment tích hợp, CI/test theo rủi ro, feedback dùng thử | Slide xanh nhưng build đỏ, báo Done khi chưa test |
| **V3 — Cộng tác với khách hàng** | Phản hồi và kết quả người dùng nào tác động quyết định? | Dữ liệu sử dụng, feedback có nguồn, Product Backlog được điều chỉnh | “Hợp đồng đã viết vậy, không cần hỏi người dùng” |
| **V4 — Phản hồi với thay đổi** | Giả định nào mới bị thách thức; nhóm có thể thay đổi có kiểm soát? | Decision log, backlog/plan thích ứng theo bằng chứng | Giữ kế hoạch bất kể tác hại, hoặc đổi việc theo mọi tin nhắn |

**Ghi chú:** bảng không trao quyền thay đổi nghĩa vụ pháp lý, hợp đồng, phê duyệt bắt buộc hay Definition of Done.

### 11.2. Bảng mười hai nguyên tắc — dùng để đặt câu hỏi và chọn tín hiệu

| Nguyên tắc | Câu hỏi đối chiếu | Tín hiệu/bằng chứng phù hợp |
|---|---|---|
| **P1 — Giá trị sớm** | Người dùng nhận điều có ích nào và khi nào? | Outcome, feedback, Increment có giá trị |
| **P2 — Đón nhận thay đổi** | Thông tin mới có được đánh giá có trách nhiệm? | Quyết định thay thứ tự/phạm vi dựa trên nguồn |
| **P3 — Giao thường xuyên** | Có lát cắt hoạt động để kiểm tra sớm? | Chu kỳ feedback, integration, DoD |
| **P4 — Nghiệp vụ–kỹ thuật cộng tác** | Những giả định nghiệp vụ đã được làm rõ trước khi lan vào code? | AC/ví dụ, vấn đề được giải đáp, rework |
| **P5 — Tin tưởng người có động lực** | Đội có quyền, nguồn lực và sự hỗ trợ cần thiết? | Trở ngại được xử lý, tự quản theo trách nhiệm |
| **P6 — Giao tiếp hiệu quả** | Các bên có thực sự hiểu cùng một quyết định? | Context handoff, vòng hỏi lại, quyết định có nguồn |
| **P7 — Phần mềm hoạt động đo tiến độ** | Có bằng chứng chất lượng của Increment, không chỉ báo cáo? | DoD, build/test, hành vi sử dụng |
| **P8 — Nhịp bền vững** | Cách làm có thể duy trì mà không làm thêm giờ mãi? | Overtime, gián đoạn, tải on-call, chất lượng |
| **P9 — Xuất sắc kỹ thuật** | Thiết kế/test giúp thay đổi an toàn hơn? | CI stability, hồi quy, công việc làm lại |
| **P10 — Đơn giản** | Có phần nào có thể chưa làm mà vẫn kiểm chứng giá trị? | Scope nhỏ, giả thuyết được kiểm tra, ít rework |
| **P11 — Đội tự tổ chức** | Người gần vấn đề có quyền quyết định cách thực hiện phù hợp? | Team ownership, trao đổi đánh đổi, thiết kế thích ứng |
| **P12 — Nhìn lại và cải tiến** | Đội đã thử thay đổi cách làm và xem lại chưa? | Improvement actions thực hiện, tín hiệu trước–sau và giới hạn |

**Không suy ra rằng tất cả các ô cần “đạt” trong mọi quyết định.** Một quyết định về text UI có thể liên quan trực tiếp P1/P4/P10; quyết định về quality gate lại trực tiếp P7/P9/P8. Hãy ghi **điều có bằng chứng, điều còn giả định và điều có rủi ro xung đột**.

### 11.3. Phiếu xem xét ba mức, không chấm điểm tổng

Có thể dùng các nhãn:

| Ký hiệu | Ý nghĩa | Hành động |
|---|---|---|
| **Hỗ trợ (supporting)** | Lựa chọn có cơ chế và bằng chứng hợp lý phục vụ giá trị/nguyên tắc | Ghi tín hiệu theo dõi |
| **Căng thẳng (tension)** | Có đánh đổi hoặc rủi ro cần quản lý | Nêu tác động và guardrail |
| **Chưa rõ (unknown)** | Không đủ dữ kiện để kết luận | Thu thập bằng chứng hoặc thử nghiệm nhỏ |
| **Không liên quan trực tiếp (not material)** | Liên hệ rất yếu với quyết định đang xem | Không ép trả lời giả tạo |

Không nên cộng số nhãn “Hỗ trợ” rồi tuyên bố **“đạt 9/12 nên quyết định đúng”**. Các nguyên tắc không có trọng số chính thức và **một vi phạm quyền dữ liệu nghiêm trọng không thể được bù bằng nhiều ô xanh khác**.

### 11.4. Ví dụ điền phiếu cho quyết định

**Đề xuất:** cắt bỏ integration tests để phát hành chức năng lưu tiến độ đúng lịch demo.

| Tiêu chí | Đánh giá | Lý do |
|---|---|---|
| **V2, P7** | **Căng thẳng** | Chưa có bằng chứng chức năng hoạt động đáng tin qua UI–API–DB |
| **P3** | **Chưa rõ** | Phát hành có thể sớm hơn nhưng tăng nguy cơ phản hồi sai/hại người dùng |
| **P8** | **Căng thẳng** | Có thể phát sinh sửa lỗi và trực ứng cứu sau demo |
| **P9** | **Căng thẳng** | Bỏ kiểm tra ở ranh giới rủi ro, giảm khả năng đổi an toàn |
| **P1, V3** | **Căng thẳng** | Người học có thể mất dữ liệu, giảm tin tưởng; chưa thu feedback thật |
| **V4** | **Chưa rõ** | Thay kế hoạch vì deadline chứ không nhất thiết vì thông tin giá trị |
| **Điều kiện bắt buộc** | **Không đạt nếu integration test thuộc DoD** | Không được báo Done hoặc phát hành như đạt chất lượng |

**Quyết định thay thế:** chia phạm vi demo thành lát cắt đã qua kiểm chứng hoặc demo rõ môi trường/hạn chế mà không giới thiệu như Increment Done; giữ integration test cần thiết và minh bạch thời hạn dự báo. Nếu có sự cố phải xử lý theo chính sách ứng cứu.

## 12. Xử lý khi các giá trị/nguyên tắc có vẻ mâu thuẫn

### 12.1. Không dùng “Agile hơn” để chọn phương án bất hợp lệ

Khi có ràng buộc bắt buộc như kiểm soát bảo mật, quyền riêng tư, an toàn, hợp đồng được xác nhận, chúng là **điều kiện của không gian lựa chọn**. Chỉ so sánh các phương án hợp lệ trong phạm vi đó; nếu chưa rõ, nhờ người có thẩm quyền làm rõ.

Ví dụ **“phát hành sớm”** không có nghĩa **bỏ yêu cầu kiểm soát quyền truy cập**. Phương án thay thế có thể là giảm phạm vi, kiểm tra sớm hơn hoặc chia rollout với cơ chế được phép.

### 12.2. Phần mềm hoạt động (V2/P7) và tài liệu thiết yếu

| Hai cực dễ tranh cãi | Câu hỏi đúng | Lựa chọn có thể phù hợp |
|---|---|---|
| “Viết mọi tài liệu thật đầy đủ trước code” | Loại tài liệu nào giảm rủi ro hiểu sai và vận hành? | AC, API contract, runbook/ADR ngắn, cập nhật cùng code |
| “Không viết tài liệu nào để code nhanh” | Người khác có thể tích hợp, review và hỗ trợ không? | Giữ nguồn quyết định và bằng chứng tối thiểu cần thiết |

Vấn đề không phải **tài liệu nhiều hay ít**, mà tài liệu có phục vụ **phần mềm hoạt động, sự phối hợp và kiểm soát quan trọng** không.

### 12.3. Thích ứng (V4/P2) và giữ Sprint Goal

Trong Scrum, khi xuất hiện một yêu cầu mới:

- Product Owner xem giá trị và thứ tự Product Backlog.
- Developers xem ảnh hưởng kế hoạch, năng lực và chất lượng.
- Scrum Master hỗ trợ hiệu quả, làm rõ Scrum và gỡ trở ngại.
- Cần minh bạch nếu một sự cố thật đòi hỏi phản ứng ngay.
- **Không được gây nguy hại Sprint Goal hoặc giảm chất lượng trong Sprint**; phạm vi có thể làm rõ và thương lượng với Product Owner.

Không nên đồng nhất **giữ Sprint Goal** với **không thay đổi một ticket nào**. Cũng không nên xem **đón nhận thay đổi** là quyền mọi stakeholder đưa việc gấp vào Sprint tùy ý.

### 12.4. Cộng tác (V1/V3/P4/P6) và quyền quyết định

Một đề xuất mới có thể cần thảo luận với nhiều người, nhưng không có nghĩa mỗi người đều có **quyền phê duyệt**:

- Người dùng cung cấp bối cảnh và phản hồi.
- Product Owner quyết định thứ tự Product Backlog trong Scrum.
- Developers quyết định cách thực hiện phù hợp DoD và kỹ thuật.
- Chuyên gia kiểm soát có thể giữ quyền đối với nghĩa vụ cụ thể theo chính sách.

**Cộng tác tốt** làm các quyết định có thông tin phong phú và minh bạch; nó không xóa accountability.

### 12.5. Đơn giản (P10) và xuất sắc kỹ thuật (P9)

Một thay đổi nhỏ có thể cần test, logging và kiến trúc tối thiểu để không mất dữ liệu. Đó **không phải “overengineering” chỉ vì không nhìn thấy trên UI**.

Ngược lại, thiết kế ngay một hạ tầng microservices phức tạp khi một module nhỏ đủ kiểm chứng giả thuyết có thể tăng phụ thuộc mà chưa có giá trị.

Cách cân bằng:

1. Nêu rủi ro và chất lượng **thực sự cần**.
2. Chọn **thiết kế đơn giản nhất đáp ứng rủi ro ấy**.
3. Tạo test và điểm thay đổi an toàn.
4. Dùng phản hồi để quyết định khi nào cần mở rộng/refactor.

### 12.6. Giao thường xuyên (P3) và nhịp bền vững (P8)

Giao thường xuyên có thể đến từ **lát cắt nhỏ, CI và giảm WIP**, không nhất thiết từ việc tăng overtime hay ép release ngoài giờ.

Nếu nhóm liên tục thức đêm để đạt “phát hành mỗi ngày”, đó có thể là tối ưu một chỉ số trong khi phá **P8** và gây lỗi kỹ thuật. Xem xét tự động hóa an toàn, giảm batch size, chính sách release/on-call và thời điểm phù hợp rủi ro.

### 12.7. Đổi kế hoạch để đón nhận phản hồi nhưng không bị điều khiển bởi mọi yêu cầu

Tín hiệu khách hàng có thể là:

- **Sự cố có tác động đáng kể** cần ứng cứu.
- **Phản hồi sử dụng có cơ sở** để cân nhắc backlog.
- **Ý tưởng cá nhân** chưa có bằng chứng giá trị.
- **Hạn hợp đồng được xác nhận** với ràng buộc riêng.

Không đối xử cả bốn giống nhau. **Tiếp nhận và phân loại** giúp đội vừa lắng nghe vừa giữ hướng ưu tiên.

## 13. Đối chiếu quyết định trong Scrum

### 13.1. Scrum hỗ trợ thực nghiệm nhưng không bảo đảm Agile tự động

Scrum đưa ra **accountabilities, events, artifacts và commitments** để đội tạo giá trị trong môi trường phức tạp. Chúng giúp tổ chức **minh bạch, kiểm tra và thích ứng**. Tuy nhiên:

- Một Sprint Review có thể trở thành buổi báo cáo slide thay vì kiểm tra Increment với stakeholders.
- Daily Scrum có thể trở thành điểm danh giờ làm thay vì Developers điều chỉnh kế hoạch hướng Sprint Goal.
- Retrospective có thể ghi 15 hành động rồi không ai thực hiện.
- Sprint Backlog có thể trở thành danh sách cố định bất chấp thông tin mới.
- Definition of Done có thể bị bỏ qua để làm đẹp báo cáo velocity.

Khi đối chiếu, hỏi **“mục đích thực sự của thực hành có được đạt?”** thay vì “buổi họp có diễn ra không?”.

### 13.2. Product Goal và Product Backlog: P1, P2, P4, P10

**Quyết định:** Product Owner tiếp tục ưu tiên thêm màn hình giao diện vì đã có roadmap, dù người dùng liên tục báo trạng thái lưu tiến độ gây hiểu sai.

Đối chiếu:

| Nguyên tắc/giá trị | Câu hỏi |
|---|---|
| **P1/V3** | Roadmap đang tạo giá trị mà người học cần, hay chỉ giao output? |
| **P2/V4** | Phản hồi mới có làm thay đổi giả định về nhu cầu không? |
| **P4/V1** | Product Owner và Developers đã làm rõ ý nghĩa “đã lưu” với người dùng/chuyên gia chưa? |
| **P10** | Có lát cắt nhỏ sửa thông báo trước khi xây các phần mở rộng không? |

Một phương án phù hợp có thể **sắp lại Product Backlog** để xác minh vấn đề ưu tiên trước; công khai chi phí cơ hội của việc hoãn animation. Đây là **quyết định về giá trị**, không phải để một công cụ tự động sắp thứ tự ticket.

### 13.3. Sprint Planning: P1, P3, P5, P8

Sprint Planning hữu ích khi:

- Product Owner trình bày **giá trị của Sprint** và Product Backlog có trật tự.
- Developers cân nhắc **năng lực thực tế**, phụ thuộc, quality work và độ bất định.
- Team hình thành Sprint Goal đủ tập trung nhưng không biến nó thành một danh sách ticket bất biến.
- Năng lực kiểm thử, review, integration và cải tiến không bị coi là việc “ngoài Sprint”.

**Phản mẫu:** gắn 50 story points vào Sprint chỉ vì trung bình trước đó là 50, dù có người nghỉ, incident và môi trường thử chưa sẵn sàng.

**Đối chiếu P8:** lập kế hoạch theo năng lực và nhịp bền vững, không dùng overtime để che dự báo sai.

### 13.4. Daily Scrum: P4, P5, P6 và thích ứng

Daily Scrum là **15 phút dành cho Developers** để kiểm tra tiến độ hướng Sprint Goal và thích ứng Sprint Backlog. Nó không phải cuộc họp báo cáo cho Scrum Master hoặc quản lý.

Một cách đặt câu hỏi có ích:

- “Điều gì đang đe dọa Sprint Goal?”
- “PBI nào đang già, chờ review/test hoặc phụ thuộc?”
- “Ai cần phối hợp sau cuộc gặp để tháo blocker?”
- “Có thông tin mới khiến kế hoạch hôm nay cần đổi không?”

**Không buộc mọi thành viên phải trình bày ba câu hỏi “hôm qua/hôm nay/blocker”** như mẫu duy nhất. Đội có thể chọn cấu trúc phù hợp miễn đạt mục đích và timebox.

### 13.5. Sprint Review: P1, P3, P4, P7

Sprint Review là **phiên làm việc để kiểm tra kết quả Sprint và bối cảnh thay đổi**, phối hợp với stakeholders về hướng tiếp theo. Nó không đơn thuần là buổi phê duyệt cuối.

Để đối chiếu:

| Câu hỏi | Dấu hiệu tốt | Phản mẫu |
|---|---|---|
| Có Increment thật? | Tính năng đã đạt DoD và hoạt động trong phạm vi trình bày | Demo mock không nêu giới hạn, PBI chưa Done vẫn được báo hoàn tất |
| Có phản hồi? | Stakeholders đặt câu hỏi về tác động, giá trị, ưu tiên | Chỉ xem slide, vỗ tay rồi kết thúc |
| Có thích ứng? | Product Backlog được điều chỉnh nếu có thông tin mới | Mọi phản hồi bị hoãn vì roadmap không được sửa |

Không dùng Sprint Review như lý do **đợi cuối Sprint mới chạy test**; kiểm chứng chất lượng nên diễn ra trong toàn bộ Sprint.

### 13.6. Sprint Retrospective: P8, P9, P11, P12

Retrospective kiểm tra **chất lượng và hiệu quả cách Scrum Team làm việc**, để tìm thay đổi hữu ích.

Ví dụ:

- Sự kiện: integration test cho luồng lưu tiến độ thất bại cuối Sprint ba lần.
- Điều kiện: UI và backend chỉ tích hợp vào ngày cuối; dữ liệu test dùng chung.
- Giả thuyết: nếu có contract test sớm và test data cô lập, thời gian chờ/việc làm lại giảm.
- Thử nghiệm: thêm hai kiểm tra phù hợp trong CI và chia PBI dọc trong hai Sprint.
- Tín hiệu: số lỗi sai contract muộn, work item age, CI stability, lỗi production.
- Guardrail: không hạ DoD, không tăng overtime.

**P12 không phải “mỗi Sprint nhất định đổi một điều cho có”**; đó là tạo khả năng học, thực hiện cải tiến khi có ý nghĩa và xem kết quả.

### 13.7. Khi Sprint Goal bị đe dọa

Nếu có incident thực đang gây mất dữ liệu:

1. Ứng cứu và bảo vệ người dùng theo chính sách phù hợp.
2. Minh bạch năng lực bị chuyển và phần Sprint Goal bị ảnh hưởng.
3. Developers phối hợp Product Owner làm rõ/điều chỉnh phạm vi; chất lượng không giảm.
4. Scrum Master hỗ trợ tháo trở ngại và hiệu quả Scrum.
5. Nếu **Sprint Goal trở nên lỗi thời**, chỉ Product Owner có quyền hủy Sprint theo Scrum Guide.

Không biến **P2 đón nhận thay đổi** thành cơ chế mỗi stakeholder chen việc vào Sprint. Cũng không viện **“Sprint đã khóa”** để bỏ qua tác hại người dùng đang xảy ra.

## 14. Đối chiếu quyết định trong Kanban và dòng công việc

### 14.1. Kanban giải quyết bài toán nào khác Scrum?

Kanban giúp **định nghĩa và trực quan hóa workflow, kiểm soát WIP, đo dòng công việc và cải tiến chính sách**. Nó có thể đứng riêng trong một dịch vụ hoặc bổ trợ Scrum.

Không nên coi “vẽ board ba cột” là bằng chứng đội đã:

- Kiểm soát việc đang làm dở.
- Có chính sách kéo việc rõ.
- Có mục tiêu dịch vụ/sản phẩm.
- Theo dõi work item age và giải quyết blocker.
- Đo chất lượng khi việc chuyển Done.

### 14.2. Ví dụ quyết định về WIP: P8, P9, P10 và V2

**Quan sát:** một đội năm người có 18 PBI đang mở, nhiều việc chờ review và test tích hợp. Đội liên tục nhận feature mới để “ai cũng bận”.

**Đề xuất:** thử giảm WIP, ưu tiên giúp việc gần Done, làm rõ policy Blocked/Review, xem lại sau hai chu kỳ.

| Đối chiếu | Vì sao liên quan? |
|---|---|
| **P10** | Giảm mở việc chưa cần làm, tập trung vào phần tạo kết quả |
| **P8** | Giảm chuyển ngữ cảnh và áp lực làm thêm giờ |
| **P9/V2** | Có thời gian review/integration để phần mềm thực sự hoạt động |
| **P11** | Developers cùng lựa chọn cách phân công và hỗ trợ nhau |
| **P12** | Kiểm tra liệu giới hạn WIP có tác dụng, không áp như luật vĩnh viễn |

**Đánh đổi:** WIP quá thấp hoặc áp cơ học có thể cản các công việc độc lập hoặc sự cố khẩn. Vì vậy **không có số WIP chuẩn áp cho mọi đội**, phải xem cả throughput, cycle time, work item age, chất lượng và nhu cầu thật.

### 14.3. Phân biệt bốn phép đo Kanban

| Phép đo | Ý nghĩa | Câu hỏi quyết định |
|---|---|---|
| **WIP** | Số items đã bắt đầu và chưa Done | Chúng ta đã mở quá nhiều việc? |
| **Throughput** | Số items Done trong một khoảng | Dòng công việc hoàn tất đều không? |
| **Cycle time** | Thời gian bắt đầu–Done của item đã hoàn thành | Phản hồi về kết quả mất bao lâu? |
| **Work item age** | Thời gian một item đang mở đã tồn tại | Việc nào đang chờ quá lâu cần chú ý? |

**SLE** (Service Level Expectation) là kỳ vọng xác suất về thời gian hoàn thành dựa trên dữ liệu dòng công việc; không tự đồng nghĩa **SLA hợp đồng** hoặc lời hứa chắc chắn. Cần nêu loại việc, mốc tính và dữ liệu lịch sử.

### 14.4. Nhận diện Expedite thật và hạn chế đổi ưu tiên tùy tiện

Một đội vận hành nền tảng học nhận hai ticket:

- **A:** Production làm người học mất tiến độ hàng loạt.
- **B:** Một stakeholder muốn thêm hiệu ứng mượt mà cho nút “Tiếp tục” trong hôm nay.

Nếu cả A và B đều được gắn **Expedite**, đội có thể phá Sprint Goal/flow mà vẫn không xử lý kịp sự cố thật. Cần policy dựa trên **tác động, tính khẩn, rủi ro và thẩm quyền triage**, không dựa trên độ lớn tiếng của người yêu cầu.

**Các lớp dịch vụ** như Expedite, Fixed Date, Standard, Intangible là thực hành có thể tham khảo, **không phải bốn lớp bắt buộc của The Kanban Guide**.

### 14.5. Kanban và P1: flow tốt vẫn cần giá trị

Nếu đội tăng throughput bằng cách xử lý thật nhiều ticket chỉnh văn bản nhưng vấn đề mất tiến độ của người học vẫn tồn tại, **P1 chưa được phục vụ tốt**.

Thực hành phù hợp là:

- Giữ mục tiêu sản phẩm/dịch vụ.
- Xếp thứ tự công việc theo giá trị và rủi ro.
- Xem flow metrics cùng outcome và chất lượng.
- Dành năng lực khắc phục nguyên nhân sự cố lặp lại.

**Không có Sprint không có nghĩa không có kế hoạch hoặc không cần đối thoại với khách hàng.**

## 15. Đối chiếu quyết định trong XP và chất lượng kỹ thuật

### 15.1. XP là một cách hỗ trợ P7–P9, không thay định hướng giá trị

**Extreme Programming (XP)** có các thực hành như TDD, pair programming, continuous integration, refactoring, simple design và small releases. Những thực hành này giúp **phát hiện sai sớm và giữ khả năng thay đổi**.

Nhưng XP không tự quyết:

- Người dùng cần giải quyết vấn đề gì?
- Product Backlog ưu tiên hạng mục nào?
- Nghĩa vụ pháp lý nào áp dụng?
- Sự cố nào phải ứng cứu trước?

Cần kết hợp với **khám phá sản phẩm và quản lý luồng công việc** phù hợp.

### 15.2. TDD như bằng chứng P9, không phải điểm thành tích

Với trạng thái lưu tiến độ, nhóm có thể viết test cho quy tắc:

~~~java
// Minh họa Java độc lập cho một quy tắc nhỏ, không đại diện
// cho toàn bộ chức năng lưu hoặc kiểm soát bảo mật.
enum SaveResult { CONFIRMED, FAILED, UNKNOWN }

final class SaveMessage {
    static String forResult(SaveResult result) {
        return switch (result) {
            case CONFIRMED -> "Đã lưu";
            case FAILED -> "Không thể lưu";
            case UNKNOWN -> "Chưa xác định kết quả lưu";
        };
    }
}
~~~

Unit test có thể chứng minh **UNKNOWN không trả chuỗi “Đã lưu”**, nhưng chưa chứng minh backend đã ghi dữ liệu đúng, API không rò thông tin, UI có khả năng tiếp cận hay production vận hành ổn.

Một quyết định kỹ thuật phù hợp P9 là **chọn các mức kiểm chứng theo rủi ro**, không tuyên bố “90% test coverage đủ cho mọi chức năng”.

### 15.3. Continuous Integration: P3, P7 và P9

Nếu UI và API chỉ tích hợp ở cuối Sprint:

- Sai hợp đồng được phát hiện muộn.
- PBI không đạt DoD dù code đã xong.
- Developers phải làm lại dưới áp lực thời gian.

**CI** có thể giúp phát hiện sớm ở build/commit cụ thể, nhưng **CI xanh chỉ chứng minh những checks đã chạy trong phạm vi đó**. Contract/integration tests phải được lựa chọn và giữ tin cậy; test flaky cần điều tra, không chỉ rerun tới khi xanh.

### 15.4. Pair programming: P5, P6, P9 và P11

Pairing có thể hữu ích khi:

- Một module có kiến thức chỉ một người giữ.
- Cần debug vấn đề phức tạp.
- Thành viên mới cần hiểu code/test.
- Cần đánh giá nhiều phương án kỹ thuật trong thời gian ngắn.

**Không nhất thiết hai người phải làm mọi ticket**. Nếu pairing làm đội phân tán phải họp đêm thường xuyên, cần xem P8. Có thể dùng **phiên ghép cặp ngắn, async handoff và test/decision log** để giảm chi phí.

### 15.5. Refactoring: P9 và khả năng phản hồi với thay đổi V4

Một hệ thống mất nhiều ngày để sửa một trạng thái nhỏ vì code rối có thể kém linh hoạt hơn hệ thống có test và module hóa tốt. Refactoring liên tục, an toàn, theo mục tiêu là **đầu tư giảm chi phí thay đổi**.

Tuy nhiên một đề xuất **“viết lại toàn bộ hệ thống trong sáu tháng”** có thể xung đột P1/P3/P10 nếu không chứng minh rủi ro và lợi ích. Chọn refactoring **theo lát cắt có kiểm chứng**, ưu tiên nơi đang cản khả năng tạo giá trị hoặc gây sự cố.

### 15.6. Small releases và feature flags

Nhóm có thể:

- Tích hợp code nhỏ thường xuyên.
- Dùng feature flag để tách phần đã tích hợp khỏi phần đã mở cho người dùng, khi rủi ro cần.
- Kiểm tra các trạng thái bật/tắt và quản lý vòng đời cờ.
- Rollout theo phạm vi, quan sát và khôi phục khi thích hợp.

**Feature flag không phải giấy phép bỏ kiểm thử hoặc kiểm soát dữ liệu**, và rollback không tự khôi phục mọi loại dữ liệu đã bị mất.

## 16. Đối chiếu quyết định về user story, backlog và Product Goal

### 16.1. User story chỉ là một hình thức trao đổi nhu cầu

Một user story thông dụng:

> “Là người học, tôi muốn tiếp tục bài từ điểm đang dở để không lặp lại phần đã học.”

Nó giúp tập trung vào **ai cần giá trị gì và vì sao**, nhưng nếu chỉ có câu đó thì chưa đủ làm rõ:

- Khi nào hệ thống xác nhận đã lưu?
- Nếu mạng gián đoạn thì trạng thái nào hiển thị?
- Một người dùng khác có quyền xem tiến độ không?
- Kiểm chứng và Definition of Done liên quan?
- Điều gì nằm ngoài phạm vi lát cắt đầu?

**User story không phải hợp đồng đặc tả hoàn chỉnh**. Nó là lời mời hội thoại, có thể kết hợp acceptance examples và test.

### 16.2. Ví dụ acceptance criteria bằng Gherkin

~~~gherkin
Feature: Tiếp tục bài học với trạng thái lưu đáng tin

  Scenario: Nhận xác nhận lưu thành công
    Given người học đang học một bài hợp lệ
    When dịch vụ xác nhận tiến độ đã được lưu
    Then giao diện hiển thị "Đã lưu"
    And người học có thể đọc lại tiến độ được phép

  Scenario: Chưa có bằng chứng lưu thành công
    Given người học đã gửi yêu cầu lưu
    When kết nối ngắt trước khi nhận xác nhận đáng tin
    Then giao diện không khẳng định "Đã lưu"
    And hiển thị trạng thái chưa xác định theo quy tắc sản phẩm
~~~

Các scenario là **ví dụ diễn đạt hành vi**, không phải executable tests nếu chưa có step definitions, dữ liệu, môi trường và mã kiểm chứng tương ứng. Quy tắc **retry/đối soát sau timeout** cần được quyết định riêng nếu chưa nằm trong phạm vi.

### 16.3. Đối chiếu một quyết định chia nhỏ story

**Lựa chọn A:** chia “lưu tiến độ” thành “xây frontend” → “xây backend” → “xây database”, mỗi phần được đánh Done độc lập dù người học chưa làm được gì.

**Lựa chọn B:** chia thành các lát cắt dọc:

1. Người học đã xác thực lưu và đọc lại một điểm tiến độ, có kiểm soát quyền.
2. Giao diện thể hiện rõ khi lưu thất bại hoặc kết quả chưa xác định.
3. Khôi phục/đối soát sau gián đoạn theo chính sách được làm rõ.
4. Mở rộng nhiều thiết bị hoặc phân khúc sau khi đã có phản hồi.

| Nguyên tắc | Đối chiếu |
|---|---|
| **P1/P3** | B có Increment có giá trị và phản hồi sớm hơn nếu mỗi lát cắt đạt DoD |
| **P4** | B đòi hỏi rõ hành vi xuyên UI–API–DB, không bàn giao từng tầng thiếu ngữ cảnh |
| **P7** | Có thể chứng minh lát cắt hoạt động thực, không chỉ hoàn tất từng chuyên môn |
| **P10** | Tránh xây phần mở rộng khi chưa biết có cần |
| **P9** | Test và tích hợp thường xuyên bảo vệ thay đổi |

Tuy nhiên không phải mọi phần kỹ thuật độc lập đều vô ích: **enabler, spike hoặc refactoring** có thể tạo giá trị gián tiếp nếu kết quả, rủi ro và liên hệ Product Goal rõ. Vấn đề là **không đánh đồng code theo tầng với Increment dùng được**.

### 16.4. Backlog ordering phải hướng đến kết quả

Ví dụ Product Owner có ba PBI:

| PBI | Giả thuyết giá trị | Rủi ro/đánh đổi |
|---|---|---|
| Sửa lỗi lưu tiến độ làm mất dữ liệu | Giảm mất niềm tin và nguy cơ người học bỏ dở | Cần xác minh mức tác động và ứng cứu nếu đang xảy ra |
| Thêm animation cho nút học tiếp | Có thể cải thiện trải nghiệm cảm nhận | Chưa chắc tác động tới completion |
| Thêm contract tests và dữ liệu test cô lập | Giảm lỗi tích hợp/làm lại, tạo khả năng giao an toàn | Tốn năng lực feature ngắn hạn |

Thứ tự không được tự động quyết bằng số story points hoặc ai yêu cầu to nhất. Cần xem **Product Goal, tín hiệu người dùng, rủi ro, nghĩa vụ và khả năng kiểm chứng**.

### 16.5. Phân biệt output, outcome và impact

- **Output:** đã thêm ba màn hình, 12 endpoint, 25 tests.
- **Outcome:** người học có thể tiếp tục bài ít lỗi hơn; tỷ lệ hoàn thành bài tăng trong bối cảnh được đo.
- **Impact dài hạn:** sản phẩm tạo giá trị bền vững cho người học và tổ chức.

Không thể suy từ **số output** sang outcome/impact nếu thiếu dữ liệu. Nhưng cũng không vì outcome đo chậm mà coi **Increment/DoD** không quan trọng; cần cả **bằng chứng năng lực phần mềm** và **bằng chứng giá trị sử dụng**.

## 17. Nhóm phân tán: đối chiếu quyết định giao tiếp với V1, P4, P6 và P8

### 17.1. Tình huống: một quyết định chỉ tồn tại trong cuộc gọi

Đội có Product Owner ở Việt Nam, Developers ở nhiều múi giờ và đối tác SSO ở châu Âu. Trong một video call, một số người chốt API hỗ trợ ba trạng thái **CONFIRMED, FAILED, UNKNOWN**.

Nhưng:

- Developer không dự họp chỉ thấy contract cũ.
- Trong chat có biểu tượng 👍, không rõ ai quyết và phê duyệt điều gì.
- Ticket chuyển sang Done sau merge nhưng integration test còn chờ.
- Người có giờ làm muộn thường xuyên phải dự họp đêm.

**V1 và P6** không đòi hỏi càng nhiều video call càng tốt. Chúng đòi hỏi **trao đổi có chất lượng và cùng hiểu thông tin**.

### 17.2. Chọn đồng bộ hay bất đồng bộ

| Vấn đề | Cách phối hợp phù hợp thường thấy | Bằng chứng hiểu chung |
|---|---|---|
| Hỏi ngắn về tên trường API đã có contract | Async trong PR/spec | Câu trả lời có link nguồn |
| Bất đồng về quy tắc timeout và rủi ro dữ liệu | Cuộc thảo luận ngắn có chuẩn bị; sau đó ghi quyết định | AC + API contract + test được cập nhật |
| Xin review PR nhỏ có mô tả/test | Async trong PR | Comment gắn diff, kiểm tra CI |
| Debug race condition không tái hiện dễ | Pairing sync có mục tiêu, giới hạn thời gian | Log, test tái hiện, mô tả nguyên nhân |
| Trạng thái công việc thường ngày | Board/ticket, trao đổi trực tiếp khi có blocker | Workflow và điều kiện Done rõ |
| Incident ảnh hưởng người dùng | Kênh ứng cứu theo mức tác động và người trực hợp lệ | Incident log và quyết định giảm tác động |

**Async-first** có thể bảo vệ thời gian tập trung nhưng không loại bỏ hội thoại khi mơ hồ. **Sync-first** có thể rút ngắn tranh luận nhưng không thể coi người vắng họp là đã đồng ý.

### 17.3. Một handoff đúng tinh thần Agile

~~~yaml
# Mẫu minh họa; có thể ghi trong ticket/PR chứ không cần file riêng.
work_item: "LEARN-42"
product_goal: "Người học tiếp tục bài từ điểm đang dở đáng tin"
current_state: "Backend đã merge; PBI chưa đạt Definition of Done"
decisions:
  - "UNKNOWN không được hiển thị 'Đã lưu'"
source_of_truth:
  acceptance_criteria: "AC-07"
  api_contract: "progress-api-v2"
evidence:
  - "Unit và contract tests gắn build"
not_yet_verified:
  - "Integration test với database"
blocker: "Môi trường thử dùng chung chưa khả dụng"
next_step: "Khôi phục môi trường, chạy kiểm tra, xác nhận UI xử lý UNKNOWN"
receiver: "Người được phân công với quyền và năng lực phù hợp"
quality_note: "Không báo Done trước DoD"
~~~

Mẫu không thay quyền quyết định Product Owner/Developers. Nó giúp người nhận **có thể hành động an toàn** ngay khi bắt đầu giờ làm của mình.

### 17.4. P8: công bằng múi giờ và nhịp bền vững

Đặt một cuộc họp đồng bộ không tự sai, nhưng nếu cùng một vùng phải thức đêm mỗi ngày, nhóm nên đánh giá:

- Có thể chuyển cập nhật thường lệ sang async không?
- Phần đồng bộ còn lại có thực sự cần thảo luận nhiều chiều không?
- Có thể luân phiên khung giờ bất tiện và gửi tài liệu trước không?
- Người không dự có thể góp ý trước khi quyết định quan trọng được chốt?
- Có kênh riêng và quy trình thích hợp cho vấn đề nhạy cảm, riêng tư không?
- Có biện pháp tiếp cận cho người dùng công nghệ hỗ trợ hoặc kết nối mạng yếu không?

**Giao tiếp có ý nghĩa** không phải số giờ hiện diện; nó là khả năng cùng hiểu, quyết định và tiếp tục công việc mà không gây chi phí nhân sự bất công.

### 17.5. Cách đo cải tiến cộng tác

Đo ở cấp dòng công việc:

- **Số vòng hỏi lại** vì thiếu bối cảnh.
- **Work item age** ở bước chờ review/decision.
- Lỗi hiểu sai API contract phát hiện muộn.
- Tỷ lệ quyết định ảnh hưởng sản phẩm có nguồn hiện hành.
- Cảm nhận công bằng và tải họp **ở mức phù hợp quyền riêng tư**.
- Chất lượng sau phát hành và khả năng tiếp tục làm việc.

Đừng đo “số tin nhắn/người”, “phút online” như đại diện cho hiệu quả Agile. Các số đó có thể khuyến khích hoạt động hình thức và xâm phạm đời sống cá nhân.

## 18. Quản trị, ràng buộc và thời hạn: đối chiếu đúng bốn giá trị

### 18.1. Agile không loại bỏ pháp lý, bảo mật hoặc hợp đồng

Một nền tảng học có thể chịu những ràng buộc về:

- Quyền truy cập tiến độ người học.
- Cách xử lý dữ liệu cá nhân, lưu giữ và xóa dữ liệu theo nguồn đã xác nhận.
- Yêu cầu bảo mật, khả năng tiếp cận, vận hành.
- Chứng cứ kiểm chứng và thẩm quyền phê duyệt trước release.
- Hạn hợp đồng hoặc yêu cầu nhà cung cấp.

**Không tự suy ra một nghĩa vụ hoặc thời hạn áp dụng cho mọi sản phẩm.** Khi đưa vào quyết định, phải nêu **nguồn, phiên bản, phạm vi và người có thẩm quyền diễn giải**.

### 18.2. Tình huống V3: cộng tác với khách hàng nhưng không được bỏ hợp đồng

Đối tác muốn thêm một vai trò quản trị mới có quyền đọc toàn bộ tiến độ, nói rằng “đội Agile nên linh hoạt và hợp tác”.

Đối chiếu:

| Điều cần xem | Cách phân tích |
|---|---|
| **V3** | Lắng nghe vấn đề nghiệp vụ: họ cần hỗ trợ học viên thế nào? |
| **V1/P4** | Mời người hiểu dữ liệu/quyền, Product Owner và Developers trao đổi |
| **P10** | Có cách đáp ứng nhỏ hơn như quyền giới hạn theo nhóm/học viên được phép không? |
| **P9/P7** | Kiểm chứng phân quyền trên API, không chỉ UI |
| **Ràng buộc** | Vai trò có phù hợp chính sách dữ liệu/hợp đồng và thẩm quyền thật không? |

**Cộng tác không cho phép cấp quyền rộng chỉ để làm đối tác hài lòng**. Có thể làm rõ nhu cầu, điều chỉnh giải pháp hợp lệ và minh bạch nếu một phần yêu cầu không thể đáp ứng.

### 18.3. Tình huống V4: deadline thật và dự báo bất định

Một cuộc phát hành có ngày ràng buộc xác nhận. Người quản lý muốn coi mọi PBI là “cam kết tuyệt đối”, kể cả khi CI chưa kiểm thử đầy đủ.

Nhóm nên phân biệt:

- **Hạn thật**: có nguồn, người có thẩm quyền và hậu quả cụ thể.
- **Phạm vi bắt buộc**: phần nào không thể thiếu để đáp ứng?
- **Dự báo triển khai**: phụ thuộc năng lực, rủi ro, kiểm chứng và yếu tố ngoài.
- **Phương án thích ứng hợp lệ**: giảm scope, giai đoạn hóa, thay thứ tự, tăng phản hồi sớm.
- **Guardrails**: DoD, kiểm soát bắt buộc, dữ liệu người dùng và nhịp bền vững.

**Không dùng “Agile phản hồi với thay đổi” để hứa chắc ngày đã biết rủi ro không thể đạt**, cũng không bỏ qua nghĩa vụ thật vì thích một plan linh hoạt.

### 18.4. Bằng chứng kiểm chứng gắn với Increment

Một test result có ích khi trả lời:

1. **Yêu cầu/kiểm soát nào** đang được kiểm chứng?
2. **Commit/build và môi trường** nào tạo kết quả?
3. Test/đánh giá đã chạy và **PASS/FAIL/NOT RUN**?
4. Phạm vi và **giới hạn của bằng chứng**?
5. Ai có quyền đánh giá/phê duyệt nếu quy định yêu cầu?
6. Khi API, cấu hình hoặc chính sách đổi, có cần kiểm tra lại không?

Một badge CI xanh trên commit cũ không chứng minh artifact release mới đáp ứng kiểm soát. **Bằng chứng có nguồn và bối cảnh** là cách tài liệu hỗ trợ phần mềm hoạt động, không đối lập V2.

### 18.5. Quản lý ngoại lệ có trách nhiệm

Nếu kiểm tra bắt buộc **không chạy vì môi trường ngừng hoạt động**, nhóm:

- Không tự đổi NOT RUN thành PASS.
- Không đánh dấu PBI Done nếu DoD liên quan chưa đạt.
- Hiển thị blocker và tác động.
- Khôi phục môi trường hoặc áp dụng phương án xác minh được phép.
- Nếu chính sách có cơ chế ngoại lệ, trình đúng thẩm quyền, ghi phạm vi, lý do, thời hạn và biện pháp giảm rủi ro.
- Không giả định mọi nghĩa vụ đều cho phép miễn trừ.

Điều này phù hợp **P7/P9** và sự minh bạch Agile; không phải “chống Agile” chỉ vì cần bằng chứng.

### 18.6. Lúc nào nên nói “chưa biết”?

Một quyết định kỹ thuật rủi ro cao không có đủ dữ liệu thường nên ghi **“chưa xác minh”**, cùng người phụ trách và mốc xem lại, thay vì ép đội đồng ý.

“Chưa biết” có thể trở thành **spike nghiên cứu có timebox**, review chuyên môn hoặc thử nghiệm nhỏ. Điều Agile đòi hỏi là **học nhanh hơn bằng bằng chứng**, không giả vờ chắc chắn.

## 19. Đo kết quả lựa chọn mà không biến chỉ số thành mục tiêu

### 19.1. Phân biệt câu hỏi giá trị, năng lực giao hàng và sức khỏe hệ thống

| Câu hỏi | Nhóm tín hiệu | Ví dụ |
|---|---|---|
| **Có tạo giá trị?** | Outcome/người dùng | Tỷ lệ học tiếp đúng tiến độ, hoàn thành bài, phản hồi lỗi lưu |
| **Có sản phẩm hoạt động?** | Increment/DoD | PBI đạt DoD, test cần thiết, tính năng sử dụng được |
| **Có dòng công việc hiệu quả?** | Kanban metrics | WIP, throughput, cycle time, work item age, blocker duration |
| **Có khả năng đổi an toàn?** | Engineering quality | CI stability, lỗi hồi quy, rework, thời gian phát hiện lỗi |
| **Có bền vững?** | Con người và vận hành | Overtime, tải ứng cứu, thời gian họp, chuyển ngữ cảnh |
| **Có học và thích ứng?** | Decision/experiment evidence | Giả thuyết được kiểm tra, action retro được làm và xem lại |

Không có **một chỉ số Agile tổng hợp**. Velocity hay số story points không thể thay tất cả những tín hiệu trên; dữ liệu của hai nhóm dùng cách ước lượng khác nhau cũng khó so sánh trực tiếp.

### 19.2. Ví dụ: throughput tăng nhưng giá trị có tăng?

Giả sử trong hai Sprint giả định:

| Chỉ báo | Sprint A | Sprint B |
|---|---:|---:|
| PBI bắt đầu | 12 | 10 |
| PBI đạt DoD | 7 | 9 |
| Lỗi sai API contract phát hiện cuối Sprint | 3 | 1 |
| PBI còn chờ review quá ba ngày | 4 | 1 |
| Lỗi người học liên quan mất tiến độ sau release | Chưa đủ dữ liệu | Chưa đủ dữ liệu |

Sprint B có tín hiệu flow và hoàn tất tốt hơn, nhưng **chưa được kết luận outcome người dùng cải thiện**. Có thể loại việc, độ khó, người tham gia và sự cố khác nhau; cần xem thêm dữ liệu và phản hồi.

### 19.3. Tránh Goodhart và chỉ số bị “chơi”

Nếu đặt mục tiêu **mỗi Developer đóng mười ticket/ngày**, người ta có thể tách ticket rất nhỏ, báo Done sớm, bỏ kiểm tra khó.

Nếu đặt mục tiêu **mọi CI run phải xanh**, người ta có thể bỏ hoặc vô hiệu hóa test flaky thay vì sửa nguyên nhân.

Nếu đặt mục tiêu **zero incidents**, người ta có thể đổi nhãn incidents thành defects hoặc ngại báo cáo.

Nếu đặt mục tiêu **không đổi backlog**, đội có thể ngừng ghi phản hồi quan trọng.

Thước đo phải được dùng để **phát hiện điều cần cải tiến**, kết hợp guardrails và hội thoại dựa trên bằng chứng; không biến mỗi con số thành đánh giá cá nhân.

### 19.4. Một thử nghiệm phải có điều kiện dừng

Ví dụ:

~~~yaml
# Thẻ thử nghiệm minh họa; không phải cấu hình bắt buộc.
experiment_id: AGILE-DECISION-05
decision: "Thử contract test sớm cho PBI thay API lưu tiến độ"
hypothesis: >
  Nếu Product Owner, frontend, backend và Tester thống nhất ví dụ
  trước implementation, kiểm tra contract chạy trước merge,
  thì lỗi hiểu sai hợp đồng sẽ được phát hiện sớm hơn.
scope: "Những PBI thay API lưu tiến độ trong hai Sprint"
actions:
  - "Làm rõ ví dụ success/fail/unknown"
  - "Ghi quyết định ở API contract hiện hành"
  - "Tích hợp contract tests vào CI"
values: ["V1", "V2", "V3", "V4"]
principles: ["P1", "P3", "P4", "P7", "P9", "P10", "P12"]
signals:
  - "Lỗi contract phát hiện sau tích hợp"
  - "Work item age ở bước review/integration"
  - "Số vòng hỏi lại vì thiếu hợp đồng"
guardrails:
  - "Không bỏ Definition of Done"
  - "Không tăng overtime thường trực"
  - "Không đưa dữ liệu cá nhân vào test/report trái chính sách"
review_point: "Retrospective sau thử nghiệm"
decision_options: ["Giữ", "Điều chỉnh", "Dừng"]
~~~

Các mã V/P ở đây là **nhãn phân tích học tập**, không phải bằng chứng tự thân. Nếu kết quả sau thử nghiệm không đổi, nhóm có trách nhiệm **điều tra giả thuyết, không che dữ liệu**.

### 19.5. Kiểm tra kết quả trước–sau có thể bị nhiễu

Một Sprint ít lỗi hơn có thể do:

- Phạm vi feature nhỏ hơn.
- Không xảy ra incident bên ngoài.
- Nhiều thành viên có kinh nghiệm hơn tham gia.
- Môi trường tích hợp ổn định hơn.
- Cách ghi nhận/định nghĩa lỗi đổi.
- Người dùng chưa được tiếp xúc đủ để phát hiện vấn đề.

Khi đọc kết quả, ghi rõ **điều kiện thay đổi và giới hạn mẫu**. Không cần thí nghiệm khoa học phức tạp cho mọi cải tiến, nhưng phải tránh khẳng định quan hệ nhân quả không được dữ liệu hỗ trợ.

### 19.6. Những tín hiệu định tính không nên bỏ qua

Ngoài số liệu, nghe:

- Người dùng có hiểu trạng thái lưu không?
- Người hỗ trợ có tái hiện và giải thích lỗi nhanh hơn không?
- Developers có tin kết quả CI hay thường rerun vì flaky?
- Thành viên phân tán có truy cập được quyết định sau cuộc họp không?
- Người trong nhóm có đủ an toàn để nêu rủi ro trước khi quá muộn?

**Trải nghiệm thật cần được tôn trọng** dù không gói hết trong dashboard. Đồng thời, cần phân biệt cảm nhận với sự kiện để tránh kết luận thiếu cơ sở.

## 20. Case study tổng hợp: đội phải chọn giữa roadmap, chất lượng và phản hồi người học

### 20.1. Bối cảnh sản phẩm

Một Scrum Team phát triển nền tảng học trực tuyến với Product Owner, Scrum Master và Developers về frontend, backend, kiểm thử và vận hành. Đội có một số stakeholders doanh nghiệp, chuyên gia bảo mật và nhà cung cấp định danh SSO.

**Product Goal minh họa:**

> “Người học có thể bắt đầu và tiếp tục bài đầu một cách đáng tin, từng bước tăng tỷ lệ hoàn thành bài trong tuần đầu.”

**Sprint Goal ban đầu:**

> “Người học mở lại bài đang dở ở đúng vị trí đã lưu, với phản hồi rõ về trạng thái lưu.”

Đội đã chuẩn bị ba Product Backlog Items:

| PBI | Mục đích | Tình trạng |
|---|---|---|
| **LEARN-201** | Lưu và đọc lại tiến độ cho cùng tài khoản | Backend code đã merge, integration test chưa hoàn tất |
| **LEARN-202** | Hiển thị trạng thái CONFIRMED/FAILED/UNKNOWN | Frontend đang phát triển, contract API còn bất đồng |
| **LEARN-203** | Animation và cá nhân hóa nút “Tiếp tục” | Mockup đã được stakeholder phê bình tích cực |

Giữa Sprint, support ghi nhận người học mạng yếu thấy thông báo **“Đã lưu”** nhưng khi mở lại không thấy tiến độ. Một test tích hợp phát hiện API có thể timeout trước khi client nhận xác nhận.

### 20.2. Các bằng chứng được phép dùng

Giả sử trong giai đoạn quan sát **hoàn toàn giả định**:

- Có **12 báo cáo** liên quan lưu tiến độ, trong đó **5 trường hợp** có bước tái hiện phù hợp.
- Một kịch bản test trên môi trường kiểm soát cho thấy **thông báo thành công giả** khi request timeout.
- Product Owner có dữ liệu rằng người học bỏ dở sau lần mất tiến độ, nhưng chưa đủ cơ sở kết luận toàn bộ tỷ lệ bỏ dở do lỗi này.
- CI đang có integration tests **không ổn định** vì dữ liệu thử dùng chung.
- Một Developer backend ở múi giờ khác không dự cuộc họp đổi hợp đồng API.
- Stakeholder vẫn muốn đưa animation lên bản demo theo lịch đã công bố.
- DoD của đội yêu cầu **tính năng tích hợp và các kiểm tra liên quan đạt** trước khi báo Done.

**Ranh giới dữ liệu:** đây là case giả định để học cách xem xét quyết định, không mô tả sự cố thật của doanh nghiệp nào. Những con số không chứng minh nhân quả hoặc độ nghiêm trọng pháp lý.

### 20.3. Lịch sử quyết định trước khi đối chiếu

| Thời điểm | Sự kiện / quyết định | Điều chưa rõ |
|---|---|---|
| Đầu Sprint | Chọn ba PBI, kỳ vọng tạo trải nghiệm học tiếp | Chưa có ví dụ chấp nhận cho timeout |
| Ngày 3 | Stakeholder đề nghị không đổi demo roadmap | Mức ràng buộc của lịch demo và chi phí cơ hội |
| Ngày 4 | Người học gửi phản hồi về mất tiến độ | Tỷ lệ và phạm vi ảnh hưởng |
| Ngày 5 | Tester tái hiện trạng thái “Đã lưu” giả | Phạm vi đường lỗi và contract |
| Ngày 6 | Backend đề nghị xử lý timeout thành FAILED | Có thể dữ liệu đã ghi nhưng client chưa biết |
| Ngày 7 | Frontend đề nghị thêm UNKNOWN | Product Owner chưa chốt thông điệp người dùng |
| Ngày 8 | Quản lý đề nghị bỏ integration tests để kịp demo | Xung đột với DoD và rủi ro người dùng |

Timeline giúp thấy **có thông tin mới thực sự**. Không nên xem đây chỉ là “team thay đổi scope vô kỷ luật”.

### 20.4. Bốn quyết định đang tranh cãi

**D1 — Giữ nguyên thứ tự backlog và triển khai animation trước vì đã có roadmap.**

**D2 — Thay đổi cách trình bày trạng thái lưu, làm rõ API contract và kiểm chứng lỗi sớm.**

**D3 — Bỏ integration tests hoặc chuyển PBI sang Done dù chưa đạt chất lượng để kịp demo.**

**D4 — Thiết lập chính sách triage incident, giảm WIP và dùng contract tests/CI để việc tương tự không lặp.**

Đây không hẳn là bốn lựa chọn loại trừ nhau: đội có thể **ưu tiên D2 và D4**, không chọn D3, còn D1 được sắp lại sau khi đánh giá thông tin mới.

### 20.5. Ai có quyền quyết định phần nào?

| Nội dung | Cách phân định |
|---|---|
| **Giá trị và thứ tự Product Backlog** | Product Owner chịu accountability trong Scrum, có tham vấn stakeholders |
| **Cách thực hiện kỹ thuật, kế hoạch Sprint và chất lượng Increment** | Developers tự quản trong phạm vi Scrum và DoD |
| **Hiệu quả Scrum, trở ngại tổ chức** | Scrum Master hỗ trợ và thúc đẩy cải tiến |
| **Kiểm soát quyền/riêng tư hoặc release đặc thù** | Chức năng có thẩm quyền theo chính sách tổ chức |
| **Lịch demo/stakeholder kỳ vọng** | Cần làm rõ cam kết thật, mức được phép điều chỉnh và truyền thông |
| **Ứng cứu sự cố đang gây hại** | Kênh/đầu mối theo chính sách incident, phối hợp với Scrum Team |

**V1/V3/P4** khuyến khích mọi bên cung cấp thông tin, nhưng không cho phép người có quyền lực nhất trong cuộc gọi **tự quyết bỏ DoD hoặc cấp quyền dữ liệu**.

### 20.6. Đối chiếu nhanh bốn giá trị cho D1–D4

| Quyết định | V1 — Tương tác | V2 — Phần mềm hoạt động | V3 — Khách hàng | V4 — Thích ứng |
|---|---|---|---|---|
| **D1 Giữ roadmap bất chấp tín hiệu lỗi** | Có nguy cơ bỏ qua kỹ thuật/tester | Animation không giải quyết lưu thất bại | Không phản ánh phản hồi mới | Căng thẳng rõ |
| **D2 Làm rõ contract và sửa trạng thái** | Cần hội thoại PO/UI/API/Tester | Hành vi có thể kiểm chứng bằng test | Giải quyết một vấn đề người học ghi nhận | Điều chỉnh theo bằng chứng |
| **D3 Bỏ test để kịp demo** | Có thể tạo áp lực và che lo ngại | Xung đột DoD và rủi ro sản phẩm | Có thể gây hại người dùng | “Nhanh” không đồng nghĩa thích ứng đúng |
| **D4 Triage, WIP, CI contract tests** | Giảm hiểu sai, hỗ trợ phối hợp | Giúp Increment đạt DoD sớm hơn | Giảm lỗi cản giá trị | Tạo khả năng phản hồi cho những thay đổi sau |

Đây là **đánh giá giả định cần kiểm tra qua thực tế**, không phải kết luận rằng mọi người liên quan D1/D3 cố ý làm sai. Những quyết định có thể có **ràng buộc chưa nêu**; cần làm rõ trước khi chọn.

## 21. Phân tích D1–D4 qua mười hai nguyên tắc

### 21.1. Ma trận nguyên tắc theo quyết định

| Nguyên tắc | D1 — Giữ roadmap | D2 — Sửa trạng thái/contract | D3 — Bỏ kiểm tra | D4 — Cải tiến flow/CI |
|---|---|---|---|---|
| **P1 Giá trị sớm** | Căng thẳng nếu ưu tiên hiệu ứng hơn lỗi người học | Có cơ hội tạo giá trị đáng tin | Rủi ro giao tác hại | Hỗ trợ giá trị ổn định hơn |
| **P2 Đón thay đổi** | Chưa phản hồi tín hiệu mới | Điều chỉnh có mục tiêu | “Đổi kế hoạch” nhưng theo áp lực, không theo giá trị | Tăng khả năng thích ứng lần sau |
| **P3 Giao thường xuyên** | Demo có thể nhanh nhưng giá trị chưa rõ | Chia lát cắt có DoD | Bản chưa kiểm chứng không đáp ứng tinh thần | CI hỗ trợ nhịp giao |
| **P4 Nghiệp vụ–kỹ thuật hợp tác** | Có nguy cơ một chiều | Cần Three Amigos và quyết định rõ | Không giải quyết mơ hồ nghiệp vụ | Chuẩn hóa trao đổi đúng lúc |
| **P5 Tin tưởng đội** | Có thể áp đặt thứ tự thiếu dữ liệu kỹ thuật | Cho Developers chủ động kiểm chứng | Dễ áp lực bỏ nguyên tắc nghề nghiệp | Đội cùng định hình policy |
| **P6 Giao tiếp hiệu quả** | Phụ thuộc roadmap cũ | API contract/AC có nguồn và hội thoại | Không giúp người khác hiểu đúng | Handoff/PR dễ truy tìm |
| **P7 Phần mềm hoạt động** | Animation có thể chạy nhưng lỗi lưu còn | Test được hành vi lưu đúng | Căng thẳng trực tiếp với DoD | Tăng tỷ lệ Increment có bằng chứng |
| **P8 Nhịp bền vững** | Có thể dồn sửa lỗi sau demo | Cần lập lại kế hoạch năng lực | Tăng nguy cơ trực sửa production | Hỗ trợ giảm rework nếu hiệu quả |
| **P9 Xuất sắc kỹ thuật** | Chưa xử lý test flaky | Sửa test/contract theo rủi ro | Tước hàng rào chất lượng | CI/TDD/refactoring phù hợp |
| **P10 Đơn giản** | Có thể thêm thứ chưa cần | Lát cắt nhỏ vào vấn đề thật | “Bỏ test” không phải giảm việc thừa | Giảm vòng lặp làm lại |
| **P11 Tự tổ chức** | Có nguy cơ chỉ đạo từ lịch demo | Developers cùng chọn giải pháp kỹ thuật | Ép đội bỏ quality gates | Cùng chọn WIP/policy |
| **P12 Nhìn lại và cải tiến** | Cần xem lại lý do giữ plan | Có thể thử và đo | Không học từ lỗi phát hiện | Là thử nghiệm cải tiến có thể đánh giá |

**Đừng cộng số ô “ủng hộ”** để chọn phương án. D3 có xung đột **DoD bắt buộc**, nên không thể được hợp thức hóa bằng một vài ô có vẻ thuận lợi cho thời gian demo.

### 21.2. Những nguyên tắc có tác động trực tiếp nhất

Đội có thể ưu tiên phân tích sâu:

- **P1:** người học nhận giá trị gì từ bản giao mới?
- **P2:** thông tin lỗi mới có làm giả định ban đầu sai?
- **P4:** ai cần thống nhất nghĩa của CONFIRMED/FAILED/UNKNOWN?
- **P7:** bản Increment có thực sự hoạt động và đạt DoD?
- **P8/P9:** sự cố và bỏ test có tạo vòng lặp quá tải–lỗi–làm lại?
- **P10:** có cần hoàn thành animation trước khi sửa lỗi lưu?
- **P12:** cách làm nào cần thử để không lặp sai contract?

Những nguyên tắc khác vẫn được quét để không bỏ dấu hiệu như **thiếu quyền tự quản** hoặc **thông tin không tới người ở múi giờ khác**.

### 21.3. Chọn quyết định thay thế hợp lệ

Sau khi làm rõ ràng buộc và dữ liệu:

1. Product Owner ưu tiên **hành vi lưu tiến độ đáng tin** và thảo luận chi phí lùi animation.
2. Product Owner, Developers, Tester làm rõ **trạng thái UNKNOWN** và cách UI thông báo cho người học.
3. Developers chia lát cắt dọc, cập nhật contract và viết test theo rủi ro.
4. Tính năng chỉ báo **Done khi đạt DoD**. Không tự coi một build thiếu integration test là Increment đủ chất lượng.
5. Với lịch demo, nhóm minh bạch **phần đã qua kiểm chứng và phần chưa**, hoặc điều chỉnh phạm vi demo; không làm giả kết quả.
6. Scrum Master hỗ trợ tháo blocker môi trường test, thúc đẩy cải tiến cách phối hợp.
7. Những quyền quyết định đặc thù của tổ chức vẫn được tôn trọng.

**Đây là phương án hợp lý trong dữ liệu giả định**, không phải công thức áp dụng mọi dự án. Nếu có nghĩa vụ/hạn được xác nhận khác, cần đánh giá lại lựa chọn hợp lệ.

### 21.4. Lát cắt thử nghiệm nhỏ hơn kế hoạch cũ

**Lát cắt A:** người học đã xác thực lưu và đọc lại điểm tiến độ, có kiểm soát quyền và test tích hợp cần thiết.

**Lát cắt B:** UI/API cùng hiểu CONFIRMED/FAILED/UNKNOWN; không báo “Đã lưu” khi kết quả chưa biết.

**Lát cắt C:** khi mạng khôi phục, người học được thông báo/đối soát theo chính sách được xác nhận; bổ sung kiểm tra tương ứng.

Nhóm có thể đo **số người học tiếp tục bài đúng**, lỗi trạng thái lưu và mức độ hiểu thông báo sau khi triển khai từng lát cắt. Nếu một lát cắt **chưa đạt DoD**, nó không được gọi là Increment Done.

### 21.5. Quyết định kỹ thuật: không chọn “viết lại hệ thống”

Trong Retrospective, một Developer đề xuất **viết lại toàn bộ API lưu tiến độ** vì code cũ khó sửa.

Đối chiếu:

- **P9:** có bằng chứng kỹ thuật nào cho thấy kiến trúc cũ ngăn thay đổi an toàn?
- **P10:** có lát cắt refactor nhỏ giảm rủi ro trước khi rewrite toàn hệ thống?
- **P1/P3:** rewrite dài sẽ trì hoãn giá trị người học ra sao?
- **P8:** rewrite song song ứng cứu có gây quá tải?
- **V4:** có thể thử sửa một phần rồi đánh giá, hay cần quyết định lớn ngay?

Một phương án phù hợp có thể **bổ sung test đặc trưng, refactor vùng xử lý trạng thái, kiểm chứng tích hợp rồi xem lại**, thay vì bác bỏ mọi cải tiến kỹ thuật hoặc chấp nhận rewrite theo cảm tính.

### 21.6. Quyết định cộng tác: cuộc họp không phải nguồn duy nhất

Đội có Developer ở múi giờ khác và chuyên gia SSO:

1. Gửi trước vấn đề và các ví dụ.
2. Họp ngắn để giải quyết phần mơ hồ cần đồng bộ.
3. Ghi **đã quyết/chưa quyết**, owner và API contract/AC phiên bản mới.
4. Gắn link trong PBI/PR và kèm kiểm tra hành vi.
5. Người vắng mặt có kênh hỏi/nhận phản hồi trong giờ làm.

Điều này phục vụ **V1/P4/P6** mà không buộc mọi người trực tuyến 24/7; đồng thời làm tăng khả năng **phần mềm hoạt động đúng theo một hợp đồng chung**.

## 22. Thử nghiệm quyết định, xem kết quả và điều chỉnh

### 22.1. Ghi decision record thay vì chỉ tuyên bố “chúng ta đã Agile”

~~~yaml
# Mẫu quyết định minh họa, không phải bằng chứng một dự án thật.
decision_id: DEC-LEARN-016
date: "Ngày ra quyết định được ghi trong công cụ nhóm"
product_goal: "Người học lưu và tiếp tục bài đáng tin"
problem: "UI có thể thông báo Đã lưu khi kết quả ghi chưa xác định"
observations:
  - "Có báo cáo người học mất tiến độ với bước tái hiện"
  - "Integration test xác định tình huống timeout gây trạng thái sai"
  - "API contract hiện hành chưa mô tả UNKNOWN"
uncertainties:
  - "Tỷ lệ người học bị ảnh hưởng thực tế chưa đủ dữ liệu"
  - "Chi phí xử lý khi đồng bộ lại sau timeout chưa rõ"
constraints:
  - "Giữ kiểm soát quyền truy cập và Definition of Done"
  - "Không làm giả kết quả test hoặc approval"
options:
  - "Giữ animation và roadmap cũ"
  - "Sửa trạng thái và contract trước"
  - "Bỏ test để theo kịp demo"
decision: "Ưu tiên lát cắt trạng thái lưu và kiểm chứng phù hợp"
accountabilities:
  product_backlog: "Product Owner"
  implementation_quality: "Developers"
  scrum_effectiveness: "Scrum Master"
values: ["V1", "V2", "V3", "V4"]
principles: ["P1", "P2", "P4", "P7", "P8", "P9", "P10", "P12"]
actions:
  - "Làm rõ ví dụ nghiệp vụ cùng Product Owner/Developers/Tester"
  - "Cập nhật AC và API contract phiên bản hiện hành"
  - "Chạy contract/integration checks theo rủi ro"
  - "Trì hoãn animation nếu cần để giữ Sprint Goal và DoD"
  - "Thử giảm WIP và làm rõ handoff"
signals:
  - "Số lỗi lưu có bước tái hiện"
  - "Lỗi sai hợp đồng được phát hiện trước/ sau tích hợp"
  - "Work item age ở review và integration"
  - "PBI đạt DoD; tỷ lệ người học tiếp tục bài khi đủ dữ liệu"
guardrails:
  - "Không bỏ kiểm soát bắt buộc"
  - "Không coi NOT RUN là PASS"
  - "Không tăng làm thêm giờ thường trực"
review_point: "Sprint Retrospective sau hai Sprint thử nghiệm"
decision_options: ["Giữ", "Điều chỉnh", "Dừng"]
~~~

**Nhãn giá trị/nguyên tắc không chứng minh quyết định tự đúng.** Nó chỉ giúp người xem hiểu **căn cứ và tiêu chí đánh giá**.

### 22.2. Lập kế hoạch thử nghiệm hai Sprint

**Sprint A — Thiết lập vòng phản hồi sớm**

- Product Owner xác nhận acceptance examples liên quan kết quả lưu.
- Developers chia PBI dọc và xử lý nhánh trạng thái UNKNOWN.
- Contract test cho API chạy trong CI trước merge.
- Một integration test rủi ro cao kiểm tra lưu/đọc theo quyền.
- Review hợp đồng và các quyết định có nguồn hiện hành.
- CI/test environment blocker được ghi rõ; không đổi trạng thái Done khi chưa đạt.
- Retrospective kiểm tra tác động lên thời gian review và áp lực cuối Sprint.

**Sprint B — Xem hiệu lực, giảm việc lặp lại**

- Theo dõi lỗi người dùng và tình huống khó tái hiện.
- Cải thiện test data isolation nếu CI flaky tiếp diễn.
- Thử WIP limit hoặc ưu tiên hỗ trợ PBI gần Done khi chờ review.
- Kiểm tra người ở múi giờ khác có tiếp nhận hợp đồng mới không.
- Xem lại chi phí kế hoạch và cơ hội làm animation/đề xuất khác.
- Cập nhật decision record khi có bằng chứng mới, không “đóng hồ sơ” sau Sprint A.

Đây là **kế hoạch minh họa**. Trong dự án thật, thời lượng, quyền và năng lực cần phù hợp tình trạng sản phẩm; không ai được đảm bảo kết quả chỉ vì thử đúng hai Sprint.

### 22.3. Tạo bằng chứng mà không làm quá nhiều thủ tục

| Quyết định | Bằng chứng sẵn có từ công việc | Phần cần bổ sung nếu thiếu |
|---|---|---|
| Trạng thái UNKNOWN đúng nghĩa | Acceptance examples, API contract, test report | Xác nhận thông điệp UI và tác dụng với người học |
| Phần mềm đạt DoD | CI theo build, integration tests, review phù hợp | Kiểm tra còn điều kiện bắt buộc chưa chạy |
| Giảm hiểu sai giữa vùng | PR/handoff và lỗi hợp đồng | Số vòng hỏi lại, trải nghiệm người nhận |
| Giảm thời gian chờ | Work item age/cycle time theo workflow | Phân biệt loại việc và nguyên nhân blocker |
| Cải thiện outcome | Số lần học tiếp, báo cáo mất tiến độ | Mẫu dữ liệu đủ và giới hạn diễn giải |

Đừng tạo **screenshot bản sao** cho mỗi cuộc họp khi link tới kết quả có nguồn đáng tin đã đủ. Nhưng cũng đừng chỉ nói “CI xanh” nếu không biết đó là **build nào, test nào và phạm vi nào**.

### 22.4. Ví dụ số liệu trước–sau có chú thích

**Tất cả số liệu trong bảng là giả định.** Các Sprint có thể khác loại việc; không được suy kết quả tuyệt đối.

| Tín hiệu | Trước thử nghiệm | Sau Sprint A | Sau Sprint B |
|---|---:|---:|---:|
| PBI feature bắt đầu | 12 | 9 | 9 |
| PBI đạt Definition of Done | 7 | 8 | 8 |
| Lỗi sai contract phát hiện sau ngày giữa Sprint | 4 | 2 | 1 |
| PBI còn mở quá năm ngày | 5 | 3 | 2 |
| Test failure do dữ liệu thử dùng chung | 8 | 4 | 1 |
| Người báo cần làm thêm giờ cuối Sprint | 4 | 3 | 2 |
| Lỗi lưu tiến độ ngoài production | Chưa đủ dữ liệu | Chưa đủ dữ liệu | Chưa đủ dữ liệu |
| Tỷ lệ người học tiếp tục bài | Chưa đủ dữ liệu | Chưa đủ dữ liệu | Chưa đủ dữ liệu |

Nhóm có thể nhận thấy **tín hiệu vận hành/flow tốt hơn**, nhưng vẫn phải nói:

> “Chúng ta có bằng chứng rằng kiểm tra được thực hiện sớm hơn và ít việc chờ kéo dài trong mẫu nhỏ. Chưa có đủ bằng chứng để nói người học đã đạt outcome tốt hơn hoặc chính thử nghiệm là nguyên nhân duy nhất tạo thay đổi.”

### 22.5. Một Sprint có kết quả xấu hơn không tự chứng minh quyết định sai

Giả sử Sprint B có nhiều incident thật hơn:

- Số PBI feature đạt Done có thể giảm vì đội đang bảo vệ người dùng.
- Lỗi production có thể tăng được **ghi nhận** nhờ quan sát tốt hơn, không hẳn hệ thống tệ hơn.
- Work item age có thể tăng do đối tác dừng dịch vụ, nằm ngoài quyền đội.
- Chất lượng không được hạ chỉ để “giữ đồ thị đẹp”.

Đội cần phân loại **điều kiện mới, tác động của lựa chọn và mức kiểm soát được**, tránh quy một kết quả vào một hành động duy nhất.

### 22.6. Quyết định giữ–điều chỉnh–dừng

| Kết quả quan sát | Quyết định có thể xem xét | Giới hạn |
|---|---|---|
| Contract tests đáng tin, lỗi hiểu sai sớm hơn và không tăng tải | **Giữ** kiểm tra và chuẩn hóa cách bàn giao | Tiếp tục xem quality/outcome dài hạn |
| Review chậm do PR vẫn quá lớn dù contract rõ | **Điều chỉnh** kích thước PR, quyền review, pairing | Không bỏ review cần thiết |
| Bộ test quá giòn khiến CI không đáng tin | **Sửa** dữ liệu thử/thiết kế test, không xóa kiểm tra quan trọng để làm đẹp | Xác định test bảo vệ rủi ro nào |
| Một buổi hội thoại dài không giảm hiểu sai | **Dừng/đổi** format, thử pre-read và ví dụ cụ thể | Không cắt trao đổi cần thiết cho quyết định khó |
| Outcome không cải thiện dù trạng thái UI rõ hơn | **Khám phá lại giả thuyết người dùng** | Không suy rằng chỉ cần thêm feature mới |
| Chính sách WIP làm incident thật bị trì hoãn | **Điều chỉnh** policy ưu tiên và escalation | Bảo vệ khẩn cấp theo tác động |

**Thay đổi quyết định sau khi có bằng chứng không phải thất bại về lãnh đạo.** Đó là cách vận hành theo V4/P12 khi được thực hiện minh bạch và có trách nhiệm.

### 22.7. Nếu stakeholder phản đối lùi animation

Một cách đối thoại có ích:

> “Chúng ta hiểu animation có ý nghĩa với bản demo. Dữ liệu mới cho thấy luồng lưu tiến độ có trường hợp thông báo thành công giả; đây là rủi ro trực tiếp với Product Goal. Nhóm đề xuất ưu tiên lát cắt sửa trạng thái và kiểm chứng trước. Phần animation sẽ được Product Owner xem lại theo giá trị và năng lực. Chúng ta sẽ cập nhật bản demo với phạm vi đã đạt DoD và không trình bày phần chưa kiểm chứng như đã hoàn tất.”

Thông điệp **tôn trọng mục tiêu stakeholder** nhưng giữ sự thật chất lượng, quyền Product Owner và tín hiệu người dùng. Đây là ứng dụng đồng thời **V1, V2, V3 và V4**.

## 23. Những ngộ nhận và phản mẫu khi “đối chiếu Agile”

| Ngộ nhận/phản mẫu | Vì sao sai? | Cách phản biện hữu ích |
|---|---|---|
| “Đội dùng Scrum nên chắc chắn Agile.” | Thực hiện sự kiện có thể không đạt mục đích | Xem Increment, feedback, cộng tác và cải tiến |
| “Agile không cần quy trình hay công cụ.” | Vế bên phải vẫn có giá trị | Dùng policy/công cụ hỗ trợ giá trị thay vì mục tiêu tự thân |
| “Agile không cần tài liệu.” | Thiếu contract, test và decision log có thể làm code sai | Tài liệu vừa đủ để phối hợp và kiểm chứng |
| “Agile không cần hợp đồng.” | Có nghĩa vụ không thể tùy ý thay | Cộng tác trong ràng buộc và thương lượng minh bạch |
| “Agile nghĩa là luôn đổi kế hoạch.” | Phản hồi không phân loại tạo WIP và hỗn loạn | Thay đổi khi có tín hiệu, xem mục tiêu và hậu quả |
| “Một stakeholder nói gấp là phải làm ngay.” | Giá trị khác khẩn cấp | Triage tác động và quyền ưu tiên |
| “Giữ Sprint Goal nghĩa là không được sửa phạm vi.” | Goal và phạm vi không giống nhau | Thương lượng scope, giữ DoD và hướng Goal |
| “Scrum Master ra lệnh cho Developers và duyệt mọi PBI.” | Sai accountability Scrum | Product Owner/Developers/SM có trách nhiệm riêng |
| “Working software là code chạy trên laptop.” | Chưa chắc tích hợp, an toàn hoặc đạt DoD | Bằng chứng theo rủi ro và trạng thái Increment |
| “Demo nhiều slide là đủ cho Sprint Review.” | Không kiểm tra Increment và bối cảnh | Hợp tác với stakeholders và cập nhật backlog |
| “Retro có nhiều action là cải tiến tốt.” | Action không được làm/đo thì vô nghĩa | Chọn ít thay đổi, ghi guardrail và mốc xem lại |
| “Mọi người phải tham gia mọi cuộc họp để tuân P6.” | Gây lãng phí, bất công múi giờ | Sync khi cần, async có ngữ cảnh và quyết định |
| “Tin tưởng đội nghĩa là bỏ review.” | Tin tưởng không bỏ trách nhiệm chất lượng | Tự quản có minh bạch và tiêu chí Done |
| “Velocity tăng chứng minh khách hàng hạnh phúc hơn.” | Velocity không đo outcome | Phân biệt output, Increment và outcome |
| “P3 đòi phát hành ngày nào cũng được dù chưa test.” | Giao thường xuyên phải là phần mềm hoạt động đáng tin | Nhỏ hóa batch và CI, giữ DoD |
| “Sự cố xuất hiện chỉ do Developers không cẩn thận.” | Bỏ qua quy trình, thiết kế, môi trường, phụ thuộc | Timeline, phân tích điều kiện và cải tiến hệ thống |
| “Bỏ test giúp đơn giản theo P10.” | Bỏ bảo vệ cần thiết không phải bỏ việc thừa | Đơn giản hóa scope/thiết kế, giữ quality gates |
| “Tất cả unit tests xanh nghĩa là hết rủi ro.” | Unit test có giới hạn và có thể không đại diện production | Integration/security/operational checks theo rủi ro |
| “XP là kỹ thuật, không liên quan giá trị người dùng.” | Tính linh hoạt kỹ thuật hỗ trợ phản hồi và outcome | Nêu cơ chế giảm lỗi/lead time và kiểm chứng |
| “Kanban chỉ cần cột To Do/Doing/Done.” | Thiếu workflow policies, WIP và số đo | Định nghĩa luồng và cải tiến bằng bằng chứng |
| “Nhiều ticket Done hơn là tốt hơn.” | Có thể tách giả ticket hoặc báo Done sớm | Kết hợp flow, DoD, outcome |
| “Tự tổ chức nghĩa là ai muốn làm gì cũng được.” | Bỏ mục tiêu chung và thẩm quyền | Tự quản trong trách nhiệm và ràng buộc |
| “Phải đồng ý mọi ý kiến để giữ cộng tác.” | Bất đồng có căn cứ giúp học | Làm rõ dữ liệu, đánh đổi và người quyết định |
| “Chấm điểm 10/12 nguyên tắc là đạt Agile.” | Nguyên tắc không có trọng số/bài kiểm tra chính thức | Phân tích liên hệ thực, không cộng điểm |
| “Một quyết định khác roadmap chứng tỏ thiếu kỷ luật.” | Thay đổi có thể phản ánh thông tin mới quan trọng | Xem ràng buộc, giả định và bằng chứng |
| “Một quyết định đúng không cần xem lại.” | Điều kiện và dữ liệu có thể đổi | Đặt trigger và điểm kiểm tra lại |
| “Không đo đủ outcome thì không được giao gì.” | Có thể thử lát cắt nhỏ đủ chất lượng để học | Nêu giới hạn, bắt đầu từ bằng chứng khả thi |
| “Càng nhiều documents/tests luôn càng Agile.” | Số lượng không tương đương chất lượng | Tập trung giá trị, mức bao phủ rủi ro và giảm rework |
| “Luật và kiểm soát có thể bỏ vì Agile ưu tiên khách hàng.” | Cộng tác không miễn nghĩa vụ | Xác minh thẩm quyền và phương án hợp lệ |
| “Team đang bận là tiến độ tốt.” | WIP cao có thể tăng chờ, ít việc Done | Nhìn flow, DoD và outcome |
| “Không còn overtime nghĩa là hệ thống chắc chắn tốt.” | Có thể còn chất lượng kém hoặc mục tiêu không rõ | Xem toàn bộ giá trị, chất lượng, bền vững |
| “Nếu kết quả xấu, người chọn phương án sai phải chịu lỗi.” | Không xem bất định và thông tin lúc quyết định | Học từ giả thuyết, trách nhiệm và điều kiện hệ thống |

**Cách dùng bảng:** chọn phản mẫu đang xảy ra thật, nêu một **sự kiện cụ thể và một hành động thay đổi**. Không dùng bảng để chỉ trích đồng nghiệp bằng nhãn “không Agile”.

## 24. Checklist tự đánh giá quyết định của nhóm

Checklist này phục vụ **thảo luận và ra quyết định**, không phải chứng chỉ Agile, không đòi mọi quyết định đi qua toàn bộ câu hỏi.

### 24.1. Mục tiêu, dữ liệu và quyền quyết định

1. **Quyết định cụ thể:** chúng ta đang đánh giá một lựa chọn thật hay chỉ tranh luận về “văn hóa Agile”?
2. **Thời điểm:** có biết thông tin sẵn có khi quyết định được đưa ra không?
3. **Product Goal:** lựa chọn phục vụ kết quả người dùng/tổ chức nào?
4. **Sprint Goal hoặc mục tiêu dịch vụ:** tác động ngắn hạn là gì?
5. **Sự kiện và nguồn:** có thể đối chiếu qua phản hồi, test, PBI, incident hay dữ liệu sử dụng?
6. **Giả định chưa kiểm chứng:** đã ghi rõ điều gì chỉ là suy đoán?
7. **Các bên chịu ảnh hưởng:** người dùng, Developers, vận hành, đối tác, stakeholder nào cần được nghe?
8. **Thẩm quyền:** ai có accountability quyết định backlog, kỹ thuật, kiểm soát hoặc release?
9. **Ràng buộc:** có nghĩa vụ pháp lý/hợp đồng/chất lượng đã xác nhận không?
10. **Phương án:** có ít nhất một cách khác khả thi và hợp lệ để so sánh không?

### 24.2. Bốn giá trị

11. **V1:** tương tác hiện tại giúp những người cần phối hợp cùng hiểu và hành động không?
12. **V1:** quy trình/công cụ có đang ngăn phản hồi hoặc làm tăng chờ không cần thiết?
13. **V2:** có Increment hoạt động và bằng chứng DoD, không chỉ tài liệu/báo cáo?
14. **V2:** tài liệu/contract nào thật sự cần để duy trì chất lượng và khả năng bàn giao?
15. **V3:** khách hàng/người dùng hoặc đại diện có thông tin thực tham gia quyết định đúng lúc?
16. **V3:** phạm vi hợp đồng, an toàn, quyền dữ liệu có được tôn trọng?
17. **V4:** thông tin mới có thể làm nhóm thay đổi ưu tiên/phạm vi có kiểm soát?
18. **V4:** có phân biệt feedback thật với thay đổi ngẫu hứng không?

### 24.3. Mười hai nguyên tắc

19. **P1:** phần giá trị nào người dùng nhận sớm và liên tục?
20. **P2:** yêu cầu thay đổi được đón nhận và đánh giá theo bằng chứng?
21. **P3:** có vòng giao phần mềm đủ chất lượng ở nhịp có thể học sớm?
22. **P4:** người hiểu nghiệp vụ và Developers cộng tác thường xuyên khi cần?
23. **P5:** đội có động lực, môi trường và sự tin tưởng để tự thực hiện?
24. **P6:** hình thức giao tiếp có đủ phong phú mà không loại người khác múi giờ?
25. **P7:** tiến độ dựa trên khả năng phần mềm thật sự hoạt động và đạt DoD?
26. **P8:** cách làm bền vững với đội, stakeholders và người dùng?
27. **P9:** thiết kế/test/CI bảo vệ khả năng thay đổi an toàn?
28. **P10:** có phạm vi chưa cần làm để kiểm chứng giá trị?
29. **P11:** người gần vấn đề có quyền chủ động phù hợp trách nhiệm?
30. **P12:** đã có hành động cải tiến thực sự được thử và xem lại?

### 24.4. Đánh đổi, bằng chứng và cách xem lại

31. **Tension:** những giá trị/nguyên tắc nào có vẻ căng thẳng? Có lý do và guardrails không?
32. **Không cherry-pick:** đã quét toàn bộ P1–P12 thay vì chỉ chọn nguyên tắc thuận cho đề xuất?
33. **Chất lượng:** lựa chọn có bỏ DoD, test hoặc kiểm soát bắt buộc không?
34. **Handoff:** người ở nhóm/múi giờ khác có đủ bối cảnh để tiếp tục?
35. **Năng lực:** có tính tới việc khẩn, review, kiểm thử và thời gian tập trung?
36. **Dòng công việc:** WIP, work item age, cycle time hay blocker nào sẽ thay đổi?
37. **Giá trị:** có tín hiệu outcome bên cạnh output không?
38. **Bền vững:** overtime, on-call, sự an toàn khi nêu rủi ro được xem xét chưa?
39. **Bằng chứng:** có cách kiểm chứng, nguồn, phạm vi và giới hạn rõ?
40. **Mốc xem lại:** khi nào sẽ kiểm tra giả thuyết?
41. **Điều kiện đổi ý:** có biết tín hiệu nào sẽ khiến giữ, sửa hoặc dừng?
42. **Trách nhiệm truyền thông:** ai thông báo quyết định, đánh đổi và giới hạn tới người liên quan?

### 24.5. Kết quả tối thiểu của một phiên đối chiếu

Một phiên thảo luận ngắn có thể kết thúc bằng **năm câu trả lời**:

1. **Vấn đề:** quyết định cụ thể nào cần sửa hoặc kiểm chứng?
2. **Căn cứ:** sự kiện nào đã được xác minh, điều gì còn giả định?
3. **Giá trị/nguyên tắc:** lựa chọn phục vụ và gây căng thẳng ở đâu?
4. **Hành động:** thay đổi nhỏ nào có người chịu trách nhiệm, đúng quyền và đúng DoD?
5. **Đánh giá lại:** khi nào và dựa vào những tín hiệu/guardrails nào?

Nếu sau một buổi dài nhóm chỉ kết luận **“cần Agile hơn”**, chưa có quyết định vận hành đủ cụ thể.

## 25. Bài tập thực hành tổng hợp

### Bài tập 1 — Đọc đúng bốn giá trị

Với mỗi phát biểu, xác định **phù hợp, diễn giải sai hoặc cần thêm bối cảnh**, và giải thích bằng hai vế của giá trị:

1. “Cộng tác quan trọng nên mọi quyết định kỹ thuật phải gọi cả đội họp.”
2. “Phần mềm hoạt động quan trọng hơn tài liệu nên không cần API contract.”
3. “Khách hàng quan trọng nên có thể bỏ một điều khoản bảo mật mà họ chưa nhắc.”
4. “Thay đổi được chào đón nên stakeholder nào muốn việc gấp cũng đưa vào Sprint.”
5. “Chúng ta nên rút tài liệu dài thành AC và link test để phát hiện sai nhanh hơn.”
6. “Khi có phản hồi đáng tin, Product Owner cần xem lại thứ tự backlog dù roadmap đã được công bố.”

**Yêu cầu thêm:** chọn hai phát biểu sai và viết lại thành **quy tắc có thể áp dụng**. Ví dụ quy tắc phải nêu **khi nào hội thoại trực tiếp, khi nào ghi nguồn quyết định và điều không được đánh đổi**.

### Bài tập 2 — Nối tình huống với mười hai nguyên tắc

Ghép mỗi tình huống với **hai hoặc ba nguyên tắc liên quan nhất** rồi giải thích:

| Tình huống | P cần chọn |
|---|---|
| A. Cuối Sprint mới thấy UI và API dùng hai hợp đồng khác nhau | ? |
| B. Team bắt đầu 18 PBI nhưng hiếm có Increment Done | ? |
| C. Người học phản hồi vấn đề đã thay đổi nhưng roadmap vẫn bất biến | ? |
| D. Một thành viên phải thức khuya review mỗi ngày vì múi giờ | ? |
| E. Đội tranh luận phải xây 12 tính năng trước khi có một thử nghiệm người dùng | ? |
| F. Retrospective nào cũng ghi “giao tiếp tốt hơn” nhưng không thay hành động | ? |

**Gợi ý:** có thể có nhiều câu trả lời hợp lý nếu trình bày mối quan hệ với sự kiện; không cố ép mỗi tình huống vào đúng một mã P.

### Bài tập 3 — Phân biệt sự kiện, giả định và kết luận

Nhóm nói:

> “Người dùng không thích sản phẩm vì Developers không làm đủ story points. Sprint trước có 12 PBI mở, 7 PBI đạt Done, và hai report lỗi mất tiến độ.”

**Yêu cầu:**

1. Tách câu trên thành **sự kiện có nguồn cần xác minh, diễn giải và giả định**.
2. Xác định dữ liệu nào còn thiếu để kết luận về **mức hài lòng người dùng**.
3. Giải thích vì sao số PBI/story points không đo trực tiếp outcome.
4. Đề xuất một cách kiểm tra vấn đề mất tiến độ không vi phạm quyền riêng tư.
5. Chỉ ra ít nhất ba nguyên tắc Agile nên xem khi quyết định việc tiếp theo.

### Bài tập 4 — Đối chiếu quyết định bỏ kiểm thử

Một quản lý muốn bỏ integration tests và review bảo mật để kịp demo. Test quyền truy cập dữ liệu người học chưa chạy; frontend có thể báo “Đã lưu” khi API timeout.

**Yêu cầu:**

- Chọn bốn giá trị liên quan và nêu cách quyết định ảnh hưởng từng giá trị.
- Đánh giá P1, P3, P7, P8, P9, P10 và ít nhất hai nguyên tắc khác.
- Nêu **điều kiện bắt buộc** ngăn phương án giả.
- Đề xuất hai phương án **hợp lệ** đáp ứng nhu cầu demo/feedback với phạm vi phù hợp.
- Ghi một câu truyền thông cho stakeholder về phần Done và phần chưa kiểm chứng.

**Gợi ý:** không “cho PASS” một test NOT RUN; có thể **giảm phạm vi demo, làm rõ hạn chế** nhưng không giới thiệu phần chưa đạt DoD như Increment hoàn thành.

### Bài tập 5 — Từ user story thành lát cắt kiểm chứng được

User story:

> “Là người học, tôi muốn tiếp tục bài học để không phải học lại từ đầu.”

**Yêu cầu:**

1. Viết ba acceptance examples, gồm trường hợp kết quả lưu chưa xác định.
2. Chia thành tối đa bốn lát cắt dọc có thể tạo Increment.
3. Chỉ ra test nào có thể làm ở unit/component, contract, integration hoặc E2E.
4. Nêu ràng buộc về quyền truy cập không được bỏ.
5. Gắn các lựa chọn với P1/P3/P4/P7/P9/P10.
6. Nêu cách lấy phản hồi người học sau lát cắt đầu.

### Bài tập 6 — Sprint Goal bị đe dọa và thay đổi đến muộn

Ngày thứ sáu của Sprint, production xảy ra lỗi mất tiến độ thực. Cùng lúc một stakeholder muốn đổi màu toàn bộ giao diện. Sprint Goal đang nhắm tới lưu/tiếp tục bài đáng tin.

**Yêu cầu:**

1. Phân loại điều gì là **incident**, điều gì là **yêu cầu backlog thường lệ**.
2. Nêu trách nhiệm Product Owner, Developers, Scrum Master và kênh ứng cứu.
3. Giải thích P2/V4 không cho phép thay Sprint Goal tùy tiện.
4. Nêu cách điều chỉnh phạm vi **không hạ DoD**.
5. Đề xuất một cải tiến P12 để giảm incident tái diễn.
6. Giải thích ai có quyền hủy Sprint nếu Sprint Goal trở nên lỗi thời.

### Bài tập 7 — Scrum Events: làm đúng hình thức hay đúng mục đích?

Nhóm có các dấu hiệu:

- Daily Scrum 45 phút mỗi ngày để quản lý hỏi từng người làm gì.
- Sprint Review là buổi chiếu slide, không có Increment đạt DoD.
- Retrospective có danh sách 20 action, không action nào được xem lại.
- Sprint Planning gắn số story points cố định theo velocity cũ.

**Yêu cầu:** với mỗi dấu hiệu, nêu:

~~~text
Mục đích của hoạt động:
Giá trị và nguyên tắc Agile liên quan:
Sự kiện/bằng chứng cần kiểm tra:
Điều chỉnh cụ thể:
Tín hiệu xác nhận điều chỉnh có tác dụng:
~~~

**Gợi ý:** không nhất thiết phải thêm một cuộc họp mới; có thể **giảm thủ tục và tăng chất lượng hội thoại/Increment**.

### Bài tập 8 — Kanban, WIP và giá trị người dùng

Một nhóm có 15 PBI đang mở, năm PBI chờ review, throughput tuần tăng vì đóng nhiều ticket support nhỏ. Người học vẫn báo mất tiến độ.

**Yêu cầu:**

1. Định nghĩa WIP, work item age, throughput và cycle time.
2. Giải thích vì sao throughput tăng **chưa chứng minh P1**.
3. Đề xuất một thử nghiệm WIP limit và chính sách hỗ trợ việc gần Done.
4. Nêu trường hợp incident thật cần được xử lý theo chính sách ưu tiên riêng.
5. Chọn ba tín hiệu flow/chất lượng/outcome để kiểm tra sau thử nghiệm.
6. Đối chiếu với P7/P8/P9/P10/P12.

### Bài tập 9 — XP, refactoring và đánh đổi thời gian

Đội muốn xây thêm năm tính năng. Tuy nhiên CI flaky làm mọi PR phải chạy lại nhiều lần; một module lưu tiến độ chỉ một Developer hiểu.

**Yêu cầu:**

- So sánh ít nhất ba phương án: tiếp tục feature, sửa CI/test, rewrite module toàn bộ.
- Đối chiếu với V2/V4 và P3/P5/P7/P8/P9/P10/P11.
- Chọn một thay đổi kỹ thuật nhỏ **có thể kiểm chứng sớm**.
- Nêu vì sao bỏ test hoặc rewrite toàn bộ theo cảm tính đều có rủi ro.
- Viết thẻ thử nghiệm có guardrail và mốc xem lại.

### Bài tập 10 — Khác múi giờ và giao tiếp trực tiếp

Product Owner ở Việt Nam, backend ở châu Âu và frontend ở Bắc Mỹ. Các cuộc gọi đồng bộ thường diễn ra ngoài giờ của một nhóm; quyết định API nằm trong chat/ghi hình.

**Yêu cầu:**

1. Giải thích P6 theo mục đích **hiểu biết chung** chứ không chỉ hình thức họp.
2. Thiết kế chính sách sync/async có agenda và quyết định sau họp.
3. Viết một handoff có trạng thái thật, AC, contract, test, blocker và bước tiếp.
4. Nêu cách bảo vệ P8 và khả năng tiếp cận.
5. Đề xuất hai chỉ báo giảm vòng hỏi lại mà **không đo thời gian online cá nhân**.

### Bài tập 11 — Lập ma trận đánh giá quyết định

Ba phương án cho một nhóm phát triển:

- **A:** giữ roadmap cũ vì đã cam kết nội bộ.
- **B:** ưu tiên sửa lỗi lưu tiến độ và contract tests trong hai Sprint.
- **C:** tạm dừng tất cả feature sáu tháng để rewrite toàn bộ backend.

**Yêu cầu:**

1. Lập bảng theo **bốn giá trị**.
2. Quét đủ **P1–P12**, chọn nguyên tắc liên quan trực tiếp và nhận diện căng thẳng.
3. Nêu ràng buộc bắt buộc và nguồn cần xác minh.
4. Chọn phương án **thử trước**, có thể kết hợp/thay đổi nếu hợp lệ.
5. Ghi ba giả định chưa rõ, hai tín hiệu outcome và hai guardrails.
6. Giải thích vì sao **không cộng điểm 12 nguyên tắc** để chọn.

### Bài tập 12 — Đối chiếu một quyết định thật của đội bạn

Chọn một quyết định gần đây về backlog, cách cộng tác, chất lượng, release, workflow hoặc xử lý incident **mà bạn được phép chia sẻ**. Nếu không có dữ liệu thật, dùng case giả định.

Điền mẫu:

~~~text
Tên quyết định và thời điểm:
Product Goal / mục tiêu dịch vụ:
Sự kiện đã xác minh và nguồn:
Điều mới xuất hiện sau quyết định:
Giả định chưa được kiểm tra:
Người dùng/đội/stakeholder chịu ảnh hưởng:
Ràng buộc bắt buộc và quyền quyết định:
Các phương án có thể lựa chọn:
V1 — hỗ trợ / căng thẳng / chưa rõ:
V2 — hỗ trợ / căng thẳng / chưa rõ:
V3 — hỗ trợ / căng thẳng / chưa rõ:
V4 — hỗ trợ / căng thẳng / chưa rõ:
P1–P12 — những nguyên tắc liên quan trực tiếp:
P1–P12 — rủi ro mâu thuẫn cần bảo vệ:
Lựa chọn/thử nghiệm nhỏ muốn thực hiện:
Vai trò phối hợp và người có accountability:
Thay đổi backlog/workflow/test/DoD:
Bằng chứng và giới hạn dữ liệu:
Outcome và flow metrics:
Guardrails về chất lượng, quyền, bền vững:
Thời gian và điều kiện xem lại:
Giữ, sửa hoặc dừng theo kết quả nào:
~~~

**Tự đánh giá:** người khác có thể đọc bản này và hiểu **vì sao quyết định hợp lý trong bối cảnh, nó hỗ trợ hoặc gây căng thẳng giá trị/nguyên tắc nào, những điều gì chưa biết và khi nào sẽ đổi ý** không?

## 26. Tổng kết

**Đối chiếu quyết định với bốn giá trị và mười hai nguyên tắc Agile** là cách kiểm tra xem đội đang ưu tiên đúng điều quan trọng trong hoàn cảnh thật, thay vì chỉ “làm đủ nghi thức”:

1. **Bốn giá trị là ưu tiên tương đối:** đặt con người, phần mềm hoạt động, cộng tác với khách hàng và phản hồi với thay đổi lên trước, nhưng **quy trình/công cụ, tài liệu, hợp đồng và kế hoạch vẫn có giá trị**.
2. **P1–P3** hướng vào **giá trị sớm, tiếp nhận thay đổi và giao phần mềm thường xuyên**, không phải phát hành phần mềm chưa đạt chất lượng.
3. **P4–P6** nhấn mạnh **nghiệp vụ–kỹ thuật cộng tác, tin tưởng người có động lực và trao đổi hiệu quả**, không đồng nghĩa họp mọi lúc hoặc xóa quyền quyết định.
4. **P7–P9** nhắc rằng **phần mềm hoạt động là bằng chứng tiến độ quan trọng, nhịp làm phải bền vững và chất lượng kỹ thuật làm tăng khả năng thích ứng**.
5. **P10–P12** yêu cầu **đơn giản hóa phần việc không cần làm, tạo điều kiện đội tự tổ chức và thường xuyên kiểm tra–điều chỉnh cách làm**, không phải bỏ kiểm soát hoặc đổi quy trình vì hình thức.
6. **Bắt đầu từ một quyết định cụ thể:** ghi thời điểm, sự kiện, giả định, mục tiêu, các phương án, chi phí cơ hội, ràng buộc và người có quyền.
7. **Đối chiếu không phải chấm điểm:** xem bốn giá trị, quét mười hai nguyên tắc để tìm **cơ chế hỗ trợ, sự căng thẳng và khoảng trống bằng chứng**; một vi phạm rủi ro nghiêm trọng không thể được “bù” bằng nhiều ô xanh.
8. **Lựa chọn phải hợp lệ trước khi tối ưu:** không viện Agile để bỏ Definition of Done, dữ liệu người dùng, bảo mật, quyền riêng tư hoặc nghĩa vụ hợp đồng đã xác nhận.
9. **Scrum, Kanban và XP phục vụ những câu hỏi khác nhau:** Scrum tạo nhịp thực nghiệm quanh Product Goal/Sprint Goal/Increment; Kanban giúp điều hành flow và WIP; XP hỗ trợ thay đổi kỹ thuật an toàn. Chọn và kết hợp chúng dựa trên **bằng chứng nhu cầu, loại việc và khả năng bàn giao**.
10. **Đo nhiều chiều:** outcome người dùng, Increment/DoD, work item age, cycle time, throughput, chất lượng, tình trạng phụ thuộc và nhịp bền vững **không thể thay nhau bằng một KPI duy nhất**.
11. **Cải tiến cần có hành động thật:** thử một thay đổi đủ nhỏ, có người phối hợp, tín hiệu, guardrail và mốc xem lại; **giữ, sửa hoặc dừng** khi hiểu biết thay đổi.
12. **Minh bạch giới hạn của dữ liệu:** một mẫu trước–sau nhỏ, một dashboard đẹp hoặc một bản demo không tự chứng minh quan hệ nhân quả hay khách hàng hài lòng.

### Bảng ghi nhớ nhanh khi ra quyết định

| Câu hỏi | Giá trị/nguyên tắc thường liên quan | Hành động tiếp theo |
|---|---|---|
| Người dùng thật sự cần gì? | V3, P1, P4 | Xác minh nhu cầu, Product Goal và phản hồi |
| Có giá trị/Increment dùng được chưa? | V2, P3, P7 | Chia lát cắt, kiểm tra và giữ DoD |
| Tại sao quyết định bị hiểu sai? | V1, P4, P6, P11 | Đối thoại đúng người và ghi nguồn quyết định |
| Thông tin mới có thay đổi kế hoạch không? | V4, P2, P10 | Triage, so phương án, điều chỉnh phạm vi hợp lệ |
| Vì sao code khó đổi và lỗi lặp? | P7, P9, P12 | CI, test, refactoring và kiểm tra tác dụng |
| Vì sao đội kiệt sức dù throughput tăng? | P5, P8, P10 | Giảm WIP, xem năng lực và nguyên nhân gián đoạn |
| Có đang làm nhiều việc chưa cần? | P1, P10 | Thử một lát cắt tối thiểu nhưng đủ chất lượng |
| Quy trình mới có tạo giá trị không? | P11, P12 và bốn giá trị | Decision record, tín hiệu, guardrail, review |

> **Câu hỏi ghi nhớ quan trọng nhất:** “Nếu phải giải thích một quyết định Agile cho người dùng, Developers và stakeholders, chúng ta có chỉ ra được **giá trị nào được phục vụ, nguyên tắc nào đang hỗ trợ hoặc bị căng thẳng, bằng chứng nào đủ tin, điều gì không được đánh đổi và khi nào sẽ thay đổi quyết định** hay không?”

### Tài liệu tham khảo

- [Manifesto for Agile Software Development](https://agilemanifesto.org/) — nguồn gốc **bốn giá trị Agile**; nên đọc cả hai vế của từng giá trị.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html) — **mười hai nguyên tắc** chính thức; bài học đã diễn giải bằng lời riêng và giữ thứ tự P1–P12 để đối chiếu.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — Scrum accountabilities, events, artifacts, Product Goal, Sprint Goal, Increment và Definition of Done; tham khảo khi áp dụng nguyên tắc trong Scrum.
- [The Kanban Guide](https://kanbanguides.org/) — Definition of Workflow, WIP, throughput, cycle time, work item age và Service Level Expectation trong quản lý dòng công việc.
- [Scrum.org — Kanban Guide for Scrum Teams](https://www.scrum.org/resources/kanban-guide-scrum-teams) — cách thực hành Kanban có thể bổ trợ Scrum.
- [Agile Alliance — Extreme Programming](https://agilealliance.org/glossary/xp/) — tổng quan XP và các thực hành kỹ thuật như TDD, pairing, CI, refactoring.
- [Martin Fowler — Continuous Integration](https://martinfowler.com/articles/continuousIntegration.html) — tích hợp thường xuyên và phản hồi kỹ thuật sớm.
- [Martin Fowler — Feature Toggles](https://martinfowler.com/articles/feature-toggles.html) — phân biệt tích hợp và mở tính năng, đánh đổi cần kiểm soát khi dùng feature flags.
- [DORA](https://dora.dev/) — tài liệu nghiên cứu và góc nhìn về hiệu quả giao phần mềm; cần diễn giải chỉ số theo bối cảnh, không xếp hạng cá nhân máy móc.
