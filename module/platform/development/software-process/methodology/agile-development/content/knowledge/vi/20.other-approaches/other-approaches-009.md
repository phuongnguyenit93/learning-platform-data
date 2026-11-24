# Phân biệt kết hợp có chủ đích với việc tùy ý bỏ những cơ chế cần thiết

Một nhóm phát triển nền tảng học trực tuyến tuyên bố đang áp dụng **“Scrum kết hợp Kanban, XP và quy trình nội bộ”**. Họ bỏ Sprint Goal vì muốn nhận yêu cầu linh hoạt, không giới hạn công việc đang thực hiện vì sợ nhân sự rảnh, chỉ họp Sprint Review khi lãnh đạo có thời gian và chuyển kiểm thử hồi quy sang cuối quý để ra tính năng nhanh hơn. Nhóm vẫn có bảng Kanban, vài cuộc họp Scrum và công cụ quản lý user story. Tuy nhiên, các hạng mục chờ kiểm thử liên tục tăng, lỗi xuất hiện muộn, Product Owner không quyết định được ưu tiên, còn người dùng phải chờ hàng tháng mới nhận được khả năng hoạt động đáng tin.

Một nhóm khác cũng dùng nhiều thực hành, nhưng có cách làm rõ ràng hơn: giữ **Product Goal, Sprint Goal, Increment và Definition of Done** của Scrum; giới hạn **Work in Progress (WIP)** và đo thời gian dòng công việc theo Kanban; dùng kiểm thử tự động, tích hợp liên tục và refactoring từ XP; đồng thời phối hợp kiểm soát bảo mật bắt buộc vào quá trình phát triển. Mỗi điều chỉnh đều có lý do, chính sách, người chịu trách nhiệm và thời điểm kiểm tra hiệu quả. Khi thấy một bước kiểm chứng bị tắc, nhóm không “giải quyết” bằng cách đổi tên cột mà thay cách phân phối công sức, xử lý phụ thuộc và quan sát kết quả.

Hai nhóm đều nói mình **kết hợp phương pháp Agile**. Nhưng chỉ nhóm thứ hai cho thấy **kết hợp có chủ đích**: biết vấn đề cần giải quyết, hiểu cơ chế nào bảo vệ giá trị của từng cách làm, bổ sung thực hành phù hợp và đánh giá bằng bằng chứng. Nhóm thứ nhất đang **tùy ý loại bỏ các cơ chế khó**, tạo ra một quy trình mang nhãn Agile nhưng mất khả năng kiểm tra, thích ứng và giao sản phẩm chất lượng.

Bài học này thuộc chương **Các cách tiếp cận khác** của module **AGILE_DEVELOPMENT**. Nội dung giúp liên kết các giá trị, nguyên tắc Agile với user story, backlog, Scrum, Kanban, XP, đo lường dòng công việc và phối hợp tổ chức. Trọng tâm không phải tuyên bố phương pháp nào luôn tốt nhất, mà là **phân biệt thích nghi đúng bối cảnh với việc cắt bỏ những điều kiện cần để phương pháp tạo ra tác dụng**.

> **Thông điệp chính:** Có thể thay đổi cách tổ chức, thời lượng, công cụ và kỹ thuật để phù hợp bối cảnh. Nhưng nếu bỏ một cơ chế giúp minh bạch, kiểm tra, phản hồi, bảo vệ chất lượng hoặc kiểm soát dòng công việc, đội cần biết **chức năng nào sẽ thay thế**, ai vận hành và bằng chứng nào chứng minh sự thay đổi là có ích.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích sự khác biệt giữa **kết hợp có chủ đích (deliberate combination)**, **điều chỉnh theo bối cảnh (tailoring)** và **lựa chọn tùy tiện/cherry-picking** các nghi thức Agile.
2. Phân biệt **thành phần cốt lõi của một khung cụ thể** với những kỹ thuật tùy chọn có thể kết hợp, chẳng hạn Scrum events và commitments, Definition of Workflow của Kanban, các thực hành kỹ thuật XP.
3. Xác định những **cơ chế nền tảng** cần được bảo toàn: mục tiêu/giá trị, quyền quyết định, minh bạch, vòng phản hồi, chất lượng tích hợp, kiểm soát WIP/phụ thuộc và cải tiến theo dữ liệu.
4. Đánh giá việc kết hợp Scrum, Kanban, XP, Lean, DevOps, product discovery hoặc ràng buộc tổ chức mà không nhầm chúng thành một bộ quy định duy nhất.
5. Nhận diện các phản mẫu: gọi ticket Done dù không đạt chất lượng, bỏ Review nhưng vẫn tự nhận có phản hồi, không giới hạn WIP nhưng tuyên bố dùng Kanban, hoặc để stakeholder liên tục chen việc mà không quyết định đánh đổi.
6. Thiết kế một phương án kết hợp rõ **vấn đề → thực hành → cơ chế → giới hạn → phép đo → mốc xem lại**.
7. Dùng một tình huống xuyên suốt, bảng quyết định và bài tập để lựa chọn cách phối hợp phù hợp với nhóm sản phẩm thực tế.

## 1. Từ “chọn cách làm linh hoạt” đến “chọn cơ chế có trách nhiệm”

Agile không bắt buộc mọi đội tổ chức công việc giống nhau. Nhóm xây ứng dụng có thể làm việc khác nhóm vận hành dịch vụ, khác nhóm xây hệ thống có yêu cầu an toàn cao hoặc nhóm tích hợp phần cứng. Sự khác biệt về nhu cầu người dùng, loại công việc, thời gian phản hồi và ràng buộc tổ chức khiến một quy trình duy nhất khó phù hợp với tất cả.

Tuy nhiên, từ **“linh hoạt”** không có nghĩa **“muốn bỏ gì cũng được”**. Cần tách ba khái niệm:

| Khái niệm | Mô tả | Dấu hiệu nhận biết |
|---|---|---|
| **Kết hợp có chủ đích** | Chọn các thực hành từ nhiều cách tiếp cận để giải quyết một vấn đề được quan sát; xác định chức năng của từng phần và cách chúng tương tác | Có lý do, chính sách, người phụ trách, dữ liệu và vòng xem lại |
| **Điều chỉnh có căn cứ** | Thay đổi hình thức hoặc mức độ thực hành để phù hợp bối cảnh, nhưng vẫn giữ cơ chế quan trọng hoặc nói rõ phương án thay thế | Ví dụ Daily Scrum vẫn 15 phút, nhóm đổi cách thảo luận từ báo cáo từng người sang nhìn tiến triển tới Sprint Goal và điểm nghẽn |
| **Tùy ý cắt bỏ cơ chế** | Bỏ thành phần vì khó, bất tiện hoặc tạo ra thông tin không mong muốn, mà không hiểu hệ quả hay chức năng thay thế | Ví dụ bỏ Definition of Done để chuyển ticket Done sớm, rồi gọi đó là “Scrum tinh gọn” |

Một thay đổi không tự tốt hoặc xấu vì tên gọi. Một đội có thể không sử dụng Scrum, chọn Kanban thuần hoặc một cách tổ chức khác mà vẫn Agile. Vấn đề xuất hiện khi **nhãn phương pháp và cơ chế vận hành không còn khớp** hoặc khi một chức năng cần thiết đã bị loại bỏ mà không ai chịu trách nhiệm.

### 1.1. “Vì sao chúng ta thay đổi?” là câu hỏi đầu tiên

Ví dụ, nhóm muốn bỏ Sprint Planning:

- **Lý do chưa đủ:** “Họp phiền quá; cứ kéo ticket đi làm.”
- **Câu hỏi cần kiểm tra:** “Công việc của nhóm là luồng yêu cầu liên tục, thường xuất hiện bất ngờ; một Sprint Goal cố định đang không giúp ích, hay chúng ta đang tổ chức Sprint Planning kém?”
- **Lựa chọn có chủ đích:** Nếu tiếp tục dùng Scrum, cải thiện Sprint Planning và giữ Sprint Goal. Nếu chuyển sang hệ thống Kanban, xác định rõ cách bổ sung việc, thứ tự ưu tiên, kiểm soát WIP, SLE, phản hồi và trách nhiệm quyết định. Không gọi một luồng không có Sprint là “Scrum nguyên vẹn”.

Để thay đổi hợp lý, cần trả lời ít nhất bốn câu:

1. **Vấn đề thực tế nào** đang cản trở giá trị hoặc năng lực hoàn tất?
2. Thực hành định bỏ/đổi đang phục vụ **cơ chế nào**?
3. Nếu bỏ, **cơ chế đó còn được bảo vệ bằng cách nào**, hoặc vì sao nó không còn cần trong bối cảnh này?
4. **Làm sao biết thay đổi tạo kết quả tốt hơn**, không chỉ bớt cuộc họp hay đẹp dashboard?

### 1.2. Hai sai lầm đối lập

**Sao chép máy móc:** nhóm áp dụng nguyên xi lịch họp, số cột và tên vai trò từ một đội khác mà không xem loại công việc, mục tiêu, quyền quyết định và hệ thống kỹ thuật. Điều này có thể tạo chi phí lớn mà ít giá trị.

**Cắt bỏ tùy tiện:** nhóm gọi mọi điều khó là “quy trình thừa”, loại bỏ tiêu chuẩn chất lượng, bỏ kiểm tra kết quả, che điểm nghẽn hoặc không làm rõ ai quyết định. Điều này có thể tạo tốc độ bề mặt nhưng tăng việc làm lại.

**Cách tiếp cận phù hợp:** hiểu nguyên lý và cơ chế, áp dụng tối thiểu cần thiết để tạo bằng chứng, rồi cải tiến theo thực tế.

## 2. Điều không thể thiếu là chức năng, nhưng mỗi khung có quy tắc riêng

Có hai mức cần phân biệt:

1. **Mức tên khung:** nếu tuyên bố thực hành một khung như Scrum, cần tôn trọng các thành phần được định nghĩa chính thức của khung đó. Không tự loại bỏ phần cốt lõi rồi tuyên bố vẫn đang áp dụng đúng toàn bộ Scrum.
2. **Mức hiệu quả hệ thống:** khi dùng một cách tiếp cận khác hoặc kết hợp nhiều thực hành, tổ chức vẫn cần cơ chế xử lý mục tiêu, quyết định, chất lượng, phản hồi và dòng công việc; nhưng hình thức cụ thể có thể khác Scrum.

Do đó, **không phải mọi đội Agile đều bắt buộc có Sprint Goal, Product Owner hoặc Sprint Review theo Scrum**. Nhưng một đội tuyên bố đang dùng Scrum phải hiểu chúng là thành phần của khung. Tương tự, một nhóm có bảng To Do–Doing–Done nhưng không có cơ chế kiểm soát WIP và chính sách dòng công việc không nên khẳng định đang thực hiện đầy đủ Kanban chỉ vì dùng các cột trực quan.

### 2.1. Bảy chức năng cần một câu trả lời rõ

| Chức năng cần được đảm bảo | Câu hỏi phải trả lời | Ví dụ cơ chế có thể dùng |
|---|---|---|
| **Định hướng giá trị** | Chúng ta đang giải quyết vấn đề nào, cho ai, và vì sao ưu tiên nó? | Product Goal, outcome hypothesis, roadmap theo kết quả, ưu tiên backlog |
| **Quyền quyết định** | Ai chọn thứ tự, ai đánh giá năng lực, ai quyết định rủi ro/ngoại lệ? | Product Owner trong Scrum, service owner, cơ chế ủy quyền minh bạch |
| **Minh bạch tiến triển** | Điều gì thực sự đã hoàn tất; còn điều gì bị chặn? | Increment/DoD, Kanban board phản ánh workflow, bằng chứng test, trạng thái phụ thuộc |
| **Kiểm tra và phản hồi** | Khi nào và bằng dữ liệu gì chúng ta biết giả thuyết đúng/sai? | Sprint Review, continuous review, product analytics, thử nghiệm người dùng |
| **Chất lượng và khả năng thay đổi** | Thay đổi được tích hợp, kiểm thử và vận hành an toàn thế nào? | DoD, TDD, CI, automated tests, code review, refactoring, kiểm soát vận hành |
| **Kiểm soát dòng công việc** | Khi nào nhận thêm việc và xử lý điểm nghẽn ra sao? | WIP limits, pull policies, flow metrics, tập trung hoàn tất |
| **Cải tiến hệ thống** | Ai xem lại cách làm, quyết định thay đổi và kiểm tra tác dụng? | Sprint Retrospective, operations review, experiment log, cải tiến liên tục |

Không nên diễn giải bảng thành **bảy buổi họp bắt buộc**. Một hoạt động có thể phục vụ nhiều chức năng; một chức năng có thể được hỗ trợ bởi nhiều thực hành. Điều cần tránh là **chức năng bị mất nhưng không ai nhận ra**.

### 2.2. Sơ đồ logic của một phương án kết hợp có chủ đích

~~~mermaid
flowchart LR
    A["Nhu cầu / mục tiêu / ràng buộc"] --> B["Chọn cách tổ chức và thực hành"]
    B --> C["Cơ chế bảo vệ giá trị, chất lượng, dòng công việc"]
    C --> D["Tạo Increment / kết quả kiểm chứng được"]
    D --> E["Phản hồi người dùng + dữ liệu vận hành"]
    E --> F{"Mục tiêu và cơ chế còn hiệu quả?"}
    F -->|"Có"| G["Duy trì và cải thiện nhỏ"]
    F -->|"Không hoặc chưa rõ"| H["Điều chỉnh có căn cứ, ghi đánh đổi"]
    G --> B
    H --> B
~~~

