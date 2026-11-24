# Thiết kế thử nghiệm để kiểm chứng cách tiếp cận phù hợp với nhóm

> **Chương:** Lựa chọn cách tiếp cận  
> **Học phần:** **AGILE_DEVELOPMENT** — hiểu giá trị và nguyên tắc Agile trong phát triển phần mềm thích ứng qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc để lựa chọn cách phối hợp phù hợp.

Một nhóm phát triển nền tảng đặt lịch tư vấn muốn “làm Agile tốt hơn”. Có người đề nghị áp dụng **Scrum** để nhóm tập trung vào mục tiêu và gặp người dùng đều đặn. Người khác muốn dùng **Kanban** vì yêu cầu hỗ trợ và lỗi production đến liên tục, khiến Sprint thường bị ngắt. Một Developer muốn đưa **TDD và Continuous Integration** theo tinh thần **Extreme Programming (XP)** vào công việc vì kiểm thử hồi quy mất nhiều ngày. Quản lý muốn chọn ngay một framework “chuẩn” và áp dụng cho tất cả nhóm.

Nhưng **tên phương pháp không phải bằng chứng rằng nó phù hợp**. Nếu vấn đề lớn nhất là bản thân nhóm không biết thứ tự giá trị sản phẩm, chỉ đặt WIP limit có thể không đủ. Nếu vấn đề là lỗi tích hợp phát hiện muộn, tổ chức Sprint Review đẹp hơn vẫn không làm test tự động xuất hiện. Nếu nhóm phải ứng cứu hàng ngày, việc cố khóa mọi yêu cầu vào Sprint có thể tạo nhiều ngoại lệ hơn khả năng học.

Một cách lựa chọn có trách nhiệm là coi phương pháp như **tập hợp giả thuyết có thể kiểm chứng**: trong bối cảnh này, thay đổi cách lập kế hoạch, luồng công việc, phản hồi hoặc kỹ thuật có khả năng cải thiện kết quả nào? Ta có thể thử **ở đâu, trong bao lâu, với bằng chứng gì và những rủi ro không được phép đánh đổi**?

**Thông điệp trung tâm:** Đừng hỏi trước “Scrum hay Kanban tốt hơn?”. Hãy hỏi **“Nhóm đang gặp giới hạn nào khi tạo giá trị, can thiệp nào có cơ chế hợp lý để giảm giới hạn đó, và bằng chứng nào sẽ khiến chúng ta giữ hoặc thay đổi cách tiếp cận?”**

Các ví dụ và số liệu trong bài mang tính **giả định để học cách thiết kế thử nghiệm**, không phải khảo sát thực tế hay công thức bảo đảm thành công.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **mục tiêu cải thiện, vấn đề hiện tại, giả thuyết nguyên nhân, phương pháp và thực hành cụ thể**.
2. Mô tả những điều kiện khiến **Scrum, Kanban, XP hoặc phối hợp các thực hành** có thể đáng thử mà không khẳng định chúng là lời giải phổ quát.
3. Xác lập **baseline** cho outcome người dùng, flow, chất lượng, khả năng học và nhịp làm việc trước khi đổi phương pháp.
4. Viết một **giả thuyết có thể bị bác bỏ** về một cơ chế cụ thể như Sprint Goal, WIP limit, review nhịp đều, CI hoặc TDD.
5. Thiết kế **thử nghiệm có ranh giới**, định nghĩa loại việc, người tham gia, thời gian, mức phơi nhiễm, việc giữ nguyên, điều kiện dừng và trách nhiệm quyết định.
6. Chọn **chỉ số chính, chỉ số toàn hệ thống, guardrails và dữ liệu định tính**, tránh tối ưu riêng velocity hay số ticket.
7. Nhận diện những yếu tố làm sai kết luận: **mẫu nhỏ, mùa vụ, công việc không đồng nhất, lựa chọn mẫu, đổi nhiều biến và khác biệt năng lực nhóm**.
8. Dùng **Plan–Do–Study–Act (PDSA)** để xem kết quả, sửa giả thuyết, duy trì, mở rộng hoặc dừng phương pháp thử.
9. Thực hành thiết kế một pilot có thể triển khai với một nhóm phát triển sản phẩm, nhóm vận hành có nhiều ngắt việc hoặc nhóm gặp khó về chất lượng kỹ thuật.

## 2. Vì sao chọn phương pháp bằng thói quen dễ thất bại?

### 2.1. Một framework không phải mục tiêu

| Cách đặt vấn đề chưa đủ | Câu hỏi về kết quả đáng quan tâm |
| --- | --- |
| “Chúng ta phải chạy Scrum hai tuần.” | Có cần một nhịp để tập trung vào mục tiêu, tạo Increment và kiểm tra với stakeholder không? |
| “Chúng ta phải bỏ Sprint chuyển sang Kanban.” | Dòng công việc có liên tục, nhiều ngắt việc và khó dự báo? Giới hạn WIP có giảm chờ không? |
| “Chúng ta cần pair programming toàn thời gian.” | Có lỗi, chậm review hoặc nút thắt tri thức nào mà pairing đúng chỗ có thể cải thiện? |
| “Nhóm khác deploy mỗi ngày nên chúng ta cũng phải thế.” | Chúng ta có bảo đảm test, rollback/đối soát và độ tin cậy phù hợp để giao nhỏ thường xuyên không? |
| “Chọn phương pháp có velocity cao nhất.” | Người dùng có nhận giá trị nhanh hơn mà chất lượng và nhịp bền vững không giảm không? |

**Thực hành chỉ có ích khi gắn với một cơ chế và một vấn đề.** Sprint Planning không thay thế quyền Product Owner; Kanban board không tự giảm WIP; viết nhiều unit test không chứng minh hành vi tích hợp an toàn.

### 2.2. Đừng coi lựa chọn là cuộc bỏ phiếu phong cách làm việc

Một nhóm có thể thích sự rõ ràng của Sprint Goal, nhóm khác thích khả năng kéo công việc khi rảnh. Những cảm nhận này **quan trọng** vì tính khả thi và mức chấp nhận quyết định cách làm có được thực hiện thật không. Nhưng cần đối chiếu chúng với:

- Loại và tốc độ xuất hiện công việc.
- Mức biến động, yêu cầu khẩn và hậu quả trì hoãn.
- Giá trị người dùng/khách hàng và độ dài vòng phản hồi.
- Năng lực kỹ thuật, kiểm thử, tích hợp và phát hành.
- Phụ thuộc liên nhóm và quyền ưu tiên sản phẩm.
- Nhu cầu dự báo và mức độ ổn định của mục tiêu ngắn hạn.
- Rủi ro chất lượng, dữ liệu, pháp lý và nghĩa vụ vận hành.

**Ý kiến số đông không tự chứng minh nhân quả.** Một cách làm nhiều người thích nhưng tăng lỗi production hoặc che blocked time vẫn phải được xem lại.

### 2.3. Phân biệt lựa chọn ở ba tầng

1. **Mục tiêu và nguyên tắc:** Tăng phản hồi sớm, giao nhỏ, hợp tác, giữ chất lượng và cải tiến liên tục. Đây là định hướng Agile.
2. **Khung phối hợp:** Dùng Scrum để kiểm tra/thích ứng qua các sự kiện và commitments; dùng Kanban để quản lý dòng; có thể dùng workflow khác phù hợp.
3. **Kỹ thuật thực thi:** TDD, CI, refactoring, pairing, contract tests, feature toggles và cách phát hành an toàn.

Nhóm có thể áp dụng **Scrum và đồng thời thực hành Kanban/XP**. Không nhất thiết chỉ được chọn đúng một nhãn. Tuy nhiên, nếu gọi một cách làm là **Scrum**, cần hiểu và áp dụng các thành phần thiết yếu của Scrum theo Scrum Guide; bỏ vai trò, sự kiện hoặc commitments quan trọng rồi vẫn tuyên bố “Scrum chuẩn” dễ gây hiểu sai.

### 2.4. Việc không chọn một framework ngay cũng là lựa chọn có thể kiểm chứng

Một nhóm mới hình thành, công việc chưa được phân loại và dữ liệu flow thiếu có thể bắt đầu bằng:

- Định nghĩa công việc và Product Goal.
- Nhìn thấy work item từ đầu đến cuối.
- Thu baseline trong một khoảng phù hợp.
- Thiết lập kiểm thử và điều kiện chất lượng tối thiểu.
- Phỏng vấn người dùng/stakeholder để hiểu giá trị.

Sau đó mới thử một can thiệp có khả năng tạo khác biệt. **Không phải trì hoãn vô hạn**; đây là làm đủ rõ câu hỏi trước khi áp cả bộ nghi thức.

## 3. Đọc bối cảnh nhóm trước khi chọn giả thuyết

### 3.1. Sáu chiều bối cảnh

| Chiều | Cần quan sát | Hướng thử nghiệm có thể hợp lý |
| --- | --- | --- |
| **Đặc điểm nhu cầu** | Việc đến thành đợt hay liên tục? Có nhiều yêu cầu khẩn? | Sprint Goal/cadence nếu cần hướng tập trung; Kanban flow nếu đến liên tục và cần ưu tiên linh hoạt. |
| **Độ rõ của giá trị** | Có Product Goal và backlog có thứ tự? Có stakeholder phản hồi được? | Tăng hợp tác, refinement, Review và discovery trước khi tối ưu tốc độ. |
| **Nút thắt flow** | Công việc nằm chờ review/test/deploy? WIP cao? | Workflow minh bạch, WIP limits, explicit policies và quản lý blocked. |
| **Chất lượng kỹ thuật** | Lỗi hồi quy, tích hợp muộn, build không ổn định? | TDD, CI, refactoring, pairing/contract tests, nhỏ hóa thay đổi. |
| **Phụ thuộc và quyền** | Có phải xin duyệt mọi thay đổi? Một người giữ kiến thức? | Làm rõ decision rights, hợp đồng API, kỹ năng đa chức năng và đường gỡ chặn. |
| **Mức rủi ro** | Hệ thống giao dịch, dữ liệu nhạy cảm, release khó đảo ngược? | Điều kiện DoD/test/giám sát và thay đổi giới hạn; không thí điểm bằng cách bỏ kiểm soát. |

**Không có cột nào tương đương quy tắc “nếu X thì bắt buộc dùng Y”.** Đây là các chỉ báo giúp hình thành giả thuyết thử.

### 3.2. Chọn một đơn vị công việc đủ rõ

Trước khi so cách làm, cần phân biệt:

- **Feature/user story:** Khả năng người dùng hoặc hệ thống nhận được.
- **Bug:** Hành vi sai đã có, có thể cần ứng cứu nếu nghiêm trọng.
- **Discovery/spike:** Công việc giảm bất định, đầu ra là bằng chứng/quyết định.
- **Nợ kỹ thuật/cải tiến kỹ thuật:** Công việc giúp thay đổi nhanh hoặc an toàn hơn.
- **Vận hành/support:** Công việc đến liên tục, có thể có SLA, mức khẩn.

Nếu chỉ đếm ticket, một spike hai ngày và một epic ba tháng đều là **một mục**, làm throughput và cycle time khó so. Nhóm cần phân loại hoặc thu hẹp phạm vi đo.

### 3.3. Hình dung hai loại dòng công việc khác nhau

**Nhóm tính năng sản phẩm:** Thường có Product Goal, cần kiểm tra với stakeholder và nhiều lát cắt cần hợp tác trước khi phát hành. Nhóm có thể thử Sprint Goal/Sprint Review để tập trung và nhận phản hồi.

**Nhóm ứng cứu/nền tảng:** Có việc đến bất ngờ, mức nghiêm trọng và chính sách phản ứng khác nhau. Họ có thể thử trực quan hóa dòng và WIP limit, kết hợp chính sách riêng cho sự cố; không thể đợi hết Sprint nếu production đang gặp lỗi nghiêm trọng.

**Cả hai vẫn cần chất lượng kỹ thuật.** Cũng không có nghĩa nhóm vận hành không thể dùng Scrum hoặc nhóm feature không thể dùng Kanban.

### 3.4. Bối cảnh sẽ thay đổi theo thời gian

Một nhóm ban đầu tập trung làm MVP có thể cần nhịp phản hồi sản phẩm; khi có nhiều khách, tỷ lệ công việc hỗ trợ/sự cố tăng, nhóm có thể cần điều chỉnh cách quản lý flow. Ngược lại, một nhóm vận hành ổn định hơn có thể đầu tư nhiều công việc roadmap có mục tiêu dài hơn.

**Không coi lựa chọn phương pháp là hợp đồng vĩnh viễn.** Nên định nghĩa mốc xem lại theo **loại nhu cầu, kết quả và rủi ro**, không đổi phương pháp hàng tuần theo xu hướng.

## 4. Những điều thực sự được thử trong Scrum, Kanban và XP

### 4.1. Scrum: một khung empiricism với các trách nhiệm, sự kiện và commitments

Theo *Scrum Guide 2020*, Scrum là framework nhẹ giúp nhóm tạo giá trị qua các giải pháp thích ứng cho vấn đề phức tạp. Điểm thiết yếu gồm:

- **Scrum Team:** Product Owner, Scrum Master và Developers.
- **Scrum events:** Sprint bao trùm Sprint Planning, Daily Scrum, Sprint Review và Sprint Retrospective.
- **Scrum artifacts/commitments:** Product Backlog/Product Goal; Sprint Backlog/Sprint Goal; Increment/Definition of Done.
- **Sprint:** Độ dài cố định tối đa một tháng; Sprint mới bắt đầu ngay sau Sprint trước.
- **Increment:** Phải đủ điều kiện chất lượng theo DoD; có thể tạo nhiều Increment và phát hành trong Sprint.

Nếu nhóm muốn kiểm chứng Scrum, họ cần triển khai đủ các yếu tố cần thiết để có thể đánh giá cơ chế **minh bạch, kiểm tra và thích ứng**. Chỉ thêm buổi Daily Scrum rồi ghi “đã thử Scrum” là **chưa đủ**.

**Câu hỏi thử:** “Một Sprint Goal rõ và các cơ hội review/retro theo nhịp có giúp chúng ta hoàn tất lát cắt giá trị và học từ stakeholder sớm hơn không?”

### 4.2. Kanban: chiến lược quản lý dòng chứ không chỉ là bảng cột

Kanban tập trung vào **xác định và trực quan hóa workflow, quản lý WIP, các chính sách rõ, quản lý flow và cải tiến qua phản hồi**. Những thước đo flow cơ bản thường gồm:

- **WIP:** Số work items đã bắt đầu nhưng chưa kết thúc theo ranh giới workflow.
- **Throughput:** Số work items hoàn tất trong khoảng thời gian.
- **Cycle time:** Thời gian từ điểm bắt đầu tới điểm hoàn tất của item.
- **Work item age:** Thời gian item còn đang mở đã nằm trong workflow.
- **Service Level Expectation (SLE):** Kỳ vọng thời gian cho work item với xác suất/điều kiện phù hợp, thường dựa trên dữ liệu flow lịch sử.

**Câu hỏi thử:** “Nếu giới hạn việc đang làm và ưu tiên hoàn tất trước khi bắt đầu mới, thời gian chờ và tính dự báo có cải thiện mà mức ứng cứu/độ tin cậy vẫn được giữ không?”

Kanban **không bắt buộc phải bỏ Sprint**. Một Scrum Team có thể dùng các thực hành Kanban để cải thiện flow, miễn không hiểu nhầm chúng thay thế thành phần cốt lõi của Scrum.

### 4.3. XP: kiểm tra năng lực thay đổi phần mềm an toàn

Extreme Programming nhấn mạnh những thực hành kỹ thuật và cộng tác giúp giữ phản hồi nhanh, chất lượng và khả năng thay đổi, như:

- **Test-Driven Development (TDD)** khi phù hợp.
- **Continuous Integration (CI)** và tự động kiểm tra thường xuyên.
- **Refactoring** để giữ thiết kế dễ sửa.
- **Pair programming** và chia sẻ tri thức.
- **Small releases** và phản hồi khách hàng thường xuyên.
- **Collective code ownership** trong ranh giới trách nhiệm phù hợp.

**Câu hỏi thử:** “Nếu áp dụng TDD và tích hợp sớm trên một luồng dễ lỗi, số hồi quy và thời gian sửa sai có giảm mà tốc độ giao giá trị bền vững không suy giảm không?”

Không cần coi tất cả thực hành XP là **một gói đồng thời phải triển khai trong một tuần**. Để đánh giá một thực hành kỹ thuật, cần nói rõ **điều gì đang được thử**, quan hệ với cách làm hiện tại và tiêu chuẩn kiểm thử/đào tạo.

### 4.4. Phối hợp thực hành: chọn cơ chế, không chọn thương hiệu

Một nhóm có thể:

1. Dùng **Scrum** cho Product Goal, Sprint Goal và các điểm kiểm tra thích ứng.
2. Dùng **Kanban** để làm rõ workflow và kiểm soát WIP, blocked, cycle time.
3. Dùng **XP** để cải thiện TDD, CI và khả năng refactor.

Đây là **cách phối hợp thực hành có chủ đích**, không có nghĩa cứ gọi tên “hybrid” là giải quyết được xung đột. Cần nêu rõ:

- Ai quyết định giá trị, thứ tự và phần việc?
- Khi có việc khẩn, chính sách ứng cứu và điều chỉnh kế hoạch là gì?
- Những điểm kiểm tra và cam kết nào đang dùng?
- Định nghĩa Done/finish và chuẩn chất lượng nào áp dụng?
- Khi các thực hành xung đột, nguyên tắc quyết định là gì?

Các nhãn như **Scrumban** có thể hữu ích để giao tiếp, nhưng không phải một đặc tả duy nhất đủ để biết cách nhóm đang làm.

## 5. Bắt đầu từ kết quả cần cải thiện, không từ framework cần quảng bá

### 5.1. Một phát biểu vấn đề có thể đo

Mẫu:

> “Trong [phạm vi, thời gian], [loại công việc/người dùng] đang gặp [triệu chứng], dẫn tới [tác động], theo [nguồn bằng chứng]. Chúng tôi nghi ngờ [cơ chế], nhưng cần kiểm chứng trước khi quyết định thay cách làm.”

Ví dụ:

> “Trong bốn tuần gần đây, các yêu cầu sửa lỗi nhỏ của luồng đặt lịch có thời gian chờ review/test dài hơn thời gian xử lý. Nhiều work items vẫn đang mở dù Developers tiếp tục bắt đầu việc mới. Chúng tôi nghi ngờ WIP cao góp phần kéo dài cycle time và muốn thử chính sách kéo việc trong một workflow xác định.”

**Tốt hơn** câu “Kanban chắc chắn sẽ làm nhóm nhanh hơn”: phát biểu vấn đề không giả định sẵn kết luận.

### 5.2. Phân biệt triệu chứng, nguyên nhân và can thiệp

| Thành phần | Ví dụ |
| --- | --- |
| **Triệu chứng** | Cycle time của một loại PBI tăng; review chờ nhiều ngày. |
| **Tác động** | Phản hồi khách được xử lý muộn, nhiều lỗi lặp lại. |
| **Giả thuyết nguyên nhân** | Nhóm bắt đầu quá nhiều việc, review/test không đủ năng lực tiếp nhận. |
| **Can thiệp giả định** | Giới hạn WIP, xem age hằng ngày và ưu tiên hoàn tất trước. |
| **Dự đoán** | Waiting time và cycle time giảm, throughput ít nhất không xấu đi đáng kể. |
| **Guardrails** | Không trì hoãn incident khẩn, không giảm DoD, không tăng lỗi nghiêm trọng. |

Một vấn đề thường có **nhiều nguyên nhân**. Nếu WIP limit không cải thiện flow, có thể do phụ thuộc API, quyền môi trường hoặc kích thước PBI quá lớn; không nhất thiết “Kanban đã thất bại ở mọi bối cảnh”.

### 5.3. Đặt outcome của người dùng bên cạnh outcome của nhóm

**Outcome sản phẩm:** Khách có thể đặt/tra cứu lịch đúng và ít phải gọi hỗ trợ.

**Outcome flow:** Nhóm giao các lát cắt đã tích hợp nhanh và dự báo tốt hơn.

**Outcome chất lượng:** Không tăng lỗi tạo lịch trùng, sự cố, rollback, vi phạm quyền dữ liệu.

**Outcome năng lực:** Developers có thể giữ nhịp bền vững, hiểu Product Goal và tự tháo trở ngại trong ranh giới thích hợp.

Một thử nghiệm chỉ làm bảng công việc đẹp hơn nhưng không cải thiện **khả năng giao giá trị thật** cần được xem lại.

### 5.4. Chọn một giới hạn có khả năng tác động

Nếu người dùng chưa biết họ cần gì, WIP thấp chưa tự giải quyết **sai nhu cầu**. Nếu nhóm đã hiểu nhu cầu nhưng kiểm thử thường hỏng, thêm Sprint Review chưa thay bộ test. Nếu production liên tục có incident, mục tiêu chỉ là tăng số feature có thể chuyển chi phí sang hỗ trợ.

**Chọn can thiệp gần giới hạn có bằng chứng nhất**. Khi chưa biết giới hạn, một **thử nghiệm quan sát/discovery ngắn** có thể có giá trị hơn đổi framework toàn diện.

## 6. Thu baseline trước khi thay đổi

### 6.1. Baseline để so với điều gì?

Baseline là mô tả hiện trạng đủ rõ về **kết quả, dòng công việc, chất lượng và cách làm** trước khi thử. Cần:

- **Cửa sổ thời gian:** Ví dụ bốn tới sáu tuần, nhưng phụ thuộc tốc độ xuất hiện hạng mục.
- **Phạm vi:** Một team, loại việc nào, hệ thống/luồng nào?
- **Ranh giới start/finish:** Khi nào một item được tính bắt đầu/hoàn thành?
- **Đơn vị:** Ticket, user story, yêu cầu hỗ trợ, phiên người dùng?
- **Loại trừ:** Những loại việc nào không so chung, ví dụ incident khẩn?
- **Số lượng và phân bố:** Có bao nhiêu trường hợp, có đuôi dài, blocked không?
- **Chất lượng số liệu:** Board/timestamps có đầy đủ và nhất quán không?

### 6.2. Ví dụ bảng baseline nhiều chiều

Giả sử một nhóm hỗn hợp feature và bug đã phân loại **bug không nghiêm trọng** trong bốn tuần. Số liệu giả định:

| Chỉ số | Baseline minh họa | Câu hỏi cần kiểm tra |
| --- | ---: | --- |
| Bug đủ điều kiện hoàn tất | 24 item / 4 tuần | Các bug có cùng ranh giới workflow và mức độ không? |
| Throughput | 6 item/tuần | Có mùa vụ hoặc nhóm loại việc rất khác nhau không? |
| WIP trung bình của dòng đo | 18 item | Có nhiều việc đã started nhưng đang chờ? |
| Cycle time trung bình | 15 ngày làm việc | Phân bố và các trường hợp quá lâu ra sao? |
| Work item age lớn nhất ở cuối kỳ | 21 ngày | Item còn mở này bị chặn ở đâu? |
| Blocked do review/môi trường | 8 item trong kỳ | Mất bao lâu, nguyên nhân thật là gì? |
| Sự cố nghiêm trọng liên quan | 1 | Mức ảnh hưởng/khả năng phục hồi ra sao? |
| Phản hồi nhóm | “Khó hoàn tất, thường chuyển ngữ cảnh” | Có quan sát thực và nhiều góc nhìn không? |

**Không suy từ một con số bình quân rằng mọi item phải mất đúng 15 ngày.** Cần xem phân bố, công việc còn mở và sự khác biệt loại việc.

### 6.3. Little’s Law là mô hình, không phải mục tiêu KPI

Trong một workflow **đủ ổn định và cùng ranh giới**, quan hệ trung bình là:

\[
\text{WIP trung bình}=\text{Throughput trung bình}\times\text{Thời gian trung bình trong hệ thống}
\]

Với WIP 18 item và throughput 6 item/tuần, thời gian trung bình xấp xỉ **3 tuần/item**, tương đương **15 ngày làm việc** nếu dùng năm ngày làm việc mỗi tuần và dữ liệu thỏa điều kiện mô hình.

Đây là một cách **kiểm tra tính nhất quán của dữ liệu và hiểu quan hệ hàng đợi**, không chứng minh cứ đặt WIP limit = 10 thì mọi việc sẽ xong trong một tuần. Hệ thống có thể biến động, loại việc khác nhau và thời gian chờ có đuôi dài.

### 6.4. Đừng chỉ tính những item đã Done

Một thử nghiệm có thể cho throughput tăng nhờ nhóm đóng các ticket dễ, trong khi **mười ticket khó nằm lâu hơn ở Blocked**. Vì vậy cần theo dõi:

- **Work item age** và vị trí của item còn mở.
- Tỷ lệ/cường độ blocked và loại phụ thuộc.
- Các item bị reopen/rework.
- Số việc mới bắt đầu so với số việc kết thúc.
- Phân bố cycle time của việc hoàn tất.

Nếu nhóm chỉ xem Done, họ có thể tuyên bố thắng lợi trong khi **nợ công việc chưa hoàn tất tăng**.

### 6.5. Baseline có thể là dữ liệu định tính khi chưa đủ số liệu

Nhóm mới chưa có lịch sử ticket đáng tin có thể bắt đầu bằng:

1. Quan sát một số ngày làm việc và ghi điều làm họ phải dừng.
2. Phỏng vấn Product Owner, Developers, người hỗ trợ và stakeholder.
3. Vẽ sơ bộ workflow và điểm chờ.
4. Định nghĩa cách ghi dữ liệu đúng ngay từ thử nghiệm.
5. Nói rõ **chưa có baseline định lượng đủ tin**, không bịa số để tính phần trăm cải thiện.

**Đừng dùng thiếu dữ liệu làm lý do trì hoãn mọi cải tiến ít rủi ro**, nhưng cần thận trọng với độ chắc chắn của kết luận.

## 7. Viết giả thuyết có thể bị bác bỏ

### 7.1. Từ khẩu hiệu tới một dự đoán có thể kiểm tra

**Chưa đủ:** “Scrum tăng năng suất.”  
**Tốt hơn:** “Nếu nhóm thử Scrum đầy đủ trong những Sprint có Product Goal/Backlog rõ và Review với stakeholder, số lát cắt được tích hợp và kiểm chứng với người dùng sẽ tăng, trong khi lỗi hồi quy không tăng.”

**Chưa đủ:** “Kanban phù hợp công việc ngẫu nhiên.”  
**Tốt hơn:** “Nếu nhóm vận hành định nghĩa workflow và giới hạn WIP cho yêu cầu không khẩn, work item age và cycle time của nhóm yêu cầu này sẽ giảm, trong khi SLA của incident khẩn không bị vi phạm.”

**Chưa đủ:** “TDD giảm lỗi.”  
**Tốt hơn:** “Nếu nhóm dùng TDD cho một mô đun nhiều lỗi và tích hợp test liên tục, tần suất lỗi hồi quy ở những thay đổi đủ điều kiện sẽ giảm, trong khi lead time và độ tin cậy build không xấu đi.”

### 7.2. Mẫu giả thuyết

> **Nếu** [một can thiệp rõ] **được áp dụng cho** [một phạm vi cụ thể], **thì** [kết quả chính] **sẽ thay đổi theo** [dự đoán có thể kiểm tra], **vì** [cơ chế giả định], **trong khi** [guardrails] **không xấu đi**.

Ví dụ:

> “Nếu Team Booking hạn chế WIP của bug thường xuống mức nhóm có thể hỗ trợ và dành thời gian xem work item age mỗi ngày, thời gian chờ review sẽ giảm vì ít việc tranh cùng người kiểm tra, trong khi lỗi nghiêm trọng và thời gian phản ứng incident không tăng.”

### 7.3. Phải nói trước điều gì khiến giả thuyết bị bác bỏ

| Dự đoán | Quan sát có thể phản bác |
| --- | --- |
| WIP limit giảm chờ. | WIP giảm nhưng cycle time/blocked duration không đổi hoặc tăng, hạng mục khó tiếp tục già đi. |
| Sprint Goal giúp tập trung. | Phần lớn Sprint Goal không thể đạt vì công việc khẩn/đầu vào liên tục đổi, dù chính sách xử lý khẩn đã rõ. |
| Review thường xuyên tăng giá trị học. | Stakeholder không thể tham gia hoặc phản hồi không làm thay đổi lựa chọn sản phẩm; chỉ tạo thêm báo cáo. |
| TDD/CI giảm phát hiện lỗi muộn. | Build/test trở nên không ổn định, lỗi thoát ra production không giảm, thời gian bảo trì quá lớn. |

**Một giả thuyết thất bại là kết quả học được**, không phải bằng chứng nhân viên yếu hoặc cả phương pháp vô giá trị.

### 7.4. Phân biệt chỉ số đầu ra và chỉ số tuân thủ

Số người tham gia Daily Scrum, số PR có test hoặc số card chuyển qua cột là **chỉ số thực thi/thực hành**. Chúng cho biết can thiệp được thực hiện ở mức nào, **chưa chứng minh nó tạo kết quả**.

Một kế hoạch tốt đo đồng thời:

1. **Fidelity:** Can thiệp có thực sự được thực hiện như thiết kế không?
2. **Primary outcome:** Điều chính cần cải thiện có thay đổi không?
3. **System outcome:** Người dùng và toàn dòng có tốt hơn không?
4. **Guardrails:** Có tác hại mới nào không?

### 7.5. Tránh mục tiêu vừa mơ hồ vừa bất khả thi

“Tăng chất lượng 100% trong hai Sprint” không có đơn vị đo. “Giảm mọi lỗi production về 0” không phải dự đoán phù hợp cho hệ thống nhiều biến động; sự kiện hiếm cần đủ thời gian và bằng chứng kỹ thuật.

Đặt mục tiêu **định tính có điều kiện** khi chưa có dữ liệu; nếu chọn ngưỡng định lượng, nói rõ **đó là ngưỡng ra quyết định thực dụng**, không phải bảo đảm thống kê.

## 8. Thiết kế phạm vi thử nghiệm: nhỏ, có thật và đủ an toàn

### 8.1. Năm chiều giới hạn

| Chiều | Câu hỏi | Ví dụ khi thử Kanban trên nhóm đặt lịch |
| --- | --- | --- |
| **Loại công việc** | Feature, bug, hỗ trợ hay discovery? | Chỉ áp dụng luồng **bug không nghiêm trọng**; incident có chính sách riêng. |
| **Người/nhóm tham gia** | Ai cần thay đổi hành vi, ai chỉ tham vấn? | Team Booking cùng người review, test và PO. |
| **Bước workflow** | Can thiệp vào đâu, điểm start/finish ở đâu? | Từ lúc nhận bug đủ rõ tới khi đạt Done, gồm review/test. |
| **Thời gian** | Quan sát bao lâu và khi nào xem lại? | Bốn tuần thử, xem rủi ro hằng ngày và kết quả theo kỳ. |
| **Phơi nhiễm/rủi ro** | Tác động tới sản phẩm, production, dữ liệu và người dùng ra sao? | Đổi chính sách nội bộ; không bỏ test hoặc trì hoãn sự cố. |

**Nhỏ nhất có ích** không đồng nghĩa “một người thử trong một buổi”. Phạm vi phải đủ số lần công việc đi qua cơ chế muốn kiểm chứng, và có đủ sự tham gia để thực hành thật.

### 8.2. Phân biệt thử quy trình với thử chức năng trên khách hàng

**Thử quy trình** có thể là giảm WIP, thay cách tổ chức review hoặc áp dụng TDD ở một mô đun. Tác động trực tiếp tới nhóm và **gián tiếp tới người dùng** qua phần mềm được giao.

**Thử chức năng sản phẩm** có thể là usability test, pilot với ít người dùng hoặc rollout theo tỷ lệ. Loại này cần đánh giá **quyền riêng tư, độ tin cậy, khả năng phục hồi và nguy cơ dữ liệu thật**.

Không vì đang “thử Agile” mà đưa tính năng chưa đạt chuẩn chất lượng cho khách thật. **DoD, an toàn và nghĩa vụ áp dụng là guardrails, không phải biến được phép hy sinh để xem chuyện gì xảy ra.**

### 8.3. Chọn can thiệp chính và điều gì giữ nguyên

Ví dụ thử **giới hạn WIP**:

- **Can thiệp:** Giới hạn số bug thường trong In Progress và ưu tiên hỗ trợ việc đang gần hoàn tất.
- **Giữ nguyên:** Tiêu chí hoàn tất, test tối thiểu, phân loại incident, Product Goal và cách định nghĩa cycle time.
- **Ghi nhận:** Các thay đổi nhân sự, kỳ nghỉ, chiến dịch khách hàng hoặc thay CI đồng thời.
- **Cơ chế dự đoán:** Ít chuyển ngữ cảnh và ít hàng đợi review/test hơn.
- **Rủi ro:** Quá ít WIP có thể khiến người có năng lực không phù hợp phải chờ; cần chính sách linh hoạt và xử lý công việc khẩn.

Nếu đổi đồng thời **WIP, CI, cơ cấu team, định nghĩa Done và thang ước lượng**, nhóm khó biết điều gì tạo khác biệt.

### 8.4. Không cần “đối chứng chịu rủi ro”

Một cách so sánh có thể là quan sát cùng loại bug **trước và trong pilot**, đồng thời ghi các biến số. Khi phù hợp, có thể xem một workflow tương tự chưa đổi; nhưng không nên cố tình giữ nhóm người dùng ở **quy trình đã biết không an toàn** chỉ để làm nhóm đối chứng.

Các cách so sánh tốt đều phải **giữ guardrails và công bằng phù hợp**, không đòi gắn nhãn “thí nghiệm” vào quyết định sửa lỗi nghiêm trọng đã được xác minh.

### 8.5. Ai có quyền phê duyệt phạm vi?