Nếu một nhóm bỏ khâu phản hồi người dùng nhưng giữ toàn bộ bảng công việc, vòng lặp trên bị đứt ở bước kiểm tra giá trị. Nếu bỏ tiêu chuẩn chất lượng nhưng phát hành thường xuyên, tốc độ tạo lỗi có thể tăng. Nếu bỏ quyết định ưu tiên, Developers nhận nhiều chỉ đạo đối lập. **Một cơ chế có thể ít nổi bật nhưng giữ vai trò kết nối cả hệ thống**.

## 3. Scrum: có thể bổ sung kỹ thuật, nhưng không thể cắt bỏ tùy tiện khung cốt lõi

Theo **The Scrum Guide (2020)**, Scrum là khung nhẹ và **có chủ đích chưa hoàn chỉnh** (*purposefully incomplete*). Nó nêu các phần cần thiết để thực hiện lý thuyết Scrum, trong khi những thực hành và công cụ khác có thể được sử dụng trong khung. Scrum dựa trên **minh bạch, kiểm tra, thích ứng** và các giá trị **cam kết, tập trung, cởi mở, tôn trọng, can đảm**.

### 3.1. Thành phần Scrum được quy định

| Nhóm thành phần | Thành phần | Cơ chế được bảo vệ |
|---|---|---|
| **Accountabilities** | Product Owner, Scrum Master, Developers trong một Scrum Team | Làm rõ trách nhiệm về giá trị, hiệu quả Scrum và tạo Increment |
| **Events** | Sprint; trong Sprint có Sprint Planning, Daily Scrum, Sprint Review, Sprint Retrospective | Nhịp kiểm tra và thích ứng thường xuyên |
| **Artifacts** | Product Backlog, Sprint Backlog, Increment | Minh bạch về công việc, mục tiêu và kết quả |
| **Commitments** | Product Goal, Sprint Goal, Definition of Done | Hướng tập trung, mục đích Sprint và chất lượng của Increment |

Một Scrum Team được thiết kế **cross-functional** và **self-managing**. Một hoặc nhiều Increment có thể được tạo trong Sprint và có thể được phát hành trước Sprint Review khi đáp ứng điều kiện; Sprint Review không phải cổng phê duyệt bắt buộc để phát hành.

### 3.2. Thành phần nào không bắt buộc theo Scrum Guide?

Scrum Guide **không yêu cầu**:

- Story point, velocity, Planning Poker hay burn-down chart.
- Dùng Jira, Trello hoặc một phần mềm cụ thể.
- Viết mọi PBI theo mẫu “Là người dùng, tôi muốn…”.
- TDD, pair programming, một framework test hoặc ngôn ngữ lập trình cụ thể.
- “Sprint 0”, “hardening Sprint”, “UAT Sprint” như những sự kiện chính thức.
- Một phiên refinement cố định có timebox được quy định như sự kiện Scrum.
- Quy trình phê duyệt release sau mỗi Sprint Review.

Các thực hành này có thể được chọn khi hữu ích, nhưng **không được nhầm kỹ thuật tùy chọn với phần cốt lõi Scrum**.

### 3.3. Ví dụ điều chỉnh có chủ đích khi vẫn dùng Scrum

**Vấn đề:** Sprint Planning kéo dài vì Developers chỉ biết các phụ thuộc ngay lúc chọn PBI.

**Thay đổi:** Product Owner và Developers tổ chức các phiên refinement ngắn khi cần, cùng QA/bảo mật làm rõ ví dụ, phụ thuộc và phạm vi của PBI gần được lựa chọn.

**Điều được giữ:** Product Goal, Sprint Goal, các Scrum events, accountabilities và DoD.

**Điều được cải thiện:** Sprint Planning có đủ thông tin để Developers chọn PBI có khả năng hoàn tất; chất lượng và bất định được nhìn thấy sớm.

**Bằng chứng cần kiểm tra:** giảm số item bị chặn vì thiếu quyết định, số Increment đạt DoD tăng hoặc ổn định, ít làm lại do hiểu sai; không chỉ đo “Planning ngắn hơn”.

Đây là việc **bổ sung/cải thiện thực hành trong Scrum**, không loại bỏ cơ chế cốt lõi.

### 3.4. Ví dụ cắt bỏ làm sai lệch Scrum

**Vấn đề được nêu:** “Không cần Sprint Review vì đã báo cáo tiến độ qua email.”

**Hệ quả:** các bên mất một sự kiện chính thức để cùng kiểm tra kết quả Sprint, bối cảnh sản phẩm và thích ứng Product Backlog. Email có thể hỗ trợ truyền đạt, nhưng không tự đảm bảo cuộc trao đổi kiểm tra thực nghiệm.

Nếu vẫn tuyên bố làm Scrum đầy đủ mà bỏ Sprint Review, khung không còn nguyên vẹn. Nếu tổ chức chuyển sang một mô hình khác có **review liên tục** thay vì Sprint, hãy mô tả thành thật **mô hình mới và cơ chế phản hồi**; đừng dùng nhãn Scrum để che chỗ đã bỏ.

### 3.5. Một số điểm dễ bị thay sai vì hiểu sai Scrum

**Sai:** “Sprint Goal là danh sách ticket không được thay đổi, nên bỏ Sprint Goal cho linh hoạt.”

**Đúng:** Sprint Goal tạo trọng tâm; Developers có thể điều chỉnh Sprint Backlog và thương lượng phạm vi với Product Owner khi học thêm, không làm nguy hiểm Sprint Goal và không giảm chất lượng. Nếu Sprint Goal trở nên lỗi thời, Scrum có cơ chế hủy Sprint do Product Owner quyết định.

**Sai:** “Đội không thể Done vì chờ kiểm thử, nên đổi DoD thành ‘code xong’.”

**Đúng:** DoD làm minh bạch chất lượng. Cần cải thiện năng lực kiểm thử/tích hợp, chia lát cắt hoặc điều chỉnh phạm vi phù hợp; nếu một PBI chưa đáp ứng DoD thì không thuộc Increment Done.

**Sai:** “Scrum Master chỉ giúp đặt lịch nên không cần.”

**Đúng:** Scrum Master chịu trách nhiệm về hiệu quả Scrum Team, giúp Scrum được hiểu, hỗ trợ đội và tổ chức tháo trở ngại. Nếu tổ chức chọn cách quản trị khác, cần nói rõ; bỏ accountability nhưng giữ nhãn đầy đủ là sai lệch.

**Sai:** “Cần thêm việc khẩn nên cho stakeholder giao thẳng task vào Sprint.”

**Đúng:** Product Owner chịu trách nhiệm thứ tự Product Backlog; Developers quản lý kế hoạch thực hiện; thay đổi cần xét Sprint Goal, DoD và quyền quyết định phù hợp.

## 4. Kanban: trực quan hóa không thay thế quản lý dòng công việc

Kanban giúp xác định và quản lý dòng công việc hướng tới giá trị. **The Kanban Guide** nêu ba thực hành chính: **định nghĩa và trực quan hóa workflow**, **chủ động quản lý các item trong workflow** và **cải tiến workflow**. Một hệ thống Kanban cần có **Definition of Workflow (DoW)** rõ ràng.

### 4.1. Những gì một Definition of Workflow cần làm rõ

| Thành phần | Ý nghĩa | Nguy cơ nếu bỏ |
|---|---|---|
| Work item types | Loại công việc nào đi qua hệ thống? | Mọi việc bị trộn, số liệu khó diễn giải |
| Điểm bắt đầu và kết thúc | Khi nào item đã started và khi nào Done theo hệ thống? | WIP, cycle time và dự báo không nhất quán |
| Các trạng thái | Item đi qua những bước nào? | Không thấy điểm chờ và phụ thuộc |
| Kiểm soát WIP | Bằng cách nào hạn chế công việc đã bắt đầu chưa hoàn tất? | Hàng chờ tăng không giới hạn |
| Chính sách rõ ràng | Điều kiện chuyển việc, chọn ưu tiên, xử lý blocker/ngoại lệ? | Mỗi người quyết khác, bảng không phản ánh thực tế |
| Service Level Expectation (SLE) | Kỳ vọng thời gian item đi qua workflow, gồm thời gian và xác suất | Không có tham chiếu để nhận diện việc già tuổi/rủi ro |

**Kanban không bắt buộc mọi đội dùng bảng ba cột hoặc đặt WIP limit bằng số người**. Chính sách và giới hạn được thiết kế theo hệ thống thực, nhưng phải làm rõ và có thể kiểm chứng.

### 4.2. Chỉ có bảng Kanban có phải đã làm Kanban?

Ví dụ:

~~~text
To Do (50) -> Doing (26) -> Done (3)
                 WIP không có giới hạn
                 Item blocked bị cất khỏi bảng
                 Không định nghĩa Done hoặc cycle time
~~~

Bảng giúp nhìn một phần công việc nhưng **chưa bảo đảm cơ chế kiểm soát luồng**. Nếu đội nói “đang làm Kanban” trong khi không có DoW, chính sách kéo và đo lường tối thiểu, họ cần phân biệt **đang dùng board trực quan** với **đang vận hành một hệ thống Kanban theo định nghĩa rõ**.

### 4.3. Ví dụ kết hợp có chủ đích với Kanban

**Vấn đề:** Một Scrum Team thường xuyên bắt đầu nhiều PBI, QA quá tải, nhiều việc không đạt DoD trong Sprint.

**Bổ sung từ Kanban:** định nghĩa workflow Ready → Development → Verification → Done; giới hạn WIP theo năng lực thực; đánh dấu blocked vẫn nằm trong WIP; đo throughput, work item age, cycle time và WIP.

**Giữ từ Scrum:** Product Goal, Sprint Goal, DoD, các events và accountabilities. Developers dùng Daily Scrum để kiểm tra item gần Done và điều chỉnh Sprint Backlog hướng Sprint Goal.

**Kiểm tra:** số item già tuổi giảm, thời gian chờ tích hợp/QA giảm và Increment thực sự đạt DoD; không chỉ tăng số ticket Done.

Nếu đội bỏ Sprint và chuyển sang luồng liên tục, đó có thể là lựa chọn phù hợp. Nhưng cần **đặt tên và mô tả mô hình đúng với cách làm mới**, xác định cơ chế bổ sung công việc, phản hồi sản phẩm và cải tiến thay cho nhịp Sprint, không chỉ xóa sự kiện.

### 4.4. Dữ liệu dòng công việc là một phần của cơ chế

The Kanban Guide nêu bốn flow metrics tối thiểu:

| Chỉ số | Câu hỏi được trả lời |
|---|---|
| **WIP** | Hiện đang có bao nhiêu item đã bắt đầu nhưng chưa hoàn tất? |
| **Throughput** | Bao nhiêu item hoàn tất trong một khoảng thời gian? |
| **Work item age** | Item đang mở đã ở trong workflow bao lâu? |
| **Cycle time** | Item đã hoàn tất mất bao lâu từ started tới Done? |

Nếu bỏ đo work item age vì “chỉ cần xem số ticket Done”, đội dễ bỏ quên những item mắc kẹt. Nếu bỏ WIP limit vì “Developers không được ngồi không”, đội có thể tiếp tục tăng tồn đọng. Nếu sửa định nghĩa Done để số liệu đẹp, dự báo mất tính đáng tin.

**Dùng Kanban không bắt buộc phải từ bỏ Scrum. Dùng Scrum cũng không cản trở đội kiểm soát WIP.** Kết hợp có ích khi mọi cơ chế và ranh giới được định nghĩa nhất quán.

## 5. XP: phản hồi thường xuyên không thể tách khỏi khả năng thay đổi code an toàn

**Extreme Programming (XP)** nhấn mạnh tương tác khách hàng, vòng lặp ngắn và các thực hành kỹ thuật giúp thay đổi phần mềm với rủi ro có thể quản lý. Những thực hành thường gắn với XP như **TDD, continuous integration, refactoring, pair programming, small releases, simple design, collective ownership và sustainable pace** hỗ trợ lẫn nhau.

### 5.1. Vì sao chỉ “lấy phần dễ” của XP có thể phản tác dụng?

Ví dụ một đội nói:

> “Chúng tôi dùng XP vì giao tính năng nhỏ và thay đổi yêu cầu thường xuyên. Nhưng test tự động, tích hợp liên tục và refactoring sẽ làm sau khi kịp roadmap.”

Những bản giao nhỏ vẫn có thể hữu ích; nhưng khi mỗi thay đổi không được kiểm tra đáng tin, chi phí sửa lỗi và rủi ro tích hợp tăng. Khách hàng phản hồi càng thường xuyên, đội càng cần **khả năng sửa code an toàn**. Nếu không, một chuỗi thay đổi nhỏ có thể tạo ra hệ thống khó bảo trì và mất lòng tin.

Không có nghĩa mọi đội phải dùng mọi thực hành XP đúng một hình thức cố định để có lợi. Nhưng khi chọn bỏ một thực hành hỗ trợ chất lượng, cần xác định **bằng cách nào đội vẫn kiểm soát được các rủi ro mà thực hành ấy thường giải quyết**.

### 5.2. Ví dụ giữ cơ chế dù thay kỹ thuật

| Chức năng cần bảo vệ | Thực hành XP thường dùng | Cách triển khai thay thế có thể phù hợp, nếu đủ bằng chứng |
|---|---|---|
| Phát hiện lỗi logic sớm | TDD và unit tests | Kiểm thử tự động phù hợp kết hợp test thiết kế trước/kiểm tra code; đánh giá lỗi và khả năng sửa |
| Phát hiện xung đột tích hợp sớm | Continuous Integration | Tích hợp thay đổi nhỏ thường xuyên vào phiên bản chung với phép kiểm tra đáng tin, không nhất thiết cùng một dịch vụ CI thương mại |
| Giảm chi phí sửa đổi về sau | Refactoring và simple design | Cải tiến cấu trúc có chủ đích, kiểm thử hồi quy và tiêu chuẩn kỹ thuật rõ |
| Chia sẻ kiến thức/giảm phụ thuộc cá nhân | Pair programming, collective code ownership | Pair ở phần rủi ro cao, peer review, mentoring và cách sở hữu code tránh điểm nghẽn cá nhân |
| Học từ người dùng sớm | On-site customer, small releases | Đại diện có quyền quyết định, phản hồi nhanh, test với người dùng, release có kiểm soát |
| Giữ nhịp làm việc dài hạn | Sustainable pace | Quản lý WIP, phụ thuộc, nghỉ ngơi và sự cố thay vì làm thêm giờ triền miên |

Một lựa chọn thay thế chỉ đáng tin khi **cơ chế được giữ và tác dụng được quan sát**; không phải cứ đổi tên thực hành là tương đương.

### 5.3. TDD, BDD và acceptance tests có cùng vai trò không?

Không hoàn toàn:

- **TDD:** vòng kiểm thử nhỏ giúp điều hướng thiết kế/code ở phạm vi phù hợp.
- **BDD/Specification by Example:** giúp các bên thống nhất hành vi nghiệp vụ qua ví dụ và ngôn ngữ chung.
- **Acceptance tests:** xác nhận hành vi cụ thể theo tiêu chí chấp nhận đã thỏa thuận.
- **Integration/E2E tests:** kiểm tra tương tác giữa thành phần hoặc luồng người dùng đầu-cuối.
- **Kiểm thử khám phá, bảo mật, hiệu năng, accessibility:** xử lý những rủi ro không thể suy ra đầy đủ từ các test khác.

Một bộ Given–When–Then được viết ra không phải bằng chứng phần mềm đã chạy đúng. Một unit test pass không chứng minh toàn bộ hành trình an toàn. Kết hợp có chủ đích nghĩa là **chọn chiến lược kiểm chứng theo rủi ro**, không dùng một kỹ thuật duy nhất để thay thế tất cả.

### 5.4. XP với Scrum hoặc Kanban

Một đội có thể:

- Dùng Scrum để tạo nhịp mục tiêu và kiểm tra.
- Dùng Kanban để quản lý WIP và điểm nghẽn.
- Dùng XP để cải thiện khả năng tạo phần mềm tích hợp đáng tin, giao nhỏ và phản hồi nhanh.

Các mảnh này **bổ sung chức năng khác nhau**. Nhưng nếu đội chỉ lấy tên của ba cách tiếp cận rồi bỏ DoD, không giới hạn WIP, không kiểm thử và không tiếp nhận phản hồi thật, đó không phải một mô hình “rất Agile”; nó là một chuỗi lỗ hổng trách nhiệm.

## 6. Lean, DevOps và Product Discovery: bổ sung chứ không thay thế giá trị

Các cách tiếp cận khác có thể giải quyết những vấn đề mà Scrum, Kanban hoặc XP không tự mô tả hết. Điều quan trọng là biết **mỗi thực hành đang bù vào khoảng trống nào**, không tích lũy thuật ngữ.

### 6.1. Lean: tối ưu toàn dòng giá trị, không chỉ hiệu suất cá nhân

Lean thường gợi ý nhìn **dòng giá trị**, xác định thời gian chờ, lãng phí, làm việc theo lô nhỏ và cải tiến liên tục.

Ví dụ một Developer viết code một story trong hai ngày, nhưng story chờ phê duyệt và kiểm thử 18 ngày. Tăng tốc viết code thêm 20% có thể ít tác dụng hơn giảm hàng chờ và đưa kiểm chứng sớm vào workflow.

**Kết hợp có chủ đích:** dùng value stream mapping để tìm điểm nghẽn, dùng Kanban/WIP policies để hạn chế việc bắt đầu quá nhiều, dùng CI và kiểm thử để giảm làm lại, theo dõi lead time/cycle time và chất lượng.

**Cắt bỏ tùy tiện:** giải thích “loại bỏ lãng phí” thành bỏ kiểm thử, tài liệu tuân thủ hoặc hoạt động trao đổi nghiệp vụ mà không xem chúng tạo giá trị bảo vệ gì. Một tài liệu phục vụ kiểm toán hoặc quyết định quan trọng **không tự là lãng phí** chỉ vì nó không phải code.

### 6.2. DevOps: rút ngắn vòng từ thay đổi tới vận hành an toàn

DevOps nhấn mạnh cộng tác giữa phát triển và vận hành, tự động hóa phù hợp, quan sát sản phẩm và cải tiến khả năng giao phần mềm.

**Kết hợp có chủ đích:** nhóm sử dụng Scrum/Kanban để ưu tiên và theo dõi việc, đầu tư build/CI/CD, kiểm thử, monitoring, rollback/roll-forward, quản lý sự cố và phản hồi từ production.

**Cắt bỏ tùy tiện:** bỏ kiểm soát thay đổi quan trọng với lập luận “DevOps là deploy nhanh”, trong khi chưa có test, quan sát và khả năng khôi phục. Tần suất triển khai cao nhưng lỗi người dùng tăng không tự chứng minh giao hàng hiệu quả.

### 6.3. Product Discovery: kiểm tra đúng vấn đề trước khi tăng tốc xây

Một nhóm có thể giao Increment kỹ thuật rất nhanh nhưng giải quyết sai nhu cầu. Product discovery có thể bổ sung phỏng vấn, quan sát tác vụ, prototype, phân tích hành vi và thử nghiệm giả thuyết.

**Kết hợp có chủ đích:** kết nối discovery với Product Goal/backlog và delivery; giả thuyết được kiểm chứng bằng hành vi người dùng; ưu tiên thay đổi khi có thông tin mới.

**Cắt bỏ tùy tiện:** tổ chức nhiều workshop ý tưởng nhưng không bao giờ đưa giả thuyết thành phần mềm kiểm chứng được; hoặc ngược lại, chỉ nhìn velocity mà không hỏi người dùng có đạt outcome không.

**Dual-track discovery và delivery** là một cách tổ chức có thể hữu ích, không phải hai bộ phận buộc tách khỏi nhau. Nếu discovery chỉ tạo tài liệu cho delivery sau nhiều tháng, đội có nguy cơ tái tạo một chuỗi bàn giao dài.

### 6.4. Các mô hình kết hợp khác không tự động tốt hoặc xấu

Những tên gọi như **Scrumban**, **Agile–Stage-Gate**, “hybrid Agile”, “Agile với quản trị theo dự án” hay các mô hình mở rộng quy mô được sử dụng trong nhiều tổ chức với **định nghĩa khác nhau**. Nhãn hiệu hoặc tên phương pháp không tự chứng minh cách triển khai.

Hãy hỏi:

1. Đâu là phần **quy định chính thức** của cách tiếp cận được viện dẫn?
2. Đâu là phần đội **tự chọn bổ sung**?
3. Quyết định nào bị chuyển cấp hay được ủy quyền?
4. Có giữ được vòng phản hồi và chất lượng không?
5. Cơ chế nào giảm được điểm nghẽn thật?
6. Những chi phí mới do mô hình phối hợp nhiều lớp tạo ra là gì?

Không cần áp dụng một “gói phương pháp” có nhiều lớp quản trị nếu một vài thay đổi nhỏ đã giải quyết vấn đề. Ngược lại, với sản phẩm có phụ thuộc pháp lý hoặc nhà cung cấp dài hạn, chỉ dựa vào một bảng ticket có thể không đủ.

## 7. Các cách kết hợp thường gặp và giới hạn cần xem

### 7.1. Scrum + Kanban: Scrum with Kanban

**Động cơ:** Nhóm có Sprint Goal, nhưng nhiều PBI đang dở, thường bị chặn ở review, kiểm thử hoặc triển khai.

**Có thể bổ sung:**

- Trực quan hóa luồng chi tiết hơn Sprint Backlog.
- Kiểm soát WIP và chính sách kéo việc phù hợp.
- Đo throughput, cycle time, work item age.
- Dùng Daily Scrum để nhìn item gần Done và điểm chặn, không chỉ báo cáo từng người.

**Phần Scrum vẫn cần giữ nếu tiếp tục gọi là Scrum:** Scrum Team accountabilities, Sprint và bốn sự kiện trong Sprint, artifacts, Product Goal, Sprint Goal và Definition of Done.

**Điều dễ nhầm:** Số item được Developers lựa chọn cho Sprint **không phải** số item phải làm đồng thời. Một Sprint có thể dự kiến hoàn tất sáu PBI, nhưng đội chỉ cho phép hai PBI cùng lúc ở Development để giảm WIP.

**Điều cần đo:** Increment đạt DoD, số item bị chặn, tuổi công việc, cycle time, chất lượng. Tăng throughput ticket không đủ nếu cách chia ticket hoặc định nghĩa Done đổi.

### 7.2. Kanban + các nhịp review/retrospective của Scrum

**Động cơ:** Nhóm xử lý yêu cầu liên tục không có Sprint Goal có ý nghĩa, nhưng thiếu thời gian kiểm tra xu hướng và cải tiến.

**Có thể bổ sung:** review sản phẩm định kỳ, hoạt động retrospective, trao đổi replenishment với người ưu tiên dịch vụ.

**Cơ chế cần giữ theo Kanban:** DoW, kiểm soát WIP, chính sách rõ, SLE, metrics và cải tiến dòng công việc.

**Điều cần diễn đạt trung thực:** Mượn cách họp Review hoặc Retrospective **không tự biến hệ thống Kanban thành Scrum**, cũng không cần ép mọi luồng hỗ trợ thành Sprint chỉ để dùng một cuộc họp có ích.

### 7.3. Scrum + XP engineering

**Động cơ:** Nhóm tổ chức Scrum đầy đủ nhưng vẫn không tạo Increment có chất lượng do kiểm thử hồi quy muộn và tích hợp khó.

**Có thể bổ sung:** TDD khi phù hợp, BDD/acceptance examples, CI, pair programming, code review, refactoring, small releases.

**Điều cần giữ:** DoD và chất lượng của Increment; Sprint Review dựa trên phần mềm có thể dùng; Developers có khả năng tự quản lý kỹ thuật trong giới hạn phù hợp.

**Điều cần đo:** lỗi tích hợp, thời gian đến phản hồi, thay đổi gây hồi quy, khả năng hoàn tất và sử dụng Increment, mức độ làm lại.

### 7.4. Kanban + XP + phản hồi khách hàng liên tục

**Động cơ:** Đội bảo trì sản phẩm, xử lý nhiều yêu cầu nhỏ và sự cố thay đổi ưu tiên, nhưng vẫn cần giữ chất lượng và học từ người dùng.

**Có thể bổ sung:** Kanban kiểm soát dòng công việc; XP giúp kiểm thử và sửa code an toàn; đại diện khách hàng/Service Owner giúp chọn ưu tiên; hoạt động review ngắn theo nhịp hoặc theo sự kiện.

**Rủi ro:** nếu mọi thứ được gọi là expedite, WIP limits mất ý nghĩa. Nếu khách hàng quyết mọi kỹ thuật, đội mất khả năng đánh giá rủi ro; nếu không có quyền ưu tiên rõ, Developers bị kéo theo người gửi yêu cầu to tiếng nhất.

### 7.5. Phân phối Agile + kiểm soát Stage-Gate bắt buộc

**Động cơ:** Một hệ thống cần kiểm toán, phê duyệt bảo mật, nghiệm thu hợp đồng hoặc chứng nhận trước khi triển khai.

**Có thể kết hợp:** phát triển theo Increment nhỏ và kiểm thử liên tục; làm rõ yêu cầu kiểm soát từ đầu; tự động lưu bằng chứng theo build và phạm vi; giữ phê duyệt có thẩm quyền tại mốc thực sự bắt buộc.

**Rủi ro:** dùng giai đoạn duyệt để hoãn toàn bộ kiểm thử đến cuối và khiến phản hồi bị trễ hàng tháng; hoặc ngược lại bỏ qua kiểm soát quan trọng chỉ để được gọi là Agile.

**Câu hỏi:** Những chứng cứ nào có thể tạo sớm? Quyết định nào bắt buộc có người ký? Cổng phê duyệt phục vụ rủi ro thực hay chỉ lặp công việc đã có bằng chứng?

### 7.6. Tổ chức nhiều đội cùng một sản phẩm

Một chương trình lớn có thể cần đồng bộ phụ thuộc và tích hợp giữa các nhóm. Nhưng **thêm cuộc họp liên đội không thay thế Increment tích hợp**.

Nếu dùng Scrum với nhiều Scrum Team trên cùng một sản phẩm, Scrum Guide yêu cầu chia sẻ cùng **Product Goal, Product Backlog và Product Owner**, và các đội phải cùng theo một **Definition of Done** để các Increment được tích hợp.

Nhóm có thể bổ sung các cuộc trao đổi phụ thuộc, kiểm thử hợp đồng API, pipeline tích hợp hoặc chính sách vận hành chung, nhưng cần kiểm tra chúng có **giảm thời gian chờ và lỗi** hay chỉ thêm tầng báo cáo.

## 8. Cách đánh giá một đề xuất kết hợp bằng sáu câu hỏi

Giả sử lãnh đạo đề xuất: “Bỏ Daily Scrum, thay bằng dashboard; tăng WIP để ai cũng có việc; để QA ở cuối tháng, như vậy Agile sẽ nhanh hơn”. Trước khi đồng ý hoặc phản đối, hãy phân tích:

### Câu 1 — Vấn đề hiện tại được quan sát bằng gì?

“Cuộc họp tốn thời gian” là cảm nhận có thể đúng, nhưng chưa đủ mô tả hệ quả. Cần nhìn:

- Daily Scrum thực tế kéo dài bao lâu, có giúp Developers điều chỉnh Sprint Backlog không?
- Những item nào đang blocked, work item age bao nhiêu?
- QA chờ vì thiếu kỹ năng, thiếu môi trường hay vì story quá lớn?
- Bao lâu một Increment thực sự đạt DoD và người dùng được nhận phản hồi?

Nếu không có bối cảnh, đội dễ chữa **triệu chứng dễ thấy** mà không xử lý **điểm nghẽn chính**.

### Câu 2 — Thực hành đang bị thay có chức năng nào?

- Daily Scrum giúp **kiểm tra tiến triển tới Sprint Goal và điều chỉnh kế hoạch**.
- WIP control giúp **hạn chế việc bắt đầu vượt quá năng lực hoàn tất**.
- Kiểm thử và DoD giúp **phân biệt code xong với Increment thật sự hoàn tất**.

Bỏ các cơ chế này có thể làm dashboard đẹp hơn và cuộc họp ít hơn, nhưng không nhất thiết làm sản phẩm ra nhanh.

### Câu 3 — Mô hình mới giữ hoặc thay thế chức năng đó ra sao?

Ví dụ:

| Điều thay đổi được đề xuất | Cơ chế phải còn | Phương án có căn cứ |
|---|---|---|
| Dùng dashboard không đồng bộ để giảm thời gian đọc trạng thái | Developers vẫn kiểm tra và điều chỉnh để đạt Sprint Goal | Giữ Daily Scrum 15 phút, chuyển việc cập nhật dữ liệu sang trước buổi; dùng thời gian để xử lý luồng và trở ngại |
| Giảm số item đang làm cùng lúc | Kiểm soát WIP nhưng không bỏ xử lý việc khẩn có thật | Thử WIP limit theo công đoạn và chính sách expedite |
| Rút ngắn thời gian kiểm thử cuối kỳ | Chất lượng/DoD không giảm | Đưa kiểm thử vào sớm, CI, test automation và chia lát cắt |
| Giảm số cuộc họp cho nhóm không theo Scrum | Vẫn có vòng phản hồi và ra quyết định | Định nghĩa review/replenishment/retrospective phù hợp workflow |

Nếu đội **không sử dụng Scrum**, họ không phải giữ Daily Scrum như một sự kiện chính thức; nhưng vẫn cần câu trả lời cho chức năng kiểm tra tiến triển và phối hợp. Nếu **vẫn tự nhận Scrum đầy đủ**, không thể bỏ sự kiện chính thức chỉ bằng cách đổi tên.

### Câu 4 — Tác động tới ai và ai có quyền quyết định?

Đổi DoD có thể ảnh hưởng người dùng, vận hành và bảo mật. Đổi chính sách ưu tiên có thể ảnh hưởng khách hàng và mục tiêu sản phẩm. Đổi cơ chế phát hành có thể ảnh hưởng nghĩa vụ hợp đồng.

Đội không nên tự thay đổi những ràng buộc nằm ngoài thẩm quyền. Ngược lại, lãnh đạo cũng không nên áp đặt phương án kỹ thuật không có bằng chứng rồi yêu cầu Developers nhận trách nhiệm cho mọi rủi ro.

### Câu 5 — Bằng chứng thành công và guardrails là gì?

Không chỉ đo:

> “Số cuộc họp giảm 30%, số ticket Done tăng 20%.”

Cần đo cùng:

- Thời gian từ bắt đầu tới Increment đạt DoD.
- WIP, work item age và item bị chặn.
- Lỗi phát hiện muộn, sự cố sau triển khai và khả năng khôi phục.
- Người dùng có hoàn thành tác vụ quan trọng hơn không?
- Chất lượng, an toàn, khối lượng làm việc bền vững có được giữ không?

**Guardrails** là các điều kiện không được đánh đổi để tăng chỉ số, chẳng hạn không bỏ kiểm tra phân quyền áp dụng, không che bug nghiêm trọng và không ép nhân sự làm thêm giờ liên tục.

### Câu 6 — Khi nào xem lại và có thể đảo ngược không?

Một thay đổi chính sách nên được coi là **thử nghiệm có mục tiêu** khi chưa có bằng chứng đủ:

> “Trong ba chu kỳ làm việc, chúng ta thử giới hạn Development WIP, theo dõi cycle time của các item tương đồng và số Increment đạt DoD. Nếu tình trạng tắc nghẽn không cải thiện hoặc chất lượng giảm, chúng ta xem lại giới hạn và điều kiện kéo việc.”

Không phải mọi quyết định đều có thể đảo ngược dễ dàng. Những thay đổi liên quan dữ liệu, bảo mật, hợp đồng hoặc kiến trúc có chi phí và nghĩa vụ cao cần đánh giá sâu và thẩm quyền trước khi thử.

## 9. Ma trận nhận diện “kết hợp” hay “bỏ mất cơ chế”

| Tuyên bố | Điều thực sự diễn ra | Phân loại sơ bộ | Điều cần sửa hoặc xác minh |
|---|---|---|---|
| “Scrum + Kanban” | Giữ Scrum Goal/DoD/events; WIP và flow metrics giúp giảm tắc nghẽn | **Kết hợp có chủ đích** nếu có dữ liệu và chính sách rõ | Theo dõi Increment, điểm chặn, phản hồi |
| “Scrum tinh gọn” | Bỏ Review, Retro và DoD để chỉ giữ Planning + Daily | **Cắt bỏ thành phần Scrum** | Không gọi là Scrum nguyên vẹn; xác định cách kiểm tra, cải tiến và chất lượng |
| “Kanban đơn giản” | Chỉ dùng bảng To Do–Doing–Done, WIP vô hạn | **Trực quan hóa, chưa đủ cơ chế Kanban** | Định nghĩa DoW, WIP control, policies, SLE và metrics |
| “XP nhẹ” | Có small releases nhưng không có cách kiểm soát hồi quy | **Thiếu cơ chế kỹ thuật hỗ trợ phản hồi** | Xây chiến lược kiểm thử/CI và cải thiện chất lượng |
| “DevOps nhanh” | Deploy nhiều nhưng không có quan sát hoặc phương án khôi phục | **Tối ưu tốc độ bề mặt** | Thêm kiểm soát chất lượng, monitoring, rollback/roll-forward |
| “Phù hợp tuân thủ” | Tạo bằng chứng kiểm tra trong Sprint và phê duyệt mốc bắt buộc | **Có thể là kết hợp có chủ đích** | Kiểm tra ranh giới quyền hạn và tránh kiểm thử dồn cuối |
| “Không cần kế hoạch vì Agile” | Không ai biết mục tiêu, phạm vi dự báo hoặc điểm quyết định | **Bỏ cơ chế phối hợp** | Lập kế hoạch thích ứng với giả định, rủi ro và nhịp xem lại |
| “Hybrid để khách hàng tham gia hơn” | Có đại diện nghiệp vụ trả lời nhanh, ví dụ AC rõ, demo Increment đều | **Có thể là kết hợp tốt** | Đảm bảo thẩm quyền, chất lượng test và phản hồi người dùng thực |
| “Tự quản lý” | Mỗi người tự kéo việc theo ý thích, không có ưu tiên sản phẩm | **Nhầm tự quản lý với thiếu trách nhiệm** | Xác định quyền quyết định, mục tiêu và chính sách luồng |
| “Scale Agile” | Tăng tầng họp, mọi đội vẫn chờ một môi trường tích hợp chung | **Cơ chế phối hợp chưa giải quyết phụ thuộc** | Cải thiện hạ tầng, hợp đồng giao tiếp và tích hợp sớm |

Phân loại trên là **gợi ý chẩn đoán**, không phải lời phán xét chỉ từ tên phương pháp. Cần kiểm chứng với điều kiện thực tế. Một đội có cách làm khác chuẩn nhưng có cơ chế hiệu quả, minh bạch và không tự nhận sai tên khung có thể là một lựa chọn phù hợp.

## 10. Tình huống xuyên suốt: hai cách xây quy trình cho nền tảng học trực tuyến

> **Tất cả số liệu, tên item và diễn biến trong tình huống này đều giả định để minh họa tư duy**, không phải tiêu chuẩn định lượng của Scrum, Kanban hay XP và không phải dữ liệu một nhóm thực tế.

Một đơn vị giáo dục muốn cải thiện hành trình **học viên chọn khóa → thanh toán hoặc ghi danh hợp lệ → được cấp quyền → vào bài đầu tiên**. Có một ngày khai giảng cần phối hợp với truyền thông và vận hành. Đội sản phẩm gồm Product Owner, Developers có kỹ năng frontend/backend/test và một nhóm vận hành hỗ trợ. Phụ thuộc quan trọng là đối tác thanh toán.

### 10.1. Phiên bản A — “Hybrid” bằng cách bỏ những phần bất tiện

Lãnh đạo tuyên bố:

> “Chúng ta dùng Scrum để chia hai tuần, Kanban để nhìn ticket, XP để làm nhanh, và cơ chế phê duyệt của công ty. Bỏ Sprint Review vì phải mời stakeholder, không cần Sprint Goal vì yêu cầu liên tục, DoD chỉ là code xong, QA cuối tháng. Không đặt WIP vì ai rảnh phải lấy việc. Hết Sprint ai đóng nhiều ticket sẽ được đánh giá cao.”

Hệ quả dễ phát sinh:

1. **Không có mục tiêu chung:** Developers lấy item dễ, chưa chắc tạo hành trình đầu-cuối.
2. **Không có kiểm tra giá trị thực:** stakeholder chỉ biết số ticket, không thấy học viên đã làm được gì.
3. **Không rõ Done:** UI xong nhưng API, dữ liệu hoặc quyền truy cập chưa đúng vẫn được đếm.
4. **QA là hàng đợi cuối kỳ:** lỗi tích hợp và bảo mật phát hiện muộn.
5. **WIP quá cao:** nhiều người mở việc mới khi item cũ chưa hoàn tất.
6. **Ưu tiên xung đột:** marketing, vận hành, quản lý dự án liên tục chen yêu cầu.
7. **Dữ liệu dự báo méo:** throughput ticket tăng do chia ticket và đổi định nghĩa Done, không chứng minh năng lực giao hàng.

Một báo cáo “80% hoàn thành” có thể trông tích cực, nhưng không trả lời **người học đã đăng ký và vào bài được chưa?**

### 10.2. Phiên bản B — Xác định vấn đề, chọn cơ chế và quyền quyết định

Đội thống nhất mục tiêu:

> **Học viên đủ điều kiện tự ghi danh hoặc thanh toán theo phương thức được hỗ trợ, nhận trạng thái chính xác và truy cập đúng nội dung trước kỳ khai giảng.**

Sau đó lập **bản đồ cơ chế**:

| Nhu cầu | Thực hành được chọn | Cơ chế và điều kiện bảo vệ |
|---|---|---|
| Có hướng sản phẩm chung | Product Goal, Product Backlog do Product Owner quản lý | Các bên biết vì sao chọn việc, ai quyết định thứ tự |
| Có mục tiêu gần để hoàn tất | Sprint Goal/Sprint Planning nếu dùng Scrum | Developers chọn phạm vi theo năng lực và mục tiêu, kế hoạch có thể thích ứng |
| Không mở quá nhiều việc | WIP control/pull từ Kanban | Item đã bắt đầu không bị bỏ quên; gỡ chặn trước khi mở thêm |
| Làm rõ hành vi thanh toán | Trao đổi kiểu XP/Three Amigos, Given–When–Then | Chứng minh trạng thái thành công, chờ, thất bại và callback lặp |
| Giao phần mềm đúng và tích hợp | DoD + CI, automated tests, refactoring theo nhu cầu | Không coi code xong là Increment hoàn tất |
| Nhận phản hồi sớm | Sprint Review và dùng thử phạm vi giới hạn | Điều chỉnh ưu tiên từ phản hồi người dùng và vận hành |
| Giữ nghĩa vụ và chất lượng | Phân quyền, dữ liệu, bảo mật, phê duyệt bắt buộc | Không đánh đổi an toàn để giữ ngày |
| Cải tiến luồng | Retrospective + flow metrics | Điều chỉnh WIP, môi trường hoặc cách chia story bằng bằng chứng |

Đội không chọn mọi thực hành chỉ vì “nhiều phương pháp sẽ mạnh hơn”. Mỗi thực hành được gắn với một **vấn đề cụ thể** và một **điều cần quan sát**.

### 10.3. Chia theo lát cắt thay vì giao theo tầng kỹ thuật

**Cách chia khó kiểm chứng sớm:**

~~~text
Tuần 1: toàn bộ UI
Tuần 2: toàn bộ API
Tuần 3: toàn bộ database
Tuần 4: toàn bộ QA và tích hợp
~~~

**Cách chia có thể lấy phản hồi sớm:**

| Lát cắt | Hành vi người dùng có thể kiểm chứng | Điều kiện chất lượng tối thiểu |
|---|---|---|
| **ENR-01** | Học viên đủ điều kiện ghi danh khóa miễn phí và vào bài đầu | UI–API–dữ liệu tích hợp, quyền truy cập đúng, yêu cầu lặp không làm sai |
| **ENR-02** | Học viên nhìn thấy trạng thái ghi danh/thanh toán đúng | Dữ liệu từ nguồn đáng tin, thông báo không gây hiểu nhầm |
| **ENR-03** | Học viên thanh toán một phương thức được hỗ trợ và được cấp quyền khi hợp lệ | Xác thực trạng thái, xử lý callback lặp, thất bại, bảo mật |
| **ENR-04** | Học viên tự xử lý một trường hợp lỗi phổ biến | Có hướng dẫn đúng, kiểm chứng với người dùng phù hợp |
| **ENR-05** | Mở rộng phương thức, báo cáo hoặc khuyến mãi theo phản hồi | Chỉ thêm khi giá trị và rủi ro đã đủ rõ |