| Quyết định | Người tham gia/thẩm quyền cần rõ |
| --- | --- |
| Thử thay cách làm nội bộ trong giới hạn và tiêu chuẩn hiện có | Developers/nhóm và người chịu trách nhiệm workflow, Product Owner khi ảnh hưởng ưu tiên/giá trị. |
| Thử Scrum đầy đủ | Scrum Team, tổ chức cấp điều kiện về vai trò/trách nhiệm, stakeholder cho feedback và nhịp. |
| Thay quy tắc phát hành, quyền truy cập hoặc dữ liệu | Người có thẩm quyền kỹ thuật, bảo mật, vận hành, pháp lý theo chính sách. |
| Dành thêm ngân sách/người hoặc thay kế hoạch cấp sản phẩm | Product Owner và cấp đầu tư/nhân sự có thẩm quyền theo loại quyết định. |
| Có sự cố đang gây hại | Đường incident response theo mức nghiêm trọng, không chờ kết thúc pilot. |

**Ủy quyền phải rõ** để nhóm có thể thử trong giới hạn; nhưng một framework không tự ban quyền vượt quy định tổ chức.

## 9. Chọn thiết kế quan sát và so sánh phù hợp

### 9.1. Một thay đổi trước–sau: dễ bắt đầu, khó kết luận nguyên nhân

Cách đơn giản:

1. Định nghĩa cùng loại việc và workflow.
2. Quan sát baseline.
3. Áp dụng can thiệp rõ.
4. Thu số liệu trong pilot.
5. So kết quả, kiểm tra guardrails và điều kiện khác biệt.

Ưu điểm: ít chi phí, gần công việc thật. Hạn chế: có thể có **yếu tố mùa vụ, thay nhân sự, đổi độ phức tạp, sự cố, công việc còn dở**. Báo kết quả là **tín hiệu/ước lượng**, không tự khẳng định quan hệ nhân quả.

### 9.2. Thử theo nhiều vòng PDSA

Thay vì ép kết luận sau hai tuần, có thể:

- **Vòng 1:** Quan sát cơ chế và kiểm tra chính sách có áp dụng thật được không.
- **Vòng 2:** Điều chỉnh giới hạn WIP hoặc cách chọn PBI dựa trên blocked.
- **Vòng 3:** Kiểm tra hiệu quả ở workload/nhóm trường hợp rộng hơn, nếu vẫn an toàn.

**Mỗi lần sửa can thiệp cần được ghi rõ**. Không gộp ba phiên bản quy trình vào một “pilot Kanban” duy nhất rồi so trung bình như thể mọi dữ liệu giống nhau.

### 9.3. So luồng tương tự khi thật sự có khả năng

Ví dụ hai luồng bug có nguồn, mức độ và năng lực tương tự; một luồng thử WIP limit mới, luồng kia tiếp tục chính sách cũ **đều đủ an toàn**. So sánh có thể giúp thấy liệu thay đổi có vượt biến động chung không.

Tuy nhiên:

- Hai luồng hiếm khi hoàn toàn tương đồng.
- Người được chia sẻ giữa luồng tạo ảnh hưởng chéo.
- Quy tắc phân loại bug khác sẽ khiến so sánh lệch.
- Một thay đổi CI chung có thể cải thiện cả hai.
- Dùng phương pháp ít hỗ trợ hơn cho một nhóm có thể gây bất công nếu biết nó kém an toàn.

**Không nên khẳng định “có đối chứng là chắc chắn chứng minh nguyên nhân”.**

### 9.4. Ngẫu nhiên hóa là công cụ có điều kiện, không phải bắt buộc

Trong một số thử nghiệm sản phẩm hay quy trình rủi ro thấp, việc phân bổ ngẫu nhiên phù hợp có thể giảm một số thiên lệch. Nhưng với nhóm phát triển, **chỉ có một vài nhóm**, sự khác biệt về năng lực, sản phẩm, vai trò và hiệu ứng học khiến việc ngẫu nhiên hóa người/team không đơn giản.

Không chọn ngẫu nhiên một số khách để chịu lỗi đặt lịch trùng, thiếu kiểm soát dữ liệu hoặc mức bảo mật thấp hơn. **Đạo đức, pháp lý, chất lượng và quyền lợi người dùng** là điều kiện tiền đề.

### 9.5. Phân biệt công việc được chọn vào thử và công việc bị loại

Nếu chọn chỉ **các bug dễ sửa** vào pilot, cycle time có thể giảm vì độ phức tạp thấp, không phải WIP limit hiệu quả.

Nên ghi:

- Tiêu chí bug/PBI được tham gia pilot.
- Số trường hợp đủ điều kiện nhưng không được chọn và lý do.
- Những item đang mở/blocked từ trước pilot.
- Tỷ lệ việc khẩn hoặc ngoại lệ.
- Đặc điểm loại việc trước và trong thử.

**Selection bias** thường lớn hơn vẻ ngoài của một dashboard có nhiều con số đẹp.

## 10. Chọn thời gian thử và lượng quan sát cần thiết

### 10.1. “Hai Sprint” không phải công thức thống kê

Với một nhóm giao vài PBI mỗi tháng, hai Sprint có thể chỉ có **ba hạng mục hoàn tất**, không đủ để nhận xét phân bố cycle time. Với nhóm support nhận nhiều yêu cầu mỗi ngày, hai tuần có thể có đủ trường hợp để hiểu cơ chế WIP.

Thời gian thử phụ thuộc:

1. **Tốc độ công việc đi qua workflow**.
2. **Độ trễ kết quả**: CI có thể phản hồi ngay, giá trị sử dụng có thể mất nhiều tuần.
3. **Mức biến động và rủi ro**.
4. **Thời gian nhóm học cách thực hành mới**.
5. **Mục đích quyết định**: Kiểm tra khả thi, phát hiện tín hiệu hay ước lượng lợi ích đáng tin.

Không có một số Sprint, số người hoặc số hạng mục **đúng cho mọi thử nghiệm**.

### 10.2. Ba cột mốc nên có

- **Mốc kiểm tra thực thi:** Sau vài ngày hoặc một số PBI đầu, các bên có hiểu policy/test/new workflow chưa?
- **Mốc an toàn:** Khi có incident, dữ liệu sai, test không đáng tin hoặc quyền bị vi phạm, có thể dừng ngay.
- **Mốc xem quyết định:** Khi đã qua thời gian và lượng trường hợp dự kiến, nhóm so với giả thuyết và quyết định tiếp.

Mốc an toàn **không đợi tới mốc cuối**. Timebox là khung học, không phải giấy phép duy trì rủi ro.

### 10.3. Khi đủ dữ liệu để khẳng định điều gì?

| Điều muốn biết | Bằng chứng tối thiểu thường cần |
| --- | --- |
| **Có thể thực hiện thực hành không?** | Nhóm có thể áp dụng đúng, chính sách rõ, công cụ/test hoạt động, không gây rủi ro. |
| **Có tín hiệu tích cực không?** | Quan sát nhiều trường hợp liên quan, cùng ranh giới, thấy xu hướng và xem guardrails. |
| **Có khả năng hiệu quả bền hơn không?** | Nhiều vòng/khác loại việc hơn, kiểm tra yếu tố nhiễu, năng lực duy trì và chi phí. |
| **Có thể mở rộng sang nhóm khác không?** | Bối cảnh nhóm mới tương ứng, guardrails phù hợp, có người hướng dẫn và kế hoạch đo lại. |
| **Có bằng chứng nhân quả đủ mạnh không?** | Thiết kế so sánh phù hợp với câu hỏi, lượng quan sát và phân tích tính bất định; không tự suy từ trước–sau. |

Nếu chỉ cần quyết định “Có đáng thử tiếp trên nhóm hiện tại không?”, không nhất thiết phải đầu tư vào một nghiên cứu quy mô lớn. Nếu chuẩn bị áp **toàn tổ chức** và thay quyền nhân sự, mức bằng chứng cần cao hơn.

### 10.4. Những thay đổi có hiệu ứng học tập ban đầu

Khi một nhóm lần đầu dùng TDD hoặc Sprint Goal, trong những ngày đầu họ có thể:

- Chậm hơn vì học công cụ/quy tắc.
- Phát hiện vấn đề test hoặc backlog đã tồn tại nhưng trước đó không thấy.
- Cần thời gian sửa cách chia PBI và hợp tác.

Không vội kết luận “thất bại” vì throughput giảm ngay vòng đầu. Nhưng cũng không **miễn mọi đánh giá vô hạn** với lý do “đang học”. Ghi riêng **chi phí học**, đặt mốc review và kiểm tra guardrails.

### 10.5. Các trường hợp hiếm nhưng nghiêm trọng

Một thử nghiệm có thể không thấy lỗi dữ liệu trong 20 yêu cầu và vẫn chưa chứng minh cơ chế retry an toàn. Với sự kiện hiếm, cần **kiểm thử có chủ đích** các trường hợp concurrent requests, timeout, mất mạng, quyền truy cập, rollback/đối soát; quan sát production **không thay thế chứng minh kỹ thuật phù hợp**.

Không dùng mức tần suất lỗi thấp để hợp lý hóa việc bỏ kiểm soát khi hậu quả rất lớn.

## 11. Thiết kế hệ đo cân bằng: outcome, flow, chất lượng và bền vững

### 11.1. Chỉ số chính phải khớp giả thuyết

| Can thiệp đang thử | Chỉ số chính có thể dùng | Cần thêm dữ liệu gì? |
| --- | --- | --- |
| WIP limit cho bug thường | Cycle time, work item age và thời gian blocked của bug đủ điều kiện. | Throughput, năng lực review/test, incident service level. |
| Sprint Goal và Review trong Scrum | Lát cắt đạt DoD phù hợp Sprint Goal và bằng chứng điều chỉnh Product Backlog. | Outcome khách, biến động việc khẩn, chất lượng, khả năng hoàn tất. |
| TDD ở một module | Lỗi hồi quy, độ phủ các trường hợp hành vi trọng yếu, thời gian sửa lỗi. | CI stability, lead time, chi phí test sai/flaky. |
| CI với tích hợp sớm | Thời gian phát hiện lỗi tích hợp, build reliability và thời gian khôi phục build. | Release stability, lỗi escape, flow tới Done/release. |
| Refinement với ví dụ nghiệp vụ | Tỷ lệ story bị làm lại do hiểu sai yêu cầu và chờ xác nhận. | Feedback người dùng, cycle time, số cuộc trao đổi cần thiết. |

**Một chỉ số chính tốt phản ánh cơ chế muốn kiểm chứng**, không được chọn chỉ vì dễ đo hoặc chắc chắn cải thiện.

### 11.2. Metric contract

~~~yaml
metric: "Cycle time cua bug khong nghiem trong"
purpose: "Kiem tra tac dong cua WIP limit len dong bug"
start: "Bug da duoc triage va bat dau xu ly"
finish: "Bug dat chuan Done da thong nhat"
unit: "Ngay lam viec / bug"
included: "Bug khong nghiem trong cua mot workflow"
excluded: "Incident khan theo quy trinh ung cuu rieng"
aggregation:
  - "Trung vi, trung binh va phan bo"
  - "Cong khai so mau"
  - "Xem them item dang mo qua work item age"
periods:
  baseline: "4 tuan"
  pilot: "4 tuan"
guardrails:
  - "Khong tang loi hoi quy nghiem trong"
  - "Khong vi pham phan ung incident"
  - "Khong doi dinh nghia Done de lam dep so"
interpretation_limit: "So sanh truoc/sau chua tu chung minh nhan qua"
~~~

Mẫu dùng chữ không dấu ở phần giá trị YAML để dễ sao chép sang công cụ cũ; khi sử dụng thật, có thể viết tiếng Việt có dấu và điều chỉnh theo chuẩn tổ chức. Quan trọng là **start/finish, loại việc và cách phân nhóm rõ**, không phải tên công cụ thu metric.

### 11.3. Đo đuôi phân bố và việc còn mở

Một nhóm báo cycle time trung vị giảm từ 10 xuống 6 ngày, nhưng ba item cần phối hợp chuyên gia **đã chờ hơn 30 ngày**. Nếu chỉ xem trung vị, nhóm có thể bỏ qua người dùng đang chịu tác động lớn nhất.

Nên xem:

- **Trung vị** để hiểu trường hợp điển hình.
- **Trung bình** để thấy ảnh hưởng của những item rất chậm.
- **Phân vị cao hoặc các trường hợp đuôi dài** khi đủ mẫu.
- **Work item age** của việc chưa Done.
- **Tỷ lệ blocked và thời gian blocked**, không chỉ nhãn Blocked.
- **Loại công việc và mức khẩn** để không trộn các nhu cầu khác nhau.

### 11.4. Đo outcome sản phẩm, không lẫn với nút bấm

Trong luồng đặt lịch:

- **Click Đặt lịch** không đồng nghĩa lịch thành công.
- **Toast “Thành công”** không chứng minh backend đã Confirmed.
- **Request accepted** có thể khác Confirmed sau đối tác.
- **Một người** có thể có nhiều phiên và mỗi phiên nhiều attempts.

Để kiểm tra cách phối hợp mới có giúp giao giá trị không, có thể theo dõi **tỷ lệ phiên đạt trạng thái Confirmed trong một cửa sổ rõ** và **số lần liên hệ hỗ trợ liên quan**, với mẫu số phù hợp. Không dùng số click làm thước đo chính chỉ vì dễ có.

### 11.5. Không để guardrails là chú thích cuối bảng

Mỗi thử nghiệm cần ít nhất ba loại tín hiệu:

1. **Kết quả chính** mà can thiệp dự đoán tạo ra.
2. **Kết quả hệ thống** để không tối ưu cục bộ.
3. **Guardrails bắt buộc** như lỗi dữ liệu, bảo mật, độ tin cậy, SLA incident, nhịp bền vững.

Ví dụ một nhóm có cycle time giảm nhưng lỗi đặt trùng tăng là **không đạt yêu cầu an toàn**, dù dashboard flow trông tốt hơn.

### 11.6. DORA và các số đo kỹ thuật

Khi thử CI/CD và thực hành XP, có thể tham khảo các phép đo về **khả năng giao thay đổi và độ ổn định vận hành** từ DORA, cùng thời gian phát hiện/sửa lỗi, độ tin cậy pipeline. Nhưng:

- **Deployment frequency** không nên tối đa hóa khi không có giá trị hoặc chưa an toàn.
- **Lead time for changes** phải có ranh giới rõ, không tự bằng thời gian từ ý tưởng tới outcome.
- **Change failure/rollback/recovery** cần định nghĩa nhất quán và xem mức nghiêm trọng.
- Không dùng chỉ số để xếp hạng người hoặc đơn giản hóa khác biệt hệ thống.

**Mục tiêu là giao giá trị an toàn, không chỉ nhiều lần deploy.**

### 11.7. Dữ liệu định tính giúp giải thích nhưng có thiên lệch

Ngoài số liệu, có thể hỏi:

- Developers gặp ít chuyển ngữ cảnh hơn không?
- Product Owner có biết công việc nào đang gần Done và giá trị nào đang bị chặn không?
- Stakeholder có nhận phản hồi đúng lúc hơn không?
- Người hỗ trợ thấy lỗi lặp hay phàn nàn khác đi không?
- Người trực sự cố có còn đủ năng lực phản ứng khi pilot thay workflow không?
- Những người ít nói có được nêu khó khăn hay phương án khác không?

Đừng chỉ khảo sát những người đề xuất phương pháp. **Ghi cả bằng chứng trái chiều**, tránh dùng phản hồi để đánh giá cá nhân hoặc ép người tham gia báo họ “thích Agile”.

## 12. Rủi ro, đạo đức và điều kiện dừng pilot

### 12.1. Điều gì không phải biến thử nghiệm?

Không thử:

- Bỏ kiểm soát bảo mật hoặc quyền truy cập nhằm đo “tốc độ”.
- Đưa code chưa đạt Definition of Done vào production để xem phản hồi.
- Cố tình giữ lỗi tạo trùng đã xác minh ở nhóm người dùng “đối chứng”.
- Cấp quyền truy cập dữ liệu khách không cần thiết cho nghiên cứu pilot.
- Ép Developers làm thêm giờ quá mức như cách tăng năng suất ngắn hạn.
- Cắt nghĩa vụ incident/khôi phục để giữ số story trong Sprint.

**Thử nghiệm phương pháp được chọn để học và cải thiện hệ thống**, không chuyển thiệt hại sang người dùng/nhân viên.

### 12.2. Chính sách sự cố và công việc khẩn

Khi thử Scrum hay Kanban trên một nhóm có trách nhiệm vận hành:

- Xác định **phân loại mức nghiêm trọng** và quyền ứng cứu hiện hành.
- Bảo đảm PBI/bug thông thường không ngăn incident được xử lý.
- Ghi **tác động của incident lên năng lực và flow**.
- Thống nhất cách làm minh bạch nếu công việc khẩn làm thay đổi Sprint plan hoặc phá dự báo.
- Không đếm incident bằng cùng mẫu số với feature bình thường rồi kết luận throughput xấu.

Trong Scrum, chất lượng không giảm; không được thay đổi gây nguy hiểm Sprint Goal, và scope có thể được làm rõ/thương lượng với Product Owner khi học thêm. Với sự cố thực, **trách nhiệm giảm thiệt hại không phụ thuộc vào lịch Scrum**.

### 12.3. Stop conditions trước khi bắt đầu