Nếu sản phẩm không có khóa miễn phí hoặc người dùng mục tiêu đều mua khóa trả phí, **không chọn ENR-01 chỉ vì dễ**. Lát cắt phải phục vụ Product Goal và bối cảnh thực. Một spike tích hợp sandbox có thể giảm bất định, nhưng **không tự động là Increment production đạt DoD**.

### 10.4. Minh họa tiêu chí chấp nhận và kiểm chứng

**PBI:** Học viên có thể xem trạng thái đơn thanh toán và nhận quyền truy cập đúng.

| ID | Tiêu chí chấp nhận cần làm rõ |
|---|---|
| **AC-01** | Giao dịch chưa được xác nhận hợp lệ không được hiển thị là đã thanh toán. |
| **AC-02** | Quyền truy cập chỉ được cấp theo quy tắc và nguồn xác nhận đáng tin đã thống nhất. |
| **AC-03** | Sự kiện xác nhận lặp không tạo giao dịch hoặc quyền trùng sai. |
| **AC-04** | Khi dịch vụ phụ thuộc lỗi, UI không thông báo thành công giả; có trạng thái xử lý phù hợp. |
| **AC-05** | Tài khoản khác không được đọc hoặc sửa đơn và quyền truy cập trái phép. |

~~~gherkin
Feature: Trang thai don dang ky khoa hoc

  Scenario: Giao dich dang cho khong duoc cap quyen som
    Given hoc vien A da gui yeu cau thanh toan don D
    And nguon trang thai chua xac nhan thanh cong
    When A mo trang chi tiet don D
    Then don D duoc hien thi dang xu ly
    And he thong khong cap quyen hoc nhu da thanh toan

  Scenario: Su kien thanh toan lap khong lam sai du lieu
    Given don D da duoc xac nhan thanh cong
    When he thong nhan lai su kien xac nhan cua D
    Then he thong khong tao giao dich hay quyen hoc trung sai

  Scenario: Khong truy cap don cua tai khoan khac
    Given hoc vien B da dang nhap
    And don D thuoc hoc vien A
    When B yeu cau doc chi tiet don D
    Then he thong tu choi theo chinh sach phan quyen
    And khong lam ro ri du lieu rieng cua A
~~~

Đây là **đặc tả bằng ví dụ**, không phải bằng chứng test đã thực thi. Developers cần chọn kiểm thử thực tế phù hợp (unit, API, integration, E2E, bảo mật, khám phá) và ghi nhận kết quả theo build/môi trường. **AC cụ thể không thay thế DoD**, còn Increment đạt DoD không tự chứng minh outcome người dùng đã đạt.

### 10.5. Cách đội xử lý thay đổi ưu tiên

Sau khi thử luồng, học viên vẫn không biết bấm vào đâu để vào bài sau giao dịch. Marketing đề nghị thêm banner chiến dịch; Developers phát hiện một số callback đến muộn.

Đội không tự kéo cả ba việc vào Sprint như “công việc tăng thêm miễn phí”. Thay vào đó:

1. Product Owner xem **điều mới học** và mức tác động của từng việc.
2. Developers làm rõ **rủi ro callback** và tiêu chuẩn an toàn phải giữ.
3. Các bên cân nhắc **lát cắt điều hướng vào bài** nếu đó là trở ngại thực.
4. Banner được giữ hoặc lùi theo chi phí chậm trễ thực, không chỉ vì người yêu cầu có vị trí cao.
5. Scrum Team điều chỉnh kế hoạch phù hợp Sprint Goal; thông tin cho các PBI tương lai được bổ sung vào Product Backlog.
6. Dự báo được cập nhật theo năng lực, phụ thuộc và những bằng chứng mới.

Điều này khác “quy trình cứng không đổi” nhưng cũng khác “ai muốn gì đều chen vào”. **Cơ chế ra quyết định được giữ dù nội dung ưu tiên có thể thay đổi.**

### 10.6. Khi kiểm chứng là bottleneck

Giả sử hệ thống có ba item Development và hai item Verification, cả hai bước đều đầy theo giới hạn thử nghiệm. Developer vừa xong code muốn kéo một story mới.

Nếu Verification không có chỗ, nhóm **không đẩy thêm item** chỉ để duy trì mức sử dụng nhân sự. Nhóm hỗ trợ item gần Done, xử lý lỗi hoặc điều kiện môi trường; khi một item Verification đạt chính sách Done và tạo slot, công đoạn đó kéo item Development đủ điều kiện, sau đó Development có thể kéo story mới nếu còn năng lực.

~~~mermaid
flowchart LR
    A["Ready"] -->|"Kéo khi đủ điều kiện"| B["Development<br/>WIP thử: 3"]
    B -->|"Hạ nguồn có chỗ"| C["Verification<br/>WIP thử: 2"]
    C -->|"Đạt chính sách Done"| D["Done / Increment"]
    C -. "Lỗi cần sửa, vẫn thuộc WIP" .-> B
~~~

Giới hạn 3 và 2 chỉ là ví dụ. Nếu item blocked, **không cất khỏi WIP để làm đẹp số liệu**. Chính sách được xem lại từ throughput, cycle time, age và chất lượng; không cố định theo cảm tính.

### 10.7. Quyết định tại mốc khai giảng

Khi ngày khai giảng là ràng buộc thật, nhóm phân loại:

- **Bắt buộc:** ghi danh hợp lệ, đúng quyền, trạng thái tin cậy, khả năng vận hành và kiểm soát an toàn.
- **Có thể thương lượng:** phương thức bổ sung, bộ gợi ý, dashboard quản trị nâng cao, trang trí chiến dịch.
- **Cần kiểm chứng sớm:** phụ thuộc nhà cung cấp, dữ liệu migration, khả năng xử lý sự cố, kênh triển khai.
- **Phương án dự phòng:** giới hạn kênh/đối tượng hỗ trợ hoặc đổi kế hoạch mở rộng khi có điều kiện hợp pháp và an toàn.

Đội không tự quyết cắt các nghĩa vụ hợp đồng hoặc bảo mật. Nếu mốc và phần cốt lõi không thể đồng thời đáp ứng, **người có thẩm quyền cần ra quyết định về phương án khả thi**, không để Developers thay bằng “Done ảo”.

### 10.8. So sánh kết quả hai cách làm

| Câu hỏi | Phiên bản A: ghép tên, cắt cơ chế | Phiên bản B: kết hợp có chủ đích |
|---|---|---|
| Người dùng cần gì? | Danh sách tính năng do nhiều bên giao | Mục tiêu và giả thuyết người dùng rõ |
| Ai ưu tiên? | Ai yêu cầu lớn tiếng hơn | Product Owner/người có quyền theo cơ chế |
| Khi nào bắt đầu mới? | Khi ai đó rảnh | Khi có năng lực, WIP và điều kiện kéo phù hợp |
| Khi nào tính Done? | Khi đóng ticket/code xong | Khi đạt chuẩn chất lượng và bằng chứng liên quan |
| Làm sao biết có ích? | % task và số ticket | Increment thực, phản hồi người dùng, outcome |
| Làm sao phát hiện lỗi sớm? | QA cuối kỳ | CI, kiểm thử và tích hợp theo lát cắt |
| Thay đổi ưu tiên ra sao? | Cộng thêm việc, không bỏ việc cũ | Thương lượng đánh đổi và cập nhật có căn cứ |
| Tự cải tiến thế nào? | Đổi nghi thức theo cảm giác | Dùng dữ liệu flow/chất lượng và thử nghiệm nhỏ |

**Bài học:** nhiều tên phương pháp không tạo khả năng thích ứng. Khả năng thích ứng đến từ việc giữ **mục tiêu, sự minh bạch, chất lượng, phản hồi và quyền quyết định** trong một hệ thống có thể học từ thực tế.

## 11. Đo tác dụng của việc kết hợp mà không tự đánh lừa mình

Sau khi đổi quy trình, nhiều đội có xu hướng tìm một con số chứng minh thay đổi thành công: số cuộc họp giảm, số story point tăng, số ticket Done nhiều hơn. Những số liệu này có thể hữu ích cho một phần câu hỏi, nhưng **không đủ để đánh giá khả năng tạo giá trị và chất lượng**.

### 11.1. Ba lớp bằng chứng

| Lớp | Câu hỏi | Tín hiệu có thể xem |
|---|---|---|
| **Kết quả người dùng / outcome** | Người dùng có thực sự giải quyết việc cần làm tốt hơn không? | Tỷ lệ tự đăng ký và vào bài thành công; mức cần hỗ trợ; phản hồi định tính |
| **Dòng công việc / năng lực hoàn tất** | Công việc có đi đến Done đều, ít bị chặn và có thể dự báo không? | WIP, throughput, work item age, cycle time, mức hoàn tất Increment |
| **Chất lượng / an toàn / vận hành** | Thay đổi có được tích hợp và cung cấp một cách đáng tin không? | Lỗi hồi quy, sự cố sau phát hành, kiểm tra bảo mật, thời gian khôi phục, rủi ro còn mở |

Khi chọn cách kết hợp, đội nên giữ ít nhất một tín hiệu về **giá trị**, một tín hiệu về **dòng công việc** và một tín hiệu về **chất lượng** trong phạm vi phù hợp. Không cần một dashboard chứa hàng trăm KPI; cần vài số đo mà nhóm thực sự dùng để ra quyết định.

### 11.2. Ví dụ throughput và cycle time không đồng nghĩa outcome

Giả sử hai giai đoạn của một đội có dữ liệu minh họa:

| Quan sát | Trước thay đổi | Sau thay đổi |
|---|---:|---:|
| Ticket Done mỗi tuần | 20 | 28 |
| Item đang mở trung bình | 18 | 12 |
| Cycle time trung bình theo cách đội báo | 8 ngày | 5 ngày |
| Luồng ghi danh tích hợp đạt chuẩn chất lượng | 1 | 3 |
| Lỗi bảo mật nghiêm trọng còn mở | 0 | 1 |

Không thể tự kết luận mô hình mới tốt hơn chỉ vì 28 lớn hơn 20 hoặc 5 nhỏ hơn 8:

- Đội có đổi **cách chia ticket** hoặc **định nghĩa Done** không?
- Một lỗi bảo mật nghiêm trọng có khiến việc mở rộng bị dừng không?
- Item của hai giai đoạn có so sánh được về loại, kích thước và phụ thuộc không?
- Người học có thực sự hoàn thành ghi danh tốt hơn không?
- Có sự thay đổi nhân sự, môi trường, nhu cầu hoặc mức sự cố không?

Trong ví dụ, lỗi bảo mật chưa xử lý phải được ưu tiên quản lý phù hợp. **Chất lượng là guardrail**, không phải một cột điểm có thể cộng bù bằng số ticket.

### 11.3. Không biến velocity thành mục tiêu thưởng/phạt

Velocity và story point có thể hữu ích cho một số đội khi dự báo nội bộ, nhưng **không phải metric bắt buộc của Scrum** và không đo trực tiếp giá trị. Khi tổ chức thưởng theo điểm, đội có động lực chia item và thay thang điểm thay vì tăng kết quả người dùng.

Tương tự, throughput của Kanban cần được đo với **các work items và chính sách Done nhất quán**. Nếu việc bỏ kiểm thử làm nhiều ticket được đóng nhanh hơn, đó có thể là giảm chất lượng chứ không phải hiệu quả dòng công việc.

### 11.4. Dự báo cần điều kiện và độ bất định

Một đội có thể kết hợp throughput lịch sử với số item còn lại để dự báo thô:

\[
\text{Thời gian dự kiến thô}\approx
\frac{\text{Số item còn lại tương đối so sánh được}}
{\text{Throughput trung bình mỗi kỳ}}
\]

Nếu lịch sử minh họa là **3, 5, 4, 4, 6 item/tuần**, throughput trung bình là:

\[
\frac{3+5+4+4+6}{5}=4{,}4\ \text{item/tuần}
\]

Với **22 item tương đối tương đồng**, phép chia \(22/4{,}4 = 5\) tuần là **ước tính trung bình thô**, không phải ngày cam kết hoặc khoảng tin cậy có xác suất. Nếu các item tích hợp thanh toán có rủi ro khác các item cũ, phải phân tích riêng, làm rõ phụ thuộc và điều chỉnh mô hình.

Một dự báo đáng tin cần công bố:

1. Phạm vi dự báo là khả năng, loại item hay outcome nào?
2. “Done” nghĩa là gì?
3. Dữ liệu lịch sử đến từ giai đoạn nào và có đại diện không?
4. Điều kiện năng lực, WIP, chất lượng và phụ thuộc nào được giả định?
5. Khi nào có bằng chứng mới để xem lại?

**Thay đổi cách làm mà không kiểm tra tác động lên dự báo** cũng là một dạng kết hợp thiếu chủ đích.

## 12. Ràng buộc tổ chức, hợp đồng và an toàn: không phải mọi cơ chế đều được bỏ

Nhiều tổ chức gọi phần tuân thủ hoặc phê duyệt là “waterfall”, rồi muốn loại hết để trở nên Agile. Phân tích đó quá đơn giản. Cần phân biệt **yêu cầu kiểm soát bắt buộc** với **cách thực hiện kiểm soát kém hiệu quả**.

### 12.1. Bản đồ ràng buộc