| Điều kiện | Ví dụ hành động |
| --- | --- |
| **Guardrail dữ liệu/bảo mật bị vi phạm** | Dừng phần liên quan, kích hoạt quy trình xử lý rủi ro và đánh giá lại pilot. |
| **SLA hoặc phản ứng incident bị ảnh hưởng nghiêm trọng** | Khôi phục chính sách ưu tiên khẩn, giảm WIP thử hoặc điều chỉnh phạm vi. |
| **Build/test không còn đáng tin** | Dừng mở rộng thực hành CI/TDD, sửa fixture và test trước. |
| **Tải làm việc không bền vững** | Giảm số sáng kiến đồng thời, điều chỉnh năng lực/timebox. |
| **Không đủ dữ liệu/cách đo sai** | Không tuyên bố thắng lợi; sửa metric contract trước khi quyết định mở rộng. |
| **Không có lợi ích sau nhiều vòng phù hợp** | Dừng hoặc đổi giả thuyết, ghi bài học và chi phí đã bỏ. |

Không cần chờ hết timebox nếu đã có **nguy cơ hoặc thiệt hại rõ**.

### 12.4. Tránh sử dụng dữ liệu cá nhân không cần thiết

Để kiểm tra policy WIP, **timestamps và loại work item** có thể đủ; không cần sao chép nội dung ticket chứa dữ liệu khách vào bảng nghiên cứu công khai.

Nếu cần thử usability hoặc theo dõi dữ liệu sản phẩm:

- Chọn mục đích và nguồn dữ liệu phù hợp.
- Tối thiểu hóa dữ liệu, kiểm soát truy cập và lưu trữ.
- Bảo vệ người tham gia và thực hiện nghĩa vụ thông báo/đồng ý khi áp dụng.
- Dùng dữ liệu giả hoặc tổng hợp khi có thể.
- Tách phân tích hệ thống khỏi đánh giá cá nhân.

### 12.5. Không bắt nhóm “chịu thử” mà không được đóng góp

Nhóm được chọn thí điểm có thể không đủ năng lực hoặc có rủi ro đặc thù. Để thử công bằng:

1. Nêu **mục tiêu và phạm vi** rõ.
2. Tham vấn những người thực sự thay đổi cách làm.
3. Giải thích điều gì cố định, điều gì có thể sửa.
4. Dành thời gian đào tạo/chuẩn bị và công cụ cần thiết.
5. Có kênh báo vấn đề an toàn.
6. Đánh giá kết quả bằng dữ liệu và bối cảnh, **không phạt người nêu giả thuyết thất bại**.

Nhân viên và stakeholder vẫn cần trách nhiệm thực hiện quy tắc đã thống nhất; **tham gia và trách nhiệm không đối lập nhau**.

## 13. Phân rõ quyền quyết định và trách nhiệm đối với thử nghiệm

### 13.1. Ai quyết định phương pháp nhóm sử dụng?

Không có một câu trả lời duy nhất cho mọi tổ chức. Trong Scrum:

- **Product Owner** chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý hiệu quả Product Backlog, không tự động quyết định mọi kỹ thuật.
- **Developers** chịu trách nhiệm lập kế hoạch Sprint Backlog, tạo Increment đạt Definition of Done, thích ứng kế hoạch và cách thực hiện.
- **Scrum Master** chịu trách nhiệm giúp Scrum được hiểu/áp dụng đúng và nâng hiệu quả Scrum Team.
- **Lãnh đạo/người quản lý có thẩm quyền** tạo điều kiện về cơ cấu, nguồn lực, nhân sự, ngân sách, tiêu chuẩn và rủi ro khi cần.

Nhóm có thể quyết định thử một chính sách WIP hoặc thực hành kỹ thuật trong ranh giới được trao quyền; thay đổi **quy trình bắt buộc toàn tổ chức, ngân sách lớn hoặc điều kiện phát hành** cần người có thẩm quyền phù hợp.

### 13.2. Một ma trận quyết định minh họa

| Quyết định | Ai chịu trách nhiệm/chốt theo phạm vi | Ai cần tham gia |
| --- | --- | --- |
| **Vấn đề sản phẩm nào quan trọng?** | Product Owner trong Scrum về Product Backlog/giá trị. | Developers, người dùng, stakeholder, vận hành. |
| **Thử cơ chế phối hợp nào trong một team?** | Scrum Team/nhóm và người quản lý workflow theo ranh giới quyền thực tế. | Người thực hiện, PO nếu ảnh hưởng Product Goal, Scrum Master nếu dùng Scrum. |
| **Thử TDD/CI ở module nào?** | Developers/người có thẩm quyền kỹ thuật theo chính sách. | Người chịu trách nhiệm chất lượng, CI, bảo mật khi cần. |
| **Phân loại incident và quyền ưu tiên ứng cứu?** | Người có thẩm quyền vận hành/incident theo quy trình. | Developers, PO, support và các bên chịu tác động. |
| **Thay quyền release hoặc dùng dữ liệu production?** | Vai trò có thẩm quyền bảo mật/production/pháp lý. | Product, kỹ thuật, vận hành, người có trách nhiệm dữ liệu. |
| **Đầu tư huấn luyện, thêm người, thay cấu trúc team?** | Người có thẩm quyền nguồn lực và nhân sự. | Team, PO, Scrum Master/coach, quản lý chuyên môn. |
| **Giữ/mở rộng pilot?** | Người được giao thẩm quyền lựa chọn cách làm và nguồn lực, dựa trên review của nhóm. | Người tham gia thử và người chịu trách nhiệm guardrails. |

**Không tự tạo quyền chỉ vì tên phương pháp.** Một Scrum Master không trở thành người quyết định ngân sách; một Product Owner không mặc định được bỏ test bảo mật; Developers có trách nhiệm báo rủi ro, không chỉ thực thi máy móc.

### 13.3. Hạn chế “pilot bị áp đặt”

Khi quản lý áp một thực hành từ bên ngoài, người thực hiện có thể:

- Làm đúng hình thức nhưng không hiểu mục đích.
- Bỏ dữ liệu xấu khỏi báo cáo vì sợ đánh giá.
- Không được cấp thời gian học.
- Giữ ngầm cách cũ để hoàn tất công việc.

Nhóm cần tham gia **thiết kế giả thuyết và chính sách**, đưa ra quan ngại hợp lý, cùng xác định cách kiểm chứng. Sponsor vẫn có thể quyết định một hướng thử trong thẩm quyền của mình, nhưng phải **giải thích lý do, guardrails và quyền phản hồi**.

### 13.4. Một decision charter ngắn cho pilot

~~~yaml
pilot: "Gioi han WIP cho bug thuong"
problem: "Nhieu bug cho review va test"
scope: "Team Booking, bug khong nghiem trong"
decision_rights:
  product_order: "Product Owner"
  workflow_policy: "Team va nguoi quan ly workflow trong pham vi da duoc trao quyen"
  technical_quality: "Developers theo chuan kiem thu"
  incident_response: "Nguoi duoc uy quyen theo cap do su co"
  extension: "Cap co quyen ve nhan su va quy trinh lien nhom"
consulted:
  - "Nguoi review/test"
  - "Product Owner"
  - "Nguoi phu trach van hanh"
guardrails:
  - "Khong ha Definition of Done"
  - "Khong tri hoan incident khan"
  - "Khong gia lap du lieu thuc tren nguoi dung"
review: "Ket thuc pilot va ngay khi co dieu kien dung"
~~~

Mẫu là **ví dụ**, không phải văn bản chính sách. Với thử nghiệm nhỏ, một thỏa thuận ngắn có thể đủ; với thay đổi có ảnh hưởng dữ liệu hoặc hợp đồng, cần mức thẩm định tương xứng.

## 14. Vòng PDSA để giữ, sửa hoặc bỏ cách tiếp cận

### 14.1. Plan — xác định điều cần học

Trước khi đổi cách làm, ghi:

1. Bối cảnh và **vấn đề** có bằng chứng.
2. **Can thiệp** và cơ chế nhân–quả giả định.
3. **Dự đoán** kết quả, bao gồm dấu hiệu thất bại.
4. Phạm vi, thời gian, lượng quan sát kỳ vọng.
5. Baseline và **metric contract**.
6. Người có quyền quyết định, tham vấn, nguồn lực.
7. Guardrails, điều kiện dừng và xử lý sự cố.

### 14.2. Do — thử đúng phạm vi, ghi cả lệch kế hoạch

Trong quá trình thử:

- Duy trì lịch/nhịp hoặc chính sách đã định đủ để đánh giá.
- Ghi việc nào không tuân chính sách và **vì sao**.
- Ghi các yếu tố nhiễu: nghỉ phép, lượng yêu cầu đột biến, CI thay đổi, API đối tác lỗi.
- Theo dõi outcome, flow, chất lượng, người dùng và mức tải.
- Tháo những trở ngại cấp thiết thay vì đợi buổi tổng kết.
- Nếu guardrail bị vi phạm, ứng cứu/dừng theo quyền đã định.

Việc không áp dụng được một thực hành là **dữ liệu về tính khả thi**, chứ chưa đủ để nói cơ chế của nó chắc chắn vô dụng.

### 14.3. Study — so dự đoán với dữ liệu

Hỏi:

- Can thiệp **được thực hiện tới mức nào**?
- Chỉ số chính có thay đổi đúng hướng không?
- Outcome của người dùng và flow toàn hệ thống có tốt hơn không?
- Guardrails, chất lượng, nhịp bền vững thế nào?
- Có khác biệt giữa bug nhỏ, feature và incident không?
- Hạng mục chưa hoàn tất có bị bỏ quên không?
- Sự khác biệt có thể do **loại việc, năng lực, mùa vụ hoặc thay đổi khác**?
- Có đủ bằng chứng cho quyết định hiện tại hay cần thử tiếp?

**Không chỉ so số thực tế với target rồi đánh giá đạt/trượt.** Cần hiểu cơ chế, bối cảnh và giới hạn.

### 14.4. Act — bốn hướng hợp lý

| Kết quả | Quyết định | Ví dụ |
| --- | --- | --- |
| Tín hiệu lợi ích, quality giữ, khả thi | **Giữ trong phạm vi thử**, cân nhắc mở rộng có kiểm soát. | WIP limit giảm chờ và không xấu incident; thử thêm luồng tương tự. |
| Có lợi ích nhưng cần thay chi tiết | **Điều chỉnh và thử vòng mới**. | WIP limit quá thấp gây blocked; thay chính sách exception. |
| Không đủ dữ liệu | **Sửa phép đo hoặc mở rộng thời gian/mẫu hợp lý**. | Chỉ hai PBI hoàn tất, cần thêm trường hợp trước khi kết luận. |
| Không hữu ích hoặc gây hại | **Dừng/khôi phục cách làm an toàn**, ghi bài học. | Bỏ review bắt buộc làm lỗi tăng; khôi phục kiểm soát. |

Không có luật “cứ đã bắt đầu Scrum phải tiếp tục vĩnh viễn”. Nhưng nếu thử rồi bỏ **những thành phần cấu thành Scrum** thì kết luận đúng là “đang thay đổi cách làm, có thể không còn dùng Scrum nguyên vẹn”, không thể khẳng định toàn bộ hiệu quả Scrum chỉ từ một nghi thức bị cắt.

### 14.5. Một vòng cải tiến có thể làm lộ nút thắt mới

Giả sử giảm WIP khiến thời gian chờ review giảm. Sau đó các bug dồn sang **môi trường test đối tác**, nơi vẫn chỉ có một người cấp quyền. Đây không nhất thiết là thất bại của WIP limit; nó cho thấy **giới hạn tiếp theo**. Vòng PDSA sau có thể thử fixture/self-service environment an toàn.

Tránh chuỗi “cứ có vấn đề là đổi framework”: nên **tập trung cải tiến cơ chế của hệ thống**, giữ những thực hành đang tạo lợi ích.

### 14.6. Lộ trình thử theo lớp

~~~mermaid
flowchart TD
    A["Quan sát bối cảnh và vấn đề"] --> B["Chọn một cơ chế có khả năng tác động"]
    B --> C["Định nghĩa giả thuyết, phạm vi và guardrails"]
    C --> D["Thu baseline hoặc xác nhận dữ liệu ban đầu"]
    D --> E["Thử trong workflow/nhóm đã chọn"]
    E --> F["Đo outcome + flow + chất lượng"]
    F --> G{"Kết quả so với dự đoán?"}
    G -->|Có lợi ích, an toàn| H["Giữ và cân nhắc mở rộng"]
    G -->|Thiếu dữ liệu| I["Sửa cách đo/quan sát tiếp"]
    G -->|Cần điều chỉnh| J["Đổi giả thuyết/can thiệp"]
    G -->|Gây hại, không hữu ích| K["Dừng và ghi bài học"]
    H -. "Vòng học sau" .-> A
    I -. "Kiểm chứng" .-> C
    J -. "Thử lại" .-> C
    K -. "Chọn giới hạn khác" .-> A
~~~

Đây là sơ đồ **để ra quyết định**, không phải một chuỗi phê duyệt bắt buộc thêm vào Scrum.

## 15. Ví dụ A: thử Kanban trên nhóm có nhiều công việc phát sinh

Toàn bộ số liệu ở phần này **được dựng để học cách phân tích**, không phải dữ liệu dự báo.

### 15.1. Bối cảnh và vấn đề

Team Booking xử lý:

- Bug thường từ khách/hỗ trợ.
- Incident khẩn từ production.
- Một số cải tiến chất lượng định kỳ.
- Các phụ thuộc môi trường test và API đối tác.

Họ đang dùng một lịch kế hoạch định kỳ, nhưng nhiều bug thường xuyên bị kéo vào In Progress trong khi review/test vẫn quá tải. Vấn đề cần cải tiến là **thời gian chờ và tính dự báo của bug không nghiêm trọng**; không phải “chứng minh Scrum dở”.

### 15.2. Baseline bốn tuần

Với luồng bug thường, ranh giới từ **Started** tới **Done theo chuẩn test**:

| Dữ liệu giả định | Trước pilot |
| --- | ---: |
| Số bug đủ điều kiện hoàn tất | 24 |
| Throughput | 6 bug/tuần |
| WIP trung bình | 18 bug |
| Cycle time trung bình | 15 ngày làm việc |
| Cycle time trung vị | 12 ngày làm việc |
| Work item age lớn nhất tại ngày cuối | 21 ngày làm việc |
| Bug từng bị blocked trong kỳ | 8 |
| Sự cố nghiêm trọng được ghi nhận trong kỳ | 2 |

Trong điều kiện đủ ổn định, \(18/6=3\) tuần, tương đương **15 ngày làm việc trung bình**. Đây là **quan hệ trung bình**, không dự báo từng bug cụ thể. Hai sự cố nghiêm trọng được xử lý **theo quy trình incident riêng**, không trộn với bug thường.

### 15.3. Giả thuyết và chính sách

> “Nếu nhóm công khai Definition of Workflow cho bug thường, giới hạn WIP phù hợp với năng lực review/test và ưu tiên hỗ trợ hoàn tất trước khi bắt đầu bug mới, cycle time và work item age sẽ giảm, còn throughput và xử lý incident khẩn không xấu đi.”

**Can thiệp:**

1. Định nghĩa trạng thái **Ready → In Progress → Review → Test → Done**, cách ghi Blocked và các tiêu chí chuyển trạng thái.
2. Thử **giới hạn WIP tổng** ở một mức đủ thấp để giảm phân tán nhưng không gây idle vô nghĩa; mức khởi đầu là một **giả thuyết cần điều chỉnh**, không phải hằng số Kanban.
3. Xem **work item age** mỗi ngày để phát hiện bug bị quên.
4. Dành bước hỗ trợ hoàn tất bug đang blocked khi có thể, trước khi kéo thêm.
5. Incident khẩn có **chính sách ưu tiên riêng**, được ghi tác động lên năng lực pilot.
6. Giữ nguyên chuẩn test và ranh giới start/finish đã định.

### 15.4. Thiết kế và guardrails

| Thành phần | Kế hoạch |
| --- | --- |
| **Phạm vi** | Bug không nghiêm trọng của Team Booking; không thay đường incident. |
| **Timebox** | Bốn tuần quan sát, kiểm tra an toàn hằng ngày. |
| **Chỉ số chính** | Cycle time và work item age. |
| **Chỉ số toàn dòng** | Throughput, blocked duration, mức tồn đọng và việc chưa hoàn tất. |
| **Guardrails** | Lỗi hồi quy, chất lượng test, SLA incident, tải trực. |
| **Điều kiện dừng/sửa** | Incident phản ứng chậm, test bị bỏ, bug khó già đi bất thường. |
| **Quyền quyết định** | Nhóm phối hợp người quản lý workflow và người chịu trách nhiệm sự cố, PO được tham vấn về tác động sản phẩm. |

### 15.5. Kết quả pilot giả định

| Dữ liệu giả định | Trước (4 tuần) | Pilot (4 tuần) |
| --- | ---: | ---: |
| Bug đủ điều kiện hoàn tất | 24 | 28 |
| Throughput | 6/tuần | 7/tuần |
| WIP trung bình | 18 | 11 |
| Cycle time trung bình | 15 ngày làm việc | 7,9 ngày làm việc |
| Cycle time trung vị | 12 ngày | 7 ngày |
| Work item age lớn nhất tại ngày cuối | 21 ngày | 13 ngày |
| Bug từng bị blocked trong kỳ | 8 | 5 |
| Sự cố nghiêm trọng được ghi nhận trong kỳ | 2 | 2 |