| Loại ràng buộc | Ví dụ | Cách kết hợp có chủ đích |
|---|---|---|
| **Pháp lý và bảo vệ dữ liệu** | Chỉ tài khoản có quyền mới xem được đơn hàng, bảo vệ thông tin cá nhân | Xác định yêu cầu sớm, test bảo mật và lưu bằng chứng; giữ phê duyệt bắt buộc |
| **Hợp đồng và kỳ hạn** | Phải hỗ trợ một luồng tối thiểu trước kỳ khai giảng | Lập kế hoạch theo khả năng cốt lõi, công bố rủi ro, thương lượng biến thể không thiết yếu |
| **Hạ tầng/nhà cung cấp** | Sandbox thanh toán cần được cấp quyền từ đối tác | Thử phụ thuộc sớm, có fallback và mốc xem lại; không ước lượng như đã chắc |
| **Kiểm toán/thay đổi production** | Cần truy vết phiên bản, người phê duyệt và kế hoạch khôi phục | Tự động thu bằng chứng, chuẩn hóa triển khai, vẫn giữ quyền quyết định đúng |
| **Ngân sách và phân bổ nhân lực** | Chuyên gia bảo mật chung cho nhiều đội | Quản lý năng lực, lịch kiểm chứng và phụ thuộc minh bạch, không tự tuyên bố team “đầy đủ kỹ năng” |

Không có mô hình quản trị duy nhất cho mọi sản phẩm. Một ứng dụng thử nghiệm nhỏ và hệ thống xử lý tiền có mức rủi ro khác nhau. **Cơ chế kiểm soát phải tương xứng tác động thực**, không bị loại chỉ vì phát âm giống “quy trình truyền thống”.

### 12.2. Tạo bằng chứng kiểm soát liên tục thay vì dồn cuối

Ví dụ, thay vì:

~~~text
Phân tích 2 tháng -> Code 2 tháng -> Kiểm thử 1 tháng
-> Bảo mật/tuân thủ cuối kỳ -> Phát hiện vấn đề lớn
~~~

Đội có thể thử:

~~~text
Làm rõ ràng buộc trước
-> Lát cắt nhỏ có AC, DoD và test bảo mật phù hợp
-> Tích hợp và lưu bằng chứng theo build
-> Kiểm tra với chuyên gia khi rủi ro xuất hiện
-> Quyết định/phê duyệt tại mốc có thẩm quyền
-> Theo dõi kết quả vận hành
~~~

Kết hợp có chủ đích **không nhất thiết xóa cổng kiểm soát**; nó giảm độ trễ phát hiện lỗi bằng cách tạo chứng cứ sớm và chuẩn hóa những bước có thể chuẩn hóa.

### 12.3. Khi ngày, phạm vi và ngân sách đều cứng

Nếu hợp đồng cố định tất cả trong khi còn phụ thuộc chưa chắc, không một kỹ thuật Scrum/Kanban/XP nào biến bất định thành chắc chắn.

Đội cần làm rõ:

- Phạm vi tối thiểu thực sự bắt buộc theo hợp đồng/quy định.
- Những phần có thể nghiệm thu tăng dần hoặc giao theo giai đoạn.
- Rủi ro có thể kiểm chứng sớm và phương án thay thế.
- Ai có thẩm quyền thương lượng lại ngày/phạm vi/nguồn lực.
- Điều kiện quyết định nếu phương án ban đầu không còn khả thi.

**Không biến “Agile đáp ứng thay đổi” thành lời hứa rằng mọi ràng buộc mâu thuẫn đều có thể được đáp ứng.**

## 13. Cơ chế ra quyết định và quản trị trong một mô hình kết hợp

Ghép công cụ kỹ thuật dễ hơn ghép **quyền quyết định**. Một tổ chức có thể dùng Product Owner theo Scrum, service owner theo Kanban, người quản lý dự án, kiến trúc sư, pháp lý và vận hành. Nếu ai cũng được phép thay thứ tự công việc, Developers sẽ nhận nhiều “ưu tiên số một”.

### 13.1. Những quyền phải được xác định

| Quyết định | Câu hỏi | Vai trò có thể chịu trách nhiệm, tùy mô hình |
|---|---|---|
| **Mục tiêu và giá trị** | Sản phẩm hướng đến kết quả gì? | Product Owner hoặc người sở hữu sản phẩm thực sự được ủy quyền |
| **Thứ tự backlog** | Công việc nào có giá trị/chi phí chậm trễ lớn nhất? | Product Owner nếu dùng Scrum; người chịu trách nhiệm dịch vụ trong mô hình khác |
| **Khả năng và kế hoạch kỹ thuật** | Nhóm có thể hoàn tất gì với chất lượng? | Developers/đội kỹ thuật |
| **Kiểm soát luồng** | Khi nào kéo thêm việc, xử lý blocked/expedite ra sao? | Đội sở hữu workflow và các vai trò theo chính sách |
| **Bảo mật, pháp lý, an toàn** | Điều kiện nào bắt buộc và ai được phép chấp nhận rủi ro? | Vai trò có thẩm quyền theo tổ chức và quy định |
| **Phát hành** | Khi nào và cho ai có thể cung cấp khả năng mới? | Vai trò phát hành/vận hành/sản phẩm theo chính sách |
| **Thay đổi quy trình** | Điều gì được thử, ai xem dữ liệu và quyết định giữ/đổi? | Scrum Team, service team, lãnh đạo/phòng ban tương ứng với phạm vi ảnh hưởng |

Bảng không áp đặt **một cấu trúc tổ chức mới**. Mục đích là tránh khoảng trống “ai cũng chịu trách nhiệm” nhưng không ai có quyền hành động.

### 13.2. Phân biệt tự quản lý và không có ranh giới

**Self-management** không đồng nghĩa mỗi người làm gì tùy thích. Trong Scrum, Developers tự quyết cách thực hiện để đạt Sprint Goal trong khi Product Owner chịu trách nhiệm tối đa hóa giá trị và Product Backlog; DoD bảo vệ chất lượng.

Trong một mô hình Kanban không dùng Scrum, đội vẫn cần chính sách **chọn item, pull, hạn mức WIP, xử lý ngoại lệ và xác định Done**. Nếu bỏ tất cả vì “tự quản lý”, công việc dễ bị dẫn bởi người phản hồi nhanh nhất thay vì mục tiêu hệ thống.

### 13.3. Quyết định cấp tổ chức không được đẩy xuống đội như trách nhiệm giả

Ví dụ môi trường kiểm thử dùng chung chỉ được cấp quyền mỗi tháng. Developers có thể chỉ ra time spent waiting, thay đổi cách chuẩn bị hoặc phối hợp sớm, nhưng có thể **không có quyền** mua môi trường hoặc đổi chính sách cấp quyền.

Một mô hình kết hợp tốt cần đường xử lý:

1. Đội thu bằng chứng về điểm nghẽn và tác động.
2. Scrum Master/service owner/những người có trách nhiệm hỗ trợ làm rõ vấn đề.
3. Người có thẩm quyền đánh giá lựa chọn và nguồn lực.
4. Chính sách thay đổi được thông báo cho các bên phụ thuộc.
5. Đội đo lại tác động lên cycle time, chất lượng và khả năng giao giá trị.

Việc có một đội Agile không xóa trách nhiệm lãnh đạo đối với **hệ thống tổ chức**.

## 14. Mười hai phản mẫu cần nhận diện sớm

### 14.1. “Chúng ta giữ tên Scrum nhưng bỏ các sự kiện không thích”

**Vấn đề:** loại bỏ Sprint Review, Retrospective hoặc Sprint Goal khi vẫn tuyên bố Scrum nguyên vẹn.

**Hệ quả:** yếu cơ chế kiểm tra, tập trung hoặc cải tiến; mất tính trung thực của tên khung.

**Hướng xử lý:** cải tiến cách thực hiện các thành phần Scrum; nếu chọn một mô hình khác, nêu rõ cơ chế phản hồi và trách nhiệm thay thế.

### 14.2. “Kanban chỉ cần bảng ba cột”

**Vấn đề:** không có ranh giới WIP, chính sách pull, SLE hoặc dữ liệu dòng công việc.

**Hệ quả:** hàng chờ vô hạn, khó dự báo và che thời gian item bị chặn.

**Hướng xử lý:** định nghĩa DoW và cách quản lý WIP, đo WIP/age/throughput/cycle time, kiểm tra hiệu quả.

### 14.3. “TDD, CI và kiểm thử là phần cộng thêm nên có thể bỏ để nhanh”

**Vấn đề:** giao phần mềm thường xuyên nhưng không kiểm chứng hoặc tích hợp đáng tin.

**Hệ quả:** hồi quy, lỗi phát hiện muộn, làm lại và chi phí thay đổi tăng.

**Hướng xử lý:** chọn chiến lược kỹ thuật phù hợp rủi ro; làm rõ điều kiện chất lượng, test và khả năng triển khai.

### 14.4. “Product Owner chỉ là thư ký ghi yêu cầu”

**Vấn đề:** nhiều người giao ưu tiên trực tiếp nhưng không ai chịu trách nhiệm Product Backlog.

**Hệ quả:** mục tiêu mơ hồ, Sprint Goal bị chen ngang, quyết định dựa trên chức vụ.

**Hướng xử lý:** nếu dùng Scrum, làm rõ trách nhiệm Product Owner và quyền quản lý backlog; nếu dùng mô hình khác, xác định người quyết định thứ tự có quyền thật.

### 14.5. “Không cần DoD, chỉ cần khách hàng đồng ý”

**Vấn đề:** chấp nhận nghiệp vụ được dùng thay cho kiểm chứng tích hợp, bảo mật và chất lượng chung.

**Hệ quả:** Done ảo, tăng lỗi và rủi ro phát hành.

**Hướng xử lý:** phân biệt AC, acceptance test, DoD và outcome; không cắt yêu cầu an toàn bắt buộc.

### 14.6. “Giảm họp là bằng chứng quy trình tốt hơn”

**Vấn đề:** loại bỏ trao đổi nhưng thời gian chờ câu hỏi, phụ thuộc hoặc làm lại vẫn cao.

**Hệ quả:** tối ưu giờ họp nhưng giảm hiệu quả phối hợp.

**Hướng xử lý:** đo độ trễ quyết định, kết quả Increment và phản hồi; giữ hoặc thay các cơ chế giao tiếp có chức năng rõ.

### 14.7. “Áp dụng mọi framework cùng lúc sẽ tối ưu”

**Vấn đề:** thêm hàng loạt ceremonies, vai trò và dashboard từ nhiều phương pháp dù không giải quyết một trở ngại cụ thể.

**Hệ quả:** công sức điều phối tăng, trách nhiệm chồng chéo, phát sinh họp thay vì học.

**Hướng xử lý:** ưu tiên **vấn đề → cơ chế nhỏ nhất có ích → thử nghiệm → bằng chứng**.

### 14.8. “Tự quản lý thì ai thích kéo ticket nào cũng được”

**Vấn đề:** thiếu Product Goal, chính sách ưu tiên hoặc ranh giới thẩm quyền.

**Hệ quả:** work items dễ được chọn vì thú vị hoặc nhỏ, không vì giá trị.

**Hướng xử lý:** minh bạch mục tiêu, ưu tiên, điều kiện kéo và trách nhiệm quyết định.

### 14.9. “Release nhanh nghĩa là bỏ kiểm soát”

**Vấn đề:** tăng số lần deploy khi chưa có monitoring, khôi phục, bảo mật hoặc kiểm thử phù hợp.

**Hệ quả:** lỗi hậu triển khai tăng và feedback bị nhiễu bởi sự cố.

**Hướng xử lý:** đầu tư DevOps theo hướng triển khai **an toàn, quan sát được và có thể khôi phục**.

### 14.10. “Hybrid nghĩa là khóa roadmap toàn bộ từ đầu rồi chia Sprint”

**Vấn đề:** mọi quyết định giải pháp và ưu tiên đã cố định, Sprint chỉ là đơn vị báo cáo.

**Hệ quả:** Review và dữ liệu người dùng khó thay đổi kế hoạch; nhóm chỉ làm nhanh hơn một giải pháp có thể sai.

**Hướng xử lý:** phân biệt ràng buộc thật với giả thuyết, giữ một mức linh hoạt cho phạm vi và thứ tự, kiểm tra outcome.

### 14.11. “Scale bằng nhiều tầng phê duyệt và nhiều cuộc họp”

**Vấn đề:** số cuộc họp liên đội tăng, nhưng công việc vẫn bị chặn bởi cùng một API, môi trường hoặc chính sách.

**Hệ quả:** điều phối có vẻ chặt chẽ nhưng cycle time không giảm.

**Hướng xử lý:** phân tích phụ thuộc kỹ thuật và tổ chức, tích hợp sớm, rõ quyền quyết định, chỉ thêm cuộc họp khi giúp giải quyết trở ngại thật.

### 14.12. “Chỉ số tăng là bằng chứng không cần xem chất lượng”

**Vấn đề:** tăng velocity/throughput bằng cách đổi cỡ ticket, đẩy QA ra ngoài workflow hoặc bỏ test.

**Hệ quả:** metric mất khả năng dự báo, người dùng nhận sản phẩm lỗi.

**Hướng xử lý:** cố định định nghĩa Done phù hợp, đọc số đo theo bối cảnh và kiểm tra cùng outcome/chất lượng.

## 15. Quy trình lựa chọn và thử nghiệm một phương án kết hợp

Một đội có thể bắt đầu từ **một trở ngại thật trong dòng giá trị**. Quy trình dưới đây không phải framework mới bắt buộc; nó là cách bảo đảm mỗi quyết định có lý do và bằng chứng.

### Bước 1 — Mô tả một vấn đề cụ thể

Không viết “cần Agile hơn”. Hãy viết:

> “Trong ba Sprint gần đây, nhiều PBI được đánh dấu hoàn tất phần code nhưng chờ tích hợp/QA quá một tuần; phần mềm người dùng có thể dùng không xuất hiện theo nhịp Sprint.”

Vấn đề nên đủ cụ thể để các bên kiểm chứng.