**Kiểm tra tính nhất quán mô hình trung bình:** \(11/7 \approx1{,}57\) tuần, tương đương **7,9 ngày làm việc** nếu năm ngày/tuần và điều kiện Little’s Law gần được đáp ứng. Throughput tăng từ 6 lên 7, tức khoảng **16,7%**; cycle time trung bình giảm từ 15 xuống 7,9, tức khoảng **47,3%** trong bộ số liệu giả định.

**Không suy ra** “Kanban chắc chắn khiến mọi đội nhanh hơn 47,3%”. Hai cửa sổ có thể khác nguồn bug, độ khó, năng lực và sự cố; đây là **thử nghiệm quan sát trước–sau**, không có kiểm soát nhân quả mạnh. Một mức WIP thấp hơn cũng không chứng minh chất lượng tự cải thiện.

### 15.6. Study và quyết định

Nhóm kiểm tra:

- Bug trong hai kỳ có mức độ tương tự không?
- Có item khó nào **chưa Done** và đang già đi không?
- Incident được xử lý tốt chứ không chỉ cùng số lượng?
- Có giảm thời gian chờ review/test thật hay chỉ đổi vị trí card?
- Các thành viên có ít chuyển ngữ cảnh hơn không?
- Có xuất hiện thời gian chờ môi trường test lớn hơn sau khi WIP giảm?

**Quyết định hợp lý:** Duy trì chính sách cho luồng bug thường nếu guardrails giữ; tiếp tục điều chỉnh giới hạn và xem thêm một số kỳ. Không mở rộng ngay sang mọi product feature hoặc xem Kanban là lựa chọn duy nhất chỉ từ pilot này.

### 15.7. Nếu kết quả xấu thì sao?

Giả sử WIP giảm nhưng throughput còn 4/tuần và nhiều người chờ việc vì nhóm thiếu reviewer. Có thể:

- WIP limit quá thấp hoặc thiếu cách hỗ trợ người ở điểm nghẽn.
- Chính sách phân chia kỹ năng khiến reviewer không có dự phòng.
- PBI quá lớn hoặc chất lượng test kém.
- Lượng incident lớn khiến dữ liệu lệch.

Cần phân tích cơ chế rồi **sửa hoặc dừng thử cụ thể**. Không đổ lỗi một framework chỉ vì một ngưỡng WIP chưa phù hợp.

## 16. Ví dụ B: thử Scrum để tăng tập trung và vòng phản hồi sản phẩm

### 16.1. Bối cảnh

Team trải nghiệm đặt lịch có backlog nhiều yêu cầu nhưng **không có mục tiêu ngắn hạn rõ**. Thường hai tuần mới có một demo gồm các màn hình rời rạc, người dùng thật chưa thử tác vụ end-to-end; mỗi stakeholder lại đưa yêu cầu mới vào giữa tuần.

Vấn đề là **giá trị và phản hồi đến muộn**, không đơn thuần thiếu số cuộc họp. Nhóm cân nhắc **thử Scrum đầy đủ** trong một khoảng thời gian đủ để có nhiều vòng kiểm tra/thích ứng.

### 16.2. Giả thuyết

> “Nếu nhóm có Product Goal rõ, Product Backlog được Product Owner sắp thứ tự, sử dụng Sprint Goal và tạo Increment đạt DoD, đồng thời dùng Sprint Review để thảo luận với stakeholder và Retrospective để cải tiến, nhóm sẽ hoàn tất và kiểm chứng nhiều lát cắt người dùng hơn mà không giảm chất lượng.”

**Lưu ý:** Chỉ dùng Sprint Planning và Daily Scrum nhưng không có PO, Product Goal, DoD hoặc Increment phù hợp thì **không phải thử đầy đủ Scrum như được định nghĩa trong Scrum Guide**.

### 16.3. Thiết kế

| Thành phần | Nội dung minh họa |
| --- | --- |
| **Product Goal** | Khách tự đặt lịch và biết trạng thái xác nhận an toàn. |
| **Khoảng thử** | Bốn Sprint hai tuần, đủ cơ hội quan sát một vài vòng học. |
| **Đối tượng công việc** | Lát cắt sản phẩm thuộc Product Goal; bug khẩn vẫn theo quy trình ứng cứu. |
| **Scrum roles** | PO, Developers, Scrum Master với trách nhiệm rõ. |
| **Artifacts/commitments** | Product Backlog/Product Goal, Sprint Backlog/Sprint Goal, Increment/DoD. |
| **Events** | Sprint Planning, Daily Scrum, Sprint Review, Sprint Retrospective trong Sprint. |
| **Chỉ số chính** | Lát cắt end-to-end đạt DoD và bằng chứng phản hồi được chuyển thành quyết định. |
| **Guardrails** | Chất lượng, các bất biến đặt lịch, năng lực ứng cứu, nhịp bền vững. |

**Sprint là một Scrum event** bao trùm bốn events còn lại, không phải “một khoảng thời gian tách khỏi Scrum”. Sprint dài tối đa một tháng; một Sprint có thể có nhiều Increment và release khi đủ điều kiện.

### 16.4. Baseline và tín hiệu giả định

Giả sử trước thử, trong tám tuần:

- Có **5 lát cắt end-to-end đạt chuẩn sử dụng**.
- Chỉ **2** lát cắt được kiểm tra trực tiếp với stakeholder/người dùng phù hợp trong kỳ.
- Nhiều yêu cầu bị làm lại do trạng thái **Pending** bị hiểu khác nhau.
- Có **3 lỗi hồi quy nghiêm trọng** đã xác minh.

Trong tám tuần thử:

- Có **8 lát cắt đạt DoD**, gồm công việc trạng thái, tra cứu và chống gửi lặp.
- **6** lát cắt có bằng chứng kiểm tra với stakeholder/người dùng phù hợp.
- Product Backlog đã thay thứ tự ít nhất hai lần theo feedback có ghi lý do.
- Có **2 lỗi hồi quy nghiêm trọng** đã xác minh.

**Diễn giải thận trọng:** Các tín hiệu về Increment và vòng học có vẻ tích cực. Tuy vậy, hai kỳ có thể khác độ khó, năng lực và các thay đổi kỹ thuật như CI; **số lỗi 3 xuống 2 không chứng minh chất lượng chắc chắn tăng**, đặc biệt khi sự cố ít và mức nghiêm trọng khác nhau.

### 16.5. Những câu hỏi cần hỏi sau thử

1. Product Goal có thật sự hướng backlog hay mỗi Sprint vẫn là danh sách yêu cầu của người nói lớn nhất?
2. Sprint Goal có giúp nhóm quyết định **không bắt đầu việc ít giá trị** không?
3. Increment có đạt DoD và tích hợp, hay chỉ demo UI với mock?
4. Sprint Review có đưa tới **quyết định sản phẩm mới** hay chỉ báo cáo trạng thái?
5. Có xử lý công việc khẩn đúng thời điểm mà không giấu ảnh hưởng tới Sprint?
6. Developers có tự lập/điều chỉnh Sprint Backlog hay bị quản lý giao task?
7. Nhóm có đủ quyền và năng lực để áp dụng Scrum, hay nút thắt nằm ngoài nhóm?

**Kết quả có thể là tiếp tục Scrum**, hoặc thay điều kiện tổ chức/nhịp phản hồi. Nếu dòng công việc thật quá đứt đoạn và Sprint Goal không thể có nghĩa, cần xem lại lựa chọn; **không ép giữ tên Scrum bằng mọi giá**.

### 16.6. Không coi “Sprint Goal đạt” là bằng chứng duy nhất

Nhóm có thể đặt Sprint Goal quá dễ để luôn đạt; hoặc chọn Goal rất khó rồi liên tục thất bại. Cần nhìn:

- Giá trị người dùng và Product Goal.
- Khả năng giao Increment có chất lượng.
- Tính minh bạch khi có thay đổi.
- Kết quả Review và khả năng thích ứng.
- Sự bền vững của công việc, khả năng xử lý rủi ro.

**Mức độ tuân thủ một nghi thức phải được xem cùng kết quả hệ thống**, không thay cho kết quả.

## 17. Ví dụ C: thử XP/TDD/CI để giảm hồi quy và tích hợp muộn

### 17.1. Bối cảnh

Team Booking có quy tắc **một chuyên gia không được có hai lịch Confirmed trùng giờ**. Mỗi thay đổi nhỏ ở xử lý timeout/retry thường phát sinh lỗi vì test tích hợp chạy muộn và các điều kiện cạnh tranh ít được kiểm chứng.

Tranh luận “Scrum hay Kanban” chưa giải quyết nút thắt chính: **năng lực thay đổi phần mềm an toàn**.

### 17.2. Giả thuyết và phạm vi

> “Nếu nhóm áp dụng TDD cho quy tắc chống trùng, chạy CI với contract/integration tests phù hợp mỗi khi thay đổi và refactor từng bước ở Booking module, lỗi hồi quy và thời gian phát hiện sai khác sẽ giảm trong khi tốc độ giao thay đổi an toàn không xấu đi đáng kể.”

**Phạm vi thử:** Một mô đun/lát cắt nghiệp vụ, không viết lại toàn kiến trúc.

**Phần không thay đổi:** Quy tắc giao dịch, quyền dữ liệu, DoD, đường incident và cơ chế đối soát production.

### 17.3. Kế hoạch học

1. Cùng chuyên gia miền viết **ví dụ hành vi**: đặt giờ trống, cùng yêu cầu gửi lại, hai khách cạnh tranh, timeout không rõ kết quả.
2. Chọn một thay đổi nhỏ, viết test mô tả hành vi cần giữ.
3. Viết giải pháp đủ đạt test, refactor khi test bảo vệ.
4. Đưa unit, contract và integration tests trọng yếu vào CI.
5. Khi test thất bại, xử lý để pipeline có ý nghĩa; không bỏ test khó để tạo “màu xanh”.
6. Đo thời gian từ thay đổi tới phản hồi test, lỗi hồi quy, build stability và thời gian thay đổi end-to-end.
7. Ghi những lần pairing hoặc học công cụ để đánh giá chi phí triển khai.

### 17.4. Ví dụ test cases cần có

~~~text
CASE 1 - Đặt giờ hợp lệ
Given một khung giờ còn trống
When khách gửi yêu cầu hợp lệ
Then có một lịch Confirmed theo quy tắc

CASE 2 - Gửi lại cùng request
Given request đã được xử lý
When client gửi lại cùng idempotency key
Then không tạo lịch Confirmed thứ hai

CASE 3 - Hai yêu cầu cạnh tranh
Given chỉ còn một slot
When hai yêu cầu khác nhau cố giữ cùng slot gần đồng thời
Then không có hai lịch Confirmed xung đột

CASE 4 - Timeout chưa biết kết quả
Given phía đối tác có thể đã nhận request
When client gặp timeout
Then không tự hiển thị Confirmed nếu chưa có kết quả có thẩm quyền
And cơ chế tra cứu/đối soát không tạo thao tác lặp nguy hiểm
~~~

Đây là **ví dụ hành vi**, chưa phải bộ test tự động đầy đủ. Cần mô phỏng/kiểm chứng ở tầng thích hợp gồm transaction, ràng buộc dữ liệu và contract API thực; **unit tests một mình không đủ chứng minh an toàn cạnh tranh**.

### 17.5. Ví dụ số liệu trước–sau

Giả sử quan sát cùng loại thay đổi trong hai kỳ đủ dài:

| Tín hiệu giả định | Baseline | Trong pilot |
| --- | ---: | ---: |
| Thay đổi Booking module đủ điều kiện | 18 | 20 |
| Lỗi hồi quy phát hiện trước phát hành | 6 | 8 |
| Lỗi hồi quy thoát ra production | 4 | 1 |
| Thời gian phản hồi build/test điển hình | 90 phút | 15 phút |
| Build bị false failure/flaky trong kỳ | 2 | 3 |
| Cycle time trung vị của thay đổi | 6 ngày | 6,5 ngày |

**Đọc dữ liệu đúng:**

- Số lỗi phát hiện **trước** phát hành tăng có thể phản ánh **bắt lỗi sớm hơn**, không tự chứng minh code viết xấu hơn.
- Lỗi production từ 4 xuống 1 là tín hiệu tốt, nhưng mẫu nhỏ và độ nặng từng lỗi cần xem.
- Phản hồi test nhanh hơn rõ ràng theo thước đo đã định.
- Build flaky tăng từ 2 lên 3 cần được điều tra như **guardrail**.
- Cycle time trung vị tăng từ 6 lên 6,5 ngày trong giai đoạn học; không được bỏ qua chi phí này hay tự kết luận nó chắc chắn sẽ giảm về sau.

### 17.6. Kết luận pilot không chỉ “XP tốt hay xấu”

Nhóm có thể **giữ TDD cho các quy tắc nhiều rủi ro**, sửa CI flaky, mở rộng test hợp đồng và bổ sung pairing cho tình huống phức tạp. Không cần ép mọi loại việc dùng đúng cùng cách viết test hoặc đồng thời đổi toàn bộ chính sách Sprint/WIP.

Thực hành XP **bổ sung** cho Scrum hoặc Kanban khi vấn đề của nhóm nằm ở **phản hồi kỹ thuật và khả năng thay đổi an toàn**.

## 18. Thử phối hợp Scrum, Kanban và XP mà không mất khả năng học

### 18.1. Vì sao nên chọn một can thiệp chính theo từng vòng?

Giả sử nhóm muốn đồng thời:

- Bắt đầu Scrum, thêm Sprint Goal và tất cả Scrum events.
- Đặt WIP limit và thay workflow hoàn toàn.
- Áp TDD, CI, pairing và refactoring lên mọi mô đun.
- Chuyển nhóm sang cơ cấu mới, thay hệ thống ticket.
- Đổi Product Goal và thay Product Owner.

Nếu cycle time giảm, không thể biết **điều gì đóng góp bao nhiêu**. Nếu chất lượng xấu, cũng khó xác định cơ chế gây hại. Tải thay đổi lớn còn khiến nhóm không thể thực hiện tốt bất kỳ phương pháp nào.

**Giải pháp thực dụng:** Đặt **vấn đề và cơ chế ưu tiên** trước. Có thể có những điều kiện nền phải bảo vệ ngay như test và quyền dữ liệu; nhưng nên **chia can thiệp có thể kiểm chứng thành các vòng**, ghi rõ thay đổi nào xảy ra lúc nào.

### 18.2. Một lộ trình phối hợp theo giới hạn

| Vòng | Vấn đề có bằng chứng | Can thiệp chính | Tiêu chí học |
| --- | --- | --- | --- |
| **Khởi đầu** | Backlog không rõ giá trị, nhóm làm nhiều phần rời rạc. | Làm rõ Product Goal, trách nhiệm PO, lát cắt và cơ hội review. | Có Increment đúng DoD và feedback thay đổi được quyết định? |
| **Vòng flow** | Nhiều PBI đã bắt đầu nhưng chờ test/review. | Minh bạch workflow, WIP limit, work item age. | Cycle time/blocked giảm mà chất lượng giữ? |
| **Vòng kỹ thuật** | Lỗi hồi quy phát hiện muộn. | TDD/CI/contract tests cho một ranh giới kỹ thuật. | Phát hiện lỗi sớm, production stability và lead time? |
| **Vòng mở rộng** | Phụ thuộc giữa hai nhóm kéo dài. | Hợp đồng chung, integration sớm, quyền ra quyết định rõ. | Increment liên nhóm và độ tin cậy tốt hơn? |

**Không cần thực hiện theo đúng thứ tự trong bảng.** Nếu hiện có lỗi dữ liệu nghiêm trọng, xử lý an toàn là ưu tiên ngay. Nếu nhóm đã có Product Goal và Review tốt, không cần “triển khai lại Scrum” chỉ để đủ bước.

### 18.3. Một Scrum Team có thể đo flow bằng Kanban

Ví dụ Scrum Team có Sprint Goal “Khách tra cứu trạng thái đặt lịch an toàn”. Trong Sprint, Developers dùng board thể hiện In Progress/Review/Test, giới hạn WIP để tránh mở quá nhiều PBI; Daily Scrum giúp kiểm tra tiến độ tới Sprint Goal và điều chỉnh kế hoạch. Nhóm tiếp tục:

- Giữ Product Backlog và trách nhiệm PO.
- Có Sprint Backlog và Sprint Goal rõ.
- Tạo Increment đáp ứng DoD.
- Dùng Sprint Review để kiểm tra kết quả với stakeholder.
- Dùng Retrospective để cải tiến.

Đó là **dùng thực hành Kanban để hỗ trợ flow trong Scrum**, không phải thay Scrum chỉ bằng một bảng. Cần giải thích những chính sách flow mới **giúp Sprint Goal**, không đặt WIP như mục tiêu độc lập.

### 18.4. Một nhóm Kanban có thể dùng một nhịp review

Nhóm hỗ trợ dùng workflow liên tục có thể tổ chức:

- Buổi nhìn WIP/blocked ngắn hằng ngày.
- Review công việc với khách/stakeholder theo kỳ.
- Retrospective hoặc buổi phân tích luồng theo nhu cầu.
- Quy hoạch năng lực cho cải tiến hệ thống.

Những cuộc gặp này **có thể có ích mà không cần gọi đó là Scrum**. Nếu nhóm không có Sprint/Sprint Goal và các sự kiện/cam kết Scrum, đừng mô tả là đã áp dụng Scrum đầy đủ.

### 18.5. Thực hành XP có thể là nền chất lượng của cả hai

TDD, CI và refactoring có thể giúp giảm lỗi hồi quy trong cả nhóm dùng Scrum lẫn Kanban. Nhưng:

- Test phải diễn đạt **hành vi quan trọng**, không chỉ chạy nhanh.
- CI cần xử lý flaky và môi trường không đáng tin.
- Pairing nên có mục tiêu học hoặc giảm rủi ro, không biến thành buổi họp cho mọi task.
- Refactoring cần được bảo vệ bằng test và được cân bằng với Product Goal.

**Nhịp lập kế hoạch và kỹ thuật đảm bảo chất lượng là hai chiều khác nhau**; so “Scrum vs XP” như hai lựa chọn loại trừ nhau thường đặt sai câu hỏi.

### 18.6. Khi nào phối hợp bị biến thành chồng nghi thức?

Các dấu hiệu:

- Vừa có Sprint Planning dài, vừa phải tái lập toàn bộ cam kết trong họp Kanban riêng mỗi ngày.
- Có hai bảng nguồn sự thật và hai người tự thay thứ tự công việc.
- Bắt mọi ticket qua mọi bước giống nhau dù discovery, incident và feature có điều kiện khác.
- Tăng thời gian báo cáo nhưng blocked vẫn chờ.
- Từng nhóm đặt metric khác khiến số liệu không thể hiểu chung.

Cần hỏi **cơ chế nào tạo thông tin và quyết định thật**, loại bỏ nghi thức trùng không có ích, và giữ những thành phần cốt lõi nếu đang cam kết sử dụng một framework đầy đủ.

## 19. Ma trận quyết định sau pilot: giữ, sửa, thử tiếp hay đổi hướng

### 19.1. Đánh giá bằng nhiều chiều thay vì một tổng điểm

| Chiều | Câu hỏi | Bằng chứng ví dụ |
| --- | --- | --- |
| **Phù hợp vấn đề** | Can thiệp có giải quyết giới hạn đã xác định không? | Waiting time/rework liên quan cơ chế đã giảm? |
| **Giá trị** | Người dùng/stakeholder nhận kết quả tốt hơn? | Increment có ích, outcome, số lần hỗ trợ, phản hồi sử dụng. |
| **Flow** | Nhóm giao và dự báo tốt hơn? | WIP, cycle time, work item age, throughput, blocked. |
| **Chất lượng** | Có giữ/giảm rủi ro và lỗi không? | Incident, lỗi hồi quy, test stability, dữ liệu. |
| **Tính thực thi** | Nhóm có duy trì thực hành trong năng lực thật? | Fidelity, đào tạo, thời gian họp, chi phí công cụ. |
| **Cách học** | Nhóm có nhận phản hồi và thích ứng quyết định? | Giả thuyết bị bác bỏ, quyết định backlog/flow được cập nhật. |
| **Phụ thuộc/rủi ro** | Điều kiện tổ chức cho phép tự chủ có trách nhiệm? | Quyền ra quyết định, release, chính sách sự cố, nguồn lực. |
| **Độ tin cậy bằng chứng** | Kết luận dựa trên dữ liệu đủ phù hợp? | Số mẫu, phân bố, biến số nhiễu, định nghĩa metric. |

Một phương pháp **không nên được chọn chỉ vì đạt một ô**. Chẳng hạn có flow tốt nhưng lộ dữ liệu thì **guardrails đã thất bại**.

### 19.2. Ma trận quyết định minh họa theo tính chất bằng chứng

| Tình huống kết quả | Kết luận phù hợp | Bước tiếp theo |
| --- | --- | --- |
| Chính sách WIP được thực hiện đúng, chờ giảm, quality giữ. | Có tín hiệu hữu ích trong phạm vi thử. | Giữ, quan sát thêm, thử mở rộng tương tự có điều kiện. |
| Nhóm thử Scrum nhưng PO không có quyền ưu tiên, Increment chưa có DoD. | **Chưa thử đủ điều kiện** để đánh giá Scrum. | Sửa điều kiện tổ chức/framework trước khi kết luận. |
| TDD giảm lỗi muộn nhưng CI rất flaky. | Một phần cơ chế có lợi, hệ quả phụ cần sửa. | Ổn định pipeline, tiếp tục đo chứ không mở rộng ngay. |
| Pilot chỉ hoàn thành hai item, không có dữ liệu chất lượng. | Bằng chứng chưa đủ. | Điều chỉnh phạm vi/cửa sổ/metric; không tuyên bố thành công. |
| WIP giảm, throughput giảm mạnh, backlog già đi. | Can thiệp hiện tại có thể không phù hợp hoặc chưa đủ. | Điều tra nút thắt, thay chính sách/đào tạo, thử lại hoặc dừng. |
| Lỗi production tăng hoặc incident bị trì hoãn. | Guardrail bị vi phạm. | Dừng phần gây hại, ứng cứu và sửa cơ chế trước khi thử tiếp. |
| Cùng kết quả với chi phí họp quá lớn. | Có thể có cách đơn giản hơn để đạt mục tiêu. | Thử giảm nghi thức, giữ vòng phản hồi/kiểm chứng có giá trị. |

**Quyết định cuối cùng phải được diễn đạt có điều kiện và có phạm vi**, không chỉ “Kanban thắng Scrum” hay “XP đã được chứng minh”.

### 19.3. Thử có đối chứng không đồng nghĩa chọn người thắng chung cuộc

Giả sử nhóm A dùng Scrum, nhóm B dùng Kanban và nhóm C dùng XP. Họ làm **ba sản phẩm khác nhau**, số PBI/incident, năng lực và cách đo khác nhau. So raw velocity, throughput hoặc số lỗi giữa A/B/C để xếp hạng phương pháp là **không có căn cứ**.

Để kiểm tra một giả thuyết, nên so **một can thiệp phù hợp vấn đề trong bối cảnh đủ tương đồng**, ghi rõ khác biệt và bằng chứng. Một số cách làm có thể cùng hữu ích vì chúng tác động lên **giới hạn khác nhau**.

### 19.4. Kết luận nên có cấu trúc

Một mẫu kết luận:

> “Trong [phạm vi] và [thời gian], chúng ta đã thử [can thiệp]. [Chỉ số chính] thay đổi từ [baseline] tới [kết quả] với [số hạng mục, giới hạn]. [Outcome toàn dòng] và [guardrails] cho thấy [điều quan sát]. Kết luận hiện tại là [giữ, sửa, mở rộng, dừng], vì [cơ chế/bằng chứng], trong khi [độ bất định/yếu tố nhiễu] còn mở. Chúng ta sẽ xem lại khi [điều kiện].”

Nếu dữ liệu chưa đủ, **“chưa biết” là câu trả lời hợp lệ** khi đi kèm cách giảm bất định tiếp theo.

## 20. Những phản mẫu khiến thử nghiệm phương pháp không tạo kiến thức

| Phản mẫu | Biểu hiện | Vì sao sai | Cách sửa |
| --- | --- | --- | --- |
| **Chọn phương pháp trước vấn đề** | “Bắt buộc Scrum vì công ty khác dùng.” | Không biết cơ chế nào cần cải thiện. | Phát biểu vấn đề và outcome trước. |
| **Framework shopping liên tục** | Mỗi Sprint đổi nhãn/công cụ vì thấy chưa nhanh. | Không đủ thời gian/quan sát, nhóm bị quá tải. | Giữ một giả thuyết và timebox phù hợp trước khi đổi. |
| **Thử Scrum chỉ bằng Daily Scrum** | Có họp 15 phút, không có PO/Goal/Increment/Review. | Không thực hiện đầy đủ framework đang tuyên bố thử. | Hiểu thành phần Scrum, thử đủ điều kiện hoặc gọi đúng thực hành. |
| **Gọi bảng ticket là Kanban** | Có cột To Do/Doing/Done nhưng WIP không rõ. | Không quản lý flow hay chính sách. | Định nghĩa workflow, WIP và feedback. |
| **Thử XP bằng yêu cầu 100% test coverage** | Đếm dòng test, bỏ hành vi quan trọng. | Coverage không tự bảo đảm lỗi không xảy ra. | Chọn test hành vi/rủi ro, CI, quality/outcome. |
| **Đổi mọi thứ cùng lúc** | Scrum, Kanban, CI, cấu trúc và PO cùng thay. | Không thể phân tích cơ chế, chi phí thay đổi lớn. | Chia thử nghiệm theo lớp, ghi biến số đồng thời. |
| **Đặt ngưỡng “thành công” tùy tiện** | “Mọi thứ phải nhanh hơn 50% sau một tuần.” | Không dựa baseline hoặc thời gian tác động. | Dùng ngưỡng ra quyết định có lý do và giới hạn. |
| **Bỏ công việc khó khỏi pilot** | Chỉ chọn bug dễ sửa. | Thiên lệch mẫu, chỉ số đẹp giả. | Định nghĩa tiêu chí chọn và ghi các item bị loại. |
| **Đổi định nghĩa Done để cải thiện số** | Tính xong khi merge thay vì test tích hợp. | So sánh khác ranh giới, giá trị chưa giao. | Giữ start/finish nhất quán và DoD. |
| **Chỉ xem item hoàn tất** | Item khó nằm Blocked nhiều tuần không hiện trong báo cáo. | Che tồn đọng và rủi ro. | Theo dõi work item age, blocked và WIP. |
| **Lấy velocity làm KPI cấp công ty** | So story points giữa các team khác nhau. | Thang ước lượng không chuẩn, dễ game. | Xem outcome/flow/quality theo bối cảnh. |
| **Bỏ guardrails để tăng flow** | Không review/test để đóng nhiều ticket. | Chuyển chi phí sang lỗi production. | Test, an toàn, incident response là điều kiện. |
| **Dùng khách thật làm nơi thử lỗi đã biết** | Để retry tạo trùng ở pilot để “đủ dữ liệu”. | Gây thiệt hại và vi phạm trách nhiệm. | Sửa/test ở sandbox trước, phát hành an toàn. |
| **Chỉ hỏi người đề xuất ý tưởng** | Người thích Scrum đánh giá Scrum. | Confirmation bias và thông tin thiếu. | Quan sát thực, lấy cả ý kiến trái chiều. |
| **Gọi tương quan là chứng minh** | Cycle time giảm sau pilot → “framework gây ra”. | Có nhiều biến nhiễu và thay đổi đồng thời. | Ghi hạn chế, so dữ liệu phù hợp, thử tiếp. |
| **Không xem chi phí áp dụng** | Mỗi tuần thêm bốn giờ họp vì theo phương pháp. | Có thể mất thời gian tạo giá trị. | Đo chi phí/họp cùng kết quả, giảm nghi thức không ích. |
| **Không có quyền quyết định** | Team thử WIP nhưng quản lý vẫn ép khởi động mọi ticket mới. | Thử không thực hiện đúng can thiệp. | Làm rõ decision rights và sponsorship trước. |
| **Đánh giá cá nhân bằng pilot** | Ai “làm theo Agile ít” bị phạt. | Khuyến khích giấu dữ liệu và giảm an toàn tâm lý. | Đo hệ thống, hỗ trợ học, giữ trách nhiệm nghề nghiệp. |
| **Cố chứng minh một lựa chọn là tốt nhất chung** | So Scrum với Kanban trên công việc khác nhau. | Sai bối cảnh, sai đơn vị. | Chọn theo vấn đề, không xếp hạng thương hiệu. |
| **Thành công nhưng không duy trì** | WIP limit chỉ áp khi có coach. | Kết quả không bền, không thể mở rộng. | Tạo chính sách nhóm hiểu, quyền và năng lực duy trì. |
| **Không ghi quyết định cuối** | Pilot kết thúc, dashboard còn đó, nhóm vẫn tranh luận. | Không đóng vòng học. | Chốt giữ/sửa/dừng, người phụ trách, mốc review. |

### 20.1. Một dashboard đẹp có thể che thất bại

Nhóm thử WIP limit giảm WIP từ 18 xuống 9 nhưng **đẩy 12 item sang cột “Waiting Outside Workflow”** và không đo age ở đó. Chỉ số cycle time giảm do thay ranh giới, còn người dùng chờ lâu hơn.

**Cách phát hiện:** Kiểm tra luồng thật từ yêu cầu tới giá trị, số item đang chờ, ranh giới finish và chất lượng. **Không tối ưu metric bằng cách di chuyển card.**

### 20.2. Một pilot thất bại không chứng minh mọi phiên bản cách tiếp cận đều sai

Nếu Sprint Review không mang lại feedback vì stakeholder không bao giờ dự, có thể vấn đề là **quyền tiếp cận người dùng, cách trình bày Increment hoặc quyết định giá trị**, chứ không thể kết luận “Scrum vô ích”. Ngược lại, nếu dùng Scrum đầy đủ và vẫn không đáp ứng được công việc đến liên tục, có thể chọn cách quản lý flow khác phù hợp hơn.

Một kết luận tốt là **“trong bối cảnh, điều kiện và cơ chế này, chúng ta thấy gì?”**.

### 20.3. Nhiều cuộc họp không thay cho khả năng tích hợp

Một nhóm thêm Daily Scrum, dependency review và ba cuộc họp liên nhóm mà code vẫn tích hợp cuối kỳ, test thiếu và Production xảy ra lỗi. Đường cải tiến có thể là **CI, contract tests, cắt lát giá trị, quyền môi trường và năng lực kiểm thử**, không phải họp thêm.

**Đo số quyết định và vấn đề thực được giải quyết**, không coi tham dự họp là giao giá trị.

### 20.4. Cần phân biệt thất bại do cách làm với điều kiện tổ chức

Một Product Owner có trách nhiệm Product Backlog nhưng **không được quyền thay thứ tự**; Developers muốn TDD nhưng **không được cấp test environment**; nhóm muốn giảm WIP nhưng **mọi lãnh đạo có quyền tự chèn ticket khẩn**.

Nếu pilot không thể triển khai đúng, câu hỏi trước tiên là **điều kiện/ủy quyền nào đang thiếu**. Có thể thử một thay đổi governance nhỏ, thay vì buộc nhóm chọn phương pháp mới và nhận lỗi về mình.

## 21. Bản đồ lựa chọn thử nghiệm theo vấn đề của nhóm

### 21.1. Chọn câu hỏi trước, rồi chọn công cụ

~~~mermaid
flowchart TD
    A["Vấn đề nào ảnh hưởng giá trị nhất?"] --> B{"Nhu cầu/ưu tiên thiếu rõ?"}
    B -->|Có| C["Làm rõ Product Goal, backlog, discovery và feedback"]
    B -->|Không| D{"Việc bắt đầu nhiều nhưng chờ lâu?"}
    D -->|Có| E["Thử workflow rõ, WIP, work item age và Kanban"]
    D -->|Không| F{"Cần tập trung theo mục tiêu ngắn hạn và review?"}
    F -->|Có| G["Đánh giá điều kiện thử Scrum đầy đủ"]
    F -->|Không| H{"Lỗi kỹ thuật phát hiện quá muộn?"}
    H -->|Có| I["Thử XP: TDD, CI, refactoring theo phạm vi"]
    H -->|Không| J["Điều tra phụ thuộc, quyền, chất lượng và tín hiệu mới"]
    C --> K["Giả thuyết + baseline + guardrails"]
    E --> K
    G --> K
    I --> K
    J --> K
    K --> L["Pilot -> Study -> Giữ, sửa hoặc dừng"]
~~~

Sơ đồ là **bộ gợi ý bắt đầu**, không phải cây quyết định cho ra “framework đúng tuyệt đối”. Nhiều vấn đề có thể tồn tại cùng lúc; nhóm ưu tiên **giới hạn cấp thiết và có thể tác động**.

### 21.2. Bảng hướng thử nghiệm theo tình huống

| Bối cảnh chính | Ứng viên thử trước | Điều không được quên | Dấu hiệu để xem lại |
| --- | --- | --- | --- |
| **Feature có Product Goal, cần review thường xuyên** | Scrum đầy đủ hoặc cải thiện feedback/refinement trong cách đang có. | Increment có DoD, quyền PO và stakeholder. | Review chỉ là demo, Goal không giúp ưu tiên, quá nhiều việc dang dở. |
| **Support/bug đến liên tục, WIP cao** | Kanban/flow policies, WIP limit, age review. | Incident class, SLE/SLA phù hợp, chất lượng. | Age/blocked không cải thiện, công việc khó bị đẩy ra ngoài đo. |
| **Nhiều lỗi hồi quy, tích hợp muộn** | TDD, CI, contract tests, pairing đúng chỗ. | Test có ý nghĩa, pipeline ổn định, rủi ro production. | Build flaky tăng, lỗi escape không giảm, chi phí duy trì quá lớn. |
| **Yêu cầu chưa hiểu, nhiều rework** | Discovery có timebox, ví dụ nghiệp vụ, refinement và review người dùng. | PO/decision rights, vấn đề thực thay vì giải pháp được yêu cầu. | Việc nghiên cứu kéo dài mà không dẫn đến quyết định. |
| **Phụ thuộc liên nhóm gây chờ** | Lát cắt tích hợp, hợp đồng/API, decision rights, giới hạn việc song song. | Product Goal chung, DoD chung nếu cùng sản phẩm dùng Scrum. | Các team Done riêng nhưng Increment vẫn chưa dùng được. |
| **Phát hành hiếm dù code xong** | CI/CD và kiểm soát release theo mức rủi ro. | Thẩm quyền vận hành/bảo mật, rollback/đối soát. | Sự cố tăng, feature flags không xử lý hậu quả dữ liệu. |
| **Không có baseline hoặc quyền rõ** | Quan sát workflow, metric contract và charter nhỏ. | Đừng coi thu số liệu như mục tiêu cuối; giữ chất lượng. | Đo liên tục nhưng không có quyết định hay thay đổi thực. |