### Bước 2 — Xác định ranh giới và cơ chế đang thiếu

Vẽ luồng từ yêu cầu tới kết quả, xác định:

- Ai sở hữu mục tiêu và thứ tự công việc?
- Đâu là điểm bắt đầu/kết thúc?
- Khi nào item được xem là Done và bằng chứng gì?
- WIP và điểm chờ nằm ở đâu?
- Khi nào người dùng hoặc stakeholder kiểm tra phần mềm?
- Ai có quyền đổi môi trường, quy trình hoặc điều kiện vận hành?

### Bước 3 — Phân loại phần giữ, phần bổ sung, phần bỏ

| Quyết định | Câu hỏi trước khi thực hiện |
|---|---|
| **Giữ** | Thành phần nào đang bảo vệ một cơ chế quan trọng và có bằng chứng hữu ích? |
| **Cải tiến hình thức** | Có thể giảm chi phí thực hiện mà giữ chức năng không? |
| **Bổ sung** | Thực hành mới giải quyết điểm nghẽn nào chưa được xử lý? |
| **Thay thế** | Chức năng cũ sẽ được thay bằng cơ chế nào, với chính sách nào? |
| **Loại bỏ** | Vì sao cơ chế không còn cần trong bối cảnh? Điều gì sẽ xảy ra nếu quyết định sai? |

Nếu đang dùng một khung chính thức như Scrum, phải nói rõ **thay đổi nào chỉ là kỹ thuật tùy chọn và thay đổi nào làm đội rời khỏi định nghĩa Scrum**.

### Bước 4 — Giữ một số guardrails không thương lượng

Ví dụ:

- Không chuyển một hạng mục chưa đạt DoD thành Increment Done.
- Không bỏ kiểm tra bảo mật/phân quyền bắt buộc.
- Không tự ý thay nghĩa vụ hợp đồng hoặc phê duyệt.
- Không làm sai lệch định nghĩa item để tăng throughput.
- Không coi làm thêm giờ liên tục là nguồn năng lực miễn phí.
- Không che giấu sự cố hoặc điểm chặn để giữ dự báo đẹp.

Các guardrails cụ thể phụ thuộc sản phẩm và quy định. Đội cần thống nhất với vai trò có thẩm quyền.

### Bước 5 — Thiết kế thử nghiệm nhỏ, có hạn và có người quyết định

Ví dụ:

> **Giả thuyết:** Nếu giới hạn Development WIP và đưa kiểm thử tích hợp của luồng đăng ký vào sớm, tỷ lệ PBI thật sự đạt DoD trong Sprint sẽ tốt hơn và thời gian chờ Verification giảm.
>
> **Thay đổi:** Trong ba Sprint tới, thử giới hạn Development theo năng lực thực, ghi chính sách blocked, kiểm tra những story gần Done mỗi ngày.
>
> **Bằng chứng:** WIP, work item age, cycle time của các item tương đồng, lỗi hồi quy, Increment đạt DoD và phản hồi người dùng.
>
> **Guardrails:** Không bỏ kiểm thử hoặc đổi DoD để tăng số Done; quản lý sự cố khẩn theo chính sách.
>
> **Người quyết định:** Scrum Team điều chỉnh quy trình nội bộ trong quyền hạn; Product Owner phối hợp về ưu tiên; lãnh đạo hỗ trợ khi cần đổi môi trường hoặc chính sách chung.

### Bước 6 — So sánh với đường cơ sở

Trước khi thay đổi, ghi:

- Dữ liệu flow hiện tại và định nghĩa đơn vị đo.
- Những lỗi, điểm chờ và phụ thuộc lớn.
- Năng lực và tải công việc khẩn.
- Điều kiện người dùng hoặc product outcome đang quan tâm.

Sau thử nghiệm, không chỉ hỏi “con số có tăng không?” mà còn hỏi:

1. Các item có còn so sánh được không?
2. Có thay đổi nhân sự/hạ tầng/loại việc đồng thời không?
3. Chất lượng, an toàn, mức làm thêm giờ có đổi không?
4. Người dùng có nhận kết quả sớm hoặc đúng hơn không?
5. Cơ chế mới có tạo chi phí điều phối vượt lợi ích không?

### Bước 7 — Giữ, sửa, thu hẹp hoặc dừng

Một kết quả cải tiến có thể là:

- **Giữ** nếu có tín hiệu cải thiện và guardrails được bảo vệ.
- **Sửa** chính sách nếu nó lộ điểm nghẽn mới hoặc gây quá tải cục bộ.
- **Thu hẹp** nếu một thực hành chỉ hữu ích cho một loại công việc.
- **Dừng** nếu chi phí vượt lợi ích hoặc ảnh hưởng xấu tới chất lượng.
- **Đưa lên cấp tổ chức** nếu trở ngại cần quyền về hạ tầng, nhân sự hoặc hợp đồng.

Việc dừng một thực hành sau thử nghiệm không phải bằng chứng “Agile thất bại”. Đó có thể là quyết định học được rằng **giả thuyết ban đầu không phù hợp**.

## 16. Mẫu quyết định kết hợp có chủ đích

### 16.1. Phiếu quyết định ngắn

~~~text
TEN THAY DOI:
  [Vi du: Scrum + WIP control + CI cho luong dang ky]

VAN DE / BANG CHUNG:
  [Hanh vi nao dang cham? Du lieu thuc te nao?]

MUC TIEU:
  [Ket qua nguoi dung va nang luc giao hang can cai thien]

KHUNG / THUC HANH DANG DUNG:
  [Scrum / Kanban / XP / mo hinh khac, ten goi trung thuc]

CO CHE CAN GIU:
  [Gia tri, quyen quyet dinh, phan hoi, DoD, WIP, an toan...]

THAY DOI CU THE:
  Giu:
  Bo sung:
  Thay the:
  Loai bo:

NEU LOAI BO MOT CO CHE:
  [Tai sao? Chuc nang con can khong? Thay bang gi?]

CHINH SACH VA VAI TRO:
  [Ai chon uu tien, ai duyet rui ro, ai quan ly workflow?]

GUARDRAILS:
  [Nhung dieu khong duoc ha]

DU LIEU DUONG CO SO:
  [Cycle time, WIP, Increment dat DoD, loi, outcome...]

THU NGHIEM:
  [Pham vi, thoi gian, loai item va nguoi phu trach]

BANG CHUNG MONG DOI:
  [Chi so va quan sat chat luong/nguoi dung]

MOC XEM LAI:
  [Sau bao nhieu chu ky hoac sau bang chung nao]

QUYET DINH TIEP:
  [Giu / sua / dung / can thay doi cap to chuc]
~~~

Mẫu trên chỉ là công cụ thực hành. Không cần tạo thêm một cổng phê duyệt cho mọi quyết định nhỏ. Với thay đổi kỹ thuật ít rủi ro, một bản ghi ngắn có thể đủ; với thay đổi ảnh hưởng bảo mật, hợp đồng hoặc tổ chức, cần sự tham gia đúng thẩm quyền.

### 16.2. Mẫu ma trận cơ chế

| Cơ chế | Cách hiện tại | Thay đổi đề xuất | Chứng minh vẫn hoạt động bằng gì? |
|---|---|---|---|
| Giá trị | Product Goal và phản hồi người dùng | Bổ sung thử nghiệm với học viên | Kết quả tác vụ và thay đổi ưu tiên dựa trên dữ liệu |
| Quyết định | Product Owner sắp Product Backlog | Giữ; làm rõ thời gian phản hồi chuyên gia | Quyết định không bị chờ vô hạn |
| Chất lượng | DoD và kiểm tra theo rủi ro | Thêm integration tests vào CI | Ít lỗi hồi quy, Increment đạt DoD |
| Dòng công việc | Nhiều item cùng bắt đầu | Thử WIP limit và pull policies | Age/cycle time, item blocked, throughput |
| Phản hồi | Sprint Review | Giữ, thêm quan sát người dùng sau release | Bằng chứng outcome và backlog thích ứng |
| Cải tiến | Retrospective | Thêm một phép đo và thử nghiệm mỗi chu kỳ | Quyết định cải tiến được theo dõi tới kết quả |

### 16.3. Cách trình bày cho lãnh đạo

Một báo cáo ngắn có thể viết:

> **Vấn đề:** Các item chờ QA quá lâu nên tính năng không ra được Increment hoàn tất.
>
> **Thay đổi đề xuất:** Giữ Scrum, bổ sung giới hạn WIP và kiểm thử tích hợp sớm từ các thực hành Kanban/XP.
>
> **Vì sao:** Ngăn công việc mới chồng lên bottleneck, phát hiện lỗi trước khi dồn cuối Sprint.
>
> **Không đánh đổi:** Sprint Goal, DoD, phân quyền và những kiểm soát bắt buộc.
>
> **Bằng chứng xem lại:** cycle time của những item tương đồng, tuổi item blocked, số Increment đạt DoD, lỗi sau phát hành và người dùng có hoàn thành tác vụ không.
>
> **Điều cần hỗ trợ từ tổ chức:** quyền tạo môi trường tích hợp hoặc thời gian chuyên gia kiểm chứng.

Thông điệp này giúp phân biệt **giảm thời gian chờ để tạo giá trị** với “cắt bớt quy trình để làm đẹp lịch”.

## 17. Bài tập vận dụng

### Bài tập A — Nhãn Scrum nhưng bỏ cơ chế

Một nhóm giữ Sprint hai tuần và Daily Scrum nhưng bỏ Product Owner vì “mọi người đều hiểu nhu cầu”, bỏ Sprint Review vì “đã gửi báo cáo” và bỏ DoD vì “QA sẽ kiểm tra sau”.

**Yêu cầu:** Xác định những phần Scrum bị loại bỏ, chức năng bị mất và lựa chọn sửa phù hợp.

<details>
<summary>Gợi ý đáp án</summary>

Product Owner là accountability cốt lõi; Sprint Review là sự kiện Scrum; Definition of Done là commitment gắn với Increment. Bỏ chúng làm yếu quyền ưu tiên, kiểm tra giá trị và minh bạch chất lượng, không còn cách thực hành Scrum nguyên vẹn. Nếu muốn dùng Scrum, cần phục hồi/cải thiện các cơ chế: xác định Product Owner thực quyền, Review Increment và học từ phản hồi, DoD thể hiện chất lượng tích hợp. Nếu chọn mô hình khác, phải nêu đúng tên và cơ chế thay thế, không giữ nhãn để che lỗ hổng.

</details>

### Bài tập B — Bảng Kanban đủ đẹp nhưng WIP tăng

Một đội có bảng To Do–Doing–Done. Cột Doing hiện có 24 item, tám item bị blocked được chuyển sang một bảng khác để báo WIP giảm. Nhóm tuyên bố “Kanban không cần quy tắc vì đội tự quản lý”.

**Yêu cầu:** Chỉ ra tối thiểu bốn điều cần làm rõ hoặc sửa để vận hành Kanban có chủ đích.

<details>
<summary>Gợi ý đáp án</summary>

Cần xác định work item types, điểm bắt đầu/kết thúc, trạng thái thực tế, chính sách di chuyển và ưu tiên, cách kiểm soát WIP và SLE. Item blocked đã bắt đầu vẫn tính trong WIP theo ranh giới đã công bố; không được cất khỏi thống kê để tạo năng lực giả. Đội nên đo WIP, work item age, throughput, cycle time và thử giới hạn phù hợp; ưu tiên tháo điểm chặn. Tự quản lý cần chính sách, mục tiêu và trách nhiệm chứ không đồng nghĩa thiếu quy tắc.

</details>

### Bài tập C — XP nhưng chất lượng đến cuối dự án

Đội nói áp dụng XP vì khách hàng trả lời nhanh và mỗi tuần có bản demo. Tuy nhiên, code chỉ tích hợp vào cuối tháng; không có kiểm thử hồi quy phù hợp và mỗi thay đổi thường phá tính năng cũ.

**Yêu cầu:** Vì sao sự cộng tác với khách hàng chưa đủ? Chọn hai hoặc ba năng lực kỹ thuật cần đầu tư sớm.

<details>
<summary>Gợi ý đáp án</summary>

Khách hàng cung cấp phản hồi về giá trị, nhưng nhóm cần sửa phần mềm an toàn và kiểm chứng sớm. Có thể thử tích hợp thường xuyên với CI, xây các test hồi quy cho luồng quan trọng, dùng TDD khi phù hợp, refactoring và chia thay đổi nhỏ. Đánh giá qua lỗi hồi quy, thời gian phát hiện lỗi, Increment đạt chất lượng và khả năng phát hành, không chỉ số buổi demo.

</details>

### Bài tập D — Trộn Scrum và Kanban theo cách hợp lý

Scrum Team có Sprint Goal “Học viên mở được bài đầu sau ghi danh”. Đội dự kiến hoàn tất sáu PBI trong Sprint và muốn giới hạn tối đa hai PBI đang Development.

**Yêu cầu:** Có mâu thuẫn không? Đề xuất cách kéo việc và cơ chế nào vẫn phải giữ.

<details>
<summary>Gợi ý đáp án</summary>

Không mâu thuẫn. Sáu PBI là dự báo các hạng mục có thể hoàn tất trong Sprint; WIP limit hai item kiểm soát số đang triển khai đồng thời. Developers kéo tiếp khi có chỗ và điều kiện phù hợp, ưu tiên hoàn tất item gần Done và giải quyết blocked. Nếu gọi là Scrum, vẫn giữ Product Goal/Sprint Goal/DoD, accountabilities và events. Đo age/cycle time, Increment và chất lượng để kiểm tra hiệu quả.

</details>

### Bài tập E — Giữ kiểm soát bắt buộc mà vẫn Agile