### 21.3. Phân biệt câu hỏi chọn khung phối hợp và câu hỏi chọn thực hành kỹ thuật

Nếu người dùng phải chờ hai tháng vì nhiều cuộc duyệt, nhóm nên hỏi **quyền/luồng quyết định** trước khi hỏi nên dùng Sprint mấy tuần.

Nếu lỗi tạo trùng lọt production, nhóm cần kiểm tra **bất biến, transaction, kiểm thử đồng thời và vận hành**; không thể giải quyết bằng một Kanban board hay Sprint Goal đơn lẻ.

Nếu Product Goal/feedback thiếu, thêm test có thể làm **phần mềm chạy đúng yêu cầu sai**; cần kết hợp hiểu người dùng với chất lượng kỹ thuật.

**Mỗi phương pháp chạm một số vấn đề**, nhưng ít phương pháp tự giải quyết mọi giới hạn trong hệ thống.

### 21.4. Thứ tự thử có thể phản ánh rủi ro và khả năng học

Khi chưa chắc ưu tiên:

1. **Ứng cứu và bảo vệ các nghĩa vụ bắt buộc** nếu có sự cố.
2. **Giảm bất định lớn** bằng một discovery/spike ít rủi ro.
3. **Thử can thiệp gần nút thắt** với ranh giới và phép đo rõ.
4. **Học từ kết quả**, kiểm tra rủi ro và chi phí.
5. **Chọn bước tiếp** theo giới hạn mới, không theo thương hiệu phương pháp.

Không cần áp một thứ tự cứng nếu bản chất vấn đề khác nhau. Một nhóm đã có CI tốt nhưng không có Product Goal có thể bắt đầu từ **giá trị/ưu tiên**, không nhất thiết thử CI lại.

## 22. Bài tập tình huống và đáp án định hướng

### Tình huống A — Tranh luận Scrum hay Kanban khi chưa có dữ liệu

Team A có Product Owner, làm feature và đôi khi hỗ trợ production. Một nhóm muốn Scrum vì cần kế hoạch ổn định; nhóm khác muốn Kanban vì nhiều việc phát sinh. Họ không biết tỷ lệ việc khẩn, WIP, cycle time hay mức giao Increment.

**Câu hỏi:**

1. Có đủ căn cứ để kết luận một framework phù hợp hơn chưa?
2. Những số liệu/bằng chứng cần thu trước?
3. Một thử nghiệm ít rủi ro đầu tiên có thể là gì?

**Hướng giải:** Chưa đủ. Phân loại feature/bug/incident, đo dòng và blocked, làm rõ Product Goal và feedback. Có thể bắt đầu định nghĩa workflow và quan sát WIP/work item age trong một khoảng phù hợp, hoặc thiết kế Sprint Goal rõ nếu đã có điều kiện Scrum. Cần giả thuyết và guardrails; không đổi toàn tổ chức ngay.

### Tình huống B — Daily Scrum không giúp giải quyết nút thắt

Team tổ chức Daily Scrum đúng 15 phút nhưng PBI vẫn chờ test integration bốn ngày vì môi trường chỉ được cấp bởi một người.

**Câu hỏi:**

1. Đây là bằng chứng Daily Scrum vô dụng hay thiếu điều kiện để cải thiện?
2. Điểm đòn bẩy nào có thể đáng thử?
3. Một chỉ số và một guardrail phù hợp là gì?

**Hướng giải:** Daily Scrum giúp Developers kiểm tra tiến độ tới Sprint Goal, không tự cấp quyền môi trường. Thử fixture test an toàn/self-service có thẩm quyền hoặc đào tạo người dự phòng, đo blocked duration và cycle time; guardrails độ tin cậy test, quyền dữ liệu. Nếu dùng Scrum, vẫn giữ các thành phần Scrum, không biến Daily thành báo cáo chờ quản lý.

### Tình huống C — WIP limit tăng tỷ lệ bận rộn thấp hơn

Sau khi đặt WIP limit, Developers ít có ticket In Progress hơn, nhưng số PBI đạt Done tăng và thời gian chờ giảm. Quản lý phàn nàn “utilization 100% không đạt”.

**Câu hỏi:**

1. Utilization có phải mục tiêu Agile chính không?
2. Dữ liệu nào có ý nghĩa hơn?
3. Có cần bỏ WIP limit không?

**Hướng giải:** Không tự động. Trong công việc tri thức biến động, tối đa hóa số task đang làm có thể tăng chờ và chuyển ngữ cảnh. Xem throughput, cycle time, work item age, outcome, chất lượng và khả năng xử lý incident. Giữ/điều chỉnh WIP theo kết quả, không chỉ mức bận.

### Tình huống D — Đọc Little’s Law

Một workflow ổn định giả định có WIP trung bình **16 item**, throughput trung bình **8 item/tuần**.

1. Mô hình cho thời gian trung bình trong hệ thống bao nhiêu tuần?
2. Nếu WIP giảm còn 12 và throughput giữ nguyên, mô hình cho bao nhiêu tuần?
3. Có được cam kết mọi item hoàn tất trong 1,5 tuần không?

**Đáp án:** (1) \(16/8=2\) tuần; (2) \(12/8=1{,}5\) tuần; (3) không, đây là quan hệ **trung bình** với điều kiện và ranh giới phù hợp. Cần xem phân bố, loại việc, đầu vào/đầu ra và các trường hợp đuôi dài.

### Tình huống E — Cycle time đẹp hơn sau khi đổi định nghĩa Done

Trước pilot, Done nghĩa là test tích hợp đạt và đủ điều kiện phát hành. Trong pilot, Done được chuyển thành “code merge vào main”. Báo cáo cho thấy cycle time giảm từ 12 xuống 5 ngày.

**Câu hỏi:**

1. Có thể so hai con số trực tiếp không?
2. Cần điều chỉnh metric contract thế nào?
3. Nên báo kết quả ở mức nào?

**Hướng giải:** Không, vì ranh giới đã đổi. Khôi phục cách đo nhất quán hoặc tính lại dữ liệu từ nguồn thô, xem thời gian tới Increment đạt DoD/release. Không kết luận phương pháp giúp giảm hơn một nửa thời gian giao giá trị từ hai số này.

### Tình huống F — Thử Scrum nhưng PO không được quyết định

Một nhóm chạy đủ Scrum events nhưng Product Backlog do trưởng dự án sắp thứ tự mỗi tháng và không thể thay theo phản hồi. Review chủ yếu để xin duyệt.

**Câu hỏi:**

1. Scrum đã được thử trong điều kiện phù hợp chưa?
2. Điều gì cần làm rõ về accountability và governance?
3. Một thử nghiệm tổ chức nhỏ là gì?

**Hướng giải:** Trách nhiệm Product Owner có thể chưa được tôn trọng; Scrum events hình thức không phản ánh đầy đủ cơ chế empiricism. Làm rõ Product Goal, quyền PO trong ranh giới đầu tư, Review là kiểm tra/thích ứng chứ không phải gate bắt buộc. Thử giảm một vòng phê duyệt không cần thiết với guardrails và đo decision latency/flow.

### Tình huống G — TDD phát hiện nhiều lỗi hơn trước phát hành

Sau pilot TDD/CI, số lỗi phát hiện **trước** phát hành tăng từ 5 lên 9, lỗi thoát production giảm từ 5 xuống 2. Product Owner nói “chất lượng code xấu vì có nhiều bug hơn”.

**Câu hỏi:**

1. Có thể diễn giải hai số khác nhau thế nào?
2. Cần thêm dữ liệu nào trước khi kết luận?
3. TDD có thể được xem là hữu ích không?

**Hướng giải:** Lỗi được phát hiện sớm hơn có thể là tín hiệu test tốt hơn, không tự chứng minh code xấu. Cần số lần thay đổi, độ khó, mức nghiêm trọng, false failures, lead time và thời gian sửa. Có thể là tín hiệu hữu ích, nhưng chưa đủ xác nhận quan hệ nhân quả hoặc tác động lâu dài.

### Tình huống H — Pilot kéo dài nhưng không có quyết định

Nhóm gọi một cách làm “thử nghiệm sáu tháng”, không nêu giả thuyết hoặc mốc review. Sau mỗi kỳ, họ nói “cần thêm dữ liệu”.

**Câu hỏi:**

1. Thiếu điều gì trong thiết kế?
2. Khi nào việc chờ thêm dữ liệu hợp lý?
3. Khi nào cần dừng hoặc đổi giả thuyết?

**Hướng giải:** Thiếu vấn đề, dự đoán, tiêu chí dữ liệu đủ, guardrails và người quyết định. Có thể kéo dài khi số mẫu ít/độ trễ chưa đủ nhưng phải ghi lý do và điểm xem lại. Nếu đã đủ trường hợp nhưng không có lợi ích hoặc chi phí lớn, cần quyết định dừng/điều chỉnh, không trì hoãn vô hạn.

### Tình huống I — Hai nhóm khác sản phẩm được đem so velocity

Nhóm phát triển web dùng Scrum báo velocity 40 points; nhóm integration dùng Kanban báo 20 ticket Done. Quản lý muốn chọn phương pháp của “nhóm có số lớn hơn”.

**Câu hỏi:**

1. Các con số có cùng đơn vị và ý nghĩa không?
2. Nên chọn cách tiếp cận bằng câu hỏi nào?
3. Có cách so nào ít sai hơn?

**Hướng giải:** Không thể so trực tiếp story points và ticket, càng không thể so khác loại việc/sản phẩm. Mỗi nhóm xác định vấn đề và baseline riêng, thử can thiệp phù hợp, đo outcome/flow/quality với ranh giới rõ. Nếu so được, chỉ so những work items/luồng đủ tương đồng và ghi giới hạn.

### Tình huống J — Pilot làm hỏng phản ứng sự cố

Nhóm hỗ trợ áp WIP limit cứng là ba item, không có chính sách incident khẩn. Một lỗi production nghiêm trọng chờ đến khi có slot trống.

**Câu hỏi:**

1. Vấn đề nằm ở Kanban hay chính sách thử?
2. Cần hành động ngay?
3. Một thiết kế WIP/urgent policy tốt hơn là gì?

**Hướng giải:** Chính sách đã bỏ guardrail và phân loại mức khẩn. Phải ứng cứu ngay theo thẩm quyền, sửa quy tắc ưu tiên sự cố; WIP limit cho dòng thường cần ngoại lệ minh bạch và theo dõi tác động. Không dùng thí nghiệm để trì hoãn thiệt hại.

### Tình huống K — Phản hồi tốt từ nhóm nhưng outcome khách không đổi

Sau khi áp một cadence mới, Developers nói họ thích hơn và ít họp hơn. Nhưng tỷ lệ khách tự đặt lịch không đổi, tổng thời gian chờ API đối tác vẫn cao.

**Câu hỏi:**

1. Điều gì có thể đã được cải thiện?
2. Vì sao chưa thể gọi thành công toàn sản phẩm?
3. Nút thắt tiếp theo đáng điều tra?

**Hướng giải:** Tính bền vững hoặc trải nghiệm nội bộ có thể tốt hơn, là giá trị cần ghi. Nhưng outcome/flow toàn hệ thống chưa được cải thiện rõ. Xem API, quyền đối tác, tích hợp và lựa chọn Product Backlog; không tăng nghi thức chỉ để cố chứng minh cadence có hiệu quả.

### Tình huống L — Hai biến đổi đồng thời

Nhóm đặt WIP limit và triển khai CI pipeline mới cùng ngày. Bốn tuần sau, cycle time giảm 30% và lỗi hồi quy cũng giảm.

**Câu hỏi:**

1. Có thể xác định đóng góp riêng của WIP và CI không?
2. Nên ghi báo cáo thế nào?
3. Làm gì nếu cần biết cơ chế nào đáng mở rộng?

**Hướng giải:** Không từ dữ liệu trước–sau đơn giản. Ghi hai can thiệp và kết quả đồng thời, không quy phần trăm riêng. Nếu đáng đầu tư thêm, thử một cơ chế trên phạm vi khác tương đồng hoặc phân tích thời gian chờ/test feedback, với guardrails và bối cảnh rõ.

### Tình huống M — Scrum và Kanban có thể cùng tồn tại?

Một Scrum Team đã có PO, Sprint Goal, DoD và các Scrum events. Họ muốn thêm WIP limit và dùng work item age trong Daily Scrum để giảm việc dở dang. Một người phản đối: “Đã Scrum thì không thể dùng Kanban.”

**Câu hỏi:**

1. Có mâu thuẫn bắt buộc giữa những thực hành này không?
2. Giả thuyết pilot nên viết thế nào?
3. Khi đánh giá, cần giữ những phần nào của Scrum?

**Hướng giải:** Có thể dùng thực hành Kanban để hỗ trợ quản lý flow trong Scrum; không phải chọn nhãn loại trừ. Thử giới hạn WIP cho một loại PBI và xem cycle time/age/blocked, bảo vệ Sprint Goal, Product Goal, DoD và đầy đủ Scrum framework. Đừng biến WIP limit thành mục tiêu cao hơn chất lượng hoặc việc ứng cứu khẩn.

### Tình huống N — Một story được chia thành nhiều ticket để tăng throughput

Trước thử, nhóm tính mỗi PBI end-to-end là một mục. Trong pilot, UI, API, SQL và test được đếm thành bốn ticket Done. Báo cáo throughput tăng từ 6 lên 18/tuần, nhưng số Increment có ích không đổi.

**Câu hỏi:**

1. Có thể kết luận throughput sản phẩm tăng gấp ba không?
2. Ranh giới measurement bị thay thế nào?
3. Chỉ số nào nên bổ sung?

**Hướng giải:** Không, đơn vị công việc đã đổi. Cần so PBI end-to-end với PBI end-to-end hoặc ghi riêng throughput task kỹ thuật và kết quả sản phẩm. Xem Increment đạt DoD, lead/cycle time tới giá trị, outcome và chất lượng, không tối ưu số ticket.

### Tình huống O — Tính tỷ lệ thay đổi nhưng không nhầm phần trăm với điểm phần trăm

Trong một pilot giả định, tỷ lệ hoàn tất đặt lịch tăng từ **60%** lên **72%**; thời gian chờ review trung vị giảm từ **5 ngày** còn **3 ngày**.

**Câu hỏi:**

1. Completion tăng bao nhiêu **điểm phần trăm**?
2. Completion tăng tương đối bao nhiêu phần trăm?
3. Thời gian chờ review giảm tương đối bao nhiêu phần trăm?
4. Kết quả có tự chứng minh phương pháp gây ra thay đổi không?

**Đáp án:** (1) \(72-60=12\) điểm phần trăm; (2) \((72-60)/60\times100\%=20\%\) tăng tương đối; (3) \((5-3)/5\times100\%=40\%\) giảm tương đối; (4) chưa, cần xem mẫu số, độ khó việc, thay đổi khác, dữ liệu thiếu và guardrails.

### Tình huống P — Người đề xuất không muốn dừng pilot

Nhóm đã thử một chuỗi họp phối hợp mới trong sáu tuần. Tổng thời gian họp tăng, blocked không giảm và nhóm thấy khó tập trung. Người đề xuất nói cần triển khai toàn công ty để “thật sự có hiệu quả”.

**Câu hỏi:**

1. Bằng chứng hiện tại hỗ trợ mở rộng hay xem lại?
2. Có thể giữ một phần thực hành nào?
3. Cách báo quyết định dừng không mang tính công kích?

**Hướng giải:** Không có căn cứ mở rộng chỉ vì pilot không tạo lợi ích. Xem cuộc họp nào thực sự tháo phụ thuộc, giữ kênh đó và bỏ phần trùng; có thể thử hình thức async/đúng người. Báo rằng giả thuyết “nhiều họp sẽ giảm blocked” **chưa được ủng hộ** trong phạm vi quan sát và quyết định dừng/sửa dựa trên outcome, không đánh giá người đề xuất.

## 23. Workshop 75–90 phút: tự thiết kế một thử nghiệm lựa chọn phương pháp

### 23.1. Đề bài chung

Một nhóm Agile phát triển sản phẩm đặt lịch có Product Owner, Developers và trách nhiệm ứng cứu một phần production. Trong sáu tuần:

- Feature quan trọng thường nằm ở Review/Test lâu.
- Các bug hỗ trợ đến xen giữa công việc phát triển.
- Có nhiều PR merge cuối kỳ, integration tests hay hỏng.
- Sprint Review đôi khi chỉ trình diễn mock, khách chưa tự sử dụng.
- Stakeholder yêu cầu tăng số tính năng ra mắt nhưng không nêu Product Goal rõ.
- Một Developer muốn XP/TDD, một người muốn Kanban, người khác muốn Scrum nghiêm túc hơn.

**Nhiệm vụ:** Chọn **một vấn đề có tác động và một can thiệp chính**. Thiết kế pilot để quyết định liệu cách tiếp cận đề xuất có hữu ích, an toàn và đáng duy trì hay không.

### 23.2. Gợi ý tổ chức workshop

| Thời gian | Hoạt động | Đầu ra |
| --- | --- | --- |
| **0–10 phút** | Xác định Product Goal, người dùng, rủi ro và vấn đề cấp bách. | Một outcome và đường incident tách riêng. |
| **10–20 phút** | Phân biệt triệu chứng, nguyên nhân giả định, phương pháp. | Phát biểu vấn đề có bằng chứng/cần đo. |
| **20–35 phút** | Vẽ workflow, baseline và loại việc; xác định nút thắt có thể tác động. | Metric contract và dữ liệu thiếu. |
| **35–50 phút** | Chọn ứng viên Scrum/Kanban/XP hay một thực hành phù hợp. | Giả thuyết có thể bị bác bỏ, cơ chế dự đoán. |
| **50–65 phút** | Khoanh phạm vi, thời gian, lượng quan sát, quyền và guardrails. | Experiment canvas một trang. |
| **65–75 phút** | Thiết kế Study/Act và các kết quả trái dự đoán. | Tiêu chí giữ/sửa/dừng, người quyết định. |
| **75–90 phút** | Phản biện chéo, mô phỏng incident hoặc kết quả bất ngờ. | Bản kế hoạch được chỉnh và bước học kế tiếp. |

**Điều chỉnh thời lượng** theo độ khó, không dùng workshop để trì hoãn sự cố production đang gây hại.

### 23.3. Experiment canvas một trang

~~~text
1. CONTEXT / PRODUCT GOAL
   Người dùng/kết quả quan trọng:
   Team, loại việc, mức ngắt và phụ thuộc:

2. PROBLEM
   Triệu chứng:
   Tác động:
   Bằng chứng và baseline:
   Điều chưa biết:

3. CAUSE HYPOTHESIS
   Nguyên nhân nghi ngờ:
   Dữ liệu hỗ trợ / bác bỏ:
   Cơ chế cần kiểm chứng:

4. APPROACH
   Scrum / Kanban / XP / phối hợp / thực hành cụ thể:
   Can thiệp chính:
   Phần cách làm giữ nguyên:
   Nếu dùng Scrum: có đủ trách nhiệm, events, artifacts/commitments?

5. EXPERIMENT SCOPE
   Loại việc:
   Bước workflow:
   Nhóm/người liên quan:
   Môi trường/phơi nhiễm:
   Thời gian và số trường hợp dự kiến:
   Việc ngoài phạm vi:

6. MEASURES
   Primary outcome và ngưỡng ra quyết định:
   End-to-end outcome:
   Chất lượng/guardrails:
   Work item age / blocked:
   Dữ liệu định tính:
   Metric contract start/finish/đơn vị:

7. SAFETY AND GOVERNANCE
   Quyền quyết định:
   Quyền incident/release:
   Stop conditions:
   Cách xử lý dữ liệu cá nhân:

8. STUDY / ACT
   Dự đoán:
   Tình huống khiến giả thuyết sai:
   Biến số gây nhiễu:
   Ngày/điều kiện xem lại:
   Giữ / sửa / mở rộng / dừng:
   Cách chia sẻ bài học:
~~~

Mẫu chỉ là **công cụ hỗ trợ tư duy**. Với thử nghiệm kỹ thuật nhỏ, một trang có thể đủ; với thay đổi có rủi ro cao, phải bổ sung đánh giá và tài liệu theo thẩm quyền.

### 23.4. Ba lựa chọn để nhóm thảo luận

**Phương án A — Tập trung vào flow:**

> Vấn đề chính là bug và PBI đang mở quá nhiều, chờ Review/Test. Thử workflow rõ và WIP limit cho bug thường, giữ đường incident, đo cycle time/age/throughput và chất lượng.

**Phương án B — Tập trung vào giá trị và feedback:**

> Vấn đề chính là các lát cắt không tạo thành Increment có ích. Làm rõ Product Goal, trách nhiệm PO, cách cắt PBI và thử Scrum đầy đủ với Sprint Goal, Review, Retrospective, DoD; đo Increment/outcome và chất lượng.

**Phương án C — Tập trung vào kỹ thuật:**

> Vấn đề chính là lỗi tích hợp phát hiện muộn. Thử TDD, CI và contract tests cho Booking module; đo thời gian phản hồi test, lỗi hồi quy, lead time và độ ổn định pipeline.

**Không có “đáp án duy nhất”** nếu thiếu dữ liệu hiện trạng. Người học phải **giải thích vì sao chọn một phương án trước và điều gì cần đo để kiểm chứng**, không chỉ nêu sở thích.

### 23.5. Ví dụ kế hoạch hoàn chỉnh

**Vấn đề chọn:** Bug thường của luồng đặt lịch chờ Review/Test nhiều ngày, việc bắt đầu song song quá nhiều làm phản hồi khách đến muộn.

**Giả thuyết:** Dùng một workflow minh bạch và giới hạn WIP sẽ giảm cycle time và age của bug thường, trong khi phản ứng incident và chất lượng không suy giảm.

**Phạm vi:** Một nhóm, một loại bug không khẩn, bốn tuần thử sau khi đã định nghĩa baseline, không thay tiêu chí Done.

**Can thiệp:** Chính sách kéo việc, WIP limit khởi đầu được nhóm thảo luận, kiểm tra work item age, ưu tiên gỡ blocked trước khi nhận thêm bug.

**Chỉ số:** Cycle time, WIP, work item age, throughput, blocked duration; chất lượng test, incident SLA và phản hồi người dùng là guardrails/đối trọng.

**Cơ chế ra quyết định:** Nhóm và người chịu trách nhiệm workflow tự quản trong giới hạn; PO được tham vấn về tác động Product Goal; incident có đường riêng.

**Dự đoán:** Waiting time có thể giảm. Không tuyên bố một tỷ lệ chắc chắn nếu baseline chưa đủ.

**Điểm dừng:** Incident không được xử lý đúng hoặc chất lượng bị bỏ, dữ liệu không đáng tin và không thể bảo vệ người dùng.

**Study/Act:** So cùng loại việc và ranh giới đo, nhìn cả item còn mở, ghi ngoại lệ và các thay đổi ngoài pilot; quyết định giữ/sửa/dừng sau đủ trường hợp.

### 23.6. Phản biện bằng bốn biến cố bất ngờ

**Biến cố 1 — Sự cố production:** Lỗi tạo hai lịch xuất hiện giữa pilot. Nhóm phải chỉ ra ai có quyền ứng cứu, cách cập nhật năng lực và vì sao incident không đợi WIP slot hay Sprint Review.

**Biến cố 2 — Số liệu đẹp nhưng ranh giới bị đổi:** Cycle time giảm một nửa vì Done đã chuyển từ “test đạt” sang “code merge”. Nhóm phải sửa metric contract và từ chối tuyên bố thắng lợi.

**Biến cố 3 — Nửa nhóm không áp dụng:** Reviewer tiếp tục nhận nhiều việc ngoài policy. Nhóm phải phân biệt thất bại **fidelity** với thất bại cơ chế; làm rõ quyền và hỗ trợ, không đổ lỗi một cá nhân.

**Biến cố 4 — CI thay đổi đồng thời:** Một đội khác nâng cấp toàn bộ pipeline trong tuần thứ hai, khiến integration tests nhanh hơn. Nhóm phải ghi biến số nhiễu và hạn chế quy kết toàn bộ cho WIP limit.

### 23.7. Tiêu chí đánh giá bài thực hành

Một kế hoạch đủ tốt giúp người khác trả lời:

1. **Vấn đề cụ thể nào**, của người dùng/flow/chất lượng, đang được giải quyết?
2. Vì sao **can thiệp đã chọn** có cơ chế hợp lý trong bối cảnh?
3. Đâu là **giả thuyết, dự đoán và dấu hiệu trái dự đoán**?
4. Phạm vi và timebox có đủ tạo bằng chứng mà **không mở rộng rủi ro** không?
5. Có baseline, metric contract, outcome/flow và **guardrails** không?
6. Có tính cả việc chưa Done, blocked và biến số nhiễu không?
7. Ai **có thẩm quyền** phê duyệt, dừng và quyết định bước tiếp?
8. Khi có incident, có **đường ứng cứu riêng** không?
9. Cách đánh giá **Scrum/Kanban/XP** có đúng bản chất và không trộn nhãn không?
10. Pilot có thể kết thúc bằng quyết định **giữ/sửa/dừng** chứ không chỉ thêm họp không?

## 24. Checklist thiết kế và đánh giá thử nghiệm lựa chọn cách tiếp cận

### 24.1. Trước khi chọn phương pháp

- [ ] Có một vấn đề có tác động tới người dùng, dòng hoặc chất lượng, không chỉ một nhãn phương pháp.
- [ ] Phân biệt triệu chứng, giả thuyết nguyên nhân và giải pháp.
- [ ] Hiểu loại công việc, mức ngắt, độ rõ Product Goal, rủi ro và phụ thuộc nhóm.
- [ ] Có bằng chứng/baseline đủ dùng hoặc nêu rõ dữ liệu còn thiếu.
- [ ] Ranh giới Product Goal và quyền quyết định ưu tiên sản phẩm được làm rõ.
- [ ] Không chọn framework chỉ vì đội khác dùng, lãnh đạo thích hoặc một chứng nhận.
- [ ] Nếu có sự cố đang gây hại, đường ứng cứu được kích hoạt trước.

### 24.2. Khi viết giả thuyết

- [ ] Có một **can thiệp chính** đủ rõ để người khác áp dụng.
- [ ] Có cơ chế giải thích vì sao can thiệp dự kiến tạo kết quả.
- [ ] Có dự đoán có thể kiểm tra và điều kiện bác bỏ giả thuyết.
- [ ] Phân biệt thử **Scrum đầy đủ** với thử một thực hành như Daily Scrum.
- [ ] Phân biệt thử **Kanban flow policies** với chỉ tạo board có cột.
- [ ] Phân biệt thử **XP/TDD/CI** với chỉ tăng số dòng test.
- [ ] Không đòi phương pháp phải tạo lợi ích cho mọi loại công việc ngay.
- [ ] Chọn primary outcome gắn đúng với cơ chế.

### 24.3. Khi khoanh phạm vi và rủi ro

- [ ] Định nghĩa loại việc, bước workflow, nhóm tham gia, môi trường, timebox.
- [ ] Có lượng trường hợp quan sát dự kiến đủ hợp lý cho quyết định.
- [ ] Nêu điều gì **giữ nguyên** và thay đổi nào ngoài pilot cần ghi.
- [ ] Có tiêu chuẩn start/finish, Done, chất lượng nhất quán.
- [ ] Có chính sách incident/việc khẩn và quyền dừng pilot.
- [ ] Thử nghiệm không cố tình để người dùng chịu lỗi đã biết hoặc bỏ kiểm soát bắt buộc.
- [ ] Quyền dữ liệu, bảo mật, ngân sách và release được làm rõ theo thẩm quyền.
- [ ] Người thực hiện có thời gian học và quyền phản hồi về policy.

### 24.4. Khi đo lường

- [ ] Có metric contract: đơn vị, start/finish, nguồn, thời gian, nhóm loại việc.
- [ ] Theo dõi outcome **người dùng**, flow end-to-end, chất lượng và bền vững.
- [ ] Có guardrails với hành động nếu bị vi phạm.
- [ ] Không chỉ xem ticket Done; có work item age và blocked của việc còn mở.
- [ ] Không trộn story points/velocity giữa những nhóm có thang khác.
- [ ] Không thay cách tính giữa baseline và pilot mà không giải thích.
- [ ] Có dữ liệu định tính từ nhiều người, kể cả phản hồi trái quan điểm.
- [ ] Ghi số trường hợp, loại việc, thay đổi nhân sự/CI/mùa vụ và sự cố.
- [ ] Không gọi tương quan trước–sau là bằng chứng nhân quả chắc chắn.
- [ ] Không chấp nhận “chỉ số tốt” khi lỗi dữ liệu, bảo mật hoặc tải làm việc tăng.

### 24.5. Khi xem lại và quyết định

- [ ] Can thiệp có được áp dụng đúng không, hay cần sửa điều kiện tổ chức?
- [ ] So kết quả với **dự đoán ban đầu**, không chỉ với mục tiêu bị đổi sau thử.
- [ ] Đã xem guardrails, item đuôi dài và việc chưa Done?
- [ ] Có phân biệt lợi ích cục bộ với outcome toàn sản phẩm?
- [ ] Có nói rõ mức tin cậy và giới hạn từ mẫu nhỏ/yếu tố nhiễu?
- [ ] Quyết định là **giữ, điều chỉnh, mở rộng có điều kiện hoặc dừng**.
- [ ] Người có quyền quyết định và người thực thi bước tiếp đã rõ.
- [ ] Những gì không hiệu quả cũng được ghi như kiến thức, không quy lỗi cá nhân.
- [ ] Phần thực hành có ích được tích hợp vào workflow, huấn luyện và công cụ phù hợp.
- [ ] Mở rộng sang nhóm khác có đánh giá lại bối cảnh/guardrails, không nhân bản nghi thức máy móc.

## 25. Ghi nhớ cốt lõi

**Chọn cách tiếp cận Agile không phải thi xem framework nào nổi tiếng hoặc nhiều nghi thức nhất.** Đó là một quyết định dựa trên **vấn đề cụ thể, năng lực nhóm, mức bất định, chất lượng và phản hồi thực tế**.

Nhớ sáu câu hỏi:

1. **Nhóm cần cải thiện điều gì?** Giá trị người dùng, khả năng tập trung, flow, chất lượng hay quyền quyết định?
2. **Cách làm nào tác động vào giới hạn ấy?** Scrum cho nhịp kiểm tra/thích ứng và mục tiêu, Kanban cho flow/WIP, XP cho phản hồi kỹ thuật và khả năng thay đổi — có thể bổ sung nhau.
3. **Làm sao thử mà không gây hại?** Chọn một can thiệp rõ, phạm vi vừa đủ, guardrails và incident path.
4. **Bằng chứng nào giúp ra quyết định?** Baseline, metric contract, outcome, flow, chất lượng, dữ liệu định tính và những việc chưa Done.
5. **Điều gì có thể khiến chúng ta sai?** Mẫu nhỏ, công việc khác nhau, đổi nhiều biến, thiên lệch người được chọn, định nghĩa Done sai và đánh đổi chất lượng.
6. **Sau pilot làm gì?** Giữ, sửa, thử thêm hoặc dừng; ghi bài học và xem lại khi bối cảnh thay đổi.

Trong **Scrum**, trọng tâm là thực nghiệm qua Product Goal, Sprint Goal, Increment đạt Definition of Done và các cơ hội kiểm tra/thích ứng. Trong **Kanban**, hãy nhìn Definition of Workflow, WIP, flow và work item age. Với **XP**, dùng TDD, CI, refactoring, pairing và phát hành nhỏ khi phù hợp để bảo vệ khả năng thay đổi. **PDSA** giúp tổ chức những vòng học giữa các cách tiếp cận mà không biến một giả thuyết thành niềm tin bất biến.

**Thử nghiệm thành công không nhất thiết cho ra câu trả lời “phương pháp này là tốt nhất”. Thành công là nhóm có đủ bằng chứng để chọn bước tiếp tốt hơn, giao phần mềm có giá trị an toàn hơn và cải tiến bền vững trong bối cảnh thật của mình.**

### Tài liệu tham khảo nền tảng

- [Manifesto for Agile Software Development](https://agilemanifesto.org/) — các giá trị Agile: con người/tương tác, phần mềm hoạt động, cộng tác khách hàng, đáp ứng thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html) — giao thường xuyên, cộng tác, chất lượng kỹ thuật, nhịp bền vững và tự xem xét hiệu quả.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — Scrum Team, các Scrum events, artifacts/commitments, Sprint Goal, Product Goal, Increment/DoD.
- [The Kanban Guide](https://kanbanguides.org/) — workflow, WIP, cycle time, throughput, work item age, service level expectation và cải tiến.
- [Scrum.org — The Kanban Guide for Scrum Teams](https://www.scrum.org/resources/kanban-guide-scrum-teams) — tham khảo cách áp dụng thực hành flow trong bối cảnh Scrum.
- [DORA](https://dora.dev/) — tham khảo năng lực giao thay đổi phần mềm và độ ổn định vận hành.
- [Lean Enterprise Institute](https://www.lean.org/) — tư duy dòng giá trị, giải quyết vấn đề và cải tiến có bằng chứng.
- [The W. Edwards Deming Institute](https://deming.org/) — tư duy hệ thống, biến động và vòng Plan–Do–Study–Act.
- Kent Beck (2004), *Extreme Programming Explained: Embrace Change*, ấn bản thứ hai — nền tảng tư tưởng và thực hành XP.
- Nicole Forsgren, Jez Humble và Gene Kim (2018), *Accelerate* — nghiên cứu năng lực giao phần mềm và hiệu quả tổ chức.