Một tổ chức xử lý dữ liệu học viên yêu cầu kiểm tra phân quyền và bằng chứng phê duyệt trước khi mở rộng triển khai. Nhóm muốn bỏ kiểm soát vì “Agile phải giao nhanh”.

**Yêu cầu:** Đề xuất một cách kết hợp phát triển tăng dần và kiểm soát tuân thủ không dồn mọi thứ về cuối.

<details>
<summary>Gợi ý đáp án</summary>

Làm rõ điều kiện bảo mật/pháp lý ngay khi chọn lát cắt, đưa kiểm chứng phân quyền vào acceptance examples và DoD, chạy test phù hợp liên tục, lưu kết quả theo build/môi trường, chuẩn hóa chứng cứ cho người có thẩm quyền. Giữ phê duyệt thực sự bắt buộc tại mốc phù hợp và phát hành giới hạn khi đủ điều kiện. Mục tiêu là giảm thời gian chờ và phát hiện lỗi muộn, không bỏ bảo vệ dữ liệu.

</details>

### Bài tập F — Chọn mô hình cho đội trực sự cố

Nhóm vận hành nhận việc bất ngờ theo ngày, nhiều sự cố cấp bách; họ vẫn cố đặt Sprint Goal hai tuần nhưng mục tiêu gần như luôn bị gián đoạn. Lãnh đạo hỏi liệu có nên chuyển sang Kanban.

**Yêu cầu:** Nêu những câu hỏi cần xác minh và những cơ chế bắt buộc phải thiết kế nếu chuyển sang hệ thống Kanban.

<details>
<summary>Gợi ý đáp án</summary>

Hỏi loại việc, mức biến động, nghĩa vụ xử lý sự cố, khả năng lập mục tiêu Sprint có ý nghĩa, WIP, điểm chờ, SLE và mục tiêu dịch vụ. Nếu chọn Kanban, định nghĩa workflow (loại item, start/end, trạng thái, WIP control, explicit policies, SLE); chính sách expedite, quyền ưu tiên, đo bốn flow metrics và vòng review/cải tiến. Nếu không còn Sprint, không gọi đó là Scrum đầy đủ. Nếu Sprint Goal vẫn có ích, có thể kết hợp Kanban với Scrum.

</details>

### Bài tập G — Phân biệt metric tốt và metric đối phó

Sau khi “lai Agile”, đội báo số ticket Done tăng từ 15 lên 28 mỗi tuần, nhưng yêu cầu đang chờ người dùng sử dụng lại tăng, lỗi hậu triển khai cũng tăng. Quản lý tuyên bố thay đổi thành công.

**Yêu cầu:** Chỉ ra những thông tin còn thiếu và cách đánh giá đầy đủ hơn.

<details>
<summary>Gợi ý đáp án</summary>

Cần biết định nghĩa Done, cách chia ticket, loại công việc, WIP, cycle time, work item age và nơi công việc chờ. Xem Increment có thật sự tích hợp/kiểm chứng được không, lỗi có nghiêm trọng không và người dùng đạt mục tiêu gì. Thông tin “ticket Done tăng” không đủ để đánh giá giá trị, đặc biệt nếu thay cách đếm hoặc bỏ QA. Cần guardrails về chất lượng và xem lại quyết định với bằng chứng.

</details>

### Bài tập H — Đề xuất thay Daily Scrum bằng báo cáo tự động

Một Scrum Team nói Daily Scrum không có ích vì mỗi người đọc lại task đã cập nhật trong công cụ. Nhóm đề xuất bỏ luôn sự kiện và dùng báo cáo tự động.

**Yêu cầu:** Phân biệt vấn đề về cách tổ chức sự kiện với việc bỏ một thành phần Scrum. Đề xuất thử nghiệm cải thiện.

<details>
<summary>Gợi ý đáp án</summary>

Daily Scrum không nhằm đọc trạng thái từng cá nhân cho quản lý; nó giúp Developers kiểm tra tiến triển hướng Sprint Goal và điều chỉnh Sprint Backlog. Có thể chuẩn bị dữ liệu trước, dùng 15 phút nhìn item gần Done, blockers, rủi ro và kế hoạch chung. Báo cáo tự động hỗ trợ minh bạch nhưng không tự thay chức năng phối hợp của sự kiện Scrum. Nếu tổ chức thật sự chuyển sang mô hình khác, phải xác định cơ chế kiểm tra/điều chỉnh thay thế và mô tả đúng tên khung.

</details>

### Bài tập I — Phân tích một đề xuất “hybrid mới”

Nhóm đề nghị kết hợp:

1. Scrum để tạo Sprint Goal và nhịp Review.
2. Kanban để giới hạn WIP.
3. XP để có TDD, CI và refactoring.
4. Product discovery để kiểm chứng mục tiêu trước khi đầu tư lớn.
5. Kiểm soát phát hành có chứng cứ theo yêu cầu an toàn.

**Yêu cầu:** Viết một giả thuyết cải tiến và tối thiểu năm tín hiệu đánh giá. Nêu hai cách kết hợp vẫn có thể thất bại dù nghe rất hợp lý.

<details>
<summary>Gợi ý đáp án</summary>

Giả thuyết có thể là “khi kiểm soát WIP, kiểm thử/tích hợp sớm và review với người dùng, nhóm giảm thời gian đến Increment đạt DoD và phát hiện giả thuyết giá trị sai sớm hơn”. Tín hiệu: WIP, work item age, cycle time, số Increment đạt DoD, lỗi hồi quy, độ trễ quyết định ưu tiên, outcome người dùng, mức tuân thủ. Hai nguy cơ: chồng thêm rất nhiều nghi thức khiến không ai còn thời gian phát triển; hoặc Product Owner thiếu quyền và QA/DevOps thiếu hạ tầng nên mọi cơ chế chỉ tồn tại trên giấy. Cần thử nhỏ, người có quyền và mốc xem lại.

</details>

## 18. Checklist tự đánh giá một mô hình Agile kết hợp

Hãy chọn **một sản phẩm hoặc dòng công việc cụ thể** và trả lời bằng bằng chứng:

1. Nhóm đang giải quyết vấn đề gì và mục tiêu người dùng nào?
2. Tại sao nhóm chọn kết hợp, thay vì chỉ cải tiến một khung hiện tại?
3. Những phần nào là **thành phần cốt lõi chính thức**, những phần nào là kỹ thuật tùy chọn?
4. Nếu nói “dùng Scrum”, nhóm có giữ Scrum Team accountabilities, events, artifacts và commitments không?
5. Nếu nói “dùng Kanban”, nhóm có Definition of Workflow, kiểm soát WIP, chính sách rõ và SLE không?
6. Những thực hành XP/engineering được chọn có đáp ứng rủi ro kỹ thuật đang quan sát không?
7. Ai chịu trách nhiệm mục tiêu và thứ tự ưu tiên, ai chịu trách nhiệm năng lực và cách triển khai?
8. Có một cách giải quyết xung đột ưu tiên giữa stakeholders không?
9. Mỗi khi bỏ một thực hành, nhóm có ghi **chức năng của nó** và cách bảo vệ chức năng đó không?
10. Các thay đổi có tạo thêm tầng họp, phê duyệt hoặc báo cáo không cần thiết không?
11. Một item được coi Done theo điều kiện nào, có bằng chứng kiểm chứng thực tế không?
12. Các rủi ro bảo mật, dữ liệu, an toàn và tuân thủ bắt buộc có được giữ không?
13. Có cơ chế kiểm tra outcome thay vì chỉ đếm output/ticket không?
14. Các quyết định sản phẩm có thay đổi khi phản hồi mới xuất hiện không?
15. Có kiểm soát số công việc bắt đầu để tránh tồn đọng quá mức không?
16. Item bị chặn có vẫn hiển thị trong WIP và dữ liệu thời gian không?
17. WIP, throughput, work item age và cycle time có định nghĩa nhất quán không?
18. Các metric có bị sử dụng để xếp hạng hoặc ép năng suất cá nhân không?
19. Nhóm có khả năng tích hợp, kiểm thử và phát hành phần mềm nhỏ một cách đáng tin không?
20. Kiểm soát vận hành có giúp giảm rủi ro mà không dồn mọi kiểm tra về cuối không?
21. Các phụ thuộc liên đội hoặc đối tác có người chịu trách nhiệm và đường tháo chặn không?
22. Khi có yêu cầu khẩn, có chính sách ưu tiên/đánh đổi và thẩm quyền tương ứng không?
23. Những thay đổi quy trình có đường cơ sở, giả thuyết và mốc xem lại không?
24. Nếu một thử nghiệm không hiệu quả, đội có quyền dừng hoặc điều chỉnh không?
25. Có đang nhầm **ít sự kiện hơn** với **phản hồi tốt hơn**, hoặc **nhiều framework hơn** với **hiệu quả hơn** không?
26. Khi xem bằng chứng chất lượng và kết quả người dùng, nhóm có sẵn sàng thay đổi cách làm đã trở thành thói quen không?

Nếu chưa trả lời được nhiều câu, đừng vội thêm một “Agile framework” mới. Hãy tìm **một cơ chế quan trọng đang bị đứt** — chẳng hạn chất lượng hoàn tất, quyền ưu tiên, quản lý WIP hoặc phản hồi người dùng — rồi thiết kế **một thay đổi nhỏ có thể kiểm tra**.

## 19. Tổng kết

- **Kết hợp có chủ đích** bắt đầu từ vấn đề thật, xác định cơ chế cần giữ, thực hành bổ sung, người quyết định, guardrails và bằng chứng xem lại.
- **Cắt bỏ tùy tiện** thường xuất hiện khi đội bỏ những phần khó hoặc làm lộ vấn đề — DoD, Review, WIP control, kiểm thử, minh bạch phụ thuộc — mà không có cách bảo vệ chức năng tương đương.
- **Tên khung cần được dùng trung thực.** Scrum có các accountability, events, artifacts và commitments; Kanban cần Definition of Workflow và thực hành quản lý flow. Những kỹ thuật tùy chọn không phải quy định chính thức của khung.
- **Scrum, Kanban, XP, Lean, DevOps và product discovery có thể bổ sung cho nhau** vì giải quyết các chức năng khác nhau: định hướng và kiểm tra, dòng công việc, chất lượng kỹ thuật, loại bỏ lãng phí, vận hành an toàn và xác nhận nhu cầu.
- **Không có công thức kết hợp tốt nhất cho mọi đội.** Đặc điểm công việc, mức biến động, rủi ro, phụ thuộc, quyền hạn và năng lực kỹ thuật quyết định lựa chọn phù hợp.
- **Chất lượng và nghĩa vụ bắt buộc không phải phần tùy chọn để đổi lấy tốc độ.** Có thể thương lượng phạm vi, chia lát cắt và cải thiện cách kiểm chứng, nhưng không được gọi sản phẩm chưa an toàn là hoàn tất.
- **Đo tác dụng ở nhiều lớp:** outcome người dùng, flow metrics và Increment đạt chất lượng. Đừng kết luận chỉ từ số ticket, story point hoặc số giờ họp.
- **Tổ chức cũng phải thay đổi khi cần.** Không một cách ghép phương pháp nào tự giải quyết quyền ưu tiên thiếu rõ, phụ thuộc môi trường hoặc phê duyệt nằm ngoài năng lực của đội.
- **Mỗi điều chỉnh nên có khả năng học từ thực tế.** Ghi lý do, thử trong phạm vi phù hợp, xem guardrails và quyết định giữ, sửa hoặc dừng.

Khi ai đó đề nghị “bỏ một bước để Agile hơn”, hãy hỏi:

> **“Bước này đang bảo vệ điều gì? Nếu bỏ đi, mục tiêu, chất lượng, phản hồi, quyền quyết định hoặc khả năng hoàn tất có bị mất không? Chúng ta sẽ giữ chức năng ấy bằng cách nào và bằng chứng nào sẽ chứng minh cách mới tốt hơn?”**

Khả năng trả lời minh bạch những câu hỏi đó — chứ không phải số tên framework xuất hiện trên slide — là dấu hiệu của một **phương án kết hợp có chủ đích**.

## Tài liệu tham khảo định hướng

- [Manifesto for Agile Software Development](https://agilemanifesto.org/): các giá trị nền tảng về tương tác, phần mềm hoạt động, hợp tác khách hàng và phản hồi thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html): giao phần mềm thường xuyên, phát triển bền vững, chú trọng chất lượng kỹ thuật và cải tiến liên tục.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html): các accountability, events, artifacts, commitments, lý thuyết Scrum và ranh giới của khung.
- [The Kanban Guide](https://kanbanguides.org/the-kanban-guide/): Definition of Workflow, WIP, explicit policies, SLE, throughput, cycle time và work item age.
- [Scrum with Kanban — Scrum.org](https://www.scrum.org/resources/kanban-guide-scrum-teams): nguồn tham khảo về bổ sung các thực hành Kanban nhằm tối ưu flow trong Scrum.
- **Kent Beck & Cynthia Andres, _Extreme Programming Explained: Embrace Change_ (ấn bản thứ hai)**: giá trị, nguyên tắc và thực hành XP; sự kết hợp giữa phản hồi khách hàng và kỹ thuật.
- [DORA](https://dora.dev/): tài liệu nghiên cứu và thực hành về năng lực giao phần mềm và vận hành, hữu ích khi kiểm tra hiệu quả kỹ thuật.
- [Agile Alliance — Agile Glossary](https://agilealliance.org/agile101/agile-glossary/): thuật ngữ Agile, các thực hành và khái niệm hỗ trợ lựa chọn phương pháp.
- [Cucumber — Gherkin Reference](https://cucumber.io/docs/gherkin/reference/): định dạng ví dụ hành vi Given–When–Then để hỗ trợ trao đổi và kiểm chứng acceptance criteria.
